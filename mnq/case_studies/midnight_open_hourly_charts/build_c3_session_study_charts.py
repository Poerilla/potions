#!/usr/bin/env python3
"""
Side-by-side **C3 study** charts (no trade markers).

**Left:** C1 · C2 · C3 **session-daily** candles (large) with candlestick-theory levels.
**Right:** C3 session **15 m** [00:00, 16:00) NY — midnight open + RTH ORB [09:30, 09:45).

Shared price scale across panels.

Example::

  python3 build_c3_session_study_charts.py --last-n 50
  python3 build_c3_session_study_charts.py --n-hits 25 --n-misses 25
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
import chart_draw as cd  # noqa: E402
from backtest_midnight_open_flip import (  # noqa: E402
    ATR_FADE_ENTRY_EARLIEST,
    ATR_FADE_ENTRY_MULT,
    atr_on_1m_bars,
    build_hourly_with_warmup,
)

NY = pytz.timezone('America/New_York')
BG = '#0D1B2A'
GREEN = '#26A69A'
RED = '#EF5350'
GRAY = '#CFD8DC'
YELLOW = '#FFC107'
PURPLE = '#EA80FC'
BLUE = '#90CAF9'
TEAL = '#26C6DA'

DEFAULT_DBN = mdata.DEFAULT_DBN
DEFAULT_SETUPS = HERE.parent / 'daily_candlestick_theory' / 'setups.csv'
OUT_DEFAULT = HERE / 'charts_c3_session_study'


def draw_daily_candles(ax, bars: pd.DataFrame, *, width_scale: float) -> None:
    """Daily bars with ``date`` column or datetime index."""
    work = bars.copy()
    if 'date' in work.columns:
        dates = pd.to_datetime(work['date'])
    else:
        dates = pd.to_datetime(work.index)
    x = mdates.date2num(dates)
    width = (1.0 * width_scale) if len(x) <= 1 else float(pd.Series(x).diff().dropna().median()) * width_scale
    for xval, (_, row) in zip(x, work.iterrows()):
        o, h, l, c = map(float, (row['open'], row['high'], row['low'], row['close']))
        col = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=col, linewidth=1.1, zorder=3, alpha=0.95)
        ax.add_patch(
            mpatches.Rectangle(
                (xval - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.1),
                facecolor=col,
                edgecolor=col,
                alpha=0.92,
                zorder=4,
            )
        )


def draw_level_h(
    ax,
    x0: float,
    x1: float,
    y: float,
    color: str,
    label: str,
    linestyle: str,
    *,
    alpha: float = 0.85,
    lw: float = 1.0,
) -> None:
    ax.hlines(y, x0, x1, colors=color, linestyles=linestyle, linewidths=lw, alpha=alpha, zorder=5)
    ax.text(x1, y, f' {label}', color=color, fontsize=7, va='center', ha='left', alpha=alpha, zorder=8)


def daily_c2_high_low(ax, setup: pd.Series, x0: float, x1: float) -> None:
    """C2 H/L only on the session-daily triplet panel."""
    draw_level_h(ax, x0, x1, float(setup['c2_high']), YELLOW, 'C2 H', '--', alpha=0.9, lw=1.1)
    draw_level_h(ax, x0, x1, float(setup['c2_low']), YELLOW, 'C2 L', '--', alpha=0.9, lw=1.1)


def atr_bands_at_entry(
    sess_1m: pd.DataFrame,
    hourly_warm: pd.DataFrame,
    session_day: date,
    M: float,
) -> tuple[float, float, float]:
    """Hourly ATR at **10:00 NY** → ``(atr, M+2×ATR, M−2×ATR)``."""
    t_ref = NY.localize(datetime.combine(session_day, ATR_FADE_ENTRY_EARLIEST))
    atr_s = atr_on_1m_bars(sess_1m, hourly_warm)
    prior = atr_s[atr_s.index <= t_ref]
    atr = float(prior.iloc[-1]) if not prior.empty else float('nan')
    if not (np.isfinite(M) and np.isfinite(atr) and atr > 0):
        return atr, float('nan'), float('nan')
    mult = ATR_FADE_ENTRY_MULT
    return atr, M + mult * atr, M - mult * atr


def session_daily_bar(raw, session_day: date) -> dict | None:
    bar = mdata.resample_daily_session_bar(raw, session_day)
    if bar is None or bar.empty:
        return None
    row = bar.iloc[0]
    return {
        'date': session_day,
        'open': float(row['open']),
        'high': float(row['high']),
        'low': float(row['low']),
        'close': float(row['close']),
    }


def draw_pair_chart(
    setup: pd.Series,
    gby: dict[date, pd.DataFrame],
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> bool:
    c3_day = date.fromisoformat(str(setup['c3_date']))
    c1_day = date.fromisoformat(str(setup['c1_date']))
    c2_day = date.fromisoformat(str(setup['c2_date']))

    triple_rows = []
    for d in (c1_day, c2_day, c3_day):
        raw = gby.get(d)
        if raw is None:
            return False
        row = session_daily_bar(raw, d)
        if row is None:
            return False
        triple_rows.append(row)
    triple = pd.DataFrame(triple_rows)

    raw_c3 = gby.get(c3_day)
    if raw_c3 is None:
        return False
    sess = mdata.slice_session_1m(raw_c3, c3_day)
    bars15 = mdata.resample_15m_midnight_to_1600(raw_c3, c3_day)
    if bars15 is None or bars15.empty:
        return False
    bars15 = bars15.sort_index()
    M = mdata.ny_midnight_open_px(sess)
    orb_h, orb_l = mdata.orb_high_low_1m(sess, c3_day)
    hw = build_hourly_with_warmup(gby, c3_day)
    atr, entry_up, entry_lo = atr_bands_at_entry(sess, hw, c3_day, M)

    price_vals = list(triple['low']) + list(triple['high']) + [float(bars15['low'].min()), float(bars15['high'].max())]
    for v in (M, orb_h, orb_l, entry_up, entry_lo):
        if np.isfinite(v):
            price_vals.append(v)
    ylo, yhi = min(price_vals), max(price_vals)
    pad = max((yhi - ylo) * 0.04, 8.0)

    fig, (ax_triple, ax_sess) = plt.subplots(
        1,
        2,
        figsize=figsize,
        facecolor=BG,
        gridspec_kw={'width_ratios': [1.0, 2.35], 'wspace': 0.08},
    )
    for ax in (ax_triple, ax_sess):
        ax.set_facecolor(BG)
        ax.set_ylim(ylo - pad, yhi + pad)
        ax.tick_params(colors='#CFD8DC')
        ax.grid(True, linestyle=':', alpha=0.22, color='#546E7A')
        for spine in ax.spines.values():
            spine.set_color('#37474F')

    # ── Left: C1 C2 C3 ──
    draw_daily_candles(ax_triple, triple, width_scale=0.78)
    dates = pd.to_datetime(triple['date'])
    x_nums = mdates.date2num(dates)
    x0, x1 = float(x_nums[0]) - 0.55, float(x_nums[-1]) + 0.55
    daily_c2_high_low(ax_triple, setup, x0, x1)

    c3_x = mdates.date2num(pd.Timestamp(c3_day))
    half = 0.42 if len(x_nums) > 1 else 0.42
    ax_triple.axvspan(c3_x - half, c3_x + half, color=TEAL, alpha=0.12, zorder=0)
    for i, lbl in enumerate(['C1', 'C2', 'C3']):
        ax_triple.text(
            x_nums[i],
            yhi + pad * 0.55,
            lbl,
            color='white',
            ha='center',
            va='bottom',
            fontsize=10,
            fontweight='bold',
        )

    ax_triple.set_xlim(x0, x1)
    ax_triple.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d', tz=NY))
    ax_triple.set_title('C1 · C2 · C3 (session daily)', color='white', fontsize=10)
    ax_triple.set_ylabel('Price', color='#B0BEC5')

    # ── Right: C3 session 15m ──
    cd.draw_session_candles(ax_sess, bars15, bar_minutes=15)

    t_orb0 = NY.localize(datetime.combine(c3_day, mdata.ORB_LO))
    t_orb1 = NY.localize(datetime.combine(c3_day, mdata.ORB_HI))
    ax_sess.axvspan(
        mdates.date2num(t_orb0),
        mdates.date2num(t_orb1),
        color='#1F4E79',
        alpha=0.32,
        zorder=0,
    )

    if np.isfinite(M):
        ax_sess.axhline(M, color='#26C6DA', linewidth=1.45, zorder=2, alpha=0.95)
    if np.isfinite(entry_up):
        ax_sess.axhline(entry_up, color='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.85)
    if np.isfinite(entry_lo):
        ax_sess.axhline(entry_lo, color='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.85)
    if np.isfinite(orb_h):
        ax_sess.axhline(orb_h, color='#90A4AE', linestyle='--', linewidth=0.9, alpha=0.65)
    if np.isfinite(orb_l):
        ax_sess.axhline(orb_l, color='#78909C', linestyle='--', linewidth=0.9, alpha=0.65)

    cd.style_session_ax(ax_sess, bars15, ny=NY, bar_minutes=15)
    hit = bool(setup.get('hit', setup.get('c3_took_c2_extreme', False)))
    ax_sess.set_title(
        f'C3 session {c3_day}  ·  15m  ·  {setup["direction"]}  ·  '
        f'{"HIT" if hit else "miss"}  ·  ext {float(setup["extension_pts"]):+.0f} pts',
        color='white',
        fontsize=10,
    )
    ax_sess.set_xlabel('NY time', color='#B0BEC5')

    fig.suptitle(
        f'MNQ daily C3 study #{int(setup["setup_id"])}  ·  '
        f'{c1_day} → {c2_day} → {c3_day}',
        color='white',
        fontsize=11,
        y=0.98,
    )

    atr_lbl = f'ATR={atr:.1f}' if np.isfinite(atr) else 'ATR'
    legend_elems = [
        Line2D([0], [0], color=TEAL, linewidth=2, label='Midnight M'),
        Line2D([0], [0], color='#FFB74D', linewidth=1.5, linestyle='--', label=f'M ± 2×ATR ({atr_lbl})'),
        Line2D([0], [0], color='#90A4AE', linewidth=1.5, linestyle='--', label='ORB H/L'),
        Line2D([0], [0], color=YELLOW, linewidth=1.5, linestyle='--', label='C2 H/L (daily)'),
    ]
    ax_sess.legend(
        handles=legend_elems,
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=7,
    )

    fig.subplots_adjust(left=0.05, right=0.98, top=0.92, bottom=0.1, wspace=0.08)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return True


def pick_setups(df: pd.DataFrame, *, last_n: int, n_hits: int, n_misses: int) -> pd.DataFrame:
    df = df.sort_values('c3_date', ascending=False)
    if n_hits > 0 or n_misses > 0:
        hits = df[df['hit'].astype(bool)].head(n_hits) if n_hits > 0 else pd.DataFrame()
        misses = df[~df['hit'].astype(bool)].head(n_misses) if n_misses > 0 else pd.DataFrame()
        return pd.concat([hits, misses]).drop_duplicates(subset=['setup_id'])
    return df.head(last_n)


def write_index(rows: list[dict], path: Path) -> None:
    lines = [
        '# C3 session study — side-by-side charts',
        '',
        f'**Charts:** {len(rows)}',
        '',
        '**Left:** C1·C2·C3 session-daily bars; **C2 H/L** only. '
        '**Right:** C3 session 15m — **M**, **M±2×ATR** @ 10:00, ORB. No trade markers.',
        '',
        '| Setup | C3 | Dir | Hit | Chart |',
        '|---:|---|---|---|---|',
    ]
    for r in sorted(rows, key=lambda x: x['c3_date']):
        fn = r['file'].replace('\\', '/')
        lines.append(
            f"| {r['setup_id']} | {r['c3_date']} | {r['direction']} | {r['hit']} | [{fn}]({fn}) |"
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--setups-csv', type=Path, default=DEFAULT_SETUPS)
    ap.add_argument('--out-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--last-n', type=int, default=50)
    ap.add_argument('--n-hits', type=int, default=0)
    ap.add_argument('--n-misses', type=int, default=0)
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(20.0, 7.5))
    args = ap.parse_args()

    if not args.setups_csv.is_file():
        print(f'Missing setups: {args.setups_csv}', file=sys.stderr)
        return 1
    if not args.dbn.is_file():
        print(f'Missing DBN: {args.dbn}', file=sys.stderr)
        return 1

    all_setups = pd.read_csv(args.setups_csv).sort_values('c3_date', ascending=False)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    valid_days = set(gby.keys())

    def chartable(row: pd.Series) -> bool:
        for col in ('c1_date', 'c2_date', 'c3_date'):
            d = date.fromisoformat(str(row[col]))
            if d not in valid_days:
                return False
            raw = gby.get(d)
            if raw is None or mdata.slice_session_1m(raw, d).empty:
                return False
            if session_daily_bar(raw, d) is None:
                return False
        c3 = date.fromisoformat(str(row['c3_date']))
        b15 = mdata.resample_15m_midnight_to_1600(gby[c3], c3)
        return b15 is not None and not b15.empty

    pool = all_setups[all_setups.apply(chartable, axis=1)]
    setups = pick_setups(pool, last_n=args.last_n, n_hits=args.n_hits, n_misses=args.n_misses)
    print(f'Charting {len(setups)} setups ({len(pool)} with DBN data) ...', flush=True)

    index_rows: list[dict] = []
    for _, setup in setups.iterrows():
        hit = bool(setup['hit'])
        sub = 'hits' if hit else 'misses'
        c3_day = date.fromisoformat(str(setup['c3_date']))
        fn = (
            f'{int(setup["setup_id"]):04d}_{setup["direction"]}_{c3_day.isoformat()}_'
            f'{"hit" if hit else "miss"}.png'
        )
        out_path = args.out_dir / sub / str(c3_day.year) / fn
        if draw_pair_chart(setup, gby, out_path, dpi=args.dpi, figsize=tuple(args.figsize)):
            index_rows.append(
                {
                    'setup_id': int(setup['setup_id']),
                    'c3_date': c3_day.isoformat(),
                    'direction': setup['direction'],
                    'hit': hit,
                    'file': str(out_path.relative_to(args.out_dir)),
                }
            )
            print(out_path, flush=True)

    write_index(index_rows, args.out_dir / 'INDEX.md')
    print(f'Wrote {len(index_rows)} charts → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
