"""HP liq-run research: band-max fade entry + range-breakout sidecar plans.

Causality of chart levels (see ``CAUSALITY.md`` in the hub):

- **Bands (up/dn min/med/max ATR)** — known *before* month open: 6-month
  rolling means of prior months' path extremes only (no current-month peek).
- **Month open** — known at first bar of the month.
- **Band price levels** — known once month open + prior ATR are known
  (``open ± atr×mult``), i.e. from month open onward.
- **Liq side / p_liq / ext / 1R stop** — known only after the liquidity
  extreme prints in the first N NY days (``t_liq``).
- **Full envelope range** (all horizontals incl. SL) — known at ``t_liq``.

Variant A — **band-max fade**: liq sets direction; limit at dn-max (long) /
up-max (short); target month open; SL distance = liq-run size.

Variant B — **range breakout sidecar**: after ``t_liq``, range =
[min(levels), max(levels)]; 4h close outside → arm limit at boundary;
SL = 2×liq-run; target = range size; max 2 attempts after stops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    _band_from_working,
    collect_path_stats,
    rolling_band_from_paths,
)
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    FEATURES_CSV,
    _ny_ts,
    detect_liquidity_run,
    select_months,
)
from .quarterly_atr4_fade_broker import MARKETS

NY = "America/New_York"


def _utc_z(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def build_enriched_hp_plans(
    *,
    liq_days: int = 2,
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    smoke: int = 0,
) -> Dict[str, dict]:
    """HP months with liq geometry + both-side band prices + envelope range."""
    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)
    paths = collect_path_stats(spec)
    path_by = {(p.year, p.month): p for p in paths}

    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]] = {}
    for year, month, m0, m1 in month_windows(bars, None, None):
        win_by[(int(year), int(month))] = (m0, m1)

    feats = pd.read_csv(FEATURES_CSV)
    feats = feats[feats["market"].astype(str).str.upper() == "NQ"]
    sel = select_months(feats)
    if smoke > 0:
        sel = sel.head(int(smoke))

    plans: Dict[str, dict] = {}
    for r in sel.itertuples(index=False):
        year, month = int(r.year), int(r.month)
        if (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        mo = float(r.month_open)
        path = path_by.get((year, month))
        atr = float(path.atr14) if path is not None else float("nan")
        wb = rolling_band_from_paths(paths, "NQ", year, month, window=int(rolling_window))
        if wb is None or not np.isfinite(atr) or atr <= 0:
            continue
        up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(wb)
        if not all(np.isfinite(x) and x > 0 for x in (up_min, up_med, up_max, dn_min, dn_med, dn_max)):
            continue

        up_min_px = mo + up_min * atr
        up_med_px = mo + up_med * atr
        up_max_px = mo + up_max * atr
        dn_min_px = mo - dn_min * atr
        dn_med_px = mo - dn_med * atr
        dn_max_px = mo - dn_max * atr

        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=mo,
            t0=t0n,
            t1=t1n,
            n_days=int(liq_days),
        )
        if liq is None or float(liq.ext_pts) <= 0:
            continue

        if liq.side == "up":
            fade_side = "short"
            p_liq = float(liq.p_liq)
            ext = float(liq.ext_pts)
            # Band-max fade entry (up max); SL = liq-run size beyond entry
            bandmax_entry = float(up_max_px)
            bandmax_stop = bandmax_entry + ext
            liq_entry = p_liq
            liq_stop = p_liq + ext
        else:
            fade_side = "long"
            p_liq = float(liq.p_liq)
            ext = float(liq.ext_pts)
            bandmax_entry = float(dn_max_px)
            bandmax_stop = bandmax_entry - ext
            liq_entry = p_liq
            liq_stop = p_liq - ext

        # Envelope of all chart horizontals once liq SL known
        levels = [
            mo,
            up_min_px,
            up_med_px,
            up_max_px,
            dn_min_px,
            dn_med_px,
            dn_max_px,
            p_liq,
            liq_stop,
        ]
        range_high = float(max(levels))
        range_low = float(min(levels))
        range_size = range_high - range_low
        if range_size <= 0:
            continue

        key = "%04d-%02d" % (year, month)
        plans[key] = {
            "year": year,
            "month": month,
            "month_open": mo,
            "atr14": atr,
            "liq_days": int(liq_days),
            "liq_side": liq.side,
            "fade_side": fade_side,
            "ext_pts": ext,
            "p_liq": p_liq,
            "liq_entry": liq_entry,
            "liq_stop": liq_stop,
            # Variant A — band-max fade (plugin uses entry/stop/month_open as target)
            "side": fade_side,
            "entry": bandmax_entry,
            "stop": bandmax_stop,
            "target": mo,
            # Bands (prices)
            "up_min": up_min_px,
            "up_med": up_med_px,
            "up_max": up_max_px,
            "dn_min": dn_min_px,
            "dn_med": dn_med_px,
            "dn_max": dn_max_px,
            # Envelope for breakout sidecar
            "range_high": range_high,
            "range_low": range_low,
            "range_size": range_size,
            "arm_after_ts": _utc_z(liq.t_liq),
            "month_end_ts": _utc_z(t1n),
            "month_start_ts": _utc_z(t0n),
            "conditions": str(getattr(r, "conditions", "") or ""),
            "bands_known_at": "month_open",
            "range_known_at": "t_liq",
        }
    return plans


def write_causality_md(path: Path) -> None:
    text = """# Causality of chart levels (HP liq-run / band overlays)

## Always both band directions

Rolling **up** and **down** extension bands are computed every month from the
same prior-month path stats. There is no live condition that “creates” only one
side — both sides exist whenever the 6-month rolling window is available.

What *does* choose a **trade direction** for the fade book is the **liquidity
run** (largest |extension| from month open in the first N NY days).

## When each object is known

| Object | Known at | Causal rule |
|---|---|---|
| Up/dn min, med, max (**ATR multiples**) | **Before month open** | Mean of prior months only (`(y,m) < current`); 6-month roll |
| Month open | First bar of month | Session open |
| Band **prices** (`open ± atr×mult`) | Month open | Needs open + prior ATR from completed prior month |
| Liq side, `p_liq`, ext | **`t_liq`** | Extreme must print in first N NY days |
| 1R stop (= `p_liq ± ext`) | **`t_liq`** | Same |
| Envelope range (all horizontals incl. SL) | **`t_liq`** | Max/min of open, both bands, `p_liq`, 1R stop |

## Variant A — band-max fade

- Direction from liq run (fade).
- Entry limit at **dn max** (long) / **up max** (short).
- Target = month open.
- Stop distance = **liq-run size** (same R as base book, measured from band-max entry).
- Arm only after `t_liq` (same as base). Re-entry policy unchanged (TP re-arms; stop waits open touch).

## Variant B — range breakout sidecar

- Wait until `t_liq` (full range causal).
- **No breakout signal during the liq-run window** (`ts < arm_after_ts`).
- Signal: **4h close** outside `[range_low, range_high]`.
- Then arm **limit** at the broken boundary (follow-through).
- SL = **2 × liq-run size**; target = **range size**.
- Max **2** attempts; after a stop, re-arm only after another 4h close outside + limit at boundary.
- If 2×liq SL is too tight, swap to SL = range size (sensitivity later).
- Persistent fails → research fade-outside-range later (not in this pass).
"""
    path.write_text(text, encoding="utf-8")
