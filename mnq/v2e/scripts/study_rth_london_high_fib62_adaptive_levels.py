#!/usr/bin/env python3
"""
Causal 1 m study — **Fib pullback long with adaptive reference high + blended floor**.

**London box:** ``low`` / ``high`` over **[02:00, 09:30)** ET.

**NY session low (causal):** Running minimum of **RTH** **[09:30, 16:00)** ``low`` from the **first**
RTH bar through the **current** bar (inclusive).

**Effective floor:** ``L_eff = min(London_low, NY_session_low_so_far)`` — used for abort-before-fill,
Fib **low anchor**, and **stop** while in trade (updates each bar as new lows print).

**Arm:** First **RTH** touch of **London high** (same as baseline fib study).

**Reference high (adaptive):** Starts at the **high** of the arming bar. While **waiting for fill**, each bar:
if ``high > H_ref``, set ``H_ref ← high`` (strict higher high). **Limit** is always::

    entry_live = H_ref - fib * (H_ref - L_eff)

using **current** ``H_ref`` and ``L_eff`` after the usual bar updates and pessimistic ordering below.

**Before fill — pessimistic intrabar order:**

1. Update ``NY_session_low`` including this bar’s ``low``; ``L_eff = min(London_low, NY_session_low)``.
2. **Abort** if ``low <= L_eff`` (effective floor tagged).
3. Ratchet **``H_ref``** upward if ``high > H_ref``.
4. If ``H_ref <= L_eff`` (degenerate range): abort.
5. **Fill** if ``low <= entry_live``.

**After fill:** **SL** = **current** ``L_eff`` each bar (dynamic). **TP** = **London high** (box).
Exit ordering matches ``rules.v2e_causal._exit_hit`` (stop before target). **EOD** = last RTH close before **16:00**.

**PnL:** MNQ **\$2**/point, **\$1.50** RT fee.

Example::

  cd potions/mnq/v2e/scripts
  python3 study_rth_london_high_fib62_adaptive_levels.py
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

from rules.v2e_causal import (  # noqa: E402
    RTH_HI,
    RTH_LO,
    _EPS,
    _eod_exit,
    _exit_hit,
    _net_usd,
    london_low_high,
)

from study_rth_london_high_fib62_limit_long import PHI_INV  # noqa: E402

from v2e_causal_live_sim import load_by_day, scan_date_range  # noqa: E402


def touch_low(lo: float, level: float) -> bool:
    return lo <= level + _EPS


def touch_high(hi: float, H: float) -> bool:
    return hi >= H - _EPS


def limit_buy_hit(low: float, entry: float) -> bool:
    return low <= entry + _EPS


def compute_limit(H_ref: float, L_eff: float, fib_ratio: float) -> float | None:
    if H_ref <= L_eff + _EPS:
        return None
    return H_ref - fib_ratio * (H_ref - L_eff)


@dataclass
class AdaptiveSessionOutcome:
    session_day: date
    status: Literal[
        'no_london_box',
        'no_rth_high_touch',
        'aborted_floor_before_fill',
        'no_fill_eod',
        'filled',
    ]
    london_low: float = float('nan')
    london_high: float = float('nan')
    entry_px: float = float('nan')
    exit_px: float = float('nan')
    result: str = ''
    net_usd: float = float('nan')
    mae_pts: float = float('nan')
    mfe_pts: float = float('nan')
    ts_first_rth_high: pd.Timestamp = field(default_factory=lambda: pd.NaT)
    ts_fill: pd.Timestamp = field(default_factory=lambda: pd.NaT)
    ts_exit: pd.Timestamp = field(default_factory=lambda: pd.NaT)
    # Snapshot at fill (for charts / audit)
    ref_high_at_fill: float = float('nan')
    ny_session_low_at_fill: float = float('nan')
    effective_low_at_fill: float = float('nan')


def simulate_session_adaptive(
    day_1m: pd.DataFrame,
    session_day: date,
    *,
    fib_ratio: float,
) -> AdaptiveSessionOutcome:
    L_box, H_box = london_low_high(day_1m, session_day)
    if math.isnan(L_box) or math.isnan(H_box) or H_box <= L_box + _EPS:
        return AdaptiveSessionOutcome(session_day, 'no_london_box')

    phase: Literal['wait_high', 'wait_fill', 'in_trade'] = 'wait_high'

    day = day_1m.sort_index()
    order_entry = float('nan')
    mae = 0.0
    mfe = 0.0
    first_high_ts = pd.NaT
    fill_ts = pd.NaT

    H_ref = float('nan')
    R_ny = float('inf')
    snap_rh_fill = float('nan')
    snap_ny_fill = float('nan')
    snap_eff_fill = float('nan')

    rth_rows: list[tuple[pd.Timestamp, float, float, float]] = []
    for ts, row in day.iterrows():
        ts = pd.Timestamp(ts)
        if ts.date() != session_day:
            continue
        if not (RTH_LO <= ts.time() < RTH_HI):
            continue
        hi = float(row['high'])
        lo = float(row['low'])
        cl = float(row['close'])
        rth_rows.append((ts, hi, lo, cl))

    if not rth_rows:
        return AdaptiveSessionOutcome(session_day, 'no_rth_high_touch', london_low=L_box, london_high=H_box)

    def _abort() -> AdaptiveSessionOutcome:
        return AdaptiveSessionOutcome(
            session_day,
            'aborted_floor_before_fill',
            london_low=L_box,
            london_high=H_box,
            ts_first_rth_high=first_high_ts,
        )

    for ts, hi, lo, _cl in rth_rows:
        R_ny = min(R_ny, lo)
        L_eff = min(L_box, R_ny)

        if phase == 'in_trade':
            assert not math.isnan(order_entry)
            ex_px, result, b_mae, b_mfe = _exit_hit(
                side='long',
                high=hi,
                low=lo,
                entry=order_entry,
                stop_px=L_eff,
                tp_px=H_box,
            )
            mae = max(mae, b_mae)
            mfe = max(mfe, b_mfe)
            if ex_px is not None and result is not None:
                nu = _net_usd('long', order_entry, float(ex_px))
                return AdaptiveSessionOutcome(
                    session_day,
                    'filled',
                    london_low=L_box,
                    london_high=H_box,
                    entry_px=order_entry,
                    exit_px=float(ex_px),
                    result=result,
                    net_usd=nu,
                    mae_pts=mae,
                    mfe_pts=mfe,
                    ts_first_rth_high=first_high_ts,
                    ts_fill=fill_ts,
                    ts_exit=ts,
                    ref_high_at_fill=snap_rh_fill,
                    ny_session_low_at_fill=snap_ny_fill,
                    effective_low_at_fill=snap_eff_fill,
                )
            continue

        if phase == 'wait_high':
            if not touch_high(hi, H_box):
                continue
            first_high_ts = ts
            H_ref = hi
            phase = 'wait_fill'

            if touch_low(lo, L_eff):
                return _abort()

            lim = compute_limit(H_ref, L_eff, fib_ratio)
            if lim is None:
                return _abort()

            if limit_buy_hit(lo, lim):
                order_entry = lim
                phase = 'in_trade'
                fill_ts = ts
                rh_fill = H_ref
                ny_fill = R_ny
                eff_fill = L_eff
                snap_rh_fill, snap_ny_fill, snap_eff_fill = rh_fill, ny_fill, eff_fill
                ex_px, result, b_mae, b_mfe = _exit_hit(
                    side='long',
                    high=hi,
                    low=lo,
                    entry=order_entry,
                    stop_px=L_eff,
                    tp_px=H_box,
                )
                mae = max(mae, b_mae)
                mfe = max(mfe, b_mfe)
                if ex_px is not None and result is not None:
                    nu = _net_usd('long', order_entry, float(ex_px))
                    return AdaptiveSessionOutcome(
                        session_day,
                        'filled',
                        london_low=L_box,
                        london_high=H_box,
                        entry_px=order_entry,
                        exit_px=float(ex_px),
                        result=result,
                        net_usd=nu,
                        mae_pts=mae,
                        mfe_pts=mfe,
                        ts_first_rth_high=first_high_ts,
                        ts_fill=fill_ts,
                        ts_exit=ts,
                        ref_high_at_fill=rh_fill,
                        ny_session_low_at_fill=ny_fill,
                        effective_low_at_fill=eff_fill,
                    )
            continue

        # wait_fill
        assert phase == 'wait_fill'
        assert not math.isnan(H_ref)

        if touch_low(lo, L_eff):
            return _abort()

        if hi > H_ref:
            H_ref = hi

        lim = compute_limit(H_ref, L_eff, fib_ratio)
        if lim is None:
            return _abort()

        if limit_buy_hit(lo, lim):
            order_entry = lim
            phase = 'in_trade'
            fill_ts = ts
            rh_fill = H_ref
            ny_fill = R_ny
            eff_fill = L_eff
            snap_rh_fill, snap_ny_fill, snap_eff_fill = rh_fill, ny_fill, eff_fill
            ex_px, result, b_mae, b_mfe = _exit_hit(
                side='long',
                high=hi,
                low=lo,
                entry=order_entry,
                stop_px=L_eff,
                tp_px=H_box,
            )
            mae = max(mae, b_mae)
            mfe = max(mfe, b_mfe)
            if ex_px is not None and result is not None:
                nu = _net_usd('long', order_entry, float(ex_px))
                return AdaptiveSessionOutcome(
                    session_day,
                    'filled',
                    london_low=L_box,
                    london_high=H_box,
                    entry_px=order_entry,
                    exit_px=float(ex_px),
                    result=result,
                    net_usd=nu,
                    mae_pts=mae,
                    mfe_pts=mfe,
                    ts_first_rth_high=first_high_ts,
                    ts_fill=fill_ts,
                    ts_exit=ts,
                    ref_high_at_fill=rh_fill,
                    ny_session_low_at_fill=ny_fill,
                    effective_low_at_fill=eff_fill,
                )

    if phase == 'wait_high':
        return AdaptiveSessionOutcome(session_day, 'no_rth_high_touch', london_low=L_box, london_high=H_box)

    if phase == 'wait_fill':
        return AdaptiveSessionOutcome(
            session_day,
            'no_fill_eod',
            london_low=L_box,
            london_high=H_box,
            ts_first_rth_high=first_high_ts,
        )

    assert phase == 'in_trade'
    eod_ts, eod_px, result = _eod_exit(day, session_day, 'long', order_entry)
    if not pd.isna(eod_ts):
        last = day.loc[eod_ts]
        mae = max(mae, order_entry - float(last['low']))
        mfe = max(mfe, float(last['high']) - order_entry)
    nu = _net_usd('long', order_entry, float(eod_px))
    exit_ts = eod_ts if not pd.isna(eod_ts) else pd.NaT
    return AdaptiveSessionOutcome(
        session_day,
        'filled',
        london_low=L_box,
        london_high=H_box,
        entry_px=order_entry,
        exit_px=float(eod_px),
        result=result,
        net_usd=nu,
        mae_pts=mae,
        mfe_pts=mfe,
        ts_first_rth_high=first_high_ts,
        ts_fill=fill_ts,
        ts_exit=exit_ts,
        ref_high_at_fill=snap_rh_fill,
        ny_session_low_at_fill=snap_ny_fill,
        effective_low_at_fill=snap_eff_fill,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument('--fib', type=float, default=PHI_INV, help='Fib retracement from H_ref toward L_eff')
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m CSV {args.m1}', file=sys.stderr)
        return 1

    fib_ratio = float(args.fib)
    if not (0.0 < fib_ratio < 1.0):
        print('--fib must be in (0,1)', file=sys.stderr)
        return 1

    if args.start and args.end:
        date_min = pd.Timestamp(args.start).date()
        date_max = pd.Timestamp(args.end).date()
    else:
        date_min, date_max = scan_date_range(args.m1, args.start, args.end)

    by_day = load_by_day(args.m1, date_min, date_max)

    outcomes: list[AdaptiveSessionOutcome] = []
    for session_day in sorted(by_day.keys()):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day]
        if day_b.empty:
            continue
        outcomes.append(simulate_session_adaptive(day_b, session_day, fib_ratio=fib_ratio))

    n_eligible = sum(1 for o in outcomes if o.status != 'no_london_box')
    n_no_box = sum(1 for o in outcomes if o.status == 'no_london_box')
    n_no_high = sum(1 for o in outcomes if o.status == 'no_rth_high_touch')
    n_abort = sum(1 for o in outcomes if o.status == 'aborted_floor_before_fill')
    n_no_fill = sum(1 for o in outcomes if o.status == 'no_fill_eod')
    filled = [o for o in outcomes if o.status == 'filled']

    print('=== Fib adaptive levels — min(London_low, RTH low), HH fib reset, dynamic SL ===')
    print(f'Date range: {date_min} .. {date_max}')
    print(f'Fib ratio: {fib_ratio:.6f}')
    print(f'Weekday sessions scanned: {len(outcomes)}')
    print(f'  Valid London box [02:00,09:30): {n_eligible}')
    print(f'  Missing London box: {n_no_box}')
    print(f'  RTH never touched London high: {n_no_high}')
    print(f'  After arm: effective floor before fill / degenerate range: {n_abort}')
    print(f'  After arm: limit never filled by 16:00: {n_no_fill}')
    print(f'  Filled trades: {len(filled)}')

    if filled:
        nets = pd.Series([float(o.net_usd) for o in filled])
        wins = sum(1 for o in filled if str(o.result) == 'Win')
        losses = sum(1 for o in filled if str(o.result) == 'Loss')
        eod_w = sum(1 for o in filled if str(o.result) == 'EOD-Win')
        eod_l = sum(1 for o in filled if str(o.result) == 'EOD-Loss')
        eod_f = sum(1 for o in filled if str(o.result) == 'EOD-Flat')
        be = sum(1 for o in filled if str(o.result) == 'Stop-BE')

        print('\n--- Filled trade outcomes ---')
        print(f'  TP at London high (Win): {wins}')
        print(f'  SL at effective floor (Loss): {losses}')
        print(f'  Stop-BE: {be}')
        print(f'  EOD exit — Win / Loss / Flat: {eod_w} / {eod_l} / {eod_f}')
        print(f'  Win rate (strict TP only): {100.0 * wins / len(filled):.2f}%')
        print(f'  Win rate (TP + EOD-Win): {100.0 * (wins + eod_w) / len(filled):.2f}%')
        print(f'  Mean net $/trade: {nets.mean():.2f}')
        print(f'  Sum net $: {nets.sum():.2f}')
        eq = nets.cumsum()
        max_dd = float((eq - eq.cummax()).min())
        print(f'  Max drawdown $ (filled trades): {max_dd:.2f}')
        print(f'  Mean MAE pts: {pd.Series([o.mae_pts for o in filled]).mean():.3f}')
        print(f'  Mean MFE pts: {pd.Series([o.mfe_pts for o in filled]).mean():.3f}')

    if n_eligible:
        armed = n_eligible - n_no_high
        print('\n--- Rates vs eligible sessions ---')
        print(f'  Armed (London high touched in RTH): {100.0 * armed / n_eligible:.2f}%')
        print(f'  Filled / eligible: {100.0 * len(filled) / n_eligible:.2f}%')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
