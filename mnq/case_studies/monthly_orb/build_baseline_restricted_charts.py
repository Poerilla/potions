#!/usr/bin/env python3
"""Annotated daily charts from monthly ORB *restricted* trade CSV.

Rules match ``scripts/monthly_orb_restricted.py`` outputs: baseline boundary
retest fills, measured-move targets, and daily **close back inside**
range as ``Range-Close`` exits where applicable.

Output: ``baseline_restricted/<year>/<YYYY-MM>.png`` plus ``INDEX.md`` files.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


MNQ_ROOT = Path('/home/tester/hsm/potions/mnq')


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def trade_pattern_row(direction: str, result: str) -> str:
    d = direction[0] if direction else '?'
    r = result[0] if result else '?'
    return f'{d}{r}'


def draw_period(
    period: str,
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    out_path: Path,
    point_value_usd: float,
) -> dict | None:
    period_rows = trades[trades['Period'].astype(str) == period].copy()
    if period_rows.empty:
        return None

    range_bars = bars.iloc[:3].copy()
    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    if range_val <= 0:
        return None

    chart_trades = period_rows
    if 'Trade_Direction' in chart_trades.columns:
        chart_trades = chart_trades[chart_trades['Trade_Direction'].astype(str) != 'No-Op'].copy()

    fig = plt.figure(figsize=(14, 8), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    width = 0.58
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.8, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )

    range_start = pd.Timestamp(range_bars.iloc[0]['date'])
    range_end = pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1)
    ax.axvspan(range_start, range_end, color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhline(range_high, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.10, zorder=0)

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'Range-Close': '#FFB74D', 'Period-Close': '#FFB74D'}
    label_offsets = [22, -34, 46, -58]

    patterns: list[str] = []

    sym = str(bars.iloc[0]['symbol'])

    if chart_trades.empty:
        pattern = 'No-Op'
        total_pl = 0.0
        ax.text(
            0.5,
            0.90,
            'No filled trades (CSV No-Op): no usable breakout / retest in period.',
            transform=ax.transAxes,
            color='#FFB74D',
            fontsize=10,
            ha='center',
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.35', fc='#0D1B2A', ec='#FFB74D', alpha=0.92),
            zorder=12,
        )
    else:
        for i, (_, tr) in enumerate(chart_trades.iterrows(), 1):
            direction = str(tr['Trade_Direction'])
            entry = float(tr['Entry_Price'])
            exit_px = float(tr['Exit_Price'])
            rh = float(tr['Range_High'])
            rl = float(tr['Range_Low'])
            rng = float(tr['Range'])
            result = str(tr['Result'])

            if direction == 'Long':
                target, stop = rh + rng, rl
            else:
                target, stop = rl - rng, rh

            entry_date = pd.Timestamp(tr['Entry_Date'])
            exit_date = pd.Timestamp(tr['Exit_Date'])
            pl = float(tr['Trade_PL'])
            patterns.append(trade_pattern_row(direction, result))

            x_e = mdates.date2num(entry_date)
            x_x = mdates.date2num(exit_date)
            ax.scatter(
                [x_e],
                [entry],
                marker='^' if direction == 'Long' else 'v',
                color='#FFC107',
                s=140,
                zorder=10,
                edgecolor='black',
                linewidth=1.2,
            )
            ax.annotate(
                f'#{i} {direction[0]} @ {entry:.2f}',
                xy=(x_e, entry),
                xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color='#FFC107',
                fontsize=8,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
            )
            ax.plot([x_e, x_x], [target, target], color='#76FF03', linewidth=0.9, alpha=0.65, zorder=4)
            ax.plot([x_e, x_x], [stop, stop], color='#FF1744', linewidth=0.9, alpha=0.65, zorder=4)
            exit_color = color_for.get(result, '#FFB74D')
            ax.scatter([x_x], [exit_px], marker='X', color=exit_color, s=140, zorder=10, edgecolor='black', linewidth=1.2)
            ax.annotate(
                f'#{i} {result} {pl:+.0f}pt',
                xy=(x_x, exit_px),
                xytext=(8, -label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=exit_color,
                fontsize=8,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=exit_color, alpha=0.95),
            )
        pattern = '+'.join(patterns)
        total_pl = float(chart_trades['Trade_PL'].sum())

    last_x = xnums[-1] + 0.4
    ax.text(last_x, range_high, f' RH {range_high:.1f}', color='#E0E0E0', fontsize=7, va='center')
    ax.text(last_x, range_low, f' RL {range_low:.1f}', color='#E0E0E0', fontsize=7, va='center')

    trade_count = 0 if chart_trades.empty else len(chart_trades)
    csv_pl_total = float(period_rows['Trade_PL'].sum())
    usd_suffix = '' if abs(point_value_usd - 1.0) < 1e-9 else f' (${total_pl * point_value_usd:+.0f})'
    title = (
        f'{period}  {sym}  MONTHLY ORB BASELINE+RESTRICTED  ·  '
        f'Range {range_val:.1f}  ·  {pattern}  ·  {total_pl:+.1f}pt{usd_suffix}'
    )
    ax.set_title(title, color='white', fontsize=9, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=2))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)

    return {
        'period': period,
        'year': int(period[:4]),
        'symbol': sym,
        'range': round(range_val, 2),
        'pattern': pattern,
        'trades': trade_count,
        'net_pts': round(total_pl, 2),
        'csv_net_pts': round(csv_pl_total, 2),
        'chart': f'{period[:4]}/{period}.png',
    }


def write_indexes(out_root: Path, rows: list[dict], multiplier: float) -> None:
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        by_year.setdefault(int(row['year']), []).append(row)

    title_block = '\n'.join(
        [
            '# Monthly ORB baseline + restricted charts',
            '',
            'Annotated from `mnq_monthly_orb_restricted.csv`: same mechanics as unrestricted '
            'monthly ORB, plus **daily close back inside** the monthly opening range exits. '
            'Months with CSV **No-Op** rows only are charted as the range window with '
            'no trade markers.',
            '',
        ]
    )

    for year, yr_rows in sorted(by_year.items()):
        idx = out_root / str(year) / 'INDEX.md'
        total = sum(r['net_pts'] for r in yr_rows)
        idx.write_text(
            '\n'.join(
                [
                    f'# {year} baseline+restricted charts',
                    '',
                    f'Periods: {len(yr_rows)}  ·  Net: {total:+.2f} pts (${total * multiplier:+,.0f} gross @ ${multiplier}/pt)',
                    '',
                    '| Period | Symbol | Range | Pattern | Trades | Net pts | Chart |',
                    '|---|---|---:|---|---:|---:|---|',
                    *[
                        (
                            f"| {r['period']} | {r['symbol']} | {r['range']:.2f} | "
                            f"{r['pattern']} | {r['trades']} | {r['net_pts']:+.2f} "
                            f"| [{r['period']}.png]({r['period']}.png) |"
                        )
                        for r in sorted(yr_rows, key=lambda x: x['period'])
                    ],
                    '',
                ]
            ),
            encoding='utf-8',
        )

    total = sum(r['net_pts'] for r in rows)
    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                title_block,
                f'Periods charted: {len(rows)}  ·  Net: {total:+.2f} pts (${total * multiplier:+,.0f} gross @ ${multiplier}/pt)',
                '',
                '| Year | Periods | Net pts | Folder |',
                '|---:|---:|---:|---|',
                *[
                    (
                        f"| {year} | {len(yr_rows)} | {sum(rr['net_pts'] for rr in yr_rows):+.2f} "
                        f"| [{year}/]({year}/INDEX.md) |"
                    )
                    for year, yr_rows in sorted(by_year.items())
                ],
                '',
                '## All periods',
                '',
                '| Period | Symbol | Range | Pattern | Trades | Net pts | Chart |',
                '|---|---|---:|---|---:|---:|---|',
                *[
                    (
                        f"| {r['period']} | {r['symbol']} | {r['range']:.2f} | {r['pattern']} | "
                        f"{r['trades']} | {r['net_pts']:+.2f} | [{r['chart']}]({r['chart']}) |"
                    )
                    for r in sorted(rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument(
        '--restricted-csv',
        type=Path,
        default=MNQ_ROOT / 'mnq_monthly_orb_restricted.csv',
        help='Trades CSV from monthly_orb_restricted.py',
    )
    ap.add_argument(
        '--out',
        type=Path,
        default=MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'baseline_restricted',
    )
    ap.add_argument(
        '--point-value-usd',
        type=float,
        default=2.0,
        help='Usd per index point per contract (MNQ ~= 2.0 for 1 MNQ point).',
    )
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    trades = pd.read_csv(args.restricted_csv)
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]

    rows: list[dict] = []
    for period, bars in period_groups(daily):
        if trades[trades['Period'].astype(str) == period].empty:
            continue
        out_path = args.out / period[:4] / f'{period}.png'
        row = draw_period(period, bars, trades, out_path, args.point_value_usd)
        if row:
            rows.append(row)
            print(f'{row["chart"]} {row["net_pts"]:+.2f}pt')

    args.out.mkdir(parents=True, exist_ok=True)
    write_indexes(args.out, rows, args.point_value_usd)
    print(f'Wrote {len(rows)} charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
