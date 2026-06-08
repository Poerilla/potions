#!/usr/bin/env python3
"""Backtest a delivery-change entry for big weekly gap fills.

Rules implemented:
- Use rows from weekly_gap_size_yorb.csv.
- Trade only rows with point_size_bucket == Big by default.
- Gap Down -> look for a Long back toward previous weekly RTH close.
- Gap Up -> look for a Short back toward previous weekly RTH close.
- Default setup: confirmed 1-hour swing high followed by confirmed 1-hour
  swing low for longs, or confirmed swing low followed by confirmed swing high
  for shorts. The order goes live after the second swing is confirmed.
- Optional legacy setup waits for a later higher-high/lower-low close through
  the prior swing while inside the weekly gap.
- Long entry is a limit at the highest open of the consecutive down-close
  1-hour candle run that forms the swing low. Stop is that run's lowest low.
- Short entry is a limit at the lowest open of the consecutive up-close
  1-hour candle run that forms the swing high. Stop is that run's highest high.
- Default size/targets match weekly_gap_fill_strategy.py:
    1 exits halfway from entry to TP1;
    2 exit at TP1, the prior weekly RTH close / gap fill;
    2 exit at TP2, one full gap beyond TP1.
- Optional scaleout exits 3 at halfway and 2 at TP1 with no TP2 runner.
- Optional 2:2:2 scaleout uses 6 units: 2 at halfway, 2 at TP1, and
  2 runners to same-day close with breakeven stop after TP1.
- Max 3 order attempts per signal day by default; max 2 filled trades per
  week by default.
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
import matplotlib.pyplot as plt
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hourly_gap_fill_analysis import load_front_month_by_date  # noqa: E402
from weekly_gap_fill_strategy import (  # noqa: E402
    build_week_windows,
    draw_candles,
    find_entry,
    gap_filled_in_window,
    gap_side,
    infer_point_value,
    max_dd,
    resample_1h,
    weekly_window,
)


@dataclass
class Pivot:
    kind: str
    pos: int
    time: pd.Timestamp
    confirm_time: pd.Timestamp
    value: float


@dataclass
class SourceRun:
    start_pos: int
    end_pos: int
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    entry: float
    stop: float


@dataclass
class Candidate:
    side: str
    signal_time: pd.Timestamp
    signal_close: float
    signal_high: float
    signal_low: float
    prev_swing_time: pd.Timestamp
    prev_swing_level: float
    structure_swing_time: pd.Timestamp
    structure_swing_level: float
    source: SourceRun


def ts_num(ts) -> float:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(None)
    return mdates.date2num(stamp.to_pydatetime())


def is_down(row: pd.Series) -> bool:
    return float(row['close']) < float(row['open'])


def is_up(row: pd.Series) -> bool:
    return float(row['close']) > float(row['open'])


def pivot_at(bars: pd.DataFrame, pivot_pos: int, confirm_pos: int) -> list[Pivot]:
    out: list[Pivot] = []
    if pivot_pos <= 0 or pivot_pos >= len(bars) - 1:
        return out
    highs = bars['high'].astype(float).to_list()
    lows = bars['low'].astype(float).to_list()
    idx = list(bars.index)
    pivot_time = pd.Timestamp(idx[pivot_pos]) + pd.Timedelta(hours=1)
    confirm_time = pd.Timestamp(idx[confirm_pos]) + pd.Timedelta(hours=1)
    if highs[pivot_pos] > highs[pivot_pos - 1] and highs[pivot_pos] > highs[pivot_pos + 1]:
        out.append(Pivot('high', pivot_pos, pivot_time, confirm_time, highs[pivot_pos]))
    if lows[pivot_pos] < lows[pivot_pos - 1] and lows[pivot_pos] < lows[pivot_pos + 1]:
        out.append(Pivot('low', pivot_pos, pivot_time, confirm_time, lows[pivot_pos]))
    return out


def source_run_for_pivot(bars: pd.DataFrame, pivot_pos: int, side: str) -> SourceRun | None:
    if pivot_pos < 0 or pivot_pos >= len(bars):
        return None
    checker = is_down if side == 'Long' else is_up
    if not checker(bars.iloc[pivot_pos]):
        return None
    start = pivot_pos
    while start > 0 and checker(bars.iloc[start - 1]):
        start -= 1
    run = bars.iloc[start : pivot_pos + 1]
    idx = list(bars.index)
    start_time = pd.Timestamp(idx[start])
    end_time = pd.Timestamp(idx[pivot_pos]) + pd.Timedelta(hours=1)
    if side == 'Long':
        entry = float(run['open'].astype(float).max())
        stop = float(run['low'].astype(float).min())
        if stop >= entry:
            return None
    else:
        entry = float(run['open'].astype(float).min())
        stop = float(run['high'].astype(float).max())
        if stop <= entry:
            return None
    return SourceRun(start, pivot_pos, start_time, end_time, entry, stop)


def close_inside_gap(side: str, close_px: float, week_open: float, prev_close: float) -> bool:
    if side == 'Long':
        return week_open < close_px < prev_close
    return prev_close < close_px < week_open


def simulate_exit_scaled(
    df1: pd.DataFrame,
    side: str,
    entry_time: pd.Timestamp,
    entry: float,
    stop: float,
    tp_half: float,
    tp1: float,
    tp2: float,
    point_value: float,
    scaleout_mode: str,
) -> dict:
    qty_start = 6 if scaleout_mode == 'two_two_two_eod_be' else 5
    qty_rem = qty_start
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

    half_qty = 1 if scaleout_mode == 'classic' else 2 if scaleout_mode == 'two_two_two_eod_be' else 3
    tp1_qty = 2
    use_tp2 = scaleout_mode == 'classic'
    use_eod_runner = scaleout_mode == 'two_two_two_eod_be'
    eod_time: pd.Timestamp | None = None
    if use_eod_runner:
        same_day = df1[df1.index.date == pd.Timestamp(entry_time).date()]
        if not same_day.empty:
            eod_time = pd.Timestamp(same_day.index[-1])

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
                take = min(half_qty, qty_rem)
                qty_half = take
                qty_rem -= take
                exits.append((pd.Timestamp(ts), 'Halfway', take, tp_half))
            if qty_tp1 == 0 and high >= tp1:
                take = min(tp1_qty, qty_rem)
                qty_tp1 = take
                qty_rem -= take
                exits.append((pd.Timestamp(ts), 'TP1', take, tp1))
                if use_eod_runner and qty_rem > 0:
                    activate_be_next_bar = True
                if not use_tp2 or qty_rem == 0:
                    if not use_eod_runner:
                        exit_time = pd.Timestamp(ts)
                        exit_reason = 'TP1'
                        break
            if use_tp2 and qty_tp2 == 0 and high >= tp2:
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
                take = min(half_qty, qty_rem)
                qty_half = take
                qty_rem -= take
                exits.append((pd.Timestamp(ts), 'Halfway', take, tp_half))
            if qty_tp1 == 0 and low <= tp1:
                take = min(tp1_qty, qty_rem)
                qty_tp1 = take
                qty_rem -= take
                exits.append((pd.Timestamp(ts), 'TP1', take, tp1))
                if use_eod_runner and qty_rem > 0:
                    activate_be_next_bar = True
                if not use_tp2 or qty_rem == 0:
                    if not use_eod_runner:
                        exit_time = pd.Timestamp(ts)
                        exit_reason = 'TP1'
                        break
            if use_tp2 and qty_tp2 == 0 and low <= tp2:
                take = qty_rem
                qty_tp2 = take
                qty_rem = 0
                exits.append((pd.Timestamp(ts), 'TP2', take, tp2))
                exit_time = pd.Timestamp(ts)
                exit_reason = 'TP2'
                break

        if use_eod_runner and eod_time is not None and pd.Timestamp(ts) >= eod_time and qty_rem > 0:
            qty_eow = qty_rem
            eod_close = float(row['close'])
            exits.append((pd.Timestamp(ts), 'EOD', qty_rem, eod_close))
            qty_rem = 0
            exit_time = pd.Timestamp(ts)
            exit_reason = 'EOD'
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
        'qty_start': qty_start,
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


def candidate_search(
    df1: pd.DataFrame,
    bars1h: pd.DataFrame,
    side: str,
    search_after: pd.Timestamp,
    week_open: float,
    prev_close: float,
    attempts_by_day: dict,
    max_attempts_per_day: int,
    entry_mode: str,
) -> tuple[Candidate | None, str]:
    last_swing_high: Pivot | None = None
    last_swing_low: Pivot | None = None
    active_long: tuple[Pivot, Pivot, SourceRun] | None = None
    active_short: tuple[Pivot, Pivot, SourceRun] | None = None
    last_gap_check = search_after

    for pos, (bar_left, bar) in enumerate(bars1h.iterrows()):
        bar_left = pd.Timestamp(bar_left)
        bar_end = bar_left + pd.Timedelta(hours=1)
        immediate_candidate: Candidate | None = None
        if pos >= 2:
            for pivot in pivot_at(bars1h, pos - 1, pos):
                if pivot.kind == 'high':
                    last_swing_high = pivot
                    if side == 'Short' and last_swing_low is not None and last_swing_low.time < pivot.time:
                        source = source_run_for_pivot(bars1h, pivot.pos, side)
                        if source is not None:
                            active_short = (last_swing_low, pivot, source)
                            if entry_mode == 'swing-sequence':
                                immediate_candidate = Candidate(
                                    side,
                                    bar_end,
                                    float(bar['close']),
                                    float(bar['high']),
                                    float(bar['low']),
                                    last_swing_low.time,
                                    last_swing_low.value,
                                    pivot.time,
                                    pivot.value,
                                    source,
                                )
                elif pivot.kind == 'low':
                    last_swing_low = pivot
                    if side == 'Long' and last_swing_high is not None and last_swing_high.time < pivot.time:
                        source = source_run_for_pivot(bars1h, pivot.pos, side)
                        if source is not None:
                            active_long = (last_swing_high, pivot, source)
                            if entry_mode == 'swing-sequence':
                                immediate_candidate = Candidate(
                                    side,
                                    bar_end,
                                    float(bar['close']),
                                    float(bar['high']),
                                    float(bar['low']),
                                    last_swing_high.time,
                                    last_swing_high.value,
                                    pivot.time,
                                    pivot.value,
                                    source,
                                )

        if bar_end <= search_after:
            continue

        check_start = max(last_gap_check, bar_left)
        pre_window = df1[(df1.index >= check_start) & (df1.index < bar_end)]
        if gap_filled_in_window(pre_window, side, prev_close):
            return None, 'gap_filled_before_delivery_change'
        last_gap_check = bar_end

        close_px = float(bar['close'])
        high_px = float(bar['high'])
        low_px = float(bar['low'])
        signal_day = bar_end.date().isoformat()
        if attempts_by_day.get(signal_day, 0) >= max_attempts_per_day:
            continue

        if entry_mode == 'swing-sequence' and immediate_candidate is not None:
            return immediate_candidate, 'candidate'

        if entry_mode == 'break-close' and side == 'Long' and active_long is not None:
            prev_high, swing_low, source = active_long
            if high_px > prev_high.value and close_px > prev_high.value and close_inside_gap(side, close_px, week_open, prev_close):
                return (
                    Candidate(
                        side,
                        bar_end,
                        close_px,
                        high_px,
                        low_px,
                        prev_high.time,
                        prev_high.value,
                        swing_low.time,
                        swing_low.value,
                        source,
                    ),
                    'candidate',
                )
        elif entry_mode == 'break-close' and side == 'Short' and active_short is not None:
            prev_low, swing_high, source = active_short
            if low_px < prev_low.value and close_px < prev_low.value and close_inside_gap(side, close_px, week_open, prev_close):
                return (
                    Candidate(
                        side,
                        bar_end,
                        close_px,
                        high_px,
                        low_px,
                        prev_low.time,
                        prev_low.value,
                        swing_high.time,
                        swing_high.value,
                        source,
                    ),
                    'candidate',
                )

    return None, 'no_delivery_change'


def simulate_week(
    row: pd.Series,
    by_week: dict,
    point_value: float,
    max_attempts_per_day: int,
    max_trades_per_week: int,
    entry_mode: str,
    scaleout_mode: str,
) -> tuple[list[dict], list[dict]]:
    market = str(row['market'])
    open_date = pd.Timestamp(row['open_date']).date()
    df1 = weekly_window(by_week, open_date)
    if df1.empty:
        return [], [{'open_date': open_date.isoformat(), 'reason': 'missing_week_data'}]

    bars1h = resample_1h(df1)
    if bars1h.empty:
        return [], [{'open_date': open_date.isoformat(), 'reason': 'missing_1h_data'}]

    side, side_mult = gap_side(row)
    gap_size = abs(float(row['gap_pts']))
    week_open = float(row['open_px'])
    prev_close = float(row['prev_close'])
    tp1 = prev_close
    tp2 = prev_close + gap_size if side == 'Long' else prev_close - gap_size
    search_after = df1.index[0]
    attempts_by_day: dict[str, int] = {}
    trades: list[dict] = []
    skips: list[dict] = []

    while len(trades) < max_trades_per_week:
        candidate, status = candidate_search(
            df1,
            bars1h,
            side,
            search_after,
            week_open,
            prev_close,
            attempts_by_day,
            max_attempts_per_day,
            entry_mode,
        )
        if candidate is None:
            skips.append({'open_date': open_date.isoformat(), 'reason': status})
            break

        signal_day = candidate.signal_time.date().isoformat()
        attempts_by_day[signal_day] = attempts_by_day.get(signal_day, 0) + 1
        day_attempt = attempts_by_day[signal_day]
        entry = candidate.source.entry
        stop = candidate.source.stop
        if side == 'Long' and stop >= entry:
            skips.append({'open_date': open_date.isoformat(), 'reason': 'invalid_long_stop', 'signal_time': candidate.signal_time.isoformat()})
            search_after = candidate.signal_time + pd.Timedelta(minutes=1)
            continue
        if side == 'Short' and stop <= entry:
            skips.append({'open_date': open_date.isoformat(), 'reason': 'invalid_short_stop', 'signal_time': candidate.signal_time.isoformat()})
            search_after = candidate.signal_time + pd.Timedelta(minutes=1)
            continue

        entry_time, fill_status = find_entry(df1, side, entry, candidate.signal_time, tp1)
        if entry_time is None:
            skips.append(
                {
                    'open_date': open_date.isoformat(),
                    'reason': fill_status,
                    'signal_time': candidate.signal_time.isoformat(),
                    'entry': entry,
                }
            )
            break

        tp_half = entry + side_mult * abs(tp1 - entry) * 0.5
        exit_result = simulate_exit_scaled(
            df1,
            side,
            entry_time,
            entry,
            stop,
            tp_half,
            tp1,
            tp2,
            point_value,
            scaleout_mode,
        )
        trade = {
            'market': market,
            'open_date': open_date.isoformat(),
            'prev_close_date': str(row['prev_close_date']),
            'direction': str(row['direction']),
            'side': side,
            'entry_mode': entry_mode,
            'scaleout_mode': scaleout_mode,
            'signal_day_attempt': day_attempt,
            'week_trade_num': len(trades) + 1,
            'gap_pts': float(row['gap_pts']),
            'abs_gap_pts': gap_size,
            'prev_close': prev_close,
            'week_open': week_open,
            'prev_swing_time': candidate.prev_swing_time.isoformat(),
            'prev_swing_level': candidate.prev_swing_level,
            'structure_swing_time': candidate.structure_swing_time.isoformat(),
            'structure_swing_level': candidate.structure_swing_level,
            'source_start_time': candidate.source.start_time.isoformat(),
            'source_end_time': candidate.source.end_time.isoformat(),
            'signal_time': candidate.signal_time.isoformat(),
            'signal_close': candidate.signal_close,
            'signal_high': candidate.signal_high,
            'signal_low': candidate.signal_low,
            'order_live_time': candidate.signal_time.isoformat(),
            'entry_time': pd.Timestamp(entry_time).isoformat(),
            'entry': entry,
            'stop': stop,
            'tp_half': tp_half,
            'tp1': tp1,
            'tp2': tp2,
            'exit_time': pd.Timestamp(exit_result['exit_time']).isoformat(),
            'exit_reason': exit_result['exit_reason'],
            'exit_events': ';'.join(
                f'{pd.Timestamp(ts).isoformat()}|{reason}|{qty}|{float(px):.2f}'
                for ts, reason, qty, px in exit_result['exits']
            ),
            'qty_start': exit_result['qty_start'],
            'qty_half': exit_result['qty_half'],
            'qty_tp1': exit_result['qty_tp1'],
            'qty_tp2': exit_result['qty_tp2'],
            'qty_stop': exit_result['qty_stop'],
            'qty_boundary_close': exit_result['qty_boundary_close'],
            'qty_eow': exit_result['qty_eow'],
            'gross_pts': exit_result['gross_pts'],
            'gross_usd': exit_result['gross_usd'],
            'mae_pts': exit_result['mae_pts'],
            'mfe_pts': exit_result['mfe_pts'],
        }
        trades.append(trade)
        search_after = pd.Timestamp(exit_result['exit_time']) + pd.Timedelta(minutes=1)
        if exit_result['qty_tp1'] > 0 or exit_result['exit_reason'] in {'TP2', 'EOW'}:
            break

    if len(trades) >= max_trades_per_week:
        skips.append({'open_date': open_date.isoformat(), 'reason': 'max_week_trades_reached'})

    return trades, skips


def parse_exit_events(text: str) -> list[tuple[pd.Timestamp, str, int, float]]:
    events: list[tuple[pd.Timestamp, str, int, float]] = []
    if not isinstance(text, str) or not text:
        return events
    for piece in text.split(';'):
        parts = piece.split('|')
        if len(parts) != 4:
            continue
        events.append((pd.Timestamp(parts[0]), parts[1], int(parts[2]), float(parts[3])))
    return events


def draw_delivery_chart(row: pd.Series, by_week: dict, out_path: Path) -> str:
    open_date = pd.Timestamp(row['open_date']).date()
    df1 = weekly_window(by_week, open_date)
    bars1h = resample_1h(df1)
    if bars1h.empty:
        return ''

    fig = plt.figure(figsize=(18, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars1h)

    levels = [
        ('Prev close / TP1', float(row['prev_close']), '#FFD54F', '--'),
        ('Week open', float(row['week_open']), '#78909C', ':'),
        ('Entry', float(row['entry']), '#E0E0E0', '-'),
        ('Stop', float(row['stop']), '#EF5350', '-'),
        ('Half', float(row['tp_half']), '#80CBC4', ':'),
        ('TP2', float(row['tp2']), '#4FC3F7', '--'),
    ]
    for label, px, color, style in levels:
        ax.axhline(px, color=color, linestyle=style, linewidth=1.0, zorder=2)
    x_right = ts_num(bars1h.index[-1]) + 0.08
    for label, px, color, _ in levels:
        ax.text(x_right, px, f' {label} {px:.2f}', color=color, fontsize=8, va='center')

    source_start = ts_num(row['source_start_time'])
    source_end = ts_num(row['source_end_time'])
    ax.axvspan(source_start, source_end, color='#AB47BC', alpha=0.16, zorder=1)

    def scatter(ts, px, marker, color, label, size=95):
        x = ts_num(ts)
        ax.scatter([x], [float(px)], marker=marker, color=color, s=size, zorder=10, edgecolor='black', linewidth=0.8)
        ax.text(x, float(px), f' {label}', color=color, fontsize=8, va='bottom', ha='left')

    side = str(row['side'])
    if side == 'Long':
        scatter(row['prev_swing_time'], row['prev_swing_level'], '^', '#BA68C8', 'prior swing high')
        scatter(row['structure_swing_time'], row['structure_swing_level'], 'v', '#4DB6AC', 'swing low')
    else:
        scatter(row['prev_swing_time'], row['prev_swing_level'], 'v', '#BA68C8', 'prior swing low')
        scatter(row['structure_swing_time'], row['structure_swing_level'], '^', '#4DB6AC', 'swing high')
    scatter(row['signal_time'], row['signal_close'], 'D', '#FFB74D', 'delivery close')
    scatter(row['entry_time'], row['entry'], 'o', '#E0E0E0', 'fill')

    for ts, reason, qty, px in parse_exit_events(str(row.get('exit_events', ''))):
        color = '#EF5350' if 'Stop' in reason else '#FFD54F'
        scatter(ts, px, 'X', color, f'{reason} x{qty}', size=85)

    title = (
        f'{row["market"]} weekly gap delivery-change {row["open_date"]} {side} '
        f'net ${float(row["gross_usd"]):,.0f}'
    )
    subtitle = (
        f'Gap {float(row["gap_pts"]):+.2f} pts · source run shaded · entry {float(row["entry"]):.2f} · '
        f'stop {float(row["stop"]):.2f} · exit {row["exit_reason"]} · '
        f'MAE {float(row["mae_pts"]):.2f} / MFE {float(row["mfe_pts"]):.2f}'
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


def write_chart_indexes(chart_root: Path, market: str, trades: pd.DataFrame) -> None:
    if trades.empty or 'chart' not in trades.columns:
        return
    work = trades[trades['chart'].astype(str).ne('')].copy()
    if work.empty:
        return
    work['year'] = pd.to_datetime(work['open_date']).dt.year.astype(int)
    for year, sub in work.groupby('year', sort=True):
        year_dir = chart_root / str(year)
        lines = [
            f'# {market} {year} delivery-change charts',
            '',
            '| Week | Side | Net | Exit | Chart |',
            '|---:|---|---:|---|---|',
        ]
        for _, row in sub.sort_values(['open_date', 'signal_time']).iterrows():
            chart_name = Path(str(row['chart'])).name
            lines.append(
                f'| {row["open_date"]} | {row["side"]} | ${float(row["gross_usd"]):,.2f} | '
                f'{row["exit_reason"]} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    lines = [f'# {market} delivery-change charts', '', '| Year | Charts | Folder |', '|---:|---:|---|']
    for year, sub in work.groupby('year', sort=True):
        lines.append(f'| {year} | {len(sub)} | [{year}/]({year}/INDEX.md) |')
    lines.append('')
    (chart_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def write_outcome_chart_indexes(chart_root: Path, market: str, trades: pd.DataFrame) -> None:
    if trades.empty or 'chart' not in trades.columns:
        return
    work = trades[trades['chart'].astype(str).ne('')].copy()
    if work.empty:
        return
    groups = [('winners', work[work['gross_usd'].astype(float) > 0]), ('losers', work[work['gross_usd'].astype(float) <= 0])]
    for folder, sub in groups:
        lines = [
            f'# {market} {folder} delivery-change charts',
            '',
            '| Week | Side | Net | Exit | Chart |',
            '|---:|---|---:|---|---|',
        ]
        for _, row in sub.sort_values(['open_date', 'signal_time']).iterrows():
            chart_name = Path(str(row['chart'])).name
            lines.append(
                f'| {row["open_date"]} | {row["side"]} | ${float(row["gross_usd"]):,.2f} | '
                f'{row["exit_reason"]} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (chart_root / folder).mkdir(parents=True, exist_ok=True)
        (chart_root / folder / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    lines = [
        f'# {market} delivery-change outcome charts',
        '',
        '| Bucket | Charts | Folder |',
        '|---|---:|---|',
    ]
    for folder, sub in groups:
        lines.append(f'| {folder.title()} | {len(sub)} | [{folder}/]({folder}/INDEX.md) |')
    lines.append('')
    (chart_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def write_report(
    out_dir: Path,
    market: str,
    trades: pd.DataFrame,
    skips: pd.DataFrame,
    point_value: float,
    entry_mode: str,
    max_attempts_per_day: int,
    max_trades_per_week: int,
    scaleout_mode: str,
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
        f'# {market} Big Weekly Gap Delivery-Change Strategy',
        '',
        'Rules: big weekly gaps only; wait for completed 1-hour delivery structure before placing the pullback limit. `swing-sequence` mode places the order after swing high -> swing low for longs, or swing low -> swing high for shorts. `break-close` mode waits for the older higher-high/lower-low close-through trigger.',
        '',
        'Entry source: longs use the highest open of the consecutive down-close 1-hour candle run that forms the swing low; shorts use the lowest open of the consecutive up-close run that forms the swing high. Stop is the opposite extreme of that source run.',
        '',
        f'Variant settings: entry mode = `{entry_mode}`; scaleout mode = `{scaleout_mode}`; max attempts per day = `{max_attempts_per_day}`; max filled trades per week = `{max_trades_per_week}`.',
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
    lines.extend(['', '## Files', '', '- `gap_delivery_trades.csv`', '- `gap_delivery_skips.csv`', '- `charts/INDEX.md` when charts are enabled', ''])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def run(args: argparse.Namespace) -> pd.DataFrame:
    market = args.market.upper()
    point_value = args.point_value if args.point_value is not None else infer_point_value(market)
    annotated = pd.read_csv(args.annotated_weekly_csv).fillna('')
    gaps = annotated[annotated['point_size_bucket'].eq(args.bucket)].copy().sort_values('open_date')
    by_date = load_front_month_by_date(args.source_1m, market)
    by_week = build_week_windows(by_date)

    all_trades: list[dict] = []
    all_skips: list[dict] = []
    for _, row in gaps.iterrows():
        trades, skips = simulate_week(
            row,
            by_week,
            point_value,
            args.max_attempts_per_day,
            args.max_trades_per_week,
            args.entry_mode,
            args.scaleout_mode,
        )
        all_trades.extend(trades)
        all_skips.extend(skips)

    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty and args.side != 'both':
        wanted_side = 'Short' if args.side == 'short' else 'Long'
        trades_df = trades_df[trades_df['side'].eq(wanted_side)].copy()
    skips_df = pd.DataFrame(all_skips)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.charts and not trades_df.empty:
        chart_root = args.out / 'charts'
        chart_paths: list[str] = []
        for chart_idx, row in trades_df.iterrows():
            year = pd.Timestamp(row['open_date']).year
            side_tag = 'long' if row['side'] == 'Long' else 'short'
            if args.chart_layout == 'outcome':
                outcome = 'winners' if float(row['gross_usd']) > 0 else 'losers'
                out_path = chart_root / outcome / f'{row["open_date"]}_{side_tag}_{chart_idx + 1:03d}.png'
            else:
                out_path = chart_root / str(year) / f'{row["open_date"]}_{side_tag}_{chart_idx + 1:03d}.png'
            path = draw_delivery_chart(row, by_week, out_path)
            chart_paths.append(str(Path(path).relative_to(chart_root)) if path else '')
        trades_df['chart'] = chart_paths
        if args.chart_layout == 'outcome':
            write_outcome_chart_indexes(chart_root, market, trades_df)
        else:
            write_chart_indexes(chart_root, market, trades_df)
    trades_df.to_csv(args.out / 'gap_delivery_trades.csv', index=False)
    skips_df.to_csv(args.out / 'gap_delivery_skips.csv', index=False)
    write_report(
        args.out,
        market,
        trades_df,
        skips_df,
        point_value,
        args.entry_mode,
        args.max_attempts_per_day,
        args.max_trades_per_week,
        args.scaleout_mode,
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
    ap.add_argument('--max-attempts-per-day', type=int, default=3)
    ap.add_argument('--max-trades-per-week', type=int, default=2)
    ap.add_argument('--entry-mode', choices=['swing-sequence', 'break-close'], default='swing-sequence')
    ap.add_argument('--scaleout-mode', choices=['classic', 'half3_tp1_2', 'two_two_two_eod_be'], default='classic')
    ap.add_argument('--side', choices=['both', 'long', 'short'], default='both')
    ap.add_argument('--chart-layout', choices=['year', 'outcome'], default='year')
    ap.add_argument('--point-value', type=float)
    ap.add_argument('--charts', action='store_true')
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
