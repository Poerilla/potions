#!/usr/bin/env python3
"""
Directional Bias Filter: only take trades on the shorter timeframe when
they align with the higher-timeframe breakout direction.

Variants tested:
  1. 15-min aligned with Yearly  (ignore shorts when yearly is Long, etc.)
  2. 15-min aligned with Monthly
  3. Monthly aligned with Yearly
  4. 15-min aligned with both Monthly AND Yearly

The bias is determined by the LAST breakout direction on the higher timeframe.
If the higher TF had a Long breakout (even if it lost), the bias is Long until
a Short breakout occurs. The bias persists across trade resolution — it's the
most recent directional signal, not the current position.

Works for any instrument that has the required CSVs.
"""
import os
import sys
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_orb(instrument, timeframe):
    """Load an ORB results CSV. Returns DataFrame with 'date' column."""
    if timeframe == '15min':
        fname = f'{instrument}_orb_results.csv'
    else:
        fname = f'{instrument}_{timeframe}_orb.csv'

    path = os.path.join(BASE, instrument, fname)
    df = pd.read_csv(path)

    if 'Date' in df.columns:
        df['date'] = pd.to_datetime(df['Date'])
    elif 'Period' in df.columns:
        df['Period'] = df['Period'].astype(str)
        if timeframe == 'monthly':
            df['date'] = pd.to_datetime(df['Period'] + '-01')
        elif timeframe == 'yearly':
            df['date'] = pd.to_datetime(df['Period'] + '-01-01')
        elif timeframe == 'quarterly':
            df['date'] = df['Period'].apply(
                lambda p: pd.to_datetime(p.split('-')[0] + '-01-01'))
    return df


def extract_bias_series(df, timeframe):
    """
    Build a bias series from higher-TF trades.
    Returns a dict: {period_key: 'Long' | 'Short' | None}

    The bias is the LAST breakout direction observed in that period.
    For yearly: bias applies Apr-Dec of that year (after Q1 range).
    For monthly: bias applies from day 4 onward of that month.
    """
    trades = df[df['Trade_Direction'].isin(['Long', 'Short'])].copy()

    if timeframe == 'yearly':
        # Group by year. Bias = last trade direction per year.
        # The bias for year Y applies from Apr of year Y onward.
        bias = {}
        for _, row in trades.iterrows():
            if 'Period' in row.index:
                yr = int(row['Period'])
            else:
                yr = row['date'].year
            bias[yr] = row['Trade_Direction']
        return bias, 'yearly'

    elif timeframe == 'monthly':
        # Bias = last trade direction per month.
        bias = {}
        for _, row in trades.iterrows():
            if 'Period' in row.index:
                ym = row['Period']  # e.g. '2021-03'
            else:
                ym = row['date'].strftime('%Y-%m')
            bias[ym] = row['Trade_Direction']
        return bias, 'monthly'

    return {}, None


def get_bias_for_date(d, bias_dict, bias_type):
    """Look up the bias for a given date."""
    if bias_type == 'yearly':
        yr = d.year
        return bias_dict.get(yr, None)
    elif bias_type == 'monthly':
        ym = d.strftime('%Y-%m')
        return bias_dict.get(ym, None)
    return None


def filter_by_bias(trades_df, bias_dict, bias_type):
    """
    Filter trades: keep only those where Trade_Direction matches the bias.
    No-Op rows pass through. Trades against bias become No-Op.
    """
    result = trades_df.copy()
    for idx, row in result.iterrows():
        if row['Trade_Direction'] in ('Long', 'Short'):
            bias = get_bias_for_date(row['date'], bias_dict, bias_type)
            if bias is not None and row['Trade_Direction'] != bias:
                result.at[idx, 'Trade_Direction'] = 'No-Op (filtered)'
                result.at[idx, 'Trade_PL'] = 0
                result.at[idx, 'Drawdown_Pct'] = 0
                result.at[idx, 'Result'] = 'Filtered'
    return result


