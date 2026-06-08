#!/usr/bin/env python3
"""Causal 4-hour simulation for the monthly ORB restricted stop/limit cycle.

This is a live-style sidecar for ``monthly_orb_restricted_stop_limit_cycle.py``.
It keeps the long-only state machine from the daily research script, but uses
front-month 1-minute data resampled to 4-hour bars for order touches.

Important causality rules:
- The monthly opening range is the first three daily rows of the month.
- Initial stop orders become live only after that range is fixed.
- Orders created by a confirmed close or TP1 event become live on the next
  4-hour bar, never on the confirmation bar.
- Daily-close exits can be filled either at that close, for research parity, or
  at the next 4-hour bar open, for live-style handling.

The 4-hour OHLC path still has ambiguity. To avoid giving same-bar target credit
after a fresh fill, new packages do not process targets until the next 4-hour
bar. Daily-close invalidations on the fill bar are still honored because that
close is the confirming information that disqualifies the package.
"""
from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pytz


ROOT = Path(__file__).resolve().parents[1]
NY = pytz.timezone('America/New_York')
BACK_IN_RANGE_STOP_FRACTION = 0.25

MARKETS = {
    'mnq': {
        'root': ROOT / 'mnq',
        'daily': ROOT / 'mnq' / 'mnq_daily.csv',
        'raw_1m': ROOT / 'mnq' / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
        'cache_4h': ROOT / 'mnq' / 'data' / 'mnq_front_month_4h_from_1m.csv',
        'point_value': 2.0,
        'label': 'MNQ',
        'product': 'MNQ',
    },
    'nq': {
        'root': ROOT / 'nq',
        'daily': ROOT / 'nq' / 'nq_daily.csv',
        'raw_1m': ROOT / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst',
        'cache_4h': ROOT / 'nq' / 'data' / 'nq_front_month_4h_from_1m.csv',
        'point_value': 20.0,
        'label': 'NQ',
        'product': 'NQ',
    },
}


@dataclass
class UnitExit:
    unit: int
    time: pd.Timestamp
    price: float
    reason: str
    pl: float


@dataclass
class Package:
    market: str
    period: str
    entry_kind: str
    order_live_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_bar_idx: int
    entry: float
    range_high: float
    range_low: float
    range_size: float
    tp50: float
    tp1: float
    tp2: float | None
    stop: float | None
    symbol: str
    exit_fill_mode: str
    source_pending: str
    exits: list[UnitExit] = field(default_factory=list)
    tp1_hit: bool = False
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    open_at_end: bool = False
    false_breakout: bool = False
    units: int = 3
    tp50_units: int = 1
    had_4h_close_above_range: bool = False

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [unit for unit in range(1, self.units + 1) if unit not in closed]

    @property
    def net_points(self) -> float:
        return float(sum(ex.pl for ex in self.exits))

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
        for ex in sorted(self.exits, key=lambda item: (item.time, item.unit)):
            if ex.reason not in reasons:
                reasons.append(ex.reason)
        return '+'.join(reasons) if reasons else 'Open'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def load_cached_4h(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars['time'] = pd.to_datetime(bars['time'], utc=True).dt.tz_convert(NY)
    bars['date'] = bars['time'].dt.date
    return bars.sort_values('time').reset_index(drop=True)


def load_1m_source(path: Path) -> pd.DataFrame:
    if path.suffix == '.csv':
        df = pd.read_csv(
            path,
            usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'],
            parse_dates=['ts_event'],
        )
    else:
        import databento as db

        df = db.DBNStore.from_file(str(path)).to_df().reset_index()
    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY)
    return df[['ts_event', 'symbol', 'open', 'high', 'low', 'close', 'volume']]


def load_front_month_1m(path: Path, product: str) -> pd.DataFrame:
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
    return df.set_index('ts_event').sort_index()


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


def load_or_build_4h(market_cfg: dict, rebuild_cache: bool) -> pd.DataFrame:
    cache = market_cfg['cache_4h']
    if cache.exists() and not rebuild_cache:
        print(f'Loading cached 4h bars: {cache}')
        return load_cached_4h(cache)
    raw_1m = market_cfg['raw_1m']
    if not raw_1m.exists():
        raise FileNotFoundError(f'Missing 4h cache and raw 1m source: {raw_1m}')
    print(f'Building 4h cache from {raw_1m}')
    bars = resample_4h(load_front_month_1m(raw_1m, market_cfg['product']))
    cache.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(cache, index=False)
    print(f'Wrote cached 4h bars: {cache} ({len(bars):,} rows)')
    return bars


def period_groups(daily: pd.DataFrame) -> Iterable[tuple[str, pd.DataFrame]]:
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def breakout_close_stop(rh: float, rl: float) -> float:
    return rh - BACK_IN_RANGE_STOP_FRACTION * (rh - rl)


def breakout_close_violation(close_px: float, rh: float, rl: float) -> bool:
    return close_px <= breakout_close_stop(rh, rl)


def is_failed_before_tp1(reason: str) -> bool:
    return reason in {
        'Daily-Close-25pct-Back-In-Range-Before-TP1',
        'Daily-Close-Back-In-Range-Before-TP1',
        'Daily-Close-At-Or-Below-Range-High-Before-TP1',
    }


