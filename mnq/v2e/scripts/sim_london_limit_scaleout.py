#!/usr/bin/env python3
"""
Causal v2e sim (2× MNQ) — no lookahead on London levels

London **high / low** are taken from the **1m** session box **02:00–09:30 ET
only** (inclusive 02:00, exclusive 9:30). At 9:30 those levels are knowable
without using 9:30–11:00 data.

  - **Short:** limit sell at the box **high**; **Long:** limit buy at the box **low**.
  - **First** RTH touch [9:30, 16:00) fills the limit.
  - **Stop width (default):** **London range** = **LdnH − LdnL** index points; short
    stops at LdnH + range; long at LdnL − range. **Fixed:** use ``--sl-mode fixed
    --sl-points N``.
  - **Scale (2 lot):** **1** at **(LdnH + LdnL) / 2** (mid), **1** at the opposite
    London corner (Short → LdnL, Long → LdnH). Not ORB-based.
  - **EOD 16:00** last 1m close on any remainder.
  - **MFE** — favorable extension in RTH after the last scale at opposite Ldn.
  - **Flags** — pre-open H/L on the last 1m before 9:30 (e.g. 9:29 bar).

See README for limitations (no partial fills, 1m bar path, etc.).
"""
import argparse
import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Literal, Optional, Tuple

SlMode = Literal['london_range', 'fixed']

import numpy as np
import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
POTIONS = V2E_ROOT.parent.parent
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

TICK = 0.25
DOLLARS_PER_POINT = 2.0  # MNQ
RTH_O = time(9, 30)
RTH_C = time(16, 0)
# Causal pre-RTH / pre-open box (all bars with 2:00 <= t < 9:30)
LDN_PREOPEN_LO = time(2, 0)
LDN_PREOPEN_HI = time(9, 30)
TP1_LOTS = 1
TP2_LOTS = 1
N_CONTRACTS = 2


def resolve_sl_distance(
    ldn_h: float, ldn_l: float, sl_mode: SlMode, sl_points: float
) -> Tuple[float, str]:
    """
    Stop distance in index points: either London range (H−L) or fixed.
    Returns (distance, 'ok' | 'no_level').
    """
    if sl_mode == 'london_range':
        d = float(ldn_h) - float(ldn_l)
        if d <= 1e-9:
            return 0.0, 'no_level'
        return d, 'ok'
    s = float(sl_points)
    if s <= 1e-9:
        return 0.0, 'no_level'
    return s, 'ok'

ANNOTATED = POTIONS / 'mnq' / 'mnq_orb_results_stops_annotated.csv'
M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'


@dataclass
class SimResult:
    pnl_dollars: float
    filled: bool
    reason: str
    n_stop: int
    n_tp1: int
    n_tp2: int
    n_eod: int
    mfe_past_opposite_london_pts: float
    london_h: float
    london_l: float
    ldn_mid: float
    extreme_h_on_last_preopen_1m: bool
    extreme_l_on_last_preopen_1m: bool
    entry_rth_idx: int  # index within RTH 1m of first limit fill; -1 if no fill

def dollars_short(entry: float, exit_px: float, n: int) -> float:
    return n * (entry - exit_px) * DOLLARS_PER_POINT


def dollars_long(entry: float, exit_px: float, n: int) -> float:
    return n * (exit_px - entry) * DOLLARS_PER_POINT


def london_0200_0930_hilo(day_1m: pd.DataFrame) -> Tuple[float, float]:
    """Max high and min low on [02:00, 09:30) ET. NaN if empty."""
    b = day_1m[
        day_1m.index.map(lambda t: LDN_PREOPEN_LO <= t.time() < LDN_PREOPEN_HI)
    ]
    if b.empty:
        return float('nan'), float('nan')
    return float(b['high'].max()), float(b['low'].min())


def preopen_extreme_on_last_1m_flags(day_1m: pd.DataFrame) -> Tuple[bool, bool]:
    """True if LdnH (resp. LdnL) is established on the last 1m before 9:30."""
    b = day_1m[
        day_1m.index.map(lambda t: LDN_PREOPEN_LO <= t.time() < LDN_PREOPEN_HI)
    ]
    if b.empty:
        return False, False
    last_ts = b.index.max()
    l_h, l_l = float(b['high'].max()), float(b['low'].min())
    h_bar = b[b['high'] >= l_h - 1e-9]
    l_bar = b[b['low'] <= l_l + 1e-9]
    h_on = not h_bar.empty and h_bar.index.max() == last_ts
    l_on = not l_bar.empty and l_bar.index.max() == last_ts
    return h_on, l_on


