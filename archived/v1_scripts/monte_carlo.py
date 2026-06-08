#!/usr/bin/env python3
"""
Monte Carlo simulation of the ORB portfolio.

Takes the actual trade P/L sequence from each strategy, shuffles them randomly
N_SIMS times, and rebuilds the equity curve each time. This tests whether the
results are order-dependent or structurally robust.

Produces:
  - monte_carlo_equity.png   (equity fan chart)
  - monte_carlo_drawdown.png (max DD distribution)
  - monte_carlo_final_pl.png (terminal P/L distribution)
  - monte_carlo_stats.csv    (percentile table)
"""
import os
import sys
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

N_SIMS = 10_000
np.random.seed(42)

PARENT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PARENT, '..')

STRATEGIES = [
    ('mnq_orb_results.csv',  2,   3, 'MNQ 15-Min'),
    ('mym_orb_results.csv',  0.5, 2, 'MYM 15-Min'),
    ('mnq_monthly_orb.csv',  2,   1, 'MNQ Monthly'),
]


def load_trades():
    """Load and merge all strategy trades into a single dollar-P/L series."""
    all_trades = []
    for csv_name, mult, contracts, label in STRATEGIES:
        path = os.path.join(DATA_DIR, csv_name)
        df = pd.read_csv(path)
        trades = df[df['Result'].isin(['Win', 'Loss', 'EOD-Close', 'Period-Close'])].copy()
        trades['dollar_pl'] = trades['Trade_PL'] * mult * contracts
        all_trades.extend(trades['dollar_pl'].tolist())
        print(f"  {label}: {len(trades)} trades, cum ${sum(trades['dollar_pl'].tolist()):,.0f}")
    return np.array(all_trades)


def run_monte_carlo(trades, n_sims):
    """Shuffle trade order N times, build equity curves."""
    n_trades = len(trades)
    # Pre-allocate: each row = one sim's equity curve
    curves = np.zeros((n_sims, n_trades))
    max_dds = np.zeros(n_sims)
    finals = np.zeros(n_sims)

    for i in range(n_sims):
        shuffled = np.random.permutation(trades)
        eq = np.cumsum(shuffled)
        curves[i] = eq
        finals[i] = eq[-1]

        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        max_dds[i] = dd.max()

    return curves, max_dds, finals


