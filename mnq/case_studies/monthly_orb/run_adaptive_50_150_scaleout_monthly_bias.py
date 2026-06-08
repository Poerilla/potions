#!/usr/bin/env python3
"""Re-sim adaptive 50/150 scaleout with monthly ORB gates inside the fill loop.

This differs from the lightweight annotated filter study in one important way:
when a policy skips a candidate leg, the next same-day leg scans from the prior
actual exit, not from an exit that would not have happened live.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd


MNQ_ROOT = Path('/home/tester/hsm/potions/mnq')
V2D = MNQ_ROOT / 'v2d'
MONTHLY_ORB = MNQ_ROOT / 'case_studies' / 'monthly_orb'
DAILY_CSV = MNQ_ROOT / 'mnq_daily.csv'
ADAPTIVE_CSV = V2D / 'mnq_orb_results_adaptive_50_150.csv'
M1_CSV = MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
OUT_ROOT = MONTHLY_ORB

sys.path[:0] = [str(V2D), str(MONTHLY_ORB)]

import run_adaptive_50_150_scaleout as so  # noqa: E402
from analyze_adaptive_scaleout_monthly_bias import (  # noqa: E402
    MNQ_DOLLARS_PER_POINT,
    SCALEOUT_FEE_PER_LEG,
    build_monthly_bias,
    fmt_money,
    fmt_num,
    fmt_pct,
    fmt_pts,
    max_drawdown,
    profit_factor,
)


Policy = Callable[[str, str], bool]


def policy_map() -> dict[str, Policy]:
    return {
        'baseline': lambda regime, alignment: True,
        'monthly_outside_only': lambda regime, alignment: alignment in {'aligned', 'opposed'},
        'monthly_aligned_only': lambda regime, alignment: alignment == 'aligned',
        'monthly_opposed_only': lambda regime, alignment: alignment == 'opposed',
        'v2b_outside_only_v2d_unchanged': (
            lambda regime, alignment: regime != 'v2b' or alignment in {'aligned', 'opposed'}
        ),
        'v2d_outside_only_v2b_unchanged': (
            lambda regime, alignment: regime != 'v2d' or alignment in {'aligned', 'opposed'}
        ),
        'v2d_aligned_only_v2b_unchanged': (
            lambda regime, alignment: regime != 'v2d' or alignment == 'aligned'
        ),
        'v2d_opposed_only_v2b_unchanged': (
            lambda regime, alignment: regime != 'v2d' or alignment == 'opposed'
        ),
        'diagnostic_v2b_opposed_v2d_aligned': (
            lambda regime, alignment: (
                (regime == 'v2b' and alignment == 'opposed')
                or (regime == 'v2d' and alignment == 'aligned')
            )
        ),
    }


def classify_alignment(monthly_bias: str, direction: str) -> str:
    if monthly_bias == 'bullish' and direction == 'Long':
        return 'aligned'
    if monthly_bias == 'bearish' and direction == 'Short':
        return 'aligned'
    if monthly_bias == 'bullish' and direction == 'Short':
        return 'opposed'
    if monthly_bias == 'bearish' and direction == 'Long':
        return 'opposed'
    if monthly_bias in {'neutral', 'building_range'}:
        return monthly_bias
    return 'missing'


@dataclass
class SimLeg:
    policy: str
    date_iso: str
    row_order: int
    regime: str
    direction: str
    monthly_bias: str
    bias_alignment: str
    csv_net_1ct: float
    scaleout_net_2ct: float
    gross_contract_points: float
    net_point_equiv: float
    tp_style: str
    hit_tp1: bool
    hit_tp2: bool
    fill_ts: str
    exit_ts: str


def metrics(label: str, rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {
            'segment': label,
            'trades': 0,
            'days': 0,
            'net_usd': 0.0,
            'gross_contract_points': 0.0,
            'net_point_equiv': 0.0,
            'trade_max_dd_usd': 0.0,
            'daily_max_dd_usd': 0.0,
            'win_rate': math.nan,
            'profit_factor': math.nan,
            'avg_trade_usd': math.nan,
            'tp1_rate': math.nan,
            'tp2_rate': math.nan,
        }

    work = rows.sort_values(['date_iso', 'row_order']).copy()
    pnl = work['scaleout_net_2ct'].astype(float)
    daily = work.groupby('date_iso', sort=True)['scaleout_net_2ct'].sum()
    return {
        'segment': label,
        'trades': int(len(work)),
        'days': int(work['date_iso'].nunique()),
        'net_usd': float(pnl.sum()),
        'gross_contract_points': float(work['gross_contract_points'].sum()),
        'net_point_equiv': float(work['net_point_equiv'].sum()),
        'trade_max_dd_usd': max_drawdown(pnl),
        'daily_max_dd_usd': max_drawdown(daily),
        'win_rate': float((pnl > 0).mean()),
        'profit_factor': profit_factor(pnl),
        'avg_trade_usd': float(pnl.mean()),
        'tp1_rate': float(work['hit_tp1'].mean()),
        'tp2_rate': float(work['hit_tp2'].mean()),
    }


def metric_table(rows: list[dict]) -> str:
    lines = [
        '| Segment | Trades | Days | Net | Gross pts | Net pt equiv | Trade DD | Daily DD | Win rate | PF | TP1 | TP2 | Avg/trade |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        lines.append(
            '| {segment} | {trades} | {days} | {net} | {gross_pts} | {net_pts} | {trade_dd} | {daily_dd} | {win_rate} | {pf} | {tp1} | {tp2} | {avg} |'.format(
                segment=row['segment'],
                trades=row['trades'],
                days=row['days'],
                net=fmt_money(row['net_usd']),
                gross_pts=fmt_pts(row['gross_contract_points']),
                net_pts=fmt_pts(row['net_point_equiv']),
                trade_dd=fmt_money(row['trade_max_dd_usd']),
                daily_dd=fmt_money(row['daily_max_dd_usd']),
                win_rate=fmt_pct(row['win_rate']),
                pf=fmt_num(row['profit_factor']),
                tp1=fmt_pct(row['tp1_rate']),
                tp2=fmt_pct(row['tp2_rate']),
                avg=fmt_money(row['avg_trade_usd']) if not math.isnan(row['avg_trade_usd']) else 'n/a',
            )
        )
    return '\n'.join(lines)


def simulate_policy(
    *,
    policy_name: str,
    keep_policy: Policy,
    adaptive: pd.DataFrame,
    raw_by_day: dict[date, pd.DataFrame],
    bias_by_date: dict[str, dict],
) -> tuple[list[SimLeg], int, int]:
    legs: list[SimLeg] = []
    skipped_by_policy = 0
    skipped_by_fill = 0

    for session_day in sorted(adaptive['Date'].unique()):
        grp = adaptive[adaptive['Date'] == session_day].sort_values('_row_order')
        day_raw = raw_by_day.get(session_day)
        if day_raw is None or day_raw.empty:
            skipped_by_fill += len(grp)
            continue
        rth = so.rth_slice(day_raw, session_day)
        if rth.empty:
            skipped_by_fill += len(grp)
            continue

        prior_exit_ts: pd.Timestamp | None = None
        bias_info = bias_by_date.get(session_day.isoformat(), {})
        monthly_bias = str(bias_info.get('monthly_bias', 'missing'))

        for _, row in grp.iterrows():
            regime = str(row['Regime']).strip().lower()
            direction = str(row['Trade_Direction']).strip()
            alignment = classify_alignment(monthly_bias, direction)
            if not keep_policy(regime, alignment):
                skipped_by_policy += 1
                continue

            rh = float(row['Range_High'])
            rl = float(row['Range_Low'])
            rv = float(row['Range'])
            csv_net = float(row['Net_$'])

            pm = so.trade_params(regime, direction, rh, rl, rv)
            if pm is None:
                skipped_by_fill += 1
                continue

            sub = so.path_after_prior(rth, session_day, prior_exit_ts)
            if sub.empty:
                skipped_by_fill += 1
                continue

            fill_ts, _entry_px = so.resolve_fill(regime, direction, sub, rh, rl)
            if fill_ts is None:
                skipped_by_fill += 1
                continue

            net_usd, tp_lab, exit_ts, h1, h2, _rf = so.simulate_scale_out_leg(
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
            if exit_ts is None:
                skipped_by_fill += 1
                continue

            prior_exit_ts = exit_ts
            gross_pts = (net_usd + SCALEOUT_FEE_PER_LEG) / MNQ_DOLLARS_PER_POINT
            legs.append(
                SimLeg(
                    policy=policy_name,
                    date_iso=session_day.isoformat(),
                    row_order=int(row['_row_order']),
                    regime=regime,
                    direction=direction,
                    monthly_bias=monthly_bias,
                    bias_alignment=alignment,
                    csv_net_1ct=csv_net,
                    scaleout_net_2ct=net_usd,
                    gross_contract_points=gross_pts,
                    net_point_equiv=net_usd / MNQ_DOLLARS_PER_POINT,
                    tp_style=tp_lab,
                    hit_tp1=bool(h1),
                    hit_tp2=bool(h2),
                    fill_ts=pd.Timestamp(fill_ts).isoformat(),
                    exit_ts=pd.Timestamp(exit_ts).isoformat(),
                )
            )

    return legs, skipped_by_policy, skipped_by_fill


def write_report(
    path: Path,
    legs_path: Path,
    summary_path: Path,
    skip_path: Path,
    summary_rows: list[dict],
) -> None:
    by_segment = {row['segment']: row for row in summary_rows}
    base = by_segment['baseline']
    base_v2b = by_segment['baseline_v2b_only_split']
    base_v2d = by_segment['baseline_v2d_only_split']
    outside = by_segment['monthly_outside_only']
    v2d_aligned = by_segment['v2d_aligned_only_v2b_unchanged']

    lines = [
        '# Adaptive 50/150 scaleout monthly-bias re-sim',
        '',
        'This is the stricter version of the monthly-bias test: the gate is applied before each candidate leg is simulated, so same-day chaining uses only trades that would actually have been taken.',
        '',
        '## Headline',
        '',
        f'- Baseline: {base["trades"]:,} legs, {fmt_money(base["net_usd"])}, trade DD {fmt_money(base["trade_max_dd_usd"])}, gross contract-points {fmt_pts(base["gross_contract_points"])}.',
        f'- Baseline split: v2b alone was {fmt_money(base_v2b["net_usd"])} with {fmt_money(base_v2b["trade_max_dd_usd"])} DD; v2d alone was {fmt_money(base_v2d["net_usd"])} with {fmt_money(base_v2d["trade_max_dd_usd"])} DD.',
        f'- Monthly outside-only: {outside["trades"]:,} legs, {fmt_money(outside["net_usd"])}, trade DD {fmt_money(outside["trade_max_dd_usd"])}, gross contract-points {fmt_pts(outside["gross_contract_points"])}.',
        f'- Best non-diagnostic split here: keep v2b unchanged, require v2d to align with monthly bias: {v2d_aligned["trades"]:,} legs, {fmt_money(v2d_aligned["net_usd"])}, trade DD {fmt_money(v2d_aligned["trade_max_dd_usd"])}, gross contract-points {fmt_pts(v2d_aligned["gross_contract_points"])}.',
        '',
        '## Metrics',
        '',
        metric_table(summary_rows),
        '',
        '## Outputs',
        '',
        f'- Re-sim legs: [{legs_path.name}]({legs_path.name})',
        f'- Summary CSV: [{summary_path.name}]({summary_path.name})',
        f'- Skip audit: [{skip_path.name}]({skip_path.name})',
        '',
        '## Notes',
        '',
        '- The monthly state is still causal: trade day uses the prior daily close versus the first 3 daily bars of the month.',
        '- This does not change the scaleout stop/target mechanics; it only gates whether a candidate adaptive leg is allowed to enter.',
        '',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--adaptive-csv', type=Path, default=ADAPTIVE_CSV)
    ap.add_argument('--daily', type=Path, default=DAILY_CSV)
    ap.add_argument('--1m', dest='m1', type=Path, default=M1_CSV)
    ap.add_argument('--out', type=Path, default=OUT_ROOT)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    adaptive = pd.read_csv(args.adaptive_csv)
    adaptive['_row_order'] = range(len(adaptive))
    adaptive['Date'] = pd.to_datetime(adaptive['Date']).dt.date
    adaptive = adaptive.sort_values(['Date', '_row_order'])

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    bias = build_monthly_bias(daily)
    bias_by_date = bias.set_index('Date').to_dict(orient='index')

    need_dates = set(adaptive['Date'].unique())
    raw = so.ann.load_1m_for_dates(str(args.m1), min(need_dates), max(need_dates), need_dates)
    raw = so.ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    raw_by_day = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    all_legs: list[SimLeg] = []
    skip_rows: list[dict] = []
    summary_rows: list[dict] = []
    policy_frames: dict[str, pd.DataFrame] = {}
    for name, keep_policy in policy_map().items():
        legs, skipped_by_policy, skipped_by_fill = simulate_policy(
            policy_name=name,
            keep_policy=keep_policy,
            adaptive=adaptive,
            raw_by_day=raw_by_day,
            bias_by_date=bias_by_date,
        )
        all_legs.extend(legs)
        frame = pd.DataFrame([leg.__dict__ for leg in legs])
        policy_frames[name] = frame
        summary_rows.append(metrics(name, frame))
        skip_rows.append({
            'policy': name,
            'legs_simulated': len(legs),
            'skipped_by_policy': skipped_by_policy,
            'skipped_by_fill_or_data': skipped_by_fill,
        })

    baseline_frame = policy_frames.get('baseline', pd.DataFrame())
    if not baseline_frame.empty:
        summary_rows.insert(1, metrics('baseline_v2b_only_split', baseline_frame[baseline_frame['regime'] == 'v2b']))
        summary_rows.insert(2, metrics('baseline_v2d_only_split', baseline_frame[baseline_frame['regime'] == 'v2d']))

    legs_path = args.out / 'adaptive_scaleout_monthly_bias_resim_legs.csv'
    summary_path = args.out / 'adaptive_scaleout_monthly_bias_resim_summary.csv'
    skip_path = args.out / 'adaptive_scaleout_monthly_bias_resim_skips.csv'
    report_path = args.out / 'ADAPTIVE_SCALEOUT_MONTHLY_BIAS_RESIM.md'

    pd.DataFrame([leg.__dict__ for leg in all_legs]).to_csv(legs_path, index=False)
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    pd.DataFrame(skip_rows).to_csv(skip_path, index=False)
    write_report(report_path, legs_path, summary_path, skip_path, summary_rows)

    print(metric_table(summary_rows))
    print(f'Wrote {legs_path}')
    print(f'Wrote {summary_path}')
    print(f'Wrote {skip_path}')
    print(f'Wrote {report_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
