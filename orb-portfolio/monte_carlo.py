#!/usr/bin/env python3
"""
Monte Carlo simulation of the v2 ORB portfolio.

Draws from three v2 pre-placed-stop backtests:
  1. MNQ NY session 15-min ORB  (from ../mnq/mnq_orb_results_stops.csv)
  2. MNQ London session 15-min ORB (from ../combined_orb/london_orb_results_stops.csv)
  3. MYM NY session 15-min ORB  (from ../mym/mym_orb_results_stops.csv)

Default allocation: 1 contract of each. Pass --size to scale uniformly
(e.g., --size 3 -> 3 MNQ NY + 3 MNQ London + 3 MYM NY). Or pass
--mnq-ny, --mnq-london, --mym-ny to allocate individually.

Pass --adaptive to use the adaptive 50/150 (MNQ daily regime) combined
trade log: MNQ NY + MNQ London + MYM NY only (--mym-london ignored).
Requires ../orb-portfolio/adaptive_portfolio_combined_50_150.csv from
combined_orb/scripts/build_adaptive_50_150_portfolio.py.

Produces (in orb-portfolio/):
  monte_carlo_equity.png      fan chart
  monte_carlo_drawdown.png    DD distribution
  monte_carlo_final_pl.png    terminal P/L distribution
  monte_carlo_stats.csv       percentile table
"""
import argparse
import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


PARENT = os.path.dirname(os.path.abspath(__file__))
BASE   = os.path.dirname(PARENT)

DEFAULTS = {
    'mnq_ny':      os.path.join(BASE, 'mnq', 'mnq_orb_results_stops.csv'),
    'mnq_london':  os.path.join(BASE, 'combined_orb', 'london_orb_results_stops.csv'),
    'mym_ny':      os.path.join(BASE, 'combined_orb', 'mym_ny_orb_results_stops.csv'),
    'mym_london':  os.path.join(BASE, 'combined_orb', 'mym_london_orb_results_stops.csv'),
}
ADAPTIVE_COMBINED = os.path.join(PARENT, 'adaptive_portfolio_combined_50_150.csv')
LEG_TO_KEY = {'MNQ_NY': 'mnq_ny', 'MNQ_London': 'mnq_london', 'MYM_NY': 'mym_ny'}
MULTIPLIERS = {'mnq_ny': 2.0, 'mnq_london': 2.0, 'mym_ny': 0.5, 'mym_london': 0.5}
FEE_RT      = 1.50

N_SIMS = 10_000
np.random.seed(42)


def load_strategy(csv_path, mult, contracts):
    """Load trades, return per-trade $ P/L scaled to `contracts` (net of fees)."""
    df = pd.read_csv(csv_path)
    # Accept either v2 columns ('Net_$') or compute from Trade_PL
    if 'Net_$' in df.columns:
        per_contract_net = df['Net_$'].to_numpy()
    else:
        per_contract_net = (df['Trade_PL'] * mult - FEE_RT).to_numpy()
    # Scale: gross scales linearly, fee scales linearly per contract
    # Net_$ was (pl*mult - fee). Scaled = pl*mult*N - fee*N = (pl*mult - fee)*N
    scaled = per_contract_net * contracts
    return scaled, df


def load_adaptive_combined(path, contracts):
    """
    Load chronological adaptive portfolio CSV (Leg, Net_$).
    Scale each row by contract count for that leg (keys: mnq_ny, mnq_london, mym_ny).
    """
    df = pd.read_csv(path)
    if 'Leg' not in df.columns or 'Net_$' not in df.columns:
        raise ValueError(f'{path} must contain Leg and Net_$ columns')
    out = []
    for _, row in df.iterrows():
        key = LEG_TO_KEY.get(row['Leg'])
        if key is None:
            continue
        n = int(contracts.get(key, 0))
        if n <= 0:
            continue
        out.append(float(row['Net_$']) * n)
    if not out:
        raise ValueError('No trades after adaptive leg filter / zero contracts')
    return np.array(out, dtype=float), df


def run_monte_carlo(dollar_pl, n_sims):
    n = len(dollar_pl)
    curves = np.zeros((n_sims, n))
    max_dds = np.zeros(n_sims)
    finals = np.zeros(n_sims)
    for i in range(n_sims):
        shuffled = np.random.permutation(dollar_pl)
        eq = np.cumsum(shuffled)
        curves[i] = eq
        finals[i] = eq[-1]
        peak = np.maximum.accumulate(eq)
        max_dds[i] = (peak - eq).max()
    return curves, max_dds, finals


