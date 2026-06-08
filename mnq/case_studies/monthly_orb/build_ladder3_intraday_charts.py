#!/usr/bin/env python3
"""Charts for intraday-validated monthly ORB 3-contract ladder variants."""
from __future__ import annotations

from pathlib import Path

import argparse
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


POTIONS = Path('/home/tester/hsm/potions')
MNQ_ROOT = POTIONS / 'mnq'
DEFAULT_TRADES = MNQ_ROOT / 'mnq_monthly_orb_inside_source_stop_ladder3_intraday.csv'
DEFAULT_OUT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'inside_source_stop_ladder3_unrestricted_intraday'


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = values.astype(float).cumsum()
    return float((eq - eq.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def fmt_money(value: float) -> str:
    return f'${value:,.2f}'


def fmt_num(value: float) -> str:
    if math.isnan(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.2f}'


def fmt_pct(value: float) -> str:
    return 'n/a' if math.isnan(value) else f'{value:.2%}'


def summarize(trades: pd.DataFrame) -> dict:
    pnl = trades['Trade_PL'].astype(float) if not trades.empty else pd.Series(dtype=float)
    unit_reason_cols = ['Unit1_Exit_Reason', 'Unit2_Exit_Reason', 'Unit3_Exit_Reason']
    reasons = trades[unit_reason_cols].astype(str) if not trades.empty else pd.DataFrame(columns=unit_reason_cols)
    return {
        'trades': int(len(trades)),
        'periods': int(trades['Period'].nunique()) if not trades.empty else 0,
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * 2.0),
        'dd_pts': max_dd(pnl),
        'dd_usd': max_dd(pnl) * 2.0,
        'win_rate': float((pnl > 0).mean()) if len(pnl) else math.nan,
        'pf': profit_factor(pnl),
        'target_1r': int(reasons.apply(lambda row: row.str.startswith('Target-1R').any(), axis=1).sum()) if not reasons.empty else 0,
        'target_2r': int(reasons.apply(lambda row: row.str.startswith('Target-2R').any(), axis=1).sum()) if not reasons.empty else 0,
        'target_3r': int(reasons.apply(lambda row: row.str.startswith('Target-3R').any(), axis=1).sum()) if not reasons.empty else 0,
        'full_stops': int((trades['Result'] == 'Full-Stop').sum()) if not trades.empty else 0,
        'initial_stops': int((trades['Result'] == 'Initial-Stop').sum()) if not trades.empty else 0,
        'boundary_stops': int((trades['Result'] == 'Boundary-Stop').sum()) if not trades.empty else 0,
        'boundary_closes': int(reasons.apply(lambda row: (row == 'Boundary-Close').any(), axis=1).sum()) if not reasons.empty else 0,
        'sl_half_closes': int(reasons.apply(lambda row: (row == 'SL-Half-Close').any(), axis=1).sum()) if not reasons.empty else 0,
        'period_closes': int((trades['Result'] == 'Period-Close').sum()) if not trades.empty else 0,
    }


def date_value(bars: pd.DataFrame, d, col: str) -> float | None:
    if pd.isna(d):
        return None
    hit = bars[pd.to_datetime(bars['date']).dt.date == pd.Timestamp(d).date()]
    if hit.empty:
        return None
    return float(hit.iloc[0][col])


def ts_num(value) -> float:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return mdates.date2num(ts)


def ts_value(value):
    ts = pd.Timestamp(value)
    return ts.tz_convert(None) if ts.tzinfo is not None else ts


def exit_style(reason: str) -> tuple[str, str]:
    if reason.startswith('Target-1R'):
        return '#B2FF59', 'o'
    if reason.startswith('Target-2R'):
        return '#76FF03', 's'
    if reason.startswith('Target-3R'):
        return '#00E676', '*'
    if reason == 'Boundary-Stop':
        return '#FFB74D', 'X'
    if reason == 'Boundary-Close':
        return '#FFB74D', 'o'
    if reason == 'SL-Half-Close':
        return '#FFB74D', 'o'
    if reason == 'Initial-Stop':
        return '#FF1744', 'X'
    if reason == 'Period-Close':
        return '#90CAF9', 'X'
    if reason == 'Range-Close':
        return '#FFB74D', 'X'
    return '#E0E0E0', 'X'


def draw_period(period: str, bars: pd.DataFrame, trades: pd.DataFrame, out_path: Path, chart_title: str) -> dict | None:
    chart_trades = trades[trades['Period'].astype(str) == period].copy()
    if chart_trades.empty:
        return None

    range_bars = bars.iloc[:3].copy()
    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low

    fig = plt.figure(figsize=(15, 8), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    width = 0.58
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.8, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )

    range_start = pd.Timestamp(range_bars.iloc[0]['date'])
    range_end = pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1)
    ax.axvspan(range_start, range_end, color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.10, zorder=0)
    ax.axhline(range_high, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)

    label_offsets = [24, -38, 52, -66]
    for i, (_, tr) in enumerate(chart_trades.iterrows(), 1):
        direction = str(tr['Trade_Direction'])
        entry = float(tr['Entry_Price'])
        initial_stop = float(tr['Initial_Stop_Price'])
        boundary_stop = float(tr['Boundary_Stop_Price'])
        t1 = float(tr['Target_1R_Price'])
        t2 = float(tr['Target_2R_Price'])
        t3 = float(tr['Target_3R_Price'])
        breakout_date = pd.Timestamp(tr['Breakout_Date'])
        source_date = pd.Timestamp(tr['Entry_Source_Date'])
        source_start = pd.Timestamp(tr['Entry_Source_Start'])
        source_end = pd.Timestamp(tr['Entry_Source_End'])
        source_open = float(tr['Entry_Source_Open'])
        entry_time = ts_value(tr['Entry_Time'])
        final_time = ts_value(tr['Exit_Time'])
        pl = float(tr['Trade_PL'])
        result = str(tr['Result'])

        ax.axvspan(source_start - pd.Timedelta(hours=12), source_end + pd.Timedelta(hours=12), color='#AB47BC', alpha=0.16, zorder=1)
        ax.scatter([mdates.date2num(source_date)], [source_open], marker='D', color='#CE93D8', s=92, zorder=9, edgecolor='black', linewidth=1.0)
        src_extreme = float(tr['Entry_Source_Run_Low']) if direction == 'Long' else float(tr['Entry_Source_Run_High'])
        ax.plot(
            [mdates.date2num(source_start) - 0.35, mdates.date2num(source_end) + 0.35],
            [src_extreme, src_extreme],
            color='#CE93D8',
            linewidth=1.0,
            alpha=0.9,
            zorder=8,
        )

        breakout_close = date_value(bars, breakout_date, 'close')
        if breakout_close is not None:
            ax.scatter([mdates.date2num(breakout_date)], [breakout_close], marker='^' if direction == 'Long' else 'v', color='#4FC3F7', s=105, zorder=9, edgecolor='black', linewidth=1.0)

        ax.scatter([mdates.date2num(entry_time)], [entry], marker='^' if direction == 'Long' else 'v', color='#FFC107', s=140, zorder=10, edgecolor='black', linewidth=1.2)
        ax.plot([entry_time, final_time], [initial_stop, initial_stop], color='#FF1744', linewidth=0.9, alpha=0.70, zorder=4)
        ax.plot([entry_time, final_time], [boundary_stop, boundary_stop], color='#FFB74D', linestyle='--', linewidth=0.95, alpha=0.75, zorder=4)
        ax.plot([entry_time, final_time], [t1, t1], color='#B2FF59', linewidth=0.85, alpha=0.55, zorder=4)
        ax.plot([entry_time, final_time], [t2, t2], color='#76FF03', linewidth=0.9, alpha=0.60, zorder=4)
        ax.plot([entry_time, final_time], [t3, t3], color='#00E676', linewidth=1.0, alpha=0.65, zorder=4)

        exits = [
            ('U1', tr['Unit1_Exit_Time'], float(tr['Unit1_Exit_Price']), str(tr['Unit1_Exit_Reason'])),
            ('U2', tr['Unit2_Exit_Time'], float(tr['Unit2_Exit_Price']), str(tr['Unit2_Exit_Reason'])),
            ('U3', tr['Unit3_Exit_Time'], float(tr['Unit3_Exit_Price']), str(tr['Unit3_Exit_Reason'])),
        ]
        for unit, ts, px, reason in exits:
            color, marker = exit_style(reason)
            ax.scatter([ts_num(ts)], [px], marker=marker, color=color, s=125 if unit != 'U3' else 170, zorder=10, edgecolor='black', linewidth=1.1)

        result_color = '#76FF03' if pl > 0 else '#FF1744'
        if result == 'Boundary-Stop':
            result_color = '#FFB74D'
        elif result == 'Period-Close':
            result_color = '#90CAF9'
        ax.annotate(
            f'#{i} {direction[0]} {result} {pl:+.0f}pt',
            xy=(ts_num(tr['Exit_Time']), float(tr['Exit_Price'])),
            xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=result_color,
            fontsize=8,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=result_color, alpha=0.95),
        )

    last_x = xnums[-1] + 0.4
    ax.text(last_x, range_high, f' RH {range_high:.1f}', color='#E0E0E0', fontsize=7, va='center')
    ax.text(last_x, range_low, f' RL {range_low:.1f}', color='#E0E0E0', fontsize=7, va='center')
    sym = str(bars.iloc[0]['symbol'])
    total_pl = float(chart_trades['Trade_PL'].sum())
    title = (
        f'{period}  {chart_title}  ·  {sym}  ·  '
        f'Range {range_val:.1f}  ·  {len(chart_trades)} trade(s)  ·  {total_pl:+.1f} ladder-pts (${total_pl * 2:+.0f})'
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
        'trades': int(len(chart_trades)),
        'net_pts': round(total_pl, 2),
        'chart': f'{period[:4]}/{period}.png',
    }


