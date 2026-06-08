#!/usr/bin/env python3
"""Pure ATR Supertrend-style DCA study.

Rules:
- Compute daily Supertrend-style ATR stop.
- Enter at the next daily open after the daily ATR trend flips.
  - Long after bearish-to-bullish flip.
  - Short after bullish-to-bearish flip when shorts are enabled.
- Start with 1 contract.
- While the stack is open, add 1 contract on scheduled Fridays at 15:50 ET
  when the previous completed daily ATR trend still agrees with the stack and
  the 15:50 price is still on the correct side of the previous ATR stop.
- Exit all contracts at the next daily open after the daily ATR trend flips
  against the stack. If the opposite side is enabled, reverse at the same next
  open.

This is intentionally unrelated to the yearly ORB. It is a pure ATR trend
following / weekly DCA study. Friday 15:50 add prices come from 1-minute data
when provided; otherwise the script falls back to the daily close.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Optional

import argparse
import math

import databento as db
import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from yearly_orb_delivery_research_charts import (
    calculate_daily_atr_trailing_stop,
    calculate_weekly_atr_trailing_stop_on_daily,
)


NY = 'America/New_York'
BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
CYAN = '#00BCD4'
ORANGE = '#FF9800'
YELLOW = '#FFC107'
PURPLE = '#EA80FC'
BROKEN_STOP_ALPHA = 0.48


@dataclass
class Unit:
    unit_id: int
    direction: str
    entry_date: pd.Timestamp
    entry_price: float
    entry_reason: str
    entry_symbol: str
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    def points(self) -> float:
        if self.exit_price is None:
            return 0.0
        if self.direction == 'Long':
            return self.exit_price - self.entry_price
        return self.entry_price - self.exit_price

    def open_points(self, price: float) -> float:
        if self.direction == 'Long':
            return price - self.entry_price
        return self.entry_price - price


@dataclass
class StackTrade:
    trade_id: int
    direction: str
    signal_date: pd.Timestamp
    signal_close: float
    signal_stop: float
    entry_date: Optional[pd.Timestamp] = None
    exit_date: Optional[pd.Timestamp] = None
    exit_reason: str = 'Open'
    units: list[Unit] = field(default_factory=list)
    mae_usd: float = 0.0
    mfe_usd: float = 0.0
    max_units: int = 0
    add_week_counter: int = 0
    scale_event_count: int = 0
    prior_bearish_stop_level: Optional[float] = None
    initial_entry_guard_level: Optional[float] = None

    @property
    def open_units(self) -> list[Unit]:
        return [unit for unit in self.units if unit.exit_date is None]

    def net_points(self) -> float:
        return sum(unit.points() for unit in self.units)


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def load_1550_prices(path: Path, market: str) -> dict[tuple[date, str], float]:
    print(f'Loading 1m add prices from {path}')
    if path.suffix == '.csv':
        raw = pd.read_csv(
            path,
            usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'],
            parse_dates=['ts_event'],
        )
    else:
        raw = db.DBNStore.from_file(str(path)).to_df().reset_index()
    raw = raw[['ts_event', 'symbol', 'open', 'volume']].copy()
    raw = raw[~raw['symbol'].astype(str).str.contains('-', na=False)]
    raw = raw[raw['symbol'].astype(str).str.startswith(market.upper())].copy()
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw = raw[raw['ts_event'].dt.time.eq(time(15, 50))].copy()
    raw['date'] = raw['ts_event'].dt.date
    raw['weekday'] = raw['ts_event'].dt.weekday
    raw = raw[raw['weekday'].eq(4)].copy()
    if raw.empty:
        return {}
    raw = raw.sort_values('ts_event')
    prices = raw.groupby(['date', 'symbol'], sort=False)['open'].first()
    print(f'  Loaded {len(prices):,} Friday 15:50 symbol/date prices')
    return {key: float(value) for key, value in prices.items()}


def update_excursion(trade: StackTrade, low: float, high: float, point_value: float) -> None:
    open_units = trade.open_units
    if not open_units:
        return
    if trade.direction == 'Long':
        adverse = sum((low - unit.entry_price) * point_value for unit in open_units)
        favorable = sum((high - unit.entry_price) * point_value for unit in open_units)
    else:
        adverse = sum((unit.entry_price - high) * point_value for unit in open_units)
        favorable = sum((unit.entry_price - low) * point_value for unit in open_units)
    trade.mae_usd = min(trade.mae_usd, adverse)
    trade.mfe_usd = max(trade.mfe_usd, favorable)
    trade.max_units = max(trade.max_units, len(open_units))


def close_trade(trade: StackTrade, d: pd.Timestamp, px: float, reason: str) -> None:
    for unit in trade.open_units:
        unit.exit_date = d
        unit.exit_price = px
        unit.exit_reason = reason
    trade.exit_date = d
    trade.exit_reason = reason


def parse_size_schedule(raw: str) -> list[int]:
    if not raw.strip():
        return []
    sizes: list[int] = []
    for piece in raw.split(','):
        piece = piece.strip()
        if not piece:
            continue
        value = int(piece)
        if value <= 0:
            raise ValueError('position size schedule values must be positive integers')
        sizes.append(value)
    return sizes


def scale_event_size(schedule: list[int], event_index: int, default_size: int) -> int:
    if schedule:
        if event_index < len(schedule):
            return schedule[event_index]
        return 1
    return default_size


def add_yearly_orb_state(daily: pd.DataFrame) -> pd.DataFrame:
    """Attach causal Jan-Mar yearly ORB state to each daily row.

    The range is fixed from the completed Jan-Mar daily bars. From April onward,
    a close above the range high sets the year state to ``long`` and a close
    below the range low sets it to ``short``. The state carries until the
    opposite boundary is closed through.
    """
    out = daily.copy().sort_values('date').reset_index(drop=True)
    out['date'] = pd.to_datetime(out['date'])
    out['yearly_orb_high'] = pd.NA
    out['yearly_orb_low'] = pd.NA
    out['yearly_orb_state'] = ''
    out['yearly_orb_breakout_date'] = ''

    for year in sorted(out['date'].dt.year.dropna().unique()):
        year_mask = out['date'].dt.year.eq(year)
        range_mask = year_mask & out['date'].dt.month.le(3)
        range_bars = out.loc[range_mask]
        if range_bars.empty:
            continue
        range_high = float(range_bars['high'].astype(float).max())
        range_low = float(range_bars['low'].astype(float).min())
        state = ''
        breakout_date = ''

        for idx in out.loc[year_mask].index:
            d = pd.Timestamp(out.at[idx, 'date'])
            out.at[idx, 'yearly_orb_high'] = range_high
            out.at[idx, 'yearly_orb_low'] = range_low
            if d.month <= 3:
                out.at[idx, 'yearly_orb_state'] = 'building'
                continue

            close = float(out.at[idx, 'close'])
            if close > range_high:
                if state != 'long':
                    breakout_date = d.date().isoformat()
                state = 'long'
            elif close < range_low:
                if state != 'short':
                    breakout_date = d.date().isoformat()
                state = 'short'

            out.at[idx, 'yearly_orb_state'] = state or 'inside'
            out.at[idx, 'yearly_orb_breakout_date'] = breakout_date

    return out


def yearly_allows_long(row: pd.Series, yearly_orb_filter: str) -> bool:
    if yearly_orb_filter == 'none':
        return True
    return str(row.get('yearly_orb_state', '')) == 'long'


def simulate(
    daily: pd.DataFrame,
    add_prices: dict[tuple[date, str], float],
    point_value: float,
    atr_length: int,
    atr_multiplier: float,
    sides: str,
    max_contracts: int,
    initial_contracts: int,
    position_size_schedule: list[int],
    add_interval_weeks: int,
    long_weekly_filter: str,
    weekly_atr_length: int,
    weekly_atr_multiplier: float,
    long_prior_bearish_guard: str,
    long_entry_price_guard: str,
    yearly_orb_filter: str,
) -> tuple[list[StackTrade], pd.DataFrame, dict]:
    work = daily.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work = calculate_daily_atr_trailing_stop(work, atr_length, atr_multiplier)
    work = add_yearly_orb_state(work)
    if long_weekly_filter != 'none':
        weekly = calculate_weekly_atr_trailing_stop_on_daily(work, weekly_atr_length, weekly_atr_multiplier)
        work['weekly_atr'] = weekly['atr']
        work['weekly_atr_stop'] = weekly['atr_stop']
        work['weekly_atr_trend'] = weekly['atr_trend']
    else:
        work['weekly_atr'] = pd.NA
        work['weekly_atr_stop'] = pd.NA
        work['weekly_atr_trend'] = pd.NA

    trades: list[StackTrade] = []
    current: Optional[StackTrade] = None
    pending_entry: Optional[dict] = None
    pending_exit: Optional[dict] = None
    next_unit_id = 1
    realized_points = 0.0
    equity_rows: list[dict] = []
    allow_long = sides in ('long', 'both')
    allow_short = sides in ('short', 'both')
    skipped_long_weekly_filter = 0
    skipped_long_add_weekly_filter = 0
    skipped_long_yearly_orb_filter = 0
    weekly_forced_long_exits = 0
    prior_bearish_guard_exits = 0
    prior_bearish_guard_reentries = 0
    prior_bearish_guard_paused = False
    prior_bearish_guard_level: Optional[float] = None
    prior_bearish_guard_exit_date: Optional[pd.Timestamp] = None
    prior_bearish_guard_reentry_week_counter = 0
    entry_price_guard_exits = 0
    entry_price_guard_reentries = 0
    entry_price_guard_paused = False
    entry_price_guard_level: Optional[float] = None

    def weekly_allows_long(row: pd.Series) -> bool:
        if long_weekly_filter == 'none':
            return True
        weekly_trend = row.get('weekly_atr_trend')
        if pd.isna(weekly_trend):
            return True
        return str(weekly_trend) != 'down'

    def start_trade(entry_info: dict, entry_date: pd.Timestamp, entry_price: float, symbol: str) -> StackTrade:
        nonlocal next_unit_id
        trade = StackTrade(
            trade_id=len(trades) + 1,
            direction=entry_info['direction'],
            signal_date=entry_info['signal_date'],
            signal_close=entry_info['signal_close'],
            signal_stop=entry_info['signal_stop'],
            entry_date=entry_date,
            prior_bearish_stop_level=entry_info.get('prior_bearish_stop_level'),
            initial_entry_guard_level=entry_info.get('initial_entry_guard_level', entry_price),
        )
        start_units = min(scale_event_size(position_size_schedule, 0, max(initial_contracts, 1)), max(max_contracts, 1))
        for _ in range(start_units):
            trade.units.append(
                Unit(
                    next_unit_id,
                    entry_info['direction'],
                    entry_date,
                    entry_price,
                    entry_info.get('entry_reason', 'ATR-Flip-Entry'),
                    symbol,
                )
            )
            next_unit_id += 1
        trade.max_units = len(trade.open_units)
        trade.scale_event_count = 1
        return trade

    for idx, row in work.iterrows():
        d = pd.Timestamp(row['date'])
        o = float(row['open'])
        h = float(row['high'])
        l = float(row['low'])
        c = float(row['close'])
        symbol = str(row['symbol'])

        if pending_exit is not None and current is not None:
            close_trade(current, d, o, pending_exit['reason'])
            realized_points += current.net_points()
            trades.append(current)
            if pending_exit.get('prior_bearish_guard_pause'):
                prior_bearish_guard_paused = True
                prior_bearish_guard_level = pending_exit.get('prior_bearish_stop_level')
                prior_bearish_guard_exit_date = d
                prior_bearish_guard_reentry_week_counter = 0
                prior_bearish_guard_exits += 1
            elif pending_exit.get('entry_price_guard_pause'):
                entry_price_guard_paused = True
                entry_price_guard_level = pending_exit.get('entry_price_guard_level')
                entry_price_guard_exits += 1
            elif current.direction == 'Long':
                prior_bearish_guard_paused = False
                prior_bearish_guard_level = None
                prior_bearish_guard_exit_date = None
                prior_bearish_guard_reentry_week_counter = 0
                entry_price_guard_paused = False
                entry_price_guard_level = None
            current = None
            reverse_entry = pending_exit.get('reverse_entry')
            pending_exit = None
            if reverse_entry is not None:
                if reverse_entry['direction'] == 'Long' and not weekly_allows_long(row):
                    skipped_long_weekly_filter += 1
                elif reverse_entry['direction'] == 'Long' and not reverse_entry.get('yearly_orb_allowed', True):
                    skipped_long_yearly_orb_filter += 1
                else:
                    current = start_trade(reverse_entry, d, o, symbol)

        if pending_entry is not None and current is None:
            if pending_entry['direction'] == 'Long' and not weekly_allows_long(row):
                skipped_long_weekly_filter += 1
            elif pending_entry['direction'] == 'Long' and not pending_entry.get('yearly_orb_allowed', True):
                skipped_long_yearly_orb_filter += 1
            else:
                current = start_trade(pending_entry, d, o, symbol)
                if current.direction == 'Long':
                    prior_bearish_guard_paused = False
                    prior_bearish_guard_level = current.prior_bearish_stop_level
                    prior_bearish_guard_exit_date = None
                    prior_bearish_guard_reentry_week_counter = 0
                    entry_price_guard_paused = False
                    entry_price_guard_level = current.initial_entry_guard_level
            pending_entry = None

        if (
            current is not None
            and current.direction == 'Long'
            and long_weekly_filter == 'flat-when-bearish'
            and not weekly_allows_long(row)
        ):
            close_trade(current, d, o, 'Weekly-ATR-Bearish-Exit')
            realized_points += current.net_points()
            trades.append(current)
            current = None
            weekly_forced_long_exits += 1
            entry_price_guard_paused = False
            entry_price_guard_level = None

        if current is not None:
            update_excursion(current, l, h, point_value)

        if current is not None and d.weekday() == 4 and idx > 0 and current.entry_date is not None and d.date() > current.entry_date.date():
            prev = work.loc[idx - 1]
            prev_stop = float(prev['atr_stop'])
            prev_trend = str(prev['atr_trend'])
            add_price = add_prices.get((d.date(), symbol), c)
            if current.direction == 'Long':
                base_add_ok = prev_trend == 'up' and add_price > prev_stop
                add_ok = base_add_ok and weekly_allows_long(row)
                if (
                    long_prior_bearish_guard != 'none'
                    and current.prior_bearish_stop_level is not None
                    and add_price <= current.prior_bearish_stop_level
                ):
                    add_ok = False
                if (
                    long_entry_price_guard != 'none'
                    and current.initial_entry_guard_level is not None
                    and add_price <= current.initial_entry_guard_level
                ):
                    add_ok = False
                if base_add_ok and not weekly_allows_long(row):
                    skipped_long_add_weekly_filter += 1
            else:
                add_ok = prev_trend == 'down' and add_price < prev_stop
            if add_ok:
                current.add_week_counter += 1
            if (
                add_ok
                and current.add_week_counter % max(add_interval_weeks, 1) == 0
                and len(current.open_units) < max_contracts
            ):
                add_units = scale_event_size(position_size_schedule, current.scale_event_count, 1)
                add_units = min(add_units, max_contracts - len(current.open_units))
                for _ in range(max(add_units, 0)):
                    current.units.append(Unit(next_unit_id, current.direction, d, add_price, 'Friday-1550-Add', symbol))
                    next_unit_id += 1
                current.scale_event_count += 1
                current.max_units = max(current.max_units, len(current.open_units))

        if (
            current is None
            and pending_entry is None
            and prior_bearish_guard_paused
            and prior_bearish_guard_level is not None
            and prior_bearish_guard_exit_date is not None
            and d.weekday() == 4
            and d.date() > prior_bearish_guard_exit_date.date()
            and idx > 0
        ):
            prev = work.loc[idx - 1]
            add_price = add_prices.get((d.date(), symbol), c)
            base_reentry_ok = str(prev['atr_trend']) == 'up' and add_price > prior_bearish_guard_level
            if base_reentry_ok and not weekly_allows_long(row):
                skipped_long_weekly_filter += 1
            elif base_reentry_ok and not yearly_allows_long(prev, yearly_orb_filter):
                skipped_long_yearly_orb_filter += 1
            elif base_reentry_ok:
                prior_bearish_guard_reentry_week_counter += 1
                if prior_bearish_guard_reentry_week_counter % max(add_interval_weeks, 1) == 0:
                    current = start_trade(
                        {
                            'direction': 'Long',
                            'signal_date': d,
                            'signal_close': c,
                            'signal_stop': float(prev['atr_stop']),
                            'prior_bearish_stop_level': prior_bearish_guard_level,
                            'entry_reason': 'Prior-Bearish-Stop-Reclaim-Reentry',
                            'yearly_orb_allowed': True,
                        },
                        d,
                        add_price,
                        symbol,
                    )
                    prior_bearish_guard_paused = False
                    prior_bearish_guard_exit_date = None
                    prior_bearish_guard_reentry_week_counter = 0
                    prior_bearish_guard_reentries += 1

        if idx > 0:
            prev_trend = str(work.loc[idx - 1, 'atr_trend'])
            trend = str(row['atr_trend'])
            if current is not None:
                if current.direction == 'Long' and prev_trend == 'up' and trend == 'down':
                    reverse = None
                    if allow_short:
                        reverse = {
                            'direction': 'Short',
                            'signal_date': d,
                            'signal_close': c,
                            'signal_stop': float(row['atr_stop']),
                        }
                    pending_exit = {'reason': 'ATR-Flip-Exit', 'reverse_entry': reverse}
                elif current.direction == 'Short' and prev_trend == 'down' and trend == 'up':
                    reverse = None
                    if allow_long and weekly_allows_long(row) and yearly_allows_long(row, yearly_orb_filter):
                        reverse = {
                            'direction': 'Long',
                            'signal_date': d,
                            'signal_close': c,
                            'signal_stop': float(row['atr_stop']),
                            'prior_bearish_stop_level': float(work.loc[idx - 1, 'atr_stop']),
                            'yearly_orb_allowed': True,
                        }
                    elif allow_long:
                        if not weekly_allows_long(row):
                            skipped_long_weekly_filter += 1
                        else:
                            skipped_long_yearly_orb_filter += 1
                    pending_exit = {'reason': 'ATR-Flip-Exit', 'reverse_entry': reverse}
            elif pending_entry is None:
                if prev_trend == 'down' and trend == 'up' and allow_long:
                    if weekly_allows_long(row) and yearly_allows_long(row, yearly_orb_filter):
                        pending_entry = {
                            'direction': 'Long',
                            'signal_date': d,
                            'signal_close': c,
                            'signal_stop': float(row['atr_stop']),
                            'prior_bearish_stop_level': float(work.loc[idx - 1, 'atr_stop']),
                            'yearly_orb_allowed': True,
                        }
                    else:
                        if not weekly_allows_long(row):
                            skipped_long_weekly_filter += 1
                        else:
                            skipped_long_yearly_orb_filter += 1
                elif prev_trend == 'up' and trend == 'down' and allow_short:
                    pending_entry = {
                        'direction': 'Short',
                        'signal_date': d,
                        'signal_close': c,
                        'signal_stop': float(row['atr_stop']),
                    }

            if (
                current is not None
                and current.direction == 'Long'
                and pending_exit is None
                and long_prior_bearish_guard != 'none'
                and current.prior_bearish_stop_level is not None
            ):
                if trend == 'up' and c < current.prior_bearish_stop_level:
                    pending_exit = {
                        'reason': 'Prior-Bearish-Stop-Close-Exit',
                        'prior_bearish_guard_pause': True,
                        'prior_bearish_stop_level': current.prior_bearish_stop_level,
                    }
            if (
                current is not None
                and current.direction == 'Long'
                and pending_exit is None
                and long_entry_price_guard != 'none'
                and current.initial_entry_guard_level is not None
            ):
                if trend == 'up' and c < current.initial_entry_guard_level:
                    pending_exit = {
                        'reason': 'Initial-Entry-Close-Exit',
                        'entry_price_guard_pause': True,
                        'entry_price_guard_level': current.initial_entry_guard_level,
                    }
            if current is None and trend == 'down' and prior_bearish_guard_paused:
                prior_bearish_guard_paused = False
                prior_bearish_guard_level = None
                prior_bearish_guard_exit_date = None
                prior_bearish_guard_reentry_week_counter = 0
            if current is None and trend == 'down' and entry_price_guard_paused:
                entry_price_guard_paused = False
                entry_price_guard_level = None

            if (
                current is None
                and pending_entry is None
                and entry_price_guard_paused
                and entry_price_guard_level is not None
                and trend == 'up'
                and c > entry_price_guard_level
                and weekly_allows_long(row)
                and yearly_allows_long(row, yearly_orb_filter)
            ):
                pending_entry = {
                    'direction': 'Long',
                    'signal_date': d,
                    'signal_close': c,
                    'signal_stop': float(row['atr_stop']),
                    'prior_bearish_stop_level': float(work.loc[idx - 1, 'atr_stop']),
                    'initial_entry_guard_level': entry_price_guard_level,
                    'entry_reason': 'Initial-Entry-Reclaim-Reentry',
                    'yearly_orb_allowed': True,
                }
                entry_price_guard_paused = False
                entry_price_guard_reentries += 1
            elif (
                current is None
                and pending_entry is None
                and entry_price_guard_paused
                and entry_price_guard_level is not None
                and trend == 'up'
                and c > entry_price_guard_level
                and weekly_allows_long(row)
                and not yearly_allows_long(row, yearly_orb_filter)
            ):
                skipped_long_yearly_orb_filter += 1

        open_unrealized = 0.0
        open_units = 0
        if current is not None:
            open_units = len(current.open_units)
            open_unrealized = sum(unit.open_points(c) for unit in current.open_units)
        equity_rows.append(
            {
                'date': d.date().isoformat(),
                'realized_points': realized_points,
                'open_unrealized_points': open_unrealized,
                'total_equity_points': realized_points + open_unrealized,
                'open_units': open_units,
                'direction': current.direction if current is not None else '',
            }
        )

    if current is not None:
        last = work.iloc[-1]
        close_trade(current, pd.Timestamp(last['date']), float(last['close']), 'Period-Close')
        realized_points += current.net_points()
        trades.append(current)

    equity = pd.DataFrame(equity_rows)
    metadata = {
        'long_weekly_filter': long_weekly_filter,
        'weekly_atr_length': weekly_atr_length,
        'weekly_atr_multiplier': weekly_atr_multiplier,
        'initial_contracts': initial_contracts,
        'position_size_schedule': ','.join(str(x) for x in position_size_schedule) if position_size_schedule else '',
        'skipped_long_weekly_filter': skipped_long_weekly_filter,
        'skipped_long_add_weekly_filter': skipped_long_add_weekly_filter,
        'yearly_orb_filter': yearly_orb_filter,
        'skipped_long_yearly_orb_filter': skipped_long_yearly_orb_filter,
        'weekly_forced_long_exits': weekly_forced_long_exits,
        'long_prior_bearish_guard': long_prior_bearish_guard,
        'prior_bearish_guard_exits': prior_bearish_guard_exits,
        'prior_bearish_guard_reentries': prior_bearish_guard_reentries,
        'long_entry_price_guard': long_entry_price_guard,
        'entry_price_guard_exits': entry_price_guard_exits,
        'entry_price_guard_reentries': entry_price_guard_reentries,
    }
    return trades, equity, metadata


def simulate_weekly_primary(
    daily: pd.DataFrame,
    add_prices: dict[tuple[date, str], float],
    point_value: float,
    atr_length: int,
    atr_multiplier: float,
    sides: str,
    max_contracts: int,
    initial_contracts: int,
    position_size_schedule: list[int],
    add_interval_weeks: int,
    long_entry_price_guard: str,
    yearly_orb_filter: str,
) -> tuple[list[StackTrade], pd.DataFrame, dict]:
    work = daily.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work = calculate_daily_atr_trailing_stop(work, atr_length, atr_multiplier)
    work = add_yearly_orb_state(work)
    weekly = calculate_weekly_atr_trailing_stop_on_daily(work, atr_length, atr_multiplier)
    work['weekly_atr'] = weekly['atr']
    work['weekly_atr_stop'] = weekly['atr_stop']
    work['weekly_atr_trend'] = weekly['atr_trend']

    trades: list[StackTrade] = []
    current: Optional[StackTrade] = None
    pending_entry: Optional[dict] = None
    pending_exit: Optional[dict] = None
    next_unit_id = 1
    realized_points = 0.0
    equity_rows: list[dict] = []
    allow_long = sides in ('long', 'both')
    weekly_forced_long_exits = 0
    skipped_long_yearly_orb_filter = 0
    entry_price_guard_exits = 0
    entry_price_guard_reentries = 0
    entry_price_guard_paused = False
    entry_price_guard_level: Optional[float] = None

    def start_trade(entry_info: dict, entry_date: pd.Timestamp, entry_price: float, symbol: str) -> StackTrade:
        nonlocal next_unit_id
        trade = StackTrade(
            trade_id=len(trades) + 1,
            direction=entry_info['direction'],
            signal_date=entry_info['signal_date'],
            signal_close=entry_info['signal_close'],
            signal_stop=entry_info['signal_stop'],
            entry_date=entry_date,
            initial_entry_guard_level=entry_info.get('initial_entry_guard_level', entry_price),
        )
        start_units = min(scale_event_size(position_size_schedule, 0, max(initial_contracts, 1)), max(max_contracts, 1))
        for _ in range(start_units):
            trade.units.append(
                Unit(
                    next_unit_id,
                    entry_info['direction'],
                    entry_date,
                    entry_price,
                    entry_info.get('entry_reason', 'Weekly-ATR-Flip-Entry'),
                    symbol,
                )
            )
            next_unit_id += 1
        trade.max_units = len(trade.open_units)
        trade.scale_event_count = 1
        return trade

    for idx, row in work.iterrows():
        d = pd.Timestamp(row['date'])
        o = float(row['open'])
        h = float(row['high'])
        l = float(row['low'])
        c = float(row['close'])
        symbol = str(row['symbol'])
        weekly_trend = row.get('weekly_atr_trend')
        weekly_stop = row.get('weekly_atr_stop')
        trend = str(weekly_trend) if not pd.isna(weekly_trend) else ''

        if pending_exit is not None and current is not None:
            close_trade(current, d, o, pending_exit['reason'])
            realized_points += current.net_points()
            trades.append(current)
            if pending_exit.get('entry_price_guard_pause'):
                entry_price_guard_paused = True
                entry_price_guard_level = pending_exit.get('entry_price_guard_level')
                entry_price_guard_exits += 1
            else:
                entry_price_guard_paused = False
                entry_price_guard_level = None
            current = None
            pending_exit = None

        if pending_entry is not None and current is None:
            if pending_entry['direction'] == 'Long' and not pending_entry.get('yearly_orb_allowed', True):
                skipped_long_yearly_orb_filter += 1
            else:
                current = start_trade(pending_entry, d, o, symbol)
                entry_price_guard_paused = False
                entry_price_guard_level = current.initial_entry_guard_level
            pending_entry = None

        if current is not None and current.direction == 'Long' and trend == 'down':
            close_trade(current, d, o, 'Weekly-ATR-Bearish-Exit')
            realized_points += current.net_points()
            trades.append(current)
            current = None
            entry_price_guard_paused = False
            entry_price_guard_level = None
            weekly_forced_long_exits += 1

        if current is None and idx > 0 and allow_long and not entry_price_guard_paused:
            prev_trend = work.loc[idx - 1].get('weekly_atr_trend')
            prev_trend = str(prev_trend) if not pd.isna(prev_trend) else ''
            if prev_trend == 'down' and trend == 'up':
                prev_row = work.loc[idx - 1]
                if yearly_allows_long(prev_row, yearly_orb_filter):
                    current = start_trade(
                        {
                            'direction': 'Long',
                            'signal_date': d,
                            'signal_close': c,
                            'signal_stop': float(weekly_stop),
                            'initial_entry_guard_level': o,
                            'entry_reason': 'Weekly-ATR-Flip-Entry',
                            'yearly_orb_allowed': True,
                        },
                        d,
                        o,
                        symbol,
                    )
                    entry_price_guard_level = current.initial_entry_guard_level
                else:
                    skipped_long_yearly_orb_filter += 1

        if current is not None:
            update_excursion(current, l, h, point_value)

        if (
            current is not None
            and current.direction == 'Long'
            and d.weekday() == 4
            and idx > 0
            and current.entry_date is not None
            and d.date() > current.entry_date.date()
            and trend == 'up'
        ):
            add_price = add_prices.get((d.date(), symbol), c)
            add_ok = not pd.isna(weekly_stop) and add_price > float(weekly_stop)
            if (
                long_entry_price_guard != 'none'
                and current.initial_entry_guard_level is not None
                and add_price <= current.initial_entry_guard_level
            ):
                add_ok = False
            if add_ok:
                current.add_week_counter += 1
            if (
                add_ok
                and current.add_week_counter % max(add_interval_weeks, 1) == 0
                and len(current.open_units) < max_contracts
            ):
                add_units = scale_event_size(position_size_schedule, current.scale_event_count, 1)
                add_units = min(add_units, max_contracts - len(current.open_units))
                for _ in range(max(add_units, 0)):
                    current.units.append(Unit(next_unit_id, current.direction, d, add_price, 'Friday-1550-Add', symbol))
                    next_unit_id += 1
                current.scale_event_count += 1
                current.max_units = max(current.max_units, len(current.open_units))

        if idx > 0:
            if (
                current is not None
                and current.direction == 'Long'
                and pending_exit is None
                and long_entry_price_guard != 'none'
                and current.initial_entry_guard_level is not None
                and trend == 'up'
                and c < current.initial_entry_guard_level
            ):
                pending_exit = {
                    'reason': 'Initial-Entry-Close-Exit',
                    'entry_price_guard_pause': True,
                    'entry_price_guard_level': current.initial_entry_guard_level,
                }
            if current is None and trend == 'down' and entry_price_guard_paused:
                entry_price_guard_paused = False
                entry_price_guard_level = None
            if (
                current is None
                and pending_entry is None
                and entry_price_guard_paused
                and entry_price_guard_level is not None
                and trend == 'up'
                and c > entry_price_guard_level
                and yearly_allows_long(row, yearly_orb_filter)
            ):
                pending_entry = {
                    'direction': 'Long',
                    'signal_date': d,
                    'signal_close': c,
                    'signal_stop': float(weekly_stop),
                    'initial_entry_guard_level': entry_price_guard_level,
                    'entry_reason': 'Initial-Entry-Reclaim-Reentry',
                    'yearly_orb_allowed': True,
                }
                entry_price_guard_paused = False
                entry_price_guard_reentries += 1
            elif (
                current is None
                and pending_entry is None
                and entry_price_guard_paused
                and entry_price_guard_level is not None
                and trend == 'up'
                and c > entry_price_guard_level
                and not yearly_allows_long(row, yearly_orb_filter)
            ):
                skipped_long_yearly_orb_filter += 1

        open_unrealized = 0.0
        open_units = 0
        if current is not None:
            open_units = len(current.open_units)
            open_unrealized = sum(unit.open_points(c) for unit in current.open_units)
        equity_rows.append(
            {
                'date': d.date().isoformat(),
                'realized_points': realized_points,
                'open_unrealized_points': open_unrealized,
                'total_equity_points': realized_points + open_unrealized,
                'open_units': open_units,
                'direction': current.direction if current is not None else '',
            }
        )

    if current is not None:
        last = work.iloc[-1]
        close_trade(current, pd.Timestamp(last['date']), float(last['close']), 'Period-Close')
        realized_points += current.net_points()
        trades.append(current)

    equity = pd.DataFrame(equity_rows)
    metadata = {
        'signal_timeframe': 'weekly',
        'long_weekly_filter': 'primary',
        'weekly_atr_length': atr_length,
        'weekly_atr_multiplier': atr_multiplier,
        'initial_contracts': initial_contracts,
        'position_size_schedule': ','.join(str(x) for x in position_size_schedule) if position_size_schedule else '',
        'skipped_long_weekly_filter': 0,
        'skipped_long_add_weekly_filter': 0,
        'yearly_orb_filter': yearly_orb_filter,
        'skipped_long_yearly_orb_filter': skipped_long_yearly_orb_filter,
        'weekly_forced_long_exits': weekly_forced_long_exits,
        'long_prior_bearish_guard': 'none',
        'prior_bearish_guard_exits': 0,
        'prior_bearish_guard_reentries': 0,
        'long_entry_price_guard': long_entry_price_guard,
        'entry_price_guard_exits': entry_price_guard_exits,
        'entry_price_guard_reentries': entry_price_guard_reentries,
    }
    return trades, equity, metadata


def trade_rows(trades: list[StackTrade], point_value: float) -> list[dict]:
    rows: list[dict] = []
    cumulative = 0.0
    for trade in trades:
        pnl = trade.net_points()
        cumulative += pnl
        rows.append(
            {
                'trade_id': trade.trade_id,
                'direction': trade.direction,
                'signal_date': trade.signal_date.date().isoformat(),
                'entry_date': trade.entry_date.date().isoformat() if trade.entry_date is not None else '',
                'exit_date': trade.exit_date.date().isoformat() if trade.exit_date is not None else '',
                'exit_reason': trade.exit_reason,
                'prior_bearish_stop_level': trade.prior_bearish_stop_level,
                'initial_entry_guard_level': trade.initial_entry_guard_level,
                'units': len(trade.units),
                'max_units': trade.max_units,
                'net_points': round(pnl, 6),
                'net_usd': round(pnl * point_value, 2),
                'mae_usd': round(trade.mae_usd, 2),
                'mfe_usd': round(trade.mfe_usd, 2),
                'cumulative_points': round(cumulative, 6),
                'cumulative_usd': round(cumulative * point_value, 2),
            }
        )
    return rows


def unit_rows(trades: list[StackTrade], point_value: float) -> list[dict]:
    rows: list[dict] = []
    for trade in trades:
        for unit in trade.units:
            rows.append(
                {
                    'trade_id': trade.trade_id,
                    'unit_id': unit.unit_id,
                    'direction': unit.direction,
                    'entry_date': unit.entry_date.date().isoformat(),
                    'entry_price': unit.entry_price,
                    'entry_reason': unit.entry_reason,
                    'entry_symbol': unit.entry_symbol,
                    'exit_date': unit.exit_date.date().isoformat() if unit.exit_date is not None else '',
                    'exit_price': unit.exit_price,
                    'exit_reason': unit.exit_reason,
                    'points': round(unit.points(), 6),
                    'usd': round(unit.points() * point_value, 2),
                }
            )
    return rows


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    dates = pd.to_datetime(bars['date'])
    x = mdates.date2num(dates)
    width = 0.72
    for xval, (_, row) in zip(x, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=color, linewidth=0.7, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (xval - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
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


def plot_atr_stop_with_extensions(
    ax: plt.Axes,
    work: pd.DataFrame,
    colors: dict[str, str],
    linewidth: float,
    alpha: float,
    linestyle: str,
    zorder: int,
    extension_weeks: int,
) -> None:
    valid = work.copy()
    valid = valid[valid['atr_stop'].notna() & valid['atr_trend'].isin(['up', 'down'])].copy()
    if valid.empty:
        return

    for trend, color in colors.items():
        segment = valid[valid['atr_trend'].eq(trend)].copy()
        split_id = (segment.index.to_series().diff() != 1).cumsum()
        for _, chunk in segment.groupby(split_id):
            ax.plot(
                mdates.date2num(pd.to_datetime(chunk['date'])),
                chunk['atr_stop'].astype(float),
                color=color,
                linewidth=linewidth,
                alpha=alpha,
                linestyle=linestyle,
                zorder=zorder,
            )

    if extension_weeks <= 0:
        return

    extension_delta = pd.Timedelta(weeks=extension_weeks)
    for idx in range(1, len(valid)):
        prev = valid.iloc[idx - 1]
        curr = valid.iloc[idx]
        prev_trend = str(prev['atr_trend'])
        curr_trend = str(curr['atr_trend'])
        if prev_trend == curr_trend:
            continue
        start = pd.Timestamp(curr['date'])
        end = min(start + extension_delta, pd.Timestamp(valid['date'].max()))
        if end <= start:
            continue
        ax.hlines(
            float(prev['atr_stop']),
            mdates.date2num(start),
            mdates.date2num(end),
            colors=colors.get(prev_trend, GRID),
            linewidth=linewidth + 0.15,
            alpha=BROKEN_STOP_ALPHA,
            linestyle=':',
            zorder=max(zorder - 1, 1),
        )


def draw_year_chart(
    year: int,
    bars: pd.DataFrame,
    trades: list[StackTrade],
    out_path: Path,
    market: str,
    point_value: float,
    atr_length: int,
    atr_multiplier: float,
    plot_weekly_atr: bool,
    weekly_atr_length: int,
    weekly_atr_multiplier: float,
    atr_extension_weeks: int,
    volume_panel: bool = False,
) -> dict:
    all_work = bars.copy().sort_values('date').reset_index(drop=True)
    all_work['date'] = pd.to_datetime(all_work['date'])
    all_work = calculate_daily_atr_trailing_stop(all_work, atr_length, atr_multiplier)
    year_start = pd.Timestamp(year=year, month=1, day=1)
    year_end = pd.Timestamp(year=year, month=12, day=31)
    visible = all_work[all_work['date'].between(year_start, year_end)].copy()
    if visible.empty:
        visible = all_work[all_work['date'].dt.year.eq(year)].copy()
    context_start = year_start - pd.Timedelta(weeks=max(atr_extension_weeks, 0))
    context_end = year_end + pd.Timedelta(weeks=max(atr_extension_weeks, 0))
    work = all_work[all_work['date'].between(context_start, context_end)].copy()
    work['date'] = pd.to_datetime(work['date'])
    weekly_work = None
    if plot_weekly_atr:
        weekly_full = calculate_weekly_atr_trailing_stop_on_daily(all_work, weekly_atr_length, weekly_atr_multiplier)
        weekly_full['date'] = pd.to_datetime(weekly_full['date'])
        weekly_work = weekly_full[weekly_full['date'].between(context_start, context_end)].copy()
    if volume_panel and 'volume' in visible.columns:
        fig, (ax, ax_vol) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(18, 10.4),
            facecolor=BG,
            gridspec_kw={'height_ratios': [4.7, 1.05], 'hspace': 0.04},
        )
        style_axis(ax_vol)
    else:
        fig = plt.figure(figsize=(18, 9), facecolor=BG)
        ax = fig.add_subplot(111)
        ax_vol = None
    style_axis(ax)
    draw_candles(ax, visible)
    if ax_vol is not None:
        xs_vol = mdates.date2num(pd.to_datetime(visible['date']))
        vol_colors = [GREEN if float(row['close']) >= float(row['open']) else RED for _, row in visible.iterrows()]
        volumes = visible['volume'].astype(float)
        ax_vol.bar(xs_vol, volumes, width=0.8, color=vol_colors, alpha=0.52, align='center', zorder=2)
        vol_ma = volumes.rolling(20, min_periods=5).mean()
        ax_vol.plot(xs_vol, vol_ma, color='#FFD54F', linewidth=1.0, alpha=0.95, zorder=3)
        ax_vol.set_ylabel('Daily vol', color=GRID, fontsize=8)
        ax_vol.yaxis.set_major_formatter(
            plt.FuncFormatter(
                lambda value, _pos: f'{value / 1_000_000:.1f}M' if value >= 1_000_000 else f'{value / 1_000:.0f}K'
            )
        )

    plot_atr_stop_with_extensions(
        ax,
        work,
        {'up': CYAN, 'down': ORANGE},
        linewidth=1.15,
        alpha=0.84,
        linestyle='-',
        zorder=5,
        extension_weeks=atr_extension_weeks,
    )

    if weekly_work is not None:
        plot_atr_stop_with_extensions(
            ax,
            weekly_work,
            {'up': '#B2FF59', 'down': '#FF6E40'},
            linewidth=1.65,
            alpha=0.88,
            linestyle='--',
            zorder=6,
            extension_weeks=atr_extension_weeks,
        )

    year_trades = [
        trade
        for trade in trades
        if (trade.entry_date is not None and trade.entry_date.year == year)
        or (trade.exit_date is not None and trade.exit_date.year == year)
        or any(unit.entry_date.year == year for unit in trade.units)
    ]
    total_pts = sum(trade.net_points() for trade in year_trades if trade.exit_date is not None and trade.exit_date.year == year)
    for trade in year_trades:
        for unit in trade.units:
            if unit.entry_date.year == year:
                is_add = unit.entry_reason == 'Friday-1550-Add'
                marker = 'P' if is_add else ('^' if unit.direction == 'Long' else 'v')
                color = PURPLE if is_add else YELLOW
                ax.scatter(
                    [mdates.date2num(unit.entry_date)],
                    [unit.entry_price],
                    marker=marker,
                    s=86 if marker == '^' else 62,
                    color=color,
                    edgecolor='black',
                    linewidth=0.7,
                    zorder=10,
                )
            if unit.exit_date is not None and unit.exit_date.year == year:
                ax.scatter(
                    [mdates.date2num(unit.exit_date)],
                    [unit.exit_price],
                    marker='X',
                    s=78,
                    color='#FF5252',
                    edgecolor='black',
                    linewidth=0.8,
                    zorder=11,
                )

    dates = pd.to_datetime(visible['date'])
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    if ax_vol is not None:
        ax_vol.xaxis.set_major_locator(mdates.MonthLocator())
        ax_vol.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=4), dates.iloc[-1] + pd.Timedelta(days=8))
    ax.set_title(
        f'{year} {market} ATR DCA · {len(year_trades)} active stack(s) · '
        f'exits this year {total_pts:+.1f} pts (${total_pts * point_value:+,.0f})',
        color='white',
        fontsize=10,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    legend_items = [
        Line2D([0], [0], color=CYAN, lw=1.2, label='Daily ATR up stop'),
        Line2D([0], [0], color=ORANGE, lw=1.2, label='Daily ATR down stop'),
    ]
    if weekly_work is not None:
        legend_items.extend(
            [
                Line2D([0], [0], color='#B2FF59', lw=1.7, linestyle='--', label='Weekly ATR up stop'),
                Line2D([0], [0], color='#FF6E40', lw=1.7, linestyle='--', label='Weekly ATR down stop'),
            ]
        )
    if atr_extension_weeks > 0:
        legend_items.append(
            Line2D(
                [0],
                [0],
                color=GRID,
                lw=1.2,
                linestyle=':',
                alpha=BROKEN_STOP_ALPHA,
                label=f'Broken ATR stop extended {atr_extension_weeks}w',
            )
        )
    if ax_vol is not None:
        legend_items.append(Line2D([0], [0], color='#FFD54F', lw=1.1, label='20d volume avg'))
    legend = ax.legend(handles=legend_items, loc='upper left', fontsize=8, framealpha=0.18)
    for text in legend.get_texts():
        text.set_color('white')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return {
        'year': year,
        'trades_active': len(year_trades),
        'exit_points': round(total_pts, 6),
        'exit_usd': round(total_pts * point_value, 2),
        'chart': f'{year}/{year}.png',
    }


def write_report(
    out_root: Path,
    market: str,
    point_value: float,
    trades_df: pd.DataFrame,
    units_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    chart_rows: list[dict],
    atr_length: int,
    atr_multiplier: float,
    sides: str,
    max_contracts: int,
    initial_contracts: int,
    add_interval_weeks: int,
    metadata: dict,
    plot_weekly_atr: bool,
    atr_extension_weeks: int,
) -> None:
    if trades_df.empty:
        stats = {
            'trades': 0,
            'units': 0,
            'net_points': 0.0,
            'net_usd': 0.0,
            'closed_dd_points': 0.0,
            'mtm_dd_points': 0.0,
            'worst_mae_usd': 0.0,
            'avg_mae_usd': 0.0,
            'win_rate': 0.0,
            'pf': math.nan,
        }
    else:
        pnl = pd.to_numeric(trades_df['net_points'], errors='coerce').fillna(0.0)
        eq = pd.to_numeric(equity_df['total_equity_points'], errors='coerce').fillna(0.0)
        stats = {
            'trades': len(trades_df),
            'units': len(units_df),
            'net_points': float(pnl.sum()),
            'net_usd': float(pnl.sum() * point_value),
            'closed_dd_points': max_drawdown(pnl),
            'mtm_dd_points': float((eq - eq.cummax()).min()) if not eq.empty else 0.0,
            'worst_mae_usd': float(pd.to_numeric(trades_df['mae_usd'], errors='coerce').fillna(0.0).min()),
            'avg_mae_usd': float(pd.to_numeric(trades_df['mae_usd'], errors='coerce').fillna(0.0).mean()),
            'win_rate': float((pnl > 0).mean() * 100),
            'pf': profit_factor(pnl),
        }

    signal_timeframe = metadata.get('signal_timeframe', 'daily')
    primary_label = 'weekly' if signal_timeframe == 'weekly' else 'daily'
    weekly_filter_text = 'primary weekly signal' if signal_timeframe == 'weekly' else metadata.get('long_weekly_filter', 'none')
    schedule_text = metadata.get('position_size_schedule') or f'{initial_contracts}, then 1 per add'
    yearly_filter_text = metadata.get('yearly_orb_filter', 'none')
    lines = [
        f'# {market} ATR Supertrend DCA Study',
        '',
        f'Signal timeframe: {signal_timeframe}.',
        f'Rules: {primary_label} Supertrend-style ATR({atr_length}) x {atr_multiplier:g}; sides={sides}; enter at the next available daily open after an enabled {primary_label} ATR trend flip; scale every {add_interval_weeks} eligible Friday(s) at 15:50 ET while the completed {primary_label} ATR trend still agrees and price is on the correct side of the completed {primary_label} ATR stop; max contracts per stack={max_contracts}; exit the entire stack at the next available daily open after an opposite {primary_label} ATR flip.',
        f'Size schedule: {schedule_text}; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.',
        f'Weekly long filter: {weekly_filter_text} using weekly Supertrend-style ATR({metadata.get("weekly_atr_length", atr_length)}) x {metadata.get("weekly_atr_multiplier", atr_multiplier):g}; skipped long entries/reversals: {metadata.get("skipped_long_weekly_filter", 0)}; skipped long add windows: {metadata.get("skipped_long_add_weekly_filter", 0)}; weekly-forced exits: {metadata.get("weekly_forced_long_exits", 0)}.',
        f'Yearly ORB first-entry filter: {yearly_filter_text}; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: {metadata.get("skipped_long_yearly_orb_filter", 0)}. Adds and exits are unchanged by this filter.',
        f'Prior bearish stop guard: {metadata.get("long_prior_bearish_guard", "none")}; guard exits: {metadata.get("prior_bearish_guard_exits", 0)}; guard reentries: {metadata.get("prior_bearish_guard_reentries", 0)}.',
        f'Initial entry price guard: {metadata.get("long_entry_price_guard", "none")}; guard exits: {metadata.get("entry_price_guard_exits", 0)}; guard reentries: {metadata.get("entry_price_guard_reentries", 0)}.',
        '',
        'Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.',
        (
            f'Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. '
            f'Dotted horizontal segments extend a broken ATR stop for {atr_extension_weeks} week(s) after the reversal close.'
        )
        if plot_weekly_atr
        else (
            f'Chart note: solid cyan/orange lines are the daily ATR stop. Dotted horizontal segments extend a broken ATR stop for {atr_extension_weeks} week(s) after the reversal close.'
        ),
        '',
        f'Trades/stacks: {stats["trades"]}  ·  Units entered: {stats["units"]}  ·  Win rate: {stats["win_rate"]:.1f}%  ·  Profit factor: {stats["pf"]:.2f}',
        f'Net: {stats["net_points"]:+.2f} pts (${stats["net_usd"]:+,.0f})',
        f'Closed-trade max DD: {stats["closed_dd_points"]:+.2f} pts (${stats["closed_dd_points"] * point_value:+,.0f})',
        f'Mark-to-market max DD: {stats["mtm_dd_points"]:+.2f} pts (${stats["mtm_dd_points"] * point_value:+,.0f})',
        f'Worst stack MAE: ${stats["worst_mae_usd"]:+,.0f}  ·  Avg stack MAE: ${stats["avg_mae_usd"]:+,.0f}',
        '',
        '## Year Charts',
        '',
        '| Year | Active Stacks | Exit Pts | Exit $ | Chart |',
        '|---:|---:|---:|---:|---|',
    ]
    for row in chart_rows:
        lines.append(
            f'| {row["year"]} | {row["trades_active"]} | {row["exit_points"]:+.2f} | ${row["exit_usd"]:+,.0f} | [{row["year"]}.png]({row["chart"]}) |'
        )
    lines.append('')
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def run(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]
    daily = daily.sort_values('date').reset_index(drop=True)

    add_prices = load_1550_prices(args.source_1m, args.market) if args.source_1m else {}
    position_size_schedule = parse_size_schedule(args.position_size_schedule)
    if args.signal_timeframe == 'weekly':
        trades, equity, metadata = simulate_weekly_primary(
            daily,
            add_prices,
            args.point_value,
            args.atr_length,
            args.atr_multiplier,
            args.sides,
            args.max_contracts,
            args.initial_contracts,
            position_size_schedule,
            args.add_interval_weeks,
            args.long_entry_price_guard,
            args.yearly_orb_filter,
        )
    else:
        trades, equity, metadata = simulate(
            daily,
            add_prices,
            args.point_value,
            args.atr_length,
            args.atr_multiplier,
            args.sides,
            args.max_contracts,
            args.initial_contracts,
            position_size_schedule,
            args.add_interval_weeks,
            args.long_weekly_filter,
            args.weekly_atr_length if args.weekly_atr_length is not None else args.atr_length,
            args.weekly_atr_multiplier if args.weekly_atr_multiplier is not None else args.atr_multiplier,
            args.long_prior_bearish_guard,
            args.long_entry_price_guard,
            args.yearly_orb_filter,
        )
    trades_df = pd.DataFrame(trade_rows(trades, args.point_value))
    units_df = pd.DataFrame(unit_rows(trades, args.point_value))

    args.out.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(args.out / 'trades.csv', index=False)
    units_df.to_csv(args.out / 'units.csv', index=False)
    equity.to_csv(args.out / 'equity.csv', index=False)

    chart_rows: list[dict] = []
    for year in sorted(daily['date'].dt.year.unique()):
        chart_rows.append(
            draw_year_chart(
                int(year),
                daily,
                trades,
                args.out / str(int(year)) / f'{int(year)}.png',
                args.market.upper(),
                args.point_value,
                args.atr_length,
                args.atr_multiplier,
                args.plot_weekly_atr,
                args.weekly_atr_length if args.weekly_atr_length is not None else args.atr_length,
                args.weekly_atr_multiplier if args.weekly_atr_multiplier is not None else args.atr_multiplier,
                args.atr_extension_weeks,
            )
        )
    write_report(
        args.out,
        args.market.upper(),
        args.point_value,
        trades_df,
        units_df,
        equity,
        chart_rows,
        args.atr_length,
        args.atr_multiplier,
        args.sides,
        args.max_contracts,
        args.initial_contracts,
        args.add_interval_weeks,
        metadata,
        args.plot_weekly_atr,
        args.atr_extension_weeks,
    )
    print(f'Wrote {args.out / "README.md"}')
    print(f'Wrote {len(chart_rows)} yearly charts under {args.out}')
    return trades_df, units_df, equity


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--source-1m', type=Path, default=None)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument('--atr-length', type=int, default=14)
    ap.add_argument('--atr-multiplier', type=float, default=3.0)
    ap.add_argument('--signal-timeframe', choices=['daily', 'weekly'], default='daily')
    ap.add_argument('--sides', choices=['long', 'short', 'both'], default='long')
    ap.add_argument('--max-contracts', type=int, default=999)
    ap.add_argument('--initial-contracts', type=int, default=1)
    ap.add_argument(
        '--position-size-schedule',
        type=str,
        default='',
        help='Optional comma-separated scale-event sizes. Example: 1,1,2,2,2 starts with 1, adds 1, then 2/2/2, then repeats 1 until max contracts.',
    )
    ap.add_argument('--add-interval-weeks', type=int, default=1)
    ap.add_argument(
        '--long-weekly-filter',
        choices=['none', 'not-bearish', 'flat-when-bearish'],
        default='none',
        help='not-bearish skips long flips/adds while the last completed weekly Supertrend is bearish; flat-when-bearish also exits longs at the next open when the completed weekly Supertrend is bearish.',
    )
    ap.add_argument('--weekly-atr-length', type=int, default=None)
    ap.add_argument('--weekly-atr-multiplier', type=float, default=None)
    ap.add_argument('--plot-weekly-atr', action='store_true')
    ap.add_argument(
        '--atr-extension-weeks',
        type=int,
        default=3,
        help='Visual only: after an ATR stop is broken by an opposite trend close, continue drawing the broken stop level for this many weeks.',
    )
    ap.add_argument(
        '--long-prior-bearish-guard',
        choices=['none', 'exit-reclaim'],
        default='none',
        help='For longs, remember the last bearish Supertrend stop on a bullish flip; exit next open after a close back below it, then allow biweekly Friday reentry only after 15:50 price reclaims it while daily trend remains bullish.',
    )
    ap.add_argument(
        '--long-entry-price-guard',
        choices=['none', 'exit-reclaim'],
        default='none',
        help='For longs, use the first unit entry price as a close-based guard; exit next open after a close below it, then re-enter next open after a close back above it while daily/weekly trend allow longs.',
    )
    ap.add_argument(
        '--yearly-orb-filter',
        choices=['none', 'long-breakout'],
        default='none',
        help='When set to long-breakout, new long stacks/restarts are allowed only after the Jan-Mar yearly ORB has closed out to the upside. Scale adds and exits are unchanged.',
    )
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
