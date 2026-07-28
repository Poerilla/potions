"""Monday OR cluster / levels / skip study — all Phase 2 instruments.

Same three phases as ``xauusd_monday_or_cluster_skip_study`` for each
pair-tag anchor. Sitout thresholds are instrument-scaled (trade |net| p90
multiples) so FX pairs are not blindly given gold's +100 pts.

Artifacts → live/state/monday_or_phase2/cluster_skip_multi/
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_data import load_fx_1m_by_ny_date
from .monday_or_phase2_tags import PHASE1_STATE_ROOTS, PAIR_PHASE2_DEFAULT
from .xauusd_monday_or_cluster_skip_study import (
    annotate_levels,
    bucket_stats,
    calendar_clustering,
    cluster_verdict,
    sim_heat_sitout,
    sim_heat_sitout_after_losses,
    sim_skip_after_n_losses,
    sim_skip_after_n_wins,
    sim_skip_after_outcome,
    state_conditional_wr,
    streak_stats,
    summarize_book,
    trade_outcomes,
    win_run_start_level_share,
)
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

NY = pytz.timezone("America/New_York")
REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "live" / "state" / "monday_or_phase2" / "cluster_skip_multi"

# (pair, tag) — Phase 2 defaults + USDJPY alternate
INSTRUMENTS: List[Tuple[str, str]] = [
    ("USDJPY", "M2_S3_R1"),
    ("USDJPY", "M2_S3_R2"),
    ("EURUSD", "M1_S2_R2"),
    ("GBPUSD", "M1_S1_R2"),
    ("AUDJPY", "M1_S2_R2"),
    ("XAUUSD", "M2_S2_R3"),
]

# Entry-near widths (price units) for prior week/month extremes.
NEAR_BY_PAIR: Dict[str, Tuple[float, float]] = {
    "XAUUSD": (5.0, 10.0),
    "USDJPY": (0.05, 0.10),
    "AUDJPY": (0.05, 0.10),
    "EURUSD": (0.0005, 0.001),
    "GBPUSD": (0.0005, 0.001),
}

# Broker Phase 1 N/S (USD) for context in summaries.
BROKER_NS: Dict[str, float] = {
    "USDJPY_M2_S3_R1": 8.20,
    "USDJPY_M2_S3_R2": 7.0,  # approx; see Phase 1 notes
    "EURUSD_M1_S2_R2": 2.0,
    "GBPUSD_M1_S1_R2": 2.0,
    "AUDJPY_M1_S2_R2": 2.0,
    "XAUUSD_M2_S2_R3": 1.90,
}


def _slug(pair: str, tag: str) -> str:
    return "%s_%s" % (pair.lower(), tag.lower())


def _fills_path(pair: str, tag: str) -> Path:
    root = REPO / PHASE1_STATE_ROOTS[pair]
    return root / "states" / _slug(pair, tag) / "fills.csv"


def _progress(out: Path, msg: str) -> None:
    print(msg, flush=True)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def build_prior_levels(pair: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    daily_path = REPO / "fx" / ("%s_daily.csv" % pair.lower())
    monthly_path = REPO / "fx" / ("%s_monthly.csv" % pair.lower())
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    tmp = daily.reset_index(drop=True)
    tmp["week_mon"] = tmp["date"] - pd.to_timedelta(tmp["date"].dt.weekday, unit="D")
    weekly = (
        tmp.groupby("week_mon", as_index=False)
        .agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .sort_values("week_mon")
    )
    weekly["prior_week_high"] = weekly["high"].shift(1)
    weekly["prior_week_low"] = weekly["low"].shift(1)

    if monthly_path.exists():
        monthly = pd.read_csv(monthly_path, parse_dates=["date"]).sort_values("date")
        monthly["date"] = pd.to_datetime(monthly["date"]).dt.normalize()
    else:
        # Build month bars from daily (EURUSD missing monthly file).
        d = daily.set_index("date")
        monthly = (
            d.resample("MS")
            .agg(high=("high", "max"), low=("low", "min"), close=("close", "last"), open=("open", "first"))
            .dropna(subset=["close"])
            .reset_index()
            .rename(columns={"date": "date"})
        )
    monthly["ym"] = monthly["date"].dt.strftime("%Y-%m")
    monthly["prior_month_high"] = monthly["high"].shift(1)
    monthly["prior_month_low"] = monthly["low"].shift(1)
    return weekly, monthly


def load_15m(pair: str, out: Path) -> Tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    one_m = REPO / "fx" / ("%s_1m.csv" % pair.lower())
    _progress(out, "loading %s 1m → 15m..." % pair)
    gby = load_fx_1m_by_ny_date(one_m, pair)
    df1 = concat_all_1m(gby)
    m15 = (
        df1.resample("15min", label="left", closed="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna(subset=["open"])
    )
    _progress(out, "15m bars: %d" % len(m15))
    return m15.index, m15["high"].to_numpy(), m15["low"].to_numpy()


def sitout_thresholds(trades: pd.DataFrame, pair: str) -> List[Tuple[str, float]]:
    """Instrument-scaled week sitout levels + XAU absolute anchors."""
    abs_net = trades.net_pts.abs()
    p90 = float(abs_net.quantile(0.90)) if len(abs_net) else 0.0
    if p90 <= 0:
        p90 = float(abs_net.mean()) if len(abs_net) else 1.0
    week_pos = trades.groupby("week_mon")["net_pts"].sum()
    week_pos = week_pos[week_pos > 0]
    out: List[Tuple[str, float]] = []
    for mult in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        thr = round(mult * p90, 6)
        out.append(("sitout_week_after_%.2fx_p90(%.6g)" % (mult, thr), thr))
    if len(week_pos):
        for q, label in ((0.25, "p25_pos_week"), (0.50, "p50_pos_week"), (0.75, "p75_pos_week")):
            thr = float(week_pos.quantile(q))
            out.append(("sitout_week_after_%s(%.6g)" % (label, thr), thr))
    # Keep gold absolute anchors for XAU continuity / cross-check.
    if pair == "XAUUSD":
        out.append(("sitout_week_after_+50pts", 50.0))
        out.append(("sitout_week_after_+100pts", 100.0))
    # Deduplicate by threshold
    seen = set()
    uniq: List[Tuple[str, float]] = []
    for name, thr in out:
        key = round(thr, 8)
        if key in seen or thr <= 0:
            continue
        seen.add(key)
        uniq.append((name, thr))
    return uniq


def run_skip_grid(trades: pd.DataFrame, pair: str, out: Path) -> List[Dict[str, Any]]:
    base_n = len(trades)
    rules: List[Tuple[str, List[bool]]] = []
    rules.append(("take_all", [True] * base_n))
    rules.append(("skip1_after_W", sim_skip_after_outcome(trades, skip_after_win=1, skip_after_loss=0)))
    rules.append(("skip1_after_2W", sim_skip_after_n_wins(trades, 2, 1)))
    rules.append(("skip1_after_1L", sim_skip_after_outcome(trades, skip_after_win=0, skip_after_loss=1)))
    rules.append(("skip1_after_2L", sim_skip_after_n_losses(trades, 2, 1)))
    rules.append(("skip1_after_3L", sim_skip_after_n_losses(trades, 3, 1)))
    rules.append(("skip2_after_2L", sim_skip_after_n_losses(trades, 2, 2)))
    rules.append(("skip2_after_3L", sim_skip_after_n_losses(trades, 3, 2)))
    for name, thr in sitout_thresholds(trades, pair):
        rules.append((name, sim_heat_sitout(trades, after_week_net=thr)))
    rules.append(("sitout_week_after_3L", sim_heat_sitout_after_losses(trades, n_losses_in_week=3)))
    rules.append(("sitout_week_after_4L", sim_heat_sitout_after_losses(trades, n_losses_in_week=4)))

    rows = []
    for name, mask in rules:
        taken = trades[mask]
        skipped = trades[[not m for m in mask]]
        row: Dict[str, Any] = {"rule": name, **summarize_book(taken, base_n)}
        if len(skipped):
            row["skipped_n"] = int(len(skipped))
            row["skipped_wr"] = round(100.0 * skipped.win.mean(), 1)
            row["skipped_net_pts"] = round(float(skipped.net_pts.sum()), 2)
            row["skipped_mean_pts"] = round(float(skipped.net_pts.mean()), 4)
        else:
            row["skipped_n"] = 0
            row["skipped_wr"] = None
            row["skipped_net_pts"] = 0.0
            row["skipped_mean_pts"] = None
        rows.append(row)
        _progress(
            out,
            "  %s n=%d WR=%.1f net=%.4g mean=%.4g maxL=%s cover=%.1f ns=%.2f"
            % (
                name,
                row["n"],
                row["wr"],
                row["net_pts"],
                row["mean_pts"],
                row.get("max_loss_streak"),
                row["coverage_pct"],
                row["ns_proxy"],
            ),
        )
    return rows


def annotate_with_near(
    trades: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    ts_idx: pd.DatetimeIndex,
    highs: np.ndarray,
    lows: np.ndarray,
    near_tight: float,
    near_wide: float,
) -> pd.DataFrame:
    """Wrap annotate_levels with pair-specific near widths via temporary module globals."""
    import potions.live.xauusd_monday_or_cluster_skip_study as mod

    old_t, old_w = mod.NEAR_TIGHT, mod.NEAR_WIDE
    mod.NEAR_TIGHT, mod.NEAR_WIDE = near_tight, near_wide
    try:
        return annotate_levels(trades, weekly, monthly, ts_idx, highs, lows)
    finally:
        mod.NEAR_TIGHT, mod.NEAR_WIDE = old_t, old_w


def run_one(pair: str, tag: str) -> Dict[str, Any]:
    slug = _slug(pair, tag)
    out = OUT_ROOT / slug
    out.mkdir(parents=True, exist_ok=True)
    fills_path = _fills_path(pair, tag)
    _progress(out, "START %s %s ← %s" % (pair, tag, fills_path))
    if not fills_path.exists():
        _progress(out, "MISSING fills — skip")
        return {"pair": pair, "tag": tag, "error": "missing_fills", "path": str(fills_path)}

    fills = pd.read_csv(fills_path)
    trades = trade_outcomes(fills)
    base_n = len(trades)
    _progress(out, "trades: %d" % base_n)

    # Phase 1
    streaks = streak_stats(trades.win.tolist())
    cal = calendar_clustering(trades)
    cond = state_conditional_wr(trades)
    base_book = summarize_book(trades, base_n)
    verdict = cluster_verdict(cond, base_book["wr"])
    phase1 = {
        "pair": pair,
        "tag": tag,
        "baseline": base_book,
        "streaks": streaks,
        "calendar": cal,
        "state_conditional": cond,
        "verdict_notes": verdict,
        "first": str(trades.entry_dt.iloc[0]),
        "last": str(trades.entry_dt.iloc[-1]),
    }
    (out / "phase1_cluster.json").write_text(json.dumps(phase1, indent=2, default=str), encoding="utf-8")
    for n in verdict:
        _progress(out, "VERDICT: " + n)

    # Phase 2 levels
    near_t, near_w = NEAR_BY_PAIR[pair]
    weekly, monthly = build_prior_levels(pair)
    ts_idx, highs, lows = load_15m(pair, out)
    ann = annotate_with_near(trades, weekly, monthly, ts_idx, highs, lows, near_t, near_w)
    # Rename near columns are fixed to _5/_10 from annotate; also store actual widths
    ann.to_csv(out / "trades_annotated.csv", index=False)
    level_buckets = [
        bucket_stats(ann, ann.touch_prior_week_ext, "path_touch_prior_week_ext"),
        bucket_stats(ann, ~ann.touch_prior_week_ext, "no_path_touch_prior_week_ext"),
        bucket_stats(ann, ann.touch_prior_month_ext, "path_touch_prior_month_ext"),
        bucket_stats(ann, ~ann.touch_prior_month_ext, "no_path_touch_prior_month_ext"),
        bucket_stats(ann, ann.touch_any_wm, "path_touch_week_or_month_ext"),
        bucket_stats(ann, ~ann.touch_any_wm, "no_path_touch_week_or_month"),
        bucket_stats(ann, ann.near_prior_week_5, "entry_near_prior_week_ext_tight"),
        bucket_stats(ann, ann.near_prior_week_10, "entry_near_prior_week_ext_wide"),
        bucket_stats(ann, ann.near_prior_month_5, "entry_near_prior_month_ext_tight"),
        bucket_stats(ann, ann.near_prior_month_10, "entry_near_prior_month_ext_wide"),
        bucket_stats(ann, ann.near_any_wm_10, "entry_near_week_or_month_wide"),
        bucket_stats(ann, ~ann.near_any_wm_10, "entry_not_near_week_or_month_wide"),
    ]
    win_start = win_run_start_level_share(ann)
    phase2 = {
        "near_tight": near_t,
        "near_wide": near_w,
        "buckets": level_buckets,
        "win_run_starts_vs_touch": win_start,
    }
    (out / "phase2_levels.json").write_text(json.dumps(phase2, indent=2, default=str), encoding="utf-8")
    _progress(out, "levels done; win-run start touch share=%s" % win_start)

    # Phase 3
    _progress(out, "skip grid...")
    skip_rows = run_skip_grid(trades, pair, out)
    pd.DataFrame(skip_rows).to_csv(out / "skip_grid.csv", index=False)
    (out / "phase3_skip_grid.json").write_text(json.dumps(skip_rows, indent=2), encoding="utf-8")

    ranked = sorted(
        [r for r in skip_rows if r.get("coverage_pct", 0) >= 50],
        key=lambda r: (r.get("ns_proxy") or 0, r.get("mean_pts") or 0, r.get("net_pts") or 0),
        reverse=True,
    )
    take_all = next(r for r in skip_rows if r["rule"] == "take_all")
    best = ranked[0] if ranked else take_all
    key = "%s_%s" % (pair, tag)
    summary = {
        "pair": pair,
        "tag": tag,
        "baseline_broker_ns_usd": BROKER_NS.get(key),
        "phase1_verdict": verdict,
        "take_all": take_all,
        "best_skip_rule_cov_ge_50": best,
        "best_skip_rules_cov_ge_50": ranked[:5],
        "delta_ns_vs_take_all": round((best.get("ns_proxy") or 0) - (take_all.get("ns_proxy") or 0), 2),
        "delta_net_vs_take_all": round((best.get("net_pts") or 0) - (take_all.get("net_pts") or 0), 4),
        "core_xau_sitout_100": next(
            (r for r in skip_rows if r["rule"] == "sitout_week_after_+100pts"), None
        ),
    }
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    md = [
        "# %s %s — cluster / levels / skip" % (pair, tag),
        "",
        "## Baseline (trade pts)",
        "- n=%d WR=%.1f%% net_pts=%s mean=%s maxL=%s stress=%s N/S_proxy=%s"
        % (
            base_book["n"],
            base_book["wr"],
            base_book["net_pts"],
            base_book["mean_pts"],
            base_book.get("max_loss_streak"),
            base_book["stress_pts"],
            base_book["ns_proxy"],
        ),
        "",
        "## Cluster verdict",
    ]
    md.extend(["- " + v for v in verdict])
    md.extend(
        [
            "",
            "## Calendar",
            "- top week %s net=%s share=%.1f%%"
            % (cal["top_week"], cal["top_week_net"], 100 * cal["top_week_share"]),
            "- top 5%% weeks share of gross + = %.1f%%" % (100 * cal["top_5pct_share_of_gross_pos"]),
            "",
            "## Skip grid (coverage ≥ 50%, ranked by N/S proxy)",
            "",
            "| rule | n | WR | net | mean | maxL | cover | stress | N/S |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in ranked[:8]:
        md.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["rule"],
                r["n"],
                r["wr"],
                r["net_pts"],
                r["mean_pts"],
                r.get("max_loss_streak"),
                r["coverage_pct"],
                r["stress_pts"],
                r["ns_proxy"],
            )
        )
    (out / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    _progress(out, "DONE → %s" % out)
    return summary


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    cross: List[Dict[str, Any]] = []
    for pair, tag in INSTRUMENTS:
        # Prefer PAIR_PHASE2_DEFAULT when tag omitted — here tags are explicit.
        assert PAIR_PHASE2_DEFAULT.get(pair) or tag
        summary = run_one(pair, tag)
        cross.append(summary)

    # Cross-instrument rollup
    rows = []
    for s in cross:
        if s.get("error"):
            rows.append(s)
            continue
        ta = s["take_all"]
        best = s["best_skip_rule_cov_ge_50"]
        rows.append(
            {
                "pair": s["pair"],
                "tag": s["tag"],
                "baseline_n": ta["n"],
                "baseline_wr": ta["wr"],
                "baseline_net": ta["net_pts"],
                "baseline_ns": ta["ns_proxy"],
                "best_rule": best["rule"],
                "best_n": best["n"],
                "best_wr": best["wr"],
                "best_net": best["net_pts"],
                "best_ns": best["ns_proxy"],
                "best_cover": best["coverage_pct"],
                "delta_ns": s["delta_ns_vs_take_all"],
                "delta_net": s["delta_net_vs_take_all"],
                "calendar_flag": (s.get("phase1_verdict") or [""])[-1] if s.get("phase1_verdict") else "",
                "verdict_notes": s.get("phase1_verdict"),
            }
        )
    pd.DataFrame(rows).to_csv(OUT_ROOT / "CROSS_SUMMARY.csv", index=False)
    (OUT_ROOT / "CROSS_SUMMARY.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    md = [
        "# Monday OR cluster/skip — cross-instrument",
        "",
        "Sitout thresholds are **instrument-scaled** (trade |net| p90 multiples + pos-week quantiles).",
        "XAUUSD also keeps absolute +50/+100 pts; **+100 is core** on `M2_S2_R3`.",
        "",
        "| pair | tag | base N/S | best rule | best N/S | ΔN/S | cover | Δnet |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        if r.get("error"):
            md.append("| %s | %s | ERR | %s | | | | |" % (r["pair"], r["tag"], r["error"]))
            continue
        md.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["pair"],
                r["tag"],
                r["baseline_ns"],
                r["best_rule"],
                r["best_ns"],
                r["delta_ns"],
                r["best_cover"],
                r["delta_net"],
            )
        )
    md.extend(
        [
            "",
            "## Core note (XAUUSD)",
            "",
            "- `week_sitout_after_pts=100` is part of Monday OR core for `M2_S2_R3`",
            "  (`live/strategies/monday_or_breakout.py` + `FOOTNOTE_TAGS`).",
            "- Do **not** copy +100 onto FX majors without per-pair threshold selection.",
            "",
        ]
    )
    (OUT_ROOT / "CROSS_SUMMARY.md").write_text("\n".join(md), encoding="utf-8")
    print("CROSS → %s" % (OUT_ROOT / "CROSS_SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
