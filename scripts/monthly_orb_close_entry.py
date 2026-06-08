#!/usr/bin/env python3
"""Causal monthly ORB with post-breakout limit entries.

The first 3 daily bars of each month define the monthly opening range. After a
daily close outside the range, the strategy places a limit order for later
daily bars only. Entry variants include breakout-close limit, strict
boundary-retest limit, and inside opposite-candle open limit.

  - unrestricted: target remains breakout-close ± monthly range
  - restricted: target uses the original boundary target again
    (monthly OR high + range for longs, monthly OR low - range for shorts),
    and exits at the daily close if it closes back inside the monthly opening
    range
  - stop-study variants:
    - breakout: breakout candle low/high
    - breakout_2x: entry minus/plus 2x breakout-candle adverse distance
    - boundary_candle: breakout boundary minus/plus breakout candle size
    - near_boundary: breakout boundary itself
    - source_extreme: low/high of the selected inside opposite candle run

Long breakout candles must be green and short breakout candles must be red.

This intentionally avoids the original same-breakout-bar fill assumption.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import argparse
import math

import pandas as pd


ROOT = Path('/home/tester/hsm/potions')
REPORT = ROOT / 'mnq' / 'case_studies' / 'monthly_orb' / 'MONTHLY_ORB_CLOSE_ENTRY.md'
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


def simulate_month(
    range_high: float,
    range_low: float,
    range_val: float,
    trade_bars: pd.DataFrame,
    *,
    restricted: bool,
    stop_mode: str = 'range',
    entry_mode: str = 'close',
    pre_bars: pd.DataFrame | None = None,
) -> list[dict]:
    if stop_mode not in {'range', 'breakout', 'breakout_2x', 'boundary_candle', 'near_boundary', 'source_extreme'}:
        raise ValueError(f'unsupported stop_mode: {stop_mode}')
    if entry_mode not in {'close', 'boundary', 'inside_opposite_open'}:
        raise ValueError(f'unsupported entry_mode: {entry_mode}')
    if stop_mode == 'source_extreme' and entry_mode != 'inside_opposite_open':
        raise ValueError('source_extreme stop_mode requires inside_opposite_open entry_mode')

    phase = WAIT_BREAKOUT
    direction = None
    limit_price = target = stop = None
    breakout_date = None
    entry_date = None
    entry_source = None
    entry_source_start = None
    entry_source_end = None
    entry_source_date = None
    entry_source_count = 0
    entry_source_open = None
    entry_source_high = None
    entry_source_low = None
    entry_source_close = None
    entry_source_run_high = None
    entry_source_run_low = None
    max_dd = 0.0
    trades: list[dict] = []
    history = [row for _, row in pre_bars.iterrows()] if pre_bars is not None else []

    def is_inside_opposite(row, new_direction: str) -> bool:
        o = float(row['open'])
        h = float(row['high'])
        l = float(row['low'])
        c = float(row['close'])
        inside_range = h <= range_high and l >= range_low
        if new_direction == 'Long':
            return inside_range and c < o
        return inside_range and c > o

    def inside_opposite_entry(new_direction: str) -> dict | None:
        prior = history[:-1]
        i = len(prior) - 1
        while i >= 0 and not is_inside_opposite(prior[i], new_direction):
            i -= 1
        if i < 0:
            return None

        run = []
        while i >= 0 and is_inside_opposite(prior[i], new_direction):
            run.append(prior[i])
            i -= 1

        if new_direction == 'Long':
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

    def source_fields() -> dict:
        return {
            'entry_source': entry_source,
            'entry_source_start': entry_source_start,
            'entry_source_end': entry_source_end,
            'entry_source_date': entry_source_date,
            'entry_source_count': entry_source_count,
            'entry_source_open': entry_source_open,
            'entry_source_high': entry_source_high,
            'entry_source_low': entry_source_low,
            'entry_source_close': entry_source_close,
            'entry_source_run_high': entry_source_run_high,
            'entry_source_run_low': entry_source_run_low,
        }

    def arm_order(new_direction: str, close_price: float, bar_date, breakout_low: float, breakout_high: float) -> bool:
        nonlocal phase, direction, limit_price, target, stop, breakout_date
        nonlocal entry_source, entry_source_start, entry_source_end, entry_source_date, entry_source_count
        nonlocal entry_source_open, entry_source_high, entry_source_low, entry_source_close
        nonlocal entry_source_run_high, entry_source_run_low
        candle_size = breakout_high - breakout_low
        source = {
            'kind': entry_mode,
            'date': None,
            'start': None,
            'end': None,
            'count': 0,
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'run_high': None,
            'run_low': None,
        }
        if new_direction == 'Long':
            if entry_mode == 'boundary':
                new_entry = range_high
            elif entry_mode == 'inside_opposite_open':
                found_entry = inside_opposite_entry(new_direction)
                if found_entry is None:
                    return False
                new_entry = found_entry['price']
                source = {'kind': 'inside_opposite_open', **found_entry}
            else:
                new_entry = close_price
            new_target = range_high + range_val if (restricted or entry_mode != 'close') else close_price + range_val
            if stop_mode == 'range':
                new_stop = range_low
            elif stop_mode == 'breakout':
                new_stop = breakout_low
            elif stop_mode == 'breakout_2x':
                new_stop = new_entry - 2.0 * (new_entry - breakout_low)
            elif stop_mode == 'boundary_candle':
                new_stop = range_high - candle_size
            elif stop_mode == 'source_extreme':
                new_stop = source['run_low']
            else:
                new_stop = range_high
            if stop_mode == 'source_extreme' and (new_stop is None or new_entry <= float(new_stop)):
                return False
            if entry_mode == 'close' and restricted and close_price >= new_target:
                return False
        else:
            if entry_mode == 'boundary':
                new_entry = range_low
            elif entry_mode == 'inside_opposite_open':
                found_entry = inside_opposite_entry(new_direction)
                if found_entry is None:
                    return False
                new_entry = found_entry['price']
                source = {'kind': 'inside_opposite_open', **found_entry}
            else:
                new_entry = close_price
            new_target = range_low - range_val if (restricted or entry_mode != 'close') else close_price - range_val
            if stop_mode == 'range':
                new_stop = range_high
            elif stop_mode == 'breakout':
                new_stop = breakout_high
            elif stop_mode == 'breakout_2x':
                new_stop = new_entry + 2.0 * (breakout_high - new_entry)
            elif stop_mode == 'boundary_candle':
                new_stop = range_low + candle_size
            elif stop_mode == 'source_extreme':
                new_stop = source['run_high']
            else:
                new_stop = range_low
            if stop_mode == 'source_extreme' and (new_stop is None or new_entry >= float(new_stop)):
                return False
            if entry_mode == 'close' and restricted and close_price <= new_target:
                return False
        direction = new_direction
        limit_price = new_entry
        breakout_date = bar_date
        target = new_target
        stop = new_stop
        entry_source = source['kind']
        entry_source_start = source['start']
        entry_source_end = source['end']
        entry_source_date = source['date']
        entry_source_count = int(source['count'] or 0)
        entry_source_open = source['open']
        entry_source_high = source['high']
        entry_source_low = source['low']
        entry_source_close = source['close']
        entry_source_run_high = source['run_high']
        entry_source_run_low = source['run_low']
        phase = WAIT_FILL
        return True

    def valid_long_breakout() -> bool:
        return c > range_high and c > float(bar['open'])

    def valid_short_breakout() -> bool:
        return c < range_low and c < float(bar['open'])

    def target_result() -> str:
        assert direction is not None and limit_price is not None and target is not None
        if direction == 'Long':
            return 'Win' if target > limit_price else 'Target-Loss'
        return 'Win' if target < limit_price else 'Target-Loss'

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
            filled = False
            if direction == 'Long' and l <= limit_price:
                entry_date = d
                filled = True
            elif direction == 'Short' and h >= limit_price:
                entry_date = d
                filled = True

            if filled:
                phase = IN_TRADE
                max_dd = 0.0
            elif entry_mode != 'inside_opposite_open':
                if valid_long_breakout():
                    arm_order('Long', c, d, l, h)
                elif valid_short_breakout():
                    arm_order('Short', c, d, l, h)

        if phase == IN_TRADE:
            assert direction is not None and limit_price is not None and target is not None and stop is not None
            if direction == 'Long':
                if l < stop:
                    trades.append({
                        'direction': 'Long',
                        'entry': limit_price,
                        'exit_price': stop,
                        'target': target,
                        'stop': stop,
                        'drawdown_pct': 100.0,
                        'result': 'Loss',
                        'breakout_date': breakout_date,
                        'entry_date': entry_date,
                        'exit_date': d,
                        **source_fields(),
                        'exit_reason': 'Stop',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif h >= target:
                    max_dd = max(max_dd, max(0.0, (limit_price - l) / range_val))
                    trades.append({
                        'direction': 'Long',
                        'entry': limit_price,
                        'exit_price': target,
                        'target': target,
                        'stop': stop,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': target_result(),
                        'breakout_date': breakout_date,
                        'entry_date': entry_date,
                        'exit_date': d,
                        **source_fields(),
                        'exit_reason': 'Target',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif restricted and range_low <= c <= range_high:
                    max_dd = max(max_dd, max(0.0, (limit_price - l) / range_val))
                    trades.append({
                        'direction': 'Long',
                        'entry': limit_price,
                        'exit_price': c,
                        'target': target,
                        'stop': stop,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': 'Range-Close',
                        'breakout_date': breakout_date,
                        'entry_date': entry_date,
                        'exit_date': d,
                        **source_fields(),
                        'exit_reason': 'Close_Back_Inside_Range',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (limit_price - l) / range_val))
                    continue
            else:
                if h > stop:
                    trades.append({
                        'direction': 'Short',
                        'entry': limit_price,
                        'exit_price': stop,
                        'target': target,
                        'stop': stop,
                        'drawdown_pct': 100.0,
                        'result': 'Loss',
                        'breakout_date': breakout_date,
                        'entry_date': entry_date,
                        'exit_date': d,
                        **source_fields(),
                        'exit_reason': 'Stop',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif l <= target:
                    max_dd = max(max_dd, max(0.0, (h - limit_price) / range_val))
                    trades.append({
                        'direction': 'Short',
                        'entry': limit_price,
                        'exit_price': target,
                        'target': target,
                        'stop': stop,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': target_result(),
                        'breakout_date': breakout_date,
                        'entry_date': entry_date,
                        'exit_date': d,
                        **source_fields(),
                        'exit_reason': 'Target',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                elif restricted and range_low <= c <= range_high:
                    max_dd = max(max_dd, max(0.0, (h - limit_price) / range_val))
                    trades.append({
                        'direction': 'Short',
                        'entry': limit_price,
                        'exit_price': c,
                        'target': target,
                        'stop': stop,
                        'drawdown_pct': round(max_dd * 100, 2),
                        'result': 'Range-Close',
                        'breakout_date': breakout_date,
                        'entry_date': entry_date,
                        'exit_date': d,
                        **source_fields(),
                        'exit_reason': 'Close_Back_Inside_Range',
                    })
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (h - limit_price) / range_val))
                    continue

        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_PERIOD:
            if valid_long_breakout():
                arm_order('Long', c, d, l, h)
            elif valid_short_breakout():
                arm_order('Short', c, d, l, h)

    if phase == IN_TRADE and len(trade_bars) > 0:
        assert direction is not None and limit_price is not None and target is not None and stop is not None
        last = trade_bars.iloc[-1]
        trades.append({
            'direction': direction,
            'entry': limit_price,
            'exit_price': float(last['close']),
            'target': target,
            'stop': stop,
            'drawdown_pct': round(max_dd * 100, 2),
            'result': 'Period-Close',
            'breakout_date': breakout_date,
            'entry_date': entry_date,
            'exit_date': last['date'],
            **source_fields(),
            'exit_reason': 'Period_Close',
        })

    return trades


def run_monthly_orb_close_entry(
    df: pd.DataFrame,
    *,
    restricted: bool,
    stop_mode: str = 'range',
    entry_mode: str = 'close',
) -> pd.DataFrame:
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
                'Breakout_Date': None,
                'Entry_Date': None,
                'Exit_Date': None,
                'TP_Price': None,
                'Stop_Price': None,
                'Stop_Mode': stop_mode,
                'Entry_Mode': entry_mode,
                'Entry_Source': None,
                'Entry_Source_Start': None,
                'Entry_Source_End': None,
                'Entry_Source_Date': None,
                'Entry_Source_Count': 0,
                'Entry_Source_Open': None,
                'Entry_Source_High': None,
                'Entry_Source_Low': None,
                'Entry_Source_Close': None,
                'Entry_Source_Run_High': None,
                'Entry_Source_Run_Low': None,
                'Risk_Pts': None,
                'R_Multiple': None,
                'Exit_Reason': result,
            })

        if range_val <= 0:
            append_noop('No-Op')
            continue

        trades = simulate_month(
            range_high,
            range_low,
            range_val,
            trade_bars,
            restricted=restricted,
            stop_mode=stop_mode,
            entry_mode=entry_mode,
            pre_bars=range_bars,
        )
        if not trades:
            append_noop('No-Op')
            continue

        for trade in trades:
            direction = trade['direction']
            entry = float(trade['entry'])
            exit_price = float(trade['exit_price'])
            pl = (exit_price - entry) if direction == 'Long' else (entry - exit_price)
            risk = (entry - float(trade['stop'])) if direction == 'Long' else (float(trade['stop']) - entry)
            r_multiple = pl / risk if risk > 0 else math.nan
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
                'Breakout_Date': trade['breakout_date'],
                'Entry_Date': trade['entry_date'],
                'Exit_Date': trade['exit_date'],
                'TP_Price': trade['target'],
                'Stop_Price': trade['stop'],
                'Stop_Mode': stop_mode,
                'Entry_Mode': entry_mode,
                'Entry_Source': trade.get('entry_source'),
                'Entry_Source_Start': trade.get('entry_source_start'),
                'Entry_Source_End': trade.get('entry_source_end'),
                'Entry_Source_Date': trade.get('entry_source_date'),
                'Entry_Source_Count': trade.get('entry_source_count'),
                'Entry_Source_Open': trade.get('entry_source_open'),
                'Entry_Source_High': trade.get('entry_source_high'),
                'Entry_Source_Low': trade.get('entry_source_low'),
                'Entry_Source_Close': trade.get('entry_source_close'),
                'Entry_Source_Run_High': trade.get('entry_source_run_high'),
                'Entry_Source_Run_Low': trade.get('entry_source_run_low'),
                'Risk_Pts': round(risk, 6) if risk > 0 else None,
                'R_Multiple': round(r_multiple, 6) if not math.isnan(r_multiple) else None,
                'Exit_Reason': trade['exit_reason'],
            })

    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum().round(6)
    return out


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
        'target_behind_trades': 0,
        'no_op_periods': 0,
        'wins_ge_2r': 0,
        'wins_ge_3r': 0,
        }
    trades = df[df['Trade_Direction'] != 'No-Op'].copy()
    pnl = trades['Trade_PL'].astype(float)
    if {'TP_Price', 'Entry_Price'}.issubset(trades.columns):
        target_behind_trades = int(
            (
                ((trades['Trade_Direction'] == 'Long') & (trades['TP_Price'] <= trades['Entry_Price']))
                | ((trades['Trade_Direction'] == 'Short') & (trades['TP_Price'] >= trades['Entry_Price']))
            ).sum()
        )
    else:
        target_behind_trades = 0

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
        'target_behind_trades': target_behind_trades,
        'no_op_periods': int((df['Trade_Direction'] == 'No-Op').sum()),
        'wins_ge_2r': int(((pnl > 0) & (trades.get('R_Multiple', pd.Series(index=trades.index, dtype=float)).astype(float) >= 2.0)).sum()) if 'R_Multiple' in trades else 0,
        'wins_ge_3r': int(((pnl > 0) & (trades.get('R_Multiple', pd.Series(index=trades.index, dtype=float)).astype(float) >= 3.0)).sum()) if 'R_Multiple' in trades else 0,
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


def load_optional(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def write_report(results: list[dict]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Monthly ORB Breakout-Close Entry',
        '',
        'Causal entry variant: after a daily close outside the monthly OR, place a limit order for later bars only. Long breakout candles must close green; short breakout candles must close red. Close-entry variants use the breakout close as entry. Boundary-retest variants use the original OR boundary as entry after the breakout close is known. Inside-candle variants use the most recent opposite-color fully-inside candle run before breakout. Stop-study variants compare the opposite range boundary, breakout candle low/high, 2x breakout-candle adverse distance, boundary plus/minus breakout candle size, the near breakout boundary itself, and the low/high of the selected inside-candle run.',
        '',
        '## Candidate Flag',
        '',
        '**Inside-candle-open restricted is now the primary scaling candidate among causal monthly ORB standalone variants by drawdown and profit factor.** Boundary-retest restricted remains the higher-net retest benchmark. Both are mechanically coherent; the original boundary-entry restricted row remains non-causal research context only.',
        '',
        '| Instrument | Variant | Periods | Trades | Range-close exits | Target behind entry | Net pts | Net $ | Max DD pts | Max DD $ | Win rate | PF | Avg/trade pts | Wins >=2R | Wins >=3R |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in results:
        for name, stats in row['stats'].items():
            lines.append(
                f"| {row['instrument']} | {name} | {stats['periods']} | {stats['trades']} | "
                f"{stats['range_close_trades']} | {stats['target_behind_trades']} | "
                f"{stats['net_pts']:,.2f} | {fmt_money(stats['net_usd'])} | "
                f"{stats['max_dd_pts']:,.2f} | {fmt_money(stats['max_dd_usd'])} | "
                f"{fmt_pct(stats['win_rate'])} | {fmt_num(stats['profit_factor'])} | {fmt_num(stats['avg_trade_pts'])} | "
                f"{stats['wins_ge_2r']} | {stats['wins_ge_3r']} |"
            )
    lines.extend([
        '',
        '## Output CSVs',
        '',
    ])
    for row in results:
        for name, path in row['outputs'].items():
            lines.append(f"- {row['instrument']} {name}: `{path}`")
    lines.append('')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def run_one(instrument: str, daily_path: Path, out_dir: Path, multiplier: float) -> dict:
    daily = load_daily(daily_path)
    prefix = instrument.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    variant_specs = [
        ('boundary-retest unrestricted', False, 'range', 'boundary', f'{prefix}_monthly_orb_boundary_retest.csv'),
        ('boundary-retest restricted', True, 'range', 'boundary', f'{prefix}_monthly_orb_boundary_retest_restricted.csv'),
        ('inside-candle-open unrestricted', False, 'range', 'inside_opposite_open', f'{prefix}_monthly_orb_inside_candle_open.csv'),
        ('inside-candle-open restricted', True, 'range', 'inside_opposite_open', f'{prefix}_monthly_orb_inside_candle_open_restricted.csv'),
        ('inside-candle-open unrestricted source-stop', False, 'source_extreme', 'inside_opposite_open', f'{prefix}_monthly_orb_inside_candle_open_source_stop.csv'),
        ('inside-candle-open restricted source-stop', True, 'source_extreme', 'inside_opposite_open', f'{prefix}_monthly_orb_inside_candle_open_restricted_source_stop.csv'),
        ('close-entry unrestricted', False, 'range', 'close', f'{prefix}_monthly_orb_close_entry.csv'),
        ('close-entry restricted', True, 'range', 'close', f'{prefix}_monthly_orb_close_entry_restricted.csv'),
        ('close-entry unrestricted breakout-stop', False, 'breakout', 'close', f'{prefix}_monthly_orb_close_entry_breakout_stop.csv'),
        ('close-entry restricted breakout-stop', True, 'breakout', 'close', f'{prefix}_monthly_orb_close_entry_restricted_breakout_stop.csv'),
        ('close-entry unrestricted 2x-breakout-stop', False, 'breakout_2x', 'close', f'{prefix}_monthly_orb_close_entry_2x_breakout_stop.csv'),
        ('close-entry restricted 2x-breakout-stop', True, 'breakout_2x', 'close', f'{prefix}_monthly_orb_close_entry_restricted_2x_breakout_stop.csv'),
        ('close-entry unrestricted boundary-candle-stop', False, 'boundary_candle', 'close', f'{prefix}_monthly_orb_close_entry_boundary_candle_stop.csv'),
        ('close-entry restricted boundary-candle-stop', True, 'boundary_candle', 'close', f'{prefix}_monthly_orb_close_entry_restricted_boundary_candle_stop.csv'),
        ('close-entry unrestricted near-boundary-stop', False, 'near_boundary', 'close', f'{prefix}_monthly_orb_close_entry_near_boundary_stop.csv'),
        ('close-entry restricted near-boundary-stop', True, 'near_boundary', 'close', f'{prefix}_monthly_orb_close_entry_restricted_near_boundary_stop.csv'),
    ]

    stats = {}
    outputs = {}
    for label, restricted, stop_mode, entry_mode, filename in variant_specs:
        out = run_monthly_orb_close_entry(daily, restricted=restricted, stop_mode=stop_mode, entry_mode=entry_mode)
        path = out_dir / filename
        out.to_csv(path, index=False)
        stats[label] = summarize(out, multiplier)
        outputs[label] = str(path)

    baseline = load_optional(out_dir / f'{prefix}_monthly_orb.csv')
    old_restricted = load_optional(out_dir / f'{prefix}_monthly_orb_restricted.csv')
    if baseline is not None:
        stats = {'original boundary-entry': summarize(baseline, multiplier), **stats}
    if old_restricted is not None:
        stats = {**stats, 'original boundary-entry restricted': summarize(old_restricted, multiplier)}

    return {
        'instrument': instrument,
        'stats': stats,
        'outputs': outputs,
    }


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

    results = []
    for instrument, daily_path, out_dir, multiplier in runs:
        row = run_one(instrument, daily_path, out_dir, multiplier)
        results.append(row)
        print(instrument)
        for name, stats in row['stats'].items():
            print(
                f"  {name}: {stats['net_pts']:,.2f}pt {fmt_money(stats['net_usd'])}, "
                f"DD {stats['max_dd_pts']:,.2f}pt {fmt_money(stats['max_dd_usd'])}, "
                f"WR {fmt_pct(stats['win_rate'])}, PF {fmt_num(stats['profit_factor'])}, "
                f"trades {stats['trades']}"
            )
        for path in row['outputs'].values():
            print(f'  wrote {path}')

    if not args.no_report:
        write_report(results)
        print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