def plot_equity_fan(curves, actual_equity, outpath):
    """Fan chart of simulated equity curves with percentile bands."""
    n_trades = curves.shape[1]
    x = np.arange(n_trades)

    p5 = np.percentile(curves, 5, axis=0)
    p25 = np.percentile(curves, 25, axis=0)
    p50 = np.percentile(curves, 50, axis=0)
    p75 = np.percentile(curves, 75, axis=0)
    p95 = np.percentile(curves, 95, axis=0)
    p_min = curves.min(axis=0)
    p_max = curves.max(axis=0)

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor('#fafafa')
    ax.set_facecolor('#fafafa')

    ax.fill_between(x, p_min, p_max, alpha=0.06, color='#457b9d', label='Min–Max range')
    ax.fill_between(x, p5, p95, alpha=0.12, color='#457b9d', label='5th–95th pctile')
    ax.fill_between(x, p25, p75, alpha=0.25, color='#457b9d', label='25th–75th pctile')
    ax.plot(x, p50, color='#457b9d', linewidth=1.5, label='Median (50th)')
    ax.plot(x, actual_equity, color='#e63946', linewidth=2, label='Actual sequence')

    ax.set_title(f'Monte Carlo Equity Curves — {N_SIMS:,} Simulations', fontsize=16, fontweight='bold', pad=15)
    ax.set_xlabel('Trade #', fontsize=12)
    ax.set_ylabel('Cumulative P/L ($)', fontsize=12)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f'${v:,.0f}'))
    ax.legend(loc='upper left', fontsize=11, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linewidth=0.5)

    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def plot_distribution(data, title, xlabel, outpath, actual_val=None, pct_fmt=False):
    """Histogram of a Monte Carlo metric."""
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#fafafa')
    ax.set_facecolor('#fafafa')

    ax.hist(data, bins=80, color='#457b9d', alpha=0.7, edgecolor='white', linewidth=0.5)

    if actual_val is not None:
        ax.axvline(actual_val, color='#e63946', linewidth=2, linestyle='--', label=f'Actual: ${actual_val:,.0f}')
        ax.legend(fontsize=12, framealpha=0.9)

    p5, p50, p95 = np.percentile(data, [5, 50, 95])
    for pct, val, ls in [(5, p5, ':'), (50, p50, '-'), (95, p95, ':')]:
        ax.axvline(val, color='#2a9d8f', linewidth=1.5, linestyle=ls, alpha=0.7)
        ax.annotate(f'{pct}th: ${val:,.0f}', xy=(val, ax.get_ylim()[1] * 0.92),
                    fontsize=9, color='#2a9d8f', ha='center',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title(title, fontsize=16, fontweight='bold', pad=15)
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f'${v:,.0f}'))
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def main():
    print(f"Loading trades ...")
    trades = load_trades()
    print(f"  Total: {len(trades)} trades, cumulative ${trades.sum():,.0f}")

    actual_equity = np.cumsum(trades)
    actual_dd = (np.maximum.accumulate(actual_equity) - actual_equity).max()
    actual_final = actual_equity[-1]

    print(f"\nRunning {N_SIMS:,} Monte Carlo simulations ...")
    curves, max_dds, finals = run_monte_carlo(trades, N_SIMS)
    print(f"  Done.")

    print(f"\nGenerating charts ...")
    plot_equity_fan(curves, actual_equity,
                    os.path.join(PARENT, 'monte_carlo_equity.png'))
    plot_distribution(finals, 'Terminal P/L Distribution', 'Final Cumulative P/L ($)',
                      os.path.join(PARENT, 'monte_carlo_final_pl.png'),
                      actual_val=actual_final)
    plot_distribution(max_dds, 'Maximum Drawdown Distribution', 'Max Drawdown ($)',
                      os.path.join(PARENT, 'monte_carlo_drawdown.png'),
                      actual_val=actual_dd)

    # Stats table
    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    stats = []
    for p in percentiles:
        stats.append({
            'Percentile': f'{p}th',
            'Final_PL': np.percentile(finals, p),
            'Max_DD': np.percentile(max_dds, p),
        })
    stats_df = pd.DataFrame(stats)
    stats_df['Min_Capital_3x'] = stats_df['Max_DD'] * 3
    stats_df['Min_Capital_8x'] = stats_df['Max_DD'] * 8
    stats_df['Annual_ROI_3x'] = (stats_df['Final_PL'] / 7) / stats_df['Min_Capital_3x'] * 100
    stats_df['Annual_ROI_8x'] = (stats_df['Final_PL'] / 7) / stats_df['Min_Capital_8x'] * 100

    stats_path = os.path.join(PARENT, 'monte_carlo_stats.csv')
    stats_df.to_csv(stats_path, index=False)
    print(f"\n  Saved {stats_path}")

    # Print summary
    print(f"\n{'='*70}")
    print(f"  MONTE CARLO RESULTS ({N_SIMS:,} simulations, {len(trades)} trades)")
    print(f"{'='*70}")
    print(f"  Actual final P/L:     ${actual_final:>12,.0f}")
    print(f"  Actual max DD:        ${actual_dd:>12,.0f}")
    print(f"")
    print(f"  {'Pctile':>8s}  {'Final P/L':>14s}  {'Max DD':>12s}  {'Capital(3x)':>12s}  {'ROI/yr(3x)':>10s}")
    print(f"  {'-'*62}")
    for _, r in stats_df.iterrows():
        print(f"  {r['Percentile']:>8s}  ${r['Final_PL']:>12,.0f}  ${r['Max_DD']:>10,.0f}  ${r['Min_Capital_3x']:>10,.0f}  {r['Annual_ROI_3x']:>9.1f}%")

    # Probability of profit
    prob_profit = (finals > 0).sum() / N_SIMS * 100
    prob_100k = (finals > 100_000).sum() / N_SIMS * 100
    prob_200k = (finals > 200_000).sum() / N_SIMS * 100
    print(f"\n  P(profit > $0):      {prob_profit:.1f}%")
    print(f"  P(profit > $100k):   {prob_100k:.1f}%")
    print(f"  P(profit > $200k):   {prob_200k:.1f}%")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