def write_index(out_root: Path, rows: list[dict], stats: dict, title: str, initial_stop_label: str, legend_note: str) -> None:
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        by_year.setdefault(row['year'], []).append(row)

    for year, yr_rows in sorted(by_year.items()):
        idx = out_root / str(year) / 'INDEX.md'
        idx.write_text(
            '\n'.join([
                f'# {year} {title}',
                '',
                '| Period | Symbol | Trades | Net ladder pts | Chart |',
                '|---|---|---:|---:|---|',
                *[
                    f"| {r['period']} | {r['symbol']} | {r['trades']} | {r['net_pts']:+.2f} | [{r['period']}.png]({r['period']}.png) |"
                    for r in sorted(yr_rows, key=lambda x: x['period'])
                ],
                '',
            ]),
            encoding='utf-8',
        )

    out_root.joinpath('INDEX.md').write_text(
        '\n'.join([
            f'# MNQ {title}',
            '',
            f"Trades: {stats['trades']}  ·  Periods: {stats['periods']}  ·  Net: {fmt_money(stats['net_usd'])}  ·  Max DD: {fmt_money(stats['dd_usd'])}  ·  WR: {fmt_pct(stats['win_rate'])}  ·  PF: {fmt_num(stats['pf'])}",
            '',
            f"1R hits: {stats['target_1r']}  ·  2R hits: {stats['target_2r']}  ·  3R hits: {stats['target_3r']}  ·  Full stops: {stats['full_stops']}  ·  Boundary stops: {stats['boundary_stops']}  ·  Boundary closes: {stats['boundary_closes']}  ·  SL-half closes: {stats['sl_half_closes']}  ·  Period closes: {stats['period_closes']}",
            '',
            legend_note,
            '',
            '| Period | Symbol | Trades | Net ladder pts | Chart |',
            '|---|---|---:|---:|---|',
            *[
                f"| {r['period']} | {r['symbol']} | {r['trades']} | {r['net_pts']:+.2f} | [{r['chart']}]({r['chart']}) |"
                for r in sorted(rows, key=lambda x: x['period'])
            ],
            '',
        ]),
        encoding='utf-8',
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--trades', type=Path, default=DEFAULT_TRADES)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--title', default='Inside Source-Stop Unrestricted Ladder 1R/2R/3R Intraday Charts')
    ap.add_argument('--chart-title', default='INTRADAY UNRESTRICTED LADDER 1R/2R/3R')
    ap.add_argument('--initial-stop-label', default='initial source stop')
    ap.add_argument(
        '--legend-note',
        default=None,
        help='Optional custom legend note for the chart index.',
    )
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    trades = pd.read_csv(args.trades)
    trade_rows = trades[trades['Trade_Direction'] != 'No-Op'].copy()
    stats = summarize(trade_rows)

    chart_rows = []
    for period, bars in period_groups(daily):
        out_path = args.out / period[:4] / f'{period}.png'
        row = draw_period(period, bars, trade_rows, out_path, args.chart_title)
        if row:
            chart_rows.append(row)
            print(f'{row["chart"]} {row["net_pts"]:+.2f} ladder-pts')

    args.out.mkdir(parents=True, exist_ok=True)
    legend_note = args.legend_note or (
        f'Purple diamond/region = selected inside opposite candle run. Blue triangle = breakout close. '
        f'Gold triangle = 1-minute limit fill. Green circle/square/star = 1R/2R/3R exits. '
        f'Orange dashed line/X = monthly boundary stop. Red line/X = {args.initial_stop_label}.'
    )
    write_index(args.out, chart_rows, stats, args.title, args.initial_stop_label, legend_note)
    print(f'Wrote {len(chart_rows)} charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
