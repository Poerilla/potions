#!/usr/bin/env python3
"""
Experimental MNQ ORB variant (research for v2e / v2b breakout behavior).

Forward-only 1m simulation (no oracle CSV inputs):
  - ORB 9:30–9:45; first *confirmed* breakout uses **5 m bar close** vs triggers (not 1 m wicks): Long if
    close >= RH+1 tick, Short if close <= RL−1 tick; same-bar both (rare tie) → tie-break via that bar open vs OR midpoint.
  - 5 m bars anchored to **9:30** ET (fixes mis-bucketed resample). Breakout candle = that 5 m bar; limit @ its close
    after bar completes.
  - Initial SL = last 5m swing pivot ± 5 ticks (fractals on bars strictly before breakout); else range extreme.
  - Limit activates from the **first 1m bar opening at/after breakout bar end** (>= ``brk_left + 5m``, not ``>``),
    so e.g. [9:55–10:00] break can fill on the 10:00 candle.
  - 3 MNQ contracts: −1 half target, −1 full target, runner flat at last RTH minute before EOD cutoff.
  - After half target, SL → breakout candle low/high.
  - Intrabar: stop-before-target (step2 pessimism). Bracket-then-reverse for leg 2.

Output: CSV like mnq_orb_results_stops + Entry_Time, Exit_Time, Initial_Stop, Gross_$.
  - ``Trade_PL`` = Σ index points over the 3 MNQ (sum of per-lot point P/L), not per-contract average.
  - ``Gross_$`` / ``Net_$`` = full 3-micro $ (``Net_$`` subtracts CONTRACTS × FEE_RT round-trip approximation).
"""
from __future__ import annotations

import argparse
from datetime import time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import databento as db
import pandas as pd
import pytz

NY_TZ = pytz.timezone('America/New_York')
RTH_START = dtime(9, 30)
RTH_END = dtime(16, 0)
EOD_CUTOFF = dtime(15, 55)
OPEN_RANGE_MIN = 15

TICK = 0.25
SWING_PAD_TICKS = 5
CONTRACTS = 3
MULT = 2.0
FEE_RT = 1.50  # all-in RT per MNQ micro (multiplied ×CONTRACTS for full 3-lot leg)

DBN_DEFAULT = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
OUT_DEFAULT = Path(__file__).resolve().parent / 'mnq_breakout_close_limit_scaleout.csv'


def open_range_end_time(minutes: int) -> dtime:
    t = pd.Timestamp('2000-01-01 09:30:00') + pd.Timedelta(minutes=minutes)
    return t.time()


RANGE_END_T = open_range_end_time(OPEN_RANGE_MIN)


def load_one_min_mnq(history_start=None) -> pd.DataFrame:
    print(f'Loading {DBN_DEFAULT} ...')
    store = db.DBNStore.from_file(DBN_DEFAULT)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (
        df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    )
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= RTH_START) & (df['t'] < RTH_END)]
    if history_start is not None:
        df = df[df['date'] >= pd.Timestamp(history_start).date()]
    else:
        df = df[df['date'] >= pd.Timestamp('2021-03-04').date()]
    df = df.set_index('ts_event').sort_index()
    print(f'  {len(df):,} 1-min RTH front-month bars')
    return df


def resample_5m(df1: pd.DataFrame) -> pd.DataFrame:
    """5 m OHLC anchored to NY 9:30 so buckets are [9:30,9:35), … (not drifted midnight origin)."""
    ix0 = df1.index[0]
    anchor = ix0.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def last_fractal_swing_low(b5: pd.DataFrame) -> Optional[float]:
    if len(b5) < 3:
        return None
    low = b5['low'].values
    vals = []
    for i in range(1, len(b5) - 1):
        if low[i] <= low[i - 1] and low[i] <= low[i + 1]:
            vals.append(low[i])
    return vals[-1] if vals else None


def last_fractal_swing_high(b5: pd.DataFrame) -> Optional[float]:
    if len(b5) < 3:
        return None
    high = b5['high'].values
    vals = []
    for i in range(1, len(b5) - 1):
        if high[i] >= high[i - 1] and high[i] >= high[i + 1]:
            vals.append(high[i])
    return vals[-1] if vals else None


def first_breakout_close_confirm_5m(
    bars5_trade: pd.DataFrame,
    rh: float,
    rl: float,
    tick: float,
    arm_long: bool,
    arm_short: bool,
) -> Optional[Tuple[str, pd.Timestamp]]:
    """
    First completed post-ORB 5 m bar whose **close** is beyond brackets (OCO spirit, no intrabar lookahead).
    Wicks touching triggers without a confirming close no longer classify as breakout.
    """
    lt, st = rh + tick, rl - tick
    for ts, row in bars5_trade.iterrows():
        clo = float(row['close'])
        opn = float(row['open'])
        long_ok = arm_long and clo >= lt - 1e-12
        short_ok = arm_short and clo <= st + 1e-12
        if not long_ok and not short_ok:
            continue
        if long_ok and short_ok:
            mid = (rh + rl) / 2.0
            return ('Long', ts) if opn >= mid else ('Short', ts)
        if long_ok:
            return 'Long', ts
        return 'Short', ts
    return None


