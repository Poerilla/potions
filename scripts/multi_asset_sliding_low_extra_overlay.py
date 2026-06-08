#!/usr/bin/env python3
"""Monthly DCA plus extra sliding-low buys across multiple tickers."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import money, monthly_dca_open, summarize_curve
from qqq_sliding_3m_low_limit_dca_study import EVENT_MODES, build_sliding_low_signals, max_drawdown
from qqq_sliding_low_extra_add_overlay import simulate_extra_overlay
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "btcc_amzn_dia_sliding_2m_low_dca_study"
DEFAULT_TICKERS = ["BTCC.TO", "AMZN", "DIA"]
DEFAULT_START = "2010-01-01"


def ticker_slug(ticker: str) -> str:
    return ticker.lower().replace(".", "_").replace("-", "_")


def summarize_overlay(
    ticker: str,
    window_mode: str,
    curve: pd.DataFrame,
    event_mode: str,
    base_summary: dict,
    equal_summary: dict,
    signal_count: int,
    years: float,
    extra_amount: float,
) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    extra_contributed = float(pd.to_numeric(curve["extra_contribution"], errors="coerce").sum()) if not curve.empty else 0.0
    return {
        "ticker": ticker,
        "window_mode": window_mode,
        "start": pd.Timestamp(curve.iloc[0]["date"]).date().isoformat() if not curve.empty else "",
        "end": pd.Timestamp(curve.iloc[-1]["date"]).date().isoformat() if not curve.empty else "",
        "event_mode": event_mode,
        "signals": signal_count,
        "signals_per_year": signal_count / years if years else math.nan,
        "extra_amount": extra_amount,
        "base_monthly_contributed": float(base_summary["total_contributed"]),
        "extra_contributed": extra_contributed,
        "total_contributed": total,
        "base_monthly_ending_equity": float(base_summary["ending_equity"]),
        "ending_equity": ending,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "ending_vs_base_monthly": ending - float(base_summary["ending_equity"]),
        "net_vs_base_monthly": net - float(base_summary["net"]),
        "ending_vs_equal_monthly": ending - float(equal_summary["ending_equity"]),
        "equal_monthly_amount": float(equal_summary["monthly_amount"]),
        "equal_monthly_ending_equity": float(equal_summary["ending_equity"]),
        "equal_monthly_net": float(equal_summary["net"]),
    }


def same_total_monthly(daily: pd.DataFrame, total_contribution: float, label: str) -> tuple[pd.DataFrame, dict]:
    month_count = int(pd.to_numeric(monthly_dca_open(daily, 1.0)["contribution"], errors="coerce").gt(0).sum())
    monthly_amount = total_contribution / month_count if month_count else 0.0
    curve = monthly_dca_open(daily, monthly_amount)
    curve["variant"] = label
    summary = summarize_curve(curve, label, 0, math.nan, 0.0)
    summary["monthly_amount"] = monthly_amount
    return curve, summary


def run_one(
    ticker: str,
    daily: pd.DataFrame,
    window_mode: str,
    lookback_months: int,
    monthly_amount: float,
    extra_amount: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = daily.copy().sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])
    base = monthly_dca_open(daily, monthly_amount)
    base["ticker"] = ticker
    base["window_mode"] = window_mode
    base_summary = summarize_curve(base, "monthly_dca_open", 0, math.nan, 0.0)
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    signals, levels = build_sliding_low_signals(daily, lookback_months)
    signals["ticker"] = ticker
    signals["window_mode"] = window_mode
    levels["ticker"] = ticker
    levels["window_mode"] = window_mode

    curve_parts = []
    event_parts = []
    summary_rows = []
    for mode, _ in EVENT_MODES:
        signal_count = int(len(signals[signals["event_mode"].eq(mode)]))
        total_contrib = float(base_summary["total_contributed"]) + signal_count * extra_amount
        equal_curve, equal_summary = same_total_monthly(daily, total_contrib, "same_total_monthly_%s" % mode)
        curve, events = simulate_extra_overlay(daily, signals, mode, monthly_amount, extra_amount)
        curve["ticker"] = ticker
        curve["window_mode"] = window_mode
        events["ticker"] = ticker
        events["window_mode"] = window_mode
        curve_parts.append(curve)
        event_parts.append(events)
        summary_rows.append(summarize_overlay(ticker, window_mode, curve, mode, base_summary, equal_summary, signal_count, years, extra_amount))

    base_row = {
        "ticker": ticker,
        "window_mode": window_mode,
        "start": pd.Timestamp(daily.iloc[0]["date"]).date().isoformat(),
        "end": pd.Timestamp(daily.iloc[-1]["date"]).date().isoformat(),
        "event_mode": "base_monthly_dca",
        "signals": 0,
        "signals_per_year": 0.0,
        "extra_amount": 0.0,
        "base_monthly_contributed": float(base_summary["total_contributed"]),
        "extra_contributed": 0.0,
        "total_contributed": float(base_summary["total_contributed"]),
        "base_monthly_ending_equity": float(base_summary["ending_equity"]),
        "ending_equity": float(base_summary["ending_equity"]),
        "net": float(base_summary["net"]),
        "return_on_contributions_pct": float(base_summary["return_on_contributions_pct"]),
        "max_dd": float(base_summary["max_dd"]),
        "net_over_dd": float(base_summary["net_over_dd"]),
        "ending_vs_base_monthly": 0.0,
        "net_vs_base_monthly": 0.0,
        "ending_vs_equal_monthly": 0.0,
        "equal_monthly_amount": monthly_amount,
        "equal_monthly_ending_equity": float(base_summary["ending_equity"]),
        "equal_monthly_net": float(base_summary["net"]),
    }
    summary = pd.DataFrame([base_row] + summary_rows)
    curves = pd.concat([base] + curve_parts, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    return summary, curves, events, pd.concat([signals, levels.assign(event_mode="level")], ignore_index=True, sort=False)


def plot_ticker_window(summary: pd.DataFrame, curves: pd.DataFrame, ticker: str, window_mode: str, out: Path, lookback_months: int) -> None:
    subset = curves[curves["ticker"].eq(ticker) & curves["window_mode"].eq(window_mode)].copy()
    if subset.empty:
        return
    fig, ax = plt.subplots(figsize=(13, 6))
    colors = {
        "monthly_dca_open": "#111827",
        "monthly_dca_plus_all_touches_extra_500": "#7c3aed",
        "monthly_dca_plus_new_touch_cluster_extra_500": "#0f766e",
        "monthly_dca_plus_first_touch_per_month_extra_500": "#2563eb",
    }
    labels = {
        "monthly_dca_open": "$1k/month DCA",
        "monthly_dca_plus_all_touches_extra_500": "+$500 every touch",
        "monthly_dca_plus_new_touch_cluster_extra_500": "+$500 new cluster",
        "monthly_dca_plus_first_touch_per_month_extra_500": "+$500 first/month",
    }
    for variant, group in subset.groupby("variant", sort=False):
        ax.plot(group["date"], group["equity"], color=colors.get(variant, "#6b7280"), linewidth=1.3, label=labels.get(variant, variant))
    ax.set_title("%s %d-month-low extra-buy overlay (%s)" % (ticker, lookback_months, window_mode))
    ax.set_ylabel("Equity (nominal local currency)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1 if window_mode == "common" else 2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def best_rows(summary: pd.DataFrame, window_mode: str) -> pd.DataFrame:
    rows = summary[summary["window_mode"].eq(window_mode) & summary["event_mode"].ne("base_monthly_dca")].copy()
    if rows.empty:
        return rows
    return rows.sort_values(["ticker", "ending_vs_equal_monthly"], ascending=[True, False]).groupby("ticker", as_index=False).head(1)


def table_rows(rows: pd.DataFrame) -> list[str]:
    lines = []
    for _, row in rows.iterrows():
        lines.append(
            "| %s | %s | %s to %s | %d | %.2f | %s | %s | %s | %s | %s |"
            % (
                row["ticker"],
                row["event_mode"],
                row["start"],
                row["end"],
                int(row["signals"]),
                float(row["signals_per_year"]),
                money(float(row["extra_contributed"])),
                money(float(row["ending_equity"])),
                money(float(row["ending_vs_base_monthly"])),
                money(float(row["equal_monthly_ending_equity"])),
                money(float(row["ending_vs_equal_monthly"])),
            )
        )
    return lines


def write_report(out_dir: Path, summary: pd.DataFrame, tickers: list[str], lookback_months: int, monthly_amount: float, extra_amount: float) -> None:
    available_best = best_rows(summary, "available")
    common_best = best_rows(summary, "common")
    title_tickers = " / ".join(tickers)
    lines = [
        "# %s Sliding %d-Month Low DCA Overlay" % (title_tickers, lookback_months),
        "",
        "Data: Yahoo adjusted daily OHLCV (%s). All tickers in this run are USD; ending dollars are directly comparable." % title_tickers,
        "",
        "Rule: regular DCA buys **%s/month** on the first trading day open. Overlay variants contribute and buy an extra **%s** when the ticker touches its prior %d-calendar-month low."
        % (money(monthly_amount), money(extra_amount), lookback_months),
        "",
        "Signal modes: `all_touches`, `new_touch_cluster`, and `first_touch_per_month`. Same-total monthly DCA is included so extra contributions are compared fairly.",
        "",
        "## Common Window Best Rows",
        "",
        "Common window starts at the latest first available date across the tickers.",
        "",
        "| Ticker | Best Signal | Window | Signals | Signals/Yr | Extra Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(table_rows(common_best))
    lines.extend(
        [
            "",
            "## Available-History Best Rows",
            "",
            "| Ticker | Best Signal | Window | Signals | Signals/Yr | Extra Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(table_rows(available_best))
    lines.extend(
        [
            "",
            "## Full Common-Window Rows",
            "",
            "| Ticker | Signal | Signals | Extra Contrib | Total Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly | Max DD | Net/DD |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    common_rows = summary[summary["window_mode"].eq("common") & summary["event_mode"].ne("base_monthly_dca")].sort_values(["ticker", "ending_vs_equal_monthly"], ascending=[True, False])
    for _, row in common_rows.iterrows():
        lines.append(
            "| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %.2f |"
            % (
                row["ticker"],
                row["event_mode"],
                int(row["signals"]),
                money(float(row["extra_contributed"])),
                money(float(row["total_contributed"])),
                money(float(row["ending_equity"])),
                money(float(row["ending_vs_base_monthly"])),
                money(float(row["equal_monthly_ending_equity"])),
                money(float(row["ending_vs_equal_monthly"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- The sidecar works best when the underlying trend is strong and drawdowns are deep enough to make the extra buys meaningful.",
            "- When tickers share the same start date, `available` and `common` windows coincide.",
            "- `all_touches` usually wins ending equity but contributes much more extra cash; `new_touch_cluster` is a cleaner operational compromise.",
            "",
            "## Charts",
            "",
        ]
    )
    for ticker in tickers:
        slug = ticker_slug(ticker)
        lines.append("- %s common-window chart: [`charts/%s_common_overlay.png`](charts/%s_common_overlay.png)" % (ticker, slug, slug))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `curves.csv`",
            "- `events.csv`",
            "- `signals_and_levels.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-asset DCA plus sliding-low extra-buy overlay.")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--lookback-months", type=int, default=2)
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--extra-amount", type=float, default=500.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily_by_ticker = {}
    for ticker in args.tickers:
        daily = load_adjusted_daily(ticker, args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh).sort_values("date").reset_index(drop=True)
        daily["date"] = pd.to_datetime(daily["date"])
        daily_by_ticker[ticker] = daily
    common_start = max(pd.Timestamp(df["date"].min()) for df in daily_by_ticker.values())

    summary_parts = []
    curve_parts = []
    event_parts = []
    signal_parts = []
    for ticker, daily in daily_by_ticker.items():
        for window_mode, window_daily in [
            ("available", daily),
            ("common", daily[daily["date"] >= common_start].reset_index(drop=True)),
        ]:
            if len(window_daily) < 80:
                continue
            summary, curves, events, signal_levels = run_one(ticker, window_daily, window_mode, args.lookback_months, args.monthly_amount, args.extra_amount)
            summary_parts.append(summary)
            curve_parts.append(curves)
            event_parts.append(events)
            signal_parts.append(signal_levels)
            if window_mode == "common":
                plot_ticker_window(summary, curves, ticker, window_mode, out_dir / "charts" / ("%s_common_overlay.png" % ticker_slug(ticker)), args.lookback_months)

    summary_all = pd.concat(summary_parts, ignore_index=True)
    curves_all = pd.concat(curve_parts, ignore_index=True)
    events_all = pd.concat(event_parts, ignore_index=True)
    signals_all = pd.concat(signal_parts, ignore_index=True)
    summary_all.to_csv(out_dir / "summary.csv", index=False)
    curves_all.to_csv(out_dir / "curves.csv", index=False)
    events_all.to_csv(out_dir / "events.csv", index=False)
    signals_all.to_csv(out_dir / "signals_and_levels.csv", index=False)
    write_report(out_dir, summary_all, args.tickers, args.lookback_months, args.monthly_amount, args.extra_amount)
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
