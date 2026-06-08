#!/usr/bin/env python3
"""Monthly ORB restricted stop/limit cycle study.

This is a daily-OHLC research pass for a long-only monthly opening-range idea:

- Monthly OR = first three daily rows of the calendar month.
- After the OR forms, a buy stop at the OR high tries to catch an expanding
  breakout candle.
- If the stop fills but that daily candle closes more than 25% back inside the
  OR, the package is closed at the daily close and the stop is re-armed.
- If a confirmed breakout package closes more than 25% back inside the OR
  before TP1, it is closed and the engine arms a buy limit at the OR low.
- After a TP1 success, the engine arms a 2-contract buy limit refill at the OR
  high for a retest. This refill can fill while an earlier runner is still open.
- Primary breakout and bottom-limit packages are 3 contracts. Top-boundary
  refills are 2 contracts with no runner.
- Once TP1 arms a top-boundary refill, fresh stop-breakout orders are suppressed
  until the refill path resolves.
- After a failed breakout before TP1, the bottom-limit reclaim becomes
  available, but fresh stop-breakouts are still allowed before the bottom limit
  fills.

Daily OHLC limitation:
The simulator cannot know exact intraday ordering. It uses conservative-ish
rules: bottom-limit stops are daily-close stops, while breakout/top-limit
packages can scale out on a bar that traded far enough after entry. False
stop-entry breakout candles are closed at the same daily close without credit
for same-day target touches.
"""
from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MARKETS = {
    'mnq': {'root': ROOT / 'mnq', 'daily': ROOT / 'mnq' / 'mnq_daily.csv', 'point_value': 2.0, 'label': 'MNQ'},
    'nq': {'root': ROOT / 'nq', 'daily': ROOT / 'nq' / 'nq_daily.csv', 'point_value': 20.0, 'label': 'NQ'},
}
BACK_IN_RANGE_STOP_FRACTION = 0.25


@dataclass
class UnitExit:
    unit: int
    date: object
    price: float
    reason: str
    pl: float


@dataclass
class Package:
    market: str
    period: str
    entry_kind: str
    entry_date: object
    entry: float
    range_high: float
    range_low: float
    range_size: float
    tp50: float
    tp1: float
    tp2: float | None
    stop: float | None
    symbol: str
    exits: list[UnitExit] = field(default_factory=list)
    tp1_hit: bool = False
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    open_at_end: bool = False
    false_breakout: bool = False
    units: int = 3

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [u for u in range(1, self.units + 1) if u not in closed]

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
        for ex in sorted(self.exits, key=lambda x: (pd.Timestamp(x.date), x.unit)):
            if ex.reason not in reasons:
                reasons.append(ex.reason)
        return '+'.join(reasons) if reasons else 'Open'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def unit_pl(entry: float, exit_price: float) -> float:
    return float(exit_price - entry)


def close_unit(pkg: Package, unit: int, date: object, price: float, reason: str) -> None:
    if unit in pkg.open_units:
        pkg.exits.append(UnitExit(unit, date, float(price), reason, unit_pl(pkg.entry, float(price))))


def close_open(pkg: Package, date: object, price: float, reason: str) -> None:
    for unit in list(pkg.open_units):
        close_unit(pkg, unit, date, price, reason)


def update_excursion(pkg: Package, high: float, low: float) -> None:
    pkg.mae_pts = max(pkg.mae_pts, max(0.0, pkg.entry - low))
    pkg.mfe_pts = max(pkg.mfe_pts, max(0.0, high - pkg.entry))


def close_inside(close_px: float, rh: float, rl: float) -> bool:
    return rl <= close_px <= rh


def breakout_close_stop(rh: float, rl: float) -> float:
    return rh - BACK_IN_RANGE_STOP_FRACTION * (rh - rl)


def breakout_close_violation(close_px: float, rh: float, rl: float) -> bool:
    return close_px <= breakout_close_stop(rh, rl)


def is_failed_breakout_before_tp1(reason: str) -> bool:
    return reason in {
        'Daily-Close-25pct-Back-In-Range-Before-TP1',
        'Daily-Close-Back-In-Range-Before-TP1',
        'Daily-Close-At-Or-Below-Range-High-Before-TP1',
    }


