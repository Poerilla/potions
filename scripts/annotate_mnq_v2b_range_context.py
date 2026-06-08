#!/usr/bin/env python3
"""
Add analysis columns to MNQ v2b ORB (15m range) without changing strategy P/L.

Uses 1m OHLCV (same schema as Databento OHLCV export):
  - FVG: 3-candle 5m ICT-style imbalance, scanned 2:00–9:45 ET (aligned with
    trade: bull FVG for Long, bear for Short).
  - "Opposing end" of 15m range (RL for Long, RH for short) vs:
    prior RTH 9:30–16:00 H/L, London 2:00–11:00 H/L, week-to-date RTH H/L
    (Mon 9:30 through prior session 16:00; Mon first week: prior Fri ref).
  - London *adversity* vs a fixed London *morning* box (2:00–5:00 ET, NOT 2–11):
    ORB can print below/above that H/L. Metrics use 1m ORB 9:30–9:45 vs
    Ldn_2_5 = min/max 2:00–5:00. (Sweep flags still use 2:00–11:00 for ctx.)

Input CSV (default): mnq/mnq_orb_results_stops.csv
1m data (default):  mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv

Output: mnq/mnq_orb_results_stops_annotated.csv
"""
import argparse
from datetime import time, timedelta

import numpy as np
import pandas as pd
import pytz

NY = pytz.timezone('America/New_York')
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
ORB_END = time(9, 45)          # 15m ORB 9:30-9:45
LDN_LO = time(2, 0)            # London H/L (wide, matches sweep/ctx)
LDN_HI = time(11, 0)
LDN_MORN_LO = time(2, 0)       # “London morning” for pierce (fixed box; ORB is outside)
LDN_MORN_HI = time(5, 0)       # [2, 5) ET
FVG_SCAN_LO = time(2, 0)        # 5m FVG scan
FVG_SCAN_HI = time(9, 45)      # through ORB end
TICK = 0.25


def load_1m_for_dates(path, date_min, date_max, needed_dates: set):
    """
    Read 1m CSV in chunks, keep only calendar dates in `needed_dates` (trade days),
    then MNQ outrights (no spread symbols). Cuts I/O to relevant rows.
    """
    usecols = ['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol']
    f32 = {'open': 'float32', 'high': 'float32', 'low': 'float32', 'close': 'float32'}
    print(f'Loading 1m {path} (chunked, {len(needed_dates)} target days) ...', flush=True)
    parts = []
    n = 0
    for ch in pd.read_csv(
        path,
        usecols=usecols,
        chunksize=400_000,
        dtype={**f32, 'volume': 'int32', 'symbol': 'string'},
        engine='c',
    ):
        ch['ts_event'] = pd.to_datetime(ch['ts_event'], utc=True).dt.tz_convert(NY)
        d = ch['ts_event'].dt.date
        ch = ch[(d >= date_min) & (d <= date_max) & (d.isin(needed_dates))]
        if ch.empty:
            continue
        ch = ch[ch['symbol'].str.startswith('MNQ', na=False)]
        ch = ch[~ch['symbol'].str.contains('-', na=False)]
        if ch.empty:
            continue
        parts.append(ch)
        n += len(ch)
    if not parts:
        raise SystemExit('No 1m rows in date/symbol range (check symbol filter vs file)')
    df = pd.concat(parts, ignore_index=True, copy=False)
    print(f'  {n:,} MNQ 1m bars after date+symbol filter', flush=True)
    return df


def pick_front_month_day(df1):
    """Per calendar date, keep rows for highest-volume ~continuous symbol (ESH2 etc)."""
    df1['d'] = df1['ts_event'].dt.date
    sym_vol = (
        df1.groupby(['d', 'symbol'])['volume']
        .sum()
        .reset_index()
        .sort_values(['d', 'volume'], ascending=[True, False])
        .groupby('d')
        .first()
        .reset_index()[['d', 'symbol']]
    )
    m = df1.merge(sym_vol, on=['d', 'symbol'], how='inner')
    return m.drop(columns=['d'])


