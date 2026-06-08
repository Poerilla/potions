#!/usr/bin/env python3
"""
**v2b_m** case-study charts (**long-only**, bullish_break by default): **RTH only** (09:30–16:00 NY),
5 m candles, ORB band, **prior-month high** only (month low omitted for cleaner vertical scale), entry/exit price lines (no timestamps in tier‑1 CSV).

Reads ``mnq_orb_results_stops.csv`` and applies ``engine.qualify_v2b_m_legs`` unless ``--from-csv`` points
at ``v2b_m_legs.csv`` from ``run_v2b_m.py``.

Example::

  cd potions/mnq/case_studies/v2b_m
  python3 run_v2b_m.py --export-csv ./v2b_m_legs.csv
  python3 build_v2b_m_charts.py --from-csv ./v2b_m_legs.csv --max-charts 0
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

HERE = Path(__file__).resolve().parent
MNQ_ROOT = HERE.parents[1]
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(HERE), str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from plot_daily_prior_month_levels import (  # noqa: E402
    load_mnq_front_daily,
    monthly_high_low,
    prior_month_levels_series,
)

from engine import qualify_v2b_m_legs  # noqa: E402

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
ORB_LO = time(9, 30)
ORB_HI = time(9, 45)

DEFAULT_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
DEFAULT_M1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_STOPS = MNQ_ROOT / 'mnq_orb_results_stops.csv'
DEFAULT_OUT = HERE / 'charts'


def rth_slice(idx_df: pd.DataFrame, session_day) -> pd.DataFrame:
    return idx_df[
        idx_df.index.map(
            lambda t: (t.date() == session_day and RTH_LO <= t.time() < RTH_HI)
        )
    ].copy()


def resample_5m_rth(rth: pd.DataFrame, session_day) -> pd.DataFrame:
    if rth.empty:
        return rth
    anchor = NY.localize(datetime.combine(session_day, RTH_LO))
    return (
        rth.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def draw_rth_chart(
    bars5: pd.DataFrame,
    session_day,
    rh: float,
    rl: float,
    pm_h: float,
    entry_px: float,
    exit_px: float,
    *,
    direction: str,
    result: str,
    net_usd: float,
    bias_bucket: str,
    geom_tag: str,
    out_path: Path,
    dpi: int,
    figsize: tuple[float, float],
) -> None:
    fig, ax = plt.subplots(figsize=figsize, facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    if not bars5.empty:
        t_orb0 = NY.localize(datetime.combine(session_day, ORB_LO))
        t_orb1 = NY.localize(datetime.combine(session_day, ORB_HI))
        ax.axvspan(
            mdates.date2num(t_orb0),
            mdates.date2num(t_orb1),
            color='#1F4E79',
            alpha=0.42,
            zorder=0,
            label='ORB [9:30–9:45)',
        )

        for ts, row in bars5.iterrows():
            x = mdates.date2num(ts)
            width = 5 / (24 * 60) * 0.72
            o, h, lo, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
            is_up = c >= o
            col = '#26A69A' if is_up else '#EF5350'
            ax.vlines(x, lo, h, color=col, linewidth=0.85, zorder=3)
            body_lo, body_hi = min(o, c), max(o, c)
            ax.add_patch(
                mpatches.Rectangle(
                    (x - width / 2, body_lo),
                    width,
                    max(body_hi - body_lo, 0.08),
                    facecolor=col,
                    edgecolor=col,
                    alpha=0.95,
                    zorder=3,
                )
            )

    x_rth_end = mdates.date2num(NY.localize(datetime.combine(session_day, RTH_HI)))

    ax.axhline(rh, color='#90A4AE', linestyle='-', linewidth=1.1, zorder=2, alpha=0.9, label='ORB high')
    ax.axhline(rl, color='#78909C', linestyle='-', linewidth=1.1, zorder=2, alpha=0.9, label='ORB low')

    if np.isfinite(pm_h):
        ax.axhline(pm_h, color='#64B5F6', linestyle='-', linewidth=1.25, zorder=2, label='Prior month high')

    orb_end_num = mdates.date2num(NY.localize(datetime.combine(session_day, ORB_HI)))
    if np.isfinite(entry_px):
        ax.hlines(
            entry_px,
            orb_end_num,
            x_rth_end,
            colors='#FFC107',
            linestyles='--',
            linewidth=1.6,
            label=f'Entry {entry_px:.2f}',
            zorder=4,
        )
    if np.isfinite(exit_px):
        ax.hlines(
            exit_px,
            orb_end_num,
            x_rth_end,
            colors='#69F0AE' if str(result).startswith('Win') or str(result).startswith('EOD-Win') else '#FF5252',
            linestyles='--',
            linewidth=1.6,
            label=f'Exit {exit_px:.2f}',
            zorder=4,
        )

    tp_note = 'TP-style ✓' if str(result).strip() in ('Win', 'EOD-Win') else 'no TP-style win'
    ax.set_title(
        f'v2b_m  ·  {session_day}  ·  {direction}  ·  {bias_bucket}\n'
        f'{geom_tag}  ·  {result}  ${float(net_usd):+.2f}  ·  {tp_note}',
        color='white',
        fontsize=10,
    )
    ax.set_xlabel('NY time', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.25, color='#546E7A')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.legend(loc='upper left', fontsize=7, facecolor='#1B263B', edgecolor='#37474F', labelcolor='#ECEFF1')
    for spine in ax.spines.values():
        spine.set_color('#37474F')

    if not bars5.empty:
        t0, t1 = bars5.index.min(), bars5.index.max()
        ax.set_xlim(mdates.date2num(t0) - 1 / (24 * 8), mdates.date2num(t1) + 5 / (24 * 60))

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor='#0D1B2A')
    plt.close(fig)


def load_qualified_frame(args: argparse.Namespace) -> pd.DataFrame:
    if args.from_csv:
        if not args.from_csv.is_file():
            raise SystemExit(f'Missing --from-csv {args.from_csv}')
        df = pd.read_csv(args.from_csv)
        return df.sort_values(['Date', 'Trade_Direction'])

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)
    monthly = monthly_high_low(daily)
    pm_h, pm_l = prior_month_levels_series(daily, monthly)
    legs = qualify_v2b_m_legs(
        args.stops_csv, daily, pm_h, pm_l, include_hemisphere=args.include_hemisphere
    )
    if legs.empty:
        raise SystemExit('No qualifying legs — widen EPS or check inputs.')
    return legs.sort_values(['Date', 'Trade_Direction'])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--from-csv', type=Path, default=None, help='Qualified legs CSV from run_v2b_m.py')
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--stops-csv', type=Path, default=DEFAULT_STOPS)
    ap.add_argument('--1m', dest='m1', type=Path, default=DEFAULT_M1)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--max-charts', type=int, default=400, help='Cap PNG count (0 = plot every qualifying leg)')
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(13.0, 6.5))
    ap.add_argument(
        '--include-hemisphere',
        action='store_true',
        help='Allow hemisphere_long when recomputing legs without --from-csv (default: breaks only)',
    )
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m: {args.m1}', file=sys.stderr)
        return 1

    comb = load_qualified_frame(args)
    need = set(pd.to_datetime(comb['Date']).dt.date.unique())
    tmin, tmax = min(need), max(need)

    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    n_done = 0
    for _, row in comb.iterrows():
        if args.max_charts and n_done >= args.max_charts:
            break
        d = pd.to_datetime(row['Date']).date()
        day = gby.get(d)
        if day is None or day.empty:
            print(f'  skip {d} no 1m', flush=True)
            continue
        rth = rth_slice(day, d)
        bars5 = resample_5m_rth(rth, d)
        if bars5.empty:
            print(f'  skip {d} empty RTH', flush=True)
            continue

        direction = str(row['Trade_Direction']).strip()
        out_dir = args.out / str(d.year)
        fname = f'{d.isoformat()}_{direction}.png'
        draw_rth_chart(
            bars5,
            d,
            float(row['Range_High']),
            float(row['Range_Low']),
            float(row['pm_high']),
            float(row['Entry_Price']),
            float(row['Exit_Price']),
            direction=direction,
            result=str(row['Result']),
            net_usd=float(row['Net_$']),
            bias_bucket=str(row['bias_bucket']),
            geom_tag=str(row['geom_tag']),
            out_path=out_dir / fname,
            dpi=args.dpi,
            figsize=tuple(args.figsize),
        )
        n_done += 1
        if n_done % 100 == 0:
            print(f'  ... {n_done} charts', flush=True)

    print(f'Wrote {n_done} charts under {args.out}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