def _range_end_ts(day_first: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(day_first)
    return ts.replace(hour=RANGE_END_T.hour, minute=RANGE_END_T.minute, second=0, microsecond=0)


def simulate_leg_scaleout(
    day_1m: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    traded_dirs: set,
    prior_end_iso: Optional[str],
    sym: str,
) -> Optional[Dict[str, Any]]:
    arm_long = 'Long' not in traded_dirs
    arm_short = 'Short' not in traded_dirs
    if not (arm_long or arm_short):
        return None

    r0 = _range_end_ts(day_1m.index[0])
    bars_trade = bars5_full[bars5_full.index >= r0]
    if prior_end_iso is not None:
        bars_trade = bars_trade[bars_trade.index > pd.Timestamp(prior_end_iso)]
    if bars_trade.empty:
        return None

    hit = first_breakout_close_confirm_5m(bars_trade, rh, rl, TICK, arm_long, arm_short)
    if hit is None:
        return None
    direction, brk_left = hit

    if brk_left not in bars5_full.index:
        return None
    brk_row = bars5_full.loc[brk_left]
    brk_lo = float(brk_row['low'])
    brk_hi = float(brk_row['high'])
    limit_px = float(brk_row['close'])
    # First minute we may work the limit is the bar that *opens* when the 5m breakout bar ends
    # (e.g. breakout [9:55,10:00) → eligible from 10:00 inclusive, not strictly after).
    first_working = brk_left + pd.Timedelta(minutes=5)

    swing_slice = bars5_full[bars5_full.index < brk_left]
    if swing_slice.empty:
        return None

    if direction == 'Long':
        sw = last_fractal_swing_low(swing_slice)
        stop0 = (sw - SWING_PAD_TICKS * TICK) if sw is not None else float(swing_slice['low'].min()) - SWING_PAD_TICKS * TICK
        half_T = (rh + (rh + rv)) / 2.0
        full_T = rh + rv
        bo_protect = brk_lo
    else:
        sw = last_fractal_swing_high(swing_slice)
        stop0 = (sw + SWING_PAD_TICKS * TICK) if sw is not None else float(swing_slice['high'].max()) + SWING_PAD_TICKS * TICK
        half_T = (rl + (rl - rv)) / 2.0
        full_T = rl - rv
        bo_protect = brk_hi

    fwd_fill = day_1m[day_1m.index >= first_working]
    fill_ts: Optional[pd.Timestamp] = None
    for ts, bar in fwd_fill.iterrows():
        if direction == 'Long' and float(bar['low']) <= limit_px + 1e-9:
            fill_ts = ts
            break
        if direction == 'Short' and float(bar['high']) >= limit_px - 1e-9:
            fill_ts = ts
            break
    if fill_ts is None:
        return None

    entry = limit_px

    qty = CONTRACTS
    sl = stop0
    half_done = False
    full_done = False
    sum_pts = 0.0  # total index pts across CONTRACTS exited (sum_i pts_i)

    exit_ts = fill_ts
    last_px = entry

    def long_intrabar(bar_ts: pd.Timestamp, hi: float, lo: float) -> bool:
        nonlocal qty, sl, half_done, full_done, sum_pts, exit_ts, last_px
        if direction != 'Long':
            return False
        if qty <= 0:
            return False
        if lo <= sl + 1e-9:
            ep = sl
            for _ in range(qty):
                sum_pts += ep - entry
                last_px = ep
                exit_ts = bar_ts
            qty = 0
            return True
        if qty == CONTRACTS and not half_done and hi >= half_T - 1e-9:
            ep = half_T
            sum_pts += ep - entry
            last_px = ep
            exit_ts = bar_ts
            qty -= 1
            half_done = True
            sl = bo_protect
        if qty == 2 and half_done and not full_done and hi >= full_T - 1e-9:
            ep = full_T
            sum_pts += ep - entry
            last_px = ep
            exit_ts = bar_ts
            qty -= 1
            full_done = True
        if qty > 0 and lo <= sl + 1e-9:
            ep = sl
            for _ in range(qty):
                sum_pts += ep - entry
                last_px = ep
                exit_ts = bar_ts
            qty = 0
        return False

    def short_intrabar(bar_ts: pd.Timestamp, hi: float, lo: float) -> bool:
        nonlocal qty, sl, half_done, full_done, sum_pts, exit_ts, last_px
        if direction != 'Short':
            return False
        if qty <= 0:
            return False
        if hi >= sl - 1e-9:
            ep = sl
            for _ in range(qty):
                sum_pts += entry - ep
                last_px = ep
                exit_ts = bar_ts
            qty = 0
            return True
        if qty == CONTRACTS and not half_done and lo <= half_T + 1e-9:
            ep = half_T
            sum_pts += entry - ep
            last_px = ep
            exit_ts = bar_ts
            qty -= 1
            half_done = True
            sl = bo_protect
        if qty == 2 and half_done and not full_done and lo <= full_T + 1e-9:
            ep = full_T
            sum_pts += entry - ep
            last_px = ep
            exit_ts = bar_ts
            qty -= 1
            full_done = True
        if qty > 0 and hi >= sl - 1e-9:
            ep = sl
            for _ in range(qty):
                sum_pts += entry - ep
                last_px = ep
                exit_ts = bar_ts
            qty = 0
        return False

    path = day_1m[day_1m.index >= fill_ts]
    intraday_only = path[path.index.map(lambda t: t.time() < EOD_CUTOFF)]
    stopped_out = False
    for ts, bar in intraday_only.iterrows():
        hi = float(bar['high'])
        lo = float(bar['low'])
        if direction == 'Long':
            long_intrabar(ts, hi, lo)
        else:
            short_intrabar(ts, hi, lo)
        if qty == 0:
            stopped_out = True
            break

    if qty > 0:
        sess_end = path[path.index.map(lambda ti: ti.time() < RTH_END)]
        if sess_end.empty:
            return None
        eod_price = float(sess_end.iloc[-1]['close'])
        eod_ix = sess_end.index[-1]
        for _ in range(qty):
            if direction == 'Long':
                sum_pts += eod_price - entry
            else:
                sum_pts += entry - eod_price
            last_px = eod_price
            exit_ts = eod_ix

    # Per-leg economics: sum_pts is total index-points across all 3 contract-units exited (Σ lot P/L pts).
    gross_usd = round(sum_pts * MULT, 2)
    net_usd = round(gross_usd - CONTRACTS * FEE_RT, 2)

    last_sess_ts = day_1m[day_1m['t'] < RTH_END].index[-1]
    ok = net_usd > 1e-6
    if exit_ts >= last_sess_ts:
        res = 'EOD-Win' if ok else 'EOD-Loss'
    else:
        res = 'Win' if ok else 'Loss'

    return {
        'Trade_Direction': direction,
        'Entry_Price': round(entry, 4),
        'Exit_Price': round(last_px, 4),
        'Trade_PL': round(sum_pts, 6),  # Σ index pts over 3 MNQ (not per-contract average)
        'Gross_$': gross_usd,
        'Net_$': net_usd,
        'Result': res,
        'Entry_Time': fill_ts.isoformat(),
        'Exit_Time': exit_ts.isoformat(),
        'Initial_Stop': round(stop0, 4),
        'Symbol': sym,
    }


def simulate_day(day_1m: pd.DataFrame, bars5: pd.DataFrame, rh: float, rl: float, rv: float) -> List[Dict[str, Any]]:
    sym = str(day_1m['symbol'].iloc[0]) if 'symbol' in day_1m.columns else ''
    traded: set = set()
    out: List[Dict[str, Any]] = []
    prior: Optional[str] = None
    for _ in range(2):
        row = simulate_leg_scaleout(day_1m, bars5, rh, rl, rv, traded, prior, sym)
        if row is None:
            break
        out.append(row)
        traded.add(row['Trade_Direction'])
        prior = row['Exit_Time']
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=str, default=str(OUT_DEFAULT))
    args = ap.parse_args()
    out_path = Path(args.out)
    df = load_one_min_mnq()

    rows = []
    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        rr = RANGE_END_T
        range_bars = day_df[day_df['t'] < rr]
        if range_bars.empty:
            continue
        rh = float(range_bars['high'].max())
        rl = float(range_bars['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        d1 = day_df[day_df['t'] >= RTH_START]
        if d1.empty:
            continue
        b5 = resample_5m(d1)
        sym = str(day_df['symbol'].iloc[0])
        legs = simulate_day(d1, b5, rh, rl, rv)
        for leg in legs:
            rows.append(
                {
                    'Date': day,
                    'Day_of_Week': pd.Timestamp(day).strftime('%A'),
                    'Symbol': sym,
                    'Range_High': rh,
                    'Range_Low': rl,
                    'Range': rv,
                    'Trade_Direction': leg['Trade_Direction'],
                    'Entry_Price': leg['Entry_Price'],
                    'Exit_Price': leg['Exit_Price'],
                    'Trade_PL': leg['Trade_PL'],
                    'Gross_$': leg['Gross_$'],
                    'Net_$': leg['Net_$'],
                    'Result': leg['Result'],
                    'Entry_Time': leg['Entry_Time'],
                    'Exit_Time': leg['Exit_Time'],
                    'Initial_Stop': leg['Initial_Stop'],
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        print('No trades simulated.')
        return 1

    # Cumulative (single stream)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)  # Σ index-pt across legs
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    wins = (out['Net_$'] > 0).sum()
    print(f'Wrote {len(out)} legs -> {out_path}')
    print(f'Win rate (Net_$>0): {wins / len(out) * 100:.1f}%  Σ Trade_PL (idx-pt, 3MNQ TOT/leg): {out["Trade_PL"].sum():.0f}')
    eq = out['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f'Max cumulative DD Net_$: ${dd.min():,.2f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
