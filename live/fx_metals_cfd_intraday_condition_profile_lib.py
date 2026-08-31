"""Book catalog, width/HTF features, and condition columns for FX/metals/CFD HP profile v1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .futures_intraday_hp_sizeup_lib import (
    _build_htf_structure_frame,
    _weekly_atr_supertrend,
    feature_family,
)
from .intraday_condition_profile import (
    Book,
    _asof_merge,
    annotate_campaigns as annotate_base,
    build_feature_frames,
    ensure_tf_bars,
    load_campaigns,
)

STUDY = "fx_metals_cfd_intraday_condition_profile_v1"
PROFILE_HUB = REPO / "live" / "state" / "fx_metals_cfd_intraday_condition_profile"
QB_ROOT = REPO / "live" / "state" / "quarterly_range_breakout_fx_metals_cfd"
PHASE2_HUB = REPO / "live" / "state" / "fx_metals_cfd_intraday_hp_sizeup_nulls"
MIN_N = 40

# Calendar / HTF from intraday profile (reuse titles for overlay/null parity).
BASE_CONDITION_COLS: List[Tuple[str, str]] = [
    ("dow", "Day of week"),
    ("week_of_month", "Week of month"),
    ("hour_ny", "Entry hour (NY)"),
    ("month", "Month"),
    ("ma5_align", "5m MA vs trade"),
    ("ma5_cross_align", "5m MA cross vs trade"),
    ("rsi_bucket", "Hourly RSI bucket"),
    ("rsi_align", "Hourly RSI vs trade"),
    ("obv_align", "Hourly OBV vs trade"),
    ("atr_q", "ATR14 quartile"),
    ("day_half_align", "Prior-day range half"),
    ("week_half_align", "Prior-week range half"),
    ("month_half_align", "Prior-month range half"),
]

WIDTH_CONDITION_COLS: List[Tuple[str, str]] = [
    ("prior_day_range_pct", "Prior-day range percentile"),
    ("atr_pct_bucket", "ATR causal rolling percentile"),
    ("prior_q_width_q", "Prior-quarter range width"),
    ("london_or_width", "London OR width vs ATR"),
    ("monday_range_pct", "Monday session range vs ATR"),
]

HTF_CONDITION_COLS: List[Tuple[str, str]] = [
    ("yor_dir", "Yearly ORB direction"),
    ("mor_dir", "Monthly OR direction"),
    ("prior_q_type", "Prior quarter type"),
    ("w_atr_align", "Weekly ATR trend vs trade"),
]

CONDITION_COLS = BASE_CONDITION_COLS + WIDTH_CONDITION_COLS + HTF_CONDITION_COLS
COND_COL: Dict[str, str] = {title: col for col, title in CONDITION_COLS}

CAUSAL_LIVE_READY = {
    "Day of week",
    "Week of month",
    "Entry hour (NY)",
    "Month",
    "5m MA vs trade",
    "5m MA cross vs trade",
    "Hourly RSI bucket",
    "Hourly RSI vs trade",
    "Hourly OBV vs trade",
    "Prior-day range half",
    "Prior-week range half",
    "Prior-month range half",
    "Prior-day range percentile",
    "Prior-quarter range width",
    "London OR width vs ATR",
    "Monday session range vs ATR",
    "Yearly ORB direction",
    "Monthly OR direction",
    "Prior quarter type",
    "Weekly ATR trend vs trade",
}
NEEDS_LIVE_PROXY = {
    "ATR14 quartile",
    "ATR causal rolling percentile",
}


def _qb_book(symbol: str) -> Book:
    sym = symbol.lower()
    return Book(
        "%s_quarterly_breakout" % sym,
        "%s quarterly range honest breakout" % symbol,
        symbol,
        QB_ROOT / sym / "states" / ("%s_quarterly_range_breakout" % sym) / "fills.csv",
        "quarterly_breakout",
        fee_override=1.5,
    )


DEFAULT_BOOKS: Tuple[Book, ...] = (
    # --- Monday OR (Phase 2 tapes + running demos) ---
    Book(
        "eurusd_monday_or",
        "EURUSD Monday OR M1_S2_R2 (Phase2)",
        "EURUSD",
        REPO / "live/state/monday_or_phase2/states/eurusd_m1_s2_r2_dd35_55/fills.csv",
        "monday_or",
        fee_override=1.5,
    ),
    Book(
        "usdjpy_monday_or",
        "USDJPY Monday OR M2_S3_R1 skip Aug/Sep",
        "USDJPY",
        REPO / "live/state/monday_or_phase2/tuneup_broker/states/usdjpy_m2_s3_r1_skip_augsep/fills.csv",
        "monday_or",
        fee_override=1.5,
    ),
    Book(
        "us30_monday_or",
        "US30 Monday OR M3_S3_R2",
        "US30",
        REPO / "live/state/monday_or_sizing_sweep_broker_us30/states/us30_m3_s3_r2/fills.csv",
        "monday_or",
        fee_override=1.5,
    ),
    Book(
        "gbpusd_monday_or",
        "GBPUSD Monday OR M1_S1_R2 (Phase2)",
        "GBPUSD",
        REPO / "live/state/monday_or_phase2/states/gbpusd_m1_s1_r2_dd35_55/fills.csv",
        "monday_or",
        fee_override=1.5,
    ),
    Book(
        "audjpy_monday_or",
        "AUDJPY Monday OR M1_S2_R2 (Phase2)",
        "AUDJPY",
        REPO / "live/state/monday_or_phase2/states/audjpy_m1_s2_r2_dd35_55/fills.csv",
        "monday_or",
        fee_override=1.5,
    ),
    Book(
        "xauusd_monday_or",
        "XAUUSD Monday OR M2_S2_R3 (Phase2)",
        "XAUUSD",
        REPO / "live/state/monday_or_phase2/states/xauusd_m2_s2_r3_dd35_55/fills.csv",
        "monday_or",
        fee_override=1.5,
    ),
    # --- Asia-range / v2b / London prior-opposed ---
    Book(
        "usdjpy_asia_range",
        "USDJPY Asia-range London S_3_1_3 filtered",
        "USDJPY",
        REPO
        / "live/state/fx_v2b_asia_range_london_usdjpy_filters/states/usdjpy_v2b_asia_range_london_S_3_1_3_flt/fills.csv",
        "asia_range",
        fee_override=1.5,
    ),
    Book(
        "eurusd_v2b_ungated",
        "EURUSD v2b ungated S_1_1_1",
        "EURUSD",
        REPO / "live/state/eurusd_v2b_ungated_S_1_1_1/states/eurusd_v2b_oco_S_1_1_1/fills.csv",
        "v2b",
        fee_override=1.5,
    ),
    Book(
        "nas100_v2b_london",
        "NAS100 v2b London ungated S_1_1_3",
        "NAS100",
        REPO / "live/state/fx_v2b_london_ungated/states/nas100_v2b_london_S_1_1_3/fills.csv",
        "v2b",
        fee_override=1.5,
    ),
    Book(
        "us30_london_prior_opposed",
        "US30 London prior-opposed S_1_1_3",
        "US30",
        REPO
        / "live/state/fx_v2b_london_prior_opposed/states/us30_v2b_london_prior_opposed_S_1_1_3/fills.csv",
        "london_prior",
        fee_override=1.5,
    ),
    # --- ST+PMC 3R (FX + metals + CFD) ---
    Book(
        "eurusd_st_pmc_3r",
        "EURUSD hourly ST+PMC 50/150 3r",
        "EURUSD",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/eurusd/states/eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "gbpusd_st_pmc_3r",
        "GBPUSD hourly ST+PMC 50/150 3r",
        "GBPUSD",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/gbpusd/states/gbpusd_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "usdjpy_st_pmc_3r",
        "USDJPY hourly ST+PMC 50/150 3r",
        "USDJPY",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/usdjpy/states/usdjpy_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "audjpy_st_pmc_3r",
        "AUDJPY hourly ST+PMC 50/150 3r",
        "AUDJPY",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/audjpy/states/audjpy_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "nas100_st_pmc_3r",
        "NAS100 hourly ST+PMC 50/150 3r",
        "NAS100",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/nas100/states/nas100_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "us30_st_pmc_3r",
        "US30 hourly ST+PMC 50/150 3r",
        "US30",
        REPO / "live/state/us30_st_pmc_runner_variants/states/us30_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "xauusd_st_pmc_3r",
        "XAUUSD hourly ST+PMC 50/150 3r",
        "XAUUSD",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/xauusd/states/xauusd_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    Book(
        "xagusd_st_pmc_3r",
        "XAGUSD hourly ST+PMC 50/150 3r",
        "XAGUSD",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/xagusd/states/xagusd_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
    # --- Quarterly range honest breakout (FX / metals / CFD) ---
    _qb_book("EURUSD"),
    _qb_book("GBPUSD"),
    _qb_book("USDJPY"),
    _qb_book("AUDJPY"),
    _qb_book("XAUUSD"),
    _qb_book("XAGUSD"),
    _qb_book("US30"),
    _qb_book("NAS100"),
)


def _rolling_pct_rank(series: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    return series.rolling(window, min_periods=min_periods).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) else np.nan,
        raw=False,
    )


def _width_tercile(col: pd.Series, *, prefix: str) -> pd.Series:
    return pd.cut(
        col,
        bins=[-0.01, 0.33, 0.66, 1.01],
        labels=["%s_comp" % prefix, "%s_norm" % prefix, "%s_exp" % prefix],
    ).astype(str)


def _width_quartile(col: pd.Series, *, prefix: str) -> pd.Series:
    try:
        return pd.qcut(col, 4, labels=["%s_q1" % prefix, "%s_q2" % prefix, "%s_q3" % prefix, "%s_q4" % prefix]).astype(str)
    except ValueError:
        return pd.Series(["%s_na" % prefix] * len(col), index=col.index)


def _prior_quarter_width_frame(d1: pd.DataFrame) -> pd.DataFrame:
    d = d1.copy().sort_values("ts")
    d["qkey"] = d["ts"].dt.year.astype(str) + "Q" + (((d["ts"].dt.month - 1) // 3) + 1).astype(str)
    q = (
        d.groupby("qkey", sort=True)
        .agg(q_high=("high", "max"), q_low=("low", "min"), q_start=("ts", "min"))
        .reset_index()
        .sort_values("q_start")
    )
    q["prior_width"] = (q["q_high"] - q["q_low"]).shift(1)
    q["prior_width_pct"] = _rolling_pct_rank(q["prior_width"], window=20, min_periods=8)
    q["prior_q_width_q"] = _width_quartile(q["prior_width_pct"], prefix="pqw")
    lookup = q[["qkey", "prior_width", "prior_q_width_q", "q_start"]].copy()
    lookup["ts"] = lookup["q_start"] + pd.Timedelta(days=1)
    return lookup[["ts", "prior_width", "prior_q_width_q"]].sort_values("ts")


def _london_or_width_frame(h1: pd.DataFrame, d1: pd.DataFrame) -> pd.DataFrame:
    """London killzone 02:00–05:00 NY OR width vs daily ATR (causal next hour)."""
    h = h1.copy()
    h["date"] = h["ts"].dt.normalize()
    h["hour"] = h["ts"].dt.hour
    lk = h[(h["hour"] >= 2) & (h["hour"] < 5)].copy()
    if lk.empty:
        return pd.DataFrame(columns=["ts", "london_or_width"])
    or_df = lk.groupby("date", sort=True).agg(or_high=("high", "max"), or_low=("low", "min"), or_end=("ts", "max"))
    or_df["or_width"] = or_df["or_high"] - or_df["or_low"]
    or_df["or_width_pct"] = _rolling_pct_rank(or_df["or_width"], window=60, min_periods=20)
    d = d1.copy()
    tr = pd.concat(
        [(d["high"] - d["low"]), (d["high"] - d["close"].shift(1)).abs(), (d["low"] - d["close"].shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    atr_map = pd.DataFrame({"ts": d["ts"].dt.normalize(), "atr14": atr}).dropna()
    or_df = or_df.reset_index().rename(columns={"date": "ts"})
    or_df = or_df.merge(atr_map, on="ts", how="left")
    or_df["or_norm"] = or_df["or_width"] / or_df["atr14"].replace(0, np.nan)
    or_df["london_or_width"] = np.where(
        or_df["or_norm"].isna() | or_df["or_width_pct"].isna(),
        "lor_na",
        np.where(
            or_df["or_width_pct"] < 0.33,
            "lor_narrow",
            np.where(or_df["or_width_pct"] < 0.66, "lor_norm", "lor_wide"),
        ),
    )
    out = or_df[["or_end", "london_or_width"]].rename(columns={"or_end": "ts"})
    out["ts"] = out["ts"] + pd.Timedelta(hours=1)
    return out.sort_values("ts")


def _monday_range_frame(d1: pd.DataFrame) -> pd.DataFrame:
    d = d1.copy()
    d["dow_i"] = d["ts"].dt.dayofweek
    mon = d[d["dow_i"] == 0].copy()
    if mon.empty:
        return pd.DataFrame(columns=["ts", "monday_range_pct"])
    mon["mon_range"] = mon["high"] - mon["low"]
    mon["mon_range_pct"] = _rolling_pct_rank(mon["mon_range"], window=60, min_periods=20)
    mon["monday_range_pct"] = np.where(
        mon["mon_range_pct"].isna(),
        "mon_na",
        np.where(
            mon["mon_range_pct"] < 0.33,
            "mon_narrow",
            np.where(mon["mon_range_pct"] < 0.66, "mon_norm", "mon_wide"),
        ),
    )
    mon["ts"] = mon["ts"].dt.normalize() + pd.Timedelta(days=1)
    return mon[["ts", "monday_range_pct"]].sort_values("ts")


def annotate_campaigns(
    campaigns: pd.DataFrame,
    symbol: str,
    *,
    family: str,
    feats: Optional[Dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """Base calendar/HTF features plus width + quarterly HTF tags."""
    if feats is None:
        feats = build_feature_frames(symbol)
    df = annotate_base(campaigns, feats)

    d1 = ensure_tf_bars(symbol, "1d")
    h1 = ensure_tf_bars(symbol, "1h")

    if d1 is not None and len(d1) >= 30:
        d = d1.copy()
        prev_rng = (d["high"].shift(1) - d["low"].shift(1))
        d["prior_day_range_pct_raw"] = _rolling_pct_rank(prev_rng)
        d_feat = pd.DataFrame(
            {
                "ts": d["ts"].dt.normalize() + pd.Timedelta(days=1),
                "prior_day_range_pct": _width_tercile(d["prior_day_range_pct_raw"], prefix="prior_range"),
            }
        )
        tr = pd.concat(
            [
                (d["high"] - d["low"]),
                (d["high"] - d["close"].shift(1)).abs(),
                (d["low"] - d["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14).mean().shift(1)
        d_feat["atr_pct_raw"] = _rolling_pct_rank(atr)
        d_feat["atr_pct_bucket"] = pd.cut(
            d_feat["atr_pct_raw"],
            bins=[-0.01, 0.25, 0.50, 0.75, 1.01],
            labels=["atr_pctl_q1", "atr_pctl_q2", "atr_pctl_q3", "atr_pctl_q4"],
        ).astype(str)
        df = _asof_merge(df, d_feat.sort_values("ts"), ["prior_day_range_pct", "atr_pct_bucket"])

        htf = _build_htf_structure_frame(d1)
        if htf is not None and not htf.empty:
            df = _asof_merge(df, htf, ["yor_dir", "mor_dir", "prior_q_type"])
        else:
            df["yor_dir"] = "yor_na"
            df["mor_dir"] = "mor_na"
            df["prior_q_type"] = "q_na"
        w_atr = _weekly_atr_supertrend(d1)
        if w_atr is not None and not w_atr.empty:
            df = _asof_merge(df, w_atr, ["w_atr_trend"])
        else:
            df["w_atr_trend"] = "w_atr_na"
    else:
        df["prior_day_range_pct"] = "prior_range_na"
        df["atr_pct_bucket"] = "atr_pctl_na"
        df["yor_dir"] = "yor_na"
        df["mor_dir"] = "mor_na"
        df["prior_q_type"] = "q_na"
        df["w_atr_trend"] = "w_atr_na"

    df["w_atr_align"] = np.where(
        df["w_atr_trend"].isna() | (df["w_atr_trend"] == "w_atr_na"),
        "w_atr_na",
        np.where(
            ((df["side"] == "long") & (df["w_atr_trend"] == "w_atr_bull"))
            | ((df["side"] == "short") & (df["w_atr_trend"] == "w_atr_bear")),
            "w_atr_aligned",
            np.where(
                ((df["side"] == "long") & (df["w_atr_trend"] == "w_atr_bear"))
                | ((df["side"] == "short") & (df["w_atr_trend"] == "w_atr_bull")),
                "w_atr_opposed",
                "w_atr_na",
            ),
        ),
    )

    if family == "quarterly_breakout" and d1 is not None and len(d1) >= 8:
        pq = _prior_quarter_width_frame(d1)
        if not pq.empty:
            df = _asof_merge(df, pq, ["prior_q_width_q"])
        else:
            df["prior_q_width_q"] = "pqw_na"
    else:
        df["prior_q_width_q"] = "pqw_na"

    if family in ("v2b", "london_prior", "asia_range") and h1 is not None and d1 is not None:
        lor = _london_or_width_frame(h1, d1)
        if not lor.empty:
            df = _asof_merge(df, lor, ["london_or_width"])
        else:
            df["london_or_width"] = "lor_na"
    else:
        df["london_or_width"] = "lor_na"

    if family == "monday_or" and d1 is not None:
        mon = _monday_range_frame(d1)
        if not mon.empty:
            df = _asof_merge(df, mon, ["monday_range_pct"])
        else:
            df["monday_range_pct"] = "mon_na"
    else:
        df["monday_range_pct"] = "mon_na"

    if "month" not in df.columns:
        df["month"] = df["entry_ts"].dt.month
    return df


__all__ = [
    "Book",
    "STUDY",
    "PROFILE_HUB",
    "PHASE2_HUB",
    "MIN_N",
    "DEFAULT_BOOKS",
    "CONDITION_COLS",
    "COND_COL",
    "CAUSAL_LIVE_READY",
    "NEEDS_LIVE_PROXY",
    "load_campaigns",
    "annotate_campaigns",
    "feature_family",
]
