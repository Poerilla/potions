"""Sample win/loss trade charts for a trend_momentum sweep (or TF-study) cell.

Default: XAUUSD 1h — highest N/S sleeve in the multi-market sweep that has
enough closed trades for a balanced 50-win / 50-loss pack (NAS100 1h ranks
#1 by N/S but only ~16 wins).
"""

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
from .trend_momentum_common import FEE

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
EXIT_REASONS = {"stop", "trend_end", "flatten", "eod_close", "target", "close"}


@dataclass
class TradeRow:
    idx: int
    trade_id: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    pnl_pts: float
    pnl_usd: float
    result: str
    exit_reason: str


def load_bars(bars_path: Path) -> pd.DataFrame:
    df = pd.read_csv(bars_path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
    df = df.set_index("ts").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"])


def load_trades(fills_path: Path, instrument: str) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    pv = float(POINT_VALUES.get(instrument, 1.0))

    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"].isin(EXIT_REASONS)]
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
        else:
            pnl_pts = (entry_px - exit_px) * qty
        pnl_usd = pnl_pts * pv - FEE * qty
        result = "win" if pnl_usd > 0 else "loss"
        rows.append(
            {
                "trade_id": str(trade_id),
                "side": side,
                "entry_ts": pd.Timestamp(entry["ts"]),
                "exit_ts": pd.Timestamp(exit_["ts"]),
                "entry": entry_px,
                "exit": exit_px,
                "pnl_pts": pnl_pts,
                "pnl_usd": pnl_usd,
                "result": result,
                "exit_reason": str(exit_["reason"]).lower(),
            }
        )
    return pd.DataFrame(rows)


def sample_trades(df: pd.DataFrame, *, wins: int, losses: int, seed: int) -> List[TradeRow]:
    rng = random.Random(seed)
    win_pool = df[df["result"] == "win"].index.tolist()
    loss_pool = df[df["result"] == "loss"].index.tolist()
    n_wins = min(wins, len(win_pool))
    n_losses = min(losses, len(loss_pool))
    if n_wins < 1 or n_losses < 1:
        raise SystemExit(
            "Need wins and losses; have %dW / %dL (requested %dW / %dL)"
            % (len(win_pool), len(loss_pool), wins, losses)
        )
    if n_wins < wins or n_losses < losses:
        print(
            "WARNING: requested %dW/%dL but only %dW/%dL available — using %dW/%dL"
            % (wins, losses, len(win_pool), len(loss_pool), n_wins, n_losses)
        )
    picked = rng.sample(win_pool, n_wins) + rng.sample(loss_pool, n_losses)
    # Stable chart order: wins first (001..), then losses
    win_picked = [i for i in picked if df.loc[i, "result"] == "win"]
    loss_picked = [i for i in picked if df.loc[i, "result"] == "loss"]
    ordered = win_picked + loss_picked
    out: List[TradeRow] = []
    for chart_idx, trade_idx in enumerate(ordered, start=1):
        r = df.loc[trade_idx]
        out.append(
            TradeRow(
                idx=chart_idx,
                trade_id=str(r["trade_id"]),
                side=str(r["side"]),
                entry_ts=pd.Timestamp(r["entry_ts"]),
                exit_ts=pd.Timestamp(r["exit_ts"]),
                entry=float(r["entry"]),
                exit=float(r["exit"]),
                pnl_pts=float(r["pnl_pts"]),
                pnl_usd=float(r["pnl_usd"]),
                result=str(r["result"]),
                exit_reason=str(r["exit_reason"]),
            )
        )
    return out


def _bar_width_days(tf: str) -> float:
    tf = tf.lower().strip()
    if tf.endswith("m") and tf[:-1].isdigit():
        return (int(tf[:-1]) / (24.0 * 60.0)) * 0.72
    if tf.endswith("h") and tf[:-1].isdigit():
        return (int(tf[:-1]) / 24.0) * 0.72
    if tf in {"d", "1d", "daily"}:
        return 0.72
    return (1.0 / 24.0) * 0.72


def _pad(tf: str) -> timedelta:
    tf = tf.lower().strip()
    if tf.endswith("m") and tf[:-1].isdigit():
        m = int(tf[:-1])
        return timedelta(minutes=max(m * 40, 120))
    if tf.endswith("h") and tf[:-1].isdigit():
        h = int(tf[:-1])
        return timedelta(hours=max(h * 24, 24))
    return timedelta(days=20)


def plot_trade(
    bars: pd.DataFrame,
    trade: TradeRow,
    out_path: Path,
    *,
    label: str,
    instrument: str,
    tf: str,
) -> bool:
    pad = _pad(tf)
    start = trade.entry_ts - pad
    end = trade.exit_ts + pad
    plot = bars[(bars.index >= start) & (bars.index <= end)].copy()
    if plot.empty:
        return False

    x = mdates.date2num(plot.index.to_pydatetime())
    width = _bar_width_days(tf)
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

    ax.axhline(trade.exit, color="#ef6c00", linestyle=":", linewidth=1.2, alpha=0.75, label="Exit %.4f" % trade.exit)
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
        label="Entry %.4f" % trade.entry,
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
        label="Exit %.4f (%s)" % (trade.exit, trade.exit_reason),
    )

    entry_l = trade.entry_ts.strftime("%Y-%m-%d %H:%M")
    exit_l = trade.exit_ts.strftime("%Y-%m-%d %H:%M")
    ax.set_title(
        "%s — #%03d %s %s | %+0.2f pts ($%+.0f) | %s → %s | %s"
        % (
            label,
            trade.idx,
            trade.result.upper(),
            trade.side,
            trade.pnl_pts,
            trade.pnl_usd,
            entry_l,
            exit_l,
            trade.exit_reason,
        ),
        fontsize=10,
    )
    ax.set_ylabel(instrument)
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    if tf.endswith("h") or tf.endswith("m"):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=14))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=axis_tz))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=axis_tz))
    ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def write_index(
    out_root: Path,
    trades: List[TradeRow],
    *,
    label: str,
    seed: int,
    n_wins: int,
    n_losses: int,
    total_trades: int,
    note: str,
) -> None:
    lines = [
        "# %s — sample trade charts" % label,
        "",
        note,
        "",
        "Sample of **%d** trades (**%d** wins + **%d** losses), seed `%d`, from **%d** closed trades."
        % (len(trades), n_wins, n_losses, seed, total_trades),
        "",
        "OHLC candles with entry/exit markers. Wins are charts 001–%03d; losses %03d–%03d."
        % (n_wins, n_wins + 1, n_wins + n_losses),
        "",
        "| # | Result | Side | Entry | Exit | Pts | P/L USD | Reason | Chart |",
        "|---:|---|---|---|---|---:|---:|---|---|",
    ]
    for t in trades:
        entry_d = t.entry_ts.strftime("%Y-%m-%d %H:%M")
        exit_d = t.exit_ts.strftime("%Y-%m-%d %H:%M")
        stamp = t.entry_ts.strftime("%Y-%m-%d_%H%M")
        rel = "charts/%03d_%s_%s.png" % (t.idx, t.result, stamp)
        lines.append(
            "| {idx} | {result} | {side} | {entry} | {exit} | {pts:+.2f} | ${usd:+,.0f} | {reason} | [{rel}]({rel}) |".format(
                idx=t.idx,
                result=t.result,
                side=t.side,
                entry=entry_d,
                exit=exit_d,
                pts=t.pnl_pts,
                usd=t.pnl_usd,
                reason=t.exit_reason,
                rel=rel,
            )
        )
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_bars_csv(state_dir: Path, instrument: str, tf: str) -> Path:
    bars_dir = state_dir / "bars"
    candidates = [
        bars_dir / ("%s_%s.csv" % (instrument, tf)),
        bars_dir / ("%s_%s.csv" % (instrument.upper(), tf)),
        bars_dir / ("%s_%s.csv" % (instrument.lower(), tf)),
    ]
    for c in candidates:
        if c.exists():
            return c
    matches = sorted(bars_dir.glob("*.csv")) if bars_dir.exists() else []
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError("No bars CSV under %s (tried %s)" % (bars_dir, candidates[0].name))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", default="xauusd_1h", help="State folder slug under sweep/tf_study")
    ap.add_argument("--instrument", default="XAUUSD")
    ap.add_argument("--tf", default="1h")
    ap.add_argument(
        "--state-root",
        default="",
        help="Override state dir (default: live/state/trend_momentum_sweep/states/{slug})",
    )
    ap.add_argument(
        "--output-root",
        default="",
        help="Override output (default: live/state/trend_momentum_sweep/charts/{slug})",
    )
    ap.add_argument("--wins", type=int, default=50)
    ap.add_argument("--losses", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    state_root = (
        Path(args.state_root)
        if args.state_root
        else REPO / "live" / "state" / "trend_momentum_sweep" / "states" / args.slug
    )
    output_root = (
        Path(args.output_root)
        if args.output_root
        else REPO / "live" / "state" / "trend_momentum_sweep" / "charts" / args.slug
    )
    if not state_root.exists():
        raise SystemExit("Missing state root: %s" % state_root)

    if args.force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    bars = load_bars(find_bars_csv(state_root, args.instrument, args.tf))
    trades_df = load_trades(state_root / "fills.csv", args.instrument)
    picked = sample_trades(trades_df, wins=args.wins, losses=args.losses, seed=args.seed)

    label = "Trend–momentum %s %s" % (args.instrument, args.tf)
    charts_dir = output_root / "charts"
    written = 0
    for trade in picked:
        stamp = trade.entry_ts.strftime("%Y-%m-%d_%H%M")
        out_path = charts_dir / ("%03d_%s_%s.png" % (trade.idx, trade.result, stamp))
        ok = plot_trade(
            bars,
            trade,
            out_path,
            label=label,
            instrument=args.instrument,
            tf=args.tf,
        )
        if ok:
            written += 1
        else:
            print("SKIP empty window: #%03d %s" % (trade.idx, trade.trade_id))

    n_wins = sum(1 for t in picked if t.result == "win")
    n_losses = sum(1 for t in picked if t.result == "loss")
    note = (
        "Sweep #1 by N/S is **NAS100 1h** (N/S 0.62) but only 16 wins — "
        "this pack uses **XAUUSD 1h** (N/S 0.19, 883 trades), the best positive "
        "sweep sleeve with enough wins and losses for a 50/50 chart sample."
        if args.slug == "xauusd_1h"
        else "Charts from `%s` fills." % args.slug
    )
    write_index(
        output_root,
        picked,
        label=label,
        seed=args.seed,
        n_wins=n_wins,
        n_losses=n_losses,
        total_trades=len(trades_df),
        note=note,
    )
    print("Wrote %d charts → %s" % (written, charts_dir))
    print("Index → %s" % (output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
