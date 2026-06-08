"""Strict causal v2e London sweep simulation.

This module models the v2e London sweep -> breaker -> piercer -> limit
pullback as a live-style 1 minute state machine. It intentionally does
not reconstruct the completed session before deciding whether an order
would have been placed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import math

import pandas as pd
import pytz

NY = pytz.timezone('America/New_York')
LDN_LO = time(2, 0)
LDN_HI = time(9, 30)
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
EOD_CUTOFF = time(15, 59)

MULT = 2.0
FEE_RT = 1.50
_EPS = 1e-12

V2eSide = Literal['long', 'short']
V2eSlFamily = Literal['london', 'breaker', 'stop_hunter']


@dataclass
class CausalV2eTrade:
    session_day: date
    side: str
    status: str
    entry: float
    exit_px: float
    net_usd: float
    mae_pts: float
    mfe_pts: float
    result: str
    sl_mode: str
    london_low: float
    london_high: float
    breaker_high: float
    breaker_low: float
    stop_hunter_low: float
    stop_hunter_high: float
    piercer_high: float
    piercer_low: float
    tp_px: float
    stop_px: float
    first_sweep_time: pd.Timestamp
    stop_hunter_time: pd.Timestamp
    breaker_5m_left: pd.Timestamp
    breaker_confirm_time: pd.Timestamp
    breaker_minutes: int
    breaker_close_confirm_required: bool
    breaker_close_confirm_time: pd.Timestamp
    breaker_close_confirm_px: float
    piercer_time: pd.Timestamp
    piercer_confirm_time: pd.Timestamp
    setup_commit_time: pd.Timestamp
    order_live_time: pd.Timestamp
    fill_time: pd.Timestamp
    exit_time: pd.Timestamp
    attempt_id: int = 1
    reentry_mode: bool = False
    reentry_base_time: pd.Timestamp = pd.NaT
    reentry_base_px: float = float('nan')

    def to_row(self) -> Dict[str, object]:
        row = asdict(self)
        for key, value in list(row.items()):
            if isinstance(value, pd.Timestamp):
                row[key] = value.isoformat()
            elif isinstance(value, date):
                row[key] = value.isoformat()
        return row


def normalize_v2e_sl_mode(value: str) -> V2eSlFamily:
    v = str(value).strip().lower()
    if v in {'london', 'london_low', 'london_high'}:
        return 'london'
    if v in {'breaker', 'breaker_low', 'breaker_high'}:
        return 'breaker'
    if v in {'stop_hunter', 'stop_hunter_low', 'stop_hunter_high'}:
        return 'stop_hunter'
    raise ValueError(f'Unknown v2e SL mode: {value}')


def concrete_sl_mode(side: V2eSide, sl_mode: str) -> str:
    family = normalize_v2e_sl_mode(sl_mode)
    if side == 'long':
        return {
            'london': 'london_low',
            'breaker': 'breaker_low',
            'stop_hunter': 'stop_hunter_low',
        }[family]
    return {
        'london': 'london_high',
        'breaker': 'breaker_high',
        'stop_hunter': 'stop_hunter_high',
    }[family]


def iter_calendar_dates(dmin: date, dmax: date):
    cur = pd.Timestamp(dmin)
    end = pd.Timestamp(dmax)
    while cur <= end:
        yield cur.date()
        cur += pd.Timedelta(days=1)


def london_low_high(day_1m: pd.DataFrame, session_day: date) -> Tuple[float, float]:
    b = day_1m[
        day_1m.index.map(
            lambda t: t.date() == session_day and LDN_LO <= t.time() < LDN_HI
        )
    ]
    if b.empty:
        return float('nan'), float('nan')
    return float(b['low'].min()), float(b['high'].max())


def resample_session_from_02(day_1m: pd.DataFrame, session_day: date, minutes: int = 5) -> pd.DataFrame:
    if minutes <= 0:
        raise ValueError(f'Breaker minutes must be positive, got {minutes}')
    sub = day_1m[
        day_1m.index.map(
            lambda t: t.date() == session_day and LDN_LO <= t.time() < RTH_HI
        )
    ].sort_index()
    if sub.empty:
        return sub
    anchor = NY.localize(datetime.combine(session_day, LDN_LO))
    return (
        sub.resample(f'{minutes}min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def resample_session_5m_from_02(day_1m: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return resample_session_from_02(day_1m, session_day, minutes=5)


def _bar_close(ts: pd.Timestamp, minutes: int = 1) -> pd.Timestamp:
    return pd.Timestamp(ts) + pd.Timedelta(minutes=minutes)


def _session_day_from_index(day_1m: pd.DataFrame) -> Optional[date]:
    if day_1m.empty:
        return None
    dates = sorted(set(pd.Timestamp(t).date() for t in day_1m.index))
    return dates[0] if dates else None


def _audit(
    audit: List[Dict[str, object]],
    *,
    session_day: date,
    side: V2eSide,
    event: str,
    ts: Optional[pd.Timestamp] = None,
    **fields: object,
) -> None:
    row: Dict[str, object] = {
        'session_day': session_day.isoformat(),
        'side': side,
        'event': event,
    }
    if ts is not None:
        row['ts'] = pd.Timestamp(ts).isoformat()
    for key, value in fields.items():
        if isinstance(value, pd.Timestamp):
            row[key] = value.isoformat()
        elif isinstance(value, date):
            row[key] = value.isoformat()
        else:
            row[key] = value
    audit.append(row)


def _first_sweep_hit(side: V2eSide, high: float, low: float, london_low: float, london_high: float) -> bool:
    if side == 'long':
        return low <= london_low + _EPS
    return high >= london_high - _EPS


def _pick_breaker_prefix(
    *,
    side: V2eSide,
    swings5: List[Dict[str, object]],
    session_day: date,
    ts_stop_hunter_open: pd.Timestamp,
    current_close: pd.Timestamp,
    breaker_minutes: int,
) -> Optional[Dict[str, object]]:
    if not swings5:
        return None

    ts_sh = pd.Timestamp(ts_stop_hunter_open)
    breaker_delta = pd.Timedelta(minutes=breaker_minutes)
    london_open = NY.localize(datetime.combine(session_day, LDN_LO))
    if ts_sh.tzinfo is None:
        ts_sh = ts_sh.tz_localize(london_open.tzinfo)
    else:
        ts_sh = ts_sh.tz_convert(london_open.tzinfo)
    if ts_sh < london_open:
        return None

    bucket_n = int((ts_sh - london_open).total_seconds() // (breaker_minutes * 60))
    sh_bucket_left = london_open + pd.Timedelta(minutes=breaker_minutes * bucket_n)
    after_left = sh_bucket_left + breaker_delta
    swings: List[Dict[str, object]] = []
    for sw in swings5:
        bl = pd.Timestamp(sw['bar_left'])
        if bl < london_open or bl > after_left:
            continue
        if pd.Timestamp(sw['confirm_close']) > current_close:
            continue
        swings.append(
            {
                'breaker_5m_left': bl,
                'breaker_high': float(sw['high']),
                'breaker_low': float(sw['low']),
                'breaker_confirm_time': pd.Timestamp(sw['confirm_label']),
            }
        )

    return swings[-1] if swings else None


def _find_piercer_prefix(
    *,
    side: V2eSide,
    swings1: List[Dict[str, int]],
    highs: List[float],
    lows: List[float],
    sh_i: int,
    breaker_high: float,
    breaker_low: float,
    current_i: int,
) -> Optional[Tuple[int, int]]:
    for sw in swings1:
        k = int(sw['i'])
        confirm_i = int(sw['confirm_i'])
        if k <= sh_i or confirm_i > current_i:
            continue
        if side == 'long':
            if highs[k] > breaker_high + _EPS:
                return k, confirm_i
        else:
            if lows[k] + _EPS < breaker_low:
                return k, confirm_i
    return None


def _resolve_setup_prefix(
    *,
    side: V2eSide,
    session_day: date,
    ts_list: List[pd.Timestamp],
    highs: List[float],
    lows: List[float],
    swings5: List[Dict[str, object]],
    swings1: List[Dict[str, int]],
    first_sweep_i: int,
    current_i: int,
    max_passes: int,
    breaker_minutes: int,
) -> Optional[Dict[str, object]]:
    current_close = _bar_close(ts_list[current_i])
    sh_i = first_sweep_i

    for _ in range(max_passes):
        brk = _pick_breaker_prefix(
            side=side,
            swings5=swings5,
            session_day=session_day,
            ts_stop_hunter_open=ts_list[sh_i],
            current_close=current_close,
            breaker_minutes=breaker_minutes,
        )
        if brk is None:
            return None

        piercer = _find_piercer_prefix(
            side=side,
            swings1=swings1,
            highs=highs,
            lows=lows,
            sh_i=sh_i,
            breaker_high=float(brk['breaker_high']),
            breaker_low=float(brk['breaker_low']),
            current_i=current_i,
        )
        if piercer is None:
            return None
        piercer_i, piercer_confirm_i = piercer
        if piercer_i <= first_sweep_i:
            return None

        segment = range(first_sweep_i, piercer_i)
        if side == 'long':
            sh_next = min(segment, key=lambda k: (lows[k], k))
        else:
            sh_next = min(segment, key=lambda k: (-highs[k], k))
        if sh_next == sh_i:
            return {
                'sh_i': sh_i,
                'piercer_i': piercer_i,
                'piercer_confirm_i': piercer_confirm_i,
                **brk,
            }
        sh_i = sh_next

    return None


def _levels_for_setup(
    *,
    side: V2eSide,
    sl_mode: V2eSlFamily,
    london_low: float,
    london_high: float,
    highs: List[float],
    lows: List[float],
    setup: Dict[str, object],
) -> Optional[Dict[str, float]]:
    sh_i = int(setup['sh_i'])
    piercer_i = int(setup['piercer_i'])
    breaker_high = float(setup['breaker_high'])
    breaker_low = float(setup['breaker_low'])

    if side == 'long':
        stop_hunter_low = float(lows[sh_i])
        piercer_high = float(highs[piercer_i])
        entry = breaker_high
        tp_px = stop_hunter_low + (piercer_high - stop_hunter_low) * 2.0
        stop_px = {
            'london': london_low,
            'breaker': breaker_low,
            'stop_hunter': stop_hunter_low,
        }[sl_mode]
        if tp_px <= entry + _EPS or entry <= stop_px + _EPS:
            return None
        return {
            'entry': entry,
            'tp_px': tp_px,
            'stop_px': stop_px,
            'stop_hunter_low': stop_hunter_low,
            'stop_hunter_high': float('nan'),
            'piercer_high': piercer_high,
            'piercer_low': float('nan'),
        }

    stop_hunter_high = float(highs[sh_i])
    piercer_low = float(lows[piercer_i])
    entry = breaker_low
    tp_px = stop_hunter_high - (stop_hunter_high - piercer_low) * 2.0
    stop_px = {
        'london': london_high,
        'breaker': breaker_high,
        'stop_hunter': stop_hunter_high,
    }[sl_mode]
    if tp_px >= entry - _EPS or stop_px <= entry + _EPS:
        return None
    return {
        'entry': entry,
        'tp_px': tp_px,
        'stop_px': stop_px,
        'stop_hunter_low': float('nan'),
        'stop_hunter_high': stop_hunter_high,
        'piercer_high': float('nan'),
        'piercer_low': piercer_low,
    }


def _build_1m_swing_cache(
    *,
    side: V2eSide,
    ts_list: List[pd.Timestamp],
    highs: List[float],
    lows: List[float],
    session_day: date,
) -> List[Dict[str, int]]:
    swings: List[Dict[str, int]] = []
    for k in range(1, len(ts_list) - 1):
        if (
            ts_list[k - 1].date() != session_day
            or ts_list[k].date() != session_day
            or ts_list[k + 1].date() != session_day
        ):
            continue
        if side == 'long':
            is_swing = highs[k] > highs[k - 1] + _EPS and highs[k] > highs[k + 1] + _EPS
        else:
            is_swing = lows[k] + _EPS < lows[k - 1] and lows[k] + _EPS < lows[k + 1]
        if is_swing:
            swings.append({'i': k, 'confirm_i': k + 1})
    return swings


def _build_breaker_swing_cache(*, side: V2eSide, bars: pd.DataFrame, breaker_minutes: int) -> List[Dict[str, object]]:
    if len(bars) < 3:
        return []
    idxs = bars.index.to_list()
    highs_b = bars['high'].astype(float).to_numpy()
    lows_b = bars['low'].astype(float).to_numpy()
    swings: List[Dict[str, object]] = []
    for k in range(1, len(idxs) - 1):
        if side == 'long':
            is_swing = highs_b[k] > highs_b[k - 1] + _EPS and highs_b[k] > highs_b[k + 1] + _EPS
        else:
            is_swing = lows_b[k] + _EPS < lows_b[k - 1] and lows_b[k] + _EPS < lows_b[k + 1]
        if not is_swing:
            continue
        right_left = idxs[k + 1]
        swings.append(
            {
                'bar_left': idxs[k],
                'high': float(highs_b[k]),
                'low': float(lows_b[k]),
                'confirm_label': right_left,
                'confirm_close': right_left + pd.Timedelta(minutes=breaker_minutes),
            }
        )
    return swings


def _build_5m_swing_cache(*, side: V2eSide, bars5: pd.DataFrame) -> List[Dict[str, object]]:
    return _build_breaker_swing_cache(side=side, bars=bars5, breaker_minutes=5)


def _build_breaker_close_cache(*, bars: pd.DataFrame, breaker_minutes: int) -> List[Dict[str, object]]:
    if bars.empty:
        return []
    return [
        {
            'bar_left': pd.Timestamp(ts),
            'confirm_time': pd.Timestamp(ts) + pd.Timedelta(minutes=breaker_minutes),
            'close': float(row['close']),
        }
        for ts, row in bars.iterrows()
    ]


def _find_breaker_close_confirm(
    *,
    side: V2eSide,
    close_cache: List[Dict[str, object]],
    breaker_high: float,
    breaker_low: float,
    earliest_confirm_time: pd.Timestamp,
    current_close: pd.Timestamp,
) -> Optional[Dict[str, object]]:
    for row in close_cache:
        confirm_time = pd.Timestamp(row['confirm_time'])
        if confirm_time < earliest_confirm_time:
            continue
        if confirm_time > current_close:
            break
        close_px = float(row['close'])
        if side == 'long' and close_px > breaker_high + _EPS:
            return row
        if side == 'short' and close_px + _EPS < breaker_low:
            return row
    return None


def _entry_hit(side: V2eSide, high: float, low: float, entry: float) -> bool:
    if side == 'long':
        return low <= entry + _EPS
    return high >= entry - _EPS


def _exit_hit(
    *,
    side: V2eSide,
    high: float,
    low: float,
    entry: float,
    stop_px: float,
    tp_px: float,
) -> Tuple[Optional[float], Optional[str], float, float]:
    if side == 'long':
        mae = max(0.0, entry - low)
        mfe = max(0.0, high - entry)
        hit_stop = low <= stop_px + _EPS
        hit_tp = high >= tp_px - _EPS
        if hit_stop:
            return stop_px, 'Loss' if stop_px < entry - _EPS else 'Stop-BE', mae, mfe
        if hit_tp:
            return tp_px, 'Win', mae, mfe
        return None, None, mae, mfe

    mae = max(0.0, high - entry)
    mfe = max(0.0, entry - low)
    hit_stop = high >= stop_px - _EPS
    hit_tp = low <= tp_px + _EPS
    if hit_stop:
        return stop_px, 'Loss' if stop_px > entry + _EPS else 'Stop-BE', mae, mfe
    if hit_tp:
        return tp_px, 'Win', mae, mfe
    return None, None, mae, mfe


def _eod_exit(day_1m: pd.DataFrame, session_day: date, side: V2eSide, entry: float) -> Tuple[pd.Timestamp, float, str]:
    tail = day_1m[
        day_1m.index.map(lambda t: t.date() == session_day and t.time() < RTH_HI)
    ].sort_index()
    if tail.empty:
        return pd.NaT, entry, 'no_data'
    ts = pd.Timestamp(tail.index[-1])
    px = float(tail.iloc[-1]['close'])
    if side == 'long':
        if px > entry + _EPS:
            return ts, px, 'EOD-Win'
        if px < entry - _EPS:
            return ts, px, 'EOD-Loss'
    else:
        if px < entry - _EPS:
            return ts, px, 'EOD-Win'
        if px > entry + _EPS:
            return ts, px, 'EOD-Loss'
    return ts, px, 'EOD-Flat'


def _net_usd(side: V2eSide, entry: float, exit_px: float) -> float:
    pnl_pts = exit_px - entry if side == 'long' else entry - exit_px
    return round(pnl_pts * MULT - FEE_RT, 2)


def simulate_v2e_causal_session(
    day_1m: pd.DataFrame,
    session_day: Optional[date] = None,
    *,
    side: V2eSide = 'long',
    sl_mode: str = 'stop_hunter',
    max_passes: int = 30,
    breaker_minutes: int = 5,
    require_breaker_close_confirm: bool = False,
    scan_start_time: Optional[pd.Timestamp] = None,
    london_low_override: Optional[float] = None,
    london_high_override: Optional[float] = None,
    attempt_id: int = 1,
    reentry_mode: bool = False,
    reentry_base_time: Optional[pd.Timestamp] = None,
    reentry_base_px: float = float('nan'),
) -> Tuple[Optional[CausalV2eTrade], List[Dict[str, object]]]:
    """Run one strict causal v2e side for one session day.

    Timestamps in the returned trade use bar labels, matching the source
    OHLCV data. For example, ``piercer_confirm_time`` is the timestamp of
    the right-neighbor 1m bar that confirms the pivot, while
    ``order_live_time`` is the next 1m bar label.
    """
    if side not in {'long', 'short'}:
        raise ValueError(f'Unknown side: {side}')
    if breaker_minutes <= 0:
        raise ValueError(f'breaker_minutes must be positive, got {breaker_minutes}')
    sl_family = normalize_v2e_sl_mode(sl_mode)

    day = day_1m.sort_index().copy()
    if session_day is None:
        session_day = _session_day_from_index(day)
    if session_day is None:
        return None, []

    audit: List[Dict[str, object]] = []
    london_low, london_high = london_low_high(day, session_day)
    if london_low_override is not None:
        london_low = float(london_low_override)
    if london_high_override is not None:
        london_high = float(london_high_override)
    if math.isnan(london_low) or math.isnan(london_high):
        _audit(audit, session_day=session_day, side=side, event='no_london_box')
        return None, audit

    ts_list = list(day.index)
    highs = [float(x) for x in day['high'].tolist()]
    lows = [float(x) for x in day['low'].tolist()]
    breaker_bars = resample_session_from_02(day, session_day, minutes=breaker_minutes)
    if len(ts_list) < 5 or len(breaker_bars) < 3:
        _audit(audit, session_day=session_day, side=side, event='insufficient_bars')
        return None, audit
    swings1 = _build_1m_swing_cache(
        side=side,
        ts_list=ts_list,
        highs=highs,
        lows=lows,
        session_day=session_day,
    )
    swings5 = _build_breaker_swing_cache(side=side, bars=breaker_bars, breaker_minutes=breaker_minutes)
    breaker_close_cache = _build_breaker_close_cache(bars=breaker_bars, breaker_minutes=breaker_minutes)

    _audit(
        audit,
        session_day=session_day,
        side=side,
        event='london_box',
        london_low=london_low,
        london_high=london_high,
    )

    first_sweep_i: Optional[int] = None
    order: Optional[Dict[str, object]] = None
    in_trade = False
    fill_time: Optional[pd.Timestamp] = None
    mae = 0.0
    mfe = 0.0

    for i, ts in enumerate(ts_list):
        ts = pd.Timestamp(ts)
        if ts.date() != session_day:
            continue
        if scan_start_time is not None and ts < pd.Timestamp(scan_start_time):
            continue
        if ts.time() < RTH_LO:
            continue
        if ts.time() >= EOD_CUTOFF:
            break

        row = day.iloc[i]
        high = float(row['high'])
        low = float(row['low'])

        if in_trade and order is not None:
            exit_px, result, b_mae, b_mfe = _exit_hit(
                side=side,
                high=high,
                low=low,
                entry=float(order['entry']),
                stop_px=float(order['stop_px']),
                tp_px=float(order['tp_px']),
            )
            mae = max(mae, b_mae)
            mfe = max(mfe, b_mfe)
            if exit_px is not None and result is not None:
                tr = _build_trade(
                    session_day=session_day,
                    side=side,
                    sl_mode=concrete_sl_mode(side, sl_family),
                    london_low=london_low,
                    london_high=london_high,
                    order=order,
                    exit_px=float(exit_px),
                    exit_time=ts,
                    result=result,
                    mae=mae,
                    mfe=mfe,
                    fill_time=fill_time or ts,
                    highs=highs,
                    lows=lows,
                    ts_list=ts_list,
                )
                _audit(audit, session_day=session_day, side=side, event='exit', ts=ts, result=result, exit_px=exit_px)
                return tr, audit
            continue

        if order is not None and not in_trade:
            order_live_time = pd.Timestamp(order['order_live_time'])
            if ts >= order_live_time and _entry_hit(side, high, low, float(order['entry'])):
                in_trade = True
                fill_time = ts
                _audit(
                    audit,
                    session_day=session_day,
                    side=side,
                    event='fill',
                    ts=ts,
                    entry=float(order['entry']),
                    order_live_time=order_live_time,
                )
                exit_px, result, b_mae, b_mfe = _exit_hit(
                    side=side,
                    high=high,
                    low=low,
                    entry=float(order['entry']),
                    stop_px=float(order['stop_px']),
                    tp_px=float(order['tp_px']),
                )
                mae = max(mae, b_mae)
                mfe = max(mfe, b_mfe)
                if exit_px is not None and result is not None:
                    tr = _build_trade(
                        session_day=session_day,
                        side=side,
                        sl_mode=concrete_sl_mode(side, sl_family),
                        london_low=london_low,
                        london_high=london_high,
                        order=order,
                        exit_px=float(exit_px),
                        exit_time=ts,
                        result=result,
                        mae=mae,
                        mfe=mfe,
                        fill_time=fill_time,
                        highs=highs,
                        lows=lows,
                        ts_list=ts_list,
                    )
                    _audit(audit, session_day=session_day, side=side, event='exit', ts=ts, result=result, exit_px=exit_px)
                    return tr, audit
            continue

        if first_sweep_i is None:
            if _first_sweep_hit(side, high, low, london_low, london_high):
                first_sweep_i = i
                _audit(
                    audit,
                    session_day=session_day,
                    side=side,
                    event='first_sweep',
                    ts=ts,
                    london_low=london_low,
                    london_high=london_high,
                )
            else:
                continue

        setup = _resolve_setup_prefix(
            side=side,
            session_day=session_day,
            ts_list=ts_list,
            highs=highs,
            lows=lows,
            swings5=swings5,
            swings1=swings1,
            first_sweep_i=first_sweep_i,
            current_i=i,
            max_passes=max_passes,
            breaker_minutes=breaker_minutes,
        )
        if setup is None:
            continue

        levels = _levels_for_setup(
            side=side,
            sl_mode=sl_family,
            london_low=london_low,
            london_high=london_high,
            highs=highs,
            lows=lows,
            setup=setup,
        )
        if levels is None:
            _audit(
                audit,
                session_day=session_day,
                side=side,
                event='invalid_levels',
                ts=ts,
                sl_mode=concrete_sl_mode(side, sl_family),
            )
            continue

        close_confirm_time = pd.NaT
        close_confirm_px = float('nan')
        if require_breaker_close_confirm:
            close_confirm = _find_breaker_close_confirm(
                side=side,
                close_cache=breaker_close_cache,
                breaker_high=float(setup['breaker_high']),
                breaker_low=float(setup['breaker_low']),
                earliest_confirm_time=_bar_close(ts_list[int(setup['piercer_confirm_i'])]),
                current_close=_bar_close(ts),
            )
            if close_confirm is None:
                continue
            close_confirm_time = pd.Timestamp(close_confirm['confirm_time'])
            close_confirm_px = float(close_confirm['close'])

        order_live_time = _bar_close(ts)
        if order_live_time.time() >= EOD_CUTOFF:
            _audit(audit, session_day=session_day, side=side, event='late_setup_skip', ts=ts)
            continue

        order = {
            **setup,
            **levels,
            'first_sweep_i': first_sweep_i,
            'breaker_minutes': breaker_minutes,
            'breaker_close_confirm_required': require_breaker_close_confirm,
            'breaker_close_confirm_time': close_confirm_time,
            'breaker_close_confirm_px': close_confirm_px,
            'attempt_id': attempt_id,
            'reentry_mode': reentry_mode,
            'reentry_base_time': reentry_base_time if reentry_base_time is not None else pd.NaT,
            'reentry_base_px': reentry_base_px,
            'setup_commit_time': ts,
            'order_live_time': order_live_time,
        }
        _audit(
            audit,
            session_day=session_day,
            side=side,
            event='setup_committed',
            ts=ts,
            entry=levels['entry'],
            stop_px=levels['stop_px'],
            tp_px=levels['tp_px'],
            order_live_time=order_live_time,
            piercer_time=ts_list[int(setup['piercer_i'])],
            piercer_confirm_time=ts_list[int(setup['piercer_confirm_i'])],
            breaker_5m_left=setup['breaker_5m_left'],
            breaker_confirm_time=setup['breaker_confirm_time'],
            breaker_minutes=breaker_minutes,
            breaker_close_confirm_required=require_breaker_close_confirm,
            breaker_close_confirm_time=close_confirm_time,
            breaker_close_confirm_px=close_confirm_px,
        )

    if in_trade and order is not None:
        eod_ts, eod_px, result = _eod_exit(day, session_day, side, float(order['entry']))
        if not pd.isna(eod_ts):
            last = day.loc[eod_ts]
            if side == 'long':
                mae = max(mae, float(order['entry']) - float(last['low']))
                mfe = max(mfe, float(last['high']) - float(order['entry']))
            else:
                mae = max(mae, float(last['high']) - float(order['entry']))
                mfe = max(mfe, float(order['entry']) - float(last['low']))
        tr = _build_trade(
            session_day=session_day,
            side=side,
            sl_mode=concrete_sl_mode(side, sl_family),
            london_low=london_low,
            london_high=london_high,
            order=order,
            exit_px=eod_px,
            exit_time=eod_ts,
            result=result,
            mae=mae,
            mfe=mfe,
            fill_time=fill_time or eod_ts,
            highs=highs,
            lows=lows,
            ts_list=ts_list,
        )
        _audit(audit, session_day=session_day, side=side, event='eod_exit', ts=eod_ts, result=result, exit_px=eod_px)
        return tr, audit

    if order is not None:
        _audit(
            audit,
            session_day=session_day,
            side=side,
            event='no_fill',
            ts=pd.Timestamp(order['order_live_time']),
            entry=float(order['entry']),
        )
    elif first_sweep_i is None:
        _audit(audit, session_day=session_day, side=side, event='no_sweep')
    else:
        _audit(audit, session_day=session_day, side=side, event='no_setup')
    return None, audit


def simulate_v2e_causal_session_reentry(
    day_1m: pd.DataFrame,
    session_day: Optional[date] = None,
    *,
    side: V2eSide = 'long',
    sl_mode: str = 'stop_hunter',
    max_passes: int = 30,
    breaker_minutes: int = 5,
    require_breaker_close_confirm: bool = False,
    max_reentries: int = 3,
) -> Tuple[List[CausalV2eTrade], List[Dict[str, object]]]:
    """Run a same-side re-entry variant for one session.

    After each filled attempt exits, the next attempt replaces the relevant
    London boundary with that attempt's stop-hunter extreme. Longs replace
    London low with stop-hunter low; shorts replace London high with
    stop-hunter high. The next search starts on the minute after exit.
    """
    if side not in {'long', 'short'}:
        raise ValueError(f'Unknown side: {side}')
    day = day_1m.sort_index()
    if session_day is None:
        session_day = _session_day_from_index(day)
    if session_day is None:
        return [], []

    london_low, london_high = london_low_high(day, session_day)
    if math.isnan(london_low) or math.isnan(london_high):
        audit: List[Dict[str, object]] = []
        _audit(audit, session_day=session_day, side=side, event='no_london_box')
        return [], audit

    max_attempts = max(1, int(max_reentries) + 1)
    trades: List[CausalV2eTrade] = []
    audit_rows: List[Dict[str, object]] = []
    scan_start_time: Optional[pd.Timestamp] = None
    active_london_low = london_low
    active_london_high = london_high
    reentry_base_time: Optional[pd.Timestamp] = None
    reentry_base_px = float('nan')

    for attempt_id in range(1, max_attempts + 1):
        trade, audit = simulate_v2e_causal_session(
            day,
            session_day,
            side=side,
            sl_mode=sl_mode,
            max_passes=max_passes,
            breaker_minutes=breaker_minutes,
            require_breaker_close_confirm=require_breaker_close_confirm,
            scan_start_time=scan_start_time,
            london_low_override=active_london_low,
            london_high_override=active_london_high,
            attempt_id=attempt_id,
            reentry_mode=True,
            reentry_base_time=reentry_base_time,
            reentry_base_px=reentry_base_px,
        )
        for row in audit:
            row.setdefault('attempt_id', attempt_id)
            row.setdefault('reentry_mode', True)
            audit_rows.append(row)
        if trade is None:
            break

        trades.append(trade)
        exit_time = pd.Timestamp(trade.exit_time)
        if pd.isna(exit_time):
            break
        next_start = exit_time + pd.Timedelta(minutes=1)
        if next_start.time() >= EOD_CUTOFF:
            break

        if side == 'long':
            if math.isnan(float(trade.stop_hunter_low)):
                break
            active_london_low = float(trade.stop_hunter_low)
            reentry_base_px = active_london_low
        else:
            if math.isnan(float(trade.stop_hunter_high)):
                break
            active_london_high = float(trade.stop_hunter_high)
            reentry_base_px = active_london_high
        reentry_base_time = pd.Timestamp(trade.stop_hunter_time)
        scan_start_time = next_start

    return trades, audit_rows


def _build_trade(
    *,
    session_day: date,
    side: V2eSide,
    sl_mode: str,
    london_low: float,
    london_high: float,
    order: Dict[str, object],
    exit_px: float,
    exit_time: pd.Timestamp,
    result: str,
    mae: float,
    mfe: float,
    fill_time: pd.Timestamp,
    highs: List[float],
    lows: List[float],
    ts_list: List[pd.Timestamp],
) -> CausalV2eTrade:
    sh_i = int(order['sh_i'])
    piercer_i = int(order['piercer_i'])
    first_sweep_i = int(order['first_sweep_i'])
    entry = float(order['entry'])
    return CausalV2eTrade(
        session_day=session_day,
        side=side,
        status='filled',
        entry=entry,
        exit_px=float(exit_px),
        net_usd=_net_usd(side, entry, float(exit_px)),
        mae_pts=round(float(mae), 4),
        mfe_pts=round(float(mfe), 4),
        result=result,
        sl_mode=sl_mode,
        london_low=float(london_low),
        london_high=float(london_high),
        breaker_high=float(order['breaker_high']),
        breaker_low=float(order['breaker_low']),
        stop_hunter_low=round(float(order['stop_hunter_low']), 8) if not math.isnan(float(order['stop_hunter_low'])) else float('nan'),
        stop_hunter_high=round(float(order['stop_hunter_high']), 8) if not math.isnan(float(order['stop_hunter_high'])) else float('nan'),
        piercer_high=round(float(order['piercer_high']), 8) if not math.isnan(float(order['piercer_high'])) else float('nan'),
        piercer_low=round(float(order['piercer_low']), 8) if not math.isnan(float(order['piercer_low'])) else float('nan'),
        tp_px=float(order['tp_px']),
        stop_px=float(order['stop_px']),
        first_sweep_time=pd.Timestamp(ts_list[first_sweep_i]),
        stop_hunter_time=pd.Timestamp(ts_list[sh_i]),
        breaker_5m_left=pd.Timestamp(order['breaker_5m_left']),
        breaker_confirm_time=pd.Timestamp(order['breaker_confirm_time']),
        breaker_minutes=int(order['breaker_minutes']),
        breaker_close_confirm_required=bool(order.get('breaker_close_confirm_required', False)),
        breaker_close_confirm_time=pd.Timestamp(order.get('breaker_close_confirm_time', pd.NaT)),
        breaker_close_confirm_px=float(order.get('breaker_close_confirm_px', float('nan'))),
        piercer_time=pd.Timestamp(ts_list[piercer_i]),
        piercer_confirm_time=pd.Timestamp(ts_list[int(order['piercer_confirm_i'])]),
        setup_commit_time=pd.Timestamp(order['setup_commit_time']),
        order_live_time=pd.Timestamp(order['order_live_time']),
        fill_time=pd.Timestamp(fill_time),
        exit_time=pd.Timestamp(exit_time),
        attempt_id=int(order.get('attempt_id', 1)),
        reentry_mode=bool(order.get('reentry_mode', False)),
        reentry_base_time=pd.Timestamp(order.get('reentry_base_time', pd.NaT)),
        reentry_base_px=float(order.get('reentry_base_px', float('nan'))),
    )
