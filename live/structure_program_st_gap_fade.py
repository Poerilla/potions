"""Overnight gap fade vs bias-change 1h candle range (analytic).

Rules
-----
Active **bias range** = high/low of the 1h candle that printed the latest 15m
program flip. Range persists until the next flip.

Each RTH morning, if the session **gaps away** from that range
(open > range high → short fade; open < range low → long fade),
**and** yesterday's last 1h candle does **not** overlap today's first 1h
candle in price, **and** the gap is at least **1/5** of the bias-candle range:

  - Wait for the **first 1h candle** of the day to close.
  - Risk R = that candle's range (high − low). Entry limit at its midpoint.
  - Size 3ct.
  - Scale: 1 @ +50pts · 1 @ near bias-range boundary · 1 runner @ ~20R.
  - After boundary fill → runner stop to BE.
  - First two contracts flatten at EOD; runner may span days (BE / 20R / stop).
  - Re-entry: same mid limit re-armed only if a later 1h close prints on the
    gap side of the midpoint (away from the range).
  - If a **new** bias range forms during the day, keep fading toward the
    **original** gap / range for that overnight play.
  - If the gap morning itself prints a new bias candle, that candle may define
    the range used for the setup.

Usage:
  python -m live.structure_program_st_gap_fade --start 2020-01-01
  python -m live.structure_program_st_gap_fade --charts-only  # after trades exist
"""

from __future__ import annotations

