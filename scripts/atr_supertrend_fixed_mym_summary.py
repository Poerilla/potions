#!/usr/bin/env python3
"""Fixed-size MYM ATR Supertrend summary for the four current variants."""
from __future__ import annotations

from pathlib import Path
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


VARIANTS = [
    ('Daily primary, 3-initial', 'daily_3initial', 'daily', [3] + [1] * 120),
    ('Daily primary, ladder 1/1/2/2/2', 'daily_ladder112221', 'daily', [1, 1, 2, 2, 2] + [1] * 120),
    ('Weekly primary, 3-initial', 'weekly_3initial', 'weekly', [3] + [1] * 120),
    ('Weekly primary, ladder 1/1/2/2/2', 'weekly_ladder112221', 'weekly', [1, 1, 2, 2, 2] + [1] * 120),
]


def money(value: float) -> str:
    return f'${value:,.0f}'


def summarize(trades: pd.DataFrame, units: pd.DataFrame, equity: pd.DataFrame, point_value: float) -> dict:
    pnl = pd.to_numeric(trades['net_points'], errors='coerce').fillna(0.0)
    eq = pd.to_numeric(equity['total_equity_points'], errors='coerce').fillna(0.0)
    mtm_dd = float((eq - eq.cummax()).min() * point_value)
    return {
        'stacks': len(trades),
        'units': len(units),
        'net_usd': float(pnl.sum() * point_value),
        'closed_dd_usd': float(max_drawdown(pnl) * point_value),
        'mtm_dd_usd': mtm_dd,
        'worst_mae_usd': float(pd.to_numeric(trades['mae_usd'], errors='coerce').fillna(0.0).min()),
        'avg_mae_usd': float(pd.to_numeric(trades['mae_usd'], errors='coerce').fillna(0.0).mean()),
        'win_rate': float((pnl > 0).mean() * 100.0),
        'pf': float(profit_factor(pnl)) if not pnl.empty else math.nan,
    }


def main() -> int:
    market = 'mym'
    point_value = 0.5
    daily = pd.read_csv('potions/mym/mym_daily.csv', parse_dates=['date']).sort_values('date').reset_index(drop=True)
    add_prices = load_1550_prices(Path('potions/mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst'), market)
    out = Path('potions/mym/case_studies/atr_supertrend_fixed_no_scaling')
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for label, slug, signal_timeframe, schedule in VARIANTS:
        if signal_timeframe == 'weekly':
            trades, equity, _ = simulate_weekly_primary(
                daily, add_prices, point_value, 14, 3.0, 'long', 10, 1, schedule, 2, 'exit-reclaim', 'none'
            )
        else:
            trades, equity, _ = simulate(
                daily,
                add_prices,
                point_value,
                14,
                3.0,
                'long',
                10,
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
        trades_df = pd.DataFrame(trade_rows(trades, point_value))
        units_df = pd.DataFrame(unit_rows(trades, point_value))
        variant_dir = out / slug
        variant_dir.mkdir(parents=True, exist_ok=True)
        trades_df.to_csv(variant_dir / 'trades.csv', index=False)
        units_df.to_csv(variant_dir / 'units.csv', index=False)
        equity.to_csv(variant_dir / 'equity.csv', index=False)
        rows.append({'variant': label, **summarize(trades_df, units_df, equity, point_value)})

    summary = pd.DataFrame(rows)
    summary.to_csv(out / 'summary.csv', index=False)
    lines = [
        '# MYM ATR Supertrend Fixed No-Scaling Summary',
        '',
        'Point value used here is MYM = $0.50/point. These are fixed 10-max variants, before the yearly equity-scaling overlay.',
        '',
        '| Variant | Stacks | Units | Net | Closed DD | MTM DD | Worst MAE | Avg MAE | Win Rate | PF |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        lines.append(
            f'| {row["variant"]} | {row["stacks"]} | {row["units"]} | {money(row["net_usd"])} | {money(row["closed_dd_usd"])} | {money(row["mtm_dd_usd"])} | {money(row["worst_mae_usd"])} | {money(row["avg_mae_usd"])} | {row["win_rate"]:.1f}% | {row["pf"]:.2f} |'
        )
    lines.append('')
    (out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {out / "README.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
