#!/usr/bin/env python3
"""
Adaptive lookback parameter sweep for v2b/v2d switching.

For each candidate lookback window N days:
  At the start of each trading day t, look at the rolling sum of
  (v2b - v2d) daily P/L over days [t-N, t-1] only (causally honest, no
  peek-ahead). If positive -> trade v2b today. If negative -> trade v2d.

Then evaluate the resulting equity curve.

Also runs a walk-forward sanity check:
  - Split data 50/50 in time.
  - Find optimal N in the first half.
  - Apply that N to the second half.
  - Compare to the in-sample-optimal N for the second half.

Outputs:
  mnq/v2d/lookback_sweep.csv      full sweep results
  mnq/v2d/lookback_sweep.txt      formatted summary
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def daily_pl(csv_path):
    df = pd.read_csv(csv_path)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df.groupby('Date')['Net_$'].sum()


def equity_stats(s):
    eq = s.cumsum()
    dd = eq - eq.cummax()
    if s.std() == 0:
        sharpe = 0.0
    else:
        sharpe = s.mean() / s.std() * np.sqrt(252)
    return {
        'final':   eq.iloc[-1],
        'max_dd':  dd.min(),
        'sigma':   s.std(),
        'sharpe':  sharpe,
        'n_days':  len(s),
    }


def adaptive_signal(both, window):
    """
    For each day, decide v2b (1) or v2d (-1) based on rolling sum of
    (v2b - v2d) over the PRIOR `window` days only.

    First `window` days have no signal; default to v2b (the long-run
    positive expectation strategy).
    """
    diff = (both['v2b'] - both['v2d']).rolling(window).sum().shift(1)  # shift(1) = causal
    sig = np.where(diff > 0, 'v2b', 'v2d')
    sig[:window] = 'v2b'  # warmup default
    return sig


def apply_signal(both, sig):
    out = both['v2b'].where(sig == 'v2b', both['v2d'])
    return out


def sweep(both, windows):
    rows = []
    for w in windows:
        sig = adaptive_signal(both, w)
        s = apply_signal(both, sig)
        st = equity_stats(s)
        st['window'] = w
        st['v2b_picked_pct'] = (sig == 'v2b').mean() * 100
        st['avg_per_day'] = s.mean()
        st['ann_$'] = s.mean() * 252
        rows.append(st)
    return pd.DataFrame(rows)


def walk_forward(both, windows, n_splits=4):
    """
    K-fold time-ordered walk-forward:
      Split data into n_splits chunks. For each split:
        - Use the chunks BEFORE the split to find the best window.
        - Apply that window to the held-out chunk.
        - Record OOS performance.
    """
    n = len(both)
    chunk = n // n_splits
    results = []
    for i in range(1, n_splits):
        train_end = chunk * i
        train = both.iloc[:train_end]
        test  = both.iloc[train_end:train_end + chunk]
        # In-sample best window on train
        train_perf = []
        for w in windows:
            sig = adaptive_signal(train, w)
            s = apply_signal(train, sig)
            train_perf.append((w, equity_stats(s)['sharpe']))
        best_w = max(train_perf, key=lambda x: x[1])[0]
        # Apply best_w to test
        sig = adaptive_signal(test, best_w)
        s = apply_signal(test, sig)
        test_st = equity_stats(s)
        # Compare to in-sample-best window for test (for reference only)
        test_perf = []
        for w in windows:
            sig_t = adaptive_signal(test, w)
            s_t = apply_signal(test, sig_t)
            test_perf.append((w, equity_stats(s_t)['sharpe']))
        oracle_w, oracle_sh = max(test_perf, key=lambda x: x[1])
        results.append({
            'split': i,
            'train_dates': f"{train.index[0]} -> {train.index[-1]}",
            'test_dates':  f"{test.index[0]} -> {test.index[-1]}",
            'best_w_train': best_w,
            'oos_final': test_st['final'],
            'oos_sharpe': test_st['sharpe'],
            'oos_max_dd': test_st['max_dd'],
            'oracle_w_test': oracle_w,
            'oracle_sharpe_test': oracle_sh,
        })
    return pd.DataFrame(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v2b', default='/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv')
    ap.add_argument('--v2d', default='/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv')
    ap.add_argument('--out', default='/home/tester/hsm/potions/mnq/v2d')
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    v2b = daily_pl(args.v2b).rename('v2b')
    v2d = daily_pl(args.v2d).rename('v2d')
    both = pd.concat([v2b, v2d], axis=1).fillna(0)
    print(f"Loaded {len(both)} trading days "
          f"({both.index[0]} -> {both.index[-1]})")
    print(f"  v2b alone: ${both['v2b'].sum():>+9,.0f}, max DD {((both['v2b'].cumsum())-(both['v2b'].cumsum().cummax())).min():.0f}")
    print(f"  v2d alone: ${both['v2d'].sum():>+9,.0f}, max DD {((both['v2d'].cumsum())-(both['v2d'].cumsum().cummax())).min():.0f}")

    windows = [3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180, 250]
    sw = sweep(both, windows)
    print("\n=== LOOKBACK SWEEP ===")
    print(f"{'Win':>4} {'Final $':>10} {'MaxDD $':>10} {'σ daily':>8} "
          f"{'Sharpe':>7} {'Ann $':>9} {'v2b_pct':>8}")
    for _, r in sw.iterrows():
        print(f"{int(r['window']):>4} ${r['final']:>+9,.0f} ${r['max_dd']:>+9,.0f} "
              f"${r['sigma']:>6.0f} {r['sharpe']:>7.2f} ${r['ann_$']:>+7,.0f} "
              f"{r['v2b_picked_pct']:>6.1f}%")
    sw.to_csv(out_dir / 'lookback_sweep.csv', index=False)

    best = sw.iloc[sw['sharpe'].idxmax()]
    print(f"\nBest by Sharpe: window={int(best['window'])} "
          f"Sharpe={best['sharpe']:.2f} Final=${best['final']:+,.0f} "
          f"MaxDD=${best['max_dd']:+,.0f}")
    best_pl = sw.iloc[sw['final'].idxmax()]
    print(f"Best by Final: window={int(best_pl['window'])} "
          f"Final=${best_pl['final']:+,.0f} Sharpe={best_pl['sharpe']:.2f}")

    # Walk-forward stress test
    print("\n=== WALK-FORWARD STRESS TEST (4-fold) ===")
    wf = walk_forward(both, windows, n_splits=4)
    print(f"{'Split':>5} {'Train':>30} {'Test':>30} "
          f"{'Best W_train':>13} {'OOS Final':>10} {'OOS Sharpe':>11} {'Oracle W':>9}")
    for _, r in wf.iterrows():
        print(f"{int(r['split']):>5} {r['train_dates']:>30} {r['test_dates']:>30} "
              f"{int(r['best_w_train']):>13} ${r['oos_final']:>+8,.0f} "
              f"{r['oos_sharpe']:>+10.2f} {int(r['oracle_w_test']):>9}")

    wf.to_csv(out_dir / 'lookback_walkforward.csv', index=False)

    # Save formatted summary
    with open(out_dir / 'lookback_sweep.txt', 'w') as f:
        f.write("LOOKBACK SWEEP — v2b/v2d adaptive switching (MNQ)\n")
        f.write("="*70 + "\n")
        f.write(sw.round(2).to_string(index=False))
        f.write(f"\n\nBest by Sharpe: window={int(best['window'])} ({best['sharpe']:.2f})")
        f.write(f"\nBest by Final:  window={int(best_pl['window'])} (${best_pl['final']:+,.0f})")
        f.write("\n\nWALK-FORWARD STRESS TEST\n")
        f.write("="*70 + "\n")
        f.write(wf.round(2).to_string(index=False))


if __name__ == '__main__':
    main()
