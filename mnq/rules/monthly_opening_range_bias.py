"""
Monthly structure filter for **opening-range breakout** direction (v2b-style).

Uses **completed calendar months** only (causal at the start of each session month).

**Rule (abbreviated)**

1. **Bullish month:** During the **prior** calendar month, price **took out** the **high**
   of the month **before that** *and* the prior month **closed above** that older high →
   **long ORB only** for the current month.

2. **Bearish month:** Prior month **took out** the **low** of two months ago *and* closed
   **below** it → **short ORB only**.

3. **Inside close:** Prior month's **close** lies **inside** the range of two months ago
   (between its low and high inclusive). Split the **prior month's own** range into two
   halves: close in the **bottom** half → **long ORB only**; **top** half → **short ORB only**.

4. Any missing history → ``insufficient_data`` (no direction allowed).

*Took out* is implemented as **monthly high strictly above** / **monthly low strictly below**
the reference month's extreme (MNQ tick-aware epsilon).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Set

import pandas as pd

Bucket = Literal[
    'bullish_break',
    'bearish_break',
    'hemisphere_long',
    'hemisphere_short',
    'ambiguous',
    'insufficient_data',
]

_TICK = 0.25
_EPS = _TICK * 0.01


@dataclass(frozen=True)
class MonthlyOrbBiasResult:
    """Allowed v2b breakout directions for sessions in the session day's calendar month."""

    allowed_long: bool
    allowed_short: bool
    bucket: Bucket
    session_date: date
    """Calendar month of session (year, month)."""
    session_month: tuple[int, int]
    """Prior completed calendar month used for classification (year, month)."""
    prior_month: tuple[int, int] | None = None


def _prev_cal_month(y: int, m: int) -> tuple[int, int]:
    if m <= 1:
        return y - 1, 12
    return y, m - 1


def _month_slice(daily: pd.DataFrame, y: int, m: int) -> pd.DataFrame:
    ts = pd.DatetimeIndex(pd.to_datetime(daily.index))
    return daily.loc[(ts.year == y) & (ts.month == m)].copy()


def _month_stats(seg: pd.DataFrame) -> tuple[float, float, float] | None:
    if seg is None or seg.empty:
        return None
    hi = float(seg['high'].max())
    lo = float(seg['low'].min())
    cl = float(seg['close'].iloc[-1])
    return hi, lo, cl


def monthly_orb_bias_for_session_date(session_day: date, daily: pd.DataFrame) -> MonthlyOrbBiasResult:
    """
    Classify allowed ORB breakout directions for trades **on** ``session_day``.

    ``daily`` must include enough history for the **two completed months strictly before**
    the calendar month containing ``session_day`` (i.e. prior month M-1 and M-2 vs session
    month's M).
    """
    cy, cm = session_day.year, session_day.month

    py, pm = _prev_cal_month(cy, cm)
    ppy, ppm = _prev_cal_month(py, pm)

    prev_seg = _month_slice(daily, py, pm)
    prev2_seg = _month_slice(daily, ppy, ppm)
    st_prev = _month_stats(prev_seg)
    st_prev2 = _month_stats(prev2_seg)

    base_kw = dict(session_date=session_day, session_month=(cy, cm), prior_month=(py, pm))

    if st_prev is None or st_prev2 is None:
        return MonthlyOrbBiasResult(
            allowed_long=False,
            allowed_short=False,
            bucket='insufficient_data',
            **base_kw,
        )

    high_prev, low_prev, close_prev = st_prev
    high_prev2, low_prev2, _close_prev2 = st_prev2

    took_high = high_prev > high_prev2 + _EPS
    closed_above = close_prev > high_prev2 + _EPS
    if took_high and closed_above:
        return MonthlyOrbBiasResult(
            allowed_long=True,
            allowed_short=False,
            bucket='bullish_break',
            **base_kw,
        )

    took_low = low_prev < low_prev2 - _EPS
    closed_below = close_prev < low_prev2 - _EPS
    if took_low and closed_below:
        return MonthlyOrbBiasResult(
            allowed_long=False,
            allowed_short=True,
            bucket='bearish_break',
            **base_kw,
        )

    inside = (close_prev >= low_prev2 - _EPS) and (close_prev <= high_prev2 + _EPS)
    if inside:
        mid = (high_prev + low_prev) / 2.0
        if close_prev <= mid + _EPS:
            return MonthlyOrbBiasResult(
                allowed_long=True,
                allowed_short=False,
                bucket='hemisphere_long',
                **base_kw,
            )
        return MonthlyOrbBiasResult(
            allowed_long=False,
            allowed_short=True,
            bucket='hemisphere_short',
            **base_kw,
        )

    return MonthlyOrbBiasResult(
        allowed_long=False,
        allowed_short=False,
        bucket='ambiguous',
        **base_kw,
    )


def allowed_trade_directions(result: MonthlyOrbBiasResult) -> Set[str]:
    """{'Long'} / {'Short'} / empty set."""
    out: Set[str] = set()
    if result.allowed_long:
        out.add('Long')
    if result.allowed_short:
        out.add('Short')
    return out
