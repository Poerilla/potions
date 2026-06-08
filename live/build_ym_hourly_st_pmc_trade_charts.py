from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"

sys.path[:0] = [str(REPO.parent), str(MNQ_ROOT), str(SCRIPTS), str(CASE)]

from potions.live.build_ym_1m_atr_supertrend_sample import compute_supertrend  # noqa: E402
from potions.live.ym_hourly_st_pmc_retest_replay import (  # noqa: E402
    concat_all_1m,
    load_1m_by_ny_date_any,
    load_prev_month_close_map,
    resample_hourly,
)


@dataclass
class TradeRow:
    idx: int
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    stop: float
    target: float
    prev_month_close: float
    pnl_pts: float
    pnl_usd: float
    result: str


def load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    for col in ("entry", "exit", "stop", "target", "prev_month_close", "pnl_pts", "pnl_usd"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_broker_like_units(path: Path, daily_path: Path, *, stop_pts: float, target_pts: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    df["entry"] = pd.to_numeric(df["entry_price"], errors="coerce")
    df["exit"] = pd.to_numeric(df["exit_price"], errors="coerce")
    df["pnl_pts"] = pd.to_numeric(df["points"], errors="coerce")
    df["pnl_usd"] = pd.to_numeric(df["usd"], errors="coerce") - 1.50
    df["side"] = df["direction"].astype(str).str.lower()
    df["result"] = np.where(df["exit_reason"].astype(str).str.lower() == "target", "win", "loss")
    is_long = df["side"].str.startswith("long")
    df["stop"] = np.where(is_long, df["entry"] - stop_pts, df["entry"] + stop_pts)
    df["target"] = np.where(is_long, df["entry"] + target_pts, df["entry"] - target_pts)
    pmc_map = load_prev_month_close_map(daily_path)
    df["prev_month_close"] = [
        pmc_map.get((int(ts.year), int(ts.month)), np.nan)
        for ts in df["entry_ts"]
    ]
    return df[
        [
            "side",
            "entry_ts",
            "exit_ts",
            "entry",
            "exit",
            "stop",
            "target",
            "prev_month_close",
            "pnl_pts",
            "pnl_usd",
            "result",
        ]
    ].dropna(subset=["entry_ts", "exit_ts", "entry", "exit", "prev_month_close"])


def sample_trades(df: pd.DataFrame, *, wins: int, losses: int, seed: int) -> List[TradeRow]:
    rng = random.Random(seed)
    win_pool = df[df["result"] == "win"].index.tolist()
    loss_pool = df[df["result"] == "loss"].index.tolist()
    if len(win_pool) < wins or len(loss_pool) < losses:
        raise SystemExit(f"Need {wins}W/{losses}L but have {len(win_pool)}W/{len(loss_pool)}L")
    picked = rng.sample(win_pool, wins) + rng.sample(loss_pool, losses)
    rng.shuffle(picked)
    rows: List[TradeRow] = []
    for chart_idx, trade_idx in enumerate(picked, start=1):
        r = df.loc[trade_idx]
        rows.append(
            TradeRow(
                idx=chart_idx,
                side=str(r["side"]),
                entry_ts=pd.Timestamp(r["entry_ts"]),
                exit_ts=pd.Timestamp(r["exit_ts"]),
                entry=float(r["entry"]),
                exit=float(r["exit"]),
                stop=float(r["stop"]),
                target=float(r["target"]),
                prev_month_close=float(r["prev_month_close"]),
                pnl_pts=float(r["pnl_pts"]),
                pnl_usd=float(r["pnl_usd"]),
                result=str(r["result"]),
            )
        )
    return rows


def plot_trade(
    hourly: pd.DataFrame,
    trade: TradeRow,
    out_path: Path,
    *,
    pre_hours: int,
    post_hours: int,
    atr_len: int,
    atr_mult: float,
) -> None:
    start = trade.entry_ts - timedelta(hours=pre_hours)
    end = trade.exit_ts + timedelta(hours=post_hours)
    plot = hourly[(hourly.index >= start) & (hourly.index <= end)].copy()
    if plot.empty:
        return

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (1.0 / 24.0) * 0.72
    axis_tz = plot.index.tz
    entry_x = mdates.date2num(trade.entry_ts.to_pydatetime())
    exit_x = mdates.date2num(trade.exit_ts.to_pydatetime())

    result_color = "#168a5a" if trade.result == "win" else "#c43d3d"
    fig, (ax, vol_ax) = plt.subplots(
        2,
        1,
        figsize=(18, 8),
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        sharex=True,
    )

    up = plot["close"] >= plot["open"]
    candle_colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=candle_colors, linewidth=0.85, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], candle_colors):
        bottom = min(o, c)
        height = max(abs(c - o), 0.01)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                alpha=0.85,
                zorder=4,
            )
        )

    bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
    bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
    ax.plot(plot.index, bull, color="#009c5b", linewidth=2.2, zorder=6, label="Hourly ST bullish")
    ax.plot(plot.index, bear, color="#d62728", linewidth=2.2, zorder=6, label="Hourly ST bearish")

    ax.axhline(
        trade.prev_month_close,
        color="#1565c0",
        linestyle="--",
        linewidth=1.4,
        zorder=5,
        alpha=0.95,
        label=f"Prior month close ({trade.prev_month_close:,.0f})",
    )
    ax.axhline(trade.stop, color="#ef6c00", linestyle=":", linewidth=1.2, alpha=0.85, label=f"Stop {trade.stop:,.0f}")
    ax.axhline(trade.target, color="#6a1b9a", linestyle=":", linewidth=1.2, alpha=0.85, label=f"Target {trade.target:,.0f}")

    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.10, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.2, linestyle="-", alpha=0.9)
    ax.axvline(exit_x, color=result_color, linewidth=1.2, linestyle="--", alpha=0.9)

    marker = "^" if trade.side == "long" else "v"
    ax.scatter(
        [entry_x],
        [trade.entry],
        marker=marker,
        s=120,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label=f"Entry {trade.entry:,.0f}",
    )
    ax.scatter(
        [exit_x],
        [trade.exit],
        marker="X",
        s=100,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label=f"Exit {trade.exit:,.0f}",
    )

    entry_l = trade.entry_ts.strftime("%Y-%m-%d %H:%M")
    exit_l = trade.exit_ts.strftime("%Y-%m-%d %H:%M")
    ax.set_title(
        f"YM hourly ST+PMC — #{trade.idx:02d} {trade.result.upper()} {trade.side} "
        f"| {trade.pnl_pts:+.0f} pts (${trade.pnl_usd:+,.0f}) "
        f"| entry {entry_l} → exit {exit_l} "
        f"| ATR({atr_len}) x {atr_mult:g}",
        fontsize=10,
    )
    ax.set_ylabel("YM price")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=7, ncol=2)

    vol_ax.bar(plot.index, plot.get("volume", 0), width=width, color=candle_colors, alpha=0.5)
    vol_ax.set_ylabel("Vol")
    vol_ax.grid(True, axis="y", color="#e2e2e2", linewidth=0.6, alpha=0.75)
    vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=axis_tz))
    vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d %H:%M", tz=axis_tz))
    vol_ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def write_index(out_root: Path, trades: List[TradeRow], *, seed: int, wins: int, losses: int) -> None:
    lines = [
        "# YM Hourly ST + PMC Trade Chart Sample",
        "",
        f"Sample: `{len(trades)}` trades (`{wins}` wins + `{losses}` losses), seed `{seed}`.",
        "Each chart: hourly candles (all sessions), Supertrend stops, prior month close, entry/exit markers.",
        "",
        "| # | Result | Side | Entry | Exit | P/L pts | P/L USD | Chart |",
        "|---:|---|---|---|---|---:|---:|---|",
    ]
    for t in sorted(trades, key=lambda item: item.idx):
        entry_d = t.entry_ts.strftime("%Y-%m-%d %H:%M")
        exit_d = t.exit_ts.strftime("%Y-%m-%d %H:%M")
        rel = f"charts/{t.idx:02d}_{t.result}_{entry_d.replace(' ', '_').replace(':', '')}.png"
        lines.append(
            f"| {t.idx} | {t.result} | {t.side} | {entry_d} | {exit_d} | "
            f"{t.pnl_pts:+.0f} | ${t.pnl_usd:+,.0f} | [{rel}]({rel}) |"
        )
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Chart sample wins/losses from hourly ST+PMC replay.")
    parser.add_argument(
        "--trades-csv",
        type=Path,
        default=REPO / "ym" / "case_studies" / "ym_hourly_st_pmc_retest_replay" / "trades.csv",
    )
    parser.add_argument(
        "--unit-fills-csv",
        type=Path,
        default=None,
        help="Broker-like audit unit_fills.csv. If set, this supersedes --trades-csv.",
    )
    parser.add_argument("--daily", type=Path, default=REPO / "ym" / "ym_daily.csv")
    parser.add_argument(
        "--dbn",
        type=Path,
        default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=REPO / "ym" / "case_studies" / "ym_hourly_st_pmc_retest_replay" / "trade_charts_50",
    )
    parser.add_argument("--wins", type=int, default=25)
    parser.add_argument("--losses", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--pre-hours", type=int, default=48)
    parser.add_argument("--post-hours", type=int, default=12)
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--stop-pts", type=float, default=50.0)
    parser.add_argument("--target-pts", type=float, default=150.0)
    args = parser.parse_args(argv)

    if args.unit_fills_csv:
        df = load_broker_like_units(args.unit_fills_csv, args.daily, stop_pts=args.stop_pts, target_pts=args.target_pts)
    else:
        df = load_trades(args.trades_csv)
    picked = sample_trades(df, wins=args.wins, losses=args.losses, seed=args.seed)

    print("Loading YM 1m and building hourly Supertrend...", flush=True)
    gby = load_1m_by_ny_date_any(args.dbn.resolve(), "ym")
    hourly = compute_supertrend(
        resample_hourly(concat_all_1m(gby)),
        atr_len=args.atr_len,
        multiplier=args.atr_mult,
    )
    print(f"  {len(hourly):,} hourly bars loaded", flush=True)

    charts_dir = args.out_root / "charts"
    for trade in picked:
        stamp = trade.entry_ts.strftime("%Y-%m-%d_%H%M")
        out_path = charts_dir / f"{trade.idx:02d}_{trade.result}_{stamp}.png"
        plot_trade(
            hourly,
            trade,
            out_path,
            pre_hours=args.pre_hours,
            post_hours=args.post_hours,
            atr_len=args.atr_len,
            atr_mult=args.atr_mult,
        )
        print(f"Built {trade.idx:02d}/{len(picked)}: {trade.result} {trade.side} {stamp}", flush=True)

    write_index(args.out_root, picked, seed=args.seed, wins=args.wins, losses=args.losses)
    print(f"Wrote {args.out_root / 'INDEX.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
