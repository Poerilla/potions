#!/usr/bin/env python3
"""Study bearish ATR Supertrend flips as fixed-R short opportunities.

For each bullish-to-bearish ATR flip, use the flip close as the reference
entry and the initial bearish ATR stop as the fixed stop. Then ask whether
price reaches 1R, 2R, and 3R before touching that original stop.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from yearly_orb_delivery_research_charts import calculate_supertrend_stop, calculate_weekly_atr_trailing_stop_on_daily


BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
CYAN = '#00BCD4'
ORANGE = '#FF9800'
YELLOW = '#FFC107'


def aggregate_ohlc(daily: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    work = daily[['date', 'open', 'high', 'low', 'close', 'symbol']].copy()
    work['date'] = pd.to_datetime(work['date'])
    if timeframe == 'daily':
        return work.sort_values('date').reset_index(drop=True)
    if timeframe == 'weekly':
        work['_period'] = work['date'].dt.to_period('W-FRI')
    elif timeframe == 'biweekly':
        work['_period'] = work['date'].dt.to_period('2W-FRI')
    elif timeframe == 'monthly':
        work['_period'] = work['date'].dt.to_period('M')
    else:
        raise ValueError(f'unsupported timeframe: {timeframe}')

    rows: list[dict] = []
    for _, group in work.groupby('_period', sort=True):
        rows.append(
            {
                'date': pd.Timestamp(group.iloc[-1]['date']),
                'open': float(group.iloc[0]['open']),
                'high': float(group['high'].max()),
                'low': float(group['low'].min()),
                'close': float(group.iloc[-1]['close']),
                'symbol': str(group.iloc[-1].get('symbol', '')),
            }
        )
    return pd.DataFrame(rows)


def evaluate_target(
    daily_after_signal: pd.DataFrame,
    entry: float,
    stop: float,
    r_mult: int,
) -> dict:
    risk = stop - entry
    target = entry - r_mult * risk
    mae = 0.0
    mfe = 0.0
    max_high = entry
    min_low = entry
    for _, row in daily_after_signal.iterrows():
        high = float(row['high'])
        low = float(row['low'])
        date = pd.Timestamp(row['date'])
        max_high = max(max_high, high)
        min_low = min(min_low, low)
        mae = min(mae, entry - max_high)
        mfe = max(mfe, entry - min_low)
        hit_stop = high >= stop
        hit_target = low <= target
        if hit_stop and hit_target:
            return {
                'r': r_mult,
                'outcome': 'stop_first_ambiguous',
                'hit': False,
                'exit_date': date,
                'target': target,
                'mae_pts': mae,
                'mfe_pts': mfe,
            }
        if hit_stop:
            return {
                'r': r_mult,
                'outcome': 'stop',
                'hit': False,
                'exit_date': date,
                'target': target,
                'mae_pts': mae,
                'mfe_pts': mfe,
            }
        if hit_target:
            return {
                'r': r_mult,
                'outcome': 'target',
                'hit': True,
                'exit_date': date,
                'target': target,
                'mae_pts': mae,
                'mfe_pts': mfe,
            }
    return {
        'r': r_mult,
        'outcome': 'open',
        'hit': False,
        'exit_date': pd.NaT,
        'target': target,
        'mae_pts': mae,
        'mfe_pts': mfe,
    }


def study_flips(
    daily: pd.DataFrame,
    signal_timeframe: str,
    atr_length: int,
    atr_multiplier: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = aggregate_ohlc(daily, signal_timeframe)
    atr = calculate_supertrend_stop(base, atr_length, atr_multiplier)
    daily = daily.copy().sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])

    flips: list[dict] = []
    target_rows: list[dict] = []
    for idx in range(1, len(atr)):
        prev = atr.iloc[idx - 1]
        curr = atr.iloc[idx]
        if str(prev['atr_trend']) != 'up' or str(curr['atr_trend']) != 'down':
            continue
        signal_date = pd.Timestamp(curr['date'])
        entry = float(curr['close'])
        stop = float(curr['atr_stop'])
        risk = stop - entry
        if not math.isfinite(risk) or risk <= 0:
            continue

        after = daily[daily['date'] > signal_date].copy()
        flip_id = len(flips) + 1
        flip_base = {
            'flip_id': flip_id,
            'signal_timeframe': signal_timeframe,
            'signal_date': signal_date.date().isoformat(),
            'symbol': str(curr.get('symbol', '')),
            'entry_ref': round(entry, 4),
            'stop_px': round(stop, 4),
            'risk_pts': round(risk, 4),
            'atr_pts': round(float(curr['atr']), 4),
            'atr_pct': round(float(curr['atr']) / entry * 100, 4) if entry else 0.0,
        }
        flips.append(flip_base)
        for r_mult in [1, 2, 3]:
            outcome = evaluate_target(after, entry, stop, r_mult)
            target_rows.append(
                {
                    **flip_base,
                    'r': r_mult,
                    'target_px': round(float(outcome['target']), 4),
                    'hit': bool(outcome['hit']),
                    'outcome': outcome['outcome'],
                    'exit_date': ''
                    if pd.isna(outcome['exit_date'])
                    else pd.Timestamp(outcome['exit_date']).date().isoformat(),
                    'mae_pts': round(float(outcome['mae_pts']), 4),
                    'mae_usd': round(float(outcome['mae_pts']) * 20.0, 2),
                    'mfe_pts': round(float(outcome['mfe_pts']), 4),
                    'mfe_usd': round(float(outcome['mfe_pts']) * 20.0, 2),
                }
            )
    return pd.DataFrame(flips), pd.DataFrame(target_rows)


def summarize(targets: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if targets.empty:
        return pd.DataFrame(rows)
    for (timeframe, r_mult), group in targets.groupby(['signal_timeframe', 'r'], sort=True):
        hits = group[group['hit']].copy()
        rows.append(
            {
                'signal_timeframe': timeframe,
                'r': r_mult,
                'flips': len(group),
                'hits': int(group['hit'].sum()),
                'hit_rate': round(float(group['hit'].mean()) * 100, 2),
                'ambiguous_stop_first': int(group['outcome'].eq('stop_first_ambiguous').sum()),
                'avg_risk_pts': round(float(group['risk_pts'].mean()), 2),
                'avg_atr_pct': round(float(group['atr_pct'].mean()), 2),
                'hit_avg_mae_pts': round(float(hits['mae_pts'].mean()), 2) if not hits.empty else 0.0,
                'hit_worst_mae_pts': round(float(hits['mae_pts'].min()), 2) if not hits.empty else 0.0,
                'hit_avg_mae_usd': round(float(hits['mae_usd'].mean()), 2) if not hits.empty else 0.0,
                'hit_worst_mae_usd': round(float(hits['mae_usd'].min()), 2) if not hits.empty else 0.0,
                'all_worst_mae_pts': round(float(group['mae_pts'].min()), 2),
                'all_worst_mae_usd': round(float(group['mae_usd'].min()), 2),
            }
        )
    return pd.DataFrame(rows)


def summarize_daily_weekly_context(
    daily: pd.DataFrame,
    daily_targets: pd.DataFrame,
    atr_length: int,
    atr_multiplier: float,
) -> pd.DataFrame:
    if daily_targets.empty:
        return pd.DataFrame()
    weekly = calculate_weekly_atr_trailing_stop_on_daily(daily, atr_length, atr_multiplier)
    weekly = weekly[['date', 'atr_trend', 'atr_stop']].copy()
    weekly['date'] = pd.to_datetime(weekly['date'])
    weekly = weekly.rename(columns={'atr_trend': 'weekly_atr_trend', 'atr_stop': 'weekly_atr_stop'})
    work = daily_targets.copy()
    work['signal_date_dt'] = pd.to_datetime(work['signal_date'])
    work = work.merge(weekly, how='left', left_on='signal_date_dt', right_on='date')
    work['weekly_atr_trend'] = work['weekly_atr_trend'].fillna('na')

    rows: list[dict] = []
    for (trend, r_mult), group in work.groupby(['weekly_atr_trend', 'r'], sort=True):
        hits = group[group['hit']].copy()
        rows.append(
            {
                'weekly_atr_trend': trend,
                'r': r_mult,
                'flips': len(group),
                'hits': int(group['hit'].sum()),
                'hit_rate': round(float(group['hit'].mean()) * 100, 2),
                'avg_risk_pts': round(float(group['risk_pts'].mean()), 2),
                'hit_avg_mae_pts': round(float(hits['mae_pts'].mean()), 2) if not hits.empty else 0.0,
                'hit_worst_mae_pts': round(float(hits['mae_pts'].min()), 2) if not hits.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, alpha=0.15, color=GRID)
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    dates = pd.to_datetime(bars['date'])
    x = mdates.date2num(dates)
    if len(x) > 1:
        median_gap = pd.Series(x).diff().dropna().median()
        width = max(0.72, float(median_gap) * 0.55)
    else:
        width = 0.72
    for xval, (_, row) in zip(x, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=color, linewidth=0.65, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (xval - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.9,
                zorder=3,
            )
        )


def plot_stop(ax: plt.Axes, atr: pd.DataFrame) -> None:
    for trend, color in [('up', CYAN), ('down', ORANGE)]:
        segment = atr[atr['atr_trend'].eq(trend)].copy()
        if segment.empty:
            continue
        split = (segment.index.to_series().diff() != 1).cumsum()
        for _, chunk in segment.groupby(split):
            ax.plot(
                mdates.date2num(pd.to_datetime(chunk['date'])),
                chunk['atr_stop'].astype(float),
                color=color,
                linewidth=1.25,
                alpha=0.95,
                zorder=5,
            )


def draw_atr_visual_chart(
    bars: pd.DataFrame,
    out_path: Path,
    title: str,
    timeframe: str,
) -> None:
    fig = plt.figure(figsize=(17, 8.5), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, bars)
    plot_stop(ax, bars.reset_index(drop=True))
    dates = pd.to_datetime(bars['date'])
    if not dates.empty:
        span_days = max((dates.iloc[-1] - dates.iloc[0]).days, 1)
        ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=14), dates.iloc[-1] + pd.Timedelta(days=14))
        if span_days > 900:
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        elif timeframe == 'monthly':
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.set_title(title, color='white', fontsize=11, fontweight='bold', loc='left')
    legend = ax.legend(
        handles=[
            plt.Line2D([0], [0], color=CYAN, lw=1.25, label='bullish trailing stop'),
            plt.Line2D([0], [0], color=ORANGE, lw=1.25, label='bearish trailing stop'),
        ],
        loc='upper left',
        fontsize=8,
        framealpha=0.18,
    )
    for text in legend.get_texts():
        text.set_color('white')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)


def write_visual_charts(daily: pd.DataFrame, out_dir: Path, market: str, atr_length: int, atr_multiplier: float) -> None:
    chart_rows: list[dict] = []
    trend_rows: list[dict] = []
    for timeframe in ['biweekly', 'monthly']:
        bars = aggregate_ohlc(daily, timeframe)
        atr = calculate_supertrend_stop(bars, atr_length, atr_multiplier)
        for year, group in atr.groupby(pd.to_datetime(atr['date']).dt.year):
            if len(group) < 2:
                continue
            out_path = out_dir / timeframe / f'{year}.png'
            draw_atr_visual_chart(
                group.copy(),
                out_path,
                f'{market.upper()} {timeframe} ATR Supertrend ATR({atr_length}) x {atr_multiplier:g} · {year}',
                timeframe,
            )
            chart_rows.append({'timeframe': timeframe, 'year': year, 'chart': f'{timeframe}/{year}.png'})

        trend_source = atr[atr['atr_trend'].isin(['up', 'down'])].copy()
        trend_source['_segment'] = trend_source['atr_trend'].ne(trend_source['atr_trend'].shift()).cumsum()
        context_bars = 6 if timeframe == 'biweekly' else 3
        for segment_no, (_, segment) in enumerate(trend_source.groupby('_segment', sort=True), start=1):
            if len(segment) < 2:
                continue
            trend = str(segment.iloc[0]['atr_trend'])
            start_pos = max(0, int(segment.index.min()) - context_bars)
            end_pos = min(len(atr) - 1, int(segment.index.max()) + context_bars)
            window = atr.iloc[start_pos : end_pos + 1].copy()
            start_date = pd.Timestamp(segment.iloc[0]['date']).date().isoformat()
            end_date = pd.Timestamp(segment.iloc[-1]['date']).date().isoformat()
            file_name = f'{segment_no:02d}_{start_date}_to_{end_date}_{trend}.png'
            out_path = out_dir / f'{timeframe}_trend_windows' / file_name
            draw_atr_visual_chart(
                window,
                out_path,
                (
                    f'{market.upper()} {timeframe} ATR {trend} trend window · '
                    f'{start_date} to {end_date} · {len(segment)} bars'
                ),
                timeframe,
            )
            trend_rows.append(
                {
                    'timeframe': timeframe,
                    'segment': segment_no,
                    'trend': trend,
                    'start': start_date,
                    'end': end_date,
                    'bars': len(segment),
                    'chart': f'{timeframe}_trend_windows/{file_name}',
                }
            )

    lines = [
        f'# {market.upper()} Higher-Timeframe ATR Supertrend Visuals',
        '',
        f'Visual-only charts using ATR({atr_length}) x {atr_multiplier:g}. These are aggregated OHLC views, not execution backtests.',
        '',
        'The trend-window charts group each contiguous ATR trend into one image, with context bars before and after the trend. Those are the better charts for studying long ATR regimes; the yearly charts are kept only as quick calendar slices.',
        '',
        '## Trend Windows',
        '',
        '| Timeframe | Segment | Trend | Start | End | Bars | Chart |',
        '|---|---:|---|---|---|---:|---|',
    ]
    for row in trend_rows:
        lines.append(
            f'| {row["timeframe"]} | {row["segment"]} | {row["trend"]} | {row["start"]} | {row["end"]} | {row["bars"]} | [{Path(row["chart"]).name}]({row["chart"]}) |'
        )
    lines.extend(
        [
            '',
            '## Year Slices',
            '',
            '| Timeframe | Year | Chart |',
            '|---|---:|---|',
        ]
    )
    for row in chart_rows:
        lines.append(f'| {row["timeframe"]} | {row["year"]} | [{Path(row["chart"]).name}]({row["chart"]}) |')
    lines.append('')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def write_readme(
    out_dir: Path,
    market: str,
    summary: pd.DataFrame,
    targets: pd.DataFrame,
    weekly_context: pd.DataFrame,
) -> None:
    lines = [
        f'# {market.upper()} ATR Bearish Flip R Study',
        '',
        'Question: after a bullish-to-bearish ATR Supertrend flip, if the flip close is the short reference price and the initial bearish ATR stop is the fixed stop, how often does price reach 1R, 2R, or 3R before touching that original stop?',
        '',
        'Rules:',
        '- ATR Supertrend-style stop: ATR(14) x 3.',
        '- Short reference price is the flip bar close.',
        '- Fixed stop is the initial bearish ATR stop on the flip bar.',
        '- Path evaluation starts on the next daily bar after the flip is confirmed.',
        '- If stop and target are both inside the same daily bar, the study counts it as stop-first.',
        '- MAE is reported as adverse points/dollars for the short; negative values are worse.',
        '',
        '## Summary',
        '',
        '| Signal TF | R Target | Flips | Hits | Hit Rate | Stop-First Ambiguous | Avg Risk Pts | Avg ATR % | Hit Avg MAE | Hit Worst MAE | All Worst MAE |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for _, row in summary.iterrows():
        lines.append(
            f'| {row["signal_timeframe"]} | {int(row["r"])}R | {int(row["flips"])} | {int(row["hits"])} | '
            f'{row["hit_rate"]:.2f}% | {int(row["ambiguous_stop_first"])} | {row["avg_risk_pts"]:.2f} | '
            f'{row["avg_atr_pct"]:.2f}% | {row["hit_avg_mae_pts"]:+.2f} pts (${row["hit_avg_mae_usd"]:+,.0f}) | '
            f'{row["hit_worst_mae_pts"]:+.2f} pts (${row["hit_worst_mae_usd"]:+,.0f}) | '
            f'{row["all_worst_mae_pts"]:+.2f} pts (${row["all_worst_mae_usd"]:+,.0f}) |'
        )
    lines.extend(['', '## Read', ''])
    daily = summary[summary['signal_timeframe'].eq('daily')]
    weekly = summary[summary['signal_timeframe'].eq('weekly')]
    if not daily.empty and not weekly.empty:
        d1 = float(daily[daily['r'].eq(1)]['hit_rate'].iloc[0])
        w1 = float(weekly[weekly['r'].eq(1)]['hit_rate'].iloc[0])
        d2 = float(daily[daily['r'].eq(2)]['hit_rate'].iloc[0])
        w2 = float(weekly[weekly['r'].eq(2)]['hit_rate'].iloc[0])
        d3 = float(daily[daily['r'].eq(3)]['hit_rate'].iloc[0])
        w3 = float(weekly[weekly['r'].eq(3)]['hit_rate'].iloc[0])
        lines.append(
            f'Weekly ATR produced fewer bearish flips, with hit-rate deltas vs daily of {w1 - d1:+.2f} pts at 1R, {w2 - d2:+.2f} pts at 2R, and {w3 - d3:+.2f} pts at 3R.'
        )
        lines.append('')
    if not weekly_context.empty:
        lines.extend(
            [
                '## Daily Flip Split By Confirmed Weekly ATR State',
                '',
                '| Weekly ATR State | R Target | Daily Flips | Hits | Hit Rate | Avg Risk Pts | Hit Avg MAE | Hit Worst MAE |',
                '|---|---:|---:|---:|---:|---:|---:|---:|',
            ]
        )
        for _, row in weekly_context.iterrows():
            lines.append(
                f'| {row["weekly_atr_trend"]} | {int(row["r"])}R | {int(row["flips"])} | {int(row["hits"])} | '
                f'{row["hit_rate"]:.2f}% | {row["avg_risk_pts"]:.2f} | {row["hit_avg_mae_pts"]:+.2f} | {row["hit_worst_mae_pts"]:+.2f} |'
            )
        lines.append('')
    lines.extend(
        [
            'CSV outputs:',
            '- `flip_targets.csv`: one row per flip/R target.',
            '- `summary.csv`: aggregate hit rates and MAE.',
            '- `daily_weekly_context_summary.csv`: daily flips split by already-confirmed weekly ATR state.',
            '',
        ]
    )
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--visual-out', type=Path, required=True)
    ap.add_argument('--market', type=str, default='NQ')
    ap.add_argument('--atr-length', type=int, default=14)
    ap.add_argument('--atr-multiplier', type=float, default=3.0)
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    args.out.mkdir(parents=True, exist_ok=True)

    all_flips: list[pd.DataFrame] = []
    all_targets: list[pd.DataFrame] = []
    for timeframe in ['daily', 'weekly']:
        flips, targets = study_flips(daily, timeframe, args.atr_length, args.atr_multiplier)
        all_flips.append(flips)
        all_targets.append(targets)

    flips_df = pd.concat(all_flips, ignore_index=True) if all_flips else pd.DataFrame()
    targets_df = pd.concat(all_targets, ignore_index=True) if all_targets else pd.DataFrame()
    summary_df = summarize(targets_df)
    daily_targets = targets_df[targets_df['signal_timeframe'].eq('daily')].copy() if not targets_df.empty else pd.DataFrame()
    weekly_context_df = summarize_daily_weekly_context(daily, daily_targets, args.atr_length, args.atr_multiplier)

    flips_df.to_csv(args.out / 'flips.csv', index=False)
    targets_df.to_csv(args.out / 'flip_targets.csv', index=False)
    summary_df.to_csv(args.out / 'summary.csv', index=False)
    weekly_context_df.to_csv(args.out / 'daily_weekly_context_summary.csv', index=False)
    write_readme(args.out, args.market, summary_df, targets_df, weekly_context_df)
    write_visual_charts(daily, args.visual_out, args.market, args.atr_length, args.atr_multiplier)
    print(summary_df.to_string(index=False))
    print(f'wrote {args.out}')
    print(f'wrote {args.visual_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