def make_package(market: str, period: str, kind: str, row: pd.Series, entry: float, rh: float, rl: float, rv: float) -> Package:
    tp1 = rh + rv
    if kind == 'Bottom-Limit':
        tp50 = rh
        tp2 = None
        stop = rl - 0.25 * rv
        units = 3
    elif kind == 'Top-Refill':
        tp50 = entry + (tp1 - entry) * 0.5
        tp2 = None
        stop = None
        units = 2
    else:
        tp50 = entry + (tp1 - entry) * 0.5
        tp2 = entry + 2.0 * (tp1 - entry)
        stop = None
        units = 3
    return Package(
        market=market.upper(),
        period=period,
        entry_kind=kind,
        entry_date=row['date'],
        entry=float(entry),
        range_high=float(rh),
        range_low=float(rl),
        range_size=float(rv),
        tp50=float(tp50),
        tp1=float(tp1),
        tp2=float(tp2) if tp2 is not None else None,
        stop=float(stop) if stop is not None else None,
        symbol=str(row.get('symbol', '')),
        units=units,
    )


def process_top_style(pkg: Package, row: pd.Series) -> tuple[bool, bool]:
    """Process stop-breakout packages. Return ``(flat, newly_hit_tp1)``."""
    d = row['date']
    high = float(row['high'])
    close_px = float(row['close'])
    update_excursion(pkg, high, float(row['low']))
    newly_hit_tp1 = False

    # Unit 1 takes half-way to TP1. Unit 2 exits at TP1. Unit 3 is the 2R runner.
    if 1 in pkg.open_units and high >= pkg.tp50:
        close_unit(pkg, 1, d, pkg.tp50, 'TP50')
    if not pkg.tp1_hit and high >= pkg.tp1:
        close_unit(pkg, 2, d, pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True

    if pkg.tp1_hit and 3 in pkg.open_units:
        assert pkg.tp2 is not None
        if high >= pkg.tp2:
            close_unit(pkg, 3, d, pkg.tp2, 'TP2')
            return True, newly_hit_tp1
        if breakout_close_violation(close_px, pkg.range_high, pkg.range_low):
            close_unit(pkg, 3, d, close_px, 'Daily-Close-25pct-Back-In-Range-After-TP1')
            return True, newly_hit_tp1
    elif not pkg.tp1_hit and breakout_close_violation(close_px, pkg.range_high, pkg.range_low):
        close_open(pkg, d, close_px, 'Daily-Close-25pct-Back-In-Range-Before-TP1')
        return True, newly_hit_tp1

    return not pkg.open_units, newly_hit_tp1


def process_refill_style(pkg: Package, row: pd.Series) -> tuple[bool, bool]:
    """Process a 2-contract top-boundary refill. Return ``(flat, newly_hit_tp1)``."""
    d = row['date']
    high = float(row['high'])
    close_px = float(row['close'])
    update_excursion(pkg, high, float(row['low']))
    newly_hit_tp1 = False

    if 1 in pkg.open_units and high >= pkg.tp50:
        close_unit(pkg, 1, d, pkg.tp50, 'TP50')
    if not pkg.tp1_hit and high >= pkg.tp1:
        close_unit(pkg, 2, d, pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True
        return True, newly_hit_tp1
    if not pkg.tp1_hit and close_px <= pkg.range_high:
        close_open(pkg, d, close_px, 'Daily-Close-At-Or-Below-Range-High-Before-TP1')
        return True, newly_hit_tp1

    return not pkg.open_units, newly_hit_tp1


def process_bottom_style(pkg: Package, row: pd.Series) -> tuple[bool, bool]:
    """Process bottom-range limit package. Return ``(flat, newly_hit_tp1)``."""
    d = row['date']
    high = float(row['high'])
    low = float(row['low'])
    close_px = float(row['close'])
    update_excursion(pkg, high, low)
    newly_hit_tp1 = False

    assert pkg.stop is not None

    if 1 in pkg.open_units and high >= pkg.tp50:
        close_unit(pkg, 1, d, pkg.tp50, 'Top-Boundary')
    if high >= pkg.tp1:
        close_unit(pkg, 2, d, pkg.tp1, 'TP1')
        close_unit(pkg, 3, d, pkg.tp1, 'TP1')
        pkg.tp1_hit = True
        newly_hit_tp1 = True
        return True, newly_hit_tp1

    if close_px <= pkg.stop:
        close_open(pkg, d, close_px, 'Bottom-Limit-Daily-Close-SL')
        return True, newly_hit_tp1

    return not pkg.open_units, newly_hit_tp1


def finalize_package(pkg: Package, row: pd.Series) -> None:
    if pkg.open_units:
        close_open(pkg, row['date'], float(row['close']), 'Period-Close')
        pkg.open_at_end = True


def package_to_row(pkg: Package) -> dict:
    exits = sorted(pkg.exits, key=lambda ex: (pd.Timestamp(ex.date), ex.unit))
    return {
        'Market': pkg.market,
        'Period': pkg.period,
        'Entry_Kind': pkg.entry_kind,
        'Entry_Date': pkg.entry_date,
        'Entry_Price': pkg.entry,
        'Range_High': pkg.range_high,
        'Range_Low': pkg.range_low,
        'Range': pkg.range_size,
        'TP50': pkg.tp50,
        'TP1': pkg.tp1,
        'TP2': pkg.tp2,
        'Stop': pkg.stop,
        'Exit_Date': exits[-1].date if exits else None,
        'Exit_Price': exits[-1].price if exits else None,
        'Exit_Reason': pkg.final_reason,
        'Trade_PL': round(pkg.net_points, 6),
        'Result': pkg.result,
        'MAE_Price_Pts': round(pkg.mae_pts, 6),
        'MFE_Price_Pts': round(pkg.mfe_pts, 6),
        'Open_At_End': pkg.open_at_end,
        'False_Breakout': pkg.false_breakout,
        'Units': pkg.units,
        'Unit_Exits': ';'.join(f'U{ex.unit}:{ex.date}:{ex.price:.2f}:{ex.reason}:{ex.pl:.2f}' for ex in exits),
        'Symbol': pkg.symbol,
    }


def simulate_month(market: str, period: str, month: pd.DataFrame) -> tuple[list[Package], list[dict]]:
    rb = month.iloc[:3]
    rh = float(rb['high'].max())
    rl = float(rb['low'].min())
    rv = rh - rl
    events: list[dict] = []
    trades: list[Package] = []
    if rv <= 0:
        return trades, [{'Period': period, 'Event': 'skip', 'Reason': 'invalid_range'}]

    pending = 'Stop'
    pending_refill = False
    active: list[Package] = []

    for idx in range(3, len(month)):
        row = month.iloc[idx]
        d = row['date']
        high = float(row['high'])
        low = float(row['low'])
        close_px = float(row['close'])

        # Refill orders are independent 2-contract packages. They can fill
        # while a prior TP1 runner remains open.
        has_active_refill = any(pkg.entry_kind == 'Top-Refill' for pkg in active)
        if pending_refill and not has_active_refill and low <= rh:
            refill = make_package(market, period, 'Top-Refill', row, rh, rh, rl, rv)
            active.append(refill)
            pending_refill = False
            events.append({'Period': period, 'Date': d, 'Event': 'fill_top_refill', 'Price': rh})

        # Primary stop/bottom entries remain mutually exclusive and only start
        # when no package is live. After a failed breakout, the bottom limit is
        # available but not exclusive: a fresh upside breakout can still fire
        # before the bottom limit is touched.
        if not active and not pending_refill:
            if pending == 'Bottom-Limit' and high >= rh:
                pkg = make_package(market, period, 'Stop-Breakout', row, rh, rh, rl, rv)
                events.append({'Period': period, 'Date': d, 'Event': 'fill_stop_from_bottom_state', 'Price': rh, 'Close': close_px})
                if breakout_close_violation(close_px, rh, rl):
                    pkg.false_breakout = True
                    close_open(pkg, d, close_px, 'False-Breakout-Close-25pct-Inside')
                    trades.append(pkg)
                    pending = 'Bottom-Limit'
                else:
                    active.append(pkg)
            elif pending == 'Bottom-Limit' and low <= rl:
                pkg = make_package(market, period, 'Bottom-Limit', row, rl, rh, rl, rv)
                active.append(pkg)
                events.append({'Period': period, 'Date': d, 'Event': 'fill_bottom_limit', 'Price': rl})
            elif pending == 'Stop' and high >= rh:
                pkg = make_package(market, period, 'Stop-Breakout', row, rh, rh, rl, rv)
                events.append({'Period': period, 'Date': d, 'Event': 'fill_stop', 'Price': rh, 'Close': close_px})
                if breakout_close_violation(close_px, rh, rl):
                    pkg.false_breakout = True
                    close_open(pkg, d, close_px, 'False-Breakout-Close-25pct-Inside')
                    trades.append(pkg)
                    pending = 'Stop'
                else:
                    active.append(pkg)

        for pkg in list(active):
            if pkg.entry_kind == 'Bottom-Limit':
                flat, tp1_new = process_bottom_style(pkg, row)
            elif pkg.entry_kind == 'Top-Refill':
                flat, tp1_new = process_refill_style(pkg, row)
            else:
                flat, tp1_new = process_top_style(pkg, row)

            if tp1_new:
                pending_refill = True
                events.append({'Period': period, 'Date': d, 'Event': 'arm_top_refill', 'Source': pkg.entry_kind, 'Price': rh})

            if flat:
                trades.append(pkg)
                active.remove(pkg)

                if pkg.entry_kind == 'Top-Refill':
                    if not active and not pending_refill and is_failed_breakout_before_tp1(pkg.final_reason):
                        pending = 'Bottom-Limit'
                    continue

                if pkg.tp1_hit:
                    pending_refill = True
                elif is_failed_breakout_before_tp1(pkg.final_reason):
                    pending = 'Bottom-Limit'
                else:
                    pending = 'Stop'

    for pkg in active:
        finalize_package(pkg, month.iloc[-1])
        trades.append(pkg)

    return trades, events


def simulate(daily: pd.DataFrame, market: str, allow_short: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    if allow_short:
        raise NotImplementedError('Short-side simulation flag is reserved but intentionally not implemented yet.')

    packages: list[Package] = []
    events: list[dict] = []
    for period, month in period_groups(daily):
        trades, month_events = simulate_month(market, period, month)
        packages.extend(trades)
        events.extend(month_events)
    out = pd.DataFrame([package_to_row(pkg) for pkg in packages])
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum()
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
            'trades': 0,
            'net_pts': 0.0,
            'net_usd': 0.0,
            'dd_usd': 0.0,
            'win_rate': 0.0,
            'pf': math.nan,
            'avg_mae': math.nan,
            'max_mae': math.nan,
        }
    pnl = pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0)
    mae = pd.to_numeric(df['MAE_Price_Pts'], errors='coerce')
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_usd': float(max_drawdown(pnl) * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'avg_mae': float(mae.mean()),
        'max_mae': float(mae.max()),
    }


