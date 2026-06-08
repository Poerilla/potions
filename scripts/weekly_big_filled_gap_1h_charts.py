#!/usr/bin/env python3
"""1-hour chart study for big weekly gaps.

Input is the annotated weekly_gap_size_yorb.csv produced by
weekly_gap_size_yorb_analysis.py. The script filters:

- point_size_bucket == Big
- filled == 1 by default, or filled == 0 with --status unfilled

Each chart shows the first trading week after the previous weekly RTH close
to current-week 09:30 ET open gap, using 1-hour candles from the 1-minute
source. It marks:

- previous weekly RTH close;
- current week 09:30 ET open;
- first fill time back to the previous close when present.
"""
from __future__ import annotations

from pathlib import Path

import argparse
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pytz


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hourly_gap_fill_analysis import RTH_OPEN, iso_week_key, load_front_month_by_date  # noqa: E402


NY = pytz.timezone('America/New_York')


def weekly_chart_window(by_date: dict, open_date) -> pd.DataFrame:
    week = iso_week_key(open_date)
    frames = []
    for d in sorted(by_date):
        if iso_week_key(d) != week or d.weekday() > 4:
            continue
        frames.append(by_date[d])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def resample_1h(df1: pd.DataFrame) -> pd.DataFrame:
    return (
        df1.resample('1h', label='left', closed='left', origin='start_day')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            volume=('volume', 'sum'),
            symbol=('symbol', 'last'),
        )
        .dropna(subset=['open'])
    )


def draw_candles(ax, bars: pd.DataFrame) -> None:
    xnums = mdates.date2num(bars.index.tz_convert(None).to_pydatetime())
    width = 45.0 / (24 * 60)
    for x, (_, row) in zip(xnums, bars.iterrows()):
        open_px, high_px, low_px, close_px = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if close_px >= open_px else '#EF5350'
        ax.vlines(x, low_px, high_px, color=color, linewidth=0.85, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(open_px, close_px)),
                width,
                max(abs(close_px - open_px), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.96,
                zorder=4,
            )
        )


def draw_chart(row: pd.Series, by_date: dict, out_path: Path) -> str:
    open_d = pd.Timestamp(row['open_date']).date()
    df1 = weekly_chart_window(by_date, open_d)
    if df1.empty:
        return ''
    bars1h = resample_1h(df1)
    if bars1h.empty:
        return ''

    prev_close = float(row['prev_close'])
    open_px = float(row['open_px'])
    gap_pts = float(row['gap_pts'])
    abs_gap = float(row['abs_gap_pts'])
    fill_time = str(row['fill_time'])
    direction = str(row['direction'])
    alignment = str(row.get('open_yorb_alignment', ''))
    state = str(row.get('open_yorb_state', ''))

    fig = plt.figure(figsize=(18, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars1h)

    close_color = '#FFD54F'
    open_color = '#4FC3F7' if gap_pts > 0 else '#FFB74D'
    fill_color = '#E0E0E0'
    ax.axhline(prev_close, color=close_color, linestyle='--', linewidth=1.35, zorder=2)
    ax.axhline(open_px, color=open_color, linestyle=':', linewidth=1.1, zorder=2)

    open_ts = pd.Timestamp.combine(open_d, RTH_OPEN).tz_localize(NY).tz_convert(None)
    ax.scatter(
        [mdates.date2num(open_ts.to_pydatetime())],
        [open_px],
        marker='o',
        color=open_color,
        s=75,
        zorder=10,
        edgecolor='black',
        linewidth=0.9,
    )

    if fill_time:
        fill_ts = pd.Timestamp(fill_time).tz_convert(NY).tz_convert(None)
        ax.scatter(
            [mdates.date2num(fill_ts.to_pydatetime())],
            [prev_close],
            marker='X',
            color=fill_color,
            s=95,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )
        ax.text(
            mdates.date2num(fill_ts.to_pydatetime()),
            prev_close,
            ' fill',
            color=fill_color,
            fontsize=8,
            va='bottom',
            ha='left',
        )

    x_right = mdates.date2num(bars1h.index[-1].tz_convert(None).to_pydatetime()) + 0.08
    ax.text(x_right, prev_close, f' Prev close {prev_close:.2f}', color=close_color, fontsize=9, va='center', fontweight='bold')
    ax.text(x_right, open_px, f' Week open {open_px:.2f}', color=open_color, fontsize=9, va='center')

    status = 'filled' if int(row.get('filled', 0)) else 'unfilled'
    title = f'{row["market"]} big {status} weekly gap {open_d.isoformat()} {direction} {gap_pts:+.2f} pts'
    subtitle = (
        f'Abs gap {abs_gap:.2f} pts · Fill {fill_time or "not filled"} · '
        f'YORB open state {state} / {alignment}'
    )
    ax.set_title(title + '\n' + subtitle, color='white', fontsize=10, fontweight='bold', loc='left', pad=10)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    ax.tick_params(axis='x', which='minor', labelsize=0)
    x0 = bars1h.index[0].tz_convert(None) - pd.Timedelta(hours=2)
    x1 = bars1h.index[-1].tz_convert(None) + pd.Timedelta(hours=4)
    ax.set_xlim(x0, x1)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)
    return str(out_path)


