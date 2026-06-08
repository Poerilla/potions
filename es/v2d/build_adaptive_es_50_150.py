#!/usr/bin/env python3
"""
Adaptive 50/150 for ES NY session: ES daily SMA(50) vs SMA(150) -> v2b vs v2d.

Reads:
  es/es_orb_results_stops.csv
  es/v2d/es_orb_results_v2d.csv
  es/raw/glbx-mdp3-20100606-20260308.ohlcv-1d (es).dbn.zst

Output:
  es/v2d/es_orb_results_adaptive_50_150.csv
"""
from pathlib import Path

import databento as db
import pandas as pd


BASE = Path('/home/tester/hsm/potions/es')
DAILY_DBN = BASE / 'raw/glbx-mdp3-20100606-20260308.ohlcv-1d (es).dbn.zst'
V2B_CSV = BASE / 'es_orb_results_stops.csv'
V2D_CSV = BASE / 'v2d/es_orb_results_v2d.csv'
OUT_CSV = BASE / 'v2d/es_orb_results_adaptive_50_150.csv'
FAST, SLOW = 50, 150


def daily_close():
    store = db.DBNStore.from_file(str(DAILY_DBN))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('ES')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def main():
    print(f'Building ES adaptive {FAST}/{SLOW} ...')
    close = daily_close()
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    regime_v2b = (ma_fast > ma_slow).shift(1).fillna(True)

    v2b = pd.read_csv(V2B_CSV)
    v2d = pd.read_csv(V2D_CSV)
    for d in (v2b, v2d):
        d['Date'] = pd.to_datetime(d['Date']).dt.date

    rows = []
    all_dates = sorted(set(v2b['Date']) | set(v2d['Date']))
    n_b = n_d = 0
    for date in all_dates:
        if date not in regime_v2b.index:
            continue
        use_v2b = bool(regime_v2b.loc[date])
        ma_f = ma_fast.loc[date] if date in ma_fast.index else None
        ma_s = ma_slow.loc[date] if date in ma_slow.index else None
        src = v2b if use_v2b else v2d
        day_trades = src[src['Date'] == date]
        if use_v2b:
            n_b += 1
        else:
            n_d += 1
        for _, t in day_trades.iterrows():
            row = t.to_dict()
            row['Regime'] = 'v2b' if use_v2b else 'v2d'
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
    print(f'  Wrote {len(df):,} trades -> {OUT_CSV}')
    print(f'  Days v2b/v2d routing: {n_b} / {n_d}')
    print(f'  Net ${df["Net_$"].sum():,.0f}  Win% {wins/len(df)*100:.1f}%')
    print(f'  Max DD ${(eq - eq.cummax()).min():,.0f}')


if __name__ == '__main__':
    main()
