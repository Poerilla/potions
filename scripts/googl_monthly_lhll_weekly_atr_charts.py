#!/usr/bin/env python3
"""GOOGL monthly candles with causal weekly ATR Supertrend and LHLL pivots."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_monthly_pivot_dca_study import detect_lhll_monthly, monthly_ohlcv
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily, plot_candles
from yearly_orb_delivery_research_charts import calculate_weekly_atr_trailing_stop_on_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_monthly_lhll_weekly_atr_charts"
DEFAULT_START = "2004-01-01"
DEFAULT_ATR_LENGTH = 14
DEFAULT_ATR_MULTIPLIER = 3.0
DEFAULT_PIVOT_BARS = 2
DATE_COLUMNS = [
    "l1_pivot_date",
    "l1_confirm_date",
    "h1_pivot_date",
    "h1_confirm_date",
    "l2_pivot_date",
    "l2_confirm_date",
    "signal_date",
    "buy_date",
]


def pct(value: float) -> str:
    return "%.2f%%" % value


def parse_signal_dates(signals: pd.DataFrame) -> pd.DataFrame:
    out = signals.copy()
    for column in DATE_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column])
    return out


def parse_pivot_dates(pivots: pd.DataFrame) -> pd.DataFrame:
    out = pivots.copy()
    for column in ["pivot_date", "confirm_date"]:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column])
    return out


def signal_touches_window(signal: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    for column in ["l1_pivot_date", "h1_pivot_date", "l2_pivot_date", "signal_date", "buy_date"]:
        value = signal.get(column)
        if pd.notna(value) and start <= pd.Timestamp(value) <= end:
            return True
    return False


def signals_for_window(signals: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    mask = signals.apply(lambda row: signal_touches_window(row, start, end), axis=1)
    return signals[mask].copy()


def plot_weekly_atr_stop(ax: plt.Axes, weekly_atr: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> None:
    work = weekly_atr.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work[work["date"].between(start, end)].copy()
    work = work.dropna(subset=["atr_stop", "atr_trend"]).sort_values("date")
    if work.empty:
        return

    work["_gap"] = work["date"].diff().dt.days.fillna(1).gt(10)
    work["_change"] = work["atr_trend"].ne(work["atr_trend"].shift())
    work["_segment"] = (work["_gap"] | work["_change"]).cumsum()
    labels_used: set[str] = set()
    colors = {"up": "#65a30d", "down": "#dc2626"}
    labels = {"up": "weekly ATR ST up stop", "down": "weekly ATR ST down stop"}

    for _, chunk in work.groupby("_segment", sort=True):
        trend = str(chunk.iloc[0]["atr_trend"])
        label = labels.get(trend, "weekly ATR ST")
        ax.plot(
            chunk["date"],
            chunk["atr_stop"].astype(float),
            color=colors.get(trend, "#6b7280"),
            linewidth=1.45,
            linestyle="--",
            alpha=0.9,
            label=label if label not in labels_used else None,
            zorder=5,
        )
        labels_used.add(label)


def draw_chart(
    title: str,
    monthly: pd.DataFrame,
    pivots: pd.DataFrame,
    signals: pd.DataFrame,
    weekly_atr: pd.DataFrame,
    out_path: Path,
    index_dir: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    pivot_bars: int,
) -> dict[str, object]:
    chart_monthly = monthly[monthly["date"].between(start, end)].copy()
    if chart_monthly.empty:
        return {}
    chart_pivots = pivots[pivots["pivot_date"].between(start, end)].copy()
    chart_signals = signals_for_window(signals, start, end)

    lows = chart_pivots[chart_pivots["kind"].eq("low")]
    highs = chart_pivots[chart_pivots["kind"].eq("high")]

    fig, (ax, ax_vol) = plt.subplots(
        2,
        1,
        figsize=(18, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [4.0, 1.0], "hspace": 0.04},
    )
    plot_candles(ax, chart_monthly, width_days=18.5)
    plot_weekly_atr_stop(ax, weekly_atr, start, end)

    ax.scatter(
        lows["pivot_date"],
        lows["value"],
        marker="^",
        color="#0f766e",
        edgecolors="white",
        linewidths=0.55,
        s=74,
        label="%d-month pivot low" % pivot_bars,
        zorder=7,
    )
    ax.scatter(
        highs["pivot_date"],
        highs["value"],
        marker="v",
        color="#b45309",
        edgecolors="white",
        linewidths=0.55,
        s=74,
        label="%d-month pivot high" % pivot_bars,
        zorder=7,
    )

    sequence_label = "low -> high -> lower low"
    signal_label = "signal known"
    for _, signal in chart_signals.iterrows():
        seq_dates = [signal["l1_pivot_date"], signal["h1_pivot_date"], signal["l2_pivot_date"]]
        seq_vals = [signal["l1_value"], signal["h1_value"], signal["l2_value"]]
        ax.plot(seq_dates, seq_vals, color="#7c3aed", linewidth=1.45, alpha=0.8, label=sequence_label, zorder=8)
        sequence_label = None
        ax.scatter(signal["l1_pivot_date"], signal["l1_value"], marker="o", color="#0f766e", edgecolors="white", linewidths=0.9, s=96, zorder=9)
        ax.scatter(signal["h1_pivot_date"], signal["h1_value"], marker="o", color="#b45309", edgecolors="white", linewidths=0.9, s=96, zorder=9)
        ax.scatter(signal["l2_pivot_date"], signal["l2_value"], marker="o", color="#dc2626", edgecolors="white", linewidths=0.9, s=124, zorder=9)
        ax.axvline(signal["signal_date"], color="#7c3aed", linewidth=0.85, alpha=0.22, label=signal_label, zorder=1)
        signal_label = None

    colors = ["#168a5a" if c >= o else "#c43d3d" for o, c in zip(chart_monthly["open"], chart_monthly["close"])]
    ax_vol.bar(chart_monthly["date"], chart_monthly["volume"] / 1_000_000.0, color=colors, width=18.5, alpha=0.42)
    ax_vol.set_ylabel("Vol (M)")
    ax_vol.grid(True, axis="y", color="#e5e7eb", linewidth=0.6, alpha=0.8)

    ax.set_title(title)
    ax.set_ylabel("Adjusted GOOGL")
    ax.grid(True, color="#e5e7eb", linewidth=0.6, alpha=0.8)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.margins(y=0.08)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1 if (end - start).days <= 2200 else 2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=145, bbox_inches="tight")
    plt.close(fig)

    return {
        "chart": out_path.relative_to(index_dir).as_posix(),
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "monthly_bars": int(len(chart_monthly)),
        "pivot_lows": int(len(lows)),
        "pivot_highs": int(len(highs)),
        "lhll_sequences": int(len(chart_signals)),
    }


def segment_windows(monthly: pd.DataFrame, years_per_chart: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    first_year = int(monthly["date"].dt.year.min())
    last_year = int(monthly["date"].dt.year.max())
    windows = []
    for start_year in range(first_year, last_year + 1, years_per_chart):
        end_year = min(start_year + years_per_chart - 1, last_year)
        start = pd.Timestamp(year=start_year, month=1, day=1)
        end = pd.Timestamp(year=end_year, month=12, day=31)
        windows.append((start, end))
    return windows


def write_index(
    out_dir: Path,
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    pivots: pd.DataFrame,
    signals: pd.DataFrame,
    chart_rows: list[dict[str, object]],
    atr_length: int,
    atr_multiplier: float,
    pivot_bars: int,
    dropped_month: str,
) -> None:
    lows = pivots[pivots["kind"].eq("low")]
    highs = pivots[pivots["kind"].eq("high")]
    lines = [
        "# GOOGL Monthly LHLL + Weekly ATR Supertrend Charts",
        "",
        "Yahoo adjusted OHLCV. Monthly candles are built from adjusted daily bars; the weekly ATR Supertrend is computed on Friday-anchored weekly candles and mapped causally onto the following trading week.",
        "",
        "Signal overlay: confirmed monthly **low -> high -> lower low** using **%d bars left / %d bars right**. The lower low is only marked once the right-side monthly confirmation is complete." % (pivot_bars, pivot_bars),
        "",
        "Window: **%s through %s** daily, **%s through %s** monthly." % (
            daily["date"].min().date().isoformat(),
            daily["date"].max().date().isoformat(),
            monthly["date"].min().date().isoformat(),
            monthly["date"].max().date().isoformat(),
        ),
        "",
        "ATR Supertrend: weekly **ATR(%d) x %.2f**." % (atr_length, atr_multiplier),
        "",
        "Counts: **%d** monthly candles, **%d** pivot lows, **%d** pivot highs, **%d** LHLL sequences." % (
            len(monthly),
            len(lows),
            len(highs),
            len(signals),
        ),
    ]
    if dropped_month:
        lines.append("")
        lines.append("Dropped partial final monthly candle: **%s**." % dropped_month)
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "| Chart | Window | Monthly Bars | Pivot Lows | Pivot Highs | LHLL Sequences |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in chart_rows:
        lines.append(
            "| [%s](%s) | %s to %s | %d | %d | %d | %d |"
            % (
                row["chart"],
                row["chart"],
                row["start"],
                row["end"],
                row["monthly_bars"],
                row["pivot_lows"],
                row["pivot_highs"],
                row["lhll_sequences"],
            )
        )

    lines.extend(["", "## LHLL Sequences", ""])
    if signals.empty:
        lines.append("No confirmed monthly LHLL sequences found.")
    else:
        lines.extend(
            [
                "| # | Low 1 | High | Lower Low | Signal Known | L2 Below L1 |",
                "|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in signals.iterrows():
            lines.append(
                "| %d | %s / %.2f | %s / %.2f | %s / %.2f | %s | %s |"
                % (
                    int(row["signal_index"]),
                    pd.Timestamp(row["l1_pivot_date"]).date().isoformat(),
                    float(row["l1_value"]),
                    pd.Timestamp(row["h1_pivot_date"]).date().isoformat(),
                    float(row["h1_value"]),
                    pd.Timestamp(row["l2_pivot_date"]).date().isoformat(),
                    float(row["l2_value"]),
                    pd.Timestamp(row["signal_date"]).date().isoformat(),
                    pct(float(row["l2_below_l1_pct"])),
                )
            )

    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `monthly_bars.csv`",
            "- `pivots.csv`",
            "- `lhll_sequences.csv`",
            "- `weekly_atr_stop_daily.csv`",
            "",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="GOOGL")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    parser.add_argument("--atr-length", type=int, default=DEFAULT_ATR_LENGTH)
    parser.add_argument("--atr-multiplier", type=float, default=DEFAULT_ATR_MULTIPLIER)
    parser.add_argument("--pivot-bars", type=int, default=DEFAULT_PIVOT_BARS)
    parser.add_argument("--segment-years", type=int, default=5)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    out_dir = args.output_root if ticker == "GOOGL" else args.output_root.parent / ("%s_monthly_lhll_weekly_atr_charts" % ticker.lower())
    out_dir.mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily(ticker, args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])
    monthly, dropped_month = monthly_ohlcv(daily, drop_final_partial=True)
    monthly["date"] = pd.to_datetime(monthly["date"])

    signals, pivots = detect_lhll_monthly(daily, monthly, args.pivot_bars)
    signals = parse_signal_dates(signals)
    pivots = parse_pivot_dates(pivots)
    weekly_atr = calculate_weekly_atr_trailing_stop_on_daily(daily, args.atr_length, args.atr_multiplier)
    weekly_atr["date"] = pd.to_datetime(weekly_atr["date"])

    monthly.to_csv(out_dir / "monthly_bars.csv", index=False)
    pivots.to_csv(out_dir / "pivots.csv", index=False)
    signals.to_csv(out_dir / "lhll_sequences.csv", index=False)
    weekly_atr[["date", "open", "high", "low", "close", "atr", "atr_stop", "atr_trend"]].to_csv(
        out_dir / "weekly_atr_stop_daily.csv",
        index=False,
    )

    chart_rows: list[dict[str, object]] = []
    full_start = pd.Timestamp(monthly["date"].min()) - pd.Timedelta(days=20)
    full_end = pd.Timestamp(monthly["date"].max()) + pd.Timedelta(days=20)
    chart_rows.append(
        draw_chart(
            "%s monthly candles + weekly ATR Supertrend + monthly LHLL pivots" % ticker,
            monthly,
            pivots,
            signals,
            weekly_atr,
            out_dir / "full_history.png",
            out_dir,
            full_start,
            full_end,
            args.pivot_bars,
        )
    )

    segment_dir = out_dir / "segments"
    for start, end in segment_windows(monthly, max(args.segment_years, 1)):
        row = draw_chart(
            "%s monthly LHLL pivots - %d to %d" % (ticker, start.year, end.year),
            monthly,
            pivots,
            signals,
            weekly_atr,
            segment_dir / ("%d_%d.png" % (start.year, end.year)),
            out_dir,
            start - pd.Timedelta(days=45),
            end + pd.Timedelta(days=45),
            args.pivot_bars,
        )
        if row:
            chart_rows.append(row)

    write_index(
        out_dir,
        daily,
        monthly,
        pivots,
        signals,
        chart_rows,
        args.atr_length,
        args.atr_multiplier,
        args.pivot_bars,
        dropped_month,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    print("LHLL sequences: %d" % len(signals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