def first_fill_idx_short(df: pd.DataFrame, entry: float) -> Optional[int]:
    for i, (ts, b) in enumerate(df.iterrows()):
        if b['high'] + 1e-9 >= entry:
            return i
    return None


def first_fill_idx_long(df: pd.DataFrame, entry: float) -> Optional[int]:
    for i, (ts, b) in enumerate(df.iterrows()):
        if b['low'] - 1e-9 <= entry:
            return i
    return None


def rth_1m(day_b: pd.DataFrame) -> pd.DataFrame:
    return day_b[(day_b.index.map(lambda t: RTH_O <= t.time() < RTH_C))].copy()


def first_rth_touch_side(
    rth: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    limit_offset_ticks: int = 0,
) -> Optional[str]:
    """
    Live-style side: **whichever** London limit is **first** touched in RTH **after 9:30** on 1m:

    * **Short** — limit sell at LdnH (optionally 1 tick below: `ldn_h - offset*tick`)
    * **Long** — limit buy at LdnL (optionally 1 tick above: `ldn_l + offset*tick`)

    Touch: short if `high >=` entry, long if `low <=` entry. First chronological 1m bar
    that triggers either; if both in the same bar, tie-break by which entry is **closer
    in price** to the bar **open** (proxy for path); exact tie → Short.

    Returns ``None`` if neither side is touched by end of RTH.
    """
    if rth is None or rth.empty or np.isnan(ldn_h) or np.isnan(ldn_l):
        return None
    sh_e = float(ldn_h) - float(limit_offset_ticks) * float(TICK)
    lg_e = float(ldn_l) + float(limit_offset_ticks) * float(TICK)
    for k in range(len(rth)):
        b = rth.iloc[k]
        h, lo, o = float(b['high']), float(b['low']), float(b['open'])
        th = h + 1e-9 >= sh_e
        tl = lo - 1e-9 <= lg_e
        if not th and not tl:
            continue
        if th and not tl:
            return 'Short'
        if tl and not th:
            return 'Long'
        d_h = abs(o - sh_e)
        d_l = abs(o - lg_e)
        if d_h < d_l - 1e-12:
            return 'Short'
        if d_l < d_h - 1e-12:
            return 'Long'
        return 'Short'
    return None


