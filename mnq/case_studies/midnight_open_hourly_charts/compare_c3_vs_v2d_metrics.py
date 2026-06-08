#!/usr/bin/env python3
"""
Compare **C3 swing + v2b opposite OR break** vs canonical **NY v2d fade** and tracker baselines.

Metrics: net, win rate, PF, median, closed DD, MTM DD, MAE/MFE (1m replay where possible).
See ``mnq/case_studies/STRATEGY_TRACKER.md`` for promoted v2b-only adaptive (not pure v2d).

Example::

  python3 compare_c3_vs_v2d_metrics.py
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
import pytz

HERE = Path(__file__).resolve().parent
MNQ_ROOT = HERE.parent.parent
V2D = MNQ_ROOT / 'v2d'
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from analyze_atr_fade_touch_excursions import (  # noqa: E402
    leg_excursions,
    load_trades,
    mtm_drawdown,
)
from backtest_midnight_open_flip import (  # noqa: E402
    ORB_HI,
    ORB_LO,
    Trade,
    USD_PER_POINT,
    orb_v2b_targets,
)

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
ORB_END = ORB_HI
EOD_CUTOFF = time(15, 55)
TICK = 0.25
SLIP = 1
USD_PP = USD_PER_POINT['mnq']
FEE_RT = 1.50
DEFAULT_DBN = mdata.DEFAULT_DBN
C3_CSV = HERE / 'backtest_c3_swing_orb_fade_trades_mnq.csv'
V2D_CSV = V2D / 'mnq_orb_results_v2d.csv'
ADAPTIVE_CSV = V2D / 'mnq_orb_results_adaptive_50_150.csv'
SCALEOUT_CSV = V2D / 'adaptive_50_150_scaleout_legs.csv'


@dataclass
class BookStats:
    name: str
    n: int
    net: float
    win_pct: float
    pf: float
    median: float
    closed_dd: float
    mtm_dd: float
    mtm_dd_pct: float
    net_per_dd: float
    mae_mean: float
    mae_median: float
    mae_max: float
    note: str = ''


def closed_dd_from_pnl(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    return float((peak - cum).max())


def pf_from_pnl(pnl: np.ndarray) -> float:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses < 1e-9:
        return float('inf') if wins > 0 else float('nan')
    return float(wins / losses)


def stats_from_pnl(name: str, pnl: np.ndarray, *, note: str = '') -> BookStats:
    pnl = np.asarray(pnl, dtype=float)
    n = len(pnl)
    net = float(pnl.sum()) if n else 0.0
    dd = closed_dd_from_pnl(pnl)
    return BookStats(
        name=name,
        n=n,
        net=net,
        win_pct=100.0 * (pnl > 0).mean() if n else float('nan'),
        pf=pf_from_pnl(pnl),
        median=float(np.median(pnl)) if n else float('nan'),
        closed_dd=dd,
        mtm_dd=float('nan'),
        mtm_dd_pct=float('nan'),
        net_per_dd=net / dd if dd > 1e-9 else float('nan'),
        mae_mean=float('nan'),
        mae_median=float('nan'),
        mae_max=float('nan'),
        note=note,
    )


def stats_from_trades(name: str, trades: list[Trade], gby: dict[date, pd.DataFrame], *, note: str = '') -> BookStats:
    pnl = np.array([t.pnl_usd for t in trades], dtype=float)
    base = stats_from_pnl(name, pnl, note=note)
    base.n = len(trades)

    mae_list: list[float] = []
    for t in trades:
        raw = gby.get(t.session)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, t.session)
        mae, _ = leg_excursions(t, sess)
        if np.isfinite(mae):
            mae_list.append(mae)
    if mae_list:
        arr = np.array(mae_list)
        base.mae_mean = float(arr.mean())
        base.mae_median = float(np.median(arr))
        base.mae_max = float(arr.max())

    mtm, pct, _ = mtm_drawdown(trades, gby)
    base.mtm_dd = mtm
    base.mtm_dd_pct = pct
    base.net_per_dd = base.net / mtm if mtm > 1e-9 else base.net_per_dd
    return base


def simulate_v2d_ny_day(
    session_day: date,
    sess_1m: pd.DataFrame,
    *,
    usd_per_point: float = USD_PP,
) -> list[Trade]:
    """Canonical NY v2d fade (max 2 legs), with timestamps for MAE/MTM."""
    orb = orb_v2b_targets(sess_1m, session_day)
    if orb is None:
        return []
    rh, rl, rv, _, _ = orb
    if rv <= 0:
        return []

    tick = TICK
    slip = SLIP * tick
    orb_ready = NY.localize(datetime.combine(session_day, ORB_END))
    session_end = NY.localize(datetime.combine(session_day, RTH_HI))

    long_break_trig = rh + tick
    short_break_trig = rl - tick
    short_fade_trig = rh - tick
    long_fade_trig = rl + tick
    short_fill = short_fade_trig - slip
    long_fill = long_fade_trig + slip

    long_break_done = short_break_done = False
    armed_short = armed_long = False
    traded_long = traded_short = False
    trades: list[Trade] = []

    post = sess_1m[(sess_1m.index >= orb_ready) & (sess_1m.index < session_end)].sort_index()

    in_trade = False
    side = entry_px = stop_px = tp_px = None
    entry_ts = exit_ts = None

    def open_trade(s: str, ep: float, st: float, tg: float, ts: pd.Timestamp) -> None:
        nonlocal in_trade, side, entry_px, stop_px, tp_px, entry_ts
        in_trade = True
        side = s
        entry_px = ep
        stop_px = st
        tp_px = tg
        entry_ts = ts

    def close_trade(ts: pd.Timestamp, xp: float, reason: str) -> None:
        nonlocal in_trade, traded_long, traded_short
        trades.append(
            Trade(session_day, side, entry_ts, entry_px, ts, xp, reason, usd_per_point)
        )
        if side == 'long':
            traded_long = True
        else:
            traded_short = True
        in_trade = False
        if len(trades) >= 2:
            return

    for ts, bar in post.iterrows():
        if ts.time() >= EOD_CUTOFF and not in_trade:
            break
        hi, lo, op = float(bar['high']), float(bar['low']), float(bar['open'])

        if not in_trade:
            if not long_break_done and hi >= long_break_trig:
                long_break_done = True
                if not traded_short:
                    armed_short = True
            if not short_break_done and lo <= short_break_trig:
                short_break_done = True
                if not traded_long:
                    armed_long = True

            if not (long_break_done and short_break_done and armed_short and armed_long):
                short_hit = armed_short and lo <= short_fade_trig
                long_hit = armed_long and hi >= long_fade_trig
                if short_hit and long_hit:
                    mid = (rh + rl) / 2
                    if op >= mid and not traded_short:
                        open_trade('short', short_fill, rh + rv, rl, ts)
                        armed_short = False
                    elif not traded_long:
                        open_trade('long', long_fill, rl - rv, rh, ts)
                        armed_long = False
                elif short_hit and not traded_short:
                    open_trade('short', short_fill, rh + rv, rl, ts)
                    armed_short = False
                elif long_hit and not traded_long:
                    open_trade('long', long_fill, rl - rv, rh, ts)
                    armed_long = False

        if in_trade:
            if side == 'long':
                if lo < stop_px:
                    close_trade(ts, stop_px, 'sl_v2d')
                elif hi >= tp_px:
                    close_trade(ts, tp_px, 'tp_v2d')
            else:
                if hi > stop_px:
                    close_trade(ts, stop_px, 'sl_v2d')
                elif lo <= tp_px:
                    close_trade(ts, tp_px, 'tp_v2d')
            if len(trades) >= 2 and not in_trade:
                break

    if in_trade and not post.empty:
        last_ts = post.index.max()
        close_trade(last_ts, float(post.loc[last_ts, 'close']), 'session_16:00')

    return trades


def replay_v2d_ny(gby: dict[date, pd.DataFrame], start: date, end: date) -> list[Trade]:
    out: list[Trade] = []
    for d in sorted(gby.keys()):
        if d < start or d > end:
            continue
        raw = gby[d]
        sess = mdata.slice_session_1m(raw, d)
        if sess.empty:
            continue
        out.extend(simulate_v2d_ny_day(d, sess))
    return out


def load_csv_pnl(path: Path, col: str = 'Net_$', date_col: str = 'Date') -> pd.DataFrame:
    df = pd.read_csv(path)
    df[date_col] = pd.to_datetime(df[date_col]).dt.date
    return df


def print_table(rows: list[BookStats], title: str) -> None:
    print(f'\n## {title}\n', flush=True)
    print(
        '| Strategy | N | Net | Win% | PF | Median | Closed DD | MTM DD | Net/MTM | '
        'MAE mean | MAE med | MAE max |',
        flush=True,
    )
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|', flush=True)
    for r in rows:
        pf = f'{r.pf:.2f}' if np.isfinite(r.pf) else '—'
        mtm = f'${r.mtm_dd:,.0f}' if np.isfinite(r.mtm_dd) else '—'
        npm = f'{r.net_per_dd:.2f}' if np.isfinite(r.net_per_dd) else '—'
        mae_m = f'{r.mae_mean:.1f}' if np.isfinite(r.mae_mean) else '—'
        mae_med = f'{r.mae_median:.1f}' if np.isfinite(r.mae_median) else '—'
        mae_x = f'{r.mae_max:.1f}' if np.isfinite(r.mae_max) else '—'
        print(
            f'| {r.name} | {r.n} | ${r.net:,.0f} | {r.win_pct:.1f}% | {pf} | ${r.median:,.0f} | '
            f'${r.closed_dd:,.0f} | {mtm} | {npm} | {mae_m} | {mae_med} | {mae_x} |',
            flush=True,
        )
        if r.note:
            print(f'| _{r.note}_ | | | | | | | | | | | |', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    args = ap.parse_args()

    if not args.dbn.is_file():
        print('Missing DBN', file=sys.stderr)
        return 1

    print('Loading 1m DBN ...', flush=True)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')

    # Date windows
    v2d_df = load_csv_pnl(V2D_CSV)
    v2d_start = min(v2d_df['Date'])
    v2d_end = max(v2d_df['Date'])

    c3_trades_all = load_trades(C3_CSV) if C3_CSV.is_file() else []
    c3_trades = [t for t in c3_trades_all if v2d_start <= t.session <= v2d_end]

    print('Replaying canonical NY v2d on 1m (for MAE/MTM) ...', flush=True)
    v2d_trades = replay_v2d_ny(gby, v2d_start, v2d_end)

    rows_full: list[BookStats] = []
    rows_overlap: list[BookStats] = []

    # --- C3 ---
    if c3_trades_all:
        rows_full.append(
            stats_from_trades(
                'C3 + swing + v2b opposite break (x1)',
                c3_trades_all,
                gby,
                note='Filtered session days only; ~445 trades',
            )
        )
    if c3_trades:
        rows_overlap.append(
            stats_from_trades(
                'C3 + swing + v2b opposite break (x1)',
                c3_trades,
                gby,
                note=f'Overlap {v2d_start}..{v2d_end}',
            )
        )

    # --- Pure v2d CSV (1 ct, fees in Net_$) ---
    pnl_v2d = v2d_df['Net_$'].astype(float).values
    s_v2d = stats_from_pnl('NY v2d fade CSV (x1, fees in Net_$)', pnl_v2d, note='mnq_orb_results_v2d.csv')
    rows_full.append(s_v2d)
    rows_overlap.append(s_v2d)

    # --- v2d 1m replay (x1, no fees in pnl_usd) ---
    s_v2d_rep = stats_from_trades(
        'NY v2d fade 1m replay (x1)',
        v2d_trades,
        gby,
        note='Matches validation.md fade; no $1.50 fee in leg PnL',
    )
    rows_overlap.append(s_v2d_rep)

    # --- Adaptive stitched v2d-only legs ---
    if ADAPTIVE_CSV.is_file():
        ad = pd.read_csv(ADAPTIVE_CSV)
        ad['Date'] = pd.to_datetime(ad['Date']).dt.date
        ad_v2d = ad[ad['Regime'] == 'v2d']
        pnl_ad_v2d = ad_v2d['Net_$'].astype(float).values
        rows_overlap.append(
            stats_from_pnl(
                'Adaptive 50/150 — v2d arm only (x1)',
                pnl_ad_v2d,
                note='~MA50<MA150 days; mnq_orb_results_adaptive_50_150.csv',
            )
        )

    # --- Scale-out 2ct books ---
    if SCALEOUT_CSV.is_file():
        so = pd.read_csv(SCALEOUT_CSV)
        so['date_iso'] = pd.to_datetime(so['date_iso']).dt.date
        so = so[(so['date_iso'] >= v2d_start) & (so['date_iso'] <= v2d_end)]
        for regime, label in (
            ('v2d', 'Adaptive scaleout — v2d only (x2 MNQ)'),
            ('v2b', 'Adaptive scaleout — v2b only (x2 MNQ, tracker leader)'),
        ):
            sub = so[so['regime'] == regime]
            pnl = sub['scaleout_net_2ct'].astype(float).values
            rows_overlap.append(
                stats_from_pnl(
                    label,
                    pnl,
                    note='adaptive_50_150_scaleout_legs.csv; STRATEGY_TRACKER leader is v2b-only',
                )
            )

    print_table(
        rows_full,
        f'Full sample (C3 from {min(t.session for t in c3_trades_all) if c3_trades_all else "—"})',
    )
    print_table(rows_overlap, f'Overlap window {v2d_start} → {v2d_end} (v2d history start)')

    print('\n### Notes\n', flush=True)
    print(
        '- **C3** trades only on C3 setup days after hit + 15m swing; **v2d** trades most NY sessions (up to 2 legs).',
        flush=True,
    )
    print(
        '- **MTM DD** / **MAE** require 1m replay; CSV rows use **closed** equity DD only.',
        flush=True,
    )
    print(
        '- Per `STRATEGY_TRACKER.md`, the intraday ORB **leader** is **v2b-only adaptive scaleout** '
        '(+$35,847 / -$5,190 DD / 1,430 legs), not pure v2d.',
        flush=True,
    )
    print(
        '- Pure **v2d** CSV total is negative on this MNQ sample; C3 opposite-break is a **conditional** overlay.',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
