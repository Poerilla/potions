from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .ym_weekly_high_loss_day_charts import load_high_loss_days
from .ym_weekly_six_loss_charts import load_weekly_bars


REPO = Path(__file__).resolve().parents[1]


def load_15m_bars(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert("America/New_York")
    bars = bars.sort_values("ts")
    for col in ["open", "high", "low", "close", "volume"]:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")
    bars = bars.dropna(subset=["open", "high", "low", "close"]).copy()
    bars = bars.set_index("ts").sort_index()
    bars["ma500_15m"] = bars["close"].rolling(500).mean()
    bars["date"] = bars.index.date
    bars["week_start"] = (bars.index.normalize() - pd.to_timedelta(bars.index.weekday, unit="D")).date
    return bars


def load_fills(path: Path) -> pd.DataFrame:
    fills = pd.read_csv(path)
    fills["entry_ts"] = pd.to_datetime(fills["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    fills["exit_ts"] = pd.to_datetime(fills["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    fills["entry_date"] = fills["entry_ts"].dt.date
    fills["usd"] = pd.to_numeric(fills["usd"], errors="coerce").fillna(0.0)
    fills["points"] = pd.to_numeric(fills["points"], errors="coerce").fillna(0.0)
    for col in ["entry_price", "exit_price"]:
        fills[col] = pd.to_numeric(fills[col], errors="coerce")
    return fills


def hourly_bars(day_15m: pd.DataFrame) -> pd.DataFrame:
    return (
        day_15m.resample("1h", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            ma500_15m=("ma500_15m", "last"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def draw_candles(ax, bars: pd.DataFrame) -> None:
    width = 42.0 / (24.0 * 60.0)
    for ts, row in bars.iterrows():
        x = mdates.date2num(ts.to_pydatetime())
        up = float(row["close"]) >= float(row["open"])
        color = "#2e7d32" if up else "#c62828"
        edge = "#1b5e20" if up else "#8e0000"
        ax.vlines(x, float(row["low"]), float(row["high"]), color=edge, linewidth=1.05, alpha=0.85)
        lower = min(float(row["open"]), float(row["close"]))
        height = abs(float(row["close"]) - float(row["open"]))
        ax.add_patch(
            plt.Rectangle(
                (x - width / 2.0, lower),
                width,
                max(height, 0.5),
                facecolor=color,
                edgecolor=edge,
                linewidth=0.8,
                alpha=0.82,
            )
        )


def plot_day(
    out_path: Path,
    day_15m: pd.DataFrame,
    fills: pd.DataFrame,
    trade_day: pd.Timestamp,
    weekly_ma10: float,
    high_loss_row: pd.Series | None,
) -> dict[str, object]:
    one_h = hourly_bars(day_15m)
    fig, (ax, eq_ax) = plt.subplots(
        2,
        1,
        figsize=(18, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05},
    )
    draw_candles(ax, one_h)
    ax.plot(day_15m.index, day_15m["ma500_15m"], color="#1f3a93", linewidth=1.35, label="15m MA500")
    ax.axhline(weekly_ma10, color="#7b1fa2", linestyle="--", linewidth=1.35, label="10-week MA")
    ax.text(day_15m.index[0], weekly_ma10, "10W MA %.2f" % weekly_ma10, color="#7b1fa2", fontsize=8, va="bottom")

    if not fills.empty:
        for _, tr in fills.iterrows():
            is_long = str(tr["direction"]).lower().startswith("long")
            color = "#008c5a" if is_long else "#c62828"
            marker = "^" if is_long else "v"
            ax.scatter([tr["entry_ts"]], [tr["entry_price"]], color=color, marker=marker, s=48, zorder=8)
            ax.scatter([tr["exit_ts"]], [tr["exit_price"]], color="#111111", marker="x", s=48, zorder=8)
            ax.plot([tr["entry_ts"], tr["exit_ts"]], [tr["entry_price"], tr["exit_price"]], color=color, linewidth=0.85, alpha=0.72)
        eq = fills.sort_values("exit_ts").set_index("exit_ts")["usd"].cumsum()
        eq_ax.step(eq.index, eq.values, where="post", color="#1f3a93", linewidth=1.2)
    eq_ax.axhline(0, color="#777777", linewidth=0.7)

    high_loss_text = ""
    if high_loss_row is not None:
        high_loss_text = " | high-loss day: %d losses / %d trades" % (int(high_loss_row["losses"]), int(high_loss_row["trades"]))
    ax.set_title(
        "YM 10W MA interaction %s | trades %d | net $%.0f%s"
        % (trade_day.date().isoformat(), len(fills), float(fills["usd"].sum()) if not fills.empty else 0.0, high_loss_text)
    )
    ax.set_ylabel("YM")
    ax.grid(True, color="#e4e4e4", linewidth=0.55, alpha=0.72)
    ax.legend(loc="upper left", fontsize=8)
    eq_ax.set_ylabel("Day P/L")
    eq_ax.grid(True, color="#e9e9e9", linewidth=0.5)
    eq_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=day_15m.index.tz))
    eq_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=day_15m.index.tz))
    eq_ax.set_xlabel("Time (America/New_York)")
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)
    return {
        "date": trade_day.date().isoformat(),
        "year": trade_day.year,
        "trades": int(len(fills)),
        "losses": int((fills["usd"] < 0).sum()) if not fills.empty else 0,
        "net": float(fills["usd"].sum()) if not fills.empty else 0.0,
        "weekly_ma10": weekly_ma10,
        "high_loss_day": high_loss_row is not None,
        "chart": str(out_path.name),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YM day charts for 10-week MA interactions.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts/ym_10week_ma_interaction_days",
    )
    parser.add_argument("--min-losses", type=int, default=2)
    parser.add_argument("--only-trade-days", action="store_true", default=True)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    if args.output_root.exists() and not args.no_force:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    bars = load_15m_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    weekly = load_weekly_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    fills = load_fills(args.source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv")
    high_loss_days, _week_summary = load_high_loss_days(args.source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv", args.min_losses)
    high_loss_map = {row["entry_date"].date(): row for _, row in high_loss_days.iterrows()}

    rows = []
    trade_dates = set(fills["entry_date"])
    for day, day_15m in bars.groupby("date"):
        if args.only_trade_days and day not in trade_dates:
            continue
        week_start = pd.Timestamp(day) - pd.Timedelta(days=pd.Timestamp(day).weekday())
        if week_start not in weekly.index:
            continue
        weekly_ma10 = weekly.loc[week_start, "ma10"]
        if pd.isna(weekly_ma10):
            continue
        if not (float(day_15m["low"].min()) <= float(weekly_ma10) <= float(day_15m["high"].max())):
            continue
        day_fills = fills[fills["entry_date"] == day].copy()
        if day_fills.empty:
            continue
        year_dir = args.output_root / str(pd.Timestamp(day).year)
        year_dir.mkdir(parents=True, exist_ok=True)
        out_path = year_dir / ("%s.png" % pd.Timestamp(day).date().isoformat())
        rows.append(plot_day(out_path, day_15m, day_fills, pd.Timestamp(day), float(weekly_ma10), high_loss_map.get(day)))

    index = pd.DataFrame(rows).sort_values(["year", "date"]) if rows else pd.DataFrame()
    index.to_csv(args.output_root / "interaction_days.csv", index=False)

    lines = [
        "# YM 10-Week MA Interaction Days",
        "",
        "Source: 6-trade-limit broker-like weekly 50% + MA500 replay. Charts use 1-hour candles, the 15-minute MA500 overlay, and a horizontal rolling 10-week MA. Only trade days where the day's high/low touched or crossed the 10-week MA are included.",
        "",
        "Interaction day table: [interaction_days.csv](interaction_days.csv)",
        "",
        "| Year | Days | High-Loss Days | Net | Folder |",
        "|---:|---:|---:|---:|---|",
    ]
    if not index.empty:
        for year, grp in index.groupby("year"):
            folder = "%d/" % int(year)
            lines.append(
                "| %d | %d | %d | $%.2f | [%s](%s) |"
                % (int(year), len(grp), int(grp["high_loss_day"].sum()), float(grp["net"].sum()), folder, folder)
            )
        for year, grp in index.groupby("year"):
            year_dir = args.output_root / str(int(year))
            year_lines = [
                "# YM 10W MA Interaction Days %d" % int(year),
                "",
                "| Date | Trades | Losses | Net | 10W MA | High-Loss Day | Chart |",
                "|---|---:|---:|---:|---:|---|---|",
            ]
            for _, row in grp.iterrows():
                chart = row["chart"]
                year_lines.append(
                    "| {date} | {trades} | {losses} | ${net:,.2f} | {weekly_ma10:.2f} | {high_loss_day} | [{chart}]({chart}) |".format(**row)
                )
            (year_dir / "INDEX.md").write_text("\n".join(year_lines), encoding="utf-8")
    args.output_root.joinpath("INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    print("Interaction trade days: %d" % len(index), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