def unit_pl(entry: float, exit_price: float) -> float:
    return float(exit_price - entry)


def close_unit(pkg: Package, unit: int, time: pd.Timestamp, price: float, reason: str) -> None:
    if unit in pkg.open_units:
        pkg.exits.append(UnitExit(unit, pd.Timestamp(time), float(price), reason, unit_pl(pkg.entry, float(price))))


def close_open(pkg: Package, time: pd.Timestamp, price: float, reason: str) -> None:
    for unit in list(pkg.open_units):
        close_unit(pkg, unit, time, price, reason)


def update_excursion(pkg: Package, high: float, low: float) -> None:
    pkg.mae_pts = max(pkg.mae_pts, max(0.0, pkg.entry - low))
    pkg.mfe_pts = max(pkg.mfe_pts, max(0.0, high - pkg.entry))


def make_package(
    market: str,
    period: str,
    kind: str,
    row: pd.Series,
    bar_idx: int,
    entry: float,
    rh: float,
    rl: float,
    rv: float,
    order_live_time: pd.Timestamp,
    exit_fill_mode: str,
    source_pending: str,
    breakout_tp50_units: int,
) -> Package:
    tp1 = rh + rv
    if kind == 'Bottom-Limit':
        tp50 = rh
        tp2 = None
        stop = rl - 0.25 * rv
        units = 3
        tp50_units = 1
    elif kind == 'Top-Refill':
        tp50 = entry + (tp1 - entry) * 0.5
        tp2 = None
        stop = None
        units = 2
        tp50_units = 1
    else:
        tp50 = entry + (tp1 - entry) * 0.5
        tp2 = entry + 2.0 * (tp1 - entry)
        stop = None
        tp50_units = max(1, int(breakout_tp50_units))
        units = tp50_units + 2
    return Package(
        market=market.upper(),
        period=period,
        entry_kind=kind,
        order_live_time=pd.Timestamp(order_live_time),
        entry_time=pd.Timestamp(row['time']),
        entry_bar_idx=bar_idx,
        entry=float(entry),
        range_high=float(rh),
        range_low=float(rl),
        range_size=float(rv),
        tp50=float(tp50),
        tp1=float(tp1),
        tp2=float(tp2) if tp2 is not None else None,
        stop=float(stop) if stop is not None else None,
        symbol=str(row.get('symbol', '')),
        exit_fill_mode=exit_fill_mode,
        source_pending=source_pending,
        units=units,
        tp50_units=tp50_units,
        had_4h_close_above_range=kind == 'Stop-Breakout' and float(row['close']) > rh,
    )


def maybe_schedule_or_close(
    pkg: Package,
    row: pd.Series,
    reason: str,
    scheduled: dict[int, str],
) -> bool:
    """Return True when the package closed immediately."""
    if pkg.exit_fill_mode == 'close':
        close_open(pkg, pd.Timestamp(row['time']), float(row['close']), reason)
        return True
    scheduled[id(pkg)] = reason
    return False


