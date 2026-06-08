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

from .ym_10week_ma_interaction_day_charts import load_15m_bars, load_fills
from .ym_weekly_high_loss_day_charts import load_high_loss_days
from .ym_weekly_six_loss_charts import load_weekly_bars


REPO = Path(__file__).resolve().parents[1]


def hourly_bars(week_15m: pd.DataFrame) -> pd.DataFrame:
    return (
        week_15m.resample("1h", label="right", closed="right")
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
        ax.vlines(x, float(row["low"]), float(row["high"]), color=edge, linewidth=1.0, alpha=0.85)
        lower = min(float(row["open"]), float(row["close"]))
        height = abs(float(row["close"]) - float(row["open"]))
        ax.add_patch(
            plt.Rectangle(
                (x - width / 2.0, lower),
                width,
                max(height, 0.5),
                facecolor=color,
                edgecolor=edge,
                linewidth=0.75,
                alpha=0.82,
            )
        )


def previous_week_levels(weekly: pd.DataFrame, week_start: pd.Timestamp) -> dict[str, float] | None:
    prev_start = week_start - pd.Timedelta(days=7)
    if prev_start not in weekly.index:
        return None
    prev = weekly.loc[prev_start]
    high = float(prev["high"])
    low = float(prev["low"])
    return {
        "PWH": high,
        "PWL": low,
        "PW 50%": low + 0.5 * (high - low),
        "PWC": float(prev["close"]),
    }


def interaction_weeks(bars: pd.DataFrame, weekly: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    rows = []
    trade_dates = set(fills["entry_date"])
    for day, day_15m in bars.groupby("date"):
        if day not in trade_dates:
            continue
        week_start = pd.Timestamp(day) - pd.Timedelta(days=pd.Timestamp(day).weekday())
        if week_start not in weekly.index:
            continue
        ma10 = weekly.loc[week_start, "ma10"]
        if pd.isna(ma10):
            continue
        if float(day_15m["low"].min()) <= float(ma10) <= float(day_15m["high"].max()):
            rows.append({"week_start": week_start, "date": pd.Timestamp(day), "ma10": float(ma10)})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return (
        out.groupby("week_start")
        .agg(interaction_days=("date", "size"), first_interaction=("date", "min"), ma10=("ma10", "last"))
        .reset_index()
        .sort_values("week_start")
    )


def plot_week(
    out_path: Path,
    week_start: pd.Timestamp,
    week_15m: pd.DataFrame,
    weekly: pd.DataFrame,
    fills: pd.DataFrame,
    high_loss_days: pd.DataFrame,
    interaction_days: int,
    ma10: float,
) -> dict[str, object]:
    one_h = hourly_bars(week_15m)
    levels = previous_week_levels(weekly, week_start)
    if one_h.empty or not levels:
        return {}
    week_start_tz = week_start.tz_localize("America/New_York") if week_start.tzinfo is None else week_start
    week_end_tz = week_start_tz + pd.Timedelta(days=7)
    week_fills = fills[(fills["entry_ts"] >= week_start_tz) & (fills["entry_ts"] < week_end_tz)].copy()
    hl_days = set(high_loss_days["entry_date"].dt.date)
    high_loss_count = int(sum(1 for day in set(week_fills["entry_date"]) if day in hl_days))

    fig, (ax, eq_ax) = plt.subplots(
        2,
        1,
        figsize=(20, 9.5),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05},
    )
    draw_candles(ax, one_h)
    ax.plot(week_15m.index, week_15m["ma500_15m"], color="#1f3a93", linewidth=1.25, label="15m MA500")

    line_specs = [
        ("PWH", "#7b1fa2", "-"),
        ("PWL", "#7b1fa2", "-"),
        ("PW 50%", "#555555", "--"),
        ("PWC", "#f57c00", "-."),
    ]
    x_text = one_h.index[0] + (one_h.index[-1] - one_h.index[0]) * 0.01
    for label, color, style in line_specs:
        value = levels[label]
        ax.axhline(value, color=color, linestyle=style, linewidth=1.0, alpha=0.82, label=label)
        ax.text(x_text, value, "%s %.2f" % (label, value), color=color, fontsize=7, va="bottom", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.58, "pad": 1.0})

    ax.axhline(ma10, color="#0097a7", linestyle="-", linewidth=1.35, alpha=0.9, label="10W MA")
    ax.text(x_text, ma10, "10W MA %.2f" % ma10, color="#007c89", fontsize=7, va="bottom", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.58, "pad": 1.0})

    if not week_fills.empty:
        for _, tr in week_fills.iterrows():
            is_long = str(tr["direction"]).lower().startswith("long")
            color = "#008c5a" if is_long else "#c62828"
            marker = "^" if is_long else "v"
            ax.scatter([tr["entry_ts"]], [tr["entry_price"]], color=color, marker=marker, s=48, zorder=8)
            ax.scatter([tr["exit_ts"]], [tr["exit_price"]], color="#111111", marker="x", s=48, zorder=8)
            ax.plot([tr["entry_ts"], tr["exit_ts"]], [tr["entry_price"], tr["exit_price"]], color=color, linewidth=0.85, alpha=0.72)
        eq = week_fills.sort_values("exit_ts").set_index("exit_ts")["usd"].cumsum()
        eq_ax.step(eq.index, eq.values, where="post", color="#1f3a93", linewidth=1.2)
    eq_ax.axhline(0, color="#777777", linewidth=0.7)

    net = float(week_fills["usd"].sum()) if not week_fills.empty else 0.0
    losses = int((week_fills["usd"] < 0).sum()) if not week_fills.empty else 0
    title = (
        "YM full week 10W MA interaction %s | interaction days %d | trades %d | losses %d | net $%.0f | high-loss days %d"
        % (week_start.date().isoformat(), interaction_days, len(week_fills), losses, net, high_loss_count)
    )
    ax.set_title(title)
    ax.set_ylabel("YM")
    ax.grid(True, color="#e4e4e4", linewidth=0.55, alpha=0.72)
    ax.legend(loc="upper left", fontsize=8)
    eq_ax.set_ylabel("Week P/L")
    eq_ax.grid(True, color="#e9e9e9", linewidth=0.5)
    eq_ax.xaxis.set_major_locator(mdates.HourLocator(interval=8, tz=week_15m.index.tz))
    eq_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=week_15m.index.tz))
    for label in eq_ax.get_xticklabels():
        label.set_rotation(75)
        label.set_fontsize(7)
    eq_ax.set_xlabel("Time (America/New_York)")
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)

    return {
        "week_start": week_start.date().isoformat(),
        "year": int(week_start.year),
        "interaction_days": int(interaction_days),
        "trades": int(len(week_fills)),
        "losses": losses,
        "net": net,
        "high_loss_days": high_loss_count,
        "ma10": float(ma10),
        "chart": out_path.name,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full-week YM charts for 10-week MA interaction weeks.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts/ym_10week_ma_interaction_weeks",
    )
    parser.add_argument("--min-losses", type=int, default=2)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    if args.output_root.exists() and not args.no_force:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    bars = load_15m_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    weekly = load_weekly_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    fills = load_fills(args.source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv")
    high_loss_days, _ = load_high_loss_days(args.source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv", args.min_losses)
    weeks = interaction_weeks(bars, weekly, fills)
    weeks.to_csv(args.output_root / "interaction_weeks.csv", index=False)

    rows = []
    for _, wk in weeks.iterrows():
        week_start = pd.Timestamp(wk["week_start"])
        week_end = week_start + pd.Timedelta(days=7)
        week_15m = bars[(bars.index >= week_start.tz_localize("America/New_York")) & (bars.index < week_end.tz_localize("America/New_York"))].copy()
        if week_15m.empty:
            continue
        year_dir = args.output_root / str(int(week_start.year))
        year_dir.mkdir(parents=True, exist_ok=True)
        out_path = year_dir / ("%s.png" % week_start.date().isoformat())
        row = plot_week(out_path, week_start, week_15m, weekly, fills, high_loss_days, int(wk["interaction_days"]), float(wk["ma10"]))
        if row:
            rows.append(row)

    index = pd.DataFrame(rows).sort_values(["year", "week_start"]) if rows else pd.DataFrame()
    index.to_csv(args.output_root / "chart_index.csv", index=False)

    lines = [
        "# YM Full-Week 10-Week MA Interaction Charts",
        "",
        "Source: 6-trade-limit broker-like weekly 50% + MA500 replay. Full-week charts use 1-hour candles with PWH/PWL/PW50/PWC, the rolling 10-week MA, 15-minute MA500, and actual broker-like fills.",
        "",
        "Interaction weeks: [interaction_weeks.csv](interaction_weeks.csv)",
        "",
        "Chart index: [chart_index.csv](chart_index.csv)",
        "",
        "| Year | Weeks | High-Loss Weeks | Net | Folder |",
        "|---:|---:|---:|---:|---|",
    ]
    if not index.empty:
        for year, grp in index.groupby("year"):
            folder = "%d/" % int(year)
            lines.append(
                "| %d | %d | %d | $%.2f | [%s](%s) |"
                % (int(year), len(grp), int((grp["high_loss_days"] > 0).sum()), float(grp["net"].sum()), folder, folder)
            )
        for year, grp in index.groupby("year"):
            year_dir = args.output_root / str(int(year))
            year_lines = [
                "# YM Full-Week 10W MA Interaction %d" % int(year),
                "",
                "| Week | Interaction Days | Trades | Losses | Net | High-Loss Days | 10W MA | Chart |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
            for _, row in grp.iterrows():
                chart = row["chart"]
                year_lines.append(
                    "| {week_start} | {interaction_days} | {trades} | {losses} | ${net:,.2f} | {high_loss_days} | {ma10:.2f} | [{chart}]({chart}) |".format(**row)
                )
            (year_dir / "INDEX.md").write_text("\n".join(year_lines), encoding="utf-8")
    args.output_root.joinpath("INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    print("Interaction weeks: %d" % len(index), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
