"""Shared FX helpers for MNQ→EURUSD untried-idea scouts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
LDN_TZ = pytz.timezone("Europe/London")

OR_START = time(9, 30)
OR_END = time(9, 45)
RTH_END = time(16, 0)
EOD_CUTOFF = time(15, 55)

POINT_VALUE = 100_000.0  # 1 standard lot
FEE = 1.50
TICK = 1e-5
HALF_SPREAD = 0.5 * TICK * 10  # ~0.5 pip
PIP = 0.0001


@dataclass
class Trade:
    strategy: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: float
    reason: str
    usd: float


def load_window(start: str = "2015-01-01", end: str = "2026-03-31") -> Tuple[pd.DataFrame, pd.DataFrame, Path]:
    one_m_path, daily_path = ensure_eurusd_platform_files(REPO)
    gby = load_fx_1m_by_ny_date(one_m_path, "EURUSD")
    one_m = concat_all_1m(gby).sort_index()
    start_ts = pd.Timestamp(start, tz=NY)
    end_ts = pd.Timestamp(end, tz=NY)
    one_m = one_m[(one_m.index >= start_ts) & (one_m.index <= end_ts)]
    daily = pd.read_csv(daily_path)
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    return one_m, daily, one_m_path


def rth_day(one_m: pd.DataFrame, day: date) -> pd.DataFrame:
    lo = NY_TZ.localize(datetime.combine(day, OR_START))
    hi = NY_TZ.localize(datetime.combine(day, RTH_END))
    return one_m[(one_m.index >= lo) & (one_m.index < hi)].copy()


def opening_range(day_1m: pd.DataFrame) -> Optional[Tuple[float, float, float]]:
    """Return (RH, RL, session_open) or None."""
    if day_1m.empty:
        return None
    opening = day_1m[(day_1m.index.time >= OR_START) & (day_1m.index.time < OR_END)]
    if opening.empty:
        return None
    rh = float(opening["high"].max())
    rl = float(opening["low"].min())
    if rh <= rl:
        return None
    session_open = float(day_1m.iloc[0]["open"])
    return rh, rl, session_open


def resample_5m_rth(day_1m: pd.DataFrame) -> pd.DataFrame:
    if day_1m.empty:
        return day_1m
    anchor = day_1m.index[0].normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        day_1m.resample("5min", label="left", closed="left", origin=anchor)
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna(subset=["open"])
    )


def prior_ma_bull_map(daily: pd.DataFrame) -> Dict[date, bool]:
    """Prior completed day MA50>MA150 → True for *next* session date."""
    close = pd.to_numeric(daily["close"], errors="coerce")
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    bull = (ma50 > ma150).shift(1)
    out: Dict[date, bool] = {}
    for i, row in daily.iterrows():
        d = pd.Timestamp(row["date"]).date()
        v = bull.iloc[i]
        if pd.isna(v):
            continue
        out[d] = bool(v)
    return out


def london_box(day_1m_full: pd.DataFrame, day: date) -> Optional[Tuple[float, float]]:
    """London box [02:00, 09:30) NY on that calendar day."""
    lo = NY_TZ.localize(datetime.combine(day, time(2, 0)))
    hi = NY_TZ.localize(datetime.combine(day, OR_START))
    box = day_1m_full[(day_1m_full.index >= lo) & (day_1m_full.index < hi)]
    if box.empty:
        return None
    return float(box["low"].min()), float(box["high"].max())


def pnl_usd(side: str, entry: float, exit_: float, qty: float = 1.0) -> float:
    if side.lower() in {"long", "buy"}:
        pts = (exit_ - entry) * qty
    else:
        pts = (entry - exit_) * qty
    return pts * POINT_VALUE - FEE * abs(qty)


def exit_long(path: pd.DataFrame, entry: float, stop: float, target: float) -> Tuple[float, str, pd.Timestamp]:
    for ts, bar in path.iterrows():
        lo, hi = float(bar["low"]), float(bar["high"])
        # pessimistic: stop before target
        if lo <= stop:
            return stop - HALF_SPREAD, "stop", pd.Timestamp(ts)
        if hi >= target:
            return target - HALF_SPREAD, "target", pd.Timestamp(ts)
    last = path.iloc[-1]
    return float(last["close"]) - HALF_SPREAD, "eod", pd.Timestamp(path.index[-1])


def exit_short(path: pd.DataFrame, entry: float, stop: float, target: float) -> Tuple[float, str, pd.Timestamp]:
    for ts, bar in path.iterrows():
        lo, hi = float(bar["low"]), float(bar["high"])
        if hi >= stop:
            return stop + HALF_SPREAD, "stop", pd.Timestamp(ts)
        if lo <= target:
            return target + HALF_SPREAD, "target", pd.Timestamp(ts)
    last = path.iloc[-1]
    return float(last["close"]) + HALF_SPREAD, "eod", pd.Timestamp(path.index[-1])


def path_after(day_1m: pd.DataFrame, after_ts: Optional[pd.Timestamp]) -> pd.DataFrame:
    if after_ts is None:
        return day_1m[day_1m.index.time >= OR_END]
    return day_1m[day_1m.index > after_ts]


def eod_path(day_1m: pd.DataFrame) -> pd.DataFrame:
    return day_1m[day_1m.index.time < EOD_CUTOFF]


def summarize(trades: Sequence[Trade], name: str) -> dict:
    if not trades:
        return {
            "strategy": name,
            "trades": 0,
            "units": 0.0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "closed_dd_usd": 0.0,
            "net_over_closed_dd": 0.0,
            "avg_usd": 0.0,
            "pass_scout_gate": False,
        }
    usd = np.array([t.usd for t in trades], dtype=float)
    qty = np.array([t.qty for t in trades], dtype=float)
    eq = np.cumsum(usd)
    peak = np.maximum.accumulate(eq)
    closed_dd = float((eq - peak).min())
    net = float(usd.sum())
    ratio = net / abs(closed_dd) if closed_dd else 0.0
    gate = (net > 0 and ratio >= 1.0) or (net >= 23533.0 and ratio > 0)
    return {
        "strategy": name,
        "trades": int(len(trades)),
        "units": float(qty.sum()),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2),
        "closed_dd_usd": round(closed_dd, 2),
        "net_over_closed_dd": round(ratio, 3),
        "avg_usd": round(net / len(trades), 2),
        "pass_scout_gate": bool(gate),
    }


def ny_sessions(one_m: pd.DataFrame) -> List[date]:
    return sorted({ts.astimezone(NY_TZ).date() for ts in one_m.index})
