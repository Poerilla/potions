#!/usr/bin/env python3
"""Daily and weekly RTH gap-fill study from 1-minute data.

Daily gap:
- previous trading day's 16:00 ET close, approximated by the 15:59 1-minute
  bar close;
- current trading day's 09:30 ET open;
- filled if price trades back to the prior 16:00 close during that same
  09:30-16:00 ET RTH session.

Weekly gap:
- previous week's final RTH close;
- first trading day's 09:30 ET open in the next week;
- filled if price trades back to the prior close any time from that 09:30
  open through Friday 23:59 ET of that same week.

The weekly chart set is 4-hour candles from the first trading day through
Friday, generated only when the weekly fill rate meets the configured
threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Iterable

import argparse

import databento as db
import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pytz


NY = pytz.timezone('America/New_York')
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class GapRow:
    market: str
    gap_type: str
    prev_close_date: date
    open_date: date
    direction: str
    prev_close: float
    open_px: float
    gap_pts: float
    abs_gap_pts: float
    filled: bool
    fill_time: pd.Timestamp | None
    chart: str = ''


def load_1m_source(path: Path) -> pd.DataFrame:
    if path.suffix == '.csv':
        return pd.read_csv(
            path,
            usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'],
            parse_dates=['ts_event'],
        )
    store = db.DBNStore.from_file(str(path))
    return store.to_df().reset_index()


def load_front_month_by_date(path: Path, product: str) -> dict[date, pd.DataFrame]:
    print(f'Loading {product} 1m source: {path}')
    df = load_1m_source(path)
    df = df[~df['symbol'].astype(str).str.contains('-', na=False)]
    df = df[df['symbol'].astype(str).str.startswith(product.upper())].copy()
    if df.empty:
        return {}

    if df['ts_event'].dt.tz is None:
        df['ts_event'] = df['ts_event'].dt.tz_localize('UTC')
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time

    front = (
        df.groupby(['date', 'symbol'])['volume']
        .sum()
        .groupby(level='date')
        .idxmax()
        .apply(lambda item: item[1])
        .to_dict()
    )
    df = df[df['symbol'].eq(df['date'].map(front))]
    df = df.set_index('ts_event').sort_index()
    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f'  Loaded {len(by_date):,} date(s)')
    return by_date


def rth_open_price(day: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    bars = day[(day.index.time >= RTH_OPEN) & (day.index.time < time(9, 31))]
    if bars.empty:
        bars = day[(day.index.time >= RTH_OPEN) & (day.index.time < RTH_CLOSE)]
    if bars.empty:
        return None
    row = bars.iloc[0]
    return float(row['open']), pd.Timestamp(bars.index[0])


def rth_close_price(day: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    bars = day[(day.index.time >= RTH_OPEN) & (day.index.time < RTH_CLOSE)]
    if bars.empty:
        return None
    row = bars.iloc[-1]
    return float(row['close']), pd.Timestamp(bars.index[-1])


def first_fill_time(window: pd.DataFrame, direction: str, prev_close: float) -> pd.Timestamp | None:
    if window.empty:
        return None
    if direction == 'Gap Up':
        hits = window[window['low'] <= prev_close]
    else:
        hits = window[window['high'] >= prev_close]
    if hits.empty:
        return None
    return pd.Timestamp(hits.index[0])


def build_daily_gaps(by_date: dict[date, pd.DataFrame], market: str) -> list[GapRow]:
    rows: list[GapRow] = []
    dates = sorted(by_date)
    for i in range(1, len(dates)):
        prev_d = dates[i - 1]
        cur_d = dates[i]
        if cur_d.weekday() >= 5:
            continue
        prev_close_pair = rth_close_price(by_date[prev_d])
        open_pair = rth_open_price(by_date[cur_d])
        if prev_close_pair is None or open_pair is None:
            continue
        prev_close, _ = prev_close_pair
        open_px, open_ts = open_pair
        gap_pts = open_px - prev_close
        if gap_pts == 0:
            continue
        direction = 'Gap Up' if gap_pts > 0 else 'Gap Down'
        window = by_date[cur_d][(by_date[cur_d].index >= open_ts) & (by_date[cur_d].index.time < RTH_CLOSE)]
        fill_ts = first_fill_time(window, direction, prev_close)
        rows.append(
            GapRow(
                market=market,
                gap_type='daily',
                prev_close_date=prev_d,
                open_date=cur_d,
                direction=direction,
                prev_close=prev_close,
                open_px=open_px,
                gap_pts=gap_pts,
                abs_gap_pts=abs(gap_pts),
                filled=fill_ts is not None,
                fill_time=fill_ts,
            )
        )
    return rows


def iso_week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return int(iso[0]), int(iso[1])


def build_weekly_gaps(by_date: dict[date, pd.DataFrame], market: str) -> list[GapRow]:
    rows: list[GapRow] = []
    dates = [d for d in sorted(by_date) if d.weekday() < 5 and rth_open_price(by_date[d]) is not None]
    by_week: dict[tuple[int, int], list[date]] = {}
    for d in dates:
        by_week.setdefault(iso_week_key(d), []).append(d)

    weeks = sorted(by_week)
    for i in range(1, len(weeks)):
        prev_week_dates = by_week[weeks[i - 1]]
        cur_week_dates = by_week[weeks[i]]
        if not prev_week_dates or not cur_week_dates:
            continue
        prev_d = prev_week_dates[-1]
        open_d = cur_week_dates[0]
        prev_close_pair = rth_close_price(by_date[prev_d])
        open_pair = rth_open_price(by_date[open_d])
        if prev_close_pair is None or open_pair is None:
            continue
        prev_close, _ = prev_close_pair
        open_px, open_ts = open_pair
        gap_pts = open_px - prev_close
        if gap_pts == 0:
            continue
        direction = 'Gap Up' if gap_pts > 0 else 'Gap Down'

        frames: list[pd.DataFrame] = []
        for d in cur_week_dates:
            if d.weekday() > 4:
                continue
            day = by_date[d]
            if d == open_d:
                day = day[day.index >= open_ts]
            frames.append(day)
        window = pd.concat(frames).sort_index() if frames else pd.DataFrame()
        fill_ts = first_fill_time(window, direction, prev_close)
        rows.append(
            GapRow(
                market=market,
                gap_type='weekly',
                prev_close_date=prev_d,
                open_date=open_d,
                direction=direction,
                prev_close=prev_close,
                open_px=open_px,
                gap_pts=gap_pts,
                abs_gap_pts=abs(gap_pts),
                filled=fill_ts is not None,
                fill_time=fill_ts,
            )
        )
    return rows


def rows_to_df(rows: list[GapRow]) -> pd.DataFrame:
    data = []
    for row in rows:
        data.append(
            {
                'market': row.market,
                'gap_type': row.gap_type,
                'prev_close_date': row.prev_close_date.isoformat(),
                'open_date': row.open_date.isoformat(),
                'direction': row.direction,
                'prev_close': row.prev_close,
                'open_px': row.open_px,
                'gap_pts': row.gap_pts,
                'abs_gap_pts': row.abs_gap_pts,
                'filled': int(row.filled),
                'fill_time': row.fill_time.isoformat() if row.fill_time is not None else '',
                'chart': row.chart,
            }
        )
    return pd.DataFrame(data)


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            'count': 0,
            'filled': 0,
            'fill_rate': 0.0,
            'median_gap': 0.0,
            'avg_gap': 0.0,
            'max_gap': 0.0,
        }
    count = int(len(df))
    filled = int(df['filled'].sum())
    return {
        'count': count,
        'filled': filled,
        'fill_rate': filled / count if count else 0.0,
        'median_gap': float(df['abs_gap_pts'].median()),
        'avg_gap': float(df['abs_gap_pts'].mean()),
        'max_gap': float(df['abs_gap_pts'].max()),
    }


def bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    labels = ['Q1 smallest', 'Q2', 'Q3', 'Q4 largest']
    work = df.copy()
    try:
        work['bucket'] = pd.qcut(work['abs_gap_pts'], q=4, labels=labels, duplicates='drop')
    except ValueError:
        work['bucket'] = 'all'
    out = (
        work.groupby('bucket', observed=True)
        .agg(
            count=('filled', 'size'),
            filled=('filled', 'sum'),
            fill_rate=('filled', 'mean'),
            min_gap=('abs_gap_pts', 'min'),
            median_gap=('abs_gap_pts', 'median'),
            max_gap=('abs_gap_pts', 'max'),
        )
        .reset_index()
    )
    return out


def resample_4h(df1: pd.DataFrame) -> pd.DataFrame:
    return (
        df1.resample('4h', label='left', closed='left', origin='start_day')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            volume=('volume', 'sum'),
            symbol=('symbol', 'last'),
        )
        .dropna(subset=['open'])
    )


def draw_candles(ax, bars: pd.DataFrame) -> None:
    xnums = mdates.date2num(bars.index.tz_convert(None).to_pydatetime())
    width = 3.1 / 24
    for x, (_, row) in zip(xnums, bars.iterrows()):
        open_px, high_px, low_px, close_px = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if close_px >= open_px else '#EF5350'
        ax.vlines(x, low_px, high_px, color=color, linewidth=0.9, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(open_px, close_px)),
                width,
                max(abs(close_px - open_px), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.96,
                zorder=4,
            )
        )


def weekly_chart_window(by_date: dict[date, pd.DataFrame], open_date: date) -> pd.DataFrame:
    week = iso_week_key(open_date)
    frames = []
    for d in sorted(by_date):
        if iso_week_key(d) != week or d.weekday() > 4:
            continue
        frames.append(by_date[d])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def draw_weekly_gap_chart(row: pd.Series, by_date: dict[date, pd.DataFrame], out_path: Path) -> str:
    open_d = pd.Timestamp(row['open_date']).date()
    df1 = weekly_chart_window(by_date, open_d)
    if df1.empty:
        return ''
    bars4h = resample_4h(df1)
    if bars4h.empty:
        return ''

    fig = plt.figure(figsize=(15, 8), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars4h)

    prev_close = float(row['prev_close'])
    open_px = float(row['open_px'])
    gap_pts = float(row['gap_pts'])
    filled = bool(row['filled'])
    line_color = '#FFD54F'
    open_color = '#4FC3F7' if gap_pts > 0 else '#FFB74D'
    ax.axhline(prev_close, color=line_color, linestyle='--', linewidth=1.35, zorder=2)
    ax.axhline(open_px, color=open_color, linestyle=':', linewidth=1.0, zorder=2)

    open_ts = pd.Timestamp.combine(open_d, RTH_OPEN).tz_localize(NY).tz_convert(None)
    ax.scatter(
        [mdates.date2num(open_ts.to_pydatetime())],
        [open_px],
        marker='o',
        color=open_color,
        s=75,
        zorder=10,
        edgecolor='black',
        linewidth=0.9,
    )

    if filled and isinstance(row['fill_time'], str) and row['fill_time']:
        fill_ts = pd.Timestamp(row['fill_time']).tz_convert(NY).tz_convert(None)
        ax.scatter(
            [mdates.date2num(fill_ts.to_pydatetime())],
            [prev_close],
            marker='X',
            color='#E0E0E0',
            s=90,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )

    x_right = mdates.date2num(bars4h.index[-1].tz_convert(None).to_pydatetime()) + 0.06
    ax.text(x_right, prev_close, f' Friday close {prev_close:.2f}', color=line_color, fontsize=9, va='center', fontweight='bold')
    ax.text(x_right, open_px, f' Week open {open_px:.2f}', color=open_color, fontsize=9, va='center')

    status = 'FILLED' if filled else 'OPEN'
    title = (
        f'{row["market"]} weekly RTH gap {row["open_date"]} {row["direction"]} {gap_pts:+.2f} pts - {status}'
    )
    subtitle = (
        f'Prev close {row["prev_close_date"]}: {prev_close:.2f} · 09:30 open {open_px:.2f} · '
        f'Fill time: {row["fill_time"] or "not filled this week"}'
    )
    ax.set_title(title + '\n' + subtitle, color='white', fontsize=10, fontweight='bold', loc='left', pad=10)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 12]))
    ax.tick_params(axis='x', which='minor', labelsize=0)
    x0 = bars4h.index[0].tz_convert(None) - pd.Timedelta(hours=4)
    x1 = bars4h.index[-1].tz_convert(None) + pd.Timedelta(hours=8)
    ax.set_xlim(x0, x1)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)
    return str(out_path)


def format_pct(x: float) -> str:
    return f'{x * 100:.1f}%'


def write_markdown(
    out_root: Path,
    market: str,
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    weekly_chart_rate_threshold: float,
    weekly_charts_generated: int,
) -> None:
    daily_s = summarize(daily_df)
    weekly_s = summarize(weekly_df)

    lines = [
        f'# {market} Hourly Gap Fill Study',
        '',
        'Definitions:',
        '',
        '- Daily gap: prior trading day 16:00 ET close to current day 09:30 ET open; filled if price trades back to the prior close during the same 09:30-16:00 ET RTH session.',
        '- Weekly gap: previous week final RTH close to first trading day 09:30 ET open; filled if price trades back to the prior close any time before the end of that trading week.',
        '- Fill detection uses the 1-minute source for exact high/low touches. Weekly inspection charts are 4-hour candles.',
        '',
        '## Summary',
        '',
        '| Gap Type | Gaps | Filled | Fill Rate | Median Gap | Avg Gap | Max Gap |',
        '|---|---:|---:|---:|---:|---:|---:|',
        f'| Daily | {daily_s["count"]} | {daily_s["filled"]} | {format_pct(daily_s["fill_rate"])} | {daily_s["median_gap"]:.2f} | {daily_s["avg_gap"]:.2f} | {daily_s["max_gap"]:.2f} |',
        f'| Weekly | {weekly_s["count"]} | {weekly_s["filled"]} | {format_pct(weekly_s["fill_rate"])} | {weekly_s["median_gap"]:.2f} | {weekly_s["avg_gap"]:.2f} | {weekly_s["max_gap"]:.2f} |',
        '',
        '## Daily Gap By Direction',
        '',
        '| Direction | Gaps | Filled | Fill Rate | Median Gap |',
        '|---|---:|---:|---:|---:|',
    ]
    for direction, sub in daily_df.groupby('direction', sort=True):
        s = summarize(sub)
        lines.append(f'| {direction} | {s["count"]} | {s["filled"]} | {format_pct(s["fill_rate"])} | {s["median_gap"]:.2f} |')

    lines.extend(['', '## Weekly Gap By Direction', '', '| Direction | Gaps | Filled | Fill Rate | Median Gap |', '|---|---:|---:|---:|---:|'])
    for direction, sub in weekly_df.groupby('direction', sort=True):
        s = summarize(sub)
        lines.append(f'| {direction} | {s["count"]} | {s["filled"]} | {format_pct(s["fill_rate"])} | {s["median_gap"]:.2f} |')

    for label, df in [('Daily', daily_df), ('Weekly', weekly_df)]:
        buckets = bucket_summary(df)
        lines.extend(['', f'## {label} Gap Size Buckets', '', '| Bucket | Gaps | Filled | Fill Rate | Min Gap | Median Gap | Max Gap |', '|---|---:|---:|---:|---:|---:|---:|'])
        for _, row in buckets.iterrows():
            lines.append(
                f'| {row["bucket"]} | {int(row["count"])} | {int(row["filled"])} | {format_pct(float(row["fill_rate"]))} | '
                f'{float(row["min_gap"]):.2f} | {float(row["median_gap"]):.2f} | {float(row["max_gap"]):.2f} |'
            )

    lines.extend(
        [
            '',
            '## Weekly 4-Hour Charts',
            '',
            f'Weekly chart threshold: {format_pct(weekly_chart_rate_threshold)} fill rate.',
            f'Charts generated: {weekly_charts_generated}.',
        ]
    )
    if weekly_charts_generated:
        lines.append('')
        lines.append('Charts are under `weekly_gap_4h/`, organized by year. They include the week-open 09:30 marker, the prior Friday/previous-week RTH close line, and the first fill marker when present.')

    lines.extend(
        [
            '',
            '## Files',
            '',
            '- `daily_gap_fills.csv`',
            '- `weekly_gap_fills.csv`',
            '- `README.md`',
        ]
    )
    if weekly_charts_generated:
        lines.append('- `weekly_gap_4h/INDEX.md`')
    lines.append('')

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def write_weekly_chart_indexes(out_root: Path, market: str, weekly_df: pd.DataFrame) -> None:
    charted = weekly_df[weekly_df['chart'].astype(str).ne('')].copy()
    if charted.empty:
        return
    chart_root = out_root / 'weekly_gap_4h'
    charted['year'] = pd.to_datetime(charted['open_date']).dt.year
    for year, sub in charted.groupby('year', sort=True):
        year_dir = chart_root / str(int(year))
        lines = [
            f'# {market} {int(year)} weekly gap 4h charts',
            '',
            '| Week Open | Direction | Gap Pts | Filled | Fill Time | Chart |',
            '|---:|---|---:|---:|---:|---|',
        ]
        for _, row in sub.sort_values('open_date').iterrows():
            chart_name = Path(str(row['chart'])).name
            filled = 'yes' if int(row['filled']) else 'no'
            fill_time = str(row['fill_time']) if str(row['fill_time']) else ''
            lines.append(
                f'| {row["open_date"]} | {row["direction"]} | {float(row["gap_pts"]):+.2f} | '
                f'{filled} | {fill_time} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    root_lines = [
        f'# {market} weekly gap 4h charts',
        '',
        'Charts show the first trading week after the prior-week RTH close to current-week 09:30 ET open gap.',
        '',
        '| Year | Charts | Filled | Open | Folder |',
        '|---:|---:|---:|---:|---|',
    ]
    for year, sub in charted.groupby('year', sort=True):
        filled = int(sub['filled'].sum())
        total = int(len(sub))
        root_lines.append(
            f'| {int(year)} | {total} | {filled} | {total - filled} | [{int(year)}/]({int(year)}/INDEX.md) |'
        )
    root_lines.append('')
    (chart_root / 'INDEX.md').write_text('\n'.join(root_lines), encoding='utf-8')


def run(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    market = args.market.upper()
    by_date = load_front_month_by_date(args.source_1m, market)
    out_root = args.out
    out_root.mkdir(parents=True, exist_ok=True)

    daily_rows = build_daily_gaps(by_date, market)
    weekly_rows = build_weekly_gaps(by_date, market)
    daily_df = rows_to_df(daily_rows)
    weekly_df = rows_to_df(weekly_rows)

    weekly_rate = summarize(weekly_df)['fill_rate']
    weekly_charts_generated = 0
    if weekly_rate >= args.weekly_chart_threshold and not weekly_df.empty:
        chart_paths = []
        for _, row in weekly_df.iterrows():
            open_d = pd.Timestamp(row['open_date']).date()
            year = open_d.year
            direction_tag = 'up' if row['direction'] == 'Gap Up' else 'down'
            status_tag = 'filled' if int(row['filled']) else 'open'
            name = f'{open_d.isoformat()}_{direction_tag}_{status_tag}_4h.png'
            out_path = out_root / 'weekly_gap_4h' / str(year) / name
            path = draw_weekly_gap_chart(row, by_date, out_path)
            rel = str(Path(path).relative_to(out_root)) if path else ''
            chart_paths.append(rel)
        weekly_df['chart'] = chart_paths
        weekly_charts_generated = sum(1 for p in chart_paths if p)

    daily_df.to_csv(out_root / 'daily_gap_fills.csv', index=False)
    weekly_df.to_csv(out_root / 'weekly_gap_fills.csv', index=False)
    write_weekly_chart_indexes(out_root, market, weekly_df)
    write_markdown(out_root, market, daily_df, weekly_df, args.weekly_chart_threshold, weekly_charts_generated)

    print(
        f'{market}: daily gaps={len(daily_df)} filled={int(daily_df["filled"].sum()) if not daily_df.empty else 0}; '
        f'weekly gaps={len(weekly_df)} filled={int(weekly_df["filled"].sum()) if not weekly_df.empty else 0}; '
        f'weekly charts={weekly_charts_generated}'
    )
    print(f'Wrote {out_root / "README.md"}')
    return daily_df, weekly_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', required=True)
    ap.add_argument('--source-1m', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--weekly-chart-threshold', type=float, default=0.50)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
