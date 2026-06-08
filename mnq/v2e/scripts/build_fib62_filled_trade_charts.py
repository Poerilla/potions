#!/usr/bin/env python3
"""
Build **5 m RTH** charts for a stratified sample of **filled** Fib-62 limit-long trades
(see ``study_rth_london_high_fib62_limit_long.py``).

Clears ``pattern_b_causal_research/charts/*.png`` plus case-study ``INDEX.md`` / ``README.md`` /
``pattern_b_sessions.csv`` unless ``--no-clean``.

Example::

  cd potions/mnq/v2e/scripts
  python3 build_fib62_filled_trade_charts.py --max-charts 50
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

V2E_SCRIPTS = Path(__file__).resolve().parent
V2E_ROOT = V2E_SCRIPTS.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
CASE_STUDY_ROOT = V2E_ROOT / 'case_studies' / 'pattern_b_causal_research'
DEFAULT_CHART_DIR = CASE_STUDY_ROOT / 'charts'

sys.path[:0] = [str(V2E_SCRIPTS), str(MNQ_ROOT), str(POTIONS_SCRIPTS)]

from build_pattern_b_causal_research_charts import plot_5m_ohlc, resample_rth_5m  # noqa: E402

from rules.v2e_causal import NY as RULES_NY  # noqa: E402

from study_rth_london_high_fib62_limit_long import (  # noqa: E402
    PHI_INV,
    SessionOutcome,
    simulate_session,
)

from v2e_causal_live_sim import load_by_day, scan_date_range  # noqa: E402


def clean_case_study(case_root: Path, charts_dir: Path, *, remove_csv: bool) -> None:
    if charts_dir.is_dir():
        for p in sorted(charts_dir.glob('*.png')):
            p.unlink(missing_ok=True)
    for name in ('INDEX.md', 'README.md'):
        p = case_root / name
        p.unlink(missing_ok=True)
    if remove_csv:
        (case_root / 'pattern_b_sessions.csv').unlink(missing_ok=True)


def stratified_sample_filled(filled: list[SessionOutcome], n: int, rng: np.random.Generator) -> list[SessionOutcome]:
    if not filled or n <= 0:
        return []
    work = sorted(filled, key=lambda o: o.session_day)
    by_m: dict[tuple[int, int], list[SessionOutcome]] = defaultdict(list)
    for o in work:
        d = o.session_day
        by_m[(d.year, d.month)].append(o)
    months = sorted(by_m.keys())
    picked: list[SessionOutcome] = []
    picked_set: set[date] = set()
    guard = 0
    while len(picked) < n and guard < n * 80:
        guard += 1
        progressed = False
        for ym in months:
            if len(picked) >= n:
                break
            pool = [x for x in by_m[ym] if x.session_day not in picked_set]
            if not pool:
                continue
            choice = pool[int(rng.integers(0, len(pool)))]
            picked.append(choice)
            picked_set.add(choice.session_day)
            progressed = True
        if not progressed:
            break
    remain = n - len(picked)
    if remain > 0:
        rest = [o for o in work if o.session_day not in picked_set]
        rng.shuffle(rest)
        picked.extend(rest[:remain])
    return picked[:n]


def _vmark(ax, ts: pd.Timestamp, color: str, lab: str) -> None:
    if pd.isna(ts):
        return
    tsn = pd.Timestamp(ts)
    if tsn.tzinfo is None:
        tsn = tsn.tz_localize(RULES_NY)
    else:
        tsn = tsn.tz_convert(RULES_NY)
    ax.axvline(
        mdates.date2num(tsn.to_pydatetime()),
        color=color,
        linestyle='-',
        linewidth=1.35,
        alpha=0.95,
        label=lab,
    )


def draw_fib62_chart(day_1m: pd.DataFrame, tr: SessionOutcome, out_path: Path, *, fib_ratio: float) -> None:
    session_day = tr.session_day
    sub = resample_rth_5m(day_1m, session_day)
    if sub.empty:
        return

    sub = sub.copy()
    sub.index = pd.to_datetime(sub.index)
    x = mdates.date2num(sub.index.to_numpy())

    fig, ax = plt.subplots(figsize=(14, 7), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    plot_5m_ohlc(ax, sub, x)

    L, H = tr.london_low, tr.london_high
    ax.axhline(L, color='#64B5F6', linestyle='-', linewidth=1.35, alpha=0.98, zorder=2, label='London low (SL)')
    ax.axhline(H, color='#FFB74D', linestyle='-', linewidth=1.35, alpha=0.98, zorder=2, label='London high (TP)')
    ax.axhline(
        tr.entry_px,
        color='#80DEEA',
        linestyle='--',
        linewidth=1.15,
        alpha=0.95,
        zorder=2,
        label=f'Fib limit ({fib_ratio:.4f} from H)',
    )

    _vmark(ax, tr.ts_first_rth_high, '#FFD54F', '1st RTH London high')
    _vmark(ax, tr.ts_fill, '#69F0AE', 'Limit fill')
    _vmark(ax, tr.ts_exit, '#FF5252', 'Exit')

    net_s = f'{tr.net_usd:+.2f}'
    ax.set_title(
        f'Fib-62 limit long (causal) · {session_day} · 5m RTH NY · {tr.result} · net ${net_s}',
        color='#ECEFF1',
        fontsize=11,
    )
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.grid(True, linestyle=':', alpha=0.22, color='#546E7A')
    ax.tick_params(colors='#B0BEC5')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=RULES_NY))
    plt.xticks(rotation=28)
    ax.legend(loc='upper left', fontsize=7, framealpha=0.35, labelcolor='#ECEFF1')
    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=125, facecolor='#0D1B2A')
    plt.close(fig)


def write_readme_and_index(
    *,
    charts_dir: Path,
    rows: list[tuple[str, str]],
    n_filled_total: int,
    n_sample: int,
    fib_ratio: float,
) -> None:
    readme = CASE_STUDY_ROOT / 'README.md'
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        '\n'.join(
            [
                '# Fib-62 London-high pullback — filled trades (charts)',
                '',
                '**Setup (causal 1 m):** First **RTH** touch of **London high**, limit buy at **Fib retracement** '
                'from **H toward L** (default φ⁻¹≈0.618), **no London low** before fill; **SL** = London low, '
                '**TP** = London high or **EOD** exit. See ``../scripts/study_rth_london_high_fib62_limit_long.py``.',
                '',
                f'**Charts:** **5 m** OHLC **RTH NY** only (**09:30–16:00** ET); London high/low + Fib limit as '
                f'horizontal lines; markers for first RTH high touch, fill, exit.',
                '',
                f'Stratified sample: **{n_sample}** sessions shown from **{n_filled_total}** filled trades '
                f'(fib ratio **{fib_ratio:.6f}**).',
                '',
                'Generate:',
                '',
                '```bash',
                'cd potions/mnq/v2e/scripts',
                'python3 build_fib62_filled_trade_charts.py --max-charts 50',
                '```',
                '',
            ]
        ),
        encoding='utf-8',
    )

    idx_lines = [
        '# Fib-62 filled trade charts (5m RTH)',
        '',
        '| PNG | Session · result · note |',
        '|-----|-------------------------|',
    ]
    for fname, note in sorted(rows):
        idx_lines.append(f'| [`{fname}`](charts/{fname}) | {note} |')
    idx_lines.append('')
    (CASE_STUDY_ROOT / 'INDEX.md').write_text('\n'.join(idx_lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--max-charts', type=int, default=50)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--fib', type=float, default=PHI_INV)
    ap.add_argument('--no-clean', action='store_true')
    ap.add_argument('--keep-pattern-b-csv', action='store_true', help='Do not delete pattern_b_sessions.csv')
    ap.add_argument('--chart-dir', type=Path, default=DEFAULT_CHART_DIR)
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m CSV {args.m1}', file=sys.stderr)
        return 1

    fib_ratio = float(args.fib)
    if args.start and args.end:
        date_min = pd.Timestamp(args.start).date()
        date_max = pd.Timestamp(args.end).date()
    else:
        date_min, date_max = scan_date_range(args.m1, args.start, args.end)

    by_day = load_by_day(args.m1, date_min, date_max)

    filled: list[SessionOutcome] = []
    for session_day in sorted(by_day.keys()):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day]
        if day_b.empty:
            continue
        o = simulate_session(day_b, session_day, fib_ratio=fib_ratio)
        if o.status == 'filled':
            filled.append(o)

    print(f'Filled trades in range: {len(filled)}')

    if not args.no_clean:
        clean_case_study(CASE_STUDY_ROOT, args.chart_dir, remove_csv=not args.keep_pattern_b_csv)

    CASE_STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    args.chart_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    n_take = min(args.max_charts, len(filled))
    sample = stratified_sample_filled(filled, n_take, rng)

    index_rows: list[tuple[str, str]] = []
    for i, tr in enumerate(sample, 1):
        fname = f'fib62_{i:03d}_{tr.session_day.isoformat()}_{tr.result.replace(" ", "_")}.png'
        out_path = args.chart_dir / fname
        draw_fib62_chart(by_day[tr.session_day], tr, out_path, fib_ratio=fib_ratio)
        note = f'{tr.session_day.isoformat()} · {tr.result} · net ${tr.net_usd:+.2f}'
        index_rows.append((fname, note))
        print(fname)

    write_readme_and_index(
        charts_dir=args.chart_dir,
        rows=index_rows,
        n_filled_total=len(filled),
        n_sample=len(sample),
        fib_ratio=fib_ratio,
    )
    print(f'\nWrote {len(sample)} charts under {args.chart_dir}')
    print(f'Wrote {CASE_STUDY_ROOT / "INDEX.md"} and README.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
