#!/usr/bin/env python3
"""
MA-cross regime switch backtest.

Rule: when 20-day MA > 50-day MA -> trade v2b.
      when 20-day MA <= 50-day MA -> trade v2d.

Uses prior-day MA values for causally-honest signal (no peek-ahead).
Also sweeps a few related MA pairs (20/100, 50/100) for context.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import databento as db


DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V2B_CSV = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
V2D_CSV = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv'
OUT = Path('/home/tester/hsm/potions/mnq/v2d')


def daily_strat(csv):
    df = pd.read_csv(csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df.groupby('Date')['Net_$'].sum()


def daily_close():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


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


def ma_cross_signal(close, fast, slow):
    """1 if fast_MA > slow_MA (yesterday), else 0. Causally honest."""
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    sig = (f > s).shift(1)   # use yesterday's relationship
    return sig.fillna(True)  # default to v2b during MA warmup


def main():
    v2b = daily_strat(V2B_CSV).rename('v2b')
    v2d = daily_strat(V2D_CSV).rename('v2d')
    close = daily_close()
    print(f"Daily MNQ: {len(close)} bars  ({close.index.min()} -> {close.index.max()})")
    print(f"Strategy:  {len(v2b)} days  ({v2b.index.min()} -> {v2b.index.max()})")

    # Compute MA signals from full daily history (including 2019-2020 warmup)
    sig_2050  = ma_cross_signal(close, 20, 50)
    sig_20100 = ma_cross_signal(close, 20, 100)
    sig_50100 = ma_cross_signal(close, 50, 100)

    # Align to strategy index
    perf = pd.concat([v2b, v2d], axis=1).fillna(0)

    def apply_signal(sig, label):
        s_aligned = sig.reindex(perf.index, method='ffill').fillna(True)
        s = perf['v2b'].where(s_aligned, perf['v2d'])
        st = stats(s, label)
        st['v2b_pct'] = round(s_aligned.mean() * 100, 1)
        # Count regime flips
        flips = (s_aligned != s_aligned.shift(1)).sum()
        st['flips'] = flips
        return s, st

    s_2050,  r_2050  = apply_signal(sig_2050,  'MA cross 20/50')
    s_20100, r_20100 = apply_signal(sig_20100, 'MA cross 20/100')
    s_50100, r_50100 = apply_signal(sig_50100, 'MA cross 50/100')

    rows = [
        stats(perf['v2b'],            'BASELINE: v2b alone'),
        stats(perf['v2d'],            'BASELINE: v2d alone'),
        stats(perf['v2b'] + perf['v2d'], 'BASELINE: 1:1 parallel'),
        r_2050, r_20100, r_50100,
    ]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / 'ma_cross_sweep.csv', index=False)

    print("\n" + "=" * 100)
    print(f"{'Config':<28} {'Final $':>10} {'Annual':>9} {'MaxDD':>9} "
          f"{'σ':>5} {'Sharpe':>7} {'Calmar':>7} {'v2b%':>7} {'Flips':>6}")
    print("-" * 100)
    for _, r in df.iterrows():
        pct = f"{r['v2b_pct']:.1f}%" if 'v2b_pct' in r and not pd.isna(r['v2b_pct']) else '-'
        flips = f"{int(r['flips'])}" if 'flips' in r and not pd.isna(r['flips']) else '-'
        print(f"{r['config']:<28} ${r['final']:>+8,.0f} ${r['annual']:>+7,.0f} "
              f"${r['max_dd']:>7,.0f} ${r['sigma']:>3.0f} {r['sharpe']:>+7.2f} "
              f"{r['calmar']:>7.2f} {pct:>7} {flips:>6}")

    # Year-by-year for the candidates
    print("\n=== YEAR-BY-YEAR ===")
    series_for_year = {
        'v2b alone':      perf['v2b'],
        '1:1 parallel':   perf['v2b'] + perf['v2d'],
        'MA 20/50':       s_2050,
        'MA 20/100':      s_20100,
        'MA 50/100':      s_50100,
    }
    yr = {}
    for k, s in series_for_year.items():
        s = s.copy()
        s.index = pd.to_datetime(s.index)
        yr[k] = s.groupby(s.index.year).sum()
    yr_df = pd.DataFrame(yr).round(0).astype(int)
    print(yr_df.to_string())

    # Print regime distribution for 20/50
    print("\n=== 20/50 MA regime distribution per year ===")
    sig_aligned = sig_2050.reindex(perf.index, method='ffill').fillna(True)
    sig_aligned.index = pd.to_datetime(sig_aligned.index)
    yr_pct = sig_aligned.groupby(sig_aligned.index.year).agg(['mean','sum','size'])
    yr_pct['v2b%'] = (yr_pct['mean']*100).round(1)
    yr_pct['v2d_days'] = yr_pct['size'] - yr_pct['sum']
    print(yr_pct[['size','sum','v2d_days','v2b%']].rename(
        columns={'size':'days','sum':'v2b_days'}).to_string())

    with open(OUT / 'ma_cross_sweep.txt', 'w') as f:
        f.write(df.round(2).to_string(index=False))
        f.write('\n\nYEAR-BY-YEAR\n')
        f.write(yr_df.to_string())
        f.write('\n\n20/50 regime distribution per year\n')
        f.write(yr_pct[['size','sum','v2d_days','v2b%']].to_string())


if __name__ == '__main__':
    main()
