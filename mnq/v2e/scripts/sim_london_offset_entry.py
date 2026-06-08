#!/usr/bin/env python3
"""
London sweep direction (same inference as child-after-sweep) → **single limit** entry offset from London box,
**fixed stop** in index points, **TP** at opposing causal London corner. One MNQ.

- **Long:** resting buy at ``LdnL − offset_pts``; SL at ``entry − sl_pts``; TP at ``LdnH``.
- **Short:** resting sell at ``LdnH + offset_pts``; SL at ``entry + sl_pts``; TP at ``LdnL``.

Limit arms from first sweep timestamp (same live rule as tier‑1 child sim). Optional causal ORB pierce gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from sim_london_child_after_sweep import (
    causal_orb_pierces_ldn_like_v2b,
    find_first_rth_sweep_ts,
    infer_sweep_low_first_rth_hit,
    orb_rh_rl_0930_0945,
)
from sim_london_limit_scaleout import DOLLARS_PER_POINT, rth_1m

_EPS = 1e-9
FEE_RT = 1.50  # per MNQ round-trip exit batch (same convention as child sim)


def dollars_long(entry: float, exit_px: float, n: int) -> float:
    return n * (exit_px - entry) * DOLLARS_PER_POINT


def dollars_short(entry: float, exit_px: float, n: int) -> float:
    return n * (entry - exit_px) * DOLLARS_PER_POINT


@dataclass
class OffsetEntrySim:
    filled: bool
    reason: str
    direction: Optional[str]
    net_dollars: float
    result_label: str
    entry_px: float
    exit_px: float
    entry_ts: Optional[pd.Timestamp]
    exit_ts: Optional[pd.Timestamp]


def simulate_london_offset_entry(
    df1: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sweep_low: Optional[bool],
    *,
    offset_pts: float = 30.0,
    sl_pts: float = 30.0,
    require_causal_orb_pierce: bool = True,
) -> OffsetEntrySim:
    nan = OffsetEntrySim(
        filled=False,
        reason='no_level',
        direction=None,
        net_dollars=0.0,
        result_label='no_level',
        entry_px=float('nan'),
        exit_px=float('nan'),
        entry_ts=None,
        exit_ts=None,
    )
    if np.isnan(ldn_h) or np.isnan(ldn_l) or ldn_h <= ldn_l + _EPS:
        return nan

    rth = rth_1m(df1)
    if rth.empty:
        return OffsetEntrySim(
            filled=False,
            reason='no_rth',
            direction=None,
            net_dollars=0.0,
            result_label='no_rth',
            entry_px=float('nan'),
            exit_px=float('nan'),
            entry_ts=None,
            exit_ts=None,
        )

    sl = sweep_low
    if sl is None:
        sl = infer_sweep_low_first_rth_hit(rth, ldn_h, ldn_l)
        if sl is None:
            return OffsetEntrySim(
                filled=False,
                reason='no_sweep',
                direction=None,
                net_dollars=0.0,
                result_label='no_sweep',
                entry_px=float('nan'),
                exit_px=float('nan'),
                entry_ts=None,
                exit_ts=None,
            )

    if require_causal_orb_pierce:
        orb_rh, orb_rl = orb_rh_rl_0930_0945(df1)
        if not causal_orb_pierces_ldn_like_v2b(orb_rh, orb_rl, float(ldn_h), float(ldn_l), sl):
            return OffsetEntrySim(
                filled=False,
                reason='orb_no_ldn_pierce',
                direction='Long' if sl else 'Short',
                net_dollars=0.0,
                result_label='orb_no_ldn_pierce',
                entry_px=float('nan'),
                exit_px=float('nan'),
                entry_ts=None,
                exit_ts=None,
            )

    st = find_first_rth_sweep_ts(rth, ldn_h, ldn_l, sl)
    if st is None:
        return OffsetEntrySim(
            filled=False,
            reason='no_sweep',
            direction='Long' if sl else 'Short',
            net_dollars=0.0,
            result_label='no_sweep',
            entry_px=float('nan'),
            exit_px=float('nan'),
            entry_ts=None,
            exit_ts=None,
        )

    direction = 'Long' if sl else 'Short'
    if direction == 'Long':
        lim_px = float(ldn_l) - float(offset_pts)
        tp_px = float(ldn_h)
    else:
        lim_px = float(ldn_h) + float(offset_pts)
        tp_px = float(ldn_l)

    phase = 'ARMED'
    entry_px = float('nan')
    entry_ts: Optional[pd.Timestamp] = None
    trade_done = False
    exit_ts: Optional[pd.Timestamp] = None
    exit_px = float('nan')
    res_lab = ''

    for ts, bar in rth.iterrows():
        ts = pd.Timestamp(ts)
        h, lo = float(bar['high']), float(bar['low'])

        if phase == 'ARMED':
            if ts < pd.Timestamp(st):
                continue
            if direction == 'Long' and lo <= lim_px + _EPS:
                entry_px = lim_px
                entry_ts = ts
                stop_px = entry_px - float(sl_pts)
                phase = 'IN'
            elif direction == 'Short' and h >= lim_px - _EPS:
                entry_px = lim_px
                entry_ts = ts
                stop_px = entry_px + float(sl_pts)
                phase = 'IN'
            else:
                continue

        if phase != 'IN' or trade_done:
            continue

        if direction == 'Long':
            if h >= tp_px - _EPS:
                exit_px, exit_ts, res_lab = tp_px, ts, 'Win'
                trade_done = True
            elif lo <= stop_px + _EPS:
                exit_px, exit_ts, res_lab = stop_px, ts, 'Loss'
                trade_done = True
        else:
            if lo <= tp_px + _EPS:
                exit_px, exit_ts, res_lab = tp_px, ts, 'Win'
                trade_done = True
            elif h >= stop_px - _EPS:
                exit_px, exit_ts, res_lab = stop_px, ts, 'Loss'
                trade_done = True

        if trade_done:
            break

    if phase == 'IN' and not trade_done and entry_ts is not None:
        eod = float(rth.iloc[-1]['close'])
        exit_ts = pd.Timestamp(rth.index[-1])
        exit_px = eod
        if direction == 'Long':
            res_lab = 'EOD-Win' if eod > entry_px else 'EOD-Loss'
        else:
            res_lab = 'EOD-Win' if eod < entry_px else 'EOD-Loss'
        trade_done = True

    if phase != 'IN' or entry_ts is None or not trade_done or exit_ts is None:
        return OffsetEntrySim(
            filled=False,
            reason='no_fill' if phase == 'ARMED' else 'incomplete',
            direction=direction,
            net_dollars=0.0,
            result_label='no_fill' if phase == 'ARMED' else 'incomplete',
            entry_px=float('nan'),
            exit_px=float('nan'),
            entry_ts=None,
            exit_ts=None,
        )

    if direction == 'Long':
        gross = dollars_long(entry_px, exit_px, 1)
    else:
        gross = dollars_short(entry_px, exit_px, 1)
    net = gross - FEE_RT

    return OffsetEntrySim(
        filled=True,
        reason='ok',
        direction=direction,
        net_dollars=round(net, 2),
        result_label=res_lab,
        entry_px=round(entry_px, 6),
        exit_px=round(exit_px, 6),
        entry_ts=entry_ts,
        exit_ts=exit_ts,
    )
