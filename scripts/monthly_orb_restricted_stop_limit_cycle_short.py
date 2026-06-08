#!/usr/bin/env python3
"""Short-only monthly ORB restricted stop/limit cycle study.

This is the bearish mirror of ``monthly_orb_restricted_stop_limit_cycle.py``.
It uses the same state machine by inverting OHLC prices, running the long
engine, then mapping prices and labels back to real short-side levels.

Short-side interpretation:

- Monthly OR = first three daily rows of the calendar month.
- Primary order = sell stop at the OR low after the OR forms.
- If the stop fills but the same daily candle closes more than 25% back inside
  the OR, close all 3 contracts at that close and re-arm the sell stop.
- Confirmed breakdown packages use 3 contracts: 1 off halfway to TP1, 1 off at
  TP1, 1 runner at TP2.
- If a confirmed breakdown package closes more than 25% back inside the OR
  before TP1, close all at the daily close and arm a top-boundary limit.
- Bottom-boundary refills close before TP1 on any daily close at or above the
  OR low.
- Top-boundary limit enters at the OR high, exits only on a daily close above
  ``OR high + 0.25 * range``, takes 1 off at the OR low, and takes the other 2
  off at TP1.
"""
from __future__ import annotations

import argparse
import math
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import monthly_orb_restricted_stop_limit_cycle as base


KIND_MAP = {
    'Stop-Breakout': 'Stop-Breakdown',
    'Top-Refill': 'Bottom-Refill',
    'Bottom-Limit': 'Top-Limit',
}

SOURCE_MAP = KIND_MAP.copy()

EVENT_MAP = {
    'fill_stop': 'fill_sell_stop',
    'fill_stop_from_bottom_state': 'fill_sell_stop_from_top_state',
    'fill_bottom_limit': 'fill_top_limit',
    'fill_top_refill': 'fill_bottom_refill',
    'arm_top_refill': 'arm_bottom_refill',
}

REASON_REPLACEMENTS = {
    'False-Breakout-Close-25pct-Inside': 'False-Breakdown-Close-25pct-Inside',
    'Bottom-Limit-Daily-Close-SL': 'Top-Limit-Daily-Close-SL',
    'Top-Boundary': 'Bottom-Boundary',
    'Daily-Close-At-Or-Below-Range-High-Before-TP1': 'Daily-Close-At-Or-Above-Range-Low-Before-TP1',
}


def invert_daily(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    open_px = pd.to_numeric(daily['open'])
    high_px = pd.to_numeric(daily['high'])
    low_px = pd.to_numeric(daily['low'])
    close_px = pd.to_numeric(daily['close'])
    out['open'] = -open_px
    out['high'] = -low_px
    out['low'] = -high_px
    out['close'] = -close_px
    return out


def map_reason(reason: object) -> object:
    if pd.isna(reason):
        return reason
    text = str(reason)
    for old, new in REASON_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def map_unit_exits(value: object) -> object:
    if pd.isna(value) or not str(value):
        return value
    mapped: list[str] = []
    for item in str(value).split(';'):
        parts = item.split(':')
        if len(parts) != 5:
            mapped.append(item)
            continue
        unit, date, price, reason, pl = parts
        try:
            mapped_price = -float(price)
            price_text = f'{mapped_price:.2f}'
        except ValueError:
            price_text = price
        mapped.append(':'.join([unit, date, price_text, str(map_reason(reason)), pl]))
    return ';'.join(mapped)


def map_short_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    orig_high = -pd.to_numeric(out['Range_Low'], errors='coerce')
    orig_low = -pd.to_numeric(out['Range_High'], errors='coerce')
    out['Range_High'] = orig_high
    out['Range_Low'] = orig_low

    for col in ['Entry_Price', 'TP50', 'TP1', 'TP2', 'Stop', 'Exit_Price']:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce').map(lambda x: -x if pd.notna(x) else x)

    out['Entry_Kind'] = out['Entry_Kind'].map(lambda x: KIND_MAP.get(str(x), x))
    out['Exit_Reason'] = out['Exit_Reason'].map(map_reason)
    out['Unit_Exits'] = out['Unit_Exits'].map(map_unit_exits)
    if 'Cumulative_PL' in out.columns:
        out['Cumulative_PL'] = pd.to_numeric(out['Trade_PL'], errors='coerce').fillna(0.0).cumsum()
    return out


def map_short_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    out = events.copy()
    for col in ['Price', 'Close']:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce').map(lambda x: -x if pd.notna(x) else x)
    if 'Event' in out.columns:
        out['Event'] = out['Event'].map(lambda x: EVENT_MAP.get(str(x), x))
    if 'Source' in out.columns:
        out['Source'] = out['Source'].map(lambda x: SOURCE_MAP.get(str(x), x) if pd.notna(x) else x)
    return out


def _kind_code(kind: str) -> str:
    return {
        'Stop-Breakdown': 'SD',
        'Bottom-Refill': 'BR',
        'Top-Limit': 'TL',
    }.get(kind, kind[:2].upper())


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xnums = mdates.date2num(pd.to_datetime(bars['date']).dt.to_pydatetime())
    width = 0.62
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.75, alpha=0.88, zorder=2)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.86,
                zorder=3,
            )
        )


