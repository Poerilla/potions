"""Kitchen-sink lookback filter: months that touch pct75→max ATR extension.

Labels months where price reaches the causal rolling-band **pct75** entry
(min + 0.75·(max−min)) and/or the band **max**, after the opening week —
same convention as ``monthly_open_atr_extension_band`` pct75 fades.

All predictors are known at the **start of the post-opening-week watch**
(month open + completed prior months/weeks + opening-week ORB of *this* month).

Hub: ``live/state/monthly_open_atr_extension_band/lookback_filter/``

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.monthly_open_atr_extension_band_lookback_filter --email
  python -m live.monthly_open_atr_extension_band_lookback_filter --symbols NQ --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import ATR_LEN, NY, wilder_atr
from .monthly_atr4_helpers import load_1h, month_windows, opening_week_slice
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    DEFAULT_SYMBOLS,
    MonthPathStats,
    _entry_stop_atr,
    collect_path_stats,
    rolling_band_from_paths,
)
from .monthly_open_atr_extension_study import _monthly_atr_lookup, _resample_monthly_ohlc
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS, MarketSpec
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO / "live" / "state" / "monthly_open_atr_extension_band" / "lookback_filter"
)
MIN_BUCKET_N = 8
SWING_LOOKBACKS = (3, 6, 12)
DOJI_BODY_FRAC = 0.10
VOL_DRY = 0.70
VOL_BUILD = 1.30
RANGE_WIDE = 1.25
ORB_WIDE = 1.25
ATR_WIDE = 1.25


def _pct75_level(band_min: float, band_med: float, band_max: float) -> float:
    """Broker-aligned pct75 (requires band_min > 0 via ``_entry_stop_atr``)."""
    entry, _stop = _entry_stop_atr(band_min, band_med, band_max, entry_mode="pct75")
    return float(entry)


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _resample_weekly_ohlc(bars: pd.DataFrame) -> pd.DataFrame:
    agg: Dict[str, str] = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in bars.columns:
        agg["volume"] = "sum"
    # Monday-start weeks in NY
    weekly = bars.resample("W-FRI", label="right", closed="right").agg(agg)
    return weekly.dropna(subset=["open", "high", "low", "close"])


def _atr_trail(ohlc: pd.DataFrame, mult: float = 3.0) -> pd.DataFrame:
    """Simple ATR trailing stop (SuperTrend-ish): trail below in uptrend / above in down."""
    atr = wilder_atr(ohlc, ATR_LEN)
    mid = (ohlc["high"].astype(float) + ohlc["low"].astype(float)) / 2.0
    upper = mid + mult * atr
    lower = mid - mult * atr
    close = ohlc["close"].astype(float)
    trail = pd.Series(np.nan, index=ohlc.index, dtype=float)
    side = pd.Series(0, index=ohlc.index, dtype=int)  # +1 long trail below, -1 short trail above
    prev_trail = float("nan")
    prev_side = 1
    for i, ts in enumerate(ohlc.index):
        u = float(upper.iloc[i])
        lo = float(lower.iloc[i])
        c = float(close.iloc[i])
        if not np.isfinite(u) or not np.isfinite(lo) or not np.isfinite(c):
            continue
        if not np.isfinite(prev_trail):
            prev_side = 1 if c >= lo else -1
            prev_trail = lo if prev_side > 0 else u
        if prev_side > 0:
            cand = max(lo, prev_trail) if np.isfinite(prev_trail) else lo
            if c < cand:
                prev_side = -1
                prev_trail = u
            else:
                prev_trail = cand
        else:
            cand = min(u, prev_trail) if np.isfinite(prev_trail) else u
            if c > cand:
                prev_side = 1
                prev_trail = lo
            else:
                prev_trail = cand
        trail.iloc[i] = prev_trail
        side.iloc[i] = prev_side
    out = ohlc.copy()
    out["atr"] = atr
    out["trail"] = trail
    out["trail_side"] = side
    out["dist_trail_atr"] = (close - trail) / atr.replace(0, np.nan)
    return out


def _candle_flags(row: pd.Series, prev: Optional[pd.Series]) -> Dict[str, float]:
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    rng = max(h - l, 1e-12)
    body = abs(c - o)
    out = {
        "body_frac": body / rng,
        "is_doji": float(body / rng <= DOJI_BODY_FRAC),
        "is_bull": float(c > o),
        "is_bear": float(c < o),
        "range": rng,
        "is_inside": 0.0,
        "is_engulf_bull": 0.0,
        "is_engulf_bear": 0.0,
    }
    if prev is not None:
        ph, pl, po, pc = (
            float(prev["high"]),
            float(prev["low"]),
            float(prev["open"]),
            float(prev["close"]),
        )
        out["is_inside"] = float(h < ph and l > pl)
        # Engulfing: this body engulfs prior body
        this_hi_body, this_lo_body = max(o, c), min(o, c)
        prev_hi_body, prev_lo_body = max(po, pc), min(po, pc)
        out["is_engulf_bull"] = float(
            c > o and this_lo_body <= prev_lo_body and this_hi_body >= prev_hi_body and (pc < po)
        )
        out["is_engulf_bear"] = float(
            c < o and this_lo_body <= prev_lo_body and this_hi_body >= prev_hi_body and (pc > po)
        )
    return out


def _year_orb(monthly: pd.DataFrame, year: int) -> Optional[Tuple[float, float, float]]:
    """Jan month high/low/open as yearly ORB proxy (completed Jan of calendar year)."""
    jan = monthly[(monthly.index.year == year) & (monthly.index.month == 1)]
    if jan.empty:
        return None
    r = jan.iloc[0]
    return float(r["open"]), float(r["high"]), float(r["low"])


def build_month_feature_frame(
    market: MarketSpec,
    paths: Sequence[MonthPathStats],
    *,
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
) -> pd.DataFrame:
    bars = load_1h(market)
    monthly = _resample_monthly_ohlc(bars)
    weekly = _resample_weekly_ohlc(bars)
    weekly_trail = _atr_trail(weekly, mult=3.0)
    atr_lookup = _monthly_atr_lookup(bars)
    path_by = {(p.year, p.month): p for p in paths}

    # Precompute monthly series helpers
    m_close = monthly["close"].astype(float)
    m_high = monthly["high"].astype(float)
    m_low = monthly["low"].astype(float)
    m_range = (m_high - m_low).astype(float)
    m_vol = monthly["volume"].astype(float) if "volume" in monthly.columns else None
    m_atr = wilder_atr(monthly, ATR_LEN)
    sma6 = m_close.rolling(6, min_periods=6).mean()
    sma12 = m_close.rolling(12, min_periods=12).mean()
    med_range_12 = m_range.rolling(12, min_periods=6).median()
    med_vol_12 = m_vol.rolling(12, min_periods=6).median() if m_vol is not None else None
    mean_atr_12 = m_atr.rolling(12, min_periods=6).mean()

    # Precompute opening-week ORB width in ATR units for every month
    orb_atr_by: Dict[Tuple[int, int], float] = {}
    for y2, m2, t0, _t1 in month_windows(bars, None, None):
        ow2 = opening_week_slice(bars, t0)
        atr2 = float(atr_lookup.get((y2, m2), float("nan")))
        if ow2.empty or not (atr2 > 0):
            continue
        orb_atr_by[(y2, m2)] = (float(ow2["high"].max()) - float(ow2["low"].min())) / atr2

    rows: List[dict] = []
    for year, month, m0, m1 in month_windows(bars, None, None):
        path = path_by.get((year, month))
        if path is None:
            continue
        wb = rolling_band_from_paths(
            paths, market.symbol, year, month, window=int(rolling_window)
        )
        if wb is None:
            continue
        up_entry = _pct75_level(wb.up_min, wb.up_median, wb.up_max)
        dn_entry = _pct75_level(wb.dn_min, wb.dn_median, wb.dn_max)
        up_valid = bool(np.isfinite(up_entry))
        dn_valid = bool(np.isfinite(dn_entry))
        if not (up_valid or dn_valid):
            continue

        touch_pct75_up = bool(up_valid and path.up.max_atr >= up_entry)
        touch_pct75_dn = bool(dn_valid and path.dn.max_atr >= dn_entry)
        touch_max_up = bool(
            np.isfinite(wb.up_max) and wb.up_max > 0 and path.up.max_atr >= wb.up_max
        )
        touch_max_dn = bool(
            np.isfinite(wb.dn_max) and wb.dn_max > 0 and path.dn.max_atr >= wb.dn_max
        )
        touch_pct75_any = touch_pct75_up or touch_pct75_dn
        touch_max_any = touch_max_up or touch_max_dn
        # Reach deep into 0.75→max zone on a broker-valid side
        in_zone_up = touch_pct75_up
        in_zone_dn = touch_pct75_dn

        # Prior completed month candle (index is month-end)
        prior_keys = [(p.year, p.month) for p in paths if (p.year, p.month) < (year, month)]
        if not prior_keys:
            continue
        py, pm = prior_keys[-1]
        prior_mask = (monthly.index.year == py) & (monthly.index.month == pm)
        if not prior_mask.any():
            continue
        prior_ts = monthly.index[prior_mask][0]
        prior_i = monthly.index.get_loc(prior_ts)
        if isinstance(prior_i, slice):
            continue
        prior_row = monthly.iloc[int(prior_i)]
        prev2 = monthly.iloc[int(prior_i) - 1] if int(prior_i) >= 1 else None
        cflags = _candle_flags(prior_row, prev2)

        # Range / ATR / volume vs normals (history ending at prior month)
        hist_end = prior_ts
        prange = float(m_range.loc[hist_end])
        med_r = (
            float(med_range_12.loc[hist_end])
            if np.isfinite(med_range_12.loc[hist_end])
            else float("nan")
        )
        patr = float(m_atr.loc[hist_end]) if np.isfinite(m_atr.loc[hist_end]) else float("nan")
        mean_a = (
            float(mean_atr_12.loc[hist_end])
            if np.isfinite(mean_atr_12.loc[hist_end])
            else float("nan")
        )
        range_vs_med = (
            prange / med_r if med_r and np.isfinite(med_r) and med_r > 0 else float("nan")
        )
        atr_vs_mean = (
            patr / mean_a if mean_a and np.isfinite(mean_a) and mean_a > 0 else float("nan")
        )
        vol_vs_med = float("nan")
        if m_vol is not None and med_vol_12 is not None:
            pv = float(m_vol.loc[hist_end])
            mv = float(med_vol_12.loc[hist_end])
            if mv > 0 and np.isfinite(mv) and np.isfinite(pv):
                vol_vs_med = pv / mv

        # Opening-week ORB of *this* month (known before watch starts)
        if (year, month) not in orb_atr_by:
            continue
        orb_range_atr = float(orb_atr_by[(year, month)])
        orb_hist = [orb_atr_by[k] for k in prior_keys if k in orb_atr_by]
        med_orb = float(np.median(orb_hist[-12:])) if len(orb_hist) >= 6 else float("nan")
        orb_vs_med = (
            orb_range_atr / med_orb
            if med_orb and np.isfinite(med_orb) and med_orb > 0
            else float("nan")
        )

        # Swing high/low sweeps in prior month vs prior N-month swing
        swing_flags: Dict[str, float] = {}
        for lb in SWING_LOOKBACKS:
            # swing from months before prior
            swing_high = float("-inf")
            swing_low = float("inf")
            count = 0
            for y2, m2 in reversed(prior_keys[:-1]):
                pp = path_by.get((y2, m2))
                if pp is None:
                    continue
                # use monthly OHLC extremes
                mask = (monthly.index.year == y2) & (monthly.index.month == m2)
                if not mask.any():
                    continue
                r = monthly.loc[mask].iloc[0]
                swing_high = max(swing_high, float(r["high"]))
                swing_low = min(swing_low, float(r["low"]))
                count += 1
                if count >= lb:
                    break
            if count < lb or not np.isfinite(swing_high):
                swing_flags["swept_swing_high_%dm" % lb] = float("nan")
                swing_flags["swept_swing_low_%dm" % lb] = float("nan")
            else:
                swing_flags["swept_swing_high_%dm" % lb] = float(float(prior_row["high"]) > swing_high)
                swing_flags["swept_swing_low_%dm" % lb] = float(float(prior_row["low"]) < swing_low)

        # Yearly ORB breakout status entering this month
        yorb = _year_orb(monthly, year)
        yorb_broke_up = float("nan")
        yorb_broke_dn = float("nan")
        month_open_vs_yorb = float("nan")
        if yorb is not None and month > 1:
            yo, yh, yl = yorb
            # any prior month this year (after Jan) swept Jan high/low?
            broke_u = False
            broke_d = False
            for y2, m2 in prior_keys:
                if y2 != year or m2 <= 1:
                    continue
                mask = (monthly.index.year == y2) & (monthly.index.month == m2)
                if not mask.any():
                    continue
                r = monthly.loc[mask].iloc[0]
                if float(r["high"]) > yh:
                    broke_u = True
                if float(r["low"]) < yl:
                    broke_d = True
            yorb_broke_up = float(broke_u)
            yorb_broke_dn = float(broke_d)
            month_open_vs_yorb = (path.month_open - yo) / path.atr14 if path.atr14 > 0 else float("nan")

        # MA / ATR mean-reversion state at prior close / month open
        sma6_v = float(sma6.loc[hist_end]) if np.isfinite(sma6.loc[hist_end]) else float("nan")
        sma12_v = float(sma12.loc[hist_end]) if np.isfinite(sma12.loc[hist_end]) else float("nan")
        prior_close = float(prior_row["close"])
        dist_sma6_atr = (
            (prior_close - sma6_v) / patr if patr and np.isfinite(patr) and patr > 0 and np.isfinite(sma6_v) else float("nan")
        )
        dist_sma12_atr = (
            (prior_close - sma12_v) / patr if patr and np.isfinite(patr) and patr > 0 and np.isfinite(sma12_v) else float("nan")
        )
        # Prior month mean-reverted toward SMA6 (open far, close nearer)
        ma_reverted = float("nan")
        if np.isfinite(sma6_v) and patr and patr > 0:
            d_open = abs(float(prior_row["open"]) - sma6_v) / patr
            d_close = abs(prior_close - sma6_v) / patr
            ma_reverted = float(d_open >= 0.5 and d_close < d_open * 0.6)
        # ATR mean reversion: prior close back inside prior ATR envelope from open
        atr_reverted = float("nan")
        if patr and patr > 0:
            po = float(prior_row["open"])
            atr_reverted = float(
                (abs(float(prior_row["high"]) - po) >= 0.75 * patr or abs(po - float(prior_row["low"])) >= 0.75 * patr)
                and abs(prior_close - po) <= 0.35 * patr
            )

        # Weekly ATR trail state at last completed week before month open
        weeks_before = weekly_trail[weekly_trail.index < m0]
        trail_side = float("nan")
        dist_trail = float("nan")
        trail_toward = float("nan")  # last 4 weeks moved toward trail?
        trail_away = float("nan")
        if len(weeks_before) >= 5:
            last = weeks_before.iloc[-1]
            trail_side = float(last["trail_side"])
            dist_trail = float(last["dist_trail_atr"]) if np.isfinite(last["dist_trail_atr"]) else float("nan")
            recent = weeks_before.iloc[-5:]
            # absolute distance change
            d0 = abs(float(recent["dist_trail_atr"].iloc[0]))
            d1 = abs(float(recent["dist_trail_atr"].iloc[-1]))
            if np.isfinite(d0) and np.isfinite(d1):
                trail_toward = float(d1 < d0 * 0.85)
                trail_away = float(d1 > d0 * 1.15)

        # Forward: after this month, do next 4 weeks move toward/away from trail?
        # (consequence of touch months — not a predictor)
        weeks_after = weekly_trail[(weekly_trail.index >= m1)]
        fwd_trail_toward = float("nan")
        fwd_trail_away = float("nan")
        if len(weeks_before) >= 1 and len(weeks_after) >= 4:
            d0 = abs(float(weeks_before.iloc[-1]["dist_trail_atr"]))
            d1 = abs(float(weeks_after.iloc[3]["dist_trail_atr"]))
            if np.isfinite(d0) and np.isfinite(d1):
                fwd_trail_toward = float(d1 < d0 * 0.85)
                fwd_trail_away = float(d1 > d0 * 1.15)

        row = {
            "market": market.symbol,
            "year": year,
            "month": month,
            "month_name": pd.Timestamp(year=year, month=month, day=1).strftime("%b"),
            "quarter": (month - 1) // 3 + 1,
            "month_open": path.month_open,
            "atr14": path.atr14,
            "up_max_atr": path.up.max_atr,
            "dn_max_atr": path.dn.max_atr,
            "pct75_up": up_entry if up_valid else float("nan"),
            "pct75_dn": dn_entry if dn_valid else float("nan"),
            "band_up_max": wb.up_max,
            "band_dn_max": wb.dn_max,
            "up_side_valid": int(up_valid),
            "dn_side_valid": int(dn_valid),
            "touch_pct75_up": int(touch_pct75_up),
            "touch_pct75_dn": int(touch_pct75_dn),
            "touch_pct75_any": int(touch_pct75_any),
            "touch_max_up": int(touch_max_up),
            "touch_max_dn": int(touch_max_dn),
            "touch_max_any": int(touch_max_any),
            "in_zone_any": int(in_zone_up or in_zone_dn),
            # calendar
            "cal_month": month,
            # prior candle
            "prior_doji": int(cflags["is_doji"]),
            "prior_inside": int(cflags["is_inside"]),
            "prior_engulf_bull": int(cflags["is_engulf_bull"]),
            "prior_engulf_bear": int(cflags["is_engulf_bear"]),
            "prior_bull": int(cflags["is_bull"]),
            "prior_bear": int(cflags["is_bear"]),
            # range / atr / vol
            "prior_range_vs_med": range_vs_med,
            "prior_range_wide": int(np.isfinite(range_vs_med) and range_vs_med >= RANGE_WIDE),
            "prior_atr_vs_mean": atr_vs_mean,
            "prior_atr_wide": int(np.isfinite(atr_vs_mean) and atr_vs_mean >= ATR_WIDE),
            "prior_vol_vs_med": vol_vs_med,
            "prior_vol_dryup": int(np.isfinite(vol_vs_med) and vol_vs_med <= VOL_DRY),
            "prior_vol_buildup": int(np.isfinite(vol_vs_med) and vol_vs_med >= VOL_BUILD),
            # this-month ORB (post open-week feature)
            "orb_range_atr": orb_range_atr,
            "orb_vs_med": orb_vs_med,
            "orb_wide": int(np.isfinite(orb_vs_med) and orb_vs_med >= ORB_WIDE),
            # yearly orb
            "yorb_broke_up": yorb_broke_up,
            "yorb_broke_dn": yorb_broke_dn,
            "month_open_vs_yorb_atr": month_open_vs_yorb,
            # MA / ATR revert
            "dist_sma6_atr": dist_sma6_atr,
            "dist_sma12_atr": dist_sma12_atr,
            "ext_above_sma6": int(np.isfinite(dist_sma6_atr) and dist_sma6_atr >= 1.0),
            "ext_below_sma6": int(np.isfinite(dist_sma6_atr) and dist_sma6_atr <= -1.0),
            "prior_ma_reverted": ma_reverted if np.isfinite(ma_reverted) else float("nan"),
            "prior_atr_reverted": atr_reverted if np.isfinite(atr_reverted) else float("nan"),
            # weekly trail
            "trail_side": trail_side,
            "dist_trail_atr": dist_trail,
            "near_trail": int(np.isfinite(dist_trail) and abs(dist_trail) <= 0.5),
            "far_trail": int(np.isfinite(dist_trail) and abs(dist_trail) >= 2.0),
            "prior_weeks_toward_trail": trail_toward if np.isfinite(trail_toward) else float("nan"),
            "prior_weeks_away_trail": trail_away if np.isfinite(trail_away) else float("nan"),
            "fwd_weeks_toward_trail": fwd_trail_toward if np.isfinite(fwd_trail_toward) else float("nan"),
            "fwd_weeks_away_trail": fwd_trail_away if np.isfinite(fwd_trail_away) else float("nan"),
        }
        row.update(swing_flags)
        # binary convenience for swings
        for lb in SWING_LOOKBACKS:
            for side in ("high", "low"):
                k = "swept_swing_%s_%dm" % (side, lb)
                v = row.get(k)
                if v == v:  # not nan
                    row[k] = int(v)
        rows.append(row)

    return pd.DataFrame(rows)


BINARY_FEATURES: Sequence[str] = (
    "prior_doji",
    "prior_inside",
    "prior_engulf_bull",
    "prior_engulf_bear",
    "prior_bull",
    "prior_bear",
    "prior_range_wide",
    "prior_atr_wide",
    "prior_vol_dryup",
    "prior_vol_buildup",
    "orb_wide",
    "ext_above_sma6",
    "ext_below_sma6",
    "near_trail",
    "far_trail",
    "swept_swing_high_3m",
    "swept_swing_low_3m",
    "swept_swing_high_6m",
    "swept_swing_low_6m",
    "swept_swing_high_12m",
    "swept_swing_low_12m",
)

OPTIONAL_BINARY: Sequence[str] = (
    "yorb_broke_up",
    "yorb_broke_dn",
    "prior_ma_reverted",
    "prior_atr_reverted",
    "prior_weeks_toward_trail",
    "prior_weeks_away_trail",
)

CATEGORICAL: Sequence[str] = ("cal_month", "quarter", "month_name")


def _lift_table(
    df: pd.DataFrame,
    label: str,
    *,
    min_n: int = MIN_BUCKET_N,
) -> pd.DataFrame:
    """Hit-rate lift for binary / categorical predictors vs base rate."""
    base = float(df[label].mean()) if len(df) else float("nan")
    n_all = int(len(df))
    rows: List[dict] = []

    def add_bucket(feature: str, bucket: str, mask: pd.Series) -> None:
        sub = df.loc[mask]
        n = int(len(sub))
        if n < min_n:
            return
        rate = float(sub[label].mean())
        lift = rate / base if base and base > 0 else float("nan")
        # simple Wilson-ish z for rate diff (approx)
        p1, p0 = rate, base
        se = math.sqrt(max(p1 * (1 - p1) / max(n, 1), 0) + max(p0 * (1 - p0) / max(n_all, 1), 0))
        z = (p1 - p0) / se if se > 0 else float("nan")
        rows.append(
            {
                "label": label,
                "feature": feature,
                "bucket": bucket,
                "n": n,
                "hit_rate": rate,
                "base_rate": base,
                "lift": lift,
                "delta_pp": (rate - base) * 100.0,
                "z": z,
                "coverage": n / n_all if n_all else float("nan"),
            }
        )

    for feat in list(BINARY_FEATURES) + list(OPTIONAL_BINARY):
        if feat not in df.columns:
            continue
        s = pd.to_numeric(df[feat], errors="coerce")
        add_bucket(feat, "true", s == 1)
        add_bucket(feat, "false", s == 0)

    for feat in CATEGORICAL:
        if feat not in df.columns:
            continue
        for val, sub_idx in df.groupby(feat).groups.items():
            add_bucket(feat, str(val), df.index.isin(sub_idx))

    # continuous quartile buckets
    for feat, label_name in (
        ("orb_range_atr", "orb_range_atr"),
        ("orb_vs_med", "orb_vs_med"),
        ("prior_range_vs_med", "prior_range_vs_med"),
        ("prior_atr_vs_mean", "prior_atr_vs_mean"),
        ("prior_vol_vs_med", "prior_vol_vs_med"),
        ("dist_sma6_atr", "dist_sma6_atr"),
        ("dist_trail_atr", "dist_trail_atr"),
    ):
        if feat not in df.columns:
            continue
        s = pd.to_numeric(df[feat], errors="coerce")
        valid = s.dropna()
        if len(valid) < min_n * 2:
            continue
        try:
            q = pd.qcut(valid, 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        except ValueError:
            continue
        for qv in q.unique():
            idx = q[q == qv].index
            add_bucket(label_name + "_quartile", str(qv), df.index.isin(idx))

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["lift", "n"], ascending=[False, False]).reset_index(drop=True)


def _fwd_trail_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Do pct75-touch months precede weekly moves toward/away from ATR trail?"""
    rows = []
    for label in ("touch_pct75_any", "touch_max_any"):
        for outcome in ("fwd_weeks_toward_trail", "fwd_weeks_away_trail"):
            for hit_val, tag in ((1, "touch"), (0, "no_touch")):
                sub = df[df[label] == hit_val]
                s = pd.to_numeric(sub[outcome], errors="coerce").dropna()
                if len(s) < MIN_BUCKET_N:
                    continue
                rows.append(
                    {
                        "touch_label": label,
                        "cohort": tag,
                        "outcome": outcome,
                        "n": int(len(s)),
                        "rate": float(s.mean()),
                    }
                )
    return pd.DataFrame(rows)


