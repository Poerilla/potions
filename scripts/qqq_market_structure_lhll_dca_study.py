#!/usr/bin/env python3
"""QQQ low-high-lower-low DCA study.

Pattern:
    confirmed swing low -> confirmed swing high -> confirmed lower low.

The buy signal is causal: the lower-low pivot is known only after the
right-side confirmation bars complete, so the study buys the next available
daily open after that confirmation.
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
    build_confirmed_pivots,
    counts_by_year,
    first_trading_day_each_month,
    money,
    monthly_dca_open,
    plot_equity,
    plot_signal_counts,
    signal_dca,
    summarize_curve,
)
from qqq_yearly_orb_study import default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_market_structure_lhll_dca_study"
DEFAULT_START = "2000-01-01"


def detect_lhll_signals(daily: pd.DataFrame, left: int, right: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    pivots = build_confirmed_pivots(daily, left, right)
    l1 = None
    h1 = None
    signals = []
    open_ = pd.to_numeric(daily["open"], errors="coerce").tolist()
    dates = pd.to_datetime(daily["date"]).tolist()

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
                    buy_idx = pivot.confirm_idx + 1
                    if buy_idx < len(daily):
                        signals.append(
                            {
                                "signal_index": len(signals) + 1,
                                "pivot_left": left,
                                "pivot_right": right,
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
                                "buy_date": pd.Timestamp(dates[buy_idx]).date().isoformat(),
                                "buy_price": float(open_[buy_idx]),
                                "bars_l1_to_h1": int(h1.pivot_idx - l1.pivot_idx),
                                "bars_h1_to_l2": int(pivot.pivot_idx - h1.pivot_idx),
                                "l2_below_l1_pct": (pivot.value / l1.value - 1.0) * 100.0,
                            }
                        )
                    l1 = pivot
                    h1 = None
                else:
                    l1 = pivot
                    h1 = None
        else:
            if l1 is not None and pivot.pivot_idx > l1.pivot_idx:
                if h1 is None or pivot.value > h1.value:
                    h1 = pivot

    pivot_rows = [
        {
            "kind": pivot.kind,
            "pivot_idx": pivot.pivot_idx,
            "confirm_idx": pivot.confirm_idx,
            "pivot_date": pivot.pivot_date.date().isoformat(),
            "confirm_date": pivot.confirm_date.date().isoformat(),
            "value": pivot.value,
        }
        for pivot in pivots
    ]
    return pd.DataFrame(signals), pd.DataFrame(pivot_rows)


def static_lump_signal_dca(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
) -> pd.DataFrame:
    """Buy all accumulated cash at every signal."""
    invest_dates = first_trading_day_each_month(daily)
    signal_set = set(pd.to_datetime(signals["buy_date"])) if not signals.empty else set()
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        if date in signal_set:
            buy_amount = cash
            if buy_amount > 0:
                shares += buy_amount / float(bar["open"])
                cash = 0.0
        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "signal_all_cash_lump",
                "contribution": contribution,
                "buy_amount": buy_amount,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def run_variant(
    daily: pd.DataFrame,
    monthly_amount: float,
    pivot_bars: int,
    monthly_summary: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signals, pivots = detect_lhll_signals(daily, pivot_bars, pivot_bars)
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    signal_count = int(len(signals))
    signal_rate = signal_count / years
    static = signal_dca(
        daily,
        signals,
        monthly_amount,
        "static_full_window",
        static_signal_rate=signal_rate,
    )
    expanding = signal_dca(daily, signals, monthly_amount, "expanding")
    rolling_5 = signal_dca(daily, signals, monthly_amount, "rolling", rolling_years=5.0)
    all_cash = static_lump_signal_dca(daily, signals, monthly_amount)
    curves = pd.concat([static, expanding, rolling_5, all_cash], ignore_index=True)
    summaries = pd.DataFrame(
        [
            summarize_curve(static, "signal_static_full_window", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve(expanding, "signal_expanding_prior_rate", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve(rolling_5, "signal_rolling_5y_rate", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve(all_cash, "signal_all_cash_lump", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
        ]
    )
    for df in [signals, pivots, curves, summaries]:
        df["pivot_bars"] = pivot_bars
    return signals, pivots, curves, summaries


def plot_equity_local(curves: pd.DataFrame, monthly: pd.DataFrame, out: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(monthly["date"], monthly["equity"], color="#111827", linewidth=1.5, label="monthly_dca_open")
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


def write_report(
    out_dir: Path,
    daily: pd.DataFrame,
    monthly_summary: dict,
    summary: pd.DataFrame,
    counts: pd.DataFrame,
    best_signals: pd.DataFrame,
    break_read: str,
    monthly_amount: float,
) -> None:
    best_causal = summary[summary["variant"].eq("signal_expanding_prior_rate")].sort_values("ending_equity", ascending=False).iloc[0]
    best_any = summary.sort_values("ending_equity", ascending=False).iloc[0]
    counts_best = counts[counts["pivot_bars"].eq(int(best_causal["pivot_bars"]))]
    median_signals = float(counts_best["signals"].median()) if not counts_best.empty else 0.0
    lines = [
        "# QQQ Low-High-Lower-Low DCA Study",
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`.",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "## Rule",
        "",
        "- Confirmed pivots use `N` left bars and `N` right bars; the pivot is known only after the right-side bars complete.",
        "- Bullish dip pattern: confirmed swing **low** -> confirmed swing **high** -> confirmed **lower low**.",
        "- Buy timing: next available daily open after the lower-low pivot confirmation.",
        "- Cashflow comparison: contribute **%s/month**. Monthly DCA buys each first trading day open. Signal variants hold cash and buy on pattern signals." % money(monthly_amount),
        "- `signal_expanding_prior_rate` is the causal backwards-trace sizing row: each signal uses only prior signal frequency to estimate `12 months of DCA / signals per year`.",
        "- `signal_all_cash_lump` buys all accumulated cash at each signal; it is included as a more aggressive timing diagnostic.",
        "",
        "## Leaderboard",
        "",
        "| Rank | Pivot Bars | Variant | Signals | Signals / Yr | Buys | Avg Buy | Deployed | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = summary.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        lines.append(
            "| %d | %d | %s | %d | %.2f | %d | %s | %.1f%% | %s | %s | %s | %.2f | %.1f%% |"
            % (
                rank,
                int(row["pivot_bars"]),
                row["variant"],
                int(row["signal_count"]),
                float(row["signal_rate_per_year"]),
                int(row["buys"]),
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
            "- Best causal expanding-frequency row: **%d pivot bars**, **%s**, **%d signals**, about **%.2f/year**, median **%.1f** signals/year."
            % (
                int(best_causal["pivot_bars"]),
                best_causal["variant"],
                int(best_causal["signal_count"]),
                float(best_causal["signal_rate_per_year"]),
                median_signals,
            ),
            "- It ended at **%s**, which is **%s** versus monthly DCA."
            % (money(float(best_causal["ending_equity"])), money(float(best_causal["equity_vs_monthly"]))),
            "- Best any-mode row was **%d pivot bars / %s** at **%s** (**%s** vs monthly)."
            % (
                int(best_any["pivot_bars"]),
                best_any["variant"],
                money(float(best_any["ending_equity"])),
                money(float(best_any["equity_vs_monthly"])),
            ),
            "- %s" % break_read,
            "",
            "## Sample Signals For Best Causal Row",
            "",
            "| Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in best_signals.tail(20).iterrows():
        lines.append(
            "| %s | %.2f | %.2f | %.2f | %.2f | %.2f%% |"
            % (
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
            "- Best causal equity comparison: [`charts/best_causal_equity.png`](charts/best_causal_equity.png)",
            "- Best causal signal counts by year: [`charts/best_causal_counts_by_year.png`](charts/best_causal_counts_by_year.png)",
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `signals.csv`",
            "- `pivots.csv`",
            "- `curves.csv`",
            "- `counts_by_year.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QQQ low-high-lower-low DCA study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--pivot-bars", type=int, nargs="+", default=[1, 2, 3, 5, 8])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    monthly = monthly_dca_open(daily, args.monthly_amount)
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)

    signal_parts = []
    pivot_parts = []
    curve_parts = []
    summary_parts = []
    count_parts = []
    for pivot_bars in args.pivot_bars:
        signals, pivots, curves, summaries = run_variant(daily, args.monthly_amount, pivot_bars, monthly_summary)
        signal_parts.append(signals)
        pivot_parts.append(pivots)
        curve_parts.append(curves)
        summary_parts.append(summaries)
        count = counts_by_year(signals)
        count["pivot_bars"] = pivot_bars
        count_parts.append(count)

    signals_all = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()
    pivots_all = pd.concat(pivot_parts, ignore_index=True) if pivot_parts else pd.DataFrame()
    curves_all = pd.concat(curve_parts, ignore_index=True) if curve_parts else pd.DataFrame()
    summary = pd.concat(summary_parts, ignore_index=True) if summary_parts else pd.DataFrame()
    counts = pd.concat(count_parts, ignore_index=True) if count_parts else pd.DataFrame()

    summary.to_csv(out_dir / "summary.csv", index=False)
    signals_all.to_csv(out_dir / "signals.csv", index=False)
    pivots_all.to_csv(out_dir / "pivots.csv", index=False)
    curves_all.to_csv(out_dir / "curves.csv", index=False)
    counts.to_csv(out_dir / "counts_by_year.csv", index=False)

    best_causal = summary[summary["variant"].eq("signal_expanding_prior_rate")].sort_values("ending_equity", ascending=False).iloc[0]
    best_pivot = int(best_causal["pivot_bars"])
    best_curves = curves_all[curves_all["pivot_bars"].eq(best_pivot)].copy()
    best_counts = counts[counts["pivot_bars"].eq(best_pivot)].copy()
    best_signals = signals_all[signals_all["pivot_bars"].eq(best_pivot)].copy()
    plot_equity_local(
        best_curves,
        monthly,
        out_dir / "charts" / "best_causal_equity.png",
        "QQQ L-H-LL DCA comparison (%d-bar pivots)" % best_pivot,
    )
    plot_signal_counts(best_counts, out_dir / "charts" / "best_causal_counts_by_year.png", "QQQ L-H-LL signals by year (%d-bar pivots)" % best_pivot)
    best_any = summary.sort_values("ending_equity", ascending=False).iloc[0]
    break_read = "This earlier lower-low entry improved on the higher-high-confirmed version, but still did not beat monthly DCA as tested." if float(best_any["ending_equity"]) < float(monthly_summary["ending_equity"]) else "This earlier lower-low entry beat monthly DCA in at least one tested row."
    write_report(
        out_dir,
        daily,
        monthly_summary,
        summary,
        counts,
        best_signals,
        break_read,
        args.monthly_amount,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
