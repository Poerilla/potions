#!/usr/bin/env python3
"""
NQ 1-hour candles with prior-week levels (PWH, PWL, PWC, PWO), PW 50%, and
weekly-open ±1/±2 ATR zones (shaded). Two views:

1. **Per week** — x-axis = one Sun–Fri week (W-SUN period, Saturday omitted).
2. **Per month** — x-axis = all Sun–Fri weeks in that calendar month.

Usage::

  python3 nq/case_studies/build_nq_weekly_1h_level_study.py
  python3 nq/case_studies/build_nq_weekly_1h_level_study.py --last-weeks 52 --last-months 12
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]
MNQ_ROOT = POTIONS_ROOT / 'mnq'
sys.path[:0] = [str(POTIONS_ROOT), str(MNQ_ROOT / 'case_studies' / 'midnight_open_hourly_charts')]

from build_midnight_open_hourly_charts import load_1m_by_ny_date  # noqa: E402

NY = pytz.timezone('America/New_York')
RTH_END = time(16, 0)
ATR_LEN = 14
BG = '#0D1B2A'
ATR_FILL = '#1F4E79'


def concat_1m(gby: dict) -> pd.DataFrame:
    parts = [df.sort_index() for df in gby.values() if df is not None and not df.empty]
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def resample_1h(one_min: pd.DataFrame) -> pd.DataFrame:
    return (
        one_min.resample('1h', label='right', closed='right')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            volume=('volume', 'sum'),
        )
        .dropna(subset=['open', 'high', 'low', 'close'])
    )


def is_sun_fri(ts: pd.Timestamp) -> bool:
    """Sunday through Friday (exclude Saturday)."""
    return ts.weekday() != 5


def clip_sun_fri_through_friday_close(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[df.index.map(is_sun_fri)].copy()
    # Friday: keep through RTH close (16:00 NY)
    fri = out[out.index.weekday == 4]
    if not fri.empty:
        keep = []
        for ts in out.index:
            if ts.weekday() == 4 and ts.time() > RTH_END:
                continue
            keep.append(ts)
        out = out.loc[keep]
    return out


def build_daily_atr(hourly: pd.DataFrame) -> pd.Series:
    """Daily ATR(14), shifted one day (causal for intraday use)."""
    daily = (
        hourly.resample('1D')
        .agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna()
    )
    prev_close = daily['close'].shift(1)
    tr = pd.concat(
        [
            daily['high'] - daily['low'],
            (daily['high'] - prev_close).abs(),
            (daily['low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=ATR_LEN, adjust=False, min_periods=ATR_LEN).mean().shift(1)
    return atr


def build_weekly_table(hourly: pd.DataFrame, daily_atr: pd.Series) -> pd.DataFrame:
    """Weekly OHLC on W-SUN periods (full 7-day week for level math)."""
    work = hourly.copy()
    work['week'] = work.index.to_period('W-SUN')
    rows = []
    for week, g in work.groupby('week', sort=True):
        g = g.sort_index()
        if g.empty:
            continue
        ws = week.start_time.tz_localize(NY)
        # Causal daily ATR as of week open (last completed day before Sunday)
        atr_val = None
        prior_days = daily_atr[daily_atr.index < ws.normalize()]
        if not prior_days.empty and pd.notna(prior_days.iloc[-1]):
            atr_val = float(prior_days.iloc[-1])
        rows.append(
            {
                'week': week,
                'week_start': ws,
                'open': float(g['open'].iloc[0]),
                'high': float(g['high'].max()),
                'low': float(g['low'].min()),
                'close': float(g['close'].iloc[-1]),
                'atr': atr_val,
            }
        )
    return pd.DataFrame(rows).set_index('week')


def prior_week_levels(weekly: pd.DataFrame, week) -> dict[str, float] | None:
    idx = weekly.index.get_loc(week) if week in weekly.index else None
    if idx is None or idx < 1:
        return None
    prev = weekly.iloc[idx - 1]
    pwh = float(prev['high'])
    pwl = float(prev['low'])
    return {
        'PWH': pwh,
        'PWL': pwl,
        'PWC': float(prev['close']),
        'PWO': float(prev['open']),
        'PW_MID': pwl + 0.5 * (pwh - pwl),
    }


def week_context(weekly: pd.DataFrame, week) -> dict[str, float] | None:
    if week not in weekly.index:
        return None
    row = weekly.loc[week]
    prev = prior_week_levels(weekly, week)
    if prev is None:
        return None
    atr = float(row['atr']) if pd.notna(row['atr']) else None
    wo = float(row['open'])
    ctx = dict(prev)
    ctx['WO'] = wo
    ctx['ATR'] = atr
    if atr is not None and np.isfinite(atr):
        ctx['WO_p1'] = wo + atr
        ctx['WO_m1'] = wo - atr
        ctx['WO_p2'] = wo + 2 * atr
        ctx['WO_m2'] = wo - 2 * atr
    return ctx


def plot_candles(ax, bars: pd.DataFrame, width_days: float) -> None:
    for ts, row in bars.iterrows():
        x = mdates.date2num(ts)
        up = row['close'] >= row['open']
        c = '#26A69A' if up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.75, zorder=3, alpha=0.92)
        body_lo = min(row['open'], row['close'])
        body_hi = max(abs(row['close'] - row['open']), 0.25)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width_days / 2, body_lo),
                width_days,
                body_hi,
                facecolor=c,
                edgecolor=c,
                alpha=0.92,
                zorder=4,
            )
        )


def shade_atr_bands(
    ax,
    x0: float,
    x1: float,
    ctx: dict[str, float],
    *,
    y_clip: tuple[float, float] | None = None,
) -> None:
    if ctx.get('ATR') is None or not np.isfinite(ctx['ATR']):
        return
    bands = [
        (ctx['WO_m2'], ctx['WO_m1'], 0.10),
        (ctx['WO_m1'], ctx['WO_p1'], 0.18),
        (ctx['WO_p1'], ctx['WO_p2'], 0.10),
    ]
    y_lo, y_hi = y_clip if y_clip else (-np.inf, np.inf)
    for y0, y1, alpha in bands:
        ya = max(y0, y_lo)
        yb = min(y1, y_hi)
        if ya < yb:
            ax.fill_between([x0, x1], ya, yb, color=ATR_FILL, alpha=alpha, zorder=0, linewidth=0)


def hline_segment(ax, x0: float, x1: float, y: float, *, color: str, linestyle: str, lw: float, label: str | None = None) -> None:
    ax.plot([x0, x1], [y, y], color=color, linestyle=linestyle, linewidth=lw, alpha=0.88, zorder=2, label=label)


def draw_levels(
    ax,
    x0: float,
    x1: float,
    ctx: dict[str, float],
    *,
    show_wo: bool = True,
    y_clip: tuple[float, float] | None = None,
) -> None:
    shade_atr_bands(ax, x0, x1, ctx, y_clip=y_clip)
    specs = [
        ('PWH', '#CE93D8', '-', 1.1),
        ('PWL', '#CE93D8', '-', 1.1),
        ('PWC', '#FFC107', '-.', 1.15),
        ('PWO', '#26C6DA', '-', 1.15),
        ('PW_MID', '#9FB3C8', '--', 1.0),
    ]
    for key, color, ls, lw in specs:
        hline_segment(ax, x0, x1, ctx[key], color=color, linestyle=ls, lw=lw, label=key)
    if show_wo:
        hline_segment(ax, x0, x1, ctx['WO'], color='#76FF03', linestyle='-', lw=1.0, label='WO')


def style_axes(ax, title: str) -> None:
    ax.set_facecolor(BG)
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.12, color='#9FB3C8')
    ax.legend(
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=7,
        ncol=2,
    )


def week_hourly_slice(hourly: pd.DataFrame, week_start: pd.Timestamp) -> pd.DataFrame:
    week_end = week_start + pd.Timedelta(days=7)
    w = hourly[(hourly.index >= week_start) & (hourly.index < week_end)]
    return clip_sun_fri_through_friday_close(w)


def plot_week_chart(
    out_path: Path,
    hourly: pd.DataFrame,
    weekly: pd.DataFrame,
    week,
) -> bool:
    ctx = week_context(weekly, week)
    if ctx is None:
        return False
    week_start = weekly.loc[week, 'week_start']
    bars = week_hourly_slice(hourly, week_start)
    if len(bars) < 12:
        return False

    fig, ax = plt.subplots(figsize=(16, 8), facecolor=BG)
    x0 = mdates.date2num(bars.index[0])
    x1 = mdates.date2num(bars.index[-1])
    pad = max((bars['high'].max() - bars['low'].min()) * 0.08, 20.0)
    y_clip = (float(bars['low'].min()) - pad, float(bars['high'].max()) + pad)
    draw_levels(ax, x0, x1, ctx, y_clip=y_clip)
    plot_candles(ax, bars, width_days=(60 / (24 * 60)) * 0.68)
    fri = (week_start + pd.Timedelta(days=5)).date()
    atr = ctx.get('ATR')
    if atr is not None and np.isfinite(atr):
        title = (
            f"NQ 1h  ·  {week_start.date()} – {fri}  ·  "
            f"PWH/PWL/PWC/PWO + WO±ATR  ·  dailyATR{ATR_LEN}={atr:.1f}"
        )
    else:
        title = f"NQ 1h  ·  {week_start.date()} – {fri}  ·  PWH/PWL/PWC/PWO"
    style_axes(ax, title)
    ax.set_ylabel('NQ', color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.set_xlim(bars.index[0] - pd.Timedelta(hours=2), bars.index[-1] + pd.Timedelta(hours=2))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return True


def plot_month_chart(
    out_path: Path,
    hourly: pd.DataFrame,
    weekly: pd.DataFrame,
    year: int,
    month: int,
) -> bool:
    month_start = pd.Timestamp(year=year, month=month, day=1, tz=NY)
    if month == 12:
        month_end = pd.Timestamp(year=year + 1, month=1, day=1, tz=NY)
    else:
        month_end = pd.Timestamp(year=year, month=month + 1, day=1, tz=NY)

    weeks_in_month = [
        w for w in weekly.index
        if month_start <= weekly.loc[w, 'week_start'] < month_end
    ]
    if not weeks_in_month:
        return False

    segments: list[pd.DataFrame] = []
    for w in weeks_in_month:
        ws = weekly.loc[w, 'week_start']
        seg = week_hourly_slice(hourly, ws)
        if len(seg) >= 8:
            segments.append(seg)
    if not segments:
        return False

    fig, ax = plt.subplots(figsize=(22, 9), facecolor=BG)
    width_days = (60 / (24 * 60)) * 0.68

    for seg in segments:
        week = seg.index[0].to_period('W-SUN')
        ctx = week_context(weekly, week)
        if ctx is None:
            plot_candles(ax, seg, width_days)
            continue
        x0 = mdates.date2num(seg.index[0])
        x1 = mdates.date2num(seg.index[-1])
        pad = max((seg['high'].max() - seg['low'].min()) * 0.08, 20.0)
        y_clip = (float(seg['low'].min()) - pad, float(seg['high'].max()) + pad)
        draw_levels(ax, x0, x1, ctx, show_wo=True, y_clip=y_clip)
        plot_candles(ax, seg, width_days)
        ax.axvline(seg.index[0], color='#546E7A', linewidth=0.8, linestyle=':', alpha=0.55, zorder=1)

    all_bars = pd.concat(segments).sort_index()
    title = f"NQ 1h  ·  {year}-{month:02d}  ·  Sun–Fri weeks  ·  prior-week levels + WO±ATR bands"
    style_axes(ax, title)
    ax.set_ylabel('NQ', color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_ha('right')
    ax.set_xlim(all_bars.index[0] - pd.Timedelta(hours=4), all_bars.index[-1] + pd.Timedelta(hours=4))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return True


def build(
    *,
    output_root: Path,
    last_weeks: int | None,
    last_months: int | None,
    start: str | None,
    force: bool,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    week_dir = output_root / 'weeks'
    month_dir = output_root / 'months'
    week_dir.mkdir(parents=True, exist_ok=True)
    month_dir.mkdir(parents=True, exist_ok=True)

    dbn = POTIONS_ROOT / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    print(f'Loading NQ 1m ({dbn}) ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    if start:
        one_min = one_min[one_min.index >= pd.Timestamp(start, tz=NY)]
    hourly = resample_1h(one_min)
    daily_atr = build_daily_atr(hourly)
    weekly = build_weekly_table(hourly, daily_atr)
    print(f'  {len(weekly)} weekly periods, {len(hourly):,} 1h bars', flush=True)

    valid_weeks = [w for w in weekly.index if week_context(weekly, w) is not None]
    if last_weeks is not None:
        valid_weeks = valid_weeks[-last_weeks:]

    rows: list[dict] = []
    for i, w in enumerate(valid_weeks, start=1):
        ws = weekly.loc[w, 'week_start']
        rel = Path(str(ws.year)) / f'{ws.date().isoformat()}.png'
        ok = plot_week_chart(week_dir / rel, hourly, weekly, w)
        if ok:
            ctx = week_context(weekly, w)
            rows.append({
                'kind': 'week',
                'period': str(w),
                'week_start': ws.date().isoformat(),
                'chart': str(Path('weeks') / rel),
                'PWH': ctx['PWH'],
                'PWL': ctx['PWL'],
                'PWC': ctx['PWC'],
                'WO': ctx['WO'],
                'ATR': ctx.get('ATR'),
            })
        if i % 50 == 0:
            print(f'  weeks {i}/{len(valid_weeks)}', flush=True)

    month_keys = sorted({(weekly.loc[w, 'week_start'].year, weekly.loc[w, 'week_start'].month) for w in valid_weeks})
    if last_months is not None:
        month_keys = month_keys[-last_months:]

    month_rows: list[dict] = []
    for y, m in month_keys:
        rel = Path(f'{y}-{m:02d}.png')
        ok = plot_month_chart(month_dir / rel, hourly, weekly, y, m)
        if ok:
            month_rows.append({'kind': 'month', 'period': f'{y}-{m:02d}', 'chart': str(Path('months') / rel)})
        print(f'  month {y}-{m:02d}', flush=True)

    pd.DataFrame(rows + month_rows).to_csv(output_root / 'manifest.csv', index=False)
    lines = [
        '# NQ Weekly 1h Level Study',
        '',
        '**1-hour** NQ candles, **Sunday–Friday** (Saturday omitted; Friday clipped at 16:00 NY).',
        '',
        '### Levels (prior completed W-SUN week)',
        '- **PWH / PWL** — previous week high / low',
        '- **PWC / PWO** — previous week close / open',
        '- **PW 50%** — dashed midpoint of prior week range',
        '- **WO** — current week open (green)',
        '',
        '### ATR bands (shaded)',
        'Anchor = **current week open (WO)**. ATR = **daily ATR(14)** as of week open (causal: last completed day before the week).',
        'Shaded: WO±1 ATR (darker) and WO±2 ATR (lighter outer), clipped to the week’s price range for readability.',
        '',
        f'- Week charts: `{len(rows)}` under [`weeks/`](weeks/)',
        f'- Month charts: `{len(month_rows)}` under [`months/`](months/)',
        '',
        'Regenerate: `python3 nq/case_studies/build_nq_weekly_1h_level_study.py`',
    ]
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {output_root / "INDEX.md"}', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description='NQ 1h weekly level study charts')
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_weekly_1h_pwc_levels')
    ap.add_argument('--last-weeks', type=int, default=104, help='Most recent N weeks (default 104)')
    ap.add_argument('--last-months', type=int, default=36, help='Most recent N calendar months')
    ap.add_argument('--start', type=str, default='2020-01-01', help='Earliest 1m data (YYYY-MM-DD)')
    ap.add_argument('--all-weeks', action='store_true', help='All weeks (ignore --last-weeks)')
    ap.add_argument('--all-months', action='store_true', help='All months (ignore --last-months)')
    ap.add_argument('--no-force', action='store_true')
    args = ap.parse_args()
    build(
        output_root=args.output_root,
        last_weeks=None if args.all_weeks else args.last_weeks,
        last_months=None if args.all_months else args.last_months,
        start=args.start,
        force=not args.no_force,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
