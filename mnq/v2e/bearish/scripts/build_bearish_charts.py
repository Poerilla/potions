#!/usr/bin/env python3
"""
Stratified sample charts for **bearish** London sweep breaker (SHORT).

Writes PNGs under ``bearish/case_studies/charts/winners/`` and
``bearish/case_studies/charts/losers/`` (25 each by default).

Reads ``bearish/data/mnq_v2e_london_sweep_breaker_bearish.csv`` — regenerate via
``backtest_london_sweep_breaker_short.py --export-csv``.

Clears ``*.png`` in those folders before each run.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, time
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

BEAR_ROOT = Path(__file__).resolve().parent.parent
V2E_ROOT = BEAR_ROOT.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(BEAR_ROOT / 'scripts'), str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402

from backtest_london_sweep_breaker_short import (  # noqa: E402
    EOD_CUTOFF,
    find_setup_short,
    london_low_high,
)

NY = pytz.timezone('America/New_York')
LDN_LO = time(2, 0)
LDN_HI = time(9, 30)
RTH_HI = time(16, 0)

DEFAULT_TRADES = BEAR_ROOT / 'data' / 'mnq_v2e_london_sweep_breaker_bearish.csv'
DEFAULT_M1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_OUT = BEAR_ROOT / 'case_studies' / 'charts'


def clean_png_dir(d: Path) -> None:
    if not d.is_dir():
        return
    for p in sorted(d.glob('*.png')):
        p.unlink(missing_ok=True)


def stratified_month_sample(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.iloc[0:0]
    work = df.copy()
    work['_ym'] = pd.to_datetime(work['session_day']).dt.to_period('M')
    months = sorted(work['_ym'].unique())
    picked_idx: list[int] = []
    guard = 0
    while len(picked_idx) < n and guard < n * 50:
        guard += 1
        progressed = False
        for ym in months:
            if len(picked_idx) >= n:
                break
            sub = work[~work.index.isin(picked_idx)]
            sub = sub[sub['_ym'] == ym]
            if sub.empty:
                continue
            row = sub.sample(1, random_state=int(rng.integers(1_000_000_000)))
            picked_idx.append(int(row.index[0]))
            progressed = True
        if not progressed:
            break
    remain = n - len(picked_idx)
    if remain > 0:
        pool = work[~work.index.isin(picked_idx)]
        if not pool.empty:
            extra = pool.sample(min(remain, len(pool)), random_state=int(rng.integers(1_000_000_000)))
            picked_idx.extend(extra.index.tolist())
    out = df.loc[[i for i in picked_idx if i in df.index]].copy()
    return out.head(n)


def resample_5m(day_idx: pd.DataFrame, session_d, anchor_h: int = 2, anchor_m: int = 0) -> pd.DataFrame:
    sub = day_idx[
        day_idx.index.map(
            lambda t: t.date() == session_d and time(anchor_h, anchor_m) <= t.time() < RTH_HI
        )
    ].sort_index()
    if sub.empty:
        return sub
    anchor = NY.localize(datetime.combine(session_d, time(anchor_h, anchor_m)))
    return (
        sub.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def draw_one(
    bars5: pd.DataFrame,
    session_d,
    row: pd.Series,
    setup: dict,
    ts_list: list[pd.Timestamp],
    ldn_h: float,
    ldn_l: float,
    out_path: Path,
    tag: str,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 7), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    xnum = mdates.date2num(bars5.index.to_pydatetime())
    width = 5 / (24 * 60) * 0.65

    for xi, (ts, r) in zip(xnum, bars5.iterrows()):
        o, hi, lo, cl = float(r['open']), float(r['high']), float(r['low']), float(r['close'])
        col = '#26A69A' if cl >= o else '#EF5350'
        ax.vlines(xi, lo, hi, color=col, linewidth=0.9, zorder=3)
        body_lo, body_hi = min(o, cl), max(o, cl)
        ax.add_patch(
            mpatches.Rectangle(
                (xi - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )

    if len(bars5.index):
        t0 = bars5.index[0]
        t_ldn_end = NY.localize(datetime.combine(session_d, LDN_HI))
        ax.axvspan(
            mdates.date2num(t0.to_pydatetime()),
            mdates.date2num(t_ldn_end),
            color='#1F4E79',
            alpha=0.28,
            zorder=0,
        )

    ax.axhline(ldn_h, color='#E0E0E0', linestyle='--', linewidth=1.0, alpha=0.85, label='London H')
    ax.axhline(ldn_l, color='#90CAF9', linestyle='--', linewidth=1.0, alpha=0.9, label='London L')
    ax.axhline(float(row['breaker_low']), color='#FFD54F', linestyle='-', linewidth=1.1, label='Breaker L / limit sell')
    ax.axhline(float(row['breaker_high']), color='#FFB74D', linestyle=':', linewidth=0.9, alpha=0.8)
    ax.axhline(float(row['tp_px']), color='#76FF03', linestyle='-', linewidth=1.0, alpha=0.85, label='TP')
    ax.axhline(float(row['stop_px']), color='#FF5252', linestyle='-', linewidth=1.0, alpha=0.85, label='SL')

    sh_i = setup['sh_i']
    pi = setup['piercer_i']
    fi = setup['fill_i']
    brk_ts = setup.get('breaker_5m_left')
    if brk_ts is not None:
        ts_b = pd.Timestamp(brk_ts)
        ax.axvline(
            mdates.date2num(ts_b.to_pydatetime()),
            color='#FFCA28',
            linestyle='--',
            linewidth=1.05,
            alpha=0.95,
            label='breaker 5m',
        )

    for lab, idx, col in (
        ('stop_hunter', sh_i, '#EA80FC'),
        ('piercer', pi, '#FFF176'),
        ('fill', fi, '#80D8FF'),
    ):
        if 0 <= idx < len(ts_list):
            ax.axvline(
                mdates.date2num(ts_list[idx].to_pydatetime()),
                color=col,
                linestyle=':',
                linewidth=1.0,
                alpha=0.95,
                label=lab,
            )

    net = float(row['net_usd'])
    title = (
        f'{tag.upper()} SHORT  {session_d}  |  Net ${net:+.2f}  |  {row["result"]}  '
        f'| MAE {float(row["mae_pts"]):.1f} pt  | MFE {float(row["mfe_pts"]):.1f} pt'
    )
    ax.set_title(title, color='#ECEFF1', fontsize=11)
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.grid(True, linestyle=':', alpha=0.25, color='#546E7A')
    ax.tick_params(colors='#B0BEC5')
    ax.legend(loc='upper left', facecolor='#263238', edgecolor='#455A64', labelcolor='#ECEFF1', fontsize=7, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    plt.xticks(rotation=30)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, facecolor='#0D1B2A')
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_TRADES)
    ap.add_argument('--1m', dest='m1', type=Path, default=DEFAULT_M1)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--n-each', type=int, default=25)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    if not args.trades_csv.is_file():
        print(f'Missing trades CSV {args.trades_csv}', file=sys.stderr)
        return 1
    if not args.m1.is_file():
        print(f'Missing 1m {args.m1}', file=sys.stderr)
        return 1

    winners_dir = args.out / 'winners'
    losers_dir = args.out / 'losers'
    winners_dir.mkdir(parents=True, exist_ok=True)
    losers_dir.mkdir(parents=True, exist_ok=True)
    clean_png_dir(winners_dir)
    clean_png_dir(losers_dir)

    df = pd.read_csv(args.trades_csv)
    df['session_day'] = pd.to_datetime(df['session_day']).dt.date
    wins = df[df['net_usd'].astype(float) > 0].copy()
    losses = df[df['net_usd'].astype(float) <= 0].copy()

    rng = np.random.default_rng(args.seed)
    sw = stratified_month_sample(wins, args.n_each, rng)
    sl = stratified_month_sample(losses, args.n_each, rng)

    need_dates = set(sw['session_day'].tolist()) | set(sl['session_day'].tolist())
    dmin, dmax = min(need_dates), max(need_dates)

    raw = ann.load_1m_for_dates(str(args.m1), dmin, dmax, need_dates)
    raw = ann.pick_front_month_day(raw)
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw = raw.set_index('ts_event').sort_index()
    raw['_d'] = raw.index.date
    by_day = {d: g.drop(columns=['_d']) for d, g in raw.groupby('_d')}
    raw = raw.drop(columns=['_d'])

    lines = ['# Bearish London sweep — charts', '', '## Winners', '', '| File | Net USD | Result |', '|------|--------:|--------|']

    def run_batch(sub_df: pd.DataFrame, prefix: str, out_dir: Path) -> None:
        for i, (_, row) in enumerate(sub_df.iterrows(), start=1):
            session_d = row['session_day']
            day_b = by_day.get(session_d)
            if day_b is None or day_b.empty:
                print(f'skip no data {session_d}', file=sys.stderr)
                continue
            ldn_l, ldn_h = london_low_high(day_b, session_d)
            ts_order = list(day_b.index)
            setup = find_setup_short(session_d, float(ldn_h), day_b)
            if setup is None:
                print(f'skip no setup {session_d}', file=sys.stderr)
                continue
            bars5 = resample_5m(day_b, session_d)
            if bars5.empty:
                continue
            fname = f'{prefix}_{i:02d}_{session_d}.png'
            out_p = out_dir / fname
            draw_one(bars5, session_d, row, setup, ts_order, ldn_h, ldn_l, out_p, prefix)
            lines.append(f'| `{out_dir.name}/{fname}` | {float(row["net_usd"]):+.2f} | {row["result"]} |')
            print(f'{out_dir.name}/{fname}')

    run_batch(sw, 'win', winners_dir)
    lines.extend(['', '## Losers', '', '| File | Net USD | Result |', '|------|--------:|--------|'])
    run_batch(sl, 'loss', losers_dir)

    (args.out / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\nWrote charts under {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
