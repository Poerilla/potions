#!/usr/bin/env python3
"""Build ATR Supertrend yearly sidecar charts with daily volume panels."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from atr_supertrend_dca_long import draw_year_chart
from redraw_atr_supertrend_charts import infer_weekly_overlay, load_trades


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

DEFAULT_VARIANT = 'atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial'


def update_base_readme(base_dir: Path) -> None:
    readme = base_dir / 'README.md'
    if not readme.exists():
        return
    text = readme.read_text(encoding='utf-8')
    line = '- [Volume sidecar yearly charts](volume_charts/INDEX.md)'
    if line in text:
        return
    if '## Year Charts' in text:
        text = text.replace('## Year Charts', f'{line}\n\n## Year Charts', 1)
    else:
        text = text.rstrip() + '\n\n' + line + '\n'
    readme.write_text(text, encoding='utf-8')


def write_indexes(out_dir: Path, market: str, variant: str, rows: list[dict], point_value: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        year_dir = out_dir / str(row['year'])
        lines = [
            f'# {market.upper()} ATR Supertrend Volume Chart {row["year"]}',
            '',
            'Daily candles with the ATR Supertrend overlay, trade markers, and a bottom volume panel. Volume is summed from the daily OHLCV cache derived from Databento.',
            '',
            f'Chart: [{row["year"]}.png]({row["year"]}.png)',
            '',
            '| Year | Active Stacks | Exit Pts | Exit $ | Daily Volume |',
            '|---:|---:|---:|---:|---:|',
            f"| {row['year']} | {row['trades_active']} | {row['exit_points']:+.2f} | ${row['exit_usd']:+,.0f} | {row['year_volume'] / 1_000_000:.2f}M |",
            '',
        ]
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    total = sum(float(row['exit_points']) for row in rows)
    lines = [
        f'# {market.upper()} {variant} Volume Sidecar Charts',
        '',
        'These are chart-only sidecars. They do not rerun the ATR Supertrend strategy or rewrite the saved trade/equity CSVs.',
        '',
        'The bottom panel shows daily volume bars plus a 20-day average so breakout/add/guard behavior can be inspected against participation.',
        '',
        f'Years charted: `{len(rows)}`  ·  Exits shown: `{total:+.2f}` pts (${total * point_value:+,.0f})',
        '',
        '| Year | Active Stacks | Exit Pts | Exit $ | Daily Volume | Chart |',
        '|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        lines.append(
            f"| {row['year']} | {row['trades_active']} | {row['exit_points']:+.2f} | "
            f"${row['exit_usd']:+,.0f} | {row['year_volume'] / 1_000_000:.2f}M | [{row['year']}/]({row['year']}/INDEX.md) |"
        )
    lines.append('')
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def run_market(root: Path, market: str, variant: str, clean: bool) -> Path:
    cfg = DEFAULT_MARKETS[market]
    daily = pd.read_csv(root / cfg['daily'], parse_dates=['date']).sort_values('date').reset_index(drop=True)
    base_dir = root / market / 'case_studies' / variant
    if not (base_dir / 'trades.csv').exists() or not (base_dir / 'units.csv').exists():
        raise FileNotFoundError(f'Missing saved ATR trade CSVs under {base_dir}')

    out_dir = base_dir / 'volume_charts'
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)

    readme_text = (base_dir / 'README.md').read_text(encoding='utf-8') if (base_dir / 'README.md').exists() else ''
    plot_weekly_atr = infer_weekly_overlay(base_dir, readme_text)
    trades = load_trades(base_dir)
    rows: list[dict] = []
    for year in sorted(daily['date'].dt.year.unique()):
        year = int(year)
        row = draw_year_chart(
            year,
            daily,
            trades,
            out_dir / str(year) / f'{year}.png',
            market.upper(),
            float(cfg['point_value']),
            atr_length=14,
            atr_multiplier=3.0,
            plot_weekly_atr=plot_weekly_atr,
            weekly_atr_length=14,
            weekly_atr_multiplier=3.0,
            atr_extension_weeks=3,
            volume_panel=True,
        )
        year_bars = daily[daily['date'].dt.year.eq(year)]
        row['year_volume'] = float(year_bars['volume'].sum()) if 'volume' in year_bars.columns else 0.0
        rows.append(row)
        print(f'{market.upper()} {variant} {row["chart"]} active={row["trades_active"]} exits={row["exit_points"]:+.2f}')

    write_indexes(out_dir, market, variant, rows, float(cfg['point_value']))
    update_base_readme(base_dir)
    print(f'Wrote {market.upper()} ATR volume sidecar: {out_dir / "INDEX.md"}')
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--markets', nargs='+', choices=sorted(DEFAULT_MARKETS), default=['mnq', 'nq'])
    ap.add_argument('--variant', default=DEFAULT_VARIANT)
    ap.add_argument('--clean', action='store_true')
    args = ap.parse_args()
    for market in args.markets:
        run_market(args.root, market, args.variant, args.clean)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
