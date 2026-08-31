"""Daily / yearly HP condition profile for multi-month hold books.

Profiles calendar + HTF daily features against broker-like campaign tapes for
yearly ORB scaleout3 and ATR Supertrend DCA winners. Diagnostic only — not a
promotion gate.

Suited to daily-bar books that hold weeks–months (not the intraday 5m/hour
stack in ``intraday_condition_profile``).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.yearly_daily_condition_profile --email
  python -m live.yearly_daily_condition_profile --book xauusd_yorb --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .replay_audit import POINT_VALUES

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "yearly_daily_condition_profile"
NY = "America/New_York"
MIN_N = 12  # sparse yearly tapes; lower than intraday 40


@dataclass(frozen=True)
class Book:
    key: str
    label: str
    symbol: str
    fills: Path
    family: str  # yearly_orb | atr_st
    fee_per_unit: float = 1.50
    pnl_ccy: str = "USD"
    usd_fx_approx: Optional[float] = None
    point_value: Optional[float] = None


def _default_books() -> List[Book]:
    """Best-known books; --refresh-from-sizing can override yearly ORB paths."""
    fx_hub = REPO / "live" / "state" / "yearly_orb_sizing_sweep_fx_metals" / "states"
    fut_hub = REPO / "live" / "state" / "yearly_orb_sizing_sweep" / "states"
    fut_micro = REPO / "live" / "state" / "yearly_orb_sizing_sweep_micro" / "states"
    atr_hub = REPO / "live" / "state" / "atr_sizing_sweep" / "states"
    metals = REPO / "live" / "state" / "metals_futures_strats_sweep" / "states"

    def yorb(sym: str, slug: str, fee: float = 1.5, ccy: str = "USD", fx: Optional[float] = None) -> Book:
        low = sym.lower()
        # Prefer FX sizing hub, then banked metals/audjpy, then futures hubs.
        cands = [
            fx_hub / f"{low}_yorb_sizing_{slug}" / "fills.csv",
            metals / f"{low}_yearly_orb_scaleout3" / "fills.csv",
            REPO / "live" / "state" / "audjpy_futures_strats_sweep" / "states" / f"{low}_yearly_orb_scaleout3" / "fills.csv",
            fut_hub / f"{low}_yorb_sizing_{slug}" / "fills.csv",
            fut_micro / f"{low}_yorb_sizing_{slug}" / "fills.csv",
        ]
        fills = next((p for p in cands if p.exists()), cands[0])
        return Book(
            key=f"{low}_yorb",
            label=f"{sym} Yearly ORB {slug}",
            symbol=sym,
            fills=fills,
            family="yearly_orb",
            fee_per_unit=fee,
            pnl_ccy=ccy,
            usd_fx_approx=fx,
        )

    books = [
        yorb("AUDJPY", "L_1_1_1", fee=7.0, ccy="JPY", fx=110.0),
        yorb("XAUUSD", "L_1_1_1"),
        yorb("XAGUSD", "L_1_1_1"),
        yorb("NQ", "L_4_1_1"),
        yorb("ES", "L_4_2_1"),
        yorb("YM", "L_4_1_1"),
        Book(
            "nq_atr_ladder",
            "NQ ATR daily ladder 1/1/2/2/2/1 10-max intv2",
            "NQ",
            atr_hub / "nq_atr_sizing_daily_ladder112221_10max_intv2" / "fills.csv",
            "atr_st",
        ),
        Book(
            "mnq_atr_ladder",
            "MNQ ATR daily ladder 1/1/2/2/2/1 10-max intv2",
            "MNQ",
            atr_hub / "mnq_atr_sizing_daily_ladder112221_10max_intv2" / "fills.csv",
            "atr_st",
        ),
        Book(
            "xauusd_atr_ladder",
            "XAUUSD ATR daily ladder 1/1/2/2/2 10-max",
            "XAUUSD",
            metals / "xauusd_atr_daily_ladder112221_10max" / "fills.csv",
            "atr_st",
        ),
    ]
    return books


def refresh_yorb_from_sizing(books: List[Book], sizing_hub: Path) -> List[Book]:
    """Swap yearly_orb fills to each market's best N/S cell under sizing_hub."""
    summary = sizing_hub / "summary.csv"
    if not summary.exists():
        return books
    df = pd.read_csv(summary)
    if df.empty:
        return books
    best = (
        df.sort_values("net_over_stress_dd", ascending=False)
        .drop_duplicates("market", keep="first")
        .set_index("market")
    )
    out: List[Book] = []
    for b in books:
        if b.family != "yearly_orb":
            out.append(b)
            continue
        mkt = b.symbol.lower()
        if mkt not in best.index:
            out.append(b)
            continue
        slug = str(best.loc[mkt, "slug"])
        fills = sizing_hub / "states" / f"{mkt}_yorb_sizing_{slug}" / "fills.csv"
        if not fills.exists():
            out.append(b)
            continue
        out.append(
            Book(
                key=b.key,
                label=f"{b.symbol} Yearly ORB {slug} (sizing best)",
                symbol=b.symbol,
                fills=fills,
                family=b.family,
                fee_per_unit=b.fee_per_unit,
                pnl_ccy=b.pnl_ccy,
                usd_fx_approx=b.usd_fx_approx,
                point_value=b.point_value,
            )
        )
    return out


