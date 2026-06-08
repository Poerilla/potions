#!/usr/bin/env python3
"""
Equity path stats for London child-after-sweep under ``--day-universe all_rth`` rules:
RTH gate [09:30,16:00), sweep side inferred (``sweep_low=None``), same sim as charts.

By default applies **causal ORB pierce** gate (ORB [9:30–9:45] vs [02:00–09:30) London, annotator geometry).
Use ``--skip-causal-orb-filter`` to disable.

Prints win rate (among filled days), cumulative P/L, max drawdown (peak→trough), and
largest trough→peak recovery on the cumulative account curve.
"""
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
from sim_london_child_after_sweep import simulate_london_child_after_sweep  # noqa: E402
from sim_london_limit_scaleout import (  # noqa: E402
    SlMode,
    london_0200_0930_hilo,
    rth_1m,
)

ANNOTATED = POTIONS / 'mnq' / 'mnq_orb_results_stops_annotated.csv'
M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'

CHART_LO = time(0, 30)
CHART_HI = time(16, 0)


def trim_chart_session(df1: pd.DataFrame) -> pd.DataFrame:
    return df1[df1.index.map(lambda t: CHART_LO <= t.time() < CHART_HI)]


def session_has_rth_like_swept_orb(day_b: pd.DataFrame) -> bool:
    return day_b is not None and not day_b.empty and not rth_1m(day_b).empty


def equity_stats(daily_net: np.ndarray) -> Tuple[float, float, float, float, float]:
    """
    Returns (max_dd_dollars, max_recovery_dollars, final_equity, min_equity, max_equity).
    Max DD = largest peak-to-trough drop on cumulative sum.
    Max recovery = largest gain from any point on the path to a later peak (trough→peak segment).
    """
    cum = np.cumsum(daily_net)
    if len(cum) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    run_max = np.maximum.accumulate(cum)
    dd = run_max - cum
    max_dd = float(dd.max()) if len(dd) else 0.0
    rev_max = np.maximum.accumulate(cum[::-1])[::-1]
    recovery = rev_max - cum
    max_rec = float(recovery.max()) if len(recovery) else 0.0
    return max_dd, max_rec, float(cum[-1]), float(cum.min()), float(cum.max())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    ap.add_argument('--start', default=None)
    ap.add_argument('--end', default=None)
    ap.add_argument('--sl-points', type=float, default=30.0)
    ap.add_argument('--sl-mode', choices=('london_range', 'fixed'), default='london_range')
    ap.add_argument(
        '--skip-causal-orb-filter',
        action='store_true',
        help='Disable causal ORB vs London pierce gate (see sim_london_child_after_sweep).',
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

    rows: List[Tuple[date, float, bool]] = []
    sl_mode: SlMode = args.sl_mode

    for d in sorted(days):
        day = gby.get(d)
        if day is None or day.empty or not session_has_rth_like_swept_orb(day):
            continue
        df1 = trim_chart_session(day)
        lh, ll = london_0200_0930_hilo(df1)
        sim = simulate_london_child_after_sweep(
            df1,
            lh,
            ll,
            None,
            args.sl_points,
            sl_mode=sl_mode,
            require_causal_orb_pierce=not args.skip_causal_orb_filter,
        )
        net = float(sim.net_dollars) if sim.filled else 0.0
        rows.append((d, net, bool(sim.filled)))

    if not rows:
        print('No session days after RTH filter', file=sys.stderr)
        return 1

    nets = np.array([r[1] for r in rows], dtype=float)
    filled = np.array([r[2] for r in rows], dtype=bool)
    n_filled = int(filled.sum())
    wins = int((nets > 1e-9).sum())
    wins_among_filled = int(((filled) & (nets > 1e-9)).sum())

    max_dd, max_rec, final_eq, min_eq, max_eq = equity_stats(nets)

    wr_all_days = 100.0 * wins / len(rows)
    wr_filled = 100.0 * wins_among_filled / n_filled if n_filled else float('nan')

    print(
        'London child-after-sweep — all_RTH universe '
        f'(ORB pierce filter: {not args.skip_causal_orb_filter})'
    )
    print(f'  Sessions evaluated: {len(rows)}  (weekdays in [{t_start} .. {t_end}] with RTH 1m)')
    print(f'  Filled trades:      {n_filled}')
    print(f'  Win rate (days $>0 / all evaluated): {wr_all_days:.2f}%')
    print(f'  Win rate ($>0 / filled only):        {wr_filled:.2f}%')
    print(f'  Sum Net $ (account path, $0 on skip): {nets.sum():,.2f}')
    print(f'  Cumulative equity — low water / high water / terminal: {min_eq:,.2f}  |  {max_eq:,.2f}  |  {final_eq:,.2f}')
    print(f'  Max drawdown (peak→trough on cum path): {max_dd:,.2f}')
    print(f'  Max recovery (trough→later peak):       {max_rec:,.2f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
