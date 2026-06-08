#!/usr/bin/env python3
"""MNQ yearly ORB charts with previous-month retracement levels.

This is a visual sidecar for the current yearly ORB scaleout3 / inside-range
swing / range-close candidate. It keeps the yearly ORB trade annotations and
adds one horizontal segment per calendar month:

- If the previous monthly candle closed green, the level is a retracement
  down from that previous month's high.
- If the previous monthly candle closed red, the level is a retracement up
  from that previous month's low.

That makes the level directional instead of drawing both fibs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from yearly_orb_swing_stop_scaleout3 import plot_weekly_supertrend, simulate_year  # noqa: E402


MNQ = ROOT / 'mnq'
DAILY = MNQ / 'mnq_daily.csv'
BASE_CSV = MNQ / 'mnq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv'
BASE_CHART_DIR = MNQ / 'case_studies' / 'yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close'
OUT_DIR = BASE_CHART_DIR / 'monthly_retracement_68'

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'
RANGE_BLUE = '#1F4E79'
ENTRY_YELLOW = '#FFC107'
RET_BULL = '#FFD54F'
RET_BEAR = '#B388FF'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    df['ym'] = df['date'].dt.to_period('M')
    return df


def monthly_ohlc(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for period, sub in daily.groupby('ym', sort=True):
        sub = sub.sort_values('date')
        rows.append(
            {
                'ym': period,
                'month': str(period),
                'start': pd.Timestamp(sub['date'].iloc[0]),
                'end': pd.Timestamp(sub['date'].iloc[-1]),
                'open': float(sub['open'].iloc[0]),
                'high': float(sub['high'].max()),
                'low': float(sub['low'].min()),
                'close': float(sub['close'].iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def prior_month_retracement_levels(daily: pd.DataFrame, retracement: float) -> pd.DataFrame:
    monthly = monthly_ohlc(daily)
    by_period = {row['ym']: row for _, row in monthly.iterrows()}
    rows: list[dict] = []
    for _, current in monthly.iterrows():
        prev_period = current['ym'] - 1
        prev = by_period.get(prev_period)
        if prev is None:
            continue
        prev_open = float(prev['open'])
        prev_close = float(prev['close'])
        prev_high = float(prev['high'])
        prev_low = float(prev['low'])
        rng = prev_high - prev_low
        if rng <= 0:
            continue
        prev_direction = 'bullish' if prev_close >= prev_open else 'bearish'
        if prev_direction == 'bullish':
            level = prev_high - retracement * rng
            method = f'high_minus_{int(round(retracement * 100))}pct_range'
        else:
            level = prev_low + retracement * rng
            method = f'low_plus_{int(round(retracement * 100))}pct_range'
        month_bars = daily[daily['ym'].eq(current['ym'])]
        touched = bool(((month_bars['low'].astype(float) <= level) & (month_bars['high'].astype(float) >= level)).any())
        first_touch = ''
        if touched:
            touch_row = month_bars[(month_bars['low'].astype(float) <= level) & (month_bars['high'].astype(float) >= level)].iloc[0]
            first_touch = pd.Timestamp(touch_row['date']).date().isoformat()
        rows.append(
            {
                'year': int(current['ym'].year),
                'month_num': int(current['ym'].month),
                'month': str(current['ym']),
                'month_start': pd.Timestamp(current['start']).date().isoformat(),
                'month_end': pd.Timestamp(current['end']).date().isoformat(),
                'prev_month': str(prev_period),
                'prev_open': round(prev_open, 4),
                'prev_high': round(prev_high, 4),
                'prev_low': round(prev_low, 4),
                'prev_close': round(prev_close, 4),
                'prev_direction': prev_direction,
                'method': method,
                'retracement': retracement,
                'level': round(level, 4),
                'touched': touched,
                'first_touch_date': first_touch,
            }
        )
    return pd.DataFrame(rows)


def add_weekly_supertrend(daily: pd.DataFrame, atr_len: int, atr_mult: float) -> pd.DataFrame:
    if atr_len <= 0:
        return daily
    from yearly_orb_delivery_research_charts import calculate_weekly_atr_trailing_stop_on_daily

    st_frame = calculate_weekly_atr_trailing_stop_on_daily(
        daily[['date', 'open', 'high', 'low', 'close']].copy(),
        atr_len,
        atr_mult,
    )
    out = daily.copy()
    out['wk_stop'] = st_frame['atr_stop'].values
    out['wk_trend'] = st_frame['atr_trend'].values
    return out


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    width = 0.72
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(x, l, h, color=color, linewidth=0.7, zorder=3)
        body_low = min(o, c)
        body_high = max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_low),
                width,
                max(body_high - body_low, 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.95,
                zorder=3,
            )
        )


def draw_retracement_segments(ax: plt.Axes, year_bars: pd.DataFrame, levels: pd.DataFrame, retracement: float) -> None:
    if levels.empty:
        return
    y_min = float(year_bars['low'].min())
    y_max = float(year_bars['high'].max())
    label_offset = max((y_max - y_min) * 0.012, 1.0)
    for _, row in levels.iterrows():
        start = pd.Timestamp(row['month_start'])
        end = pd.Timestamp(row['month_end']) + pd.Timedelta(days=1)
        level = float(row['level'])
        color = RET_BULL if row['prev_direction'] == 'bullish' else RET_BEAR
        alpha = 0.92 if bool(row['touched']) else 0.55
        ax.hlines(
            level,
            mdates.date2num(start),
            mdates.date2num(end),
            colors=color,
            linestyles='-',
            linewidth=1.2,
            alpha=alpha,
            zorder=5,
        )
        mid = start + (end - start) / 2
        label = f"{pd.Timestamp(start).strftime('%b')} prev{retracement:.0%} {level:,.0f}"
        if bool(row['touched']):
            label += ' *'
        ax.text(
            mdates.date2num(mid),
            level + label_offset,
            label,
            color=color,
            fontsize=6.5,
            ha='center',
            va='bottom',
            alpha=0.95,
            zorder=8,
        )


def draw_trades(ax: plt.Axes, trades: list, point_value: float) -> tuple[float, str]:
    exit_colors = {
        'TP25': '#64FFDA',
        'TP': '#76FF03',
        'BE-Stop': '#B0BEC5',
        'Swing-Stop': '#FF1744',
        'Range-Close': '#FFB74D',
        'Period-Close': '#BA68C8',
    }
    total_pl = sum(trade.net_points for trade in trades)
    pattern = '+'.join(f'{trade.direction[0]}{trade.result[0]}' for trade in trades) if trades else 'No-Op'
    label_offsets = [18, -26, 34, -42, 50, -58, 66, -74]
    for i, trade in enumerate(trades, 1):
        x_entry = mdates.date2num(trade.entry_date)
        x_stop_source = mdates.date2num(trade.stop_source_date)
        ax.scatter([x_stop_source], [trade.stop_source_price], marker='o', color='#64B5F6', s=46, zorder=9, edgecolor='black', linewidth=0.7)
        ax.scatter(
            [x_entry],
            [trade.entry],
            marker='^' if trade.direction == 'Long' else 'v',
            color=ENTRY_YELLOW,
            s=92,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )
        last_exit_date = max((ex.date for ex in trade.exits), default=trade.entry_date)
        x_last = mdates.date2num(last_exit_date)
        ax.plot([x_entry, x_last], [trade.tp25, trade.tp25], color='#64FFDA', linewidth=0.65, alpha=0.42, zorder=4)
        ax.plot([x_entry, x_last], [trade.target, trade.target], color='#76FF03', linewidth=0.72, alpha=0.52, zorder=4)
        ax.plot([x_entry, x_last], [trade.initial_stop, trade.initial_stop], color='#FF1744', linewidth=0.72, alpha=0.50, zorder=4)
        if any(ex.reason in ('BE-Stop', 'Period-Close', 'Range-Close') for ex in trade.exits):
            ax.plot([x_entry, x_last], [trade.entry, trade.entry], color='#B0BEC5', linewidth=0.55, alpha=0.35, zorder=4)
        for ex in trade.exits:
            color = exit_colors.get(ex.reason, '#E0E0E0')
            ax.scatter([mdates.date2num(ex.date)], [ex.price], marker='X', color=color, s=88, zorder=10, edgecolor='black', linewidth=0.8)
        if not trade.exits:
            continue
        final_exit = max(trade.exits, key=lambda ex: ex.date)
        color = exit_colors.get(final_exit.reason, '#E0E0E0')
        ax.annotate(
            f'#{i} {trade.direction[0]} {trade.net_points:+.0f}',
            xy=(mdates.date2num(final_exit.date), final_exit.price),
            xytext=(7, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=color,
            fontsize=7,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.18', fc=BG, ec=color, alpha=0.92),
        )
    return total_pl, pattern


def draw_year(
    year: int,
    bars: pd.DataFrame,
    levels: pd.DataFrame,
    out_path: Path,
    retracement: float,
    market: str,
    point_value: float,
) -> dict:
    period = str(year)
    work = bars.copy().sort_values('date').reset_index(drop=True)
    trades, meta = simulate_year(period, work, True, 'boundary', 'inside-range-candle')
    range_bars = work[work['month'] <= 3]
    dates = pd.to_datetime(work['date'])

    fig = plt.figure(figsize=(19, 9.5), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    draw_candles(ax, work)
    plot_weekly_supertrend(ax, work)

    if not range_bars.empty:
        ax.axvspan(
            pd.Timestamp(range_bars.iloc[0]['date']),
            pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1),
            color=RANGE_BLUE,
            alpha=0.28,
            zorder=0,
        )

    rh = float(meta.get('range_high', 0.0) or 0.0)
    rl = float(meta.get('range_low', 0.0) or 0.0)
    rv = float(meta.get('range', 0.0) or 0.0)
    if rv > 0:
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhspan(rl, rh, color=RANGE_BLUE, alpha=0.10, zorder=0)
        last_x = mdates.date2num(dates.iloc[-1]) + 2.0
        ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=8, va='center')
        ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=8, va='center')

    year_levels = levels[levels['year'].eq(year)].copy()
    draw_retracement_segments(ax, work, year_levels, retracement)
    total_pl, pattern = draw_trades(ax, trades, point_value)

    touched = int(year_levels['touched'].sum()) if not year_levels.empty else 0
    total_levels = len(year_levels)
    title = (
        f'{year} {market} yearly ORB scaleout3 · prior-month directional {retracement:.0%} retracement · '
        f'{touched}/{total_levels} touched · {len(trades)} trades · {total_pl:+.1f} contract-pts (${total_pl * point_value:+,.0f})'
    )
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color=GRID)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=4), dates.iloc[-1] + pd.Timedelta(days=8))
    legend_handles = [
        mpatches.Patch(facecolor='none', edgecolor=RET_BULL, label=f'Prev bullish month: high - {retracement:.0%} range'),
        mpatches.Patch(facecolor='none', edgecolor=RET_BEAR, label=f'Prev bearish month: low + {retracement:.0%} range'),
        mpatches.Patch(facecolor='none', edgecolor='#E0E0E0', label='Yearly ORB H/L'),
    ]
    leg = ax.legend(handles=legend_handles, loc='upper left', fontsize=7, framealpha=0.16)
    for text in leg.get_texts():
        text.set_color(TEXT)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)

    return {
        'year': year,
        'symbol': str(meta.get('symbol', '')),
        'range': round(rv, 2),
        'pattern': pattern,
        'trades': len(trades),
        'net_pts': round(total_pl, 2),
        'net_usd': round(total_pl * point_value, 2),
        'levels': total_levels,
        'touched': touched,
        'touch_rate': round(touched / total_levels * 100, 2) if total_levels else 0.0,
        'chart': f'{year}/{year}.png',
    }


def write_indexes(out_dir: Path, rows: list[dict], levels: pd.DataFrame, retracement: float, market: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        year_levels = levels[levels['year'].eq(row['year'])]
        lines = [
            f'# {row["year"]} {market} Yearly ORB + Prior-Month {retracement:.0%} Retracement',
            '',
            'Daily candles with the existing yearly ORB scaleout3 trade annotations and one prior-month directional retracement segment for each month.',
            '',
            f'Chart: [{row["year"]}.png]({row["year"]}.png)',
            '',
            f'| Month | Previous Month | Previous Direction | {retracement:.0%} Level | Touched | First Touch |',
            '|---|---|---|---:|---|---|',
        ]
        for _, level in year_levels.iterrows():
            lines.append(
                f"| {level['month']} | {level['prev_month']} | {level['prev_direction']} | "
                f"{float(level['level']):.2f} | {'yes' if bool(level['touched']) else 'no'} | {level['first_touch_date'] or ''} |"
            )
        lines.append('')
        (out_dir / str(row['year']) / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    lines = [
        f'# {market} Yearly ORB Prior-Month {retracement:.0%} Retracement Study',
        '',
        'Sidecar chart set for `yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close`.',
        '',
        'Level definition:',
        '',
        f'- Previous month green close: `previous high - {retracement:.2f} * previous range`.',
        f'- Previous month red close: `previous low + {retracement:.2f} * previous range`.',
        '- The line is drawn only across the following/current month.',
        '',
        '[levels.csv](levels.csv) contains every monthly level and first touch date.',
        '',
        '| Year | Symbol | Levels | Touched | Touch Rate | Trades | Net contract-pts | Chart |',
        '|---:|---|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        lines.append(
            f"| {row['year']} | {row['symbol']} | {row['levels']} | {row['touched']} | "
            f"{row['touch_rate']:.1f}% | {row['trades']} | {row['net_pts']:+.2f} | [{row['year']}/]({row['year']}/INDEX.md) |"
        )
    lines.append('')
    lines.extend(
        [
            '## Read',
            '',
            'This chart set is for visual research, not a trade rule. The immediate question is whether the prior month retracement line behaves like a monthly support/resistance shelf around the yearly ORB trade windows.',
            '',
        ]
    )
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def update_base_index(base_dir: Path, out_dir: Path, retracement: float) -> None:
    index = base_dir / 'INDEX.md'
    if not index.exists():
        return
    text = index.read_text(encoding='utf-8')
    rel = out_dir.resolve().relative_to(base_dir.resolve())
    line = f'- [Prior-month {retracement:.0%} retracement sidecar charts]({rel}/INDEX.md)'
    if line in text:
        return
    if '## Sidecar Studies' in text:
        text = text.rstrip() + '\n' + line + '\n'
    else:
        text = text.rstrip() + '\n\n## Sidecar Studies\n\n' + line + '\n'
    index.write_text(text, encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY)
    ap.add_argument('--base-csv', type=Path, default=BASE_CSV)
    ap.add_argument('--out', type=Path, default=OUT_DIR)
    ap.add_argument('--retracement', type=float, default=0.68)
    ap.add_argument('--market', type=str, default='MNQ')
    ap.add_argument('--point-value', type=float, default=2.0)
    ap.add_argument('--weekly-atr-len', type=int, default=14)
    ap.add_argument('--weekly-atr-mult', type=float, default=3.0)
    args = ap.parse_args()

    daily = load_daily(args.daily)
    daily = add_weekly_supertrend(daily, args.weekly_atr_len, args.weekly_atr_mult)
    levels = prior_month_retracement_levels(daily, args.retracement)
    base = pd.read_csv(args.base_csv)
    years = sorted(int(year) for year in base['Period'].dropna().astype(int).unique())

    rows: list[dict] = []
    for year in years:
        year_bars = daily[daily['year'].eq(year)].copy()
        if year_bars.empty:
            continue
        row = draw_year(year, year_bars, levels, args.out / str(year) / f'{year}.png', args.retracement, args.market.upper(), args.point_value)
        rows.append(row)
        print(f"{row['chart']} levels={row['touched']}/{row['levels']} touched net={row['net_pts']:+.2f}")

    args.out.mkdir(parents=True, exist_ok=True)
    levels[levels['year'].isin([row['year'] for row in rows])].to_csv(args.out / 'levels.csv', index=False)
    write_indexes(args.out, rows, levels, args.retracement, args.market.upper())
    update_base_index(BASE_CHART_DIR, args.out, args.retracement)
    print(f'Wrote {len(rows)} retracement charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    print(f'Wrote {args.out / "levels.csv"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
