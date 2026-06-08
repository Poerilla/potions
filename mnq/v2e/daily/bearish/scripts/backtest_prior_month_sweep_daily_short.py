#!/usr/bin/env python3
"""
**Prior-month sweep → daily breaker → piercer → limit pullback** (short).

Mirror of ``daily/scripts/backtest_prior_month_sweep_daily_long.py`` with signs flipped:

- **Sweep level:** prior calendar month **high** (first daily in **current** month with ``high >= prior_month_high``).
- **Ordering:** earliest daily in **prior** month tagging that high must precede (index-wise) the first sweep.
- **Stop hunter:** **highest** ``high`` in segment (tie → earliest day).
- **Breaker:** last strict **daily** swing **low** through SH day + next row.
- **Piercer:** first swing **low** strictly after SH (within session month) with ``low < breaker_low``.
- **Entry:** limit **sell** at ``breaker_low``; fill when ``high >= breaker_low``.
- **TP:** ``stop_hunter_high - (stop_hunter_high - piercer_low) * 2``.
- **Post-fill:** pessimistic stop-before-TP on daily bars through **month-end**; short P/L = ``entry - exit``.

Example::

  cd potions/mnq/v2e/daily/bearish/scripts
  python3 backtest_prior_month_sweep_daily_short.py --all-sl
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

import pandas as pd

BEAR_SCRIPTS = Path(__file__).resolve().parent
DAILY_SCRIPTS = BEAR_SCRIPTS.parent.parent / 'scripts'

sys.path[:0] = [str(DAILY_SCRIPTS)]

from prior_month_sweep_daily_common import (  # noqa: E402
    DEFAULT_DAILY_DBN,
    in_month,
    load_mnq_front_daily,
    monthly_high_low,
    month_day_indices,
    pick_breaker_daily_short,
)

MULT = 2.0
FEE_RT = 1.50
_EPS = 1e-12


class SLMode(str, Enum):
    prior_month_high = 'prior_month_high'
    breaker_high = 'breaker_high'
    stop_hunter_high = 'stop_hunter_high'


@dataclass
class TradeResultShort:
    session_month: str
    fill_day: date
    entry: float
    exit_px: float
    net_usd: float
    mae_pts: float
    mfe_pts: float
    result: str
    sl_mode: str
    prior_month_high: float
    breaker_high: float
    breaker_low: float
    stop_hunter_high: float
    piercer_low: float
    tp_px: float
    stop_px: float
    breaker_day_idx: int


def prev_calendar_month(y: int, m: int) -> tuple[int, int]:
    if m <= 1:
        return y - 1, 12
    return y, m - 1


def indices_for_month(
    ranges: dict[tuple[int, int], tuple[int, int]], y: int, m: int
) -> tuple[list[int], int, int] | None:
    if (y, m) not in ranges:
        return None
    lo, hi = ranges[(y, m)]
    return list(range(lo, hi + 1)), lo, hi


def pm_high_first_touch(prev_idxs: list[int], highs: list[float], pm_h: float) -> int | None:
    first: int | None = None
    for i in prev_idxs:
        if highs[i] >= pm_h - _EPS:
            first = i if first is None else min(first, i)
    return first


def find_setup_short_month(
    dates: list[date],
    highs: list[float],
    lows: list[float],
    y: int,
    m: int,
    month_start_idx: int,
    month_end_idx: int,
    prev_idxs: list[int],
    pm_h: float,
) -> dict | None:
    win_start = pm_high_first_touch(prev_idxs, highs, pm_h)
    if win_start is None:
        return None

    first_sweep_i: int | None = None
    for i in range(month_start_idx, month_end_idx + 1):
        if highs[i] >= pm_h - _EPS:
            first_sweep_i = i
            break
    if first_sweep_i is None:
        return None

    if win_start >= first_sweep_i:
        return None

    sh_i = first_sweep_i
    breaker_high = 0.0
    breaker_low = 0.0
    breaker_day_idx = month_start_idx
    piercer_i: int | None = None

    for _ in range(30):
        brk = pick_breaker_daily_short(dates, highs, lows, y, m, month_start_idx, sh_i)
        if brk is None:
            return None
        breaker_high, breaker_low, breaker_day_idx = brk

        piercer_i = None
        for i in range(sh_i + 1, month_end_idx):
            if i < 1 or i >= len(lows) - 1:
                continue
            if not (
                in_month(dates[i - 1], y, m)
                and in_month(dates[i], y, m)
                and in_month(dates[i + 1], y, m)
            ):
                continue
            if lows[i] + _EPS < lows[i - 1] and lows[i] + _EPS < lows[i + 1]:
                if lows[i] + _EPS < breaker_low:
                    piercer_i = i
                    break
        if piercer_i is None or piercer_i <= first_sweep_i:
            return None

        segment = range(first_sweep_i, piercer_i)
        sh_next = min(segment, key=lambda k: (-highs[k], k))
        if sh_next == sh_i:
            break
        sh_i = sh_next
    else:
        return None

    fill_i = None
    for j in range(piercer_i + 1, month_end_idx + 1):
        if highs[j] >= breaker_low - _EPS:
            fill_i = j
            break
    if fill_i is None:
        return None

    piercer_low = lows[piercer_i]

    return {
        'sh_i': sh_i,
        'piercer_i': piercer_i,
        'breaker_high': breaker_high,
        'breaker_low': breaker_low,
        'breaker_day_idx': breaker_day_idx,
        'stop_hunter_high': highs[sh_i],
        'piercer_low': piercer_low,
        'fill_i': fill_i,
        'pm_h': pm_h,
    }


def simulate_trade_short_daily(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    fill_idx: int,
    month_trade_end_idx: int,
    entry: float,
    stop_px: float,
    tp_px: float,
) -> tuple[float, float, float, str]:
    mae = 0.0
    mfe = 0.0
    end_j = min(month_trade_end_idx, len(highs) - 1)
    for j in range(fill_idx, end_j + 1):
        h = highs[j]
        lo = lows[j]
        mae = max(mae, h - entry)
        mfe = max(mfe, entry - lo)
        both_stop = h >= stop_px - _EPS
        both_tp = lo <= tp_px + _EPS
        if both_stop and both_tp:
            return stop_px, mae, mfe, 'Loss' if stop_px > entry + _EPS else 'Stop-BE'
        if both_stop:
            return stop_px, mae, mfe, 'Loss' if stop_px > entry + _EPS else 'Stop-BE'
        if both_tp:
            return tp_px, mae, mfe, 'Win'

    eod = float(closes[end_j])
    mae = max(mae, highs[end_j] - entry)
    mfe = max(mfe, entry - lows[end_j])
    pl = entry - eod
    if pl > _EPS:
        lab = 'EOM-Win'
    elif pl < -_EPS:
        lab = 'EOM-Loss'
    else:
        lab = 'EOM-Flat'
    return eod, mae, mfe, lab


def compute_setup_month(
    dates: list[date],
    highs: list[float],
    lows: list[float],
    monthly: pd.DataFrame,
    ranges: dict[tuple[int, int], tuple[int, int]],
    y: int,
    m: int,
) -> dict | None:
    py, pm = prev_calendar_month(y, m)
    if (py, pm) not in monthly.index:
        return None
    pm_h = float(monthly.loc[(py, pm), 'm_high'])

    prev_pack = indices_for_month(ranges, py, pm)
    cur_pack = indices_for_month(ranges, y, m)
    if prev_pack is None or cur_pack is None:
        return None
    prev_idxs, _plo, _phi = prev_pack
    _cur_list, month_start_idx, month_end_idx = cur_pack

    base = find_setup_short_month(
        dates,
        highs,
        lows,
        y,
        m,
        month_start_idx,
        month_end_idx,
        prev_idxs,
        pm_h,
    )
    if base is None:
        return None

    entry = float(base['breaker_low'])
    tp_px = float(base['stop_hunter_high']) - (
        float(base['stop_hunter_high']) - float(base['piercer_low'])
    ) * 2.0
    if tp_px >= entry - _EPS:
        return None

    return {
        **base,
        'tp_px': tp_px,
        'entry': entry,
        'month_end_idx': month_end_idx,
        'session_y': y,
        'session_m': m,
    }


def finalize_trade(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    dates: list[date],
    base: dict,
    sl_mode: SLMode,
) -> TradeResultShort | None:
    pm_h = float(base['pm_h'])
    entry = float(base['entry'])
    tp_px = float(base['tp_px'])
    fill_i = int(base['fill_i'])
    month_end_idx = int(base['month_end_idx'])
    y, m = int(base['session_y']), int(base['session_m'])

    if sl_mode == SLMode.prior_month_high:
        stop_px = pm_h
    elif sl_mode == SLMode.breaker_high:
        stop_px = float(base['breaker_high'])
    else:
        stop_px = float(base['stop_hunter_high'])

    if entry >= stop_px - _EPS:
        return None

    exit_px, mae, mfe, res = simulate_trade_short_daily(
        highs, lows, closes, fill_i, month_end_idx, entry, stop_px, tp_px
    )

    pnl_pts = entry - exit_px
    net_usd = round(pnl_pts * MULT - FEE_RT, 2)

    return TradeResultShort(
        session_month=f'{y:04d}-{m:02d}',
        fill_day=dates[fill_i],
        entry=entry,
        exit_px=exit_px,
        net_usd=net_usd,
        mae_pts=round(mae, 4),
        mfe_pts=round(mfe, 4),
        result=res,
        sl_mode=sl_mode.value,
        prior_month_high=pm_h,
        breaker_high=float(base['breaker_high']),
        breaker_low=float(base['breaker_low']),
        stop_hunter_high=float(base['stop_hunter_high']),
        piercer_low=float(base['piercer_low']),
        tp_px=tp_px,
        stop_px=stop_px,
        breaker_day_idx=int(base['breaker_day_idx']),
    )


def summarize(rows: list[TradeResultShort]) -> dict[str, float]:
    if not rows:
        return {
            'n': 0,
            'sum_net': 0.0,
            'wr': float('nan'),
            'max_dd': 0.0,
            'mean_mae': float('nan'),
        }
    nets = [r.net_usd for r in rows]
    cum = pd.Series(nets).cumsum()
    dd = float((cum - cum.cummax()).min())
    wins = sum(1 for r in rows if r.net_usd > 0)
    maes = [r.mae_pts for r in rows]
    return {
        'n': len(rows),
        'sum_net': float(sum(nets)),
        'wr': wins / len(rows) * 100,
        'max_dd': dd,
        'mean_mae': float(sum(maes) / len(maes)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DAILY_DBN)
    ap.add_argument('--start', type=str, default=None)
    ap.add_argument('--end', type=str, default=None)
    ap.add_argument(
        '--sl-at',
        choices=[x.value for x in SLMode],
        default=SLMode.stop_hunter_high.value,
    )
    ap.add_argument('--all-sl', action='store_true')
    ap.add_argument('--export-csv', type=Path, default=None)
    args = ap.parse_args()

    if not args.daily_dbn.is_file():
        print(f'Missing daily DBN {args.daily_dbn}', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)

    if args.start:
        daily = daily[daily.index >= pd.to_datetime(args.start)]
    if args.end:
        daily = daily[daily.index <= pd.to_datetime(args.end)]
    if daily.empty:
        print('No rows after date filter.', file=sys.stderr)
        return 1

    dates = [pd.Timestamp(x).date() for x in daily.index]
    highs = [float(x) for x in daily['high'].tolist()]
    lows = [float(x) for x in daily['low'].tolist()]
    closes = [float(x) for x in daily['close'].tolist()]

    monthly = monthly_high_low(daily)
    ranges = month_day_indices(dates)

    modes = list(SLMode) if args.all_sl else [SLMode(args.sl_at)]
    buckets: dict[SLMode, list[TradeResultShort]] = {sm: [] for sm in modes}

    months_seen = sorted({(d.year, d.month) for d in dates})

    for y, m in months_seen:
        base = compute_setup_month(dates, highs, lows, monthly, ranges, y, m)
        if base is None:
            continue
        for sm in modes:
            tr = finalize_trade(highs, lows, closes, dates, base, sm)
            if tr is not None:
                buckets[sm].append(tr)

    print('Prior-month sweep → daily breaker → piercer → limit (short)')
    for sm in modes:
        st = summarize(buckets[sm])
        print(f'\n--- SL = {sm.value} ---')
        print(f'Months with trade: {st["n"]}')
        print(f'Σ Net USD (1 MNQ): ${st["sum_net"]:,.2f}')
        print(f'Win rate (Net > 0): {st["wr"]:.2f}%')
        print(f'Max DD (leg cumulative): ${st["max_dd"]:,.2f}')
        print(f'Mean MAE (pts): {st["mean_mae"]:.4f}')
        eff = st['sum_net'] / abs(st['max_dd']) if st['max_dd'] else float('nan')
        print(f'Σ Net / |max DD|: {eff:.3f}')

    print(f'\nDate range in daily frame: {dates[0]} .. {dates[-1]}')

    trades_final = buckets[SLMode(args.sl_at)]
    if args.export_csv:
        cols = [
            'session_month',
            'fill_day',
            'entry',
            'exit_px',
            'net_usd',
            'mae_pts',
            'mfe_pts',
            'result',
            'sl_mode',
            'prior_month_high',
            'breaker_high',
            'breaker_low',
            'stop_hunter_high',
            'piercer_low',
            'tp_px',
            'stop_px',
            'breaker_day_idx',
        ]
        pd.DataFrame([{k: getattr(r, k) for k in cols} for r in trades_final]).to_csv(
            args.export_csv, index=False
        )
        print(f'Wrote {args.export_csv}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
