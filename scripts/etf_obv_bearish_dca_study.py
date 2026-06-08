#!/usr/bin/env python3
"""ETF OBV bearish-cross DCA study for QQQ/SPY/SHOP.

The study compares blind monthly DCA to buying only when OBV crosses bearish.
Signal-buy sizes are calibrated from observed bearish-cross frequency so the
signal strategy attempts to deploy the same monthly contribution budget.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from qqq_yearly_orb_study import load_adjusted_daily


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_spy_shop_obv_bearish_dca_study"
DEFAULT_START = "2015-06-01"


def money(value: float, digits: int = 0) -> str:
    if pd.isna(value):
        return ""
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.%df" % digits))


def pct(value: float) -> str:
    if pd.isna(value):
        return ""
    return "%.2f%%" % value


def default_completed_end(today: dt.date | None = None) -> str:
    day = (today or dt.date.today()) - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day.isoformat()


def max_drawdown(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    return float((vals - vals.cummax()).min())


def add_obv(df: pd.DataFrame, obv_ma: int) -> pd.DataFrame:
    out = df.copy().sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    direction = np.sign(close.diff()).fillna(0.0)
    out["obv"] = (direction * volume).cumsum()
    out["obv_ma"] = out["obv"].rolling(obv_ma, min_periods=obv_ma).mean()
    out["obv_above_ma"] = out["obv"] > out["obv_ma"]
    prev_above = out["obv_above_ma"].shift(1).fillna(False)
    out["obv_bear_cross"] = (~out["obv_above_ma"]) & prev_above & out["obv_ma"].notna()
    out["obv_bull_cross"] = out["obv_above_ma"] & (~prev_above) & out["obv_ma"].notna()
    return out


def first_trading_day_each_month(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily[["date"]].copy()
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def summarize_equity(equity: pd.DataFrame, variant: str) -> dict:
    end_equity = float(equity.iloc[-1]["equity"]) if not equity.empty else 0.0
    total_contributed = float(equity.iloc[-1]["total_contributed"]) if not equity.empty else 0.0
    net = end_equity - total_contributed
    dd = max_drawdown(equity["equity"]) if not equity.empty else 0.0
    invested_value = float(equity.iloc[-1]["invested_value"]) if not equity.empty else 0.0
    cash = float(equity.iloc[-1]["cash"]) if not equity.empty else 0.0
    buys = int(pd.to_numeric(equity["buy_amount"], errors="coerce").fillna(0.0).gt(0).sum()) if not equity.empty else 0
    years = max((pd.Timestamp(equity.iloc[-1]["date"]) - pd.Timestamp(equity.iloc[0]["date"])).days / 365.25, 1e-9) if len(equity) > 1 else 1e-9
    return {
        "variant": variant,
        "start": pd.Timestamp(equity.iloc[0]["date"]).date().isoformat() if not equity.empty else "",
        "end": pd.Timestamp(equity.iloc[-1]["date"]).date().isoformat() if not equity.empty else "",
        "total_contributed": total_contributed,
        "ending_equity": end_equity,
        "net": net,
        "return_on_contributions_pct": net / total_contributed * 100.0 if total_contributed else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "ending_cash": cash,
        "ending_invested_value": invested_value,
        "ending_cash_pct_of_contrib": cash / total_contributed * 100.0 if total_contributed else math.nan,
        "avg_exposure_pct": float(pd.to_numeric(equity["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0) if not equity.empty else 0.0,
        "buys": buys,
        "buys_per_year": buys / years,
        "avg_buy_amount": float(equity.loc[pd.to_numeric(equity["buy_amount"], errors="coerce").fillna(0.0) > 0, "buy_amount"].mean()) if buys else 0.0,
    }


def monthly_dca(daily: pd.DataFrame, monthly_amount: float) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
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
            contributed += contribution
            cash += contribution
            buy_amount = cash
            shares += buy_amount / close
            cash = 0.0
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "monthly_blind_dca",
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


def static_signal_amount(daily: pd.DataFrame, monthly_amount: float) -> tuple[float, float]:
    signals = int(daily["obv_bear_cross"].sum())
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    signals_per_year = signals / years
    add_amount = monthly_amount * 12.0 / signals_per_year if signals_per_year else math.inf
    return signals_per_year, add_amount


def rolling_expected_crosses(
    signal_dates: list[pd.Timestamp],
    current_date: pd.Timestamp,
    lookback_years: float,
) -> float:
    start = current_date - pd.Timedelta(days=int(round(365.25 * lookback_years)))
    count = sum(1 for date in signal_dates if start <= date < current_date)
    return max(count / lookback_years, 1.0)


def signal_dca(
    daily: pd.DataFrame,
    monthly_amount: float,
    variant: str,
    static_add_amount: float | None = None,
    lookback_years: float | None = None,
) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    signal_dates: list[pd.Timestamp] = []
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        contribution = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        buy_amount = 0.0
        expected_crosses = math.nan
        target_add_amount = math.nan
        if bool(bar["obv_bear_cross"]):
            if static_add_amount is not None:
                target_add_amount = static_add_amount
            elif lookback_years is not None:
                expected_crosses = rolling_expected_crosses(signal_dates, date, lookback_years)
                target_add_amount = monthly_amount * 12.0 / expected_crosses
            else:
                raise ValueError("signal_dca needs static_add_amount or lookback_years")
            buy_amount = min(cash, target_add_amount)
            if buy_amount > 0:
                shares += buy_amount / close
                cash -= buy_amount
            signal_dates.append(date)
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": variant,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "target_add_amount": target_add_amount,
                "expected_crosses_per_year": expected_crosses,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def signal_yearly_counts(daily: pd.DataFrame) -> pd.DataFrame:
    sig = daily[daily["obv_bear_cross"]].copy()
    if sig.empty:
        return pd.DataFrame(columns=["ticker", "year", "bear_crosses"])
    sig["year"] = sig["date"].dt.year
    return sig.groupby("year", as_index=False).size().rename(columns={"size": "bear_crosses"})


def plot_equity(ticker: str, curves: dict[str, pd.DataFrame], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, df in curves.items():
        ax.plot(df["date"], df["equity"], label=label, linewidth=1.6)
    ax.set_title(f"{ticker} monthly DCA vs OBV bearish-cross DCA")
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left")
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_obv(ticker: str, daily: pd.DataFrame, out_path: Path) -> None:
    signals = daily[daily["obv_bear_cross"]]
    fig, (ax_price, ax_obv) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[2, 1])
    ax_price.plot(daily["date"], daily["close"], color="#1f2937", linewidth=1.2)
    ax_price.scatter(signals["date"], signals["close"], color="#dc2626", s=20, label="OBV bear cross")
    ax_price.set_title(f"{ticker} price with OBV bearish-cross buys")
    ax_price.set_ylabel("Adj close")
    ax_price.grid(True, alpha=0.25)
    ax_price.legend(loc="upper left")
    ax_obv.plot(daily["date"], daily["obv"], color="#2563eb", linewidth=1.0, label="OBV")
    ax_obv.plot(daily["date"], daily["obv_ma"], color="#f97316", linewidth=1.0, label="OBV SMA")
    ax_obv.scatter(signals["date"], signals["obv"], color="#dc2626", s=16)
    ax_obv.set_ylabel("OBV")
    ax_obv.grid(True, alpha=0.25)
    ax_obv.legend(loc="upper left")
    ax_obv.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax_obv.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ma_sweep(ticker: str, best_rows: pd.DataFrame, out_path: Path) -> None:
    work = best_rows[best_rows["ticker"].eq(ticker)].sort_values("obv_ma")
    if work.empty:
        return
    fig, ax_freq = plt.subplots(figsize=(12, 6))
    ax_freq.plot(
        work["obv_ma"],
        work["observed_bear_crosses_per_year"],
        color="#dc2626",
        marker="o",
        linewidth=1.8,
        label="Bear crosses/year",
    )
    ax_freq.axhline(12.0, color="#9ca3af", linestyle="--", linewidth=1.0, label="Monthly cadence")
    ax_freq.axhline(5.0, color="#6b7280", linestyle=":", linewidth=1.0, label="5/year target")
    ax_freq.set_xlabel("OBV SMA length")
    ax_freq.set_ylabel("Bearish crosses / year")
    ax_freq.grid(True, alpha=0.25)

    ax_add = ax_freq.twinx()
    ax_add.plot(
        work["obv_ma"],
        work["static_matched_add_amount"],
        color="#2563eb",
        marker="s",
        linewidth=1.6,
        label="Static matched add",
    )
    ax_add.set_ylabel("Matched buy amount ($)")

    handles_1, labels_1 = ax_freq.get_legend_handles_labels()
    handles_2, labels_2 = ax_add.get_legend_handles_labels()
    ax_freq.legend(handles_1 + handles_2, labels_1 + labels_2, loc="upper right")
    ax_freq.set_title(f"{ticker} OBV bearish-cross frequency by SMA length")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def choose_best_match(summary: pd.DataFrame) -> pd.Series:
    candidates = summary[summary["variant"].ne("monthly_blind_dca")].copy()
    candidates["deployment_score"] = candidates["ending_cash_pct_of_contrib"].abs()
    candidates["exposure_gap"] = (candidates["avg_exposure_pct"] - float(summary[summary["variant"].eq("monthly_blind_dca")]["avg_exposure_pct"].iloc[0])).abs()
    return candidates.sort_values(["deployment_score", "exposure_gap", "return_on_contributions_pct"], ascending=[True, True, False]).iloc[0]


def run_ticker(
    ticker: str,
    start: str,
    end: str,
    monthly_amount: float,
    obv_ma: int,
    lookbacks: Iterable[float],
    refresh: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = load_adjusted_daily(ticker, start, end, ROOT / "data" / "benchmarks", refresh=refresh)
    daily = add_obv(daily, obv_ma)
    monthly = monthly_dca(daily, monthly_amount)
    signals_per_year, add_amount = static_signal_amount(daily, monthly_amount)
    curves: dict[str, pd.DataFrame] = {
        "monthly_blind_dca": monthly,
        "obv_bear_static_full_window": signal_dca(
            daily,
            monthly_amount,
            "obv_bear_static_full_window",
            static_add_amount=add_amount,
        ),
    }
    for lookback in lookbacks:
        label = "obv_bear_rolling_%gy" % lookback
        curves[label] = signal_dca(daily, monthly_amount, label, lookback_years=lookback)

    summary_rows = []
    for label, curve in curves.items():
        item = summarize_equity(curve, label)
        item["ticker"] = ticker
        item["obv_ma"] = obv_ma
        item["bear_crosses"] = int(daily["obv_bear_cross"].sum())
        item["observed_bear_crosses_per_year"] = signals_per_year
        item["static_matched_add_amount"] = add_amount
        summary_rows.append(item)
    summary = pd.DataFrame(summary_rows)
    best = choose_best_match(summary)
    summary["is_best_deployment_match"] = summary["variant"].eq(best["variant"])

    daily_parts = []
    for label, curve in curves.items():
        out = curve.copy()
        out["ticker"] = ticker
        daily_parts.append(out)
    all_daily = pd.concat(daily_parts, ignore_index=True)

    counts = signal_yearly_counts(daily)
    counts["ticker"] = ticker
    return daily, summary, all_daily, counts, curves


def write_report(
    summaries: pd.DataFrame,
    counts: pd.DataFrame,
    monthly_amount: float,
    start: str,
    end: str,
    obv_ma: int,
    lookbacks: Iterable[float],
) -> None:
    lines = [
        "# QQQ / SPY / SHOP OBV Bearish-Cross DCA Study",
        "",
        "Rule: calculate daily OBV from adjusted close direction and raw Yahoo volume, then buy only when OBV crosses below its %d-day SMA." % obv_ma,
        "",
        "Comparison model:",
        "",
        "- Blind monthly DCA buys `%s` on the first trading day of each month." % money(monthly_amount),
        "- OBV bearish-cross DCA receives the same monthly contribution, holds it as cash, and buys only on bearish OBV crosses.",
        "- `static_full_window` uses the observed bearish-cross frequency over the study window to size each signal buy: annual monthly budget divided by bearish crosses per year.",
        "- Rolling variants estimate bearish-cross frequency from prior 1y/2y/3y/5y/10y lookbacks and cap purchases at available cash.",
        "- No sells, no fees, no cash interest, no optimization of OBV length.",
        "",
        "Window: **%s through %s**. Monthly contribution: **%s**." % (start, end, money(monthly_amount)),
        "",
        "## Frequency And Suggested Adds",
        "",
        "| Ticker | Bear Crosses | Crosses / Year | Static Add To Match $12k/Yr | Best Deployment Variant | Ending Cash | Ending Cash % |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for ticker, group in summaries.groupby("ticker", sort=False):
        monthly = group[group["variant"].eq("monthly_blind_dca")].iloc[0]
        best = group[group["is_best_deployment_match"]].iloc[0]
        lines.append(
            "| %s | %d | %.2f | %s | %s | %s | %.2f%% |"
            % (
                ticker,
                int(monthly["bear_crosses"]),
                float(monthly["observed_bear_crosses_per_year"]),
                money(float(monthly["static_matched_add_amount"])),
                str(best["variant"]),
                money(float(best["ending_cash"])),
                float(best["ending_cash_pct_of_contrib"]),
            )
        )

    lines.extend(
        [
            "",
            "## Performance Summary",
            "",
            "| Ticker | Variant | Buys | Avg Buy | Total Contributed | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    order = ["monthly_blind_dca", "obv_bear_static_full_window"] + ["obv_bear_rolling_%gy" % lb for lb in lookbacks]
    for ticker, group in summaries.groupby("ticker", sort=False):
        for variant in order:
            row = group[group["variant"].eq(variant)]
            if row.empty:
                continue
            r = row.iloc[0]
            label = variant + (" (best match)" if bool(r["is_best_deployment_match"]) else "")
            lines.append(
                "| %s | %s | %d | %s | %s | %s | %s | %.2f%% | %s | %.2f | %.1f%% | %s |"
                % (
                    ticker,
                    label,
                    int(r["buys"]),
                    money(float(r["avg_buy_amount"])),
                    money(float(r["total_contributed"])),
                    money(float(r["ending_equity"])),
                    money(float(r["net"])),
                    float(r["return_on_contributions_pct"]),
                    money(float(r["max_dd"])),
                    float(r["net_over_dd"]),
                    float(r["avg_exposure_pct"]),
                    money(float(r["ending_cash"])),
                )
            )

    lines.extend(
        [
            "",
            "## Read",
            "",
        ]
    )
    for ticker, group in summaries.groupby("ticker", sort=False):
        monthly = group[group["variant"].eq("monthly_blind_dca")].iloc[0]
        static = group[group["variant"].eq("obv_bear_static_full_window")].iloc[0]
        best_perf = group.sort_values("ending_equity", ascending=False).iloc[0]
        best_match = group[group["is_best_deployment_match"]].iloc[0]
        lines.append(
            "- **%s:** bearish crosses average %.2f/year, implying a static matched add of %s per signal versus %s monthly. Best deployment match is `%s`; best ending equity is `%s` at %s."
            % (
                ticker,
                float(monthly["observed_bear_crosses_per_year"]),
                money(float(monthly["static_matched_add_amount"])),
                money(monthly_amount),
                best_match["variant"],
                best_perf["variant"],
                money(float(best_perf["ending_equity"])),
            )
        )
        lines.append(
            "  Monthly DCA ending equity/net: %s / %s; static OBV ending equity/net: %s / %s."
            % (
                money(float(monthly["ending_equity"])),
                money(float(monthly["net"])),
                money(float(static["ending_equity"])),
                money(float(static["net"])),
            )
        )

    lines.extend(
        [
            "",
            "## Charts",
            "",
        ]
    )
    for ticker in summaries["ticker"].drop_duplicates():
        lines.append("- %s equity curves: [`charts/%s_equity.png`](charts/%s_equity.png); OBV signals: [`charts/%s_obv.png`](charts/%s_obv.png)" % (ticker, ticker.lower(), ticker.lower(), ticker.lower(), ticker.lower()))

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `summary.csv`",
            "- `daily_equity.csv`",
            "- `bear_cross_counts_by_year.csv`",
            "- `signals.csv`",
        ]
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_ma_sweep_best_rows(summaries: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (ticker, obv_ma), group in summaries.groupby(["ticker", "obv_ma"], sort=False):
        monthly = group[group["variant"].eq("monthly_blind_dca")].iloc[0]
        obv_rows = group[group["variant"].ne("monthly_blind_dca")].copy()
        best_equity = obv_rows.sort_values("ending_equity", ascending=False).iloc[0]
        best_match = group[group["is_best_deployment_match"]].iloc[0]
        closest_to_monthly = obv_rows.iloc[
            (obv_rows["ending_equity"] - monthly["ending_equity"]).abs().argsort()
        ].iloc[0]
        rows.append(
            {
                "ticker": ticker,
                "obv_ma": int(obv_ma),
                "bear_crosses": int(monthly["bear_crosses"]),
                "observed_bear_crosses_per_year": float(monthly["observed_bear_crosses_per_year"]),
                "static_matched_add_amount": float(monthly["static_matched_add_amount"]),
                "monthly_ending_equity": float(monthly["ending_equity"]),
                "monthly_net": float(monthly["net"]),
                "monthly_max_dd": float(monthly["max_dd"]),
                "best_obv_variant": str(best_equity["variant"]),
                "best_obv_ending_equity": float(best_equity["ending_equity"]),
                "best_obv_net": float(best_equity["net"]),
                "best_obv_max_dd": float(best_equity["max_dd"]),
                "best_obv_net_over_dd": float(best_equity["net_over_dd"]),
                "best_obv_avg_buy_amount": float(best_equity["avg_buy_amount"]),
                "best_obv_buys": int(best_equity["buys"]),
                "best_obv_vs_monthly": float(best_equity["ending_equity"] - monthly["ending_equity"]),
                "best_deployment_variant": str(best_match["variant"]),
                "best_deployment_ending_cash": float(best_match["ending_cash"]),
                "best_deployment_ending_cash_pct": float(best_match["ending_cash_pct_of_contrib"]),
                "closest_to_monthly_variant": str(closest_to_monthly["variant"]),
            }
        )
    return pd.DataFrame(rows)


def write_ma_sweep_report(
    best_rows: pd.DataFrame,
    monthly_amount: float,
    start: str,
    end: str,
    obv_mas: Iterable[int],
    lookbacks: Iterable[float],
) -> None:
    lines = [
        "# QQQ / SPY / SHOP Slower OBV MA Sweep",
        "",
        "Purpose: test slower OBV moving averages after the 20-day OBV bearish cross fired too often.",
        "",
        "Method: each ticker contributes `%s` per month, then signal variants buy only when daily OBV crosses below the selected OBV SMA. The static add size is calibrated as `$12k / observed bearish crosses per year`; rolling variants use prior 1y/2y/3y/5y/10y signal frequency and cap buys at available cash." % money(monthly_amount),
        "",
        "Window: **%s through %s**. Tested OBV SMA lengths: **%s**. Rolling lookbacks: **%s years**."
        % (
            start,
            end,
            ", ".join(str(int(x)) for x in obv_mas),
            ", ".join("%g" % x for x in lookbacks),
        ),
        "",
        "## Frequency Sweep",
        "",
        "| Ticker | OBV SMA | Bear Crosses | Crosses / Year | Static Add | Best OBV Variant | Best OBV Ending Equity | vs Monthly DCA | Best OBV Max DD |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for _, row in best_rows.sort_values(["ticker", "obv_ma"]).iterrows():
        lines.append(
            "| %s | %d | %d | %.2f | %s | %s | %s | %s | %s |"
            % (
                row["ticker"],
                int(row["obv_ma"]),
                int(row["bear_crosses"]),
                float(row["observed_bear_crosses_per_year"]),
                money(float(row["static_matched_add_amount"])),
                row["best_obv_variant"],
                money(float(row["best_obv_ending_equity"])),
                money(float(row["best_obv_vs_monthly"])),
                money(float(row["best_obv_max_dd"])),
            )
        )

    lines.extend(["", "## Read", ""])
    for ticker, group in best_rows.groupby("ticker", sort=False):
        monthly_end = float(group.iloc[0]["monthly_ending_equity"])
        best_perf = group.sort_values("best_obv_ending_equity", ascending=False).iloc[0]
        rarest = group.sort_values("observed_bear_crosses_per_year").iloc[0]
        closest_5 = group.assign(
            abs_gap=(group["observed_bear_crosses_per_year"] - 5.0).abs()
        ).sort_values("abs_gap").iloc[0]
        lines.append(
            "- **%s:** best OBV timing is SMA %d (`%s`) at %s, versus monthly DCA at %s. It is %s relative to monthly."
            % (
                ticker,
                int(best_perf["obv_ma"]),
                best_perf["best_obv_variant"],
                money(float(best_perf["best_obv_ending_equity"])),
                money(monthly_end),
                money(float(best_perf["best_obv_vs_monthly"])),
            )
        )
        lines.append(
            "  Rarest tested signal is SMA %d at %.2f crosses/year with a %s static matched add. Closest tested cadence to 5/year is SMA %d at %.2f crosses/year with a %s add."
            % (
                int(rarest["obv_ma"]),
                float(rarest["observed_bear_crosses_per_year"]),
                money(float(rarest["static_matched_add_amount"])),
                int(closest_5["obv_ma"]),
                float(closest_5["observed_bear_crosses_per_year"]),
                money(float(closest_5["static_matched_add_amount"])),
            )
        )

    lines.extend(
        [
            "",
            "## Charts",
            "",
        ]
    )
    for ticker in best_rows["ticker"].drop_duplicates():
        lines.append(
            "- %s frequency/add sweep: [`charts/%s_ma_sweep.png`](charts/%s_ma_sweep.png)"
            % (ticker, ticker.lower(), ticker.lower())
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `ma_sweep_best_by_ma.csv`",
            "- `ma_sweep_summary.csv`",
            "- `ma_sweep_counts_by_year.csv`",
        ]
    )
    (OUT_DIR / "MA_SWEEP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ma_sweep(
    tickers: Iterable[str],
    start: str,
    end: str,
    monthly_amount: float,
    obv_mas: Iterable[int],
    lookbacks: Iterable[float],
    refresh: bool,
) -> None:
    chart_dir = OUT_DIR / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    counts_parts = []
    for ticker in tickers:
        for obv_ma in obv_mas:
            daily, summary, _all_daily, counts, _curves = run_ticker(
                ticker=ticker,
                start=start,
                end=end,
                monthly_amount=monthly_amount,
                obv_ma=obv_ma,
                lookbacks=lookbacks,
                refresh=refresh,
            )
            summaries.append(summary)
            counts = counts.copy()
            counts["obv_ma"] = obv_ma
            counts_parts.append(counts)
    summary_df = pd.concat(summaries, ignore_index=True)
    best_rows = build_ma_sweep_best_rows(summary_df)
    summary_df.to_csv(OUT_DIR / "ma_sweep_summary.csv", index=False)
    best_rows.to_csv(OUT_DIR / "ma_sweep_best_by_ma.csv", index=False)
    counts_df = pd.concat(counts_parts, ignore_index=True) if counts_parts else pd.DataFrame()
    counts_df.to_csv(OUT_DIR / "ma_sweep_counts_by_year.csv", index=False)
    for ticker in best_rows["ticker"].drop_duplicates():
        plot_ma_sweep(ticker, best_rows, chart_dir / ("%s_ma_sweep.png" % ticker.lower()))
    write_ma_sweep_report(best_rows, monthly_amount, start, end, obv_mas, lookbacks)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", nargs="+", default=["QQQ", "SPY", "SHOP"])
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=default_completed_end())
    ap.add_argument("--monthly-amount", type=float, default=1000.0)
    ap.add_argument("--obv-ma", type=int, default=20)
    ap.add_argument("--obv-ma-sweep", type=int, nargs="+", default=[20, 50, 100, 150, 200, 252, 504])
    ap.add_argument("--skip-sweep", action="store_true")
    ap.add_argument("--lookbacks", type=float, nargs="+", default=[1.0, 2.0, 3.0, 5.0, 10.0])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chart_dir = OUT_DIR / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    daily_parts = []
    counts_parts = []
    signal_parts = []
    for ticker in [t.upper() for t in args.tickers]:
        daily, summary, all_daily, counts, curves = run_ticker(
            ticker=ticker,
            start=args.start,
            end=args.end,
            monthly_amount=args.monthly_amount,
            obv_ma=args.obv_ma,
            lookbacks=args.lookbacks,
            refresh=args.refresh,
        )
        summaries.append(summary)
        daily_parts.append(all_daily)
        counts_parts.append(counts)
        signals = daily[daily["obv_bear_cross"]][["date", "close", "obv", "obv_ma"]].copy()
        signals["ticker"] = ticker
        signals["signal"] = "obv_bear_cross"
        signal_parts.append(signals)
        best_variant = str(summary[summary["is_best_deployment_match"]].iloc[0]["variant"])
        plot_equity(
            ticker,
            {
                "monthly_blind_dca": curves["monthly_blind_dca"],
                "obv_static": curves["obv_bear_static_full_window"],
                best_variant: curves[best_variant],
            },
            chart_dir / ("%s_equity.png" % ticker.lower()),
        )
        plot_obv(ticker, daily, chart_dir / ("%s_obv.png" % ticker.lower()))

    summary_df = pd.concat(summaries, ignore_index=True)
    daily_df = pd.concat(daily_parts, ignore_index=True)
    counts_df = pd.concat(counts_parts, ignore_index=True) if counts_parts else pd.DataFrame()
    signals_df = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()

    summary_df.to_csv(OUT_DIR / "summary.csv", index=False)
    daily_df.to_csv(OUT_DIR / "daily_equity.csv", index=False)
    counts_df.to_csv(OUT_DIR / "bear_cross_counts_by_year.csv", index=False)
    signals_df.to_csv(OUT_DIR / "signals.csv", index=False)
    write_report(summary_df, counts_df, args.monthly_amount, args.start, args.end, args.obv_ma, args.lookbacks)
    if not args.skip_sweep:
        run_ma_sweep(
            tickers=[t.upper() for t in args.tickers],
            start=args.start,
            end=args.end,
            monthly_amount=args.monthly_amount,
            obv_mas=args.obv_ma_sweep,
            lookbacks=args.lookbacks,
            refresh=args.refresh,
        )
    print("Wrote %s" % (OUT_DIR / "INDEX.md"))
    if not args.skip_sweep:
        print("Wrote %s" % (OUT_DIR / "MA_SWEEP.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
