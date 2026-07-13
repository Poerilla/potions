#!/usr/bin/env python3
"""Build plain MNQ 5-minute RTH candle charts for source-data comparison."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
NY_TZ = "America/New_York"
BARS_PATH = ROOT / "mnq/mnq_5min_rth.csv"
OUT_DIR = ROOT / "live/state/mnq_5m_source_comparison_charts_2024_10"
DATES = ["2024-10-07", "2024-10-08", "2024-10-09", "2024-10-11"]


def load_bars() -> pd.DataFrame:
    df = pd.read_csv(BARS_PATH)
    df["ts"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY_TZ)
    df["session_day"] = df["ts"].dt.date.astype(str)
    return df.sort_values("ts").reset_index(drop=True)


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xs = mdates.date2num(bars["ts"].dt.tz_localize(None))
    width = (xs[1] - xs[0]) * 0.72 if len(xs) > 1 else 0.002
    for x, (_, row) in zip(xs, bars.iterrows()):
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        color = "#089981" if c >= o else "#f23645"
        ax.vlines(x, l, h, color=color, linewidth=0.85, alpha=0.95, zorder=3)
        body_low = min(o, c)
        body_height = max(abs(c - o), 0.01)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_low),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                alpha=0.9,
                zorder=4,
            )
        )


def chart_day(bars: pd.DataFrame, day: str) -> tuple[Path, int, str]:
    day_bars = bars[bars["session_day"].eq(day)].copy()
    if day_bars.empty:
        raise SystemExit(f"No MNQ 5-minute bars found for {day}")

    symbol = str(day_bars["symbol"].mode().iloc[0])
    csv_path = OUT_DIR / f"mnq_5m_rth_{day}.csv"
    png_path = OUT_DIR / f"mnq_5m_rth_{day}.png"
    day_bars[["ts_event", "open", "high", "low", "close", "volume", "symbol"]].to_csv(csv_path, index=False)

    fig, ax = plt.subplots(figsize=(15.5, 7.8))
    draw_candles(ax, day_bars)

    xs = mdates.date2num(day_bars["ts"].dt.tz_localize(None))
    ax.set_xlim(xs.min() - 0.004, xs.max() + 0.006)
    pad = max((float(day_bars["high"].max()) - float(day_bars["low"].min())) * 0.04, 8.0)
    ax.set_ylim(float(day_bars["low"].min()) - pad, float(day_bars["high"].max()) + pad)
    ax.set_title(f"MNQ 5-minute RTH candles | {day} | {symbol}", loc="left", fontsize=13)
    ax.set_ylabel("Price")
    ax.grid(True, axis="y", alpha=0.2)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[30]))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(png_path, dpi=170)
    plt.close(fig)
    return png_path, len(day_bars), symbol


def write_index(rows: list[tuple[str, Path, int, str]]) -> None:
    lines = [
        "# MNQ 5-Minute RTH Source Comparison Charts",
        "",
        f"Source: `{BARS_PATH.relative_to(ROOT)}`.",
        "",
        "Charts are plain 5-minute RTH candles from the same front-month cache used by the local StrategyPlugin chart/replay tooling. No strategy overlays, levels, fills, or indicators are drawn.",
        "",
        "| Date | Symbol | Bars | Chart | CSV |",
        "|---|---:|---:|---|---|",
    ]
    for day, png_path, n_bars, symbol in rows:
        csv_name = f"mnq_5m_rth_{day}.csv"
        lines.append(f"| {day} | `{symbol}` | {n_bars} | [{png_path.name}]({png_path.name}) | [{csv_name}]({csv_name}) |")
    lines.append("")
    (OUT_DIR / "INDEX.md").write_text("\n".join(lines))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bars = load_bars()
    rows = []
    for day in DATES:
        png_path, n_bars, symbol = chart_day(bars, day)
        rows.append((day, png_path, n_bars, symbol))
    write_index(rows)


if __name__ == "__main__":
    main()
