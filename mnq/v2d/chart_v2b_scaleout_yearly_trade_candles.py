#!/usr/bin/env python3
"""
Yearly charts: one **trade candle** per v2b scaleout leg on a **cumulative equity** axis.

Each bar is one scaleout leg (×2 MNQ); Y-axis is account equity (USD), like a price chart:
- **O** = equity at leg entry (after all prior legs closed)
- **H** = peak equity while leg is open
- **L** = trough equity while leg is open
- **C** = equity after leg closes

Example::

  python3 chart_v2b_scaleout_yearly_trade_candles.py
  python3 chart_v2b_scaleout_yearly_trade_candles.py --years 2023 2024 2025
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

V2D = Path(__file__).resolve().parent
MNQ_ROOT = V2D.parent
CASE = MNQ_ROOT / 'case_studies' / 'midnight_open_hourly_charts'
DEFAULT_DBN = MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
HISTORY_START = date(2021, 3, 4)
OUT_DEFAULT = V2D / 'charts_v2b_scaleout_trade_candles'

POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
sys.path[:0] = [str(MNQ_ROOT), str(POTIONS_SCRIPTS), str(V2D), str(CASE)]

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from benchmark_v2b_scaleout_candidates import causal_regime_v2b, orb_range  # noqa: E402
from mtm_v2b_scaleout import LegOhlcUsd, simulate_scale_out_leg_ohlc  # noqa: E402
from run_adaptive_50_150_scaleout import (  # noqa: E402
    ORB_HI,
    _EPS,
    find_fill_v2b_long,
    find_fill_v2b_short,
    path_after_prior,
    rth_slice,
    trade_params,
)

BG = '#0D1B2A'
GREEN = '#26A69A'
RED = '#EF5350'


@dataclass
class LegEquityCandle:
    """One leg on the cumulative equity curve."""

    session_day: date
    direction: str
    open_eq: float
    high_eq: float
    low_eq: float
    close_eq: float


def legs_to_equity_candles(legs: list[LegOhlcUsd]) -> list[LegEquityCandle]:
    """Map per-leg excursion (vs 0 at entry) onto running equity."""
    equity = 0.0
    out: list[LegEquityCandle] = []
    for leg in legs:
        o = equity
        h = equity + leg.high_usd
        l = equity + leg.low_usd
        c = equity + leg.close_usd
        out.append(
            LegEquityCandle(
                session_day=leg.session_day,
                direction=leg.direction,
                open_eq=round(o, 2),
                high_eq=round(h, 2),
                low_eq=round(l, 2),
                close_eq=round(c, 2),
            )
        )
        equity = c
    return out


def collect_legs_ohlc(gby: dict[date, pd.DataFrame], regime: pd.Series) -> list[LegOhlcUsd]:
    out: list[LegOhlcUsd] = []
    for session_day in sorted(gby.keys()):
        if session_day < HISTORY_START:
            continue
        if session_day not in regime.index or not bool(regime.loc[session_day]):
            continue
        raw = gby[session_day]
        if raw is None or raw.empty:
            continue
        rth = rth_slice(raw, session_day)
        if rth.empty:
            continue
        orb = orb_range(rth, session_day)
        if orb is None:
            continue
        rh, rl, rv = orb
        prior_exit: pd.Timestamp | None = None
        for direction in ('Long', 'Short'):
            if len([x for x in out if x.session_day == session_day]) >= 2:
                break
            pm = trade_params('v2b', direction, rh, rl, rv)
            if pm is None:
                continue
            sub = path_after_prior(rth, session_day, prior_exit)
            if sub.empty:
                continue
            if direction == 'Long':
                fts, _ = find_fill_v2b_long(sub, rh)
            else:
                fts, _ = find_fill_v2b_short(sub, rl)
            if fts is None:
                continue
            _net, exit_ts, ohlc = simulate_scale_out_leg_ohlc(
                rth,
                session_day,
                fts,
                entry=float(pm['entry']),
                long_side=bool(pm['long_side']),
                init_sl=float(pm['init_sl']),
                tp1=float(pm['tp1']),
                tp2=float(pm['tp2']),
                runner_sl=float(pm['runner_sl']),
            )
            out.append(ohlc)
            if exit_ts is not None:
                prior_exit = exit_ts
    return out


def draw_trade_candles(ax, legs: list[LegEquityCandle], *, width: float) -> None:
    dates = [pd.Timestamp(leg.session_day) for leg in legs]
    xs = mdates.date2num(dates)
    day_count: dict[date, int] = defaultdict(int)
    for i, leg in enumerate(legs):
        off = day_count[leg.session_day] * width * 0.55
        day_count[leg.session_day] += 1
        x = xs[i] + off
        o, h, l, c = leg.open_eq, leg.high_eq, leg.low_eq, leg.close_eq
        col = GREEN if c >= o else RED
        ax.vlines(x, l, h, color=col, linewidth=0.9, alpha=0.92, zorder=3)
        body_lo = min(o, c)
        body_hi = max(abs(c - o), 1.0)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                body_hi,
                facecolor=col,
                edgecolor=col,
                alpha=0.9,
                zorder=4,
            )
        )


def draw_year(
    year: int,
    legs: list[LegEquityCandle],
    out_path: Path,
    *,
    dpi: int,
    year_start_eq: float,
    year_end_eq: float,
) -> None:
    sub = sorted([leg for leg in legs if leg.session_day.year == year], key=lambda x: x.session_day)
    if not sub:
        return
    fig, ax = plt.subplots(figsize=(16, 6), facecolor=BG)
    ax.set_facecolor(BG)
    dates = pd.to_datetime([leg.session_day for leg in sub])
    if len(dates) > 1:
        width = float((mdates.date2num(dates.max()) - mdates.date2num(dates.min())) / max(len(sub), 1) * 0.65)
        width = max(width, 0.8)
    else:
        width = 0.8
    draw_trade_candles(ax, sub, width=width)

    yvals = [v for leg in sub for v in (leg.low_eq, leg.high_eq, leg.open_eq, leg.close_eq)]
    yvals.extend((year_start_eq, year_end_eq))
    ylo, yhi = min(yvals), max(yvals)
    pad = max((yhi - ylo) * 0.06, 200.0)
    ax.set_ylim(ylo - pad, yhi + pad)
    year_pnl = year_end_eq - year_start_eq
    ax.set_title(
        f'v2b-only scaleout (×2) — equity candles {year}  ·  '
        f'{len(sub)} legs  ·  year P&L ${year_pnl:+,.0f}  ·  '
        f'eq ${year_start_eq:,.0f} → ${year_end_eq:,.0f}',
        color='white',
        fontsize=11,
    )
    ax.set_ylabel('Cumulative equity (USD)', color='#B0BEC5')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.2, color='#546E7A')
    for spine in ax.spines.values():
        spine.set_color('#37474F')
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)


def write_index(by_year: dict[int, list[LegEquityCandle]], out_dir: Path) -> None:
    lines = [
        '# v2b-only scaleout — yearly equity candles',
        '',
        'Y-axis = **cumulative equity** (USD). Each bar = one scaleout leg: **O** entry equity, '
        '**H** peak, **L** trough, **C** exit equity.',
        'Book: prior-day MA50>MA150, causal 1m v2b (`benchmark_v2b_scaleout_candidates.py`).',
        '',
        '| Year | Legs | Start eq | End eq | Year P&L | Chart |',
        '|---:|---:|---:|---:|---:|---|',
    ]
    for year in sorted(by_year):
        legs = by_year[year]
        if not legs:
            continue
        start_eq = legs[0].open_eq
        end_eq = legs[-1].close_eq
        fn = f'{year}.png'
        lines.append(
            f'| {year} | {len(legs)} | ${start_eq:,.0f} | ${end_eq:,.0f} | '
            f'${end_eq - start_eq:+,.0f} | [{fn}]({fn}) |'
        )
    (out_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--out-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--years', type=int, nargs='*', default=None)
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--export-csv', type=Path, default=None)
    args = ap.parse_args()

    if not args.dbn.is_file():
        print('Missing DBN', file=sys.stderr)
        return 1

    regime = causal_regime_v2b()
    print('Loading 1m + simulating legs ...', flush=True)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    rel_legs = collect_legs_ohlc(gby, regime)
    eq_legs = legs_to_equity_candles(rel_legs)
    print(f'Collected {len(eq_legs)} legs', flush=True)

    if args.export_csv:
        pd.DataFrame(
            [
                {
                    'session': leg.session_day.isoformat(),
                    'direction': leg.direction,
                    'open_eq': leg.open_eq,
                    'high_eq': leg.high_eq,
                    'low_eq': leg.low_eq,
                    'close_eq': leg.close_eq,
                    'leg_pnl': round(leg.close_eq - leg.open_eq, 2),
                }
                for leg in eq_legs
            ]
        ).to_csv(args.export_csv, index=False)
        print(f'Wrote {args.export_csv}', flush=True)

    by_year: dict[int, list[LegEquityCandle]] = defaultdict(list)
    for leg in eq_legs:
        by_year[leg.session_day.year].append(leg)

    years = args.years if args.years else sorted(by_year.keys())
    for year in years:
        if year not in by_year or not by_year[year]:
            continue
        year_legs = by_year[year]
        out_path = args.out_dir / f'{year}.png'
        draw_year(
            year,
            eq_legs,
            out_path,
            dpi=args.dpi,
            year_start_eq=year_legs[0].open_eq,
            year_end_eq=year_legs[-1].close_eq,
        )
        print(out_path, flush=True)

    write_index(by_year, args.out_dir)
    print(f'Done → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
