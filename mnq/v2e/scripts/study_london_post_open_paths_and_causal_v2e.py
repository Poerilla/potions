#!/usr/bin/env python3
"""
London box **post-open path** counts (strict causal bar logic) + **causal v2e** PnL sweep.

**London levels:** ``[02:00, 09:30)`` ET — same window as v2e (knowable before first RTH bar).

**Path universe:** only **[09:30, 16:00)** RTH **1 m** bars, chronological order.

**Touches:** ``touch_low`` if ``low <= London_low + eps``; ``touch_high`` if ``high >= London_high - eps``.

**Ambiguous bar:** same bar both touches low and high → excluded from **Pattern A** and **Pattern B**
first-touch classification.

**Inside range:** bar whose entire range lies in ``[London_low, London_high]``:
``low >= L - eps`` and ``high <= H + eps``.

**Pattern A — low-first, double high, retrace, no second low**

1. **First envelope interaction** after RTH open: first bar with ``touch_low OR touch_high`` must be a **clean**
   low-only touch (``touch_low`` and not ``touch_high``). Dual-touch bars do **not** count.
2. First ``touch_high`` strictly **after** that bar (indices increasing).
3. From the bar **after** first ``touch_high``, find first **inside-range** bar; **no** bar from the bar after the
   initial low touch through completion may ``touch_low`` again (only one London-low sweep allowed).
4. After that inside bar, first ``touch_high`` again (**second** take of London high).

**Pattern B — high-first, no London low, retrace, second high**

1. First envelope-interaction bar must be **clean high-only** (not ``touch_low``, not dual-touch).
2. **No** RTH bar **before** that first high touch may ``touch_low``.
3. After first ``touch_high``, same inside-range + second ``touch_high`` as Pattern A, with **no**
   ``touch_low`` on any bar through the second high.

---

**Causal v2e:** Replays ``simulate_v2e_causal_session`` over the same calendar span for breaker configs
``(5m, no close-confirm)``, ``(15m, no close-confirm)``, ``(15m, close-confirm)``, **stop_hunter** SL only,
**long + short**. Highlights the best total ``Σ net`` among those three.

Example::

  cd potions/mnq/v2e/scripts
  python3 study_london_post_open_paths_and_causal_v2e.py
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd

V2E_SCRIPTS = Path(__file__).resolve().parent
V2E_ROOT = V2E_SCRIPTS.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(V2E_SCRIPTS), str(MNQ_ROOT), str(POTIONS_SCRIPTS)]

from backtest_london_sweep_breaker import (  # noqa: E402
    london_low_high,
)

from v2e_causal_live_sim import (  # noqa: E402
    collect_trades,
    load_by_day,
    scan_date_range,
)

from rules.v2e_causal import RTH_HI as RULES_RTH_HI  # noqa: E402
from rules.v2e_causal import RTH_LO as RULES_RTH_LO  # noqa: E402

_EPS_PATH = 1e-9


def _max_dd(nets: pd.Series) -> float:
    if nets.empty:
        return 0.0
    eq = nets.astype(float).cumsum()
    return float((eq - eq.cummax()).min())


def summary_filled(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {'n': 0, 'sum_net': 0.0, 'wr': float('nan'), 'max_dd': 0.0}
    work = df[df['status'].astype(str) == 'filled'].copy()
    if work.empty:
        return {'n': 0, 'sum_net': 0.0, 'wr': float('nan'), 'max_dd': 0.0}
    nets = work['net_usd'].astype(float)
    return {
        'n': int(len(work)),
        'sum_net': float(nets.sum()),
        'wr': float((nets > 0).mean() * 100.0),
        'max_dd': _max_dd(nets),
    }


def rth_high_low_bars(day_1m: pd.DataFrame, session_day: date) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for ts, row in day_1m.iterrows():
        if ts.date() != session_day:
            continue
        if not (RULES_RTH_LO <= ts.time() < RULES_RTH_HI):
            continue
        out.append((float(row['high']), float(row['low'])))
    return out


def touch_low(lo: float, L: float) -> bool:
    return lo <= L + _EPS_PATH


def touch_high(hi: float, H: float) -> bool:
    return hi >= H - _EPS_PATH


def bar_inside(hi: float, lo: float, L: float, H: float) -> bool:
    return lo >= L - _EPS_PATH and hi <= H + _EPS_PATH


def pattern_low_first_double_high(bars: list[tuple[float, float]], L: float, H: float) -> bool:
    low1: int | None = None
    for i, (hi, lo) in enumerate(bars):
        tl = touch_low(lo, L)
        th = touch_high(hi, H)
        if not tl and not th:
            continue
        if tl and not th:
            low1 = i
            break
        return False
    else:
        return False

    assert low1 is not None
    high1: int | None = None
    for j in range(low1 + 1, len(bars)):
        hi_j, lo_j = bars[j]
        if touch_low(lo_j, L):
            return False
        if touch_high(hi_j, H):
            high1 = j
            break
    else:
        return False

    inside_k: int | None = None
    assert high1 is not None
    for k in range(high1 + 1, len(bars)):
        hi_k, lo_k = bars[k]
        if touch_low(lo_k, L):
            return False
        if bar_inside(hi_k, lo_k, L, H):
            inside_k = k
            break
    else:
        return False

    assert inside_k is not None
    for m in range(inside_k + 1, len(bars)):
        hi_m, lo_m = bars[m]
        if touch_low(lo_m, L):
            return False
        if touch_high(hi_m, H):
            return True
    return False


def pattern_high_only_double_high(bars: list[tuple[float, float]], L: float, H: float) -> bool:
    high1: int | None = None
    for i, (hi, lo) in enumerate(bars):
        tl = touch_low(lo, L)
        th = touch_high(hi, H)
        if not tl and not th:
            continue
        if th and not tl:
            high1 = i
            break
        return False
    else:
        return False

    assert high1 is not None
    for i in range(high1):
        if touch_low(bars[i][1], L):
            return False

    inside_k: int | None = None
    for k in range(high1 + 1, len(bars)):
        hi_k, lo_k = bars[k]
        if touch_low(lo_k, L):
            return False
        if bar_inside(hi_k, lo_k, L, H):
            inside_k = k
            break
    else:
        return False

    assert inside_k is not None
    for m in range(inside_k + 1, len(bars)):
        hi_m, lo_m = bars[m]
        if touch_low(lo_m, L):
            return False
        if touch_high(hi_m, H):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m CSV {args.m1}', file=sys.stderr)
        return 1

    if args.start and args.end:
        date_min = pd.Timestamp(args.start).date()
        date_max = pd.Timestamp(args.end).date()
    else:
        date_min, date_max = scan_date_range(args.m1, args.start, args.end)
    by_day = load_by_day(args.m1, date_min, date_max)

    eligible = 0
    n_low_double_hi = 0
    n_hi_double_hi = 0

    for session_day in sorted(by_day.keys()):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day]
        if day_b.empty:
            continue
        L, H = london_low_high(day_b, session_day)
        if math.isnan(L) or math.isnan(H) or H <= L + _EPS_PATH:
            continue
        bars = rth_high_low_bars(day_b, session_day)
        if len(bars) < 4:
            continue
        eligible += 1
        if pattern_low_first_double_high(bars, L, H):
            n_low_double_hi += 1
        if pattern_high_only_double_high(bars, L, H):
            n_hi_double_hi += 1

    print('\n=== London post-open path study (causal bar sequence rules — see docstring) ===')
    print(f'Eligible weekday sessions (valid London box + ≥4 RTH bars): {eligible}')
    print(f'Pattern A — low first → high → inside range → high again (single London low): {n_low_double_hi}')
    print(f'Pattern B — high first, never London low → inside → high again: {n_hi_double_hi}')
    if eligible:
        print(f'Pattern A rate: {100.0 * n_low_double_hi / eligible:.2f}%')
        print(f'Pattern B rate: {100.0 * n_hi_double_hi / eligible:.2f}%')

    print('\n=== Causal v2e (stop_hunter SL, long + short), same date span ===')
    configs = [
        (5, False, '5m breaker'),
        (15, False, '15m breaker'),
        (15, True, '15m breaker + breaker close confirm'),
    ]
    best_label = ''
    best_sum = float('-inf')

    for bm, cc, label in configs:
        all_df, _audit = collect_trades(
            by_day,
            sides=['long', 'short'],
            sl_families=['stop_hunter'],
            breaker_minutes=bm,
            require_breaker_close_confirm=cc,
            allow_reentry=False,
            max_reentries=0,
        )
        fd = all_df[all_df['status'].astype(str) == 'filled'].copy()
        st = summary_filled(all_df)
        print(f'\n--- {label} ---')
        print(f'Filled trades: {st["n"]}')
        print(f'Σ Net USD (1 MNQ): ${st["sum_net"]:,.2f}')
        print(f'Win rate (Net > 0): {st["wr"]:.2f}%')
        print(f'Max DD (trade cumulative): ${st["max_dd"]:,.2f}')
        eff = st['sum_net'] / abs(st['max_dd']) if st['max_dd'] else float('nan')
        print(f'Σ Net / |max DD|: {eff:.3f}')
        if not fd.empty:
            for side in ['long', 'short']:
                ss = summary_filled(fd[fd['side'].astype(str) == side])
                print(f'  [{side}] n={ss["n"]}  Σ=${ss["sum_net"]:,.2f}  DD=${ss["max_dd"]:,.2f}')
        if st['sum_net'] > best_sum:
            best_sum = st['sum_net']
            best_label = label

    print('\n--- Best of {5m, 15m, 15m+close} by Σ Net (stop_hunter, both sides) ---')
    print(f'{best_label}: Σ Net ${best_sum:,.2f}')

    print(f'\nCalendar span: {date_min} .. {date_max}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
