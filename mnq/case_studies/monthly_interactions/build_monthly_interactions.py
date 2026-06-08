#!/usr/bin/env python3
"""
**Monthly interactions** — MNQ sessions where **prior calendar month** high or low is **crossed**
on 5 m candles from **midnight–16:00 NY** (Globex open through RTH close).

- Monthly levels: same definition as ``plot_daily_prior_month_levels.py`` (prior completed month H/L).
- **Cross**: session transitions through the level (previous 5 m close on one side, current bar’s range
  reaches the other side). Evaluated separately for prior-month **high** and **low**.
- Charts: 5 m OHLC candles, horizontal prior-month H/L, **ORB [09:30, 09:45)** high/low band, optional
  subtitle with ``rules.monthly_opening_range_bias`` bucket.

Charts default layout: ``{out_dir}/{YYYY}/{YYYY-MM-DD}.png`` (one folder per calendar year).

Outputs PNGs + root ``INDEX.md``.

Cross detection lives in ``rules.monthly_interaction_cross`` (shared with v2b_m MI annotator).

**Lookahead note:** chart PNGs use (a) a **daily-bar touch** pre-filter and (b) **full** 00:00–16:00 crosses —
both are backward-looking if interpreted as live filters. For **causal** flags through a decision clock,
see ``case_studies/v2b_m/annotate_monthly_interaction_flags.py`` and
``crosses_prior_month_levels_through_cutoff``.

Example::

  cd potions/mnq/case_studies/monthly_interactions
  python3 build_monthly_interactions.py --start 2023-01-01 --end 2024-01-01 --max-charts 100
  python3 build_monthly_interactions.py --count-only
  python3 build_monthly_interactions.py --max-charts 0
"""
from __future__ import annotations

import argparse
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
MNQ_ROOT = HERE.parents[1]
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path.insert(0, str(MNQ_ROOT))
sys.path.insert(0, str(MNQ_ROOT / 'scripts'))
sys.path.insert(0, str(POTIONS_SCRIPTS))

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from plot_daily_prior_month_levels import (  # noqa: E402
    load_mnq_front_daily,
    monthly_high_low,
    prior_month_levels_series,
)
from rules.monthly_interaction_cross import (  # noqa: E402
    cross_detect_5m,
    resample_5m_midnight_to_1600,
)
from rules.monthly_opening_range_bias import monthly_orb_bias_for_session_date  # noqa: E402

NY = pytz.timezone('America/New_York')
ORB_LO = time(9, 30)
ORB_HI = time(9, 45)

DEFAULT_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
DEFAULT_M1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'


def chart_out_dir(base: Path, session_day: date) -> Path:
    """Calendar year folder under ``base``."""
    return base / str(session_day.year)


def daily_touches_level(lo: float, hi: float, level: float) -> bool:
    if not (np.isfinite(lo) and np.isfinite(hi) and np.isfinite(level)):
        return False
    return lo <= level <= hi


def orb_high_low_1m(day_1m: pd.DataFrame, session_day: date) -> tuple[float, float]:
    orb = day_1m[
        day_1m.index.map(
            lambda t: (t.date() == session_day and ORB_LO <= t.time() < ORB_HI)
        )
    ]
    if orb.empty:
        return float('nan'), float('nan')
    return float(orb['high'].max()), float(orb['low'].min())


