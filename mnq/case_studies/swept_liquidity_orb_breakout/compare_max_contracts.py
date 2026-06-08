#!/usr/bin/env python3
"""Compare replay_row(..., max_contracts=3) vs 5: Σ$, equity, max DD. No charts."""
from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PATH = Path(__file__).resolve().parent / 'resim_scale_in_ladder.py'


def load_mod():
    spec = importlib.util.spec_from_file_location('chl', PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


MOD = load_mod()

SL = 70.0
CE = 5.0


def net_ok(r):
    if r['status'] != 'ok':
        return 0.0
    return float(r['Net_$'])


def dd_trade_stats(arr: np.ndarray):
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd_curve = cum - peak
    max_dd = float(dd_curve.min())
    trough_i = int(np.argmin(dd_curve))
    peak_i = int(np.argmax(cum[: trough_i + 1])) if trough_i >= 0 else 0
    return cum, dd_curve, max_dd, peak_i, trough_i


def kadane_min(a):
    best = cur = float('inf')
    s = e = 0
    cur_s = 0
    for i, x in enumerate(a):
        if cur > 0:
            cur = x
            cur_s = i
        else:
            cur += x
        if cur < best:
            best = cur
            s, e = cur_s, i
    return best, s, e


def daily_agg(rows, nets) -> tuple[list, np.ndarray]:
    d_tot: dict = defaultdict(float)
    for (row, _), n in zip(rows, nets):
        d = pd.to_datetime(row['Date']).date()
        d_tot[d] += n
    days = sorted(d_tot.keys())
    return days, np.cumsum(np.array([d_tot[d] for d in days], dtype=float))


def main():
    csv = pd.read_csv(Path(__file__).resolve().parent / 'mnq_swept_orb_breakout.csv')
    filled = csv[csv['Entry_Price'].notna()].copy()
    by_d = MOD.load_by_date()

    pairs = []
    for _, row in filled.iterrows():
        d = pd.to_datetime(row['Date']).date()
        if d not in by_d:
            continue
        dd = by_d[d]
        if 'symbol' in dd.columns:
            dd = dd[dd['symbol'] == row['Symbol']]
        if dd.empty:
            continue
        pairs.append((row, dd))


    def rk(pair):
        r = pair[0]
        sw = pd.to_datetime(r['Sweep'])
        if getattr(sw, 'tzinfo', None) is None:
            sw = sw.tz_localize(MOD.NY)
        else:
            sw = sw.tz_convert(MOD.NY)
        return (pd.to_datetime(r['Date']).date(), sw, str(r.get('Sequence_ID', '')))

    pairs.sort(key=rk)

    print(
        'Child ladder: tier1 SL=L0±{:.0f}, child long RH−{:.0f} short RL+{:.0f}, TP1 only. '
        'Compared: max_contracts=3 vs max_contracts=5\n'.format(SL, CE, CE)
    )

    out3 = []
    out5 = []
    for row, dd in pairs:
        out3.append(MOD.replay_row(row, dd, SL, CE, max_contracts=3))
        out5.append(MOD.replay_row(row, dd, SL, CE, max_contracts=5))

    nets3 = np.array([net_ok(r) for r in out3])
    nets5 = np.array([net_ok(r) for r in out5])

    n_ok3 = sum(1 for r in out3 if r['status'] == 'ok')
    n_ok5 = sum(1 for r in out5 if r['status'] == 'ok')

    sum3 = float(nets3.sum())
    sum5 = float(nets5.sum())

    cum3, dd_curve3, md3, p3i, t3i = dd_trade_stats(nets3)
    cum5, dd_curve5, md5, p5i, t5i = dd_trade_stats(nets5)

    worst_contig3 = kadane_min(nets3.tolist())[0]
    worst_contig5 = kadane_min(nets5.tolist())[0]

    days_ord, day_cum3 = daily_agg(pairs, nets3)
    _, day_cum5 = daily_agg(pairs, nets5)
    peak_d3 = np.maximum.accumulate(day_cum3)
    dd_d3 = day_cum3 - peak_d3
    md_daily3 = float(dd_d3.min())
    trough_d_idx3 = int(np.argmin(dd_d3))

    peak_d5 = np.maximum.accumulate(day_cum5)
    dd_d5 = day_cum5 - peak_d5
    md_daily5 = float(dd_d5.min())
    trough_d_idx5 = int(np.argmin(dd_d5))

    print(f"{'Metric':40} {'3 ctr':>18} {'5 ctr':>18}")
    print('-' * 78)
    print(f"{'Σ Net_$ (replay path, zeros for non-ok)':40} ${sum3:>16,.2f} ${sum5:>16,.2f}")
    print(f"{'Ending cumulative equity vs $0':40} ${float(cum3[-1]):>16,.2f} ${float(cum5[-1]):>16,.2f}")
    print(f"{'Improvement vs 3 ctr':40} {'':18} {'$' + f'{sum5 - sum3:,.2f}':>18}")
    print(f"{'n status=ok':40} {n_ok3:>18} {n_ok5:>18}")

    print()
    print('--- Peak-to-trough on TRADE SEQUENCE (cumsum Net_$ per row) ---')
    print(f"{'Max drawdown ($)':40} ${md3:>16,.2f} ${md5:>16,.2f}")
    d_p3, d_t3 = pd.to_datetime(pairs[p3i][0]['Date']).date(), pd.to_datetime(pairs[t3i][0]['Date']).date()
    d_p5, d_t5 = pd.to_datetime(pairs[p5i][0]['Date']).date(), pd.to_datetime(pairs[t5i][0]['Date']).date()
    print(f"{'Peak row date (cum after idx) → trough':40}")
    print(f"{'  max 3 ctr':40} {d_p3} → {d_t3}  (#{p3i + 1} → #{t3i + 1})")
    print(f"{'  max 5 ctr':40} {d_p5} → {d_t5}  (#{p5i + 1} → #{t5i + 1})")
    print(f"{'Peak cum equity @ peak → trough':40}")
    print(f"{'  3 ctr':40} ${float(cum3[p3i]):,.2f} → ${float(cum3[t3i]):,.2f}")
    print(f"{'  5 ctr':40} ${float(cum5[p5i]):,.2f} → ${float(cum5[t5i]):,.2f}")
    print(f"{'Worst contiguous trade cluster (min subarray sum)':40} ${worst_contig3:>16,.2f} ${worst_contig5:>16,.2f}")

    print()
    print('--- Daily aggregated equity (same trade order, summed by calendar day) ---')
    print(f"{'Max drawdown daily curve ($)':40} ${md_daily3:>16,.2f} ${md_daily5:>16,.2f}")
    print(f"Trough calendar day index: {'3 ctr':22} day {days_ord[trough_d_idx3]}")
    print(f"{'':40}{'5 ctr':22} day {days_ord[trough_d_idx5]}")


if __name__ == '__main__':
    main()
