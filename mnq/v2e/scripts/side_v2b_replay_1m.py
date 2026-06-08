#!/usr/bin/env python3
"""
Causal replay of **v2b** (step2_preplaced_stops) OCO side on 1m data — no CSV.

Logic matches `potions/scripts/step2_preplaced_stops.py`:
  - ORB: 9:30 ET for *open_range_minutes* (default 15 → through 9:44 bar), H/L of that window.
  - At range end, OCO: buy stop @ RH+1 tick, sell stop @ RL−1 tick.
  - First 1m bar (from range_end onward) that triggers either stop sets the **side**;
    same-bar both-hit tie-break: bar open vs ORB midpoint (same as step2).

`side_v2b_replay_1m` returns the **first** OCO fill only (bracket first leg), not
the second re-armed trade — for pairing with v2e London execution from **after** that bar.
"""
from __future__ import annotations

from datetime import time
from typing import Literal, Optional, Tuple

import pandas as pd

from sim_london_limit_scaleout import TICK  # noqa: E402  # MNQ 0.25

RTH_O = time(9, 30)
RTH_C = time(16, 0)
DEFAULT_ORB_MIN = 15


def open_range_end_time(minutes: int) -> time:
    """ORB end: 9:30 + *minutes* (first trade bar has this time = step2)."""
    t = pd.Timestamp('2000-01-01 09:30:00') + pd.Timedelta(minutes=minutes)
    return t.time()


def rth_bars_step2_style(day_1m: pd.DataFrame) -> pd.DataFrame:
    """RTH 9:30–16:00 with ``t`` column; same window as step2 MNQ after front-month pick."""
    b = day_1m[day_1m.index.map(lambda x: RTH_O <= x.time() < RTH_C)].copy()
    if b.empty:
        return b
    b = b.assign(t=b.index.map(lambda x: x.time()))
    return b.sort_index()


def v2b_first_oco_fill(
    trade_bars: pd.DataFrame,
    rh: float,
    rl: float,
    tick: float,
) -> Optional[Tuple[Literal['Long', 'Short'], pd.Timestamp]]:
    """
    First OCO hit only (``ARMED`` phase in ``simulate_day``), mirroring step2.

    Entry *slip* in step2 does not change which side hits first; omitted here.
    """
    long_trigger = rh + tick
    short_trigger = rl - tick
    arm_long = True
    arm_short = True
    for _, bar in trade_bars.iterrows():
        ts = bar.name
        h, l = float(bar['high']), float(bar['low'])
        o = float(bar['open'])
        long_hit = arm_long and h + 1e-9 >= long_trigger
        short_hit = arm_short and l - 1e-9 <= short_trigger
        if not long_hit and not short_hit:
            continue
        if long_hit and short_hit:
            mid = (rh + rl) / 2.0
            if o >= mid:
                return 'Long', ts
            return 'Short', ts
        if long_hit:
            return 'Long', ts
        if short_hit:
            return 'Short', ts
    return None


def rth_slice_strictly_after_oco_bar(
    rth: pd.DataFrame,
    oco_decision_bar_ts: pd.Timestamp,
) -> pd.DataFrame:
    """
    RTH 1m bars with index **strictly after** the bar where the v2b OCO first hit.

    v2e London limit evaluation does not use the OCO bar itself (1m path ordering).
    """
    if rth.empty:
        return rth
    return rth.loc[rth.index > oco_decision_bar_ts]


def side_v2b_replay_1m(
    day_1m: pd.DataFrame,
    tick: float = TICK,
    open_range_minutes: int = DEFAULT_ORB_MIN,
) -> Optional[Tuple[Literal['Long', 'Short'], pd.Timestamp, float, float, float]]:
    """
    Returns ``(side, first_oco_bar_ts, orb_rh, orb_rl, orb_range)`` or ``None`` if
    there is no RTH data, a flat ORB, or no OCO fill by end of *trade_bars* session.
    """
    day_rth = rth_bars_step2_style(day_1m)
    if day_rth.empty:
        return None
    range_end = open_range_end_time(open_range_minutes)
    range_bars = day_rth[day_rth['t'] < range_end]
    if range_bars.empty:
        return None
    rh = float(range_bars['high'].max())
    rl = float(range_bars['low'].min())
    rv = rh - rl
    if rv <= 1e-12:
        return None
    trade_bars = day_rth[day_rth['t'] >= range_end]
    if trade_bars.empty:
        return None
    out = v2b_first_oco_fill(trade_bars, rh, rl, tick)
    if out is None:
        return None
    side, t0 = out
    return (side, t0, rh, rl, rv)
