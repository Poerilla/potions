#!/usr/bin/env python3
"""Measure monthly ORB bias as a filter for adaptive v2b child trades.

Bias definition is causal at the RTH open:
  - monthly OR = first 3 daily bars of the calendar month
  - current session bias uses the prior daily close
  - prior close above monthly OR high = bullish
  - prior close below monthly OR low = bearish
  - prior close inside the monthly OR = neutral/skip
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import argparse
import math

import pandas as pd


MNQ_ROOT = Path('/home/tester/hsm/potions/mnq')
DAILY_CSV = MNQ_ROOT / 'mnq_daily.csv'
ADAPTIVE_CHILD_CSV = MNQ_ROOT / 'v2d' / 'mnq_orb_results_adaptive_50_150_child_3max.csv'
OUT_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb'


def fmt_money(value: float) -> str:
    return f'${value:,.2f}'


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


def metrics(label: str, rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {
            'segment': label,
            'trades': 0,
            'days': 0,
            'net_usd': 0.0,
            'trade_max_dd_usd': 0.0,
            'daily_max_dd_usd': 0.0,
            'win_rate': math.nan,
            'profit_factor': math.nan,
            'avg_trade_usd': math.nan,
            'median_trade_usd': math.nan,
        }

    work = rows.sort_values(['entry_dt', 'Date', 'Trade_Direction']).copy()
    pnl = work['Net_$'].astype(float)
    daily = work.groupby('Date', sort=True)['Net_$'].sum()
    return {
        'segment': label,
        'trades': int(len(work)),
        'days': int(work['Date'].nunique()),
        'net_usd': float(pnl.sum()),
        'trade_max_dd_usd': max_drawdown(pnl),
        'daily_max_dd_usd': max_drawdown(daily),
        'win_rate': float((pnl > 0).mean()),
        'profit_factor': profit_factor(pnl),
        'avg_trade_usd': float(pnl.mean()),
        'median_trade_usd': float(pnl.median()),
    }


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
    direction = row.get('Trade_Direction')
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


def metric_table(rows: list[dict]) -> str:
    lines = [
        '| Segment | Trades | Days | Net | Trade DD | Daily DD | Win rate | PF | Avg/trade | Median |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        lines.append(
            '| {segment} | {trades} | {days} | {net} | {trade_dd} | {daily_dd} | {win_rate} | {pf} | {avg} | {median} |'.format(
                segment=row['segment'],
                trades=row['trades'],
                days=row['days'],
                net=fmt_money(row['net_usd']),
                trade_dd=fmt_money(row['trade_max_dd_usd']),
                daily_dd=fmt_money(row['daily_max_dd_usd']),
                win_rate=fmt_pct(row['win_rate']),
                pf=fmt_num(row['profit_factor']),
                avg=fmt_money(row['avg_trade_usd']) if not math.isnan(row['avg_trade_usd']) else 'n/a',
                median=fmt_money(row['median_trade_usd']) if not math.isnan(row['median_trade_usd']) else 'n/a',
            )
        )
    return '\n'.join(lines)


def group_table(rows: pd.DataFrame, group_cols: list[str]) -> str:
    grouped = (
        rows.groupby(group_cols, dropna=False)
        .agg(
            trades=('Net_$', 'size'),
            days=('Date', 'nunique'),
            net_usd=('Net_$', 'sum'),
            win_rate=('Net_$', lambda x: float((x > 0).mean())),
            avg_trade_usd=('Net_$', 'mean'),
        )
        .reset_index()
        .sort_values(['net_usd', 'trades'], ascending=[False, False])
    )
    headers = group_cols + ['trades', 'days', 'net_usd', 'win_rate', 'avg_trade_usd']
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
            elif col == 'win_rate':
                cells.append(fmt_pct(float(val)))
            else:
                cells.append(str(val))
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def write_markdown(
    out_path: Path,
    annotated_path: Path,
    bias_path: Path,
    summary_rows: list[dict],
    dropped_v2b: pd.DataFrame,
    kept_v2b: pd.DataFrame,
    annotated: pd.DataFrame,
) -> None:
    baseline_v2b = next(r for r in summary_rows if r['segment'] == 'v2b only baseline')
    aligned_v2b = next(r for r in summary_rows if r['segment'] == 'v2b aligned only')
    opposed_v2b = next(r for r in summary_rows if r['segment'] == 'v2b opposed only')
    outside_v2b = next(r for r in summary_rows if r['segment'] == 'v2b monthly outside only')
    full_base = next(r for r in summary_rows if r['segment'] == 'full adaptive baseline')
    full_filtered = next(r for r in summary_rows if r['segment'] == 'full adaptive, v2b monthly aligned only')
    full_outside = next(r for r in summary_rows if r['segment'] == 'full adaptive, v2b monthly outside only')

    v2b_drop_net = float(dropped_v2b['Net_$'].sum()) if not dropped_v2b.empty else 0.0
    v2b_trade_cut = baseline_v2b['trades'] - aligned_v2b['trades']
    v2b_net_delta = aligned_v2b['net_usd'] - baseline_v2b['net_usd']
    full_net_delta = full_filtered['net_usd'] - full_base['net_usd']
    full_outside_net_delta = full_outside['net_usd'] - full_base['net_usd']

    report = [
        '# Adaptive child vs monthly ORB bias',
        '',
        'Bias rule used here is causal: after the first 3 daily bars of a month, the next RTH session uses the prior daily close versus that monthly opening range.',
        '',
        '- Prior close above monthly OR high: bullish bias, keep Long v2b trades.',
        '- Prior close below monthly OR low: bearish bias, keep Short v2b trades.',
        '- Prior close inside the monthly OR, or while the range is still building: skip v2b trades.',
        '- v2d rows are left unchanged in the full-adaptive comparison; the filter is only applied to v2b rows.',
        '',
        '## Headline',
        '',
        f'- v2b-only filter kept {aligned_v2b["trades"]:,} of {baseline_v2b["trades"]:,} trades and removed {v2b_trade_cut:,}.',
        f'- Dropped v2b trades had combined net {fmt_money(v2b_drop_net)}.',
        f'- v2b-only net changed by {fmt_money(v2b_net_delta)}.',
        f'- Full adaptive net changed by {fmt_money(full_net_delta)} because v2d trades were retained.',
        f'- Opposed-only v2b trades were stronger than aligned-only in this sample: {fmt_money(opposed_v2b["net_usd"])} vs {fmt_money(aligned_v2b["net_usd"])}.',
        f'- The cleaner variant was not directional alignment; it was skipping v2b while the prior close was still inside the monthly range. That full-adaptive outside-only version changed net by {fmt_money(full_outside_net_delta)}.',
        '',
        '## Metrics',
        '',
        metric_table(summary_rows),
        '',
        '## Kept v2b trades by direction and bias',
        '',
        group_table(kept_v2b, ['Trade_Direction', 'monthly_bias']) if not kept_v2b.empty else 'No kept v2b trades.',
        '',
        '## Dropped v2b trades by filter state',
        '',
        group_table(dropped_v2b, ['bias_alignment', 'monthly_bias', 'Trade_Direction']) if not dropped_v2b.empty else 'No dropped v2b trades.',
        '',
        '## All adaptive rows by monthly bias',
        '',
        group_table(annotated, ['Regime', 'bias_alignment', 'monthly_bias']) if not annotated.empty else 'No adaptive rows.',
        '',
        '## Outputs',
        '',
        f'- Annotated trades: [{annotated_path.name}]({annotated_path.name})',
        f'- Daily monthly-bias table: [{bias_path.name}]({bias_path.name})',
        '',
    ]
    out_path.write_text('\n'.join(report), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY_CSV)
    ap.add_argument('--adaptive', type=Path, default=ADAPTIVE_CHILD_CSV)
    ap.add_argument('--out', type=Path, default=OUT_ROOT)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    bias = build_monthly_bias(daily)
    trades = pd.read_csv(args.adaptive)
    trades['Date'] = pd.to_datetime(trades['Date']).dt.date.astype(str)
    trades['entry_dt'] = pd.to_datetime(trades['Entry_Time'], errors='coerce')

    annotated = trades.merge(bias, on='Date', how='left')
    annotated['monthly_bias'] = annotated['monthly_bias'].fillna('missing')
    annotated['bias_alignment'] = annotated.apply(classify_alignment, axis=1)
    annotated['monthly_bias_keep_v2b'] = (annotated['Regime'] != 'v2b') | (annotated['bias_alignment'] == 'aligned')

    v2b = annotated[annotated['Regime'] == 'v2b'].copy()
    v2b_aligned = v2b[v2b['bias_alignment'] == 'aligned'].copy()
    v2b_opposed = v2b[v2b['bias_alignment'] == 'opposed'].copy()
    v2b_outside = v2b[v2b['bias_alignment'].isin(['aligned', 'opposed'])].copy()
    v2b_dropped = v2b[v2b['bias_alignment'] != 'aligned'].copy()
    full_filtered = annotated[annotated['monthly_bias_keep_v2b']].copy()
    full_opposed = annotated[(annotated['Regime'] != 'v2b') | (annotated['bias_alignment'] == 'opposed')].copy()
    full_outside = annotated[(annotated['Regime'] != 'v2b') | (annotated['bias_alignment'].isin(['aligned', 'opposed']))].copy()

    summary_rows = [
        metrics('full adaptive baseline', annotated),
        metrics('full adaptive, v2b monthly aligned only', full_filtered),
        metrics('full adaptive, v2b monthly opposed only', full_opposed),
        metrics('full adaptive, v2b monthly outside only', full_outside),
        metrics('v2b only baseline', v2b),
        metrics('v2b aligned only', v2b_aligned),
        metrics('v2b opposed only', v2b_opposed),
        metrics('v2b monthly outside only', v2b_outside),
        metrics('v2b dropped by monthly filter', v2b_dropped),
        metrics('v2d retained unchanged', annotated[annotated['Regime'] == 'v2d']),
    ]

    annotated_path = args.out / 'adaptive_child_monthly_bias_annotated.csv'
    bias_path = args.out / 'monthly_bias_by_day.csv'
    summary_path = args.out / 'adaptive_child_monthly_bias_summary.csv'
    md_path = args.out / 'ADAPTIVE_CHILD_MONTHLY_BIAS.md'

    annotated.to_csv(annotated_path, index=False)
    bias.to_csv(bias_path, index=False)
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    write_markdown(md_path, annotated_path, bias_path, summary_rows, v2b_dropped, v2b_aligned, annotated)

    print(metric_table(summary_rows))
    print(f'Wrote {annotated_path}')
    print(f'Wrote {bias_path}')
    print(f'Wrote {summary_path}')
    print(f'Wrote {md_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
