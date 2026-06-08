#!/usr/bin/env python3
"""Daily candlestick theory continuation study + breakout-candle strategy backtest.

Same three-candle pattern as the monthly study, applied directly to daily bars:
  C1 = any daily bar.
  C2 = immediately following bar that takes AND closes beyond C1's high (bull) or low (bear).
  C3 = the bar immediately after C2; expected to take C2's continuation extreme.
  Hit = C3.high > C2.high (bull) or C3.low < C2.low (bear).

Strategy (breakout-candle entry, same mechanics as monthly study):
  Opening candle (OC) = C3 itself.
  R = OC.high − OC.low.
  Breakout candle (bull): first bar in the next --lookahead bars whose close > OC.high.
  Breakout candle (bear): first bar whose close < OC.low.
  Entry at breakout close.  SL = entry ± 2R.  TP = entry ± tp_mult*R.
  Tracking starts on the bar AFTER the breakout candle.
  Same-bar TP+SL conflict → SL (conservative).

Additional quality metrics (same as monthly study):
  swept_opposing_before_breakout: any bar between OC and the breakout traded through OC's
    opposing extreme (e.g., low < OC.low before a bullish breakout).
  clean_body_run_to_tp: for TP trades, all closes from breakout bar to TP bar stayed on
    the correct side of OC.high/low (wicks may cross, but no close-back).
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


# ── Theory ──────────────────────────────────────────────────────────────────

def classify_setups(daily: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Roll through daily bars as C1/C2/C3 triplets and classify setups."""
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work = work.sort_values('date').reset_index(drop=True)

    rows: list[dict] = []
    skipped = {
        'high_failure_sweeps': 0,
        'low_failure_sweeps': 0,
        'unique_failure_sweep_bars': 0,
        'non_signal_bars': 0,
    }

    for i in range(len(work) - 2):
        c1 = work.iloc[i]
        c2 = work.iloc[i + 1]
        c3 = work.iloc[i + 2]

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
            skipped['unique_failure_sweep_bars'] += 1

        if is_bull:
            target = float(c2['high'])
            took_c2_extreme = float(c3['high']) > target
            closed_beyond_c2 = float(c3['close']) > target
            extension = float(c3['high']) - target if took_c2_extreme else 0.0
            adverse = max(0.0, float(c2['low']) - float(c3['low']))
            direction = 'bullish'
            c1_level = float(c1['high'])
            c2_extreme = float(c2['high'])
        elif is_bear:
            target = float(c2['low'])
            took_c2_extreme = float(c3['low']) < target
            closed_beyond_c2 = float(c3['close']) < target
            extension = target - float(c3['low']) if took_c2_extreme else 0.0
            adverse = max(0.0, float(c3['high']) - float(c2['high']))
            direction = 'bearish'
            c1_level = float(c1['low'])
            c2_extreme = float(c2['low'])
        else:
            skipped['non_signal_bars'] += 1
            continue

        rows.append({
            'setup_id': len(rows) + 1,
            'direction': direction,
            'c1_date': str(pd.Timestamp(c1['date']).date()),
            'c2_date': str(pd.Timestamp(c2['date']).date()),
            'c3_date': str(pd.Timestamp(c3['date']).date()),
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
        })

    return pd.DataFrame(rows), skipped


