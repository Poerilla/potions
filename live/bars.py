from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd

NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def rth_minute_index(session_day: date, tz: str = NY) -> pd.DatetimeIndex:
    """Return the dense 1m RTH grid 09:30–15:59 NY for one session."""
    start = pd.Timestamp(datetime.combine(session_day, RTH_OPEN), tz=tz)
    end = pd.Timestamp(datetime.combine(session_day, RTH_CLOSE), tz=tz) - pd.Timedelta(minutes=1)
    return pd.date_range(start=start, end=end, freq="1min")


def dense_rth_1m_bars(df: Optional[pd.DataFrame], session_day: date) -> pd.DataFrame:
    """Forward-fill sparse Databento 1m rows onto a dense RTH grid.

    Missing minutes get ``open=high=low=close=prev_close`` and ``volume=0``.
    """
    grid = rth_minute_index(session_day)
    if df is None or df.empty:
        return pd.DataFrame(index=grid, columns=["open", "high", "low", "close", "volume"])

    day = df[
        df.index.map(
            lambda ts: ts.date() == session_day
            and ts.time() >= RTH_OPEN
            and ts.time() < RTH_CLOSE
        )
    ].sort_index()
    if day.empty:
        return pd.DataFrame(index=grid, columns=["open", "high", "low", "close", "volume"])

    cols = ["open", "high", "low", "close"]
    for col in cols:
        if col not in day.columns:
            raise ValueError("1m frame missing column %s" % col)
    if "volume" not in day.columns:
        day = day.copy()
        day["volume"] = 0.0

    dense = day.reindex(grid)
    first_close = None
    for ts in grid:
        if pd.notna(dense.at[ts, "close"]):
            first_close = float(dense.at[ts, "close"])
            break
    if first_close is None:
        return pd.DataFrame(index=grid, columns=["open", "high", "low", "close", "volume"])

    prev_close = first_close
    for ts in grid:
        if pd.notna(dense.at[ts, "close"]):
            prev_close = float(dense.at[ts, "close"])
            continue
        dense.at[ts, "open"] = prev_close
        dense.at[ts, "high"] = prev_close
        dense.at[ts, "low"] = prev_close
        dense.at[ts, "close"] = prev_close
        dense.at[ts, "volume"] = 0.0

    dense["volume"] = dense["volume"].fillna(0.0)
    return dense


def rth_bars(df: Optional[pd.DataFrame], session_day: date, *, dense: bool = True) -> pd.DataFrame:
    """Filter to RTH and optionally densify to a full 390-minute grid."""
    if df is None or df.empty:
        return pd.DataFrame()
    if dense:
        return dense_rth_1m_bars(df, session_day)
    return df[
        df.index.map(
            lambda ts: ts.date() == session_day
            and ts.time() >= RTH_OPEN
            and ts.time() < RTH_CLOSE
        )
    ].sort_index()