def _combo_screen(df: pd.DataFrame, label: str, top_feats: Sequence[str]) -> pd.DataFrame:
    """Pairwise AND of top binary features — exploratory only."""
    rows = []
    base = float(df[label].mean()) if len(df) else float("nan")
    feats = [f for f in top_feats if f in df.columns]
    for i, a in enumerate(feats):
        for b in feats[i + 1 :]:
            sa = pd.to_numeric(df[a], errors="coerce")
            sb = pd.to_numeric(df[b], errors="coerce")
            mask = (sa == 1) & (sb == 1)
            n = int(mask.sum())
            if n < MIN_BUCKET_N:
                continue
            rate = float(df.loc[mask, label].mean())
            rows.append(
                {
                    "label": label,
                    "combo": "%s AND %s" % (a, b),
                    "n": n,
                    "hit_rate": rate,
                    "base_rate": base,
                    "lift": rate / base if base > 0 else float("nan"),
                    "delta_pp": (rate - base) * 100.0,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("lift", ascending=False).reset_index(drop=True)


def _summary_md(
    frames: Dict[str, pd.DataFrame],
    lifts: Dict[str, pd.DataFrame],
    fwd: pd.DataFrame,
    combos: Dict[str, pd.DataFrame],
) -> str:
    lines = [
        "# Monthly open ATR extension — pct75 lookback filter",
        "",
        "Kitchen-sink predictors for months that reach the causal rolling-6m",
        "**pct75** band (min + 0.75·(max−min)) after the opening week.",
        "Diagnostic only — not a promotion gate.",
        "",
        "## Base rates",
        "",
        "| Market | N months | pct75 any | pct75 up | pct75 dn | max any |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for sym, df in sorted(frames.items()):
        lines.append(
            "| %s | %d | %.1f%% | %.1f%% | %.1f%% | %.1f%% |"
            % (
                sym,
                len(df),
                100 * df["touch_pct75_any"].mean(),
                100 * df["touch_pct75_up"].mean(),
                100 * df["touch_pct75_dn"].mean(),
                100 * df["touch_max_any"].mean(),
            )
        )

    lines.extend(["", "## Calendar month hit rates (pct75 any)", ""])
    for sym, df in sorted(frames.items()):
        lines.append("### %s" % sym)
        lines.append("")
        lines.append("| Month | N | Hit% | Lift |")
        lines.append("|---|---:|---:|---:|")
        base = float(df["touch_pct75_any"].mean())
        for m in range(1, 13):
            sub = df[df["cal_month"] == m]
            if len(sub) < 5:
                continue
            rate = float(sub["touch_pct75_any"].mean())
            name = pd.Timestamp(year=2000, month=m, day=1).strftime("%b")
            lines.append(
                "| %s | %d | %.0f%% | %.2fx |"
                % (name, len(sub), 100 * rate, rate / base if base else float("nan"))
            )
        lines.append("")

    lines.extend(
        [
            "## Top lift predictors (pct75 any, lift≥1.15, n≥%d, |z|≥1.0)" % MIN_BUCKET_N,
            "",
        ]
    )
    for sym, lift in sorted(lifts.items()):
        sub = lift[
            (lift["label"] == "touch_pct75_any")
            & (lift["lift"] >= 1.15)
            & (lift["n"] >= MIN_BUCKET_N)
            & (lift["z"].abs() >= 1.0)
            & (lift["bucket"].isin(["true", "Q4", "Q1"]) | lift["feature"].isin(["cal_month", "month_name", "quarter"]))
        ].head(20)
        lines.append("### %s" % sym)
        lines.append("")
        if sub.empty:
            lines.append("_No strong lifts at this threshold._")
            lines.append("")
            continue
        lines.append("| Feature | Bucket | N | Hit% | Base% | Lift | Δpp | z |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for _, r in sub.iterrows():
            lines.append(
                "| %s | %s | %d | %.0f%% | %.0f%% | %.2fx | %+.1f | %.2f |"
                % (
                    r["feature"],
                    r["bucket"],
                    int(r["n"]),
                    100 * r["hit_rate"],
                    100 * r["base_rate"],
                    r["lift"],
                    r["delta_pp"],
                    r["z"],
                )
            )
        lines.append("")

    lines.extend(["## Protective / skip signals (lift≤0.85, true bucket)", ""])
    for sym, lift in sorted(lifts.items()):
        sub = lift[
            (lift["label"] == "touch_pct75_any")
            & (lift["bucket"] == "true")
            & (lift["lift"] <= 0.85)
            & (lift["n"] >= MIN_BUCKET_N)
        ].head(12)
        lines.append("### %s" % sym)
        lines.append("")
        if sub.empty:
            lines.append("_None at this threshold._")
            lines.append("")
            continue
        lines.append("| Feature | N | Hit% | Lift | Δpp | z |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for _, r in sub.iterrows():
            lines.append(
                "| %s | %d | %.0f%% | %.2fx | %+.1f | %.2f |"
                % (r["feature"], int(r["n"]), 100 * r["hit_rate"], r["lift"], r["delta_pp"], r["z"])
            )
        lines.append("")

    lines.extend(["## Forward weekly ATR-trail after touch months", ""])
    if fwd is not None and not fwd.empty:
        lines.append("| Touch label | Cohort | Outcome | N | Rate |")
        lines.append("|---|---|---|---:|---:|")
        for _, r in fwd.iterrows():
            lines.append(
                "| %s | %s | %s | %d | %.0f%% |"
                % (r["touch_label"], r["cohort"], r["outcome"], int(r["n"]), 100 * r["rate"])
            )
        lines.append("")
    else:
        lines.append("_Insufficient forward weeks._")
        lines.append("")

    lines.extend(["## Top pairwise combos (exploratory)", ""])
    for sym, c in sorted(combos.items()):
        lines.append("### %s" % sym)
        lines.append("")
        if c is None or c.empty:
            lines.append("_None._")
            lines.append("")
            continue
        top = c.head(10)
        lines.append("| Combo | N | Hit% | Lift |")
        lines.append("|---|---:|---:|---:|")
        for _, r in top.iterrows():
            lines.append(
                "| %s | %d | %.0f%% | %.2fx |"
                % (r["combo"], int(r["n"]), 100 * r["hit_rate"], r["lift"])
            )
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- Band = causal rolling **6** prior months mean(min/med/max).",
            "- Opening-week ORB is allowed (strategy already waits until after week 1).",
            "- Swing sweeps / candle patterns / volume / ATR width use **prior completed** month only.",
            "- Forward trail stats are consequences, not entry filters.",
            "",
        ]
    )
    return "\n".join(lines)


def _email_body(
    output_root: Path,
    frames: Dict[str, pd.DataFrame],
    lifts: Dict[str, pd.DataFrame],
) -> str:
    lines = [
        "Monthly open ATR extension — pct75 lookback filter",
        "",
        "Hub: %s" % output_root,
        "",
        "Base rates (months reaching pct75 band after open week):",
    ]
    for sym, df in sorted(frames.items()):
        lines.append(
            "  %s: N=%d  pct75_any=%.0f%%  max_any=%.0f%%"
            % (
                sym,
                len(df),
                100 * df["touch_pct75_any"].mean(),
                100 * df["touch_max_any"].mean(),
            )
        )
    lines.append("")
    lines.append("Strongest true-bucket lifts (pct75 any, lift≥1.2, |z|≥1.2):")
    for sym, lift in sorted(lifts.items()):
        sub = lift[
            (lift["label"] == "touch_pct75_any")
            & (lift["bucket"] == "true")
            & (lift["lift"] >= 1.2)
            & (lift["z"].abs() >= 1.2)
            & (lift["n"] >= MIN_BUCKET_N)
        ].head(6)
        lines.append("  [%s]" % sym)
        if sub.empty:
            lines.append("    (none)")
            continue
        for _, r in sub.iterrows():
            lines.append(
                "    %s  n=%d  hit=%.0f%%  lift=%.2fx  z=%.1f"
                % (r["feature"], int(r["n"]), 100 * r["hit_rate"], r["lift"], r["z"])
            )
    lines.extend(
        [
            "",
            "Stance: diagnostic filter hunt — use SUMMARY.md before wiring skip/size rules.",
            "Artifacts: months_features.csv, lift_*.csv, SUMMARY.md",
        ]
    )
    return "\n".join(lines) + "\n"


def run(
    *,
    symbols: Sequence[str],
    output_root: Path,
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    email: bool = False,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress(output_root, "lookback filter start symbols=%s window=%d" % (list(symbols), rolling_window))

    frames: Dict[str, pd.DataFrame] = {}
    lifts: Dict[str, pd.DataFrame] = {}
    combos: Dict[str, pd.DataFrame] = {}
    fwd_parts: List[pd.DataFrame] = []

    for sym in symbols:
        market = MARKETS[sym.upper()]
        _progress(output_root, "collect paths %s" % market.symbol)
        paths = collect_path_stats(market)
        _progress(output_root, "  paths=%d — build features" % len(paths))
        df = build_month_feature_frame(market, paths, rolling_window=rolling_window)
        frames[market.symbol] = df
        df.to_csv(output_root / ("months_features_%s.csv" % market.symbol.lower()), index=False)
        _progress(
            output_root,
            "  months=%d pct75_any=%.1f%%"
            % (len(df), 100 * df["touch_pct75_any"].mean() if len(df) else 0.0),
        )

        lift_parts = []
        for label in ("touch_pct75_any", "touch_pct75_up", "touch_pct75_dn", "touch_max_any"):
            lift_parts.append(_lift_table(df, label))
        lift = pd.concat(lift_parts, ignore_index=True) if lift_parts else pd.DataFrame()
        lifts[market.symbol] = lift
        lift.to_csv(output_root / ("lift_%s.csv" % market.symbol.lower()), index=False)

        # top binaries by lift for combos
        top = (
            lift[
                (lift["label"] == "touch_pct75_any")
                & (lift["bucket"] == "true")
                & (lift["n"] >= MIN_BUCKET_N)
            ]
            .sort_values("lift", ascending=False)["feature"]
            .head(8)
            .tolist()
        )
        combo = _combo_screen(df, "touch_pct75_any", top)
        combos[market.symbol] = combo
        if not combo.empty:
            combo.to_csv(output_root / ("combos_%s.csv" % market.symbol.lower()), index=False)

        fwd = _fwd_trail_summary(df)
        if not fwd.empty:
            fwd = fwd.assign(market=market.symbol)
            fwd_parts.append(fwd)

    all_feat = pd.concat(frames.values(), ignore_index=True)
    all_feat.to_csv(output_root / "months_features_all.csv", index=False)
    all_lift = pd.concat(
        [v.assign(market=k) for k, v in lifts.items()], ignore_index=True
    )
    all_lift.to_csv(output_root / "lift_all.csv", index=False)
    fwd_all = pd.concat(fwd_parts, ignore_index=True) if fwd_parts else pd.DataFrame()
    if not fwd_all.empty:
        fwd_all.to_csv(output_root / "forward_trail_outcomes.csv", index=False)

    summary = _summary_md(frames, lifts, fwd_all, combos)
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")

    email_txt = _email_body(output_root, frames, lifts)
    (output_root / "EMAIL.txt").write_text(email_txt, encoding="utf-8")

    meta = {
        "symbols": list(symbols),
        "rolling_window": rolling_window,
        "n_months": {k: int(len(v)) for k, v in frames.items()},
        "pct75_any_rate": {
            k: float(v["touch_pct75_any"].mean()) if len(v) else None for k, v in frames.items()
        },
    }
    (output_root / "RUN_COMPLETE.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _progress(output_root, "done — wrote %s" % output_root)

    for sym, df in frames.items():
        try:
            log_run(
                run_class="pandas",
                variant_slug="monthly_open_atr_ext_band_lookback_filter",
                instrument=sym,
                hub_path=str(output_root),
                trades=int(len(df)),
                meta={
                    "pct75_any_rate": float(df["touch_pct75_any"].mean()) if len(df) else None,
                    "rolling_window": rolling_window,
                },
                notes="kitchen-sink lookback filter for pct75 touch months",
            )
        except Exception as exc:  # noqa: BLE001
            _progress(output_root, "ledger warn %s: %s" % (sym, exc))

    if email:
        send_email(
            subject="potions: monthly ATR pct75 lookback filter",
            body=email_txt,
        )
    return output_root


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        run(
            symbols=args.symbols,
            output_root=args.output_root,
            rolling_window=int(args.rolling_window),
            email=bool(args.email),
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        err = traceback.format_exc()
        print(err, flush=True)
        try:
            send_email(
                subject="potions: monthly ATR pct75 lookback FAILED",
                body="FAILED\n\n%s\n\n%s\n" % (args.output_root, err),
            )
        except Exception:
            pass
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
