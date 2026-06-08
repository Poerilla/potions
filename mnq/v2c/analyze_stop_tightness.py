#!/usr/bin/env python3
"""
v2c stop-tightness analysis.

Walks every v2b MNQ NY trade through 1-min bars to compute MAE
(maximum adverse excursion) and MFE (maximum favorable excursion)
between entry and the original outcome. Then sweeps tight-stop
levels (expressed as fractions of Range) and reports what total
P/L would have been at each tightness.

Goal: find the optimal tight stop for a "no-lookback breakout" variant.

Outputs:
  mnq/v2c/v2c_trade_excursions.csv   (per-trade MAE/MFE in pts and R)
  mnq/v2c/v2c_stop_sweep.csv         (P/L by stop tightness)
  mnq/v2c/v2c_stop_sweep.txt         (formatted summary)
"""
import os
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz


NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
CSV_FILE = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
OUT_DIR  = Path('/home/tester/hsm/potions/mnq/v2c')

TICK = 0.25
MULT = 2.00
FEE_RT = 1.50  # round-turn

# Stop tightness levels (as fraction of Range). 1.0R = the original v2b stop.
STOP_LEVELS = [0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00]


def load_dbn():
    print(f"Loading DBN ({DBN_FILE}) ...")
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (df.groupby(['date', 'symbol'])['volume'].sum()
            .groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict())
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= time(9, 30)) & (df['t'] < time(16, 0))].copy()
    df = df.set_index('ts_event').sort_index()
    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f"  {len(by_date):,} days loaded")
    return by_date


def find_entry_time(df1, rh, rl, prior_exit, direction):
    """Find first 1-min bar where the trigger fires after prior_exit."""
    after = df1[df1.index > prior_exit]
    long_trig = rh + TICK
    short_trig = rl - TICK
    for ts, bar in after.iterrows():
        if direction == 'Long' and bar['high'] >= long_trig:
            return ts
        if direction == 'Short' and bar['low'] <= short_trig:
            return ts
    return after.index[0] if not after.empty else df1.index[-1]


