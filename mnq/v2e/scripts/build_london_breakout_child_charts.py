#!/usr/bin/env python3
"""
Render **~20** sample PNG charts for ``london_breakout_child`` (5 m RTH candles + London box,
breakout span, child spans, limit lines, fill markers, SL/TP).

Writes to ``case_studies/london_breakout_child_charts/``.

Example::

  cd potions/mnq/v2e/scripts
  python3 build_london_breakout_child_charts.py --max-charts 20
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
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

V2E_SCRIPTS = Path(__file__).resolve().parent
V2E_ROOT = V2E_SCRIPTS.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
CASE_STUDY_ROOT = V2E_ROOT / 'case_studies' / 'london_breakout_child_charts'
DEFAULT_CHART_DIR = CASE_STUDY_ROOT / 'charts'

sys.path[:0] = [str(V2E_SCRIPTS), str(MNQ_ROOT), str(POTIONS_SCRIPTS)]

from build_pattern_b_causal_research_charts import plot_5m_ohlc, resample_rth_5m  # noqa: E402

from london_breakout_child import BreakoutChildOutcome, simulate_session  # noqa: E402

from rules.v2e_causal import NY as RULES_NY  # noqa: E402

from v2e_causal_live_sim import load_by_day, scan_date_range  # noqa: E402


def clean_case_study(case_root: Path, charts_dir: Path) -> None:
    if charts_dir.is_dir():
        for p in sorted(charts_dir.glob('*.png')):
            p.unlink(missing_ok=True)
    for name in ('INDEX.md', 'README.md'):
        p = case_root / name
        p.unlink(missing_ok=True)


def stratified_sample_filled(filled: list[BreakoutChildOutcome], n: int, rng: np.random.Generator) -> list[BreakoutChildOutcome]:
    if not filled or n <= 0:
        return []
    work = sorted(filled, key=lambda o: o.session_day)
    by_m: dict[tuple[int, int], list[BreakoutChildOutcome]] = defaultdict(list)
    for o in work:
        d = o.session_day
        by_m[(d.year, d.month)].append(o)
    months = sorted(by_m.keys())
    picked: list[BreakoutChildOutcome] = []
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


def _num(ts: pd.Timestamp) -> float:
    tsn = pd.Timestamp(ts)
    if tsn.tzinfo is None:
        tsn = tsn.tz_localize(RULES_NY)
    else:
        tsn = tsn.tz_convert(RULES_NY)
    return float(mdates.date2num(tsn.to_pydatetime()))


def draw_chart(day_1m: pd.DataFrame, tr: BreakoutChildOutcome, out_path: Path) -> None:
    if tr.status != 'filled':
        return
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
    ax.axhline(L, color='#90CAF9', linestyle='--', linewidth=1.1, alpha=0.95, label='London low')
    ax.axhline(H, color='#E0E0E0', linestyle='--', linewidth=1.1, alpha=0.95, label='London high')
    ax.axhline(tr.sl_px, color='#FF5252', linestyle='-', linewidth=1.2, alpha=0.95, label='SL')
    ax.axhline(tr.tp_px, color='#76FF03', linestyle='-', linewidth=1.2, alpha=0.95, label='TP')

    for i, px in enumerate(tr.chart_order_limit_px):
        lbl = f'Limit {i + 1} (child open)' if i < 4 else '_nolegend_'
        ax.axhline(px, color='#80DEEA', linestyle=':', linewidth=1.0, alpha=0.85, label=lbl)

    if not pd.isna(tr.ts_breakout_left):
        t0 = pd.Timestamp(tr.ts_breakout_left)
        t1 = t0 + pd.Timedelta(minutes=5)
        ax.axvspan(_num(t0), _num(t1), color='#7E57C2', alpha=0.22, zorder=0, label='Breakout 5m')

    for ci, ch_left in enumerate(tr.chart_child_bar_left):
        c0 = pd.Timestamp(ch_left)
        c1 = c0 + pd.Timedelta(minutes=5)
        lab = 'Child 5m (outside + green/red)' if ci == 0 else '_nolegend_'
        ax.axvspan(_num(c0), _num(c1), color='#00897B', alpha=0.18, zorder=0, label=lab)

    for lim_px, fts in zip(tr.chart_order_limit_px, tr.chart_order_fill_ts):
        if pd.isna(fts):
            continue
        ax.scatter([_num(fts)], [lim_px], color='#69F0AE', s=55, zorder=9, edgecolors='#0D1B2A', linewidths=0.8, label='_nolegend_')

    if not pd.isna(tr.ts_exit):
        ax.axvline(_num(tr.ts_exit), color='#FFB74D', linestyle='-', linewidth=1.35, alpha=0.95, label='Exit')

    fill_proxy = ax.scatter([], [], color='#69F0AE', s=55, edgecolors='#0D1B2A', linewidths=0.8, label='Fill (1m)')
    handles, labels = ax.get_legend_handles_labels()
    handles = [h for h, lab in zip(handles, labels) if lab and not str(lab).startswith('_')]
    labels = [lab for lab in labels if lab and not str(lab).startswith('_')]
    ax.legend(handles + [fill_proxy], labels + ['Fill (1m)'], loc='upper left', fontsize=7, framealpha=0.35, labelcolor='#ECEFF1')

    side_u = str(tr.side or '').upper()
    ax.set_title(
        f'London breakout child · {session_day} · {side_u} · {tr.contracts} MNQ · {tr.result} · net ${tr.net_usd:+.2f}',
        color='#ECEFF1',
        fontsize=11,
    )
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.grid(True, linestyle=':', alpha=0.22, color='#546E7A')
    ax.tick_params(colors='#B0BEC5')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=RULES_NY))
    plt.xticks(rotation=28)
    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=125, facecolor='#0D1B2A')
    plt.close(fig)


def write_docs(rows: list[tuple[str, str]], *, n_sample: int, max_children: int) -> None:
    CASE_STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    (CASE_STUDY_ROOT / 'README.md').write_text(
        '\n'.join(
            [
                '# London breakout + child limits — chart sample',
                '',
                'Visual check for ``../scripts/london_breakout_child.py``: first **5 m close** outside London, '
                'then **green** (long) / **red** (short) **child** 5 m bars fully outside the box; **limits at child opens** '
                '(live after child close); '
                f'up to **{max_children}** scale-ins; SL/TP per script.',
                '',
                f'Month-stratified sample: **{n_sample}** sessions with ≥1 fill.',
                '',
                '```bash',
                'cd potions/mnq/v2e/scripts',
                'python3 build_london_breakout_child_charts.py --max-charts 20',
                '```',
                '',
            ]
        ),
        encoding='utf-8',
    )
    lines = [
        '# London breakout child charts',
        '',
        '| PNG | Session · side · note |',
        '|-----|----------------------|',
    ]
    for fname, note in sorted(rows):
        lines.append(f'| [`{fname}`](charts/{fname}) | {note} |')
    lines.append('')
    (CASE_STUDY_ROOT / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--max-charts', type=int, default=20)
    ap.add_argument('--max-children', type=int, default=5)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--no-clean', action='store_true')
    ap.add_argument('--chart-dir', type=Path, default=DEFAULT_CHART_DIR)
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m CSV {args.m1}', file=sys.stderr)
        return 1

    if args.start and args.end:
        date_min = pd.Timestamp(args.start).date()
        date_max = pd.Timestamp(args.end).date()
    else:
        date_min, date_max = scan_date_range(args.m1, args.start, args.end)

    by_day = load_by_day(args.m1, date_min, date_max)

    filled: list[BreakoutChildOutcome] = []
    for session_day in sorted(by_day.keys()):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day]
        if day_b.empty:
            continue
        o = simulate_session(day_b, session_day, max_children=args.max_children)
        if o.status == 'filled':
            filled.append(o)

    rng = np.random.default_rng(args.seed)
    n_take = min(args.max_charts, len(filled))
    sample_refs = stratified_sample_filled(filled, n_take, rng)

    if not args.no_clean:
        clean_case_study(CASE_STUDY_ROOT, args.chart_dir)

    CASE_STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    args.chart_dir.mkdir(parents=True, exist_ok=True)

    index_rows: list[tuple[str, str]] = []
    for i, ref in enumerate(sample_refs, 1):
        day_b = by_day[ref.session_day]
        tr = simulate_session(day_b, ref.session_day, max_children=args.max_children, record_chart_meta=True)
        if tr.status != 'filled':
            continue
        fname = f'lbc_{i:02d}_{tr.session_day.isoformat()}_{str(tr.side).capitalize()}_{tr.result.replace(" ", "_")}.png'
        out_path = args.chart_dir / fname
        draw_chart(day_b, tr, out_path)
        note = f'{tr.session_day.isoformat()} · {tr.side} · {tr.contracts} ct · ${tr.net_usd:+.2f}'
        index_rows.append((fname, note))
        print(fname)

    write_docs(index_rows, n_sample=len(index_rows), max_children=args.max_children)
    print(f'\nWrote {len(index_rows)} charts under {args.chart_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
