#!/usr/bin/env python3
"""
**London sweep → breaker → piercer → limit pullback** (short only, **no ORB**).

Mirror of the bullish v2e model with signs reversed (NY time, 1 m MNQ):

- **London box:** **[02:00, 09:30)** — **London high** = maximum ``high``.
- **london_high_time:** earliest London bar whose ``high`` tags ``London_high``.
- **First RTH sweep:** first **[09:30, 16:00)** bar with ``high >= London_high``.
- **stop_hunter:** fixed-point like the long side but on **highs**: among bars from first sweep **through**
  index ``piercer_i - 1``, move SH to the bar with the **highest** ``high`` (tie → earliest). Recompute **breaker**
  (5 m swing **low** window through candle after SH bucket) and **piercer** each pass (max 30).
- **Breaker:** last strict **5 m swing low** from **02:00** through the **5 m candle after** the SH bucket (inclusive window on centers).
- **Piercer:** first **1 m** swing strictly **after** SH with ``low < breaker_low``.
- **Entry:** **limit sell** at ``breaker_low``; fill when ``high >= breaker_low``.
- **Stop:** ``London_high``, **breaker** ``high``, or **stop_hunter** candle ``high``.
- **TP:** ``stop_hunter_high - (stop_hunter_high - piercer_low) * 2`` (symmetric projection down).

Fees: **\$1.50** RT/MNQ; **\$2**/point; short P/L in points = entry minus exit.

Example::

  cd potions/mnq/v2e/bearish/scripts
  python3 backtest_london_sweep_breaker_short.py --all-sl
  python3 backtest_london_sweep_breaker_short.py --sl-at stop_hunter_high --export-csv ../data/mnq_v2e_london_sweep_breaker_bearish.csv
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytz

BEAR_ROOT = Path(__file__).resolve().parent.parent
V2E_ROOT = BEAR_ROOT.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402

NY = pytz.timezone('America/New_York')
LDN_LO = time(2, 0)
LDN_HI = time(9, 30)
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
EOD_CUTOFF = time(15, 59)

MULT = 2.0
FEE_RT = 1.50
_EPS = 1e-12


class SLMode(str, Enum):
    london_high = 'london_high'
    breaker_high = 'breaker_high'
    stop_hunter_high = 'stop_hunter_high'


def london_low_high(day_1m: pd.DataFrame, session_day: date) -> tuple[float, float]:
    b = day_1m[
        day_1m.index.map(
            lambda t: t.date() == session_day and LDN_LO <= t.time() < LDN_HI
        )
    ]
    if b.empty:
        return float('nan'), float('nan')
    return float(b['low'].min()), float(b['high'].max())


def london_high_first_touch_index(
    session_day: date,
    ldn_h: float,
    ts_list: list[pd.Timestamp],
    highs: list[float],
) -> int | None:
    """Earliest London-window bar on session_day whose high tags London_high."""
    first: int | None = None
    for i, t in enumerate(ts_list):
        if t.date() != session_day:
            continue
        if not (LDN_LO <= t.time() < LDN_HI):
            continue
        if highs[i] >= ldn_h - _EPS:
            first = i if first is None else min(first, i)
    return first


def iter_calendar_dates(dmin: date, dmax: date) -> Iterator[date]:
    cur = pd.Timestamp(dmin)
    end = pd.Timestamp(dmax)
    while cur <= end:
        yield cur.date()
        cur += pd.Timedelta(days=1)


@dataclass
class TradeResultShort:
    session_day: date
    entry: float
    exit_px: float
    net_usd: float
    mae_pts: float
    mfe_pts: float
    result: str
    sl_mode: str
    london_high: float
    london_low: float
    breaker_high: float
    breaker_low: float
    stop_hunter_high: float
    piercer_low: float
    tp_px: float
    stop_px: float
    breaker_5m_left: str


def resample_session_5m_from_02(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    sub = day_1m[
        day_1m.index.map(
            lambda t: t.date() == session_day and LDN_LO <= t.time() < RTH_HI
        )
    ].sort_index()
    if sub.empty:
        return sub
    anchor = NY.localize(datetime.combine(session_day, LDN_LO))
    return (
        sub.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def pick_breaker_5m_last_swing_low_through_after_sh_bucket(
    bars5: pd.DataFrame,
    session_day: date,
    ts_stop_hunter_open: pd.Timestamp,
) -> tuple[float, float, pd.Timestamp] | None:
    """Strict swing lows through 5 m bar after SH bucket; breaker bar = last chronologically."""
    if len(bars5) < 3:
        return None
    ts_sh = pd.Timestamp(ts_stop_hunter_open)
    if bars5.index.tz is not None:
        if ts_sh.tzinfo is None:
            ts_sh = ts_sh.tz_localize(bars5.index.tz)
        else:
            ts_sh = ts_sh.tz_convert(bars5.index.tz)

    idxs = bars5.index.to_list()
    highs5 = bars5['high'].astype(float).to_numpy()
    lows5 = bars5['low'].astype(float).to_numpy()
    five = pd.Timedelta(minutes=5)

    london_open = NY.localize(datetime.combine(session_day, LDN_LO))

    sh_bucket_left: pd.Timestamp | None = None
    for bl in idxs:
        if bl <= ts_sh < bl + five:
            sh_bucket_left = bl
            break
    if sh_bucket_left is None:
        return None

    after_left = sh_bucket_left + five

    swings: list[tuple[pd.Timestamp, float, float]] = []
    for k in range(1, len(idxs) - 1):
        if not (
            lows5[k] + _EPS < lows5[k - 1] and lows5[k] + _EPS < lows5[k + 1]
        ):
            continue
        bl = idxs[k]
        if bl < london_open or bl > after_left:
            continue
        swings.append((bl, float(highs5[k]), float(lows5[k])))

    if not swings:
        return None
    bar_left, breaker_high, breaker_low = swings[-1]
    return breaker_high, breaker_low, bar_left


def find_setup_short(
    session_day: date,
    ldn_h: float,
    day_1m: pd.DataFrame,
) -> dict | None:
    ts_list = list(day_1m.index)
    highs = [float(x) for x in day_1m['high'].tolist()]
    lows = [float(x) for x in day_1m['low'].tolist()]
    n = len(ts_list)
    if n < 5:
        return None

    first_sweep_i: int | None = None
    for i in range(n):
        t = ts_list[i]
        if t.date() != session_day:
            continue
        if not (RTH_LO <= t.time() < RTH_HI):
            continue
        if highs[i] >= ldn_h - _EPS:
            first_sweep_i = i
            break
    if first_sweep_i is None:
        return None

    win_start = london_high_first_touch_index(session_day, ldn_h, ts_list, highs)
    if win_start is None or win_start >= first_sweep_i:
        return None

    bars5 = resample_session_5m_from_02(day_1m, session_day)
    if len(bars5) < 3:
        return None

    sh_i = first_sweep_i
    breaker_high = 0.0
    breaker_low = 0.0
    breaker_5m_left = ts_list[first_sweep_i]
    piercer_i: int | None = None

    for _ in range(30):
        brk = pick_breaker_5m_last_swing_low_through_after_sh_bucket(
            bars5, session_day, ts_list[sh_i]
        )
        if brk is None:
            return None
        breaker_high, breaker_low, breaker_5m_left = brk

        piercer_i = None
        for i in range(sh_i + 1, n - 1):
            if (
                ts_list[i - 1].date() != session_day
                or ts_list[i].date() != session_day
                or ts_list[i + 1].date() != session_day
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
    for j in range(piercer_i + 1, n):
        if ts_list[j].date() != session_day:
            continue
        if ts_list[j].time() >= EOD_CUTOFF:
            break
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
        'breaker_5m_left': breaker_5m_left,
        'stop_hunter_high': highs[sh_i],
        'piercer_low': piercer_low,
        'fill_i': fill_i,
    }


def simulate_trade_short_with_close(
    day_1m: pd.DataFrame,
    session_day: date,
    start_i: int,
    entry: float,
    stop_px: float,
    tp_px: float,
    ts_order: list[pd.Timestamp],
) -> tuple[float, float, float, str]:
    """Short: favorable P/L when exit < entry; stop above entry; TP below."""
    path = day_1m.loc[ts_order[start_i] :].sort_index()
    mae = 0.0
    mfe = 0.0
    for ts, bar in path.iterrows():
        if ts.date() != session_day:
            continue
        if ts.time() >= EOD_CUTOFF:
            break
        h = float(bar['high'])
        l = float(bar['low'])
        mae = max(mae, h - entry)
        mfe = max(mfe, entry - l)
        both_stop = h >= stop_px - _EPS
        both_tp = l <= tp_px + _EPS
        if both_stop and both_tp:
            return stop_px, mae, mfe, 'Loss' if stop_px > entry + _EPS else 'Stop-BE'
        if both_stop:
            return stop_px, mae, mfe, 'Loss' if stop_px > entry + _EPS else 'Stop-BE'
        if both_tp:
            return tp_px, mae, mfe, 'Win'

    tail = day_1m[
        day_1m.index.map(lambda t: t.date() == session_day and t.time() < RTH_HI)
    ]
    if tail.empty:
        return entry, mae, mfe, 'no_data'
    eod = float(tail.iloc[-1]['close'])
    mae = max(mae, float(tail.iloc[-1]['high']) - entry)
    mfe = max(mfe, entry - float(tail.iloc[-1]['low']))
    pl = entry - eod
    if pl > _EPS:
        lab = 'EOD-Win'
    elif pl < -_EPS:
        lab = 'EOD-Loss'
    else:
        lab = 'EOD-Flat'
    return eod, mae, mfe, lab


def compute_setup_short(day_1m: pd.DataFrame, session_day: date) -> dict | None:
    ldn_l, ldn_h = london_low_high(day_1m, session_day)
    if math.isnan(ldn_h):
        return None

    ts_order = list(day_1m.index)

    setup = find_setup_short(session_day, ldn_h, day_1m)
    if setup is None:
        return None

    stop_hunter_high = setup['stop_hunter_high']
    piercer_low = setup['piercer_low']

    tp_px = stop_hunter_high - (stop_hunter_high - piercer_low) * 2.0
    entry = setup['breaker_low']

    if tp_px >= entry - _EPS:
        return None

    return {
        **setup,
        'ldn_l': ldn_l,
        'ldn_h': ldn_h,
        'tp_px': tp_px,
        'entry': entry,
        'ts_order': ts_order,
    }


def finalize_trade_short(
    day_1m: pd.DataFrame,
    session_day: date,
    base: dict,
    sl_mode: SLMode,
) -> TradeResultShort | None:
    ldn_h = float(base['ldn_h'])
    ldn_l = float(base['ldn_l'])
    entry = float(base['entry'])
    tp_px = float(base['tp_px'])
    ts_order = base['ts_order']

    if sl_mode == SLMode.london_high:
        stop_px = ldn_h
    elif sl_mode == SLMode.breaker_high:
        stop_px = float(base['breaker_high'])
    else:
        stop_px = float(base['stop_hunter_high'])

    if stop_px <= entry + _EPS:
        return None

    exit_px, mae, mfe, res = simulate_trade_short_with_close(
        day_1m,
        session_day,
        base['fill_i'],
        entry,
        stop_px,
        tp_px,
        ts_order,
    )

    pnl_pts = entry - exit_px
    net_usd = round(pnl_pts * MULT - FEE_RT, 2)

    brk_left = base['breaker_5m_left']
    return TradeResultShort(
        session_day=session_day,
        entry=entry,
        exit_px=exit_px,
        net_usd=net_usd,
        mae_pts=round(mae, 4),
        mfe_pts=round(mfe, 4),
        result=res,
        sl_mode=sl_mode.value,
        london_high=ldn_h,
        london_low=ldn_l,
        breaker_high=float(base['breaker_high']),
        breaker_low=float(base['breaker_low']),
        stop_hunter_high=float(base['stop_hunter_high']),
        piercer_low=float(base['piercer_low']),
        tp_px=tp_px,
        stop_px=stop_px,
        breaker_5m_left=(
            brk_left.isoformat() if isinstance(brk_left, pd.Timestamp) else str(brk_left)
        ),
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
    ap.add_argument(
        '--1m',
        dest='m1',
        type=Path,
        default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv',
    )
    ap.add_argument('--start', type=str, default=None, help='YYYY-MM-DD inclusive')
    ap.add_argument('--end', type=str, default=None, help='YYYY-MM-DD inclusive')
    ap.add_argument(
        '--sl-at',
        choices=[x.value for x in SLMode],
        default=SLMode.stop_hunter_high.value,
        help='Short stop price source',
    )
    ap.add_argument('--all-sl', action='store_true')
    ap.add_argument('--export-csv', type=Path, default=None)
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m file {args.m1}', file=sys.stderr)
        return 1

    sl_mode = SLMode(args.sl_at)

    chunks_for_max: date | None = None
    chunks_for_min: date | None = None
    for ch in pd.read_csv(args.m1, usecols=['ts_event'], chunksize=800_000):
        ch['ts_event'] = pd.to_datetime(ch['ts_event'], utc=True).dt.tz_convert(NY)
        dpart = ch['ts_event'].dt.date
        cmin, cmax = dpart.min(), dpart.max()
        chunks_for_min = cmin if chunks_for_min is None else min(chunks_for_min, cmin)
        chunks_for_max = cmax if chunks_for_max is None else max(chunks_for_max, cmax)
    if chunks_for_max is None or chunks_for_min is None:
        print('Empty 1m file', file=sys.stderr)
        return 1
    date_min = chunks_for_min
    date_max = chunks_for_max
    if args.start:
        date_min = max(date_min, datetime.strptime(args.start, '%Y-%m-%d').date())
    if args.end:
        date_max = min(date_max, datetime.strptime(args.end, '%Y-%m-%d').date())

    needed = {d for d in iter_calendar_dates(date_min, date_max) if d.weekday() < 5}

    raw = ann.load_1m_for_dates(str(args.m1), date_min, date_max, needed)
    raw = ann.pick_front_month_day(raw)
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw = raw.set_index('ts_event').sort_index()

    raw['__d'] = raw.index.date
    by_day = {d: g.drop(columns=['__d'], errors='ignore') for d, g in raw.groupby('__d')}
    raw = raw.drop(columns=['__d'], errors='ignore')

    def collect_trades(selected_modes: list[SLMode]) -> dict[SLMode, list[TradeResultShort]]:
        buckets: dict[SLMode, list[TradeResultShort]] = {sm: [] for sm in selected_modes}
        for session_day in sorted(by_day.keys()):
            if session_day.weekday() >= 5:
                continue
            day_b = by_day[session_day]
            if day_b.empty:
                continue
            base = compute_setup_short(day_b, session_day)
            if base is None:
                continue
            for sm in selected_modes:
                tr = finalize_trade_short(day_b, session_day, base, sm)
                if tr is not None:
                    buckets[sm].append(tr)
        return buckets

    modes = list(SLMode) if args.all_sl else [sl_mode]
    print('London sweep → breaker → piercer → limit (SHORT, no ORB)')
    cache = collect_trades(modes)
    for sm in modes:
        st = summarize(cache[sm])
        print(f'\n--- SL = {sm.value} ---')
        print(f'Sessions with trade: {st["n"]}')
        print(f'Σ Net USD (1 MNQ): ${st["sum_net"]:,.2f}')
        print(f'Win rate (Net > 0): {st["wr"]:.2f}%')
        print(f'Max DD (leg cumulative): ${st["max_dd"]:,.2f}')
        print(f'Mean MAE (pts): {st["mean_mae"]:.4f}')
        eff = st['sum_net'] / abs(st['max_dd']) if st['max_dd'] else float('nan')
        print(f'Σ Net / |max DD|: {eff:.3f}')

    print(f'\nDate range scanned: {date_min} .. {date_max}')

    trades_final = cache[sl_mode]
    if args.export_csv:
        cols = [
            'session_day',
            'entry',
            'exit_px',
            'net_usd',
            'mae_pts',
            'mfe_pts',
            'result',
            'sl_mode',
            'london_high',
            'london_low',
            'breaker_high',
            'breaker_low',
            'stop_hunter_high',
            'piercer_low',
            'tp_px',
            'stop_px',
            'breaker_5m_left',
        ]
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{k: getattr(r, k) for k in cols} for r in trades_final]).to_csv(
            args.export_csv, index=False
        )
        print(f'Wrote {args.export_csv}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
