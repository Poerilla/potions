#!/usr/bin/env python3
"""Yearly capital-scaling model for ATR Supertrend DCA variants.

This is a practical sizing overlay, not a new fill engine. It reuses the same
ATR simulation logic, runs a ladder of fixed size bumps, then chooses the
largest bump level allowed at each calendar year start by:

    starting capital + prior MTM profit >= 3 * abs(full-sample MTM DD)

Level 0 is the current study. Level 1 bumps every scale event by one contract
and also bumps max stack size by one. The yearly model reconfigures only at
calendar-year boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math

import pandas as pd

from atr_supertrend_dca_long import (
    load_1550_prices,
    max_drawdown,
    profit_factor,
    simulate,
    simulate_weekly_primary,
    trade_rows,
    unit_rows,
)


@dataclass(frozen=True)
class MarketConfig:
    market: str
    daily: Path
    source_1m: Path
    point_value: float
    out_dir: Path


@dataclass(frozen=True)
class VariantConfig:
    label: str
    slug: str
    signal_timeframe: str
    schedule_kind: str


VARIANTS = [
    VariantConfig('Daily primary, 3-initial', 'daily_3initial', 'daily', '3initial'),
    VariantConfig('Daily primary, ladder 1/1/2/2/2', 'daily_ladder112221', 'daily', 'ladder'),
    VariantConfig('Weekly primary, 3-initial', 'weekly_3initial', 'weekly', '3initial'),
    VariantConfig('Weekly primary, ladder 1/1/2/2/2', 'weekly_ladder112221', 'weekly', 'ladder'),
]


def size_schedule(kind: str, bump: int, repeat_adds: int = 120) -> list[int]:
    if kind == '3initial':
        return [3 + bump] + [1 + bump] * repeat_adds
    if kind == 'ladder':
        return [1 + bump, 1 + bump, 2 + bump, 2 + bump, 2 + bump] + [1 + bump] * repeat_adds
    raise ValueError(f'unknown schedule kind: {kind}')


def run_fixed_level(
    daily: pd.DataFrame,
    add_prices: dict[tuple, float],
    market: MarketConfig,
    variant: VariantConfig,
    bump: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    schedule = size_schedule(variant.schedule_kind, bump)
    max_contracts = 10 + bump
    if variant.signal_timeframe == 'weekly':
        trades, equity, _metadata = simulate_weekly_primary(
            daily,
            add_prices,
            market.point_value,
            14,
            3.0,
            'long',
            max_contracts,
            1,
            schedule,
            2,
            'exit-reclaim',
            'none',
        )
    else:
        trades, equity, _metadata = simulate(
            daily,
            add_prices,
            market.point_value,
            14,
            3.0,
            'long',
            max_contracts,
            1,
            schedule,
            2,
            'flat-when-bearish',
            14,
            3.0,
            'none',
            'exit-reclaim',
            'none',
        )
    return (
        pd.DataFrame(trade_rows(trades, market.point_value)),
        pd.DataFrame(unit_rows(trades, market.point_value)),
        equity.copy(),
    )


def full_stats(trades: pd.DataFrame, units: pd.DataFrame, equity: pd.DataFrame, point_value: float) -> dict:
    pnl_pts = pd.to_numeric(trades.get('net_points', pd.Series(dtype=float)), errors='coerce').fillna(0.0)
    eq_pts = pd.to_numeric(equity.get('total_equity_points', pd.Series(dtype=float)), errors='coerce').fillna(0.0)
    mtm_dd_pts = float((eq_pts - eq_pts.cummax()).min()) if not eq_pts.empty else 0.0
    return {
        'stacks': int(len(trades)),
        'units': int(len(units)),
        'net_usd': float(pnl_pts.sum() * point_value),
        'closed_dd_usd': float(max_drawdown(pnl_pts) * point_value) if not pnl_pts.empty else 0.0,
        'mtm_dd_usd': float(mtm_dd_pts * point_value),
        'capital_required_usd': float(abs(mtm_dd_pts * point_value) * 3.0),
        'win_rate': float((pnl_pts > 0).mean() * 100.0) if not pnl_pts.empty else 0.0,
        'pf': float(profit_factor(pnl_pts)) if not pnl_pts.empty else math.nan,
    }


def yearly_deltas(equity: pd.DataFrame, point_value: float) -> dict[int, dict]:
    if equity.empty:
        return {}
    work = equity.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['year'] = work['date'].dt.year
    work['equity_usd'] = pd.to_numeric(work['total_equity_points'], errors='coerce').fillna(0.0) * point_value
    work['open_units'] = pd.to_numeric(work['open_units'], errors='coerce').fillna(0).astype(int)

    rows: dict[int, dict] = {}
    prev_end_equity = 0.0
    for year, group in work.groupby('year', sort=True):
        series = pd.concat([pd.Series([prev_end_equity]), group['equity_usd']], ignore_index=True)
        dd = float((series - series.cummax()).min())
        end_equity = float(group['equity_usd'].iloc[-1])
        rows[int(year)] = {
            'year_net_usd': end_equity - prev_end_equity,
            'year_mtm_dd_usd': dd,
            'year_max_open_units': int(group['open_units'].max()),
        }
        prev_end_equity = end_equity
    return rows


def choose_level(capital: float, level_stats: dict[int, dict]) -> int | None:
    allowed = [
        level
        for level, stats in level_stats.items()
        if capital >= stats['capital_required_usd']
    ]
    if not allowed:
        return None
    return max(allowed)


def dynamic_year_model(
    level_stats: dict[int, dict],
    level_years: dict[int, dict[int, dict]],
    level_daily: dict[int, pd.DataFrame],
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, float, float]:
    initial_capital = level_stats[0]['capital_required_usd']
    capital = initial_capital
    rows = []
    equity_high = capital
    dynamic_dd = 0.0
    daily_rows = []

    for year in range(start_year, end_year + 1):
        level = choose_level(capital, level_stats)
        if level is None:
            rows.append(
                {
                    'year': year,
                    'start_capital_usd': round(capital, 2),
                    'bump_level': 'NO_TRADE',
                    'max_contracts': 0,
                    'required_capital_usd': '',
                    'capital_headroom_usd': '',
                    'year_net_usd': 0.0,
                    'year_mtm_dd_usd': 0.0,
                    'year_max_open_units': 0,
                    'end_capital_usd': round(capital, 2),
                }
            )
            continue

        required = level_stats[level]['capital_required_usd']
        year_start_capital = capital
        y = level_years[level].get(year, {'year_net_usd': 0.0, 'year_mtm_dd_usd': 0.0, 'year_max_open_units': 0})
        year_frame = level_daily[level]
        year_frame = year_frame[year_frame['year'].eq(year)].copy()
        year_high = capital
        year_dd = 0.0
        for _, drow in year_frame.iterrows():
            day_delta = float(drow['day_equity_delta_usd'])
            capital += day_delta
            equity_high = max(equity_high, capital)
            year_high = max(year_high, capital)
            dynamic_dd = min(dynamic_dd, capital - equity_high)
            year_dd = min(year_dd, capital - year_high)
            daily_rows.append(
                {
                    'date': drow['date'],
                    'year': year,
                    'bump_level': level,
                    'max_contracts': 10 + level,
                    'daily_equity_delta_usd': round(day_delta, 2),
                    'equity_usd': round(capital, 2),
                    'drawdown_usd': round(capital - equity_high, 2),
                    'open_units': int(drow.get('open_units', 0)),
                }
            )
        year_net = capital - year_start_capital
        year_dd = year_dd if not year_frame.empty else float(y['year_mtm_dd_usd'])
        rows.append(
            {
                'year': year,
                'start_capital_usd': round(year_start_capital, 2),
                'bump_level': level,
                'max_contracts': 10 + level,
                'required_capital_usd': round(required, 2),
                'capital_headroom_usd': round(year_start_capital - required, 2),
                'year_net_usd': round(year_net, 2),
                'year_mtm_dd_usd': round(year_dd, 2),
                'year_max_open_units': int(y['year_max_open_units']),
                'end_capital_usd': round(capital, 2),
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(daily_rows), initial_capital, dynamic_dd


def money(value: float | int | str) -> str:
    if value == '':
        return ''
    return f'${float(value):,.0f}'


def write_market_report(
    market: MarketConfig,
    variant_results: dict[str, dict],
    max_bump: int,
) -> None:
    out_dir = market.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f'# {market.market.upper()} ATR Supertrend Equity Scaling',
        '',
        'Rule: at each calendar-year start, choose the largest bump level where current capital is at least **3x the full-sample MTM DD** for that bump level. Level 0 is the existing 10-max study. Level 1 bumps every scale event by one contract and max stack from 10 to 11, and so on.',
        '',
        'This is a yearly capital-allocation model. It keeps the ATR entries, exits, Friday 15:50 adds, entry guard, and weekly filters unchanged.',
        '',
        f'Run note: this pass used `--max-bump {max_bump}`, so the largest allowed stack is {10 + max_bump} contracts/units. If peak bump equals {max_bump}, treat the final years as a capped practical-sizing run, not an uncapped compounding forecast.',
        '',
        '## Summary',
        '',
        '| Variant | Start Capital | End Capital | Dynamic Net | Dynamic MTM DD | End/Start | Peak Bump | Peak Max Contracts |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]

    for variant in VARIANTS:
        result = variant_results[variant.slug]
        dyn = result['dynamic']
        end_cap = float(dyn['end_capital_usd'].iloc[-1])
        start_cap = float(result['start_capital'])
        peak_bump = max(int(x) for x in dyn['bump_level'] if str(x) != 'NO_TRADE')
        lines.append(
            f'| {variant.label} | {money(start_cap)} | {money(end_cap)} | {money(end_cap - start_cap)} | {money(result["dynamic_dd"])} | {end_cap / start_cap:.2f}x | {peak_bump} | {10 + peak_bump} |'
        )

    lines.extend(['', '## Yearly Tables', ''])
    for variant in VARIANTS:
        result = variant_results[variant.slug]
        dyn = result['dynamic']
        lines.extend(
            [
                f'### {variant.label}',
                '',
                '| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |',
                '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
            ]
        )
        for row in dyn.to_dict('records'):
            lines.append(
                f'| {row["year"]} | {money(row["start_capital_usd"])} | {row["bump_level"]} | {row["max_contracts"]} | {money(row["required_capital_usd"])} | {money(row["capital_headroom_usd"])} | {money(row["year_net_usd"])} | {money(row["year_mtm_dd_usd"])} | {row["year_max_open_units"]} | {money(row["end_capital_usd"])} |'
            )
        lines.append('')

    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def run_market(market: MarketConfig, max_bump: int) -> None:
    print(f'Loading {market.market.upper()} daily data')
    daily = pd.read_csv(market.daily, parse_dates=['date']).sort_values('date').reset_index(drop=True)
    print(f'Loading {market.market.upper()} 1m add prices')
    add_prices = load_1550_prices(market.source_1m, market.market)
    start_year = int(pd.to_datetime(daily['date']).dt.year.min())
    end_year = int(pd.to_datetime(daily['date']).dt.year.max())

    variant_results: dict[str, dict] = {}
    for variant in VARIANTS:
        print(f'Running {market.market.upper()} {variant.label}')
        level_stats: dict[int, dict] = {}
        level_years: dict[int, dict[int, dict]] = {}
        level_daily: dict[int, pd.DataFrame] = {}
        level_rows = []
        for bump in range(max_bump + 1):
            trades, units, equity = run_fixed_level(daily, add_prices, market, variant, bump)
            stats = full_stats(trades, units, equity, market.point_value)
            level_stats[bump] = stats
            level_years[bump] = yearly_deltas(equity, market.point_value)
            daily_equity = equity.copy()
            daily_equity['date'] = pd.to_datetime(daily_equity['date'])
            daily_equity['year'] = daily_equity['date'].dt.year
            daily_equity['equity_usd'] = pd.to_numeric(daily_equity['total_equity_points'], errors='coerce').fillna(0.0) * market.point_value
            daily_equity['day_equity_delta_usd'] = daily_equity['equity_usd'].diff().fillna(daily_equity['equity_usd'])
            daily_equity['date'] = daily_equity['date'].dt.date.astype(str)
            level_daily[bump] = daily_equity[['date', 'year', 'day_equity_delta_usd', 'open_units']].copy()
            level_rows.append({'bump_level': bump, 'max_contracts': 10 + bump, **stats})
        dynamic, dynamic_daily, start_capital, dynamic_dd = dynamic_year_model(
            level_stats, level_years, level_daily, start_year, end_year
        )

        variant_dir = market.out_dir / variant.slug
        variant_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(level_rows).to_csv(variant_dir / 'level_summary.csv', index=False)
        dynamic.to_csv(variant_dir / 'dynamic_yearly.csv', index=False)
        dynamic_daily.to_csv(variant_dir / 'dynamic_daily.csv', index=False)
        variant_results[variant.slug] = {
            'dynamic': dynamic,
            'start_capital': start_capital,
            'dynamic_dd': dynamic_dd,
        }

    write_market_report(market, variant_results, max_bump)
    print(f'Wrote {market.out_dir / "README.md"}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--max-bump', type=int, default=40)
    ap.add_argument(
        '--markets',
        type=str,
        default='mnq,nq',
        help='Comma-separated markets to run: mnq,nq,mym,es,ym',
    )
    args = ap.parse_args()

    all_markets = {
        'mnq': MarketConfig(
            'mnq',
            Path('potions/mnq/mnq_daily.csv'),
            Path('potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'),
            2.0,
            Path('potions/mnq/case_studies/atr_supertrend_equity_scaling'),
        ),
        'nq': MarketConfig(
            'nq',
            Path('potions/nq/nq_daily.csv'),
            Path('potions/nq/raw/glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'),
            20.0,
            Path('potions/nq/case_studies/atr_supertrend_equity_scaling'),
        ),
        'mym': MarketConfig(
            'mym',
            Path('potions/mym/mym_daily.csv'),
            Path('potions/mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst'),
            0.5,
            Path('potions/mym/case_studies/atr_supertrend_equity_scaling'),
        ),
        'es': MarketConfig(
            'es',
            Path('potions/es/es_daily.csv'),
            Path('potions/es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst'),
            50.0,
            Path('potions/es/case_studies/atr_supertrend_equity_scaling'),
        ),
        'ym': MarketConfig(
            'ym',
            Path('potions/ym/ym_daily.csv'),
            Path('potions/ym/raw/glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst'),
            5.0,
            Path('potions/ym/case_studies/atr_supertrend_equity_scaling'),
        ),
    }
    requested = [piece.strip().lower() for piece in args.markets.split(',') if piece.strip()]
    for name in requested:
        if name not in all_markets:
            raise SystemExit(f'unknown market: {name}')
        run_market(all_markets[name], args.max_bump)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
