#!/usr/bin/env python3
"""
Rebuild ``case_studies/all_v2e_trades_ok`` using the **adaptive experiment** stitched log
(v2b 60% 5m close + limit retrace arm + unchanged v2d).

For each ``status=ok`` v2e row we pick the **experiment** trade for that session: same
``Date``, prefer adaptive row with matching ``Trade_Direction`` when present; otherwise
the **first** adaptive trade printed for that day (CSV row order).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
V2E_SCR = Path(__file__).resolve().parent
POTIONS = V2E_ROOT.parent.parent
sys.path.insert(0, str(V2E_SCR))
sys.path.insert(0, str(POTIONS / 'scripts'))
from build_london_sweep_charts import draw_opens_research_chart  # noqa: E402
import annotate_mnq_v2b_range_context as ann  # noqa: E402

from prior_week_levels import (  # noqa: E402
    DEFAULT_DAILY_DBN,
    load_mnq_front_daily,
    prior_week_last_close,
)

EXP_ROOT = POTIONS / 'mnq' / 'adaptive_experiment'
DEFAULT_ADAPTIVE = EXP_ROOT / 'mnq_orb_results_adaptive_50_150_60pct.csv'

OUT_DEFAULT = V2E_ROOT / 'case_studies' / 'all_v2e_trades_ok'
V2E_CSV_DEFAULT = V2E_ROOT / 'data' / 'mnq_v2e_per_leg.csv'
M1 = Path('/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv')


def _pick_trade_row(day_ad: pd.DataFrame, pref_side: str) -> pd.Series:
    """One session row when v2e ref side does not equal adaptive-side for that date."""
    if day_ad.empty:
        raise ValueError('empty day_ad')
    m = day_ad[day_ad['Trade_Direction'] == pref_side]
    if len(m) == 1:
        return m.iloc[0]
    if len(m) > 1:
        return m.iloc[0]
    return day_ad.iloc[0]


def _levels(row: pd.Series) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Entry (filled limit), RH/RL ± Range target, opposite boundary stop."""
    d = row.get('Trade_Direction')
    if d not in ('Long', 'Short'):
        return None, None, None
    rh = float(row['Range_High'])
    rl = float(row['Range_Low'])
    rv = float(row['Range'])
    ent = float(row['Entry_Price'])
    if d == 'Long':
        return ent, rh + rv, rl
    return ent, rl - rv, rh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--v2e-csv', type=Path, default=V2E_CSV_DEFAULT)
    ap.add_argument('--adaptive', type=Path, default=DEFAULT_ADAPTIVE)
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    ap.add_argument('--out', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--max', type=int, default=0)
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.adaptive.is_file():
        print(f'Missing adaptive CSV: {args.adaptive}', file=sys.stderr)
        return 1

    ve = pd.read_csv(args.v2e_csv)
    ve['Date'] = pd.to_datetime(ve['Date'], errors='coerce').dt.date
    sub = ve.loc[ve['status'] == 'ok'].copy()
    if sub.empty:
        print('No status=ok rows.', file=sys.stderr)
        return 1
    sub = sub.sort_values('Date')
    if args.max:
        sub = sub.head(args.max)

    ad = pd.read_csv(args.adaptive)
    ad['Date'] = pd.to_datetime(ad['Date']).dt.date

    need = set(sub['Date'].unique())
    tmin, tmax = min(need), max(need)
    print(
        f'adaptive 60% case studies: {len(sub)} row(s)  |  1m load...',
        flush=True,
    )
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {
        d: g
        for d, g in raw.groupby(
            pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
        )
    }

    print(f'Load daily (prior week last close): {args.daily_dbn} ...', flush=True)
    try:
        daily_mnq = load_mnq_front_daily(args.daily_dbn)
    except Exception as e:
        print(f'  Warning: daily load failed: {e}', file=sys.stderr)
        daily_mnq = None

    tag = f'adaptive 50/150 · v2b 60% retrace · {args.adaptive.name}'
    written: list[dict] = []
    n_charts = len(sub)

    for i, (_, row) in enumerate(sub.iterrows(), 1):
        d = row['Date']
        side = row['Direction']
        if not isinstance(side, str) or side not in ('Short', 'Long'):
            print(f'  [{i}/{n_charts}] {d} skip: Direction={side!r}', flush=True)
            continue
        day = gby.get(d)
        if day is None or day.empty:
            print(f'  [{i}/{n_charts}] {d} no 1m, skip', flush=True)
            continue

        day_ad = ad[ad['Date'] == d].reset_index(drop=True)
        if day_ad.empty:
            print(f'  [{i}/{n_charts}] {d} {side} no stitched adaptive row — ORB-only chart', flush=True)
            tr = pd.Series(
                {
                    'Symbol': 'MNQ',
                    'Trade_Direction': side,
                    'Trade_PL': 0.0,
                    'Net_$': np.nan,
                    'Regime': 'no_trade_in_adaptive_log',
                    'Result': '',
                }
            )
            ent = tp = sl = None
        else:
            tr = _pick_trade_row(day_ad, side)
            ent, tp, sl = _levels(tr)
        pwc = None
        if daily_mnq is not None:
            pwc = prior_week_last_close(daily_mnq, d)

        out = args.out / f'{d}_{side}.png'
        try:
            ok = draw_opens_research_chart(
                d,
                gby,
                d,
                tr,
                out,
                v2e_side=side,
                case_study_tag=tag,
                show_orb_ref=True,
                prior_week_close=pwc,
                level_entry=ent,
                level_tp=tp,
                level_sl=sl,
            )
            if ok:
                written.append(
                    {
                        'date': d,
                        'dir': side,
                        'file': out.name,
                        'regime': tr.get('Regime', ''),
                        'net': tr.get('Net_$', np.nan),
                    }
                )
        except Exception as e:
            print(f'  [{i}/{n_charts}] {d} {side} error: {e}', flush=True)
        if i % 100 == 0 or i == n_charts:
            print(f'  [{i}/{n_charts}] wrote {len(written)} ...', flush=True)

    idx = args.out / 'INDEX.md'
    with open(idx, 'w', encoding='utf-8') as f:
        f.write('# Adaptive 60% experiment — case studies (matching v2e ok trades)\n\n')
        f.write(f'**Source:** `{tag}`  \n')
        f.write(f'**Generated:** {len(written)} PNGs (attempted {n_charts})\n\n')
        f.write('| Date | Side | Regime | Net $ | Chart |\n')
        f.write('|---|:---:|:---:|---:|:---|\n')
        for w in sorted(written, key=lambda x: (x['date'], str(x['dir']))):
            f.write(
                f"| {w['date']} | {w['dir']} | {w.get('regime', '')} | "
                f"{w.get('net', '')} | [{w['file']}]({w['file']}) |\n"
            )
    print(f'Wrote {len(written)} PNGs to {args.out}\nWrote {idx}')
    return 0 if written else 1


if __name__ == '__main__':
    raise SystemExit(main())
