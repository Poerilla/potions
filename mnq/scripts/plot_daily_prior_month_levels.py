#!/usr/bin/env python3
"""
MNQ **daily** chart from Databento **ohlcv-1d**: settlement-style bars (front month / day).

- Vertical dashed lines on **Jan 1** each year (calendar year delineation).
- **Prior calendar month** high / low as horizontal **step** lines (levels known once the
  prior month has completed; constant across the current month).

Writes:

1. One **full-range** PNG (``--out``).
2. Additional **~6 calendar month** slices (unless ``--no-six-month-charts``) under
   ``--six-month-dir`` (default: ``{dirname}/{stem}_6mo/`` next to ``--out``), files named
   ``{first}_{last}.png``.

Example::

  cd potions/mnq/scripts
  python3 plot_daily_prior_month_levels.py --out ../v2d/mnq_daily_prior_month_chart.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MNQ_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DAILY_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
SYMBOL_PREFIX = 'MNQ'


def load_mnq_front_daily(dbn: Path) -> pd.DataFrame:
    """Daily MNQ: highest-volume symbol per calendar day (matches ``prior_week_levels``)."""
    import databento as db

    store = db.DBNStore.from_file(str(dbn))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(SYMBOL_PREFIX)].copy()
    df['d'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('d')['volume'].idxmax()]
    out = fm.set_index('d').sort_index()
    return out[['open', 'high', 'low', 'close', 'volume', 'symbol']].copy()


def _prev_calendar_month(y: int, m: int) -> tuple[int, int]:
    if m <= 1:
        return y - 1, 12
    return y, m - 1


def monthly_high_low(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar month in *daily* index: that month's high / low."""
    s = daily.copy()
    s['_y'] = pd.DatetimeIndex(s.index).year
    s['_m'] = pd.DatetimeIndex(s.index).month
    g = s.groupby(['_y', '_m'], sort=True).agg(m_high=('high', 'max'), m_low=('low', 'min'))
    return g


