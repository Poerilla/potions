#!/usr/bin/env python3
"""
v2b (**pre-placed OCO stops**, canonical ``scripts/step2_preplaced_stops.py``) +
optional **child** scale-in limits on **5 m** qualifying bars.

Tier-1 (same as README / step2 MNQ):
  At range end (default 9:45), stops rest at **buy stop RH+tick** / **sell stop RL−tick** (OCO).
  Fill price with **slip_ticks** slippage beyond trigger. Bracket: TP **RH+Range** / **RL−Range**,
  stop **opposite OR boundary** (RL long / RH short). Bracket-then-reverse; max 2 legs/day.

Child adds (research): after tier-1 fills, scan **5 m** bars strictly after fill time;
each qualifying child arms a **limit at that bar’s close** (live at bar end). Up to
``--max-child-adds`` children (default **1** ⇒ max 2 contracts; **2** ⇒ max 3).

**Stops (split):** tier‑1 keeps the **canonical** bracket stop (**RL** long / **RH** short).
Each **child** uses a **tighter** partial exit (tier‑1 unchanged until TP or wide stop). CLI
``--child-partial-stop edge`` (default): partial at **RH** (long children) / **RL** (short).
``mid``: partial at **(RH+RL)/2** — wider vs edge (needs deeper pullback before children flat).

TP remains **shared**. Pending child limits clear after a partial child stop-out.

Output CSV in this folder for charts / comparison (includes Entry/Exit times for PNGs).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

ChildPartialStopMode = Literal['edge', 'mid']

import databento as db
import pandas as pd
import pytz

_MNQ_ROOT = Path(__file__).resolve().parents[2]
if str(_MNQ_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNQ_ROOT))

from lib.execution import (  # noqa: E402
    DEFAULT_ROLL_CALENDAR,
    ChildEngine,
    ChildFilterParams,
    ExecutionParams,
    RollParams,
    apply_roll_selection,
    child_limit_hit,
    deterministic_miss,
    evaluate_child_filters,
    execution_params_for_profile,
    is_blackout,
    stop_exit_price,
    stop_hit,
    summarize_audit,
    summarize_legs,
    target_hit,
    write_stress_outputs,
)

_EPS = 1e-9

NY_TZ = pytz.timezone('America/New_York')
RTH_START = pd.Timestamp('2000-01-01 09:30:00').time()
RTH_END = pd.Timestamp('2000-01-01 16:00:00').time()
EOD_CUTOFF = pd.Timestamp('2000-01-01 15:55:00').time()
OPEN_RANGE_MIN = 15
MAX_TRADES_PER_DAY = 2

TICK = 0.25
MULT = 2.0
FEE_RT = 1.50
DEFAULT_SLIP_TICKS = 1

DBN_DEFAULT = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'

DEFAULT_MAX_CHILD_ADDS = 1


def open_range_end_time(minutes: int):
    t = pd.Timestamp('2000-01-01 09:30:00') + pd.Timedelta(minutes=minutes)
    return t.time()


RANGE_END_T = open_range_end_time(OPEN_RANGE_MIN)


def load_one_min_mnq(
    history_start=None,
    *,
    roll_params: Optional[RollParams] = None,
) -> pd.DataFrame:
    roll_params = roll_params or RollParams()
    print(f'Loading {DBN_DEFAULT} ...')
    store = db.DBNStore.from_file(DBN_DEFAULT)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    df = apply_roll_selection(df, roll_params)
    df = df[(df['t'] >= RTH_START) & (df['t'] < RTH_END)]
    if history_start is not None:
        df = df[df['date'] >= pd.Timestamp(history_start).date()]
    else:
        df = df[df['date'] >= pd.Timestamp('2021-03-04').date()]
    df = df.set_index('ts_event').sort_index()
    print(f'  {len(df):,} 1-min RTH front-month bars  (roll_mode={roll_params.mode})')
    return df


def resample_5m(df1: pd.DataFrame) -> pd.DataFrame:
    ix0 = df1.index[0]
    anchor = ix0.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def is_child_long_5m(row: pd.Series, rh: float) -> bool:
    o = float(row['open'])
    h = float(row['high'])
    l = float(row['low'])
    c = float(row['close'])
    if not (c > o + _EPS):
        return False
    return min(o, h, l, c) > rh + _EPS


def is_child_short_5m(row: pd.Series, rl: float) -> bool:
    o = float(row['open'])
    h = float(row['high'])
    l = float(row['low'])
    c = float(row['close'])
    if not (c < o - _EPS):
        return False
    return max(o, h, l, c) < rl - _EPS


def collect_child_orders(
    bars5_full: pd.DataFrame,
    fill_ts: pd.Timestamp,
    direction: str,
    rh: float,
    rl: float,
    max_child_adds: int,
) -> List[Tuple[float, pd.Timestamp]]:
    if max_child_adds <= 0:
        return []
    out: List[Tuple[float, pd.Timestamp]] = []
    bars_after = bars5_full[bars5_full.index > fill_ts]
    for ts5, row in bars_after.iterrows():
        if len(out) >= max_child_adds:
            break
        if direction == 'Long' and is_child_long_5m(row, rh):
            out.append((float(row['close']), ts5 + pd.Timedelta(minutes=5)))
        elif direction == 'Short' and is_child_short_5m(row, rl):
            out.append((float(row['close']), ts5 + pd.Timedelta(minutes=5)))
    return out


def _child_partial_px(direction: str, rh: float, rl: float, mode: ChildPartialStopMode) -> float:
    """Price level that triggers **partial exit of child-only** contracts (tier‑1 stays)."""
    if mode == 'edge':
        return rh if direction == 'Long' else rl
    # halfway between OR boundaries (wider than RH/RL edge — deeper pullback needed vs tier‑1)
    return (rh + rl) / 2.0


def simulate_day_preplaced_child(
    trade_bars: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    tick: float,
    slip_ticks: int,
    max_child_adds: int,
    sym: str,
    *,
    child_partial_stop: ChildPartialStopMode = 'edge',
) -> List[Dict[str, Any]]:
    """OCO tier-1 + optional children; tier-1 wide stop / tighter child stops / shared TP."""
    long_trigger = rh + tick
    short_trigger = rl - tick
    long_entry_px = long_trigger + slip_ticks * tick
    short_entry_px = short_trigger - slip_ticks * tick

    arm_long = True
    arm_short = True
    phase = 'ARMED'
    direction: Optional[str] = None
    tier1_entry = 0.0
    target = 0.0
    stop = 0.0  # tier-1 wide stop (CSV): RL long / RH short
    entries: List[float] = []
    fill_times: List[pd.Timestamp] = []
    child_orders: List[Tuple[float, pd.Timestamp]] = []
    child_orders_snapshot: List[Tuple[float, pd.Timestamp]] = []
    all_fill_prices: List[float] = []
    all_fill_times: List[pd.Timestamp] = []
    realized_pl_pts = 0.0
    realized_fee_units = 0  # RT fee events already charged (per contract exit)
    max_contracts_in_leg = 0
    legs_out: List[Dict[str, Any]] = []

    def emit_row(
        exit_ts: pd.Timestamp,
        exit_px: float,
        res_lab: str,
        final_entries: List[float],
        final_fill_times: List[pd.Timestamp],
    ) -> None:
        nonlocal phase, arm_long, arm_short, direction, realized_pl_pts, realized_fee_units, max_contracts_in_leg
        pl_rem = sum((exit_px - e) if direction == 'Long' else (e - exit_px) for e in final_entries)
        pl_pts = realized_pl_pts + pl_rem
        fee_events = realized_fee_units + len(final_entries)
        gross = round(pl_pts * MULT, 2)
        net = round(gross - FEE_RT * fee_events, 2)
        snap = child_orders_snapshot
        n_hist = len(all_fill_prices)
        legs_out.append(
            {
                'Trade_Direction': direction,
                'Tier1_Entry': round(tier1_entry, 4),
                'Entry_Price': round(sum(all_fill_prices) / len(all_fill_prices), 4)
                if all_fill_prices
                else round(final_entries[0], 4),
                'Exit_Price': round(exit_px, 4),
                'Trade_PL': round(pl_pts, 6),
                'Gross_$': gross,
                'Net_$': net,
                'Result': res_lab,
                'Entry_Time': final_fill_times[0].isoformat(),
                'Exit_Time': exit_ts.isoformat(),
                'Stop_Price': round(stop, 4),
                'TP_Price': round(target, 4),
                'Symbol': sym,
                'Contracts': max_contracts_in_leg,
                'Child_Add_Count': max(0, max_contracts_in_leg - 1),
                'Child_Add': max_contracts_in_leg > 1,
                'Child_Limit_Price': round(all_fill_prices[1], 4) if n_hist > 1 else '',
                'Child_Limit_Live_After': snap[0][1].isoformat() if len(snap) >= 1 else '',
                'Child1_Fill_Time': all_fill_times[1].isoformat() if n_hist > 1 else '',
                'Child2_Limit_Price': round(all_fill_prices[2], 4) if n_hist > 2 else '',
                'Child2_Limit_Live_After': snap[1][1].isoformat() if len(snap) >= 2 else '',
                'Child2_Fill_Time': all_fill_times[2].isoformat() if n_hist > 2 else '',
                'Max_Child_Adds_Param': max_child_adds,
                'Child_Partial_Stop': child_partial_stop,
            }
        )
        if direction == 'Long':
            arm_long = False
        else:
            arm_short = False
        direction = None
        entries.clear()
        fill_times.clear()
        child_orders.clear()
        child_orders_snapshot.clear()
        all_fill_prices.clear()
        all_fill_times.clear()
        realized_pl_pts = 0.0
        realized_fee_units = 0
        max_contracts_in_leg = 0
        phase = 'ARMED'
        if not (arm_long or arm_short) or len(legs_out) >= MAX_TRADES_PER_DAY:
            phase = 'DONE'

    def arm_entries(dir_: str, ts: pd.Timestamp) -> None:
        nonlocal direction, tier1_entry, target, stop, max_contracts_in_leg
        direction = dir_
        if dir_ == 'Long':
            tier1_entry = long_entry_px
            target = rh + rv
            stop = rl
        else:
            tier1_entry = short_entry_px
            target = rl - rv
            stop = rh
        entries[:] = [tier1_entry]
        fill_times[:] = [ts]
        all_fill_prices[:] = [tier1_entry]
        all_fill_times[:] = [ts]
        max_contracts_in_leg = 1
        child_orders[:] = collect_child_orders(bars5_full, ts, direction, rh, rl, max_child_adds)
        child_orders_snapshot[:] = list(child_orders)

    last_ts: Optional[pd.Timestamp] = None

    for ts, bar in trade_bars.iterrows():
        last_ts = ts
        h, l = float(bar['high']), float(bar['low'])
        opn = float(bar['open'])
        bar_time = ts.time()

        if phase == 'ARMED' and bar_time >= EOD_CUTOFF:
            break

        if phase == 'ARMED':
            long_hit = arm_long and h >= long_trigger
            short_hit = arm_short and l <= short_trigger
            if long_hit and short_hit:
                mid = (rh + rl) / 2.0
                arm_entries('Long' if opn >= mid else 'Short', ts)
                phase = 'IN'
            elif long_hit:
                arm_entries('Long', ts)
                phase = 'IN'
            elif short_hit:
                arm_entries('Short', ts)
                phase = 'IN'

        if phase == 'IN' and direction is not None:
            while True:
                closed = False
                last_px = 0.0
                exit_ts = ts
                res_lab = ''

                tight_ch = _child_partial_px(direction, rh, rl, child_partial_stop)

                if direction == 'Long':
                    if h >= target:
                        last_px = target
                        closed = True
                        res_lab = 'Win'
                    elif l <= rl:
                        last_px = rl
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and l <= tight_ch and l > rl:
                        exit_px_ch = tight_ch
                        for e in entries[1:]:
                            realized_pl_pts += exit_px_ch - e
                        realized_fee_units += len(entries) - 1
                        entries[:] = entries[:1]
                        fill_times[:] = fill_times[:1]
                        child_orders.clear()
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        continue
                else:
                    if l <= target:
                        last_px = target
                        closed = True
                        res_lab = 'Win'
                    elif h >= rh:
                        last_px = rh
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and h >= tight_ch and h < rh:
                        exit_px_ch = tight_ch
                        for e in entries[1:]:
                            realized_pl_pts += e - exit_px_ch
                        realized_fee_units += len(entries) - 1
                        entries[:] = entries[:1]
                        fill_times[:] = fill_times[:1]
                        child_orders.clear()
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        continue

                if closed:
                    emit_row(exit_ts, last_px, res_lab, entries[:], fill_times[:])
                    break

                progressed_limits = False
                j_next = len(entries) - 1
                while j_next < len(child_orders):
                    lim_px, live_ts = child_orders[j_next]
                    if ts < live_ts:
                        break
                    did = False
                    if direction == 'Long' and l <= lim_px + _EPS:
                        entries.append(lim_px)
                        fill_times.append(ts)
                        all_fill_prices.append(lim_px)
                        all_fill_times.append(ts)
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        did = True
                        progressed_limits = True
                    elif direction == 'Short' and h >= lim_px - _EPS:
                        entries.append(lim_px)
                        fill_times.append(ts)
                        all_fill_prices.append(lim_px)
                        all_fill_times.append(ts)
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        did = True
                        progressed_limits = True
                    if not did:
                        break
                    j_next = len(entries) - 1

                if not progressed_limits:
                    break

            if phase == 'DONE':
                break

    if phase == 'IN' and direction is not None and last_ts is not None:
        last_row = trade_bars.iloc[-1]
        eod_price = float(last_row['close'])
        ets = trade_bars.index[-1]
        avg_e = sum(entries) / len(entries)
        if direction == 'Long':
            res = 'EOD-Win' if eod_price > avg_e else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod_price < avg_e else 'EOD-Loss'
        emit_row(ets, eod_price, res, entries[:], fill_times[:])

    return legs_out


def simulate_day_preplaced_child_chronological(
    trade_bars: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    tick: float,
    max_child_adds: int,
    sym: str,
    *,
    execution: ExecutionParams,
    child_filters: ChildFilterParams,
    child_partial_stop: ChildPartialStopMode = 'edge',
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Live-style v2b OCO + children.

    Children are evaluated only after a 5m candle has completed, then a
    single pending child limit is tracked forward on subsequent 1m bars.
    """
    child_filters = ChildFilterParams(
        enabled=child_filters.enabled,
        max_child_adds=max_child_adds,
        min_distance_to_target_pts=child_filters.min_distance_to_target_pts,
        max_minutes_after_parent_fill=child_filters.max_minutes_after_parent_fill,
        min_or_range_pts=child_filters.min_or_range_pts,
        max_or_range_pts=child_filters.max_or_range_pts,
        min_child_close_distance_to_target_pts=child_filters.min_child_close_distance_to_target_pts,
        max_impulse_1m_pts=child_filters.max_impulse_1m_pts,
    )

    long_trigger = rh + tick
    short_trigger = rl - tick
    long_entry_px = long_trigger + execution.entry_slip_ticks * tick
    short_entry_px = short_trigger - execution.entry_slip_ticks * tick

    arm_long = True
    arm_short = True
    phase = 'ARMED'
    direction: Optional[str] = None
    tier1_entry = 0.0
    target = 0.0
    stop = 0.0
    entries: List[float] = []
    fill_times: List[pd.Timestamp] = []
    child_orders_snapshot: List[Tuple[float, pd.Timestamp]] = []
    all_fill_prices: List[float] = []
    all_fill_times: List[pd.Timestamp] = []
    realized_pl_pts = 0.0
    realized_fee_units = 0
    max_contracts_in_leg = 0
    parent_fill_ts: Optional[pd.Timestamp] = None
    processed_5m: set[pd.Timestamp] = set()
    next_5m_pos = 0
    pending_child: Optional[Dict[str, Any]] = None
    audit: List[Dict[str, Any]] = []
    legs_out: List[Dict[str, Any]] = []

    def cancel_pending(reason: str) -> None:
        nonlocal pending_child
        if pending_child is not None:
            audit[pending_child['audit_idx']]['cancel_reason'] = reason
            pending_child = None

    def emit_row(
        exit_ts: pd.Timestamp,
        exit_px: float,
        res_lab: str,
        final_entries: List[float],
        final_fill_times: List[pd.Timestamp],
    ) -> None:
        nonlocal phase, arm_long, arm_short, direction, realized_pl_pts, realized_fee_units, max_contracts_in_leg
        nonlocal parent_fill_ts, pending_child, processed_5m, next_5m_pos
        cancel_pending('closed')
        pl_rem = sum((exit_px - e) if direction == 'Long' else (e - exit_px) for e in final_entries)
        pl_pts = realized_pl_pts + pl_rem
        fee_events = realized_fee_units + len(final_entries)
        gross = round(pl_pts * MULT, 2)
        net = round(gross - execution.fee_rt * fee_events, 2)
        n_hist = len(all_fill_prices)
        legs_out.append(
            {
                'Trade_Direction': direction,
                'Tier1_Entry': round(tier1_entry, 4),
                'Entry_Price': round(sum(all_fill_prices) / len(all_fill_prices), 4)
                if all_fill_prices
                else round(final_entries[0], 4),
                'Exit_Price': round(exit_px, 4),
                'Trade_PL': round(pl_pts, 6),
                'Gross_$': gross,
                'Net_$': net,
                'Result': res_lab,
                'Entry_Time': final_fill_times[0].isoformat(),
                'Exit_Time': exit_ts.isoformat(),
                'Stop_Price': round(stop, 4),
                'TP_Price': round(target, 4),
                'Symbol': sym,
                'Contracts': max_contracts_in_leg,
                'Child_Add_Count': max(0, max_contracts_in_leg - 1),
                'Child_Add': max_contracts_in_leg > 1,
                'Child_Limit_Price': round(all_fill_prices[1], 4) if n_hist > 1 else '',
                'Child_Limit_Live_After': child_orders_snapshot[0][1].isoformat() if len(child_orders_snapshot) >= 1 else '',
                'Child1_Fill_Time': all_fill_times[1].isoformat() if n_hist > 1 else '',
                'Child2_Limit_Price': round(all_fill_prices[2], 4) if n_hist > 2 else '',
                'Child2_Limit_Live_After': child_orders_snapshot[1][1].isoformat() if len(child_orders_snapshot) >= 2 else '',
                'Child2_Fill_Time': all_fill_times[2].isoformat() if n_hist > 2 else '',
                'Max_Child_Adds_Param': max_child_adds,
                'Child_Partial_Stop': child_partial_stop,
                'Execution_Profile': execution.profile,
                'Child_Engine': 'chronological',
            }
        )
        if direction == 'Long':
            arm_long = False
        else:
            arm_short = False
        direction = None
        entries.clear()
        fill_times.clear()
        child_orders_snapshot.clear()
        all_fill_prices.clear()
        all_fill_times.clear()
        realized_pl_pts = 0.0
        realized_fee_units = 0
        max_contracts_in_leg = 0
        parent_fill_ts = None
        pending_child = None
        processed_5m.clear()
        next_5m_pos = 0
        phase = 'ARMED'
        if not (arm_long or arm_short) or len(legs_out) >= MAX_TRADES_PER_DAY:
            phase = 'DONE'

    def arm_entries(dir_: str, ts: pd.Timestamp) -> None:
        nonlocal direction, tier1_entry, target, stop, max_contracts_in_leg, parent_fill_ts, next_5m_pos
        direction = dir_
        if dir_ == 'Long':
            tier1_entry = long_entry_px
            target = rh + rv
            stop = rl
        else:
            tier1_entry = short_entry_px
            target = rl - rv
            stop = rh
        entries[:] = [tier1_entry]
        fill_times[:] = [ts]
        all_fill_prices[:] = [tier1_entry]
        all_fill_times[:] = [ts]
        max_contracts_in_leg = 1
        parent_fill_ts = pd.Timestamp(ts)
        next_5m_pos = int(bars5_full.index.searchsorted(parent_fill_ts, side='right'))

    def maybe_fill_pending_child(ts: pd.Timestamp, high: float, low: float) -> None:
        nonlocal pending_child, max_contracts_in_leg, next_5m_pos
        if pending_child is None or direction is None:
            return
        if pd.Timestamp(ts) < pending_child['live_ts']:
            return
        lim_px = float(pending_child['limit_price'])
        if not child_limit_hit(direction, high, low, lim_px, tick, execution):
            return
        key = f'{sym}|{ts.isoformat()}|{direction}|{lim_px:.4f}|{len(all_fill_prices)}'
        if deterministic_miss(key, execution.child_limit_miss_rate, execution.seed):
            audit[pending_child['audit_idx']]['cancel_reason'] = 'missed_by_model'
            pending_child = None
            next_5m_pos = int(bars5_full.index.searchsorted(pd.Timestamp(ts), side='right'))
            return
        entries.append(lim_px)
        fill_times.append(pd.Timestamp(ts))
        all_fill_prices.append(lim_px)
        all_fill_times.append(pd.Timestamp(ts))
        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
        audit[pending_child['audit_idx']]['filled'] = True
        audit[pending_child['audit_idx']]['fill_time'] = pd.Timestamp(ts).isoformat()
        pending_child = None
        next_5m_pos = int(bars5_full.index.searchsorted(pd.Timestamp(ts), side='right'))

    def maybe_arm_child_after_bar(ts: pd.Timestamp) -> None:
        nonlocal pending_child, next_5m_pos
        if direction is None or parent_fill_ts is None or max_child_adds <= 0:
            return
        if len(all_fill_prices) - 1 >= max_child_adds or pending_child is not None:
            return
        bar_end = pd.Timestamp(ts) + pd.Timedelta(minutes=1)
        while next_5m_pos < len(bars5_full):
            ts5 = pd.Timestamp(bars5_full.index[next_5m_pos])
            if ts5 + pd.Timedelta(minutes=5) > bar_end:
                break
            next_5m_pos += 1
            if ts5 in processed_5m:
                continue
            processed_5m.add(ts5)
            row = bars5_full.iloc[next_5m_pos - 1]
            if direction == 'Long':
                is_signal = is_child_long_5m(row, rh)
            else:
                is_signal = is_child_short_5m(row, rl)
            if not is_signal:
                continue
            limit_px = float(row['close'])
            live_after = ts5 + pd.Timedelta(minutes=5 + execution.order_delay_bars)
            candidate_1m = trade_bars[(trade_bars.index >= ts5) & (trade_bars.index < ts5 + pd.Timedelta(minutes=5))]
            ok, reason = evaluate_child_filters(
                child_filters,
                direction=direction,
                rh=rh,
                rl=rl,
                rv=rv,
                target=target,
                parent_fill_ts=parent_fill_ts,
                candidate_ts=ts5,
                child_close=limit_px,
                candidate_1m=candidate_1m,
            )
            audit_row = {
                'event': 'child_candidate',
                'symbol': sym,
                'candidate_time': ts5.isoformat(),
                'direction': direction,
                'limit_price': limit_px,
                'live_after': live_after.isoformat(),
                'filter_pass': ok,
                'filter_reason': reason,
                'filled': False,
                'fill_time': '',
                'cancel_reason': '',
            }
            audit.append(audit_row)
            audit_idx = len(audit) - 1
            if not ok:
                audit[audit_idx]['cancel_reason'] = 'filtered'
                continue
            if is_blackout(live_after, execution):
                audit[audit_idx]['cancel_reason'] = 'blackout'
                audit.append({'event': 'blackout_skip', 'symbol': sym, 'candidate_time': ts5.isoformat(), 'reason': 'child_live_after'})
                continue
            child_orders_snapshot.append((limit_px, live_after))
            pending_child = {
                'limit_price': limit_px,
                'live_ts': live_after,
                'audit_idx': audit_idx,
            }
            break

    last_ts: Optional[pd.Timestamp] = None

    for ts, bar in trade_bars.iterrows():
        ts = pd.Timestamp(ts)
        last_ts = ts
        h, l = float(bar['high']), float(bar['low'])
        opn = float(bar['open'])
        bar_time = ts.time()

        bar_blackout = is_blackout(ts, execution)

        if phase == 'ARMED' and bar_time >= EOD_CUTOFF:
            break

        if phase == 'ARMED':
            if bar_blackout:
                audit.append({'event': 'blackout_skip', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'entry_window'})
                continue
            long_hit = arm_long and h >= long_trigger
            short_hit = arm_short and l <= short_trigger
            if long_hit and short_hit:
                audit.append({'event': 'ambiguous_bar', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'both_oco_entries'})
                mid = (rh + rl) / 2.0
                arm_entries('Long' if opn >= mid else 'Short', ts)
                phase = 'IN'
            elif long_hit:
                arm_entries('Long', ts)
                phase = 'IN'
            elif short_hit:
                arm_entries('Short', ts)
                phase = 'IN'

        if phase == 'IN' and direction is not None:
            if bar_blackout:
                audit.append({'event': 'blackout_skip', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'child_window'})
                cancel_pending('blackout')
            tight_ch = _child_partial_px(direction, rh, rl, child_partial_stop)
            closed = False
            last_px = 0.0
            res_lab = ''

            target_now = target_hit(direction, h, l, target, tick, execution)
            wide_stop_now = stop_hit(direction, h, l, stop)
            partial_now = False
            if direction == 'Long':
                partial_now = len(entries) > 1 and l <= tight_ch and l > stop
            else:
                partial_now = len(entries) > 1 and h >= tight_ch and h < stop
            if target_now and wide_stop_now:
                audit.append({'event': 'ambiguous_bar', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'target_and_stop'})

            if execution.ambiguity_policy == 'adverse':
                if wide_stop_now:
                    last_px = stop_exit_price(direction, stop, tick, execution)
                    closed = True
                    res_lab = 'Loss'
                elif partial_now:
                    exit_px_ch = stop_exit_price(direction, tight_ch, tick, execution)
                    for e in entries[1:]:
                        realized_pl_pts += (exit_px_ch - e) if direction == 'Long' else (e - exit_px_ch)
                    realized_fee_units += len(entries) - 1
                    entries[:] = entries[:1]
                    fill_times[:] = fill_times[:1]
                    cancel_pending('partial_child_stop')
                elif target_now:
                    last_px = target
                    closed = True
                    res_lab = 'Win'
            else:
                if target_now:
                    last_px = target
                    closed = True
                    res_lab = 'Win'
                elif wide_stop_now:
                    last_px = stop_exit_price(direction, stop, tick, execution)
                    closed = True
                    res_lab = 'Loss'
                elif partial_now:
                    exit_px_ch = stop_exit_price(direction, tight_ch, tick, execution)
                    for e in entries[1:]:
                        realized_pl_pts += (exit_px_ch - e) if direction == 'Long' else (e - exit_px_ch)
                    realized_fee_units += len(entries) - 1
                    entries[:] = entries[:1]
                    fill_times[:] = fill_times[:1]
                    cancel_pending('partial_child_stop')

            if closed:
                emit_row(ts, last_px, res_lab, entries[:], fill_times[:])
            elif not bar_blackout:
                maybe_fill_pending_child(ts, h, l)
                maybe_arm_child_after_bar(ts)

            if phase == 'DONE':
                break

    if phase == 'IN' and direction is not None and last_ts is not None:
        cancel_pending('eod')
        last_row = trade_bars.iloc[-1]
        eod_price = float(last_row['close'])
        ets = trade_bars.index[-1]
        avg_e = sum(entries) / len(entries)
        if direction == 'Long':
            res = 'EOD-Win' if eod_price > avg_e else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod_price < avg_e else 'EOD-Loss'
        emit_row(pd.Timestamp(ets), eod_price, res, entries[:], fill_times[:])

    return legs_out, audit


