#!/usr/bin/env python3
"""
Same 50/150 daily MA regime switch as ``v2d/build_adaptive_trades.py``, but v2b arm uses
``mnq_orb_results_stops_60pct.csv`` from this folder. v2d CSV unchanged.

Output: ``adaptive_experiment/mnq_orb_results_adaptive_50_150_60pct.csv``
"""
from pathlib import Path

import databento as db
import pandas as pd

_D = Path(__file__).resolve().parent
DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V2B_CSV = _D / 'mnq_orb_results_stops_60pct.csv'
V2D_CSV = Path('/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv')
OUT_CSV = _D / 'mnq_orb_results_adaptive_50_150_60pct.csv'

FAST = 50
SLOW = 150


def daily_close():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def main():
    print(f'Building adaptive {FAST}/{SLOW} with v2b={V2B_CSV.name} ...')
    close = daily_close()
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    regime_v2b = (ma_fast > ma_slow).shift(1).fillna(True)

    v2b = pd.read_csv(V2B_CSV)
    v2d = pd.read_csv(V2D_CSV)
    for d in (v2b, v2d):
        d['Date'] = pd.to_datetime(d['Date']).dt.date

    rows = []
    all_dates = sorted(set(v2b['Date']) | set(v2d['Date']))
    n_v2b_days = n_v2d_days = 0
    for date in all_dates:
        # If a session exists in v2b/v2d but daily MA index gaps (holiday/symbol edge),
        # still stitch trades (aligns with needing full calendar coverage).
        if date in regime_v2b.index:
            is_v2b = bool(regime_v2b.loc[date])
            ma_f = ma_fast.loc[date] if date in ma_fast.index else None
            ma_s = ma_slow.loc[date] if date in ma_slow.index else None
        else:
            is_v2b = True
            ma_f = ma_s = None
        src = v2b if is_v2b else v2d
        day_trades = src[src['Date'] == date]
        if is_v2b:
            n_v2b_days += 1
        else:
            n_v2d_days += 1
        for _, t in day_trades.iterrows():
            row = t.to_dict()
            row['Regime'] = 'v2b_60pct' if is_v2b else 'v2d'
            row['MA_fast_prev'] = round(ma_f, 2) if ma_f is not None else None
            row['MA_slow_prev'] = round(ma_s, 2) if ma_s is not None else None
            rows.append(row)

    df = pd.DataFrame(rows)
    df['Cumulative_$'] = df['Net_$'].cumsum().round(2)
    df['Cumulative_PL'] = df['Trade_PL'].cumsum().round(6)
    cols_first = ['Date', 'Regime', 'MA_fast_prev', 'MA_slow_prev']
    df = df[cols_first + [c for c in df.columns if c not in cols_first]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print(f"\n  Wrote {len(df):,} adaptive trades -> {OUT_CSV}")
    tot_d = n_v2b_days + n_v2d_days
    pct_b = (100.0 * n_v2b_days / tot_d) if tot_d else 0.0
    pct_d = (100.0 * n_v2d_days / tot_d) if tot_d else 0.0
    print(
        f"  Days in v2b (60%) regime: {n_v2b_days}  ({pct_b:.1f}%)")
    print(f"  Days in v2d regime: {n_v2d_days}  ({pct_d:.1f}%)")
    print(f"  Total Net $/MNQ: ${df['Net_$'].sum():,.2f}")
    wins = (df['Trade_PL'] > 0).sum()
    print(f"  Win rate: {wins/len(df)*100:.1f}%   "
          f"({wins} wins / {len(df)-wins} losses+EOD)")
    eq = df['Net_$'].cumsum()
    print(f"  Max realized DD: ${(eq - eq.cummax()).min():,.2f}")


if __name__ == '__main__':
    main()
