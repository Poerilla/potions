"""Broker-like filter / size-up overlay on intraday condition-profile hits.

Replays annotated campaign tapes from ``live/state/intraday_condition_profile``
under three policies vs baseline:

- **filter**: take only high-probability (HP) campaigns
- **size_1.25**: 1.25× size when HP, else 1.0×
- **size_1.5**: 1.5× size when HP, else 1.0×

Single-book candidates = strong dual-lift notables. Cross-book candidates =
condition/bucket clearing the profile heuristic on ≥``--min-cross-books`` books.

Features are entry-asof (pre-fill). ATR quartile in the profile hub is a
within-book static cut — live would need a causal rolling percentile.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.intraday_condition_overlay --email
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email

PROFILE_HUB = REPO / "live" / "state" / "intraday_condition_profile"
HUB = REPO / "live" / "state" / "intraday_condition_overlay"

# Profile condition title → campaign column
COND_COL = {
    "Day of week": "dow",
    "Week of month": "week_of_month",
    "Entry hour (NY)": "hour_ny",
    "5m MA vs trade": "ma5_align",
    "5m MA cross vs trade": "ma5_cross_align",
    "Hourly RSI bucket": "rsi_bucket",
    "Hourly RSI vs trade": "rsi_align",
    "Hourly OBV vs trade": "obv_align",
    "ATR14 quartile": "atr_q",
    "Prior-day range half": "day_half_align",
    "Prior-week range half": "week_half_align",
    "Prior-month range half": "month_half_align",
}

# Conditions that are knowable strictly before fill with no static-book look-ahead.
CAUSAL_LIVE_READY = {
    "Day of week",
    "Week of month",
    "Entry hour (NY)",
    "5m MA vs trade",
    "5m MA cross vs trade",
    "Hourly RSI bucket",
    "Hourly RSI vs trade",
    "Hourly OBV vs trade",
    "Prior-day range half",
    "Prior-week range half",
    "Prior-month range half",
}
# ATR q needs rolling causal percentile for live; still scored here as research proxy.
NEEDS_LIVE_PROXY = {"ATR14 quartile"}


def _max_dd(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _pf(pnl: np.ndarray) -> float:
    if pnl.size == 0:
        return 0.0
    gains = float(pnl[pnl > 0].sum())
    losses = float((-pnl[pnl < 0]).sum())
    if losses <= 0:
        return 99.0 if gains > 0 else 0.0
    return gains / losses


def score_nets(nets: np.ndarray, *, label: str = "") -> Dict[str, float]:
    nets = np.asarray(nets, dtype=float)
    n = int(nets.size)
    if n == 0:
        return {
            "label": label,
            "n": 0,
            "wins": 0,
            "wr": 0.0,
            "net": 0.0,
            "avg": 0.0,
            "pf": 0.0,
            "max_dd": 0.0,
            "stress": 0.0,
            "ns": 0.0,
        }
    eq = np.cumsum(nets)
    dd = _max_dd(eq)
    stress = abs(dd)
    net = float(nets.sum())
    wins = int((nets > 0).sum())
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "wr": wins / n,
        "net": net,
        "avg": float(nets.mean()),
        "pf": _pf(nets),
        "max_dd": dd,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
    }


def apply_policy(df: pd.DataFrame, mask: np.ndarray, policy: str, size_mult: float = 1.0) -> np.ndarray:
    """Return chronologically ordered sized nets under policy."""
    base = df["net_usd"].to_numpy(dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if policy == "baseline":
        return base.copy()
    if policy == "filter":
        return base[mask]
    if policy.startswith("size_"):
        out = base.copy()
        out[mask] = out[mask] * float(size_mult)
        return out
    raise ValueError("unknown policy %s" % policy)


def hp_mask(df: pd.DataFrame, condition: str, bucket: str) -> np.ndarray:
    col = COND_COL.get(condition)
    if col is None or col not in df.columns:
        return np.zeros(len(df), dtype=bool)
    # hour / week_of_month may be int in campaigns and str in notables
    series = df[col]
    if col in ("hour_ny", "week_of_month"):
        try:
            want = type(series.dropna().iloc[0])(bucket) if series.notna().any() else bucket
        except (ValueError, TypeError, IndexError):
            want = bucket
        return (series.astype(str) == str(want)) | (series == want)
    return series.astype(str) == str(bucket)


def select_single_book_hits(
    notables: pd.DataFrame,
    *,
    min_z: float = 1.64,
    min_n: int = 60,
    top_per_book: int = 4,
) -> pd.DataFrame:
    """Strong per-book dual-lift rows."""
    n = notables.copy()
    n["score"] = n["avg_lift"] * np.sqrt(n["n"].clip(lower=1) / 100.0) + 40.0 * n["z_wr"].clip(lower=0)
    strong = n[(n["n"] >= min_n) & (n["wr_lift_pp"] > 0) & (n["avg_lift"] > 0)]
    strong = strong[(strong["z_wr"] >= min_z) | (strong["avg_lift"] >= strong.groupby("book")["avg_lift"].transform("median"))]
    # Prefer z≥min_z; fill with top avg_lift if book has few z-hits
    rows = []
    for book, g in strong.groupby("book"):
        zhit = g[g["z_wr"] >= min_z].sort_values("score", ascending=False)
        rest = g[g["z_wr"] < min_z].sort_values("score", ascending=False)
        pick = pd.concat([zhit, rest], ignore_index=True).drop_duplicates(
            subset=["condition", "bucket"]
        ).head(top_per_book)
        rows.append(pick)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["scope"] = "single_book"
    return out


def select_cross_book_hits(
    notables: pd.DataFrame,
    *,
    min_books: int = 3,
) -> pd.DataFrame:
    rows = []
    for (cond, bucket), g in notables.groupby(["condition", "bucket"]):
        books = sorted(g["book"].unique())
        if len(books) < min_books:
            continue
        rows.append(
            {
                "scope": "cross_book",
                "condition": cond,
                "bucket": bucket,
                "books": ",".join(books),
                "n_books": len(books),
                "median_wr_lift_pp": float(g["wr_lift_pp"].median()),
                "median_avg_lift": float(g["avg_lift"].median()),
                "median_z_wr": float(g["z_wr"].median()),
                "total_n": int(g["n"].sum()),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["n_books", "median_avg_lift"], ascending=False
    ).reset_index(drop=True)


def evaluate_candidate(
    campaigns: pd.DataFrame,
    *,
    book: str,
    condition: str,
    bucket: str,
    scope: str,
    policies: Sequence[Tuple[str, float]],
    is_frac: float = 0.60,
) -> List[dict]:
    df = campaigns[campaigns["book"] == book].sort_values("entry_ts").reset_index(drop=True)
    if df.empty:
        return []
    mask = hp_mask(df, condition, bucket)
    hp_n = int(mask.sum())
    if hp_n < 10:
        return []

    cut = max(int(len(df) * is_frac), 1)
    is_df, oos_df = df.iloc[:cut], df.iloc[cut:]
    is_mask, oos_mask = mask[:cut], mask[cut:]

    causal = "live_ready" if condition in CAUSAL_LIVE_READY else (
        "needs_rolling_proxy" if condition in NEEDS_LIVE_PROXY else "review"
    )
    out = []
    for split_name, split_df, split_mask in (
        ("full", df, mask),
        ("is", is_df, is_mask),
        ("oos", oos_df, oos_mask),
    ):
        base = score_nets(split_df["net_usd"].to_numpy(dtype=float), label="baseline")
        for policy, mult in policies:
            nets = apply_policy(split_df, split_mask, policy, size_mult=mult)
            sc = score_nets(nets, label=policy)
            out.append(
                {
                    "scope": scope,
                    "book": book,
                    "condition": condition,
                    "bucket": str(bucket),
                    "causal": causal,
                    "split": split_name,
                    "policy": policy,
                    "size_mult": float(mult) if policy.startswith("size_") else (0.0 if policy == "filter" else 1.0),
                    "hp_n": int(split_mask.sum()),
                    "hp_frac": float(split_mask.mean()) if len(split_mask) else 0.0,
                    "base_n": base["n"],
                    "base_net": base["net"],
                    "base_avg": base["avg"],
                    "base_wr": base["wr"],
                    "base_pf": base["pf"],
                    "base_stress": base["stress"],
                    "base_ns": base["ns"],
                    "n": sc["n"],
                    "net": sc["net"],
                    "avg": sc["avg"],
                    "wr": sc["wr"],
                    "pf": sc["pf"],
                    "stress": sc["stress"],
                    "ns": sc["ns"],
                    "delta_net": sc["net"] - base["net"],
                    "delta_ns": sc["ns"] - base["ns"],
                    "delta_stress": sc["stress"] - base["stress"],
                    "net_lift_pct": (sc["net"] / base["net"] - 1.0) if abs(base["net"]) > 1 else math.nan,
                }
            )
    return out


def stance_row(r: dict) -> str:
    """Promote / retain / reject heuristic for phone + plan."""
    if r["split"] != "oos" or r["policy"] == "baseline":
        return ""
    # Need OOS net lift and N/S not worse by much; filter must keep enough trades
    if r["policy"] == "filter":
        if r["n"] < 25:
            return "thin"
        if r["delta_net"] > 0 and r["ns"] >= 0.9 * r["base_ns"] and r["avg"] > r["base_avg"]:
            return "worth_filter"
        if r["delta_net"] > 0 and r["ns"] >= r["base_ns"]:
            return "retain_filter"
        return "reject_filter"
    # size-up: want net up, stress not exploding, N/S not collapsing
    if r["delta_net"] <= 0:
        return "reject_size"
    stress_ok = r["stress"] <= 1.35 * r["base_stress"] + 1.0
    ns_ok = r["ns"] >= 0.85 * r["base_ns"]
    if stress_ok and ns_ok and r["delta_net"] >= 0.05 * abs(r["base_net"]):
        return "worth_size"
    if stress_ok and r["delta_net"] > 0:
        return "retain_size"
    return "reject_size"


def render_summary(
    results: pd.DataFrame,
    singles: pd.DataFrame,
    crosses: pd.DataFrame,
) -> str:
    lines = [
        "# Intraday condition overlay (filter vs size-up)",
        "",
        "Broker-like campaign replay of condition-profile hits under **filter**,",
        "**1.25× size-up**, and **1.5× size-up** vs each book's baseline tape.",
        "Source: `live/state/intraday_condition_profile/all_campaigns.csv` (entry-asof features).",
        "",
        "Splits: **full** tape, chronological **IS** (first 60%), **OOS** (last 40%).",
        "Size-up scales campaign `net_usd` on HP rows only (PnL+fees linear in size).",
        "",
        "## Causality",
        "",
        "- Calendar / hour / MA / RSI / OBV / prior range-half: **pre-fill** (live-ready).",
        "- ATR quartile here is a **static within-book** cut — live needs causal rolling percentile.",
        "- No post-fill add-on size studied; all HP flags are knowable at entry.",
        "",
    ]

    oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")].copy()
    oos["stance"] = oos.apply(lambda r: stance_row(r.to_dict()), axis=1)

    worth = oos[oos["stance"].isin(["worth_filter", "worth_size", "retain_filter", "retain_size"])]
    lines.append("## OOS keepers (heuristic)")
    lines.append("")
    if worth.empty:
        lines.append("_No OOS overlay cleared the keep heuristic._")
    else:
        lines.append("| scope | book | condition | bucket | policy | stance | hp% | Δnet | ΔN/S | OOS net | OOS N/S | causal |")
        lines.append("|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|")
        show = worth.sort_values(["stance", "delta_net"], ascending=[True, False])
        for _, r in show.iterrows():
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %.0f%% | %+.0f | %+.2f | %.0f | %.2f | %s |"
                % (
                    r["scope"],
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    r["policy"],
                    r["stance"],
                    100.0 * r["hp_frac"],
                    r["delta_net"],
                    r["delta_ns"],
                    r["net"],
                    r["ns"],
                    r["causal"],
                )
            )
    lines.append("")

    # Per-scope highlights on full tape for size 1.5 / filter
    lines.append("## Single-book candidates tested")
    lines.append("")
    if singles.empty:
        lines.append("_none_")
    else:
        for _, r in singles.iterrows():
            lines.append(
                "- `%s` · %s=%s · profile n=%d WR%+.1fpp avg$%+.0f z=%.2f"
                % (r["book"], r["condition"], r["bucket"], int(r["n"]), r["wr_lift_pp"], r["avg_lift"], r["z_wr"])
            )
    lines.append("")
    lines.append("## Cross-book candidates tested")
    lines.append("")
    if crosses.empty:
        lines.append("_none_")
    else:
        for _, r in crosses.iterrows():
            lines.append(
                "- **%s=%s** · %d books (%s) · med WR%+.1fpp med avg$%+.0f"
                % (
                    r["condition"],
                    r["bucket"],
                    int(r["n_books"]),
                    r["books"],
                    r["median_wr_lift_pp"],
                    r["median_avg_lift"],
                )
            )
    lines.append("")

    # Compact full-tape comparison for top size/filter deltas
    full = results[(results["split"] == "full") & (results["policy"] != "baseline")].copy()
    full = full.sort_values("delta_net", ascending=False)
    lines.append("## Full-tape top Δnet overlays")
    lines.append("")
    lines.append("| scope | book | condition=bucket | policy | hp% | base net | overlay net | Δnet | base N/S | N/S | stress× |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in full.head(25).iterrows():
        stress_x = (r["stress"] / r["base_stress"]) if r["base_stress"] > 1 else float("nan")
        lines.append(
            "| %s | %s | %s=%s | %s | %.0f%% | %.0f | %.0f | %+.0f | %.2f | %.2f | %.2f |"
            % (
                r["scope"],
                r["book"],
                r["condition"],
                r["bucket"],
                r["policy"],
                100.0 * r["hp_frac"],
                r["base_net"],
                r["net"],
                r["delta_net"],
                r["base_ns"],
                r["ns"],
                stress_x,
            )
        )
    lines.append("")
    lines.append("## Verdict draft")
    lines.append("")
    wf = worth[worth["stance"].isin(["worth_filter", "worth_size"])]
    if wf.empty:
        lines.append(
            "OOS evidence is weak for promoting HP filter/size overlays as alpha. "
            "Prefer calendar/hour/RSI-against that stay live-ready if any retain_* rows look robust; "
            "otherwise treat as research-only and do not change live sizing yet."
        )
    else:
        lines.append(
            "Several OOS overlays clear a soft keep bar — see keepers table and `LIVE_PLAN.md` "
            "for a staged live/demo sizing hook (causal flags only; ATR deferred)."
        )
    lines.append("")
    return "\n".join(lines)


def phone_email(summary_path: Path, results: pd.DataFrame) -> str:
    oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")].copy()
    oos["stance"] = oos.apply(lambda r: stance_row(r.to_dict()), axis=1)
    keep = oos[oos["stance"].isin(["worth_filter", "worth_size", "retain_filter", "retain_size"])]
    lines = [
        "potions: condition overlay (filter/size) complete",
        "hub: %s" % HUB,
        "",
    ]
    if keep.empty:
        lines.append("OOS: no clear keepers for filter or 1.25/1.5 size-up.")
        lines.append("Stance: research-only; do not change live sizing yet.")
    else:
        lines.append("OOS keepers: %d" % len(keep))
        top = keep.sort_values("delta_net", ascending=False).head(8)
        for _, r in top.iterrows():
            lines.append(
                "- %s %s %s=%s %s Δnet%+.0f N/S%.2f (%s)"
                % (
                    r["stance"],
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    r["policy"],
                    r["delta_net"],
                    r["ns"],
                    r["causal"],
                )
            )
    lines.append("")
    lines.append(str(summary_path))
    return "\n".join(lines)


def write_live_plan(results: pd.DataFrame, path: Path) -> None:
    oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")].copy()
    oos["stance"] = oos.apply(lambda r: stance_row(r.to_dict()), axis=1)
    keep = oos[oos["stance"].isin(["worth_filter", "worth_size", "retain_filter", "retain_size"])]
    live_ready = keep[keep["causal"] == "live_ready"]

    lines = [
        "# Plan: HP condition overlays on live/demo",
        "",
        "Diagnostic source: `intraday_condition_overlay` on broker-like campaign tapes.",
        "Do **not** promote until OOS keepers below are reviewed and ATR (if used) is causal.",
        "",
        "## What worked (OOS heuristic)",
        "",
    ]
    if live_ready.empty:
        lines.extend(
            [
                "_No live-ready OOS keepers._ Skip live wiring for now; keep profiling.",
                "",
                "## If revisiting later",
                "",
                "1. Re-run profile + overlay after more demo tape or frozen OOS years.",
                "2. Prefer **size-up** over hard filter (keeps N; less selection risk).",
                "3. Caps: single-book ≤1.5×, cross-book ≤1.25× until path stress audited.",
                "4. Only entry-asof flags; no mid-trade add unless multi-day and separately audited.",
                "",
            ]
        )
    else:
        lines.append("| book | condition | bucket | policy | stance | Δnet OOS |")
        lines.append("|---|---|---|---|---|---:|")
        for _, r in live_ready.sort_values("delta_net", ascending=False).iterrows():
            lines.append(
                "| %s | %s | %s | %s | %s | %+.0f |"
                % (r["book"], r["condition"], r["bucket"], r["policy"], r["stance"], r["delta_net"])
            )
        lines.extend(
            [
                "",
                "## Staged live/demo rollout",
                "",
                "1. **Shadow only** on one demo family (prefer Monday OR or ST+PMC): log HP flag +",
                "   would-be size mult beside each fill; no order-size change.",
                "2. **Paper size-up** (1.25× cross-book or single-book keepers) with hard cap on",
                "   concurrent HP risk (e.g. one HP boost at a time per account).",
                "3. Wire as plugin config: `hp_conditions: [{col, value, size_mult}]` evaluated in",
                "   `on_bar` / order intent **before** submit — same asof as research features.",
                "4. Skip ATR quartile until rolling causal percentile exists; skip post-fill add-on",
                "   for intraday books (Monday OR multi-day could later add size only after a",
                "   separate mid-trade study).",
                "5. Gate with existing month / shadow WR-PF filters — HP size is an overlay, not a replacement.",
                "6. After 50–100 live HP campaigns, re-score OOS-style and promote or kill.",
                "",
                "## Filter vs size",
                "",
                "- Prefer **size-up** when OOS Δnet > 0 and stress ≤ ~1.35× baseline.",
                "- Use **filter** only when sit-out improves N/S and leftover N stays healthy (≥25 OOS).",
                "- Cross-book: start at **1.25×**; reserve **1.5×** for single-book hits with strong OOS.",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def run(
    *,
    email: bool = False,
    min_cross_books: int = 3,
    min_z: float = 1.64,
    min_n: int = 60,
    top_per_book: int = 4,
) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    notables = pd.read_csv(PROFILE_HUB / "notables.csv")

    singles = select_single_book_hits(notables, min_z=min_z, min_n=min_n, top_per_book=top_per_book)
    crosses = select_cross_book_hits(notables, min_books=min_cross_books)

    policies: List[Tuple[str, float]] = [
        ("baseline", 1.0),
        ("filter", 0.0),
        ("size_1.25", 1.25),
        ("size_1.5", 1.5),
    ]

    rows: List[dict] = []
    # Single-book: evaluate on that book only
    for _, hit in singles.iterrows():
        rows.extend(
            evaluate_candidate(
                campaigns,
                book=str(hit["book"]),
                condition=str(hit["condition"]),
                bucket=str(hit["bucket"]),
                scope="single_book",
                policies=policies,
            )
        )

    # Cross-book: evaluate on each book that cleared the profile notable
    for _, hit in crosses.iterrows():
        for book in str(hit["books"]).split(","):
            rows.extend(
                evaluate_candidate(
                    campaigns,
                    book=book,
                    condition=str(hit["condition"]),
                    bucket=str(hit["bucket"]),
                    scope="cross_book",
                    policies=policies,
                )
            )

    results = pd.DataFrame(rows)
    if not results.empty:
        results["stance"] = results.apply(lambda r: stance_row(r.to_dict()), axis=1)
        results.to_csv(HUB / "overlay_results.csv", index=False)
    singles.to_csv(HUB / "single_book_candidates.csv", index=False)
    crosses.to_csv(HUB / "cross_book_candidates.csv", index=False)

    # Stance pivot for OOS
    oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")].copy()
    if not oos.empty:
        oos.to_csv(HUB / "oos_overlays.csv", index=False)

    summary = render_summary(results, singles, crosses)
    summary_path = HUB / "SUMMARY.md"
    summary_path.write_text(summary, encoding="utf-8")
    write_live_plan(results, HUB / "LIVE_PLAN.md")

    meta = {
        "n_single_candidates": int(len(singles)),
        "n_cross_candidates": int(len(crosses)),
        "n_result_rows": int(len(results)),
        "min_cross_books": min_cross_books,
        "min_z": min_z,
        "min_n": min_n,
    }
    (HUB / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    email_body = phone_email(summary_path, results)
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    if email:
        send_email(subject="potions: condition overlay (filter/size) complete", body=email_body)
        print("emailed completion summary", flush=True)
    print("wrote %s" % summary_path, flush=True)
    return summary_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--min-cross-books", type=int, default=3)
    p.add_argument("--min-z", type=float, default=1.64)
    p.add_argument("--min-n", type=int, default=60)
    p.add_argument("--top-per-book", type=int, default=4)
    args = p.parse_args(argv)
    run(
        email=bool(args.email),
        min_cross_books=int(args.min_cross_books),
        min_z=float(args.min_z),
        min_n=int(args.min_n),
        top_per_book=int(args.top_per_book),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
