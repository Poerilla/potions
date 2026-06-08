#!/usr/bin/env python3
"""Restricted monthly ORB boundary-close scaleout study.

This variant keeps the causal inside-opposite-candle limit entry and stale-limit
cancellation, but changes the restricted exit:

* initial stop is one monthly range beyond the inside source stop
* if price closes back through the breakout boundary, two units come off
* the remaining unit is left for the first monthly range target
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import argparse
import math
import sys

import pandas as pd

from monthly_orb_intraday_ladder3_validate import Ladder3Month, max_drawdown, profit_factor
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


REPORT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'INSIDE_RESTRICTED_BOUNDARY_CLOSE_SCALEOUT_TP1_WIDE_STOP_STUDY.md'


class BoundaryCloseScaleoutMonth(Ladder3Month):
    """Three units: two off on boundary close, one runner to target 1."""

    def reset_to_breakout(self) -> None:
        super().reset_to_breakout()
        self.source_stop = None
        self.boundary_close_taken = False
        self.cancelled_stale_orders: list[dict] = getattr(self, 'cancelled_stale_orders', [])

    def arm_order(self, direction: str, bar) -> bool:
        found = inside_opposite_entry(self.history, direction, self.range_high, self.range_low)
        if found is None:
            return False

        entry = float(found['price'])
        if direction == 'Long':
            source_stop = float(found['run_low'])
            initial_stop = source_stop - self.range_val
            risk = entry - initial_stop
            if risk <= 0:
                return False
            target = self.range_high + self.range_val
            boundary_stop = self.range_high
        else:
            source_stop = float(found['run_high'])
            initial_stop = source_stop + self.range_val
            risk = initial_stop - entry
            if risk <= 0:
                return False
            target = self.range_low - self.range_val
            boundary_stop = self.range_low

        self.direction = direction
        self.entry = entry
        self.source_stop = source_stop
        self.initial_stop = initial_stop
        self.boundary_stop = boundary_stop
        self.risk = risk
        self.targets = [target, target, target]
        self.breakout_date = bar['date']
        self.order_live_date = bar['date'] + timedelta(days=1)
        self.source = found
        self.phase = WAIT_FILL
        return True

    def pending_target_touched(self, minute) -> bool:
        if self.phase != WAIT_FILL or self.direction is None or not self.targets:
            return False
        target = float(self.targets[0])
        touched = (self.direction == 'Long' and float(minute.high) >= target) or (
            self.direction == 'Short' and float(minute.low) <= target
        )
        if not touched:
            return False

        self.cancelled_stale_orders.append({
            'period': self.period,
            'direction': self.direction,
            'breakout_date': self.breakout_date,
            'cancel_time': minute.ts_event,
            'entry': self.entry,
            'target_1': target,
        })
        self.reset_to_breakout()
        return True

    def process_trade_minute(self, minute) -> None:
        if self.phase != IN_TRADE:
            return
        assert self.direction is not None and self.entry is not None and self.initial_stop is not None
        assert self.targets

        h = float(minute.high)
        l = float(minute.low)
        self.update_mae(h, l)
        if self.just_filled:
            self.just_filled = False
            return

        if not self.open_units():
            return

        target = float(self.targets[0])
        if self.direction == 'Long':
            if l <= self.initial_stop:
                self.exit_all_open(self.initial_stop, minute.ts_event, 'Initial-Stop')
                return
            if h >= target:
                self.exit_all_open(target, minute.ts_event, 'Target-1R')
                return
        else:
            if h >= self.initial_stop:
                self.exit_all_open(self.initial_stop, minute.ts_event, 'Initial-Stop')
                return
            if l <= target:
                self.exit_all_open(target, minute.ts_event, 'Target-1R')
                return

    def boundary_close_scaleout(self, bar, close_time) -> None:
        if self.phase != IN_TRADE or self.boundary_close_taken:
            return
        if self.unit_exit_px[0] is not None or self.unit_exit_px[1] is not None:
            return
        assert self.direction is not None and self.boundary_stop is not None

        close_px = float(bar['close'])
        crossed = (self.direction == 'Long' and close_px <= self.boundary_stop) or (
            self.direction == 'Short' and close_px >= self.boundary_stop
        )
        if not crossed:
            return

        self.exit_unit(0, close_px, close_time, 'Boundary-Close')
        self.exit_unit(1, close_px, close_time, 'Boundary-Close')
        self.boundary_close_taken = True

    def period_close_exit(self, bar, close_time) -> None:
        if self.phase != IN_TRADE:
            return
        self.exit_all_open(float(bar['close']), close_time, 'Period-Close')

    def append_trade(self) -> None:
        assert self.direction is not None and self.entry is not None and self.initial_stop is not None
        assert self.boundary_stop is not None and self.risk is not None and self.source is not None
        assert self.source_stop is not None

        pls = []
        for px in self.unit_exit_px:
            assert px is not None
            if self.direction == 'Long':
                pls.append(float(px) - self.entry)
            else:
                pls.append(self.entry - float(px))

        total_pl = sum(pls)
        account_r = total_pl / (3.0 * self.risk) if self.risk > 0 else math.nan
        reasons = [str(reason) for reason in self.unit_exit_reason]
        final_reason = reasons[-1]
        boundary_close = any(reason == 'Boundary-Close' for reason in reasons)

        if all(reason == 'Initial-Stop' for reason in reasons):
            result = 'Full-Stop'
        elif all(reason == 'Target-1R' for reason in reasons):
            result = 'Target-TP1'
        elif boundary_close and final_reason == 'Target-1R':
            result = 'Boundary-Close-Then-TP1'
        elif boundary_close and final_reason == 'Initial-Stop':
            result = 'Boundary-Close-Then-Stop'
        elif boundary_close and final_reason == 'Period-Close':
            result = 'Boundary-Close-Then-Period-Close'
        elif any(reason == 'Period-Close' for reason in reasons):
            result = 'Period-Close'
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
            'Source_Stop_Price': self.source_stop,
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
            'Boundary_Close_Taken': boundary_close,
            'Boundary_Stop_Activated': False,
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

            self.boundary_close_scaleout(bar, close_time)

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


def run_study(daily: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    grouped = raw.groupby(['date', 'symbol'], sort=False)
    trade_rows = []
    cancel_rows = []
    for period, bars in period_rows(daily):
        sim = BoundaryCloseScaleoutMonth(period, bars, grouped, restricted=True)
        trade_rows.extend(sim.run())
        cancel_rows.extend(sim.cancelled_stale_orders)
    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades['Cumulative_PL'] = trades['Trade_PL'].astype(float).cumsum().round(6)
    return trades, pd.DataFrame(cancel_rows)


def summarize_boundary(df: pd.DataFrame, multiplier: float = 2.0) -> dict:
    pnl = df['Trade_PL'].astype(float) if not df.empty else pd.Series(dtype=float)
    account_r = pd.to_numeric(df.get('Account_R', pd.Series(dtype=float)), errors='coerce') if not df.empty else pd.Series(dtype=float)
    unit_reason_cols = ['Unit1_Exit_Reason', 'Unit2_Exit_Reason', 'Unit3_Exit_Reason']
    reasons = df[unit_reason_cols].astype(str) if not df.empty else pd.DataFrame(columns=unit_reason_cols)
    target_tp1 = reasons.apply(lambda row: row.str.startswith('Target-1R').any(), axis=1).sum() if not reasons.empty else 0
    boundary_close = reasons.apply(lambda row: (row == 'Boundary-Close').any(), axis=1).sum() if not reasons.empty else 0
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
        'target_tp1_trades': int(target_tp1),
        'direct_tp1': int((df['Result'] == 'Target-TP1').sum()) if not df.empty else 0,
        'boundary_close_then_tp1': int((df['Result'] == 'Boundary-Close-Then-TP1').sum()) if not df.empty else 0,
        'boundary_close_then_stop': int((df['Result'] == 'Boundary-Close-Then-Stop').sum()) if not df.empty else 0,
        'boundary_close_then_period': int((df['Result'] == 'Boundary-Close-Then-Period-Close').sum()) if not df.empty else 0,
        'boundary_close_trades': int(boundary_close),
        'full_stops': int((df['Result'] == 'Full-Stop').sum()) if not df.empty else 0,
        'period_closes': int((df['Result'] == 'Period-Close').sum()) if not df.empty else 0,
    }


def write_report(trades: pd.DataFrame, cancels: pd.DataFrame, trade_path: Path, cancel_path: Path) -> None:
    s = summarize_boundary(trades)
    lines = [
        '# Inside Restricted Boundary-Close Scaleout TP1 Wide-Stop Study',
        '',
        'This is a restricted-only branch of the causal monthly ORB inside-candle-open study.',
        '',
        'Rules in this study:',
        '',
        '- Entry remains the causal inside opposite candle/run open limit after a valid monthly OR breakout close.',
        '- Pending limits are cancelled if TP1 trades before the limit fills; the strategy then waits for a new setup.',
        '- Initial stop is one monthly range beyond the selected source stop: long = source stop - range; short = source stop + range.',
        '- TP1 is the first monthly measured move: long = range high + range; short = range low - range.',
        '- If a daily close crosses back through the breakout boundary, two contracts are closed at that daily close.',
        '- The final contract remains open for TP1, the wide initial stop, or period close.',
        '',
        'Boundary close means close <= monthly OR high for longs, and close >= monthly OR low for shorts. Intraday stop/target events are processed before the daily close scaleout.',
        '',
        '| Trades | Cancelled stale limits | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | TP1 trades | Direct TP1 | Boundary close -> TP1 | Boundary close -> stop | Boundary close -> period | Boundary close trades | Full stops | Period closes |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        (
            f"| {s['trades']} | {len(cancels)} | {fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | "
            f"{fmt_money(s['net_per_contract_usd'])} | {fmt_money(s['dd_per_contract_usd'])} | "
            f"{fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | {fmt_num(s['avg_trade_pts'])} | "
            f"{fmt_num(s['avg_account_r'])} | {s['target_tp1_trades']} | {s['direct_tp1']} | "
            f"{s['boundary_close_then_tp1']} | {s['boundary_close_then_stop']} | "
            f"{s['boundary_close_then_period']} | {s['boundary_close_trades']} | "
            f"{s['full_stops']} | {s['period_closes']} |"
        ),
        '',
        '## Outputs',
        '',
        f'- Trades CSV: `{trade_path}`',
        f'- Cancelled stale limits CSV: `{cancel_path}`',
        '',
    ]
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

    trades, cancels = run_study(daily, raw)
    trade_path = MNQ_ROOT / 'mnq_monthly_orb_inside_restricted_boundary_close_scaleout_tp1_wide_stop_intraday.csv'
    cancel_path = MNQ_ROOT / 'mnq_monthly_orb_inside_restricted_boundary_close_scaleout_tp1_wide_stop_cancelled_limits_intraday.csv'
    trades.to_csv(trade_path, index=False)
    cancels.to_csv(cancel_path, index=False)
    write_report(trades, cancels, trade_path, cancel_path)

    s = summarize_boundary(trades)
    print(
        f"restricted boundary-close scaleout TP1 wide-stop: {fmt_money(s['net_usd'])}, "
        f"DD {fmt_money(s['dd_usd'])}, WR {fmt_pct(s['win_rate'])}, PF {fmt_num(s['pf'])}, "
        f"TP1 {s['target_tp1_trades']}, boundary-close trades {s['boundary_close_trades']}, "
        f"cancelled {len(cancels)}, wrote {trade_path}"
    )
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
