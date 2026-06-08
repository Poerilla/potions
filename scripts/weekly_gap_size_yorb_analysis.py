#!/usr/bin/env python3
"""Weekly gap size and yearly ORB alignment study.

Inputs are the weekly gap fill CSVs produced by hourly_gap_fill_analysis.py
and the market daily CSV.

Primary questions:
- What is a small / medium / big weekly gap for this instrument?
- How do fill rates change by gap size and direction?
- When a weekly gap aligns with the yearly ORB breakout state, how often
  does it still fill?

Alignment definitions:
- Open-state alignment: the 09:30 weekly open is outside the Jan-Mar yearly
  ORB and the gap direction matches that side. This is known at the weekly
  open.
- Prior-close alignment: the previous RTH close was already outside the
  Jan-Mar yearly ORB and the gap direction matches that side. This is stricter
  and known before the weekly open.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import argparse

import pandas as pd


def period_groups(daily: pd.DataFrame) -> Iterable[tuple[int, pd.DataFrame]]:
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    work['year'] = work['date'].dt.year
    work['month'] = work['date'].dt.month
    for year, sub in work.groupby('year', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if (sub['month'] <= 3).any() and (sub['month'] > 3).any():
            yield int(year), sub


def yearly_ranges(daily: pd.DataFrame) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for year, sub in period_groups(daily):
        rb = sub[sub['month'] <= 3]
        high = float(rb['high'].max())
        low = float(rb['low'].min())
        if high > low:
            out[year] = {
                'yearly_or_high': high,
                'yearly_or_low': low,
                'yearly_or_range': high - low,
            }
    return out


def state_from_price(px: float, rng: dict[str, float] | None, month: int) -> str:
    if rng is None:
        return 'NoRange'
    if month <= 3:
        return 'PreORB'
    if px > rng['yearly_or_high']:
        return 'Bullish'
    if px < rng['yearly_or_low']:
        return 'Bearish'
    return 'Inside'


def align_state(gap_bias: str, state: str) -> str:
    if state == 'Bullish' and gap_bias == 'Bullish':
        return 'Aligned'
    if state == 'Bearish' and gap_bias == 'Bearish':
        return 'Aligned'
    if state == 'Bullish' and gap_bias == 'Bearish':
        return 'Counter'
    if state == 'Bearish' and gap_bias == 'Bullish':
        return 'Counter'
    return state


def assign_size_buckets(work: pd.DataFrame, prefix: str, value_col: str) -> tuple[pd.DataFrame, dict[str, float]]:
    q33 = float(work[value_col].quantile(1 / 3))
    q66 = float(work[value_col].quantile(2 / 3))

    def bucket(value: float) -> str:
        if value <= q33:
            return 'Small'
        if value <= q66:
            return 'Medium'
        return 'Big'

    out = work.copy()
    out[f'{prefix}_size_bucket'] = out[value_col].map(bucket)
    return out, {f'{prefix}_small_max': q33, f'{prefix}_medium_max': q66}


def annotate_weekly_gaps(weekly_path: Path, daily_path: Path, market: str) -> tuple[pd.DataFrame, dict[str, float]]:
    weekly = pd.read_csv(weekly_path, parse_dates=['prev_close_date', 'open_date'])
    daily = pd.read_csv(daily_path, parse_dates=['date'])
    ranges = yearly_ranges(daily)

    work = weekly.copy()
    work['market'] = market.upper()
    work['prev_close_date'] = work['prev_close_date'].dt.date
    work['open_date'] = work['open_date'].dt.date
    work['open_year'] = pd.to_datetime(work['open_date']).dt.year.astype(int)
    work['open_month'] = pd.to_datetime(work['open_date']).dt.month.astype(int)
    work['gap_bias'] = work['gap_pts'].map(lambda x: 'Bullish' if float(x) > 0 else 'Bearish')
    work['abs_gap_pct_prev_close'] = work['abs_gap_pts'] / work['prev_close'].abs()

    yearly_highs: list[float | None] = []
    yearly_lows: list[float | None] = []
    yearly_ranges_out: list[float | None] = []
    prev_states: list[str] = []
    open_states: list[str] = []
    for _, row in work.iterrows():
        rng = ranges.get(int(row['open_year']))
        month = int(row['open_month'])
        yearly_highs.append(rng['yearly_or_high'] if rng else None)
        yearly_lows.append(rng['yearly_or_low'] if rng else None)
        yearly_ranges_out.append(rng['yearly_or_range'] if rng else None)
        prev_states.append(state_from_price(float(row['prev_close']), rng, month))
        open_states.append(state_from_price(float(row['open_px']), rng, month))

    work['yearly_or_high'] = yearly_highs
    work['yearly_or_low'] = yearly_lows
    work['yearly_or_range'] = yearly_ranges_out
    work['prev_close_yorb_state'] = prev_states
    work['open_yorb_state'] = open_states
    work['prev_close_yorb_alignment'] = [
        align_state(gap_bias, state) for gap_bias, state in zip(work['gap_bias'], work['prev_close_yorb_state'])
    ]
    work['open_yorb_alignment'] = [
        align_state(gap_bias, state) for gap_bias, state in zip(work['gap_bias'], work['open_yorb_state'])
    ]
    work['abs_gap_pct_yorb_range'] = work['abs_gap_pts'] / work['yearly_or_range']

    work, point_thresholds = assign_size_buckets(work, 'point', 'abs_gap_pts')
    work, pct_thresholds = assign_size_buckets(work, 'pct_prev_close', 'abs_gap_pct_prev_close')
    thresholds = {**point_thresholds, **pct_thresholds}
    return work, thresholds


def summarize(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = (
        df.groupby(group_cols, dropna=False, observed=True)
        .agg(
            gaps=('filled', 'size'),
            filled=('filled', 'sum'),
            fill_rate=('filled', 'mean'),
            not_filled=('filled', lambda s: int((pd.to_numeric(s) == 0).sum())),
            median_gap_pts=('abs_gap_pts', 'median'),
            avg_gap_pts=('abs_gap_pts', 'mean'),
            max_gap_pts=('abs_gap_pts', 'max'),
            median_gap_pct=('abs_gap_pct_prev_close', 'median'),
        )
        .reset_index()
    )
    return out


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return ''
    return f'{float(value) * 100:.1f}%'


def fmt_pts(value: float) -> str:
    if pd.isna(value):
        return ''
    return f'{float(value):.2f}'


def table_from_df(df: pd.DataFrame, columns: list[str], money_cols: set[str] | None = None) -> list[str]:
    if df.empty:
        return ['No rows.', '']
    money_cols = money_cols or set()
    lines = ['| ' + ' | '.join(columns) + ' |', '|' + '|'.join(['---'] * len(columns)) + '|']
    for _, row in df.iterrows():
        vals = []
        for col in columns:
            value = row[col]
            if col in {'fill_rate', 'median_gap_pct'}:
                vals.append(fmt_pct(value))
            elif col in money_cols or col.endswith('_pts') or col in {'gap_pts', 'abs_gap_pts'}:
                vals.append(fmt_pts(value))
            elif isinstance(value, float):
                vals.append(f'{value:.3f}')
            else:
                vals.append(str(value))
        lines.append('| ' + ' | '.join(vals) + ' |')
    lines.append('')
    return lines


def write_market_report(out_dir: Path, market: str, annotated: pd.DataFrame, thresholds: dict[str, float]) -> None:
    size = summarize(annotated, ['point_size_bucket'])
    size_dir = summarize(annotated, ['point_size_bucket', 'direction'])
    open_align = summarize(annotated, ['open_yorb_alignment'])
    prev_align = summarize(annotated, ['prev_close_yorb_alignment'])
    open_align_size = summarize(annotated, ['open_yorb_alignment', 'point_size_bucket'])
    aligned_unfilled = annotated[
        (annotated['open_yorb_alignment'] == 'Aligned') & (pd.to_numeric(annotated['filled']) == 0)
    ].copy()
    aligned_unfilled = aligned_unfilled.sort_values('abs_gap_pts', ascending=False)

    lines: list[str] = [
        f'# {market} Weekly Gap Size + Yearly ORB Alignment Study',
        '',
        'Definitions:',
        '',
        '- Small / medium / big are empirical terciles of this market\'s weekly absolute gap size.',
        '- Open-state alignment: the 09:30 weekly open is outside the Jan-Mar yearly ORB and the gap direction matches that side.',
        '- Prior-close alignment: the previous RTH close was already outside the Jan-Mar yearly ORB and the gap direction matches that side.',
        '- Fill means price traded back to the previous week\'s final RTH close before the end of that same week.',
        '',
        '## Size Thresholds',
        '',
        '| Bucket | Absolute Gap | Percent Of Prior Close |',
        '|---|---:|---:|',
        f'| Small | <= {thresholds["point_small_max"]:.2f} pts | <= {thresholds["pct_prev_close_small_max"] * 100:.3f}% |',
        f'| Medium | > {thresholds["point_small_max"]:.2f} and <= {thresholds["point_medium_max"]:.2f} pts | > {thresholds["pct_prev_close_small_max"] * 100:.3f}% and <= {thresholds["pct_prev_close_medium_max"] * 100:.3f}% |',
        f'| Big | > {thresholds["point_medium_max"]:.2f} pts | > {thresholds["pct_prev_close_medium_max"] * 100:.3f}% |',
        '',
        '## Fill Rate By Gap Size',
        '',
    ]
    lines.extend(table_from_df(size, ['point_size_bucket', 'gaps', 'filled', 'not_filled', 'fill_rate', 'median_gap_pts', 'avg_gap_pts', 'max_gap_pts']))
    lines.extend(['## Fill Rate By Gap Size And Direction', ''])
    lines.extend(table_from_df(size_dir, ['point_size_bucket', 'direction', 'gaps', 'filled', 'not_filled', 'fill_rate', 'median_gap_pts']))
    lines.extend(['## Yearly ORB Alignment At Weekly Open', ''])
    lines.extend(table_from_df(open_align, ['open_yorb_alignment', 'gaps', 'filled', 'not_filled', 'fill_rate', 'median_gap_pts']))
    lines.extend(['## Yearly ORB Alignment By Size', ''])
    lines.extend(table_from_df(open_align_size, ['open_yorb_alignment', 'point_size_bucket', 'gaps', 'filled', 'not_filled', 'fill_rate', 'median_gap_pts']))
    lines.extend(['## Stricter Prior-Close Alignment', ''])
    lines.extend(table_from_df(prev_align, ['prev_close_yorb_alignment', 'gaps', 'filled', 'not_filled', 'fill_rate', 'median_gap_pts']))

    lines.extend(
        [
            '## Unfilled Open-Aligned Gaps',
            '',
            f'Open-aligned weekly gaps that did not fill: **{len(aligned_unfilled)}**.',
            '',
        ]
    )
    if not aligned_unfilled.empty:
        show = aligned_unfilled.head(25)[
            [
                'open_date',
                'direction',
                'point_size_bucket',
                'gap_pts',
                'abs_gap_pts',
                'prev_close',
                'open_px',
                'open_yorb_state',
                'chart',
            ]
        ]
        lines.extend(table_from_df(show, list(show.columns)))
        if len(aligned_unfilled) > len(show):
            lines.extend([f'_Showing largest {len(show)} of {len(aligned_unfilled)}. See CSV for all rows._', ''])
    else:
        lines.extend(['No unfilled open-aligned gaps.', ''])

    lines.extend(
        [
            '## Files',
            '',
            '- `weekly_gap_size_yorb.csv`',
            '- `README.md`',
            '',
        ]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def write_cross_market(out_dir: Path, market_rows: list[dict]) -> None:
    df = pd.DataFrame(market_rows)
    lines = [
        '# Weekly Gap Size + Yearly ORB Alignment Cross-Market Summary',
        '',
        'Primary alignment is open-state alignment: the 09:30 weekly open is outside the Jan-Mar yearly ORB and the gap direction matches that side.',
        '',
        '| Market | Small Max | Medium Max | Weekly Gaps | Overall Fill | Open-Aligned Gaps | Open-Aligned Fill | Open-Aligned Not Filled | Big Open-Aligned Fill |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for _, row in df.iterrows():
        lines.append(
            f'| {row["market"]} | {row["small_max"]:.2f} | {row["medium_max"]:.2f} | '
            f'{int(row["gaps"])} | {fmt_pct(row["fill_rate"])} | {int(row["aligned_gaps"])} | '
            f'{fmt_pct(row["aligned_fill_rate"])} | {int(row["aligned_not_filled"])} | {fmt_pct(row["big_aligned_fill_rate"])} |'
        )
    lines.extend(
        [
            '',
            'Read: smaller weekly gaps fill most often; big gaps still fill often enough to investigate, but unfilled gaps cluster more heavily in the big bucket. Yearly ORB alignment does not make the gap immune to fills.',
            '',
            'Detailed market reports:',
            '',
            '- `mnq/case_studies/gap_analysis/weekly_gap_size_yorb/README.md`',
            '- `nq/case_studies/gap_analysis/weekly_gap_size_yorb/README.md`',
            '',
        ]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'WEEKLY_GAP_SIZE_YORB_SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')


def market_summary(market: str, annotated: pd.DataFrame, thresholds: dict[str, float]) -> dict:
    aligned = annotated[annotated['open_yorb_alignment'] == 'Aligned']
    big_aligned = aligned[aligned['point_size_bucket'] == 'Big']
    filled = pd.to_numeric(annotated['filled'])
    aligned_filled = pd.to_numeric(aligned['filled']) if not aligned.empty else pd.Series(dtype=float)
    big_aligned_filled = pd.to_numeric(big_aligned['filled']) if not big_aligned.empty else pd.Series(dtype=float)
    return {
        'market': market,
        'small_max': thresholds['point_small_max'],
        'medium_max': thresholds['point_medium_max'],
        'gaps': len(annotated),
        'fill_rate': float(filled.mean()) if len(filled) else 0.0,
        'aligned_gaps': len(aligned),
        'aligned_fill_rate': float(aligned_filled.mean()) if len(aligned_filled) else 0.0,
        'aligned_not_filled': int((aligned_filled == 0).sum()) if len(aligned_filled) else 0,
        'big_aligned_fill_rate': float(big_aligned_filled.mean()) if len(big_aligned_filled) else 0.0,
    }


def run_one(args: argparse.Namespace) -> dict:
    annotated, thresholds = annotate_weekly_gaps(args.weekly_csv, args.daily, args.market)
    args.out.mkdir(parents=True, exist_ok=True)
    annotated.to_csv(args.out / 'weekly_gap_size_yorb.csv', index=False)
    write_market_report(args.out, args.market.upper(), annotated, thresholds)
    return market_summary(args.market.upper(), annotated, thresholds)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', required=True)
    ap.add_argument('--weekly-csv', type=Path, required=True)
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cross-summary-out', type=Path)
    args = ap.parse_args()
    row = run_one(args)
    if args.cross_summary_out:
        write_cross_market(args.cross_summary_out, [row])
    print(
        f'{row["market"]}: weekly gaps={row["gaps"]}, aligned={row["aligned_gaps"]}, '
        f'aligned not filled={row["aligned_not_filled"]}'
    )
    print(f'Wrote {args.out / "README.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
