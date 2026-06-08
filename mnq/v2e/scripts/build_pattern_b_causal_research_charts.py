#!/usr/bin/env python3
"""
Build **Pattern B** research charts — causal London box path (see ``pattern_b_london_causal.py``).

Charts use **5 m OHLC** for **RTH NY only** (**09:30–16:00** ET). **London high / low** are horizontal
lines from the **[02:00, 09:30)** box (no London-session candles).

Writes PNGs under ``case_studies/pattern_b_causal_research/charts/`` plus ``INDEX.md`` and optional CSV.

Clears prior PNGs / INDEX in the charts folder unless ``--no-clean``.

Example::

  cd potions/mnq/v2e/scripts
  python3 build_pattern_b_causal_research_charts.py --max-charts 48
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from datetime import date
from datetime import datetime
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

from backtest_london_sweep_breaker import london_low_high  # noqa: E402

from pattern_b_london_causal import (  # noqa: E402
    PatternBResult,
    batch_equivalent_high_double_path,
    detect_pattern_b_causal_session,
    iter_rth_high_low,
)

from rules.v2e_causal import NY as RULES_NY  # noqa: E402
from rules.v2e_causal import RTH_HI as RULES_RTH_HI  # noqa: E402
from rules.v2e_causal import RTH_LO as RULES_RTH_LO  # noqa: E402

from v2e_causal_live_sim import load_by_day, scan_date_range  # noqa: E402

_EPS = 1e-12


def clean_charts_parent(case_root: Path, charts_dir: Path) -> None:
    if charts_dir.is_dir():
        for p in sorted(charts_dir.glob('*.png')):
            p.unlink(missing_ok=True)
    idx = case_root / 'INDEX.md'
    idx.unlink(missing_ok=True)
    readme = case_root / 'README.md'
    readme.unlink(missing_ok=True)


def rth_1m_slice(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    """Regular session **[09:30, 16:00)** NY only."""
    return day_1m[
        day_1m.index.map(
            lambda t: t.date() == session_day and RULES_RTH_LO <= t.time() < RULES_RTH_HI
        )
    ].sort_index()


def resample_rth_5m(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    """RTH 1 m → **5 m** bars (``label=left``, anchored at **09:30** NY)."""
    sub = rth_1m_slice(day_1m, session_day)
    if sub.empty:
        return sub
    anchor = RULES_NY.localize(datetime.combine(session_day, RULES_RTH_LO))
    return (
        sub.resample('5min', label='left', closed='left', origin=anchor)
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
        )
        .dropna(subset=['open'])
    )


def plot_5m_ohlc(ax, sub: pd.DataFrame, x_num: np.ndarray) -> None:
    n = len(sub)
    if n == 0:
        return
    if n >= 2:
        dx = float(np.median(np.diff(x_num)))
        width = max(dx * 0.72, 5 / (24 * 60) * 0.55)
    else:
        width = 5 / (24 * 60) * 0.55

    for i in range(n):
        xi = float(x_num[i])
        row = sub.iloc[i]
        o = float(row['open'])
        h = float(row['high'])
        lo = float(row['low'])
        c = float(row['close'])
        up = c >= o
        col = '#26A69A' if up else '#EF5350'
        ax.vlines(xi, lo, h, color=col, linewidth=0.85, zorder=3)
        body_lo = min(o, c)
        body_hi = max(o, c)
        bh = max(body_hi - body_lo, max(h - lo, 0.02) * 0.05 + 0.03)
        ax.add_patch(
            mpatches.Rectangle(
                (xi - width / 2, body_lo),
                width,
                bh,
                facecolor=col,
                edgecolor=col,
                linewidth=0.55,
                zorder=4,
            )
        )


def draw_pattern_b_chart(day_1m: pd.DataFrame, hit: PatternBResult, out_path: Path) -> None:
    session_day = hit.session_day
    sub = resample_rth_5m(day_1m, session_day)
    if sub.empty:
        return

    sub = sub.copy()
    sub.index = pd.to_datetime(sub.index)
    x = mdates.date2num(sub.index.to_numpy())

    fig, ax = plt.subplots(figsize=(14, 7), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    plot_5m_ohlc(ax, sub, x)

    L, H = hit.london_low, hit.london_high
    ax.axhline(L, color='#64B5F6', linestyle='-', linewidth=1.35, alpha=0.98, zorder=2, label='London low')
    ax.axhline(H, color='#FFB74D', linestyle='-', linewidth=1.35, alpha=0.98, zorder=2, label='London high')

    def vmark(ts: pd.Timestamp, color: str, lab: str) -> None:
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

    vmark(hit.ts_first_high, '#FFD54F', '1st London H (clean)')
    vmark(hit.ts_inside, '#CE93D8', 'Inside range bar')
    vmark(hit.ts_second_high, '#76FF03', '2nd London H')

    ax.set_title(
        f'Pattern B (causal) · {session_day} · 5m RTH NY · clean high-first → inside → 2nd high · no London L sweep',
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


def stratified_sample_dates(hits: list[PatternBResult], n: int, rng: np.random.Generator) -> list[PatternBResult]:
    if not hits or n <= 0:
        return []
    work = sorted(hits, key=lambda h: h.session_day)
    by_m: dict[tuple[int, int], list[PatternBResult]] = defaultdict(list)
    for h in work:
        d = h.session_day
        by_m[(d.year, d.month)].append(h)
    months = sorted(by_m.keys())
    picked: list[PatternBResult] = []
    picked_set = set()
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
        rest = [h for h in work if h.session_day not in picked_set]
        rng.shuffle(rest)
        picked.extend(rest[:remain])
    return picked[:n]


def scan_sessions(
    by_day: dict[date, pd.DataFrame],
) -> tuple[list[PatternBResult], int, int]:
    hits: list[PatternBResult] = []
    eligible = 0
    mismatches = 0

    for session_day in sorted(by_day.keys()):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day]
        if day_b.empty:
            continue
        L, H = london_low_high(day_b, session_day)
        if math.isnan(L) or math.isnan(H) or H <= L + _EPS:
            continue

        rth_list = list(iter_rth_high_low(day_b, session_day, rth_lo=RULES_RTH_LO, rth_hi=RULES_RTH_HI))
        if len(rth_list) < 4:
            continue
        eligible += 1

        bars_only = [(hi, lo) for _ts, hi, lo in rth_list]
        batch_hit = batch_equivalent_high_double_path(bars_only, L, H)

        causal_res = detect_pattern_b_causal_session(
            ((ts, hi, lo) for ts, hi, lo in rth_list),
            session_day,
            L,
            H,
        )

        if batch_hit != (causal_res is not None):
            mismatches += 1

        if causal_res is not None:
            hits.append(causal_res)

    return hits, eligible, mismatches


def write_readme_and_index(
    charts_dir: Path,
    rows: list[tuple[str, str]],
    *,
    n_total: int,
    eligible: int,
    mismatches: int,
) -> None:
    readme = CASE_STUDY_ROOT / 'README.md'
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        '\n'.join(
            [
                '# Pattern B — causal London path (research)',
                '',
                '**Pattern:** After RTH open, **clean high-first** touch of London high (no same-bar low sweep), '
                '**never** a London-low sweep through the **second** reclaim of London high, '
                'one **inside-range** bar (full bar in `[London low, London high]`), then **second** London-high touch.',
                '',
                'Identification is **causal**: one ``step()`` per **closed** 1 m bar — see ``../scripts/pattern_b_london_causal.py``.',
                '',
                '**Charts:** **5 m** OHLC for **RTH NY** (**09:30–16:00** ET only); **London high/low** as horizontal lines '
                '(levels from **[02:00, 09:30)**).',
                '',
                f'Charts are a stratified sample. Session hits in scan: **{n_total}** / **{eligible}** eligible weekdays.',
                f'Batch vs causal parity mismatches: **{mismatches}** (expect 0).',
                '',
                'Generate:',
                '',
                '```bash',
                'cd potions/mnq/v2e/scripts',
                'python3 build_pattern_b_causal_research_charts.py',
                '```',
                '',
            ]
        ),
        encoding='utf-8',
    )

    idx_lines = [
        '# Pattern B causal research charts',
        '',
        '| PNG | Session |',
        '|-----|---------|',
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
    ap.add_argument('--max-charts', type=int, default=48)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--export-csv', type=Path, default=CASE_STUDY_ROOT / 'pattern_b_sessions.csv')
    ap.add_argument('--no-export-csv', action='store_true')
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
    hits, eligible, mismatches = scan_sessions(by_day)

    print(f'Eligible weekdays: {eligible}')
    print(f'Pattern B hits (causal): {len(hits)}')
    print(f'Batch↔causal mismatches: {mismatches}')
    if mismatches:
        print('WARNING: parity check failed — review detector logic.', file=sys.stderr)

    if not args.no_export_csv and args.export_csv:
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    'session_day': h.session_day.isoformat(),
                    'london_low': h.london_low,
                    'london_high': h.london_high,
                    'ts_first_high': pd.Timestamp(h.ts_first_high).isoformat(),
                    'ts_inside': pd.Timestamp(h.ts_inside).isoformat(),
                    'ts_second_high': pd.Timestamp(h.ts_second_high).isoformat(),
                }
                for h in sorted(hits, key=lambda x: x.session_day)
            ]
        ).to_csv(args.export_csv, index=False)
        print(f'Wrote {args.export_csv}')

    if not args.no_clean:
        clean_charts_parent(CASE_STUDY_ROOT, args.chart_dir)

    CASE_STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    args.chart_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    sample = stratified_sample_dates(hits, min(args.max_charts, len(hits)), rng)

    index_rows: list[tuple[str, str]] = []
    for i, hit in enumerate(sample, 1):
        fname = f'pattern_b_{i:03d}_{hit.session_day.isoformat()}.png'
        out_path = args.chart_dir / fname
        draw_pattern_b_chart(by_day[hit.session_day], hit, out_path)
        index_rows.append((fname, hit.session_day.isoformat()))
        print(fname)

    write_readme_and_index(args.chart_dir, index_rows, n_total=len(hits), eligible=eligible, mismatches=mismatches)
    print(f'\nWrote {len(sample)} charts under {args.chart_dir}')
    print(f'Wrote {CASE_STUDY_ROOT / "INDEX.md"} and README.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
