#!/usr/bin/env python3
"""Order-sequencing audit for MNQ adaptive 50/150 v2b-only scaleout.

The current tracker leader uses a fresh 1-minute discovery pass on every
prior-day MA50>MA150 session. This script replays that same book and compares
it with broker-like sequencing variants:

1. ``long_priority_scanner``: current benchmark. Scan Long first; if it never
   fills, scan Short from the same post-ORB path. This reproduces
   ``benchmark_v2b_scaleout_candidates.py``.
2. ``oco_bracket_reverse``: place long and short stop campaigns together after
   the opening range; whichever side triggers first owns the first campaign.
   After that campaign exits, only the opposite side can arm.
3. ``long_then_short_strict``: executable literal of "try Long first, then Short
   after leg 1 exits"; if Long never fills, no Short is taken that day.

All fills and exits reuse the same pessimistic 1-minute scaleout simulator as
the benchmark: 2 MNQ, 1 off at TP1, runner to TP2, stop before target on
ambiguous bars, and remaining size flattened at the last RTH close.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

V2D = Path(__file__).resolve().parent
MNQ_ROOT = V2D.parent
CASE = MNQ_ROOT / 'case_studies' / 'midnight_open_hourly_charts'
DEFAULT_DBN = MNQ_ROOT / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
OUT_SUMMARY = V2D / 'v2b_scaleout_ordering_audit_summary.csv'
OUT_REPORT = V2D / 'V2B_SCALEOUT_ORDERING_AUDIT.md'
HISTORY_START = date(2021, 3, 4)

POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'
sys.path[:0] = [str(MNQ_ROOT), str(POTIONS_SCRIPTS), str(V2D), str(CASE)]

from benchmark_v2b_scaleout_candidates import (  # noqa: E402
    causal_regime_v2b,
    orb_range,
    v2b_scaleout_session,
)
from mtm_v2b_scaleout import (  # noqa: E402
    LegMtm,
    closed_dd,
    portfolio_mtm_dd_simple,
    simulate_scale_out_leg_mtm,
)
from run_adaptive_50_150_scaleout import (  # noqa: E402
    _EPS,
    find_fill_v2b_long,
    find_fill_v2b_short,
    path_after_prior,
    rth_slice,
    trade_params,
)

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass
class ReplaySummary:
    scenario: str
    days_with_legs: int
    legs: int
    net: float
    closed_dd: float
    mtm_dd: float
    mtm_pct: float
    net_mtm: float
    win_pct: float
    pf: float
    median: float
    notes: str


@dataclass
class ReplayLeg:
    scenario: str
    session_day: str
    leg_index: int
    direction: str
    fill_ts: str
    exit_ts: str
    net_usd: float


def _first_trigger(
    sub: pd.DataFrame,
    rh: float,
    rl: float,
    directions: tuple[str, ...],
) -> tuple[str | None, pd.Timestamp | None]:
    """Return first chronological entry trigger among supplied directions.

    If both sides touch on the same 1-minute bar, Long wins the tie. Ties are
    rare, and using Long preserves the benchmark's stated side priority.
    """
    long_trig = rh + 0.25
    short_trig = rl - 0.25
    for ts, bar in sub.iterrows():
        candidates: list[str] = []
        if 'Long' in directions and float(bar['high']) >= long_trig - _EPS:
            candidates.append('Long')
        if 'Short' in directions and float(bar['low']) <= short_trig + _EPS:
            candidates.append('Short')
        if candidates:
            return ('Long' if 'Long' in candidates else candidates[0]), pd.Timestamp(ts)
    return None, None


def _simulate_one_leg(
    session_day: date,
    rth: pd.DataFrame,
    direction: str,
    fill_ts: pd.Timestamp,
    rh: float,
    rl: float,
    rv: float,
) -> tuple[LegMtm, list[tuple[pd.Timestamp, float]]]:
    pm = trade_params('v2b', direction, rh, rl, rv)
    if pm is None:
        raise ValueError('Invalid range for %s' % session_day)
    net, exit_ts, samples = simulate_scale_out_leg_mtm(
        rth,
        session_day,
        fill_ts,
        entry=float(pm['entry']),
        long_side=bool(pm['long_side']),
        init_sl=float(pm['init_sl']),
        tp1=float(pm['tp1']),
        tp2=float(pm['tp2']),
        runner_sl=float(pm['runner_sl']),
    )
    return LegMtm(session_day, direction, fill_ts, exit_ts, net), samples


def replay_oco_bracket_reverse(
    session_day: date,
    day_raw: pd.DataFrame,
) -> tuple[list[LegMtm], list[list[tuple[pd.Timestamp, float]]]]:
    rth = rth_slice(day_raw, session_day)
    if rth.empty:
        return [], []
    orb = orb_range(rth, session_day)
    if orb is None:
        return [], []
    rh, rl, rv = orb

    legs: list[LegMtm] = []
    curves: list[list[tuple[pd.Timestamp, float]]] = []
    prior_exit: pd.Timestamp | None = None
    remaining = ('Long', 'Short')

    while len(legs) < 2 and remaining:
        sub = path_after_prior(rth, session_day, prior_exit)
        if sub.empty:
            break
        direction, fill_ts = _first_trigger(sub, rh, rl, remaining)
        if direction is None or fill_ts is None:
            break
        leg, samples = _simulate_one_leg(session_day, rth, direction, fill_ts, rh, rl, rv)
        legs.append(leg)
        curves.append(samples)
        if leg.exit_ts is None:
            break
        prior_exit = leg.exit_ts
        remaining = tuple(d for d in ('Long', 'Short') if d != direction)

    return legs, curves


def replay_long_then_short_strict(
    session_day: date,
    day_raw: pd.DataFrame,
) -> tuple[list[LegMtm], list[list[tuple[pd.Timestamp, float]]]]:
    rth = rth_slice(day_raw, session_day)
    if rth.empty:
        return [], []
    orb = orb_range(rth, session_day)
    if orb is None:
        return [], []
    rh, rl, rv = orb

    legs: list[LegMtm] = []
    curves: list[list[tuple[pd.Timestamp, float]]] = []
    prior_exit: pd.Timestamp | None = None

    sub = path_after_prior(rth, session_day, prior_exit)
    fts, _ = find_fill_v2b_long(sub, rh)
    if fts is None:
        return [], []
    leg, samples = _simulate_one_leg(session_day, rth, 'Long', fts, rh, rl, rv)
    legs.append(leg)
    curves.append(samples)
    if leg.exit_ts is None:
        return legs, curves
    prior_exit = leg.exit_ts

    sub = path_after_prior(rth, session_day, prior_exit)
    fts, _ = find_fill_v2b_short(sub, rl)
    if fts is not None:
        leg, samples = _simulate_one_leg(session_day, rth, 'Short', fts, rh, rl, rv)
        legs.append(leg)
        curves.append(samples)
    return legs, curves


def replay_long_priority_scanner(
    session_day: date,
    day_raw: pd.DataFrame,
) -> tuple[list[LegMtm], list[list[tuple[pd.Timestamp, float]]]]:
    legs, curves, _nets = v2b_scaleout_session(session_day, day_raw)
    return legs, curves


def summarize(
    scenario: str,
    gby: dict[date, pd.DataFrame],
    regime: pd.Series,
    replay_fn: Callable[[date, pd.DataFrame], tuple[list[LegMtm], list[list[tuple[pd.Timestamp, float]]]]],
    notes: str,
) -> tuple[ReplaySummary, list[ReplayLeg]]:
    all_legs: list[LegMtm] = []
    all_curves: list[list[tuple[pd.Timestamp, float]]] = []
    out_legs: list[ReplayLeg] = []
    days = 0

    for session_day in sorted(gby.keys()):
        if session_day < HISTORY_START:
            continue
        if session_day not in regime.index or not bool(regime.loc[session_day]):
            continue
        legs, curves = replay_fn(session_day, gby[session_day])
        if not legs:
            continue
        days += 1
        all_legs.extend(legs)
        all_curves.extend(curves)
        for i, leg in enumerate(legs, start=1):
            out_legs.append(
                ReplayLeg(
                    scenario=scenario,
                    session_day=session_day.isoformat(),
                    leg_index=i,
                    direction=leg.direction,
                    fill_ts=str(leg.fill_ts),
                    exit_ts='' if leg.exit_ts is None else str(leg.exit_ts),
                    net_usd=leg.net_usd,
                )
            )

    pnl = np.array([leg.net_usd for leg in all_legs], dtype=float)
    mtm_dd, mtm_pct, net = portfolio_mtm_dd_simple(all_legs, all_curves)
    cdd = closed_dd(pnl)
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl <= 0].sum())
    pf = wins / losses if losses > 1e-9 else math.inf
    summary = ReplaySummary(
        scenario=scenario,
        days_with_legs=days,
        legs=len(all_legs),
        net=round(net, 2),
        closed_dd=round(cdd, 2),
        mtm_dd=round(mtm_dd, 2),
        mtm_pct=round(mtm_pct, 4) if np.isfinite(mtm_pct) else float('nan'),
        net_mtm=round(net / mtm_dd, 4) if mtm_dd > 1e-9 else float('nan'),
        win_pct=round(100.0 * (pnl > 0).mean(), 4) if len(pnl) else float('nan'),
        pf=round(pf, 4) if np.isfinite(pf) else float('inf'),
        median=round(float(np.median(pnl)), 2) if len(pnl) else float('nan'),
        notes=notes,
    )
    return summary, out_legs


def _money(v: float) -> str:
    return '$%s' % format(v, ',.0f')


def write_report(rows: list[ReplaySummary], report_path: Path) -> None:
    lines = [
        '# MNQ v2b Scaleout Ordering Audit',
        '',
        'Source: full MNQ 1-minute DBN `raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst`.',
        'Regime: prior-day daily MA50 > MA150, shifted one day. Sizing: 2 MNQ, TP1/runner/TP2.',
        '',
        '| Scenario | Days | Legs | Net | Closed DD | MTM DD | Net/MTM | Win% | PF | Median |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in rows:
        lines.append(
            '| %s | %d | %d | %s | %s | %s | %.2f | %.1f%% | %.2f | %s |'
            % (
                r.scenario,
                r.days_with_legs,
                r.legs,
                _money(r.net),
                _money(r.closed_dd),
                _money(r.mtm_dd),
                r.net_mtm,
                r.win_pct,
                r.pf,
                _money(r.median),
            )
        )
    lines.extend(
        [
            '',
            '## Read',
            '',
            '- `long_priority_scanner` reproduces the current tracker row, but it is a scanner convention rather than a normal live OCO order book.',
            '- `oco_bracket_reverse` is closest to the Pine/TradingView harness: both sides can arm after the opening range, first fill owns the campaign, then only the opposite side can re-arm after exit.',
            '- `long_then_short_strict` is the literal executable version of "try Long first, then Short after Long exits"; it intentionally skips Short-only days where Long never filled.',
            '',
            'If the strategy is routed through TradingView/Tradovate using the current Pine, compare live paper fills to `oco_bracket_reverse`, not to the long-priority scanner.',
            '',
        ]
    )
    report_path.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--summary-csv', type=Path, default=OUT_SUMMARY)
    ap.add_argument('--report-md', type=Path, default=OUT_REPORT)
    args = ap.parse_args()

    if not args.dbn.is_file():
        print('Missing DBN: %s' % args.dbn, file=sys.stderr)
        return 1

    regime = causal_regime_v2b()
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')

    specs = [
        (
            'long_priority_scanner',
            replay_long_priority_scanner,
            'Current benchmark; Long gets whole-day priority before Short scanner.',
        ),
        (
            'oco_bracket_reverse',
            replay_oco_bracket_reverse,
            'Broker-like OCO first campaign, then opposite side can re-arm.',
        ),
        (
            'long_then_short_strict',
            replay_long_then_short_strict,
            'Executable literal: Short only after a filled Long exits.',
        ),
    ]
    summaries: list[ReplaySummary] = []
    all_legs: list[ReplayLeg] = []
    for name, fn, notes in specs:
        print('Running %s ...' % name, flush=True)
        summary, legs = summarize(name, gby, regime, fn, notes)
        summaries.append(summary)
        all_legs.extend(legs)

    pd.DataFrame([asdict(r) for r in summaries]).to_csv(args.summary_csv, index=False)
    legs_path = args.summary_csv.with_name(args.summary_csv.stem + '_legs.csv')
    pd.DataFrame([asdict(r) for r in all_legs]).to_csv(legs_path, index=False)
    write_report(summaries, args.report_md)

    print('\n| Scenario | Days | Legs | Net | Closed DD | MTM DD | Net/MTM | Win% | PF |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    for r in summaries:
        print(
            '| %s | %d | %d | %s | %s | %s | %.2f | %.1f%% | %.2f |'
            % (
                r.scenario,
                r.days_with_legs,
                r.legs,
                _money(r.net),
                _money(r.closed_dd),
                _money(r.mtm_dd),
                r.net_mtm,
                r.win_pct,
                r.pf,
            )
        )
    print('\nWrote %s' % args.summary_csv)
    print('Wrote %s' % legs_path)
    print('Wrote %s' % args.report_md)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
