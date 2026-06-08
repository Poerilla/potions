#!/usr/bin/env python3
"""Build annotated daily charts for MNQ yearly ORB periods.

Yearly ORB range = Jan-Mar. Trades are evaluated from Apr-Dec using the same
daily ORB rules as ``potions/scripts/daily_orb.py``: wait for a daily close
outside the range, place a retest entry at the broken boundary, target one
range extension, stop at the opposite boundary, and allow up to two trades per
period.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import argparse

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


MNQ_ROOT = Path('/home/tester/hsm/potions/mnq')
DAILY_CSV = MNQ_ROOT / 'mnq_daily.csv'
YEARLY_ORB_CSV = MNQ_ROOT / 'mnq_yearly_orb.csv'
OUT_ROOT = MNQ_ROOT / 'case_studies' / 'yearly_orb'

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_PERIOD = 2


@dataclass
class ChartTrade:
    direction: str
    entry: float
    exit_price: float
    target: float
    stop: float
    pl: float
    result: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    drawdown_pct: float


def simulate_period_with_dates(
    range_high: float,
    range_low: float,
    range_val: float,
    trade_bars: pd.DataFrame,
) -> list[ChartTrade]:
    phase = WAIT_BREAKOUT
    direction: Optional[str] = None
    entry = target = stop = None
    entry_date: Optional[pd.Timestamp] = None
    max_adverse = 0.0
    trades: list[ChartTrade] = []

    for _, bar in trade_bars.iterrows():
        if len(trades) >= MAX_TRADES_PER_PERIOD and phase != IN_TRADE:
            break

        h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])
        d = pd.Timestamp(bar['date'])

        if phase == WAIT_FILL:
            filled = False
            if direction == 'Long' and l <= range_high:
                entry, target, stop = range_high, range_high + range_val, range_low
                entry_date = d
                filled = True
            elif direction == 'Short' and h >= range_low:
                entry, target, stop = range_low, range_low - range_val, range_high
                entry_date = d
                filled = True

            if filled:
                phase = IN_TRADE
                max_adverse = 0.0
            else:
                if direction == 'Long' and c < range_low:
                    direction = 'Short'
                elif direction == 'Short' and c > range_high:
                    direction = 'Long'

        if phase == IN_TRADE:
            assert direction is not None and entry is not None and target is not None and stop is not None and entry_date is not None
            if direction == 'Long':
                if l < stop:
                    trades.append(ChartTrade(direction, entry, stop, target, stop, stop - entry, 'Loss', entry_date, d, 100.0))
                    phase, direction = WAIT_BREAKOUT, None
                elif h >= target:
                    max_adverse = max(max_adverse, max(0.0, (entry - l) / range_val))
                    trades.append(ChartTrade(direction, entry, target, target, stop, target - entry, 'Win', entry_date, d, round(max_adverse * 100, 2)))
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_adverse = max(max_adverse, max(0.0, (entry - l) / range_val))
                    continue
            else:
                if h > stop:
                    trades.append(ChartTrade(direction, entry, stop, target, stop, entry - stop, 'Loss', entry_date, d, 100.0))
                    phase, direction = WAIT_BREAKOUT, None
                elif l <= target:
                    max_adverse = max(max_adverse, max(0.0, (h - entry) / range_val))
                    trades.append(ChartTrade(direction, entry, target, target, stop, entry - target, 'Win', entry_date, d, round(max_adverse * 100, 2)))
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_adverse = max(max_adverse, max(0.0, (h - entry) / range_val))
                    continue

        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_PERIOD:
            if c > range_high:
                direction = 'Long'
                if l <= range_high:
                    entry, target, stop = range_high, range_high + range_val, range_low
                    entry_date = d
                    phase = IN_TRADE
                    max_adverse = 0.0
                    continue
                phase = WAIT_FILL
            elif c < range_low:
                direction = 'Short'
                if h >= range_low:
                    entry, target, stop = range_low, range_low - range_val, range_high
                    entry_date = d
                    phase = IN_TRADE
                    max_adverse = 0.0
                    continue
                phase = WAIT_FILL

    if phase == IN_TRADE and not trade_bars.empty:
        assert direction is not None and entry is not None and target is not None and stop is not None and entry_date is not None
        last = trade_bars.iloc[-1]
        exit_price = float(last['close'])
        exit_date = pd.Timestamp(last['date'])
        pl = exit_price - entry if direction == 'Long' else entry - exit_price
        trades.append(ChartTrade(direction, entry, exit_price, target, stop, pl, 'Period-Close', entry_date, exit_date, round(max_adverse * 100, 2)))

    return trades


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['year'] = work['date'].dt.year
    work['month'] = work['date'].dt.month
    for year, sub in work.groupby('year', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if not (sub['month'] <= 3).any() or not (sub['month'] > 3).any():
            continue
        yield str(year), sub


def draw_period(
    period: str,
    bars: pd.DataFrame,
    csv_rows: pd.DataFrame,
    out_path: Path,
    point_value: float,
) -> Optional[dict]:
    range_bars = bars[bars['month'] <= 3].copy()
    trade_bars = bars[bars['month'] > 3].copy().reset_index(drop=True)
    if range_bars.empty or trade_bars.empty or csv_rows.empty:
        return None

    range_high = float(csv_rows.iloc[0]['Range_High'])
    range_low = float(csv_rows.iloc[0]['Range_Low'])
    range_val = float(csv_rows.iloc[0]['Range'])
    if range_val <= 0:
        return None

    trades = simulate_period_with_dates(range_high, range_low, range_val, trade_bars)

    fig = plt.figure(figsize=(18, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    width = 0.72
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.7, zorder=3)
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
    ax.axvspan(range_start, range_end, color='#1F4E79', alpha=0.28, zorder=0)
    ax.axhline(range_high, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.10, zorder=0)

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'Period-Close': '#FFB74D'}
    total_pl = sum(t.pl for t in trades)
    pattern = '+'.join(f'{t.direction[0]}{t.result[0]}' for t in trades) if trades else 'No-Op'
    label_offsets = [24, -36, 50, -62]
    for i, tr in enumerate(trades, 1):
        x_e = mdates.date2num(tr.entry_date)
        x_x = mdates.date2num(tr.exit_date)
        ax.scatter(
            [x_e],
            [tr.entry],
            marker='^' if tr.direction == 'Long' else 'v',
            color='#FFC107',
            s=135,
            zorder=10,
            edgecolor='black',
            linewidth=1.2,
        )
        ax.annotate(
            f'#{i} {tr.direction[0]} @ {tr.entry:.1f}',
            xy=(x_e, tr.entry),
            xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color='#FFC107',
            fontsize=8,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
        )
        ax.plot([x_e, x_x], [tr.target, tr.target], color='#76FF03', linewidth=0.9, alpha=0.65, zorder=4)
        ax.plot([x_e, x_x], [tr.stop, tr.stop], color='#FF1744', linewidth=0.9, alpha=0.65, zorder=4)
        exit_color = color_for.get(tr.result, '#FFB74D')
        ax.scatter([x_x], [tr.exit_price], marker='X', color=exit_color, s=135, zorder=10, edgecolor='black', linewidth=1.2)
        ax.annotate(
            f'#{i} {tr.result} {tr.pl:+.0f}pt',
            xy=(x_x, tr.exit_price),
            xytext=(8, -label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=exit_color,
            fontsize=8,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=exit_color, alpha=0.95),
        )

    last_x = xnums[-1] + 2.0
    ax.text(last_x, range_high, f' RH {range_high:.1f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, range_low, f' RL {range_low:.1f}', color='#E0E0E0', fontsize=8, va='center')

    sym = str(csv_rows.iloc[0]['Symbol'])
    range_days = int(csv_rows.iloc[0]['Range_Days'])
    csv_pl = float(csv_rows['Trade_PL'].sum())
    title = (
        f'{period}  YEARLY ORB  ·  {sym}  ·  Jan-Mar / {range_days} range days  ·  '
        f'Range {range_val:.1f}  ·  {pattern}  ·  chart {total_pl:+.1f}pt  ·  csv {csv_pl:+.1f}pt'
    )
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=4), dates.iloc[-1] + pd.Timedelta(days=8))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)

    return {
        'period': period,
        'year': int(period),
        'symbol': sym,
        'range': round(range_val, 2),
        'range_days': range_days,
        'trade_days': int(csv_rows.iloc[0]['Trade_Days']),
        'pattern': pattern,
        'trades': len(trades),
        'net_pts': round(total_pl, 2),
        'net_usd_1_contract': round(total_pl * point_value, 2),
        'csv_net_pts': round(csv_pl, 2),
        'chart': f'{period}/{period}.png',
    }


def write_indexes(out_root: Path, rows: list[dict], market: str, point_value: float) -> None:
    for row in sorted(rows, key=lambda x: x['period']):
        idx = out_root / row['period'] / 'INDEX.md'
        idx.write_text(
            '\n'.join(
                [
                    f'# {row["period"]} yearly ORB chart',
                    '',
                    f'Symbol: {row["symbol"]}  ·  Range days: {row["range_days"]}  ·  Trade days: {row["trade_days"]}',
                    f'Net: {row["net_pts"]:+.2f} pts (${row["net_usd_1_contract"]:+,.0f} / 1 {market} gross)',
                    '',
                    '| Period | Symbol | Range | Pattern | Trades | Chart net pts | CSV net pts | Chart |',
                    '|---|---|---:|---|---:|---:|---:|---|',
                    f'| {row["period"]} | {row["symbol"]} | {row["range"]:.2f} | {row["pattern"]} | {row["trades"]} | {row["net_pts"]:+.2f} | {row["csv_net_pts"]:+.2f} | [{row["period"]}.png]({row["period"]}.png) |',
                    '',
                ]
            ),
            encoding='utf-8',
        )

    total = sum(r['net_pts'] for r in rows)
    csv_total = sum(r['csv_net_pts'] for r in rows)
    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                f'# {market} yearly ORB charts',
                '',
                'Daily-candle annotations for the yearly ORB study. The shaded band is Jan-Mar, which defines the yearly opening range; trades are annotated from Apr-Dec.',
                '',
                f'Periods charted: {len(rows)}  ·  Chart net: {total:+.2f} pts (${total * point_value:+,.0f} / 1 {market} gross)  ·  CSV net: {csv_total:+.2f} pts',
                '',
                '| Year | Symbol | Range Days | Trade Days | Range | Pattern | Trades | Chart net pts | CSV net pts | Folder |',
                '|---:|---|---:|---:|---:|---|---:|---:|---:|---|',
                *[
                    f'| {r["period"]} | {r["symbol"]} | {r["range_days"]} | {r["trade_days"]} | {r["range"]:.2f} | {r["pattern"]} | {r["trades"]} | {r["net_pts"]:+.2f} | {r["csv_net_pts"]:+.2f} | [{r["period"]}/]({r["period"]}/INDEX.md) |'
                    for r in sorted(rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY_CSV)
    ap.add_argument('--yearly-csv', type=Path, default=YEARLY_ORB_CSV)
    ap.add_argument('--out', type=Path, default=OUT_ROOT)
    ap.add_argument('--market', type=str, default='MNQ')
    ap.add_argument('--point-value', type=float, default=2.0)
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    yearly = pd.read_csv(args.yearly_csv)
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]

    rows: list[dict] = []
    for period, bars in period_groups(daily):
        csv_rows = yearly[yearly['Period'].astype(str) == period]
        if csv_rows.empty:
            continue
        out_path = args.out / period / f'{period}.png'
        row = draw_period(period, bars, csv_rows, out_path, args.point_value)
        if row is not None:
            rows.append(row)
            print(f'{row["chart"]} chart={row["net_pts"]:+.2f}pt csv={row["csv_net_pts"]:+.2f}pt')

    write_indexes(args.out, rows, args.market.upper(), args.point_value)
    print(f'Wrote {len(rows)} yearly ORB charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
