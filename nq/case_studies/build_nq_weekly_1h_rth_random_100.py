#!/usr/bin/env python3
"""
Random sample of NQ weekly 1h charts — prior-week levels + RTH session shading.

Same candle/level style as the WO gap study, but:
- No ATR background bands
- NY RTH (09:30–16:00 ET, Mon–Fri) shaded on the chart background
- No trade overlays

Usage::

  python3 nq/case_studies/build_nq_weekly_1h_rth_random_100.py
  python3 nq/case_studies/build_nq_weekly_1h_rth_random_100.py --sample-size 100 --seed 42
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import datetime, time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_nq_weekly_1h_level_study import (  # noqa: E402
    BG,
    NY,
    build_daily_atr,
    build_weekly_table,
    concat_1m,
    load_1m_by_ny_date,
    plot_candles,
    resample_1h,
    style_axes,
    week_context,
    week_hourly_slice,
)

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
RTH_FILL = '#243B55'
ETH_FILL = '#111D2C'


def draw_levels_no_atr(
    ax,
    x0: float,
    x1: float,
    ctx: dict[str, float],
    *,
    y_clip: tuple[float, float] | None = None,
) -> None:
    """Level lines only (no WO±ATR shading)."""
    import build_nq_weekly_1h_level_study as lvl

    specs = [
        ('PWH', '#CE93D8', '-', 1.1),
        ('PWL', '#CE93D8', '-', 1.1),
        ('PWC', '#FFC107', '-.', 1.15),
        ('PWO', '#26C6DA', '-', 1.15),
        ('PW_MID', '#9FB3C8', '--', 1.0),
    ]
    for key, color, ls, lw in specs:
        lvl.hline_segment(ax, x0, x1, ctx[key], color=color, linestyle=ls, lw=lw, label=key)
    lvl.hline_segment(ax, x0, x1, ctx['WO'], color='#76FF03', linestyle='-', lw=1.0, label='WO')


def shade_rth_eth(ax, bars: pd.DataFrame, y_lo: float, y_hi: float) -> None:
    """Shade RTH 09:30–16:00 NY on Mon–Fri; slightly different tone for ETH."""
    if bars.empty:
        return
    t_start = bars.index[0] - pd.Timedelta(hours=6)
    t_end = bars.index[-1] + pd.Timedelta(hours=6)
    ax.axvspan(
        mdates.date2num(t_start),
        mdates.date2num(t_end),
        ymin=0,
        ymax=1,
        facecolor=ETH_FILL,
        alpha=0.55,
        zorder=0,
    )
    days = pd.date_range(bars.index[0].normalize(), bars.index[-1].normalize(), freq='D', tz=NY)
    for day in days:
        if day.weekday() >= 5:
            continue
        rth0 = NY.localize(datetime.combine(day.date(), RTH_OPEN))
        rth1 = NY.localize(datetime.combine(day.date(), RTH_CLOSE))
        if rth1 <= t_start or rth0 >= t_end:
            continue
        ax.axvspan(
            mdates.date2num(max(rth0, t_start)),
            mdates.date2num(min(rth1, t_end)),
            ymin=0,
            ymax=1,
            facecolor=RTH_FILL,
            alpha=0.72,
            zorder=1,
        )


def plot_week_rth_chart(
    out_path: Path,
    bars: pd.DataFrame,
    ctx: dict[str, float],
    week_start: pd.Timestamp,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 8), facecolor=BG)
    pad = max((bars['high'].max() - bars['low'].min()) * 0.08, 20.0)
    y_lo = float(bars['low'].min()) - pad
    y_hi = float(bars['high'].max()) + pad
    shade_rth_eth(ax, bars, y_lo, y_hi)

    x0 = mdates.date2num(bars.index[0])
    x1 = mdates.date2num(bars.index[-1])
    draw_levels_no_atr(ax, x0, x1, ctx, y_clip=(y_lo, y_hi))
    plot_candles(ax, bars, width_days=(60 / (24 * 60)) * 0.68)

    fri = (week_start + pd.Timedelta(days=5)).date()
    title = (
        f"NQ 1h · {week_start.date()} – {fri} · "
        f"PWH/PWL/PWC/PWO + WO · RTH 09:30–16:00 shaded"
    )
    style_axes(ax, title)
    ax.get_legend().remove()
    handles = [
        mpatches.Patch(facecolor=RTH_FILL, alpha=0.72, label='RTH 09:30–16:00 NY'),
        mpatches.Patch(facecolor=ETH_FILL, alpha=0.55, label='ETH / overnight'),
        plt.Line2D([0], [0], color='#76FF03', lw=1.0, label='WO'),
        plt.Line2D([0], [0], color='#CE93D8', lw=1.1, label='PWH/PWL'),
        plt.Line2D([0], [0], color='#FFC107', lw=1.1, linestyle='-.', label='PWC'),
        plt.Line2D([0], [0], color='#26C6DA', lw=1.1, label='PWO'),
    ]
    ax.legend(
        handles=handles,
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=7,
        ncol=2,
    )
    ax.set_ylabel('NQ', color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.set_xlim(bars.index[0] - pd.Timedelta(hours=2), bars.index[-1] + pd.Timedelta(hours=2))
    ax.set_ylim(y_lo, y_hi)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)


def sample_weeks_stratified(
    weekly: pd.DataFrame,
    valid: list,
    n: int,
    seed: int,
) -> list:
    """Pick ``n`` weeks spread across calendar years."""
    rng = random.Random(seed)
    by_year: dict[int, list] = {}
    for w in valid:
        y = int(weekly.loc[w, 'week_start'].year)
        by_year.setdefault(y, []).append(w)

    years = sorted(by_year.keys())
    if not years:
        return []

    per = max(1, n // len(years))
    picked: list = []
    for y in years:
        pool = by_year[y][:]
        rng.shuffle(pool)
        picked.extend(pool[:per])

    rest = [w for w in valid if w not in picked]
    rng.shuffle(rest)
    for w in rest:
        if len(picked) >= n:
            break
        picked.append(w)

    picked = picked[:n]
    picked.sort(key=lambda w: weekly.loc[w, 'week_start'])
    return picked


def build(
    *,
    output_root: Path,
    sample_size: int,
    seed: int,
    start: str,
    force: bool,
) -> str:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    chart_dir = output_root / 'charts'
    chart_dir.mkdir(parents=True, exist_ok=True)

    dbn = HERE.parent / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    print(f'Loading NQ 1m ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    one_min = one_min[one_min.index >= pd.Timestamp(start, tz=NY)]
    hourly = resample_1h(one_min)
    daily_atr = build_daily_atr(hourly)
    weekly = build_weekly_table(hourly, daily_atr)

    valid = [w for w in weekly.index if week_context(weekly, w) is not None]
    picked = sample_weeks_stratified(weekly, valid, sample_size, seed)
    print(f'Sampled {len(picked)} weeks across {len({weekly.loc[w, "week_start"].year for w in picked})} years (seed={seed})', flush=True)

    rows: list[dict] = []
    first_chart = ''
    for idx, w in enumerate(picked, start=1):
        ctx = week_context(weekly, w)
        ws = weekly.loc[w, 'week_start']
        bars = week_hourly_slice(hourly, ws)
        if len(bars) < 12:
            continue
        rel = f'charts/{idx:03d}_{ws.date().isoformat()}.png'
        if not first_chart:
            first_chart = rel
        plot_week_rth_chart(output_root / rel, bars, ctx, ws)
        rows.append(
            {
                'idx': idx,
                'week_start': ws.date().isoformat(),
                'year': ws.year,
                'chart': rel,
                'PWH': ctx['PWH'],
                'PWL': ctx['PWL'],
                'PWC': ctx['PWC'],
                'WO': ctx['WO'],
                'bars': len(bars),
            }
        )
        if idx % 25 == 0:
            print(f'  … {idx} charts', flush=True)

    pd.DataFrame(rows).to_csv(output_root / 'manifest.csv', index=False)
    year_counts = pd.Series([r['year'] for r in rows]).value_counts().sort_index()
    lines = [
        '# NQ weekly 1h — RTH session shading (random sample)',
        '',
        f'**{len(rows)}** random weeks · **1-hour** candles · Sun–Fri (no trades).',
        '',
        '### Levels',
        '- **PWH / PWL / PWC / PWO** — prior completed week',
        '- **PW 50%** — dashed midpoint',
        '- **WO** — current week open (green)',
        '',
        '### Background',
        '- **Darker blue band** — NY **RTH 09:30–16:00** (Mon–Fri)',
        '- **Lighter band** — ETH / overnight',
        '- No ATR shading',
        '',
        f'Sample seed: `{seed}` · earliest data: `{start}`',
        '',
        '## By year',
        '',
    ]
    for y, c in year_counts.items():
        lines.append(f'- **{y}**: {c} charts')
    lines.extend(['', '| # | Week | Year | Chart |', '|---:|---|---:|---|'])
    for r in rows:
        lines.append(f'| {r["idx"]} | {r["week_start"]} | {r["year"]} | [{r["chart"]}]({r["chart"]}) |')
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {output_root / "INDEX.md"}', flush=True)
    return first_chart


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_weekly_1h_rth_random_100')
    ap.add_argument('--sample-size', type=int, default=100)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--start', type=str, default='2011-01-01')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    first = build(
        output_root=args.output_root,
        sample_size=args.sample_size,
        seed=args.seed,
        start=args.start,
        force=args.force,
    )
    if first:
        print(f'First chart: {args.output_root / first}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
