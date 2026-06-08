#!/usr/bin/env python3
"""
Replay mnq_swept_orb_breakout.csv with child-based scale-in vs L0 (brk2 close).

Scale-in:
  • Lot 1: limit at L0−15 (long) / L0+15 (short). Stop: fixed L0 ∓ sl_pts (default ±70).

  • Lots 2..N (optional, default N=5): successive “child” candles AFTER lot 1 fills define
    limit prices (1st child → 2nd contract, etc.):
      – Long — green bar, entire OHLC strictly above RH.
      – Short — red bar, entire OHLC strictly below RL.
    Stop for **child-added** lots (tier 2+): **opening-range boundary ± edge** —
    Long adds: **RH − edge**, Short adds: **RL + edge** (buffer inside the prior range vs RH/RL).

  Use ``--max-contracts`` to cap total contracts (min 2, default 5).

Exit: flatten all remaining contracts at TP1 only (TP2 disabled until validated).

Usage:
  python resim_scale_in_ladder.py [--sl-pts 70] [--child-or-edge 5] [--max-contracts 5]
"""
from __future__ import annotations

import argparse
from datetime import time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import databento as db
import pandas as pd
import pytz

EPS = 1e-9
NY = pytz.timezone('America/New_York')
DBN = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
T_RTH0 = dtime(9, 30)
T_RTH1 = dtime(16, 0)
T_SIM_END = dtime(15, 55)

MULT = 2.0
FEE_RT = 1.50
STEP = 15.0
DEFAULT_SL_PTS = 70.0
DEFAULT_CHILD_OR_EDGE = 5.0  # long child stops @ RH−edge, short child stops @ RL+edge
DEFAULT_MAX_CONTRACTS = 5


def load_by_date():
    print('Loading DBN ...')
    store = db.DBNStore.from_file(DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')]
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= T_RTH0) & (df['t'] < T_RTH1)]
    df = df[df['date'] >= pd.Timestamp('2021-03-04').date()]
    df = df.set_index('ts_event').sort_index()
    return {d: g for d, g in df.groupby(df.index.date)}


def breach_brk1_classic_tp(brk1_dir: str, lvl: float, hi: float, lo: float) -> bool:
    if brk1_dir == 'Long':
        return hi >= lvl - EPS
    return lo <= lvl + EPS


def first_scale_limit_px(l0: float, direction: str) -> float:
    return (l0 - STEP) if direction == 'Long' else (l0 + STEP)


def is_child_above_or_green(bar: pd.Series, rh: float) -> bool:
    """Green candle fully above RH (opening range high)."""
    o = float(bar['open'])
    h = float(bar['high'])
    l = float(bar['low'])
    c = float(bar['close'])
    if not (c > o + EPS):
        return False
    return min(o, h, l, c) > rh + EPS


def is_child_below_or_red(bar: pd.Series, rl: float) -> bool:
    """Red candle fully below RL (opening range low)."""
    o = float(bar['open'])
    h = float(bar['high'])
    l = float(bar['low'])
    c = float(bar['close'])
    if not (c < o - EPS):
        return False
    return max(o, h, l, c) < rl - EPS


def avg_price(entries: List[float]) -> float:
    return sum(entries) / len(entries) if entries else float('nan')


