#!/usr/bin/env python3
"""Yearly-rotating ranks 8-10 SPY/QQQ/DIA OBV DCA backtest."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

import top_index_obv_yearly_rotation as base
from top_index_obv_yearly_rotation import (
    count_schedule_crosses,
    load_price_data,
    load_schedule,
    plot_equity,
    plot_frequency,
    run_etf_lump_sum,
    run_etf_monthly_dca,
    run_monthly_blind,
    run_obv,
    summarize_curve,
)
from etf_obv_bearish_dca_study import default_completed_end, money


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "nq" / "case_studies" / "top_index_obv_yearly_ranks_8_10"
DEFAULT_START = "2010-01-01"
DEFAULT_SCHEDULE = OUT_DIR / "annual_ranks_8_10_schedule.csv"


def relabel_frame(df: pd.DataFrame, old: str, new: str) -> pd.DataFrame:
    out = df.copy()
    if "variant" in out.columns:
        out["variant"] = out["variant"].replace(old, new)
    return out


def write_report(
    schedule: pd.DataFrame,
    summary: pd.DataFrame,
    start: str,
    end: str,
    monthly_amount: float,
    obv_mas: list[int],
) -> None:
    monthly = summary[summary["variant"].eq("monthly_blind_yearly_ranks_8_10")].iloc[0]
    obv = summary[summary["variant"].str.startswith("obv_")].copy().sort_values("ending_equity", ascending=False)
    best = obv.iloc[0]
    closest_5 = obv.assign(gap=(obv["avg_crosses_per_slot_year"] - 5.0).abs()).sort_values("gap").iloc[0]
    lines = [
        "# Yearly-Rotating Ranks 8-10 SPY / QQQ / DIA OBV DCA Backtest",
        "",
        "This is the annual-rotation version of the lower top-10 tranche test. Each calendar year uses an explicit beginning-of-year ranks 8, 9, and 10 schedule for SPY, QQQ, and DIA instead of applying the 2026 ranks to the past.",
        "",
        "Mechanics: nine persistent sleeves (`SPY_8..10`, `QQQ_8..10`, `DIA_8..10`) receive one ninth of each monthly contribution. At the start of each year the target ticker for new money changes to that year's schedule. Existing shares are held; there is **no annual liquidation**, no taxes, no fees, and no cash interest.",
        "",
        "Schedule status: `annual_ranks_8_10_schedule.csv` is a curated v0 public-holdings approximation. The mechanics are anti-hindsight; the schedule should be SEC/fund-document audited before treating the numbers as final.",
        "",
        "Window: **%s through %s**. Monthly contribution pool: **%s**. Tested OBV SMA lengths: **%s**."
        % (start, end, money(monthly_amount), ", ".join(str(x) for x in obv_mas)),
        "",
        "OBV sizing rule: for each SMA, count bearish crosses across the yearly schedule, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot-year`, then each active sleeve buys `MATCHED_ADD_AVERAGE / 9` when its current ticker's own OBV bearish cross fires.",
        "",
        "## Leaderboard",
        "",
        "| Rank | Variant | OBV SMA | Crosses / Slot-Year | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = pd.concat([summary[summary["variant"].eq("monthly_blind_yearly_ranks_8_10")], obv], ignore_index=True).sort_values("ending_equity", ascending=False)
    for idx, row in ranked.reset_index(drop=True).iterrows():
        lines.append(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %.2f%% | %s | %.2f | %.1f%% | %s |"
            % (
                idx + 1,
                row["variant"],
                "" if pd.isna(row["obv_ma"]) else str(int(row["obv_ma"])),
                "" if pd.isna(row["avg_crosses_per_slot_year"]) else "%.2f" % float(row["avg_crosses_per_slot_year"]),
                "" if pd.isna(row["matched_add_average"]) else money(float(row["matched_add_average"])),
                "" if pd.isna(row["slot_add_amount"]) else money(float(row["slot_add_amount"])),
                money(float(row["ending_equity"])),
                money(float(row["net"])),
                float(row["return_on_contributions_pct"]),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                float(row["avg_exposure_pct"]),
                money(float(row["ending_cash"])),
            )
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- Blind monthly yearly ranks 8-10 finishes at **%s**. Best OBV row is **SMA%d** at **%s**, a difference of **%s**."
            % (
                money(float(monthly["ending_equity"])),
                int(best["obv_ma"]),
                money(float(best["ending_equity"])),
                money(float(best["ending_equity"] - monthly["ending_equity"])),
            ),
            "- Closest tested cadence to 5 crosses/slot-year is **SMA%d** at **%.2f**, with **%s** matched-add average and **%s** per sleeve signal."
            % (
                int(closest_5["obv_ma"]),
                float(closest_5["avg_crosses_per_slot_year"]),
                money(float(closest_5["matched_add_average"])),
                money(float(closest_5["slot_add_amount"])),
            ),
            "- This is now structurally comparable with the anti-hindsight top-three study, but both schedules are curated v0 and should be audited against provider/SEC holdings before promotion.",
            "",
            "## QQQ / SPY Baselines",
            "",
            "| Rank | Variant | Ending Equity | Net | Return | Max DD | Net/DD |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    baseline = summary[
        summary["variant"].isin(
            [
                "monthly_blind_yearly_ranks_8_10",
                str(best["variant"]),
                "QQQ_monthly_dca",
                "SPY_monthly_dca",
                "QQQ_lump_sum",
                "SPY_lump_sum",
            ]
        )
    ].sort_values("ending_equity", ascending=False)
    for idx, row in baseline.reset_index(drop=True).iterrows():
        lines.append(
            "| %d | %s | %s | %s | %.2f%% | %s | %.2f |"
            % (
                idx + 1,
                row["variant"],
                money(float(row["ending_equity"])),
                money(float(row["net"])),
                float(row["return_on_contributions_pct"]),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )
    lines.extend(
        [
            "",
            "## Annual Schedule",
            "",
            "| Year | SPY Ranks 8-10 | QQQ Ranks 8-10 | DIA Ranks 8-10 |",
            "|---:|---|---|---|",
        ]
    )
    for year, group in schedule.groupby("year"):
        parts = {}
        for index_source, idx_group in group.groupby("index_source"):
            parts[index_source] = " / ".join(idx_group.sort_values("slot_rank")["ticker"].tolist())
        lines.append("| %d | %s | %s | %s |" % (year, parts.get("SPY", ""), parts.get("QQQ", ""), parts.get("DIA", "")))
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Equity leaderboard: [`charts/equity_yearly_ranks_8_10.png`](charts/equity_yearly_ranks_8_10.png)",
            "- Frequency/add sizing: [`charts/frequency_add_yearly_ranks_8_10.png`](charts/frequency_add_yearly_ranks_8_10.png)",
            "",
            "## Outputs",
            "",
            "- `leaderboard.csv`",
            "- `etf_baseline_comparison.csv`",
            "- `daily_equity.csv`",
            "- `transactions.csv`",
            "- `annual_ranks_8_10_schedule.csv`",
        ]
    )
    (OUT_DIR / "YEARLY_RANKS_8_10.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=default_completed_end())
    ap.add_argument("--monthly-amount", type=float, default=1000.0)
    ap.add_argument("--obv-ma-sweep", type=int, nargs="+", default=[20, 50, 100, 150, 200, 252, 504])
    ap.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chart_dir = OUT_DIR / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    schedule = load_schedule(args.schedule, pd.Timestamp(args.start).year, pd.Timestamp(args.end).year)
    tickers = sorted(schedule["ticker"].unique())

    all_daily = []
    all_transactions = []
    summary_rows = []
    plot_curves = {}
    monthly_done = False
    for obv_ma in args.obv_ma_sweep:
        data, dates = load_price_data(tickers, args.start, args.end, obv_ma, args.refresh)
        if not monthly_done:
            monthly_curve, monthly_tx = run_monthly_blind(schedule, data, dates, args.monthly_amount)
            monthly_curve = relabel_frame(monthly_curve, "monthly_blind_yearly_top3", "monthly_blind_yearly_ranks_8_10")
            monthly_tx = relabel_frame(monthly_tx, "monthly_blind_yearly_top3", "monthly_blind_yearly_ranks_8_10")
            summary_rows.append(summarize_curve(monthly_curve, "monthly_blind_yearly_ranks_8_10", math.nan, math.nan, math.nan, math.nan))
            all_daily.append(monthly_curve)
            all_transactions.append(monthly_tx)
            plot_curves["monthly ranks 8-10"] = monthly_curve
            monthly_done = True
        avg_crosses, _total_crosses = count_schedule_crosses(schedule, data, dates)
        obv_curve, obv_tx, matched_avg, slot_add = run_obv(schedule, data, dates, args.monthly_amount, obv_ma, avg_crosses)
        old_variant = "obv_bear_sma%d_yearly_top3" % obv_ma
        new_variant = "obv_bear_sma%d_yearly_ranks_8_10" % obv_ma
        obv_curve = relabel_frame(obv_curve, old_variant, new_variant)
        obv_tx = relabel_frame(obv_tx, old_variant, new_variant)
        summary_rows.append(summarize_curve(obv_curve, new_variant, obv_ma, avg_crosses, matched_avg, slot_add))
        all_daily.append(obv_curve)
        all_transactions.append(obv_tx)
        plot_curves["obv sma%d" % obv_ma] = obv_curve

    total_contributed = float(summary_rows[0]["total_contributed"])
    for ticker in ["QQQ", "SPY"]:
        dca_curve = run_etf_monthly_dca(ticker, args.start, args.end, args.monthly_amount, args.refresh)
        lump_curve = run_etf_lump_sum(ticker, args.start, args.end, total_contributed, args.refresh)
        summary_rows.append(summarize_curve(dca_curve, "%s_monthly_dca" % ticker, math.nan, math.nan, math.nan, math.nan))
        summary_rows.append(summarize_curve(lump_curve, "%s_lump_sum" % ticker, math.nan, math.nan, math.nan, math.nan))
        all_daily.append(dca_curve)
        all_daily.append(lump_curve)
        plot_curves["%s monthly DCA" % ticker] = dca_curve
        plot_curves["%s lump sum" % ticker] = lump_curve

    summary = pd.DataFrame(summary_rows)
    daily = pd.concat(all_daily, ignore_index=True)
    transactions = pd.concat(all_transactions, ignore_index=True) if all_transactions else pd.DataFrame()
    summary.to_csv(OUT_DIR / "leaderboard.csv", index=False)
    summary[
        summary["variant"].isin(
            ["monthly_blind_yearly_ranks_8_10", "QQQ_monthly_dca", "SPY_monthly_dca", "QQQ_lump_sum", "SPY_lump_sum"]
        )
    ].to_csv(OUT_DIR / "etf_baseline_comparison.csv", index=False)
    daily.to_csv(OUT_DIR / "daily_equity.csv", index=False)
    transactions.to_csv(OUT_DIR / "transactions.csv", index=False)
    schedule.to_csv(OUT_DIR / "annual_ranks_8_10_schedule_used.csv", index=False)
    plot_equity(plot_curves, chart_dir / "equity_yearly_ranks_8_10.png")
    plot_frequency(summary, chart_dir / "frequency_add_yearly_ranks_8_10.png")
    write_report(schedule, summary, args.start, args.end, args.monthly_amount, args.obv_ma_sweep)
    print("Wrote %s" % (OUT_DIR / "YEARLY_RANKS_8_10.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