def same_bar_daily_exit(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> bool:
    if not bool(row.get('is_daily_close_bar', False)):
        return False
    close_px = float(row['close'])
    if pkg.entry_kind == 'Stop-Breakout' and breakout_close_violation(close_px, pkg.range_high, pkg.range_low):
        pkg.false_breakout = True
        return maybe_schedule_or_close(pkg, row, 'False-Breakout-Close-25pct-Inside', scheduled)
    if pkg.entry_kind == 'Bottom-Limit':
        assert pkg.stop is not None
        if close_px <= pkg.stop:
            return maybe_schedule_or_close(pkg, row, 'Bottom-Limit-Daily-Close-SL', scheduled)
    if pkg.entry_kind == 'Top-Refill' and close_px <= pkg.range_high:
        return maybe_schedule_or_close(pkg, row, 'Daily-Close-At-Or-Below-Range-High-Before-TP1', scheduled)
    return False


def process_stop_breakout(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> tuple[bool, bool]:
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    if close_px > pkg.range_high:
        pkg.had_4h_close_above_range = True
    newly_hit_tp1 = False
    tp1_unit = pkg.tp50_units + 1
    runner_unit = pkg.tp50_units + 2

    for unit in range(1, pkg.tp50_units + 1):
        if unit in pkg.open_units and high >= pkg.tp50:
            close_unit(pkg, unit, pd.Timestamp(row['time']), pkg.tp50, 'TP50')
    if not pkg.tp1_hit and high >= pkg.tp1:
        close_unit(pkg, tp1_unit, pd.Timestamp(row['time']), pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True

    if pkg.tp1_hit and runner_unit in pkg.open_units:
        assert pkg.tp2 is not None
        if high >= pkg.tp2:
            close_unit(pkg, runner_unit, pd.Timestamp(row['time']), pkg.tp2, 'TP2')
            return True, newly_hit_tp1
        if bool(row.get('is_daily_close_bar', False)) and breakout_close_violation(close_px, pkg.range_high, pkg.range_low):
            closed = maybe_schedule_or_close(pkg, row, 'Daily-Close-25pct-Back-In-Range-After-TP1', scheduled)
            return closed, newly_hit_tp1
    elif not pkg.tp1_hit and bool(row.get('is_daily_close_bar', False)) and breakout_close_violation(close_px, pkg.range_high, pkg.range_low):
        closed = maybe_schedule_or_close(pkg, row, 'Daily-Close-25pct-Back-In-Range-Before-TP1', scheduled)
        return closed, newly_hit_tp1

    return not pkg.open_units, newly_hit_tp1


def process_top_refill(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> tuple[bool, bool]:
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    newly_hit_tp1 = False

    if 1 in pkg.open_units and high >= pkg.tp50:
        close_unit(pkg, 1, pd.Timestamp(row['time']), pkg.tp50, 'TP50')
    if not pkg.tp1_hit and high >= pkg.tp1:
        close_unit(pkg, 2, pd.Timestamp(row['time']), pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True
        return True, newly_hit_tp1
    if not pkg.tp1_hit and bool(row.get('is_daily_close_bar', False)) and close_px <= pkg.range_high:
        closed = maybe_schedule_or_close(pkg, row, 'Daily-Close-At-Or-Below-Range-High-Before-TP1', scheduled)
        return closed, newly_hit_tp1
    return not pkg.open_units, newly_hit_tp1


def process_bottom_limit(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> tuple[bool, bool]:
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    newly_hit_tp1 = False
    assert pkg.stop is not None

    if 1 in pkg.open_units and high >= pkg.tp50:
        close_unit(pkg, 1, pd.Timestamp(row['time']), pkg.tp50, 'Top-Boundary')
    if high >= pkg.tp1:
        close_unit(pkg, 2, pd.Timestamp(row['time']), pkg.tp1, 'TP1')
        close_unit(pkg, 3, pd.Timestamp(row['time']), pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True
        return True, newly_hit_tp1
    if bool(row.get('is_daily_close_bar', False)) and close_px <= pkg.stop:
        closed = maybe_schedule_or_close(pkg, row, 'Bottom-Limit-Daily-Close-SL', scheduled)
        return closed, newly_hit_tp1
    return not pkg.open_units, newly_hit_tp1


def finalize_package(pkg: Package, row: pd.Series) -> None:
    if pkg.open_units:
        close_open(pkg, pd.Timestamp(row['time']), float(row['close']), 'Period-Close')
        pkg.open_at_end = True


def prepare_month_4h(month_daily: pd.DataFrame, bars4h: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_dates = set(month_daily['date'])
    month4h = bars4h[bars4h['date'].isin(period_dates)].copy().reset_index(drop=True)
    close_by_date = {pd.Timestamp(row['date']).date(): float(row['close']) for _, row in month_daily.iterrows()}
    month4h['daily_close'] = month4h['date'].map(close_by_date)
    month4h['is_daily_close_bar'] = (
        month4h.groupby('date').cumcount() == month4h.groupby('date')['date'].transform('size') - 1
    )
    trade_start = month_daily.iloc[3]['date']
    trade4h = month4h[month4h['date'] >= trade_start].copy().reset_index(drop=True)
    return month4h, trade4h


def live_time_for(trade4h: pd.DataFrame, live_idx: int | float, fallback: pd.Timestamp) -> pd.Timestamp:
    if isinstance(live_idx, float) and not math.isfinite(live_idx):
        return pd.Timestamp(fallback)
    idx = int(live_idx)
    if 0 <= idx < len(trade4h):
        return pd.Timestamp(trade4h.iloc[idx]['time'])
    return pd.Timestamp(fallback)


def package_to_row(pkg: Package) -> dict:
    exits = sorted(pkg.exits, key=lambda ex: (ex.time, ex.unit))
    return {
        'Market': pkg.market,
        'Period': pkg.period,
        'Exit_Fill_Mode': pkg.exit_fill_mode,
        'Entry_Kind': pkg.entry_kind,
        'Order_Live_Time': pkg.order_live_time.isoformat(),
        'Entry_Time': pkg.entry_time.isoformat(),
        'Entry_Price': pkg.entry,
        'Range_High': pkg.range_high,
        'Range_Low': pkg.range_low,
        'Range': pkg.range_size,
        'TP50': pkg.tp50,
        'TP1': pkg.tp1,
        'TP2': pkg.tp2,
        'Stop': pkg.stop,
        'Exit_Time': exits[-1].time.isoformat() if exits else None,
        'Exit_Price': exits[-1].price if exits else None,
        'Exit_Reason': pkg.final_reason,
        'Trade_PL': round(pkg.net_points, 6),
        'Result': pkg.result,
        'MAE_Price_Pts': round(pkg.mae_pts, 6),
        'MFE_Price_Pts': round(pkg.mfe_pts, 6),
        'Open_At_End': pkg.open_at_end,
        'False_Breakout': pkg.false_breakout,
        'Units': pkg.units,
        'TP50_Units': pkg.tp50_units,
        'Had_4H_Close_Above_Range': pkg.had_4h_close_above_range,
        'Unit_Exits': ';'.join(
            f'U{ex.unit}:{ex.time.isoformat()}:{ex.price:.2f}:{ex.reason}:{ex.pl:.2f}' for ex in exits
        ),
        'Symbol': pkg.symbol,
    }


def handle_completed_package(
    pkg: Package,
    completed: list[Package],
    active: list[Package],
    current_idx: int,
    state: dict,
    reason: str | None = None,
) -> None:
    completed.append(pkg)
    if pkg in active:
        active.remove(pkg)

    final_reason = reason or pkg.final_reason
    if pkg.entry_kind == 'Stop-Breakout' and pkg.had_4h_close_above_range:
        state['bottom_limit_allowed'] = True

    if final_reason == 'False-Breakout-Close-25pct-Inside':
        state['pending'] = 'Bottom-Limit' if pkg.source_pending == 'Bottom-Limit' else 'Stop'
        state['primary_live_from_idx'] = current_idx + 1
        return

    if pkg.entry_kind == 'Top-Refill':
        can_arm_bottom = not state['require_bottom_close'] or state['bottom_limit_allowed']
        if not active and not state['pending_refill'] and is_failed_before_tp1(final_reason) and can_arm_bottom:
            state['pending'] = 'Bottom-Limit'
            state['primary_live_from_idx'] = current_idx + 1
        elif not active and not state['pending_refill'] and is_failed_before_tp1(final_reason):
            state['pending'] = 'Stop'
            state['primary_live_from_idx'] = current_idx + 1
        return

    if pkg.tp1_hit:
        state['pending_refill'] = True
        state['refill_live_from_idx'] = current_idx + 1
    elif is_failed_before_tp1(final_reason):
        can_arm_bottom = not state['require_bottom_close'] or pkg.had_4h_close_above_range or state['bottom_limit_allowed']
        state['pending'] = 'Bottom-Limit' if can_arm_bottom else 'Stop'
        state['primary_live_from_idx'] = current_idx + 1
    else:
        state['pending'] = 'Stop'
        state['primary_live_from_idx'] = current_idx + 1


def simulate_month_4h(
    market: str,
    period: str,
    month_daily: pd.DataFrame,
    trade4h: pd.DataFrame,
    exit_fill_mode: str,
    same_bar_priority: str,
    require_bottom_close: bool,
    breakout_tp50_units: int,
) -> tuple[list[Package], list[dict]]:
    rb = month_daily.iloc[:3]
    rh = float(rb['high'].max())
    rl = float(rb['low'].min())
    rv = rh - rl
    completed: list[Package] = []
    events: list[dict] = []
    if rv <= 0 or trade4h.empty:
        return completed, [{'Period': period, 'Event': 'skip', 'Reason': 'invalid_range_or_no_4h'}]

    active: list[Package] = []
    scheduled: dict[int, str] = {}
    state = {
        'pending': 'Stop',
        'pending_refill': False,
        'primary_live_from_idx': 0,
        'refill_live_from_idx': math.inf,
        'require_bottom_close': require_bottom_close,
        'bottom_limit_allowed': False,
    }

    for idx, row in trade4h.iterrows():
        row_time = pd.Timestamp(row['time'])

        # Next-open daily-close exits execute before new 4h touches.
        for pkg in list(active):
            scheduled_reason = scheduled.pop(id(pkg), None)
            if scheduled_reason is not None:
                close_open(pkg, row_time, float(row['open']), f'Next-Open-After-{scheduled_reason}')
                handle_completed_package(pkg, completed, active, idx, state, scheduled_reason)

        high = float(row['high'])
        low = float(row['low'])

        has_active_refill = any(pkg.entry_kind == 'Top-Refill' for pkg in active)
        if state['pending_refill'] and idx >= state['refill_live_from_idx'] and not has_active_refill and low <= rh:
            refill_live_time = live_time_for(trade4h, state['refill_live_from_idx'], row_time)
            refill = make_package(
                market,
                period,
                'Top-Refill',
                row,
                idx,
                rh,
                rh,
                rl,
                rv,
                refill_live_time,
                exit_fill_mode,
                state['pending'],
                breakout_tp50_units,
            )
            active.append(refill)
            state['pending_refill'] = False
            events.append({'Period': period, 'Time': row_time.isoformat(), 'Event': 'fill_top_refill', 'Price': rh})
            if same_bar_daily_exit(refill, row, scheduled):
                handle_completed_package(refill, completed, active, idx, state)

        if not active and not state['pending_refill'] and idx >= state['primary_live_from_idx']:
            filled: Package | None = None
            event = ''
            primary_live_time = live_time_for(trade4h, state['primary_live_from_idx'], row_time)
            if state['pending'] == 'Bottom-Limit' and high >= rh and low <= rl:
                if same_bar_priority == 'bottom':
                    filled = make_package(
                        market,
                        period,
                        'Bottom-Limit',
                        row,
                        idx,
                        rl,
                        rh,
                        rl,
                        rv,
                        primary_live_time,
                        exit_fill_mode,
                        state['pending'],
                        breakout_tp50_units,
                    )
                    event = 'fill_bottom_limit_same_bar_priority'
                else:
                    filled = make_package(
                        market,
                        period,
                        'Stop-Breakout',
                        row,
                        idx,
                        rh,
                        rh,
                        rl,
                        rv,
                        primary_live_time,
                        exit_fill_mode,
                        state['pending'],
                        breakout_tp50_units,
                    )
                    event = 'fill_stop_from_bottom_state_same_bar_priority'
            elif state['pending'] == 'Bottom-Limit' and high >= rh:
                filled = make_package(
                    market,
                    period,
                    'Stop-Breakout',
                    row,
                    idx,
                    rh,
                    rh,
                    rl,
                    rv,
                    primary_live_time,
                    exit_fill_mode,
                    state['pending'],
                    breakout_tp50_units,
                )
                event = 'fill_stop_from_bottom_state'
            elif state['pending'] == 'Bottom-Limit' and low <= rl:
                filled = make_package(
                    market,
                    period,
                    'Bottom-Limit',
                    row,
                    idx,
                    rl,
                    rh,
                    rl,
                    rv,
                    primary_live_time,
                    exit_fill_mode,
                    state['pending'],
                    breakout_tp50_units,
                )
                event = 'fill_bottom_limit'
            elif state['pending'] == 'Stop' and high >= rh:
                filled = make_package(
                    market,
                    period,
                    'Stop-Breakout',
                    row,
                    idx,
                    rh,
                    rh,
                    rl,
                    rv,
                    primary_live_time,
                    exit_fill_mode,
                    state['pending'],
                    breakout_tp50_units,
                )
                event = 'fill_stop'

            if filled is not None:
                active.append(filled)
                events.append({'Period': period, 'Time': row_time.isoformat(), 'Event': event, 'Price': filled.entry})
                if same_bar_daily_exit(filled, row, scheduled):
                    handle_completed_package(filled, completed, active, idx, state)

        # Fresh fills are not given same-bar target credit.
        for pkg in list(active):
            if pkg.entry_bar_idx == idx:
                continue
            if id(pkg) in scheduled:
                continue
            if pkg.entry_kind == 'Bottom-Limit':
                flat, tp1_new = process_bottom_limit(pkg, row, scheduled)
            elif pkg.entry_kind == 'Top-Refill':
                flat, tp1_new = process_top_refill(pkg, row, scheduled)
            else:
                flat, tp1_new = process_stop_breakout(pkg, row, scheduled)

            if tp1_new:
                state['pending_refill'] = True
                state['refill_live_from_idx'] = idx + 1
                events.append({'Period': period, 'Time': row_time.isoformat(), 'Event': 'arm_top_refill', 'Price': rh})

            if flat:
                handle_completed_package(pkg, completed, active, idx, state)

    if not trade4h.empty:
        final_row = trade4h.iloc[-1]
        for pkg in list(active):
            finalize_package(pkg, final_row)
            completed.append(pkg)

    return completed, events


def simulate(
    daily: pd.DataFrame,
    bars4h: pd.DataFrame,
    market: str,
    exit_fill_mode: str,
    same_bar_priority: str,
    require_bottom_close: bool,
    breakout_tp50_units: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    packages: list[Package] = []
    events: list[dict] = []
    for period, month_daily in period_groups(daily):
        _month4h, trade4h = prepare_month_4h(month_daily, bars4h)
        month_packages, month_events = simulate_month_4h(
            market,
            period,
            month_daily,
            trade4h,
            exit_fill_mode,
            same_bar_priority,
            require_bottom_close,
            breakout_tp50_units,
        )
        packages.extend(month_packages)
        events.extend(month_events)
    out = pd.DataFrame([package_to_row(pkg) for pkg in packages])
    if not out.empty:
        out['Cumulative_PL'] = pd.to_numeric(out['Trade_PL'], errors='coerce').fillna(0.0).cumsum()
    return out, pd.DataFrame(events)


def max_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), pnl.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float(pnl[pnl < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def stats(df: pd.DataFrame, point_value: float) -> dict:
    if df.empty:
        return {
            'packages': 0,
            'net_pts': 0.0,
            'net_usd': 0.0,
            'dd_usd': 0.0,
            'win_rate': 0.0,
            'pf': math.nan,
            'avg_mae': math.nan,
            'max_mae': math.nan,
            'false_breakouts': 0,
            'top_refills': 0,
            'bottom_limits': 0,
        }
    pnl = pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0)
    mae = pd.to_numeric(df['MAE_Price_Pts'], errors='coerce')
    return {
        'packages': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_usd': float(max_drawdown(pnl) * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'avg_mae': float(mae.mean()),
        'max_mae': float(mae.max()),
        'false_breakouts': int(df.get('False_Breakout', pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        'top_refills': int((df.get('Entry_Kind', pd.Series(dtype=str)) == 'Top-Refill').sum()),
        'bottom_limits': int((df.get('Entry_Kind', pd.Series(dtype=str)) == 'Bottom-Limit').sum()),
    }


def fmt_money(value: float) -> str:
    return f'${value:,.0f}'


def fmt_num(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.{digits}f}'


def fmt_pct(value: float) -> str:
    return f'{value:.1%}'


def write_report(report_path: Path, summary_rows: list[dict], csv_paths: list[Path]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Monthly ORB Restricted Stop-Limit Cycle: 4H Causal Sim',
        '',
        'This sidecar keeps the long-only restricted stop/limit cycle rules, but uses 4-hour bars derived from front-month 1-minute data. Orders armed by a close or TP1 event become live on the next 4-hour bar.',
        '',
        'Two daily-close exit treatments are compared:',
        '',
        '- `close`: fills daily-close exits at the confirming 4-hour close. This is closer to research parity.',
        '- `next_open`: fills daily-close exits at the next 4-hour bar open. This is closer to live automation.',
        '',
        'Fresh fills do not receive same-bar target credit. Same-bar false-breakout daily-close invalidations are honored.',
        '',
        '## Summary',
        '',
        '| Market | Exit Fill | Packages | Net Pts | Net USD | Max DD USD | Win Rate | PF | Avg MAE | Max MAE | False BO | Top Refills | Bottom Limits | CSV |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in summary_rows:
        lines.append(
            '| {market} | {mode} | {packages} | {net_pts} | {net_usd} | {dd_usd} | {win_rate} | {pf} | {avg_mae} | {max_mae} | {false_breakouts} | {top_refills} | {bottom_limits} | [{csv_name}]({csv_rel}) |'.format(
                market=row['market'],
                mode=row['mode'],
                packages=row['packages'],
                net_pts=fmt_num(row['net_pts'], 1),
                net_usd=fmt_money(row['net_usd']),
                dd_usd=fmt_money(row['dd_usd']),
                win_rate=fmt_pct(row['win_rate']),
                pf=fmt_num(row['pf'], 2),
                avg_mae=fmt_num(row['avg_mae'], 1),
                max_mae=fmt_num(row['max_mae'], 1),
                false_breakouts=row['false_breakouts'],
                top_refills=row['top_refills'],
                bottom_limits=row['bottom_limits'],
                csv_name=row['csv_path'].name,
                csv_rel=row['csv_path'].relative_to(report_path.parent).as_posix(),
            )
        )
    lines.extend(
        [
            '',
            '## Notes',
            '',
            '- The sim still cannot know the exact intrabar path inside a 4-hour candle.',
            '- `next_open` is the more realistic daily-close exit mode for automation because the daily close is only known after the bar closes.',
            '- If a 4-hour bar touches both the breakout stop and bottom limit while both are logically available, the default priority is `breakout`, matching the latest daily research state machine.',
            '- This is not yet a Pine/MultiCharts implementation; it is the causal Python reference pass before porting.',
            '',
            '## Outputs',
            '',
        ]
    )
    for path in csv_paths:
        rel = path.relative_to(report_path.parent).as_posix()
        if path.name == 'INDEX.md' and path.parent.name.startswith('charts_'):
            label = path.parent.name.replace('charts_', '').replace('_', ' ').upper() + ' 4h charts'
        else:
            label = path.name
        lines.append(f'- [{label}]({rel})')
    lines.append('')
    report_path.write_text('\n'.join(lines), encoding='utf-8')


def variant_suffix(require_bottom_close: bool, breakout_tp50_units: int) -> str:
    parts: list[str] = []
    if require_bottom_close:
        parts.append('bottom_confirmed')
    if breakout_tp50_units != 1:
        parts.append(f'tp50x{breakout_tp50_units}')
    return '_' + '_'.join(parts) if parts else ''


def parse_unit_exits(value: object) -> list[dict]:
    if value is None or pd.isna(value):
        return []
    exits: list[dict] = []
    for part in str(value).split(';'):
        if not part:
            continue
        unit_part, rest = part.split(':', 1)
        time_s, price_s, reason, pl_s = rest.rsplit(':', 3)
        exits.append(
            {
                'unit': unit_part,
                'time': pd.Timestamp(time_s),
                'price': float(price_s),
                'reason': reason,
                'pl': float(pl_s),
            }
        )
    return exits


def plot_time(value: object) -> float:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(NY).tz_localize(None)
    return mdates.date2num(ts.to_pydatetime())


def draw_4h_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    width = 0.12
    for _, row in bars.iterrows():
        x = plot_time(row['time'])
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.75, alpha=0.95, zorder=2)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                alpha=0.90,
                zorder=3,
            )
        )


def add_day_grid(ax: plt.Axes, bars: pd.DataFrame) -> None:
    seen: set[object] = set()
    for _, row in bars.iterrows():
        d = row['date']
        if d in seen:
            continue
        seen.add(d)
        ax.axvline(plot_time(row['time']), color='#94A3B8', linewidth=0.45, alpha=0.30, zorder=0)


def entry_marker(kind: str) -> tuple[str, str, str]:
    if kind == 'Bottom-Limit':
        return 'D', '#FBBF24', 'BL'
    if kind == 'Top-Refill':
        return 'o', '#38BDF8', 'TR'
    return '^', '#22C55E', 'SB'


def chart_period(
    label: str,
    period: str,
    month_daily: pd.DataFrame,
    month4h: pd.DataFrame,
    period_trades: pd.DataFrame,
    mode: str,
    out_path: Path,
) -> None:
    if month4h.empty:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    period_trades = period_trades.sort_values(['Entry_Time', 'Entry_Kind']).reset_index(drop=True)
    if period_trades.empty:
        range_bars = month_daily.iloc[:3]
        rh = float(range_bars['high'].max())
        rl = float(range_bars['low'].min())
        rv = rh - rl
    else:
        first = period_trades.iloc[0]
        rh = float(first['Range_High'])
        rl = float(first['Range_Low'])
        rv = float(first['Range'])
    tp50 = rh + 0.5 * rv
    tp1 = rh + rv
    tp2 = rh + 2.0 * rv
    breakout_stop = breakout_close_stop(rh, rl)
    bottom_stop = rl - 0.25 * rv

    fig = plt.figure(figsize=(18, 8), facecolor='#111827')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_4h_candles(ax, month4h)
    add_day_grid(ax, month4h)

    range_days = set(month_daily.iloc[:3]['date'])
    range_bars = month4h[month4h['date'].isin(range_days)]
    if not range_bars.empty:
        ax.axvspan(
            plot_time(range_bars.iloc[0]['time']),
            plot_time(range_bars.iloc[-1]['time']) + 0.16,
            color='#1F4E79',
            alpha=0.22,
            zorder=0,
        )
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)

    level_specs = [
        (rh, 'OR High', '#E5E7EB', '--', 1.1, 0.92),
        (rl, 'OR Low', '#E5E7EB', '--', 1.1, 0.92),
        (breakout_stop, '25% close stop', '#FB923C', ':', 0.9, 0.80),
        (bottom_stop, 'Bottom close stop', '#F97316', ':', 0.9, 0.65),
        (tp50, 'TP50', '#FDE047', ':', 0.9, 0.70),
        (tp1, 'TP1', '#84CC16', '--', 1.0, 0.78),
        (tp2, 'TP2', '#22C55E', '--', 0.9, 0.55),
    ]
    x_label = plot_time(month4h.iloc[-1]['time'])
    for y, text, color, ls, lw, alpha in level_specs:
        ax.axhline(y, color=color, linestyle=ls, linewidth=lw, alpha=alpha, zorder=1)
        ax.text(x_label, y, f' {text}', color=color, fontsize=8, va='center', ha='left', alpha=0.95)

    label_offsets = [24, -34, 46, -58, 70, -82]
    for idx, (_, tr) in enumerate(period_trades.iterrows(), 1):
        marker, color, code = entry_marker(str(tr['Entry_Kind']))
        entry_x = plot_time(tr['Entry_Time'])
        entry_y = float(tr['Entry_Price'])
        live_x = plot_time(tr['Order_Live_Time'])
        exits = parse_unit_exits(tr['Unit_Exits'])
        pl = float(tr['Trade_PL'])
        result = str(tr['Result'])

        ax.scatter([live_x], [entry_y], marker='o', s=32, facecolor='none', edgecolor='#60A5FA', linewidth=1.1, zorder=8)
        ax.scatter([entry_x], [entry_y], marker=marker, color=color, s=95, edgecolor='black', linewidth=0.8, zorder=10)
        ax.annotate(
            f'#{idx} {code} {pl:+.0f}pt',
            xy=(entry_x, entry_y),
            xytext=(8, label_offsets[(idx - 1) % len(label_offsets)]),
            textcoords='offset points',
            fontsize=7,
            color=color,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=color, alpha=0.92),
            arrowprops=dict(arrowstyle='-', color=color, alpha=0.65, linewidth=0.7),
            zorder=12,
        )

        exit_color = '#84CC16' if result == 'Win' else '#F43F5E' if result == 'Loss' else '#F59E0B'
        for ex in exits:
            ax.scatter(
                [plot_time(ex['time'])],
                [ex['price']],
                marker='x',
                color=exit_color,
                s=42,
                linewidth=1.2,
                zorder=11,
            )
        if exits:
            last = exits[-1]
            ax.annotate(
                f"#{idx} exit {result[0]}",
                xy=(plot_time(last['time']), last['price']),
                xytext=(8, -label_offsets[(idx - 1) % len(label_offsets)]),
                textcoords='offset points',
                fontsize=7,
                color=exit_color,
                bbox=dict(boxstyle='round,pad=0.18', fc='#111827', ec=exit_color, alpha=0.90),
                arrowprops=dict(arrowstyle='-', color=exit_color, alpha=0.60, linewidth=0.7),
                zorder=12,
            )

    total_pl = float(period_trades['Trade_PL'].sum()) if not period_trades.empty else 0.0
    ax.set_title(
        f'{label} monthly ORB 4h causal {mode} | {period} | {len(period_trades)} packages | {total_pl:+.1f} pts',
        color='white',
        fontsize=14,
        loc='left',
    )
    ax.set_ylabel('Price', color='#CBD5E1')
    ax.tick_params(colors='#CBD5E1', labelsize=8)
    ax.grid(True, axis='y', color='#334155', linewidth=0.45, alpha=0.40)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    fig.autofmt_xdate()
    for spine in ax.spines.values():
        spine.set_color('#334155')
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def build_charts(
    label: str,
    market: str,
    daily: pd.DataFrame,
    bars4h: pd.DataFrame,
    trades: pd.DataFrame,
    mode: str,
    chart_root: Path,
    include_no_trade: bool,
) -> Path:
    if chart_root.exists():
        shutil.rmtree(chart_root)
    chart_root.mkdir(parents=True, exist_ok=True)
    root_lines = [f'# {label} 4h causal {mode} charts', '', 'Blue hollow dots mark order-live time. Entry markers show actual fills. Vertical grid lines mark day changes.', '']
    year_lines: dict[int, list[str]] = {}

    for period, month_daily in period_groups(daily):
        period_trades = trades[trades['Period'].eq(period)].copy()
        if period_trades.empty and not include_no_trade:
            continue
        month4h, _trade4h = prepare_month_4h(month_daily, bars4h)
        if month4h.empty:
            continue
        year = int(period.split('-')[0])
        year_dir = chart_root / str(year)
        chart_name = f'{period}.png'
        chart_path = year_dir / chart_name
        chart_period(label, period, month_daily, month4h, period_trades, mode, chart_path)
        total_pl = float(period_trades['Trade_PL'].sum()) if not period_trades.empty else 0.0
        result = 'Win' if total_pl > 0 else 'Loss' if total_pl < 0 else 'Scratch'
        status = 'No trade' if period_trades.empty else result
        root_lines.append(f'- {period}: {len(period_trades)} packages, {total_pl:+.1f} pts, {status}, [{chart_name}]({year}/{chart_name})')
        year_lines.setdefault(year, [f'# {label} 4h causal {mode} charts: {year}', ''])
        year_lines[year].append(f'- {period}: {len(period_trades)} packages, {total_pl:+.1f} pts, {status}, [{chart_name}]({chart_name})')

    for year, lines in year_lines.items():
        (chart_root / str(year) / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (chart_root / 'INDEX.md').write_text('\n'.join(root_lines) + '\n', encoding='utf-8')
    return chart_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--market', choices=['mnq', 'nq', 'both'], default='mnq')
    parser.add_argument('--exit-fill-mode', choices=['close', 'next_open', 'both'], default='both')
    parser.add_argument('--same-bar-priority', choices=['breakout', 'bottom'], default='breakout')
    parser.add_argument(
        '--bottom-limit-require-4h-close-above-range',
        action='store_true',
        help='Only arm bottom-limit reclaims after a prior stop-breakout package had at least one 4h close above OR high.',
    )
    parser.add_argument(
        '--breakout-tp50-units',
        type=int,
        default=1,
        help='Number of stop-breakout units to exit at TP50. Baseline 1 gives 3-unit breakout; 2 gives 4-unit breakout.',
    )
    parser.add_argument('--rebuild-4h-cache', action='store_true')
    parser.add_argument('--charts', action='store_true', help='Generate monthly 4h candle charts for each selected market/mode.')
    parser.add_argument('--include-no-trade-charts', action='store_true', help='When charting, include monthly periods with no trade packages.')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'mnq' / 'case_studies' / 'monthly_orb' / 'restricted_stop_limit_cycle_4h_causal')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.breakout_tp50_units < 1:
        raise SystemExit('--breakout-tp50-units must be >= 1')
    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    modes = ['close', 'next_open'] if args.exit_fill_mode == 'both' else [args.exit_fill_mode]
    suffix = variant_suffix(args.bottom_limit_require_4h_close_above_range, args.breakout_tp50_units)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    csv_paths: list[Path] = []

    for market in markets:
        cfg = MARKETS[market]
        daily = load_daily(cfg['daily'])
        bars4h = load_or_build_4h(cfg, args.rebuild_4h_cache)
        for mode in modes:
            trades, events = simulate(
                daily,
                bars4h,
                market,
                mode,
                args.same_bar_priority,
                args.bottom_limit_require_4h_close_above_range,
                args.breakout_tp50_units,
            )
            csv_path = args.out_dir / f'{market}_monthly_orb_restricted_stop_limit_cycle_4h_causal_{mode}{suffix}.csv'
            events_path = args.out_dir / f'{market}_monthly_orb_restricted_stop_limit_cycle_4h_causal_{mode}{suffix}.events.csv'
            trades.to_csv(csv_path, index=False)
            events.to_csv(events_path, index=False)
            if args.charts:
                chart_root = args.out_dir / f'charts_{market}_{mode}{suffix}'
                build_charts(cfg['label'], market, daily, bars4h, trades, mode, chart_root, args.include_no_trade_charts)
                csv_paths.append(chart_root / 'INDEX.md')
            row = {'market': cfg['label'], 'mode': mode, 'csv_path': csv_path}
            row.update(stats(trades, cfg['point_value']))
            summary_rows.append(row)
            csv_paths.extend([csv_path, events_path])
            print(
                f"{cfg['label']} {mode}: packages={row['packages']} "
                f"net={fmt_money(row['net_usd'])} dd={fmt_money(row['dd_usd'])} "
                f"win={fmt_pct(row['win_rate'])} pf={fmt_num(row['pf'], 2)}"
            )

    report_path = args.out_dir / 'README.md'
    write_report(report_path, summary_rows, csv_paths)
    print(f'Wrote report: {report_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
