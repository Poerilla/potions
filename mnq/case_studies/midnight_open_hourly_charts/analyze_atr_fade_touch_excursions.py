#!/usr/bin/env python3
"""MAE / MFE and mark-to-market max drawdown for atr_fade_touch trades CSV."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from backtest_midnight_open_flip import Trade, USD_PER_POINT  # noqa: E402

DEFAULT_CSV = HERE / 'backtest_midnight_open_flip_trades_mnq_atr_fade_touch.csv'
DEFAULT_DBN = mdata.DEFAULT_DBN


def load_trades(path: Path) -> list[Trade]:
    df = pd.read_csv(path)
    out: list[Trade] = []
    for _, row in df.iterrows():
        d = date.fromisoformat(str(row['session']))
        out.append(
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
    out.sort(key=lambda t: (t.entry_time, t.exit_time))
    return out


def leg_excursions(t: Trade, sess_1m: pd.DataFrame) -> tuple[float, float]:
    """MAE and MFE in points (always >= 0)."""
    path = sess_1m[(sess_1m.index >= t.entry_time) & (sess_1m.index <= t.exit_time)]
    if path.empty:
        return float('nan'), float('nan')
    hi = float(path['high'].max())
    lo = float(path['low'].min())
    if t.side == 'long':
        mae = max(t.entry_px - lo, 0.0)
        mfe = max(hi - t.entry_px, 0.0)
    else:
        mae = max(hi - t.entry_px, 0.0)
        mfe = max(t.entry_px - lo, 0.0)
    return mae, mfe


def mtm_drawdown(trades: list[Trade], gby: dict[date, pd.DataFrame]) -> tuple[float, float, float]:
    """
    Chronological equity = realized + open MTM at each 1m bar close while in a trade.
    Returns (max_drawdown_usd, max_drawdown_pct_of_peak, final_equity).
    """
    realized = 0.0
    peak = 0.0
    max_dd = 0.0

    for t in trades:
        raw = gby.get(t.session)
        if raw is None:
            realized += t.pnl_usd
            peak = max(peak, realized)
            max_dd = max(max_dd, peak - realized)
            continue
        sess = mdata.slice_session_1m(raw, t.session)
        path = sess[(sess.index >= t.entry_time) & (sess.index <= t.exit_time)]
        for _, bar in path.iterrows():
            cl = float(bar['close'])
            if t.side == 'long':
                open_pnl = (cl - t.entry_px) * t.usd_per_point
            else:
                open_pnl = (t.entry_px - cl) * t.usd_per_point
            eq = realized + open_pnl
            peak = max(peak, eq)
            max_dd = max(max_dd, peak - eq)
        realized += t.pnl_usd
        peak = max(peak, realized)
        max_dd = max(max_dd, peak - realized)

    pct_dd = (100.0 * max_dd / peak) if peak > 1e-9 else float('nan')
    return max_dd, pct_dd, realized


def print_report(mae_pts: np.ndarray, mfe_pts: np.ndarray, max_dd: float, pct_dd: float, n: int) -> None:
    usd_pp = USD_PER_POINT['mnq']
    mae_usd = mae_pts * usd_pp
    mfe_usd = mfe_pts * usd_pp
    pct = [10, 25, 50, 75, 90, 95]

    print('## atr_fade_touch — MAE / MFE / MTM drawdown (MNQ x1)\n', flush=True)
    print(f'- **Trades analyzed:** {n}', flush=True)
    print(f'- **Max MTM drawdown:** ${max_dd:,.2f} ({pct_dd:.1f}% off equity peak)', flush=True)
    print('', flush=True)
    print('### MAE (max adverse excursion, points then USD)', flush=True)
    print(f'- **Mean:** {mae_pts.mean():.1f} pts (${mae_usd.mean():,.0f})', flush=True)
    print(f'- **Median:** {np.median(mae_pts):.1f} pts (${np.median(mae_usd):,.0f})', flush=True)
    print(f'- **Max (worst trade):** {mae_pts.max():.1f} pts (${mae_usd.max():,.0f})', flush=True)
    for p in pct:
        q = np.percentile(mae_pts, p)
        print(f'- **P{p}:** {q:.1f} pts (${q * usd_pp:,.0f})', flush=True)
    print('', flush=True)
    print('### MFE (max favorable excursion)', flush=True)
    print(f'- **Mean:** {mfe_pts.mean():.1f} pts (${mfe_usd.mean():,.0f})', flush=True)
    print(f'- **Median:** {np.median(mfe_pts):.1f} pts (${np.median(mfe_usd):,.0f})', flush=True)
    for p in pct:
        q = np.percentile(mfe_pts, p)
        print(f'- **P{p}:** {q:.1f} pts (${q * usd_pp:,.0f})', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_CSV)
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    args = ap.parse_args()

    if not args.trades_csv.is_file():
        print(f'Missing {args.trades_csv}', file=sys.stderr)
        return 1
    if not args.dbn.is_file():
        print(f'Missing {args.dbn}', file=sys.stderr)
        return 1

    trades = load_trades(args.trades_csv)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')

    mae_list: list[float] = []
    mfe_list: list[float] = []
    for t in trades:
        raw = gby.get(t.session)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, t.session)
        mae, mfe = leg_excursions(t, sess)
        if np.isfinite(mae):
            mae_list.append(mae)
            mfe_list.append(mfe)

    max_dd, pct_dd, final_eq = mtm_drawdown(trades, gby)
    print_report(np.array(mae_list), np.array(mfe_list), max_dd, pct_dd, len(mae_list))
    print(f'- **Final realized equity:** ${final_eq:,.2f}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
