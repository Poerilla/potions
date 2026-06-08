#!/usr/bin/env python3
"""
Feasibility: **no London** — fade **prior week** H/L only, **RTH 9:30–16:00** on 1m.

For each stop width in {20, 30, 40, 50, 100} **index points** (and optional custom list):

  * **PWH short** — first 1m where ``high >= PWH``; entry = PWH; stop = PWH + SL;
    if not flat first, last RTH 1m **close** (EOD). No take-profit; **only** stop or EOD exit.
  * **PWL long** — first 1m where ``low <= PWL``; entry = PWL; stop = PWL − SL;
    else EOD close.

**Same bar** (conservative): on the entry bar, if both entry and stop can print, count **stop**.

P/L: ``(exit − entry)`` in points × ``$2`` × *contracts* (MNQ), direction-aware.

This does **not** decide between PWH and PWL on the same day — the two tables are
**independent** “what if we only ran this leg every session” samples (days with no
touch are excluded for that leg).
"""
from __future__ import annotations

import argparse
import sys
from datetime import time
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

POTIONS_MNQ = Path(__file__).resolve().parent.parent
V2E_SCRIPTS = POTIONS_MNQ / 'v2e' / 'scripts'
sys.path.insert(0, str(V2E_SCRIPTS))
from prior_week_levels import (  # noqa: E402
    DEFAULT_DAILY_DBN,
    load_mnq_front_daily,
    prior_week_hilo,
)

POTIONS = POTIONS_MNQ.parent
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

RTH_O = time(9, 30)
RTH_C = time(16, 0)
DOLLARS_PER_POINT = 2.0  # 1 MNQ
M1 = POTIONS_MNQ / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
ANNOTATED = POTIONS_MNQ / 'mnq_orb_results_stops_annotated.csv'


def rth_1m(day: pd.DataFrame) -> pd.DataFrame:
    return day[day.index.map(lambda t: RTH_O <= t.time() < RTH_C)].copy()


def first_idx_short_touch(rth: pd.DataFrame, pwh: float) -> Optional[int]:
    for i in range(len(rth)):
        if float(rth.iloc[i]['high']) + 1e-9 >= pwh:
            return i
    return None


def first_idx_long_touch(rth: pd.DataFrame, pwl: float) -> Optional[int]:
    for i in range(len(rth)):
        if float(rth.iloc[i]['low']) - 1e-9 <= pwl:
            return i
    return None


def pnl_usd(
    pnl_points: float, n_contracts: int
) -> float:
    return pnl_points * DOLLARS_PER_POINT * n_contracts


def sim_pwh_short_eod(
    rth: pd.DataFrame, pwh: float, sl_pts: float, n_contracts: int
) -> Optional[Tuple[str, float]]:
    """
    Returns ``(exit_reason, pnl_usd)`` or ``None`` if PWH never touched.
    exit_reason: ``stop`` | ``eod``
    """
    j = first_idx_short_touch(rth, pwh)
    if j is None:
        return None
    entry = float(pwh)
    sl_px = entry + float(sl_pts)
    for k in range(j, len(rth)):
        h = float(rth.iloc[k]['high'])
        if h + 1e-9 >= sl_px:
            pts = entry - sl_px
            return 'stop', pnl_usd(pts, n_contracts)
    last = float(rth.iloc[-1]['close'])
    pts = entry - last
    return 'eod', pnl_usd(pts, n_contracts)


def sim_pwl_long_eod(
    rth: pd.DataFrame, pwl: float, sl_pts: float, n_contracts: int
) -> Optional[Tuple[str, float]]:
    j = first_idx_long_touch(rth, pwl)
    if j is None:
        return None
    entry = float(pwl)
    sl_px = entry - float(sl_pts)
    for k in range(j, len(rth)):
        lo = float(rth.iloc[k]['low'])
        if lo - 1e-9 <= sl_px:
            pts = sl_px - entry  # = -sl_pts
            return 'stop', pnl_usd(pts, n_contracts)
    last = float(rth.iloc[-1]['close'])
    pts = last - entry
    return 'eod', pnl_usd(pts, n_contracts)


def _agg(name: str, results: List[Tuple[str, float]]) -> None:
    n = len(results)
    if n == 0:
        print(f'  {name}: (no tags)')
        return
    n_stop = sum(1 for r, _ in results if r == 'stop')
    n_eod = sum(1 for r, _ in results if r == 'eod')
    total = sum(p for _, p in results)
    n_win = sum(1 for _, p in results if p > 0)
    print(
        f'  {name}:  trades={n}  (stop={n_stop}, eod={n_eod})  |  sum $ = {total:,.2f}  |  '
        f'win% = {100.0 * n_win / n:.1f}%  |  avg $/trade = {total / n:,.2f}'
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--sl-list',
        type=str,
        default='20,30,40,50,100',
        help='Comma-separated SL widths (index points)',
    )
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    ap.add_argument('--m1', type=Path, default=M1, help='1m OHLCV csv')
    ap.add_argument('--annotated', type=Path, default=ANNOTATED, help='date list')
    ap.add_argument('--contracts', type=int, default=1, help='MNQ contracts (× $2/point/ct)')
    args = ap.parse_args()
    sls = [float(x.strip()) for x in args.sl_list.split(',') if x.strip()]

    df0 = pd.read_csv(args.annotated)
    df0['Date'] = pd.to_datetime(df0['Date']).dt.date
    need = set(df0['Date'].unique())
    tmin, tmax = min(need), max(need)

    print('Load daily (PWH/PWL) ...', flush=True)
    daily = load_mnq_front_daily(args.daily_dbn)

    print('Load 1m ...', flush=True)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    days = sorted(d for d in need if d in gby and len(gby[d]) > 0)

    for sl in sls:
        print(f"\n======== SL = {sl:g} index points  ({args.contracts} MNQ) ========")
        pwh_out: List[Tuple[str, float]] = []
        pwl_out: List[Tuple[str, float]] = []
        for d in days:
            pwh, pwl = prior_week_hilo(daily, d)
            if pwh is None or pwl is None:
                continue
            r = rth_1m(gby[d])
            if r.empty:
                continue
            a = sim_pwh_short_eod(r, pwh, sl, args.contracts)
            if a is not None:
                pwh_out.append(a)
            b = sim_pwl_long_eod(r, pwl, sl, args.contracts)
            if b is not None:
                pwl_out.append(b)
        _agg('Fade PWH (short, touch → stop or EOD)', pwh_out)
        _agg('Fade PWL (long,  touch → stop or EOD)', pwl_out)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
