"""EURUSD monthly candles with quarterly prior high/low overlays.

Builds monthly OHLC from ``fx/eurusd_daily.csv`` and charts in **4-year**
chunks (readable; full history is ~275 months). Each quarter is shaded; the
**previous quarter's high and low** are drawn as horizontal guides across
the current quarter.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]


def load_monthly(daily_path: Path) -> pd.DataFrame:
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    monthly = (
        daily.set_index("date")
        .resample("M")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    monthly["year"] = monthly.index.year
    monthly["quarter"] = monthly.index.quarter
    monthly["qkey"] = monthly["year"].astype(str) + "Q" + monthly["quarter"].astype(str)
    return monthly


def quarter_ranges(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for qkey, g in monthly.groupby("qkey", sort=True):
        rows.append(
            {
                "qkey": qkey,
                "year": int(g["year"].iloc[0]),
                "quarter": int(g["quarter"].iloc[0]),
                "start": g.index.min(),
                "end": g.index.max(),
                "high": float(g["high"].max()),
                "low": float(g["low"].min()),
            }
        )
    return pd.DataFrame(rows).sort_values("start").reset_index(drop=True)


def _month_centers(df: pd.DataFrame) -> np.ndarray:
    centers = df.index.to_series().apply(lambda ts: pd.Timestamp(ts.year, ts.month, 15))
    return mdates.date2num(pd.DatetimeIndex(centers).to_pydatetime())


def detect_swing_streaks(monthly: pd.DataFrame) -> pd.DataFrame:
    """Flag months where a 3-bar lower-high or higher-low streak completes.

    - 3 lower highs: ``high[i] < high[i-1] < high[i-2]`` → red down triangle
    - 3 higher lows: ``low[i] > low[i-1] > low[i-2]`` → green up triangle

    Markers alternate colour: after a green ▲, further greens are ignored until a
    red ▼; after a red, further reds are ignored until a green.
    """
    out = monthly.copy()
    highs = out["high"].astype(float)
    lows = out["low"].astype(float)
    raw_lh = (highs < highs.shift(1)) & (highs.shift(1) < highs.shift(2))
    raw_hl = (lows > lows.shift(1)) & (lows.shift(1) > lows.shift(2))

    keep_lh = []
    keep_hl = []
    last: Optional[str] = None  # "green" | "red"
    for lh, hl in zip(raw_lh.fillna(False).tolist(), raw_hl.fillna(False).tolist()):
        show_lh = False
        show_hl = False
        if lh and hl:
            # Both fire same month: take the colour that alternates from last.
            if last == "green":
                show_lh = True
                last = "red"
            elif last == "red":
                show_hl = True
                last = "green"
            else:
                show_hl = True
                last = "green"
        elif hl and last != "green":
            show_hl = True
            last = "green"
        elif lh and last != "red":
            show_lh = True
            last = "red"
        keep_lh.append(show_lh)
        keep_hl.append(show_hl)

    out["three_lower_highs"] = keep_lh
    out["three_higher_lows"] = keep_hl
    return out


def _plot_streak_markers(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    x = _month_centers(df)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    pad = float(np.nanmax(highs) - np.nanmin(lows)) * 0.012

    lh = df["three_lower_highs"].fillna(False).to_numpy(dtype=bool)
    hl = df["three_higher_lows"].fillna(False).to_numpy(dtype=bool)

    if lh.any():
        ax.scatter(
            x[lh],
            highs[lh] + pad,
            marker="v",
            s=110,
            color="#c62828",
            edgecolors="#1b1b1b",
            linewidths=0.4,
            zorder=8,
            label="3 lower highs",
        )
    if hl.any():
        ax.scatter(
            x[hl],
            lows[hl] - pad,
            marker="^",
            s=110,
            color="#2e7d32",
            edgecolors="#1b1b1b",
            linewidths=0.4,
            zorder=8,
            label="3 higher lows",
        )


def _plot_monthly_candles(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    # Matplotlib date units are days. Months are ~30d apart; use ~60% of that
    # so bodies read as real candles instead of thin sticks.
    width = 20.0
    x = _month_centers(df)
    colors = np.where(df["close"].to_numpy() >= df["open"].to_numpy(), "#168a5a", "#c43d3d")
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)

    for xi, o, h, l, c, color in zip(x, opens, highs, lows, closes, colors):
        body_low = min(o, c)
        body_high = max(o, c)
        # Wick above / below the body (not through it) so bodies stay visible.
        if h > body_high:
            ax.vlines(xi, body_high, h, color=color, linewidth=1.35, zorder=3)
        if l < body_low:
            ax.vlines(xi, l, body_low, color=color, linewidth=1.35, zorder=3)
        height = max(body_high - body_low, (h - l) * 0.02 + 1e-6)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, body_low if body_high > body_low else body_low - height / 2.0),
                width,
                height,
                facecolor=color,
                edgecolor="#1b1b1b",
                linewidth=0.55,
                alpha=0.92,
                zorder=4,
            )
        )


def _shade_quarters(ax, quarters: pd.DataFrame, y0: float, y1: float) -> None:
    palette = ["#e3f2fd", "#fff8e1", "#e8f5e9", "#fce4ec"]
    for i, row in quarters.iterrows():
        color = palette[int(row["quarter"]) - 1]
        # Extend shade to month-end of last bar in quarter.
        left = pd.Timestamp(row["start"]).replace(day=1)
        right = pd.Timestamp(row["end"]) + pd.offsets.MonthEnd(0)
        ax.axvspan(left, right, color=color, alpha=0.35, zorder=0)
        mid = left + (right - left) / 2
        ax.text(
            mid,
            y1,
            str(row["qkey"]),
            ha="center",
            va="bottom",
            fontsize=8,
            color="#546e7a",
            zorder=5,
        )


def _prior_quarter_levels(ax, quarters: pd.DataFrame, *, visible_year_start: int) -> None:
    labeled = False
    for i in range(1, len(quarters)):
        prev = quarters.iloc[i - 1]
        cur = quarters.iloc[i]
        if int(cur["year"]) < visible_year_start:
            continue
        left = pd.Timestamp(cur["start"]).replace(day=1)
        right = pd.Timestamp(cur["end"]) + pd.offsets.MonthEnd(0)
        ax.hlines(
            prev["high"],
            left,
            right,
            colors="#1565c0",
            linestyles="--",
            linewidth=1.15,
            alpha=0.9,
            zorder=2,
        )
        ax.hlines(
            prev["low"],
            left,
            right,
            colors="#ef6c00",
            linestyles="--",
            linewidth=1.15,
            alpha=0.9,
            zorder=2,
        )
        if not labeled:
            ax.text(left, prev["high"], "  prior Q high", color="#1565c0", fontsize=7, va="bottom")
            ax.text(left, prev["low"], "  prior Q low", color="#ef6c00", fontsize=7, va="top")
            labeled = True


def chunk_bounds(start_year: int, end_year: int, chunk_years: int) -> List[Tuple[int, int]]:
    out = []
    y = start_year
    while y <= end_year:
        out.append((y, min(y + chunk_years - 1, end_year)))
        y += chunk_years
    return out


def plot_chunk(
    monthly: pd.DataFrame,
    quarters: pd.DataFrame,
    year_start: int,
    year_end: int,
    out_path: Path,
) -> None:
    # Full-history streak flags so patterns spanning chunk edges stay causal.
    marked = detect_swing_streaks(monthly)
    chunk = marked[(marked["year"] >= year_start) & (marked["year"] <= year_end)].copy()
    if chunk.empty:
        return
    qchunk = quarters[(quarters["year"] >= year_start) & (quarters["year"] <= year_end)].copy()
    # Include one prior quarter before chunk for first prior-Q levels.
    prior_idx = quarters.index[quarters["qkey"] == qchunk.iloc[0]["qkey"]]
    if len(prior_idx) and int(prior_idx[0]) > 0:
        qchunk = pd.concat([quarters.iloc[[int(prior_idx[0]) - 1]], qchunk]).drop_duplicates("qkey")

    y0 = float(chunk["low"].min())
    y1 = float(chunk["high"].max())
    pad = (y1 - y0) * 0.06

    fig, ax = plt.subplots(figsize=(20, 9))
    _shade_quarters(ax, qchunk[qchunk["year"] >= year_start], y0 - pad, y1 + pad)
    _prior_quarter_levels(ax, qchunk, visible_year_start=year_start)
    _plot_monthly_candles(ax, chunk)
    _plot_streak_markers(ax, chunk)
    ax.set_title(
        "EURUSD monthly — %d–%d  (prior Q H/L; ▲ 3 higher lows; ▼ 3 lower highs)"
        % (year_start, year_end)
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
    ax.set_xlim(
        pd.Timestamp(date(year_start, 1, 1)),
        pd.Timestamp(date(year_end, 12, 31)),
    )
    ax.set_ylim(y0 - pad * 1.4, y1 + pad * 1.25)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    legend = [
        mpatches.Patch(color="#e3f2fd", label="Q1"),
        mpatches.Patch(color="#fff8e1", label="Q2"),
        mpatches.Patch(color="#e8f5e9", label="Q3"),
        mpatches.Patch(color="#fce4ec", label="Q4"),
        plt.Line2D([0], [0], color="#1565c0", linestyle="--", label="Prior Q high"),
        plt.Line2D([0], [0], color="#ef6c00", linestyle="--", label="Prior Q low"),
        plt.Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            markerfacecolor="#2e7d32",
            markeredgecolor="#1b1b1b",
            markersize=9,
            linestyle="None",
            label="3 higher lows",
        ),
        plt.Line2D(
            [0],
            [0],
            marker="v",
            color="w",
            markerfacecolor="#c62828",
            markeredgecolor="#1b1b1b",
            markersize=9,
            linestyle="None",
            label="3 lower highs",
        ),
    ]
    ax.legend(handles=legend, loc="upper left", fontsize=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_full_overview(monthly: pd.DataFrame, quarters: pd.DataFrame, out_path: Path) -> None:
    """Compressed full-history overview (optional)."""
    y0 = float(monthly["low"].min())
    y1 = float(monthly["high"].max())
    pad = (y1 - y0) * 0.04
    fig, ax = plt.subplots(figsize=(22, 8))
    _shade_quarters(ax, quarters, y0 - pad, y1 + pad)
    _prior_quarter_levels(ax, quarters, visible_year_start=int(monthly["year"].min()))
    _plot_monthly_candles(ax, monthly)
    ax.set_title("EURUSD monthly — full history overview (prior-quarter H/L)")
    ax.set_ylabel("EURUSD")
    ax.grid(True, color="#dedede", linewidth=0.5, alpha=0.7)
    ax.set_ylim(y0 - pad, y1 + pad * 1.1)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", type=Path, default=REPO / "fx" / "eurusd_daily.csv")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_monthly_quarter_charts",
    )
    parser.add_argument("--chunk-years", type=int, default=4)
    parser.add_argument(
        "--full-overview",
        action="store_true",
        help="Also write a dense full-history overview chart.",
    )
    args = parser.parse_args(argv)

    monthly = load_monthly(args.daily)
    quarters = quarter_ranges(monthly)
    charts_dir = args.output_root / "charts"
    if charts_dir.exists():
        for old in charts_dir.glob("*.png"):
            old.unlink()
    args.output_root.mkdir(parents=True, exist_ok=True)

    start_year = int(monthly["year"].min())
    end_year = int(monthly["year"].max())
    chunks = chunk_bounds(start_year, end_year, args.chunk_years)
    built = []
    for y0, y1 in chunks:
        rel = Path("charts") / ("eurusd_monthly_%d_%d.png" % (y0, y1))
        plot_chunk(monthly, quarters, y0, y1, args.output_root / rel)
        built.append(rel)
        print("Wrote %s" % (args.output_root / rel), flush=True)

    overview = None
    if args.full_overview:
        overview = Path("charts") / "eurusd_monthly_full_overview.png"
        plot_full_overview(monthly, quarters, args.output_root / overview)
        print("Wrote %s" % (args.output_root / overview), flush=True)

    lines = [
        "# EURUSD monthly candles + prior-quarter H/L",
        "",
        "Monthly OHLC from daily Histdata EURUSD. Quarters are shaded; dashed lines are the **previous quarter high/low**. "
        "Green ▲ = **3 higher lows** in a row; red ▼ = **3 lower highs** in a row (marked on the completing month). Markers **alternate** colour — same colour is never shown back-to-back.",
        "",
        "- History: **%s → %s** (%d months)"
        % (monthly.index.min().date().isoformat(), monthly.index.max().date().isoformat(), len(monthly)),
        "- Layout: **%d-year** chunks only (candles use day-unit body width)." % args.chunk_years,
        "",
        "## Charts",
        "",
    ]
    if overview is not None:
        lines.append("- Full overview: [`%s`](%s)" % (overview, overview))
    for rel in built:
        lines.append("- [`%s`](%s)" % (rel, rel))
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
