#!/usr/bin/env python3
"""Filter adaptive 50/150 v2b-only scaleout by prior-day yearly ORB state.

Primary filter:
- Jan-Mar defines the yearly opening range.
- A trade is eligible only from Apr-Dec, after the range is complete.
- The prior trading day must have traded outside the yearly range:
  high > yearly OR high for bullish bias, or low < yearly OR low for bearish bias.
- Skip ambiguous prior days that traded both above and below the yearly range.
- Keep only v2b scaleout legs whose direction matches that prior-day yearly bias.

This script filters already-resimulated scaleout legs. It does not alter fills.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import argparse
import math

import pandas as pd


POTIONS = Path('/home/tester/hsm/potions')


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
            out[year] = {'yearly_or_high': high, 'yearly_or_low': low, 'yearly_or_range': high - low}
    return out


def prior_day_bias_map(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy().sort_values('date').reset_index(drop=True)
    work['date'] = pd.to_datetime(work['date'])
    work['trade_date'] = work['date'].dt.date
    work['year'] = work['date'].dt.year
    work['month'] = work['date'].dt.month
    ranges = yearly_ranges(work)

    rows: list[dict] = []
    for idx, row in work.iterrows():
        d = row['trade_date']
        year = int(row['year'])
        rng = ranges.get(year)
        if idx == 0 or rng is None or int(row['month']) <= 3:
            rows.append({'date_iso': d.isoformat(), 'yearly_bias': 'none', 'yearly_bias_source': 'unavailable'})
            continue

        prev = work.iloc[idx - 1]
        prev_high = float(prev['high'])
        prev_low = float(prev['low'])
        prev_close = float(prev['close'])
        above = prev_high > rng['yearly_or_high']
        below = prev_low < rng['yearly_or_low']
        close_above = prev_close > rng['yearly_or_high']
        close_below = prev_close < rng['yearly_or_low']

        if above and below:
            bias = 'ambiguous'
        elif above:
            bias = 'Long'
        elif below:
            bias = 'Short'
        else:
            bias = 'inside'

        if close_above and close_below:
            close_bias = 'ambiguous'
        elif close_above:
            close_bias = 'Long'
        elif close_below:
            close_bias = 'Short'
        else:
            close_bias = 'inside'

        rows.append(
            {
                'date_iso': d.isoformat(),
                'yearly_bias': bias,
                'yearly_close_bias': close_bias,
                'yearly_bias_source': 'prior_trading_day',
                'prior_date': pd.Timestamp(prev['date']).date().isoformat(),
                'prior_high': prev_high,
                'prior_low': prev_low,
                'prior_close': prev_close,
                **rng,
            }
        )
    return pd.DataFrame(rows)


def load_legs(path: Path, market: str) -> pd.DataFrame:
    legs = pd.read_csv(path)
    if market.upper() == 'MNQ':
        legs = legs[legs.get('regime', 'v2b').astype(str).eq('v2b')].copy()
        legs['net_usd'] = pd.to_numeric(legs['scaleout_net_2ct'], errors='coerce').fillna(0.0)
    else:
        segment = legs.get('segment', '').astype(str)
        legs = legs[segment.str.contains('v2b[-_]only', case=False, regex=True, na=False)].copy()
        legs['net_usd'] = pd.to_numeric(legs['net_usd'], errors='coerce').fillna(0.0)
    legs['date_iso'] = pd.to_datetime(legs['date_iso']).dt.date.astype(str)
    legs['direction'] = legs['direction'].astype(str)
    return legs


def max_dd(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def summarize(tag: str, legs: pd.DataFrame) -> dict:
    net = pd.to_numeric(legs['net_usd'], errors='coerce').fillna(0.0)
    by_day = legs.assign(_net=net).groupby('date_iso')['_net'].sum().sort_index()
    out = {
        'segment': tag,
        'legs': int(len(legs)),
        'days': int(legs['date_iso'].nunique()) if not legs.empty else 0,
        'net_usd': float(net.sum()),
        'trade_dd_usd': max_dd(net),
        'daily_dd_usd': max_dd(by_day),
        'win_rate': float((net > 0).mean()) if len(net) else math.nan,
        'profit_factor': profit_factor(net),
        'avg_trade': float(net.mean()) if len(net) else math.nan,
    }
    if 'hit_tp1' in legs.columns:
        out['tp1_rate'] = float(legs['hit_tp1'].astype(str).str.lower().isin(['true', '1']).mean()) if len(legs) else math.nan
    if 'hit_tp2' in legs.columns:
        out['tp2_rate'] = float(legs['hit_tp2'].astype(str).str.lower().isin(['true', '1']).mean()) if len(legs) else math.nan
    return out


def run(args: argparse.Namespace) -> None:
    market = args.market.upper()
    daily = pd.read_csv(args.daily, parse_dates=['date'])
    legs = load_legs(args.legs, market)
    bias = prior_day_bias_map(daily)
    tagged = legs.merge(bias, on='date_iso', how='left')

    primary = tagged[(tagged['yearly_bias'].eq(tagged['direction']))].copy()
    close_only = tagged[(tagged['yearly_close_bias'].eq(tagged['direction']))].copy()
    outside_any = tagged[tagged['yearly_bias'].isin(['Long', 'Short'])].copy()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    primary_path = args.out_dir / f'{market.lower()}_adaptive_v2b_scaleout_yearly_orb_bias.csv'
    close_path = args.out_dir / f'{market.lower()}_adaptive_v2b_scaleout_yearly_orb_close_bias.csv'
    tagged_path = args.out_dir / f'{market.lower()}_adaptive_v2b_scaleout_yearly_orb_tagged.csv'
    summary_path = args.out_dir / f'{market.lower()}_adaptive_v2b_scaleout_yearly_orb_bias_summary.csv'

    primary.to_csv(primary_path, index=False)
    close_only.to_csv(close_path, index=False)
    tagged.to_csv(tagged_path, index=False)
    pd.DataFrame(
        [
            summarize('baseline v2b-only adaptive scaleout', legs),
            summarize('prior-day traded outside yearly ORB, aligned', primary),
            summarize('prior-day close outside yearly ORB, aligned', close_only),
            summarize('prior-day traded outside yearly ORB, no direction filter', outside_any),
        ]
    ).to_csv(summary_path, index=False)

    print(f'{market} baseline legs={len(legs)} net=${legs["net_usd"].sum():,.2f}')
    print(f'{market} yearly-bias aligned legs={len(primary)} net=${primary["net_usd"].sum():,.2f}')
    print(f'Wrote {summary_path}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', required=True, choices=['MNQ', 'NQ'])
    ap.add_argument('--daily', type=Path, required=True)
    ap.add_argument('--legs', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, default=POTIONS / 'mnq' / 'case_studies' / 'yearly_orb_v2b_bias_filter')
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
