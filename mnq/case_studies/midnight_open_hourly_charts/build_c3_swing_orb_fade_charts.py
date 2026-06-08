#!/usr/bin/env python3
"""
Side-by-side **C3 swing ORB fade** review charts (15m session + trade markers).

**Left:** C1 · C2 · C3 session-daily (C2 H/L only).
**Right:** C3 session **15m** with intraday **hit**, **15m swing** confirm, **ORB** H/L,
v2b **TP** / far **SL**, and trade entry/exit.

Example::

  python3 build_c3_swing_orb_fade_charts.py --n-wins 50 --n-losses 50
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
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
from backtest_c3_swing_orb_fade import (  # noqa: E402
    first_intraday_hit_ts,
    first_qualifying_swing,
)
from backtest_midnight_open_flip import Trade, orb_v2b_targets  # noqa: E402
from build_c3_session_study_charts import (  # noqa: E402
    BG,
    GREEN,
    RED,
    TEAL,
    YELLOW,
    daily_c2_high_low,
    draw_daily_candles,
    session_daily_bar,
)

NY = pytz.timezone('America/New_York')
DEFAULT_DBN = mdata.DEFAULT_DBN
DEFAULT_SETUPS = HERE.parent / 'daily_candlestick_theory' / 'setups.csv'
DEFAULT_TRADES = HERE / 'backtest_c3_swing_orb_fade_trades_mnq.csv'
OUT_DEFAULT = HERE / 'charts_c3_swing_orb_fade'


def _xnum(ts: pd.Timestamp) -> float:
    return mdates.date2num(pd.Timestamp(ts))


def orb_trade_levels(
    sess_1m: pd.DataFrame,
    session_day: date,
    side: str,
) -> tuple[float, float, float, float] | None:
    """``(rh, rl, tp, sl)`` — v2b break entry, opposite OR boundary stop, v2b extension TP."""
    orb = orb_v2b_targets(sess_1m, session_day)
    if orb is None:
        return None
    rh, rl, _rv, target_long, target_short = orb
    if side == 'short':
        return rh, rl, target_short, rh
    return rh, rl, target_long, rl


def draw_pair_chart(
    setup: pd.Series,
    gby: dict[date, pd.DataFrame],
    trade: Trade,
    out_path: Path,
    *,
    dpi: int,
    figsize: tuple[float, float],
) -> bool:
    c3_day = trade.session
    c1_day = date.fromisoformat(str(setup['c1_date']))
    c2_day = date.fromisoformat(str(setup['c2_date']))
    direction = str(setup['direction'])
    c2_extreme = float(setup['c2_expected_extreme'])
    c2_low = float(setup['c2_low'])

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
    levels = orb_trade_levels(sess, c3_day, trade.side)
    rh = rl = tp_px = sl_px = float('nan')
    if levels:
        rh, rl, tp_px, sl_px = levels

    hit_ts = first_intraday_hit_ts(sess, direction, c2_extreme, c2_low)
    swing = (
        first_qualifying_swing(bars15, hit_ts, direction, c2_extreme, c2_low)
        if hit_ts is not None
        else None
    )

    price_vals = list(triple['low']) + list(triple['high']) + [float(bars15['low'].min()), float(bars15['high'].max())]
    for v in (M, orb_h, orb_l, c2_extreme, c2_low, tp_px, sl_px, trade.entry_px, trade.exit_px):
        if np.isfinite(v):
            price_vals.append(v)
    if swing is not None:
        price_vals.append(swing.price)
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

    draw_daily_candles(ax_triple, triple, width_scale=0.78)
    dates = pd.to_datetime(triple['date'])
    x_nums = mdates.date2num(dates)
    x0, x1 = float(x_nums[0]) - 0.55, float(x_nums[-1]) + 0.55
    daily_c2_high_low(ax_triple, setup, x0, x1)
    c3_x = mdates.date2num(pd.Timestamp(c3_day))
    half = 0.42
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
    if np.isfinite(c2_extreme):
        ax_sess.axhline(c2_extreme, color=YELLOW, linestyle='--', linewidth=1.0, alpha=0.9)
    if np.isfinite(orb_h):
        ax_sess.axhline(orb_h, color='#90A4AE', linestyle='--', linewidth=0.9, alpha=0.65)
    if np.isfinite(orb_l):
        ax_sess.axhline(orb_l, color='#78909C', linestyle='--', linewidth=0.9, alpha=0.65)
    if np.isfinite(tp_px):
        ax_sess.axhline(tp_px, color='#66BB6A', linestyle='-.', linewidth=1.0, alpha=0.8)
    if np.isfinite(sl_px):
        ax_sess.axhline(sl_px, color='#EF5350', linestyle='-.', linewidth=1.0, alpha=0.8)

    if hit_ts is not None:
        ax_sess.axvline(_xnum(hit_ts), color='#EA80FC', linewidth=1.1, alpha=0.85, linestyle='-')
    if swing is not None:
        ax_sess.axvline(_xnum(swing.confirm_ts), color='#81D4FA', linewidth=1.1, alpha=0.85, linestyle='--')
        mk = '^' if swing.kind == 'high' else 'v'
        ax_sess.scatter(
            _xnum(swing.pivot_ts),
            swing.price,
            marker=mk,
            s=72,
            c='#81D4FA',
            zorder=7,
            edgecolors='white',
            linewidths=0.5,
        )

    et, xt = pd.Timestamp(trade.entry_time), pd.Timestamp(trade.exit_time)
    ec = GREEN if trade.side == 'long' else RED
    xc = '#A5D6A7' if trade.pnl_usd >= 0 else '#EF9A9A'
    ax_sess.axvline(_xnum(et), color='#FFEB3B', linewidth=1.2, alpha=0.9)
    ax_sess.scatter(
        _xnum(et),
        trade.entry_px,
        marker='^' if trade.side == 'long' else 'v',
        s=95,
        c=ec,
        zorder=9,
        edgecolors='white',
        linewidths=0.6,
    )
    ax_sess.scatter(_xnum(xt), trade.exit_px, marker='x', s=70, c=xc, zorder=9, linewidths=1.2)
    ax_sess.annotate(
        f'{trade.reason_exit} ${trade.pnl_usd:+.0f}',
        (_xnum(xt), trade.exit_px),
        fontsize=8,
        color=xc,
        xytext=(6, 6),
        textcoords='offset points',
    )

    cd.style_session_ax(ax_sess, bars15, ny=NY, bar_minutes=15)
    c2_lbl = 'C2 extreme (hit lvl)'
    ax_sess.set_title(
        f'C3 {c3_day}  ·  15m  ·  C3 {direction}  ·  fade {trade.side}  ·  '
        f'${trade.pnl_usd:+.0f}',
        color='white',
        fontsize=10,
    )
    ax_sess.set_xlabel('NY time', color='#B0BEC5')

    fig.suptitle(
        f'C3 swing ORB fade #{int(setup["setup_id"])}  ·  '
        f'{c1_day} → {c2_day} → {c3_day}',
        color='white',
        fontsize=11,
        y=0.98,
    )

    legend_elems = [
        Line2D([0], [0], color=TEAL, linewidth=2, label='Midnight M'),
        Line2D([0], [0], color=YELLOW, linewidth=1.5, linestyle='--', label=c2_lbl),
        Line2D([0], [0], color='#90A4AE', linewidth=1.5, linestyle='--', label='ORB H/L'),
        Line2D([0], [0], color='#66BB6A', linewidth=1.5, linestyle='-.', label='TP v2b'),
        Line2D([0], [0], color='#EF5350', linewidth=1.5, linestyle='-.', label='SL opposite OR edge'),
        Line2D([0], [0], color='#EA80FC', linewidth=1.5, label='Intraday hit'),
        Line2D([0], [0], color='#81D4FA', linewidth=1.5, linestyle='--', label='15m swing confirm'),
        Line2D([0], [0], color='#FFEB3B', linewidth=1.5, label='v2b opposite break entry'),
    ]
    ax_sess.legend(
        handles=legend_elems,
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=6.5,
    )

    fig.subplots_adjust(left=0.05, right=0.98, top=0.92, bottom=0.1, wspace=0.08)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return True


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


def _slug_ts(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime('%H-%M')


def write_index(rows: list[dict], path: Path) -> None:
    lines = [
        '# C3 swing ORB fade — review charts',
        '',
        f'**Charts:** {len(rows)}',
        '',
        '**Left:** C1·C2·C3 daily; **C2 H/L**. **Right:** 15m session — hit, swing, ORB fade entry/exit.',
        '',
        '| Bucket | Setup | C3 | C3 dir | Side | P&L | Exit | Chart |',
        '|---|---|---|---|---|---:|---|---|',
    ]
    for r in sorted(rows, key=lambda x: (-abs(float(x['pnl'])), x['date'])):
        fn = r['file'].replace('\\', '/')
        lines.append(
            f"| {r['bucket']} | {r['setup_id']} | {r['date']} | {r['c3_direction']} | "
            f"{r['side']} | {r['pnl']} | {r['reason']} | [{fn}]({fn}) |"
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--setups-csv', type=Path, default=DEFAULT_SETUPS)
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_TRADES)
    ap.add_argument('--out-dir', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--n-wins', type=int, default=50)
    ap.add_argument('--n-losses', type=int, default=50)
    ap.add_argument('--dpi', type=int, default=120)
    ap.add_argument('--figsize', nargs=2, type=float, default=(20.0, 7.5))
    args = ap.parse_args()

    if not args.trades_csv.is_file() or not args.setups_csv.is_file() or not args.dbn.is_file():
        print('Missing trades CSV, setups CSV, or DBN', file=sys.stderr)
        return 1

    setups = pd.read_csv(args.setups_csv)
    setups['c3_date'] = setups['c3_date'].astype(str)
    setup_by_c3 = setups.set_index('c3_date', drop=False)

    df = pd.read_csv(args.trades_csv)
    df['pnl_usd'] = df['pnl_usd'].astype(float)
    wins = df.nlargest(args.n_wins, 'pnl_usd')
    losses = df.nsmallest(args.n_losses, 'pnl_usd')

    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    index_rows: list[dict] = []

    def render_bucket(subdf: pd.DataFrame, bucket: str) -> None:
        for _, row in subdf.iterrows():
            t = row_to_trade(row.to_dict())
            key = t.session.isoformat()
            if key not in setup_by_c3.index:
                print(f'skip {key}: no setup', flush=True)
                continue
            setup = setup_by_c3.loc[key]
            if isinstance(setup, pd.DataFrame):
                setup = setup.iloc[0]
            subdir = 'wins' if bucket == 'win' else 'losses'
            c3_dir = str(row.get('c3_direction', setup['direction']))
            fname = (
                f'{int(setup["setup_id"]):04d}_{c3_dir}_{key}_'
                f'{_slug_ts(t.entry_time)}_{t.side}_pnl{t.pnl_usd:+.0f}.png'
            )
            fname = re.sub(r'[^\w.\-+]', '_', fname)
            out_path = args.out_dir / subdir / str(t.session.year) / fname
            if draw_pair_chart(setup, gby, t, out_path, dpi=args.dpi, figsize=tuple(args.figsize)):
                index_rows.append(
                    {
                        'bucket': bucket,
                        'setup_id': int(setup['setup_id']),
                        'date': key,
                        'c3_direction': c3_dir,
                        'side': t.side,
                        'pnl': f'{t.pnl_usd:.0f}',
                        'reason': t.reason_exit,
                        'file': str(out_path.relative_to(args.out_dir)),
                    }
                )
                print(out_path, flush=True)

    print(f'Loading DBN ...', flush=True)
    render_bucket(wins, 'win')
    render_bucket(losses, 'loss')
    write_index(index_rows, args.out_dir / 'INDEX.md')
    print(f'Wrote {len(index_rows)} charts → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
