"""
**Pattern B (London box)** — causal identification on **completed** 1 m bars.

**London levels:** ``low`` / ``high`` over **[02:00, 09:30)** ET (fixed before RTH).

**Universe:** **[09:30, 16:00)** RTH bars only, processed **oldest → newest**. Each step sees only
the current bar’s OHLC (no future bars).

**Rules (same as ``study_london_post_open_paths_and_causal_v2e`` Pattern B):**

1. **Before** the first “envelope” bar, no bar may ``touch_low`` (``low <= London_low``).
2. **First envelope** interaction must be **clean high-only**: ``high >= London_high`` and
   **not** ``touch_low`` on that bar. A bar that touches **both** low and high is **invalid**
   (ambiguous first touch).
3. After that, find first bar **strictly after** the first-high bar whose entire range lies in
   ``[London_low, London_high]`` (**inside**).
4. After inside, find first bar with ``touch_high`` again (**second** London high).
5. From first-high bar through the second-high bar (inclusive), **no** bar may ``touch_low``.

The detector is a small state machine suitable for live replay: call ``step()`` once per new 1 m bar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum, auto
from typing import Iterable, Iterator, Literal

import pandas as pd

_EPS = 1e-9


def touch_low(lo: float, L: float) -> bool:
    return lo <= L + _EPS


def touch_high(hi: float, H: float) -> bool:
    return hi >= H - _EPS


def bar_inside(hi: float, lo: float, L: float, H: float) -> bool:
    return lo >= L - _EPS and hi <= H + _EPS


class _Phase(Enum):
    SEEK_FIRST_HIGH = auto()
    SEEK_INSIDE = auto()
    SEEK_SECOND_HIGH = auto()


@dataclass
class PatternBResult:
    """Filled when Pattern B completes on ``step()``."""

    session_day: date
    london_low: float
    london_high: float
    ts_first_high: pd.Timestamp
    ts_inside: pd.Timestamp
    ts_second_high: pd.Timestamp


class PatternBLondonCausalDetector:
    """Incremental Pattern B detector (one ``step`` per chronological RTH bar)."""

    def __init__(self, session_day: date, L: float, H: float) -> None:
        self.session_day = session_day
        self.L = float(L)
        self.H = float(H)
        self._phase = _Phase.SEEK_FIRST_HIGH
        self._idx_first_high: pd.Timestamp | None = None
        self._ts_inside: pd.Timestamp | None = None
        self.last_result: PatternBResult | None = None

    def step(self, ts: pd.Timestamp, hi: float, lo: float) -> Literal['continue', 'fail', 'done']:
        """Process one closed 1 m bar. Returns ``done`` exactly once with result in ``last_result``."""
        L, H = self.L, self.H
        tl = touch_low(lo, L)
        th = touch_high(hi, H)

        if self._phase == _Phase.SEEK_FIRST_HIGH:
            if not tl and not th:
                return 'continue'
            if tl and th:
                return 'fail'
            if tl:
                return 'fail'
            # clean high-only first envelope
            assert th
            self._idx_first_high = ts
            self._phase = _Phase.SEEK_INSIDE
            return 'continue'

        if self._phase == _Phase.SEEK_INSIDE:
            assert self._idx_first_high is not None
            if tl:
                return 'fail'
            if bar_inside(hi, lo, L, H):
                self._ts_inside = ts
                self._phase = _Phase.SEEK_SECOND_HIGH
            return 'continue'

        # SEEK_SECOND_HIGH
        assert self._idx_first_high is not None
        assert self._ts_inside is not None
        if tl:
            return 'fail'
        if touch_high(hi, H):
            assert self._ts_inside is not None
            self.last_result = PatternBResult(
                session_day=self.session_day,
                london_low=L,
                london_high=H,
                ts_first_high=self._idx_first_high,
                ts_inside=self._ts_inside,
                ts_second_high=ts,
            )
            return 'done'
        return 'continue'


def detect_pattern_b_causal_session(
    rth_bars: Iterable[tuple[pd.Timestamp, float, float]],
    session_day: date,
    L: float,
    H: float,
) -> PatternBResult | None:
    """Offline replay: feed all RTH (ts, high, low) bars; return result or None."""
    det = PatternBLondonCausalDetector(session_day, L, H)
    for ts, hi, lo in rth_bars:
        out = det.step(ts, hi, lo)
        if out == 'fail':
            return None
        if out == 'done':
            return det.last_result
    return None


def iter_rth_high_low(
    day_1m: pd.DataFrame, session_day: date, *, rth_lo, rth_hi
) -> Iterator[tuple[pd.Timestamp, float, float]]:
    for ts, row in day_1m.iterrows():
        if ts.date() != session_day:
            continue
        if not (rth_lo <= ts.time() < rth_hi):
            continue
        yield ts, float(row['high']), float(row['low'])


def batch_equivalent_high_double_path(
    bars: list[tuple[float, float]], L: float, H: float
) -> bool:
    """Matches ``study_london_post_open_paths_and_causal_v2e.pattern_high_only_double_high``."""
    high1: int | None = None
    for i, (hi, lo) in enumerate(bars):
        tl = touch_low(lo, L)
        th = touch_high(hi, H)
        if not tl and not th:
            continue
        if th and not tl:
            high1 = i
            break
        return False
    else:
        return False

    assert high1 is not None
    for i in range(high1):
        if touch_low(bars[i][1], L):
            return False

    inside_k: int | None = None
    for k in range(high1 + 1, len(bars)):
        hi_k, lo_k = bars[k]
        if touch_low(lo_k, L):
            return False
        if bar_inside(hi_k, lo_k, L, H):
            inside_k = k
            break
    else:
        return False

    assert inside_k is not None
    for m in range(inside_k + 1, len(bars)):
        hi_m, lo_m = bars[m]
        if touch_low(lo_m, L):
            return False
        if touch_high(hi_m, H):
            return True
    return False