_HELP_EPILOG = """\
Example runs:
  cd potions/mnq/case_studies/v2b_child
  python3 orb_open_limit_v2b_child.py --max-child-adds 0 --out mnq_orb_step2_match.csv
  python3 orb_open_limit_v2b_child.py --max-child-adds 1 --slip-ticks 1 \\
      --out mnq_orb_open_limit_v2b_child.csv
  python3 orb_open_limit_v2b_child.py --max-child-adds 2 --out mnq_orb_open_limit_v2b_child_3max.csv
  python3 orb_open_limit_v2b_child.py --max-child-adds 2 --child-partial-stop mid \\
      --out ../v2b_c/experiments/child_stop_midrange/mnq_orb_open_limit_v2b_child_3max_mid.csv

Outputs:
  CSV (--out): one row per simulated leg; columns include Tier1_Entry, TP_Price,
    Stop_Price, Contracts, Child_* prices/times, Net_$, cumulative columns.
  Stdout: leg count, win rate (Net_$ > 0), Σ Net_$, max drawdown on cumulative Net_$.
"""


def make_child_filter_params(args: argparse.Namespace, max_child_adds: int) -> ChildFilterParams:
    return ChildFilterParams(
        enabled=bool(args.enable_child_filters),
        max_child_adds=max_child_adds,
        min_distance_to_target_pts=args.child_min_distance_to_target_pts,
        max_minutes_after_parent_fill=args.child_max_minutes_after_parent_fill,
        min_or_range_pts=args.child_min_or_range_pts,
        max_or_range_pts=args.child_max_or_range_pts,
        min_child_close_distance_to_target_pts=args.child_min_close_distance_to_target_pts,
        max_impulse_1m_pts=args.child_max_impulse_1m_pts,
    )


