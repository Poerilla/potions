#!/usr/bin/env python3
"""RSI overbought deferral sweep for combined 2m-low + LHLL DCA."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from googl_qqq_combined_2m_low_lhll_dca_study import (
    DEFAULT_LOOKBACK_MONTHS,
    DEFAULT_MONTHLY_AMOUNT,
    DEFAULT_PIVOT_BARS,
    DEFAULT_START,
    DEFAULT_TICKERS,
    combined_signals,
    signal_rate_prior,
    ticker_slug,
)
from qqq_market_structure_dca_study import first_trading_day_each_month, money, monthly_dca_open, summarize_curve
from qqq_sliding_3m_low_limit_dca_study import EVENT_MODES, max_drawdown
from qqq_smoothed_rsi_chart import compute_rsi
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_qqq_combined_lhll_rsi_deferral_study"
RSI_TIMEFRAMES = ["daily", "weekly", "monthly"]
THRESHOLDS = [60.0, 65.0, 70.0, 75.0, 80.0]
SIZING_MODES = ["static_full_window", "expanding_prior_rate", "rolling_5y_rate"]
MAX_REDEPLOY_MULTIPLE = 2.0


def aggregate_ohlcv(daily: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    work = daily.copy().sort_values("date").reset_index(drop=True)
    work["date"] = pd.to_datetime(work["date"])
    if timeframe == "weekly":
        work["_period"] = work["date"].dt.to_period("W-FRI")
    elif timeframe == "monthly":
        work["_period"] = work["date"].dt.to_period("M")
    else:
        raise ValueError("timeframe must be weekly or monthly")
    return (
        work.groupby("_period", as_index=False)
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


def add_rsi_state(
    daily: pd.DataFrame,
    timeframe: str,
    threshold: float,
    rsi_length: int,
    smooth: int,
) -> pd.DataFrame:
    base = daily.copy().sort_values("date").reset_index(drop=True)
    base["date"] = pd.to_datetime(base["date"])
    if timeframe == "daily":
        rsi_bars = compute_rsi(base, rsi_length, smooth)
    else:
        rsi_bars = compute_rsi(aggregate_ohlcv(base, timeframe), rsi_length, smooth)
    state = rsi_bars[["date", "rsi", "rsi_smooth"]].copy().sort_values("date")
    state = state.rename(columns={"rsi": "state_rsi", "rsi_smooth": "state_rsi_smooth"})
    mapped = pd.merge_asof(
        base[["date"]].sort_values("date"),
        state,
        on="date",
        direction="backward",
        allow_exact_matches=False,
    )
    out = base.merge(mapped, on="date", how="left")
    out["rsi_timeframe"] = timeframe
    out["rsi_threshold"] = threshold
    out["overbought"] = pd.to_numeric(out["state_rsi_smooth"], errors="coerce").ge(threshold).fillna(False)
    return out


def simulate_basic_deferral(
    daily: pd.DataFrame,
    monthly_amount: float,
    max_multiple: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        event_type = ""
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            if bool(bar["overbought"]):
                event_type = "monthly_blocked_overbought"
            else:
                buy_amount = min(cash, monthly_amount * max_multiple)
                shares += buy_amount / float(bar["open"])
                cash -= buy_amount
                event_type = "monthly_buy_allowed"
            events.append(
                {
                    "date": date,
                    "strategy": "basic_dca_deferral",
                    "event_type": event_type,
                    "overbought": bool(bar["overbought"]),
                    "buy_amount": buy_amount,
                    "buy_price": float(bar["open"]) if buy_amount else math.nan,
                    "cash_after": cash,
                    "state_rsi_smooth": float(bar["state_rsi_smooth"]) if pd.notna(bar["state_rsi_smooth"]) else math.nan,
                }
            )
        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "basic_dca_deferral",
                "contribution": contribution,
                "buy_amount": buy_amount,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
                "overbought": bool(bar["overbought"]),
                "state_rsi_smooth": bar["state_rsi_smooth"],
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def simulate_combined_deferral(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    sizing_mode: str,
    static_signal_rate: float,
    max_multiple: float,
    rolling_years: float = 5.0,
    floor_per_year: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    work_signals = signals.copy().sort_values(["date", "combined_signal_index"]).reset_index(drop=True)
    signal_dates = [pd.Timestamp(date) for date in work_signals["date"].tolist()] if not work_signals.empty else []
    by_date: dict[pd.Timestamp, list[pd.Series]] = {}
    for _, signal in work_signals.iterrows():
        by_date.setdefault(pd.Timestamp(signal["date"]), []).append(signal)

    start_date = pd.Timestamp(daily.iloc[0]["date"])
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        day_buy = 0.0
        day_signals = 0
        if date in invest_dates:
            contribution = monthly_amount
            cash += contribution
            contributed += contribution

        for signal in by_date.get(date, []):
            day_signals += 1
            if sizing_mode == "static_full_window":
                signal_rate = max(static_signal_rate, floor_per_year)
            else:
                signal_rate = signal_rate_prior(signal_dates, date, start_date, sizing_mode, rolling_years, floor_per_year)
            target_add = monthly_amount * 12.0 / signal_rate
            buy_amount = 0.0
            blocked = bool(bar["overbought"])
            if not blocked:
                buy_amount = min(cash, target_add * max_multiple)
                if buy_amount > 0:
                    shares += buy_amount / float(signal["buy_price"])
                    cash -= buy_amount
                    day_buy += buy_amount
            events.append(
                {
                    "date": date,
                    "strategy": "combined_signal_deferral",
                    "signal_family": signal["signal_family"],
                    "signal_key": signal["signal_key"],
                    "touch_mode": signal["touch_mode"],
                    "sizing_mode": sizing_mode,
                    "event_type": "signal_blocked_overbought" if blocked else "signal_buy_allowed",
                    "overbought": blocked,
                    "buy_amount": buy_amount,
                    "buy_price": float(signal["buy_price"]) if buy_amount else math.nan,
                    "target_add_amount": target_add,
                    "signal_rate_per_year": signal_rate,
                    "cash_after": cash,
                    "combined_signal_index": int(signal["combined_signal_index"]),
                    "state_rsi_smooth": float(bar["state_rsi_smooth"]) if pd.notna(bar["state_rsi_smooth"]) else math.nan,
                }
            )

        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "combined_%s_deferral" % sizing_mode,
                "sizing_mode": sizing_mode,
                "contribution": contribution,
                "buy_amount": day_buy,
                "signal_occurrences": day_signals,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
                "overbought": bool(bar["overbought"]),
                "state_rsi_smooth": bar["state_rsi_smooth"],
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def summarize_deferral(
    ticker: str,
    strategy: str,
    curve: pd.DataFrame,
    events: pd.DataFrame,
    baseline_monthly: dict,
    rsi_timeframe: str,
    threshold: float,
    touch_mode: str = "",
    sizing_mode: str = "",
    signal_count: int = 0,
    sliding_count: int = 0,
    lhll_count: int = 0,
    static_matched_add: float = math.nan,
) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    buy_amounts = pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0)
    event_type = events["event_type"].astype(str) if not events.empty and "event_type" in events else pd.Series(dtype=str)
    blocked = int(event_type.str.contains("blocked").sum()) if not event_type.empty else 0
    allowed = int(event_type.str.contains("allowed").sum()) if not event_type.empty else 0
    return {
        "ticker": ticker,
        "strategy": strategy,
        "touch_mode": touch_mode,
        "sizing_mode": sizing_mode,
        "rsi_timeframe": rsi_timeframe,
        "rsi_threshold": threshold,
        "signal_count": signal_count,
        "sliding_signal_count": sliding_count,
        "lhll_signal_count": lhll_count,
        "static_matched_add_amount": static_matched_add,
        "events_blocked": blocked,
        "events_allowed": allowed,
        "total_contributed": total,
        "ending_equity": ending,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "buys": int(buy_amounts.gt(0).sum()),
        "avg_buy_amount": float(buy_amounts[buy_amounts.gt(0)].mean()) if buy_amounts.gt(0).any() else 0.0,
        "ending_cash": float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0,
        "deployed_contributions_pct": (total - float(curve.iloc[-1]["cash"])) / total * 100.0 if total else math.nan,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0) if not curve.empty else math.nan,
        "basic_dca_ending_equity": float(baseline_monthly["ending_equity"]),
        "ending_vs_basic_dca": ending - float(baseline_monthly["ending_equity"]),
    }


def plot_selected_curves(curves: pd.DataFrame, ticker: str, out: Path) -> None:
    subset = curves[curves["ticker"].eq(ticker)].copy()
    if subset.empty:
        return
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = {
        "basic_dca_open": "#111827",
        "best_basic_deferral": "#2563eb",
        "best_combined_deferral": "#b45309",
        "best_combined_unfiltered": "#0f766e",
    }
    labels = {
        "basic_dca_open": "$1k/month basic DCA",
        "best_basic_deferral": "best RSI-deferred basic DCA",
        "best_combined_deferral": "best RSI-deferred combined",
        "best_combined_unfiltered": "best unfiltered combined",
    }
    for variant, group in subset.groupby("plot_variant", sort=False):
        ax.plot(group["date"], group["equity"], color=colors.get(variant, "#6b7280"), linewidth=1.25, label=labels.get(variant, variant))
    ax.set_title("%s RSI overbought deferral comparison" % ticker)
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


def table_row(row: pd.Series) -> str:
    return (
        "| %s | %s | %s | %s | %.0f | %s | %s | %s | %d | %d | %s | %.1f%% | %s | %s | %.2f |"
        % (
            row["ticker"],
            row["strategy"],
            row.get("touch_mode", "") or "-",
            row.get("sizing_mode", "") or "-",
            float(row["rsi_threshold"]),
            row["rsi_timeframe"],
            money(float(row["ending_equity"])),
            money(float(row["ending_vs_basic_dca"])),
            int(row["events_blocked"]),
            int(row["buys"]),
            money(float(row["ending_cash"])),
            float(row["deployed_contributions_pct"]),
            money(float(row["max_dd"])),
            money(float(row["static_matched_add_amount"])) if pd.notna(row["static_matched_add_amount"]) else "-",
            float(row["net_over_dd"]),
        )
    )


def write_report(
    out_dir: Path,
    summary: pd.DataFrame,
    baselines: pd.DataFrame,
    tickers: list[str],
    thresholds: list[float],
    rsi_timeframes: list[str],
    rsi_length: int,
    smooth: int,
    max_multiple: float,
    monthly_amount: float,
    start: str,
    end: str,
) -> None:
    filtered = summary[summary["rsi_timeframe"].ne("none")].copy()
    basic = filtered[filtered["strategy"].eq("basic_dca_deferral")]
    combined = filtered[filtered["strategy"].eq("combined_signal_deferral")]
    best_basic = basic.sort_values(["ticker", "ending_equity"], ascending=[True, False]).groupby("ticker", as_index=False).head(1)
    best_combined = combined.sort_values(["ticker", "ending_equity"], ascending=[True, False]).groupby("ticker", as_index=False).head(1)
    lines = [
        "# GOOGL / QQQ RSI Overbought Deferral Sweep",
        "",
        "Data: Yahoo adjusted daily OHLCV on the common comparison window.",
        "",
        "Window: **%s through %s**." % (start, end),
        "",
        "Rule tested:",
        "",
        "- Keep `$1,000/month` cashflow.",
        "- If the selected RSI cadence is overbought, skip the scheduled buy/add and leave cash idle.",
        "- Later allowed buys can spend up to **%.1fx** the normal target, so skipped cash is redeployed gradually." % max_multiple,
        "- RSI is Wilder RSI(%d) smoothed with EMA(%d), mapped causally from the prior completed daily/weekly/monthly bar." % (rsi_length, smooth),
        "- Thresholds swept: **%s** across **%s**." % (", ".join("%.0f" % x for x in thresholds), ", ".join(rsi_timeframes)),
        "- Rows with **0 blocked events** did not actually use the overbought filter; any improvement there comes from the 2x redeployment cap, not RSI timing.",
        "",
        "Strategies tested:",
        "",
        "- **basic_dca_deferral:** first-trading-day monthly DCA with the same overbought skip/redeploy rule.",
        "- **combined_signal_deferral:** combined 2-month-low touch + monthly LHLL signal buys with the same overbought skip/redeploy rule.",
        "",
        "## Unfiltered Baselines",
        "",
        "| Ticker | Baseline | Touch Mode | Sizing | Ending Equity | vs Basic DCA | Max DD | Net/DD |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for _, row in baselines.iterrows():
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %.2f |"
            % (
                row["ticker"],
                row["strategy"],
                row.get("touch_mode", "") or "-",
                row.get("sizing_mode", "") or "-",
                money(float(row["ending_equity"])),
                money(float(row["ending_vs_basic_dca"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )
    lines.extend(
        [
            "",
            "## Best Filtered Rows",
            "",
            "| Ticker | Strategy | Touch | Sizing | Threshold | RSI TF | Ending Equity | vs Basic DCA | Blocked Events | Buys | Ending Cash | Deployed | Max DD | Matched Add | Net/DD |",
            "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in pd.concat([best_basic, best_combined], ignore_index=True).sort_values(["ticker", "strategy"]).iterrows():
        lines.append(table_row(row))
    lines.extend(
        [
            "",
            "## Combined-Signal Top 15",
            "",
            "| Ticker | Strategy | Touch | Sizing | Threshold | RSI TF | Ending Equity | vs Basic DCA | Blocked Events | Buys | Ending Cash | Deployed | Max DD | Matched Add | Net/DD |",
            "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    top_combined = combined.sort_values(["ticker", "ending_equity"], ascending=[True, False]).groupby("ticker", as_index=False).head(15)
    for _, row in top_combined.iterrows():
        lines.append(table_row(row))
    lines.extend(["", "## Read", ""])
    for ticker in tickers:
        base = baselines[(baselines["ticker"].eq(ticker)) & (baselines["strategy"].eq("basic_dca_open"))].iloc[0]
        b_basic = best_basic[best_basic["ticker"].eq(ticker)].iloc[0]
        b_combined = best_combined[best_combined["ticker"].eq(ticker)].iloc[0]
        lines.append(
            "- **%s:** basic DCA is **%s**. Best RSI-deferred basic DCA is **%s / %.0f %s** at **%s** (**%s** vs basic). Best RSI-deferred combined signal is **%s / %s / %.0f %s** at **%s** (**%s** vs basic)."
            % (
                ticker,
                money(float(base["ending_equity"])),
                b_basic["rsi_timeframe"],
                float(b_basic["rsi_threshold"]),
                "threshold",
                money(float(b_basic["ending_equity"])),
                money(float(b_basic["ending_vs_basic_dca"])),
                b_combined["touch_mode"],
                b_combined["rsi_timeframe"],
                float(b_combined["rsi_threshold"]),
                "threshold",
                money(float(b_combined["ending_equity"])),
                money(float(b_combined["ending_vs_basic_dca"])),
            )
        )
    lines.extend(["", "## Charts", ""])
    for ticker in tickers:
        slug = ticker_slug(ticker)
        lines.append("- %s selected equity curves: [`charts/%s_selected_equity.png`](charts/%s_selected_equity.png)" % (ticker, slug, slug))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `baselines.csv`",
            "- `selected_curves.csv`",
            "- `events.csv`",
            "",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=DEFAULT_MONTHLY_AMOUNT)
    parser.add_argument("--lookback-months", type=int, default=DEFAULT_LOOKBACK_MONTHS)
    parser.add_argument("--pivot-bars", type=int, default=DEFAULT_PIVOT_BARS)
    parser.add_argument("--rsi-length", type=int, default=14)
    parser.add_argument("--smooth", type=int, default=14)
    parser.add_argument("--thresholds", nargs="+", type=float, default=THRESHOLDS)
    parser.add_argument("--rsi-timeframes", nargs="+", default=RSI_TIMEFRAMES)
    parser.add_argument("--max-multiple", type=float, default=MAX_REDEPLOY_MULTIPLE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    raw_daily: dict[str, pd.DataFrame] = {}
    for ticker in args.tickers:
        daily = load_adjusted_daily(ticker, args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
        daily = daily.sort_values("date").reset_index(drop=True)
        daily["date"] = pd.to_datetime(daily["date"])
        raw_daily[ticker.upper()] = daily
    common_start = max(pd.Timestamp(df["date"].min()) for df in raw_daily.values())
    daily_by_ticker = {
        ticker: df[df["date"] >= common_start].copy().reset_index(drop=True)
        for ticker, df in raw_daily.items()
    }
    common_start_str = min(df["date"].min().date().isoformat() for df in daily_by_ticker.values())
    common_end_str = max(df["date"].max().date().isoformat() for df in daily_by_ticker.values())

    summary_rows = []
    baseline_rows = []
    selected_curves = []
    event_parts = []

    for ticker, daily in daily_by_ticker.items():
        basic_curve = monthly_dca_open(daily, args.monthly_amount)
        basic_curve["ticker"] = ticker
        basic_curve["plot_variant"] = "basic_dca_open"
        basic_summary = summarize_curve(basic_curve, "monthly_dca_open", 0, math.nan, 0.0)
        baseline_rows.append(
            {
                "ticker": ticker,
                "strategy": "basic_dca_open",
                "touch_mode": "",
                "sizing_mode": "",
                "ending_equity": float(basic_summary["ending_equity"]),
                "ending_vs_basic_dca": 0.0,
                "max_dd": float(basic_summary["max_dd"]),
                "net_over_dd": float(basic_summary["net_over_dd"]),
            }
        )
        selected_curves.append(basic_curve)

        years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
        signals_by_touch = {}
        for touch_mode, _ in EVENT_MODES:
            signals, _, _, _ = combined_signals(daily, touch_mode, args.lookback_months, args.pivot_bars)
            signals_by_touch[touch_mode] = signals

        # Keep the unfiltered best combined row as a reference line in the chart/report.
        unfiltered_candidates = []
        unfiltered_curves = {}
        from googl_qqq_combined_2m_low_lhll_dca_study import simulate_combined_signal_dca, summarize_combined

        for touch_mode, signals in signals_by_touch.items():
            static_rate = len(signals) / years if years else 0.0
            for sizing_mode in SIZING_MODES:
                curve, _ = simulate_combined_signal_dca(daily, signals, args.monthly_amount, sizing_mode, static_rate)
                row = summarize_combined(ticker, touch_mode, sizing_mode, curve, signals, basic_summary, years, args.monthly_amount)
                row["strategy"] = "combined_signal_unfiltered"
                unfiltered_candidates.append(row)
                unfiltered_curves[(touch_mode, sizing_mode)] = curve
        unfiltered_best = pd.DataFrame(unfiltered_candidates).sort_values("ending_equity", ascending=False).iloc[0]
        baseline_rows.append(
            {
                "ticker": ticker,
                "strategy": "combined_signal_unfiltered",
                "touch_mode": unfiltered_best["touch_mode"],
                "sizing_mode": unfiltered_best["sizing_mode"],
                "ending_equity": float(unfiltered_best["ending_equity"]),
                "ending_vs_basic_dca": float(unfiltered_best["ending_vs_monthly_dca"]),
                "max_dd": float(unfiltered_best["max_dd"]),
                "net_over_dd": float(unfiltered_best["net_over_dd"]),
            }
        )
        ref_curve = unfiltered_curves[(unfiltered_best["touch_mode"], unfiltered_best["sizing_mode"])].copy()
        ref_curve["ticker"] = ticker
        ref_curve["plot_variant"] = "best_combined_unfiltered"
        selected_curves.append(ref_curve)

        curve_cache: dict[tuple, pd.DataFrame] = {}
        for rsi_timeframe in args.rsi_timeframes:
            for threshold in args.thresholds:
                state_daily = add_rsi_state(daily, rsi_timeframe, threshold, args.rsi_length, args.smooth)
                basic_def, basic_events = simulate_basic_deferral(state_daily, args.monthly_amount, args.max_multiple)
                summary_rows.append(
                    summarize_deferral(
                        ticker,
                        "basic_dca_deferral",
                        basic_def,
                        basic_events,
                        basic_summary,
                        rsi_timeframe,
                        threshold,
                    )
                )
                basic_def["ticker"] = ticker
                curve_cache[("basic", "", "", rsi_timeframe, threshold)] = basic_def
                if not basic_events.empty:
                    basic_events["ticker"] = ticker
                    basic_events["rsi_timeframe"] = rsi_timeframe
                    basic_events["rsi_threshold"] = threshold
                    event_parts.append(basic_events)

                for touch_mode, signals in signals_by_touch.items():
                    signal_count = int(len(signals))
                    sliding_count = int(signals["signal_family"].astype(str).str.startswith("sliding_").sum()) if not signals.empty else 0
                    lhll_count = int(signals["signal_family"].eq("monthly_lhll").sum()) if not signals.empty else 0
                    static_rate = signal_count / years if years else 0.0
                    static_matched = args.monthly_amount * 12.0 / static_rate if static_rate else math.inf
                    for sizing_mode in SIZING_MODES:
                        curve, events = simulate_combined_deferral(
                            state_daily,
                            signals,
                            args.monthly_amount,
                            sizing_mode,
                            static_rate,
                            args.max_multiple,
                        )
                        summary_rows.append(
                            summarize_deferral(
                                ticker,
                                "combined_signal_deferral",
                                curve,
                                events,
                                basic_summary,
                                rsi_timeframe,
                                threshold,
                                touch_mode,
                                sizing_mode,
                                signal_count,
                                sliding_count,
                                lhll_count,
                                static_matched,
                            )
                        )
                        curve["ticker"] = ticker
                        curve_cache[("combined", touch_mode, sizing_mode, rsi_timeframe, threshold)] = curve
                        if not events.empty:
                            events["ticker"] = ticker
                            events["rsi_timeframe"] = rsi_timeframe
                            events["rsi_threshold"] = threshold
                            event_parts.append(events)

        ticker_summary = pd.DataFrame([row for row in summary_rows if row["ticker"] == ticker])
        best_basic = ticker_summary[ticker_summary["strategy"].eq("basic_dca_deferral")].sort_values("ending_equity", ascending=False).iloc[0]
        best_combined = ticker_summary[ticker_summary["strategy"].eq("combined_signal_deferral")].sort_values("ending_equity", ascending=False).iloc[0]
        best_basic_curve = curve_cache[("basic", "", "", best_basic["rsi_timeframe"], float(best_basic["rsi_threshold"]))].copy()
        best_basic_curve["ticker"] = ticker
        best_basic_curve["plot_variant"] = "best_basic_deferral"
        selected_curves.append(best_basic_curve)
        best_combined_curve = curve_cache[
            (
                "combined",
                best_combined["touch_mode"],
                best_combined["sizing_mode"],
                best_combined["rsi_timeframe"],
                float(best_combined["rsi_threshold"]),
            )
        ].copy()
        best_combined_curve["ticker"] = ticker
        best_combined_curve["plot_variant"] = "best_combined_deferral"
        selected_curves.append(best_combined_curve)

    summary = pd.DataFrame(summary_rows)
    baselines = pd.DataFrame(baseline_rows)
    selected = pd.concat(selected_curves, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True, sort=False) if event_parts else pd.DataFrame()

    summary.to_csv(out_dir / "summary.csv", index=False)
    baselines.to_csv(out_dir / "baselines.csv", index=False)
    selected.to_csv(out_dir / "selected_curves.csv", index=False)
    events.to_csv(out_dir / "events.csv", index=False)
    for ticker in sorted(selected["ticker"].unique()):
        plot_selected_curves(selected, ticker, out_dir / "charts" / ("%s_selected_equity.png" % ticker_slug(ticker)))
    write_report(
        out_dir,
        summary,
        baselines,
        sorted(daily_by_ticker.keys()),
        [float(x) for x in args.thresholds],
        list(args.rsi_timeframes),
        args.rsi_length,
        args.smooth,
        args.max_multiple,
        args.monthly_amount,
        common_start_str,
        common_end_str,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
