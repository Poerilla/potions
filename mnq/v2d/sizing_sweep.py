#!/usr/bin/env python3
"""
v2b + v2d parallel sizing sweep.

Tests every combination of (n_v2b, n_v2d) contracts and computes:
  - Total net P/L
  - Max realized drawdown
  - Sharpe ratio (annualized)
  - Calmar ratio (annual return / max DD)
  - Margin requirement (overnight IM × total contracts)
  - Daily volatility

Then provides apples-to-apples comparison: for each combo, find the
"v2b-only equivalent" sized to the SAME max DD, and check whether
the combo produces more or less P/L per dollar of drawdown.

Output:
  mnq/v2d/sizing_sweep.csv
  mnq/v2d/sizing_sweep.txt
"""
from pathlib import Path

import numpy as np
import pandas as pd


V2B_CSV = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
V2D_CSV = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv'
OUT_DIR = Path('/home/tester/hsm/potions/mnq/v2d')

MNQ_OVERNIGHT_IM = 2100      # CME initial margin per MNQ contract


def daily_pl(csv):
    df = pd.read_csv(csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df.groupby('Date')['Net_$'].sum()


def stats(s, label):
    eq = s.cumsum()
    dd = eq - eq.cummax()
    sigma = s.std()
    sharpe = s.mean() / sigma * np.sqrt(252) if sigma > 0 else 0.0
    final = eq.iloc[-1]
    yrs = len(s) / 252
    annual = final / yrs if yrs else 0
    max_dd = abs(dd.min())
    calmar = annual / max_dd if max_dd > 0 else 0
    return {
        'config': label,
        'final':  final,
        'annual': annual,
        'max_dd': max_dd,
        'sigma':  sigma,
        'sharpe': sharpe,
        'calmar': calmar,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    v2b = daily_pl(V2B_CSV).rename('v2b')
    v2d = daily_pl(V2D_CSV).rename('v2d')
    both = pd.concat([v2b, v2d], axis=1).fillna(0)
    print(f"Loaded {len(both)} days ({both.index[0]} -> {both.index[-1]})")

    # Compute v2b alone scaled (linear since it's the same series × N)
    base_v2b = stats(both['v2b'], 'v2b x 1')
    print(f"\nBaseline: v2b x 1 → Final ${base_v2b['final']:+,.0f}  "
          f"DD ${base_v2b['max_dd']:,.0f}  Sharpe {base_v2b['sharpe']:.2f}")

    # Sweep
    rows = []
    for n_v2b in range(0, 6):
        for n_v2d in range(0, 6):
            if n_v2b == 0 and n_v2d == 0:
                continue
            combined = both['v2b'] * n_v2b + both['v2d'] * n_v2d
            s = stats(combined, f"v2b x {n_v2b} + v2d x {n_v2d}")
            s['n_v2b'] = n_v2b
            s['n_v2d'] = n_v2d
            s['total_contracts'] = n_v2b + n_v2d
            s['margin'] = (n_v2b + n_v2d) * MNQ_OVERNIGHT_IM
            # Required capital = margin + 3x max DD buffer
            s['min_capital_3x'] = s['margin'] + 3 * s['max_dd']
            s['return_on_capital_pct'] = (s['annual'] / s['min_capital_3x'] * 100
                                          if s['min_capital_3x'] > 0 else 0)
            rows.append(s)

    sw = pd.DataFrame(rows)
    sw = sw.sort_values('sharpe', ascending=False)
    sw.to_csv(OUT_DIR / 'sizing_sweep.csv', index=False)

    print("\n" + "=" * 110)
    print("SIZING SWEEP — v2b/v2d contract mixes (sorted by Sharpe)")
    print("=" * 110)
    print(f"{'Config':<22} {'Final $':>10} {'Annual':>9} {'MaxDD':>9} "
          f"{'σ daily':>8} {'Sharpe':>7} {'Calmar':>7} {'MinCap':>9} {'ROC %':>6}")
    print("-" * 110)
    for _, r in sw.iterrows():
        print(f"{r['config']:<22} ${r['final']:>+8,.0f} ${r['annual']:>+7,.0f} "
              f"${r['max_dd']:>7,.0f} ${r['sigma']:>6.0f} {r['sharpe']:>+7.2f} "
              f"{r['calmar']:>7.2f} ${r['min_capital_3x']:>7,.0f} "
              f"{r['return_on_capital_pct']:>5.1f}%")

    # Find apples-to-apples: for each combo, what's the v2b-only equivalent at the same DD?
    print("\n" + "=" * 110)
    print("APPLES-TO-APPLES: combo vs equivalent v2b-only sized to same max DD")
    print("=" * 110)
    base_dd = base_v2b['max_dd']
    base_annual = base_v2b['annual']
    print(f"{'Config':<22} {'Combo $/yr':>11} {'Combo DD':>10} "
          f"{'Equiv v2b N':>12} {'Equiv $/yr':>11} {'Combo wins?':>12}")
    print("-" * 110)
    for _, r in sw.iterrows():
        equiv_n_v2b = r['max_dd'] / base_dd
        equiv_annual = base_annual * equiv_n_v2b
        wins = "YES" if r['annual'] > equiv_annual else "no"
        edge_pct = (r['annual'] - equiv_annual) / abs(equiv_annual) * 100 if equiv_annual else 0
        print(f"{r['config']:<22} ${r['annual']:>+9,.0f} ${r['max_dd']:>8,.0f} "
              f"{equiv_n_v2b:>11.2f}x ${equiv_annual:>+9,.0f} "
              f"{wins:>10} ({edge_pct:+.1f}%)")

    # Best risk-adjusted (Sharpe) and best capital-efficiency (Calmar)
    best_sharpe = sw.iloc[sw['sharpe'].idxmax()]
    best_calmar = sw.iloc[sw['calmar'].idxmax()]
    print(f"\nBest by Sharpe: {best_sharpe['config']} → Sharpe={best_sharpe['sharpe']:.2f}")
    print(f"Best by Calmar: {best_calmar['config']} → Calmar={best_calmar['calmar']:.2f}, "
          f"$/yr ${best_calmar['annual']:+,.0f} on ${best_calmar['min_capital_3x']:,.0f} cap")

    # Save formatted summary
    with open(OUT_DIR / 'sizing_sweep.txt', 'w') as f:
        f.write("v2b + v2d SIZING SWEEP — MNQ\n")
        f.write("="*70 + "\n\n")
        f.write(sw.round(2).to_string(index=False))
        f.write(f"\n\nBest by Sharpe: {best_sharpe['config']}")
        f.write(f"\nBest by Calmar: {best_calmar['config']}")


if __name__ == '__main__':
    main()
