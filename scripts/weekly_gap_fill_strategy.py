#!/usr/bin/env python3
"""Backtest a first-pass weekly gap-fill strategy on big weekly gaps.

Rules implemented:
- Use rows from weekly_gap_size_yorb.csv.
- Trade only rows with point_size_bucket == Big by default.
- Gap Down -> look for a Long back toward previous weekly RTH close.
- Gap Up -> look for a Short back toward previous weekly RTH close.
- A 1-hour candle must close inside the weekly gap and at least halfway
  toward the prior weekly close. If remaining distance to TP1 is greater
  than half the original gap, keep waiting.
- After that 1-hour candle closes, place a limit at that candle close.
- Long limit fills when later 1-minute price trades <= limit.
- Short limit fills when later 1-minute price trades >= limit.
- Stop is the break-in 1-hour candle low for longs / high for shorts.
- Optional variant can use the latest causally confirmed 1-hour swing point
  as the initial stop instead.
- Size is 5 units:
    1 exits halfway from entry to TP1;
    2 exit at TP1, the prior weekly RTH close / gap fill;
    2 exit at TP2, one full gap beyond TP1.
- Optional variant can move the remaining stop to breakeven after TP1.
- Optional variant can exit remaining size on a 1-hour close back outside
  the weekly gap boundary.
- Max 2 filled trades per weekly gap.
- Stop is checked before targets on ambiguous 1-minute bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pytz


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hourly_gap_fill_analysis import RTH_OPEN, iso_week_key, load_front_month_by_date  # noqa: E402


NY = pytz.timezone('America/New_York')


@dataclass
class Trade:
    market: str
    open_date: str
    prev_close_date: str
    direction: str
    side: str
    attempt: int
    gap_pts: float
    abs_gap_pts: float
    prev_close: float
    week_open: float
    break_time: pd.Timestamp
    break_close: float
    break_low: float
    break_high: float
    stop_mode: str
    stop_source_time: str
    order_live_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry: float
    stop: float
    tp_half: float
    tp1: float
    tp2: float
    exit_time: pd.Timestamp
    exit_reason: str
    qty_start: int
    qty_half: int
    qty_tp1: int
    qty_tp2: int
    qty_stop: int
    qty_boundary_close: int
    qty_eow: int
    gross_pts: float
    gross_usd: float
    mae_pts: float
    mfe_pts: float
    chart: str = ''


@dataclass
class SwingPoint:
    kind: str
    value: float
    pivot_time: pd.Timestamp
    confirm_time: pd.Timestamp


def weekly_window(by_date: dict, open_date) -> pd.DataFrame:
    week = iso_week_key(open_date)
    if week in by_date:
        df = by_date[week]
        open_ts = pd.Timestamp.combine(open_date, RTH_OPEN).tz_localize(NY)
        return df[df.index >= open_ts]

    frames = []
    open_ts = pd.Timestamp.combine(open_date, RTH_OPEN).tz_localize(NY)
    for d in sorted(by_date):
        if iso_week_key(d) != week or d.weekday() > 4:
            continue
        day = by_date[d]
        if d == open_date:
            day = day[day.index >= open_ts]
        frames.append(day)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def build_week_windows(by_date: dict) -> dict:
    out: dict = {}
    for d in sorted(by_date):
        if d.weekday() > 4:
            continue
        out.setdefault(iso_week_key(d), []).append(by_date[d])
    return {week: pd.concat(frames).sort_index() for week, frames in out.items() if frames}


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


def latest_confirmed_swing_stop(
    bars1h: pd.DataFrame,
    current_pos: int,
    side: str,
    entry: float,
) -> SwingPoint | None:
    """Return the newest 1h pivot confirmed by the current bar close."""
    if current_pos < 2:
        return None
    lows = bars1h['low'].astype(float).to_list()
    highs = bars1h['high'].astype(float).to_list()
    idx = list(bars1h.index)
    for i in range(current_pos - 1, 0, -1):
        confirm_time = pd.Timestamp(idx[i + 1]) + pd.Timedelta(hours=1)
        if side == 'Long' and lows[i] < lows[i - 1] and lows[i] < lows[i + 1] and lows[i] < entry:
            return SwingPoint('swing_low', lows[i], pd.Timestamp(idx[i]), confirm_time)
        if side == 'Short' and highs[i] > highs[i - 1] and highs[i] > highs[i + 1] and highs[i] > entry:
            return SwingPoint('swing_high', highs[i], pd.Timestamp(idx[i]), confirm_time)
    return None


def gap_side(row: pd.Series) -> tuple[str, int]:
    if float(row['gap_pts']) < 0:
        return 'Long', 1
    return 'Short', -1


def gap_filled_in_bar(row1m: pd.Series, side: str, tp1: float) -> bool:
    if side == 'Long':
        return float(row1m['high']) >= tp1
    return float(row1m['low']) <= tp1


def gap_filled_in_window(window: pd.DataFrame, side: str, tp1: float) -> bool:
    if window.empty:
        return False
    if side == 'Long':
        return bool((window['high'].astype(float) >= tp1).any())
    return bool((window['low'].astype(float) <= tp1).any())


def candidate_from_bar(bar: pd.Series, side: str, week_open: float, tp1: float, gap_size: float) -> dict | None:
    close = float(bar['close'])
    if side == 'Long':
        inside_gap = week_open < close < tp1
        remaining = tp1 - close
        if not inside_gap or remaining > gap_size * 0.5:
            return None
        return {'entry': close, 'stop': float(bar['low']), 'remaining': remaining}

    inside_gap = tp1 < close < week_open
    remaining = close - tp1
    if not inside_gap or remaining > gap_size * 0.5:
        return None
    return {'entry': close, 'stop': float(bar['high']), 'remaining': remaining}


def find_entry(df1: pd.DataFrame, side: str, entry: float, live_time: pd.Timestamp, tp1: float) -> tuple[pd.Timestamp | None, str]:
    live = df1[df1.index >= live_time]
    for ts, row in live.iterrows():
        if gap_filled_in_bar(row, side, tp1):
            return None, 'gap_filled_before_limit'
        if side == 'Long' and float(row['low']) <= entry:
            return pd.Timestamp(ts), 'filled'
        if side == 'Short' and float(row['high']) >= entry:
            return pd.Timestamp(ts), 'filled'
    return None, 'limit_not_filled'


def simulate_exit(
    df1: pd.DataFrame,
    bars1h: pd.DataFrame,
    side: str,
    entry_time: pd.Timestamp,
    entry: float,
    stop: float,
    tp_half: float,
    tp1: float,
    tp2: float,
    point_value: float,
    move_stop_be_after_tp1: bool,
    boundary_close_exit: bool,
    boundary_px: float,
) -> dict:
    qty_rem = 5
    qty_half = 0
    qty_tp1 = 0
    qty_tp2 = 0
    qty_stop = 0
    qty_boundary_close = 0
    qty_eow = 0
    exits: list[tuple[pd.Timestamp, str, int, float]] = []
    mae = 0.0
    mfe = 0.0
    exit_time = entry_time
    exit_reason = 'EOW'
    active_stop = stop
    be_active = False
    activate_be_next_bar = False

    boundary_events: list[tuple[pd.Timestamp, float]] = []
    if boundary_close_exit:
        for bar_left, bar in bars1h.iterrows():
            event_time = pd.Timestamp(bar_left) + pd.Timedelta(hours=1)
            if event_time < entry_time:
                continue
            close_px = float(bar['close'])
            outside = close_px <= boundary_px if side == 'Long' else close_px >= boundary_px
            if outside:
                boundary_events.append((event_time, close_px))
        boundary_events.sort(key=lambda item: item[0])
    boundary_idx = 0

    live = df1[df1.index >= entry_time]
    for ts, row in live.iterrows():
        if activate_be_next_bar:
            active_stop = entry
            be_active = True
            activate_be_next_bar = False

        high = float(row['high'])
        low = float(row['low'])
        if side == 'Long':
            mae = min(mae, low - entry)
            mfe = max(mfe, high - entry)
            if low <= active_stop:
                qty_stop = qty_rem
                reason = 'BE Stop' if be_active else 'Stop'
                exits.append((pd.Timestamp(ts), reason, qty_rem, active_stop))
                qty_rem = 0
                exit_time = pd.Timestamp(ts)
                exit_reason = reason
                break
            if qty_half == 0 and high >= tp_half:
                qty_half = 1
                qty_rem -= 1
                exits.append((pd.Timestamp(ts), 'Halfway', 1, tp_half))
            if qty_tp1 == 0 and high >= tp1:
                take = min(2, qty_rem)
                qty_tp1 = take
                qty_rem -= take
                exits.append((pd.Timestamp(ts), 'TP1', take, tp1))
                if move_stop_be_after_tp1 and qty_rem > 0:
                    activate_be_next_bar = True
            if qty_tp2 == 0 and high >= tp2:
                take = qty_rem
                qty_tp2 = take
                qty_rem = 0
                exits.append((pd.Timestamp(ts), 'TP2', take, tp2))
                exit_time = pd.Timestamp(ts)
                exit_reason = 'TP2'
                break
        else:
            mae = min(mae, entry - high)
            mfe = max(mfe, entry - low)
            if high >= active_stop:
                qty_stop = qty_rem
                reason = 'BE Stop' if be_active else 'Stop'
                exits.append((pd.Timestamp(ts), reason, qty_rem, active_stop))
                qty_rem = 0
                exit_time = pd.Timestamp(ts)
                exit_reason = reason
                break
            if qty_half == 0 and low <= tp_half:
                qty_half = 1
                qty_rem -= 1
                exits.append((pd.Timestamp(ts), 'Halfway', 1, tp_half))
            if qty_tp1 == 0 and low <= tp1:
                take = min(2, qty_rem)
                qty_tp1 = take
                qty_rem -= take
                exits.append((pd.Timestamp(ts), 'TP1', take, tp1))
                if move_stop_be_after_tp1 and qty_rem > 0:
                    activate_be_next_bar = True
            if qty_tp2 == 0 and low <= tp2:
                take = qty_rem
                qty_tp2 = take
                qty_rem = 0
                exits.append((pd.Timestamp(ts), 'TP2', take, tp2))
                exit_time = pd.Timestamp(ts)
                exit_reason = 'TP2'
                break

        while boundary_idx < len(boundary_events) and boundary_events[boundary_idx][0] <= pd.Timestamp(ts) + pd.Timedelta(minutes=1):
            event_time, event_close = boundary_events[boundary_idx]
            boundary_idx += 1
            if qty_rem <= 0:
                break
            qty_boundary_close = qty_rem
            exits.append((event_time, 'BoundaryClose', qty_rem, event_close))
            qty_rem = 0
            exit_time = event_time
            exit_reason = 'BoundaryClose'
            break
        if qty_rem == 0:
            break

    if qty_rem > 0:
        last_ts = pd.Timestamp(live.index[-1])
        last_close = float(live.iloc[-1]['close'])
        qty_eow = qty_rem
        exits.append((last_ts, 'EOW', qty_rem, last_close))
        exit_time = last_ts
        exit_reason = 'EOW'

    gross_pts = 0.0
    for _, _, qty, px in exits:
        gross_pts += qty * ((px - entry) if side == 'Long' else (entry - px))

    return {
        'exits': exits,
        'qty_half': qty_half,
        'qty_tp1': qty_tp1,
        'qty_tp2': qty_tp2,
        'qty_stop': qty_stop,
        'qty_boundary_close': qty_boundary_close,
        'qty_eow': qty_eow,
        'exit_time': exit_time,
        'exit_reason': exit_reason,
        'gross_pts': gross_pts,
        'gross_usd': gross_pts * point_value,
        'mae_pts': abs(mae),
        'mfe_pts': mfe,
    }


def simulate_week(
    row: pd.Series,
    by_date: dict,
    point_value: float,
    max_trades: int,
    stop_mode: str,
    move_stop_be_after_tp1: bool,
    boundary_close_exit: bool,
) -> tuple[list[Trade], list[dict]]:
    market = str(row['market'])
    open_date = pd.Timestamp(row['open_date']).date()
    df1 = weekly_window(by_date, open_date)
    if df1.empty:
        return [], [{'open_date': open_date.isoformat(), 'reason': 'missing_week_data'}]

    bars1h = resample_1h(df1)
    side, side_mult = gap_side(row)
    gap_size = abs(float(row['gap_pts']))
    week_open = float(row['open_px'])
    prev_close = float(row['prev_close'])
    tp1 = prev_close
    tp2 = prev_close + gap_size if side == 'Long' else prev_close - gap_size
    trades: list[Trade] = []
    skips: list[dict] = []
    search_after = df1.index[0]

    while len(trades) < max_trades:
        trade_count_before = len(trades)
        made_candidate = False
        stopped_or_done = False
        for bar_pos, (bar_ts, bar) in enumerate(bars1h.iterrows()):
            bar_left = pd.Timestamp(bar_ts)
            bar_end = bar_left + pd.Timedelta(hours=1)
            if bar_end <= search_after:
                continue

            bar_start = max(search_after, bar_left)
            pre_window = df1[(df1.index >= bar_start) & (df1.index < bar_end)]
            if gap_filled_in_window(pre_window, side, tp1):
                skips.append({'open_date': open_date.isoformat(), 'reason': 'gap_filled_before_break_in'})
                stopped_or_done = True
                break

            candidate = candidate_from_bar(bar, side, week_open, tp1, gap_size)
            if candidate is None:
                continue
            made_candidate = True
            entry = float(candidate['entry'])
            if stop_mode == 'break-candle':
                stop = float(candidate['stop'])
                stop_source_time = bar_end.isoformat()
            else:
                swing = latest_confirmed_swing_stop(bars1h, bar_pos, side, entry)
                if swing is None:
                    skips.append({'open_date': open_date.isoformat(), 'reason': 'no_confirmed_swing_stop', 'break_time': bar_end.isoformat()})
                    continue
                stop = float(swing.value)
                stop_source_time = swing.confirm_time.isoformat()
            if side == 'Long' and stop >= entry:
                skips.append({'open_date': open_date.isoformat(), 'reason': 'invalid_long_stop', 'break_time': bar_end.isoformat()})
                continue
            if side == 'Short' and stop <= entry:
                skips.append({'open_date': open_date.isoformat(), 'reason': 'invalid_short_stop', 'break_time': bar_end.isoformat()})
                continue

            entry_time, fill_status = find_entry(df1, side, entry, bar_end, tp1)
            if entry_time is None:
                skips.append({'open_date': open_date.isoformat(), 'reason': fill_status, 'break_time': bar_end.isoformat()})
                stopped_or_done = True
                break

            tp_half = entry + side_mult * abs(tp1 - entry) * 0.5
            exit_result = simulate_exit(
                df1,
                bars1h,
                side,
                entry_time,
                entry,
                stop,
                tp_half,
                tp1,
                tp2,
                point_value,
                move_stop_be_after_tp1,
                boundary_close_exit,
                week_open,
            )
            trade = Trade(
                market=market,
                open_date=open_date.isoformat(),
                prev_close_date=str(row['prev_close_date']),
                direction=str(row['direction']),
                side=side,
                attempt=len(trades) + 1,
                gap_pts=float(row['gap_pts']),
                abs_gap_pts=gap_size,
                prev_close=prev_close,
                week_open=week_open,
                break_time=bar_end,
                break_close=float(bar['close']),
                break_low=float(bar['low']),
                break_high=float(bar['high']),
                stop_mode=stop_mode,
                stop_source_time=stop_source_time,
                order_live_time=bar_end,
                entry_time=entry_time,
                entry=entry,
                stop=stop,
                tp_half=tp_half,
                tp1=tp1,
                tp2=tp2,
                exit_time=exit_result['exit_time'],
                exit_reason=exit_result['exit_reason'],
                qty_start=5,
                qty_half=exit_result['qty_half'],
                qty_tp1=exit_result['qty_tp1'],
                qty_tp2=exit_result['qty_tp2'],
                qty_stop=exit_result['qty_stop'],
                qty_boundary_close=exit_result['qty_boundary_close'],
                qty_eow=exit_result['qty_eow'],
                gross_pts=exit_result['gross_pts'],
                gross_usd=exit_result['gross_usd'],
                mae_pts=exit_result['mae_pts'],
                mfe_pts=exit_result['mfe_pts'],
            )
            trade._exits = exit_result['exits']  # type: ignore[attr-defined]
            trades.append(trade)
            search_after = trade.exit_time + pd.Timedelta(minutes=1)
            if trade.exit_reason in {'TP2', 'EOW'} or trade.qty_tp1 > 0:
                stopped_or_done = True
            break

        if stopped_or_done:
            break
        if len(trades) == trade_count_before:
            if made_candidate:
                skips.append({'open_date': open_date.isoformat(), 'reason': 'no_valid_or_filled_candidate'})
            else:
                skips.append({'open_date': open_date.isoformat(), 'reason': 'no_qualifying_break_in'})
            break
        if not made_candidate:
            skips.append({'open_date': open_date.isoformat(), 'reason': 'no_qualifying_break_in'})
            break

    return trades, skips


def draw_candles(ax, bars: pd.DataFrame) -> None:
    xnums = mdates.date2num(bars.index.tz_convert(None).to_pydatetime())
    width = 45.0 / (24 * 60)
    for x, (_, row) in zip(xnums, bars.iterrows()):
        open_px, high_px, low_px, close_px = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if close_px >= open_px else '#EF5350'
        ax.vlines(x, low_px, high_px, color=color, linewidth=0.85, zorder=3)
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


def draw_trade_chart(trade: Trade, by_date: dict, out_path: Path) -> str:
    open_date = pd.Timestamp(trade.open_date).date()
    df1 = weekly_window(by_date, open_date)
    bars1h = resample_1h(df1)
    if bars1h.empty:
        return ''

    fig = plt.figure(figsize=(18, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars1h)

    levels = [
        ('Prev close / TP1', trade.prev_close, '#FFD54F', '--'),
        ('Week open', trade.week_open, '#78909C', ':'),
        ('Entry', trade.entry, '#E0E0E0', '-'),
        ('Stop', trade.stop, '#EF5350', '-'),
        ('Half', trade.tp_half, '#80CBC4', ':'),
        ('TP2', trade.tp2, '#4FC3F7', '--'),
    ]
    for label, px, color, style in levels:
        ax.axhline(px, color=color, linestyle=style, linewidth=1.0, zorder=2)
    x_right = mdates.date2num(bars1h.index[-1].tz_convert(None).to_pydatetime()) + 0.08
    for label, px, color, _ in levels:
        ax.text(x_right, px, f' {label} {px:.2f}', color=color, fontsize=8, va='center')

    def scatter(ts, px, marker, color, label):
        x = mdates.date2num(pd.Timestamp(ts).tz_convert(NY).tz_convert(None).to_pydatetime())
        ax.scatter([x], [px], marker=marker, color=color, s=85, zorder=10, edgecolor='black', linewidth=0.8)
        ax.text(x, px, f' {label}', color=color, fontsize=8, va='bottom', ha='left')

    scatter(trade.break_time, trade.break_close, '^', '#AB47BC', 'break-in')
    scatter(trade.entry_time, trade.entry, 'o', '#E0E0E0', 'fill')
    for ts, reason, qty, px in getattr(trade, '_exits', []):
        scatter(ts, px, 'X', '#FFD54F' if reason != 'Stop' else '#EF5350', f'{reason} x{qty}')

    title = (
        f'{trade.market} weekly gap-fill strategy {trade.open_date} {trade.side} attempt {trade.attempt} '
        f'net ${trade.gross_usd:,.0f}'
    )
    subtitle = (
        f'Gap {trade.gap_pts:+.2f} pts · entry {trade.entry:.2f} · stop {trade.stop:.2f} · '
        f'exit {trade.exit_reason} · MAE {trade.mae_pts:.2f} / MFE {trade.mfe_pts:.2f}'
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
    ax.set_xlim(bars1h.index[0].tz_convert(None) - pd.Timedelta(hours=2), bars1h.index[-1].tz_convert(None) + pd.Timedelta(hours=4))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)
    return str(out_path)


def trade_to_dict(t: Trade) -> dict:
    out = t.__dict__.copy()
    out.pop('_exits', None)
    for key in ['break_time', 'order_live_time', 'entry_time', 'exit_time']:
        out[key] = pd.Timestamp(out[key]).isoformat()
    return out


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def write_report(
    out_dir: Path,
    market: str,
    trades: pd.DataFrame,
    skips: pd.DataFrame,
    point_value: float,
    stop_mode: str,
    move_stop_be_after_tp1: bool,
    boundary_close_exit: bool,
) -> None:
    net = float(trades['gross_usd'].sum()) if not trades.empty else 0.0
    dd = max_dd(trades['gross_usd']) if not trades.empty else 0.0
    wins = int((trades['gross_usd'] > 0).sum()) if not trades.empty else 0
    pf_loss = abs(float(trades.loc[trades['gross_usd'] < 0, 'gross_usd'].sum())) if not trades.empty else 0.0
    pf_gain = float(trades.loc[trades['gross_usd'] > 0, 'gross_usd'].sum()) if not trades.empty else 0.0
    pf = math.inf if pf_loss == 0 and pf_gain > 0 else (pf_gain / pf_loss if pf_loss else 0.0)

    by_reason = trades.groupby('exit_reason')['gross_usd'].agg(['count', 'sum', 'mean']).reset_index() if not trades.empty else pd.DataFrame()
    by_side = trades.groupby('side')['gross_usd'].agg(['count', 'sum', 'mean']).reset_index() if not trades.empty else pd.DataFrame()
    skip_counts = skips['reason'].value_counts().reset_index() if not skips.empty else pd.DataFrame(columns=['reason', 'count'])
    if not skip_counts.empty:
        skip_counts.columns = ['reason', 'count']

    lines = [
        f'# {market} Big Weekly Gap-Fill Strategy',
        '',
        'Rules: big weekly gaps only; 1-hour break-in close must be at least halfway to the prior weekly RTH close; then a limit at the break-in close is placed after that candle closes. Max two filled attempts per week. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, 2 off at TP2 one gap beyond TP1. Stop is the break-in candle low for longs or high for shorts.',
        '',
        f'Variant settings: stop mode = `{stop_mode}`; move remaining stop to breakeven after TP1 = `{move_stop_be_after_tp1}`; 1-hour close back outside gap boundary exit = `{boundary_close_exit}`.',
        '',
        f'Point value used: ${point_value:.2f}/pt.',
        '',
        '## Summary',
        '',
        '| Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Avg MFE |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|',
        f'| {len(trades)} | ${net:,.2f} | ${dd:,.2f} | {(wins / len(trades) * 100) if len(trades) else 0:.1f}% | {pf:.2f} | ${float(trades["gross_usd"].mean()) if len(trades) else 0:,.2f} | {float(trades["mae_pts"].mean()) if len(trades) else 0:.2f} | {float(trades["mfe_pts"].mean()) if len(trades) else 0:.2f} |',
        '',
        '## By Exit Reason',
        '',
        '| Exit | Trades | Net | Avg |',
        '|---|---:|---:|---:|',
    ]
    for _, row in by_reason.iterrows():
        lines.append(f'| {row["exit_reason"]} | {int(row["count"])} | ${float(row["sum"]):,.2f} | ${float(row["mean"]):,.2f} |')
    lines.extend(['', '## By Side', '', '| Side | Trades | Net | Avg |', '|---|---:|---:|---:|'])
    for _, row in by_side.iterrows():
        lines.append(f'| {row["side"]} | {int(row["count"])} | ${float(row["sum"]):,.2f} | ${float(row["mean"]):,.2f} |')
    lines.extend(['', '## Skips / No Trade Reasons', '', '| Reason | Count |', '|---|---:|'])
    for _, row in skip_counts.iterrows():
        lines.append(f'| {row["reason"]} | {int(row["count"])} |')
    lines.extend(
        [
            '',
            '## Files',
            '',
            '- `gap_fill_trades.csv`',
            '- `gap_fill_skips.csv`',
            '- `charts/INDEX.md` when charts are enabled',
            '',
        ]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def write_chart_indexes(chart_root: Path, market: str, trades: pd.DataFrame) -> None:
    if trades.empty:
        return
    work = trades[trades['chart'].astype(str).ne('')].copy()
    if work.empty:
        return
    work['year'] = pd.to_datetime(work['open_date']).dt.year.astype(int)
    for year, sub in work.groupby('year', sort=True):
        year_dir = chart_root / str(year)
        lines = [
            f'# {market} {year} gap-fill strategy charts',
            '',
            '| Week | Side | Attempt | Net | Exit | Chart |',
            '|---:|---|---:|---:|---|---|',
        ]
        for _, row in sub.sort_values(['open_date', 'attempt']).iterrows():
            chart_name = Path(str(row['chart'])).name
            lines.append(
                f'| {row["open_date"]} | {row["side"]} | {int(row["attempt"])} | ${float(row["gross_usd"]):,.2f} | '
                f'{row["exit_reason"]} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    lines = [f'# {market} gap-fill strategy charts', '', '| Year | Charts | Folder |', '|---:|---:|---|']
    for year, sub in work.groupby('year', sort=True):
        lines.append(f'| {year} | {len(sub)} | [{year}/]({year}/INDEX.md) |')
    lines.append('')
    (chart_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def infer_point_value(market: str) -> float:
    return 2.0 if market.upper() == 'MNQ' else 20.0 if market.upper() == 'NQ' else 1.0


def run(args: argparse.Namespace) -> pd.DataFrame:
    market = args.market.upper()
    point_value = args.point_value if args.point_value is not None else infer_point_value(market)
    annotated = pd.read_csv(args.annotated_weekly_csv).fillna('')
    gaps = annotated[annotated['point_size_bucket'].eq(args.bucket)].copy()
    gaps = gaps.sort_values('open_date')
    by_date = load_front_month_by_date(args.source_1m, market)
    by_week = build_week_windows(by_date)

    all_trades: list[Trade] = []
    all_skips: list[dict] = []
    for _, row in gaps.iterrows():
        trades, skips = simulate_week(
            row,
            by_week,
            point_value,
            args.max_trades,
            args.stop_mode,
            args.move_stop_be_after_tp1,
            args.boundary_close_exit,
        )
        all_trades.extend(trades)
        all_skips.extend(skips)

    chart_root = args.out / 'charts'
    trade_rows = []
    for trade in all_trades:
        year = pd.Timestamp(trade.open_date).year
        side_tag = 'long' if trade.side == 'Long' else 'short'
        out_path = chart_root / str(year) / f'{trade.open_date}_{side_tag}_attempt{trade.attempt}.png'
        path = draw_trade_chart(trade, by_week, out_path) if args.charts else ''
        trade.chart = str(Path(path).relative_to(chart_root)) if path else ''
        trade_rows.append(trade_to_dict(trade))

    trades_df = pd.DataFrame(trade_rows)
    skips_df = pd.DataFrame(all_skips)
    args.out.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(args.out / 'gap_fill_trades.csv', index=False)
    skips_df.to_csv(args.out / 'gap_fill_skips.csv', index=False)
    if args.charts:
        write_chart_indexes(chart_root, market, trades_df)
    write_report(
        args.out,
        market,
        trades_df,
        skips_df,
        point_value,
        args.stop_mode,
        args.move_stop_be_after_tp1,
        args.boundary_close_exit,
    )
    print(f'{market}: gaps={len(gaps)}, trades={len(trades_df)}, net=${trades_df["gross_usd"].sum() if not trades_df.empty else 0:,.2f}')
    print(f'Wrote {args.out / "README.md"}')
    return trades_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', required=True)
    ap.add_argument('--annotated-weekly-csv', type=Path, required=True)
    ap.add_argument('--source-1m', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--bucket', default='Big')
    ap.add_argument('--max-trades', type=int, default=2)
    ap.add_argument('--point-value', type=float)
    ap.add_argument('--stop-mode', choices=['break-candle', 'swing'], default='break-candle')
    ap.add_argument('--move-stop-be-after-tp1', action='store_true')
    ap.add_argument('--boundary-close-exit', action='store_true')
    ap.add_argument('--no-charts', dest='charts', action='store_false')
    ap.set_defaults(charts=True)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
