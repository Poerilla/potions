#!/usr/bin/env python3
"""Weekly candle charts with weekly and monthly ATR Supertrend overlays."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from yearly_orb_delivery_research_charts import calculate_supertrend_stop


ROOT = Path(__file__).resolve().parents[1]

MARKETS = {
    'mnq': {
        'label': 'MNQ',
        'daily': ROOT / 'mnq' / 'mnq_daily.csv',
        'out': ROOT / 'mnq' / 'case_studies' / 'atr_supertrend_htf_visuals' / 'weekly_monthly_combo',
    },
    'nq': {
        'label': 'NQ',
        'daily': ROOT / 'nq' / 'nq_daily.csv',
        'out': ROOT / 'nq' / 'case_studies' / 'atr_supertrend_htf_visuals' / 'weekly_monthly_combo',
    },
}

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'
WEEKLY_UP = '#00BCD4'
WEEKLY_DOWN = '#FF9800'
MONTHLY_UP = '#B2FF59'
MONTHLY_DOWN = '#FF5252'


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, alpha=0.15, color=GRID)
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')


def aggregate_ohlc(daily: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    work = daily.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    if timeframe == 'weekly':
        work['_period'] = work['date'].dt.to_period('W-FRI')
    elif timeframe == 'monthly':
        work['_period'] = work['date'].dt.to_period('M')
    else:
        raise ValueError(f'unsupported timeframe: {timeframe}')

    rows: list[dict] = []
    for period, group in work.groupby('_period', sort=True):
        group = group.sort_values('date')
        rows.append(
            {
                'period': period,
                'date': pd.Timestamp(group['date'].iloc[-1]),
                'open': float(group['open'].iloc[0]),
                'high': float(group['high'].max()),
                'low': float(group['low'].min()),
                'close': float(group['close'].iloc[-1]),
                'volume': float(group['volume'].sum()) if 'volume' in group.columns else 0.0,
                'symbol': str(group['symbol'].iloc[-1]) if 'symbol' in group.columns else '',
            }
        )
    return pd.DataFrame(rows)


def map_monthly_stop_to_weekly(weekly: pd.DataFrame, monthly: pd.DataFrame, length: int, multiplier: float) -> pd.DataFrame:
    monthly_st = calculate_supertrend_stop(monthly[['date', 'open', 'high', 'low', 'close']].copy(), length, multiplier)
    monthly_st['period'] = monthly['period'].values
    monthly_plot = monthly_st[['period', 'atr_stop', 'atr_trend']].copy()
    monthly_plot['plot_period'] = monthly_plot['period'].shift(-1)
    monthly_plot = monthly_plot.dropna(subset=['plot_period'])

    mapped = weekly.copy()
    mapped['month_period'] = pd.to_datetime(mapped['date']).dt.to_period('M')
    mapped = mapped.merge(
        monthly_plot[['plot_period', 'atr_stop', 'atr_trend']],
        how='left',
        left_on='month_period',
        right_on='plot_period',
        suffixes=('', '_monthly'),
    )
    mapped = mapped.rename(columns={'atr_stop': 'monthly_atr_stop', 'atr_trend': 'monthly_atr_trend'})
    return mapped


def draw_weekly_candles(ax: plt.Axes, weekly: pd.DataFrame) -> None:
    xs = mdates.date2num(pd.to_datetime(weekly['date']))
    width = 4.3
    for x, (_, row) in zip(xs, weekly.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(x, l, h, color=color, linewidth=1.0, zorder=3)
        body_low = min(o, c)
        body_high = max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_low),
                width,
                max(body_high - body_low, 0.05),
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                alpha=0.93,
                zorder=3,
            )
        )


def plot_stop_segments(
    ax: plt.Axes,
    bars: pd.DataFrame,
    trend_col: str,
    stop_col: str,
    colors: dict[str, str],
    linewidth: float,
    linestyle: str,
    alpha: float,
    zorder: int,
) -> None:
    work = bars.copy()
    work = work[work[stop_col].notna() & work[trend_col].isin(['up', 'down'])].copy()
    if work.empty:
        return
    work['_segment'] = (
        work[trend_col].ne(work[trend_col].shift())
        | pd.to_datetime(work['date']).diff().dt.days.gt(12)
    ).cumsum()
    for _, chunk in work.groupby('_segment', sort=True):
        trend = str(chunk.iloc[0][trend_col])
        ax.plot(
            mdates.date2num(pd.to_datetime(chunk['date'])),
            chunk[stop_col].astype(float),
            color=colors.get(trend, GRID),
            linewidth=linewidth,
            linestyle=linestyle,
            alpha=alpha,
            zorder=zorder,
        )


def plot_weekly_lingering_stops(ax: plt.Axes, weekly_st: pd.DataFrame, months: int) -> int:
    work = weekly_st[weekly_st['atr_stop'].notna() & weekly_st['atr_trend'].isin(['up', 'down'])].copy()
    if work.empty:
        return 0
    count = 0
    for idx in range(1, len(work)):
        prev = work.iloc[idx - 1]
        curr = work.iloc[idx]
        prev_trend = str(prev['atr_trend'])
        curr_trend = str(curr['atr_trend'])
        if prev_trend == curr_trend:
            continue
        start = pd.Timestamp(curr['date'])
        end = start + pd.DateOffset(months=months)
        color = WEEKLY_UP if prev_trend == 'up' else WEEKLY_DOWN
        ax.hlines(
            float(prev['atr_stop']),
            mdates.date2num(start),
            mdates.date2num(end),
            colors=color,
            linewidth=1.25,
            alpha=0.52,
            linestyle=':',
            zorder=4,
        )
        count += 1
    return count


def draw_year(
    market: str,
    cfg: dict,
    year: int,
    weekly_st: pd.DataFrame,
    monthly_mapped: pd.DataFrame,
    out_path: Path,
    linger_months: int,
) -> dict:
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year, month=12, day=31)
    context_start = start - pd.DateOffset(months=3)
    context_end = end + pd.DateOffset(months=3)
    visible = weekly_st[weekly_st['date'].between(start, end)].copy()
    context_weekly = weekly_st[weekly_st['date'].between(context_start, context_end)].copy()
    context_monthly = monthly_mapped[monthly_mapped['date'].between(context_start, context_end)].copy()
    if visible.empty:
        return {}

    fig = plt.figure(figsize=(18, 9.5), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_weekly_candles(ax, visible)
    plot_stop_segments(
        ax,
        context_weekly,
        'atr_trend',
        'atr_stop',
        {'up': WEEKLY_UP, 'down': WEEKLY_DOWN},
        linewidth=1.25,
        linestyle='-',
        alpha=0.90,
        zorder=6,
    )
    plot_stop_segments(
        ax,
        context_monthly,
        'monthly_atr_trend',
        'monthly_atr_stop',
        {'up': MONTHLY_UP, 'down': MONTHLY_DOWN},
        linewidth=2.0,
        linestyle='--',
        alpha=0.92,
        zorder=5,
    )
    linger_count = plot_weekly_lingering_stops(ax, context_weekly, linger_months)

    dates = pd.to_datetime(visible['date'])
    y_low = float(visible['low'].min())
    y_high = float(visible['high'].max())
    for frame, stop_col in [(context_weekly, 'atr_stop'), (context_monthly, 'monthly_atr_stop')]:
        if stop_col in frame.columns and frame[stop_col].notna().any():
            y_low = min(y_low, float(frame[stop_col].min()))
            y_high = max(y_high, float(frame[stop_col].max()))
    y_rng = max(y_high - y_low, 1.0)
    ax.set_ylim(y_low - y_rng * 0.08, y_high + y_rng * 0.12)
    ax.set_xlim(start - pd.Timedelta(days=18), end + pd.Timedelta(days=18))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_title(
        f'{year} {cfg["label"]} weekly candles · weekly + monthly ATR Supertrend · weekly broken stops linger {linger_months}m',
        color='white',
        fontsize=10,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    legend = ax.legend(
        handles=[
            plt.Line2D([0], [0], color=WEEKLY_UP, lw=1.35, label='Weekly ATR up stop'),
            plt.Line2D([0], [0], color=WEEKLY_DOWN, lw=1.35, label='Weekly ATR down stop'),
            plt.Line2D([0], [0], color=MONTHLY_UP, lw=2.0, linestyle='--', label='Completed-month ATR up stop'),
            plt.Line2D([0], [0], color=MONTHLY_DOWN, lw=2.0, linestyle='--', label='Completed-month ATR down stop'),
            plt.Line2D([0], [0], color=GRID, lw=1.2, linestyle=':', alpha=0.7, label='Broken weekly stop linger'),
        ],
        loc='upper left',
        fontsize=8,
        framealpha=0.18,
    )
    for text in legend.get_texts():
        text.set_color(TEXT)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)

    return {
        'year': year,
        'weekly_bars': len(visible),
        'weekly_state': str(visible.iloc[-1]['atr_trend']),
        'monthly_state': str(context_monthly[context_monthly['date'].le(end)].iloc[-1]['monthly_atr_trend'])
        if not context_monthly[context_monthly['date'].le(end)].empty
        else 'n/a',
        'linger_segments': linger_count,
        'chart': f'{year}.png',
    }


def draw_all_weeks(
    cfg: dict,
    weekly_st: pd.DataFrame,
    monthly_mapped: pd.DataFrame,
    out_path: Path,
    linger_months: int,
) -> dict:
    visible = weekly_st.copy()
    if visible.empty:
        return {}

    fig = plt.figure(figsize=(24, 10), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_weekly_candles(ax, visible)
    plot_stop_segments(
        ax,
        weekly_st,
        'atr_trend',
        'atr_stop',
        {'up': WEEKLY_UP, 'down': WEEKLY_DOWN},
        linewidth=1.05,
        linestyle='-',
        alpha=0.88,
        zorder=6,
    )
    plot_stop_segments(
        ax,
        monthly_mapped,
        'monthly_atr_trend',
        'monthly_atr_stop',
        {'up': MONTHLY_UP, 'down': MONTHLY_DOWN},
        linewidth=1.75,
        linestyle='--',
        alpha=0.92,
        zorder=5,
    )
    linger_count = plot_weekly_lingering_stops(ax, weekly_st, linger_months)

    dates = pd.to_datetime(visible['date'])
    y_low = float(visible['low'].min())
    y_high = float(visible['high'].max())
    for frame, stop_col in [(weekly_st, 'atr_stop'), (monthly_mapped, 'monthly_atr_stop')]:
        if stop_col in frame.columns and frame[stop_col].notna().any():
            y_low = min(y_low, float(frame[stop_col].min()))
            y_high = max(y_high, float(frame[stop_col].max()))
    y_rng = max(y_high - y_low, 1.0)
    ax.set_ylim(y_low - y_rng * 0.07, y_high + y_rng * 0.11)
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=28), dates.iloc[-1] + pd.Timedelta(days=28))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.set_title(
        (
            f'{cfg["label"]} weekly candles · full history · weekly + monthly ATR Supertrend · '
            f'weekly broken stops linger {linger_months}m'
        ),
        color='white',
        fontsize=11,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    legend = ax.legend(
        handles=[
            plt.Line2D([0], [0], color=WEEKLY_UP, lw=1.15, label='Weekly ATR up stop'),
            plt.Line2D([0], [0], color=WEEKLY_DOWN, lw=1.15, label='Weekly ATR down stop'),
            plt.Line2D([0], [0], color=MONTHLY_UP, lw=1.8, linestyle='--', label='Completed-month ATR up stop'),
            plt.Line2D([0], [0], color=MONTHLY_DOWN, lw=1.8, linestyle='--', label='Completed-month ATR down stop'),
            plt.Line2D([0], [0], color=GRID, lw=1.1, linestyle=':', alpha=0.7, label='Broken weekly stop linger'),
        ],
        loc='upper left',
        fontsize=8,
        framealpha=0.18,
    )
    for text in legend.get_texts():
        text.set_color(TEXT)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return {
        'start': str(dates.iloc[0].date()),
        'end': str(dates.iloc[-1].date()),
        'weekly_bars': len(visible),
        'linger_segments': linger_count,
        'chart': out_path.name,
    }


def write_index(out_dir: Path, cfg: dict, rows: list[dict], atr_length: int, atr_multiplier: float, linger_months: int) -> None:
    lines = [
        f'# {cfg["label"]} Weekly Candles + Weekly/Monthly ATR Supertrend',
        '',
        f'Visual-only charts using ATR({atr_length}) x {atr_multiplier:g}. Weekly candles are aggregated from daily OHLCV.',
        '',
        'Monthly ATR is mapped causally: a completed monthly ATR state is drawn over the following month of weekly candles.',
        f'Broken weekly ATR stop levels are extended for `{linger_months}` month(s) after the weekly trend flips.',
        '',
        '## Full History',
        '',
        '[all_weeks.png](all_weeks.png)',
        '',
        '## Year Slices',
        '',
        '| Year | Weekly Bars | Final Weekly State | Final Monthly State | Linger Segments In Context | Chart |',
        '|---:|---:|---|---|---:|---|',
    ]
    for row in rows:
        lines.append(
            f"| {row['year']} | {row['weekly_bars']} | {row['weekly_state']} | {row['monthly_state']} | "
            f"{row['linger_segments']} | [{row['chart']}]({row['chart']}) |"
        )
    lines.append('')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def update_parent_index(parent: Path) -> None:
    index = parent / 'INDEX.md'
    line = '- [Weekly candles + weekly/monthly ATR Supertrend](weekly_monthly_combo/INDEX.md)'
    if not index.exists():
        market = parent.parts[-3].upper() if len(parent.parts) >= 3 else 'Market'
        index.write_text(
            '\n'.join(
                [
                    f'# {market} Higher-Timeframe ATR Supertrend Visuals',
                    '',
                    line,
                    '',
                ]
            ),
            encoding='utf-8',
        )
        return
    text = index.read_text(encoding='utf-8')
    if line in text:
        return
    text = text.rstrip() + '\n' + line + '\n'
    index.write_text(text, encoding='utf-8')


def run_market(market: str, clean: bool, atr_length: int, atr_multiplier: float, linger_months: int) -> Path:
    cfg = MARKETS[market]
    daily = pd.read_csv(cfg['daily'], parse_dates=['date']).sort_values('date').reset_index(drop=True)
    weekly = aggregate_ohlc(daily, 'weekly')
    monthly = aggregate_ohlc(daily, 'monthly')
    weekly_st = calculate_supertrend_stop(weekly[['date', 'open', 'high', 'low', 'close']].copy(), atr_length, atr_multiplier)
    weekly_st['volume'] = weekly['volume'].values
    weekly_st['symbol'] = weekly['symbol'].values
    monthly_mapped = map_monthly_stop_to_weekly(weekly, monthly, atr_length, atr_multiplier)

    out_dir = cfg['out']
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)

    full_row = draw_all_weeks(cfg, weekly_st, monthly_mapped, out_dir / 'all_weeks.png', linger_months)
    if full_row:
        print(
            f'{cfg["label"]} all_weeks.png weeks={full_row["weekly_bars"]} '
            f'{full_row["start"]}->{full_row["end"]}'
        )

    rows: list[dict] = []
    for year in sorted(pd.to_datetime(weekly_st['date']).dt.year.unique()):
        row = draw_year(market, cfg, int(year), weekly_st, monthly_mapped, out_dir / f'{int(year)}.png', linger_months)
        if row:
            rows.append(row)
            print(f'{cfg["label"]} {row["chart"]} weekly={row["weekly_state"]} monthly={row["monthly_state"]}')
    write_index(out_dir, cfg, rows, atr_length, atr_multiplier, linger_months)
    update_parent_index(out_dir.parent)
    print(f'Wrote {cfg["label"]} combo charts: {out_dir / "INDEX.md"}')
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--markets', nargs='+', choices=sorted(MARKETS), default=['mnq', 'nq'])
    ap.add_argument('--atr-length', type=int, default=14)
    ap.add_argument('--atr-multiplier', type=float, default=3.0)
    ap.add_argument('--linger-months', type=int, default=3)
    ap.add_argument('--clean', action='store_true')
    args = ap.parse_args()
    for market in args.markets:
        run_market(market, args.clean, args.atr_length, args.atr_multiplier, args.linger_months)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
