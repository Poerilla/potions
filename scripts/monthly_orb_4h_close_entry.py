#!/usr/bin/env python3
"""Monthly ORB variants using causal 4-hour breakout-close entries and swing stops.

This is a sidecar study for the daily monthly ORB restricted candidates.  The
opening range remains the first 3 trading sessions of each month from the
existing daily CSV.  After that range is fixed, this script uses front-month
MNQ 1-minute data, resampled to 4-hour candles, and enters only after a 4-hour
candle closes outside the monthly opening range.

Entry is modeled at the 4-hour breakout candle close.  The old restricted
daily-close-back-inside exit is removed.  Stops are set at the most recent
confirmed 4-hour swing low for longs / swing high for shorts.  If that swing is
beyond the opposing monthly OR boundary, the stop is pulled to the monthly OR
midpoint.  Max two monthly attempts and one live trade at a time remain.
"""
from __future__ import annotations

import argparse
import math
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import databento as db
import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pytz


ROOT = Path(__file__).resolve().parents[1]
MNQ_ROOT = ROOT / 'mnq'
CASE_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb'
DAILY = MNQ_ROOT / 'mnq_daily.csv'
RAW_1M = MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
FOUR_H_CACHE = MNQ_ROOT / 'data' / 'mnq_front_month_4h_from_1m.csv'
NY = pytz.timezone('America/New_York')
MAX_TRADES_PER_PERIOD = 2


@dataclass
class SingleTrade:
    period: str
    direction: str
    entry: float
    target: float
    stop: float
    breakout_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    mae_pts: float
    mfe_pts: float

    @property
    def pl(self) -> float:
        return self.exit_price - self.entry if self.direction == 'Long' else self.entry - self.exit_price

    @property
    def result(self) -> str:
        if self.pl > 0:
            return 'Win'
        if self.pl < 0:
            return 'Loss'
        return 'Scratch'


@dataclass
class UnitExit:
    unit: int
    time: pd.Timestamp
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
    breakout_time: pd.Timestamp
    entry_time: pd.Timestamp
    exits: list[UnitExit] = field(default_factory=list)
    be_active: bool = False
    mae_price_pts: float = 0.0
    mae_position_pts: float = 0.0
    mfe_price_pts: float = 0.0

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [u for u in (1, 2, 3) if u not in closed]

    @property
    def net_points(self) -> float:
        return sum(ex.pl for ex in self.exits)

    @property
    def result(self) -> str:
        if self.net_points > 0:
            return 'Win'
        if self.net_points < 0:
            return 'Loss'
        return 'Scratch'

    @property
    def final_reason(self) -> str:
        reasons: list[str] = []
        for ex in sorted(self.exits, key=lambda x: (x.time, x.unit)):
            if ex.reason not in reasons:
                reasons.append(ex.reason)
        return '+'.join(reasons) if reasons else 'Open'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def load_1m_source(path: Path) -> pd.DataFrame:
    if path.suffix == '.csv':
        df = pd.read_csv(
            path,
            usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'],
            parse_dates=['ts_event'],
        )
    else:
        df = db.DBNStore.from_file(str(path)).to_df().reset_index()
    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY)
    return df[['ts_event', 'symbol', 'open', 'high', 'low', 'close', 'volume']]


def load_front_month_1m(path: Path, product: str) -> pd.DataFrame:
    print(f'Loading {product} 1m source: {path}')
    df = load_1m_source(path)
    df = df[~df['symbol'].astype(str).str.contains('-', na=False)]
    df = df[df['symbol'].astype(str).str.startswith(product.upper())].copy()
    if df.empty:
        raise RuntimeError(f'No {product} rows found in {path}')
    df['date'] = df['ts_event'].dt.date
    front = (
        df.groupby(['date', 'symbol'])['volume']
        .sum()
        .groupby(level='date')
        .idxmax()
        .apply(lambda item: item[1])
        .to_dict()
    )
    df = df[df['symbol'].eq(df['date'].map(front))].copy()
    df = df.set_index('ts_event').sort_index()
    return df