def chart_trades(daily: pd.DataFrame, trades: pd.DataFrame, out_root: Path, label: str, point_value: float) -> None:
    if trades.empty:
        return
    chart_root = out_root / 'restricted_stop_limit_cycle_short'
    if chart_root.exists():
        shutil.rmtree(chart_root)
    chart_root.mkdir(parents=True, exist_ok=True)

    work = daily.copy()
    work['Period'] = pd.to_datetime(work['date']).dt.to_period('M').astype(str)
    index_lines = [f'# {label} restricted stop-limit cycle short charts', '']
    year_rows: dict[int, list[dict]] = {}

    for period, period_trades in trades.groupby('Period', sort=True):
        period_trades = period_trades.sort_values(['Entry_Date', 'Exit_Date', 'Entry_Kind']).reset_index(drop=True)
        bars = work[work['Period'] == period].copy().reset_index(drop=True)
        if bars.empty:
            continue
        year = int(str(period).split('-')[0])
        year_dir = chart_root / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        fig = plt.figure(figsize=(14, 7), facecolor='#111827')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0D1B2A')
        draw_candles(ax, bars)

        dates = pd.to_datetime(bars['date'])
        rb = bars.iloc[:3]
        range_start = pd.Timestamp(rb.iloc[0]['date'])
        range_end = pd.Timestamp(rb.iloc[-1]['date']) + pd.Timedelta(days=1)
        rh = float(period_trades.iloc[0]['Range_High'])
        rl = float(period_trades.iloc[0]['Range_Low'])
        rv = rh - rl
        tp50 = rl - 0.5 * rv
        tp1 = rl - rv
        tp2 = rl - 2.0 * rv
        breakdown_stop = rl + 0.25 * rv
        top_limit_stop = rh + 0.25 * rv

        ax.axvspan(range_start, range_end, color='#1F4E79', alpha=0.30, zorder=0)
        ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(breakdown_stop, color='#FFB74D', linestyle=':', linewidth=0.8, alpha=0.60, zorder=2)
        ax.axhline(tp50, color='#FFD54F', linestyle=':', linewidth=0.8, alpha=0.75, zorder=2)
        ax.axhline(tp1, color='#76FF03', linestyle='--', linewidth=0.9, alpha=0.70, zorder=2)
        ax.axhline(tp2, color='#64DD17', linestyle='--', linewidth=0.8, alpha=0.45, zorder=2)
        ax.axhline(top_limit_stop, color='#FF8A65', linestyle=':', linewidth=0.8, alpha=0.65, zorder=2)

        total_pl = float(period_trades['Trade_PL'].sum())
        pattern_parts: list[str] = []
        label_offsets = [24, -36, 48, -60, 72, -84]
        marker_for = {'Stop-Breakdown': 'v', 'Bottom-Refill': 'o', 'Top-Limit': 'D'}
        color_for = {'Stop-Breakdown': '#FF5252', 'Bottom-Refill': '#40C4FF', 'Top-Limit': '#FFC107'}
        result_color = {'Win': '#76FF03', 'Loss': '#FF1744', 'Scratch': '#FFB74D'}

        for i, (_, tr) in enumerate(period_trades.iterrows(), 1):
            entry_x = pd.Timestamp(tr['Entry_Date'])
            exit_x = pd.Timestamp(tr['Exit_Date'])
            entry_y = float(tr['Entry_Price'])
            exit_y = float(tr['Exit_Price'])
            kind = str(tr['Entry_Kind'])
            code = _kind_code(kind)
            result = str(tr['Result'])
            pl = float(tr['Trade_PL'])
            pattern_parts.append(f'{code}-{result[0]}')

            ax.scatter(
                [entry_x],
                [entry_y],
                marker=marker_for.get(kind, 'v'),
                color=color_for.get(kind, '#FF5252'),
                s=105,
                zorder=10,
                edgecolor='black',
                linewidth=1.0,
            )
            ax.annotate(
                f'#{i} {code} @ {entry_y:.0f}',
                xy=(entry_x, entry_y),
                xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=color_for.get(kind, '#FF5252'),
                fontsize=7,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=color_for.get(kind, '#FF5252'), alpha=0.94),
            )
            ax.scatter(
                [exit_x],
                [exit_y],
                marker='X',
                color=result_color.get(result, '#FFB74D'),
                s=110,
                zorder=10,
                edgecolor='black',
                linewidth=1.0,
            )
            ax.annotate(
                f'#{i} {result[0]} {pl:+.0f}pt',
                xy=(exit_x, exit_y),
                xytext=(8, -label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=result_color.get(result, '#FFB74D'),
                fontsize=7,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=result_color.get(result, '#FFB74D'), alpha=0.94),
            )

        last_x = mdates.date2num(dates.iloc[-1]) + 0.35
        ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=7, va='center')
        ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=7, va='center')
        ax.text(last_x, breakdown_stop, f' 25% close {breakdown_stop:.1f}', color='#FFB74D', fontsize=7, va='center')
        ax.text(last_x, tp1, f' TP1 {tp1:.1f}', color='#76FF03', fontsize=7, va='center')
        ax.text(last_x, tp2, f' TP2 {tp2:.1f}', color='#64DD17', fontsize=7, va='center')

        sym = str(bars.iloc[0].get('symbol', ''))
        pattern = '+'.join(pattern_parts)
        ax.set_title(
            f'{period}  {label} restricted stop-limit cycle SHORT  ·  {sym}  ·  '
            f'Range {rv:.1f}  ·  {pattern}  ·  {total_pl:+.1f}pt (${total_pl * point_value:+.0f})',
            color='white',
            fontsize=9,
            fontweight='bold',
            loc='left',
            pad=8,
        )
        ax.tick_params(colors='#9FB3C8', labelsize=7)
        for spine in ax.spines.values():
            spine.set_color('#3A506B')
        ax.grid(True, alpha=0.15, color='#9FB3C8')
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=2))
        fig.autofmt_xdate()
        fig.tight_layout()
        path = year_dir / f'{period}.png'
        fig.savefig(path, dpi=140)
        plt.close(fig)

        year_rows.setdefault(year, []).append(
            {
                'Period': period,
                'Symbol': sym,
                'Range': rv,
                'Pattern': pattern,
                'Packages': len(period_trades),
                'Net': total_pl,
                'Chart': f'{period}.png',
            }
        )

    for year in sorted(year_rows):
        rows = year_rows[year]
        year_net = sum(r['Net'] for r in rows)
        year_dir = chart_root / str(year)
        lines = [
            f'# {year} {label} restricted stop-limit cycle short charts',
            '',
            f"Periods: {len(rows)}  ·  Net: {year_net:+.2f} pts (${year_net * point_value:+,.0f})",
            '',
            '| Period | Symbol | Range | Pattern | Packages | Net pts | Chart |',
            '|---|---|---:|---|---:|---:|---|',
        ]
        for r in rows:
            lines.append(
                f"| {r['Period']} | {r['Symbol']} | {r['Range']:.2f} | {r['Pattern']} | "
                f"{r['Packages']} | {r['Net']:+.2f} | [{r['Chart']}]({r['Chart']}) |"
            )
        (year_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n')
        index_lines.append(f"- [{year}/]({year}/INDEX.md) — {len(rows)} periods, {year_net:+.1f} pts")

    (chart_root / 'INDEX.md').write_text('\n'.join(index_lines) + '\n')


def write_report(market: str, label: str, root: Path, trades: pd.DataFrame, events: pd.DataFrame, point_value: float) -> Path:
    case_root = root / 'case_studies' / 'monthly_orb'
    case_root.mkdir(parents=True, exist_ok=True)
    report = case_root / 'MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md'
    s = base.stats(trades, point_value)
    lines = [
        f'# {label} Monthly ORB Restricted Stop-Limit Cycle Short',
        '',
        'Rules modeled:',
        '',
        '- Short only. This is a separate bearish mirror of the long restricted stop-limit cycle.',
        '- Monthly OR = first 3 daily rows of each calendar month.',
        '- Primary order = sell stop at the OR low after the OR forms.',
        '- If the stop fills but the same daily candle closes more than 25% back inside the OR, close all 3 contracts at that close and re-arm the sell stop.',
        '- Confirmed breakdown packages use 3 contracts: 1 off halfway to TP1, 1 off at TP1, 1 runner at TP2.',
        '- If a confirmed breakdown package closes more than 25% back inside the OR before TP1, close all at the daily close and arm a top-boundary limit.',
        '- Bottom-boundary refill packages close before TP1 on any daily close at or above the OR low.',
        '- After any TP1 success, arm a 2-contract bottom-boundary refill at the OR low, even if an earlier runner is still open.',
        '- Bottom-boundary refills take 1 off halfway to TP1 and 1 off at TP1; they do not leave a runner.',
        '- Top-boundary limit enters at the OR high, exits only on a daily close above `OR high + 0.25 * range`, takes 1 off at the OR low, and takes the other 2 off at TP1.',
        '- After a failed breakdown before TP1, the top-boundary limit becomes available, but a fresh sell-stop breakdown can still fire before that top limit fills.',
        '',
        'Daily OHLC caveat: this cannot prove intraday ordering. This short study inherits the same daily data limitations as the long version.',
        '',
        f'Dollar figures use {label} point value of ${point_value:g}/point per contract.',
        '',
        '## Summary',
        '',
        '| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|',
        f"| {s['trades']} | {base.fmt_num(s['net_pts'])} | {base.fmt_money(s['net_usd'])} | {base.fmt_money(s['dd_usd'])} | {base.fmt_pct(s['win_rate'])} | {base.fmt_num(s['pf'], 2)} | {base.fmt_num(s['avg_mae'])} | {base.fmt_num(s['max_mae'])} |",
        '',
        '## Entry Type Split',
        '',
    ]
    if trades.empty:
        lines.append('No trades.')
    else:
        split = trades.groupby('Entry_Kind').apply(lambda x: pd.Series(base.stats(x, point_value))).reset_index()
        lines.extend(['| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |', '|---|---:|---:|---:|---:|---:|---:|'])
        for _, row in split.iterrows():
            lines.append(
                f"| {row['Entry_Kind']} | {int(row['trades'])} | {base.fmt_num(row['net_pts'])} | "
                f"{base.fmt_money(row['net_usd'])} | {base.fmt_money(row['dd_usd'])} | {base.fmt_pct(row['win_rate'])} | {base.fmt_num(row['pf'], 2)} |"
            )
    lines.extend(['', '## Exit Mix', ''])
    if trades.empty:
        lines.append('No trades.')
    else:
        for reason, count in trades['Exit_Reason'].value_counts().items():
            lines.append(f'- {reason}: **{count}**')
    lines.extend(['', '## Yearly Split', ''])
    if trades.empty:
        lines.append('No trades.')
    else:
        work = trades.copy()
        work['Year'] = pd.to_datetime(work['Entry_Date']).dt.year
        lines.extend(['| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |', '|---:|---:|---:|---:|---:|---:|---:|'])
        for year, row in work.groupby('Year').agg(
            trades=('Trade_PL', 'size'),
            net=('Trade_PL', 'sum'),
            wins=('Trade_PL', lambda x: int((x > 0).sum())),
            losses=('Trade_PL', lambda x: int((x < 0).sum())),
            avg_mae=('MAE_Price_Pts', 'mean'),
            max_mae=('MAE_Price_Pts', 'max'),
        ).iterrows():
            lines.append(f"| {year} | {int(row['trades'])} | {row['net']:,.1f} | {int(row['wins'])} | {int(row['losses'])} | {row['avg_mae']:.1f} | {row['max_mae']:.1f} |")
    lines.extend(
        [
            '',
            '## Outputs',
            '',
            f'- `{market}/{market}_monthly_orb_restricted_stop_limit_cycle_short.csv`',
            f'- `{market}/{market}_monthly_orb_restricted_stop_limit_cycle_short_events.csv`',
            '- Charts: `case_studies/monthly_orb/restricted_stop_limit_cycle_short/INDEX.md`',
        ]
    )
    report.write_text('\n'.join(lines) + '\n')
    return report


def run_market(market: str, charts: bool) -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    cfg = base.MARKETS[market]
    daily = base.load_daily(cfg['daily'])
    inverted = invert_daily(daily)
    raw_trades, raw_events = base.simulate(inverted, market, allow_short=False)
    trades = map_short_trades(raw_trades)
    events = map_short_events(raw_events)

    out = cfg['root'] / f'{market}_monthly_orb_restricted_stop_limit_cycle_short.csv'
    events_out = cfg['root'] / f'{market}_monthly_orb_restricted_stop_limit_cycle_short_events.csv'
    trades.to_csv(out, index=False)
    events.to_csv(events_out, index=False)

    case_root = cfg['root'] / 'case_studies' / 'monthly_orb'
    if charts and not trades.empty:
        chart_trades(daily, trades, case_root, cfg['label'], cfg['point_value'])
    report = write_report(market, cfg['label'], cfg['root'], trades, events, cfg['point_value'])
    return trades, events, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--charts', action='store_true')
    args = ap.parse_args()

    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        trades, events, report = run_market(market, args.charts)
        print(f'Wrote {market} short: {len(trades)} packages, {len(events)} events, report {report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
