#!/usr/bin/env python3
"""
London sweep → **tier‑1 limit at London L/H** → **then** inside‑box child adds (5m closes); split stops; TP opposing corner.

- **Tier‑1:** resting limit at **LdnL** (Long) or **LdnH** (Short), live from the sweep bar timestamp.
- **Adds (≤2):** qualifying **green/red** inside‑box **5m** bars **after** the sweep, limits at closes (unchanged).

Stops: tier‑1 uses **same wide SL as v2e** (Ldn range width below L / above H). **Adds** (children)
use **boundary** stops (LdnL for long children, LdnH for short children). **TP:** opposing London
corner for full exit. Up to **3** contracts (tier‑1 + up to 2 child limits). RT fee **$1.50** per contract
per exit batch (aligned with v2b_child).

See ``build_london_sweep_charts.py --strategy child-after-sweep``.

Optional **causal ORB pierce** gate (default on): same geometry as annotator ``Opp_sweep_London_*`` but with
**London H/L from [02:00, 09:30)** only and ORB RH/RL from **9:30–9:45** on 1m — knowable at 9:45 with no lookahead.
Long path requires ``Range_low``-style pierce of ``LdnL``; Short path requires pierce of ``LdnH``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import time as dt_time
from typing import List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from sim_london_limit_scaleout import (
    DOLLARS_PER_POINT,
    SlMode,
    resolve_sl_distance,
    rth_1m,
    TICK,
)

_EPS = 1e-9
FEE_RT = 1.50
MAX_CONTRACTS = 3
ORB_LO = dt_time(9, 30)
ORB_HI = dt_time(9, 45)


def orb_rh_rl_0930_0945(df1: pd.DataFrame) -> Tuple[float, float]:
    """Opening range from 1m [09:30, 09:45) (same window as ORB charts)."""
    b = df1[df1.index.map(lambda t: ORB_LO <= t.time() < ORB_HI)]
    if b.empty:
        return float('nan'), float('nan')
    return float(b['high'].max()), float(b['low'].min())


def causal_orb_pierces_ldn_like_v2b(
    orb_rh: float,
    orb_rl: float,
    ldn_h: float,
    ldn_l: float,
    sweep_low: bool,
) -> bool:
    """
    Annotator-equivalent pierce test using **causal** London (caller must pass 02:00–09:30 H/L).

    Long-side row uses ``_ge(rl, London_L)`` → ``rl - TICK*0.1 <= London_L``.
    Short-side uses ``_le(rh, London_H)`` → ``rh + TICK*0.1 >= London_H``.
    """
    if np.isnan(orb_rh) or np.isnan(orb_rl) or np.isnan(ldn_h) or np.isnan(ldn_l):
        return False
    slack = TICK * 0.1
    if sweep_low:
        return orb_rl - slack <= float(ldn_l) + _EPS
    return orb_rh + slack >= float(ldn_h) - _EPS


def resample_5m_anchor0930(df1: pd.DataFrame) -> pd.DataFrame:
    ix0 = df1.index[0]
    anchor = ix0.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def find_first_rth_sweep_ts(
    rth: pd.DataFrame, ldn_h: float, ldn_l: float, sweep_low: bool
) -> Optional[pd.Timestamp]:
    """First RTH bar that sweeps London low (long setup) or high (short setup)."""
    for ts, b in rth.iterrows():
        h, lo = float(b['high']), float(b['low'])
        if sweep_low and lo <= ldn_l + _EPS:
            return pd.Timestamp(ts)
        if not sweep_low and h >= ldn_h - _EPS:
            return pd.Timestamp(ts)
    return None


def infer_sweep_low_first_rth_hit(
    rth: pd.DataFrame, ldn_h: float, ldn_l: float
) -> Optional[bool]:
    """
    Which London side was swept first in RTH: True = low (long path), False = high (short).
    Same-bar both-sided sweep: tie-break by distance from bar open to each level (mirrors
    ``first_rth_touch_side`` tie policy; exact tie → Short path).
    """
    if rth is None or rth.empty:
        return None
    lh, ll = float(ldn_h), float(ldn_l)
    if np.isnan(lh) or np.isnan(ll):
        return None
    for k in range(len(rth)):
        b = rth.iloc[k]
        h, lo, o = float(b['high']), float(b['low']), float(b['open'])
        hit_l = lo <= ll + _EPS
        hit_h = h >= lh - _EPS
        if not hit_l and not hit_h:
            continue
        if hit_l and not hit_h:
            return True
        if hit_h and not hit_l:
            return False
        d_h = abs(o - lh)
        d_l = abs(o - ll)
        if d_l < d_h - 1e-12:
            return True
        if d_h < d_l - 1e-12:
            return False
        return False
    return None


def _inside_strict(o: float, h: float, l: float, c: float, hi: float, lo: float) -> bool:
    return min(o, h, l, c) > lo + _EPS and max(o, h, l, c) < hi - _EPS


def is_long_child_inside(row: pd.Series, ldn_h: float, ldn_l: float) -> bool:
    o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
    if not (c > o + _EPS):
        return False
    return _inside_strict(o, h, l, c, ldn_h, ldn_l)


def is_short_child_inside(row: pd.Series, ldn_h: float, ldn_l: float) -> bool:
    o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
    if not (c < o - _EPS):
        return False
    return _inside_strict(o, h, l, c, ldn_h, ldn_l)


def collect_child_limits_after_sweep(
    bars5: pd.DataFrame,
    sweep_ts: pd.Timestamp,
    direction: Literal['Long', 'Short'],
    ldn_h: float,
    ldn_l: float,
    max_contracts: int = MAX_CONTRACTS,
) -> List[Tuple[float, pd.Timestamp]]:
    """
    Sequential qualifying 5m bars **after** sweep_ts (strict left edge > sweep_ts).
    Each tuple: (limit price = bar close, live timestamp = bar end + 5m).
    Used for **child adds** only; tier‑1 is London H/L (caller caps ``max_contracts`` at 2).
    """
    out: List[Tuple[float, pd.Timestamp]] = []
    for ts5, row in bars5.iterrows():
        if pd.Timestamp(ts5) <= sweep_ts:
            continue
        if len(out) >= max_contracts:
            break
        if direction == 'Long' and is_long_child_inside(row, ldn_h, ldn_l):
            live = pd.Timestamp(ts5) + pd.Timedelta(minutes=5)
            out.append((float(row['close']), live))
        elif direction == 'Short' and is_short_child_inside(row, ldn_h, ldn_l):
            live = pd.Timestamp(ts5) + pd.Timedelta(minutes=5)
            out.append((float(row['close']), live))
    return out


def dollars_short(entry: float, exit_px: float, n: int) -> float:
    return n * (entry - exit_px) * DOLLARS_PER_POINT


def dollars_long(entry: float, exit_px: float, n: int) -> float:
    return n * (exit_px - entry) * DOLLARS_PER_POINT


@dataclass
class LondonChildSim:
    filled: bool
    reason: str
    direction: Optional[str]
    net_dollars: float
    gross_dollars: float
    fee_dollars: float
    result_label: str
    entry_ts: Optional[pd.Timestamp]
    exit_ts: Optional[pd.Timestamp]
    entry_avg_px: float
    exit_px: float
    stop_wide: float
    stop_tight_boundary: float
    tp_px: float
    ldn_h: float
    ldn_l: float
    sweep_ts: Optional[pd.Timestamp]
    contracts_peak: int
    trade_pl_pts: float
    max_adverse_pts: float  # max excursion vs avg entry while IN (index pts); NaN if unfilled


def _sim_skip(
    ldn_h: float,
    ldn_l: float,
    *,
    reason: str,
    direction: Optional[str] = None,
    sweep_ts: Optional[pd.Timestamp] = None,
) -> LondonChildSim:
    """Placeholder row when no trade."""
    return LondonChildSim(
        filled=False,
        reason=reason,
        direction=direction,
        net_dollars=0.0,
        gross_dollars=0.0,
        fee_dollars=0.0,
        result_label=reason,
        entry_ts=None,
        exit_ts=None,
        entry_avg_px=float('nan'),
        exit_px=float('nan'),
        stop_wide=float('nan'),
        stop_tight_boundary=float('nan'),
        tp_px=float('nan'),
        ldn_h=ldn_h,
        ldn_l=ldn_l,
        sweep_ts=sweep_ts,
        contracts_peak=0,
        trade_pl_pts=0.0,
        max_adverse_pts=float('nan'),
    )


def simulate_london_child_after_sweep(
    df1: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sweep_low: Optional[bool],
    sl_points: float,
    sl_mode: SlMode = 'london_range',
    *,
    require_causal_orb_pierce: bool = True,
) -> LondonChildSim:
    """
    sweep_low True / False: Long vs Short path after that side’s London level is swept first.
    sweep_low None: infer from **first** RTH sweep of LdnL vs LdnH (same-bar tie-break as v2e).

    If ``require_causal_orb_pierce``, require ORB [9:30–9:45) vs causal London pierce aligned with ``sweep_low``
    (annotator-style geometry; ``ldn_h``/``ldn_l`` must be 02:00–09:30 box).
    """
    nan = _sim_skip(ldn_h, ldn_l, reason='no_level')
    if np.isnan(ldn_h) or np.isnan(ldn_l) or ldn_h <= ldn_l + _EPS:
        return replace(nan, reason='no_level')

    rth = rth_1m(df1)
    if rth.empty:
        return replace(nan, reason='no_rth')

    sl = sweep_low
    if sl is None:
        sl = infer_sweep_low_first_rth_hit(rth, ldn_h, ldn_l)
        if sl is None:
            return _sim_skip(ldn_h, ldn_l, reason='no_sweep')

    if require_causal_orb_pierce:
        orb_rh, orb_rl = orb_rh_rl_0930_0945(df1)
        if not causal_orb_pierces_ldn_like_v2b(orb_rh, orb_rl, float(ldn_h), float(ldn_l), sl):
            return _sim_skip(
                ldn_h,
                ldn_l,
                reason='orb_no_ldn_pierce',
                direction='Long' if sl else 'Short',
            )

    sl_dist, rsn = resolve_sl_distance(float(ldn_h), float(ldn_l), sl_mode, float(sl_points))
    if rsn == 'no_level':
        return replace(nan, reason='no_level')

    st = find_first_rth_sweep_ts(rth, ldn_h, ldn_l, sl)
    if st is None:
        return _sim_skip(ldn_h, ldn_l, reason='no_sweep')

    direction = 'Long' if sl else 'Short'
    bars5 = resample_5m_anchor0930(df1)
    if bars5.empty:
        return _sim_skip(ldn_h, ldn_l, reason='no_5m', direction=direction, sweep_ts=st)

    # Tier‑1: limit at opposite London corner (same prices as default v2e); adds: inside children after sweep.
    tier1_px = float(ldn_l) if direction == 'Long' else float(ldn_h)
    tier1_live = pd.Timestamp(st)
    children = collect_child_limits_after_sweep(
        bars5, st, direction, ldn_h, ldn_l, max_contracts=MAX_CONTRACTS - 1
    )
    limits: List[Tuple[float, pd.Timestamp]] = [(tier1_px, tier1_live)] + children

    if direction == 'Long':
        stop_wide = float(ldn_l) - sl_dist
        tp_px = float(ldn_h)
        tight_child = float(ldn_l)
    else:
        stop_wide = float(ldn_h) + sl_dist
        tp_px = float(ldn_l)
        tight_child = float(ldn_h)

    entries: List[float] = []
    fill_times: List[pd.Timestamp] = []
    pending_limits: List[Tuple[float, pd.Timestamp]] = list(limits)
    gross_dollars_acc = 0.0
    realized_fee_units = 0
    max_contracts_in_leg = 0
    phase = 'ARMED'
    trade_done = False
    exit_ts: Optional[pd.Timestamp] = None
    exit_px = float('nan')
    res_lab = ''
    tier1_entry = float('nan')
    mae_pts = 0.0

    for ts, bar in rth.iterrows():
        ts = pd.Timestamp(ts)
        h, lo = float(bar['high']), float(bar['low'])

        if phase == 'ARMED' and pending_limits:
            lim_px, live_ts = pending_limits[0]
            if ts >= live_ts:
                did = False
                if direction == 'Long' and lo <= lim_px + _EPS:
                    entries.append(lim_px)
                    fill_times.append(ts)
                    tier1_entry = lim_px
                    pending_limits.pop(0)
                    phase = 'IN'
                    max_contracts_in_leg = len(entries)
                    did = True
                elif direction == 'Short' and h >= lim_px - _EPS:
                    entries.append(lim_px)
                    fill_times.append(ts)
                    tier1_entry = lim_px
                    pending_limits.pop(0)
                    phase = 'IN'
                    max_contracts_in_leg = len(entries)
                    did = True
                if did:
                    pass

        if phase != 'IN' or trade_done:
            continue

        while not trade_done:
            closed = False
            if direction == 'Long':
                if h >= tp_px - _EPS:
                    n = len(entries)
                    gross_dollars_acc += sum(dollars_long(e, tp_px, 1) for e in entries)
                    exit_px, exit_ts, res_lab = tp_px, ts, 'Win'
                    realized_fee_units += n
                    closed = trade_done = True
                elif lo <= stop_wide + _EPS:
                    n = len(entries)
                    gross_dollars_acc += sum(dollars_long(e, stop_wide, 1) for e in entries)
                    exit_px, exit_ts, res_lab = stop_wide, ts, 'Loss'
                    realized_fee_units += n
                    closed = trade_done = True
                elif len(entries) > 1 and lo <= tight_child + _EPS and lo > stop_wide + _EPS:
                    for e in entries[1:]:
                        gross_dollars_acc += dollars_long(e, tight_child, 1)
                    realized_fee_units += len(entries) - 1
                    entries = entries[:1]
                    pending_limits.clear()
                    max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                    continue
            else:
                if lo <= tp_px + _EPS:
                    n = len(entries)
                    gross_dollars_acc += sum(dollars_short(e, tp_px, 1) for e in entries)
                    exit_px, exit_ts, res_lab = tp_px, ts, 'Win'
                    realized_fee_units += n
                    closed = trade_done = True
                elif h >= stop_wide - _EPS:
                    n = len(entries)
                    gross_dollars_acc += sum(dollars_short(e, stop_wide, 1) for e in entries)
                    exit_px, exit_ts, res_lab = stop_wide, ts, 'Loss'
                    realized_fee_units += n
                    closed = trade_done = True
                elif len(entries) > 1 and h >= tight_child - _EPS and h < stop_wide - _EPS:
                    for e in entries[1:]:
                        gross_dollars_acc += dollars_short(e, tight_child, 1)
                    realized_fee_units += len(entries) - 1
                    entries = entries[:1]
                    pending_limits.clear()
                    max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                    continue

            if closed:
                break

            progressed = False
            while pending_limits:
                lim_px, live_ts = pending_limits[0]
                if ts < live_ts:
                    break
                did = False
                if direction == 'Long' and lo <= lim_px + _EPS:
                    entries.append(lim_px)
                    fill_times.append(ts)
                    pending_limits.pop(0)
                    max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                    did = True
                    progressed = True
                elif direction == 'Short' and h >= lim_px - _EPS:
                    entries.append(lim_px)
                    fill_times.append(ts)
                    pending_limits.pop(0)
                    max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                    did = True
                    progressed = True
                if not did:
                    break

            if trade_done:
                break
            if not progressed:
                break

        if phase == 'IN' and entries:
            avg_e = sum(entries) / len(entries)
            if direction == 'Long':
                mae_pts = max(mae_pts, max(0.0, avg_e - lo))
            else:
                mae_pts = max(mae_pts, max(0.0, h - avg_e))

        if trade_done:
            break

    if phase == 'IN' and entries and not trade_done:
        eod = float(rth.iloc[-1]['close'])
        exit_ts = pd.Timestamp(rth.index[-1])
        avg_e = sum(entries) / len(entries)
        if direction == 'Long':
            res_lab = 'EOD-Win' if eod > avg_e else 'EOD-Loss'
            gross_dollars_acc += sum(dollars_long(e, eod, 1) for e in entries)
        else:
            res_lab = 'EOD-Win' if eod < avg_e else 'EOD-Loss'
            gross_dollars_acc += sum(dollars_short(e, eod, 1) for e in entries)
        exit_px = eod
        realized_fee_units += len(entries)
        trade_done = True

    if phase != 'IN' or not entries or exit_ts is None:
        rs = 'no_fill' if phase == 'ARMED' else 'incomplete'
        base = _sim_skip(ldn_h, ldn_l, reason=rs, direction=direction, sweep_ts=st)
        return replace(
            base,
            stop_wide=stop_wide,
            stop_tight_boundary=tight_child,
            tp_px=tp_px,
            contracts_peak=max_contracts_in_leg,
            max_adverse_pts=float('nan'),
        )

    fee_dollars = FEE_RT * realized_fee_units
    net = gross_dollars_acc - fee_dollars
    trade_pl_pts = gross_dollars_acc / DOLLARS_PER_POINT if DOLLARS_PER_POINT else 0.0

    return LondonChildSim(
        filled=True,
        reason='ok',
        direction=direction,
        net_dollars=round(net, 2),
        gross_dollars=round(gross_dollars_acc, 2),
        fee_dollars=round(fee_dollars, 2),
        result_label=res_lab,
        entry_ts=fill_times[0],
        exit_ts=exit_ts,
        entry_avg_px=sum(entries) / len(entries),
        exit_px=exit_px,
        stop_wide=stop_wide,
        stop_tight_boundary=tight_child,
        tp_px=tp_px,
        ldn_h=ldn_h,
        ldn_l=ldn_l,
        sweep_ts=st,
        contracts_peak=max_contracts_in_leg,
        trade_pl_pts=round(trade_pl_pts, 6),
        max_adverse_pts=round(mae_pts, 6),
    )