def resample_4h(df1: pd.DataFrame) -> pd.DataFrame:
    bars = (
        df1.resample('4h', label='left', closed='left', origin='start_day')
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
    bars['time'] = bars.index
    bars['date'] = bars.index.date
    return bars.reset_index(drop=True)


def load_cached_4h(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars['time'] = pd.to_datetime(bars['time'], utc=True).dt.tz_convert(NY)
    bars['date'] = bars['time'].dt.date
    return bars.sort_values('time').reset_index(drop=True)


def write_cached_4h(bars: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = bars.copy()
    out.to_csv(path, index=False)


def load_or_build_4h(raw_1m: Path, product: str, cache: Path, rebuild_cache: bool) -> pd.DataFrame:
    if cache.exists() and not rebuild_cache:
        print(f'Loading cached 4h bars: {cache}')
        return load_cached_4h(cache)
    raw = load_front_month_1m(raw_1m, product)
    bars4h = resample_4h(raw)
    write_cached_4h(bars4h, cache)
    print(f'Wrote cached 4h bars: {cache} ({len(bars4h):,} rows)')
    return bars4h


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def add_confirmed_swings(bars: pd.DataFrame) -> pd.DataFrame:
    """Add most recent causal 4h swing levels.

    A swing at bar i-1 becomes known only when bar i has closed.  The current
    breakout bar can therefore use a pivot from the prior bar, never itself.
    """
    out = bars.copy()
    recent_low = math.nan
    recent_high = math.nan
    lows: list[float] = []
    highs: list[float] = []
    recent_lows: list[float] = []
    recent_highs: list[float] = []
    swing_low_flags: list[bool] = []
    swing_high_flags: list[bool] = []
    for idx, row in out.iterrows():
        lows.append(float(row['low']))
        highs.append(float(row['high']))
        confirmed_low = False
        confirmed_high = False
        if idx >= 2:
            mid = idx - 1
            if lows[mid] < lows[mid - 1] and lows[mid] <= lows[idx]:
                recent_low = lows[mid]
                confirmed_low = True
            if highs[mid] > highs[mid - 1] and highs[mid] >= highs[idx]:
                recent_high = highs[mid]
                confirmed_high = True
        recent_lows.append(recent_low)
        recent_highs.append(recent_high)
        swing_low_flags.append(confirmed_low)
        swing_high_flags.append(confirmed_high)
    out['recent_swing_low'] = recent_lows
    out['recent_swing_high'] = recent_highs
    out['confirmed_swing_low_here'] = swing_low_flags
    out['confirmed_swing_high_here'] = swing_high_flags
    return out


def unit_pl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def update_single_excursion(direction: str, entry: float, high: float, low: float, mae: float, mfe: float) -> tuple[float, float]:
    if direction == 'Long':
        return max(mae, max(0.0, entry - low)), max(mfe, max(0.0, high - entry))
    return max(mae, max(0.0, high - entry)), max(mfe, max(0.0, entry - low))


def stop_from_recent_swing(row: pd.Series, direction: str, rh: float, rl: float) -> tuple[float, str]:
    midpoint = (rh + rl) / 2.0
    if direction == 'Long':
        swing = row.get('recent_swing_low')
        if pd.isna(swing):
            return midpoint, 'OR-midpoint-no-swing'
        swing = float(swing)
        if swing < rl:
            return midpoint, 'OR-midpoint-swing-beyond-opposite-boundary'
        return swing, 'recent-4h-swing-low'
    swing = row.get('recent_swing_high')
    if pd.isna(swing):
        return midpoint, 'OR-midpoint-no-swing'
    swing = float(swing)
    if swing > rh:
        return midpoint, 'OR-midpoint-swing-beyond-opposite-boundary'
    return swing, 'recent-4h-swing-high'


def maybe_open_trade(period: str, row: pd.Series, rh: float, rl: float, rv: float) -> tuple[str, float, float, float, str] | None:
    c = float(row['close'])
    if c > rh:
        target = rh + rv
        if c >= target:
            return None
        stop, source = stop_from_recent_swing(row, 'Long', rh, rl)
        if stop >= c:
            return None
        return ('Long', c, target, stop, source)
    if c < rl:
        target = rl - rv
        if c <= target:
            return None
        stop, source = stop_from_recent_swing(row, 'Short', rh, rl)
        if stop <= c:
            return None
        return ('Short', c, target, stop, source)
    return None


def daily_close_inside(row: pd.Series, rh: float, rl: float) -> bool:
    if not bool(row.get('is_daily_close_bar', False)):
        return False
    daily_close = row.get('daily_close')
    if pd.isna(daily_close):
        return False
    return rl <= float(daily_close) <= rh


def simulate_single(period: str, rh: float, rl: float, rv: float, bars: pd.DataFrame) -> list[SingleTrade]:
    trades: list[SingleTrade] = []
    active: dict | None = None
    needs_rearm = False
    for _, row in bars.iterrows():
        t = pd.Timestamp(row['time'])
        h, l, c = float(row['high']), float(row['low']), float(row['close'])

        if active is None and needs_rearm:
            if daily_close_inside(row, rh, rl):
                needs_rearm = False
            continue

        if active is not None:
            active['mae'], active['mfe'] = update_single_excursion(
                active['direction'], active['entry'], h, l, active['mae'], active['mfe']
            )
            direction = active['direction']
            exit_price = None
            exit_reason = ''
            if direction == 'Long':
                if l <= active['stop']:
                    exit_price, exit_reason = active['stop'], 'Stop'
                elif h >= active['target']:
                    exit_price, exit_reason = active['target'], 'Target'
            else:
                if h >= active['stop']:
                    exit_price, exit_reason = active['stop'], 'Stop'
                elif l <= active['target']:
                    exit_price, exit_reason = active['target'], 'Target'
            if exit_price is not None:
                trades.append(
                    SingleTrade(
                        period=period,
                        direction=direction,
                        entry=active['entry'],
                        target=active['target'],
                        stop=active['stop'],
                        breakout_time=active['breakout_time'],
                        entry_time=active['entry_time'],
                        exit_time=t,
                        exit_price=float(exit_price),
                        exit_reason=exit_reason,
                        mae_pts=active['mae'],
                        mfe_pts=active['mfe'],
                    )
                )
                active = None
                needs_rearm = True
                if len(trades) >= MAX_TRADES_PER_PERIOD:
                    break
            continue

        if len(trades) >= MAX_TRADES_PER_PERIOD:
            break
        setup = maybe_open_trade(period, row, rh, rl, rv)
        if setup is None:
            continue
        direction, entry, target, stop, stop_source = setup
        active = {
            'direction': direction,
            'entry': float(entry),
            'target': float(target),
            'stop': float(stop),
            'stop_source': stop_source,
            'breakout_time': t,
            'entry_time': t,
            'mae': 0.0,
            'mfe': 0.0,
        }

    if active is not None and not bars.empty:
        last = bars.iloc[-1]
        exit_price = float(last['close'])
        trades.append(
            SingleTrade(
                period=period,
                direction=active['direction'],
                entry=active['entry'],
                target=active['target'],
                stop=active['stop'],
                breakout_time=active['breakout_time'],
                entry_time=active['entry_time'],
                exit_time=pd.Timestamp(last['time']),
                exit_price=exit_price,
                exit_reason='Period-Close',
                mae_pts=active['mae'],
                mfe_pts=active['mfe'],
            )
        )
    return trades


def add_exit(trade: ScaleTrade, unit: int, time: pd.Timestamp, price: float, reason: str) -> None:
    if unit not in trade.open_units:
        return
    trade.exits.append(UnitExit(unit, time, price, reason, unit_pl(trade.direction, trade.entry, price)))


def close_scale_units(trade: ScaleTrade, time: pd.Timestamp, price: float, reason: str) -> None:
    for unit in list(trade.open_units):
        add_exit(trade, unit, time, price, reason)


def update_scale_excursion(trade: ScaleTrade, high: float, low: float) -> None:
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


def start_scale_trade(period: str, row: pd.Series, direction: str, entry: float, target: float, stop: float) -> ScaleTrade:
    tp25 = entry + (target - entry) * 0.25 if direction == 'Long' else entry - (entry - target) * 0.25
    t = pd.Timestamp(row['time'])
    return ScaleTrade(
        period=period,
        direction=direction,
        entry=float(entry),
        target=float(target),
        tp25=float(tp25),
        initial_stop=float(stop),
        breakout_time=t,
        entry_time=t,
    )


def process_scale_trade(trade: ScaleTrade, row: pd.Series, rh: float, rl: float) -> bool:
    t = pd.Timestamp(row['time'])
    h, l, c = float(row['high']), float(row['low']), float(row['close'])
    update_scale_excursion(trade, h, l)
    stop_price = trade.entry if trade.be_active else trade.initial_stop
    stop_reason = 'BE-Stop' if trade.be_active else 'Boundary-Stop'

    if trade.direction == 'Long':
        if l <= stop_price:
            close_scale_units(trade, t, stop_price, stop_reason)
            return True
        if 1 in trade.open_units and h >= trade.tp25:
            add_exit(trade, 1, t, trade.tp25, 'TP25')
        if 2 in trade.open_units and h >= trade.target:
            add_exit(trade, 2, t, trade.target, 'TP')
            trade.be_active = True
    else:
        if h >= stop_price:
            close_scale_units(trade, t, stop_price, stop_reason)
            return True
        if 1 in trade.open_units and l <= trade.tp25:
            add_exit(trade, 1, t, trade.tp25, 'TP25')
        if 2 in trade.open_units and l <= trade.target:
            add_exit(trade, 2, t, trade.target, 'TP')
            trade.be_active = True

    return not trade.open_units


def simulate_scaleout3(period: str, rh: float, rl: float, rv: float, bars: pd.DataFrame) -> list[ScaleTrade]:
    trades: list[ScaleTrade] = []
    trade: ScaleTrade | None = None
    needs_rearm = False
    for _, row in bars.iterrows():
        if trade is None and needs_rearm:
            if daily_close_inside(row, rh, rl):
                needs_rearm = False
            continue

        if trade is not None:
            if process_scale_trade(trade, row, rh, rl):
                trades.append(trade)
                trade = None
                needs_rearm = True
                if len(trades) >= MAX_TRADES_PER_PERIOD:
                    break
            continue

        if len(trades) >= MAX_TRADES_PER_PERIOD:
            break
        setup = maybe_open_trade(period, row, rh, rl, rv)
        if setup is None:
            continue
        direction, entry, target, stop, _stop_source = setup
        trade = start_scale_trade(period, row, direction, entry, target, stop)

    if trade is not None and not bars.empty:
        last = bars.iloc[-1]
        close_scale_units(trade, pd.Timestamp(last['time']), float(last['close']), 'Period-Close')
        trades.append(trade)
    return trades


def run_variants(daily: pd.DataFrame, bars4h: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    single_rows: list[dict] = []
    scale_rows: list[dict] = []
    chart_bars: dict[str, pd.DataFrame] = {}
    single_cum = 0.0
    scale_cum = 0.0

    for period, month_daily in period_groups(daily):
        range_bars = month_daily.iloc[:3]
        trade_start = month_daily.iloc[3]['date']
        period_dates = set(month_daily['date'])
        rh = float(range_bars['high'].max())
        rl = float(range_bars['low'].min())
        rv = rh - rl
        symbol = str(range_bars.iloc[0]['symbol'])
        month4h = bars4h[bars4h['date'].isin(period_dates)].copy().reset_index(drop=True)
        month4h = add_confirmed_swings(month4h)
        close_by_date = {pd.Timestamp(row['date']).date(): float(row['close']) for _, row in month_daily.iterrows()}
        month4h['daily_close'] = month4h['date'].map(close_by_date)
        month4h['is_daily_close_bar'] = month4h.groupby('date').cumcount() == month4h.groupby('date')['date'].transform('size') - 1
        trade4h = month4h[month4h['date'] >= trade_start].copy().reset_index(drop=True)
        chart_bars[period] = month4h

        if rv <= 0 or trade4h.empty:
            single_rows.append(noop_single_row(period, rh, rl, max(rv, 0.0), symbol, len(trade4h), 'No-Op'))
            scale_rows.append(noop_scale_row(period, rh, rl, max(rv, 0.0), symbol, len(trade4h), 'No-Op'))
            continue

        singles = simulate_single(period, rh, rl, rv, trade4h)
        if not singles:
            single_rows.append(noop_single_row(period, rh, rl, rv, symbol, len(trade4h), 'No-Op'))
        for t in singles:
            single_cum += t.pl
            single_rows.append(single_row(t, rh, rl, rv, symbol, len(trade4h), single_cum))

        scales = simulate_scaleout3(period, rh, rl, rv, trade4h)
        if not scales:
            scale_rows.append(noop_scale_row(period, rh, rl, rv, symbol, len(trade4h), 'No-Op'))
        for t in scales:
            scale_cum += t.net_points
            scale_rows.append(scale_row(t, rh, rl, rv, symbol, len(trade4h), scale_cum))

    return pd.DataFrame(single_rows), pd.DataFrame(scale_rows), chart_bars


def noop_single_row(period: str, rh: float, rl: float, rv: float, symbol: str, trade_bars: int, result: str) -> dict:
    return {
        'Period': period,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'Trade_Direction': 'No-Op',
        'Entry_Price': None,
        'Exit_Price': None,
        'Trade_PL': 0.0,
        'Drawdown_Pct': 0.0,
        'Result': result,
        'Symbol': symbol,
        'Range_Days': 3,
        'Trade_Days': trade_bars,
        'Entry_Date': None,
        'Exit_Date': None,
        'Entry_Time': None,
        'Exit_Time': None,
        'Exit_Reason': result,
        'Entry_Mode': '4h_close',
        'Cumulative_PL': 0.0,
    }


def single_row(t: SingleTrade, rh: float, rl: float, rv: float, symbol: str, trade_bars: int, cumulative: float) -> dict:
    return {
        'Period': t.period,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'Trade_Direction': t.direction,
        'Entry_Price': t.entry,
        'Exit_Price': t.exit_price,
        'Trade_PL': round(t.pl, 6),
        'Drawdown_Pct': round((t.mae_pts / rv) * 100, 2) if rv else 0.0,
        'Result': t.result,
        'Symbol': symbol,
        'Range_Days': 3,
        'Trade_Days': trade_bars,
        'Entry_Date': t.entry_time.date().isoformat(),
        'Exit_Date': t.exit_time.date().isoformat(),
        'Entry_Time': t.entry_time.isoformat(),
        'Exit_Time': t.exit_time.isoformat(),
        'Exit_Reason': t.exit_reason,
        'Entry_Mode': '4h_close',
        'Breakout_Time': t.breakout_time.isoformat(),
        'Target_Price': t.target,
        'Stop_Price': t.stop,
        'MAE_Price_Pts': round(t.mae_pts, 6),
        'MFE_Price_Pts': round(t.mfe_pts, 6),
        'Cumulative_PL': round(cumulative, 6),
    }


def noop_scale_row(period: str, rh: float, rl: float, rv: float, symbol: str, trade_bars: int, result: str) -> dict:
    row = {
        'Period': period,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'Trade_Direction': 'No-Op',
        'Units': 0,
        'Entry_Date': None,
        'Entry_Time': None,
        'Entry_Price': None,
        'Entry_Mode': '4h_close',
        'Stop_Swing_Scope': 'recent-4h-swing-with-midpoint-fallback',
        'Breakout_Date': None,
        'Breakout_Time': None,
        'Breakout_Close': None,
        'Initial_Stop_Price': None,
        'Stop_Source_Date': None,
        'Stop_Source_Price': None,
        'TP25_Price': None,
        'TP_Price': None,
        'Trade_PL': 0.0,
        'MAE_Price_Pts': 0.0,
        'MAE_Position_Pts': 0.0,
        'MFE_Price_Pts': 0.0,
        'Result': result,
        'Final_Reason': result,
        'Symbol': symbol,
        'Range_Days': 3,
        'Trade_Days': trade_bars,
        'Cumulative_PL': 0.0,
    }
    for unit in (1, 2, 3):
        row[f'Unit{unit}_Exit_Price'] = None
        row[f'Unit{unit}_Exit_Date'] = None
        row[f'Unit{unit}_Exit_Time'] = None
        row[f'Unit{unit}_Exit_Reason'] = None
    return row


def scale_row(t: ScaleTrade, rh: float, rl: float, rv: float, symbol: str, trade_bars: int, cumulative: float) -> dict:
    exits = {ex.unit: ex for ex in t.exits}
    row = {
        'Period': t.period,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'Trade_Direction': t.direction,
        'Units': 3,
        'Entry_Date': t.entry_time.date().isoformat(),
        'Entry_Time': t.entry_time.isoformat(),
        'Entry_Price': t.entry,
        'Entry_Mode': '4h_close',
        'Stop_Swing_Scope': 'recent-4h-swing-with-midpoint-fallback',
        'Breakout_Date': t.breakout_time.date().isoformat(),
        'Breakout_Time': t.breakout_time.isoformat(),
        'Breakout_Close': t.entry,
        'Initial_Stop_Price': t.initial_stop,
        'Stop_Source_Date': t.entry_time.date().isoformat(),
        'Stop_Source_Price': t.initial_stop,
        'TP25_Price': t.tp25,
        'TP_Price': t.target,
        'Trade_PL': round(t.net_points, 6),
        'MAE_Price_Pts': round(t.mae_price_pts, 6),
        'MAE_Position_Pts': round(t.mae_position_pts, 6),
        'MFE_Price_Pts': round(t.mfe_price_pts, 6),
        'Result': t.result,
        'Final_Reason': t.final_reason,
        'Symbol': symbol,
        'Range_Days': 3,
        'Trade_Days': trade_bars,
        'Cumulative_PL': round(cumulative, 6),
    }
    for unit in (1, 2, 3):
        ex = exits.get(unit)
        row[f'Unit{unit}_Exit_Price'] = ex.price if ex else None
        row[f'Unit{unit}_Exit_Date'] = ex.time.date().isoformat() if ex else None
        row[f'Unit{unit}_Exit_Time'] = ex.time.isoformat() if ex else None
        row[f'Unit{unit}_Exit_Reason'] = ex.reason if ex else None
    return row


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


def stats(df: pd.DataFrame, point_value: float) -> dict:
    t = df[df['Trade_Direction'].astype(str) != 'No-Op'].copy()
    if t.empty:
        return {'trades': 0, 'net_pts': 0.0, 'net_usd': 0.0, 'dd_pts': 0.0, 'dd_usd': 0.0, 'win_rate': 0.0, 'pf': 0.0}
    pnl = pd.to_numeric(t['Trade_PL'], errors='coerce').fillna(0.0)
    dd = max_drawdown(pnl)
    mae_series = pd.to_numeric(t.get('MAE_Price_Pts', pd.Series(index=t.index, dtype=float)), errors='coerce')
    if mae_series.isna().all() and {'Drawdown_Pct', 'Range'}.issubset(t.columns):
        mae_series = (
            pd.to_numeric(t['Drawdown_Pct'], errors='coerce').fillna(0.0)
            / 100.0
            * pd.to_numeric(t['Range'], errors='coerce').fillna(0.0)
        )
    reason_text = pd.Series('', index=t.index, dtype=str)
    for col in ('Exit_Reason', 'Final_Reason'):
        if col in t.columns:
            reason_text = reason_text.str.cat(t[col].astype(str), sep=' ')
    return {
        'trades': int(len(t)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_pts': float(dd),
        'dd_usd': float(dd * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'range_close': int(reason_text.str.contains('Range-Close|Close_Back_Inside_Range', na=False).sum()),
        'avg_mae_pts': float(mae_series.mean()) if not mae_series.empty else 0.0,
        'max_mae_pts': float(mae_series.max()) if not mae_series.empty else 0.0,
    }


def draw_candles(ax, bars: pd.DataFrame) -> None:
    if bars.empty:
        return
    xnums = mdates.date2num(pd.to_datetime(bars['time']).dt.tz_convert(None).dt.to_pydatetime())
    width = 0.12
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.8, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.95,
                zorder=4,
            )
        )


def annotate_level(ax, xnums, price: float, label: str, color: str, ls: str = '-') -> None:
    if not len(xnums):
        return
    ax.hlines(price, xnums[0], xnums[-1], colors=color, linestyles=ls, linewidth=1.1, alpha=0.95)
    ax.text(xnums[-1], price, f' {label}', color=color, fontsize=8, va='center', ha='left')


def draw_single_chart(period: str, bars: pd.DataFrame, trades: pd.DataFrame, out_path: Path) -> None:
    draw_chart(period, bars, trades, out_path, scaleout=False)


def draw_scale_chart(period: str, bars: pd.DataFrame, trades: pd.DataFrame, out_path: Path) -> None:
    draw_chart(period, bars, trades, out_path, scaleout=True)


def draw_chart(period: str, bars: pd.DataFrame, trades: pd.DataFrame, out_path: Path, scaleout: bool) -> None:
    if bars.empty:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rh = float(trades.iloc[0]['Range_High'])
    rl = float(trades.iloc[0]['Range_Low'])
    rv = rh - rl
    fig = plt.figure(figsize=(16, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars)
    times = pd.to_datetime(bars['time'])
    xnums = mdates.date2num(times.dt.tz_convert(None).dt.to_pydatetime())
    annotate_level(ax, xnums, rh, 'OR High', '#64B5F6')
    annotate_level(ax, xnums, rl, 'OR Low', '#64B5F6')
    ax.axhspan(rl, rh, color='#263D5A', alpha=0.22, zorder=1)
    range_dates = sorted(set(bars['date']))[:3]
    if range_dates:
        shade = bars[bars['date'].isin(range_dates)]
        if not shade.empty:
            sx = mdates.date2num(pd.to_datetime(shade['time']).dt.tz_convert(None).dt.to_pydatetime())
            ax.axvspan(sx[0], sx[-1], color='#FFD54F', alpha=0.08, zorder=0)

    real_trades = trades[trades['Trade_Direction'].astype(str) != 'No-Op'].copy()
    for idx, row in real_trades.iterrows():
        direction = str(row['Trade_Direction'])
        entry_t = pd.to_datetime(row['Entry_Time']).tz_convert(NY)
        entry_x = mdates.date2num(entry_t.tz_convert(None).to_pydatetime())
        entry = float(row['Entry_Price'])
        marker = '^' if direction == 'Long' else 'v'
        color = '#00E676' if direction == 'Long' else '#FF8A80'
        ax.scatter(entry_x, entry, s=80, marker=marker, color=color, edgecolor='white', linewidth=0.6, zorder=8)
        ax.text(entry_x, entry, f' #{idx + 1} {direction[0]} entry', color='white', fontsize=8, ha='left', va='bottom')
        if scaleout:
            for unit in (1, 2, 3):
                exit_time = row.get(f'Unit{unit}_Exit_Time')
                exit_px = row.get(f'Unit{unit}_Exit_Price')
                if pd.isna(exit_time) or pd.isna(exit_px):
                    continue
                xt = pd.to_datetime(exit_time).tz_convert(NY)
                xx = mdates.date2num(xt.tz_convert(None).to_pydatetime())
                ax.scatter(xx, float(exit_px), s=55, marker='x', color='#FFCA28', zorder=9)
                ax.text(xx, float(exit_px), f' u{unit} {row.get(f"Unit{unit}_Exit_Reason")}', color='#FFCA28', fontsize=7)
            annotate_level(ax, xnums, float(row['TP_Price']), f'#{idx + 1} TP', '#81C784', '--')
            annotate_level(ax, xnums, float(row['TP25_Price']), f'#{idx + 1} TP25', '#AED581', ':')
            annotate_level(ax, xnums, float(row['Initial_Stop_Price']), f'#{idx + 1} Stop', '#EF5350', '--')
        else:
            exit_t = pd.to_datetime(row['Exit_Time']).tz_convert(NY)
            exit_x = mdates.date2num(exit_t.tz_convert(None).to_pydatetime())
            exit_px = float(row['Exit_Price'])
            ax.scatter(exit_x, exit_px, s=70, marker='x', color='#FFCA28', zorder=9)
            ax.text(exit_x, exit_px, f' exit {row["Exit_Reason"]}', color='#FFCA28', fontsize=8)
            annotate_level(ax, xnums, float(row['Target_Price']), f'#{idx + 1} Target', '#81C784', '--')
            annotate_level(ax, xnums, float(row['Stop_Price']), f'#{idx + 1} Stop', '#EF5350', '--')

    net = pd.to_numeric(real_trades['Trade_PL'], errors='coerce').sum() if not real_trades.empty else 0.0
    title_kind = '4h swing-stop scaleout3' if scaleout else '4h swing-stop'
    ax.set_title(f'MNQ monthly ORB {title_kind} | {period} | net {net:,.1f} pts', color='white', fontsize=13)
    ax.grid(True, color='white', alpha=0.08)
    ax.tick_params(colors='white')
    ax.yaxis.set_tick_params(labelcolor='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def write_indexes(root: Path, title: str) -> None:
    year_dirs = sorted([p for p in root.iterdir() if p.is_dir() and p.name.isdigit()])
    root_lines = [f'# {title}', '', '| Year | Charts |', '|---|---:|']
    for yd in year_dirs:
        pngs = sorted(yd.glob('*.png'))
        root_lines.append(f'| [{yd.name}]({yd.name}/INDEX.md) | {len(pngs)} |')
        lines = [f'# {title} {yd.name}', '']
        for p in pngs:
            lines.append(f'- [{p.name}]({p.name})')
        (yd / 'INDEX.md').write_text('\n'.join(lines) + '\n')
    (root / 'INDEX.md').write_text('\n'.join(root_lines) + '\n')


def build_charts(single: pd.DataFrame, scale: pd.DataFrame, chart_bars: dict[str, pd.DataFrame], out_root: Path) -> None:
    single_root = out_root / 'baseline_4h_swing_stop'
    scale_root = out_root / 'baseline_scaleout3_4h_swing_stop'
    for root in (single_root, scale_root):
        root.mkdir(parents=True, exist_ok=True)
    for period, bars in chart_bars.items():
        year = period[:4]
        st = single[single['Period'].eq(period)]
        sc = scale[scale['Period'].eq(period)]
        if not st.empty:
            draw_single_chart(period, bars, st, single_root / year / f'{period}.png')
        if not sc.empty:
            draw_scale_chart(period, bars, sc, scale_root / year / f'{period}.png')
    write_indexes(single_root, 'MNQ monthly ORB 4h swing-stop charts')
    write_indexes(scale_root, 'MNQ monthly ORB scaleout3 4h swing-stop charts')


def fmt_money(v: float) -> str:
    return f'${v:,.0f}'


def fmt_pct(v: float) -> str:
    return f'{v:.1%}'


def write_report(path: Path, single: pd.DataFrame, scale: pd.DataFrame, point_value: float) -> None:
    old_single = pd.read_csv(MNQ_ROOT / 'mnq_monthly_orb_restricted.csv')
    old_scale = pd.read_csv(MNQ_ROOT / 'mnq_monthly_orb_restricted_scaleout3.csv')
    rows = [
        ('Daily restricted boundary entry', stats(old_single, point_value)),
        ('4h swing-stop close entry', stats(single, point_value)),
        ('Daily restricted scaleout3 boundary entry', stats(old_scale, point_value)),
        ('4h swing-stop scaleout3 close entry', stats(scale, point_value)),
    ]
    lines = [
        '# MNQ Monthly ORB 4H Swing-Stop Review',
        '',
        'This sidecar study keeps the first-3-session monthly opening range, max two attempts per month, and measured-move target. The changed assumptions are entry and stop: instead of filling at the opening-range boundary after a daily breakout, the new variants wait for a 4-hour candle to close outside the range and enter at that 4-hour close; instead of using a range-close restriction, they stop at the most recent confirmed 4-hour swing.',
        '',
        'For longs, the stop is the most recent confirmed 4-hour swing low. For shorts, it is the most recent confirmed 4-hour swing high. A swing is only usable after the next 4-hour candle confirms it. If the swing is beyond the opposing opening-range boundary, the stop is pulled to the OR midpoint. There is no close-back-inside exit; trades exit by stop, target, or period close. The engine allows only one open trade at a time and up to two completed attempts per month. After a completed trade, the next attempt must re-arm with a daily close back inside the monthly OR, then a fresh 4-hour close outside.',
        '',
        '| Variant | Trades | Net pts | Net USD | Max closed DD | Win rate | PF | Avg MAE pts | Max MAE pts | Range-close exits |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for name, s in rows:
        lines.append(
            f"| {name} | {s['trades']} | {s['net_pts']:,.1f} | {fmt_money(s['net_usd'])} | "
            f"{fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {s['pf']:.2f} | "
            f"{s.get('avg_mae_pts', 0.0):.1f} | {s.get('max_mae_pts', 0.0):.1f} | {s.get('range_close', 0)} |"
        )
    lines.extend(
        [
            '',
            '## Outputs',
            '',
            '- `mnq/mnq_monthly_orb_4h_swing_stop.csv`',
            '- `mnq/mnq_monthly_orb_scaleout3_4h_swing_stop.csv`',
            '- `mnq/data/mnq_front_month_4h_from_1m.csv`',
            '- `mnq/case_studies/monthly_orb/baseline_4h_swing_stop/`',
            '- `mnq/case_studies/monthly_orb/baseline_scaleout3_4h_swing_stop/`',
            '',
            '## Causality Note',
            '',
            'The 4-hour breakout close and the most recent confirmed swing are knowable only after the candle closes. A live implementation would place the order immediately after that close; actual fill may be a tick or more away from the plotted close. A stricter next-4-hour-open/market-fill stress pass is still useful before live testing.',
            '',
            '## Regeneration',
            '',
            'Normal rerun, using the cached 4-hour front-month bars:',
            '',
            '```bash',
            'python3 potions/scripts/monthly_orb_4h_close_entry.py',
            '```',
            '',
            'Rebuild the 4-hour cache from the 1-minute DBN only when raw data changes:',
            '',
            '```bash',
            'python3 potions/scripts/monthly_orb_4h_close_entry.py --rebuild-4h-cache',
            '```',
        ]
    )
    path.write_text('\n'.join(lines) + '\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY)
    ap.add_argument('--raw-1m', type=Path, default=RAW_1M)
    ap.add_argument('--product', default='MNQ')
    ap.add_argument('--cache-4h', type=Path, default=FOUR_H_CACHE)
    ap.add_argument('--rebuild-4h-cache', action='store_true')
    ap.add_argument('--point-value-usd', type=float, default=2.0)
    ap.add_argument('--single-out', type=Path, default=MNQ_ROOT / 'mnq_monthly_orb_4h_swing_stop.csv')
    ap.add_argument(
        '--scaleout-out',
        type=Path,
        default=MNQ_ROOT / 'mnq_monthly_orb_scaleout3_4h_swing_stop.csv',
    )
    ap.add_argument('--chart-root', type=Path, default=CASE_ROOT)
    ap.add_argument('--no-charts', action='store_true')
    args = ap.parse_args()

    daily = load_daily(args.daily)
    bars4h = load_or_build_4h(args.raw_1m, args.product, args.cache_4h, args.rebuild_4h_cache)
    single, scale, chart_bars = run_variants(daily, bars4h)

    args.single_out.parent.mkdir(parents=True, exist_ok=True)
    args.scaleout_out.parent.mkdir(parents=True, exist_ok=True)
    single.to_csv(args.single_out, index=False)
    scale.to_csv(args.scaleout_out, index=False)
    print(f'Wrote {args.single_out} ({len(single)} rows)')
    print(f'Wrote {args.scaleout_out} ({len(scale)} rows)')

    for label, df in [('single', single), ('scaleout3', scale)]:
        s = stats(df, args.point_value_usd)
        print(
            f"{label}: trades={s['trades']} net={s['net_pts']:,.1f} pts "
            f"({fmt_money(s['net_usd'])}) dd={s['dd_pts']:,.1f} pts ({fmt_money(s['dd_usd'])}) "
            f"wr={fmt_pct(s['win_rate'])} pf={s['pf']:.2f}"
        )

    if not args.no_charts:
        build_charts(single, scale, chart_bars, args.chart_root)
        print(f'Wrote charts under {args.chart_root}')

    write_report(args.chart_root / 'MONTHLY_ORB_4H_SWING_STOP.md', single, scale, args.point_value_usd)
    print(f"Wrote {args.chart_root / 'MONTHLY_ORB_4H_SWING_STOP.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
