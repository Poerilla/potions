#!/usr/bin/env python3
"""Multi-day 1-hour context charts after yearly ORB breakouts.

Signal day:
- Jan-Mar defines the yearly opening range.
- From Apr-Dec, find daily candles that open inside that yearly range and
  close outside it.
- Bullish break: open is inside range and close > yearly OR high.
- Bearish break: open is inside range and close < yearly OR low.

Chart window:
- Include the breakout date and the next five weekday trading dates from
  the daily file.
- Draw 00:00-23:59 ET price action for each included date, including the
  evening/Asian session hours through the 23:00 candle.
- Resample from 1-minute DBN/CSV data to 1-hour candles.
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
SESSION_END = time(23, 59, 59)


@dataclass(frozen=True)
class BreakoutEvent:
    market: str
    year: int
    symbol: str
    direction: str
    breakout_date: date
    chart_dates: tuple[date, ...]
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


def chart_dates_for_event(trade_bars: pd.DataFrame, idx: int, count_after: int) -> tuple[date, ...]:
    row_date = pd.Timestamp(trade_bars.iloc[idx]['date']).date()
    dates: list[date] = [row_date]
    for next_idx in range(idx + 1, len(trade_bars)):
        candidate_date = pd.Timestamp(trade_bars.iloc[next_idx]['date']).date()
        if candidate_date.weekday() >= 5:
            continue
        dates.append(candidate_date)
        if len(dates) >= count_after + 1:
            break
    return tuple(dates)


def find_events(daily_path: Path, market: str, count_after: int) -> list[BreakoutEvent]:
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

            dates = chart_dates_for_event(trade_bars, idx, count_after)
            if len(dates) <= 1:
                continue

            events.append(
                BreakoutEvent(
                    market=market.upper(),
                    year=year,
                    symbol=str(row['symbol']),
                    direction=direction,
                    breakout_date=pd.Timestamp(row['date']).date(),
                    chart_dates=dates,
                    range_high=range_high,
                    range_low=range_low,
                    range_size=range_size,
                    breakout_open=open_px,
                    breakout_close=close_px,
                    boundary=boundary,
                )
            )
    return events


def normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'symbol': 'symbol',
        'ts_event': 'ts_event',
    }
    return df.rename(columns=rename)


def load_1m_source(path: Path) -> pd.DataFrame:
    if path.suffix == '.csv':
        df = pd.read_csv(
            path,
            usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'],
            parse_dates=['ts_event'],
        )
    else:
        store = db.DBNStore.from_file(str(path))
        df = store.to_df().reset_index()
    return normalize_ohlcv_columns(df)


def load_front_month_by_date(path: Path, product: str, wanted_dates: set[date]) -> dict[date, pd.DataFrame]:
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
    df = df[(df['t'] >= SESSION_START) & (df['t'] <= SESSION_END)].copy()
    df = df.set_index('ts_event').sort_index()
    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f'  Loaded {len(by_date):,} chart date(s)')
    return by_date


def resample_1h(df1: pd.DataFrame) -> pd.DataFrame:
    return (
        df1.resample('1h', label='left', closed='left', origin='start_day')
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
    width = 45.0 / (24 * 60)
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


def combine_event_data(event: BreakoutEvent, by_date: dict[date, pd.DataFrame]) -> pd.DataFrame:
    frames = [by_date[d] for d in event.chart_dates if d in by_date and not by_date[d].empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def draw_chart(event: BreakoutEvent, df1: pd.DataFrame, out_path: Path) -> dict:
    bars1h = resample_1h(df1)
    fig = plt.figure(figsize=(18, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars1h)

    line_color = '#4FC3F7' if event.direction == 'Bullish' else '#FFB74D'
    ax.axhline(event.boundary, color=line_color, linestyle='--', linewidth=1.35, zorder=2)
    label = 'Yearly OR High' if event.direction == 'Bullish' else 'Yearly OR Low'
    x_right = mdates.date2num(bars1h.index[-1].tz_convert(None).to_pydatetime()) + 0.05
    ax.text(
        x_right,
        event.boundary,
        f' {label} {event.boundary:.2f}',
        color=line_color,
        fontsize=9,
        fontweight='bold',
        va='center',
    )

    present_dates = sorted({pd.Timestamp(ts).date() for ts in bars1h.index})
    for idx, d in enumerate(present_dates):
        left = pd.Timestamp.combine(d, SESSION_START).tz_localize(NY).tz_convert(None)
        right = pd.Timestamp.combine(d, SESSION_END).tz_localize(NY).tz_convert(None)
        ax.axvline(left, color='#9FB3C8', linewidth=0.6, alpha=0.25, zorder=1)
        if idx % 2 == 0:
            ax.axvspan(left, right, color='white', alpha=0.025, zorder=0)

    breakout_bars = bars1h[[pd.Timestamp(ts).date() == event.breakout_date for ts in bars1h.index]]
    if not breakout_bars.empty:
        close_bar = breakout_bars.iloc[-1]
        close_ts = breakout_bars.index[-1]
        ax.scatter(
            [mdates.date2num(close_ts.tz_convert(None).to_pydatetime())],
            [float(close_bar['close'])],
            marker='X',
            color='#FFD54F',
            s=90,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )
        ax.text(
            mdates.date2num(close_ts.tz_convert(None).to_pydatetime()),
            float(close_bar['close']),
            ' breakout close',
            color='#FFD54F',
            fontsize=8,
            va='bottom',
            ha='left',
        )

    title = (
        f'{event.market} {event.breakout_date.isoformat()} +5 trading days 1h context '
        f'after {event.direction.upper()} yearly ORB break'
    )
    subtitle = (
        f'Daily breakout O/C {event.breakout_open:.2f} -> {event.breakout_close:.2f} · '
        f'Yearly range {event.range_low:.2f} - {event.range_high:.2f} ({event.range_size:.2f}) · '
        f'boundary {event.boundary:.2f}'
    )
    ax.set_title(title + '\n' + subtitle, color='white', fontsize=10, fontweight='bold', loc='left', pad=10)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    ax.tick_params(axis='x', which='minor', labelsize=0)

    x0 = bars1h.index[0].tz_convert(None) - pd.Timedelta(hours=2)
    x1 = bars1h.index[-1].tz_convert(None) + pd.Timedelta(hours=4)
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
        'chart_start': min(present_dates).isoformat(),
        'chart_end': max(present_dates).isoformat(),
        'dates_requested': ','.join(d.isoformat() for d in event.chart_dates),
        'dates_loaded': ','.join(d.isoformat() for d in present_dates),
        'symbol': str(bars1h.iloc[0]['symbol']),
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
            f'# {market} {year} yearly ORB breakout +5 day 1h charts',
            '',
            '| Direction | Breakout Day | Chart Window | Boundary | Chart |',
            '|---|---:|---:|---:|---|',
        ]
        for row in sorted(year_rows, key=lambda x: (x['breakout_date'], x['direction'])):
            chart_name = Path(row['chart']).name
            lines.append(
                f'| {row["direction"]} | {row["breakout_date"]} | {row["chart_start"]} -> {row["chart_end"]} | '
                f'{row["boundary"]:.2f} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    summary = [
        f'# {market} yearly ORB breakout day + five trading days 1h charts',
        '',
        'Charts are generated for daily candles that opened inside the Jan-Mar yearly ORB and closed outside it. Each chart includes the breakout date plus the next five weekday trading dates, using 00:00-23:59 ET 1-hour candles resampled from 1-minute DBN/CSV data.',
        '',
        'Only the relevant yearly ORB boundary is plotted: high for bullish breaks, low for bearish breaks. The yellow X marks the last plotted hourly candle on the breakout date.',
        '',
        f'Charts generated: {len(rows)}',
        f'Missing chart windows in 1m source: {len(missing)}',
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
        summary.extend(['## Missing', '', '| Direction | Breakout Day | Requested Dates |', '|---|---:|---|'])
        for event in missing:
            requested = ', '.join(d.isoformat() for d in event.chart_dates)
            summary.append(f'| {event.direction} | {event.breakout_date.isoformat()} | {requested} |')
        summary.append('')
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'INDEX.md').write_text('\n'.join(summary), encoding='utf-8')


def run(args: argparse.Namespace) -> pd.DataFrame:
    market = args.market.upper()
    events = find_events(args.daily, market, args.days_after)
    wanted = {d for event in events for d in event.chart_dates}
    by_date = load_front_month_by_date(args.source_1m, market, wanted)
    rows: list[dict] = []
    missing: list[BreakoutEvent] = []

    for event in events:
        df1 = combine_event_data(event, by_date)
        if df1.empty:
            missing.append(event)
            continue
        direction_tag = 'bull' if event.direction == 'Bullish' else 'bear'
        name = f'{event.breakout_date.isoformat()}_{direction_tag}_plus{args.days_after}_1h.png'
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
    ap.add_argument('--source-1m', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    ap.add_argument('--days-after', type=int, default=5)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
