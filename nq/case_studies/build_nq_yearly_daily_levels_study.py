#!/usr/bin/env python3
"""
NQ yearly daily charts by calendar quarter.

Prior-year levels + yearly open + monthly-open step + YO/MO breakout marks.
Alternating month shading within each quarter. No HA pins or engulfing.

Output: ``charts/YYYY/Q1.png`` … ``Q4.png``

Usage::

  python3 nq/case_studies/build_nq_yearly_daily_levels_study.py --force
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]

QUARTER_MONTHS = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN_CANDLE = '#26A69A'
RED_CANDLE = '#EF5350'
MONTH_FILL_A = '#152535'
MONTH_FILL_B = '#1E3048'
BREAK_YO_BULL = '#FFB74D'
BREAK_YO_BEAR = '#E64A19'
BREAK_MO_BULL = '#4FC3F7'
BREAK_MO_BEAR = '#CE93D8'


@dataclass
class BarMark:
    bar_idx: int
    kind: str


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def yearly_ohlc(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy()
    work['year'] = work['date'].dt.year
    rows = []
    for year, g in work.groupby('year', sort=True):
        g = g.sort_values('date')
        rows.append(
            {
                'year': int(year),
                'open': float(g['open'].iloc[0]),
                'high': float(g['high'].max()),
                'low': float(g['low'].min()),
                'close': float(g['close'].iloc[-1]),
            }
        )
    return pd.DataFrame(rows).set_index('year')


def prior_year_ctx(yearly: pd.DataFrame, year: int) -> dict[str, float] | None:
    if year not in yearly.index or (year - 1) not in yearly.index:
        return None
    prev = yearly.loc[year - 1]
    pyh = float(prev['high'])
    pyl = float(prev['low'])
    return {
        'PYO': float(prev['open']),
        'PYH': pyh,
        'PYL': pyl,
        'PYC': float(prev['close']),
        'PY_MID': pyl + 0.5 * (pyh - pyl),
        'YO': float(yearly.loc[year, 'open']),
    }


def month_opens_for_year(year_bars: pd.DataFrame) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    for (y, m), g in year_bars.groupby([year_bars['date'].dt.year, year_bars['date'].dt.month]):
        g = g.sort_values('date')
        out[(int(y), int(m))] = float(g['open'].iloc[0])
    return out


def quarter_slice(year_bars: pd.DataFrame, quarter: int) -> pd.DataFrame:
    months = QUARTER_MONTHS[quarter]
    return year_bars[year_bars['date'].dt.month.isin(months)].copy()


def crosses_up(o: float, c: float, level: float) -> bool:
    return o < level < c


def crosses_down(o: float, c: float, level: float) -> bool:
    return o > level > c


def collect_breakout_marks(
    bars: pd.DataFrame,
    yo: float,
    mo_map: dict[tuple[int, int], float],
) -> list[BarMark]:
    marks: list[BarMark] = []
    for i in range(len(bars)):
        ts = bars['date'].iloc[i]
        row = bars.iloc[i]
        o, c = float(row['open']), float(row['close'])
        ym = (int(ts.year), int(ts.month))
        mo = mo_map.get(ym)
        if crosses_up(o, c, yo):
            marks.append(BarMark(i, 'break_yo_bull'))
        if crosses_down(o, c, yo):
            marks.append(BarMark(i, 'break_yo_bear'))
        if mo is not None:
            if crosses_up(o, c, mo):
                marks.append(BarMark(i, 'break_mo_bull'))
            if crosses_down(o, c, mo):
                marks.append(BarMark(i, 'break_mo_bear'))
    return marks


def shade_alternating_months(ax, bars: pd.DataFrame) -> None:
    if bars.empty:
        return
    for month in sorted(bars['date'].dt.month.unique()):
        sub = bars[bars['date'].dt.month == month]
        if sub.empty:
            continue
        t0 = pd.Timestamp(sub['date'].iloc[0]) - pd.Timedelta(hours=12)
        t1 = pd.Timestamp(sub['date'].iloc[-1]) + pd.Timedelta(hours=12)
        fill = MONTH_FILL_A if int(month) % 2 == 1 else MONTH_FILL_B
        ax.axvspan(
            mdates.date2num(t0),
            mdates.date2num(t1),
            facecolor=fill,
            alpha=0.55,
            zorder=0,
        )


def draw_month_open_steps(
    ax,
    bars: pd.DataFrame,
    year: int,
    mo_map: dict[tuple[int, int], float],
) -> None:
    if bars.empty:
        return
    for month in sorted(bars['date'].dt.month.unique()):
        mo = mo_map.get((year, int(month)))
        if mo is None:
            continue
        sub = bars[bars['date'].dt.month == month]
        if sub.empty:
            continue
        t0 = mdates.date2num(pd.Timestamp(sub['date'].iloc[0]))
        t1 = mdates.date2num(pd.Timestamp(sub['date'].iloc[-1]) + pd.Timedelta(hours=20))
        ax.plot([t0, t1], [mo, mo], color='#26C6DA', linestyle=':', linewidth=1.0, alpha=0.75, zorder=2)


def draw_candles(ax, work: pd.DataFrame) -> None:
    dates = pd.to_datetime(work['date'])
    xnums = mdates.date2num(dates)
    width = 0.62
    for x, (_, row) in zip(xnums, work.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN_CANDLE if c >= o else RED_CANDLE
        ax.vlines(x, l, h, color=col, linewidth=0.7, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.92,
                zorder=3,
            )
        )


def outline_bar(ax, x: float, row: pd.Series, color: str, lw: float, ls: str = '-') -> None:
    width = 0.62
    ax.add_patch(
        mpatches.Rectangle(
            (x - width / 2 * 0.55, float(row['low']) - 1),
            width * 1.1,
            float(row['high']) - float(row['low']) + 2,
            fill=False,
            edgecolor=color,
            linewidth=lw,
            linestyle=ls,
            zorder=8,
        )
    )


def plot_quarter(
    out_path: Path,
    year: int,
    quarter: int,
    bars: pd.DataFrame,
    ctx: dict[str, float],
    marks: list[BarMark],
    mo_map: dict[tuple[int, int], float],
) -> None:
    work = bars.sort_values('date').reset_index(drop=True)
    if work.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 8), facecolor=BG)
    ax.set_facecolor(BG)
    shade_alternating_months(ax, work)
    draw_candles(ax, work)

    x0 = mdates.date2num(work['date'].iloc[0])
    x1 = mdates.date2num(work['date'].iloc[-1])
    specs = [
        ('PYH', '#CE93D8', '-', 1.1),
        ('PYL', '#CE93D8', '-', 1.1),
        ('PYC', '#FFC107', '-.', 1.15),
        ('PYO', '#26C6DA', '-', 1.15),
        ('PY_MID', '#9FB3C8', '--', 1.0),
        ('YO', '#76FF03', '-', 1.2),
    ]
    for key, color, ls, lw in specs:
        ax.plot([x0, x1], [ctx[key], ctx[key]], color=color, linestyle=ls, linewidth=lw, alpha=0.9, zorder=2)

    draw_month_open_steps(ax, work, year, mo_map)

    mark_styles = {
        'break_yo_bull': (BREAK_YO_BULL, 2.2, '--'),
        'break_yo_bear': (BREAK_YO_BEAR, 2.2, '--'),
        'break_mo_bull': (BREAK_MO_BULL, 2.0, ':'),
        'break_mo_bear': (BREAK_MO_BEAR, 2.0, ':'),
    }
    tags = {
        'break_yo_bull': 'YO↑',
        'break_yo_bear': 'YO↓',
        'break_mo_bull': 'MO↑',
        'break_mo_bear': 'MO↓',
    }
    for m in marks:
        row = work.iloc[m.bar_idx]
        x = mdates.date2num(work['date'].iloc[m.bar_idx])
        color, lw, ls = mark_styles.get(m.kind, ('white', 1.5, '-'))
        outline_bar(ax, x, row, color, lw, ls)
        ax.annotate(
            tags.get(m.kind, m.kind),
            xy=(x, float(row['high']) + 4),
            fontsize=5,
            color=color,
            ha='center',
            rotation=90,
            zorder=9,
        )

    n_yo = sum(1 for m in marks if m.kind.startswith('break_yo'))
    n_mo = sum(1 for m in marks if m.kind.startswith('break_mo'))
    q_label = f'Q{quarter}'
    ax.set_title(
        f'NQ daily · {year} {q_label} · PY levels + YO/MO · break YO {n_yo} MO {n_mo}',
        color='white',
        fontsize=11,
        fontweight='bold',
        loc='left',
        pad=10,
    )
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.1, color=GRID, zorder=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.set_ylabel('NQ', color=GRID)

    handles = [
        mpatches.Patch(facecolor=MONTH_FILL_A, alpha=0.7, label='odd months'),
        mpatches.Patch(facecolor=MONTH_FILL_B, alpha=0.7, label='even months'),
        plt.Line2D([0], [0], color='#76FF03', lw=1.2, label='YO'),
        plt.Line2D([0], [0], color='#26C6DA', lw=1.0, ls=':', label='MO'),
        plt.Line2D([0], [0], color='#CE93D8', lw=1.1, label='PYH/PYL'),
        mpatches.Rectangle((0, 0), 1, 1, fill=False, edgecolor=BREAK_YO_BULL, linewidth=2, ls='--', label='break YO'),
        mpatches.Rectangle((0, 0), 1, 1, fill=False, edgecolor=BREAK_MO_BULL, linewidth=2, ls=':', label='break MO'),
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
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, facecolor=BG)
    plt.close(fig)


def build(output_root: Path, daily_path: Path, start_year: int, force: bool) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    daily = load_daily(daily_path)
    yearly = yearly_ohlc(daily)

    manifest: list[dict] = []
    index_rows: list[str] = []
    chart_count = 0

    years = [y for y in sorted(yearly.index) if y >= start_year and (y - 1) in yearly.index]
    print(f'Charting {len(years)} years × 4 quarters from {daily_path.name} ...', flush=True)

    for year in years:
        ctx = prior_year_ctx(yearly, year)
        if ctx is None:
            continue
        year_bars = daily[daily['date'].dt.year == year].copy()
        if year_bars.empty:
            continue
        mo_map = month_opens_for_year(year_bars)

        for quarter in (1, 2, 3, 4):
            qbars = quarter_slice(year_bars, quarter)
            if len(qbars) < 3:
                continue
            marks = collect_breakout_marks(qbars, ctx['YO'], mo_map)
            rel = f'charts/{year}/Q{quarter}.png'
            plot_quarter(output_root / rel, year, quarter, qbars, ctx, marks, mo_map)
            chart_count += 1

            n_yo = sum(1 for m in marks if m.kind.startswith('break_yo'))
            n_mo = sum(1 for m in marks if m.kind.startswith('break_mo'))
            index_rows.append(
                f'| {year} | Q{quarter} | {len(qbars)} | {n_yo} | {n_mo} | [Q{quarter}.png](charts/{year}/Q{quarter}.png) |'
            )
            for m in marks:
                ts = qbars['date'].iloc[m.bar_idx]
                manifest.append(
                    {
                        'year': year,
                        'quarter': quarter,
                        'date': ts.date().isoformat(),
                        'kind': m.kind,
                    }
                )

        if year % 5 == 0:
            print(f'  … {year}', flush=True)

    pd.DataFrame(manifest).to_csv(output_root / 'manifest.csv', index=False)
    lines = [
        '# NQ yearly daily — quarterly charts',
        '',
        f'**{chart_count}** quarter charts ({len(years)} years × Q1–Q4 where data exists) · `{daily_path.name}`.',
        'Paths: `charts/YYYY/Q1.png` … `Q4.png`.',
        '',
        '## Levels (full prior-year context on each quarter chart)',
        '',
        '| Level | Description |',
        '|---|---|',
        '| PYH / PYL | Prior calendar year high / low |',
        '| PYC | Prior year close |',
        '| PYO | Prior year open |',
        '| PY_MID | Prior year 50% |',
        '| YO | Current year open |',
        '| MO | Monthly open (cyan dotted, months in view) |',
        '',
        '## Marked candles',
        '',
        '- **Orange / red dashed** — crosses **yearly open**',
        '- **Cyan / purple dotted** — crosses **that month\'s open**',
        '',
        'HA pins and engulfing are **not** shown on this version.',
        '',
        '## Charts',
        '',
        '| Year | Quarter | Days | Break YO | Break MO | Chart |',
        '|---:|---:|---:|---:|---:|---|',
        *index_rows,
        '',
        'Bar-level log: [`manifest.csv`](manifest.csv)',
        '',
    ]
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {chart_count} charts · {output_root / "INDEX.md"}', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_yearly_daily_levels')
    ap.add_argument('--daily', type=Path, default=POTIONS_ROOT / 'nq' / 'nq_daily.csv')
    ap.add_argument('--start-year', type=int, default=2011)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    build(args.output_root, args.daily, args.start_year, args.force)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
