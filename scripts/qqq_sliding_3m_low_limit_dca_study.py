#!/usr/bin/env python3
"""QQQ sliding N-month-low limit DCA study."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import first_trading_day_each_month, money, monthly_dca_open, summarize_curve
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_sliding_3m_low_limit_dca_study"
DEFAULT_START = "2000-01-01"


EVENT_MODES = [
    ("all_touches", "Every daily touch of the trailing low"),
    ("new_touch_cluster", "First touch after a non-touch day"),
    ("first_touch_per_month", "First touch per calendar month"),
]


def max_drawdown(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    return float((vals - vals.cummax()).min())


def complete_year_end_dates(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily.copy()
    work["year"] = work["date"].dt.year
    last = work.groupby("year", as_index=False).tail(1).copy()
    complete = last[pd.to_datetime(last["date"]).dt.month.eq(12)]
    return set(pd.to_datetime(complete["date"]))


def build_sliding_low_signals(daily: pd.DataFrame, lookback_months: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = daily.copy().sort_values("date").reset_index(drop=True)
    work["date"] = pd.to_datetime(work["date"])
    first_date = pd.Timestamp(work.iloc[0]["date"])
    prev_touch = False
    touched_months: set[pd.Period] = set()
    touched_quarters: set[pd.Period] = set()
    levels = []
    signals = []

    for _, bar in work.iterrows():
        date = pd.Timestamp(bar["date"])
        level = math.nan
        source_date = pd.NaT
        source_low = math.nan
        eligible = date >= first_date + pd.DateOffset(months=lookback_months)
        touch = False

        if eligible:
            window_start = date - pd.DateOffset(months=lookback_months)
            prior = work[(work["date"] >= window_start) & (work["date"] < date)]
            if not prior.empty:
                low_idx = pd.to_numeric(prior["low"], errors="coerce").idxmin()
                source = prior.loc[low_idx]
                level = float(source["low"])
                source_low = level
                source_date = pd.Timestamp(source["date"])
                touch = float(bar["low"]) <= level

        month = date.to_period("M")
        quarter = date.to_period("Q-DEC")
        mode_hits = {
            "all_touches": touch,
            "new_touch_cluster": touch and not prev_touch,
            "first_touch_per_month": touch and month not in touched_months,
            "first_touch_per_quarter": touch and quarter not in touched_quarters,
        }

        if touch:
            touched_months.add(month)
            touched_quarters.add(quarter)

        levels.append(
            {
                "date": date,
                "eligible": bool(eligible and not math.isnan(level)),
                "lookback_months": lookback_months,
                "window_start": date - pd.DateOffset(months=lookback_months) if eligible else pd.NaT,
                "rolling_low": level,
                "rolling_low_date": source_date,
                "daily_low": float(bar["low"]),
                "daily_open": float(bar["open"]),
                "daily_close": float(bar["close"]),
                "touch": bool(touch),
                "new_touch_cluster": bool(mode_hits["new_touch_cluster"]),
                "first_touch_per_month": bool(mode_hits["first_touch_per_month"]),
                "first_touch_per_quarter": bool(mode_hits["first_touch_per_quarter"]),
            }
        )

        for mode, _ in EVENT_MODES:
            if mode_hits[mode]:
                signals.append(
                    {
                        "date": date,
                        "event_mode": mode,
                        "buy_price": level,
                        "lookback_months": lookback_months,
                        "rolling_low": source_low,
                        "rolling_low_date": source_date,
                        "window_start": date - pd.DateOffset(months=lookback_months),
                        "daily_low": float(bar["low"]),
                        "daily_open": float(bar["open"]),
                        "daily_close": float(bar["close"]),
                    }
                )

        prev_touch = touch

    return pd.DataFrame(signals), pd.DataFrame(levels)


def prior_signal_rate(
    signal_dates: list[pd.Timestamp],
    current_date: pd.Timestamp,
    start_date: pd.Timestamp,
    sizing_mode: str,
    rolling_years: float,
    floor_per_year: float,
) -> float:
    if sizing_mode == "expanding_prior_rate":
        prior = [date for date in signal_dates if date < current_date]
        years = max((current_date - start_date).days / 365.25, 1e-9)
        rate = len(prior) / years
    elif sizing_mode == "rolling_5y_rate":
        window_start = current_date - pd.Timedelta(days=int(round(365.25 * rolling_years)))
        prior = [date for date in signal_dates if window_start <= date < current_date]
        rate = len(prior) / rolling_years
    else:
        raise ValueError("unknown sizing mode %s" % sizing_mode)
    return max(rate, floor_per_year)


def signal_dca(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    event_mode: str,
    lookback_months: int,
    monthly_amount: float,
    sizing_mode: str,
    static_signal_rate: float | None = None,
    rolling_years: float = 5.0,
    floor_per_year: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    signal_rows = signals[signals["event_mode"].eq(event_mode)].copy().sort_values("date")
    signal_rows["date"] = pd.to_datetime(signal_rows["date"])
    signal_dates = [pd.Timestamp(date) for date in signal_rows["date"].tolist()]
    by_date = {pd.Timestamp(row["date"]): row for _, row in signal_rows.iterrows()}
    start_date = pd.Timestamp(daily.iloc[0]["date"])
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    curve_rows = []
    event_rows = []

    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        buy_price = math.nan
        target_add_amount = math.nan
        signal_rate = math.nan
        event_type = ""

        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution

        signal = by_date.get(date)
        if signal is not None:
            if sizing_mode == "static_full_window":
                signal_rate = max(float(static_signal_rate or 0.0), floor_per_year)
            else:
                signal_rate = prior_signal_rate(signal_dates, date, start_date, sizing_mode, rolling_years, floor_per_year)
            target_add_amount = monthly_amount * 12.0 / signal_rate
            buy_amount = min(cash, target_add_amount)
            buy_price = float(signal["buy_price"])
            event_type = "sliding_%dm_low_%s" % (lookback_months, event_mode)
            if buy_amount > 0:
                shares += buy_amount / buy_price
                cash -= buy_amount
                event_rows.append(
                    {
                        "date": date,
                        "event_mode": event_mode,
                        "sizing_mode": sizing_mode,
                        "event_type": event_type,
                        "buy_amount": buy_amount,
                        "buy_price": buy_price,
                        "shares_bought": buy_amount / buy_price,
                        "target_add_amount": target_add_amount,
                        "signal_rate_per_year": signal_rate,
                        "cash_after": cash,
                        "rolling_low": float(signal["rolling_low"]),
                        "rolling_low_date": pd.Timestamp(signal["rolling_low_date"]),
                        "window_start": pd.Timestamp(signal["window_start"]),
                        "daily_low": float(signal["daily_low"]),
                        "daily_open": float(signal["daily_open"]),
                        "daily_close": float(signal["daily_close"]),
                    }
                )

        invested = shares * float(bar["close"])
        equity = cash + invested
        curve_rows.append(
            {
                "date": date,
                "variant": "%s__%s" % (event_mode, sizing_mode),
                "event_mode": event_mode,
                "sizing_mode": sizing_mode,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "buy_price": buy_price,
                "target_add_amount": target_add_amount,
                "signal_rate_per_year": signal_rate,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )

    return pd.DataFrame(curve_rows), pd.DataFrame(event_rows)


def signal_counts_by_year(signals: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    years = sorted(pd.to_datetime(daily["date"]).dt.year.unique())
    rows = []
    sig = signals.copy()
    if not sig.empty:
        sig["year"] = pd.to_datetime(sig["date"]).dt.year
    for year in years:
        for mode, _ in EVENT_MODES:
            count = int(len(sig[sig["year"].eq(year) & sig["event_mode"].eq(mode)])) if not sig.empty else 0
            rows.append({"year": int(year), "event_mode": mode, "signals": count})
    return pd.DataFrame(rows)


def summarize_variant(
    curve: pd.DataFrame,
    event_mode: str,
    sizing_mode: str,
    signal_count: int,
    signal_rate: float,
    monthly_ending_equity: float,
    monthly_amount: float,
) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    buys = int(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0).gt(0).sum()) if not curve.empty else 0
    cash = float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0
    return {
        "variant": "%s__%s" % (event_mode, sizing_mode),
        "event_mode": event_mode,
        "sizing_mode": sizing_mode,
        "signal_count": signal_count,
        "signal_rate_per_year": signal_rate,
        "static_matched_add_amount": monthly_amount * 12.0 / signal_rate if signal_rate else math.inf,
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
        "equity_vs_monthly": ending - monthly_ending_equity,
    }


def summarize_monthly(curve: pd.DataFrame) -> dict:
    summary = summarize_curve(curve, "monthly_dca_open", 0, math.nan, 0.0)
    summary["event_mode"] = "monthly"
    summary["sizing_mode"] = "monthly"
    summary["static_matched_add_amount"] = 1_000.0
    return summary


def plot_equity(curves: pd.DataFrame, monthly: pd.DataFrame, out: Path, lookback_months: int) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(monthly["date"], monthly["equity"], color="#111827", linewidth=1.6, label="monthly_dca_open")
    colors = {
        "all_touches__static_full_window": "#6b7280",
        "new_touch_cluster__static_full_window": "#2563eb",
        "new_touch_cluster__expanding_prior_rate": "#0f766e",
        "first_touch_per_month__static_full_window": "#b45309",
        "first_touch_per_month__expanding_prior_rate": "#7c3aed",
    }
    for variant, group in curves.groupby("variant", sort=False):
        if variant not in colors:
            continue
        ax.plot(group["date"], group["equity"], color=colors[variant], linewidth=1.2, label=variant)
    ax.set_title("QQQ sliding %d-month-low limit DCA vs monthly DCA" % lookback_months)
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


def plot_signal_counts(counts: pd.DataFrame, out: Path, lookback_months: int) -> None:
    pivot = counts.pivot(index="year", columns="event_mode", values="signals").fillna(0.0)
    fig, ax = plt.subplots(figsize=(14, 5))
    x = range(len(pivot.index))
    width = 0.25
    colors = {"all_touches": "#6b7280", "new_touch_cluster": "#2563eb", "first_touch_per_month": "#b45309"}
    modes = [mode for mode, _ in EVENT_MODES]
    for idx, mode in enumerate(modes):
        offset = (idx - 1) * width
        vals = pivot[mode].tolist() if mode in pivot else [0.0] * len(pivot)
        ax.bar([v + offset for v in x], vals, width=width, color=colors.get(mode), label=mode)
    ax.set_xticks(list(x))
    ax.set_xticklabels([str(int(y)) for y in pivot.index], rotation=75)
    ax.set_title("QQQ sliding %d-month-low signal counts by year" % lookback_months)
    ax.set_ylabel("Signals")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_recent_levels(daily: pd.DataFrame, levels: pd.DataFrame, signals: pd.DataFrame, out: Path, lookback_months: int) -> None:
    start = pd.Timestamp(daily.iloc[-1]["date"]) - pd.DateOffset(years=3)
    d = daily[pd.to_datetime(daily["date"]) >= start].copy()
    l = levels[pd.to_datetime(levels["date"]) >= start].copy()
    s = signals[(signals["event_mode"].eq("new_touch_cluster")) & (pd.to_datetime(signals["date"]) >= start)].copy()
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(d["date"], d["close"], color="#111827", linewidth=1.2, label="QQQ close")
    ax.plot(l["date"], l["rolling_low"], color="#2563eb", linewidth=1.0, alpha=0.8, label="prior %d-month low" % lookback_months)
    if not s.empty:
        ax.scatter(s["date"], s["buy_price"], color="#dc2626", s=28, label="new touch cluster fills", zorder=5)
    ax.set_title("QQQ recent prior %d-month-low levels" % lookback_months)
    ax.set_ylabel("Adjusted QQQ")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def write_report(
    out_dir: Path,
    daily: pd.DataFrame,
    monthly_summary: dict,
    summary: pd.DataFrame,
    counts: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    lookback_months: int,
) -> None:
    ranked = summary.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    main = summary[
        summary["event_mode"].eq("new_touch_cluster") & summary["sizing_mode"].eq("static_full_window")
    ].iloc[0]
    main_causal = summary[
        summary["event_mode"].eq("new_touch_cluster") & summary["sizing_mode"].eq("expanding_prior_rate")
    ].iloc[0]
    best_row = ranked.iloc[0]
    frequency_rows = []
    for mode, label in EVENT_MODES:
        mode_signals = signals[signals["event_mode"].eq(mode)]
        by_year = counts[counts["event_mode"].eq(mode)]
        complete = by_year[by_year["year"].lt(int(daily["date"].max().year))]
        zero_years = int((complete["signals"].eq(0)).sum()) if not complete.empty else 0
        rate = float(len(mode_signals)) / max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
        frequency_rows.append((mode, label, len(mode_signals), rate, 12.0 * monthly_amount / rate if rate else math.inf, zero_years))

    recent = signals[signals["event_mode"].eq("new_touch_cluster")].tail(20).copy()
    lines = [
        "# QQQ Sliding %d-Month-Low Limit DCA Study" % lookback_months,
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`.",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "## Rule",
        "",
        "- Each trading day calculates the adjusted low of the **prior %d calendar months**, excluding the current day." % lookback_months,
        "- A buy limit is considered filled if the current daily low touches that trailing level. Fill price is the trailing low level, which is conservative on gap-down days for a buy limit.",
        "- `all_touches` buys every daily touch; `new_touch_cluster` buys only the first touch after a non-touch day; `first_touch_per_month` buys the first touch per calendar month.",
        "- Cashflow comparison: contribute **%s/month**. Monthly DCA buys first trading day open; signal variants hold cash and buy only on rolling-low signals." % money(monthly_amount),
        "- Matched-add sizing uses **12 months of DCA budget / expected fills per year**, capped by available cash. `static_full_window` is diagnostic; `expanding_prior_rate` uses only prior signal frequency.",
        "- No year-end catch-up, no fees, taxes, slippage, or cash interest.",
        "",
        "## Fill Frequency",
        "",
        "| Event Mode | Definition | Signals | Signals / Yr | Static Matched Add | Zero-Fill Complete Years |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for mode, label, count, rate, add, zero_years in frequency_rows:
        lines.append("| %s | %s | %d | %.2f | %s | %d |" % (mode, label, count, rate, money(add), zero_years))

    lines.extend(
        [
            "",
            "## Performance Leaderboard",
            "",
            "| Rank | Event Mode | Sizing | Signals/Yr | Buys | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure | Ending Cash |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        lines.append(
            "| %d | %s | %s | %.2f | %d | %s | %.1f%% | %s | %s | %s | %.2f | %.1f%% | %s |"
            % (
                rank,
                row["event_mode"],
                row["sizing_mode"],
                float(row["signal_rate_per_year"]),
                int(row["buys"]),
                money(float(row["avg_buy_amount"])),
                float(row["deployed_contributions_pct"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                float(row["avg_exposure_pct"]),
                money(float(row["ending_cash"])),
            )
        )

    lines.extend(
        [
            "",
            "Monthly DCA baseline: **%s ending equity**, **%s net**, **%s max DD**, **%.2f Net/DD**."
            % (
                money(float(monthly_summary["ending_equity"])),
                money(float(monthly_summary["net"])),
                money(float(monthly_summary["max_dd"])),
                float(monthly_summary["net_over_dd"]),
            ),
            "",
            "## Main Read",
            "",
            "- Best tested row is **%s / %s**, ending at **%s**, **%s** versus monthly DCA, with **%.1f%%** deployed."
            % (
                best_row["event_mode"],
                best_row["sizing_mode"],
                money(float(best_row["ending_equity"])),
                money(float(best_row["equity_vs_monthly"])),
                float(best_row["deployed_contributions_pct"]),
            ),
            "- The cleanest cadence is **new_touch_cluster**: **%d** fills, **%.2f/year**, static matched add **%s**."
            % (int(main["signal_count"]), float(main["signal_rate_per_year"]), money(float(main["static_matched_add_amount"]))),
            "- Static matched `new_touch_cluster` ends at **%s**, **%s** versus monthly DCA, with **%.1f%%** deployed."
            % (money(float(main["ending_equity"])), money(float(main["equity_vs_monthly"])), float(main["deployed_contributions_pct"])),
            "- Causal expanding-rate `new_touch_cluster` ends at **%s**, **%s** versus monthly DCA, with **%.1f%%** deployed."
            % (money(float(main_causal["ending_equity"])), money(float(main_causal["equity_vs_monthly"])), float(main_causal["deployed_contributions_pct"])),
            "",
            "## Recent New-Touch Events",
            "",
            "| Date | Buy Price | Rolling Low Date | Window Start | Daily Low | Daily Close |",
            "|---|---:|---|---|---:|---:|",
        ]
    )
    for _, row in recent.iterrows():
        lines.append(
            "| %s | %.2f | %s | %s | %.2f | %.2f |"
            % (
                pd.Timestamp(row["date"]).date().isoformat(),
                float(row["buy_price"]),
                pd.Timestamp(row["rolling_low_date"]).date().isoformat(),
                pd.Timestamp(row["window_start"]).date().isoformat(),
                float(row["daily_low"]),
                float(row["daily_close"]),
            )
        )

    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Equity comparison: [`charts/equity_vs_monthly.png`](charts/equity_vs_monthly.png)",
            "- Signal counts by year: [`charts/signal_counts_by_year.png`](charts/signal_counts_by_year.png)",
            "- Recent trailing-low levels: [`charts/recent_levels.png`](charts/recent_levels.png)",
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `signals.csv`",
            "- `levels.csv`",
            "- `counts_by_year.csv`",
            "- `curves.csv`",
            "- `events.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QQQ sliding N-month-low limit DCA study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--lookback-months", type=int, default=3)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh).sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])
    monthly = monthly_dca_open(daily, args.monthly_amount)
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)
    monthly_ending = float(monthly_summary["ending_equity"])

    signals, levels = build_sliding_low_signals(daily, args.lookback_months)
    counts = signal_counts_by_year(signals, daily)
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)

    curve_parts = []
    event_parts = []
    summary_rows = []
    for event_mode, _ in EVENT_MODES:
        signal_count = int(len(signals[signals["event_mode"].eq(event_mode)]))
        signal_rate = signal_count / years
        for sizing_mode in ["static_full_window", "expanding_prior_rate", "rolling_5y_rate"]:
            curve, events = signal_dca(
                daily,
                signals,
                event_mode,
                args.lookback_months,
                args.monthly_amount,
                sizing_mode,
                static_signal_rate=signal_rate,
            )
            curve_parts.append(curve)
            event_parts.append(events)
            summary_rows.append(summarize_variant(curve, event_mode, sizing_mode, signal_count, signal_rate, monthly_ending, args.monthly_amount))

    curves = pd.concat(curve_parts, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    summary = pd.DataFrame(summary_rows)

    summary.to_csv(out_dir / "summary.csv", index=False)
    signals.to_csv(out_dir / "signals.csv", index=False)
    levels.to_csv(out_dir / "levels.csv", index=False)
    counts.to_csv(out_dir / "counts_by_year.csv", index=False)
    curves.to_csv(out_dir / "curves.csv", index=False)
    events.to_csv(out_dir / "events.csv", index=False)

    plot_equity(curves, monthly, out_dir / "charts" / "equity_vs_monthly.png", args.lookback_months)
    plot_signal_counts(counts, out_dir / "charts" / "signal_counts_by_year.png", args.lookback_months)
    plot_recent_levels(daily, levels, signals, out_dir / "charts" / "recent_levels.png", args.lookback_months)
    write_report(out_dir, daily, monthly_summary, summary, counts, signals, args.monthly_amount, args.lookback_months)
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
