#!/usr/bin/env python3
"""
London **child-after-sweep** × **monthly ORB bias** filter.

**Day universe**

- ``--day-universe opp_sweep`` (default): annotator ``Opp_sweep_London_*`` rows only; sweep side
  from row flags (same as ``build_london_sweep_charts --day-universe opp_sweep``).
- ``--day-universe all_rth``: NY weekdays in ``--start``/``--end`` with RTH 1m
  ``[09:30,16:00)``; ``simulate_london_child_after_sweep(..., sweep_low=None)`` infers first RTH
  London sweep — aligned with ``analyze_london_child_after_sweep_equity.py`` and the PNG batch in
  ``case_studies/london_sweep/`` when charts were built with ``--day-universe all_rth``.

**Bias mapping (user rule)**

- **Bullish month** (``bullish_break`` or ``hemisphere_long``): trade only when the session’s
  **first RTH London sweep** is **low** (long path).
- **Bearish month** (``bearish_break`` or ``hemisphere_short``): trade only when first sweep is **high**
  (short path).
- **Neutral** (``ambiguous`` or ``insufficient_data``): skip ($0).

Baseline always runs the full model (annotator side or inferred ``None``). Filtered rows zero out P/L
when bias and sweep disagree or month is neutral.

Defaults: causal ORB gate on, ``sl_mode=london_range``, ``--sl-points 30``.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

V2E_SCR = Path(__file__).resolve().parent
MNQ = V2E_SCR.parents[1]
POTIONS_PKG = MNQ.parent

sys.path[:0] = [str(V2E_SCR), str(POTIONS_PKG / 'scripts'), str(MNQ / 'scripts'), str(MNQ)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from build_london_sweep_charts import (  # noqa: E402
    row_sweep_low,
    session_has_rth_like_swept_orb,
    trim_chart_session,
)
from sim_london_child_after_sweep import (  # noqa: E402
    infer_sweep_low_first_rth_hit,
    simulate_london_child_after_sweep,
)
from sim_london_limit_scaleout import SlMode, london_0200_0930_hilo, rth_1m  # noqa: E402

from plot_daily_prior_month_levels import load_mnq_front_daily  # noqa: E402
from rules.monthly_opening_range_bias import MonthlyOrbBiasResult, monthly_orb_bias_for_session_date  # noqa: E402

DEFAULT_ANNOTATED = MNQ / 'mnq_orb_results_stops_annotated.csv'
DEFAULT_M1 = MNQ / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_DBN = MNQ / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'


def monthly_ldn_sweep_bias_state(b: MonthlyOrbBiasResult) -> str:
    if b.bucket in ('bullish_break', 'hemisphere_long'):
        return 'bullish'
    if b.bucket in ('bearish_break', 'hemisphere_short'):
        return 'bearish'
    return 'neutral'


def sweep_alignment_keep(state: str, sweep_low: bool | None) -> bool:
    if state == 'neutral' or sweep_low is None:
        return False
    if state == 'bullish':
        return sweep_low is True
    if state == 'bearish':
        return sweep_low is False
    return False


def equity_max_dd_terminal(nets: np.ndarray) -> tuple[float, float]:
    cum = np.cumsum(nets)
    if len(cum) == 0:
        return 0.0, 0.0
    run_max = np.maximum.accumulate(cum)
    dd = run_max - cum
    return float(dd.max()), float(cum[-1])


def print_block(title: str, nets: np.ndarray, filled: np.ndarray | None = None) -> None:
    n = len(nets)
    total = float(nets.sum())
    wr_all = 100.0 * float((nets > 1e-9).sum()) / n if n else float('nan')
    mdd, te = equity_max_dd_terminal(nets)
    print(f'\n=== {title} ===')
    print(f'  n (events):        {n}')
    print(f'  Σ Net_$:           {total:,.2f}')
    print(f'  Win rate ($>0/n):  {wr_all:.2f}%')
    if filled is not None:
        nf = int(filled.sum())
        wins_f = int((filled & (nets > 1e-9)).sum())
        wr_f = 100.0 * wins_f / nf if nf else float('nan')
        print(f'  Filled sim:        {nf}')
        print(f'  Win rate ($>/filled): {wr_f:.2f}%')
    print(f'  Max DD (cum sum):  {mdd:,.2f}')
    print(f'  Terminal equity:   {te:,.2f}')


def collect_opp_sweep(
    sub: pd.DataFrame,
    bias_by_date: dict,
    gby: dict,
    sl_points: float,
    sl_mode: SlMode,
    orb_gate: bool,
) -> pd.DataFrame:
    rows_out: List[dict] = []
    for _, row in sub.iterrows():
        d = row['Date']
        sw = row_sweep_low(row)
        b = bias_by_date[d]
        st = monthly_ldn_sweep_bias_state(b)
        align = sweep_alignment_keep(st, sw)
        day = gby.get(d)
        if day is None or day.empty:
            sim_net = 0.0
            sim_filled = False
            reason = 'no_1m'
        else:
            df1 = trim_chart_session(day)
            lh, ll = london_0200_0930_hilo(df1)
            sim = simulate_london_child_after_sweep(
                df1,
                lh,
                ll,
                sw,
                sl_points,
                sl_mode=sl_mode,
                require_causal_orb_pierce=orb_gate,
            )
            sim_net = float(sim.net_dollars)
            sim_filled = bool(sim.filled)
            reason = sim.reason
        rows_out.append(
            {
                'Date': d,
                'sweep_low': sw,
                'bias_bucket': b.bucket,
                'bias_state': st,
                'align_ok': align,
                'sim_net': sim_net,
                'sim_filled': sim_filled,
                'sim_reason': reason,
                'v2b_net': float(row['Net_$']),
            }
        )
    return pd.DataFrame(rows_out)


def collect_all_rth(
    days: List[date],
    bias_by_date: dict,
    gby: dict,
    sl_points: float,
    sl_mode: SlMode,
    orb_gate: bool,
) -> pd.DataFrame:
    """Same session gate + trim + sim(None) as ``analyze_london_child_after_sweep_equity``."""
    rows_out: List[dict] = []
    for d in sorted(days):
        day = gby.get(d)
        if day is None or day.empty or not session_has_rth_like_swept_orb(day):
            continue
        b = bias_by_date[d]
        st = monthly_ldn_sweep_bias_state(b)
        df1 = trim_chart_session(day)
        lh, ll = london_0200_0930_hilo(df1)
        rth = rth_1m(df1)
        sl_inf = infer_sweep_low_first_rth_hit(rth, lh, ll)
        align = sweep_alignment_keep(st, sl_inf)
        sim = simulate_london_child_after_sweep(
            df1,
            lh,
            ll,
            None,
            sl_points,
            sl_mode=sl_mode,
            require_causal_orb_pierce=orb_gate,
        )
        sim_net = float(sim.net_dollars)
        sim_filled = bool(sim.filled)
        rows_out.append(
            {
                'Date': d,
                'sweep_low': sl_inf,
                'bias_bucket': b.bucket,
                'bias_state': st,
                'align_ok': align,
                'sim_net': sim_net,
                'sim_filled': sim_filled,
                'sim_reason': sim.reason,
                'v2b_net': float('nan'),
            }
        )
    return pd.DataFrame(rows_out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--annotated', type=Path, default=DEFAULT_ANNOTATED)
    ap.add_argument('--1m', dest='m1', type=Path, default=DEFAULT_M1)
    ap.add_argument('--daily-dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument(
        '--day-universe',
        choices=('opp_sweep', 'all_rth'),
        default='opp_sweep',
        help='opp_sweep: annotator London sweep rows. all_rth: weekdays + RTH gate (matches INDEX PNG batch).',
    )
    ap.add_argument(
        '--start',
        default=None,
        help='ISO date lower bound (all_rth only; default: min Date in annotated CSV)',
    )
    ap.add_argument(
        '--end',
        default=None,
        help='ISO date upper bound (all_rth only; default: max Date in annotated CSV)',
    )
    ap.add_argument('--sl-points', type=float, default=30.0)
    ap.add_argument('--sl-mode', choices=('london_range', 'fixed'), default='london_range')
    ap.add_argument(
        '--skip-causal-orb-filter',
        action='store_true',
        help='Disable causal ORB pierce gate (see simulate_london_child_after_sweep).',
    )
    args = ap.parse_args()

    if not args.annotated.is_file():
        print(f'Missing annotated CSV: {args.annotated}', file=sys.stderr)
        return 1
    if not args.m1.is_file():
        print(f'Missing 1m CSV: {args.m1}', file=sys.stderr)
        return 1
    if not args.daily_dbn.is_file():
        print(f'Missing daily DBN: {args.daily_dbn}', file=sys.stderr)
        return 1

    sl_mode: SlMode = args.sl_mode  # type: ignore[assignment]
    orb_gate = not args.skip_causal_orb_filter

    df = pd.read_csv(args.annotated)
    df['Date'] = pd.to_datetime(df['Date']).dt.date

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)

    if args.day_universe == 'opp_sweep':
        sel = (df['Opp_sweep_London_H'] == 1) | (df['Opp_sweep_London_L'] == 1)
        sub = df.loc[sel].sort_values('Date').reset_index(drop=True)
        need = set(sub['Date'].unique())
        bias_days = sorted(sub['Date'].unique())
    else:
        t_start = pd.to_datetime(args.start).date() if args.start else df['Date'].min()
        t_end = pd.to_datetime(args.end).date() if args.end else df['Date'].max()
        days_list = [ts.date() for ts in pd.bdate_range(pd.Timestamp(t_start), pd.Timestamp(t_end))]
        need = set(days_list)
        bias_days = days_list
        sub = pd.DataFrame()

    bias_by_date = {d: monthly_orb_bias_for_session_date(d, daily) for d in bias_days}

    tmin, tmax = min(need), max(need)
    raw = ann.load_1m_for_dates(str(args.m1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {
        d: g
        for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    if args.day_universe == 'opp_sweep':
        out = collect_opp_sweep(sub, bias_by_date, gby, args.sl_points, sl_mode, orb_gate)
    else:
        out = collect_all_rth(bias_days, bias_by_date, gby, args.sl_points, sl_mode, orb_gate)

    if out.empty:
        print('No session rows after filters', file=sys.stderr)
        return 1

    print(
        'London sweep × monthly bias  |  model=child-after-sweep  |  '
        f'day_universe={args.day_universe}  |  '
        f'sl_mode={sl_mode} sl_points={args.sl_points} orb_gate={orb_gate}'
    )
    if args.day_universe == 'all_rth':
        print(f'  Weekdays in range: {len(bias_days)}  |  sessions after RTH gate: {len(out)}')
    else:
        print(f'  Annotator sweep rows: {len(out)}')

    nets_all = out['sim_net'].to_numpy(dtype=float)
    filled_all = out['sim_filled'].to_numpy()
    title_base = (
        'BASELINE: inferred sweep (sweep_low=None)'
        if args.day_universe == 'all_rth'
        else 'BASELINE: all annotator sweep days (model @ row sweep side)'
    )
    print_block(title_base, nets_all, filled_all)

    flt = out.loc[out['align_ok']]
    print_block(
        'FILTERED: bias-aligned sessions only (neutral→skip; wrong first-sweep→skip)',
        flt['sim_net'].to_numpy(dtype=float),
        flt['sim_filled'].to_numpy(),
    )

    nets_gate = np.where(out['align_ok'], out['sim_net'], 0.0)
    filled_gate = out['align_ok'].to_numpy() & out['sim_filled'].to_numpy()
    print_block(
        'FILTERED padded to full evaluated timeline ($0 on skipped sessions)',
        nets_gate,
        filled_gate,
    )

    if args.day_universe == 'opp_sweep':
        print_block('v2b Net_$ (tier-1 ORB leg on same CSV rows)', out['v2b_net'].to_numpy())
        print_block('v2b Net_$ — filtered aligned rows only', flt['v2b_net'].to_numpy())

    print('\n=== bias_state counts (sessions in output series) ===')
    print(out['bias_state'].value_counts().sort_index().to_string())
    print(f"\nAlign OK: {int(out['align_ok'].sum())} / {len(out)}")
    neu = int((out['bias_state'] == 'neutral').sum())
    print(f'Neutral sessions (bias skip): {neu}')
    dir_only = out['bias_state'].isin(('bullish', 'bearish'))
    wrong_sweep = dir_only & (~out['align_ok'])
    print(f'Directional month but first-RTH sweep mismatch skipped: {int(wrong_sweep.sum())}')

    order = [
        'bullish_break',
        'bearish_break',
        'hemisphere_long',
        'hemisphere_short',
        'ambiguous',
        'insufficient_data',
    ]
    print('\n=== Model Net_$ by bias bucket | ALL vs ALIGN_OK ===')
    hdr = (
        f'{"bucket":<22} {"n_all":>6} {"sum_all":>12} {"wr_all":>8} '
        f'{"n_flt":>6} {"sum_flt":>12} {"wr_flt":>8}'
    )
    print(hdr)
    print('-' * len(hdr))
    for bkt in order:
        a = out.loc[out['bias_bucket'] == bkt, 'sim_net']
        f = out.loc[(out['bias_bucket'] == bkt) & out['align_ok'], 'sim_net']
        if len(a) == 0:
            continue

        def fmt(s: pd.Series) -> tuple[int, float, float]:
            return len(s), float(s.sum()), 100.0 * float((s > 0).mean()) if len(s) else float('nan')

        na, sa, wa = fmt(a)
        nf, sf, wf = fmt(f)
        print(f'{bkt:<22} {na:>6} {sa:>12,.2f} {wa:>7.1f}% {nf:>6} {sf:>12,.2f} {wf:>7.1f}%')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
