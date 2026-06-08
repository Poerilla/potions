#!/usr/bin/env python3
"""
Build 5m candle charts for v2b rows with London sweep (Opp_sweep_London_H or
Opp_sweep_London_L).

**Strategies** (--strategy):

- **v2e-limit**: causal v2e limits at London H/L (``sim_london_limit_scaleout``),
  first RTH touch or v2b row side.

- **child-after-sweep** (default): after RTH sweep, **tier‑1 limit at London L/H**; then qualifying **inside-range** 5m children for adds; up to 3 contracts with split stops (tier‑1
  wide SL same as v2e; children stop at London boundary); TP opposing corner. Writes PNGs to
  ``--out/winners``, ``--out/losers``, ``--out/skipped``.

London H/L from **02:00–09:30 ET** 1m only.

**Day universe:** ``--day-universe opp_sweep`` (default) uses annotator sweep rows only.
``--day-universe all_rth`` walks NY **weekdays** in ``--start``/``--end`` (defaults: min/max
Date in annotated CSV) and keeps sessions with RTH 1m in **[09:30, 16:00) ET** — same slice as
``case_studies/swept_liquidity_orb_breakout`` chart loaders. Child-after-sweep then sets sweep path
from **first** RTH London sweep (optional ``None`` to ``simulate_london_child_after_sweep``).

Requires extended-hours 1m Databento OHLCV export.

Output (v2e-limit):  mnq/v2e/case_studies/london_sweep/<date>_{Long|Short}.png + INDEX.md

Output (child-after-sweep): winners/ losers/ skipped/ + INDEX.md
"""
import argparse
import sys
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Reuse 1m loader from annotator (single source of truth for front month + filter)
V2E_ROOT = Path(__file__).resolve().parent.parent
V2E_SCR = Path(__file__).resolve().parent
POTIONS = V2E_ROOT.parent.parent
sys.path.insert(0, str(V2E_SCR))
from sim_london_limit_scaleout import (  # noqa: E402
    DOLLARS_PER_POINT,
    N_CONTRACTS,
    first_rth_touch_side,
    london_0200_0930_hilo,
    rth_1m,
    v2e_chart_path_long,
    v2e_chart_path_short,
)
from sim_london_child_after_sweep import LondonChildSim, simulate_london_child_after_sweep  # noqa: E402
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

NY = pytz.timezone('America/New_York')
TICK = 0.25
NLOT = N_CONTRACTS
OUT_DIR = V2E_ROOT / 'case_studies' / 'london_sweep'
ANNOTATED = POTIONS / 'mnq' / 'mnq_orb_results_stops_annotated.csv'
M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
CHART_LO = time(0, 30)  # start plot at 0:30 ET (Globex)
CHART_HI = time(16, 0)
# Full overnight + RTH for “opens research” charts (00:00–16:00 NY)
CHART_OPENS_LO = time(0, 0)
CHART_OPENS_HI = time(16, 0)
# RTH 1m slice [09:30, 16:00) ET — matches ``swept_liquidity_orb_breakout/{sweep_orb_backtest,build_random_samples_swept_orb}.py``.


def session_has_rth_like_swept_orb(day_b: pd.DataFrame) -> bool:
    """Include session days that have at least one RTH bar (same filter as swept ORB chart loaders)."""
    return day_b is not None and not day_b.empty and not rth_1m(day_b).empty


def synthetic_v2b_row(session_d: date, symbol: str) -> pd.Series:
    """Placeholder row when iterating ``--day-universe all_rth`` (no v2b leg)."""
    return pd.Series(
        {
            'Date': session_d,
            'Trade_Direction': '—',
            'Trade_PL': np.nan,
            'Net_$': np.nan,
            'Result': '—',
            'Symbol': symbol,
        }
    )


def symbol_from_day_b(day_b: pd.DataFrame) -> str:
    if day_b is not None and not day_b.empty and 'symbol' in day_b.columns:
        return str(day_b['symbol'].iloc[0])
    return 'MNQ'


def child_chart_side_label(sw_low: Optional[bool], sim: LondonChildSim) -> str:
    if sim.direction:
        return sim.direction
    if sw_low is True:
        return 'Long'
    if sw_low is False:
        return 'Short'
    return 'Skip'


def _fmt_trade_pl_pt(trade_row) -> str:
    v = trade_row.get('Trade_PL', np.nan)
    try:
        if pd.isna(v):
            return '—pt'
        return f'{float(v):+.0f}pt'
    except (TypeError, ValueError):
        return '—pt'


def trim_chart_session(df1: pd.DataFrame) -> pd.DataFrame:
    """0:30–16:00 ET 1m for one trading day (keeps London + RTH)."""
    return df1[
        df1.index.map(lambda t: CHART_LO <= t.time() < CHART_HI)
    ]


def trim_chart_opens_session(df1: pd.DataFrame) -> pd.DataFrame:
    """00:00–16:00 ET 1m (midnight through RTH close) for open-level research."""
    return df1[
        df1.index.map(lambda t: CHART_OPENS_LO <= t.time() < CHART_OPENS_HI)
    ]


def ny_midnight_open_px(df1: pd.DataFrame) -> float:
    """
    Open of the first 1m at/after 00:00 NY on this session’s index date.
    If no 00:00 bar, first bar in 00:00–00:14.
    """
    if df1.empty:
        return float('nan')
    try:
        w = df1.between_time('00:00', '00:14', inclusive='left')
    except (TypeError, ValueError):
        w = df1[df1.index.map(lambda t: t.hour == 0 and t.minute < 15)]
    if w.empty:
        return float('nan')
    w = w.sort_index()
    return float(w.iloc[0]['open'])


def ny_rth_0930_open_px(df1: pd.DataFrame) -> float:
    """Open of the 09:30 NY 1m (regular session start)."""
    if df1.empty:
        return float('nan')
    try:
        w = df1.between_time('09:30', '09:31', inclusive='left')
    except (TypeError, ValueError):
        w = df1[df1.index.map(lambda t: t.time() >= time(9, 30) and t.time() < time(9, 32))]
    if not w.empty:
        return float(w.sort_index().iloc[0]['open'])
    rth = rth_1m(df1)
    if rth.empty:
        return float('nan')
    return float(rth.iloc[0]['open'])


