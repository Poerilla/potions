#!/usr/bin/env python3
"""
C3 hit + in-session 15m swing + **v2b opposite ORB break**.

Filters (all required before entry):
1. **C3 day** from daily candlestick theory setups.
2. **Intraday hit** on 1m: bullish session high > C2 expected extreme; bearish low < C2 low.
3. **15m swing** after hit: bullish swing high **above** C2 extreme; bearish swing low **below** C2 low.
4. **v2b break** (09:30–09:45 OR, trade from 09:45) in the direction **opposite** to the C2 hit:
   - Bullish C3 (took C2 high) → OR **low** break → **short** (RL−1t−slip), SL **RH**, TP **RL−range**.
   - Bearish C3 (took C2 low) → OR **high** break → **long** (RH+1t+slip), SL **RL**, TP **RH+range**.

One trade per session; exit by TP/SL or 16:00 session close.

Example::

  python3 backtest_c3_swing_orb_fade.py
  python3 backtest_c3_swing_orb_fade.py --compare-v2d
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
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from backtest_midnight_open_flip import (  # noqa: E402
    ORB_HI,
    ORB_LO,
    Trade,
    USD_PER_POINT,
    orb_v2b_targets,
)

NY = pytz.timezone('America/New_York')
SESSION_END = mdata.SESSION_HI
TICK = 0.25
SLIP_TICKS = 1
DEFAULT_SETUPS = HERE.parent / 'daily_candlestick_theory' / 'setups.csv'
DEFAULT_DBN = mdata.DEFAULT_DBN


@dataclass(frozen=True)
class Swing15:
    kind: str  # 'high' | 'low'
    price: float
    pivot_ts: pd.Timestamp
    confirm_ts: pd.Timestamp


def build_15m_swings(bars15: pd.DataFrame) -> list[Swing15]:
    bars15 = bars15.sort_index()
    if len(bars15) < 3:
        return []
    out: list[Swing15] = []
    highs = bars15['high'].astype(float).values
    lows = bars15['low'].astype(float).values
    idx = bars15.index
    for k in range(1, len(bars15) - 1):
        if highs[k] > highs[k - 1] and highs[k] >= highs[k + 1]:
            out.append(Swing15('high', float(highs[k]), pd.Timestamp(idx[k]), pd.Timestamp(idx[k + 1])))
        if lows[k] < lows[k - 1] and lows[k] <= lows[k + 1]:
            out.append(Swing15('low', float(lows[k]), pd.Timestamp(idx[k]), pd.Timestamp(idx[k + 1])))
    return out


def first_intraday_hit_ts(
    sess_1m: pd.DataFrame,
    direction: str,
    c2_extreme: float,
    c2_low: float,
) -> pd.Timestamp | None:
    """First 1m timestamp when C3 **hit** is realized intraday."""
    for ts, bar in sess_1m.sort_index().iterrows():
        hi, lo = float(bar['high']), float(bar['low'])
        if direction == 'bullish' and hi > c2_extreme + 1e-9:
            return pd.Timestamp(ts)
        if direction == 'bearish' and lo < c2_low - 1e-9:
            return pd.Timestamp(ts)
    return None


def first_qualifying_swing(
    bars15: pd.DataFrame,
    hit_ts: pd.Timestamp,
    direction: str,
    c2_extreme: float,
    c2_low: float,
) -> Swing15 | None:
    """First 15m swing **after** hit with extension beyond C2 extreme."""
    for sw in build_15m_swings(bars15):
        if sw.confirm_ts <= hit_ts:
            continue
        if direction == 'bullish' and sw.kind == 'high' and sw.price > c2_extreme + 1e-9:
            return sw
        if direction == 'bearish' and sw.kind == 'low' and sw.price < c2_low - 1e-9:
            return sw
    return None


def first_qualifying_swing_confirm(
    bars15: pd.DataFrame,
    hit_ts: pd.Timestamp,
    direction: str,
    c2_extreme: float,
    c2_low: float,
) -> pd.Timestamp | None:
    sw = first_qualifying_swing(bars15, hit_ts, direction, c2_extreme, c2_low)
    return sw.confirm_ts if sw else None


def simulate_orb_v2b_opposite_break(
    session_day: date,
    sess_1m: pd.DataFrame,
    usd_per_point: float,
    *,
    earliest_entry: pd.Timestamp,
    trade_side: str,
) -> list[Trade]:
    """
    v2b stop entry on OR break **opposite** to the C2 extension (take the break).

    Matches ``london_ny_orb_stops.simulate_session`` for one side only.
    """
    trades: list[Trade] = []
    orb = orb_v2b_targets(sess_1m, session_day)
    if orb is None:
        return trades
    rh, rl, rv, target_long, target_short = orb
    if rv <= 0:
        return trades

    tick = TICK
    slip = SLIP_TICKS * tick
    orb_ready = NY.localize(datetime.combine(session_day, ORB_HI))
    session_end = NY.localize(datetime.combine(session_day, SESSION_END))

    if trade_side == 'short':
        break_trig = rl - tick
        entry_px = break_trig - slip
        stop_px = rh
        tp_px = target_short
    else:
        break_trig = rh + tick
        entry_px = break_trig + slip
        stop_px = rl
        tp_px = target_long

    traded = False
    in_trade = False
    pos = entry_ts = None

    def close(exit_ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal in_trade, pos, entry_ts
        if not in_trade:
            return
        trades.append(Trade(session_day, pos, entry_ts, entry_px, exit_ts, exit_px, reason, usd_per_point))
        in_trade = False
        pos = None

    post = sess_1m[(sess_1m.index >= earliest_entry) & (sess_1m.index < session_end)].sort_index()
    for ts, bar in post.iterrows():
        if ts < orb_ready:
            continue
        hi, lo = float(bar['high']), float(bar['low'])

        if not in_trade and not traded:
            if trade_side == 'short' and lo <= break_trig + 1e-9:
                in_trade = True
                traded = True
                pos = 'short'
                entry_ts = ts
            elif trade_side == 'long' and hi >= break_trig - 1e-9:
                in_trade = True
                traded = True
                pos = 'long'
                entry_ts = ts

        if in_trade:
            if pos == 'short':
                if hi >= stop_px - 1e-9:
                    close(ts, stop_px, 'sl_orb_boundary')
                elif lo <= tp_px + 1e-9:
                    close(ts, tp_px, 'tp_v2b')
            else:
                if lo <= stop_px + 1e-9:
                    close(ts, stop_px, 'sl_orb_boundary')
                elif hi >= tp_px - 1e-9:
                    close(ts, tp_px, 'tp_v2b')

    if in_trade and not post.empty:
        last_ts = post.index.max()
        close(last_ts, float(post.loc[last_ts, 'close']), 'session_16:00')

    return trades


def simulate_plain_v2d_session(
    session_day: date,
    sess_1m: pd.DataFrame,
    usd_per_point: float,
) -> list[Trade]:
    """Unfiltered v2d on C3 day: both fade directions, up to two legs."""
    orb_ready = NY.localize(datetime.combine(session_day, ORB_HI))
    short_trades = simulate_orb_v2b_opposite_break(
        session_day, sess_1m, usd_per_point, earliest_entry=orb_ready, trade_side='short'
    )
    long_trades = simulate_orb_v2b_opposite_break(
        session_day, sess_1m, usd_per_point, earliest_entry=orb_ready, trade_side='long'
    )
    # v2d allows one per direction; merge chronologically, cap 2
    merged = sorted(short_trades + long_trades, key=lambda t: t.entry_time)
    return merged[:2]


def simulate_c3_session(
    setup: pd.Series,
    sess_1m: pd.DataFrame,
    bars15: pd.DataFrame,
    usd_per_point: float,
) -> tuple[list[Trade], dict]:
    """Returns trades and diagnostic meta."""
    session_day = date.fromisoformat(str(setup['c3_date']))
    direction = str(setup['direction'])
    c2_extreme = float(setup['c2_expected_extreme'])
    c2_low = float(setup['c2_low'])

    meta: dict = {
        'session': session_day.isoformat(),
        'direction': direction,
        'hit_ts': '',
        'swing_confirm_ts': '',
        'skipped': 'ok',
    }

    hit_ts = first_intraday_hit_ts(sess_1m, direction, c2_extreme, c2_low)
    if hit_ts is None:
        meta['skipped'] = 'no_intraday_hit'
        return [], meta
    meta['hit_ts'] = str(hit_ts)

    swing_ts = first_qualifying_swing_confirm(bars15, hit_ts, direction, c2_extreme, c2_low)
    if swing_ts is None:
        meta['skipped'] = 'no_swing_after_hit'
        return [], meta
    meta['swing_confirm_ts'] = str(swing_ts)

    orb_ready = NY.localize(datetime.combine(session_day, ORB_HI))
    earliest = max(swing_ts, hit_ts, orb_ready)
    trade_side = 'short' if direction == 'bullish' else 'long'
    trades = simulate_orb_v2b_opposite_break(
        session_day, sess_1m, usd_per_point, earliest_entry=earliest, trade_side=trade_side
    )
    if not trades:
        meta['skipped'] = 'no_orb_fade_fill'
    return trades, meta


def print_summary(label: str, trades: list[Trade]) -> None:
    if not trades:
        print(f'## {label}\n\nNo trades.\n', flush=True)
        return
    pnl = np.array([t.pnl_usd for t in trades], dtype=float)
    reasons = pd.Series([t.reason_exit for t in trades]).value_counts()
    print(f'## {label}\n', flush=True)
    print(f'- **Trades:** {len(trades)}', flush=True)
    print(f'- **Total P&L:** ${pnl.sum():,.2f}', flush=True)
    print(f'- **Win rate:** {100 * (pnl > 0).mean():.1f}%', flush=True)
    print(f'- **Median:** ${np.median(pnl):,.2f}', flush=True)
    print(f'- **Exits:** {", ".join(f"{k}={v}" for k, v in reasons.head(6).items())}', flush=True)
    print(flush=True)


def print_direction_breakdown(trades: list[tuple[Trade, str]]) -> None:
    """``trades`` as ``(Trade, c3_direction)`` pairs."""
    if not trades:
        return
    print('## P&L by C3 direction\n', flush=True)
    print('| C3 direction | Trades | Total P&L | Win % | Median |', flush=True)
    print('|---|---:|---:|---:|---:|', flush=True)
    for direction in ('bullish', 'bearish'):
        subset = [t for t, d in trades if d == direction]
        if not subset:
            print(f'| {direction} | 0 | — | — | — |', flush=True)
            continue
        pnl = np.array([t.pnl_usd for t in subset], dtype=float)
        print(
            f'| {direction} | {len(subset)} | ${pnl.sum():,.2f} | '
            f'{100 * (pnl > 0).mean():.1f}% | ${np.median(pnl):,.2f} |',
            flush=True,
        )
    print(flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--setups-csv', type=Path, default=DEFAULT_SETUPS)
    ap.add_argument('--compare-v2d', action='store_true', help='Also run plain v2d on C3 days')
    args = ap.parse_args()

    if not args.setups_csv.is_file() or not args.dbn.is_file():
        print('Missing setups CSV or DBN', file=sys.stderr)
        return 1

    setups = pd.read_csv(args.setups_csv)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    usd_pp = USD_PER_POINT['mnq']

    all_trades: list[Trade] = []
    traded_meta: list[tuple[Trade, str]] = []
    diag_rows: list[dict] = []
    v2d_trades: list[Trade] = []

    for _, setup in setups.iterrows():
        d = date.fromisoformat(str(setup['c3_date']))
        raw = gby.get(d)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, d)
        if sess.empty:
            continue
        bars15 = mdata.resample_15m_midnight_to_1600(raw, d)
        if bars15 is None or bars15.empty:
            continue

        trades, meta = simulate_c3_session(setup, sess, bars15.sort_index(), usd_pp)
        direction = str(setup['direction'])
        meta['setup_id'] = int(setup['setup_id'])
        meta['csv_hit'] = bool(setup['hit'])
        diag_rows.append(meta)
        all_trades.extend(trades)
        for t in trades:
            traded_meta.append((t, direction))

        if args.compare_v2d:
            v2d_trades.extend(simulate_plain_v2d_session(d, sess, usd_pp))

    out_csv = HERE / 'backtest_c3_swing_orb_fade_trades_mnq.csv'
    if all_trades:
        pd.DataFrame(
            [
                {
                    'session': t.session.isoformat(),
                    'c3_direction': d,
                    'side': t.side,
                    'entry_time': str(t.entry_time),
                    'entry_px': t.entry_px,
                    'exit_time': str(t.exit_time),
                    'exit_px': t.exit_px,
                    'reason_exit': t.reason_exit,
                    'pnl_usd': round(t.pnl_usd, 2),
                }
                for t, d in traded_meta
            ]
        ).to_csv(out_csv, index=False)
        print(f'Wrote {out_csv}', flush=True)

    pd.DataFrame(diag_rows).to_csv(HERE / 'backtest_c3_swing_orb_fade_diag_mnq.csv', index=False)

    n_c3 = len(setups)
    n_traded = len(all_trades)
    n_hit = sum(1 for r in diag_rows if r.get('hit_ts'))
    n_swing = sum(1 for r in diag_rows if r.get('swing_confirm_ts'))
    print(f'C3 setup days: {n_c3} | intraday hit: {n_hit} | swing after hit: {n_swing} | trades: {n_traded}\n', flush=True)

    print_summary('C3 + swing + v2b opposite OR break', all_trades)
    print_direction_breakdown(traded_meta)
    if args.compare_v2d:
        print_summary('Plain v2d on same C3 calendar days (reference)', v2d_trades)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
