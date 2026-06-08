#!/usr/bin/env python3
"""Yearly-rotating top-index-stock OBV DCA backtest.

This is the anti-hindsight version of the top-index OBV study. Each year uses
an explicit beginning-of-year top-three schedule for SPY, QQQ, and DIA slots.
New monthly contributions follow that year's schedule; existing shares are
held, with no annual liquidation, fees, taxes, or cash interest.
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

from etf_obv_bearish_dca_study import add_obv, default_completed_end, max_drawdown, money
from qqq_yearly_orb_study import load_adjusted_daily


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "nq" / "case_studies" / "top_index_obv_yearly_rotation"
DEFAULT_START = "2010-01-01"
DEFAULT_SCHEDULE = OUT_DIR / "annual_top3_schedule.csv"


def first_trading_day_each_month(dates: Iterable[pd.Timestamp]) -> set[pd.Timestamp]:
    work = pd.DataFrame({"date": pd.to_datetime(list(dates))})
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def load_schedule(path: Path, start_year: int, end_year: int) -> pd.DataFrame:
    schedule = pd.read_csv(path)
    required = {"year", "index_source", "slot_rank", "ticker", "name"}
    missing = required.difference(schedule.columns)
    if missing:
        raise ValueError("Schedule missing columns: %s" % ", ".join(sorted(missing)))
    schedule["year"] = pd.to_numeric(schedule["year"], errors="raise").astype(int)
    schedule["slot_rank"] = pd.to_numeric(schedule["slot_rank"], errors="raise").astype(int)
    schedule["ticker"] = schedule["ticker"].str.upper()
    schedule = schedule[(schedule["year"] >= start_year) & (schedule["year"] <= end_year)].copy()
    counts = schedule.groupby("year").size()
    bad = counts[counts.ne(9)]
    if not bad.empty:
        raise ValueError("Each year needs 9 rows; bad years: %s" % bad.to_dict())
    schedule["sleeve"] = schedule["index_source"].astype(str) + "_" + schedule["slot_rank"].astype(str)
    return schedule.sort_values(["year", "index_source", "slot_rank"]).reset_index(drop=True)


def load_price_data(
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
    dates = sorted(set.intersection(*date_sets))
    if not dates:
        raise RuntimeError("No common dates across selected tickers")
    return data, dates


def active_rows(schedule: pd.DataFrame, year: int) -> pd.DataFrame:
    rows = schedule[schedule["year"].eq(year)]
    if rows.empty:
        raise ValueError("No schedule rows for %s" % year)
    return rows


def count_schedule_crosses(schedule: pd.DataFrame, data: dict[str, pd.DataFrame], dates: list[pd.Timestamp]) -> tuple[float, int]:
    total = 0
    slot_years = 0
    by_year_dates = pd.DataFrame({"date": dates})
    by_year_dates["year"] = by_year_dates["date"].dt.year
    for year, group_dates in by_year_dates.groupby("year"):
        rows = active_rows(schedule, int(year))
        year_dates = list(group_dates["date"])
        for _, row in rows.iterrows():
            total += int(pd.to_numeric(data[row["ticker"]].loc[year_dates, "obv_bear_cross"], errors="coerce").fillna(False).sum())
            slot_years += 1
    return total / slot_years if slot_years else 0.0, total


def summarize_curve(
    curve: pd.DataFrame,
    variant: str,
    obv_ma: float,
    avg_crosses_per_slot_year: float,
    matched_add_average: float,
    slot_add_amount: float,
) -> dict:
    total_contributed = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending_equity = float(curve.iloc[-1]["equity"]) if not curve.empty else 0.0
    net = ending_equity - total_contributed
    dd = max_drawdown(curve["equity"]) if not curve.empty else 0.0
    buys = int(pd.to_numeric(curve["buy_count"], errors="coerce").fillna(0).sum()) if not curve.empty else 0
    buy_amount = float(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0).sum()) if not curve.empty else 0.0
    return {
        "variant": variant,
        "obv_ma": obv_ma,
        "avg_crosses_per_slot_year": avg_crosses_per_slot_year,
        "matched_add_average": matched_add_average,
        "slot_add_amount": slot_add_amount,
        "total_contributed": total_contributed,
        "ending_equity": ending_equity,
        "net": net,
        "return_on_contributions_pct": net / total_contributed * 100.0 if total_contributed else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0).mean() * 100.0) if not curve.empty else 0.0,
        "ending_cash": float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0,
        "buys": buys,
        "avg_buy_amount": buy_amount / buys if buys else 0.0,
    }


def run_etf_monthly_dca(
    ticker: str,
    start: str,
    end: str,
    monthly_amount: float,
    refresh: bool,
) -> pd.DataFrame:
    daily = load_adjusted_daily(ticker, start, end, ROOT / "data" / "benchmarks", refresh=refresh).sort_values("date").reset_index(drop=True)
    month_dates = first_trading_day_each_month(pd.to_datetime(daily["date"]).tolist())
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        contribution = 0.0
        buy_amount = 0.0
        if date in month_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            buy_amount = cash
            shares += buy_amount / close
            cash = 0.0
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "%s_monthly_dca" % ticker,
                "obv_ma": math.nan,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_count": 1 if buy_amount > 0 else 0,
                "cash": cash,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def run_etf_lump_sum(
    ticker: str,
    start: str,
    end: str,
    capital: float,
    refresh: bool,
) -> pd.DataFrame:
    daily = load_adjusted_daily(ticker, start, end, ROOT / "data" / "benchmarks", refresh=refresh).sort_values("date").reset_index(drop=True)
    first_close = float(daily.iloc[0]["close"])
    shares = capital / first_close
    rows = []
    for _, bar in daily.iterrows():
        close = float(bar["close"])
        invested = shares * close
        rows.append(
            {
                "date": pd.Timestamp(bar["date"]),
                "variant": "%s_lump_sum" % ticker,
                "obv_ma": math.nan,
                "contribution": 0.0,
                "buy_amount": capital if len(rows) == 0 else 0.0,
                "buy_count": 1 if len(rows) == 0 else 0,
                "cash": 0.0,
                "invested_value": invested,
                "equity": invested,
                "total_contributed": capital,
                "exposure_frac": 1.0,
            }
        )
    return pd.DataFrame(rows)


def run_monthly_blind(
    schedule: pd.DataFrame,
    data: dict[str, pd.DataFrame],
    dates: list[pd.Timestamp],
    monthly_amount: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    month_dates = first_trading_day_each_month(dates)
    sleeve_cash = {sleeve: 0.0 for sleeve in schedule["sleeve"].unique()}
    shares: dict[tuple[str, str], float] = {}
    contributed = 0.0
    rows = []
    transactions = []
    for date in dates:
        year = pd.Timestamp(date).year
        active = active_rows(schedule, year)
        contribution = 0.0
        buy_amount = 0.0
        buy_count = 0
        if date in month_dates:
            sleeve_add = monthly_amount / 9.0
            for _, slot in active.iterrows():
                sleeve = slot["sleeve"]
                ticker = slot["ticker"]
                close = float(data[ticker].loc[date, "close"])
                sleeve_cash[sleeve] += sleeve_add
                contributed += sleeve_add
                contribution += sleeve_add
                this_buy = sleeve_cash[sleeve]
                shares[(sleeve, ticker)] = shares.get((sleeve, ticker), 0.0) + this_buy / close
                sleeve_cash[sleeve] = 0.0
                buy_amount += this_buy
                buy_count += 1
                transactions.append({"date": date, "variant": "monthly_blind_yearly_top3", **slot.to_dict(), "buy_amount": this_buy, "price": close})
        invested = sum(qty * float(data[ticker].loc[date, "close"]) for (sleeve, ticker), qty in shares.items())
        cash = sum(sleeve_cash.values())
        equity = invested + cash
        rows.append(
            {
                "date": date,
                "variant": "monthly_blind_yearly_top3",
                "obv_ma": math.nan,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_count": buy_count,
                "cash": cash,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(transactions)


def run_obv(
    schedule: pd.DataFrame,
    data: dict[str, pd.DataFrame],
    dates: list[pd.Timestamp],
    monthly_amount: float,
    obv_ma: int,
    avg_crosses_per_slot_year: float,
) -> tuple[pd.DataFrame, pd.DataFrame, float, float]:
    month_dates = first_trading_day_each_month(dates)
    matched_add_average = monthly_amount * 12.0 / avg_crosses_per_slot_year if avg_crosses_per_slot_year else math.inf
    slot_add_amount = matched_add_average / 9.0
    sleeve_cash = {sleeve: 0.0 for sleeve in schedule["sleeve"].unique()}
    shares: dict[tuple[str, str], float] = {}
    contributed = 0.0
    rows = []
    transactions = []
    variant = "obv_bear_sma%d_yearly_top3" % obv_ma
    for date in dates:
        year = pd.Timestamp(date).year
        active = active_rows(schedule, year)
        contribution = 0.0
        buy_amount = 0.0
        buy_count = 0
        if date in month_dates:
            sleeve_add = monthly_amount / 9.0
            for _, slot in active.iterrows():
                sleeve_cash[slot["sleeve"]] += sleeve_add
                contributed += sleeve_add
                contribution += sleeve_add
        for _, slot in active.iterrows():
            sleeve = slot["sleeve"]
            ticker = slot["ticker"]
            if bool(data[ticker].loc[date, "obv_bear_cross"]):
                this_buy = min(sleeve_cash[sleeve], slot_add_amount)
                if this_buy > 0:
                    close = float(data[ticker].loc[date, "close"])
                    shares[(sleeve, ticker)] = shares.get((sleeve, ticker), 0.0) + this_buy / close
                    sleeve_cash[sleeve] -= this_buy
                    buy_amount += this_buy
                    buy_count += 1
                    transactions.append({"date": date, "variant": variant, **slot.to_dict(), "buy_amount": this_buy, "price": close})
        invested = sum(qty * float(data[ticker].loc[date, "close"]) for (sleeve, ticker), qty in shares.items())
        cash = sum(sleeve_cash.values())
        equity = invested + cash
        rows.append(
            {
                "date": date,
                "variant": variant,
                "obv_ma": obv_ma,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_count": buy_count,
                "cash": cash,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(transactions), matched_add_average, slot_add_amount


def plot_equity(curves: dict[str, pd.DataFrame], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, curve in curves.items():
        ax.plot(curve["date"], curve["equity"], linewidth=1.4, label=label)
    ax.set_title("Yearly-rotating top-index OBV DCA")
    ax.set_ylabel("Equity ($)")
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
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(obv["obv_ma"], obv["avg_crosses_per_slot_year"], color="#dc2626", marker="o", label="Crosses/slot/year")
    ax.axhline(5.0, color="#6b7280", linestyle=":", linewidth=1.0, label="5/year target")
    ax.set_xlabel("OBV SMA length")
    ax.set_ylabel("Crosses / slot / year")
    ax.grid(True, alpha=0.25)
    ax2 = ax.twinx()
    ax2.plot(obv["obv_ma"], obv["slot_add_amount"], color="#2563eb", marker="s", label="Slot add")
    ax2.set_ylabel("Slot add amount ($)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right")
    ax.set_title("Yearly schedule signal frequency and add sizing")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_report(schedule: pd.DataFrame, summary: pd.DataFrame, start: str, end: str, monthly_amount: float, obv_mas: Iterable[int]) -> None:
    monthly = summary[summary["variant"].eq("monthly_blind_yearly_top3")].iloc[0]
    obv = summary[summary["variant"].str.startswith("obv_")].copy().sort_values("ending_equity", ascending=False)
    best = obv.iloc[0]
    closest_5 = obv.assign(gap=(obv["avg_crosses_per_slot_year"] - 5.0).abs()).sort_values("gap").iloc[0]
    lines = [
        "# Yearly-Rotating Top SPY / QQQ / DIA OBV DCA Backtest",
        "",
        "This is the anti-hindsight version of the top-index-stock OBV DCA study. Each calendar year uses an explicit beginning-of-year top-three schedule for SPY, QQQ, and DIA instead of applying 2026 winners to the past.",
        "",
        "Mechanics: nine persistent sleeves (`SPY_1..3`, `QQQ_1..3`, `DIA_1..3`) receive one ninth of each monthly contribution. At the start of each year the target ticker for new money changes to that year's schedule. Existing shares are held; there is **no annual liquidation**, no taxes, no fees, and no cash interest.",
        "",
        "Schedule status: `annual_top3_schedule.csv` is a curated v0 public-top-holdings schedule. The backtest mechanics are anti-hindsight; the schedule itself should be SEC/fund-document audited before treating the numbers as final.",
        "",
        "Window: **%s through %s**. Monthly contribution pool: **%s**. Tested OBV SMA lengths: **%s**." % (start, end, money(monthly_amount), ", ".join(str(int(x)) for x in obv_mas)),
        "",
        "OBV sizing rule: for each SMA, count bearish crosses across the yearly schedule, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot-year`, then each active sleeve buys `MATCHED_ADD_AVERAGE / 9` when its current ticker's own OBV bearish cross fires.",
        "",
        "## Leaderboard",
        "",
        "| Rank | Variant | OBV SMA | Crosses / Slot-Year | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = pd.concat([summary[summary["variant"].eq("monthly_blind_yearly_top3")], obv], ignore_index=True).sort_values("ending_equity", ascending=False)
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
            "- Best OBV yearly-rotation row is **SMA%d** at **%s**, versus blind monthly yearly-rotation DCA at **%s**. Difference: **%s**."
            % (int(best["obv_ma"]), money(float(best["ending_equity"])), money(float(monthly["ending_equity"])), money(float(best["ending_equity"] - monthly["ending_equity"]))),
            "- Closest tested cadence to 5 crosses/slot-year is **SMA%d** at **%.2f**, with **%s** matched-add average and **%s** per sleeve signal."
            % (int(closest_5["obv_ma"]), float(closest_5["avg_crosses_per_slot_year"]), money(float(closest_5["matched_add_average"])), money(float(closest_5["slot_add_amount"]))),
            "- Compared with the static 2026-holdings leaderboard, the annual schedule removes most of the early-NVDA hindsight edge. This is the right structure for future top-holdings research.",
            "",
            "## Annual Schedule",
            "",
            "| Year | SPY Top 3 | QQQ Top 3 | DIA Top 3 |",
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
            "## QQQ / SPY Baselines",
            "",
            "| Rank | Variant | Ending Equity | Net | Return | Max DD | Net/DD |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    baseline = summary[
        summary["variant"].isin(
            [
                "monthly_blind_yearly_top3",
                "obv_bear_sma20_yearly_top3",
                "obv_bear_sma50_yearly_top3",
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
            "Read: the apples-to-apples monthly-cashflow comparison is almost even with QQQ DCA: yearly-rotating top-three monthly DCA finishes about %s ahead of QQQ monthly DCA, but QQQ has a smaller max drawdown and higher Net/DD. Lump-sum QQQ/SPY are shown separately because they use all %s on day one, which is a different cashflow than `$1,000/month` DCA."
            % (
                money(
                    float(summary[summary["variant"].eq("monthly_blind_yearly_top3")]["ending_equity"].iloc[0])
                    - float(summary[summary["variant"].eq("QQQ_monthly_dca")]["ending_equity"].iloc[0])
                ),
                money(float(summary[summary["variant"].eq("monthly_blind_yearly_top3")]["total_contributed"].iloc[0])),
            ),
            "",
            "## Charts",
            "",
            "- Equity leaderboard: [`charts/equity_yearly_rotation.png`](charts/equity_yearly_rotation.png)",
            "- Frequency/add sizing: [`charts/frequency_add_yearly_rotation.png`](charts/frequency_add_yearly_rotation.png)",
            "",
            "## Outputs",
            "",
            "- `leaderboard.csv`",
            "- `etf_baseline_comparison.csv`",
            "- `daily_equity.csv`",
            "- `transactions.csv`",
            "- `annual_top3_schedule.csv`",
        ]
    )
    (OUT_DIR / "YEARLY_ROTATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    start_year = pd.Timestamp(args.start).year
    end_year = pd.Timestamp(args.end).year
    schedule = load_schedule(args.schedule, start_year, end_year)
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
            summary_rows.append(summarize_curve(monthly_curve, "monthly_blind_yearly_top3", math.nan, math.nan, math.nan, math.nan))
            all_daily.append(monthly_curve)
            all_transactions.append(monthly_tx)
            plot_curves["monthly_blind"] = monthly_curve
            monthly_done = True
        avg_crosses, _total_crosses = count_schedule_crosses(schedule, data, dates)
        obv_curve, obv_tx, matched_avg, slot_add = run_obv(schedule, data, dates, args.monthly_amount, obv_ma, avg_crosses)
        variant = "obv_sma%d" % obv_ma
        summary_rows.append(summarize_curve(obv_curve, "obv_bear_sma%d_yearly_top3" % obv_ma, obv_ma, avg_crosses, matched_avg, slot_add))
        all_daily.append(obv_curve)
        all_transactions.append(obv_tx)
        plot_curves[variant] = obv_curve

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
    summary[summary["variant"].isin(["monthly_blind_yearly_top3", "QQQ_monthly_dca", "SPY_monthly_dca", "QQQ_lump_sum", "SPY_lump_sum"])].to_csv(OUT_DIR / "etf_baseline_comparison.csv", index=False)
    daily.to_csv(OUT_DIR / "daily_equity.csv", index=False)
    transactions.to_csv(OUT_DIR / "transactions.csv", index=False)
    schedule.to_csv(OUT_DIR / "annual_top3_schedule_used.csv", index=False)
    plot_equity(plot_curves, chart_dir / "equity_yearly_rotation.png")
    plot_frequency(summary, chart_dir / "frequency_add_yearly_rotation.png")
    write_report(schedule, summary, args.start, args.end, args.monthly_amount, args.obv_ma_sweep)
    print("Wrote %s" % (OUT_DIR / "YEARLY_ROTATION.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
