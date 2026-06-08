"""
**v2b_m** — filter legacy v2b OCO legs (`mnq_orb_results_stops.csv`) for **long-only** setups:

**Monthly bias** (exclude neutral ``ambiguous`` / ``insufficient_data``):

- **Trade** only when bias is ``bullish_break`` → **Long** legs (opening-range breakout long from tier‑1 CSV).
- Optional ``include_hemisphere=True`` also allows ``hemisphere_long``. Default is **breaks only**; on pure
  hemisphere months without a break classification, v2b_m stays **flat**.
- **Bearish / short** legs are **not** part of v2b_m (removed — marginal vs long book).

**ORB vs prior calendar month high** (same prior month as ``plot_daily_prior_month_levels``;
``EPS_IDX_PT`` slack on index prices):

Opening-range breakout long is *aligned* if either:

- **Floor at/above prior-month high:** ``Range_Low >= pm_high − EPS``, OR
- **Ceiling at/below prior-month high (break up toward it):** ``Range_High <= pm_high + EPS``.

**TP success:** ``Result`` is ``Win`` or ``EOD-Win`` (profitable target path / settlement in favour on that leg).

No scaling — tier‑1 CSV only.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

MNQ_ROOT = Path(__file__).resolve().parents[2]

import sys

if str(MNQ_ROOT) not in sys.path:
    sys.path.insert(0, str(MNQ_ROOT))

from rules.monthly_opening_range_bias import monthly_orb_bias_for_session_date


def long_bias_buckets(*, include_hemisphere: bool = False) -> frozenset:
    b = {'bullish_break'}
    if include_hemisphere:
        b.add('hemisphere_long')
    return frozenset(b)


EPS_IDX_PT = 1.0  # MNQ index points — tweakable slack vs monthly extremes


def long_geometry_tags(rh: float, rl: float, pm_h: float) -> List[str]:
    if not np.isfinite(pm_h):
        return []
    tags: List[str] = []
    if rl >= pm_h - EPS_IDX_PT:
        tags.append('floor_above_pmh')
    if rh <= pm_h + EPS_IDX_PT:
        tags.append('ceiling_below_pmh')
    return tags


def long_geom_ok(rh: float, rl: float, pm_h: float) -> bool:
    return bool(long_geometry_tags(rh, rl, pm_h))


def geom_tag_long(rh: float, rl: float, pm_h: float) -> str:
    t = long_geometry_tags(rh, rl, pm_h)
    return '+'.join(t) if t else ''


def tp_hit(result: str) -> bool:
    r = str(result).strip()
    return r in ('Win', 'EOD-Win')


def qualify_v2b_m_legs(
    stops_csv: Path,
    daily: pd.DataFrame,
    pm_high: pd.Series,
    pm_low: pd.Series,
    *,
    bias_lookup: dict | None = None,
    include_hemisphere: bool = False,
) -> pd.DataFrame:
    """
    Qualified **Long** rows from ``stops_csv`` with extra columns
    ``bias_bucket``, ``pm_high``, ``pm_low``, ``geom_tag``, ``tp_hit``.

    Default ``include_hemisphere=False``: only ``bullish_break``; ``hemisphere_long`` months without that
    bucket stay flat.
    """
    bull_bins = long_bias_buckets(include_hemisphere=include_hemisphere)
    df = pd.read_csv(stops_csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date

    rows = []

    for _, row in df.iterrows():
        d = row['Date']
        ts = pd.Timestamp(d)
        if ts not in pm_high.index:
            continue
        pm_h = float(pm_high.loc[ts])
        pm_l = float(pm_low.loc[ts])
        bias = (
            bias_lookup[d]
            if bias_lookup is not None and d in bias_lookup
            else monthly_orb_bias_for_session_date(d, daily).bucket
        )
        if bias not in bull_bins:
            continue

        rh = float(row['Range_High'])
        rl = float(row['Range_Low'])
        direction = str(row['Trade_Direction']).strip()
        if direction != 'Long':
            continue
        if not long_geom_ok(rh, rl, pm_h):
            continue
        tag = geom_tag_long(rh, rl, pm_h)
        extra = {
            'bias_bucket': bias,
            'pm_high': pm_h,
            'pm_low': pm_l,
            'geom_tag': tag,
            'tp_hit': tp_hit(row['Result']),
        }
        rows.append({**row.to_dict(), **extra})

    return pd.DataFrame(rows)


def summary_stats(legs: pd.DataFrame) -> dict:
    def pack(tag: str, sub: pd.DataFrame) -> dict:
        if sub.empty:
            return {
                'tag': tag,
                'n': 0,
                'tp': 0,
                'wr': float('nan'),
                'sum_net': 0.0,
                'mean_net': 0.0,
            }
        net = sub['Net_$'].astype(float)
        tp = sub['tp_hit'].astype(bool)
        return {
            'tag': tag,
            'n': len(sub),
            'tp': int(tp.sum()),
            'wr': float(tp.mean() * 100) if len(sub) else float('nan'),
            'sum_net': float(net.sum()),
            'mean_net': float(net.mean()),
        }

    out = {'long_legs': pack('bullish_break [+ optional hemisphere_long] + long + pm_high_geom', legs)}
    if legs.empty:
        out['combined'] = {}
        return out

    by_day = legs.groupby('Date')['Net_$'].sum().sort_index()
    cum = by_day.cumsum()
    dd = float((cum.cummax() - cum).max())
    out['combined'] = {
        'n_legs': len(legs),
        'n_days': int(by_day.shape[0]),
        'sum_net': float(legs['Net_$'].astype(float).sum()),
        'tp_legs': int(legs['tp_hit'].sum()),
        'wr_legs': float(legs['tp_hit'].mean() * 100),
        'max_dd_daily_path': dd,
    }
    return out
