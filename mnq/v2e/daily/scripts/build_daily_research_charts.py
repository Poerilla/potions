#!/usr/bin/env python3
"""
Build research PNGs under ``daily/charts/research/``:

1. **Equity** — cumulative net (1 MNQ, ``stop_hunter`` SL) for long and short variants.
2. **Trade panels** — daily OHLC context (prior month + session month) with prior-month low/high,
   breaker, entry, TP, stop-hunter stop, and markers for SH / piercer / fill.

Clears ``*.png`` and ``INDEX.md`` in ``--out`` when ``--clean`` (default).

Example::

  cd potions/mnq/v2e/daily/scripts
  python3 build_daily_research_charts.py
"""
from __future__ import annotations

import argparse
import sys
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

DAILY_SCRIPTS = Path(__file__).resolve().parent
DAILY_ROOT = DAILY_SCRIPTS.parent
MNQ_ROOT = DAILY_ROOT.parent.parent
BEAR_SCRIPTS = DAILY_ROOT / 'bearish' / 'scripts'

sys.path[:0] = [str(DAILY_SCRIPTS), str(BEAR_SCRIPTS)]

from prior_month_sweep_daily_common import (  # noqa: E402
    DEFAULT_DAILY_DBN,
    load_mnq_front_daily,
    monthly_high_low,
    month_day_indices,
)

import backtest_prior_month_sweep_daily_long as bd_long  # noqa: E402
import backtest_prior_month_sweep_daily_short as bd_short  # noqa: E402

DEFAULT_OUT = DAILY_ROOT / 'charts' / 'research'


def clean_out(out_dir: Path) -> None:
    if not out_dir.is_dir():
        return
    for p in sorted(out_dir.glob('*.png')):
        p.unlink(missing_ok=True)
    (out_dir / 'INDEX.md').unlink(missing_ok=True)


def prev_ym(y: int, m: int) -> tuple[int, int]:
    if m <= 1:
        return y - 1, 12
    return y, m - 1


@dataclass
class AnnotatedTrade:
    side: str  # 'long' | 'short'
    base: dict
    net_usd: float
    result: str


def collect_long_trades(
    dates: list[date],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    monthly: pd.DataFrame,
    ranges: dict[tuple[int, int], tuple[int, int]],
) -> list[AnnotatedTrade]:
    out: list[AnnotatedTrade] = []
    for y, m in sorted({(d.year, d.month) for d in dates}):
        base = bd_long.compute_setup_month(dates, highs, lows, monthly, ranges, y, m)
        if base is None:
            continue
        tr = bd_long.finalize_trade(
            highs,
            lows,
            closes,
            dates,
            base,
            bd_long.SLMode.stop_hunter_low,
        )
        if tr is None:
            continue
        out.append(
            AnnotatedTrade(side='long', base=base, net_usd=tr.net_usd, result=tr.result)
        )
    return out


def collect_short_trades(
    dates: list[date],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    monthly: pd.DataFrame,
    ranges: dict[tuple[int, int], tuple[int, int]],
) -> list[AnnotatedTrade]:
    out: list[AnnotatedTrade] = []
    for y, m in sorted({(d.year, d.month) for d in dates}):
        base = bd_short.compute_setup_month(dates, highs, lows, monthly, ranges, y, m)
        if base is None:
            continue
        tr = bd_short.finalize_trade(
            highs,
            lows,
            closes,
            dates,
            base,
            bd_short.SLMode.stop_hunter_high,
        )
        if tr is None:
            continue
        out.append(
            AnnotatedTrade(side='short', base=base, net_usd=tr.net_usd, result=tr.result)
        )
    return out


