#!/usr/bin/env python3
"""
Annotated **1 h** charts for **weekly_baseline_1d** (session daily vs weekly open **W**).

Shows: weekly open **W**, ½ prior-week-range TP band, entries/exits from backtest CSV.

Example::

  python3 build_weekly_baseline_1d_charts.py --last-n 100
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
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
    Trade,
    build_week_context_by_day,
)

NY = pytz.timezone('America/New_York')
DEFAULT_DBN = mdata.DEFAULT_DBN
DEFAULT_TRADES = HERE / 'backtest_midnight_open_flip_trades_mnq_weekly_baseline_1d.csv'
OUT_DEFAULT = HERE / 'charts_weekly_baseline_1d'


def _xnum(ts: pd.Timestamp) -> float:
    return mdates.date2num(pd.Timestamp(ts))


def half_week_from_trade(side: str, entry_px: float, exit_px: float, reason: str) -> float:
    if reason == 'tp_half_week':
        return abs(exit_px - entry_px)
    return float('nan')


def draw_chart(
    bars1h: pd.DataFrame,
    session_day: date,
    W: float,
    half_range: float,
    trades: list[Trade],
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> None:
    fig, ax = cd.new_session_figure(figsize)
    cd.draw_1h_candles(ax, bars1h)

    ax.axhline(W, color='#26C6DA', linewidth=1.45, zorder=2, alpha=0.95)

    if np.isfinite(half_range) and half_range > 0:
        ax.axhline(W + half_range, color='#81C784', linestyle='--', linewidth=1.0, alpha=0.8)
        ax.axhline(W - half_range, color='#81C784', linestyle='--', linewidth=1.0, alpha=0.8)
        ax.text(
            _xnum(bars1h.index.max()) if not bars1h.empty else 0,
            W + half_range,
            f'  W±½wk ({half_range:.1f})',
            color='#81C784',
            fontsize=8,
            va='bottom',
        )

    for t in trades:
        et, xt = pd.Timestamp(t.entry_time), pd.Timestamp(t.exit_time)
        xe, xx = _xnum(et), _xnum(xt)
        ec = '#66BB6A' if t.side == 'long' else '#EF5350'
        xc = '#A5D6A7' if t.pnl_usd >= 0 else '#EF9A9A'
        ax.scatter(
            xe,
            t.entry_px,
            marker='^' if t.side == 'long' else 'v',
            s=90,
            c=ec,
            zorder=8,
            edgecolors='white',
            linewidths=0.6,
        )
        ax.scatter(xx, t.exit_px, marker='x', s=70, c=xc, zorder=8, linewidths=1.2)
        hw = half_week_from_trade(t.side, t.entry_px, t.exit_px, t.reason_exit)
        if np.isfinite(hw) and hw > 0:
            tp = t.entry_px + hw if t.side == 'long' else t.entry_px - hw
            ax.axhline(tp, color='#AED581', linestyle=':', linewidth=0.9, alpha=0.65)
        ax.annotate(
            f'{t.reason_exit} {t.pnl_usd:+.0f}',
            (xx, t.exit_px),
            fontsize=7,
            color=xc,
            xytext=(4, 4),
            textcoords='offset points',
        )

    pnl_day = sum(t.pnl_usd for t in trades)
    ax.set_title(
        f'MNQ {session_day}  ·  weekly_baseline_1d  ·  1h  ·  W={W:,.2f}  ·  day P&L ${pnl_day:,.0f}',
        color='white',
        fontsize=10,
    )
    cd.style_session_ax(ax, bars1h, ny=NY)
    ax.legend(
        handles=[
            Line2D([0], [0], color='#26C6DA', linewidth=2, label='Weekly open W'),
            Line2D([0], [0], color='#81C784', linewidth=1.5, linestyle='--', label='W ± ½ prior-week range'),
            Line2D([0], [0], marker='^', color='#66BB6A', linestyle='None', label='Long @ W'),
            Line2D([0], [0], marker='v', color='#EF5350', linestyle='None', label='Short @ W'),
        ],
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=8,
    )

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
        '# weekly_baseline_1d — MNQ hourly charts',
        '',
        f'**Charts:** {len(rows)}',
        '',
        'Session **daily** bar vs **weekly open W** (Mon-start week). Limit @ W; '
        'TP = entry ± **½ prior-week range** on 1m; flip on daily close through W.',
        '',
        '| Session | Day P&L | Chart |',
        '|---|---:|---|',
    ]
    for r in sorted(rows, key=lambda x: x['date']):
        fn = r['file'].replace('\\', '/')
        lines.append(f"| {r['date']} | {r.get('pnl_day', '')} | [{fn}]({fn}) |")
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_TRADES)
    ap.add_argument('--out-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--last-n', type=int, default=100)
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(14.0, 7.5))
    args = ap.parse_args()

    if not args.dbn.is_file():
        print(f'Missing DBN: {args.dbn}', file=sys.stderr)
        return 1

    trades_raw = load_trades_by_session(args.trades_csv)
    if not trades_raw:
        print(f'No trades in {args.trades_csv}', file=sys.stderr)
        return 1

    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    week_ctx = build_week_context_by_day(gby)

    picked = sorted(trades_raw.keys(), reverse=True)[: args.last_n]
    index_rows: list[dict] = []

    for d in sorted(picked, reverse=True):
        raw = gby.get(d)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, d)
        hourly = mdata.resample_1h_midnight_to_1600(raw, d)
        if hourly is None or hourly.empty:
            continue
        wk = week_ctx.get(d)
        W = float(wk.weekly_open) if wk else float('nan')
        half_range = 0.5 * float(wk.prior_week_range) if wk and np.isfinite(wk.prior_week_range) else float('nan')

        trades: list[Trade] = []
        for row in trades_raw.get(d, []):
            trades.append(
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

        out_path = args.out_dir / str(d.year) / f'{d.isoformat()}_weekly_baseline_1d.png'
        draw_chart(
            hourly.sort_index(),
            d,
            W,
            half_range,
            trades,
            out_path,
            dpi=args.dpi,
            figsize=tuple(args.figsize),
        )
        pnl_day = sum(t.pnl_usd for t in trades)
        index_rows.append(
            {
                'date': d.isoformat(),
                'file': str(out_path.relative_to(args.out_dir)),
                'pnl_day': f'{pnl_day:.0f}',
            }
        )
        print(out_path, flush=True)

    write_index(index_rows, args.out_dir / 'INDEX.md')
    print(f'Wrote {len(index_rows)} charts → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
