#!/usr/bin/env python3
"""Apply ``rules.monthly_opening_range_bias`` to canonical **v2b** leg CSV (ORB stops)."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

MNQ_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_V2B_CSV = MNQ_ROOT / 'mnq_orb_results_stops.csv'
DEFAULT_DAILY_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'

sys.path.insert(0, str(MNQ_ROOT))
sys.path.insert(0, str(MNQ_ROOT / 'scripts'))
from plot_daily_prior_month_levels import load_mnq_front_daily  # noqa: E402

from rules.monthly_opening_range_bias import monthly_orb_bias_for_session_date  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv', type=Path, default=DEFAULT_V2B_CSV)
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    args = ap.parse_args()

    if not args.csv.is_file():
        print(f'Missing v2b CSV: {args.csv}', file=sys.stderr)
        return 1
    if not args.daily_dbn.is_file():
        print(f'Missing daily DBN: {args.daily_dbn}', file=sys.stderr)
        return 1

    df = pd.read_csv(args.csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)

    uniq_days = sorted(df['Date'].unique())
    bias_by_date = {d: monthly_orb_bias_for_session_date(d, daily) for d in uniq_days}

    bc = Counter(b.bucket for b in bias_by_date.values())

    def ok_row(r) -> bool:
        b = bias_by_date[r['Date']]
        d = str(r['Trade_Direction']).strip()
        return (d == 'Long' and b.allowed_long) or (d == 'Short' and b.allowed_short)

    df['_bias_bucket'] = df['Date'].map(lambda d: bias_by_date[d].bucket)
    mask = df.apply(ok_row, axis=1)
    filt = df.loc[mask]

    gross = float(df['Net_$'].sum())
    kept = float(filt['Net_$'].sum())

    print('=== v2b legs + monthly ORB bias filter ===')
    print(f'  CSV legs:              {len(df)}')
    print(f'  Legs after filter:     {len(filt)}')
    print(f'  Σ Net_$ (all legs):    {gross:,.2f}')
    print(f'  Σ Net_$ (filtered):    {kept:,.2f}')
    print(f'  Δ filtered − all:      {kept - gross:,.2f}')
    print(f'  Unique session days:   {len(uniq_days)}')
    print('  Bias bucket (per trade-day calendar context):')
    for k in sorted(bc.keys()):
        print(f'    {k}: {bc[k]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
