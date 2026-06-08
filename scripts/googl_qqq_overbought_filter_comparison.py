#!/usr/bin/env python3
"""Compare RSI, OBV, and ATR overbought deferral filters for ETF DCA."""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from googl_qqq_combined_lhll_rsi_deferral_study import add_rsi_state
from qqq_market_structure_dca_study import first_trading_day_each_month, money, monthly_dca_open, summarize_curve
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_qqq_overbought_filter_comparison"
DEFAULT_START = "2004-08-19"
DEFAULT_TICKERS = ["GOOGL", "QQQ"]
DEFAULT_MONTHLY_AMOUNT = 1000.0
MAX_REDEPLOY_MULTIPLE = 2.0


def pct(value: float) -> str:
    if pd.isna(value):
        return ""
    return "%.1f%%" % value


def add_daily_obv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    direction = np.sign(close.diff()).fillna(0.0)
    out["obv"] = (direction * volume).cumsum()
    return out


def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    out = df.copy().sort_values("date").reset_index(drop=True)
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr%d" % length] = tr.ewm(alpha=1.0 / float(length), adjust=False, min_periods=length).mean()
    return out


def map_prior_state(daily: pd.DataFrame, state: pd.DataFrame, value_col: str, overbought_col: str) -> pd.DataFrame:
    base = daily.copy().sort_values("date").reset_index(drop=True)
    base["date"] = pd.to_datetime(base["date"])
    state = state[["date", value_col, overbought_col]].copy().sort_values("date")
    state["date"] = pd.to_datetime(state["date"])
    mapped = pd.merge_asof(
        base[["date"]],
        state,
        on="date",
        direction="backward",
        allow_exact_matches=False,
    )
    out = base.merge(mapped, on="date", how="left")
    out["filter_value"] = pd.to_numeric(out[value_col], errors="coerce")
    out["overbought"] = out[overbought_col].fillna(False).astype(bool)
    return out


def rsi_filter(daily: pd.DataFrame, timeframe: str, threshold: float) -> pd.DataFrame:
    out = add_rsi_state(daily, timeframe, threshold, rsi_length=14, smooth=14)
    out["filter_value"] = pd.to_numeric(out["state_rsi_smooth"], errors="coerce")
    return out


def obv_z_filter(daily: pd.DataFrame, ma: int, threshold: float) -> pd.DataFrame:
    state = add_daily_obv(daily)
    state["obv_ma"] = state["obv"].rolling(ma, min_periods=ma).mean()
    state["obv_std"] = state["obv"].rolling(ma, min_periods=ma).std(ddof=0)
    state["obv_z"] = (state["obv"] - state["obv_ma"]) / state["obv_std"].replace(0.0, np.nan)
    state["obv_z_overbought"] = pd.to_numeric(state["obv_z"], errors="coerce").ge(threshold).fillna(False)
    return map_prior_state(daily, state, "obv_z", "obv_z_overbought")


def obv_above_ma_filter(daily: pd.DataFrame, ma: int) -> pd.DataFrame:
    state = add_daily_obv(daily)
    state["obv_ma"] = state["obv"].rolling(ma, min_periods=ma).mean()
    state["obv_above_ma_value"] = (state["obv"] > state["obv_ma"]).astype(float)
    state["obv_above_ma_overbought"] = (state["obv"] > state["obv_ma"]) & state["obv_ma"].notna()
    return map_prior_state(daily, state, "obv_above_ma_value", "obv_above_ma_overbought")


