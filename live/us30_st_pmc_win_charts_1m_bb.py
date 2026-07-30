"""US30 ST+PMC sl50_tp150_3r — sample winning trades on 1m candles + Bollinger bands."""

from __future__ import annotations

import argparse
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

from .replay_audit import POINT_VALUES

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
OUT = REPO / "live" / "state" / "us30_futures_strats_sweep" / "charts" / "sl50_tp150_3r_wins_1m_bb"
STATE = (
    REPO
    / "live"
    / "state"
    / "us30_futures_strats_sweep"
    / "st_pmc"
    / "states"
    / "us30_hourly_st_pmc_sl50_tp150_3r"
)
POINT_VALUE = float(POINT_VALUES["US30"])
FEE = 1.50
BB_LEN = 20
BB_STD = 2.0
EXIT_REASONS = {"stop", "target", "tp1", "eod", "flatten", "close", "runner_stop", "wide_stop"}


@dataclass
class TradeRow:
    idx: int
    trade_id: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    stop: float
    target: float
    pnl_pts: float
    pnl_usd: float
    exit_reason: str


def load_win_trades(fills_path: Path, *, stop_pts: float = 50.0, target_pts: float = 150.0) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"].isin(EXIT_REASONS)]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        # FIFO-ish: use last exit for closed trade; sum partial if scaleout
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        entry_ts = pd.Timestamp(entry["ts"])
        qty = float(entry["quantity"])
        pnl = 0.0
        exit_ts = None
        exit_px = None
        exit_reason = ""
        closed_qty = 0.0
        for _, x in exits.iterrows():
            q = float(x["quantity"])
            px = float(x["price"])
            if side == "long" and str(x["side"]).lower() == "sell":
                pnl += (px - entry_px) * q
                closed_qty += q
            elif side == "short" and str(x["side"]).lower() == "buy":
                pnl += (entry_px - px) * q
                closed_qty += q
            else:
                continue
            exit_ts = pd.Timestamp(x["ts"])
            exit_px = px
            exit_reason = str(x["reason"]).lower()
        if exit_ts is None or closed_qty <= 0:
            continue
        pnl_usd = pnl * POINT_VALUE - FEE * qty
        if pnl_usd <= 0:
            continue
        if side == "long":
            stop = entry_px - stop_pts
            target = entry_px + target_pts
        else:
            stop = entry_px + stop_pts
            target = entry_px - target_pts
        rows.append(
            {
                "trade_id": str(trade_id),
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "entry": entry_px,
                "exit": float(exit_px),
                "stop": stop,
                "target": target,
                "pnl_pts": pnl,
                "pnl_usd": pnl_usd,
                "exit_reason": exit_reason,
            }
        )
    return pd.DataFrame(rows)


def bollinger(close: pd.Series, length: int = BB_LEN, n_std: float = BB_STD) -> pd.DataFrame:
    mid = close.rolling(length, min_periods=length).mean()
    std = close.rolling(length, min_periods=length).std()
    return pd.DataFrame({"bb_mid": mid, "bb_upper": mid + n_std * std, "bb_lower": mid - n_std * std})


