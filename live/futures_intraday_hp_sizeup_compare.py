"""Baseline vs HP-sized sensitivity for futures_intraday_hp_sizeup_v1.

Compares validated + near-miss (provisional / risk-budget) candidates at
1.0× / 1.25× / 2× / 3× / 4× on full-book net, MTM DD, N/S, and yearly
best / worst / bad (lowest N/S) years. Also writes the three-way
prior-opposed incremental-sleeve overlap report.

Linear 2×/3×/4× tables are **sizing sensitivity only** — not validation.
Each intended multiplier needs its own null suite.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.futures_intraday_hp_sizeup_compare --email
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
from live.intraday_condition_overlay import hp_mask, score_nets
from live.notify_email import send_email

from .futures_intraday_hp_sizeup_lib import (
    COND_COL,
    LIVE_HUB,
    NULLS_HUB,
    PROFILE_HUB,
    STUDY,
)

# Deployment candidates (tier, decision label, book, condition, bucket, short label)
DEFAULT_CANDIDATES: List[Tuple[str, str, str, str, str, str]] = [
    (
        "A",
        "SIZE-UP VALIDATED",
        "es_prior_opposed_legacy",
        "ST-event age",
        "st_age_gt180m",
        "ES prior-opposed legacy, ST age >180m",
    ),
    (
        "A",
        "SIZE-UP VALIDATED",
        "ym_prior_opposed_rl",
        "Overnight range third",
        "on_middle",
        "YM prior-opposed RL, overnight middle third",
    ),
    (
        "B",
        "PROVISIONAL PAPER",
        "nq_prior_opposed_rl",
        "Opening 15m range vs ATR",
        "or_norm",
        "NQ prior-opposed RL, normal opening 15m range",
    ),
    (
        "C",
        "RISK-BUDGET PROFILE",
        "nq_st_pmc_3r",
        "Entry hour (NY)",
        "11",
        "NQ ST+PMC hour 11",
    ),
    (
        "C",
        "RISK-BUDGET PROFILE",
        "nq_v2b_s113",
        "Prior RTH close location",
        "prior_close_mid_third",
        "NQ v2b prior RTH mid-third",
    ),
    (
        "C",
        "RISK-BUDGET PROFILE",
        "ym_prior_opposed_rl",
        "Prior RTH range percentile",
        "prior_range_norm",
        "YM prior-opposed prior-RTH-normal",
    ),
    (
        "C",
        "RISK-BUDGET PROFILE",
        "ym_st_pmc_3r",
        "Day of week",
        "Thursday",
        "YM ST+PMC Thursday",
    ),
]

PRIOR_OPPOSED_TRIPLE = [
    ("es_prior_opposed_legacy", "ST-event age", "st_age_gt180m"),
    ("ym_prior_opposed_rl", "Overnight range third", "on_middle"),
    ("nq_prior_opposed_rl", "Opening 15m range vs ATR", "or_norm"),
]

MULTS = (1.0, 1.25, 2.0, 3.0, 4.0)


def _patch_cond() -> None:
    overlay.COND_COL.clear()
    overlay.COND_COL.update(COND_COL)


def _load_campaigns() -> pd.DataFrame:
    path = PROFILE_HUB / "all_campaigns.csv"
    if not path.exists():
        raise FileNotFoundError("missing %s — run futures profile first" % path)
    camp = pd.read_csv(path)
    camp["entry_ts"] = pd.to_datetime(camp["entry_ts"], utc=True)
    if "session_date" not in camp.columns:
        camp["session_date"] = camp["entry_ts"].dt.strftime("%Y-%m-%d")
    else:
        camp["session_date"] = camp["session_date"].astype(str)
    if "direction" not in camp.columns and "side" in camp.columns:
        camp["direction"] = np.where(camp["side"].astype(str) == "long", 1, -1)
    return camp


def yearly_stats(df: pd.DataFrame, nets: np.ndarray) -> Dict:
    tmp = df[["year"]].copy()
    tmp["net"] = nets
    rows = []
    for y, g in tmp.groupby("year"):
        sc = score_nets(g["net"].to_numpy(float))
        rows.append(
            {
                "year": int(y),
                "net": sc["net"],
                "stress": sc["stress"],
                "ns": sc["ns"],
                "max_dd": sc["max_dd"],
                "n": sc["n"],
            }
        )
    yd = pd.DataFrame(rows)
    if yd.empty:
        raise ValueError("empty yearly frame")
    best = yd.loc[yd["net"].idxmax()]
    worst = yd.loc[yd["net"].idxmin()]
    yd2 = yd[yd["n"] >= 5] if (yd["n"] >= 5).any() else yd
    bad = yd2.loc[yd2["ns"].idxmin()]
    return {
        "best_year": int(best["year"]),
        "best_net": float(best["net"]),
        "best_ns": float(best["ns"]),
        "best_dd": float(best["max_dd"]),
        "worst_year": int(worst["year"]),
        "worst_net": float(worst["net"]),
        "worst_ns": float(worst["ns"]),
        "worst_dd": float(worst["max_dd"]),
        "bad_year": int(bad["year"]),
        "bad_net": float(bad["net"]),
        "bad_ns": float(bad["ns"]),
        "bad_dd": float(bad["max_dd"]),
        "yearly": yd,
    }


def size_sensitivity(
    campaigns: pd.DataFrame,
    candidates: Sequence[Tuple[str, str, str, str, str, str]] = DEFAULT_CANDIDATES,
    mults: Sequence[float] = MULTS,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    book_rows: List[dict] = []
    year_rows: List[dict] = []
    for tier, decision, book, cond, bucket, label in candidates:
        df = campaigns[campaigns["book"] == book].sort_values("entry_ts").reset_index(drop=True)
        if df.empty:
            continue
        m = hp_mask(df, cond, bucket)
        if not m.any():
            raise RuntimeError("empty HP mask for %s %s=%s" % (book, cond, bucket))
        base = df["net_usd"].to_numpy(float)
        base_sc = score_nets(base)
        ybase = yearly_stats(df, base)
        for mult in mults:
            sized = base.copy()
            if float(mult) != 1.0:
                sized[m] = sized[m] * float(mult)
            sc = score_nets(sized)
            ys = yearly_stats(df, sized)
            book_rows.append(
                {
                    "tier": tier,
                    "decision": decision,
                    "label": label,
                    "book": book,
                    "condition": cond,
                    "bucket": str(bucket),
                    "mult": float(mult),
                    "hp_n": int(m.sum()),
                    "hp_pct": round(100.0 * float(m.mean()), 2),
                    "net": round(sc["net"], 2),
                    "mtm_dd": round(sc["max_dd"], 2),
                    "stress": round(sc["stress"], 2),
                    "ns": round(sc["ns"], 3),
                    "delta_net": round(sc["net"] - base_sc["net"], 2),
                    "delta_mtm_dd": round(sc["max_dd"] - base_sc["max_dd"], 2),
                    "delta_ns": round(sc["ns"] - base_sc["ns"], 3),
                    "stress_x": (
                        round(sc["stress"] / base_sc["stress"], 4)
                        if base_sc["stress"] > 1
                        else float("nan")
                    ),
                    "best_year": ys["best_year"],
                    "best_net": round(ys["best_net"], 2),
                    "best_ns": round(ys["best_ns"], 3),
                    "best_mtm_dd": round(ys["best_dd"], 2),
                    "worst_year": ys["worst_year"],
                    "worst_net": round(ys["worst_net"], 2),
                    "worst_ns": round(ys["worst_ns"], 3),
                    "worst_mtm_dd": round(ys["worst_dd"], 2),
                    "bad_year": ys["bad_year"],
                    "bad_net": round(ys["bad_net"], 2),
                    "bad_ns": round(ys["bad_ns"], 3),
                    "bad_mtm_dd": round(ys["bad_dd"], 2),
                    "base_best_year": ybase["best_year"],
                    "base_best_net": round(ybase["best_net"], 2),
                    "base_best_ns": round(ybase["best_ns"], 3),
                    "base_worst_year": ybase["worst_year"],
                    "base_worst_net": round(ybase["worst_net"], 2),
                    "base_worst_ns": round(ybase["worst_ns"], 3),
                    "base_bad_year": ybase["bad_year"],
                    "base_bad_net": round(ybase["bad_net"], 2),
                    "base_bad_ns": round(ybase["bad_ns"], 3),
                }
            )
            for _, yr in ys["yearly"].iterrows():
                year_rows.append(
                    {
                        "tier": tier,
                        "book": book,
                        "condition": cond,
                        "bucket": str(bucket),
                        "label": label,
                        "mult": float(mult),
                        "year": int(yr["year"]),
                        "net": round(float(yr["net"]), 2),
                        "stress": round(float(yr["stress"]), 2),
                        "ns": round(float(yr["ns"]), 3),
                        "mtm_dd": round(float(yr["max_dd"]), 2),
                        "n": int(yr["n"]),
                    }
                )
    return pd.DataFrame(book_rows), pd.DataFrame(year_rows)


def prior_opposed_overlap(campaigns: pd.DataFrame) -> pd.DataFrame:
    masks = {}
    for book, cond, bucket in PRIOR_OPPOSED_TRIPLE:
        df = campaigns[campaigns["book"] == book].sort_values("entry_ts").reset_index(drop=True)
        m = hp_mask(df, cond, bucket)
        masks[book] = (df, m, cond, bucket)

    rows = []
    keys = list(masks)
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            dfa, ma, ca, ba = masks[a]
            dfb, mb, cb, bb = masks[b]
            dates_a = set(dfa.loc[ma, "session_date"].astype(str))
            dates_b = set(dfb.loc[mb, "session_date"].astype(str))
            shared = sorted(dates_a & dates_b)
            same_dir = both = 0
            joint_day: List[float] = []
            for d in shared:
                sa = dfa.loc[(dfa["session_date"].astype(str) == d) & ma]
                sb = dfb.loc[(dfb["session_date"].astype(str) == d) & mb]
                if len(sa) and len(sb):
                    both += 1
                    if int(sa["direction"].iloc[0]) == int(sb["direction"].iloc[0]):
                        same_dir += 1
                    joint_day.append(
                        0.25 * float(sa["net_usd"].sum()) + 0.25 * float(sb["net_usd"].sum())
                    )

            def _daily_inc(df: pd.DataFrame, mask: np.ndarray) -> pd.Series:
                inc = np.zeros(len(df))
                inc[mask] = 0.25 * df["net_usd"].to_numpy(float)[mask]
                tmp = df[["session_date"]].copy()
                tmp["inc"] = inc
                return tmp.groupby("session_date")["inc"].sum()

            joined = pd.concat(
                [_daily_inc(dfa, ma), _daily_inc(dfb, mb)], axis=1, keys=["a", "b"]
            ).fillna(0.0)
            corr = float(joined["a"].corr(joined["b"])) if len(joined) > 3 else float("nan")
            jsc = score_nets((joined["a"] + joined["b"]).to_numpy(float))
            rows.append(
                {
                    "book_a": a,
                    "cond_a": "%s=%s" % (ca, ba),
                    "book_b": b,
                    "cond_b": "%s=%s" % (cb, bb),
                    "shared_hp_dates": len(shared),
                    "same_dir_rate": round(same_dir / both, 3) if both else float("nan"),
                    "inc_corr": round(corr, 4) if corr == corr else float("nan"),
                    "inc_joint_net": round(jsc["net"], 2),
                    "inc_joint_stress": round(jsc["stress"], 2),
                    "inc_joint_ns": round(jsc["ns"], 3),
                    "inc_joint_mtm_dd": round(jsc["max_dd"], 2),
                    "worst_simultaneous_loss": (
                        round(min(joint_day), 2) if joint_day else float("nan")
                    ),
                    "simultaneous_boosted_extra_units": 0.5,
                    "gate": "HOLD_ONE_HP_PER_SESSION",
                }
            )
    return pd.DataFrame(rows)


def _money(x: float) -> str:
    if x != x or math.isinf(x):
        return "n/a"
    sign = "+" if x >= 0 else "-"
    return "%s$%s" % (sign, "{:,.0f}".format(abs(x)))


def render_comparison_md(br: pd.DataFrame, ov: pd.DataFrame) -> str:
    lines = [
        "# Futures HP size sensitivity vs baseline",
        "",
        "Study: `%s`" % STUDY,
        "",
        "Linear campaign scaling only. **1.25×** is the only multiplier with a",
        "null-suite decision. **2×/3×/4×** = sensitivity / stress research — do",
        "**not** promote from these columns.",
        "",
        "Metrics: full-book **net**, **MTM DD** (path max drawdown), **N/S**,",
        "yearly **worst** (min net), **bad** (min N/S, n≥5), **best** (max net).",
        "",
        "## Book-level vs baseline",
        "",
        "| tier | book / bucket | mult | net | MTM DD | N/S | stress× | Δnet | ΔN/S | worst yr net | bad yr N/S | best yr net |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    show = br[br["mult"].isin(list(MULTS))].copy()
    for _, r in show.iterrows():
        lines.append(
            "| %s | %s `%s` | %s× | %s | %s | %.2f | %.2f | %s | %+.2f | %d %s | %d %.2f | %d %s |"
            % (
                r["tier"],
                r["book"],
                r["bucket"],
                ("%g" % float(r["mult"])),
                _money(r["net"]),
                _money(r["mtm_dd"]),
                r["ns"],
                r["stress_x"],
                _money(r["delta_net"]),
                r["delta_ns"],
                int(r["worst_year"]),
                _money(r["worst_net"]),
                int(r["bad_year"]),
                r["bad_ns"],
                int(r["best_year"]),
                _money(r["best_net"]),
            )
        )

    lines.extend(
        [
            "",
            "## 1.25× lift snapshot (validated + near misses)",
            "",
            "| tier | candidate | base N/S | @1.25 N/S | ΔN/S | base MTM DD | @1.25 MTM DD | stress× |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tier in ("A", "B", "C"):
        sub = br[(br["tier"] == tier) & (br["mult"].isin([1.0, 1.25]))]
        for book in sub["book"].unique():
            for bucket in sub[sub["book"] == book]["bucket"].unique():
                r0 = sub[(sub["book"] == book) & (sub["bucket"] == bucket) & (sub["mult"] == 1.0)]
                r1 = sub[(sub["book"] == book) & (sub["bucket"] == bucket) & (sub["mult"] == 1.25)]
                if r0.empty or r1.empty:
                    continue
                a, b = r0.iloc[0], r1.iloc[0]
                lines.append(
                    "| %s | %s / `%s` | %.2f | **%.2f** | %+.2f | %s | %s | %.3f |"
                    % (
                        tier,
                        book,
                        bucket,
                        a["ns"],
                        b["ns"],
                        b["delta_ns"],
                        _money(a["mtm_dd"]),
                        _money(b["mtm_dd"]),
                        b["stress_x"],
                    )
                )

    lines.extend(
        [
            "",
            "## Prior-opposed incremental-sleeve overlap",
            "",
            "Until this joint gate is explicitly cleared for simultaneous boosts,",
            "implement **at most one prior-opposed HP multiplier across ES/YM/NQ",
            "per session**.",
            "",
            "| pair | shared HP dates | same-dir | inc corr | joint inc N/S | joint MTM DD | worst sim loss |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in ov.iterrows():
        lines.append(
            "| %s ↔ %s | %d | %.0f%% | %.3f | %.2f | %s | %s |"
            % (
                r["book_a"].replace("_prior_opposed_legacy", "").replace("_prior_opposed_rl", ""),
                r["book_b"].replace("_prior_opposed_legacy", "").replace("_prior_opposed_rl", ""),
                int(r["shared_hp_dates"]),
                100.0 * float(r["same_dir_rate"]) if r["same_dir_rate"] == r["same_dir_rate"] else float("nan"),
                r["inc_corr"],
                r["inc_joint_ns"],
                _money(r["inc_joint_mtm_dd"]),
                _money(r["worst_simultaneous_loss"]),
            )
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `size_sensitivity.csv` / `size_sensitivity_yearly.csv`",
            "- `prior_opposed_overlap_report.csv`",
            "- `LIVE_PLAN.md` / `DEPLOYMENT_PLAN.md`",
            "- Null decisions: `../futures_intraday_hp_sizeup_nulls/SUMMARY.md`",
            "",
        ]
    )
    return "\n".join(lines)


def phone_body(br: pd.DataFrame, ov: pd.DataFrame) -> str:
    lines = [
        "Study: %s" % STUDY,
        "Hub: live/state/futures_intraday_hp_live_plan/",
        "",
        "1.25× vs baseline (net / MTM DD / N/S):",
    ]
    for _, r in br[br["mult"] == 1.25].iterrows():
        b0 = br[
            (br["book"] == r["book"])
            & (br["bucket"] == r["bucket"])
            & (br["mult"] == 1.0)
        ].iloc[0]
        lines.append(
            "  Tier%s %s: N/S %.2f→%.2f (Δ%+.2f); DD %s→%s; stress×%.3f"
            % (
                r["tier"],
                r["bucket"],
                b0["ns"],
                r["ns"],
                r["delta_ns"],
                _money(b0["mtm_dd"]),
                _money(r["mtm_dd"]),
                r["stress_x"],
            )
        )
    lines.append("")
    lines.append("2×/3×/4× = sensitivity only (not validated).")
    lines.append("Prior-opposed overlap: hold ≤1 HP/session until joint gate clears.")
    for _, r in ov.iterrows():
        lines.append(
            "  %s↔%s shared=%d sameDir=%.0f%% corr=%.3f worstSim=%s"
            % (
                r["book_a"][:2],
                r["book_b"][:2],
                int(r["shared_hp_dates"]),
                100 * float(r["same_dir_rate"]) if r["same_dir_rate"] == r["same_dir_rate"] else 0,
                r["inc_corr"],
                _money(r["worst_simultaneous_loss"]),
            )
        )
    lines.append("")
    lines.append(
        "Core: two causal-looking 1.25× allocations survived full nulls "
        "(ES ST-age>180, YM overnight-middle); NQ OR-norm provisional."
    )
    return "\n".join(lines)


def run(*, email: bool = False) -> Path:
    _patch_cond()
    LIVE_HUB.mkdir(parents=True, exist_ok=True)
    campaigns = _load_campaigns()
    br, yr = size_sensitivity(campaigns)
    ov = prior_opposed_overlap(campaigns)
    br.to_csv(LIVE_HUB / "size_sensitivity.csv", index=False)
    yr.to_csv(LIVE_HUB / "size_sensitivity_yearly.csv", index=False)
    ov.to_csv(LIVE_HUB / "prior_opposed_overlap_report.csv", index=False)
    md = render_comparison_md(br, ov)
    (LIVE_HUB / "COMPARISON.md").write_text(md, encoding="utf-8")
    body = phone_body(br, ov)
    (LIVE_HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(subject="potions: futures HP size comparison", body=body)
    return LIVE_HUB / "COMPARISON.md"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)
    run(email=args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
