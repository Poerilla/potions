#!/usr/bin/env python3
"""
Adaptive 50/150 with v1b (limit pullback / next-bar fill) instead of v2b.

Same daily MNQ causal regime as v2 adaptive:
  - Prior day SMA(50) > SMA(150) -> v1b limit ORB trades that day
  - Else -> v2d fade trades that day

Inputs:
  mnq/v1_limit/mnq_orb_results_v1b_limit.csv  (from run_v1b_from_5min.py)
  mnq/v2d/mnq_orb_results_v2d.csv

Output:
  mnq/v1_limit/mnq_orb_results_adaptive_v1_v2d_50_150.csv
"""
from pathlib import Path

import databento as db
import pandas as pd


BASE = Path('/home/tester/hsm/potions/mnq')
DAILY_DBN = BASE / 'raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V1_CSV = BASE / 'v1_limit/mnq_orb_results_v1b_limit.csv'
V2D_CSV = BASE / 'v2d/mnq_orb_results_v2d.csv'
OUT_CSV = BASE / 'v1_limit/mnq_orb_results_adaptive_v1_v2d_50_150.csv'
FAST, SLOW = 50, 150


def daily_close():
    store = db.DBNStore.from_file(str(DAILY_DBN))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def main():
    print(f'Building adaptive v1b+v2d {FAST}/{SLOW} (MNQ daily regime) ...')
    close = daily_close()
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    regime_v1 = (ma_fast > ma_slow).shift(1).fillna(True)

    v1 = pd.read_csv(V1_CSV)
    v2d = pd.read_csv(V2D_CSV)
    for d in (v1, v2d):
        d['Date'] = pd.to_datetime(d['Date']).dt.date

    rows = []
    all_dates = sorted(set(v1['Date']) | set(v2d['Date']))
    n_v1 = n_v2d = 0
    for date in all_dates:
        if date not in regime_v1.index:
            continue
        use_v1 = bool(regime_v1.loc[date])
        ma_f = ma_fast.loc[date] if date in ma_fast.index else None
        ma_s = ma_slow.loc[date] if date in ma_slow.index else None
        src = v1 if use_v1 else v2d
        day_trades = src[src['Date'] == date]
        if use_v1:
            n_v1 += 1
        else:
            n_v2d += 1
        for _, t in day_trades.iterrows():
            row = t.to_dict()
            row['Regime'] = 'v1_limit' if use_v1 else 'v2d'
            row['MA_fast_prev'] = round(float(ma_f), 2) if pd.notna(ma_f) else None
            row['MA_slow_prev'] = round(float(ma_s), 2) if pd.notna(ma_s) else None
            rows.append(row)

    df = pd.DataFrame(rows)
    df['Cumulative_$'] = df['Net_$'].cumsum().round(2)
    df['Cumulative_PL'] = df['Trade_PL'].cumsum().round(6)
    cols_first = ['Date', 'Regime', 'MA_fast_prev', 'MA_slow_prev']
    df = df[cols_first + [c for c in df.columns if c not in cols_first]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    eq = df['Net_$'].cumsum()
    wins = (df['Trade_PL'] > 0).sum()
    print(f'\n  Wrote {len(df):,} trades -> {OUT_CSV}')
    print(f'  Days routed v1_limit: {n_v1}   v2d: {n_v2d}')
    print(f'  Net $: ${df["Net_$"].sum():,.0f}   Win%: {wins/len(df)*100:.1f}%')
    print(f'  Max realized DD: ${(eq - eq.cummax()).min():,.0f}')

    df['Year'] = pd.to_datetime(df['Date']).dt.year
    yr = df.groupby('Year').agg(
        Trades=('Net_$', 'size'),
        v1=('Regime', lambda x: (x == 'v1_limit').sum()),
        v2d=('Regime', lambda x: (x == 'v2d').sum()),
        Win_pct=('Trade_PL', lambda x: (x > 0).mean() * 100),
        NetUSD=('Net_$', 'sum'),
    )
    yr['Win_pct'] = yr['Win_pct'].round(1)
    yr['NetUSD'] = yr['NetUSD'].round(0).astype(int)
    print('\n  Year-by-year:')
    print(yr.to_string())


if __name__ == '__main__':
    main()
