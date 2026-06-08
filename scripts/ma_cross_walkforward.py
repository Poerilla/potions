#!/usr/bin/env python3
"""
MA-cross regime switch — walk-forward + multi-product test.

For each (fast, slow) MA pair from a wide grid, evaluate the
v2b/v2d switching rule (fast > slow → v2b, else v2d) using
PRIOR-DAY MA values for causal honesty.

Then walk-forward:
  - Split the strategy days into N chunks.
  - For each split: find best MA pair on the training chunks (in-sample
    Sharpe-max) and apply that pair to the held-out test chunk.
  - Report OOS performance and compare to v2b alone on the same window.

Supports MNQ (5 yrs) and NQ (16 yrs).
"""
import argparse
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd


PRODUCTS = {
    'MNQ': {
        'daily_dbn': '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst',
        'v2b':   '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv',
        'v2d':   '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv',
        'out':   Path('/home/tester/hsm/potions/mnq/v2d'),
    },
    'NQ': {
        'daily_dbn': '/home/tester/hsm/potions/nq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d (nq).dbn.zst',
        'v2b':   '/home/tester/hsm/potions/nq/nq_orb_results_stops.csv',
        'v2d':   '/home/tester/hsm/potions/nq/v2d/nq_orb_results_v2d.csv',
        'out':   Path('/home/tester/hsm/potions/nq/v2d'),
    },
}

MA_GRID = [
    (10, 25), (10, 30), (10, 50),
    (15, 40), (15, 50),
    (20, 40), (20, 50), (20, 75), (20, 100),
    (25, 50), (25, 75), (25, 100),
    (30, 60), (30, 75), (30, 100),
    (40, 100), (50, 100), (50, 150),
]


def daily_strat(csv):
    df = pd.read_csv(csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df.groupby('Date')['Net_$'].sum()


def daily_close(dbn_path, prefix):
    store = db.DBNStore.from_file(dbn_path)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(prefix)].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def stats(s):
    if len(s) == 0:
        return dict(final=0, annual=0, max_dd=0, sigma=0, sharpe=0, calmar=0)
    eq = s.cumsum()
    dd = eq - eq.cummax()
    sigma = s.std()
    sharpe = s.mean() / sigma * np.sqrt(252) if sigma > 0 else 0
    final = eq.iloc[-1]
    annual = final / (len(s) / 252) if len(s) else 0
    max_dd = abs(dd.min())
    calmar = annual / max_dd if max_dd > 0 else 0
    return dict(final=final, annual=annual, max_dd=max_dd,
                sigma=sigma, sharpe=sharpe, calmar=calmar)


def signal_for(close, fast, slow):
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    return (f > s).shift(1).fillna(True)


