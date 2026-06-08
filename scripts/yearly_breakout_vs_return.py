#!/usr/bin/env python3
"""
Analyze: Does the Yearly ORB (Jan-Mar range) breakout direction predict full-year return?

- Bullish breakout (Long)  -> does the year end positive?
- Bearish breakout (Short) -> does the year end negative?

Uses daily data: close at end of March vs close at end of December.
"""

import os
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_year_return(daily_path: str) -> pd.DataFrame:
    """Compute year return: (close_dec - close_mar) / close_mar for each year."""
    df = pd.read_csv(daily_path)
    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month

    # Last trading day of March and December per year
    mar = df[df['month'] == 3].groupby('year').last().reset_index()
    dec = df[df['month'] == 12].groupby('year').last().reset_index()

    mar = mar[['year', 'close']].rename(columns={'close': 'close_mar'})
    dec = dec[['year', 'close']].rename(columns={'close': 'close_dec'})

    merged = mar.merge(dec, on='year')
    merged['year_return'] = (merged['close_dec'] - merged['close_mar']) / merged['close_mar']
    merged['year_positive'] = merged['close_dec'] > merged['close_mar']
    return merged[['year', 'close_mar', 'close_dec', 'year_return', 'year_positive']]


def get_breakout_direction(orb_path: str) -> pd.DataFrame:
    """First trade direction per year = breakout direction (Long = bullish, Short = bearish)."""
    df = pd.read_csv(orb_path)
    first = df.groupby('Period').first().reset_index()
    first = first[['Period', 'Trade_Direction']].rename(columns={'Period': 'year'})
    return first


def main():
    instruments = ['mnq', 'nq', 'es']
    results = []

    for inst in instruments:
        daily_path = os.path.join(BASE, inst, f'{inst}_daily.csv')
        orb_path = os.path.join(BASE, inst, f'{inst}_yearly_orb.csv')
        if not os.path.exists(daily_path) or not os.path.exists(orb_path):
            continue

        returns = get_year_return(daily_path)
        breakout = get_breakout_direction(orb_path)
        merged = returns.merge(breakout, on='year', how='inner')

        # Exclude No-Op (no breakout in Jan-Mar)
        merged = merged[merged['Trade_Direction'].isin(['Long', 'Short'])]

        for _, row in merged.iterrows():
            results.append({
                'instrument': inst.upper(),
                'year': row['year'],
                'breakout': row['Trade_Direction'],
                'year_positive': row['year_positive'],
                'year_return_pct': row['year_return'] * 100,
                'close_mar': row['close_mar'],
                'close_dec': row['close_dec'],
            })

    df = pd.DataFrame(results)
    if df.empty:
        print("No data.")
        return

    # Summary by instrument
    print("=" * 70)
    print("YEARLY ORB BREAKOUT vs FULL-YEAR RETURN")
    print("=" * 70)
    print("\nQuestion: Bullish breakout -> year positive? Bearish -> year negative?\n")

    for inst in df['instrument'].unique():
        sub = df[df['instrument'] == inst].copy()
        sub = sub.sort_values('year')

        print(f"\n--- {inst} ---")
        print(sub[['year', 'breakout', 'year_positive', 'year_return_pct']].to_string(index=False))

        # Contingency
        bull = sub[sub['breakout'] == 'Long']
        bear = sub[sub['breakout'] == 'Short']

        bull_correct = (bull['year_positive'] == True).sum()
        bull_total = len(bull)
        bear_correct = (bear['year_positive'] == False).sum()
        bear_total = len(bear)

        print(f"\n  Bullish breakout (Long):  {bull_correct}/{bull_total} years ended positive ({100*bull_correct/max(1,bull_total):.0f}%)")
        print(f"  Bearish breakout (Short): {bear_correct}/{bear_total} years ended negative ({100*bear_correct/max(1,bear_total):.0f}%)")

        # Overall predictive power
        pred_correct = bull_correct + bear_correct
        pred_total = bull_total + bear_total
        print(f"  Overall: {pred_correct}/{pred_total} correct ({100*pred_correct/max(1,pred_total):.0f}%)")

    # Combined summary
    print("\n" + "=" * 70)
    print("COMBINED (all instruments, each year counted once per instrument)")
    print("=" * 70)

    bull = df[df['breakout'] == 'Long']
    bear = df[df['breakout'] == 'Short']
    bull_correct = (bull['year_positive'] == True).sum()
    bear_correct = (bear['year_positive'] == False).sum()
    print(f"\nBullish breakout -> year positive: {bull_correct}/{len(bull)} ({100*bull_correct/max(1,len(bull)):.1f}%)")
    print(f"Bearish breakout -> year negative: {bear_correct}/{len(bear)} ({100*bear_correct/max(1,len(bear)):.1f}%)")
    print(f"Overall predictive accuracy: {(bull_correct+bear_correct)}/{len(df)} ({100*(bull_correct+bear_correct)/len(df):.1f}%)")

    # Save
    out_path = os.path.join(BASE, 'volatility', 'yearly_breakout_vs_return.csv')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
