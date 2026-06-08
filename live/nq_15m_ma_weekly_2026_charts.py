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


def load_15m_with_ma() -> pd.DataFrame:
    cfg = MARKETS["nq"]
    print("Loading NQ 1m DBN...", flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    one_min = concat_all_1m(by_day).sort_index()
    start = pd.Timestamp("2025-12-01", tz=NY)
    end = pd.Timestamp("2026-03-09", tz=NY)
    one_min = one_min[(one_min.index >= start) & (one_min.index < end)].copy()
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
    bars["ma50"] = pd.to_numeric(bars["close"], errors="coerce").rolling(50).mean()
    bars["ma150"] = pd.to_numeric(bars["close"], errors="coerce").rolling(150).mean()
    bars["ma_spread"] = bars["ma50"] - bars["ma150"]
    bars["regime"] = np.where(bars["ma50"] > bars["ma150"], "bull", np.where(bars["ma50"] < bars["ma150"], "bear", "flat"))
    return bars


def week_starts_for_2026(bars: pd.DataFrame) -> list[pd.Timestamp]:
    in_2026 = bars[(bars.index >= pd.Timestamp("2026-01-01", tz=NY)) & (bars.index < pd.Timestamp("2027-01-01", tz=NY))]
    weeks = []
    for period in sorted(in_2026.index.to_period("W-SUN").unique()):
        start = period.start_time.tz_localize(NY)
        if start not in weeks:
            weeks.append(start)
    return weeks


def shade_rth(ax, start: pd.Timestamp, end: pd.Timestamp) -> None:
    day = start.normalize()
    while day <= end.normalize():
        rth_start = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(NY)
        rth_end = pd.Timestamp.combine(day.date(), time(16, 0)).tz_localize(NY)
        if rth_end >= start and rth_start <= end:
            ax.axvspan(max(rth_start, start), min(rth_end, end), color="#f4f6f8", alpha=0.75, zorder=0)
        ax.axvline(day, color="#9e9e9e", linewidth=0.65, linestyle=":", alpha=0.55, zorder=1)
        day += pd.Timedelta(days=1)


def summarize_week(df: pd.DataFrame) -> dict[str, object]:
    if df.empty:
        return {}
    valid = df[df["ma150"].notna()]
    bull_pct = 100.0 * (valid["ma50"] > valid["ma150"]).mean() if not valid.empty else 0.0
    crosses = int((valid["regime"] != valid["regime"].shift(1)).sum()) if not valid.empty else 0
    return {
        "bars": len(df),
        "start_close": float(df["close"].iloc[0]),
        "end_close": float(df["close"].iloc[-1]),
        "range_pts": float(df["high"].max() - df["low"].min()),
        "net_pts": float(df["close"].iloc[-1] - df["close"].iloc[0]),
        "bull_pct": bull_pct,
        "crosses": max(crosses - 1, 0),
        "ending_regime": str(valid["regime"].iloc[-1]) if not valid.empty else "unknown",
    }


def build_charts(output_root: Path, force: bool) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    bars = load_15m_with_ma()
    weeks = week_starts_for_2026(bars)
    rows: list[dict[str, object]] = []
    for idx, week_start in enumerate(weeks, start=1):
        week_end = week_start + pd.Timedelta(days=7)
        plot_start = week_start - pd.Timedelta(hours=8)
        plot = bars[(bars.index >= plot_start) & (bars.index < week_end)].copy()
        week_only = bars[(bars.index >= max(week_start, pd.Timestamp("2026-01-01", tz=NY))) & (bars.index < week_end)].copy()
        if week_only.empty:
            continue
        stats = summarize_week(week_only)
        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(20, 9.5),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        shade_rth(ax, week_start, week_end)
        plot_candles(ax, plot, width_days=(15 / (24 * 60)) * 0.68)
        ax.plot(plot.index, plot["ma50"], color="#0057b8", linewidth=1.35, label="15m MA50")
        ax.plot(plot.index, plot["ma150"], color="#7b1fa2", linewidth=1.55, label="15m MA150")
        bull = plot[plot["ma50"] > plot["ma150"]]
        bear = plot[plot["ma50"] < plot["ma150"]]
        if not bull.empty:
            ax.scatter(bull.index, bull["ma50"], s=4, color="#0057b8", alpha=0.18, zorder=5)
        if not bear.empty:
            ax.scatter(bear.index, bear["ma50"], s=4, color="#c62828", alpha=0.18, zorder=5)
        ax.axvline(week_start, color="#111111", linewidth=1.0, linestyle="--", alpha=0.75)
        ax.set_title(
            "NQ 15m MA50/MA150 Weekly Trend Context - %s - %s - %s %.0f pts"
            % (week_start.date().isoformat(), (week_end - pd.Timedelta(days=1)).date().isoformat(), stats["ending_regime"], stats["net_pts"])
        )
        ax.set_ylabel("NQ")
        ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
        ax.legend(loc="upper left", fontsize=9)

        colors = np.where(plot["close"] >= plot["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(plot.index, plot["volume"], width=(15 / (24 * 60)) * 0.68, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=plot.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %H:%M", tz=plot.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        for label in vol_ax.get_xticklabels():
            label.set_rotation(75)
            label.set_fontsize(8)

        rel = Path("charts") / ("%02d_%s.png" % (idx, week_start.date().isoformat()))
        fig.savefig(output_root / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "week_start": week_start.date().isoformat(),
                "week_end": (week_end - pd.Timedelta(days=1)).date().isoformat(),
                "bars": stats["bars"],
                "net_pts": stats["net_pts"],
                "range_pts": stats["range_pts"],
                "bull_pct": stats["bull_pct"],
                "crosses": stats["crosses"],
                "ending_regime": stats["ending_regime"],
                "chart": str(rel),
            }
        )
    pd.DataFrame(rows).to_csv(output_root / "weekly_summary.csv", index=False)
    lines = [
        "# NQ 2026 Weekly 15m MA50/MA150 Study",
        "",
        "One chart per available 2026 week. Candles are 15-minute NQ bars from the full available 1-minute stream, with MA50 and MA150 calculated on 15-minute closes. Light background bands mark regular trading hours.",
        "",
        "Intent: inspect whether a short-term 15-minute MA50/MA150 regime captures trend persistence that lasts longer than one day.",
        "",
        "| # | Week | Net Pts | Range Pts | Bull % | Crosses | Ending Regime | Chart |",
        "|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {idx} | {week_start} | {net_pts:,.2f} | {range_pts:,.2f} | {bull_pct:.1f}% | {crosses} | {ending_regime} | [{chart}]({chart}) |".format(
                **row
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build NQ 2026 weekly 15m MA50/MA150 charts.")
    parser.add_argument("--output-root", type=Path, default=REPO / "nq/case_studies/nq_2026_weekly_15m_ma50_150")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_charts(args.output_root, force=not args.no_force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
