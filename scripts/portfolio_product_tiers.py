#!/usr/bin/env python3
"""Multi-tier portfolio products: 5% / 10% / 15% / 20% target CAGR.

Same sleeve universe; different risk budgets + profit-lock thresholds.
Tier B (10%) matches the prior target_10pct_portfolio baseline.

Outputs: live/state/portfolio_product_tiers/
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
METRICS = REPO / "live/state/institutional_strategy_metrics/metrics.csv"
OUT = REPO / "live/state/portfolio_product_tiers"
LEGACY_OUT = REPO / "live/state/target_10pct_portfolio"

POINT_VALUE = {
    "NQ": 20.0,
    "MNQ": 2.0,
    "ES": 50.0,
    "MES": 5.0,
    "YM": 5.0,
    "MYM": 0.5,
    "EURUSD": 100_000.0,
    "GBPUSD": 100_000.0,
    "USDJPY": 100_000.0,
    "AUDJPY": 100_000.0,
    "XAUUSD": 100.0,
    "XAGUSD": 1000.0,
}
JPY_INSTRUMENTS = {"USDJPY", "AUDJPY"}
JPY_USD = 110.0
PORTFOLIO_CAPITAL = 300_000.0

# Shared sleeve metadata (weights come from TIER_WEIGHTS)
SLEEVE_META: dict[str, dict[str, str]] = {
    "nq_v2b": {
        "name": "NQ prior-opposed v2b resting-limit (hour-complete)",
        "bucket": "high",
        "status": "live/paper eligible",
    },
    "mnq_v2b": {
        "name": "MNQ prior-opposed v2b resting-limit (hour-complete)",
        "bucket": "high",
        "status": "micro mirror",
    },
    "ym_v2b": {
        "name": "YM prior-opposed v2b resting-limit (hour-complete)",
        "bucket": "high",
        "status": "dow confirmation",
    },
    "mym_v2b": {
        "name": "MYM prior-opposed v2b resting-limit (hour-complete)",
        "bucket": "medium",
        "status": "micro Dow",
    },
    "mnq_hourly": {
        "name": "MNQ hourly ST+PMC sl25_tp75_3r",
        "bucket": "medium",
        "status": "fast feedback",
    },
    "usdjpy_mon_or": {
        "name": "USDJPY Monday OR M2_S3_R1",
        "bucket": "core_fx",
        "status": "Phase 2 primary",
    },
    "audjpy_mon_or": {
        "name": "AUDJPY Monday OR M1_S2_R2",
        "bucket": "mild",
        "status": "satellite",
    },
    "eurusd_fbo": {
        "name": "EURUSD Monthly ORB FBO 1/1/3 atr80",
        "bucket": "mild",
        "status": "promoted monthly",
    },
    "usdjpy_fbo": {
        "name": "USDJPY Monthly ORB FBO 1/1/3 atr80",
        "bucket": "mild",
        "status": "cross-pair FBO",
    },
    "eurusd_stpmc": {
        "name": "EURUSD hourly ST+PMC 25/75 MA-bull prior",
        "bucket": "mild",
        "status": "FX intraday baseline",
    },
    "nq_yearly": {
        "name": "NQ Yearly ORB scaleout3",
        "bucket": "trend",
        "status": "long-horizon trend",
    },
    "audjpy_yearly": {
        "name": "AUDJPY Yearly ORB scaleout3",
        "bucket": "trend",
        "status": "FX yearly ORB",
    },
    "xau_yearly": {
        "name": "XAUUSD Yearly ORB scaleout3",
        "bucket": "trend",
        "status": "metals yearly ORB",
    },
}

LOCKABLE = {"nq_v2b", "mnq_v2b", "ym_v2b", "mym_v2b"}


@dataclass(frozen=True)
class TierSpec:
    tier_id: str
    label: str
    target_pct: float
    haircut: float  # design CAGR = haircut × normalized CAGR
    lock_scale: float  # residual risk after lock
    lock_threshold_mult: float  # planned contrib = weight × design_cagr × mult
    blurb: str
    weights: dict[str, float]


# Weights tuned so Σ(w × design_cagr) ≈ target (see main printout).
TIERS: list[TierSpec] = [
    TierSpec(
        tier_id="A_5pct",
        label="Tier A · 5% target (low risk)",
        target_pct=5.0,
        haircut=0.70,
        lock_scale=0.05,
        lock_threshold_mult=1.0,
        blurb="Trend/mild FX backbone; v2b ≤5% combined; tight profit-lock.",
        weights={
            "nq_v2b": 0.02,
            "mnq_v2b": 0.01,
            "ym_v2b": 0.01,
            "mym_v2b": 0.01,
            "mnq_hourly": 0.03,
            "usdjpy_mon_or": 0.10,
            "audjpy_mon_or": 0.08,
            "eurusd_fbo": 0.14,
            "usdjpy_fbo": 0.12,
            "eurusd_stpmc": 0.10,
            "nq_yearly": 0.14,
            "audjpy_yearly": 0.12,
            "xau_yearly": 0.12,
        },
    ),
    TierSpec(
        tier_id="B_10pct",
        label="Tier B · 10% target (baseline)",
        target_pct=10.0,
        haircut=0.70,
        lock_scale=0.10,
        lock_threshold_mult=1.0,
        blurb="Current product mix; medium risk; design contrib ≈11.7%.",
        weights={
            "nq_v2b": 0.15,
            "mnq_v2b": 0.05,
            "ym_v2b": 0.05,
            "mym_v2b": 0.04,
            "mnq_hourly": 0.04,
            "usdjpy_mon_or": 0.22,
            "audjpy_mon_or": 0.06,
            "eurusd_fbo": 0.08,
            "usdjpy_fbo": 0.06,
            "eurusd_stpmc": 0.05,
            "nq_yearly": 0.08,
            "audjpy_yearly": 0.06,
            "xau_yearly": 0.06,
        },
    ),
    TierSpec(
        tier_id="C_15pct",
        label="Tier C · 15% target (medium-high)",
        target_pct=15.0,
        haircut=0.70,
        lock_scale=0.15,
        lock_threshold_mult=1.25,
        blurb="More v2b + USDJPY Monday OR; lock thresholds raised ~25%.",
        weights={
            "nq_v2b": 0.22,
            "mnq_v2b": 0.07,
            "ym_v2b": 0.06,
            "mym_v2b": 0.04,
            "mnq_hourly": 0.05,
            "usdjpy_mon_or": 0.28,
            "audjpy_mon_or": 0.03,
            "eurusd_fbo": 0.04,
            "usdjpy_fbo": 0.03,
            "eurusd_stpmc": 0.02,
            "nq_yearly": 0.06,
            "audjpy_yearly": 0.05,
            "xau_yearly": 0.05,
        },
    ),
    TierSpec(
        tier_id="D_20pct",
        label="Tier D · 20% target (high risk)",
        target_pct=20.0,
        haircut=1.00,  # plan on full normalized CAGRs
        lock_scale=0.25,
        lock_threshold_mult=1.50,
        blurb="Highest intraday weight; no design haircut; looser lock (more upside).",
        weights={
            "nq_v2b": 0.20,
            "mnq_v2b": 0.08,
            "ym_v2b": 0.07,
            "mym_v2b": 0.05,
            "mnq_hourly": 0.06,
            "usdjpy_mon_or": 0.26,
            "audjpy_mon_or": 0.03,
            "eurusd_fbo": 0.03,
            "usdjpy_fbo": 0.03,
            "eurusd_stpmc": 0.02,
            "nq_yearly": 0.07,
            "audjpy_yearly": 0.05,
            "xau_yearly": 0.05,
        },
    ),
]


def _load_equity_usd(path: Path, instrument: str) -> pd.Series:
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    if ts.isna().all():
        ts = pd.to_datetime(df["ts"], errors="coerce")
    df = df.loc[ts.notna()].copy()
    ts = ts.loc[ts.notna()]
    inst = instrument.upper()
    if "close_equity_usd" in df:
        equity = pd.to_numeric(df["close_equity_usd"], errors="coerce")
    elif "close_equity_points" in df:
        equity = pd.to_numeric(df["close_equity_points"], errors="coerce") * POINT_VALUE[inst]
        if inst in JPY_INSTRUMENTS:
            equity = equity / JPY_USD
    else:
        raise ValueError(f"No equity column in {path}")
    daily = pd.DataFrame({"date": ts.dt.tz_localize(None).dt.normalize(), "equity": equity}).dropna()
    return daily.groupby("date")["equity"].last().sort_index()


def _f0(val: object) -> float:
    try:
        x = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return x if np.isfinite(x) else 0.0


def build_budget(metrics: pd.DataFrame, tier: TierSpec) -> pd.DataFrame:
    wsum = sum(tier.weights.values())
    if abs(wsum - 1.0) > 1e-9:
        raise SystemExit(f"{tier.tier_id} weights sum to {wsum}, not 1")
    rows = []
    for sid, w in tier.weights.items():
        meta = SLEEVE_META[sid]
        m = metrics.loc[metrics["name"] == meta["name"]]
        if m.empty:
            raise SystemExit(f"Missing metrics for {meta['name']}")
        m = m.iloc[0]
        cagr = float(m["cagr_pct"]) / 100.0
        design = cagr * tier.haircut
        planned = w * design * tier.lock_threshold_mult
        capital = w * PORTFOLIO_CAPITAL
        rows.append(
            {
                "tier_id": tier.tier_id,
                "sleeve_id": sid,
                "name": meta["name"],
                "bucket": meta["bucket"],
                "status": meta["status"],
                "weight": w,
                "capital_usd": capital,
                "norm_cagr_pct": cagr * 100.0,
                "design_cagr_pct": design * 100.0,
                "haircut": tier.haircut,
                "implied_contrib_full_pct": w * cagr * 100.0,
                "implied_contrib_design_pct": w * design * 100.0,
                "planned_contrib_pct": planned * 100.0,
                "profit_lock": sid in LOCKABLE,
                "lock_scale": tier.lock_scale,
                "lock_threshold_mult": tier.lock_threshold_mult,
                "ref_cap_3x_stress": float(m["reference_capital_3x_stress"]),
                "scale_vs_full_book": capital / float(m["reference_capital_3x_stress"]),
                "sharpe": float(m["sharpe_daily"]),
                "calmar": float(m["calmar_mar"]),
                "qqq_corr": float(m["qqq_daily_corr"]),
                "start": m["start"],
                "end": m["end"],
                "equity_path": m["equity_path"],
                "instrument": m["instrument"],
            }
        )
    return pd.DataFrame(rows)


def sleeve_daily_returns(budget: pd.DataFrame) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for _, row in budget.iterrows():
        path = REPO / str(row["equity_path"])
        eq = _load_equity_usd(path, str(row["instrument"]))
        ref = float(row["ref_cap_3x_stress"])
        pnl = eq.diff().fillna(0.0)
        out[str(row["sleeve_id"])] = (pnl / ref).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out


def combine_static(
    returns: dict[str, pd.Series],
    budget: pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
    reweight_available: bool = True,
) -> pd.DataFrame:
    frame = pd.DataFrame(returns).sort_index().fillna(0.0)
    if start:
        frame = frame.loc[pd.Timestamp(start) :]
    if end:
        frame = frame.loc[: pd.Timestamp(end)]
    weights = {str(r.sleeve_id): float(r.weight) for r in budget.itertuples()}
    first = {k: returns[k].index.min() for k in returns}
    rows = []
    cum = 0.0
    for dt, row in frame.iterrows():
        live = [sid for sid in weights if first[sid] <= dt]
        if not live:
            port_ret = 0.0
        elif reweight_available:
            wsum = sum(weights[s] for s in live)
            port_ret = sum(_f0(row[s]) * (weights[s] / wsum) for s in live) if wsum else 0.0
        else:
            port_ret = sum(_f0(row.get(s, 0.0)) * weights[s] for s in weights if first[s] <= dt)
        cum += port_ret * PORTFOLIO_CAPITAL
        rows.append({"date": dt, "port_ret": port_ret, "equity_pnl": cum})
    return pd.DataFrame(rows).set_index("date")


def combine_profit_lock(
    returns: dict[str, pd.Series],
    budget: pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
    lock_scale: float = 0.10,
) -> pd.DataFrame:
    frame = pd.DataFrame(returns).sort_index().fillna(0.0)
    if start:
        frame = frame.loc[pd.Timestamp(start) :]
    if end:
        frame = frame.loc[: pd.Timestamp(end)]
    meta = budget.set_index("sleeve_id")
    first = {k: returns[k].index.min() for k in returns}
    planned = {sid: float(meta.loc[sid, "planned_contrib_pct"]) / 100.0 for sid in meta.index}
    can_lock = {sid: bool(meta.loc[sid, "profit_lock"]) for sid in meta.index}
    base_w = {sid: float(meta.loc[sid, "weight"]) for sid in meta.index}
    soft_buckets = {"mild", "trend", "core_fx", "medium"}

    rows = []
    cum = 0.0
    ytd = {sid: 0.0 for sid in base_w}
    locked = {sid: False for sid in base_w}
    cur_year = None
    for dt, row in frame.iterrows():
        if cur_year != dt.year:
            cur_year = dt.year
            ytd = {sid: 0.0 for sid in base_w}
            locked = {sid: False for sid in base_w}

        live = [sid for sid in base_w if first[sid] <= dt]
        eff = {sid: base_w[sid] * (lock_scale if locked[sid] else 1.0) for sid in live}
        freed = sum(base_w[s] * (1.0 - lock_scale) for s in live if locked[s])
        receivers = [
            s for s in live if (not locked[s]) and str(meta.loc[s, "bucket"]) in soft_buckets
        ]
        if freed > 0 and receivers:
            add = freed / len(receivers)
            for s in receivers:
                eff[s] += add

        wsum = sum(eff.values())
        port_ret = 0.0
        if wsum > 0:
            for sid, w in eff.items():
                r = _f0(row.get(sid, 0.0))
                port_ret += r * (w / wsum)
            for sid in live:
                r = _f0(row.get(sid, 0.0))
                ytd[sid] += r * base_w[sid]
                if can_lock[sid] and (not locked[sid]) and ytd[sid] >= planned[sid]:
                    locked[sid] = True

        cum += port_ret * PORTFOLIO_CAPITAL
        rows.append(
            {
                "date": dt,
                "port_ret": port_ret,
                "equity_pnl": cum,
                "n_locked": int(sum(1 for v in locked.values() if v)),
            }
        )
    return pd.DataFrame(rows).set_index("date")


def summarize(path_df: pd.DataFrame, label: str, tier_id: str) -> dict:
    if path_df.empty:
        return {"tier_id": tier_id, "label": label, "cagr_pct": math.nan}
    years = max((path_df.index.max() - path_df.index.min()).days / 365.25, 1e-9)
    wealth = PORTFOLIO_CAPITAL * (1.0 + path_df["port_ret"].fillna(0.0)).cumprod()
    total_ret = float(wealth.iloc[-1] / PORTFOLIO_CAPITAL - 1.0)
    cagr = (1.0 + total_ret) ** (1.0 / years) - 1.0 if total_ret > -1 else math.nan
    peak = wealth.cummax()
    dd = float(((wealth - peak) / peak).min())
    yr = path_df["port_ret"].groupby(path_df.index.year).apply(lambda s: float((1 + s).prod() - 1))
    return {
        "tier_id": tier_id,
        "label": label,
        "start": path_df.index.min().date().isoformat(),
        "end": path_df.index.max().date().isoformat(),
        "years": years,
        "ending_pnl": float(wealth.iloc[-1] - PORTFOLIO_CAPITAL),
        "ending_equity": float(wealth.iloc[-1]),
        "total_return_pct": total_ret * 100.0,
        "cagr_pct": cagr * 100.0,
        "max_dd_pct": dd * 100.0,
        "positive_years": int((yr > 0).sum()),
        "total_years": int(len(yr)),
        "worst_year_pct": float(yr.min() * 100.0) if len(yr) else math.nan,
        "best_year_pct": float(yr.max() * 100.0) if len(yr) else math.nan,
        "median_year_pct": float(yr.median() * 100.0) if len(yr) else math.nan,
        "years_ge_target": int((yr >= 0.0).sum()),  # filled below per tier
        "years_ge_8pct": int((yr >= 0.08).sum()),
        "years_ge_10pct": int((yr >= 0.10).sum()),
    }


def yearly_table(path_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, grp in path_df.groupby(path_df.index.year):
        r = float((1 + grp["port_ret"]).prod() - 1)
        rows.append(
            {
                "year": int(year),
                "return_pct": r * 100.0,
                "pnl_usd": float(grp["port_ret"].sum() * PORTFOLIO_CAPITAL),
            }
        )
    return pd.DataFrame(rows)


def run_tier(
    tier: TierSpec,
    metrics: pd.DataFrame,
    returns_cache: Optional[Dict[str, pd.Series]] = None,
) -> Tuple[pd.DataFrame, List[dict], Dict[str, pd.DataFrame], Dict[str, pd.Series]]:
    budget = build_budget(metrics, tier)
    if returns_cache is None:
        returns_cache = {}
    missing = [sid for sid in budget["sleeve_id"] if sid not in returns_cache]
    if missing:
        returns_cache.update(sleeve_daily_returns(budget[budget["sleeve_id"].isin(missing)]))
    returns = {sid: returns_cache[sid] for sid in budget["sleeve_id"]}

    tier_dir = OUT / tier.tier_id
    tier_dir.mkdir(parents=True, exist_ok=True)
    budget.to_csv(tier_dir / "risk_budget.csv", index=False)

    static_2010 = combine_static(returns, budget, start="2010-06-06", end="2026-03-31", reweight_available=True)
    static_2021 = combine_static(returns, budget, start="2021-03-04", end="2026-03-31", reweight_available=True)
    static_pre = combine_static(returns, budget, start="2010-06-06", end="2020-12-31", reweight_available=True)
    lock_2010 = combine_profit_lock(
        returns, budget, start="2010-06-06", end="2026-03-31", lock_scale=tier.lock_scale
    )
    lock_2021 = combine_profit_lock(
        returns, budget, start="2021-03-04", end="2026-03-31", lock_scale=tier.lock_scale
    )

    summaries = [
        summarize(static_pre, f"{tier.tier_id} · static 2010–2020", tier.tier_id),
        summarize(static_2010, f"{tier.tier_id} · static 2010–2026", tier.tier_id),
        summarize(lock_2010, f"{tier.tier_id} · profit-lock 2010–2026", tier.tier_id),
        summarize(static_2021, f"{tier.tier_id} · static 2021–2026", tier.tier_id),
        summarize(lock_2021, f"{tier.tier_id} · profit-lock 2021–2026", tier.tier_id),
    ]
    target = tier.target_pct / 100.0
    for s in summaries:
        # recompute years ≥ target from yearly later; placeholder
        s["target_pct"] = tier.target_pct

    yearly = {
        "static_2010": yearly_table(static_2010),
        "lock_2010": yearly_table(lock_2010),
        "static_2021": yearly_table(static_2021),
        "lock_2021": yearly_table(lock_2021),
    }
    for key, df in yearly.items():
        df.to_csv(tier_dir / f"yearly_{key}.csv", index=False)
        if key == "lock_2010":
            for s in summaries:
                if "profit-lock 2010" in s["label"]:
                    s["years_ge_target"] = int((df["return_pct"] >= tier.target_pct).sum())

    static_2010.to_csv(tier_dir / "equity_static_2010.csv")
    lock_2010.to_csv(tier_dir / "equity_lock_2010.csv")
    static_2021.to_csv(tier_dir / "equity_static_2021.csv")
    lock_2021.to_csv(tier_dir / "equity_lock_2021.csv")
    pd.DataFrame(summaries).to_csv(tier_dir / "summaries.csv", index=False)

    # Per-tier mini summary
    design_sum = float(budget["implied_contrib_design_pct"].sum())
    full_sum = float(budget["implied_contrib_full_pct"].sum())
    lines = [
        f"# {tier.label}",
        "",
        tier.blurb,
        "",
        f"- Advertised target: **{tier.target_pct:.0f}%**",
        f"- Design haircut: **{tier.haircut*100:.0f}%** of normalized CAGR",
        f"- Profit-lock residual scale: **{tier.lock_scale*100:.0f}%**; threshold mult: **{tier.lock_threshold_mult:.2f}×**",
        f"- Σ design contribution: **{design_sum:.2f}%** (full-CAGR Σ: {full_sum:.2f}%)",
        f"- Example NAV: ${PORTFOLIO_CAPITAL:,.0f}",
        "",
        "## Risk budget",
        "",
        "| Sleeve | Bucket | Weight | Design CAGR | Design contrib | Planned lock | Lock? |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for _, r in budget.iterrows():
        lines.append(
            f"| {r.sleeve_id} | {r.bucket} | {r.weight*100:.0f}% | {r.design_cagr_pct:.1f}% | {r.implied_contrib_design_pct:.2f}% | {r.planned_contrib_pct:.2f}% | {'yes' if r.profit_lock else 'no'} |"
        )
    lines += [
        "",
        "## Backtest (compounded)",
        "",
        "| Variant | CAGR | Max DD | +Years | Median year | Worst | Years ≥ target |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        ydf = yearly["lock_2010"] if "profit-lock 2010" in s["label"] else (
            yearly["static_2010"] if "static 2010–2026" in s["label"] else (
                yearly["static_2021"] if "static 2021" in s["label"] else (
                    yearly["lock_2021"] if "profit-lock 2021" in s["label"] else yearly["static_2010"]
                )
            )
        )
        if "2010–2020" in s["label"]:
            ge = "—"
        else:
            ge = str(int((ydf["return_pct"] >= tier.target_pct).sum()))
        lines.append(
            f"| {s['label']} | **{s['cagr_pct']:.1f}%** | {s['max_dd_pct']:.1f}% | {s['positive_years']}/{s['total_years']} | {s['median_year_pct']:.1f}% | {s['worst_year_pct']:.1f}% | {ge} |"
        )
    lines += [
        "",
        "## Yearly returns (profit-lock)",
        "",
        "| Year | Return |",
        "|---:|---:|",
    ]
    for _, r in yearly["lock_2010"].iterrows():
        lines.append(f"| {int(r.year)} | {r.return_pct:.1f}% |")
    (tier_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return budget, summaries, yearly, returns


def write_hub(all_budgets: pd.DataFrame, all_summaries: pd.DataFrame) -> None:
    # Wide weight table
    pivot = all_budgets.pivot_table(index="sleeve_id", columns="tier_id", values="weight", aggfunc="first")
    # stable column order
    cols = [t.tier_id for t in TIERS]
    pivot = pivot.reindex(columns=cols)
    pivot["bucket"] = all_budgets.drop_duplicates("sleeve_id").set_index("sleeve_id")["bucket"]
    pivot = pivot[["bucket"] + cols]
    pivot.to_csv(OUT / "weights_by_tier.csv")

    design = all_budgets.groupby("tier_id").agg(
        design_contrib_pct=("implied_contrib_design_pct", "sum"),
        full_contrib_pct=("implied_contrib_full_pct", "sum"),
        haircut=("haircut", "first"),
        lock_scale=("lock_scale", "first"),
        lock_threshold_mult=("lock_threshold_mult", "first"),
    )
    design.to_csv(OUT / "tier_design_targets.csv")

    # Preferred product path rows
    pref = all_summaries[all_summaries["label"].str.contains("profit-lock 2010–2026")].copy()
    static = all_summaries[all_summaries["label"].str.contains("static 2010–2026")].copy()

    lines = [
        "# Portfolio product tiers (5% / 10% / 15% / 20%)",
        "",
        "Hypothetical/backtested multi-product suite sharing one sleeve universe. "
        "Weights and profit-lock thresholds differ by tier. Not audited live performance.",
        "",
        "## Context",
        "",
        "- Inputs: [`../institutional_strategy_metrics/`](../institutional_strategy_metrics/SUMMARY.md)",
        "- Prior single-product path: [`../target_10pct_portfolio/`](../target_10pct_portfolio/SUMMARY.md) (= Tier B)",
        "- Precursors: [`orb-portfolio/`](../../../orb-portfolio/README.md), MNQ+MYM yearly blend",
        "",
        "## Tier map",
        "",
        "| Tier | Target | Haircut | Lock residual | Lock threshold | Design Σ | Full Σ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for t in TIERS:
        row = design.loc[t.tier_id]
        lines.append(
            f"| **{t.label}** | {t.target_pct:.0f}% | {t.haircut*100:.0f}% | {t.lock_scale*100:.0f}% | {t.lock_threshold_mult:.2f}× | {row.design_contrib_pct:.1f}% | {row.full_contrib_pct:.1f}% |"
        )
    lines += [
        "",
        "### Blurbs",
        "",
    ]
    for t in TIERS:
        lines.append(f"- **{t.tier_id}:** {t.blurb}")

    lines += [
        "",
        "## Weights by tier",
        "",
        "| Sleeve | Bucket | A 5% | B 10% | C 15% | D 20% |",
        "|---|---|---:|---:|---:|---:|",
    ]
    order = list(SLEEVE_META.keys())
    for sid in order:
        b = SLEEVE_META[sid]["bucket"]
        ws = [f"{float(pivot.loc[sid, c])*100:.0f}%" for c in cols]
        lines.append(f"| {sid} | {b} | " + " | ".join(ws) + " |")

    lines += [
        "",
        "## Realized backtest (compounded wealth, $300k)",
        "",
        "### Preferred path — profit-lock 2010–2026",
        "",
        "| Tier | CAGR | Max DD | +Years | Median year | Worst year | Best year |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for t in TIERS:
        s = pref[pref["tier_id"] == t.tier_id].iloc[0]
        lines.append(
            f"| {t.tier_id} | **{s.cagr_pct:.1f}%** | {s.max_dd_pct:.1f}% | {s.positive_years}/{s.total_years} | {s.median_year_pct:.1f}% | {s.worst_year_pct:.1f}% | {s.best_year_pct:.1f}% |"
        )
    lines += [
        "",
        "### Uncapped static 2010–2026 (shows why locks matter)",
        "",
        "| Tier | CAGR | Max DD | Median year | Best year |",
        "|---|---:|---:|---:|---:|",
    ]
    for t in TIERS:
        s = static[static["tier_id"] == t.tier_id].iloc[0]
        lines.append(
            f"| {t.tier_id} | {s.cagr_pct:.1f}% | {s.max_dd_pct:.1f}% | {s.median_year_pct:.1f}% | {s.best_year_pct:.1f}% |"
        )

    lines += [
        "",
        "## How to read this for allocators",
        "",
        "- **Advertised target** is the design risk budget (weight × haircuted CAGR), not a guarantee.",
        "- **Profit-lock** path is the product operating rule; static uncapped is diagnostic only.",
        "- Tier A is the consistency engine; Tier D is high-octane managed futures with larger residual lock scale.",
        "- Same sleeves and ops stack; only risk budgeting and lock thresholds change.",
        "",
        f"Generator: [`../../../scripts/portfolio_product_tiers.py`](../../../scripts/portfolio_product_tiers.py).",
        "",
        "Per-tier folders: [`A_5pct/`](A_5pct/SUMMARY.md), [`B_10pct/`](B_10pct/SUMMARY.md), [`C_15pct/`](C_15pct/SUMMARY.md), [`D_20pct/`](D_20pct/SUMMARY.md).",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    all_budgets.to_csv(OUT / "risk_budget_all_tiers.csv", index=False)
    all_summaries.to_csv(OUT / "summaries_all_tiers.csv", index=False)


def sync_legacy_tier_b(tier_dir: Path) -> None:
    """Keep target_10pct_portfolio/ as a pointer + copy of Tier B for old links."""
    LEGACY_OUT.mkdir(parents=True, exist_ok=True)
    note = (
        "# Moved: multi-tier products\n\n"
        "This folder remains for backward links. **Tier B (10%)** and the full 5/10/15/20 suite live at "
        "[`../portfolio_product_tiers/`](../portfolio_product_tiers/SUMMARY.md).\n\n"
        "Regenerate with: `python3 scripts/portfolio_product_tiers.py`\n"
    )
    (LEGACY_OUT / "README.md").write_text(note, encoding="utf-8")
    # Refresh core Tier B artifacts into legacy path
    for name in (
        "risk_budget.csv",
        "summaries.csv",
        "equity_static_2010.csv",
        "equity_lock_2010.csv",
        "yearly_static_2010.csv",
        "yearly_lock_2010.csv",
        "SUMMARY.md",
    ):
        src = tier_dir / name
        if src.exists():
            (LEGACY_OUT / name).write_bytes(src.read_bytes())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(METRICS)
    returns_cache: dict[str, pd.Series] = {}
    all_budget_rows = []
    all_summary_rows = []

    for tier in TIERS:
        print(f"\n=== {tier.label} ===")
        budget, summaries, _yearly, returns_cache = run_tier(tier, metrics, returns_cache)
        design_sum = float(budget["implied_contrib_design_pct"].sum())
        print(f"weights={budget['weight'].sum():.4f}  design_Σ={design_sum:.2f}%  (target {tier.target_pct:.0f}%)")
        for s in summaries:
            if "profit-lock 2010" in s["label"] or "static 2010–2026" in s["label"]:
                print(
                    f"  {s['label']}: CAGR={s['cagr_pct']:.2f}%  DD={s['max_dd_pct']:.1f}%  "
                    f"med={s['median_year_pct']:.1f}%  +yrs={s['positive_years']}/{s['total_years']}"
                )
        all_budget_rows.append(budget)
        all_summary_rows.extend(summaries)
        if tier.tier_id == "B_10pct":
            sync_legacy_tier_b(OUT / tier.tier_id)

    all_budgets = pd.concat(all_budget_rows, ignore_index=True)
    all_summaries = pd.DataFrame(all_summary_rows)
    write_hub(all_budgets, all_summaries)
    print(f"\nWrote hub {OUT / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
