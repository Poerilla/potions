#!/usr/bin/env python3
"""Monthly candlestick theory continuation study.

Pattern:
- Candle 1 defines its high/low.
- Candle 2 must take and close beyond Candle 1's high/low.
- Candle 3 is expected to take Candle 2's continuation extreme.

Failure sweeps, where Candle 2 takes a Candle 1 extreme but does not close
beyond it, are counted as skipped context and excluded from the signal set.

Strategy backtest (breakout-candle entry):
  Opening candle = first daily bar of C3.
  R = opening_candle_high - opening_candle_low.
  Breakout candle (bull): first subsequent C3 bar whose close > opening_candle_high.
  Breakout candle (bear): first subsequent C3 bar whose close < opening_candle_low.
  Entry:  breakout candle close.
  SL:     entry - 2*R (bull) / entry + 2*R (bear).
  TP:     entry + tp_mult*R (bull) / entry - tp_mult*R (bear).
  Tested for tp_mult = 2 and tp_mult = 3.
  Tracking starts on the bar AFTER the breakout candle.
  Same-bar TP+SL conflict resolves to SL (conservative).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
BLUE = '#40C4FF'
YELLOW = '#FFC107'
PURPLE = '#EA80FC'
GRAY = '#CFD8DC'
ORANGE = '#FF7043'
TEAL = '#00BCD4'


def aggregate_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily[['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']].copy()
    work['date'] = pd.to_datetime(work['date'])
    work['_month'] = work['date'].dt.to_period('M')
    rows: list[dict] = []
    for month, group in work.groupby('_month', sort=True):
        rows.append(
            {
                'month': str(month),
                'date': pd.Timestamp(group.iloc[-1]['date']),
                'open': float(group.iloc[0]['open']),
                'high': float(group['high'].max()),
                'low': float(group['low'].min()),
                'close': float(group.iloc[-1]['close']),
                'volume': float(group['volume'].sum()),
                'symbol': str(group.iloc[-1]['symbol']),
            }
        )
    return pd.DataFrame(rows)


def classify_setups(monthly: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    skipped = {
        'high_failure_sweeps': 0,
        'low_failure_sweeps': 0,
        'unique_failure_sweep_months': 0,
        'non_signal_months': 0,
    }
    for i in range(0, len(monthly) - 2):
        c1 = monthly.iloc[i]
        c2 = monthly.iloc[i + 1]
        c3 = monthly.iloc[i + 2]

        took_high = float(c2['high']) > float(c1['high'])
        closed_above = float(c2['close']) > float(c1['high'])
        took_low = float(c2['low']) < float(c1['low'])
        closed_below = float(c2['close']) < float(c1['low'])

        high_failure = took_high and not closed_above
        low_failure = took_low and not closed_below
        is_bull = took_high and closed_above
        is_bear = took_low and closed_below

        if high_failure:
            skipped['high_failure_sweeps'] += 1
        if low_failure:
            skipped['low_failure_sweeps'] += 1
        if (high_failure or low_failure) and not (is_bull or is_bear):
            skipped['unique_failure_sweep_months'] += 1

        if is_bull:
            target = float(c2['high'])
            took_c2_extreme = float(c3['high']) > target
            closed_beyond_c2 = float(c3['close']) > target
            extension = float(c3['high']) - target
            adverse = max(0.0, float(c2['low']) - float(c3['low']))
            direction = 'bullish'
            c1_level = float(c1['high'])
            c2_extreme = float(c2['high'])
        elif is_bear:
            target = float(c2['low'])
            took_c2_extreme = float(c3['low']) < target
            closed_beyond_c2 = float(c3['close']) < target
            extension = target - float(c3['low'])
            adverse = max(0.0, float(c3['high']) - float(c2['high']))
            direction = 'bearish'
            c1_level = float(c1['low'])
            c2_extreme = float(c2['low'])
        else:
            skipped['non_signal_months'] += 1
            continue

        rows.append(
            {
                'setup_id': len(rows) + 1,
                'direction': direction,
                'c1_month': c1['month'],
                'c2_month': c2['month'],
                'c3_month': c3['month'],
                'c1_open': round(float(c1['open']), 2),
                'c1_high': round(float(c1['high']), 2),
                'c1_low': round(float(c1['low']), 2),
                'c1_close': round(float(c1['close']), 2),
                'c2_open': round(float(c2['open']), 2),
                'c2_high': round(float(c2['high']), 2),
                'c2_low': round(float(c2['low']), 2),
                'c2_close': round(float(c2['close']), 2),
                'c3_open': round(float(c3['open']), 2),
                'c3_high': round(float(c3['high']), 2),
                'c3_low': round(float(c3['low']), 2),
                'c3_close': round(float(c3['close']), 2),
                'c1_break_level': round(c1_level, 2),
                'c2_expected_extreme': round(c2_extreme, 2),
                'c2_swept_both_sides': bool(took_high and took_low),
                'c3_took_c2_extreme': bool(took_c2_extreme),
                'c3_closed_beyond_c2_extreme': bool(closed_beyond_c2),
                'hit': bool(took_c2_extreme or closed_beyond_c2),
                'extension_pts': round(extension, 2),
                'adverse_vs_c2_range_pts': round(adverse, 2),
                'c3_body_direction': 'up' if float(c3['close']) >= float(c3['open']) else 'down',
            }
        )
    return pd.DataFrame(rows), skipped


def summarize(setups: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for direction, group in setups.groupby('direction', sort=True):
        hits = group[group['hit']].copy()
        rows.append(
            {
                'direction': direction,
                'setups': len(group),
                'hits': int(group['hit'].sum()),
                'hit_rate': round(float(group['hit'].mean()) * 100, 2),
                'closed_beyond_count': int(group['c3_closed_beyond_c2_extreme'].sum()),
                'closed_beyond_rate': round(float(group['c3_closed_beyond_c2_extreme'].mean()) * 100, 2),
                'avg_extension_pts': round(float(hits['extension_pts'].mean()), 2) if not hits.empty else 0.0,
                'median_extension_pts': round(float(hits['extension_pts'].median()), 2) if not hits.empty else 0.0,
                'avg_adverse_pts': round(float(group['adverse_vs_c2_range_pts'].mean()), 2),
                'worst_adverse_pts': round(float(group['adverse_vs_c2_range_pts'].max()), 2),
            }
        )
    if not setups.empty:
        hits = setups[setups['hit']].copy()
        rows.append(
            {
                'direction': 'all',
                'setups': len(setups),
                'hits': int(setups['hit'].sum()),
                'hit_rate': round(float(setups['hit'].mean()) * 100, 2),
                'closed_beyond_count': int(setups['c3_closed_beyond_c2_extreme'].sum()),
                'closed_beyond_rate': round(float(setups['c3_closed_beyond_c2_extreme'].mean()) * 100, 2),
                'avg_extension_pts': round(float(hits['extension_pts'].mean()), 2) if not hits.empty else 0.0,
                'median_extension_pts': round(float(hits['extension_pts'].median()), 2) if not hits.empty else 0.0,
                'avg_adverse_pts': round(float(setups['adverse_vs_c2_range_pts'].mean()), 2),
                'worst_adverse_pts': round(float(setups['adverse_vs_c2_range_pts'].max()), 2),
            }
        )
    return pd.DataFrame(rows)


def simulate_strat(daily: pd.DataFrame, setups: pd.DataFrame, tp_mult: float = 2.0) -> pd.DataFrame:
    """Backtest the breakout-candle entry strategy.

    Opening candle = first daily bar of C3.  R = its high - low.
    Breakout candle (bull): first C3 bar (after day 1) that closes above opening high.
    Breakout candle (bear): first C3 bar (after day 1) that closes below opening low.
    Entry at breakout candle close.  SL = entry ± 2R.  TP = entry ± tp_mult*R.
    Tracking starts the bar after the breakout candle.
    Same-bar TP+SL → SL (conservative).
    PnL expressed as multiples of base R (= opening candle range).
    """
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    results: list[dict] = []

    for _, setup in setups.iterrows():
        direction = str(setup['direction'])
        c3_period = pd.Period(str(setup['c3_month']), freq='M')
        c3_bars = (
            work[work['date'].dt.to_period('M').eq(c3_period)]
            .sort_values('date')
            .reset_index(drop=True)
        )

        def _no_fill(reason: str) -> dict:
            return {
                'setup_id': int(setup['setup_id']),
                'direction': direction,
                'c3_month': setup['c3_month'],
                'oc_high': None,
                'oc_low': None,
                'base_r': None,
                'breakout_day': None,
                'breakout_date': None,
                'entry': None,
                'sl': None,
                'tp': None,
                'outcome': reason,
                'pnl_r': 0.0,
                'pnl_pts': 0.0,
                'mae_pts': 0.0,
                'mae_r': 0.0,
                'days_to_outcome': None,
                'outcome_date': None,
                'swept_opposing_before_breakout': False,
                'clean_body_run_to_tp': False,
            }

        if len(c3_bars) < 2:
            results.append(_no_fill('no_breakout'))
            continue

        oc = c3_bars.iloc[0]
        oc_high = float(oc['high'])
        oc_low = float(oc['low'])
        base_r = oc_high - oc_low

        if base_r <= 0:
            results.append(_no_fill('no_breakout'))
            continue

        # Find breakout candle (starting from bar index 1)
        breakout_idx: Optional[int] = None
        for i in range(1, len(c3_bars)):
            bar = c3_bars.iloc[i]
            if direction == 'bullish' and float(bar['close']) > oc_high:
                breakout_idx = i
                break
            elif direction == 'bearish' and float(bar['close']) < oc_low:
                breakout_idx = i
                break

        if breakout_idx is None:
            results.append(_no_fill('no_breakout'))
            continue

        bk = c3_bars.iloc[breakout_idx]
        entry = float(bk['close'])
        breakout_date = bk['date']

        if direction == 'bullish':
            sl = entry - 2.0 * base_r
            tp = entry + tp_mult * base_r
        else:
            sl = entry + 2.0 * base_r
            tp = entry - tp_mult * base_r

        # Swept opposing: any bar BETWEEN OC and breakout traded through OC's opposing extreme
        pre_bk = c3_bars.iloc[1:breakout_idx]  # bars after OC, before breakout
        if direction == 'bullish':
            swept_opposing = bool(not pre_bk.empty and (pre_bk['low'].astype(float) < oc_low).any())
        else:
            swept_opposing = bool(not pre_bk.empty and (pre_bk['high'].astype(float) > oc_high).any())

        # Track from the bar AFTER the breakout candle
        post_entry = c3_bars.iloc[breakout_idx + 1:].reset_index(drop=True)

        outcome = 'open_eom'
        outcome_date = None
        days_to_outcome: Optional[int] = None
        mae_pts = 0.0
        pnl_r = 0.0
        pnl_pts = 0.0

        for day_n, bar in post_entry.iterrows():
            bar_h = float(bar['high'])
            bar_l = float(bar['low'])

            if direction == 'bullish':
                mae_pts = max(mae_pts, max(0.0, entry - bar_l))
                hit_sl = bar_l <= sl
                hit_tp = bar_h >= tp
                if hit_sl and hit_tp:
                    outcome, pnl_r, pnl_pts = 'sl', -2.0, -2.0 * base_r
                elif hit_tp:
                    outcome, pnl_r, pnl_pts = 'tp', tp_mult, tp_mult * base_r
                elif hit_sl:
                    outcome, pnl_r, pnl_pts = 'sl', -2.0, -2.0 * base_r
            else:
                mae_pts = max(mae_pts, max(0.0, bar_h - entry))
                hit_sl = bar_h >= sl
                hit_tp = bar_l <= tp
                if hit_sl and hit_tp:
                    outcome, pnl_r, pnl_pts = 'sl', -2.0, -2.0 * base_r
                elif hit_tp:
                    outcome, pnl_r, pnl_pts = 'tp', tp_mult, tp_mult * base_r
                elif hit_sl:
                    outcome, pnl_r, pnl_pts = 'sl', -2.0, -2.0 * base_r

            if outcome in ('tp', 'sl'):
                outcome_date = bar['date']
                days_to_outcome = int(day_n) + 1
                break

        # MAE as a fraction of the full SL distance (2*R)
        mae_r = round(mae_pts / (2.0 * base_r), 3) if base_r > 0 else 0.0

        # Clean body run to TP: from breakout bar through TP bar, all closes on correct side of OC boundary
        clean_body = False
        if outcome == 'tp' and days_to_outcome is not None:
            bk_to_tp = c3_bars.iloc[breakout_idx: breakout_idx + 1 + days_to_outcome]
            if direction == 'bullish':
                clean_body = bool((bk_to_tp['close'].astype(float) >= oc_high).all())
            else:
                clean_body = bool((bk_to_tp['close'].astype(float) <= oc_low).all())

        results.append({
            'setup_id': int(setup['setup_id']),
            'direction': direction,
            'c3_month': setup['c3_month'],
            'oc_high': round(oc_high, 2),
            'oc_low': round(oc_low, 2),
            'base_r': round(base_r, 2),
            'breakout_day': breakout_idx + 1,  # 1-based trading day within C3
            'breakout_date': str(pd.Timestamp(breakout_date).date()),
            'entry': round(entry, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'outcome': outcome,
            'pnl_r': pnl_r,
            'pnl_pts': round(pnl_pts, 2),
            'mae_pts': round(mae_pts, 2),
            'mae_r': mae_r,
            'days_to_outcome': days_to_outcome,
            'outcome_date': (str(pd.Timestamp(outcome_date).date()) if outcome_date is not None else None),
            'swept_opposing_before_breakout': swept_opposing,
            'clean_body_run_to_tp': clean_body,
        })

    return pd.DataFrame(results)


def strat_summary(strat: pd.DataFrame, tp_mult: float) -> pd.DataFrame:
    rows: list[dict] = []
    for direction in ['bullish', 'bearish', 'all']:
        total = strat if direction == 'all' else strat[strat['direction'] == direction]
        if total.empty:
            continue
        resolved = total[total['outcome'].isin(['tp', 'sl'])]
        tp_t = resolved[resolved['outcome'] == 'tp']
        sl_t = resolved[resolved['outcome'] == 'sl']
        n = len(resolved)

        with_bk = total[total['outcome'] != 'no_breakout']
        n_bk = len(with_bk)
        n_swept = int(with_bk['swept_opposing_before_breakout'].fillna(False).sum()) if n_bk > 0 else 0
        pct_swept = round(n_swept / n_bk * 100, 1) if n_bk > 0 else 0.0
        n_clean = int(tp_t['clean_body_run_to_tp'].fillna(False).sum()) if not tp_t.empty else 0
        pct_clean = round(n_clean / len(tp_t) * 100, 1) if not tp_t.empty else 0.0

        rows.append(
            {
                'direction': direction,
                'tp_mult': tp_mult,
                'setups': len(total),
                'no_breakout': int((total['outcome'] == 'no_breakout').sum()),
                'resolved': n,
                'open_eom': int((total['outcome'] == 'open_eom').sum()),
                'tp': len(tp_t),
                'sl': len(sl_t),
                'hit_rate_pct': round(len(tp_t) / n * 100, 2) if n > 0 else 0.0,
                'avg_mae_r': round(float(resolved['mae_r'].mean()), 3) if n > 0 else 0.0,
                'avg_mae_pts': round(float(resolved['mae_pts'].mean()), 2) if n > 0 else 0.0,
                'avg_breakout_day': round(float(total[total['breakout_day'].notna()]['breakout_day'].mean()), 1),
                'avg_days_tp': (round(float(tp_t['days_to_outcome'].mean()), 1) if not tp_t.empty else None),
                'avg_days_sl': (round(float(sl_t['days_to_outcome'].mean()), 1) if not sl_t.empty else None),
                'total_pnl_r': round(float(resolved['pnl_r'].sum()), 2),
                'total_pnl_pts': round(float(resolved['pnl_pts'].sum()), 2),
                'n_swept_opposing': n_swept,
                'pct_swept_opposing': pct_swept,
                'n_clean_body_tp': n_clean,
                'pct_clean_body_tp': pct_clean,
            }
        )
    return pd.DataFrame(rows)


def simulate_strat_clean_body(daily: pd.DataFrame, setups: pd.DataFrame, tp_mult: float = 2.0) -> pd.DataFrame:
    """Clean-body-exit variant.

    Same entry as the base strat (breakout candle close).
    Exit rule: exit when any post-breakout bar CLOSES back through the OC boundary
      (close < OC_high for bull, close > OC_low for bear).
    TP: entry ± tp_mult*R (same as original).
    On a bar where TP is reached intraday AND close crosses the boundary → TP wins.
    PnL normalised by base_R (= OC range).
    """
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    results: list[dict] = []

    for _, setup in setups.iterrows():
        direction = str(setup['direction'])
        c3_period = pd.Period(str(setup['c3_month']), freq='M')
        c3_bars = (
            work[work['date'].dt.to_period('M').eq(c3_period)]
            .sort_values('date').reset_index(drop=True)
        )

        def _skip(reason: str) -> dict:
            return {
                'setup_id': int(setup['setup_id']), 'direction': direction,
                'c3_month': setup['c3_month'], 'oc_high': None, 'oc_low': None,
                'base_r': None, 'breakout_day': None, 'breakout_date': None,
                'entry': None, 'tp': None, 'outcome': reason,
                'pnl_pts': 0.0, 'pnl_r': 0.0, 'mae_pts': 0.0, 'mae_r': 0.0,
                'days_to_outcome': None, 'outcome_date': None,
            }

        if len(c3_bars) < 2:
            results.append(_skip('no_breakout'))
            continue
        oc = c3_bars.iloc[0]
        oc_high, oc_low = float(oc['high']), float(oc['low'])
        base_r = oc_high - oc_low
        if base_r <= 0:
            results.append(_skip('no_breakout'))
            continue

        breakout_idx: Optional[int] = None
        for i in range(1, len(c3_bars)):
            bar = c3_bars.iloc[i]
            if direction == 'bullish' and float(bar['close']) > oc_high:
                breakout_idx = i; break
            elif direction == 'bearish' and float(bar['close']) < oc_low:
                breakout_idx = i; break
        if breakout_idx is None:
            results.append(_skip('no_breakout'))
            continue

        bk = c3_bars.iloc[breakout_idx]
        entry = float(bk['close'])
        tp = entry + tp_mult * base_r if direction == 'bullish' else entry - tp_mult * base_r

        post_entry = c3_bars.iloc[breakout_idx + 1:].reset_index(drop=True)
        outcome, outcome_date = 'open_eom', None
        days_to_outcome: Optional[int] = None
        mae_pts = pnl_pts = pnl_r = 0.0

        for day_n, bar in post_entry.iterrows():
            bar_h, bar_l, bar_c = float(bar['high']), float(bar['low']), float(bar['close'])
            if direction == 'bullish':
                mae_pts = max(mae_pts, max(0.0, entry - bar_l))
                if bar_h >= tp:
                    outcome, pnl_pts, pnl_r = 'tp', tp_mult * base_r, tp_mult
                elif bar_c < oc_high:
                    outcome, pnl_pts, pnl_r = 'close_exit', bar_c - entry, (bar_c - entry) / base_r
            else:
                mae_pts = max(mae_pts, max(0.0, bar_h - entry))
                if bar_l <= tp:
                    outcome, pnl_pts, pnl_r = 'tp', tp_mult * base_r, tp_mult
                elif bar_c > oc_low:
                    outcome, pnl_pts, pnl_r = 'close_exit', entry - bar_c, (entry - bar_c) / base_r
            if outcome in ('tp', 'close_exit'):
                outcome_date = bar['date']
                days_to_outcome = int(day_n) + 1
                break

        results.append({
            'setup_id': int(setup['setup_id']), 'direction': direction,
            'c3_month': setup['c3_month'],
            'oc_high': round(oc_high, 2), 'oc_low': round(oc_low, 2), 'base_r': round(base_r, 2),
            'breakout_day': breakout_idx + 1,
            'breakout_date': str(pd.Timestamp(bk['date']).date()),
            'entry': round(entry, 2), 'tp': round(tp, 2),
            'outcome': outcome,
            'pnl_pts': round(pnl_pts, 2), 'pnl_r': round(pnl_r, 3),
            'mae_pts': round(mae_pts, 2),
            'mae_r': round(mae_pts / base_r, 3) if base_r > 0 else 0.0,
            'days_to_outcome': days_to_outcome,
            'outcome_date': (str(pd.Timestamp(outcome_date).date()) if outcome_date is not None else None),
        })
    return pd.DataFrame(results)


def simulate_strat_swept_opposing(daily: pd.DataFrame, setups: pd.DataFrame, tp_mult: float = 2.0) -> pd.DataFrame:
    """Swept-opposing-only variant.

    Only takes setups where a bar between OC and the breakout candle traded through OC's
    opposing extreme (low < OC_low for bull, high > OC_high for bear).
    SL: OC_low (bull) / OC_high (bear) — structural level at the swept opposing extreme.
    TP: entry ± tp_mult*R (same targets as original, R = OC range).
    Setups without an opposing sweep are marked 'skip'.
    PnL reported in both points and R (normalised by OC range).
    """
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    results: list[dict] = []

    for _, setup in setups.iterrows():
        direction = str(setup['direction'])
        c3_period = pd.Period(str(setup['c3_month']), freq='M')
        c3_bars = (
            work[work['date'].dt.to_period('M').eq(c3_period)]
            .sort_values('date').reset_index(drop=True)
        )

        def _skip(reason: str) -> dict:
            return {
                'setup_id': int(setup['setup_id']), 'direction': direction,
                'c3_month': setup['c3_month'], 'oc_high': None, 'oc_low': None,
                'base_r': None, 'swept_opposing': False,
                'breakout_day': None, 'breakout_date': None,
                'entry': None, 'sl': None, 'tp': None, 'risk_pts': None,
                'outcome': reason, 'pnl_pts': 0.0, 'pnl_r': 0.0,
                'mae_pts': 0.0, 'mae_r': 0.0,
                'days_to_outcome': None, 'outcome_date': None,
            }

        if len(c3_bars) < 2:
            results.append(_skip('no_breakout'))
            continue
        oc = c3_bars.iloc[0]
        oc_high, oc_low = float(oc['high']), float(oc['low'])
        base_r = oc_high - oc_low
        if base_r <= 0:
            results.append(_skip('no_breakout'))
            continue

        breakout_idx: Optional[int] = None
        for i in range(1, len(c3_bars)):
            bar = c3_bars.iloc[i]
            if direction == 'bullish' and float(bar['close']) > oc_high:
                breakout_idx = i; break
            elif direction == 'bearish' and float(bar['close']) < oc_low:
                breakout_idx = i; break
        if breakout_idx is None:
            results.append(_skip('no_breakout'))
            continue

        pre_bk = c3_bars.iloc[1:breakout_idx]
        if direction == 'bullish':
            swept = bool(not pre_bk.empty and (pre_bk['low'].astype(float) < oc_low).any())
        else:
            swept = bool(not pre_bk.empty and (pre_bk['high'].astype(float) > oc_high).any())
        if not swept:
            results.append(_skip('skip'))
            continue

        bk = c3_bars.iloc[breakout_idx]
        entry = float(bk['close'])
        if direction == 'bullish':
            sl, tp = oc_low, entry + tp_mult * base_r
        else:
            sl, tp = oc_high, entry - tp_mult * base_r
        risk_pts = abs(entry - sl)

        post_entry = c3_bars.iloc[breakout_idx + 1:].reset_index(drop=True)
        outcome, outcome_date = 'open_eom', None
        days_to_outcome: Optional[int] = None
        mae_pts = pnl_pts = pnl_r = 0.0

        for day_n, bar in post_entry.iterrows():
            bar_h, bar_l = float(bar['high']), float(bar['low'])
            if direction == 'bullish':
                mae_pts = max(mae_pts, max(0.0, entry - bar_l))
                hit_sl, hit_tp = bar_l <= sl, bar_h >= tp
                if hit_sl and hit_tp:
                    outcome, pnl_pts, pnl_r = 'sl', sl - entry, (sl - entry) / base_r
                elif hit_tp:
                    outcome, pnl_pts, pnl_r = 'tp', tp_mult * base_r, tp_mult
                elif hit_sl:
                    outcome, pnl_pts, pnl_r = 'sl', sl - entry, (sl - entry) / base_r
            else:
                mae_pts = max(mae_pts, max(0.0, bar_h - entry))
                hit_sl, hit_tp = bar_h >= sl, bar_l <= tp
                if hit_sl and hit_tp:
                    outcome, pnl_pts, pnl_r = 'sl', entry - sl, (entry - sl) / base_r
                elif hit_tp:
                    outcome, pnl_pts, pnl_r = 'tp', tp_mult * base_r, tp_mult
                elif hit_sl:
                    outcome, pnl_pts, pnl_r = 'sl', entry - sl, (entry - sl) / base_r
            if outcome in ('tp', 'sl'):
                outcome_date = bar['date']
                days_to_outcome = int(day_n) + 1
                break

        results.append({
            'setup_id': int(setup['setup_id']), 'direction': direction,
            'c3_month': setup['c3_month'],
            'oc_high': round(oc_high, 2), 'oc_low': round(oc_low, 2), 'base_r': round(base_r, 2),
            'swept_opposing': True,
            'breakout_day': breakout_idx + 1,
            'breakout_date': str(pd.Timestamp(bk['date']).date()),
            'entry': round(entry, 2), 'sl': round(sl, 2), 'tp': round(tp, 2),
            'risk_pts': round(risk_pts, 2),
            'outcome': outcome,
            'pnl_pts': round(pnl_pts, 2), 'pnl_r': round(pnl_r, 3),
            'mae_pts': round(mae_pts, 2),
            'mae_r': round(mae_pts / base_r, 3) if base_r > 0 else 0.0,
            'days_to_outcome': days_to_outcome,
            'outcome_date': (str(pd.Timestamp(outcome_date).date()) if outcome_date is not None else None),
        })
    return pd.DataFrame(results)


def strat_variant_summary(strat: pd.DataFrame, tp_mult: float, variant: str) -> pd.DataFrame:
    rows: list[dict] = []
    for direction in ['bullish', 'bearish', 'all']:
        total = strat if direction == 'all' else strat[strat['direction'] == direction]
        if total.empty:
            continue
        active = total[~total['outcome'].isin(['skip', 'no_breakout'])]
        resolved = active[active['outcome'].isin(['tp', 'close_exit', 'sl'])]
        tp_t = resolved[resolved['outcome'] == 'tp']
        loss_t = resolved[resolved['outcome'].isin(['close_exit', 'sl'])]
        n = len(resolved)
        rows.append({
            'direction': direction, 'tp_mult': tp_mult, 'variant': variant,
            'active_setups': len(active),
            'no_breakout': int((total['outcome'] == 'no_breakout').sum()),
            'skipped': int((total['outcome'] == 'skip').sum()),
            'resolved': n,
            'open_eom': int((active['outcome'] == 'open_eom').sum()),
            'tp': len(tp_t), 'loss': len(loss_t),
            'hit_rate_pct': round(len(tp_t) / n * 100, 2) if n > 0 else 0.0,
            'avg_mae_r': round(float(resolved['mae_r'].mean()), 3) if n > 0 else 0.0,
            'avg_mae_pts': round(float(resolved['mae_pts'].mean()), 2) if n > 0 else 0.0,
            'avg_days_tp': (round(float(tp_t['days_to_outcome'].mean()), 1) if not tp_t.empty else None),
            'avg_days_loss': (round(float(loss_t['days_to_outcome'].mean()), 1) if not loss_t.empty else None),
            'total_pnl_pts': round(float(resolved['pnl_pts'].sum()), 2),
            'total_pnl_r': round(float(resolved['pnl_r'].sum()), 2),
        })
    return pd.DataFrame(rows)


def style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.grid(True, alpha=0.15, color=GRID)
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')


def draw_candles(ax: plt.Axes, bars: pd.DataFrame, width_scale: float = 0.62) -> None:
    dates = pd.to_datetime(bars['date'])
    x = mdates.date2num(dates)
    if len(x) > 1:
        width = float(pd.Series(x).diff().dropna().median()) * width_scale
    else:
        width = 16
    for xval, (_, row) in zip(x, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=color, linewidth=0.9, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (xval - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.92,
                zorder=3,
            )
        )


def setup_chart(monthly: pd.DataFrame, setup: pd.Series, out_path: Path, market: str) -> str:
    c3_idx = int(monthly.index[monthly['month'].eq(setup['c3_month'])][0])
    start = max(0, c3_idx - 8)
    end = min(len(monthly), c3_idx + 7)
    bars = monthly.iloc[start:end].copy()

    fig = plt.figure(figsize=(15, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, bars)

    c1 = bars[bars['month'].eq(setup['c1_month'])].iloc[0]
    c2 = bars[bars['month'].eq(setup['c2_month'])].iloc[0]
    c3 = bars[bars['month'].eq(setup['c3_month'])].iloc[0]
    c3_x = mdates.date2num(pd.Timestamp(c3['date']))
    ax.axvspan(c3_x - 18, c3_x + 18, color=BLUE if setup['hit'] else RED, alpha=0.16, zorder=1)

    c1_break = float(setup['c1_break_level'])
    c2_extreme = float(setup['c2_expected_extreme'])
    x0 = mdates.date2num(pd.Timestamp(c1['date'])) - 20
    x3 = mdates.date2num(pd.Timestamp(c3['date'])) + 20
    ax.hlines(c1_break, x0, x3, color=YELLOW, linestyle=':', linewidth=1.2, zorder=6, label='C1 break level')
    ax.hlines(c2_extreme, x0, x3, color=PURPLE, linestyle='--', linewidth=1.2, zorder=6, label='C2 expected extreme')

    for label, candle, color in [('1', c1, GRAY), ('2', c2, YELLOW), ('3', c3, BLUE if setup['hit'] else RED)]:
        ax.scatter(
            [mdates.date2num(pd.Timestamp(candle['date']))],
            [float(candle['high'])],
            s=120, marker='o', color=color, edgecolor='black', zorder=9,
        )
        ax.text(
            mdates.date2num(pd.Timestamp(candle['date'])), float(candle['high']),
            label, color='black', ha='center', va='center',
            fontsize=8, fontweight='bold', zorder=10,
        )

    dates = pd.to_datetime(bars['date'])
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=20), dates.iloc[-1] + pd.Timedelta(days=20))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    direction = str(setup['direction'])
    result = 'hit' if bool(setup['hit']) else 'miss'
    ax.set_title(
        f'{market.upper()} monthly candle theory #{int(setup["setup_id"])} · {direction} · C3 {result} · '
        f'{setup["c1_month"]}, {setup["c2_month"]}, {setup["c3_month"]}',
        color='white', fontsize=10, fontweight='bold', loc='left',
    )
    legend = ax.legend(loc='upper left', fontsize=8, framealpha=0.18)
    for text in legend.get_texts():
        text.set_color('white')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return str(out_path)


def timeline_chart(monthly: pd.DataFrame, setups: pd.DataFrame, out_path: Path, market: str) -> str:
    fig = plt.figure(figsize=(22, 9), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, monthly, width_scale=0.55)

    setup_by_c3 = {row['c3_month']: row for _, row in setups.iterrows()}
    for _, candle in monthly.iterrows():
        row = setup_by_c3.get(candle['month'])
        if row is None:
            continue
        x = mdates.date2num(pd.Timestamp(candle['date']))
        color = BLUE if bool(row['hit']) else RED
        marker = '^' if row['direction'] == 'bullish' else 'v'
        ax.axvspan(x - 14, x + 14, color=color, alpha=0.12, zorder=1)
        y = float(candle['high']) if row['direction'] == 'bullish' else float(candle['low'])
        ax.scatter([x], [y], marker=marker, s=80, color=color, edgecolor='black', linewidth=0.7, zorder=9)

    dates = pd.to_datetime(monthly['date'])
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=30), dates.iloc[-1] + pd.Timedelta(days=30))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.set_title(
        f'{market.upper()} monthly candle theory · all C3 occurrences highlighted',
        color='white', fontsize=11, fontweight='bold', loc='left',
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return str(out_path)


def draw_level(
    ax: plt.Axes, x0: float, x1: float, y: float,
    color: str, label: str, linestyle: str, alpha: float = 0.9,
    linewidth: float = 1.0,
) -> None:
    ax.hlines(y, x0, x1, color=color, linestyle=linestyle,
              linewidth=linewidth, alpha=alpha, zorder=5)
    ax.text(x1, y, f' {label}', color=color, fontsize=7,
            va='center', ha='left', alpha=alpha, zorder=8)


def daily_c3_chart(
    daily: pd.DataFrame,
    setup: pd.Series,
    out_path: Path,
    market: str,
    strat_2r: Optional[pd.Series] = None,
    strat_3r: Optional[pd.Series] = None,
) -> str:
    """Daily candles for C3 with C1/C2 OHLC levels and breakout-candle strat overlay."""
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    c3_period = pd.Period(str(setup['c3_month']), freq='M')
    bars = work[work['date'].dt.to_period('M').eq(c3_period)].copy().reset_index(drop=True)
    if bars.empty:
        return ''

    fig = plt.figure(figsize=(16, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, bars, width_scale=0.68)

    dates = pd.to_datetime(bars['date'])
    x0 = mdates.date2num(dates.iloc[0]) - 1.0
    x1 = mdates.date2num(dates.iloc[-1]) + 1.0

    # C1 / C2 OHLC reference levels
    for label, level in [
        ('C1 O', float(setup['c1_open'])), ('C1 H', float(setup['c1_high'])),
        ('C1 L', float(setup['c1_low'])),  ('C1 C', float(setup['c1_close'])),
    ]:
        draw_level(ax, x0, x1, level, GRAY, label, ':', alpha=0.55)
    for label, level in [
        ('C2 O', float(setup['c2_open'])), ('C2 H', float(setup['c2_high'])),
        ('C2 L', float(setup['c2_low'])),  ('C2 C', float(setup['c2_close'])),
    ]:
        color = YELLOW if label in ('C2 H', 'C2 L') else '#90CAF9'
        draw_level(ax, x0, x1, level, color, label, '--', alpha=0.70)

    expected = float(setup['c2_expected_extreme'])
    draw_level(ax, x0, x1, expected, PURPLE, 'C2 expected extreme', '-', alpha=0.98, linewidth=1.2)

    # Opening candle highlight (day 1 of C3)
    oc_x = mdates.date2num(dates.iloc[0])
    if len(dates) > 1:
        half_gap = (mdates.date2num(dates.iloc[1]) - oc_x) * 0.48
    else:
        half_gap = 0.48
    ax.axvspan(oc_x - half_gap, oc_x + half_gap, color=TEAL, alpha=0.10, zorder=0, label='opening candle')

    # Strategy overlay (shared SL, entry, TP2 and TP3)
    # We use strat_2r for entry/SL/TP2, strat_3r only for its TP level
    strat = strat_2r if strat_2r is not None else strat_3r
    if strat is not None and str(strat.get('outcome', 'no_breakout')) != 'no_breakout':
        entry_price = float(strat['entry'])
        sl_price = float(strat['sl'])
        oc_high = strat.get('oc_high')
        oc_low = strat.get('oc_low')

        if oc_high is not None and not pd.isna(oc_high):
            draw_level(ax, x0, x1, float(oc_high), TEAL, f'OC high {float(oc_high):.2f}', ':', alpha=0.80)
        if oc_low is not None and not pd.isna(oc_low):
            draw_level(ax, x0, x1, float(oc_low), TEAL, f'OC low {float(oc_low):.2f}', ':', alpha=0.80)

        draw_level(ax, x0, x1, entry_price, GREEN, f'entry {entry_price:.2f}', '--', alpha=0.95, linewidth=1.1)
        draw_level(ax, x0, x1, sl_price, RED, f'SL {sl_price:.2f}', '--', alpha=0.95, linewidth=1.1)

        if strat_2r is not None and str(strat_2r.get('outcome', 'no_breakout')) != 'no_breakout':
            tp2 = float(strat_2r['tp'])
            draw_level(ax, x0, x1, tp2, ORANGE, f'TP 2R {tp2:.2f}', '--', alpha=0.95, linewidth=1.1)
        if strat_3r is not None and str(strat_3r.get('outcome', 'no_breakout')) != 'no_breakout':
            tp3 = float(strat_3r['tp'])
            draw_level(ax, x0, x1, tp3, YELLOW, f'TP 3R {tp3:.2f}', '--', alpha=0.90, linewidth=1.1)

        # Breakout candle marker
        bk_date_str = strat.get('breakout_date')
        if bk_date_str and str(bk_date_str) != 'None':
            bk_d = pd.Timestamp(str(bk_date_str))
            bk_x = mdates.date2num(bk_d)
            ax.scatter([bk_x], [entry_price], marker='D', s=90, color=GREEN,
                       edgecolor='black', linewidth=0.8, zorder=12)
            ax.text(bk_x, entry_price, f'  breakout\n  {bk_d.date()}',
                    color=GREEN, fontsize=7, va='bottom', ha='left', zorder=13)

        # Outcome markers for both variants
        for sr, tp_label, tp_color in [
            (strat_2r, '2R', ORANGE),
            (strat_3r, '3R', YELLOW),
        ]:
            if sr is None or str(sr.get('outcome', 'no_breakout')) in ('no_breakout', 'open_eom'):
                continue
            out = str(sr['outcome'])
            od_str = sr.get('outcome_date')
            if not od_str or str(od_str) == 'None':
                continue
            od = pd.Timestamp(str(od_str))
            ox = mdates.date2num(od)
            out_price = float(sr['tp']) if out == 'tp' else float(sr['sl'])
            out_color = tp_color if out == 'tp' else RED
            ax.scatter([ox], [out_price],
                       marker='*' if out == 'tp' else 'X',
                       s=160, color=out_color, edgecolor='black', linewidth=0.7, zorder=13)
            ax.text(ox, out_price,
                    f'  {tp_label} {out.upper()} {od.date()}',
                    color=out_color, fontsize=7,
                    va='top' if out == 'sl' else 'bottom', ha='left', zorder=14)

    # First C3 target touch (monthly theory)
    direction = str(setup['direction'])
    hit_day = None
    if direction == 'bullish':
        hit_rows = bars[bars['high'].astype(float) > expected]
        marker_y, marker = expected, '^'
    else:
        hit_rows = bars[bars['low'].astype(float) < expected]
        marker_y, marker = expected, 'v'
    if not hit_rows.empty:
        hit_day = hit_rows.iloc[0]
        ax.scatter(
            [mdates.date2num(pd.Timestamp(hit_day['date']))], [marker_y],
            marker=marker, s=130, color=BLUE, edgecolor='black', linewidth=0.8, zorder=11,
        )

    ax.axhspan(float(setup['c3_low']), float(setup['c3_high']),
               color=BLUE if bool(setup['hit']) else RED, alpha=0.04, zorder=0)
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=1))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    result = 'hit' if bool(setup['hit']) else 'miss'
    close_text = 'closed beyond' if bool(setup['c3_closed_beyond_c2_extreme']) else 'wick/no close'

    strat_tag = ''
    if strat is not None:
        parts = []
        for sr, lbl in [(strat_2r, '2R'), (strat_3r, '3R')]:
            if sr is not None:
                out = str(sr.get('outcome', '?'))
                pr = float(sr.get('pnl_r', 0.0))
                parts.append(f'{lbl}:{out}({pr:+.0f}R)')
        if parts:
            strat_tag = ' | ' + '  '.join(parts)

    ax.set_title(
        f'{market.upper()} daily C3 #{int(setup["setup_id"])} · {direction} · {setup["c3_month"]} · '
        f'{result} · {close_text}{strat_tag}',
        color='white', fontsize=9, fontweight='bold', loc='left',
    )

    handles = [
        plt.Line2D([0], [0], color=GRAY, lw=1.0, linestyle=':', alpha=0.6, label='C1 OHLC'),
        plt.Line2D([0], [0], color=YELLOW, lw=1.0, linestyle='--', alpha=0.8, label='C2 H/L'),
        plt.Line2D([0], [0], color='#90CAF9', lw=1.0, linestyle='--', alpha=0.8, label='C2 O/C'),
        plt.Line2D([0], [0], color=PURPLE, lw=1.2, linestyle='-', alpha=0.98, label='C2 expected extreme'),
        mpatches.Patch(color=TEAL, alpha=0.20, label='opening candle'),
    ]
    if strat is not None and str(strat.get('outcome', 'no_breakout')) != 'no_breakout':
        handles += [
            plt.Line2D([0], [0], color=TEAL, lw=1.0, linestyle=':', alpha=0.8, label='OC H/L'),
            plt.Line2D([0], [0], color=GREEN, lw=1.1, linestyle='--', alpha=0.95, label='entry'),
            plt.Line2D([0], [0], color=RED, lw=1.1, linestyle='--', alpha=0.95, label='SL (2R)'),
            plt.Line2D([0], [0], color=ORANGE, lw=1.1, linestyle='--', alpha=0.95, label='TP 2R'),
            plt.Line2D([0], [0], color=YELLOW, lw=1.1, linestyle='--', alpha=0.90, label='TP 3R'),
        ]
    if hit_day is not None:
        handles.append(
            plt.Line2D([0], [0], marker=marker, color='none', markerfacecolor=BLUE,
                       markeredgecolor='black', markersize=8, label='C3 theory target touch')
        )
    legend = ax.legend(handles=handles, loc='upper left', fontsize=7, framealpha=0.18)
    for text in legend.get_texts():
        text.set_color('white')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return str(out_path)


def write_outputs(
    out_dir: Path,
    market: str,
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    setups: pd.DataFrame,
    summary: pd.DataFrame,
    skipped: dict,
    make_charts: bool,
    strat_2r: pd.DataFrame,
    strat_3r: pd.DataFrame,
    strat_sum_2r: pd.DataFrame,
    strat_sum_3r: pd.DataFrame,
    strat_cb_2r: pd.DataFrame,
    strat_cb_3r: pd.DataFrame,
    strat_sum_cb_2r: pd.DataFrame,
    strat_sum_cb_3r: pd.DataFrame,
    strat_so_2r: pd.DataFrame,
    strat_so_3r: pd.DataFrame,
    strat_sum_so_2r: pd.DataFrame,
    strat_sum_so_3r: pd.DataFrame,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_dir / 'monthly_candles.csv', index=False)
    setups.to_csv(out_dir / 'setups.csv', index=False)
    summary.to_csv(out_dir / 'summary.csv', index=False)
    strat_2r.to_csv(out_dir / 'strat_2r_trades.csv', index=False)
    strat_3r.to_csv(out_dir / 'strat_3r_trades.csv', index=False)
    strat_sum_2r.to_csv(out_dir / 'strat_2r_summary.csv', index=False)
    strat_sum_3r.to_csv(out_dir / 'strat_3r_summary.csv', index=False)
    strat_cb_2r.to_csv(out_dir / 'strat_clean_body_2r_trades.csv', index=False)
    strat_cb_3r.to_csv(out_dir / 'strat_clean_body_3r_trades.csv', index=False)
    strat_sum_cb_2r.to_csv(out_dir / 'strat_clean_body_2r_summary.csv', index=False)
    strat_sum_cb_3r.to_csv(out_dir / 'strat_clean_body_3r_summary.csv', index=False)
    strat_so_2r.to_csv(out_dir / 'strat_swept_opposing_2r_trades.csv', index=False)
    strat_so_3r.to_csv(out_dir / 'strat_swept_opposing_3r_trades.csv', index=False)
    strat_sum_so_2r.to_csv(out_dir / 'strat_swept_opposing_2r_summary.csv', index=False)
    strat_sum_so_3r.to_csv(out_dir / 'strat_swept_opposing_3r_summary.csv', index=False)

    s2_by_id: dict[int, pd.Series] = {}
    s3_by_id: dict[int, pd.Series] = {}
    for _, sr in strat_2r.iterrows():
        s2_by_id[int(sr['setup_id'])] = sr
    for _, sr in strat_3r.iterrows():
        s3_by_id[int(sr['setup_id'])] = sr

    chart_rows: list[dict] = []
    daily_chart_rows: list[dict] = []
    timeline = ''

    if make_charts and not setups.empty:
        timeline = timeline_chart(monthly, setups, out_dir / 'charts' / 'timeline_all_c3.png', market)
        for _, setup in setups.iterrows():
            folder = 'hits' if bool(setup['hit']) else 'misses'
            file_name = (
                f'{int(setup["setup_id"]):03d}_{setup["direction"]}_{setup["c3_month"]}'
                f'_c3_{"hit" if setup["hit"] else "miss"}.png'
            )
            chart_path = out_dir / 'charts' / folder / file_name
            setup_chart(monthly, setup, chart_path, market)
            chart_rows.append({
                'setup_id': int(setup['setup_id']),
                'direction': setup['direction'],
                'c1': setup['c1_month'], 'c2': setup['c2_month'], 'c3': setup['c3_month'],
                'hit': bool(setup['hit']),
                'closed': bool(setup['c3_closed_beyond_c2_extreme']),
                'extension': float(setup['extension_pts']),
                'chart': f'charts/{folder}/{file_name}',
            })

            daily_folder = 'hits' if bool(setup['hit']) else 'misses'
            daily_name = (
                f'{int(setup["setup_id"]):03d}_{setup["direction"]}_{setup["c3_month"]}'
                f'_daily_c3_{"hit" if setup["hit"] else "miss"}.png'
            )
            daily_path = out_dir / 'charts' / 'daily' / daily_folder / daily_name
            sid = int(setup['setup_id'])
            daily_chart = daily_c3_chart(
                daily, setup, daily_path, market,
                strat_2r=s2_by_id.get(sid),
                strat_3r=s3_by_id.get(sid),
            )
            if daily_chart:
                daily_chart_rows.append({
                    'setup_id': sid,
                    'direction': setup['direction'],
                    'c1': setup['c1_month'], 'c2': setup['c2_month'], 'c3': setup['c3_month'],
                    'hit': bool(setup['hit']),
                    'closed': bool(setup['c3_closed_beyond_c2_extreme']),
                    'extension': float(setup['extension_pts']),
                    'chart': str(Path(daily_chart).relative_to(out_dir)),
                })

        daily_index_lines = [
            '# Daily C3 Charts',
            '',
            'Daily candles for C3 with C1/C2 reference levels and breakout-candle strategy overlay.',
            'Opening candle (day 1 of C3) highlighted in teal. Breakout candle marked with diamond.',
            '',
            '| Setup | Direction | C1 | C2 | C3 | Hit | Extension | Daily Chart |',
            '|---:|---|---|---|---|---|---:|---|',
        ]
        for row in daily_chart_rows:
            daily_link = Path(row['chart']).relative_to(Path('charts') / 'daily')
            daily_index_lines.append(
                f'| {row["setup_id"]} | {row["direction"]} | {row["c1"]} | {row["c2"]} | {row["c3"]} | '
                f'{row["hit"]} | {row["extension"]:+.2f} | [{Path(row["chart"]).name}]({daily_link}) |'
            )
        daily_index = out_dir / 'charts' / 'daily' / 'INDEX.md'
        daily_index.parent.mkdir(parents=True, exist_ok=True)
        daily_index.write_text('\n'.join(daily_index_lines) + '\n', encoding='utf-8')

        # Category charts: clean body runs and swept opposing
        clean_ids = set(strat_2r[strat_2r['clean_body_run_to_tp'].eq(True)]['setup_id'].tolist())
        swept_ids = set(strat_2r[strat_2r['swept_opposing_before_breakout'].eq(True)]['setup_id'].tolist())

        for cat_ids, cat_folder, cat_label in [
            (clean_ids, 'clean_body_runs', 'clean body run'),
            (swept_ids, 'swept_opposing', 'swept opposing'),
        ]:
            for _, setup in setups[setups['setup_id'].isin(cat_ids)].iterrows():
                sid = int(setup['setup_id'])
                cat_name = (
                    f'{sid:03d}_{setup["direction"]}_{setup["c3_month"]}'
                    f'_{"hit" if setup["hit"] else "miss"}.png'
                )
                cat_path = out_dir / 'charts' / 'daily' / cat_folder / cat_name
                daily_c3_chart(daily, setup, cat_path, market, strat_2r=s2_by_id.get(sid), strat_3r=s3_by_id.get(sid))

    # ── README ──────────────────────────────────────────────────────────────
    def _strat_table_rows(df: pd.DataFrame) -> list[str]:
        out = []
        for _, row in df.iterrows():
            avg_tp = f'{row["avg_days_tp"]:.1f}' if row['avg_days_tp'] is not None else '—'
            avg_sl = f'{row["avg_days_sl"]:.1f}' if row['avg_days_sl'] is not None else '—'
            swept = f'{int(row["n_swept_opposing"])} / {row["pct_swept_opposing"]:.1f}%'
            clean = f'{int(row["n_clean_body_tp"])} / {row["pct_clean_body_tp"]:.1f}%'
            out.append(
                f'| {row["direction"]} | {int(row["setups"])} | {int(row["no_breakout"])} | '
                f'{int(row["resolved"])} | {int(row["open_eom"])} | '
                f'{int(row["tp"])} | {int(row["sl"])} | {row["hit_rate_pct"]:.2f}% | '
                f'{row["avg_mae_r"]:.3f} | {row["avg_mae_pts"]:.2f} | '
                f'{row["avg_breakout_day"]:.1f} | {avg_tp} | {avg_sl} | '
                f'{row["total_pnl_r"]:+.2f} | {row["total_pnl_pts"]:+.2f} | {swept} | {clean} |'
            )
        return out

    strat_header = (
        '| Direction | Setups | No Breakout | Resolved | open_eom | TP | SL | Hit Rate | '
        'Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | '
        'Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |'
    )
    strat_sep = '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'

    lines = [
        f'# {market.upper()} Monthly Candlestick Theory Study',
        '',
        '## Theory Summary',
        '',
        '| Direction | Setups | Hits | Hit Rate | C3 Close Beyond | Close Rate | Avg Extension | Median Extension | Avg Adverse | Worst Adverse |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for _, row in summary.iterrows():
        lines.append(
            f'| {row["direction"]} | {int(row["setups"])} | {int(row["hits"])} | {row["hit_rate"]:.2f}% | '
            f'{int(row["closed_beyond_count"])} | {row["closed_beyond_rate"]:.2f}% | '
            f'{row["avg_extension_pts"]:.2f} | {row["median_extension_pts"]:.2f} | '
            f'{row["avg_adverse_pts"]:.2f} | {row["worst_adverse_pts"]:.2f} |'
        )

    lines += [
        '',
        '## Strategy: Breakout-Candle Entry · TP = 2R',
        '',
        'Opening candle = first daily bar of C3.  R = its H−L.',
        'Breakout candle: first bar that closes beyond opening candle H (bull) or L (bear).',
        'Entry at breakout close.  SL = entry ± 2R.  TP = entry ± 2R.',
        'open_eom = filled but C3 ended before TP/SL (excluded from PnL).',
        '',
        strat_header, strat_sep,
    ] + _strat_table_rows(strat_sum_2r)

    lines += [
        '',
        '## Strategy: Breakout-Candle Entry · TP = 3R',
        '',
        'Same entry/SL rules.  TP = entry ± 3R.',
        '',
        strat_header, strat_sep,
    ] + _strat_table_rows(strat_sum_3r)

    def _variant_table_rows(df: pd.DataFrame) -> list[str]:
        out = []
        for _, row in df.iterrows():
            avg_tp = f'{row["avg_days_tp"]:.1f}' if row['avg_days_tp'] is not None else '—'
            avg_loss = f'{row["avg_days_loss"]:.1f}' if row['avg_days_loss'] is not None else '—'
            out.append(
                f'| {row["direction"]} | {int(row["active_setups"])} | {int(row["no_breakout"])} | '
                f'{int(row["skipped"])} | {int(row["resolved"])} | {int(row["open_eom"])} | '
                f'{int(row["tp"])} | {int(row["loss"])} | {row["hit_rate_pct"]:.2f}% | '
                f'{row["avg_mae_r"]:.3f} | {row["avg_mae_pts"]:.2f} | '
                f'{avg_tp} | {avg_loss} | '
                f'{row["total_pnl_r"]:+.3f} | {row["total_pnl_pts"]:+.2f} |'
            )
        return out

    variant_header = (
        '| Direction | Active | No Breakout | Skipped | Resolved | open_eom | TP | Loss | '
        'Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg days→TP | Avg days→Loss | '
        'Total PnL (R) | Total PnL (pts) |'
    )
    variant_sep = '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'

    lines += [
        '',
        '## Variant: Clean-Body-Exit · TP = 2R',
        '',
        'Entry at breakout close.  Exit when any bar CLOSES back through OC boundary',
        '(close < OC_high for bull, close > OC_low for bear).  TP = entry ± 2R.',
        'TP takes priority over close-exit on the same bar.',
        '',
        variant_header, variant_sep,
    ] + _variant_table_rows(strat_sum_cb_2r)

    lines += [
        '',
        '## Variant: Clean-Body-Exit · TP = 3R',
        '',
        'Same close-based exit.  TP = entry ± 3R.',
        '',
        variant_header, variant_sep,
    ] + _variant_table_rows(strat_sum_cb_3r)

    lines += [
        '',
        '## Variant: Swept-Opposing-Only · TP = 2R',
        '',
        "Only trades setups where a bar before the breakout swept OC's opposing extreme.",
        'SL = OC_low (bull) / OC_high (bear).  TP = entry ± 2R (R = OC range).  Skipped = no sweep.',
        '',
        variant_header, variant_sep,
    ] + _variant_table_rows(strat_sum_so_2r)

    lines += [
        '',
        '## Variant: Swept-Opposing-Only · TP = 3R',
        '',
        'Same SL rules.  TP = entry ± 3R.',
        '',
        variant_header, variant_sep,
    ] + _variant_table_rows(strat_sum_so_3r)

    lines += [
        '',
        '## Skipped / Failure Sweep Context',
        '',
        f'- High failure sweeps: {skipped["high_failure_sweeps"]}',
        f'- Low failure sweeps: {skipped["low_failure_sweeps"]}',
        f'- Unique non-signal failure-sweep months: {skipped["unique_failure_sweep_months"]}',
        f'- Non-signal rolling windows: {skipped["non_signal_months"]}',
        '',
        '## Charts',
        '',
    ]
    if timeline:
        lines.append(f'- [All C3 occurrences timeline]({Path(timeline).relative_to(out_dir)})')
        lines.append('- [Daily C3 chart index](charts/daily/INDEX.md)')
        lines.append('')
    lines += [
        '| Setup | Direction | C1 | C2 | C3 | Hit | Extension | Chart |',
        '|---:|---|---|---|---|---|---:|---|',
    ]
    for row in chart_rows:
        lines.append(
            f'| {row["setup_id"]} | {row["direction"]} | {row["c1"]} | {row["c2"]} | {row["c3"]} | '
            f'{row["hit"]} | {row["extension"]:+.2f} | [{Path(row["chart"]).name}]({row["chart"]}) |'
        )
    lines += [
        '',
        'CSV outputs: `monthly_candles.csv` · `setups.csv` · `summary.csv` · '
        '`strat_2r_trades.csv` · `strat_3r_trades.csv` · '
        '`strat_clean_body_2r_trades.csv` · `strat_clean_body_3r_trades.csv` · '
        '`strat_swept_opposing_2r_trades.csv` · `strat_swept_opposing_3r_trades.csv`',
        '',
    ]
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--market', default='NQ')
    ap.add_argument('--no-charts', action='store_true')
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    monthly = aggregate_monthly(daily)
    setups, skipped = classify_setups(monthly)
    summary = summarize(setups)

    strat_2r = simulate_strat(daily, setups, tp_mult=2.0)
    strat_3r = simulate_strat(daily, setups, tp_mult=3.0)
    strat_sum_2r = strat_summary(strat_2r, tp_mult=2.0)
    strat_sum_3r = strat_summary(strat_3r, tp_mult=3.0)

    strat_cb_2r = simulate_strat_clean_body(daily, setups, tp_mult=2.0)
    strat_cb_3r = simulate_strat_clean_body(daily, setups, tp_mult=3.0)
    strat_sum_cb_2r = strat_variant_summary(strat_cb_2r, tp_mult=2.0, variant='clean_body')
    strat_sum_cb_3r = strat_variant_summary(strat_cb_3r, tp_mult=3.0, variant='clean_body')

    strat_so_2r = simulate_strat_swept_opposing(daily, setups, tp_mult=2.0)
    strat_so_3r = simulate_strat_swept_opposing(daily, setups, tp_mult=3.0)
    strat_sum_so_2r = strat_variant_summary(strat_so_2r, tp_mult=2.0, variant='swept_opposing')
    strat_sum_so_3r = strat_variant_summary(strat_so_3r, tp_mult=3.0, variant='swept_opposing')

    write_outputs(
        args.out, args.market, daily, monthly, setups, summary, skipped,
        not args.no_charts,
        strat_2r, strat_3r, strat_sum_2r, strat_sum_3r,
        strat_cb_2r, strat_cb_3r, strat_sum_cb_2r, strat_sum_cb_3r,
        strat_so_2r, strat_so_3r, strat_sum_so_2r, strat_sum_so_3r,
    )

    print('=== Monthly Theory Summary ===')
    print(summary.to_string(index=False))
    print()
    print('=== Base Strat · TP = 2R ===')
    print(strat_sum_2r.to_string(index=False))
    print()
    print('=== Variant: Clean Body · TP = 2R ===')
    print(strat_sum_cb_2r.to_string(index=False))
    print()
    print('=== Variant: Swept Opposing · TP = 2R ===')
    print(strat_sum_so_2r.to_string(index=False))
    print(f'\nwrote {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
