from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .v2b_strategy_cross_market_replay import MARKETS


REPO = Path(__file__).resolve().parents[1]


def plot_candles(ax, df: pd.DataFrame, width_days: float = 0.62) -> None:
    x = mdates.date2num(df["date"].dt.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.9, alpha=0.9)
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
                linewidth=0.45,
                alpha=0.8,
            )
        )


def build_market(market_name: str, output_root: Path) -> dict[str, object]:
    cfg = MARKETS[market_name]
    out_dir = output_root / market_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(cfg.daily_path, parse_dates=["date"]).sort_values("date")
    daily["ma50"] = pd.to_numeric(daily["close"], errors="coerce").rolling(50).mean()
    rows = []
    for year, group in daily.groupby(daily["date"].dt.year):
        if group.empty:
            continue
        pad = daily[(daily["date"] >= group["date"].iloc[0] - pd.Timedelta(days=90)) & (daily["date"] <= group["date"].iloc[-1])]
        fig, (ax, vol_ax) = plt.subplots(2, 1, figsize=(18, 8.5), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04})
        plot_candles(ax, pad)
        ax.plot(pad["date"], pad["ma50"], color="#1f3a93", linewidth=1.65, label="50-day MA")
        ax.axvspan(group["date"].iloc[0], group["date"].iloc[-1], color="#f4f6f8", alpha=0.55, zorder=0)
        ax.set_title("%s daily candles + 50-day MA - %d" % (cfg.instrument, int(year)))
        ax.set_ylabel(cfg.instrument)
        ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
        ax.legend(loc="upper left", fontsize=9)
        if "volume" in pad.columns:
            colors = np.where(pad["close"] >= pad["open"], "#168a5a", "#c43d3d")
            vol_ax.bar(pad["date"], pad["volume"], color=colors, alpha=0.45, width=0.75)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        for label in vol_ax.get_xticklabels():
            label.set_rotation(70)
            label.set_fontsize(7)
        rel = Path("charts") / ("%d.png" % int(year))
        fig.savefig(out_dir / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "year": int(year),
                "bars": int(len(group)),
                "net_pts": float(group["close"].iloc[-1] - group["open"].iloc[0]),
                "above_ma50_pct": float((group["close"] > group["ma50"]).mean() * 100.0),
                "chart": str(rel),
            }
        )
    pd.DataFrame(rows).to_csv(out_dir / "yearly_summary.csv", index=False)
    lines = [
        "# %s Daily 50-Day MA Year Charts" % cfg.instrument,
        "",
        "One chart per calendar year. Candles are daily front-month continuous bars from `%s`; the blue line is a 50-day moving average calculated on daily closes. Each chart includes about 90 prior calendar days as warmup context when available." % cfg.daily_path,
        "",
        "| Year | Bars | Net Pts | Above MA50 | Chart |",
        "|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append("| {year} | {bars} | {net_pts:,.2f} | {above_ma50_pct:.1f}% | [{chart}]({chart}) |".format(**row))
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return {"market": market_name, "instrument": cfg.instrument, "years": len(rows), "index": str(out_dir / "INDEX.md")}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build daily 50MA yearly chart packs.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/daily_ma50_yearly_charts")
    parser.add_argument("--market", action="append", choices=sorted(MARKETS), default=None)
    args = parser.parse_args(argv)
    if args.output_root.exists():
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    rows = [build_market(market, args.output_root) for market in (args.market or ["nq"])]
    lines = [
        "# Daily 50-Day MA Year Charts",
        "",
        "| Market | Instrument | Years | Report |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        rel = Path(row["index"]).resolve().relative_to(args.output_root.resolve())
        lines.append("| {market} | {instrument} | {years} | [{rel}]({rel}) |".format(rel=rel, **row))
    (args.output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
