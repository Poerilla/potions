from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .ym_weekly_six_loss_charts import load_weekly_bars


REPO = Path(__file__).resolve().parents[1]


def load_high_loss_days(unit_fills_path: Path, min_losses: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    fills = pd.read_csv(unit_fills_path)
    fills["entry_ts"] = pd.to_datetime(fills["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    fills["usd"] = pd.to_numeric(fills["usd"], errors="coerce").fillna(0.0)
    fills["entry_date"] = fills["entry_ts"].dt.date
    fills["week_start"] = (fills["entry_ts"].dt.normalize() - pd.to_timedelta(fills["entry_ts"].dt.weekday, unit="D")).dt.date
    fills["is_loss"] = fills["usd"] < 0
    days = (
        fills.groupby(["week_start", "entry_date"])
        .agg(trades=("usd", "size"), losses=("is_loss", "sum"), net=("usd", "sum"))
        .reset_index()
    )
    high_loss_days = days[days["losses"] > min_losses].copy()
    week_summary = (
        high_loss_days.groupby("week_start")
        .agg(high_loss_days=("entry_date", "size"), max_day_losses=("losses", "max"), net_on_high_loss_days=("net", "sum"))
        .reset_index()
    )
    high_loss_days["week_start"] = pd.to_datetime(high_loss_days["week_start"])
    high_loss_days["entry_date"] = pd.to_datetime(high_loss_days["entry_date"])
    week_summary["week_start"] = pd.to_datetime(week_summary["week_start"])
    return high_loss_days, week_summary


def plot_year(out_path: Path, year: int, weekly: pd.DataFrame, week_summary: pd.DataFrame) -> dict[str, object]:
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year + 1, month=1, day=1)
    view = weekly[(weekly.index >= start - pd.Timedelta(weeks=12)) & (weekly.index < end)].copy()
    body = weekly[(weekly.index >= start) & (weekly.index < end)].copy()
    marker_by_week = {
        row["week_start"].normalize(): row
        for _, row in week_summary.iterrows()
    }
    year_markers = [idx for idx in body.index if idx.normalize() in marker_by_week]

    fig, ax = plt.subplots(figsize=(18, 8))
    x_map = {ts: i for i, ts in enumerate(view.index)}
    for ts, row in view.iterrows():
        x = x_map[ts]
        in_year = start <= ts < end
        marker = marker_by_week.get(ts.normalize())
        up = float(row["close"]) >= float(row["open"])
        if marker is not None:
            color = "#7b1fa2"
            edge = "#4a0f66"
            alpha = 0.95
        elif not in_year:
            color = "#d6d6d6"
            edge = "#9e9e9e"
            alpha = 0.50
        elif up:
            color = "#2e7d32"
            edge = "#1b5e20"
            alpha = 0.80
        else:
            color = "#c62828"
            edge = "#8e0000"
            alpha = 0.80
        ax.vlines(x, float(row["low"]), float(row["high"]), color=edge, linewidth=1.1, alpha=alpha)
        lower = min(float(row["open"]), float(row["close"]))
        height = abs(float(row["close"]) - float(row["open"]))
        ax.add_patch(
            plt.Rectangle(
                (x - 0.34, lower),
                0.68,
                max(height, 0.5),
                facecolor=color,
                edgecolor=edge,
                linewidth=0.9,
                alpha=alpha,
            )
        )
    ax.plot([x_map[ts] for ts in view.index], view["ma10"], color="#1565c0", linewidth=1.6, label="10-week MA")
    y_pad = max((view["high"].max() - view["low"].min()) * 0.012, 10)
    for ts in year_markers:
        row = weekly.loc[ts]
        marker = marker_by_week[ts.normalize()]
        x = x_map[ts]
        ax.text(
            x,
            float(row["high"]) + y_pad,
            "%dD/%dL" % (int(marker["high_loss_days"]), int(marker["max_day_losses"])),
            color="#7b1fa2",
            ha="center",
            va="bottom",
            fontsize=7,
            fontweight="bold",
        )
    ticks = [x_map[ts] for ts in view.index if ts.month in {1, 4, 7, 10} and ts.day <= 7]
    labels = [ts.strftime("%Y-%m-%d") for ts in view.index if ts.month in {1, 4, 7, 10} and ts.day <= 7]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_title("YM weekly candles %d - purple = week with day >2 losing trades" % year)
    ax.set_ylabel("YM")
    ax.grid(True, color="#e3e3e3", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left")
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)
    return {"year": year, "weeks": len(body), "flagged_weeks": len(year_markers), "chart": out_path.name}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YM weekly candles with high-loss days highlighted.")
    parser.add_argument("--min-losses", type=int, default=2, help="Flag days with losses > this value.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts/ym_weekly_days_gt2_losses",
    )
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    if args.output_root.exists() and not args.no_force:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    weekly = load_weekly_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    high_loss_days, week_summary = load_high_loss_days(
        args.source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv",
        args.min_losses,
    )
    high_loss_days.to_csv(args.output_root / ("days_gt%d_losses.csv" % args.min_losses), index=False)
    week_summary.to_csv(args.output_root / "flagged_weeks.csv", index=False)

    rows = []
    for year in sorted(weekly.index.year.unique()):
        year_body = weekly[weekly.index.year == year]
        if year_body.empty:
            continue
        rows.append(plot_year(args.output_root / ("%d.png" % year), int(year), weekly, week_summary))

    pd.DataFrame(rows).to_csv(args.output_root / "yearly_chart_index.csv", index=False)
    lines = [
        "# YM Weekly High-Loss Day Cluster Charts",
        "",
        "Source: 6-trade-limit broker-like weekly 50%% + MA500 replay. Purple candles are weeks containing at least one day with more than `%d` losing trades. Label format is `flagged-days/max-losses-on-a-day`. Blue line is the rolling 10-week MA of weekly closes." % args.min_losses,
        "",
        "High-loss day list: [days_gt%d_losses.csv](days_gt%d_losses.csv)" % (args.min_losses, args.min_losses),
        "",
        "Flagged week summary: [flagged_weeks.csv](flagged_weeks.csv)",
        "",
        "| Year | Weeks | Flagged Weeks | Chart |",
        "|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append("| {year} | {weeks} | {flagged_weeks} | [{chart}]({chart}) |".format(**row))
    args.output_root.joinpath("INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    print("Flagged days: %d; flagged weeks: %d" % (len(high_loss_days), len(week_summary)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
