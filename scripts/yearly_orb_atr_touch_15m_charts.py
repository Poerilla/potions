#!/usr/bin/env python3
"""15-minute charts for yearly ORB ATR trailing-stop touch days.

Study filter:
- Build yearly ORB from Jan-Mar daily bars.
- After the first yearly ORB breakout:
  - Bullish yearly breakout: chart days where price trades down to the daily
    Supertrend-style ATR trailing stop.
  - Bearish yearly breakout: chart days where price trades up to the daily
    Supertrend-style ATR trailing stop.
- Use 1-minute data to draw a 15-minute intraday chart for each touch day.

The ATR stop is daily ATR(14) x 3 by default, matching the visual research
overlay in yearly_orb_delivery_research_charts.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

import argparse

import databento as db
import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from yearly_orb_delivery_research_charts import calculate_daily_atr_trailing_stop


NY = 'America/New_York'
BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
CYAN = '#00BCD4'
ORANGE = '#FF9800'
RANGE = '#E0E0E0'


@dataclass
class TouchDay:
    period: str
    day: date
    symbol: str
    breakout_direction: str
    breakout_date: pd.Timestamp
    range_high: float
    range_low: float
    atr_stop: float
    atr_trend: str
    daily_open: float
    daily_high: float
    daily_low: float
    daily_close: float


def load_1m_source(path: Path) -> pd.DataFrame:
    if path.suffix == '.csv':
        raw = pd.read_csv(
            path,
            usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'],
            parse_dates=['ts_event'],
        )
    else:
        raw = db.DBNStore.from_file(str(path)).to_df().reset_index()
    raw = raw[['ts_event', 'symbol', 'open', 'high', 'low', 'close', 'volume']].copy()
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw['date'] = raw['ts_event'].dt.date
    raw = raw[~raw['symbol'].astype(str).str.contains('-', na=False)].copy()
    return raw.sort_values('ts_event').reset_index(drop=True)


def first_breakout(work: pd.DataFrame, range_high: float, range_low: float) -> tuple[int | None, str | None]:
    for idx, row in work[work['month'] > 3].iterrows():
        c = float(row['close'])
        if c > range_high:
            return int(idx), 'Long'
        if c < range_low:
            return int(idx), 'Short'
    return None, None


def find_touch_days(daily: pd.DataFrame, atr_length: int, atr_multiplier: float) -> list[TouchDay]:
    rows: list[TouchDay] = []
    daily = daily.copy().sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])
    daily['year'] = daily['date'].dt.year

    for year, bars in daily.groupby('year', sort=True):
        work = bars.sort_values('date').reset_index(drop=True)
        work['month'] = work['date'].dt.month
        range_bars = work[work['month'] <= 3]
        trade_bars = work[work['month'] > 3]
        if range_bars.empty or trade_bars.empty:
            continue
        range_high = float(range_bars['high'].max())
        range_low = float(range_bars['low'].min())
        breakout_idx, direction = first_breakout(work, range_high, range_low)
        if breakout_idx is None or direction is None:
            continue

        atr_work = calculate_daily_atr_trailing_stop(work, atr_length, atr_multiplier)
        breakout_date = pd.Timestamp(work.loc[breakout_idx, 'date'])
        for idx, row in atr_work.iloc[breakout_idx + 1 :].iterrows():
            stop = row.get('atr_stop')
            trend = row.get('atr_trend')
            if pd.isna(stop):
                continue
            stop = float(stop)
            high = float(row['high'])
            low = float(row['low'])
            if not (low <= stop <= high):
                continue
            if direction == 'Long' and trend != 'up':
                continue
            if direction == 'Short' and trend != 'down':
                continue
            rows.append(
                TouchDay(
                    period=str(int(year)),
                    day=pd.Timestamp(row['date']).date(),
                    symbol=str(row['symbol']),
                    breakout_direction=direction,
                    breakout_date=breakout_date,
                    range_high=range_high,
                    range_low=range_low,
                    atr_stop=stop,
                    atr_trend=str(trend),
                    daily_open=float(row['open']),
                    daily_high=high,
                    daily_low=low,
                    daily_close=float(row['close']),
                )
            )
    return rows


def resample_15m(day: pd.DataFrame) -> pd.DataFrame:
    if day.empty:
        return day
    work = day.copy().set_index('ts_event').sort_index()
    bars = (
        work.resample('15min', label='left', closed='left', origin='start_day')
        .agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
        .dropna(subset=['open', 'high', 'low', 'close'])
        .reset_index()
    )
    bars['date'] = bars['ts_event'].dt.date
    return bars


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    x = mdates.date2num(pd.to_datetime(bars['ts_event']))
    if len(x) > 1:
        width = min((x[1] - x[0]) * 0.72, 0.008)
    else:
        width = 0.006
    for xval, (_, row) in zip(x, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=col, linewidth=0.8, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (xval - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, alpha=0.15, color=GRID)
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')


def chart_touch_day(touch: TouchDay, raw_day: pd.DataFrame, out_path: Path, market: str) -> dict:
    bars = resample_15m(raw_day)
    if bars.empty:
        return {
            'period': touch.period,
            'date': touch.day.isoformat(),
            'symbol': touch.symbol,
            'direction': touch.breakout_direction,
            'atr_stop': touch.atr_stop,
            'chart': '',
            'status': 'missing_raw',
        }

    stop = touch.atr_stop
    if touch.breakout_direction == 'Long':
        touch_bars = bars[(bars['low'].astype(float) <= stop) & (bars['high'].astype(float) >= stop)].copy()
        favorable_bars = bars[bars['close'].astype(float) >= stop].copy()
        touch_favorable = touch_bars[touch_bars['close'].astype(float) >= stop].copy()
        adverse_bars = bars[bars['close'].astype(float) < stop].copy()
    else:
        touch_bars = bars[(bars['high'].astype(float) >= stop) & (bars['low'].astype(float) <= stop)].copy()
        favorable_bars = bars[bars['close'].astype(float) <= stop].copy()
        touch_favorable = touch_bars[touch_bars['close'].astype(float) <= stop].copy()
        adverse_bars = bars[bars['close'].astype(float) > stop].copy()

    if not touch_bars.empty:
        first_touch_time = pd.Timestamp(touch_bars.iloc[0]['ts_event'])
        post_touch = bars[bars['ts_event'] >= first_touch_time].copy()
    else:
        first_touch_time = None
        post_touch = bars.iloc[0:0].copy()
    if touch.breakout_direction == 'Long':
        post_favorable = post_touch[post_touch['close'].astype(float) >= stop].copy()
        post_close_over = post_touch[post_touch['close'].astype(float) >= stop].copy()
    else:
        post_favorable = post_touch[post_touch['close'].astype(float) <= stop].copy()
        post_close_over = post_touch[post_touch['close'].astype(float) >= stop].copy()

    fig = plt.figure(figsize=(16, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, bars)

    stop_color = CYAN if touch.breakout_direction == 'Long' else ORANGE
    ax.axhline(stop, color=stop_color, linewidth=1.25, alpha=0.95, zorder=4)
    ax.axhline(touch.range_high, color=RANGE, linestyle='--', linewidth=0.75, alpha=0.55, zorder=2)
    ax.axhline(touch.range_low, color=RANGE, linestyle='--', linewidth=0.75, alpha=0.55, zorder=2)
    ax.axhspan(touch.range_low, touch.range_high, color='#1F4E79', alpha=0.07, zorder=0)

    for tmark, label, color in [
        (time(9, 30), '09:30', '#90CAF9'),
        (time(16, 0), '16:00', '#90CAF9'),
    ]:
        xs = bars[bars['ts_event'].dt.time == tmark]
        if not xs.empty:
            xval = mdates.date2num(pd.Timestamp(xs.iloc[0]['ts_event']))
            ax.axvline(xval, color=color, linestyle=':', linewidth=0.75, alpha=0.55, zorder=1)
            ax.text(xval, ax.get_ylim()[1], label, color=color, fontsize=7, va='top', ha='left')

    if not touch_bars.empty:
        ax.scatter(
            mdates.date2num(pd.to_datetime(touch_bars['ts_event'])),
            [stop] * len(touch_bars),
            marker='o',
            s=50,
            color='#FFD54F',
            edgecolor='black',
            linewidth=0.55,
            zorder=10,
            label='15m touched ATR stop',
        )
    if not touch_favorable.empty:
        ax.scatter(
            mdates.date2num(pd.to_datetime(touch_favorable['ts_event'])),
            touch_favorable['close'].astype(float),
            marker='^' if touch.breakout_direction == 'Long' else 'v',
            s=62,
            color='#00E676',
            edgecolor='black',
            linewidth=0.55,
            zorder=11,
            label='touch bar favorable close',
        )
    if not adverse_bars.empty:
        shown = adverse_bars[adverse_bars['ts_event'].isin(touch_bars['ts_event'])].copy()
        if not shown.empty:
            ax.scatter(
                mdates.date2num(pd.to_datetime(shown['ts_event'])),
                shown['close'].astype(float),
                marker='x',
                s=60,
                color='#FF5252',
                linewidth=1.2,
                zorder=11,
                label='touch bar adverse close',
            )

    dates = pd.to_datetime(bars['ts_event'])
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=8, maxticks=14))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=dates.dt.tz))
    ax.set_xlim(dates.iloc[0], dates.iloc[-1])
    title = (
        f'{market} {touch.day.isoformat()} 15m ATR touch · yearly ORB {touch.breakout_direction} '
        f'({touch.breakout_date.date().isoformat()}) · stop {stop:.2f} · '
        f'touch bars {len(touch_bars)} · touch favorable closes {len(touch_favorable)} · '
        f'post-touch favorable closes {len(post_favorable)} · post-touch close-over {len(post_close_over)}'
    )
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', loc='left', pad=8)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)

    return {
        'period': touch.period,
        'date': touch.day.isoformat(),
        'symbol': touch.symbol,
        'direction': touch.breakout_direction,
        'breakout_date': touch.breakout_date.date().isoformat(),
        'atr_stop': round(stop, 6),
        'atr_trend': touch.atr_trend,
        'daily_open': touch.daily_open,
        'daily_high': touch.daily_high,
        'daily_low': touch.daily_low,
        'daily_close': touch.daily_close,
        'touch_15m_bars': int(len(touch_bars)),
        'touch_favorable_close_15m_bars': int(len(touch_favorable)),
        'post_touch_favorable_close_15m_bars': int(len(post_favorable)),
        'post_touch_close_over_stop_15m_bars': int(len(post_close_over)),
        'first_touch_time': first_touch_time.isoformat() if first_touch_time is not None else '',
        'chart': str(out_path.relative_to(out_path.parents[2])),
        'status': 'charted',
    }


def write_index(out_root: Path, rows: list[dict], market: str, atr_length: int, atr_multiplier: float) -> None:
    traded = [row for row in rows if row['status'] == 'charted']
    long_rows = [row for row in traded if row['direction'] == 'Long']
    short_rows = [row for row in traded if row['direction'] == 'Short']

    lines = [
        f'# {market} yearly ORB ATR touch 15m study',
        '',
        f'Filter: daily ATR({atr_length}) x {atr_multiplier:g} Supertrend-style stop after first yearly ORB breakout.',
        '',
        'Bullish yearly breakout: chart days where price traded down to the bullish ATR trail. Bearish yearly breakout: chart days where price traded up to the bearish ATR trail.',
        '',
        'Counts are from 15-minute candles built from 1-minute data. Favorable close means close back above the stop for bullish breakout days and close back below the stop for bearish breakout days. `close-over` is literal close above the stop, included because it is useful on bearish tests.',
        '',
        f'Total charted days: {len(traded)}  ·  Bullish-breakout touch days: {len(long_rows)}  ·  Bearish-breakout touch days: {len(short_rows)}',
        '',
        '| Year | Date | Direction | Symbol | ATR Stop | Touch 15m Bars | Touch Favorable Closes | Post-Touch Favorable Closes | Post-Touch Close-Over | First Touch | Chart |',
        '|---:|---|---|---|---:|---:|---:|---:|---:|---|---|',
    ]
    for row in sorted(traded, key=lambda x: (x['date'], x['direction'])):
        lines.append(
            f'| {row["period"]} | {row["date"]} | {row["direction"]} | {row["symbol"]} | {row["atr_stop"]:.2f} | {row["touch_15m_bars"]} | {row["touch_favorable_close_15m_bars"]} | {row["post_touch_favorable_close_15m_bars"]} | {row["post_touch_close_over_stop_15m_bars"]} | {row["first_touch_time"]} | [{Path(row["chart"]).name}]({row["chart"]}) |'
        )
    lines.append('')
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def run(args: argparse.Namespace) -> pd.DataFrame:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]
    touch_days = find_touch_days(daily, args.atr_length, args.atr_multiplier)
    needed_dates = {touch.day for touch in touch_days}
    if not needed_dates:
        args.out.mkdir(parents=True, exist_ok=True)
        result = pd.DataFrame()
        result.to_csv(args.export_csv, index=False)
        write_index(args.out, [], args.market.upper(), args.atr_length, args.atr_multiplier)
        return result

    raw = load_1m_source(args.source_1m)
    raw = raw[raw['date'].isin(needed_dates)].copy()
    if args.market:
        raw = raw[raw['symbol'].astype(str).str.startswith(args.market.upper())].copy()
    by_key = {key: group.sort_values('ts_event') for key, group in raw.groupby(['date', 'symbol'], sort=False)}

    rows: list[dict] = []
    for i, touch in enumerate(touch_days, 1):
        raw_day = by_key.get((touch.day, touch.symbol), pd.DataFrame())
        if raw_day.empty:
            same_day = raw[raw['date'].eq(touch.day)].copy()
            if not same_day.empty:
                front_symbol = same_day.groupby('symbol')['volume'].sum().sort_values(ascending=False).index[0]
                raw_day = same_day[same_day['symbol'].eq(front_symbol)].copy()
        out_dir = 'bullish_breakout' if touch.breakout_direction == 'Long' else 'bearish_breakout'
        out_path = args.out / out_dir / touch.period / f'{touch.day.isoformat()}_{touch.breakout_direction.lower()}_atr_touch.png'
        rows.append(chart_touch_day(touch, raw_day, out_path, args.market.upper()))
        if i % 25 == 0:
            print(f'  Charted {i}/{len(touch_days)} touch days')

    result = pd.DataFrame(rows)
    args.export_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.export_csv, index=False)
    write_index(args.out, rows, args.market.upper(), args.atr_length, args.atr_multiplier)
    print(f'Wrote {len(result)} rows to {args.export_csv}')
    print(f'Wrote charts/index under {args.out}')
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--source-1m', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    ap.add_argument('--market', type=str, default='MNQ')
    ap.add_argument('--atr-length', type=int, default=14)
    ap.add_argument('--atr-multiplier', type=float, default=3.0)
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
