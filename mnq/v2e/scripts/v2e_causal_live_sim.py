#!/usr/bin/env python3
"""
Strict causal v2e live-style simulator.

This is the live-test counterpart to ``backtest_london_sweep_breaker.py``:
it walks each 1 minute session prefix, confirms breaker-timeframe and
1 minute swings only after their right-side bars exist, places the breaker
limit on the next 1 minute bar, and then simulates stop/target/EOD exits.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

V2E_ROOT = Path(__file__).resolve().parent.parent
MNQ_ROOT = V2E_ROOT.parent
POTIONS_ROOT = MNQ_ROOT.parent
POTIONS_SCRIPTS = POTIONS_ROOT / 'scripts'

sys.path[:0] = [str(MNQ_ROOT), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from rules import (  # noqa: E402
    EOD_CUTOFF,
    LDN_HI,
    LDN_LO,
    NY,
    RTH_HI,
    RTH_LO,
    concrete_sl_mode,
    iter_calendar_dates,
    normalize_v2e_sl_mode,
    resample_session_from_02,
    simulate_v2e_causal_session,
    simulate_v2e_causal_session_reentry,
)

DEFAULT_M1 = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_OUT_CSV = V2E_ROOT / 'data' / 'mnq_v2e_causal_live.csv'
DEFAULT_CHART_OUT = V2E_ROOT / 'case_studies' / 'causal_live'
DEFAULT_LEGACY_LONG = V2E_ROOT / 'data' / 'mnq_v2e_london_sweep_breaker.csv'
DEFAULT_LEGACY_SHORT = V2E_ROOT / 'bearish' / 'data' / 'mnq_v2e_london_sweep_breaker_bearish.csv'

SL_CHOICES = [
    'london',
    'breaker',
    'stop_hunter',
    'london_low',
    'breaker_low',
    'stop_hunter_low',
    'london_high',
    'breaker_high',
    'stop_hunter_high',
]
SIDE_ORDER = {'long': 0, 'short': 1}


def default_chart_out_for_breaker(minutes: int, require_close_confirm: bool = False, allow_reentry: bool = False) -> Path:
    if allow_reentry and minutes == 5 and not require_close_confirm:
        return V2E_ROOT / 'case_studies' / 'causal_live_reentry'
    if minutes == 5:
        suffix = 'causal_live'
    else:
        suffix = f'causal_live_{minutes}m'
    if require_close_confirm:
        suffix += '_close_confirm'
    if allow_reentry:
        suffix += '_reentry'
    return V2E_ROOT / 'case_studies' / suffix


def _dt(value: str) -> date:
    return pd.Timestamp(value).date()


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _max_dd(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    eq = series.astype(float).cumsum()
    return float((eq - eq.cummax()).min())


def _summary(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {'n': 0, 'sum_net': 0.0, 'wr': 0.0, 'max_dd': 0.0, 'mean_mae': 0.0}
    nets = df['net_usd'].astype(float)
    return {
        'n': int(len(df)),
        'sum_net': float(nets.sum()),
        'wr': float((nets > 0).mean() * 100.0),
        'max_dd': _max_dd(nets),
        'mean_mae': float(df['mae_pts'].astype(float).mean()),
    }


def _sort_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out['_d_sort'] = pd.to_datetime(out['session_day'])
    out['_side_sort'] = out['side'].map(SIDE_ORDER).fillna(99).astype(int)
    if 'attempt_id' not in out.columns:
        out['attempt_id'] = 1
    out = out.sort_values(['_d_sort', '_side_sort', 'sl_family', 'attempt_id']).drop(columns=['_d_sort', '_side_sort'])
    return out.reset_index(drop=True)


def scan_date_range(m1: Path, start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    chunks_for_max: Optional[date] = None
    chunks_for_min: Optional[date] = None
    for ch in pd.read_csv(m1, usecols=['ts_event'], chunksize=800_000):
        ch['ts_event'] = pd.to_datetime(ch['ts_event'], utc=True).dt.tz_convert(NY)
        dpart = ch['ts_event'].dt.date
        cmin, cmax = dpart.min(), dpart.max()
        chunks_for_min = cmin if chunks_for_min is None else min(chunks_for_min, cmin)
        chunks_for_max = cmax if chunks_for_max is None else max(chunks_for_max, cmax)
    if chunks_for_min is None or chunks_for_max is None:
        raise RuntimeError(f'Empty 1m file: {m1}')
    date_min = chunks_for_min
    date_max = chunks_for_max
    if start:
        date_min = max(date_min, _dt(start))
    if end:
        date_max = min(date_max, _dt(end))
    return date_min, date_max


def load_by_day(m1: Path, date_min: date, date_max: date) -> Dict[date, pd.DataFrame]:
    needed = {d for d in iter_calendar_dates(date_min, date_max) if d.weekday() < 5}
    print(f'Loading 1m {m1} (chunked, {len(needed)} target days) ...', flush=True)
    raw = ann.load_1m_for_dates(str(m1), date_min, date_max, needed)
    raw = ann.pick_front_month_day(raw)
    raw['ts_event'] = pd.to_datetime(raw['ts_event'], utc=True).dt.tz_convert(NY)
    raw = raw.set_index('ts_event').sort_index()
    raw['__d'] = raw.index.date
    by_day = {d: g.drop(columns=['__d'], errors='ignore') for d, g in raw.groupby('__d')}
    print(f'  {len(raw):,} 1m front-month bars after date+symbol filter', flush=True)
    return by_day


def collect_trades(
    by_day: Dict[date, pd.DataFrame],
    *,
    sides: Iterable[str],
    sl_families: Iterable[str],
    breaker_minutes: int,
    require_breaker_close_confirm: bool,
    allow_reentry: bool,
    max_reentries: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    audit_rows: List[Dict[str, object]] = []
    for session_day in sorted(by_day):
        if session_day.weekday() >= 5:
            continue
        day_b = by_day[session_day].sort_index()
        if day_b.empty:
            continue
        for side in sides:
            for sl_family in sl_families:
                if allow_reentry:
                    trades, audit = simulate_v2e_causal_session_reentry(
                        day_b,
                        session_day,
                        side=side,  # type: ignore[arg-type]
                        sl_mode=sl_family,
                        breaker_minutes=breaker_minutes,
                        require_breaker_close_confirm=require_breaker_close_confirm,
                        max_reentries=max_reentries,
                    )
                else:
                    trade, audit = simulate_v2e_causal_session(
                        day_b,
                        session_day,
                        side=side,  # type: ignore[arg-type]
                        sl_mode=sl_family,
                        breaker_minutes=breaker_minutes,
                        require_breaker_close_confirm=require_breaker_close_confirm,
                    )
                    trades = [trade] if trade is not None else []
                for a in audit:
                    audit_rows.append({'sl_family': sl_family, **a})
                for trade in trades:
                    row = trade.to_row()
                    row['sl_family'] = sl_family
                    rows.append(row)
    return _sort_trades(pd.DataFrame(rows)), pd.DataFrame(audit_rows)


def validate_causality(df: pd.DataFrame) -> None:
    if df.empty:
        return
    work = df.copy()
    for col in ['fill_time', 'piercer_confirm_time', 'order_live_time', 'breaker_confirm_time', 'setup_commit_time', 'breaker_close_confirm_time']:
        if col in work.columns:
            work[col] = pd.to_datetime(work[col], errors='coerce')
    bad_fill = work[work['fill_time'] <= work['piercer_confirm_time']]
    if not bad_fill.empty:
        raise AssertionError(f'{len(bad_fill)} filled trade(s) violate fill_time > piercer_confirm_time')
    bad_order = work[work['fill_time'] < work['order_live_time']]
    if not bad_order.empty:
        raise AssertionError(f'{len(bad_order)} filled trade(s) violate fill_time >= order_live_time')
    bad_breaker = work[work['breaker_confirm_time'] > work['setup_commit_time']]
    if not bad_breaker.empty:
        raise AssertionError(f'{len(bad_breaker)} trade(s) use breaker before confirmation')
    if 'breaker_close_confirm_required' in work.columns:
        required = work['breaker_close_confirm_required'].astype(str).str.lower().isin({'true', '1', 'yes'})
        missing_close = work[required & work['breaker_close_confirm_time'].isna()]
        if not missing_close.empty:
            raise AssertionError(f'{len(missing_close)} trade(s) require breaker close confirmation but have no confirmation time')
        bad_close = work[required & (work['order_live_time'] < work['breaker_close_confirm_time'])]
        if not bad_close.empty:
            raise AssertionError(f'{len(bad_close)} trade(s) went live before breaker close confirmation')


def print_summaries(df: pd.DataFrame, date_min: date, date_max: date, breaker_minutes: int, require_close_confirm: bool, allow_reentry: bool) -> None:
    confirm_label = ' + close-confirm' if require_close_confirm else ''
    reentry_label = ' + re-entry' if allow_reentry else ''
    print(f'v2e causal live sim — London sweep breaker ({breaker_minutes}m swings{confirm_label}{reentry_label})')
    if df.empty:
        print('No filled trades.')
        return
    for (side, sl_mode), sub in df.groupby(['side', 'sl_mode'], sort=True):
        st = _summary(sub)
        eff = st['sum_net'] / abs(st['max_dd']) if st['max_dd'] else float('nan')
        print(f'\n--- Side={side}  SL={sl_mode} ---')
        print(f'Sessions with trade: {st["n"]}')
        print(f'Σ Net USD (1 MNQ): ${st["sum_net"]:,.2f}')
        print(f'Win rate (Net > 0): {st["wr"]:.2f}%')
        print(f'Max DD (leg cumulative): ${st["max_dd"]:,.2f}')
        print(f'Mean MAE (pts): {st["mean_mae"]:.4f}')
        print(f'Σ Net / |max DD|: {eff:.3f}')
    both = _summary(_sort_trades(df))
    print('\n--- Combined rows in this run ---')
    print(f'Trades: {both["n"]}   Σ Net: ${both["sum_net"]:,.2f}   WR: {both["wr"]:.2f}%   Max DD: ${both["max_dd"]:,.2f}')
    print(f'\nDate range scanned: {date_min} .. {date_max}')


def load_legacy_trades(long_csv: Path, short_csv: Path) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    if long_csv.is_file():
        df = pd.read_csv(long_csv)
        if not df.empty:
            df = df.rename(columns={'session_day': 'session_day'})
            df['side'] = 'long'
            frames.append(df)
    if short_csv.is_file():
        df = pd.read_csv(short_csv)
        if not df.empty:
            df = df.rename(columns={'session_day': 'session_day'})
            df['side'] = 'short'
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out['session_day'] = pd.to_datetime(out['session_day']).dt.date.astype(str)
    keep = ['session_day', 'side', 'entry', 'exit_px', 'net_usd', 'result', 'sl_mode']
    keep = [c for c in keep if c in out.columns]
    out = out[keep].copy()
    return out.rename(
        columns={
            'entry': 'legacy_entry',
            'exit_px': 'legacy_exit_px',
            'net_usd': 'legacy_net_usd',
            'result': 'legacy_result',
            'sl_mode': 'legacy_sl_mode',
        }
    )


def filter_legacy(legacy_df: pd.DataFrame, *, date_min: date, date_max: date, sides: Iterable[str]) -> pd.DataFrame:
    if legacy_df.empty:
        return legacy_df
    side_set = set(sides)
    out = legacy_df.copy()
    d = pd.to_datetime(out['session_day']).dt.date
    out = out[(d >= date_min) & (d <= date_max)]
    out = out[out['side'].isin(side_set)]
    return out.reset_index(drop=True)


def compare_legacy(causal_df: pd.DataFrame, legacy_df: pd.DataFrame, out_path: Optional[Path]) -> pd.DataFrame:
    if causal_df.empty and legacy_df.empty:
        print('Legacy comparison skipped: no causal or legacy rows.')
        return pd.DataFrame()
    c = causal_df.copy()
    c['session_day'] = pd.to_datetime(c['session_day']).dt.date.astype(str)
    c = c.rename(
        columns={
            'entry': 'causal_entry',
            'exit_px': 'causal_exit_px',
            'net_usd': 'causal_net_usd',
            'result': 'causal_result',
            'sl_mode': 'causal_sl_mode',
        }
    )
    ckeep = ['session_day', 'side', 'causal_entry', 'causal_exit_px', 'causal_net_usd', 'causal_result', 'causal_sl_mode']
    c = c[[col for col in ckeep if col in c.columns]]
    merged = c.merge(legacy_df, on=['session_day', 'side'], how='outer', indicator=True)
    if 'causal_net_usd' in merged and 'legacy_net_usd' in merged:
        merged['net_delta_causal_minus_legacy'] = merged['causal_net_usd'].fillna(0) - merged['legacy_net_usd'].fillna(0)

    overlap = merged[merged['_merge'] == 'both']
    causal_only = int((merged['_merge'] == 'left_only').sum())
    legacy_only = int((merged['_merge'] == 'right_only').sum())
    print('\n--- Legacy comparison (current full-session v2e CSVs) ---')
    print(f'Overlap rows: {len(overlap)}   causal-only: {causal_only}   legacy-only: {legacy_only}')
    if not overlap.empty:
        print(f'Overlap causal net: ${overlap["causal_net_usd"].sum():,.2f}')
        print(f'Overlap legacy net: ${overlap["legacy_net_usd"].sum():,.2f}')
        print(f'Overlap delta: ${overlap["net_delta_causal_minus_legacy"].sum():,.2f}')
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(out_path, index=False)
        print(f'Wrote legacy comparison -> {out_path}')
    return merged


def clean_chart_dirs(chart_out: Path) -> None:
    for sub in ['winners', 'losers']:
        d = chart_out / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob('*.png')):
            p.unlink(missing_ok=True)
    idx = chart_out / 'INDEX.md'
    idx.unlink(missing_ok=True)


def stratified_month_sample(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.iloc[0:0]
    work = df.copy()
    work['_ym'] = pd.to_datetime(work['session_day']).dt.to_period('M')
    months = sorted(work['_ym'].unique())
    picked_idx: List[int] = []
    guard = 0
    while len(picked_idx) < n and guard < n * 50:
        guard += 1
        progressed = False
        for ym in months:
            if len(picked_idx) >= n:
                break
            sub = work[~work.index.isin(picked_idx)]
            sub = sub[sub['_ym'] == ym]
            if sub.empty:
                continue
            row = sub.sample(1, random_state=int(rng.integers(1_000_000_000)))
            picked_idx.append(int(row.index[0]))
            progressed = True
        if not progressed:
            break
    remain = n - len(picked_idx)
    if remain > 0:
        pool = work[~work.index.isin(picked_idx)]
        if not pool.empty:
            extra = pool.sample(min(remain, len(pool)), random_state=int(rng.integers(1_000_000_000)))
            picked_idx.extend(int(x) for x in extra.index.tolist())
    return df.loc[[i for i in picked_idx if i in df.index]].head(n).copy()


def _plot_vline(ax, value: object, *, color: str, label: str, linestyle: str = ':') -> None:
    if value is None or pd.isna(value):
        return
    ts = pd.Timestamp(value)
    ax.axvline(
        mdates.date2num(ts.to_pydatetime()),
        color=color,
        linestyle=linestyle,
        linewidth=1.0,
        alpha=0.95,
        label=label,
    )


def _plot_marker(ax, ts_value: object, y_value: object, *, color: str, marker: str, label: str, size: int = 70) -> None:
    if ts_value is None or y_value is None or pd.isna(ts_value) or pd.isna(y_value):
        return
    ts = pd.Timestamp(ts_value)
    ax.scatter(
        [mdates.date2num(ts.to_pydatetime())],
        [float(y_value)],
        color=color,
        edgecolors='#0D1B2A',
        linewidths=0.7,
        marker=marker,
        s=size,
        zorder=8,
        label=label,
    )


def _bar_value_at(day_1m: pd.DataFrame, ts_value: object, column: str, fallback: object = np.nan) -> float:
    if ts_value is None or pd.isna(ts_value):
        return float(fallback) if not pd.isna(fallback) else float('nan')
    ts = pd.Timestamp(ts_value)
    if ts not in day_1m.index or column not in day_1m.columns:
        return float(fallback) if not pd.isna(fallback) else float('nan')
    value = day_1m.loc[ts, column]
    if isinstance(value, pd.Series):
        value = value.iloc[0]
    return float(value)


def opening_15m_range(day_1m: pd.DataFrame, session_day: date) -> Tuple[float, float, pd.Timestamp, pd.Timestamp]:
    start = NY.localize(pd.Timestamp.combine(session_day, RTH_LO))
    end = start + pd.Timedelta(minutes=15)
    sub = day_1m[
        day_1m.index.map(
            lambda t: t.date() == session_day and RTH_LO <= t.time() < end.time()
        )
    ]
    if sub.empty:
        return float('nan'), float('nan'), start, end
    return float(sub['low'].min()), float(sub['high'].max()), start, end


def draw_causal_chart(day_1m: pd.DataFrame, row: pd.Series, outpath: Path) -> bool:
    session_day = pd.Timestamp(row['session_day']).date()
    breaker_minutes = int(row.get('breaker_minutes', 5))
    close_confirm_required = str(row.get('breaker_close_confirm_required', False)).lower() in {'true', '1', 'yes'}
    bars = resample_session_from_02(day_1m, session_day, minutes=breaker_minutes)
    if bars.empty:
        return False

    fig, ax = plt.subplots(figsize=(14, 7), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')

    xnum = mdates.date2num(bars.index.to_pydatetime())
    width = breaker_minutes / (24 * 60) * 0.65
    for xi, (_ts, r) in zip(xnum, bars.iterrows()):
        o, hi, lo, cl = float(r['open']), float(r['high']), float(r['low']), float(r['close'])
        col = '#26A69A' if cl >= o else '#EF5350'
        ax.vlines(xi, lo, hi, color=col, linewidth=0.9, zorder=3)
        body_lo, body_hi = min(o, cl), max(o, cl)
        ax.add_patch(
            mpatches.Rectangle(
                (xi - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )

    if len(bars.index):
        ax.axvspan(
            mdates.date2num(bars.index[0].to_pydatetime()),
            mdates.date2num(NY.localize(pd.Timestamp.combine(session_day, LDN_HI)).to_pydatetime()),
            color='#1F4E79',
            alpha=0.28,
            zorder=0,
        )

    or15_low, or15_high, or15_start, or15_end = opening_15m_range(day_1m, session_day)
    if not pd.isna(or15_low) and not pd.isna(or15_high):
        ax.axvspan(
            mdates.date2num(or15_start.to_pydatetime()),
            mdates.date2num(or15_end.to_pydatetime()),
            color='#455A64',
            alpha=0.26,
            zorder=0,
        )
        ax.axhline(or15_high, color='#FFAB40', linestyle='-.', linewidth=1.15, alpha=0.95, label='OR15 H')
        ax.axhline(or15_low, color='#40C4FF', linestyle='-.', linewidth=1.15, alpha=0.95, label='OR15 L')

    ax.axhline(float(row['london_high']), color='#E0E0E0', linestyle='--', linewidth=1.0, alpha=0.85, label='London H')
    ax.axhline(float(row['london_low']), color='#90CAF9', linestyle='--', linewidth=1.0, alpha=0.9, label='London L')
    ax.axhline(float(row['breaker_high']), color='#FFD54F', linestyle='-', linewidth=1.1, label='Breaker H')
    ax.axhline(float(row['breaker_low']), color='#FFB74D', linestyle=':', linewidth=0.9, alpha=0.85, label='Breaker L')
    ax.axhline(float(row['entry']), color='#80D8FF', linestyle='-', linewidth=1.1, alpha=0.9, label='Entry limit')
    ax.axhline(float(row['tp_px']), color='#76FF03', linestyle='-', linewidth=1.0, alpha=0.85, label='TP')
    ax.axhline(float(row['stop_px']), color='#FF5252', linestyle='-', linewidth=1.0, alpha=0.85, label='SL')

    is_long = str(row['side']).lower() == 'long'
    stop_hunter_y = row['stop_hunter_low'] if is_long else row['stop_hunter_high']
    piercer_y = row['piercer_high'] if is_long else row['piercer_low']
    piercer_confirm_y = _bar_value_at(day_1m, row['piercer_confirm_time'], 'close', piercer_y)

    _plot_vline(ax, row['first_sweep_time'], color='#CE93D8', label='first sweep', linestyle='--')
    _plot_vline(ax, row['breaker_5m_left'], color='#FFCA28', label=f'breaker {breaker_minutes}m', linestyle='--')
    _plot_marker(ax, row['stop_hunter_time'], stop_hunter_y, color='#EA80FC', marker='v' if is_long else '^', label='stop hunter', size=80)
    _plot_marker(ax, row['piercer_time'], piercer_y, color='#FFF176', marker='^' if is_long else 'v', label='piercer', size=80)
    _plot_marker(ax, row['piercer_confirm_time'], piercer_confirm_y, color='#DCE775', marker='>', label='piercer confirm', size=64)
    if close_confirm_required and 'breaker_close_confirm_time' in row:
        _plot_marker(ax, row['breaker_close_confirm_time'], row.get('breaker_close_confirm_px', np.nan), color='#00E5FF', marker='s', label=f'{breaker_minutes}m close confirm', size=62)
    _plot_marker(ax, row['order_live_time'], row['entry'], color='#4FC3F7', marker='D', label='order live', size=58)
    _plot_marker(ax, row['fill_time'], row['entry'], color='#80D8FF', marker='o', label='fill', size=74)
    _plot_marker(ax, row['exit_time'], row['exit_px'], color='#FF8A65', marker='X', label='exit', size=78)

    attempt_id = int(row.get('attempt_id', 1))
    reentry_mode = str(row.get('reentry_mode', False)).lower() in {'true', '1', 'yes'}
    attempt_label = f'  |  Attempt {attempt_id}' if reentry_mode else ''
    title = (
        f'V2E CAUSAL {str(row["side"]).upper()}  {session_day}  |  '
        f'Breaker {breaker_minutes}m{" close-confirm" if close_confirm_required else ""}  |  '
        f'Net ${float(row["net_usd"]):+.2f}  |  {row["result"]}  |  {row["sl_mode"]}  '
        f'| MAE {float(row["mae_pts"]):.1f} pt  | MFE {float(row["mfe_pts"]):.1f} pt{attempt_label}'
    )
    ax.set_title(title, color='#ECEFF1', fontsize=11)
    ax.set_ylabel('Price', color='#B0BEC5')
    ax.grid(True, linestyle=':', alpha=0.25, color='#546E7A')
    ax.tick_params(colors='#B0BEC5')
    ax.legend(loc='upper left', facecolor='#263238', edgecolor='#455A64', labelcolor='#ECEFF1', fontsize=7, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    plt.xticks(rotation=30)
    plt.tight_layout()
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=130, facecolor='#0D1B2A')
    plt.close(fig)
    return True


def legacy_lookup(legacy_df: pd.DataFrame) -> Dict[Tuple[str, str], Tuple[object, object]]:
    out: Dict[Tuple[str, str], Tuple[object, object]] = {}
    if legacy_df.empty:
        return out
    for _, row in legacy_df.iterrows():
        out[(str(row['session_day']), str(row['side']))] = (
            row.get('legacy_net_usd', np.nan),
            row.get('legacy_result', ''),
        )
    return out


def write_charts(
    selected_df: pd.DataFrame,
    by_day: Dict[date, pd.DataFrame],
    chart_out: Path,
    *,
    n_each: int,
    seed: int,
    no_clean: bool,
    legacy_df: pd.DataFrame,
) -> None:
    if selected_df.empty:
        print('No selected rows for charting.')
        return
    if not no_clean:
        clean_chart_dirs(chart_out)
    winners_dir = chart_out / 'winners'
    losers_dir = chart_out / 'losers'
    winners_dir.mkdir(parents=True, exist_ok=True)
    losers_dir.mkdir(parents=True, exist_ok=True)

    wins = selected_df[selected_df['net_usd'].astype(float) > 0].copy()
    losses = selected_df[selected_df['net_usd'].astype(float) <= 0].copy()
    rng = np.random.default_rng(seed)
    sw = stratified_month_sample(wins, n_each, rng)
    sl = stratified_month_sample(losses, n_each, rng)
    lookup = legacy_lookup(legacy_df)
    index_rows: List[Dict[str, object]] = []

    def run_batch(sub: pd.DataFrame, prefix: str, folder: Path) -> None:
        for i, (_, row) in enumerate(sub.iterrows(), 1):
            d = pd.Timestamp(row['session_day']).date()
            day_b = by_day.get(d)
            if day_b is None or day_b.empty:
                print(f'skip chart no 1m {d} {row["side"]}', file=sys.stderr)
                continue
            fname = f'{prefix}_{i:02d}_{d}_{str(row["side"]).capitalize()}.png'
            rel = f'{folder.name}/{fname}'
            out = folder / fname
            if not draw_causal_chart(day_b, row, out):
                print(f'skip chart draw failed {d} {row["side"]}', file=sys.stderr)
                continue
            leg_net, leg_result = lookup.get((d.isoformat(), str(row['side'])), (np.nan, ''))
            index_rows.append(
                {
                    'date': d.isoformat(),
                    'side': row['side'],
                    'attempt_id': int(row.get('attempt_id', 1)),
                    'reentry': str(row.get('reentry_mode', False)).lower() in {'true', '1', 'yes'},
                    'breaker_minutes': int(row.get('breaker_minutes', 5)),
                    'close_confirm': str(row.get('breaker_close_confirm_required', False)).lower() in {'true', '1', 'yes'},
                    'causal_net': float(row['net_usd']),
                    'causal_result': row['result'],
                    'legacy_net': leg_net,
                    'legacy_result': leg_result,
                    'file': rel,
                }
            )
            print(rel)

    run_batch(sw, 'win', winners_dir)
    run_batch(sl, 'loss', losers_dir)

    idx = chart_out / 'INDEX.md'
    breaker_values = sorted({int(x) for x in selected_df.get('breaker_minutes', pd.Series([5])).dropna().unique()})
    breaker_label = ', '.join(f'{x}m' for x in breaker_values) if breaker_values else '5m'
    close_confirm = False
    if 'breaker_close_confirm_required' in selected_df.columns:
        close_confirm = selected_df['breaker_close_confirm_required'].astype(str).str.lower().isin({'true', '1', 'yes'}).any()
    reentry = False
    if 'reentry_mode' in selected_df.columns:
        reentry = selected_df['reentry_mode'].astype(str).str.lower().isin({'true', '1', 'yes'}).any()
    lines = [
        f'# v2e causal live charts ({breaker_label} breaker{" close-confirm" if close_confirm else ""}{" re-entry" if reentry else ""})',
        '',
        'Strict next-bar causal simulation. Charts are split into `winners/` and `losers/`.',
        '',
        '| Date | Side | Attempt | Breaker | Close Confirm | Causal Net | Causal Result | Legacy Net | Legacy Result | Chart |',
        '|---|:---:|---:|:---:|:---:|---:|---|---:|---|---|',
    ]
    for r in sorted(index_rows, key=lambda x: (x['date'], x['side'], x['file'])):
        legacy_net = r['legacy_net']
        legacy_net_s = '' if pd.isna(legacy_net) else f'{float(legacy_net):+.2f}'
        lines.append(
            f"| {r['date']} | {r['side']} | {int(r['attempt_id']) if r['reentry'] else 1} | "
            f"{int(r['breaker_minutes'])}m | {'yes' if r['close_confirm'] else 'no'} | "
            f"{float(r['causal_net']):+.2f} | {r['causal_result']} | "
            f"{legacy_net_s} | {r['legacy_result']} | [{r['file']}]({r['file']}) |"
        )
    idx.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Wrote {len(index_rows)} charts under {chart_out}\nWrote {idx}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--1m', dest='m1', type=Path, default=DEFAULT_M1)
    ap.add_argument('--start', type=str, default=None, help='YYYY-MM-DD inclusive')
    ap.add_argument('--end', type=str, default=None, help='YYYY-MM-DD inclusive')
    ap.add_argument('--sl-at', choices=SL_CHOICES, default='stop_hunter')
    ap.add_argument('--all-sl', action='store_true')
    ap.add_argument('--export-csv', type=Path, default=None)
    ap.add_argument('--side', choices=['long', 'short', 'both'], default='both')
    ap.add_argument('--breaker-minutes', type=int, default=5, help='Breaker swing timeframe in minutes; 5 is the baseline, 15 is the larger-swing variant.')
    ap.add_argument('--require-breaker-close-confirm', action='store_true', help='Require a completed breaker-timeframe close beyond the breaker before the entry limit goes live.')
    ap.add_argument('--allow-reentry', action='store_true', help='After an attempt exits, replace the swept London boundary with the stop-hunter extreme and search again.')
    ap.add_argument('--max-reentries', type=int, default=3, help='Maximum additional same-side attempts per session when --allow-reentry is set.')
    ap.add_argument('--audit-csv', type=Path, default=None)
    ap.add_argument('--compare-legacy', action='store_true')
    ap.add_argument('--legacy-long-csv', type=Path, default=DEFAULT_LEGACY_LONG)
    ap.add_argument('--legacy-short-csv', type=Path, default=DEFAULT_LEGACY_SHORT)
    ap.add_argument('--charts', action='store_true')
    ap.add_argument('--chart-out', type=Path, default=None)
    ap.add_argument('--n-each', type=int, default=25)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--no-clean-charts', action='store_true')
    args = ap.parse_args()

    if not args.m1.is_file():
        print(f'Missing 1m file {args.m1}', file=sys.stderr)
        return 1
    if args.breaker_minutes <= 0:
        print(f'--breaker-minutes must be positive, got {args.breaker_minutes}', file=sys.stderr)
        return 1
    if args.max_reentries < 0:
        print(f'--max-reentries must be >= 0, got {args.max_reentries}', file=sys.stderr)
        return 1

    selected_family = normalize_v2e_sl_mode(args.sl_at)
    sl_families = ['london', 'breaker', 'stop_hunter'] if args.all_sl else [selected_family]
    sides = ['long', 'short'] if args.side == 'both' else [args.side]
    chart_out = args.chart_out or default_chart_out_for_breaker(
        args.breaker_minutes,
        require_close_confirm=args.require_breaker_close_confirm,
        allow_reentry=args.allow_reentry,
    )

    date_min, date_max = scan_date_range(args.m1, args.start, args.end)
    by_day = load_by_day(args.m1, date_min, date_max)
    all_df, audit_df = collect_trades(
        by_day,
        sides=sides,
        sl_families=sl_families,
        breaker_minutes=args.breaker_minutes,
        require_breaker_close_confirm=args.require_breaker_close_confirm,
        allow_reentry=args.allow_reentry,
        max_reentries=args.max_reentries,
    )
    validate_causality(all_df)
    print_summaries(all_df, date_min, date_max, args.breaker_minutes, args.require_breaker_close_confirm, args.allow_reentry)

    selected_df = all_df[all_df['sl_family'] == selected_family].copy() if not all_df.empty else all_df
    selected_df = _sort_trades(selected_df)
    validate_causality(selected_df)

    if args.export_csv:
        args.export_csv.parent.mkdir(parents=True, exist_ok=True)
        selected_df.to_csv(args.export_csv, index=False)
        print(f'Wrote selected causal rows -> {args.export_csv}')
    if args.audit_csv:
        args.audit_csv.parent.mkdir(parents=True, exist_ok=True)
        audit_df.to_csv(args.audit_csv, index=False)
        print(f'Wrote audit rows -> {args.audit_csv}')

    legacy_df = pd.DataFrame()
    if args.compare_legacy or args.charts:
        legacy_df = load_legacy_trades(args.legacy_long_csv, args.legacy_short_csv)
        legacy_df = filter_legacy(legacy_df, date_min=date_min, date_max=date_max, sides=sides)
    if args.compare_legacy:
        compare_path = None
        if args.export_csv:
            compare_path = args.export_csv.with_suffix(args.export_csv.suffix + '.legacy_compare.csv')
        compare_legacy(selected_df, legacy_df, compare_path)
    if args.charts:
        write_charts(
            selected_df,
            by_day,
            chart_out,
            n_each=args.n_each,
            seed=args.seed,
            no_clean=args.no_clean_charts,
            legacy_df=legacy_df,
        )

    if args.export_csv is None:
        print(f'\nTip: add --export-csv {DEFAULT_OUT_CSV} to persist the selected causal trade log.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
