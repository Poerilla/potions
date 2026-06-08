#!/usr/bin/env python3
"""Compute **v2b_m** stats (long-only, breaks by default) and optionally export qualified legs CSV."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
MNQ_ROOT = HERE.parents[1]

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(MNQ_ROOT))
sys.path.insert(0, str(MNQ_ROOT / 'scripts'))

from plot_daily_prior_month_levels import (  # noqa: E402
    load_mnq_front_daily,
    monthly_high_low,
    prior_month_levels_series,
)

from engine import EPS_IDX_PT, qualify_v2b_m_legs, summary_stats  # noqa: E402

DEFAULT_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
DEFAULT_STOPS = MNQ_ROOT / 'mnq_orb_results_stops.csv'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--stops-csv', type=Path, default=DEFAULT_STOPS)
    ap.add_argument(
        '--include-hemisphere',
        action='store_true',
        help='Also allow hemisphere_long (default: bullish_break only → flat on hemisphere-only months)',
    )
    ap.add_argument('--export-csv', type=Path, default=None, help='Write qualified legs CSV')
    ap.add_argument('--json', action='store_true', help='Print summary as JSON')
    args = ap.parse_args()

    if not args.daily_dbn.is_file():
        print(f'Missing DBN: {args.daily_dbn}', file=sys.stderr)
        return 1
    if not args.stops_csv.is_file():
        print(f'Missing stops CSV: {args.stops_csv}', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)
    monthly = monthly_high_low(daily)
    pm_h, pm_l = prior_month_levels_series(daily, monthly)

    legs = qualify_v2b_m_legs(
        args.stops_csv, daily, pm_h, pm_l, include_hemisphere=args.include_hemisphere
    )
    stats = summary_stats(legs)

    if args.json:
        print(json.dumps(stats, indent=2))
        return 0

    mode = 'bullish_break only (hemisphere months flat)' if not args.include_hemisphere else '+ hemisphere_long'
    print(f'v2b_m  |  long-only  |  {mode}  |  EPS slack (index pts) = {EPS_IDX_PT}')
    print()
    lg = stats['long_legs']
    print(
        f"Long legs (bull bias + PM-high geometry):\n"
        f"  legs={lg['n']}  TP-style wins={lg['tp']}  WR={lg['wr']:.2f}%  Σ Net=${lg['sum_net']:,.2f}"
    )
    if lg['n']:
        print(f"  mean Net/leg=${lg['mean_net']:+.2f}")
    cb = stats.get('combined') or {}
    if cb:
        print(
            f"\nDaily equity path (one leg max per session day in tier‑1 CSV):\n"
            f"  legs={cb['n_legs']}  session-days={cb['n_days']}  TP legs={cb['tp_legs']}  leg WR={cb['wr_legs']:.2f}%\n"
            f"  Σ Net=${cb['sum_net']:,.2f}  max DD (daily steps)=${cb['max_dd_daily_path']:,.2f}"
        )

    if args.export_csv:
        if legs.empty:
            print('Nothing to export.', file=sys.stderr)
            return 1
        legs = legs.sort_values(['Date', 'Trade_Direction'])
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        legs.to_csv(args.export_csv, index=False)
        print(f'\nWrote {args.export_csv} ({len(legs)} rows)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
