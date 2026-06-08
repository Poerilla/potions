#!/usr/bin/env python3
"""
Causal **v2b-only scaleout (×2)** on NQ, ES, MES, YM, MYM (+ MNQ reference).

Same rules as ``benchmark_v2b_scaleout_candidates.py`` scenario A:
  - Prior-day **MA50 > MA150** on **that product's** daily closes (shift 1).
  - v2b Long RH+tick / Short RL−tick; 2 contracts; TP1 ±1R, runner BE, TP2 ±2R.
  - Pessimistic 1m bar order; $1.50 RT fee per contract closed.

Example::

  python3 benchmark_v2b_scaleout_multiproduct.py
  python3 benchmark_v2b_scaleout_multiproduct.py --only nq es
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
import pytz

V2D = Path(__file__).resolve().parent
POTIONS = V2D.parent.parent
MNQ_ROOT = V2D.parent
CASE = MNQ_ROOT / 'case_studies' / 'midnight_open_hourly_charts'
HISTORY_START = date(2021, 3, 4)
NY = pytz.timezone('America/New_York')

sys.path[:0] = [str(MNQ_ROOT), str(POTIONS / 'scripts'), str(V2D), str(CASE)]

from mtm_v2b_scaleout import (  # noqa: E402
    LegMtm,
    closed_dd,
    portfolio_mtm_dd_simple,
    simulate_scale_out_leg_mtm,
)
from run_adaptive_50_150_scaleout import (  # noqa: E402
    ORB_HI,
    RTH_HI,
    RTH_LO,
    _EPS,
    path_after_prior,
    rth_slice,
)

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass(frozen=True)
class ProductSpec:
    code: str
    instrument: str
    prefix: str
    tick: float
    mult: float
    fee_rt: float
    dbn_1m: Path
    daily_dbn: Path | None
    csv_1m: Path | None = None
    note: str = ''


PRODUCTS: dict[str, ProductSpec] = {
    'mnq': ProductSpec(
        'MNQ',
        'mnq',
        'MNQ',
        0.25,
        2.0,
        1.50,
        MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
        MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst',
    ),
    'nq': ProductSpec(
        'NQ',
        'nq',
        'NQ',
        0.25,
        20.0,
        1.50,
        POTIONS / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst',
        POTIONS / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1d (nq).dbn.zst',
    ),
    'es': ProductSpec(
        'ES',
        'es',
        'ES',
        0.25,
        50.0,
        1.50,
        POTIONS / 'es' / 'raw' / 'glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst',
        POTIONS / 'es' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1d (es).dbn.zst',
    ),
    'mes': ProductSpec(
        'MES',
        'mes',
        'MES',
        0.25,
        5.0,
        1.50,
        POTIONS / 'mes' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m (mym-mes).dbn.zst',
        None,
        csv_1m=POTIONS / 'mes' / 'mes_1min_raw.csv',
        note='DBN corrupt; 1m from mes_1min_raw.csv',
    ),
    'ym': ProductSpec(
        'YM',
        'ym',
        'YM',
        1.0,
        5.0,
        1.50,
        POTIONS / 'ym' / 'raw' / 'glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst',
        None,
        note='Daily DBN is ES mislabel; regime from 1m session last close',
    ),
    'mym': ProductSpec(
        'MYM',
        'mym',
        'MYM',
        1.0,
        0.50,
        1.50,
        POTIONS / 'mym' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst',
        None,
        note='No daily DBN; regime from 1m session last close',
    ),
}


@dataclass
class ProductResult:
    code: str
    n_days: int
    n_legs: int
    net: float
    closed_dd: float
    mtm_dd: float
    net_mtm: float
    win_pct: float
    pf: float
    note: str


def causal_regime_from_daily(daily_dbn: Path, prefix: str) -> pd.Series:
    store = db.DBNStore.from_file(str(daily_dbn))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    if prefix == 'NQ':
        df = df[df['symbol'].str.startswith('NQ') & ~df['symbol'].str.startswith('MNQ')].copy()
    elif prefix == 'ES':
        df = df[df['symbol'].str.startswith('ES') & ~df['symbol'].str.startswith('MES')].copy()
    elif prefix == 'YM':
        df = df[df['symbol'].str.startswith('YM') & ~df['symbol'].str.startswith('MYM')].copy()
    else:
        df = df[df['symbol'].str.startswith(prefix)].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    close = fm.set_index('date').sort_index()['close']
    ma_fast = close.rolling(50).mean()
    ma_slow = close.rolling(150).mean()
    return (ma_fast > ma_slow).shift(1).fillna(True)


def causal_regime_from_gby(gby: dict[date, pd.DataFrame]) -> pd.Series:
    """Session last 1m close per NY date → MA50/150 (shift 1)."""
    closes: dict[date, float] = {}
    for d, df in gby.items():
        if df is None or df.empty:
            continue
        day = df[df.index.map(lambda t: t.date() == d)]
        if day.empty:
            continue
        closes[d] = float(day.iloc[-1]['close'])
    if not closes:
        return pd.Series(dtype=bool)
    s = pd.Series(closes).sort_index()
    ma_fast = s.rolling(50).mean()
    ma_slow = s.rolling(150).mean()
    return (ma_fast > ma_slow).shift(1).fillna(True)


def load_1m_from_csv(csv_path: Path, instrument: str) -> dict[date, pd.DataFrame]:
    print(f'Loading CSV {csv_path} ({instrument.upper()}) ...', flush=True)
    df = pd.read_csv(csv_path)
    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY)
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[mdata._symbol_mask(df['symbol'], instrument)].copy()
    df['d'] = df['ts_event'].dt.date
    fm = (
        df.groupby(['d', 'symbol'])['volume']
        .sum()
        .groupby(level='d')
        .idxmax()
        .apply(lambda x: x[1])
        .to_dict()
    )
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['d']), axis=1)]
    df = df.set_index('ts_event').sort_index()
    gby = {d: g.drop(columns=['d'], errors='ignore') for d, g in df.groupby(df.index.date)}
    print(f'  {len(gby):,} NY dates with bars', flush=True)
    return gby


def load_1m(spec: ProductSpec) -> dict[date, pd.DataFrame]:
    if spec.csv_1m is not None and spec.csv_1m.is_file():
        return load_1m_from_csv(spec.csv_1m, spec.instrument)
    if not spec.dbn_1m.is_file():
        raise FileNotFoundError(spec.dbn_1m)
    try:
        return mdata.load_1m_by_ny_date(spec.dbn_1m.resolve(), spec.instrument)
    except Exception as exc:
        if spec.csv_1m and spec.csv_1m.is_file():
            print(f'  DBN failed ({exc}); falling back to CSV', flush=True)
            return load_1m_from_csv(spec.csv_1m, spec.instrument)
        raise


def orb_range(rth: pd.DataFrame, session_day: date) -> tuple[float, float, float] | None:
    orb = rth[rth.index.map(lambda t: t.date() == session_day and t.time() < ORB_HI)]
    if orb.empty:
        return None
    rh = float(orb['high'].max())
    rl = float(orb['low'].min())
    rv = rh - rl
    if rv <= _EPS:
        return None
    return rh, rl, rv


def trade_params_v2b(direction: str, rh: float, rl: float, rv: float, tick: float) -> dict | None:
    if rv <= _EPS:
        return None
    if direction == 'Long':
        return {
            'long_side': True,
            'entry': rh + tick,
            'init_sl': rl,
            'tp1': rh + rv,
            'tp2': rh + 2.0 * rv,
            'runner_sl': rh + tick,
        }
    return {
        'long_side': False,
        'entry': rl - tick,
        'init_sl': rh,
        'tp1': rl - rv,
        'tp2': rl - 2.0 * rv,
        'runner_sl': rl - tick,
    }


def find_fill_v2b_long(sub: pd.DataFrame, rh: float, tick: float) -> tuple[pd.Timestamp | None, float | None]:
    trig = rh + tick
    for ts, bar in sub.iterrows():
        if float(bar['high']) >= trig - _EPS:
            return pd.Timestamp(ts), float(trig)
    return None, None


def find_fill_v2b_short(sub: pd.DataFrame, rl: float, tick: float) -> tuple[pd.Timestamp | None, float | None]:
    trig = rl - tick
    for ts, bar in sub.iterrows():
        if float(bar['low']) <= trig + _EPS:
            return pd.Timestamp(ts), float(trig)
    return None, None


def v2b_scaleout_session(
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
        pm = trade_params_v2b(direction, rh, rl, rv, tick)
        if pm is None:
            continue
        sub = path_after_prior(rth, session_day, prior_exit)
        if sub.empty:
            continue
        if direction == 'Long':
            fts, _ = find_fill_v2b_long(sub, rh, tick)
        else:
            fts, _ = find_fill_v2b_short(sub, rl, tick)
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

    if spec.daily_dbn is not None and spec.daily_dbn.is_file():
        regime = causal_regime_from_daily(spec.daily_dbn, spec.prefix)
    else:
        regime = causal_regime_from_gby(gby)

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
        legs, curves, nets = v2b_scaleout_session(
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
    ap.add_argument(
        '--only',
        nargs='+',
        default=['mnq', 'nq', 'es', 'mes', 'ym', 'mym'],
        help='Product keys to run (default: all)',
    )
    args = ap.parse_args()

    print(
        '\n## v2b-only scaleout (×2) — causal 1m rerun, MA50>MA150 gate\n'
        f'_History from {HISTORY_START}; fee $1.50 RT/contract; pessimistic 1m fills_\n',
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
            print(f'Unknown product key {key!r}', file=sys.stderr)
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
        best_net = max(rows, key=lambda r: r.net)
        best_ratio = max(rows, key=lambda r: r.net_mtm if np.isfinite(r.net_mtm) else -1)
        print(
            f'\n**Largest net:** {best_net.code} (${best_net.net:,.0f}, MTM DD ${best_net.mtm_dd:,.0f})',
            flush=True,
        )
        print(
            f'**Best Net/MTM:** {best_ratio.code} ({best_ratio.net_mtm:.2f})',
            flush=True,
        )
        mnq = next((r for r in rows if r.code == 'MNQ'), None)
        if mnq:
            print(
                f'\n_MNQ reference (this run): ${mnq.net:,.0f} net, ${mnq.mtm_dd:,.0f} MTM DD '
                f'(tracker causal ~$83k / $3.1k)_',
                flush=True,
            )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
