"""Sample trade charts for US30 / NAS100 ST+PMC sl50_tp150_3r_1mfill.

Even win/loss sample from StrategyPlugin 1m-fill fills. Hourly candles,
ATR SuperTrend 14×3, prior-month close, stop/target, entry/exit markers.
"""

from __future__ import annotations

import argparse
import random
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import load_prev_month_close_map

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
ATR_LEN = 14
ATR_MULT = 3.0
FEE = 1.50
STOP_PTS = 50.0
TARGET_PTS = 150.0
EXIT_REASONS = {"stop", "target", "tp1", "eod", "flatten", "close", "runner_stop", "wide_stop"}

OUT_ROOT = REPO / "live" / "state" / "st_pmc_1mfill_cross_market" / "charts"

MARKETS: Dict[str, Dict[str, object]] = {
    "us30": {
        "instrument": "US30",
        "label": "US30 ST+PMC sl50_tp150_3r_1mfill",
        "fills": (
            REPO
            / "live"
            / "state"
            / "us30_st_pmc_retest_add_experiment"
            / "states"
            / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"
            / "fills.csv"
        ),
        "hourly_csv": REPO / "fx" / "us30_1h.csv",
        "daily_csv": REPO / "fx" / "us30_daily.csv",
        "point_value": float(POINT_VALUES.get("US30", 1.0)),
    },
    "nas100": {
        "instrument": "NAS100",
        "label": "NAS100 ST+PMC sl50_tp150_3r_1mfill",
        "fills": (
            REPO
            / "live"
            / "state"
            / "st_pmc_1mfill_cross_market"
            / "nas100"
            / "states"
            / "nas100_hourly_st_pmc_sl50_tp150_3r_1mfill"
            / "fills.csv"
        ),
        "hourly_csv": REPO / "fx" / "nas100_1h.csv",
        "daily_csv": REPO / "fx" / "nas100_daily.csv",
        "point_value": float(POINT_VALUES.get("NAS100", 1.0)),
    },
}


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


