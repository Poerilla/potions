"""FX / CFD market clocks for OR-profile and turtle-soup studies.

Clocks (all times America/New_York):
  - rth          : 09:30–09:45 OR, session → 15:59 (US30 / NAS100)
  - london_open  : 03:00–03:15 OR, session → 11:59 (EURUSD / USDJPY London book)
  - london_2h_or : 03:00–05:00 OR, session → 11:59 (wider London watch → arm at 05:00)
  - london_4h_or : 03:00–07:00 OR, session → 11:59 (03:00–06:59 watch → arm at 07:00)
  - ny_open      : 08:00–08:15 OR, session → 16:59 (EURUSD / USDJPY / XAU NY book)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"


@dataclass(frozen=True)
class FxClock:
    name: str
    or_start: time
    or_end: time
    session_end: time  # exclusive densify end (last bar = end - 1m)
    eod: time  # flatten / walk end
    min_session_bars: int
    min_or_bars: int = 10


CLOCKS: Dict[str, FxClock] = {
    "rth": FxClock("rth", time(9, 30), time(9, 45), time(16, 0), time(15, 59), 300),
    "london_open": FxClock("london_open", time(3, 0), time(3, 15), time(12, 0), time(11, 59), 120),
    "london_2h_or": FxClock("london_2h_or", time(3, 0), time(5, 0), time(12, 0), time(11, 59), 240, min_or_bars=60),
    "london_4h_or": FxClock("london_4h_or", time(3, 0), time(7, 0), time(12, 0), time(11, 59), 300, min_or_bars=120),
    "ny_open": FxClock("ny_open", time(8, 0), time(8, 15), time(17, 0), time(16, 59), 200),
}


@dataclass(frozen=True)
class FxMarket:
    key: str
    symbol: str
    path: Path
    clock: FxClock
    tick: float
    point_value: float  # USD per 1.0 price point per 1 unit
    fee_per_unit: float = 0.0


FX_MARKETS: Dict[str, FxMarket] = {
    "us30": FxMarket("us30", "US30", REPO / "fx" / "us30_1m.csv", CLOCKS["rth"], 1.0, 1.0),
    "nas100": FxMarket("nas100", "NAS100", REPO / "fx" / "nas100_1m.csv", CLOCKS["rth"], 0.1, 1.0),
    "eurusd_london": FxMarket(
        "eurusd_london", "EURUSD", REPO / "fx" / "eurusd_1m.csv", CLOCKS["london_open"], 0.00001, 100000.0
    ),
    "eurusd_ny": FxMarket(
        "eurusd_ny", "EURUSD", REPO / "fx" / "eurusd_1m.csv", CLOCKS["ny_open"], 0.00001, 100000.0
    ),
    "usdjpy_london": FxMarket(
        "usdjpy_london", "USDJPY", REPO / "fx" / "usdjpy_1m.csv", CLOCKS["london_open"], 0.001, 1000.0
    ),
    "usdjpy_ny": FxMarket(
        "usdjpy_ny", "USDJPY", REPO / "fx" / "usdjpy_1m.csv", CLOCKS["ny_open"], 0.001, 1000.0
    ),
    "xauusd_ny": FxMarket(
        "xauusd_ny", "XAUUSD", REPO / "fx" / "xauusd_1m.csv", CLOCKS["ny_open"], 0.01, 1.0
    ),
}


def session_minute_index(session_day: date, clock: FxClock) -> pd.DatetimeIndex:
    start = pd.Timestamp(datetime.combine(session_day, clock.or_start), tz=NY)
    end = pd.Timestamp(datetime.combine(session_day, clock.session_end), tz=NY) - pd.Timedelta(minutes=1)
    if end < start:
        return pd.DatetimeIndex([])
    return pd.date_range(start=start, end=end, freq="1min")


def session_bars(
    df: Optional[pd.DataFrame],
    session_day: date,
    clock: FxClock,
    *,
    dense: bool = True,
) -> pd.DataFrame:
    """Filter (and optionally densify) bars to the market's session window."""
    if df is None or df.empty:
        return pd.DataFrame()
    if not dense:
        return df[
            df.index.map(
                lambda ts: ts.date() == session_day
                and ts.time() >= clock.or_start
                and ts.time() < clock.session_end
            )
        ].sort_index()

    grid = session_minute_index(session_day, clock)
    if len(grid) == 0:
        return pd.DataFrame()
    day = df[
        df.index.map(
            lambda ts: ts.date() == session_day
            and ts.time() >= clock.or_start
            and ts.time() < clock.session_end
        )
    ].sort_index()
    if day.empty:
        return pd.DataFrame(index=grid, columns=["open", "high", "low", "close", "volume"])
    cols = ["open", "high", "low", "close"]
    if "volume" not in day.columns:
        day = day.copy()
        day["volume"] = 0.0
    dense_df = day.reindex(grid)
    first_close = None
    for ts in grid:
        if pd.notna(dense_df.at[ts, "close"]):
            first_close = float(dense_df.at[ts, "close"])
            break
    if first_close is None:
        return pd.DataFrame(index=grid, columns=["open", "high", "low", "close", "volume"])
    prev = first_close
    for ts in grid:
        if pd.notna(dense_df.at[ts, "close"]):
            prev = float(dense_df.at[ts, "close"])
            continue
        dense_df.at[ts, "open"] = prev
        dense_df.at[ts, "high"] = prev
        dense_df.at[ts, "low"] = prev
        dense_df.at[ts, "close"] = prev
        dense_df.at[ts, "volume"] = 0.0
    dense_df["volume"] = dense_df["volume"].fillna(0.0)
    return dense_df


def load_market_gby(mkt: FxMarket) -> Dict[date, pd.DataFrame]:
    return load_fx_1m_by_ny_date(mkt.path.resolve(), mkt.symbol)
