#!/usr/bin/env python3
"""QQQ weekly-pivot market-structure DCA study.

Tests two bullish weekly swing patterns:

1. low -> high -> lower low
2. low -> high -> lower low -> higher high

Weekly pivots are confirmed only after the right-side weekly bars complete.
Signal buys happen at the next available daily open after the weekly signal is
known, while the cashflow baseline remains monthly DCA on daily bars.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import (
    ROOT,
    Pivot,
    build_confirmed_pivots,
    counts_by_year,
    first_trading_day_each_month,
    money,
    monthly_dca_open,
    plot_signal_counts,
    prior_signal_rate,
    summarize_curve,
)
from qqq_yearly_orb_study import default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_market_structure_weekly_pivot_dca_study"
DEFAULT_START = "2000-01-01"


def weekly_ohlcv(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy().sort_values("date")
    work["week"] = work["date"].dt.to_period("W-FRI")
    weekly = (
        work.groupby("week", as_index=False)
        .agg(
            date=("date", "max"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    return weekly


def next_daily_open_after(daily: pd.DataFrame, after_date: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    dates = pd.to_datetime(daily["date"]).reset_index(drop=True)
    idx = int(dates.searchsorted(pd.Timestamp(after_date), side="right"))
    if idx >= len(daily):
        return None
    row = daily.iloc[idx]
    return pd.Timestamp(row["date"]), float(row["open"])


def year_end_sweep_dates(weekly: pd.DataFrame) -> dict[pd.Timestamp, float]:
    """Return final December weekly bar date -> weekly high."""
    dec = weekly[pd.to_datetime(weekly["date"]).dt.month.eq(12)].copy()
    if dec.empty:
        return {}
    dec["year"] = pd.to_datetime(dec["date"]).dt.year
    final_weeks = dec.sort_values("date").groupby("year", as_index=False).tail(1)
    return {pd.Timestamp(row["date"]): float(row["high"]) for _, row in final_weeks.iterrows()}


def pivot_rows(pivots: list[Pivot], pivot_bars: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "kind": pivot.kind,
                "pivot_idx": pivot.pivot_idx,
                "confirm_idx": pivot.confirm_idx,
                "pivot_date": pivot.pivot_date.date().isoformat(),
                "confirm_date": pivot.confirm_date.date().isoformat(),
                "value": pivot.value,
                "pivot_bars": pivot_bars,
            }
            for pivot in pivots
        ]
    )


def detect_lhll_weekly(daily: pd.DataFrame, weekly: pd.DataFrame, pivot_bars: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    pivots = build_confirmed_pivots(weekly, pivot_bars, pivot_bars)
    l1: Pivot | None = None
    h1: Pivot | None = None
    signals = []

    for pivot in pivots:
        if pivot.kind == "low":
            if l1 is None:
                l1 = pivot
                h1 = None
                continue
            if h1 is None:
                if pivot.value < l1.value:
                    l1 = pivot
                continue
            if pivot.pivot_idx > h1.pivot_idx:
                if pivot.value < l1.value:
                    buy = next_daily_open_after(daily, pivot.confirm_date)
                    if buy is not None:
                        buy_date, buy_price = buy
                        signals.append(
                            {
                                "signal_index": len(signals) + 1,
                                "pattern": "low_high_lower_low",
                                "pivot_left": pivot_bars,
                                "pivot_right": pivot_bars,
                                "l1_pivot_date": l1.pivot_date.date().isoformat(),
                                "l1_confirm_date": l1.confirm_date.date().isoformat(),
                                "l1_value": l1.value,
                                "h1_pivot_date": h1.pivot_date.date().isoformat(),
                                "h1_confirm_date": h1.confirm_date.date().isoformat(),
                                "h1_value": h1.value,
                                "l2_pivot_date": pivot.pivot_date.date().isoformat(),
                                "l2_confirm_date": pivot.confirm_date.date().isoformat(),
                                "l2_value": pivot.value,
                                "signal_date": pivot.confirm_date.date().isoformat(),
                                "buy_date": buy_date.date().isoformat(),
                                "buy_price": buy_price,
                                "weeks_l1_to_h1": int(h1.pivot_idx - l1.pivot_idx),
                                "weeks_h1_to_l2": int(pivot.pivot_idx - h1.pivot_idx),
                                "weeks_l2_to_signal": 0,
                                "l2_below_l1_pct": (pivot.value / l1.value - 1.0) * 100.0,
                                "break_above_h1_pct": math.nan,
                                "break_mode": "",
                            }
                        )
                    l1 = pivot
                    h1 = None
                else:
                    l1 = pivot
                    h1 = None
        elif l1 is not None and pivot.pivot_idx > l1.pivot_idx:
            if h1 is None or pivot.value > h1.value:
                h1 = pivot

    return pd.DataFrame(signals), pivot_rows(pivots, pivot_bars)


def detect_lhllhh_weekly(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    pivot_bars: int,
    break_mode: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pivots = build_confirmed_pivots(weekly, pivot_bars, pivot_bars)
    by_confirm: dict[int, list[Pivot]] = {}
    for pivot in pivots:
        by_confirm.setdefault(pivot.confirm_idx, []).append(pivot)

    l1: Pivot | None = None
    h1: Pivot | None = None
    l2: Pivot | None = None
    armed = False
    signals = []
    closes = pd.to_numeric(weekly["close"], errors="coerce").tolist()
    highs = pd.to_numeric(weekly["high"], errors="coerce").tolist()
    dates = pd.to_datetime(weekly["date"]).tolist()

    for idx in range(len(weekly)):
        for pivot in by_confirm.get(idx, []):
            if armed:
                if pivot.kind == "low" and l2 is not None and pivot.value < l2.value:
                    l2 = pivot
                continue

            if pivot.kind == "low":
                if l1 is None or h1 is None:
                    l1 = pivot
                    h1 = None
                    continue
                if pivot.pivot_idx > h1.pivot_idx:
                    if pivot.value < l1.value:
                        l2 = pivot
                        armed = True
                    else:
                        l1 = pivot
                        h1 = None
            elif l1 is not None and pivot.pivot_idx > l1.pivot_idx:
                if h1 is None or pivot.value > h1.value:
                    h1 = pivot

        if armed and l1 is not None and h1 is not None and l2 is not None and idx > l2.confirm_idx:
            break_value = float(closes[idx]) if break_mode == "close" else float(highs[idx])
            if break_value > h1.value:
                signal_date = pd.Timestamp(dates[idx])
                buy = next_daily_open_after(daily, signal_date)
                if buy is not None:
                    buy_date, buy_price = buy
                    signals.append(
                        {
                            "signal_index": len(signals) + 1,
                            "pattern": "low_high_lower_low_higher_high",
                            "pivot_left": pivot_bars,
                            "pivot_right": pivot_bars,
                            "l1_pivot_date": l1.pivot_date.date().isoformat(),
                            "l1_confirm_date": l1.confirm_date.date().isoformat(),
                            "l1_value": l1.value,
                            "h1_pivot_date": h1.pivot_date.date().isoformat(),
                            "h1_confirm_date": h1.confirm_date.date().isoformat(),
                            "h1_value": h1.value,
                            "l2_pivot_date": l2.pivot_date.date().isoformat(),
                            "l2_confirm_date": l2.confirm_date.date().isoformat(),
                            "l2_value": l2.value,
                            "signal_date": signal_date.date().isoformat(),
                            "buy_date": buy_date.date().isoformat(),
                            "buy_price": buy_price,
                            "weeks_l1_to_h1": int(h1.pivot_idx - l1.pivot_idx),
                            "weeks_h1_to_l2": int(l2.pivot_idx - h1.pivot_idx),
                            "weeks_l2_to_signal": int(idx - l2.pivot_idx),
                            "l2_below_l1_pct": (l2.value / l1.value - 1.0) * 100.0,
                            "break_above_h1_pct": (break_value / h1.value - 1.0) * 100.0,
                            "break_mode": break_mode,
                        }
                    )
                l1 = None
                h1 = None
                l2 = None
                armed = False

    return pd.DataFrame(signals), pivot_rows(pivots, pivot_bars)


def signal_dca_with_year_end_sweep(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    sizing_mode: str,
    static_signal_rate: float | None = None,
    rolling_years: float = 5.0,
    floor_per_year: float = 1.0,
) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    signal_set = set(pd.to_datetime(signals["buy_date"])) if not signals.empty and "buy_date" in signals.columns else set()
    signal_dates = sorted(signal_set)
    sweeps = year_end_sweep_dates(weekly)
    start_date = pd.Timestamp(daily.iloc[0]["date"])
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        signal_buy_amount = 0.0
        sweep_buy_amount = 0.0
        target_add_amount = math.nan
        signal_rate = math.nan
        sweep_price = math.nan
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        if date in signal_set:
            if sizing_mode == "all_cash_lump":
                signal_buy_amount = cash
            else:
                if sizing_mode == "static_full_window":
                    signal_rate = max(float(static_signal_rate or 0.0), floor_per_year)
                else:
                    signal_rate = prior_signal_rate(signal_dates, date, start_date, sizing_mode, rolling_years, floor_per_year)
                target_add_amount = monthly_amount * 12.0 / signal_rate
                signal_buy_amount = min(cash, target_add_amount)
            if signal_buy_amount > 0:
                shares += signal_buy_amount / float(bar["open"])
                cash -= signal_buy_amount
        if date in sweeps and cash > 0:
            sweep_price = sweeps[date]
            sweep_buy_amount = cash
            shares += sweep_buy_amount / sweep_price
            cash = 0.0
        buy_amount = signal_buy_amount + sweep_buy_amount
        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "signal_all_cash_lump" if sizing_mode == "all_cash_lump" else "signal_%s" % sizing_mode if sizing_mode != "rolling" else "signal_rolling_%gy" % rolling_years,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "signal_buy_amount": signal_buy_amount,
                "sweep_buy_amount": sweep_buy_amount,
                "target_add_amount": target_add_amount,
                "signal_rate_per_year": signal_rate,
                "year_end_sweep_price": sweep_price,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_curve_with_sweeps(curve: pd.DataFrame, variant: str, signal_count: int, signal_rate: float, monthly_ending_equity: float) -> dict:
    out = summarize_curve(curve, variant, signal_count, signal_rate, monthly_ending_equity)
    out["year_end_sweeps"] = int(pd.to_numeric(curve.get("sweep_buy_amount", 0.0), errors="coerce").fillna(0.0).gt(0).sum())
    out["signal_buys"] = int(pd.to_numeric(curve.get("signal_buy_amount", 0.0), errors="coerce").fillna(0.0).gt(0).sum())
    return out


def empty_signal_frame(pattern: str, pivot_bars: int, break_mode: str = "") -> pd.DataFrame:
    columns = [
        "signal_index",
        "pattern",
        "pivot_left",
        "pivot_right",
        "l1_pivot_date",
        "l1_confirm_date",
        "l1_value",
        "h1_pivot_date",
        "h1_confirm_date",
        "h1_value",
        "l2_pivot_date",
        "l2_confirm_date",
        "l2_value",
        "signal_date",
        "buy_date",
        "buy_price",
        "weeks_l1_to_h1",
        "weeks_h1_to_l2",
        "weeks_l2_to_signal",
        "l2_below_l1_pct",
        "break_above_h1_pct",
        "break_mode",
        "pivot_bars",
    ]
    out = pd.DataFrame(columns=columns)
    out["pattern"] = pattern
    out["pivot_bars"] = pivot_bars
    out["break_mode"] = break_mode
    return out


def run_variant(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly_amount: float,
    pattern: str,
    pivot_bars: int,
    break_mode: str,
    monthly_summary: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if pattern == "low_high_lower_low":
        signals, pivots = detect_lhll_weekly(daily, weekly, pivot_bars)
    elif pattern == "low_high_lower_low_higher_high":
        signals, pivots = detect_lhllhh_weekly(daily, weekly, pivot_bars, break_mode)
    else:
        raise ValueError("Unknown pattern %s" % pattern)

    if signals.empty:
        signals = empty_signal_frame(pattern, pivot_bars, break_mode if pattern.endswith("higher_high") else "")
    else:
        signals["pivot_bars"] = pivot_bars
    pivots["pattern"] = pattern
    pivots["break_mode"] = break_mode if pattern.endswith("higher_high") else ""

    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    signal_count = int(len(signals))
    signal_rate = signal_count / years
    static = signal_dca_with_year_end_sweep(daily, weekly, signals, monthly_amount, "static_full_window", static_signal_rate=signal_rate)
    expanding = signal_dca_with_year_end_sweep(daily, weekly, signals, monthly_amount, "expanding")
    rolling_5 = signal_dca_with_year_end_sweep(daily, weekly, signals, monthly_amount, "rolling", rolling_years=5.0)
    all_cash = signal_dca_with_year_end_sweep(daily, weekly, signals, monthly_amount, "all_cash_lump")
    curves = pd.concat([static, expanding, rolling_5, all_cash], ignore_index=True)
    summaries = pd.DataFrame(
        [
            summarize_curve_with_sweeps(static, "signal_static_full_window", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve_with_sweeps(expanding, "signal_expanding_prior_rate", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve_with_sweeps(rolling_5, "signal_rolling_5y_rate", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve_with_sweeps(all_cash, "signal_all_cash_lump", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
        ]
    )
    for df in [signals, curves, summaries]:
        df["pattern"] = pattern
        df["pivot_bars"] = pivot_bars
        df["break_mode"] = break_mode if pattern.endswith("higher_high") else ""
    return signals, pivots, curves, summaries


def plot_equity_local(curves: pd.DataFrame, monthly: pd.DataFrame, out: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(monthly["date"], monthly["equity"], color="#111827", linewidth=1.55, label="monthly_dca_open")
    colors = {
        "signal_static_full_window": "#2563eb",
        "signal_expanding_prior_rate": "#0f766e",
        "signal_rolling_5y_rate": "#b45309",
        "signal_all_cash_lump": "#7c3aed",
    }
    for variant, group in curves.groupby("variant", sort=False):
        ax.plot(group["date"], group["equity"], color=colors.get(variant), linewidth=1.15, label=variant)
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


def plot_top_causal(summary: pd.DataFrame, monthly_summary: dict, out: Path) -> None:
    causal = summary[summary["variant"].eq("signal_expanding_prior_rate")].copy()
    causal["label"] = causal["pattern"].str.replace("low_high_", "L-H-", regex=False).str.replace("_", "-") + " / " + causal["pivot_bars"].astype(str) + "w"
    causal = causal.sort_values("ending_equity", ascending=True).tail(15)
    fig, ax = plt.subplots(figsize=(13, 7))
    colors = ["#0f766e" if value >= 0 else "#dc2626" for value in causal["equity_vs_monthly"]]
    ax.barh(causal["label"], causal["equity_vs_monthly"], color=colors)
    ax.axvline(0, color="#111827", linewidth=0.9)
    ax.set_title("Weekly-pivot causal signal DCA vs monthly DCA")
    ax.set_xlabel("Ending equity minus monthly DCA ($)")
    ax.grid(True, axis="x", alpha=0.25)
    ax.text(
        0.99,
        0.03,
        "Monthly baseline: %s" % money(float(monthly_summary["ending_equity"])),
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="#374151",
    )
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def display_pattern(pattern: str) -> str:
    if pattern == "low_high_lower_low":
        return "L-H-LL"
    if pattern == "low_high_lower_low_higher_high":
        return "L-H-LL-HH"
    return pattern


def write_report(
    out_dir: Path,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly_summary: dict,
    summary: pd.DataFrame,
    counts: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
) -> None:
    ranked = summary.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    causal = summary[summary["variant"].eq("signal_expanding_prior_rate")].sort_values("ending_equity", ascending=False)
    best_causal = causal.iloc[0]
    best_any = ranked.iloc[0]
    best_by_pattern = (
        causal.sort_values(["pattern", "ending_equity"], ascending=[True, False])
        .groupby("pattern", as_index=False)
        .head(1)
        .sort_values("ending_equity", ascending=False)
    )

    lines = [
        "# QQQ Weekly-Pivot Market-Structure DCA Study",
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`; weekly candles are resampled from the same adjusted daily bars.",
        "Window: **%s through %s** (%d completed/partial weekly bars)." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat(), len(weekly)),
        "",
        "## Rule",
        "",
        "- Weekly pivots use `N` completed weekly bars on the left and `N` completed weekly bars on the right.",
        "- Pattern 1: **L-H-LL** = confirmed weekly low -> confirmed weekly high -> confirmed lower weekly low.",
        "- Pattern 2: **L-H-LL-HH** = L-H-LL, then first later completed weekly bar that breaks above the prior weekly high.",
        "- Signal buys happen at the **next available daily open** after the weekly signal is known.",
        "- Year-end catch-up: if signal buys have not spent the accumulated annual budget, remaining cash is invested on the final December weekly bar at that week's **high**.",
        "- Cashflow comparison: contribute **%s/month**. Monthly DCA buys the first trading day open; signal variants hold cash and buy on weekly-swing signals." % money(monthly_amount),
        "- `signal_expanding_prior_rate` is the causal backwards-trace sizing row: each signal uses only prior signal frequency to estimate `12 months of DCA / signals per year`.",
        "- `signal_all_cash_lump` buys all accumulated cash at each signal; it is a timing diagnostic, not the causal frequency-matched row.",
        "",
        "## Leaderboard",
        "",
        "| Rank | Pattern | Weekly Pivot Bars | Variant | Signals | Signals / Yr | Signal Buys | Dec Sweeps | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        lines.append(
            "| %d | %s | %d | %s | %d | %.2f | %d | %d | %s | %.1f%% | %s | %s | %s | %.2f | %.1f%% |"
            % (
                rank,
                display_pattern(row["pattern"]),
                int(row["pivot_bars"]),
                row["variant"],
                int(row["signal_count"]),
                float(row["signal_rate_per_year"]),
                int(row["signal_buys"]),
                int(row["year_end_sweeps"]),
                money(float(row["avg_buy_amount"])),
                float(row["deployed_contributions_pct"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                float(row["avg_exposure_pct"]),
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
            "## Read",
            "",
            "- Best causal weekly-swing row: **%s / %d-week pivots / %s**, with **%d signals** (%.2f/year), **%d signal buys** and **%d December sweeps**, ending at **%s** (**%s** vs monthly DCA)."
            % (
                display_pattern(best_causal["pattern"]),
                int(best_causal["pivot_bars"]),
                best_causal["variant"],
                int(best_causal["signal_count"]),
                float(best_causal["signal_rate_per_year"]),
                int(best_causal["signal_buys"]),
                int(best_causal["year_end_sweeps"]),
                money(float(best_causal["ending_equity"])),
                money(float(best_causal["equity_vs_monthly"])),
            ),
            "- Best any-mode row: **%s / %d-week pivots / %s**, with **%d signal buys** and **%d December sweeps**, ending at **%s** (**%s** vs monthly DCA)."
            % (
                display_pattern(best_any["pattern"]),
                int(best_any["pivot_bars"]),
                best_any["variant"],
                int(best_any["signal_buys"]),
                int(best_any["year_end_sweeps"]),
                money(float(best_any["ending_equity"])),
                money(float(best_any["equity_vs_monthly"])),
            ),
            "- The December sweep removes the worst idle-cash drag, but it also means some performance is fallback deployment rather than signal timing.",
            "",
            "## Best Causal By Pattern",
            "",
            "| Pattern | Weekly Pivot Bars | Signals | Signals / Yr | Signal Buys | Dec Sweeps | End Equity | Vs Monthly | Deployed | Max DD | Net/DD |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in best_by_pattern.iterrows():
        lines.append(
            "| %s | %d | %d | %.2f | %d | %d | %s | %s | %.1f%% | %s | %.2f |"
            % (
                display_pattern(row["pattern"]),
                int(row["pivot_bars"]),
                int(row["signal_count"]),
                float(row["signal_rate_per_year"]),
                int(row["signal_buys"]),
                int(row["year_end_sweeps"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
                float(row["deployed_contributions_pct"]),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )

    lines.extend(
        [
            "",
            "## Recent Signals",
            "",
            "| Pattern | Pivot Bars | Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 |",
            "|---|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    sample = signals[signals["pattern"].eq(best_causal["pattern"]) & signals["pivot_bars"].eq(int(best_causal["pivot_bars"]))].tail(15)
    for _, row in sample.iterrows():
        lines.append(
            "| %s | %d | %s | %.2f | %.2f | %.2f | %.2f | %.2f%% |"
            % (
                display_pattern(row["pattern"]),
                int(row["pivot_bars"]),
                row["buy_date"],
                float(row["l1_value"]),
                float(row["h1_value"]),
                float(row["l2_value"]),
                float(row["buy_price"]),
                float(row["l2_below_l1_pct"]),
            )
        )

    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Top causal rows vs monthly DCA: [`charts/top_causal_vs_monthly.png`](charts/top_causal_vs_monthly.png)",
            "- Best weekly row yearly chart pack: [`charts/yearly_lhll_3w/INDEX.md`](charts/yearly_lhll_3w/INDEX.md)",
            "- Best L-H-LL equity comparison: [`charts/best_lhll_equity.png`](charts/best_lhll_equity.png)",
            "- Best L-H-LL signal counts: [`charts/best_lhll_counts_by_year.png`](charts/best_lhll_counts_by_year.png)",
            "- Best L-H-LL-HH equity comparison: [`charts/best_lhllhh_equity.png`](charts/best_lhllhh_equity.png)",
            "- Best L-H-LL-HH signal counts: [`charts/best_lhllhh_counts_by_year.png`](charts/best_lhllhh_counts_by_year.png)",
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `signals.csv`",
            "- `pivots.csv`",
            "- `weekly_bars.csv`",
            "- `curves.csv`",
            "- `counts_by_year.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QQQ weekly-pivot market-structure DCA study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--pivot-bars", type=int, nargs="+", default=[1, 2, 3, 5, 8])
    parser.add_argument("--break-mode", choices=["high", "close"], default="high")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = daily.sort_values("date").reset_index(drop=True)
    weekly = weekly_ohlcv(daily)
    monthly = monthly_dca_open(daily, args.monthly_amount)
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)

    signal_parts = []
    pivot_parts = []
    curve_parts = []
    summary_parts = []
    count_parts = []
    patterns = ["low_high_lower_low", "low_high_lower_low_higher_high"]
    for pattern in patterns:
        for pivot_bars in args.pivot_bars:
            signals, pivots, curves, summaries = run_variant(
                daily,
                weekly,
                args.monthly_amount,
                pattern,
                pivot_bars,
                args.break_mode,
                monthly_summary,
            )
            signal_parts.append(signals)
            pivot_parts.append(pivots)
            curve_parts.append(curves)
            summary_parts.append(summaries)
            count = counts_by_year(signals)
            count["pattern"] = pattern
            count["pivot_bars"] = pivot_bars
            count["break_mode"] = args.break_mode if pattern.endswith("higher_high") else ""
            count_parts.append(count)

    signals_all = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()
    pivots_all = pd.concat(pivot_parts, ignore_index=True) if pivot_parts else pd.DataFrame()
    curves_all = pd.concat(curve_parts, ignore_index=True) if curve_parts else pd.DataFrame()
    summary = pd.concat(summary_parts, ignore_index=True) if summary_parts else pd.DataFrame()
    counts = pd.concat(count_parts, ignore_index=True) if count_parts else pd.DataFrame()

    summary.to_csv(out_dir / "summary.csv", index=False)
    signals_all.to_csv(out_dir / "signals.csv", index=False)
    pivots_all.to_csv(out_dir / "pivots.csv", index=False)
    weekly.to_csv(out_dir / "weekly_bars.csv", index=False)
    curves_all.to_csv(out_dir / "curves.csv", index=False)
    counts.to_csv(out_dir / "counts_by_year.csv", index=False)

    plot_top_causal(summary, monthly_summary, out_dir / "charts" / "top_causal_vs_monthly.png")
    for pattern, stem in [("low_high_lower_low", "lhll"), ("low_high_lower_low_higher_high", "lhllhh")]:
        pattern_causal = summary[summary["pattern"].eq(pattern) & summary["variant"].eq("signal_expanding_prior_rate")]
        if pattern_causal.empty:
            continue
        best = pattern_causal.sort_values("ending_equity", ascending=False).iloc[0]
        best_pivot = int(best["pivot_bars"])
        best_curves = curves_all[curves_all["pattern"].eq(pattern) & curves_all["pivot_bars"].eq(best_pivot)].copy()
        best_counts = counts[counts["pattern"].eq(pattern) & counts["pivot_bars"].eq(best_pivot)].copy()
        plot_equity_local(
            best_curves,
            monthly,
            out_dir / "charts" / ("best_%s_equity.png" % stem),
            "QQQ weekly %s DCA comparison (%d-week pivots)" % (display_pattern(pattern), best_pivot),
        )
        plot_signal_counts(
            best_counts,
            out_dir / "charts" / ("best_%s_counts_by_year.png" % stem),
            "QQQ weekly %s signals by year (%d-week pivots)" % (display_pattern(pattern), best_pivot),
        )

    write_report(out_dir, daily, weekly, monthly_summary, summary, counts, signals_all, args.monthly_amount)
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
