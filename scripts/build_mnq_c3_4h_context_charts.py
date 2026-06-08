#!/usr/bin/env python3
"""Build MNQ 4-hour charts for every monthly C3 setup."""
from __future__ import annotations

import argparse
import gc
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MONTHLY_DIR = ROOT / 'mnq' / 'case_studies' / 'monthly_candles'
C3_DIR = MONTHLY_DIR / 'c3_marked'
C3_SETUPS = C3_DIR / 'c3_setups.csv'
MONTHLY_CANDLES = MONTHLY_DIR / 'monthly_candles.csv'
FOUR_H = ROOT / 'mnq' / 'data' / 'mnq_front_month_4h_from_1m.csv'
OUT_DIR = C3_DIR / '4h_context'

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'
BLUE = '#40C4FF'
YELLOW = '#FFD54F'
ORANGE = '#FF8A65'
PURPLE = '#B388FF'


def load_4h(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['ts'] = pd.to_datetime(df['time'], utc=True).dt.tz_convert('America/New_York')
    df['month'] = df['ts'].dt.tz_localize(None).dt.to_period('M').astype(str)
    return df.sort_values('ts').reset_index(drop=True)


def load_monthly(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xs = mdates.date2num(bars['ts'].dt.tz_localize(None))
    width = (xs[1] - xs[0]) * 0.72 if len(xs) > 1 else 0.10
    opens = bars['open'].astype(float).to_numpy()
    highs = bars['high'].astype(float).to_numpy()
    lows = bars['low'].astype(float).to_numpy()
    closes = bars['close'].astype(float).to_numpy()
    colors = [GREEN if c >= o else RED for o, c in zip(opens, closes)]
    body_lows = [min(o, c) for o, c in zip(opens, closes)]
    body_heights = [max(abs(c - o), 0.05) for o, c in zip(opens, closes)]
    ax.vlines(xs, lows, highs, color=colors, linewidth=0.7, alpha=0.92, zorder=3)
    ax.bar(
        xs,
        body_heights,
        bottom=body_lows,
        width=width,
        color=colors,
        edgecolor=colors,
        linewidth=0.45,
        alpha=0.88,
        align='center',
        zorder=4,
    )


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, axis='y', color=GRID, alpha=0.16, linewidth=0.8)
    ax.tick_params(colors=TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#607D8B')
        spine.set_alpha(0.55)
    ax.yaxis.label.set_color(TEXT)
    ax.xaxis.label.set_color(TEXT)
    ax.title.set_color(TEXT)


def draw_day_grid(ax: plt.Axes, bars: pd.DataFrame) -> None:
    days = pd.to_datetime(bars['ts'].dt.date).drop_duplicates()
    for day in days:
        ax.axvline(
            mdates.date2num(pd.Timestamp(day)),
            color='#90A4AE',
            linewidth=0.4,
            alpha=0.18,
            zorder=1,
        )


def line_with_label(
    ax: plt.Axes,
    x0: float,
    x1: float,
    y: float,
    label: str,
    color: str,
    linestyle: str = '-',
) -> None:
    ax.hlines(y, x0, x1, colors=color, linestyles=linestyle, linewidth=1.1, alpha=0.92, zorder=2)
    ax.text(x1, y, f' {label} {y:,.2f}', color=color, va='center', fontsize=8, zorder=6)


def chart_setup(
    setup: pd.Series,
    bars4h: pd.DataFrame,
    monthly_by_month: dict[str, pd.Series],
    out_path: Path,
) -> bool:
    c2_month = str(setup['c2_month'])
    c3_month = str(setup['c3_month'])
    c3_bars = bars4h[bars4h['month'].eq(c3_month)].copy()
    if c3_bars.empty or c2_month not in monthly_by_month:
        return False
    c2 = monthly_by_month[c2_month]
    fig, ax = plt.subplots(figsize=(16, 7.5), facecolor=BG)
    style_axis(ax)
    draw_day_grid(ax, c3_bars)
    draw_candles(ax, c3_bars)

    xs = mdates.date2num(c3_bars['ts'].dt.tz_localize(None))
    x0 = float(xs.min())
    x1 = float(xs.max())
    levels = [
        ('C2 High', float(c2['high']), GREEN, '--'),
        ('C2 Low', float(c2['low']), RED, '--'),
        ('C2 Open', float(c2['open']), BLUE, '-'),
        ('C2 Close', float(c2['close']), YELLOW, '-'),
    ]
    for label, price, color, style in levels:
        line_with_label(ax, x0, x1, price, label, color, style)

    direction = str(setup['direction'])
    hit = bool(setup['c3_hit'])
    expected = float(setup['c2_expected_extreme'])
    expected_color = GREEN if direction == 'bullish' else RED
    ax.hlines(expected, x0, x1, colors=expected_color, linestyles=':', linewidth=1.5, alpha=0.8)

    c3_high = float(c3_bars['high'].max())
    c3_low = float(c3_bars['low'].min())
    marker_x = xs[int(len(xs) * 0.03)]
    if direction == 'bullish':
        ax.scatter([marker_x], [c3_high], marker='^', s=95, color=GREEN if hit else ORANGE, zorder=8)
    else:
        ax.scatter([marker_x], [c3_low], marker='v', s=95, color=RED if hit else ORANGE, zorder=8)

    low = min(float(c3_bars['low'].min()), float(c2['low']))
    high = max(float(c3_bars['high'].max()), float(c2['high']))
    rng = max(high - low, 1.0)
    ax.set_ylim(low - rng * 0.08, high + rng * 0.10)
    ax.set_xlim(x0 - 0.12, x1 + 0.65)
    ax.set_ylabel('Price')
    ax.set_title(
        (
            f"MNQ C3 4h context | setup #{int(setup['setup_id'])} | "
            f"{c3_month} | {direction} | {'hit' if hit else 'miss'} | C2 {c2_month}"
        ),
        loc='left',
        fontsize=13,
        pad=12,
    )
    ax.title.set_color(TEXT)
    ax._left_title.set_color(TEXT)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_minor_locator(mdates.DayLocator(interval=1))

    legend_handles = [
        mpatches.Patch(facecolor='none', edgecolor=GREEN, linestyle='--', label='C2 high'),
        mpatches.Patch(facecolor='none', edgecolor=RED, linestyle='--', label='C2 low'),
        mpatches.Patch(facecolor='none', edgecolor=BLUE, label='C2 open'),
        mpatches.Patch(facecolor='none', edgecolor=YELLOW, label='C2 close'),
        mpatches.Patch(facecolor='none', edgecolor=PURPLE, linestyle=':', label='Expected C2 extreme'),
    ]
    leg = ax.legend(handles=legend_handles, loc='upper left', fontsize=8, framealpha=0.18)
    for text in leg.get_texts():
        text.set_color(TEXT)

    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    gc.collect()
    return True


def write_indexes(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        '# MNQ C3 4h Context Charts',
        '',
        'One 4-hour chart for each monthly C3 setup. Each chart shows the C3 month and overlays the prior C2 monthly open, close, high, and low.',
        '',
        '| # | C3 Month | Direction | Hit | C2 Month | Chart |',
        '|---:|---|---|---|---|---|',
    ]
    by_year: dict[str, list[dict]] = {}
    for row in rows:
        c3_year = str(row['c3_month'])[:4]
        by_year.setdefault(c3_year, []).append(row)
        rel = Path(row['path']).relative_to(OUT_DIR)
        lines.append(
            f"| {row['setup_id']} | {row['c3_month']} | {row['direction']} | "
            f"{'yes' if row['hit'] else 'no'} | {row['c2_month']} | [{rel}]({rel}) |"
        )
    lines.append('')
    (OUT_DIR / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    for year, year_rows in sorted(by_year.items()):
        year_lines = [
            f'# MNQ C3 4h Context Charts - {year}',
            '',
            '| # | C3 Month | Direction | Hit | C2 Month | Chart |',
            '|---:|---|---|---|---|---|',
        ]
        for row in year_rows:
            path = Path(row['path'])
            year_lines.append(
                f"| {row['setup_id']} | {row['c3_month']} | {row['direction']} | "
                f"{'yes' if row['hit'] else 'no'} | {row['c2_month']} | [{path.name}]({path.name}) |"
            )
        (OUT_DIR / 'years' / year / 'INDEX.md').write_text('\n'.join(year_lines) + '\n', encoding='utf-8')


def update_c3_index() -> None:
    index = C3_DIR / 'INDEX.md'
    if not index.exists():
        return
    text = index.read_text(encoding='utf-8')
    line = '- [4h context charts for every C3](4h_context/INDEX.md)'
    if line in text:
        return
    marker = '- [full_history_c3.png](full_history_c3.png)'
    if marker in text:
        text = text.replace(marker, marker + '\n' + line)
    else:
        text += '\n' + line + '\n'
    index.write_text(text, encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-charts', type=int, default=0, help='0 means all C3 setups.')
    args = parser.parse_args()

    setups = pd.read_csv(C3_SETUPS)
    if args.max_charts and args.max_charts > 0:
        setups = setups.head(args.max_charts).copy()
    monthly = load_monthly(MONTHLY_CANDLES)
    monthly_by_month = {str(row['month']): row for _, row in monthly.iterrows()}
    bars4h = load_4h(FOUR_H)

    rows: list[dict] = []
    for _, setup in setups.iterrows():
        c3_month = str(setup['c3_month'])
        year = c3_month[:4]
        direction = str(setup['direction'])
        hit = bool(setup['c3_hit'])
        name = f"{int(setup['setup_id']):03d}_{c3_month}_{direction}_{'hit' if hit else 'miss'}.png"
        out_path = OUT_DIR / 'years' / year / name
        if chart_setup(setup, bars4h, monthly_by_month, out_path):
            rows.append(
                {
                    'setup_id': int(setup['setup_id']),
                    'c3_month': c3_month,
                    'direction': direction,
                    'hit': hit,
                    'c2_month': str(setup['c2_month']),
                    'path': str(out_path),
                }
            )
    write_indexes(rows)
    update_c3_index()
    print(f'Wrote {OUT_DIR / "INDEX.md"} ({len(rows)} charts)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