def compute_stats(df, label):
    """Compute strategy stats from a filtered DataFrame."""
    def tag(r):
        if r['Result'] in ('Win', 'Loss'):
            return r['Result']
        if r['Result'] in ('EOD-Close', 'Period-Close'):
            return 'Win' if r['Trade_PL'] > 0 else 'Loss'
        return 'Skip'

    df = df.copy()
    df['Tag'] = df.apply(tag, axis=1)
    trades = df[df['Tag'].isin(['Win', 'Loss'])]
    filtered = len(df[df['Result'] == 'Filtered'])

    if len(trades) == 0:
        return {'Label': label, 'Trades': 0, 'Filtered': filtered,
                'Wins': 0, 'Losses': 0, 'WinPct': 0, 'CumPL': 0,
                'MaxDD': 0, 'AvgDD': 0, 'AvgWinDD': 0, 'MaxLStreak': 0}

    wins = (trades['Tag'] == 'Win').sum()
    losses = (trades['Tag'] == 'Loss').sum()
    cum_pl = trades['Trade_PL'].sum()

    eq = trades['Trade_PL'].cumsum().values
    peak = np.maximum.accumulate(eq)
    max_dd = (peak - eq).max()

    # Loss streak
    tags = trades['Tag'].tolist()
    ms = cs = 0
    for t in tags:
        if t == 'Loss':
            cs += 1
            ms = max(ms, cs)
        else:
            cs = 0

    return {
        'Label': label,
        'Trades': len(trades),
        'Filtered': filtered,
        'Wins': wins,
        'Losses': losses,
        'WinPct': round(wins / (wins + losses) * 100, 1),
        'CumPL': round(cum_pl, 2),
        'MaxDD': round(max_dd, 2),
        'AvgDD': round(trades['Drawdown_Pct'].mean(), 1),
        'AvgWinDD': round(trades[trades['Tag'] == 'Win']['Drawdown_Pct'].mean(), 1),
        'MaxLStreak': ms,
    }


def run_instrument(instrument, mult):
    """Run all bias variants for one instrument."""
    print(f"\n{'='*80}")
    print(f"  {instrument.upper()} (${mult}/pt)")
    print(f"{'='*80}")

    # Load all available timeframes
    available = {}
    for tf in ['15min', 'monthly', 'quarterly', 'yearly']:
        try:
            df = load_orb(instrument, tf)
            available[tf] = df
            print(f"  Loaded {tf}: {len(df)} rows")
        except FileNotFoundError:
            pass

    if '15min' not in available:
        print(f"  No 15-min data for {instrument}, skipping.")
        return []

    results = []

    # Baseline: unfiltered 15-min
    baseline = compute_stats(available['15min'], f'{instrument.upper()} 15-Min (baseline)')
    results.append(baseline)

    # Variant 1: 15-min aligned with Yearly
    if 'yearly' in available:
        bias_y, bt_y = extract_bias_series(available['yearly'], 'yearly')
        filtered = filter_by_bias(available['15min'], bias_y, bt_y)
        s = compute_stats(filtered, f'{instrument.upper()} 15-Min + Yearly bias')
        results.append(s)

    # Variant 2: 15-min aligned with Monthly
    if 'monthly' in available:
        bias_m, bt_m = extract_bias_series(available['monthly'], 'monthly')
        filtered = filter_by_bias(available['15min'], bias_m, bt_m)
        s = compute_stats(filtered, f'{instrument.upper()} 15-Min + Monthly bias')
        results.append(s)

    # Variant 3: Monthly aligned with Yearly
    if 'monthly' in available and 'yearly' in available:
        bias_y, bt_y = extract_bias_series(available['yearly'], 'yearly')
        filtered = filter_by_bias(available['monthly'], bias_y, bt_y)
        s = compute_stats(filtered, f'{instrument.upper()} Monthly + Yearly bias')
        results.append(s)

    # Variant 4: 15-min aligned with BOTH Monthly AND Yearly
    if 'monthly' in available and 'yearly' in available:
        bias_y, bt_y = extract_bias_series(available['yearly'], 'yearly')
        bias_m, bt_m = extract_bias_series(available['monthly'], 'monthly')
        # Both must agree AND match the trade direction
        filtered = available['15min'].copy()
        filtered['date'] = pd.to_datetime(filtered['Date'])
        for idx, row in filtered.iterrows():
            if row['Trade_Direction'] in ('Long', 'Short'):
                yb = get_bias_for_date(row['date'], bias_y, bt_y)
                mb = get_bias_for_date(row['date'], bias_m, bt_m)
                if yb is not None and mb is not None:
                    if row['Trade_Direction'] != yb or row['Trade_Direction'] != mb:
                        filtered.at[idx, 'Trade_Direction'] = 'No-Op (filtered)'
                        filtered.at[idx, 'Trade_PL'] = 0
                        filtered.at[idx, 'Drawdown_Pct'] = 0
                        filtered.at[idx, 'Result'] = 'Filtered'
                elif yb is not None and row['Trade_Direction'] != yb:
                    filtered.at[idx, 'Trade_Direction'] = 'No-Op (filtered)'
                    filtered.at[idx, 'Trade_PL'] = 0
                    filtered.at[idx, 'Drawdown_Pct'] = 0
                    filtered.at[idx, 'Result'] = 'Filtered'
                elif mb is not None and row['Trade_Direction'] != mb:
                    filtered.at[idx, 'Trade_Direction'] = 'No-Op (filtered)'
                    filtered.at[idx, 'Trade_PL'] = 0
                    filtered.at[idx, 'Drawdown_Pct'] = 0
                    filtered.at[idx, 'Result'] = 'Filtered'
        s = compute_stats(filtered, f'{instrument.upper()} 15-Min + Monthly + Yearly bias')
        results.append(s)

    # Baseline monthly
    if 'monthly' in available:
        mb = compute_stats(available['monthly'], f'{instrument.upper()} Monthly (baseline)')
        results.append(mb)

    return results


