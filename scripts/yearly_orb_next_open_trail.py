#!/usr/bin/env python3
"""Yearly ORB breakout-open retest trailing stop studies.

Default rules:
- Jan-Mar defines the yearly ORB.
- From Apr-Dec, wait for a fresh daily close outside the yearly ORB.
- Place one retest limit at that breakout candle's open.
- Long stop starts at the breakout candle low; short stop starts at the
  breakout candle high.
- After fill, trail with the previous daily low for longs or previous daily
  high for shorts. The stop never loosens.
- Do not place repeated orders while price remains outside the yearly range.

The archived repeated-outside-next-open mode is kept for comparison because
that higher-turnover version also showed positive expectancy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import argparse

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


@dataclass
class TrailTrade:
    period: str
    direction: str
    breakout_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry: float
    initial_stop: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str
    pnl_pts: float
    mae_pts: float
    mfe_pts: float
    stop_points: list[tuple[pd.Timestamp, float]]


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['year'] = work['date'].dt.year
    work['month'] = work['date'].dt.month
    for year, sub in work.groupby('year', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if not (sub['month'] <= 3).any() or not (sub['month'] > 3).any():
            continue
        yield str(int(year)), sub


def trade_pnl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def update_excursion(direction: str, entry: float, high: float, low: float, mae: float, mfe: float) -> tuple[float, float]:
    if direction == 'Long':
        mae = max(mae, max(0.0, entry - low))
        mfe = max(mfe, max(0.0, high - entry))
    else:
        mae = max(mae, max(0.0, high - entry))
        mfe = max(mfe, max(0.0, entry - low))
    return mae, mfe


def exit_at_stop(direction: str, open_px: float, stop: float) -> float:
    if direction == 'Long' and open_px < stop:
        return open_px
    if direction == 'Short' and open_px > stop:
        return open_px
    return stop


def close_state(close: float, range_high: float, range_low: float) -> str:
    if close > range_high:
        return 'Long'
    if close < range_low:
        return 'Short'
    return 'Inside'


def simulate_year_repeated_outside_next_open(period: str, bars: pd.DataFrame) -> tuple[list[TrailTrade], dict]:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month

    range_bars = work[work['month'] <= 3]
    trade_start_idx = int(range_bars.index.max()) + 1 if not range_bars.empty else len(work)
    meta = {
        'period': period,
        'symbol': str(work.iloc[0]['symbol']),
        'range_days': len(range_bars),
        'trade_days': int((work['month'] > 3).sum()),
    }
    if range_bars.empty or trade_start_idx >= len(work):
        return [], meta

    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    meta.update({'range_high': range_high, 'range_low': range_low, 'range': range_val})
    if range_val <= 0:
        return [], meta

    trades: list[TrailTrade] = []
    pending_direction: Optional[str] = None
    pending_breakout_date: Optional[pd.Timestamp] = None
    in_trade = False
    direction: Optional[str] = None
    entry = initial_stop = stop = None
    entry_date: Optional[pd.Timestamp] = None
    breakout_date: Optional[pd.Timestamp] = None
    mae = mfe = 0.0
    stop_points: list[tuple[pd.Timestamp, float]] = []

    for idx in range(trade_start_idx, len(work)):
        bar = work.iloc[idx]
        date = pd.Timestamp(bar['date'])
        o, h, l, c = map(float, [bar['open'], bar['high'], bar['low'], bar['close']])

        if pending_direction is not None and not in_trade:
            direction = pending_direction
            entry = o
            entry_date = date
            breakout_date = pending_breakout_date
            initial_stop = l if direction == 'Long' else h
            stop = initial_stop
            stop_points = [(date, stop)]
            mae, mfe = update_excursion(direction, entry, h, l, 0.0, 0.0)
            in_trade = True
            pending_direction = None
            pending_breakout_date = None
            continue

        if in_trade:
            assert direction is not None and entry is not None and stop is not None and entry_date is not None
            prev = work.iloc[idx - 1]
            prev_stop = float(prev['low']) if direction == 'Long' else float(prev['high'])
            if direction == 'Long':
                stop = max(stop, prev_stop)
            else:
                stop = min(stop, prev_stop)
            stop_points.append((date, stop))
            mae, mfe = update_excursion(direction, entry, h, l, mae, mfe)

            hit = (direction == 'Long' and l <= stop) or (direction == 'Short' and h >= stop)
            if hit:
                exit_price = exit_at_stop(direction, o, stop)
                trades.append(
                    TrailTrade(
                        period=period,
                        direction=direction,
                        breakout_date=breakout_date or entry_date,
                        entry_date=entry_date,
                        entry=entry,
                        initial_stop=initial_stop if initial_stop is not None else stop,
                        exit_date=date,
                        exit_price=exit_price,
                        exit_reason='Trail-Stop',
                        pnl_pts=trade_pnl(direction, entry, exit_price),
                        mae_pts=mae,
                        mfe_pts=mfe,
                        stop_points=stop_points.copy(),
                    )
                )
                in_trade = False
                direction = None
                entry = initial_stop = stop = None
                entry_date = breakout_date = None
                mae = mfe = 0.0
                stop_points = []

        if not in_trade and pending_direction is None:
            if c > range_high and idx + 1 < len(work):
                pending_direction = 'Long'
                pending_breakout_date = date
            elif c < range_low and idx + 1 < len(work):
                pending_direction = 'Short'
                pending_breakout_date = date

    if in_trade:
        assert direction is not None and entry is not None and entry_date is not None
        last = work.iloc[-1]
        exit_price = float(last['close'])
        exit_date = pd.Timestamp(last['date'])
        trades.append(
            TrailTrade(
                period=period,
                direction=direction,
                breakout_date=breakout_date or entry_date,
                entry_date=entry_date,
                entry=entry,
                initial_stop=initial_stop if initial_stop is not None else entry,
                exit_date=exit_date,
                exit_price=exit_price,
                exit_reason='Period-Close',
                pnl_pts=trade_pnl(direction, entry, exit_price),
                mae_pts=mae,
                mfe_pts=mfe,
                stop_points=stop_points.copy(),
            )
        )

    return trades, meta


def simulate_year_breakout_open_retest(period: str, bars: pd.DataFrame) -> tuple[list[TrailTrade], dict]:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month

    range_bars = work[work['month'] <= 3]
    trade_start_idx = int(range_bars.index.max()) + 1 if not range_bars.empty else len(work)
    meta = {
        'period': period,
        'symbol': str(work.iloc[0]['symbol']),
        'range_days': len(range_bars),
        'trade_days': int((work['month'] > 3).sum()),
    }
    if range_bars.empty or trade_start_idx >= len(work):
        return [], meta

    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    meta.update({'range_high': range_high, 'range_low': range_low, 'range': range_val})
    if range_val <= 0:
        return [], meta

    trades: list[TrailTrade] = []
    pending: Optional[dict] = None
    in_trade = False
    direction: Optional[str] = None
    entry = initial_stop = stop = None
    entry_date: Optional[pd.Timestamp] = None
    breakout_date: Optional[pd.Timestamp] = None
    mae = mfe = 0.0
    stop_points: list[tuple[pd.Timestamp, float]] = []
    last_state = close_state(float(work.iloc[trade_start_idx - 1]['close']), range_high, range_low)

    for idx in range(trade_start_idx, len(work)):
        bar = work.iloc[idx]
        date = pd.Timestamp(bar['date'])
        o, h, l, c = map(float, [bar['open'], bar['high'], bar['low'], bar['close']])
        exited_this_bar = False

        if in_trade:
            assert direction is not None and entry is not None and stop is not None and entry_date is not None
            prev = work.iloc[idx - 1]
            prev_stop = float(prev['low']) if direction == 'Long' else float(prev['high'])
            if direction == 'Long':
                stop = max(stop, prev_stop)
            else:
                stop = min(stop, prev_stop)
            stop_points.append((date, stop))
            mae, mfe = update_excursion(direction, entry, h, l, mae, mfe)

            hit = (direction == 'Long' and l <= stop) or (direction == 'Short' and h >= stop)
            if hit:
                exit_price = exit_at_stop(direction, o, stop)
                trades.append(
                    TrailTrade(
                        period=period,
                        direction=direction,
                        breakout_date=breakout_date or entry_date,
                        entry_date=entry_date,
                        entry=entry,
                        initial_stop=initial_stop if initial_stop is not None else stop,
                        exit_date=date,
                        exit_price=exit_price,
                        exit_reason='Trail-Stop',
                        pnl_pts=trade_pnl(direction, entry, exit_price),
                        mae_pts=mae,
                        mfe_pts=mfe,
                        stop_points=stop_points.copy(),
                    )
                )
                in_trade = False
                exited_this_bar = True
                direction = None
                entry = initial_stop = stop = None
                entry_date = breakout_date = None
                mae = mfe = 0.0
                stop_points = []

        if pending is not None and not in_trade:
            pend_dir = str(pending['direction'])
            pend_entry = float(pending['entry'])
            pend_stop = float(pending['stop'])
            fill_hit = (pend_dir == 'Long' and l <= pend_entry) or (pend_dir == 'Short' and h >= pend_entry)
            if fill_hit:
                direction = pend_dir
                entry = pend_entry
                initial_stop = pend_stop
                stop = pend_stop
                entry_date = date
                breakout_date = pd.Timestamp(pending['breakout_date'])
                stop_points = [(date, stop)]
                mae, mfe = update_excursion(direction, entry, h, l, 0.0, 0.0)
                pending = None

                hit = (direction == 'Long' and l <= stop) or (direction == 'Short' and h >= stop)
                if hit:
                    exit_price = exit_at_stop(direction, o, stop)
                    trades.append(
                        TrailTrade(
                            period=period,
                            direction=direction,
                            breakout_date=breakout_date,
                            entry_date=entry_date,
                            entry=entry,
                            initial_stop=initial_stop,
                            exit_date=date,
                            exit_price=exit_price,
                            exit_reason='Initial-Stop',
                            pnl_pts=trade_pnl(direction, entry, exit_price),
                            mae_pts=mae,
                            mfe_pts=mfe,
                            stop_points=stop_points.copy(),
                        )
                    )
                    direction = None
                    entry = initial_stop = stop = None
                    entry_date = breakout_date = None
                    mae = mfe = 0.0
                    stop_points = []
                    exited_this_bar = True
                else:
                    in_trade = True

        state = close_state(c, range_high, range_low)
        if pending is not None:
            pend_dir = str(pending['direction'])
            if state != pend_dir:
                pending = None

        if not in_trade and pending is None and not exited_this_bar and idx + 1 < len(work):
            if state in ('Long', 'Short') and state != last_state:
                pending = {
                    'direction': state,
                    'entry': o,
                    'stop': l if state == 'Long' else h,
                    'breakout_date': date,
                }

        last_state = state

    if in_trade:
        assert direction is not None and entry is not None and entry_date is not None
        last = work.iloc[-1]
        exit_price = float(last['close'])
        exit_date = pd.Timestamp(last['date'])
        trades.append(
            TrailTrade(
                period=period,
                direction=direction,
                breakout_date=breakout_date or entry_date,
                entry_date=entry_date,
                entry=entry,
                initial_stop=initial_stop if initial_stop is not None else entry,
                exit_date=exit_date,
                exit_price=exit_price,
                exit_reason='Period-Close',
                pnl_pts=trade_pnl(direction, entry, exit_price),
                mae_pts=mae,
                mfe_pts=mfe,
                stop_points=stop_points.copy(),
            )
        )

    return trades, meta


def simulate_year(period: str, bars: pd.DataFrame, mode: str) -> tuple[list[TrailTrade], dict]:
    if mode == 'repeated-outside-next-open':
        return simulate_year_repeated_outside_next_open(period, bars)
    if mode == 'fresh-breakout-open-retest':
        return simulate_year_breakout_open_retest(period, bars)
    raise ValueError(f'unknown mode: {mode}')


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def mode_label(mode: str) -> str:
    if mode == 'repeated-outside-next-open':
        return 'YEARLY ORB REPEATED OUTSIDE NEXT-OPEN TRAIL'
    return 'YEARLY ORB BREAKOUT-OPEN RETEST TRAIL'


def mode_description(mode: str) -> str:
    if mode == 'repeated-outside-next-open':
        return (
            'Research rules: Jan-Mar yearly ORB, enter 1 unit at the next daily open after every daily close '
            'outside the yearly range, entry-day low/high becomes the initial stop after that day has completed, '
            'then trail with the previous daily low/high without loosening.'
        )
    return (
        'Research rules: Jan-Mar yearly ORB, wait for a fresh daily close outside the yearly range, place one '
        "retest limit at that breakout candle's open, use the breakout candle low/high as the initial stop, "
        'then trail with the previous daily low/high without loosening. No repeated orders are placed while price '
        'remains outside the yearly range.'
    )


def mode_caveat(mode: str) -> str:
    if mode == 'repeated-outside-next-open':
        return (
            '**Causality caveat:** the entry-day low/high is not known at the entry open. This archived version '
            'is a structure study, not a live-equivalent automation test.'
        )
    return (
        '**Execution caveat:** this uses daily OHLC for retest fills and stop ordering. The signal and initial '
        'stop are causal after the breakout candle closes, but same-day fill/stop sequencing should be checked '
        'with intraday data before paper automation.'
    )


def rows_for(trades: list[TrailTrade], meta: dict) -> list[dict]:
    if not trades:
        return [
            {
                'Period': meta['period'],
                'Range_High': meta.get('range_high'),
                'Range_Low': meta.get('range_low'),
                'Range': meta.get('range'),
                'Trade_Direction': 'No-Op',
                'Breakout_Date': None,
                'Entry_Date': None,
                'Entry_Price': None,
                'Initial_Stop': None,
                'Exit_Date': None,
                'Exit_Price': None,
                'Trade_PL': 0.0,
                'MAE_Pts': 0.0,
                'MFE_Pts': 0.0,
                'Result': 'No-Op',
                'Exit_Reason': 'No-Op',
                'Symbol': meta['symbol'],
                'Range_Days': meta['range_days'],
                'Trade_Days': meta['trade_days'],
                'Cumulative_PL': 0.0,
            }
        ]

    out: list[dict] = []
    cumulative = 0.0
    for tr in trades:
        cumulative += tr.pnl_pts
        out.append(
            {
                'Period': tr.period,
                'Range_High': meta.get('range_high'),
                'Range_Low': meta.get('range_low'),
                'Range': meta.get('range'),
                'Trade_Direction': tr.direction,
                'Breakout_Date': tr.breakout_date.date().isoformat(),
                'Entry_Date': tr.entry_date.date().isoformat(),
                'Entry_Price': tr.entry,
                'Initial_Stop': tr.initial_stop,
                'Exit_Date': tr.exit_date.date().isoformat(),
                'Exit_Price': tr.exit_price,
                'Trade_PL': round(tr.pnl_pts, 6),
                'MAE_Pts': round(tr.mae_pts, 6),
                'MFE_Pts': round(tr.mfe_pts, 6),
                'Result': 'Win' if tr.pnl_pts > 0 else ('Loss' if tr.pnl_pts < 0 else 'Scratch'),
                'Exit_Reason': tr.exit_reason,
                'Symbol': meta['symbol'],
                'Range_Days': meta['range_days'],
                'Trade_Days': meta['trade_days'],
                'Cumulative_PL': round(cumulative, 6),
            }
        )
    return out


def draw_year(
    period: str,
    bars: pd.DataFrame,
    trades: list[TrailTrade],
    meta: dict,
    out_path: Path,
    market: str,
    point_value: float,
    label: str,
) -> dict:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    dates = pd.to_datetime(work['date'])
    xnums = mdates.date2num(dates)
    range_bars = work[work['month'] <= 3]
    rh = float(meta.get('range_high', 0.0) or 0.0)
    rl = float(meta.get('range_low', 0.0) or 0.0)
    rv = float(meta.get('range', 0.0) or 0.0)

    fig = plt.figure(figsize=(18, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    width = 0.72
    for x, (_, row) in zip(xnums, work.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.7, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )

    if not range_bars.empty:
        ax.axvspan(pd.Timestamp(range_bars.iloc[0]['date']), pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1), color='#1F4E79', alpha=0.28, zorder=0)
    if rv > 0:
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)

    total = sum(t.pnl_pts for t in trades)
    offsets = [18, -26, 34, -42, 50, -58]
    for i, tr in enumerate(trades, 1):
        x_b = mdates.date2num(tr.breakout_date)
        x_e = mdates.date2num(tr.entry_date)
        x_x = mdates.date2num(tr.exit_date)
        ax.scatter([x_b], [tr.entry], marker='o', color='#40C4FF', s=58, zorder=9, edgecolor='black', linewidth=0.7)
        ax.scatter([x_e], [tr.entry], marker='^' if tr.direction == 'Long' else 'v', color='#FFC107', s=90, zorder=10, edgecolor='black', linewidth=0.9)
        if tr.stop_points:
            sx = [mdates.date2num(d) for d, _ in tr.stop_points]
            sy = [s for _, s in tr.stop_points]
            ax.plot(sx, sy, color='#FF1744', linewidth=0.8, alpha=0.8, zorder=4)
        col = '#76FF03' if tr.pnl_pts > 0 else '#FF1744'
        ax.scatter([x_x], [tr.exit_price], marker='X', color=col, s=90, zorder=10, edgecolor='black', linewidth=0.9)
        ax.annotate(
            f'#{i} {tr.direction[0]} {tr.pnl_pts:+.0f}',
            xy=(x_x, tr.exit_price),
            xytext=(7, offsets[(i - 1) % len(offsets)]),
            textcoords='offset points',
            color=col,
            fontsize=7,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=col, alpha=0.92),
        )

    title = f'{period} {market} {label} · {len(trades)} trades · {total:+.1f}pt (${total * point_value:+,.0f})'
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=4), dates.iloc[-1] + pd.Timedelta(days=8))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)

    return {
        'period': period,
        'symbol': meta['symbol'],
        'range': round(rv, 2),
        'trades': len(trades),
        'net_pts': round(total, 2),
        'net_usd': round(total * point_value, 2),
        'chart': f'{period}/{period}.png',
    }


def write_indexes(
    out_root: Path,
    market: str,
    point_value: float,
    chart_rows: list[dict],
    result_df: pd.DataFrame,
    mode: str,
) -> None:
    trades = result_df[result_df['Trade_Direction'] != 'No-Op'].copy()
    vals = pd.to_numeric(trades['Trade_PL'], errors='coerce').fillna(0.0)
    mae = pd.to_numeric(trades['MAE_Pts'], errors='coerce').fillna(0.0)
    wins = int((vals > 0).sum())
    losses = int((vals < 0).sum())
    total = float(vals.sum())
    dd = max_dd(vals)
    win_rate = wins / len(trades) * 100 if len(trades) else 0.0
    label = mode_label(mode).lower()

    for row in sorted(chart_rows, key=lambda x: x['period']):
        idx = out_root / row['period'] / 'INDEX.md'
        idx.write_text(
            '\n'.join(
                [
                    f'# {row["period"]} {market} {label} chart',
                    '',
                    f'Net: {row["net_pts"]:+.2f} pts (${row["net_usd"]:+,.0f} / 1 {market})',
                    '',
                    '| Year | Symbol | Range | Trades | Net pts | Chart |',
                    '|---:|---|---:|---:|---:|---|',
                    f'| {row["period"]} | {row["symbol"]} | {row["range"]:.2f} | {row["trades"]} | {row["net_pts"]:+.2f} | [{row["period"]}.png]({row["period"]}.png) |',
                    '',
                ]
            ),
            encoding='utf-8',
        )

    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                f'# {market} {label} charts',
                '',
                mode_description(mode),
                '',
                mode_caveat(mode),
                '',
                f'Trades: {len(trades)}  ·  Wins: {wins}  ·  Losses: {losses}  ·  Win rate: {win_rate:.1f}%',
                f'Net: {total:+.2f} pts (${total * point_value:+,.0f})  ·  Max DD: {dd:+.2f} pts (${dd * point_value:+,.0f})',
                f'Avg MAE: {mae.mean():.2f} pts (${mae.mean() * point_value:,.0f})  ·  Worst MAE: {mae.max():.2f} pts (${mae.max() * point_value:,.0f})',
                '',
                '| Year | Symbol | Range | Trades | Net pts | Folder |',
                '|---:|---|---:|---:|---:|---|',
                *[
                    f'| {r["period"]} | {r["symbol"]} | {r["range"]:.2f} | {r["trades"]} | {r["net_pts"]:+.2f} | [{r["period"]}/]({r["period"]}/INDEX.md) |'
                    for r in sorted(chart_rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def run(args: argparse.Namespace) -> pd.DataFrame:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    daily['date'] = pd.to_datetime(daily['date'])
    rows: list[dict] = []
    chart_rows: list[dict] = []
    label = mode_label(args.mode)
    for period, bars in period_groups(daily):
        trades, meta = simulate_year(period, bars, args.mode)
        rows.extend(rows_for(trades, meta))
        if args.charts:
            chart_rows.append(
                draw_year(
                    period,
                    bars,
                    trades,
                    meta,
                    args.out / period / f'{period}.png',
                    args.market.upper(),
                    args.point_value,
                    label,
                )
            )
        else:
            chart_rows.append({'period': period, 'symbol': meta['symbol'], 'range': round(float(meta.get('range', 0) or 0), 2), 'trades': len(trades), 'net_pts': round(sum(t.pnl_pts for t in trades), 2), 'net_usd': round(sum(t.pnl_pts for t in trades) * args.point_value, 2), 'chart': f'{period}/{period}.png'})
        print(f'{period} trades={len(trades)} net={sum(t.pnl_pts for t in trades):+.2f}pt')

    out_df = pd.DataFrame(rows)
    if not out_df.empty:
        out_df['Cumulative_PL'] = out_df['Trade_PL'].astype(float).cumsum().round(6)
    args.export_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.export_csv, index=False)
    if args.charts:
        write_indexes(args.out, args.market.upper(), args.point_value, chart_rows, out_df, args.mode)
    print(f'Wrote {args.export_csv}')
    if args.charts:
        print(f'Wrote charts under {args.out}')
    return out_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument(
        '--mode',
        choices=['fresh-breakout-open-retest', 'repeated-outside-next-open'],
        default='fresh-breakout-open-retest',
    )
    ap.add_argument('--charts', action='store_true')
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
