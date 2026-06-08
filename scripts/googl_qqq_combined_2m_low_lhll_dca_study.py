#!/usr/bin/env python3
"""Combined 2-month-low touch + monthly LHLL DCA study for GOOGL and QQQ."""
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
from qqq_market_structure_monthly_pivot_dca_study import detect_lhll_monthly, monthly_ohlcv
from qqq_sliding_3m_low_limit_dca_study import EVENT_MODES, build_sliding_low_signals, max_drawdown
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_qqq_combined_2m_low_lhll_dca_study"
DEFAULT_START = "2004-01-01"
DEFAULT_TICKERS = ["GOOGL", "QQQ"]
DEFAULT_MONTHLY_AMOUNT = 1_000.0
DEFAULT_LOOKBACK_MONTHS = 2
DEFAULT_PIVOT_BARS = 2
SIZING_MODES = ["static_full_window", "expanding_prior_rate", "rolling_5y_rate"]


def ticker_slug(ticker: str) -> str:
    return ticker.lower().replace(".", "_").replace("-", "_")


def signal_rate_prior(
    dates: list[pd.Timestamp],
    current_date: pd.Timestamp,
    start_date: pd.Timestamp,
    sizing_mode: str,
    rolling_years: float,
    floor_per_year: float,
) -> float:
    if sizing_mode == "expanding_prior_rate":
        prior = [date for date in dates if date < current_date]
        years = max((current_date - start_date).days / 365.25, 1e-9)
        rate = len(prior) / years
    elif sizing_mode == "rolling_5y_rate":
        window_start = current_date - pd.Timedelta(days=int(round(365.25 * rolling_years)))
        prior = [date for date in dates if window_start <= date < current_date]
        rate = len(prior) / rolling_years
    else:
        raise ValueError("unknown sizing mode %s" % sizing_mode)
    return max(rate, floor_per_year)