def draw_chart(
    bars5: pd.DataFrame,
    session_day: date,
    pm_h: float,
    pm_l: float,
    orb_rh: float,
    orb_rl: float,
    bias_bucket: str,
    cross_h: bool,
    cross_l: bool,
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> None:
    fig, ax = plt.subplots(figsize=figsize, facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    if not bars5.empty:
        t0 = bars5.index.min()
        t1 = bars5.index.max()
        t_orb0 = NY.localize(datetime.combine(session_day, ORB_LO))
        t_orb1 = NY.localize(datetime.combine(session_day, ORB_HI))
        ax.axvspan(
            mdates.date2num(t_orb0),
            mdates.date2num(t_orb1),
            color='#1F4E79',
            alpha=0.35,
            zorder=0,
        )

        for ts, row in bars5.iterrows():
            x = mdates.date2num(ts)
            width = 5 / (24 * 60) * 0.72
            is_up = float(row['close']) >= float(row['open'])
            c = '#26A69A' if is_up else '#EF5350'
            lo = float(row['low'])
            hi = float(row['high'])
            ax.vlines(x, lo, hi, color=c, linewidth=0.85, zorder=3)
            body_lo = min(float(row['open']), float(row['close']))
            body_hi = max(float(row['open']), float(row['close']))
            ax.add_patch(
                mpatches.Rectangle(
                    (x - width / 2, body_lo),
                    width,
                    max(body_hi - body_lo, 0.08),
                    facecolor=c,
                    edgecolor=c,
                    alpha=0.95,
                    zorder=3,
                )
            )

    if np.isfinite(pm_h):
        ax.axhline(pm_h, color='#64B5F6', linestyle='-', linewidth=1.35, zorder=2, alpha=0.95, label='Prior month high')
    if np.isfinite(pm_l):
        ax.axhline(pm_l, color='#FFB74D', linestyle='-', linewidth=1.35, zorder=2, alpha=0.95, label='Prior month low')

    if np.isfinite(orb_rh) and np.isfinite(orb_rl):
        ax.axhline(orb_rh, color='#90A4AE', linestyle='--', linewidth=1.0, zorder=2, alpha=0.8, label='ORB high')
        ax.axhline(orb_rl, color='#78909C', linestyle='--', linewidth=1.0, zorder=2, alpha=0.8, label='ORB low')

    cross_bits = []
    if cross_h:
        cross_bits.append('cross prior-month high')
    if cross_l:
        cross_bits.append('cross prior-month low')
    cross_txt = ' · '.join(cross_bits) if cross_bits else '—'

    ax.set_title(
        f'MNQ {session_day}  ·  5 m  ·  midnight–16:00 NY  ·  monthly ORB bias: {bias_bucket}',
        color='white',
        fontsize=11,
    )
    ax.set_xlabel('NY time', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.25, color='#546E7A')

    ax.text(
        0.01,
        0.02,
        cross_txt + f'\nPrior month H={pm_h:.2f}  L={pm_l:.2f}',
        transform=ax.transAxes,
        va='bottom',
        ha='left',
        fontsize=8,
        color='#ECEFF1',
        bbox=dict(boxstyle='round,pad=0.35', fc='#1B263B', ec='#37474F', alpha=0.92),
    )

    ax.legend(loc='upper left', facecolor='#1B263B', edgecolor='#37474F', labelcolor='#ECEFF1', fontsize=8)

    if not bars5.empty:
        ax.set_xlim(mdates.date2num(t0) - 1 / (24 * 12), mdates.date2num(t1) + 5 / (24 * 60))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))

    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor='#0D1B2A')
    plt.close(fig)


def iter_candidate_dates(
    daily: pd.DataFrame,
    pm_h: pd.Series,
    pm_l: pd.Series,
    d0: pd.Timestamp,
    d1: pd.Timestamp,
) -> list[pd.Timestamp]:
    """Days in [d0,d1] whose **daily** range touches prior-month H or L."""
    sub = daily[(daily.index >= d0) & (daily.index <= d1)].copy()
    out: list[pd.Timestamp] = []
    for ts in sub.index:
        ph = float(pm_h.loc[ts])
        pl = float(pm_l.loc[ts])
        if not (np.isfinite(ph) or np.isfinite(pl)):
            continue
        row = sub.loc[ts]
        lo = float(row['low'])
        hi = float(row['high'])
        ok = False
        if np.isfinite(ph) and daily_touches_level(lo, hi, ph):
            ok = True
        if np.isfinite(pl) and daily_touches_level(lo, hi, pl):
            ok = True
        if ok:
            out.append(ts)
    return out


