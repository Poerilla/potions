#!/usr/bin/env python3
"""Scale-out study for monthly ORB inside-candle-open source-stop entries."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import argparse
import math

import pandas as pd


ROOT = Path('/home/tester/hsm/potions')
REPORT = ROOT / 'mnq' / 'case_studies' / 'monthly_orb' / 'INSIDE_CANDLE_SOURCE_STOP_SCALEOUT_STUDY.md'
DEFAULT_RUNS = [
    ('MNQ', ROOT / 'mnq' / 'mnq_daily.csv', ROOT / 'mnq', 2.0),
    ('NQ', ROOT / 'nq' / 'nq_daily.csv', ROOT / 'nq', 20.0),
]

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_PERIOD = 2


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


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


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


def simulate_month(
    period: str,
    bars: pd.DataFrame,
    *,
    restricted: bool,
    runner_r: float,
) -> list[dict]:
    range_bars = bars.iloc[:3]
    trade_bars = bars.iloc[3:].reset_index(drop=True)
    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    symbol = str(range_bars.iloc[0]['symbol'])
    if range_val <= 0:
        return []

    phase = WAIT_BREAKOUT
    direction = None
    limit_price = stop = risk = None
    first_target = runner_target = None
    breakout_date = entry_date = None
    source = None
    partial_done = False
    partial_exit_date = None
    runner_exit_date = None
    runner_exit_price = None
    runner_exit_reason = None
    max_adverse_pts = 0.0
    trades: list[dict] = []
    history = [row for _, row in range_bars.iterrows()]

    def valid_long_breakout(row) -> bool:
        return float(row['close']) > range_high and float(row['close']) > float(row['open'])

    def valid_short_breakout(row) -> bool:
        return float(row['close']) < range_low and float(row['close']) < float(row['open'])

    def reset_to_breakout() -> None:
        nonlocal phase, direction, limit_price, stop, risk, first_target, runner_target
        nonlocal breakout_date, entry_date, source, partial_done, partial_exit_date
        nonlocal runner_exit_date, runner_exit_price, runner_exit_reason, max_adverse_pts
        phase = WAIT_BREAKOUT
        direction = None
        limit_price = stop = risk = None
        first_target = runner_target = None
        breakout_date = entry_date = None
        source = None
        partial_done = False
        partial_exit_date = None
        runner_exit_date = runner_exit_price = runner_exit_reason = None
        max_adverse_pts = 0.0

    def arm_order(new_direction: str, bar) -> bool:
        nonlocal phase, direction, limit_price, stop, risk, first_target, runner_target
        nonlocal breakout_date, source, partial_done, partial_exit_date
        found = inside_opposite_entry(history, new_direction, range_high, range_low)
        if found is None:
            return False
        entry = float(found['price'])
        if new_direction == 'Long':
            new_stop = float(found['run_low'])
            new_risk = entry - new_stop
            if new_risk <= 0:
                return False
            first = entry + new_risk
            runner = entry + runner_r * new_risk
        else:
            new_stop = float(found['run_high'])
            new_risk = new_stop - entry
            if new_risk <= 0:
                return False
            first = entry - new_risk
            runner = entry - runner_r * new_risk

        direction = new_direction
        limit_price = entry
        stop = new_stop
        risk = new_risk
        first_target = first
        runner_target = runner
        breakout_date = bar['date']
        source = found
        partial_done = False
        partial_exit_date = None
        phase = WAIT_FILL
        return True

    def append_trade(exit_date, exit_reason: str, first_exit_reason: str, second_exit_price: float, second_exit_reason: str) -> None:
        assert direction is not None and limit_price is not None and stop is not None and risk is not None
        assert first_target is not None and runner_target is not None and source is not None
        if direction == 'Long':
            first_pl = first_target - limit_price if partial_done else second_exit_price - limit_price
            second_pl = second_exit_price - limit_price
        else:
            first_pl = limit_price - first_target if partial_done else limit_price - second_exit_price
            second_pl = limit_price - second_exit_price
        total_pl = first_pl + second_pl
        account_r = total_pl / (2.0 * risk) if risk > 0 else math.nan
        trades.append({
            'Period': period,
            'Range_High': range_high,
            'Range_Low': range_low,
            'Range': range_val,
            'Trade_Direction': direction,
            'Units': 2,
            'Entry_Price': limit_price,
            'Initial_Stop_Price': stop,
            'Risk_Pts': risk,
            'First_Target_Price': first_target,
            'Runner_Target_Price': runner_target,
            'Runner_R_Target': runner_r,
            'First_Exit_Price': first_target if partial_done else second_exit_price,
            'First_Exit_Date': partial_exit_date if partial_done else exit_date,
            'First_Exit_Reason': first_exit_reason,
            'Runner_Exit_Price': second_exit_price,
            'Runner_Exit_Date': exit_date,
            'Runner_Exit_Reason': second_exit_reason,
            'Exit_Price': second_exit_price,
            'Exit_Date': exit_date,
            'Breakout_Date': breakout_date,
            'Entry_Date': entry_date,
            'Trade_PL': round(total_pl, 6),
            'First_Unit_PL': round(first_pl, 6),
            'Runner_PL': round(second_pl, 6),
            'Account_R': round(account_r, 6) if not math.isnan(account_r) else None,
            'MAE_Pts': round(max_adverse_pts, 6),
            'MAE_R': round(max_adverse_pts / risk, 6) if risk > 0 else None,
            'Result': exit_reason,
            'Symbol': symbol,
            'Range_Days': 3,
            'Trade_Days': len(trade_bars),
            'Entry_Source': 'inside_opposite_open',
            'Entry_Source_Start': source['start'],
            'Entry_Source_End': source['end'],
            'Entry_Source_Date': source['date'],
            'Entry_Source_Count': source['count'],
            'Entry_Source_Open': source['open'],
            'Entry_Source_High': source['high'],
            'Entry_Source_Low': source['low'],
            'Entry_Source_Close': source['close'],
            'Entry_Source_Run_High': source['run_high'],
            'Entry_Source_Run_Low': source['run_low'],
        })

    def update_mae(h: float, l: float) -> None:
        nonlocal max_adverse_pts
        assert direction is not None and limit_price is not None
        if direction == 'Long':
            max_adverse_pts = max(max_adverse_pts, max(0.0, limit_price - l))
        else:
            max_adverse_pts = max(max_adverse_pts, max(0.0, h - limit_price))

    for _, bar in trade_bars.iterrows():
        history.append(bar)
        if len(trades) >= MAX_TRADES_PER_PERIOD and phase != IN_TRADE:
            break

        h = float(bar['high'])
        l = float(bar['low'])
        c = float(bar['close'])
        d = bar['date']

        if phase == WAIT_FILL:
            assert direction is not None and limit_price is not None
            filled = (direction == 'Long' and l <= limit_price) or (direction == 'Short' and h >= limit_price)
            if filled:
                entry_date = d
                partial_done = False
                partial_exit_date = None
                max_adverse_pts = 0.0
                phase = IN_TRADE

        if phase == IN_TRADE:
            assert direction is not None and limit_price is not None and stop is not None
            assert first_target is not None and runner_target is not None and risk is not None
            update_mae(h, l)
            if direction == 'Long':
                if not partial_done:
                    if l <= stop:
                        append_trade(d, 'Full-Stop', 'Initial_Stop', stop, 'Initial_Stop')
                        reset_to_breakout()
                    elif h >= first_target:
                        partial_done = True
                        partial_exit_date = d
                        if h >= runner_target:
                            append_trade(d, f'Runner-{runner_r:g}R', 'First_1R', runner_target, f'Runner_{runner_r:g}R')
                            reset_to_breakout()
                        elif restricted and range_low <= c <= range_high:
                            append_trade(d, 'Range-Close', 'First_1R', c, 'Close_Back_Inside_Range')
                            reset_to_breakout()
                    elif restricted and range_low <= c <= range_high:
                        append_trade(d, 'Range-Close', 'Close_Back_Inside_Range', c, 'Close_Back_Inside_Range')
                        reset_to_breakout()
                else:
                    if l <= limit_price:
                        append_trade(d, 'Runner-BE', 'First_1R', limit_price, 'Breakeven_Stop')
                        reset_to_breakout()
                    elif h >= runner_target:
                        append_trade(d, f'Runner-{runner_r:g}R', 'First_1R', runner_target, f'Runner_{runner_r:g}R')
                        reset_to_breakout()
                    elif restricted and range_low <= c <= range_high:
                        append_trade(d, 'Range-Close', 'First_1R', c, 'Close_Back_Inside_Range')
                        reset_to_breakout()
            else:
                if not partial_done:
                    if h >= stop:
                        append_trade(d, 'Full-Stop', 'Initial_Stop', stop, 'Initial_Stop')
                        reset_to_breakout()
                    elif l <= first_target:
                        partial_done = True
                        partial_exit_date = d
                        if l <= runner_target:
                            append_trade(d, f'Runner-{runner_r:g}R', 'First_1R', runner_target, f'Runner_{runner_r:g}R')
                            reset_to_breakout()
                        elif restricted and range_low <= c <= range_high:
                            append_trade(d, 'Range-Close', 'First_1R', c, 'Close_Back_Inside_Range')
                            reset_to_breakout()
                    elif restricted and range_low <= c <= range_high:
                        append_trade(d, 'Range-Close', 'Close_Back_Inside_Range', c, 'Close_Back_Inside_Range')
                        reset_to_breakout()
                else:
                    if h >= limit_price:
                        append_trade(d, 'Runner-BE', 'First_1R', limit_price, 'Breakeven_Stop')
                        reset_to_breakout()
                    elif l <= runner_target:
                        append_trade(d, f'Runner-{runner_r:g}R', 'First_1R', runner_target, f'Runner_{runner_r:g}R')
                        reset_to_breakout()
                    elif restricted and range_low <= c <= range_high:
                        append_trade(d, 'Range-Close', 'First_1R', c, 'Close_Back_Inside_Range')
                        reset_to_breakout()

        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_PERIOD:
            if valid_long_breakout(bar):
                arm_order('Long', bar)
            elif valid_short_breakout(bar):
                arm_order('Short', bar)

    if phase == IN_TRADE and len(trade_bars) > 0:
        assert direction is not None
        last = trade_bars.iloc[-1]
        last_close = float(last['close'])
        if partial_done:
            append_trade(last['date'], 'Period-Close', 'First_1R', last_close, 'Period_Close')
        else:
            append_trade(last['date'], 'Period-Close', 'Period_Close', last_close, 'Period_Close')

    return trades


def run_study(df: pd.DataFrame, *, restricted: bool, runner_r: float) -> pd.DataFrame:
    rows = []
    for period, bars in period_rows(df):
        rows.extend(simulate_month(period, bars, restricted=restricted, runner_r=runner_r))
    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum().round(6)
    return out


def summarize(df: pd.DataFrame, multiplier: float) -> dict:
    pnl = df['Trade_PL'].astype(float) if not df.empty else pd.Series(dtype=float)
    account_r = pd.to_numeric(df.get('Account_R', pd.Series(dtype=float)), errors='coerce') if not df.empty else pd.Series(dtype=float)
    mae_r = pd.to_numeric(df.get('MAE_R', pd.Series(dtype=float)), errors='coerce') if not df.empty else pd.Series(dtype=float)
    runner_reasons = df['Runner_Exit_Reason'] if 'Runner_Exit_Reason' in df else pd.Series(dtype=str)
    wins = df[pnl > 0].copy() if not df.empty else pd.DataFrame()
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float((pnl * multiplier).sum()),
        'max_dd_pts': max_drawdown(pnl),
        'max_dd_usd': max_drawdown(pnl * multiplier),
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'profit_factor': profit_factor(pnl),
        'avg_trade_pts': float(pnl.mean()) if len(pnl) else math.nan,
        'avg_account_r': float(account_r.mean()) if len(account_r) else math.nan,
        'median_account_r': float(account_r.median()) if len(account_r) else math.nan,
        'avg_mae_r': float(mae_r.mean()) if len(mae_r) else math.nan,
        'median_mae_r': float(mae_r.median()) if len(mae_r) else math.nan,
        'full_stops': int((df['Result'] == 'Full-Stop').sum()) if 'Result' in df else 0,
        'first_1r_hits': int((df['First_Exit_Reason'] == 'First_1R').sum()) if 'First_Exit_Reason' in df else 0,
        'runner_be': int((runner_reasons == 'Breakeven_Stop').sum()),
        'range_close': int((df['Result'] == 'Range-Close').sum()) if 'Result' in df else 0,
        'period_close': int((df['Result'] == 'Period-Close').sum()) if 'Result' in df else 0,
        'runner_target': int(runner_reasons.astype(str).str.startswith('Runner_').sum()) if len(runner_reasons) else 0,
        'winning_trades': int((pnl > 0).sum()),
        'wins_account_ge_1r': int(((pnl > 0) & (account_r >= 1.0)).sum()) if len(account_r) else 0,
        'wins_account_ge_1_5r': int(((pnl > 0) & (account_r >= 1.5)).sum()) if len(account_r) else 0,
        'wins_account_ge_2r': int(((pnl > 0) & (account_r >= 2.0)).sum()) if len(account_r) else 0,
        'wins_runner_ge_2r': int((wins['Runner_R_Target'].astype(float) >= 2.0).sum()) if not wins.empty else 0,
        'wins_runner_target': int(wins['Runner_Exit_Reason'].astype(str).str.startswith('Runner_').sum()) if not wins.empty else 0,
    }


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


def write_report(results: list[dict]) -> None:
    lines = [
        '# Inside-Candle Source-Stop Scale-Out Study',
        '',
        'Entry is the causal inside-candle-open monthly ORB source-stop setup. This study uses two units per trade package: one unit exits at 1R, then the remaining unit moves its stop to breakeven and targets either 2R or 3R.',
        '',
        'Restricted keeps the daily close-back-inside monthly range exit. Unrestricted does not. Results are gross, before commissions/slippage. Daily OHLC cannot prove same-day ordering between 1R, BE, and runner targets, so this remains a research approximation.',
        '',
        '## Summary',
        '',
        '| Instrument | Variant | Runner target | Trades | Net | Max DD | Win rate | PF | Avg/trade pts | Avg acct R | Median acct R | Avg MAE R | 1R hits | Full stops | Runner target hits | Runner BE | Range closes |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in results:
        s = row['stats']
        lines.append(
            f"| {row['instrument']} | {row['variant']} | {row['runner_r']:g}R | {s['trades']} | "
            f"{fmt_money(s['net_usd'])} | {fmt_money(s['max_dd_usd'])} | {fmt_pct(s['win_rate'])} | "
            f"{fmt_num(s['profit_factor'])} | {fmt_num(s['avg_trade_pts'])} | {fmt_num(s['avg_account_r'])} | "
            f"{fmt_num(s['median_account_r'])} | {fmt_num(s['avg_mae_r'])} | {s['first_1r_hits']} | "
            f"{s['full_stops']} | {s['runner_target']} | {s['runner_be']} | {s['range_close']} |"
        )
    lines.extend([
        '',
        '## Winning Trade R Counts',
        '',
        'Account R is total package P/L divided by initial risk on both units. A 1R partial plus a 2R runner is +1.5 account R; a 1R partial plus a 3R runner is +2.0 account R.',
        '',
        '| Instrument | Variant | Runner target | Winning trades | Wins >=1 account R | Wins >=1.5 account R | Wins >=2 account R | Runner target wins |',
        '|---|---|---:|---:|---:|---:|---:|---:|',
    ])
    for row in results:
        s = row['stats']
        lines.append(
            f"| {row['instrument']} | {row['variant']} | {row['runner_r']:g}R | {s['winning_trades']} | "
            f"{s['wins_account_ge_1r']} | {s['wins_account_ge_1_5r']} | {s['wins_account_ge_2r']} | "
            f"{s['wins_runner_target']} |"
        )
    lines.extend([
        '',
        '## Output CSVs',
        '',
    ])
    for row in results:
        lines.append(f"- {row['instrument']} {row['variant']} {row['runner_r']:g}R: `{row['path']}`")
    lines.append('')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def run_one(instrument: str, daily_path: Path, out_dir: Path, multiplier: float) -> list[dict]:
    daily = load_daily(daily_path)
    prefix = instrument.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for restricted in (False, True):
        for runner_r in (2.0, 3.0):
            label = 'restricted source-stop scaleout' if restricted else 'unrestricted source-stop scaleout'
            suffix = 'restricted_source_stop' if restricted else 'source_stop'
            filename = f'{prefix}_monthly_orb_inside_candle_open_{suffix}_scaleout_{int(runner_r)}r.csv'
            out = run_study(daily, restricted=restricted, runner_r=runner_r)
            path = out_dir / filename
            out.to_csv(path, index=False)
            results.append({
                'instrument': instrument,
                'variant': label,
                'runner_r': runner_r,
                'stats': summarize(out, multiplier),
                'path': str(path),
            })
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--instrument', choices=['MNQ', 'NQ', 'all'], default='all')
    ap.add_argument('--daily', type=Path, default=None)
    ap.add_argument('--out-dir', type=Path, default=None)
    ap.add_argument('--multiplier', type=float, default=None)
    ap.add_argument('--no-report', action='store_true')
    args = ap.parse_args()

    if args.instrument == 'all':
        runs = DEFAULT_RUNS
    else:
        default = next(r for r in DEFAULT_RUNS if r[0] == args.instrument)
        runs = [(
            args.instrument,
            args.daily or default[1],
            args.out_dir or default[2],
            args.multiplier if args.multiplier is not None else default[3],
        )]

    all_results = []
    for instrument, daily_path, out_dir, multiplier in runs:
        rows = run_one(instrument, daily_path, out_dir, multiplier)
        all_results.extend(rows)
        print(instrument)
        for row in rows:
            s = row['stats']
            print(
                f"  {row['variant']} {row['runner_r']:g}R: {s['net_pts']:,.2f} package-pts "
                f"{fmt_money(s['net_usd'])}, DD {s['max_dd_pts']:,.2f} package-pts "
                f"{fmt_money(s['max_dd_usd'])}, WR {fmt_pct(s['win_rate'])}, "
                f"PF {fmt_num(s['profit_factor'])}, trades {s['trades']}, "
                f"runner hits {s['runner_target']}"
            )
            print(f"  wrote {row['path']}")

    if not args.no_report:
        write_report(all_results)
        print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
