#!/usr/bin/env python3
"""Yearly ORB variant with prior confirmed swing stops and unlimited trades.

Rules:
- Yearly opening range is Jan-Mar.
- Trades are searched from Apr-Dec.
- A daily close above/below the range arms a boundary retest entry.
- Long entry is the range high; short entry is the range low.
- Long stop is the most recent confirmed daily swing low below entry.
- Short stop is the most recent confirmed daily swing high above entry.
- Target is still one opening-range extension.
- Trades are unlimited within the year.

Swing confirmation is causal on daily bars: a pivot at bar ``i`` is known only
after bar ``i + 1`` has closed. The fill/exit ordering remains daily-OHLC
research style and uses stop-first ordering when stop and target are both
inside the same daily bar.
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


WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2


@dataclass(frozen=True)
class SwingPoint:
    kind: str
    value: float
    pivot_idx: int
    confirm_idx: int
    pivot_date: pd.Timestamp


@dataclass
class ChartTrade:
    period: str
    direction: str
    entry: float
    exit_price: float
    target: float
    stop: float
    stop_source_date: pd.Timestamp
    stop_source_price: float
    pl: float
    result: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    mae_pts: float
    mfe_pts: float
    drawdown_pct: float


def build_swings(bars: pd.DataFrame) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    lows = bars['low'].astype(float).tolist()
    highs = bars['high'].astype(float).tolist()
    dates = pd.to_datetime(bars['date']).tolist()
    for i in range(1, len(bars) - 1):
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            swings.append(SwingPoint('low', lows[i], i, i + 1, pd.Timestamp(dates[i])))
        if highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            swings.append(SwingPoint('high', highs[i], i, i + 1, pd.Timestamp(dates[i])))
    return swings


def latest_valid_swing(
    swings: list[SwingPoint],
    direction: str,
    entry: float,
    current_idx: int,
) -> Optional[SwingPoint]:
    kind = 'low' if direction == 'Long' else 'high'
    for swing in reversed(swings):
        if swing.kind != kind or swing.confirm_idx >= current_idx:
            continue
        if direction == 'Long' and swing.value < entry:
            return swing
        if direction == 'Short' and swing.value > entry:
            return swing
    return None


def update_excursion(
    direction: str,
    entry: float,
    high: float,
    low: float,
    mae_pts: float,
    mfe_pts: float,
) -> tuple[float, float]:
    if direction == 'Long':
        mae_pts = max(mae_pts, max(0.0, entry - low))
        mfe_pts = max(mfe_pts, max(0.0, high - entry))
    else:
        mae_pts = max(mae_pts, max(0.0, high - entry))
        mfe_pts = max(mfe_pts, max(0.0, entry - low))
    return mae_pts, mfe_pts


def simulate_year(period: str, bars: pd.DataFrame) -> tuple[list[ChartTrade], dict]:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    range_bars = work[work['month'] <= 3].copy()
    trade_bars = work[work['month'] > 3].copy()
    symbol = str(work.iloc[0]['symbol'])
    meta = {
        'period': period,
        'symbol': symbol,
        'range_days': len(range_bars),
        'trade_days': len(trade_bars),
    }
    if range_bars.empty or trade_bars.empty:
        return [], meta

    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    meta.update({'range_high': range_high, 'range_low': range_low, 'range': range_val})
    if range_val <= 0:
        return [], meta

    swings = build_swings(work)
    phase = WAIT_BREAKOUT
    direction: Optional[str] = None
    entry = target = stop = None
    stop_swing: Optional[SwingPoint] = None
    entry_date: Optional[pd.Timestamp] = None
    mae_pts = mfe_pts = 0.0
    trades: list[ChartTrade] = []

    for idx, bar in work.iterrows():
        if int(bar['month']) <= 3:
            continue

        h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])
        d = pd.Timestamp(bar['date'])

        if phase == WAIT_FILL:
            filled = False
            if direction == 'Long' and l <= range_high:
                candidate_entry = range_high
                candidate_stop_swing = latest_valid_swing(swings, 'Long', candidate_entry, idx)
                if candidate_stop_swing is not None:
                    entry = candidate_entry
                    target = range_high + range_val
                    stop = candidate_stop_swing.value
                    stop_swing = candidate_stop_swing
                    entry_date = d
                    filled = True
            elif direction == 'Short' and h >= range_low:
                candidate_entry = range_low
                candidate_stop_swing = latest_valid_swing(swings, 'Short', candidate_entry, idx)
                if candidate_stop_swing is not None:
                    entry = candidate_entry
                    target = range_low - range_val
                    stop = candidate_stop_swing.value
                    stop_swing = candidate_stop_swing
                    entry_date = d
                    filled = True

            if filled:
                phase = IN_TRADE
                mae_pts = mfe_pts = 0.0
            else:
                if direction == 'Long' and c < range_low:
                    direction = 'Short'
                elif direction == 'Short' and c > range_high:
                    direction = 'Long'

        if phase == IN_TRADE:
            assert direction is not None
            assert entry is not None and target is not None and stop is not None
            assert stop_swing is not None and entry_date is not None
            mae_pts, mfe_pts = update_excursion(direction, entry, h, l, mae_pts, mfe_pts)
            risk = abs(entry - stop)
            if direction == 'Long':
                if l <= stop:
                    trades.append(
                        ChartTrade(
                            period,
                            direction,
                            entry,
                            stop,
                            target,
                            stop,
                            stop_swing.pivot_date,
                            stop_swing.value,
                            stop - entry,
                            'Loss',
                            entry_date,
                            d,
                            mae_pts,
                            mfe_pts,
                            round(mae_pts / risk * 100, 2) if risk else 0.0,
                        )
                    )
                    phase, direction = WAIT_BREAKOUT, None
                elif h >= target:
                    trades.append(
                        ChartTrade(
                            period,
                            direction,
                            entry,
                            target,
                            target,
                            stop,
                            stop_swing.pivot_date,
                            stop_swing.value,
                            target - entry,
                            'Win',
                            entry_date,
                            d,
                            mae_pts,
                            mfe_pts,
                            round(mae_pts / risk * 100, 2) if risk else 0.0,
                        )
                    )
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    continue
            else:
                if h >= stop:
                    trades.append(
                        ChartTrade(
                            period,
                            direction,
                            entry,
                            stop,
                            target,
                            stop,
                            stop_swing.pivot_date,
                            stop_swing.value,
                            entry - stop,
                            'Loss',
                            entry_date,
                            d,
                            mae_pts,
                            mfe_pts,
                            round(mae_pts / risk * 100, 2) if risk else 0.0,
                        )
                    )
                    phase, direction = WAIT_BREAKOUT, None
                elif l <= target:
                    trades.append(
                        ChartTrade(
                            period,
                            direction,
                            entry,
                            target,
                            target,
                            stop,
                            stop_swing.pivot_date,
                            stop_swing.value,
                            entry - target,
                            'Win',
                            entry_date,
                            d,
                            mae_pts,
                            mfe_pts,
                            round(mae_pts / risk * 100, 2) if risk else 0.0,
                        )
                    )
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    continue

        if phase == WAIT_BREAKOUT:
            if c > range_high:
                candidate_stop_swing = latest_valid_swing(swings, 'Long', range_high, idx)
                if candidate_stop_swing is None:
                    continue
                direction = 'Long'
                if l <= range_high:
                    entry = range_high
                    target = range_high + range_val
                    stop = candidate_stop_swing.value
                    stop_swing = candidate_stop_swing
                    entry_date = d
                    phase = IN_TRADE
                    mae_pts = mfe_pts = 0.0
                    continue
                phase = WAIT_FILL
            elif c < range_low:
                candidate_stop_swing = latest_valid_swing(swings, 'Short', range_low, idx)
                if candidate_stop_swing is None:
                    continue
                direction = 'Short'
                if h >= range_low:
                    entry = range_low
                    target = range_low - range_val
                    stop = candidate_stop_swing.value
                    stop_swing = candidate_stop_swing
                    entry_date = d
                    phase = IN_TRADE
                    mae_pts = mfe_pts = 0.0
                    continue
                phase = WAIT_FILL

    if phase == IN_TRADE and not trade_bars.empty:
        assert direction is not None
        assert entry is not None and target is not None and stop is not None
        assert stop_swing is not None and entry_date is not None
        last = trade_bars.iloc[-1]
        exit_price = float(last['close'])
        exit_date = pd.Timestamp(last['date'])
        pl = exit_price - entry if direction == 'Long' else entry - exit_price
        risk = abs(entry - stop)
        trades.append(
            ChartTrade(
                period,
                direction,
                entry,
                exit_price,
                target,
                stop,
                stop_swing.pivot_date,
                stop_swing.value,
                pl,
                'Period-Close',
                entry_date,
                exit_date,
                mae_pts,
                mfe_pts,
                round(mae_pts / risk * 100, 2) if risk else 0.0,
            )
        )

    return trades, meta


def result_tag(result: str, pl: float) -> str:
    if result == 'Win' or (result == 'Period-Close' and pl > 0):
        return 'Win'
    if result == 'Loss' or (result == 'Period-Close' and pl < 0):
        return 'Loss'
    return 'No-Op'


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def trade_rows(trades: list[ChartTrade], meta: dict) -> list[dict]:
    rows: list[dict] = []
    cumulative = 0.0
    if not trades:
        return [
            {
                'Period': meta['period'],
                'Range_High': meta.get('range_high'),
                'Range_Low': meta.get('range_low'),
                'Range': meta.get('range'),
                'Trade_Direction': 'No-Op',
                'Entry_Date': None,
                'Exit_Date': None,
                'Entry_Price': None,
                'Exit_Price': None,
                'Target': None,
                'Stop': None,
                'Stop_Source_Date': None,
                'Stop_Source_Price': None,
                'Trade_PL': 0.0,
                'MAE_Pts': 0.0,
                'MFE_Pts': 0.0,
                'Drawdown_Pct': 0.0,
                'Result': 'No-Op',
                'Symbol': meta['symbol'],
                'Range_Days': meta['range_days'],
                'Trade_Days': meta['trade_days'],
                'Cumulative_PL': cumulative,
            }
        ]

    for tr in trades:
        cumulative += tr.pl
        rows.append(
            {
                'Period': tr.period,
                'Range_High': meta.get('range_high'),
                'Range_Low': meta.get('range_low'),
                'Range': meta.get('range'),
                'Trade_Direction': tr.direction,
                'Entry_Date': tr.entry_date.date().isoformat(),
                'Exit_Date': tr.exit_date.date().isoformat(),
                'Entry_Price': tr.entry,
                'Exit_Price': tr.exit_price,
                'Target': tr.target,
                'Stop': tr.stop,
                'Stop_Source_Date': tr.stop_source_date.date().isoformat(),
                'Stop_Source_Price': tr.stop_source_price,
                'Trade_PL': round(tr.pl, 6),
                'MAE_Pts': round(tr.mae_pts, 6),
                'MFE_Pts': round(tr.mfe_pts, 6),
                'Drawdown_Pct': tr.drawdown_pct,
                'Result': tr.result,
                'Symbol': meta['symbol'],
                'Range_Days': meta['range_days'],
                'Trade_Days': meta['trade_days'],
                'Cumulative_PL': round(cumulative, 6),
            }
        )
    return rows


def draw_year(
    period: str,
    bars: pd.DataFrame,
    trades: list[ChartTrade],
    meta: dict,
    out_path: Path,
    market: str,
    point_value: float,
) -> dict:
    work = bars.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['month'] = work['date'].dt.month
    range_bars = work[work['month'] <= 3]
    dates = pd.to_datetime(work['date'])
    xnums = mdates.date2num(dates)

    fig = plt.figure(figsize=(18, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    width = 0.72
    for x, (_, row) in zip(xnums, work.iterrows()):
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

    if not range_bars.empty:
        ax.axvspan(
            pd.Timestamp(range_bars.iloc[0]['date']),
            pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1),
            color='#1F4E79',
            alpha=0.28,
            zorder=0,
        )
    rh = float(meta.get('range_high', 0.0) or 0.0)
    rl = float(meta.get('range_low', 0.0) or 0.0)
    rv = float(meta.get('range', 0.0) or 0.0)
    if rv > 0:
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'Period-Close': '#FFB74D'}
    total_pl = sum(t.pl for t in trades)
    pattern = '+'.join(f'{t.direction[0]}{t.result[0]}' for t in trades) if trades else 'No-Op'
    label_offsets = [20, -28, 38, -46, 56, -64]
    for i, tr in enumerate(trades, 1):
        x_e = mdates.date2num(tr.entry_date)
        x_x = mdates.date2num(tr.exit_date)
        x_s = mdates.date2num(tr.stop_source_date)
        ax.scatter([x_s], [tr.stop_source_price], marker='o', color='#64B5F6', s=55, zorder=9, edgecolor='black', linewidth=0.8)
        ax.scatter(
            [x_e],
            [tr.entry],
            marker='^' if tr.direction == 'Long' else 'v',
            color='#FFC107',
            s=105,
            zorder=10,
            edgecolor='black',
            linewidth=1.0,
        )
        ax.plot([x_e, x_x], [tr.target, tr.target], color='#76FF03', linewidth=0.75, alpha=0.55, zorder=4)
        ax.plot([x_e, x_x], [tr.stop, tr.stop], color='#FF1744', linewidth=0.75, alpha=0.55, zorder=4)
        exit_color = color_for.get(tr.result, '#FFB74D')
        ax.scatter([x_x], [tr.exit_price], marker='X', color=exit_color, s=105, zorder=10, edgecolor='black', linewidth=1.0)
        ax.annotate(
            f'#{i} {tr.direction[0]} {tr.pl:+.0f}',
            xy=(x_x, tr.exit_price),
            xytext=(7, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=exit_color,
            fontsize=7,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.18', fc='#0D1B2A', ec=exit_color, alpha=0.92),
        )

    if rv > 0:
        last_x = xnums[-1] + 2.0
        ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=8, va='center')
        ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=8, va='center')

    title = (
        f'{period} {market} YEARLY ORB SWING STOP · Jan-Mar · unlimited trades · '
        f'Range {rv:.1f} · {len(trades)} trades · {total_pl:+.1f}pt '
        f'(${total_pl * point_value:+,.0f})'
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
        'symbol': meta['symbol'],
        'range_days': meta['range_days'],
        'trade_days': meta['trade_days'],
        'range': round(rv, 2),
        'pattern': pattern,
        'trades': len(trades),
        'net_pts': round(total_pl, 2),
        'net_usd': round(total_pl * point_value, 2),
        'chart': f'{period}/{period}.png',
    }


def write_indexes(out_root: Path, market: str, point_value: float, chart_rows: list[dict], result_df: pd.DataFrame) -> None:
    trades = result_df[result_df['Trade_Direction'] != 'No-Op'].copy()
    if not trades.empty:
        tags = trades.apply(lambda r: result_tag(str(r['Result']), float(r['Trade_PL'])), axis=1)
        wins = int((tags == 'Win').sum())
        losses = int((tags == 'Loss').sum())
        total_pts = float(trades['Trade_PL'].sum())
        max_dd_pts = max_dd(trades['Trade_PL'])
        avg_mae_pts = float(trades['MAE_Pts'].mean())
        max_mae_pts = float(trades['MAE_Pts'].max())
        win_rate = wins / len(trades) * 100
    else:
        wins = losses = 0
        total_pts = max_dd_pts = avg_mae_pts = max_mae_pts = win_rate = 0.0

    for row in sorted(chart_rows, key=lambda x: x['period']):
        idx = out_root / row['period'] / 'INDEX.md'
        idx.write_text(
            '\n'.join(
                [
                    f'# {row["period"]} {market} yearly ORB swing-stop chart',
                    '',
                    f'Symbol: {row["symbol"]}  ·  Range days: {row["range_days"]}  ·  Trade days: {row["trade_days"]}',
                    f'Net: {row["net_pts"]:+.2f} pts (${row["net_usd"]:+,.0f} / 1 {market} gross)',
                    '',
                    '| Period | Symbol | Range | Pattern | Trades | Net pts | Chart |',
                    '|---|---|---:|---|---:|---:|---|',
                    f'| {row["period"]} | {row["symbol"]} | {row["range"]:.2f} | {row["pattern"]} | {row["trades"]} | {row["net_pts"]:+.2f} | [{row["period"]}.png]({row["period"]}.png) |',
                    '',
                ]
            ),
            encoding='utf-8',
        )

    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                f'# {market} yearly ORB swing-stop unlimited charts',
                '',
                'Variant rules: Jan-Mar defines the yearly ORB; Apr-Dec trades range-boundary retests after daily closes outside the ORB; long stops use the latest confirmed daily swing low below entry, short stops use the latest confirmed daily swing high above entry; trades are unlimited per year.',
                '',
                f'Trades: {len(trades)}  ·  Wins: {wins}  ·  Losses: {losses}  ·  Win rate: {win_rate:.1f}%',
                f'Net: {total_pts:+.2f} pts (${total_pts * point_value:+,.0f} / 1 {market} gross)  ·  Max DD: {max_dd_pts:+.2f} pts (${max_dd_pts * point_value:+,.0f})',
                f'Avg MAE: {avg_mae_pts:.2f} pts (${avg_mae_pts * point_value:,.0f})  ·  Worst MAE: {max_mae_pts:.2f} pts (${max_mae_pts * point_value:,.0f})',
                '',
                '| Year | Symbol | Range Days | Trade Days | Range | Pattern | Trades | Net pts | Folder |',
                '|---:|---|---:|---:|---:|---|---:|---:|---|',
                *[
                    f'| {r["period"]} | {r["symbol"]} | {r["range_days"]} | {r["trade_days"]} | {r["range"]:.2f} | {r["pattern"]} | {r["trades"]} | {r["net_pts"]:+.2f} | [{r["period"]}/]({r["period"]}/INDEX.md) |'
                    for r in sorted(chart_rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def run(args: argparse.Namespace) -> pd.DataFrame:
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    if args.start:
        daily = daily[daily['date'] >= pd.Timestamp(args.start)]
    if args.end:
        daily = daily[daily['date'] <= pd.Timestamp(args.end)]

    daily = daily.copy()
    daily['date'] = pd.to_datetime(daily['date'])
    daily['year'] = daily['date'].dt.year
    all_rows: list[dict] = []
    chart_rows: list[dict] = []

    for year, bars in daily.groupby('year', sort=True):
        bars = bars.sort_values('date').reset_index(drop=True)
        months = bars['date'].dt.month
        if not (months <= 3).any() or not (months > 3).any():
            continue
        period = str(int(year))
        trades, meta = simulate_year(period, bars)
        all_rows.extend(trade_rows(trades, meta))
        chart_row = draw_year(
            period,
            bars,
            trades,
            meta,
            args.out / period / f'{period}.png',
            args.market.upper(),
            args.point_value,
        )
        chart_rows.append(chart_row)
        print(f'{chart_row["chart"]} trades={chart_row["trades"]} net={chart_row["net_pts"]:+.2f}pt')

    result_df = pd.DataFrame(all_rows)
    if not result_df.empty:
        result_df['Cumulative_PL'] = result_df['Trade_PL'].astype(float).cumsum().round(6)
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_csv(args.export_csv, index=False)
    write_indexes(args.out, args.market.upper(), args.point_value, chart_rows, result_df)
    print(f'Wrote {args.export_csv}')
    print(f'Wrote {len(chart_rows)} charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    return result_df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--export-csv', type=Path, required=True)
    ap.add_argument('--market', type=str, required=True)
    ap.add_argument('--point-value', type=float, required=True)
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
