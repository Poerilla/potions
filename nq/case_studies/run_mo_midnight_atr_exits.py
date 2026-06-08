#!/usr/bin/env python3
"""Single-pass ATR exit backtest for MO midnight retest."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'mnq' / 'case_studies' / 'midnight_open_hourly_charts'))

from backtest_nq_mo_midnight_retest import build_bias_streaks, build_monthly_mo, load_daily, scan_day_setups  # noqa: E402
from build_midnight_open_hourly_charts import DEFAULT_DBN_NQ, load_1m_by_ny_date, resample_15m_midnight_to_1600  # noqa: E402

ATR_LEN = 14


def build_daily_atr(daily: pd.DataFrame) -> dict[date, float]:
    work = daily.sort_values('date').copy()
    pc = work['close'].shift(1)
    tr = pd.concat([work['high'] - work['low'], (work['high'] - pc).abs(), (work['low'] - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=ATR_LEN, adjust=False, min_periods=ATR_LEN).mean().shift(1)
    return {d: float(v) for d, v in zip(work['date'].dt.date, atr) if pd.notna(v)}


def simulate_exit(bars, side, entry_idx, entry, stop_pts, target_pts):
    stop = entry - stop_pts if side == 'long' else entry + stop_pts
    target = entry + target_pts if side == 'long' else entry - target_pts
    for j in range(entry_idx, len(bars)):
        h, l = float(bars.iloc[j]['high']), float(bars.iloc[j]['low'])
        if side == 'long':
            if l <= stop:
                return -stop_pts, 'stop', j
            if h >= target:
                return target_pts, 'target', j
        else:
            if h >= stop:
                return -stop_pts, 'stop', j
            if l <= target:
                return target_pts, 'target', j
    c = float(bars.iloc[-1]['close'])
    pts = c - entry if side == 'long' else entry - c
    return pts, 'session_close', len(bars) - 1


def streak_day(session, streak_id, tdays):
    start = date.fromisoformat(streak_id.rsplit('_', 1)[0])
    idx = {d: i for i, d in enumerate(tdays)}
    return idx[session] - idx[start] + 1


def streak_rank(session, streak_id, smap):
    month = pd.Timestamp(session).to_period('M')
    seen = []
    for d, (_, sid) in smap.items():
        if pd.Timestamp(d).to_period('M') == month and sid not in seen:
            seen.append((date.fromisoformat(sid.rsplit('_', 1)[0]), sid))
    uniq = [s for _, s in sorted(seen)]
    return uniq.index(streak_id) + 1 if streak_id in uniq else 99


def simulate_day(bars15, side, mc, stop_pts, target_pts, max_trades=2):
    setups = scan_day_setups(bars15, side, mc)
    trades = []
    si = 0
    while len(trades) < max_trades and si < len(setups):
        bo, en = setups[si]
        si += 1
        pts, res, ex = simulate_exit(bars15, side, en, mc, stop_pts, target_pts)
        trades.append((bo, en, ex, pts, res))
        if res == 'stop' and len(trades) < max_trades:
            continue
        if res == 'target':
            break
    return trades


def run_cached(b15_cache, atr_map, sl_mult, streak_filter, tdays, smap):
    streak_wins = {}
    out = []
    for session in sorted(b15_cache.keys()):
        if session not in smap:
            continue
        bias, sid = smap[session]
        if streak_wins.get(sid, 0) >= 3:
            continue
        if streak_filter:
            if streak_day(session, sid, tdays) > 3 or streak_rank(session, sid, smap) > 2:
                continue
        atrv = atr_map.get(session)
        if not atrv or atrv <= 0:
            continue
        b15 = b15_cache[session]
        if len(b15) < 3:
            continue
        mc = float(b15.iloc[0]['close'])
        side = 'long' if bias == 'bull' else 'short'
        stop_pts, target_pts = sl_mult * atrv, 2.0 * atrv
        day_tr = simulate_day(b15, side, mc, stop_pts, target_pts)
        for _bo, _en, _ex, pts, res in day_tr:
            if streak_wins.get(sid, 0) >= 3:
                break
            out.append({'session': session, 'pts': pts, 'result': res, 'atr': atrv, 'stop_pts': stop_pts, 'target_pts': target_pts})
            if res == 'target':
                streak_wins[sid] = streak_wins.get(sid, 0) + 1
    return out


def show(label, rows):
    if not rows:
        print(f'{label:30s} | no trades')
        return
    df = pd.DataFrame(rows)
    print(
        f"{label:30s} | {len(df):5d} | {(df['pts']>0).mean()*100:5.1f}% | {df['pts'].sum():+10.1f} | "
        f"{df['pts'].mean():+7.2f} | {(df['result']=='target').sum():4d} | {(df['result']=='stop').sum():4d} | "
        f"{(df['result']=='session_close').sum():4d} | avgATR {df['atr'].mean():.1f}"
    )


def main():
    daily = load_daily(HERE.parent / 'nq_daily.csv').sort_values('date')
    mo = build_monthly_mo(daily)
    atr = build_daily_atr(daily)
    tdays = sorted(daily['date'].dt.date.unique())
    smap = build_bias_streaks(daily, mo)
    print('Loading 1m...', flush=True)
    gby = load_1m_by_ny_date(DEFAULT_DBN_NQ, 'nq')
    print('Resampling 15m cache...', flush=True)
    b15_cache: dict[date, pd.DataFrame] = {}
    for i, (session, d1) in enumerate(gby.items()):
        b15_cache[session] = resample_15m_midnight_to_1600(d1, session)
        if (i + 1) % 1000 == 0:
            print(f'  … {i+1}/{len(gby)}', flush=True)
    hdr = f"{'Config':30s} | {'Trds':>5} | {'Win%':>6} | {'Total':>10} | {'Avg':>7} | {'Tgt':>4} | {'Stp':>4} | {'EOD':>4} |"
    for title, y0 in [('FULL HISTORY', None), ('2020-2026', 2020)]:
        print(f'\n=== {title} · TP 2×ATR (daily ATR14, causal) ===')
        print(hdr)
        for sl, filt in [(0.5, False), (1.0, False), (0.5, True), (1.0, True)]:
            rows = run_cached(b15_cache, atr, sl, filt, tdays, smap)
            if y0:
                rows = [r for r in rows if r['session'].year >= y0]
            tag = f'SL {sl}×ATR' + (' · D1-3·≤2/mo' if filt else '')
            show(tag, rows)


if __name__ == '__main__':
    main()
