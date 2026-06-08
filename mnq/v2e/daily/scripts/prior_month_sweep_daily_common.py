"""Shared helpers: MNQ daily bars + prior calendar month high/low (see plot_daily_prior_month_levels)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

MNQ_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DAILY_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
SYMBOL_PREFIX = 'MNQ'
_EPS = 1e-12


def load_mnq_front_daily(dbn: Path) -> pd.DataFrame:
    """Daily MNQ: highest-volume symbol per calendar day."""
    import databento as db

    store = db.DBNStore.from_file(str(dbn))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(SYMBOL_PREFIX)].copy()
    df['d'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('d')['volume'].idxmax()]
    out = fm.set_index('d').sort_index()
    return out[['open', 'high', 'low', 'close', 'volume', 'symbol']].copy()


def monthly_high_low(daily: pd.DataFrame) -> pd.DataFrame:
    s = daily.copy()
    s['_y'] = pd.DatetimeIndex(s.index).year
    s['_m'] = pd.DatetimeIndex(s.index).month
    return s.groupby(['_y', '_m'], sort=True).agg(m_high=('high', 'max'), m_low=('low', 'min'))


def _prev_calendar_month(y: int, m: int) -> tuple[int, int]:
    if m <= 1:
        return y - 1, 12
    return y, m - 1


def prior_month_low_high_for_day(d: date, monthly: pd.DataFrame) -> tuple[float, float] | None:
    py, pm = _prev_calendar_month(d.year, d.month)
    if (py, pm) not in set(monthly.index):
        return None
    row = monthly.loc[(py, pm)]
    return float(row['m_low']), float(row['m_high'])


def month_day_indices(dates: list[date]) -> dict[tuple[int, int], tuple[int, int]]:
    """Map (year, month) -> (first_idx, last_idx) inclusive."""
    by_m: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, d in enumerate(dates):
        by_m[(d.year, d.month)].append(i)
    out = {}
    for ym, idxs in by_m.items():
        sorted_i = sorted(idxs)
        out[ym] = (sorted_i[0], sorted_i[-1])
    return out


def pick_breaker_daily_long(
    dates: list[date],
    highs: list[float],
    lows: list[float],
    month_y: int,
    month_m: int,
    month_start_idx: int,
    sh_idx: int,
) -> tuple[float, float, int] | None:
    """Last strict swing high through SH day + next row (may spill into next month, like 5m-after-bucket)."""
    swings: list[tuple[int, float, float]] = []
    lo_k = max(month_start_idx + 1, 1)
    for k in range(lo_k, len(highs) - 1):
        if k > sh_idx + 1:
            break
        if highs[k] <= highs[k - 1] + _EPS or highs[k] <= highs[k + 1] + _EPS:
            continue
        if not in_month(dates[k], month_y, month_m):
            if k != sh_idx + 1:
                continue
        swings.append((k, float(highs[k]), float(lows[k])))
    if not swings:
        return None
    k, bh, bl = swings[-1]
    return bh, bl, k


def pick_breaker_daily_short(
    dates: list[date],
    highs: list[float],
    lows: list[float],
    month_y: int,
    month_m: int,
    month_start_idx: int,
    sh_idx: int,
) -> tuple[float, float, int] | None:
    """Last strict swing low through SH day + next row."""
    swings: list[tuple[int, float, float]] = []
    lo_k = max(month_start_idx + 1, 1)
    for k in range(lo_k, len(lows) - 1):
        if k > sh_idx + 1:
            break
        if lows[k] + _EPS >= lows[k - 1] or lows[k] + _EPS >= lows[k + 1]:
            continue
        if not in_month(dates[k], month_y, month_m):
            if k != sh_idx + 1:
                continue
        swings.append((k, float(highs[k]), float(lows[k])))
    if not swings:
        return None
    k, bh, bl = swings[-1]
    return bh, bl, k


def in_month(d: date, y: int, m: int) -> bool:
    return d.year == y and d.month == m
