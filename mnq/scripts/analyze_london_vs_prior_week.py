#!/usr/bin/env python3
"""
Compare **02:00–09:30 London** H/L to **prior calendar week** (Mon–Fri) H/L
from MNQ **daily** bars, and measure **RTH** (9:30–16:00) full rejections
of those weekly levels with bounded overshoot.

**Prior week** for session date *d* = Mon–Fri of the week *before* the week
containing *d* (trading days present in the daily file only).

**Coincide** (configurable, index pts): |LdnH − PWH| ≤ c and/or |LdnL − PWL| ≤ c.

**RTH rejection** (asymmetric by level; configurable):

  - *PWH* (resistance): session tags the zone (high ≥ PWH − touch) without
    spiking more than *max_viol* above PWH (high ≤ PWH + *max_viol*), and the
    session then trades *fade_min* index points *below* PWH (low ≤ PWH − fade).
  - *PWL* (support): low ≤ PWL + touch, low ≥ PWL − *max_viol*, high ≥ PWL + *fade*.

Defaults: *touch* 5, *max_viol* 20, *fade* 25 (MNQ index points).

Inputs (override with env or flags):

  - Daily: ``mnq/raw/glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst`` (latest drop)
  - 1m: ``mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst``
"""
from __future__ import annotations

import argparse
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import databento as db
import numpy as np
import pandas as pd
import pytz

POTIONS_MNQ = Path(__file__).resolve().parent.parent
RAW = POTIONS_MNQ / 'raw'

NY = pytz.timezone('America/New_York')
LDN_LO = time(2, 0)
LDN_HI = time(9, 30)
RTH_O = time(9, 30)
RTH_C = time(16, 0)
SYMBOL_PREFIX = 'MNQ'


def _load_mnq_front_daily(dbn: Path) -> pd.DataFrame:
    store = db.DBNStore.from_file(str(dbn))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(SYMBOL_PREFIX)].copy()
    df['d'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('d')['volume'].idxmax()]
    out = fm.set_index('d').sort_index()
    return out[['open', 'high', 'low', 'close', 'volume', 'symbol']].copy()


def _week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _prior_week_range(session_day: date) -> Tuple[date, date]:
    """Mon–Fri of the *previous* week relative to the week of *session_day*."""
    this_mon = _week_start_monday(session_day)
    prev_mon = this_mon - timedelta(days=7)
    return prev_mon, prev_mon + timedelta(days=4)


def _prior_week_pwh_pwl(
    daily: pd.DataFrame, session_day: date
) -> Tuple[Optional[float], Optional[float]]:
    lo, hi = _prior_week_range(session_day)
    wk = [lo + timedelta(days=i) for i in range(5)]
    sub = daily.reindex(wk)
    if sub['high'].isna().all():
        return None, None
    pwh = float(sub['high'].max())
    pwl = float(sub['low'].min())
    if np.isnan(pwh) or np.isnan(pwl):
        return None, None
    return pwh, pwl


