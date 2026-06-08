#!/usr/bin/env python3
"""Monthly ORB variant with daily-close failure exits.

Rules are the same as ``daily_orb.py`` monthly ORB except an open position is
closed at the daily close when price closes back inside the monthly opening
range. The opening range is still the first 3 trading days of the month, entry
is still the range boundary after a close-based breakout, target is still 1R,
stop is still the opposite boundary, and each month still allows max 2 trades.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import argparse
import math

import pandas as pd


ROOT = Path('/home/tester/hsm/potions')
DEFAULT_RUNS = [
    ('MNQ', ROOT / 'mnq' / 'mnq_daily.csv', ROOT / 'mnq' / 'mnq_monthly_orb_restricted.csv', 2.0),
    ('NQ', ROOT / 'nq' / 'nq_daily.csv', ROOT / 'nq' / 'nq_monthly_orb_restricted.csv', 20.0),
]
REPORT = ROOT / 'mnq' / 'case_studies' / 'monthly_orb' / 'MONTHLY_ORB_RESTRICTED.md'

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


def parse_period_start(value: object) -> pd.Timestamp:
    return pd.to_datetime(f'{value}-01')


def simulate_month_restricted(range_high: float, range_low: float, range_val: float, trade_bars: pd.DataFrame) -> list[dict]:
    phase = WAIT_BREAKOUT
    direction = None
    entry = target = stop = None
    entry_date = None
    max_dd = 0.0
    trades: list[dict] = []

    for _, bar in trade_bars.iterrows():
        if len(trades) >= MAX_TRADES_PER_PERIOD and phase != IN_TRADE:
            break

        h = float(bar['high'])
        l = float(bar['low'])
        c = float(bar['close'])
        d = bar['date']

        if phase == WAIT_FILL:
            filled = False
            if direction == 'Long' and l <= range_high:
                entry, target, stop = range_high, range_high + range_val, range_low
                entry_date = d
                filled = True
            elif direction == 'Short' and h >= range_low:
                entry, target, stop = range_low, range_low - range_val, range_high
                entry_date = d
                filled = True

            if filled:
                phase = IN_TRADE
                max_dd = 0.0
            else:
                if direction == 'Long' and c < range_low:
                    direction = 'Short'
                elif direction == 'Short' and c > range_high:
                    direction = 'Long'

        if phase == IN_TRADE:
            if direction == 'Long':
                assert entry is not None and target is not None and stop is not None
                if l < stop:
                    trades.append({
                        'direction': 'Long',
                        'entry': entry,
                        'exit_price': stop,
                        'drawdown_pct': 100.0,
                        'result': 'Loss',
                        'entry_date': entry_date,
                        'exit_date': d,
                        'exit_reason': 'Stop',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif h >= target:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    trades.append({
                        'direction': 'Long',
                        'entry': entry,
                        'exit_price': target,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': 'Win',
                        'entry_date': entry_date,
                        'exit_date': d,
                        'exit_reason': 'Target',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif range_low <= c <= range_high:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    trades.append({
                        'direction': 'Long',
                        'entry': entry,
                        'exit_price': c,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': 'Range-Close',
                        'entry_date': entry_date,
                        'exit_date': d,
                        'exit_reason': 'Close_Back_Inside_Range',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    continue
            else:
                assert entry is not None and target is not None and stop is not None
                if h > stop:
                    trades.append({
                        'direction': 'Short',
                        'entry': entry,
                        'exit_price': stop,
                        'drawdown_pct': 100.0,
                        'result': 'Loss',
                        'entry_date': entry_date,
                        'exit_date': d,
                        'exit_reason': 'Stop',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif l <= target:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    trades.append({
                        'direction': 'Short',
                        'entry': entry,
                        'exit_price': target,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': 'Win',
                        'entry_date': entry_date,
                        'exit_date': d,
                        'exit_reason': 'Target',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif range_low <= c <= range_high:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    trades.append({
                        'direction': 'Short',
                        'entry': entry,
                        'exit_price': c,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': 'Range-Close',
                        'entry_date': entry_date,
                        'exit_date': d,
                        'exit_reason': 'Close_Back_Inside_Range',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    continue

        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_PERIOD:
            if c > range_high:
                direction = 'Long'
                if l <= range_high:
                    entry, target, stop = range_high, range_high + range_val, range_low
                    entry_date = d
                    phase = IN_TRADE
                    max_dd = 0.0
                    continue
                phase = WAIT_FILL
            elif c < range_low:
                direction = 'Short'
                if h >= range_low:
                    entry, target, stop = range_low, range_low - range_val, range_high
                    entry_date = d
                    phase = IN_TRADE
                    max_dd = 0.0
                    continue
                phase = WAIT_FILL

    if phase == IN_TRADE and len(trade_bars) > 0:
        last = trade_bars.iloc[-1]
        trades.append({
            'direction': direction,
            'entry': entry,
            'exit_price': float(last['close']),
            'drawdown_pct': round(max_dd * 100, 2),
            'result': 'Period-Close',
            'entry_date': entry_date,
            'exit_date': last['date'],
            'exit_reason': 'Period_Close',
        })

    return trades


def run_monthly_orb_restricted(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ym'] = df['date'].apply(lambda d: (d.year, d.month))

    periods: OrderedDict[tuple[int, int], list[pd.Series]] = OrderedDict()
    for _, row in df.iterrows():
        periods.setdefault(row['ym'], []).append(row)

    rows: list[dict] = []
    for (yr, mo), bars in periods.items():
        bars_df = pd.DataFrame(bars)
        if len(bars_df) < 4:
            continue

        range_bars = bars_df.iloc[:3]
        trade_bars = bars_df.iloc[3:].reset_index(drop=True)
        range_high = float(range_bars['high'].max())
        range_low = float(range_bars['low'].min())
        range_val = range_high - range_low
        symbol = str(range_bars.iloc[0]['symbol'])
        period_label = f'{yr}-{mo:02d}'

        def append_noop(result: str) -> None:
            rows.append({
                'Period': period_label,
                'Range_High': range_high,
                'Range_Low': range_low,
                'Range': max(range_val, 0.0),
                'Trade_Direction': 'No-Op',
                'Entry_Price': None,
                'Exit_Price': None,
                'Trade_PL': 0.0,
                'Drawdown_Pct': 0.0,
                'Result': result,
                'Symbol': symbol,
                'Range_Days': 3,
                'Trade_Days': len(trade_bars),
                'Entry_Date': None,
                'Exit_Date': None,
                'Exit_Reason': result,
            })

        if range_val <= 0:
            append_noop('No-Op')
            continue

        trades = simulate_month_restricted(range_high, range_low, range_val, trade_bars)
        if not trades:
            append_noop('No-Op')
            continue

        for trade in trades:
            direction = trade['direction']
            entry = trade['entry']
            exit_price = trade['exit_price']
            pl = (exit_price - entry) if direction == 'Long' else (entry - exit_price)
            rows.append({
                'Period': period_label,
                'Range_High': range_high,
                'Range_Low': range_low,
                'Range': range_val,
                'Trade_Direction': direction,
                'Entry_Price': entry,
                'Exit_Price': exit_price,
                'Trade_PL': round(pl, 6),
                'Drawdown_Pct': trade['drawdown_pct'],
                'Result': trade['result'],
                'Symbol': symbol,
                'Range_Days': 3,
                'Trade_Days': len(trade_bars),
                'Entry_Date': trade['entry_date'],
                'Exit_Date': trade['exit_date'],
                'Exit_Reason': trade['exit_reason'],
            })

    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum().round(6)
    return out


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def summarize(df: pd.DataFrame, multiplier: float) -> dict:
    if df.empty:
        return {
            'periods': 0,
            'trades': 0,
            'net_pts': 0.0,
            'net_usd': 0.0,
            'max_dd_pts': 0.0,
            'max_dd_usd': 0.0,
            'win_rate': math.nan,
            'profit_factor': math.nan,
            'avg_trade_pts': math.nan,
            'range_close_trades': 0,
        }

    trades = df[df['Trade_Direction'] != 'No-Op'].copy()
    pnl = trades['Trade_PL'].astype(float)
    return {
        'periods': int(df['Period'].nunique()),
        'trades': int(len(trades)),
        'net_pts': float(pnl.sum()),
        'net_usd': float((pnl * multiplier).sum()),
        'max_dd_pts': max_drawdown(pnl),
        'max_dd_usd': max_drawdown(pnl * multiplier),
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'profit_factor': profit_factor(pnl),
        'avg_trade_pts': float(pnl.mean()) if len(pnl) else math.nan,
        'range_close_trades': int((trades['Result'] == 'Range-Close').sum()),
        'no_op_periods': int((df['Trade_Direction'] == 'No-Op').sum()),
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


def compare_with_baseline(label: str, restricted: pd.DataFrame, baseline_path: Path, multiplier: float) -> tuple[dict, dict]:
    baseline = pd.read_csv(baseline_path)
    return summarize(baseline, multiplier), summarize(restricted, multiplier)


def write_report(results: list[dict]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Monthly ORB Restricted',
        '',
        'Restricted rule: after a monthly ORB breakout position is open, close it at the daily close if that close returns inside the monthly opening range. Max 2 trades per month and all other monthly ORB mechanics stay the same.',
        '',
        '| Instrument | Variant | Periods | Trades | Range-close exits | Net pts | Net $ | Max DD pts | Max DD $ | Win rate | PF | Avg/trade pts |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in results:
        for variant in ['baseline', 'restricted']:
            stats = row[variant]
            lines.append(
                f"| {row['instrument']} | {variant} | {stats['periods']} | {stats['trades']} | "
                f"{stats['range_close_trades']} | {stats['net_pts']:,.2f} | {fmt_money(stats['net_usd'])} | "
                f"{stats['max_dd_pts']:,.2f} | {fmt_money(stats['max_dd_usd'])} | "
                f"{fmt_pct(stats['win_rate'])} | {fmt_num(stats['profit_factor'])} | {fmt_num(stats['avg_trade_pts'])} |"
            )
    lines.extend([
        '',
        '## Effect Versus Baseline',
        '',
        '| Instrument | Trade change | Net change pts | Net change $ | Max DD reduction pts | Max DD reduction $ | Win-rate change | PF change |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ])
    for row in results:
        baseline = row['baseline']
        restricted = row['restricted']
        dd_reduction_pts = abs(baseline['max_dd_pts']) - abs(restricted['max_dd_pts'])
        dd_reduction_usd = abs(baseline['max_dd_usd']) - abs(restricted['max_dd_usd'])
        pf_change = restricted['profit_factor'] - baseline['profit_factor']
        lines.append(
            f"| {row['instrument']} | {restricted['trades'] - baseline['trades']:+d} | "
            f"{restricted['net_pts'] - baseline['net_pts']:+,.2f} | "
            f"{fmt_money(restricted['net_usd'] - baseline['net_usd'])} | "
            f"{dd_reduction_pts:+,.2f} | {fmt_money(dd_reduction_usd)} | "
            f"{restricted['win_rate'] - baseline['win_rate']:+.2%} | {pf_change:+.2f} |"
        )
    lines.extend(['', '## Output CSVs', ''])
    for row in results:
        rel = row['output']
        lines.append(f"- {row['instrument']}: `{rel}`")
    lines.append('')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def run_one(instrument: str, daily_path: Path, output_path: Path, multiplier: float) -> dict:
    daily = load_daily(daily_path)
    restricted = run_monthly_orb_restricted(daily)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    restricted.to_csv(output_path, index=False)

    baseline_path = daily_path.with_name(f'{instrument.lower()}_monthly_orb.csv')
    baseline, restricted_stats = compare_with_baseline(instrument, restricted, baseline_path, multiplier)
    return {
        'instrument': instrument,
        'output': str(output_path),
        'baseline': baseline,
        'restricted': restricted_stats,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--instrument', choices=['MNQ', 'NQ', 'all'], default='all')
    ap.add_argument('--daily', type=Path, default=None, help='Override daily CSV for a single instrument run.')
    ap.add_argument('--output', type=Path, default=None, help='Override output CSV for a single instrument run.')
    ap.add_argument('--multiplier', type=float, default=None, help='Dollar value per index point for a single instrument run.')
    ap.add_argument('--no-report', action='store_true')
    args = ap.parse_args()

    if args.instrument == 'all':
        runs = DEFAULT_RUNS
    else:
        default = next(r for r in DEFAULT_RUNS if r[0] == args.instrument)
        runs = [(
            args.instrument,
            args.daily or default[1],
            args.output or default[2],
            args.multiplier if args.multiplier is not None else default[3],
        )]

    results = []
    for instrument, daily_path, output_path, multiplier in runs:
        row = run_one(instrument, daily_path, output_path, multiplier)
        results.append(row)
        b = row['baseline']
        r = row['restricted']
        print(
            f"{instrument}: baseline {b['net_pts']:,.2f}pt DD {b['max_dd_pts']:,.2f}pt WR {fmt_pct(b['win_rate'])} "
            f"-> restricted {r['net_pts']:,.2f}pt DD {r['max_dd_pts']:,.2f}pt WR {fmt_pct(r['win_rate'])} "
            f"range-close exits {r['range_close_trades']}"
        )
        print(f"Wrote {row['output']}")

    if not args.no_report:
        write_report(results)
        print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
