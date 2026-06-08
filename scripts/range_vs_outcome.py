#!/usr/bin/env python3
"""
Analyze the relationship between opening range size and trade outcome.

Questions:
  - Do larger ranges correlate with higher win rates?
  - Does range size affect drawdown severity?
  - Are there optimal range-size bands?
  - Is range size a useful pre-trade filter?

Analyzes MNQ and NQ 15-min ORB data (largest datasets).
Outputs stats CSV, charts, and a summary to the volatility/ folder.
"""
import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'volatility')


def tag(r):
    if r['Result'] in ('Win', 'Loss'):
        return r['Result']
    if r['Result'] in ('EOD-Close', 'Period-Close'):
        return 'Win' if r['Trade_PL'] > 0 else 'Loss'
    return 'Skip'


def load_and_prepare(instrument):
    path = os.path.join(BASE, instrument, f'{instrument}_orb_results.csv')
    df = pd.read_csv(path)
    df = df[df['Result'].isin(['Win', 'Loss', 'EOD-Close'])].copy()
    df['Tag'] = df.apply(tag, axis=1)
    df['date'] = pd.to_datetime(df['Date'])
    df['year'] = df['date'].dt.year
    return df


def range_quintile_analysis(df, label):
    """Split trades into quintiles by range size and compute stats per band."""
    df = df.copy()
    df['range_quintile'] = pd.qcut(df['Range'], 5, labels=False, duplicates='drop')
    
    bands = []
    for q in sorted(df['range_quintile'].unique()):
        sub = df[df['range_quintile'] == q]
        rmin, rmax = sub['Range'].min(), sub['Range'].max()
        wins = (sub['Tag'] == 'Win').sum()
        losses = (sub['Tag'] == 'Loss').sum()
        total = wins + losses
        wr = wins / total * 100 if total else 0
        avg_pl = sub['Trade_PL'].mean()
        avg_dd = sub['Drawdown_Pct'].mean()
        avg_win_dd = sub[sub['Tag'] == 'Win']['Drawdown_Pct'].mean() if wins else 0
        cum_pl = sub['Trade_PL'].sum()
        
        bands.append({
            'Quintile': q + 1,
            'Range_Min': rmin,
            'Range_Max': rmax,
            'Avg_Range': sub['Range'].mean(),
            'Trades': total,
            'Wins': wins,
            'Losses': losses,
            'WinPct': round(wr, 1),
            'Avg_PL': round(avg_pl, 2),
            'Cum_PL': round(cum_pl, 2),
            'Avg_DD': round(avg_dd, 1),
            'Avg_Win_DD': round(avg_win_dd, 1),
        })
    
    return pd.DataFrame(bands)


def range_decile_analysis(df):
    """Finer 10-bin analysis."""
    df = df.copy()
    df['range_decile'] = pd.qcut(df['Range'], 10, labels=False, duplicates='drop')
    
    bands = []
    for q in sorted(df['range_decile'].unique()):
        sub = df[df['range_decile'] == q]
        wins = (sub['Tag'] == 'Win').sum()
        losses = (sub['Tag'] == 'Loss').sum()
        total = wins + losses
        wr = wins / total * 100 if total else 0
        bands.append({
            'Decile': q + 1,
            'Avg_Range': round(sub['Range'].mean(), 1),
            'Range_Band': f"{sub['Range'].min():.0f}–{sub['Range'].max():.0f}",
            'Trades': total,
            'WinPct': round(wr, 1),
            'Avg_PL': round(sub['Trade_PL'].mean(), 2),
            'Avg_DD': round(sub['Drawdown_Pct'].mean(), 1),
        })
    return pd.DataFrame(bands)


def correlation_analysis(df):
    """Compute correlation between range size and various outcomes."""
    wins = df[df['Tag'] == 'Win']
    losses = df[df['Tag'] == 'Loss']
    
    corrs = {
        'Range vs Trade_PL': df['Range'].corr(df['Trade_PL']),
        'Range vs Drawdown_Pct': df['Range'].corr(df['Drawdown_Pct']),
        'Range vs Win (binary)': df['Range'].corr((df['Tag'] == 'Win').astype(int)),
        'Range vs Abs(Trade_PL)': df['Range'].corr(df['Trade_PL'].abs()),
    }
    if len(wins) > 0:
        corrs['Range vs Win_DD (wins only)'] = wins['Range'].corr(wins['Drawdown_Pct'])
    return corrs


