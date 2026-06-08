#!/usr/bin/env python3
"""Yearly charts for QQQ low-high-lower-low pivot signals."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import ROOT
from qqq_market_structure_lhll_dca_study import DEFAULT_START, OUT_DIR
from qqq_yearly_orb_study import default_completed_end, load_adjusted_daily, plot_candles


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


def infer_existing_end(out_dir: Path) -> str:
    curves = out_dir / "curves.csv"
    if curves.exists():
        dates = pd.read_csv(curves, usecols=["date"], parse_dates=["date"])
        if not dates.empty:
            return pd.Timestamp(dates["date"].max()).date().isoformat()
    signals = out_dir / "signals.csv"
    if signals.exists():
        dates = pd.read_csv(signals, usecols=["buy_date"], parse_dates=["buy_date"])
        if not dates.empty:
            return pd.Timestamp(dates["buy_date"].max()).date().isoformat()
    return default_completed_end()


def load_study_tables(out_dir: Path, pivot_bars: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    signals_path = out_dir / "signals.csv"
    pivots_path = out_dir / "pivots.csv"
    if not signals_path.exists() or not pivots_path.exists():
        raise FileNotFoundError("Run qqq_market_structure_lhll_dca_study.py before building charts.")

    signals = pd.read_csv(signals_path)
    pivots = pd.read_csv(pivots_path)
    signals = signals[signals["pivot_bars"].eq(pivot_bars)].copy()
    pivots = pivots[pivots["pivot_bars"].eq(pivot_bars)].copy()
    signals = parse_dates(signals, SIGNAL_DATE_COLUMNS)
    pivots = parse_dates(pivots, PIVOT_DATE_COLUMNS)
    if signals.empty:
        raise RuntimeError("No low-high-lower-low signals for pivot_bars=%d." % pivot_bars)
    signals["buy_year"] = signals["buy_date"].dt.year
    pivots["pivot_year"] = pivots["pivot_date"].dt.year
    return signals, pivots


def bounds_for_year(year: int, daily: pd.DataFrame, year_signals: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year, month=12, day=31)
    dates = [start, end]
    if not year_signals.empty:
        for column in ["l1_pivot_date", "h1_pivot_date", "l2_pivot_date", "signal_date", "buy_date"]:
            dates.extend(pd.to_datetime(year_signals[column]).dropna().tolist())
    start = min(dates) - pd.Timedelta(days=7)
    end = max(dates) + pd.Timedelta(days=7)
    start = max(start, pd.Timestamp(daily["date"].min()))
    end = min(end, pd.Timestamp(daily["date"].max()))
    return start, end


def plot_year(
    year: int,
    daily: pd.DataFrame,
    pivots: pd.DataFrame,
    signals: pd.DataFrame,
    pivot_bars: int,
    out: Path,
) -> dict:
    year_signals = signals[signals["buy_year"].eq(year)].copy()
    start, end = bounds_for_year(year, daily, year_signals)
    chart_daily = daily[(daily["date"] >= start) & (daily["date"] <= end)].copy()
    if chart_daily.empty:
        return {}

    visible_pivots = pivots[(pivots["pivot_date"] >= start) & (pivots["pivot_date"] <= end)].copy()
    year_pivots = pivots[pivots["pivot_year"].eq(year)]
    lows = visible_pivots[visible_pivots["kind"].eq("low")]
    highs = visible_pivots[visible_pivots["kind"].eq("high")]

    fig, (ax, ax_vol) = plt.subplots(
        2,
        1,
        figsize=(17, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [4.0, 1.0], "hspace": 0.04},
    )
    plot_candles(ax, chart_daily, width_days=0.7)
    ax.axvspan(pd.Timestamp(year=year, month=1, day=1), pd.Timestamp(year=year, month=12, day=31), color="#f3f4f6", alpha=0.35, zorder=0)

    ax.scatter(
        lows["pivot_date"],
        lows["value"],
        marker="^",
        color="#0f766e",
        edgecolors="white",
        linewidths=0.4,
        s=36,
        label="%d-bar pivot low" % pivot_bars,
        zorder=6,
    )
    ax.scatter(
        highs["pivot_date"],
        highs["value"],
        marker="v",
        color="#b45309",
        edgecolors="white",
        linewidths=0.4,
        s=36,
        label="%d-bar pivot high" % pivot_bars,
        zorder=6,
    )

    sequence_label = "L-H-LL sequence"
    buy_label = "next-open buy"
    for _, signal in year_signals.iterrows():
        seq_dates = [signal["l1_pivot_date"], signal["h1_pivot_date"], signal["l2_pivot_date"]]
        seq_vals = [signal["l1_value"], signal["h1_value"], signal["l2_value"]]
        ax.plot(seq_dates, seq_vals, color="#7c3aed", linewidth=1.25, alpha=0.75, label=sequence_label, zorder=7)
        sequence_label = None
        ax.scatter(signal["l1_pivot_date"], signal["l1_value"], marker="o", color="#0f766e", edgecolors="white", linewidths=0.8, s=80, zorder=8)
        ax.scatter(signal["h1_pivot_date"], signal["h1_value"], marker="o", color="#b45309", edgecolors="white", linewidths=0.8, s=80, zorder=8)
        ax.scatter(signal["l2_pivot_date"], signal["l2_value"], marker="o", color="#dc2626", edgecolors="white", linewidths=0.8, s=92, zorder=8)
        ax.axvline(signal["signal_date"], color="#7c3aed", linewidth=0.8, alpha=0.18, zorder=1)
        ax.scatter(
            signal["buy_date"],
            signal["buy_price"],
            marker="*",
            color="#111827",
            edgecolors="#facc15",
            linewidths=0.9,
            s=185,
            label=buy_label,
            zorder=9,
        )
        buy_label = None

    volume_colors = ["#168a5a" if c >= o else "#c43d3d" for o, c in zip(chart_daily["open"], chart_daily["close"])]
    ax_vol.bar(chart_daily["date"], chart_daily["volume"] / 1_000_000.0, color=volume_colors, width=1.0, alpha=0.42)
    ax_vol.set_ylabel("Vol (M)")
    ax_vol.grid(True, axis="y", color="#e5e7eb", linewidth=0.6, alpha=0.8)

    ax.set_title(
        "QQQ low-high-lower-low signal, %d-bar pivots - %d (%d buys)"
        % (pivot_bars, year, len(year_signals))
    )
    ax.set_ylabel("Adjusted QQQ")
    ax.grid(True, color="#e5e7eb", linewidth=0.6, alpha=0.8)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.margins(y=0.08)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.autofmt_xdate()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=145, bbox_inches="tight")
    plt.close(fig)

    return {
        "year": year,
        "signals": int(len(year_signals)),
        "pivot_lows": int(year_pivots["kind"].eq("low").sum()),
        "pivot_highs": int(year_pivots["kind"].eq("high").sum()),
        "first_buy": year_signals["buy_date"].min().date().isoformat() if not year_signals.empty else "",
        "last_buy": year_signals["buy_date"].max().date().isoformat() if not year_signals.empty else "",
        "chart": out.name,
    }


def write_index(chart_dir: Path, rows: list[dict], pivot_bars: int, daily: pd.DataFrame) -> None:
    total_signals = sum(row["signals"] for row in rows)
    lines = [
        "# QQQ Low-High-Lower-Low Yearly Charts",
        "",
        "These charts visualize the **%d-bar confirmed pivot** signal from the QQQ low-high-lower-low DCA study." % pivot_bars,
        "",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "Markers:",
        "",
        "- Green triangles: confirmed pivot lows.",
        "- Orange triangles: confirmed pivot highs.",
        "- Purple line: the signal sequence, low -> high -> lower low.",
        "- Black/yellow star: next available open after the lower-low confirmation, which is the tested buy point.",
        "",
        "Charts are grouped by the signal's **buy year**. If a setup began late in the prior year, the chart includes that earlier context.",
        "",
        "Total %d-bar buy signals: **%d**." % (pivot_bars, total_signals),
        "",
        "| Year | Buy Signals | Pivot Lows | Pivot Highs | First Buy | Last Buy | Chart |",
        "|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| %d | %d | %d | %d | %s | %s | [%s](%s) |"
            % (
                row["year"],
                row["signals"],
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
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--pivot-bars", type=int, default=2)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    end = args.end or infer_existing_end(args.out_dir)
    signals, pivots = load_study_tables(args.out_dir, args.pivot_bars)
    daily = load_adjusted_daily("QQQ", args.start, end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = daily.sort_values("date").reset_index(drop=True)

    chart_dir = args.out_dir / "charts" / ("yearly_%dbar" % args.pivot_bars)
    chart_dir.mkdir(parents=True, exist_ok=True)
    years = list(range(int(daily["date"].dt.year.min()), int(daily["date"].dt.year.max()) + 1))
    rows = []
    for year in years:
        row = plot_year(year, daily, pivots, signals, args.pivot_bars, chart_dir / ("%d.png" % year))
        if row:
            rows.append(row)
    write_index(chart_dir, rows, args.pivot_bars, daily)
    print("Wrote %d yearly charts to %s" % (len(rows), chart_dir))


if __name__ == "__main__":
    main()
