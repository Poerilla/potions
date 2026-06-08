#!/usr/bin/env python3
"""
Experimental v2b MNQ: **5m close breakout** + **limit at 60% retracement into range**;
**stop** opposite OR boundary; **target** RH±Range like step2.

• **Leg 1:** Earliest 5m **close** above RH or below RL; limit at RH−0.6·Range (long) or
  RL+0.6·Range (short). If that signal never fills, **no trade that day** (no opposite leg).

• **Leg 2:** After leg 1 exit, only the **first opposite** 5m close outside the range;
  same limit rule. If it does not fill, stop (leg 1 kept).

Output: ``adaptive_experiment/mnq_orb_results_stops_60pct.csv`` (does not touch canonical v2b).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

_SCR = Path(__file__).resolve().parent.parent.parent / 'scripts'
sys.path.insert(0, str(_SCR))
from step2_preplaced_stops import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    DEFAULT_OPEN_RANGE_MIN,
    MAX_TRADES_PER_DAY,
    PRODUCTS,
    load_one_min,
    open_range_end_time,
)

RETRACE = 0.60
OUT_DEFAULT = Path(__file__).resolve().parent / 'mnq_orb_results_stops_60pct.csv'


def _bars5(post_range_1m: pd.DataFrame) -> pd.DataFrame:
    if post_range_1m.empty:
        return post_range_1m
    return (
        post_range_1m.sort_index().resample('5min', label='left', closed='right')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            symbol=('symbol', 'first'),
        )
        .dropna(subset=['open'])
    )


def _first_break_both(
    rh: float, rl: float, bars5: pd.DataFrame
) -> Optional[Tuple[str, pd.Timestamp]]:
    ta = tb = None
    ab = bars5[bars5['close'] > rh]
    below = bars5[bars5['close'] < rl]
    if not ab.empty:
        ta = ab.index.min()
    if not below.empty:
        tb = below.index.min()
    if ta is None and tb is None:
        return None
    if tb is None or (ta is not None and ta <= tb):
        return ('Long', ta)
    return ('Short', tb)


def _first_break_short_only(
    rh: float, rl: float, bars5: pd.DataFrame
) -> Optional[Tuple[str, pd.Timestamp]]:
    bx = bars5[bars5['close'] < rl]
    if bx.empty:
        return None
    return ('Short', bx.index.min())


def _first_break_long_only(
    rh: float, rl: float, bars5: pd.DataFrame
) -> Optional[Tuple[str, pd.Timestamp]]:
    bx = bars5[bars5['close'] > rh]
    if bx.empty:
        return None
    return ('Long', bx.index.min())


def simulate_day_60pct(
    rh: float,
    rl: float,
    rv: float,
    trade_bars_1m: pd.DataFrame,
) -> List[Tuple[str, float, float, str]]:
    """Mirrors step2 intrabar pessimism when stop and target coincide (stop first)."""
    ti = trade_bars_1m.sort_index()
    trades: List[Tuple[str, float, float, str]] = []
    if ti.empty or rv <= 1e-12:
        return trades
    bars5_full = _bars5(ti)

    leg = 0
    min_exclusive: Optional[pd.Timestamp] = None

    while leg < MAX_TRADES_PER_DAY:
        bx = (
            bars5_full
            if min_exclusive is None
            else bars5_full[bars5_full.index > min_exclusive]
        )
        if bx.empty:
            break
        if leg == 0:
            fb = _first_break_both(rh, rl, bx)
        elif trades[-1][0] == 'Long':
            fb = _first_break_short_only(rh, rl, bx)
        else:
            fb = _first_break_long_only(rh, rl, bx)

        if fb is None:
            break
        direction, t5_open = fb
        if direction == 'Long':
            lim = rh - RETRACE * rv
            target = rh + rv
            stop_v = rl
        else:
            lim = rl + RETRACE * rv
            target = rl - rv
            stop_v = rh

        fill_after = t5_open + pd.Timedelta(minutes=5)
        rest = ti[ti.index >= fill_after]
        rest = rest[rest.index.map(lambda t: t.time() <= EOD_CUTOFF)]
        entry_ts: Optional[pd.Timestamp] = None
        for ts, row in rest.iterrows():
            lo, hi = float(row['low']), float(row['high'])
            if direction == 'Long' and lo - 1e-9 <= lim:
                entry_ts = ts
                break
            if direction == 'Short' and hi + 1e-9 >= lim:
                entry_ts = ts
                break
        if entry_ts is None:
            break

        path = ti[ti.index >= entry_ts]
        path = path[path.index.map(lambda t: t.time() <= EOD_CUTOFF)]
        exit_px = lim
        res = 'EOD-Loss'
        exit_ts = entry_ts
        done = False
        for ts, row in path.iterrows():
            h, lo = float(row['high']), float(row['low'])
            if direction == 'Long':
                if lo < stop_v:
                    exit_px, res, exit_ts = stop_v, 'Loss', ts
                    done = True
                    break
                if h >= target:
                    exit_px, res, exit_ts = target, 'Win', ts
                    done = True
                    break
            else:
                if h > stop_v:
                    exit_px, res, exit_ts = stop_v, 'Loss', ts
                    done = True
                    break
                if lo <= target:
                    exit_px, res, exit_ts = target, 'Win', ts
                    done = True
                    break
        if not done and not path.empty:
            last_row = path.iloc[-1]
            eod = float(last_row['close'])
            exit_ts = last_row.name
            if direction == 'Long':
                res = 'EOD-Win' if eod > lim else 'EOD-Loss'
            else:
                res = 'EOD-Win' if eod < lim else 'EOD-Loss'
            exit_px = eod

        trades.append((direction, lim, exit_px, res))
        min_exclusive = exit_ts
        leg += 1

    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--open-range-minutes', type=int, default=DEFAULT_OPEN_RANGE_MIN)
    ap.add_argument('--out', type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()

    if not (1 <= args.open_range_minutes <= 150):
        raise SystemExit('--open-range-minutes must be 1..150')

    cfg = PRODUCTS['MNQ']
    mult = cfg['mult']
    range_end = open_range_end_time(args.open_range_minutes)
    _re = pd.Timestamp('2000-01-01 09:30:00') + pd.Timedelta(
        minutes=args.open_range_minutes
    )
    print(
        f"60% limit retrace (5m close break)  |  ORB 9:30–{_re.strftime('%H:%M')}  |  → {args.out}"
    )

    df = load_one_min('MNQ')
    results = []
    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        range_bars = day_df[day_df['t'] < range_end]
        if range_bars.empty:
            continue
        rh, rl = float(range_bars['high'].max()), float(range_bars['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        trade_bars = day_df[day_df['t'] >= range_end]
        if trade_bars.empty:
            continue
        day_trades = simulate_day_60pct(rh, rl, rv, trade_bars)
        sym = trade_bars.iloc[0]['symbol']
        for d, entry, exit_p, res in day_trades:
            pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append(
                {
                    'Date': day,
                    'Day_of_Week': day.strftime('%A'),
                    'Symbol': sym,
                    'Range_High': rh,
                    'Range_Low': rl,
                    'Range': rv,
                    'Trade_Direction': d,
                    'Entry_Price': entry,
                    'Exit_Price': exit_p,
                    'Trade_PL': round(pl, 6),
                    'Net_$': round(pl * mult - FEE_RT, 2),
                    'Result': res,
                }
            )

    out = pd.DataFrame(results)
    if out.empty:
        print('No trades produced.')
    else:
        out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
        out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {len(out):,} trades -> {args.out}")
    if not out.empty:
        wins = (out['Trade_PL'] > 0).sum()
        print(
            f"Win rate: {wins/len(out)*100:.1f}%  "
            f"Total P/L: {out['Trade_PL'].sum():.0f} pts  "
            f"Net $ @ 1 ctr: ${out['Net_$'].sum():,.0f}"
        )
        eq = out['Net_$'].cumsum()
        print(f"Max realized DD: ${(eq - eq.cummax()).min():,.2f}")


if __name__ == '__main__':
    main()