def atr_stretch_filter(daily: pd.DataFrame, ma: int, threshold: float) -> pd.DataFrame:
    state = add_atr(daily, 14)
    close = pd.to_numeric(state["close"], errors="coerce")
    state["trend_ma"] = close.rolling(ma, min_periods=max(20, ma // 2)).mean()
    state["atr_stretch"] = (close - state["trend_ma"]) / state["atr14"].replace(0.0, np.nan)
    state["atr_stretch_overbought"] = pd.to_numeric(state["atr_stretch"], errors="coerce").ge(threshold).fillna(False)
    return map_prior_state(daily, state, "atr_stretch", "atr_stretch_overbought")


def simulate_deferral(
    daily: pd.DataFrame,
    monthly_amount: float,
    max_multiple: float,
    filter_label: str,
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
                    "filter_label": filter_label,
                    "event_type": event_type,
                    "overbought": bool(bar["overbought"]),
                    "filter_value": float(bar["filter_value"]) if pd.notna(bar["filter_value"]) else math.nan,
                    "buy_amount": buy_amount,
                    "buy_price": float(bar["open"]) if buy_amount else math.nan,
                    "cash_after": cash,
                }
            )
        invested = shares * float(bar["close"])
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": filter_label,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
                "overbought": bool(bar["overbought"]),
                "filter_value": float(bar["filter_value"]) if pd.notna(bar["filter_value"]) else math.nan,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def summarize_filter(
    ticker: str,
    filter_family: str,
    filter_label: str,
    detail: str,
    curve: pd.DataFrame,
    events: pd.DataFrame,
    baseline: dict,
    monthly_amount: float,
) -> dict:
    summary = summarize_curve(curve, filter_label, 0, math.nan, float(baseline["ending_equity"]))
    event_types = events["event_type"].astype(str) if not events.empty else pd.Series(dtype=str)
    blocked = int(event_types.eq("monthly_blocked_overbought").sum())
    allowed = int(event_types.eq("monthly_buy_allowed").sum())
    gross_saved = blocked * monthly_amount
    ending_cash = float(summary["ending_cash"])
    return {
        "ticker": ticker,
        "filter_family": filter_family,
        "filter_label": filter_label,
        "detail": detail,
        "events_blocked": blocked,
        "events_allowed": allowed,
        "gross_saved": gross_saved,
        "redeployed_est": max(gross_saved - ending_cash, 0.0),
        "ending_cash": ending_cash,
        "total_contributed": float(summary["total_contributed"]),
        "ending_equity": float(summary["ending_equity"]),
        "net": float(summary["net"]),
        "ending_vs_basic_dca": float(summary["equity_vs_monthly"]),
        "max_dd": float(summary["max_dd"]),
        "net_over_dd": float(summary["net_over_dd"]),
        "buys": int(summary["buys"]),
        "avg_buy_amount": float(summary["avg_buy_amount"]),
        "deployed_contributions_pct": float(summary["deployed_contributions_pct"]),
        "avg_exposure_pct": float(summary["avg_exposure_pct"]),
    }


def plot_best(curves: pd.DataFrame, ticker: str, out_path: Path) -> None:
    subset = curves[curves["ticker"].eq(ticker)].copy()
    if subset.empty:
        return
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = {
        "basic_dca_open": "#111827",
        "RSI monthly >=70": "#2563eb",
        "best_obv": "#0f766e",
        "best_atr": "#b45309",
    }
    labels = {
        "basic_dca_open": "$1k/month DCA",
        "RSI monthly >=70": "RSI monthly >=70 deferral",
        "best_obv": "best OBV deferral",
        "best_atr": "best ATR-stretch deferral",
    }
    for variant, group in subset.groupby("plot_variant", sort=False):
        ax.plot(group["date"], group["equity"], linewidth=1.25, color=colors.get(variant, "#6b7280"), label=labels.get(variant, variant))
    ax.set_title("%s overbought deferral filter comparison" % ticker)
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def row_line(row: pd.Series) -> str:
    return (
        "| %s | %s | %s | %s | %s | %s | %s | %d | %s | %s | %s | %d | %s | %.2f |"
        % (
            row["ticker"],
            row["filter_family"],
            row["filter_label"],
            row["detail"],
            money(float(row["ending_equity"])),
            money(float(row["ending_vs_basic_dca"])),
            money(float(row["gross_saved"])),
            int(row["events_blocked"]),
            money(float(row["redeployed_est"])),
            money(float(row["ending_cash"])),
            pct(float(row["deployed_contributions_pct"])),
            int(row["buys"]),
            money(float(row["max_dd"])),
            float(row["net_over_dd"]),
        )
    )


def write_report(
    out_dir: Path,
    baselines: pd.DataFrame,
    summary: pd.DataFrame,
    tickers: list[str],
    monthly_amount: float,
    max_multiple: float,
    start: str,
    end: str,
) -> None:
    best_family = (
        summary.sort_values(["ticker", "filter_family", "ending_equity"], ascending=[True, True, False])
        .groupby(["ticker", "filter_family"], as_index=False)
        .head(1)
    )
    top = summary.sort_values(["ticker", "ending_equity"], ascending=[True, False]).groupby("ticker", as_index=False).head(12)
    lines = [
        "# GOOGL / QQQ Overbought Deferral Filter Comparison",
        "",
        "Data: Yahoo adjusted daily OHLCV.",
        "",
        "Window: **%s through %s**." % (start, end),
        "",
        "Rule:",
        "",
        "- Start with the same `$%s/month` DCA contribution." % format(monthly_amount, ",.0f"),
        "- If the filter is overbought on the first trading day of the month, skip that buy and leave the cash idle.",
        "- Later allowed buys can spend up to **%.1fx** the normal monthly amount." % max_multiple,
        "- Daily filters are causal: the buy decision uses the prior completed daily bar. RSI weekly/monthly uses the prior completed weekly/monthly bar.",
        "",
        "Filter families:",
        "",
        "- **RSI:** smoothed RSI(14) EMA(14), same as the current RSI deferral study.",
        "- **OBV:** daily OBV z-score above its moving average, plus simple OBV-above-MA diagnostics.",
        "- **ATR:** adjusted close stretched above SMA50/SMA200 by ATR(14) units.",
        "",
        "## Baselines",
        "",
        "| Ticker | Ending Equity | Net | Max DD | Net/DD | Total Contributed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in baselines.iterrows():
        lines.append(
            "| %s | %s | %s | %s | %.2f | %s |"
            % (
                row["ticker"],
                money(float(row["ending_equity"])),
                money(float(row["net"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                money(float(row["total_contributed"])),
            )
        )
    lines.extend(
        [
            "",
            "## Best By Filter Family",
            "",
            "| Ticker | Family | Filter | Detail | Ending Equity | vs Basic DCA | Gross Saved | Blocked | Redeployed Est. | Ending Cash | Deployed | Buys | Max DD | Net/DD |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in best_family.sort_values(["ticker", "ending_equity"], ascending=[True, False]).iterrows():
        lines.append(row_line(row))
    lines.extend(
        [
            "",
            "## Top Rows",
            "",
            "| Ticker | Family | Filter | Detail | Ending Equity | vs Basic DCA | Gross Saved | Blocked | Redeployed Est. | Ending Cash | Deployed | Buys | Max DD | Net/DD |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in top.iterrows():
        lines.append(row_line(row))
    lines.extend(["", "## Read", ""])
    for ticker in tickers:
        ticker_summary = summary[summary["ticker"].eq(ticker)]
        rsi70 = ticker_summary[ticker_summary["filter_label"].eq("RSI monthly >=70")]
        best_any = ticker_summary.sort_values("ending_equity", ascending=False).iloc[0]
        best_obv = ticker_summary[ticker_summary["filter_family"].eq("OBV")].sort_values("ending_equity", ascending=False).head(1)
        best_atr = ticker_summary[ticker_summary["filter_family"].eq("ATR")].sort_values("ending_equity", ascending=False).head(1)
        if not rsi70.empty:
            row = rsi70.iloc[0]
            lines.append(
                "- **%s RSI monthly >=70:** saved **%s** across **%d** blocked months, redeployed about **%s**, left **%s** cash, and finished **%s** versus basic DCA."
                % (
                    ticker,
                    money(float(row["gross_saved"])),
                    int(row["events_blocked"]),
                    money(float(row["redeployed_est"])),
                    money(float(row["ending_cash"])),
                    money(float(row["ending_vs_basic_dca"])),
                )
            )
        if not best_obv.empty and not best_atr.empty:
            obv = best_obv.iloc[0]
            atr = best_atr.iloc[0]
            lines.append(
                "- **%s best OBV / ATR:** OBV tops at **%s** (**%s** vs basic), ATR tops at **%s** (**%s** vs basic). Overall best tested row is **%s** at **%s** (**%s** vs basic)."
                % (
                    ticker,
                    obv["filter_label"],
                    money(float(obv["ending_vs_basic_dca"])),
                    atr["filter_label"],
                    money(float(atr["ending_vs_basic_dca"])),
                    best_any["filter_label"],
                    money(float(best_any["ending_equity"])),
                    money(float(best_any["ending_vs_basic_dca"])),
                )
            )
    lines.extend(["", "## Charts", ""])
    for ticker in tickers:
        slug = ticker.lower().replace(".", "_").replace("-", "_")
        lines.append("- %s: [`charts/%s_filter_comparison.png`](charts/%s_filter_comparison.png)" % (ticker, slug, slug))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `baselines.csv`",
            "- `events.csv`",
            "- `selected_curves.csv`",
            "",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end(dt.date.today()))
    parser.add_argument("--monthly-amount", type=float, default=DEFAULT_MONTHLY_AMOUNT)
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
    common_end = min(pd.Timestamp(df["date"].max()) for df in raw_daily.values())
    daily_by_ticker = {
        ticker: df[(df["date"] >= common_start) & (df["date"] <= common_end)].copy().reset_index(drop=True)
        for ticker, df in raw_daily.items()
    }

    filter_specs = []
    for timeframe in ["daily", "weekly", "monthly"]:
        for threshold in [60.0, 65.0, 70.0, 75.0, 80.0]:
            filter_specs.append(
                {
                    "family": "RSI",
                    "label": "RSI %s >=%.0f" % (timeframe, threshold),
                    "detail": "RSI14 EMA14, prior %s bar" % timeframe,
                    "builder": lambda daily, tf=timeframe, th=threshold: rsi_filter(daily, tf, th),
                }
            )
    for ma in [50, 100, 200]:
        for threshold in [1.0, 1.5, 2.0]:
            filter_specs.append(
                {
                    "family": "OBV",
                    "label": "OBV z%d >=%.1f" % (ma, threshold),
                    "detail": "daily OBV z-score vs SMA%d" % ma,
                    "builder": lambda daily, m=ma, th=threshold: obv_z_filter(daily, m, th),
                }
            )
        filter_specs.append(
            {
                "family": "OBV",
                "label": "OBV above SMA%d" % ma,
                "detail": "daily OBV above SMA%d" % ma,
                "builder": lambda daily, m=ma: obv_above_ma_filter(daily, m),
            }
        )
    for ma in [50, 200]:
        for threshold in [2.0, 3.0, 4.0, 5.0]:
            filter_specs.append(
                {
                    "family": "ATR",
                    "label": "ATR stretch SMA%d >=%.0f" % (ma, threshold),
                    "detail": "(close - SMA%d) / ATR14" % ma,
                    "builder": lambda daily, m=ma, th=threshold: atr_stretch_filter(daily, m, th),
                }
            )

    baselines = []
    summaries = []
    event_parts = []
    selected_curves = []

    for ticker, daily in daily_by_ticker.items():
        basic = monthly_dca_open(daily, args.monthly_amount)
        base_summary = summarize_curve(basic, "basic_dca_open", 0, math.nan, 0.0)
        base_summary["ticker"] = ticker
        baselines.append(base_summary)
        basic_plot = basic.copy()
        basic_plot["ticker"] = ticker
        basic_plot["plot_variant"] = "basic_dca_open"
        selected_curves.append(basic_plot)

        curves_by_label: dict[str, pd.DataFrame] = {}
        for spec in filter_specs:
            filt_daily = spec["builder"](daily)
            curve, events = simulate_deferral(filt_daily, args.monthly_amount, args.max_multiple, spec["label"])
            summaries.append(
                summarize_filter(
                    ticker,
                    spec["family"],
                    spec["label"],
                    spec["detail"],
                    curve,
                    events,
                    base_summary,
                    args.monthly_amount,
                )
            )
            curve = curve.copy()
            curve["ticker"] = ticker
            curve["filter_label"] = spec["label"]
            curves_by_label[spec["label"]] = curve
            events = events.copy()
            events["ticker"] = ticker
            events["filter_family"] = spec["family"]
            events["detail"] = spec["detail"]
            event_parts.append(events)

        ticker_summary = pd.DataFrame([row for row in summaries if row["ticker"] == ticker])
        rsi70_label = "RSI monthly >=70"
        if rsi70_label in curves_by_label:
            rsi70_curve = curves_by_label[rsi70_label].copy()
            rsi70_curve["plot_variant"] = rsi70_label
            selected_curves.append(rsi70_curve)
        for family, plot_variant in [("OBV", "best_obv"), ("ATR", "best_atr")]:
            best = ticker_summary[ticker_summary["filter_family"].eq(family)].sort_values("ending_equity", ascending=False).head(1)
            if not best.empty:
                label = str(best.iloc[0]["filter_label"])
                curve = curves_by_label[label].copy()
                curve["plot_variant"] = plot_variant
                selected_curves.append(curve)

    baselines_df = pd.DataFrame(baselines)
    summary_df = pd.DataFrame(summaries)
    events_df = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    selected_df = pd.concat(selected_curves, ignore_index=True) if selected_curves else pd.DataFrame()

    baselines_df.to_csv(out_dir / "baselines.csv", index=False)
    summary_df.to_csv(out_dir / "summary.csv", index=False)
    events_df.to_csv(out_dir / "events.csv", index=False)
    selected_df.to_csv(out_dir / "selected_curves.csv", index=False)

    for ticker in sorted(daily_by_ticker):
        slug = ticker.lower().replace(".", "_").replace("-", "_")
        plot_best(selected_df, ticker, out_dir / "charts" / ("%s_filter_comparison.png" % slug))

    write_report(
        out_dir,
        baselines_df,
        summary_df,
        sorted(daily_by_ticker),
        args.monthly_amount,
        args.max_multiple,
        common_start.date().isoformat(),
        common_end.date().isoformat(),
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