def fmt_money(value: float) -> str:
    return f'${value:,.0f}'


def fmt_num(value: float, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.{digits}f}'


def fmt_pct(value: float) -> str:
    return f'{value:.1%}'


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xnums = mdates.date2num(pd.to_datetime(bars['date']).dt.to_pydatetime())
    width = 0.62
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.75, alpha=0.88, zorder=2)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.86,
                zorder=3,
            )
        )


def _kind_code(kind: str) -> str:
    return {
        'Stop-Breakout': 'SB',
        'Top-Refill': 'TR',
        'Bottom-Limit': 'BL',
    }.get(kind, kind[:2].upper())


def chart_trades(daily: pd.DataFrame, trades: pd.DataFrame, out_root: Path, label: str, point_value: float) -> None:
    if trades.empty:
        return
    chart_root = out_root / 'restricted_stop_limit_cycle'
    if chart_root.exists():
        shutil.rmtree(chart_root)
    chart_root.mkdir(parents=True, exist_ok=True)

    work = daily.copy()
    work['Period'] = pd.to_datetime(work['date']).dt.to_period('M').astype(str)

    index_lines = [f'# {label} restricted stop-limit cycle charts', '']
    year_rows: dict[int, list[dict]] = {}

    for period, period_trades in trades.groupby('Period', sort=True):
        period_trades = period_trades.sort_values(['Entry_Date', 'Exit_Date', 'Entry_Kind']).reset_index(drop=True)
        bars = work[work['Period'] == period].copy().reset_index(drop=True)
        if bars.empty:
            continue
        year = int(str(period).split('-')[0])
        year_dir = chart_root / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        fig = plt.figure(figsize=(14, 7), facecolor='#111827')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0D1B2A')
        draw_candles(ax, bars)

        dates = pd.to_datetime(bars['date'])
        x0 = dates.iloc[0]
        x1 = dates.iloc[-1]
        rb = bars.iloc[:3]
        range_start = pd.Timestamp(rb.iloc[0]['date'])
        range_end = pd.Timestamp(rb.iloc[-1]['date']) + pd.Timedelta(days=1)
        rh = float(period_trades.iloc[0]['Range_High'])
        rl = float(period_trades.iloc[0]['Range_Low'])
        rv = rh - rl
        tp50 = rh + 0.5 * rv
        tp1 = rh + rv
        tp2 = rh + 2.0 * rv
        breakout_stop = breakout_close_stop(rh, rl)
        bottom_stop = rl - 0.25 * rv

        ax.axvspan(range_start, range_end, color='#1F4E79', alpha=0.30, zorder=0)
        ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(breakout_stop, color='#FFB74D', linestyle=':', linewidth=0.8, alpha=0.60, zorder=2)
        ax.axhline(tp50, color='#FFD54F', linestyle=':', linewidth=0.8, alpha=0.75, zorder=2)
        ax.axhline(tp1, color='#76FF03', linestyle='--', linewidth=0.9, alpha=0.70, zorder=2)
        ax.axhline(tp2, color='#64DD17', linestyle='--', linewidth=0.8, alpha=0.45, zorder=2)
        ax.axhline(bottom_stop, color='#FF8A65', linestyle=':', linewidth=0.8, alpha=0.65, zorder=2)

        total_pl = float(period_trades['Trade_PL'].sum())
        pattern_parts: list[str] = []
        label_offsets = [24, -36, 48, -60, 72, -84]
        marker_for = {'Stop-Breakout': '^', 'Top-Refill': 'o', 'Bottom-Limit': 'D'}
        color_for = {'Stop-Breakout': '#00E676', 'Top-Refill': '#40C4FF', 'Bottom-Limit': '#FFC107'}
        result_color = {'Win': '#76FF03', 'Loss': '#FF1744', 'Scratch': '#FFB74D'}

        for i, (_, tr) in enumerate(period_trades.iterrows(), 1):
            entry_x = pd.Timestamp(tr['Entry_Date'])
            exit_x = pd.Timestamp(tr['Exit_Date'])
            entry_y = float(tr['Entry_Price'])
            exit_y = float(tr['Exit_Price'])
            kind = str(tr['Entry_Kind'])
            code = _kind_code(kind)
            result = str(tr['Result'])
            pl = float(tr['Trade_PL'])
            pattern_parts.append(f'{code}-{result[0]}')

            ax.scatter(
                [entry_x],
                [entry_y],
                marker=marker_for.get(kind, '^'),
                color=color_for.get(kind, '#00E676'),
                s=105,
                zorder=10,
                edgecolor='black',
                linewidth=1.0,
            )
            ax.annotate(
                f'#{i} {code} @ {entry_y:.0f}',
                xy=(entry_x, entry_y),
                xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=color_for.get(kind, '#00E676'),
                fontsize=7,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=color_for.get(kind, '#00E676'), alpha=0.94),
            )
            ax.scatter(
                [exit_x],
                [exit_y],
                marker='X',
                color=result_color.get(result, '#FFB74D'),
                s=110,
                zorder=10,
                edgecolor='black',
                linewidth=1.0,
            )
            ax.annotate(
                f'#{i} {result[0]} {pl:+.0f}pt',
                xy=(exit_x, exit_y),
                xytext=(8, -label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=result_color.get(result, '#FFB74D'),
                fontsize=7,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=result_color.get(result, '#FFB74D'), alpha=0.94),
            )

        last_x = mdates.date2num(dates.iloc[-1]) + 0.35
        ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=7, va='center')
        ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=7, va='center')
        ax.text(last_x, breakout_stop, f' 25% close {breakout_stop:.1f}', color='#FFB74D', fontsize=7, va='center')
        ax.text(last_x, tp1, f' TP1 {tp1:.1f}', color='#76FF03', fontsize=7, va='center')
        ax.text(last_x, tp2, f' TP2 {tp2:.1f}', color='#64DD17', fontsize=7, va='center')

        sym = str(bars.iloc[0].get('symbol', ''))
        pattern = '+'.join(pattern_parts)
        ax.set_title(
            f'{period}  {label} restricted stop-limit cycle  ·  {sym}  ·  '
            f'Range {rv:.1f}  ·  {pattern}  ·  {total_pl:+.1f}pt (${total_pl * point_value:+.0f})',
            color='white',
            fontsize=9,
            fontweight='bold',
            loc='left',
            pad=8,
        )
        ax.tick_params(colors='#9FB3C8', labelsize=7)
        for spine in ax.spines.values():
            spine.set_color('#3A506B')
        ax.grid(True, alpha=0.15, color='#9FB3C8')
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=2))
        fig.autofmt_xdate()
        fig.tight_layout()
        path = year_dir / f'{period}.png'
        fig.savefig(path, dpi=140)
        plt.close(fig)

        year_rows.setdefault(year, []).append(
            {
                'Period': period,
                'Symbol': sym,
                'Range': rv,
                'Pattern': pattern,
                'Packages': len(period_trades),
                'Net': total_pl,
                'Chart': f'{period}.png',
            }
        )

    for year in sorted(year_rows):
        rows = year_rows[year]
        year_net = sum(r['Net'] for r in rows)
        year_dir = chart_root / str(year)
        lines = [
            f'# {year} {label} restricted stop-limit cycle charts',
            '',
            f"Periods: {len(rows)}  ·  Net: {year_net:+.2f} pts (${year_net * point_value:+,.0f})",
            '',
            '| Period | Symbol | Range | Pattern | Packages | Net pts | Chart |',
            '|---|---|---:|---|---:|---:|---|',
        ]
        for r in rows:
            lines.append(
                f"| {r['Period']} | {r['Symbol']} | {r['Range']:.2f} | {r['Pattern']} | "
                f"{r['Packages']} | {r['Net']:+.2f} | [{r['Chart']}]({r['Chart']}) |"
            )
        (year_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n')
        index_lines.append(f"- [{year}/]({year}/INDEX.md) — {len(rows)} periods, {year_net:+.1f} pts")

    (chart_root / 'INDEX.md').write_text('\n'.join(index_lines) + '\n')


def write_report(market: str, label: str, root: Path, trades: pd.DataFrame, events: pd.DataFrame, point_value: float) -> Path:
    case_root = root / 'case_studies' / 'monthly_orb'
    case_root.mkdir(parents=True, exist_ok=True)
    report = case_root / 'MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md'
    s = stats(trades, point_value)
    lines = [
        f'# {label} Monthly ORB Restricted Stop-Limit Cycle',
        '',
        'Rules modeled:',
        '',
        '- Long only. `--allow-short` exists as a reserved flag but raises `NotImplementedError`.',
        '- Monthly OR = first 3 daily rows of each calendar month.',
        '- Primary order = buy stop at the OR high after the OR forms.',
        '- If the stop fills but the same daily candle closes more than 25% back inside the OR, close all 3 contracts at that close and re-arm the stop.',
        '- Confirmed breakout packages use 3 contracts: 1 off halfway to TP1, 1 off at TP1, 1 runner at TP2.',
        '- If a confirmed breakout package closes more than 25% back inside the OR before TP1, close all at the daily close and arm a bottom-boundary limit.',
        '- Top-boundary refill packages still close before TP1 on any daily close at or below the OR high.',
        '- After any TP1 success, arm a 2-contract top-boundary refill at the OR high, even if an earlier runner is still open.',
        '- Top-boundary refills take 1 off halfway to TP1 and 1 off at TP1; they do not leave a runner.',
        '- Bottom-boundary limit enters at the OR low, exits only on a daily close below `OR low - 0.25 * range`, takes 1 off at the OR high, and takes the other 2 off at TP1.',
        '- After a failed breakout before TP1, the bottom-boundary limit becomes available, but a fresh stop-breakout can still fire before that bottom limit fills.',
        '- Primary 3-contract packages remain mutually exclusive. A 2-contract top-boundary refill may overlap with an earlier runner.',
        '',
        'Daily OHLC caveat: this cannot prove intraday ordering. The report uses the same daily data family as the older monthly restricted studies.',
        '',
        f'Dollar figures use {label} point value of ${point_value:g}/point per contract.',
        '',
        '## Summary',
        '',
        '| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|',
        f"| {s['trades']} | {fmt_num(s['net_pts'])} | {fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'], 2)} | {fmt_num(s['avg_mae'])} | {fmt_num(s['max_mae'])} |",
        '',
        '## Entry Type Split',
        '',
    ]
    if trades.empty:
        lines.append('No trades.')
    else:
        split = trades.groupby('Entry_Kind').apply(lambda x: pd.Series(stats(x, point_value))).reset_index()
        lines.extend(['| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |', '|---|---:|---:|---:|---:|---:|---:|'])
        for _, row in split.iterrows():
            lines.append(
                f"| {row['Entry_Kind']} | {int(row['trades'])} | {fmt_num(row['net_pts'])} | "
                f"{fmt_money(row['net_usd'])} | {fmt_money(row['dd_usd'])} | {fmt_pct(row['win_rate'])} | {fmt_num(row['pf'], 2)} |"
            )
    lines.extend(['', '## Exit Mix', ''])
    if trades.empty:
        lines.append('No trades.')
    else:
        for reason, count in trades['Exit_Reason'].value_counts().items():
            lines.append(f'- {reason}: **{count}**')
    lines.extend(['', '## Yearly Split', ''])
    if trades.empty:
        lines.append('No trades.')
    else:
        work = trades.copy()
        work['Year'] = pd.to_datetime(work['Entry_Date']).dt.year
        lines.extend(['| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |', '|---:|---:|---:|---:|---:|---:|---:|'])
        for year, row in work.groupby('Year').agg(
            trades=('Trade_PL', 'size'),
            net=('Trade_PL', 'sum'),
            wins=('Trade_PL', lambda x: int((x > 0).sum())),
            losses=('Trade_PL', lambda x: int((x < 0).sum())),
            avg_mae=('MAE_Price_Pts', 'mean'),
            max_mae=('MAE_Price_Pts', 'max'),
        ).iterrows():
            lines.append(f"| {year} | {int(row['trades'])} | {row['net']:,.1f} | {int(row['wins'])} | {int(row['losses'])} | {row['avg_mae']:.1f} | {row['max_mae']:.1f} |")
    lines.extend(
        [
            '',
            '## Outputs',
            '',
            f'- `{market}/{market}_monthly_orb_restricted_stop_limit_cycle.csv`',
            f'- `{market}/{market}_monthly_orb_restricted_stop_limit_cycle_events.csv`',
            '- Charts: `case_studies/monthly_orb/restricted_stop_limit_cycle/INDEX.md`',
        ]
    )
    report.write_text('\n'.join(lines) + '\n')
    return report


def run_market(market: str, charts: bool, allow_short: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    cfg = MARKETS[market]
    daily = load_daily(cfg['daily'])
    trades, events = simulate(daily, market, allow_short=allow_short)
    out = cfg['root'] / f'{market}_monthly_orb_restricted_stop_limit_cycle.csv'
    events_out = cfg['root'] / f'{market}_monthly_orb_restricted_stop_limit_cycle_events.csv'
    trades.to_csv(out, index=False)
    events.to_csv(events_out, index=False)
    case_root = cfg['root'] / 'case_studies' / 'monthly_orb'
    if charts and not trades.empty:
        chart_trades(daily, trades, case_root, cfg['label'], cfg['point_value'])
    report = write_report(market, cfg['label'], cfg['root'], trades, events, cfg['point_value'])
    return trades, events, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--charts', action='store_true')
    ap.add_argument('--allow-short', action='store_true', help='Reserved flag; short side is intentionally not implemented.')
    args = ap.parse_args()

    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        trades, events, report = run_market(market, args.charts, allow_short=args.allow_short)
        print(f'Wrote {market}: {len(trades)} packages, {len(events)} events, report {report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
