#!/usr/bin/env python3
"""GOOGL daily candles with daily + weekly ATR Supertrend — one chart per calendar year."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import pandas as pd

from atr_supertrend_dca_long import (
    BG,
    CYAN,
    GRID,
    ORANGE,
    draw_candles,
    plot_atr_stop_with_extensions,
    style_axis,
)
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily
from yearly_orb_delivery_research_charts import (
    calculate_daily_atr_trailing_stop,
    calculate_weekly_atr_trailing_stop_on_daily,
)


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_daily_weekly_atr_supertrend_charts"
DEFAULT_ATR_LENGTH = 14
DEFAULT_ATR_MULTIPLIER = 3.0
DEFAULT_EXTENSION_WEEKS = 3
WEEKLY_UP = "#B2FF59"
WEEKLY_DOWN = "#FF6E40"


def draw_googl_year(
    year: int,
    daily: pd.DataFrame,
    out_path: Path,
    atr_length: int,
    atr_multiplier: float,
    extension_weeks: int,
) -> None:
    all_work = daily.copy().sort_values("date").reset_index(drop=True)
    all_work["date"] = pd.to_datetime(all_work["date"])
    all_work = calculate_daily_atr_trailing_stop(all_work, atr_length, atr_multiplier)
    weekly_full = calculate_weekly_atr_trailing_stop_on_daily(all_work, atr_length, atr_multiplier)
    weekly_full["date"] = pd.to_datetime(weekly_full["date"])

    year_start = pd.Timestamp(year=year, month=1, day=1)
    year_end = pd.Timestamp(year=year, month=12, day=31)
    visible = all_work[all_work["date"].between(year_start, year_end)].copy()
    if visible.empty:
        return

    context_start = year_start - pd.Timedelta(weeks=max(extension_weeks, 0))
    context_end = year_end + pd.Timedelta(weeks=max(extension_weeks, 0))
    work = all_work[all_work["date"].between(context_start, context_end)].copy()
    weekly_work = weekly_full[weekly_full["date"].between(context_start, context_end)].copy()

    fig = plt.figure(figsize=(18, 9), facecolor=BG)
    ax = fig.add_subplot(111)
    style_axis(ax)
    draw_candles(ax, visible)

    plot_atr_stop_with_extensions(
        ax,
        work,
        {"up": CYAN, "down": ORANGE},
        linewidth=1.15,
        alpha=0.84,
        linestyle="-",
        zorder=5,
        extension_weeks=extension_weeks,
    )
    plot_atr_stop_with_extensions(
        ax,
        weekly_work,
        {"up": WEEKLY_UP, "down": WEEKLY_DOWN},
        linewidth=1.65,
        alpha=0.88,
        linestyle="--",
        zorder=6,
        extension_weeks=extension_weeks,
    )

    dates = pd.to_datetime(visible["date"])
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=4), dates.iloc[-1] + pd.Timedelta(days=8))
    ax.set_title(
        f"{year} GOOGL · daily ATR Supertrend ({atr_length},{atr_multiplier}) + weekly (causal)",
        color="white",
        fontsize=10,
        fontweight="bold",
        loc="left",
        pad=8,
    )
    legend_items = [
        Line2D([0], [0], color=CYAN, lw=1.2, label="Daily ATR up stop"),
        Line2D([0], [0], color=ORANGE, lw=1.2, label="Daily ATR down stop"),
        Line2D([0], [0], color=WEEKLY_UP, lw=1.7, linestyle="--", label="Weekly ATR up stop"),
        Line2D([0], [0], color=WEEKLY_DOWN, lw=1.7, linestyle="--", label="Weekly ATR down stop"),
    ]
    legend = ax.legend(handles=legend_items, loc="upper left", fontsize=8, framealpha=0.18)
    for text in legend.get_texts():
        text.set_color("white")
    ax.set_ylabel("Price (adj close)", color=GRID, fontsize=8)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


def write_index(out_dir: Path, years: list[int], atr_length: int, atr_multiplier: float) -> None:
    lines = [
        "# GOOGL Daily + Weekly ATR Supertrend (Yearly Charts)",
        "",
        "Daily adjusted OHLCV (Yahoo). One chart per calendar year for the last ten full years.",
        "",
        f"ATR Supertrend: length **{atr_length}**, multiplier **{atr_multiplier}** (Wilder ATR, standard band ratchet).",
        "",
        "- **Solid cyan/orange**: daily stop",
        "- **Dashed lime/coral**: weekly stop (Friday week, plotted causally on the following week)",
        "",
        "| Year | Chart |",
        "|:---:|---|",
    ]
    for year in years:
        lines.append(f"| {year} | [{year}.png]({year}/{year}.png) |")
    lines.extend(["", "## Files", "", "- One PNG per year under `YYYY/YYYY.png`", ""])
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="GOOGL yearly daily+weekly ATR Supertrend charts.")
    parser.add_argument("--years", type=int, default=10, help="Number of full calendar years to chart (from end year backward).")
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--atr-length", type=int, default=DEFAULT_ATR_LENGTH)
    parser.add_argument("--atr-multiplier", type=float, default=DEFAULT_ATR_MULTIPLIER)
    parser.add_argument("--extension-weeks", type=int, default=DEFAULT_EXTENSION_WEEKS)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    end_ts = pd.Timestamp(args.end)
    end_year = int(end_ts.year) - 1 if end_ts.month < 12 or end_ts.day < 28 else int(end_ts.year)
    years = list(range(end_year - args.years + 1, end_year + 1))
    warmup_start = f"{years[0] - 2}-01-01"

    daily = load_adjusted_daily("GOOGL", warmup_start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    for year in years:
        path = out_dir / str(year) / f"{year}.png"
        draw_googl_year(year, daily, path, args.atr_length, args.atr_multiplier, args.extension_weeks)
        print(f"Wrote {path}")

    write_index(out_dir, years, args.atr_length, args.atr_multiplier)
    print(f"Wrote {out_dir / 'INDEX.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
