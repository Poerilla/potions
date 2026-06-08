#!/usr/bin/env python3
"""Yearly bundle-scaling overlay for v2b-family intraday systems.

The source files are already flat-by-session/leg research outputs. A sizing
level here means running N identical copies of the current trade plan:

- v2b scaleout: copy the full TP1 + runner bundle.
- child systems: copy the full parent/child bundle.

This preserves the stored execution logic without inventing new partial-exit
ratios. Capital is checked at each calendar-year start against
``3 * daily-closed max DD`` for the chosen bundle count.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math

import pandas as pd


@dataclass(frozen=True)
class Variant:
    label: str
    slug: str
    path: Path
    date_col: str
    net_col: str
    filter_col: str = ''
    filter_value: str = ''
    base_max_contracts: int = 1
    instrument: str = 'MNQ'


VARIANTS = [
    Variant(
        'MNQ adaptive 50/150 v2b-only scaleout',
        'mnq_adaptive_50_150_v2b_only_scaleout',
        Path('potions/mnq/v2d/adaptive_50_150_scaleout_legs.csv'),
        'date_iso',
        'scaleout_net_2ct',
        'regime',
        'v2b',
        2,
        'MNQ',
    ),
    Variant(
        'MNQ full adaptive 50/150 scaleout',
        'mnq_full_adaptive_50_150_scaleout',
        Path('potions/mnq/v2d/adaptive_50_150_scaleout_legs.csv'),
        'date_iso',
        'scaleout_net_2ct',
        '',
        '',
        2,
        'MNQ',
    ),
    Variant(
        'MNQ monthly-aligned v2d + unchanged v2b scaleout',
        'mnq_monthly_aligned_v2d_v2b_unchanged_scaleout',
        Path('potions/mnq/case_studies/monthly_orb/adaptive_scaleout_monthly_bias_resim_legs.csv'),
        'date_iso',
        'scaleout_net_2ct',
        'policy',
        'v2d_aligned_only_v2b_unchanged',
        2,
        'MNQ',
    ),
    Variant(
        'MNQ adaptive 50/150 child 3max',
        'mnq_adaptive_50_150_child_3max',
        Path('potions/mnq/v2d/mnq_orb_results_adaptive_50_150_child_3max.csv'),
        'Date',
        'Net_$',
        '',
        '',
        3,
        'MNQ',
    ),
    Variant(
        'MNQ v2b child 3max',
        'mnq_v2b_child_3max',
        Path('potions/mnq/case_studies/v2b_child/mnq_orb_open_limit_v2b_child_3max.csv'),
        'Date',
        'Net_$',
        '',
        '',
        3,
        'MNQ',
    ),
    Variant(
        'MNQ v2b child 1-add',
        'mnq_v2b_child_1add',
        Path('potions/mnq/case_studies/v2b_child/mnq_orb_open_limit_v2b_child.csv'),
        'Date',
        'Net_$',
        '',
        '',
        2,
        'MNQ',
    ),
    Variant(
        'MNQ v2b tier-1 only',
        'mnq_v2b_tier1_only',
        Path('potions/mnq/case_studies/v2b_child/mnq_orb_step2_match.csv'),
        'Date',
        'Net_$',
        '',
        '',
        1,
        'MNQ',
    ),
    Variant(
        'NQ adaptive 50/150 v2b-only scaleout',
        'nq_adaptive_50_150_v2b_only_scaleout',
        Path('potions/nq/v2d/nq_adaptive_50_150_v2b_scaleout.csv'),
        'date_iso',
        'net_usd',
        'segment',
        'adaptive_50_150_v2b_only_scaleout',
        2,
        'NQ',
    ),
    Variant(
        'NQ all-v2b-days scaleout reference',
        'nq_all_v2b_days_scaleout',
        Path('potions/nq/v2d/nq_adaptive_50_150_v2b_scaleout.csv'),
        'date_iso',
        'net_usd',
        'segment',
        'all_v2b_days_scaleout',
        2,
        'NQ',
    ),
]


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def load_variant(variant: Variant) -> pd.DataFrame:
    df = pd.read_csv(variant.path)
    if variant.filter_col:
        df = df[df[variant.filter_col].astype(str).eq(variant.filter_value)].copy()
    out = pd.DataFrame(
        {
            'date': pd.to_datetime(df[variant.date_col]).dt.date,
            'net_usd': pd.to_numeric(df[variant.net_col], errors='coerce').fillna(0.0),
        }
    )
    out = out.sort_values('date').reset_index(drop=True)
    return out


def daily_net(legs: pd.DataFrame) -> pd.DataFrame:
    daily = legs.groupby('date', sort=True)['net_usd'].sum().reset_index()
    daily['date'] = pd.to_datetime(daily['date'])
    daily['year'] = daily['date'].dt.year
    return daily


def choose_bundles(capital: float, required_per_bundle: float, max_bundles: int) -> int:
    if required_per_bundle <= 0:
        return max_bundles
    return max(0, min(max_bundles, int(capital // required_per_bundle)))


def simulate_dynamic(
    daily: pd.DataFrame,
    required_per_bundle: float,
    max_bundles: int,
    base_max_contracts: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    start_capital = required_per_bundle
    capital = start_capital
    equity_high = capital
    dynamic_dd = 0.0
    yearly_rows = []
    daily_rows = []

    for year, group in daily.groupby('year', sort=True):
        start = capital
        bundles = choose_bundles(capital, required_per_bundle, max_bundles)
        if bundles <= 0:
            yearly_rows.append(
                {
                    'year': int(year),
                    'start_capital_usd': round(start, 2),
                    'bundles': 0,
                    'max_contracts': 0,
                    'required_capital_usd': round(required_per_bundle, 2),
                    'year_net_usd': 0.0,
                    'year_daily_dd_usd': 0.0,
                    'end_capital_usd': round(capital, 2),
                }
            )
            continue

        year_high = capital
        year_dd = 0.0
        for _, row in group.iterrows():
            pnl = float(row['net_usd']) * bundles
            capital += pnl
            equity_high = max(equity_high, capital)
            year_high = max(year_high, capital)
            dynamic_dd = min(dynamic_dd, capital - equity_high)
            year_dd = min(year_dd, capital - year_high)
            daily_rows.append(
                {
                    'date': pd.Timestamp(row['date']).date().isoformat(),
                    'year': int(year),
                    'bundles': bundles,
                    'daily_pnl_usd': round(pnl, 2),
                    'equity_usd': round(capital, 2),
                    'drawdown_usd': round(capital - equity_high, 2),
                }
            )
        yearly_rows.append(
            {
                'year': int(year),
                'start_capital_usd': round(start, 2),
                'bundles': bundles,
                'max_contracts': bundles * base_max_contracts,
                'required_capital_usd': round(required_per_bundle * bundles, 2),
                'year_net_usd': round(capital - start, 2),
                'year_daily_dd_usd': round(year_dd, 2),
                'end_capital_usd': round(capital, 2),
            }
        )

    stats = {
        'start_capital_usd': start_capital,
        'end_capital_usd': capital,
        'dynamic_net_usd': capital - start_capital,
        'dynamic_daily_dd_usd': dynamic_dd,
        'peak_bundles': max((row['bundles'] for row in yearly_rows), default=0),
    }
    return pd.DataFrame(yearly_rows), pd.DataFrame(daily_rows), stats


def money(value: float | int) -> str:
    return f'${float(value):,.0f}'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=Path('potions/mnq/case_studies/v2b_equity_scaling'))
    ap.add_argument('--max-bundles', type=int, default=250)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    lines = [
        '# v2b-Family Equity Scaling',
        '',
        'Sizing rule: run N identical bundles of the current strategy, and at each calendar-year start choose the largest N where capital is at least `3 x daily-closed max DD x N`. This is a closed/session-equity overlay; it does not include intraday open heat unless the source strategy already baked it into realized exits.',
        '',
        f'Run cap: max bundles = {args.max_bundles}.',
        '',
        '| Variant | Instrument | Start Capital | End Capital | Dynamic Net | Dynamic Daily DD | End/Start | Peak Bundles | Peak Max Contracts | Base Net | Base Daily DD |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]

    for variant in VARIANTS:
        legs = load_variant(variant)
        daily = daily_net(legs)
        base_daily_dd = max_drawdown(daily['net_usd'])
        base_trade_dd = max_drawdown(legs['net_usd'])
        base_net = float(legs['net_usd'].sum())
        required = abs(base_daily_dd) * 3.0
        yearly, dyn_daily, stats = simulate_dynamic(daily, required, args.max_bundles, variant.base_max_contracts)
        variant_dir = args.out / variant.slug
        variant_dir.mkdir(parents=True, exist_ok=True)
        yearly.to_csv(variant_dir / 'dynamic_yearly.csv', index=False)
        dyn_daily.to_csv(variant_dir / 'dynamic_daily.csv', index=False)
        legs.to_csv(variant_dir / 'normalized_legs.csv', index=False)
        base = {
            'variant': variant.label,
            'instrument': variant.instrument,
            'legs': len(legs),
            'days': daily['date'].nunique(),
            'base_net_usd': base_net,
            'base_trade_dd_usd': base_trade_dd,
            'base_daily_dd_usd': base_daily_dd,
            'required_per_bundle_usd': required,
            'base_win_rate': float((legs['net_usd'] > 0).mean() * 100.0),
            'base_profit_factor': profit_factor(legs['net_usd']),
            **stats,
            'base_max_contracts_per_bundle': variant.base_max_contracts,
            'peak_max_contracts': variant.base_max_contracts * stats['peak_bundles'],
        }
        summary_rows.append(base)
        lines.append(
            f'| {variant.label} | {variant.instrument} | {money(stats["start_capital_usd"])} | {money(stats["end_capital_usd"])} | {money(stats["dynamic_net_usd"])} | {money(stats["dynamic_daily_dd_usd"])} | {stats["end_capital_usd"] / stats["start_capital_usd"]:.2f}x | {stats["peak_bundles"]} | {int(base["peak_max_contracts"])} | {money(base_net)} | {money(base_daily_dd)} |'
        )

    pd.DataFrame(summary_rows).to_csv(args.out / 'summary.csv', index=False)
    lines.extend(
        [
            '',
            '## Notes',
            '',
            '- For v2b scaleout, one bundle is the full two-contract TP1 + runner plan.',
            '- For child variants, one bundle is the full parent/child execution path as stored in the source CSV.',
            '- The NQ v2b rows show an important brittleness: starting with exactly 3x historical daily DD, the first available year loses enough to drop below the one-bundle requirement, so the strict model stops trading thereafter. A live account would need extra buffer or an explicit minimum-size rule.',
            '- This is best used for capital-sizing sensitivity, not as proof that fills remain identical at larger size.',
            '',
        ]
    )
    (args.out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {args.out / "README.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