def summarize(df: pd.DataFrame) -> dict:
    big = df[df['point_size_bucket'].eq('Big')].copy()
    filled = big[pd.to_numeric(big['filled']) == 1]
    return {
        'big_total': int(len(big)),
        'big_filled': int(len(filled)),
        'big_not_filled': int(len(big) - len(filled)),
        'big_fill_rate': float(len(filled) / len(big)) if len(big) else 0.0,
    }


def write_indexes(out_root: Path, market: str, charted: pd.DataFrame, source_summary: dict, status: str) -> None:
    status_title = 'filled' if status == 'filled' else 'unfilled'
    by_year: dict[int, pd.DataFrame] = {}
    if not charted.empty:
        charted = charted.copy()
        charted['year'] = pd.to_datetime(charted['open_date']).dt.year.astype(int)
        for year, sub in charted.groupby('year', sort=True):
            by_year[int(year)] = sub.sort_values('open_date')

    for year, sub in by_year.items():
        year_dir = out_root / str(year)
        lines = [
            f'# {market} {year} big {status_title} weekly gap 1h charts',
            '',
            '| Week Open | Direction | Gap Pts | Fill Time | YORB Alignment | Chart |',
            '|---:|---|---:|---:|---|---|',
        ]
        for _, row in sub.iterrows():
            chart_name = Path(str(row['chart'])).name
            lines.append(
                f'| {row["open_date"]} | {row["direction"]} | {float(row["gap_pts"]):+.2f} | '
                f'{row["fill_time"]} | {row["open_yorb_alignment"]} | [{chart_name}]({chart_name}) |'
            )
        lines.append('')
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    lines = [
        f'# {market} Big {status_title.title()} Weekly Gap 1h Study',
        '',
        f'Charts include only weekly gaps whose empirical point-size bucket is `Big` and status is `{status_title}` before the end of the same trading week.',
        '',
        '| Big Gaps | Filled | Not Filled | Fill Rate | Charts |',
        '|---:|---:|---:|---:|---:|',
        f'| {source_summary["big_total"]} | {source_summary["big_filled"]} | {source_summary["big_not_filled"]} | {source_summary["big_fill_rate"] * 100:.1f}% | {len(charted)} |',
        '',
        '## By Direction',
        '',
        '| Direction | Charts | Median Gap | Max Gap |',
        '|---|---:|---:|---:|',
    ]
    for direction, sub in charted.groupby('direction', sort=True):
        lines.append(
            f'| {direction} | {len(sub)} | {float(sub["abs_gap_pts"].median()):.2f} | {float(sub["abs_gap_pts"].max()):.2f} |'
        )
    lines.extend(['', '## By Year', '', '| Year | Charts | Folder |', '|---:|---:|---|'])
    for year, sub in by_year.items():
        lines.append(f'| {year} | {len(sub)} | [{year}/]({year}/INDEX.md) |')
    lines.extend(
        [
            '',
            '## Files',
            '',
            f'- `big_{status}_weekly_gap_1h.csv`',
            '- `README.md`',
            '',
        ]
    )
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def run(args: argparse.Namespace) -> pd.DataFrame:
    market = args.market.upper()
    annotated = pd.read_csv(args.annotated_weekly_csv).fillna('')
    summary = summarize(annotated)
    wanted_filled = 1 if args.status == 'filled' else 0
    targets = annotated[
        annotated['point_size_bucket'].eq('Big') & (pd.to_numeric(annotated['filled']) == wanted_filled)
    ].copy()
    targets = targets.sort_values(['open_date', 'direction']).reset_index(drop=True)

    by_date = load_front_month_by_date(args.source_1m, market)
    chart_paths = []
    for _, row in targets.iterrows():
        open_d = pd.Timestamp(row['open_date']).date()
        year = open_d.year
        direction_tag = 'up' if row['direction'] == 'Gap Up' else 'down'
        name = f'{open_d.isoformat()}_{direction_tag}_big_{args.status}_1h.png'
        out_path = args.out / str(year) / name
        path = draw_chart(row, by_date, out_path)
        chart_paths.append(str(Path(path).relative_to(args.out)) if path else '')

    targets['chart'] = chart_paths
    args.out.mkdir(parents=True, exist_ok=True)
    targets.to_csv(args.out / f'big_{args.status}_weekly_gap_1h.csv', index=False)
    write_indexes(args.out, market, targets[targets['chart'].astype(str).ne('')], summary, args.status)
    print(
        f'{market}: big gaps={summary["big_total"]}, filled={summary["big_filled"]}, '
        f'not_filled={summary["big_not_filled"]}, charts={sum(1 for p in chart_paths if p)}'
    )
    print(f'Wrote {args.out / "README.md"}')
    return targets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', required=True)
    ap.add_argument('--annotated-weekly-csv', type=Path, required=True)
    ap.add_argument('--source-1m', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--status', choices=['filled', 'unfilled'], default='filled')
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