def premarket_hilo(gby: Dict[date, pd.DataFrame], session_d: date) -> Tuple[float, float]:
    """
    High / low from **extended pre-RTH** window: **prior NY calendar day from 18:00 ET**
    (post–equity pit / globex evening) through **session day strictly before 09:30** —
    i.e. Asian + overnight + early morning, not only 02:00–09:30 London.
    """
    parts: list[pd.DataFrame] = []
    prev = gby.get(session_d - timedelta(days=1))
    if prev is not None and not prev.empty:
        ev = prev[prev.index.map(lambda t: t.time() >= time(18, 0))]
        if not ev.empty:
            parts.append(ev)
    cur = gby.get(session_d)
    if cur is not None and not cur.empty:
        am = cur[cur.index.map(lambda t: t.time() < time(9, 30))]
        if not am.empty:
            parts.append(am)
    if not parts:
        return float('nan'), float('nan')
    comb = pd.concat(parts).sort_index()
    return float(comb['high'].max()), float(comb['low'].min())


def build_opens_chart_window_1m(gby: Dict[date, pd.DataFrame], session_d: date) -> pd.DataFrame:
    """
    1m series for the chart: **previous calendar day 18:00 ET** through **session day 16:00** (NY),
    so the overnight segment is visible with RTH.
    """
    parts: list[pd.DataFrame] = []
    prev = gby.get(session_d - timedelta(days=1))
    if prev is not None and not prev.empty:
        pe = prev[prev.index.map(lambda t: t.time() >= time(18, 0))]
        if not pe.empty:
            parts.append(pe)
    cur = gby.get(session_d)
    if cur is not None and not cur.empty:
        cur_slice = cur[cur.index.map(lambda t: t.time() < time(16, 0))]
        if not cur_slice.empty:
            parts.append(cur_slice)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def _orb_rh_rl_session_day(gby: Dict[date, pd.DataFrame], session_d: date) -> Tuple[float, float]:
    cur = gby.get(session_d)
    if cur is None or cur.empty:
        return float('nan'), float('nan')
    rng = cur[(cur.index.time >= time(9, 30)) & (cur.index.time < time(9, 45))]
    if rng.empty:
        return float('nan'), float('nan')
    return float(rng['high'].max()), float(rng['low'].min())


