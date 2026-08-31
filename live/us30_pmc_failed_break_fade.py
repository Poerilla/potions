"""US30 PMC failed-break / liquidity-sweep fade — Phase 1 taxonomy + Phase 2 controls.

Frozen v1 (see ``live/state/us30_pmc_failed_break_fade/RESEARCH_PLAN.md``):

  Pre-known PMC → sweep (≥0.10×ATR_20_5m) → 5m close back inside (≤60m)
  → next 5m confirmation → next 1m open fade → structural stop ±1 tick
  → scale-out 50%@1R / 25%@2R / 25%@4R (4 lots: 2/1/1). No add.

Controls: naive fade | reclaim-only | v1 confirmed (primary).

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.us30_pmc_failed_break_fade --email
  python -m live.us30_pmc_failed_break_fade --email --smoke
  python -m live.us30_pmc_failed_break_fade --email --phase taxonomy
  python -m live.us30_pmc_failed_break_fade --email --phase replay
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_prev_month_close_map

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "us30_pmc_failed_break_fade"
ONE_M = REPO / "fx" / "us30_1m.csv"
DAILY = REPO / "fx" / "us30_daily.csv"
SYM = "US30"
NY = "America/New_York"
DSR = "TRL-2026-00187"

TICK = 0.1
POINT_VALUE = 1.0
FEE_PER_UNIT = 1.50
SLIPPAGE_TICKS = 1
MIN_PENETRATION_ATR = 0.10
MAX_FAILURE_MINUTES = 60
CONFIRMATION_BARS = 1
STOP_BUFFER_TICKS = 1
TP_LADDER = (1.0, 2.0, 4.0)
TP_QTY = (2, 1, 1)  # 50/25/25 of 4 lots
ENTRY_QTY = sum(TP_QTY)
SESSION_OPEN = time(9, 30)
SESSION_CUTOFF = time(15, 0)
EOD_FLATTEN = time(15, 55)
SESSION_END = time(16, 0)
MIN_SESSION_BARS = 300  # exclude early closes / holidays
ATR_LEN = 20

CONTROLS = ("naive", "reclaim_only", "confirmed")


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


def _us_holidays() -> set:
    try:
        import pandas.tseries.holiday as hol

        cal = hol.USFederalHolidayCalendar()
        days = cal.holidays(start="2016-01-01", end="2027-12-31")
        return {pd.Timestamp(d).date() for d in days}
    except Exception:
        return set()


def _is_nfp_friday(d: date) -> bool:
    """First Friday of the month (NFP proxy)."""
    if d.weekday() != 4:
        return False
    return 1 <= d.day <= 7


def _localize(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize(NY)
    return ts.tz_convert(NY)


def _ny_time(ts: pd.Timestamp) -> time:
    return _localize(ts).time()


def _rth_slice(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(NY)
    else:
        out.index = out.index.tz_convert(NY)
    mask = (out.index.time >= SESSION_OPEN) & (out.index.time < SESSION_END)
    return out.loc[mask].sort_index()


def _is_early_close(rth: pd.DataFrame) -> bool:
    if rth is None or rth.empty:
        return True
    if len(rth) < MIN_SESSION_BARS:
        return True
    last_t = _ny_time(rth.index[-1])
    return last_t < time(15, 45)


# ---------------------------------------------------------------------------
# Bars / ATR
# ---------------------------------------------------------------------------


def resample_5m(one_m: pd.DataFrame) -> pd.DataFrame:
    return (
        one_m.resample("5min", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def atr_wilder(df: pd.DataFrame, length: int = ATR_LEN) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


# ---------------------------------------------------------------------------
# Sweep / fade geometry
# ---------------------------------------------------------------------------


@dataclass
class SweepEvent:
    session: date
    side: str  # UPSIDE_SWEEP | DOWNSIDE_SWEEP
    sweep_ts: pd.Timestamp
    sweep_extreme: float
    pmc: float
    atr_5m: float
    penetration: float
    penetration_atr: float


@dataclass
class FadeCandidate:
    control: str
    side: str  # LONG | SHORT
    session: date
    pmc: float
    sweep_ts: pd.Timestamp
    sweep_extreme: float
    failure_ts: Optional[pd.Timestamp]
    confirm_ts: Optional[pd.Timestamp]
    entry_ts: pd.Timestamp
    entry_price: float
    stop_price: float
    risk_r: float
    tp1: float
    tp2: float
    runner: float
    atr_5m: float
    penetration_atr: float


@dataclass
class OpenFade:
    trade_id: int
    control: str
    side: str
    session: date
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    risk_r: float
    targets: List[Tuple[float, int, str]]  # (price, qty, label)
    units_remaining: int
    filled: Dict[str, int] = field(default_factory=dict)
    mfe: float = 0.0
    mae: float = 0.0
    pmc: float = 0.0
    sweep_ts: str = ""
    failure_ts: str = ""
    confirm_ts: str = ""


def _adverse_entry(side: str, open_px: float) -> float:
    slip = SLIPPAGE_TICKS * TICK
    if side == "LONG":
        return open_px + slip
    return open_px - slip


def _adverse_stop(side: str, stop: float) -> float:
    slip = SLIPPAGE_TICKS * TICK
    if side == "LONG":
        return stop - slip
    return stop + slip


@dataclass
class AtrIndex:
    """Completed 5m ATR lookup: bar at ``times[i]`` finishes at times[i]+5m."""

    times_ns: np.ndarray  # int64 ns of 5m bar start
    values: np.ndarray

    @classmethod
    def from_series(cls, atr: pd.Series) -> "AtrIndex":
        idx = atr.index
        if idx.tz is None:
            idx = idx.tz_localize(NY)
        else:
            idx = idx.tz_convert(NY)
        return cls(
            times_ns=idx.asi8.astype(np.int64),
            values=atr.to_numpy(dtype=float),
        )

    def at_ts_ns(self, ts_ns: int) -> float:
        # most recent 5m bar with start + 5m <= ts  ⇒  start <= ts - 5m
        cutoff = int(ts_ns) - 5 * 60 * 1_000_000_000
        i = int(np.searchsorted(self.times_ns, cutoff, side="right") - 1)
        if i < 0:
            return float("nan")
        v = float(self.values[i])
        return v if np.isfinite(v) and v > 0 else float("nan")


def _ts_ns(ts: pd.Timestamp) -> int:
    return int(_localize(ts).value)


def _all_sweeps_for_taxonomy(
    rth_1m: pd.DataFrame,
    pmc: float,
    atr_ix: AtrIndex,
) -> List[SweepEvent]:
    """First qualifying sweep per side in session (numpy hot path)."""
    out: List[SweepEvent] = []
    if rth_1m is None or rth_1m.empty:
        return out
    idx = rth_1m.index
    if idx.tz is None:
        idx = idx.tz_localize(NY)
    else:
        idx = idx.tz_convert(NY)
    ts_ns = idx.asi8.astype(np.int64)
    highs = rth_1m["high"].to_numpy(dtype=float)
    lows = rth_1m["low"].to_numpy(dtype=float)
    seen = set()
    session_day = pd.Timestamp(idx[0]).tz_convert(NY).date()
    for i in range(len(ts_ns)):
        atr = atr_ix.at_ts_ns(int(ts_ns[i]))
        if not np.isfinite(atr):
            continue
        min_pen = MIN_PENETRATION_ATR * atr
        hi = float(highs[i])
        lo = float(lows[i])
        up_pen = hi - pmc
        dn_pen = pmc - lo
        ts = pd.Timestamp(ts_ns[i], tz="UTC").tz_convert(NY)
        if "UPSIDE_SWEEP" not in seen and up_pen >= min_pen:
            seen.add("UPSIDE_SWEEP")
            out.append(
                SweepEvent(
                    session=session_day,
                    side="UPSIDE_SWEEP",
                    sweep_ts=ts,
                    sweep_extreme=hi,
                    pmc=pmc,
                    atr_5m=atr,
                    penetration=up_pen,
                    penetration_atr=up_pen / atr,
                )
            )
        if "DOWNSIDE_SWEEP" not in seen and dn_pen >= min_pen:
            seen.add("DOWNSIDE_SWEEP")
            out.append(
                SweepEvent(
                    session=session_day,
                    side="DOWNSIDE_SWEEP",
                    sweep_ts=ts,
                    sweep_extreme=lo,
                    pmc=pmc,
                    atr_5m=atr,
                    penetration=dn_pen,
                    penetration_atr=dn_pen / atr,
                )
            )
        if len(seen) >= 2:
            break
    return out


def _find_first_sweep(
    rth_1m: pd.DataFrame,
    pmc: float,
    atr_ix: AtrIndex,
    *,
    until: Optional[time] = None,
) -> Optional[SweepEvent]:
    sweeps = _all_sweeps_for_taxonomy(rth_1m, pmc, atr_ix)
    if until is not None:
        sweeps = [s for s in sweeps if s.sweep_ts.time() <= until]
    if not sweeps:
        return None
    sweeps.sort(key=lambda s: s.sweep_ts)
    return sweeps[0]


def _completed_5m_after(
    five: pd.DataFrame,
    after_ts: pd.Timestamp,
    until_ts: pd.Timestamp,
) -> List[Tuple[pd.Timestamp, pd.Series]]:
    """5m bars whose *close* (index+5m) is after after_ts and <= until_ts."""
    after_ts = _localize(after_ts)
    until_ts = _localize(until_ts)
    # left-labeled: close_ts = start + 5m; need start > after_ts - 5m and start <= until_ts - 5m
    start_lo = after_ts - pd.Timedelta(minutes=5)
    start_hi = until_ts - pd.Timedelta(minutes=5)
    idx = five.index
    lo = idx.searchsorted(start_lo, side="right")
    hi = idx.searchsorted(start_hi, side="right")
    rows = []
    for i in range(int(lo), int(hi)):
        ts = _localize(idx[i])
        close_ts = ts + pd.Timedelta(minutes=5)
        if close_ts <= after_ts:
            continue
        if close_ts > until_ts:
            break
        rows.append((ts, five.iloc[i]))
    return rows


def _max_high_between(one_m: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    sl = one_m.loc[_localize(start) : _localize(end)]
    if sl.empty:
        return float("nan")
    return float(sl["high"].max())


def _min_low_between(one_m: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    sl = one_m.loc[_localize(start) : _localize(end)]
    if sl.empty:
        return float("nan")
    return float(sl["low"].min())


def _first_1m_after(one_m: pd.DataFrame, after_ts: pd.Timestamp) -> Optional[Tuple[pd.Timestamp, pd.Series]]:
    after_ts = _localize(after_ts)
    idx = one_m.index.searchsorted(after_ts, side="right")
    if idx >= len(one_m):
        return None
    ts = _localize(one_m.index[idx])
    return ts, one_m.iloc[idx]


def _build_confirmed(
    sweep: SweepEvent,
    five: pd.DataFrame,
    one_m: pd.DataFrame,
) -> Optional[FadeCandidate]:
    deadline = sweep.sweep_ts + pd.Timedelta(minutes=MAX_FAILURE_MINUTES)
    bars = _completed_5m_after(five, sweep.sweep_ts, deadline)
    failure = None
    fail_row = None
    for ts, row in bars:
        cl = float(row["close"])
        if sweep.side == "UPSIDE_SWEEP" and cl < sweep.pmc:
            failure, fail_row = ts, row
            break
        if sweep.side == "DOWNSIDE_SWEEP" and cl > sweep.pmc:
            failure, fail_row = ts, row
            break
    if failure is None:
        return None
    fail_close_ts = failure + pd.Timedelta(minutes=5)
    # next confirmation bar
    conf_bars = _completed_5m_after(five, fail_close_ts - pd.Timedelta(seconds=1), fail_close_ts + pd.Timedelta(days=1))
    conf_bars = [(t, r) for t, r in conf_bars if t > failure]
    if not conf_bars:
        return None
    conf_ts, conf_row = conf_bars[0]
    conf_close = float(conf_row["close"])
    conf_close_ts = conf_ts + pd.Timedelta(minutes=5)
    if sweep.side == "UPSIDE_SWEEP":
        if conf_close >= sweep.pmc:
            return None
        if conf_close >= float(fail_row["low"]):
            return None
        side = "SHORT"
        stop = _max_high_between(one_m, sweep.sweep_ts, conf_close_ts) + STOP_BUFFER_TICKS * TICK
    else:
        if conf_close <= sweep.pmc:
            return None
        if conf_close <= float(fail_row["high"]):
            return None
        side = "LONG"
        stop = _min_low_between(one_m, sweep.sweep_ts, conf_close_ts) - STOP_BUFFER_TICKS * TICK
    nxt = _first_1m_after(one_m, conf_close_ts)
    if nxt is None:
        return None
    entry_ts, entry_row = nxt
    if entry_ts.time() > SESSION_CUTOFF:
        return None
    entry = _adverse_entry(side, float(entry_row["open"]))
    if side == "SHORT":
        risk = stop - entry
        if risk <= 0:
            return None
        tp1, tp2, runner = entry - 1.0 * risk, entry - 2.0 * risk, entry - 4.0 * risk
    else:
        risk = entry - stop
        if risk <= 0:
            return None
        tp1, tp2, runner = entry + 1.0 * risk, entry + 2.0 * risk, entry + 4.0 * risk
    return FadeCandidate(
        control="confirmed",
        side=side,
        session=sweep.session,
        pmc=sweep.pmc,
        sweep_ts=sweep.sweep_ts,
        sweep_extreme=sweep.sweep_extreme,
        failure_ts=fail_close_ts,
        confirm_ts=conf_close_ts,
        entry_ts=entry_ts,
        entry_price=entry,
        stop_price=stop,
        risk_r=risk,
        tp1=tp1,
        tp2=tp2,
        runner=runner,
        atr_5m=sweep.atr_5m,
        penetration_atr=sweep.penetration_atr,
    )


def _build_reclaim_only(
    sweep: SweepEvent,
    five: pd.DataFrame,
    one_m: pd.DataFrame,
) -> Optional[FadeCandidate]:
    deadline = sweep.sweep_ts + pd.Timedelta(minutes=MAX_FAILURE_MINUTES)
    bars = _completed_5m_after(five, sweep.sweep_ts, deadline)
    failure = None
    for ts, row in bars:
        cl = float(row["close"])
        if sweep.side == "UPSIDE_SWEEP" and cl < sweep.pmc:
            failure = ts
            break
        if sweep.side == "DOWNSIDE_SWEEP" and cl > sweep.pmc:
            failure = ts
            break
    if failure is None:
        return None
    fail_close_ts = failure + pd.Timedelta(minutes=5)
    if sweep.side == "UPSIDE_SWEEP":
        side = "SHORT"
        stop = _max_high_between(one_m, sweep.sweep_ts, fail_close_ts) + STOP_BUFFER_TICKS * TICK
    else:
        side = "LONG"
        stop = _min_low_between(one_m, sweep.sweep_ts, fail_close_ts) - STOP_BUFFER_TICKS * TICK
    nxt = _first_1m_after(one_m, fail_close_ts)
    if nxt is None:
        return None
    entry_ts, entry_row = nxt
    if entry_ts.time() > SESSION_CUTOFF:
        return None
    entry = _adverse_entry(side, float(entry_row["open"]))
    if side == "SHORT":
        risk = stop - entry
        if risk <= 0:
            return None
        tp1, tp2, runner = entry - risk, entry - 2 * risk, entry - 4 * risk
    else:
        risk = entry - stop
        if risk <= 0:
            return None
        tp1, tp2, runner = entry + risk, entry + 2 * risk, entry + 4 * risk
    return FadeCandidate(
        control="reclaim_only",
        side=side,
        session=sweep.session,
        pmc=sweep.pmc,
        sweep_ts=sweep.sweep_ts,
        sweep_extreme=sweep.sweep_extreme,
        failure_ts=fail_close_ts,
        confirm_ts=None,
        entry_ts=entry_ts,
        entry_price=entry,
        stop_price=stop,
        risk_r=risk,
        tp1=tp1,
        tp2=tp2,
        runner=runner,
        atr_5m=sweep.atr_5m,
        penetration_atr=sweep.penetration_atr,
    )


def _build_naive(
    sweep: SweepEvent,
    one_m: pd.DataFrame,
) -> Optional[FadeCandidate]:
    nxt = _first_1m_after(one_m, sweep.sweep_ts)
    if nxt is None:
        return None
    entry_ts, entry_row = nxt
    if entry_ts.time() > SESSION_CUTOFF:
        return None
    if sweep.side == "UPSIDE_SWEEP":
        side = "SHORT"
        stop = sweep.sweep_extreme + STOP_BUFFER_TICKS * TICK
    else:
        side = "LONG"
        stop = sweep.sweep_extreme - STOP_BUFFER_TICKS * TICK
    entry = _adverse_entry(side, float(entry_row["open"]))
    if side == "SHORT":
        risk = stop - entry
        if risk <= 0:
            return None
        tp1, tp2, runner = entry - risk, entry - 2 * risk, entry - 4 * risk
    else:
        risk = entry - stop
        if risk <= 0:
            return None
        tp1, tp2, runner = entry + risk, entry + 2 * risk, entry + 4 * risk
    return FadeCandidate(
        control="naive",
        side=side,
        session=sweep.session,
        pmc=sweep.pmc,
        sweep_ts=sweep.sweep_ts,
        sweep_extreme=sweep.sweep_extreme,
        failure_ts=None,
        confirm_ts=None,
        entry_ts=entry_ts,
        entry_price=entry,
        stop_price=stop,
        risk_r=risk,
        tp1=tp1,
        tp2=tp2,
        runner=runner,
        atr_5m=sweep.atr_5m,
        penetration_atr=sweep.penetration_atr,
    )


# ---------------------------------------------------------------------------
# Taxonomy (Phase 1)
# ---------------------------------------------------------------------------


def _post_reclaim_excursions(
    one_m: pd.DataFrame,
    reclaim_ts: pd.Timestamp,
    side: str,
    pmc: float,
    eod: pd.Timestamp,
) -> Tuple[float, float, float]:
    """Return (mfe_pts, mae_pts, max_extension_before_reclaim already separate).

    For upside sweep reclaim (fade short): MFE = pmc - low after reclaim (favorable down).
    MAE = high - pmc after reclaim.
    """
    sl = one_m.loc[_localize(reclaim_ts) : _localize(eod)]
    if sl.empty:
        return float("nan"), float("nan"), float("nan")
    if side == "UPSIDE_SWEEP":
        mfe = pmc - float(sl["low"].min())
        mae = float(sl["high"].max()) - pmc
    else:
        mfe = float(sl["high"].max()) - pmc
        mae = pmc - float(sl["low"].min())
    return mfe, mae, float(sl["close"].iloc[-1])


def build_taxonomy(
    gby: Dict[date, pd.DataFrame],
    five: pd.DataFrame,
    atr: pd.Series,
    pmc_map: Dict[Tuple[int, int], float],
    holidays: set,
    *,
    smoke: bool = False,
) -> pd.DataFrame:
    atr_ix = AtrIndex.from_series(atr)
    rows: List[Dict[str, Any]] = []
    days = sorted(gby.keys())
    if smoke:
        days = days[:60]
    for i, d in enumerate(days):
        if i % 200 == 0:
            print("  taxonomy session %d/%d %s" % (i, len(days), d), flush=True)
        pmc = pmc_map.get((d.year, d.month))
        if pmc is None:
            continue
        rth = _rth_slice(gby.get(d))
        if _is_early_close(rth):
            continue
        sweeps = _all_sweeps_for_taxonomy(rth, float(pmc), atr_ix)
        eod = pd.Timestamp(datetime.combine(d, EOD_FLATTEN), tz=NY)
        for sw in sweeps:
            # time beyond / reclaim windows
            beyond_mins = 0.0
            bars_accepted = 0
            reclaim_ts = None
            reclaim_window = None
            deadline = sw.sweep_ts + pd.Timedelta(minutes=MAX_FAILURE_MINUTES)
            five_after = _completed_5m_after(five, sw.sweep_ts, sw.sweep_ts + pd.Timedelta(hours=8))
            for ts, row in five_after:
                close_ts = ts + pd.Timedelta(minutes=5)
                cl = float(row["close"])
                hi = float(row["high"])
                lo = float(row["low"])
                if sw.side == "UPSIDE_SWEEP":
                    accepted = cl > sw.pmc
                    still_beyond = lo > sw.pmc
                else:
                    accepted = cl < sw.pmc
                    still_beyond = hi < sw.pmc
                if accepted:
                    bars_accepted += 1
                if still_beyond:
                    beyond_mins = (close_ts - sw.sweep_ts).total_seconds() / 60.0
                # reclaim = first close back inside
                if reclaim_ts is None:
                    if sw.side == "UPSIDE_SWEEP" and cl < sw.pmc:
                        reclaim_ts = close_ts
                    elif sw.side == "DOWNSIDE_SWEEP" and cl > sw.pmc:
                        reclaim_ts = close_ts
                    if reclaim_ts is not None:
                        mins = (reclaim_ts - sw.sweep_ts).total_seconds() / 60.0
                        for w in (5, 15, 30, 60):
                            if mins <= w:
                                reclaim_window = w
                                break
                        if reclaim_window is None and mins <= MAX_FAILURE_MINUTES:
                            reclaim_window = 60
            # extension before reclaim
            if reclaim_ts is not None:
                if sw.side == "UPSIDE_SWEEP":
                    ext = _max_high_between(rth, sw.sweep_ts, reclaim_ts) - sw.pmc
                else:
                    ext = sw.pmc - _min_low_between(rth, sw.sweep_ts, reclaim_ts)
                mfe, mae, _ = _post_reclaim_excursions(rth, reclaim_ts, sw.side, sw.pmc, eod)
                time_to_reclaim = (reclaim_ts - sw.sweep_ts).total_seconds() / 60.0
            else:
                if sw.side == "UPSIDE_SWEEP":
                    ext = float(rth.loc[sw.sweep_ts :]["high"].max()) - sw.pmc
                else:
                    ext = sw.pmc - float(rth.loc[sw.sweep_ts :]["low"].min())
                mfe = mae = float("nan")
                time_to_reclaim = float("nan")
            # wick/body on sweep 1m
            sw_row = rth.loc[sw.sweep_ts] if sw.sweep_ts in rth.index else None
            wick_body = float("nan")
            if sw_row is not None:
                body = abs(float(sw_row["close"]) - float(sw_row["open"]))
                rng = float(sw_row["high"]) - float(sw_row["low"])
                wick_body = (rng - body) / body if body > 1e-9 else float("inf")
            touched = True  # by construction
            rows.append(
                {
                    "session": d.isoformat(),
                    "side": sw.side,
                    "pmc": round(sw.pmc, 4),
                    "pmc_touched": touched,
                    "sweep_ts": sw.sweep_ts.isoformat(),
                    "sweep_extreme": round(sw.sweep_extreme, 4),
                    "penetration": round(sw.penetration, 4),
                    "penetration_atr": round(sw.penetration_atr, 4),
                    "atr_5m": round(sw.atr_5m, 4),
                    "time_beyond_pmc_mins": round(beyond_mins, 2),
                    "reclaim_within_5m": bool(reclaim_window is not None and reclaim_window <= 5),
                    "reclaim_within_15m": bool(reclaim_window is not None and reclaim_window <= 15),
                    "reclaim_within_30m": bool(reclaim_window is not None and reclaim_window <= 30),
                    "reclaim_within_60m": bool(reclaim_window is not None and reclaim_window <= 60),
                    "reclaim_window_min": reclaim_window if reclaim_window is not None else "",
                    "bars_5m_accepted_beyond": bars_accepted,
                    "sweep_wick_body_ratio": round(wick_body, 4) if np.isfinite(wick_body) else "",
                    "max_extension_before_reclaim": round(ext, 4),
                    "time_sweep_to_reclaim_mins": round(time_to_reclaim, 2) if pd.notna(time_to_reclaim) else "",
                    "post_reclaim_mfe_pts": round(mfe, 4) if pd.notna(mfe) else "",
                    "post_reclaim_mae_pts": round(mae, 4) if pd.notna(mae) else "",
                    "hour_ny": int(sw.sweep_ts.hour),
                    "dow": sw.sweep_ts.day_name(),
                    "event_day": bool(d in holidays or _is_nfp_friday(d)),
                    "holiday": bool(d in holidays),
                    "nfp_friday": _is_nfp_friday(d),
                    "reclaim_before_deadline": bool(
                        reclaim_ts is not None and reclaim_ts <= deadline
                    ),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Replay management (Phase 2)
# ---------------------------------------------------------------------------


def _manage_open(
    ot: OpenFade,
    bars: pd.DataFrame,
    *,
    point_value: float = POINT_VALUE,
    fee: float = FEE_PER_UNIT,
) -> Tuple[Optional[OpenFade], List[dict], float, float]:
    """Walk 1m bars stop-first; return (still_open, unit_exits, realized_delta, stress)."""
    exits: List[dict] = []
    realized = 0.0
    stress = 0.0
    if bars is None or bars.empty:
        return ot, exits, realized, stress
    idx = bars.index
    if idx.tz is None:
        idx = idx.tz_localize(NY)
    else:
        idx = idx.tz_convert(NY)
    ts_ns = idx.asi8.astype(np.int64)
    opens = bars["open"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    entry_ns = _ts_ns(ot.entry_ts)

    def _flat(ts: pd.Timestamp, px: float, reason: str) -> None:
        nonlocal realized
        while ot.units_remaining > 0:
            qty = 1
            pts = (px - ot.entry) if ot.side == "LONG" else (ot.entry - px)
            net = pts * point_value * qty - fee * qty
            exits.append(
                {
                    "trade_id": ot.trade_id,
                    "control": ot.control,
                    "side": ot.side,
                    "session": ot.session.isoformat(),
                    "unit_qty": qty,
                    "entry_ts": ot.entry_ts.isoformat(),
                    "exit_ts": ts.isoformat(),
                    "entry": ot.entry,
                    "exit": px,
                    "reason": reason,
                    "target_r": "",
                    "points": pts,
                    "net_usd": net,
                }
            )
            realized += net
            ot.units_remaining -= qty

    for i in range(len(ts_ns)):
        if int(ts_ns[i]) <= entry_ns:
            continue
        ts = pd.Timestamp(int(ts_ns[i]), tz="UTC").tz_convert(NY)
        tclock = ts.time()
        if tclock >= EOD_FLATTEN:
            _flat(ts, float(opens[i]), "eod_flatten")
            return None, exits, realized, stress

        hi = float(highs[i])
        lo = float(lows[i])
        if ot.side == "LONG":
            ot.mfe = max(ot.mfe, hi - ot.entry)
            ot.mae = min(ot.mae, lo - ot.entry)
            adverse = (lo - ot.entry) * point_value * ot.units_remaining
        else:
            ot.mfe = max(ot.mfe, ot.entry - lo)
            ot.mae = min(ot.mae, ot.entry - hi)
            adverse = (ot.entry - hi) * point_value * ot.units_remaining
        stress = min(stress, adverse)

        stopped = (ot.side == "LONG" and lo <= ot.stop) or (ot.side == "SHORT" and hi >= ot.stop)
        if stopped:
            px = _adverse_stop(ot.side, ot.stop)
            _flat(ts, px, "stop")
            return None, exits, realized, stress

        for tgt_px, qty_want, label in ot.targets:
            if label in ot.filled or ot.units_remaining <= 0:
                continue
            hit = (ot.side == "LONG" and hi >= tgt_px) or (ot.side == "SHORT" and lo <= tgt_px)
            if not hit:
                continue
            qty = min(qty_want, ot.units_remaining)
            pts = (tgt_px - ot.entry) if ot.side == "LONG" else (ot.entry - tgt_px)
            net = pts * point_value * qty - fee * qty
            exits.append(
                {
                    "trade_id": ot.trade_id,
                    "control": ot.control,
                    "side": ot.side,
                    "session": ot.session.isoformat(),
                    "unit_qty": qty,
                    "entry_ts": ot.entry_ts.isoformat(),
                    "exit_ts": ts.isoformat(),
                    "entry": ot.entry,
                    "exit": tgt_px,
                    "reason": label,
                    "target_r": label.replace("tp_", "").replace("r", ""),
                    "points": pts,
                    "net_usd": net,
                }
            )
            realized += net
            ot.filled[label] = qty
            ot.units_remaining -= qty
        if ot.units_remaining <= 0:
            return None, exits, realized, stress
    return ot, exits, realized, stress


def _candidate_for_session(
    control: str,
    sweeps: List[SweepEvent],
    five: pd.DataFrame,
    one_m: pd.DataFrame,
) -> Optional[FadeCandidate]:
    cands: List[FadeCandidate] = []
    for sw in sweeps:
        if control == "naive":
            c = _build_naive(sw, one_m)
        elif control == "reclaim_only":
            c = _build_reclaim_only(sw, five, one_m)
        else:
            c = _build_confirmed(sw, five, one_m)
        if c is not None:
            cands.append(c)
    if not cands:
        return None
    cands.sort(key=lambda x: x.entry_ts)
    return cands[0]


def run_control_replay(
    control: str,
    gby: Dict[date, pd.DataFrame],
    five: pd.DataFrame,
    atr: pd.Series,
    pmc_map: Dict[Tuple[int, int], float],
    *,
    smoke: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    atr_ix = AtrIndex.from_series(atr)
    trades: List[dict] = []
    units: List[dict] = []
    equity: List[dict] = []
    realized = 0.0
    peak = 0.0
    max_dd = 0.0
    trade_id = 0
    days = sorted(gby.keys())
    if smoke:
        days = days[:60]
    for i, d in enumerate(days):
        if i % 200 == 0:
            print("  %s session %d/%d %s" % (control, i, len(days), d), flush=True)
        pmc = pmc_map.get((d.year, d.month))
        if pmc is None:
            continue
        rth = _rth_slice(gby.get(d))
        if _is_early_close(rth):
            continue
        sweeps = _all_sweeps_for_taxonomy(rth, float(pmc), atr_ix)
        if not sweeps:
            continue
        cand = _candidate_for_session(control, sweeps, five, rth)
        if cand is None:
            continue
        trade_id += 1
        targets = [
            (cand.tp1, TP_QTY[0], "tp_1r"),
            (cand.tp2, TP_QTY[1], "tp_2r"),
            (cand.runner, TP_QTY[2], "tp_4r"),
        ]
        ot = OpenFade(
            trade_id=trade_id,
            control=control,
            side=cand.side,
            session=d,
            entry_ts=cand.entry_ts,
            entry=cand.entry_price,
            stop=cand.stop_price,
            risk_r=cand.risk_r,
            targets=targets,
            units_remaining=ENTRY_QTY,
            pmc=cand.pmc,
            sweep_ts=cand.sweep_ts.isoformat(),
            failure_ts=cand.failure_ts.isoformat() if cand.failure_ts is not None else "",
            confirm_ts=cand.confirm_ts.isoformat() if cand.confirm_ts is not None else "",
        )
        # manage from entry through EOD on this session (+ spill to next RTH if needed)
        manage_bars = rth.loc[cand.entry_ts :]
        still, exits, d_real, stress = _manage_open(ot, manage_bars)
        # if still open past session (shouldn't with EOD), flatten last close
        if still is not None and still.units_remaining > 0:
            last_ts = _localize(manage_bars.index[-1])
            px = float(manage_bars.iloc[-1]["close"])
            while still.units_remaining > 0:
                pts = (px - still.entry) if still.side == "LONG" else (still.entry - px)
                net = pts * POINT_VALUE - FEE_PER_UNIT
                exits.append(
                    {
                        "trade_id": still.trade_id,
                        "control": control,
                        "side": still.side,
                        "session": d.isoformat(),
                        "unit_qty": 1,
                        "entry_ts": still.entry_ts.isoformat(),
                        "exit_ts": last_ts.isoformat(),
                        "entry": still.entry,
                        "exit": px,
                        "reason": "session_end",
                        "target_r": "",
                        "points": pts,
                        "net_usd": net,
                    }
                )
                d_real += net
                still.units_remaining -= 1
            ot = still
        units.extend(exits)
        realized += d_real
        peak = max(peak, realized)
        max_dd = min(max_dd, realized - peak)
        exit_ts = exits[-1]["exit_ts"] if exits else cand.entry_ts.isoformat()
        reasons = sorted({e["reason"] for e in exits})
        trades.append(
            {
                "trade_id": trade_id,
                "control": control,
                "session": d.isoformat(),
                "side": cand.side,
                "pmc": cand.pmc,
                "sweep_ts": cand.sweep_ts.isoformat(),
                "failure_ts": cand.failure_ts.isoformat() if cand.failure_ts else "",
                "confirm_ts": cand.confirm_ts.isoformat() if cand.confirm_ts else "",
                "entry_ts": cand.entry_ts.isoformat(),
                "exit_ts": exit_ts,
                "entry": cand.entry_price,
                "stop": cand.stop_price,
                "risk_r": cand.risk_r,
                "tp1": cand.tp1,
                "tp2": cand.tp2,
                "runner": cand.runner,
                "penetration_atr": cand.penetration_atr,
                "atr_5m": cand.atr_5m,
                "mfe_pts": ot.mfe,
                "mae_pts": ot.mae,
                "units": ENTRY_QTY,
                "net_usd": float(sum(e["net_usd"] for e in exits)),
                "stress_usd": float(stress),
                "exit_reasons": ",".join(reasons),
                "hit_1r": any(e["reason"] == "tp_1r" for e in exits),
                "hit_2r": any(e["reason"] == "tp_2r" for e in exits),
                "hit_4r": any(e["reason"] == "tp_4r" for e in exits),
                "stopped": any(e["reason"] == "stop" for e in exits),
            }
        )
        equity.append(
            {
                "ts": exit_ts,
                "realized_usd": realized,
                "trade_id": trade_id,
                "control": control,
            }
        )
    tdf = pd.DataFrame(trades)
    udf = pd.DataFrame(units)
    edf = pd.DataFrame(equity)
    metrics = _metrics(tdf, realized, max_dd)
    return tdf, udf, edf, metrics


def _metrics(tdf: pd.DataFrame, realized: float, max_dd: float) -> Dict[str, float]:
    if tdf is None or tdf.empty:
        return {
            "net_usd": 0.0,
            "stress_dd_usd": 0.0,
            "ns": 0.0,
            "trades": 0,
            "units": 0,
            "win_rate": 0.0,
            "pf": 0.0,
            "avg_r": 0.0,
            "median_r": 0.0,
            "long_net": 0.0,
            "short_net": 0.0,
            "runner_net_share": 0.0,
            "close_mtm_dd_usd": float(max_dd),
        }
    nets = tdf["net_usd"].astype(float)
    wins = nets[nets > 0].sum()
    losses = nets[nets < 0].sum()
    pf = float(wins / abs(losses)) if losses < 0 else float("inf")
    r_vals = []
    for _, r in tdf.iterrows():
        risk = float(r.get("risk_r") or 0)
        if risk <= 0:
            continue
        one_r_usd = risk * POINT_VALUE * ENTRY_QTY
        r_vals.append(float(r["net_usd"]) / one_r_usd if one_r_usd else 0.0)
    stress = float(tdf["stress_usd"].min()) if "stress_usd" in tdf.columns else float(max_dd)
    # book stress = min of campaign stresses (conservative) or equity DD
    book_stress = min(float(stress), float(max_dd))
    ns = float(realized / abs(book_stress)) if book_stress < 0 else (float("inf") if realized > 0 else 0.0)
    long_net = float(tdf.loc[tdf["side"] == "LONG", "net_usd"].sum()) if (tdf["side"] == "LONG").any() else 0.0
    short_net = float(tdf.loc[tdf["side"] == "SHORT", "net_usd"].sum()) if (tdf["side"] == "SHORT").any() else 0.0
    # runner share from unit exits not available here — filled in later
    return {
        "net_usd": float(realized),
        "stress_dd_usd": float(book_stress),
        "ns": float(ns) if np.isfinite(ns) else 0.0,
        "trades": int(len(tdf)),
        "units": int(tdf["units"].sum()) if "units" in tdf.columns else int(len(tdf) * ENTRY_QTY),
        "win_rate": float((nets > 0).mean()) if len(nets) else 0.0,
        "pf": float(pf) if np.isfinite(pf) else 999.0,
        "avg_r": float(np.mean(r_vals)) if r_vals else 0.0,
        "median_r": float(np.median(r_vals)) if r_vals else 0.0,
        "long_net": long_net,
        "short_net": short_net,
        "runner_net_share": 0.0,
        "close_mtm_dd_usd": float(max_dd),
    }


def _runner_share(units: pd.DataFrame) -> float:
    if units is None or units.empty:
        return 0.0
    total = float(units["net_usd"].sum())
    if abs(total) < 1e-9:
        return 0.0
    runner = float(units.loc[units["reason"] == "tp_4r", "net_usd"].sum())
    return runner / total


def _yearly(tdf: pd.DataFrame) -> pd.DataFrame:
    if tdf is None or tdf.empty:
        return pd.DataFrame()
    df = tdf.copy()
    df["year"] = pd.to_datetime(df["session"]).dt.year
    rows = []
    for y, g in df.groupby("year"):
        net = float(g["net_usd"].sum())
        stress = float(g["stress_usd"].min()) if "stress_usd" in g.columns else 0.0
        rows.append(
            {
                "year": int(y),
                "trades": int(len(g)),
                "net_usd": net,
                "stress_usd": stress,
                "ns": (net / abs(stress)) if stress < 0 else (float("inf") if net > 0 else 0.0),
                "win_rate": float((g["net_usd"] > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DSR / IO / summary
# ---------------------------------------------------------------------------


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "us30_pmc_failed_break_fade",
            "is_independent": "TRUE",
            "market": "US30",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "level": "PMC",
                    "min_penetration_atr": MIN_PENETRATION_ATR,
                    "max_failure_min": MAX_FAILURE_MINUTES,
                    "confirmation_bars": CONFIRMATION_BARS,
                    "tp": list(TP_LADDER),
                    "qty": list(TP_QTY),
                    "controls": list(CONTROLS),
                    "fill": "1m_stop_first",
                    "costs": "fee_1.50_plus_1tick_adverse",
                }
            ),
            "fixed_parameters_ref": "live/us30_pmc_failed_break_fade.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "US30 PMC failed-break fade Phase1 taxonomy + Phase2 naive/reclaim/confirmed",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str = "COMPLETE") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _stance(metrics_by: Dict[str, Dict[str, float]]) -> Tuple[str, str]:
    """Return (stance_label, rationale) per interpretation gates."""
    c = metrics_by.get("confirmed") or {}
    r = metrics_by.get("reclaim_only") or {}
    n = metrics_by.get("naive") or {}
    c_net = float(c.get("net_usd") or 0)
    r_net = float(r.get("net_usd") or 0)
    n_net = float(n.get("net_usd") or 0)
    c_ns = float(c.get("ns") or 0)
    runner_share = float(c.get("runner_net_share") or 0)

    if c_net < 0 or c_ns < 0:
        if r_net > 0 and c_net < 0:
            return (
                "DO_NOT_PROMOTE",
                "Reclaim-only positive / confirmed negative — confirmation too late; "
                "no promote; early-entry study only if warranted. Do not revive fair-3R.",
            )
        if n_net > 0 and c_net < 0:
            return (
                "REJECT_ARTIFACT",
                "Naive positive / confirmed negative — suspect path artifact; do not promote. "
                "Retire US30 revival program for this fade family.",
            )
        return (
            "RETIRE_US30_REVIVAL",
            "Confirmed fade negative — post-close liquidity-sweep story does not translate "
            "into a trade. Retire US30 revival program.",
        )
    # confirmed positive
    if runner_share > 0.85 and c_net > 0:
        return (
            "RESEARCH_RUNNER_DEPENDENT",
            "Confirmed positive but runner (4R) drives most of net — keep runner dependence "
            "explicit; capped exits before any demo.",
        )
    if c_ns >= 1.0 and c_net > 0:
        return (
            "RESEARCH_PLUGIN_CANDIDATE",
            "Confirmed fade positive — proceed to Phase 3 causality + bounded sensitivity "
            "before StrategyPlugin port (not demo-promote yet).",
        )
    return (
        "RESEARCH_WEAK_POSITIVE",
        "Confirmed fade net positive but weak N/S — research only; no promote.",
    )


def write_summary(
    hub: Path,
    tax: pd.DataFrame,
    metrics_by: Dict[str, Dict[str, float]],
    yearly_by: Dict[str, pd.DataFrame],
    stance: str,
    rationale: str,
) -> str:
    lines = [
        "# US30 PMC failed-break fade — Phase 1/2",
        "",
        "**Hub:** `live/state/us30_pmc_failed_break_fade/`",
        "**DSR:** `%s`" % DSR,
        "**Status:** Phase 1 taxonomy + Phase 2 frozen base replay complete.",
        "",
        "## Frozen params",
        "",
        "| Param | Value |",
        "|---|---|",
        "| Level | PMC only |",
        "| MIN_PENETRATION | 0.10 × ATR_20_5m |",
        "| MAX_FAILURE_MINUTES | 60 |",
        "| CONFIRMATION_BARS | 1 |",
        "| STOP_BUFFER | 1 tick (0.1) |",
        "| TP ladder | 1R/2R/4R @ 2/1/1 lots (50/25/25) |",
        "| Costs | fee $1.50/unit + 1-tick adverse entry/stop |",
        "| Early closes | excluded (<300 RTH bars or last <15:45) |",
        "",
        "## Phase 1 — event taxonomy",
        "",
    ]
    if tax is None or tax.empty:
        lines.append("_No PMC sweeps found._")
    else:
        n = len(tax)
        reclaim60 = float(tax["reclaim_within_60m"].mean()) if "reclaim_within_60m" in tax else 0
        lines.extend(
            [
                "- Sweep events (first per side/session, early-closes excluded): **%d**" % n,
                "- Upside / downside: %d / %d"
                % (
                    int((tax["side"] == "UPSIDE_SWEEP").sum()),
                    int((tax["side"] == "DOWNSIDE_SWEEP").sum()),
                ),
                "- Reclaim within 60m: **%.1f%%**" % (100.0 * reclaim60),
                "- Reclaim within 15m: **%.1f%%**"
                % (100.0 * float(tax["reclaim_within_15m"].mean())),
                "- Median penetration (ATR): **%.2f**" % float(tax["penetration_atr"].median()),
                "- Median time sweep→reclaim (min): **%s**"
                % (
                    ("%.1f" % float(pd.to_numeric(tax["time_sweep_to_reclaim_mins"], errors="coerce").median()))
                    if tax["time_sweep_to_reclaim_mins"].astype(str).ne("").any()
                    else "n/a"
                ),
                "- Event-day fraction: **%.1f%%**" % (100.0 * float(tax["event_day"].mean())),
                "",
                "Full table: `taxonomy/pmc_sweeps.csv`",
            ]
        )
    lines.extend(["", "## Phase 2 — frozen base replay", "", "| Control | N | Net $ | Stress $ | N/S | WR | PF | Avg R | Long $ | Short $ | Runner share |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for name in CONTROLS:
        m = metrics_by.get(name) or {}
        lines.append(
            "| %s | %d | %.0f | %.0f | %.2f | %.1f%% | %.2f | %.2f | %.0f | %.0f | %.0f%% |"
            % (
                name,
                int(m.get("trades") or 0),
                float(m.get("net_usd") or 0),
                float(m.get("stress_dd_usd") or 0),
                float(m.get("ns") or 0),
                100.0 * float(m.get("win_rate") or 0),
                float(m.get("pf") or 0),
                float(m.get("avg_r") or 0),
                float(m.get("long_net") or 0),
                float(m.get("short_net") or 0),
                100.0 * float(m.get("runner_net_share") or 0),
            )
        )
    lines.append("")
    lines.append(
        "_Runner share = tp_4r net / book net (can exceed 100% when other legs lose)._"
    )
    lines.extend(["", "### Yearly (confirmed)", ""])
    y = yearly_by.get("confirmed")
    if y is not None and not y.empty:
        lines.append("| Year | N | Net $ | Stress $ | N/S | WR |")
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for _, r in y.iterrows():
            lines.append(
                "| %d | %d | %.0f | %.0f | %.2f | %.1f%% |"
                % (
                    int(r["year"]),
                    int(r["trades"]),
                    float(r["net_usd"]),
                    float(r["stress_usd"]),
                    float(r["ns"]) if np.isfinite(r["ns"]) else 0.0,
                    100.0 * float(r["win_rate"]),
                )
            )
    else:
        lines.append("_no confirmed trades_")
    lines.extend(
        [
            "",
            "## Stance",
            "",
            "**%s** — %s" % (stance, rationale),
            "",
            "## Gates (reference)",
            "",
            "| Result | Action |",
            "|---|---|",
            "| Confirmed fade negative | Retire US30 revival program |",
            "| Reclaim-only + / confirmed − | Do not promote; early-entry study only if warranted |",
            "| Confirmed + stable plateau | StrategyPlugin port (Phase 3+) |",
            "| Naive + / confirmed − | Suspect artifact; do not promote |",
            "| Runner drives all net | Keep runner dependence explicit |",
            "",
            "Phase 3 (causality + sensitivity) and Phase 4 (adversarial) **not** run in this pass.",
        ]
    )
    text = "\n".join(lines) + "\n"
    (hub / "SUMMARY.md").write_text(text)
    return text


def write_email(
    hub: Path,
    metrics_by: Dict[str, Dict[str, float]],
    stance: str,
    rationale: str,
    tax_n: int,
) -> str:
    lines = [
        "US30 PMC failed-break fade Phase 1/2 complete.",
        "Hub: %s" % hub,
        "DSR: %s" % DSR,
        "Taxonomy sweeps: %d" % tax_n,
        "",
        "Controls:",
    ]
    for name in CONTROLS:
        m = metrics_by.get(name) or {}
        lines.append(
            "  %s  N=%d net=$%.0f stress=$%.0f N/S=%.2f WR=%.1f%% runner_share=%.0f%%"
            % (
                name,
                int(m.get("trades") or 0),
                float(m.get("net_usd") or 0),
                float(m.get("stress_dd_usd") or 0),
                float(m.get("ns") or 0),
                100.0 * float(m.get("win_rate") or 0),
                100.0 * float(m.get("runner_net_share") or 0),
            )
        )
    lines.extend(["", "Stance: %s" % stance, rationale, ""])
    body = "\n".join(lines)
    (hub / "EMAIL.txt").write_text(body)
    return body


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="US30 PMC failed-break fade Phase 1/2")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="~60 sessions only")
    ap.add_argument(
        "--phase",
        choices=("all", "taxonomy", "replay"),
        default="all",
    )
    ap.add_argument("--hub", type=Path, default=HUB)
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub: Path = args.hub
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "taxonomy").mkdir(exist_ok=True)
    (hub / "replay").mkdir(exist_ok=True)
    run_log = hub / "run.log"

    def log(msg: str) -> None:
        line = "[%s] %s" % (datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), msg)
        print(line, flush=True)
        with run_log.open("a") as fh:
            fh.write(line + "\n")

    try:
        hub_rel = str(hub.relative_to(REPO))
    except ValueError:
        hub_rel = str(hub)
    rid = begin_run(
        run_class="pandas",
        variant_slug="us30_pmc_failed_break_fade",
        instrument=SYM,
        hub_path=hub_rel,
        dsr_trial_id=DSR,
        meta={"phase": args.phase, "smoke": bool(args.smoke)},
    )
    _append_dsr()

    try:
        log("loading US30 1m …")
        gby = load_fx_1m_by_ny_date(ONE_M, SYM)
        one_m = concat_all_1m(gby)
        log("1m bars=%d sessions=%d" % (len(one_m), len(gby)))
        log("resampling 5m + ATR …")
        five = resample_5m(one_m)
        atr = atr_wilder(five, ATR_LEN)
        pmc_map = load_prev_month_close_map(DAILY)
        holidays = _us_holidays()

        tax = pd.DataFrame()
        if args.phase in ("all", "taxonomy"):
            log("Phase 1 taxonomy …")
            tax = build_taxonomy(gby, five, atr, pmc_map, holidays, smoke=args.smoke)
            tax_path = hub / "taxonomy" / "pmc_sweeps.csv"
            tax.to_csv(tax_path, index=False)
            # compact rollup
            roll = {
                "n_sweeps": int(len(tax)),
                "reclaim_60m_frac": float(tax["reclaim_within_60m"].mean()) if len(tax) else 0,
                "reclaim_15m_frac": float(tax["reclaim_within_15m"].mean()) if len(tax) else 0,
                "median_penetration_atr": float(tax["penetration_atr"].median()) if len(tax) else 0,
            }
            (hub / "taxonomy" / "rollup.json").write_text(json.dumps(roll, indent=2))
            log("taxonomy n=%d → %s" % (len(tax), tax_path))

        metrics_by: Dict[str, Dict[str, float]] = {}
        yearly_by: Dict[str, pd.DataFrame] = {}
        if args.phase in ("all", "replay"):
            log("Phase 2 frozen base replay …")
            for control in CONTROLS:
                log("control=%s" % control)
                tdf, udf, edf, metrics = run_control_replay(
                    control, gby, five, atr, pmc_map, smoke=args.smoke
                )
                metrics["runner_net_share"] = _runner_share(udf)
                metrics_by[control] = metrics
                yearly_by[control] = _yearly(tdf)
                out = hub / "replay" / control
                out.mkdir(parents=True, exist_ok=True)
                tdf.to_csv(out / "trades.csv", index=False)
                udf.to_csv(out / "units.csv", index=False)
                edf.to_csv(out / "equity.csv", index=False)
                yearly_by[control].to_csv(out / "yearly.csv", index=False)
                (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
                log(
                    "%s n=%d net=%.0f ns=%.2f"
                    % (control, metrics["trades"], metrics["net_usd"], metrics["ns"])
                )

            # summary board
            board = []
            for c, m in metrics_by.items():
                board.append({"control": c, **m})
            pd.DataFrame(board).to_csv(hub / "summary.csv", index=False)

        if tax.empty and (hub / "taxonomy" / "pmc_sweeps.csv").exists():
            tax = pd.read_csv(hub / "taxonomy" / "pmc_sweeps.csv")

        stance, rationale = _stance(metrics_by) if metrics_by else ("PENDING", "taxonomy only")
        write_summary(hub, tax, metrics_by, yearly_by, stance, rationale)
        body = write_email(hub, metrics_by, stance, rationale, int(len(tax)))

        # update RESEARCH_PLAN status
        plan = hub / "RESEARCH_PLAN.md"
        if plan.exists():
            import re

            txt = plan.read_text()
            txt2, n = re.subn(
                r"\*\*Status:\*\*[^\n]*",
                "**Status:** Phase 1/2 COMPLETE — %s." % stance,
                txt,
                count=1,
            )
            if n:
                plan.write_text(txt2)
            elif "QUEUED" in txt:
                plan.write_text(
                    txt.replace(
                        "**Status:** QUEUED — starts after `us30_st_pmc_causal_revival_abc` full matrix (pid watch) completes.",
                        "**Status:** Phase 1/2 COMPLETE — %s." % stance,
                    )
                )

        conf = metrics_by.get("confirmed") or {}
        complete_run(
            rid,
            net_usd=float(conf.get("net_usd") or 0),
            stress_dd_usd=float(conf.get("stress_dd_usd") or 0),
            close_mtm_dd_usd=float(conf.get("close_mtm_dd_usd") or 0),
            ns=float(conf.get("ns") or 0),
            trades=int(conf.get("trades") or 0),
            units=int(conf.get("units") or 0),
            notes="stance=%s" % stance,
            meta={"stance": stance, "controls": metrics_by},
        )
        _mark_dsr("COMPLETE")

        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                    "stance": stance,
                    "metrics": metrics_by,
                    "dsr": DSR,
                },
                indent=2,
                default=str,
            )
        )

        if args.email:
            send_email(subject="potions: US30 PMC failed-break fade Phase 1/2 complete", body=body)
            log("email sent")
        log("done stance=%s" % stance)
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _mark_dsr("FAILED")
        tb = traceback.format_exc()
        log("FAILED: %s" % exc)
        (hub / "EMAIL.txt").write_text("FAILED\n%s\n%s" % (exc, tb))
        if args.email:
            send_email(
                subject="potions: US30 PMC failed-break fade FAILED",
                body="Hub: %s\n%s\n%s" % (hub, exc, tb[-2000:]),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
