#!/usr/bin/env python3
"""Causal 4-hour overlap-range monthly ORB breakout cycle.

This is the live-style counterpart to ``monthly_orb_overlap_range_breakout.py``.
It keeps the overlap-range idea, but uses the same causal stop/limit cycle as
``monthly_orb_restricted_stop_limit_cycle_4h_causal.py``:

- Monthly OR = first three daily rows of each calendar month.
- Adjacent overlapping monthly ORs become a single combined range.
- Later monthly ORs can expand the active combined range if they overlap it.
- Default **long** side: resting buy-stop at the combined range high.
- Optional **short** side (`--side short` or `--side both`): resting sell-stop at the combined range low;
  **breakout-only** variant only for shorts in this pass (mirrored 3-unit stop-breakout). Run short and long as
  **separate CSV/chart outputs** so live tests do not mix fills on one account.
- Failed breakouts can arm a bottom-range limit only after at least one 4-hour
  candle has closed above the combined range.
- TP1 arms top refills while any original runner remains open.
- Orders created by a confirmed event become live on the next 4-hour bar.
- Daily-close exits can fill at the close or at the next 4-hour open.

The stop-breakout package uses 3 contracts:
1 @ TP50, 1 @ TP1, and 1 runner @ TP2.
Bottom-limit packages also use 3 contracts, but all remaining contracts exit at
TP1. Top-refill packages use 2 contracts, 1 @ TP50 and 1 @ TP1.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from monthly_orb_restricted_stop_limit_cycle_4h_causal import (
    MARKETS,
    add_day_grid,
    draw_4h_candles,
    fmt_money,
    fmt_num,
    fmt_pct,
    load_daily,
    load_or_build_4h,
    max_drawdown,
    parse_unit_exits,
    plot_time,
    profit_factor,
)


ROOT = Path(__file__).resolve().parents[1]
BACK_IN_RANGE_STOP_FRACTION = 0.25


@dataclass
class MonthlyRange:
    period: str
    year: int
    month: int
    start_date: object
    complete_date: object
    activation_date: object
    end_date: object
    high: float
    low: float


@dataclass
class Cluster:
    cluster_id: int
    start_period: str
    end_period: str
    start_date: object
    high: float
    low: float
    months: list[str] = field(default_factory=list)
    attempts: int = 0
    expanded_this_month: bool = False

    @property
    def size(self) -> float:
        return self.high - self.low


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
    cluster_id: int
    cluster_months: str
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
    catastrophe_stop_frac: float | None
    catastrophe_stop: float | None
    symbol: str
    exit_fill_mode: str
    source_pending: str
    side: str = 'long'
    exits: list[UnitExit] = field(default_factory=list)
    tp1_hit: bool = False
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    open_at_end: bool = False
    false_breakout: bool = False
    units: int = 3
    tp50_units: int = 1
    had_4h_close_above_range: bool = False
    had_4h_close_below_range: bool = False
    extension_used: bool = False
    extension_time: pd.Timestamp | None = None
    extension_old_tp1: float | None = None
    extension_new_tp1: float | None = None
    parent_entry_time: pd.Timestamp | None = None
    scalein_level: float | None = None

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


def overlap(high1: float, low1: float, high2: float, low2: float) -> bool:
    return max(low1, low2) <= min(high1, high2)


def monthly_ranges(daily: pd.DataFrame) -> list[MonthlyRange]:
    work = daily.copy()
    work['period'] = pd.to_datetime(work['date']).dt.to_period('M').astype(str)
    out: list[MonthlyRange] = []
    for period, sub in work.groupby('period', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) < 4:
            continue
        rb = sub.iloc[:3]
        year, month = map(int, period.split('-'))
        out.append(
            MonthlyRange(
                period=period,
                year=year,
                month=month,
                start_date=sub.iloc[0]['date'],
                complete_date=sub.iloc[2]['date'],
                activation_date=sub.iloc[3]['date'],
                end_date=sub.iloc[-1]['date'],
                high=float(rb['high'].max()),
                low=float(rb['low'].min()),
            )
        )
    return out


def overlap_cluster_records(daily: pd.DataFrame) -> pd.DataFrame:
    ranges = monthly_ranges(daily)
    records: list[dict] = []
    active: dict | None = None
    next_cluster_id = 1
    for i, current in enumerate(ranges):
        previous = ranges[i - 1] if i else None
        if active is not None and overlap(active['Range_High'], active['Range_Low'], current.high, current.low):
            active['End_Period'] = current.period
            active['End_Date'] = current.end_date
            active['Range_High'] = max(float(active['Range_High']), current.high)
            active['Range_Low'] = min(float(active['Range_Low']), current.low)
            active['Cluster_Months'].append(current.period)
            continue

        if active is not None:
            records.append(active)
            active = None

        if previous is not None and overlap(previous.high, previous.low, current.high, current.low):
            active = {
                'Cluster_ID': next_cluster_id,
                'Start_Period': previous.period,
                'End_Period': current.period,
                'Start_Date': previous.start_date,
                'Activation_Date': current.activation_date,
                'End_Date': current.end_date,
                'Range_High': max(previous.high, current.high),
                'Range_Low': min(previous.low, current.low),
                'Cluster_Months': [previous.period, current.period],
            }
            next_cluster_id += 1

    if active is not None:
        records.append(active)

    for rec in records:
        rec['Cluster_Months'] = '+'.join(rec['Cluster_Months'])
        rec['Range'] = float(rec['Range_High']) - float(rec['Range_Low'])
    return pd.DataFrame(records)


def prepare_4h_with_daily_close(daily: pd.DataFrame, bars4h: pd.DataFrame) -> pd.DataFrame:
    period_dates = set(daily['date'])
    work = bars4h[bars4h['date'].isin(period_dates)].copy().reset_index(drop=True)
    close_by_date = {pd.Timestamp(row['date']).date(): float(row['close']) for _, row in daily.iterrows()}
    work['daily_close'] = work['date'].map(close_by_date)
    work['is_daily_close_bar'] = work.groupby('date').cumcount() == work.groupby('date')['date'].transform('size') - 1
    return work


def maybe_start_or_expand_cluster(
    active: Cluster | None,
    current: MonthlyRange,
    previous: MonthlyRange | None,
    next_cluster_id: int,
) -> tuple[Cluster | None, int, dict | None]:
    if active is not None and overlap(active.high, active.low, current.high, current.low):
        old_high, old_low = active.high, active.low
        active.high = max(active.high, current.high)
        active.low = min(active.low, current.low)
        active.end_period = current.period
        active.months.append(current.period)
        active.expanded_this_month = active.high != old_high or active.low != old_low
        return active, next_cluster_id, {
            'Cluster_ID': active.cluster_id,
            'Event': 'expand',
            'Period': current.period,
            'Activation_Date': current.activation_date,
            'Range_High': active.high,
            'Range_Low': active.low,
            'Attempts': active.attempts,
        }

    if active is not None:
        active = None

    if previous is not None and overlap(previous.high, previous.low, current.high, current.low):
        cluster = Cluster(
            cluster_id=next_cluster_id,
            start_period=previous.period,
            end_period=current.period,
            start_date=previous.start_date,
            high=max(previous.high, current.high),
            low=min(previous.low, current.low),
            months=[previous.period, current.period],
            expanded_this_month=True,
        )
        return cluster, next_cluster_id + 1, {
            'Cluster_ID': cluster.cluster_id,
            'Event': 'start',
            'Period': current.period,
            'Activation_Date': current.activation_date,
            'Range_High': cluster.high,
            'Range_Low': cluster.low,
            'Attempts': cluster.attempts,
        }

    return None, next_cluster_id, None


def breakout_close_stop(rh: float, rl: float) -> float:
    return rh - BACK_IN_RANGE_STOP_FRACTION * (rh - rl)


def catastrophe_stop_level(rh: float, rl: float, frac: float) -> float:
    return rh - frac * (rh - rl)


def breakout_close_violation(close_px: float, rh: float, rl: float) -> bool:
    return close_px <= breakout_close_stop(rh, rl)


def breakout_close_violation_short(close_px: float, rh: float, rl: float) -> bool:
    """Short mirror: daily close re-enters range from below by ``BACK_IN_RANGE_STOP_FRACTION``."""
    thr = rl + BACK_IN_RANGE_STOP_FRACTION * (rh - rl)
    return close_px >= thr


def catastrophe_stop_level_short(rh: float, rl: float, frac: float) -> float:
    """Adverse spike **up** for a short stop-breakout (symmetric to long cat stop below)."""
    return rl + frac * (rh - rl)


def signed_unit_pl(side: str, entry: float, exit_price: float) -> float:
    if side == 'short':
        return float(entry - exit_price)
    return float(exit_price - entry)


def is_failed_before_tp1(reason: str) -> bool:
    return reason in {
        'Daily-Close-25pct-Back-In-Range-Before-TP1',
        'Daily-Close-Back-In-Range-Before-TP1',
        'Daily-Close-At-Or-Below-Range-High-Before-TP1',
        'False-Breakout-Close-25pct-Inside',
        'Next-Open-After-Daily-Close-25pct-Back-In-Range-Before-TP1',
        'Next-Open-After-Daily-Close-At-Or-Below-Range-High-Before-TP1',
        'Next-Open-After-False-Breakout-Close-25pct-Inside',
    }


def close_unit(pkg: Package, unit: int, time: pd.Timestamp, price: float, reason: str) -> None:
    if unit in pkg.open_units:
        pkg.exits.append(
            UnitExit(unit, pd.Timestamp(time), float(price), reason, signed_unit_pl(pkg.side, pkg.entry, float(price)))
        )


def close_open(pkg: Package, time: pd.Timestamp, price: float, reason: str) -> None:
    for unit in list(pkg.open_units):
        close_unit(pkg, unit, time, price, reason)


def is_supertrend_scalein(pkg: Package) -> bool:
    return pkg.entry_kind in {
        'Daily-ST-Bear-Reclaim-Scalein',
        'Daily-ST-Limit-Retest-Scalein',
    }


def is_supertrend_retest_scalein(pkg: Package) -> bool:
    return pkg.entry_kind == 'Daily-ST-Limit-Retest-Scalein'


def primary_active_count(active: list[Package]) -> int:
    return sum(1 for pkg in active if not is_supertrend_scalein(pkg))


def update_excursion(pkg: Package, high: float, low: float) -> None:
    if pkg.side == 'short':
        pkg.mae_pts = max(pkg.mae_pts, max(0.0, high - pkg.entry))
        pkg.mfe_pts = max(pkg.mfe_pts, max(0.0, pkg.entry - low))
    else:
        pkg.mae_pts = max(pkg.mae_pts, max(0.0, pkg.entry - low))
        pkg.mfe_pts = max(pkg.mfe_pts, max(0.0, high - pkg.entry))


def live_time_for(bars4h: pd.DataFrame, live_idx: int | float, fallback: pd.Timestamp) -> pd.Timestamp:
    if isinstance(live_idx, float) and not math.isfinite(live_idx):
        return pd.Timestamp(fallback)
    idx = int(live_idx)
    if 0 <= idx < len(bars4h):
        return pd.Timestamp(bars4h.iloc[idx]['time'])
    return pd.Timestamp(fallback)


def make_package(
    market: str,
    cluster: Cluster,
    kind: str,
    row: pd.Series,
    bar_idx: int,
    entry: float,
    order_live_time: pd.Timestamp,
    exit_fill_mode: str,
    source_pending: str,
    catastrophe_stop_frac: float | None = None,
    side: str = 'long',
) -> Package:
    rh = float(cluster.high)
    rl = float(cluster.low)
    rv = rh - rl
    if kind == 'Stop-Breakout' and side == 'short':
        tp1 = rl - rv
        tp50 = entry + (tp1 - entry) * 0.5
        tp2 = entry + 2.0 * (tp1 - entry)
        stop = None
        units = 3
        tp50_units = 1
        cat_stop = (
            catastrophe_stop_level_short(rh, rl, catastrophe_stop_frac)
            if catastrophe_stop_frac is not None
            else None
        )
        return Package(
            market=market.upper(),
            cluster_id=cluster.cluster_id,
            cluster_months='+'.join(cluster.months),
            entry_kind=kind,
            order_live_time=pd.Timestamp(order_live_time),
            entry_time=pd.Timestamp(row['time']),
            entry_bar_idx=bar_idx,
            entry=float(entry),
            range_high=rh,
            range_low=rl,
            range_size=rv,
            tp50=float(tp50),
            tp1=float(tp1),
            tp2=float(tp2),
            stop=None,
            catastrophe_stop_frac=catastrophe_stop_frac,
            catastrophe_stop=float(cat_stop) if cat_stop is not None else None,
            symbol=str(row.get('symbol', '')),
            exit_fill_mode=exit_fill_mode,
            source_pending=source_pending,
            side='short',
            units=units,
            tp50_units=tp50_units,
            had_4h_close_above_range=False,
            had_4h_close_below_range=float(row['close']) < rl,
        )
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
        units = 3
        tp50_units = 1
    cat_stop = catastrophe_stop_level(rh, rl, catastrophe_stop_frac) if kind == 'Stop-Breakout' and catastrophe_stop_frac is not None else None
    return Package(
        market=market.upper(),
        cluster_id=cluster.cluster_id,
        cluster_months='+'.join(cluster.months),
        entry_kind=kind,
        order_live_time=pd.Timestamp(order_live_time),
        entry_time=pd.Timestamp(row['time']),
        entry_bar_idx=bar_idx,
        entry=float(entry),
        range_high=rh,
        range_low=rl,
        range_size=rv,
        tp50=float(tp50),
        tp1=float(tp1),
        tp2=float(tp2) if tp2 is not None else None,
        stop=float(stop) if stop is not None else None,
        catastrophe_stop_frac=catastrophe_stop_frac if kind == 'Stop-Breakout' else None,
        catastrophe_stop=float(cat_stop) if cat_stop is not None else None,
        symbol=str(row.get('symbol', '')),
        exit_fill_mode=exit_fill_mode,
        source_pending=source_pending,
        side=side,
        units=units,
        tp50_units=tp50_units,
        had_4h_close_above_range=kind == 'Stop-Breakout' and float(row['close']) > rh,
        had_4h_close_below_range=False,
    )


def make_supertrend_scalein(
    market: str,
    parent: Package,
    row: pd.Series,
    bar_idx: int,
    level: float,
    units: int,
) -> Package:
    return Package(
        market=market.upper(),
        cluster_id=parent.cluster_id,
        cluster_months=parent.cluster_months,
        entry_kind='Daily-ST-Bear-Reclaim-Scalein',
        order_live_time=pd.Timestamp(row['time']),
        entry_time=pd.Timestamp(row['time']),
        entry_bar_idx=bar_idx,
        entry=float(row['close']),
        range_high=parent.range_high,
        range_low=parent.range_low,
        range_size=parent.range_size,
        tp50=parent.tp50,
        tp1=parent.tp1,
        tp2=parent.tp2,
        stop=float(level),
        catastrophe_stop_frac=None,
        catastrophe_stop=None,
        symbol=str(row.get('symbol', '')),
        exit_fill_mode=parent.exit_fill_mode,
        source_pending='Daily-ST-Bear-Reclaim',
        side=parent.side,
        units=int(units),
        tp50_units=0,
        had_4h_close_above_range=parent.had_4h_close_above_range,
        had_4h_close_below_range=parent.had_4h_close_below_range,
        parent_entry_time=parent.entry_time,
        scalein_level=float(level),
    )


def make_supertrend_retest_scalein(
    market: str,
    parent: Package,
    row: pd.Series,
    bar_idx: int,
    level: float,
    units: int,
) -> Package:
    return Package(
        market=market.upper(),
        cluster_id=parent.cluster_id,
        cluster_months=parent.cluster_months,
        entry_kind='Daily-ST-Limit-Retest-Scalein',
        order_live_time=pd.Timestamp(row['time']),
        entry_time=pd.Timestamp(row['time']),
        entry_bar_idx=bar_idx,
        entry=float(level),
        range_high=parent.range_high,
        range_low=parent.range_low,
        range_size=parent.range_size,
        tp50=parent.tp50,
        tp1=parent.tp1,
        tp2=parent.tp2,
        stop=float(level),
        catastrophe_stop_frac=None,
        catastrophe_stop=None,
        symbol=str(row.get('symbol', '')),
        exit_fill_mode=parent.exit_fill_mode,
        source_pending='Daily-ST-Limit-Retest',
        side=parent.side,
        units=int(units),
        tp50_units=0,
        had_4h_close_above_range=parent.had_4h_close_above_range,
        had_4h_close_below_range=parent.had_4h_close_below_range,
        parent_entry_time=parent.entry_time,
        scalein_level=float(level),
    )


def maybe_schedule_or_close(
    pkg: Package,
    row: pd.Series,
    reason: str,
    scheduled: dict[int, str],
) -> bool:
    if pkg.exit_fill_mode == 'close':
        close_open(pkg, pd.Timestamp(row['time']), float(row['close']), reason)
        return True
    scheduled[id(pkg)] = reason
    return False


def same_bar_daily_exit(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> bool:
    if not bool(row.get('is_daily_close_bar', False)):
        return False
    close_px = float(row['close'])
    if pkg.entry_kind == 'Stop-Breakout':
        viol = (
            breakout_close_violation_short(close_px, pkg.range_high, pkg.range_low)
            if pkg.side == 'short'
            else breakout_close_violation(close_px, pkg.range_high, pkg.range_low)
        )
        if viol:
            pkg.false_breakout = True
            return maybe_schedule_or_close(pkg, row, 'False-Breakout-Close-25pct-Inside', scheduled)
    if pkg.entry_kind == 'Bottom-Limit':
        assert pkg.stop is not None
        if close_px <= pkg.stop:
            return maybe_schedule_or_close(pkg, row, 'Bottom-Limit-Daily-Close-SL', scheduled)
    if pkg.entry_kind == 'Top-Refill' and close_px <= pkg.range_high:
        return maybe_schedule_or_close(pkg, row, 'Daily-Close-At-Or-Below-Range-High-Before-TP1', scheduled)
    return False


def process_stop_breakout_short(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> tuple[bool, bool]:
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    if pkg.catastrophe_stop is not None and high >= pkg.catastrophe_stop:
        reason = f'Catastrophe-Stop-{pkg.catastrophe_stop_frac:.2f}-Range-Depth'
        close_open(pkg, pd.Timestamp(row['time']), pkg.catastrophe_stop, reason)
        return True, False
    if close_px < pkg.range_low:
        pkg.had_4h_close_below_range = True
    newly_hit_tp1 = False
    tp1_unit = pkg.tp50_units + 1
    runner_unit = pkg.tp50_units + 2

    for unit in range(1, pkg.tp50_units + 1):
        if unit in pkg.open_units and low <= pkg.tp50:
            close_unit(pkg, unit, pd.Timestamp(row['time']), pkg.tp50, 'TP50')
    if not pkg.tp1_hit and low <= pkg.tp1:
        close_unit(pkg, tp1_unit, pd.Timestamp(row['time']), pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True

    if pkg.tp1_hit and runner_unit in pkg.open_units:
        assert pkg.tp2 is not None
        if low <= pkg.tp2:
            close_unit(pkg, runner_unit, pd.Timestamp(row['time']), pkg.tp2, 'TP2')
            return True, newly_hit_tp1
        if bool(row.get('is_daily_close_bar', False)) and breakout_close_violation_short(
            close_px, pkg.range_high, pkg.range_low
        ):
            closed = maybe_schedule_or_close(pkg, row, 'Daily-Close-25pct-Back-In-Range-After-TP1', scheduled)
            return closed, newly_hit_tp1
    elif not pkg.tp1_hit and bool(row.get('is_daily_close_bar', False)) and breakout_close_violation_short(
        close_px, pkg.range_high, pkg.range_low
    ):
        closed = maybe_schedule_or_close(pkg, row, 'Daily-Close-25pct-Back-In-Range-Before-TP1', scheduled)
        return closed, newly_hit_tp1

    return not pkg.open_units, newly_hit_tp1


def process_stop_breakout(pkg: Package, row: pd.Series, scheduled: dict[int, str]) -> tuple[bool, bool]:
    if pkg.side == 'short':
        return process_stop_breakout_short(pkg, row, scheduled)
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    if pkg.catastrophe_stop is not None and low <= pkg.catastrophe_stop:
        reason = f'Catastrophe-Stop-{pkg.catastrophe_stop_frac:.2f}-Range-Depth'
        close_open(pkg, pd.Timestamp(row['time']), pkg.catastrophe_stop, reason)
        return True, False
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


def process_supertrend_scalein(pkg: Package, row: pd.Series) -> tuple[bool, bool]:
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    if pkg.side == 'long':
        trailing_stop = row.get('daily_st_stop', math.nan) if is_supertrend_retest_scalein(pkg) else pkg.scalein_level
        if pd.isna(trailing_stop):
            trailing_stop = pkg.scalein_level
        assert trailing_stop is not None
        if close_px < float(trailing_stop):
            reason = (
                '4H-Close-Below-Daily-ST-Retest-Stop'
                if is_supertrend_retest_scalein(pkg)
                else '4H-Close-Below-ST-Scalein-Level'
            )
            close_open(pkg, pd.Timestamp(row['time']), close_px, reason)
            return True, False
    return not pkg.open_units, False


def close_linked_scaleins(
    parent: Package,
    active: list[Package],
    completed: list[Package],
    current_idx: int,
) -> None:
    if parent.entry_kind != 'Stop-Breakout' or not parent.exits:
        return
    last_exit = sorted(parent.exits, key=lambda ex: (ex.time, ex.unit))[-1]
    for pkg in list(active):
        if (
            is_supertrend_scalein(pkg)
            and pkg.parent_entry_time == parent.entry_time
            and pkg.cluster_id == parent.cluster_id
        ):
            close_open(pkg, last_exit.time, last_exit.price, 'Parent-Runner-Exit')
            handle_completed_package(pkg, completed, active, current_idx, None, 'Parent-Runner-Exit')


def maybe_extend_package(pkg: Package, cluster: Cluster, row: pd.Series) -> bool:
    if pkg.entry_kind != 'Stop-Breakout' or pkg.extension_used or pkg.cluster_id != cluster.cluster_id:
        return False
    close_px = float(row['close'])
    if pkg.side == 'short':
        if close_px >= cluster.low or cluster.low >= pkg.range_low:
            return False
        new_tp1 = cluster.low - cluster.size
        if new_tp1 >= pkg.tp1:
            return False
    else:
        if close_px <= cluster.high or cluster.high <= pkg.range_high:
            return False
        new_tp1 = cluster.high + cluster.size
        if new_tp1 <= pkg.tp1:
            return False

    old_tp1 = pkg.tp1
    pkg.extension_used = True
    pkg.extension_time = pd.Timestamp(row['time'])
    pkg.extension_old_tp1 = old_tp1
    pkg.extension_new_tp1 = new_tp1
    pkg.range_high = float(cluster.high)
    pkg.range_low = float(cluster.low)
    pkg.range_size = float(cluster.size)
    pkg.tp50 = pkg.entry + (new_tp1 - pkg.entry) * 0.5
    pkg.tp1 = float(new_tp1)
    if pkg.tp2 is not None:
        pkg.tp2 = pkg.entry + 2.0 * (new_tp1 - pkg.entry)
    return True


def finalize_package(pkg: Package, row: pd.Series) -> None:
    if pkg.open_units:
        close_open(pkg, pd.Timestamp(row['time']), float(row['close']), 'Final-Close')
        pkg.open_at_end = True


def package_to_row(pkg: Package) -> dict:
    exits = sorted(pkg.exits, key=lambda ex: (ex.time, ex.unit))
    return {
        'Market': pkg.market,
        'Trade_Side': pkg.side,
        'Cluster_ID': pkg.cluster_id,
        'Cluster_Months': pkg.cluster_months,
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
        'Catastrophe_Stop_Frac': pkg.catastrophe_stop_frac,
        'Catastrophe_Stop': pkg.catastrophe_stop,
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
        'Had_4H_Close_Below_Range': pkg.had_4h_close_below_range,
        'Extension_Used': pkg.extension_used,
        'Extension_Time': pkg.extension_time.isoformat() if pkg.extension_time is not None else None,
        'Extension_Old_TP1': pkg.extension_old_tp1,
        'Extension_New_TP1': pkg.extension_new_tp1,
        'Parent_Entry_Time': pkg.parent_entry_time.isoformat() if pkg.parent_entry_time is not None else None,
        'Scalein_Level': pkg.scalein_level,
        'Unit_Exits': ';'.join(
            f'U{ex.unit}:{ex.time.isoformat()}:{ex.price:.2f}:{ex.reason}:{ex.pl:.2f}' for ex in exits
        ),
        'Symbol': pkg.symbol,
    }


def fresh_state(variant: str) -> dict:
    return {
        'variant': variant,
        'pending': 'Stop',
        'pending_refill': False,
        'primary_live_from_idx': 0,
        'refill_live_from_idx': math.inf,
        'bottom_limit_allowed': False,
    }


def handle_completed_package(
    pkg: Package,
    completed: list[Package],
    active: list[Package],
    current_idx: int,
    state: dict | None,
    reason: str | None = None,
) -> None:
    completed.append(pkg)
    if pkg in active:
        active.remove(pkg)
    if state is None:
        return

    final_reason = reason or pkg.final_reason
    if pkg.entry_kind == 'Stop-Breakout' and pkg.had_4h_close_above_range:
        state['bottom_limit_allowed'] = True

    if state.get('variant') == 'breakout_only':
        state['pending_refill'] = False
        state['pending'] = 'Stop'
        state['primary_live_from_idx'] = current_idx + 1
        return

    if pkg.entry_kind == 'Top-Refill':
        if not active and not state['pending_refill'] and is_failed_before_tp1(final_reason):
            state['pending'] = 'Bottom-Limit' if state['bottom_limit_allowed'] else 'Stop'
            state['primary_live_from_idx'] = current_idx + 1
        return

    if pkg.tp1_hit:
        state['pending_refill'] = True
        state['refill_live_from_idx'] = current_idx + 1
    elif is_failed_before_tp1(final_reason):
        state['pending'] = 'Bottom-Limit' if (pkg.had_4h_close_above_range or state['bottom_limit_allowed']) else 'Stop'
        state['primary_live_from_idx'] = current_idx + 1
    else:
        state['pending'] = 'Stop'
        state['primary_live_from_idx'] = current_idx + 1


def process_range_event(
    active_cluster: Cluster | None,
    current_range: MonthlyRange,
    previous_range: MonthlyRange | None,
    next_cluster_id: int,
    state: dict | None,
    variant: str,
) -> tuple[Cluster | None, int, dict | None, dict | None]:
    old_id = active_cluster.cluster_id if active_cluster is not None else None
    active_cluster, next_cluster_id, event = maybe_start_or_expand_cluster(
        active_cluster,
        current_range,
        previous_range,
        next_cluster_id,
    )
    if event is None:
        if old_id is not None and active_cluster is None:
            state = None
        return active_cluster, next_cluster_id, state, None

    if event['Event'] == 'start':
        state = fresh_state(variant)
    elif old_id is not None and active_cluster is not None and active_cluster.cluster_id == old_id:
        state = state or fresh_state(variant)
    return active_cluster, next_cluster_id, state, event


def fill_primary_if_possible(
    market: str,
    bars4h: pd.DataFrame,
    idx: int,
    row: pd.Series,
    active_cluster: Cluster,
    active: list[Package],
    completed: list[Package],
    state: dict,
    scheduled: dict[int, str],
    events: list[dict],
    exit_fill_mode: str,
    same_bar_priority: str,
    variant: str,
    max_concurrent_trades: int,
    catastrophe_stop_frac: float | None,
    side: str = 'long',
    trend_filter: str = 'none',
) -> None:
    same_cluster_active = any(pkg.cluster_id == active_cluster.cluster_id for pkg in active)
    if (
        active_cluster.attempts >= 2
        or same_cluster_active
        or primary_active_count(active) >= max_concurrent_trades
        or state['pending_refill']
        or idx < state['primary_live_from_idx']
    ):
        return

    high = float(row['high'])
    low = float(row['low'])
    rh = active_cluster.high
    rl = active_cluster.low
    primary_live_time = live_time_for(bars4h, state['primary_live_from_idx'], pd.Timestamp(row['time']))
    filled: Package | None = None
    event = ''

    if trend_filter == 'daily_supertrend':
        direction = row.get('daily_st_direction', math.nan)
        bullish = pd.notna(direction) and float(direction) > 0
        bearish = pd.notna(direction) and float(direction) < 0
        if side == 'short':
            touched = low <= rl
            if touched and not bearish:
                events.append(
                    {
                        'Cluster_ID': active_cluster.cluster_id,
                        'Cluster_Months': '+'.join(active_cluster.months),
                        'Time': pd.Timestamp(row['time']).isoformat(),
                        'Event': 'skip_daily_supertrend_not_bearish',
                        'Price': rl,
                        'Range_High': rh,
                        'Range_Low': rl,
                        'Attempts': active_cluster.attempts,
                    }
                )
                return
            if touched and high < rl:
                return
        else:
            touched = high >= rh
            if touched and not bullish:
                events.append(
                    {
                        'Cluster_ID': active_cluster.cluster_id,
                        'Cluster_Months': '+'.join(active_cluster.months),
                        'Time': pd.Timestamp(row['time']).isoformat(),
                        'Event': 'skip_daily_supertrend_not_bullish',
                        'Price': rh,
                        'Range_High': rh,
                        'Range_Low': rl,
                        'Attempts': active_cluster.attempts,
                    }
                )
                return
            if touched and low > rh:
                return

    if side == 'short':
        if state['pending'] == 'Stop' and low <= rl:
            filled = make_package(
                market,
                active_cluster,
                'Stop-Breakout',
                row,
                idx,
                rl,
                primary_live_time,
                exit_fill_mode,
                state['pending'],
                catastrophe_stop_frac,
                side='short',
            )
            event = 'fill_stop_short'
    else:
        bottom_allowed = state['bottom_limit_allowed'] and variant != 'breakout_only'
        if state['pending'] == 'Bottom-Limit' and not bottom_allowed:
            state['pending'] = 'Stop'

        if state['pending'] == 'Bottom-Limit' and high >= rh and low <= rl:
            if same_bar_priority == 'bottom':
                filled = make_package(
                    market, active_cluster, 'Bottom-Limit', row, idx, rl, primary_live_time, exit_fill_mode, state['pending']
                )
                event = 'fill_bottom_limit_same_bar_priority'
            else:
                filled = make_package(
                    market,
                    active_cluster,
                    'Stop-Breakout',
                    row,
                    idx,
                    rh,
                    primary_live_time,
                    exit_fill_mode,
                    state['pending'],
                    catastrophe_stop_frac,
                )
                event = 'fill_stop_from_bottom_state_same_bar_priority'
        elif state['pending'] == 'Bottom-Limit' and high >= rh:
            filled = make_package(
                market,
                active_cluster,
                'Stop-Breakout',
                row,
                idx,
                rh,
                primary_live_time,
                exit_fill_mode,
                state['pending'],
                catastrophe_stop_frac,
            )
            event = 'fill_stop_from_bottom_state'
        elif state['pending'] == 'Bottom-Limit' and low <= rl:
            filled = make_package(market, active_cluster, 'Bottom-Limit', row, idx, rl, primary_live_time, exit_fill_mode, state['pending'])
            event = 'fill_bottom_limit'
        elif state['pending'] == 'Stop' and high >= rh:
            filled = make_package(
                market,
                active_cluster,
                'Stop-Breakout',
                row,
                idx,
                rh,
                primary_live_time,
                exit_fill_mode,
                state['pending'],
                catastrophe_stop_frac,
            )
            event = 'fill_stop'

    if filled is not None:
        active.append(filled)
        active_cluster.attempts += 1
        events.append(
            {
                'Cluster_ID': active_cluster.cluster_id,
                'Cluster_Months': '+'.join(active_cluster.months),
                'Time': pd.Timestamp(row['time']).isoformat(),
                'Event': event,
                'Price': filled.entry,
                'Range_High': rh,
                'Range_Low': rl,
                'Attempts': active_cluster.attempts,
            }
        )
        if same_bar_daily_exit(filled, row, scheduled):
            handle_completed_package(filled, completed, active, idx, state)


def parent_runner_open(pkg: Package) -> bool:
    if pkg.entry_kind != 'Stop-Breakout' or pkg.side != 'long':
        return False
    runner_unit = pkg.tp50_units + 2
    return runner_unit in pkg.open_units


def find_active_parent(active: list[Package], entry_time: pd.Timestamp, cluster_id: int) -> Package | None:
    for pkg in active:
        if pkg.entry_kind == 'Stop-Breakout' and pkg.cluster_id == cluster_id and pkg.entry_time == entry_time:
            return pkg
    return None


def has_scalein_for_parent(active: list[Package], parent: Package) -> bool:
    return any(
        is_supertrend_scalein(pkg)
        and pkg.parent_entry_time == parent.entry_time
        and pkg.cluster_id == parent.cluster_id
        for pkg in active
    )


def has_pending_scalein_for_parent(pending: list[dict], parent: Package) -> bool:
    return any(
        item['parent_entry_time'] == parent.entry_time
        and item['cluster_id'] == parent.cluster_id
        for item in pending
    )


def has_completed_retest_scalein(completed: list[Package], parent: Package) -> bool:
    return any(
        is_supertrend_retest_scalein(pkg)
        and pkg.parent_entry_time == parent.entry_time
        and pkg.cluster_id == parent.cluster_id
        for pkg in completed
    )


def maybe_arm_supertrend_scaleins(
    active: list[Package],
    pending: list[dict],
    row: pd.Series,
    idx: int,
    prev_st_direction: float | None,
    events: list[dict],
    scalein_contracts: int,
) -> None:
    if scalein_contracts <= 0 or prev_st_direction is None or pd.isna(prev_st_direction):
        return
    direction = row.get('daily_st_direction', math.nan)
    level = row.get('daily_st_stop', math.nan)
    if pd.isna(direction) or pd.isna(level) or not (float(prev_st_direction) > 0 and float(direction) < 0):
        return
    for parent in list(active):
        if (
            not parent_runner_open(parent)
            or has_scalein_for_parent(active, parent)
            or has_pending_scalein_for_parent(pending, parent)
        ):
            continue
        pending.append(
            {
                'cluster_id': parent.cluster_id,
                'cluster_months': parent.cluster_months,
                'parent_entry_time': parent.entry_time,
                'level': float(level),
                'live_from_idx': idx + 1,
            }
        )
        events.append(
            {
                'Cluster_ID': parent.cluster_id,
                'Cluster_Months': parent.cluster_months,
                'Time': pd.Timestamp(row['time']).isoformat(),
                'Event': 'arm_daily_st_bear_reclaim_scalein',
                'Price': float(level),
                'Parent_Entry_Time': parent.entry_time.isoformat(),
                'Scalein_Contracts': scalein_contracts,
            }
            )


def maybe_fill_supertrend_retest_scaleins(
    market: str,
    active: list[Package],
    completed: list[Package],
    row: pd.Series,
    idx: int,
    events: list[dict],
    retest_contracts: int,
) -> None:
    if retest_contracts <= 0:
        return
    direction = row.get('daily_st_direction', math.nan)
    level = row.get('daily_st_stop', math.nan)
    if pd.isna(direction) or pd.isna(level) or float(direction) <= 0:
        return
    level = float(level)
    low = float(row['low'])
    high = float(row['high'])
    if not (low <= level <= high):
        return
    for parent in list(active):
        if (
            not parent_runner_open(parent)
            or has_scalein_for_parent(active, parent)
            or has_completed_retest_scalein(completed, parent)
            or parent.entry_bar_idx == idx
        ):
            continue
        pkg = make_supertrend_retest_scalein(market, parent, row, idx, level, retest_contracts)
        active.append(pkg)
        events.append(
            {
                'Cluster_ID': pkg.cluster_id,
                'Cluster_Months': pkg.cluster_months,
                'Time': pd.Timestamp(row['time']).isoformat(),
                'Event': 'fill_daily_st_limit_retest_scalein',
                'Price': pkg.entry,
                'Scalein_Level': level,
                'Parent_Entry_Time': parent.entry_time.isoformat(),
                'Scalein_Contracts': retest_contracts,
            }
        )


def maybe_fill_supertrend_scaleins(
    market: str,
    active: list[Package],
    completed: list[Package],
    pending: list[dict],
    row: pd.Series,
    idx: int,
    events: list[dict],
    scalein_contracts: int,
) -> None:
    if scalein_contracts <= 0:
        return
    close_px = float(row['close'])
    for item in list(pending):
        parent = find_active_parent(active, item['parent_entry_time'], int(item['cluster_id']))
        if parent is None or not parent_runner_open(parent):
            pending.remove(item)
            continue
        if idx < int(item['live_from_idx']):
            continue
        level = float(item['level'])
        if close_px > level:
            pkg = make_supertrend_scalein(market, parent, row, idx, level, scalein_contracts)
            active.append(pkg)
            pending.remove(item)
            events.append(
                {
                    'Cluster_ID': pkg.cluster_id,
                    'Cluster_Months': pkg.cluster_months,
                    'Time': pd.Timestamp(row['time']).isoformat(),
                    'Event': 'fill_daily_st_bear_reclaim_scalein',
                    'Price': pkg.entry,
                    'Scalein_Level': level,
                    'Parent_Entry_Time': parent.entry_time.isoformat(),
                    'Scalein_Contracts': scalein_contracts,
                }
            )


def simulate(
    daily: pd.DataFrame,
    bars4h: pd.DataFrame,
    market: str,
    exit_fill_mode: str,
    same_bar_priority: str,
    variant: str,
    max_concurrent_trades: int = 1,
    catastrophe_stop_frac: float | None = None,
    side: str = 'long',
    trend_filter: str = 'none',
    supertrend_scalein_contracts: int = 0,
    supertrend_retest_contracts: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if side == 'short' and variant != 'breakout_only':
        raise ValueError('Short side is implemented only for variant breakout_only.')
    ranges = monthly_ranges(daily)
    if not ranges:
        return pd.DataFrame(), pd.DataFrame()

    previous_range_by_period = {ranges[i].period: ranges[i - 1] if i else None for i in range(len(ranges))}
    bars = prepare_4h_with_daily_close(daily, bars4h)
    if bars.empty:
        return pd.DataFrame(), pd.DataFrame()
    if trend_filter == 'daily_supertrend' or supertrend_scalein_contracts > 0 or supertrend_retest_contracts > 0:
        daily_st = daily_supertrend_on_4h(bars, 14, 3.0, confirmed=True)
        bars['daily_st_direction'] = daily_st['direction'].values
        bars['daily_st_stop'] = daily_st['supertrend'].values

    range_idx = 0
    active_cluster: Cluster | None = None
    next_cluster_id = 1
    state: dict | None = None
    active: list[Package] = []
    completed: list[Package] = []
    scheduled: dict[int, str] = {}
    pending_scaleins: list[dict] = []
    events: list[dict] = []

    for idx, row in bars.iterrows():
        row_time = pd.Timestamp(row['time'])
        prev_st_direction = None
        if 'daily_st_direction' in bars.columns and idx > 0:
            prev_st_direction = bars.iloc[idx - 1].get('daily_st_direction', math.nan)

        # Next-open daily-close exits execute before new 4h touches.
        for pkg in list(active):
            if pkg not in active:
                continue
            scheduled_reason = scheduled.pop(id(pkg), None)
            if scheduled_reason is not None:
                close_open(pkg, row_time, float(row['open']), f'Next-Open-After-{scheduled_reason}')
                pkg_state = state if active_cluster is not None and pkg.cluster_id == active_cluster.cluster_id else None
                handle_completed_package(pkg, completed, active, idx, pkg_state, scheduled_reason)
                close_linked_scaleins(pkg, active, completed, idx)

        while range_idx < len(ranges) and row['date'] >= ranges[range_idx].activation_date:
            current = ranges[range_idx]
            previous = previous_range_by_period[current.period]
            active_cluster, next_cluster_id, state, event = process_range_event(
                active_cluster,
                current,
                previous,
                next_cluster_id,
                state,
                variant,
            )
            if event is not None:
                events.append(event)
                if state is not None:
                    state['primary_live_from_idx'] = idx
            range_idx += 1

        maybe_arm_supertrend_scaleins(
            active,
            pending_scaleins,
            row,
            idx,
            prev_st_direction,
            events,
            supertrend_scalein_contracts,
        )

        if active_cluster is not None and state is not None:
            has_active_refill = any(pkg.entry_kind == 'Top-Refill' for pkg in active)
            if (
                side == 'long'
                and variant != 'breakout_only'
                and state['pending_refill']
                and idx >= state['refill_live_from_idx']
                and not has_active_refill
            ):
                if float(row['low']) <= active_cluster.high:
                    refill_live_time = live_time_for(bars, state['refill_live_from_idx'], row_time)
                    refill = make_package(
                        market,
                        active_cluster,
                        'Top-Refill',
                        row,
                        idx,
                        active_cluster.high,
                        refill_live_time,
                        exit_fill_mode,
                        state['pending'],
                    )
                    active.append(refill)
                    state['pending_refill'] = False
                    events.append(
                        {
                            'Cluster_ID': active_cluster.cluster_id,
                            'Cluster_Months': '+'.join(active_cluster.months),
                            'Time': row_time.isoformat(),
                            'Event': 'fill_top_refill',
                            'Price': active_cluster.high,
                            'Range_High': active_cluster.high,
                            'Range_Low': active_cluster.low,
                        }
                    )
                    if same_bar_daily_exit(refill, row, scheduled):
                        handle_completed_package(refill, completed, active, idx, state)

            fill_primary_if_possible(
                market,
                bars,
                idx,
                row,
                active_cluster,
                active,
                completed,
                state,
                scheduled,
                events,
                exit_fill_mode,
                same_bar_priority,
                variant,
                max_concurrent_trades,
                catastrophe_stop_frac,
                side,
                trend_filter,
            )

        # Fresh fills are not given same-bar target credit.
        for pkg in list(active):
            if pkg not in active:
                continue
            if pkg.entry_bar_idx == idx or id(pkg) in scheduled:
                continue
            if pkg.entry_kind == 'Bottom-Limit':
                flat, tp1_new = process_bottom_limit(pkg, row, scheduled)
            elif pkg.entry_kind == 'Top-Refill':
                flat, tp1_new = process_top_refill(pkg, row, scheduled)
            elif is_supertrend_scalein(pkg):
                flat, tp1_new = process_supertrend_scalein(pkg, row)
            else:
                flat, tp1_new = process_stop_breakout(pkg, row, scheduled)

            if (
                variant != 'breakout_only'
                and tp1_new
                and state is not None
                and active_cluster is not None
                and pkg.cluster_id == active_cluster.cluster_id
            ):
                state['pending_refill'] = True
                state['refill_live_from_idx'] = idx + 1
                events.append(
                    {
                        'Cluster_ID': pkg.cluster_id,
                        'Cluster_Months': pkg.cluster_months,
                        'Time': row_time.isoformat(),
                        'Event': 'arm_top_refill',
                        'Price': pkg.range_high,
                    }
                )

            if flat:
                pkg_state = (
                    state
                    if active_cluster is not None
                    and pkg.cluster_id == active_cluster.cluster_id
                    and not is_supertrend_scalein(pkg)
                    else None
                )
                handle_completed_package(pkg, completed, active, idx, pkg_state)
                close_linked_scaleins(pkg, active, completed, idx)

        if active_cluster is not None:
            for pkg in list(active):
                if id(pkg) in scheduled:
                    continue
                if maybe_extend_package(pkg, active_cluster, row):
                    events.append(
                        {
                            'Cluster_ID': active_cluster.cluster_id,
                            'Cluster_Months': '+'.join(active_cluster.months),
                            'Time': row_time.isoformat(),
                            'Event': 'extend_target',
                            'Old_TP1': pkg.extension_old_tp1,
                            'New_TP1': pkg.extension_new_tp1,
                            'Range_High': active_cluster.high,
                            'Range_Low': active_cluster.low,
                        }
                    )

        # Scale-in trigger is a 4h close condition. Process parent intrabar
        # exits first, then add only if the original runner survived the bar.
        maybe_fill_supertrend_scaleins(
            market,
            active,
            completed,
            pending_scaleins,
            row,
            idx,
            events,
            supertrend_scalein_contracts,
        )
        # Limit-retest add uses the confirmed daily Supertrend stop as a live
        # buy-limit. It fills after parent exits are processed for the bar.
        maybe_fill_supertrend_retest_scaleins(
            market,
            active,
            completed,
            row,
            idx,
            events,
            supertrend_retest_contracts,
        )

    if not bars.empty:
        final_row = bars.iloc[-1]
        for pkg in list(active):
            finalize_package(pkg, final_row)
            completed.append(pkg)

    out = pd.DataFrame([package_to_row(pkg) for pkg in completed])
    if not out.empty:
        out['Cumulative_PL'] = pd.to_numeric(out['Trade_PL'], errors='coerce').fillna(0.0).cumsum()
    return out, pd.DataFrame(events)


def stats(df: pd.DataFrame, point_value: float) -> dict:
    if df.empty:
        return {
            'trades': 0,
            'net_pts': 0.0,
            'net_usd': 0.0,
            'dd_usd': 0.0,
            'win_rate': 0.0,
            'pf': math.nan,
            'avg_mae': math.nan,
            'max_mae': math.nan,
            'tp1_hit_rate': 0.0,
            'bottom_limit_count': 0,
            'top_refill_count': 0,
        }
    pnl = pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0)
    mae = pd.to_numeric(df.get('MAE_Price_Pts', pd.Series(dtype=float)), errors='coerce')
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_usd': float(max_drawdown(pnl) * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'avg_mae': float(mae.mean()),
        'max_mae': float(mae.max()),
        'tp1_hit_rate': float(df['Unit_Exits'].astype(str).str.contains('TP1').mean()),
        'bottom_limit_count': int((df['Entry_Kind'] == 'Bottom-Limit').sum()),
        'top_refill_count': int((df['Entry_Kind'] == 'Top-Refill').sum()),
    }


def winner_drawdown_frame(results: dict[tuple[str, str, str], pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict] = []
    for (market, variant, mode), df in sorted(results.items()):
        if df.empty:
            continue
        cfg = MARKETS[market]
        work = df[pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0) > 0].copy()
        for _, row in work.iterrows():
            range_size = float(row['Range'])
            mae = float(row['MAE_Price_Pts'])
            depth = mae / range_size if range_size else math.nan
            rows.append(
                {
                    'Market': cfg['label'],
                    'Run_Variant': variant,
                    'Variant': variant_title(variant),
                    'Exit_Fill_Mode': mode,
                    'Cluster_ID': int(row['Cluster_ID']),
                    'Cluster_Months': row['Cluster_Months'],
                    'Entry_Kind': row['Entry_Kind'],
                    'Entry_Time': row['Entry_Time'],
                    'Exit_Time': row['Exit_Time'],
                    'Entry_Price': float(row['Entry_Price']),
                    'Range_High': float(row['Range_High']),
                    'Range_Low': float(row['Range_Low']),
                    'Range': range_size,
                    'MAE_Price_Pts': mae,
                    'MAE_Range_Depth_Pct': depth * 100.0 if not pd.isna(depth) else math.nan,
                    'MFE_Price_Pts': float(row['MFE_Price_Pts']),
                    'Trade_PL_Pts': float(row['Trade_PL']),
                    'Trade_PL_USD': float(row['Trade_PL']) * cfg['point_value'],
                    'Exit_Reason': row['Exit_Reason'],
                    'Unit_Exits': row['Unit_Exits'],
                }
            )
    return pd.DataFrame(rows)


def strip_side_suffix(run_variant: str) -> tuple[str, str]:
    if run_variant.endswith('_short'):
        return run_variant[: -len('_short')], 'short'
    return run_variant, 'long'


def strip_filter_suffix(run_variant: str) -> tuple[str, str]:
    if run_variant.endswith('_daily_st'):
        return run_variant[: -len('_daily_st')], 'daily_supertrend'
    return run_variant, 'none'


def strip_scalein_suffix(run_variant: str) -> tuple[str, int]:
    match = re.search(r'_scalein(\d+)$', run_variant)
    if match:
        return run_variant[: match.start()], int(match.group(1))
    return run_variant, 0


def strip_retest_suffix(run_variant: str) -> tuple[str, int]:
    match = re.search(r'_retest(\d+)$', run_variant)
    if match:
        return run_variant[: match.start()], int(match.group(1))
    return run_variant, 0


def strip_max_active_suffix(core: str) -> tuple[str, int]:
    head, sep, tail = core.rpartition('_')
    if sep and tail.endswith('active') and tail[:-6].isdigit():
        return head, int(tail[:-6])
    return core, 1


def base_variant(variant: str) -> str:
    core, _ = strip_side_suffix(variant)
    core, _ = strip_retest_suffix(core)
    core, _ = strip_scalein_suffix(core)
    core, _ = strip_filter_suffix(core)
    base, _ = strip_max_active_suffix(core)
    return base


def max_active_from_variant(variant: str) -> int:
    core, _ = strip_side_suffix(variant)
    core, _ = strip_retest_suffix(core)
    core, _ = strip_scalein_suffix(core)
    core, _ = strip_filter_suffix(core)
    _, max_active = strip_max_active_suffix(core)
    return max_active


def variant_title(variant: str) -> str:
    core, side = strip_side_suffix(variant)
    core, retest_qty = strip_retest_suffix(core)
    core, scalein_qty = strip_scalein_suffix(core)
    core, trend_filter = strip_filter_suffix(core)
    base, max_active = strip_max_active_suffix(core)
    title = 'Full cycle first pass' if base == 'full_cycle' else 'Breakout only'
    if max_active != 1:
        title = f'{title} ({max_active} active max)'
    if trend_filter == 'daily_supertrend':
        title = f'{title} — Daily ST filter'
    if scalein_qty:
        title = f'{title} + ST reclaim scale-in x{scalein_qty}'
    if retest_qty:
        title = f'{title} + ST limit retest x{retest_qty}'
    if side == 'short':
        title = f'{title} — Short'
    return title


def variant_file_label(variant: str) -> str:
    return variant.replace('-', '_')


def make_run_variant(variant: str, max_concurrent_trades: int) -> str:
    return variant if max_concurrent_trades == 1 else f'{variant}_{max_concurrent_trades}active'


def apply_trend_filter_suffix(run_variant: str, trend_filter: str) -> str:
    if trend_filter == 'daily_supertrend':
        return f'{run_variant}_daily_st'
    return run_variant


def apply_scalein_suffix(run_variant: str, scalein_contracts: int) -> str:
    if scalein_contracts > 0:
        return f'{run_variant}_scalein{scalein_contracts}'
    return run_variant


def apply_retest_suffix(run_variant: str, retest_contracts: int) -> str:
    if retest_contracts > 0:
        return f'{run_variant}_retest{retest_contracts}'
    return run_variant


def parse_sides(raw: str) -> list[str]:
    if raw == 'both':
        return ['long', 'short']
    if raw in ('long', 'short'):
        return [raw]
    raise ValueError(raw)


def parse_max_concurrent_values(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.split(','):
        text = part.strip()
        if not text:
            continue
        value = int(text)
        if value < 1:
            raise ValueError('--max-concurrent-trades values must be >= 1')
        values.append(value)
    return sorted(set(values)) or [1]


def calculate_atr(bars: pd.DataFrame, length: int = 14) -> pd.Series:
    high = pd.to_numeric(bars['high'], errors='coerce')
    low = pd.to_numeric(bars['low'], errors='coerce')
    close = pd.to_numeric(bars['close'], errors='coerce')
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def calculate_supertrend(bars: pd.DataFrame, length: int = 14, multiplier: float = 3.0) -> pd.DataFrame:
    high = pd.to_numeric(bars['high'], errors='coerce').reset_index(drop=True)
    low = pd.to_numeric(bars['low'], errors='coerce').reset_index(drop=True)
    close = pd.to_numeric(bars['close'], errors='coerce').reset_index(drop=True)
    atr = calculate_atr(bars, length).reset_index(drop=True)
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = pd.Series(index=bars.index, dtype=float).reset_index(drop=True)
    final_lower = pd.Series(index=bars.index, dtype=float).reset_index(drop=True)
    direction = pd.Series(index=bars.index, dtype=float).reset_index(drop=True)
    stop = pd.Series(index=bars.index, dtype=float).reset_index(drop=True)

    for i in range(len(bars)):
        if pd.isna(atr.iloc[i]):
            continue
        if i == 0 or pd.isna(final_upper.iloc[i - 1]) or pd.isna(final_lower.iloc[i - 1]) or pd.isna(direction.iloc[i - 1]):
            final_upper.iloc[i] = basic_upper.iloc[i]
            final_lower.iloc[i] = basic_lower.iloc[i]
            direction.iloc[i] = 1.0 if close.iloc[i] >= hl2.iloc[i] else -1.0
        else:
            prev_upper = final_upper.iloc[i - 1]
            prev_lower = final_lower.iloc[i - 1]
            prev_close = close.iloc[i - 1]
            final_upper.iloc[i] = basic_upper.iloc[i] if basic_upper.iloc[i] < prev_upper or prev_close > prev_upper else prev_upper
            final_lower.iloc[i] = basic_lower.iloc[i] if basic_lower.iloc[i] > prev_lower or prev_close < prev_lower else prev_lower
            prev_direction = direction.iloc[i - 1]
            if prev_direction < 0 and close.iloc[i] > final_upper.iloc[i]:
                direction.iloc[i] = 1.0
            elif prev_direction > 0 and close.iloc[i] < final_lower.iloc[i]:
                direction.iloc[i] = -1.0
            else:
                direction.iloc[i] = prev_direction
        stop.iloc[i] = final_lower.iloc[i] if direction.iloc[i] > 0 else final_upper.iloc[i]

    return pd.DataFrame(
        {
            'supertrend': stop.values,
            'direction': direction.values,
            'bull_stop': stop.where(direction > 0).values,
            'bear_stop': stop.where(direction < 0).values,
        },
        index=bars.index,
    )


def daily_supertrend_on_4h(
    bars: pd.DataFrame,
    length: int = 14,
    multiplier: float = 3.0,
    confirmed: bool = False,
) -> pd.DataFrame:
    daily = (
        bars.groupby('date', as_index=False)
        .agg(
            time=('time', 'last'),
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
        )
        .sort_values('date')
        .reset_index(drop=True)
    )
    daily_st = calculate_supertrend(daily, length, multiplier)
    daily = pd.concat([daily[['date']], daily_st.reset_index(drop=True)], axis=1)
    if confirmed:
        for col in ('supertrend', 'direction', 'bull_stop', 'bear_stop'):
            daily[col] = daily[col].shift(1)
    mapped = bars[['date']].merge(daily, on='date', how='left')
    return mapped[['supertrend', 'direction', 'bull_stop', 'bear_stop']]


def chart_cluster(
    label: str,
    cluster: pd.Series,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    mode: str,
    variant: str,
    out_path: Path,
) -> None:
    if bars.empty:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trades = trades.sort_values(['Entry_Time', 'Entry_Kind']).reset_index(drop=True)
    rh = float(cluster['Range_High'])
    rl = float(cluster['Range_Low'])
    rv = rh - rl
    trade_side = 'long'
    if not trades.empty and 'Trade_Side' in trades.columns:
        trade_side = str(trades.iloc[0]['Trade_Side'])

    if trade_side == 'short':
        tp50 = rl - 0.5 * rv
        tp1 = rl - rv
        tp2 = rl - 2.0 * rv
        close_line = rl + BACK_IN_RANGE_STOP_FRACTION * rv
        line_specs = [
            (rl, 'Combined Low / Sell Stop', '#E5E7EB', '--', 1.2, 0.95),
            (rh, 'Combined High', '#E5E7EB', '--', 1.2, 0.95),
            (close_line, '25% close reclaim', '#FB923C', ':', 0.95, 0.85),
            (tp50, 'TP50', '#FDE047', ':', 0.95, 0.75),
            (tp1, 'TP1', '#84CC16', '--', 1.0, 0.82),
            (tp2, 'TP2', '#22C55E', '--', 0.9, 0.60),
        ]
    else:
        tp50 = rh + 0.5 * rv
        tp1 = rh + rv
        tp2 = rh + 2.0 * rv
        close_line = breakout_close_stop(rh, rl)
        line_specs = [
            (rh, 'Combined High / Buy Stop', '#E5E7EB', '--', 1.2, 0.95),
            (rl, 'Combined Low', '#E5E7EB', '--', 1.2, 0.95),
            (close_line, '25% close stop', '#FB923C', ':', 0.95, 0.85),
            (tp50, 'TP50', '#FDE047', ':', 0.95, 0.75),
            (tp1, 'TP1', '#84CC16', '--', 1.0, 0.82),
            (tp2, 'TP2', '#22C55E', '--', 0.9, 0.60),
        ]

    fig = plt.figure(figsize=(18, 8), facecolor='#111827')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_4h_candles(ax, bars)
    add_day_grid(ax, bars)
    supertrend = daily_supertrend_on_4h(bars, 14, 3.0)
    st_x = [plot_time(value) for value in bars['time']]
    ax.plot(st_x, supertrend['bull_stop'], color='#22C55E', linewidth=1.45, alpha=0.95, zorder=5)
    ax.plot(st_x, supertrend['bear_stop'], color='#F97316', linewidth=1.45, alpha=0.95, zorder=5)
    latest_st = supertrend['supertrend'].dropna()
    if not latest_st.empty:
        latest_direction = supertrend['direction'].dropna().iloc[-1]
        st_color = '#22C55E' if latest_direction > 0 else '#F97316'
        ax.text(
            0.012,
            0.93,
            f'Daily Supertrend ATR(14)x3: {latest_st.iloc[-1]:,.1f}',
            transform=ax.transAxes,
            color=st_color,
            fontsize=9,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.18', fc='#111827', ec=st_color, alpha=0.86),
            va='top',
            ha='left',
            zorder=20,
        )

    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.12, zorder=0)
    x_label = plot_time(bars.iloc[-1]['time'])
    for y, text, color, ls, lw, alpha in line_specs:
        ax.axhline(y, color=color, linestyle=ls, linewidth=lw, alpha=alpha, zorder=1)
        ax.text(x_label, y, f' {text}', color=color, fontsize=8, va='center', ha='left', alpha=0.95)

    act_y = rl if trade_side == 'short' else rh
    act_va = 'top' if trade_side == 'short' else 'bottom'
    ax.axvline(plot_time(pd.Timestamp(cluster['Activation_Date'])), color='#60A5FA', linewidth=1.0, alpha=0.7, zorder=1)
    ax.text(
        plot_time(pd.Timestamp(cluster['Activation_Date'])),
        act_y,
        ' active',
        color='#60A5FA',
        fontsize=8,
        va=act_va,
        ha='left',
        alpha=0.95,
    )

    if trades.empty:
        ax.text(
            0.02,
            0.95,
            'No filled overlap breakout',
            transform=ax.transAxes,
            color='#F8FAFC',
            fontsize=12,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', fc='#111827', ec='#64748B', alpha=0.92),
            va='top',
        )
    label_offsets = [24, -34, 46, -58, 70, -82]
    for i, (_, tr) in enumerate(trades.iterrows(), 1):
        entry_x = plot_time(tr['Entry_Time'])
        entry_y = float(tr['Entry_Price'])
        live_x = plot_time(tr['Order_Live_Time'])
        pl = float(tr['Trade_PL'])
        result = str(tr['Result'])
        tr_side = str(tr.get('Trade_Side', 'long'))
        if tr['Entry_Kind'] == 'Stop-Breakout':
            marker = 'v' if tr_side == 'short' else '^'
        else:
            marker = 'D' if tr['Entry_Kind'] == 'Bottom-Limit' else 'o'
        color = '#22C55E' if tr['Entry_Kind'] == 'Stop-Breakout' else '#FBBF24' if tr['Entry_Kind'] == 'Bottom-Limit' else '#38BDF8'
        ax.scatter([live_x], [entry_y], marker='o', s=32, facecolor='none', edgecolor='#60A5FA', linewidth=1.1, zorder=8)
        ax.scatter([entry_x], [entry_y], marker=marker, color=color, s=95, edgecolor='black', linewidth=0.8, zorder=10)
        ax.annotate(
            f'#{i} {tr["Entry_Kind"]} {pl:+.0f}pt',
            xy=(entry_x, entry_y),
            xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            fontsize=7,
            color=color,
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=color, alpha=0.92),
            arrowprops=dict(arrowstyle='-', color=color, alpha=0.65, linewidth=0.7),
            zorder=12,
        )
        exit_color = '#84CC16' if result == 'Win' else '#F43F5E' if result == 'Loss' else '#F59E0B'
        exits = parse_unit_exits(tr['Unit_Exits'])
        for ex in exits:
            ax.scatter([plot_time(ex['time'])], [ex['price']], marker='x', color=exit_color, s=46, linewidth=1.2, zorder=11)
        if exits:
            last = exits[-1]
            ax.annotate(
                f'#{i} exit {result[0]}',
                xy=(plot_time(last['time']), last['price']),
                xytext=(8, -label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                fontsize=7,
                color=exit_color,
                bbox=dict(boxstyle='round,pad=0.18', fc='#111827', ec=exit_color, alpha=0.90),
                arrowprops=dict(arrowstyle='-', color=exit_color, alpha=0.60, linewidth=0.7),
                zorder=12,
            )

    total_pl = float(trades['Trade_PL'].sum()) if not trades.empty else 0.0
    title_status = 'No-op' if trades.empty else 'Win' if total_pl > 0 else 'Loss' if total_pl < 0 else 'Scratch'
    ax.set_title(
        f"{label} overlap range 4h causal {variant_title(variant)} {mode} | "
        f"Cluster {int(cluster['Cluster_ID'])} {cluster['Cluster_Months']} | "
        f"{len(trades)} packages | {total_pl:+.1f} pts | {title_status}",
        color='white',
        fontsize=13,
        loc='left',
    )
    ax.set_ylabel('Price', color='#CBD5E1')
    ax.tick_params(colors='#CBD5E1', labelsize=8)
    ax.grid(True, axis='y', color='#334155', linewidth=0.45, alpha=0.40)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()
    for spine in ax.spines.values():
        spine.set_color('#334155')
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def build_cluster_charts(
    label: str,
    daily: pd.DataFrame,
    bars4h: pd.DataFrame,
    trades: pd.DataFrame,
    mode: str,
    variant: str,
    chart_root: Path,
    include_no_trade: bool,
) -> Path:
    if chart_root.exists():
        shutil.rmtree(chart_root)
    chart_root.mkdir(parents=True, exist_ok=True)
    clusters = overlap_cluster_records(daily)
    root_lines = [
        f'# {label} overlap range 4h causal {variant_title(variant)} {mode} charts',
        '',
        'Every overlapping monthly-range cluster is shown. No-op charts are clusters where the overlap existed but no breakout package filled.',
        '',
    ]
    year_lines: dict[int, list[str]] = {}
    for _, cluster in clusters.iterrows():
        cluster_trades = trades[trades['Cluster_ID'].eq(cluster['Cluster_ID'])].copy() if not trades.empty else pd.DataFrame()
        if cluster_trades.empty and not include_no_trade:
            continue
        start = pd.Timestamp(cluster['Start_Date']).date()
        end = pd.Timestamp(cluster['End_Date']).date()
        if not cluster_trades.empty:
            exit_dates = pd.to_datetime(cluster_trades['Exit_Time'], utc=True, errors='coerce').dropna()
            if not exit_dates.empty:
                end = max(end, exit_dates.max().date())
        cluster_bars = bars4h[(bars4h['date'] >= start) & (bars4h['date'] <= end)].copy()
        if cluster_bars.empty:
            continue
        year = int(str(cluster['Start_Period']).split('-')[0])
        status = 'No-op'
        total_pl = 0.0
        if not cluster_trades.empty:
            total_pl = float(cluster_trades['Trade_PL'].sum())
            status = 'Win' if total_pl > 0 else 'Loss' if total_pl < 0 else 'Scratch'
        chart_name = f"cluster_{int(cluster['Cluster_ID']):02d}_{cluster['Cluster_Months'].replace('+', '_')}_{status.lower()}.png"
        year_dir = chart_root / str(year)
        chart_path = year_dir / chart_name
        chart_cluster(label, cluster, cluster_bars, cluster_trades, mode, variant, chart_path)
        line = f"- Cluster {int(cluster['Cluster_ID'])}: {cluster['Cluster_Months']}, {len(cluster_trades)} packages, {total_pl:+.1f} pts, {status}, [{chart_name}]({year}/{chart_name})"
        root_lines.append(line)
        year_lines.setdefault(year, [f'# {label} overlap range 4h causal {variant_title(variant)} {mode}: {year}', ''])
        year_lines[year].append(line.replace(f']({year}/', ']('))
    for year, lines in year_lines.items():
        (chart_root / str(year) / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (chart_root / 'INDEX.md').write_text('\n'.join(root_lines) + '\n', encoding='utf-8')
    return chart_root / 'INDEX.md'


def write_report(
    results: dict[tuple[str, str, str], pd.DataFrame],
    events_by_run: dict[tuple[str, str, str], pd.DataFrame],
    output_paths: list[Path],
    chart_indexes: list[Path],
) -> Path:
    report_root = MARKETS['mnq']['root'] / 'case_studies' / 'monthly_orb' / 'overlap_range_breakout_4h_causal'
    report_root.mkdir(parents=True, exist_ok=True)
    report = report_root / 'README.md'
    winner_dd = winner_drawdown_frame(results)
    if not winner_dd.empty:
        winner_dd_path = report_root / 'winner_drawdown_by_trade.csv'
        winner_dd.to_csv(winner_dd_path, index=False)
        output_paths.append(winner_dd_path)
    lines = [
        '# Monthly ORB Overlap Range Breakout - 4H Causal Stop/Limit Cycle',
        '',
        'This rewrites the older daily-close overlap-range breakout into the causal 4-hour engine used by the restricted stop/limit cycle.',
        '',
        'Rules in this pass:',
        '',
        '- Default **long** side: buy stop at the combined range high; optional **`--side short`** (or **`--side both`**) runs a mirrored sell-stop breakout at the combined range low (`breakout_only` only), writing separate `Run_Variant` rows and files (`*_short`) for side-by-side live tests.',
        '- Monthly OR = first three daily rows of each calendar month.',
        '- Adjacent overlapping monthly ORs become one combined range; later overlapping months can expand that range.',
        '- After the combined range is active, the resting primary is a buy stop at the range high (long) or a sell stop at the range low (short, breakout-only path).',
        '- Stop-breakout package uses **3 contracts**: 1 @ TP50, 1 @ TP1, 1 runner @ TP2.',
        '- A failed stop-breakout can arm the bottom-range limit only after at least one 4-hour candle closed above the range.',
        '- Bottom-limit package uses 3 contracts: 1 off at the top boundary and 2 off at TP1.',
        '- TP1 arms a 2-contract top refill while the original runner may remain open.',
        '- Max two primary attempts per overlap cluster; top refills do not count as new primary attempts.',
    '- Runs with a `2 active max` label allow one older overlap trade to remain open while a newer overlap cluster takes one package.',
    '- `ST reclaim scale-in` risk-on runs add contracts only after a confirmed daily Supertrend bearish flip during an open long runner; the stored bearish stop level becomes a 4h-close reclaim trigger and a 4h-close stop for those added contracts.',
    '- `ST limit retest` risk-on runs place a 5-contract long limit at the confirmed daily Supertrend trailing stop while an original breakout runner is open; the add exits with that runner or on a 4h close below the current confirmed daily Supertrend stop.',
    '- Daily-close invalidations are shown in both close-fill and next-open-fill modes.',
        '',
        '## Summary',
        '',
        '| Market | Variant | Exit fill | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts | Bottom limits | Top refills | TP1-hit rows |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for (market, variant, mode), df in sorted(results.items()):
        cfg = MARKETS[market]
        s = stats(df, cfg['point_value'])
        lines.append(
            f"| {cfg['label']} | {variant_title(variant)} | {mode} | {s['trades']} | {fmt_num(s['net_pts'])} | {fmt_money(s['net_usd'])} | "
            f"{fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'], 2)} | "
            f"{fmt_num(s['avg_mae'])} | {fmt_num(s['max_mae'])} | {s['bottom_limit_count']} | "
            f"{s['top_refill_count']} | {fmt_pct(s['tp1_hit_rate'])} |"
        )

    lines.extend(
        [
            '',
            '## Read',
            '',
            '- **Full cycle first pass** is banked here as the original causal overlap-cycle run.',
            '- **Breakout only** removes bottom-limit reclaims and top refills. It keeps the 3-contract stop-breakout (long at range high; use `--side short` for the mirrored short at range low, separate outputs).',
            '- The first-pass read still matters: in the full cycle, the edge was concentrated in the Stop-Breakout packages while the inherited Bottom-Limit and Top-Refill components were net-negative.',
            '',
        ]
    )

    lines.extend(['## Winner Drawdown Profile', ''])
    if winner_dd.empty:
        lines.append('No winning trades.')
    else:
        lines.extend(
            [
                'Depth means the winner’s maximum adverse excursion measured from entry back into the combined range.',
                'For a breakout entry, 25% depth means price came one quarter of the overlap range back inside before eventually winning.',
                '',
                '| Market | Variant | Exit fill | Winners | Avg depth | Max depth | <=25% | 25-50% | 50-100% | >100% |',
                '|---|---|---|---:|---:|---:|---:|---:|---:|---:|',
            ]
        )
        for (market, variant, mode), df in sorted(results.items()):
            cfg = MARKETS[market]
            sub = winner_dd[
                winner_dd['Market'].eq(cfg['label'])
                & winner_dd['Run_Variant'].eq(variant)
                & winner_dd['Exit_Fill_Mode'].eq(mode)
            ]
            if sub.empty:
                continue
            depth = pd.to_numeric(sub['MAE_Range_Depth_Pct'], errors='coerce')
            lines.append(
                f"| {cfg['label']} | {variant_title(variant)} | {mode} | {len(sub)} | "
                f"{depth.mean():.1f}% | {depth.max():.1f}% | "
                f"{int((depth <= 25).sum())} | {int(((depth > 25) & (depth <= 50)).sum())} | "
                f"{int(((depth > 50) & (depth <= 100)).sum())} | {int((depth > 100).sum())} |"
            )
        lines.extend(['', 'Worst winning pullbacks:', '', '| Market | Variant | Exit fill | Cluster | Entry | MAE pts | Depth | Net USD |', '|---|---|---|---|---|---:|---:|---:|'])
        worst_wins = winner_dd.sort_values('MAE_Range_Depth_Pct', ascending=False).head(12)
        for _, row in worst_wins.iterrows():
            lines.append(
                f"| {row['Market']} | {row['Variant']} | {row['Exit_Fill_Mode']} | {int(row['Cluster_ID'])} {row['Cluster_Months']} | "
                f"{row['Entry_Time']} | {float(row['MAE_Price_Pts']):,.1f} | {float(row['MAE_Range_Depth_Pct']):.1f}% | "
                f"{fmt_money(float(row['Trade_PL_USD']))} |"
            )
        lines.extend(['', f'Per-trade winner drawdown CSV: `{winner_dd_path.relative_to(ROOT)}`', ''])

    lines.extend(['## Loss Containment Scan', ''])
    lines.extend(['| Market | Variant | Exit fill | Losses | Gross loss USD | Worst loss USD | Avg losing depth | Max losing depth | Main exit reason |', '|---|---|---|---:|---:|---:|---:|---:|---|'])
    for (market, variant, mode), df in sorted(results.items()):
        if df.empty:
            continue
        cfg = MARKETS[market]
        work = df.copy()
        work['Trade_PL'] = pd.to_numeric(work['Trade_PL'], errors='coerce').fillna(0.0)
        losses = work[work['Trade_PL'] < 0].copy()
        if losses.empty:
            continue
        losses['Depth'] = pd.to_numeric(losses['MAE_Price_Pts'], errors='coerce') / pd.to_numeric(losses['Range'], errors='coerce') * 100.0
        reason = str(losses['Exit_Reason'].mode().iloc[0]) if not losses['Exit_Reason'].mode().empty else 'n/a'
        lines.append(
            f"| {cfg['label']} | {variant_title(variant)} | {mode} | {len(losses)} | "
            f"{fmt_money(float(losses['Trade_PL'].sum()) * cfg['point_value'])} | "
            f"{fmt_money(float(losses['Trade_PL'].min()) * cfg['point_value'])} | "
            f"{losses['Depth'].mean():.1f}% | {losses['Depth'].max():.1f}% | {reason} |"
        )
    lines.append('')

    lines.extend(['', '## Entry Kind Split', ''])
    for (market, variant, mode), df in sorted(results.items()):
        cfg = MARKETS[market]
        lines.extend([f'### {cfg["label"]} - {variant_title(variant)} - {mode}', ''])
        if df.empty:
            lines.append('No trades.')
            continue
        lines.extend(['| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |', '|---|---:|---:|---:|---:|---:|---:|'])
        for kind, sub in df.groupby('Entry_Kind', sort=True):
            s = stats(sub, cfg['point_value'])
            lines.append(
                f"| {kind} | {s['trades']} | {fmt_num(s['net_pts'])} | {fmt_money(s['net_usd'])} | "
                f"{fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'], 2)} |"
            )
        lines.append('')

    lines.extend(['## Yearly Split', ''])
    for (market, variant, mode), df in sorted(results.items()):
        cfg = MARKETS[market]
        lines.extend([f'### {cfg["label"]} - {variant_title(variant)} - {mode}', ''])
        if df.empty:
            lines.append('No trades.')
            continue
        work = df.copy()
        work['Year'] = pd.to_datetime(work['Entry_Time'], utc=True).dt.year
        lines.extend(['| Year | Trades | Net pts | Net USD | Wins | Losses | Avg MAE pts | Max MAE pts |', '|---:|---:|---:|---:|---:|---:|---:|---:|'])
        for year, row in work.groupby('Year').agg(
            trades=('Trade_PL', 'size'),
            net=('Trade_PL', 'sum'),
            wins=('Trade_PL', lambda x: int((x > 0).sum())),
            losses=('Trade_PL', lambda x: int((x < 0).sum())),
            avg_mae=('MAE_Price_Pts', 'mean'),
            max_mae=('MAE_Price_Pts', 'max'),
        ).iterrows():
            lines.append(
                f"| {year} | {int(row['trades'])} | {row['net']:,.1f} | {fmt_money(float(row['net']) * cfg['point_value'])} | "
                f"{int(row['wins'])} | {int(row['losses'])} | {row['avg_mae']:.1f} | {row['max_mae']:.1f} |"
            )
        lines.append('')

    lines.extend(['## Cluster Events', ''])
    for (market, variant, mode), events in sorted(events_by_run.items()):
        cfg = MARKETS[market]
        lines.extend([f'### {cfg["label"]} - {variant_title(variant)} - {mode}', ''])
        if events.empty:
            lines.append('No events.')
            continue
        for event, count in events['Event'].value_counts().items():
            lines.append(f'- {event}: **{count}**')
        lines.append('')

    lines.extend(
        [
            '## Outputs',
            '',
        ]
    )
    for path in output_paths:
        lines.append(f'- `{path.relative_to(ROOT)}`')
    for path in chart_indexes:
        rel = Path(os.path.relpath(path, report.parent)).as_posix()
        lines.append(f'- [{path.parent.name}]({rel})')
    lines.extend(
        [
            '',
            'Hardening note: this is still built from the existing daily first-three-row monthly OR definition. Before live use, the OR calendar/session definition should be made explicit exactly as noted in the restricted-cycle hardening notes.',
        ]
    )
    report_text = '\n'.join(lines) + '\n'
    report.write_text(report_text)
    for mirror_market in ('nq',):
        mirror_root = MARKETS[mirror_market]['root'] / 'case_studies' / 'monthly_orb' / 'overlap_range_breakout_4h_causal'
        mirror_root.mkdir(parents=True, exist_ok=True)
        (mirror_root / 'README.md').write_text(report_text)
    return report


def run_market(
    market: str,
    variants: Iterable[str],
    modes: Iterable[str],
    max_concurrent_values: Iterable[int],
    rebuild_4h_cache: bool,
    charts: bool,
    include_no_trade_charts: bool,
    sides: Iterable[str],
    trend_filter: str,
    supertrend_scalein_contracts: int,
    supertrend_retest_contracts: int,
) -> tuple[dict[tuple[str, str, str], pd.DataFrame], dict[tuple[str, str, str], pd.DataFrame], list[Path], list[Path]]:
    cfg = MARKETS[market]
    daily = load_daily(cfg['daily'])
    bars4h = load_or_build_4h(cfg, rebuild_4h_cache)
    out_root = cfg['root'] / 'case_studies' / 'monthly_orb' / 'overlap_range_breakout_4h_causal'
    out_root.mkdir(parents=True, exist_ok=True)
    results: dict[tuple[str, str, str], pd.DataFrame] = {}
    events_by_run: dict[tuple[str, str, str], pd.DataFrame] = {}
    output_paths: list[Path] = []
    chart_indexes: list[Path] = []
    for max_concurrent in max_concurrent_values:
        for variant in variants:
            run_variant_core = make_run_variant(variant, max_concurrent)
            run_variant_core = apply_trend_filter_suffix(run_variant_core, trend_filter)
            run_variant_core = apply_scalein_suffix(run_variant_core, supertrend_scalein_contracts)
            run_variant_core = apply_retest_suffix(run_variant_core, supertrend_retest_contracts)
            for side in sides:
                if side == 'short' and variant != 'breakout_only':
                    continue
                run_variant = f'{run_variant_core}_short' if side == 'short' else run_variant_core
                for mode in modes:
                    trades, events = simulate(
                        daily,
                        bars4h,
                        market,
                        mode,
                        same_bar_priority='breakout',
                        variant=variant,
                        max_concurrent_trades=max_concurrent,
                        side=side,
                        trend_filter=trend_filter,
                        supertrend_scalein_contracts=supertrend_scalein_contracts,
                        supertrend_retest_contracts=supertrend_retest_contracts,
                    )
                    if not trades.empty:
                        trades.insert(1, 'Run_Variant', run_variant)
                        trades.insert(2, 'Max_Concurrent_Trades', max_concurrent)
                    if not events.empty:
                        events.insert(1, 'Run_Variant', run_variant)
                        events.insert(2, 'Max_Concurrent_Trades', max_concurrent)
                    label = variant_file_label(run_variant)
                    trades_out = out_root / f'{market}_overlap_range_breakout_4h_causal_{label}_{mode}.csv'
                    events_out = out_root / f'{market}_overlap_range_breakout_4h_causal_{label}_{mode}_events.csv'
                    trades.to_csv(trades_out, index=False)
                    events.to_csv(events_out, index=False)
                    output_paths.extend([trades_out, events_out])
                    results[(market, run_variant, mode)] = trades
                    events_by_run[(market, run_variant, mode)] = events
                    print(f'Wrote {trades_out} ({len(trades)} rows)')
                    print(f'Wrote {events_out} ({len(events)} rows)')
                    if charts and variant == 'breakout_only':
                        chart_root = out_root / f'charts_{market}_{label}_{mode}'
                        chart_index = build_cluster_charts(
                            cfg['label'],
                            daily,
                            bars4h,
                            trades,
                            mode,
                            run_variant,
                            chart_root,
                            include_no_trade_charts,
                        )
                        chart_indexes.append(chart_index)
                        print(f'Wrote charts {chart_index}')
    return results, events_by_run, output_paths, chart_indexes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--exit-fill-mode', choices=['close', 'next_open', 'both'], default='both')
    ap.add_argument('--variant', choices=['full_cycle', 'breakout_only', 'both'], default='both')
    ap.add_argument('--max-concurrent-trades', default='1', help='Comma-separated max live packages, e.g. 1 or 1,2.')
    ap.add_argument(
        '--trend-filter',
        choices=['none', 'daily-supertrend'],
        default='none',
        help='Optional causal breakout filter. daily-supertrend allows longs only when prior confirmed daily Supertrend is bullish.',
    )
    ap.add_argument(
        '--supertrend-scalein-contracts',
        type=int,
        default=0,
        help='Risk-on long-only add: after a confirmed daily Supertrend bearish flip during an open runner, add this many contracts on a 4h close back over that bearish stop.',
    )
    ap.add_argument(
        '--supertrend-retest-contracts',
        type=int,
        default=0,
        help='Risk-on long-only add: while an original runner is open, buy this many contracts on a retest of the confirmed daily Supertrend stop.',
    )
    ap.add_argument('--rebuild-4h-cache', action='store_true')
    ap.add_argument('--charts', action='store_true', help='Generate breakout-only 4h cluster charts.')
    ap.add_argument('--include-no-trade-charts', action='store_true', help='When charting, include overlap clusters with no filled package.')
    ap.add_argument(
        '--side',
        choices=['long', 'short', 'both'],
        default='long',
        help='Long buy-stop at range high (default). Short sell-stop at range low (breakout_only only); both writes separate *_short outputs.',
    )
    args = ap.parse_args()

    if args.side == 'short' and args.variant == 'full_cycle':
        ap.error('--side short requires --variant breakout_only (or both, which runs short only on breakout_only).')

    modes = ['close', 'next_open'] if args.exit_fill_mode == 'both' else [args.exit_fill_mode]
    variants = ['full_cycle', 'breakout_only'] if args.variant == 'both' else [args.variant]
    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    max_concurrent_values = parse_max_concurrent_values(args.max_concurrent_trades)
    sides = parse_sides(args.side)
    trend_filter = 'daily_supertrend' if args.trend_filter == 'daily-supertrend' else 'none'
    if args.supertrend_scalein_contracts < 0:
        ap.error('--supertrend-scalein-contracts must be >= 0.')
    if args.supertrend_retest_contracts < 0:
        ap.error('--supertrend-retest-contracts must be >= 0.')
    if args.supertrend_scalein_contracts > 0 and 'short' in sides:
        ap.error('--supertrend-scalein-contracts is implemented for long-side runs only.')
    if args.supertrend_retest_contracts > 0 and 'short' in sides:
        ap.error('--supertrend-retest-contracts is implemented for long-side runs only.')
    if args.supertrend_scalein_contracts > 0 and args.supertrend_retest_contracts > 0:
        ap.error('Run --supertrend-scalein-contracts and --supertrend-retest-contracts separately.')
    all_results: dict[tuple[str, str, str], pd.DataFrame] = {}
    all_events: dict[tuple[str, str, str], pd.DataFrame] = {}
    output_paths: list[Path] = []
    chart_indexes: list[Path] = []
    for market in markets:
        results, events, paths, charts = run_market(
            market,
            variants,
            modes,
            max_concurrent_values,
            args.rebuild_4h_cache,
            args.charts,
            args.include_no_trade_charts,
            sides,
            trend_filter,
            args.supertrend_scalein_contracts,
            args.supertrend_retest_contracts,
        )
        all_results.update(results)
        all_events.update(events)
        output_paths.extend(paths)
        chart_indexes.extend(charts)

    report = write_report(all_results, all_events, output_paths, chart_indexes)
    print(f'Wrote {report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