def summarize(setups: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for direction, group in setups.groupby('direction', sort=True):
        hits = group[group['hit']].copy()
        rows.append({
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
        })
    if not setups.empty:
        hits = setups[setups['hit']].copy()
        rows.append({
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
        })
    return pd.DataFrame(rows)


# ── Strategy ────────────────────────────────────────────────────────────────

def simulate_strat(
    daily: pd.DataFrame,
    setups: pd.DataFrame,
    tp_mult: float = 2.0,
    lookahead: int = 20,
) -> pd.DataFrame:
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work = work.sort_values('date').reset_index(drop=True)
    date_to_idx: dict[str, int] = {str(d.date()): i for i, d in enumerate(work['date'])}

    results: list[dict] = []

    for _, setup in setups.iterrows():
        direction = str(setup['direction'])
        c3_date_str = str(setup['c3_date'])

        def _nofill(reason: str) -> dict:
            return {
                'setup_id': int(setup['setup_id']), 'direction': direction,
                'c3_date': c3_date_str, 'oc_high': None, 'oc_low': None, 'base_r': None,
                'breakout_day': None, 'breakout_date': None, 'entry': None,
                'sl': None, 'tp': None, 'outcome': reason, 'pnl_r': 0.0,
                'pnl_pts': 0.0, 'mae_pts': 0.0, 'mae_r': 0.0,
                'days_to_outcome': None, 'outcome_date': None,
                'swept_opposing_before_breakout': False, 'clean_body_run_to_tp': False,
            }

        c3_idx = date_to_idx.get(c3_date_str)
        if c3_idx is None:
            results.append(_nofill('no_breakout'))
            continue

        oc = work.iloc[c3_idx]
        oc_high = float(oc['high'])
        oc_low = float(oc['low'])
        base_r = oc_high - oc_low

        if base_r <= 0:
            results.append(_nofill('no_breakout'))
            continue

        # Lookahead window = bars after C3
        window = work.iloc[c3_idx + 1: c3_idx + 1 + lookahead].reset_index(drop=True)
        if window.empty:
            results.append(_nofill('no_breakout'))
            continue

        # Find breakout candle within window
        breakout_idx: Optional[int] = None
        for wi in range(len(window)):
            bar = window.iloc[wi]
            if direction == 'bullish' and float(bar['close']) > oc_high:
                breakout_idx = wi
                break
            elif direction == 'bearish' and float(bar['close']) < oc_low:
                breakout_idx = wi
                break

        if breakout_idx is None:
            results.append(_nofill('no_breakout'))
            continue

        bk = window.iloc[breakout_idx]
        entry = float(bk['close'])

        if direction == 'bullish':
            sl = entry - 2.0 * base_r
            tp = entry + tp_mult * base_r
        else:
            sl = entry + 2.0 * base_r
            tp = entry - tp_mult * base_r

        # Swept opposing: any bar between OC and breakout traded through OC's opposing extreme
        pre_bk = window.iloc[:breakout_idx]
        if direction == 'bullish':
            swept_opposing = bool(not pre_bk.empty and (pre_bk['low'].astype(float) < oc_low).any())
        else:
            swept_opposing = bool(not pre_bk.empty and (pre_bk['high'].astype(float) > oc_high).any())

        # Track from bar after breakout, within window
        post_entry = window.iloc[breakout_idx + 1:].reset_index(drop=True)

        outcome = 'open_window'
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

        mae_r = round(mae_pts / (2.0 * base_r), 3) if base_r > 0 else 0.0

        # Clean body run: from breakout bar through TP bar, all closes on correct side
        clean_body = False
        if outcome == 'tp' and days_to_outcome is not None:
            bk_to_tp = window.iloc[breakout_idx: breakout_idx + 1 + days_to_outcome]
            if direction == 'bullish':
                clean_body = bool((bk_to_tp['close'].astype(float) >= oc_high).all())
            else:
                clean_body = bool((bk_to_tp['close'].astype(float) <= oc_low).all())

        results.append({
            'setup_id': int(setup['setup_id']),
            'direction': direction,
            'c3_date': c3_date_str,
            'oc_high': round(oc_high, 2),
            'oc_low': round(oc_low, 2),
            'base_r': round(base_r, 2),
            'breakout_day': breakout_idx + 1,
            'breakout_date': str(pd.Timestamp(bk['date']).date()),
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

        rows.append({
            'direction': direction,
            'tp_mult': tp_mult,
            'setups': len(total),
            'no_breakout': int((total['outcome'] == 'no_breakout').sum()),
            'resolved': n,
            'open_window': int((total['outcome'] == 'open_window').sum()),
            'tp': len(tp_t),
            'sl': len(sl_t),
            'hit_rate_pct': round(len(tp_t) / n * 100, 2) if n > 0 else 0.0,
            'avg_mae_r': round(float(resolved['mae_r'].mean()), 3) if n > 0 else 0.0,
            'avg_mae_pts': round(float(resolved['mae_pts'].mean()), 2) if n > 0 else 0.0,
            'avg_breakout_day': round(float(with_bk[with_bk['breakout_day'].notna()]['breakout_day'].mean()), 1) if n_bk > 0 else 0.0,
            'avg_days_tp': (round(float(tp_t['days_to_outcome'].mean()), 1) if not tp_t.empty else None),
            'avg_days_sl': (round(float(sl_t['days_to_outcome'].mean()), 1) if not sl_t.empty else None),
            'total_pnl_r': round(float(resolved['pnl_r'].sum()), 2),
            'total_pnl_pts': round(float(resolved['pnl_pts'].sum()), 2),
            'n_swept_opposing': n_swept,
            'pct_swept_opposing': pct_swept,
            'n_clean_body_tp': n_clean,
            'pct_clean_body_tp': pct_clean,
        })
    return pd.DataFrame(rows)


# ── Charts (optional) ───────────────────────────────────────────────────────

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
        width = 1.0
    for xval, (_, row) in zip(x, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(xval, l, h, color=color, linewidth=0.9, zorder=3)
        ax.add_patch(mpatches.Rectangle(
            (xval - width / 2, min(o, c)), width, max(abs(c - o), 0.05),
            facecolor=color, edgecolor=color, alpha=0.92, zorder=3,
        ))


def draw_level(
    ax: plt.Axes, x0: float, x1: float, y: float,
    color: str, label: str, linestyle: str,
    alpha: float = 0.9, linewidth: float = 1.0,
) -> None:
    ax.hlines(y, x0, x1, color=color, linestyle=linestyle,
              linewidth=linewidth, alpha=alpha, zorder=5)
    ax.text(x1, y, f' {label}', color=color, fontsize=7,
            va='center', ha='left', alpha=alpha, zorder=8)


def strat_trade_chart(
    daily: pd.DataFrame,
    setup: pd.Series,
    strat_2r: Optional[pd.Series],
    strat_3r: Optional[pd.Series],
    out_path: Path,
    market: str,
    lookahead: int,
) -> str:
    """Show C3 (OC) bar plus the lookahead window, with C1/C2 reference levels and strategy overlay."""
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work = work.sort_values('date').reset_index(drop=True)

    c3_date = pd.Timestamp(str(setup['c3_date']))
    c3_mask = work['date'].dt.date == c3_date.date()
    if not c3_mask.any():
        return ''
    c3_idx = int(work[c3_mask].index[0])

    # Show from C1 through end of lookahead window for context
    c1_date = pd.Timestamp(str(setup['c1_date']))
    c1_mask = work['date'].dt.date == c1_date.date()
    c1_idx = int(work[c1_mask].index[0]) if c1_mask.any() else max(0, c3_idx - 4)

    end_idx = min(len(work), c3_idx + lookahead + 3)
    bars = work.iloc[c1_idx:end_idx].reset_index(drop=True)
    if bars.empty:
        return ''

    fig = plt.figure(figsize=(16, 8), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, bars, width_scale=0.68)

    dates = pd.to_datetime(bars['date'])
    x0 = mdates.date2num(dates.iloc[0]) - 0.5
    x1 = mdates.date2num(dates.iloc[-1]) + 0.5

    # C1 / C2 reference levels
    for label, level in [
        ('C1 H', float(setup['c1_high'])), ('C1 L', float(setup['c1_low'])),
        ('C2 H', float(setup['c2_high'])), ('C2 L', float(setup['c2_low'])),
        ('C2 C', float(setup['c2_close'])),
    ]:
        color = YELLOW if label.startswith('C2 H') or label.startswith('C2 L') else (GRAY if label.startswith('C1') else '#90CAF9')
        draw_level(ax, x0, x1, level, color, label, '--', alpha=0.65)

    expected = float(setup['c2_expected_extreme'])
    draw_level(ax, x0, x1, expected, PURPLE, 'C2 expected extreme', '-', alpha=0.98, linewidth=1.2)

    # Highlight C3 (OC) bar
    oc_x = mdates.date2num(c3_date)
    oc_bars = bars[pd.to_datetime(bars['date']).dt.date == c3_date.date()]
    if not oc_bars.empty and len(dates) > 1:
        half_gap = (mdates.date2num(dates.iloc[1]) - mdates.date2num(dates.iloc[0])) * 0.48
        ax.axvspan(oc_x - half_gap, oc_x + half_gap, color=TEAL, alpha=0.12, zorder=0)

    # Strategy overlay
    strat = strat_2r if strat_2r is not None else strat_3r
    if strat is not None and str(strat.get('outcome', 'no_breakout')) != 'no_breakout':
        oc_h = strat.get('oc_high')
        oc_l = strat.get('oc_low')
        entry_price = float(strat['entry'])
        sl_price = float(strat['sl'])

        if oc_h is not None and not pd.isna(oc_h):
            draw_level(ax, x0, x1, float(oc_h), TEAL, f'OC H {float(oc_h):.2f}', ':', alpha=0.80)
        if oc_l is not None and not pd.isna(oc_l):
            draw_level(ax, x0, x1, float(oc_l), TEAL, f'OC L {float(oc_l):.2f}', ':', alpha=0.80)

        draw_level(ax, x0, x1, entry_price, GREEN, f'entry {entry_price:.2f}', '--', alpha=0.95, linewidth=1.1)
        draw_level(ax, x0, x1, sl_price, RED, f'SL {sl_price:.2f}', '--', alpha=0.95, linewidth=1.1)

        if strat_2r is not None and str(strat_2r.get('outcome', 'no_breakout')) != 'no_breakout':
            tp2 = float(strat_2r['tp'])
            draw_level(ax, x0, x1, tp2, ORANGE, f'TP 2R {tp2:.2f}', '--', alpha=0.95, linewidth=1.1)
        if strat_3r is not None and str(strat_3r.get('outcome', 'no_breakout')) != 'no_breakout':
            tp3 = float(strat_3r['tp'])
            draw_level(ax, x0, x1, tp3, YELLOW, f'TP 3R {tp3:.2f}', '--', alpha=0.90, linewidth=1.1)

        # Breakout candle marker
        bk_ds = strat.get('breakout_date')
        if bk_ds and str(bk_ds) != 'None':
            bk_d = pd.Timestamp(str(bk_ds))
            bk_x = mdates.date2num(bk_d)
            ax.scatter([bk_x], [entry_price], marker='D', s=80, color=GREEN,
                       edgecolor='black', linewidth=0.8, zorder=12)
            ax.text(bk_x, entry_price, f'  bk {bk_d.date()}', color=GREEN,
                    fontsize=7, va='bottom', ha='left', zorder=13)

        # Outcome markers
        for sr, lbl, tp_color in [(strat_2r, '2R', ORANGE), (strat_3r, '3R', YELLOW)]:
            if sr is None or str(sr.get('outcome', 'no_breakout')) in ('no_breakout', 'open_window'):
                continue
            out = str(sr['outcome'])
            od_s = sr.get('outcome_date')
            if not od_s or str(od_s) == 'None':
                continue
            od = pd.Timestamp(str(od_s))
            ox = mdates.date2num(od)
            out_price = float(sr['tp']) if out == 'tp' else float(sr['sl'])
            out_color = tp_color if out == 'tp' else RED
            ax.scatter([ox], [out_price], marker='*' if out == 'tp' else 'X',
                       s=160, color=out_color, edgecolor='black', linewidth=0.7, zorder=13)
            ax.text(ox, out_price, f'  {lbl} {out.upper()} {od.date()}',
                    color=out_color, fontsize=7,
                    va='top' if out == 'sl' else 'bottom', ha='left', zorder=14)

        strat_tag = ''
        parts = []
        for sr, lbl in [(strat_2r, '2R'), (strat_3r, '3R')]:
            if sr is not None:
                parts.append(f'{lbl}:{sr.get("outcome","?")}({float(sr.get("pnl_r", 0)):+.0f}R)')
        if parts:
            strat_tag = ' | ' + '  '.join(parts)
    else:
        strat_tag = ' | no breakout'

    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=0.5), dates.iloc[-1] + pd.Timedelta(days=0.5))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    direction = str(setup['direction'])
    result = 'hit' if bool(setup['hit']) else 'miss'
    ax.set_title(
        f'{market.upper()} daily C3 #{int(setup["setup_id"])} · {direction} · {setup["c3_date"]} · '
        f'{result}{strat_tag}',
        color='white', fontsize=9, fontweight='bold', loc='left',
    )

    handles = [
        plt.Line2D([0], [0], color=GRAY, lw=1.0, linestyle='--', alpha=0.65, label='C1 H/L'),
        plt.Line2D([0], [0], color=YELLOW, lw=1.0, linestyle='--', alpha=0.75, label='C2 H/L'),
        plt.Line2D([0], [0], color=PURPLE, lw=1.2, linestyle='-', alpha=0.98, label='C2 expected extreme'),
        mpatches.Patch(color=TEAL, alpha=0.20, label='OC (C3 bar)'),
    ]
    if strat is not None and str(strat.get('outcome', 'no_breakout')) != 'no_breakout':
        handles += [
            plt.Line2D([0], [0], color=TEAL, lw=1.0, linestyle=':', alpha=0.8, label='OC H/L'),
            plt.Line2D([0], [0], color=GREEN, lw=1.1, linestyle='--', alpha=0.95, label='entry'),
            plt.Line2D([0], [0], color=RED, lw=1.1, linestyle='--', alpha=0.95, label='SL (2R)'),
            plt.Line2D([0], [0], color=ORANGE, lw=1.1, linestyle='--', alpha=0.95, label='TP 2R'),
            plt.Line2D([0], [0], color=YELLOW, lw=1.1, linestyle='--', alpha=0.90, label='TP 3R'),
        ]
    legend = ax.legend(handles=handles, loc='upper left', fontsize=7, framealpha=0.18)
    for text in legend.get_texts():
        text.set_color('white')
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)
    return str(out_path)


# ── Output ───────────────────────────────────────────────────────────────────

def write_outputs(
    out_dir: Path,
    market: str,
    daily: pd.DataFrame,
    setups: pd.DataFrame,
    summary: pd.DataFrame,
    skipped: dict,
    make_charts: bool,
    strat_2r: pd.DataFrame,
    strat_3r: pd.DataFrame,
    strat_sum_2r: pd.DataFrame,
    strat_sum_3r: pd.DataFrame,
    lookahead: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    setups.to_csv(out_dir / 'setups.csv', index=False)
    summary.to_csv(out_dir / 'summary.csv', index=False)
    strat_2r.to_csv(out_dir / 'strat_2r_trades.csv', index=False)
    strat_3r.to_csv(out_dir / 'strat_3r_trades.csv', index=False)
    strat_sum_2r.to_csv(out_dir / 'strat_2r_summary.csv', index=False)
    strat_sum_3r.to_csv(out_dir / 'strat_3r_summary.csv', index=False)

    chart_rows: list[dict] = []
    if make_charts and not setups.empty:
        s2_by_id = {int(r['setup_id']): r for _, r in strat_2r.iterrows()}
        s3_by_id = {int(r['setup_id']): r for _, r in strat_3r.iterrows()}
        resolved_ids = set(
            strat_2r[strat_2r['outcome'].isin(['tp', 'sl'])]['setup_id'].tolist() +
            strat_3r[strat_3r['outcome'].isin(['tp', 'sl'])]['setup_id'].tolist()
        )
        for _, setup in setups.iterrows():
            sid = int(setup['setup_id'])
            if sid not in resolved_ids:
                continue
            folder = 'hits' if bool(setup['hit']) else 'misses'
            fname = (
                f'{sid:04d}_{setup["direction"]}_{setup["c3_date"]}'
                f'_{"hit" if setup["hit"] else "miss"}.png'
            )
            chart_path = out_dir / 'charts' / folder / fname
            result = strat_trade_chart(
                daily, setup, s2_by_id.get(sid), s3_by_id.get(sid),
                chart_path, market, lookahead,
            )
            if result:
                chart_rows.append({
                    'setup_id': sid, 'direction': setup['direction'],
                    'c1': setup['c1_date'], 'c2': setup['c2_date'], 'c3': setup['c3_date'],
                    'hit': bool(setup['hit']),
                    'chart': str(Path(result).relative_to(out_dir)),
                })

    def _strat_rows(df: pd.DataFrame) -> list[str]:
        out = []
        for _, row in df.iterrows():
            avg_tp = f'{row["avg_days_tp"]:.1f}' if row['avg_days_tp'] is not None else '—'
            avg_sl = f'{row["avg_days_sl"]:.1f}' if row['avg_days_sl'] is not None else '—'
            swept = f'{int(row["n_swept_opposing"])} / {row["pct_swept_opposing"]:.1f}%'
            clean = f'{int(row["n_clean_body_tp"])} / {row["pct_clean_body_tp"]:.1f}%'
            out.append(
                f'| {row["direction"]} | {int(row["setups"])} | {int(row["no_breakout"])} | '
                f'{int(row["resolved"])} | {int(row["open_window"])} | '
                f'{int(row["tp"])} | {int(row["sl"])} | {row["hit_rate_pct"]:.2f}% | '
                f'{row["avg_mae_r"]:.3f} | {row["avg_mae_pts"]:.2f} | '
                f'{row["avg_breakout_day"]:.1f} | {avg_tp} | {avg_sl} | '
                f'{row["total_pnl_r"]:+.2f} | {row["total_pnl_pts"]:+.2f} | {swept} | {clean} |'
            )
        return out

    strat_hdr = (
        '| Direction | Setups | No Breakout | Resolved | open_window | TP | SL | Hit Rate | '
        'Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | '
        'Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |'
    )
    strat_sep = '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'

    lines = [
        f'# {market.upper()} Daily Candlestick Theory Study',
        '',
        f'Lookahead window for strategy: {lookahead} bars after C3.',
        '',
        '## Theory Summary',
        '',
        '| Direction | Setups | Hits | Hit Rate | C3 Close Beyond | Close Rate | '
        'Avg Extension | Median Extension | Avg Adverse | Worst Adverse |',
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
        'OC = C3 bar.  R = OC.high − OC.low.  Breakout: first bar in lookahead window '
        'that closes beyond OC.  Entry at breakout close.  SL = entry ± 2R.  TP = entry ± 2R.',
        '',
        strat_hdr, strat_sep,
    ] + _strat_rows(strat_sum_2r)

    lines += [
        '',
        '## Strategy: Breakout-Candle Entry · TP = 3R',
        '',
        'Same entry/SL rules.  TP = entry ± 3R.',
        '',
        strat_hdr, strat_sep,
    ] + _strat_rows(strat_sum_3r)

    lines += [
        '',
        '## Skipped / Failure Sweep Context',
        '',
        f'- High failure sweeps: {skipped["high_failure_sweeps"]}',
        f'- Low failure sweeps: {skipped["low_failure_sweeps"]}',
        f'- Unique non-signal failure-sweep bars: {skipped["unique_failure_sweep_bars"]}',
        f'- Non-signal rolling windows: {skipped["non_signal_bars"]}',
        '',
        'CSV outputs: `setups.csv` · `summary.csv` · `strat_2r_trades.csv` · '
        '`strat_3r_trades.csv` · `strat_2r_summary.csv` · `strat_3r_summary.csv`',
        '',
    ]

    if chart_rows:
        lines += ['## Charts', '', '| Setup | Direction | C1 | C2 | C3 | Hit | Chart |', '|---:|---|---|---|---|---|---|']
        for row in chart_rows:
            lines.append(
                f'| {row["setup_id"]} | {row["direction"]} | {row["c1"]} | {row["c2"]} | '
                f'{row["c3"]} | {row["hit"]} | [{Path(row["chart"]).name}]({row["chart"]}) |'
            )
        lines.append('')

    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--market', default='NQ')
    ap.add_argument('--lookahead', type=int, default=20,
                    help='Bars after C3 to search for breakout and track TP/SL (default 20)')
    ap.add_argument('--charts', action='store_true',
                    help='Generate charts for resolved strategy trades (off by default)')
    args = ap.parse_args()

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    daily = daily.sort_values('date').reset_index(drop=True)

    setups, skipped = classify_setups(daily)
    summary_df = summarize(setups)

    strat_2r = simulate_strat(daily, setups, tp_mult=2.0, lookahead=args.lookahead)
    strat_3r = simulate_strat(daily, setups, tp_mult=3.0, lookahead=args.lookahead)
    strat_sum_2r = strat_summary(strat_2r, tp_mult=2.0)
    strat_sum_3r = strat_summary(strat_3r, tp_mult=3.0)

    write_outputs(
        args.out, args.market, daily, setups, summary_df, skipped,
        args.charts, strat_2r, strat_3r, strat_sum_2r, strat_sum_3r, args.lookahead,
    )

    print('=== Daily Theory Summary ===')
    print(summary_df.to_string(index=False))
    print()
    print('=== Strategy · TP = 2R ===')
    print(strat_sum_2r.to_string(index=False))
    print()
    print('=== Strategy · TP = 3R ===')
    print(strat_sum_3r.to_string(index=False))
    print(f'\nwrote {args.out}  ({len(setups)} setups)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
