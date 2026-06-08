#!/usr/bin/env python3
"""Charts and MAE report for monthly ORB inside-candle-open variants."""
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
NQ_ROOT = POTIONS / 'nq'
OUT_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'inside_candle_open_restricted'


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def fmt_money(value: float) -> str:
    return f'${value:,.2f}'


def fmt_num(value: float) -> str:
    if math.isnan(value):
        return 'n/a'
    return f'{value:,.2f}'


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = values.astype(float).cumsum()
    return float((eq - eq.cummax()).min())


def date_value(bars: pd.DataFrame, d, col: str) -> float | None:
    if pd.isna(d):
        return None
    hit = bars[pd.to_datetime(bars['date']).dt.date == pd.Timestamp(d).date()]
    if hit.empty:
        return None
    return float(hit.iloc[0][col])


def draw_period(period: str, bars: pd.DataFrame, trades: pd.DataFrame, out_path: Path, chart_title: str) -> dict | None:
    chart_trades = trades[(trades['Period'].astype(str) == period) & (trades['Trade_Direction'] != 'No-Op')].copy()
    if chart_trades.empty:
        return None

    range_bars = bars.iloc[:3].copy()
    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low

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
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.10, zorder=0)
    ax.axhline(range_high, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'Range-Close': '#FFB74D', 'Period-Close': '#FFB74D'}
    label_offsets = [22, -34, 46, -58]
    for i, (_, tr) in enumerate(chart_trades.iterrows(), 1):
        direction = str(tr['Trade_Direction'])
        entry = float(tr['Entry_Price'])
        exit_px = float(tr['Exit_Price'])
        target = float(tr['TP_Price'])
        stop = float(tr['Stop_Price'])
        entry_date = pd.Timestamp(tr['Entry_Date'])
        exit_date = pd.Timestamp(tr['Exit_Date'])
        breakout_date = pd.Timestamp(tr['Breakout_Date'])
        source_date = pd.Timestamp(tr['Entry_Source_Date'])
        source_start = pd.Timestamp(tr['Entry_Source_Start'])
        source_end = pd.Timestamp(tr['Entry_Source_End'])
        source_open = float(tr['Entry_Source_Open'])
        source_low = float(tr['Entry_Source_Low'])
        source_high = float(tr['Entry_Source_High'])
        result = str(tr['Result'])
        pl = float(tr['Trade_PL'])

        ax.axvspan(source_start - pd.Timedelta(hours=12), source_end + pd.Timedelta(hours=12), color='#AB47BC', alpha=0.16, zorder=1)
        ax.scatter([mdates.date2num(source_date)], [source_open], marker='D', color='#CE93D8', s=92, zorder=9, edgecolor='black', linewidth=1.0)
        ax.plot(
            [mdates.date2num(source_date) - 0.35, mdates.date2num(source_date) + 0.35],
            [source_low if direction == 'Long' else source_high] * 2,
            color='#CE93D8',
            linewidth=1.0,
            alpha=0.9,
            zorder=8,
        )

        breakout_close = date_value(bars, breakout_date, 'close')
        if breakout_close is not None:
            ax.scatter(
                [mdates.date2num(breakout_date)],
                [breakout_close],
                marker='^' if direction == 'Long' else 'v',
                color='#4FC3F7',
                s=105,
                zorder=9,
                edgecolor='black',
                linewidth=1.0,
            )

        ax.plot([breakout_date, entry_date], [entry, entry], color='#FFC107', linestyle=':', linewidth=1.2, alpha=0.9, zorder=5)
        ax.scatter(
            [mdates.date2num(entry_date)],
            [entry],
            marker='^' if direction == 'Long' else 'v',
            color='#FFC107',
            s=140,
            zorder=10,
            edgecolor='black',
            linewidth=1.2,
        )
        ax.plot([entry_date, exit_date], [target, target], color='#76FF03', linewidth=0.95, alpha=0.70, zorder=4)
        ax.plot([entry_date, exit_date], [stop, stop], color='#FF1744', linewidth=0.95, alpha=0.70, zorder=4)

        exit_color = color_for.get(result, '#FFB74D')
        ax.scatter([mdates.date2num(exit_date)], [exit_px], marker='X', color=exit_color, s=140, zorder=10, edgecolor='black', linewidth=1.2)
        ax.annotate(
            f'#{i} {direction[0]} {result} {pl:+.0f}pt',
            xy=(mdates.date2num(exit_date), exit_px),
            xytext=(8, -label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=exit_color,
            fontsize=8,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=exit_color, alpha=0.95),
        )
        ax.annotate(
            f'#{i} src open {source_open:.1f}',
            xy=(mdates.date2num(source_date), source_open),
            xytext=(8, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color='#CE93D8',
            fontsize=7,
            fontweight='bold',
            ha='left',
            bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec='#CE93D8', alpha=0.95),
        )

    last_x = xnums[-1] + 0.4
    ax.text(last_x, range_high, f' RH {range_high:.1f}', color='#E0E0E0', fontsize=7, va='center')
    ax.text(last_x, range_low, f' RL {range_low:.1f}', color='#E0E0E0', fontsize=7, va='center')
    sym = str(bars.iloc[0]['symbol'])
    total_pl = float(chart_trades['Trade_PL'].sum())
    title = (
        f'{period}  {chart_title}  ·  {sym}  ·  '
        f'Range {range_val:.1f}  ·  {len(chart_trades)} trade(s)  ·  {total_pl:+.1f}pt (${total_pl * 2:+.0f})'
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


def mae_rows(daily: pd.DataFrame, trades: pd.DataFrame, instrument: str, multiplier: float) -> pd.DataFrame:
    work_daily = daily.copy()
    work_daily['date_key'] = pd.to_datetime(work_daily['date']).dt.date.astype(str)
    rows = []
    trade_rows = trades[(trades['Trade_Direction'] != 'No-Op') & (trades['Trade_PL'].astype(float) > 0)].copy()
    for _, tr in trade_rows.iterrows():
        entry_date = str(pd.Timestamp(tr['Entry_Date']).date())
        exit_date = str(pd.Timestamp(tr['Exit_Date']).date())
        window = work_daily[(work_daily['date_key'] >= entry_date) & (work_daily['date_key'] <= exit_date)]
        if window.empty:
            continue
        direction = str(tr['Trade_Direction'])
        entry = float(tr['Entry_Price'])
        source_low = float(tr['Entry_Source_Low'])
        source_high = float(tr['Entry_Source_High'])
        if direction == 'Long':
            worst = float(window['low'].min())
            normal_mae = max(0.0, entry - worst)
            source_cushion = max(0.0, entry - source_low)
            beyond_source = max(0.0, source_low - worst)
            signed_to_source = worst - source_low
        else:
            worst = float(window['high'].max())
            normal_mae = max(0.0, worst - entry)
            source_cushion = max(0.0, source_high - entry)
            beyond_source = max(0.0, worst - source_high)
            signed_to_source = source_high - worst

        rows.append({
            'Instrument': instrument,
            'Period': tr['Period'],
            'Direction': direction,
            'Result': tr['Result'],
            'Net_Pts': float(tr['Trade_PL']),
            'Net_$': float(tr['Trade_PL']) * multiplier,
            'Entry_Date': tr['Entry_Date'],
            'Exit_Date': tr['Exit_Date'],
            'Entry_Price': entry,
            'Source_Date': tr['Entry_Source_Date'],
            'Source_Open': float(tr['Entry_Source_Open']),
            'Source_High': source_high,
            'Source_Low': source_low,
            'Source_Cushion_Pts': source_cushion,
            'Normal_MAE_Pts': normal_mae,
            'MAE_Beyond_Source_Extreme_Pts': beyond_source,
            'Worst_Price': worst,
            'Signed_Worst_To_Source_Extreme_Pts': signed_to_source,
        })
    return pd.DataFrame(rows)


def summarize_mae(rows: pd.DataFrame) -> list[str]:
    lines = [
        '| Instrument | Group | Winners | Net | Avg normal MAE | Median normal MAE | Avg source cushion | Avg beyond source extreme | Median beyond | Max beyond | No source violation |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for instrument, sub in rows.groupby('Instrument', sort=True):
        for group_name, group in [('All', sub), ('Long', sub[sub['Direction'] == 'Long']), ('Short', sub[sub['Direction'] == 'Short'])]:
            if group.empty:
                continue
            no_violation = float((group['MAE_Beyond_Source_Extreme_Pts'] == 0).mean())
            lines.append(
                f"| {instrument} | {group_name} | {len(group)} | {fmt_money(group['Net_$'].sum())} | "
                f"{fmt_num(group['Normal_MAE_Pts'].mean())} | {fmt_num(group['Normal_MAE_Pts'].median())} | "
                f"{fmt_num(group['Source_Cushion_Pts'].mean())} | {fmt_num(group['MAE_Beyond_Source_Extreme_Pts'].mean())} | "
                f"{fmt_num(group['MAE_Beyond_Source_Extreme_Pts'].median())} | {fmt_num(group['MAE_Beyond_Source_Extreme_Pts'].max())} | "
                f"{no_violation:.1%} |"
            )
    return lines


def write_index(out_root: Path, chart_rows: list[dict], mae: pd.DataFrame, variant_label: str, candidate_note: str) -> None:
    by_year: dict[int, list[dict]] = {}
    for row in chart_rows:
        by_year.setdefault(int(row['year']), []).append(row)

    for year, yr_rows in sorted(by_year.items()):
        idx = out_root / str(year) / 'INDEX.md'
        idx.write_text(
            '\n'.join(
                [
                    f'# {year} {variant_label} charts',
                    '',
                    '| Period | Symbol | Trades | Net pts | Chart |',
                    '|---|---|---:|---:|---|',
                    *[
                        f"| {r['period']} | {r['symbol']} | {r['trades']} | {r['net_pts']:+.2f} | [{r['period']}.png]({r['period']}.png) |"
                        for r in sorted(yr_rows, key=lambda x: x['period'])
                    ],
                    '',
                ]
            ),
            encoding='utf-8',
        )

    total = sum(r['net_pts'] for r in chart_rows)
    out_root.joinpath('INDEX.md').write_text(
        '\n'.join(
            [
                f'# MNQ {variant_label} Charts',
                '',
                *([candidate_note, ''] if candidate_note else []),
                f'Periods charted: {len(chart_rows)}  ·  Net on charted periods: {total:+.2f} pts (${total * 2:+,.0f} / 1 MNQ gross)',
                '',
                'Purple diamond/region = selected fully-inside opposite candle/run. Blue triangle = breakout close. Gold triangle/line = live limit fill.',
                '',
                '## Winner MAE Summary',
                '',
                *summarize_mae(mae),
                '',
                '## All Periods',
                '',
                '| Period | Symbol | Trades | Net pts | Chart |',
                '|---|---|---:|---:|---|',
                *[
                    f"| {r['period']} | {r['symbol']} | {r['trades']} | {r['net_pts']:+.2f} | [{r['chart']}]({r['chart']}) |"
                    for r in sorted(chart_rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def write_mae_report(out_root: Path, mae: pd.DataFrame, variant_label: str, mae_stem: str) -> Path:
    mae_csv = out_root / f'{mae_stem}_mae.csv'
    mae_md = out_root / f'{mae_stem.upper()}_MAE.md'
    mae.to_csv(mae_csv, index=False)
    mae_md.write_text(
        '\n'.join(
            [
                f'# {variant_label} Winner MAE',
                '',
                'Rows are profitable trades only. For longs, source extreme means the selected inside candle low. For shorts, source extreme means the selected inside candle high.',
                '',
                '- `Normal_MAE_Pts`: adverse excursion from entry after fill, using daily OHLC.',
                '- `Source_Cushion_Pts`: distance from entry open to selected source candle low/high.',
                '- `MAE_Beyond_Source_Extreme_Pts`: amount price moved beyond the selected source candle low/high after fill. Zero means the selected source extreme held.',
                '',
                *summarize_mae(mae),
                '',
                f'Detail CSV: [{mae_csv.name}]({mae_csv.name})',
                '',
            ]
        ),
        encoding='utf-8',
    )
    return mae_md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mnq-daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--mnq-trades', type=Path, default=MNQ_ROOT / 'mnq_monthly_orb_inside_candle_open_restricted.csv')
    ap.add_argument('--nq-daily', type=Path, default=NQ_ROOT / 'nq_daily.csv')
    ap.add_argument('--nq-trades', type=Path, default=NQ_ROOT / 'nq_monthly_orb_inside_candle_open_restricted.csv')
    ap.add_argument('--out', type=Path, default=OUT_ROOT)
    ap.add_argument('--variant-label', default='Inside-Candle-Open Restricted')
    ap.add_argument('--chart-title', default=None)
    ap.add_argument('--candidate-note', default='**Primary candidate flag:** this is the current best scaling candidate among causal monthly ORB standalone variants by drawdown and profit factor.')
    ap.add_argument('--mae-stem', default='inside_candle_open_restricted')
    args = ap.parse_args()
    chart_title = args.chart_title or args.variant_label.upper()

    mnq_daily = pd.read_csv(args.mnq_daily, parse_dates=['date'])
    mnq_trades = pd.read_csv(args.mnq_trades)
    nq_daily = pd.read_csv(args.nq_daily, parse_dates=['date'])
    nq_trades = pd.read_csv(args.nq_trades)

    chart_rows = []
    for period, bars in period_groups(mnq_daily):
        out_path = args.out / period[:4] / f'{period}.png'
        row = draw_period(period, bars, mnq_trades, out_path, chart_title)
        if row:
            chart_rows.append(row)
            print(f'{row["chart"]} {row["net_pts"]:+.2f}pt')

    mae = pd.concat(
        [
            mae_rows(mnq_daily, mnq_trades, 'MNQ', 2.0),
            mae_rows(nq_daily, nq_trades, 'NQ', 20.0),
        ],
        ignore_index=True,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    write_index(args.out, chart_rows, mae, args.variant_label, args.candidate_note)
    mae_md = write_mae_report(args.out, mae, args.variant_label, args.mae_stem)
    print(f'Wrote {len(chart_rows)} charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    print(f'Wrote {mae_md}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
