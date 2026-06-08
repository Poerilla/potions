#!/usr/bin/env python3
"""
Case-study PNGs for **v2d fade** legs **only when adaptive MA regime selects v2d**
(i.e. prior trading day's MNQ daily MA50 ≤ MA150 — ``Regime == \"v2d\"`` in the unified adaptive child CSV).

Requires legs CSV from ``orb_adaptive_50_150_child.py`` (has Entry_Time / TP_Price / Stop_Price for charting).

Splits sampled calendar days into **winners** (Σ Net_$ > 0 that session) vs **losers** (Σ Net_$ < 0),
writes PNGs under ``winners/`` and ``losers/`` plus parent ``INDEX.md``.
"""
from __future__ import annotations

import argparse
import importlib.util
import random
from pathlib import Path
from typing import Callable

import pandas as pd

_HERE = Path(__file__).resolve().parent
MNQ_ROOT = _HERE.parent.parent
CSV_DEFAULT = MNQ_ROOT / 'v2d' / 'mnq_orb_results_adaptive_50_150_child_3max.csv'

HELP_EPILOG = """\
Prerequisite CSV (timestamps required for charts):
  cd potions/mnq/v2d
  python3 orb_adaptive_50_150_child.py --max-child-adds 0 --out mnq_orb_results_adaptive_50_150_child_m0.csv

Example runs:
  cd potions/mnq/case_studies/v2d_regime_case_studies
  python3 build_v2d_winners_losers.py \\
      --csv ../../v2d/mnq_orb_results_adaptive_50_150_child_3max.csv \\
      --n-per-bucket 18 --seed 44 --start 2024-01-01

Outputs:
  winners/*.png   — sampled Regime=v2d days with positive day Σ Net_$.
  losers/*.png    — sampled Regime=v2d days with negative day Σ Net_$.
  INDEX.md        — tables linking both folders.

Uses shared renderer from ``v2b_c/build_case_studies.py`` (fade tier‑1 labeling).
"""


