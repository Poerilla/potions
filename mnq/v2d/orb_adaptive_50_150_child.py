#!/usr/bin/env python3
"""
Combined **adaptive 50/150** backtest (same routing as ``build_adaptive_trades.py``)
with **v2b_child**-style child scale-ins on **both** arms:

  - **v2b regime:** pre-placed OCO tier-1 + optional children (same simulator as
    ``case_studies/v2b_child/orb_open_limit_v2b_child.py``).

  - **v2d regime:** canonical fade simulator logic from ``step2_preplaced_stops_v2d_fade.py``,
    extended so after each fade fill children arm under the **same** 5 m RH/RL rules,
    with **split stops** (wide tier‑1 / tighter children) matching ``orb_open_limit_v2b_child`` semantics.

Daily routing uses prior day's MNQ daily closes (**MA50 vs MA150**), causal ``shift(1)``.

Outputs CSV aligned with ``v2b_child`` leg columns plus ``Regime``, ``MA_fast_prev``, ``MA_slow_prev``.

Example::

  cd potions/mnq/v2d
  python3 orb_adaptive_50_150_child.py --max-child-adds 1 --out mnq_orb_results_adaptive_50_150_child.csv

Sanity: ``--max-child-adds 0`` should reproduce stitched adaptive totals vs canonical v2b + v2d CSVs
for each regime path (same 1 m DB + assumptions).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import databento as db
import pandas as pd

_MNQ_ROOT = Path(__file__).resolve().parent.parent
if str(_MNQ_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNQ_ROOT))

_V2B_CHILD = Path(__file__).resolve().parent.parent / 'case_studies' / 'v2b_child'
if str(_V2B_CHILD) not in sys.path:
    sys.path.insert(0, str(_V2B_CHILD))

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

from orb_open_limit_v2b_child import (  # noqa: E402
    EOD_CUTOFF,
    OPEN_RANGE_MIN,
    RTH_START,
    RTH_END,
    FEE_RT,
    MULT,
    TICK,
    collect_child_orders,
    is_child_long_5m,
    is_child_short_5m,
    load_one_min_mnq,
    open_range_end_time,
    resample_5m,
    simulate_day_preplaced_child,
    simulate_day_preplaced_child_chronological,
)

RANGE_END_T = open_range_end_time(OPEN_RANGE_MIN)
MAX_TRADES_PER_DAY = 2
_EPS = 1e-9

DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
FAST, SLOW = 50, 150


def daily_close_ma(roll_params: Optional[RollParams] = None):
    roll_params = roll_params or RollParams()
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = apply_roll_selection(df, roll_params)
    close = fm.set_index('date').sort_index()['close']
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    regime_v2b = (ma_fast > ma_slow).shift(1).fillna(True)
    return regime_v2b, ma_fast, ma_slow


def simulate_day_v2d_child(
    trade_bars: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    range_val: float,
    tick: float,
    slip_ticks: int,
    max_child_adds: int,
    sym: str,
) -> List[Dict[str, Any]]:
    """Fade v2d + optional children; tier-1 wide stop / tighter child stops / shared TP."""
    long_break_trig = rh + tick
    short_break_trig = rl - tick
    short_fade_trig = rh - tick
    long_fade_trig = rl + tick
    short_fade_fill = short_fade_trig - slip_ticks * tick
    long_fade_fill = long_fade_trig + slip_ticks * tick

    long_break_done = False
    short_break_done = False
    armed_short_fade = False
    armed_long_fade = False
    traded_long = False
    traded_short = False

    in_trade = False
    direction: Optional[str] = None
    entry = target = stop = None
    tier1_entry = 0.0
    entries: List[float] = []
    fill_times: List[pd.Timestamp] = []
    child_orders: List[Tuple[float, pd.Timestamp]] = []
    child_orders_snapshot: List[Tuple[float, pd.Timestamp]] = []
    all_fill_prices: List[float] = []
    all_fill_times: List[pd.Timestamp] = []
    realized_pl_pts = 0.0
    realized_fee_units = 0
    max_contracts_in_leg = 0

    legs_out: List[Dict[str, Any]] = []
    last_bar = None
    last_ts: Optional[pd.Timestamp] = None

    def finalize_leg(exit_ts: pd.Timestamp, last_px: float, res_lab: str) -> None:
        nonlocal in_trade, direction, traded_long, traded_short
        nonlocal entries, fill_times, child_orders, entry, target, stop, tier1_entry
        nonlocal armed_short_fade, armed_long_fade
        nonlocal child_orders_snapshot, all_fill_prices, all_fill_times
        nonlocal realized_pl_pts, realized_fee_units, max_contracts_in_leg
        assert direction is not None
        pl_rem = sum((last_px - e) if direction == 'Long' else (e - last_px) for e in entries)
        pl_pts = realized_pl_pts + pl_rem
        fee_events = realized_fee_units + len(entries)
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
                else round(entries[0], 4),
                'Exit_Price': round(last_px, 4),
                'Trade_PL': round(pl_pts, 6),
                'Gross_$': gross,
                'Net_$': net,
                'Result': res_lab,
                'Entry_Time': fill_times[0].isoformat(),
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
            }
        )
        if direction == 'Long':
            traded_long = True
            armed_long_fade = False
        else:
            traded_short = True
            armed_short_fade = False
        in_trade = False
        direction = None
        entry = target = stop = None
        tier1_entry = 0.0
        entries.clear()
        fill_times.clear()
        child_orders.clear()
        child_orders_snapshot.clear()
        all_fill_prices.clear()
        all_fill_times.clear()
        realized_pl_pts = 0.0
        realized_fee_units = 0
        max_contracts_in_leg = 0

    def push_fade_fill(dir_: str, px: float, ts: pd.Timestamp, tgt: float, stp: float) -> None:
        nonlocal direction, entry, target, stop, tier1_entry, max_contracts_in_leg
        direction = dir_
        entry = px
        target = tgt
        stop = stp
        tier1_entry = entry
        entries[:] = [entry]
        fill_times[:] = [pd.Timestamp(ts)]
        all_fill_prices[:] = [entry]
        all_fill_times[:] = [pd.Timestamp(ts)]
        max_contracts_in_leg = 1
        child_orders[:] = collect_child_orders(bars5_full, fill_times[0], direction, rh, rl, max_child_adds)
        child_orders_snapshot[:] = list(child_orders)

    for ts, bar in trade_bars.iterrows():
        last_bar = bar
        last_ts = pd.Timestamp(ts)
        bt = ts.time() if hasattr(ts, 'time') else None
        if not in_trade and bt is not None and bt >= EOD_CUTOFF:
            break
        h, l = float(bar['high']), float(bar['low'])
        opn = float(bar['open'])
        breakout_this_bar = False

        if not in_trade:
            if not long_break_done and h >= long_break_trig:
                long_break_done = True
                breakout_this_bar = True
                if not traded_short:
                    armed_short_fade = True
            if not short_break_done and l <= short_break_trig:
                short_break_done = True
                breakout_this_bar = True
                if not traded_long:
                    armed_long_fade = True

        if not in_trade and not breakout_this_bar:
            short_hit = armed_short_fade and l <= short_fade_trig
            long_hit = armed_long_fade and h >= long_fade_trig
            if short_hit and long_hit:
                mid = (rh + rl) / 2.0
                if opn >= mid:
                    push_fade_fill('Short', short_fade_fill, ts, rl, rh + range_val)
                else:
                    push_fade_fill('Long', long_fade_fill, ts, rh, rl - range_val)
                in_trade = True
                armed_short_fade = False
                armed_long_fade = False
            elif short_hit:
                push_fade_fill('Short', short_fade_fill, ts, rl, rh + range_val)
                in_trade = True
                armed_short_fade = False
            elif long_hit:
                push_fade_fill('Long', long_fade_fill, ts, rh, rl - range_val)
                in_trade = True
                armed_long_fade = False

        if in_trade and direction is not None:
            while True:
                closed = False
                exit_ts = pd.Timestamp(ts)
                last_px = 0.0
                res_lab = ''

                if direction == 'Long':
                    if h >= float(target):
                        last_px = float(target)
                        closed = True
                        res_lab = 'Win'
                    elif l <= float(stop):
                        last_px = float(stop)
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and l <= rh and l > float(stop):
                        exit_px_ch = rh
                        for e in entries[1:]:
                            realized_pl_pts += exit_px_ch - e
                        realized_fee_units += len(entries) - 1
                        entries[:] = entries[:1]
                        fill_times[:] = fill_times[:1]
                        child_orders.clear()
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        continue
                else:
                    if l <= float(target):
                        last_px = float(target)
                        closed = True
                        res_lab = 'Win'
                    elif h >= float(stop):
                        last_px = float(stop)
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and h >= rl and h < float(stop):
                        exit_px_ch = rl
                        for e in entries[1:]:
                            realized_pl_pts += e - exit_px_ch
                        realized_fee_units += len(entries) - 1
                        entries[:] = entries[:1]
                        fill_times[:] = fill_times[:1]
                        child_orders.clear()
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        continue

                if closed:
                    finalize_leg(exit_ts, last_px, res_lab)
                    break

                progressed_limits = False
                j_next = len(entries) - 1
                while j_next < len(child_orders):
                    lim_px, live_ts = child_orders[j_next]
                    if pd.Timestamp(ts) < live_ts:
                        break
                    did = False
                    if direction == 'Long' and l <= lim_px + _EPS:
                        entries.append(lim_px)
                        fill_times.append(pd.Timestamp(ts))
                        all_fill_prices.append(lim_px)
                        all_fill_times.append(pd.Timestamp(ts))
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        did = True
                        progressed_limits = True
                    elif direction == 'Short' and h >= lim_px - _EPS:
                        entries.append(lim_px)
                        fill_times.append(pd.Timestamp(ts))
                        all_fill_prices.append(lim_px)
                        all_fill_times.append(pd.Timestamp(ts))
                        max_contracts_in_leg = max(max_contracts_in_leg, len(entries))
                        did = True
                        progressed_limits = True
                    if not did:
                        break
                    j_next = len(entries) - 1

                if not progressed_limits:
                    break

            if traded_long and traded_short:
                break
            if len(legs_out) >= MAX_TRADES_PER_DAY:
                break

    if in_trade and direction is not None and last_bar is not None and last_ts is not None:
        eod_price = float(last_bar['close'])
        avg_e = sum(entries) / len(entries)
        if direction == 'Long':
            res = 'EOD-Win' if eod_price > avg_e else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod_price < avg_e else 'EOD-Loss'
        finalize_leg(last_ts, eod_price, res)

    return legs_out


def simulate_day_v2d_child_chronological(
    trade_bars: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    range_val: float,
    tick: float,
    max_child_adds: int,
    sym: str,
    *,
    execution: ExecutionParams,
    child_filters: ChildFilterParams,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Live-style v2d fade + chronological child tracking."""
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
    long_break_trig = rh + tick
    short_break_trig = rl - tick
    short_fade_trig = rh - tick
    long_fade_trig = rl + tick
    short_fade_fill = short_fade_trig - execution.entry_slip_ticks * tick
    long_fade_fill = long_fade_trig + execution.entry_slip_ticks * tick

    long_break_done = False
    short_break_done = False
    armed_short_fade = False
    armed_long_fade = False
    traded_long = False
    traded_short = False

    in_trade = False
    direction: Optional[str] = None
    entry = target = stop = None
    tier1_entry = 0.0
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
    last_bar = None
    last_ts: Optional[pd.Timestamp] = None

    def cancel_pending(reason: str) -> None:
        nonlocal pending_child
        if pending_child is not None:
            audit[pending_child['audit_idx']]['cancel_reason'] = reason
            pending_child = None

    def finalize_leg(exit_ts: pd.Timestamp, last_px: float, res_lab: str) -> None:
        nonlocal in_trade, direction, traded_long, traded_short
        nonlocal entries, fill_times, entry, target, stop, tier1_entry
        nonlocal armed_short_fade, armed_long_fade
        nonlocal child_orders_snapshot, all_fill_prices, all_fill_times
        nonlocal realized_pl_pts, realized_fee_units, max_contracts_in_leg
        nonlocal parent_fill_ts, pending_child, next_5m_pos
        assert direction is not None
        cancel_pending('closed')
        pl_rem = sum((last_px - e) if direction == 'Long' else (e - last_px) for e in entries)
        pl_pts = realized_pl_pts + pl_rem
        fee_events = realized_fee_units + len(entries)
        gross = round(pl_pts * MULT, 2)
        net = round(gross - execution.fee_rt * fee_events, 2)
        n_hist = len(all_fill_prices)
        legs_out.append(
            {
                'Trade_Direction': direction,
                'Tier1_Entry': round(tier1_entry, 4),
                'Entry_Price': round(sum(all_fill_prices) / len(all_fill_prices), 4)
                if all_fill_prices
                else round(entries[0], 4),
                'Exit_Price': round(last_px, 4),
                'Trade_PL': round(pl_pts, 6),
                'Gross_$': gross,
                'Net_$': net,
                'Result': res_lab,
                'Entry_Time': fill_times[0].isoformat(),
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
                'Execution_Profile': execution.profile,
                'Child_Engine': 'chronological',
            }
        )
        if direction == 'Long':
            traded_long = True
            armed_long_fade = False
        else:
            traded_short = True
            armed_short_fade = False
        in_trade = False
        direction = None
        entry = target = stop = None
        tier1_entry = 0.0
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

    def push_fade_fill(dir_: str, px: float, ts: pd.Timestamp, tgt: float, stp: float) -> None:
        nonlocal direction, entry, target, stop, tier1_entry, max_contracts_in_leg, parent_fill_ts, next_5m_pos
        direction = dir_
        entry = px
        target = tgt
        stop = stp
        tier1_entry = entry
        entries[:] = [entry]
        fill_times[:] = [pd.Timestamp(ts)]
        all_fill_prices[:] = [entry]
        all_fill_times[:] = [pd.Timestamp(ts)]
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
        key = f'{sym}|{ts.isoformat()}|v2d|{direction}|{lim_px:.4f}|{len(all_fill_prices)}'
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
            is_signal = is_child_long_5m(row, rh) if direction == 'Long' else is_child_short_5m(row, rl)
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
                rv=range_val,
                target=float(target),
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
            pending_child = {'limit_price': limit_px, 'live_ts': live_after, 'audit_idx': audit_idx}
            break

    for ts, bar in trade_bars.iterrows():
        ts = pd.Timestamp(ts)
        last_bar = bar
        last_ts = ts
        bt = ts.time() if hasattr(ts, 'time') else None
        if not in_trade and bt is not None and bt >= EOD_CUTOFF:
            break
        h, l = float(bar['high']), float(bar['low'])
        opn = float(bar['open'])
        bar_blackout = is_blackout(ts, execution)
        breakout_this_bar = False

        if not in_trade:
            if bar_blackout:
                audit.append({'event': 'blackout_skip', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'entry_window'})
            else:
                if not long_break_done and h >= long_break_trig:
                    long_break_done = True
                    breakout_this_bar = True
                    if not traded_short:
                        armed_short_fade = True
                if not short_break_done and l <= short_break_trig:
                    short_break_done = True
                    breakout_this_bar = True
                    if not traded_long:
                        armed_long_fade = True

        if not in_trade and not breakout_this_bar and not bar_blackout:
            short_hit = armed_short_fade and l <= short_fade_trig
            long_hit = armed_long_fade and h >= long_fade_trig
            if short_hit and long_hit:
                audit.append({'event': 'ambiguous_bar', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'both_fade_entries'})
                mid = (rh + rl) / 2.0
                if opn >= mid:
                    push_fade_fill('Short', short_fade_fill, ts, rl, rh + range_val)
                else:
                    push_fade_fill('Long', long_fade_fill, ts, rh, rl - range_val)
                in_trade = True
                armed_short_fade = False
                armed_long_fade = False
            elif short_hit:
                push_fade_fill('Short', short_fade_fill, ts, rl, rh + range_val)
                in_trade = True
                armed_short_fade = False
            elif long_hit:
                push_fade_fill('Long', long_fade_fill, ts, rh, rl - range_val)
                in_trade = True
                armed_long_fade = False

        if in_trade and direction is not None:
            if bar_blackout:
                audit.append({'event': 'blackout_skip', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'child_window'})
                cancel_pending('blackout')
            closed = False
            last_px = 0.0
            res_lab = ''
            target_now = target_hit(direction, h, l, float(target), tick, execution)
            wide_stop_now = stop_hit(direction, h, l, float(stop))
            if target_now and wide_stop_now:
                audit.append({'event': 'ambiguous_bar', 'symbol': sym, 'candidate_time': ts.isoformat(), 'reason': 'target_and_stop'})

            if execution.ambiguity_policy == 'adverse':
                if wide_stop_now:
                    last_px = stop_exit_price(direction, float(stop), tick, execution)
                    closed = True
                    res_lab = 'Loss'
                elif direction == 'Long' and len(entries) > 1 and l <= rh and l > float(stop):
                    exit_px_ch = stop_exit_price(direction, rh, tick, execution)
                    for e in entries[1:]:
                        realized_pl_pts += exit_px_ch - e
                    realized_fee_units += len(entries) - 1
                    entries[:] = entries[:1]
                    fill_times[:] = fill_times[:1]
                    cancel_pending('partial_child_stop')
                elif direction == 'Short' and len(entries) > 1 and h >= rl and h < float(stop):
                    exit_px_ch = stop_exit_price(direction, rl, tick, execution)
                    for e in entries[1:]:
                        realized_pl_pts += e - exit_px_ch
                    realized_fee_units += len(entries) - 1
                    entries[:] = entries[:1]
                    fill_times[:] = fill_times[:1]
                    cancel_pending('partial_child_stop')
                elif target_now:
                    last_px = float(target)
                    closed = True
                    res_lab = 'Win'
            else:
                if target_now:
                    last_px = float(target)
                    closed = True
                    res_lab = 'Win'
                elif wide_stop_now:
                    last_px = stop_exit_price(direction, float(stop), tick, execution)
                    closed = True
                    res_lab = 'Loss'
                elif direction == 'Long' and len(entries) > 1 and l <= rh and l > float(stop):
                    exit_px_ch = stop_exit_price(direction, rh, tick, execution)
                    for e in entries[1:]:
                        realized_pl_pts += exit_px_ch - e
                    realized_fee_units += len(entries) - 1
                    entries[:] = entries[:1]
                    fill_times[:] = fill_times[:1]
                    cancel_pending('partial_child_stop')
                elif direction == 'Short' and len(entries) > 1 and h >= rl and h < float(stop):
                    exit_px_ch = stop_exit_price(direction, rl, tick, execution)
                    for e in entries[1:]:
                        realized_pl_pts += e - exit_px_ch
                    realized_fee_units += len(entries) - 1
                    entries[:] = entries[:1]
                    fill_times[:] = fill_times[:1]
                    cancel_pending('partial_child_stop')

            if closed:
                finalize_leg(ts, last_px, res_lab)
            elif not bar_blackout:
                maybe_fill_pending_child(ts, h, l)
                maybe_arm_child_after_bar(ts)

            if traded_long and traded_short:
                break
            if len(legs_out) >= MAX_TRADES_PER_DAY:
                break

    if in_trade and direction is not None and last_bar is not None and last_ts is not None:
        cancel_pending('eod')
        eod_price = float(last_bar['close'])
        avg_e = sum(entries) / len(entries)
        if direction == 'Long':
            res = 'EOD-Win' if eod_price > avg_e else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod_price < avg_e else 'EOD-Loss'
        finalize_leg(last_ts, eod_price, res)

    return legs_out, audit


