from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


REPO = Path(__file__).resolve().parents[1]


def load_weekly_bars(bars_path: Path) -> pd.DataFrame:
    bars = pd.read_csv(bars_path)
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert("America/New_York")
    bars = bars.sort_values("ts")
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars = bars.dropna(subset=["open", "high", "low", "close"]).copy()
    bars["week_start"] = (bars["ts"].dt.normalize() - pd.to_timedelta(bars["ts"].dt.weekday, unit="D")).dt.date
    weekly = (
        bars.groupby("week_start")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            start_ts=("ts", "min"),
            end_ts=("ts", "max"),
        )
        .reset_index()
    )
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    weekly = weekly.set_index("week_start").sort_index()
    weekly["ma10"] = weekly["close"].rolling(10).mean()
    return weekly


def load_six_loss_weeks(unit_fills_path: Path) -> pd.DataFrame:
    fills = pd.read_csv(unit_fills_path)
    fills["entry_ts"] = pd.to_datetime(fills["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    fills["usd"] = pd.to_numeric(fills["usd"], errors="coerce").fillna(0.0)
    fills["week_start"] = (fills["entry_ts"].dt.normalize() - pd.to_timedelta(fills["entry_ts"].dt.weekday, unit="D")).dt.date
    fills["is_loss"] = fills["usd"] < 0
    weeks = (
        fills.groupby("week_start")
        .agg(trades=("usd", "size"), losses=("is_loss", "sum"), net=("usd", "sum"))
        .reset_index()
    )
    weeks["week_start"] = pd.to_datetime(weeks["week_start"])
    return weeks[(weeks["trades"] == 6) & (weeks["losses"] == 6)].copy()


def plot_year(out_path: Path, year: int, weekly: pd.DataFrame, six_loss: pd.DataFrame) -> dict[str, object]:
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year + 1, month=1, day=1)
    view = weekly[(weekly.index >= start - pd.Timedelta(weeks=12)) & (weekly.index < end)].copy()
    body = weekly[(weekly.index >= start) & (weekly.index < end)].copy()
    six_set = set(six_loss["week_start"].dt.normalize())
    year_six = [idx for idx in body.index if idx.normalize() in six_set]

    fig, ax = plt.subplots(figsize=(18, 8))
    x_map = {ts: i for i, ts in enumerate(view.index)}
    for ts, row in view.iterrows():
        x = x_map[ts]
        in_year = start <= ts < end
        is_six_loss = ts.normalize() in six_set
        up = float(row["close"]) >= float(row["open"])
        if is_six_loss:
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
    for ts in year_six:
        row = weekly.loc[ts]
        x = x_map[ts]
        ax.text(
            x,
            float(row["high"]) + max((view["high"].max() - view["low"].min()) * 0.012, 10),
            "6L",
            color="#7b1fa2",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )
    ticks = [x_map[ts] for ts in view.index if ts.month in {1, 4, 7, 10} and ts.day <= 7]
    labels = [ts.strftime("%Y-%m-%d") for ts in view.index if ts.month in {1, 4, 7, 10} and ts.day <= 7]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_title("YM weekly candles %d - purple = six losing trades in 6-trade-limit broker replay" % year)
    ax.set_ylabel("YM")
    ax.grid(True, color="#e3e3e3", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left")
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)
    return {"year": year, "weeks": len(body), "six_loss_weeks": len(year_six), "chart": out_path.name}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YM weekly candles with 6-loss weeks highlighted.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts/ym_weekly_six_loss",
    )
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    if args.output_root.exists() and not args.no_force:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    weekly = load_weekly_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    six_loss = load_six_loss_weeks(args.source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv")
    six_loss.to_csv(args.output_root / "six_loss_weeks.csv", index=False)

    rows = []
    for year in sorted(weekly.index.year.unique()):
        year_body = weekly[weekly.index.year == year]
        if year_body.empty:
            continue
        rows.append(plot_year(args.output_root / ("%d.png" % year), int(year), weekly, six_loss))

    pd.DataFrame(rows).to_csv(args.output_root / "yearly_chart_index.csv", index=False)
    lines = [
        "# YM Weekly Six-Loss Cluster Charts",
        "",
        "Source: 6-trade-limit broker-like weekly 50% + MA500 replay. Purple candles are weeks where YM used all 6 allowed trades and all 6 were losers. Blue line is the rolling 10-week MA of weekly closes.",
        "",
        "Six-loss week list: [six_loss_weeks.csv](six_loss_weeks.csv)",
        "",
        "| Year | Weeks | Six-Loss Weeks | Chart |",
        "|---:|---:|---:|---|",
    ]
    for row in rows:
        chart = row["chart"]
        lines.append("| {year} | {weeks} | {six_loss_weeks} | [{chart}]({chart}) |".format(**row))
    args.output_root.joinpath("INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
