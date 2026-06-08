#!/usr/bin/env python3
"""
Causal **v2d-only scaleout (×2)** — ORB fade on products where MA50 ≤ MA150 (prior day).

Mirrors ``benchmark_v2b_scaleout_multiproduct.py`` but:
  - Regime gate: **not** v2b (prior-day MA50 ≤ MA150, same shift/fillna as adaptive stitch).
  - v2d fade fills: Long after low ≤ RL−tick then buy RL+tick; Short after high ≥ RH+tick then sell RH−tick.
  - Same scaleout: 2 contracts, TP1 at opposite OR edge, runner BE, TP2 extended fade target.

Example::

  python3 benchmark_v2d_scaleout_multiproduct.py
  python3 benchmark_v2d_scaleout_multiproduct.py --only ym mym mnq
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import numpy as np
import pandas as pd

from benchmark_v2b_scaleout_multiproduct import (  # noqa: E402
    HISTORY_START,
    PRODUCTS,
    ProductResult,
    ProductSpec,
    causal_regime_from_daily,
    causal_regime_from_gby,
    load_1m,
    orb_range,
)
from mtm_v2b_scaleout import (  # noqa: E402
    LegMtm,
    closed_dd,
    portfolio_mtm_dd_simple,
    simulate_scale_out_leg_mtm,
)
from run_adaptive_50_150_scaleout import (  # noqa: E402
    ORB_HI,
    _EPS,
    path_after_prior,
    rth_slice,
)


def regime_v2d(spec: ProductSpec, gby: dict[date, pd.DataFrame]) -> pd.Series:
    if spec.daily_dbn is not None and spec.daily_dbn.is_file():
        v2b = causal_regime_from_daily(spec.daily_dbn, spec.prefix)
    else:
        v2b = causal_regime_from_gby(gby)
    return ~v2b.astype(bool)


def trade_params_v2d(direction: str, rh: float, rl: float, rv: float, tick: float) -> dict | None:
    if rv <= _EPS:
        return None
    if direction == 'Long':
        return {
            'long_side': True,
            'entry': rl + tick,
            'init_sl': rl - rv,
            'tp1': rh,
            'tp2': rh + rv,
            'runner_sl': rl + tick,
        }
    return {
        'long_side': False,
        'entry': rh - tick,
        'init_sl': rh + rv,
        'tp1': rl,
        'tp2': rl - rv,
        'runner_sl': rh - tick,
    }


def find_fill_v2d_long(sub: pd.DataFrame, rl: float, tick: float) -> tuple[pd.Timestamp | None, float | None]:
    br = rl - tick
    fd = rl + tick
    phase = 0
    for ts, bar in sub.iterrows():
        if phase == 0:
            if float(bar['low']) <= br + _EPS:
                phase = 1
                if float(bar['high']) >= fd - _EPS:
                    return pd.Timestamp(ts), float(fd)
            continue
        if float(bar['high']) >= fd - _EPS:
            return pd.Timestamp(ts), float(fd)
    return None, None


def find_fill_v2d_short(sub: pd.DataFrame, rh: float, tick: float) -> tuple[pd.Timestamp | None, float | None]:
    br = rh + tick
    fd = rh - tick
    phase = 0
    for ts, bar in sub.iterrows():
        if phase == 0:
            if float(bar['high']) >= br - _EPS:
                phase = 1
                if float(bar['low']) <= fd + _EPS:
                    return pd.Timestamp(ts), float(fd)
            continue
        if float(bar['low']) <= fd + _EPS:
            return pd.Timestamp(ts), float(fd)
    return None, None


def v2d_scaleout_session(
    session_day: date,
    day_raw: pd.DataFrame,
    *,
    tick: float,
    mult: float,
    fee_rt: float,
) -> tuple[list[LegMtm], list[list[tuple[pd.Timestamp, float]]], list[float]]:
    rth = rth_slice(day_raw, session_day)
    if rth.empty:
        return [], [], []
    orb = orb_range(rth, session_day)
    if orb is None:
        return [], [], []
    rh, rl, rv = orb

    legs: list[LegMtm] = []
    curves: list[list[tuple[pd.Timestamp, float]]] = []
    nets: list[float] = []
    prior_exit: pd.Timestamp | None = None

    for direction in ('Long', 'Short'):
        if len(legs) >= 2:
            break
        pm = trade_params_v2d(direction, rh, rl, rv, tick)
        if pm is None:
            continue
        sub = path_after_prior(rth, session_day, prior_exit)
        if sub.empty:
            continue
        if direction == 'Long':
            fts, _ = find_fill_v2d_long(sub, rl, tick)
        else:
            fts, _ = find_fill_v2d_short(sub, rh, tick)
        if fts is None:
            continue

        net, exit_ts, samples = simulate_scale_out_leg_mtm(
            rth,
            session_day,
            fts,
            entry=float(pm['entry']),
            long_side=bool(pm['long_side']),
            init_sl=float(pm['init_sl']),
            tp1=float(pm['tp1']),
            tp2=float(pm['tp2']),
            runner_sl=float(pm['runner_sl']),
            mult=mult,
            fee_rt=fee_rt,
        )
        legs.append(LegMtm(session_day, direction, fts, exit_ts, net))
        curves.append(samples)
        nets.append(net)
        if exit_ts is not None:
            prior_exit = exit_ts

    return legs, curves, nets


def run_product(spec: ProductSpec) -> ProductResult | None:
    try:
        gby = load_1m(spec)
    except Exception as exc:
        print(f'** {spec.code} SKIP:** {exc}', flush=True)
        return None

    regime = regime_v2d(spec, gby)
    n_v2d_days = int(regime[regime.index >= HISTORY_START].sum()) if len(regime) else 0
    print(f'  v2d regime days (≥{HISTORY_START}): {n_v2d_days}', flush=True)

    all_legs: list[LegMtm] = []
    all_curves: list[list[tuple[pd.Timestamp, float]]] = []
    all_nets: list[float] = []
    n_days = 0

    for session_day in sorted(gby.keys()):
        if session_day < HISTORY_START:
            continue
        if session_day not in regime.index or not bool(regime.loc[session_day]):
            continue
        raw = gby[session_day]
        if raw is None or raw.empty:
            continue
        legs, curves, nets = v2d_scaleout_session(
            session_day,
            raw,
            tick=spec.tick,
            mult=spec.mult,
            fee_rt=spec.fee_rt,
        )
        if not legs:
            continue
        n_days += 1
        all_legs.extend(legs)
        all_curves.extend(curves)
        all_nets.extend(nets)

    pnl = np.array(all_nets, dtype=float)
    mtm_dd, _, net = portfolio_mtm_dd_simple(all_legs, all_curves)
    cdd = closed_dd(pnl)
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl <= 0].sum())
    pf = wins / losses if losses > 1e-9 else float('inf')

    return ProductResult(
        code=spec.code,
        n_days=n_days,
        n_legs=len(all_legs),
        net=net,
        closed_dd=cdd,
        mtm_dd=mtm_dd,
        net_mtm=net / mtm_dd if mtm_dd > 1e-9 else float('nan'),
        win_pct=100.0 * (pnl > 0).mean() if len(pnl) else float('nan'),
        pf=pf,
        note=spec.note,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--only', nargs='+', default=['ym', 'mym', 'mnq'], help='Product keys')
    args = ap.parse_args()

    print(
        '\n## v2d-only scaleout (×2) — causal 1m rerun, MA50≤MA150 gate\n'
        f'_History from {HISTORY_START}; fade ORB; fee $1.50 RT/contract_\n',
        flush=True,
    )
    print(
        '| Product | Days | Legs | Net | Closed DD | **MTM DD** | Net/MTM | Win% | PF | Note |',
        flush=True,
    )
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---|', flush=True)

    rows: list[ProductResult] = []
    for key in args.only:
        spec = PRODUCTS.get(key.lower())
        if spec is None:
            print(f'Unknown product {key!r}', file=sys.stderr)
            continue
        print(f'\n--- {spec.code} ---', flush=True)
        res = run_product(spec)
        if res is None:
            continue
        rows.append(res)
        pf = f'{res.pf:.2f}' if np.isfinite(res.pf) else '—'
        note = res.note or '—'
        print(
            f'| {res.code} | {res.n_days} | {res.n_legs} | ${res.net:,.0f} | ${res.closed_dd:,.0f} | '
            f'**${res.mtm_dd:,.0f}** | {res.net_mtm:.2f} | {res.win_pct:.1f}% | {pf} | {note} |',
            flush=True,
        )

    if rows:
        v2b_ref = {
            'YM': (976, 1290, 305_950, 24_434),
            'MYM': (957, 1260, 26_754, 2_541),
            'MNQ': (961, 1302, 83_245, 3_130),
        }
        print('\n### v2b reference (same causal scanner, MA50>MA150)\n', flush=True)
        print('| Product | v2b Net | v2b MTM DD | v2d Net | v2d MTM DD |', flush=True)
        print('|---|---:|---:|---:|---:|', flush=True)
        for r in rows:
            ref = v2b_ref.get(r.code)
            if ref:
                print(
                    f'| {r.code} | ${ref[2]:,.0f} | ${ref[3]:,.0f} | ${r.net:,.0f} | ${r.mtm_dd:,.0f} |',
                    flush=True,
                )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
