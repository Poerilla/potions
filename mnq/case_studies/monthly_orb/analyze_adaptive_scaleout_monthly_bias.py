#!/usr/bin/env python3
"""Measure monthly ORB bias as a filter for adaptive 50/150 scaleout trades.

Bias definition is causal at the RTH open:
  - monthly OR = first 3 daily bars of the calendar month
  - current session bias uses the prior daily close
  - prior close above monthly OR high = bullish
  - prior close below monthly OR low = bearish
  - prior close inside the monthly OR = neutral/skip

The scaleout CSV is produced by ``potions/mnq/v2d/run_adaptive_50_150_scaleout.py``.
It contains one row per successfully replayed adaptive 50/150 leg.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

import pandas as pd


MNQ_ROOT = Path('/home/tester/hsm/potions/mnq')
DAILY_CSV = MNQ_ROOT / 'mnq_daily.csv'
SCALEOUT_CSV = MNQ_ROOT / 'v2d' / 'adaptive_50_150_scaleout_legs.csv'
OUT_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb'

MNQ_DOLLARS_PER_POINT = 2.0
SCALEOUT_FEE_PER_LEG = 3.0  # two MNQ closed at $1.50 RT each


def fmt_money(value: float) -> str:
    return f'${value:,.2f}'


def fmt_pts(value: float) -> str:
    return f'{value:,.2f}'


def fmt_pct(value: float) -> str:
    if math.isnan(value):
        return 'n/a'
    return f'{value:.2%}'


def fmt_num(value: float) -> str:
    if math.isnan(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.2f}'


def max_drawdown(values: Iterable[float]) -> float:
    series = pd.Series(list(values), dtype=float)
    if series.empty:
        return 0.0
    equity = series.cumsum()
    return float((equity - equity.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def build_monthly_bias(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.sort_values('date').copy()
    daily['date'] = pd.to_datetime(daily['date']).dt.date.astype(str)
    daily['month'] = pd.to_datetime(daily['date']).dt.to_period('M')

    rows: list[dict] = []
    for period, month_bars in daily.groupby('month', sort=True):
        month_bars = month_bars.sort_values('date').reset_index(drop=True)
        if len(month_bars) < 3:
            for _, bar in month_bars.iterrows():
                rows.append({
                    'Date': bar['date'],
                    'monthly_or_period': str(period),
                    'monthly_or_high': math.nan,
                    'monthly_or_low': math.nan,
                    'monthly_or_range': math.nan,
                    'monthly_or_complete_date': None,
                    'prior_daily_close': math.nan,
                    'monthly_bias': 'building_range',
                    'monthly_bias_reason': 'fewer_than_3_daily_bars_in_month',
                })
            continue

        range_bars = month_bars.iloc[:3]
        or_high = float(range_bars['high'].max())
        or_low = float(range_bars['low'].min())
        or_range = or_high - or_low
        complete_date = str(range_bars.iloc[-1]['date'])

        for i, bar in month_bars.iterrows():
            prev_close = float(month_bars.iloc[i - 1]['close']) if i > 0 else math.nan
            if i < 3:
                bias = 'building_range'
                reason = 'first_3_monthly_or_days_not_complete_for_open'
            elif prev_close > or_high:
                bias = 'bullish'
                reason = 'prior_close_above_monthly_or_high'
            elif prev_close < or_low:
                bias = 'bearish'
                reason = 'prior_close_below_monthly_or_low'
            else:
                bias = 'neutral'
                reason = 'prior_close_inside_monthly_or'

            rows.append({
                'Date': str(bar['date']),
                'monthly_or_period': str(period),
                'monthly_or_high': or_high,
                'monthly_or_low': or_low,
                'monthly_or_range': or_range,
                'monthly_or_complete_date': complete_date,
                'prior_daily_close': prev_close,
                'monthly_bias': bias,
                'monthly_bias_reason': reason,
            })

    return pd.DataFrame(rows)


def classify_alignment(row: pd.Series) -> str:
    bias = row.get('monthly_bias')
    direction = row.get('direction')
    if bias == 'bullish' and direction == 'Long':
        return 'aligned'
    if bias == 'bearish' and direction == 'Short':
        return 'aligned'
    if bias == 'bullish' and direction == 'Short':
        return 'opposed'
    if bias == 'bearish' and direction == 'Long':
        return 'opposed'
    if bias in {'neutral', 'building_range'}:
        return bias
    return 'missing'


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
            'median_trade_usd': math.nan,
            'tp1_rate': math.nan,
            'tp2_rate': math.nan,
        }

    work = rows.sort_values(['Date', '_row_order']).copy()
    pnl = work['scaleout_net_2ct'].astype(float)
    daily = work.groupby('Date', sort=True)['scaleout_net_2ct'].sum()
    return {
        'segment': label,
        'trades': int(len(work)),
        'days': int(work['Date'].nunique()),
        'net_usd': float(pnl.sum()),
        'gross_contract_points': float(work['gross_contract_points'].sum()),
        'net_point_equiv': float(work['net_point_equiv'].sum()),
        'trade_max_dd_usd': max_drawdown(pnl),
        'daily_max_dd_usd': max_drawdown(daily),
        'win_rate': float((pnl > 0).mean()),
        'profit_factor': profit_factor(pnl),
        'avg_trade_usd': float(pnl.mean()),
        'median_trade_usd': float(pnl.median()),
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


def group_table(rows: pd.DataFrame, group_cols: list[str]) -> str:
    grouped = (
        rows.groupby(group_cols, dropna=False)
        .agg(
            trades=('scaleout_net_2ct', 'size'),
            days=('Date', 'nunique'),
            net_usd=('scaleout_net_2ct', 'sum'),
            gross_contract_points=('gross_contract_points', 'sum'),
            win_rate=('scaleout_net_2ct', lambda x: float((x > 0).mean())),
            avg_trade_usd=('scaleout_net_2ct', 'mean'),
            tp2_rate=('hit_tp2', 'mean'),
        )
        .reset_index()
        .sort_values(['net_usd', 'trades'], ascending=[False, False])
    )
    headers = group_cols + [
        'trades',
        'days',
        'net_usd',
        'gross_contract_points',
        'win_rate',
        'avg_trade_usd',
        'tp2_rate',
    ]
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |',
    ]
    for _, row in grouped.iterrows():
        cells = []
        for col in headers:
            val = row[col]
            if col == 'net_usd' or col == 'avg_trade_usd':
                cells.append(fmt_money(float(val)))
            elif col == 'gross_contract_points':
                cells.append(fmt_pts(float(val)))
            elif col == 'win_rate' or col == 'tp2_rate':
                cells.append(fmt_pct(float(val)))
            else:
                cells.append(str(val))
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def write_markdown(
    out_path: Path,
    annotated_path: Path,
    bias_path: Path,
    summary_path: Path,
    summary_rows: list[dict],
    annotated: pd.DataFrame,
) -> None:
    by_segment = {row['segment']: row for row in summary_rows}
    base = by_segment['full adaptive scaleout baseline']
    outside = by_segment['full scaleout, monthly outside only']
    aligned = by_segment['full scaleout, monthly aligned only']
    v2b_outside = by_segment['full scaleout, v2b outside only; v2d unchanged']
    v2d_aligned = by_segment['full scaleout, v2d aligned only; v2b unchanged']
    regime_specific = by_segment['diagnostic: v2b opposed only + v2d aligned only']

    outside_net_delta = outside['net_usd'] - base['net_usd']
    outside_dd_delta = outside['trade_max_dd_usd'] - base['trade_max_dd_usd']
    outside_point_delta = outside['gross_contract_points'] - base['gross_contract_points']
    outside_trade_cut = base['trades'] - outside['trades']

    aligned_net_delta = aligned['net_usd'] - base['net_usd']
    v2b_outside_net_delta = v2b_outside['net_usd'] - base['net_usd']
    v2d_aligned_net_delta = v2d_aligned['net_usd'] - base['net_usd']
    regime_specific_net_delta = regime_specific['net_usd'] - base['net_usd']

    kept_outside = annotated[annotated['bias_alignment'].isin(['aligned', 'opposed'])]
    dropped_outside = annotated[~annotated['bias_alignment'].isin(['aligned', 'opposed'])]

    report = [
        '# Adaptive 50/150 scaleout vs monthly ORB bias',
        '',
        'This applies the causal monthly ORB state to the exported 2-contract adaptive 50/150 scaleout legs.',
        '',
        '- Monthly OR = first 3 daily bars of the calendar month.',
        '- Trade-day state uses the prior daily close only.',
        '- `outside only` means prior close was above the monthly OR high or below the monthly OR low; direction alignment is not required.',
        '- `aligned only` means Long only in bullish monthly state and Short only in bearish monthly state.',
        '',
        '## Headline',
        '',
        f'- Baseline scaleout: {base["trades"]:,} legs, {fmt_money(base["net_usd"])}, trade DD {fmt_money(base["trade_max_dd_usd"])}, daily DD {fmt_money(base["daily_max_dd_usd"])}.',
        f'- Monthly outside-only: kept {outside["trades"]:,} legs and removed {outside_trade_cut:,}; net changed by {fmt_money(outside_net_delta)} and gross contract-points changed by {fmt_pts(outside_point_delta)}.',
        f'- Outside-only trade DD changed by {fmt_money(outside_dd_delta)}; daily DD is {fmt_money(outside["daily_max_dd_usd"])}.',
        f'- Direction-aligned-only net changed by {fmt_money(aligned_net_delta)}.',
        f'- Filtering only v2b by outside state while leaving v2d unchanged changed net by {fmt_money(v2b_outside_net_delta)}.',
        f'- Filtering only v2d to monthly-aligned rows while leaving v2b unchanged changed net by {fmt_money(v2d_aligned_net_delta)}.',
        f'- Diagnostic regime-specific state selection, v2b opposed plus v2d aligned, changed net by {fmt_money(regime_specific_net_delta)}.',
        '',
        '## Metrics',
        '',
        metric_table(summary_rows),
        '',
        '## Kept outside-only rows',
        '',
        group_table(kept_outside, ['regime', 'bias_alignment', 'monthly_bias', 'direction']) if not kept_outside.empty else 'No outside-only rows.',
        '',
        '## Dropped by outside-only filter',
        '',
        group_table(dropped_outside, ['regime', 'bias_alignment', 'monthly_bias', 'direction']) if not dropped_outside.empty else 'No dropped rows.',
        '',
        '## All rows by regime and monthly state',
        '',
        group_table(annotated, ['regime', 'bias_alignment', 'monthly_bias']) if not annotated.empty else 'No rows.',
        '',
        '## Outputs',
        '',
        f'- Annotated trades: [{annotated_path.name}]({annotated_path.name})',
        f'- Summary CSV: [{summary_path.name}]({summary_path.name})',
        f'- Daily monthly-bias table: [{bias_path.name}]({bias_path.name})',
        '',
        '## Notes',
        '',
        '- Gross contract-points are reconstructed from the scaleout net using the known $3 total fee per 2-contract leg.',
        '- This is a session-level filter study. It does not alter the intraday scaleout mechanics or rerun fills after removing earlier same-day legs.',
        '',
    ]
    out_path.write_text('\n'.join(report), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY_CSV)
    ap.add_argument('--scaleout', type=Path, default=SCALEOUT_CSV)
    ap.add_argument('--out', type=Path, default=OUT_ROOT)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    bias = build_monthly_bias(daily)

    trades = pd.read_csv(args.scaleout)
    trades['_row_order'] = range(len(trades))
    trades['Date'] = pd.to_datetime(trades['date_iso']).dt.date.astype(str)
    trades['regime'] = trades['regime'].astype(str).str.lower()
    trades['direction'] = trades['direction'].astype(str)
    trades['scaleout_net_2ct'] = trades['scaleout_net_2ct'].astype(float)
    trades['gross_contract_points'] = (
        trades['scaleout_net_2ct'] + SCALEOUT_FEE_PER_LEG
    ) / MNQ_DOLLARS_PER_POINT
    trades['net_point_equiv'] = trades['scaleout_net_2ct'] / MNQ_DOLLARS_PER_POINT
    trades['hit_tp1'] = trades['hit_tp1'].astype(bool)
    trades['hit_tp2'] = trades['hit_tp2'].astype(bool)

    annotated = trades.merge(bias, on='Date', how='left')
    annotated['monthly_bias'] = annotated['monthly_bias'].fillna('missing')
    annotated['bias_alignment'] = annotated.apply(classify_alignment, axis=1)
    annotated['monthly_outside'] = annotated['bias_alignment'].isin(['aligned', 'opposed'])
    annotated['monthly_aligned'] = annotated['bias_alignment'] == 'aligned'
    annotated['monthly_opposed'] = annotated['bias_alignment'] == 'opposed'

    outside = annotated[annotated['monthly_outside']].copy()
    aligned = annotated[annotated['monthly_aligned']].copy()
    opposed = annotated[annotated['monthly_opposed']].copy()
    inside = annotated[~annotated['monthly_outside']].copy()

    v2b_outside_full = annotated[(annotated['regime'] != 'v2b') | annotated['monthly_outside']].copy()
    v2b_aligned_full = annotated[(annotated['regime'] != 'v2b') | annotated['monthly_aligned']].copy()
    v2b_opposed_full = annotated[(annotated['regime'] != 'v2b') | annotated['monthly_opposed']].copy()
    v2d_outside_full = annotated[(annotated['regime'] != 'v2d') | annotated['monthly_outside']].copy()
    v2d_aligned_full = annotated[(annotated['regime'] != 'v2d') | annotated['monthly_aligned']].copy()
    v2d_opposed_full = annotated[(annotated['regime'] != 'v2d') | annotated['monthly_opposed']].copy()
    regime_specific_best_state = annotated[
        ((annotated['regime'] == 'v2b') & annotated['monthly_opposed'])
        | ((annotated['regime'] == 'v2d') & annotated['monthly_aligned'])
    ].copy()

    summary_rows = [
        metrics('full adaptive scaleout baseline', annotated),
        metrics('full scaleout, monthly outside only', outside),
        metrics('full scaleout, monthly aligned only', aligned),
        metrics('full scaleout, monthly opposed only', opposed),
        metrics('full scaleout, monthly neutral/building only', inside),
        metrics('full scaleout, v2b outside only; v2d unchanged', v2b_outside_full),
        metrics('full scaleout, v2b aligned only; v2d unchanged', v2b_aligned_full),
        metrics('full scaleout, v2b opposed only; v2d unchanged', v2b_opposed_full),
        metrics('full scaleout, v2d outside only; v2b unchanged', v2d_outside_full),
        metrics('full scaleout, v2d aligned only; v2b unchanged', v2d_aligned_full),
        metrics('full scaleout, v2d opposed only; v2b unchanged', v2d_opposed_full),
        metrics('diagnostic: v2b opposed only + v2d aligned only', regime_specific_best_state),
        metrics('v2b baseline', annotated[annotated['regime'] == 'v2b']),
        metrics('v2b monthly outside only', annotated[(annotated['regime'] == 'v2b') & annotated['monthly_outside']]),
        metrics('v2b monthly aligned only', annotated[(annotated['regime'] == 'v2b') & annotated['monthly_aligned']]),
        metrics('v2b monthly opposed only', annotated[(annotated['regime'] == 'v2b') & annotated['monthly_opposed']]),
        metrics('v2d baseline', annotated[annotated['regime'] == 'v2d']),
        metrics('v2d monthly outside only', annotated[(annotated['regime'] == 'v2d') & annotated['monthly_outside']]),
        metrics('v2d monthly aligned only', annotated[(annotated['regime'] == 'v2d') & annotated['monthly_aligned']]),
        metrics('v2d monthly opposed only', annotated[(annotated['regime'] == 'v2d') & annotated['monthly_opposed']]),
    ]

    annotated_path = args.out / 'adaptive_scaleout_monthly_bias_annotated.csv'
    bias_path = args.out / 'monthly_bias_by_day.csv'
    summary_path = args.out / 'adaptive_scaleout_monthly_bias_summary.csv'
    md_path = args.out / 'ADAPTIVE_SCALEOUT_MONTHLY_BIAS.md'

    annotated.to_csv(annotated_path, index=False)
    bias.to_csv(bias_path, index=False)
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    write_markdown(md_path, annotated_path, bias_path, summary_path, summary_rows, annotated)

    print(metric_table(summary_rows))
    print(f'Wrote {annotated_path}')
    print(f'Wrote {bias_path}')
    print(f'Wrote {summary_path}')
    print(f'Wrote {md_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
