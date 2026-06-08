#!/usr/bin/env python3
"""Chart MNQ monthly C3 C2-close limit study trades."""
from __future__ import annotations

import argparse
import gc
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
NY = 'America/New_York'
STUDY_DIR = ROOT / 'mnq' / 'case_studies' / 'monthly_candles' / 'c3_marked' / 'c2_close_limit_4h_lower_high_exit'
TRADES = STUDY_DIR / 'trades.csv'
FOUR_H = ROOT / 'mnq' / 'data' / 'mnq_front_month_4h_from_1m.csv'
MONTHLY = ROOT / 'mnq' / 'case_studies' / 'monthly_candles' / 'monthly_candles.csv'
OUT_DIR = STUDY_DIR / 'charts'

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'
BLUE = '#40C4FF'
YELLOW = '#FFD54F'
ORANGE = '#FF8A65'
PURPLE = '#B388FF'
MAGENTA = '#FF66C4'


def parse_ts(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True).tz_convert(NY)


def load_4h(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars['ts'] = pd.to_datetime(bars['time'], utc=True).dt.tz_convert(NY)
    bars['month'] = bars['ts'].dt.tz_localize(None).dt.to_period('M').astype(str)
    bars['date_only'] = bars['ts'].dt.date
    return bars.sort_values('ts').reset_index(drop=True)


def load_monthly(path: Path) -> dict[str, pd.Series]:
    monthly = pd.read_csv(path)
    return {str(row['month']): row for _, row in monthly.iterrows()}


def load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades['entry_ts'] = trades['entry_time'].apply(parse_ts)
    trades['exit_ts'] = trades['exit_time'].apply(parse_ts)
    trades['result'] = trades['net_usd'].astype(float).apply(lambda value: 'winner' if value > 0 else 'loser' if value < 0 else 'scratch')
    return trades.sort_values(['entry_ts', 'setup_id', 'attempt']).reset_index(drop=True)


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
    days = pd.to_datetime(bars['date_only']).drop_duplicates()
    for day in days:
        ax.axvline(
            mdates.date2num(pd.Timestamp(day)),
            color='#90A4AE',
            linewidth=0.45,
            alpha=0.22,
            zorder=1,
        )


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xs = mdates.date2num(bars['ts'].dt.tz_localize(None))
    width = (xs[1] - xs[0]) * 0.72 if len(xs) > 1 else 0.10
    opens = bars['open'].astype(float).to_numpy()
    highs = bars['high'].astype(float).to_numpy()
    lows = bars['low'].astype(float).to_numpy()
    closes = bars['close'].astype(float).to_numpy()
    colors = [GREEN if close >= open_ else RED for open_, close in zip(opens, closes)]
    body_lows = [min(open_, close) for open_, close in zip(opens, closes)]
    body_heights = [max(abs(close - open_), 0.05) for open_, close in zip(opens, closes)]
    ax.vlines(xs, lows, highs, color=colors, linewidth=0.75, alpha=0.92, zorder=3)
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


def line_with_label(ax: plt.Axes, x0: float, x1: float, y: float, label: str, color: str, linestyle: str = '-') -> None:
    ax.hlines(y, x0, x1, colors=color, linestyles=linestyle, linewidth=1.1, alpha=0.92, zorder=2)
    ax.text(x1, y, f' {label} {y:,.2f}', color=color, va='center', fontsize=8, zorder=6)


def nearest_x(bars: pd.DataFrame, ts: pd.Timestamp) -> float:
    diffs = (bars['ts'] - ts).abs()
    pos = int(diffs.idxmin())
    return float(mdates.date2num(bars.loc[pos, 'ts'].tz_localize(None)))


def chart_trade(
    trade: pd.Series,
    bars4h: pd.DataFrame,
    monthly_by_month: dict[str, pd.Series],
    out_path: Path,
    seq: int,
    collection: str,
) -> bool:
    entry_ts = pd.Timestamp(trade['entry_ts'])
    exit_ts = pd.Timestamp(trade['exit_ts'])
    start = entry_ts - pd.Timedelta(days=8)
    end = exit_ts + pd.Timedelta(days=4)
    c3_month = str(trade['c3_month'])
    c3_bars = bars4h[bars4h['month'].eq(c3_month)]
    if not c3_bars.empty:
        start = min(start, pd.Timestamp(c3_bars['ts'].iloc[0]))
    bars = bars4h[(bars4h['ts'] >= start) & (bars4h['ts'] <= end)].copy()
    if bars.empty:
        return False

    c2 = monthly_by_month.get(str(trade['c2_month']))
    xs = mdates.date2num(bars['ts'].dt.tz_localize(None))
    x0 = float(xs.min())
    x1 = float(xs.max())
    entry_x = nearest_x(bars, entry_ts)
    exit_x = nearest_x(bars, exit_ts)

    fig, ax = plt.subplots(figsize=(17, 8), facecolor=BG)
    style_axis(ax)
    draw_day_grid(ax, bars)
    draw_candles(ax, bars)

    if c2 is not None:
        line_with_label(ax, x0, x1, float(c2['high']), 'C2 high', GREEN, '--')
        line_with_label(ax, x0, x1, float(c2['low']), 'C2 low', RED, '--')
        line_with_label(ax, x0, x1, float(c2['open']), 'C2 open', BLUE, ':')
    line_with_label(ax, x0, x1, float(trade['c2_close']), 'C2 close / entry limit', YELLOW, '-')
    line_with_label(ax, x0, x1, float(trade['stop_level']), '50pt close stop', RED, '-.')

    ax.axvline(entry_x, color=ORANGE, linewidth=1.25, alpha=0.85, zorder=5)
    ax.scatter([entry_x], [float(trade['entry_px'])], marker='^', s=95, color=ORANGE, zorder=8, label='entry fill')

    exit_color = GREEN if float(trade['net_usd']) > 0 else RED if float(trade['net_usd']) < 0 else PURPLE
    ax.axvline(exit_x, color=exit_color, linewidth=1.25, alpha=0.88, zorder=5)
    ax.scatter([exit_x], [float(trade['exit_px'])], marker='o', s=80, color=exit_color, zorder=8, label='exit')

    low = min(float(bars['low'].min()), float(trade['stop_level']), float(trade['entry_px']), float(trade['exit_px']))
    high = max(float(bars['high'].max()), float(trade['entry_px']), float(trade['exit_px']))
    if c2 is not None:
        low = min(low, float(c2['low']))
        high = max(high, float(c2['high']))
    rng = max(high - low, 1.0)
    ax.set_ylim(low - rng * 0.08, high + rng * 0.10)
    ax.set_xlim(x0 - 0.20, x1 + 0.75)

    ax.set_ylabel('Price')
    title = (
        f"MNQ C3 C2-close retest | {collection} #{seq:03d} | "
        f"setup {int(trade['setup_id'])}.{int(trade['attempt'])} | C3 {trade['c3_month']} | "
        f"{trade['exit_category']} | {float(trade['net_pts']):+.2f} pts / ${float(trade['net_usd']):+,.0f} | "
        f"MAE {float(trade['mae_pts']):.2f} pts | MFE {float(trade['mfe_pts']):.2f} pts"
    )
    ax.set_title(title, loc='left', fontsize=12, pad=12)
    ax._left_title.set_color(TEXT)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, min(7, len(bars['date_only'].unique()) // 8 or 1))))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    handles = [
        mpatches.Patch(facecolor='none', edgecolor=YELLOW, label='C2 close / entry'),
        mpatches.Patch(facecolor='none', edgecolor=RED, label='50pt close stop'),
        mpatches.Patch(facecolor='none', edgecolor=ORANGE, label='entry marker'),
        mpatches.Patch(facecolor='none', edgecolor=exit_color, label='exit marker'),
    ]
    leg = ax.legend(handles=handles, loc='upper left', fontsize=8, framealpha=0.18)
    for text in leg.get_texts():
        text.set_color(TEXT)
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    gc.collect()
    return True


def write_index(out_dir: Path, title: str, description: str, rows: list[dict]) -> None:
    lines = [
        f'# {title}',
        '',
        description,
        '',
        f'Charts: `{len(rows)}`',
        '',
        '| # | Setup | C3 Month | Exit | P/L | MAE | MFE | Chart |',
        '|---:|---:|---|---|---:|---:|---:|---|',
    ]
    for row in rows:
        rel = Path(row['path']).relative_to(out_dir)
        lines.append(
            f"| {row['seq']} | {row['setup_id']}.{row['attempt']} | {row['c3_month']} | "
            f"{row['exit_category']} | {row['net_pts']:+.2f} pts | {row['mae_pts']:.2f} | "
            f"{row['mfe_pts']:.2f} | [{rel}]({rel}) |"
        )
    (out_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def chart_collection(name: str, trades: pd.DataFrame, bars4h: pd.DataFrame, monthly_by_month: dict[str, pd.Series], out_dir: Path) -> int:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for seq, (_, trade) in enumerate(trades.iterrows(), 1):
        result = str(trade['result'])
        c3_month = str(trade['c3_month'])
        filename = f"{seq:03d}_setup_{int(trade['setup_id']):02d}_{int(trade['attempt']):02d}_{c3_month}_{result}.png"
        path = out_dir / filename
        if not chart_trade(trade, bars4h, monthly_by_month, path, seq, name):
            continue
        rows.append(
            {
                'seq': seq,
                'setup_id': int(trade['setup_id']),
                'attempt': int(trade['attempt']),
                'c3_month': c3_month,
                'exit_category': str(trade['exit_category']),
                'net_pts': float(trade['net_pts']),
                'mae_pts': float(trade['mae_pts']),
                'mfe_pts': float(trade['mfe_pts']),
                'path': path,
            }
        )
    return len(rows)


def write_master_index(collections: list[tuple[str, Path, str, int]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        '# MNQ Monthly C3 C2-Close Limit Trade Charts',
        '',
        '4-hour trade charts for the C2-close limit / daily lower-high exit study.',
        '',
        '| Collection | Count | Notes |',
        '|---|---:|---|',
    ]
    for label, path, notes, count in collections:
        rel = path.relative_to(OUT_DIR)
        lines.append(f"| [{label}]({rel}/INDEX.md) | {count} | {notes} |")
    (OUT_DIR / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def update_readme_links(collections: list[tuple[str, Path, str, int]]) -> None:
    readme = STUDY_DIR / 'README.md'
    if not readme.exists():
        return
    text = readme.read_text(encoding='utf-8')
    marker = '## Chart Sets'
    block = [
        marker,
        '',
        '- [All chart collections](charts/INDEX.md)',
    ]
    for label, path, _notes, _count in collections:
        rel = path.relative_to(STUDY_DIR)
        block.append(f'- [{label}]({rel}/INDEX.md)')
    block.extend([''])
    block_text = '\n'.join(block)
    if marker in text:
        before = text.split(marker, 1)[0].rstrip()
        after = text.split(marker, 1)[1]
        next_marker = after.find('\n## ')
        if next_marker >= 0:
            text = before + '\n\n' + block_text + after[next_marker:]
        else:
            text = before + '\n\n' + block_text + '\n'
    else:
        insert = '## Causality Notes'
        if insert in text:
            text = text.replace(insert, block_text + '\n' + insert)
        else:
            text = text.rstrip() + '\n\n' + block_text + '\n'
    readme.write_text(text, encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--charts', choices=['all', 'daily-lh', 'losers'], default='all')
    args = ap.parse_args()

    bars4h = load_4h(FOUR_H)
    monthly_by_month = load_monthly(MONTHLY)
    trades = load_trades(TRADES)

    collections: list[tuple[str, Path, str, int]] = []
    if args.charts in {'all', 'daily-lh'}:
        daily_lh = trades[trades['exit_category'].eq('daily_lower_high_next_4h_open')].copy()
        for result, title, notes in [
            ('winner', 'Daily lower-high winners', 'Trades that exited via daily lower high with positive P/L.'),
            ('loser', 'Daily lower-high losers', 'Trades that exited via daily lower high with negative P/L.'),
        ]:
            subset = daily_lh[daily_lh['result'].eq(result)].copy()
            path = OUT_DIR / 'daily_lower_high_exits' / f'{result}s'
            count = chart_collection(title, subset, bars4h, monthly_by_month, path)
            write_index(path, f'MNQ C3 C2-Close Limit - {title}', notes, [
                {
                    'seq': i,
                    'setup_id': int(row['setup_id']),
                    'attempt': int(row['attempt']),
                    'c3_month': str(row['c3_month']),
                    'exit_category': str(row['exit_category']),
                    'net_pts': float(row['net_pts']),
                    'mae_pts': float(row['mae_pts']),
                    'mfe_pts': float(row['mfe_pts']),
                    'path': path / f"{i:03d}_setup_{int(row['setup_id']):02d}_{int(row['attempt']):02d}_{row['c3_month']}_{result}.png",
                }
                for i, (_, row) in enumerate(subset.iterrows(), 1)
            ])
            collections.append((title, path, notes, count))

    if args.charts in {'all', 'losers'}:
        losers = trades[trades['result'].eq('loser')].copy()
        path = OUT_DIR / 'all_losers'
        notes = 'Every losing trade from the study, including 4-hour close-stop and lower-high exits.'
        count = chart_collection('All losers', losers, bars4h, monthly_by_month, path)
        write_index(path, 'MNQ C3 C2-Close Limit - All Losers', notes, [
            {
                'seq': i,
                'setup_id': int(row['setup_id']),
                'attempt': int(row['attempt']),
                'c3_month': str(row['c3_month']),
                'exit_category': str(row['exit_category']),
                'net_pts': float(row['net_pts']),
                'mae_pts': float(row['mae_pts']),
                'mfe_pts': float(row['mfe_pts']),
                'path': path / f"{i:03d}_setup_{int(row['setup_id']):02d}_{int(row['attempt']):02d}_{row['c3_month']}_loser.png",
            }
            for i, (_, row) in enumerate(losers.iterrows(), 1)
        ])
        collections.append(('All losers', path, notes, count))

    write_master_index(collections)
    update_readme_links(collections)
    print(f'Wrote {OUT_DIR / "INDEX.md"}')
    for label, path, _notes, count in collections:
        print(f'{label}: {count} charts -> {path / "INDEX.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
