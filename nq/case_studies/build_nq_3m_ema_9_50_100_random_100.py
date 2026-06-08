#!/usr/bin/env python3
"""
Random sample of NQ RTH sessions — **3-minute** candles with EMA 9 / 50 / 100.

Chart style matches MNQ adaptive case studies (dark navy, teal/red candles, ORB shade).

Usage::

  python3 nq/case_studies/build_nq_3m_ema_9_50_100_random_100.py
  python3 nq/case_studies/build_nq_3m_ema_9_50_100_random_100.py --seed 7 --sample-size 100
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import date, datetime, time
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
POTIONS_ROOT = HERE.parents[1]
MNQ_ROOT = POTIONS_ROOT / 'mnq'
sys.path[:0] = [str(MNQ_ROOT / 'case_studies' / 'midnight_open_hourly_charts')]

from build_midnight_open_hourly_charts import (  # noqa: E402
    DEFAULT_DBN_NQ,
    INSTRUMENT_DBN,
    load_1m_by_ny_date,
)

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
# First 15 minutes of RTH: [09:30, 09:45) NY (1m bars 09:30 … 09:44).
ORB_LO = time(9, 30)
ORB_HI = time(9, 45)


def orb_window(session_day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    return (
        NY.localize(datetime.combine(session_day, ORB_LO)),
        NY.localize(datetime.combine(session_day, ORB_HI)),
    )

EMA_PERIODS = (9, 50, 100)
EMA_COLORS = {9: '#FFC107', 50: '#26C6DA', 100: '#CE93D8'}
BG = '#0D1B2A'
ORB_SHADE = '#1F4E79'


def rth_1m(day_df: pd.DataFrame, session_day: date) -> pd.DataFrame:
    if day_df is None or day_df.empty:
        return pd.DataFrame()
    return day_df[
        day_df.index.map(
            lambda ts: ts.date() == session_day
            and RTH_LO <= ts.time() < RTH_HI
        )
    ].sort_index()


def resample_3m(rth: pd.DataFrame) -> pd.DataFrame:
    if rth.empty:
        return rth
    return (
        rth.resample('3min', label='right', closed='right')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
        )
        .dropna(subset=['open', 'high', 'low', 'close'])
    )


def add_emas(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    close = pd.to_numeric(out['close'], errors='coerce')
    for p in EMA_PERIODS:
        out[f'ema{p}'] = close.ewm(span=p, adjust=False).mean()
    return out


def orb_levels(rth_1m: pd.DataFrame, session_day: date) -> tuple[float, float]:
    """High/low of 1m bars in the opening range [09:30, 09:45) NY."""
    t0, t1 = orb_window(session_day)
    orb = rth_1m[(rth_1m.index >= t0) & (rth_1m.index < t1)]
    if orb.empty:
        return float('nan'), float('nan')
    return float(orb['high'].max()), float(orb['low'].min())


def front_symbol(day_df: pd.DataFrame) -> str:
    if day_df is None or day_df.empty or 'symbol' not in day_df.columns:
        return 'NQ'
    vol = day_df.groupby('symbol')['volume'].sum()
    if vol.empty:
        return 'NQ'
    return str(vol.idxmax())


def ema_stack_label(row: pd.Series) -> str:
    e9, e50, e100 = row.get('ema9'), row.get('ema50'), row.get('ema100')
    if not all(np.isfinite(x) for x in (e9, e50, e100)):
        return 'warming'
    if e9 > e50 > e100:
        return 'bull_stack'
    if e9 < e50 < e100:
        return 'bear_stack'
    return 'mixed'


def draw_chart(
    session_day: date,
    bars3: pd.DataFrame,
    orb_h: float,
    orb_l: float,
    symbol: str,
    out_path: Path,
) -> dict[str, object]:
    fig = plt.figure(figsize=(14, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)

    t_orb0, t_orb1 = orb_window(session_day)
    ax.axvspan(t_orb0, t_orb1, color=ORB_SHADE, alpha=0.30, zorder=0)

    if np.isfinite(orb_h) and np.isfinite(orb_l):
        ax.axhline(orb_h, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(orb_l, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhspan(orb_l, orb_h, color=ORB_SHADE, alpha=0.10, zorder=0)

    for ts, row in bars3.iterrows():
        x = mdates.date2num(ts)
        width = 3 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.7, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=c,
                edgecolor=c,
                alpha=0.95,
                zorder=3,
            )
        )

    for p in EMA_PERIODS:
        col = f'ema{p}'
        ax.plot(
            bars3.index,
            bars3[col],
            color=EMA_COLORS[p],
            linewidth=1.15 if p == 9 else 1.35,
            alpha=0.95,
            label=f'EMA {p}',
            zorder=5,
        )

    last = bars3.iloc[-1]
    end_regime = ema_stack_label(last)
    net_pts = float(bars3['close'].iloc[-1] - bars3['open'].iloc[0])
    rv = float(bars3['high'].max() - bars3['low'].min())
    orb_rng = (orb_h - orb_l) if np.isfinite(orb_h) and np.isfinite(orb_l) else float('nan')

    title = (
        f'{session_day}  ·  NQ 3m EMA 9/50/100  ·  {end_regime}  ·  {symbol}  ·  '
        f'RTH {rv:.1f}pt  ·  net {net_pts:+.1f}pt'
    )
    if np.isfinite(orb_rng):
        title += f'  ·  ORB {orb_rng:.1f}'
    ax.set_title(title, color='white', fontsize=9, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(
        bars3.index[0] - pd.Timedelta(minutes=8),
        bars3.index[-1] + pd.Timedelta(minutes=12),
    )
    ax.legend(
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=8,
    )

    if np.isfinite(orb_h) and np.isfinite(orb_l):
        last_x = mdates.date2num(bars3.index[-1]) + 0.004
        ax.text(last_x, orb_h, f' RH {orb_h:.1f}', color='#E0E0E0', fontsize=7, va='center')
        ax.text(last_x, orb_l, f' RL {orb_l:.1f}', color='#E0E0E0', fontsize=7, va='center')

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=100, bbox_inches='tight', facecolor=BG)
    plt.close()

    return {
        'session': session_day.isoformat(),
        'symbol': symbol,
        'bars_3m': len(bars3),
        'rth_range_pts': round(rv, 2),
        'net_pts': round(net_pts, 2),
        'orb_range_pts': round(orb_rng, 2) if np.isfinite(orb_rng) else None,
        'end_regime': end_regime,
        'ema9_end': round(float(last['ema9']), 2),
        'ema50_end': round(float(last['ema50']), 2),
        'ema100_end': round(float(last['ema100']), 2),
    }


def build(
    *,
    output_root: Path,
    dbn_path: Path,
    sample_size: int,
    seed: int,
    force: bool,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    chart_dir = output_root / 'charts'
    chart_dir.mkdir(parents=True, exist_ok=True)

    print(f'Loading NQ 1m ({dbn_path}) ...', flush=True)
    by_day = load_1m_by_ny_date(dbn_path, 'nq')
    rng = random.Random(seed)
    candidates = sorted(by_day.keys())
    rng.shuffle(candidates)

    selected: list[date] = []
    prepared: dict[date, tuple[pd.DataFrame, pd.DataFrame, float, float, str]] = {}
    min_3m = max(EMA_PERIODS) + 5

    for day in candidates:
        raw = by_day.get(day)
        rth = rth_1m(raw, day)
        if rth.empty or len(rth) < 250:
            continue
        bars3 = add_emas(resample_3m(rth))
        if len(bars3) < min_3m or not bars3['ema100'].iloc[-1:].notna().all():
            continue
        oh, ol = orb_levels(rth, day)
        sym = front_symbol(raw)
        selected.append(day)
        prepared[day] = (bars3, rth, oh, ol, sym)
        if len(selected) >= sample_size:
            break

    selected = sorted(selected)
    print(f'Sampled {len(selected)} sessions (seed={seed})', flush=True)

    rows: list[dict[str, object]] = []
    for idx, day in enumerate(selected, start=1):
        bars3, _rth, oh, ol, sym = prepared[day]
        rel = Path('charts') / f'{idx:03d}_{day.isoformat()}.png'
        meta = draw_chart(day, bars3, oh, ol, sym, output_root / rel)
        meta['idx'] = idx
        meta['chart'] = str(rel)
        rows.append(meta)
        if idx % 25 == 0:
            print(f'  charted {idx}/{len(selected)}', flush=True)

    pd.DataFrame(rows).to_csv(output_root / 'chart_manifest.csv', index=False)

    regime_counts = pd.Series([r['end_regime'] for r in rows]).value_counts()
    lines = [
        '# NQ 3m EMA 9 / 50 / 100 — random sample',
        '',
        f'**{len(rows)}** RTH sessions on **3-minute** candles with EMA(9), EMA(50), EMA(100) '
        f'(`ewm(span=period, adjust=False)`). Sample seed `{seed}`.',
        '',
        'Visual style matches `mnq/case_studies/adaptive_by_year` (dark navy, teal/red bodies, '
        'opening range **09:30–09:45 NY** shaded, dashed RH/RL from 1m bars in that window).',
        '',
        '## End-of-session EMA stack',
        '',
    ]
    for label, cnt in regime_counts.items():
        lines.append(f'- **{label}**: {cnt}')
    lines.extend(['', '| # | Session | Symbol | Regime | Net pt | RTH range | Chart |', '|---:|---|---|---|---:|---:|---|'])
    for row in rows:
        lines.append(
            '| {idx} | {session} | {symbol} | {end_regime} | {net_pts:+.1f} | {rth_range_pts:.1f} | '
            '[{chart}]({chart}) |'.format(**row)
        )
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {output_root / "INDEX.md"}', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description='NQ 3m EMA 9/50/100 random sample charts')
    ap.add_argument(
        '--output-root',
        type=Path,
        default=HERE / 'nq_3m_ema_9_50_100_random_100',
    )
    ap.add_argument('--dbn', type=Path, default=INSTRUMENT_DBN.get('nq', DEFAULT_DBN_NQ))
    ap.add_argument('--sample-size', type=int, default=100)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--no-force', action='store_true')
    args = ap.parse_args()
    build(
        output_root=args.output_root,
        dbn_path=args.dbn.resolve(),
        sample_size=args.sample_size,
        seed=args.seed,
        force=not args.no_force,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
