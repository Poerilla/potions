"""Chart sample Monday-OR breakout trades (wins + losses) on 15m Mon–Fri weeks."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .eurusd_monday_or_breakout_15m import DEFAULT_OUT, resample_15m, week_bounds
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"


def plot_trade(m15: pd.DataFrame, row: pd.Series, out_path: Path, *, chart_idx: int, bucket: str) -> None:
    monday = pd.Timestamp(row["week_monday"])
    mon0, _, sat0 = week_bounds(NY_TZ.localize(datetime.combine(monday.date(), time(0, 0))))
    plot = m15[(m15.index >= mon0) & (m15.index < sat0)].copy()
    if plot.empty:
        return

    entry_ts = pd.Timestamp(row["entry_ts"])
    exit_ts = pd.Timestamp(row["exit_ts"])
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize(NY)
    else:
        entry_ts = entry_ts.tz_convert(NY)
    if exit_ts.tzinfo is None:
        exit_ts = exit_ts.tz_localize(NY)
    else:
        exit_ts = exit_ts.tz_convert(NY)

    side = str(row["side"])
    entry = float(row["entry"])
    exit_px = float(row["exit"])
    stop = float(row["stop"])
    target = float(row["target"])
    mon_h = float(row["monday_high"])
    mon_l = float(row["monday_low"])
    pnl = float(row["pnl_usd"])
    result = str(row["result"])
    reason = str(row["exit_reason"])

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (15.0 / (24.0 * 60.0)) * 0.75
    axis_tz = plot.index.tz
    win_lo = float(min(plot["low"].min(), stop, target, mon_l, entry, exit_px))
    win_hi = float(max(plot["high"].max(), stop, target, mon_h, entry, exit_px))
    span = max(win_hi - win_lo, 1e-5)

    fig, ax = plt.subplots(figsize=(20, 7.5))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.45, alpha=0.85, zorder=3)
    min_body = max(span * 0.0008, 1e-6)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.25,
                alpha=0.8,
                zorder=4,
            )
        )

    # Monday OR band
    ax.axhspan(mon_l, mon_h, color="#90caf9", alpha=0.18, zorder=1, label="Monday OR")
    ax.axhline(mon_h, color="#1565c0", linestyle="--", linewidth=1.3, alpha=0.95, label="Mon high %.5f" % mon_h)
    ax.axhline(mon_l, color="#ef6c00", linestyle="--", linewidth=1.3, alpha=0.95, label="Mon low %.5f" % mon_l)
    ax.axhline(stop, color="#c62828", linestyle=":", linewidth=1.4, alpha=0.95, label="Stop %.5f" % stop)
    ax.axhline(target, color="#6a1b9a", linestyle=":", linewidth=1.4, alpha=0.95, label="Target %.5f" % target)

    result_color = "#168a5a" if result == "win" else "#c43d3d"
    entry_x = mdates.date2num(entry_ts.to_pydatetime())
    exit_x = mdates.date2num(exit_ts.to_pydatetime())
    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.10, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.1, alpha=0.9)
    ax.axvline(exit_x, color=result_color, linewidth=1.1, linestyle="--", alpha=0.9)

    marker = "^" if side == "long" else "v"
    ax.scatter(
        [entry_x],
        [entry],
        marker=marker,
        s=110,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label="Entry %.5f" % entry,
    )
    ax.scatter(
        [exit_x],
        [exit_px],
        marker="X",
        s=95,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label="Exit %.5f (%s)" % (exit_px, reason),
    )

    pad = max(span * 0.06, 1e-5)
    ax.set_ylim(win_lo - pad, win_hi + pad)
    ax.set_title(
        "EURUSD Mon OR 15m — #%03d %s %s | $%+.0f | %s → %s | R=%.5f"
        % (
            chart_idx,
            result.upper(),
            side,
            pnl,
            entry_ts.strftime("%Y-%m-%d %H:%M"),
            exit_ts.strftime("%Y-%m-%d %H:%M"),
            float(row["R"]),
        ),
        fontsize=10,
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.5, alpha=0.7)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=axis_tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d", tz=axis_tz))
    ax.set_xlabel("Mon–Fri week of %s (America/New_York)" % mon0.strftime("%Y-%m-%d"))
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=125, bbox_inches="tight")
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, default=DEFAULT_OUT / "trades.csv")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT / "charts_sample")
    parser.add_argument("--wins", type=int, default=100)
    parser.add_argument("--losses", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args(list(argv) if argv is not None else None)

    trades = pd.read_csv(args.trades)
    rng = random.Random(args.seed)
    win_idx = trades.index[trades["result"] == "win"].tolist()
    loss_idx = trades.index[trades["result"] == "loss"].tolist()
    n_w = min(args.wins, len(win_idx))
    n_l = min(args.losses, len(loss_idx))
    picked = rng.sample(win_idx, n_w) + rng.sample(loss_idx, n_l)
    rng.shuffle(picked)

    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD 15m...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    m15 = resample_15m(concat_all_1m(bars_by_day))
    if m15.index.tz is None:
        m15.index = m15.index.tz_localize(NY)
    else:
        m15.index = m15.index.tz_convert(NY)

    charts_dir = args.output_root / "charts"
    if charts_dir.exists():
        for p in charts_dir.glob("*.png"):
            p.unlink()
    charts_dir.mkdir(parents=True, exist_ok=True)

    rows_meta: List[dict] = []
    for i, ti in enumerate(picked, start=1):
        row = trades.loc[ti]
        stamp = pd.Timestamp(row["entry_ts"]).strftime("%Y-%m-%d_%H%M")
        fname = "%03d_%s_%s_%s.png" % (i, row["result"], row["side"], stamp)
        out = charts_dir / fname
        plot_trade(m15, row, out, chart_idx=i, bucket=str(row["result"]))
        rows_meta.append(
            {
                "idx": i,
                "result": row["result"],
                "side": row["side"],
                "entry": row["entry_ts"],
                "exit": row["exit_ts"],
                "pnl": float(row["pnl_usd"]),
                "reason": row["exit_reason"],
                "path": fname,
            }
        )
        if i % 25 == 0:
            print("  wrote %d/%d" % (i, len(picked)), flush=True)

    lines = [
        "# EURUSD Monday OR breakout — sample trade charts",
        "",
        "Random sample of **%d wins** + **%d losses** (seed `%d`) from the 2R book."
        % (n_w, n_l, args.seed),
        "",
        "Each chart = Mon–Fri week, 15m candles, Monday OR band, entry/exit, stop/target.",
        "",
        "| # | Result | Side | Entry | Exit | P/L | Reason | Chart |",
        "|---:|---|---|---|---|---:|---|---|",
    ]
    for r in rows_meta:
        lines.append(
            "| %d | %s | %s | %s | %s | $%+.0f | %s | [charts/%s](charts/%s) |"
            % (
                r["idx"],
                r["result"],
                r["side"],
                str(r["entry"])[:16],
                str(r["exit"])[:16],
                r["pnl"],
                r["reason"],
                r["path"],
                r["path"],
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Convenience folders
    (args.output_root / "WINS.md").write_text(
        "\n".join(
            ["# Wins", ""]
            + ["- [%03d](charts/%s) $%+.0f" % (r["idx"], r["path"], r["pnl"]) for r in rows_meta if r["result"] == "win"]
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_root / "LOSSES.md").write_text(
        "\n".join(
            ["# Losses", ""]
            + [
                "- [%03d](charts/%s) $%+.0f" % (r["idx"], r["path"], r["pnl"])
                for r in rows_meta
                if r["result"] == "loss"
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print("Wrote %d charts → %s" % (len(rows_meta), args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
