"""Shared helpers for monthly ±4×ATR path / ladder studies on 1h bars."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from .quarterly_atr4_fade_broker import CACHE_1H, MARKETS, MarketSpec

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"


def resolve_1h_path(market: MarketSpec) -> Path:
    """Pick the longest available 1h source (fx csv / source_1h / cache parquet)."""
    cands: List[Tuple[int, Path]] = []
    fx = REPO / "fx" / ("%s_1h.csv" % market.symbol.lower())
    for path in (fx, market.source_1h, CACHE_1H / ("%s_1h.parquet" % market.symbol.lower())):
        if path is None or not path.exists() or path.stat().st_size <= 0:
            continue
        try:
            if path.suffix == ".parquet":
                # cheap row count
                import pyarrow.parquet as pq

                n = int(pq.ParquetFile(path).metadata.num_rows)
            else:
                with path.open("rb") as fh:
                    n = max(0, sum(1 for _ in fh) - 1)
        except Exception:
            n = int(path.stat().st_size)
        cands.append((n, path))
    if not cands:
        raise FileNotFoundError("No 1h source for %s" % market.symbol)
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def load_1h(market: MarketSpec) -> pd.DataFrame:
    path = resolve_1h_path(market)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == market.symbol.upper()].copy()
    ts_col = "ts_event" if "ts_event" in df.columns else ("ts" if "ts" in df.columns else None)
    if ts_col is None:
        raise ValueError("1h file missing ts/ts_event: %s" % path)
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df[ts_col], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    df = df.assign(ts_event=ts).dropna(subset=["ts_event"]).set_index("ts_event").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep]


def month_windows(
    bars: pd.DataFrame,
    start: Optional[date],
    end: Optional[date],
) -> List[Tuple[int, int, pd.Timestamp, pd.Timestamp]]:
    """Return (year, month, t0, t1) for each calendar month with bars."""
    idx = bars.index
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        idx = idx[idx < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if len(idx) == 0:
        return []
    keys = sorted({(int(ts.year), int(ts.month)) for ts in idx})
    out: List[Tuple[int, int, pd.Timestamp, pd.Timestamp]] = []
    for year, month in keys:
        t0 = pd.Timestamp(year=year, month=month, day=1, tz=NY)
        t1 = t0 + pd.offsets.MonthBegin(1)
        if bars[(bars.index >= t0) & (bars.index < t1)].empty:
            continue
        out.append((year, month, t0, t1))
    return out


def opening_week_slice(bars: pd.DataFrame, period_start: pd.Timestamp) -> pd.DataFrame:
    local = (
        period_start.tz_convert(NY)
        if period_start.tzinfo is not None
        else period_start.tz_localize(NY)
    )
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    w1 = monday + pd.Timedelta(days=7)
    left = max(monday, period_start)
    return bars[(bars.index >= left) & (bars.index < w1)].copy()