ENTRY_REASONS = {"entry", "runner_entry", "add", "scale_in", "dca_add"}


def load_campaigns(book: Book) -> pd.DataFrame:
    if not book.fills.exists():
        raise FileNotFoundError(book.fills)
    pv = float(book.point_value if book.point_value is not None else POINT_VALUES[book.symbol])
    fee = float(book.fee_per_unit)
    fills = pd.read_csv(book.fills)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True, errors="coerce")
    # Daily bars often lack TZ; treat naive as UTC midnight then convert.
    if fills["ts"].dt.tz is None:
        fills["ts"] = fills["ts"].dt.tz_localize("UTC")
    fills["ts"] = fills["ts"].dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    fills["reason"] = fills["reason"].astype(str)
    rows = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].isin(ENTRY_REASONS)]
        exits = group[~group["reason"].isin(ENTRY_REASONS)]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        # Qty-weighted average entry when adds at different prices (ATR DCA).
        eq = float((entries["price"] * entries["quantity"]).sum())
        eqty = float(entries["quantity"].sum())
        entry_px = eq / eqty if eqty else float(entry["price"])
        net_native = 0.0
        for _, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - entry_px if side == "long" else entry_px - px
            net_native += pts * pv * qty - fee * qty
        if book.pnl_ccy != "USD" and book.usd_fx_approx:
            net_usd = net_native / float(book.usd_fx_approx)
        else:
            net_usd = net_native
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
                "entry_qty": int(eqty),
                "hold_days": float((exits["ts"].max() - entry["ts"]).total_seconds() / 86400.0),
                "net_usd": float(net_usd),
                "net_native": float(net_native),
            }
        )
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    if out.empty:
        return out
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["month"] = out["entry_ts"].dt.month
    out["month_name"] = out["entry_ts"].dt.month_name()
    out["year"] = out["entry_ts"].dt.year
    out["quarter"] = out["entry_ts"].dt.quarter.map(lambda q: f"Q{q}")
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    return out


def _daily_path(symbol: str) -> Path:
    low = symbol.lower()
    for p in (
        REPO / "fx" / f"{low}_daily.csv",
        REPO / low / f"{low}_daily.csv",
        REPO / "nq" / "nq_daily.csv" if symbol == "NQ" else None,
        REPO / "mnq" / "mnq_daily.csv" if symbol == "MNQ" else None,
        REPO / "es" / "es_daily.csv" if symbol == "ES" else None,
        REPO / "ym" / "ym_daily.csv" if symbol == "YM" else None,
    ):
        if p is not None and p.exists():
            return p
    raise FileNotFoundError(f"no daily csv for {symbol}")


