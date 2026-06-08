"""Shared execution assumptions for MNQ ORB research.

The defaults intentionally preserve the legacy research backtests. More
conservative behavior is opt-in via explicit profiles/CLI flags.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, time
from hashlib import sha256
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Tuple

import pandas as pd

RollMode = Literal['legacy-volume', 'calendar']
ChildEngine = Literal['legacy', 'chronological']
FillRule = Literal['touch', 'through_1_tick']
AmbiguityPolicy = Literal['current', 'adverse']
ExecutionProfile = Literal['baseline', 'mild', 'conservative', 'latency', 'blackout']


LIB_DIR = Path(__file__).resolve().parent
DEFAULT_ROLL_CALENDAR = LIB_DIR / 'mnq_roll_calendar.csv'


@dataclass(frozen=True)
class BlackoutWindow:
    start: pd.Timestamp
    end: pd.Timestamp
    reason: str = ''


@dataclass(frozen=True)
class RollParams:
    mode: RollMode = 'legacy-volume'
    calendar_path: Path = DEFAULT_ROLL_CALENDAR
    product: str = 'MNQ'


@dataclass(frozen=True)
class ExecutionParams:
    profile: str = 'baseline'
    entry_slip_ticks: int = 1
    stop_slip_ticks: int = 0
    target_fill_rule: FillRule = 'touch'
    child_limit_fill_rule: FillRule = 'touch'
    child_limit_miss_rate: float = 0.0
    ambiguity_policy: AmbiguityPolicy = 'current'
    order_delay_bars: int = 0
    fee_rt: float = 1.50
    seed: int = 42
    blackout_windows: Tuple[BlackoutWindow, ...] = ()


@dataclass(frozen=True)
class ChildFilterParams:
    enabled: bool = False
    max_child_adds: int = 1
    min_distance_to_target_pts: Optional[float] = None
    max_minutes_after_parent_fill: Optional[float] = None
    min_or_range_pts: Optional[float] = None
    max_or_range_pts: Optional[float] = None
    min_child_close_distance_to_target_pts: Optional[float] = None
    max_impulse_1m_pts: Optional[float] = None


def load_roll_calendar(path: Path = DEFAULT_ROLL_CALENDAR) -> pd.DataFrame:
    cal = pd.read_csv(path)
    required = {'product', 'start_date', 'end_date', 'symbol', 'notes'}
    missing = required - set(cal.columns)
    if missing:
        raise ValueError(f'Roll calendar {path} missing columns: {sorted(missing)}')
    cal = cal.copy()
    cal['start_date'] = pd.to_datetime(cal['start_date']).dt.date
    cal['end_date'] = pd.to_datetime(cal['end_date']).dt.date
    return cal


def front_month_by_legacy_volume(df: pd.DataFrame, *, date_col: str = 'date') -> Dict[date, str]:
    return (
        df.groupby([date_col, 'symbol'])['volume']
        .sum()
        .groupby(level=date_col)
        .idxmax()
        .apply(lambda x: x[1])
        .to_dict()
    )


def front_month_by_roll_calendar(
    dates: Iterable[date],
    *,
    product: str = 'MNQ',
    calendar_path: Path = DEFAULT_ROLL_CALENDAR,
) -> Dict[date, str]:
    cal = load_roll_calendar(calendar_path)
    cal = cal[cal['product'].astype(str).str.upper() == product.upper()]
    out: Dict[date, str] = {}
    for d in dates:
        hit = cal[(cal['start_date'] <= d) & (cal['end_date'] >= d)]
        if not hit.empty:
            out[d] = str(hit.iloc[-1]['symbol'])
    return out


def apply_roll_selection(
    df: pd.DataFrame,
    params: RollParams,
    *,
    date_col: str = 'date',
) -> pd.DataFrame:
    """Filter a multi-symbol MNQ DataFrame to the chosen front-month symbol per date."""
    if params.mode == 'legacy-volume':
        front = front_month_by_legacy_volume(df, date_col=date_col)
    elif params.mode == 'calendar':
        front = front_month_by_roll_calendar(
            sorted(df[date_col].dropna().unique()),
            product=params.product,
            calendar_path=params.calendar_path,
        )
    else:
        raise ValueError(f'Unknown roll mode: {params.mode}')
    return df[df.apply(lambda r: r['symbol'] == front.get(r[date_col]), axis=1)].copy()


def load_blackout_windows(path: Optional[Path]) -> Tuple[BlackoutWindow, ...]:
    """Load blackout windows from CSV columns start,end[,reason]."""
    if path is None:
        return ()
    if not Path(path).is_file():
        raise FileNotFoundError(f'Blackout CSV not found: {path}')
    df = pd.read_csv(path)
    required = {'start', 'end'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f'Blackout CSV {path} missing columns: {sorted(missing)}')
    out: List[BlackoutWindow] = []
    for _, row in df.iterrows():
        out.append(
            BlackoutWindow(
                start=pd.Timestamp(row['start']),
                end=pd.Timestamp(row['end']),
                reason=str(row.get('reason', '')),
            )
        )
    return tuple(out)


def execution_params_for_profile(
    profile: ExecutionProfile,
    *,
    entry_slip_ticks: int,
    fee_rt: float,
    seed: int = 42,
    blackout_csv: Optional[Path] = None,
) -> ExecutionParams:
    base = ExecutionParams(
        profile=profile,
        entry_slip_ticks=entry_slip_ticks,
        fee_rt=fee_rt,
        seed=seed,
        blackout_windows=load_blackout_windows(blackout_csv) if profile == 'blackout' else (),
    )
    if profile == 'baseline':
        return replace(base, profile='baseline')
    if profile == 'mild':
        return replace(
            base,
            stop_slip_ticks=1,
            child_limit_fill_rule='through_1_tick',
        )
    if profile == 'conservative':
        return replace(
            base,
            stop_slip_ticks=2,
            target_fill_rule='through_1_tick',
            child_limit_fill_rule='through_1_tick',
            child_limit_miss_rate=0.15,
            ambiguity_policy='adverse',
        )
    if profile == 'latency':
        return replace(base, order_delay_bars=1)
    if profile == 'blackout':
        return base
    raise ValueError(f'Unknown execution profile: {profile}')


def is_blackout(ts: pd.Timestamp, params: ExecutionParams) -> bool:
    if not params.blackout_windows:
        return False
    t = pd.Timestamp(ts)
    return any(w.start <= t < w.end for w in params.blackout_windows)


def price_offset_for_rule(rule: FillRule, tick: float) -> float:
    return tick if rule == 'through_1_tick' else 0.0


def target_hit(direction: str, high: float, low: float, target: float, tick: float, params: ExecutionParams) -> bool:
    off = price_offset_for_rule(params.target_fill_rule, tick)
    if direction == 'Long':
        return high >= target + off
    return low <= target - off


def stop_hit(direction: str, high: float, low: float, stop: float) -> bool:
    if direction == 'Long':
        return low <= stop
    return high >= stop


def stop_exit_price(direction: str, stop: float, tick: float, params: ExecutionParams) -> float:
    slip = params.stop_slip_ticks * tick
    if direction == 'Long':
        return stop - slip
    return stop + slip


def child_limit_hit(direction: str, high: float, low: float, limit_px: float, tick: float, params: ExecutionParams) -> bool:
    off = price_offset_for_rule(params.child_limit_fill_rule, tick)
    if direction == 'Long':
        return low <= limit_px - off
    return high >= limit_px + off


def deterministic_miss(key: str, miss_rate: float, seed: int) -> bool:
    if miss_rate <= 0:
        return False
    if miss_rate >= 1:
        return True
    payload = f'{seed}|{key}'.encode('utf-8')
    val = int(sha256(payload).hexdigest()[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
    return val < miss_rate


def evaluate_child_filters(
    params: ChildFilterParams,
    *,
    direction: str,
    rh: float,
    rl: float,
    rv: float,
    target: float,
    parent_fill_ts: pd.Timestamp,
    candidate_ts: pd.Timestamp,
    child_close: float,
    candidate_1m: Optional[pd.DataFrame] = None,
) -> Tuple[bool, str]:
    if not params.enabled:
        return True, 'disabled'
    if params.min_or_range_pts is not None and rv < params.min_or_range_pts:
        return False, f'range<{params.min_or_range_pts:g}'
    if params.max_or_range_pts is not None and rv > params.max_or_range_pts:
        return False, f'range>{params.max_or_range_pts:g}'
    elapsed = (pd.Timestamp(candidate_ts) - pd.Timestamp(parent_fill_ts)).total_seconds() / 60.0
    if params.max_minutes_after_parent_fill is not None and elapsed > params.max_minutes_after_parent_fill:
        return False, f'elapsed>{params.max_minutes_after_parent_fill:g}m'
    dist_to_target = (target - child_close) if direction == 'Long' else (child_close - target)
    if params.min_distance_to_target_pts is not None and dist_to_target < params.min_distance_to_target_pts:
        return False, f'dist_to_target<{params.min_distance_to_target_pts:g}'
    if params.min_child_close_distance_to_target_pts is not None and dist_to_target < params.min_child_close_distance_to_target_pts:
        return False, f'child_close_near_target<{params.min_child_close_distance_to_target_pts:g}'
    if params.max_impulse_1m_pts is not None and candidate_1m is not None and not candidate_1m.empty:
        impulse = float((candidate_1m['high'] - candidate_1m['low']).max())
        if impulse > params.max_impulse_1m_pts:
            return False, f'impulse>{params.max_impulse_1m_pts:g}'
    return True, 'pass'


def max_drawdown(cumulative: pd.Series) -> float:
    if cumulative.empty:
        return 0.0
    dd = cumulative - cumulative.cummax()
    return float(dd.min())


def summarize_legs(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {
            'legs': 0,
            'net': 0.0,
            'win_rate': 0.0,
            'max_dd': 0.0,
            'child_fills': 0,
        }
    eq = df['Net_$'].astype(float).cumsum()
    return {
        'legs': int(len(df)),
        'net': float(df['Net_$'].astype(float).sum()),
        'win_rate': float((df['Net_$'].astype(float) > 0).mean() * 100.0),
        'max_dd': max_drawdown(eq),
        'child_fills': int(df.get('Child_Add_Count', pd.Series(dtype=float)).fillna(0).astype(int).sum()),
    }


def summarize_audit(audit_df: pd.DataFrame) -> Dict[str, int]:
    if audit_df.empty:
        return {
            'child_candidates': 0,
            'child_filtered': 0,
            'child_missed': 0,
            'child_filled': 0,
            'blackout_skips': 0,
            'ambiguous_bars': 0,
        }
    cancel = audit_df.get('cancel_reason', pd.Series('', index=audit_df.index)).fillna('').astype(str)
    event = audit_df.get('event', pd.Series('', index=audit_df.index)).fillna('').astype(str)
    return {
        'child_candidates': int((event == 'child_candidate').sum()) if 'event' in audit_df else len(audit_df),
        'child_filtered': int((audit_df.get('filter_pass', pd.Series(True, index=audit_df.index)) == False).sum()),
        'child_missed': int((cancel == 'missed_by_model').sum()),
        'child_filled': int((audit_df.get('filled', pd.Series(False, index=audit_df.index)) == True).sum()),
        'blackout_skips': int(((event == 'blackout_skip') | (cancel == 'blackout')).sum()),
        'ambiguous_bars': int((event == 'ambiguous_bar').sum()),
    }


def write_stress_outputs(
    out_csv: Path,
    rows: List[Dict[str, object]],
    *,
    title: str,
) -> Tuple[Path, Path]:
    stress_csv = out_csv.with_suffix(out_csv.suffix + '.execution_stress.csv')
    stress_md = out_csv.with_suffix(out_csv.suffix + '.execution_stress.md')
    df = pd.DataFrame(rows)
    df.to_csv(stress_csv, index=False)
    lines = [f'# {title}', '', '| Profile | Legs | Net $ | Win % | Max DD $ | Child fills | Missed children | Filtered children | Blackout skips | Ambiguous bars |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(
            '| {profile} | {legs} | {net:.2f} | {win_rate:.1f} | {max_dd:.2f} | {child_fills} | {child_missed} | {child_filtered} | {blackout_skips} | {ambiguous_bars} |'.format(
                **r
            )
        )
    lines.extend(
        [
            '',
            'Notes:',
            '- `baseline` is intentionally no-op and should stay comparable to the regular backtest when using the same child engine and roll mode.',
            '- Stress profiles are 1-minute OHLC approximations. Exact queue position, bid/ask spread, sub-second latency, and partial fills require tick/1s data plus broker fill logs.',
        ]
    )
    stress_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return stress_csv, stress_md


def parse_hhmm(value: str) -> time:
    h, m = value.split(':', 1)
    return time(int(h), int(m))