def draw_chart(
    date_obj,
    df1: pd.DataFrame,
    trade_row,
    outpath: Path,
    sl_points: float,
    limit_offset_ticks: int,
    v2e_side: str,
    case_study_tag: str = 'London sweep (annot)',
    sl_mode: str = 'london_range',
):
    """
    Causal v2e: 02:00–09:30 H/L from 1m, 5 MNQ, 2@Ldn mid + 3@opposite Ldn, SL in points.
    `v2e_side` = 'Short' or 'Long' (from first RTH touch or v2b row, per --side-from).
    ORB (9:30–9:45) from 1m is drawn only for reference.
    `case_study_tag` — short label for the title (e.g. all-trades batch vs London sweep).
    """
    if df1.empty:
        return None
    rng = df1[(df1.index.time >= time(9, 30)) & (df1.index.time < time(9, 45))]
    if rng.empty:
        return None
    rh, rl = float(rng['high'].max()), float(rng['low'].min())
    ldn_h, ldn_l = london_0200_0930_hilo(df1)
    if np.isnan(ldn_h) or np.isnan(ldn_l):
        return None
    rth = rth_1m(df1)
    if rth.empty:
        return None

    d = v2e_side
    r = trade_row
    if d == 'Short':
        p = v2e_chart_path_short(
            rth, ldn_h, ldn_l, sl_points, limit_offset_ticks, sl_mode=sl_mode,
        )
    else:
        p = v2e_chart_path_long(
            rth, ldn_h, ldn_l, sl_points, limit_offset_ticks, sl_mode=sl_mode,
        )

    if p.reason == 'no_level':
        return None

    no_fill = not p.filled and p.reason == 'no_fill'
    e_time, x_time = p.entry_ts, p.exit_ts
    if not no_fill and e_time is None:
        return None
    if x_time is None or (no_fill and x_time is None):
        x_time = df1.index[-1]

    pt_equiv = p.pnl_dollars / (DOLLARS_PER_POINT * NLOT) if p.filled else 0.0
    trades = [{
        'direction': d,
        'entry': p.entry_px,
        'exit_price': p.exit_px,
        'sl': p.sl,
        'tp1': p.tp1,
        'tp2': p.tp2,
        'ldn_mid': p.ldn_mid,
        'mfe_past': p.mfe_past_opposite_london_pts,
        'result': p.result_label,
        'entry_time': e_time,
        'exit_time': x_time,
        'pl_pts': pt_equiv,
        'pnl_v2e': p.pnl_dollars,
        'no_fill': no_fill,
        'n_stop': p.n_stop,
        'n_tp1': p.n_tp1,
        'n_tp2': p.n_tp2,
        'n_eod': p.n_eod,
        'tp1_done_ts': getattr(p, 'tp1_done_ts', None),
        'tp2_done_ts': getattr(p, 'tp2_done_ts', None),
    }]
    t = trades[0]

    bars5 = (
        df1.resample('5min', label='left', closed='right')
        .agg(open=('open', 'first'), high=('high', 'max'),
             low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )
    if bars5.empty:
        return None

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    # ORB 9:30–9:45 (5m can start at 00:30, so do not use bars5.index[0])
    orbm = (bars5.index.hour == 9) & (bars5.index.minute >= 30) & (bars5.index.minute < 45)
    if orbm.any():
        t0 = bars5[orbm].index[0]
        ax.axvspan(t0, t0 + pd.Timedelta(minutes=15), color='#1F4E79', alpha=0.30, zorder=0)
    # 15m ORB reference (not used for v2e levels)
    ax.axhline(rh, color='#78909C', linestyle='--', linewidth=0.8, zorder=1, alpha=0.5)
    ax.axhline(rl, color='#78909C', linestyle='--', linewidth=0.8, zorder=1, alpha=0.5)
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.08, zorder=0)
    # v2e: Ldn-based stop + scale-out targets (2 @ mid, 3 @ opp, 5 MNQ)
    if not (np.isnan(t['sl']) or pd.isna(t['sl'])):
        ax.axhline(t['sl'], color='#FF5252', linestyle='-', linewidth=1.2, alpha=0.85, zorder=2)
    if not (np.isnan(t['tp1']) or pd.isna(t['tp1'])):
        ax.axhline(t['tp1'], color='#81C784', linestyle='--', linewidth=1.0, alpha=0.9, zorder=2)
    if not (np.isnan(t['tp2']) or pd.isna(t['tp2'])):
        ax.axhline(t['tp2'], color='#69F0AE', linestyle='--', linewidth=1.0, alpha=0.75, zorder=2)
    if not (np.isnan(t['entry']) or pd.isna(t['entry'])):
        ax.axhline(t['entry'], color='#FFC107', linestyle=':', linewidth=1.1, alpha=0.75, zorder=2)
    # Causal 02:00–09:30 box H/L
    if not (pd.isna(ldn_h) or np.isnan(ldn_h)):
        ax.axhline(
            ldn_h, color='#4DD0E1', linestyle='-.', linewidth=1.3, zorder=2, alpha=0.95
        )
    if not (pd.isna(ldn_l) or np.isnan(ldn_l)):
        ax.axhline(
            ldn_l, color='#E040FB', linestyle='-.', linewidth=1.3, zorder=2, alpha=0.95
        )

    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=c,
                edgecolor=c,
                alpha=0.95,
                zorder=3,
            )
        )

    if not t['no_fill']:
        for ts_ev, col in (
            (t.get('tp1_done_ts'), '#B0BEC5'),
            (t.get('tp2_done_ts'), '#90A4AE'),
        ):
            if ts_ev is not None and not (isinstance(ts_ev, float) and (np.isnan(ts_ev) or pd.isna(ts_ev))):
                xev = mdates.date2num(ts_ev)
                ax.axvline(xev, color=col, linestyle='-', linewidth=1.1, alpha=0.9, zorder=4, clip_on=False)

    color_for = {
        'Win': '#76FF03', 'Loss': '#FF1744', 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D',
        'Stop-BE': '#FFAB40', 'EOD': '#FFB74D',
    }
    label_offset = [+24, -36]
    x_e = mdates.date2num(t['entry_time']) if t['entry_time'] is not None else None
    x_x = mdates.date2num(t['exit_time'])
    if not t['no_fill'] and x_e is not None:
        ax.scatter(
            [x_e], [t['entry']],
            marker='^' if t['direction'] == 'Long' else 'v',
            color='#FFC107',
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f"{NLOT} MNQ v2e  {'L' if t['direction'] == 'Long' else 'S'}  @ {t['entry']:.2f}  "
            f"(limit @ Ldn {'L' if t['direction'] == 'Long' else 'H'}; 1@mid 1@opp; SL {sl_mode})",
            xy=(x_e, t['entry']),
            xytext=(8, label_offset[0]),
            textcoords='offset points',
            color='#FFC107',
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
        )
    else:
        ax.text(
            0.02, 0.95,
            'v2e: no RTH fill at London limit (09:30–16:00 first touch)\n'
            f'  Limit would be {t["entry"]:.2f}  ·  v2b row for reference: {r.get("Result")}  {r.get("Trade_PL", 0):+.0f}pt',
            transform=ax.transAxes,
            color='#FFAB40',
            fontsize=9,
            fontweight='bold',
            va='top',
            bbox=dict(boxstyle='round,pad=0.4', fc='#0D1B2A', ec='#FFAB40', alpha=0.95),
            zorder=10,
        )
    c = color_for.get(t['result'], '#FFC107')
    if not t['no_fill'] and t['exit_time'] is not None and not (np.isnan(t['exit_price']) or pd.isna(t['exit_price'])):
        ax.scatter(
            [x_x], [t['exit_price']],
            marker='X',
            color=c,
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        mfe_t = t.get('mfe_past', np.nan)
        mfe_s = f"  MFE past TP2: {mfe_t:+.1f} pt" if not (isinstance(mfe_t, float) and np.isnan(mfe_t)) else ''
        ns = int(t.get('n_stop', 0) or 0)
        stop_s = f"  stop {ns}/{NLOT}" if ns else ''
        ax.annotate(
            f"{t['result']}  ${t['pnl_v2e']:+,.0f}  (5 MNQ){stop_s}{mfe_s}",
            xy=(x_x, t['exit_price']),
            xytext=(8, label_offset[1]),
            textcoords='offset points',
            color=c,
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec=c, alpha=0.95),
        )

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=8, va='center')
    if not (pd.isna(ldn_h) or np.isnan(ldn_h)):
        ax.text(last_x, ldn_h, f'  2–9:30 H {ldn_h:.2f}', color='#4DD0E1', fontsize=7, va='center')
    if not (pd.isna(ldn_l) or np.isnan(ldn_l)):
        ax.text(last_x, ldn_l, f'  2–9:30 L {ldn_l:.2f}', color='#E040FB', fontsize=7, va='center')

    sym = trade_row.get('Symbol', '')
    v2b_pl = r.get('Trade_PL', 0.0)
    v2b_dir = r.get('Trade_Direction', '')
    sl_title = f"Ldn range" if sl_mode == 'london_range' else f"{sl_points} idx-pt"
    title = (
        f"{date_obj}  ·  {sym}  ·  v2e side {d}  ·  v2b row {v2b_dir}  ·  {case_study_tag}  "
        f"·  v2e: SL {sl_title}  {('no fill' if t['no_fill'] else t['result'])}  "
        f"·  v2b same row: {r.get('Result', '')}  {v2b_pl:+.0f}pt  (1 lot)"
    )
    ax.set_title(title, color='white', fontsize=12, fontweight='bold', pad=10, loc='left')
    ax.set_xlabel('NY time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel('Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(
        bars5.index[0] - pd.Timedelta(minutes=8),
        bars5.index[-1] + pd.Timedelta(minutes=25),
    )
    y0, y1 = ax.get_ylim()
    ax.plot([], [], color='#4DD0E1', linestyle='-.', label='2:00–9:30 H (causal)')
    ax.plot([], [], color='#E040FB', linestyle='-.', label='2:00–9:30 L (causal)')
    ax.plot([], [], color='#81C784', linestyle='--', label='TP1: Ldn mid (1@)')
    ax.plot([], [], color='#69F0AE', linestyle='--', label='TP2: opp. Ldn (1@)')
    ax.plot([], [], color='#B0BEC5', linestyle='-', label='V-line: 2@ fill time')
    ax.plot([], [], color='#90A4AE', linestyle='-', label='V-line: 3@ fill time')
    ax.legend(
        loc='upper left', facecolor='#0D1B2A', edgecolor='#3A506B', fontsize=7, labelcolor='white'
    )
    ax.set_ylim(y0, y1)

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return True


def row_sweep_low(row) -> Optional[bool]:
    """True = Opp_sweep_London_L row (long path); False = Opp_sweep_London_H (short)."""
    ol = row.get('Opp_sweep_London_L')
    oh = row.get('Opp_sweep_London_H')

    def one(v) -> bool:
        if pd.isna(v):
            return False
        try:
            return abs(float(v) - 1.0) < 1e-6
        except (TypeError, ValueError):
            return False

    if one(ol):
        return True
    if one(oh):
        return False
    return None


def draw_chart_london_child_after_sweep(
    date_obj,
    df1: pd.DataFrame,
    trade_row,
    outpath: Path,
    sl_points: float,
    sl_mode: str,
    sweep_low: Optional[bool],
    *,
    require_causal_orb_pierce: bool = True,
):
    """After-sweep child limits + split stops (see sim_london_child_after_sweep)."""
    if df1.empty:
        return False
    rng = df1[(df1.index.time >= time(9, 30)) & (df1.index.time < time(9, 45))]
    if rng.empty:
        return False
    rh, rl = float(rng['high'].max()), float(rng['low'].min())
    ldn_h, ldn_l = london_0200_0930_hilo(df1)
    if np.isnan(ldn_h) or np.isnan(ldn_l):
        return False

    s = simulate_london_child_after_sweep(
        df1, ldn_h, ldn_l, sweep_low, sl_points, sl_mode=sl_mode,
        require_causal_orb_pierce=require_causal_orb_pierce,
    )
    dir_lab = child_chart_side_label(sweep_low, s)

    bars5 = (
        df1.resample('5min', label='left', closed='right')
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )
    if bars5.empty:
        return False

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    orbm = (bars5.index.hour == 9) & (bars5.index.minute >= 30) & (bars5.index.minute < 45)
    if orbm.any():
        t0 = bars5[orbm].index[0]
        ax.axvspan(t0, t0 + pd.Timedelta(minutes=15), color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhline(rh, color='#78909C', linestyle='--', linewidth=0.8, zorder=1, alpha=0.5)
    ax.axhline(rl, color='#78909C', linestyle='--', linewidth=0.8, zorder=1, alpha=0.5)
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.08, zorder=0)

    if np.isfinite(s.stop_wide):
        ax.axhline(s.stop_wide, color='#FF5252', linestyle='-', linewidth=1.2, alpha=0.85, zorder=2)
    if np.isfinite(s.tp_px):
        ax.axhline(s.tp_px, color='#64B5F6', linestyle='-', linewidth=1.1, alpha=0.9, zorder=2)
    if np.isfinite(s.stop_tight_boundary):
        ax.axhline(
            s.stop_tight_boundary, color='#FFB74D', linestyle=':', linewidth=1.0, alpha=0.85, zorder=2,
        )

    ax.axhline(ldn_h, color='#4DD0E1', linestyle='-.', linewidth=1.3, zorder=2, alpha=0.95)
    ax.axhline(ldn_l, color='#E040FB', linestyle='-.', linewidth=1.3, zorder=2, alpha=0.95)

    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=c,
                edgecolor=c,
                alpha=0.95,
                zorder=3,
            )
        )

    color_for = {
        'Win': '#76FF03', 'Loss': '#FF1744', 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D',
    }
    label_offset = [+24, -36]
    if s.filled and s.entry_ts is not None:
        x_e = mdates.date2num(s.entry_ts)
        ax.scatter(
            [x_e], [s.entry_avg_px],
            marker='^' if dir_lab == 'Long' else 'v',
            color='#FFC107',
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f"{s.contracts_peak} MNQ @ avg {s.entry_avg_px:.2f}  (child-after-sweep; split SL)",
            xy=(x_e, s.entry_avg_px),
            xytext=(8, label_offset[0]),
            textcoords='offset points',
            color='#FFC107',
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
        )
    else:
        ax.text(
            0.02, 0.95,
            f"No setup: {s.reason}\n"
            f"v2b row ref: {trade_row.get('Trade_Direction','')}  {_fmt_trade_pl_pt(trade_row)}",
            transform=ax.transAxes,
            color='#FFAB40',
            fontsize=9,
            fontweight='bold',
            va='top',
            bbox=dict(boxstyle='round,pad=0.4', fc='#0D1B2A', ec='#FFAB40', alpha=0.95),
            zorder=10,
        )

    if s.filled and s.exit_ts is not None:
        c = color_for.get(s.result_label, '#FFC107')
        x_x = mdates.date2num(s.exit_ts)
        ax.scatter(
            [x_x], [s.exit_px],
            marker='X',
            color=c,
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f"{s.result_label}  Net ${s.net_dollars:+,.2f}  (gross ${s.gross_dollars:+,.2f}, fee ${s.fee_dollars:.2f})",
            xy=(x_x, s.exit_px),
            xytext=(8, label_offset[1]),
            textcoords='offset points',
            color=c,
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec=c, alpha=0.95),
        )

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, ldn_h, f'  2–9:30 H {ldn_h:.2f}', color='#4DD0E1', fontsize=7, va='center')
    ax.text(last_x, ldn_l, f'  2–9:30 L {ldn_l:.2f}', color='#E040FB', fontsize=7, va='center')

    r = trade_row
    sym = trade_row.get('Symbol', '')
    title = (
        f"{date_obj}  ·  {sym}  ·  London child-after-sweep  ·  side {dir_lab}  ·  {s.reason}  "
        f"·  v2b {r.get('Trade_Direction','')} {_fmt_trade_pl_pt(r)}"
    )
    if s.filled:
        title += f"  ·  model Net ${s.net_dollars:+,.2f}"
    ax.set_title(title, color='white', fontsize=11, fontweight='bold', pad=10, loc='left')
    ax.set_xlabel('NY time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel('Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for sp in ax.spines.values():
        sp.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(
        bars5.index[0] - pd.Timedelta(minutes=8),
        bars5.index[-1] + pd.Timedelta(minutes=25),
    )
    y0, y1 = ax.get_ylim()
    ax.plot([], [], color='#4DD0E1', linestyle='-.', label='2:00–9:30 H')
    ax.plot([], [], color='#E040FB', linestyle='-.', label='2:00–9:30 L')
    ax.plot([], [], color='#FF5252', linestyle='-', label='Wide SL (tier‑1)')
    ax.plot([], [], color='#FFB74D', linestyle=':', label='Boundary SL (children)')
    ax.plot([], [], color='#64B5F6', linestyle='-', label='TP opposite corner')
    ax.legend(
        loc='upper left', facecolor='#0D1B2A', edgecolor='#3A506B', fontsize=7, labelcolor='white'
    )
    ax.set_ylim(y0, y1)

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return True


def draw_opens_research_chart(
    date_obj: date,
    gby: Dict[date, pd.DataFrame],
    session_d: date,
    trade_row,
    outpath: Path,
    v2e_side: str,
    case_study_tag: str = 'opens research',
    show_orb_ref: bool = True,
    prior_week_close: Optional[float] = None,
    *,
    level_entry: Optional[float] = None,
    level_tp: Optional[float] = None,
    level_sl: Optional[float] = None,
):
    """
    5m candles from **prev day 18:00 ET** through **session 16:00** (overnight visible).

    Horizontals: **NY 00:00** and **9:30 RTH** 1m opens; **premarket high / low** (H/L from
    prev 18:00 through **< 9:30** on session day — Asia + full overnight, not 02:00 only);
    **prior week last close** (daily) with above/below vs 9:30 open. No v2e trade marks.

    *Premarket* H/L: extended electronic window, not the old 02:00–09:30 London-only box.
    *Prior week close*: last **close** of the Mon–Fri week before this session’s week
    (from daily DBN).
    """
    day_only = gby.get(session_d)
    if day_only is None or day_only.empty:
        return None
    o_mid = ny_midnight_open_px(day_only)
    o_930 = ny_rth_0930_open_px(day_only)
    pmh, pml = premarket_hilo(gby, session_d)
    pwc = prior_week_close
    if pwc is not None and (isinstance(pwc, float) and (np.isnan(pwc) or not np.isfinite(pwc))):
        pwc = None

    chart_1m = build_opens_chart_window_1m(gby, session_d)
    if chart_1m.empty:
        return None
    chart_1m = chart_1m.sort_index()
    df_plot = chart_1m
    rh, rl = _orb_rh_rl_session_day(gby, session_d)

    bars5 = (
        df_plot.resample('5min', label='left', closed='right')
        .agg(open=('open', 'first'), high=('high', 'max'),
             low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )
    if bars5.empty:
        return None

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    if show_orb_ref and np.isfinite(rh) and np.isfinite(rl):
        orbm = (bars5.index.hour == 9) & (bars5.index.minute >= 30) & (bars5.index.minute < 45)
        if orbm.any():
            t0 = bars5[orbm].index[0]
            ax.axvspan(t0, t0 + pd.Timedelta(minutes=15), color='#1F4E79', alpha=0.22, zorder=0)
        ax.axhline(rh, color='#78909C', linestyle='--', linewidth=0.7, zorder=1, alpha=0.45)
        ax.axhline(rl, color='#78909C', linestyle='--', linewidth=0.7, zorder=1, alpha=0.45)
        ax.axhspan(rl, rh, color='#1F4E79', alpha=0.06, zorder=0)

    if level_sl is not None and np.isfinite(level_sl):
        ax.axhline(
            level_sl, color='#EF5350', linestyle='-', linewidth=1.0, zorder=3, alpha=0.95,
            label='_nolegend_',
        )
    if level_entry is not None and np.isfinite(level_entry):
        ax.axhline(
            level_entry, color='#A5D6A7', linestyle='-', linewidth=1.0, zorder=3, alpha=0.95,
            label='_nolegend_',
        )
    if level_tp is not None and np.isfinite(level_tp):
        ax.axhline(
            level_tp, color='#64B5F6', linestyle='-', linewidth=1.0, zorder=3, alpha=0.92,
            label='_nolegend_',
        )

    # Session-day 0:00 and 9:30 verticals (in session_d local)
    try:
        t_anchor = gby[session_d].index.min() if not gby[session_d].empty else None
        if t_anchor is not None:
            d_zero = t_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
            if df_plot.index.max() >= d_zero:
                ax.axvline(mdates.date2num(d_zero), color='#546E7A', linestyle=':', linewidth=0.9, alpha=0.5, zorder=1)
            d93 = t_anchor.replace(hour=9, minute=30, second=0, microsecond=0)
            if df_plot.index.max() >= d93:
                ax.axvline(mdates.date2num(d93), color='#90A4AE', linestyle=':', linewidth=0.9, alpha=0.6, zorder=1)
    except Exception:
        pass

    if np.isfinite(pmh) and np.isfinite(pml) and pml <= pmh + 1e-9:
        ax.axhline(pmh, color='#FF9800', linestyle='-', linewidth=1.3, zorder=2, alpha=0.92)
        ax.axhline(pml, color='#AB47BC', linestyle='-', linewidth=1.3, zorder=2, alpha=0.92)
    if np.isfinite(o_mid):
        ax.axhline(o_mid, color='#26C6DA', linestyle='-', linewidth=1.4, zorder=2, alpha=0.95)
    if np.isfinite(o_930):
        ax.axhline(o_930, color='#FFEB3B', linestyle='-', linewidth=1.4, zorder=2, alpha=0.95)
    if pwc is not None and np.isfinite(pwc):
        ax.axhline(pwc, color='#ECEFF1', linestyle='--', linewidth=1.1, zorder=2, alpha=0.85)

    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=c,
                edgecolor=c,
                alpha=0.95,
                zorder=3,
            )
        )

    pwc_note = ''
    r = trade_row
    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    if np.isfinite(pmh):
        ax.text(last_x, pmh, f'  Premkt H {pmh:.2f}', color='#FF9800', fontsize=7, va='center')
    if np.isfinite(pml):
        ax.text(last_x, pml, f'  Premkt L {pml:.2f}', color='#AB47BC', fontsize=7, va='center')
    if np.isfinite(o_mid):
        ax.text(last_x, o_mid, f'  00:00 O {o_mid:.2f}', color='#26C6DA', fontsize=8, va='center')
    if np.isfinite(o_930):
        ax.text(last_x, o_930, f'  9:30 O {o_930:.2f}', color='#FFEB3B', fontsize=8, va='center')
    if pwc is not None and np.isfinite(pwc):
        ax.text(last_x, pwc, f'  Prior wk close {pwc:.2f}', color='#ECEFF1', fontsize=7, va='center')
    if show_orb_ref and np.isfinite(rh):
        ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=7, va='center', alpha=0.7)
    if show_orb_ref and np.isfinite(rl):
        ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=7, va='center', alpha=0.7)

    sym = trade_row.get('Symbol', '')
    v2b_pl = r.get('Trade_PL', 0.0)
    v2b_dir = r.get('Trade_Direction', '')
    regime = ''
    net_disp = ''
    try:
        if hasattr(r, 'get'):
            reg = str(r.get('Regime', '')).strip()
            regime = reg if reg and reg.lower() != 'nan' else ''
            nx = r.get('Net_$')
            if nx is not None and pd.notna(nx):
                xf = float(nx)
                if np.isfinite(xf):
                    net_disp = f'  Net ${xf:.0f}'
    except (TypeError, ValueError):
        pass

    if pwc is not None and np.isfinite(pwc) and np.isfinite(o_930):
        dlt = o_930 - pwc
        if abs(dlt) < 0.5:
            pwc_note = f'9:30 open ≈ prior wk close (Δ {dlt:+.1f} pt)  ·  '
        elif o_930 > pwc:
            pwc_note = f'9:30 ABOVE prior wk close (Δ {dlt:+.1f} pt)  ·  '
        else:
            pwc_note = f'9:30 BELOW prior wk close (Δ {dlt:+.1f} pt)  ·  '

    title = (
        f"{date_obj}  ·  {sym}  ·  ref side {v2e_side}  ·  {case_study_tag}  ·  "
        f"Premkt H/L: prev 18:00 through before 9:30; PWC = prior week last daily close  ·  {pwc_note}"
        f"{(regime + '  ') if regime else ''}trade row: {v2b_dir}  {v2b_pl:+.0f}pt"
        f"{net_disp}"
    )
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=10, loc='left')
    ax.text(
        0.01, 0.02,
        '5m: long if close > 9:30 or midnight open (your rule, not backtested). '
        'Premarket range = full overnight electronic window, not 02:00 London-only.',
        transform=ax.transAxes, color='#B0BEC5', fontsize=7.5, va='bottom', ha='left',
    )
    ax.set_xlabel('NY time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel('Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(
        bars5.index[0] - pd.Timedelta(minutes=8),
        bars5.index[-1] + pd.Timedelta(minutes=25),
    )
    y0, y1 = ax.get_ylim()
    leg_h = [
        Line2D([0], [0], color='#FF9800', linewidth=2, linestyle='-', label='Premarket H (18:00→<9:30)'),
        Line2D([0], [0], color='#AB47BC', linewidth=2, linestyle='-', label='Premarket L (18:00→<9:30)'),
        Line2D([0], [0], color='#26C6DA', linewidth=2, linestyle='-', label='NY 00:00 open (1m)'),
        Line2D([0], [0], color='#FFEB3B', linewidth=2, linestyle='-', label='RTH 9:30 open (1m)'),
    ]
    if pwc is not None and np.isfinite(pwc):
        leg_h.append(
            Line2D([0], [0], color='#ECEFF1', linewidth=1.2, linestyle='--', label='Prior week last close (daily)'),
        )
    if show_orb_ref:
        leg_h.append(Line2D([0], [0], color='#78909C', linewidth=1, linestyle='--', label='ORB RH/RL (ref)'))
    if level_sl is not None and np.isfinite(level_sl):
        leg_h.append(Line2D([0], [0], color='#EF5350', linewidth=2, linestyle='-', label='Stop (model)'))
    if level_entry is not None and np.isfinite(level_entry):
        leg_h.append(Line2D([0], [0], color='#A5D6A7', linewidth=2, linestyle='-', label='Entry limit (model)'))
    if level_tp is not None and np.isfinite(level_tp):
        leg_h.append(Line2D([0], [0], color='#64B5F6', linewidth=2, linestyle='-', label='Target RH/RL ± Range'))
    ax.legend(
        handles=leg_h, loc='upper left', facecolor='#0D1B2A', edgecolor='#3A506B', fontsize=6.5,
        labelcolor='white',
    )
    ax.set_ylim(y0, y1)

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--annotated', type=Path, default=ANNOTATED, help='Annotated v2b CSV (with ctx London)'
    )
    ap.add_argument('--1m', dest='m1', type=Path, default=M1)
    ap.add_argument('--out', type=Path, default=OUT_DIR)
    ap.add_argument('--max', type=int, default=0, help='Cap number of charts (0 = all)')
    ap.add_argument(
        '--strategy',
        choices=('v2e-limit', 'child-after-sweep'),
        default='child-after-sweep',
        help='v2e-limit = limits @ Ldn H/L + mid/opp scale-out; '
        'child-after-sweep = tier‑1 @ London H/L + child adds + split stops + winners/losers folders',
    )
    ap.add_argument(
        '--day-universe',
        choices=('opp_sweep', 'all_rth'),
        default='opp_sweep',
        help='opp_sweep: Opp_sweep_London_* rows only. '
        'all_rth: NY weekdays in [--start,--end] with RTH 1m [09:30,16:00) (same slice as swept ORB charts). '
        'child-after-sweep infers Low-vs-High sweep path when not using annotator rows.',
    )
    ap.add_argument(
        '--start',
        default=None,
        help='ISO date lower bound (default: min Date in annotated CSV)',
    )
    ap.add_argument(
        '--end',
        default=None,
        help='ISO date upper bound (default: max Date in annotated CSV)',
    )
    ap.add_argument(
        '--sl-points', type=float, default=30.0,
        help='v2e stop in index points (causal Ldn); match sim_v2e_all',
    )
    ap.add_argument(
        '--limit-offset', type=int, default=0,
        help='[v2e-limit] 0 = limit at Ldn H/L; 1 = short 1 tick below LdnH / long 1 tick above LdnL',
    )
    ap.add_argument(
        '--sl-mode', choices=['london_range', 'fixed'], default='london_range',
        help='Stop width: Ldn range (default) or fixed --sl-points (match sim_v2e_all)',
    )
    ap.add_argument(
        '--side-from',
        choices=('first_rth_touch', 'v2b_row'),
        default='first_rth_touch',
        help='[v2e-limit] Chart side: first RTH touch of LdnH/LdnL or v2b Trade_Direction',
    )
    ap.add_argument(
        '--only-dates', nargs='*', default=(),
        help='If set, only these ISO dates (e.g. 2021-03-04 2021-05-21)',
    )
    ap.add_argument(
        '--skip-causal-orb-filter',
        action='store_true',
        help='Turn off annotator-style causal gate: ORB [9:30–9:45] RH/RL vs [02:00–09:30) London pierce '
        'aligned with sweep side (default: filter ON).',
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if args.day_universe == 'all_rth' and args.strategy == 'v2e-limit' and args.side_from == 'v2b_row':
        print(
            '--day-universe all_rth requires --side-from first_rth_touch for v2e-limit',
            file=sys.stderr,
        )
        return 1

    df = pd.read_csv(args.annotated)
    df['Date'] = pd.to_datetime(df['Date']).dt.date

    t_start = pd.to_datetime(args.start).date() if args.start else df['Date'].min()
    t_end = pd.to_datetime(args.end).date() if args.end else df['Date'].max()

    only_dates_set = {pd.to_datetime(s).date() for s in args.only_dates} if args.only_dates else None

    all_rth_days_ordered: Optional[List[date]] = None

    if args.day_universe == 'opp_sweep':
        sel = (df['Opp_sweep_London_H'] == 1) | (df['Opp_sweep_London_L'] == 1)
        sub = df[sel].copy()
        sub = sub[(sub['Date'] >= t_start) & (sub['Date'] <= t_end)]
        if only_dates_set is not None:
            sub = sub[sub['Date'].isin(only_dates_set)]
        if args.max:
            sub = sub.head(args.max)
        if sub.empty:
            print('No London sweep rows in annotated CSV for this filter', file=sys.stderr)
            return 1

        sub['Date'] = pd.to_datetime(sub['Date']).dt.date
        if args.strategy == 'v2e-limit' and args.side_from == 'first_rth_touch':
            sub = sub.drop_duplicates(subset='Date', keep='first')
        elif args.strategy == 'child-after-sweep':
            sub = sub.drop_duplicates(subset='Date', keep='first')

        need = set(sub['Date'].unique())
        run_label = 'London sweep'
    else:
        weeks = [ts.date() for ts in pd.bdate_range(pd.Timestamp(t_start), pd.Timestamp(t_end))]
        if only_dates_set is not None:
            weeks = [x for x in weeks if x in only_dates_set]
        if args.max:
            weeks = weeks[: args.max]
        all_rth_days_ordered = weeks
        need = set(weeks)
        sub = df.iloc[:0].copy()
        run_label = 'all-RTH weekdays'

    if not need:
        print('No session dates after filters', file=sys.stderr)
        return 1

    tmin, tmax = min(need), max(need)
    print(
        f'{run_label}: {len(need)} days  strategy={args.strategy}  day-universe={args.day_universe}',
        flush=True,
    )

    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    written: List[dict] = []

    if args.strategy == 'child-after-sweep':
        winners_dir = args.out / 'winners'
        losers_dir = args.out / 'losers'
        skipped_dir = args.out / 'skipped'
        winners_dir.mkdir(parents=True, exist_ok=True)
        losers_dir.mkdir(parents=True, exist_ok=True)
        skipped_dir.mkdir(parents=True, exist_ok=True)

        rows_to_run: List[Tuple[date, pd.Series, Optional[bool]]] = []
        if args.day_universe == 'opp_sweep':
            for _, row in sub.iterrows():
                rows_to_run.append((row['Date'], row, row_sweep_low(row)))
            n_plan = len(rows_to_run)
        else:
            assert all_rth_days_ordered is not None
            for _d in all_rth_days_ordered:
                rows_to_run.append((_d, pd.Series(dtype=object), None))
            n_plan = len(rows_to_run)

        for i, (d, r, sw_low) in enumerate(rows_to_run, 1):
            day = gby.get(d)
            if day is None or day.empty:
                print(f'  [{i}/{n_plan}] {d} no 1m, skip', flush=True)
                continue
            if args.day_universe == 'all_rth':
                if not session_has_rth_like_swept_orb(day):
                    print(f'  [{i}/{n_plan}] {d} no RTH [09:30,16:00) bars, skip', flush=True)
                    continue
                r = synthetic_v2b_row(d, symbol_from_day_b(day))
                sw_low = None
            else:
                if sw_low is None:
                    print(f'  [{i}/{n_plan}] {d} no Opp_sweep flag, skip', flush=True)
                    continue

            df1 = trim_chart_session(day)
            lh, ll = london_0200_0930_hilo(df1)
            orb_gate = not args.skip_causal_orb_filter
            sim = simulate_london_child_after_sweep(
                df1, lh, ll, sw_low, args.sl_points, sl_mode=args.sl_mode,
                require_causal_orb_pierce=orb_gate,
            )
            dir_lab = child_chart_side_label(sw_low, sim)

            if sim.filled and sim.net_dollars > 0:
                bucket, folder = 'winners', winners_dir
            elif sim.filled:
                bucket, folder = 'losers', losers_dir
            else:
                bucket, folder = 'skipped', skipped_dir

            out = folder / f'{d}_{dir_lab}_child.png'
            try:
                if draw_chart_london_child_after_sweep(
                    d, df1, r, out, args.sl_points, args.sl_mode, sw_low,
                    require_causal_orb_pierce=orb_gate,
                ):
                    written.append(
                        {
                            'date': d,
                            'dir': dir_lab,
                            'v2b_dir': r['Trade_Direction'],
                            'result': r['Result'],
                            'net_v2b': r.get('Net_$', np.nan),
                            'pl': r['Trade_PL'],
                            'file': f'{bucket}/{out.name}',
                            'LdnH_0200_0930': lh,
                            'LdnL_0200_0930': ll,
                            'model_net': sim.net_dollars,
                            'model_reason': sim.reason,
                            'model_filled': sim.filled,
                            'bucket': bucket,
                        }
                    )
                if i % 25 == 0 or i == n_plan:
                    print(f'  [{i}/{n_plan}] wrote {len(written)} charts ...', flush=True)
            except Exception as e:
                print(f'  [{i}/{n_plan}] {d} {dir_lab!s} error: {e}', flush=True)

        filled = [w for w in written if w.get('model_filled')]
        wins = [w for w in filled if w['model_net'] > 0]
        if filled:
            pct = 100.0 * len(wins) / len(filled)
            print(
                f"\nModel win rate (Net_$ > 0, filled days): {len(wins)}/{len(filled)} = {pct:.1f}%",
                flush=True,
            )
        idx = args.out / 'INDEX.md'
        with open(idx, 'w', encoding='utf-8') as f:
            f.write('# London sweep — **child-after-sweep** (tier‑1 @ London + child adds)\n\n')
            f.write(
                'After RTH sweep of LdnL/LdnH: **tier‑1** resting limit at **LdnL** (Long) / **LdnH** (Short); '
                'then **green/red** inside‑box 5m **children** for adds (tier‑2/3), max **3** MNQ. '
                '**Default:** causal ORB gate — ORB [9:30–9:45] must pierce **[02:00, 09:30)** London on '
                'the sweep side (annotator geometry); disable with `--skip-causal-orb-filter`. '
                'Tier‑1 SL = v2e wide (Ldn range width); **children** stopped at **London boundary**; '
                'TP = opposing corner. RT fee $1.50 × contracts per exit batch.\n\n'
            )
            f.write(f'**Day universe:** `{args.day_universe}` (`--start`/`--end` from annotated CSV unless set). ')
            f.write(f'**Causal ORB filter:** `{not args.skip_causal_orb_filter}`.\n\n')
            if filled:
                f.write(
                    f'**Win rate (model, filled):** {len(wins)}/{len(filled)} = '
                    f'{100.0 * len(wins) / len(filled):.1f}%\n\n'
                )
            f.write('| Date | Side | v2b | Model Net $ | Bucket | Chart |\n')
            f.write('|---|:---:|---|---:|---|:---|\n')
            for w in sorted(written, key=lambda x: (x['date'], x['dir'])):
                f.write(
                    f"| {w['date']} | {w['dir']} | {w['v2b_dir']} | {w['model_net']!s} | "
                    f"{w['bucket']} | [{w['file']}]({w['file']}) |\n"
                )
        print(f"Wrote {len(written)} PNGs under {args.out} (winners/losers/skipped)\nWrote {idx}")
        return 0 if written else 1

    # --- v2e-limit (legacy chart layout) ---
    rows_v2e: List[Tuple[date, pd.Series]] = []
    if args.day_universe == 'opp_sweep':
        for _, row in sub.iterrows():
            rows_v2e.append((row['Date'], row))
        n_v2e = len(rows_v2e)
    else:
        assert all_rth_days_ordered is not None
        rows_v2e.extend((_d, pd.Series(dtype=object)) for _d in all_rth_days_ordered)
        n_v2e = len(rows_v2e)

    for i, (d, r) in enumerate(rows_v2e, 1):
        day = gby.get(d)
        if day is None or day.empty:
            print(f'  [{i}/{n_v2e}] {d} no 1m, skip', flush=True)
            continue
        if args.day_universe == 'all_rth':
            if not session_has_rth_like_swept_orb(day):
                print(f'  [{i}/{n_v2e}] {d} no RTH [09:30,16:00) bars, skip', flush=True)
                continue
            r = synthetic_v2b_row(d, symbol_from_day_b(day))
        df1 = trim_chart_session(day)
        lh, ll = london_0200_0930_hilo(df1)
        rth = rth_1m(df1)
        if args.side_from == 'first_rth_touch':
            v2e_side = first_rth_touch_side(rth, lh, ll, args.limit_offset)
            if v2e_side is None:
                print(f'  [{i}/{n_v2e}] {d} no v2e side (no first RTH touch), skip', flush=True)
                continue
        else:
            v2e_side = r['Trade_Direction']
        out = args.out / f"{d}_{v2e_side}.png"
        try:
            if draw_chart(
                d, df1, r, out,
                sl_points=args.sl_points,
                limit_offset_ticks=args.limit_offset,
                v2e_side=v2e_side,
                case_study_tag='London sweep (annot)',
                sl_mode=args.sl_mode,
            ):
                written.append(
                    {
                        'date': d,
                        'dir': v2e_side,
                        'v2b_dir': r['Trade_Direction'],
                        'result': r['Result'],
                        'net': r.get('Net_$', np.nan),
                        'pl': r['Trade_PL'],
                        'file': out.name,
                        'LdnH_0200_0930': lh,
                        'LdnL_0200_0930': ll,
                    }
                )
                if i % 25 == 0 or i == n_v2e:
                    print(f'  [{i}/{n_v2e}] wrote {len(written)} charts ...', flush=True)
        except Exception as e:
            print(f'  [{i}/{n_v2e}] {d} {v2e_side!s} error: {e}', flush=True)

    idx = args.out / 'INDEX.md'
    with open(idx, 'w', encoding='utf-8') as f:
        f.write('# London sweep — v2e MNQ charts (annotated subset)\n\n')
        f.write('**Causal v2e:** 02:00–09:30 box H/L from 1m, limit at H (short) / L (long), SL in **index points**, ')
        f.write('2 @ Ldn mid + 3 @ opposite Ldn, 5m layout + ORB (grey) for reference. ')
        f.write('Session ~00:30–16:00 NY from the 1m Databento export.\n\n')
        f.write(
            f'**Charts generated:** {len(written)}  ·  from `{args.annotated.name}`  ·  '
            f'`--side-from {args.side_from}`  ·  **`--day-universe {args.day_universe}`**\n\n'
        )
        f.write('| Date | v2e side | v2b row | Result | Net $ | 2–9:30 H | 2–9:30 L | Chart |\n')
        f.write('|---|---:|---:|---:|---:|---:|---:|:---|\n')
        for w in sorted(written, key=lambda x: (x['date'], x['dir'])):
            f.write(
                f"| {w['date']} | {w['dir']} | {w['v2b_dir']} | {w['result']} | {w['net']!s} | "
                f"{w['LdnH_0200_0930']!s} | {w['LdnL_0200_0930']!s} | [{w['file']}]({w['file']}) |\n"
            )
    print(f"Wrote {len(written)} PNGs to {args.out}\nWrote {idx}")
    return 0 if written else 1


if __name__ == '__main__':
    raise SystemExit(main())