def plot_equity_fan(curves, actual_equity, outpath, title_suffix='', title_prefix='v2 ORB Portfolio', n_sims=None):
    if n_sims is None:
        n_sims = N_SIMS
    n = curves.shape[1]
    x = np.arange(n)
    p5 = np.percentile(curves, 5, axis=0)
    p25 = np.percentile(curves, 25, axis=0)
    p50 = np.percentile(curves, 50, axis=0)
    p75 = np.percentile(curves, 75, axis=0)
    p95 = np.percentile(curves, 95, axis=0)

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor('#fafafa')
    ax.set_facecolor('#fafafa')
    ax.fill_between(x, curves.min(0), curves.max(0), alpha=0.06, color='#457b9d', label='Min-Max')
    ax.fill_between(x, p5, p95, alpha=0.12, color='#457b9d', label='5-95 pct')
    ax.fill_between(x, p25, p75, alpha=0.25, color='#457b9d', label='25-75 pct')
    ax.plot(x, p50, color='#457b9d', lw=1.5, label='Median')
    ax.plot(x, actual_equity, color='#e63946', lw=2, label='Actual sequence')
    ax.set_title(f'{title_prefix} — Monte Carlo Equity ({n_sims:,} sims){title_suffix}',
                 fontsize=16, fontweight='bold', pad=15)
    ax.set_xlabel('Trade #')
    ax.set_ylabel('Cumulative Net P/L ($)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
    ax.legend(loc='upper left', framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color='gray', lw=0.5)
    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def plot_distribution(data, title, xlabel, outpath, actual_val=None):
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#fafafa')
    ax.set_facecolor('#fafafa')
    ax.hist(data, bins=80, color='#457b9d', alpha=0.7, edgecolor='white', linewidth=0.5)
    if actual_val is not None:
        ax.axvline(actual_val, color='#e63946', lw=2, linestyle='--',
                   label=f'Actual: ${actual_val:,.0f}')
        ax.legend(fontsize=12, framealpha=0.9)
    p5, p50, p95 = np.percentile(data, [5, 50, 95])
    for pct, val, ls in [(5, p5, ':'), (50, p50, '-'), (95, p95, ':')]:
        ax.axvline(val, color='#2a9d8f', lw=1.5, ls=ls, alpha=0.7)
        ax.annotate(f'{pct}th: ${val:,.0f}', xy=(val, ax.get_ylim()[1] * 0.92),
                    fontsize=9, color='#2a9d8f', ha='center',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    ax.set_title(title, fontsize=16, fontweight='bold', pad=15)
    ax.set_xlabel(xlabel); ax.set_ylabel('Frequency')
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mnq-ny',     type=int, default=1)
    ap.add_argument('--mnq-london', type=int, default=1)
    ap.add_argument('--mym-ny',     type=int, default=1)
    ap.add_argument('--mym-london', type=int, default=1)
    ap.add_argument('--size',       type=int, default=None,
                    help='Uniform scaling: override all four (e.g., --size 3 -> 3/3/3/3)')
    ap.add_argument('--sims',       type=int, default=N_SIMS)
    ap.add_argument('--adaptive',   action='store_true',
                    help='Use adaptive 50/150 combined CSV (MNQ NY + MNQ London + MYM NY)')
    args = ap.parse_args()

    if args.size is not None:
        contracts = {k: args.size for k in DEFAULTS}
    else:
        contracts = {
            'mnq_ny':     args.mnq_ny,
            'mnq_london': args.mnq_london,
            'mym_ny':     args.mym_ny,
            'mym_london': args.mym_london,
        }

    if args.adaptive:
        contracts['mym_london'] = 0

    title_prefix = 'Adaptive 50/150 ORB Portfolio' if args.adaptive else 'v2 ORB Portfolio'

    if args.adaptive:
        print('Loading adaptive 50/150 combined sequence ...')
        dollar_pl, _adf = load_adaptive_combined(ADAPTIVE_COMBINED, contracts)
        for key in ('mnq_ny', 'mnq_london', 'mym_ny'):
            n = contracts[key]
            print(f"  {key:<12} x{n} (from combined CSV row scaling)")
        print(f"  Total rows: {len(dollar_pl):,}, cumulative ${dollar_pl.sum():>+12,.0f}")
    else:
        print("Loading v2 strategies ...")
        all_pnl = []
        for key, path in DEFAULTS.items():
            n = contracts[key]
            if n <= 0:
                print(f"  {key}: skipped (0 contracts)")
                continue
            scaled, df = load_strategy(path, MULTIPLIERS[key], n)
            all_pnl.append(scaled)
            print(f"  {key:<12} x{n}: {len(scaled):>5} trades, total ${scaled.sum():>+12,.0f}")

        dollar_pl = np.concatenate(all_pnl)
    print(f"\nPortfolio: {len(dollar_pl):,} total trades (rows), cumulative ${dollar_pl.sum():+,.0f}")

    actual_eq = np.cumsum(dollar_pl)
    actual_dd = (np.maximum.accumulate(actual_eq) - actual_eq).max()
    actual_final = actual_eq[-1]

    print(f"\nRunning {args.sims:,} simulations ...")
    curves, max_dds, finals = run_monte_carlo(dollar_pl, args.sims)

    alloc_str = " + ".join(f"{k} x{v}" for k, v in contracts.items() if v > 0)
    plot_equity_fan(curves, actual_eq,
                    os.path.join(PARENT, 'monte_carlo_equity.png'),
                    title_suffix=f" — {alloc_str}",
                    title_prefix=title_prefix,
                    n_sims=args.sims)
    dist_label = 'Adaptive' if args.adaptive else 'v2'
    plot_distribution(finals, f'{dist_label} Terminal P/L Distribution',
                      'Final Cumulative Net P/L ($)',
                      os.path.join(PARENT, 'monte_carlo_final_pl.png'),
                      actual_val=actual_final)
    plot_distribution(max_dds, f'{dist_label} Maximum Drawdown Distribution',
                      'Max Drawdown ($)',
                      os.path.join(PARENT, 'monte_carlo_drawdown.png'),
                      actual_val=actual_dd)

    # Stats table
    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    if args.adaptive:
        adf = pd.read_csv(ADAPTIVE_COMBINED)
        d0, d1 = pd.to_datetime(adf['Date']).min(), pd.to_datetime(adf['Date']).max()
        years = max((d1 - d0).days / 365.25, 0.25)
    else:
        years = 5.15  # approximate overlap window of the four v2 strategies
    rows = []
    for p in percentiles:
        fp = np.percentile(finals, p)
        dd = np.percentile(max_dds, p)
        rows.append({
            'Percentile': f'{p}th',
            'Final_PL':   round(fp, 2),
            'Max_DD':     round(dd, 2),
            'Capital_3x': round(dd * 3, 2),
            'Capital_8x': round(dd * 8, 2),
            'Annual_ROI_3x_pct': round((fp / years) / (dd * 3) * 100, 1) if dd > 0 else None,
            'Annual_ROI_8x_pct': round((fp / years) / (dd * 8) * 100, 1) if dd > 0 else None,
        })
    stats_df = pd.DataFrame(rows)
    stats_path = os.path.join(PARENT, 'monte_carlo_stats.csv')
    stats_df.to_csv(stats_path, index=False)
    print(f"\nSaved {stats_path}")

    # Summary
    print(f"\n{'='*78}")
    print(f"  {title_prefix.upper()} MONTE CARLO ({args.sims:,} sims, {len(dollar_pl):,} trades)")
    print(f"{'='*78}")
    print(f"  Allocation:   {', '.join(f'{k} x{v}' for k, v in contracts.items())}")
    print(f"  Actual final: ${actual_final:>+14,.0f}")
    print(f"  Actual max DD:${actual_dd:>+14,.0f}")
    print(f"\n  {'Pctile':>8}  {'Final P/L':>12}  {'Max DD':>12}  {'Cap 3x':>12}  {'ROI 3x':>8}")
    print(f"  {'-'*62}")
    for r in rows:
        print(f"  {r['Percentile']:>8}  ${r['Final_PL']:>+12,.0f}  ${r['Max_DD']:>+12,.0f}  ${r['Capital_3x']:>+12,.0f}  {r['Annual_ROI_3x_pct']:>7.1f}%")

    prob_profit = (finals > 0).mean() * 100
    print(f"\n  P(profit > $0):      {prob_profit:.1f}%")
    print(f"  P(profit > $50k):    {(finals > 50_000).mean()*100:.1f}%")
    print(f"  P(profit > $100k):   {(finals > 100_000).mean()*100:.1f}%")
    print(f"  P(profit > $200k):   {(finals > 200_000).mean()*100:.1f}%")
    print(f"{'='*78}")


if __name__ == '__main__':
    main()