def stratified_month_sample(
    rows: list[AnnotatedTrade], n: int, rng: np.random.Generator
) -> list[AnnotatedTrade]:
    if not rows or n <= 0:
        return []
    work_meta = []
    for i, r in enumerate(rows):
        y, m = int(r.base['session_y']), int(r.base['session_m'])
        work_meta.append((i, pd.Period(year=y, month=m, freq='M')))
    months = sorted({p for _, p in work_meta})
    picked: list[int] = []
    guard = 0
    while len(picked) < n and guard < max(n * 50, 100):
        guard += 1
        progressed = False
        for per in months:
            if len(picked) >= n:
                break
            pool_idx = [i for i, p in work_meta if p == per and i not in picked]
            if not pool_idx:
                continue
            choice = int(rng.choice(pool_idx))
            picked.append(choice)
            progressed = True
        if not progressed:
            break
    remain = n - len(picked)
    if remain > 0:
        rest = [i for i in range(len(rows)) if i not in picked]
        if rest:
            rng.shuffle(rest)
            picked.extend(rest[:remain])
    return [rows[i] for i in picked[:n]]


def draw_equity_side(title: str, nets: list[float], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 5), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')
    cum = np.cumsum(np.array(nets, dtype=float))
    xs = np.arange(len(cum))
    ax.plot(xs, cum, color='#64B5F6', linewidth=1.4)
    ax.axhline(0, color='#546E7A', linewidth=0.8)
    ax.set_title(title, color='white', fontsize=12)
    ax.set_xlabel('Trade #', color='#B0BEC5')
    ax.set_ylabel('Cumulative net USD', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.25, color='#546E7A')
    for spine in ax.spines.values():
        spine.set_color('#37474F')
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, facecolor='#0D1B2A')
    plt.close(fig)


def plot_daily_ohlc(ax, sub: pd.DataFrame, x_num: np.ndarray) -> None:
    """Draw candlesticks (daily OHLC) at matplotlib date numbers ``x_num``."""
    n = len(sub)
    if n == 0:
        return
    if n >= 2:
        dx = float(np.median(np.diff(x_num)))
        width = max(dx * 0.72, 0.35)
    else:
        width = 0.45

    for i in range(n):
        xi = float(x_num[i])
        row = sub.iloc[i]
        o = float(row['open'])
        h = float(row['high'])
        lo = float(row['low'])
        c = float(row['close'])
        up = c >= o
        col = '#26A69A' if up else '#EF5350'
        ax.vlines(xi, lo, h, color=col, linewidth=1.0, zorder=2)
        body_lo = min(o, c)
        body_hi = max(o, c)
        bh = max(body_hi - body_lo, (h - lo) * 0.02 + 0.08)
        ax.add_patch(
            mpatches.Rectangle(
                (xi - width / 2, body_lo),
                width,
                bh,
                facecolor=col,
                edgecolor=col,
                linewidth=0.65,
                zorder=3,
            )
        )


def draw_long_panel(
    daily: pd.DataFrame,
    dates: list[date],
    at: AnnotatedTrade,
    ranges: dict[tuple[int, int], tuple[int, int]],
    out_path: Path,
) -> None:
    base = at.base
    y, m = int(base['session_y']), int(base['session_m'])
    py, pm = prev_ym(y, m)
    if (py, pm) not in ranges or (y, m) not in ranges:
        return
    lo_prev, hi_prev = ranges[(py, pm)]
    lo_cur, hi_cur = ranges[(y, m)]
    plot_lo, plot_hi = lo_prev, hi_cur

    sub = daily.iloc[plot_lo : plot_hi + 1].copy()
    sub.index = pd.to_datetime(sub.index)
    x = mdates.date2num(sub.index.to_numpy())

    fig, ax = plt.subplots(figsize=(13, 6), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    plot_daily_ohlc(ax, sub, x)

    pm_l = float(base['pm_l'])
    ax.axhline(pm_l, color='#FFB74D', linestyle='-', linewidth=1.2, alpha=0.95, label='Prior month low')

    ax.axhline(float(base['breaker_high']), color='#81C784', linestyle='--', linewidth=1.0, label='Breaker / entry')
    ax.axhline(float(base['tp_px']), color='#64B5F6', linestyle='-', linewidth=1.0, alpha=0.9, label='TP')
    ax.axhline(float(base['stop_hunter_low']), color='#E57373', linestyle='-', linewidth=1.0, alpha=0.9, label='SL (SH low)')

    sh_i = int(base['sh_i'])
    pc_i = int(base['piercer_i'])
    fi = int(base['fill_i'])

    def mark(idx: int, color: str, lab: str, mk: str) -> None:
        if plot_lo <= idx <= plot_hi:
            xi = mdates.date2num(pd.Timestamp(dates[idx]))
            yi = float(daily.iloc[idx]['close'])
            ax.scatter([xi], [yi], c=color, s=55, marker=mk, zorder=5, label=lab)

    mark(sh_i, '#FFD54F', 'Stop hunter', 'v')
    mark(pc_i, '#CE93D8', 'Piercer', 's')
    mark(fi, '#A5D6A7', 'Fill', 'o')

    ym_prev = f'{py:04d}-{pm:02d}'
    ax.set_title(
        f'LONG {y:04d}-{m:02d}  ·  prior {ym_prev}  ·  net ${at.net_usd:,.2f}  ·  {at.result}',
        color='white',
        fontsize=11,
    )
    ax.set_xlabel('Date', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=22, ha='right')
    ax.grid(True, linestyle=':', alpha=0.2, color='#546E7A')
    ax.legend(loc='upper left', fontsize=7, framealpha=0.35, labelcolor='#ECEFF1')
    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor='#0D1B2A')
    plt.close(fig)


