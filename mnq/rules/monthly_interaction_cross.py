"""
**Monthly interaction** cross detection — prior calendar month **high** / **low** crossed on **5 m** OHLC.

Specification matches ``case_studies/monthly_interactions/build_monthly_interactions.py``:

- Session window on ``session_day``: **[00:00, 16:00) NY** (same as chart builder).
- **Cross**: sequential scan using prior reference price (first bar’s **open**, then each bar’s **close**);
  the current bar’s **range** must bridge to the level from the reference side (see ``cross_detect_5m``).

**Oracle vs causal**

- Running crosses on the **full** 00:00–16:00 slice uses information **through session close** → **not**
  knowable at the open or at ORB completion.
- ``cross_detect_5m_through_cutoff`` restricts to 5 m bars whose **start time** is strictly **before**
  ``cutoff_ny`` on that calendar day — only data **available up to that NY clock time** (causal for
  decisions taken after the last included bar is fixed).

Daily-bar **touch** pre-filter in the chart builder (days whose settled daily range hits pm H/L) is
also backward-looking for same-day decisions; this module does **not** implement that filter.
"""
from __future__ import annotations

from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytz

NY = pytz.timezone('America/New_York')
TICK_EPS = 0.03  # sub-tick noise for MNQ quarter-points


def cross_detect_5m(bars5: pd.DataFrame, level: float) -> bool:
    """True if the session sequence crosses ``level`` (reference-to-range transitions)."""
    if bars5.empty or not np.isfinite(level):
        return False
    prev = float(bars5.iloc[0]['open'])
    for i in range(len(bars5)):
        row = bars5.iloc[i]
        h = float(row['high'])
        lo = float(row['low'])
        c = float(row['close'])
        if prev < level - TICK_EPS and h >= level - TICK_EPS:
            return True
        if prev > level + TICK_EPS and lo <= level + TICK_EPS:
            return True
        prev = c
    return False


def resample_5m_ny_window(
    day_1m: pd.DataFrame,
    session_day: date,
    *,
    t_lo: time,
    t_hi: time,
) -> pd.DataFrame:
    """Resample 1 m bars to 5 m OHLC for ``session_day`` in **[t_lo, t_hi) NY**."""
    if day_1m.empty:
        return day_1m.iloc[:0].copy()
    x = day_1m[
        day_1m.index.map(lambda t: (t.date() == session_day and t_lo <= t.time() < t_hi))
    ]
    if x.empty:
        return x
    anchor = NY.localize(datetime.combine(session_day, t_lo))
    return (
        x.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def resample_5m_midnight_to_1600(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    """[00:00, 16:00) NY — monthly-interactions chart window."""
    return resample_5m_ny_window(day_1m, session_day, t_lo=time(0, 0), t_hi=time(16, 0))


def bars5_before_ny_cutoff(bars5: pd.DataFrame, cutoff: time) -> pd.DataFrame:
    """Keep 5 m bars whose **left edge** time is strictly before ``cutoff`` (NY wall clock)."""
    if bars5.empty:
        return bars5

    def ny_time(ts: pd.Timestamp) -> time:
        if ts.tzinfo is None:
            return ts.time()
        return ts.tz_convert(NY).time()

    return bars5[bars5.index.map(lambda ts: ny_time(pd.Timestamp(ts)) < cutoff)]


def cross_detect_5m_through_cutoff(
    bars5_full_session: pd.DataFrame,
    level: float,
    cutoff_ny: time,
) -> bool:
    """Cross detection using only bars strictly **before** ``cutoff_ny`` (causal prefix)."""
    return cross_detect_5m(bars5_before_ny_cutoff(bars5_full_session, cutoff_ny), level)


def crosses_prior_month_levels(
    bars5: pd.DataFrame,
    pm_high: float,
    pm_low: float,
) -> tuple[bool, bool]:
    """Return ``(cross_high, cross_low)`` for the given 5 m slice."""
    cross_h = np.isfinite(pm_high) and cross_detect_5m(bars5, float(pm_high))
    cross_l = np.isfinite(pm_low) and cross_detect_5m(bars5, float(pm_low))
    return cross_h, cross_l


def crosses_prior_month_levels_through_cutoff(
    bars5_full_session: pd.DataFrame,
    pm_high: float,
    pm_low: float,
    cutoff_ny: time,
) -> tuple[bool, bool]:
    """Causal variant: crosses using prefix of ``bars5_full_session`` before ``cutoff_ny``."""
    prefix = bars5_before_ny_cutoff(bars5_full_session, cutoff_ny)
    return crosses_prior_month_levels(prefix, pm_high, pm_low)
