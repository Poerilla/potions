#!/usr/bin/env python3
"""
MNQ hourly candles **00:00–16:00 NY** per calendar session day, with **NY midnight open**
( first 1 m open in 00:00–00:14 ET ) drawn as a horizontal reference.

- One PNG per session (under ``{out_dir}/{YYYY}/``).
- Default: last **100** Mon–Fri session dates with data (see ``--last-n``).
- 1 m source: Databento DBN (same default path as other MNQ case studies).

Example::

  python3 build_midnight_open_hourly_charts.py --last-n 100 --out-dir ./charts_out
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from pathlib import Path

import databento as db
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
POTIONS_ROOT = MNQ_ROOT.parent
DEFAULT_DBN = MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
DEFAULT_DBN_NQ = POTIONS_ROOT / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'

INSTRUMENT_DBN: dict[str, Path] = {
    'mnq': DEFAULT_DBN,
    'nq': DEFAULT_DBN_NQ,
}

NY = pytz.timezone('America/New_York')
SESSION_LO = time(0, 0)
SESSION_HI = time(16, 0)
ORB_LO = time(9, 30)
ORB_HI = time(9, 45)


def _symbol_mask(series: pd.Series, instrument: str) -> pd.Series:
    inst = instrument.lower()
    if inst == 'mnq':
        return series.str.startswith('MNQ', na=False)
    if inst == 'nq':
        return series.str.startswith('NQ', na=False) & ~series.str.startswith('MNQ', na=False)
    if inst == 'es':
        return series.str.startswith('ES', na=False) & ~series.str.startswith('MES', na=False)
    if inst == 'mes':
        return series.str.startswith('MES', na=False)
    if inst == 'ym':
        return series.str.startswith('YM', na=False) & ~series.str.startswith('MYM', na=False)
    if inst == 'mym':
        return series.str.startswith('MYM', na=False)
    raise ValueError(f'Unknown instrument {instrument!r}')


def load_1m_by_ny_date(dbn_path: Path, instrument: str = 'mnq') -> dict[date, pd.DataFrame]:
    """Front-month outrights for ``instrument``; partitioned by **NY calendar date** of bar."""
    inst = instrument.lower()
    print(f'Loading DBN {dbn_path} ({inst.upper()}) ...', flush=True)
    store = db.DBNStore.from_file(str(dbn_path))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[_symbol_mask(df['symbol'], inst)].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['d'] = df['ts_event'].dt.date
    fm = (
        df.groupby(['d', 'symbol'])['volume']
        .sum()
        .groupby(level='d')
        .idxmax()
        .apply(lambda x: x[1])
        .to_dict()
    )
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['d']), axis=1)]
    df = df.set_index('ts_event').sort_index()
    gby = {d: g.drop(columns=['d'], errors='ignore') for d, g in df.groupby(df.index.date)}
    print(f'  {len(gby):,} NY dates with bars', flush=True)
    return gby


def load_mnq_1m_by_ny_date(dbn_path: Path) -> dict[date, pd.DataFrame]:
    """Alias for :func:`load_1m_by_ny_date` with ``instrument='mnq'``."""
    return load_1m_by_ny_date(dbn_path, 'mnq')


def slice_session_1m(day_1m: pd.DataFrame | None, session_day: date) -> pd.DataFrame:
    """1 m rows for ``session_day`` in **[00:00, 16:00) NY**."""
    if day_1m is None or day_1m.empty:
        return pd.DataFrame()
    return day_1m[
        day_1m.index.map(lambda t: (t.date() == session_day and SESSION_LO <= t.time() < SESSION_HI))
    ]


def _resample_session_ohlcv(x: pd.DataFrame, session_day: date, rule: str) -> pd.DataFrame:
    """Resample session 1 m OHLCV with anchor at **00:00 NY** on ``session_day``."""
    if x.empty:
        return x
    anchor = NY.localize(datetime.combine(session_day, SESSION_LO))
    kw: dict = {'label': 'left', 'origin': anchor}
    try:
        r = x.resample(rule, **kw, closed='left')
    except TypeError:
        r = x.resample(rule, **kw, inclusive='left')
    return (
        r.agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
        )
        .dropna(subset=['open'])
    )


def resample_1h_midnight_to_1600(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return _resample_session_ohlcv(slice_session_1m(day_1m, session_day), session_day, '1h')


def resample_15m_midnight_to_1600(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return _resample_session_ohlcv(slice_session_1m(day_1m, session_day), session_day, '15min')


def resample_4h_midnight_to_1600(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return _resample_session_ohlcv(slice_session_1m(day_1m, session_day), session_day, '4h')


def resample_daily_session_bar(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    """One OHLC bar for **[00:00, 16:00) NY** (session “daily” candle)."""
    x = slice_session_1m(day_1m, session_day)
    if x.empty:
        return x
    anchor = NY.localize(datetime.combine(session_day, SESSION_LO))
    return pd.DataFrame(
        {
            'open': [float(x.iloc[0]['open'])],
            'high': [float(x['high'].max())],
            'low': [float(x['low'].min())],
            'close': [float(x.iloc[-1]['close'])],
        },
        index=pd.DatetimeIndex([anchor], tz=NY),
    )


def resample_session_bars(day_1m: pd.DataFrame, session_day: date, bar_tf: str) -> pd.DataFrame:
    """``bar_tf`` in ``1h``, ``4h``, ``1d`` (session aggregate)."""
    tf = bar_tf.lower()
    if tf == '1h':
        return resample_1h_midnight_to_1600(day_1m, session_day)
    if tf == '4h':
        return resample_4h_midnight_to_1600(day_1m, session_day)
    if tf in ('1d', 'daily'):
        return resample_daily_session_bar(day_1m, session_day)
    raise ValueError(f'Unknown bar_tf {bar_tf!r}')


def ny_midnight_open_px(sess_1m: pd.DataFrame) -> float:
    """Open of first 1 m in **[00:00, 00:15) NY** on this slice."""
    if sess_1m.empty:
        return float('nan')
    try:
        w = sess_1m.between_time('00:00', '00:14', inclusive='left')
    except (TypeError, ValueError):
        w = sess_1m[sess_1m.index.map(lambda t: t.hour == 0 and t.minute < 15)]
    if w.empty:
        return float('nan')
    return float(w.sort_index().iloc[0]['open'])


def orb_high_low_1m(sess_1m: pd.DataFrame, session_day: date) -> tuple[float, float]:
    orb = sess_1m[sess_1m.index.map(lambda t: t.date() == session_day and ORB_LO <= t.time() < ORB_HI)]
    if orb.empty:
        return float('nan'), float('nan')
    return float(orb['high'].max()), float(orb['low'].min())


def draw_hourly_chart(
    bars1h: pd.DataFrame,
    session_day: date,
    midnight_open: float,
    orb_h: float,
    orb_l: float,
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> None:
    fig, ax = plt.subplots(figsize=figsize, facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    if not bars1h.empty:
        xs = mdates.date2num(list(bars1h.index.to_pydatetime()))
        width = (1.0 / 24.0) * 0.72 if len(xs) > 1 else 0.04
        for x, (_, row) in zip(xs, bars1h.iterrows()):
            o, h_, l, c = (float(row['open']), float(row['high']), float(row['low']), float(row['close']))
            col = '#26A69A' if c >= o else '#EF5350'
            ax.vlines(x, l, h_, color=col, linewidth=0.95, zorder=3, alpha=0.92)
            body_lo = min(o, c)
            body_hi = max(abs(c - o), 0.08)
            ax.add_patch(
                mpatches.Rectangle(
                    (x - width / 2, body_lo),
                    width,
                    body_hi,
                    facecolor=col,
                    edgecolor=col,
                    alpha=0.92,
                    zorder=4,
                )
            )

        t_orb0 = NY.localize(datetime.combine(session_day, ORB_LO))
        t_orb1 = NY.localize(datetime.combine(session_day, ORB_HI))
        ax.axvspan(
            mdates.date2num(t_orb0),
            mdates.date2num(t_orb1),
            color='#1F4E79',
            alpha=0.32,
            zorder=0,
        )

    if np.isfinite(midnight_open):
        ax.axhline(
            midnight_open,
            color='#26C6DA',
            linestyle='-',
            linewidth=1.45,
            zorder=2,
            alpha=0.95,
            label='NY midnight open',
        )

    if np.isfinite(orb_h) and np.isfinite(orb_l):
        ax.axhline(orb_h, color='#90A4AE', linestyle='--', linewidth=0.9, zorder=2, alpha=0.65, label='ORB high')
        ax.axhline(orb_l, color='#78909C', linestyle='--', linewidth=0.9, zorder=2, alpha=0.65, label='ORB low')

    mo_txt = f'{midnight_open:,.2f}' if np.isfinite(midnight_open) else 'n/a'
    ax.set_title(
        f'MNQ {session_day}  ·  1 h  ·  00:00–16:00 NY  ·  midnight O = {mo_txt}',
        color='white',
        fontsize=11,
    )
    ax.set_xlabel('NY time', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.22, color='#546E7A')
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(
            handles,
            labels,
            loc='upper left',
            facecolor='#1B263B',
            edgecolor='#37474F',
            labelcolor='#ECEFF1',
            fontsize=8,
        )

    if not bars1h.empty:
        ax.set_xlim(
            mdates.date2num(bars1h.index.min()) - 1 / (24 * 12),
            mdates.date2num(bars1h.index.max()) + 1 / (24 * 8),
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))

    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor='#0D1B2A')
    plt.close(fig)


def candidate_weekday_dates(gby: dict[date, pd.DataFrame]) -> list[date]:
    """Mon–Fri NY dates that have at least one 1 m bar in the session window."""
    out: list[date] = []
    for d in sorted(gby.keys(), reverse=True):
        if d.weekday() >= 5:
            continue
        raw = gby.get(d)
        if raw is None or raw.empty:
            continue
        if not slice_session_1m(raw, d).empty:
            out.append(d)
    out.sort(reverse=True)
    return out


def write_index(rows: list[dict], path: Path) -> None:
    lines = [
        '# MNQ hourly charts — midnight open reference',
        '',
        f'**Charts:** {len(rows)}',
        '',
        'Each figure: **1 h OHLC** for **00:00–16:00 NY**, horizontal **NY midnight open** '
        '(first 1 m open in 00:00–00:14), shaded **ORB [09:30, 09:45)**.',
        '',
        '| Session (NY) | Chart |',
        '|---|---|',
    ]
    for r in rows:
        fn = r['file'].replace('\\', '/')
        lines.append(f"| {r['date']} | [{fn}]({fn}) |")
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN, help='1 m OHLCV DBN path')
    ap.add_argument('--out-dir', type=Path, default=HERE / 'charts', help='Output root (year subfolders)')
    ap.add_argument('--last-n', type=int, default=100, help='Most recent N Mon–Fri session days to chart')
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(14.0, 7.0))
    args = ap.parse_args()

    if not args.dbn.is_file():
        print(f'Missing DBN: {args.dbn}', file=sys.stderr)
        return 1

    gby = load_mnq_1m_by_ny_date(args.dbn.resolve())
    cand = candidate_weekday_dates(gby)
    if len(cand) < args.last_n:
        picked = cand
    else:
        picked = cand[: args.last_n]

    out_root = args.out_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict] = []

    for d in sorted(picked):
        day_raw = gby.get(d)
        sess = slice_session_1m(day_raw, d)
        bars1h = resample_1h_midnight_to_1600(day_raw, d)
        if bars1h.empty:
            continue
        mo = ny_midnight_open_px(sess)
        oh, ol = orb_high_low_1m(sess, d)
        rel = out_root / str(d.year) / f'{d.isoformat()}_mnq_1h_midnight_open.png'
        draw_hourly_chart(bars1h, d, mo, oh, ol, rel, dpi=args.dpi, figsize=tuple(args.figsize))
        index_rows.append({'date': d.isoformat(), 'file': str(rel.relative_to(out_root))})
        print(rel, flush=True)

    write_index(index_rows, out_root / 'INDEX.md')
    print(f'Wrote {len(index_rows)} charts under {out_root}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
