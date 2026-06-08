#!/usr/bin/env python3
"""Build monthly candlestick chart archives for MNQ and NQ."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

MARKETS = {
    'mnq': {
        'daily': ROOT / 'mnq' / 'mnq_daily.csv',
        'out': ROOT / 'mnq' / 'case_studies' / 'monthly_candles',
    },
    'nq': {
        'daily': ROOT / 'nq' / 'nq_daily.csv',
        'out': ROOT / 'nq' / 'case_studies' / 'monthly_candles',
    },
}

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def aggregate_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily[['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']].copy()
    work['_month'] = work['date'].dt.to_period('M')
    rows: list[dict] = []
    for month, group in work.groupby('_month', sort=True):
        rows.append(
            {
                'month': str(month),
                'date': pd.Timestamp(month.start_time),
                'open': float(group.iloc[0]['open']),
                'high': float(group['high'].max()),
                'low': float(group['low'].min()),
                'close': float(group.iloc[-1]['close']),
                'volume': float(group['volume'].sum()),
                'symbol': str(group.iloc[-1]['symbol']),
                'daily_bars': int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def draw_candles(ax: plt.Axes, candles: pd.DataFrame, width_days: float) -> None:
    dates = pd.to_datetime(candles['date'])
    xs = mdates.date2num(dates)
    for x, (_, row) in zip(xs, candles.iterrows()):
        o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
        color = GREEN if c >= o else RED
        ax.vlines(x, l, h, color=color, linewidth=1.05, alpha=0.98, zorder=3)
        body_low = min(o, c)
        body_height = max(abs(c - o), 0.05)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width_days / 2, body_low),
                width_days,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.7,
                alpha=0.95,
                zorder=4,
            )
        )


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, color=GRID, alpha=0.16, linewidth=0.8)
    ax.tick_params(colors=TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#607D8B')
        spine.set_alpha(0.55)
    ax.yaxis.label.set_color(TEXT)
    ax.xaxis.label.set_color(TEXT)
    ax.title.set_color(TEXT)


def chart_months(candles: pd.DataFrame, path: Path, title: str, full_history: bool) -> None:
    if candles.empty:
        return
    n = len(candles)
    width = max(12, min(28, n * 0.45 if full_history else n * 0.9))
    fig, ax = plt.subplots(figsize=(width, 7.5), facecolor=BG)
    style_axis(ax)
    draw_candles(ax, candles, width_days=18 if full_history else 15)

    xs = mdates.date2num(pd.to_datetime(candles['date']))
    pad = 24
    ax.set_xlim(xs.min() - pad, xs.max() + pad)
    low = float(candles['low'].min())
    high = float(candles['high'].max())
    rng = max(high - low, 1.0)
    ax.set_ylim(low - rng * 0.06, high + rng * 0.08)
    ax.set_ylabel('Price')
    ax.set_title(title, loc='left', fontsize=13, pad=12)
    ax.title.set_color(TEXT)
    ax._left_title.set_color(TEXT)
    ax._right_title.set_color(TEXT)

    if full_history:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
        year = pd.Timestamp(candles.iloc[0]['date']).year
        ax.set_xlabel(str(year))
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)

    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_index(out_dir: Path, market: str, monthly: pd.DataFrame, year_paths: list[Path]) -> None:
    start = str(monthly.iloc[0]['month']) if not monthly.empty else ''
    end = str(monthly.iloc[-1]['month']) if not monthly.empty else ''
    lines = [
        f'# {market.upper()} Monthly Candle Archive',
        '',
        f'Source: `{MARKETS[market]["daily"].relative_to(ROOT)}`',
        f'Coverage: **{start}** through **{end}** ({len(monthly)} monthly candles).',
        '',
        'Artifacts:',
        '',
        '- [monthly_candles.csv](monthly_candles.csv)',
        '- [full_history.png](full_history.png)',
        '',
        '## Year Charts',
        '',
        '| Year | Chart | Months |',
        '|---:|---|---:|',
    ]
    for path in year_paths:
        year = path.stem
        count = int((monthly['date'].dt.year == int(year)).sum())
        lines.append(f'| {year} | [years/{path.name}](years/{path.name}) | {count} |')
    lines.append('')
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def build_market(market: str, cfg: dict) -> None:
    daily = load_daily(cfg['daily'])
    monthly = aggregate_monthly(daily)
    out_dir = cfg['out']
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_df = monthly.copy()
    csv_df['date'] = csv_df['date'].dt.strftime('%Y-%m-%d')
    csv_df.to_csv(out_dir / 'monthly_candles.csv', index=False)

    chart_months(
        monthly,
        out_dir / 'full_history.png',
        f'{market.upper()} monthly candles · {monthly.iloc[0]["month"]} to {monthly.iloc[-1]["month"]}',
        full_history=True,
    )

    year_paths: list[Path] = []
    for year, group in monthly.groupby(monthly['date'].dt.year, sort=True):
        path = out_dir / 'years' / f'{year}.png'
        chart_months(group.reset_index(drop=True), path, f'{market.upper()} monthly candles · {year}', full_history=False)
        year_paths.append(path.relative_to(out_dir / 'years'))
    write_index(out_dir, market, monthly, year_paths)
    print(f'Wrote {out_dir / "INDEX.md"}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    args = ap.parse_args()
    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        build_market(market, MARKETS[market])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
