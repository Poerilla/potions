#!/usr/bin/env python3
"""One chart per calendar quarter: three months of daily candles on one axis.

All bars use the **same** price (y) and time (x) scales. Each month gets its own
opening range from the first three sessions (rh/rl), shown as a tinted band
spanning that month’s trading days so the three ORBs are visually comparable.

Trades from ``mnq_monthly_orb_restricted.csv`` for the three ``YYYY-MM``
periods are drawn on the same timeline.

Output: ``quarterly_panels/<YYYY>-Q<q>.png`` plus ``quarterly_panels/INDEX.md``.

Example:
  python mnq/case_studies/monthly_orb/build_quarterly_panel_charts.py
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

MNQ_ROOT = Path(__file__).resolve().parents[2]
OR_LEN = 3

# Month 1 / 2 / 3 of the quarter (distinct OR bands)
ORB_COLORS = ('#1B4965', '#5C4D7D', '#B08900')
ORB_FORMATION_ALPHA = 0.38
ORB_BAND_ALPHA = 0.16


def draw_candles(ax, dates, opens, highs, lows, closes) -> None:
    xnums = mdates.date2num(dates)
    width = 0.55
    for x, o, h, l, c in zip(xnums, opens, highs, lows, closes):
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.75, zorder=3)
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


def annotate_trades(ax, chart_trades: pd.DataFrame, color_for: dict) -> None:
    label_offsets = [14, -22, 30, -38, 46, -54]
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
        x_e = mdates.date2num(entry_date)
        x_x = mdates.date2num(exit_date)
        ax.scatter(
            [x_e],
            [entry],
            marker='^' if direction == 'Long' else 'v',
            color='#FFC107',
            s=90,
            zorder=10,
            edgecolor='black',
            linewidth=0.9,
        )
        ax.plot([x_e, x_x], [target, target], color='#76FF03', linewidth=0.65, alpha=0.55, zorder=4)
        ax.plot([x_e, x_x], [stop, stop], color='#FF1744', linewidth=0.65, alpha=0.55, zorder=4)
        exit_color = color_for.get(result, '#FFB74D')
        ax.scatter([x_x], [exit_px], marker='X', color=exit_color, s=90, zorder=10, edgecolor='black', linewidth=0.8)
        ax.annotate(
            f'#{i} {pl:+.0f}',
            xy=(x_x, exit_px),
            xytext=(6, label_offsets[(i - 1) % len(label_offsets)]),
            textcoords='offset points',
            color=exit_color,
            fontsize=7,
            fontweight='bold',
            ha='left',
        )


def month_daily(daily: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    return daily[(daily['date'].dt.year == year) & (daily['date'].dt.month == month)].copy()


def draw_quarter_single_scale(
    ax,
    year: int,
    months: list[int],
    daily: pd.DataFrame,
    trades: pd.DataFrame,
) -> None:
    ax.set_facecolor('#0D1B2A')
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    quarter_frames: list[pd.DataFrame] = []
    y_ext: list[float] = []

    for idx, mo in enumerate(months):
        mdf = month_daily(daily, year, mo).sort_values('date').reset_index(drop=True)
        if mdf.empty:
            continue
        quarter_frames.append(mdf)
        if len(mdf) >= OR_LEN:
            rb = mdf.iloc[:OR_LEN]
            rh = float(rb['high'].max())
            rl = float(rb['low'].min())
            rv = rh - rl
            d_first = pd.Timestamp(mdf.iloc[0]['date'])
            d_last = pd.Timestamp(mdf.iloc[-1]['date'])
            y_ext.extend([rh, rl, float(mdf['high'].max()), float(mdf['low'].min())])
            if rv > 0:
                rs = pd.Timestamp(rb.iloc[0]['date'])
                re = pd.Timestamp(rb.iloc[-1]['date']) + pd.Timedelta(days=1)
                color = ORB_COLORS[idx % len(ORB_COLORS)]
                ax.axvspan(rs, re, color=color, alpha=ORB_FORMATION_ALPHA, zorder=1)
                ax.fill_between(
                    [d_first, d_last],
                    rl,
                    rh,
                    color=color,
                    alpha=ORB_BAND_ALPHA,
                    zorder=0,
                    linewidth=0,
                )
                ax.plot([d_first, d_last], [rh, rh], color=color, linestyle='--', linewidth=0.85, alpha=0.75, zorder=2)
                ax.plot([d_first, d_last], [rl, rl], color=color, linestyle='--', linewidth=0.85, alpha=0.75, zorder=2)
        else:
            y_ext.extend([float(mdf['high'].max()), float(mdf['low'].min())])

    if not quarter_frames:
        ax.text(0.5, 0.5, 'No daily data for this quarter', transform=ax.transAxes, ha='center', color='#9FB3C8')
        return

    qdf = pd.concat(quarter_frames, ignore_index=True).sort_values('date').reset_index(drop=True)
    dates = pd.to_datetime(qdf['date'])
    draw_candles(ax, dates, qdf['open'], qdf['high'], qdf['low'], qdf['close'])

    # Month boundaries (vertical guides)
    for mo in months[1:]:
        first = daily[(daily['date'].dt.year == year) & (daily['date'].dt.month == mo)]
        if not first.empty:
            d0 = pd.Timestamp(first['date'].min())
            ax.axvline(d0, color='#9FB3C8', linestyle=':', linewidth=0.9, alpha=0.45, zorder=2)

    legend_patches = []
    for idx, mo in enumerate(months):
        mdf = month_daily(daily, year, mo)
        if mdf.empty or len(mdf) < OR_LEN:
            continue
        period = f'{year}-{mo:02d}'
        color = ORB_COLORS[idx % len(ORB_COLORS)]
        legend_patches.append(
            mpatches.Patch(color=color, alpha=0.45, label=f'{month_names[mo - 1]} OR ({period})'),
        )

    all_chart = []
    for mo in months:
        period = f'{year}-{mo:02d}'
        pr = trades[trades['Period'].astype(str) == period]
        ct = pr[pr['Trade_Direction'].astype(str) != 'No-Op']
        if not ct.empty:
            all_chart.append(ct)
    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'Range-Close': '#FFB74D', 'Period-Close': '#BA68C8'}
    if all_chart:
        annotate_trades(ax, pd.concat(all_chart, ignore_index=True), color_for)

    if legend_patches:
        ax.legend(
            handles=legend_patches,
            loc='upper left',
            fontsize=8,
            framealpha=0.35,
            facecolor='#0D1B2A',
            labelcolor='white',
        )

    if y_ext:
        pad = max((max(y_ext) - min(y_ext)) * 0.02, 5.0)
        ax.set_ylim(min(y_ext) - pad, max(y_ext) + pad)
    ax.set_xlim(
        dates.iloc[0] - pd.Timedelta(days=0.6),
        dates.iloc[-1] + pd.Timedelta(days=1.2),
    )

    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.12, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.set_ylabel('Price', color='#9FB3C8', fontsize=9)


def quarter_months(q: int) -> list[int]:
    return {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}[q]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--restricted-csv', type=Path, default=MNQ_ROOT / 'mnq_monthly_orb_restricted.csv')
    ap.add_argument(
        '--out',
        type=Path,
        default=MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'quarterly_panels',
    )
    ap.add_argument('--from-year', type=int, default=2019)
    ap.add_argument('--to-year', type=int, default=2026)
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    daily['date'] = pd.to_datetime(daily['date'])
    trades = pd.read_csv(args.restricted_csv)

    args.out.mkdir(parents=True, exist_ok=True)
    index_rows: list[str] = []
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    for year in range(args.from_year, args.to_year + 1):
        for q in range(1, 5):
            months = quarter_months(q)
            fig, ax = plt.subplots(1, 1, figsize=(16, 6.2), facecolor='#0D1B2A')
            draw_quarter_single_scale(ax, year, months, daily, trades)
            mstr = ' / '.join(month_names[m - 1] for m in months)
            fig.suptitle(
                f'{year} Q{q} — MNQ monthly ORB restricted  ·  {mstr}  ·  one price scale',
                color='white',
                fontsize=12,
                fontweight='bold',
                y=0.98,
            )
            fname = f'{year}-Q{q}.png'
            out_path = args.out / fname
            plt.tight_layout(rect=[0, 0, 1, 0.94])
            fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor='#0D1B2A')
            plt.close(fig)
            index_rows.append(f'| {year} Q{q} | [{fname}]({fname}) |')

    idx = args.out / 'INDEX.md'
    body = '\n'.join(
        [
            '# Monthly ORB restricted — quarterly charts (single scale)',
            '',
            'One PNG per calendar quarter: **all daily candles** for the three months on **one** '
            'time axis and **one** price axis. Each month’s first-3-session OR is a distinct tint '
            '(band + dashed hi/lo for that month’s date span). Trades from '
            f'`{args.restricted_csv.name}`; daily from `{args.daily.name}`.',
            '',
            '| Quarter | Chart |',
            '|---|---|',
            *sorted(index_rows),
            '',
        ]
    )
    idx.write_text(body, encoding='utf-8')
    print(f'Wrote {len(index_rows)} PNGs under {args.out}')
    print(f'Wrote {idx}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
