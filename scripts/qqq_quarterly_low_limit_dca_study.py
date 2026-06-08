#!/usr/bin/env python3
"""QQQ previous-quarter-low limit DCA study."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import ROOT, first_trading_day_each_month, money, monthly_dca_open, summarize_curve
from qqq_yearly_orb_study import default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_quarterly_low_limit_dca_study"
DEFAULT_START = "2000-01-01"


def quarter_label(period: pd.Period) -> str:
    return "%dQ%d" % (period.year, period.quarter)


def build_quarters(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy().sort_values("date")
    work["quarter"] = work["date"].dt.to_period("Q-DEC")
    rows = []
    for quarter, group in work.groupby("quarter", sort=True):
        group = group.sort_values("date")
        low_idx = pd.to_numeric(group["low"], errors="coerce").idxmin()
        low_row = group.loc[low_idx]
        rows.append(
            {
                "quarter": quarter_label(quarter),
                "period": str(quarter),
                "year": int(quarter.year),
                "quarter_num": int(quarter.quarter),
                "start_date": pd.Timestamp(group.iloc[0]["date"]),
                "end_date": pd.Timestamp(group.iloc[-1]["date"]),
                "open": float(group.iloc[0]["open"]),
                "high": float(pd.to_numeric(group["high"], errors="coerce").max()),
                "low": float(low_row["low"]),
                "low_date": pd.Timestamp(low_row["date"]),
                "close": float(group.iloc[-1]["close"]),
                "volume": float(pd.to_numeric(group["volume"], errors="coerce").sum()),
                "trading_days": int(len(group)),
            }
        )
    quarters = pd.DataFrame(rows)
    if quarters.empty:
        return quarters
    quarters["prev_quarter"] = quarters["quarter"].shift(1)
    quarters["prev_quarter_low"] = quarters["low"].shift(1)
    quarters["prev_quarter_low_date"] = quarters["low_date"].shift(1)
    return quarters


def complete_year_end_dates(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily.copy()
    work["year"] = work["date"].dt.year
    last = work.groupby("year", as_index=False).tail(1).copy()
    complete = last[pd.to_datetime(last["date"]).dt.month.eq(12)]
    return set(pd.to_datetime(complete["date"]))


def simulate_prev_quarter_low_limit(
    daily: pd.DataFrame,
    quarters: pd.DataFrame,
    monthly_amount: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    complete_year_ends = complete_year_end_dates(daily)
    quarter_by_date = {}
    for _, row in quarters.dropna(subset=["prev_quarter_low"]).iterrows():
        dates = daily[(daily["date"] >= row["start_date"]) & (daily["date"] <= row["end_date"])]["date"]
        for date in dates:
            quarter_by_date[pd.Timestamp(date)] = row

    filled_quarters: set[str] = set()
    quarterly_fill_years: set[int] = set()
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    events = []

    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        buy_price = math.nan
        event_type = ""
        trigger_level = math.nan
        trigger_quarter = ""
        prev_quarter = ""

        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution

        qrow = quarter_by_date.get(date)
        if qrow is not None:
            trigger_quarter = str(qrow["quarter"])
            prev_quarter = str(qrow["prev_quarter"])
            trigger_level = float(qrow["prev_quarter_low"])
            if trigger_quarter not in filled_quarters and float(bar["low"]) <= trigger_level and cash > 0:
                buy_amount = cash
                buy_price = trigger_level
                shares += buy_amount / buy_price
                cash = 0.0
                event_type = "prev_quarter_low_limit"
                filled_quarters.add(trigger_quarter)
                quarterly_fill_years.add(int(date.year))

        if not event_type and date in complete_year_ends and int(date.year) not in quarterly_fill_years and cash > 0:
            buy_amount = cash
            buy_price = float(bar["close"])
            shares += buy_amount / buy_price
            cash = 0.0
            event_type = "year_end_no_quarter_fill"

        if event_type:
            events.append(
                {
                    "date": date,
                    "event_type": event_type,
                    "buy_amount": buy_amount,
                    "buy_price": buy_price,
                    "shares_bought": buy_amount / buy_price if buy_price else math.nan,
                    "cash_after": cash,
                    "trigger_quarter": trigger_quarter,
                    "prev_quarter": prev_quarter,
                    "prev_quarter_low": trigger_level,
                    "daily_low": float(bar["low"]),
                    "daily_open": float(bar["open"]),
                    "daily_close": float(bar["close"]),
                }
            )

        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "prev_quarter_low_limit_with_year_end_fallback",
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_price": buy_price,
                "event_type": event_type,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(events)


def max_drawdown(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    peak = vals.cummax()
    return float((vals - peak).min())


def summarize_strategy(curve: pd.DataFrame, monthly_summary: dict, events: pd.DataFrame, quarters: pd.DataFrame) -> dict:
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(curve.iloc[-1]["equity"]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(curve["equity"])
    quarterly_events = events[events["event_type"].eq("prev_quarter_low_limit")] if not events.empty else pd.DataFrame()
    fallback_events = events[events["event_type"].eq("year_end_no_quarter_fill")] if not events.empty else pd.DataFrame()
    eligible_quarters = quarters.dropna(subset=["prev_quarter_low"]).copy()
    complete_years = sorted(pd.to_datetime(curve.loc[curve["date"].dt.month.eq(12), "date"]).dt.year.unique())
    return {
        "variant": "prev_quarter_low_limit_with_year_end_fallback",
        "total_contributed": total,
        "ending_equity": ending,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "ending_cash": float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0,
        "deployed_contributions_pct": (total - float(curve.iloc[-1]["cash"])) / total * 100.0 if total else math.nan,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0),
        "equity_vs_monthly": ending - float(monthly_summary["ending_equity"]),
        "eligible_quarters": int(len(eligible_quarters)),
        "quarterly_limit_fills": int(len(quarterly_events)),
        "quarterly_fill_rate_pct": len(quarterly_events) / len(eligible_quarters) * 100.0 if len(eligible_quarters) else math.nan,
        "year_end_fallbacks": int(len(fallback_events)),
        "complete_years": int(len(complete_years)),
        "avg_quarterly_fills_per_year": len(quarterly_events) / len(complete_years) if complete_years else math.nan,
        "avg_buy_amount": float(pd.to_numeric(events["buy_amount"], errors="coerce").mean()) if not events.empty else 0.0,
        "avg_quarterly_buy_amount": float(pd.to_numeric(quarterly_events["buy_amount"], errors="coerce").mean()) if not quarterly_events.empty else 0.0,
        "avg_fallback_buy_amount": float(pd.to_numeric(fallback_events["buy_amount"], errors="coerce").mean()) if not fallback_events.empty else 0.0,
    }


def build_counts(events: pd.DataFrame, quarters: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    years = sorted(pd.to_datetime(daily["date"]).dt.year.unique())
    rows = []
    events = events.copy()
    if not events.empty:
        events["year"] = pd.to_datetime(events["date"]).dt.year
    for year in years:
        qfills = events[events["year"].eq(year) & events["event_type"].eq("prev_quarter_low_limit")] if not events.empty else pd.DataFrame()
        fallbacks = events[events["year"].eq(year) & events["event_type"].eq("year_end_no_quarter_fill")] if not events.empty else pd.DataFrame()
        eligible = quarters[quarters["year"].eq(year) & quarters["prev_quarter_low"].notna()]
        rows.append(
            {
                "year": int(year),
                "eligible_quarters": int(len(eligible)),
                "quarterly_limit_fills": int(len(qfills)),
                "quarterly_fill_rate_pct": len(qfills) / len(eligible) * 100.0 if len(eligible) else math.nan,
                "year_end_fallbacks": int(len(fallbacks)),
                "total_buys": int(len(qfills) + len(fallbacks)),
                "buy_amount": float(pd.to_numeric(pd.concat([qfills, fallbacks], ignore_index=True)["buy_amount"], errors="coerce").sum()) if len(qfills) + len(fallbacks) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def plot_equity(curve: pd.DataFrame, monthly: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(monthly["date"], monthly["equity"], color="#111827", linewidth=1.5, label="monthly_dca_open")
    ax.plot(curve["date"], curve["equity"], color="#0f766e", linewidth=1.2, label="prev_quarter_low_limit")
    ax.set_title("QQQ previous-quarter-low limit DCA vs monthly DCA")
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


def plot_counts(counts: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 5))
    labels = counts["year"].astype(str).tolist()
    ax.bar(labels, counts["quarterly_limit_fills"], color="#0f766e", label="quarterly low fills")
    ax.bar(labels, counts["year_end_fallbacks"], bottom=counts["quarterly_limit_fills"], color="#2563eb", label="year-end fallback")
    ax.set_title("QQQ previous-quarter-low fills by year")
    ax.set_ylabel("Buy events")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.tick_params(axis="x", labelrotation=75)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_quarter_fill_rates(quarters: pd.DataFrame, events: pd.DataFrame, out: Path) -> None:
    eligible = quarters.dropna(subset=["prev_quarter_low"]).copy()
    fills = set(events.loc[events["event_type"].eq("prev_quarter_low_limit"), "trigger_quarter"].astype(str)) if not events.empty else set()
    rows = []
    for qnum, group in eligible.groupby("quarter_num"):
        fill_count = int(group["quarter"].astype(str).isin(fills).sum())
        rows.append({"quarter": "Q%d" % qnum, "eligible": len(group), "fills": fill_count, "fill_rate_pct": fill_count / len(group) * 100.0 if len(group) else 0.0})
    rates = pd.DataFrame(rows).sort_values("quarter")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(rates["quarter"], rates["fill_rate_pct"], color="#7c3aed")
    for _, row in rates.iterrows():
        ax.text(row["quarter"], row["fill_rate_pct"] + 1.0, "%d/%d" % (row["fills"], row["eligible"]), ha="center", va="bottom", fontsize=9)
    ax.set_title("Previous-quarter-low retest rate by calendar quarter")
    ax.set_ylabel("Fill rate (%)")
    ax.set_ylim(0, max(100.0, float(rates["fill_rate_pct"].max()) + 12.0 if not rates.empty else 100.0))
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def write_report(
    out_dir: Path,
    daily: pd.DataFrame,
    monthly_summary: dict,
    strategy_summary: dict,
    quarters: pd.DataFrame,
    events: pd.DataFrame,
    counts: pd.DataFrame,
    monthly_amount: float,
) -> None:
    qfills = events[events["event_type"].eq("prev_quarter_low_limit")] if not events.empty else pd.DataFrame()
    fallbacks = events[events["event_type"].eq("year_end_no_quarter_fill")] if not events.empty else pd.DataFrame()
    recent = events.tail(20).copy()
    lines = [
        "# QQQ Previous-Quarter-Low Limit DCA Study",
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`.",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "## Rule",
        "",
        "- Each completed quarter defines a low from adjusted daily lows.",
        "- In the next quarter, place one resting buy limit at the **previous quarter's low**. Q1 uses the prior year's Q4 low when available.",
        "- If any daily low touches that level, buy all available cash at the limit price. One fill maximum per quarter.",
        "- Cashflow comparison: contribute **%s/month**. Monthly DCA buys first trading day open; this variant holds cash until a quarterly low retest or fallback." % money(monthly_amount),
        "- If a calendar year has **no** quarterly-low fill, buy all available cash on the final trading day of that year at the close.",
        "- No fees, taxes, cash interest, or slippage.",
        "",
        "## Result",
        "",
        "| Variant | End Equity | Net | Vs Monthly DCA | Max DD | Net/DD | Deployed | Avg Exposure | Quarterly Fills | Fill Rate | Year-End Fallbacks |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| Previous-quarter-low limit | %s | %s | %s | %s | %.2f | %.1f%% | %.1f%% | %d / %d | %.1f%% | %d |"
        % (
            money(strategy_summary["ending_equity"]),
            money(strategy_summary["net"]),
            money(strategy_summary["equity_vs_monthly"]),
            money(strategy_summary["max_dd"]),
            strategy_summary["net_over_dd"],
            strategy_summary["deployed_contributions_pct"],
            strategy_summary["avg_exposure_pct"],
            strategy_summary["quarterly_limit_fills"],
            strategy_summary["eligible_quarters"],
            strategy_summary["quarterly_fill_rate_pct"],
            strategy_summary["year_end_fallbacks"],
        ),
        "",
        "Monthly DCA baseline: **%s ending equity**, **%s net**, **%s max DD**, **%.2f Net/DD**."
        % (
            money(float(monthly_summary["ending_equity"])),
            money(float(monthly_summary["net"])),
            money(float(monthly_summary["max_dd"])),
            float(monthly_summary["net_over_dd"]),
        ),
        "",
        "## Fill Cadence",
        "",
        "- Eligible quarters: **%d**." % strategy_summary["eligible_quarters"],
        "- Previous-quarter-low fills: **%d**, or **%.1f%%** of eligible quarters." % (strategy_summary["quarterly_limit_fills"], strategy_summary["quarterly_fill_rate_pct"]),
        "- Expected cadence: **%.2f quarterly-low fills/year** over complete years." % strategy_summary["avg_quarterly_fills_per_year"],
        "- Years with no quarterly-low fill and a year-end fallback: **%d**." % strategy_summary["year_end_fallbacks"],
        "- Average quarterly-low buy: **%s**; average fallback buy: **%s**."
        % (money(strategy_summary["avg_quarterly_buy_amount"]), money(strategy_summary["avg_fallback_buy_amount"])),
        "",
        "## By Year",
        "",
        "| Year | Eligible Quarters | Quarterly Fills | Fill Rate | Fallbacks | Total Buys | Buy Amount |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in counts.iterrows():
        lines.append(
            "| %d | %d | %d | %.1f%% | %d | %d | %s |"
            % (
                int(row["year"]),
                int(row["eligible_quarters"]),
                int(row["quarterly_limit_fills"]),
                float(row["quarterly_fill_rate_pct"]) if not pd.isna(row["quarterly_fill_rate_pct"]) else 0.0,
                int(row["year_end_fallbacks"]),
                int(row["total_buys"]),
                money(float(row["buy_amount"])),
            )
        )
    lines.extend(
        [
            "",
            "## Recent Events",
            "",
            "| Date | Event | Buy Amount | Price | Quarter | Prior Quarter | Prior Q Low | Daily Low |",
            "|---|---|---:|---:|---|---|---:|---:|",
        ]
    )
    for _, row in recent.iterrows():
        lines.append(
            "| %s | %s | %s | %.2f | %s | %s | %s | %.2f |"
            % (
                pd.Timestamp(row["date"]).date().isoformat(),
                row["event_type"],
                money(float(row["buy_amount"])),
                float(row["buy_price"]),
                row["trigger_quarter"] if isinstance(row["trigger_quarter"], str) and row["trigger_quarter"] else "-",
                row["prev_quarter"] if isinstance(row["prev_quarter"], str) and row["prev_quarter"] else "-",
                "%.2f" % float(row["prev_quarter_low"]) if not pd.isna(row["prev_quarter_low"]) else "-",
                float(row["daily_low"]),
            )
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Equity vs monthly DCA: [`charts/equity_vs_monthly.png`](charts/equity_vs_monthly.png)",
            "- Buy events by year: [`charts/fills_by_year.png`](charts/fills_by_year.png)",
            "- Fill rate by calendar quarter: [`charts/fill_rate_by_quarter.png`](charts/fill_rate_by_quarter.png)",
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `events.csv`",
            "- `counts_by_year.csv`",
            "- `quarters.csv`",
            "- `curves.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QQQ previous-quarter-low limit DCA study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh).sort_values("date").reset_index(drop=True)
    quarters = build_quarters(daily)
    monthly = monthly_dca_open(daily, args.monthly_amount)
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)
    curve, events = simulate_prev_quarter_low_limit(daily, quarters, args.monthly_amount)
    strategy_summary = summarize_strategy(curve, monthly_summary, events, quarters)
    counts = build_counts(events, quarters, daily)

    pd.DataFrame([strategy_summary]).to_csv(out_dir / "summary.csv", index=False)
    events.to_csv(out_dir / "events.csv", index=False)
    counts.to_csv(out_dir / "counts_by_year.csv", index=False)
    quarters.drop(columns=["period"], errors="ignore").to_csv(out_dir / "quarters.csv", index=False)
    curve.to_csv(out_dir / "curves.csv", index=False)

    plot_equity(curve, monthly, out_dir / "charts" / "equity_vs_monthly.png")
    plot_counts(counts, out_dir / "charts" / "fills_by_year.png")
    plot_quarter_fill_rates(quarters, events, out_dir / "charts" / "fill_rate_by_quarter.png")
    write_report(out_dir, daily, monthly_summary, strategy_summary, quarters, events, counts, args.monthly_amount)
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
