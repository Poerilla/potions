#!/usr/bin/env python3
"""
ORB open-limit variant (v2b research, 1 × MNQ).

After OR formation (9:30–9:45), wait for first **5 m close beyond** RH+tick / RL−tick
(same-close logic as breakout_close_limit). Place a **limit at the OPEN of the first 9:30 bar**
(one session price: first 1 m bar at exactly 09:30). Limit goes live when that 5 m breakout bar ends.

Targets: Long RH+Range, Short RL−Range (classic ORB TP).
Stop (v1 tweak): Long stop = session_open − Range, Short = session_open + Range.

Bracket-then-reverse: at most one Long + one Short per day after each leg exits.
1 contract — no scale-outs.

Output: CSV compatible with orb_open_limit case charts.
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
MAX_TRADES_PER_DAY = 2

TICK = 0.25
CONTRACTS = 1
MULT = 2.0
FEE_RT = 1.50

DBN_DEFAULT = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
OUT_DEFAULT = Path(__file__).resolve().parent.parent / 'case_studies' / 'open_limit' / 'mnq_orb_open_limit.csv'


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
    fm = df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
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
    ix0 = df1.index[0]
    anchor = ix0.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def first_bar_open_at_0930(day_1m: pd.DataFrame) -> Optional[float]:
    """Open price of first 09:30 1 m bar (= first bar whose time is exactly 09:30)."""
    subset = day_1m[day_1m['t'] == dtime(9, 30)]
    if subset.empty:
        return None
    return float(subset.iloc[0]['open'])


def first_breakout_close_confirm_5m(
    bars5_trade: pd.DataFrame,
    rh: float,
    rl: float,
    tick: float,
    arm_long: bool,
    arm_short: bool,
) -> Optional[Tuple[str, pd.Timestamp]]:
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


def simulate_leg_open_limit(
    day_1m: pd.DataFrame,
    bars5_full: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    session_open: float,
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

    limit_px = session_open
    first_working = brk_left + pd.Timedelta(minutes=5)

    fwd = day_1m[day_1m.index >= first_working]
    fill_ts: Optional[pd.Timestamp] = None
    for ts, bar in fwd.iterrows():
        if direction == 'Long' and float(bar['low']) <= limit_px + 1e-9:
            fill_ts = ts
            break
        if direction == 'Short' and float(bar['high']) >= limit_px - 1e-9:
            fill_ts = ts
            break
    if fill_ts is None:
        return None

    entry = limit_px
    if direction == 'Long':
        target = rh + rv
        stop = session_open - rv
    else:
        target = rl - rv
        stop = session_open + rv

    path = day_1m[day_1m.index >= fill_ts]
    intraday = path[path.index.map(lambda tt: tt.time() < EOD_CUTOFF)]
    exit_ts = fill_ts
    last_px = entry
    outcome = ''

    for ts, bar in intraday.iterrows():
        h, l = float(bar['high']), float(bar['low'])
        if direction == 'Long':
            if l <= stop + 1e-12:
                last_px = stop
                exit_ts = ts
                outcome = 'Loss'
                break
            if h >= target - 1e-12:
                last_px = target
                exit_ts = ts
                outcome = 'Win'
                break
        else:
            if h >= stop - 1e-12:
                last_px = stop
                exit_ts = ts
                outcome = 'Loss'
                break
            if l <= target + 1e-12:
                last_px = target
                exit_ts = ts
                outcome = 'Win'
                break

    res = outcome
    if not outcome:
        sess = path[path.index.map(lambda ti: ti.time() < RTH_END)]
        if sess.empty:
            return None
        eod = float(sess.iloc[-1]['close'])
        exit_ts = sess.index[-1]
        last_px = eod
        ok = eod > entry if direction == 'Long' else eod < entry
        res = 'EOD-Win' if ok else 'EOD-Loss'

    pl = (last_px - entry) if direction == 'Long' else (entry - last_px)
    gross_usd = round(pl * MULT * CONTRACTS, 2)
    net_usd = round(gross_usd - FEE_RT * CONTRACTS, 2)

    return {
        'Trade_Direction': direction,
        'Entry_Price': round(entry, 4),
        'Exit_Price': round(last_px, 4),
        'Trade_PL': round(pl, 6),
        'Gross_$': gross_usd,
        'Net_$': net_usd,
        'Result': res,
        'Entry_Time': fill_ts.isoformat(),
        'Exit_Time': exit_ts.isoformat(),
        'Session_Open_930': round(session_open, 4),
        'Stop_Price': round(stop, 4),
        'Symbol': sym,
    }


def simulate_day(
    day_1m: pd.DataFrame,
    bars5: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    session_open: float,
) -> List[Dict[str, Any]]:
    sym = str(day_1m['symbol'].iloc[0]) if 'symbol' in day_1m.columns else ''
    traded: set = set()
    out: List[Dict[str, Any]] = []
    prior: Optional[str] = None
    for _ in range(MAX_TRADES_PER_DAY):
        row = simulate_leg_open_limit(day_1m, bars5, rh, rl, rv, session_open, traded, prior, sym)
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
        range_bars = day_df[day_df['t'] < RANGE_END_T]
        if range_bars.empty:
            continue
        rh = float(range_bars['high'].max())
        rl = float(range_bars['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        d1 = day_df[day_df['t'] >= RTH_START]
        so = first_bar_open_at_0930(d1)
        if so is None:
            continue
        b5 = resample_5m(d1)
        sym = str(day_df['symbol'].iloc[0])
        legs = simulate_day(d1, b5, rh, rl, rv, so)
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
                    'Session_Open_930': leg['Session_Open_930'],
                    'Stop_Price': leg['Stop_Price'],
                }
            )

    out_df = pd.DataFrame(rows)
    if out_df.empty:
        print('No trades.')
        return 1
    out_df['Cumulative_PL'] = out_df['Trade_PL'].cumsum().round(6)
    out_df['Cumulative_$'] = out_df['Net_$'].cumsum().round(2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)

    wins = (out_df['Net_$'] > 0).sum()
    print(f'Wrote {len(out_df)} legs -> {out_path}')
    print(f'Win rate Net_$>0: {wins/len(out_df)*100:.1f}%  ΣNet_$ ${out_df["Net_$"].sum():,.2f}')
    eq = out_df['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f'Max DD Net_$ ${dd.min():,.2f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
