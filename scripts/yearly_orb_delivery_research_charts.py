#!/usr/bin/env python3
"""Visual research charts for yearly ORB delivery-state scale-ins."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import argparse

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from yearly_orb_delivery_scalein_study import TradeBundle, simulate_year_with_scaleins, swing_key
from yearly_orb_swing_stop_scaleout3 import SwingPoint, build_swings


BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
RANGE = '#E0E0E0'
BLUE = '#40C4FF'
PURPLE = '#EA80FC'


def draw_candles(ax: plt.Axes, bars: pd.DataFrame, width: float = 0.72) -> None:
    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN if c >= o else RED
        ax.vlines(x, l, h, color=col, linewidth=0.8, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
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


def add_range(ax: plt.Axes, bars: pd.DataFrame, range_high: float, range_low: float) -> None:
    work = bars.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    range_bars = work[work['month'] <= 3]
    if not range_bars.empty:
        ax.axvspan(
            pd.Timestamp(range_bars.iloc[0]['date']),
            pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1),
            color='#1F4E79',
            alpha=0.22,
            zorder=0,
        )
    ax.axhline(range_high, color=RANGE, linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color=RANGE, linestyle='--', linewidth=1.0, zorder=2)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.08, zorder=0)


def first_breakout(work: pd.DataFrame, range_high: float, range_low: float) -> tuple[Optional[int], Optional[str]]:
    trade = work[work['month'] > 3]
    for idx, row in trade.iterrows():
        c = float(row['close'])
        if c > range_high:
            return int(idx), 'Long'
        if c < range_low:
            return int(idx), 'Short'
    return None, None


def calculate_supertrend_stop(ohlc: pd.DataFrame, length: int, multiplier: float) -> pd.DataFrame:
    """Return a Supertrend-style ATR trailing stop on OHLC bars.

    True range is the largest of:
    - high - low
    - abs(high - previous close)
    - abs(low - previous close)

    ATR uses Wilder-style smoothing via alpha = 1 / length. The final upper
    and lower bands ratchet, then a close through the opposite band flips the
    active stop side.
    """
    work = ohlc.copy().sort_values('date').reset_index(drop=True)
    high = work['high'].astype(float)
    low = work['low'].astype(float)
    close = work['close'].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / max(length, 1), adjust=False).mean()
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    trend: list[str] = ['up']
    stop: list[float] = [float(final_lower.iloc[0])]
    for i in range(1, len(work)):
        prev_final_upper = float(final_upper.iloc[i - 1])
        prev_final_lower = float(final_lower.iloc[i - 1])
        if float(basic_upper.iloc[i]) < prev_final_upper or float(close.iloc[i - 1]) > prev_final_upper:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = prev_final_upper
        if float(basic_lower.iloc[i]) > prev_final_lower or float(close.iloc[i - 1]) < prev_final_lower:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = prev_final_lower

        prev_trend = trend[-1]
        if prev_trend == 'down':
            next_trend = 'up' if float(close.iloc[i]) > float(final_upper.iloc[i]) else 'down'
        else:
            next_trend = 'down' if float(close.iloc[i]) < float(final_lower.iloc[i]) else 'up'
        trend.append(next_trend)
        stop.append(float(final_lower.iloc[i] if next_trend == 'up' else final_upper.iloc[i]))

    work['atr'] = atr
    work['atr_stop'] = stop
    work['atr_trend'] = trend
    return work


def calculate_daily_atr_trailing_stop(bars: pd.DataFrame, length: int, multiplier: float) -> pd.DataFrame:
    return calculate_supertrend_stop(bars, length, multiplier)


def calculate_weekly_atr_trailing_stop_on_daily(bars: pd.DataFrame, length: int, multiplier: float) -> pd.DataFrame:
    """Compute a weekly ATR stop and map it onto daily bars.

    The weekly candle is Friday-anchored. To keep this causal, the stop from a
    completed weekly candle is plotted during the next available trading week.
    """
    # Work from only the raw OHLC columns so callers can safely pass a frame
    # that already has daily ATR columns named atr/atr_stop/atr_trend.
    daily = bars[['date', 'open', 'high', 'low', 'close']].copy().sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])
    daily['_week'] = daily['date'].dt.to_period('W-FRI')
    weekly_rows: list[dict] = []
    for week, group in daily.groupby('_week', sort=True):
        weekly_rows.append(
            {
                'week': week,
                'date': pd.Timestamp(group.iloc[-1]['date']),
                'open': float(group.iloc[0]['open']),
                'high': float(group['high'].max()),
                'low': float(group['low'].min()),
                'close': float(group.iloc[-1]['close']),
            }
        )
    weekly = pd.DataFrame(weekly_rows)
    if weekly.empty:
        daily['atr'] = pd.NA
        daily['atr_stop'] = pd.NA
        daily['atr_trend'] = pd.NA
        return daily

    weekly_stop = calculate_supertrend_stop(weekly, length, multiplier)
    weekly_plot = weekly_stop[['week', 'atr', 'atr_stop', 'atr_trend']].copy()
    weekly_plot['week'] = weekly_plot['week'].shift(-1)
    weekly_plot = weekly_plot.dropna(subset=['week'])
    mapped = daily.merge(weekly_plot, how='left', left_on='_week', right_on='week', suffixes=('', '_atr'))
    mapped = mapped.drop(columns=[col for col in ('week_atr', '_week') if col in mapped.columns])
    return mapped


def plot_atr_trailing_stop(
    ax: plt.Axes,
    work: pd.DataFrame,
    breakout_idx: Optional[int],
    length: int,
    multiplier: float,
    timeframe: str,
) -> tuple[int, int]:
    if timeframe == 'weekly':
        atr_work = calculate_weekly_atr_trailing_stop_on_daily(work, length, multiplier)
    else:
        atr_work = calculate_daily_atr_trailing_stop(work, length, multiplier)
    start_idx = breakout_idx if breakout_idx is not None else 0
    visible = atr_work.iloc[start_idx:].copy()
    if visible.empty:
        return 0, 0

    up_count = 0
    down_count = 0
    for trend, color in [('up', '#00BCD4'), ('down', '#FF9800')]:
        segment = visible[visible['atr_trend'] == trend].copy()
        segment = segment[segment['atr_stop'].notna()].copy()
        if segment.empty:
            continue
        if trend == 'up':
            up_count = len(segment)
        else:
            down_count = len(segment)
        split_id = (segment.index.to_series().diff() != 1).cumsum()
        for _, chunk in segment.groupby(split_id):
            ax.plot(
                mdates.date2num(pd.to_datetime(chunk['date'])),
                chunk['atr_stop'].astype(float),
                color=color,
                linewidth=1.15,
                alpha=0.82,
                zorder=5,
            )
    return up_count, down_count


def build_weekly_swings_on_daily(work: pd.DataFrame) -> list[SwingPoint]:
    """Build confirmed weekly pivots, expressed in daily-row coordinates.

    The chart remains daily, but a weekly swing is not usable until the
    following weekly candle is complete. ``confirm_idx`` therefore points to
    the final daily bar of the right-side weekly candle.
    """
    daily = work.copy().sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])
    daily['_idx'] = daily.index
    daily['_week'] = daily['date'].dt.to_period('W-FRI')
    weekly_rows: list[dict] = []
    for week, group in daily.groupby('_week', sort=True):
        high_idx = int(group['high'].astype(float).idxmax())
        low_idx = int(group['low'].astype(float).idxmin())
        weekly_rows.append(
            {
                'week': str(week),
                'start_idx': int(group['_idx'].min()),
                'end_idx': int(group['_idx'].max()),
                'high': float(group['high'].max()),
                'low': float(group['low'].min()),
                'high_idx': high_idx,
                'low_idx': low_idx,
                'high_date': pd.Timestamp(daily.loc[high_idx, 'date']),
                'low_date': pd.Timestamp(daily.loc[low_idx, 'date']),
            }
        )
    weekly = pd.DataFrame(weekly_rows)
    swings: list[SwingPoint] = []
    if weekly.empty:
        return swings
    highs = weekly['high'].astype(float).tolist()
    lows = weekly['low'].astype(float).tolist()
    for i in range(1, len(weekly) - 1):
        confirm_idx = int(weekly.iloc[i + 1]['end_idx'])
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            swings.append(
                SwingPoint(
                    'low',
                    lows[i],
                    int(weekly.iloc[i]['low_idx']),
                    confirm_idx,
                    pd.Timestamp(weekly.iloc[i]['low_date']),
                    highs[i],
                    lows[i],
                )
            )
        if highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            swings.append(
                SwingPoint(
                    'high',
                    highs[i],
                    int(weekly.iloc[i]['high_idx']),
                    confirm_idx,
                    pd.Timestamp(weekly.iloc[i]['high_date']),
                    highs[i],
                    lows[i],
                )
            )
    return swings


def delivery_events_after_breakout(
    work: pd.DataFrame,
    swings: list[SwingPoint],
    breakout_idx: int,
    range_high: float,
    range_low: float,
) -> list[dict]:
    events: list[dict] = []
    used: set[tuple[str, int, int, float]] = set()
    for idx, row in work.iterrows():
        if idx <= breakout_idx:
            continue
        c = float(row['close'])
        d = pd.Timestamp(row['date'])
        for swing in swings:
            key = swing_key(swing)
            if key in used:
                continue
            if swing.confirm_idx >= idx or swing.pivot_idx <= breakout_idx:
                continue
            if swing.kind == 'high' and swing.value > range_high and c > swing.value:
                used.add(key)
                events.append(
                    {
                        'direction': 'Bullish',
                        'signal_idx': int(idx),
                        'signal_date': d,
                        'signal_close': c,
                        'swing': swing,
                    }
                )
            elif swing.kind == 'low' and swing.value < range_low and c < swing.value:
                used.add(key)
                events.append(
                    {
                        'direction': 'Bearish',
                        'signal_idx': int(idx),
                        'signal_date': d,
                        'signal_close': c,
                        'swing': swing,
                    }
                )
    return events


def draw_delivery_state_year(
    period: str,
    bars: pd.DataFrame,
    meta: dict,
    out_path: Path,
    market: str,
    state_swing_timeframe: str,
    show_atr_stop: bool,
    atr_length: int,
    atr_multiplier: float,
    atr_timeframe: str,
) -> dict:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    range_high = float(meta.get('range_high', 0.0) or 0.0)
    range_low = float(meta.get('range_low', 0.0) or 0.0)
    breakout_idx, breakout_dir = first_breakout(work, range_high, range_low)
    if state_swing_timeframe == 'weekly':
        swings = build_weekly_swings_on_daily(work)
    else:
        swings = build_swings(work)
    events = delivery_events_after_breakout(work, swings, breakout_idx, range_high, range_low) if breakout_idx is not None else []

    fig = plt.figure(figsize=(18, 9), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, work)
    add_range(ax, work, range_high, range_low)
    atr_up_bars = 0
    atr_down_bars = 0
    if show_atr_stop:
        atr_up_bars, atr_down_bars = plot_atr_trailing_stop(
            ax,
            work,
            breakout_idx,
            atr_length,
            atr_multiplier,
            atr_timeframe,
        )

    if breakout_idx is not None:
        b = work.loc[breakout_idx]
        marker = '^' if breakout_dir == 'Long' else 'v'
        color = '#FFC107'
        ax.scatter(
            [mdates.date2num(pd.Timestamp(b['date']))],
            [float(b['close'])],
            marker=marker,
            s=120,
            color=color,
            edgecolor='black',
            linewidth=0.8,
            zorder=12,
            label='First yearly ORB breakout',
        )

    bull_count = 0
    bear_count = 0
    for i, event in enumerate(events, 1):
        swing = event['swing']
        sig_x = mdates.date2num(event['signal_date'])
        swing_x = mdates.date2num(swing.pivot_date)
        if event['direction'] == 'Bullish':
            bull_count += 1
            color = '#00E676'
            marker = '^'
        else:
            bear_count += 1
            color = '#FF5252'
            marker = 'v'
        ax.scatter([swing_x], [swing.value], marker='o', s=42, color=color, edgecolor='black', linewidth=0.6, zorder=10)
        ax.scatter([sig_x], [event['signal_close']], marker=marker, s=78, color=color, edgecolor='black', linewidth=0.7, zorder=11)
        ax.plot([swing_x, sig_x], [swing.value, swing.value], color=color, linewidth=0.6, alpha=0.35, zorder=4)
        if i <= 28:
            ax.annotate(
                str(i),
                xy=(sig_x, event['signal_close']),
                xytext=(4, 9 if event['direction'] == 'Bullish' else -14),
                textcoords='offset points',
                color=color,
                fontsize=7,
                fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.12', fc=BG, ec=color, alpha=0.88),
            )

    dates = pd.to_datetime(work['date'])
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=4), dates.iloc[-1] + pd.Timedelta(days=8))
    ax.set_title(
        f'{period} {market} yearly ORB {state_swing_timeframe} delivery-state map · first break {breakout_dir or "none"} · '
        f'bullish changes {bull_count} · bearish changes {bear_count}'
        + (f' · {atr_timeframe} ATR stop {atr_length}x{atr_multiplier:g}' if show_atr_stop else ''),
        color='white',
        fontsize=10,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return {
        'period': period,
        'symbol': meta.get('symbol'),
        'first_breakout': breakout_dir or 'None',
        'bullish_changes': bull_count,
        'bearish_changes': bear_count,
        'total_changes': bull_count + bear_count,
        'atr_up_bars': atr_up_bars,
        'atr_down_bars': atr_down_bars,
        'chart': f'delivery_state_by_year{"_weekly_swings" if state_swing_timeframe == "weekly" else ""}/{period}.png',
    }


def find_window(work: pd.DataFrame, dates: Iterable[pd.Timestamp], before: int, after: int) -> pd.DataFrame:
    date_list = sorted(pd.Timestamp(d) for d in dates if d is not None)
    if not date_list:
        return work
    positions: list[int] = []
    for d in date_list:
        matches = work.index[work['date'] == d].tolist()
        if matches:
            positions.append(matches[0])
    if not positions:
        return work
    start = max(0, min(positions) - before)
    end = min(len(work) - 1, max(positions) + after)
    return work.iloc[start : end + 1].copy()


def draw_scalein_chart(
    period: str,
    bars: pd.DataFrame,
    meta: dict,
    bundle: TradeBundle,
    addon_idx: int,
    out_path: Path,
    market: str,
    point_value: float,
) -> dict:
    order = bundle.addons[addon_idx]
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    window = find_window(
        work,
        [
            bundle.base.breakout_date,
            bundle.base.entry_date,
            order.signal_date,
            order.fill_date,
            order.exit_date,
        ],
        before=22,
        after=20,
    )
    range_high = float(meta.get('range_high', 0.0) or 0.0)
    range_low = float(meta.get('range_low', 0.0) or 0.0)

    fig = plt.figure(figsize=(15, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, window)
    ax.axhline(range_high, color=RANGE, linestyle='--', linewidth=1.0, alpha=0.8, zorder=2)
    ax.axhline(range_low, color=RANGE, linestyle='--', linewidth=1.0, alpha=0.8, zorder=2)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.08, zorder=0)

    base = bundle.base
    x_base = mdates.date2num(base.entry_date)
    ax.scatter([x_base], [base.entry], marker='^' if base.direction == 'Long' else 'v', s=100, color='#FFC107', edgecolor='black', linewidth=0.8, zorder=11)
    ax.axhline(base.target, color='#76FF03', linewidth=0.8, alpha=0.45, zorder=2)
    ax.axhline(base.initial_stop, color='#FF1744', linewidth=0.8, alpha=0.42, zorder=2)

    swing_x = mdates.date2num(order.swing_date)
    sig_x = mdates.date2num(order.signal_date)
    ax.scatter([swing_x], [order.swing_value], marker='o', s=70, color=BLUE, edgecolor='black', linewidth=0.7, zorder=12)
    ax.scatter([sig_x], [order.signal_close], marker='D', s=82, color=BLUE, edgecolor='black', linewidth=0.7, zorder=12)
    ax.plot([swing_x, sig_x], [order.swing_value, order.swing_value], color=BLUE, linewidth=0.8, alpha=0.55, zorder=5)
    ax.axhline(order.entry, color=PURPLE, linewidth=0.85, alpha=0.68, zorder=4)
    ax.axhline(order.stop, color='#FF5252', linewidth=0.85, alpha=0.68, zorder=4)
    ax.axhline(order.target, color='#00E676', linewidth=0.85, alpha=0.68, zorder=4)

    if order.fill_date is not None:
        ax.scatter([mdates.date2num(order.fill_date)], [order.entry], marker='P', s=90, color=PURPLE, edgecolor='black', linewidth=0.7, zorder=12)
    if order.exit_date is not None and order.exit_price is not None:
        color = '#00E676' if order.pl > 0 else '#FF5252' if order.pl < 0 else '#B0BEC5'
        ax.scatter([mdates.date2num(order.exit_date)], [order.exit_price], marker='X', s=98, color=color, edgecolor='black', linewidth=0.8, zorder=12)

    for label, date, price, color, offset in [
        ('base entry', base.entry_date, base.entry, '#FFC107', 16),
        ('broken swing', order.swing_date, order.swing_value, BLUE, 16),
        ('signal close', order.signal_date, order.signal_close, BLUE, -22),
        ('fill', order.fill_date, order.entry, PURPLE, 16),
        ('exit', order.exit_date, order.exit_price, '#E0E0E0', -24),
    ]:
        if date is None or price is None:
            continue
        ax.annotate(
            label,
            xy=(mdates.date2num(date), price),
            xytext=(6, offset),
            textcoords='offset points',
            color=color,
            fontsize=7,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.14', fc=BG, ec=color, alpha=0.9),
        )

    dates = pd.to_datetime(window['date'])
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=1))
    ax.set_title(
        f'{period} {market} delivery scale-in #{order.scale_id} {order.direction} · '
        f'{order.exit_reason or order.status} · {order.pl:+.2f} pts (${order.pl * point_value:+,.0f})',
        color='white',
        fontsize=10,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return {
        'period': period,
        'scale_id': order.scale_id,
        'direction': order.direction,
        'signal_date': order.signal_date.date().isoformat(),
        'fill_date': order.fill_date.date().isoformat() if order.fill_date is not None else '',
        'exit_reason': order.exit_reason or order.status,
        'pl_pts': round(order.pl, 2),
        'pl_usd': round(order.pl * point_value, 2),
        'chart': str(out_path.relative_to(out_path.parents[2])),
    }


def write_index(
    out_root: Path,
    market: str,
    state_rows: list[dict],
    scale_rows: list[dict],
    state_swing_timeframe: str,
    show_atr_stop: bool,
    atr_length: int,
    atr_multiplier: float,
    atr_timeframe: str,
) -> None:
    lines = [
        f'# {market} yearly ORB delivery visual research',
        '',
        f'This folder is visual research only. It separates the delivery-state marks from the performance backtest. Delivery-state maps use {state_swing_timeframe} swing highs/lows on a daily candle chart.',
        '',
        'Markers:',
        '- Yellow triangle: first yearly ORB breakout after Jan-Mar.',
        f'- Green triangle/circle pair: daily close broke a confirmed {state_swing_timeframe} swing high above the yearly range.',
        f'- Red triangle/circle pair: daily close broke a confirmed {state_swing_timeframe} swing low below the yearly range.',
        *(
            [
                f'- Cyan/orange line: Supertrend-style ATR trailing stop, computed from {atr_timeframe} ATR({atr_length}) x {atr_multiplier:g} and plotted only after the first yearly ORB breakout.',
            ]
            if show_atr_stop
            else []
        ),
        '- Blue diamond on scale-in charts: add-on signal close.',
        '- Purple pentagon on scale-in charts: add-on fill.',
        '',
        '## Delivery State By Year',
        '',
        '| Year | Symbol | First Break | Bullish Changes | Bearish Changes | Total | ATR Up Bars | ATR Down Bars | Chart |',
        '|---:|---|---|---:|---:|---:|---:|---:|---|',
    ]
    for row in state_rows:
        lines.append(
            f'| {row["period"]} | {row["symbol"]} | {row["first_breakout"]} | {row["bullish_changes"]} | {row["bearish_changes"]} | {row["total_changes"]} | {row.get("atr_up_bars", 0)} | {row.get("atr_down_bars", 0)} | [{row["period"]}.png]({row["chart"]}) |'
        )
    if scale_rows:
        lines.extend(
            [
                '',
                '## Scale-In Samples',
                '',
                '| Year | Scale | Direction | Signal | Fill | Exit | P/L pts | P/L $ | Chart |',
                '|---:|---:|---|---|---|---|---:|---:|---|',
            ]
        )
        for row in scale_rows:
            lines.append(
                f'| {row["period"]} | {row["scale_id"]} | {row["direction"]} | {row["signal_date"]} | {row["fill_date"]} | {row["exit_reason"]} | {row["pl_pts"]:+.2f} | ${row["pl_usd"]:+,.0f} | [{Path(row["chart"]).name}]({row["chart"]}) |'
            )
    lines.append('')
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def run(args: argparse.Namespace) -> None:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]
    daily = daily.copy()
    daily['date'] = pd.to_datetime(daily['date'])
    daily['year'] = daily['date'].dt.year

    state_rows: list[dict] = []
    scale_rows: list[dict] = []
    scale_count = 0
    for year, bars in daily.groupby('year', sort=True):
        bars = bars.sort_values('date').reset_index(drop=True)
        months = bars['date'].dt.month
        if not (months <= 3).any() or not (months > 3).any():
            continue
        period = str(int(year))
        bundles, meta = simulate_year_with_scaleins(
            period,
            bars,
            range_close_exit=True,
            entry_mode='boundary',
            stop_swing_scope='inside-range-candle',
        )
        state_dir = 'delivery_state_by_year_weekly_swings' if args.state_swing_timeframe == 'weekly' else 'delivery_state_by_year'
        state_rows.append(
            draw_delivery_state_year(
                period,
                bars,
                meta,
                args.out / state_dir / f'{period}.png',
                args.market.upper(),
                args.state_swing_timeframe,
                args.show_atr_stop,
                args.atr_length,
                args.atr_multiplier,
                args.atr_timeframe,
            )
        )
        if args.state_only:
            continue
        for bundle in bundles:
            for addon_idx, _ in enumerate(bundle.addons):
                if scale_count >= args.max_scalein_charts:
                    continue
                order = bundle.addons[addon_idx]
                result_dir = 'winners' if order.pl > 0 else 'losers' if order.pl < 0 else 'scratch'
                name = f'{period}_scale_{scale_count + 1:02d}_{order.direction.lower()}_{result_dir[:-1]}.png'
                scale_rows.append(
                    draw_scalein_chart(
                        period,
                        bars,
                        meta,
                        bundle,
                        addon_idx,
                        args.out / 'scalein_samples' / result_dir / name,
                        args.market.upper(),
                        args.point_value,
                    )
                )
                scale_count += 1
    write_index(
        args.out,
        args.market.upper(),
        state_rows,
        scale_rows,
        args.state_swing_timeframe,
        args.show_atr_stop,
        args.atr_length,
        args.atr_multiplier,
        args.atr_timeframe,
    )
    print(f'Wrote {len(state_rows)} delivery-state charts and {len(scale_rows)} scale-in charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--max-scalein-charts', type=int, default=40)
    ap.add_argument('--state-swing-timeframe', choices=['daily', 'weekly'], default='daily')
    ap.add_argument('--state-only', action='store_true')
    ap.add_argument('--show-atr-stop', action='store_true')
    ap.add_argument('--atr-length', type=int, default=14)
    ap.add_argument('--atr-multiplier', type=float, default=3.0)
    ap.add_argument('--atr-timeframe', choices=['daily', 'weekly'], default='daily')
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
