#!/usr/bin/env python3
"""
Build adaptive 50/150 (MNQ daily SMA) trade logs for multiple ORB legs.

Regime (causal, same for every leg):
  Prior calendar day's MNQ daily close: if SMA(50) > SMA(150) -> v2b else v2d.

Legs:
  MNQ NY      — mnq/mnq_orb_results_stops.csv + mnq/v2d/mnq_orb_results_v2d.csv
  MNQ London  — combined_orb/london_orb_results_stops.csv + london_orb_results_v2d.csv
  MYM NY      — combined_orb/mym_ny_orb_results_stops.csv + mym_ny_orb_results_v2d.csv

Outputs:
  mnq/v2d/mnq_orb_results_adaptive_50_150.csv       (MNQ NY, backward-compatible path)
  combined_orb/mnq_london_adaptive_50_150.csv
  combined_orb/mym_ny_adaptive_50_150.csv
  orb-portfolio/adaptive_portfolio_combined_50_150.csv  (all legs, sorted by Date/Leg)
"""
from pathlib import Path

import databento as db
import pandas as pd


BASE = Path('/home/tester/hsm/potions')
DAILY_DBN = BASE / 'mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
FAST, SLOW = 50, 150

LEGS = [
    {
        'leg': 'MNQ_NY',
        'v2b': BASE / 'mnq/mnq_orb_results_stops.csv',
        'v2d': BASE / 'mnq/v2d/mnq_orb_results_v2d.csv',
        'out': BASE / 'mnq/v2d/mnq_orb_results_adaptive_50_150.csv',
    },
    {
        'leg': 'MNQ_London',
        'v2b': BASE / 'combined_orb/london_orb_results_stops.csv',
        'v2d': BASE / 'combined_orb/london_orb_results_v2d.csv',
        'out': BASE / 'combined_orb/mnq_london_adaptive_50_150.csv',
    },
    {
        'leg': 'MYM_NY',
        'v2b': BASE / 'combined_orb/mym_ny_orb_results_stops.csv',
        'v2d': BASE / 'combined_orb/mym_ny_orb_results_v2d.csv',
        'out': BASE / 'combined_orb/mym_ny_adaptive_50_150.csv',
    },
]


def mnq_daily_close():
    store = db.DBNStore.from_file(str(DAILY_DBN))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def regime_series():
    close = mnq_daily_close()
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    regime_v2b = (ma_fast > ma_slow).shift(1).fillna(True)
    return regime_v2b, ma_fast, ma_slow


def merge_leg(v2b: pd.DataFrame, v2d: pd.DataFrame, regime_v2b, ma_fast, ma_slow, leg: str):
    v2b = v2b.copy()
    v2d = v2d.copy()
    v2b['Date'] = pd.to_datetime(v2b['Date']).dt.date
    v2d['Date'] = pd.to_datetime(v2d['Date']).dt.date
    rows = []
    all_dates = sorted(set(v2b['Date']) | set(v2d['Date']))
    n_b = n_d = 0
    for date in all_dates:
        if date not in regime_v2b.index:
            continue
        is_v2b = bool(regime_v2b.loc[date])
        ma_f = ma_fast.loc[date] if date in ma_fast.index else None
        ma_s = ma_slow.loc[date] if date in ma_slow.index else None
        src = v2b if is_v2b else v2d
        day_trades = src[src['Date'] == date]
        if is_v2b:
            n_b += 1
        else:
            n_d += 1
        for _, t in day_trades.iterrows():
            row = t.to_dict()
            row['Leg'] = leg
            row['Regime'] = 'v2b' if is_v2b else 'v2d'
            row['MA_fast_prev'] = round(float(ma_f), 2) if pd.notna(ma_f) else None
            row['MA_slow_prev'] = round(float(ma_s), 2) if pd.notna(ma_s) else None
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df, n_b, n_d
    df['Cumulative_$'] = df['Net_$'].cumsum().round(2)
    df['Cumulative_PL'] = df['Trade_PL'].cumsum().round(6)
    cols_front = ['Date', 'Leg', 'Regime', 'MA_fast_prev', 'MA_slow_prev']
    rest = [c for c in df.columns if c not in cols_front]
    df = df[cols_front + rest]
    return df, n_b, n_d


def summarize_leg(name, df):
    if df.empty:
        print(f"\n{name}: (empty)")
        return
    eq = df['Net_$'].cumsum()
    dd = (eq - eq.cummax()).min()
    wins = (df['Trade_PL'] > 0).sum()
    print(f"\n{name}: {len(df):,} trades  win {wins/len(df)*100:.1f}%  "
          f"net ${df['Net_$'].sum():,.0f}  max DD ${dd:,.0f}")


def main():
    print(f'Adaptive {FAST}/{SLOW} portfolio (MNQ daily regime for all legs)\n')
    regime_v2b, ma_fast, ma_slow = regime_series()
    combined_parts = []
    for spec in LEGS:
        leg = spec['leg']
        print(f"--- {leg} ---")
        v2b = pd.read_csv(spec['v2b'])
        v2d = pd.read_csv(spec['v2d'])
        df, n_b, n_d = merge_leg(v2b, v2d, regime_v2b, ma_fast, ma_slow, leg)
        if df.empty:
            print(f"  ERROR: no rows for {leg}; check v2b/v2d paths and date overlap.")
            continue
        spec['out'].parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(spec['out'], index=False)
        print(f"  Wrote {spec['out']}  ({len(df)} trades, regime days v2b≈{n_b} v2d≈{n_d})")
        summarize_leg(leg, df)
        combined_parts.append(df)

    if not combined_parts:
        return
    combo = pd.concat(combined_parts, ignore_index=True)
    combo['Date'] = pd.to_datetime(combo['Date'])
    combo = combo.sort_values(['Date', 'Leg']).reset_index(drop=True)
    combo['Date'] = combo['Date'].dt.date
    pcombo = BASE / 'orb-portfolio/adaptive_portfolio_combined_50_150.csv'
    pcombo.parent.mkdir(parents=True, exist_ok=True)

    # Session-style order same calendar day: London, MNQ NY, MYM NY
    leg_order = {'MNQ_London': 0, 'MNQ_NY': 1, 'MYM_NY': 2}
    combo2 = combo.copy()
    combo2['_o'] = combo2['Leg'].map(lambda L: leg_order.get(L, 9))
    combo2 = combo2.sort_values(['Date', '_o']).drop(columns=['_o'])
    combo2['Portfolio_Cumulative_$'] = combo2['Net_$'].cumsum().round(2)
    combo2.to_csv(pcombo, index=False)

    peq = combo2['Net_$'].cumsum()
    print(f"\n=== Combined file ({len(combo2)} rows) ===")
    print(f"  {pcombo}")
    print(f"  Total net ${combo2['Net_$'].sum():,.0f}  max DD ${(peq - peq.cummax()).min():,.0f}")


if __name__ == '__main__':
    main()
