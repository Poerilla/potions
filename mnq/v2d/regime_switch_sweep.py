#!/usr/bin/env python3
"""
v2b/v2d regime-switch backtests.

Three signal families, all causally honest (signal at day t uses only
data through day t-1).

  A. Sign switch:
       if v2b's rolling N-day P/L > 0  -> trade v2b today
       else                              -> trade v2d today

  B. EMA-smoothed gradient switch:
       smooth v2b's rolling N-day P/L with span S
       if slope of smoothed series > 0 -> v2b today
       else                             -> v2d today

  C. Reference baselines:
       - v2b alone
       - v2d alone
       - 1:1 parallel mix
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


def sign_switch(both, N):
    roll = both['v2b'].rolling(N).sum().shift(1)
    pick_v2b = (roll > 0).fillna(True)
    return both['v2b'].where(pick_v2b, both['v2d']), pick_v2b.mean() * 100


def gradient_switch(both, N, span):
    roll = both['v2b'].rolling(N).sum()
    smoothed = roll.ewm(span=span, adjust=False).mean()
    slope = smoothed.diff().shift(1)
    pick_v2b = (slope > 0).fillna(True)
    return both['v2b'].where(pick_v2b, both['v2d']), pick_v2b.mean() * 100


def main():
    v2b = daily(V2B_CSV).rename('v2b')
    v2d = daily(V2D_CSV).rename('v2d')
    both = pd.concat([v2b, v2d], axis=1).fillna(0)
    print(f"Loaded {len(both)} days ({both.index[0]} -> {both.index[-1]})")

    rows = []
    rows.append(stats(both['v2b'],            'BASELINE: v2b alone'))
    rows.append(stats(both['v2d'],            'BASELINE: v2d alone'))
    rows.append(stats(both['v2b'] + both['v2d'], 'BASELINE: 1:1 parallel'))

    for N in (20, 40, 60, 90, 120, 180, 250):
        s, pct = sign_switch(both, N)
        st = stats(s, f"SIGN  N={N:>3}")
        st['v2b_pct'] = round(pct, 1)
        rows.append(st)

    for N in (30, 60, 90):
        for S in (3, 5, 10, 20):
            s, pct = gradient_switch(both, N, S)
            st = stats(s, f"GRAD  N={N:>3} EMA={S:>2}")
            st['v2b_pct'] = round(pct, 1)
            rows.append(st)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / 'regime_switch_sweep.csv', index=False)

    print("\n" + "=" * 100)
    print(f"{'Config':<28} {'Final $':>10} {'Annual':>9} {'MaxDD':>9} "
          f"{'σ':>5} {'Sharpe':>7} {'Calmar':>7} {'v2b%':>6}")
    print("-" * 100)
    for _, r in df.iterrows():
        pct = f"{r['v2b_pct']:.1f}%" if not pd.isna(r.get('v2b_pct', np.nan)) else "-"
        print(f"{r['config']:<28} ${r['final']:>+8,.0f} ${r['annual']:>+7,.0f} "
              f"${r['max_dd']:>7,.0f} ${r['sigma']:>3.0f} {r['sharpe']:>+7.2f} "
              f"{r['calmar']:>7.2f} {pct:>6}")

    print("\n=== TOP 5 BY SHARPE ===")
    for _, r in df.nlargest(5, 'sharpe').iterrows():
        print(f"  {r['config']:<28} Sharpe={r['sharpe']:+.2f}  "
              f"Final=${r['final']:+,.0f}  DD=${r['max_dd']:,.0f}")
    print("\n=== TOP 5 BY FINAL P/L ===")
    for _, r in df.nlargest(5, 'final').iterrows():
        print(f"  {r['config']:<28} Final=${r['final']:+,.0f}  "
              f"Sharpe={r['sharpe']:+.2f}  DD=${r['max_dd']:,.0f}")

    # Year-by-year for top candidates
    print("\n=== YEAR-BY-YEAR FOR TOP CANDIDATES ===")
    candidates = [
        ('v2b alone', both['v2b']),
        ('1:1 parallel', both['v2b'] + both['v2d']),
    ]
    for N in (60, 90, 120):
        s, _ = sign_switch(both, N)
        candidates.append((f'SIGN N={N}', s))
    for N, S in [(60, 5), (60, 10), (90, 10)]:
        s, _ = gradient_switch(both, N, S)
        candidates.append((f'GRAD N={N} S={S}', s))

    yr_rows = {}
    for label, s in candidates:
        s = s.copy()
        s.index = pd.to_datetime(s.index)
        yr_rows[label] = s.groupby(s.index.year).sum()
    yr_df = pd.DataFrame(yr_rows).round(0).astype(int)
    print(yr_df.to_string())

    with open(OUT_DIR / 'regime_switch_sweep.txt', 'w') as f:
        f.write(df.round(2).to_string(index=False))
        f.write("\n\nYEAR-BY-YEAR\n")
        f.write(yr_df.to_string())


if __name__ == '__main__':
    main()
