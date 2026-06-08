#!/usr/bin/env python3
"""
NQ weekly 1h charts: engulfing candles after price has extended >1 ATR from WO.

Same chart layout as ``nq_weekly_wo_gap_reversal_sample`` (prior-week levels, WO,
WO±ATR bands, causal HA pin outlines). Engulfing bars highlighted orange (bull) /
red (bear).

Usage::

  python3 nq/case_studies/build_nq_weekly_wo_atr_engulfing_sample.py --count 100 --force
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from build_nq_weekly_1h_level_study import (  # noqa: E402
    BG,
    NY,
    build_daily_atr,
    build_weekly_table,
    concat_1m,
    draw_levels,
    load_1m_by_ny_date,
    plot_candles,
    resample_1h,
    style_axes,
    week_context,
    week_hourly_slice,
)
from build_nq_wo_gap_reversal_sample import (  # noqa: E402
    compute_ha_candles,
    ha_pins_for_week,
)


@dataclass
class EngulfEvent:
    bar_idx: int
    kind: Literal['bullish_engulf', 'bearish_engulf']
    extension: str  # 'below_wo_minus_atr' | 'above_wo_plus_atr'


def bullish_engulfing(curr: pd.Series, prev: pd.Series) -> bool:
    o0, c0 = float(prev['open']), float(prev['close'])
    o1, c1 = float(curr['open']), float(curr['close'])
    if not (c0 < o0 and c1 > o1):
        return False
    if o1 > c0 or c1 < o0:
        return False
    return o1 <= o0 and c1 >= c0


def bearish_engulfing(curr: pd.Series, prev: pd.Series) -> bool:
    o0, c0 = float(prev['open']), float(prev['close'])
    o1, c1 = float(curr['open']), float(curr['close'])
    if not (c0 > o0 and c1 < o1):
        return False
    if o1 < c0 or c1 > o0:
        return False
    return o1 >= o0 and c1 <= c0


def find_engulfings_after_atr_extension(
    bars: pd.DataFrame,
    wo: float,
    atr: float,
) -> list[EngulfEvent]:
    if atr <= 0 or not pd.notna(atr):
        return []
    wo_plus = wo + atr
    wo_minus = wo - atr
    seen_above = False
    seen_below = False
    out: list[EngulfEvent] = []
    for i in range(1, len(bars)):
        prev = bars.iloc[i - 1]
        curr = bars.iloc[i]
        if bullish_engulfing(curr, prev) and seen_below:
            out.append(EngulfEvent(i, 'bullish_engulf', 'below_wo_minus_atr'))
        if bearish_engulfing(curr, prev) and seen_above:
            out.append(EngulfEvent(i, 'bearish_engulf', 'above_wo_plus_atr'))
        h, l = float(curr['high']), float(curr['low'])
        if h >= wo_plus:
            seen_above = True
        if l <= wo_minus:
            seen_below = True
    return out


def stratified_sample(weeks: list[dict], count: int, seed: int) -> list[dict]:
    if len(weeks) <= count:
        return weeks
    by_year: dict[int, list[dict]] = defaultdict(list)
    for w in weeks:
        by_year[int(w['year'])].append(w)
    years = sorted(by_year)
    rng = random.Random(seed)
    picked: list[dict] = []
    remaining = count
    for yi, year in enumerate(years):
        pool = by_year[year]
        if yi == len(years) - 1:
            n = remaining
        else:
            n = max(1, round(count * len(pool) / len(weeks)))
            n = min(n, remaining, len(pool))
        rng.shuffle(pool)
        picked.extend(pool[:n])
        remaining -= n
    if len(picked) < count:
        rest = [w for w in weeks if w not in picked]
        rng.shuffle(rest)
        picked.extend(rest[: count - len(picked)])
    elif len(picked) > count:
        rng.shuffle(picked)
        picked = picked[:count]
    picked.sort(key=lambda w: w['week_start'])
    return picked


def plot_week_engulf_chart(
    out_path: Path,
    bars: pd.DataFrame,
    ctx: dict[str, float],
    week_key: str,
    engulfs: list[EngulfEvent],
    ha_pins: list[tuple[int, str]] | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 8), facecolor=BG)
    x0 = mdates.date2num(bars.index[0])
    x1 = mdates.date2num(bars.index[-1])
    pad = max((bars['high'].max() - bars['low'].min()) * 0.08, 20.0)
    y_clip = (float(bars['low'].min()) - pad, float(bars['high'].max()) + pad)
    draw_levels(ax, x0, x1, ctx, y_clip=y_clip)
    plot_candles(ax, bars, width_days=(60 / (24 * 60)) * 0.68)

    width_days = (60 / (24 * 60)) * 0.68
    for i, kind in ha_pins or []:
        row = bars.iloc[i]
        x = mdates.date2num(bars.index[i])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width_days * 0.55, float(row['low']) - 2),
                width_days * 1.1,
                float(row['high']) - float(row['low']) + 4,
                fill=False,
                edgecolor='black',
                linewidth=2.8,
                zorder=8,
            )
        )
        tag = 'HA↑pin' if kind == 'bullish_ha_pin' else 'HA↓pin'
        ax.annotate(
            tag,
            xy=(x, float(row['high']) + 3),
            fontsize=6,
            color='#ECEFF1',
            ha='center',
            zorder=9,
        )

    for ev in engulfs:
        row = bars.iloc[ev.bar_idx]
        x = mdates.date2num(bars.index[ev.bar_idx])
        color = '#FF9800' if ev.kind == 'bullish_engulf' else '#FF5722'
        ax.add_patch(
            mpatches.Rectangle(
                (x - width_days * 0.55, float(row['low']) - 2),
                width_days * 1.1,
                float(row['high']) - float(row['low']) + 4,
                fill=False,
                edgecolor=color,
                linewidth=2.8,
                zorder=7,
            )
        )
        tag = '↑engulf' if ev.kind == 'bullish_engulf' else '↓engulf'
        ax.annotate(
            tag,
            xy=(x, float(row['high']) + 5),
            fontsize=7,
            color=color,
            ha='center',
            fontweight='bold',
            zorder=9,
        )

    atr = ctx.get('ATR')
    wo = ctx['WO']
    bull_n = sum(1 for e in engulfs if e.kind == 'bullish_engulf')
    bear_n = len(engulfs) - bull_n
    fri = (pd.Timestamp(week_key, tz=NY) + pd.Timedelta(days=5)).date()
    title = (
        f'NQ 1h · {week_key} – {fri} · WO±ATR engulf · '
        f'{len(engulfs)} signal ({bull_n}↑ {bear_n}↓) · WO {wo:.1f} ATR {atr:.1f}'
    )
    style_axes(ax, title)
    ax.set_ylabel('NQ', color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.set_xlim(bars.index[0] - pd.Timedelta(hours=2), bars.index[-1] + pd.Timedelta(hours=2))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)


def build(
    *,
    output_root: Path,
    start: str,
    count: int,
    seed: int,
    force: bool,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    dbn = POTIONS_ROOT / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    print('Loading NQ 1m ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    one_min = one_min[one_min.index >= pd.Timestamp(start, tz=NY)]
    hourly = resample_1h(one_min)
    ha_full = compute_ha_candles(hourly)
    daily_atr = build_daily_atr(hourly)
    weekly = build_weekly_table(hourly, daily_atr)

    candidates: list[dict] = []
    total_engulfs = 0

    for week in weekly.index:
        ctx = week_context(weekly, week)
        if ctx is None or ctx.get('ATR') is None:
            continue
        ws = weekly.loc[week, 'week_start']
        if ws < pd.Timestamp(start, tz=NY):
            continue
        bars = week_hourly_slice(hourly, ws)
        if len(bars) < 12:
            continue
        wo = float(ctx['WO'])
        atr = float(ctx['ATR'])
        engulfs = find_engulfings_after_atr_extension(bars, wo, atr)
        if not engulfs:
            continue
        total_engulfs += len(engulfs)
        candidates.append(
            {
                'week_start': ws.date().isoformat(),
                'year': ws.year,
                'wo': wo,
                'atr': atr,
                'engulf_count': len(engulfs),
                'bullish': sum(1 for e in engulfs if e.kind == 'bullish_engulf'),
                'bearish': sum(1 for e in engulfs if e.kind == 'bearish_engulf'),
                'bars': bars,
                'ctx': ctx,
                'engulfs': engulfs,
                'week': week,
            }
        )

    print(f'  {len(candidates)} weeks with ≥1 qualifying engulf · {total_engulfs} signals total', flush=True)
    selected = stratified_sample(candidates, count, seed)
    print(f'  charting {len(selected)} weeks (target {count})', flush=True)

    manifest_rows: list[dict] = []
    index_lines: list[str] = []

    for n, item in enumerate(selected, start=1):
        ws_key = item['week_start']
        year = item['year']
        rel = f'charts/{year}/{ws_key}.png'
        plot_week_engulf_chart(
            output_root / rel,
            item['bars'],
            item['ctx'],
            ws_key,
            item['engulfs'],
            ha_pins=ha_pins_for_week(item['bars'], ha_full),
        )
        sig = f'{item["engulf_count"]} ({item["bullish"]}↑/{item["bearish"]}↓)'
        index_lines.append(
            f'| {n} | {ws_key} | {sig} | [{ws_key}.png]({rel}) |'
        )
        for ev in item['engulfs']:
            manifest_rows.append(
                {
                    'chart': rel,
                    'week_start': ws_key,
                    'year': year,
                    'bar_idx': ev.bar_idx,
                    'ts': str(item['bars'].index[ev.bar_idx]),
                    'kind': ev.kind,
                    'extension': ev.extension,
                    'WO': item['wo'],
                    'ATR': item['atr'],
                }
            )
        if n % 25 == 0:
            print(f'  … {n} charts', flush=True)

    pd.DataFrame(manifest_rows).to_csv(output_root / 'manifest.csv', index=False)
    year_counts = pd.Series([r['year'] for r in manifest_rows]).value_counts().sort_index()
    by_year_weeks = pd.DataFrame(selected).groupby('year').size() if selected else pd.Series()

    lines = [
        '# NQ weekly 1h — engulfing after >1 ATR from WO',
        '',
        f'**{len(selected)}** sample weeks (seed **{seed}**, stratified by year) · '
        f'**{sum(r["engulf_count"] for r in selected)}** engulfing signals charted.',
        f'Universe: **{len(candidates)}** qualifying weeks from **{start}** with **{total_engulfs}** total signals.',
        '',
        '## Rules',
        '',
        '- **Weekly open (WO)** and **daily ATR(14)** at week start (causal, same as WO gap study).',
        '- Price must have traded **≥1 ATR above WO** (`high ≥ WO+ATR`) before a **bearish engulfing**,',
        '  or **≥1 ATR below WO** (`low ≤ WO−ATR`) before a **bullish engulfing**.',
        '- **Engulfing:** current body fully engulfs prior opposite-color body (strict O/C rules).',
        '- Chart layout matches [`nq_weekly_wo_gap_reversal_sample`](nq_weekly_wo_gap_reversal_sample/INDEX.md):',
        '  PWH/PWL/PWC/PWO, PW 50%, WO, WO±ATR bands, causal **HA pin** black outlines.',
        '- **Orange** outline = bullish engulf · **Red** = bearish engulf.',
        '',
        f'Earliest data: `{start}`',
        '',
        '## By year (charted weeks)',
        '',
    ]
    for y in sorted(by_year_weeks.index):
        lines.append(f'- **{y}**: {int(by_year_weeks[y])} weeks')
    lines.extend(
        [
            '',
            '## Charts',
            '',
            '| # | Week | Engulf signals | Chart |',
            '|---:|---|---|---|',
            *index_lines,
            '',
            'Full bar list: [`manifest.csv`](manifest.csv)',
            '',
        ]
    )
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {output_root / "INDEX.md"}', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_weekly_wo_atr_engulfing_sample')
    ap.add_argument('--start', type=str, default='2011-01-01')
    ap.add_argument('--count', type=int, default=100)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    build(
        output_root=args.output_root,
        start=args.start,
        count=args.count,
        seed=args.seed,
        force=args.force,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
