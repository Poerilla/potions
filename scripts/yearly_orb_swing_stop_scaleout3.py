#!/usr/bin/env python3
"""Yearly ORB swing-stop scaleout study.

Rules:
- Jan-Mar defines the yearly ORB.
- Apr-Dec trades range-boundary retests after daily closes outside the ORB.
- Optional ``--entry-mode breakout-close`` places the retest limit at the
  breakout candle close instead of the ORB boundary.
- Long stop uses the latest confirmed daily swing low below entry.
- Short stop uses the latest confirmed daily swing high above entry.
- Unlimited trades per year.
- 3 units:
  - Unit 1 exits at 25% of the distance from entry to the ORB measured-move TP.
  - Unit 2 exits at the ORB measured-move TP.
  - Unit 3 is the runner.
  - The runner stop moves to breakeven only after Unit 2 reaches TP.
- Optional ``--range-close-exit`` exits all remaining units at the daily close
  when price closes back inside the Jan-Mar range.

This is still daily-OHLC research. Stop checks are conservative and happen
before target checks inside each daily candle; the breakeven runner stop becomes
active on bars after the TP bar.

Yearly PNGs optionally overlay **weekly ATR Supertrend** (completed-week ATR
mapped to daily bars; same engine as ``yearly_orb_delivery_research_charts``).
Use ``--weekly-atr-len 14 --weekly-atr-mult 3`` (defaults) or ``--weekly-atr-len 0`` to omit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import argparse

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2


@dataclass(frozen=True)
class SwingPoint:
    kind: str
    value: float
    pivot_idx: int
    confirm_idx: int
    pivot_date: pd.Timestamp
    pivot_high: float
    pivot_low: float


@dataclass
class UnitExit:
    unit: int
    date: pd.Timestamp
    price: float
    reason: str
    pl: float


@dataclass
class ScaleTrade:
    period: str
    direction: str
    entry: float
    target: float
    tp25: float
    initial_stop: float
    stop_source_date: pd.Timestamp
    stop_source_price: float
    entry_date: pd.Timestamp
    entry_mode: str
    stop_swing_scope: str
    breakout_date: pd.Timestamp
    breakout_close: float
    exits: list[UnitExit] = field(default_factory=list)
    be_active: bool = False
    mae_price_pts: float = 0.0
    mae_position_pts: float = 0.0
    mfe_price_pts: float = 0.0
    result: str = 'Open'
    final_reason: str = 'Open'

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [unit for unit in (1, 2, 3) if unit not in closed]

    @property
    def net_points(self) -> float:
        return sum(ex.pl for ex in self.exits)


def build_swings(bars: pd.DataFrame) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    lows = bars['low'].astype(float).tolist()
    highs = bars['high'].astype(float).tolist()
    dates = pd.to_datetime(bars['date']).tolist()
    for i in range(1, len(bars) - 1):
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            swings.append(SwingPoint('low', lows[i], i, i + 1, pd.Timestamp(dates[i]), highs[i], lows[i]))
        if highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            swings.append(SwingPoint('high', highs[i], i, i + 1, pd.Timestamp(dates[i]), highs[i], lows[i]))
    return swings


def latest_valid_swing(
    swings: list[SwingPoint],
    direction: str,
    entry: float,
    current_idx: int,
    stop_swing_scope: str,
    range_high: float,
    range_low: float,
) -> Optional[SwingPoint]:
    kind = 'low' if direction == 'Long' else 'high'
    for swing in reversed(swings):
        if swing.kind != kind or swing.confirm_idx >= current_idx:
            continue
        if stop_swing_scope == 'inside-range-candle':
            if swing.pivot_high > range_high or swing.pivot_low < range_low:
                continue
        if direction == 'Long' and swing.value < entry:
            return swing
        if direction == 'Short' and swing.value > entry:
            return swing
    return None


def start_trade(
    period: str,
    direction: str,
    entry: float,
    target: float,
    initial_stop: float,
    stop_swing: SwingPoint,
    entry_date: pd.Timestamp,
    entry_mode: str,
    stop_swing_scope: str,
    breakout_date: pd.Timestamp,
    breakout_close: float,
) -> ScaleTrade:
    if direction == 'Long':
        tp25 = entry + (target - entry) * 0.25
    else:
        tp25 = entry - (entry - target) * 0.25
    return ScaleTrade(
        period=period,
        direction=direction,
        entry=entry,
        target=target,
        tp25=tp25,
        initial_stop=initial_stop,
        stop_source_date=stop_swing.pivot_date,
        stop_source_price=stop_swing.value,
        entry_date=entry_date,
        entry_mode=entry_mode,
        stop_swing_scope=stop_swing_scope,
        breakout_date=breakout_date,
        breakout_close=breakout_close,
    )


def unit_pl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def add_exit(trade: ScaleTrade, unit: int, date: pd.Timestamp, price: float, reason: str) -> None:
    if unit not in trade.open_units:
        return
    trade.exits.append(UnitExit(unit, date, price, reason, unit_pl(trade.direction, trade.entry, price)))


def close_units(trade: ScaleTrade, date: pd.Timestamp, price: float, reason: str) -> None:
    for unit in list(trade.open_units):
        add_exit(trade, unit, date, price, reason)


def update_excursion(trade: ScaleTrade, high: float, low: float) -> None:
    open_count = len(trade.open_units)
    if open_count == 0:
        return
    if trade.direction == 'Long':
        adverse = max(0.0, trade.entry - low)
        favorable = max(0.0, high - trade.entry)
    else:
        adverse = max(0.0, high - trade.entry)
        favorable = max(0.0, trade.entry - low)
    trade.mae_price_pts = max(trade.mae_price_pts, adverse)
    trade.mae_position_pts = max(trade.mae_position_pts, adverse * open_count)
    trade.mfe_price_pts = max(trade.mfe_price_pts, favorable)


def classify_trade(trade: ScaleTrade) -> None:
    if trade.net_points > 0:
        trade.result = 'Win'
    elif trade.net_points < 0:
        trade.result = 'Loss'
    else:
        trade.result = 'Scratch'
    reasons = []
    for ex in sorted(trade.exits, key=lambda x: (x.date, x.unit)):
        if ex.reason not in reasons:
            reasons.append(ex.reason)
    trade.final_reason = '+'.join(reasons) if reasons else 'Open'


def process_open_trade(
    trade: ScaleTrade,
    bar: pd.Series,
    range_low: float,
    range_high: float,
    range_close_exit: bool,
) -> bool:
    h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])
    d = pd.Timestamp(bar['date'])
    update_excursion(trade, h, l)

    stop_price = trade.entry if trade.be_active else trade.initial_stop
    stop_reason = 'BE-Stop' if trade.be_active else 'Swing-Stop'
    if trade.direction == 'Long':
        if l <= stop_price:
            close_units(trade, d, stop_price, stop_reason)
            classify_trade(trade)
            return True
        if 1 in trade.open_units and h >= trade.tp25:
            add_exit(trade, 1, d, trade.tp25, 'TP25')
        if 2 in trade.open_units and h >= trade.target:
            add_exit(trade, 2, d, trade.target, 'TP')
            trade.be_active = True
    else:
        if h >= stop_price:
            close_units(trade, d, stop_price, stop_reason)
            classify_trade(trade)
            return True
        if 1 in trade.open_units and l <= trade.tp25:
            add_exit(trade, 1, d, trade.tp25, 'TP25')
        if 2 in trade.open_units and l <= trade.target:
            add_exit(trade, 2, d, trade.target, 'TP')
            trade.be_active = True

    if range_close_exit and trade.open_units and range_low <= c <= range_high:
        close_units(trade, d, c, 'Range-Close')
        classify_trade(trade)
        return True

    if not trade.open_units:
        classify_trade(trade)
        return True
    return False


def valid_entry_target(direction: str, entry: float, target: float) -> bool:
    if direction == 'Long':
        return entry < target
    return entry > target


def order_prices(
    direction: str,
    entry_mode: str,
    breakout_close: float,
    range_high: float,
    range_low: float,
    range_val: float,
) -> tuple[float, float]:
    if direction == 'Long':
        entry = range_high if entry_mode == 'boundary' else breakout_close
        return entry, range_high + range_val
    entry = range_low if entry_mode == 'boundary' else breakout_close
    return entry, range_low - range_val


def simulate_year(
    period: str,
    bars: pd.DataFrame,
    range_close_exit: bool,
    entry_mode: str,
    stop_swing_scope: str,
) -> tuple[list[ScaleTrade], dict]:
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
    meta.update({'range_high': range_high, 'range_low': range_low, 'range': range_val})
    if range_val <= 0:
        return [], meta

    swings = build_swings(work)
    phase = WAIT_BREAKOUT
    armed_direction: Optional[str] = None
    armed_entry: Optional[float] = None
    armed_target: Optional[float] = None
    armed_breakout_date: Optional[pd.Timestamp] = None
    armed_breakout_close: Optional[float] = None
    trade: Optional[ScaleTrade] = None
    trades: list[ScaleTrade] = []

    for idx, bar in work.iterrows():
        if int(bar['month']) <= 3:
            continue

        h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])
        d = pd.Timestamp(bar['date'])

        if phase == WAIT_FILL and armed_direction is not None and armed_entry is not None and armed_target is not None:
            filled = False
            if armed_direction == 'Long' and l <= armed_entry:
                stop_swing = latest_valid_swing(swings, 'Long', armed_entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is not None:
                    trade = start_trade(
                        period,
                        'Long',
                        armed_entry,
                        armed_target,
                        stop_swing.value,
                        stop_swing,
                        d,
                        entry_mode,
                        stop_swing_scope,
                        armed_breakout_date or d,
                        armed_breakout_close if armed_breakout_close is not None else c,
                    )
                    filled = True
            elif armed_direction == 'Short' and h >= armed_entry:
                stop_swing = latest_valid_swing(swings, 'Short', armed_entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is not None:
                    trade = start_trade(
                        period,
                        'Short',
                        armed_entry,
                        armed_target,
                        stop_swing.value,
                        stop_swing,
                        d,
                        entry_mode,
                        stop_swing_scope,
                        armed_breakout_date or d,
                        armed_breakout_close if armed_breakout_close is not None else c,
                    )
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
            done = process_open_trade(trade, bar, range_low, range_high, range_close_exit)
            if done:
                trades.append(trade)
                trade = None
                phase = WAIT_BREAKOUT
                armed_direction = None
                armed_entry = armed_target = armed_breakout_date = armed_breakout_close = None
                continue

        if phase == WAIT_BREAKOUT:
            if c > range_high:
                entry, target = order_prices('Long', entry_mode, c, range_high, range_low, range_val)
                if not valid_entry_target('Long', entry, target):
                    continue
                stop_swing = latest_valid_swing(swings, 'Long', entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is None:
                    continue
                armed_direction = 'Long'
                armed_entry = entry
                armed_target = target
                armed_breakout_date = d
                armed_breakout_close = c
                if entry_mode == 'boundary' and l <= entry:
                    trade = start_trade(period, 'Long', entry, target, stop_swing.value, stop_swing, d, entry_mode, stop_swing_scope, d, c)
                    phase = IN_TRADE
                    continue
                phase = WAIT_FILL
            elif c < range_low:
                entry, target = order_prices('Short', entry_mode, c, range_high, range_low, range_val)
                if not valid_entry_target('Short', entry, target):
                    continue
                stop_swing = latest_valid_swing(swings, 'Short', entry, idx, stop_swing_scope, range_high, range_low)
                if stop_swing is None:
                    continue
                armed_direction = 'Short'
                armed_entry = entry
                armed_target = target
                armed_breakout_date = d
                armed_breakout_close = c
                if entry_mode == 'boundary' and h >= entry:
                    trade = start_trade(period, 'Short', entry, target, stop_swing.value, stop_swing, d, entry_mode, stop_swing_scope, d, c)
                    phase = IN_TRADE
                    continue
                phase = WAIT_FILL

    if phase == IN_TRADE and trade is not None and not trade_bars.empty:
        last = trade_bars.iloc[-1]
        close_units(trade, pd.Timestamp(last['date']), float(last['close']), 'Period-Close')
        classify_trade(trade)
        trades.append(trade)

    return trades, meta


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def trade_rows(trades: list[ScaleTrade], meta: dict) -> list[dict]:
    if not trades:
        return [
            {
                'Period': meta['period'],
                'Range_High': meta.get('range_high'),
                'Range_Low': meta.get('range_low'),
                'Range': meta.get('range'),
                'Trade_Direction': 'No-Op',
                'Units': 0,
                'Entry_Date': None,
                'Entry_Price': None,
                'Entry_Mode': None,
                'Stop_Swing_Scope': None,
                'Breakout_Date': None,
                'Breakout_Close': None,
                'Initial_Stop_Price': None,
                'Stop_Source_Date': None,
                'Stop_Source_Price': None,
                'TP25_Price': None,
                'TP_Price': None,
                'Unit1_Exit_Price': None,
                'Unit1_Exit_Date': None,
                'Unit1_Exit_Reason': None,
                'Unit2_Exit_Price': None,
                'Unit2_Exit_Date': None,
                'Unit2_Exit_Reason': None,
                'Unit3_Exit_Price': None,
                'Unit3_Exit_Date': None,
                'Unit3_Exit_Reason': None,
                'Trade_PL': 0.0,
                'MAE_Price_Pts': 0.0,
                'MAE_Position_Pts': 0.0,
                'MFE_Price_Pts': 0.0,
                'Result': 'No-Op',
                'Final_Reason': 'No-Op',
                'Symbol': meta['symbol'],
                'Range_Days': meta['range_days'],
                'Trade_Days': meta['trade_days'],
                'Cumulative_PL': 0.0,
            }
        ]

    rows: list[dict] = []
    cumulative = 0.0
    for trade in trades:
        cumulative += trade.net_points
        exits = {ex.unit: ex for ex in trade.exits}
        row = {
            'Period': trade.period,
            'Range_High': meta.get('range_high'),
            'Range_Low': meta.get('range_low'),
            'Range': meta.get('range'),
            'Trade_Direction': trade.direction,
            'Units': 3,
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
            'Trade_PL': round(trade.net_points, 6),
            'MAE_Price_Pts': round(trade.mae_price_pts, 6),
            'MAE_Position_Pts': round(trade.mae_position_pts, 6),
            'MFE_Price_Pts': round(trade.mfe_price_pts, 6),
            'Result': trade.result,
            'Final_Reason': trade.final_reason,
            'Symbol': meta['symbol'],
            'Range_Days': meta['range_days'],
            'Trade_Days': meta['trade_days'],
            'Cumulative_PL': round(cumulative, 6),
        }
        for unit in (1, 2, 3):
            ex = exits.get(unit)
            row[f'Unit{unit}_Exit_Price'] = ex.price if ex else None
            row[f'Unit{unit}_Exit_Date'] = ex.date.date().isoformat() if ex else None
            row[f'Unit{unit}_Exit_Reason'] = ex.reason if ex else None
        rows.append(row)
    return rows


def plot_weekly_supertrend(ax: plt.Axes, work: pd.DataFrame) -> None:
    """Overlay weekly ATR Supertrend stop (causal completed-week mapping on daily bars)."""
    if 'wk_stop' not in work.columns or 'wk_trend' not in work.columns:
        return
    w = work[work['wk_stop'].notna() & work['wk_trend'].notna()].copy()
    if w.empty:
        return
    trend = w['wk_trend'].astype(str)
    seg_id = trend.ne(trend.shift()).cumsum()
    for _, chunk in w.groupby(seg_id):
        col = '#00BCD4' if str(chunk['wk_trend'].iloc[0]) == 'up' else '#FF9800'
        ax.plot(
            mdates.date2num(pd.to_datetime(chunk['date'])),
            chunk['wk_stop'].astype(float),
            color=col,
            linewidth=1.05,
            alpha=0.88,
            zorder=4,
        )


def draw_year(
    period: str,
    bars: pd.DataFrame,
    trades: list[ScaleTrade],
    meta: dict,
    out_path: Path,
    market: str,
    point_value: float,
    range_close_exit: bool,
    entry_mode: str,
    stop_swing_scope: str,
    weekly_st_label: str = '',
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

    plot_weekly_supertrend(ax, work)

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
    }
    total_pl = sum(t.net_points for t in trades)
    pattern = '+'.join(f'{t.direction[0]}{t.result[0]}' for t in trades) if trades else 'No-Op'
    label_offsets = [18, -26, 34, -42, 50, -58, 66, -74]
    for i, trade in enumerate(trades, 1):
        x_e = mdates.date2num(trade.entry_date)
        x_s = mdates.date2num(trade.stop_source_date)
        ax.scatter([x_s], [trade.stop_source_price], marker='o', color='#64B5F6', s=46, zorder=9, edgecolor='black', linewidth=0.7)
        ax.scatter(
            [x_e],
            [trade.entry],
            marker='^' if trade.direction == 'Long' else 'v',
            color='#FFC107',
            s=92,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )
        last_exit_date = max((ex.date for ex in trade.exits), default=trade.entry_date)
        x_last = mdates.date2num(last_exit_date)
        ax.plot([x_e, x_last], [trade.tp25, trade.tp25], color='#64FFDA', linewidth=0.65, alpha=0.42, zorder=4)
        ax.plot([x_e, x_last], [trade.target, trade.target], color='#76FF03', linewidth=0.72, alpha=0.52, zorder=4)
        ax.plot([x_e, x_last], [trade.initial_stop, trade.initial_stop], color='#FF1744', linewidth=0.72, alpha=0.50, zorder=4)
        if any(ex.reason in ('BE-Stop', 'Period-Close', 'Range-Close') for ex in trade.exits):
            ax.plot([x_e, x_last], [trade.entry, trade.entry], color='#B0BEC5', linewidth=0.55, alpha=0.35, zorder=4)

        for ex in trade.exits:
            x_x = mdates.date2num(ex.date)
            color = exit_colors.get(ex.reason, '#E0E0E0')
            ax.scatter([x_x], [ex.price], marker='X', color=color, s=88, zorder=10, edgecolor='black', linewidth=0.8)
        final_exit = max(trade.exits, key=lambda ex: ex.date)
        color = exit_colors.get(final_exit.reason, '#E0E0E0')
        ax.annotate(
            f'#{i} {trade.direction[0]} {trade.net_points:+.0f}',
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

    variant = 'range-close' if range_close_exit else 'runner'
    entry_label = 'breakout close limit' if entry_mode == 'breakout-close' else 'boundary limit'
    swing_label = 'inside-range swing stop' if stop_swing_scope == 'inside-range-candle' else 'any swing stop'
    st_part = f' · {weekly_st_label}' if weekly_st_label else ''
    title = (
        f'{period} {market} YEARLY ORB SCALEOUT3 {variant} · {entry_label} · {swing_label} · Jan-Mar · '
        f'{len(trades)} trades · {total_pl:+.1f} contract-pts '
        f'(${total_pl * point_value:+,.0f}){st_part}'
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
        'trades': len(trades),
        'net_pts': round(total_pl, 2),
        'net_usd': round(total_pl * point_value, 2),
        'chart': f'{period}/{period}.png',
    }


def write_indexes(
    out_root: Path,
    market: str,
    point_value: float,
    rows: list[dict],
    result_df: pd.DataFrame,
    range_close_exit: bool,
    entry_mode: str,
    stop_swing_scope: str,
    chart_overlay_note: str = '',
) -> None:
    trades = result_df[result_df['Trade_Direction'] != 'No-Op'].copy()
    if not trades.empty:
        vals = pd.to_numeric(trades['Trade_PL'], errors='coerce').fillna(0.0)
        wins = int((vals > 0).sum())
        losses = int((vals < 0).sum())
        total_pts = float(vals.sum())
        max_dd_pts = max_dd(vals)
        avg_mae_pts = float(pd.to_numeric(trades['MAE_Position_Pts'], errors='coerce').fillna(0.0).mean())
        max_mae_pts = float(pd.to_numeric(trades['MAE_Position_Pts'], errors='coerce').fillna(0.0).max())
        win_rate = wins / len(trades) * 100
    else:
        wins = losses = 0
        total_pts = max_dd_pts = avg_mae_pts = max_mae_pts = win_rate = 0.0

    variant = 'range-close restricted' if range_close_exit else 'runner'
    entry_label = 'breakout-close limit' if entry_mode == 'breakout-close' else 'boundary limit'
    swing_label = 'inside-range swing stop' if stop_swing_scope == 'inside-range-candle' else 'any swing stop'
    for row in sorted(rows, key=lambda x: x['period']):
        idx = out_root / row['period'] / 'INDEX.md'
        per_lines = [
            f'# {row["period"]} {market} yearly ORB scaleout3 {variant} {entry_label} {swing_label} chart',
            '',
            f'Symbol: {row["symbol"]}  ·  Range days: {row["range_days"]}  ·  Trade days: {row["trade_days"]}',
            f'Net: {row["net_pts"]:+.2f} contract-pts (${row["net_usd"]:+,.0f} / 1 {market} per unit)',
        ]
        if chart_overlay_note:
            per_lines.extend(['', f'Chart overlay: {chart_overlay_note}.'])
        per_lines.extend(
            [
                '',
                '| Period | Symbol | Range | Pattern | Trades | Net contract-pts | Chart |',
                '|---|---|---:|---|---:|---:|---|',
                f'| {row["period"]} | {row["symbol"]} | {row["range"]:.2f} | {row["pattern"]} | {row["trades"]} | {row["net_pts"]:+.2f} | [{row["period"]}.png]({row["period"]}.png) |',
                '',
            ]
        )
        idx.write_text('\n'.join(per_lines), encoding='utf-8')

    overlay_line = (
        f'\n\nChart overlay: {chart_overlay_note}.'
        if chart_overlay_note
        else ''
    )

    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                f'# {market} yearly ORB scaleout3 {variant} {entry_label} {swing_label} charts',
                '',
                f'Variant rules: Jan-Mar defines the yearly ORB; Apr-Dec trades retests after daily closes outside the ORB; entry mode is {entry_label}; stop source is {swing_label}; unlimited trades; 3 units with Unit 1 at 25% to TP, Unit 2 at TP, and Unit 3 as runner. Runner stop moves to breakeven only after Unit 2 reaches TP.{overlay_line}',
                '',
                f'Trades: {len(trades)}  ·  Wins: {wins}  ·  Losses: {losses}  ·  Win rate: {win_rate:.1f}%',
                f'Net: {total_pts:+.2f} contract-pts (${total_pts * point_value:+,.0f})  ·  Max DD: {max_dd_pts:+.2f} contract-pts (${max_dd_pts * point_value:+,.0f})',
                f'Avg position MAE: {avg_mae_pts:.2f} contract-pts (${avg_mae_pts * point_value:,.0f})  ·  Worst position MAE: {max_mae_pts:.2f} contract-pts (${max_mae_pts * point_value:,.0f})',
                '',
                '| Year | Symbol | Range Days | Trade Days | Range | Pattern | Trades | Net contract-pts | Folder |',
                '|---:|---|---:|---:|---:|---|---:|---:|---|',
                *[
                    f'| {r["period"]} | {r["symbol"]} | {r["range_days"]} | {r["trade_days"]} | {r["range"]:.2f} | {r["pattern"]} | {r["trades"]} | {r["net_pts"]:+.2f} | [{r["period"]}/]({r["period"]}/INDEX.md) |'
                    for r in sorted(rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def run(args: argparse.Namespace) -> pd.DataFrame:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]

    daily = daily.copy()
    daily['date'] = pd.to_datetime(daily['date'])
    daily['year'] = daily['date'].dt.year
    daily = daily.sort_values('date').reset_index(drop=True)

    weekly_st_label = ''
    if int(getattr(args, 'weekly_atr_len', 0) or 0) > 0:
        from yearly_orb_delivery_research_charts import calculate_weekly_atr_trailing_stop_on_daily

        st_frame = calculate_weekly_atr_trailing_stop_on_daily(
            daily[['date', 'open', 'high', 'low', 'close']].copy(),
            int(args.weekly_atr_len),
            float(args.weekly_atr_mult),
        )
        daily['wk_stop'] = st_frame['atr_stop'].values
        daily['wk_trend'] = st_frame['atr_trend'].values
        weekly_st_label = f'weekly ATR ST {int(args.weekly_atr_len)}×{float(args.weekly_atr_mult):g} (cyan up / orange down)'

    all_rows: list[dict] = []
    chart_rows: list[dict] = []
    for year, bars in daily.groupby('year', sort=True):
        bars = bars.sort_values('date').reset_index(drop=True)
        months = bars['date'].dt.month
        if not (months <= 3).any() or not (months > 3).any():
            continue
        period = str(int(year))
        trades, meta = simulate_year(period, bars, args.range_close_exit, args.entry_mode, args.stop_swing_scope)
        all_rows.extend(trade_rows(trades, meta))
        chart_row = draw_year(
            period,
            bars,
            trades,
            meta,
            args.out / period / f'{period}.png',
            args.market.upper(),
            args.point_value,
            args.range_close_exit,
            args.entry_mode,
            args.stop_swing_scope,
            weekly_st_label=weekly_st_label,
        )
        chart_rows.append(chart_row)
        print(f'{chart_row["chart"]} trades={chart_row["trades"]} net={chart_row["net_pts"]:+.2f} contract-pts')

    result_df = pd.DataFrame(all_rows)
    if not result_df.empty:
        result_df['Cumulative_PL'] = result_df['Trade_PL'].astype(float).cumsum().round(6)
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(args.export_csv, index=False)
    write_indexes(
        args.out,
        args.market.upper(),
        args.point_value,
        chart_rows,
        result_df,
        args.range_close_exit,
        args.entry_mode,
        args.stop_swing_scope,
        chart_overlay_note=weekly_st_label,
    )
    print(f'Wrote {args.export_csv}')
    print(f'Wrote {len(chart_rows)} charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    return result_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument('--range-close-exit', action='store_true')
    ap.add_argument('--entry-mode', choices=['boundary', 'breakout-close'], default='boundary')
    ap.add_argument('--stop-swing-scope', choices=['any', 'inside-range-candle'], default='any')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument(
        '--weekly-atr-len',
        type=int,
        default=14,
        help='Weekly ATR Supertrend length on daily chart; set 0 to omit overlay.',
    )
    ap.add_argument('--weekly-atr-mult', type=float, default=3.0)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
