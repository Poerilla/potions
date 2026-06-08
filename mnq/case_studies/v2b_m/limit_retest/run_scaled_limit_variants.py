#!/usr/bin/env python3
"""
Scaled-limit variants on the **v2b_m limit-retest** signal (same filter + 5 m breakout cue).

**A — Two 1-lot limits:** after signal, bid **RH − 30%·Range** then **RH − 70%·Range** (deeper = lower price).
Each fills once if touched; **1 MNQ per fill**. **Stop:** flat **all** at **RL**. **TP:** flat **all** at **RH + Range**.
Intraday **stop-before-target** on ambiguous bars; else **EOD** flatten at last RTH close (15:59 bar).

**B — Single fill:** limit **RH** (boundary retest). **Stop** at **RH − 30%·Range** (not RL). **TP** **RH + Range**.

Fees: **\$1.50** round-trip **per filled contract** (same convention as ``run_limit_retest.py``).
"""
from __future__ import annotations

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
ORB_HI = time(9, 45)
EOD_CUTOFF = time(15, 55)

TICK = 0.25
MULT = 2.0
FEE_RT = 1.50


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


def signal_first_working(rth_1m: pd.DataFrame, session_day: date, rh: float) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return (sig_left, first_working_ts) or (None, None)."""
    bars5 = resample_5m_rth(rth_1m, session_day)
    if bars5.empty:
        return None, None
    or_end = NY.localize(datetime.combine(session_day, ORB_HI))
    sig_left = first_long_break_close_5m(bars5[bars5.index >= or_end], rh)
    if sig_left is None:
        return None, None
    first_working = sig_left + pd.Timedelta(minutes=5)
    return sig_left, first_working


def max_dd_cumulative(net_series: pd.Series) -> float:
    cum = net_series.cumsum()
    return float((cum - cum.cummax()).min())


def simulate_dual_30_70_rl_stop(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
    *,
    symbol: str,
) -> dict | None:
    if rv <= 1e-12:
        return None
    sig_left, first_working = signal_first_working(rth_1m, session_day, rh)
    if first_working is None:
        return None

    L1 = rh - 0.30 * rv
    L2 = rh - 0.70 * rv
    target = rh + rv
    stop_sl = rl

    fwd = rth_1m[rth_1m.index >= first_working]
    fwd = fwd.sort_index()

    filled1 = filled2 = False
    entries: list[float] = []
    fill_ts_first: pd.Timestamp | None = None

    for ts, bar in fwd.iterrows():
        h = float(bar['high'])
        l = float(bar['low'])

        if not filled1 and l <= L1 + 1e-9:
            filled1 = True
            entries.append(L1)
            if fill_ts_first is None:
                fill_ts_first = pd.Timestamp(ts)
        if not filled2 and l <= L2 + 1e-9:
            filled2 = True
            entries.append(L2)
            if fill_ts_first is None:
                fill_ts_first = pd.Timestamp(ts)

        if not entries:
            continue

        qty = len(entries)
        if l <= stop_sl + 1e-12:
            exit_px = stop_sl
            exit_ts = pd.Timestamp(ts)
            gross_pts = sum(exit_px - e for e in entries)
            net_usd = round(gross_pts * MULT - FEE_RT * qty, 2)
            return _pack_row(
                session_day,
                symbol,
                rh,
                rl,
                rv,
                sig_left,
                fill_ts_first,
                exit_ts,
                entries,
                exit_px,
                gross_pts,
                net_usd,
                'Loss',
                stop_sl,
                target,
                qty,
            )

        if h >= target - 1e-12:
            exit_px = target
            exit_ts = pd.Timestamp(ts)
            gross_pts = sum(exit_px - e for e in entries)
            net_usd = round(gross_pts * MULT - FEE_RT * qty, 2)
            return _pack_row(
                session_day,
                symbol,
                rh,
                rl,
                rv,
                sig_left,
                fill_ts_first,
                exit_ts,
                entries,
                exit_px,
                gross_pts,
                net_usd,
                'Win',
                stop_sl,
                target,
                qty,
            )

    if not entries:
        return None

    qty = len(entries)
    path_eod = rth_1m[rth_1m.index >= fill_ts_first]
    sess = path_eod[path_eod.index.map(lambda ti: ti.time() < RTH_HI)]
    if sess.empty:
        return None
    eod = float(sess.iloc[-1]['close'])
    exit_ts = pd.Timestamp(sess.index[-1])
    gross_pts = sum(eod - e for e in entries)
    avg_e = sum(entries) / qty
    ok = eod > avg_e
    res = 'EOD-Win' if ok else 'EOD-Loss'
    net_usd = round(gross_pts * MULT - FEE_RT * qty, 2)
    return _pack_row(
        session_day,
        symbol,
        rh,
        rl,
        rv,
        sig_left,
        fill_ts_first,
        exit_ts,
        entries,
        eod,
        gross_pts,
        net_usd,
        res,
        stop_sl,
        target,
        qty,
    )


def _pack_row(
    session_day,
    symbol,
    rh,
    rl,
    rv,
    sig_left,
    fill_ts_first,
    exit_ts,
    entries,
    exit_px,
    gross_pts,
    net_usd,
    res,
    stop_px,
    tp_px,
    qty,
):
    avg_e = sum(entries) / qty
    return {
        'session_day': session_day,
        'Symbol': symbol,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'n_contracts': qty,
        'entries': '+'.join(f'{e:.2f}' for e in entries),
        'avg_entry': round(avg_e, 4),
        'Signal_5m_Left': sig_left.isoformat() if sig_left is not None else '',
        'First_Fill_Time': fill_ts_first.isoformat() if fill_ts_first is not None else '',
        'Exit_Time': exit_ts.isoformat(),
        'Exit_Price': round(exit_px, 4),
        'Stop_Price': round(stop_px, 4),
        'TP_Price': round(tp_px, 4),
        'Trade_PL_pts_total': round(gross_pts, 6),
        'Net_$': net_usd,
        'Result': res,
    }


def simulate_single_rh_stop30(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
    *,
    symbol: str,
) -> dict | None:
    if rv <= 1e-12:
        return None
    sig_left, first_working = signal_first_working(rth_1m, session_day, rh)
    if first_working is None:
        return None

    limit_px = rh
    stop_sl = rh - 0.30 * rv
    target = rh + rv

    fwd = rth_1m[rth_1m.index >= first_working]
    fwd = fwd[fwd.index.map(lambda t: t.time() <= EOD_CUTOFF)]
    fill_ts = None
    for ts, bar in fwd.iterrows():
        if float(bar['low']) <= limit_px + 1e-9:
            fill_ts = pd.Timestamp(ts)
            break
    if fill_ts is None:
        return None

    entry = limit_px
    path = rth_1m[rth_1m.index >= fill_ts]
    intraday = path[path.index.map(lambda tt: tt.time() < EOD_CUTOFF)]

    for ts, bar in intraday.iterrows():
        h, l = float(bar['high']), float(bar['low'])
        if l <= stop_sl + 1e-12:
            exit_px = stop_sl
            pl = exit_px - entry
            net_usd = round(pl * MULT - FEE_RT, 2)
            return {
                'session_day': session_day,
                'Symbol': symbol,
                'Range_High': rh,
                'Range_Low': rl,
                'Range': rv,
                'n_contracts': 1,
                'entries': f'{entry:.2f}',
                'avg_entry': entry,
                'Signal_5m_Left': sig_left.isoformat() if sig_left else '',
                'First_Fill_Time': fill_ts.isoformat(),
                'Exit_Time': ts.isoformat(),
                'Exit_Price': round(exit_px, 4),
                'Stop_Price': round(stop_sl, 4),
                'TP_Price': round(target, 4),
                'Trade_PL_pts_total': round(pl, 6),
                'Net_$': net_usd,
                'Result': 'Loss',
            }
        if h >= target - 1e-12:
            exit_px = target
            pl = exit_px - entry
            net_usd = round(pl * MULT - FEE_RT, 2)
            return {
                'session_day': session_day,
                'Symbol': symbol,
                'Range_High': rh,
                'Range_Low': rl,
                'Range': rv,
                'n_contracts': 1,
                'entries': f'{entry:.2f}',
                'avg_entry': entry,
                'Signal_5m_Left': sig_left.isoformat() if sig_left else '',
                'First_Fill_Time': fill_ts.isoformat(),
                'Exit_Time': ts.isoformat(),
                'Exit_Price': round(exit_px, 4),
                'Stop_Price': round(stop_sl, 4),
                'TP_Price': round(target, 4),
                'Trade_PL_pts_total': round(pl, 6),
                'Net_$': net_usd,
                'Result': 'Win',
            }

    sess = path[path.index.map(lambda ti: ti.time() < RTH_HI)]
    if sess.empty:
        return None
    eod = float(sess.iloc[-1]['close'])
    exit_ts = pd.Timestamp(sess.index[-1])
    pl = eod - entry
    net_usd = round(pl * MULT - FEE_RT, 2)
    res = 'EOD-Win' if eod > entry else 'EOD-Loss'
    return {
        'session_day': session_day,
        'Symbol': symbol,
        'Range_High': rh,
        'Range_Low': rl,
        'Range': rv,
        'n_contracts': 1,
        'entries': f'{entry:.2f}',
        'avg_entry': entry,
        'Signal_5m_Left': sig_left.isoformat() if sig_left else '',
        'First_Fill_Time': fill_ts.isoformat(),
        'Exit_Time': exit_ts.isoformat(),
        'Exit_Price': round(eod, 4),
        'Stop_Price': round(stop_sl, 4),
        'TP_Price': round(target, 4),
        'Trade_PL_pts_total': round(pl, 6),
        'Net_$': net_usd,
        'Result': res,
    }


def print_stats(label: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f'\n{label}: no trades')
        return
    n = len(df)
    tp = df['Result'].isin(('Win', 'EOD-Win')).sum()
    wr = tp / n * 100
    wr_net = (df['Net_$'] > 0).mean() * 100
    sn = float(df['Net_$'].sum())
    dd = max_dd_cumulative(df['Net_$'])
    by_day = df.groupby(df['Date'])['Net_$'].sum().sort_index()
    dd_d = float((by_day.cumsum() - by_day.cumsum().cummax()).min())
    avg_q = df['n_contracts'].mean()
    print(f'\n=== {label} ===')
    print(f'Sessions traded: {n}  |  avg contracts/exit: {avg_q:.2f}')
    print(f'TP-style WR (Win|EOD-Win): {wr:.2f}%  ({int(tp)} / {n})')
    print(f'Net_$ > 0 WR:              {wr_net:.2f}%')
    print(f'Sum Net_$:                 ${sn:,.2f}')
    print(f'Max DD (leg cumulative):   ${dd:,.2f}')
    print(f'Max DD (daily Net sum):      ${dd_d:,.2f}')


def main() -> int:
    DEFAULT_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'
    DEFAULT_M1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
    DEFAULT_STOPS = MNQ_ROOT / 'mnq_orb_results_stops.csv'

    daily = load_mnq_front_daily(DEFAULT_DBN)
    daily.index = pd.to_datetime(daily.index)
    monthly = monthly_high_low(daily)
    pm_h_ser, pm_l_ser = prior_month_levels_series(daily, monthly)

    legs = qualify_v2b_m_legs(DEFAULT_STOPS, daily, pm_h_ser, pm_l_ser, include_hemisphere=False)
    if legs.empty:
        print('No qualified legs.', file=sys.stderr)
        return 1

    need_dates = set(pd.to_datetime(legs['Date']).dt.date.unique())
    raw = ann.load_1m_for_dates(str(DEFAULT_M1), min(need_dates), max(need_dates), need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    rows_a: list[dict] = []
    rows_b: list[dict] = []

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

        sa = simulate_dual_30_70_rl_stop(rth, d, rh, rl, rv, symbol=sym)
        if sa:
            rows_a.append({**sa, 'Date': d.isoformat(), 'tp_hit_style': tp_hit(sa['Result'])})

        sb = simulate_single_rh_stop30(rth, d, rh, rl, rv, symbol=sym)
        if sb:
            rows_b.append({**sb, 'Date': d.isoformat(), 'tp_hit_style': tp_hit(sb['Result'])})

    df_a = pd.DataFrame(rows_a)
    df_b = pd.DataFrame(rows_b)

    print(f'v2b_m filter sessions: {len(legs)}')
    print(f'EPS_IDX_PT={EPS_IDX_PT}  |  fee \${FEE_RT}/rt per filled MNQ')

    print_stats(
        'A: limits RH−30%·R & RH−70%·R (1 lot each), SL flat RL, TP RH+R',
        df_a,
    )
    print_stats(
        'B: limit RH, SL RH−30%·R, TP RH+R',
        df_b,
    )

    out_a = LIMIT_HERE / 'v2b_m_scaled_30_70_rl_sl.csv'
    out_b = LIMIT_HERE / 'v2b_m_single_rh_sl30.csv'
    df_a.to_csv(out_a, index=False)
    df_b.to_csv(out_b, index=False)
    print(f'\nWrote {out_a}\nWrote {out_b}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