def simulate_short(
    rth: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sl_points: float = 30.0,
    limit_offset_ticks: int = 0,
    day_1m: Optional[pd.DataFrame] = None,
    sl_mode: SlMode = 'london_range',
) -> SimResult:
    if (
        pd.isna(ldn_h)
        or pd.isna(ldn_l)
        or rth.empty
        or (isinstance(ldn_h, float) and np.isnan(ldn_h))
    ):
        return SimResult(0, False, 'no_level', 0, 0, 0, 0, np.nan, np.nan, np.nan, np.nan, False, False, -1)
    ldn_h, ldn_l = float(ldn_h), float(ldn_l)
    sl_dist, rsn = resolve_sl_distance(ldn_h, ldn_l, sl_mode, float(sl_points))
    if rsn == 'no_level':
        return SimResult(0, False, 'no_level', 0, 0, 0, 0, np.nan, np.nan, np.nan, np.nan, False, False, -1)
    mid = (ldn_h + ldn_l) / 2.0
    tp1, tp2 = mid, ldn_l
    sl = ldn_h + sl_dist
    entry = ldn_h - limit_offset_ticks * TICK
    j = first_fill_idx_short(rth, entry)
    if j is None:
        exh, exl = (False, False)
        if day_1m is not None and not day_1m.empty:
            exh, exl = preopen_extreme_on_last_1m_flags(day_1m)
        return SimResult(
            0, False, 'no_fill', 0, 0, 0, 0, np.nan, ldn_h, ldn_l, mid, exh, exl, -1
        )
    rem = N_CONTRACTS
    pnl = 0.0
    n1, n2, nst, neod = 0, 0, 0, 0
    tp2_done_k: Optional[int] = None
    n1_cap, n2_cap = TP1_LOTS, TP2_LOTS
    for k in range(j, len(rth)):
        h, lo = float(rth.iloc[k]['high']), float(rth.iloc[k]['low'])
        if rem > 0 and h >= sl - 1e-9:
            pnl += dollars_short(entry, sl, rem)
            nst = rem
            rem = 0
            break
        if rem <= 0:
            break
        if n1 < n1_cap and rem > 0 and lo <= tp1 + 1e-9:
            c1 = min(n1_cap - n1, rem)
            pnl += dollars_short(entry, tp1, c1)
            n1 += c1
            rem -= c1
        if n2 < n2_cap and rem > 0 and lo <= tp2 + 1e-9:
            c2 = min(n2_cap - n2, rem)
            pnl += dollars_short(entry, tp2, c2)
            n2 += c2
            rem -= c2
            if n2 >= TP2_LOTS:
                tp2_done_k = k
    if rem > 0 and not rth.empty:
        last = float(rth.iloc[-1]['close'])
        pnl += dollars_short(entry, last, rem)
        neod = rem
    mfe = np.nan
    if (
        tp2_done_k is not None
        and n2 >= TP2_LOTS
        and nst == 0
    ):
        tail = rth.iloc[tp2_done_k + 1 :]
        if not tail.empty:
            mlow = float(tail['low'].min())
            mfe = max(0.0, ldn_l - mlow)
    exh, exl = (False, False)
    if day_1m is not None and not day_1m.empty:
        exh, exl = preopen_extreme_on_last_1m_flags(day_1m)
    return SimResult(
        pnl, True, 'ok', nst, n1, n2, neod, mfe, ldn_h, ldn_l, mid, exh, exl, j
    )


def simulate_long(
    rth: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sl_points: float = 30.0,
    limit_offset_ticks: int = 0,
    day_1m: Optional[pd.DataFrame] = None,
    sl_mode: SlMode = 'london_range',
) -> SimResult:
    if (
        pd.isna(ldn_h)
        or pd.isna(ldn_l)
        or rth.empty
        or (isinstance(ldn_h, float) and np.isnan(ldn_h))
        or (isinstance(ldn_l, float) and np.isnan(ldn_l))
    ):
        return SimResult(0, False, 'no_level', 0, 0, 0, 0, np.nan, np.nan, np.nan, np.nan, False, False, -1)
    ldn_h, ldn_l = float(ldn_h), float(ldn_l)
    sl_dist, rsn = resolve_sl_distance(ldn_h, ldn_l, sl_mode, float(sl_points))
    if rsn == 'no_level':
        return SimResult(0, False, 'no_level', 0, 0, 0, 0, np.nan, np.nan, np.nan, np.nan, False, False, -1)
    mid = (ldn_h + ldn_l) / 2.0
    tp1, tp2 = mid, ldn_h
    sl = ldn_l - sl_dist
    entry = ldn_l + limit_offset_ticks * TICK
    j = first_fill_idx_long(rth, entry)
    if j is None:
        exh, exl = (False, False)
        if day_1m is not None and not day_1m.empty:
            exh, exl = preopen_extreme_on_last_1m_flags(day_1m)
        return SimResult(
            0, False, 'no_fill', 0, 0, 0, 0, np.nan, ldn_h, ldn_l, mid, exh, exl, -1
        )
    rem = N_CONTRACTS
    pnl = 0.0
    n1, n2, nst, neod = 0, 0, 0, 0
    tp2_done_k: Optional[int] = None
    n1_cap, n2_cap = TP1_LOTS, TP2_LOTS
    for k in range(j, len(rth)):
        h, lo = float(rth.iloc[k]['high']), float(rth.iloc[k]['low'])
        if rem > 0 and lo <= sl + 1e-9:
            pnl += dollars_long(entry, sl, rem)
            nst = rem
            rem = 0
            break
        if rem <= 0:
            break
        if n1 < n1_cap and rem > 0 and h >= tp1 - 1e-9:
            c1 = min(n1_cap - n1, rem)
            pnl += dollars_long(entry, tp1, c1)
            n1 += c1
            rem -= c1
        if n2 < n2_cap and rem > 0 and h >= tp2 - 1e-9:
            c2 = min(n2_cap - n2, rem)
            pnl += dollars_long(entry, tp2, c2)
            n2 += c2
            rem -= c2
            if n2 >= TP2_LOTS:
                tp2_done_k = k
    if rem > 0 and not rth.empty:
        last = float(rth.iloc[-1]['close'])
        pnl += dollars_long(entry, last, rem)
        neod = rem
    mfe = np.nan
    if tp2_done_k is not None and n2 >= TP2_LOTS and nst == 0:
        tail = rth.iloc[tp2_done_k + 1 :]
        if not tail.empty:
            mh = float(tail['high'].max())
            mfe = max(0.0, mh - ldn_h)
    exh, exl = (False, False)
    if day_1m is not None and not day_1m.empty:
        exh, exl = preopen_extreme_on_last_1m_flags(day_1m)
    return SimResult(
        pnl, True, 'ok', nst, n1, n2, neod, mfe, ldn_h, ldn_l, mid, exh, exl, j
    )


