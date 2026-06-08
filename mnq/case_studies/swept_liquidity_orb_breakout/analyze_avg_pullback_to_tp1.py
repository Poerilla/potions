#!/usr/bin/env python3
"""
From entry to first intrabar touch of TP1: mean per-1m-bar adverse (pullback)
vs entry. Does not use MAE (worst); uses average of bar-wise adverse on that path.

Requires the same DBN as sweep_orb_backtest.py and mnq_swept_orb_breakout.csv.

Usage:
  python analyze_avg_pullback_to_tp1.py [--csv path]
"""
from __future__ import annotations

import argparse
from datetime import time as dtime
from pathlib import Path
from typing import Dict, Optional

import databento as db
import pandas as pd
import pytz

EPS = 1e-9
NY = pytz.timezone('America/New_York')
DBN = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'

T_RTH0 = dtime(9, 30)
T_RTH1 = dtime(16, 0)


def load_by_date() -> Dict:
    print(f'Loading DBN ...')
    store = db.DBNStore.from_file(DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')]
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= T_RTH0) & (df['t'] < T_RTH1)]
    df = df[df['date'] >= pd.Timestamp('2021-03-04').date()]
    df = df.set_index('ts_event').sort_index()
    return {d: g for d, g in df.groupby(df.index.date)}


def avg_pullback_until_tp1(
    m1: pd.Timestamp,
    entry_px: float,
    tp1: float,
    direction: str,
    day_bars: pd.DataFrame,
) -> Optional[float]:
    """
    Mean adverse per 1m bar from entry bar through the bar where TP1 is first touched intrabar.
    Long: adverse on bar = max(0, entry - low). Short: max(0, high - entry).
    """
    fwd = day_bars[day_bars.index >= m1]
    if fwd.empty:
        return None

    d_long = direction == 'Long'
    pulls: list[float] = []

    for _, bar in fwd.iterrows():
        hi = float(bar['high'])
        lo = float(bar['low'])
        if d_long:
            pulls.append(max(0.0, entry_px - lo))
            touched = hi >= tp1 - EPS
        else:
            pulls.append(max(0.0, hi - entry_px))
            touched = lo <= tp1 + EPS
        if touched:
            return float(sum(pulls) / len(pulls))
    return None  # never touched TP1 during session


def main() -> int:
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    ap.add_argument('--csv', type=str, default=str(root / 'mnq_swept_orb_breakout.csv'))
    args = ap.parse_args()

    csv = pd.read_csv(args.csv)
    filled = csv[csv['Entry_Price'].notna()].copy()
    filled['Date'] = pd.to_datetime(filled['Date']).dt.date

    by_d = load_by_date()

    per_trade: list[float] = []
    no_data = 0
    no_tp1 = 0

    for _, row in filled.iterrows():
        d = row['Date']
        if d not in by_d:
            no_data += 1
            continue
        day = by_d[d]
        if str(row['Symbol']) and 'symbol' in day.columns:
            day = day[day['symbol'] == row['Symbol']]
        if day.empty:
            no_data += 1
            continue

        et = pd.to_datetime(row['Entry_Time'])
        if et.tzinfo is None:
            et = et.tz_localize(NY)
        else:
            et = et.tz_convert(NY)

        out = avg_pullback_until_tp1(
            et,
            float(row['Entry_Price']),
            float(row['TP1_Level']),
            str(row['Trade_Direction']),
            day,
        )
        if out is None:
            no_tp1 += 1
        else:
            per_trade.append(out)

    n = len(per_trade)
    s = pd.Series(per_trade)

    print(
        'Per trade: average of adverse per minute from entry bar through first bar that touches TP1 '
        '(long: max(0, entry−low); short: max(0, high−entry)). Uses market path, not sim fill order.'
    )
    print(f'Sessions where price ever touched TP1 after entry: {n} / {len(filled)}')
    print(f'Mean (over those trades) of that per-minute average pullback: {s.mean():.4f} index pts')
    print(f'Median:                                                       {s.median():.4f}')
    print(f'Sessions ending before TP1 touched: {no_tp1}')
    print(f'Missing DBN slice:                     {no_data}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
