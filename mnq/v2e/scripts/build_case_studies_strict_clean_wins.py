#!/usr/bin/env python3
"""
One PNG per **winning** strict-clean trade row (``Trade_PL > 0`` and/or ``Result`` win).

Levels (from the 2-pt stop model used in ``backtest_strict_clean_full.py``):
  - **Entry** = ``Entry_Price`` (v2b slip fill)
  - **TP** = ``Range_High + Range`` (long) / ``Range_Low - Range`` (short)
  - **Tight SL** = entry ∓ ``Stop_pts`` (default 2 MNQ index pts)

Input CSV: ``data/mnq_v2e_strict_clean_trades.csv`` (regenerate with
``adaptive_experiment/backtest_strict_clean_full.py``).

Output: ``case_studies/strict_clean_wins/`` + ``INDEX.md``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
POTIONS = V2E_ROOT.parent.parent
sys.path.insert(0, str(V2E_ROOT / 'scripts'))
sys.path.insert(0, str(POTIONS / 'scripts'))
from build_london_sweep_charts import draw_opens_research_chart  # noqa: E402
import annotate_mnq_v2b_range_context as ann  # noqa: E402

from prior_week_levels import DEFAULT_DAILY_DBN, load_mnq_front_daily, prior_week_last_close  # noqa: E402

DEFAULT_CSV = V2E_ROOT / 'data' / 'mnq_v2e_strict_clean_trades.csv'
OUT_DEFAULT = V2E_ROOT / 'case_studies' / 'strict_clean_wins'
M1 = Path('/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv')


def _levels(row: pd.Series):
    d = row['Trade_Direction']
    rh, rl, rv = float(row['Range_High']), float(row['Range_Low']), float(row['Range'])
    ent = float(row['Entry_Price'])
    sp = float(row.get('Stop_pts', 2.0))
    if d == 'Long':
        tp, sl = rh + rv, ent - sp
    else:
        tp, sl = rl - rv, ent + sp
    return ent, tp, sl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', type=Path, default=DEFAULT_CSV)
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    ap.add_argument('--out', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    ap.add_argument('--max', type=int, default=0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.csv.is_file():
        print(f'Missing CSV: {args.csv}', file=sys.stderr)
        return 1

    trd = pd.read_csv(args.csv)
    trd['Date'] = pd.to_datetime(trd['Date']).dt.date
    wins = trd[trd['Trade_PL'].astype(float) > 0].copy()
    if wins.empty:
        print('No winning rows.', file=sys.stderr)
        return 1
    wins = wins.sort_values('Date')
    if args.max:
        wins = wins.head(args.max)

    need = set(wins['Date'].unique())
    tmin, tmax = min(need), max(need)
    print(f'strict-clean wins: {len(wins)} chart(s) …', flush=True)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw).set_index('ts_event').sort_index()
    gby = {
        d: g
        for d, g in raw.groupby(
            pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
        )
    }
    try:
        daily_mnq = load_mnq_front_daily(args.daily_dbn)
    except Exception as e:
        print(f'warn: daily load: {e}', file=sys.stderr)
        daily_mnq = None

    tag = 'v2e strict-clean 2SL model — win-only'
    written = []
    for i, (_, r) in enumerate(wins.iterrows(), 1):
        d = r['Date']
        side = r['Trade_Direction']
        ent, tp, sl = _levels(r)
        pwc = prior_week_last_close(daily_mnq, d) if daily_mnq is not None else None

        sr = pd.Series(
            {
                'Symbol': str(r.get('Symbol', 'MNQ')),
                'Trade_Direction': side,
                'Trade_PL': float(r['Trade_PL']),
                'Net_$': float(r['Net_$']),
                'Range_High': r['Range_High'],
                'Range_Low': r['Range_Low'],
                'Range': r['Range'],
                'Regime': 'strict_clean_2sl_win',
            }
        )

        fn = args.out / f"{d}_{side}_Leg{int(r['Leg'])}_Win.png"
        ok = draw_opens_research_chart(
            d,
            gby,
            d,
            sr,
            fn,
            v2e_side=side,
            case_study_tag=tag,
            show_orb_ref=True,
            prior_week_close=pwc,
            level_entry=ent,
            level_tp=tp,
            level_sl=sl,
        )
        if ok:
            written.append({'date': d, 'side': side, 'file': fn.name, 'net': r['Net_$']})

    idx = args.out / 'INDEX.md'
    with open(idx, 'w', encoding='utf-8') as f:
        f.write('# Strict-clean wins — annotated ORB + entry / TP / 2pt SL\n\n')
        f.write(f'**CSV:** `{args.csv.name}`  ·  **Charts:** {len(written)}\n\n')
        f.write('| Date | Side | Net $ | PNG |\n|---|:---:|---:|:---|\n')
        for w in sorted(written, key=lambda x: (x['date'], x['file'])):
            f.write(
                f"| {w['date']} | {w['side']} | {w['net']} | [{w['file']}]({w['file']}) |\n"
            )
    print(f'Wrote {len(written)} PNGs + {idx}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