def _load_1m_front_by_date(
    dbn: Path, date_min: date, date_max: date
) -> Dict[date, pd.DataFrame]:
    store = db.DBNStore.from_file(str(dbn))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(SYMBOL_PREFIX)].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['d'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    # front month by day
    vol = (
        df.groupby(['d', 'symbol'])['volume']
        .sum()
        .reset_index()
    )
    pick = vol.loc[vol.groupby('d')['volume'].idxmax()]
    m = {r['d']: r['symbol'] for _, r in pick.iterrows()}
    df = df[df.apply(lambda r: m.get(r['d']) == r['symbol'], axis=1)]
    df = df[(df['d'] >= date_min) & (df['d'] <= date_max)]
    gby: Dict[date, pd.DataFrame] = {}
    for d, g in df.groupby('d', sort=False):
        g2 = g.set_index('ts_event').sort_index()
        gby[d] = g2[['open', 'high', 'low', 'close', 'volume']]
    return gby


def _london_hilo(day: pd.DataFrame) -> Tuple[float, float]:
    b = day[day.index.map(lambda t: LDN_LO <= t.time() < LDN_HI)]
    if b.empty:
        return float('nan'), float('nan')
    return float(b['high'].max()), float(b['low'].min())


def _rth_only(day: pd.DataFrame) -> pd.DataFrame:
    return day[day.index.map(lambda t: RTH_O <= t.time() < RTH_C)]


def _rth_reject_pwh(
    rth: pd.DataFrame,
    pwh: float,
    *,
    touch: float,
    max_viol: float,
    fade: float,
) -> bool:
    if rth.empty or not np.isfinite(pwh):
        return False
    h = float(rth['high'].max())
    l_ = float(rth['low'].min())
    if h < pwh - touch:
        return False
    if h > pwh + max_viol:
        return False
    if l_ > pwh - fade:
        return False
    return True


def _rth_reject_pwl(
    rth: pd.DataFrame,
    pwl: float,
    *,
    touch: float,
    max_viol: float,
    fade: float,
) -> bool:
    if rth.empty or not np.isfinite(pwl):
        return False
    h = float(rth['high'].max())
    l_ = float(rth['low'].min())
    if l_ > pwl + touch:
        return False
    if l_ < pwl - max_viol:
        return False
    if h < pwl + fade:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description='London vs prior-week H/L; RTH rejections of PWH/PWL (bounded overshoot).'
    )
    ap.add_argument(
        '--daily-dbn',
        type=Path,
        default=RAW / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst',
        help='MNQ ohlcv-1d dbn',
    )
    ap.add_argument(
        '--m1-dbn',
        type=Path,
        default=RAW / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
        help='MNQ ohlcv-1m dbn (for London + RTH intraday)',
    )
    ap.add_argument(
        '--coincide-pts',
        type=float,
        default=8.0,
        help='|LdnH−PWH| or |LdnL−PWL| within this = coincide (index pts).',
    )
    ap.add_argument('--touch-pts', type=float, default=5.0, help='RTH tag of weekly level')
    ap.add_argument(
        '--max-viol-pts', type=float, default=20.0, help='max overshoot through PWH/PWL'
    )
    ap.add_argument(
        '--fade-pts', type=float, default=25.0, help='min favorable fade past level (idx pts)'
    )
    ap.add_argument(
        '--out',
        type=Path,
        default=POTIONS_MNQ / 'data' / 'london_vs_prior_week_daily.csv',
        help='per-day flags CSV (optional).',
    )
    args = ap.parse_args()

    print(f'Load daily: {args.daily_dbn} ...', flush=True)
    daily = _load_mnq_front_daily(args.daily_dbn)
    d0, d1 = daily.index.min(), daily.index.max()
    print(f'  {len(daily):,} days  {d0} → {d1}')

    print(f'Load 1m: {args.m1_dbn} ...', flush=True)
    by1 = _load_1m_front_by_date(args.m1_dbn, d0, d1)
    # overlap with 1m availability
    m1_d0, m1_d1 = min(by1), max(by1)
    overlap_lo = max(d0, m1_d0)
    overlap_hi = min(d1, m1_d1)
    print(f'  1m sessions: {len(by1):,}  {m1_d0} → {m1_d1}   overlap with daily: {overlap_lo} → {overlap_hi}')

    days = sorted(
        d for d in by1
        if overlap_lo <= d <= overlap_hi and d in daily.index
    )
    c = float(args.coincide_pts)
    touch = float(args.touch_pts)
    mx = float(args.max_viol_pts)
    fade = float(args.fade_pts)

    n = len(days)
    n_prior = 0
    h_coin = l_coin = both_coin = 0
    pwh_rej = pwl_rej = 0
    pwh_tag = pwl_tag = 0
    rows: list[dict] = []

    for d in days:
        pwh, pwl = _prior_week_pwh_pwl(daily, d)
        if pwh is None or pwl is None:
            rows.append(
                {
                    'date': d,
                    'pwh': np.nan,
                    'pwl': np.nan,
                    'ldn_h': np.nan,
                    'ldn_l': np.nan,
                    'h_near_pwh': False,
                    'l_near_pwl': False,
                    'rth_tag_pwh': False,
                    'rth_tag_pwl': False,
                    'rth_pwh_reject': False,
                    'rth_pwl_reject': False,
                }
            )
            continue
        n_prior += 1
        day1 = by1[d]
        lh, ll = _london_hilo(day1)
        rth = _rth_only(day1)
        h_hit = bool(np.isfinite(lh) and abs(lh - pwh) <= c)
        l_hit = bool(np.isfinite(ll) and abs(ll - pwl) <= c)
        if h_hit:
            h_coin += 1
        if l_hit:
            l_coin += 1
        if h_hit and l_hit:
            both_coin += 1

        tag_pwh = not rth.empty and float(rth['high'].max()) >= pwh - touch
        tag_pwl = not rth.empty and float(rth['low'].min()) <= pwl + touch
        if tag_pwh:
            pwh_tag += 1
        if tag_pwl:
            pwl_tag += 1

        rq = _rth_reject_pwh(rth, pwh, touch=touch, max_viol=mx, fade=fade)
        rf = _rth_reject_pwl(rth, pwl, touch=touch, max_viol=mx, fade=fade)
        if rq:
            pwh_rej += 1
        if rf:
            pwl_rej += 1

        rows.append(
            {
                'date': d,
                'pwh': pwh,
                'pwl': pwl,
                'ldn_h': lh,
                'ldn_l': ll,
                'h_near_pwh': h_hit,
                'l_near_pwl': l_hit,
                'rth_tag_pwh': tag_pwh,
                'rth_tag_pwl': tag_pwl,
                'rth_pwh_reject': rq,
                'rth_pwl_reject': rf,
            }
        )

    def pct(a: int, b: int) -> str:
        return f'{100.0 * a / b:.1f}%' if b else 'n/a'

    print()
    print('--- London (02:00–09:30) vs prior Mon–Fri week (daily) ---')
    print(
        f"  'Close enough' = within ±{c:g} index pts; days with both Ldn and prior week: {n_prior:,} / {n:,}"
    )
    print(f'  |LdnH − PWH| ≤ {c:g}:  {h_coin:,}  ({pct(h_coin, n_prior)})')
    print(f'  |LdnL − PWL| ≤ {c:g}:  {l_coin:,}  ({pct(l_coin, n_prior)})')
    print(f'  both same day:  {both_coin:,}  ({pct(both_coin, n_prior)})')

    print()
    print(
        f'--- RTH 9:30–16:00: full reversals (touch ≤{touch:g}, viol ≤{mx:g}, fade ≥{fade:g} pts) ---'
    )
    print(f'  tag PWH (session high ≥ PWH−{touch:g}):  {pwh_tag:,}  ({pct(pwh_tag, n_prior)})')
    print(f'  tag PWL (session low  ≤ PWL+{touch:g}):  {pwl_tag:,}  ({pct(pwl_tag, n_prior)})')
    print(
        f'  PWH "full" rejection (session: tag zone, high ≤ PWH+{mx:g}, low ≤ PWH−{fade:g}):  '
        f'{pwh_rej:,}  ({pct(pwh_rej, n_prior)} of all days with PWH/PWL)'
    )
    print(
        f'  PWL "full" rejection (session: tag zone, low ≥ PWL−{mx:g}, high ≥ PWL+{fade:g}):  '
        f'{pwl_rej:,}  ({pct(pwl_rej, n_prior)} of all days with PWH/PWL)'
    )
    # rq/rf are only true when the session also tags the level; conditional = pwh_rej / pwh_tag
    print(
        f'  → conditional on *tag* PWH:  {pwh_rej:,} / {pwh_tag:,}  =  '
        f'{pct(pwh_rej, pwh_tag)}  (reversals of tagged sessions)'
    )
    print(
        f'  → conditional on *tag* PWL:  {pwl_rej:,} / {pwl_tag:,}  =  '
        f'{pct(pwl_rej, pwl_tag)}  (reversals of tagged sessions)'
    )

    df = pd.DataFrame(rows)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
        print()
        print(f'Wrote {args.out}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