def prev_business_day(d: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(d).normalize()
    for _ in range(10):
        t = t - timedelta(days=1)
        if t.weekday() < 5:
            return t
    return t


def in_rth(ts) -> bool:
    t = ts.time() if isinstance(ts, pd.Timestamp) else ts
    return RTH_OPEN <= t < RTH_CLOSE


def rth_pdh_pdl_from_day_b(day_b: pd.DataFrame):
    """Full RTH 9:30-16:00 for one calendar day's 1m rows."""
    b = day_b[day_b.index.map(in_rth)]
    if b.empty:
        return np.nan, np.nan
    return float(b['high'].max()), float(b['low'].min())


def london_hi_lo_from_day_b(day_b: pd.DataFrame):
    b = day_b[day_b.index.map(lambda x: LDN_LO <= x.time() < LDN_HI)]
    if b.empty:
        return np.nan, np.nan
    return float(b['high'].max()), float(b['low'].min())


def london_morning_2_5_from_day_b(day_b: pd.DataFrame):
    """Min/max 1m 02:00–05:00 ET; ORB 9:30–9:45 is outside this box → pierce can be >0."""
    b = day_b[day_b.index.map(lambda x: LDN_MORN_LO <= x.time() < LDN_MORN_HI)]
    if b.empty:
        return np.nan, np.nan
    return float(b['high'].max()), float(b['low'].min())


def week_rth_hilo_prior_days(gby, d0):
    """
    Mon 9:30–Fri: prior RTH highs/lows from week start through **previous** session
    (not including d0 9:30+). If Monday, use prior week Friday only.
    """
    d0 = pd.Timestamp(d0).date()
    mon = d0 - timedelta(days=pd.Timestamp(d0).weekday())
    days = []
    cur = mon
    while cur < d0:
        if cur.weekday() < 5:
            days.append(cur)
        cur = cur + timedelta(days=1)
    if not days:
        t = d0 - timedelta(days=1)
        while t.weekday() >= 5:
            t = t - timedelta(days=1)
        days = [t]
    hs, ls = [], []
    for day in days:
        b = gby.get(day)
        if b is None or b.empty:
            continue
        b = b[b.index.map(in_rth)]
        if b.empty:
            continue
        hs.append(b['high'].max())
        ls.append(b['low'].min())
    if not hs:
        return np.nan, np.nan
    return float(max(hs)), float(min(ls))


def fvg_5m_flags(oh5: pd.DataFrame) -> tuple:
    """
    5m OHLC; ICT 3-candle FVG: bull if low[2] > high[0], bear if high[2] < low[0]
    for consecutive rows. Scans all triplets in window.
    """
    o = oh5[['open', 'high', 'low', 'close']].values
    n = len(o)
    bull, bear = False, False
    for i in range(n - 2):
        a, c = o[i], o[i + 2]
        if c[2] > a[1]:  # low_c > high_a
            bull = True
        if c[1] < a[2]:  # high_c < low_a
            bear = True
        if bull and bear:
            break
    return bull, bear


def orb_range(orb_bars) -> tuple:
    if orb_bars.empty:
        return np.nan, np.nan
    return float(orb_bars['high'].max()), float(orb_bars['low'].min())


def group_by_trading_date(bars_ny: pd.DataFrame) -> dict:
    """O(n) single groupby: date -> 1m bars for that NY session day."""
    key = pd.Series(bars_ny.index.date, index=bars_ny.index, dtype=object)
    return dict(tuple(bars_ny.groupby(key, sort=False)))


def add_features_to_trades(trades: pd.DataFrame, bars_ny: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    trades['Date'] = pd.to_datetime(trades['Date']).dt.date
    udays = sorted(trades['Date'].unique())
    print('  groupby trading date (one pass) ...', flush=True)
    gby = group_by_trading_date(bars_ny)
    # Precompute per trade day only
    cache = {}
    for d in udays:
        day_b = gby.get(d)
        if day_b is None or day_b.empty:
            cache[d] = None
            continue
        orb = day_b[day_b.index.map(lambda x: RTH_OPEN <= x.time() < ORB_END)]
        rh, rl = orb_range(orb)
        prev = prev_business_day(pd.Timestamp(d)).date()
        pday = gby.get(prev)
        if pday is None or pday.empty:
            pdh, pdl = np.nan, np.nan
        else:
            pdh, pdl = rth_pdh_pdl_from_day_b(pday)
        ldn_h, ldn_l = london_hi_lo_from_day_b(day_b)
        wk_h, wk_l = week_rth_hilo_prior_days(gby, d)
        morn_h, morn_l = london_morning_2_5_from_day_b(day_b)
        # 5m in FVG window 02:00–09:45 ET
        w = day_b[day_b.index.map(lambda x: FVG_SCAN_LO <= x.time() <= FVG_SCAN_HI)]
        win5 = w.resample('5min', label='left', closed='right').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna(how='any')
        fvg_bull, fvg_bear = fvg_5m_flags(win5) if len(win5) >= 3 else (False, False)
        cache[d] = {
            'range_high_csv': rh,
            'range_low_csv': rl,
            'PDH': pdh,
            'PDL': pdl,
            'London_H': ldn_h,
            'London_L': ldn_l,
            'London_2_5_H': morn_h,
            'London_2_5_L': morn_l,
            'Week_H_prior': wk_h,
            'Week_L_prior': wk_l,
            'FVG_5m_bull_in_window': fvg_bull,
            'FVG_5m_bear_in_window': fvg_bear,
        }

    rows = []
    for _, r in trades.iterrows():
        d = r['Date']
        c = cache.get(d)
        if c is None:
            row = {**r.to_dict(), **{k: np.nan for k in [
                'FVG_5m_bull_in_window', 'FVG_5m_bear_in_window', 'FVG_5m_with_trade',
                'Opp_sweep_PDH', 'Opp_sweep_PDL', 'Opp_sweep_London_H', 'Opp_sweep_London_L',
                'Opp_sweep_WeekH', 'Opp_sweep_WeekL', 'ctx_PDH', 'ctx_PDL', 'ctx_London_H',
                'ctx_London_L',                 'ctx_Week_H', 'ctx_Week_L', 'Ldn_2_5_pierce_pts',
                'ctx_London_2_5_L', 'ctx_London_2_5_H',
            ]}}
            rows.append(row)
            continue
        dr = r['Trade_Direction']
        rh, rl = float(r['Range_High']), float(r['Range_Low'])
        orh, orl = c['range_high_csv'], c['range_low_csv']  # 1m 9:30–9:45 (same as CSV typical)
        l2_5h, l2_5l = c['London_2_5_H'], c['London_2_5_L']
        if dr == 'Long':
            fvg_ok = c['FVG_5m_bull_in_window']
            opp_sweep_pdh, opp_sweep_pdl = np.nan, _ge(rl, c['PDL'])
            opp_sweep_ldn_h, opp_sweep_ldn_l = np.nan, _ge(rl, c['London_L'])
            opp_sweep_wk_h, opp_sweep_wk_l = np.nan, _ge(rl, c['Week_L_prior'])
            if pd.isna(l2_5l) or pd.isna(orl):
                p2_5 = np.nan
            else:
                p2_5 = max(0.0, float(l2_5l) - float(orl))  # ORB low below 2–5 a.m. L
        else:
            fvg_ok = c['FVG_5m_bear_in_window']
            opp_sweep_pdh, opp_sweep_pdl = _le(rh, c['PDH']), np.nan
            opp_sweep_ldn_h, opp_sweep_ldn_l = _le(rh, c['London_H']), np.nan
            opp_sweep_wk_h, opp_sweep_wk_l = _le(rh, c['Week_H_prior']), np.nan
            if pd.isna(l2_5h) or pd.isna(orh):
                p2_5 = np.nan
            else:
                p2_5 = max(0.0, float(orh) - float(l2_5h))  # ORB high above 2–5 a.m. H
        row = {
            **r.to_dict(),
            'FVG_5m_bull_in_window': int(bool(c['FVG_5m_bull_in_window'])),
            'FVG_5m_bear_in_window': int(bool(c['FVG_5m_bear_in_window'])),
            'FVG_5m_with_trade': int(bool(fvg_ok)),
            'Opp_sweep_PDH': opp_sweep_pdh,
            'Opp_sweep_PDL': opp_sweep_pdl,
            'Opp_sweep_London_H': opp_sweep_ldn_h,
            'Opp_sweep_London_L': opp_sweep_ldn_l,
            'Opp_sweep_WeekH': opp_sweep_wk_h,
            'Opp_sweep_WeekL': opp_sweep_wk_l,
            'ctx_PDH': c['PDH'],
            'ctx_PDL': c['PDL'],
            'ctx_London_H': c['London_H'],
            'ctx_London_L': c['London_L'],
            'ctx_Week_H': c['Week_H_prior'],
            'ctx_Week_L': c['Week_L_prior'],
            'ctx_London_2_5_L': c['London_2_5_L'],
            'ctx_London_2_5_H': c['London_2_5_H'],
            'Ldn_2_5_pierce_pts': p2_5,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _le(a, b):
    if pd.isna(b) or pd.isna(a):
        return np.nan
    return int(a + TICK * 0.1 >= b)  # RH took out / pierced level above


def _ge(a, b):
    if pd.isna(b) or pd.isna(a):
        return np.nan
    return int(a - TICK * 0.1 <= b)  # RL at/below support


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v2b', default='/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv')
    ap.add_argument('--1m', dest='m1', default='/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--out', default='/home/tester/hsm/potions/mnq/mnq_orb_results_stops_annotated.csv')
    args = ap.parse_args()

    trades = pd.read_csv(args.v2b)
    tmin, tmax = pd.to_datetime(trades['Date']).dt.date.min(), pd.to_datetime(trades['Date']).dt.date.max()
    trade_dates = set(pd.to_datetime(trades['Date']).dt.date.unique())
    need = set(trade_dates)
    for d in trade_dates:
        need.add(prev_business_day(pd.Timestamp(d)).date())
        d0 = pd.Timestamp(d).date()
        mon = d0 - timedelta(days=pd.Timestamp(d0).weekday())
        cur = mon
        while cur < d0:
            if cur.weekday() < 5:
                need.add(cur)
            cur = cur + timedelta(days=1)
    print(
        f'v2b trades: {len(trades)}  RTH day span {tmin} .. {tmax}  ({len(need)} cal days 1m load incl. refs)',
        flush=True,
    )

    raw = load_1m_for_dates(args.m1, tmin, tmax, need)
    raw = pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    out_df = add_features_to_trades(trades, raw)
    out_df.to_csv(args.out, index=False)
    print(f'Wrote {args.out}  ({len(out_df)} rows)')

    # quick sanity
    if 'FVG_5m_with_trade' in out_df.columns:
        print('FVG_5m_with_trade share:', out_df['FVG_5m_with_trade'].mean() * 100, '%')
        print('(Long) Opp_sweep_PDL mean (non-nan):', out_df[out_df['Trade_Direction'] == 'Long']['Opp_sweep_PDL'].dropna().mean())


if __name__ == '__main__':
    main()
