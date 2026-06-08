#!/usr/bin/env python3
"""
Weekly rebalance: at every Friday close, look at the last N weeks of
v2b vs v2d P/L. For all 5 days of the upcoming week, trade whichever
performed better. Re-evaluate next Friday.

Sweep N in {1, 2, 3, 4, 6, 8, 12} weeks.

This is causally honest (signal locked at Friday close, applied to
following Mon-Fri only) and creates at most 1 flip per week instead of
daily noise.
"""
from pathlib import Path
import numpy as np
import pandas as pd

V2B_CSV = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
V2D_CSV = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv'
OUT_DIR = Path('/home/tester/hsm/potions/mnq/v2d')


def daily(csv):
    df = pd.read_csv(csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df.groupby('Date')['Net_$'].sum()


def stats(s, label):
    eq = s.cumsum()
    dd = eq - eq.cummax()
    sigma = s.std()
    sharpe = s.mean() / sigma * np.sqrt(252) if sigma > 0 else 0
    final = eq.iloc[-1]
    annual = final / (len(s) / 252) if len(s) else 0
    max_dd = abs(dd.min())
    calmar = annual / max_dd if max_dd > 0 else 0
    return {
        'config': label, 'final': final, 'annual': annual,
        'max_dd': max_dd, 'sigma': sigma, 'sharpe': sharpe, 'calmar': calmar,
    }


def weekly_rebalance(both, n_weeks):
    """
    For each ISO week, decide whether to trade v2b or v2d for that week
    based on the prior n_weeks of P/L.
    """
    df = both.copy()
    df.index = pd.to_datetime(df.index)
    # Tag each day with its ISO year-week
    iso = df.index.isocalendar()
    df['yw'] = iso['year'].astype(str) + '-' + iso['week'].astype(str).str.zfill(2)
    weekly_sum = df.groupby('yw').agg(v2b=('v2b','sum'), v2d=('v2d','sum'))
    # For each week, decision uses sum of PRIOR n_weeks (causal)
    weekly_sum['v2b_lag'] = weekly_sum['v2b'].rolling(n_weeks).sum().shift(1)
    weekly_sum['v2d_lag'] = weekly_sum['v2d'].rolling(n_weeks).sum().shift(1)
    weekly_sum['pick_v2b'] = weekly_sum['v2b_lag'] > weekly_sum['v2d_lag']
    # Default v2b during warmup (when lag is NaN)
    weekly_sum['pick_v2b'] = weekly_sum['pick_v2b'].fillna(True)

    # Apply weekly pick to each day
    pick_for_day = df['yw'].map(weekly_sum['pick_v2b'].to_dict())
    s = df['v2b'].where(pick_for_day, df['v2d'])
    flips = (weekly_sum['pick_v2b'] != weekly_sum['pick_v2b'].shift(1)).sum()
    pct_v2b = pick_for_day.mean() * 100
    return s, flips, pct_v2b


def main():
    v2b = daily(V2B_CSV).rename('v2b')
    v2d = daily(V2D_CSV).rename('v2d')
    both = pd.concat([v2b, v2d], axis=1).fillna(0)

    print(f"Loaded {len(both)} days ({both.index[0]} -> {both.index[-1]})")
    print()

    rows = []
    rows.append(stats(both['v2b'], 'BASELINE: v2b alone'))
    rows.append(stats(both['v2d'], 'BASELINE: v2d alone'))
    rows.append(stats(both['v2b'] + both['v2d'], 'BASELINE: 1:1 parallel'))
    # Adaptive 50/150 reference
    adapt = pd.read_csv('/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_adaptive_50_150.csv')
    adapt['Date'] = pd.to_datetime(adapt['Date']).dt.date
    adapt_d = adapt.groupby('Date')['Net_$'].sum()
    rows.append(stats(adapt_d, 'BASELINE: Adaptive 50/150 MA'))

    week_results = {}
    for n_weeks in (1, 2, 3, 4, 6, 8, 12):
        s, flips, pct_v2b = weekly_rebalance(both, n_weeks)
        st = stats(s, f"Weekly rebalance, {n_weeks}w lookback")
        st['flips'] = flips
        st['v2b_pct'] = pct_v2b
        rows.append(st)
        week_results[n_weeks] = s

    print("=" * 100)
    print(f"{'Config':<38} {'Final $':>10} {'Annual':>9} {'MaxDD':>9} "
          f"{'Sharpe':>7} {'Calmar':>7} {'v2b%':>7} {'Flips':>6}")
    print("-" * 100)
    for r in rows:
        flips = f"{int(r.get('flips', 0))}" if 'flips' in r else '-'
        pct = f"{r.get('v2b_pct', 0):.1f}%" if 'v2b_pct' in r else '-'
        print(f"{r['config']:<38} ${r['final']:>+8,.0f} ${r['annual']:>+7,.0f} "
              f"${r['max_dd']:>7,.0f} {r['sharpe']:>+7.2f} {r['calmar']:>7.2f} "
              f"{pct:>7} {flips:>6}")

    # Year by year
    print("\n=== YEAR-BY-YEAR ===")
    yr = {}
    yr['v2b alone'] = both['v2b']
    yr['Adaptive 50/150'] = adapt_d
    for n_weeks in (1, 2, 3, 4, 8):
        yr[f'Weekly {n_weeks}w'] = week_results[n_weeks]
    yr_df = {}
    for k, s in yr.items():
        s = s.copy()
        s.index = pd.to_datetime(s.index)
        yr_df[k] = s.groupby(s.index.year).sum()
    yr_df = pd.DataFrame(yr_df).round(0).astype(int)
    print(yr_df.to_string())

    # Save weekly trade log for the best variant for inspection
    best = max((r for r in rows if 'Weekly' in r['config']), key=lambda r: r['sharpe'])
    print(f"\nBest weekly variant: {best['config']}")
    print(f"  Final: ${best['final']:+,.0f}  Sharpe: {best['sharpe']:+.2f}  "
          f"DD: ${best['max_dd']:,.0f}  Calmar: {best['calmar']:.2f}")


if __name__ == '__main__':
    main()
