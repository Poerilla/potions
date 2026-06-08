#!/usr/bin/env python3
"""DJD DCA, yearly ORB, and QQQ correlation study."""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from etf_obv_bearish_dca_study import max_drawdown
from qqq_yearly_orb_study import (
    ROOT,
    Trade,
    blend_equity_curves,
    build_or_levels,
    build_yearly_summary,
    cagr,
    default_completed_end,
    hybrid_stop_breakout_plus_monthly_dca,
    load_adjusted_daily,
    max_drawdown_pct,
    simulate_orb_variant,
    summarize_trades,
    trades_to_frame,
)


OUT_DIR = ROOT / "nq" / "case_studies" / "djd_dca_yearly_orb_correlation"
DEFAULT_START = "2000-01-01"


def money(value: float) -> str:
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.0f"))


def pct(value: float) -> str:
    return "%.2f%%" % value


def first_trading_day_each_month(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily[["date"]].copy()
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def buy_hold_equity(daily: pd.DataFrame, capital: float, ticker: str) -> pd.DataFrame:
    out = daily[["date", "close"]].copy()
    first = float(out.iloc[0]["close"])
    out["variant"] = "%s buy-and-hold" % ticker
    out["equity"] = capital * pd.to_numeric(out["close"], errors="coerce") / first
    out["exposed"] = 1.0
    return out[["date", "variant", "equity", "exposed"]]


def cash_funded_monthly_dca(daily: pd.DataFrame, capital: float, ticker: str) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    installments = len(invest_dates)
    installment = capital / installments if installments else 0.0
    cash = capital
    shares = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        if date in invest_dates and cash > 0:
            buy = min(installment, cash)
            shares += buy / close
            cash -= buy
        invested_value = shares * close
        equity = cash + invested_value
        rows.append(
            {
                "date": date,
                "variant": "%s monthly DCA cash-funded" % ticker,
                "equity": equity,
                "exposed": invested_value / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def contribution_monthly_dca(daily: pd.DataFrame, monthly_amount: float, ticker: str) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        contribution = 0.0
        buy_amount = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            buy_amount = monthly_amount
            contributed += contribution
            shares += buy_amount / close
        invested = shares * close
        rows.append(
            {
                "date": date,
                "variant": "%s monthly DCA contribution" % ticker,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "equity": invested,
                "total_contributed": contributed,
                "cash": 0.0,
                "invested_value": invested,
                "exposure_frac": 1.0 if invested else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_equity(equity: pd.DataFrame, capital: float) -> pd.DataFrame:
    rows = []
    for variant, group in equity.groupby("variant"):
        group = group.sort_values("date")
        series = pd.to_numeric(group["equity"], errors="coerce")
        net = float(series.iloc[-1] - capital)
        dd = max_drawdown(series)
        dd_pct = max_drawdown_pct(series)
        rows.append(
            {
                "variant": variant,
                "start_capital": capital,
                "end_capital": float(series.iloc[-1]),
                "net": net,
                "return_pct": net / capital * 100.0,
                "cagr_pct": cagr(series, group["date"]) * 100.0,
                "max_dd": dd,
                "max_dd_pct": dd_pct * 100.0,
                "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
                "exposure_pct": 100.0 * float(pd.to_numeric(group["exposed"], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("net_over_dd", ascending=False)


def summarize_contribution_dca(curve: pd.DataFrame) -> pd.DataFrame:
    series = pd.to_numeric(curve["equity"], errors="coerce")
    contributed = float(curve.iloc[-1]["total_contributed"])
    net = float(series.iloc[-1] - contributed)
    dd = max_drawdown(series)
    return pd.DataFrame(
        [
            {
                "variant": str(curve.iloc[-1]["variant"]),
                "total_contributed": contributed,
                "end_equity": float(series.iloc[-1]),
                "net": net,
                "return_on_contributions_pct": net / contributed * 100.0 if contributed else math.nan,
                "max_dd": dd,
                "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
            }
        ]
    )


def align_common(left: pd.DataFrame, right: pd.DataFrame, left_name: str, right_name: str) -> pd.DataFrame:
    cols = ["date", "open", "high", "low", "close", "volume"]
    out = left[cols].merge(right[cols], on="date", suffixes=("_%s" % left_name.lower(), "_%s" % right_name.lower()))
    return out.sort_values("date").reset_index(drop=True)


def correlation_summary(common: pd.DataFrame) -> pd.DataFrame:
    work = common.copy()
    work["djd_daily_return"] = pd.to_numeric(work["close_djd"], errors="coerce").pct_change()
    work["qqq_daily_return"] = pd.to_numeric(work["close_qqq"], errors="coerce").pct_change()

    monthly = work[["date", "close_djd", "close_qqq"]].copy()
    monthly["month"] = monthly["date"].dt.to_period("M")
    monthly = monthly.groupby("month", as_index=False).last()
    monthly["djd_return"] = monthly["close_djd"].pct_change()
    monthly["qqq_return"] = monthly["close_qqq"].pct_change()

    yearly = work[["date", "close_djd", "close_qqq"]].copy()
    yearly["year"] = yearly["date"].dt.year
    yearly = yearly.groupby("year", as_index=False).last()
    yearly["djd_return"] = yearly["close_djd"].pct_change()
    yearly["qqq_return"] = yearly["close_qqq"].pct_change()

    qqq = work["qqq_daily_return"]
    djd = work["djd_daily_return"]
    up = work[qqq > 0]
    down = work[qqq < 0]
    rows = [
        {
            "sample": "daily",
            "observations": int(work[["djd_daily_return", "qqq_daily_return"]].dropna().shape[0]),
            "correlation": float(djd.corr(qqq)),
            "djd_avg_return_pct": float(djd.mean() * 100.0),
            "qqq_avg_return_pct": float(qqq.mean() * 100.0),
        },
        {
            "sample": "monthly",
            "observations": int(monthly[["djd_return", "qqq_return"]].dropna().shape[0]),
            "correlation": float(monthly["djd_return"].corr(monthly["qqq_return"])),
            "djd_avg_return_pct": float(monthly["djd_return"].mean() * 100.0),
            "qqq_avg_return_pct": float(monthly["qqq_return"].mean() * 100.0),
        },
        {
            "sample": "yearly",
            "observations": int(yearly[["djd_return", "qqq_return"]].dropna().shape[0]),
            "correlation": float(yearly["djd_return"].corr(yearly["qqq_return"])),
            "djd_avg_return_pct": float(yearly["djd_return"].mean() * 100.0),
            "qqq_avg_return_pct": float(yearly["qqq_return"].mean() * 100.0),
        },
        {
            "sample": "daily_when_QQQ_up",
            "observations": int(up[["djd_daily_return", "qqq_daily_return"]].dropna().shape[0]),
            "correlation": float(up["djd_daily_return"].corr(up["qqq_daily_return"])),
            "djd_avg_return_pct": float(up["djd_daily_return"].mean() * 100.0),
            "qqq_avg_return_pct": float(up["qqq_daily_return"].mean() * 100.0),
        },
        {
            "sample": "daily_when_QQQ_down",
            "observations": int(down[["djd_daily_return", "qqq_daily_return"]].dropna().shape[0]),
            "correlation": float(down["djd_daily_return"].corr(down["qqq_daily_return"])),
            "djd_avg_return_pct": float(down["djd_daily_return"].mean() * 100.0),
            "qqq_avg_return_pct": float(down["qqq_daily_return"].mean() * 100.0),
        },
    ]
    return pd.DataFrame(rows), monthly, yearly


def plot_equity(equity: pd.DataFrame, out: Path) -> None:
    colors = {
        "DJD buy-and-hold": "#111827",
        "DJD monthly DCA cash-funded": "#6b7280",
        "stop_breakout_range_close": "#0f766e",
        "close_breakout_next_open": "#2563eb",
        "limit_retest_after_close": "#7c3aed",
        "50/50 stop_breakout + monthly DCA": "#0891b2",
        "hybrid_stop_breakout_plus_monthly_dca": "#b45309",
    }
    fig, ax = plt.subplots(figsize=(14, 7))
    for variant, group in equity.groupby("variant"):
        group = group.sort_values("date")
        ax.plot(group["date"], group["equity"], label=variant, linewidth=1.3, color=colors.get(variant))
    ax.set_title("DJD DCA and yearly ORB variants")
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_correlation(common: pd.DataFrame, out: Path) -> None:
    work = common.copy()
    work["djd_norm"] = work["close_djd"] / float(work.iloc[0]["close_djd"]) * 100.0
    work["qqq_norm"] = work["close_qqq"] / float(work.iloc[0]["close_qqq"]) * 100.0
    work["djd_return"] = pd.to_numeric(work["close_djd"], errors="coerce").pct_change()
    work["qqq_return"] = pd.to_numeric(work["close_qqq"], errors="coerce").pct_change()
    work["rolling_corr_63d"] = work["djd_return"].rolling(63, min_periods=40).corr(work["qqq_return"])

    fig, (ax_price, ax_corr) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, height_ratios=[2, 1])
    ax_price.plot(work["date"], work["djd_norm"], label="DJD normalized", color="#0f766e", linewidth=1.4)
    ax_price.plot(work["date"], work["qqq_norm"], label="QQQ normalized", color="#2563eb", linewidth=1.4)
    ax_price.set_yscale("log")
    ax_price.set_ylabel("Normalized adj close\nlog scale")
    ax_price.grid(True, alpha=0.25)
    ax_price.legend(loc="upper left")
    ax_price.set_title("DJD versus QQQ")

    ax_corr.plot(work["date"], work["rolling_corr_63d"], color="#7c3aed", linewidth=1.0, label="63d return corr")
    ax_corr.axhline(0, color="#6b7280", linewidth=0.8)
    ax_corr.set_ylim(-1.05, 1.05)
    ax_corr.set_ylabel("Correlation")
    ax_corr.grid(True, alpha=0.25)
    ax_corr.legend(loc="upper left")
    ax_corr.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax_corr.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_djd_price_chart(daily: pd.DataFrame, levels: pd.DataFrame, out: Path, last_bars: int | None = None) -> None:
    work = daily.copy().sort_values("date").reset_index(drop=True)
    if last_bars is not None:
        work = work.tail(last_bars).copy().reset_index(drop=True)
    if work.empty:
        return

    work["raw_norm"] = pd.to_numeric(work["close_raw"], errors="coerce") / float(work.iloc[0]["close_raw"]) * 100.0
    work["adj_norm"] = pd.to_numeric(work["close"], errors="coerce") / float(work.iloc[0]["close"]) * 100.0
    work["sma50"] = pd.to_numeric(work["close"], errors="coerce").rolling(50, min_periods=20).mean()
    work["sma200"] = pd.to_numeric(work["close"], errors="coerce").rolling(200, min_periods=80).mean()

    start = pd.Timestamp(work["date"].min())
    end = pd.Timestamp(work["date"].max())
    visible_levels = levels[(levels["trade_end"] >= start) & (levels["or_start"] <= end)].copy()

    fig, (ax_norm, ax_price, ax_vol) = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        sharex=True,
        height_ratios=[1.4, 2.0, 0.8],
    )

    ax_norm.plot(work["date"], work["raw_norm"], color="#6b7280", linestyle="--", linewidth=1.1, label="Raw close normalized")
    ax_norm.plot(work["date"], work["adj_norm"], color="#0f766e", linewidth=1.4, label="Adjusted close normalized")
    ax_norm.set_yscale("log")
    ax_norm.set_ylabel("Normalized close\nlog scale")
    ax_norm.grid(True, alpha=0.25)
    ax_norm.legend(loc="upper left", fontsize=8)

    ax_price.plot(work["date"], work["close"], color="#111827", linewidth=1.25, label="DJD adjusted close")
    ax_price.plot(work["date"], work["sma50"], color="#2563eb", linewidth=1.0, label="SMA50")
    ax_price.plot(work["date"], work["sma200"], color="#f97316", linewidth=1.0, label="SMA200")
    for _, level in visible_levels.iterrows():
        x0 = max(pd.Timestamp(level["trade_start"]), start)
        x1 = min(pd.Timestamp(level["trade_end"]), end)
        if x0 > x1:
            continue
        ax_price.hlines(float(level["or_high"]), x0, x1, color="#0f766e", linewidth=1.1, alpha=0.55)
        ax_price.hlines(float(level["or_low"]), x0, x1, color="#c2410c", linewidth=1.1, alpha=0.45)
        if last_bars is not None:
            ax_price.text(x0, float(level["or_high"]), str(int(level["year"])), color="#0f766e", fontsize=7, va="bottom")
    ax_price.set_ylabel("Adjusted price")
    ax_price.grid(True, alpha=0.25)
    ax_price.legend(loc="upper left", fontsize=8)
    span = "recent %d bars" % last_bars if last_bars is not None else "full history"
    ax_price.set_title("DJD price chart (%s)" % span)

    ax_vol.bar(work["date"], pd.to_numeric(work["volume"], errors="coerce"), color="#94a3b8", width=1.0, alpha=0.7)
    ax_vol.set_ylabel("Volume")
    ax_vol.grid(True, axis="y", alpha=0.2)
    ax_vol.xaxis.set_major_locator(mdates.YearLocator(base=1 if last_bars is not None else 2))
    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def write_report(
    out_dir: Path,
    daily: pd.DataFrame,
    qqq: pd.DataFrame,
    levels: pd.DataFrame,
    equity_summary: pd.DataFrame,
    trade_summary: pd.DataFrame,
    contribution_summary: pd.DataFrame,
    corr_summary: pd.DataFrame,
    capital: float,
    monthly_amount: float,
) -> None:
    lines = [
        "# DJD DCA, Yearly ORB, and QQQ Correlation",
        "",
        "Data: Yahoo adjusted daily OHLCV for `DJD` and `QQQ`.",
        "Window: **%s through %s** for DJD; QQQ correlation is aligned to the same dates." % (
            daily["date"].min().date().isoformat(),
            daily["date"].max().date().isoformat(),
        ),
        "",
        "Primary performance table uses the ETF yearly-ORB convention: **%s starting capital**, no fees, no cash interest." % money(capital),
        "Contribution DCA sidecar uses **%s/month** of new cash." % money(monthly_amount),
        "",
        "Rules:",
        "",
        "- Jan-Mar defines DJD's yearly opening range.",
        "- Apr-Dec is the trade window.",
        "- `stop_breakout_range_close`: resting buy stop at the OR high from Apr 1; exit next open after a daily close back below/at OR high, or year-end.",
        "- `close_breakout_next_open`: enter next open after a fresh daily close above the OR high; same exit.",
        "- `limit_retest_after_close`: after a fresh close above the OR high, rest a buy limit at the OR high; same exit.",
        "- DCA rows are long-only DJD ETF exposure.",
        "",
        "## Equity Ranking",
        "",
        "| Rank | Variant | End Capital | Net | Return | CAGR | Max DD | Max DD % | Net/DD | Exposure |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (_, row) in enumerate(equity_summary.iterrows(), start=1):
        lines.append(
            "| %d | %s | %s | %s | %.1f%% | %.2f%% | %s | %.2f%% | %.2f | %.1f%% |"
            % (
                rank,
                row["variant"],
                money(float(row["end_capital"])),
                money(float(row["net"])),
                float(row["return_pct"]),
                float(row["cagr_pct"]),
                money(float(row["max_dd"])),
                float(row["max_dd_pct"]),
                float(row["net_over_dd"]),
                float(row["exposure_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Contribution DCA Sidecar",
            "",
            "| Variant | Total Contributed | End Equity | Net | Return On Contributions | Max DD | Net/DD |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in contribution_summary.iterrows():
        lines.append(
            "| %s | %s | %s | %s | %.1f%% | %s | %.2f |"
            % (
                row["variant"],
                money(float(row["total_contributed"])),
                money(float(row["end_equity"])),
                money(float(row["net"])),
                float(row["return_on_contributions_pct"]),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )
    lines.extend(
        [
            "",
            "## Correlation With QQQ",
            "",
            "| Sample | Observations | Correlation | DJD Avg Return | QQQ Avg Return |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in corr_summary.iterrows():
        lines.append(
            "| %s | %d | %.3f | %.3f%% | %.3f%% |"
            % (
                row["sample"],
                int(row["observations"]),
                float(row["correlation"]),
                float(row["djd_avg_return_pct"]),
                float(row["qqq_avg_return_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Trade Stats",
            "",
            "| Variant | Trades | Win Rate | PF | Avg Return | Median Return | Avg Days | Worst | Best |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if trade_summary.empty:
        lines.append("| No trades | 0 |  |  |  |  |  |  |  |")
    else:
        for _, row in trade_summary.iterrows():
            lines.append(
                "| %s | %d | %.1f%% | %.2f | %.2f%% | %.2f%% | %.1f | %.2f%% | %.2f%% |"
                % (
                    row["variant"],
                    int(row["trades"]),
                    float(row["win_rate_pct"]),
                    float(row["profit_factor"]),
                    float(row["avg_trade_return_pct"]),
                    float(row["median_trade_return_pct"]),
                    float(row["avg_days_held"]),
                    float(row["worst_trade_pct"]),
                    float(row["best_trade_pct"]),
                )
            )
    lines.extend(
        [
            "",
            "## Read",
            "",
        ]
    )
    best = equity_summary.iloc[0]
    bh = equity_summary[equity_summary["variant"].eq("DJD buy-and-hold")].iloc[0]
    dca = equity_summary[equity_summary["variant"].eq("DJD monthly DCA cash-funded")].iloc[0]
    daily_corr = corr_summary[corr_summary["sample"].eq("daily")].iloc[0]
    lines.extend(
        [
            "- Best primary row: **%s**, ending at **%s** with **%.2f Net/DD**." % (
                best["variant"],
                money(float(best["end_capital"])),
                float(best["net_over_dd"]),
            ),
            "- DJD buy-and-hold ends at **%s**; cash-funded monthly DCA ends at **%s**." % (
                money(float(bh["end_capital"])),
                money(float(dca["end_capital"])),
            ),
            "- Daily return correlation to QQQ is **%.3f**, so this is equity-correlated diversification, not an independent sleeve." % float(daily_corr["correlation"]),
            "",
            "## Charts",
            "",
            "- DJD price chart: [`charts/djd_price_full.png`](charts/djd_price_full.png)",
            "- DJD recent price chart: [`charts/djd_price_recent.png`](charts/djd_price_recent.png)",
            "- Equity comparison: [`charts/equity_comparison.png`](charts/equity_comparison.png)",
            "- DJD vs QQQ correlation: [`charts/djd_qqq_correlation.png`](charts/djd_qqq_correlation.png)",
            "",
            "## Files",
            "",
            "- `DJD_daily.csv`",
            "- `QQQ_common_daily.csv`",
            "- `or_levels.csv`",
            "- `equity_curves.csv`",
            "- `equity_summary.csv`",
            "- `trades.csv`",
            "- `trade_summary.csv`",
            "- `yearly_summary.csv`",
            "- `contribution_dca.csv`",
            "- `contribution_dca_summary.csv`",
            "- `correlation_summary.csv`",
            "- `monthly_returns.csv`",
            "- `yearly_returns.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build DJD DCA/yearly-ORB/correlation study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    djd_raw = load_adjusted_daily("DJD", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    djd_raw = djd_raw.sort_values("date").reset_index(drop=True)
    start = djd_raw["date"].min().date().isoformat()
    end = djd_raw["date"].max().date().isoformat()
    qqq_raw = load_adjusted_daily("QQQ", start, end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    qqq_raw = qqq_raw.sort_values("date").reset_index(drop=True)
    common = align_common(djd_raw, qqq_raw, "djd", "qqq")
    dates = set(pd.to_datetime(common["date"]))
    djd = djd_raw[djd_raw["date"].isin(dates)].copy().reset_index(drop=True)
    qqq = qqq_raw[qqq_raw["date"].isin(dates)].copy().reset_index(drop=True)

    levels = build_or_levels(djd)
    buy_hold = buy_hold_equity(djd, args.capital, "DJD")
    dca = cash_funded_monthly_dca(djd, args.capital, "DJD")
    hybrid = hybrid_stop_breakout_plus_monthly_dca(djd, levels, args.capital)
    equity_parts = [buy_hold, dca, hybrid]
    all_trades: list[Trade] = []
    stop_breakout = None
    for variant in ["stop_breakout_range_close", "close_breakout_next_open", "limit_retest_after_close"]:
        curve, trades = simulate_orb_variant(djd, levels, variant, args.capital)
        equity_parts.append(curve)
        all_trades.extend(trades)
        if variant == "stop_breakout_range_close":
            stop_breakout = curve
    if stop_breakout is not None:
        equity_parts.append(blend_equity_curves(stop_breakout, dca, "50/50 stop_breakout + monthly DCA"))

    equity_curves = pd.concat(equity_parts, ignore_index=True)
    trades = trades_to_frame(all_trades)
    equity_summary = summarize_equity(equity_curves, args.capital)
    trade_summary = summarize_trades(trades)
    yearly_summary = build_yearly_summary(equity_curves)
    contribution = contribution_monthly_dca(djd, args.monthly_amount, "DJD")
    contribution_summary = summarize_contribution_dca(contribution)
    corr, monthly_returns, yearly_returns = correlation_summary(common)

    djd.to_csv(out_dir / "DJD_daily.csv", index=False)
    qqq.to_csv(out_dir / "QQQ_common_daily.csv", index=False)
    levels.to_csv(out_dir / "or_levels.csv", index=False)
    equity_curves.to_csv(out_dir / "equity_curves.csv", index=False)
    equity_summary.to_csv(out_dir / "equity_summary.csv", index=False)
    trades.to_csv(out_dir / "trades.csv", index=False)
    trade_summary.to_csv(out_dir / "trade_summary.csv", index=False)
    yearly_summary.to_csv(out_dir / "yearly_summary.csv", index=False)
    contribution.to_csv(out_dir / "contribution_dca.csv", index=False)
    contribution_summary.to_csv(out_dir / "contribution_dca_summary.csv", index=False)
    corr.to_csv(out_dir / "correlation_summary.csv", index=False)
    monthly_returns.to_csv(out_dir / "monthly_returns.csv", index=False)
    yearly_returns.to_csv(out_dir / "yearly_returns.csv", index=False)

    plot_equity(equity_curves, out_dir / "charts" / "equity_comparison.png")
    plot_correlation(common, out_dir / "charts" / "djd_qqq_correlation.png")
    plot_djd_price_chart(djd, levels, out_dir / "charts" / "djd_price_full.png")
    plot_djd_price_chart(djd, levels, out_dir / "charts" / "djd_price_recent.png", last_bars=760)
    write_report(
        out_dir,
        djd,
        qqq,
        levels,
        equity_summary,
        trade_summary,
        contribution_summary,
        corr,
        args.capital,
        args.monthly_amount,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