# Chart path: mirrors simulate and records timestamps
@dataclass
class V2EChartPath:
    filled: bool
    reason: str
    pnl_dollars: float
    entry_ts: Optional[pd.Timestamp]
    entry_px: float
    sl: float
    tp1: float
    tp2: float
    ldn_mid: float
    exit_ts: Optional[pd.Timestamp]
    exit_px: float
    mfe_past_opposite_london_pts: float
    n_stop: int
    n_tp1: int
    n_tp2: int
    n_eod: int
    result_label: str
    tp1_done_ts: Optional[pd.Timestamp] = None
    tp2_done_ts: Optional[pd.Timestamp] = None


def _label_v2e_result(pnl: float, nst: int, neod: int) -> str:
    if nst > 0:
        return 'Loss' if pnl < 0 else 'Stop-BE'
    if neod > 0:
        return 'EOD-Win' if pnl > 0 else 'EOD-Loss'
    return 'Win' if pnl > 0 else 'Loss'


def v2e_chart_path_short(
    rth: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sl_points: float = 30.0,
    limit_offset_ticks: int = 0,
    sl_mode: SlMode = 'london_range',
) -> V2EChartPath:
    s = simulate_short(
        rth, ldn_h, ldn_l, sl_points, limit_offset_ticks, sl_mode=sl_mode,
    )
    if s.reason == 'no_level':
        return V2EChartPath(
            False, 'no_level', 0.0, None, float('nan'), float('nan'), float('nan'),
            float('nan'), float('nan'), float('nan'), None, float('nan'), np.nan, 0, 0, 0, 0, 'no_level',
        )
    entry = ldn_h - limit_offset_ticks * TICK
    d_sl, _ = resolve_sl_distance(float(ldn_h), float(ldn_l), sl_mode, float(sl_points))
    slv = ldn_h + d_sl
    mid = (ldn_h + ldn_l) / 2.0
    if s.reason == 'no_fill':
        return V2EChartPath(
            False, 'no_fill', 0.0, None, float(entry), slv, mid, ldn_l, mid, None, float('nan'),
            np.nan, 0, 0, 0, 0, 'no_fill',
        )
    j = first_fill_idx_short(rth, entry)
    assert j is not None
    entry_ts = rth.index[j]
    last_ts, last_px = entry_ts, float(entry)
    rem = N_CONTRACTS
    pnl = 0.0
    n1, n2, nst, neod = 0, 0, 0, 0
    tp1, tp2 = mid, ldn_l
    n1_cap, n2_cap = TP1_LOTS, TP2_LOTS
    tp2_done_k = None
    tp1_done_ts, tp2_done_ts = None, None
    for k in range(j, len(rth)):
        h, lo = float(rth.iloc[k]['high']), float(rth.iloc[k]['low'])
        ts = rth.index[k]
        if rem > 0 and h >= slv - 1e-9:
            pnl += dollars_short(entry, slv, rem)
            nst = rem
            rem = 0
            last_ts, last_px = ts, slv
            break
        if rem <= 0:
            break
        if n1 < n1_cap and rem > 0 and lo <= tp1 + 1e-9:
            c1 = min(n1_cap - n1, rem)
            pnl += dollars_short(entry, tp1, c1)
            n1 += c1
            rem -= c1
            if n1 >= n1_cap and tp1_done_ts is None:
                tp1_done_ts = ts
            last_ts, last_px = ts, tp1
        if n2 < n2_cap and rem > 0 and lo <= tp2 + 1e-9:
            c2 = min(n2_cap - n2, rem)
            pnl += dollars_short(entry, tp2, c2)
            n2 += c2
            rem -= c2
            if n2 >= TP2_LOTS:
                tp2_done_k = k
                if tp2_done_ts is None:
                    tp2_done_ts = ts
            last_ts, last_px = ts, tp2
    mfe = np.nan
    if tp2_done_k is not None and n2 >= TP2_LOTS and nst == 0:
        tail = rth.iloc[tp2_done_k + 1 :]
        if not tail.empty:
            mfe = max(0.0, ldn_l - float(tail['low'].min()))
    if rem > 0 and not rth.empty:
        last = float(rth.iloc[-1]['close'])
        pnl += dollars_short(entry, last, rem)
        neod = rem
        last_ts, last_px = rth.index[-1], last
    lab = _label_v2e_result(pnl, nst, neod)
    return V2EChartPath(
        True, 'ok', pnl, entry_ts, float(entry), slv, tp1, tp2, mid, last_ts, float(last_px),
        mfe, nst, n1, n2, neod, lab, tp1_done_ts, tp2_done_ts,
    )


