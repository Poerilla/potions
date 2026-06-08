#!/usr/bin/env python3
"""
Annotated **1 h** charts for **atr_cross_opp** (fade extension retrace @ midnight open).

Shows: midnight **M**, **M ± ATR** at cross, extension/cross markers, entries/exits from backtest.

Example::

  python3 build_atr_cross_opp_charts.py --last-n 100
  python3 build_atr_cross_opp_charts.py --sessions-with-setup-only
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
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
from backtest_midnight_open_flip import (  # noqa: E402
    ATR_WARMUP_DAYS,
    Trade,
    build_hourly_with_warmup,
    hourly_atr_series,
)

NY = pytz.timezone('America/New_York')
DEFAULT_DBN = mdata.DEFAULT_DBN
DEFAULT_TRADES = HERE / 'backtest_midnight_open_flip_trades_mnq_atr_cross_opp.csv'
OUT_DEFAULT = HERE / 'charts_atr_cross_opp'


@dataclass
class SessionTrace:
    session_day: date
    M: float
    chop: bool = False
    ext_up_ts: pd.Timestamp | None = None
    ext_down_ts: pd.Timestamp | None = None
    cross_ts: pd.Timestamp | None = None
    cross_dir: str | None = None  # 'down' | 'up'
    setup_side: str | None = None
    atr_at_cross: float = float('nan')
    trades: list[Trade] = field(default_factory=list)


def trace_atr_cross_opp_session(
    session_day: date,
    M: float,
    hourly: pd.DataFrame,
    hourly_warm: pd.DataFrame,
) -> SessionTrace:
    """Mirror ``atr_cross_opp`` event detection (no fills)."""
    trace = SessionTrace(session_day=session_day, M=M)
    h = hourly.sort_index()
    if not (np.isfinite(M)) or len(h) < 3 or hourly_warm.empty:
        return trace

    hw = hourly_warm.sort_index()
    atr_all = hourly_atr_series(hw).shift(1)

    extended_up = False
    extended_down = False
    any_extension = False
    closes_below_pre = 0

    for i in range(len(h)):
        row = h.iloc[i]
        ts = h.index[i]
        o, hi, lo, cl = map(float, (row['open'], row['high'], row['low'], row['close']))
        atr = float(atr_all.loc[ts]) if ts in atr_all.index else float('nan')

        if not any_extension:
            if cl < M:
                closes_below_pre += 1
            if closes_below_pre >= 2:
                trace.chop = True
                return trace

        if np.isfinite(atr) and atr > 0:
            if hi >= M + atr - 1e-9 and not extended_up:
                extended_up = True
                any_extension = True
                trace.ext_up_ts = ts
            if lo <= M - atr + 1e-9 and not extended_down:
                extended_down = True
                any_extension = True
                trace.ext_down_ts = ts

        if i == 0:
            continue
        prev_cl = float(h.iloc[i - 1]['close'])
        if extended_up and prev_cl > M and cl < M and trace.cross_ts is None:
            trace.cross_ts = ts
            trace.cross_dir = 'down'
            trace.setup_side = 'short'
            trace.atr_at_cross = atr
        elif extended_down and prev_cl < M and cl > M and trace.cross_ts is None:
            trace.cross_ts = ts
            trace.cross_dir = 'up'
            trace.setup_side = 'long'
            trace.atr_at_cross = atr

    return trace


def _xnum(ts: pd.Timestamp) -> float:
    return mdates.date2num(pd.Timestamp(ts))


def draw_chart(
    bars1h: pd.DataFrame,
    trace: SessionTrace,
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> None:
    M = trace.M
    fig, ax = plt.subplots(figsize=figsize, facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    if not bars1h.empty:
        xs = mdates.date2num(list(bars1h.index.to_pydatetime()))
        width = (1.0 / 24.0) * 0.72 if len(xs) > 1 else 0.04
        for x, (_, row) in zip(xs, bars1h.iterrows()):
            o, h_, l, c = map(float, (row['open'], row['high'], row['low'], row['close']))
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

    ax.axhline(M, color='#26C6DA', linewidth=1.45, zorder=2, alpha=0.95, label='Midnight open M')

    if np.isfinite(trace.atr_at_cross) and trace.atr_at_cross > 0:
        ax.axhline(M + trace.atr_at_cross, color='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.85)
        ax.axhline(M - trace.atr_at_cross, color='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.85)
        ax.text(
            mdates.date2num(bars1h.index.max()) if not bars1h.empty else 0,
            M + trace.atr_at_cross,
            f'  M±ATR({trace.atr_at_cross:.1f})',
            color='#FFB74D',
            fontsize=8,
            va='bottom',
        )

    if trace.ext_up_ts is not None:
        ax.axvline(_xnum(trace.ext_up_ts), color='#AB47BC', linewidth=1.0, alpha=0.55, linestyle=':')
    if trace.ext_down_ts is not None:
        ax.axvline(_xnum(trace.ext_down_ts), color='#7E57C2', linewidth=1.0, alpha=0.55, linestyle=':')

    if trace.cross_ts is not None:
        ax.axvline(_xnum(trace.cross_ts), color='#FFEB3B', linewidth=1.4, alpha=0.9, linestyle='-')

    for t in trace.trades:
        et = pd.Timestamp(t.entry_time)
        xt = pd.Timestamp(t.exit_time)
        xe, xx = _xnum(et), _xnum(xt)
        ec = '#66BB6A' if t.side == 'long' else '#EF5350'
        xc = '#A5D6A7' if t.pnl_usd >= 0 else '#EF9A9A'
        ax.scatter(xe, t.entry_px, marker='^' if t.side == 'long' else 'v', s=90, c=ec, zorder=8, edgecolors='white', linewidths=0.6)
        ax.scatter(xx, t.exit_px, marker='x', s=70, c=xc, zorder=8, linewidths=1.2)
        ax.annotate(
            f'{t.pnl_usd:+.0f}',
            (xx, t.exit_px),
            fontsize=7,
            color=xc,
            xytext=(4, 4),
            textcoords='offset points',
        )

    status = 'CHOP (≥2 closes below M)' if trace.chop else ''
    if trace.setup_side and not trace.chop:
        status = f'fade {trace.setup_side.upper()} after {trace.cross_dir or "?"} cross'
    pnl_day = sum(t.pnl_usd for t in trace.trades)
    ax.set_title(
        f'MNQ {trace.session_day}  ·  atr_cross_opp  ·  1h  ·  M={M:,.2f}  ·  {status}  ·  day P&L ${pnl_day:,.0f}',
        color='white',
        fontsize=10,
    )
    ax.set_xlabel('NY time', color='#B0BEC5')
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.22, color='#546E7A')

    legend_elems = [
        Line2D([0], [0], color='#26C6DA', linewidth=2, label='Midnight open'),
        Line2D([0], [0], color='#FFB74D', linewidth=1.5, linestyle='--', label='M ± ATR @ cross'),
        Line2D([0], [0], color='#FFEB3B', linewidth=1.5, label='Cross bar'),
        Line2D([0], [0], marker='^', color='#66BB6A', linestyle='None', label='Long entry'),
        Line2D([0], [0], marker='v', color='#EF5350', linestyle='None', label='Short entry'),
    ]
    ax.legend(handles=legend_elems, loc='upper left', facecolor='#1B263B', edgecolor='#37474F', labelcolor='#ECEFF1', fontsize=8)

    if not bars1h.empty:
        ax.set_xlim(
            mdates.date2num(bars1h.index.min()) - 1 / (24 * 12),
            mdates.date2num(bars1h.index.max()) + 1 / (24 * 6),
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))

    for spine in ax.spines.values():
        spine.set_color('#37474F')

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor='#0D1B2A')
    plt.close(fig)


def load_trades_by_session(path: Path) -> dict[date, list[dict]]:
    if not path.is_file():
        return {}
    df = pd.read_csv(path)
    out: dict[date, list[dict]] = {}
    for _, row in df.iterrows():
        d = date.fromisoformat(str(row['session']))
        out.setdefault(d, []).append(row.to_dict())
    return out


def write_index(rows: list[dict], path: Path) -> None:
    lines = [
        '# atr_cross_opp — MNQ hourly charts',
        '',
        f'**Charts:** {len(rows)}',
        '',
        'Fade: up-extension + cross down → **short** @ M; down-extension + cross up → **long** @ M. '
        'Chop skip: ≥2 hourly closes **below** M before extension. Yellow = cross bar; '
        'purple = extension; triangles = entries; × = exits.',
        '',
        '| Session | Setup | Day P&L | Chart |',
        '|---|---|---:|---|',
    ]
    for r in rows:
        fn = r['file'].replace('\\', '/')
        lines.append(
            f"| {r['date']} | {r.get('setup', '—')} | {r.get('pnl_day', '')} | [{fn}]({fn}) |"
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_TRADES)
    ap.add_argument('--out-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--last-n', type=int, default=100)
    ap.add_argument(
        '--sessions-with-setup-only',
        action='store_true',
        help='Only chart days with a valid cross/setup (not chop)',
    )
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(14.0, 7.5))
    args = ap.parse_args()

    if not args.dbn.is_file():
        print(f'Missing DBN: {args.dbn}', file=sys.stderr)
        return 1

    trades_raw = load_trades_by_session(args.trades_csv)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    candidates = mdata.candidate_weekday_dates(gby)

    # Prefer recent sessions that appear in backtest CSV
    traded = sorted(trades_raw.keys(), reverse=True)
    pool = traded if traded else candidates
    picked: list[date] = []
    for d in pool:
        if d.weekday() >= 5:
            continue
        picked.append(d)
        if len(picked) >= args.last_n * 3:
            break

    index_rows: list[dict] = []
    written = 0

    for d in sorted(picked, reverse=True):
        if written >= args.last_n:
            break
        raw = gby.get(d)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, d)
        M = mdata.ny_midnight_open_px(sess)
        hourly = mdata.resample_1h_midnight_to_1600(raw, d)
        if hourly is None or len(hourly) < 3:
            continue
        hw = build_hourly_with_warmup(gby, d, warmup_days=ATR_WARMUP_DAYS)
        trace = trace_atr_cross_opp_session(d, M, hourly, hw)

        if args.sessions_with_setup_only and (trace.chop or trace.cross_ts is None):
            continue

        # attach trades from CSV
        for row in trades_raw.get(d, []):
            trace.trades.append(
                Trade(
                    d,
                    str(row['side']),
                    pd.Timestamp(row['entry_time']),
                    float(row['entry_px']),
                    pd.Timestamp(row['exit_time']),
                    float(row['exit_px']),
                    str(row['reason_exit']),
                    2.0,
                )
            )

        out_path = args.out_dir / str(d.year) / f'{d.isoformat()}_atr_cross_opp.png'
        draw_chart(hourly.sort_index(), trace, out_path, dpi=args.dpi, figsize=tuple(args.figsize))
        pnl_day = sum(t.pnl_usd for t in trace.trades)
        index_rows.append(
            {
                'date': d.isoformat(),
                'file': str(out_path.relative_to(args.out_dir)),
                'setup': trace.setup_side or ('chop' if trace.chop else '—'),
                'pnl_day': f'{pnl_day:.0f}',
            }
        )
        written += 1
        print(out_path, flush=True)

    index_rows.sort(key=lambda r: r['date'])
    write_index(index_rows, args.out_dir / 'INDEX.md')
    print(f'Wrote {written} charts → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