def plot_analysis(df, quintiles, deciles, label, corrs):
    """Generate a multi-panel analysis chart."""
    fig = plt.figure(figsize=(18, 14))
    fig.patch.set_facecolor('#fafafa')
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    colors_q = ['#1a1a2e', '#457b9d', '#2a9d8f', '#e9c46a', '#e63946']

    # 1. Win rate by quintile
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor('#fafafa')
    bars = ax1.bar(quintiles['Quintile'], quintiles['WinPct'], color=colors_q, alpha=0.85)
    ax1.axhline(y=df.apply(tag, axis=1).eq('Win').mean() * 100 if 'Tag' not in df.columns else (df['Tag'] == 'Win').mean() * 100,
                color='gray', linestyle='--', linewidth=1, label='Overall avg')
    ax1.set_xlabel('Range Quintile (1=smallest, 5=largest)')
    ax1.set_ylabel('Win Rate (%)')
    ax1.set_title('Win Rate by Range Size Quintile', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')
    for bar, val in zip(bars, quintiles['WinPct']):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f'{val:.1f}%', ha='center', fontsize=10, fontweight='bold')

    # 2. Avg P/L by quintile
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor('#fafafa')
    colors_pl = ['#2a9d8f' if v > 0 else '#e63946' for v in quintiles['Avg_PL']]
    ax2.bar(quintiles['Quintile'], quintiles['Avg_PL'], color=colors_pl, alpha=0.85)
    ax2.axhline(y=0, color='gray', linewidth=0.5)
    ax2.set_xlabel('Range Quintile')
    ax2.set_ylabel('Avg P/L per Trade (pts)')
    ax2.set_title('Avg Trade P/L by Range Size', fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')

    # 3. Avg Drawdown by quintile
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor('#fafafa')
    ax3.bar(quintiles['Quintile'], quintiles['Avg_DD'], color='#457b9d', alpha=0.7, label='All trades')
    ax3.bar(quintiles['Quintile'], quintiles['Avg_Win_DD'], color='#2a9d8f', alpha=0.7, label='Wins only')
    ax3.set_xlabel('Range Quintile')
    ax3.set_ylabel('Avg Drawdown (%)')
    ax3.set_title('Drawdown by Range Size', fontweight='bold')
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis='y')

    # 4. Win rate by decile (finer resolution)
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor('#fafafa')
    ax4.plot(deciles['Avg_Range'], deciles['WinPct'], 'o-', color='#1a1a2e', linewidth=2, markersize=6)
    ax4.axhline(y=(df['Tag'] == 'Win').mean() * 100, color='gray', linestyle='--', linewidth=1)
    ax4.set_xlabel('Avg Range Size (pts)')
    ax4.set_ylabel('Win Rate (%)')
    ax4.set_title('Win Rate vs Range (decile resolution)', fontweight='bold')
    ax4.grid(True, alpha=0.3)

    # 5. Scatter: Range vs Trade P/L
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.set_facecolor('#fafafa')
    wins_mask = df['Tag'] == 'Win'
    ax5.scatter(df.loc[wins_mask, 'Range'], df.loc[wins_mask, 'Trade_PL'],
                alpha=0.15, s=8, color='#2a9d8f', label='Win')
    ax5.scatter(df.loc[~wins_mask, 'Range'], df.loc[~wins_mask, 'Trade_PL'],
                alpha=0.15, s=8, color='#e63946', label='Loss')
    ax5.axhline(y=0, color='gray', linewidth=0.5)
    ax5.set_xlabel('Range (pts)')
    ax5.set_ylabel('Trade P/L (pts)')
    ax5.set_title(f'Range vs P/L (r={corrs.get("Range vs Trade_PL", 0):.3f})', fontweight='bold')
    ax5.legend(markerscale=3)
    ax5.grid(True, alpha=0.3)

    # 6. Distribution of ranges for wins vs losses
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.set_facecolor('#fafafa')
    win_ranges = df[df['Tag'] == 'Win']['Range']
    loss_ranges = df[df['Tag'] == 'Loss']['Range']
    bins = np.linspace(df['Range'].min(), df['Range'].quantile(0.95), 40)
    ax6.hist(win_ranges, bins=bins, alpha=0.6, color='#2a9d8f', label=f'Wins (avg={win_ranges.mean():.0f})', density=True)
    ax6.hist(loss_ranges, bins=bins, alpha=0.6, color='#e63946', label=f'Losses (avg={loss_ranges.mean():.0f})', density=True)
    ax6.set_xlabel('Range (pts)')
    ax6.set_ylabel('Density')
    ax6.set_title('Range Distribution: Wins vs Losses', fontweight='bold')
    ax6.legend()
    ax6.grid(True, alpha=0.3, axis='y')

    fig.suptitle(f'{label} — Opening Range Size vs Trade Outcome', fontsize=16, fontweight='bold', y=1.01)
    
    outpath = os.path.join(OUT, f'{label.lower().replace(" ", "_")}_range_analysis.png')
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def main():
    all_stats = []

    for instrument, label, mult in [('mnq', 'MNQ', 2), ('nq', 'NQ', 20)]:
        print(f"\n{'='*60}")
        print(f"  {label} — Range vs Outcome Analysis")
        print(f"{'='*60}")

        df = load_and_prepare(instrument)
        print(f"  {len(df)} trades loaded")

        # Correlations
        corrs = correlation_analysis(df)
        print(f"\n  Correlations:")
        for k, v in corrs.items():
            print(f"    {k}: {v:.4f}")

        # Quintile analysis
        quintiles = range_quintile_analysis(df, label)
        print(f"\n  Quintile Analysis:")
        print(f"  {'Q':>3s} {'Range':>12s} {'Trades':>7s} {'Win%':>7s} {'AvgPL':>10s} {'CumPL':>12s} {'AvgDD':>7s}")
        print(f"  {'-'*62}")
        for _, r in quintiles.iterrows():
            print(f"  {int(r['Quintile']):>3d} {r['Range_Min']:.0f}–{r['Range_Max']:.0f}{' ':>4s} {int(r['Trades']):>7d} {r['WinPct']:>6.1f}% {r['Avg_PL']:>+10.2f} {r['Cum_PL']:>+12,.2f} {r['Avg_DD']:>6.1f}%")

        # Decile analysis
        deciles = range_decile_analysis(df)

        # Additional: win rate for very small vs very large ranges
        p10 = df['Range'].quantile(0.10)
        p90 = df['Range'].quantile(0.90)
        small = df[df['Range'] <= p10]
        large = df[df['Range'] >= p90]
        sw = (small['Tag'] == 'Win').sum()
        lw = (large['Tag'] == 'Win').sum()
        print(f"\n  Extremes:")
        print(f"    Bottom 10% (range <= {p10:.0f}): {sw}/{len(small)} = {sw/len(small)*100:.1f}% win rate")
        print(f"    Top 10%    (range >= {p90:.0f}): {lw}/{len(large)} = {lw/len(large)*100:.1f}% win rate")

        # Avg range for wins vs losses
        w_avg = df[df['Tag'] == 'Win']['Range'].mean()
        l_avg = df[df['Tag'] == 'Loss']['Range'].mean()
        print(f"\n  Avg range on Wins:   {w_avg:.1f} pts")
        print(f"  Avg range on Losses: {l_avg:.1f} pts")

        # Chart
        plot_analysis(df, quintiles, deciles, label, corrs)

        # Save quintile stats
        quintiles['Instrument'] = label
        all_stats.append(quintiles)

        deciles['Instrument'] = label
        dec_path = os.path.join(OUT, f'{instrument}_decile_stats.csv')
        deciles.to_csv(dec_path, index=False)

    # Combined stats
    combined = pd.concat(all_stats, ignore_index=True)
    combined.to_csv(os.path.join(OUT, 'range_quintile_stats.csv'), index=False)
    print(f"\n  Saved range_quintile_stats.csv")


if __name__ == '__main__':
    main()
