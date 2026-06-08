#!/usr/bin/env python3
"""
Add **monthly interaction** cross flags to a qualified-legs CSV (e.g. ``v2b_m_legs.csv``).

For each session date, builds **5 m** bars **[00:00, 16:00) NY** (same window as monthly-interaction
charts) and evaluates prior-month **high** / **low** crosses using ``rules.monthly_interaction_cross``.

**Columns added**

- ``mi_cross_high_full_sess`` / ``mi_cross_low_full_sess`` — cross using the **full** 00:00–16:00 window
  (same **intraday** rule as the PNG charts; the chart script **also** requires an end-of-day **daily touch**
  on pm H/L — this annotator does **not** apply that extra gate).
- ``mi_cross_high_thru_cutoff`` / ``mi_cross_low_thru_cutoff`` — cross using only 5 m bars **strictly
  before** ``--cutoff`` NY (**causal** for decisions taken after that clock instant).

Requires MNQ **1 m** data overlapping all dates in the input CSV.

Example::

  cd potions/mnq/case_studies/v2b_m
  python3 annotate_monthly_interaction_flags.py \\
      --legs ./v2b_m_legs.csv \\
      --output ./v2b_m_legs_mi.csv \\
      --cutoff 09:45
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict

import pandas as pd

HERE = Path(__file__).resolve().parent
MNQ_ROOT = HERE.parents[1]
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path.insert(0, str(MNQ_ROOT))
sys.path.insert(0, str(MNQ_ROOT / 'scripts'))
sys.path.insert(0, str(POTIONS_SCRIPTS))

import annotate_mnq_v2b_range_context as ann  # noqa: E402

from rules.monthly_interaction_cross import (  # noqa: E402
    crosses_prior_month_levels,
    crosses_prior_month_levels_through_cutoff,
    resample_5m_midnight_to_1600,
)


def _parse_cutoff(s: str):
    return datetime.strptime(s.strip(), '%H:%M').time()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--legs', type=Path, required=True, help='CSV with Date, pm_high, pm_low (and optional extra cols)')
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument(
        '--cutoff',
        type=_parse_cutoff,
        default='09:45',
        help='NY clock cutoff for causal crosses (5 m bars starting strictly before this time)',
    )
    args = ap.parse_args()

    if not args.legs.is_file():
        print(f'Missing legs CSV: {args.legs}', file=sys.stderr)
        return 1
    if not args.m1.is_file():
        print(f'Missing 1m: {args.m1}', file=sys.stderr)
        return 1

    legs = pd.read_csv(args.legs)
    if not {'Date', 'pm_high', 'pm_low'}.issubset(legs.columns):
        print('Input CSV must include columns Date, pm_high, pm_low', file=sys.stderr)
        return 1

    legs['Date'] = pd.to_datetime(legs['Date']).dt.date
    need_dates = set(legs['Date'].unique())
    if not need_dates:
        print('No dates in legs CSV.', file=sys.stderr)
        return 1

    tmin, tmax = min(need_dates), max(need_dates)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby: Dict[date, pd.DataFrame] = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    full_map: Dict[date, tuple[bool, bool, bool, bool]] = {}

    for d in sorted(need_dates):
        day_raw = gby.get(d)
        if day_raw is None or day_raw.empty:
            full_map[d] = (False, False, False, False)
            continue

        bars5 = resample_5m_midnight_to_1600(day_raw, d)
        row0 = legs.loc[legs['Date'] == d].iloc[0]
        pm_h = float(row0['pm_high'])
        pm_l = float(row0['pm_low'])

        ch_full, cl_full = crosses_prior_month_levels(bars5, pm_h, pm_l)
        ch_pre, cl_pre = crosses_prior_month_levels_through_cutoff(bars5, pm_h, pm_l, args.cutoff)
        full_map[d] = (ch_full, cl_full, ch_pre, cl_pre)

    def row_flags(day):
        return full_map.get(day, (False, False, False, False))

    tup = legs['Date'].map(lambda dd: row_flags(dd))
    legs['mi_cross_high_full_sess'] = tup.map(lambda x: x[0])
    legs['mi_cross_low_full_sess'] = tup.map(lambda x: x[1])
    legs['mi_cross_high_thru_cutoff'] = tup.map(lambda x: x[2])
    legs['mi_cross_low_thru_cutoff'] = tup.map(lambda x: x[3])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    legs.to_csv(args.output, index=False)
    n = len(legs)
    causal_any = legs['mi_cross_high_thru_cutoff'] | legs['mi_cross_low_thru_cutoff']
    full_any = legs['mi_cross_high_full_sess'] | legs['mi_cross_low_full_sess']
    print(
        f'Wrote {args.output} ({n} rows)\n'
        f'  Full-session cross (high or low): {int(full_any.sum())} legs\n'
        f'  Causal thru {args.cutoff.strftime("%H:%M")} NY (high or low): {int(causal_any.sum())} legs'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
