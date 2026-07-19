"""Sample EURUSD Hourly ST+PMC trade charts from broker-like fills.

Even sample of wins/losses with hourly candles, SuperTrend, prior-month close,
stop/target, and entry/exit markers.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
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

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import (
    concat_all_1m,
    load_prev_month_close_map,
    resample_hourly,
)


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
INSTRUMENT = "EURUSD"
POINT_VALUE = 100_000.0
FEE_PER_UNIT = 7.0
ATR_LEN = 14
ATR_MULT = 3.0


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
    exit_reason: str


def _load_config(state_root: Path) -> dict:
    inst = pd.read_csv(state_root / "strategy_instances.csv")
    return json.loads(str(inst.iloc[0]["config_json"]))


def load_trades_from_fills(fills_path: Path, *, stop_pts: float, target_pts: float, daily_path: Path) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    pmc_map = load_prev_month_close_map(daily_path)

    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"].isin(["stop", "target", "eod", "flatten", "close"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        exit_ = exits.iloc[-1]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        exit_px = float(exit_["price"])
        qty = float(entry["quantity"])
        if side == "long":
            pnl_pts = (exit_px - entry_px) * qty
            stop = entry_px - stop_pts
            target = entry_px + target_pts
        else:
            pnl_pts = (entry_px - exit_px) * qty
            stop = entry_px + stop_pts
            target = entry_px - target_pts
        pnl_usd = pnl_pts * POINT_VALUE - FEE_PER_UNIT * qty
        exit_reason = str(exit_["reason"]).lower()
        result = "win" if exit_reason == "target" or pnl_usd > 0 else "loss"
        if exit_reason == "target":
            result = "win"
        elif exit_reason == "stop":
            result = "loss"
        entry_ts = pd.Timestamp(entry["ts"])
        pmc = pmc_map.get((int(entry_ts.year), int(entry_ts.month)), np.nan)
        rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": pd.Timestamp(exit_["ts"]),
                "entry": entry_px,
                "exit": exit_px,
                "stop": stop,
                "target": target,
                "prev_month_close": pmc,
                "pnl_pts": pnl_pts,
                "pnl_usd": pnl_usd,
                "result": result,
                "exit_reason": exit_reason,
            }
        )
    df = pd.DataFrame(rows)
    return df.dropna(subset=["entry_ts", "exit_ts", "entry", "exit", "prev_month_close"])


def sample_trades(df: pd.DataFrame, *, wins: int, losses: int, seed: int) -> List[TradeRow]:
    rng = random.Random(seed)
    win_pool = df[df["result"] == "win"].index.tolist()
    loss_pool = df[df["result"] == "loss"].index.tolist()
    n_wins = min(wins, len(win_pool))
    n_losses = min(losses, len(loss_pool))
    if n_wins < 1 or n_losses < 1:
        raise SystemExit("Need wins and losses; have %dW / %dL" % (len(win_pool), len(loss_pool)))
    picked = rng.sample(win_pool, n_wins) + rng.sample(loss_pool, n_losses)
    rng.shuffle(picked)
    out: List[TradeRow] = []
    for chart_idx, trade_idx in enumerate(picked, start=1):
        r = df.loc[trade_idx]
        out.append(
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
                exit_reason=str(r["exit_reason"]),
            )
        )
    return out


def plot_trade(
    hourly: pd.DataFrame,
    trade: TradeRow,
    out_path: Path,
    *,
    label: str,
    pre_hours: int,
    post_hours: int,
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

    fig, ax = plt.subplots(figsize=(18, 8))
    up = plot["close"] >= plot["open"]
    candle_colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=candle_colors, linewidth=0.85, alpha=0.9, zorder=3)
    price_span = float(plot["high"].max() - plot["low"].min())
    min_body = max(price_span * 0.001, 1e-6)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], candle_colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
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

    if "supertrend" in plot.columns:
        bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
        bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
        ax.plot(plot.index, bull, color="#009c5b", linewidth=2.0, zorder=6, label="Hourly ST bull")
        ax.plot(plot.index, bear, color="#d62728", linewidth=2.0, zorder=6, label="Hourly ST bear")

    ax.axhline(
        trade.prev_month_close,
        color="#1565c0",
        linestyle="--",
        linewidth=1.4,
        zorder=5,
        alpha=0.95,
        label="Prior month close %.5f" % trade.prev_month_close,
    )
    ax.axhline(trade.stop, color="#ef6c00", linestyle=":", linewidth=1.2, alpha=0.85, label="Stop %.5f" % trade.stop)
    ax.axhline(trade.target, color="#6a1b9a", linestyle=":", linewidth=1.2, alpha=0.85, label="Target %.5f" % trade.target)

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
        label="Entry %.5f" % trade.entry,
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
        label="Exit %.5f (%s)" % (trade.exit, trade.exit_reason),
    )

    entry_l = trade.entry_ts.strftime("%Y-%m-%d %H:%M")
    exit_l = trade.exit_ts.strftime("%Y-%m-%d %H:%M")
    ax.set_title(
        "%s — #%02d %s %s | %+0.1f pips ($%+.0f) | %s → %s | ATR(%d)×%g"
        % (
            label,
            trade.idx,
            trade.result.upper(),
            trade.side,
            trade.pnl_pts * 10_000,
            trade.pnl_usd,
            entry_l,
            exit_l,
            ATR_LEN,
            ATR_MULT,
        ),
        fontsize=10,
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=axis_tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d %H:%M", tz=axis_tz))
    ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def write_index(
    out_root: Path,
    trades: List[TradeRow],
    *,
    label: str,
    seed: int,
    wins: int,
    losses: int,
    total_trades: int,
) -> None:
    lines = [
        "# %s — sample trade charts" % label,
        "",
        "Even sample of **%d** trades (%d wins + %d losses), seed `%d`, from **%d** campaign trades."
        % (len(trades), wins, losses, seed, total_trades),
        "",
        "Hourly candles (all sessions), ATR SuperTrend 14×3, prior-month close, stop/target, entry/exit.",
        "",
        "| # | Result | Side | Entry | Exit | Pips | P/L USD | Chart |",
        "|---:|---|---|---|---|---:|---:|---|",
    ]
    for t in sorted(trades, key=lambda item: item.idx):
        entry_d = t.entry_ts.strftime("%Y-%m-%d %H:%M")
        exit_d = t.exit_ts.strftime("%Y-%m-%d %H:%M")
        stamp = t.entry_ts.strftime("%Y-%m-%d_%H%M")
        rel = "charts/%02d_%s_%s.png" % (t.idx, t.result, stamp)
        lines.append(
            "| {idx} | {result} | {side} | {entry} | {exit} | {pips:+.1f} | ${usd:+,.0f} | [{rel}]({rel}) |".format(
                idx=t.idx,
                result=t.result,
                side=t.side,
                entry=entry_d,
                exit=exit_d,
                pips=t.pnl_pts * 10_000,
                usd=t.pnl_usd,
                rel=rel,
            )
        )
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_pack(
    *,
    state_root: Path,
    output_root: Path,
    label: str,
    wins: int,
    losses: int,
    seed: int,
    pre_hours: int,
    post_hours: int,
    force: bool,
    hourly: pd.DataFrame,
    daily_path: Path,
) -> int:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = _load_config(state_root)
    stop_pts = float(cfg.get("stop_pts", 0.0025))
    target_pts = float(cfg.get("target_pts", 0.0075))
    df = load_trades_from_fills(
        state_root / "fills.csv",
        stop_pts=stop_pts,
        target_pts=target_pts,
        daily_path=daily_path,
    )
    picked = sample_trades(df, wins=wins, losses=losses, seed=seed)
    charts_dir = output_root / "charts"
    for trade in picked:
        stamp = trade.entry_ts.strftime("%Y-%m-%d_%H%M")
        out_path = charts_dir / ("%02d_%s_%s.png" % (trade.idx, trade.result, stamp))
        plot_trade(
            hourly,
            trade,
            out_path,
            label=label,
            pre_hours=pre_hours,
            post_hours=post_hours,
        )
        print("  %s %02d/%d %s %s %s" % (label, trade.idx, len(picked), trade.result, trade.side, stamp), flush=True)

    write_index(
        output_root,
        picked,
        label=label,
        seed=seed,
        wins=sum(1 for t in picked if t.result == "win"),
        losses=sum(1 for t in picked if t.result == "loss"),
        total_trades=len(df),
    )
    return len(picked)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD Hourly ST+PMC sample trade charts.")
    parser.add_argument(
        "--st-pmc-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_overnight_sweep" / "st_pmc",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_overnight_sweep" / "st_pmc" / "charts",
    )
    parser.add_argument("--wins", type=int, default=25)
    parser.add_argument("--losses", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--pre-hours", type=int, default=48)
    parser.add_argument("--post-hours", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--only",
        choices=["3r", "ma_bull", "all"],
        default="all",
    )
    args = parser.parse_args(argv)

    packs = []
    if args.only in ("3r", "all"):
        packs.append(
            (
                "eurusd_hourly_st_pmc_sl25_tp75_3r",
                "EURUSD Hourly ST+PMC 25/75 3R",
            )
        )
    if args.only in ("ma_bull", "all"):
        packs.append(
            (
                "eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior",
                "EURUSD Hourly ST+PMC 25/75 + MA bull prior",
            )
        )

    one_m_path, daily_path = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD 1m and building hourly SuperTrend...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    hourly = compute_supertrend(
        resample_hourly(concat_all_1m(bars_by_day)),
        atr_len=ATR_LEN,
        multiplier=ATR_MULT,
    )
    print("  %s hourly bars" % f"{len(hourly):,}", flush=True)

    total = 0
    for slug, label in packs:
        state_root = args.st_pmc_root / "states" / slug
        out = args.output_root / slug
        print("Building %s ..." % label, flush=True)
        n = build_pack(
            state_root=state_root,
            output_root=out,
            label=label,
            wins=args.wins,
            losses=args.losses,
            seed=args.seed,
            pre_hours=args.pre_hours,
            post_hours=args.post_hours,
            force=args.force,
            hourly=hourly,
            daily_path=daily_path,
        )
        total += n
        print("Wrote %d charts → %s" % (n, out), flush=True)

    master = [
        "# EURUSD Hourly ST+PMC sample charts",
        "",
        "Broker-like fills from overnight sweep ST+PMC states.",
        "",
    ]
    for slug, label in packs:
        master.append("- [%s](%s/INDEX.md)" % (label, slug))
    (args.output_root / "INDEX.md").write_text("\n".join(master) + "\n", encoding="utf-8")
    print("Total charts: %d under %s" % (total, args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
