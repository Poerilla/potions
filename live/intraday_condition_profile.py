"""Condition profile for running intraday systems.

Joins broker-like campaign tapes to calendar / HTF / 5m features and ranks
bucket lift vs book baseline. Diagnostic only — not a filter promotion gate.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.intraday_condition_profile --email
  python -m live.intraday_condition_profile --book usdjpy_monday_or --email
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import JPY_USD, MARKETS, REPO, _usd_norm
from .notify_email import send_email

NY = "America/New_York"
HUB = REPO / "live" / "state" / "intraday_condition_profile"
CACHE = REPO / "live" / "state" / "_cache" / "bars"
MIN_N = 40


@dataclass(frozen=True)
class Book:
    key: str
    label: str
    symbol: str
    fills: Path
    family: str
    fee_override: Optional[float] = None


# Research tapes aligned to currently running intraday demos (not thin live fills).
DEFAULT_BOOKS: Tuple[Book, ...] = (
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
        "NAS100 v2b London ungated S_1_1_3 (index OR proxy)",
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
        "eurusd_st_pmc_3r",
        "EURUSD hourly ST+PMC 50/150 3r",
        "EURUSD",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/eurusd/states/eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        "st_pmc",
        fee_override=1.5,
    ),
)


def _market(symbol: str):
    return MARKETS[symbol.upper()]


def load_campaigns(book: Book) -> pd.DataFrame:
    market = _market(book.symbol)
    fee = float(book.fee_override if book.fee_override is not None else market.fee_per_unit)
    fills = pd.read_csv(book.fills)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    rows = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        net_native = 0.0
        for _, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - entry_px if side == "long" else entry_px - px
            net_native += pts * market.point_value * qty - fee * qty
        rows.append(
            {
                "book": book.key,
                "family": book.family,
                "symbol": book.symbol,
                "trade_id": str(trade_id),
                "side": side,
                "entry_ts": pd.Timestamp(entry["ts"]),
                "exit_ts": pd.Timestamp(exits["ts"].max()),
                "entry_price": entry_px,
                "net_usd": float(_usd_norm(net_native, market.quote)),
            }
        )
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    if out.empty:
        return out
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["hour_ny"] = out["entry_ts"].dt.hour
    out["month"] = out["entry_ts"].dt.month
    out["year"] = out["entry_ts"].dt.year
    # Week of month: 1..5 from NY calendar day
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    return out


def _read_ohlcv_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts_col = "ts_event" if "ts_event" in df.columns else ("date" if "date" in df.columns else None)
    if ts_col is None:
        raise ValueError("no ts column in %s" % path)
    if ts_col == "date":
        ts = pd.to_datetime(df["date"]).dt.tz_localize(NY)
    else:
        ts = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert(NY)
    out = pd.DataFrame(
        {
            "ts": ts,
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0.0),
        }
    ).dropna(subset=["ts", "close"])
    return out.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.set_index("ts").sort_index()
    ohlc = g.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return ohlc.dropna(subset=["close"]).reset_index().rename(columns={"index": "ts"})


def ensure_tf_bars(symbol: str, tf: str) -> pd.DataFrame:
    """Return NY-tz OHLCV for tf in {5m,1h,1d}. Cache parquet under _cache/bars."""
    sym = symbol.lower()
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / ("%s_%s.parquet" % (sym, tf))
    native = {
        "5m": REPO / "fx" / ("%s_5m.csv" % sym),
        "1h": REPO / "fx" / ("%s_1h.csv" % sym),
        "1d": REPO / "fx" / ("%s_daily.csv" % sym),
    }[tf]
    one_m = REPO / "fx" / ("%s_1m.csv" % sym)

    def _usable(path: Path, min_rows: int) -> bool:
        if not path.exists():
            return False
        try:
            n = sum(1 for _ in path.open()) - 1
        except Exception:
            return False
        return n >= min_rows

    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
        if len(df) >= (200 if tf != "1d" else 100):
            return df

    if tf == "1d" and native.exists():
        df = _read_ohlcv_csv(native)
        df.to_parquet(cache_path, index=False)
        return df

    if tf == "1h" and _usable(native, 5_000):
        df = _read_ohlcv_csv(native)
        df.to_parquet(cache_path, index=False)
        return df

    if tf == "5m" and native.exists() and _usable(native, 20_000):
        df = _read_ohlcv_csv(native)
        df.to_parquet(cache_path, index=False)
        return df

    if not one_m.exists():
        raise FileNotFoundError("need %s or usable native %s for %s" % (one_m, native, symbol))

    print("  resampling %s 1m → %s (cache %s) ..." % (symbol, tf, cache_path.name), flush=True)
    # Chunked read to keep memory bounded.
    chunks = []
    for chunk in pd.read_csv(
        one_m,
        usecols=lambda c: c in {"ts_event", "open", "high", "low", "close", "volume"},
        chunksize=400_000,
    ):
        chunk["ts"] = pd.to_datetime(chunk["ts_event"], utc=True).dt.tz_convert(NY)
        chunk = chunk.drop(columns=["ts_event"])
        chunk["volume"] = pd.to_numeric(chunk.get("volume", 0), errors="coerce").fillna(0.0)
        for col in ("open", "high", "low", "close"):
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        chunks.append(chunk[["ts", "open", "high", "low", "close", "volume"]])
    one = pd.concat(chunks, ignore_index=True).dropna(subset=["ts", "close"]).sort_values("ts")
    one = one.drop_duplicates("ts", keep="last")
    rule = {"5m": "5min", "1h": "1h", "1d": "1D"}[tf]
    df = _resample_ohlcv(one, rule)
    df.to_parquet(cache_path, index=False)
    print("  cached %s rows=%s" % (cache_path.name, f"{len(df):,}"), flush=True)
    return df


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume.fillna(0.0)).cumsum()


def build_feature_frames(symbol: str) -> Dict[str, pd.DataFrame]:
    h1 = ensure_tf_bars(symbol, "1h")
    d1 = ensure_tf_bars(symbol, "1d")
    m5 = ensure_tf_bars(symbol, "5m")

    h = h1.copy()
    h["rsi14"] = rsi(h["close"], 14)
    h["obv"] = obv(h["close"], h["volume"])
    h["obv_ma20"] = h["obv"].rolling(20).mean()
    h["obv_cross"] = np.where(
        h["obv"] > h["obv_ma20"],
        "obv_above_ma",
        np.where(h["obv"] < h["obv_ma20"], "obv_below_ma", "obv_flat"),
    )
    h["rsi_bucket"] = pd.cut(
        h["rsi14"],
        bins=[-0.1, 30, 45, 55, 70, 100.1],
        labels=["rsi_le30", "rsi_30_45", "rsi_45_55", "rsi_55_70", "rsi_gt70"],
    ).astype(str)

    # Causal: shift so features are from last completed hour before entry.
    h_feat = h[["ts", "rsi14", "rsi_bucket", "obv_cross", "close"]].copy()
    h_feat["ts"] = h_feat["ts"] + pd.Timedelta(hours=1)

    d = d1.copy()
    prev = d[["high", "low", "close"]].shift(1)
    d["prev_day_high"] = prev["high"]
    d["prev_day_low"] = prev["low"]
    d["prev_day_mid"] = (prev["high"] + prev["low"]) / 2.0
    tr = pd.concat(
        [
            (d["high"] - d["low"]),
            (d["high"] - d["close"].shift(1)).abs(),
            (d["low"] - d["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["atr14"] = tr.rolling(14).mean().shift(1)
    # Week / month ranges from completed prior periods (causal).
    d["week"] = d["ts"].dt.to_period("W-SUN")
    d["month"] = d["ts"].dt.to_period("M")
    week_hl = d.groupby("week", sort=False).agg(w_high=("high", "max"), w_low=("low", "min"))
    month_hl = d.groupby("month", sort=False).agg(m_high=("high", "max"), m_low=("low", "min"))
    d = d.join(week_hl.shift(1), on="week")
    d = d.join(month_hl.shift(1), on="month")
    d["prev_week_mid"] = (d["w_high"] + d["w_low"]) / 2.0
    d["prev_month_mid"] = (d["m_high"] + d["m_low"]) / 2.0
    d_feat = d[
        [
            "ts",
            "prev_day_high",
            "prev_day_low",
            "prev_day_mid",
            "prev_week_mid",
            "w_high",
            "w_low",
            "prev_month_mid",
            "m_high",
            "m_low",
            "atr14",
        ]
    ].copy()
    # Valid from next day open: keep date as midnight NY for asof.
    d_feat["ts"] = d_feat["ts"].dt.normalize() + pd.Timedelta(days=1)

    m = m5.copy()
    m["sma9"] = m["close"].rolling(9).mean()
    m["sma21"] = m["close"].rolling(21).mean()
    m["ma_state"] = np.where(m["sma9"] > m["sma21"], "ma_bull", np.where(m["sma9"] < m["sma21"], "ma_bear", "ma_flat"))
    # Cross on last completed 5m bar: bullish cross = 9 crossed above 21 this bar.
    prev_state = m["ma_state"].shift(1)
    m["ma_cross"] = np.where(
        (m["ma_state"] == "ma_bull") & (prev_state != "ma_bull"),
        "ma_cross_up",
        np.where((m["ma_state"] == "ma_bear") & (prev_state != "ma_bear"), "ma_cross_down", "ma_no_cross"),
    )
    m_feat = m[["ts", "ma_state", "ma_cross", "close"]].copy()
    m_feat["ts"] = m_feat["ts"] + pd.Timedelta(minutes=5)

    return {"h1": h_feat.sort_values("ts"), "d1": d_feat.sort_values("ts"), "m5": m_feat.sort_values("ts"), "d_raw": d}


def _asof_merge(left: pd.DataFrame, right: pd.DataFrame, cols: Sequence[str], suffix: str = "") -> pd.DataFrame:
    l = left.sort_values("entry_ts").copy()
    r = right.sort_values("ts").copy()
    merged = pd.merge_asof(l, r, left_on="entry_ts", right_on="ts", direction="backward")
    keep = [c for c in cols if c in merged.columns]
    rename = {c: ("%s%s" % (c, suffix) if suffix else c) for c in keep}
    out = left.copy()
    for src, dst in rename.items():
        out[dst] = merged[src].values
    return out


def annotate_campaigns(campaigns: pd.DataFrame, feats: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = campaigns.copy()
    df = _asof_merge(df, feats["h1"], ["rsi14", "rsi_bucket", "obv_cross"])
    df = _asof_merge(df, feats["d1"], ["prev_day_mid", "prev_week_mid", "prev_month_mid", "atr14", "w_high", "w_low", "m_high", "m_low"])
    df = _asof_merge(df, feats["m5"], ["ma_state", "ma_cross"])

    # ATR quartile within book (causal rolling would be nicer; static quartile is ok for profile).
    if df["atr14"].notna().sum() >= 20:
        try:
            df["atr_q"] = pd.qcut(df["atr14"], 4, labels=["atr_q1", "atr_q2", "atr_q3", "atr_q4"], duplicates="drop").astype(str)
        except ValueError:
            df["atr_q"] = "atr_na"
    else:
        df["atr_q"] = "atr_na"

    def half(px: pd.Series, mid: pd.Series) -> pd.Series:
        return np.where(px.isna() | mid.isna(), "range_na", np.where(px < mid, "lower_half", "upper_half"))

    df["day_half"] = half(df["entry_price"], df["prev_day_mid"])
    df["week_half"] = half(df["entry_price"], df["prev_week_mid"])
    df["month_half"] = half(df["entry_price"], df["prev_month_mid"])

    # Alignment: bullish long in lower half / bearish short in upper half.
    def align(side: pd.Series, half_col: pd.Series, name: str) -> pd.Series:
        good = ((side == "long") & (half_col == "lower_half")) | ((side == "short") & (half_col == "upper_half"))
        bad = ((side == "long") & (half_col == "upper_half")) | ((side == "short") & (half_col == "lower_half"))
        return np.where(half_col == "range_na", "%s_na" % name, np.where(good, "%s_aligned" % name, np.where(bad, "%s_opposed" % name, "%s_na" % name)))

    df["day_half_align"] = align(df["side"], df["day_half"], "day")
    df["week_half_align"] = align(df["side"], df["week_half"], "week")
    df["month_half_align"] = align(df["side"], df["month_half"], "month")

    # 5m MA alignment with trade direction.
    df["ma5_align"] = np.where(
        df["ma_state"].isna(),
        "ma_na",
        np.where(
            ((df["side"] == "long") & (df["ma_state"] == "ma_bull")) | ((df["side"] == "short") & (df["ma_state"] == "ma_bear")),
            "ma_aligned",
            np.where(
                ((df["side"] == "long") & (df["ma_state"] == "ma_bear")) | ((df["side"] == "short") & (df["ma_state"] == "ma_bull")),
                "ma_opposed",
                "ma_flat",
            ),
        ),
    )
    df["ma5_cross_align"] = np.where(
        df["ma_cross"].isna() | (df["ma_cross"] == "ma_no_cross"),
        "cross_none",
        np.where(
            ((df["side"] == "long") & (df["ma_cross"] == "ma_cross_up"))
            | ((df["side"] == "short") & (df["ma_cross"] == "ma_cross_down")),
            "cross_aligned",
            "cross_opposed",
        ),
    )
    # Hourly RSI / OBV alignment
    df["rsi_align"] = np.where(
        df["rsi14"].isna(),
        "rsi_na",
        np.where(
            ((df["side"] == "long") & (df["rsi14"] >= 55)) | ((df["side"] == "short") & (df["rsi14"] <= 45)),
            "rsi_with_side",
            np.where(
                ((df["side"] == "long") & (df["rsi14"] <= 45)) | ((df["side"] == "short") & (df["rsi14"] >= 55)),
                "rsi_against_side",
                "rsi_neutral",
            ),
        ),
    )
    df["obv_align"] = np.where(
        df["obv_cross"].isna(),
        "obv_na",
        np.where(
            ((df["side"] == "long") & (df["obv_cross"] == "obv_above_ma"))
            | ((df["side"] == "short") & (df["obv_cross"] == "obv_below_ma")),
            "obv_aligned",
            np.where(
                ((df["side"] == "long") & (df["obv_cross"] == "obv_below_ma"))
                | ((df["side"] == "short") & (df["obv_cross"] == "obv_above_ma")),
                "obv_opposed",
                "obv_flat",
            ),
        ),
    )
    return df


def summarize_bucket(df: pd.DataFrame, baseline: Dict[str, float]) -> Dict[str, float]:
    n = int(len(df))
    if n == 0:
        return {"n": 0}
    nets = df["net_usd"]
    wins = int((nets > 0).sum())
    gross_win = float(nets[nets > 0].sum())
    gross_loss = float(-nets[nets <= 0].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)
    wr = wins / n
    avg = float(nets.mean())
    # Two-proportion z for WR vs baseline (large-sample).
    p0 = baseline["wr"]
    n0 = baseline["n"]
    se = math.sqrt(max(p0 * (1 - p0) * (1 / n + 1 / max(n0, 1)), 1e-12))
    z = (wr - p0) / se if se > 0 else 0.0
    return {
        "n": n,
        "wins": wins,
        "wr": wr,
        "avg_net": avg,
        "net": float(nets.sum()),
        "pf": float(pf) if math.isfinite(pf) else 99.0,
        "wr_lift_pp": 100.0 * (wr - p0),
        "avg_lift": avg - baseline["avg_net"],
        "z_wr": z,
    }


CONDITION_COLS = [
    ("dow", "Day of week"),
    ("week_of_month", "Week of month"),
    ("hour_ny", "Entry hour (NY)"),
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


def profile_book(df: pd.DataFrame, min_n: int = MIN_N) -> Tuple[pd.DataFrame, Dict[str, float], List[dict]]:
    baseline = {
        "n": float(len(df)),
        "wr": float((df["net_usd"] > 0).mean()) if len(df) else 0.0,
        "avg_net": float(df["net_usd"].mean()) if len(df) else 0.0,
        "net": float(df["net_usd"].sum()) if len(df) else 0.0,
    }
    rows = []
    notables = []
    for col, title in CONDITION_COLS:
        if col not in df.columns:
            continue
        for val, g in df.groupby(col, dropna=False):
            stats = summarize_bucket(g, baseline)
            if stats.get("n", 0) < min_n:
                continue
            row = {
                "condition": title,
                "bucket": str(val),
                **stats,
            }
            rows.append(row)
            # Notable: min N, material lift, z>|1.64| (~90%) OR avg_lift large vs |baseline avg|
            scale = max(abs(baseline["avg_net"]), 1.0)
            notable = (
                stats["n"] >= min_n
                and (
                    abs(stats["z_wr"]) >= 1.64
                    or abs(stats["avg_lift"]) >= 0.35 * scale
                )
                and (stats["avg_lift"] > 0 or stats["wr_lift_pp"] > 3.0)
            )
            if notable and stats["avg_lift"] > 0 and stats["wr_lift_pp"] > 0:
                notables.append({**row, "book": df["book"].iloc[0], "symbol": df["symbol"].iloc[0]})
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["avg_lift", "wr_lift_pp"], ascending=False).reset_index(drop=True)
    return table, baseline, notables


def render_summary(
    all_tables: Dict[str, pd.DataFrame],
    baselines: Dict[str, dict],
    notables: List[dict],
    books: Sequence[Book],
    min_n: int = MIN_N,
) -> str:
    lines = [
        "# Intraday condition profile",
        "",
        "Diagnostic profile of calendar / HTF / 5m conditions vs broker-like campaign outcomes",
        "for research tapes aligned to **running intraday demos**. Not a promotion gate.",
        "",
        "Features (causal asof): day-of-week, week-of-month, NY hour, 5m SMA9/21 state+cross,",
        "hourly RSI14 + OBV×MA20, daily ATR14 quartiles, entry vs prior day/week/month range half",
        "(aligned = long in lower half / short in upper half).",
        "",
        "Significance heuristic: n≥%d, positive WR and avg-net lift, and (|z_WR|≥1.64 or avg lift ≥35%% of |baseline avg|)."
        % min_n,
        "",
        "## Books",
        "",
    ]
    for b in books:
        base = baselines.get(b.key, {})
        lines.append(
            "- **%s** (`%s`): n=%s WR=%.1f%% avg=$%.2f net=$%.0f"
            % (
                b.label,
                b.key,
                int(base.get("n", 0)),
                100.0 * base.get("wr", 0.0),
                base.get("avg_net", 0.0),
                base.get("net", 0.0),
            )
        )
    lines.extend(["", "## Cross-book notables (positive lift)", ""])
    if not notables:
        lines.append("_No buckets cleared the positive-lift heuristic._")
    else:
        # Aggregate by condition/bucket across books
        ndf = pd.DataFrame(notables)
        for (cond, bucket), g in ndf.groupby(["condition", "bucket"]):
            books_hit = ", ".join(sorted(g["book"].unique()))
            lines.append(
                "- **%s = %s** — %d book(s): %s (median WR lift %+0.1fpp, median avg lift $%+.2f)"
                % (
                    cond,
                    bucket,
                    g["book"].nunique(),
                    books_hit,
                    g["wr_lift_pp"].median(),
                    g["avg_lift"].median(),
                )
            )
    lines.extend(["", "## Per-book top positive buckets", ""])
    for b in books:
        table = all_tables.get(b.key)
        lines.append("### %s" % b.label)
        if table is None or table.empty:
            lines.append("_insufficient data_")
            lines.append("")
            continue
        pos = table[(table["avg_lift"] > 0) & (table["wr_lift_pp"] > 0)].head(12)
        if pos.empty:
            lines.append("_no positive dual-lift buckets with n≥%d_" % min_n)
        else:
            lines.append("| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
            for _, r in pos.iterrows():
                lines.append(
                    "| %s | %s | %d | %.1f%% | %+0.1fpp | %.2f | %+.2f | %.2f | %+.2f |"
                    % (
                        r["condition"],
                        r["bucket"],
                        int(r["n"]),
                        100.0 * r["wr"],
                        r["wr_lift_pp"],
                        r["avg_net"],
                        r["avg_lift"],
                        r["pf"],
                        r["z_wr"],
                    )
                )
        lines.append("")
    lines.extend(
        [
            "## Caveats",
            "",
            "- Multiple comparisons: treat single-bucket spikes as hypotheses, not gates.",
            "- Live demo tapes are too short; this uses research/broker-like fills.",
            "- NAS100 live v2b ungated proxied by London ungated research tape.",
            "- SPX500 omitted (no long 1m research series in `fx/`).",
            "",
        ]
    )
    return "\n".join(lines)


def phone_email(summary_path: Path, notables: List[dict], baselines: Dict[str, dict]) -> str:
    lines = [
        "potions: intraday condition profile complete",
        "hub: %s" % HUB,
        "",
    ]
    if not notables:
        lines.append("No cross-book positive-lift notables cleared the heuristic.")
    else:
        ndf = pd.DataFrame(notables)
        top = (
            ndf.groupby(["condition", "bucket"])
            .agg(books=("book", "nunique"), wr_lift=("wr_lift_pp", "median"), avg_lift=("avg_lift", "median"))
            .sort_values(["books", "avg_lift"], ascending=False)
            .head(8)
        )
        lines.append("Top hypotheses:")
        for (cond, bucket), r in top.iterrows():
            lines.append(
                "- %s=%s · %d books · WR%+0.1fpp · avg$%+.1f"
                % (cond, bucket, int(r["books"]), r["wr_lift"], r["avg_lift"])
            )
    lines.append("")
    lines.append("Books profiled: %d" % len(baselines))
    lines.append("See SUMMARY.md for full tables.")
    lines.append("")
    lines.append(str(summary_path))
    return "\n".join(lines)


def run(books: Sequence[Book], email: bool = False, min_n: int = MIN_N) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    all_tables: Dict[str, pd.DataFrame] = {}
    baselines: Dict[str, dict] = {}
    notables: List[dict] = []
    annotated_frames = []

    feat_cache: Dict[str, Dict[str, pd.DataFrame]] = {}
    for book in books:
        print("== %s ==" % book.key, flush=True)
        if not book.fills.exists():
            print("  SKIP missing fills %s" % book.fills, flush=True)
            continue
        campaigns = load_campaigns(book)
        print("  campaigns=%d" % len(campaigns), flush=True)
        if campaigns.empty:
            continue
        if book.symbol not in feat_cache:
            print("  building features for %s ..." % book.symbol, flush=True)
            feat_cache[book.symbol] = build_feature_frames(book.symbol)
        ann = annotate_campaigns(campaigns, feat_cache[book.symbol])
        table, baseline, book_notes = profile_book(ann, min_n=min_n)
        all_tables[book.key] = table
        baselines[book.key] = baseline
        notables.extend(book_notes)
        annotated_frames.append(ann)
        out_csv = HUB / ("%s_buckets.csv" % book.key)
        table.to_csv(out_csv, index=False)
        ann.to_csv(HUB / ("%s_campaigns.csv" % book.key), index=False)
        print("  baseline WR=%.1f%% avg=$%.2f notables=%d" % (100 * baseline["wr"], baseline["avg_net"], len(book_notes)), flush=True)

    if annotated_frames:
        pd.concat(annotated_frames, ignore_index=True).to_csv(HUB / "all_campaigns.csv", index=False)
    if notables:
        pd.DataFrame(notables).to_csv(HUB / "notables.csv", index=False)

    summary = render_summary(all_tables, baselines, notables, books, min_n=min_n)
    summary_path = HUB / "SUMMARY.md"
    summary_path.write_text(summary, encoding="utf-8")
    (HUB / "baselines.json").write_text(json.dumps(baselines, indent=2), encoding="utf-8")
    email_body = phone_email(summary_path, notables, baselines)
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    if email:
        send_email(subject="potions: intraday condition profile complete", body=email_body)
        print("emailed completion summary", flush=True)
    print("wrote %s" % summary_path, flush=True)
    return summary_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", default=[], help="Book key (repeatable). Default: all.")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--min-n", type=int, default=MIN_N)
    args = parser.parse_args(argv)
    books = DEFAULT_BOOKS
    if args.book:
        wanted = set(args.book)
        books = tuple(b for b in DEFAULT_BOOKS if b.key in wanted)
        missing = wanted - {b.key for b in books}
        if missing:
            raise SystemExit("unknown books: %s" % sorted(missing))
    run(books, email=bool(args.email), min_n=int(args.min_n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
