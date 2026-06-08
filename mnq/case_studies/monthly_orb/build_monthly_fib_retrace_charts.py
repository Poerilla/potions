#!/usr/bin/env python3
"""Yearly daily charts: monthly swing L→H Fib retracement touch + weekly ST + yearly OR.

For each **confirmed** monthly pivot high (after a prior pivot low), with a
**bullish monthly break** (that month's close above the prior month's high),
compute the **Fib retracement from swing low to swing high** of the impulse leg
and mark the **first daily session** where price trades through the configured
retracement level (default **61.8%** pullback from H toward L:
``H - ratio * (H - L)``).

Charts are split **one PNG per calendar year** for readability. Each chart shows:
- Daily candles for that year
- **Yearly opening range** (Jan–Mar high / low) for that calendar year as dashed horizontals + light band
- **Weekly ATR Supertrend** stop (cyan when trend ``up``, orange when ``down``)
- **Fib level** horizontal(s) for events whose first-touch date falls in that year
- **Green vertical line** on each first-touch day

Also writes ``events.csv`` and ``INDEX.md`` under the output root.

Example:
  python mnq/case_studies/monthly_orb/build_monthly_fib_retrace_charts.py
  python mnq/case_studies/monthly_orb/build_monthly_fib_retrace_charts.py \\
      --daily nq/nq_daily.csv --out-root nq/case_studies/monthly_orb/fib_retrace_yearly
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from yearly_orb_delivery_research_charts import calculate_weekly_atr_trailing_stop_on_daily

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
CYAN = '#00BCD4'
ORANGE = '#FF9800'
FIB_COLOR = '#FFEB3B'
YOR = '#E0E0E0'
TOUCH_VLINE = '#00E676'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def daily_to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d['ym'] = d['date'].dt.to_period('M')
    mon = (
        d.groupby('ym', sort=True)
        .agg(
            month_open=('open', 'first'),
            month_high=('high', 'max'),
            month_low=('low', 'min'),
            month_close=('close', 'last'),
            month_first=('date', 'min'),
            month_last=('date', 'max'),
        )
        .reset_index()
    )
    mon['year'] = mon['ym'].dt.year
    mon['month'] = mon['ym'].dt.month
    return mon


def pivot_low_indices(lows: pd.Series, left: int, right: int) -> list[int]:
    n = len(lows)
    out: list[int] = []
    vals = lows.astype(float).values
    for i in range(left, n - right):
        window = vals[i - left : i + right + 1]
        m = float(window.min())
        if vals[i] == m and list(window).count(vals[i]) == 1:
            out.append(i)
    return out


def pivot_high_indices(highs: pd.Series, left: int, right: int) -> list[int]:
    n = len(highs)
    out: list[int] = []
    vals = highs.astype(float).values
    for i in range(left, n - right):
        window = vals[i - left : i + right + 1]
        m = float(window.max())
        if vals[i] == m and list(window).count(vals[i]) == 1:
            out.append(i)
    return out


def yearly_or_levels(daily: pd.DataFrame, year: int) -> tuple[float, float]:
    m = daily['date'].dt.year == year
    m &= daily['date'].dt.month <= 3
    sub = daily.loc[m]
    if sub.empty:
        return float('nan'), float('nan')
    return float(sub['high'].max()), float(sub['low'].min())


def attach_weekly_st(daily: pd.DataFrame, atr_len: int, atr_mult: float) -> pd.DataFrame:
    work = daily.copy()
    mapped = calculate_weekly_atr_trailing_stop_on_daily(work, atr_len, atr_mult)
    out = mapped.rename(columns={'atr_trend': 'wk_trend', 'atr_stop': 'wk_stop'})
    return out


def collect_fib_touch_events(
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    *,
    pivot_left: int,
    pivot_right: int,
    retrace_ratio: float,
    bull_filter: str,
) -> pd.DataFrame:
    """Fib from monthly swing low to swing high; optional bullish context filter."""
    lows = monthly['month_low']
    highs = monthly['month_high']
    closes = monthly['month_close']
    pl = pivot_low_indices(lows, pivot_left, pivot_right)
    ph = pivot_high_indices(highs, pivot_left, pivot_right)
    pl_set = set(pl)

    rows: list[dict] = []
    for hi in ph:
        prior_lows = [j for j in pl if j < hi]
        if not prior_lows:
            continue
        lo = max(prior_lows)
        L = float(monthly.iloc[lo]['month_low'])
        H = float(monthly.iloc[hi]['month_high'])
        if H <= L:
            continue

        if hi < 1:
            continue

        prev_high = float(monthly.iloc[hi - 1]['month_high'])
        prev_close = float(monthly.iloc[hi - 1]['month_close'])
        c_hi = float(closes.iloc[hi])
        if bull_filter == 'prior_month_high':
            bull_ok = c_hi > prev_high
        elif bull_filter == 'prior_month_close':
            bull_ok = c_hi > prev_close
        elif bull_filter == 'green_month':
            o_hi = float(monthly.iloc[hi]['month_open'])
            bull_ok = c_hi > o_hi and c_hi > prev_close
        else:
            bull_ok = True
        if not bull_ok:
            continue

        confirm_idx = hi + pivot_right
        if confirm_idx >= len(monthly):
            continue

        search_start = pd.Timestamp(monthly.iloc[confirm_idx]['month_last']) + pd.Timedelta(days=1)
        fib_price = H - retrace_ratio * (H - L)

        sub = daily[daily['date'] >= search_start].copy()
        if sub.empty:
            rows.append(
                {
                    'pivot_low_idx': lo,
                    'pivot_high_idx': hi,
                    'swing_low': L,
                    'swing_high': H,
                    'fib_ratio': retrace_ratio,
                    'fib_price': fib_price,
                    'touch_date': pd.NaT,
                    'month_low_period': str(monthly.iloc[lo]['ym']),
                    'month_high_period': str(monthly.iloc[hi]['ym']),
                }
            )
            continue

        touch_date = None
        for _, bar in sub.iterrows():
            b_lo = float(bar['low'])
            b_hi = float(bar['high'])
            if b_lo <= fib_price <= b_hi:
                touch_date = bar['date']
                break

        rows.append(
            {
                'pivot_low_idx': lo,
                'pivot_high_idx': hi,
                'swing_low': L,
                'swing_high': H,
                'fib_ratio': retrace_ratio,
                'fib_price': fib_price,
                'touch_date': touch_date,
                'month_low_period': str(monthly.iloc[lo]['ym']),
                'month_high_period': str(monthly.iloc[hi]['ym']),
            }
        )

    return pd.DataFrame(rows)


def draw_candles(ax: plt.Axes, work: pd.DataFrame) -> None:
    dates = pd.to_datetime(work['date'])
    xnums = mdates.date2num(dates)
    width = 0.62
    for x, (_, row) in zip(xnums, work.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN if c >= o else RED
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


def plot_weekly_stop(ax: plt.Axes, work: pd.DataFrame) -> None:
    w = work[work['wk_stop'].notna() & work['wk_trend'].notna()].copy()
    if w.empty:
        return
    x = mdates.date2num(pd.to_datetime(w['date']))
    trend = w['wk_trend'].astype(str)
    seg_id = (trend.ne(trend.shift())).cumsum()
    for _, chunk in w.groupby(seg_id):
        col = CYAN if str(chunk['wk_trend'].iloc[0]) == 'up' else ORANGE
        ax.plot(
            mdates.date2num(pd.to_datetime(chunk['date'])),
            chunk['wk_stop'].astype(float),
            color=col,
            linewidth=1.1,
            alpha=0.85,
            zorder=4,
        )


def draw_year_chart(
    year: int,
    year_daily: pd.DataFrame,
    y_rh: float,
    y_rl: float,
    events_in_year: pd.DataFrame,
    out_path: Path,
    title_tag: str,
    retrace_ratio: float,
) -> None:
    work = year_daily.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])

    fig = plt.figure(figsize=(18, 8.5), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    draw_candles(ax, work)
    plot_weekly_stop(ax, work)

    if math.isfinite(y_rh) and math.isfinite(y_rl) and y_rh > y_rl:
        ax.axhline(y_rh, color=YOR, linestyle='--', linewidth=1.05, zorder=2, label='YOR high')
        ax.axhline(y_rl, color=YOR, linestyle='--', linewidth=1.05, zorder=2, label='YOR low')
        ax.axhspan(y_rl, y_rh, color='#1F4E79', alpha=0.12, zorder=0)

    for _, ev in events_in_year.iterrows():
        fp = float(ev['fib_price'])
        ax.axhline(fp, color=FIB_COLOR, linestyle=':', linewidth=0.9, alpha=0.75, zorder=2)
        td = ev['touch_date']
        if pd.notna(td):
            x0 = mdates.date2num(pd.Timestamp(td))
            ax.axvline(x0, color=TOUCH_VLINE, linewidth=1.35, alpha=0.9, zorder=5)

    rtxt = f'{float(events_in_year.iloc[0]["fib_ratio"]):.1%}' if len(events_in_year) else f'{retrace_ratio:.1%}'
    ax.set_title(
        f'{title_tag} {year} — daily · monthly swing Fib {rtxt} retrace touch (green) · weekly ST · yearly OR',
        color='white',
        fontsize=11,
        fontweight='bold',
        loc='left',
        pad=12,
    )
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.12, color=GRID)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, facecolor=BG)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=ROOT / 'mnq' / 'mnq_daily.csv')
    ap.add_argument(
        '--out-root',
        type=Path,
        default=ROOT / 'mnq' / 'case_studies' / 'monthly_orb' / 'fib_retrace_yearly',
    )
    ap.add_argument('--title-tag', type=str, default='MNQ')
    ap.add_argument('--weekly-atr-len', type=int, default=14)
    ap.add_argument('--weekly-atr-mult', type=float, default=3.0)
    ap.add_argument('--retrace', type=float, default=0.618, help='Pullback from H toward L (0.618 = 61.8%%)')
    ap.add_argument(
        '--bull-filter',
        choices=('prior_month_high', 'prior_month_close', 'green_month', 'none'),
        default='prior_month_close',
        help='Bullish context at pivot-high month: close vs prior month (default: close above prior month close).',
    )
    ap.add_argument(
        '--pivot-left',
        type=int,
        default=1,
        help='Monthly fractal half-width (bars).',
    )
    ap.add_argument('--pivot-right', type=int, default=1)
    args = ap.parse_args()

    daily_raw = load_daily(args.daily)
    daily = attach_weekly_st(daily_raw, args.weekly_atr_len, args.weekly_atr_mult)

    monthly = daily_to_monthly(daily)
    events = collect_fib_touch_events(
        daily,
        monthly,
        pivot_left=args.pivot_left,
        pivot_right=args.pivot_right,
        retrace_ratio=args.retrace,
        bull_filter=args.bull_filter,
    )

    args.out_root.mkdir(parents=True, exist_ok=True)
    events_path = args.out_root / 'events.csv'
    events.to_csv(events_path, index=False)

    years = sorted(daily['date'].dt.year.unique().tolist())
    bull_desc = {
        'prior_month_high': 'month of pivot **high** closes **above prior month high**',
        'prior_month_close': 'month of pivot **high** closes **above prior month close**',
        'green_month': 'bullish month (close > open) and close above prior month close',
        'none': 'no extra filter (impulse H > L only)',
    }[args.bull_filter]

    index_lines = [
        '# Monthly swing Fib retracement — yearly charts',
        '',
        f'- Daily: `{args.daily}`',
        f'- Fib from **confirmed monthly swing low** to **swing high**; level = `H − {args.retrace:.3f}×(H−L)` (retracement from the high).',
        f'- **Bullish context:** {bull_desc}.',
        f'- Monthly pivots: **{args.pivot_left}** left / **{args.pivot_right}** right bars (fractal).',
        f'- **Green vertical line:** first daily bar **after** pivot confirmation where `low ≤ fib ≤ high`.',
        f'- **Weekly ATR Supertrend** on daily series (cyan `up`, orange `down`).',
        f'- **Yearly opening range:** Jan–Mar high/low for each chart year.',
        f'- Events CSV: [`events.csv`](events.csv)',
        '',
        '## Charts by year',
        '',
        '| Year | Chart |',
        '|---:|---|',
    ]

    for yr in years:
        ymask = daily['date'].dt.year == yr
        y_daily = daily.loc[ymask].copy()
        if y_daily.empty:
            continue
        y_rh, y_rl = yearly_or_levels(daily, yr)

        ev_y = events[events['touch_date'].notna()].copy()
        ev_y = ev_y[pd.to_datetime(ev_y['touch_date']).dt.year == yr]

        out_png = args.out_root / str(yr) / f'{yr}.png'
        draw_year_chart(yr, y_daily, y_rh, y_rl, ev_y, out_png, args.title_tag, args.retrace)
        rel = f'{yr}/{yr}.png'
        index_lines.append(f'| {yr} | [{yr}.png]({rel}) |')

    index_path = args.out_root / 'INDEX.md'
    index_path.write_text('\n'.join(index_lines) + '\n', encoding='utf-8')

    n_touch = int(events['touch_date'].notna().sum())
    print(f'Wrote {events_path} ({len(events)} legs, {n_touch} with first daily touch)')
    print(f'Wrote yearly PNGs under {args.out_root}')
    print(f'Wrote {index_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
