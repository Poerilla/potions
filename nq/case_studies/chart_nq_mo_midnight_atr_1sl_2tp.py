#!/usr/bin/env python3
"""
Chart all MO midnight retest trades · SL 1×ATR / TP 2×ATR (2:1 R:R).

Same entry rules + streak filter (days 1–3 · max 2/month). Exits re-simulated on 15m.

Output::

  nq_mo_midnight_retest/charts/atr_1sl_2tp/winners/
  nq_mo_midnight_retest/charts/atr_1sl_2tp/losers/

Usage::

  python3 nq/case_studies/chart_nq_mo_midnight_atr_1sl_2tp.py
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
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'mnq' / 'case_studies' / 'midnight_open_hourly_charts'))

from backtest_nq_mo_midnight_retest import (  # noqa: E402
    BG,
    BULL_COLOR,
    BEAR_COLOR,
    ETH_FILL,
    GREEN_CANDLE,
    MC_COLOR,
    MO_COLOR,
    RED_CANDLE,
    RTH_CLOSE,
    RTH_FILL,
    RTH_OPEN,
    TradeRecord,
    load_daily,
    shade_rth,
)
from build_midnight_open_hourly_charts import (  # noqa: E402
    DEFAULT_DBN_NQ,
    NY,
    load_1m_by_ny_date,
    resample_15m_midnight_to_1600,
)
from chart_nq_mo_midnight_streak_filter import apply_streak_filter, row_to_trade  # noqa: E402

STUDY = 'atr_1sl_2tp'
SL_MULT = 1.0
TP_MULT = 2.0
ATR_LEN = 14


def build_daily_atr(daily: pd.DataFrame) -> dict[date, float]:
    work = daily.sort_values('date').copy()
    pc = work['close'].shift(1)
    tr = pd.concat(
        [work['high'] - work['low'], (work['high'] - pc).abs(), (work['low'] - pc).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=ATR_LEN, adjust=False, min_periods=ATR_LEN).mean().shift(1)
    return {d: float(v) for d, v in zip(work['date'].dt.date, atr) if pd.notna(v)}


def simulate_exit_atr(bars, side, entry_idx, entry, stop_pts, target_pts):
    stop = entry - stop_pts if side == 'long' else entry + stop_pts
    target = entry + target_pts if side == 'long' else entry - target_pts
    for j in range(entry_idx, len(bars)):
        h, l = float(bars.iloc[j]['high']), float(bars.iloc[j]['low'])
        if side == 'long':
            if l <= stop:
                return -stop_pts, 'stop', j, stop
            if h >= target:
                return target_pts, 'target', j, target
        else:
            if h >= stop:
                return -stop_pts, 'stop', j, stop
            if l <= target:
                return target_pts, 'target', j, target
    c = float(bars.iloc[-1]['close'])
    pts = c - entry if side == 'long' else entry - c
    return pts, 'session_close', len(bars) - 1, c


def plot_atr_trade(
    out_path: Path,
    trade: TradeRecord,
    bars15: pd.DataFrame,
    atr: float,
    target_pts: float,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 7), facecolor=BG)
    ax.set_facecolor(BG)
    shade_rth(ax, bars15)

    xs = mdates.date2num(list(bars15.index.to_pydatetime()))
    width = (15 / (24 * 60)) * 0.72 if len(xs) > 1 else 0.01
    for x, (_, row) in zip(xs, bars15.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN_CANDLE if c >= o else RED_CANDLE
        ax.vlines(x, l, h, color=col, linewidth=0.85, zorder=3)
        body_lo = min(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(abs(c - o), 0.08),
                facecolor=col,
                edgecolor=col,
                alpha=0.92,
                zorder=3,
            )
        )

    x0, x1 = xs[0], xs[-1]
    mc = trade.midnight_close
    ax.plot([x0, x1], [mc, mc], color=MC_COLOR, linewidth=1.5, zorder=4, label=f'MC {mc:.1f}')
    ax.plot([x0, x1], [trade.mo, trade.mo], color=MO_COLOR, linewidth=1.2, linestyle=':', zorder=4, label=f'MO {trade.mo:.1f}')

    stop = trade.entry - trade.stop_pts if trade.side == 'long' else trade.entry + trade.stop_pts
    target = trade.entry + target_pts if trade.side == 'long' else trade.entry - target_pts
    ax.axhline(stop, color=BEAR_COLOR, linestyle='--', linewidth=1.0, alpha=0.8, label=f'SL 1×ATR ({trade.stop_pts:.1f})')
    ax.axhline(target, color=BULL_COLOR, linestyle='--', linewidth=1.0, alpha=0.8, label=f'TP 2×ATR ({target_pts:.1f})')
    ax.axhline(trade.entry, color='white', linestyle='-', linewidth=0.8, alpha=0.6)

    x_bo = mdates.date2num(trade.breakout_ts.to_pydatetime())
    x_en = mdates.date2num(trade.entry_ts.to_pydatetime())
    x_ex = mdates.date2num(trade.exit_ts.to_pydatetime())
    ax.axvline(x_bo, color='#FFB74D', linestyle=':', linewidth=1.2, alpha=0.9)
    ax.scatter([x_en], [trade.entry], color='white', s=40, zorder=9, marker='^' if trade.side == 'long' else 'v')
    ax.scatter([x_ex], [trade.exit], color=BEAR_COLOR if trade.pts < 0 else BULL_COLOR, s=50, zorder=9, marker='x')

    bias_c = BULL_COLOR if trade.bias == 'bull' else BEAR_COLOR
    ax.set_title(
        f'NQ 15m · {trade.session} · {trade.side.upper()} · SL 1×ATR / TP 2×ATR (ATR {atr:.1f}) · '
        f'{trade.result} {trade.pts:+.1f} pts',
        color=bias_c,
        fontsize=9,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.1, color='#9FB3C8')
    ax.legend(loc='upper right', fontsize=7, facecolor='#1B263B', labelcolor='white')
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, facecolor=BG)
    plt.close(fig)


def build(
    *,
    trades_csv: Path,
    charts_root: Path,
    daily_path: Path,
    dbn_path: Path,
    streak_filter: bool,
) -> None:
    daily = load_daily(daily_path)
    atr_map = build_daily_atr(daily)
    trades = pd.read_csv(trades_csv, parse_dates=['session', 'entry_ts', 'exit_ts', 'breakout_ts'])
    pool = apply_streak_filter(trades, daily) if streak_filter else trades.copy()

    study_dir = charts_root / STUDY
    win_dir = study_dir / 'winners'
    lose_dir = study_dir / 'losers'
    win_dir.mkdir(parents=True, exist_ok=True)
    lose_dir.mkdir(parents=True, exist_ok=True)

    sessions = sorted({pd.Timestamp(s).date() for s in pool['session']})
    print(f'Loading 1m · {len(pool)} trades · {len(sessions)} sessions ...', flush=True)
    gby = load_1m_by_ny_date(dbn_path, 'nq')
    b15: dict[date, pd.DataFrame] = {}
    for i, s in enumerate(sessions):
        if s in gby:
            b15[s] = resample_15m_midnight_to_1600(gby[s], s)
        if (i + 1) % 200 == 0:
            print(f'  … cached {i+1}/{len(sessions)}', flush=True)

    rows: list[dict] = []
    manifest: list[dict] = []
    nw = nl = 0

    for trade_id, (_, row) in enumerate(pool.iterrows()):
        s = pd.Timestamp(row['session']).date()
        bars = b15.get(s)
        atr = atr_map.get(s)
        if bars is None or bars.empty or not atr:
            continue
        ets = pd.Timestamp(row['entry_ts'])
        match = [i for i, ts in enumerate(bars.index) if ts == ets]
        if not match:
            continue
        en = match[0]
        entry = float(row['entry'])
        side = row['side']
        stop_pts = SL_MULT * atr
        target_pts = TP_MULT * atr
        pts, result, ex_idx, exit_px = simulate_exit_atr(bars, side, en, entry, stop_pts, target_pts)

        t = row_to_trade(row)
        t.stop_pts = stop_pts
        t.pts = pts
        t.result = result
        t.exit = exit_px
        t.exit_ts = pd.Timestamp(bars.index[ex_idx])

        bucket = 'winners' if pts > 0 else 'losers'
        out_dir = win_dir if pts > 0 else lose_dir
        n = nw + 1 if pts > 0 else nl + 1
        if pts > 0:
            nw += 1
        else:
            nl += 1
        fname = f'{n:04d}_{s.isoformat()}_{side}_{result}_{pts:+.1f}.png'
        plot_atr_trade(out_dir / fname, t, bars, atr, target_pts)

        rel = f'{STUDY}/{bucket}/{fname}'
        manifest.append({'chart': rel, 'bucket': bucket, 'session': s.isoformat(), 'pts': pts, 'result': result, 'atr': atr})
        rows.append(
            {
                'trade_id': trade_id,
                'session': s.isoformat(),
                'side': side,
                'bias': row['bias'],
                'streak_id': row['streak_id'],
                'atr': atr,
                'stop_pts': stop_pts,
                'target_pts': target_pts,
                'entry': entry,
                'exit': exit_px,
                'pts': pts,
                'result': result,
                'chart': rel,
            }
        )
        if (trade_id + 1) % 100 == 0:
            print(f'  … charted {trade_id+1}/{len(pool)}', flush=True)

    pd.DataFrame(rows).to_csv(study_dir / 'trades.csv', index=False)
    pd.DataFrame(manifest).to_csv(study_dir / 'manifest.csv', index=False)

    total_pts = sum(r['pts'] for r in rows)
    filt_note = 'days 1–3 · max 2 streaks/month · ' if streak_filter else ''
    lines = [
        f'# MO midnight retest · {STUDY}',
        '',
        f'Exit: **SL 1×ATR / TP 2×ATR** (2:1 R:R) · daily ATR14 causal.',
        '',
        f'Filter: {filt_note}same entries as SL30 backtest.',
        '',
        f'**{len(rows)}** trades charted · **{nw}** winners · **{nl}** losers · **{total_pts:+.1f}** total pts.',
        '',
        '- [`winners/`](winners/)',
        '- [`losers/`](losers/)',
        '- [`trades.csv`](trades.csv)',
        '',
    ]
    (study_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {study_dir} · {nw} wins / {nl} losses · {total_pts:+.1f} pts', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--trades', type=Path, default=HERE / 'nq_mo_midnight_retest' / 'trades_sl30.csv')
    ap.add_argument('--charts-root', type=Path, default=HERE / 'nq_mo_midnight_retest' / 'charts')
    ap.add_argument('--daily', type=Path, default=HERE.parent / 'nq_daily.csv')
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN_NQ)
    ap.add_argument('--no-streak-filter', action='store_true')
    args = ap.parse_args()
    build(
        trades_csv=args.trades,
        charts_root=args.charts_root,
        daily_path=args.daily,
        dbn_path=args.dbn,
        streak_filter=not args.no_streak_filter,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