def draw_short_panel(
    daily: pd.DataFrame,
    dates: list[date],
    at: AnnotatedTrade,
    ranges: dict[tuple[int, int], tuple[int, int]],
    out_path: Path,
) -> None:
    base = at.base
    y, m = int(base['session_y']), int(base['session_m'])
    py, pm = prev_ym(y, m)
    if (py, pm) not in ranges or (y, m) not in ranges:
        return
    lo_prev, hi_prev = ranges[(py, pm)]
    lo_cur, hi_cur = ranges[(y, m)]
    plot_lo, plot_hi = lo_prev, hi_cur

    sub = daily.iloc[plot_lo : plot_hi + 1].copy()
    sub.index = pd.to_datetime(sub.index)
    x = mdates.date2num(sub.index.to_numpy())

    fig, ax = plt.subplots(figsize=(13, 6), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    plot_daily_ohlc(ax, sub, x)

    pm_h = float(base['pm_h'])
    ax.axhline(pm_h, color='#64B5F6', linestyle='-', linewidth=1.2, alpha=0.95, label='Prior month high')

    ax.axhline(float(base['breaker_low']), color='#FFAB91', linestyle='--', linewidth=1.0, label='Breaker / entry')
    ax.axhline(float(base['tp_px']), color='#81C784', linestyle='-', linewidth=1.0, alpha=0.9, label='TP')
    ax.axhline(float(base['stop_hunter_high']), color='#E57373', linestyle='-', linewidth=1.0, alpha=0.9, label='SL (SH high)')

    sh_i = int(base['sh_i'])
    pc_i = int(base['piercer_i'])
    fi = int(base['fill_i'])

    def mark(idx: int, color: str, lab: str, mk: str) -> None:
        if plot_lo <= idx <= plot_hi:
            xi = mdates.date2num(pd.Timestamp(dates[idx]))
            yi = float(daily.iloc[idx]['close'])
            ax.scatter([xi], [yi], c=color, s=55, marker=mk, zorder=5, label=lab)

    mark(sh_i, '#FFD54F', 'Stop hunter', '^')
    mark(pc_i, '#CE93D8', 'Piercer', 's')
    mark(fi, '#FFCC80', 'Fill', 'o')

    ym_prev = f'{py:04d}-{pm:02d}'
    ax.set_title(
        f'SHORT {y:04d}-{m:02d}  ·  prior {ym_prev}  ·  net ${at.net_usd:,.2f}  ·  {at.result}',
        color='white',
        fontsize=11,
    )
    ax.set_xlabel('Date', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=22, ha='right')
    ax.grid(True, linestyle=':', alpha=0.2, color='#546E7A')
    ax.legend(loc='upper left', fontsize=7, framealpha=0.35, labelcolor='#ECEFF1')
    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor='#0D1B2A')
    plt.close(fig)


