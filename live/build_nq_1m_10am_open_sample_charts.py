from __future__ import annotations

import argparse
import random
import shutil
from datetime import date, time
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"


def plot_candles(ax, df: pd.DataFrame, width_days: float) -> None:
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.75, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), 0.01)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.35,
                alpha=0.82,
                zorder=4,
            )
        )


def ten_am_open(rth: pd.DataFrame) -> tuple[pd.Timestamp, float] | None:
    exact = rth[rth.index.time == time(10, 0)]
    if exact.empty:
        exact = rth[rth.index >= pd.Timestamp.combine(rth.index[0].date(), time(10, 0)).tz_localize(NY)].head(1)
    if exact.empty:
        return None
    row = exact.iloc[0]
    return pd.Timestamp(exact.index[0]), float(row["open"])


def build_charts(*, output_root: Path, sample_size: int, seed: int, atr_len: int, atr_mult: float, force: bool) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    chart_dir = output_root / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    cfg = MARKETS["nq"]
    print("Loading NQ 1m bars...", flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    rng = random.Random(seed)
    candidate_days = sorted(day for day, df in by_day.items() if df is not None and not df.empty)
    rng.shuffle(candidate_days)
    selected: list[date] = []
    rth_by_day: dict[date, pd.DataFrame] = {}
    for day in candidate_days:
        rth = _rth_bars(by_day.get(day), day)
        if rth.empty or len(rth) < 300 or ten_am_open(rth) is None:
            continue
        selected.append(day)
        rth_by_day[day] = rth
        if len(selected) >= sample_size:
            break
    selected = sorted(selected)
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(selected, start=1):
        rth = rth_by_day[day]
        marker = ten_am_open(rth)
        if marker is None:
            continue
        marker_ts, marker_open = marker

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(18, 8.5),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        rth_with_st = compute_supertrend(rth.copy(), atr_len=atr_len, multiplier=atr_mult)
        plot_candles(ax, rth_with_st, width_days=(1 / (24 * 60)) * 0.72)
        bull = rth_with_st["supertrend"].where(rth_with_st["supertrend_trend"] == 1)
        bear = rth_with_st["supertrend"].where(rth_with_st["supertrend_trend"] == -1)
        ax.plot(rth_with_st.index, bull, color="#009c5b", linewidth=1.15, label="1m ST ATR%d x %.1f bull" % (atr_len, atr_mult))
        ax.plot(rth_with_st.index, bear, color="#d62728", linewidth=1.15, label="1m ST ATR%d x %.1f bear" % (atr_len, atr_mult))
        ax.axhline(marker_open, color="#0057b8", linewidth=1.35, linestyle="-", alpha=0.88)
        ax.axvline(marker_ts, color="#0057b8", linewidth=1.1, linestyle="--", alpha=0.72)
        ax.annotate(
            "10:00 open %.2f" % marker_open,
            xy=(marker_ts, marker_open),
            xytext=(8, 18),
            textcoords="offset points",
            color="#0057b8",
            fontsize=8,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": "#0057b8", "lw": 0.9},
        )
        ax.set_title("NQ 1m RTH candles with 10:00 candle open - %s" % day.isoformat())
        ax.set_ylabel("NQ")
        ax.grid(True, color="#e2e2e2", linewidth=0.55, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)

        colors = np.where(rth["close"] >= rth["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(rth.index, rth["volume"], width=(1 / (24 * 60)) * 0.72, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[30, 0], tz=rth.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=rth.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        for label in vol_ax.get_xticklabels():
            label.set_rotation(90)
            label.set_fontsize(7)
        ax.set_xlim(rth.index[0], rth.index[-1])

        rel = Path("charts") / ("%03d_%s.png" % (idx, day.isoformat()))
        fig.savefig(output_root / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": day.isoformat(),
                "rth_start": pd.Timestamp(rth.index[0]).isoformat(),
                "rth_end": pd.Timestamp(rth.index[-1]).isoformat(),
                "ten_am_ts": marker_ts.isoformat(),
                "ten_am_open": marker_open,
                "chart": str(rel),
            }
        )
        if idx % 25 == 0:
            print("  charted %d/%d" % (idx, len(selected)), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# NQ 1m 10:00 Open Sample Charts",
        "",
        "Sample of **%d** NQ RTH sessions, selected deterministically with seed `%d` from available full-ish RTH days." % (len(rows), seed),
        "",
        "Each chart shows 1-minute RTH candles from the session open through RTH end. The blue horizontal line is the opening price of the 10:00 ET candle. The green/red trailing line is 1-minute Supertrend `ATR(%d) x %.1f`." % (atr_len, atr_mult),
        "",
        "| # | Session | 10:00 Open | Chart |",
        "|---:|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {idx} | {session} | {ten_am_open:.2f} | [{chart}]({chart}) |".format(**row)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build 100 NQ 1m RTH candle charts with 10:00 candle-open line.")
    parser.add_argument("--output-root", type=Path, default=REPO / "nq/case_studies/nq_1m_10am_open_random_100")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=2.0)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_charts(
        output_root=args.output_root,
        sample_size=args.sample_size,
        seed=args.seed,
        atr_len=args.atr_len,
        atr_mult=args.atr_mult,
        force=not args.no_force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
