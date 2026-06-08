#!/usr/bin/env python3
"""QQQ market-structure DCA study.

Pattern:
    confirmed swing low -> confirmed swing high -> confirmed lower low ->
    first later higher high above that swing high.

The buy signal is causal: swing pivots require right-side confirmation and the
higher-high break buys on the next available daily open.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from etf_obv_bearish_dca_study import max_drawdown
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_market_structure_dca_study"
DEFAULT_START = "2000-01-01"


@dataclass(frozen=True)
class Pivot:
    kind: str
    pivot_idx: int
    confirm_idx: int
    pivot_date: pd.Timestamp
    confirm_date: pd.Timestamp
    value: float


def money(value: float, digits: int = 0) -> str:
    if pd.isna(value):
        return ""
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.%df" % digits))


def first_trading_day_each_month(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily[["date"]].copy()
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def build_confirmed_pivots(daily: pd.DataFrame, left: int, right: int) -> list[Pivot]:
    highs = pd.to_numeric(daily["high"], errors="coerce").tolist()
    lows = pd.to_numeric(daily["low"], errors="coerce").tolist()
    dates = pd.to_datetime(daily["date"]).tolist()
    pivots: list[Pivot] = []
    for idx in range(left, len(daily) - right):
        high = float(highs[idx])
        low = float(lows[idx])
        left_highs = highs[idx - left : idx]
        right_highs = highs[idx + 1 : idx + right + 1]
        left_lows = lows[idx - left : idx]
        right_lows = lows[idx + 1 : idx + right + 1]
        confirm_idx = idx + right
        if all(high > float(v) for v in left_highs) and all(high > float(v) for v in right_highs):
            pivots.append(
                Pivot(
                    "high",
                    idx,
                    confirm_idx,
                    pd.Timestamp(dates[idx]),
                    pd.Timestamp(dates[confirm_idx]),
                    high,
                )
            )
        if all(low < float(v) for v in left_lows) and all(low < float(v) for v in right_lows):
            pivots.append(
                Pivot(
                    "low",
                    idx,
                    confirm_idx,
                    pd.Timestamp(dates[idx]),
                    pd.Timestamp(dates[confirm_idx]),
                    low,
                )
            )
    return sorted(pivots, key=lambda p: (p.confirm_idx, p.pivot_idx, 0 if p.kind == "low" else 1))


def detect_ll_hh_signals(daily: pd.DataFrame, left: int, right: int, break_mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    pivots = build_confirmed_pivots(daily, left, right)
    by_confirm: dict[int, list[Pivot]] = {}
    for pivot in pivots:
        by_confirm.setdefault(pivot.confirm_idx, []).append(pivot)

    l1: Pivot | None = None
    h1: Pivot | None = None
    l2: Pivot | None = None
    armed = False
    signals = []
    close = pd.to_numeric(daily["close"], errors="coerce").tolist()
    high = pd.to_numeric(daily["high"], errors="coerce").tolist()
    open_ = pd.to_numeric(daily["open"], errors="coerce").tolist()
    dates = pd.to_datetime(daily["date"]).tolist()

    for idx in range(len(daily)):
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
            elif pivot.kind == "high":
                if l1 is not None and pivot.pivot_idx > l1.pivot_idx:
                    if h1 is None or pivot.value > h1.value:
                        h1 = pivot

        if armed and l1 is not None and h1 is not None and l2 is not None and idx > l2.confirm_idx:
            break_value = float(close[idx]) if break_mode == "close" else float(high[idx])
            if break_value > h1.value:
                buy_idx = idx + 1
                if buy_idx < len(daily):
                    signals.append(
                        {
                            "signal_index": len(signals) + 1,
                            "pivot_left": left,
                            "pivot_right": right,
                            "break_mode": break_mode,
                            "l1_pivot_date": l1.pivot_date.date().isoformat(),
                            "l1_confirm_date": l1.confirm_date.date().isoformat(),
                            "l1_value": l1.value,
                            "h1_pivot_date": h1.pivot_date.date().isoformat(),
                            "h1_confirm_date": h1.confirm_date.date().isoformat(),
                            "h1_value": h1.value,
                            "l2_pivot_date": l2.pivot_date.date().isoformat(),
                            "l2_confirm_date": l2.confirm_date.date().isoformat(),
                            "l2_value": l2.value,
                            "signal_date": pd.Timestamp(dates[idx]).date().isoformat(),
                            "buy_date": pd.Timestamp(dates[buy_idx]).date().isoformat(),
                            "buy_price": float(open_[buy_idx]),
                            "bars_l1_to_h1": int(h1.pivot_idx - l1.pivot_idx),
                            "bars_h1_to_l2": int(l2.pivot_idx - h1.pivot_idx),
                            "bars_l2_to_signal": int(idx - l2.pivot_idx),
                            "l2_below_l1_pct": (l2.value / l1.value - 1.0) * 100.0,
                            "break_above_h1_pct": (break_value / h1.value - 1.0) * 100.0,
                        }
                    )
                l1 = None
                h1 = None
                l2 = None
                armed = False

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


def monthly_dca_open(daily: pd.DataFrame, monthly_amount: float) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
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
            buy_amount = cash
            shares += buy_amount / float(bar["open"])
            cash = 0.0
        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "monthly_dca_open",
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


def prior_signal_rate(
    signal_dates: list[pd.Timestamp],
    current_date: pd.Timestamp,
    start_date: pd.Timestamp,
    mode: str,
    rolling_years: float,
    floor_per_year: float,
) -> float:
    if mode == "static_full_window":
        raise ValueError("static_full_window is handled separately")
    if mode == "rolling":
        window_start = current_date - pd.Timedelta(days=int(round(365.25 * rolling_years)))
        prior = [date for date in signal_dates if window_start <= date < current_date]
        rate = len(prior) / rolling_years
    elif mode == "expanding":
        prior = [date for date in signal_dates if date < current_date]
        years = max((current_date - start_date).days / 365.25, 1e-9)
        rate = len(prior) / years
    else:
        raise ValueError("unknown sizing mode %s" % mode)
    return max(rate, floor_per_year)


def signal_dca(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    sizing_mode: str,
    static_signal_rate: float | None = None,
    rolling_years: float = 5.0,
    floor_per_year: float = 1.0,
) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    signal_dates = [pd.Timestamp(date) for date in signals["buy_date"].tolist()] if not signals.empty else []
    signal_dates = sorted(signal_dates)
    signal_set = set(signal_dates)
    start_date = pd.Timestamp(daily.iloc[0]["date"])
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        target_add_amount = math.nan
        signal_rate = math.nan
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        if date in signal_set:
            if sizing_mode == "static_full_window":
                signal_rate = max(float(static_signal_rate or 0.0), floor_per_year)
            else:
                signal_rate = prior_signal_rate(signal_dates, date, start_date, sizing_mode, rolling_years, floor_per_year)
            target_add_amount = monthly_amount * 12.0 / signal_rate
            buy_amount = min(cash, target_add_amount)
            if buy_amount > 0:
                shares += buy_amount / float(bar["open"])
                cash -= buy_amount
        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "signal_%s" % sizing_mode if sizing_mode != "rolling" else "signal_rolling_%gy" % rolling_years,
                "contribution": contribution,
                "buy_amount": buy_amount,
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
    return pd.DataFrame(rows)


def summarize_curve(curve: pd.DataFrame, variant: str, signal_count: int, signal_rate: float, monthly_ending_equity: float) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    end_equity = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = end_equity - total
    dd = max_drawdown(equity)
    buys = int(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0).gt(0).sum()) if not curve.empty else 0
    cash = float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0
    return {
        "variant": variant,
        "signal_count": signal_count,
        "signal_rate_per_year": signal_rate,
        "total_contributed": total,
        "ending_equity": end_equity,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "buys": buys,
        "avg_buy_amount": float(curve.loc[pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0) > 0, "buy_amount"].mean()) if buys else 0.0,
        "ending_cash": cash,
        "deployed_contributions_pct": (total - cash) / total * 100.0 if total else math.nan,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0) if not curve.empty else math.nan,
        "equity_vs_monthly": end_equity - monthly_ending_equity,
        "beats_monthly": end_equity > monthly_ending_equity,
    }


def counts_by_year(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame(columns=["year", "signals"])
    out = signals.copy()
    out["year"] = pd.to_datetime(out["buy_date"]).dt.year
    return out.groupby("year").size().reset_index(name="signals")


def run_variant(
    daily: pd.DataFrame,
    monthly_amount: float,
    pivot_bars: int,
    break_mode: str,
    monthly_summary: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signals, pivots = detect_ll_hh_signals(daily, pivot_bars, pivot_bars, break_mode)
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
    curves = pd.concat([static, expanding, rolling_5], ignore_index=True)
    summaries = pd.DataFrame(
        [
            summarize_curve(static, "signal_static_full_window", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve(expanding, "signal_expanding_prior_rate", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
            summarize_curve(rolling_5, "signal_rolling_5y_rate", signal_count, signal_rate, float(monthly_summary["ending_equity"])),
        ]
    )
    for df in [signals, pivots, curves, summaries]:
        df["pivot_bars"] = pivot_bars
        df["break_mode"] = break_mode
    return signals, pivots, curves, summaries


def plot_equity(curves: pd.DataFrame, monthly: pd.DataFrame, out: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(monthly["date"], monthly["equity"], color="#111827", linewidth=1.5, label="monthly_dca_open")
    colors = {
        "signal_static_full_window": "#2563eb",
        "signal_expanding_prior_rate": "#0f766e",
        "signal_rolling_5y_rate": "#b45309",
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


def plot_signal_counts(counts: pd.DataFrame, out: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(14, 5))
    if not counts.empty:
        ax.bar(counts["year"].astype(str), counts["signals"], color="#2563eb")
    ax.set_title(title)
    ax.set_ylabel("Signals")
    ax.grid(True, axis="y", alpha=0.25)
    ax.tick_params(axis="x", labelrotation=75)
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
    pivot_bars_list: list[int],
    break_mode: str,
    monthly_amount: float,
) -> None:
    best = summary[summary["variant"].eq("signal_expanding_prior_rate")].sort_values("ending_equity", ascending=False).iloc[0]
    best_any = summary.sort_values("ending_equity", ascending=False).iloc[0]
    counts_best = counts[counts["pivot_bars"].eq(int(best["pivot_bars"]))]
    median_signals = float(counts_best["signals"].median()) if not counts_best.empty else 0.0
    lines = [
        "# QQQ Low-High-Lower-Low-Higher-High DCA Study",
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`.",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "## Rule",
        "",
        "- Confirmed pivots use `N` left bars and `N` right bars; the pivot is known only after the right-side bars complete.",
        "- Bullish pattern: confirmed swing **low** -> confirmed swing **high** -> confirmed **lower low** -> first later **higher high** above that swing high.",
        "- Higher high mode: **%s**. The study buys on the next available daily open after the higher-high signal." % break_mode,
        "- Cashflow comparison: contribute **%s/month**. Monthly DCA buys each first trading day open. Signal variants hold cash and buy on pattern signals." % money(monthly_amount),
        "- `signal_expanding_prior_rate` is the causal backwards-trace sizing row: each signal uses only prior signal frequency to estimate `12 months of DCA / signals per year`.",
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
            "## Causal Backwards-Trace Read",
            "",
            "- Best causal expanding-frequency row: **%d pivot bars**, **%s**, **%d signals**, about **%.2f/year**, median **%.1f** signals/year."
            % (
                int(best["pivot_bars"]),
                best["variant"],
                int(best["signal_count"]),
                float(best["signal_rate_per_year"]),
                median_signals,
            ),
            "- It ended at **%s**, which is **%s** versus monthly DCA."
            % (money(float(best["ending_equity"])), money(float(best["equity_vs_monthly"]))),
            "- Best any-mode row was **%d pivot bars / %s** at **%s** (**%s** vs monthly)."
            % (
                int(best_any["pivot_bars"]),
                best_any["variant"],
                money(float(best_any["ending_equity"])),
                money(float(best_any["equity_vs_monthly"])),
            ),
            "",
            "## Sample Signals For Best Causal Row",
            "",
            "| Buy Date | L1 | H1 | L2 | Buy Price | L2 vs L1 | Break vs H1 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in best_signals.tail(20).iterrows():
        lines.append(
            "| %s | %.2f | %.2f | %.2f | %.2f | %.2f%% | %.2f%% |"
            % (
                row["buy_date"],
                float(row["l1_value"]),
                float(row["h1_value"]),
                float(row["l2_value"]),
                float(row["buy_price"]),
                float(row["l2_below_l1_pct"]),
                float(row["break_above_h1_pct"]),
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
    parser = argparse.ArgumentParser(description="Run QQQ low-high-lower-low-higher-high DCA study.")
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
    monthly = monthly_dca_open(daily, args.monthly_amount)
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)

    signal_parts = []
    pivot_parts = []
    curve_parts = []
    summary_parts = []
    count_parts = []
    for pivot_bars in args.pivot_bars:
        signals, pivots, curves, summaries = run_variant(
            daily,
            args.monthly_amount,
            pivot_bars,
            args.break_mode,
            monthly_summary,
        )
        signal_parts.append(signals)
        pivot_parts.append(pivots)
        curve_parts.append(curves)
        summary_parts.append(summaries)
        count = counts_by_year(signals)
        count["pivot_bars"] = pivot_bars
        count["break_mode"] = args.break_mode
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

    best = summary[summary["variant"].eq("signal_expanding_prior_rate")].sort_values("ending_equity", ascending=False).iloc[0]
    best_pivot = int(best["pivot_bars"])
    best_curves = curves_all[curves_all["pivot_bars"].eq(best_pivot)].copy()
    best_counts = counts[counts["pivot_bars"].eq(best_pivot)].copy()
    best_signals = signals_all[signals_all["pivot_bars"].eq(best_pivot)].copy()
    plot_equity(
        best_curves[best_curves["variant"].isin(["signal_static_full_window", "signal_expanding_prior_rate", "signal_rolling_5y_rate"])],
        monthly,
        out_dir / "charts" / "best_causal_equity.png",
        "QQQ L-H-LL-HH DCA comparison (%d-bar pivots)" % best_pivot,
    )
    plot_signal_counts(best_counts, out_dir / "charts" / "best_causal_counts_by_year.png", "QQQ L-H-LL-HH signals by year (%d-bar pivots)" % best_pivot)
    write_report(
        out_dir,
        daily,
        monthly_summary,
        summary,
        counts,
        best_signals,
        args.pivot_bars,
        args.break_mode,
        args.monthly_amount,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
