#!/usr/bin/env python3
"""Equity scaling for the top yearly ORB inside-range swing model.

One bundle is the full three-unit yearly ORB scaleout ladder. The model uses
closed unit exits for realized equity and approximates open-heat stress by
subtracting each active trade's recorded MAE for the full time it is open.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math

import pandas as pd


@dataclass(frozen=True)
class Market:
    name: str
    path: Path
    point_value: float


MARKETS = [
    Market('MNQ', Path('potions/mnq/mnq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv'), 2.0),
    Market('MYM', Path('potions/mym/mym_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv'), 0.5),
    Market('NQ', Path('potions/nq/nq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv'), 20.0),
    Market('ES', Path('potions/es/es_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv'), 50.0),
    Market('YM', Path('potions/ym/ym_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv'), 5.0),
]


def max_drawdown(values: pd.Series) -> float:
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def money(value: float) -> str:
    return f'${value:,.0f}'


def normalize_trades(market: Market) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(market.path)
    raw = raw[raw['Entry_Date'].notna()].copy()
    raw['trade_id'] = range(1, len(raw) + 1)
    raw['Entry_Date'] = pd.to_datetime(raw['Entry_Date'])
    raw['Final_Exit_Date'] = pd.to_datetime(
        raw[['Unit1_Exit_Date', 'Unit2_Exit_Date', 'Unit3_Exit_Date']].max(axis=1)
    )
    raw['mae_usd'] = pd.to_numeric(raw['MAE_Position_Pts'], errors='coerce').fillna(0.0) * market.point_value
    raw['trade_usd'] = pd.to_numeric(raw['Trade_PL'], errors='coerce').fillna(0.0) * market.point_value

    units = []
    for _, row in raw.iterrows():
        direction = str(row['Trade_Direction'])
        entry = float(row['Entry_Price'])
        for unit_idx in [1, 2, 3]:
            exit_date = row.get(f'Unit{unit_idx}_Exit_Date')
            exit_px = row.get(f'Unit{unit_idx}_Exit_Price')
            if pd.isna(exit_date) or pd.isna(exit_px):
                continue
            exit_date = pd.to_datetime(exit_date)
            exit_px = float(exit_px)
            pts = exit_px - entry if direction == 'Long' else entry - exit_px
            units.append(
                {
                    'trade_id': int(row['trade_id']),
                    'date': exit_date,
                    'usd': pts * market.point_value,
                    'unit_idx': unit_idx,
                }
            )
    return raw, pd.DataFrame(units)


def base_stats(trades: pd.DataFrame, units: pd.DataFrame) -> dict:
    daily = units.groupby('date', sort=True)['usd'].sum().reset_index()
    closed_dd = max_drawdown(daily['usd']) if not daily.empty else 0.0
    net = float(units['usd'].sum()) if not units.empty else 0.0
    years = pd.date_range(trades['Entry_Date'].min(), trades['Final_Exit_Date'].max(), freq='D')
    closed_by_day = daily.set_index('date')['usd'].reindex(years, fill_value=0.0).cumsum()
    stress_values = []
    for day, closed_eq in closed_by_day.items():
        active = trades[(trades['Entry_Date'] <= day) & (trades['Final_Exit_Date'] >= day)]
        stress_values.append(float(closed_eq) - float(active['mae_usd'].sum()))
    stress_eq = pd.Series(stress_values)
    stress_dd = float((stress_eq - closed_by_day.reset_index(drop=True).cummax()).min()) if not stress_eq.empty else 0.0
    pnl_by_trade = trades['trade_usd'].astype(float)
    return {
        'trades': int(len(trades)),
        'net_usd': net,
        'closed_dd_usd': closed_dd,
        'stress_dd_usd': stress_dd,
        'worst_mae_usd': float(trades['mae_usd'].max()) if not trades.empty else 0.0,
        'avg_mae_usd': float(trades['mae_usd'].mean()) if not trades.empty else 0.0,
        'win_rate': float((pnl_by_trade > 0).mean() * 100.0) if not pnl_by_trade.empty else 0.0,
    }


def simulate_dynamic(
    trades: pd.DataFrame,
    units: pd.DataFrame,
    required_per_bundle: float,
    max_bundles: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    start = required_per_bundle
    capital = start
    closed_high = capital
    stress_dd = 0.0
    closed_dd = 0.0
    bundle_by_trade = {}
    yearly_rows = []
    daily_rows = []
    first_year = int(trades['Entry_Date'].dt.year.min())
    last_date = max(pd.to_datetime(units['date']).max(), trades['Final_Exit_Date'].max())
    last_year = int(last_date.year)

    for year in range(first_year, last_year + 1):
        year_start = capital
        bundles = min(max_bundles, int(capital // required_per_bundle)) if required_per_bundle > 0 else max_bundles
        bundles = max(bundles, 0)
        for trade_id in trades.loc[trades['Entry_Date'].dt.year.eq(year), 'trade_id']:
            bundle_by_trade[int(trade_id)] = bundles

        year_days = pd.date_range(f'{year}-01-01', f'{year}-12-31', freq='D')
        year_days = year_days[year_days <= last_date]
        year_closed_high = capital
        year_stress_dd = 0.0
        year_closed_dd = 0.0
        for day in year_days:
            exits = units[pd.to_datetime(units['date']).dt.date.eq(day.date())].copy()
            day_pnl = 0.0
            for _, unit in exits.iterrows():
                day_pnl += float(unit['usd']) * bundle_by_trade.get(int(unit['trade_id']), 0)
            capital += day_pnl
            closed_high = max(closed_high, capital)
            year_closed_high = max(year_closed_high, capital)
            closed_dd = min(closed_dd, capital - closed_high)
            year_closed_dd = min(year_closed_dd, capital - year_closed_high)
            active = trades[(trades['Entry_Date'] <= day) & (trades['Final_Exit_Date'] >= day)]
            heat = sum(float(row['mae_usd']) * bundle_by_trade.get(int(row['trade_id']), 0) for _, row in active.iterrows())
            stress_equity = capital - heat
            stress_dd = min(stress_dd, stress_equity - closed_high)
            year_stress_dd = min(year_stress_dd, stress_equity - year_closed_high)
            daily_rows.append(
                {
                    'date': day.date().isoformat(),
                    'year': year,
                    'bundles': bundles,
                    'daily_pnl_usd': round(day_pnl, 2),
                    'closed_equity_usd': round(capital, 2),
                    'active_heat_usd': round(heat, 2),
                    'stress_equity_usd': round(stress_equity, 2),
                    'closed_drawdown_usd': round(capital - closed_high, 2),
                    'stress_drawdown_usd': round(stress_equity - closed_high, 2),
                }
            )
        yearly_rows.append(
            {
                'year': year,
                'start_capital_usd': round(year_start, 2),
                'bundles': bundles,
                'max_contracts': bundles * 3,
                'required_capital_usd': round(required_per_bundle * bundles, 2),
                'year_net_usd': round(capital - year_start, 2),
                'year_closed_dd_usd': round(year_closed_dd, 2),
                'year_stress_dd_usd': round(year_stress_dd, 2),
                'end_capital_usd': round(capital, 2),
            }
        )

    return (
        pd.DataFrame(yearly_rows),
        pd.DataFrame(daily_rows),
        {
            'start_capital_usd': start,
            'end_capital_usd': capital,
            'dynamic_net_usd': capital - start,
            'dynamic_closed_dd_usd': closed_dd,
            'dynamic_stress_dd_usd': stress_dd,
            'peak_bundles': max((row['bundles'] for row in yearly_rows), default=0),
        },
    )


def write_market_report(out: Path, market: Market, base: dict, yearly: pd.DataFrame, dynamic: dict, max_bundles: int) -> None:
    lines = [
        f'# {market.name} Yearly ORB Equity Scaling',
        '',
        'Variant: yearly ORB scaleout3 / inside-range swing stop / range-close exit.',
        'One bundle is the full 3-contract scaleout ladder. Capital requirement uses 3x the base open-heat stress DD, not just closed DD.',
        f'Run cap: {max_bundles} bundles.',
        '',
        '## Summary',
        '',
        '| Metric | Value |',
        '|---|---:|',
        f'| Base trades | {base["trades"]} |',
        f'| Base net | {money(base["net_usd"])} |',
        f'| Base closed DD | {money(base["closed_dd_usd"])} |',
        f'| Base open-heat stress DD | {money(base["stress_dd_usd"])} |',
        f'| Base worst MAE | {money(base["worst_mae_usd"])} |',
        f'| Scaling start capital | {money(dynamic["start_capital_usd"])} |',
        f'| Scaling end capital | {money(dynamic["end_capital_usd"])} |',
        f'| Scaling net | {money(dynamic["dynamic_net_usd"])} |',
        f'| Scaling closed DD | {money(dynamic["dynamic_closed_dd_usd"])} |',
        f'| Scaling stress DD | {money(dynamic["dynamic_stress_dd_usd"])} |',
        f'| Peak bundles | {dynamic["peak_bundles"]} |',
        f'| Peak contracts | {dynamic["peak_bundles"] * 3} |',
        '',
        '## Yearly Scaling',
        '',
        '| Year | Start Capital | Bundles | Max Contracts | Required Capital | Year Net | Closed DD | Stress DD | End Capital |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in yearly.to_dict('records'):
        lines.append(
            f'| {row["year"]} | {money(row["start_capital_usd"])} | {row["bundles"]} | {row["max_contracts"]} | {money(row["required_capital_usd"])} | {money(row["year_net_usd"])} | {money(row["year_closed_dd_usd"])} | {money(row["year_stress_dd_usd"])} | {money(row["end_capital_usd"])} |'
        )
    lines.append('')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def pair_mnq_mym(root: Path) -> None:
    mnq = pd.read_csv(root / 'mnq' / 'dynamic_daily.csv', parse_dates=['date'])
    mym = pd.read_csv(root / 'mym' / 'dynamic_daily.csv', parse_dates=['date'])
    combo = mnq[['date', 'daily_pnl_usd', 'active_heat_usd']].rename(
        columns={'daily_pnl_usd': 'mnq_pnl', 'active_heat_usd': 'mnq_heat'}
    ).merge(
        mym[['date', 'daily_pnl_usd', 'active_heat_usd']].rename(
            columns={'daily_pnl_usd': 'mym_pnl', 'active_heat_usd': 'mym_heat'}
        ),
        on='date',
        how='outer',
    ).fillna(0.0).sort_values('date')
    mnq_yearly = pd.read_csv(root / 'mnq' / 'dynamic_yearly.csv')
    mym_yearly = pd.read_csv(root / 'mym' / 'dynamic_yearly.csv')
    start = float(mnq_yearly['start_capital_usd'].iloc[0] + mym_yearly['start_capital_usd'].iloc[0])
    capital = start
    high = start
    closed_dd = 0.0
    stress_dd = 0.0
    rows = []
    for _, row in combo.iterrows():
        pnl = float(row['mnq_pnl']) + float(row['mym_pnl'])
        heat = float(row['mnq_heat']) + float(row['mym_heat'])
        capital += pnl
        high = max(high, capital)
        closed_dd = min(closed_dd, capital - high)
        stress_dd = min(stress_dd, capital - heat - high)
        rows.append(
            {
                'date': pd.Timestamp(row['date']).date().isoformat(),
                'daily_pnl_usd': round(pnl, 2),
                'closed_equity_usd': round(capital, 2),
                'active_heat_usd': round(heat, 2),
                'stress_equity_usd': round(capital - heat, 2),
                'closed_drawdown_usd': round(capital - high, 2),
                'stress_drawdown_usd': round(capital - heat - high, 2),
            }
        )
    out = root / 'mnq_mym_pair'
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / 'dynamic_daily.csv', index=False)
    corr = float(combo[['mnq_pnl', 'mym_pnl']].corr().iloc[0, 1])
    end = capital
    summary = pd.DataFrame(
        [
            {
                'start_capital_usd': start,
                'end_capital_usd': end,
                'net_usd': end - start,
                'closed_dd_usd': closed_dd,
                'stress_dd_usd': stress_dd,
                'daily_pnl_corr': corr,
            }
        ]
    )
    summary.to_csv(out / 'summary.csv', index=False)
    lines = [
        '# Yearly ORB MNQ + MYM Scaling Pair',
        '',
        'Both markets are independently scaled by the yearly ORB 3x open-heat stress-DD rule, then combined daily.',
        '',
        '| Start | End | Net | Closed DD | Stress DD | Daily PnL Corr |',
        '|---:|---:|---:|---:|---:|---:|',
        f'| {money(start)} | {money(end)} | {money(end - start)} | {money(closed_dd)} | {money(stress_dd)} | {corr:.2f} |',
        '',
    ]
    (out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=Path('potions/mnq/case_studies/yearly_orb_equity_scaling'))
    ap.add_argument('--max-bundles', type=int, default=250)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for market in MARKETS:
        trades, units = normalize_trades(market)
        base = base_stats(trades, units)
        required = abs(base['stress_dd_usd']) * 3.0
        yearly, daily, dynamic = simulate_dynamic(trades, units, required, args.max_bundles)
        out = args.out / market.name.lower()
        out.mkdir(parents=True, exist_ok=True)
        trades.to_csv(out / 'normalized_trades.csv', index=False)
        units.to_csv(out / 'normalized_unit_exits.csv', index=False)
        yearly.to_csv(out / 'dynamic_yearly.csv', index=False)
        daily.to_csv(out / 'dynamic_daily.csv', index=False)
        write_market_report(out, market, base, yearly, dynamic, args.max_bundles)
        summary_rows.append({'market': market.name, **base, **dynamic})
    pd.DataFrame(summary_rows).to_csv(args.out / 'summary.csv', index=False)
    pair_mnq_mym(args.out)
    print(f'Wrote {args.out / "summary.csv"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
