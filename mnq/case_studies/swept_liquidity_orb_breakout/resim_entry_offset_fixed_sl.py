#!/usr/bin/env python3
"""
Replay filled rows from mnq_swept_orb_breakout.csv with:
  - Limit 50 pts favorable vs original brk2 close: Long at old_limit-50, Short at old_limit+50
  - SL = fixed 20 index pts from filled entry (same-bar pessimism as main backtest)
  - TP1/TP2 still +1R/+2R vs entry with R = RV (from CSV Range)

Requires DBN. Compares win rate and Net_$ to the subset that still receive a fill.
"""

from __future__ import annotations

import argparse
from datetime import time as dtime
from pathlib import Path

import databento as db
import pandas as pd
import pytz

EPS = 1e-9
NY = pytz.timezone('America/New_York')
DBN = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
T_RTH0 = dtime(9, 30)
T_RTH1 = dtime(16, 0)
T_SIM_END = dtime(15, 55)

MULT = 2.0
FEE_RT = 1.50
POSITION_SIZE = 2


def load_by_date():
    print('Loading DBN ...')
    store = db.DBNStore.from_file(DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')]
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= T_RTH0) & (df['t'] < T_RTH1)]
    df = df[df['date'] >= pd.Timestamp('2021-03-04').date()]
    df = df.set_index('ts_event').sort_index()
    return {d: g for d, g in df.groupby(df.index.date)}


def breach_brk1_classic_tp(brk1_dir: str, lvl: float, hi: float, lo: float) -> bool:
    if brk1_dir == 'Long':
        return hi >= lvl - EPS
    return lo <= lvl + EPS


def breach_limit_fill(direction: str, lim: float, hi: float, lo: float) -> bool:
    if direction == 'Long':
        return lo <= lim + EPS
    return hi >= lim - EPS


def _realized_pts(direction: str, entry: float, exit_px: float) -> float:
    return exit_px - entry if direction == 'Long' else entry - exit_px


def simulate_from_fill(
    intraday_only: pd.DataFrame,
    lim: float,
    direction: str,
    rv: float,
    sl_pts: float,
) -> tuple[float, str, float]:
    """2-lot TP1/TP2 with fixed SL distance; return (sum_pts, result, last_exit_px)."""
    d_long = direction == 'Long'
    tp1 = lim + rv if d_long else lim - rv
    tp2 = lim + 2.0 * rv if d_long else lim - 2.0 * rv
    sl_px = lim - sl_pts if d_long else lim + sl_pts

    qty = POSITION_SIZE
    sum_pts = 0.0

    def process_long(ts_, hi: float, lo: float) -> bool:
        nonlocal qty, sum_pts
        if qty <= 0:
            return True
        if lo <= sl_px + EPS:
            sum_pts += qty * (sl_px - lim)
            qty = 0
            return True
        if qty == 2:
            if hi >= tp2 - EPS:
                sum_pts += (tp1 - lim) + (tp2 - lim)
                qty = 0
                return True
            if hi >= tp1 - EPS:
                sum_pts += tp1 - lim
                qty = 1
                if lo <= sl_px + EPS:
                    sum_pts += sl_px - lim
                    qty = 0
                    return True
                if hi >= tp2 - EPS:
                    sum_pts += tp2 - lim
                    qty = 0
                    return True
            return False
        if lo <= sl_px + EPS:
            sum_pts += sl_px - lim
            qty = 0
            return True
        if hi >= tp2 - EPS:
            sum_pts += tp2 - lim
            qty = 0
            return True
        return False

    def process_short(ts_, hi: float, lo: float) -> bool:
        nonlocal qty, sum_pts
        if qty <= 0:
            return True
        if hi >= sl_px - EPS:
            sum_pts += qty * (lim - sl_px)
            qty = 0
            return True
        if qty == 2:
            if lo <= tp2 + EPS:
                sum_pts += (lim - tp1) + (lim - tp2)
                qty = 0
                return True
            if lo <= tp1 + EPS:
                sum_pts += lim - tp1
                qty = 1
                if hi >= sl_px - EPS:
                    sum_pts += lim - sl_px
                    qty = 0
                    return True
                if lo <= tp2 + EPS:
                    sum_pts += lim - tp2
                    qty = 0
                    return True
            return False
        if hi >= sl_px - EPS:
            sum_pts += lim - sl_px
            qty = 0
            return True
        if lo <= tp2 + EPS:
            sum_pts += lim - tp2
            qty = 0
            return True
        return False

    for ts, bar in intraday_only.iterrows():
        hi = float(bar['high'])
        lo = float(bar['low'])
        if d_long:
            done = process_long(ts, hi, lo)
        else:
            done = process_short(ts, hi, lo)
        if done and qty == 0:
            flat = True
            break
    else:
        flat = qty == 0

    if qty > 0:
        tail = intraday_only
        px = float(tail.iloc[-1]['close'])
        sum_pts += qty * _realized_pts(direction, lim, px)
        result_kind = 'EOD-Win' if sum_pts > EPS else 'EOD-Loss'
        last_px = px
    else:
        last_px = lim
        result_kind = 'Win' if sum_pts > EPS else 'Loss'

    return sum_pts, result_kind, last_px


