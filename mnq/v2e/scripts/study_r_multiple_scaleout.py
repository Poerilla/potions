#!/usr/bin/env python3
"""
Study (no chart updates):

1. **3R before SL** — Among fills from the bullish / bearish sweep-breaker models (stop at
   ``stop_hunter_low`` / ``stop_hunter_high``), how often does price touch **3×R** (where
   **R = |entry − stop|**) **before** the stop level, using the same pessimistic same-bar rule as the backtest
   (stop wins if both touch one bar).

2. **Scale-out (2 MNQ)** — Enter **2** contracts at the model fill; exit **1** at **+1R** (long: ``entry+R``,
   short: ``entry−R``); move runner stop to **breakeven at entry** (same price as the limit fill).
   Compare runner flat at **2R** vs runner held to **EOD** (last RTH close before 16:00 after cutoff).

Economics: **\$2**/point/**contract**; **\$3** round-trip fees assumed per completed trade (two contracts).

Run::

  cd potions/mnq/v2e/scripts
  python3 study_r_multiple_scaleout.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

V2E_SCRIPTS = Path(__file__).resolve().parent
V2E_ROOT = V2E_SCRIPTS.parent
MNQ_ROOT = V2E_ROOT.parent
BEAR_SCRIPTS = V2E_ROOT / 'bearish' / 'scripts'
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(BEAR_SCRIPTS), str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402

import backtest_london_sweep_breaker as bull_bt  # noqa: E402
import backtest_london_sweep_breaker_short as bear_bt  # noqa: E402

MULT = 2.0  # $/point/contract
FEE_2LOT = 3.0  # $1.50 × 2 MNQ per completed trade (study assumption)
_EPS = 1e-12


def iter_days(raw_by_day: dict) -> list[date]:
    return sorted(d for d in raw_by_day if d.weekday() < 5)


def bars_from_fill(
    day_1m: pd.DataFrame, session_day: date, ts_order: list, fill_i: int
) -> list[tuple]:
    out: list[tuple] = []
    for k in range(fill_i, len(ts_order)):
        ts = ts_order[k]
        if ts.date() != session_day:
            continue
        if ts.time() >= bull_bt.EOD_CUTOFF:
            break
        row = day_1m.loc[ts]
        out.append((ts, float(row['high']), float(row['low']), float(row['close'])))
    return out


def eod_close_long(day_1m: pd.DataFrame, session_day: date) -> float | None:
    tail = day_1m[
        day_1m.index.map(lambda t: t.date() == session_day and t.time() < bull_bt.RTH_HI)
    ]
    if tail.empty:
        return None
    return float(tail.iloc[-1]['close'])


def hit_3r_before_stop_long(
    bars: list[tuple], entry: float, stop_px: float, R: float
) -> bool | None:
    """True if 3R touched before stop; False if stop first or neither by session end; None invalid R."""
    if R <= _EPS:
        return None
    tgt = entry + 3 * R
    for _ts, h, l, _c in bars:
        hit_stop = l <= stop_px + _EPS
        hit_t = h >= tgt - _EPS
        if hit_stop and hit_t:
            return False
        if hit_stop:
            return False
        if hit_t:
            return True
    return False


def hit_3r_before_stop_short(
    bars: list[tuple], entry: float, stop_px: float, R: float
) -> bool | None:
    if R <= _EPS:
        return None
    tgt = entry - 3 * R
    for _ts, h, l, _c in bars:
        hit_stop = h >= stop_px - _EPS
        hit_t = l <= tgt + _EPS
        if hit_stop and hit_t:
            return False
        if hit_stop:
            return False
        if hit_t:
            return True
    return False


@dataclass
class ScaleOutResult:
    net_usd: float
    outcome: str


def scale_out_long(
    day_1m: pd.DataFrame,
    session_day: date,
    ts_order: list,
    fill_i: int,
    entry: float,
    stop_px: float,
    runner_exit: str,
) -> ScaleOutResult | None:
    """runner_exit: '2r' or 'eod'. Runner BE = entry. If '2r' never touches, runner exits EOD."""
    R = entry - stop_px
    if R <= _EPS:
        return None
    tgt_1r = entry + R
    tgt_2r = entry + 2 * R
    qty = 2
    runner_stop = stop_px
    pts_sum = 0.0

    bars = bars_from_fill(day_1m, session_day, ts_order, fill_i)

    for _ts, h, l, _c in bars:
        if qty == 2:
            if l <= stop_px + _EPS:
                pts_sum = 2 * (stop_px - entry)
                return ScaleOutResult(
                    net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                    outcome='full_stop_pre_scale',
                )
            if h >= tgt_1r - _EPS:
                pts_sum += 1 * (tgt_1r - entry)
                qty = 1
                runner_stop = entry
                if l <= entry + _EPS:
                    return ScaleOutResult(
                        net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                        outcome='scaled_be_same_bar',
                    )
                if runner_exit == '2r' and h >= tgt_2r - _EPS:
                    pts_sum += 1 * (tgt_2r - entry)
                    return ScaleOutResult(
                        net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                        outcome='scaled_2r_same_bar',
                    )
        if qty == 1:
            if l <= runner_stop + _EPS:
                pts_sum += 1 * (runner_stop - entry)
                return ScaleOutResult(
                    net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                    outcome='runner_stop_be',
                )
            if runner_exit == '2r' and h >= tgt_2r - _EPS:
                pts_sum += 1 * (tgt_2r - entry)
                return ScaleOutResult(
                    net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                    outcome='runner_2r',
                )

    ec = eod_close_long(day_1m, session_day)
    if ec is None:
        return None
    if qty == 2:
        pts_sum = 2 * (ec - entry)
        return ScaleOutResult(
            net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
            outcome='eod_2lot_no_scale',
        )
    pts_sum += 1 * (ec - entry)
    lab = 'runner_eod' if runner_exit == 'eod' else 'runner_eod_fallback_no_2r'
    return ScaleOutResult(net_usd=round(pts_sum * MULT - FEE_2LOT, 2), outcome=lab)


def scale_out_short(
    day_1m: pd.DataFrame,
    session_day: date,
    ts_order: list,
    fill_i: int,
    entry: float,
    stop_px: float,
    runner_exit: str,
) -> ScaleOutResult | None:
    R = stop_px - entry
    if R <= _EPS:
        return None
    tgt_1r = entry - R
    tgt_2r = entry - 2 * R
    qty = 2
    runner_stop = stop_px
    pts_sum = 0.0

    bars = bars_from_fill(day_1m, session_day, ts_order, fill_i)

    for _ts, h, l, _c in bars:
        if qty == 2:
            if h >= stop_px - _EPS:
                pts_sum = 2 * (entry - stop_px)
                return ScaleOutResult(
                    net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                    outcome='full_stop_pre_scale',
                )
            if l <= tgt_1r + _EPS:
                pts_sum += 1 * (entry - tgt_1r)
                qty = 1
                runner_stop = entry
                if h >= entry - _EPS:
                    return ScaleOutResult(
                        net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                        outcome='scaled_be_same_bar',
                    )
                if runner_exit == '2r' and l <= tgt_2r + _EPS:
                    pts_sum += 1 * (entry - tgt_2r)
                    return ScaleOutResult(
                        net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                        outcome='scaled_2r_same_bar',
                    )
        if qty == 1:
            if h >= runner_stop - _EPS:
                pts_sum += 1 * (entry - runner_stop)
                return ScaleOutResult(
                    net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                    outcome='runner_stop_be',
                )
            if runner_exit == '2r' and l <= tgt_2r + _EPS:
                pts_sum += 1 * (entry - tgt_2r)
                return ScaleOutResult(
                    net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
                    outcome='runner_2r',
                )

    ec = eod_close_long(day_1m, session_day)
    if ec is None:
        return None
    if qty == 2:
        pts_sum = 2 * (entry - ec)
        return ScaleOutResult(
            net_usd=round(pts_sum * MULT - FEE_2LOT, 2),
            outcome='eod_2lot_no_scale',
        )
    pts_sum += 1 * (entry - ec)
    lab = 'runner_eod' if runner_exit == 'eod' else 'runner_eod_fallback_no_2r'
    return ScaleOutResult(net_usd=round(pts_sum * MULT - FEE_2LOT, 2), outcome=lab)


def hold_2_to_model_tp_long(
    day_1m: pd.DataFrame,
    session_day: date,
    ts_order: list,
    fill_i: int,
    entry: float,
    stop_px: float,
    tp_px: float,
) -> float | None:
    """Net USD for 2 MNQ held to model TP or stopped (pessimistic bar logic)."""
    bars = bars_from_fill(day_1m, session_day, ts_order, fill_i)
    for _ts, h, l, _c in bars:
        hit_stop = l <= stop_px + _EPS
        hit_tp = h >= tp_px - _EPS
        if hit_stop and hit_tp:
            pts = 2 * (stop_px - entry)
            return round(pts * MULT - FEE_2LOT, 2)
        if hit_stop:
            pts = 2 * (stop_px - entry)
            return round(pts * MULT - FEE_2LOT, 2)
        if hit_tp:
            pts = 2 * (tp_px - entry)
            return round(pts * MULT - FEE_2LOT, 2)
    ec = eod_close_long(day_1m, session_day)
    if ec is None:
        return None
    pts = 2 * (ec - entry)
    return round(pts * MULT - FEE_2LOT, 2)


def hold_2_to_model_tp_short(
    day_1m: pd.DataFrame,
    session_day: date,
    ts_order: list,
    fill_i: int,
    entry: float,
    stop_px: float,
    tp_px: float,
) -> float | None:
    bars = bars_from_fill(day_1m, session_day, ts_order, fill_i)
    for _ts, h, l, _c in bars:
        hit_stop = h >= stop_px - _EPS
        hit_tp = l <= tp_px + _EPS
        if hit_stop and hit_tp:
            pts = 2 * (entry - stop_px)
            return round(pts * MULT - FEE_2LOT, 2)
        if hit_stop:
            pts = 2 * (entry - stop_px)
            return round(pts * MULT - FEE_2LOT, 2)
        if hit_tp:
            pts = 2 * (entry - tp_px)
            return round(pts * MULT - FEE_2LOT, 2)
    ec = eod_close_long(day_1m, session_day)
    if ec is None:
        return None
    pts = 2 * (entry - ec)
    return round(pts * MULT - FEE_2LOT, 2)


def max_dd(nets: list[float]) -> float:
    if not nets:
        return 0.0
    s = pd.Series(nets).cumsum()
    return float((s - s.cummax()).min())


def main() -> int:
    m1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
    NY = bull_bt.NY
    chunks_for_max: date | None = None
    chunks_for_min: date | None = None
    for ch in pd.read_csv(m1, usecols=['ts_event'], chunksize=800_000):
        ch['ts_event'] = pd.to_datetime(ch['ts_event'], utc=True).dt.tz_convert(NY)
        dpart = ch['ts_event'].dt.date
        cmin, cmax = dpart.min(), dpart.max()
        chunks_for_min = cmin if chunks_for_min is None else min(chunks_for_min, cmin)
        chunks_for_max = cmax if chunks_for_max is None else max(chunks_for_max, cmax)
    assert chunks_for_min and chunks_for_max

    needed = {
        d for d in bull_bt.iter_calendar_dates(chunks_for_min, chunks_for_max) if d.weekday() < 5
    }
    raw = ann.load_1m_for_dates(str(m1), chunks_for_min, chunks_for_max, needed)
    raw = ann.pick_front_month_day(raw)
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw = raw.set_index('ts_event').sort_index()
    raw['__d'] = raw.index.date
    by_day = {d: g.drop(columns=['__d']) for d, g in raw.groupby('__d')}
    raw = raw.drop(columns=['__d'])

    bull_rows_3r: list[bool] = []
    bear_rows_3r: list[bool] = []
    bull_scale_2r: list[float] = []
    bull_scale_eod: list[float] = []
    bear_scale_2r: list[float] = []
    bear_scale_eod: list[float] = []
    bull_hold2: list[float] = []
    bear_hold2: list[float] = []

    for d in iter_days(by_day):
        day_b = by_day[d]
        ts_order = list(day_b.index)

        b_base = bull_bt.compute_setup(day_b, d)
        if b_base is not None:
            entry = float(b_base['entry'])
            stop_px = float(b_base['stop_hunter_low'])
            tp_px = float(b_base['tp_px'])
            fill_i = int(b_base['fill_i'])
            R = entry - stop_px
            bars = bars_from_fill(day_b, d, ts_order, fill_i)
            hit = hit_3r_before_stop_long(bars, entry, stop_px, R)
            if hit is not None:
                bull_rows_3r.append(hit)

            so2 = scale_out_long(day_b, d, ts_order, fill_i, entry, stop_px, '2r')
            soe = scale_out_long(day_b, d, ts_order, fill_i, entry, stop_px, 'eod')
            h2 = hold_2_to_model_tp_long(day_b, d, ts_order, fill_i, entry, stop_px, tp_px)
            if so2:
                bull_scale_2r.append(so2.net_usd)
            if soe:
                bull_scale_eod.append(soe.net_usd)
            if h2 is not None:
                bull_hold2.append(h2)

        s_base = bear_bt.compute_setup_short(day_b, d)
        if s_base is not None:
            entry = float(s_base['entry'])
            stop_px = float(s_base['stop_hunter_high'])
            tp_px = float(s_base['tp_px'])
            fill_i = int(s_base['fill_i'])
            R = stop_px - entry
            bars = bars_from_fill(day_b, d, ts_order, fill_i)
            hit = hit_3r_before_stop_short(bars, entry, stop_px, R)
            if hit is not None:
                bear_rows_3r.append(hit)

            so2 = scale_out_short(day_b, d, ts_order, fill_i, entry, stop_px, '2r')
            soe = scale_out_short(day_b, d, ts_order, fill_i, entry, stop_px, 'eod')
            h2 = hold_2_to_model_tp_short(day_b, d, ts_order, fill_i, entry, stop_px, tp_px)
            if so2:
                bear_scale_2r.append(so2.net_usd)
            if soe:
                bear_scale_eod.append(soe.net_usd)
            if h2 is not None:
                bear_hold2.append(h2)

    def pct_true(xs: list[bool]) -> float:
        if not xs:
            return float('nan')
        return sum(1 for z in xs if z) / len(xs) * 100

    print('=== Study: R-multiples & 2-MNQ scale-out ===\n')
    print(f'Date span: {chunks_for_min} .. {chunks_for_max}')
    print('R = |entry − stop_hunter|; pessimistic bar: stop wins if both touch.\n')

    print('--- 3R touched BEFORE stop (among sessions with valid R & setup) ---')
    print(f'Bullish:  n={len(bull_rows_3r)}  hit 3R first={pct_true(bull_rows_3r):.2f}%')
    print(f'Bearish: n={len(bear_rows_3r)}  hit 3R first={pct_true(bear_rows_3r):.2f}%\n')

    def block(name: str, nets: list[float]) -> None:
        if not nets:
            print(f'{name}: no trades')
            return
        s = sum(nets)
        wr = sum(1 for x in nets if x > 0) / len(nets) * 100
        print(f'{name}:')
        print(f'  n={len(nets)}  Σ Net=${s:,.2f}  WR(net>0)={wr:.2f}%  max DD=${max_dd(nets):,.2f}')

    print('--- 2 MNQ scale-out: −1 at +1R, runner BE at entry; fees $3/trade ---')
    block('Bull scale runner exit @ 2R', bull_scale_2r)
    block('Bull scale runner → EOD close', bull_scale_eod)
    block('Bear scale runner exit @ 2R', bear_scale_2r)
    block('Bear scale runner → EOD close', bear_scale_eod)

    print('\n--- Reference: 2 MNQ hold to **model TP** (same pessimistic bar priority) ---')
    block('Bull hold 2 @ model TP', bull_hold2)
    block('Bear hold 2 @ model TP', bear_hold2)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
