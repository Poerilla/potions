#!/usr/bin/env python3
"""Charts for years with no previous-quarter-low fills."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_quarterly_low_limit_dca_study import DEFAULT_START, OUT_DIR
from qqq_yearly_orb_study import ROOT, load_adjusted_daily, plot_candles


def infer_end(out_dir: Path) -> str:
    curve_path = out_dir / "curves.csv"
    if curve_path.exists():
        dates = pd.read_csv(curve_path, usecols=["date"], parse_dates=["date"])
        if not dates.empty:
            return pd.Timestamp(dates["date"].max()).date().isoformat()
    return pd.Timestamp.today().date().isoformat()


def load_tables(out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    counts = pd.read_csv(out_dir / "counts_by_year.csv")
    quarters = pd.read_csv(out_dir / "quarters.csv", parse_dates=["start_date", "end_date", "low_date", "prev_quarter_low_date"])
    events = pd.read_csv(out_dir / "events.csv", parse_dates=["date"])
    return counts, quarters, events


def no_fill_years(counts: pd.DataFrame) -> list[int]:
    rows = counts[counts["quarterly_limit_fills"].eq(0) & counts["year_end_fallbacks"].gt(0)]
    return rows["year"].astype(int).tolist()


def plot_year(
    year: int,
    daily: pd.DataFrame,
    quarters: pd.DataFrame,
    events: pd.DataFrame,
    out: Path,
) -> dict:
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year, month=12, day=31)
    chart_daily = daily[(daily["date"] >= start - pd.Timedelta(days=10)) & (daily["date"] <= end + pd.Timedelta(days=10))].copy()
    if chart_daily.empty:
        return {}

    year_quarters = quarters[quarters["year"].eq(year) & quarters["prev_quarter_low"].notna()].sort_values("quarter_num").copy()
    fallback = events[(events["event_type"].eq("year_end_no_quarter_fill")) & (events["date"].dt.year.eq(year))].copy()

    fig, (ax, ax_vol) = plt.subplots(
        2,
        1,
        figsize=(17, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [4.0, 1.0], "hspace": 0.04},
    )
    plot_candles(ax, chart_daily, width_days=0.7)
    ax.axvspan(start, end, color="#f3f4f6", alpha=0.35, zorder=0)

    level_label = "active prev-quarter low"
    previous_low_label = "source quarter low"
    colors = ["#2563eb", "#7c3aed", "#0f766e", "#b45309"]
    for idx, (_, row) in enumerate(year_quarters.iterrows()):
        color = colors[idx % len(colors)]
        level = float(row["prev_quarter_low"])
        q_start = pd.Timestamp(row["start_date"])
        q_end = pd.Timestamp(row["end_date"])
        ax.hlines(level, q_start, q_end, color=color, linewidth=1.5, alpha=0.85, label=level_label)
        level_label = None
        ax.text(
            q_start + (q_end - q_start) / 2,
            level,
            "%s limit %.2f" % (row["quarter"], level),
            color=color,
            fontsize=8,
            ha="center",
            va="bottom",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1.0},
        )
        source_date = pd.Timestamp(row["prev_quarter_low_date"])
        if chart_daily["date"].min() <= source_date <= chart_daily["date"].max():
            ax.scatter(
                source_date,
                level,
                marker="o",
                color=color,
                edgecolors="white",
                linewidths=0.8,
                s=70,
                label=previous_low_label,
                zorder=8,
            )
            previous_low_label = None

    if not fallback.empty:
        ax.scatter(
            fallback["date"],
            fallback["buy_price"],
            marker="*",
            color="#111827",
            edgecolors="#facc15",
            linewidths=1.0,
            s=230,
            label="year-end fallback buy",
            zorder=9,
        )

    volume_colors = ["#168a5a" if c >= o else "#c43d3d" for o, c in zip(chart_daily["open"], chart_daily["close"])]
    ax_vol.bar(chart_daily["date"], chart_daily["volume"] / 1_000_000.0, color=volume_colors, width=1.0, alpha=0.42)
    ax_vol.set_ylabel("Vol (M)")
    ax_vol.grid(True, axis="y", color="#e5e7eb", linewidth=0.6, alpha=0.8)

    fallback_text = ""
    if not fallback.empty:
        row = fallback.iloc[0]
        fallback_text = " - fallback %s at %.2f" % (pd.Timestamp(row["date"]).date().isoformat(), float(row["buy_price"]))
    ax.set_title("QQQ previous-quarter-low no-fill year %d%s" % (year, fallback_text))
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
        "eligible_quarters": int(len(year_quarters)),
        "fallback_date": pd.Timestamp(fallback.iloc[0]["date"]).date().isoformat() if not fallback.empty else "",
        "fallback_buy": float(fallback.iloc[0]["buy_amount"]) if not fallback.empty else 0.0,
        "fallback_price": float(fallback.iloc[0]["buy_price"]) if not fallback.empty else 0.0,
        "chart": out.name,
    }


def write_index(out_dir: Path, rows: list[dict]) -> None:
    lines = [
        "# QQQ Previous-Quarter-Low No-Fill Year Charts",
        "",
        "These are the years where no previous-quarter-low limit filled, so the study used the year-end fallback buy.",
        "",
        "Chart markers:",
        "",
        "- Colored horizontal lines: active prior-quarter-low limit for each quarter.",
        "- Colored circles: the source low from the prior quarter when visible in the chart window.",
        "- Black/yellow star: final trading day fallback buy.",
        "",
        "| Year | Eligible Quarters | Fallback Date | Fallback Buy | Fallback Price | Chart |",
        "|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| %d | %d | %s | $%s | %.2f | [%s](%s) |"
            % (
                row["year"],
                row["eligible_quarters"],
                row["fallback_date"],
                f"{row['fallback_buy']:,.0f}",
                row["fallback_price"],
                row["chart"],
                row["chart"],
            )
        )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    counts, quarters, events = load_tables(args.output_root)
    years = no_fill_years(counts)
    end = args.end or infer_end(args.output_root)
    daily = load_adjusted_daily("QQQ", args.start, end, ROOT / "data" / "benchmarks", refresh=args.refresh).sort_values("date").reset_index(drop=True)
    chart_dir = args.output_root / "charts" / "no_fill_years"
    rows = []
    for year in years:
        row = plot_year(year, daily, quarters, events, chart_dir / ("%d.png" % year))
        if row:
            rows.append(row)
    write_index(chart_dir, rows)
    print("Wrote %d no-fill year charts to %s" % (len(rows), chart_dir))


if __name__ == "__main__":
    main()