def plot_trade(m1: pd.DataFrame, trade: TradeRow, out_path: Path) -> bool:
    if m1.empty:
        return False
    bb = bollinger(m1["close"])
    plot = m1.join(bb)

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (1.0 / (24.0 * 60.0)) * 0.85
    result_color = "#168a5a"
    entry_x = mdates.date2num(trade.entry_ts.to_pydatetime())
    exit_x = mdates.date2num(trade.exit_ts.to_pydatetime())

    fig, ax = plt.subplots(figsize=(18, 8))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.6, alpha=0.85, zorder=3)
    span = float(plot["high"].max() - plot["low"].min())
    min_body = max(span * 0.0008, 1e-6)
    for xi, o, c, col in zip(x, plot["open"], plot["close"], colors):
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, min(o, c)),
                width,
                max(abs(c - o), min_body),
                facecolor=col,
                edgecolor=col,
                linewidth=0.3,
                alpha=0.85,
                zorder=4,
            )
        )

    ax.plot(plot.index, plot["bb_mid"], color="#1565c0", linewidth=1.2, label="BB mid (%d)" % BB_LEN, zorder=5)
    ax.plot(plot.index, plot["bb_upper"], color="#6a1b9a", linewidth=1.0, linestyle="--", label="BB upper", zorder=5)
    ax.plot(plot.index, plot["bb_lower"], color="#6a1b9a", linewidth=1.0, linestyle="--", label="BB lower", zorder=5)
    ax.fill_between(plot.index, plot["bb_lower"], plot["bb_upper"], color="#6a1b9a", alpha=0.06, zorder=1)

    ax.axhline(trade.entry, color="#333333", linestyle="--", linewidth=1.1, label="Entry %.1f" % trade.entry)
    ax.axhline(trade.stop, color="#ef6c00", linestyle=":", linewidth=1.2, label="Stop %.1f" % trade.stop)
    ax.axhline(trade.target, color="#2e7d32", linestyle=":", linewidth=1.2, label="Target %.1f" % trade.target)
    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.08, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.1)
    ax.axvline(exit_x, color=result_color, linewidth=1.1, linestyle="--")

    marker = "^" if trade.side == "long" else "v"
    ax.scatter([entry_x], [trade.entry], marker=marker, s=110, color=result_color, edgecolors="white", zorder=8)
    ax.scatter([exit_x], [trade.exit], marker="X", s=90, color=result_color, edgecolors="white", zorder=8)

    ax.set_title(
        "US30 ST+PMC 50/150 — #%02d WIN %s | %+0.1f pts ($%+.0f) | %s → %s (%s) | 1m + BB(%d,%.0fσ)"
        % (
            trade.idx,
            trade.side,
            trade.pnl_pts,
            trade.pnl_usd,
            trade.entry_ts.strftime("%Y-%m-%d %H:%M"),
            trade.exit_ts.strftime("%H:%M"),
            trade.exit_reason,
            BB_LEN,
            BB_STD,
        ),
        fontsize=10,
    )
    ax.set_ylabel("US30")
    ax.grid(True, color="#d9d9d9", linewidth=0.5, alpha=0.7)
    ax.legend(loc="upper left", fontsize=7, ncol=3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=plot.index.tz))
    ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wins", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--pad-hours", type=float, default=2.0, help="1m context hours before entry / after exit")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    fills = STATE / "fills.csv"
    if not fills.exists():
        raise SystemExit("Missing fills: %s" % fills)

    out = Path(args.out)
    if args.force and out.exists():
        shutil.rmtree(out)
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)

    wins_df = load_win_trades(fills)
    if wins_df.empty:
        raise SystemExit("No winning trades found")
    rng = random.Random(args.seed)
    n = min(args.wins, len(wins_df))
    picked_idx = rng.sample(wins_df.index.tolist(), n)
    picked = wins_df.loc[picked_idx].sort_values("entry_ts")

    # Load 1m once (large) then slice — faster than per-trade CSV reads
    print("Loading US30 1m…")
    path = REPO / "fx" / "us30_1m.csv"
    raw = pd.read_csv(path)
    ts_col = "ts_event" if "ts_event" in raw.columns else "ts"
    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True).dt.tz_convert(NY)
    raw = raw.set_index("ts").sort_index()
    for c in ("open", "high", "low", "close"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw.dropna(subset=["open", "high", "low", "close"])

    pad = timedelta(hours=float(args.pad_hours))
    lines = [
        "# US30 ST+PMC sl50_tp150_3r — %d winning trades (1m + Bollinger)" % n,
        "",
        "Source: [`us30_hourly_st_pmc_sl50_tp150_3r`](../../st_pmc/states/us30_hourly_st_pmc_sl50_tp150_3r/).",
        "1-minute candles with Bollinger Bands (%d, %.1fσ). Seed `%d`." % (BB_LEN, BB_STD, args.seed),
        "",
        "| # | Side | Entry | Exit | Pts | $ | Reason | Chart |",
        "|---:|---|---|---|---:|---:|---|---|",
    ]
    written = 0
    for i, (_, r) in enumerate(picked.iterrows(), start=1):
        trade = TradeRow(
            idx=i,
            trade_id=str(r["trade_id"]),
            side=str(r["side"]),
            entry_ts=pd.Timestamp(r["entry_ts"]),
            exit_ts=pd.Timestamp(r["exit_ts"]),
            entry=float(r["entry"]),
            exit=float(r["exit"]),
            stop=float(r["stop"]),
            target=float(r["target"]),
            pnl_pts=float(r["pnl_pts"]),
            pnl_usd=float(r["pnl_usd"]),
            exit_reason=str(r["exit_reason"]),
        )
        window = raw.loc[(raw.index >= trade.entry_ts - pad) & (raw.index <= trade.exit_ts + pad)]
        stamp = trade.entry_ts.strftime("%Y-%m-%d_%H%M")
        rel = "charts/%02d_win_%s_%s.png" % (i, trade.side, stamp)
        ok = plot_trade(window, trade, out / rel)
        if not ok:
            print("SKIP empty 1m window", trade.trade_id)
            continue
        written += 1
        lines.append(
            "| %d | %s | %s | %s | %+.1f | %+.0f | %s | [%s](%s) |"
            % (
                i,
                trade.side,
                trade.entry_ts.strftime("%Y-%m-%d %H:%M"),
                trade.exit_ts.strftime("%Y-%m-%d %H:%M"),
                trade.pnl_pts,
                trade.pnl_usd,
                trade.exit_reason,
                rel,
                rel,
            )
        )
        if i % 10 == 0:
            print("  plotted %d/%d" % (i, n))

    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %d charts → %s" % (written, charts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
