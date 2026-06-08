#!/usr/bin/env python3
"""Adaptive 50/150 study with v2b inside-opposite limit parent entries.

The adaptive router is unchanged:

* prior-day MA50 > MA150 -> v2b regime
* otherwise -> v2d regime

Only the v2b parent entry changes. Instead of pre-placed OR breakout stops, v2b
waits for a 5-minute breakout close, then places a parent limit at the most
recent consecutive opposite-color 5-minute candle/run that is fully inside the
opening range. v2d remains the existing child-enabled fade simulator.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from orb_adaptive_50_150_child import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    MAX_TRADES_PER_DAY,
    MULT,
    RANGE_END_T,
    RTH_START,
    TICK,
    _EPS,
    collect_child_orders,
    daily_close_ma,
    load_one_min_mnq,
    make_child_filter_params,
    resample_5m,
    simulate_day_v2d_child,
)

_MNQ_ROOT = Path(__file__).resolve().parent.parent
if str(_MNQ_ROOT) not in sys.path:
    sys.path.insert(0, str(_MNQ_ROOT))

from lib.execution import (  # noqa: E402
    DEFAULT_ROLL_CALENDAR,
    ChildFilterParams,
    ExecutionParams,
    RollParams,
    execution_params_for_profile,
)


InsidePrice = Literal['open', 'close']
ChildPartialStopMode = Literal['edge', 'mid']

REPORT = _MNQ_ROOT / 'case_studies' / 'v2b_child' / 'ADAPTIVE_INSIDE_V2B_STUDY.md'


def fmt_money(v: float) -> str:
    return f'${v:,.2f}'


def fmt_num(v: float) -> str:
    if math.isnan(v):
        return 'n/a'
    if math.isinf(v):
        return 'inf'
    return f'{v:,.2f}'


def fmt_pct(v: float) -> str:
    return 'n/a' if math.isnan(v) else f'{v:.2%}'


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = values.astype(float).cumsum()
    return float((eq - eq.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def summarize(df: pd.DataFrame) -> dict:
    pnl = df['Net_$'].astype(float) if not df.empty else pd.Series(dtype=float)
    return {
        'legs': int(len(df)),
        'net': float(pnl.sum()),
        'dd': max_dd(pnl),
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'pf': profit_factor(pnl),
        'v2b_legs': int((df['Regime'] == 'v2b').sum()) if not df.empty and 'Regime' in df else 0,
        'v2d_legs': int((df['Regime'] == 'v2d').sum()) if not df.empty and 'Regime' in df else 0,
        'v2b_net': float(df.loc[df['Regime'] == 'v2b', 'Net_$'].sum()) if not df.empty and 'Regime' in df else 0.0,
        'v2d_net': float(df.loc[df['Regime'] == 'v2d', 'Net_$'].sum()) if not df.empty and 'Regime' in df else 0.0,
        'child_add_rate': float(df['Child_Add'].astype(bool).mean()) if not df.empty and 'Child_Add' in df else math.nan,
    }


def _child_partial_px(direction: str, rh: float, rl: float, mode: ChildPartialStopMode) -> float:
    if mode == 'edge':
        return rh if direction == 'Long' else rl
    return (rh + rl) / 2.0


def is_inside_opposite_5m(row: pd.Series, direction: str, rh: float, rl: float) -> bool:
    o = float(row['open'])
    h = float(row['high'])
    l = float(row['low'])
    c = float(row['close'])
    if h > rh + _EPS or l < rl - _EPS:
        return False
    if direction == 'Long':
        return c < o - _EPS
    return c > o + _EPS


def inside_opposite_5m_entry(
    history: list[tuple[pd.Timestamp, pd.Series]],
    direction: str,
    rh: float,
    rl: float,
    price_field: InsidePrice,
) -> dict | None:
    i = len(history) - 1
    while i >= 0 and not is_inside_opposite_5m(history[i][1], direction, rh, rl):
        i -= 1
    if i < 0:
        return None

    run: list[tuple[pd.Timestamp, pd.Series]] = []
    while i >= 0 and is_inside_opposite_5m(history[i][1], direction, rh, rl):
        run.append(history[i])
        i -= 1

    key = lambda item: float(item[1][price_field])
    chosen_ts, chosen = max(run, key=key) if direction == 'Long' else min(run, key=key)
    return {
        'price': float(chosen[price_field]),
        'price_field': price_field,
        'ts': chosen_ts,
        'start_ts': run[-1][0],
        'end_ts': run[0][0],
        'count': len(run),
        'open': float(chosen['open']),
        'high': float(chosen['high']),
        'low': float(chosen['low']),
        'close': float(chosen['close']),
        'run_high': max(float(row['high']) for _, row in run),
        'run_low': min(float(row['low']) for _, row in run),
    }


def valid_long_breakout_5m(row: pd.Series, rh: float) -> bool:
    return float(row['close']) > rh + _EPS and float(row['close']) > float(row['open']) + _EPS


def valid_short_breakout_5m(row: pd.Series, rl: float) -> bool:
    return float(row['close']) < rl - _EPS and float(row['close']) < float(row['open']) - _EPS


def build_inside_parent_candidates(
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    price_field: InsidePrice,
) -> list[dict]:
    history: list[tuple[pd.Timestamp, pd.Series]] = []
    candidates: list[dict] = []
    for ts5, row in bars5_full.iterrows():
        ts5 = pd.Timestamp(ts5)
        bar_end = ts5 + pd.Timedelta(minutes=5)
        if ts5.time() >= RANGE_END_T:
            for direction in ('Long', 'Short'):
                is_breakout = valid_long_breakout_5m(row, rh) if direction == 'Long' else valid_short_breakout_5m(row, rl)
                if not is_breakout:
                    continue
                found = inside_opposite_5m_entry(history, direction, rh, rl, price_field)
                if found is None:
                    continue
                candidates.append(
                    {
                        'direction': direction,
                        'live_ts': bar_end,
                        'breakout_ts': ts5,
                        'breakout_close': float(row['close']),
                        'entry': float(found['price']),
                        'source': found,
                    }
                )
        history.append((ts5, row))
    return candidates


def simulate_day_v2b_inside_limit_child(
    trade_bars: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    max_child_adds: int,
    sym: str,
    *,
    inside_price: InsidePrice,
    cancel_stale_target: bool,
    child_partial_stop: ChildPartialStopMode,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """v2b parent as inside-opposite limit; child/TP/SL mechanics match v2b_child legacy."""
    candidates = build_inside_parent_candidates(bars5_full, rh, rl, inside_price)
    next_candidate = 0
    arm_long = True
    arm_short = True
    phase = 'ARMED'
    pending: Optional[Dict[str, Any]] = None
    direction: Optional[str] = None
    tier1_entry = 0.0
    target = 0.0
    stop = 0.0
    entries: list[float] = []
    fill_times: list[pd.Timestamp] = []
    child_orders: list[tuple[float, pd.Timestamp]] = []
    child_orders_snapshot: list[tuple[float, pd.Timestamp]] = []
    all_fill_prices: list[float] = []
    all_fill_times: list[pd.Timestamp] = []
    realized_pl_pts = 0.0
    realized_fee_units = 0
    max_contracts_in_leg = 0
    legs_out: list[dict[str, Any]] = []
    cancel_rows: list[dict[str, Any]] = []

    def emit_row(exit_ts: pd.Timestamp, exit_px: float, res_lab: str) -> None:
        nonlocal phase, arm_long, arm_short, direction, realized_pl_pts, realized_fee_units, max_contracts_in_leg
        nonlocal pending
        assert direction is not None and pending is None
        pl_rem = sum((exit_px - e) if direction == 'Long' else (e - exit_px) for e in entries)
        pl_pts = realized_pl_pts + pl_rem
        fee_events = realized_fee_units + len(entries)
        gross = round(pl_pts * MULT, 2)
        net = round(gross - FEE_RT * fee_events, 2)
        n_hist = len(all_fill_prices)
        snap = child_orders_snapshot
        source = fill_source
        legs_out.append(
            {
                'Trade_Direction': direction,
                'Tier1_Entry': round(tier1_entry, 4),
                'Entry_Price': round(sum(all_fill_prices) / len(all_fill_prices), 4),
                'Exit_Price': round(exit_px, 4),
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
                'Child_Partial_Stop': child_partial_stop,
                'Parent_Entry_Mode': f'inside_5m_{inside_price}_limit',
                'Parent_Breakout_Time': source['breakout_ts'].isoformat(),
                'Parent_Order_Live_After': source['live_ts'].isoformat(),
                'Parent_Breakout_Close': round(float(source['breakout_close']), 4),
                'Inside_Source_Time': source['source']['ts'].isoformat(),
                'Inside_Source_Start': source['source']['start_ts'].isoformat(),
                'Inside_Source_End': source['source']['end_ts'].isoformat(),
                'Inside_Source_Count': source['source']['count'],
                'Inside_Source_Price_Field': source['source']['price_field'],
                'Inside_Source_Open': round(source['source']['open'], 4),
                'Inside_Source_High': round(source['source']['high'], 4),
                'Inside_Source_Low': round(source['source']['low'], 4),
                'Inside_Source_Close': round(source['source']['close'], 4),
                'Inside_Source_Run_High': round(source['source']['run_high'], 4),
                'Inside_Source_Run_Low': round(source['source']['run_low'], 4),
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

    fill_source: Dict[str, Any] = {}

    def arm_pending(candidate: dict) -> None:
        nonlocal pending
        pending = candidate

    def fill_parent(ts: pd.Timestamp) -> None:
        nonlocal pending, direction, tier1_entry, target, stop, max_contracts_in_leg, phase, fill_source
        assert pending is not None
        direction = pending['direction']
        tier1_entry = float(pending['entry'])
        if direction == 'Long':
            target = rh + rv
            stop = rl
        else:
            target = rl - rv
            stop = rh
        entries[:] = [tier1_entry]
        fill_times[:] = [ts]
        all_fill_prices[:] = [tier1_entry]
        all_fill_times[:] = [ts]
        max_contracts_in_leg = 1
        fill_source = dict(pending)
        pending = None
        child_orders[:] = collect_child_orders(bars5_full, ts, direction, rh, rl, max_child_adds)
        child_orders_snapshot[:] = list(child_orders)
        phase = 'IN'

    def cancel_pending(ts: pd.Timestamp, reason: str) -> None:
        nonlocal pending
        if pending is None:
            return
        cancel_rows.append(
            {
                'symbol': sym,
                'direction': pending['direction'],
                'reason': reason,
                'cancel_time': ts.isoformat(),
                'breakout_time': pending['breakout_ts'].isoformat(),
                'order_live_after': pending['live_ts'].isoformat(),
                'entry': pending['entry'],
                'target': rh + rv if pending['direction'] == 'Long' else rl - rv,
            }
        )
        pending = None

    last_ts: Optional[pd.Timestamp] = None

    for ts, bar in trade_bars.iterrows():
        ts = pd.Timestamp(ts)
        last_ts = ts
        h, l = float(bar['high']), float(bar['low'])
        bar_time = ts.time()

        if phase == 'ARMED' and pending is None and bar_time >= EOD_CUTOFF:
            break

        while phase == 'ARMED' and pending is None and next_candidate < len(candidates):
            cand = candidates[next_candidate]
            if pd.Timestamp(cand['live_ts']) > ts:
                break
            next_candidate += 1
            if cand['direction'] == 'Long' and not arm_long:
                continue
            if cand['direction'] == 'Short' and not arm_short:
                continue
            arm_pending(cand)
            break

        if phase == 'ARMED' and pending is not None:
            if bar_time >= EOD_CUTOFF:
                cancel_pending(ts, 'eod')
                break
            pdir = str(pending['direction'])
            pentry = float(pending['entry'])
            ptarget = rh + rv if pdir == 'Long' else rl - rv
            target_before_fill = (pdir == 'Long' and h >= ptarget) or (pdir == 'Short' and l <= ptarget)
            filled = (pdir == 'Long' and l <= pentry + _EPS) or (pdir == 'Short' and h >= pentry - _EPS)
            if cancel_stale_target and target_before_fill:
                cancel_pending(ts, 'target_before_parent_fill')
                continue
            if filled:
                fill_parent(ts)

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
                    elif l <= stop:
                        last_px = stop
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and l <= tight_ch and l > stop:
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
                    elif h >= stop:
                        last_px = stop
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and h >= tight_ch and h < stop:
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
                    emit_row(exit_ts, last_px, res_lab)
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
        ets = pd.Timestamp(trade_bars.index[-1])
        avg_e = sum(entries) / len(entries)
        if direction == 'Long':
            res = 'EOD-Win' if eod_price > avg_e else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod_price < avg_e else 'EOD-Loss'
        emit_row(ets, eod_price, res)

    return legs_out, cancel_rows


def run_adaptive_inside_v2b_backtest(
    df: pd.DataFrame,
    *,
    regime_v2b: pd.Series,
    ma_fast: pd.Series,
    ma_slow: pd.Series,
    max_child_adds: int,
    slip_ticks: int,
    inside_price: InsidePrice,
    cancel_stale_target: bool,
    child_partial_stop: ChildPartialStopMode,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    cancel_rows: list[dict[str, Any]] = []

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
            legs, cancels = simulate_day_v2b_inside_limit_child(
                trade_bars,
                b5,
                rh,
                rl,
                rv,
                max_child_adds,
                sym,
                inside_price=inside_price,
                cancel_stale_target=cancel_stale_target,
                child_partial_stop=child_partial_stop,
            )
            for c in cancels:
                cancel_rows.append({'Date': day, 'Regime': regime_lab, **c})
        else:
            legs = simulate_day_v2d_child(trade_bars, b5, rh, rl, rv, TICK, slip_ticks, max_child_adds, sym)

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

    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
        out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    return out, pd.DataFrame(cancel_rows)


def write_report(
    out_df: pd.DataFrame,
    cancel_df: pd.DataFrame,
    out_path: Path,
    cancel_path: Path,
    baseline_path: Path | None,
    *,
    max_child_adds: int,
    inside_price: InsidePrice,
    cancel_stale_target: bool,
) -> None:
    rows = [
        {
            'label': f'adaptive inside-v2b {inside_price} limit',
            'stats': summarize(out_df),
            'path': out_path,
            'cancels': len(cancel_df),
        }
    ]
    if baseline_path and baseline_path.exists():
        base = pd.read_csv(baseline_path)
        rows.insert(0, {'label': 'current adaptive v2b_child/v2d', 'stats': summarize(base), 'path': baseline_path, 'cancels': None})

    lines = [
        '# Adaptive 50/150 Inside-v2b Parent Entry Study',
        '',
        'This study keeps the adaptive router and v2d implementation unchanged, but replaces v2b parent stop entries with a causal inside-opposite 5-minute limit entry.',
        '',
        'v2b inside entry rules:',
        '',
        '- Opening range remains 09:30-09:45 ET.',
        '- A v2b setup arms only after a 5-minute candle closes beyond the opening range in the breakout direction.',
        f'- Parent limit price uses the selected inside opposing candle `{inside_price}`.',
        '- Longs use the most recent consecutive red 5-minute candle/run fully inside the opening range; shorts use the most recent consecutive green run.',
        '- For a long run, the highest selected price in the run is used; for a short run, the lowest selected price is used.',
        '- Initial parent stop remains v2b-style: range low for longs, range high for shorts.',
        '- Target remains v2b-style: range high + range for longs, range low - range for shorts.',
        '- Child adds and child partial stops use the same legacy v2b_child mechanics as the current adaptive child model.',
        f'- Pending parent limits are {"cancelled" if cancel_stale_target else "not cancelled"} if TP1 trades before fill.',
        '',
        f'Max child adds: `{max_child_adds}`.',
        '',
        '| Variant | Legs | v2b legs | v2d legs | Net | Max DD | Win rate | PF | v2b net | v2d net | Child add rate | Parent cancels | CSV |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        s = row['stats']
        cancels = 'n/a' if row['cancels'] is None else str(row['cancels'])
        lines.append(
            f"| {row['label']} | {s['legs']} | {s['v2b_legs']} | {s['v2d_legs']} | "
            f"{fmt_money(s['net'])} | {fmt_money(s['dd'])} | {fmt_pct(s['win_rate'])} | "
            f"{fmt_num(s['pf'])} | {fmt_money(s['v2b_net'])} | {fmt_money(s['v2d_net'])} | "
            f"{fmt_pct(s['child_add_rate'])} | {cancels} | `{row['path']}` |"
        )
    lines.extend([
        '',
        '## Outputs',
        '',
        f'- Study CSV: `{out_path}`',
        f'- Parent cancel CSV: `{cancel_path}`',
        '',
    ])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=_HERE / 'mnq_orb_results_adaptive_50_150_inside_v2b_close_child_3max.csv')
    ap.add_argument('--cancel-out', type=Path, default=None)
    ap.add_argument('--baseline', type=Path, default=_HERE / 'mnq_orb_results_adaptive_50_150_child_3max.csv')
    ap.add_argument('--max-child-adds', type=int, default=2, choices=[0, 1, 2])
    ap.add_argument('--slip-ticks', type=int, default=1, help='Used by unchanged v2d fade arm only.')
    ap.add_argument('--inside-price', choices=['open', 'close'], default='close')
    ap.add_argument('--no-cancel-stale-target', action='store_true')
    ap.add_argument('--child-partial-stop', choices=['edge', 'mid'], default='edge')
    ap.add_argument('--roll-mode', choices=['legacy-volume', 'calendar'], default='legacy-volume')
    ap.add_argument('--roll-calendar', type=Path, default=DEFAULT_ROLL_CALENDAR)
    args = ap.parse_args()

    roll_params = RollParams(mode=args.roll_mode, calendar_path=Path(args.roll_calendar))
    # Keep this call to mirror the current adaptive script's causal daily MA source.
    regime_v2b, ma_fast, ma_slow = daily_close_ma(roll_params)
    df = load_one_min_mnq(roll_params=roll_params)
    out_df, cancel_df = run_adaptive_inside_v2b_backtest(
        df,
        regime_v2b=regime_v2b,
        ma_fast=ma_fast,
        ma_slow=ma_slow,
        max_child_adds=int(args.max_child_adds),
        slip_ticks=int(args.slip_ticks),
        inside_price=args.inside_price,  # type: ignore[arg-type]
        cancel_stale_target=not args.no_cancel_stale_target,
        child_partial_stop=args.child_partial_stop,  # type: ignore[arg-type]
    )
    if out_df.empty:
        print('No trades.')
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)
    cancel_path = args.cancel_out or args.out.with_suffix(args.out.suffix + '.parent_cancels.csv')
    cancel_df.to_csv(cancel_path, index=False)
    write_report(
        out_df,
        cancel_df,
        args.out,
        cancel_path,
        args.baseline,
        max_child_adds=int(args.max_child_adds),
        inside_price=args.inside_price,  # type: ignore[arg-type]
        cancel_stale_target=not args.no_cancel_stale_target,
    )

    s = summarize(out_df)
    print(f'Wrote {len(out_df)} legs -> {args.out}')
    print(f'Wrote parent cancels -> {cancel_path}')
    print(
        f"inside-v2b {args.inside_price}: {fmt_money(s['net'])}, DD {fmt_money(s['dd'])}, "
        f"WR {fmt_pct(s['win_rate'])}, PF {fmt_num(s['pf'])}, "
        f"v2b/v2d net {fmt_money(s['v2b_net'])}/{fmt_money(s['v2d_net'])}, cancels {len(cancel_df)}"
    )
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
