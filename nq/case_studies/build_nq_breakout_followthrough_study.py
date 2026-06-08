#!/usr/bin/env python3
"""
Monthly MO bias follow-through — every session day in bias-tagged folders.

Bias (close vs current-month open):
- **bull** when daily close >= MO
- **bear** when daily close < MO

Layout::

  charts/{YYYY}/{YYYY-MM}/month_overview.png   # daily month + bias switches
  charts/{YYYY}/{YYYY-MM}/{bias}_{start_date}/
    {YYYY-MM-DD}.png   # 15m NY 00:00–16:00

Within a calendar month, consecutive days sharing the same bias live in one folder.
When bias flips, a new ``{bias}_{flip_date}`` folder starts. A new month → new parent
``{YYYY-MM}/`` with that month's MO.

Levels on each chart: MO, PMO, PMH, PML, PM 50%, MO ±1/±2 ATR (daily ATR14, causal).

Bias notes (not a strategy): ``nq_yearly_daily_levels/BIAS_STUDY.md``

Usage::

  python3 nq/case_studies/build_nq_breakout_followthrough_study.py --force
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]
MNQ_CS = POTIONS_ROOT / 'mnq' / 'case_studies' / 'midnight_open_hourly_charts'
sys.path.insert(0, str(MNQ_CS))

from build_midnight_open_hourly_charts import (  # noqa: E402
    DEFAULT_DBN_NQ,
    NY,
    load_1m_by_ny_date,
    resample_15m_midnight_to_1600,
)
from build_nq_yearly_daily_levels_study import BG, GREEN_CANDLE, RED_CANDLE, load_daily  # noqa: E402

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
RTH_FILL = '#243B55'
ETH_FILL = '#111D2C'
ATR_LEN = 14

BULL_COLOR = '#76FF03'
BEAR_COLOR = '#EF5350'
MO_COLOR = '#26C6DA'
PM_COLOR = '#CE93D8'
ATR_COLOR = '#1F4E79'


@dataclass
class MonthCtx:
    ym: tuple[int, int]
    mo: float
    pmo: float
    pmh: float
    pml: float
    pm_mid: float
    atr: float | None


@dataclass
class BiasStreak:
    bias: str
    start: date
    days: list[date] = field(default_factory=list)


def build_monthly_table(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy()
    work['ym'] = list(zip(work['date'].dt.year, work['date'].dt.month))
    rows = []
    for ym, g in work.groupby('ym', sort=True):
        g = g.sort_values('date')
        rows.append(
            {
                'ym': ym,
                'open': float(g['open'].iloc[0]),
                'high': float(g['high'].max()),
                'low': float(g['low'].min()),
                'close': float(g['close'].iloc[-1]),
            }
        )
    return pd.DataFrame(rows).set_index(pd.MultiIndex.from_tuples([r['ym'] for r in rows], names=['year', 'month']))


def build_daily_atr(daily: pd.DataFrame) -> pd.Series:
    work = daily.sort_values('date').copy()
    prev_close = work['close'].shift(1)
    tr = pd.concat(
        [
            work['high'] - work['low'],
            (work['high'] - prev_close).abs(),
            (work['low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=ATR_LEN, adjust=False, min_periods=ATR_LEN).mean().shift(1)
    return pd.Series(atr.values, index=work['date'].dt.date)


def month_context(
    ym: tuple[int, int],
    monthly: pd.DataFrame,
    atr_by_date: pd.Series,
    month_first_day: date,
) -> MonthCtx | None:
    y, m = ym
    prev_ym = (y, m - 1) if m > 1 else (y - 1, 12)
    if ym not in monthly.index and (y, m) not in monthly.index:
        return None
    idx = ym if ym in monthly.index else (y, m)
    prev_idx = (y, m - 1) if m > 1 else (y - 1, 12)
    if prev_idx not in monthly.index:
        return None
    cur = monthly.loc[idx]
    prev = monthly.loc[prev_idx]
    pmh = float(prev['high'])
    pml = float(prev['low'])
    atr_val = None
    prior = atr_by_date[atr_by_date.index < month_first_day]
    if not prior.empty and pd.notna(prior.iloc[-1]):
        atr_val = float(prior.iloc[-1])
    return MonthCtx(
        ym=ym,
        mo=float(cur['open']),
        pmo=float(prev['open']),
        pmh=pmh,
        pml=pml,
        pm_mid=pml + 0.5 * (pmh - pml),
        atr=atr_val,
    )


def close_bias(close: float, mo: float, prior: str | None) -> str:
    if close > mo:
        return 'bull'
    if close < mo:
        return 'bear'
    return prior or 'bull'


def streak_folder(month_key: str, streak: BiasStreak) -> str:
    return f'{streak.bias}_{streak.start.isoformat()}'


def month_rel_dir(year: int, month_key: str) -> str:
    return f'charts/{year:04d}/{month_key}'


def draw_daily_candles(ax, work: pd.DataFrame, width: float = 0.55) -> None:
    for _, row in work.iterrows():
        x = mdates.date2num(pd.Timestamp(row['date']))
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN_CANDLE if c >= o else RED_CANDLE
        ax.vlines(x, l, h, color=col, linewidth=0.8, zorder=3)
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


def plot_month_overview(
    out_path: Path,
    month_key: str,
    month_bars: pd.DataFrame,
    ctx: MonthCtx,
    streaks: list[BiasStreak],
) -> None:
    work = month_bars.sort_values('date').reset_index(drop=True)
    if work.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 6), facecolor=BG)
    ax.set_facecolor(BG)

    for streak in streaks:
        t0 = pd.Timestamp(streak.start) - pd.Timedelta(hours=6)
        t1 = pd.Timestamp(streak.days[-1]) + pd.Timedelta(hours=18)
        fill = BULL_COLOR if streak.bias == 'bull' else BEAR_COLOR
        ax.axvspan(
            mdates.date2num(t0),
            mdates.date2num(t1),
            facecolor=fill,
            alpha=0.10,
            zorder=0,
        )

    draw_daily_candles(ax, work)

    x0 = mdates.date2num(work['date'].iloc[0])
    x1 = mdates.date2num(work['date'].iloc[-1])
    draw_level_lines(ax, x0, x1, ctx, 'bull')

    for streak in streaks[1:]:
        x = mdates.date2num(pd.Timestamp(streak.start))
        color = BULL_COLOR if streak.bias == 'bull' else BEAR_COLOR
        ax.axvline(x, color=color, linestyle='--', linewidth=1.6, alpha=0.95, zorder=6)
        y_top = float(work['high'].max())
        ax.annotate(
            streak.bias,
            xy=(x, y_top),
            xytext=(0, 4),
            textcoords='offset points',
            color=color,
            fontsize=7,
            ha='center',
            fontweight='bold',
            rotation=90,
            zorder=7,
        )

    n_bull = sum(1 for s in streaks if s.bias == 'bull')
    n_bear = sum(1 for s in streaks if s.bias == 'bear')
    ax.set_title(
        f'NQ daily · {month_key} · MO bias overview · {len(streaks)} switches (bull {n_bull} / bear {n_bear})',
        color='white',
        fontsize=10,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.12, color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    fig.autofmt_xdate(rotation=0)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, facecolor=BG)
    plt.close(fig)


def shade_rth(ax, bars: pd.DataFrame) -> None:
    if bars.empty:
        return
    t0, t1 = bars.index[0], bars.index[-1]
    ax.axvspan(mdates.date2num(t0), mdates.date2num(t1), facecolor=ETH_FILL, alpha=0.5, zorder=0)
    day = bars.index[0].normalize()
    if day.weekday() < 5:
        rth0 = NY.localize(datetime.combine(day.date(), RTH_OPEN))
        rth1 = NY.localize(datetime.combine(day.date(), RTH_CLOSE))
        ax.axvspan(
            mdates.date2num(max(rth0, t0)),
            mdates.date2num(min(rth1, t1)),
            facecolor=RTH_FILL,
            alpha=0.65,
            zorder=1,
        )


def draw_level_lines(ax, x0: float, x1: float, ctx: MonthCtx, bias: str) -> None:
    specs: list[tuple[str, float, str, str, float]] = [
        ('MO', ctx.mo, MO_COLOR, '-', 1.4),
        ('PMO', ctx.pmo, PM_COLOR, '-', 1.0),
        ('PMH', ctx.pmh, PM_COLOR, '-', 1.0),
        ('PML', ctx.pml, PM_COLOR, '-', 1.0),
        ('PM 50%', ctx.pm_mid, PM_COLOR, '--', 0.9),
    ]
    if ctx.atr is not None and np.isfinite(ctx.atr):
        a = ctx.atr
        specs.extend(
            [
                ('MO+1ATR', ctx.mo + a, ATR_COLOR, ':', 0.85),
                ('MO-1ATR', ctx.mo - a, ATR_COLOR, ':', 0.85),
                ('MO+2ATR', ctx.mo + 2 * a, ATR_COLOR, ':', 0.65),
                ('MO-2ATR', ctx.mo - 2 * a, ATR_COLOR, ':', 0.65),
            ]
        )
    for label, y, color, ls, lw in specs:
        ax.plot([x0, x1], [y, y], color=color, linestyle=ls, linewidth=lw, alpha=0.9, zorder=2)
        ax.annotate(
            f'{label} {y:.1f}',
            xy=(x1, y),
            xytext=(3, 0),
            textcoords='offset points',
            color=color,
            fontsize=6,
            va='center',
        )


def plot_15m_day(
    out_path: Path,
    session_day: date,
    bars15: pd.DataFrame,
    ctx: MonthCtx,
    bias: str,
) -> bool:
    if bars15.empty or len(bars15) < 2:
        return False

    bias_color = BULL_COLOR if bias == 'bull' else BEAR_COLOR
    fig, ax = plt.subplots(figsize=(14, 7), facecolor=BG)
    ax.set_facecolor(BG)
    shade_rth(ax, bars15)

    xs = mdates.date2num(list(bars15.index.to_pydatetime()))
    width = (15 / (24 * 60)) * 0.72 if len(xs) > 1 else 0.01
    for x, (_, row) in zip(xs, bars15.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN_CANDLE if c >= o else RED_CANDLE
        ax.vlines(x, l, h, color=col, linewidth=0.85, zorder=3)
        body_lo = min(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(abs(c - o), 0.08),
                facecolor=col,
                edgecolor=col,
                alpha=0.92,
                zorder=3,
            )
        )

    x0, x1 = xs[0], xs[-1]
    draw_level_lines(ax, x0, x1, ctx, bias)

    ym = f'{session_day.year:04d}-{session_day.month:02d}'
    ax.set_title(
        f'NQ 15m · {session_day} · {ym} · {bias.upper()} (close vs MO) · MO {ctx.mo:.2f}',
        color=bias_color,
        fontsize=9,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.1, color='#9FB3C8')
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, facecolor=BG)
    plt.close(fig)
    return True


def assign_month_streaks(month_bars: pd.DataFrame, mo: float) -> list[BiasStreak]:
    streaks: list[BiasStreak] = []
    current: BiasStreak | None = None
    prior_bias: str | None = None
    for _, row in month_bars.sort_values('date').iterrows():
        d = row['date'].date()
        bias = close_bias(float(row['close']), mo, prior_bias)
        prior_bias = bias
        if current is None or current.bias != bias:
            current = BiasStreak(bias=bias, start=d, days=[d])
            streaks.append(current)
        else:
            current.days.append(d)
    return streaks


def build(
    output_root: Path,
    daily_path: Path,
    dbn_path: Path,
    force: bool,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    charts_root = output_root / 'charts'
    charts_root.mkdir(parents=True, exist_ok=True)

    daily = load_daily(daily_path).sort_values('date')
    monthly = build_monthly_table(daily)
    atr_by_date = build_daily_atr(daily)

    print(f'Loading 1m from {dbn_path.name} ...', flush=True)
    gby_1m = load_1m_by_ny_date(dbn_path, 'nq')

    day_rows: list[dict] = []
    streak_rows: list[dict] = []
    n_charts = 0
    n_skip = 0
    n_overviews = 0

    months = sorted(daily.assign(ym=list(zip(daily['date'].dt.year, daily['date'].dt.month)))['ym'].unique())
    print(f'Processing {len(months)} calendar months from {daily_path.name} ...', flush=True)

    for mi, ym in enumerate(months):
        month_bars = daily[(daily['date'].dt.year == ym[0]) & (daily['date'].dt.month == ym[1])].copy()
        if month_bars.empty:
            continue
        month_key = f'{ym[0]:04d}-{ym[1]:02d}'
        year = ym[0]
        month_dir_rel = month_rel_dir(year, month_key)
        month_dir = output_root / month_dir_rel
        first_day = month_bars['date'].iloc[0].date()
        ctx = month_context(ym, monthly, atr_by_date, first_day)
        if ctx is None:
            continue

        streaks = assign_month_streaks(month_bars, ctx.mo)
        plot_month_overview(month_dir / 'month_overview.png', month_key, month_bars, ctx, streaks)
        n_overviews += 1

        for streak in streaks:
            rel_dir = f'{month_dir_rel}/{streak_folder(month_key, streak)}'
            streak_dir = output_root / rel_dir
            chart_days = 0
            for d in streak.days:
                day_1m = gby_1m.get(d)
                bars15 = resample_15m_midnight_to_1600(day_1m, d) if day_1m is not None else pd.DataFrame()
                out_png = streak_dir / f'{d.isoformat()}.png'
                ok = plot_15m_day(out_png, d, bars15, ctx, streak.bias)
                if ok:
                    n_charts += 1
                    chart_days += 1
                else:
                    n_skip += 1
                day_rows.append(
                    {
                        'date': d.isoformat(),
                        'month': month_key,
                        'bias': streak.bias,
                        'close': float(month_bars[month_bars['date'].dt.date == d]['close'].iloc[0]),
                        'mo': ctx.mo,
                        'streak_start': streak.start.isoformat(),
                        'folder': rel_dir,
                        'chart': f'{rel_dir}/{d.isoformat()}.png' if ok else '',
                    }
                )
            streak_rows.append(
                {
                    'month': month_key,
                    'bias': streak.bias,
                    'start': streak.start.isoformat(),
                    'end': streak.days[-1].isoformat(),
                    'days': len(streak.days),
                    'charts': chart_days,
                    'folder': rel_dir,
                    'mo': ctx.mo,
                    'pmo': ctx.pmo,
                    'pmh': ctx.pmh,
                    'pml': ctx.pml,
                    'pm_mid': ctx.pm_mid,
                    'atr': ctx.atr if ctx.atr is not None else '',
                }
            )

        if (mi + 1) % 24 == 0:
            print(f'  … {month_key} · {n_charts:,} charts', flush=True)

    pd.DataFrame(day_rows).to_csv(output_root / 'days.csv', index=False)
    pd.DataFrame(streak_rows).to_csv(output_root / 'streaks.csv', index=False)

    bias_link = '../nq_yearly_daily_levels/BIAS_STUDY.md'
    n_days = len(day_rows)
    n_streaks = len(streak_rows)
    lines = [
        '# NQ monthly MO bias follow-through',
        '',
        f'**{n_days:,}** session days · **{n_streaks:,}** bias streaks · **{n_charts:,}** 15m charts · **{n_overviews:,}** month overviews.',
        '',
        f'Bias framework (notes only): [`BIAS_STUDY.md`]({bias_link})',
        '',
        '## Rules',
        '',
        '- **Bull** when daily **close >= MO** (current calendar month open).',
        '- **Bear** when daily **close < MO**.',
        '- Bias resets each month (new MO, new parent folder).',
        '- Within a month, consecutive same-bias days share one folder until close flips side of MO.',
        '',
        '## Folder layout',
        '',
        '```',
        'charts/{YYYY}/{YYYY-MM}/month_overview.png',
        'charts/{YYYY}/{YYYY-MM}/{bull|bear}_{YYYY-MM-DD}/',
        '  {YYYY-MM-DD}.png   # 15m NY 00:00–16:00',
        '```',
        '',
        '`month_overview.png` — full-month daily candles, MO/PM levels, shaded bull/bear streaks, dashed verticals at each bias switch.',
        '',
        '`{YYYY-MM-DD}` on the streak folder = first day of that bias streak.',
        '',
        '## Levels (each 15m chart)',
        '',
        '| Level | Description |',
        '|---|---|',
        '| MO | Current month open |',
        '| PMO / PMH / PML | Prior month open / high / low |',
        '| PM 50% | Prior month midpoint |',
        '| MO ±1/±2 ATR | Daily ATR(14), prior session (causal) |',
        '',
        f'Skipped (no 1m session): **{n_skip:,}**',
        '',
        '## Streaks by month',
        '',
        '| Month | Bias | Start | End | Days | Folder | Overview |',
        '|---|---|---|---|---:|---|---|',
    ]
    overview_by_month: dict[str, str] = {}
    for r in streak_rows:
        overview_by_month.setdefault(r['month'], r['folder'].rsplit('/', 1)[0])
    seen_month: set[str] = set()
    for r in streak_rows:
        ov_link = ''
        if r['month'] not in seen_month:
            seen_month.add(r['month'])
            base = overview_by_month.get(r['month'], '')
            if base:
                ov_link = f'[overview]({base}/month_overview.png)'
        lines.append(
            f"| {r['month']} | {r['bias']} | {r['start']} | {r['end']} | {r['days']} | "
            f"[{r['folder'].split('/')[-1]}]({r['folder']}/{r['start']}.png) | {ov_link} |"
        )
    lines.extend(['', 'Day log: [`days.csv`](days.csv) · Streak log: [`streaks.csv`](streaks.csv)', ''])
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    print(
        f'Done → {n_days:,} days · {n_streaks:,} streaks · {n_charts:,} charts · {n_overviews:,} overviews · {output_root / "INDEX.md"}',
        flush=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_breakout_followthrough')
    ap.add_argument('--daily', type=Path, default=POTIONS_ROOT / 'nq' / 'nq_daily.csv')
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN_NQ)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    build(args.output_root, args.daily, args.dbn, args.force)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
