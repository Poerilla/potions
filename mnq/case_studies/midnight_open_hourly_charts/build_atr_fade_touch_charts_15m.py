#!/usr/bin/env python3
"""
Annotated **15 m** charts for **atr_fade_touch** — 50 biggest wins and 50 biggest losses.

Example::

  python3 build_atr_fade_touch_charts_15m.py --n-wins 50 --n-losses 50
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import pytz
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
import chart_draw as cd  # noqa: E402
from backtest_midnight_open_flip import Trade  # noqa: E402

NY = pytz.timezone('America/New_York')
BAR_MINUTES = 15
DEFAULT_DBN = mdata.DEFAULT_DBN
DEFAULT_TRADES = HERE / 'backtest_midnight_open_flip_trades_mnq_atr_fade_touch.csv'
OUT_DEFAULT = HERE / 'charts_atr_fade_touch_15m'


def _xnum(ts: pd.Timestamp) -> float:
    return mdates.date2num(pd.Timestamp(ts))


def bands_for_trade(M: float, side: str, entry_px: float) -> tuple[float, float, float, float]:
    if side == 'short':
        atr = (entry_px - M) / 2.0
    else:
        atr = (M - entry_px) / 2.0
    entry_up = M + 2.0 * atr
    entry_lo = M - 2.0 * atr
    if side == 'short':
        return entry_up, entry_lo, M + 3.0 * atr, M - 2.0 * atr
    return entry_up, entry_lo, M - 3.0 * atr, M + 2.0 * atr


def _slug_ts(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime('%H-%M')


def draw_trade_chart(
    bars15: pd.DataFrame,
    session_day: date,
    M: float,
    focus: Trade,
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> None:
    upper, lower, sl_px, tp_px = bands_for_trade(M, focus.side, focus.entry_px)
    fig, ax = cd.new_session_figure(figsize)
    cd.draw_session_candles(ax, bars15, bar_minutes=BAR_MINUTES)

    ax.axhline(M, color='#26C6DA', linewidth=1.45, zorder=2, alpha=0.95)
    ax.axhline(upper, color='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.85)
    ax.axhline(lower, color='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.85)
    ax.axhline(sl_px, color='#EF5350', linestyle='-.', linewidth=1.0, alpha=0.75)
    ax.axhline(tp_px, color='#66BB6A', linestyle='-.', linewidth=1.0, alpha=0.75)
    ax.axvline(_xnum(focus.entry_time), color='#FFEB3B', linewidth=1.2, alpha=0.85, linestyle='-')

    et, xt = pd.Timestamp(focus.entry_time), pd.Timestamp(focus.exit_time)
    ec = '#66BB6A' if focus.side == 'long' else '#EF5350'
    xc = '#A5D6A7' if focus.pnl_usd >= 0 else '#EF9A9A'
    ax.scatter(
        _xnum(et),
        focus.entry_px,
        marker='^' if focus.side == 'long' else 'v',
        s=95,
        c=ec,
        zorder=8,
        edgecolors='white',
        linewidths=0.6,
    )
    ax.scatter(_xnum(xt), focus.exit_px, marker='x', s=70, c=xc, zorder=8, linewidths=1.2)
    ax.annotate(
        f'{focus.reason_exit} ${focus.pnl_usd:+.0f}',
        (_xnum(xt), focus.exit_px),
        fontsize=8,
        color=xc,
        xytext=(6, 6),
        textcoords='offset points',
    )

    atr = (upper - M) / 2.0
    ax.set_title(
        f'MNQ {session_day}  ·  atr_fade_touch  ·  15m  ·  {focus.side.upper()}  ·  '
        f'{focus.reason_exit}  ·  ${focus.pnl_usd:+.0f}  ·  M={M:,.2f}  ATR={atr:.1f}',
        color='white',
        fontsize=10,
    )
    cd.style_session_ax(ax, bars15, ny=NY, bar_minutes=BAR_MINUTES)
    ax.legend(
        handles=[
            Line2D([0], [0], color='#26C6DA', linewidth=2, label='Midnight M'),
            Line2D([0], [0], color='#FFB74D', linewidth=1.5, linestyle='--', label='M ± 2×ATR entry'),
            Line2D([0], [0], color='#EF5350', linewidth=1.5, linestyle='-.', label='SL M ± 3×ATR'),
            Line2D([0], [0], color='#66BB6A', linewidth=1.5, linestyle='-.', label='TP opposite 2×ATR'),
            Line2D([0], [0], color='#FFEB3B', linewidth=1.5, label='Entry'),
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


def row_to_trade(row: dict) -> Trade:
    d = date.fromisoformat(str(row['session']))
    return Trade(
        d,
        str(row['side']),
        pd.Timestamp(row['entry_time']),
        float(row['entry_px']),
        pd.Timestamp(row['exit_time']),
        float(row['exit_px']),
        str(row['reason_exit']),
        2.0,
    )


def write_index(rows: list[dict], path: Path) -> None:
    lines = [
        '# atr_fade_touch — MNQ **15m** review charts',
        '',
        f'**Charts:** {len(rows)} (50 wins + 50 losses by P&L)',
        '',
        'Session **[00:00, 16:00) NY** in **15-minute** bars. Same levels as 1h charts.',
        '',
        '| Bucket | Session | Side | P&L | Exit | Chart |',
        '|---|---|---|---:|---|---|',
    ]
    for r in sorted(rows, key=lambda x: (-abs(float(x['pnl'])), x['date'])):
        fn = r['file'].replace('\\', '/')
        lines.append(
            f"| {r['bucket']} | {r['date']} | {r['side']} | {r['pnl']} | {r['reason']} | [{fn}]({fn}) |"
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_TRADES)
    ap.add_argument('--out-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--n-wins', type=int, default=50)
    ap.add_argument('--n-losses', type=int, default=50)
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(16.0, 7.5))
    args = ap.parse_args()

    if not args.trades_csv.is_file() or not args.dbn.is_file():
        print('Missing trades CSV or DBN', file=sys.stderr)
        return 1

    df = pd.read_csv(args.trades_csv)
    df['pnl_usd'] = df['pnl_usd'].astype(float)
    wins = df.nlargest(args.n_wins, 'pnl_usd')
    losses = df.nsmallest(args.n_losses, 'pnl_usd')

    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    bars_cache: dict[date, pd.DataFrame] = {}
    index_rows: list[dict] = []

    def render_bucket(subdf: pd.DataFrame, bucket: str) -> None:
        for _, row in subdf.iterrows():
            t = row_to_trade(row.to_dict())
            d = t.session
            raw = gby.get(d)
            if raw is None:
                continue
            if d not in bars_cache:
                b = mdata.resample_15m_midnight_to_1600(raw, d)
                bars_cache[d] = b.sort_index() if b is not None else pd.DataFrame()
            bars15 = bars_cache[d]
            if bars15.empty:
                continue
            sess = mdata.slice_session_1m(raw, d)
            M = mdata.ny_midnight_open_px(sess)
            subdir = 'wins' if bucket == 'win' else 'losses'
            fname = f'{d.isoformat()}_{_slug_ts(t.entry_time)}_{t.side}_pnl{t.pnl_usd:+.0f}.png'
            fname = re.sub(r'[^\w.\-+]', '_', fname)
            out_path = args.out_dir / subdir / str(d.year) / fname
            draw_trade_chart(bars15, d, M, t, out_path, dpi=args.dpi, figsize=tuple(args.figsize))
            index_rows.append(
                {
                    'bucket': bucket,
                    'date': d.isoformat(),
                    'side': t.side,
                    'pnl': f'{t.pnl_usd:.0f}',
                    'reason': t.reason_exit,
                    'file': str(out_path.relative_to(args.out_dir)),
                }
            )
            print(out_path, flush=True)

    render_bucket(wins, 'win')
    render_bucket(losses, 'loss')
    write_index(index_rows, args.out_dir / 'INDEX.md')
    print(f'Wrote {len(index_rows)} charts → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
