#!/usr/bin/env python3
"""Last-5-month NQ prior-opposed review, then OR-norm 2x and 4x on that window.

Campaign stress is the closed equity path of campaign nets (same score as the
HP size-up compare). It is not a fresh intrabar MTM audit.
"""
from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/tester/hsm/potions")
HUB = REPO / "live/state/nq_prior_opposed_last5m_or_norm"
UNITS = (
    REPO
    / "live/state/nq_v2b_prior_opposed_stpmc_resting_limit_through_20261011"
    / "states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv"
)
BARS = REPO / "nq/raw/nq_front_1m_20100606_20261011.csv"
NY = "America/New_York"
CUT = pd.Timestamp("2026-05-13", tz=NY)
START = pd.Timestamp("2021-03-04", tz=NY)


def score(nets: np.ndarray) -> dict:
    nets = np.asarray(nets, dtype=float)
    if nets.size == 0:
        return {"n": 0, "net": 0.0, "stress": 0.0, "ns": 0.0, "wr": 0.0, "avg": 0.0, "pf": 0.0}
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    stress = float(abs((eq - peak).min()))
    gains = float(nets[nets > 0].sum())
    losses = float(-nets[nets < 0].sum())
    pf = gains / losses if losses > 1e-9 else (99.0 if gains > 0 else 0.0)
    net = float(nets.sum())
    return {
        "n": int(nets.size),
        "net": net,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
        "wr": float((nets > 0).mean()),
        "avg": float(nets.mean()),
        "pf": pf,
    }


def or_buckets(path: Path) -> pd.DataFrame:
    print("loading OR bars", flush=True)
    df = pd.read_csv(path, usecols=["ts_event", "high", "low"])
    ts = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY)
    t = ts.dt.time
    mask = (t >= time(9, 30)) & (t < time(9, 45))
    sub = df.loc[mask].copy()
    sub["day"] = ts.loc[mask].dt.date
    og = sub.groupby("day", sort=True).agg(or_high=("high", "max"), or_low=("low", "min"))
    og["or_width"] = og["or_high"] - og["or_low"]
    og["pct"] = og["or_width"].rolling(60, min_periods=20).apply(
        lambda x: float(pd.Series(x).rank(pct=True).iloc[-1]), raw=False
    )
    og["or15_width_pct"] = pd.cut(
        og["pct"],
        bins=[-0.01, 0.33, 0.66, 1.01],
        labels=["or_narrow", "or_norm", "or_wide"],
    ).astype(str)
    og.loc[og["pct"].isna(), "or15_width_pct"] = "or_na"
    return og.reset_index()


def campaigns() -> pd.DataFrame:
    u = pd.read_csv(UNITS)
    u["entry_ts"] = pd.to_datetime(u["entry_ts"], utc=True).dt.tz_convert(NY)
    g = (
        u.groupby("trade_id", sort=False)
        .agg(
            entry_ts=("entry_ts", "min"),
            net_usd=("net_usd", "sum"),
            direction=("direction", "first"),
            units=("unit_id", "count"),
        )
        .reset_index()
    )
    g = g[g["entry_ts"] >= START].sort_values("entry_ts").reset_index(drop=True)
    g["day"] = g["entry_ts"].dt.date
    g["month"] = g["entry_ts"].dt.strftime("%Y-%m")
    return g


def sized(df: pd.DataFrame, mult: float) -> np.ndarray:
    nets = df["net_usd"].to_numpy(float)
    if mult == 1.0:
        return nets
    out = nets.copy()
    m = df["or15_width_pct"].eq("or_norm").to_numpy()
    out[m] = out[m] * mult
    return out


def row(label: str, window: str, df: pd.DataFrame, mult: float = 1.0, bucket: str = "all") -> dict:
    use = df if bucket == "all" else df[df["or15_width_pct"] == bucket]
    sc = score(sized(use, mult) if bucket == "all" else use["net_usd"].to_numpy(float) * mult)
    return {
        "window": window,
        "slice": label,
        "mult": mult,
        "bucket": bucket,
        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in sc.items()},
    }


