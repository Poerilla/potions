#!/usr/bin/env python3
"""
**v2b_m limit @ boundary** — same **filters** as main ``v2b_m`` (long-only, ``bullish_break`` default,
PM-high OR geometry from ``engine``); **no** monthly-interaction oracle columns.

**Execution** (differs from tier‑1 OCO breakout):

1. **Signal:** first **RTH 5 m bar** (anchored 09:30 NY, ``closed=left``) ending **after** OR **[09:30, 09:45)** whose
   **close ≥ Range_High + 1 tick**.
2. **Entry:** **limit buy at Range_High** (opening-range **upper boundary** retest). Limit becomes active **after**
   the signal bar closes; first **1 m** touch ``low ≤ RH`` fills at ``RH``.
3. **Bracket** (canonical v2b): **TP** ``RH + Range``, **stop** ``RL``. Intraday pessimistic **stop-before-target**
   on ambiguous bars; unsettled → **EOD-Win** / **EOD-Loss** vs entry at last RTH close before 16:00 (same spirit as
   ``experiments/orb_open_limit_v2b.py``).

Output CSV + printed win rate (TP-style and Net_$>0), Σ Net \$, max DD on cumulative Net_\$.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
import pytz

LIMIT_HERE = Path(__file__).resolve().parent
V2B_M = LIMIT_HERE.parent
MNQ_ROOT = V2B_M.parents[1]
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(V2B_M), str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from plot_daily_prior_month_levels import (  # noqa: E402
    load_mnq_front_daily,
    monthly_high_low,
    prior_month_levels_series,
)

from engine import EPS_IDX_PT, qualify_v2b_m_legs, tp_hit  # noqa: E402

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
ORB_LO = time(9, 30)
ORB_HI = time(9, 45)
EOD_CUTOFF = time(15, 55)

TICK = 0.25
CONTRACTS = 1
MULT = 2.0
FEE_RT = 1.50

DEFAULT_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
DEFAULT_M1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_STOPS = MNQ_ROOT / 'mnq_orb_results_stops.csv'
DEFAULT_OUT = LIMIT_HERE / 'v2b_m_limit_retest_legs.csv'


def rth_slice(idx_df: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return idx_df[
        idx_df.index.map(lambda t: (t.date() == session_day and RTH_LO <= t.time() < RTH_HI))
    ].copy()


def resample_5m_rth(rth: pd.DataFrame, session_day: date) -> pd.DataFrame:
    if rth.empty:
        return rth
    anchor = NY.localize(datetime.combine(session_day, RTH_LO))
    return (
        rth.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def first_long_break_close_5m(bars5_after_or: pd.DataFrame, rh: float) -> pd.Timestamp | None:
    thr = rh + TICK
    for ts, row in bars5_after_or.iterrows():
        if float(row['close']) >= thr - 1e-12:
            return pd.Timestamp(ts)
    return None


def simulate_long_limit_at_rh(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
    *,
    symbol: str,
) -> dict | None:
    if rv <= 1e-12 or not (np.isfinite(rh) and np.isfinite(rl)):
        return None

    bars5 = resample_5m_rth(rth_1m, session_day)
    if bars5.empty:
        return None

    or_end = NY.localize(datetime.combine(session_day, ORB_HI))
    bars_sig = bars5[bars5.index >= or_end]
    sig_left = first_long_break_close_5m(bars_sig, rh)
    if sig_left is None:
        return None

    first_working = sig_left + pd.Timedelta(minutes=5)
    limit_px = rh
    target = rh + rv
    stop = rl

    fwd = rth_1m[rth_1m.index >= first_working]
    fwd = fwd[fwd.index.map(lambda t: t.time() <= EOD_CUTOFF)]
    fill_ts: pd.Timestamp | None = None
    for ts, bar in fwd.iterrows():
        if float(bar['low']) <= limit_px + 1e-9:
            fill_ts = pd.Timestamp(ts)
            break
    if fill_ts is None:
        return None

    entry = limit_px
    path = rth_1m[rth_1m.index >= fill_ts]
    intraday = path[path.index.map(lambda tt: tt.time() < EOD_CUTOFF)]
    exit_ts = fill_ts
    last_px = entry
    outcome = ''

    for ts, bar in intraday.iterrows():
        h, l = float(bar['high']), float(bar['low'])
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

    res = outcome
    if not outcome:
        sess = path[path.index.map(lambda ti: ti.time() < RTH_HI)]
        if sess.empty:
            return None
        eod = float(sess.iloc[-1]['close'])
        exit_ts = pd.Timestamp(sess.index[-1])
        last_px = eod
        ok = eod > entry
        res = 'EOD-Win' if ok else 'EOD-Loss'

    pl_pts = last_px - entry
    gross_usd = round(pl_pts * MULT * CONTRACTS, 2)
    net_usd = round(gross_usd - FEE_RT * CONTRACTS, 2)

    return {
        'session_day': session_day,
        'Symbol': symbol,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'Trade_Direction': 'Long',
        'Signal_5m_Left': sig_left.isoformat(),
        'Entry_Time': fill_ts.isoformat(),
        'Exit_Time': exit_ts.isoformat(),
        'Entry_Price': round(entry, 4),
        'Exit_Price': round(last_px, 4),
        'Stop_Price': round(stop, 4),
        'TP_Price': round(target, 4),
        'Trade_PL': round(pl_pts, 6),
        'Net_$': net_usd,
        'Result': res,
    }


def max_dd_cumulative(net_series: pd.Series) -> float:
    cum = net_series.cumsum()
    return float((cum - cum.cummax()).min())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--stops-csv', type=Path, default=DEFAULT_STOPS)
    ap.add_argument('--1m', dest='m1', type=Path, default=DEFAULT_M1)
    ap.add_argument('--include-hemisphere', action='store_true')
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.daily_dbn.is_file():
        print(f'Missing DBN: {args.daily_dbn}', file=sys.stderr)
        return 1
    if not args.stops_csv.is_file():
        print(f'Missing stops: {args.stops_csv}', file=sys.stderr)
        return 1
    if not args.m1.is_file():
        print(f'Missing 1m: {args.m1}', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)
    monthly = monthly_high_low(daily)
    pm_h_ser, pm_l_ser = prior_month_levels_series(daily, monthly)

    legs = qualify_v2b_m_legs(
        args.stops_csv,
        daily,
        pm_h_ser,
        pm_l_ser,
        include_hemisphere=args.include_hemisphere,
    )
    if legs.empty:
        print('No v2b_m-qualified sessions.', file=sys.stderr)
        return 1

    need_dates = set(pd.to_datetime(legs['Date']).dt.date.unique())
    tmin, tmax = min(need_dates), max(need_dates)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    rows: list[dict] = []
    for _, q in legs.sort_values('Date').iterrows():
        d = pd.Timestamp(q['Date']).date()
        sym = str(q.get('Symbol', '') or '')
        rh = float(q['Range_High'])
        rl = float(q['Range_Low'])
        rv = float(q['Range'])

        day_raw = gby.get(d)
        if day_raw is None or day_raw.empty:
            continue
        rth = rth_slice(day_raw, d)
        if rth.empty:
            continue

        sim = simulate_long_limit_at_rh(rth, d, rh, rl, rv, symbol=sym)
        if sim is None:
            continue

        row = {
            'Date': d.isoformat(),
            'Day_of_Week': pd.Timestamp(d).strftime('%A'),
            'Symbol': sim['Symbol'],
            'Range_High': sim['Range_High'],
            'Range_Low': sim['Range_Low'],
            'Range': sim['Range'],
            'Trade_Direction': sim['Trade_Direction'],
            'Entry_Price': sim['Entry_Price'],
            'Exit_Price': sim['Exit_Price'],
            'Trade_PL': sim['Trade_PL'],
            'Net_$': sim['Net_$'],
            'Result': sim['Result'],
            'bias_bucket': q['bias_bucket'],
            'geom_tag': q['geom_tag'],
            'pm_high': float(q['pm_high']),
            'pm_low': float(q['pm_low']),
            'EPS_IDX_PT': EPS_IDX_PT,
            'Signal_5m_Left': sim['Signal_5m_Left'],
            'Entry_Time': sim['Entry_Time'],
            'Exit_Time': sim['Exit_Time'],
            'Stop_Price': sim['Stop_Price'],
            'TP_Price': sim['TP_Price'],
            'tp_hit_style': tp_hit(sim['Result']),
        }
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        print('No simulated fills (limit never touched after signal).', file=sys.stderr)
        return 1

    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    n = len(out)
    tp_style = out['tp_hit_style'].sum()
    wr_tp = tp_style / n * 100
    wr_net = (out['Net_$'] > 0).mean() * 100
    sum_net = float(out['Net_$'].sum())
    dd = max_dd_cumulative(out['Net_$'])
    by_day = out.groupby('Date')['Net_$'].sum().sort_index()
    cum_d = by_day.cumsum()
    dd_daily = float((cum_d - cum_d.cummax()).min())

    bias_note = '+ hemisphere_long' if args.include_hemisphere else 'bullish_break only'
    print(f'v2b_m limit @ RH retest  |  filter: long-only v2b_m ({bias_note})  |  EPS={EPS_IDX_PT}')
    print(f'Qualified v2b_m sessions: {len(legs)}  |  Limit fills after signal: {n}')
    print()
    print(f'TP-style WR (Win|EOD-Win): {wr_tp:.2f}%  ({int(tp_style)} / {n})')
    print(f'Net_$ > 0 WR:              {wr_net:.2f}%')
    print(f'Sum Net_$:                 ${sum_net:,.2f}')
    print(f'Max DD (leg cumulative):   ${dd:,.2f}')
    print(f'Max DD (daily Net sum):    ${dd_daily:,.2f}')
    print(f'\nWrote {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
