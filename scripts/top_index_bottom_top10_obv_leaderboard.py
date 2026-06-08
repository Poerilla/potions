#!/usr/bin/env python3
"""Current ranks 8-10 of SPY/QQQ/DIA top-10 OBV DCA diagnostic."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd

from etf_obv_bearish_dca_study import default_completed_end, money
from top_index_obv_leaderboard import (
    load_all_daily,
    plot_equity,
    plot_frequency,
    portfolio_monthly_dca,
    portfolio_obv_dca,
    summarize_curve,
)


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "nq" / "case_studies" / "top_index_bottom_top10_obv_leaderboard"
DEFAULT_START = "2015-06-01"

SLOTS = [
    {"slot": "SPY_8_META", "index": "S&P 500 / SPY", "rank": 8, "ticker": "META", "name": "Meta Platforms"},
    {"slot": "SPY_9_TSLA", "index": "S&P 500 / SPY", "rank": 9, "ticker": "TSLA", "name": "Tesla"},
    {"slot": "SPY_10_MU", "index": "S&P 500 / SPY", "rank": 10, "ticker": "MU", "name": "Micron Technology"},
    {"slot": "QQQ_8_TSLA", "index": "Nasdaq-100 / QQQ", "rank": 8, "ticker": "TSLA", "name": "Tesla"},
    {"slot": "QQQ_9_AVGO", "index": "Nasdaq-100 / QQQ", "rank": 9, "ticker": "AVGO", "name": "Broadcom"},
    {"slot": "QQQ_10_GOOG", "index": "Nasdaq-100 / QQQ", "rank": 10, "ticker": "GOOG", "name": "Alphabet Class C"},
    {"slot": "DIA_8_AXP", "index": "Dow / DIA", "rank": 8, "ticker": "AXP", "name": "American Express"},
    {"slot": "DIA_9_AAPL", "index": "Dow / DIA", "rank": 9, "ticker": "AAPL", "name": "Apple"},
    {"slot": "DIA_10_SHW", "index": "Dow / DIA", "rank": 10, "ticker": "SHW", "name": "Sherwin-Williams"},
]

SOURCES = [
    ("SPY", "https://stockanalysis.com/etf/spy/holdings/", "ranks 8-10 META / TSLA / MU, as of Jun 1, 2026"),
    ("QQQ", "https://stockanalysis.com/etf/qqq/holdings/", "ranks 8-10 TSLA / AVGO / GOOG, as of May 29, 2026"),
    ("DIA", "https://stockanalysis.com/etf/dia/holdings/", "ranks 8-10 AXP / AAPL / SHW, as of May 28, 2026"),
]


def write_report(
    selected_slots: pd.DataFrame,
    summary: pd.DataFrame,
    slot_summary: pd.DataFrame,
    start: str,
    end: str,
    monthly_amount: float,
    obv_mas: list[int],
) -> None:
    monthly = summary[summary["variant"].eq("monthly_blind_bottom_top10")].iloc[0]
    obv = summary[summary["variant"].str.startswith("obv_")].sort_values("ending_equity", ascending=False)
    best = obv.iloc[0]
    closest_5 = obv.assign(gap=(obv["avg_crosses_per_slot_per_year"] - 5.0).abs()).sort_values("gap").iloc[0]
    lines = [
        "# Current Bottom-3-of-Top-10 SPY / QQQ / DIA OBV DCA Diagnostic",
        "",
        "Nine-slot portfolio built from current ranks **8, 9, and 10** of each ETF/index top-10 holding list. Duplicate names are preserved as separate slots. This is a **static current-holdings diagnostic**, not an anti-hindsight historical holdings backtest.",
        "",
        "Sources: %s." % "; ".join("[%s](%s) %s" % item for item in SOURCES),
        "",
        "Window: **%s through %s**. Monthly contribution pool: **%s**. Tested OBV SMA lengths: **%s**."
        % (start, end, money(monthly_amount), ", ".join(str(x) for x in obv_mas)),
        "",
        "Add sizing rule: for each OBV SMA, calculate the average bearish-cross frequency across the nine slots, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot per year`, then buy `MATCHED_ADD_AVERAGE / 9` in each slot when that slot's own OBV bearish cross fires.",
        "",
        "## Selected Slots",
        "",
        "| Slot | Index Source | Rank | Ticker | Name |",
        "|---|---|---:|---|---|",
    ]
    for _, row in selected_slots.iterrows():
        lines.append("| %s | %s | %d | %s | %s |" % (row["slot"], row["index"], int(row["rank"]), row["ticker"], row["name"]))
    lines.extend(
        [
            "",
            "## Leaderboard",
            "",
            "| Rank | Variant | OBV SMA | Avg Crosses / Slot / Yr | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    ranked = pd.concat([summary[summary["variant"].eq("monthly_blind_bottom_top10")], obv], ignore_index=True).sort_values("ending_equity", ascending=False)
    for idx, row in ranked.reset_index(drop=True).iterrows():
        lines.append(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %.2f%% | %s | %.2f | %.1f%% | %s |"
            % (
                idx + 1,
                row["variant"],
                "" if pd.isna(row["obv_ma"]) else str(int(row["obv_ma"])),
                "" if pd.isna(row["avg_crosses_per_slot_per_year"]) else "%.2f" % float(row["avg_crosses_per_slot_per_year"]),
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
            "- Blind monthly bottom-top10 DCA finishes at **%s**. Best OBV timing is **SMA%d** at **%s**, a difference of **%s**."
            % (
                money(float(monthly["ending_equity"])),
                int(best["obv_ma"]),
                money(float(best["ending_equity"])),
                money(float(best["ending_equity"] - monthly["ending_equity"])),
            ),
            "- Closest tested cadence to 5 crosses/slot/year is **SMA%d** at **%.2f**, with **%s** matched-add average and **%s** per-slot signal."
            % (
                int(closest_5["obv_ma"]),
                float(closest_5["avg_crosses_per_slot_per_year"]),
                money(float(closest_5["matched_add_average"])),
                money(float(closest_5["slot_add_amount"])),
            ),
            "- This lower top-10 tranche is more speculative/concentrated than QQQ/SPY itself and should be treated as diagnostic until a yearly ranks-8-to-10 historical schedule is built.",
            "",
            "## Best OBV Slot Breakdown",
            "",
            "| Slot | Ticker | Crosses / Yr | Buys | Avg Buy | Ending Equity | Net | Ending Cash |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    best_slots = slot_summary[slot_summary["variant"].eq(str(best["variant"]))]
    for _, row in best_slots.sort_values(["index", "rank"]).iterrows():
        lines.append(
            "| %s | %s | %.2f | %d | %s | %s | %s | %s |"
            % (
                row["slot"],
                row["ticker"],
                float(row["crosses_per_year"]),
                int(row["buys"]),
                money(float(row["avg_buy_amount"])),
                money(float(row["ending_equity"])),
                money(float(row["net"])),
                money(float(row["ending_cash"])),
            )
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Equity leaderboard: [`charts/equity_leaderboard.png`](charts/equity_leaderboard.png)",
            "- Frequency/add sizing: [`charts/frequency_add_by_ma.png`](charts/frequency_add_by_ma.png)",
            "",
            "## Outputs",
            "",
            "- `leaderboard.csv`",
            "- `daily_equity.csv`",
            "- `slot_summary.csv`",
            "- `selected_slots.csv`",
        ]
    )
    (OUT_DIR / "LEADERBOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=default_completed_end())
    ap.add_argument("--monthly-amount", type=float, default=1000.0)
    ap.add_argument("--obv-ma-sweep", type=int, nargs="+", default=[20, 50, 100, 150, 200, 252, 504])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chart_dir = OUT_DIR / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    slots = [dict(item) for item in SLOTS]
    selected_slots = pd.DataFrame(slots)
    tickers = [slot["ticker"] for slot in slots]
    monthly_curve = None
    monthly_slots = None
    summary_rows = []
    daily_parts = []
    slot_parts = []
    curves_for_plot = {}
    for obv_ma in args.obv_ma_sweep:
        data, dates = load_all_daily(tickers, args.start, args.end, obv_ma, args.refresh)
        if monthly_curve is None:
            monthly_curve, monthly_slots = portfolio_monthly_dca(data, dates, slots, args.monthly_amount)
            monthly_curve = monthly_curve.copy()
            monthly_curve["variant"] = "monthly_blind_bottom_top10"
            monthly_slots = monthly_slots.copy()
            monthly_slots["variant"] = "monthly_blind_bottom_top10"
            summary_rows.append(
                summarize_curve(
                    monthly_curve,
                    "monthly_blind_bottom_top10",
                    math.nan,
                    math.nan,
                    math.nan,
                    math.nan,
                )
            )
            daily_parts.append(monthly_curve)
            slot_parts.append(monthly_slots)
            curves_for_plot["monthly_blind_bottom_top10"] = monthly_curve
        obv_curve, obv_slots, avg_crosses, matched_avg, slot_add = portfolio_obv_dca(
            data,
            dates,
            slots,
            args.monthly_amount,
            obv_ma,
        )
        obv_curve = obv_curve.copy()
        obv_slots = obv_slots.copy()
        old_variant = f"obv_bear_sma{obv_ma}_top9"
        new_variant = f"obv_bear_sma{obv_ma}_bottom_top10"
        obv_curve["variant"] = new_variant
        obv_slots["variant"] = new_variant
        summary_rows.append(
            summarize_curve(
                obv_curve,
                new_variant,
                obv_ma,
                avg_crosses,
                matched_avg,
                slot_add,
            )
        )
        daily_parts.append(obv_curve)
        slot_parts.append(obv_slots)
        curves_for_plot[f"obv_sma{obv_ma}"] = obv_curve

    summary = pd.DataFrame(summary_rows)
    daily = pd.concat(daily_parts, ignore_index=True)
    slot_summary = pd.concat(slot_parts, ignore_index=True)
    summary.to_csv(OUT_DIR / "leaderboard.csv", index=False)
    daily.to_csv(OUT_DIR / "daily_equity.csv", index=False)
    slot_summary.to_csv(OUT_DIR / "slot_summary.csv", index=False)
    selected_slots.to_csv(OUT_DIR / "selected_slots.csv", index=False)
    plot_equity(curves_for_plot, chart_dir / "equity_leaderboard.png")
    plot_frequency(summary.rename(columns={"avg_crosses_per_slot_per_year": "avg_crosses_per_slot_per_year"}), chart_dir / "frequency_add_by_ma.png")
    write_report(selected_slots, summary, slot_summary, args.start, args.end, args.monthly_amount, args.obv_ma_sweep)
    print("Wrote %s" % (OUT_DIR / "LEADERBOARD.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