_HELP_EPILOG = """\
Example runs:
  cd potions/mnq/v2d
  python3 orb_adaptive_50_150_child.py --max-child-adds 0 --out /tmp/adaptive_child_0.csv
  python3 orb_adaptive_50_150_child.py --max-child-adds 1 \\
      --out mnq_orb_results_adaptive_50_150_child.csv
  python3 orb_adaptive_50_150_child.py --max-child-adds 2 \\
      --out mnq_orb_results_adaptive_50_150_child_3max.csv

Outputs:
  CSV (--out): one row per leg with Regime (v2b/v2d), MA_fast_prev, MA_slow_prev,
    same leg columns as v2b_child (Tier1_Entry, TP_Price, Stop_Price, Child_*, Net_$).
  Stdout: leg counts by regime, Σ Net_$, win rate, max DD, child-add rate when N>0.
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


def run_adaptive_child_backtest(
    df: pd.DataFrame,
    *,
    regime_v2b: pd.Series,
    ma_fast: pd.Series,
    ma_slow: pd.Series,
    max_child_adds: int,
    slip_ticks: int,
    child_partial_stop: str,
    child_engine: ChildEngine,
    execution: ExecutionParams,
    child_filters: ChildFilterParams,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, Any]] = []
    audit_rows: List[Dict[str, Any]] = []

    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        if day not in regime_v2b.index:
            continue
        is_v2b = bool(regime_v2b.loc[day])
        ma_f = ma_fast.loc[day] if day in ma_fast.index else None
        ma_s = ma_slow.loc[day] if day in ma_slow.index else None

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
        regime_lab = 'v2b' if is_v2b else 'v2d'

        if is_v2b:
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
                    child_partial_stop=child_partial_stop,  # type: ignore[arg-type]
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
                    child_partial_stop=child_partial_stop,  # type: ignore[arg-type]
                )
        else:
            if child_engine == 'legacy':
                legs = simulate_day_v2d_child(trade_bars, b5, rh, rl, rv, TICK, slip_ticks, max_child_adds, sym)
                audit = []
            else:
                legs, audit = simulate_day_v2d_child_chronological(
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
                )

        for a in audit:
            audit_rows.append({'Date': day, 'Regime': regime_lab, **a})
        for leg in legs:
            rows.append(
                {
                    'Date': day,
                    'Day_of_Week': pd.Timestamp(day).strftime('%A'),
                    'Regime': regime_lab,
                    'MA_fast_prev': round(ma_f, 2) if ma_f is not None else None,
                    'MA_slow_prev': round(ma_s, 2) if ma_s is not None else None,
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
        cols_first = ['Date', 'Regime', 'MA_fast_prev', 'MA_slow_prev', 'Day_of_Week', 'Symbol']
        rest = [c for c in out_df.columns if c not in cols_first]
        out_df = out_df[cols_first + rest]
    return out_df, pd.DataFrame(audit_rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Adaptive 50/150 + v2b_child scale-ins (unified sim)',
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _here = Path(__file__).resolve().parent
    ap.add_argument(
        '--out',
        type=str,
        default=str(_here / 'mnq_orb_results_adaptive_50_150_child.csv'),
        help='Output CSV path',
    )
    ap.add_argument('--max-child-adds', type=int, default=1, choices=[0, 1, 2])
    ap.add_argument('--slip-ticks', type=int, default=1)
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
        help='v2b regime only: child partial exit level (same flag as orb_open_limit_v2b_child)',
    )
    args = ap.parse_args()
    out_path = Path(args.out)
    max_child_adds = int(args.max_child_adds)
    slip_ticks = int(args.slip_ticks)
    child_partial_stop = args.child_partial_stop
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

    regime_v2b, ma_fast, ma_slow = daily_close_ma(roll_params)

    df = load_one_min_mnq(roll_params=roll_params)
    out_df, audit_df = run_adaptive_child_backtest(
        df,
        regime_v2b=regime_v2b,
        ma_fast=ma_fast,
        ma_slow=ma_slow,
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
    n_v2b = (out_df['Regime'] == 'v2b').sum()
    n_v2d = (out_df['Regime'] == 'v2d').sum()
    print(f'Wrote {len(out_df)} legs -> {out_path}')
    print(
        f'  max_child_adds={max_child_adds}  slip_ticks={slip_ticks}  '
        f'child_partial_stop(v2b)={child_partial_stop}  child_engine={child_engine}  '
        f'execution_profile={execution.profile}  roll_mode={roll_params.mode}'
    )
    print(f'  legs Regime=v2b: {n_v2b}   Regime=v2d: {n_v2d}')
    print(f'  Σ Net_$ ${out_df["Net_$"].sum():,.2f}   win-rate Net_$>0: {wins/len(out_df)*100:.1f}%')
    eq = out_df['Net_$'].cumsum()
    print(f'  Max DD Net_$ ${(eq - eq.cummax()).min():,.2f}')
    if max_child_adds > 0 and 'Child_Add' in out_df.columns:
        n_child = (out_df['Child_Add'] == True).sum()
        print(f'  legs with ≥1 child add: {100.0 * n_child / len(out_df):.1f}%')
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
            sdf, sad = run_adaptive_child_backtest(
                df,
                regime_v2b=regime_v2b,
                ma_fast=ma_fast,
                ma_slow=ma_slow,
                max_child_adds=max_child_adds,
                slip_ticks=slip_ticks,
                child_partial_stop=child_partial_stop,
                child_engine='chronological',
                execution=ep,
                child_filters=child_filters,
            )
            leg_sum = summarize_legs(sdf)
            audit_sum = summarize_audit(sad)
            v2b_net = float(sdf.loc[sdf['Regime'] == 'v2b', 'Net_$'].sum()) if not sdf.empty else 0.0
            v2d_net = float(sdf.loc[sdf['Regime'] == 'v2d', 'Net_$'].sum()) if not sdf.empty else 0.0
            stress_rows.append({'profile': profile, **leg_sum, **audit_sum, 'v2b_net': v2b_net, 'v2d_net': v2d_net})
        scsv, smd = write_stress_outputs(out_path, stress_rows, title='adaptive v2b_child/v2d execution stress')
        print(f'  Wrote execution stress -> {scsv} and {smd}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