def simulate_trade(
    fwd: pd.DataFrame,
    brk1: str,
    sk_lvl: float,
    l0: float,
    direction: str,
    sl_pts: float,
    tp1_px: float,
    tp2_px_unused: float,
    rh: float,
    rl: float,
    child_or_edge: float,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Tier1 @ L0±STEP with SL=L0±sl_pts (primary). Lots 2..max_contracts at successive child closes;
    SL for child-added lots at OR boundary (long RH−edge; short RL+edge).
    Flatten all contracts at TP1 only.
    tp2_px_unused kept for ABI/chart payloads only (not simulated exit).
    """
    _ = tp2_px_unused
    if max_contracts < 2:
        raise ValueError('max_contracts must be at least 2')
    long = direction == 'Long'
    sl_px_primary = (l0 - sl_pts) if long else (l0 + sl_pts)
    # Tier-2+ stops: bound risk at opposite OR edge (not RL−σ for longs — that widens risk).
    child_sl_pt = float(rh - child_or_edge) if long else float(rl + child_or_edge)
    scale0_px = first_scale_limit_px(l0, direction)

    n_child_levels = max_contracts - 1
    filled_flag = [False] * max_contracts
    pend: List[Optional[float]] = [None] * n_child_levels
    lots: List[Tuple[float, float]] = []
    child_events = 0  # assigns pend[k] at k-th qualifying child bar
    idx_first_scale: Optional[int] = None  # bars strictly after this row can count as children

    sum_pts = 0.0
    exit_count = 0
    fill_ts_first: Optional[pd.Timestamp] = None

    entries_log: List[float] = []

    last_exit_px = float(l0)

    def build_payload(ts_exit: pd.Timestamp, res_lab: str, tp2_for_disp: float) -> Dict[str, Any]:
        assert fill_ts_first is not None
        eps_used = avg_price(entries_log)
        return {
            'sum_pts': sum_pts,
            'exit_count': exit_count,
            'fill_ts_first': fill_ts_first,
            'exit_ts': ts_exit,
            'avg_entry_px': eps_used,
            'exit_px': last_exit_px,
            'sl_px': sl_px_primary,
            'tp1_px': tp1_px,
            'tp2_px': tp2_for_disp,
            'sl_child_px': child_sl_pt,
            'rh': rh,
            'rl': rl,
            'l0': l0,
            'result': res_lab,
            'filled_flags': tuple(filled_flag),
            'max_contracts': max_contracts,
        }

    def try_limit_fills(ts_bar: pd.Timestamp, lo: float, hi: float, bar_idx: int) -> None:
        nonlocal fill_ts_first, pend, idx_first_scale
        cand: List[Tuple[int, float, float]] = []

        def maybe_add(tidx: int, lim_px: float, sl_for_lot: float) -> None:
            if filled_flag[tidx]:
                return
            if long:
                if lo <= lim_px + EPS:
                    cand.append((tidx, lim_px, sl_for_lot))
            else:
                if hi >= lim_px - EPS:
                    cand.append((tidx, lim_px, sl_for_lot))

        maybe_add(0, scale0_px, sl_px_primary)
        for j in range(n_child_levels):
            px = pend[j]
            if px is not None:
                maybe_add(j + 1, px, child_sl_pt)

        if long:
            cand.sort(key=lambda x: x[1], reverse=True)
        else:
            cand.sort(key=lambda x: x[1])

        for tidx, px, slo in cand:
            if filled_flag[tidx]:
                continue
            lots.append((px, slo))
            filled_flag[tidx] = True
            entries_log.append(px)
            if fill_ts_first is None:
                fill_ts_first = ts_bar
            if tidx == 0:
                idx_first_scale = bar_idx
            if tidx >= 1:
                pend[tidx - 1] = None

    def apply_stops(lo: float, hi: float) -> None:
        nonlocal lots, sum_pts, exit_count, last_exit_px
        alive: List[Tuple[float, float]] = []
        for entry_px, slo in lots:
            if long:
                if lo <= slo + EPS:
                    sum_pts += slo - entry_px
                    exit_count += 1
                    last_exit_px = slo
                    continue
                alive.append((entry_px, slo))
            else:
                if hi >= slo - EPS:
                    sum_pts += entry_px - slo
                    exit_count += 1
                    last_exit_px = slo
                    continue
                alive.append((entry_px, slo))
        lots = alive

    def apply_tp1(lo: float, hi: float) -> bool:
        nonlocal lots, sum_pts, exit_count, last_exit_px
        if not lots:
            return False
        if long and hi >= tp1_px - EPS:
            last_exit_px = tp1_px
            n_here = len(lots)
            for entry_px, _ in lots:
                sum_pts += tp1_px - entry_px
            exit_count += n_here
            lots.clear()
            return True
        if not long and lo <= tp1_px + EPS:
            last_exit_px = tp1_px
            n_here = len(lots)
            for entry_px, _ in lots:
                sum_pts += entry_px - tp1_px
            exit_count += n_here
            lots.clear()
            return True
        return False

    for bar_idx, (ts, bar) in enumerate(fwd.iterrows()):
        lo = float(bar['low'])
        hi = float(bar['high'])
        if breach_brk1_classic_tp(brk1, sk_lvl, hi, lo):
            return ('skipped_brk1', None)

        try_limit_fills(ts, lo, hi, bar_idx)
        apply_stops(lo, hi)

        if apply_tp1(lo, hi):
            lab = 'Win' if sum_pts > EPS else 'Loss'
            return ('ok', build_payload(ts, lab, tp2_px_unused))

        if filled_flag[0] and not lots:
            lab = 'Win' if sum_pts > EPS else 'Loss'
            return ('ok', build_payload(ts, lab, tp2_px_unused))

        if (
            filled_flag[0]
            and idx_first_scale is not None
            and bar_idx > idx_first_scale
            and child_events < n_child_levels
        ):
            qualifies = False
            if long and is_child_above_or_green(bar, rh):
                qualifies = True
            elif not long and is_child_below_or_red(bar, rl):
                qualifies = True
            if qualifies:
                pend[child_events] = float(bar['close'])
                child_events += 1

    if any(filled_flag) and lots:
        last_px = float(fwd.iloc[-1]['close'])
        last_ts = fwd.index[-1]
        if long:
            for ep, _ in lots:
                sum_pts += last_px - ep
                exit_count += 1
        else:
            for ep, _ in lots:
                sum_pts += ep - last_px
                exit_count += 1
        last_exit_px = last_px
        lab = 'EOD-Win' if sum_pts > EPS else 'EOD-Loss'
        assert fill_ts_first is not None
        return ('ok', build_payload(last_ts, lab, tp2_px_unused))

    return ('ladder_no_fill', None)


def replay_row(
    row: pd.Series,
    day_df: pd.DataFrame,
    sl_pts: float,
    child_or_edge: float = DEFAULT_CHILD_OR_EDGE,
    *,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
) -> dict:
    l0 = float(row['Entry_Price'])
    direction = str(row['Trade_Direction'])
    brk1 = str(row['brk1_dir'])
    rh, rl, rv = float(row['RH']), float(row['RL']), float(row['Range'])
    sk = (
        float(row['Skip_Level_or_ref'])
        if pd.notna(row.get('Skip_Level_or_ref'))
        else (rh + rv if brk1 == 'Long' else rl - rv)
    )

    sweep = pd.to_datetime(row['Sweep'])
    if sweep.tzinfo is None:
        sweep = sweep.tz_localize(NY)
    else:
        sweep = sweep.tz_convert(NY)

    t_work = sweep + pd.Timedelta(minutes=5)
    fwd_all = day_df[day_df.index >= t_work]
    fwd_all = fwd_all[fwd_all.index.map(lambda t: t.time() < T_SIM_END)]

    if fwd_all.empty:
        return {'status': 'no_time', 'sum_pts': None, 'exits': 0}

    if direction == 'Long':
        tp1_px, tp2_px = l0 + rv, l0 + 2.0 * rv
    else:
        tp1_px, tp2_px = l0 - rv, l0 - 2.0 * rv

    st, out = simulate_trade(
        fwd_all,
        brk1,
        sk,
        l0,
        direction,
        sl_pts,
        tp1_px,
        tp2_px,
        rh,
        rl,
        child_or_edge,
        max_contracts,
    )
    if st == 'skipped_brk1':
        return {'status': 'skipped_brk1_tp', 'sum_pts': None, 'exits': 0}
    if st != 'ok' or out is None:
        return {'status': 'no_fill_ladder', 'sum_pts': None, 'exits': 0}

    sum_pts = float(out['sum_pts'])
    exits = int(out['exit_count'])
    gross = round(sum_pts * MULT, 2)
    net = round(gross - FEE_RT * exits, 2)
    out['Net_$'] = net
    out['Trade_PL_pts'] = sum_pts
    return {'status': 'ok', **out}


def main() -> int:
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    ap.add_argument('--csv', type=str, default=str(root / 'mnq_swept_orb_breakout.csv'))
    ap.add_argument('--sl-pts', type=float, default=DEFAULT_SL_PTS)
    ap.add_argument(
        '--child-or-edge',
        type=float,
        default=DEFAULT_CHILD_OR_EDGE,
        help='Buffer inside OR: long child stops @ RH−edge, short child stops @ RL+edge',
    )
    ap.add_argument(
        '--max-contracts',
        type=int,
        default=DEFAULT_MAX_CONTRACTS,
        help='Max contracts (tier1 @ L0±15 plus up to N−1 child-based adds)',
    )
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        raise SystemExit(f'Missing CSV: {csv_path}')

    csv = pd.read_csv(csv_path)
    filled = csv[csv['Entry_Price'].notna()].copy()
    by_d = load_by_date()

    nets = []
    statuses = []
    for _, row in filled.iterrows():
        d = pd.to_datetime(row['Date']).date()
        if d not in by_d:
            statuses.append('no_day')
            nets.append(0.0)
            continue
        dd = by_d[d]
        if 'symbol' in dd.columns:
            dd = dd[dd['symbol'] == row['Symbol']]
        if dd.empty:
            statuses.append('no_sym')
            nets.append(0.0)
            continue
        r = replay_row(row, dd, args.sl_pts, args.child_or_edge, max_contracts=args.max_contracts)
        statuses.append(r['status'])
        nets.append(float(r.get('Net_$', r.get('net', 0.0)) or 0.0))

    orig_net = filled['Net_$'].astype(float)

    print(
        f'Child scale-in · max {args.max_contracts} contracts · 1st L0±{STEP:.0f} · '
        f'SL tier1 L0±{args.sl_pts:.0f} · child long RH−{args.child_or_edge:.0f} short RL+{args.child_or_edge:.0f} · TP1 only ·'
    )
    print()
    print(f'Baseline CSV: Σ Net ${orig_net.sum():,.2f}')
    ok = statuses.count('ok')
    print(f'Ladder ok: Σ Net ${sum(nets):,.2f}  (n_ok={ok})')
    print(f'Status: { {(x, statuses.count(x)) for x in sorted(set(statuses))} }')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
