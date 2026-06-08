#!/usr/bin/env python3
"""
For rows with Opp_sweep_London_H / Opp_sweep_London_L, report when price
**first touches** the causal **02:00–09:30** box high (Short) or low (Long)
computed from 1m — same definition as v2e (not ctx 02:00–11:00 from the CSV).

Buckets (NY time, first touch of Ldn H for Short / Ldn L for Long):
  - pre_rth:   before 09:30 (e.g. 09:25 overnight / Globex)
  - in_orb:    09:30 <= t < 09:45  (ORB window; level can be "swept" here)
  - post_orb:  t >= 09:45

v2e sim only counts **first RTH fill** 09:30–16:00 at the **limit** — so a
touch at 09:25 does **not** produce a fill in the current model; if RTH never
re-touches the limit, you get **no_fill** (see London sweep charts).

Run:  python3 analyze_london_sweep_timings.py
      python3 analyze_london_sweep_timings.py --csv /path/to/annotated.csv
"""
import argparse
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
V2E_SCR = Path(__file__).resolve().parent
POTIONS = V2E_ROOT.parent.parent
sys.path.insert(0, str(V2E_SCR))
from sim_london_limit_scaleout import london_0200_0930_hilo  # noqa: E402
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

T_RTH = time(9, 30)
T_ORB_END = time(9, 45)
M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
ANNOTATED = POTIONS / 'mnq' / 'mnq_orb_results_stops_annotated.csv'


def first_touch_short(day: pd.DataFrame, ldn_h: float):
    """First bar where high >= ldn_h."""
    if pd.isna(ldn_h):
        return None
    for ts, b in day.iterrows():
        if float(b['high']) >= float(ldn_h) - 1e-9:
            return ts
    return None


def first_touch_long(day: pd.DataFrame, ldn_l: float):
    if pd.isna(ldn_l):
        return None
    for ts, b in day.iterrows():
        if float(b['low']) <= float(ldn_l) + 1e-9:
            return ts
    return None


def bucket(ts: pd.Timestamp) -> str:
    t = ts.tz_convert('America/New_York').time() if ts.tzinfo else ts.time()
    if t < T_RTH:
        return 'pre_rth'
    if t < T_ORB_END:
        return 'in_orb'
    return 'post_orb'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    args = ap.parse_args()

    df = pd.read_csv(args.annotated)
    sel = (df['Opp_sweep_London_H'] == 1) | (df['Opp_sweep_London_L'] == 1)
    sub = df[sel].copy()
    sub['Date'] = pd.to_datetime(sub['Date']).dt.date
    if sub.empty:
        print('No London sweep rows', file=sys.stderr)
        return 1

    need = set(sub['Date'].unique())
    tmin, tmax = min(need), max(need)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    rows = []
    for _, r in sub.iterrows():
        d = r['Date']
        day = gby.get(d)
        if day is None or day.empty:
            ldn_h, ldn_l = np.nan, np.nan
        else:
            ldn_h, ldn_l = london_0200_0930_hilo(day)
        dr = r['Trade_Direction']
        ts0 = None
        if dr == 'Short':
            ts0 = first_touch_short(day, ldn_h) if day is not None and not day.empty else None
        else:
            ts0 = first_touch_long(day, ldn_l) if day is not None and not day.empty else None
        b = bucket(ts0) if ts0 is not None else 'no_touch'
        rows.append(
            {
                'Date': d,
                'dir': dr,
                'first_touch_ny': ts0,
                'bucket': b,
                'ldn_h': ldn_h,
                'ldn_l': ldn_l,
            }
        )

    out = pd.DataFrame(rows)
    print('London sweep rows:', len(out))
    print('\nFirst touch of *adverse* London level (Short→LdnH, Long→LdnL) by bucket:')
    print(out['bucket'].value_counts().sort_index().to_string())
    print(
        "\nMeaning: **pre_rth** = touch before 09:30 (v2e RTH sim does not see it as fill time); "
        "if price never re-touches the limit in RTH → chart shows no_fill."
    )
    pre = out[out['bucket'] == 'pre_rth']
    if not pre.empty:
        print(f"\nSample pre-RTH (first {min(8, len(pre))} rows):")
        print(
            pre[['Date', 'dir', 'first_touch_ny', 'ldn_h', 'ldn_l']]
            .head(8)
            .to_string(index=False)
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