def load_hourly_with_st(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    ts_col = "ts_event" if "ts_event" in raw.columns else "ts"
    raw["ts"] = pd.to_datetime(raw[ts_col], utc=True).dt.tz_convert(NY)
    raw = raw.set_index("ts").sort_index()
    for c in ("open", "high", "low", "close"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw.dropna(subset=["open", "high", "low", "close"])
    return compute_supertrend(raw, atr_len=ATR_LEN, multiplier=ATR_MULT)


def load_trades(fills_path: Path, *, daily_path: Path, point_value: float) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    pmc_map = load_prev_month_close_map(daily_path)

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
            stop = entry_px - STOP_PTS
            target = entry_px + TARGET_PTS
        else:
            pnl_pts = (entry_px - exit_px) * qty
            stop = entry_px + STOP_PTS
            target = entry_px - TARGET_PTS
        pnl_usd = pnl_pts * point_value - FEE * qty
        exit_reason = str(exit_["reason"]).lower()
        if exit_reason == "target":
            result = "win"
        elif exit_reason == "stop":
            result = "loss"
        else:
            result = "win" if pnl_usd > 0 else "loss"
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
    instrument: str,
    pre_hours: int,
    post_hours: int,
) -> bool:
    start = trade.entry_ts - timedelta(hours=pre_hours)
    end = trade.exit_ts + timedelta(hours=post_hours)
    plot = hourly[(hourly.index >= start) & (hourly.index <= end)].copy()
    if plot.empty:
        return False

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
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, min(o, c)),
                width,
                max(abs(c - o), min_body),
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
        label="Prior month close %.1f" % trade.prev_month_close,
    )
    ax.axhline(trade.stop, color="#ef6c00", linestyle=":", linewidth=1.2, alpha=0.85, label="Stop %.1f" % trade.stop)
    ax.axhline(trade.target, color="#6a1b9a", linestyle=":", linewidth=1.2, alpha=0.85, label="Target %.1f" % trade.target)

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
        label="Entry %.1f" % trade.entry,
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
        label="Exit %.1f (%s)" % (trade.exit, trade.exit_reason),
    )

    ax.set_title(
        "%s — #%03d %s %s | %+0.1f pts ($%+.0f) | %s → %s | ATR(%d)×%g"
        % (
            label,
            trade.idx,
            trade.result.upper(),
            trade.side,
            trade.pnl_pts,
            trade.pnl_usd,
            trade.entry_ts.strftime("%Y-%m-%d %H:%M"),
            trade.exit_ts.strftime("%Y-%m-%d %H:%M"),
            ATR_LEN,
            ATR_MULT,
        ),
        fontsize=10,
    )
    ax.set_ylabel(instrument)
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=axis_tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d %H:%M", tz=axis_tz))
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
    total_trades: int,
) -> None:
    n_wins = sum(1 for t in trades if t.result == "win")
    n_losses = sum(1 for t in trades if t.result == "loss")
    lines = [
        "# %s — sample trade charts" % label,
        "",
        "Even sample of **%d** trades (%d wins + %d losses), seed `%d`, from **%d** campaign trades."
        % (len(trades), n_wins, n_losses, seed, total_trades),
        "",
        "Hourly candles (all sessions), ATR SuperTrend 14×3, prior-month close, stop/target 50/150, entry/exit.",
        "Source fills: StrategyPlugin + 1m fill tape (`sl50_tp150_3r_1mfill`).",
        "",
        "| # | Result | Side | Entry | Exit | Pts | P/L USD | Chart |",
        "|---:|---|---|---|---|---:|---:|---|",
    ]
    for t in sorted(trades, key=lambda item: item.idx):
        stamp = t.entry_ts.strftime("%Y-%m-%d_%H%M")
        rel = "charts/%03d_%s_%s.png" % (t.idx, t.result, stamp)
        lines.append(
            "| %d | %s | %s | %s | %s | %+.1f | $%+.0f | [%s](%s) |"
            % (
                t.idx,
                t.result,
                t.side,
                t.entry_ts.strftime("%Y-%m-%d %H:%M"),
                t.exit_ts.strftime("%Y-%m-%d %H:%M"),
                t.pnl_pts,
                t.pnl_usd,
                rel,
                rel,
            )
        )
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_market(
    key: str,
    *,
    wins: int,
    losses: int,
    seed: int,
    pre_hours: int,
    post_hours: int,
    force: bool,
) -> Tuple[str, int, Path]:
    cfg = MARKETS[key]
    instrument = str(cfg["instrument"])
    label = str(cfg["label"])
    fills = Path(str(cfg["fills"]))
    hourly_csv = Path(str(cfg["hourly_csv"]))
    daily_csv = Path(str(cfg["daily_csv"]))
    pv = float(cfg["point_value"])
    out = OUT_ROOT / key

    if not fills.exists():
        raise SystemExit("Missing fills: %s" % fills)
    if not hourly_csv.exists():
        raise SystemExit("Missing hourly: %s" % hourly_csv)
    if not daily_csv.exists():
        raise SystemExit("Missing daily: %s" % daily_csv)

    if force and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    print("Loading %s trades…" % instrument, flush=True)
    df = load_trades(fills, daily_path=daily_csv, point_value=pv)
    print("  %d trades (%dW / %dL)" % (len(df), (df["result"] == "win").sum(), (df["result"] == "loss").sum()), flush=True)
    picked = sample_trades(df, wins=wins, losses=losses, seed=seed)

    print("Loading %s hourly + SuperTrend…" % instrument, flush=True)
    hourly = load_hourly_with_st(hourly_csv)
    print("  %s hourly bars" % f"{len(hourly):,}", flush=True)

    charts_dir = out / "charts"
    written = 0
    for trade in picked:
        stamp = trade.entry_ts.strftime("%Y-%m-%d_%H%M")
        path = charts_dir / ("%03d_%s_%s.png" % (trade.idx, trade.result, stamp))
        ok = plot_trade(
            hourly,
            trade,
            path,
            label=label,
            instrument=instrument,
            pre_hours=pre_hours,
            post_hours=post_hours,
        )
        if ok:
            written += 1
        if trade.idx % 25 == 0 or trade.idx == len(picked):
            print("  %s %d/%d" % (instrument, trade.idx, len(picked)), flush=True)

    write_index(out, picked, label=label, seed=seed, total_trades=len(df))
    return instrument, written, out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--markets", nargs="*", default=["us30", "nas100"], choices=sorted(MARKETS))
    ap.add_argument("--wins", type=int, default=100)
    ap.add_argument("--losses", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260730)
    ap.add_argument("--pre-hours", type=int, default=48)
    ap.add_argument("--post-hours", type=int, default=12)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    results = []
    for key in args.markets:
        print("=" * 60, flush=True)
        inst, n, out = build_market(
            key,
            wins=args.wins,
            losses=args.losses,
            seed=args.seed,
            pre_hours=args.pre_hours,
            post_hours=args.post_hours,
            force=args.force,
        )
        results.append((inst, n, out))
        print("Wrote %d charts → %s" % (n, out), flush=True)

    master = [
        "# ST+PMC sl50_tp150_3r_1mfill — sample trade charts",
        "",
        "Even win/loss samples from StrategyPlugin + 1m fill-tape books.",
        "",
    ]
    for inst, n, out in results:
        rel = out.relative_to(OUT_ROOT)
        master.append("- **%s** — %d charts → [`%s/INDEX.md`](%s/INDEX.md)" % (inst, n, rel, rel))
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "INDEX.md").write_text("\n".join(master) + "\n", encoding="utf-8")
    print("Master index → %s" % (OUT_ROOT / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
