#!/usr/bin/env python3
"""Yearly ORB candidate with delivery-state scale-ins.

This study keeps the current yearly ORB leader intact:
- Jan-Mar defines the yearly opening range.
- Apr-Dec trades boundary retests after daily closes outside the range.
- Stop source is the latest confirmed swing, optionally inside the range.
- Base position stays 3 units: TP25, TP, runner.
- Optional range-close exit behaves like the current candidate.

The extra study layer adds one delivery scale-in at a time:
- Long add signal: close above the highest confirmed swing high above the
  yearly range high after the base entry.
- Short add signal: close below the lowest confirmed swing low below the
  yearly range low after the base entry.
- The scale-in order is a next-bar limit at the signal candle close.
- Long scale stop is the low of the leg that formed the broken swing high.
- Short scale stop is the high of the leg that formed the broken swing low.
- Scale target is 2R from the scale entry.
- Pending scale-ins are cancelled if the base yearly ORB TP is reached first.

This is still daily-OHLC research. Same-day ordering is conservative:
base stops are processed before base targets, pending scale-ins are cancelled
if the yearly ORB TP is reached on that bar, and scale-in stops are processed
before scale-in targets.
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

from yearly_orb_swing_stop_scaleout3 import (
    IN_TRADE,
    WAIT_BREAKOUT,
    WAIT_FILL,
    ScaleTrade,
    SwingPoint,
    build_swings,
    classify_trade,
    close_units,
    latest_valid_swing,
    max_dd,
    order_prices,
    process_open_trade,
    start_trade,
    valid_entry_target,
)


def build_weekly_swings_on_daily(work: pd.DataFrame) -> list[SwingPoint]:
    """Build confirmed weekly pivots, expressed in daily-row coordinates."""
    daily = work.copy().sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])
    daily['_idx'] = daily.index
    daily['_week'] = daily['date'].dt.to_period('W-FRI')
    weekly_rows: list[dict] = []
    for _, group in daily.groupby('_week', sort=True):
        high_idx = int(group['high'].astype(float).idxmax())
        low_idx = int(group['low'].astype(float).idxmin())
        weekly_rows.append(
            {
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


@dataclass
class DeliveryScaleOrder:
    period: str
    direction: str
    scale_id: int
    signal_idx: int
    signal_date: pd.Timestamp
    signal_close: float
    swing_key: tuple[str, int, int, float]
    swing_date: pd.Timestamp
    swing_value: float
    leg_start_date: pd.Timestamp
    leg_stop_date: pd.Timestamp
    entry: float
    stop: float
    target: float
    scale_swing_timeframe: str
    status: str = 'Pending'
    fill_date: Optional[pd.Timestamp] = None
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pl: float = 0.0
    mae_pts: float = 0.0
    mfe_pts: float = 0.0


@dataclass
class TradeBundle:
    base: ScaleTrade
    addons: list[DeliveryScaleOrder]

    @property
    def base_points(self) -> float:
        return self.base.net_points

    @property
    def addon_points(self) -> float:
        return sum(order.pl for order in self.addons)

    @property
    def total_points(self) -> float:
        return self.base_points + self.addon_points


def swing_key(swing: SwingPoint) -> tuple[str, int, int, float]:
    return (swing.kind, int(swing.pivot_idx), int(swing.confirm_idx), round(float(swing.value), 6))


def scale_pl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def close_scale_order(order: DeliveryScaleOrder, date: pd.Timestamp, price: float, reason: str) -> None:
    if order.status == 'Closed':
        return
    order.status = 'Closed'
    order.exit_date = date
    order.exit_price = price
    order.exit_reason = reason
    order.pl = scale_pl(order.direction, order.entry, price)


def cancel_scale_order(order: DeliveryScaleOrder, date: pd.Timestamp, reason: str) -> None:
    if order.status in ('Closed', 'Cancelled'):
        return
    order.status = 'Cancelled'
    order.exit_date = date
    order.exit_reason = reason


def update_scale_excursion(order: DeliveryScaleOrder, high: float, low: float) -> None:
    if order.status != 'Open':
        return
    if order.direction == 'Long':
        adverse = max(0.0, order.entry - low)
        favorable = max(0.0, high - order.entry)
    else:
        adverse = max(0.0, high - order.entry)
        favorable = max(0.0, order.entry - low)
    order.mae_pts = max(order.mae_pts, adverse)
    order.mfe_pts = max(order.mfe_pts, favorable)


def process_scale_order(order: DeliveryScaleOrder, bar: pd.Series) -> None:
    d = pd.Timestamp(bar['date'])
    h = float(bar['high'])
    l = float(bar['low'])

    if order.status == 'Pending':
        if order.direction == 'Long' and l <= order.entry:
            order.status = 'Open'
            order.fill_date = d
        elif order.direction == 'Short' and h >= order.entry:
            order.status = 'Open'
            order.fill_date = d
        else:
            return

    update_scale_excursion(order, h, l)
    if order.direction == 'Long':
        if l <= order.stop:
            close_scale_order(order, d, order.stop, 'Scale-Stop')
            return
        if h >= order.target:
            close_scale_order(order, d, order.target, 'Scale-TP2R')
            return
    else:
        if h >= order.stop:
            close_scale_order(order, d, order.stop, 'Scale-Stop')
            return
        if l <= order.target:
            close_scale_order(order, d, order.target, 'Scale-TP2R')
            return


def previous_opposite_swing(
    swings: list[SwingPoint],
    direction: str,
    signal_swing: SwingPoint,
    min_idx: int,
) -> Optional[SwingPoint]:
    needed = 'low' if direction == 'Long' else 'high'
    prior = [
        swing
        for swing in swings
        if swing.kind == needed
        and swing.pivot_idx < signal_swing.pivot_idx
        and swing.pivot_idx >= min_idx
        and swing.confirm_idx < signal_swing.confirm_idx
    ]
    return prior[-1] if prior else None


def leg_stop(
    work: pd.DataFrame,
    swings: list[SwingPoint],
    direction: str,
    signal_swing: SwingPoint,
    min_idx: int,
) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    prior = previous_opposite_swing(swings, direction, signal_swing, min_idx)
    start_idx = prior.pivot_idx if prior is not None else max(min_idx, signal_swing.pivot_idx - 5)
    stop_slice = work.iloc[start_idx : signal_swing.pivot_idx + 1]
    if direction == 'Long':
        stop_idx = int(stop_slice['low'].astype(float).idxmin())
        stop_price = float(work.loc[stop_idx, 'low'])
    else:
        stop_idx = int(stop_slice['high'].astype(float).idxmax())
        stop_price = float(work.loc[stop_idx, 'high'])
    return stop_price, pd.Timestamp(work.loc[start_idx, 'date']), pd.Timestamp(work.loc[stop_idx, 'date'])


def find_delivery_signal(
    work: pd.DataFrame,
    swings: list[SwingPoint],
    idx: int,
    direction: str,
    range_high: float,
    range_low: float,
    min_confirm_idx: int,
    used: set[tuple[str, int, int, float]],
) -> Optional[SwingPoint]:
    c = float(work.loc[idx, 'close'])
    candidates: list[SwingPoint] = []
    for swing in swings:
        key = swing_key(swing)
        if key in used:
            continue
        if swing.confirm_idx >= idx or swing.confirm_idx < min_confirm_idx or swing.pivot_idx < min_confirm_idx:
            continue
        if direction == 'Long':
            if swing.kind == 'high' and swing.value > range_high and c > swing.value:
                candidates.append(swing)
        else:
            if swing.kind == 'low' and swing.value < range_low and c < swing.value:
                candidates.append(swing)
    if not candidates:
        return None
    if direction == 'Long':
        return max(candidates, key=lambda swing: (swing.value, swing.confirm_idx))
    return min(candidates, key=lambda swing: (swing.value, -swing.confirm_idx))


def make_scale_order(
    period: str,
    work: pd.DataFrame,
    swings: list[SwingPoint],
    idx: int,
    direction: str,
    signal_swing: SwingPoint,
    min_idx: int,
    scale_id: int,
    scale_swing_timeframe: str,
) -> Optional[DeliveryScaleOrder]:
    signal_date = pd.Timestamp(work.loc[idx, 'date'])
    entry = float(work.loc[idx, 'close'])
    stop, leg_start_date, leg_stop_date = leg_stop(work, swings, direction, signal_swing, min_idx)
    if direction == 'Long':
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + risk * 2.0
    else:
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - risk * 2.0

    return DeliveryScaleOrder(
        period=period,
        direction=direction,
        scale_id=scale_id,
        signal_idx=idx,
        signal_date=signal_date,
        signal_close=entry,
        swing_key=swing_key(signal_swing),
        swing_date=signal_swing.pivot_date,
        swing_value=float(signal_swing.value),
        leg_start_date=leg_start_date,
        leg_stop_date=leg_stop_date,
        entry=entry,
        stop=stop,
        target=target,
        scale_swing_timeframe=scale_swing_timeframe,
    )


def unit2_tp_seen(trade: ScaleTrade) -> bool:
    return any(ex.unit == 2 and ex.reason == 'TP' for ex in trade.exits)


def simulate_year_with_scaleins(
    period: str,
    bars: pd.DataFrame,
    range_close_exit: bool,
    entry_mode: str,
    stop_swing_scope: str,
    scale_swing_timeframe: str = 'daily',
) -> tuple[list[TradeBundle], dict]:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    range_bars = work[work['month'] <= 3].copy()
    trade_bars = work[work['month'] > 3].copy()
    symbol = str(work.iloc[0]['symbol'])
    meta = {
        'period': period,
        'symbol': symbol,
        'range_days': len(range_bars),
        'trade_days': len(trade_bars),
    }
    if range_bars.empty or trade_bars.empty:
        return [], meta

    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    meta.update({'range_high': range_high, 'range_low': range_low, 'range': range_val, 'scale_swing_timeframe': scale_swing_timeframe})
    if range_val <= 0:
        return [], meta

    base_swings = build_swings(work)
    scale_swings = build_weekly_swings_on_daily(work) if scale_swing_timeframe == 'weekly' else base_swings
    phase = WAIT_BREAKOUT
    armed_direction: Optional[str] = None
    armed_entry: Optional[float] = None
    armed_target: Optional[float] = None
    armed_breakout_date: Optional[pd.Timestamp] = None
    armed_breakout_close: Optional[float] = None
    trade: Optional[ScaleTrade] = None
    trade_entry_idx: Optional[int] = None
    active_order: Optional[DeliveryScaleOrder] = None
    addons: list[DeliveryScaleOrder] = []
    used_scale_swings: set[tuple[str, int, int, float]] = set()
    next_scale_id = 1
    base_tp_locked = False
    bundles: list[TradeBundle] = []

    def begin_trade(
        direction: str,
        entry: float,
        target: float,
        stop_swing: SwingPoint,
        idx: int,
        date: pd.Timestamp,
        close: float,
    ) -> ScaleTrade:
        nonlocal active_order, addons, used_scale_swings, next_scale_id, base_tp_locked, trade_entry_idx
        active_order = None
        addons = []
        used_scale_swings = set()
        next_scale_id = 1
        base_tp_locked = False
        trade_entry_idx = idx
        return start_trade(
            period,
            direction,
            entry,
            target,
            stop_swing.value,
            stop_swing,
            date,
            entry_mode,
            stop_swing_scope,
            armed_breakout_date or date,
            armed_breakout_close if armed_breakout_close is not None else close,
        )

    def finish_trade(date: pd.Timestamp, close: float, reason: str) -> None:
        nonlocal trade, active_order, phase, armed_direction, armed_entry, armed_target
        nonlocal armed_breakout_date, armed_breakout_close, trade_entry_idx, base_tp_locked
        if active_order is not None:
            if active_order.status == 'Open':
                close_scale_order(active_order, date, close, reason)
            elif active_order.status == 'Pending':
                cancel_scale_order(active_order, date, reason)
        if trade is not None:
            bundles.append(TradeBundle(trade, list(addons)))
        trade = None
        active_order = None
        phase = WAIT_BREAKOUT
        armed_direction = None
        armed_entry = armed_target = armed_breakout_date = armed_breakout_close = None
        trade_entry_idx = None
        base_tp_locked = False

    for idx, bar in work.iterrows():
        if int(bar['month']) <= 3:
            continue

        h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])
        d = pd.Timestamp(bar['date'])

        if phase == WAIT_FILL and armed_direction is not None and armed_entry is not None and armed_target is not None:
            filled = False
            if armed_direction == 'Long' and l <= armed_entry:
                stop_swing = latest_valid_swing(base_swings, 'Long', armed_entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is not None:
                    trade = begin_trade('Long', armed_entry, armed_target, stop_swing, idx, d, c)
                    filled = True
            elif armed_direction == 'Short' and h >= armed_entry:
                stop_swing = latest_valid_swing(base_swings, 'Short', armed_entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is not None:
                    trade = begin_trade('Short', armed_entry, armed_target, stop_swing, idx, d, c)
                    filled = True

            if filled:
                phase = IN_TRADE
            else:
                if armed_direction == 'Long' and c < range_low:
                    armed_direction = 'Short'
                    armed_entry, armed_target = order_prices('Short', entry_mode, c, range_high, range_low, range_val)
                    armed_breakout_date = d
                    armed_breakout_close = c
                    if not valid_entry_target('Short', armed_entry, armed_target):
                        phase = WAIT_BREAKOUT
                        armed_direction = armed_entry = armed_target = armed_breakout_date = armed_breakout_close = None
                elif armed_direction == 'Short' and c > range_high:
                    armed_direction = 'Long'
                    armed_entry, armed_target = order_prices('Long', entry_mode, c, range_high, range_low, range_val)
                    armed_breakout_date = d
                    armed_breakout_close = c
                    if not valid_entry_target('Long', armed_entry, armed_target):
                        phase = WAIT_BREAKOUT
                        armed_direction = armed_entry = armed_target = armed_breakout_date = armed_breakout_close = None

        if phase == IN_TRADE and trade is not None:
            tp_before = unit2_tp_seen(trade)
            done = process_open_trade(trade, bar, range_low, range_high, range_close_exit)
            tp_after = unit2_tp_seen(trade)
            if tp_after:
                base_tp_locked = True

            if active_order is not None:
                if active_order.status == 'Pending' and (not tp_before and tp_after):
                    cancel_scale_order(active_order, d, 'Base-TP-Cancel')
                    active_order = None
                elif active_order.status in ('Pending', 'Open'):
                    process_scale_order(active_order, bar)
                    if active_order.status in ('Closed', 'Cancelled'):
                        active_order = None

            if done:
                finish_trade(d, c, 'Base-Closed')
                continue

            if active_order is None and not base_tp_locked and trade_entry_idx is not None:
                if trade.direction == 'Long' and c > range_high:
                    signal = find_delivery_signal(
                        work, scale_swings, idx, 'Long', range_high, range_low, trade_entry_idx, used_scale_swings
                    )
                elif trade.direction == 'Short' and c < range_low:
                    signal = find_delivery_signal(
                        work, scale_swings, idx, 'Short', range_high, range_low, trade_entry_idx, used_scale_swings
                    )
                else:
                    signal = None

                if signal is not None:
                    order = make_scale_order(
                        period,
                        work,
                        scale_swings,
                        idx,
                        trade.direction,
                        signal,
                        trade_entry_idx,
                        next_scale_id,
                        scale_swing_timeframe,
                    )
                    used_scale_swings.add(swing_key(signal))
                    if order is not None:
                        addons.append(order)
                        active_order = order
                        next_scale_id += 1

        if phase == WAIT_BREAKOUT:
            if c > range_high:
                entry, target = order_prices('Long', entry_mode, c, range_high, range_low, range_val)
                if not valid_entry_target('Long', entry, target):
                    continue
                stop_swing = latest_valid_swing(base_swings, 'Long', entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is None:
                    continue
                armed_direction = 'Long'
                armed_entry = entry
                armed_target = target
                armed_breakout_date = d
                armed_breakout_close = c
                if entry_mode == 'boundary' and l <= entry:
                    trade = begin_trade('Long', entry, target, stop_swing, idx, d, c)
                    phase = IN_TRADE
                    continue
                phase = WAIT_FILL
            elif c < range_low:
                entry, target = order_prices('Short', entry_mode, c, range_high, range_low, range_val)
                if not valid_entry_target('Short', entry, target):
                    continue
                stop_swing = latest_valid_swing(base_swings, 'Short', entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is None:
                    continue
                armed_direction = 'Short'
                armed_entry = entry
                armed_target = target
                armed_breakout_date = d
                armed_breakout_close = c
                if entry_mode == 'boundary' and h >= entry:
                    trade = begin_trade('Short', entry, target, stop_swing, idx, d, c)
                    phase = IN_TRADE
                    continue
                phase = WAIT_FILL

    if phase == IN_TRADE and trade is not None and not trade_bars.empty:
        last = trade_bars.iloc[-1]
        d = pd.Timestamp(last['date'])
        c = float(last['close'])
        close_units(trade, d, c, 'Period-Close')
        classify_trade(trade)
        finish_trade(d, c, 'Period-Close')

    return bundles, meta


def bundle_rows(bundles: list[TradeBundle], meta: dict) -> list[dict]:
    if not bundles:
        return [
            {
                'Period': meta['period'],
                'Trade_Direction': 'No-Op',
                'Base_PL': 0.0,
                'Scale_PL': 0.0,
                'Total_PL': 0.0,
                'Scale_Attempts': 0,
                'Scale_Fills': 0,
                'Scale_Wins': 0,
                'Scale_Losses': 0,
                'Scale_Cancels': 0,
                'Scale_Swing_Timeframe': meta.get('scale_swing_timeframe'),
                'Result': 'No-Op',
                'Symbol': meta['symbol'],
                'Range_High': meta.get('range_high'),
                'Range_Low': meta.get('range_low'),
                'Range': meta.get('range'),
                'Cumulative_PL': 0.0,
            }
        ]

    rows: list[dict] = []
    cumulative = 0.0
    for trade_no, bundle in enumerate(bundles, 1):
        trade = bundle.base
        scale_fills = [order for order in bundle.addons if order.fill_date is not None]
        scale_wins = [order for order in bundle.addons if order.pl > 0]
        scale_losses = [order for order in bundle.addons if order.pl < 0]
        scale_cancels = [order for order in bundle.addons if order.status == 'Cancelled']
        cumulative += bundle.total_points
        row = {
            'Period': trade.period,
            'Trade_No': trade_no,
            'Range_High': meta.get('range_high'),
            'Range_Low': meta.get('range_low'),
            'Range': meta.get('range'),
            'Trade_Direction': trade.direction,
            'Base_Units': 3,
            'Entry_Date': trade.entry_date.date().isoformat(),
            'Entry_Price': trade.entry,
            'Entry_Mode': trade.entry_mode,
            'Stop_Swing_Scope': trade.stop_swing_scope,
            'Breakout_Date': trade.breakout_date.date().isoformat(),
            'Breakout_Close': trade.breakout_close,
            'Initial_Stop_Price': trade.initial_stop,
            'Stop_Source_Date': trade.stop_source_date.date().isoformat(),
            'Stop_Source_Price': trade.stop_source_price,
            'TP25_Price': trade.tp25,
            'TP_Price': trade.target,
            'Base_PL': round(bundle.base_points, 6),
            'Scale_PL': round(bundle.addon_points, 6),
            'Total_PL': round(bundle.total_points, 6),
            'Scale_Attempts': len(bundle.addons),
            'Scale_Fills': len(scale_fills),
            'Scale_Wins': len(scale_wins),
            'Scale_Losses': len(scale_losses),
            'Scale_Cancels': len(scale_cancels),
            'Scale_Swing_Timeframe': meta.get('scale_swing_timeframe'),
            'Base_MAE_Position_Pts': round(trade.mae_position_pts, 6),
            'Scale_Max_MAE_Pts': round(max((order.mae_pts for order in bundle.addons), default=0.0), 6),
            'Result': 'Win' if bundle.total_points > 0 else 'Loss' if bundle.total_points < 0 else 'Scratch',
            'Base_Result': trade.result,
            'Base_Final_Reason': trade.final_reason,
            'Symbol': meta['symbol'],
            'Range_Days': meta['range_days'],
            'Trade_Days': meta['trade_days'],
            'Cumulative_PL': round(cumulative, 6),
        }
        for unit in (1, 2, 3):
            ex = next((exit_ for exit_ in trade.exits if exit_.unit == unit), None)
            row[f'Unit{unit}_Exit_Price'] = ex.price if ex else None
            row[f'Unit{unit}_Exit_Date'] = ex.date.date().isoformat() if ex else None
            row[f'Unit{unit}_Exit_Reason'] = ex.reason if ex else None
        rows.append(row)
    return rows


def addon_rows(bundles: list[TradeBundle], point_value: float) -> list[dict]:
    rows: list[dict] = []
    for bundle_no, bundle in enumerate(bundles, 1):
        for order in bundle.addons:
            rows.append(
                {
                    'Period': order.period,
                    'Base_Trade_No': bundle_no,
                    'Scale_ID': order.scale_id,
                    'Direction': order.direction,
                    'Signal_Date': order.signal_date.date().isoformat(),
                    'Signal_Close': order.signal_close,
                    'Broken_Swing_Date': order.swing_date.date().isoformat(),
                    'Broken_Swing_Value': order.swing_value,
                    'Scale_Swing_Timeframe': order.scale_swing_timeframe,
                    'Leg_Start_Date': order.leg_start_date.date().isoformat(),
                    'Leg_Stop_Date': order.leg_stop_date.date().isoformat(),
                    'Entry': order.entry,
                    'Stop': order.stop,
                    'Target_2R': order.target,
                    'Status': order.status,
                    'Fill_Date': order.fill_date.date().isoformat() if order.fill_date is not None else None,
                    'Exit_Date': order.exit_date.date().isoformat() if order.exit_date is not None else None,
                    'Exit_Price': order.exit_price,
                    'Exit_Reason': order.exit_reason,
                    'PL_Pts': round(order.pl, 6),
                    'PL_USD': round(order.pl * point_value, 2),
                    'MAE_Pts': round(order.mae_pts, 6),
                    'MFE_Pts': round(order.mfe_pts, 6),
                }
            )
    return rows


def draw_year(
    period: str,
    bars: pd.DataFrame,
    bundles: list[TradeBundle],
    meta: dict,
    out_path: Path,
    market: str,
    point_value: float,
) -> dict:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    range_bars = work[work['month'] <= 3]
    dates = pd.to_datetime(work['date'])
    xnums = mdates.date2num(dates)

    fig = plt.figure(figsize=(18, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    width = 0.72
    for x, (_, row) in zip(xnums, work.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.7, zorder=3)
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

    if not range_bars.empty:
        ax.axvspan(
            pd.Timestamp(range_bars.iloc[0]['date']),
            pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1),
            color='#1F4E79',
            alpha=0.28,
            zorder=0,
        )

    rh = float(meta.get('range_high', 0.0) or 0.0)
    rl = float(meta.get('range_low', 0.0) or 0.0)
    rv = float(meta.get('range', 0.0) or 0.0)
    if rv > 0:
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)

    exit_colors = {
        'TP25': '#64FFDA',
        'TP': '#76FF03',
        'BE-Stop': '#B0BEC5',
        'Swing-Stop': '#FF1744',
        'Range-Close': '#FFB74D',
        'Period-Close': '#BA68C8',
        'Scale-TP2R': '#00E676',
        'Scale-Stop': '#FF5252',
        'Base-Closed': '#FFB74D',
    }
    total_pl = sum(bundle.total_points for bundle in bundles)
    scale_pl_total = sum(bundle.addon_points for bundle in bundles)
    pattern = '+'.join(f'{b.base.direction[0]}{("W" if b.total_points > 0 else "L" if b.total_points < 0 else "S")}' for b in bundles) if bundles else 'No-Op'
    label_offsets = [18, -26, 34, -42, 50, -58, 66, -74]

    for i, bundle in enumerate(bundles, 1):
        trade = bundle.base
        x_e = mdates.date2num(trade.entry_date)
        x_s = mdates.date2num(trade.stop_source_date)
        ax.scatter([x_s], [trade.stop_source_price], marker='o', color='#64B5F6', s=42, zorder=9, edgecolor='black', linewidth=0.7)
        ax.scatter(
            [x_e],
            [trade.entry],
            marker='^' if trade.direction == 'Long' else 'v',
            color='#FFC107',
            s=90,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )
        last_exit_date = max((ex.date for ex in trade.exits), default=trade.entry_date)
        x_last = mdates.date2num(last_exit_date)
        ax.plot([x_e, x_last], [trade.target, trade.target], color='#76FF03', linewidth=0.72, alpha=0.48, zorder=4)
        ax.plot([x_e, x_last], [trade.initial_stop, trade.initial_stop], color='#FF1744', linewidth=0.72, alpha=0.45, zorder=4)
        for ex in trade.exits:
            color = exit_colors.get(ex.reason, '#E0E0E0')
            ax.scatter([mdates.date2num(ex.date)], [ex.price], marker='X', color=color, s=76, zorder=10, edgecolor='black', linewidth=0.8)

        for order in bundle.addons:
            x_sig = mdates.date2num(order.signal_date)
            ax.scatter(
                [x_sig],
                [order.signal_close],
                marker='D',
                color='#40C4FF',
                s=54,
                zorder=11,
                edgecolor='black',
                linewidth=0.7,
            )
            end_date = order.exit_date or last_exit_date
            ax.plot(
                [x_sig, mdates.date2num(end_date)],
                [order.entry, order.entry],
                color='#40C4FF',
                linewidth=0.7,
                alpha=0.55,
                zorder=4,
            )
            if order.fill_date is not None:
                ax.scatter(
                    [mdates.date2num(order.fill_date)],
                    [order.entry],
                    marker='P',
                    color='#EA80FC',
                    s=66,
                    zorder=11,
                    edgecolor='black',
                    linewidth=0.7,
                )
                ax.plot(
                    [mdates.date2num(order.fill_date), mdates.date2num(end_date)],
                    [order.stop, order.stop],
                    color='#FF5252',
                    linewidth=0.65,
                    alpha=0.55,
                    zorder=4,
                )
                ax.plot(
                    [mdates.date2num(order.fill_date), mdates.date2num(end_date)],
                    [order.target, order.target],
                    color='#00E676',
                    linewidth=0.65,
                    alpha=0.55,
                    zorder=4,
                )
            if order.exit_price is not None and order.exit_date is not None:
                color = exit_colors.get(order.exit_reason or '', '#E0E0E0')
                ax.scatter(
                    [mdates.date2num(order.exit_date)],
                    [order.exit_price],
                    marker='X',
                    color=color,
                    s=82,
                    zorder=11,
                    edgecolor='black',
                    linewidth=0.8,
                )

        final_exit = max(trade.exits, key=lambda ex: ex.date)
        color = '#76FF03' if bundle.total_points > 0 else '#FF5252' if bundle.total_points < 0 else '#B0BEC5'
        ax.annotate(
            f'#{i} {trade.direction[0]} base {bundle.base_points:+.0f} add {bundle.addon_points:+.0f} total {bundle.total_points:+.0f}',
            xy=(mdates.date2num(final_exit.date), final_exit.price),
            xytext=(7, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=color,
            fontsize=7,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=color, alpha=0.92),
        )

    if rv > 0:
        last_x = xnums[-1] + 2.0
        ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=8, va='center')
        ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=8, va='center')

    title = (
        f'{period} {market} YEARLY ORB DELIVERY SCALE-IN · {meta.get("scale_swing_timeframe", "daily")} scale swings · '
        f'inside-range swing range-close · '
        f'{len(bundles)} base trades · total {total_pl:+.1f} pts (${total_pl * point_value:+,.0f}) · '
        f'scale {scale_pl_total:+.1f} pts (${scale_pl_total * point_value:+,.0f})'
    )
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
        'range_days': meta['range_days'],
        'trade_days': meta['trade_days'],
        'range': round(rv, 2),
        'pattern': pattern,
        'trades': len(bundles),
        'base_pts': round(sum(bundle.base_points for bundle in bundles), 2),
        'scale_pts': round(scale_pl_total, 2),
        'total_pts': round(total_pl, 2),
        'total_usd': round(total_pl * point_value, 2),
        'chart': f'{period}/{period}.png',
    }


def write_indexes(
    out_root: Path,
    market: str,
    point_value: float,
    chart_rows: list[dict],
    result_df: pd.DataFrame,
    addon_df: pd.DataFrame,
    export_csv: Path,
    addon_csv: Path,
    scale_swing_timeframe: str,
) -> None:
    trades = result_df[result_df['Trade_Direction'] != 'No-Op'].copy() if not result_df.empty else pd.DataFrame()
    if not trades.empty:
        vals = pd.to_numeric(trades['Total_PL'], errors='coerce').fillna(0.0)
        base_vals = pd.to_numeric(trades['Base_PL'], errors='coerce').fillna(0.0)
        scale_vals = pd.to_numeric(trades['Scale_PL'], errors='coerce').fillna(0.0)
        wins = int((vals > 0).sum())
        losses = int((vals < 0).sum())
        total_pts = float(vals.sum())
        base_pts = float(base_vals.sum())
        scale_pts = float(scale_vals.sum())
        max_dd_pts = max_dd(vals)
        win_rate = wins / len(trades) * 100
        scale_attempts = int(pd.to_numeric(trades['Scale_Attempts'], errors='coerce').fillna(0).sum())
        scale_fills = int(pd.to_numeric(trades['Scale_Fills'], errors='coerce').fillna(0).sum())
        scale_wins = int(pd.to_numeric(trades['Scale_Wins'], errors='coerce').fillna(0).sum())
        scale_losses = int(pd.to_numeric(trades['Scale_Losses'], errors='coerce').fillna(0).sum())
        avg_base_mae = float(pd.to_numeric(trades['Base_MAE_Position_Pts'], errors='coerce').fillna(0.0).mean())
        max_base_mae = float(pd.to_numeric(trades['Base_MAE_Position_Pts'], errors='coerce').fillna(0.0).max())
    else:
        wins = losses = scale_attempts = scale_fills = scale_wins = scale_losses = 0
        total_pts = base_pts = scale_pts = max_dd_pts = win_rate = avg_base_mae = max_base_mae = 0.0

    avg_scale_mae = 0.0
    max_scale_mae = 0.0
    if not addon_df.empty:
        filled = addon_df[addon_df['Fill_Date'].notna()].copy()
        if not filled.empty:
            mae = pd.to_numeric(filled['MAE_Pts'], errors='coerce').fillna(0.0)
            avg_scale_mae = float(mae.mean())
            max_scale_mae = float(mae.max())

    for row in sorted(chart_rows, key=lambda x: x['period']):
        idx = out_root / row['period'] / 'INDEX.md'
        idx.write_text(
            '\n'.join(
                [
                    f'# {row["period"]} {market} yearly ORB {scale_swing_timeframe} delivery scale-in chart',
                    '',
                    f'Symbol: {row["symbol"]}  ·  Range days: {row["range_days"]}  ·  Trade days: {row["trade_days"]}',
                    f'Total: {row["total_pts"]:+.2f} pts (${row["total_usd"]:+,.0f})  ·  Base: {row["base_pts"]:+.2f} pts  ·  Scale: {row["scale_pts"]:+.2f} pts',
                    '',
                    '| Period | Symbol | Range | Pattern | Base trades | Base pts | Scale pts | Total pts | Chart |',
                    '|---|---|---:|---|---:|---:|---:|---:|---|',
                    f'| {row["period"]} | {row["symbol"]} | {row["range"]:.2f} | {row["pattern"]} | {row["trades"]} | {row["base_pts"]:+.2f} | {row["scale_pts"]:+.2f} | {row["total_pts"]:+.2f} | [{row["period"]}.png]({row["period"]}.png) |',
                    '',
                ]
            ),
            encoding='utf-8',
        )

    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                f'# {market} yearly ORB {scale_swing_timeframe} delivery scale-in study',
                '',
                'Base strategy: current yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close candidate. Jan-Mar defines the yearly ORB; Apr-Dec trades boundary retests after daily closes outside the ORB; stop is the latest confirmed inside-range swing; range-close exit is enabled.',
                '',
                f'Scale-in rule tested here: while a base trade is active and before the base yearly ORB TP is reached, place one scale-in at a time after a daily close breaks the highest recent {scale_swing_timeframe} swing high above the yearly range for longs, or the lowest recent {scale_swing_timeframe} swing low below the yearly range for shorts. The add-on limit is the signal close, the stop is the low/high of the leg that formed the broken swing, and the target is 2R.',
                '',
                'Causality note: add-on orders are placed after the signal close and cannot fill until a later daily candle. Daily OHLC sequencing is conservative and cannot prove intraday ordering.',
                '',
                f'Base trades: {len(trades)}  ·  Wins: {wins}  ·  Losses: {losses}  ·  Win rate: {win_rate:.1f}%',
                f'Total: {total_pts:+.2f} pts (${total_pts * point_value:+,.0f})  ·  Base: {base_pts:+.2f} pts (${base_pts * point_value:+,.0f})  ·  Scale add-ons: {scale_pts:+.2f} pts (${scale_pts * point_value:+,.0f})',
                f'Max DD on combined trade ledger: {max_dd_pts:+.2f} pts (${max_dd_pts * point_value:+,.0f})',
                f'Scale attempts: {scale_attempts}  ·  Fills: {scale_fills}  ·  Wins: {scale_wins}  ·  Losses: {scale_losses}',
                f'Avg base position MAE: {avg_base_mae:.2f} pts (${avg_base_mae * point_value:,.0f})  ·  Worst base position MAE: {max_base_mae:.2f} pts (${max_base_mae * point_value:,.0f})',
                f'Avg filled scale MAE: {avg_scale_mae:.2f} pts (${avg_scale_mae * point_value:,.0f})  ·  Worst filled scale MAE: {max_scale_mae:.2f} pts (${max_scale_mae * point_value:,.0f})',
                '',
                f'Trade CSV: [{export_csv.name}]({export_csv.resolve()})',
                f'Add-on CSV: [{addon_csv.name}]({addon_csv.resolve()})',
                '',
                '| Year | Symbol | Range Days | Trade Days | Range | Pattern | Base trades | Base pts | Scale pts | Total pts | Folder |',
                '|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---|',
                *[
                    f'| {r["period"]} | {r["symbol"]} | {r["range_days"]} | {r["trade_days"]} | {r["range"]:.2f} | {r["pattern"]} | {r["trades"]} | {r["base_pts"]:+.2f} | {r["scale_pts"]:+.2f} | {r["total_pts"]:+.2f} | [{r["period"]}/]({r["period"]}/INDEX.md) |'
                    for r in sorted(chart_rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def run(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]

    daily = daily.copy()
    daily['date'] = pd.to_datetime(daily['date'])
    daily['year'] = daily['date'].dt.year
    all_rows: list[dict] = []
    all_addons: list[dict] = []
    chart_rows: list[dict] = []

    for year, bars in daily.groupby('year', sort=True):
        bars = bars.sort_values('date').reset_index(drop=True)
        months = bars['date'].dt.month
        if not (months <= 3).any() or not (months > 3).any():
            continue
        period = str(int(year))
        bundles, meta = simulate_year_with_scaleins(
            period,
            bars,
            args.range_close_exit,
            args.entry_mode,
            args.stop_swing_scope,
            args.scale_swing_timeframe,
        )
        all_rows.extend(bundle_rows(bundles, meta))
        all_addons.extend(addon_rows(bundles, args.point_value))
        if not args.no_charts:
            chart_row = draw_year(
                period,
                bars,
                bundles,
                meta,
                args.out / period / f'{period}.png',
                args.market.upper(),
                args.point_value,
            )
            chart_rows.append(chart_row)
            print(
                f'{chart_row["chart"]} base={chart_row["base_pts"]:+.2f} '
                f'scale={chart_row["scale_pts"]:+.2f} total={chart_row["total_pts"]:+.2f} pts'
            )

    result_df = pd.DataFrame(all_rows)
    addon_df = pd.DataFrame(all_addons)
    if not result_df.empty:
        result_df['Cumulative_PL'] = result_df['Total_PL'].astype(float).cumsum().round(6)
    args.export_csv.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(args.export_csv, index=False)
    args.addon_csv.parent.mkdir(parents=True, exist_ok=True)
    addon_df.to_csv(args.addon_csv, index=False)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.no_charts:
        for year, bars in daily.groupby('year', sort=True):
            period = str(int(year))
            rows = result_df[result_df['Period'].astype(str) == period] if not result_df.empty else pd.DataFrame()
            chart_rows.append(
                {
                    'period': period,
                    'symbol': str(bars.iloc[0]['symbol']),
                    'range_days': int((bars['date'].dt.month <= 3).sum()),
                    'trade_days': int((bars['date'].dt.month > 3).sum()),
                    'range': 0.0,
                    'pattern': '',
                    'trades': int((rows['Trade_Direction'] != 'No-Op').sum()) if not rows.empty else 0,
                    'base_pts': float(pd.to_numeric(rows.get('Base_PL', pd.Series(dtype=float)), errors='coerce').fillna(0.0).sum()) if not rows.empty else 0.0,
                    'scale_pts': float(pd.to_numeric(rows.get('Scale_PL', pd.Series(dtype=float)), errors='coerce').fillna(0.0).sum()) if not rows.empty else 0.0,
                    'total_pts': float(pd.to_numeric(rows.get('Total_PL', pd.Series(dtype=float)), errors='coerce').fillna(0.0).sum()) if not rows.empty else 0.0,
                    'total_usd': 0.0,
                    'chart': '',
                }
            )
    write_indexes(
        args.out,
        args.market.upper(),
        args.point_value,
        chart_rows,
        result_df,
        addon_df,
        args.export_csv,
        args.addon_csv,
        args.scale_swing_timeframe,
    )
    print(f'Wrote {args.export_csv}')
    print(f'Wrote {args.addon_csv}')
    print(f'Wrote {args.out / "INDEX.md"}')
    return result_df, addon_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    ap.add_argument('--addon-csv', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument('--range-close-exit', action='store_true')
    ap.add_argument('--entry-mode', choices=['boundary', 'breakout-close'], default='boundary')
    ap.add_argument('--stop-swing-scope', choices=['any', 'inside-range-candle'], default='any')
    ap.add_argument('--scale-swing-timeframe', choices=['daily', 'weekly'], default='daily')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--no-charts', action='store_true')
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