import argparse
import random
from dataclasses import asdict, dataclass, field
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .structure_program_st_study import (
    FEE_PER_CONTRACT_RT,
    POINT_VALUE,
    StructureProgramEngine,
    confirm_swings,
    rth_slice,
    to_15m,
    try_form_structures,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "structure_program_st" / "gap_fade"
NY = "America/New_York"
EOD = time(15, 59)
QTY = 3
SCALE_PTS = 50.0
RUNNER_R = 20.0
MIN_GAP_FRAC = 0.2  # gap ≥ 1/5 of bias-candle range
N_CHART_EACH = 50


def _candles_overlap(h1: float, l1: float, h2: float, l2: float) -> bool:
    """True if price ranges intersect (inclusive)."""
    return not (h1 < l2 or h2 < l1)


def _gap_size(prev_h: float, prev_l: float, cur_h: float, cur_l: float) -> float:
    """Absolute empty space between two non-overlapping candles; 0 if overlap."""
    if _candles_overlap(prev_h, prev_l, cur_h, cur_l):
        return 0.0
    if cur_l > prev_h:
        return cur_l - prev_h  # gap up
    if prev_l > cur_h:
        return prev_l - cur_h  # gap down
    return 0.0


def _valid_overnight_gap(
    *,
    prev_h: float,
    prev_l: float,
    cur_h: float,
    cur_l: float,
    cur_o: float,
    bias_high: float,
    bias_low: float,
) -> Optional[str]:
    """Return 'above' | 'below' if gap qualifies, else None.

    Requires: (1) yesterday last 1h and today first 1h do not overlap in price,
    (2) gap size ≥ 1/5 of bias-candle range, (3) open/candle away from bias range.
    """
    bias_rng = float(bias_high) - float(bias_low)
    if bias_rng < 1.0:
        return None
    if _candles_overlap(prev_h, prev_l, cur_h, cur_l):
        return None
    gap = _gap_size(prev_h, prev_l, cur_h, cur_l)
    if gap < MIN_GAP_FRAC * bias_rng:
        return None
    # direction vs bias range
    gap_above = cur_o > bias_high or cur_l > bias_high
    gap_below = cur_o < bias_low or cur_h < bias_low
    if gap_above and cur_l > prev_h:
        return "above"
    if gap_below and cur_h < prev_l:
        return "below"
    return None


@dataclass
class BiasRange:
    flip_ts: pd.Timestamp
    program: str
    high: float
    low: float
    bar_ts: pd.Timestamp


@dataclass
class Position:
    trade_id: int
    side: str  # long | short
    entry: float
    entry_ts: pd.Timestamp
    stop: float
    risk_pts: float
    mid: float
    range_high: float
    range_low: float
    boundary: float  # near edge of bias range (fade target)
    qty_open: float = float(QTY)
    qty_eod_bucket: float = 2.0  # first two contracts — EOD
    qty_runner: float = 1.0
    hit_50: bool = False
    hit_boundary: bool = False
    be_armed: bool = False
    realized_usd: float = 0.0
    exit_legs: List[str] = field(default_factory=list)
    signal_day: date = field(default_factory=date.today)
    gap_side: str = ""  # above | below
    is_reentry: bool = False


@dataclass
class TradeRow:
    trade_id: int
    side: str
    gap_side: str
    is_reentry: bool
    signal_day: str
    entry_ts: pd.Timestamp
    entry: float
    mid: float
    risk_pts: float
    stop0: float
    range_high: float
    range_low: float
    boundary: float
    exit_ts: pd.Timestamp
    exit: float
    exit_reason: str
    pnl_usd: float
    pnl_pts: float
    qty: float
    hit_50: bool
    hit_boundary: bool
    be_armed: bool
    runner_held: bool
    mfe_pts: float
    mae_pts: float


def to_1h(rth_1m: pd.DataFrame) -> pd.DataFrame:
    if rth_1m is None or rth_1m.empty:
        return pd.DataFrame()
    ohlc = rth_1m.resample("1h", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum") if "volume" in rth_1m.columns else ("close", "count"),
    )
    return ohlc.dropna(subset=["open", "high", "low", "close"])


def _bias_candle_1h(day_1h: pd.DataFrame, flip_ts: pd.Timestamp) -> Optional[Tuple[float, float, pd.Timestamp]]:
    ts = pd.Timestamp(flip_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    else:
        ts = ts.tz_convert(NY)
    if day_1h is None or day_1h.empty:
        return None
    for bt, row in day_1h.iterrows():
        if bt <= ts < bt + pd.Timedelta(hours=1):
            return float(row["high"]), float(row["low"]), bt
    deltas = [(abs((bt - ts).total_seconds()), bt, row) for bt, row in day_1h.iterrows()]
    if not deltas:
        return None
    _, bt, row = min(deltas, key=lambda t: t[0])
    return float(row["high"]), float(row["low"]), bt


def _realize(pos: Position, qty: float, px: float, tag: str) -> None:
    qty = min(qty, pos.qty_open)
    if qty <= 0:
        return
    sign = 1.0 if pos.side == "long" else -1.0
    pts = sign * (px - pos.entry)
    pos.realized_usd += pts * qty * POINT_VALUE - FEE_PER_CONTRACT_RT * qty
    pos.qty_open -= qty
    pos.exit_legs.append(tag)


def _finalize(pos: Position, ts: pd.Timestamp, px: float, reason: str, mfe: float, mae: float) -> TradeRow:
    if pos.qty_open > 0:
        _realize(pos, pos.qty_open, px, reason)
    legs = "+".join(pos.exit_legs) if pos.exit_legs else reason
    pnl = pos.realized_usd
    return TradeRow(
        trade_id=pos.trade_id,
        side=pos.side,
        gap_side=pos.gap_side,
        is_reentry=pos.is_reentry,
        signal_day=str(pos.signal_day),
        entry_ts=pos.entry_ts,
        entry=pos.entry,
        mid=pos.mid,
        risk_pts=pos.risk_pts,
        stop0=pos.stop if not pos.be_armed else pos.entry,
        range_high=pos.range_high,
        range_low=pos.range_low,
        boundary=pos.boundary,
        exit_ts=ts,
        exit=px,
        exit_reason=legs,
        pnl_usd=pnl,
        pnl_pts=pnl / POINT_VALUE / QTY,
        qty=float(QTY),
        hit_50=pos.hit_50,
        hit_boundary=pos.hit_boundary,
        be_armed=pos.be_armed,
        runner_held=pos.hit_boundary and ("runner" in legs or "eod" not in legs.split("+")[-1:]),
        mfe_pts=mfe,
        mae_pts=mae,
    )


def run_study(
    start: Optional[date] = None,
    end: Optional[date] = None,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
) -> pd.DataFrame:
    if gby is None:
        print("Loading NQ 1m…", flush=True)
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    eng = StructureProgramEngine()
    active_range: Optional[BiasRange] = None
    trades: List[TradeRow] = []
    pos: Optional[Position] = None
    next_id = 1
    mfe = mae = 0.0

    # pending day setup after first hour
    pending_limit: Optional[dict] = None  # mid, side, R, range, boundary, gap_side, day
    reentry_armed = False

    bars1h_by_day: Dict[date, pd.DataFrame] = {}
    prev_last_1h: Optional[Tuple[float, float]] = None  # (high, low)

    print("Running gap_fade over %d days…" % len(days), flush=True)
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        b15 = to_15m(rth)
        b1h = to_1h(rth)
        if b1h.empty:
            continue
        bars1h_by_day[d] = b1h
        day_prev_hl = prev_last_1h  # freeze for this morning's gap check

        # --- overnight range frozen before today's flips ---
        overnight_range = active_range

        # --- walk 15m for bias flips; capture 1h candle H/L ---
        day_swings = confirm_swings(b15)
        by_confirm: Dict[pd.Timestamp, list] = {}
        for sw in day_swings:
            by_confirm.setdefault(sw[0], []).append(sw)

        day_flips: List[BiasRange] = []
        for ts, row in b15.iterrows():
            for sw in by_confirm.get(ts, []):
                if eng.swings and eng.swings[-1][1] == sw[1]:
                    prev = eng.swings[-1]
                    if sw[1] == "H" and sw[2] >= prev[2]:
                        eng.swings[-1] = sw
                    elif sw[1] == "L" and sw[2] <= prev[2]:
                        eng.swings[-1] = sw
                    else:
                        continue
                else:
                    eng.swings.append(sw)
                for st in try_form_structures(eng.swings):
                    sig = (st.kind, round(st.key, 4), round(st.p4, 4), str(st.formed_ts))
                    if sig in eng._seen_structure_keys:
                        continue
                    eng._seen_structure_keys.add(sig)
                    if st.kind == "bull":
                        eng.bull.append(st)
                    else:
                        eng.bear.append(st)
            prev_prog = eng.program
            eng._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
            if eng.program in {"buy", "sell"} and eng.program != prev_prog and eng.ready:
                candle = _bias_candle_1h(b1h, ts)
                if candle is not None:
                    hi, lo, bt = candle
                    br = BiasRange(flip_ts=ts, program=eng.program, high=hi, low=lo, bar_ts=bt)
                    day_flips.append(br)
                    active_range = br

        first = b1h.iloc[0]
        first_ts = b1h.index[0]
        first_o = float(first["open"])
        first_h = float(first["high"])
        first_l = float(first["low"])
        first_c = float(first["close"])

        # Gap play range: overnight bias H/L; if gap morning *is* a new bias candle, use it
        play_range = overnight_range
        for br in day_flips:
            if br.bar_ts == first_ts:
                play_range = br
                break
        # New bias later in the day must NOT replace play_range (stick to old gap)

        # Manage open runner / position on today's 1h bars
        def manage_bar(ts, o, h, l, c, is_first: bool) -> None:
            nonlocal pos, mfe, mae, trades, pending_limit, reentry_armed
            if pos is None:
                return
            sign = 1.0 if pos.side == "long" else -1.0
            # MFE/MAE
            if pos.side == "long":
                mfe = max(mfe, h - pos.entry)
                mae = max(mae, pos.entry - l)
            else:
                mfe = max(mfe, pos.entry - l)
                mae = max(mae, h - pos.entry)

            # stop
            hit_stop = (pos.side == "long" and l <= pos.stop) or (
                pos.side == "short" and h >= pos.stop
            )
            if hit_stop:
                tag = "be_stop" if pos.be_armed else "risk_stop"
                trades.append(_finalize(pos, ts, float(pos.stop), tag, mfe, mae))
                pos = None
                mfe = mae = 0.0
                return

            # scale +50
            if not pos.hit_50 and pos.qty_open > 0:
                tp = pos.entry + sign * SCALE_PTS
                hit = (pos.side == "long" and h >= tp) or (pos.side == "short" and l <= tp)
                if hit:
                    _realize(pos, 1.0, tp, "scale_50")
                    pos.hit_50 = True
                    pos.qty_eod_bucket = max(0.0, pos.qty_eod_bucket - 1.0)

            # scale at bias-range boundary
            if pos is not None and not pos.hit_boundary and pos.qty_open > 0:
                b = pos.boundary
                hit = (pos.side == "long" and h >= b) or (pos.side == "short" and l <= b)
                if hit:
                    _realize(pos, 1.0, b, "boundary")
                    pos.hit_boundary = True
                    pos.qty_eod_bucket = max(0.0, pos.qty_eod_bucket - 1.0)
                    # runner → BE
                    pos.stop = pos.entry
                    pos.be_armed = True

            # runner 20R
            if pos is not None and pos.hit_boundary and pos.qty_open > 0:
                tpr = pos.entry + sign * RUNNER_R * pos.risk_pts
                hit = (pos.side == "long" and h >= tpr) or (pos.side == "short" and l <= tpr)
                if hit:
                    trades.append(_finalize(pos, ts, tpr, "runner_20R", mfe, mae))
                    pos = None
                    mfe = mae = 0.0
                    return

            # EOD: before boundary, flatten everything; after boundary, keep 1 runner
            if pos is not None and ts.time() >= EOD:
                if not pos.hit_boundary:
                    trades.append(_finalize(pos, ts, c, "eod", mfe, mae))
                    pos = None
                    mfe = mae = 0.0
                    return
                # keep at most 1 runner
                if pos.qty_open > 1.0:
                    _realize(pos, pos.qty_open - 1.0, c, "eod")
                    pos.qty_eod_bucket = 0.0
                    pos.qty_runner = 1.0
                if pos.qty_open <= 0:
                    trades.append(_finalize(pos, ts, c, "eod", mfe, mae))
                    pos = None
                    mfe = mae = 0.0
                    return

        # Process bars: first hour closes → arm limit; later bars manage + fill
        for bi, (ts, row) in enumerate(b1h.iterrows()):
            o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
            is_first = bi == 0

            # manage existing position first
            manage_bar(ts, o, h, l, c, is_first)
            if pos is not None and pos.qty_open <= 0:
                pos = None

            # After first hour close: arm gap-fade limit if gapped away
            if is_first and play_range is not None and pos is None and day_prev_hl is not None:
                rh, rl = play_range.high, play_range.low
                prev_h, prev_l = day_prev_hl
                gap_side = _valid_overnight_gap(
                    prev_h=prev_h,
                    prev_l=prev_l,
                    cur_h=first_h,
                    cur_l=first_l,
                    cur_o=first_o,
                    bias_high=rh,
                    bias_low=rl,
                )
                if gap_side is not None:
                    R = first_h - first_l
                    if R >= 1.0:
                        mid = 0.5 * (first_h + first_l)
                        if gap_side == "below":
                            side = "long"
                            boundary = rl
                            stop = mid - R
                        else:
                            side = "short"
                            boundary = rh
                            stop = mid + R
                        pending_limit = {
                            "day": d,
                            "side": side,
                            "mid": mid,
                            "R": R,
                            "stop": stop,
                            "range_high": rh,
                            "range_low": rl,
                            "boundary": boundary,
                            "gap_side": gap_side,
                            "first_ts": first_ts,
                            "armed_after": ts,
                            "is_reentry": False,
                            "gap_pts": _gap_size(prev_h, prev_l, first_h, first_l),
                        }
                        reentry_armed = False

            # Fill pending limit on subsequent bars (touch mid)
            if pending_limit is not None and pos is None and not is_first:
                mid = float(pending_limit["mid"])
                side = pending_limit["side"]
                touched = (side == "long" and l <= mid) or (side == "short" and h >= mid)
                if touched and ts > pending_limit["armed_after"]:
                    fill = mid
                    pos = Position(
                        trade_id=next_id,
                        side=side,
                        entry=fill,
                        entry_ts=ts,
                        stop=float(pending_limit["stop"]),
                        risk_pts=float(pending_limit["R"]),
                        mid=mid,
                        range_high=float(pending_limit["range_high"]),
                        range_low=float(pending_limit["range_low"]),
                        boundary=float(pending_limit["boundary"]),
                        signal_day=d,
                        gap_side=str(pending_limit["gap_side"]),
                        is_reentry=bool(pending_limit.get("is_reentry")),
                    )
                    next_id += 1
                    mfe = mae = 0.0
                    pending_limit = None
                    reentry_armed = False
                    # same-bar manage after fill
                    manage_bar(ts, o, h, l, c, False)

            # Re-entry arm: candle closes on gap side of mid while flat / no pending
            if (
                play_range is not None
                and pos is None
                and pending_limit is None
                and not is_first
                and bi >= 1
                and day_prev_hl is not None
            ):
                rh, rl = play_range.high, play_range.low
                prev_h, prev_l = day_prev_hl
                gap_side0 = _valid_overnight_gap(
                    prev_h=prev_h,
                    prev_l=prev_l,
                    cur_h=first_h,
                    cur_l=first_l,
                    cur_o=first_o,
                    bias_high=rh,
                    bias_low=rl,
                )
                R0 = first_h - first_l
                mid0 = 0.5 * (first_h + first_l)
                if gap_side0 is not None and R0 >= 1.0:
                    away = (gap_side0 == "below" and c < mid0) or (
                        gap_side0 == "above" and c > mid0
                    )
                    if away:
                        if gap_side0 == "below":
                            side = "long"
                            boundary = rl
                            stop = mid0 - R0
                        else:
                            side = "short"
                            boundary = rh
                            stop = mid0 + R0
                        pending_limit = {
                            "day": d,
                            "side": side,
                            "mid": mid0,
                            "R": R0,
                            "stop": stop,
                            "range_high": rh,
                            "range_low": rl,
                            "boundary": boundary,
                            "gap_side": gap_side0,
                            "first_ts": first_ts,
                            "armed_after": ts,
                            "is_reentry": True,
                            "gap_pts": _gap_size(prev_h, prev_l, first_h, first_l),
                        }
                        reentry_armed = True

            # last bar safety: flatten day book if somehow still open without boundary
            if bi == len(b1h) - 1 and pos is not None and not pos.hit_boundary:
                trades.append(_finalize(pos, ts, c, "eod", mfe, mae))
                pos = None
                mfe = mae = 0.0
            elif bi == len(b1h) - 1 and pos is not None and pos.hit_boundary and pos.qty_open > 1:
                _realize(pos, pos.qty_open - 1.0, c, "eod")
                pos.qty_runner = 1.0

        # clear day pending at session end (don't carry unfilled limit overnight)
        if pending_limit is not None and pending_limit.get("day") == d:
            pending_limit = None

        # roll yesterday-last for next session's gap check
        last = b1h.iloc[-1]
        prev_last_1h = (float(last["high"]), float(last["low"]))

        if di % 250 == 0:
            print("  %d/%d days | trades %d | open=%s" % (di, len(days), len(trades), pos is not None), flush=True)

    # flatten residual runner at end
    if pos is not None and pos.qty_open > 0:
        last_day = max(bars1h_by_day)
        last = bars1h_by_day[last_day]
        trades.append(
            _finalize(pos, last.index[-1], float(last.iloc[-1]["close"]), "eod_residual", mfe, mae)
        )

    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(t) for t in trades])
    if not df.empty:
        df.to_csv(OUT / "trades.csv", index=False)
    _write_summary(df)
    # stash 1h for charts
    meta = {"n_days": len(days), "n_trades": len(df)}
    pd.DataFrame([meta]).to_csv(OUT / "meta.csv", index=False)
    print("Wrote %d trades → %s" % (len(df), OUT), flush=True)
    return df


