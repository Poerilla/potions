#!/usr/bin/env python3
"""Range-target ladder with stale-limit cancellation and optional range stop."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import argparse
import math
import sys

import pandas as pd

from monthly_orb_intraday_ladder3_range_validate import RangeTargetLadder3Month
from monthly_orb_intraday_ladder3_validate import summarize
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


REPORT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'INSIDE_RANGE_TARGET_LADDER_CANCEL_STALE_LIMIT_STUDY.md'


class CancelStaleRangeTargetLadder3Month(RangeTargetLadder3Month):
    """Cancel pending limit if target 1 trades before fill."""

    def __init__(self, *args, initial_stop_mode: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if initial_stop_mode not in {'source', 'opposing_range'}:
            raise ValueError(f'unsupported initial_stop_mode: {initial_stop_mode}')
        self.initial_stop_mode = initial_stop_mode
        self.cancelled_stale_orders: list[dict] = []

    def arm_order(self, direction: str, bar) -> bool:
        found = inside_opposite_entry(self.history, direction, self.range_high, self.range_low)
        if found is None:
            return False
        entry = float(found['price'])
        if direction == 'Long':
            initial_stop = self.range_low if self.initial_stop_mode == 'opposing_range' else float(found['run_low'])
            risk = entry - initial_stop
            if risk <= 0:
                return False
            targets = [
                self.range_high + self.range_val,
                self.range_high + 2.0 * self.range_val,
                self.range_high + 3.0 * self.range_val,
            ]
            boundary_stop = self.range_high
        else:
            initial_stop = self.range_high if self.initial_stop_mode == 'opposing_range' else float(found['run_high'])
            risk = initial_stop - entry
            if risk <= 0:
                return False
            targets = [
                self.range_low - self.range_val,
                self.range_low - 2.0 * self.range_val,
                self.range_low - 3.0 * self.range_val,
            ]
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

    def pending_target_touched(self, minute) -> bool:
        if self.phase != WAIT_FILL or self.direction is None or not self.targets:
            return False
        target1 = float(self.targets[0])
        touched = (self.direction == 'Long' and float(minute.high) >= target1) or (
            self.direction == 'Short' and float(minute.low) <= target1
        )
        if not touched:
            return False
        self.cancelled_stale_orders.append({
            'period': self.period,
            'direction': self.direction,
            'breakout_date': self.breakout_date,
            'cancel_time': minute.ts_event,
            'entry': self.entry,
            'target_1': target1,
        })
        self.reset_to_breakout()
        return True

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
                        if self.pending_target_touched(minute):
                            continue
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


def run_ladder(daily: pd.DataFrame, raw: pd.DataFrame, *, restricted: bool, initial_stop_mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    grouped = raw.groupby(['date', 'symbol'], sort=False)
    trade_rows = []
    cancel_rows = []
    for period, bars in period_rows(daily):
        sim = CancelStaleRangeTargetLadder3Month(
            period,
            bars,
            grouped,
            restricted=restricted,
            initial_stop_mode=initial_stop_mode,
        )
        trade_rows.extend(sim.run())
        cancel_rows.extend(sim.cancelled_stale_orders)
    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades['Cumulative_PL'] = trades['Trade_PL'].astype(float).cumsum().round(6)
    cancels = pd.DataFrame(cancel_rows)
    return trades, cancels


def write_report(rows: list[dict]) -> None:
    lines = [
        '# Inside Range-Target Ladder With Stale-Limit Cancellation',
        '',
        'Targets are monthly OR range multiples: long target 1 = RH + range, target 2 = RH + 2x range, target 3 = RH + 3x range; shorts use RL - range multiples.',
        '',
        'New rules in this study:',
        '',
        '- If target 1 trades before the pending inside-candle limit fills, the limit is cancelled and the strategy waits for a new setup.',
        '- Unrestricted uses the opposing monthly OR boundary as the initial stop: range low for longs, range high for shorts.',
        '- Restricted keeps the source inside-candle/run stop and keeps the close-back-inside range exit.',
        '',
        'Same-minute pending target/fill ambiguity is resolved target-first, meaning the stale limit is cancelled.',
        '',
        '| Variant | Stop mode | Trades | Cancelled stale limits | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Target 1 | Target 2 | Target 3 | Full stops | Boundary stops | Range closes | Period closes |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        s = row['stats']
        lines.append(
            f"| {row['label']} | {row['stop_mode']} | {s['trades']} | {row['cancelled']} | "
            f"{fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | "
            f"{fmt_money(s['net_per_contract_usd'])} | {fmt_money(s['dd_per_contract_usd'])} | "
            f"{fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | {fmt_num(s['avg_trade_pts'])} | "
            f"{s['target1_hits']} | {s['target2_hits']} | {s['target3_hits']} | "
            f"{s['full_stops']} | {s['boundary_stops']} | {s['range_closes']} | {s['period_closes']} |"
        )
    lines.extend(['', '## Output CSVs', ''])
    for row in rows:
        lines.append(f"- {row['label']} trades: `{row['path']}`")
        lines.append(f"- {row['label']} cancelled stale limits: `{row['cancel_path']}`")
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

    specs = [
        ('unrestricted range-stop cancel-stale ladder', False, 'opposing_range', 'range_stop_ladder3_range_targets_cancel_stale'),
        ('restricted source-stop cancel-stale ladder', True, 'source', 'restricted_source_stop_ladder3_range_targets_cancel_stale'),
    ]
    rows = []
    for label, restricted, stop_mode, suffix in specs:
        trades, cancels = run_ladder(daily, raw, restricted=restricted, initial_stop_mode=stop_mode)
        path = MNQ_ROOT / f'mnq_monthly_orb_inside_{suffix}_intraday.csv'
        cancel_path = MNQ_ROOT / f'mnq_monthly_orb_inside_{suffix}_cancelled_limits_intraday.csv'
        trades.to_csv(path, index=False)
        cancels.to_csv(cancel_path, index=False)
        stats = summarize(trades)
        rows.append({
            'label': label,
            'stop_mode': stop_mode,
            'path': path,
            'cancel_path': cancel_path,
            'cancelled': int(len(cancels)),
            'stats': stats,
        })
        print(
            f"{label}: {fmt_money(stats['net_usd'])}, DD {fmt_money(stats['dd_usd'])}, "
            f"WR {fmt_pct(stats['win_rate'])}, PF {fmt_num(stats['pf'])}, "
            f"T1/T2/T3 {stats['target1_hits']}/{stats['target2_hits']}/{stats['target3_hits']}, "
            f"cancelled {len(cancels)}, wrote {path}"
        )

    write_report(rows)
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
