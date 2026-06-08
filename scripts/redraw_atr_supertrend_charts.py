#!/usr/bin/env python3
"""Redraw existing ATR Supertrend yearly charts from saved trade CSVs.

This is a chart-only helper. It does not rerun the strategy simulation or
rewrite the trade/equity CSVs.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Optional

import pandas as pd

from atr_supertrend_dca_long import StackTrade, Unit, draw_year_chart


DEFAULT_MARKETS = {
    'mnq': {
        'daily': Path('mnq/mnq_daily.csv'),
        'point_value': 2.0,
    },
    'nq': {
        'daily': Path('nq/nq_daily.csv'),
        'point_value': 20.0,
    },
}


def parse_float(value) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def parse_timestamp(value) -> Optional[pd.Timestamp]:
    if value is None or pd.isna(value) or str(value).strip() == '':
        return None
    return pd.Timestamp(value)


def load_trades(out_dir: Path) -> list[StackTrade]:
    trades_csv = out_dir / 'trades.csv'
    units_csv = out_dir / 'units.csv'
    trades_df = pd.read_csv(trades_csv)
    units_df = pd.read_csv(units_csv)
    units_by_trade = {int(k): v.copy() for k, v in units_df.groupby('trade_id', sort=False)}
    trades: list[StackTrade] = []
    for _, row in trades_df.iterrows():
        trade_id = int(row['trade_id'])
        trade_direction = str(row['direction']) if 'direction' in row and not pd.isna(row['direction']) else 'Long'
        trade = StackTrade(
            trade_id=trade_id,
            direction=trade_direction,
            signal_date=pd.Timestamp(row['signal_date']),
            signal_close=0.0,
            signal_stop=0.0,
            entry_date=parse_timestamp(row.get('entry_date')),
            exit_date=parse_timestamp(row.get('exit_date')),
            exit_reason=str(row.get('exit_reason', '')),
            mae_usd=float(row.get('mae_usd', 0.0) or 0.0),
            mfe_usd=float(row.get('mfe_usd', 0.0) or 0.0),
            max_units=int(row.get('max_units', row.get('units', 0)) or 0),
            prior_bearish_stop_level=parse_float(row.get('prior_bearish_stop_level')),
            initial_entry_guard_level=parse_float(row.get('initial_entry_guard_level')),
        )
        for _, unit_row in units_by_trade.get(trade_id, pd.DataFrame()).iterrows():
            unit_direction = (
                str(unit_row['direction'])
                if 'direction' in unit_row and not pd.isna(unit_row['direction'])
                else trade_direction
            )
            trade.units.append(
                Unit(
                    unit_id=int(unit_row['unit_id']),
                    direction=unit_direction,
                    entry_date=pd.Timestamp(unit_row['entry_date']),
                    entry_price=float(unit_row['entry_price']),
                    entry_reason=str(unit_row.get('entry_reason', '')),
                    entry_symbol=str(unit_row.get('entry_symbol', '')),
                    exit_date=parse_timestamp(unit_row.get('exit_date')),
                    exit_price=parse_float(unit_row.get('exit_price')),
                    exit_reason=str(unit_row.get('exit_reason', '')) if not pd.isna(unit_row.get('exit_reason', '')) else '',
                )
            )
        trades.append(trade)
    return trades


def infer_weekly_overlay(out_dir: Path, readme_text: str) -> bool:
    name = out_dir.name.lower()
    return (
        'weekly_primary' in name
        or 'weekly_flat' in name
        or 'weekly_not_bearish' in name
        or 'completed-week atr stop' in readme_text.lower()
    )


def update_readme_note(readme: Path, plot_weekly_atr: bool, extension_weeks: int) -> None:
    text = readme.read_text(encoding='utf-8')
    if plot_weekly_atr:
        note = (
            'Chart note: solid cyan/orange lines are the daily ATR stop. '
            'Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. '
            f'Dotted horizontal segments extend a broken ATR stop for {extension_weeks} week(s) after the reversal close.'
        )
    else:
        note = (
            'Chart note: solid cyan/orange lines are the daily ATR stop. '
            f'Dotted horizontal segments extend a broken ATR stop for {extension_weeks} week(s) after the reversal close.'
        )
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith('Chart note:'):
            lines[idx] = note
            readme.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            return
    for idx, line in enumerate(lines):
        if line.startswith('Important modeling note:'):
            lines.insert(idx + 1, note)
            readme.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            return


def redraw_out_dir(
    out_dir: Path,
    daily: pd.DataFrame,
    market: str,
    point_value: float,
    extension_weeks: int,
) -> int:
    readme = out_dir / 'README.md'
    readme_text = readme.read_text(encoding='utf-8') if readme.exists() else ''
    plot_weekly_atr = infer_weekly_overlay(out_dir, readme_text)
    trades = load_trades(out_dir)
    count = 0
    for year in sorted(daily['date'].dt.year.unique()):
        draw_year_chart(
            int(year),
            daily,
            trades,
            out_dir / str(int(year)) / f'{int(year)}.png',
            market.upper(),
            point_value,
            atr_length=14,
            atr_multiplier=3.0,
            plot_weekly_atr=plot_weekly_atr,
            weekly_atr_length=14,
            weekly_atr_multiplier=3.0,
            atr_extension_weeks=extension_weeks,
        )
        count += 1
    if readme.exists():
        update_readme_note(readme, plot_weekly_atr, extension_weeks)
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--markets', nargs='+', default=['mnq', 'nq'], choices=sorted(DEFAULT_MARKETS))
    ap.add_argument('--extension-weeks', type=int, default=3)
    args = ap.parse_args()

    total = 0
    for market in args.markets:
        config = DEFAULT_MARKETS[market]
        daily = pd.read_csv(args.root / config['daily'], parse_dates=['date']).sort_values('date').reset_index(drop=True)
        case_root = args.root / market / 'case_studies'
        out_dirs = sorted(
            path
            for path in case_root.glob('atr_supertrend*')
            if (path / 'trades.csv').exists() and (path / 'units.csv').exists()
        )
        for out_dir in out_dirs:
            count = redraw_out_dir(out_dir, daily, market, float(config['point_value']), args.extension_weeks)
            total += count
            print(f'{market.upper()} {out_dir.name}: redrew {count} yearly chart(s)')
    print(f'Redrew {total} ATR Supertrend yearly chart(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
