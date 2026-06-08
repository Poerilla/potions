from __future__ import annotations

import argparse
import shutil
from datetime import time
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"


def plot_candles(ax, df: pd.DataFrame, width_days: float) -> None:
    if df.empty:
        return
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.8, alpha=0.88, zorder=3)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(float(o), float(c))
        height = max(abs(float(c) - float(o)), 0.01)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.35,
                alpha=0.78,
                zorder=4,
            )
        )


def load_15m(ma_window: int) -> pd.DataFrame:
    cfg = MARKETS["nq"]
    print("Loading NQ 1m DBN...", flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    one_min = concat_all_1m(by_day).sort_index()
    bars = (
        one_min.resample("15min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    bars = compute_supertrend(bars, atr_len=14, multiplier=3.0)
    ma_col = "ma%d" % ma_window
    above_col = "above_ma%d" % ma_window
    bars[ma_col] = pd.to_numeric(bars["close"], errors="coerce").rolling(ma_window).mean()
    bars[above_col] = bars["close"] > bars[ma_col]
    bars["st_bull"] = bars["supertrend_trend"] == 1
    bars["aligned_regime"] = np.where(
        bars[above_col] & bars["st_bull"],
        "bull_align",
        np.where((~bars[above_col]) & (~bars["st_bull"]), "bear_align", "mixed"),
    )
    return bars


def recent_week_starts(bars: pd.DataFrame, count: int) -> list[pd.Timestamp]:
    periods = sorted(bars.index.to_period("W-SUN").unique())
    starts = [p.start_time.tz_localize(NY) for p in periods]
    starts = [s for s in starts if bars[(bars.index >= s) & (bars.index < s + pd.Timedelta(days=7))].shape[0] >= 20]
    return starts[-count:]


def shade_rth(ax, start: pd.Timestamp, end: pd.Timestamp) -> None:
    day = start.normalize()
    while day <= end.normalize():
        rth_start = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(NY)
        rth_end = pd.Timestamp.combine(day.date(), time(16, 0)).tz_localize(NY)
        if rth_end >= start and rth_start <= end:
            ax.axvspan(max(rth_start, start), min(rth_end, end), color="#f4f6f8", alpha=0.75, zorder=0)
        ax.axvline(day, color="#9e9e9e", linewidth=0.65, linestyle=":", alpha=0.55, zorder=1)
        day += pd.Timedelta(days=1)


def summarize_week(df: pd.DataFrame, ma_window: int) -> dict[str, object]:
    ma_col = "ma%d" % ma_window
    above_col = "above_ma%d" % ma_window
    valid = df[df[ma_col].notna()]
    if valid.empty:
        above_ma = st_bull = bull_align = bear_align = mixed = 0.0
        st_flips = align_changes = 0
        ending = "unknown"
    else:
        above_ma = 100.0 * valid[above_col].mean()
        st_bull = 100.0 * valid["st_bull"].mean()
        bull_align = 100.0 * (valid["aligned_regime"] == "bull_align").mean()
        bear_align = 100.0 * (valid["aligned_regime"] == "bear_align").mean()
        mixed = 100.0 * (valid["aligned_regime"] == "mixed").mean()
        st_flips = int((valid["supertrend_trend"] != valid["supertrend_trend"].shift(1)).sum()) - 1
        align_changes = int((valid["aligned_regime"] != valid["aligned_regime"].shift(1)).sum()) - 1
        ending = str(valid["aligned_regime"].iloc[-1])
    return {
        "bars": len(df),
        "net_pts": float(df["close"].iloc[-1] - df["close"].iloc[0]),
        "range_pts": float(df["high"].max() - df["low"].min()),
        "above_ma_pct": above_ma,
        "st_bull_pct": st_bull,
        "bull_align_pct": bull_align,
        "bear_align_pct": bear_align,
        "mixed_pct": mixed,
        "st_flips": max(st_flips, 0),
        "align_changes": max(align_changes, 0),
        "ending_regime": ending,
    }


def build_charts(output_root: Path, week_count: int, ma_window: int, force: bool) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    bars = load_15m(ma_window)
    weeks = recent_week_starts(bars, week_count)
    rows: list[dict[str, object]] = []
    for idx, week_start in enumerate(weeks, start=1):
        week_end = week_start + pd.Timedelta(days=7)
        plot_start = week_start - pd.Timedelta(hours=8)
        plot = bars[(bars.index >= plot_start) & (bars.index < week_end)].copy()
        week = bars[(bars.index >= week_start) & (bars.index < week_end)].copy()
        if week.empty:
            continue
        stats = summarize_week(week, ma_window)
        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(20, 9.5),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        shade_rth(ax, week_start, week_end)
        plot_candles(ax, plot, width_days=(15 / (24 * 60)) * 0.68)
        ma_col = "ma%d" % ma_window
        ax.plot(plot.index, plot[ma_col], color="#1f3a93", linewidth=1.65, label="15m MA%d" % ma_window)
        bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
        bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
        ax.step(plot.index, bull, where="post", color="#009c5b", linewidth=1.25, label="15m ST ATR14 x 3 bull")
        ax.step(plot.index, bear, where="post", color="#d62728", linewidth=1.25, label="15m ST ATR14 x 3 bear")
        aligned_bull = plot[plot["aligned_regime"] == "bull_align"]
        aligned_bear = plot[plot["aligned_regime"] == "bear_align"]
        if not aligned_bull.empty:
            ax.scatter(aligned_bull.index, aligned_bull["close"], s=5, color="#009c5b", alpha=0.22, zorder=5)
        if not aligned_bear.empty:
            ax.scatter(aligned_bear.index, aligned_bear["close"], s=5, color="#c62828", alpha=0.22, zorder=5)
        ax.axvline(week_start, color="#111111", linewidth=1.0, linestyle="--", alpha=0.75)
        ax.set_title(
            "NQ 15m MA%d + Supertrend - %s to %s - %s %.0f pts"
            % (ma_window, week_start.date().isoformat(), (week_end - pd.Timedelta(days=1)).date().isoformat(), stats["ending_regime"], stats["net_pts"])
        )
        ax.set_ylabel("NQ")
        ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
        ax.legend(loc="upper left", fontsize=9)

        colors = np.where(plot["close"] >= plot["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(plot.index, plot["volume"], width=(15 / (24 * 60)) * 0.68, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=plot.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=plot.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        for label in vol_ax.get_xticklabels():
            label.set_rotation(78)
            label.set_fontsize(7)

        rel = Path("charts") / ("%03d_%s.png" % (idx, week_start.date().isoformat()))
        fig.savefig(output_root / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        row = {
            "idx": idx,
            "week_start": week_start.date().isoformat(),
            "week_end": (week_end - pd.Timedelta(days=1)).date().isoformat(),
            "chart": str(rel),
        }
        row.update(stats)
        rows.append(row)
        if idx % 20 == 0:
            print("  charted %d/%d" % (idx, len(weeks)), flush=True)
    pd.DataFrame(rows).to_csv(output_root / "weekly_summary.csv", index=False)
    lines = [
        "# NQ Recent %d Weeks 15m MA%d + Supertrend Study" % (week_count, ma_window),
        "",
        "One chart per recent NQ week. Candles are 15-minute bars from the full available 1-minute stream. The only overlays are 15-minute MA%d and 15-minute Supertrend `ATR(14) x 3.0`. Light bands mark regular trading hours." % ma_window,
        "",
        "Green/red close dots mark bars where price/MA%d and Supertrend agree: above MA%d plus bullish ST, or below MA%d plus bearish ST." % (ma_window, ma_window, ma_window),
        "",
        "| # | Week | Net Pts | Range Pts | Above MA%d | ST Bull | Bull Align | Bear Align | ST Flips | Regime Changes | Ending | Chart |" % ma_window,
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {idx} | {week_start} | {net_pts:,.2f} | {range_pts:,.2f} | {above_ma_pct:.1f}% | {st_bull_pct:.1f}% | {bull_align_pct:.1f}% | {bear_align_pct:.1f}% | {st_flips} | {align_changes} | {ending_regime} | [{chart}]({chart}) |".format(
                **row
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build recent N-week NQ 15m MA + Supertrend charts.")
    parser.add_argument("--output-root", type=Path, default=REPO / "nq/case_studies/nq_recent_100_weekly_15m_ma200_supertrend")
    parser.add_argument("--weeks", type=int, default=100)
    parser.add_argument("--ma-window", type=int, default=200)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_charts(args.output_root, week_count=args.weeks, ma_window=args.ma_window, force=not args.no_force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
