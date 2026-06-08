#!/usr/bin/env python3
"""
Experiment only — **does not change** ``backtest_london_sweep_breaker.py``.

Baseline piercer: first **1 m** swing strictly after SH with ``high > breaker_high``.

Variant piercer: first **5 m** bar (02:00 NY grid) **after** SH opens whose candle **tags**
``breaker_high`` (``high >= breaker_high``) **and** **closes above** it (``close > breaker_high``).

Stop-hunter / breaker fixed-point matches baseline except depth segment ends strictly **before**
the variant piercer 5 m bar opens (``ts < piercer_5m_left`` on 1 m bars).

Fill: first **1 m** bar with ``ts_event >= piercer_5m_end`` and ``low <= breaker_high``.

Run::

  cd potions/mnq/v2e/scripts
  python3 experiment_piercer_5m_close_over_breaker.py

Uses same 1m CSV, fees, SL modes, and date span discovery as the main backtest.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
sys.path[:0] = [str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402

import backtest_london_sweep_breaker as bt  # noqa: E402


def find_setup_long_piercer_5m_close(
    session_day: date,
    ldn_l: float,
    day_1m: pd.DataFrame,
) -> dict | None:
    ts_list = list(day_1m.index)
    highs = [float(x) for x in day_1m['high'].tolist()]
    lows = [float(x) for x in day_1m['low'].tolist()]
    closes = [float(x) for x in day_1m['close'].tolist()]
    n = len(ts_list)
    if n < 5:
        return None

    first_sweep_i: int | None = None
    for i in range(n):
        t = ts_list[i]
        if t.date() != session_day:
            continue
        if not (bt.RTH_LO <= t.time() < bt.RTH_HI):
            continue
        if lows[i] <= ldn_l + bt._EPS:
            first_sweep_i = i
            break
    if first_sweep_i is None:
        return None

    win_start = bt.london_low_first_touch_index(session_day, ldn_l, ts_list, lows)
    if win_start is None or win_start >= first_sweep_i:
        return None

    bars5 = bt.resample_session_5m_from_02(day_1m, session_day)
    if len(bars5) < 3:
        return None

    idxs5 = bars5.index.to_list()
    h5 = bars5['high'].astype(float).to_numpy()
    c5 = bars5['close'].astype(float).to_numpy()
    five = pd.Timedelta(minutes=5)

    sh_i = first_sweep_i
    breaker_high = 0.0
    breaker_low = 0.0
    breaker_5m_left = ts_list[first_sweep_i]
    piercer_5m_left: pd.Timestamp | None = None
    piercer_5m_end: pd.Timestamp | None = None
    piercer_high = 0.0
    piercer_1m_proxy: int | None = None

    for _ in range(30):
        brk = bt.pick_breaker_5m_last_swing_through_after_sh_bucket(
            bars5, session_day, ts_list[sh_i]
        )
        if brk is None:
            return None
        breaker_high, breaker_low, breaker_5m_left = brk

        ts_sh = ts_list[sh_i]
        piercer_5m_left = None
        for bl, hi, cl in zip(idxs5, h5, c5):
            bar_end = bl + five
            if bar_end <= ts_sh:
                continue
            if hi >= breaker_high - bt._EPS and cl > breaker_high + bt._EPS:
                piercer_5m_left = bl
                piercer_high = float(hi)
                piercer_5m_end = bar_end
                break
        if piercer_5m_left is None or piercer_5m_end is None:
            return None

        seg_k = [
            k
            for k in range(first_sweep_i, n)
            if ts_list[k] < piercer_5m_left
        ]
        if not seg_k:
            return None
        sh_next = min(seg_k, key=lambda k: (lows[k], k))

        if sh_next == sh_i:
            break
        sh_i = sh_next
    else:
        return None

    # First 1 m bar at or after piercer 5 m completes — proxy index for charts / consistency
    piercer_1m_proxy = None
    for j in range(n):
        if ts_list[j].date() != session_day:
            continue
        if ts_list[j] >= piercer_5m_end:
            piercer_1m_proxy = j
            break
    if piercer_1m_proxy is None:
        return None

    fill_i = None
    for j in range(piercer_1m_proxy, n):
        if ts_list[j].date() != session_day:
            continue
        if ts_list[j].time() >= bt.EOD_CUTOFF:
            break
        if lows[j] <= breaker_high + bt._EPS:
            fill_i = j
            break
    if fill_i is None:
        return None

    return {
        'sh_i': sh_i,
        'piercer_i': piercer_1m_proxy,
        'breaker_high': breaker_high,
        'breaker_low': breaker_low,
        'breaker_5m_left': breaker_5m_left,
        'stop_hunter_low': lows[sh_i],
        'piercer_high': piercer_high,
        'fill_i': fill_i,
    }


def compute_setup_variant(day_1m: pd.DataFrame, session_day: date) -> dict | None:
    ldn_l, _ldn_h = bt.london_low_high(day_1m, session_day)
    if bt.math.isnan(ldn_l):
        return None
    ts_order = list(day_1m.index)
    setup = find_setup_long_piercer_5m_close(session_day, ldn_l, day_1m)
    if setup is None:
        return None
    tp_px = setup['stop_hunter_low'] + (setup['piercer_high'] - setup['stop_hunter_low']) * 2.0
    entry = setup['breaker_high']
    if tp_px <= entry + bt._EPS:
        return None
    return {
        **setup,
        'ldn_l': ldn_l,
        'tp_px': tp_px,
        'entry': entry,
        'ts_order': ts_order,
    }


def main() -> int:
    m1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
    if not m1.is_file():
        print(f'Missing {m1}', file=sys.stderr)
        return 1

    NY = bt.NY
    chunks_for_max: date | None = None
    chunks_for_min: date | None = None
    for ch in pd.read_csv(m1, usecols=['ts_event'], chunksize=800_000):
        ch['ts_event'] = pd.to_datetime(ch['ts_event'], utc=True).dt.tz_convert(NY)
        dpart = ch['ts_event'].dt.date
        cmin, cmax = dpart.min(), dpart.max()
        chunks_for_min = cmin if chunks_for_min is None else min(chunks_for_min, cmin)
        chunks_for_max = cmax if chunks_for_max is None else max(chunks_for_max, cmax)
    assert chunks_for_min is not None and chunks_for_max is not None

    needed = {d for d in bt.iter_calendar_dates(chunks_for_min, chunks_for_max) if d.weekday() < 5}
    raw = ann.load_1m_for_dates(str(m1), chunks_for_min, chunks_for_max, needed)
    raw = ann.pick_front_month_day(raw)
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw = raw.set_index('ts_event').sort_index()
    raw['__d'] = raw.index.date
    by_day = {d: g.drop(columns=['__d'], errors='ignore') for d, g in raw.groupby('__d')}
    raw = raw.drop(columns=['__d'])

    def collect(compute) -> dict[bt.SLMode, list[bt.TradeResult]]:
        buckets: dict[bt.SLMode, list[bt.TradeResult]] = {sm: [] for sm in bt.SLMode}
        for session_day in sorted(by_day.keys()):
            if session_day.weekday() >= 5:
                continue
            day_b = by_day[session_day]
            if day_b.empty:
                continue
            base = compute(day_b, session_day)
            if base is None:
                continue
            for sm in bt.SLMode:
                tr = bt.finalize_trade(day_b, session_day, base, sm)
                if tr is not None:
                    buckets[sm].append(tr)
        return buckets

    base_cache = collect(bt.compute_setup)
    var_cache = collect(compute_setup_variant)

    sl_main = bt.SLMode.stop_hunter_low

    def stats(rows: list[bt.TradeResult]) -> dict:
        st = bt.summarize(rows)
        losses = sum(1 for r in rows if r.net_usd <= 0)
        loss_lab = sum(1 for r in rows if str(r.result).startswith('Loss'))
        return {**st, 'losses_net_nonpos': losses, 'loss_result_label': loss_lab}

    print('Comparison on same calendar span and economics as main backtest.\n')
    print(f'Date range: {chunks_for_min} .. {chunks_for_max}\n')

    for label, cache in (
        ('BASELINE (1 m swing piercer)', base_cache),
        ('VARIANT (first 5 m bar: touch breaker high + close above)', var_cache),
    ):
        print('=' * 72)
        print(label)
        print('=' * 72)
        for sm in bt.SLMode:
            rows = cache[sm]
            s = stats(rows)
            print(f'\n--- SL = {sm.value} ---')
            print(f'Sessions with trade: {s["n"]}')
            print(f'Σ Net USD (1 MNQ): ${s["sum_net"]:,.2f}')
            print(f'Win rate (Net > 0): {s["wr"]:.2f}%')
            print(f'Max DD (leg cumulative): ${s["max_dd"]:,.2f}')
            print(f'Mean MAE (pts): {s["mean_mae"]:.4f}')
            eff = s['sum_net'] / abs(s['max_dd']) if s['max_dd'] else float('nan')
            print(f'Σ Net / |max DD|: {eff:.3f}')
            print(f'Trades with net ≤ 0: {s["losses_net_nonpos"]}')
            print(f'Trades with result Loss (label): {s["loss_result_label"]}')
        print()

    b = stats(base_cache[sl_main])
    v = stats(var_cache[sl_main])
    print('=' * 72)
    print(f'DELTA (variant − baseline), SL = {sl_main.value}')
    print('=' * 72)
    print(f'Δ trades: {v["n"] - b["n"]}')
    print(f'Δ Σ Net USD: ${v["sum_net"] - b["sum_net"]:,.2f}')
    print(f'Δ Win rate (pts): {v["wr"] - b["wr"]:.2f}')
    print(f'Δ Max DD: ${v["max_dd"] - b["max_dd"]:,.2f}')
    print(f'Δ trades net ≤ 0: {v["losses_net_nonpos"] - b["losses_net_nonpos"]}')
    print(f'Δ Loss (result label): {v["loss_result_label"] - b["loss_result_label"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