def walk_trade(df1, entry_time, direction, entry_price, target, stop):
    """
    Walk 1-min bars from entry_time until target or stop is hit (or EOD).
    Returns (exit_time, mae_pts, mfe_pts, terminated_by) where terminated_by ∈ {'Win','Loss','EOD'}.
    MAE = max adverse excursion in pts (always >= 0).
    MFE = max favorable excursion in pts.
    """
    after = df1[df1.index >= entry_time]
    mae = 0.0
    mfe = 0.0
    for ts, bar in after.iterrows():
        h, l = bar['high'], bar['low']
        if direction == 'Long':
            cur_mae = max(0.0, entry_price - l)
            cur_mfe = max(0.0, h - entry_price)
            mae = max(mae, cur_mae)
            mfe = max(mfe, cur_mfe)
            if l < stop:    return ts, mae, mfe, 'Loss'
            if h >= target: return ts, mae, mfe, 'Win'
        else:
            cur_mae = max(0.0, h - entry_price)
            cur_mfe = max(0.0, entry_price - l)
            mae = max(mae, cur_mae)
            mfe = max(mfe, cur_mfe)
            if h > stop:    return ts, mae, mfe, 'Loss'
            if l <= target: return ts, mae, mfe, 'Win'
    return after.index[-1] if not after.empty else df1.index[-1], mae, mfe, 'EOD'


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv = pd.read_csv(CSV_FILE)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    print(f"Loaded {len(csv):,} v2b MNQ NY trades")

    by_date = load_dbn()

    # Per-trade enrichment
    enriched = []
    for date, g in csv.groupby('Date'):
        g = g.reset_index(drop=True)
        if date not in by_date:
            continue
        df1 = by_date[date]
        prior_exit = df1[df1.index.time < time(9, 45)].index[-1] if not df1[df1.index.time < time(9, 45)].empty else df1.index[0]
        for _, r in g.iterrows():
            d = r['Trade_Direction']
            rh, rl = r['Range_High'], r['Range_Low']
            rv = rh - rl
            entry = r['Entry_Price']
            target = rh + rv if d == 'Long' else rl - rv
            stop = rl if d == 'Long' else rh

            entry_time = find_entry_time(df1, rh, rl, prior_exit, d)
            exit_time, mae, mfe, term = walk_trade(df1, entry_time, d, entry, target, stop)
            enriched.append({
                'Date': date, 'Direction': d, 'Range': rv,
                'Entry': entry, 'Target': target, 'OrigStop': stop,
                'OrigResult': r['Result'], 'OrigPL_pts': r['Trade_PL'],
                'MAE_pts': round(mae, 4),
                'MFE_pts': round(mfe, 4),
                'MAE_R': round(mae / rv, 4),
                'MFE_R': round(mfe / rv, 4),
                'Term': term,
                'EntryTime': entry_time, 'ExitTime': exit_time,
            })
            prior_exit = exit_time

    edf = pd.DataFrame(enriched)
    edf.to_csv(OUT_DIR / 'v2c_trade_excursions.csv', index=False)
    print(f"\nWrote {len(edf):,} rows -> v2c_trade_excursions.csv")

    # Quick MAE distribution stats
    print(f"\nMAE (in R) distribution across all v2b trades:")
    for p in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
        print(f"  P{int(p*100):>3}: {edf['MAE_R'].quantile(p):.3f}R")
    print(f"  Mean: {edf['MAE_R'].mean():.3f}R   Std: {edf['MAE_R'].std():.3f}R")

    # Sweep stop tightness
    rows = []
    for tight in STOP_LEVELS:
        # Per-trade simulation under the tight stop:
        # If MAE_R >= tight, the tight stop fires first (loss = tight × Range)
        # Else trade outcome unchanged from original
        df = edf.copy()
        df['stopped_by_tight'] = df['MAE_R'] >= tight
        # New per-trade pts P/L
        def new_pl(r):
            if r['stopped_by_tight']:
                return -tight * r['Range']
            else:
                # Use original outcome pts (which already accounts for win/loss/EOD)
                return r['OrigPL_pts']
        df['NewPL_pts'] = df.apply(new_pl, axis=1)
        df['NewNet_$'] = df['NewPL_pts'] * MULT - FEE_RT

        n = len(df)
        n_stopped = df['stopped_by_tight'].sum()
        n_orig_win = (df['OrigPL_pts'] > 0).sum()
        n_new_win = (df['NewPL_pts'] > 0).sum()
        # Distinct categories
        n_full_win = ((~df['stopped_by_tight']) & (df['OrigResult'].isin(['Win','EOD-Win']))).sum()
        n_eod = (df['OrigResult'].str.startswith('EOD') & (~df['stopped_by_tight'])).sum()

        net_pts = df['NewPL_pts'].sum()
        net_dollar = df['NewNet_$'].sum()
        eq = df['NewNet_$'].cumsum()
        max_dd = (eq - eq.cummax()).min()

        rows.append({
            'StopR': tight,
            'StopPts_avg': round(tight * df['Range'].mean(), 1),
            'Trades': n,
            'StoppedByTight': int(n_stopped),
            'StoppedPct': round(n_stopped / n * 100, 1),
            'NewWins': int(n_new_win),
            'NewWinPct': round(n_new_win / n * 100, 1),
            'Net_pts': round(net_pts, 0),
            'Net_$': round(net_dollar, 0),
            'PerTrade_$': round(net_dollar / n, 2),
            'Annual_$': round(net_dollar / 5.13, 0),  # ~5.13 yrs in MNQ data
            'MaxDD_$': round(max_dd, 0),
        })

    sw = pd.DataFrame(rows)
    sw.to_csv(OUT_DIR / 'v2c_stop_sweep.csv', index=False)

    print("\n" + "=" * 95)
    print("STOP TIGHTNESS SWEEP — MNQ NY (v2b trades, simulated under tighter stops)")
    print("=" * 95)
    print(f"{'StopR':>7} {'~pts':>6} {'Trd':>5} {'Stop%':>6} {'Win%':>6} "
          f"{'NetPts':>8} {'Net $':>10} {'$/trade':>8} {'$/yr':>9} {'MaxDD':>9}")
    print("-" * 95)
    for r in rows:
        print(f"{r['StopR']:>7.3f} {r['StopPts_avg']:>6.1f} {r['Trades']:>5} "
              f"{r['StoppedPct']:>5.1f}% {r['NewWinPct']:>5.1f}% "
              f"{r['Net_pts']:>+8,.0f} ${r['Net_$']:>+8,.0f} ${r['PerTrade_$']:>+6.2f} "
              f"${r['Annual_$']:>+7,.0f} ${r['MaxDD_$']:>+8,.0f}")

    # Find best
    best = max(rows, key=lambda r: r['Net_$'])
    print(f"\nBest by Total P/L:  StopR={best['StopR']}  Net=${best['Net_$']:+,.0f}  Annual=${best['Annual_$']:+,.0f}")

    with open(OUT_DIR / 'v2c_stop_sweep.txt', 'w') as f:
        f.write(sw.to_string(index=False))
        f.write(f"\n\nBest by Total P/L: StopR={best['StopR']} Net=${best['Net_$']:+,.0f}\n")


if __name__ == '__main__':
    main()
