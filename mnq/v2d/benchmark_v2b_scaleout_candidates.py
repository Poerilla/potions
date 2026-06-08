#!/usr/bin/env python3
"""
Causal **v2b scaleout (×2)** rerun on current 1m DBN — all days and C3 filters.

Scenarios (all use prior-day **MA50>MA150** where noted; ORB from 1m; no lookahead):
1. **Tracker (v2b-only all days)** — trade only v2b-regime days; Long+Short up to 2 legs.
2. **C3 days only** — same v2b scaleout on C3 calendar days (no MA filter).
3. **C3 + MA50>MA150** — C3 day AND v2b regime.

Reports net, closed DD, MTM DD, PF, Net/MTM. Compares to STRATEGY_TRACKER leader.

Example::

  python3 benchmark_v2b_scaleout_candidates.py
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

V2D = Path(__file__).resolve().parent
MNQ_ROOT = V2D.parent
CASE = MNQ_ROOT / 'case_studies' / 'midnight_open_hourly_charts'
SETUPS = MNQ_ROOT / 'case_studies' / 'daily_candlestick_theory' / 'setups.csv'
DEFAULT_DBN = MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
DAILY_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
HISTORY_START = date(2021, 3, 4)

POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
sys.path[:0] = [str(MNQ_ROOT), str(POTIONS_SCRIPTS), str(V2D), str(CASE)]

from mtm_v2b_scaleout import (  # noqa: E402
    LegMtm,
    closed_dd,
    portfolio_mtm_dd_simple,
    simulate_scale_out_leg_mtm,
)
from run_adaptive_50_150_scaleout import (  # noqa: E402
    ORB_HI,
    _EPS,
    find_fill_v2b_long,
    find_fill_v2b_short,
    path_after_prior,
    rth_slice,
    trade_params,
)

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass
class ScenarioResult:
    name: str
    n_days: int
    n_legs: int
    net: float
    closed_dd: float
    mtm_dd: float
    mtm_pct: float
    net_mtm: float
    win_pct: float
    pf: float
    median: float
    note: str


def causal_regime_v2b() -> pd.Series:
    store = db.DBNStore.from_file(str(DAILY_DBN))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    close = fm.set_index('date').sort_index()['close']
    ma_fast = close.rolling(50).mean()
    ma_slow = close.rolling(150).mean()
    return (ma_fast > ma_slow).shift(1).fillna(True)


def load_c3_days(path: Path) -> set[date]:
    df = pd.read_csv(path)
    return {date.fromisoformat(str(x)) for x in df['c3_date']}


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


def v2b_scaleout_session(
    session_day: date,
    day_raw: pd.DataFrame,
) -> tuple[list[LegMtm], list[list[tuple[pd.Timestamp, float]]], list[float]]:
    """Causal v2b scaleout: Long then Short leg, max 2, 1m fill discovery."""
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
        pm = trade_params('v2b', direction, rh, rl, rv)
        if pm is None:
            continue
        sub = path_after_prior(rth, session_day, prior_exit)
        if sub.empty:
            continue
        if direction == 'Long':
            fts, _ = find_fill_v2b_long(sub, rh)
        else:
            fts, _ = find_fill_v2b_short(sub, rl)
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
        )
        legs.append(LegMtm(session_day, direction, fts, exit_ts, net))
        curves.append(samples)
        nets.append(net)
        if exit_ts is not None:
            prior_exit = exit_ts

    return legs, curves, nets


def run_scenario(
    name: str,
    gby: dict[date, pd.DataFrame],
    regime: pd.Series,
    *,
    day_filter,
    note: str,
) -> ScenarioResult:
    all_legs: list[LegMtm] = []
    all_curves: list[list[tuple[pd.Timestamp, float]]] = []
    all_nets: list[float] = []
    n_days = 0

    for session_day in sorted(gby.keys()):
        if session_day < HISTORY_START:
            continue
        if not day_filter(session_day):
            continue
        raw = gby[session_day]
        if raw is None or raw.empty:
            continue
        legs, curves, nets = v2b_scaleout_session(session_day, raw)
        if not legs:
            continue
        n_days += 1
        all_legs.extend(legs)
        all_curves.extend(curves)
        all_nets.extend(nets)

    pnl = np.array(all_nets, dtype=float)
    mtm_dd, mtm_pct, net = portfolio_mtm_dd_simple(all_legs, all_curves)
    cdd = closed_dd(pnl)
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl <= 0].sum())
    pf = wins / losses if losses > 1e-9 else float('inf')

    return ScenarioResult(
        name=name,
        n_days=n_days,
        n_legs=len(all_legs),
        net=net,
        closed_dd=cdd,
        mtm_dd=mtm_dd,
        mtm_pct=mtm_pct,
        net_mtm=net / mtm_dd if mtm_dd > 1e-9 else float('nan'),
        win_pct=100.0 * (pnl > 0).mean() if len(pnl) else float('nan'),
        pf=pf,
        median=float(np.median(pnl)) if len(pnl) else float('nan'),
        note=note,
    )


def print_results(rows: list[ScenarioResult], tracker: ScenarioResult) -> None:
    print('\n## v2b scaleout (×2 MNQ) — causal 1m rerun\n', flush=True)
    print(
        '| Scenario | Days | Legs | Net | Closed DD | **MTM DD** | Net/MTM | Win% | PF | Median |',
        flush=True,
    )
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|', flush=True)
    for r in rows:
        pf = f'{r.pf:.2f}' if np.isfinite(r.pf) else '—'
        print(
            f'| {r.name} | {r.n_days} | {r.n_legs} | ${r.net:,.0f} | ${r.closed_dd:,.0f} | '
            f'**${r.mtm_dd:,.0f}** | {r.net_mtm:.2f} | {r.win_pct:.1f}% | {pf} | ${r.median:,.0f} |',
            flush=True,
        )
    print(f'\n_Tracker reference (this run): ${tracker.net:,.0f} net, ${tracker.mtm_dd:,.0f} MTM DD_\n', flush=True)

    # Rank by net/MTM among causal books
    causal = [r for r in rows if 'MA50' in r.name or r.name.startswith('A)')]
    if causal:
        best = max(causal, key=lambda x: x.net_mtm if np.isfinite(x.net_mtm) else -1)
        print(f'**Best Net/MTM (causal v2b scaleout):** {best.name} ({best.net_mtm:.2f})', flush=True)

    old_net = 35_847.0
    old_dd = 5_190.0
    print(f'\n**STRATEGY_TRACKER prior:** ${old_net:,.0f} net, ${old_dd:,.0f} closed DD (no MTM published)\n', flush=True)

    beats = [
        r
        for r in rows
        if r.net > old_net and r.mtm_dd <= old_dd * 1.05 and r.name != 'D) C3 days (no MA filter)'
    ]
    if beats:
        w = max(beats, key=lambda x: x.net_mtm)
        print(
            f'**Promotion candidate:** {w.name} — ${w.net:,.0f} net, ${w.mtm_dd:,.0f} MTM DD, '
            f'beats tracker on net with similar/worse DD check passed.',
            flush=True,
        )
    else:
        print('**No scenario beats tracker on net + DD together.** Tracker leader unchanged.', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--setups-csv', type=Path, default=SETUPS)
    args = ap.parse_args()

    if not args.dbn.is_file():
        print('Missing DBN', file=sys.stderr)
        return 1

    regime = causal_regime_v2b()
    c3_days = load_c3_days(args.setups_csv) if args.setups_csv.is_file() else set()

    print('Loading 1m DBN (full book) ...', flush=True)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')

    def is_regime(d: date) -> bool:
        return d in regime.index and bool(regime.loc[d])

    rows = [
        run_scenario(
            'A) Tracker: v2b-only all days (MA50>MA150)',
            gby,
            regime,
            day_filter=lambda d: is_regime(d),
            note='Causal; skip v2d regime days',
        ),
        run_scenario(
            'B) C3 days only (no MA filter)',
            gby,
            regime,
            day_filter=lambda d: d in c3_days,
            note='Not causal regime — diagnostic only',
        ),
        run_scenario(
            'C) C3 + MA50>MA150',
            gby,
            regime,
            day_filter=lambda d: d in c3_days and is_regime(d),
            note='Causal regime + C3 calendar filter',
        ),
    ]

    tracker_row = rows[0]
    print_results(rows, tracker_row)

    # C3 study ×1 reference
    c3_csv = CASE / 'backtest_c3_swing_orb_fade_trades_mnq.csv'
    if c3_csv.is_file():
        from analyze_atr_fade_touch_excursions import load_trades, mtm_drawdown

        c3t = load_trades(c3_csv)
        pnl = np.array([t.pnl_usd for t in c3t])
        mtm, _, _ = mtm_drawdown(c3t, gby)
        print(
            f'\n_Reference — C3 opposite-break (×1): ${pnl.sum():,.0f} net, '
            f'{len(c3t)} trades, MTM DD ${mtm:,.0f}_\n',
            flush=True,
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