def v2e_chart_path_long(
    rth: pd.DataFrame,
    ldn_h: float,
    ldn_l: float,
    sl_points: float = 30.0,
    limit_offset_ticks: int = 0,
    sl_mode: SlMode = 'london_range',
) -> V2EChartPath:
    s = simulate_long(
        rth, ldn_h, ldn_l, sl_points, limit_offset_ticks, sl_mode=sl_mode,
    )
    if s.reason == 'no_level':
        return V2EChartPath(
            False, 'no_level', 0.0, None, float('nan'), float('nan'), float('nan'),
            float('nan'), float('nan'), float('nan'), None, float('nan'), np.nan, 0, 0, 0, 0, 'no_level',
        )
    entry = ldn_l + limit_offset_ticks * TICK
    d_sl, _ = resolve_sl_distance(float(ldn_h), float(ldn_l), sl_mode, float(sl_points))
    slv = ldn_l - d_sl
    mid = (ldn_h + ldn_l) / 2.0
    if s.reason == 'no_fill':
        return V2EChartPath(
            False, 'no_fill', 0.0, None, float(entry), slv, mid, ldn_h, mid, None, float('nan'),
            np.nan, 0, 0, 0, 0, 'no_fill',
        )
    j = first_fill_idx_long(rth, entry)
    assert j is not None
    entry_ts = rth.index[j]
    last_ts, last_px = entry_ts, float(entry)
    rem = N_CONTRACTS
    pnl = 0.0
    n1, n2, nst, neod = 0, 0, 0, 0
    tp1, tp2 = mid, ldn_h
    n1_cap, n2_cap = TP1_LOTS, TP2_LOTS
    tp2_done_k = None
    tp1_done_ts, tp2_done_ts = None, None
    for k in range(j, len(rth)):
        h, lo = float(rth.iloc[k]['high']), float(rth.iloc[k]['low'])
        ts = rth.index[k]
        if rem > 0 and lo <= slv + 1e-9:
            pnl += dollars_long(entry, slv, rem)
            nst = rem
            rem = 0
            last_ts, last_px = ts, slv
            break
        if rem <= 0:
            break
        if n1 < n1_cap and rem > 0 and h >= tp1 - 1e-9:
            c1 = min(n1_cap - n1, rem)
            pnl += dollars_long(entry, tp1, c1)
            n1 += c1
            rem -= c1
            if n1 >= n1_cap and tp1_done_ts is None:
                tp1_done_ts = ts
            last_ts, last_px = ts, tp1
        if n2 < n2_cap and rem > 0 and h >= tp2 - 1e-9:
            c2 = min(n2_cap - n2, rem)
            pnl += dollars_long(entry, tp2, c2)
            n2 += c2
            rem -= c2
            if n2 >= TP2_LOTS:
                tp2_done_k = k
                if tp2_done_ts is None:
                    tp2_done_ts = ts
            last_ts, last_px = ts, tp2
    mfe = np.nan
    if tp2_done_k is not None and n2 >= TP2_LOTS and nst == 0:
        tail = rth.iloc[tp2_done_k + 1 :]
        if not tail.empty:
            mfe = max(0.0, float(tail['high'].max()) - ldn_h)
    if rem > 0 and not rth.empty:
        last = float(rth.iloc[-1]['close'])
        pnl += dollars_long(entry, last, rem)
        neod = rem
        last_ts, last_px = rth.index[-1], last
    lab = _label_v2e_result(pnl, nst, neod)
    return V2EChartPath(
        True, 'ok', pnl, entry_ts, float(entry), slv, tp1, tp2, mid, last_ts, float(last_px),
        mfe, nst, n1, n2, neod, lab, tp1_done_ts, tp2_done_ts,
    )


