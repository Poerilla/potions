#!/usr/bin/env python3
"""
**Strict-clean only** — full MNQ history: every session where the clean-break manifest has a
**strict_clean** leg that was a v2b **Win** at the OR target, re-simulated with **2 pt** stop
and **5 MNQ** (no 50/150 regime, **no v2d**).

Output:
  - ``adaptive_experiment/mnq_strict_clean_2sl_5ct_full.csv``
  - ``v2e/data/mnq_v2e_strict_clean_trades.csv`` (canonical v2e trade log for this model)

This is the dataset to use for strict-clean-only performance and win-only case studies.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd

POTIONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(POTIONS / 'scripts'))
sys.path.insert(0, str(POTIONS / 'mnq' / 'v2e' / 'scripts'))

from step2_preplaced_stops import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    DEFAULT_OPEN_RANGE_MIN,
    PRODUCTS,
    load_one_min,
    open_range_end_time,
)
from count_clean_break_v2b import simulate_day_trace  # noqa: E402

from backtest_clean_break_adaptive import net_dollars, simulate_tight_exit  # noqa: E402

MANIFEST_DEFAULT = (
    Path(__file__).resolve().parents[1] / 'v2e' / 'data' / 'clean_break_manifest.csv'
)
OUT_LOCAL = Path(__file__).resolve().parent / 'mnq_strict_clean_2sl_5ct_full.csv'
V2E_DATA = Path(__file__).resolve().parents[1] / 'v2e' / 'data' / 'mnq_v2e_strict_clean_trades.csv'

MNQ_TICK = float(PRODUCTS['MNQ']['tick'])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', type=Path, default=MANIFEST_DEFAULT)
    ap.add_argument('--stop-pts', type=float, default=2.0)
    ap.add_argument('--contracts', type=int, default=5)
    ap.add_argument('--open-range-minutes', type=int, default=DEFAULT_OPEN_RANGE_MIN)
    ap.add_argument('--no-copy-v2e', action='store_true', help='Do not write v2e/data/*.csv')
    args = ap.parse_args()

    man = pd.read_csv(args.manifest)
    man['Date'] = pd.to_datetime(man['Date']).dt.date
    strict = man[man['strict_clean'].astype(bool)].copy()

    tick = MNQ_TICK
    range_end = open_range_end_time(args.open_range_minutes)
    df = load_one_min('MNQ')
    rows: List[dict] = []

    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        rng = day_df[day_df['t'] < range_end]
        if rng.empty:
            continue
        rh, rl = float(rng['high'].max()), float(rng['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        trade_seg = day_df[day_df['t'] >= range_end]
        if trade_seg.empty:
            continue
        d = day
        want = strict[strict['Date'] == d]
        if want.empty:
            continue

        trs, mts = simulate_day_trace(rh, rl, rv, trade_seg, tick, 1)
        for k, ((direc, ent, _ox, ores), (fill_ts, _, _ex)) in enumerate(zip(trs, mts)):
            leg = k + 1
            m = want[(want['Leg'] == leg) & (want['Trade_Direction'] == direc)]
            if m.empty or ores != 'Win':
                continue
            tar = rh + rv if direc == 'Long' else rl - rv
            exit_px, res2 = simulate_tight_exit(
                trade_seg, fill_ts, direc, ent, tar, args.stop_pts
            )
            net = net_dollars(direc, ent, exit_px, res2, args.contracts)
            pl_pts = (exit_px - ent) if direc == 'Long' else (ent - exit_px)
            sym = trade_seg.iloc[0]['symbol']
            rows.append(
                {
                    'Date': d,
                    'Model': 'strict_clean_2sl',
                    'Symbol': sym,
                    'Range_High': rh,
                    'Range_Low': rl,
                    'Range': rv,
                    'Trade_Direction': direc,
                    'Leg': leg,
                    'Entry_Price': ent,
                    'Exit_Price': exit_px,
                    'Stop_pts': args.stop_pts,
                    'Trade_PL': round(pl_pts, 6),
                    'Net_$': round(net, 2),
                    'Result': res2,
                    'Contracts': args.contracts,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        print('No rows.')
        return
    out = out.sort_values(['Date', 'Leg'])
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    OUT_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_LOCAL, index=False)

    if not args.no_copy_v2e:
        V2E_DATA.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT_LOCAL, V2E_DATA)

    print('=== Strict-clean only (full dataset, no v2d, no MA regime) ===\n')
    print(f"Stop {args.stop_pts:g} pts  |  {args.contracts} MNQ")
    print(f"Trades: {len(out):,} -> {OUT_LOCAL}")
    if not args.no_copy_v2e:
        print(f"Canonical copy: {V2E_DATA}")
    print(f"Total Net_$: ${out['Net_$'].sum():,.2f}")
    eq = out['Net_$'].cumsum()
    print(f"Max DD: ${(eq - eq.cummax()).min():,.2f}")
    print(f"Win rate (Trade_PL>0): {(out['Trade_PL'] > 0).mean() * 100:.1f}%")


if __name__ == '__main__':
    main()
