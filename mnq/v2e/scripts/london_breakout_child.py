#!/usr/bin/env python3
"""
**London breakout + outside‑child scale‑in** — causal **5 m breakout**, **1 m** fills/exits.

**London box:** ``low`` / ``high`` from **[02:00, 09:30)** ET.

**RTH:** **[09:30, 16:00)** NY on **1 m** bars; **5 m** series is **RTH 1 m → 5 m**, ``label=left``, anchored **09:30**.

**Breakout (parent):** First **5 m** bar whose **close** is strictly outside the London box:

* ``close > London_high`` → **long** track,
* ``close < London_low`` → **short** track.

**Child:** A later **5 m** bar (strictly **after** the breakout bar, chronological ``iloc``) whose entire OHLC sits outside the box **and** matches breakout direction by candle color:

* **Long (upside break):** ``low > London_high`` **and** **green** candle ``close > open``.
* **Short (downside break):** ``high < London_low`` **and** **red** candle ``close < open``.

**Limits:** One **limit order per child**, price = that **5 m open**. Once the child bar **closes**, its OHLC is known (including outside‑box check); the order goes live at **bar close** time (``left_edge + 5 min``). Up to **``--max-children``** children (default **5**); **no trade** if there are **zero** qualifying children.

**Fills (1 m):** Long limit fills when ``low <= limit``; short limit when ``high >= limit``. Multiple resting limits may fill on the same minute.

**Scale:** Each filled limit adds **1 MNQ** contract (same SL/TP basket).

**Stop / target (fixed vs London box; ``range = London_high − London_low``):**

* **Long:** SL ``London_high − 5`` pts · TP ``London_high + range``.
* **Short:** SL ``London_low + 5`` pts · TP ``London_low − range``.

**Intrabar:** **Stop before target** (long: SL then TP). Each minute: if already in a position, evaluate exit first; then new limit fills; then evaluate exit again if size increased.

**EOD:** If still open, flatten at **last RTH 1 m close** before **16:00** (same tail rule as ``rules.v2e_causal._eod_exit``).

**Costs:** **\$2**/point per MNQ, **\$1.50** RT fee **per contract** at exit.

Example::

  cd potions/mnq/v2e/scripts
  python3 london_breakout_child.py
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

V2E_SCRIPTS = Path(__file__).resolve().parent
V2E_ROOT = V2E_SCRIPTS.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(V2E_SCRIPTS), str(MNQ_ROOT), str(POTIONS_SCRIPTS)]

from build_pattern_b_causal_research_charts import resample_rth_5m  # noqa: E402

from rules.v2e_causal import (  # noqa: E402
    RTH_HI,
    RTH_LO,
    _EPS,
    _eod_exit,
    london_low_high,
)

from v2e_causal_live_sim import load_by_day, scan_date_range  # noqa: E402

MULT = 2.0
FEE_RT = 1.50
SL_OFFSET_PTS = 5.0


Side = Literal['long', 'short']


def _net_usd_long(avg_entry: float, exit_px: float, contracts: int) -> float:
    return round(contracts * (exit_px - avg_entry) * MULT - contracts * FEE_RT, 2)


def _net_usd_short(avg_entry: float, exit_px: float, contracts: int) -> float:
    return round(contracts * (avg_entry - exit_px) * MULT - contracts * FEE_RT, 2)


def _long_exit_hit(
    *, high: float, low: float, avg_entry: float, stop_px: float, tp_px: float
) -> tuple[float | None, str]:
    hit_sl = low <= stop_px + _EPS
    hit_tp = high >= tp_px - _EPS
    if hit_sl:
        return stop_px, 'Loss' if stop_px < avg_entry - _EPS else 'Stop-BE'
    if hit_tp:
        return tp_px, 'Win'
    return None, ''


def _short_exit_hit(
    *, high: float, low: float, avg_entry: float, stop_px: float, tp_px: float
) -> tuple[float | None, str]:
    hit_sl = high >= stop_px - _EPS
    hit_tp = low <= tp_px + _EPS
    if hit_sl:
        return stop_px, 'Loss' if stop_px > avg_entry + _EPS else 'Stop-BE'
    if hit_tp:
        return tp_px, 'Win'
    return None, ''


@dataclass
class BreakoutChildOutcome:
    session_day: date
    status: Literal[
        'no_london_box',
        'no_breakout',
        'no_child',
        'filled',
    ]
    side: Side | None = None
    contracts: int = 0
    entry_avg: float = float('nan')
    exit_px: float = float('nan')
    net_usd: float = float('nan')
    result: str = ''
    london_low: float = float('nan')
    london_high: float = float('nan')
    range_pts: float = float('nan')
    tp_px: float = float('nan')
    sl_px: float = float('nan')
    ts_breakout_left: pd.Timestamp = field(default_factory=lambda: pd.NaT)
    ts_exit: pd.Timestamp = field(default_factory=lambda: pd.NaT)
    # Populated when simulate_session(..., record_chart_meta=True)
    chart_child_bar_left: list[pd.Timestamp] = field(default_factory=list)
    chart_order_limit_px: list[float] = field(default_factory=list)
    chart_order_live_ts: list[pd.Timestamp] = field(default_factory=list)
    chart_order_fill_ts: list[pd.Timestamp] = field(default_factory=list)


def collect_child_orders(
    bars5: pd.DataFrame,
    *,
    breakout_idx: int,
    side: Side,
    L: float,
    H: float,
    max_children: int,
) -> list[tuple[float, pd.Timestamp, pd.Timestamp]]:
    """Return list of (limit_px=5m open, live_ts=bar close time, child_bar_left). Child must be green (long) or red (short)."""
    out: list[tuple[float, pd.Timestamp, pd.Timestamp]] = []
    idx_list = list(bars5.index)
    for j in range(breakout_idx + 1, len(bars5)):
        if len(out) >= max_children:
            break
        row = bars5.iloc[j]
        ts_left = pd.Timestamp(idx_list[j])
        o = float(row['open'])
        hi = float(row['high'])
        lo = float(row['low'])
        cl = float(row['close'])
        if side == 'long':
            if lo <= H + _EPS:
                continue
            if not (cl > o + _EPS):
                continue
        else:
            if hi >= L - _EPS:
                continue
            if not (cl < o - _EPS):
                continue
        live_ts = ts_left + pd.Timedelta(minutes=5)
        out.append((o, live_ts, ts_left))
    return out


def simulate_session(
    day_1m: pd.DataFrame,
    session_day: date,
    *,
    max_children: int,
    record_chart_meta: bool = False,
) -> BreakoutChildOutcome:
    L, H = london_low_high(day_1m, session_day)
    if math.isnan(L) or math.isnan(H) or H <= L + _EPS:
        return BreakoutChildOutcome(session_day, 'no_london_box')

    rng = H - L
    bars5 = resample_rth_5m(day_1m, session_day)
    if bars5.empty:
        return BreakoutChildOutcome(session_day, 'no_breakout', london_low=L, london_high=H)

    breakout_idx: int | None = None
    side: Side | None = None
    for i in range(len(bars5)):
        cl = float(bars5.iloc[i]['close'])
        if cl > H + _EPS:
            breakout_idx = i
            side = 'long'
            break
        if cl < L - _EPS:
            breakout_idx = i
            side = 'short'
            break

    if breakout_idx is None or side is None:
        return BreakoutChildOutcome(session_day, 'no_breakout', london_low=L, london_high=H)

    ts_break_left = pd.Timestamp(bars5.index[breakout_idx])
    orders = collect_child_orders(bars5, breakout_idx=breakout_idx, side=side, L=L, H=H, max_children=max_children)
    chart_child_left: list[pd.Timestamp] = []
    chart_lim_px: list[float] = []
    chart_live: list[pd.Timestamp] = []
    chart_fill: list[pd.Timestamp] = []
    if record_chart_meta:
        for o_px, lv_ts, ch_left in orders:
            chart_lim_px.append(o_px)
            chart_live.append(lv_ts)
            chart_child_left.append(ch_left)
            chart_fill.append(pd.NaT)
    if not orders:
        return BreakoutChildOutcome(
            session_day,
            'no_child',
            side=side,
            london_low=L,
            london_high=H,
            range_pts=rng,
            ts_breakout_left=ts_break_left,
            chart_child_bar_left=chart_child_left,
            chart_order_limit_px=chart_lim_px,
            chart_order_live_ts=chart_live,
            chart_order_fill_ts=chart_fill,
        )

    if side == 'long':
        sl_px = H - SL_OFFSET_PTS
        tp_px = H + rng
    else:
        sl_px = L + SL_OFFSET_PTS
        tp_px = L - rng

    filled_flags = [False] * len(orders)
    entries: list[float] = []

    day = day_1m.sort_index()
    rth_1m: list[tuple[pd.Timestamp, float, float]] = []
    for ts, row in day.iterrows():
        ts = pd.Timestamp(ts)
        if ts.date() != session_day:
            continue
        if not (RTH_LO <= ts.time() < RTH_HI):
            continue
        rth_1m.append((ts, float(row['high']), float(row['low'])))

    def avg_entry() -> float:
        return sum(entries) / len(entries)

    def try_exit(ts: pd.Timestamp, hi: float, lo: float) -> BreakoutChildOutcome | None:
        nonlocal entries
        if not entries:
            return None
        ae = avg_entry()
        n = len(entries)
        if side == 'long':
            ex_px, label = _long_exit_hit(high=hi, low=lo, avg_entry=ae, stop_px=sl_px, tp_px=tp_px)
            if ex_px is None:
                return None
            nu = _net_usd_long(ae, float(ex_px), n)
        else:
            ex_px, label = _short_exit_hit(high=hi, low=lo, avg_entry=ae, stop_px=sl_px, tp_px=tp_px)
            if ex_px is None:
                return None
            nu = _net_usd_short(ae, float(ex_px), n)
        return BreakoutChildOutcome(
            session_day,
            'filled',
            side=side,
            contracts=n,
            entry_avg=ae,
            exit_px=float(ex_px),
            net_usd=nu,
            result=label,
            london_low=L,
            london_high=H,
            range_pts=rng,
            tp_px=tp_px,
            sl_px=sl_px,
            ts_breakout_left=ts_break_left,
            ts_exit=ts,
            chart_child_bar_left=chart_child_left,
            chart_order_limit_px=chart_lim_px,
            chart_order_live_ts=chart_live,
            chart_order_fill_ts=chart_fill,
        )

    for ts, hi, lo in rth_1m:
        # Exit before new fills if already positioned
        hit = try_exit(ts, hi, lo)
        if hit is not None:
            return hit

        # Limit fills
        for k, (lim_px, live_ts, _ch_left) in enumerate(orders):
            if filled_flags[k]:
                continue
            if ts < live_ts:
                continue
            if side == 'long':
                if lo <= lim_px + _EPS:
                    filled_flags[k] = True
                    entries.append(lim_px)
                    if record_chart_meta:
                        chart_fill[k] = ts
            else:
                if hi >= lim_px - _EPS:
                    filled_flags[k] = True
                    entries.append(lim_px)
                    if record_chart_meta:
                        chart_fill[k] = ts

        hit2 = try_exit(ts, hi, lo)
        if hit2 is not None:
            return hit2

    if not entries:
        return BreakoutChildOutcome(
            session_day,
            'no_child',
            side=side,
            london_low=L,
            london_high=H,
            range_pts=rng,
            ts_breakout_left=ts_break_left,
            chart_child_bar_left=chart_child_left,
            chart_order_limit_px=chart_lim_px,
            chart_order_live_ts=chart_live,
            chart_order_fill_ts=chart_fill,
        )

    ae = avg_entry()
    n = len(entries)
    eod_ts, eod_px, label = _eod_exit(day, session_day, side, ae)
    if side == 'long':
        nu = _net_usd_long(ae, float(eod_px), n)
    else:
        nu = _net_usd_short(ae, float(eod_px), n)

    return BreakoutChildOutcome(
        session_day,
        'filled',
        side=side,
        contracts=n,
        entry_avg=ae,
        exit_px=float(eod_px),
        net_usd=nu,
        result=label,
        london_low=L,
        london_high=H,
        range_pts=rng,
        tp_px=tp_px,
        sl_px=sl_px,
        ts_breakout_left=ts_break_left,
        ts_exit=eod_ts if not pd.isna(eod_ts) else pd.NaT,
        chart_child_bar_left=chart_child_left,
        chart_order_limit_px=chart_lim_px,
        chart_order_live_ts=chart_live,
        chart_order_fill_ts=chart_fill,
    )


def _max_dd(nets: pd.Series) -> float:
    if nets.empty:
        return 0.0
    eq = nets.astype(float).cumsum()
    return float((eq - eq.cummax()).min())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--max-children', type=int, default=5, help='Max scale-in limits (one per qualifying 5m child)')
    args = ap.parse_args()

    if args.max_children < 1:
        print('--max-children must be >= 1', file=sys.stderr)
        return 1

    if not args.m1.is_file():
        print(f'Missing 1m CSV {args.m1}', file=sys.stderr)
        return 1

    if args.start and args.end:
        date_min = pd.Timestamp(args.start).date()
        date_max = pd.Timestamp(args.end).date()
    else:
        date_min, date_max = scan_date_range(args.m1, args.start, args.end)

    by_day = load_by_day(args.m1, date_min, date_max)

    outcomes: list[BreakoutChildOutcome] = []
    for session_day in sorted(by_day.keys()):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day]
        if day_b.empty:
            continue
        outcomes.append(simulate_session(day_b, session_day, max_children=args.max_children))

    n_box = sum(1 for o in outcomes if o.status == 'no_london_box')
    n_eligible = len(outcomes) - n_box
    n_no_bo = sum(1 for o in outcomes if o.status == 'no_breakout')
    n_no_child = sum(1 for o in outcomes if o.status == 'no_child')
    filled = [o for o in outcomes if o.status == 'filled']

    print('=== London breakout + outside-child limits (causal 5m / 1m) ===')
    print(f'Date range: {date_min} .. {date_max}')
    print(f'Max children (scale-in limits): {args.max_children}')
    print(f'Weekday sessions scanned: {len(outcomes)}')
    print(f'  Missing London box: {n_box}')
    print(f'  No 5m close outside London (RTH): {n_no_bo}')
    print(f'  Breakout but zero outside-OHLC children: {n_no_child}')
    print(f'  Sessions with ≥1 fill: {len(filled)}')

    if filled:
        nets = pd.Series([float(o.net_usd) for o in filled])
        wins = sum(1 for o in filled if str(o.result) == 'Win')
        losses = sum(1 for o in filled if str(o.result) == 'Loss')
        eod_w = sum(1 for o in filled if str(o.result) == 'EOD-Win')
        eod_l = sum(1 for o in filled if str(o.result) == 'EOD-Loss')
        eod_f = sum(1 for o in filled if str(o.result) == 'EOD-Flat')
        be = sum(1 for o in filled if str(o.result) == 'Stop-BE')
        longs = [o for o in filled if o.side == 'long']
        shorts = [o for o in filled if o.side == 'short']

        print('\n--- Filled sessions ---')
        print(f'  TP hits (Win): {wins}')
        print(f'  SL hits (Loss): {losses}')
        print(f'  Stop-BE: {be}')
        print(f'  EOD — Win / Loss / Flat: {eod_w} / {eod_l} / {eod_f}')
        print(f'  Win rate (strict TP): {100.0 * wins / len(filled):.2f}%')
        print(f'  Win rate (TP + EOD-Win): {100.0 * (wins + eod_w) / len(filled):.2f}%')
        print(f'  Mean contracts / session: {pd.Series([o.contracts for o in filled]).mean():.2f}')
        print(f'  Mean net $/session: {nets.mean():.2f}')
        print(f'  Sum net $: {nets.sum():.2f}')
        print(f'  Max drawdown $ (session nets series): {_max_dd(nets):.2f}')
        if longs:
            nl = pd.Series([float(o.net_usd) for o in longs])
            print(f'\n  Long fills: {len(longs)}  |  Σ net ${nl.sum():,.2f}  |  mean ${nl.mean():.2f}')
        if shorts:
            ns = pd.Series([float(o.net_usd) for o in shorts])
            print(f'  Short fills: {len(shorts)}  |  Σ net ${ns.sum():,.2f}  |  mean ${ns.mean():.2f}')

    if n_eligible:
        print('\n--- Rates vs sessions with London box ---')
        print(f'  Breakout rate: {100.0 * (n_eligible - n_no_bo) / max(n_eligible, 1):.2f}%')
        print(f'  ≥1 fill / eligible: {100.0 * len(filled) / max(n_eligible, 1):.2f}%')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