def write_index(rows: list[dict], path: Path, *, n_cross_detected: int) -> None:
    lines = [
        '# Monthly interactions — prior month H/L crosses',
        '',
        f'**Sessions with 5 m cross (high and/or low), this run:** {n_cross_detected}',
        f'**Charts in this index:** {len(rows)}',
        '',
    ]
    if len(rows) < n_cross_detected:
        lines.append(
            f'*Listing capped by `--max-charts` ({len(rows)} of {n_cross_detected} crosses).*'
        )
        lines.append('')
    lines.extend(
        [
            '5 m candles **00:00–16:00 NY**. Horizontal lines: **prior calendar month** high/low. '
            'Shaded band: **ORB [09:30, 09:45)** on 1 m. '
            'Folders: **`YYYY`** (one folder per year).',
            '',
            '| Date | Cross high | Cross low | ORB bias bucket | Chart |',
            '|---|:---:|:---:|---|---|',
        ]
    )
    for r in rows:
        fn = r['file'].replace('\\', '/')
        lines.append(
            f"| {r['date']} | {'Y' if r['cross_h'] else ''} | {'Y' if r['cross_l'] else ''} "
            f"| `{r['bucket']}` | [{fn}]({fn}) |"
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--1m', dest='m1', type=Path, default=DEFAULT_M1)
    ap.add_argument('--start', default=None, help='First session date (YYYY-MM-DD), inclusive')
    ap.add_argument('--end', default=None, help='Last session date (YYYY-MM-DD), inclusive')
    ap.add_argument('--out-dir', type=Path, default=HERE, help='PNG + INDEX output directory')
    ap.add_argument('--max-charts', type=int, default=0, help='Cap PNG count (0 = no cap)')
    ap.add_argument(
        '--count-only',
        action='store_true',
        help='Run cross detection + print totals only (no PNGs / INDEX)',
    )
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(14.0, 7.5))
    args = ap.parse_args()

    if not args.daily_dbn.is_file():
        print(f'Missing daily DBN: {args.daily_dbn}', file=sys.stderr)
        return 1
    if not args.m1.is_file():
        print(f'Missing 1m CSV: {args.m1}', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)
    monthly_full = monthly_high_low(daily)
    pm_h_ser, pm_l_ser = prior_month_levels_series(daily, monthly_full)

    d0 = pd.to_datetime(args.start).normalize() if args.start else daily.index.min()
    d1 = pd.to_datetime(args.end).normalize() if args.end else daily.index.max()
    out_root = args.out_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    candidates_ts = iter_candidate_dates(daily, pm_h_ser, pm_l_ser, d0, d1)
    need_dates = {ts.date() for ts in candidates_ts}
    print(f'Daily-touch candidates in range: {len(need_dates)} sessions', flush=True)

    if not need_dates:
        print('No candidate days (prior month levels vs daily range).', file=sys.stderr)
        return 1

    tmin, tmax = min(need_dates), max(need_dates)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    index_rows: list[dict] = []
    n_written = 0
    n_cross = 0

    for ts_sess in sorted(candidates_ts):
        d = ts_sess.date()
        day_raw = gby.get(d)
        if day_raw is None or day_raw.empty:
            continue

        pm_h = float(pm_h_ser.loc[ts_sess])
        pm_l = float(pm_l_ser.loc[ts_sess])
        bars5 = resample_5m_midnight_to_1600(day_raw, d)
        if bars5.empty:
            continue

        cross_h = np.isfinite(pm_h) and cross_detect_5m(bars5, pm_h)
        cross_l = np.isfinite(pm_l) and cross_detect_5m(bars5, pm_l)
        if not (cross_h or cross_l):
            continue

        n_cross += 1

        if args.count_only:
            continue

        if args.max_charts and n_written >= args.max_charts:
            continue

        orb_rh, orb_rl = orb_high_low_1m(day_raw, d)
        b = monthly_orb_bias_for_session_date(d, daily)
        fname = f'{d.isoformat()}.png'
        rel_dir = chart_out_dir(out_root, d)
        out_path = rel_dir / fname
        rel_file = out_path.relative_to(out_root).as_posix()

        draw_chart(
            bars5,
            d,
            pm_h,
            pm_l,
            orb_rh,
            orb_rl,
            b.bucket,
            cross_h,
            cross_l,
            out_path,
            dpi=args.dpi,
            figsize=tuple(args.figsize),
        )
        index_rows.append(
            {
                'date': d.isoformat(),
                'cross_h': cross_h,
                'cross_l': cross_l,
                'bucket': b.bucket,
                'file': rel_file,
            }
        )
        n_written += 1

    print(f'Sessions with 5 m cross (high and/or low): {n_cross}', flush=True)

    if args.count_only:
        return 0

    print(f'Charts written: {n_written}', flush=True)
    if index_rows:
        write_index(index_rows, out_root / 'INDEX.md', n_cross_detected=n_cross)
        print(f'Wrote {out_root / "INDEX.md"}', flush=True)
    else:
        print('No charts after intraday cross filter.', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