def _write_summary(df: pd.DataFrame) -> None:
    lines = [
        "# Structure overnight gap fade",
        "",
        "Fade gaps away from the active **bias-change 1h candle** H/L range.",
        "Gap filters: yesterday-last vs today-first 1h **no price overlap**, and",
        "gap size ≥ **1/5** of the bias-candle range.",
        "3ct: 1@+50 · 1@range boundary→BE · 1 runner@20R; first two EOD-only.",
        "Re-entry at first-hour midpoint if price closes further away.",
        "",
    ]
    if df is None or df.empty:
        lines.append("No trades.")
        (OUT / "SUMMARY.md").write_text("\n".join(lines))
        return
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]
    gp = float(wins.pnl_usd.sum()) if len(wins) else 0.0
    gl = float(-losses.pnl_usd.sum()) if len(losses) else 1e-9
    pf = gp / gl if gl > 0 else float("inf")
    lines += [
        "## Results",
        "",
        "| metric | value |",
        "|---|---|",
        "| trades | %d |" % len(df),
        "| net $ | %.0f |" % df.pnl_usd.sum(),
        "| win%% | %.1f |" % (100.0 * (df.pnl_usd > 0).mean()),
        "| PF | %.3f |" % pf,
        "| avg $/trade | %.1f |" % df.pnl_usd.mean(),
        "| long / short | %d / %d |"
        % (int((df.side == "long").sum()), int((df.side == "short").sum())),
        "| reentries | %d |" % int(df.is_reentry.sum()),
        "| hit_50 / boundary | %d / %d |" % (int(df.hit_50.sum()), int(df.hit_boundary.sum())),
        "",
        "### By exit reason",
        "",
        df.groupby("exit_reason").pnl_usd.agg(["count", "sum", "mean"]).to_markdown(),
        "",
        "### By year",
        "",
    ]
    yr = df.copy()
    yr["year"] = pd.to_datetime(yr["entry_ts"], utc=True).dt.tz_convert(NY).dt.year
    lines.append(yr.groupby("year").pnl_usd.agg(["count", "sum", "mean"]).to_markdown())
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


