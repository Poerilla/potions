#!/usr/bin/env python3
"""Build 50/50 monthly-DCA plus sliding-low timing hybrid reports."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import money, monthly_dca_open, summarize_curve
from qqq_sliding_3m_low_limit_dca_study import DEFAULT_START, OUT_DIR, max_drawdown
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


def blend_monthly_and_signal(monthly: pd.DataFrame, signal: pd.DataFrame, label: str) -> pd.DataFrame:
    cols = [
        "date",
        "contribution",
        "buy_amount",
        "cash",
        "shares",
        "invested_value",
        "equity",
        "total_contributed",
        "exposure_frac",
    ]
    merged = monthly[cols].merge(signal[cols + ["variant", "event_mode", "sizing_mode"]], on="date", suffixes=("_monthly", "_signal"))
    rows = []
    for _, row in merged.iterrows():
        cash = 0.5 * float(row["cash_monthly"]) + 0.5 * float(row["cash_signal"])
        invested = 0.5 * float(row["invested_value_monthly"]) + 0.5 * float(row["invested_value_signal"])
        equity = 0.5 * float(row["equity_monthly"]) + 0.5 * float(row["equity_signal"])
        rows.append(
            {
                "date": pd.Timestamp(row["date"]),
                "variant": label,
                "signal_variant": row["variant"],
                "event_mode": row["event_mode"],
                "sizing_mode": row["sizing_mode"],
                "monthly_leg_contribution": 0.5 * float(row["contribution_monthly"]),
                "signal_leg_contribution": 0.5 * float(row["contribution_signal"]),
                "contribution": 0.5 * float(row["contribution_monthly"]) + 0.5 * float(row["contribution_signal"]),
                "monthly_leg_buy_amount": 0.5 * float(row["buy_amount_monthly"]),
                "signal_leg_buy_amount": 0.5 * float(row["buy_amount_signal"]),
                "buy_amount": 0.5 * float(row["buy_amount_monthly"]) + 0.5 * float(row["buy_amount_signal"]),
                "cash": cash,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": 0.5 * float(row["total_contributed_monthly"]) + 0.5 * float(row["total_contributed_signal"]),
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_hybrid(curve: pd.DataFrame, monthly_summary: dict, signal_summary: pd.Series) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    buys = int(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0).gt(0).sum()) if not curve.empty else 0
    cash = float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0
    return {
        "variant": str(curve.iloc[0]["variant"]),
        "signal_variant": str(curve.iloc[0]["signal_variant"]),
        "event_mode": str(curve.iloc[0]["event_mode"]),
        "sizing_mode": str(curve.iloc[0]["sizing_mode"]),
        "signal_rate_per_year": float(signal_summary["signal_rate_per_year"]),
        "total_contributed": total,
        "ending_equity": ending,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "buys": buys,
        "avg_buy_amount": float(curve.loc[pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0) > 0, "buy_amount"].mean()) if buys else 0.0,
        "ending_cash": cash,
        "deployed_contributions_pct": (total - cash) / total * 100.0 if total else math.nan,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0) if not curve.empty else math.nan,
        "equity_vs_monthly": ending - float(monthly_summary["ending_equity"]),
        "signal_ending_equity": float(signal_summary["ending_equity"]),
        "signal_equity_vs_monthly": float(signal_summary["equity_vs_monthly"]),
    }


def plot_hybrids(monthly: pd.DataFrame, hybrids: pd.DataFrame, out: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(monthly["date"], monthly["equity"], color="#111827", linewidth=1.6, label="monthly_dca_open")
    colors = {
        "first_touch_per_month__static_full_window": "#2563eb",
        "first_touch_per_month__rolling_5y_rate": "#0f766e",
        "new_touch_cluster__rolling_5y_rate": "#b45309",
        "new_touch_cluster__static_full_window": "#7c3aed",
        "first_touch_per_month__expanding_prior_rate": "#dc2626",
        "new_touch_cluster__expanding_prior_rate": "#6b7280",
    }
    for variant, group in hybrids.groupby("signal_variant", sort=False):
        if variant not in colors:
            continue
        ax.plot(group["date"], group["equity"], color=colors[variant], linewidth=1.2, label="50/50 " + variant)
    ax.set_title(title)
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def write_report(out_dir: Path, lookback_months: int, monthly_summary: dict, hybrid_summary: pd.DataFrame) -> None:
    ranked = hybrid_summary.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    best = ranked.iloc[0]
    static = hybrid_summary[
        hybrid_summary["event_mode"].eq("first_touch_per_month") & hybrid_summary["sizing_mode"].eq("static_full_window")
    ]
    rolling = hybrid_summary[
        hybrid_summary["event_mode"].eq("first_touch_per_month") & hybrid_summary["sizing_mode"].eq("rolling_5y_rate")
    ]
    lines = [
        "# QQQ Sliding %d-Month Low 50/50 Hybrid" % lookback_months,
        "",
        "Hybrid rule: allocate half of each monthly contribution to blind QQQ monthly DCA and half to the selected sliding-low timing variant.",
        "",
        "- Total contribution remains **$1,000/month**.",
        "- Monthly leg contributes **$500/month** and buys the first trading day open.",
        "- Timing leg contributes **$500/month**, holds cash, and buys only on its sliding-low signal.",
        "- Static full-window sizing is diagnostic because it knows the full-window signal frequency; rolling/expanding rows are causal sizing approximations.",
        "",
        "Monthly DCA baseline: **%s ending equity**, **%s net**, **%s max DD**, **%.2f Net/DD**."
        % (
            money(float(monthly_summary["ending_equity"])),
            money(float(monthly_summary["net"])),
            money(float(monthly_summary["max_dd"])),
            float(monthly_summary["net_over_dd"]),
        ),
        "",
        "## Leaderboard",
        "",
        "| Rank | Timing Leg | Sizing | Signals/Yr | End Equity | Vs Monthly | Max DD | Net/DD | Deployed | Avg Exposure | Ending Cash |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        lines.append(
            "| %d | %s | %s | %.2f | %s | %s | %s | %.2f | %.1f%% | %.1f%% | %s |"
            % (
                rank,
                row["event_mode"],
                row["sizing_mode"],
                float(row["signal_rate_per_year"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                float(row["deployed_contributions_pct"]),
                float(row["avg_exposure_pct"]),
                money(float(row["ending_cash"])),
            )
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- Best 50/50 row is **%s / %s**, ending at **%s**, **%s** versus monthly DCA."
            % (best["event_mode"], best["sizing_mode"], money(float(best["ending_equity"])), money(float(best["equity_vs_monthly"]))),
        ]
    )
    if not static.empty:
        row = static.iloc[0]
        lines.append(
            "- The requested diagnostic **first-touch-per-month / static-full-window** hybrid ends at **%s**, **%s** versus monthly DCA."
            % (money(float(row["ending_equity"])), money(float(row["equity_vs_monthly"])))
        )
    if not rolling.empty:
        row = rolling.iloc[0]
        lines.append(
            "- The more defensible **first-touch-per-month / rolling-5y-rate** hybrid ends at **%s**, **%s** versus monthly DCA."
            % (money(float(row["ending_equity"])), money(float(row["equity_vs_monthly"])))
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Hybrid equity comparison: [`charts/hybrid_equity_vs_monthly.png`](charts/hybrid_equity_vs_monthly.png)",
            "",
            "## Files",
            "",
            "- `hybrid_50_50_summary.csv`",
            "- `hybrid_50_50_curves.csv`",
        ]
    )
    (out_dir / "HYBRID_50_50.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build 50/50 monthly DCA plus sliding-low timing hybrid report.")
    parser.add_argument("--lookback-months", type=int, default=2)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--study-root", type=Path, default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    study_root = args.study_root or ROOT / "nq" / "case_studies" / ("qqq_sliding_%dm_low_limit_dca_study" % args.lookback_months)
    if not (study_root / "curves.csv").exists() or not (study_root / "summary.csv").exists():
        raise FileNotFoundError("Run qqq_sliding_3m_low_limit_dca_study.py first for %s" % study_root)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh).sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])
    monthly = monthly_dca_open(daily, args.monthly_amount)
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)

    curves = pd.read_csv(study_root / "curves.csv", parse_dates=["date"])
    base_summary = pd.read_csv(study_root / "summary.csv")
    hybrid_parts = []
    summary_rows = []
    for variant, signal_curve in curves.groupby("variant", sort=False):
        label = "50_50_monthly_plus_%s" % variant
        hybrid = blend_monthly_and_signal(monthly, signal_curve, label)
        hybrid_parts.append(hybrid)
        signal_summary = base_summary[base_summary["variant"].eq(variant)].iloc[0]
        summary_rows.append(summarize_hybrid(hybrid, monthly_summary, signal_summary))

    hybrid_curves = pd.concat(hybrid_parts, ignore_index=True)
    hybrid_summary = pd.DataFrame(summary_rows)
    hybrid_summary.to_csv(study_root / "hybrid_50_50_summary.csv", index=False)
    hybrid_curves.to_csv(study_root / "hybrid_50_50_curves.csv", index=False)
    plot_hybrids(
        monthly,
        hybrid_curves,
        study_root / "charts" / "hybrid_equity_vs_monthly.png",
        "QQQ sliding %d-month low 50/50 hybrids vs monthly DCA" % args.lookback_months,
    )
    write_report(study_root, args.lookback_months, monthly_summary, hybrid_summary)
    print("Wrote %s" % (study_root / "HYBRID_50_50.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
