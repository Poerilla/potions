"""OR Profile Probability Engine.

Batch engine that replays 1m RTH tapes per session, builds the 09:30-09:45 NY
opening range (identical to live/strategies/v2b_scaleout.py: R = OR width,
targets are 1R/2R/3R projections from the broken boundary), then walks the
rest of the session as a causal event sequence under two break-trigger
definitions profiled in parallel:

- ``touch``  : a 1m bar pierces the boundary (matches live v2b stop fills)
- ``close5`` : a 5m candle closes outside the OR (close-confirmation taxonomy)

Per session x trigger it emits a timestamped event tape (FirstBreak, Hit1R,
Hit2R, Hit3R, RevertBoundary, TraverseOpposite, ReEntry, OppositeBreak,
OppHit1R, OppHit2R, OppReEntry) plus a terminal day label:

  clean_break_1r, break_extend_2r, break_revert, fakeout_opposite,
  one_r_reversal, double_fail_range, no_break_range, break_hold_no1r

``break_hold_no1r`` is an addition to the planned taxonomy: sessions whose
first break neither reaches 1R nor re-enters the range by EOD.

From the session tape it emits conditional probability tables (N, p, Wilson
95% CI, min-N actionability flag), conditioned on trigger, side, OR-width
quartile (trailing 250 sessions), gap bucket and break-time-of-day bucket,
with per-calendar-year stability slices (a cell is "stable" when the sign of
its edge vs the unconditioned baseline holds in >=70% of qualifying years).

Outputs under live/state/or_profile_engine/<market>/<asof>/:
  events.csv, sessions.csv, tables.csv, reentry_timing.csv, SUMMARY.md
plus a pooled SUMMARY_<asof>.md at the output root.

Usage (from repo root):
  python -m live.or_profile_engine --markets nq --asof 2026H2 --start 2024-06-01 --end 2025-06-01
  python -m live.or_profile_engine --markets nq mnq ym mym --asof 2026H2
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .bars import rth_bars
from .fx_or_markets import FX_MARKETS, FxClock, load_market_gby, session_bars
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO / "live" / "state" / "or_profile_engine"

OR_START = time(9, 30)
OR_END = time(9, 45)
MIN_RAW_RTH_BARS = 300  # excludes holidays / half-days (futures RTH)
MIN_RAW_OR_BARS = 10
RTH_CLOCK = FxClock("rth", OR_START, OR_END, time(16, 0), time(15, 59), MIN_RAW_RTH_BARS)
TRIGGERS = ("touch", "close5")
TRAIL_WINDOW = 250
MIN_TRAIL_SESSIONS = 50
MIN_N_ACTIONABLE = 30
MIN_N_YEAR = 10
STABILITY_THRESHOLD = 0.70
MIN_STABILITY_YEARS = 3

EVENT_COLUMNS = [
    "market",
    "session_date",
    "trigger",
    "seq",
    "event",
    "side",
    "ts",
    "price",
    "bars5_since_break",
    "mfe_r",
    "mae_r",
]


# ---------------------------------------------------------------------------
# Session walker (per trigger)
# ---------------------------------------------------------------------------


@dataclass
class WalkResult:
    trigger: str
    events: List[Dict[str, object]] = field(default_factory=list)
    first_break: bool = False
    first_break_side: str = ""
    first_break_ts: Optional[pd.Timestamp] = None
    hit_1r: bool = False
    hit_2r: bool = False
    hit_3r: bool = False
    ts_1r: Optional[pd.Timestamp] = None
    reentry: bool = False
    reentry_ts: Optional[pd.Timestamp] = None
    bars5_to_reentry: Optional[int] = None
    revert_boundary: bool = False
    traverse_opposite: bool = False
    opposite_break: bool = False
    opposite_break_ts: Optional[pd.Timestamp] = None
    opp_hit_1r: bool = False
    opp_hit_2r: bool = False
    opp_reentry: bool = False
    mfe_r: float = 0.0
    mae_r: float = 0.0

    def label(self) -> str:
        if not self.first_break:
            return "no_break_range"
        if self.hit_1r:
            if self.traverse_opposite or self.opposite_break:
                return "one_r_reversal"
            if self.hit_2r:
                return "break_extend_2r"
            if self.reentry:
                return "break_revert"
            return "clean_break_1r"
        if self.reentry:
            if self.opposite_break:
                return "fakeout_opposite" if self.opp_hit_1r else "double_fail_range"
            return "break_revert"
        return "break_hold_no1r"


class SessionWalker:
    """Causal OR state machine for one session under one trigger definition.

    Price points are fed through each bar as an ordered 4-point path
    (open -> first extreme -> second extreme -> close, ordered by candle
    color) so intra-bar event sequencing is deterministic. Close-based
    events (close5 breaks, re-entry closes) fire on 5m candle closes for
    BOTH triggers: the touch trigger detects breaks/level hits off 1m
    pierces (matching v2b stop fills) but confirms re-entry on 5m closes,
    otherwise nearly every touch break registers a momentary 1m re-entry
    and the day labels degenerate.
    """

    def __init__(self, market: str, session_date: date, orh: float, orl: float, trigger: str):
        self.market = market
        self.session_date = session_date
        self.orh = orh
        self.orl = orl
        self.r = orh - orl
        self.trigger = trigger
        self.res = WalkResult(trigger=trigger)
        self.phase = "pre"  # pre -> broken -> inside -> opp_broken -> opp_inside
        self._seq = 0
        self._up: Optional[bool] = None  # first break direction

    # -- helpers ----------------------------------------------------------

    def _bars5(self, ts: pd.Timestamp) -> Optional[int]:
        if self.res.first_break_ts is None:
            return None
        return int((ts - self.res.first_break_ts).total_seconds() // 300)

    def _emit(self, event: str, side: str, ts: pd.Timestamp, price: float) -> None:
        self._seq += 1
        self.res.events.append(
            {
                "market": self.market,
                "session_date": self.session_date.isoformat(),
                "trigger": self.trigger,
                "seq": self._seq,
                "event": event,
                "side": side,
                "ts": ts.isoformat(),
                "price": round(float(price), 4),
                "bars5_since_break": self._bars5(ts),
                "mfe_r": round(self.res.mfe_r, 3),
                "mae_r": round(self.res.mae_r, 3),
            }
        )

    def _boundary(self) -> float:
        return self.orh if self._up else self.orl

    def _opp_boundary(self) -> float:
        return self.orl if self._up else self.orh

    def _update_excursions(self, p: float) -> None:
        if self._up is None:
            return
        boundary = self._boundary()
        fav = (p - boundary) / self.r if self._up else (boundary - p) / self.r
        adv = -fav
        if fav > self.res.mfe_r:
            self.res.mfe_r = fav
        if adv > self.res.mae_r:
            self.res.mae_r = adv

    # -- price-point processing -------------------------------------------

    def on_price(self, ts: pd.Timestamp, p: float) -> None:
        res = self.res
        if self.phase == "pre":
            if self.trigger != "touch":
                return
            if p > self.orh:
                self._first_break(ts, p, up=True)
            elif p < self.orl:
                self._first_break(ts, p, up=False)
            return

        self._update_excursions(p)
        boundary = self._boundary()
        sign = 1.0 if self._up else -1.0

        # First-break-side level hits track through EOD regardless of phase:
        # the tables ask "did boundary +/- kR trade at any point after break".
        if not res.hit_1r and sign * (p - boundary) >= self.r:
            res.hit_1r, res.ts_1r = True, ts
            self._emit("Hit1R", res.first_break_side, ts, p)
        if res.hit_1r and not res.hit_2r and sign * (p - boundary) >= 2.0 * self.r:
            res.hit_2r = True
            self._emit("Hit2R", res.first_break_side, ts, p)
        if res.hit_2r and not res.hit_3r and sign * (p - boundary) >= 3.0 * self.r:
            res.hit_3r = True
            self._emit("Hit3R", res.first_break_side, ts, p)
        if res.hit_1r and not res.revert_boundary and sign * (p - boundary) <= 0.0:
            res.revert_boundary = True
            self._emit("RevertBoundary", res.first_break_side, ts, p)
        if res.hit_1r and not res.traverse_opposite and sign * (p - self._opp_boundary()) <= 0.0:
            res.traverse_opposite = True
            self._emit("TraverseOpposite", res.first_break_side, ts, p)

        if self.phase == "inside" and self.trigger == "touch":
            if (self._up and p < self.orl) or ((not self._up) and p > self.orh):
                self._opposite_break(ts, p)

        if self.phase == "opp_broken":
            opp_sign = -sign
            opp_boundary = self._opp_boundary()
            if not res.opp_hit_1r and opp_sign * (p - opp_boundary) >= self.r:
                res.opp_hit_1r = True
                self._emit("OppHit1R", self._opp_side(), ts, p)
            if res.opp_hit_1r and not res.opp_hit_2r and opp_sign * (p - opp_boundary) >= 2.0 * self.r:
                res.opp_hit_2r = True
                self._emit("OppHit2R", self._opp_side(), ts, p)

    def _opp_side(self) -> str:
        return "down" if self._up else "up"

    def _first_break(self, ts: pd.Timestamp, p: float, *, up: bool) -> None:
        self._up = up
        self.phase = "broken"
        self.res.first_break = True
        self.res.first_break_side = "up" if up else "down"
        self.res.first_break_ts = ts
        self._emit("FirstBreak", self.res.first_break_side, ts, p)
        self._update_excursions(p)

    def _opposite_break(self, ts: pd.Timestamp, p: float) -> None:
        self.phase = "opp_broken"
        self.res.opposite_break = True
        self.res.opposite_break_ts = ts
        self._emit("OppositeBreak", self._opp_side(), ts, p)

    # -- close processing ---------------------------------------------------

    def on_close(self, ts: pd.Timestamp, c: float) -> None:
        res = self.res
        if self.phase == "pre":
            if self.trigger == "close5":
                if c > self.orh:
                    self._first_break(ts, c, up=True)
                elif c < self.orl:
                    self._first_break(ts, c, up=False)
            return

        inside = self.orl <= c <= self.orh
        if self.phase == "broken" and inside:
            res.reentry = True
            res.reentry_ts = ts
            res.bars5_to_reentry = self._bars5(ts)
            self.phase = "inside"
            self._emit("ReEntry", res.first_break_side, ts, c)
            return

        if self.phase == "inside" and self.trigger == "close5":
            if (self._up and c < self.orl) or ((not self._up) and c > self.orh):
                self._opposite_break(ts, c)
                return

        if self.phase == "opp_broken" and inside:
            res.opp_reentry = True
            self.phase = "opp_inside"
            self._emit("OppReEntry", self._opp_side(), ts, c)

    def finish(self, ts: pd.Timestamp, close: float) -> WalkResult:
        self._emit("SessionEnd", self.res.first_break_side, ts, close)
        return self.res


def _bar_path(o: float, h: float, l: float, c: float) -> Tuple[float, ...]:
    # Green candle: assume open -> low -> high -> close; red: open -> high -> low -> close.
    if c >= o:
        return (o, l, h, c)
    return (o, h, l, c)


def walk_session(
    market: str,
    session_date: date,
    dense: pd.DataFrame,
    orh: float,
    orl: float,
    trigger: str,
    or_end: time = OR_END,
) -> WalkResult:
    walker = SessionWalker(market, session_date, orh, orl, trigger)
    post_or = dense[dense.index.map(lambda ts: ts.time() >= or_end)]

    if trigger == "touch":
        bars = post_or
        for ts, row in bars.iterrows():
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            for p in _bar_path(o, h, l, c):
                walker.on_price(ts, p)
            if ts.minute % 5 == 4:  # this 1m bar completes a 5m candle
                walker.on_close(ts + pd.Timedelta(minutes=1), c)
        last_ts = bars.index[-1]
        return walker.finish(last_ts, float(bars.iloc[-1]["close"]))

    bars5 = (
        post_or.resample("5min", label="left", closed="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna(subset=["open"])
    )
    for ts_start, row in bars5.iterrows():
        ts = ts_start + pd.Timedelta(minutes=5)  # event time = candle completion
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        if walker.phase == "pre":
            # Break only confirms on the 5m close; the confirming candle's own
            # extreme beyond the close is not credited (conservative).
            walker.on_close(ts, c)
            if walker.phase != "pre":
                walker.on_price(ts, c)
            continue
        for p in _bar_path(o, h, l, c):
            walker.on_price(ts, p)
        walker.on_close(ts, c)
    last_ts = bars5.index[-1] + pd.Timedelta(minutes=5)
    return walker.finish(last_ts, float(bars5.iloc[-1]["close"]))


# ---------------------------------------------------------------------------
# Session features
# ---------------------------------------------------------------------------


def _gap_bucket(gap_prior_range: Optional[float]) -> str:
    if gap_prior_range is None or not math.isfinite(gap_prior_range):
        return ""
    if abs(gap_prior_range) < 0.10:
        return "flat"
    side = "up" if gap_prior_range > 0 else "dn"
    mag = "lg" if abs(gap_prior_range) >= 0.50 else "sm"
    return "gap_%s_%s" % (side, mag)


def _or_loc_bucket(or_loc: Optional[float]) -> str:
    if or_loc is None or not math.isfinite(or_loc):
        return ""
    if or_loc < 0.0:
        return "below_prior"
    if or_loc > 1.0:
        return "above_prior"
    if or_loc < 0.33:
        return "lower_third"
    if or_loc < 0.67:
        return "mid_third"
    return "upper_third"


def _break_tod_bucket(ts: Optional[pd.Timestamp], or_end: time = OR_END) -> str:
    """Absolute NY buckets for RTH; relative early/mid/late for other clocks."""
    if ts is None:
        return ""
    t = ts.time()
    if or_end == OR_END:
        if t <= time(10, 30):
            return "0945_1030"
        if t <= time(12, 0):
            return "1030_1200"
        return "1200_eod"
    # relative to OR end: +45m / +2h30m
    mins = t.hour * 60 + t.minute
    base = or_end.hour * 60 + or_end.minute
    if mins <= base + 45:
        return "early"
    if mins <= base + 150:
        return "mid"
    return "late"


def _trailing_percentile(history: Sequence[float], value: float) -> Optional[float]:
    if len(history) < MIN_TRAIL_SESSIONS:
        return None
    window = history[-TRAIL_WINDOW:]
    rank = sum(1 for w in window if w <= value)
    return 100.0 * rank / len(window)


def _quartile(pctile: Optional[float]) -> str:
    if pctile is None:
        return ""
    if pctile < 25.0:
        return "q1"
    if pctile < 50.0:
        return "q2"
    if pctile < 75.0:
        return "q3"
    return "q4"


# ---------------------------------------------------------------------------
# Market run
# ---------------------------------------------------------------------------


def run_market(
    market: str,
    *,
    asof: str,
    output_root: Path,
    start: Optional[date] = None,
    end: Optional[date] = None,
    max_days: Optional[int] = None,
) -> Optional[Path]:
    key = market.lower()
    fx = FX_MARKETS.get(key)
    if fx is not None:
        if not fx.path.exists():
            print("SKIP %s: missing 1m data at %s" % (market, fx.path), flush=True)
            return None
        gby = load_market_gby(fx)
        clock = fx.clock
        label_market = fx.key
        instrument_label = fx.symbol
    else:
        cfg = MARKETS[key]
        if not cfg.dbn_path.exists():
            print("SKIP %s: missing 1m data at %s" % (market, cfg.dbn_path), flush=True)
            return None
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
        clock = RTH_CLOCK
        label_market = cfg.market
        instrument_label = cfg.instrument

    days = sorted(gby)
    if start is not None:
        days = [d for d in days if d >= start]
    if end is not None:
        days = [d for d in days if d <= end]
    if max_days is not None:
        days = days[:max_days]

    out_dir = output_root / key / asof
    out_dir.mkdir(parents=True, exist_ok=True)

    event_rows: List[Dict[str, object]] = []
    session_rows: List[Dict[str, object]] = []
    or_width_history: List[float] = []
    prior_high = prior_low = prior_close = None
    n_walked = n_skipped = 0

    for idx, day in enumerate(days, start=1):
        if fx is not None:
            raw = session_bars(gby.get(day), day, clock, dense=False)
            dense = session_bars(gby.get(day), day, clock, dense=True)
        else:
            raw = rth_bars(gby.get(day), day, dense=False)
            dense = rth_bars(gby.get(day), day, dense=True)

        if raw.empty or len(raw) < max(40, clock.min_session_bars // 4):
            n_skipped += 1
            continue
        raw_or = raw[raw.index.map(lambda ts: ts.time() < clock.or_end)]
        if len(raw_or) < clock.min_or_bars:
            n_skipped += 1
            continue
        if dense.empty or len(dense) < max(60, clock.min_session_bars // 2):
            n_skipped += 1
            continue

        or_bars = dense[dense.index.map(lambda ts: ts.time() < clock.or_end)]
        orh = float(or_bars["high"].max())
        orl = float(or_bars["low"].min())
        r = orh - orl
        if not (r > 0):
            n_skipped += 1
            continue

        session_open = float(dense.iloc[0]["open"])
        session_close = float(dense.iloc[-1]["close"])

        or_pctile = _trailing_percentile(or_width_history, r)
        prior_range = (
            (prior_high - prior_low)
            if (prior_high is not None and prior_low is not None and prior_high > prior_low)
            else None
        )
        gap_pts = (session_open - prior_close) if prior_close is not None else None
        gap_pr = (gap_pts / prior_range) if (gap_pts is not None and prior_range) else None
        or_mid = (orh + orl) / 2.0
        or_loc = ((or_mid - prior_low) / prior_range) if (prior_range and prior_low is not None) else None

        base_features = {
            "or_high": round(orh, 6),
            "or_low": round(orl, 6),
            "or_width_pts": round(r, 6),
            "or_width_pctile": round(or_pctile, 1) if or_pctile is not None else "",
            "or_width_q": _quartile(or_pctile),
            "prior_close": round(prior_close, 6) if prior_close is not None else "",
            "prior_range": round(prior_range, 6) if prior_range is not None else "",
            "gap_pts": round(gap_pts, 6) if gap_pts is not None else "",
            "gap_prior_range": round(gap_pr, 4) if gap_pr is not None else "",
            "gap_bucket": _gap_bucket(gap_pr),
            "or_loc": round(or_loc, 4) if or_loc is not None else "",
            "or_loc_bucket": _or_loc_bucket(or_loc),
            "session_open": round(session_open, 6),
            "session_close": round(session_close, 6),
            "clock": clock.name,
        }

        for trigger in TRIGGERS:
            res = walk_session(label_market, day, dense, orh, orl, trigger, or_end=clock.or_end)
            event_rows.extend(res.events)
            close_vs_or = (
                "above" if session_close > orh else ("below" if session_close < orl else "inside")
            )
            session_rows.append(
                {
                    "market": label_market,
                    "session_date": day.isoformat(),
                    "year": day.year,
                    "trigger": trigger,
                    "label": res.label(),
                    **base_features,
                    "first_break": int(res.first_break),
                    "first_break_side": res.first_break_side,
                    "first_break_ts": res.first_break_ts.isoformat() if res.first_break_ts is not None else "",
                    "break_tod_bucket": _break_tod_bucket(res.first_break_ts, clock.or_end),
                    "hit_1r": int(res.hit_1r),
                    "hit_2r": int(res.hit_2r),
                    "hit_3r": int(res.hit_3r),
                    "ts_1r": res.ts_1r.isoformat() if res.ts_1r is not None else "",
                    "reentry": int(res.reentry),
                    "reentry_ts": res.reentry_ts.isoformat() if res.reentry_ts is not None else "",
                    "bars5_to_reentry": res.bars5_to_reentry if res.bars5_to_reentry is not None else "",
                    "revert_boundary": int(res.revert_boundary),
                    "traverse_opposite": int(res.traverse_opposite),
                    "opposite_break": int(res.opposite_break),
                    "opposite_break_ts": res.opposite_break_ts.isoformat()
                    if res.opposite_break_ts is not None
                    else "",
                    "opp_hit_1r": int(res.opp_hit_1r),
                    "opp_hit_2r": int(res.opp_hit_2r),
                    "opp_reentry": int(res.opp_reentry),
                    "mfe_r": round(res.mfe_r, 3),
                    "mae_r": round(res.mae_r, 3),
                    "close_vs_or": close_vs_or,
                }
            )

        or_width_history.append(r)
        prior_high = float(dense["high"].max())
        prior_low = float(dense["low"].min())
        prior_close = session_close
        n_walked += 1
        if idx % 500 == 0:
            print("  %s: %d/%d sessions walked" % (instrument_label, idx, len(days)), flush=True)

    print(
        "%s: %d sessions walked, %d skipped (holiday/half-day/missing OR)"
        % (instrument_label, n_walked, n_skipped),
        flush=True,
    )
    if not session_rows:
        return None

    events_df = pd.DataFrame(event_rows, columns=EVENT_COLUMNS)
    sessions_df = pd.DataFrame(session_rows)
    events_df.to_csv(out_dir / "events.csv", index=False)
    sessions_df.to_csv(out_dir / "sessions.csv", index=False)

    tables_df = emit_tables(sessions_df)
    tables_df.to_csv(out_dir / "tables.csv", index=False)
    timing_df = emit_reentry_timing(sessions_df)
    timing_df.to_csv(out_dir / "reentry_timing.csv", index=False)
    write_market_summary(out_dir, label_market, sessions_df, tables_df, timing_df)
    return out_dir


# ---------------------------------------------------------------------------
# Probability tables
# ---------------------------------------------------------------------------


def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


# (table_name, denominator query, numerator column)
TABLE_SPECS: List[Tuple[str, str, str]] = [
    ("hit1r_given_break", "first_break == 1", "hit_1r"),
    ("hit2r_given_1r", "hit_1r == 1", "hit_2r"),
    ("hit3r_given_2r", "hit_2r == 1", "hit_3r"),
    ("reentry_given_break", "first_break == 1", "reentry"),
    ("reentry_given_no1r_break", "first_break == 1 and hit_1r == 0", "reentry"),
    ("revert_boundary_given_1r", "hit_1r == 1", "revert_boundary"),
    ("traverse_opp_given_1r", "hit_1r == 1", "traverse_opposite"),
    ("opp_break_given_1r_revert", "hit_1r == 1 and revert_boundary == 1", "opposite_break"),
    ("opp_break_given_failed_break", "first_break == 1 and hit_1r == 0 and reentry == 1", "opposite_break"),
    ("opp_hit1r_given_opp_break", "hit_1r == 0 and reentry == 1 and opposite_break == 1", "opp_hit_1r"),
    ("opp_hit2r_given_opp_break", "hit_1r == 0 and reentry == 1 and opposite_break == 1", "opp_hit_2r"),
]

CONDITION_DIMS: List[Tuple[str, ...]] = [
    (),
    ("first_break_side",),
    ("or_width_q",),
    ("gap_bucket",),
    ("break_tod_bucket",),
    ("or_width_q", "gap_bucket"),
    ("or_width_q", "break_tod_bucket"),
]


def _cell_stats(den: pd.DataFrame, num_col: str) -> Tuple[int, int, float, float, float]:
    n = len(den)
    k = int(den[num_col].sum())
    p, lo, hi = wilson_ci(k, n)
    return n, k, p, lo, hi


def emit_tables(sessions_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for trigger in TRIGGERS:
        tdf = sessions_df[sessions_df["trigger"] == trigger]
        for table_name, den_query, num_col in TABLE_SPECS:
            den_all = tdf.query(den_query)
            if den_all.empty:
                continue
            n_all, k_all, p_all, lo_all, hi_all = _cell_stats(den_all, num_col)

            # Per-year unconditioned baselines for stability scoring.
            year_baseline: Dict[int, float] = {}
            for year, ydf in den_all.groupby("year"):
                if len(ydf) >= MIN_N_YEAR:
                    year_baseline[int(year)] = float(ydf[num_col].mean())

            for dims in CONDITION_DIMS:
                if not dims:
                    groups = [("all", den_all)]
                else:
                    valid = den_all
                    for d in dims:
                        valid = valid[valid[d].astype(str) != ""]
                    groups = [
                        ("|".join("%s=%s" % (d, v) for d, v in zip(dims, (key if isinstance(key, tuple) else (key,)))), g)
                        for key, g in valid.groupby(list(dims))
                    ]
                for cond, den in groups:
                    n, k, p, lo, hi = _cell_stats(den, num_col)
                    if n == 0:
                        continue
                    stability = ""
                    n_years = ""
                    stable = ""
                    if cond != "all":
                        pooled_edge = p - p_all
                        agree = total = 0
                        for year, ydf in den.groupby("year"):
                            if int(year) not in year_baseline or len(ydf) < MIN_N_YEAR:
                                continue
                            edge_y = float(ydf[num_col].mean()) - year_baseline[int(year)]
                            total += 1
                            if pooled_edge == 0 or edge_y * pooled_edge > 0:
                                agree += 1
                        if total > 0:
                            frac = agree / total
                            stability = round(frac, 3)
                            n_years = total
                            stable = int(frac >= STABILITY_THRESHOLD and total >= MIN_STABILITY_YEARS)
                    rows.append(
                        {
                            "table": table_name,
                            "trigger": trigger,
                            "condition": cond,
                            "n": n,
                            "k": k,
                            "p": round(p, 4),
                            "wilson_lo": round(lo, 4),
                            "wilson_hi": round(hi, 4),
                            "actionable": int(n >= MIN_N_ACTIONABLE),
                            "edge_vs_all": round(p - p_all, 4) if cond != "all" else "",
                            "stability_frac": stability,
                            "stability_years": n_years,
                            "stable": stable,
                        }
                    )
    return pd.DataFrame(rows)


def emit_reentry_timing(sessions_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    reentered = sessions_df[(sessions_df["reentry"] == 1) & (sessions_df["bars5_to_reentry"] != "")]
    for keys, grp in reentered.groupby(["trigger"]):
        trigger = keys[0] if isinstance(keys, tuple) else keys
        rows.append(_timing_row(trigger, "all", grp))
        for q, qgrp in grp[grp["or_width_q"].astype(str) != ""].groupby("or_width_q"):
            rows.append(_timing_row(trigger, "or_width_q=%s" % q, qgrp))
        no1r = grp[grp["hit_1r"] == 0]
        if not no1r.empty:
            rows.append(_timing_row(trigger, "failed_break_no1r", no1r))
    return pd.DataFrame(rows)


def _timing_row(trigger: str, condition: str, grp: pd.DataFrame) -> Dict[str, object]:
    vals = pd.to_numeric(grp["bars5_to_reentry"], errors="coerce").dropna()
    return {
        "trigger": trigger,
        "condition": condition,
        "n": len(vals),
        "bars5_p25": round(float(vals.quantile(0.25)), 1) if len(vals) else "",
        "bars5_median": round(float(vals.median()), 1) if len(vals) else "",
        "bars5_p75": round(float(vals.quantile(0.75)), 1) if len(vals) else "",
        "bars5_p90": round(float(vals.quantile(0.90)), 1) if len(vals) else "",
    }


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def write_market_summary(
    out_dir: Path,
    market: str,
    sessions_df: pd.DataFrame,
    tables_df: pd.DataFrame,
    timing_df: pd.DataFrame,
) -> None:
    lines: List[str] = []
    lines.append("# OR Profile Engine — %s" % market.upper())
    lines.append("")
    n_sessions = sessions_df["session_date"].nunique()
    lines.append(
        "Sessions walked: **%d** (%s → %s). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR)."
        % (n_sessions, sessions_df["session_date"].min(), sessions_df["session_date"].max())
    )
    lines.append("")

    lines.append("## Terminal day-label distribution")
    lines.append("")
    lines.append("| Label | touch N | touch % | close5 N | close5 % |")
    lines.append("|---|---:|---:|---:|---:|")
    label_counts = {
        trig: sessions_df[sessions_df["trigger"] == trig]["label"].value_counts() for trig in TRIGGERS
    }
    all_labels = sorted(set(sessions_df["label"]))
    for lbl in all_labels:
        tc = int(label_counts["touch"].get(lbl, 0))
        cc = int(label_counts["close5"].get(lbl, 0))
        tn = max(1, int(label_counts["touch"].sum()))
        cn = max(1, int(label_counts["close5"].sum()))
        lines.append("| %s | %d | %.1f%% | %d | %.1f%% |" % (lbl, tc, 100.0 * tc / tn, cc, 100.0 * cc / cn))
    lines.append("")

    lines.append("## Headline chains (condition = all)")
    lines.append("")
    lines.append("| Table | Trigger | N | p | Wilson 95% CI |")
    lines.append("|---|---|---:|---:|---|")
    headline = tables_df[tables_df["condition"] == "all"]
    for _, row in headline.iterrows():
        lines.append(
            "| %s | %s | %d | %.3f | [%.3f, %.3f] |"
            % (row["table"], row["trigger"], row["n"], row["p"], row["wilson_lo"], row["wilson_hi"])
        )
    lines.append("")

    lines.append("## Empirical failed-break cutoff (5m candles to re-entry)")
    lines.append("")
    lines.append("| Trigger | Condition | N | p25 | median | p75 | p90 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for _, row in timing_df.iterrows():
        lines.append(
            "| %s | %s | %d | %s | %s | %s | %s |"
            % (
                row["trigger"],
                row["condition"],
                row["n"],
                row["bars5_p25"],
                row["bars5_median"],
                row["bars5_p75"],
                row["bars5_p90"],
            )
        )
    lines.append("")

    stable = tables_df[
        (tables_df["stable"] == 1) & (tables_df["actionable"] == 1) & (tables_df["condition"] != "all")
    ].copy()
    lines.append("## Stable conditioned edges (sign holds in >=70%% of years, N>=%d)" % MIN_N_ACTIONABLE)
    lines.append("")
    if stable.empty:
        lines.append("None met the stability bar.")
    else:
        stable["abs_edge"] = stable["edge_vs_all"].abs()
        stable = stable.sort_values("abs_edge", ascending=False).head(40)
        lines.append("| Table | Trigger | Condition | N | p | edge vs all | stability |")
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for _, row in stable.iterrows():
            lines.append(
                "| %s | %s | %s | %d | %.3f | %+.3f | %.0f%% (%s yrs) |"
                % (
                    row["table"],
                    row["trigger"],
                    row["condition"],
                    row["n"],
                    row["p"],
                    row["edge_vs_all"],
                    100.0 * float(row["stability_frac"]),
                    row["stability_years"],
                )
            )
    lines.append("")
    (out_dir / "SUMMARY.md").write_text("\n".join(lines))


def write_pooled_summary(output_root: Path, asof: str, market_dirs: Dict[str, Path]) -> None:
    lines = ["# OR Profile Engine — pooled master (%s)" % asof, ""]
    lines.append(
        "Per-market tables live in `<market>/%s/`. Headline P(hit 1R | first break) and P(hit 2R | hit 1R) across markets:" % asof
    )
    lines.append("")
    lines.append("| Market | Trigger | N breaks | P(1R\\|break) | P(2R\\|1R) | P(reentry\\|break) | P(opp 1R\\|fakeout opp break) |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for market, mdir in sorted(market_dirs.items()):
        tables = pd.read_csv(mdir / "tables.csv")
        head = tables[tables["condition"] == "all"]
        for trigger in TRIGGERS:
            t = head[head["trigger"] == trigger]

            def _get(name: str, col: str = "p") -> str:
                row = t[t["table"] == name]
                return ("%.3f" % float(row.iloc[0][col])) if not row.empty else "-"

            nb = t[t["table"] == "hit1r_given_break"]
            n_breaks = int(nb.iloc[0]["n"]) if not nb.empty else 0
            lines.append(
                "| %s | %s | %d | %s | %s | %s | %s |"
                % (
                    market.upper(),
                    trigger,
                    n_breaks,
                    _get("hit1r_given_break"),
                    _get("hit2r_given_1r"),
                    _get("reentry_given_break"),
                    _get("opp_hit1r_given_opp_break"),
                )
            )
    lines.append("")
    (output_root / ("SUMMARY_%s.md" % asof)).write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="OR profile probability engine (batch, semi-annual refresh)")
    ap.add_argument("--markets", nargs="+", default=["nq", "mnq", "ym", "mym"])
    ap.add_argument("--asof", required=True, help="version tag for output dirs, e.g. 2026H2")
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = ap.parse_args()

    market_dirs: Dict[str, Path] = {}
    for market in args.markets:
        out = run_market(
            market,
            asof=args.asof,
            output_root=args.out,
            start=args.start,
            end=args.end,
            max_days=args.max_days,
        )
        if out is not None:
            market_dirs[market.lower()] = out
    if market_dirs:
        write_pooled_summary(args.out, args.asof, market_dirs)
    print("Done. Outputs under %s" % args.out, flush=True)


if __name__ == "__main__":
    main()
