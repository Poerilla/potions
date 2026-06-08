#!/usr/bin/env python3
"""
Build one 5m chart per row in `mnq_v2e_per_leg.csv` (default: `status=ok`).

**Default (`--style opens`)** — **Premarket H/L** (prev calendar day **18:00 ET** through
**before 9:30** on session day — full overnight electronic, not 02:00–09:30 London-only);
**NY 00:00** and **9:30** 1m opens; **prior week last close** (daily) + above/below note
vs 9:30. Chart window **18:00 prior → 16:00** session. No v2e trade marks.

`--style v2e` — legacy chart with v2e sim (limits, Ldn mid, fill markers).

Output:  `../case_studies/all_v2e_trades_ok/<date>_{Long|Short}.png` and `INDEX.md`
Requires: same 1m export as `sim_v2e_all.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytz

# Reuse 5m chart + loader
V2E_ROOT = Path(__file__).resolve().parent.parent
V2E_SCR = Path(__file__).resolve().parent
POTIONS = V2E_ROOT.parent.parent
sys.path.insert(0, str(V2E_SCR))
from build_london_sweep_charts import (  # noqa: E402
    ANNOTATED,
    M1,
    draw_chart,
    draw_opens_research_chart,
    trim_chart_session,
)
from prior_week_levels import (  # noqa: E402
    DEFAULT_DAILY_DBN,
    load_mnq_front_daily,
    prior_week_last_close,
)
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

NY = pytz.timezone('America/New_York')
OUT_DEFAULT = V2E_ROOT / 'case_studies' / 'all_v2e_trades_ok'
V2E_CSV_DEFAULT = V2E_ROOT / 'data' / 'mnq_v2e_per_leg.csv'


def _merge_v2b_first(annot: pd.DataFrame) -> pd.DataFrame:
    a = annot.copy()
    a['Date'] = pd.to_datetime(a['Date'], errors='coerce').dt.date
    a = a.sort_values('Date')
    return a.groupby('Date', as_index=False).first()


def _chart_row(ve: pd.Series, m: Optional[pd.Series]) -> pd.Series:
    """Trade row for title: prefer merged annot row, else v2e-only fields."""
    if m is not None and not m.empty:
        s = m.copy()
        s['Trade_Direction'] = m.get('Trade_Direction', ve.get('v2b_first_row_direction', 'Short'))
        if 'Result' not in s.index or pd.isna(s.get('Result')):
            s['Result'] = ''
        if 'Trade_PL' not in s.index or pd.isna(s.get('Trade_PL')):
            s['Trade_PL'] = 0.0
        if 'Net_$' not in s.index and 'v2b_Net' in ve.index:
            s['Net_$'] = ve.get('v2b_Net', np.nan)
        if 'Symbol' not in s.index or pd.isna(s.get('Symbol')):
            s['Symbol'] = 'MNQ'
        return s
    return pd.Series(
        {
            'Date': ve['Date'],
            'Symbol': 'MNQ',
            'Trade_Direction': ve.get('v2b_first_row_direction', '-'),
            'Result': '',
            'Net_$': ve.get('v2b_Net', np.nan),
            'Trade_PL': 0.0,
        }
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description='v2e case studies: one PNG per filled sim row (or wider status filter).',
    )
    ap.add_argument(
        '--v2e-csv', type=Path, default=V2E_CSV_DEFAULT, help='Output from sim_v2e_all.py',
    )
    ap.add_argument(
        '--annotated', type=Path, default=ANNOTATED,
        help='Optional v2b CSV for Symbol / Result on title (first row per date)',
    )
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    ap.add_argument('--out', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--max', type=int, default=0, help='Cap charts (0 = all).')
    ap.add_argument(
        '--sl-mode', choices=['london_range', 'fixed'], default='london_range',
        help='Must match sim_v2e_all (default: Ldn range = stop width).',
    )
    ap.add_argument(
        '--sl-points', type=float, default=30.0, help='Must match the sim; used when --sl-mode fixed.',
    )
    ap.add_argument(
        '--limit-offset', type=int, default=0, help='Must match the sim that built the CSV.',
    )
    ap.add_argument(
        '--include-no-fill',
        action='store_true',
        help='Also draw rows with status=no_fill (no RTH limit fill).',
    )
    ap.add_argument(
        '--style', choices=['opens', 'v2e'], default='opens',
        help='opens: NY 00:00 + 9:30 open lines only (default). v2e: full sim chart.',
    )
    ap.add_argument(
        '--no-orb', action='store_true',
        help='With --style opens: hide ORB RH/RL reference.',
    )
    ap.add_argument(
        '--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN,
        help='opens: Databento MNQ daily ohlcv for prior-week last close.',
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    ve = pd.read_csv(args.v2e_csv)
    if ve.empty:
        print('Empty v2e CSV', file=sys.stderr)
        return 1
    ve['Date'] = pd.to_datetime(ve['Date'], errors='coerce').dt.date

    stat_ok = ve['status'] == 'ok'
    if args.include_no_fill:
        mask = stat_ok | (ve['status'] == 'no_fill')
    else:
        mask = stat_ok
    sub = ve.loc[mask].copy()
    if sub.empty:
        print('No rows for chosen status filter.', file=sys.stderr)
        return 1
    sub = sub.sort_values('Date')
    if args.max:
        sub = sub.head(args.max)

    # Merge first v2b row / date for chart annotations
    ann_df = pd.read_csv(args.annotated)
    mfirst = _merge_v2b_first(ann_df)
    mby = mfirst.set_index('Date')

    need = set(sub['Date'].unique())
    tmin, tmax = min(need), max(need)
    n_charts = len(sub)
    print(
        f'all_v2e case studies: {n_charts} row(s)  |  {len(need)} unique dates  |  1m load...',
        flush=True,
    )
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    daily_mnq = None
    if args.style == 'opens':
        print(f'Load daily (prior week last close): {args.daily_dbn} ...', flush=True)
        try:
            daily_mnq = load_mnq_front_daily(args.daily_dbn)
        except Exception as e:
            print(f'  Warning: could not load daily: {e} — PWC line skipped.', file=sys.stderr)

    tag = (
        f"NY opens research · {args.v2e_csv.name}"
        if args.style == 'opens'
        else f"all v2e trades (ok) · {args.v2e_csv.name}"
    )

    written: list[dict] = []
    for i, (_, row) in enumerate(sub.iterrows(), 1):
        d = row['Date']
        v2e_side = row['Direction']
        if not isinstance(v2e_side, str) or v2e_side not in ('Short', 'Long'):
            print(f'  [{i}/{n_charts}] {d} skip: Direction={v2e_side!r}', flush=True)
            continue
        day = gby.get(d)
        if day is None or day.empty:
            print(f'  [{i}/{n_charts}] {d} no 1m, skip', flush=True)
            continue
        mrow = mby.loc[d] if d in mby.index else None
        tr = _chart_row(row, mrow)
        out = args.out / f"{d}_{v2e_side}.png"
        try:
            if args.style == 'opens':
                pwc = None
                if daily_mnq is not None:
                    pwc = prior_week_last_close(daily_mnq, d)
                ok_draw = draw_opens_research_chart(
                    d,
                    gby,
                    d,
                    tr,
                    out,
                    v2e_side=v2e_side,
                    case_study_tag=tag,
                    show_orb_ref=not args.no_orb,
                    prior_week_close=pwc,
                )
            else:
                df1 = trim_chart_session(day)
                ok_draw = draw_chart(
                    d,
                    df1,
                    tr,
                    out,
                    sl_points=args.sl_points,
                    limit_offset_ticks=args.limit_offset,
                    v2e_side=v2e_side,
                    case_study_tag=tag,
                    sl_mode=args.sl_mode,
                )
            if ok_draw:
                written.append(
                    {
                        'date': d,
                        'dir': v2e_side,
                        'v2e_pnl': row.get('v2e_pnl_5m', np.nan),
                        'status': row.get('status', ''),
                        'tight_930': row.get('tight_930_entry_risk', False),
                        'file': out.name,
                    }
                )
        except Exception as e:
            print(f'  [{i}/{n_charts}] {d} {v2e_side} error: {e}', flush=True)
        if i % 100 == 0 or i == n_charts:
            print(f'  [{i}/{n_charts}] wrote {len(written)} ...', flush=True)

    idx = args.out / 'INDEX.md'
    with open(idx, 'w', encoding='utf-8') as f:
        title = (
            '# v2e case studies — NY 00:00 & 9:30 opens (5m, no trade overlay)\n\n'
            if args.style == 'opens'
            else '# v2e — all sim sessions (per filled trade)\n\n'
        )
        f.write(title)
        if args.style == 'opens':
            f.write(
                f'**Chart style:** `opens` — **premarket H/L** (prev 18:00–before 9:30), '
                f'**00:00** & **9:30** opens, **prior week last close** from `{args.daily_dbn.name}`. '
                f'ORB: `{"off" if args.no_orb else "ref"}`\n\n'
            )
        f.write(
            f'**Source:** `{args.v2e_csv.name}`  ·  **filter:** '
            f'`status=ok`'
            f"{' or `no_fill`' if args.include_no_fill else ''}  "
        )
        if args.style == 'v2e':
            f.write(f'·  `sl_mode={args.sl_mode}`  `sl_points={args.sl_points}`  offset={args.limit_offset}\n\n')
        else:
            f.write('\n\n')
        f.write(
            f'**Generated:** {len(written)} charts  (attempted {n_charts} rows)  \n\n'
        )
        f.write('| Date | Side | v2e $ | status | tight_930 | Chart |\n')
        f.write('|---|:---:|---:|:---:|:---:|:---|\n')
        for w in sorted(written, key=lambda x: (x['date'], str(x['dir']))):
            ts = w.get('tight_930', False)
            tss = 'Y' if ts else ''
            f.write(
                f"| {w['date']} | {w['dir']} | {w['v2e_pnl']!s} | {w.get('status', '')} | {tss} | "
                f"[{w['file']}]({w['file']}) |\n"
            )
    print(f"Wrote {len(written)} PNGs to {args.out}\nWrote {idx}")
    return 0 if written else 1


if __name__ == '__main__':
    raise SystemExit(main())
