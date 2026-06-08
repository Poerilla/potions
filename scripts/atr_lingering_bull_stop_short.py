#!/usr/bin/env python3
"""Short retest study against a broken bullish ATR stop.

Idea:
- Compute the same daily ATR Supertrend-style stop used by the ATR DCA study.
- When trend flips from bullish to bearish, keep the prior bullish stop level
  alive as a "lingering bullish stop" for a fixed number of weeks.
- During that bearish window, wait for the first down-close daily candle that
  closes under the lingering line.
- After that signal close, place a sell-limit at the lingering line.
- If filled, short 1 contract with a fixed point target and point stop.
- Also exit next daily open after a daily close back over the lingering line.

The study is intentionally daily-bar research. It is a first pass to see
whether the lingering stop acts like resistance after a bearish flip.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import argparse
import math
import shutil

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from yearly_orb_delivery_research_charts import calculate_daily_atr_trailing_stop
from atr_supertrend_dca_long import max_drawdown, profit_factor


BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
CYAN = '#00BCD4'
ORANGE = '#FF9800'
YELLOW = '#FFC107'
PURPLE = '#EA80FC'
BLUE = '#40C4FF'


@dataclass
class LingeringLine:
    line_id: int
    start_idx: int
    end_idx: int
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    level: float
    source_date: pd.Timestamp


@dataclass
class Trade:
    trade_id: int
    line_id: int
    line_level: float
    line_start_date: pd.Timestamp
    line_end_date: pd.Timestamp
    signal_date: pd.Timestamp
    order_live_date: pd.Timestamp
    fill_date: pd.Timestamp
    entry_price: float
    target: float
    stop: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str
    symbol: str
    mae_pts: float
    mfe_pts: float

    @property
    def net_pts(self) -> float:
        return self.entry_price - self.exit_price

    @property
    def result(self) -> str:
        return 'Win' if self.net_pts > 0 else 'Loss' if self.net_pts < 0 else 'Flat'


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    dates = pd.to_datetime(bars['date'])
    x = mdates.date2num(dates)
    width = 0.72
    for xval, (_, row) in zip(x, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=color, linewidth=0.75, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (xval - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.95,
                zorder=3,
            )
        )


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, alpha=0.15, color=GRID)
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')


def build_lingering_lines(work: pd.DataFrame, extension_weeks: int) -> list[LingeringLine]:
    lines: list[LingeringLine] = []
    extension_days = max(extension_weeks, 0) * 7
    for idx in range(1, len(work)):
        prev = work.iloc[idx - 1]
        curr = work.iloc[idx]
        if str(prev['atr_trend']) != 'up' or str(curr['atr_trend']) != 'down':
            continue
        start_date = pd.Timestamp(curr['date'])
        end_date = start_date + pd.Timedelta(days=extension_days)
        end_idx = idx
        for j in range(idx, len(work)):
            d = pd.Timestamp(work.loc[j, 'date'])
            if d > end_date or str(work.loc[j, 'atr_trend']) != 'down':
                break
            end_idx = j
        if end_idx < idx:
            continue
        lines.append(
            LingeringLine(
                line_id=len(lines) + 1,
                start_idx=idx,
                end_idx=end_idx,
                start_date=start_date,
                end_date=pd.Timestamp(work.loc[end_idx, 'date']),
                level=float(prev['atr_stop']),
                source_date=pd.Timestamp(prev['date']),
            )
        )
    return lines


def simulate(
    daily: pd.DataFrame,
    point_target: float,
    point_stop: float,
    point_value: float,
    atr_length: int,
    atr_multiplier: float,
    extension_weeks: int,
    close_over_line_exit: bool,
    allow_multiple_entries: bool,
) -> tuple[pd.DataFrame, list[LingeringLine], list[Trade], list[dict]]:
    work = daily.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work = calculate_daily_atr_trailing_stop(work, atr_length, atr_multiplier)
    lines = build_lingering_lines(work, extension_weeks)
    trades: list[Trade] = []
    audit: list[dict] = []

    for line in lines:
        search_idx = line.start_idx
        line_attempts = 0
        while search_idx <= line.end_idx:
            signal_idx: Optional[int] = None
            for idx in range(search_idx, line.end_idx + 1):
                row = work.loc[idx]
                if float(row['close']) < float(row['open']) and float(row['close']) < line.level:
                    signal_idx = idx
                    break
            if signal_idx is None:
                if line_attempts == 0:
                    audit.append(
                        {
                            'line_id': line.line_id,
                            'line_start_date': line.start_date.date().isoformat(),
                            'line_end_date': line.end_date.date().isoformat(),
                            'line_level': line.level,
                            'status': 'no_downclose_under_line',
                        }
                    )
                break

            line_attempts += 1
            order_live_idx = signal_idx + 1
            if order_live_idx > line.end_idx or order_live_idx >= len(work):
                audit.append(
                    {
                        'line_id': line.line_id,
                        'attempt': line_attempts,
                        'signal_date': pd.Timestamp(work.loc[signal_idx, 'date']).date().isoformat(),
                        'line_level': line.level,
                        'status': 'signal_too_late',
                    }
                )
                break

            fill_idx: Optional[int] = None
            for idx in range(order_live_idx, line.end_idx + 1):
                row = work.loc[idx]
                if float(row['high']) >= line.level:
                    fill_idx = idx
                    break
            if fill_idx is None:
                audit.append(
                    {
                        'line_id': line.line_id,
                        'attempt': line_attempts,
                        'signal_date': pd.Timestamp(work.loc[signal_idx, 'date']).date().isoformat(),
                        'order_live_date': pd.Timestamp(work.loc[order_live_idx, 'date']).date().isoformat(),
                        'line_level': line.level,
                        'status': 'limit_not_filled',
                    }
                )
                break

            entry = line.level
            target = entry - point_target
            stop = entry + point_stop
            mae_pts = 0.0
            mfe_pts = 0.0
            pending_close_over_exit = False
            exit_idx: Optional[int] = None
            exit_price: Optional[float] = None
            exit_reason = ''

            for idx in range(fill_idx, len(work)):
                row = work.loc[idx]
                if pending_close_over_exit:
                    exit_idx = idx
                    exit_price = float(row['open'])
                    exit_reason = 'Close-Over-Line-Next-Open'
                    break

                high = float(row['high'])
                low = float(row['low'])
                open_px = float(row['open'])
                close = float(row['close'])

                fill_bar_opened_through_limit = idx == fill_idx and open_px >= entry
                fill_bar_rallied_to_limit = idx == fill_idx and open_px < entry
                if fill_bar_rallied_to_limit:
                    # The low of the fill day may have printed before the sell
                    # limit was touched. Keep the adverse high, but only credit
                    # favorable movement that is confirmed by the close.
                    mae_pts = min(mae_pts, entry - high)
                    mfe_pts = max(mfe_pts, max(0.0, entry - close))
                else:
                    mae_pts = min(mae_pts, entry - high)
                    mfe_pts = max(mfe_pts, entry - low)

                hit_stop = high >= stop
                hit_target = low <= target and (idx != fill_idx or fill_bar_opened_through_limit)
                if hit_stop:
                    exit_idx = idx
                    exit_price = stop
                    exit_reason = 'Point-Stop'
                    break
                if hit_target:
                    exit_idx = idx
                    exit_price = target
                    exit_reason = 'Target'
                    break
                if close_over_line_exit and close > line.level:
                    pending_close_over_exit = True

            if exit_idx is None:
                last = work.iloc[-1]
                exit_idx = len(work) - 1
                exit_price = float(last['close'])
                exit_reason = 'Period-Close'

            trade = Trade(
                trade_id=len(trades) + 1,
                line_id=line.line_id,
                line_level=line.level,
                line_start_date=line.start_date,
                line_end_date=line.end_date,
                signal_date=pd.Timestamp(work.loc[signal_idx, 'date']),
                order_live_date=pd.Timestamp(work.loc[order_live_idx, 'date']),
                fill_date=pd.Timestamp(work.loc[fill_idx, 'date']),
                entry_price=entry,
                target=target,
                stop=stop,
                exit_date=pd.Timestamp(work.loc[exit_idx, 'date']),
                exit_price=float(exit_price),
                exit_reason=exit_reason,
                symbol=str(work.loc[fill_idx, 'symbol']),
                mae_pts=mae_pts,
                mfe_pts=mfe_pts,
            )
            trades.append(trade)
            audit.append(
                {
                    'line_id': line.line_id,
                    'attempt': line_attempts,
                    'signal_date': trade.signal_date.date().isoformat(),
                    'order_live_date': trade.order_live_date.date().isoformat(),
                    'fill_date': trade.fill_date.date().isoformat(),
                    'exit_date': trade.exit_date.date().isoformat(),
                    'line_level': line.level,
                    'status': 'filled',
                    'result': trade.result,
                    'net_pts': round(trade.net_pts, 2),
                    'net_usd': round(trade.net_pts * point_value, 2),
                }
            )
            if not allow_multiple_entries or exit_idx >= line.end_idx:
                break
            search_idx = exit_idx + 1

    trades_df = pd.DataFrame(
        [
            {
                'trade_id': t.trade_id,
                'line_id': t.line_id,
                'symbol': t.symbol,
                'line_start_date': t.line_start_date.date().isoformat(),
                'line_end_date': t.line_end_date.date().isoformat(),
                'signal_date': t.signal_date.date().isoformat(),
                'order_live_date': t.order_live_date.date().isoformat(),
                'fill_date': t.fill_date.date().isoformat(),
                'exit_date': t.exit_date.date().isoformat(),
                'entry_price': round(t.entry_price, 2),
                'line_level': round(t.line_level, 2),
                'target': round(t.target, 2),
                'stop': round(t.stop, 2),
                'exit_price': round(t.exit_price, 2),
                'exit_reason': t.exit_reason,
                'result': t.result,
                'net_pts': round(t.net_pts, 2),
                'net_usd': round(t.net_pts * point_value, 2),
                'mae_pts': round(t.mae_pts, 2),
                'mae_usd': round(t.mae_pts * point_value, 2),
                'mfe_pts': round(t.mfe_pts, 2),
                'mfe_usd': round(t.mfe_pts * point_value, 2),
            }
            for t in trades
        ]
    )
    return work, lines, trades, audit


def plot_atr(ax: plt.Axes, work: pd.DataFrame) -> None:
    for trend, color in [('up', CYAN), ('down', ORANGE)]:
        segment = work[work['atr_trend'].eq(trend)].copy()
        if segment.empty:
            continue
        split_id = (segment.index.to_series().diff() != 1).cumsum()
        for _, chunk in segment.groupby(split_id):
            ax.plot(
                mdates.date2num(pd.to_datetime(chunk['date'])),
                chunk['atr_stop'].astype(float),
                color=color,
                linewidth=1.05,
                alpha=0.8,
                zorder=4,
            )


def draw_trade_chart(trade: Trade, work: pd.DataFrame, out_path: Path, market: str, point_value: float) -> str:
    start = trade.line_start_date - pd.Timedelta(days=14)
    end = trade.exit_date + pd.Timedelta(days=14)
    bars = work[work['date'].between(start, end)].copy()
    if bars.empty:
        return ''

    fig = plt.figure(figsize=(16, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, bars)
    plot_atr(ax, bars)

    line_x0 = mdates.date2num(trade.line_start_date)
    line_x1 = mdates.date2num(trade.line_end_date)
    ax.hlines(trade.line_level, line_x0, line_x1, color=GREEN, linewidth=1.45, linestyle=':', alpha=0.95, zorder=7)
    ax.hlines(trade.target, mdates.date2num(trade.fill_date), mdates.date2num(trade.exit_date), color=BLUE, linewidth=1.0, linestyle='--', alpha=0.8, zorder=6)
    ax.hlines(trade.stop, mdates.date2num(trade.fill_date), mdates.date2num(trade.exit_date), color=RED, linewidth=1.0, linestyle='--', alpha=0.8, zorder=6)
    ax.hlines(trade.entry_price, mdates.date2num(trade.order_live_date), mdates.date2num(trade.fill_date), color=YELLOW, linewidth=1.0, linestyle='-', alpha=0.9, zorder=6)

    ax.scatter([mdates.date2num(trade.signal_date)], [trade.line_level], marker='v', s=86, color=YELLOW, edgecolor='black', linewidth=0.7, zorder=10, label='signal')
    ax.scatter([mdates.date2num(trade.fill_date)], [trade.entry_price], marker='v', s=112, color=PURPLE, edgecolor='black', linewidth=0.8, zorder=11, label='short fill')
    ax.scatter([mdates.date2num(trade.exit_date)], [trade.exit_price], marker='X', s=96, color=RED if trade.net_pts <= 0 else BLUE, edgecolor='black', linewidth=0.8, zorder=12, label='exit')

    dates = pd.to_datetime(bars['date'])
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=2), dates.iloc[-1] + pd.Timedelta(days=2))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.set_title(
        f'{market} lingering bullish ATR stop short #{trade.trade_id} · {trade.result} · '
        f'{trade.net_pts:+.1f} pts (${trade.net_pts * point_value:+,.0f}) · {trade.exit_reason}',
        color='white',
        fontsize=10,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    legend = ax.legend(
        handles=[
            Line2D([0], [0], color=CYAN, lw=1.1, label='ATR bullish stop'),
            Line2D([0], [0], color=ORANGE, lw=1.1, label='ATR bearish stop'),
            Line2D([0], [0], color=GREEN, lw=1.5, linestyle=':', label='lingering bullish stop'),
            Line2D([0], [0], color=BLUE, lw=1.0, linestyle='--', label='100pt target'),
            Line2D([0], [0], color=RED, lw=1.0, linestyle='--', label='100pt stop'),
        ],
        loc='upper left',
        fontsize=8,
        framealpha=0.18,
    )
    for text in legend.get_texts():
        text.set_color('white')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return str(out_path)


def write_outputs(
    out_dir: Path,
    market: str,
    point_value: float,
    point_target: float,
    point_stop: float,
    extension_weeks: int,
    work: pd.DataFrame,
    lines: list[LingeringLine],
    trades: list[Trade],
    audit: list[dict],
    charts: bool,
    close_over_line_exit: bool,
    allow_multiple_entries: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if charts and (out_dir / 'charts').exists():
        shutil.rmtree(out_dir / 'charts')
    trades_df = pd.DataFrame(
        [
            {
                'trade_id': t.trade_id,
                'line_id': t.line_id,
                'symbol': t.symbol,
                'line_start_date': t.line_start_date.date().isoformat(),
                'line_end_date': t.line_end_date.date().isoformat(),
                'signal_date': t.signal_date.date().isoformat(),
                'order_live_date': t.order_live_date.date().isoformat(),
                'fill_date': t.fill_date.date().isoformat(),
                'exit_date': t.exit_date.date().isoformat(),
                'entry_price': round(t.entry_price, 2),
                'target': round(t.target, 2),
                'stop': round(t.stop, 2),
                'exit_price': round(t.exit_price, 2),
                'exit_reason': t.exit_reason,
                'result': t.result,
                'net_pts': round(t.net_pts, 2),
                'net_usd': round(t.net_pts * point_value, 2),
                'mae_pts': round(t.mae_pts, 2),
                'mae_usd': round(t.mae_pts * point_value, 2),
                'mfe_pts': round(t.mfe_pts, 2),
                'mfe_usd': round(t.mfe_pts * point_value, 2),
            }
            for t in trades
        ]
    )
    trades_df.to_csv(out_dir / 'trades.csv', index=False)
    pd.DataFrame(audit).to_csv(out_dir / 'audit.csv', index=False)

    chart_rows: list[dict] = []
    if charts:
        for trade in trades:
            folder = 'winners' if trade.net_pts > 0 else 'losers'
            name = f'{trade.trade_id:03d}_{trade.fill_date.date()}_{trade.result.lower()}.png'
            chart_path = out_dir / 'charts' / folder / name
            draw_trade_chart(trade, work, chart_path, market, point_value)
            chart_rows.append(
                {
                    'trade_id': trade.trade_id,
                    'fill_date': trade.fill_date.date().isoformat(),
                    'result': trade.result,
                    'net_pts': round(trade.net_pts, 2),
                    'mae_pts': round(trade.mae_pts, 2),
                    'exit_reason': trade.exit_reason,
                    'chart': f'charts/{folder}/{name}',
                }
            )

    pnl = trades_df['net_pts'] if not trades_df.empty else pd.Series(dtype=float)
    net_pts = float(pnl.sum()) if not pnl.empty else 0.0
    wins = int((pnl > 0).sum()) if not pnl.empty else 0
    losses = int((pnl < 0).sum()) if not pnl.empty else 0
    win_rate = wins / len(pnl) * 100 if len(pnl) else 0.0
    dd_pts = max_drawdown(pnl) if not pnl.empty else 0.0
    pf = profit_factor(pnl) if not pnl.empty else math.nan
    filled_count = len(trades)
    line_count = len(lines)
    audit_df = pd.DataFrame(audit)
    status_counts = audit_df['status'].value_counts().to_dict() if not audit_df.empty else {}

    exit_counts = trades_df['exit_reason'].value_counts().to_dict() if not trades_df.empty else {}
    worst_mae = float(trades_df['mae_pts'].min()) if not trades_df.empty else 0.0
    avg_mae = float(trades_df['mae_pts'].mean()) if not trades_df.empty else 0.0

    lines_out = [
        f'# {market} Lingering Bullish ATR Stop Short Study',
        '',
        'Short-only first pass.',
        '',
        'Rules:',
        f'- Daily ATR Supertrend-style stop: ATR(14) x 3.',
        f'- On bullish-to-bearish ATR flip, extend the prior bullish ATR stop for {extension_weeks} week(s).',
        '- While the ATR trend remains bearish, wait for the first red daily candle that closes below that lingering line.',
        '- After that signal close, place a sell limit at the lingering line on subsequent daily bars.',
        f'- Entry size: 1 contract. Target: {point_target:g} points. Intraday point stop: {point_stop:g} points.',
        '- Multiple entries are allowed inside the same lingering-line window, but only after the prior trade has closed; only one trade can be live at a time.'
        if allow_multiple_entries
        else '- Only one entry attempt is allowed per lingering-line window.',
        '- Also exit at the next daily open after a daily close back above the lingering line.'
        if close_over_line_exit
        else '- No close-over-line exit is used; trades close only at target, point stop, or final dataset close.',
        '- If stop and target are both inside the same daily bar, the model uses stop-first ordering.',
        '- Fill-bar ordering is conservative: if the day opens below the sell limit and only later rallies into the limit, same-day target touches are ignored because the low may have printed before the fill.',
        '',
        'Causality note: no same-day signal fill is allowed. The sell limit becomes live on the session after the signal candle closes.',
        '',
        '## Results',
        '',
        f'Lingering lines found: {line_count}  ·  Filled trades: {filled_count}  ·  Wins: {wins}  ·  Losses: {losses}  ·  Win rate: {win_rate:.1f}%  ·  Profit factor: {pf:.2f}',
        f'Net: {net_pts:+.2f} pts (${net_pts * point_value:+,.0f})',
        f'Closed-trade max DD: {dd_pts:+.2f} pts (${dd_pts * point_value:+,.0f})',
        f'Worst MAE: {worst_mae:+.2f} pts (${worst_mae * point_value:+,.0f})  ·  Avg MAE: {avg_mae:+.2f} pts (${avg_mae * point_value:+,.0f})',
        '',
        '## Audit Status',
        '',
        '| Status | Count |',
        '|---|---:|',
    ]
    for status, count in sorted(status_counts.items()):
        lines_out.append(f'| {status} | {count} |')
    lines_out.extend(['', '## Exit Reasons', '', '| Exit Reason | Count |', '|---|---:|'])
    for reason, count in sorted(exit_counts.items()):
        lines_out.append(f'| {reason} | {count} |')
    lines_out.extend(['', '## Charts', '', '| Trade | Fill Date | Result | Net Pts | MAE Pts | Exit | Chart |', '|---:|---|---|---:|---:|---|---|'])
    for row in chart_rows:
        lines_out.append(
            f'| {row["trade_id"]} | {row["fill_date"]} | {row["result"]} | {row["net_pts"]:+.2f} | {row["mae_pts"]:+.2f} | {row["exit_reason"]} | [{Path(row["chart"]).name}]({row["chart"]}) |'
        )
    lines_out.append('')
    (out_dir / 'README.md').write_text('\n'.join(lines_out), encoding='utf-8')

    if charts:
        for folder in ['winners', 'losers']:
            sub = [row for row in chart_rows if f'charts/{folder}/' in row['chart']]
            idx_lines = [
                f'# {market} lingering ATR short {folder}',
                '',
                '| Trade | Fill Date | Result | Net Pts | MAE Pts | Exit | Chart |',
                '|---:|---|---|---:|---:|---|---|',
            ]
            for row in sub:
                idx_lines.append(
                    f'| {row["trade_id"]} | {row["fill_date"]} | {row["result"]} | {row["net_pts"]:+.2f} | {row["mae_pts"]:+.2f} | {row["exit_reason"]} | [{Path(row["chart"]).name}]({Path(row["chart"]).name}) |'
                )
            idx_dir = out_dir / 'charts' / folder
            idx_dir.mkdir(parents=True, exist_ok=True)
            (idx_dir / 'INDEX.md').write_text('\n'.join(idx_lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument('--atr-length', type=int, default=14)
    ap.add_argument('--atr-multiplier', type=float, default=3.0)
    ap.add_argument('--extension-weeks', type=int, default=3)
    ap.add_argument('--target-pts', type=float, default=100.0)
    ap.add_argument('--stop-pts', type=float, default=100.0)
    ap.add_argument('--allow-multiple-entries', action='store_true')
    ap.add_argument(
        '--no-close-over-line-exit',
        action='store_true',
        help='Disable the next-open close-over-lingering-line exit and use only target/point stop/period close.',
    )
    ap.add_argument('--no-charts', action='store_true')
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    work, lines, trades, audit = simulate(
        daily=daily,
        point_target=args.target_pts,
        point_stop=args.stop_pts,
        point_value=args.point_value,
        atr_length=args.atr_length,
        atr_multiplier=args.atr_multiplier,
        extension_weeks=args.extension_weeks,
        close_over_line_exit=not args.no_close_over_line_exit,
        allow_multiple_entries=args.allow_multiple_entries,
    )
    write_outputs(
        out_dir=args.out,
        market=args.market.upper(),
        point_value=args.point_value,
        point_target=args.target_pts,
        point_stop=args.stop_pts,
        extension_weeks=args.extension_weeks,
        work=work,
        lines=lines,
        trades=trades,
        audit=audit,
        charts=not args.no_charts,
        close_over_line_exit=not args.no_close_over_line_exit,
        allow_multiple_entries=args.allow_multiple_entries,
    )
    print(f'Wrote {args.out / "README.md"}')
    print(f'Trades: {len(trades)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
