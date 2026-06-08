#!/usr/bin/env python3
"""Next-day midnight-to-close 5-minute charts after yearly ORB breakouts.

Signal day:
- Jan-Mar defines the yearly opening range.
- From Apr-Dec, find daily candles that open inside that yearly range and
  close outside it.
- Bullish break: open is inside range and close > yearly OR high.
- Bearish break: open is inside range and close < yearly OR low.

Chart day:
- Use the next available trading day after the signal candle.
- Draw 00:00-16:00 ET 5-minute candles from 1-minute DBN data.
- Plot only the relevant yearly ORB boundary: upper boundary for bullish
  breaks, lower boundary for bearish breaks.
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
SESSION_START = time(0, 0)
SESSION_END = time(16, 0)


@dataclass(frozen=True)
class BreakoutEvent:
    market: str
    year: int
    symbol: str
    direction: str
    breakout_date: date
    chart_date: date
    range_high: float
    range_low: float
    range_size: float
    breakout_open: float
    breakout_close: float
    boundary: float


def period_groups(daily: pd.DataFrame) -> Iterable[tuple[int, pd.DataFrame]]:
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['year'] = work['date'].dt.year
    work['month'] = work['date'].dt.month
    for year, sub in work.groupby('year', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if (sub['month'] <= 3).any() and (sub['month'] > 3).any():
            yield int(year), sub


def find_events(daily_path: Path, market: str) -> list[BreakoutEvent]:
    daily = pd.read_csv(daily_path, parse_dates=['date'])
    events: list[BreakoutEvent] = []
    for year, bars in period_groups(daily):
        range_bars = bars[bars['month'] <= 3]
        trade_bars = bars[bars['month'] > 3].reset_index(drop=True)
        if range_bars.empty or trade_bars.empty:
            continue

        range_high = float(range_bars['high'].max())
        range_low = float(range_bars['low'].min())
        range_size = range_high - range_low
        if range_size <= 0:
            continue

        for idx, row in trade_bars.iterrows():
            next_rth_row = None
            for next_idx in range(idx + 1, len(trade_bars)):
                candidate = trade_bars.iloc[next_idx]
                if pd.Timestamp(candidate['date']).date().weekday() < 5:
                    next_rth_row = candidate
                    break
            if next_rth_row is None:
                continue
            open_px = float(row['open'])
            close_px = float(row['close'])
            opened_inside = range_low <= open_px <= range_high
            if not opened_inside:
                continue

            direction = ''
            boundary = 0.0
            if close_px > range_high:
                direction = 'Bullish'
                boundary = range_high
            elif close_px < range_low:
                direction = 'Bearish'
                boundary = range_low
            if not direction:
                continue

            events.append(
                BreakoutEvent(
                    market=market.upper(),
                    year=year,
                    symbol=str(row['symbol']),
                    direction=direction,
                    breakout_date=pd.Timestamp(row['date']).date(),
                    chart_date=pd.Timestamp(next_rth_row['date']).date(),
                    range_high=range_high,
                    range_low=range_low,
                    range_size=range_size,
                    breakout_open=open_px,
                    breakout_close=close_px,
                    boundary=boundary,
                )
            )
    return events


def load_front_month_rth_by_date(dbn_path: Path, product: str, wanted_dates: set[date]) -> dict[date, pd.DataFrame]:
    print(f'Loading {product} 1m DBN: {dbn_path}')
    store = db.DBNStore.from_file(str(dbn_path))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(product.upper())].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df = df[df['date'].isin(wanted_dates)].copy()
    if df.empty:
        return {}

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
    df = df[(df['t'] >= SESSION_START) & (df['t'] < SESSION_END)].copy()
    df = df.set_index('ts_event').sort_index()
    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f'  Loaded {len(by_date):,} chart day(s)')
    return by_date


def resample_5m_rth(df1: pd.DataFrame) -> pd.DataFrame:
    anchor = df1.index[0].normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
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
    width = 4.1 / (24 * 60)
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


def draw_chart(event: BreakoutEvent, df1: pd.DataFrame, out_path: Path) -> dict:
    bars5 = resample_5m_rth(df1)
    fig = plt.figure(figsize=(15, 8), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars5)

    line_color = '#4FC3F7' if event.direction == 'Bullish' else '#FFB74D'
    ax.axhline(event.boundary, color=line_color, linestyle='--', linewidth=1.25, zorder=2)
    label = 'Yearly OR High' if event.direction == 'Bullish' else 'Yearly OR Low'
    x_right = mdates.date2num(bars5.index[-1].tz_convert(None).to_pydatetime()) + 0.003
    ax.text(
        x_right,
        event.boundary,
        f' {label} {event.boundary:.2f}',
        color=line_color,
        fontsize=9,
        fontweight='bold',
        va='center',
    )

    day_open = float(bars5.iloc[0]['open'])
    day_close = float(bars5.iloc[-1]['close'])
    ax.scatter(
        [mdates.date2num(bars5.index[0].tz_convert(None).to_pydatetime())],
        [day_open],
        marker='o',
        color='#FFC107',
        s=75,
        zorder=10,
        edgecolor='black',
        linewidth=0.9,
    )
    ax.scatter(
        [mdates.date2num(bars5.index[-1].tz_convert(None).to_pydatetime())],
        [day_close],
        marker='X',
        color='#E0E0E0',
        s=75,
        zorder=10,
        edgecolor='black',
        linewidth=0.9,
    )

    title = (
        f'{event.market} {event.chart_date.isoformat()} 00:00-16:00 ET 5m after {event.direction.upper()} yearly ORB break '
        f'({event.breakout_date.isoformat()}) · boundary {event.boundary:.2f}'
    )
    subtitle = (
        f'Breakout daily O/C {event.breakout_open:.2f} -> {event.breakout_close:.2f} · '
        f'Yearly range {event.range_low:.2f} - {event.range_high:.2f} ({event.range_size:.2f})'
    )
    ax.set_title(title + '\n' + subtitle, color='white', fontsize=10, fontweight='bold', loc='left', pad=10)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    x0 = bars5.index[0].tz_convert(None) - pd.Timedelta(minutes=8)
    x1 = bars5.index[-1].tz_convert(None) + pd.Timedelta(minutes=18)
    ax.set_xlim(x0, x1)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)

    return {
        'market': event.market,
        'year': event.year,
        'direction': event.direction,
        'breakout_date': event.breakout_date.isoformat(),
        'chart_date': event.chart_date.isoformat(),
        'symbol': str(bars5.iloc[0]['symbol']),
        'range_high': event.range_high,
        'range_low': event.range_low,
        'boundary': event.boundary,
        'breakout_open': event.breakout_open,
        'breakout_close': event.breakout_close,
        'chart': f'{event.year}/{out_path.name}',
    }


def write_indexes(out_root: Path, market: str, rows: list[dict], missing: list[BreakoutEvent]) -> None:
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        by_year.setdefault(int(row['year']), []).append(row)

    for year, year_rows in sorted(by_year.items()):
        year_dir = out_root / str(year)
        lines = [
            f'# {market} {year} yearly ORB next-day 5m charts',
            '',
            '| Direction | Breakout Day | Chart Day | Boundary | Chart |',
            '|---|---:|---:|---:|---|',
        ]
        for row in sorted(year_rows, key=lambda x: (x['chart_date'], x['direction'])):
            chart_name = Path(row['chart']).name
            lines.append(
                f'| {row["direction"]} | {row["breakout_date"]} | {row["chart_date"]} | '
                f'{row["boundary"]:.2f} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    summary = [
        f'# {market} yearly ORB next-day 00:00-16:00 ET 5m charts',
        '',
        'Charts are generated for daily candles that opened inside the Jan-Mar yearly ORB and closed outside it. The chart shown is the next trading day from 00:00-16:00 ET, resampled from 1-minute DBN data to 5-minute candles.',
        '',
        'Only the relevant yearly ORB boundary is plotted: high for bullish breaks, low for bearish breaks.',
        '',
        f'Charts generated: {len(rows)}',
        f'Missing chart days in DBN: {len(missing)}',
        '',
        '| Year | Charts | Bullish | Bearish | Folder |',
        '|---:|---:|---:|---:|---|',
    ]
    for year, year_rows in sorted(by_year.items()):
        bullish = sum(1 for r in year_rows if r['direction'] == 'Bullish')
        bearish = sum(1 for r in year_rows if r['direction'] == 'Bearish')
        summary.append(f'| {year} | {len(year_rows)} | {bullish} | {bearish} | [{year}/]({year}/INDEX.md) |')
    summary.append('')
    if missing:
        summary.extend(['## Missing', '', '| Direction | Breakout Day | Chart Day |', '|---|---:|---:|'])
        for event in missing:
            summary.append(f'| {event.direction} | {event.breakout_date.isoformat()} | {event.chart_date.isoformat()} |')
        summary.append('')
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'INDEX.md').write_text('\n'.join(summary), encoding='utf-8')


def run(args: argparse.Namespace) -> pd.DataFrame:
    market = args.market.upper()
    events = find_events(args.daily, market)
    wanted = {event.chart_date for event in events}
    by_date = load_front_month_rth_by_date(args.dbn, market, wanted)
    rows: list[dict] = []
    missing: list[BreakoutEvent] = []

    for event in events:
        df1 = by_date.get(event.chart_date)
        if df1 is None or df1.empty:
            missing.append(event)
            continue
        direction_tag = 'bull' if event.direction == 'Bullish' else 'bear'
        name = f'{event.chart_date.isoformat()}_{direction_tag}_after_{event.breakout_date.isoformat()}.png'
        out_path = args.out / str(event.year) / name
        rows.append(draw_chart(event, df1, out_path))

    args.export_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(args.export_csv, index=False)
    write_indexes(args.out, market, rows, missing)
    print(f'{market}: events={len(events)} charts={len(rows)} missing={len(missing)}')
    print(f'Wrote {args.export_csv}')
    print(f'Wrote charts under {args.out}')
    return out_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', required=True)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--dbn', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
