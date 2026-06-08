#!/usr/bin/env python3
"""Top-index-stock OBV bearish-cross DCA leaderboard.

Builds a nine-slot portfolio from the top three current holdings of SPY,
QQQ, and DIA. Duplicate names are intentionally preserved as separate slots
because the user asked for top three from each index and a /9 allocation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from etf_obv_bearish_dca_study import add_obv, default_completed_end, max_drawdown, money, pct
from qqq_yearly_orb_study import load_adjusted_daily


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "nq" / "case_studies" / "top_index_obv_bearish_dca_leaderboard"
DEFAULT_START = "2015-06-01"

DEFAULT_SLOTS = [
    {"slot": "SPY_1_NVDA", "index": "S&P 500 / SPY", "rank": 1, "ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"slot": "SPY_2_AAPL", "index": "S&P 500 / SPY", "rank": 2, "ticker": "AAPL", "name": "Apple Inc."},
    {"slot": "SPY_3_MSFT", "index": "S&P 500 / SPY", "rank": 3, "ticker": "MSFT", "name": "Microsoft Corporation"},
    {"slot": "QQQ_1_NVDA", "index": "Nasdaq-100 / QQQ", "rank": 1, "ticker": "NVDA", "name": "NVIDIA Corporation"},
    {"slot": "QQQ_2_AAPL", "index": "Nasdaq-100 / QQQ", "rank": 2, "ticker": "AAPL", "name": "Apple Inc."},
    {"slot": "QQQ_3_MSFT", "index": "Nasdaq-100 / QQQ", "rank": 3, "ticker": "MSFT", "name": "Microsoft Corporation"},
    {"slot": "DIA_1_GS", "index": "Dow / DIA", "rank": 1, "ticker": "GS", "name": "Goldman Sachs Group"},
    {"slot": "DIA_2_CAT", "index": "Dow / DIA", "rank": 2, "ticker": "CAT", "name": "Caterpillar Inc."},
    {"slot": "DIA_3_MSFT", "index": "Dow / DIA", "rank": 3, "ticker": "MSFT", "name": "Microsoft Corporation"},
]

HOLDING_SOURCES = [
    ("SPY", "https://stockanalysis.com/etf/spy/holdings/"),
    ("QQQ", "https://stockanalysis.com/etf/qqq/"),
    ("DIA", "https://stockanalysis.com/etf/dia/holdings/"),
]


def first_trading_day_each_month_from_dates(dates: Iterable[pd.Timestamp]) -> set[pd.Timestamp]:
    work = pd.DataFrame({"date": pd.to_datetime(list(dates))})
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def load_all_daily(
    tickers: Iterable[str],
    start: str,
    end: str,
    obv_ma: int,
    refresh: bool,
) -> tuple[dict[str, pd.DataFrame], list[pd.Timestamp]]:
    data = {}
    date_sets = []
    for ticker in sorted(set(tickers)):
        daily = load_adjusted_daily(ticker, start, end, ROOT / "data" / "benchmarks", refresh=refresh)
        daily = add_obv(daily, obv_ma).set_index("date", drop=False)
        data[ticker] = daily
        date_sets.append(set(pd.to_datetime(daily["date"])))
    common_dates = sorted(set.intersection(*date_sets))
    if not common_dates:
        raise RuntimeError("No common dates across selected tickers")
    return data, common_dates


def summarize_curve(
    curve: pd.DataFrame,
    variant: str,
    obv_ma: int | float,
    avg_crosses_per_year: float,
    matched_add_average: float,
    slot_add_amount: float,
) -> dict:
    end_equity = float(curve.iloc[-1]["equity"]) if not curve.empty else 0.0
    total_contributed = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    net = end_equity - total_contributed
    dd = max_drawdown(curve["equity"]) if not curve.empty else 0.0
    buys = int(pd.to_numeric(curve["buy_count"], errors="coerce").fillna(0.0).sum()) if not curve.empty else 0
    total_buy_amount = float(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0).sum()) if not curve.empty else 0.0
    return {
        "variant": variant,
        "obv_ma": obv_ma,
        "start": pd.Timestamp(curve.iloc[0]["date"]).date().isoformat() if not curve.empty else "",
        "end": pd.Timestamp(curve.iloc[-1]["date"]).date().isoformat() if not curve.empty else "",
        "avg_crosses_per_slot_per_year": avg_crosses_per_year,
        "matched_add_average": matched_add_average,
        "slot_add_amount": slot_add_amount,
        "total_contributed": total_contributed,
        "ending_equity": end_equity,
        "net": net,
        "return_on_contributions_pct": net / total_contributed * 100.0 if total_contributed else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "ending_cash": float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0,
        "ending_invested_value": float(curve.iloc[-1]["invested_value"]) if not curve.empty else 0.0,
        "ending_cash_pct_of_contrib": float(curve.iloc[-1]["cash"]) / total_contributed * 100.0 if total_contributed else math.nan,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0) if not curve.empty else 0.0,
        "buys": buys,
        "avg_buy_amount": total_buy_amount / buys if buys else 0.0,
    }


def portfolio_monthly_dca(
    data: dict[str, pd.DataFrame],
    dates: list[pd.Timestamp],
    slots: list[dict],
    monthly_amount: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    month_dates = first_trading_day_each_month_from_dates(dates)
    slot_amount = monthly_amount / len(slots)
    cash = {slot["slot"]: 0.0 for slot in slots}
    shares = {slot["slot"]: 0.0 for slot in slots}
    contributed = {slot["slot"]: 0.0 for slot in slots}
    buy_counts = {slot["slot"]: 0 for slot in slots}
    buy_amounts = {slot["slot"]: 0.0 for slot in slots}
    rows = []
    for date in dates:
        contribution = 0.0
        buy_amount = 0.0
        buy_count = 0
        if date in month_dates:
            for slot in slots:
                slot_id = slot["slot"]
                ticker = slot["ticker"]
                close = float(data[ticker].loc[date, "close"])
                cash[slot_id] += slot_amount
                contributed[slot_id] += slot_amount
                contribution += slot_amount
                this_buy = cash[slot_id]
                shares[slot_id] += this_buy / close
                cash[slot_id] = 0.0
                buy_amount += this_buy
                buy_count += 1
                buy_counts[slot_id] += 1
                buy_amounts[slot_id] += this_buy
        invested = sum(shares[slot["slot"]] * float(data[slot["ticker"]].loc[date, "close"]) for slot in slots)
        cash_total = sum(cash.values())
        equity = invested + cash_total
        rows.append(
            {
                "date": date,
                "variant": "monthly_blind_top9",
                "obv_ma": math.nan,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_count": buy_count,
                "cash": cash_total,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": sum(contributed.values()),
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    slot_rows = []
    end_date = dates[-1]
    for slot in slots:
        slot_id = slot["slot"]
        ticker = slot["ticker"]
        invested = shares[slot_id] * float(data[ticker].loc[end_date, "close"])
        equity = invested + cash[slot_id]
        slot_rows.append(
            {
                **slot,
                "variant": "monthly_blind_top9",
                "obv_ma": math.nan,
                "bear_crosses": math.nan,
                "crosses_per_year": math.nan,
                "buys": buy_counts[slot_id],
                "avg_buy_amount": buy_amounts[slot_id] / buy_counts[slot_id] if buy_counts[slot_id] else 0.0,
                "total_contributed": contributed[slot_id],
                "ending_equity": equity,
                "net": equity - contributed[slot_id],
                "ending_cash": cash[slot_id],
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(slot_rows)


def portfolio_obv_dca(
    data: dict[str, pd.DataFrame],
    dates: list[pd.Timestamp],
    slots: list[dict],
    monthly_amount: float,
    obv_ma: int,
) -> tuple[pd.DataFrame, pd.DataFrame, float, float, float]:
    month_dates = first_trading_day_each_month_from_dates(dates)
    slot_monthly = monthly_amount / len(slots)
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    cross_counts = {
        slot["slot"]: int(pd.to_numeric(data[slot["ticker"]].loc[dates, "obv_bear_cross"], errors="coerce").fillna(False).sum())
        for slot in slots
    }
    crosses_per_year = {slot_id: count / years for slot_id, count in cross_counts.items()}
    avg_crosses_per_year = sum(crosses_per_year.values()) / len(slots)
    matched_add_average = monthly_amount * 12.0 / avg_crosses_per_year if avg_crosses_per_year else math.inf
    slot_add_amount = matched_add_average / len(slots)
    cash = {slot["slot"]: 0.0 for slot in slots}
    shares = {slot["slot"]: 0.0 for slot in slots}
    contributed = {slot["slot"]: 0.0 for slot in slots}
    buy_counts = {slot["slot"]: 0 for slot in slots}
    buy_amounts = {slot["slot"]: 0.0 for slot in slots}
    rows = []
    for date in dates:
        contribution = 0.0
        buy_amount = 0.0
        buy_count = 0
        if date in month_dates:
            for slot in slots:
                slot_id = slot["slot"]
                cash[slot_id] += slot_monthly
                contributed[slot_id] += slot_monthly
                contribution += slot_monthly
        for slot in slots:
            ticker = slot["ticker"]
            slot_id = slot["slot"]
            if bool(data[ticker].loc[date, "obv_bear_cross"]):
                this_buy = min(cash[slot_id], slot_add_amount)
                if this_buy > 0:
                    close = float(data[ticker].loc[date, "close"])
                    shares[slot_id] += this_buy / close
                    cash[slot_id] -= this_buy
                    buy_amount += this_buy
                    buy_count += 1
                    buy_counts[slot_id] += 1
                    buy_amounts[slot_id] += this_buy
        invested = sum(shares[slot["slot"]] * float(data[slot["ticker"]].loc[date, "close"]) for slot in slots)
        cash_total = sum(cash.values())
        equity = invested + cash_total
        rows.append(
            {
                "date": date,
                "variant": f"obv_bear_sma{obv_ma}_top9",
                "obv_ma": obv_ma,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_count": buy_count,
                "cash": cash_total,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": sum(contributed.values()),
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    slot_rows = []
    end_date = dates[-1]
    for slot in slots:
        slot_id = slot["slot"]
        ticker = slot["ticker"]
        invested = shares[slot_id] * float(data[ticker].loc[end_date, "close"])
        equity = invested + cash[slot_id]
        slot_rows.append(
            {
                **slot,
                "variant": f"obv_bear_sma{obv_ma}_top9",
                "obv_ma": obv_ma,
                "bear_crosses": cross_counts[slot_id],
                "crosses_per_year": crosses_per_year[slot_id],
                "buys": buy_counts[slot_id],
                "avg_buy_amount": buy_amounts[slot_id] / buy_counts[slot_id] if buy_counts[slot_id] else 0.0,
                "total_contributed": contributed[slot_id],
                "ending_equity": equity,
                "net": equity - contributed[slot_id],
                "ending_cash": cash[slot_id],
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(slot_rows), avg_crosses_per_year, matched_add_average, slot_add_amount


def plot_equity(curves: dict[str, pd.DataFrame], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, curve in curves.items():
        ax.plot(curve["date"], curve["equity"], label=label, linewidth=1.5)
    ax.set_title("Top-index 9-slot OBV DCA leaderboard")
    ax.set_ylabel("Portfolio equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_frequency(summary: pd.DataFrame, out_path: Path) -> None:
    obv = summary[summary["variant"].str.startswith("obv_")].sort_values("obv_ma")
    fig, ax_freq = plt.subplots(figsize=(12, 6))
    ax_freq.plot(obv["obv_ma"], obv["avg_crosses_per_slot_per_year"], marker="o", color="#dc2626", label="Avg crosses/slot/year")
    ax_freq.axhline(5.0, color="#6b7280", linestyle=":", linewidth=1.0, label="5/year target")
    ax_freq.set_xlabel("OBV SMA length")
    ax_freq.set_ylabel("Average crosses / slot / year")
    ax_freq.grid(True, alpha=0.25)
    ax_add = ax_freq.twinx()
    ax_add.plot(obv["obv_ma"], obv["slot_add_amount"], marker="s", color="#2563eb", label="Add per slot signal")
    ax_add.set_ylabel("Slot add amount ($)")
    h1, l1 = ax_freq.get_legend_handles_labels()
    h2, l2 = ax_add.get_legend_handles_labels()
    ax_freq.legend(h1 + h2, l1 + l2, loc="upper right")
    ax_freq.set_title("Portfolio signal cadence and add size")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_report(
    selected_slots: pd.DataFrame,
    summary: pd.DataFrame,
    slot_summary: pd.DataFrame,
    start: str,
    end: str,
    monthly_amount: float,
    obv_mas: Iterable[int],
) -> None:
    monthly = summary[summary["variant"].eq("monthly_blind_top9")].iloc[0]
    obv = summary[summary["variant"].str.startswith("obv_")].copy().sort_values("ending_equity", ascending=False)
    best = obv.iloc[0]
    closest_5 = obv.assign(gap=(obv["avg_crosses_per_slot_per_year"] - 5.0).abs()).sort_values("gap").iloc[0]
    lines = [
        "# Top SPY / QQQ / DIA Holdings OBV DCA Leaderboard",
        "",
        "Nine-slot portfolio built from the current top three holdings of SPY/S&P 500, QQQ/Nasdaq-100, and DIA/Dow. Duplicate names are preserved as separate slots, so MSFT has three sleeves and NVDA/AAPL have two sleeves. Each slot receives one ninth of the monthly contribution and buys only when its own ticker's OBV crosses bearish.",
        "",
        "Holdings source links: %s." % ", ".join("[%s](%s)" % (label, url) for label, url in HOLDING_SOURCES),
        "",
        "Window: **%s through %s**. Monthly contribution pool: **%s**. Tested OBV SMA lengths: **%s**."
        % (start, end, money(monthly_amount), ", ".join(str(int(x)) for x in obv_mas)),
        "",
        "Add sizing rule: for each OBV SMA, calculate the average bearish-cross frequency across the nine slots, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot per year`, then buy `MATCHED_ADD_AVERAGE / 9` in each slot when that slot's own OBV bearish cross fires. This targets the same annual deployment budget as `$1,000/month` blind DCA.",
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
    ranked = pd.concat([summary[summary["variant"].eq("monthly_blind_top9")], obv], ignore_index=True)
    ranked = ranked.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    for idx, row in ranked.iterrows():
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
            "- Best OBV portfolio row is **SMA%d** at **%s**, versus blind monthly top-nine DCA at **%s**. Difference: **%s**."
            % (
                int(best["obv_ma"]),
                money(float(best["ending_equity"])),
                money(float(monthly["ending_equity"])),
                money(float(best["ending_equity"] - monthly["ending_equity"])),
            ),
            "- Closest tested cadence to 5 crosses/slot/year is **SMA%d** at **%.2f crosses/slot/year**, with **%s** matched-add average and **%s** per slot signal."
            % (
                int(closest_5["obv_ma"]),
                float(closest_5["avg_crosses_per_slot_per_year"]),
                money(float(closest_5["matched_add_average"])),
                money(float(closest_5["slot_add_amount"])),
            ),
            "- Because the top SPY and QQQ holdings currently overlap, this is not a diversified nine-company study; it is a nine-slot index-overlap study. That concentration is intentional for this pass.",
            "",
            "## Best OBV Slot Breakdown",
            "",
            "| Slot | Ticker | Crosses / Yr | Buys | Avg Buy | Ending Equity | Net | Ending Cash |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    best_slots = slot_summary[slot_summary["variant"].eq(str(best["variant"]))].copy()
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

    slots = [dict(item) for item in DEFAULT_SLOTS]
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
            summary_rows.append(
                summarize_curve(
                    monthly_curve,
                    "monthly_blind_top9",
                    math.nan,
                    math.nan,
                    math.nan,
                    math.nan,
                )
            )
            daily_parts.append(monthly_curve)
            slot_parts.append(monthly_slots)
            curves_for_plot["monthly_blind_top9"] = monthly_curve
        obv_curve, obv_slots, avg_crosses, matched_avg, slot_add = portfolio_obv_dca(
            data,
            dates,
            slots,
            args.monthly_amount,
            obv_ma,
        )
        summary_rows.append(
            summarize_curve(
                obv_curve,
                f"obv_bear_sma{obv_ma}_top9",
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
    plot_frequency(summary, chart_dir / "frequency_add_by_ma.png")
    write_report(selected_slots, summary, slot_summary, args.start, args.end, args.monthly_amount, args.obv_ma_sweep)
    print("Wrote %s" % (OUT_DIR / "LEADERBOARD.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