def apply(perf, sig):
    s_aligned = sig.reindex(perf.index, method='ffill').fillna(True)
    return perf['v2b'].where(s_aligned, perf['v2d']), s_aligned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--product', choices=list(PRODUCTS.keys()), default='MNQ')
    ap.add_argument('--splits', type=int, default=4,
                    help='Walk-forward splits (default 4)')
    args = ap.parse_args()

    cfg = PRODUCTS[args.product]
    print(f"\n{'='*70}\n  {args.product} MA-CROSS WALK-FORWARD\n{'='*70}")

    v2b = daily_strat(cfg['v2b']).rename('v2b')
    v2d = daily_strat(cfg['v2d']).rename('v2d')
    perf = pd.concat([v2b, v2d], axis=1).fillna(0)
    close = daily_close(cfg['daily_dbn'], args.product)
    print(f"Strategy days: {len(perf)} ({perf.index.min()} -> {perf.index.max()})")
    print(f"v2b alone: ${perf['v2b'].sum():,.0f}, MaxDD ${stats(perf['v2b'])['max_dd']:,.0f}")
    print(f"v2d alone: ${perf['v2d'].sum():,.0f}, MaxDD ${stats(perf['v2d'])['max_dd']:,.0f}")

    # ---- 1) Full-sample sweep ----
    print(f"\n{'-'*70}\n  Full-sample MA cross sweep ({len(MA_GRID)} pairs)\n{'-'*70}")
    print(f"{'fast/slow':>10} {'Final $':>11} {'Annual':>9} {'MaxDD':>9} "
          f"{'Sharpe':>7} {'Calmar':>7} {'v2b%':>6} {'Flips':>6}")
    full_rows = []
    for fast, slow in MA_GRID:
        sig = signal_for(close, fast, slow)
        s, sa = apply(perf, sig)
        st = stats(s)
        st['fast'] = fast; st['slow'] = slow
        st['v2b_pct'] = sa.mean() * 100
        st['flips'] = (sa != sa.shift(1)).sum()
        full_rows.append(st)
        print(f"{fast:>4}/{slow:<4} ${st['final']:>+9,.0f} ${st['annual']:>+7,.0f} "
              f"${st['max_dd']:>7,.0f} {st['sharpe']:>+7.2f} {st['calmar']:>7.2f} "
              f"{st['v2b_pct']:>5.1f}% {int(st['flips']):>6}")
    full_df = pd.DataFrame(full_rows)
    print(f"\nv2b alone reference: ${perf['v2b'].sum():,.0f}, "
          f"Sharpe {stats(perf['v2b'])['sharpe']:.2f}")
    full_df.to_csv(cfg['out'] / f'ma_cross_full_sweep_{args.product.lower()}.csv',
                    index=False)
    n_better = (full_df['final'] > perf['v2b'].sum()).sum()
    print(f"\n  {n_better} of {len(full_df)} MA pairs beat v2b alone in absolute $")
    n_better_sh = (full_df['sharpe'] > stats(perf['v2b'])['sharpe']).sum()
    print(f"  {n_better_sh} of {len(full_df)} MA pairs beat v2b alone in Sharpe")

    # ---- 2) Walk-forward ----
    print(f"\n{'-'*70}\n  Walk-forward ({args.splits}-fold)\n{'-'*70}")
    n = len(perf)
    chunk = n // args.splits
    wf_rows = []
    oos_concat = []
    for i in range(1, args.splits):
        train = perf.iloc[:chunk * i]
        test  = perf.iloc[chunk * i: chunk * (i + 1)]

        # Find best MA pair on train
        train_perf = []
        for fast, slow in MA_GRID:
            sig = signal_for(close, fast, slow)
            s, _ = apply(train, sig)
            train_perf.append(((fast, slow), stats(s)['sharpe']))
        best_pair = max(train_perf, key=lambda x: x[1])[0]

        # Apply to test
        sig = signal_for(close, *best_pair)
        s_test, sa = apply(test, sig)
        st = stats(s_test)
        st['split'] = i
        st['train_end'] = train.index[-1]
        st['test_start'] = test.index[0]
        st['test_end'] = test.index[-1]
        st['best_pair_train'] = f"{best_pair[0]}/{best_pair[1]}"
        st['v2b_alone_test'] = test['v2b'].sum()
        st['oos_v2b_pct'] = sa.mean() * 100
        wf_rows.append(st)
        oos_concat.append(s_test)

        print(f"Split {i}: train→ {st['train_end']}  test {st['test_start']} → {st['test_end']}")
        print(f"   Best pair on train: {st['best_pair_train']}")
        print(f"   OOS test: ${st['final']:>+9,.0f}  vs v2b alone ${st['v2b_alone_test']:>+9,.0f}  "
              f"Δ ${st['final'] - st['v2b_alone_test']:>+7,.0f}  "
              f"Sharpe {st['sharpe']:>+.2f}")

    # Stitched OOS
    oos = pd.concat(oos_concat)
    oos_st = stats(oos)
    v2b_compare = perf.loc[oos.index, 'v2b']
    v2b_st = stats(v2b_compare)
    print(f"\n=== STITCHED OOS ({len(oos)} days) ===")
    print(f"  Adaptive (walk-forward picks): "
          f"${oos_st['final']:+,.0f}  Sharpe {oos_st['sharpe']:+.2f}  "
          f"DD ${oos_st['max_dd']:,.0f}")
    print(f"  v2b alone (same window):       "
          f"${v2b_st['final']:+,.0f}  Sharpe {v2b_st['sharpe']:+.2f}  "
          f"DD ${v2b_st['max_dd']:,.0f}")
    print(f"  Δ (adaptive - v2b):            "
          f"${oos_st['final'] - v2b_st['final']:+,.0f}")

    # Year-by-year on stitched OOS
    print(f"\n=== YEAR-BY-YEAR (stitched OOS) ===")
    yr_oos = oos.copy(); yr_oos.index = pd.to_datetime(yr_oos.index)
    yr_v2b = v2b_compare.copy(); yr_v2b.index = pd.to_datetime(yr_v2b.index)
    yr_df = pd.DataFrame({
        'v2b_alone': yr_v2b.groupby(yr_v2b.index.year).sum(),
        'WF_adaptive': yr_oos.groupby(yr_oos.index.year).sum(),
    }).round(0).astype(int)
    yr_df['delta'] = yr_df['WF_adaptive'] - yr_df['v2b_alone']
    print(yr_df.to_string())

    pd.DataFrame(wf_rows).to_csv(
        cfg['out'] / f'ma_cross_walkforward_{args.product.lower()}.csv', index=False)


if __name__ == '__main__':
    main()