def chart_trades(
    gby: Dict[date, pd.DataFrame],
    df: pd.DataFrame,
    n_each: int = N_CHART_EACH,
    seed: int = 42,
) -> None:
    if df is None or df.empty:
        print("No trades to chart")
        return
    rng = random.Random(seed)
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]

    def pick(sub: pd.DataFrame, k: int) -> pd.DataFrame:
        if sub.empty:
            return sub
        idxs = sub.index.tolist()
        if len(idxs) <= k:
            return sub.copy()
        step = max(1, len(idxs) // k)
        chosen = idxs[::step][:k]
        if len(chosen) < k:
            rest = [i for i in idxs if i not in set(chosen)]
            chosen.extend(rng.sample(rest, min(k - len(chosen), len(rest))))
        return sub.loc[chosen[:k]].copy()

    sample = pd.concat([pick(wins, n_each), pick(losses, n_each)], ignore_index=False)
    sample = sample.sort_values("entry_ts")
    win_dir = OUT / "charts" / "winners"
    loss_dir = OUT / "charts" / "losers"
    for d in (win_dir, loss_dir):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.png"):
            old.unlink()

    print("Charting %d trades…" % len(sample), flush=True)
    rows = []
    wi = li = 0
    for _, t in sample.iterrows():
        is_win = float(t.pnl_usd) > 0
        if is_win:
            wi += 1
            cid = wi
            out_dir = win_dir
        else:
            li += 1
            cid = li
            out_dir = loss_dir
        ok = _plot_one(gby, t, out_dir, cid)
        if ok:
            rows.append(
                {
                    "chart_id": cid,
                    "result": "win" if is_win else "loss",
                    "trade_id": t.trade_id,
                    "pnl_usd": t.pnl_usd,
                    "side": t.side,
                    "entry_ts": t.entry_ts,
                    "exit_reason": t.exit_reason,
                }
            )
    pd.DataFrame(rows).to_csv(OUT / "charts" / "charted.csv", index=False)
    (OUT / "charts" / "README.md").write_text(
        "\n".join(
            [
                "# Gap-fade trade charts",
                "",
                "%d winners + %d losers (1h context, bias range + first-hour mid/R)."
                % (wi, li),
                "",
                "- Blue/pink band = bias candle H/L range",
                "- Orange mid = first-hour midpoint (entry limit)",
                "- Markers = entry / exit",
                "",
            ]
        )
        + "\n"
    )
    print("Charts → %s" % (OUT / "charts"), flush=True)


def _plot_one(gby: Dict[date, pd.DataFrame], t: pd.Series, out_dir: Path, cid: int) -> bool:
    entry_ts = pd.Timestamp(t.entry_ts)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize(NY)
    else:
        entry_ts = entry_ts.tz_convert(NY)
    exit_ts = pd.Timestamp(t.exit_ts)
    if exit_ts.tzinfo is None:
        exit_ts = exit_ts.tz_localize(NY)
    else:
        exit_ts = exit_ts.tz_convert(NY)

    d0 = entry_ts.date()
    all_days = sorted(gby)
    # show prior day + entry day + up to +3 sessions (runner)
    if d0 not in all_days:
        near = [d for d in all_days if abs((d - d0).days) < 5]
        if not near:
            return False
        d0 = min(near, key=lambda x: abs((x - d0).days))
    i0 = all_days.index(d0)
    start_i = max(0, i0 - 1)
    end_i = min(len(all_days) - 1, all_days.index(exit_ts.date()) if exit_ts.date() in all_days else i0 + 2)
    end_i = max(end_i, min(len(all_days) - 1, i0 + 2))
    sessions = all_days[start_i : end_i + 1]
    frames = []
    for d in sessions:
        rth = rth_slice(gby[d])
        if rth.empty:
            continue
        h = to_1h(rth)
        if not h.empty:
            frames.append(h)
    if not frames:
        return False
    plot = pd.concat(frames).sort_index()
    plot = plot[~plot.index.duplicated(keep="last")]
    if len(plot) < 5:
        return False

    fig, ax = plt.subplots(figsize=(16, 8))
    x = np.arange(len(plot))
    o = plot["open"].to_numpy()
    h = plot["high"].to_numpy()
    l = plot["low"].to_numpy()
    c = plot["close"].to_numpy()
    up = c >= o
    ax.vlines(x, l, h, color="#888", lw=0.8, zorder=1)
    ax.vlines(x[up], o[up], c[up], color="#1a9850", lw=2.0, zorder=2)
    ax.vlines(x[~up], c[~up], o[~up], color="#d73027", lw=2.0, zorder=2)

    rh, rl = float(t.range_high), float(t.range_low)
    ax.axhspan(rl, rh, color="#90caf9", alpha=0.18, zorder=0, label="bias candle range")
    ax.axhline(rh, color="#1565c0", lw=1.2, ls="--")
    ax.axhline(rl, color="#1565c0", lw=1.2, ls="--")
    ax.axhline(float(t.mid), color="#ef6c00", lw=1.6, label="first-hour mid %.1f" % float(t.mid))
    ax.axhline(float(t.boundary), color="#6a1b9a", lw=1.4, ls=":", label="boundary %.1f" % float(t.boundary))
    ax.axhline(float(t.entry) + (SCALE_PTS if t.side == "long" else -SCALE_PTS), color="#2e7d32", lw=0.9, ls="--", alpha=0.7, label="+50")

    def xi(ts):
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize(NY)
        else:
            ts = ts.tz_convert(NY)
        for i, bt in enumerate(plot.index):
            if bt <= ts < bt + pd.Timedelta(hours=1):
                return i
        deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(plot.index)]
        return min(deltas)[1] if deltas else None

    ei = xi(entry_ts)
    xi_ = xi(exit_ts)
    color = "#1a9850" if float(t.pnl_usd) > 0 else "#d73027"
    if ei is not None:
        ax.scatter([ei], [float(t.entry)], marker="^" if t.side == "long" else "v", s=160, color=color, edgecolors="white", zorder=8, label="entry")
    if xi_ is not None:
        ax.scatter([xi_], [float(t.exit)], marker="X", s=140, color=color, edgecolors="white", zorder=8, label="exit")

    for d in sessions[1:]:
        for i, bt in enumerate(plot.index):
            if bt.date() == d:
                ax.axvline(i, color="#bbb", lw=0.7, ls="--", zorder=0)
                break

    tag = "WIN" if float(t.pnl_usd) > 0 else "LOSS"
    ax.set_title(
        "NQ 1h gap-fade #%d %s %s $%+.0f | %s → %s | %s%s"
        % (
            cid,
            str(t.side).upper(),
            tag,
            float(t.pnl_usd),
            entry_ts.strftime("%Y-%m-%d %H:%M"),
            exit_ts.strftime("%m-%d %H:%M"),
            t.exit_reason,
            " · reentry" if bool(t.is_reentry) else "",
        ),
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=7)
    ax.set_xlim(-1, len(plot))
    step = max(1, len(plot) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([plot.index[i].strftime("%m-%d %H:%M") for i in x[::step]], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fname = "%03d_%s_%s_pnl%+.0f.png" % (
        cid,
        entry_ts.strftime("%Y-%m-%d"),
        t.side,
        float(t.pnl_usd),
    )
    fig.savefig(out_dir / fname, dpi=110)
    plt.close(fig)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--charts-only", action="store_true")
    ap.add_argument("--n-charts", type=int, default=N_CHART_EACH)
    args = ap.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")

    if args.charts_only:
        df = pd.read_csv(OUT / "trades.csv")
    else:
        df = run_study(start=start, end=end, gby=gby)

    if df is not None and not df.empty:
        chart_trades(gby, df, n_each=args.n_charts)


if __name__ == "__main__":
    main()