def run_v2b_child_backtest(
    df: pd.DataFrame,
    *,
    max_child_adds: int,
    slip_ticks: int,
    child_partial_stop: ChildPartialStopMode,
    child_engine: ChildEngine,
    execution: ExecutionParams,
    child_filters: ChildFilterParams,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []
    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        range_bars = day_df[day_df['t'] < RANGE_END_T]
        if range_bars.empty:
            continue
        rh = float(range_bars['high'].max())
        rl = float(range_bars['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        trade_bars = day_df[day_df['t'] >= RANGE_END_T]
        if trade_bars.empty:
            continue
        d1 = day_df[day_df['t'] >= RTH_START]
        b5 = resample_5m(d1)
        sym = str(day_df['symbol'].iloc[0])
        if child_engine == 'legacy':
            legs = simulate_day_preplaced_child(
                trade_bars,
                b5,
                rh,
                rl,
                rv,
                TICK,
                slip_ticks,
                max_child_adds,
                sym,
                child_partial_stop=child_partial_stop,
            )
            audit = []
        else:
            legs, audit = simulate_day_preplaced_child_chronological(
                trade_bars,
                b5,
                rh,
                rl,
                rv,
                TICK,
                max_child_adds,
                sym,
                execution=execution,
                child_filters=child_filters,
                child_partial_stop=child_partial_stop,
            )
        for a in audit:
            audit_rows.append({'Date': day, 'Regime': 'v2b', **a})
        for leg in legs:
            rows.append(
                {
                    'Date': day,
                    'Day_of_Week': pd.Timestamp(day).strftime('%A'),
                    'Symbol': sym,
                    'Range_High': rh,
                    'Range_Low': rl,
                    'Range': rv,
                    **leg,
                }
            )

    out_df = pd.DataFrame(rows)
    if not out_df.empty:
        out_df['Cumulative_PL'] = out_df['Trade_PL'].cumsum().round(6)
        out_df['Cumulative_$'] = out_df['Net_$'].cumsum().round(2)
    return out_df, pd.DataFrame(audit_rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='v2b OCO tier-1 + optional child scale-in',
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _here = Path(__file__).resolve().parent
    ap.add_argument('--out', type=str, default=str(_here / 'mnq_orb_open_limit_v2b_child.csv'))
    ap.add_argument(
        '--max-child-adds',
        type=int,
        default=DEFAULT_MAX_CHILD_ADDS,
        choices=[0, 1, 2],
        help='Max extra MNQ limits after tier-1 OCO fill (0=pure step2-style legs)',
    )
    ap.add_argument('--slip-ticks', type=int, default=DEFAULT_SLIP_TICKS)
    ap.add_argument('--child-engine', choices=['legacy', 'chronological'], default='legacy')
    ap.add_argument('--execution-profile', choices=['baseline', 'mild', 'conservative', 'latency', 'blackout'], default='baseline')
    ap.add_argument('--stress-report', action='store_true', help='Write .execution_stress CSV/MD sidecars using chronological child engine')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--blackout-csv', type=Path, default=None, help='CSV with start,end[,reason] for blackout profile')
    ap.add_argument('--audit-out', type=Path, default=None, help='Optional child/audit CSV path for chronological runs')
    ap.add_argument('--roll-mode', choices=['legacy-volume', 'calendar'], default='legacy-volume')
    ap.add_argument('--roll-calendar', type=Path, default=DEFAULT_ROLL_CALENDAR)
    ap.add_argument('--enable-child-filters', action='store_true', help='Enable optional child quality filters; defaults are no-op')
    ap.add_argument('--child-min-distance-to-target-pts', type=float, default=None)
    ap.add_argument('--child-max-minutes-after-parent-fill', type=float, default=None)
    ap.add_argument('--child-min-or-range-pts', type=float, default=None)
    ap.add_argument('--child-max-or-range-pts', type=float, default=None)
    ap.add_argument('--child-min-close-distance-to-target-pts', type=float, default=None)
    ap.add_argument('--child-max-impulse-1m-pts', type=float, default=None)
    ap.add_argument(
        '--child-partial-stop',
        type=str,
        choices=['edge', 'mid'],
        default='edge',
        help=(
            'Partial exit for child-only contracts: edge = RH (long) / RL (short); '
            'mid = (RH+RL)/2 (wider — deeper pullback vs edge)'
        ),
    )
    args = ap.parse_args()
    out_path = Path(args.out)
    max_child_adds = int(args.max_child_adds)
    slip_ticks = int(args.slip_ticks)
    child_partial_stop = args.child_partial_stop  # type: ignore[assignment]
    child_engine: ChildEngine = args.child_engine
    if args.execution_profile != 'baseline' and child_engine == 'legacy':
        print('Non-baseline execution profiles require chronological child handling; switching --child-engine to chronological.')
        child_engine = 'chronological'
    roll_params = RollParams(mode=args.roll_mode, calendar_path=Path(args.roll_calendar))
    execution = execution_params_for_profile(
        args.execution_profile,
        entry_slip_ticks=slip_ticks,
        fee_rt=FEE_RT,
        seed=args.seed,
        blackout_csv=args.blackout_csv,
    )
    child_filters = make_child_filter_params(args, max_child_adds)

    df = load_one_min_mnq(roll_params=roll_params)
    out_df, audit_df = run_v2b_child_backtest(
        df,
        max_child_adds=max_child_adds,
        slip_ticks=slip_ticks,
        child_partial_stop=child_partial_stop,
        child_engine=child_engine,
        execution=execution,
        child_filters=child_filters,
    )
    if out_df.empty:
        print('No trades.')
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    if child_engine == 'chronological':
        audit_path = args.audit_out or out_path.with_suffix(out_path.suffix + '.child_audit.csv')
        audit_df.to_csv(audit_path, index=False)
        print(f'Wrote child audit -> {audit_path}')

    wins = (out_df['Net_$'] > 0).sum()
    print(
        f'Wrote {len(out_df)} legs -> {out_path}  '
        f'(max_child_adds={max_child_adds}, slip_ticks={slip_ticks}, '
        f'child_partial_stop={child_partial_stop}, child_engine={child_engine}, '
        f'execution_profile={execution.profile}, roll_mode={roll_params.mode})'
    )
    print(f'Win rate Net_$>0: {wins/len(out_df)*100:.1f}%  ΣNet_$ ${out_df["Net_$"].sum():,.2f}')
    if max_child_adds > 0:
        print(f'Legs with ≥1 child add: {out_df["Child_Add"].mean()*100:.1f}%')
    eq = out_df['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f'Max DD Net_$ ${dd.min():,.2f}')
    if args.stress_report:
        stress_rows: List[Dict[str, object]] = []
        for profile in ['baseline', 'mild', 'conservative', 'latency', 'blackout']:
            ep = execution_params_for_profile(
                profile,  # type: ignore[arg-type]
                entry_slip_ticks=slip_ticks,
                fee_rt=FEE_RT,
                seed=args.seed,
                blackout_csv=args.blackout_csv,
            )
            sdf, sad = run_v2b_child_backtest(
                df,
                max_child_adds=max_child_adds,
                slip_ticks=slip_ticks,
                child_partial_stop=child_partial_stop,
                child_engine='chronological',
                execution=ep,
                child_filters=child_filters,
            )
            leg_sum = summarize_legs(sdf)
            audit_sum = summarize_audit(sad)
            stress_rows.append({'profile': profile, **leg_sum, **audit_sum})
        scsv, smd = write_stress_outputs(out_path, stress_rows, title='v2b_child execution stress')
        print(f'Wrote execution stress -> {scsv} and {smd}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
