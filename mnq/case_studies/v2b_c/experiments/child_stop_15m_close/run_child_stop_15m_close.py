#!/usr/bin/env python3
"""v2b_c experiment: child partial stop only on 15m close back inside OR."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


HERE = Path(__file__).resolve().parent
V2B_CHILD = HERE.parents[2] / 'v2b_child'
if str(V2B_CHILD) not in sys.path:
    sys.path.insert(0, str(V2B_CHILD))

from orb_open_limit_v2b_child import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    MAX_TRADES_PER_DAY,
    MULT,
    RANGE_END_T,
    RTH_START,
    TICK,
    _EPS,
    collect_child_orders,
    load_one_min_mnq,
    resample_5m,
)


BASE_CSV = V2B_CHILD / 'mnq_orb_open_limit_v2b_child_3max.csv'
OUT_CSV = HERE / 'mnq_orb_open_limit_v2b_child_3max_15m_close_child_stop.csv'
REPORT = HERE / 'README.md'


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
    partial_child_exits = None
    if not df.empty and 'Child_Partial_Exit_Count' in df:
        partial_child_exits = int(df['Child_Partial_Exit_Count'].fillna(0).astype(float).sum())
    return {
        'legs': int(len(df)),
        'net': float(pnl.sum()),
        'dd': max_dd(pnl),
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'pf': profit_factor(pnl),
        'child_add_rate': float(df['Child_Add'].astype(bool).mean()) if not df.empty and 'Child_Add' in df else math.nan,
        'avg_contracts': float(df['Contracts'].astype(float).mean()) if not df.empty and 'Contracts' in df else math.nan,
        'partial_child_exits': partial_child_exits,
    }


def is_completed_15m_bar(ts: pd.Timestamp) -> bool:
    anchor = ts.normalize() + pd.Timedelta(hours=9, minutes=30)
    mins = int((pd.Timestamp(ts) - anchor).total_seconds() // 60)
    return mins >= 0 and (mins + 1) % 15 == 0


def close_inside_child_boundary(direction: str, close_px: float, rh: float, rl: float) -> bool:
    if direction == 'Long':
        return close_px <= rh + _EPS
    return close_px >= rl - _EPS


def simulate_day_preplaced_child_15m_close_stop(
    trade_bars: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    tick: float,
    slip_ticks: int,
    max_child_adds: int,
    sym: str,
) -> List[Dict[str, Any]]:
    """OCO parent + children, but child partial exit needs a 15m close inside OR."""
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
    stop = 0.0
    entries: List[float] = []
    fill_times: List[pd.Timestamp] = []
    child_orders: List[Tuple[float, pd.Timestamp]] = []
    child_orders_snapshot: List[Tuple[float, pd.Timestamp]] = []
    all_fill_prices: List[float] = []
    all_fill_times: List[pd.Timestamp] = []
    realized_pl_pts = 0.0
    realized_fee_units = 0
    max_contracts_in_leg = 0
    child_partial_exit_count = 0
    child_partial_exit_time = ''
    child_partial_exit_price = ''
    child_partial_exit_reason = ''
    legs_out: List[Dict[str, Any]] = []

    def emit_row(
        exit_ts: pd.Timestamp,
        exit_px: float,
        res_lab: str,
        final_entries: List[float],
        final_fill_times: List[pd.Timestamp],
    ) -> None:
        nonlocal phase, arm_long, arm_short, direction, realized_pl_pts, realized_fee_units, max_contracts_in_leg
        nonlocal child_partial_exit_count, child_partial_exit_time, child_partial_exit_price, child_partial_exit_reason
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
                'Child_Partial_Stop': '15m_close_inside',
                'Child_Partial_Exit_Count': child_partial_exit_count,
                'Child_Partial_Exit_Time': child_partial_exit_time,
                'Child_Partial_Exit_Price': child_partial_exit_price,
                'Child_Partial_Exit_Reason': child_partial_exit_reason,
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
        child_partial_exit_count = 0
        child_partial_exit_time = ''
        child_partial_exit_price = ''
        child_partial_exit_reason = ''
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
        ts = pd.Timestamp(ts)
        last_ts = ts
        h, l = float(bar['high']), float(bar['low'])
        opn = float(bar['open'])
        c = float(bar['close'])
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

                if direction == 'Long':
                    if h >= target:
                        last_px = target
                        closed = True
                        res_lab = 'Win'
                    elif l <= stop:
                        last_px = stop
                        closed = True
                        res_lab = 'Loss'
                    elif len(entries) > 1 and is_completed_15m_bar(ts) and close_inside_child_boundary(direction, c, rh, rl) and c > stop:
                        child_count = len(entries) - 1
                        exit_px_ch = c
                        for e in entries[1:]:
                            realized_pl_pts += exit_px_ch - e
                        realized_fee_units += child_count
                        entries[:] = entries[:1]
                        fill_times[:] = fill_times[:1]
                        child_orders.clear()
                        child_partial_exit_count += child_count
                        child_partial_exit_time = ts.isoformat()
                        child_partial_exit_price = f'{exit_px_ch:.4f}'
                        child_partial_exit_reason = '15m_close_inside'
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
                    elif len(entries) > 1 and is_completed_15m_bar(ts) and close_inside_child_boundary(direction, c, rh, rl) and c < stop:
                        child_count = len(entries) - 1
                        exit_px_ch = c
                        for e in entries[1:]:
                            realized_pl_pts += e - exit_px_ch
                        realized_fee_units += child_count
                        entries[:] = entries[:1]
                        fill_times[:] = fill_times[:1]
                        child_orders.clear()
                        child_partial_exit_count += child_count
                        child_partial_exit_time = ts.isoformat()
                        child_partial_exit_price = f'{exit_px_ch:.4f}'
                        child_partial_exit_reason = '15m_close_inside'
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


def run_backtest(df: pd.DataFrame, *, max_child_adds: int, slip_ticks: int) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
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
        legs = simulate_day_preplaced_child_15m_close_stop(
            trade_bars,
            b5,
            rh,
            rl,
            rv,
            TICK,
            slip_ticks,
            max_child_adds,
            sym,
        )
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
    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
        out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    return out


def write_report(base: pd.DataFrame | None, variant: pd.DataFrame, out_path: Path) -> None:
    rows = []
    if base is not None and not base.empty:
        rows.append({'label': 'base v2b_c / v2b_child edge child stop', 'stats': summarize(base), 'path': BASE_CSV})
    rows.append({'label': '15m close-inside child stop', 'stats': summarize(variant), 'path': out_path})

    lines = [
        '# v2b_c Child Stop 15m Close-Inside Experiment',
        '',
        'This experiment keeps tier-1 v2b OCO entry, targets, wide parent stops, and child limit rules unchanged.',
        '',
        'Only the child partial-stop rule changes:',
        '',
        '- Base v2b_c: child contracts are stopped on an intrabar touch of the near OR boundary: RH for long children, RL for short children.',
        '- This variant: child contracts are stopped only after a completed 15-minute candle closes back inside that boundary.',
        '- Long child exit trigger: 15-minute close `<= RH`; child exits at that close.',
        '- Short child exit trigger: 15-minute close `>= RL`; child exits at that close.',
        '- Parent/tier-1 contract still uses the original wide v2b stop: RL for longs, RH for shorts.',
        '',
        '| Variant | Legs | Net | Max DD | Win rate | PF | Child add rate | Avg contracts | Child partial exits | CSV |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        s = row['stats']
        partial_exits = 'n/a' if s['partial_child_exits'] is None else str(s['partial_child_exits'])
        lines.append(
            f"| {row['label']} | {s['legs']} | {fmt_money(s['net'])} | {fmt_money(s['dd'])} | "
            f"{fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | {fmt_pct(s['child_add_rate'])} | "
            f"{fmt_num(s['avg_contracts'])} | {partial_exits} | `{row['path']}` |"
        )
    lines.append('')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=OUT_CSV)
    ap.add_argument('--base', type=Path, default=BASE_CSV)
    ap.add_argument('--max-child-adds', type=int, default=2, choices=[0, 1, 2])
    ap.add_argument('--slip-ticks', type=int, default=1)
    args = ap.parse_args()

    df = load_one_min_mnq()
    out = run_backtest(df, max_child_adds=args.max_child_adds, slip_ticks=args.slip_ticks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    base_df = pd.read_csv(args.base) if args.base.exists() else None
    write_report(base_df, out, args.out)

    s = summarize(out)
    print(
        f"15m close-inside child stop: {len(out)} legs, {fmt_money(s['net'])}, "
        f"DD {fmt_money(s['dd'])}, WR {fmt_pct(s['win_rate'])}, PF {fmt_num(s['pf'])}, "
        f"child partial exits {s['partial_child_exits']}, wrote {args.out}"
    )
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
