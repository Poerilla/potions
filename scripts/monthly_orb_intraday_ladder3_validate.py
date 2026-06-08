#!/usr/bin/env python3
"""3-contract intraday ladder study for monthly ORB inside source-stop entries."""
from __future__ import annotations

from pathlib import Path
from datetime import timedelta
from typing import Iterable

import argparse
import math
import sys

import pandas as pd

from monthly_orb_intraday_scaleout_validate import (
    IN_TRADE,
    MAX_TRADES_PER_PERIOD,
    MNQ_ROOT,
    RAW_1M,
    WAIT_BREAKOUT,
    WAIT_FILL,
    fmt_money,
    fmt_num,
    fmt_pct,
    inside_opposite_entry,
    load_daily,
    load_raw_1m,
    period_rows,
)


REPORT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'INSIDE_SOURCE_STOP_LADDER3_INTRADAY_STUDY.md'


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


class Ladder3Month:
    def __init__(self, period: str, bars: pd.DataFrame, raw_grouped, *, restricted: bool) -> None:
        self.period = period
        self.bars = bars
        self.raw_grouped = raw_grouped
        self.restricted = restricted
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
        self.entry = None
        self.initial_stop = None
        self.boundary_stop = None
        self.risk = None
        self.targets = []
        self.breakout_date = None
        self.order_live_date = None
        self.entry_time = None
        self.source = None
        self.unit_exit_px = [None, None, None]
        self.unit_exit_time = [None, None, None]
        self.unit_exit_reason = [None, None, None]
        self.boundary_stop_active = False
        self.boundary_stop_activate_next = False
        self.boundary_stop_waiting_cross = False
        self.just_filled = False
        self.max_adverse_pts = 0.0

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
            initial_stop = float(found['run_low'])
            risk = entry - initial_stop
            if risk <= 0:
                return False
            targets = [entry + risk, entry + 2.0 * risk, entry + 3.0 * risk]
            boundary_stop = self.range_high
        else:
            initial_stop = float(found['run_high'])
            risk = initial_stop - entry
            if risk <= 0:
                return False
            targets = [entry - risk, entry - 2.0 * risk, entry - 3.0 * risk]
            boundary_stop = self.range_low

        self.direction = direction
        self.entry = entry
        self.initial_stop = initial_stop
        self.boundary_stop = boundary_stop
        self.risk = risk
        self.targets = targets
        self.breakout_date = bar['date']
        self.order_live_date = bar['date'] + timedelta(days=1)
        self.source = found
        self.phase = WAIT_FILL
        return True

    def update_mae(self, h: float, l: float) -> None:
        assert self.direction is not None and self.entry is not None
        if self.direction == 'Long':
            self.max_adverse_pts = max(self.max_adverse_pts, max(0.0, self.entry - l))
        else:
            self.max_adverse_pts = max(self.max_adverse_pts, max(0.0, h - self.entry))

    def open_units(self) -> list[int]:
        return [i for i, px in enumerate(self.unit_exit_px) if px is None]

    def exit_unit(self, idx: int, px: float, ts, reason: str) -> None:
        self.unit_exit_px[idx] = float(px)
        self.unit_exit_time[idx] = ts
        self.unit_exit_reason[idx] = reason

    def exit_all_open(self, px: float, ts, reason: str) -> None:
        for idx in self.open_units():
            self.exit_unit(idx, px, ts, reason)
        self.append_trade()
        self.reset_to_breakout()

    def append_trade(self) -> None:
        assert self.direction is not None and self.entry is not None and self.initial_stop is not None
        assert self.boundary_stop is not None and self.risk is not None and self.source is not None
        pls = []
        for px in self.unit_exit_px:
            assert px is not None
            if self.direction == 'Long':
                pls.append(float(px) - self.entry)
            else:
                pls.append(self.entry - float(px))
        total_pl = sum(pls)
        account_r = total_pl / (3.0 * self.risk) if self.risk > 0 else math.nan
        final_reason = str(self.unit_exit_reason[-1])
        if all(str(reason).startswith('Target') for reason in self.unit_exit_reason):
            result = 'Target-3R'
        elif any(reason == 'Range-Close' for reason in self.unit_exit_reason):
            result = 'Range-Close'
        elif any(reason == 'Period-Close' for reason in self.unit_exit_reason):
            result = 'Period-Close'
        elif any(reason == 'Boundary-Stop' for reason in self.unit_exit_reason):
            result = 'Boundary-Stop'
        elif all(reason == 'Initial-Stop' for reason in self.unit_exit_reason):
            result = 'Full-Stop'
        else:
            result = final_reason
        self.trades.append({
            'Period': self.period,
            'Range_High': self.range_high,
            'Range_Low': self.range_low,
            'Range': self.range_val,
            'Trade_Direction': self.direction,
            'Units': 3,
            'Entry_Price': self.entry,
            'Initial_Stop_Price': self.initial_stop,
            'Boundary_Stop_Price': self.boundary_stop,
            'Risk_Pts': self.risk,
            'Target_1R_Price': self.targets[0],
            'Target_2R_Price': self.targets[1],
            'Target_3R_Price': self.targets[2],
            'Unit1_Exit_Price': self.unit_exit_px[0],
            'Unit1_Exit_Time': self.unit_exit_time[0],
            'Unit1_Exit_Reason': self.unit_exit_reason[0],
            'Unit2_Exit_Price': self.unit_exit_px[1],
            'Unit2_Exit_Time': self.unit_exit_time[1],
            'Unit2_Exit_Reason': self.unit_exit_reason[1],
            'Unit3_Exit_Price': self.unit_exit_px[2],
            'Unit3_Exit_Time': self.unit_exit_time[2],
            'Unit3_Exit_Reason': self.unit_exit_reason[2],
            'Exit_Price': self.unit_exit_px[-1],
            'Exit_Time': self.unit_exit_time[-1],
            'Breakout_Date': self.breakout_date,
            'Order_Live_Date': self.order_live_date,
            'Entry_Time': self.entry_time,
            'Trade_PL': round(total_pl, 6),
            'Unit1_PL': round(pls[0], 6),
            'Unit2_PL': round(pls[1], 6),
            'Unit3_PL': round(pls[2], 6),
            'Account_R': round(account_r, 6) if not math.isnan(account_r) else None,
            'MAE_Pts': round(self.max_adverse_pts, 6),
            'MAE_R': round(self.max_adverse_pts / self.risk, 6) if self.risk > 0 else None,
            'Result': result,
            'Final_Reason': final_reason,
            'Boundary_Stop_Activated': self.boundary_stop_active,
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
        assert self.direction is not None and self.entry is not None and self.initial_stop is not None
        h = float(minute.high)
        l = float(minute.low)
        filled = (self.direction == 'Long' and l <= self.entry) or (self.direction == 'Short' and h >= self.entry)
        if not filled:
            return False
        self.entry_time = minute.ts_event
        self.phase = IN_TRADE
        self.just_filled = True
        self.max_adverse_pts = 0.0
        if self.direction == 'Long' and l <= self.initial_stop:
            self.update_mae(h, l)
            self.exit_all_open(self.initial_stop, minute.ts_event, 'Initial-Stop')
        elif self.direction == 'Short' and h >= self.initial_stop:
            self.update_mae(h, l)
            self.exit_all_open(self.initial_stop, minute.ts_event, 'Initial-Stop')
        return True

    def mark_boundary_cross_for_activation(self, h: float, l: float) -> None:
        assert self.direction is not None and self.boundary_stop is not None
        if self.boundary_stop_active or self.boundary_stop_activate_next:
            return
        if self.direction == 'Long' and h >= self.boundary_stop:
            self.boundary_stop_activate_next = True
            self.boundary_stop_waiting_cross = False
        elif self.direction == 'Short' and l <= self.boundary_stop:
            self.boundary_stop_activate_next = True
            self.boundary_stop_waiting_cross = False
        else:
            self.boundary_stop_waiting_cross = True

    def process_trade_minute(self, minute) -> None:
        if self.phase != IN_TRADE:
            return
        assert self.direction is not None and self.entry is not None and self.initial_stop is not None
        assert self.boundary_stop is not None and self.risk is not None

        if self.boundary_stop_activate_next:
            self.boundary_stop_active = True
            self.boundary_stop_activate_next = False

        h = float(minute.high)
        l = float(minute.low)
        self.update_mae(h, l)
        if self.just_filled:
            self.just_filled = False
            return

        open_units = self.open_units()
        if not open_units:
            return

        if self.direction == 'Long':
            active_stop = self.boundary_stop if self.boundary_stop_active else self.initial_stop
            if l <= active_stop:
                reason = 'Boundary-Stop' if self.boundary_stop_active else 'Initial-Stop'
                self.exit_all_open(active_stop, minute.ts_event, reason)
                return
            for idx, target in enumerate(self.targets):
                if self.unit_exit_px[idx] is None and h >= target:
                    self.exit_unit(idx, target, minute.ts_event, f'Target-{idx + 1}R')
                    if idx == 0:
                        self.mark_boundary_cross_for_activation(h, l)
            if self.open_units():
                if self.unit_exit_px[0] is not None:
                    self.mark_boundary_cross_for_activation(h, l)
            else:
                self.append_trade()
                self.reset_to_breakout()
        else:
            active_stop = self.boundary_stop if self.boundary_stop_active else self.initial_stop
            if h >= active_stop:
                reason = 'Boundary-Stop' if self.boundary_stop_active else 'Initial-Stop'
                self.exit_all_open(active_stop, minute.ts_event, reason)
                return
            for idx, target in enumerate(self.targets):
                if self.unit_exit_px[idx] is None and l <= target:
                    self.exit_unit(idx, target, minute.ts_event, f'Target-{idx + 1}R')
                    if idx == 0:
                        self.mark_boundary_cross_for_activation(h, l)
            if self.open_units():
                if self.unit_exit_px[0] is not None:
                    self.mark_boundary_cross_for_activation(h, l)
            else:
                self.append_trade()
                self.reset_to_breakout()

    def range_close_exit(self, bar, close_time) -> None:
        if self.phase != IN_TRADE or not self.restricted:
            return
        c = float(bar['close'])
        if not (self.range_low <= c <= self.range_high):
            return
        self.exit_all_open(c, close_time, 'Range-Close')

    def period_close_exit(self, bar, close_time) -> None:
        if self.phase != IN_TRADE:
            return
        self.exit_all_open(float(bar['close']), close_time, 'Period-Close')

    def run(self) -> list[dict]:
        if self.range_val <= 0:
            return []
        for _, bar in self.trade_bars.iterrows():
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


def run_ladder3(daily: pd.DataFrame, raw: pd.DataFrame, *, restricted: bool) -> pd.DataFrame:
    grouped = raw.groupby(['date', 'symbol'], sort=False)
    rows = []
    for period, bars in period_rows(daily):
        sim = Ladder3Month(period, bars, grouped, restricted=restricted)
        rows.extend(sim.run())
    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum().round(6)
    return out


def summarize(df: pd.DataFrame, multiplier: float = 2.0) -> dict:
    pnl = df['Trade_PL'].astype(float) if not df.empty else pd.Series(dtype=float)
    account_r = pd.to_numeric(df.get('Account_R', pd.Series(dtype=float)), errors='coerce') if not df.empty else pd.Series(dtype=float)
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float((pnl * multiplier).sum()),
        'dd_pts': max_drawdown(pnl),
        'dd_usd': max_drawdown(pnl * multiplier),
        'net_per_contract_usd': float((pnl / 3.0 * multiplier).sum()) if len(pnl) else 0.0,
        'dd_per_contract_usd': max_drawdown(pnl / 3.0 * multiplier) if len(pnl) else 0.0,
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'pf': profit_factor(pnl),
        'avg_trade_pts': float(pnl.mean()) if len(pnl) else math.nan,
        'avg_account_r': float(account_r.mean()) if len(account_r) else math.nan,
        'median_account_r': float(account_r.median()) if len(account_r) else math.nan,
        'target1_hits': int(df['Unit1_Exit_Reason'].astype(str).str.startswith('Target-1R').sum()) if not df.empty else 0,
        'target2_hits': int(df['Unit2_Exit_Reason'].astype(str).str.startswith('Target-2R').sum()) if not df.empty else 0,
        'target3_hits': int(df['Unit3_Exit_Reason'].astype(str).str.startswith('Target-3R').sum()) if not df.empty else 0,
        'full_stops': int((df['Result'] == 'Full-Stop').sum()) if not df.empty else 0,
        'boundary_stops': int((df['Result'] == 'Boundary-Stop').sum()) if not df.empty else 0,
        'range_closes': int((df['Result'] == 'Range-Close').sum()) if not df.empty else 0,
        'period_closes': int((df['Result'] == 'Period-Close').sum()) if not df.empty else 0,
    }


def write_report(rows: list[dict]) -> None:
    lines = [
        '# Inside Source-Stop 3-Contract Ladder Intraday Study',
        '',
        'Setup is the causal monthly ORB inside-candle-open source-stop entry. This study uses 3 contracts: one exits at 1R, one exits at 2R, and one exits at 3R.',
        '',
        'After the 1R exit, the remaining two contracts move their stop to the breakout-side monthly OR boundary: monthly OR high for longs and monthly OR low for shorts. To keep this live-realistic, that boundary stop only becomes a protective stop after price has traded on the profitable side of that boundary; until then the original source stop remains active.',
        '',
        'Restricted keeps the daily close-back-inside monthly range exit. Results are MNQ gross before fees/slippage, using raw 1-minute bars for fill and exit order.',
        '',
        '| Variant | Trades | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | Target 1R | Target 2R | Target 3R | Full stops | Boundary stops | Range closes |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        s = row['stats']
        lines.append(
            f"| {row['label']} | {s['trades']} | {fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | "
            f"{fmt_money(s['net_per_contract_usd'])} | {fmt_money(s['dd_per_contract_usd'])} | "
            f"{fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | {fmt_num(s['avg_trade_pts'])} | "
            f"{fmt_num(s['avg_account_r'])} | {s['target1_hits']} | {s['target2_hits']} | {s['target3_hits']} | "
            f"{s['full_stops']} | {s['boundary_stops']} | {s['range_closes']} |"
        )
    lines.extend([
        '',
        '## Read',
        '',
        'The 3R contract does add gross profit, especially in the unrestricted variant, but the boundary-stop logic does not beat the current restricted 2-contract 2R candidate on drawdown-adjusted quality.',
        '',
        'The restricted ladder is still constrained by the close-back-inside rule, so it does not get many 3R completions. The unrestricted ladder gives the third contract more room, but the larger open exposure and delayed boundary-stop validity increase drawdown.',
        '',
        '## Output CSVs',
        '',
    ])
    for row in rows:
        lines.append(f"- {row['label']}: `{row['path']}`")
    lines.append('')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--raw-1m', type=Path, default=RAW_1M)
    args = ap.parse_args()

    daily = load_daily(args.daily)
    print(f'Loading raw 1m from {args.raw_1m}...', file=sys.stderr)
    raw = load_raw_1m(args.raw_1m)
    print(f'Loaded {len(raw):,} minute rows', file=sys.stderr)

    rows = []
    for restricted in (False, True):
        label = 'unrestricted ladder 1R/2R/3R' if not restricted else 'restricted ladder 1R/2R/3R'
        suffix = 'source_stop_ladder3' if not restricted else 'restricted_source_stop_ladder3'
        out = run_ladder3(daily, raw, restricted=restricted)
        path = MNQ_ROOT / f'mnq_monthly_orb_inside_{suffix}_intraday.csv'
        out.to_csv(path, index=False)
        stats = summarize(out)
        rows.append({'label': label, 'path': path, 'stats': stats})
        print(
            f"{label}: {fmt_money(stats['net_usd'])}, DD {fmt_money(stats['dd_usd'])}, "
            f"WR {fmt_pct(stats['win_rate'])}, PF {fmt_num(stats['pf'])}, "
            f"3R hits {stats['target3_hits']}, wrote {path}"
        )

    write_report(rows)
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
