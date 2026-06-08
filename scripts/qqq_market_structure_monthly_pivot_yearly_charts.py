#!/usr/bin/env python3
"""Yearly charts for QQQ monthly-pivot market-structure signals."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_monthly_pivot_dca_study import OUT_DIR
from qqq_market_structure_weekly_pivot_dca_study import display_pattern
from qqq_yearly_orb_study import plot_candles


SIGNAL_DATE_COLUMNS = [
    "l1_pivot_date",
    "l1_confirm_date",
    "h1_pivot_date",
    "h1_confirm_date",
    "l2_pivot_date",
    "l2_confirm_date",
    "signal_date",
    "buy_date",
]
PIVOT_DATE_COLUMNS = ["pivot_date", "confirm_date"]


def parse_dates(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column])
    return out


def load_chart_tables(out_dir: Path, pattern: str, pivot_bars: int, variant: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly_path = out_dir / "monthly_bars.csv"
    signals_path = out_dir / "signals.csv"
    pivots_path = out_dir / "pivots.csv"
    curves_path = out_dir / "curves.csv"
    missing = [path for path in [monthly_path, signals_path, pivots_path, curves_path] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing monthly study output files: %s" % ", ".join(str(path) for path in missing))

    monthly = pd.read_csv(monthly_path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    signals = pd.read_csv(signals_path)
    pivots = pd.read_csv(pivots_path)
    curves = pd.read_csv(curves_path, parse_dates=["date"], low_memory=False)
    signals = signals[signals["pattern"].eq(pattern) & signals["pivot_bars"].eq(pivot_bars)].copy()
    pivots = pivots[pivots["pattern"].eq(pattern) & pivots["pivot_bars"].eq(pivot_bars)].copy()
    curves = curves[curves["pattern"].eq(pattern) & curves["pivot_bars"].eq(pivot_bars) & curves["variant"].eq(variant)].copy()
    signals = parse_dates(signals, SIGNAL_DATE_COLUMNS)
    pivots = parse_dates(pivots, PIVOT_DATE_COLUMNS)
    if signals.empty:
        raise RuntimeError("No signals found for %s / %d-month pivots." % (pattern, pivot_bars))
    if curves.empty:
        raise RuntimeError("No curve rows found for %s / %d-month pivots / %s." % (pattern, pivot_bars, variant))
    signals["buy_year"] = signals["buy_date"].dt.year
    pivots["pivot_year"] = pivots["pivot_date"].dt.year
    return monthly, signals, pivots, curves


def bounds_for_year(year: int, monthly: pd.DataFrame, year_signals: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year, month=12, day=31)
    dates = [start, end]
    if not year_signals.empty:
        for column in ["l1_pivot_date", "h1_pivot_date", "l2_pivot_date", "signal_date", "buy_date"]:
            dates.extend(pd.to_datetime(year_signals[column]).dropna().tolist())
    start = min(dates) - pd.Timedelta(days=45)
    end = max(dates) + pd.Timedelta(days=45)
    start = max(start, pd.Timestamp(monthly["date"].min()))
    end = min(end, pd.Timestamp(monthly["date"].max()))
    return start, end


def plot_year(
    year: int,
    monthly: pd.DataFrame,
    signals: pd.DataFrame,
    pivots: pd.DataFrame,
    curves: pd.DataFrame,
    pattern: str,
    pivot_bars: int,
    variant: str,
    out: Path,
) -> dict:
    year_signals = signals[signals["buy_year"].eq(year)].copy()
    start, end = bounds_for_year(year, monthly, year_signals)
    chart_monthly = monthly[(monthly["date"] >= start) & (monthly["date"] <= end)].copy()
    if chart_monthly.empty:
        return {}

    visible_pivots = pivots[(pivots["pivot_date"] >= start) & (pivots["pivot_date"] <= end)].copy()
    year_pivots = pivots[pivots["pivot_year"].eq(year)]
    year_curve = curves[curves["date"].dt.year.eq(year)].copy()
    year_sweeps = year_curve[pd.to_numeric(year_curve.get("sweep_buy_amount", 0.0), errors="coerce").fillna(0.0).gt(0)].copy()
    lows = visible_pivots[visible_pivots["kind"].eq("low")]
    highs = visible_pivots[visible_pivots["kind"].eq("high")]

    fig, (ax, ax_vol) = plt.subplots(
        2,
        1,
        figsize=(17, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [4.0, 1.0], "hspace": 0.04},
    )
    plot_candles(ax, chart_monthly, width_days=19.0)
    ax.axvspan(pd.Timestamp(year=year, month=1, day=1), pd.Timestamp(year=year, month=12, day=31), color="#f3f4f6", alpha=0.35, zorder=0)

    ax.scatter(
        lows["pivot_date"],
        lows["value"],
        marker="^",
        color="#0f766e",
        edgecolors="white",
        linewidths=0.5,
        s=64,
        label="%d-month pivot low" % pivot_bars,
        zorder=6,
    )
    ax.scatter(
        highs["pivot_date"],
        highs["value"],
        marker="v",
        color="#b45309",
        edgecolors="white",
        linewidths=0.5,
        s=64,
        label="%d-month pivot high" % pivot_bars,
        zorder=6,
    )

    sequence_label = "%s sequence" % display_pattern(pattern)
    buy_label = "next-daily-open buy"
    for _, signal in year_signals.iterrows():
        seq_dates = [signal["l1_pivot_date"], signal["h1_pivot_date"], signal["l2_pivot_date"]]
        seq_vals = [signal["l1_value"], signal["h1_value"], signal["l2_value"]]
        ax.plot(seq_dates, seq_vals, color="#7c3aed", linewidth=1.5, alpha=0.8, label=sequence_label, zorder=7)
        sequence_label = None
        ax.scatter(signal["l1_pivot_date"], signal["l1_value"], marker="o", color="#0f766e", edgecolors="white", linewidths=0.9, s=100, zorder=8)
        ax.scatter(signal["h1_pivot_date"], signal["h1_value"], marker="o", color="#b45309", edgecolors="white", linewidths=0.9, s=100, zorder=8)
        ax.scatter(signal["l2_pivot_date"], signal["l2_value"], marker="o", color="#dc2626", edgecolors="white", linewidths=0.9, s=116, zorder=8)
        ax.axvline(signal["signal_date"], color="#7c3aed", linewidth=0.9, alpha=0.2, zorder=1)
        ax.scatter(
            signal["buy_date"],
            signal["buy_price"],
            marker="*",
            color="#111827",
            edgecolors="#facc15",
            linewidths=1.0,
            s=220,
            label=buy_label,
            zorder=9,
        )
        buy_label = None

    if not year_sweeps.empty:
        ax.scatter(
            year_sweeps["date"],
            year_sweeps["year_end_sweep_price"],
            marker="s",
            color="#2563eb",
            edgecolors="white",
            linewidths=0.9,
            s=115,
            label="Dec high catch-up",
            zorder=9,
        )

    volume_colors = ["#168a5a" if c >= o else "#c43d3d" for o, c in zip(chart_monthly["open"], chart_monthly["close"])]
    ax_vol.bar(chart_monthly["date"], chart_monthly["volume"] / 1_000_000.0, color=volume_colors, width=18.5, alpha=0.42)
    ax_vol.set_ylabel("Vol (M)")
    ax_vol.grid(True, axis="y", color="#e5e7eb", linewidth=0.6, alpha=0.8)

    ax.set_title(
        "QQQ monthly %s signal, %d-month pivots - %d (%d signals, %d Dec sweeps)"
        % (display_pattern(pattern), pivot_bars, year, len(year_signals), len(year_sweeps))
    )
    ax.set_ylabel("Adjusted QQQ")
    ax.grid(True, color="#e5e7eb", linewidth=0.6, alpha=0.8)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.margins(y=0.08)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.autofmt_xdate()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=145, bbox_inches="tight")
    plt.close(fig)

    return {
        "year": year,
        "signals": int(len(year_signals)),
        "dec_sweeps": int(len(year_sweeps)),
        "pivot_lows": int(year_pivots["kind"].eq("low").sum()),
        "pivot_highs": int(year_pivots["kind"].eq("high").sum()),
        "first_buy": year_signals["buy_date"].min().date().isoformat() if not year_signals.empty else "",
        "last_buy": year_signals["buy_date"].max().date().isoformat() if not year_signals.empty else "",
        "chart": out.name,
    }


def write_index(chart_dir: Path, rows: list[dict], pattern: str, pivot_bars: int, variant: str, monthly: pd.DataFrame) -> None:
    total_signals = sum(row["signals"] for row in rows)
    total_sweeps = sum(row["dec_sweeps"] for row in rows)
    lines = [
        "# QQQ Monthly %s Yearly Charts" % display_pattern(pattern),
        "",
        "These charts visualize the **%d-month confirmed pivot** version of the monthly-pivot market-structure DCA study." % pivot_bars,
        "",
        "Variant shown: **`%s`**." % variant,
        "",
        "Window: **%s through %s**." % (monthly["date"].min().date().isoformat(), monthly["date"].max().date().isoformat()),
        "",
        "Markers:",
        "",
        "- Green triangles: confirmed monthly pivot lows.",
        "- Orange triangles: confirmed monthly pivot highs.",
        "- Purple line: monthly low -> high -> lower-low sequence.",
        "- Black/yellow star: next available daily open after the monthly signal is known.",
        "- Blue square: year-end catch-up buy at the final December weekly high.",
        "",
        "Charts are grouped by the signal's **buy year**. If a setup began in a prior year, the chart includes that earlier context.",
        "",
        "Total %d-month %s buy signals: **%d**. December catch-up buys: **%d**." % (pivot_bars, display_pattern(pattern), total_signals, total_sweeps),
        "",
        "| Year | Buy Signals | Dec Sweeps | Pivot Lows | Pivot Highs | First Buy | Last Buy | Chart |",
        "|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| %d | %d | %d | %d | %d | %s | %s | [%s](%s) |"
            % (
                row["year"],
                row["signals"],
                row["dec_sweeps"],
                row["pivot_lows"],
                row["pivot_highs"],
                row["first_buy"] or "-",
                row["last_buy"] or "-",
                row["chart"],
                row["chart"],
            )
        )
    (chart_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    parser.add_argument("--pattern", default="low_high_lower_low")
    parser.add_argument("--pivot-bars", type=int, default=2)
    parser.add_argument("--variant", default="signal_static_full_window")
    parser.add_argument("--chart-dir", type=Path, default=None)
    args = parser.parse_args()

    monthly, signals, pivots, curves = load_chart_tables(args.output_root, args.pattern, args.pivot_bars, args.variant)
    chart_dir = args.chart_dir or args.output_root / "charts" / ("yearly_%s_%dm" % (display_pattern(args.pattern).lower().replace("-", ""), args.pivot_bars))
    chart_dir.mkdir(parents=True, exist_ok=True)

    years = list(range(int(monthly["date"].dt.year.min()), int(monthly["date"].dt.year.max()) + 1))
    rows = []
    for year in years:
        row = plot_year(year, monthly, signals, pivots, curves, args.pattern, args.pivot_bars, args.variant, chart_dir / ("%d.png" % year))
        if row:
            rows.append(row)
    write_index(chart_dir, rows, args.pattern, args.pivot_bars, args.variant, monthly)
    print("Wrote %d yearly charts to %s" % (len(rows), chart_dir))


if __name__ == "__main__":
    main()
