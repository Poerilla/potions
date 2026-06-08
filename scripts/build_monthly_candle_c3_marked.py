#!/usr/bin/env python3
"""Build monthly candle charts with all candlestick-theory C3 candles marked."""
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
        'monthly': ROOT / 'mnq' / 'case_studies' / 'monthly_candles' / 'monthly_candles.csv',
        'out': ROOT / 'mnq' / 'case_studies' / 'monthly_candles' / 'c3_marked',
    },
    'nq': {
        'monthly': ROOT / 'nq' / 'case_studies' / 'monthly_candles' / 'monthly_candles.csv',
        'out': ROOT / 'nq' / 'case_studies' / 'monthly_candles' / 'c3_marked',
    },
}

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'
BULL = '#64DD17'
BEAR = '#FF5252'
MISS = '#FFCA28'


def load_monthly(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def classify_c3(monthly: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for i in range(0, len(monthly) - 2):
        c1 = monthly.iloc[i]
        c2 = monthly.iloc[i + 1]
        c3 = monthly.iloc[i + 2]

        took_high = float(c2['high']) > float(c1['high'])
        closed_above = float(c2['close']) > float(c1['high'])
        took_low = float(c2['low']) < float(c1['low'])
        closed_below = float(c2['close']) < float(c1['low'])

        if took_high and closed_above:
            direction = 'bullish'
            c1_break_level = float(c1['high'])
            c2_expected_extreme = float(c2['high'])
            hit = float(c3['high']) > c2_expected_extreme or float(c3['close']) > c2_expected_extreme
            closed_beyond = float(c3['close']) > c2_expected_extreme
            extension_pts = max(0.0, float(c3['high']) - c2_expected_extreme)
            adverse_pts = max(0.0, c2_expected_extreme - float(c3['low']))
        elif took_low and closed_below:
            direction = 'bearish'
            c1_break_level = float(c1['low'])
            c2_expected_extreme = float(c2['low'])
            hit = float(c3['low']) < c2_expected_extreme or float(c3['close']) < c2_expected_extreme
            closed_beyond = float(c3['close']) < c2_expected_extreme
            extension_pts = max(0.0, c2_expected_extreme - float(c3['low']))
            adverse_pts = max(0.0, float(c3['high']) - c2_expected_extreme)
        else:
            continue

        rows.append(
            {
                'setup_id': len(rows) + 1,
                'direction': direction,
                'c1_month': c1['month'],
                'c2_month': c2['month'],
                'c3_month': c3['month'],
                'c1_break_level': round(c1_break_level, 2),
                'c2_expected_extreme': round(c2_expected_extreme, 2),
                'c2_swept_both_sides': bool(took_high and took_low),
                'c3_hit': bool(hit),
                'c3_closed_beyond_c2_extreme': bool(closed_beyond),
                'extension_pts': round(extension_pts, 2),
                'adverse_pts': round(adverse_pts, 2),
            }
        )
    return pd.DataFrame(rows)


def draw_candles(ax: plt.Axes, candles: pd.DataFrame, width_days: float) -> None:
    xs = mdates.date2num(pd.to_datetime(candles['date']))
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


def annotate_c3(
    ax: plt.Axes,
    candles: pd.DataFrame,
    setups: pd.DataFrame,
    width_days: float,
    label: bool,
) -> None:
    if setups.empty:
        return
    by_month = {str(row['month']): row for _, row in candles.iterrows()}
    low = float(candles['low'].min())
    high = float(candles['high'].max())
    yrange = max(high - low, 1.0)
    pad = yrange * 0.035
    label_pad = yrange * 0.055

    for _, setup in setups.iterrows():
        month = str(setup['c3_month'])
        if month not in by_month:
            continue
        candle = by_month[month]
        x = mdates.date2num(pd.Timestamp(candle['date']))
        direction = str(setup['direction'])
        hit = bool(setup['c3_hit'])
        edge = BULL if direction == 'bullish' else BEAR
        marker = '^' if direction == 'bullish' else 'v'
        y = float(candle['high']) + pad if direction == 'bullish' else float(candle['low']) - pad
        face = edge if hit else 'none'
        ax.add_patch(
            mpatches.Rectangle(
                (x - width_days * 0.68, float(candle['low'])),
                width_days * 1.36,
                max(float(candle['high']) - float(candle['low']), 0.05),
                facecolor='none',
                edgecolor=edge if hit else MISS,
                linewidth=1.6 if hit else 1.2,
                linestyle='-' if hit else '--',
                zorder=6,
            )
        )
        ax.scatter(
            [x],
            [y],
            marker=marker,
            s=62 if label else 34,
            facecolors=face,
            edgecolors=edge if hit else MISS,
            linewidths=1.3,
            zorder=8,
        )
        if label:
            text = f"C3 {'↑' if direction == 'bullish' else '↓'} {'hit' if hit else 'miss'}"
            ty = float(candle['high']) + label_pad if direction == 'bullish' else float(candle['low']) - label_pad
            va = 'bottom' if direction == 'bullish' else 'top'
            ax.text(x, ty, text, color=edge if hit else MISS, fontsize=7, ha='center', va=va, zorder=9)


def chart_months(
    candles: pd.DataFrame,
    setups: pd.DataFrame,
    path: Path,
    title: str,
    full_history: bool,
) -> None:
    if candles.empty:
        return
    n = len(candles)
    width = max(12, min(30, n * 0.45 if full_history else n * 0.92))
    fig, ax = plt.subplots(figsize=(width, 7.8), facecolor=BG)
    style_axis(ax)
    width_days = 18 if full_history else 15
    draw_candles(ax, candles, width_days=width_days)
    annotate_c3(ax, candles, setups, width_days=width_days, label=not full_history)

    xs = mdates.date2num(pd.to_datetime(candles['date']))
    ax.set_xlim(xs.min() - 24, xs.max() + 24)
    low = float(candles['low'].min())
    high = float(candles['high'].max())
    rng = max(high - low, 1.0)
    ax.set_ylim(low - rng * 0.10, high + rng * 0.12)
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
        ax.set_xlabel(str(pd.Timestamp(candles.iloc[0]['date']).year))
    ax.xaxis.label.set_color(TEXT)

    hit_patch = mpatches.Patch(facecolor='none', edgecolor=BULL, linewidth=1.4, label='Bullish C3 hit')
    bear_patch = mpatches.Patch(facecolor='none', edgecolor=BEAR, linewidth=1.4, label='Bearish C3 hit')
    miss_patch = mpatches.Patch(facecolor='none', edgecolor=MISS, linestyle='--', linewidth=1.2, label='C3 miss')
    leg = ax.legend(handles=[hit_patch, bear_patch, miss_patch], loc='upper left', fontsize=8, framealpha=0.18)
    for text in leg.get_texts():
        text.set_color(TEXT)

    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def setup_summary(setups: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if setups.empty:
        return pd.DataFrame(rows)
    for direction, group in setups.groupby('direction', sort=True):
        rows.append(
            {
                'direction': direction,
                'setups': int(len(group)),
                'hits': int(group['c3_hit'].sum()),
                'hit_rate': round(float(group['c3_hit'].mean()) * 100.0, 2),
                'closed_beyond': int(group['c3_closed_beyond_c2_extreme'].sum()),
                'closed_beyond_rate': round(float(group['c3_closed_beyond_c2_extreme'].mean()) * 100.0, 2),
            }
        )
    rows.append(
        {
            'direction': 'all',
            'setups': int(len(setups)),
            'hits': int(setups['c3_hit'].sum()),
            'hit_rate': round(float(setups['c3_hit'].mean()) * 100.0, 2),
            'closed_beyond': int(setups['c3_closed_beyond_c2_extreme'].sum()),
            'closed_beyond_rate': round(float(setups['c3_closed_beyond_c2_extreme'].mean()) * 100.0, 2),
        }
    )
    return pd.DataFrame(rows)


def write_index(out_dir: Path, market: str, monthly: pd.DataFrame, setups: pd.DataFrame, summary: pd.DataFrame) -> None:
    start = str(monthly.iloc[0]['month']) if not monthly.empty else ''
    end = str(monthly.iloc[-1]['month']) if not monthly.empty else ''
    lines = [
        f'# {market.upper()} Monthly Candles With C3 Marks',
        '',
        f'Coverage: **{start}** through **{end}**.',
        '',
        'C3 rule: C1 defines the range; C2 must take and close beyond C1 high/low; the next monthly candle is marked as C3. Failure sweeps are skipped.',
        '',
        'Artifacts:',
        '',
        '- [c3_setups.csv](c3_setups.csv)',
        '- [c3_summary.csv](c3_summary.csv)',
        '- [full_history_c3.png](full_history_c3.png)',
        '',
        '## Summary',
        '',
        '| Direction | Setups | Hits | Hit Rate | Closed Beyond | Closed Beyond Rate |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['direction']} | {int(row['setups'])} | {int(row['hits'])} | "
            f"{float(row['hit_rate']):.2f}% | {int(row['closed_beyond'])} | "
            f"{float(row['closed_beyond_rate']):.2f}% |"
        )
    lines.extend(['', '## Year Charts', '', '| Year | Chart | C3 Marks |', '|---:|---|---:|'])
    for year, group in monthly.groupby(monthly['date'].dt.year, sort=True):
        year_setups = setups[setups['c3_month'].astype(str).str.startswith(f'{int(year)}-')]
        lines.append(f"| {int(year)} | [years/{int(year)}.png](years/{int(year)}.png) | {len(year_setups)} |")
    lines.append('')
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def update_parent_index(parent: Path) -> None:
    index = parent / 'INDEX.md'
    if not index.exists():
        return
    text = index.read_text(encoding='utf-8')
    line = '- [C3-marked monthly candles](c3_marked/INDEX.md)'
    if line in text:
        return
    marker = '- [full_history.png](full_history.png)'
    if marker in text:
        text = text.replace(marker, marker + '\n' + line)
    else:
        text += '\n' + line + '\n'
    index.write_text(text, encoding='utf-8')


def build_market(market: str, cfg: dict) -> None:
    monthly = load_monthly(cfg['monthly'])
    setups = classify_c3(monthly)
    summary = setup_summary(setups)
    out_dir = cfg['out']
    out_dir.mkdir(parents=True, exist_ok=True)
    setups.to_csv(out_dir / 'c3_setups.csv', index=False)
    summary.to_csv(out_dir / 'c3_summary.csv', index=False)

    chart_months(
        monthly,
        setups,
        out_dir / 'full_history_c3.png',
        f'{market.upper()} monthly candles · all C3 marks · {monthly.iloc[0]["month"]} to {monthly.iloc[-1]["month"]}',
        full_history=True,
    )

    for year, group in monthly.groupby(monthly['date'].dt.year, sort=True):
        year = int(year)
        year_setups = setups[setups['c3_month'].astype(str).str.startswith(f'{year}-')]
        chart_months(
            group.reset_index(drop=True),
            year_setups,
            out_dir / 'years' / f'{year}.png',
            f'{market.upper()} monthly candles · C3 marks · {year}',
            full_history=False,
        )
    write_index(out_dir, market, monthly, setups, summary)
    update_parent_index(cfg['out'].parent)
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
