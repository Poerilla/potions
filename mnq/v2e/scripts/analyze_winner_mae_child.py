#!/usr/bin/env python3
"""
Distribution of **maximum adverse excursion (MAE)** vs **average entry** for TP winners
(``result_label == 'Win'``) in ``simulate_london_child_after_sweep``.

MAE is updated each RTH 1m bar while position is open: Long ``max(avg_entry - low)``,
Short ``max(high - avg_entry)``. Same path options as ``analyze_london_child_after_sweep_equity.py``.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, time
from pathlib import Path
from typing import List

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


def pct(a: np.ndarray, q: float) -> float:
    return float(np.percentile(a, q)) if len(a) else float('nan')


def hist_lines(a: np.ndarray, edges: List[float]) -> List[tuple[str, int]]:
    """Bucket counts with labels [e0,e1), ... last bin [edges[-1], inf)."""
    out = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        n = int(np.sum((a >= lo) & (a < hi)))
        out.append((f'[{lo:g}, {hi:g})', n))
    lo = edges[-1]
    n = int(np.sum(a >= lo))
    out.append((f'[{lo:g}, ∞)', n))
    return out


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
        help='Match equity script: disable causal ORB pierce gate.',
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

    sl_mode: SlMode = args.sl_mode
    orb_on = not args.skip_causal_orb_filter

    winners_tp: List[float] = []

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
            require_causal_orb_pierce=orb_on,
        )
        if not sim.filled or sim.result_label != 'Win':
            continue
        if np.isnan(sim.max_adverse_pts):
            continue
        winners_tp.append(float(sim.max_adverse_pts))

    arr = np.array(winners_tp, dtype=float)
    if len(arr) == 0:
        print('No strict TP winners (result_label Win) in span.', file=sys.stderr)
        return 1

    print('TP winners only (`Win` = opposing London corner); MAE vs **average entry** (index points)')
    print(f'  Sessions grid: {len(days)} weekdays  ·  causal ORB pierce: {orb_on}')
    print(f'  TP-win sample size: {len(arr)}')
    print(f'  Mean MAE:   {arr.mean():.3f} pt')
    print(f'  Std MAE:    {arr.std():.3f} pt')
    print(f'  Min / Max:  {arr.min():.3f}  /  {arr.max():.3f} pt')
    print(
        f'  Percentiles (pt):  p50={pct(arr, 50):.2f}  p75={pct(arr, 75):.2f}  '
        f'p90={pct(arr, 90):.2f}  p95={pct(arr, 95):.2f}  p99={pct(arr, 99):.2f}'
    )
    print()
    print('Histogram (index points MAE):')
    edges = [0, 2, 5, 10, 15, 20, 30, 50]
    for label, n in hist_lines(arr, edges):
        pct_n = 100.0 * n / len(arr)
        bar = '█' * int(round(pct_n / 2))
        print(f'  {label:18}  {n:4}  ({pct_n:5.1f}%)  {bar}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