def main():
    instruments = [
        ('mnq', 2),
        ('nq', 20),
    ]

    all_results = []
    for inst, mult in instruments:
        all_results.extend(run_instrument(inst, mult))

    df = pd.DataFrame(all_results)

    # Print comparison
    print(f"\n\n{'='*120}")
    print(f"  DIRECTIONAL BIAS FILTER — FULL COMPARISON")
    print(f"{'='*120}")
    print()
    print(f"{'Strategy':<45s} {'Trades':>7s} {'Filtered':>9s} {'Win%':>7s} {'Cum PL':>12s} {'MaxDD':>10s} {'AvgDD':>7s} {'WinDD':>7s} {'MaxLStr':>8s}")
    print(f"{'-'*110}")

    prev_inst = None
    for _, r in df.iterrows():
        inst = r['Label'].split()[0]
        if prev_inst and inst != prev_inst:
            print()
        prev_inst = inst
        print(f"{r['Label']:<45s} {r['Trades']:>7d} {r['Filtered']:>9d} {r['WinPct']:>6.1f}% {r['CumPL']:>+12,.2f} {r['MaxDD']:>10,.2f} {r['AvgDD']:>6.1f}% {r['AvgWinDD']:>6.1f}% {r['MaxLStreak']:>8d}")

    # Save
    outpath = os.path.join(BASE, 'bias_aligned_results.csv')
    df.to_csv(outpath, index=False)
    print(f"\nSaved {outpath}")

    # Generate chart
    plot_comparison(df)


def plot_comparison(df):
    """Bar chart comparing win rates and P/L across variants."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    fig.patch.set_facecolor('#fafafa')

    for ax in axes:
        ax.set_facecolor('#fafafa')

    colors = ['#1a1a2e', '#e63946', '#457b9d', '#2a9d8f', '#f4a261', '#6c757d']

    # Group by instrument
    for inst_prefix in ['MNQ', 'NQ']:
        sub = df[df['Label'].str.startswith(inst_prefix)]
        if sub.empty:
            continue

        labels = [r['Label'].replace(f'{inst_prefix} ', '') for _, r in sub.iterrows()]
        win_pcts = sub['WinPct'].values
        cum_pls = sub['CumPL'].values

        x = np.arange(len(labels))
        width = 0.35
        offset = 0 if inst_prefix == 'MNQ' else width

        axes[0].barh(x + offset, win_pcts, width, label=inst_prefix,
                     color=colors[0] if inst_prefix == 'MNQ' else colors[1], alpha=0.8)
        axes[1].barh(x + offset, cum_pls, width, label=inst_prefix,
                     color=colors[0] if inst_prefix == 'MNQ' else colors[1], alpha=0.8)

    axes[0].set_xlabel('Win Rate (%)', fontsize=12)
    axes[0].set_title('Win Rate by Variant', fontsize=14, fontweight='bold')
    axes[0].set_yticks(np.arange(len(labels)))
    axes[0].set_yticklabels(labels, fontsize=9)
    axes[0].legend()
    axes[0].grid(True, alpha=0.3, axis='x')

    axes[1].set_xlabel('Cumulative P/L (pts)', fontsize=12)
    axes[1].set_title('Cumulative P/L by Variant', fontsize=14, fontweight='bold')
    axes[1].set_yticks(np.arange(len(labels)))
    axes[1].set_yticklabels(labels, fontsize=9)
    axes[1].xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f'{v:,.0f}'))
    axes[1].legend()
    axes[1].grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    outpath = os.path.join(BASE, 'bias_aligned_chart.png')
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved {outpath}")


if __name__ == '__main__':
    main()
