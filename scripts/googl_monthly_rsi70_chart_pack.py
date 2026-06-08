#!/usr/bin/env python3
"""GOOGL monthly candles with weekly/monthly smoothed RSI and DCA blocks."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from googl_qqq_overbought_filter_comparison import rsi_filter, simulate_deferral
from qqq_market_structure_monthly_pivot_dca_study import monthly_ohlcv
from qqq_market_structure_weekly_pivot_dca_study import weekly_ohlcv
from qqq_smoothed_rsi_chart import compute_rsi
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily, plot_candles


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_monthly_rsi70_chart_pack"
DEFAULT_START = "2004-08-19"
DEFAULT_MONTHLY_AMOUNT = 1000.0
MAX_REDEPLOY_MULTIPLE = 2.0
RSI_LENGTH = 14
RSI_SMOOTH = 14
THRESHOLD = 70.0


def money(value: float, digits: int = 0) -> str:
    if pd.isna(value):
        return ""
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.%df" % digits))


def simulate_window_catchup(
    daily: pd.DataFrame,
    monthly_amount: float,
    catchup_window_months: int,
    filter_label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = set(pd.to_datetime(daily[["date"]].assign(month=daily["date"].dt.to_period("M")).groupby("month")["date"].first()))
    cash = 0.0
    deferred_cash = 0.0
    shares = 0.0
    contributed = 0.0
    catchup_remaining = 0
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        contribution = 0.0
        buy_amount = 0.0
        normal_buy = 0.0
        catchup_buy = 0.0
        event_type = ""
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            if bool(bar["overbought"]):
                deferred_cash += contribution
                catchup_remaining = 0
                event_type = "monthly_blocked_overbought"
            else:
                normal_buy = contribution
                if deferred_cash > 0:
                    if catchup_remaining <= 0:
                        catchup_remaining = catchup_window_months
                    catchup_buy = min(deferred_cash, deferred_cash / float(catchup_remaining))
                    deferred_cash -= catchup_buy
                    catchup_remaining = max(catchup_remaining - 1, 0)
                    if deferred_cash <= 1e-9:
                        deferred_cash = 0.0
                        catchup_remaining = 0
                buy_amount = min(cash, normal_buy + catchup_buy)
                if buy_amount > 0:
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
                    "normal_buy": normal_buy,
                    "catchup_buy": catchup_buy,
                    "buy_price": float(bar["open"]) if buy_amount else math.nan,
                    "cash_after": cash,
                    "deferred_cash_after": deferred_cash,
                    "catchup_remaining": catchup_remaining,
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
                "normal_buy": normal_buy,
                "catchup_buy": catchup_buy,
                "cash": cash,
                "deferred_cash": deferred_cash,
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


def rsi_panel(
    ax: plt.Axes,
    rsi: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    title: str,
    line_color: str,
    marker_color: str,
    threshold: float,
) -> None:
    work = rsi[rsi["date"].between(start, end)].copy()
    ax.axhspan(threshold, 100, color="#fecaca", alpha=0.28)
    ax.axhline(threshold, color="#dc2626", linewidth=0.9, linestyle="--")
    ax.axhline(50, color="#6b7280", linewidth=0.8, linestyle=":")
    ax.axhline(30, color="#2563eb", linewidth=0.8, linestyle="--")
    ax.plot(work["date"], work["rsi_smooth"], color=line_color, linewidth=1.45, label=title)
    hot = work[pd.to_numeric(work["rsi_smooth"], errors="coerce").ge(threshold)]
    ax.scatter(hot["date"], hot["rsi_smooth"], s=28, color=marker_color, edgecolors="white", linewidths=0.45, zorder=4, label=">=%.0f" % threshold)
    ax.set_ylim(0, 100)
    ax.set_ylabel(title)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)


def draw_block_lines(axes: list[plt.Axes], events: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> None:
    blocked = events[
        events["event_type"].eq("monthly_blocked_overbought")
        & events["date"].between(start, end)
    ].copy()
    buy = events[
        events["event_type"].eq("monthly_buy_allowed")
        & events["date"].between(start, end)
        & pd.to_numeric(events["buy_amount"], errors="coerce").gt(1000.0)
    ].copy()
    block_label = "blocked DCA buy"
    catchup_label = "2x catch-up buy"
    for _, row in blocked.iterrows():
        for ax in axes:
            ax.axvline(row["date"], color="#dc2626", linewidth=0.95, alpha=0.38, label=block_label if ax is axes[0] else None)
        block_label = None
    for _, row in buy.iterrows():
        for ax in axes:
            ax.axvline(row["date"], color="#0f766e", linewidth=0.85, alpha=0.24, linestyle=":", label=catchup_label if ax is axes[0] else None)
        catchup_label = None


def draw_chart(
    title: str,
    monthly_price: pd.DataFrame,
    weekly_rsi: pd.DataFrame,
    monthly_rsi: pd.DataFrame,
    events: pd.DataFrame,
    out_path: Path,
    index_dir: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    threshold: float,
) -> dict[str, object]:
    price = monthly_price[monthly_price["date"].between(start, end)].copy()
    if price.empty:
        return {}
    chart_events = events[events["date"].between(start, end)].copy()
    blocked = chart_events[chart_events["event_type"].eq("monthly_blocked_overbought")]
    catchup = chart_events[
        chart_events["event_type"].eq("monthly_buy_allowed")
        & pd.to_numeric(chart_events["buy_amount"], errors="coerce").gt(1000.0)
    ]

    fig, (ax_price, ax_weekly, ax_monthly) = plt.subplots(
        3,
        1,
        figsize=(18, 11),
        sharex=True,
        gridspec_kw={"height_ratios": [3.6, 1.25, 1.25], "hspace": 0.06},
    )
    plot_candles(ax_price, price, width_days=18.5)
    draw_block_lines([ax_price, ax_weekly, ax_monthly], events, start, end)

    if not blocked.empty:
        lows = []
        for _, event in blocked.iterrows():
            recent = price[price["date"] <= event["date"]].tail(1)
            lows.append(float(recent.iloc[-1]["high"]) if not recent.empty else float(price["high"].max()))
        ax_price.scatter(blocked["date"], lows, marker="v", s=78, color="#dc2626", edgecolors="white", linewidths=0.65, zorder=8, label="blocked buy marker")
    if not catchup.empty:
        lows = []
        for _, event in catchup.iterrows():
            recent = price[price["date"] <= event["date"]].tail(1)
            lows.append(float(recent.iloc[-1]["low"]) if not recent.empty else float(price["low"].min()))
        ax_price.scatter(catchup["date"], lows, marker="^", s=68, color="#0f766e", edgecolors="white", linewidths=0.55, zorder=8, label="catch-up buy marker")

    rsi_panel(ax_weekly, weekly_rsi, start, end, "Weekly RSI14 EMA14", "#7c3aed", "#a855f7", threshold)
    rsi_panel(ax_monthly, monthly_rsi, start, end, "Monthly RSI14 EMA14", "#b45309", "#f97316", threshold)

    ax_price.set_title(title)
    ax_price.set_ylabel("Adjusted GOOGL monthly")
    ax_price.grid(True, alpha=0.25)
    ax_price.legend(loc="upper left", fontsize=8, ncol=3)
    ax_price.margins(y=0.08)
    ax_monthly.xaxis.set_major_locator(mdates.YearLocator(base=1 if (end - start).days <= 2200 else 2))
    ax_monthly.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=145, bbox_inches="tight")
    plt.close(fig)

    return {
        "chart": out_path.relative_to(index_dir).as_posix(),
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "monthly_bars": int(len(price)),
        "blocked_buys": int(len(blocked)),
        "catchup_buys": int(len(catchup)),
    }


def segment_windows(daily: pd.DataFrame, years_per_chart: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    first_year = int(pd.Timestamp(daily["date"].min()).year)
    last_year = int(pd.Timestamp(daily["date"].max()).year)
    windows = []
    for start_year in range(first_year, last_year + 1, years_per_chart):
        end_year = min(start_year + years_per_chart - 1, last_year)
        windows.append((pd.Timestamp(year=start_year, month=1, day=1), pd.Timestamp(year=end_year, month=12, day=31)))
    return windows


def write_index(
    out_dir: Path,
    daily: pd.DataFrame,
    monthly_price: pd.DataFrame,
    monthly_rsi: pd.DataFrame,
    weekly_rsi: pd.DataFrame,
    events: pd.DataFrame,
    curve: pd.DataFrame,
    chart_rows: list[dict[str, object]],
    dropped_completed_month: str,
    monthly_amount: float,
    max_multiple: float,
    signal_timeframe: str,
    threshold: float,
    filter_label: str,
    catchup_window_months: int,
) -> None:
    blocked = events[events["event_type"].eq("monthly_blocked_overbought")].copy()
    allowed = events[events["event_type"].eq("monthly_buy_allowed")].copy()
    gross_saved = len(blocked) * monthly_amount
    ending_cash = float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0
    redeployed = max(gross_saved - ending_cash, 0.0)
    monthly_hot = monthly_rsi[pd.to_numeric(monthly_rsi["rsi_smooth"], errors="coerce").ge(threshold)]
    weekly_hot = weekly_rsi[pd.to_numeric(weekly_rsi["rsi_smooth"], errors="coerce").ge(threshold)]
    end_equity = float(curve.iloc[-1]["equity"]) if not curve.empty else 0.0
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    lines = [
        "# GOOGL %s Deferral Chart Pack" % filter_label,
        "",
        "Yahoo adjusted OHLCV. Price is shown as monthly candles, with weekly and monthly smoothed RSI panels underneath.",
        "",
        "Rule visualized: **block the first-trading-day monthly DCA buy when prior completed %s RSI14 EMA14 is >=%.0f**, then %s." % (
            signal_timeframe,
            threshold,
            "schedule deferred cash across the next **%d allowed monthly buys**" % catchup_window_months
            if catchup_window_months > 0
            else "allow later buys to spend up to **%.1fx** the normal `$%s` monthly amount" % (max_multiple, format(monthly_amount, ",.0f")),
        ),
        "",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "Counts:",
        "",
        "- Completed monthly RSI >=%.0f bars: **%d**." % (threshold, len(monthly_hot)),
        "- Weekly RSI >=%.0f bars: **%d**." % (threshold, len(weekly_hot)),
        "- Blocked monthly DCA buys: **%d**." % len(blocked),
        "- Allowed buys: **%d**." % len(allowed),
        "- Gross skipped/saved cash: **%s**." % money(gross_saved),
        "- Redeployed estimate through catch-up: **%s**." % money(redeployed),
        "- Ending cash still unspent: **%s**." % money(ending_cash),
        "- Ending equity: **%s** on **%s** contributed." % (money(end_equity), money(total)),
    ]
    if dropped_completed_month:
        lines.append("- Dropped final partial month from completed-month RSI: **%s**." % dropped_completed_month)
    lines.extend(
        [
            "",
            "Legend:",
            "",
            "- Red vertical lines / down markers = monthly DCA buy blocked by **%s**." % filter_label,
            "- Green dotted vertical lines / up markers = catch-up buy larger than the normal monthly contribution.",
            "- Orange monthly RSI points mark completed monthly RSI >=%.0f." % threshold,
            "- Purple weekly RSI points mark completed weekly RSI >=%.0f." % threshold,
            "",
            "## Charts",
            "",
            "| Chart | Window | Monthly Bars | Blocked Buys | Catch-Up Buys |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in chart_rows:
        lines.append(
            "| [`%s`](%s) | %s to %s | %d | %d | %d |"
            % (
                Path(str(row["chart"])).name,
                row["chart"],
                row["start"],
                row["end"],
                row["monthly_bars"],
                row["blocked_buys"],
                row["catchup_buys"],
            )
        )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `monthly_candles.csv`",
            "- `weekly_rsi.csv`",
            "- `monthly_rsi.csv`",
            "- `rsi_deferral_events.csv`",
            "- `rsi_deferral_curve.csv`",
            "",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=DEFAULT_MONTHLY_AMOUNT)
    parser.add_argument("--max-multiple", type=float, default=MAX_REDEPLOY_MULTIPLE)
    parser.add_argument("--signal-timeframe", choices=["daily", "weekly", "monthly"], default="monthly")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--catchup-window-months", type=int, default=0)
    parser.add_argument("--years-per-chart", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "segments").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("GOOGL", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])

    monthly_price, _ = monthly_ohlcv(daily, drop_final_partial=False)
    monthly_completed, dropped_completed_month = monthly_ohlcv(daily, drop_final_partial=True)
    weekly = weekly_ohlcv(daily)
    weekly_rsi = compute_rsi(weekly, RSI_LENGTH, RSI_SMOOTH)
    monthly_rsi = compute_rsi(monthly_completed, RSI_LENGTH, RSI_SMOOTH)
    filter_label = "RSI %s >=%.0f" % (args.signal_timeframe, args.threshold)
    state_daily = rsi_filter(daily, args.signal_timeframe, args.threshold)
    if args.catchup_window_months > 0:
        curve, events = simulate_window_catchup(state_daily, args.monthly_amount, args.catchup_window_months, filter_label)
    else:
        curve, events = simulate_deferral(state_daily, args.monthly_amount, args.max_multiple, filter_label)

    for df in [monthly_price, monthly_completed, weekly, weekly_rsi, monthly_rsi, curve, events]:
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

    monthly_price.to_csv(out_dir / "monthly_candles.csv", index=False)
    weekly_rsi.to_csv(out_dir / "weekly_rsi.csv", index=False)
    monthly_rsi.to_csv(out_dir / "monthly_rsi.csv", index=False)
    events.to_csv(out_dir / "rsi_deferral_events.csv", index=False)
    curve.to_csv(out_dir / "rsi_deferral_curve.csv", index=False)

    chart_rows = []
    full = draw_chart(
        "GOOGL monthly candles with weekly/monthly %s deferral markers (full history)" % filter_label,
        monthly_price,
        weekly_rsi,
        monthly_rsi,
        events,
        out_dir / "full_history.png",
        out_dir,
        pd.Timestamp(daily["date"].min()),
        pd.Timestamp(daily["date"].max()),
        args.threshold,
    )
    if full:
        chart_rows.append(full)
    for start, end in segment_windows(daily, args.years_per_chart):
        clipped_start = max(start, pd.Timestamp(daily["date"].min()))
        clipped_end = min(end, pd.Timestamp(daily["date"].max()))
        name = "%04d_%04d.png" % (start.year, end.year)
        row = draw_chart(
            "GOOGL monthly %s deferral markers (%s-%s)" % (filter_label, start.year, end.year),
            monthly_price,
            weekly_rsi,
            monthly_rsi,
            events,
            out_dir / "segments" / name,
            out_dir,
            clipped_start,
            clipped_end,
            args.threshold,
        )
        if row:
            chart_rows.append(row)

    write_index(
        out_dir,
        daily,
        monthly_price,
        monthly_rsi,
        weekly_rsi,
        events,
        curve,
        chart_rows,
        dropped_completed_month,
        args.monthly_amount,
        args.max_multiple,
        args.signal_timeframe,
        args.threshold,
        filter_label,
        args.catchup_window_months,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
