#!/usr/bin/env python3
"""Restricted monthly ORB half-stop-close scaleout study."""
from __future__ import annotations

from pathlib import Path
import argparse
import math
import sys

import pandas as pd

from monthly_orb_intraday_boundary_close_scaleout import (
    BoundaryCloseScaleoutMonth,
    summarize_boundary,
)
from monthly_orb_intraday_ladder3_validate import max_drawdown, profit_factor
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
    load_daily,
    load_raw_1m,
    period_rows,
)


REPORT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'INSIDE_RESTRICTED_SL_HALF_CLOSE_SCALEOUT_TP1_WIDE_STOP_STUDY.md'


class SLHalfCloseScaleoutMonth(BoundaryCloseScaleoutMonth):
    """Scale out two units only after a close strictly beyond halfway to stop."""

    def sl_half_level(self) -> float:
        assert self.direction is not None and self.entry is not None and self.risk is not None
        if self.direction == 'Long':
            return self.entry - 0.5 * self.risk
        return self.entry + 0.5 * self.risk

    def boundary_close_scaleout(self, bar, close_time) -> None:
        if self.phase != IN_TRADE or self.boundary_close_taken:
            return
        if self.unit_exit_px[0] is not None or self.unit_exit_px[1] is not None:
            return
        assert self.direction is not None

        close_px = float(bar['close'])
        half_level = self.sl_half_level()
        crossed = (self.direction == 'Long' and close_px < half_level) or (
            self.direction == 'Short' and close_px > half_level
        )
        if not crossed:
            return

        self.exit_unit(0, close_px, close_time, 'SL-Half-Close')
        self.exit_unit(1, close_px, close_time, 'SL-Half-Close')
        self.boundary_close_taken = True

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
        half_close = any(reason == 'SL-Half-Close' for reason in reasons)

        if all(reason == 'Initial-Stop' for reason in reasons):
            result = 'Full-Stop'
        elif all(reason == 'Target-1R' for reason in reasons):
            result = 'Target-TP1'
        elif half_close and final_reason == 'Target-1R':
            result = 'SL-Half-Close-Then-TP1'
        elif half_close and final_reason == 'Initial-Stop':
            result = 'SL-Half-Close-Then-Stop'
        elif half_close and final_reason == 'Period-Close':
            result = 'SL-Half-Close-Then-Period-Close'
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
            'SL_Half_Close_Price': self.sl_half_level(),
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
            'SL_Half_Close_Taken': half_close,
            'Boundary_Close_Taken': False,
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


def run_study(daily: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    grouped = raw.groupby(['date', 'symbol'], sort=False)
    trade_rows = []
    cancel_rows = []
    for period, bars in period_rows(daily):
        sim = SLHalfCloseScaleoutMonth(period, bars, grouped, restricted=True)
        trade_rows.extend(sim.run())
        cancel_rows.extend(sim.cancelled_stale_orders)
    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades['Cumulative_PL'] = trades['Trade_PL'].astype(float).cumsum().round(6)
    return trades, pd.DataFrame(cancel_rows)


def summarize_half(df: pd.DataFrame, multiplier: float = 2.0) -> dict:
    base = summarize_boundary(df, multiplier)
    if df.empty:
        base.update({
            'sl_half_close_trades': 0,
            'sl_half_close_then_tp1': 0,
            'sl_half_close_then_stop': 0,
            'sl_half_close_then_period': 0,
        })
        return base
    unit_reason_cols = ['Unit1_Exit_Reason', 'Unit2_Exit_Reason', 'Unit3_Exit_Reason']
    reasons = df[unit_reason_cols].astype(str)
    base.update({
        'sl_half_close_trades': int(reasons.apply(lambda row: (row == 'SL-Half-Close').any(), axis=1).sum()),
        'sl_half_close_then_tp1': int((df['Result'] == 'SL-Half-Close-Then-TP1').sum()),
        'sl_half_close_then_stop': int((df['Result'] == 'SL-Half-Close-Then-Stop').sum()),
        'sl_half_close_then_period': int((df['Result'] == 'SL-Half-Close-Then-Period-Close').sum()),
    })
    return base


def write_report(trades: pd.DataFrame, cancels: pd.DataFrame, trade_path: Path, cancel_path: Path) -> None:
    s = summarize_half(trades)
    lines = [
        '# Inside Restricted SL-Half-Close Scaleout TP1 Wide-Stop Study',
        '',
        'This branch tests a deeper restriction trigger than boundary close.',
        '',
        'Rules in this study:',
        '',
        '- Entry remains the causal inside opposite candle/run open limit after a valid monthly OR breakout close.',
        '- Pending limits are cancelled if TP1 trades before the limit fills; the strategy then waits for a new setup.',
        '- Initial stop is one monthly range beyond the selected source stop: long = source stop - range; short = source stop + range.',
        '- The half-stop scaleout level is halfway between entry and the wide initial stop.',
        '- Two contracts are closed only when the daily close is strictly more than halfway to the stop: long close < halfway level; short close > halfway level.',
        '- The final contract remains open for TP1, the wide initial stop, or period close.',
        '',
        'Intraday stop/target events are processed before the daily close scaleout.',
        '',
        '| Trades | Cancelled stale limits | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | TP1 trades | Direct TP1 | SL-half close -> TP1 | SL-half close -> stop | SL-half close -> period | SL-half close trades | Full stops | Period closes |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        (
            f"| {s['trades']} | {len(cancels)} | {fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | "
            f"{fmt_money(s['net_per_contract_usd'])} | {fmt_money(s['dd_per_contract_usd'])} | "
            f"{fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | {fmt_num(s['avg_trade_pts'])} | "
            f"{fmt_num(s['avg_account_r'])} | {s['target_tp1_trades']} | {s['direct_tp1']} | "
            f"{s['sl_half_close_then_tp1']} | {s['sl_half_close_then_stop']} | "
            f"{s['sl_half_close_then_period']} | {s['sl_half_close_trades']} | "
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
    trade_path = MNQ_ROOT / 'mnq_monthly_orb_inside_restricted_sl_half_close_scaleout_tp1_wide_stop_intraday.csv'
    cancel_path = MNQ_ROOT / 'mnq_monthly_orb_inside_restricted_sl_half_close_scaleout_tp1_wide_stop_cancelled_limits_intraday.csv'
    trades.to_csv(trade_path, index=False)
    cancels.to_csv(cancel_path, index=False)
    write_report(trades, cancels, trade_path, cancel_path)

    s = summarize_half(trades)
    print(
        f"restricted SL-half-close scaleout TP1 wide-stop: {fmt_money(s['net_usd'])}, "
        f"DD {fmt_money(s['dd_usd'])}, WR {fmt_pct(s['win_rate'])}, PF {fmt_num(s['pf'])}, "
        f"TP1 {s['target_tp1_trades']}, SL-half-close trades {s['sl_half_close_trades']}, "
        f"cancelled {len(cancels)}, wrote {trade_path}"
    )
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
