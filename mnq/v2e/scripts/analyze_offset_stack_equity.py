#!/usr/bin/env python3
"""Equity path for ``simulate_london_offset_stack_entry`` (same-level stacked limits + shared SL); same session grid as offset equity."""
from __future__ import annotations

import argparse
import sys
from datetime import date, time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

V2E_SCR = Path(__file__).resolve().parent
POTIONS = V2E_SCR.parents[2]
sys.path.insert(0, str(V2E_SCR))
sys.path.insert(0, str(POTIONS / 'scripts'))

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from sim_london_limit_scaleout import london_0200_0930_hilo, rth_1m  # noqa: E402
from sim_london_offset_stack_entry import simulate_london_offset_stack_entry  # noqa: E402

ANNOTATED = POTIONS / 'mnq' / 'mnq_orb_results_stops_annotated.csv'
M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'

CHART_LO = time(0, 30)
CHART_HI = time(16, 0)


def trim_chart_session(df1: pd.DataFrame) -> pd.DataFrame:
    return df1[df1.index.map(lambda t: CHART_LO <= t.time() < CHART_HI)]


def session_has_rth_like_swept_orb(day_b: pd.DataFrame) -> bool:
    return day_b is not None and not day_b.empty and not rth_1m(day_b).empty


def equity_stats(daily_net: np.ndarray) -> Tuple[float, float, float, float, float]:
    cum = np.cumsum(daily_net)
    if len(cum) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    run_max = np.maximum.accumulate(cum)
    dd = run_max - cum
    max_dd = float(dd.max())
    rev_max = np.maximum.accumulate(cum[::-1])[::-1]
    recovery = rev_max - cum
    max_rec = float(recovery.max())
    return max_dd, max_rec, float(cum[-1]), float(cum.min()), float(cum.max())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    ap.add_argument('--start', default=None)
    ap.add_argument('--end', default=None)
    ap.add_argument('--offset-pts', type=float, default=30.0)
    ap.add_argument('--sl-pts', type=float, default=30.0)
    ap.add_argument('--max-contracts', type=int, default=3)
    ap.add_argument(
        '--skip-causal-orb-filter',
        action='store_true',
    )
    args = ap.parse_args()

    df = pd.read_csv(args.annotated)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    t_start = pd.to_datetime(args.start).date() if args.start else df['Date'].min()
    t_end = pd.to_datetime(args.end).date() if args.end else df['Date'].max()

    days: List[date] = [ts.date() for ts in pd.bdate_range(pd.Timestamp(t_start), pd.Timestamp(t_end))]
    need = set(days)
    tmin, tmax = min(need), max(need)

    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    orb_on = not args.skip_causal_orb_filter
    nets: List[float] = []
    filled = 0
    wins = 0

    for d in sorted(days):
        day = gby.get(d)
        if day is None or day.empty or not session_has_rth_like_swept_orb(day):
            continue
        df1 = trim_chart_session(day)
        lh, ll = london_0200_0930_hilo(df1)
        sim = simulate_london_offset_stack_entry(
            df1,
            lh,
            ll,
            None,
            offset_pts=args.offset_pts,
            sl_pts=args.sl_pts,
            max_contracts=args.max_contracts,
            require_causal_orb_pierce=orb_on,
        )
        net = float(sim.net_dollars) if sim.filled else 0.0
        nets.append(net)
        if sim.filled:
            filled += 1
            if net > 1e-9:
                wins += 1

    arr = np.array(nets, dtype=float)
    if len(arr) == 0:
        print('No sessions', file=sys.stderr)
        return 1

    max_dd, max_rec, final_eq, min_eq, max_eq = equity_stats(arr)

    print(
        f'London **offset stack** sim  ·  L±{args.offset_pts:g} · SL={args.sl_pts:g} · '
        f'max {args.max_contracts} ct  ·  ORB pierce: {orb_on}'
    )
    print(f'  Sessions evaluated: {len(arr)}')
    print(f'  Filled trades:      {filled}')
    if filled:
        print(f'  Win rate (filled, Net$>0): {100.0 * wins / filled:.2f}%')
    print(f'  Sum Net $: {arr.sum():,.2f}')
    print(f'  Equity low / high / terminal: {min_eq:,.2f}  |  {max_eq:,.2f}  |  {final_eq:,.2f}')
    print(f'  Max drawdown: {max_dd:,.2f}   Max recovery: {max_rec:,.2f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