def write_index(out_dir: Path, rows: list[tuple[str, str]]) -> None:
    lines = ['# Daily v2e — research charts', '', '| File | Note |', '|------|------|']
    for fname, note in sorted(rows):
        lines.append(f'| `{fname}` | {note} |')
    (out_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--max-per-side', type=int, default=10, help='Win + loss panels each side')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--no-clean', action='store_true', help='Keep existing PNGs in --out')
    args = ap.parse_args()

    if not args.daily_dbn.is_file():
        print(f'Missing daily DBN {args.daily_dbn}', file=sys.stderr)
        return 1

    if not args.no_clean:
        clean_out(args.out)

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)

    if args.start:
        daily = daily[daily.index >= pd.to_datetime(args.start)]
    if args.end:
        daily = daily[daily.index <= pd.to_datetime(args.end)]
    if daily.empty:
        print('No rows after date filter.', file=sys.stderr)
        return 1

    dates = [pd.Timestamp(x).date() for x in daily.index]
    highs = [float(x) for x in daily['high'].tolist()]
    lows = [float(x) for x in daily['low'].tolist()]
    closes = [float(x) for x in daily['close'].tolist()]
    monthly = monthly_high_low(daily)
    ranges = month_day_indices(dates)

    long_trades = collect_long_trades(dates, highs, lows, closes, monthly, ranges)
    short_trades = collect_short_trades(dates, highs, lows, closes, monthly, ranges)

    rng = np.random.default_rng(args.seed)
    index_rows: list[tuple[str, str]] = []

    args.out.mkdir(parents=True, exist_ok=True)

    # Equity charts
    if long_trades:
        nets = [t.net_usd for t in long_trades]
        p = args.out / 'equity_long_stop_hunter.png'
        draw_equity_side(
            'Daily v2e LONG — cumulative net (1 MNQ, SL @ stop_hunter_low)',
            nets,
            p,
        )
        index_rows.append((p.name, 'Cumulative equity, long'))

    if short_trades:
        nets = [t.net_usd for t in short_trades]
        p = args.out / 'equity_short_stop_hunter.png'
        draw_equity_side(
            'Daily v2e SHORT — cumulative net (1 MNQ, SL @ stop_hunter_high)',
            nets,
            p,
        )
        index_rows.append((p.name, 'Cumulative equity, short'))

    n_side = max(0, args.max_per_side)

    def panels_for_side(
        side: str, trades: list[AnnotatedTrade], prefix: str, sample_rng: np.random.Generator
    ) -> None:
        if not trades:
            return
        wins = [t for t in trades if t.net_usd > 0]
        losses = [t for t in trades if t.net_usd <= 0]
        sw = stratified_month_sample(wins, min(n_side, len(wins)), sample_rng)
        sl = stratified_month_sample(losses, min(n_side, len(losses)), sample_rng)
        wi = 0
        for t in sw:
            wi += 1
            ym = f'{int(t.base["session_y"]):04d}-{int(t.base["session_m"]):02d}'
            fname = f'{prefix}_win_{wi:02d}_{ym}.png'
            out_path = args.out / fname
            if side == 'long':
                draw_long_panel(daily, dates, t, ranges, out_path)
            else:
                draw_short_panel(daily, dates, t, ranges, out_path)
            index_rows.append((fname, f'{prefix} winner {ym} net=${t.net_usd:.2f}'))
        li = 0
        for t in sl:
            li += 1
            ym = f'{int(t.base["session_y"]):04d}-{int(t.base["session_m"]):02d}'
            fname = f'{prefix}_loss_{li:02d}_{ym}.png'
            out_path = args.out / fname
            if side == 'long':
                draw_long_panel(daily, dates, t, ranges, out_path)
            else:
                draw_short_panel(daily, dates, t, ranges, out_path)
            index_rows.append((fname, f'{prefix} loser {ym} net=${t.net_usd:.2f}'))

    panels_for_side('long', long_trades, 'long', rng)
    rng_short = np.random.default_rng(args.seed + 7)
    panels_for_side('short', short_trades, 'short', rng_short)

    write_index(args.out, index_rows)
    print(f'Wrote charts under {args.out}')
    print(f'  Long trades: {len(long_trades)}  Short trades: {len(short_trades)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