def _load_v2bc_chart_module():
    path = _HERE.parent / 'v2b_c' / 'build_case_studies.py'
    spec = importlib.util.spec_from_file_location('v2bc_cs', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            'v2d regime-only case studies (winners vs losers folders); '
            'samples days where adaptive CSV Regime=v2d.'
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--csv', type=str, default=str(CSV_DEFAULT), help='Adaptive leg CSV (with Regime column)')
    ap.add_argument('--n-per-bucket', type=int, default=18, metavar='N', help='Samples each for winners and losers')
    ap.add_argument('--seed', type=int, default=44)
    ap.add_argument('--start', default='2024-01-01', help='Earliest calendar date (CSV dates)')
    ap.add_argument(
        '--out-root',
        type=str,
        default=str(_HERE),
        help='Parent folder containing winners/ and losers/ subfolders',
    )
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        raise SystemExit(
            f'Missing {csv_path}\nGenerate with:\n'
            '  cd ../../v2d && python3 orb_adaptive_50_150_child.py --max-child-adds 2 '
            f'--out {CSV_DEFAULT.name}'
        )

    mod = _load_v2bc_chart_module()
    draw_chart: Callable[..., object] = mod.draw_chart
    load_dbn_once = mod.load_dbn_once

    csv = pd.read_csv(csv_path)
    if 'Regime' not in csv.columns:
        raise SystemExit('CSV must include Regime column (use orb_adaptive_50_150_child.py output).')
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv = csv[csv['Date'] >= pd.to_datetime(args.start).date()]
    v2d = csv[csv['Regime'].astype(str) == 'v2d'].copy()
    if v2d.empty:
        raise SystemExit('No Regime=v2d rows after --start filter.')

    day_net = v2d.groupby('Date', as_index=False)['Net_$'].sum()
    day_net['Net_$'] = day_net['Net_$'].astype(float)
    win_dates = sorted(day_net.loc[day_net['Net_$'] > 0, 'Date'].tolist())
    lose_dates = sorted(day_net.loc[day_net['Net_$'] < 0, 'Date'].tolist())

    rng = random.Random(args.seed)
    n = args.n_per_bucket
    picked_win = sorted(rng.sample(win_dates, min(n, len(win_dates))))
    picked_lose = sorted(rng.sample(lose_dates, min(n, len(lose_dates))))

    out_root = Path(args.out_root)
    w_dir = out_root / 'winners'
    l_dir = out_root / 'losers'
    w_dir.mkdir(parents=True, exist_ok=True)
    l_dir.mkdir(parents=True, exist_ok=True)

    print(
        f'Regime=v2d days: win_pool={len(win_dates)} lose_pool={len(lose_dates)}  '
        f'sample → winners={len(picked_win)} losers={len(picked_lose)}  seed={args.seed}'
    )

    by_date = load_dbn_once()

    def run_batch(label: str, dates: list, folder: Path, rows_accum: list) -> None:
        for i, d in enumerate(dates, 1):
            if d not in by_date:
                print(f'  [{label} {i}/{len(dates)}] {d}: no DBN day')
                continue
            cr = v2d[v2d['Date'] == d]
            if cr.empty:
                print(f'  [{label} {i}/{len(dates)}] {d}: no v2d rows')
                continue
            day_sum = float(cr['Net_$'].astype(float).sum())
            outpath = folder / f'{d}.png'
            try:
                pat, _nd, _sx, rv = draw_chart(d, by_date[d], cr, outpath)
                rows_accum.append(
                    {
                        'date': d,
                        'symbol': cr['Symbol'].iloc[0],
                        'rv': rv,
                        'pattern': pat,
                        'day_net': day_sum,
                    }
                )
                print(f'  [{label} {i:>2}/{len(dates)}] {d} net=${day_sum:+,.2f} -> {outpath.name}')
            except Exception as e:
                print(f'  [{label} {i}/{len(dates)}] {d}: {e}')

    win_rows: list = []
    lose_rows: list = []
    run_batch('win', picked_win, w_dir, win_rows)
    run_batch('lose', picked_lose, l_dir, lose_rows)

    idx = out_root / 'INDEX.md'
    sw = sum(r['day_net'] for r in win_rows)
    sl = sum(r['day_net'] for r in lose_rows)
    with open(idx, 'w') as f:
        f.write('# v2d regime — winners vs losers (adaptive favours chop)\n\n')
        f.write(
            'Charts include **only** sessions where **`Regime=v2d`** (prior-day MA50 ≤ MA150 on MNQ daily closes)\n'
            f'in `{csv_path.name}`. Renderer: `v2b_c/build_case_studies.py` (fade tier‑1 annotations).\n\n'
        )
        f.write(f'Start ≥ `{args.start}`, `--n-per-bucket={args.n_per_bucket}`, seed `{args.seed}`.\n\n')
        f.write(f'**Winners folder:** {len(win_rows)} charts (Σ sampled net ${sw:+,.0f}).\n\n')
        f.write('| Date | Symbol | OR pts | Pattern | Day Σ Net_$ | PNG |\n|---|---|---:|---|---:|---|\n')
        for r in sorted(win_rows, key=lambda x: x['date']):
            du = r['date']
            f.write(
                f"| {du} | {r['symbol']} | {r['rv']:.1f} | {r['pattern']} | ${r['day_net']:+,.0f} | [winners/{du}.png](winners/{du}.png) |\n"
            )
        f.write(f'\n**Losers folder:** {len(lose_rows)} charts (Σ sampled net ${sl:+,.0f}).\n\n')
        f.write('| Date | Symbol | OR pts | Pattern | Day Σ Net_$ | PNG |\n|---|---|---:|---|---:|---|\n')
        for r in sorted(lose_rows, key=lambda x: x['date']):
            du = r['date']
            f.write(
                f"| {du} | {r['symbol']} | {r['rv']:.1f} | {r['pattern']} | ${r['day_net']:+,.0f} | [losers/{du}.png](losers/{du}.png) |\n"
            )

    print(f'Wrote {idx}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