def prior_month_levels_series(daily: pd.DataFrame, monthly: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Per trading day: prior completed calendar month's high and low."""
    idx = pd.DatetimeIndex(pd.to_datetime(daily.index))
    highs = np.full(len(daily), np.nan)
    lows = np.full(len(daily), np.nan)
    keys = set(monthly.index)

    for i, d in enumerate(idx):
        py, pm = _prev_calendar_month(int(d.year), int(d.month))
        if (py, pm) not in keys:
            continue
        highs[i] = float(monthly.loc[(py, pm), 'm_high'])
        lows[i] = float(monthly.loc[(py, pm), 'm_low'])

    ser_h = pd.Series(highs, index=idx, name='prior_month_high')
    ser_l = pd.Series(lows, index=idx, name='prior_month_low')
    return ser_h, ser_l


def iter_six_month_exclusive_starts(dmin: pd.Timestamp, dmax: pd.Timestamp) -> list[pd.Timestamp]:
    """Non-overlapping windows ``[t, t + 6 calendar months)`` anchored at the first session day."""
    cur = pd.Timestamp(dmin).normalize()
    starts: list[pd.Timestamp] = []
    cap = pd.Timestamp(dmax).normalize()
    while cur <= cap:
        starts.append(cur)
        cur = cur + pd.DateOffset(months=6)
    return starts


def slice_daily_six_month(daily: pd.DataFrame, window_start: pd.Timestamp) -> pd.DataFrame:
    excl_end = window_start + pd.DateOffset(months=6)
    return daily[(daily.index >= window_start) & (daily.index < excl_end)].copy()


def render_chart(
    daily: pd.DataFrame,
    monthly_full: pd.DataFrame,
    out_path: Path,
    *,
    figsize: tuple[float, float],
    dpi: int,
    title: str,
    x_major_months: int | None,
) -> None:
    """``x_major_months``: None → year ticks; 1 → monthly labels (good for 6‑month panels)."""
    pm_h, pm_l = prior_month_levels_series(daily, monthly_full)

    fig, ax = plt.subplots(figsize=figsize, facecolor='#fafafa')
    ax.set_facecolor('#fafafa')

    x = mdates.date2num(pd.to_datetime(daily.index).to_numpy())
    ax.fill_between(x, daily['low'].values, daily['high'].values, color='#bdbdbd', alpha=0.35, linewidth=0, label='Daily range')
    ax.plot(x, daily['close'].values, color='#1a237e', linewidth=1.1, label='Close')
    ax.plot(x, pm_h.values, color='#1565c0', linewidth=1.25, linestyle='-', drawstyle='steps-post', label='Prior month high')
    ax.plot(x, pm_l.values, color='#c62828', linewidth=1.25, linestyle='-', drawstyle='steps-post', label='Prior month low')

    y0 = int(daily.index.year.min())
    y1 = int(daily.index.year.max())
    x_min, x_max = daily.index.min(), daily.index.max()
    for yy in range(y0, y1 + 1):
        jan = pd.Timestamp(year=yy, month=1, day=1)
        if jan <= x_max and jan >= x_min:
            ax.axvline(jan, color='#9e9e9e', linestyle='--', linewidth=1.0, alpha=0.85, zorder=1)

    ax.set_title(title, fontsize=12)
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend(loc='upper left', framealpha=0.92)
    ax.grid(True, linestyle=':', alpha=0.45)

    if x_major_months == 1:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha='right')
    else:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_minor_locator(mdates.MonthLocator(interval=3))

    sym = str(daily['symbol'].iloc[-1]) if 'symbol' in daily.columns else ''
    ax.text(
        0.99,
        0.02,
        f'{sym}  ·  {daily.index.min().date()} → {daily.index.max().date()}',
        transform=ax.transAxes,
        ha='right',
        va='bottom',
        fontsize=8,
        color='#424242',
    )

    ax.set_xlim(mdates.date2num(x_min), mdates.date2num(x_max))

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    ap.add_argument('--start', default=None, help='YYYY-MM-DD inclusive lower bound')
    ap.add_argument('--end', default=None, help='YYYY-MM-DD inclusive upper bound')
    ap.add_argument('--out', type=Path, default=MNQ_ROOT / 'v2d' / 'mnq_daily_prior_month_chart.png')
    ap.add_argument('--figsize', nargs=2, type=float, default=(14.0, 7.0))
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument(
        '--no-six-month-charts',
        action='store_true',
        help='Skip writing ~6‑month slice PNGs (full chart only)',
    )
    ap.add_argument(
        '--six-month-figsize',
        nargs=2,
        type=float,
        default=(11.0, 5.0),
        metavar=('W', 'H'),
        help='Figure size for each 6‑month PNG',
    )
    ap.add_argument(
        '--six-month-dir',
        type=Path,
        default=None,
        help='Folder for 6‑month PNGs (default: ``{out dirname}/{stem}_6mo``)',
    )
    args = ap.parse_args()

    if not args.daily_dbn.is_file():
        print(f'Missing daily DBN: {args.daily_dbn}', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)

    if args.start:
        daily = daily[daily.index >= pd.to_datetime(args.start)]
    if args.end:
        daily = daily[daily.index <= pd.to_datetime(args.end)]
    if daily.empty:
        print('No rows after date filter.', file=sys.stderr)
        return 1

    monthly_full = monthly_high_low(daily)

    render_chart(
        daily,
        monthly_full,
        args.out,
        figsize=tuple(args.figsize),
        dpi=args.dpi,
        title='MNQ daily (front month / day) — prior calendar month high/low + year dividers (Jan 1)',
        x_major_months=None,
    )
    print(f'Wrote {args.out}')

    if args.no_six_month_charts:
        return 0

    stem = args.out.stem
    six_fig = tuple(args.six_month_figsize)
    six_dir = args.six_month_dir if args.six_month_dir is not None else args.out.parent / f'{stem}_6mo'
    six_dir.mkdir(parents=True, exist_ok=True)

    dmin = pd.Timestamp(daily.index.min())
    dmax = pd.Timestamp(daily.index.max())
    starts = iter_six_month_exclusive_starts(dmin, dmax)
    n_written = 0
    for ws in starts:
        seg = slice_daily_six_month(daily, ws)
        if seg.empty or len(seg) < 2:
            continue
        d0 = seg.index.min().date()
        d1 = seg.index.max().date()
        part_path = six_dir / f'{d0}_{d1}.png'
        render_chart(
            seg,
            monthly_full,
            part_path,
            figsize=six_fig,
            dpi=args.dpi,
            title=f'MNQ daily — 6‑month window · prior month H/L · {d0} → {d1}',
            x_major_months=1,
        )
        print(f'Wrote {part_path}')
        n_written += 1

    if n_written == 0:
        print('No six-month charts written (empty segments).', file=sys.stderr)
    else:
        print(f'Six-month charts directory: {six_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