def build_lhll_signals(daily: pd.DataFrame, pivot_bars: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly, dropped_month = monthly_ohlcv(daily, drop_final_partial=True)
    monthly["date"] = pd.to_datetime(monthly["date"])
    lhll, pivots = detect_lhll_monthly(daily, monthly, pivot_bars)
    if not lhll.empty:
        for column in [
            "l1_pivot_date",
            "l1_confirm_date",
            "h1_pivot_date",
            "h1_confirm_date",
            "l2_pivot_date",
            "l2_confirm_date",
            "signal_date",
            "buy_date",
        ]:
            lhll[column] = pd.to_datetime(lhll[column])
        lhll["dropped_partial_month"] = dropped_month
    if not pivots.empty:
        pivots["pivot_date"] = pd.to_datetime(pivots["pivot_date"])
        pivots["confirm_date"] = pd.to_datetime(pivots["confirm_date"])
    return lhll, pivots, monthly


def combined_signals(
    daily: pd.DataFrame,
    touch_mode: str,
    lookback_months: int,
    pivot_bars: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sliding, levels = build_sliding_low_signals(daily, lookback_months)
    if not sliding.empty:
        for column in ["date", "rolling_low_date", "window_start"]:
            sliding[column] = pd.to_datetime(sliding[column])
    if not levels.empty:
        for column in ["date", "rolling_low_date", "window_start"]:
            levels[column] = pd.to_datetime(levels[column])

    lhll, pivots, monthly = build_lhll_signals(daily, pivot_bars)
    rows = []
    touch = sliding[sliding["event_mode"].eq(touch_mode)].copy()
    for idx, row in touch.sort_values("date").reset_index(drop=True).iterrows():
        rows.append(
            {
                "date": pd.Timestamp(row["date"]),
                "buy_price": float(row["buy_price"]),
                "signal_family": "sliding_%dm_low" % lookback_months,
                "touch_mode": touch_mode,
                "signal_key": "sliding_%dm_low_%s" % (lookback_months, touch_mode),
                "source_index": int(idx + 1),
                "rolling_low": float(row["rolling_low"]),
                "rolling_low_date": pd.Timestamp(row["rolling_low_date"]),
                "window_start": pd.Timestamp(row["window_start"]),
                "daily_low": float(row["daily_low"]),
                "daily_open": float(row["daily_open"]),
                "daily_close": float(row["daily_close"]),
                "signal_date": pd.Timestamp(row["date"]),
                "lhll_l1_date": pd.NaT,
                "lhll_h1_date": pd.NaT,
                "lhll_l2_date": pd.NaT,
            }
        )
    for _, row in lhll.sort_values("buy_date").iterrows():
        buy_date = pd.Timestamp(row["buy_date"])
        rows.append(
            {
                "date": buy_date,
                "buy_price": float(row["buy_price"]),
                "signal_family": "monthly_lhll",
                "touch_mode": touch_mode,
                "signal_key": "monthly_lhll_%dm_pivots" % pivot_bars,
                "source_index": int(row["signal_index"]),
                "rolling_low": math.nan,
                "rolling_low_date": pd.NaT,
                "window_start": pd.NaT,
                "daily_low": math.nan,
                "daily_open": math.nan,
                "daily_close": math.nan,
                "signal_date": pd.Timestamp(row["signal_date"]),
                "lhll_l1_date": pd.Timestamp(row["l1_pivot_date"]),
                "lhll_h1_date": pd.Timestamp(row["h1_pivot_date"]),
                "lhll_l2_date": pd.Timestamp(row["l2_pivot_date"]),
            }
        )
    signals = pd.DataFrame(rows)
    if not signals.empty:
        family_order = {"sliding_%dm_low" % lookback_months: 0, "monthly_lhll": 1}
        signals["_family_order"] = signals["signal_family"].map(family_order).fillna(9)
        signals = signals.sort_values(["date", "_family_order", "source_index"]).drop(columns=["_family_order"]).reset_index(drop=True)
        signals["combined_signal_index"] = signals.index + 1
    return signals, sliding, lhll, pd.concat([levels.assign(table_type="sliding_level"), pivots.assign(table_type="monthly_pivot")], ignore_index=True, sort=False)


def simulate_combined_signal_dca(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    sizing_mode: str,
    static_signal_rate: float,
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
    curve_rows = []
    event_rows = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        day_buy_amount = 0.0
        day_signal_count = 0
        if date in invest_dates:
            contribution = monthly_amount
            cash += contribution
            contributed += contribution

        for signal in by_date.get(date, []):
            day_signal_count += 1
            if sizing_mode == "static_full_window":
                signal_rate = max(static_signal_rate, floor_per_year)
            else:
                signal_rate = signal_rate_prior(signal_dates, date, start_date, sizing_mode, rolling_years, floor_per_year)
            target_add_amount = monthly_amount * 12.0 / signal_rate
            buy_amount = min(cash, target_add_amount)
            buy_price = float(signal["buy_price"])
            if buy_amount > 0:
                shares += buy_amount / buy_price
                cash -= buy_amount
                day_buy_amount += buy_amount
            event_rows.append(
                {
                    "date": date,
                    "signal_family": signal["signal_family"],
                    "signal_key": signal["signal_key"],
                    "touch_mode": signal["touch_mode"],
                    "sizing_mode": sizing_mode,
                    "buy_amount": buy_amount,
                    "buy_price": buy_price,
                    "shares_bought": buy_amount / buy_price if buy_amount else 0.0,
                    "target_add_amount": target_add_amount,
                    "signal_rate_per_year": signal_rate,
                    "cash_after": cash,
                    "combined_signal_index": int(signal["combined_signal_index"]),
                    "signal_date": pd.Timestamp(signal["signal_date"]),
                    "rolling_low_date": signal.get("rolling_low_date", pd.NaT),
                    "lhll_l1_date": signal.get("lhll_l1_date", pd.NaT),
                    "lhll_h1_date": signal.get("lhll_h1_date", pd.NaT),
                    "lhll_l2_date": signal.get("lhll_l2_date", pd.NaT),
                }
            )

        invested = shares * float(bar["close"])
        equity = cash + invested
        curve_rows.append(
            {
                "date": date,
                "variant": "combined_%s" % sizing_mode,
                "sizing_mode": sizing_mode,
                "contribution": contribution,
                "buy_amount": day_buy_amount,
                "signal_occurrences": day_signal_count,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(curve_rows), pd.DataFrame(event_rows)


def summarize_combined(
    ticker: str,
    touch_mode: str,
    sizing_mode: str,
    curve: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_summary: dict,
    years: float,
    monthly_amount: float,
) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    buy_amounts = pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0)
    signal_count = int(len(signals))
    sliding_count = int(signals["signal_family"].astype(str).str.startswith("sliding_").sum()) if not signals.empty else 0
    lhll_count = int(signals["signal_family"].eq("monthly_lhll").sum()) if not signals.empty else 0
    signal_rate = signal_count / years if years else 0.0
    return {
        "ticker": ticker,
        "touch_mode": touch_mode,
        "sizing_mode": sizing_mode,
        "signal_count": signal_count,
        "sliding_signal_count": sliding_count,
        "lhll_signal_count": lhll_count,
        "signal_rate_per_year": signal_rate,
        "static_matched_add_amount": monthly_amount * 12.0 / signal_rate if signal_rate else math.inf,
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
        "monthly_dca_ending_equity": float(monthly_summary["ending_equity"]),
        "ending_vs_monthly_dca": ending - float(monthly_summary["ending_equity"]),
    }


def summarize_monthly_row(ticker: str, curve: pd.DataFrame) -> dict:
    summary = summarize_curve(curve, "monthly_dca_open", 0, math.nan, 0.0)
    return {
        "ticker": ticker,
        "touch_mode": "base_monthly_dca",
        "sizing_mode": "monthly_dca_open",
        "signal_count": 0,
        "sliding_signal_count": 0,
        "lhll_signal_count": 0,
        "signal_rate_per_year": 0.0,
        "static_matched_add_amount": 1_000.0,
        "total_contributed": float(summary["total_contributed"]),
        "ending_equity": float(summary["ending_equity"]),
        "net": float(summary["net"]),
        "return_on_contributions_pct": float(summary["return_on_contributions_pct"]),
        "max_dd": float(summary["max_dd"]),
        "net_over_dd": float(summary["net_over_dd"]),
        "buys": int(summary["buys"]),
        "avg_buy_amount": float(summary["avg_buy_amount"]),
        "ending_cash": float(summary["ending_cash"]),
        "deployed_contributions_pct": float(summary["deployed_contributions_pct"]),
        "avg_exposure_pct": float(summary["avg_exposure_pct"]),
        "monthly_dca_ending_equity": float(summary["ending_equity"]),
        "ending_vs_monthly_dca": 0.0,
    }


def run_ticker(
    ticker: str,
    daily: pd.DataFrame,
    monthly_amount: float,
    lookback_months: int,
    pivot_bars: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = daily.copy().sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)

    monthly = monthly_dca_open(daily, monthly_amount)
    monthly["ticker"] = ticker
    monthly["touch_mode"] = "base_monthly_dca"
    monthly["sizing_mode"] = "monthly_dca_open"
    monthly_summary = summarize_curve(monthly, "monthly_dca_open", 0, math.nan, 0.0)

    summary_rows = [summarize_monthly_row(ticker, monthly)]
    curve_parts = [monthly]
    event_parts = []
    signal_parts = []
    diagnostic_parts = []

    for touch_mode, _ in EVENT_MODES:
        signals, sliding_raw, lhll_raw, diagnostics = combined_signals(daily, touch_mode, lookback_months, pivot_bars)
        if not signals.empty:
            signals["ticker"] = ticker
            signals["touch_mode"] = touch_mode
            signal_parts.append(signals)
        if not sliding_raw.empty:
            diagnostic_parts.append(sliding_raw.assign(ticker=ticker, touch_mode=touch_mode, diagnostic_table="sliding_signals_raw"))
        if not lhll_raw.empty:
            diagnostic_parts.append(lhll_raw.assign(ticker=ticker, touch_mode=touch_mode, diagnostic_table="lhll_signals_raw"))
        if not diagnostics.empty:
            diagnostic_parts.append(diagnostics.assign(ticker=ticker, touch_mode=touch_mode))

        static_rate = len(signals) / years if years else 0.0
        for sizing_mode in SIZING_MODES:
            curve, events = simulate_combined_signal_dca(
                daily,
                signals,
                monthly_amount,
                sizing_mode,
                static_signal_rate=static_rate,
            )
            curve["ticker"] = ticker
            curve["touch_mode"] = touch_mode
            events["ticker"] = ticker
            curve_parts.append(curve)
            event_parts.append(events)
            summary_rows.append(summarize_combined(ticker, touch_mode, sizing_mode, curve, signals, monthly_summary, years, monthly_amount))

    summary = pd.DataFrame(summary_rows)
    curves = pd.concat(curve_parts, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    signals = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()
    diagnostics = pd.concat(diagnostic_parts, ignore_index=True, sort=False) if diagnostic_parts else pd.DataFrame()
    return summary, curves, events, pd.concat([signals.assign(diagnostic_table="combined_signals"), diagnostics], ignore_index=True, sort=False)


def plot_equity(curves: pd.DataFrame, ticker: str, out: Path) -> None:
    subset = curves[curves["ticker"].eq(ticker)].copy()
    if subset.empty:
        return
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = {
        ("base_monthly_dca", "monthly_dca_open"): "#111827",
        ("all_touches", "static_full_window"): "#7c3aed",
        ("new_touch_cluster", "static_full_window"): "#0f766e",
        ("first_touch_per_month", "static_full_window"): "#2563eb",
        ("first_touch_per_month", "expanding_prior_rate"): "#b45309",
    }
    labels = {
        ("base_monthly_dca", "monthly_dca_open"): "$1k/month basic DCA",
        ("all_touches", "static_full_window"): "all touches + LHLL static",
        ("new_touch_cluster", "static_full_window"): "new clusters + LHLL static",
        ("first_touch_per_month", "static_full_window"): "first/month + LHLL static",
        ("first_touch_per_month", "expanding_prior_rate"): "first/month + LHLL causal",
    }
    for (touch_mode, sizing_mode), group in subset.groupby(["touch_mode", "sizing_mode"], sort=False):
        key = (touch_mode, sizing_mode)
        if key not in colors:
            continue
        ax.plot(group["date"], group["equity"], color=colors[key], linewidth=1.25, label=labels[key])
    ax.set_title("%s combined 2-month-low touch + monthly LHLL DCA" % ticker)
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


def table_line(row: pd.Series) -> str:
    return (
        "| %s | %s | %s | %d | %d | %d | %.2f | %s | %d | %s | %.1f%% | %s | %s | %.2f |"
        % (
            row["ticker"],
            row["touch_mode"],
            row["sizing_mode"],
            int(row["signal_count"]),
            int(row["sliding_signal_count"]),
            int(row["lhll_signal_count"]),
            float(row["signal_rate_per_year"]),
            money(float(row["static_matched_add_amount"])),
            int(row["buys"]),
            money(float(row["ending_equity"])),
            float(row["deployed_contributions_pct"]),
            money(float(row["ending_vs_monthly_dca"])),
            money(float(row["max_dd"])),
            float(row["net_over_dd"]),
        )
    )


def write_report(
    out_dir: Path,
    daily_by_ticker: dict[str, pd.DataFrame],
    summary: pd.DataFrame,
    lookback_months: int,
    pivot_bars: int,
    monthly_amount: float,
) -> None:
    ranked = summary[summary["touch_mode"].ne("base_monthly_dca")].sort_values(["ticker", "ending_equity"], ascending=[True, False])
    dca = summary[summary["touch_mode"].eq("base_monthly_dca")].sort_values("ticker")
    literal = summary[
        summary["touch_mode"].eq("all_touches") & summary["sizing_mode"].eq("static_full_window")
    ].sort_values("ticker")
    best = ranked.groupby("ticker", as_index=False).head(1)
    first_month = summary[
        summary["touch_mode"].eq("first_touch_per_month") & summary["sizing_mode"].isin(["static_full_window", "expanding_prior_rate"])
    ].sort_values(["ticker", "sizing_mode"])

    window = " / ".join(
        "%s %s to %s"
        % (
            ticker,
            df["date"].min().date().isoformat(),
            df["date"].max().date().isoformat(),
        )
        for ticker, df in daily_by_ticker.items()
    )
    lines = [
        "# GOOGL vs QQQ Combined 2-Month-Low + LHLL DCA Study",
        "",
        "Data: Yahoo adjusted daily OHLCV. Primary comparison uses the common GOOGL/QQQ window.",
        "",
        "Window: **%s**." % window,
        "",
        "Monthly cashflow: **%s/month**. Basic DCA buys the first trading-day open." % money(monthly_amount),
        "",
        "Combined signal rule:",
        "",
        "- 2-month-low touch: daily low touches the prior **%d calendar months** adjusted low, excluding the current day." % lookback_months,
        "- Monthly LHLL: confirmed monthly **low -> high -> lower low** with **%d left / %d right** pivot confirmation; buy on the next available daily open." % (pivot_bars, pivot_bars),
        "- Every occurrence from either family counts as one expected signal. Same-day overlaps count twice.",
        "- Matched add size = `12 months of DCA budget / expected combined signals per year`, capped by available cash.",
        "- No year-end catch-up, fees, taxes, slippage, or cash interest.",
        "",
        "## Basic DCA Baselines",
        "",
        "| Ticker | Total Contributed | Ending Equity | Net | Max DD | Net/DD |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in dca.iterrows():
        lines.append(
            "| %s | %s | %s | %s | %s | %.2f |"
            % (
                row["ticker"],
                money(float(row["total_contributed"])),
                money(float(row["ending_equity"])),
                money(float(row["net"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )

    lines.extend(
        [
            "",
            "## Best Combined Rows Per Ticker",
            "",
            "| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in best.iterrows():
        lines.append(table_line(row))

    lines.extend(
        [
            "",
            "## Literal Every-Touch + LHLL Rows",
            "",
            "These are the rows closest to the phrase \"each occurrence\" for the 2-month-low side: every daily touch plus every LHLL signal.",
            "",
            "| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in literal.iterrows():
        lines.append(table_line(row))

    lines.extend(
        [
            "",
            "## Operational First-Touch-Per-Month Rows",
            "",
            "These keep the 2-month-low side from firing repeatedly during the same drawdown month.",
            "",
            "| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in first_month.iterrows():
        lines.append(table_line(row))

    lines.extend(
        [
            "",
            "## Full Leaderboard",
            "",
            "| Ticker | Touch Mode | Sizing | Total Signals | 2m Touches | LHLL | Signals/Yr | Static Matched Add | Buys | Ending Equity | Deployed | vs Basic DCA | Max DD | Net/DD |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in ranked.iterrows():
        lines.append(table_line(row))

    lines.extend(["", "## Read", ""])
    for ticker in sorted(summary["ticker"].unique()):
        ticker_dca = dca[dca["ticker"].eq(ticker)].iloc[0]
        ticker_best = best[best["ticker"].eq(ticker)].iloc[0]
        lines.append(
            "- **%s:** basic DCA ends at **%s**. Best combined row is **%s / %s** at **%s**, which is **%s** versus basic DCA."
            % (
                ticker,
                money(float(ticker_dca["ending_equity"])),
                ticker_best["touch_mode"],
                ticker_best["sizing_mode"],
                money(float(ticker_best["ending_equity"])),
                money(float(ticker_best["ending_vs_monthly_dca"])),
            )
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
        ]
    )
    for ticker in sorted(summary["ticker"].unique()):
        slug = ticker_slug(ticker)
        lines.append("- %s equity comparison: [`charts/%s_equity.png`](charts/%s_equity.png)" % (ticker, slug, slug))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `curves.csv`",
            "- `events.csv`",
            "- `signals_and_diagnostics.csv`",
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

    summary_parts = []
    curve_parts = []
    event_parts = []
    diagnostic_parts = []
    for ticker, daily in daily_by_ticker.items():
        summary, curves, events, diagnostics = run_ticker(
            ticker,
            daily,
            args.monthly_amount,
            args.lookback_months,
            args.pivot_bars,
        )
        summary_parts.append(summary)
        curve_parts.append(curves)
        event_parts.append(events)
        diagnostic_parts.append(diagnostics)
        plot_equity(curves, ticker, out_dir / "charts" / ("%s_equity.png" % ticker_slug(ticker)))

    summary = pd.concat(summary_parts, ignore_index=True)
    curves = pd.concat(curve_parts, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    diagnostics = pd.concat(diagnostic_parts, ignore_index=True, sort=False) if diagnostic_parts else pd.DataFrame()

    summary.to_csv(out_dir / "summary.csv", index=False)
    curves.to_csv(out_dir / "curves.csv", index=False)
    events.to_csv(out_dir / "events.csv", index=False)
    diagnostics.to_csv(out_dir / "signals_and_diagnostics.csv", index=False)
    write_report(out_dir, daily_by_ticker, summary, args.lookback_months, args.pivot_bars, args.monthly_amount)
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
