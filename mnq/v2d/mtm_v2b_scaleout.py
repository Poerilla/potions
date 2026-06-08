#!/usr/bin/env python3
"""
Mark-to-market max drawdown for **v2b-only adaptive scaleout (×2 MNQ)**.

Uses the same 1m replay as ``run_adaptive_50_150_scaleout.py``: prior-day MA50>MA150
days only, v2b breakout legs from the stitched adaptive book (direction per row).

Example::

  cd potions/mnq/v2d
  python3 mtm_v2b_scaleout.py
  python3 mtm_v2b_scaleout.py --dbn ../raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

V2D = Path(__file__).resolve().parent
MNQ_ROOT = V2D.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
sys.path[:0] = [str(MNQ_ROOT), str(POTIONS_SCRIPTS), str(V2D)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from run_adaptive_50_150_scaleout import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    MULT,
    RTH_HI,
    TICK,
    _EPS,
    path_after_prior,
    resolve_fill,
    rth_slice,
    trade_params,
)


@dataclass
class LegMtm:
    session_day: date
    direction: str
    fill_ts: pd.Timestamp
    exit_ts: pd.Timestamp | None
    net_usd: float


@dataclass
class LegOhlcUsd:
    """Per-leg excursion candle in USD (O=0, H=MFE, L=MAE, C=closed net)."""

    session_day: date
    direction: str
    open_usd: float
    high_usd: float
    low_usd: float
    close_usd: float


def open_pnl_pts(
    cl: float,
    *,
    entry: float,
    qty: int,
    long_side: bool,
    realized_pts: float,
) -> float:
    if qty <= 0:
        return realized_pts
    if long_side:
        return realized_pts + qty * (cl - entry)
    return realized_pts + qty * (entry - cl)


def simulate_scale_out_leg_mtm(
    rth: pd.DataFrame,
    session_day: date,
    fill_ts: pd.Timestamp,
    *,
    entry: float,
    long_side: bool,
    init_sl: float,
    tp1: float,
    tp2: float,
    runner_sl: float,
    mult: float = MULT,
    fee_rt: float = FEE_RT,
) -> tuple[float, pd.Timestamp | None, list[tuple[pd.Timestamp, float]]]:
    """
    Same pessimistic 1m logic as ``simulate_scale_out_leg``, plus MTM samples at each bar **close**.
    Returns (net_usd, exit_ts, [(ts, equity_usd), ...]).
    """
    path = rth[rth.index >= fill_ts].sort_index()
    qty = 2
    pnl_pts = 0.0
    fees = 0.0
    exit_ts: pd.Timestamp | None = None
    samples: list[tuple[pd.Timestamp, float]] = []

    def fee_close(n: int) -> None:
        nonlocal fees
        fees += fee_rt * n

    def record(ts: pd.Timestamp, cl: float) -> None:
        pts = open_pnl_pts(cl, entry=entry, qty=qty, long_side=long_side, realized_pts=pnl_pts)
        samples.append((pd.Timestamp(ts), round(pts * mult - fees, 2)))

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        h, l, cl = float(bar['high']), float(bar['low']), float(bar['close'])
        record(ts, cl)

        if long_side:
            if qty == 2:
                if l <= init_sl + _EPS:
                    pnl_pts += 2.0 * (init_sl - entry)
                    fee_close(2)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if h >= tp1 - _EPS:
                    pnl_pts += tp1 - entry
                    fee_close(1)
                    qty = 1
                    if l <= runner_sl + _EPS:
                        pnl_pts += runner_sl - entry
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
                    if h >= tp2 - _EPS:
                        pnl_pts += tp2 - entry
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if l <= runner_sl + _EPS:
                    pnl_pts += runner_sl - entry
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if h >= tp2 - _EPS:
                    pnl_pts += tp2 - entry
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
        else:
            if qty == 2:
                if h >= init_sl - _EPS:
                    pnl_pts += 2.0 * (entry - init_sl)
                    fee_close(2)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if l <= tp1 + _EPS:
                    pnl_pts += entry - tp1
                    fee_close(1)
                    qty = 1
                    if h >= runner_sl - _EPS:
                        pnl_pts += entry - runner_sl
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
                    if l <= tp2 + _EPS:
                        pnl_pts += entry - tp2
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if h >= runner_sl - _EPS:
                    pnl_pts += entry - runner_sl
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if l <= tp2 + _EPS:
                    pnl_pts += entry - tp2
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break

    if qty > 0:
        tail = rth[rth.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)]
        if not tail.empty:
            eod = float(tail.iloc[-1]['close'])
            ts_last = pd.Timestamp(tail.index[-1])
            if long_side:
                pnl_pts += (2.0 if qty == 2 else 1.0) * (eod - entry)
            else:
                pnl_pts += (2.0 if qty == 2 else 1.0) * (entry - eod)
            fee_close(qty)
            exit_ts = ts_last
            record(ts_last, eod)

    net_usd = round(pnl_pts * mult - fees, 2)
    return net_usd, exit_ts, samples


def simulate_scale_out_leg_ohlc(
    rth: pd.DataFrame,
    session_day: date,
    fill_ts: pd.Timestamp,
    *,
    entry: float,
    long_side: bool,
    init_sl: float,
    tp1: float,
    tp2: float,
    runner_sl: float,
) -> tuple[float, pd.Timestamp | None, LegOhlcUsd]:
    """Same as ``simulate_scale_out_leg_mtm``; also returns USD OHLC vs entry (O=0)."""
    path = rth[rth.index >= fill_ts].sort_index()
    qty = 2
    pnl_pts = 0.0
    fees = 0.0
    exit_ts: pd.Timestamp | None = None
    mfe_usd = 0.0
    mae_usd = 0.0
    direction = 'Long' if long_side else 'Short'

    def fee_close(n: int) -> None:
        nonlocal fees
        fees += FEE_RT * n

    def mark(cl: float) -> float:
        pts = open_pnl_pts(cl, entry=entry, qty=qty, long_side=long_side, realized_pts=pnl_pts)
        return pts * MULT - fees

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        h, l, cl = float(bar['high']), float(bar['low']), float(bar['close'])
        eq = mark(cl)
        mfe_usd = max(mfe_usd, eq)
        mae_usd = min(mae_usd, eq)

        if long_side:
            if qty == 2:
                if l <= init_sl + _EPS:
                    pnl_pts += 2.0 * (init_sl - entry)
                    fee_close(2)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if h >= tp1 - _EPS:
                    pnl_pts += tp1 - entry
                    fee_close(1)
                    qty = 1
                    if l <= runner_sl + _EPS:
                        pnl_pts += runner_sl - entry
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
                    if h >= tp2 - _EPS:
                        pnl_pts += tp2 - entry
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if l <= runner_sl + _EPS:
                    pnl_pts += runner_sl - entry
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if h >= tp2 - _EPS:
                    pnl_pts += tp2 - entry
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
        else:
            if qty == 2:
                if h >= init_sl - _EPS:
                    pnl_pts += 2.0 * (entry - init_sl)
                    fee_close(2)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if l <= tp1 + _EPS:
                    pnl_pts += entry - tp1
                    fee_close(1)
                    qty = 1
                    if h >= runner_sl - _EPS:
                        pnl_pts += entry - runner_sl
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
                    if l <= tp2 + _EPS:
                        pnl_pts += entry - tp2
                        fee_close(1)
                        qty = 0
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if h >= runner_sl - _EPS:
                    pnl_pts += entry - runner_sl
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break
                if l <= tp2 + _EPS:
                    pnl_pts += entry - tp2
                    fee_close(1)
                    qty = 0
                    exit_ts = pd.Timestamp(ts)
                    break

    if qty > 0:
        tail = rth[rth.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)]
        if not tail.empty:
            eod = float(tail.iloc[-1]['close'])
            ts_last = pd.Timestamp(tail.index[-1])
            if long_side:
                pnl_pts += (2.0 if qty == 2 else 1.0) * (eod - entry)
            else:
                pnl_pts += (2.0 if qty == 2 else 1.0) * (entry - eod)
            fee_close(qty)
            exit_ts = ts_last
            eq = mark(eod)
            mfe_usd = max(mfe_usd, eq)
            mae_usd = min(mae_usd, eq)

    net_usd = round(pnl_pts * MULT - fees, 2)
    mfe_usd = max(mfe_usd, net_usd)
    mae_usd = min(mae_usd, net_usd)
    ohlc = LegOhlcUsd(
        session_day=session_day,
        direction=direction,
        open_usd=0.0,
        high_usd=round(mfe_usd, 2),
        low_usd=round(mae_usd, 2),
        close_usd=net_usd,
    )
    return net_usd, exit_ts, ohlc


def portfolio_mtm_dd_simple(legs: list[LegMtm], leg_curves: list[list[tuple[pd.Timestamp, float]]]) -> tuple[float, float, float]:
    realized = 0.0
    peak = 0.0
    max_dd = 0.0
    for i, curve in enumerate(leg_curves):
        base = realized
        for _ts, open_eq in curve:
            total = base + open_eq
            peak = max(peak, total)
            max_dd = max(max_dd, peak - total)
        realized += legs[i].net_usd
        peak = max(peak, realized)
        max_dd = max(max_dd, peak - realized)
    pct = 100.0 * max_dd / peak if peak > 1e-9 else float('nan')
    return max_dd, pct, realized


def closed_dd(pnl: np.ndarray) -> float:
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    return float((peak - cum).max()) if len(cum) else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument(
        '--adaptive-csv',
        type=Path,
        default=V2D / 'mnq_orb_results_adaptive_50_150.csv',
    )
    ap.add_argument(
        '--dbn',
        type=Path,
        default=MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
    )
    args = ap.parse_args()

    if not args.adaptive_csv.is_file():
        print(f'Missing {args.adaptive_csv}', file=sys.stderr)
        return 1
    if not args.dbn.is_file():
        print(f'Missing {args.dbn}', file=sys.stderr)
        return 1

    ad = pd.read_csv(args.adaptive_csv)
    ad['_row_order'] = range(len(ad))
    ad['Date'] = pd.to_datetime(ad['Date']).dt.date
    v2b = ad[ad['Regime'].astype(str).str.lower() == 'v2b'].sort_values(['Date', '_row_order'])

    need_dates = set(v2b['Date'].unique())
    print(f'Loading 1m for {len(need_dates)} v2b regime days ...', flush=True)

    import databento as db

    store = db.DBNStore.from_file(str(args.dbn))
    raw = store.to_df().reset_index()
    raw = raw[~raw['symbol'].str.contains('-', na=False)]
    raw = raw[raw['symbol'].str.startswith('MNQ')].copy()
    raw['ts_event'] = raw['ts_event'].dt.tz_convert('America/New_York')
    raw['date'] = raw['ts_event'].dt.date
    raw = raw[raw['date'].isin(need_dates)]
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {d: g for d, g in raw.groupby(raw['date'], sort=False)}

    legs: list[LegMtm] = []
    curves: list[list[tuple[pd.Timestamp, float]]] = []
    nets: list[float] = []
    skipped = 0

    for session_day in sorted(v2b['Date'].unique()):
        grp = v2b[v2b['Date'] == session_day].sort_values('_row_order')
        day_raw = gby.get(session_day)
        if day_raw is None or day_raw.empty:
            skipped += len(grp)
            continue
        rth = rth_slice(day_raw, session_day)
        if rth.empty:
            skipped += len(grp)
            continue

        prior_exit: pd.Timestamp | None = None
        for _, row in grp.iterrows():
            direction = str(row['Trade_Direction']).strip()
            rh, rl, rv = float(row['Range_High']), float(row['Range_Low']), float(row['Range'])
            pm = trade_params('v2b', direction, rh, rl, rv)
            if pm is None:
                skipped += 1
                continue
            sub = path_after_prior(rth, session_day, prior_exit)
            if sub.empty:
                skipped += 1
                continue
            fts, _ = resolve_fill('v2b', direction, sub, rh, rl)
            if fts is None:
                skipped += 1
                continue

            net, exit_ts, samples = simulate_scale_out_leg_mtm(
                rth,
                session_day,
                fts,
                entry=float(pm['entry']),
                long_side=bool(pm['long_side']),
                init_sl=float(pm['init_sl']),
                tp1=float(pm['tp1']),
                tp2=float(pm['tp2']),
                runner_sl=float(pm['runner_sl']),
            )
            legs.append(
                LegMtm(session_day, direction, fts, exit_ts, net)
            )
            curves.append(samples)
            nets.append(net)
            if exit_ts is not None:
                prior_exit = exit_ts

    mtm_dd, mtm_pct, final_net = portfolio_mtm_dd_simple(legs, curves)
    pnl = np.array(nets, dtype=float)
    cdd = closed_dd(pnl)

    print('\n## v2b-only adaptive scaleout (×2 MNQ) — MTM drawdown\n', flush=True)
    print(f'- **Legs replayed:** {len(legs)} (skipped {skipped})', flush=True)
    print(f'- **Total net (replay):** ${final_net:,.2f}', flush=True)
    so_path = V2D / 'adaptive_50_150_scaleout_legs.csv'
    scaleout_csv_sum = (
        float(pd.read_csv(so_path).query("regime == 'v2b'")['scaleout_net_2ct'].sum())
        if so_path.is_file()
        else float('nan')
    )
    if np.isfinite(scaleout_csv_sum):
        print(f'- **Scaleout CSV net (v2b legs):** ${scaleout_csv_sum:,.2f}', flush=True)
    print(f'- **Closed equity DD (legs):** ${cdd:,.2f}', flush=True)
    print(f'- **Max MTM drawdown:** ${mtm_dd:,.2f} ({mtm_pct:.1f}% off intraday peak)', flush=True)
    npm = final_net / mtm_dd if mtm_dd > 1e-9 else float('nan')
    print(f'- **Net / MTM DD:** {npm:.2f}' if np.isfinite(npm) else '-', flush=True)
    print(f'- **Win rate:** {100 * (pnl > 0).mean():.1f}%', flush=True)
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl <= 0].sum())
    pf = wins / losses if losses > 1e-9 else float('inf')
    print(f'- **Profit factor:** {pf:.2f}', flush=True)
    print(flush=True)
    print('Method: 1m bar **close** MTM while leg open (×2 until TP1); pessimistic stop-before-TP intrabar.', flush=True)
    print('Book: `mnq_orb_results_adaptive_50_150.csv` rows with `Regime=v2b` only.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