def replay_row(
    row: pd.Series,
    day_df: pd.DataFrame,
    entry_pad: float,
    sl_pts: float,
) -> dict:
    """
    entry_pad: Long -> new limit at old_entry - pad; Short -> old_entry + pad
    """
    old_lim = float(row['Entry_Price'])
    direction = str(row['Trade_Direction'])
    brk1 = str(row['brk1_dir'])
    rh, rl, rv = float(row['RH']), float(row['RL']), float(row['Range'])
    sk = float(row['Skip_Level_or_ref']) if pd.notna(row.get('Skip_Level_or_ref')) else (
        rh + rv if brk1 == 'Long' else rl - rv
    )

    if direction == 'Long':
        new_lim = old_lim - entry_pad
    else:
        new_lim = old_lim + entry_pad

    sweep = pd.to_datetime(row['Sweep'])
    if sweep.tzinfo is None:
        sweep = sweep.tz_localize(NY)
    else:
        sweep = sweep.tz_convert(NY)

    t_work = sweep + pd.Timedelta(minutes=5)
    fwd = day_df[day_df.index >= t_work]
    fwd = fwd[fwd.index.map(lambda t: t.time() < T_SIM_END)]

    if fwd.empty:
        return {'status': 'no_time', 'net': 0.0}

    fill_ts = None
    for ts, bar in fwd.iterrows():
        lo, hi = float(bar['low']), float(bar['high'])
        if breach_brk1_classic_tp(brk1, sk, hi, lo):
            return {'status': 'skipped_brk1_tp', 'net': 0.0}
        if breach_limit_fill(direction, new_lim, hi, lo):
            fill_ts = ts
            break

    if fill_ts is None:
        return {'status': 'no_fill', 'net': 0.0}

    path = day_df[day_df.index >= fill_ts]
    intraday_only = path[path.index.map(lambda t: t.time() < T_SIM_END)]

    sum_pts, res, _ = simulate_from_fill(intraday_only, new_lim, direction, rv, sl_pts)
    gross = round(sum_pts * MULT, 2)
    net = round(gross - 2.0 * FEE_RT, 2)
    return {'status': 'filled', 'net': net, 'result': res, 'sum_pts': sum_pts}


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    ap.add_argument('--csv', type=str, default=str(root / 'mnq_swept_orb_breakout.csv'))
    ap.add_argument('--entry-pad', type=float, default=50.0, help='pts favorable: long -, short +')
    ap.add_argument('--sl-pts', type=float, default=20.0)
    args = ap.parse_args()

    csv = pd.read_csv(args.csv)
    filled = csv[csv['Entry_Price'].notna()].copy()

    by_d = load_by_date()

    nets = []
    statuses = []
    fills = 0
    for _, row in filled.iterrows():
        d = pd.to_datetime(row['Date']).date()
        if d not in by_d:
            statuses.append('no_day')
            nets.append(0.0)
            continue
        dd = by_d[d]
        if 'symbol' in dd.columns:
            dd = dd[dd['symbol'] == row['Symbol']]
        if dd.empty:
            statuses.append('no_sym')
            nets.append(0.0)
            continue
        out = replay_row(row, dd, args.entry_pad, args.sl_pts)
        statuses.append(out['status'])
        if out['status'] == 'filled':
            fills += 1
            nets.append(out['net'])
        else:
            nets.append(0.0)

    s = pd.Series(nets)
    filled_mask = [st == 'filled' for st in statuses]
    sf = s[filled_mask]

    print(
        f'Scenario: limit 50 pts favorable vs brk2 close (long −50 / short +50); '
        f'SL = {args.sl_pts:.0f} pts from fill; TP1/TP2 = +1R/+2R from entry (R=RV).'
    )
    print(f'Parameters: entry_pad={args.entry_pad}, sl_pts={args.sl_pts}')
    print()

    orig_net = filled['Net_$'].astype(float)
    print('--- Original backtest (baseline, same CSV rows) ---')
    print(f'  Fills: {len(filled)}   Σ Net_$ {orig_net.sum():,.2f}')
    print(f'  Win rate (Net>0): {(orig_net > 0).mean()*100:.2f}%')

    print()
    print('--- Resim with favorable offset + tight SL ---')
    print(f'  Still filled after deeper/shallower limit: {fills} / {len(filled)}')
    print(f'  No new limit fill: {statuses.count("no_fill")}')
    print(f'  Skipped (brk1 TP before fill): {statuses.count("skipped_brk1_tp")}')
    policy_total = float(s.sum())  # 0 when no new fill (no trade under new rules)
    print(f'  Σ Net_$ (new policy: trade only if offset fill; else flat): {policy_total:,.2f}')
    if fills:
        print(f'  Win rate (Net>0 | refilled): {(sf > 0).mean()*100:.2f}%')
        print(f'  Mean Net_$ / trade (refilled): {sf.mean():.2f}')

    orig_list = orig_net.tolist()
    new_list = [nets[i] for i, st in enumerate(statuses) if st == 'filled']
    old_for_filled = [orig_list[i] for i, st in enumerate(statuses) if st == 'filled']
    other_baseline = [orig_list[i] for i, st in enumerate(statuses) if st != 'filled']
    if old_for_filled and new_list and len(old_for_filled) == len(new_list):
        print()
        print('--- Cohort that *could* still get the 50pt limit (refilled) ---')
        print('  (Selection: refills skew to worse baseline outcomes; do not read as “all trades”.)')
        print(f'  n = {len(new_list)}')
        print(f'  Baseline Σ Net on this cohort: {sum(old_for_filled):,.2f}')
        print(f'  Resim Σ Net (same cohort):     {sum(new_list):,.2f}')
        print(
            f'  Baseline win rate (this cohort): {sum(1 for x in old_for_filled if x > 0) / len(old_for_filled) * 100:.2f}%'
        )
        print(f'  Resim win rate (this cohort):    {sum(1 for x in new_list if x > 0) / len(new_list) * 100:.2f}%')
    if other_baseline:
        print(f'  Baseline Σ Net on trades with **no** offset fill (skipped): {sum(other_baseline):,.2f}  (n={len(other_baseline)})')

    dfc = filled.reset_index(drop=True)
    dfc['policy_net'] = nets
    dfc = dfc.sort_values(['Date', 'Sequence_ID'])
    base_c = dfc['Net_$'].astype(float).cumsum()
    pol_c = dfc['policy_net'].cumsum()
    print()
    print('--- Cumulative $ (chronological over all {} rows) ---'.format(len(dfc)))
    print(f'  Last baseline cumulative: {base_c.iloc[-1]:,.2f}')
    print(f'  Last policy cumulative:   {pol_c.iloc[-1]:,.2f}  (no trade when offset does not fill)')
    print(f'  Max policy drawdown from peak (running): { (pol_c.cummax() - pol_c).max():,.2f}')
    print(f'  Max baseline DD from peak (running):      { (base_c.cummax() - base_c).max():,.2f}')


if __name__ == '__main__':
    main()
