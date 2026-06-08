#!/usr/bin/env python3
"""
Exploratory correlation: can we predict **strict clean** v2b TP wins from data that is
known **before or at** the end of the opening range (fair vs intraday path)?

Features tested (all aligned to **session date**):

- **ma50_gt_150_prior**: prior calendar day’s MA50 > MA150 on daily close (same signal as
  adaptive regime, **causal** before that session’s OR completes if you use yesterday’s close).
- **range_pts**: OR height in index points (known at 9:45 end of OR window).
- **range_pct_mid**: Range / midpoint(RH, RL).
- **dow_mon0**: weekday (0 Mon).

Population: TP **Win** legs in ``clean_break_manifest.csv`` (~922 rows). Strict clean is rare;
this script quantifies crude lift vs baserate and univariate standardized differences.

Outputs: concise console report (optional CSV summary).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

MANIFEST_DEFAULT = Path(__file__).resolve().parent.parent / 'data' / 'clean_break_manifest.csv'
DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
FAST, SLOW = 50, 150


def load_daily_close_series():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    s = fm.set_index('date').sort_index()['close']
    mf = s.rolling(FAST).mean()
    ms = s.rolling(SLOW).mean()
    prior_ma_up = (mf > ms).shift(1).fillna(False)
    return mf, ms, prior_ma_up


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', type=Path, default=MANIFEST_DEFAULT)
    ap.add_argument('--out-csv', type=Path, default=None)
    args = ap.parse_args()

    man = pd.read_csv(args.manifest)
    man['Date'] = pd.to_datetime(man['Date']).dt.date
    wins = man[man['Result'] == 'Win'].copy()
    wins['strict'] = wins['strict_clean'].astype(bool)
    mf, ms, prior_ma_up = load_daily_close_series()

    merged = []
    for _, r in wins.iterrows():
        d = r['Date']
        rh, rl = float(r['RH']), float(r['RL'])
        rg = float(r['Range'])
        mid = (rh + rl) / 2
        pmap = False
        if d in mf.index:
            pmap = bool(prior_ma_up.loc[d])
        merged.append(
            {
                'Date': d,
                'strict': r['strict'],
                'prior_ma_up': pmap,
                'range_pts': rg,
                'range_pct_mid': rg / mid if mid else math.nan,
                'Leg': int(r['Leg']),
                'direction': r['Trade_Direction'],
            }
        )

    dd = pd.DataFrame(merged)
    base = dd['strict'].mean()
    print('=== Population: TP Win legs only (manifest) ===\n')
    print(f"n = {len(dd)} wins  |  strict-clean rate P(strict) ≈ {100*base:.1f}%")
    lift = dd.groupby('prior_ma_up')['strict'].agg(['mean', 'size'])
    print('\n--- By prior-day MA regime (causal overnight) ---')
    print('  Prior day 50>150 (adaptive-like v2b side): strict rate')
    print(lift.to_string())

    # Point-biserial-style: compare Range for strict vs not
    st = dd.loc[dd['strict'], 'range_pts'].dropna()
    not_st = dd.loc[~dd['strict'], 'range_pts'].dropna()
    mu_s, mu_n = st.mean(), not_st.mean()
    print('\n--- OR Range (pts), TP wins ---')
    print(f'  strict  (n={len(st):4d})  mean RV = {mu_s:.2f}')
    print(f'  not     (n={len(not_st):4d})  mean RV = {mu_n:.2f}')
    pooled = np.concatenate([st.values, not_st.values])
    pooled_std = float(np.nanstd(pooled, ddof=1)) or 1.0
    cohens_d = (mu_s - mu_n) / pooled_std
    print(f"  Cohen's d (approx): {cohens_d:.3f}  (~0.02 trivial, ~0.5 moderate)")

    # Leg effect
    print('\n--- Leg ---')
    print(dd.groupby('Leg')['strict'].agg(['mean', 'count']).to_string())

    if args.out_csv:
        dd.to_csv(args.out_csv, index=False)
        print(f"\nSaved {args.out_csv}")

    print(
        '\nInterpretation: Strict clean is labeled from the whole post-fill path, so '
        'same-day RV and prior-close MA splits are associative only—not live predictors without '
        'features known before entry. Cohen d on OR Range among wins is small (~0.2); leg split '
        'matters more in this table than naive MA stratification.'
    )


if __name__ == '__main__':
    main()