def run_sweep_subset(
    sl_points: float, annotated: Path, sl_mode: SlMode = 'london_range',
) -> None:
    df = pd.read_csv(annotated)
    sel = (df['Opp_sweep_London_H'] == 1) | (df['Opp_sweep_London_L'] == 1)
    sub = df[sel].copy()
    sub['Date'] = pd.to_datetime(sub['Date']).dt.date
    need = set(sub['Date'].unique())
    tmin, tmax = min(need), max(need)
    raw = ann.load_1m_for_dates(str(M1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    v2b_net = sub['Net_$'].sum()
    v2b_scaled = v2b_net * N_CONTRACTS
    sim_total = 0.0
    total_stopped = 0
    for _, r in sub.iterrows():
        d, dr = r['Date'], r['Trade_Direction']
        day = gby.get(d)
        if day is None:
            continue
        rth = rth_1m(day)
        ldn_h, ldn_l = london_0200_0930_hilo(day)
        if dr == 'Short':
            s = simulate_short(
                rth, ldn_h, ldn_l, sl_points, day_1m=day, sl_mode=sl_mode,
            )
        else:
            s = simulate_long(
                rth, ldn_h, ldn_l, sl_points, day_1m=day, sl_mode=sl_mode,
            )
        sim_total += s.pnl_dollars
        if s.n_stop >= N_CONTRACTS:
            total_stopped += 1

    n = len(sub)
    print('--- London sweep subset (causal 02:00–09:30 Ldn) ---')
    print(f'  Rows: {n}')
    print(
        f'  v2b cumulative Net_$ (1 lot, from CSV):  {v2b_net:,.2f}  |  x{N_CONTRACTS} = {v2b_scaled:,.2f}'
    )
    sl_desc = f'Ldn range (H−L) idx pt' if sl_mode == 'london_range' else f'{sl_points} idx pt (fixed)'
    print(
        f'  Sim: {N_CONTRACTS} MNQ, limit@02:00–09:30 H/L, SL={sl_desc}, '
        f'1@mid+1@opposite Ldn  |  sl_mode={sl_mode}'
    )
    print(f'  Sim cumulative P/L ($):  {sim_total:,.2f}')
    print(f'  sim / (v2b x{N_CONTRACTS}):  {sim_total / v2b_scaled if v2b_scaled else 0:,.3f}×')
    print(f'  Trades with full {N_CONTRACTS}-contract stop-out:  {total_stopped}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--sl-mode', choices=['london_range', 'fixed'], default='london_range',
        help='Stop distance: LdnH−LdnL (default) or fixed --sl-points',
    )
    ap.add_argument(
        '--sl-points', type=float, default=30.0,
        help='Stop width in index points when --sl-mode fixed; ignored for london_range',
    )
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    ap.add_argument(
        '--sweep', action='store_true',
        help='Run fixed SL grid 10, 20, 30 (implies --sl-mode fixed)',
    )
    args = ap.parse_args()
    if args.sweep:
        pts, mode = [10.0, 20.0, 30.0], 'fixed'
    else:
        pts, mode = [args.sl_points], args.sl_mode
    for i, p in enumerate(pts):
        if i:
            print()
        run_sweep_subset(p, args.annotated, sl_mode=mode)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
