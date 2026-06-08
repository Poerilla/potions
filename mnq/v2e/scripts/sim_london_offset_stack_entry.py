#!/usr/bin/env python3
"""
London sweep + offset limits at ``LdnL−offset`` / ``LdnH+offset`` → **stack** up to ``max_contracts``
resting limits all at the **same** entry price. Same fixed SL for every fill (``entry ± sl_pts``).

Adds (queued resting limits at ``lim_px``):
  - **Long:** each **1m bar close** strictly above ``lim_px`` queues **one** additional limit,
    until ``filled + pending_queue == max_contracts``.
  - **Short:** symmetric — each close strictly **below** ``lim_px`` queues one more sell limit.

Queued limits fill FIFO when price trades through ``lim_px`` after they are queued (active **next** bar onward;
within-bar: TP/SL checked first, then fills).

**Cancel:** any unfilled queued limits are cleared when **TP** trades (full exit at TP). Same at SL/EOD.

Optional causal ORB pierce gate matches ``simulate_london_offset_entry``.
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
FEE_RT = 1.50


def dollars_long(entry: float, exit_px: float, n: int) -> float:
    return n * (exit_px - entry) * DOLLARS_PER_POINT


def dollars_short(entry: float, exit_px: float, n: int) -> float:
    return n * (entry - exit_px) * DOLLARS_PER_POINT


@dataclass
class OffsetStackSim:
    filled: bool
    reason: str
    direction: Optional[str]
    net_dollars: float
    gross_dollars: float
    fee_dollars: float
    result_label: str
    lim_px: float
    contracts_peak: int
    exit_px: float
    exit_ts: Optional[pd.Timestamp]
    entry_ts: Optional[pd.Timestamp]


def simulate_london_offset_stack_entry(
    df1: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sweep_low: Optional[bool],
    *,
    offset_pts: float = 30.0,
    sl_pts: float = 30.0,
    max_contracts: int = 3,
    require_causal_orb_pierce: bool = True,
) -> OffsetStackSim:
    nan = OffsetStackSim(
        filled=False,
        reason='no_level',
        direction=None,
        net_dollars=0.0,
        gross_dollars=0.0,
        fee_dollars=0.0,
        result_label='no_level',
        lim_px=float('nan'),
        contracts_peak=0,
        exit_px=float('nan'),
        exit_ts=None,
        entry_ts=None,
    )
    if max_contracts < 1:
        return nan

    if np.isnan(ldn_h) or np.isnan(ldn_l) or ldn_h <= ldn_l + _EPS:
        return nan

    rth = rth_1m(df1)
    if rth.empty:
        return OffsetStackSim(
            filled=False,
            reason='no_rth',
            direction=None,
            net_dollars=0.0,
            gross_dollars=0.0,
            fee_dollars=0.0,
            result_label='no_rth',
            lim_px=float('nan'),
            contracts_peak=0,
            exit_px=float('nan'),
            exit_ts=None,
            entry_ts=None,
        )

    sl = sweep_low
    if sl is None:
        sl = infer_sweep_low_first_rth_hit(rth, ldn_h, ldn_l)
        if sl is None:
            return OffsetStackSim(
                filled=False,
                reason='no_sweep',
                direction=None,
                net_dollars=0.0,
                gross_dollars=0.0,
                fee_dollars=0.0,
                result_label='no_sweep',
                lim_px=float('nan'),
                contracts_peak=0,
                exit_px=float('nan'),
                exit_ts=None,
                entry_ts=None,
            )

    if require_causal_orb_pierce:
        orb_rh, orb_rl = orb_rh_rl_0930_0945(df1)
        if not causal_orb_pierces_ldn_like_v2b(orb_rh, orb_rl, float(ldn_h), float(ldn_l), sl):
            return OffsetStackSim(
                filled=False,
                reason='orb_no_ldn_pierce',
                direction='Long' if sl else 'Short',
                net_dollars=0.0,
                gross_dollars=0.0,
                fee_dollars=0.0,
                result_label='orb_no_ldn_pierce',
                lim_px=float('nan'),
                contracts_peak=0,
                exit_px=float('nan'),
                exit_ts=None,
                entry_ts=None,
            )

    st = find_first_rth_sweep_ts(rth, ldn_h, ldn_l, sl)
    if st is None:
        return OffsetStackSim(
            filled=False,
            reason='no_sweep',
            direction='Long' if sl else 'Short',
            net_dollars=0.0,
            gross_dollars=0.0,
            fee_dollars=0.0,
            result_label='no_sweep',
            lim_px=float('nan'),
            contracts_peak=0,
            exit_px=float('nan'),
            exit_ts=None,
            entry_ts=None,
        )

    direction = 'Long' if sl else 'Short'
    if direction == 'Long':
        lim_px = float(ldn_l) - float(offset_pts)
        tp_px = float(ldn_h)
        stop_px = lim_px - float(sl_pts)
    else:
        lim_px = float(ldn_h) + float(offset_pts)
        tp_px = float(ldn_l)
        stop_px = lim_px + float(sl_pts)

    phase = 'ARMED'
    entries = 0  # filled contracts (all at lim_px)
    pending_resting = 0  # FIFO queue count at lim_px (not yet filled)
    trade_done = False
    exit_ts: Optional[pd.Timestamp] = None
    exit_px = float('nan')
    res_lab = ''
    gross_acc = 0.0
    fee_units = 0
    entry_ts: Optional[pd.Timestamp] = None
    peak_c = 0

    for ts, bar in rth.iterrows():
        ts = pd.Timestamp(ts)
        h, lo = float(bar['high']), float(bar['low'])
        c = float(bar['close'])

        if phase == 'ARMED':
            if ts < pd.Timestamp(st):
                continue
            filled_here = False
            if direction == 'Long' and lo <= lim_px + _EPS:
                entries = 1
                entry_ts = ts
                peak_c = max(peak_c, entries)
                filled_here = True
            elif direction == 'Short' and h >= lim_px - _EPS:
                entries = 1
                entry_ts = ts
                peak_c = max(peak_c, entries)
                filled_here = True
            if filled_here:
                phase = 'IN'
            else:
                continue

        if phase != 'IN' or trade_done:
            continue

        n = entries

        # --- TP / SL (full position); clears pending_resting on TP ---
        if direction == 'Long':
            if h >= tp_px - _EPS:
                gross_acc += dollars_long(lim_px, tp_px, n)
                fee_units += n
                exit_px, exit_ts, res_lab = tp_px, ts, 'Win'
                pending_resting = 0
                trade_done = True
            elif lo <= stop_px + _EPS:
                gross_acc += dollars_long(lim_px, stop_px, n)
                fee_units += n
                exit_px, exit_ts, res_lab = stop_px, ts, 'Loss'
                pending_resting = 0
                trade_done = True
        else:
            if lo <= tp_px + _EPS:
                gross_acc += dollars_short(lim_px, tp_px, n)
                fee_units += n
                exit_px, exit_ts, res_lab = tp_px, ts, 'Win'
                pending_resting = 0
                trade_done = True
            elif h >= stop_px - _EPS:
                gross_acc += dollars_short(lim_px, stop_px, n)
                fee_units += n
                exit_px, exit_ts, res_lab = stop_px, ts, 'Loss'
                pending_resting = 0
                trade_done = True

        if trade_done:
            peak_c = max(peak_c, n)
            break

        # --- Fill queued resting limits at lim_px (FIFO, possibly multiple per bar) ---
        while pending_resting > 0:
            if direction == 'Long' and lo <= lim_px + _EPS:
                entries += 1
                pending_resting -= 1
                peak_c = max(peak_c, entries)
            elif direction == 'Short' and h >= lim_px - _EPS:
                entries += 1
                pending_resting -= 1
                peak_c = max(peak_c, entries)
            else:
                break

        # --- End of bar: queue one more resting limit on favorable close (cap 3 total filled+queue) ---
        if direction == 'Long' and c > lim_px + _EPS and entries + pending_resting < max_contracts:
            pending_resting += 1
        elif direction == 'Short' and c < lim_px - _EPS and entries + pending_resting < max_contracts:
            pending_resting += 1

    if phase == 'IN' and entries > 0 and not trade_done:
        eod = float(rth.iloc[-1]['close'])
        exit_ts = pd.Timestamp(rth.index[-1])
        exit_px = eod
        n = entries
        if direction == 'Long':
            res_lab = 'EOD-Win' if eod > lim_px else 'EOD-Loss'
            gross_acc += dollars_long(lim_px, eod, n)
        else:
            res_lab = 'EOD-Win' if eod < lim_px else 'EOD-Loss'
            gross_acc += dollars_short(lim_px, eod, n)
        fee_units += n
        trade_done = True
        peak_c = max(peak_c, entries)

    if phase != 'IN' or entries == 0 or exit_ts is None or not trade_done:
        return OffsetStackSim(
            filled=False,
            reason='no_fill' if phase == 'ARMED' else 'incomplete',
            direction=direction,
            net_dollars=0.0,
            gross_dollars=0.0,
            fee_dollars=0.0,
            result_label='no_fill' if phase == 'ARMED' else 'incomplete',
            lim_px=lim_px,
            contracts_peak=peak_c,
            exit_px=float('nan'),
            exit_ts=None,
            entry_ts=entry_ts,
        )

    fee_d = FEE_RT * fee_units
    net = gross_acc - fee_d

    return OffsetStackSim(
        filled=True,
        reason='ok',
        direction=direction,
        net_dollars=round(net, 2),
        gross_dollars=round(gross_acc, 2),
        fee_dollars=round(fee_d, 2),
        result_label=res_lab,
        lim_px=round(lim_px, 6),
        contracts_peak=int(peak_c),
        exit_px=round(exit_px, 6),
        exit_ts=exit_ts,
        entry_ts=entry_ts,
    )