def load_daily(symbol: str) -> pd.DataFrame:
    path = _daily_path(symbol)
    df = pd.read_csv(path)
    ts_col = "date" if "date" in df.columns else ("ts" if "ts" in df.columns else "ts_event")
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    ts = ts.dt.tz_convert(NY)
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


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def build_daily_features(symbol: str) -> pd.DataFrame:
    """Causal daily feature frame valid from next session (asof-backward safe)."""
    d = load_daily(symbol).copy()
    tr = pd.concat(
        [
            d["high"] - d["low"],
            (d["high"] - d["close"].shift(1)).abs(),
            (d["low"] - d["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    d["atr_pct_252"] = d["atr14"].rolling(252, min_periods=60).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    d["sma50"] = d["close"].rolling(50).mean()
    d["sma200"] = d["close"].rolling(200).mean()
    d["ma_stack"] = np.where(
        (d["sma50"] > d["sma200"]) & (d["close"] > d["sma50"]),
        "ma_bull_stack",
        np.where(
            (d["sma50"] < d["sma200"]) & (d["close"] < d["sma50"]),
            "ma_bear_stack",
            "ma_mixed",
        ),
    )
    d["rsi14"] = rsi(d["close"], 14)
    d["rsi_bucket"] = pd.cut(
        d["rsi14"],
        bins=[-0.1, 30, 45, 55, 70, 100.1],
        labels=["rsi_le30", "rsi_30_45", "rsi_45_55", "rsi_55_70", "rsi_gt70"],
    ).astype(str)

    # Prior calendar year stats (fully known from Jan 1).
    d["cal_year"] = d["ts"].dt.year
    yearly = d.groupby("cal_year", sort=True).agg(
        y_open=("open", "first"),
        y_high=("high", "max"),
        y_low=("low", "min"),
        y_close=("close", "last"),
    )
    yearly["y_ret"] = yearly["y_close"] / yearly["y_open"] - 1.0
    yearly["y_mid"] = (yearly["y_high"] + yearly["y_low"]) / 2.0
    prior = yearly.shift(1)
    d = d.join(prior.add_prefix("prior_"), on="cal_year")

    # Jan–Mar opening range for *this* calendar year (known once April starts).
    # For asof at entry in Apr–Dec: use same-year OR built from completed Mar.
    or_rows = []
    for year, g in d.groupby("cal_year"):
        jm = g[g["ts"].dt.month.isin([1, 2, 3])]
        if jm.empty:
            continue
        or_rows.append(
            {
                "cal_year": int(year),
                "yor_high": float(jm["high"].max()),
                "yor_low": float(jm["low"].min()),
                "yor_ready_ts": pd.Timestamp(year=int(year), month=4, day=1, tz=NY),
            }
        )
    or_df = pd.DataFrame(or_rows)
    if not or_df.empty:
        d = d.merge(or_df, on="cal_year", how="left")
        d["yor_width"] = d["yor_high"] - d["yor_low"]
        d["yor_mid"] = (d["yor_high"] + d["yor_low"]) / 2.0
    else:
        d["yor_high"] = np.nan
        d["yor_low"] = np.nan
        d["yor_width"] = np.nan
        d["yor_mid"] = np.nan
        d["yor_ready_ts"] = pd.NaT

    # YTD return from Jan 1 open (causal through prior close).
    d["ytd_open"] = d.groupby("cal_year")["open"].transform("first")
    d["ytd_ret"] = d["close"] / d["ytd_open"] - 1.0

    # Shift so features are from last completed daily bar before entry.
    feat = d.copy()
    feat["ts"] = feat["ts"] + pd.Timedelta(days=1)
    return feat.sort_values("ts").reset_index(drop=True)


def _asof_merge(left: pd.DataFrame, right: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    l = left.sort_values("entry_ts").copy()
    r = right.sort_values("ts").copy()
    merged = pd.merge_asof(l, r, left_on="entry_ts", right_on="ts", direction="backward")
    out = left.copy()
    for c in cols:
        if c in merged.columns:
            out[c] = merged[c].values
    return out


def annotate_campaigns(campaigns: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "atr14",
        "atr_pct_252",
        "sma50",
        "sma200",
        "ma_stack",
        "rsi14",
        "rsi_bucket",
        "prior_y_ret",
        "prior_y_high",
        "prior_y_low",
        "prior_y_mid",
        "prior_y_close",
        "yor_high",
        "yor_low",
        "yor_width",
        "yor_mid",
        "ytd_ret",
        "close",
    ]
    df = _asof_merge(campaigns, feats, cols)

    # ATR percentile buckets
    df["atr_pct_bucket"] = pd.cut(
        df["atr_pct_252"],
        bins=[-0.01, 0.25, 0.50, 0.75, 1.01],
        labels=["atr_pctl_q1", "atr_pctl_q2", "atr_pctl_q3", "atr_pctl_q4"],
    ).astype(str)

    # Prior-year return tercile within book
    if df["prior_y_ret"].notna().sum() >= 9:
        try:
            df["prior_year_ret_bucket"] = pd.qcut(
                df["prior_y_ret"], 3, labels=["prior_yr_weak", "prior_yr_mid", "prior_yr_strong"], duplicates="drop"
            ).astype(str)
        except ValueError:
            df["prior_year_ret_bucket"] = "prior_yr_na"
    else:
        df["prior_year_ret_bucket"] = "prior_yr_na"

    # Prior-year close location in prior-year range
    span = (df["prior_y_high"] - df["prior_y_low"]).replace(0, np.nan)
    loc = (df["prior_y_close"] - df["prior_y_low"]) / span
    df["prior_year_loc"] = pd.cut(
        loc,
        bins=[-0.01, 0.33, 0.66, 1.01],
        labels=["prior_yr_lower", "prior_yr_middle", "prior_yr_upper"],
    ).astype(str)

    # MA alignment vs trade
    df["ma_align"] = np.where(
        df["ma_stack"].isna(),
        "ma_na",
        np.where(
            ((df["side"] == "long") & (df["ma_stack"] == "ma_bull_stack"))
            | ((df["side"] == "short") & (df["ma_stack"] == "ma_bear_stack")),
            "ma_aligned",
            np.where(
                ((df["side"] == "long") & (df["ma_stack"] == "ma_bear_stack"))
                | ((df["side"] == "short") & (df["ma_stack"] == "ma_bull_stack")),
                "ma_opposed",
                "ma_mixed",
            ),
        ),
    )

    # RSI vs side
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

    # Yearly OR geometry (only meaningful for Apr–Dec entries after OR ready)
    orw = df["yor_width"].replace(0, np.nan)
    df["or_ext_widths"] = np.where(
        df["side"] == "long",
        (df["entry_price"] - df["yor_high"]) / orw,
        (df["yor_low"] - df["entry_price"]) / orw,
    )
    df["or_ext_bucket"] = pd.cut(
        df["or_ext_widths"],
        bins=[-99, 0, 0.25, 0.75, 1.5, 99],
        labels=["inside_or", "ext_0_25", "ext_25_75", "ext_75_150", "ext_gt150"],
    ).astype(str)

    if df["yor_width"].notna().sum() >= 9:
        try:
            df["or_width_bucket"] = pd.qcut(
                df["yor_width"], 3, labels=["or_narrow", "or_mid", "or_wide"], duplicates="drop"
            ).astype(str)
        except ValueError:
            df["or_width_bucket"] = "or_na"
    else:
        df["or_width_bucket"] = "or_na"

    # Entry month bucket for trade window
    df["entry_month"] = df["month_name"]
    df["hold_bucket"] = pd.cut(
        df["hold_days"],
        bins=[-0.1, 10, 30, 90, 200, 9999],
        labels=["hold_le10d", "hold_10_30d", "hold_30_90d", "hold_90_200d", "hold_gt200d"],
    ).astype(str)

    # YTD return bucket
    df["ytd_bucket"] = pd.cut(
        df["ytd_ret"],
        bins=[-99, -0.05, 0.05, 0.15, 99],
        labels=["ytd_down5", "ytd_flat", "ytd_up5_15", "ytd_up15p"],
    ).astype(str)

    return df


CONDITION_COLS = [
    ("dow", "Day of week"),
    ("entry_month", "Entry month"),
    ("quarter", "Entry quarter"),
    ("week_of_month", "Week of month"),
    ("ma_align", "Daily MA50/200 vs trade"),
    ("ma_stack", "Daily MA stack"),
    ("rsi_bucket", "Daily RSI14 bucket"),
    ("rsi_align", "Daily RSI vs trade"),
    ("atr_pct_bucket", "ATR14 252d percentile"),
    ("prior_year_ret_bucket", "Prior calendar-year return"),
    ("prior_year_loc", "Prior-year close in range"),
    ("or_ext_bucket", "Extension past yearly OR (widths)"),
    ("or_width_bucket", "Yearly OR width tercile"),
    ("ytd_bucket", "YTD return at entry"),
    ("hold_bucket", "Hold duration (outcome; diagnostic)"),
    ("side", "Trade side"),
]


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
    p0 = baseline["wr"]
    n0 = baseline["n"]
    se = math.sqrt(max(p0 * (1 - p0) * (1 / n + 1 / max(n0, 1)), 1e-12))
    z = (wr - p0) / se if se > 0 else 0.0
    eq = nets.cumsum()
    stress = float(abs((eq - eq.cummax()).min())) if len(eq) else 0.0
    ns = (float(nets.sum()) / stress) if stress > 1e-9 else 0.0
    return {
        "n": n,
        "wins": wins,
        "wr": wr,
        "avg_net": avg,
        "net": float(nets.sum()),
        "stress": stress,
        "ns": ns,
        "pf": float(pf) if math.isfinite(pf) else 99.0,
        "wr_lift_pp": 100.0 * (wr - p0),
        "avg_lift": avg - baseline["avg_net"],
        "z_wr": z,
    }


def profile_book(df: pd.DataFrame, min_n: int = MIN_N) -> Tuple[pd.DataFrame, Dict[str, float], List[dict]]:
    baseline = {
        "n": int(len(df)),
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
            if pd.isna(val) or str(val) in {"nan", "None", "or_na", "prior_yr_na", "atr_na", "ma_na", "rsi_na"}:
                continue
            # Skip outcome-leaking hold buckets from notables later; still report.
            stats = summarize_bucket(g, baseline)
            if stats["n"] < min_n:
                continue
            row = {
                "condition": col,
                "condition_title": title,
                "bucket": str(val),
                **stats,
            }
            rows.append(row)
            # Notable heuristic: dual lift + (z or large avg lift); skip hold_bucket.
            if col == "hold_bucket":
                continue
            if (
                stats["wr_lift_pp"] > 0
                and stats["avg_lift"] > 0
                and (abs(stats["z_wr"]) >= 1.28 or stats["avg_lift"] >= 0.35 * abs(baseline["avg_net"] or 1.0))
            ):
                notables.append(row)
    return pd.DataFrame(rows), baseline, notables


def write_reports(
    hub: Path,
    book_results: Dict[str, dict],
    all_campaigns: pd.DataFrame,
    min_n: int,
) -> Tuple[Path, Path]:
    hub.mkdir(parents=True, exist_ok=True)
    all_campaigns.to_csv(hub / "all_campaigns.csv", index=False)
    notables_all = []
    lines = [
        "# Yearly / daily HP condition profile",
        "",
        "Diagnostic only — multi-month hold books on **daily** causal features.",
        f"Min bucket N={min_n}. Notable = dual WR+avg lift and (|z_WR|≥1.28 or avg lift ≥35% of |baseline avg|).",
        "Hold-duration buckets are outcome-correlated; shown but excluded from notables.",
        "",
        "## Books",
        "",
        "| Book | Family | n | WR | Avg $ | Net $ | fills |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for key, res in book_results.items():
        b = res["book"]
        bl = res["baseline"]
        lines.append(
            f"| {b.label} | {b.family} | {bl['n']} | {100*bl['wr']:.1f}% | "
            f"${bl['avg_net']:,.0f} | ${bl['net']:,.0f} | `{b.fills}` |"
        )
        res["buckets"].to_csv(hub / f"{key}_buckets.csv", index=False)
        res["campaigns"].to_csv(hub / f"{key}_campaigns.csv", index=False)
        for n in res["notables"]:
            notables_all.append({"book": key, **n})

    ndf = pd.DataFrame(notables_all)
    if not ndf.empty:
        ndf.to_csv(hub / "notables.csv", index=False)
    else:
        (hub / "notables.csv").write_text("book,condition,bucket\n", encoding="utf-8")

    lines.extend(["", "## Cross-book notables", ""])
    if ndf.empty:
        lines.append("_No buckets cleared the positive-lift heuristic._")
    else:
        lines.append("| condition | bucket | books | mean WR lift | mean avg lift |")
        lines.append("|---|---|---:|---:|---:|")
        for (cond, bucket), g in ndf.groupby(["condition", "bucket"]):
            lines.append(
                f"| {cond} | {bucket} | {g['book'].nunique()} | "
                f"{g['wr_lift_pp'].mean():+.1f}pp | ${g['avg_lift'].mean():+,.0f} |"
            )

    lines.extend(["", "## Per-book top positive buckets", ""])
    for key, res in book_results.items():
        lines.append(f"### {res['book'].label}")
        lines.append("")
        notes = sorted(res["notables"], key=lambda r: (-r["wr_lift_pp"], -r["avg_lift"]))[:12]
        if not notes:
            lines.append(f"_no positive dual-lift buckets with n≥{min_n}_")
        else:
            lines.append("| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
            for r in notes:
                lines.append(
                    f"| {r['condition']} | {r['bucket']} | {r['n']} | {100*r['wr']:.1f}% | "
                    f"{r['wr_lift_pp']:+.1f}pp | ${r['avg_net']:,.0f} | ${r['avg_lift']:+,.0f} | "
                    f"{r['pf']:.2f} | {r['z_wr']:+.2f} |"
                )
        lines.append("")

    lines.extend(
        [
            "## Caveats",
            "",
            "- Multiple comparisons: treat single-bucket spikes as hypotheses, not gates.",
            "- Yearly ORB sample is sparse (~1–4 campaigns/year); prefer signals that repeat across books.",
            "- Follow with null/OOS / broker-like filter tests before any size-up or sit-out.",
            "",
        ]
    )
    summary_path = hub / "SUMMARY.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = [
        "potions: yearly/daily HP condition profile complete",
        "",
        f"Hub: {hub.relative_to(REPO)}",
        f"Books: {len(book_results)} | min_n={min_n}",
        "",
    ]
    if ndf.empty:
        email.append("No cross-book notables cleared the dual-lift bar.")
    else:
        email.append("Top cross-book repeats:")
        top = (
            ndf.groupby(["condition", "bucket"])
            .agg(books=("book", "nunique"), wr_lift=("wr_lift_pp", "mean"), avg_lift=("avg_lift", "mean"))
            .sort_values(["books", "wr_lift"], ascending=False)
            .head(12)
        )
        for (cond, bucket), r in top.iterrows():
            email.append(
                f"  {cond}={bucket}  books={int(r['books'])}  "
                f"WRΔ={r['wr_lift']:+.1f}pp  avgΔ=${r['avg_lift']:+,.0f}"
            )
    email.append("")
    email.append("Stance: hypotheses only — not a promotion gate.")
    email_path = hub / "EMAIL.txt"
    email_path.write_text("\n".join(email) + "\n", encoding="utf-8")
    (hub / "baselines.json").write_text(
        json.dumps({k: v["baseline"] for k, v in book_results.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary_path, email_path


def run(*, books: Sequence[Book], hub: Path, min_n: int, email: bool) -> int:
    hub.mkdir(parents=True, exist_ok=True)
    book_results: Dict[str, dict] = {}
    all_parts: List[pd.DataFrame] = []
    for book in books:
        print(f"=== {book.key} ({book.fills}) ===", flush=True)
        if not book.fills.exists():
            print(f"  SKIP missing fills", flush=True)
            continue
        camps = load_campaigns(book)
        if camps.empty:
            print(f"  SKIP empty campaigns", flush=True)
            continue
        feats = build_daily_features(book.symbol)
        ann = annotate_campaigns(camps, feats)
        buckets, baseline, notables = profile_book(ann, min_n=min_n)
        book_results[book.key] = {
            "book": book,
            "campaigns": ann,
            "buckets": buckets,
            "baseline": baseline,
            "notables": notables,
        }
        all_parts.append(ann)
        print(
            f"  n={baseline['n']} WR={100*baseline['wr']:.1f}% avg=${baseline['avg_net']:,.0f} "
            f"notables={len(notables)}",
            flush=True,
        )
    if not book_results:
        raise SystemExit("No books produced campaigns")
    all_campaigns = pd.concat(all_parts, ignore_index=True)
    summary_path, email_path = write_reports(hub, book_results, all_campaigns, min_n)
    (hub / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "n_books": len(book_results)}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {summary_path}", flush=True)
    if email:
        send_email(
            subject="potions: yearly/daily HP condition profile complete",
            body=email_path.read_text(encoding="utf-8"),
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Daily/yearly HP condition profile")
    p.add_argument("--hub", type=Path, default=HUB)
    p.add_argument("--book", type=str, default="", help="Single book key (default: all)")
    p.add_argument("--min-n", type=int, default=MIN_N)
    p.add_argument(
        "--refresh-from-sizing",
        type=Path,
        default=None,
        help="Path to yearly_orb sizing hub; swap YORB fills to best N/S cell per market",
    )
    p.add_argument("--email", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    hub = args.hub if args.hub.is_absolute() else (REPO / args.hub)
    try:
        books = _default_books()
        if args.refresh_from_sizing is not None:
            sizing = args.refresh_from_sizing
            if not sizing.is_absolute():
                sizing = REPO / sizing
            books = refresh_yorb_from_sizing(books, sizing)
            # Also refresh from futures sizing hubs for NQ/ES/YM.
            for extra in (
                REPO / "live" / "state" / "yearly_orb_sizing_sweep",
                REPO / "live" / "state" / "yearly_orb_sizing_sweep_micro",
            ):
                books = refresh_yorb_from_sizing(books, extra)
        if args.book:
            books = [b for b in books if b.key == args.book]
            if not books:
                raise SystemExit(f"Unknown book {args.book}")
        return run(books=books, hub=hub, min_n=args.min_n, email=args.email)
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        if args.email:
            send_email(
                subject="potions: yearly/daily HP condition profile FAILED",
                body=f"Hub: {hub}\n\n{tb}",
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
