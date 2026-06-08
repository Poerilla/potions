#!/usr/bin/env python3
"""Intraday validation for the monthly ORB inside-candle source-stop scaleout."""
from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import argparse
import math
import sys

import databento as db
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path('/home/tester/hsm/potions')
MNQ_ROOT = ROOT / 'mnq'
REPORT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'INTRADAY_VALIDATION_AND_BEST_VARIANT.md'
CHART_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'inside_source_stop_scaleout_2r_intraday'
RAW_1M = MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_PERIOD = 2


VARIANTS = [
    ('boundary-retest unrestricted', MNQ_ROOT / 'mnq_monthly_orb_boundary_retest.csv', 1, True),
    ('boundary-retest restricted', MNQ_ROOT / 'mnq_monthly_orb_boundary_retest_restricted.csv', 1, True),
    ('inside-candle-open unrestricted', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open.csv', 1, True),
    ('inside-candle-open restricted', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_restricted.csv', 1, True),
    ('inside-candle-open unrestricted source-stop', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_source_stop.csv', 1, True),
    ('inside-candle-open restricted source-stop', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_restricted_source_stop.csv', 1, True),
    ('inside source-stop scaleout 2R unrestricted', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_source_stop_scaleout_2r.csv', 2, True),
    ('inside source-stop scaleout 3R unrestricted', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_source_stop_scaleout_3r.csv', 2, True),
    ('inside source-stop scaleout 2R restricted', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_2r.csv', 2, True),
    ('inside source-stop scaleout 3R restricted', MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_3r.csv', 2, True),
    ('close-entry unrestricted', MNQ_ROOT / 'mnq_monthly_orb_close_entry.csv', 1, True),
    ('close-entry restricted', MNQ_ROOT / 'mnq_monthly_orb_close_entry_restricted.csv', 1, True),
    ('close-entry unrestricted breakout-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_breakout_stop.csv', 1, True),
    ('close-entry restricted breakout-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_restricted_breakout_stop.csv', 1, True),
    ('close-entry unrestricted 2x-breakout-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_2x_breakout_stop.csv', 1, True),
    ('close-entry restricted 2x-breakout-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_restricted_2x_breakout_stop.csv', 1, True),
    ('close-entry unrestricted boundary-candle-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_boundary_candle_stop.csv', 1, True),
    ('close-entry restricted boundary-candle-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_restricted_boundary_candle_stop.csv', 1, True),
    ('close-entry unrestricted near-boundary-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_near_boundary_stop.csv', 1, True),
    ('close-entry restricted near-boundary-stop', MNQ_ROOT / 'mnq_monthly_orb_close_entry_restricted_near_boundary_stop.csv', 1, True),
    ('original boundary-entry', MNQ_ROOT / 'mnq_monthly_orb.csv', 1, False),
    ('original boundary-entry restricted', MNQ_ROOT / 'mnq_monthly_orb_restricted.csv', 1, False),
]


def max_drawdown(values: Iterable[float]) -> float:
    series = pd.Series(list(values), dtype=float)
    if series.empty:
        return 0.0
    equity = series.cumsum()
    return float((equity - equity.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def fmt_money(v: float) -> str:
    return f'${v:,.2f}'


def fmt_num(v: float) -> str:
    if math.isnan(v):
        return 'n/a'
    if math.isinf(v):
        return 'inf'
    return f'{v:,.2f}'


def fmt_pct(v: float) -> str:
    return 'n/a' if math.isnan(v) else f'{v:.2%}'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def load_raw_1m(path: Path) -> pd.DataFrame:
    raw = db.DBNStore.from_file(str(path)).to_df().reset_index()
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True)
    raw['date'] = raw['ts_event'].dt.date
    return raw[['ts_event', 'date', 'symbol', 'open', 'high', 'low', 'close', 'volume']].sort_values('ts_event').reset_index(drop=True)


def period_rows(df: pd.DataFrame):
    work = df.copy()
    work['ym'] = work['date'].apply(lambda d: (d.year, d.month))
    periods: OrderedDict[tuple[int, int], list[pd.Series]] = OrderedDict()
    for _, row in work.iterrows():
        periods.setdefault(row['ym'], []).append(row)
    for (yr, mo), bars in periods.items():
        bars_df = pd.DataFrame(bars).reset_index(drop=True)
        if len(bars_df) >= 4:
            yield f'{yr}-{mo:02d}', bars_df


def is_inside_opposite(row, direction: str, range_high: float, range_low: float) -> bool:
    o = float(row['open'])
    h = float(row['high'])
    l = float(row['low'])
    c = float(row['close'])
    inside_range = h <= range_high and l >= range_low
    if direction == 'Long':
        return inside_range and c < o
    return inside_range and c > o


def inside_opposite_entry(history: list[pd.Series], direction: str, range_high: float, range_low: float) -> dict | None:
    prior = history[:-1]
    i = len(prior) - 1
    while i >= 0 and not is_inside_opposite(prior[i], direction, range_high, range_low):
        i -= 1
    if i < 0:
        return None

    run = []
    while i >= 0 and is_inside_opposite(prior[i], direction, range_high, range_low):
        run.append(prior[i])
        i -= 1

    if direction == 'Long':
        chosen = max(run, key=lambda row: float(row['open']))
    else:
        chosen = min(run, key=lambda row: float(row['open']))

    return {
        'price': float(chosen['open']),
        'date': chosen['date'],
        'start': run[-1]['date'],
        'end': run[0]['date'],
        'count': len(run),
        'open': float(chosen['open']),
        'high': float(chosen['high']),
        'low': float(chosen['low']),
        'close': float(chosen['close']),
        'run_high': max(float(row['high']) for row in run),
        'run_low': min(float(row['low']) for row in run),
    }


def summarize_csv(path: Path, units: int, causal: bool, multiplier: float = 2.0) -> dict | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if 'Trade_Direction' in df.columns:
        df = df[df['Trade_Direction'] != 'No-Op'].copy()
    if df.empty or 'Trade_PL' not in df.columns:
        return None
    pnl = df['Trade_PL'].astype(float)
    gross_usd = pnl * multiplier
    per_unit_usd = pnl / units * multiplier
    return {
        'variant': None,
        'path': path,
        'causal': causal,
        'units': units,
        'trades': int(len(df)),
        'net_usd': float(gross_usd.sum()),
        'dd_usd': max_drawdown(gross_usd),
        'net_per_unit_usd': float(per_unit_usd.sum()),
        'dd_per_unit_usd': max_drawdown(per_unit_usd),
        'win_rate': float((pnl > 0).mean()),
        'pf': profit_factor(pnl),
        'avg_trade_pts': float(pnl.mean()),
        'score': float(gross_usd.sum() / abs(max_drawdown(gross_usd))) if max_drawdown(gross_usd) < 0 else math.inf,
    }


def compare_variants() -> list[dict]:
    rows = []
    for label, path, units, causal in VARIANTS:
        row = summarize_csv(path, units, causal)
        if row is None:
            continue
        row['variant'] = label
        rows.append(row)
    return sorted(rows, key=lambda row: (row['causal'], row['pf'], row['score'], row['net_per_unit_usd']), reverse=True)


class IntradayMonth:
    def __init__(self, period: str, bars: pd.DataFrame, raw_grouped, restricted: bool, runner_r: float) -> None:
        self.period = period
        self.bars = bars
        self.raw_grouped = raw_grouped
        self.restricted = restricted
        self.runner_r = runner_r
        self.range_bars = bars.iloc[:3]
        self.trade_bars = bars.iloc[3:].reset_index(drop=True)
        self.range_high = float(self.range_bars['high'].max())
        self.range_low = float(self.range_bars['low'].min())
        self.range_val = self.range_high - self.range_low
        self.symbol = str(self.range_bars.iloc[0]['symbol'])
        self.history = [row for _, row in self.range_bars.iterrows()]
        self.trades: list[dict] = []
        self.reset_to_breakout()

    def reset_to_breakout(self) -> None:
        self.phase = WAIT_BREAKOUT
        self.direction = None
        self.limit_price = None
        self.stop = None
        self.risk = None
        self.first_target = None
        self.runner_target = None
        self.breakout_date = None
        self.order_live_date = None
        self.entry_time = None
        self.source = None
        self.partial_done = False
        self.partial_exit_time = None
        self.max_adverse_pts = 0.0
        self.be_active_next_minute = False
        self.just_filled = False

    def raw_for_day(self, d, symbol: str) -> pd.DataFrame:
        try:
            return self.raw_grouped.get_group((d, symbol)).sort_values('ts_event')
        except KeyError:
            return pd.DataFrame(columns=['ts_event', 'date', 'symbol', 'open', 'high', 'low', 'close', 'volume'])

    def valid_long_breakout(self, row) -> bool:
        return float(row['close']) > self.range_high and float(row['close']) > float(row['open'])

    def valid_short_breakout(self, row) -> bool:
        return float(row['close']) < self.range_low and float(row['close']) < float(row['open'])

    def arm_order(self, direction: str, bar) -> bool:
        found = inside_opposite_entry(self.history, direction, self.range_high, self.range_low)
        if found is None:
            return False
        entry = float(found['price'])
        if direction == 'Long':
            stop = float(found['run_low'])
            risk = entry - stop
            if risk <= 0:
                return False
            first = entry + risk
            runner = entry + self.runner_r * risk
        else:
            stop = float(found['run_high'])
            risk = stop - entry
            if risk <= 0:
                return False
            first = entry - risk
            runner = entry - self.runner_r * risk

        self.direction = direction
        self.limit_price = entry
        self.stop = stop
        self.risk = risk
        self.first_target = first
        self.runner_target = runner
        self.breakout_date = bar['date']
        self.order_live_date = bar['date'] + timedelta(days=1)
        self.source = found
        self.phase = WAIT_FILL
        return True

    def update_mae(self, h: float, l: float) -> None:
        assert self.direction is not None and self.limit_price is not None
        if self.direction == 'Long':
            self.max_adverse_pts = max(self.max_adverse_pts, max(0.0, self.limit_price - l))
        else:
            self.max_adverse_pts = max(self.max_adverse_pts, max(0.0, h - self.limit_price))

    def append_trade(self, exit_time, exit_reason: str, first_exit_reason: str, runner_exit_price: float, runner_exit_reason: str) -> None:
        assert self.direction is not None and self.limit_price is not None and self.stop is not None
        assert self.risk is not None and self.first_target is not None and self.runner_target is not None
        assert self.source is not None
        if self.direction == 'Long':
            first_pl = self.first_target - self.limit_price if self.partial_done else runner_exit_price - self.limit_price
            runner_pl = runner_exit_price - self.limit_price
        else:
            first_pl = self.limit_price - self.first_target if self.partial_done else self.limit_price - runner_exit_price
            runner_pl = self.limit_price - runner_exit_price
        total_pl = first_pl + runner_pl
        account_r = total_pl / (2.0 * self.risk) if self.risk > 0 else math.nan
        self.trades.append({
            'Period': self.period,
            'Range_High': self.range_high,
            'Range_Low': self.range_low,
            'Range': self.range_val,
            'Trade_Direction': self.direction,
            'Units': 2,
            'Entry_Price': self.limit_price,
            'Initial_Stop_Price': self.stop,
            'Risk_Pts': self.risk,
            'First_Target_Price': self.first_target,
            'Runner_Target_Price': self.runner_target,
            'Runner_R_Target': self.runner_r,
            'First_Exit_Price': self.first_target if self.partial_done else runner_exit_price,
            'First_Exit_Time': self.partial_exit_time if self.partial_done else exit_time,
            'First_Exit_Reason': first_exit_reason,
            'Runner_Exit_Price': runner_exit_price,
            'Runner_Exit_Time': exit_time,
            'Runner_Exit_Reason': runner_exit_reason,
            'Exit_Price': runner_exit_price,
            'Exit_Time': exit_time,
            'Breakout_Date': self.breakout_date,
            'Order_Live_Date': self.order_live_date,
            'Entry_Time': self.entry_time,
            'Trade_PL': round(total_pl, 6),
            'First_Unit_PL': round(first_pl, 6),
            'Runner_PL': round(runner_pl, 6),
            'Account_R': round(account_r, 6) if not math.isnan(account_r) else None,
            'MAE_Pts': round(self.max_adverse_pts, 6),
            'MAE_R': round(self.max_adverse_pts / self.risk, 6) if self.risk > 0 else None,
            'Result': exit_reason,
            'Symbol': self.symbol,
            'Entry_Source': 'inside_opposite_open',
            'Entry_Source_Start': self.source['start'],
            'Entry_Source_End': self.source['end'],
            'Entry_Source_Date': self.source['date'],
            'Entry_Source_Count': self.source['count'],
            'Entry_Source_Open': self.source['open'],
            'Entry_Source_High': self.source['high'],
            'Entry_Source_Low': self.source['low'],
            'Entry_Source_Close': self.source['close'],
            'Entry_Source_Run_High': self.source['run_high'],
            'Entry_Source_Run_Low': self.source['run_low'],
        })

    def maybe_fill(self, minute) -> bool:
        assert self.direction is not None and self.limit_price is not None
        h = float(minute.high)
        l = float(minute.low)
        if self.direction == 'Long' and l <= self.limit_price:
            self.entry_time = minute.ts_event
            self.partial_done = False
            self.partial_exit_time = None
            self.max_adverse_pts = 0.0
            self.phase = IN_TRADE
            self.just_filled = True
            if l <= float(self.stop):
                self.update_mae(h, l)
                self.append_trade(minute.ts_event, 'Full-Stop', 'Initial_Stop', float(self.stop), 'Initial_Stop')
                self.reset_to_breakout()
            return True
        if self.direction == 'Short' and h >= self.limit_price:
            self.entry_time = minute.ts_event
            self.partial_done = False
            self.partial_exit_time = None
            self.max_adverse_pts = 0.0
            self.phase = IN_TRADE
            self.just_filled = True
            if h >= float(self.stop):
                self.update_mae(h, l)
                self.append_trade(minute.ts_event, 'Full-Stop', 'Initial_Stop', float(self.stop), 'Initial_Stop')
                self.reset_to_breakout()
            return True
        return False

    def process_trade_minute(self, minute) -> None:
        if self.phase != IN_TRADE:
            return
        assert self.direction is not None and self.limit_price is not None and self.stop is not None
        assert self.first_target is not None and self.runner_target is not None and self.risk is not None
        h = float(minute.high)
        l = float(minute.low)
        self.update_mae(h, l)
        if self.just_filled:
            self.just_filled = False
            return

        if self.direction == 'Long':
            if not self.partial_done:
                if l <= self.stop:
                    self.append_trade(minute.ts_event, 'Full-Stop', 'Initial_Stop', self.stop, 'Initial_Stop')
                    self.reset_to_breakout()
                elif h >= self.first_target:
                    self.partial_done = True
                    self.partial_exit_time = minute.ts_event
                    self.be_active_next_minute = True
            else:
                if self.be_active_next_minute:
                    self.be_active_next_minute = False
                    return
                if l <= self.limit_price:
                    self.append_trade(minute.ts_event, 'Runner-BE', 'First_1R', self.limit_price, 'Breakeven_Stop')
                    self.reset_to_breakout()
                elif h >= self.runner_target:
                    self.append_trade(minute.ts_event, f'Runner-{self.runner_r:g}R', 'First_1R', self.runner_target, f'Runner_{self.runner_r:g}R')
                    self.reset_to_breakout()
        else:
            if not self.partial_done:
                if h >= self.stop:
                    self.append_trade(minute.ts_event, 'Full-Stop', 'Initial_Stop', self.stop, 'Initial_Stop')
                    self.reset_to_breakout()
                elif l <= self.first_target:
                    self.partial_done = True
                    self.partial_exit_time = minute.ts_event
                    self.be_active_next_minute = True
            else:
                if self.be_active_next_minute:
                    self.be_active_next_minute = False
                    return
                if h >= self.limit_price:
                    self.append_trade(minute.ts_event, 'Runner-BE', 'First_1R', self.limit_price, 'Breakeven_Stop')
                    self.reset_to_breakout()
                elif l <= self.runner_target:
                    self.append_trade(minute.ts_event, f'Runner-{self.runner_r:g}R', 'First_1R', self.runner_target, f'Runner_{self.runner_r:g}R')
                    self.reset_to_breakout()

    def range_close_exit(self, bar, close_time) -> None:
        if self.phase != IN_TRADE or not self.restricted:
            return
        c = float(bar['close'])
        if not (self.range_low <= c <= self.range_high):
            return
        if self.partial_done:
            self.append_trade(close_time, 'Range-Close', 'First_1R', c, 'Close_Back_Inside_Range')
        else:
            self.append_trade(close_time, 'Range-Close', 'Close_Back_Inside_Range', c, 'Close_Back_Inside_Range')
        self.reset_to_breakout()

    def period_close_exit(self, bar, close_time) -> None:
        if self.phase != IN_TRADE:
            return
        c = float(bar['close'])
        if self.partial_done:
            self.append_trade(close_time, 'Period-Close', 'First_1R', c, 'Period_Close')
        else:
            self.append_trade(close_time, 'Period-Close', 'Period_Close', c, 'Period_Close')
        self.reset_to_breakout()

    def run(self) -> list[dict]:
        if self.range_val <= 0:
            return []
        for day_i, bar in self.trade_bars.iterrows():
            self.history.append(bar)
            if len(self.trades) >= MAX_TRADES_PER_PERIOD and self.phase != IN_TRADE:
                break
            d = bar['date']
            symbol = str(bar['symbol'])
            raw_day = self.raw_for_day(d, symbol)
            close_time = pd.Timestamp(d, tz='UTC')
            if not raw_day.empty:
                close_time = raw_day.iloc[-1]['ts_event']
                for minute in raw_day.itertuples(index=False):
                    if self.phase == WAIT_FILL:
                        self.maybe_fill(minute)
                    if self.phase == IN_TRADE:
                        self.process_trade_minute(minute)
                    if self.phase == WAIT_BREAKOUT and len(self.trades) >= MAX_TRADES_PER_PERIOD:
                        break

            self.range_close_exit(bar, close_time)

            if self.phase == WAIT_BREAKOUT and len(self.trades) < MAX_TRADES_PER_PERIOD:
                if self.valid_long_breakout(bar):
                    self.arm_order('Long', bar)
                elif self.valid_short_breakout(bar):
                    self.arm_order('Short', bar)

        if self.phase == IN_TRADE and len(self.trade_bars) > 0:
            last = self.trade_bars.iloc[-1]
            raw_day = self.raw_for_day(last['date'], str(last['symbol']))
            close_time = raw_day.iloc[-1]['ts_event'] if not raw_day.empty else pd.Timestamp(last['date'], tz='UTC')
            self.period_close_exit(last, close_time)
        return self.trades


def run_intraday(daily: pd.DataFrame, raw: pd.DataFrame, *, restricted: bool, runner_r: float) -> pd.DataFrame:
    grouped = raw.groupby(['date', 'symbol'], sort=False)
    rows = []
    for period, bars in period_rows(daily):
        sim = IntradayMonth(period, bars, grouped, restricted=restricted, runner_r=runner_r)
        rows.extend(sim.run())
    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum().round(6)
    return out


def summarize_intraday(df: pd.DataFrame, multiplier: float = 2.0) -> dict:
    pnl = df['Trade_PL'].astype(float) if not df.empty else pd.Series(dtype=float)
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float((pnl * multiplier).sum()),
        'dd_pts': max_drawdown(pnl),
        'dd_usd': max_drawdown(pnl * multiplier),
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'pf': profit_factor(pnl),
        'avg_trade_pts': float(pnl.mean()) if len(pnl) else math.nan,
        'runner_hits': int(df['Runner_Exit_Reason'].astype(str).str.startswith('Runner_').sum()) if not df.empty else 0,
        'first_1r_hits': int((df['First_Exit_Reason'] == 'First_1R').sum()) if not df.empty else 0,
        'full_stops': int((df['Result'] == 'Full-Stop').sum()) if not df.empty else 0,
        'range_closes': int((df['Result'] == 'Range-Close').sum()) if not df.empty else 0,
        'be_exits': int((df['Runner_Exit_Reason'] == 'Breakeven_Stop').sum()) if not df.empty else 0,
        'avg_mae_r': float(pd.to_numeric(df.get('MAE_R', pd.Series(dtype=float)), errors='coerce').mean()) if not df.empty else math.nan,
        'median_mae_r': float(pd.to_numeric(df.get('MAE_R', pd.Series(dtype=float)), errors='coerce').median()) if not df.empty else math.nan,
    }


def date_value(bars: pd.DataFrame, d, col: str) -> float | None:
    if pd.isna(d):
        return None
    hit = bars[pd.to_datetime(bars['date']).dt.date == pd.Timestamp(d).date()]
    if hit.empty:
        return None
    return float(hit.iloc[0][col])


def draw_period(period: str, bars: pd.DataFrame, trades: pd.DataFrame, out_path: Path) -> dict | None:
    chart_trades = trades[trades['Period'].astype(str) == period].copy()
    if chart_trades.empty:
        return None
    range_bars = bars.iloc[:3].copy()
    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low

    fig = plt.figure(figsize=(15, 8), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    width = 0.58
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.8, zorder=3)
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

    ax.axvspan(pd.Timestamp(range_bars.iloc[0]['date']), pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1), color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.10, zorder=0)
    ax.axhline(range_high, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)

    label_offsets = [24, -38, 52, -66]
    for i, (_, tr) in enumerate(chart_trades.iterrows(), 1):
        direction = str(tr['Trade_Direction'])
        entry = float(tr['Entry_Price'])
        stop = float(tr['Initial_Stop_Price'])
        one_r = float(tr['First_Target_Price'])
        runner = float(tr['Runner_Target_Price'])
        breakout_date = pd.Timestamp(tr['Breakout_Date'])
        source_date = pd.Timestamp(tr['Entry_Source_Date'])
        source_start = pd.Timestamp(tr['Entry_Source_Start'])
        source_end = pd.Timestamp(tr['Entry_Source_End'])
        entry_time = pd.Timestamp(tr['Entry_Time'])
        first_time = pd.Timestamp(tr['First_Exit_Time'])
        runner_time = pd.Timestamp(tr['Runner_Exit_Time'])
        result = str(tr['Result'])
        pl = float(tr['Trade_PL'])

        ax.axvspan(source_start - pd.Timedelta(hours=12), source_end + pd.Timedelta(hours=12), color='#AB47BC', alpha=0.16, zorder=1)
        ax.scatter([mdates.date2num(source_date)], [float(tr['Entry_Source_Open'])], marker='D', color='#CE93D8', s=90, zorder=9, edgecolor='black', linewidth=1.0)
        breakout_close = date_value(bars, breakout_date, 'close')
        if breakout_close is not None:
            ax.scatter([mdates.date2num(breakout_date)], [breakout_close], marker='^' if direction == 'Long' else 'v', color='#4FC3F7', s=105, zorder=9, edgecolor='black', linewidth=1.0)

        entry_x = mdates.date2num(entry_time.tz_convert(None))
        first_x = mdates.date2num(first_time.tz_convert(None))
        runner_x = mdates.date2num(runner_time.tz_convert(None))
        ax.scatter([entry_x], [entry], marker='^' if direction == 'Long' else 'v', color='#FFC107', s=140, zorder=10, edgecolor='black', linewidth=1.2)
        ax.scatter([first_x], [one_r], marker='o', color='#B2FF59', s=95, zorder=10, edgecolor='black', linewidth=1.0)
        exit_color = '#76FF03' if pl > 0 else '#FF1744'
        if result == 'Range-Close':
            exit_color = '#FFB74D'
        ax.scatter([runner_x], [float(tr['Runner_Exit_Price'])], marker='X', color=exit_color, s=145, zorder=10, edgecolor='black', linewidth=1.2)

        ax.plot([entry_time.tz_convert(None), runner_time.tz_convert(None)], [stop, stop], color='#FF1744', linewidth=0.9, alpha=0.70, zorder=4)
        ax.plot([entry_time.tz_convert(None), runner_time.tz_convert(None)], [one_r, one_r], color='#B2FF59', linewidth=0.9, alpha=0.75, zorder=4)
        ax.plot([entry_time.tz_convert(None), runner_time.tz_convert(None)], [runner, runner], color='#76FF03', linewidth=0.9, alpha=0.55, zorder=4)
        ax.annotate(
            f'#{i} {direction[0]} {result} {pl:+.0f}pt',
            xy=(runner_x, float(tr['Runner_Exit_Price'])),
            xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=exit_color,
            fontsize=8,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=exit_color, alpha=0.95),
        )

    sym = str(bars.iloc[0]['symbol'])
    total_pl = float(chart_trades['Trade_PL'].sum())
    ax.set_title(
        f'{period}  INTRADAY VALIDATED INSIDE SOURCE-STOP SCALEOUT 2R  ·  {sym}  ·  '
        f'Range {range_val:.1f}  ·  {len(chart_trades)} trade(s)  ·  {total_pl:+.1f} package-pts (${total_pl * 2:+.0f})',
        color='white',
        fontsize=9,
        fontweight='bold',
        pad=8,
        loc='left',
    )
    last_x = xnums[-1] + 0.4
    ax.text(last_x, range_high, f' RH {range_high:.1f}', color='#E0E0E0', fontsize=7, va='center')
    ax.text(last_x, range_low, f' RL {range_low:.1f}', color='#E0E0E0', fontsize=7, va='center')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=2))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)
    return {
        'period': period,
        'year': int(period[:4]),
        'symbol': sym,
        'trades': int(len(chart_trades)),
        'net_pts': round(total_pl, 2),
        'chart': f'{period[:4]}/{period}.png',
    }


def write_chart_index(out_root: Path, rows: list[dict], stats: dict) -> None:
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        by_year.setdefault(row['year'], []).append(row)
    for year, yr_rows in sorted(by_year.items()):
        idx = out_root / str(year) / 'INDEX.md'
        idx.write_text(
            '\n'.join([
                f'# {year} intraday scaleout charts',
                '',
                '| Period | Symbol | Trades | Net package pts | Chart |',
                '|---|---|---:|---:|---|',
                *[
                    f"| {r['period']} | {r['symbol']} | {r['trades']} | {r['net_pts']:+.2f} | [{r['period']}.png]({r['period']}.png) |"
                    for r in sorted(yr_rows, key=lambda x: x['period'])
                ],
                '',
            ]),
            encoding='utf-8',
        )
    out_root.joinpath('INDEX.md').write_text(
        '\n'.join([
            '# MNQ Intraday-Validated Inside Source-Stop Scaleout 2R Charts',
            '',
            f"Trades: {stats['trades']}  ·  Net: {fmt_money(stats['net_usd'])}  ·  Max DD: {fmt_money(stats['dd_usd'])}  ·  PF: {fmt_num(stats['pf'])}",
            '',
            'Purple diamond/region = selected inside opposite candle run. Blue triangle = breakout close. Gold triangle = 1-minute limit fill. Green dot = 1R partial. X = runner exit.',
            '',
            '| Period | Symbol | Trades | Net package pts | Chart |',
            '|---|---|---:|---:|---|',
            *[
                f"| {r['period']} | {r['symbol']} | {r['trades']} | {r['net_pts']:+.2f} | [{r['chart']}]({r['chart']}) |"
                for r in sorted(rows, key=lambda x: x['period'])
            ],
            '',
        ]),
        encoding='utf-8',
    )


def write_report(
    variant_rows: list[dict],
    intraday_runner_rows: list[dict],
    daily_stats: dict,
    intraday_stats: dict,
    out_csv: Path,
    chart_root: Path,
) -> None:
    lines = [
        '# Monthly ORB Variant Comparison And Intraday Validation',
        '',
        'Raw MNQ 1-minute bars were used to validate the strongest causal daily candidate: inside-candle-open restricted source-stop scaleout with a 2R runner.',
        '',
        'Causal intraday assumptions:',
        '',
        '- Monthly OR is still built from the first 3 daily bars.',
        '- Breakout signal is only known after the daily close.',
        '- The inside-candle-open limit is live on the next UTC daily bar.',
        '- Fill is a limit touch on 1-minute bars.',
        '- If entry and initial stop are both touched in the fill minute, the stop is counted.',
        '- The 1R partial can trigger only after fill; BE/runner orders become active on the next minute.',
        '- After the BE move, same-minute BE/runner ambiguity is resolved BE-first.',
        '- Restricted range-close exits are applied at the daily close after all minute events for that date.',
        '',
        '## Variant Comparison',
        '',
        '| Rank | Variant | Causal? | Units | Trades | Net | Max DD | Net/unit | DD/unit | Win rate | PF | Net/DD |',
        '|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for i, row in enumerate(variant_rows, 1):
        lines.append(
            f"| {i} | {row['variant']} | {'yes' if row['causal'] else 'no'} | {row['units']} | {row['trades']} | "
            f"{fmt_money(row['net_usd'])} | {fmt_money(row['dd_usd'])} | {fmt_money(row['net_per_unit_usd'])} | "
            f"{fmt_money(row['dd_per_unit_usd'])} | {fmt_pct(row['win_rate'])} | {fmt_num(row['pf'])} | {fmt_num(row['score'])} |"
        )

    lines.extend([
        '',
        '## Intraday Scale-Out Runner Comparison',
        '',
        '| Variant | Runner target | Trades | Net | Max DD | Win rate | PF | Avg/trade pts | 1R hits | Runner hits | Full stops | BE exits | Range closes | Avg MAE R |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ])
    for row in intraday_runner_rows:
        s = row['stats']
        lines.append(
            f"| {row['variant']} | {row['runner_r']:g}R | {s['trades']} | {fmt_money(s['net_usd'])} | "
            f"{fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | "
            f"{fmt_num(s['avg_trade_pts'])} | {s['first_1r_hits']} | {s['runner_hits']} | "
            f"{s['full_stops']} | {s['be_exits']} | {s['range_closes']} | {fmt_num(s['avg_mae_r'])} |"
        )

    lines.extend([
        '',
        '## Daily Vs Intraday For Selected Candidate',
        '',
        '| Mode | Trades | Net | Max DD | Win rate | PF | Avg/trade pts | 1R hits | Runner hits | Full stops | BE exits | Range closes | Avg MAE R | Median MAE R |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        f"| Daily OHLC | {daily_stats['trades']} | {fmt_money(daily_stats['net_usd'])} | {fmt_money(daily_stats['dd_usd'])} | {fmt_pct(daily_stats['win_rate'])} | {fmt_num(daily_stats['pf'])} | {fmt_num(daily_stats['avg_trade_pts'])} | {daily_stats['first_1r_hits']} | {daily_stats['runner_hits']} | {daily_stats['full_stops']} | {daily_stats['be_exits']} | {daily_stats['range_closes']} | {fmt_num(daily_stats['avg_mae_r'])} | {fmt_num(daily_stats['median_mae_r'])} |",
        f"| 1-minute causal | {intraday_stats['trades']} | {fmt_money(intraday_stats['net_usd'])} | {fmt_money(intraday_stats['dd_usd'])} | {fmt_pct(intraday_stats['win_rate'])} | {fmt_num(intraday_stats['pf'])} | {fmt_num(intraday_stats['avg_trade_pts'])} | {intraday_stats['first_1r_hits']} | {intraday_stats['runner_hits']} | {intraday_stats['full_stops']} | {intraday_stats['be_exits']} | {intraday_stats['range_closes']} | {fmt_num(intraday_stats['avg_mae_r'])} | {fmt_num(intraday_stats['median_mae_r'])} |",
        '',
        '## Best Candidate',
        '',
        '**Best current execution candidate: inside-candle-open restricted source-stop scaleout with a 2R runner, validated on MNQ 1-minute bars.** It is not the highest gross daily backtest row, but it has the best blend of causality, drawdown control, profit factor, and explicit risk. In the minute-level runner comparison, unrestricted 3R has the highest net, but restricted 2R has much lower drawdown and the best profit factor.',
        '',
        'The non-causal original boundary-entry rows stay in the table for context only; they are not live-test candidates because they assume same-bar knowledge/fill behavior that the causal studies removed.',
        '',
        '## Outputs',
        '',
        f'- Intraday CSV: `{out_csv}`',
        f'- Chart index: `{chart_root / "INDEX.md"}`',
        '',
    ])
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--raw-1m', type=Path, default=RAW_1M)
    ap.add_argument('--out-csv', type=Path, default=MNQ_ROOT / 'mnq_monthly_orb_inside_restricted_source_stop_scaleout_2r_intraday.csv')
    ap.add_argument('--chart-out', type=Path, default=CHART_ROOT)
    ap.add_argument('--no-charts', action='store_true')
    args = ap.parse_args()

    daily = load_daily(args.daily)
    print(f'Loading raw 1m from {args.raw_1m}...', file=sys.stderr)
    raw = load_raw_1m(args.raw_1m)
    print(f'Loaded {len(raw):,} minute rows', file=sys.stderr)

    intraday_runner_rows = []
    selected_intraday = None
    selected_path = args.out_csv
    for restricted in (False, True):
        for runner_r in (2.0, 3.0):
            intraday = run_intraday(daily, raw, restricted=restricted, runner_r=runner_r)
            suffix = 'restricted_source_stop' if restricted else 'source_stop'
            path = MNQ_ROOT / f'mnq_monthly_orb_inside_{suffix}_scaleout_{int(runner_r)}r_intraday.csv'
            if restricted and runner_r == 2.0:
                path = selected_path
                selected_intraday = intraday
            path.parent.mkdir(parents=True, exist_ok=True)
            intraday.to_csv(path, index=False)
            intraday_runner_rows.append({
                'variant': 'restricted source-stop scaleout' if restricted else 'unrestricted source-stop scaleout',
                'runner_r': runner_r,
                'path': path,
                'stats': summarize_intraday(intraday),
            })

    assert selected_intraday is not None

    variant_rows = compare_variants()
    daily_df = pd.read_csv(MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_2r.csv')
    daily_stats = summarize_intraday(daily_df)
    intraday_stats = summarize_intraday(selected_intraday)

    chart_rows = []
    if not args.no_charts:
        args.chart_out.mkdir(parents=True, exist_ok=True)
        for period, bars in period_rows(daily):
            out_path = args.chart_out / period[:4] / f'{period}.png'
            row = draw_period(period, bars, selected_intraday, out_path)
            if row:
                chart_rows.append(row)
                print(f'{row["chart"]} {row["net_pts"]:+.2f} package-pts')
        write_chart_index(args.chart_out, chart_rows, intraday_stats)

    write_report(variant_rows, intraday_runner_rows, daily_stats, intraday_stats, args.out_csv, args.chart_out)
    print(f'Wrote {args.out_csv}')
    print(f'Wrote {REPORT}')
    if not args.no_charts:
        print(f'Wrote {len(chart_rows)} charts under {args.chart_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