def main() -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    og = or_buckets(BARS)
    camps = campaigns().merge(og[["day", "or_width", "pct", "or15_width_pct"]], on="day", how="left")
    camps["or15_width_pct"] = camps["or15_width_pct"].fillna("or_na")
    camps.to_csv(HUB / "campaigns.csv", index=False)

    prior = camps[camps["entry_ts"] < CUT]
    recent = camps[camps["entry_ts"] >= CUT]
    rows = []
    for name, df in (("full_2021_on", camps), ("before_2026_05_13", prior), ("last_5_months", recent)):
        for mult in (1.0, 2.0, 4.0):
            rows.append(row("whole_book_or_norm_boost", name, df, mult))
        for bucket in ("or_narrow", "or_norm", "or_wide"):
            rows.append(row("bucket_only", name, df, 1.0, bucket))
    for month, df in recent.groupby("month"):
        rows.append(row("month_1x", month, df, 1.0))
        rows.append(row("month_or_norm_2x", month, df, 2.0))
        rows.append(row("month_or_norm_4x", month, df, 4.0))
        mix = df["or15_width_pct"].value_counts(normalize=True)
        rows.append(
            {
                "window": month,
                "slice": "or_mix",
                "mult": 1.0,
                "bucket": "mix",
                "n": int(len(df)),
                "net": round(float(df["net_usd"].sum()), 2),
                "or_norm_share": round(float(mix.get("or_norm", 0.0)), 4),
                "or_wide_share": round(float(mix.get("or_wide", 0.0)), 4),
                "or_narrow_share": round(float(mix.get("or_narrow", 0.0)), 4),
                "median_or_width": round(float(df["or_width"].median()), 2) if df["or_width"].notna().any() else None,
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(HUB / "summary.csv", index=False)

    def grab(window, slice_, mult=1.0, bucket="all"):
        hit = out[(out["window"] == window) & (out["slice"] == slice_) & (out["mult"] == mult) & (out["bucket"] == bucket)]
        return hit.iloc[0].to_dict() if len(hit) else {}

    prior_mix = prior["or15_width_pct"].value_counts(normalize=True)
    recent_mix = recent["or15_width_pct"].value_counts(normalize=True)
    note = {
        "cut": "2026-05-13",
        "prior_n": int(len(prior)),
        "recent_n": int(len(recent)),
        "prior_median_or_width": None if prior.empty else round(float(prior["or_width"].median()), 2),
        "recent_median_or_width": None if recent.empty else round(float(recent["or_width"].median()), 2),
        "prior_or_norm_share": round(float(prior_mix.get("or_norm", 0.0)), 4),
        "recent_or_norm_share": round(float(recent_mix.get("or_norm", 0.0)), 4),
        "prior_or_wide_share": round(float(prior_mix.get("or_wide", 0.0)), 4),
        "recent_or_wide_share": round(float(recent_mix.get("or_wide", 0.0)), 4),
        "prior_1x": grab("before_2026_05_13", "whole_book_or_norm_boost", 1.0),
        "recent_1x": grab("last_5_months", "whole_book_or_norm_boost", 1.0),
        "recent_2x": grab("last_5_months", "whole_book_or_norm_boost", 2.0),
        "recent_4x": grab("last_5_months", "whole_book_or_norm_boost", 4.0),
        "prior_or_norm": grab("before_2026_05_13", "bucket_only", 1.0, "or_norm"),
        "recent_or_norm": grab("last_5_months", "bucket_only", 1.0, "or_norm"),
        "prior_or_wide": grab("before_2026_05_13", "bucket_only", 1.0, "or_wide"),
        "recent_or_wide": grab("last_5_months", "bucket_only", 1.0, "or_wide"),
        "full_1x": grab("full_2021_on", "whole_book_or_norm_boost", 1.0),
        "full_2x": grab("full_2021_on", "whole_book_or_norm_boost", 2.0),
        "full_4x": grab("full_2021_on", "whole_book_or_norm_boost", 4.0),
    }
    (HUB / "RESULT.json").write_text(json.dumps(note, indent=2, default=str))
    print(json.dumps(note, indent=2, default=str))


if __name__ == "__main__":
    main()
