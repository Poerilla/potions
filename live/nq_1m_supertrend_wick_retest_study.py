from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_nq_1m_10am_open_sample_charts import plot_candles, ten_am_open
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
POINT_VALUE = 20.0
FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class Setup:
    session: date
    side: str
    signal_idx: int
    signal_ts: pd.Timestamp
    signal_price: float
    st_level: float


@dataclass(frozen=True)
class Trade:
    session: date
    side: str
    signal_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry: float
    exit_ts: pd.Timestamp
    exit: float
    exit_reason: str
    net_usd: float
    signal_st: float
    confirmed_swing: bool


def is_wick_touch(row: pd.Series) -> Optional[str]:
    st = float(row.get("supertrend", np.nan))
    trend = int(row.get("supertrend_trend", 0) or 0)
    if not np.isfinite(st) or trend == 0:
        return None
    if trend == 1 and float(row["low"]) <= st and float(row["close"]) > st:
        return "long"
    if trend == -1 and float(row["high"]) >= st and float(row["close"]) < st:
        return "short"
    return None


def confirms_swing(df: pd.DataFrame, signal_idx: int, side: str) -> Optional[bool]:
    # One candle of left context and two candles of right context.
    if signal_idx <= 0 or signal_idx + 2 >= len(df):
        return None
    row = df.iloc[signal_idx]
    prev = df.iloc[signal_idx - 1]
    nxt1 = df.iloc[signal_idx + 1]
    nxt2 = df.iloc[signal_idx + 2]
    if side == "long":
        low = float(row["low"])
        return low <= float(prev["low"]) and low <= float(nxt1["low"]) and low <= float(nxt2["low"])
    high = float(row["high"])
    return high >= float(prev["high"]) and high >= float(nxt1["high"]) and high >= float(nxt2["high"])


def trend_broken(row: pd.Series, side: str) -> bool:
    st = float(row.get("supertrend", np.nan))
    if not np.isfinite(st):
        return False
    if side == "long":
        return float(row["close"]) < st
    return float(row["close"]) > st


def resample_signal_bars(rth: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return rth.copy()
    return (
        rth.resample("%dmin" % minutes, label="right", closed="right")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
        .dropna(subset=["open", "high", "low", "close"])
    )


def target_hit(row: pd.Series, side: str, target: float) -> bool:
    if side == "long":
        return float(row["high"]) >= target
    return float(row["low"]) <= target


def simulate_day(session: date, rth: pd.DataFrame, max_trades: int, st_minutes: int, target_pts: Optional[float]) -> list[Trade]:
    signal_bars = resample_signal_bars(rth, st_minutes)
    df = compute_supertrend(signal_bars.copy(), atr_len=14, multiplier=2.0).reset_index(names="ts")
    start = pd.Timestamp.combine(session, time(9, 30)).tz_localize(NY)
    end_entry = pd.Timestamp.combine(session, time(15, 45)).tz_localize(NY)
    end_flat = pd.Timestamp.combine(session, time(15, 59)).tz_localize(NY)
    trades: list[Trade] = []
    i = 0
    while i < len(df) - 1 and len(trades) < max_trades:
        ts = pd.Timestamp(df.iloc[i]["ts"])
        if ts < start or ts > end_entry:
            i += 1
            continue
        side = is_wick_touch(df.iloc[i])
        if side is None:
            i += 1
            continue
        entry_idx = i + 1
        entry_ts = pd.Timestamp(df.iloc[entry_idx]["ts"])
        if entry_ts > end_entry:
            break
        entry = float(df.iloc[entry_idx]["open"])
        target = entry + target_pts if side == "long" and target_pts is not None else (
            entry - target_pts if side == "short" and target_pts is not None else None
        )
        signal_st = float(df.iloc[i]["supertrend"])
        confirm_idx = min(i + 2, len(df) - 1)
        confirmed = confirms_swing(df, i, side)
        exit_idx = None
        exit_reason = ""
        exit_px_override = None
        for j in range(entry_idx, len(df)):
            row_ts = pd.Timestamp(df.iloc[j]["ts"])
            if row_ts > end_flat:
                break
            if trend_broken(df.iloc[j], side):
                exit_idx = j
                exit_reason = "trend_break_close"
                break
            if target is not None and target_hit(df.iloc[j], side, target):
                exit_idx = j
                exit_reason = "target_%g" % target_pts
                exit_px_override = target
                break
            if j >= confirm_idx and confirmed is False:
                exit_idx = j
                exit_reason = "not_swing_confirmed"
                break
        if exit_idx is None:
            eligible = df[pd.to_datetime(df["ts"]) <= end_flat]
            exit_idx = int(eligible.index[-1]) if not eligible.empty else len(df) - 1
            exit_reason = "eod_flat"
        exit_ts = pd.Timestamp(df.iloc[exit_idx]["ts"])
        exit_px = float(exit_px_override) if exit_px_override is not None else float(df.iloc[exit_idx]["close"])
        pts = exit_px - entry if side == "long" else entry - exit_px
        trades.append(
            Trade(
                session=session,
                side=side,
                signal_ts=ts,
                entry_ts=entry_ts,
                entry=entry,
                exit_ts=exit_ts,
                exit=exit_px,
                exit_reason=exit_reason,
                net_usd=pts * POINT_VALUE - FEE_PER_UNIT,
                signal_st=signal_st,
                confirmed_swing=bool(confirmed),
            )
        )
        i = max(exit_idx + 1, i + 1)
    return trades


def summarize(trades: Sequence[Trade]) -> dict[str, float]:
    if not trades:
        return {}
    net = sum(t.net_usd for t in trades)
    wins = [t for t in trades if t.net_usd > 0]
    losses = [t for t in trades if t.net_usd <= 0]
    gross_win = sum(t.net_usd for t in wins)
    gross_loss = abs(sum(t.net_usd for t in losses))
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for t in sorted(trades, key=lambda item: (item.exit_ts, item.session.isoformat())):
        equity += t.net_usd
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return {
        "trades": len(trades),
        "net_usd": net,
        "closed_dd_usd": dd,
        "win_rate_pct": 100.0 * len(wins) / len(trades),
        "profit_factor": gross_win / gross_loss if gross_loss else math.inf,
        "avg_trade": net / len(trades),
        "trend_breaks": sum(1 for t in trades if t.exit_reason == "trend_break_close"),
        "not_swing": sum(1 for t in trades if t.exit_reason == "not_swing_confirmed"),
        "eod": sum(1 for t in trades if t.exit_reason == "eod_flat"),
    }


def plot_day(output_root: Path, idx: int, session: date, rth: pd.DataFrame, trades: Sequence[Trade], st_minutes: int, target_pts: Optional[float]) -> str:
    df = compute_supertrend(rth.copy(), atr_len=14, multiplier=2.0)
    signal_df = compute_supertrend(resample_signal_bars(rth, st_minutes), atr_len=14, multiplier=2.0)
    marker = ten_am_open(rth)
    fig, (ax, vol_ax) = plt.subplots(2, 1, figsize=(18, 8.5), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04})
    plot_candles(ax, df, width_days=(1 / (24 * 60)) * 0.72)
    bull = signal_df["supertrend"].where(signal_df["supertrend_trend"] == 1)
    bear = signal_df["supertrend"].where(signal_df["supertrend_trend"] == -1)
    ax.step(signal_df.index, bull, where="post", color="#009c5b", linewidth=1.35, label="%dm ST ATR14 x 2 bull" % st_minutes)
    ax.step(signal_df.index, bear, where="post", color="#d62728", linewidth=1.35, label="%dm ST ATR14 x 2 bear" % st_minutes)
    if marker is not None:
        marker_ts, marker_open = marker
        ax.axhline(marker_open, color="#0057b8", linewidth=1.0, alpha=0.65, label="10:00 open")
        ax.axvline(marker_ts, color="#0057b8", linewidth=0.9, linestyle="--", alpha=0.55)
    ax.axvline(pd.Timestamp.combine(session, time(15, 45)).tz_localize(NY), color="#333333", linewidth=0.9, linestyle="--", alpha=0.55)
    colors = {"long": "#006dce", "short": "#7b3fb2"}
    for n, t in enumerate(trades, start=1):
        color = colors[t.side]
        ax.scatter([t.signal_ts], [t.signal_st], color=color, marker="D", s=70, zorder=10)
        ax.scatter([t.entry_ts], [t.entry], color=color, marker="^" if t.side == "long" else "v", s=115, zorder=11)
        ax.scatter([t.exit_ts], [t.exit], color=color, marker="x", s=90, zorder=11)
        ax.plot([t.entry_ts, t.exit_ts], [t.entry, t.exit], color=color, linewidth=1.2, alpha=0.8)
        if target_pts is not None:
            target = t.entry + target_pts if t.side == "long" else t.entry - target_pts
            ax.axhline(target, color=color, linestyle=":", linewidth=0.8, alpha=0.45)
        ax.annotate(
            "%d %s $%.0f\n%s" % (n, t.side.upper(), t.net_usd, "swing" if t.confirmed_swing else "not swing"),
            xy=(t.entry_ts, t.entry),
            xytext=(8, 22 if t.side == "long" else -28),
            textcoords="offset points",
            color=color,
            fontsize=8,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": color, "lw": 0.8},
        )
    ax.set_title("NQ %dm Supertrend wick-retest next-open prototype - %s - %d trade(s)" % (st_minutes, session.isoformat(), len(trades)))
    ax.set_ylabel("NQ")
    ax.grid(True, color="#e2e2e2", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8)
    bar_colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    vol_ax.bar(df.index, df["volume"], width=(1 / (24 * 60)) * 0.72, color=bar_colors, alpha=0.45)
    vol_ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[30, 0], tz=df.index.tz))
    vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=df.index.tz))
    vol_ax.set_xlabel("Time (America/New_York)")
    vol_ax.set_ylabel("Vol")
    for label in vol_ax.get_xticklabels():
        label.set_rotation(90)
        label.set_fontsize(7)
    out = output_root / "charts" / ("%03d_%s.png" % (idx, session.isoformat()))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=135, bbox_inches="tight")
    plt.close(fig)
    return str(out.relative_to(output_root))


def run(output_root: Path, sample_manifest: Path, force: bool, max_trades: int, st_minutes: int, target_pts: Optional[float]) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    sessions = [pd.Timestamp(s).date() for s in pd.read_csv(sample_manifest)["session"].astype(str)]
    cfg = MARKETS["nq"]
    print("Loading NQ 1m bars...", flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    all_trades: list[Trade] = []
    trade_rows: list[dict[str, object]] = []
    chart_rows: list[dict[str, object]] = []
    for idx, session in enumerate(sessions, start=1):
        rth = _rth_bars(by_day.get(session), session)
        if rth.empty:
            continue
        trades = simulate_day(session, rth, max_trades=max_trades, st_minutes=st_minutes, target_pts=target_pts)
        all_trades.extend(trades)
        chart = plot_day(output_root, idx, session, rth, trades, st_minutes=st_minutes, target_pts=target_pts)
        chart_rows.append({"idx": idx, "session": session.isoformat(), "trades": len(trades), "net_usd": sum(t.net_usd for t in trades), "chart": chart})
        for trade_num, t in enumerate(trades, start=1):
            trade_rows.append(
                {
                    "session": t.session.isoformat(),
                    "trade_num": trade_num,
                    "side": t.side,
                    "signal_ts": t.signal_ts.isoformat(),
                    "entry_ts": t.entry_ts.isoformat(),
                    "entry": "%.2f" % t.entry,
                    "exit_ts": t.exit_ts.isoformat(),
                    "exit": "%.2f" % t.exit,
                    "exit_reason": t.exit_reason,
                    "net_usd": "%.2f" % t.net_usd,
                    "signal_st": "%.2f" % t.signal_st,
                    "confirmed_swing": t.confirmed_swing,
                }
            )
        if idx % 25 == 0:
            print("  processed %d/%d" % (idx, len(sessions)), flush=True)
    pd.DataFrame(trade_rows).to_csv(output_root / "trades.csv", index=False)
    pd.DataFrame(chart_rows).to_csv(output_root / "chart_manifest.csv", index=False)
    stats = summarize(all_trades)
    lines = [
        "# NQ 1m Supertrend Wick-Retest Next-Open Prototype",
        "",
        "Sample: the same 100 sessions from `nq/case_studies/nq_1m_10am_open_random_100/chart_manifest.csv`.",
        "",
        "Rule assumptions encoded:",
        "",
        "- %d-minute Supertrend `ATR(14) x 2.0` is the signal/trailing stop; charts still show 1-minute candles." % st_minutes,
        "- Trade window starts once Supertrend exists and ends for new entries at 15:45 ET.",
        "- Long setup: bullish Supertrend, candle wicks/touches the ST line with `low <= ST`, but closes back above ST.",
        "- Short setup: bearish Supertrend, candle wicks/touches the ST line with `high >= ST`, but closes back below ST.",
        "- Entry is the **next candle open**, not the touch candle.",
        "- Stay in the trade only if the touch candle confirms as a 1-left / 2-right swing low for longs or swing high for shorts; otherwise flatten after that confirmation window.",
        "- Exit on %s, a close through the current Supertrend line, or EOD if still open." % (
            "a %.1f-point target" % target_pts if target_pts is not None else "no fixed target"
        ),
        "- Max %d trades per day. The 10:00 open line remains on charts for study only." % max_trades,
        "",
        "## Summary",
        "",
        "| Trades | Net | Closed DD | Win % | PF | Avg Trade | Trend Breaks | Not Swing | EOD |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if stats:
        lines.append(
            "| {trades:.0f} | ${net_usd:,.2f} | ${closed_dd_usd:,.2f} | {win_rate_pct:.2f} | {profit_factor:.3f} | ${avg_trade:,.2f} | {trend_breaks:.0f} | {not_swing:.0f} | {eod:.0f} |".format(
                **stats
            )
        )
    else:
        lines.append("| 0 | $0.00 | $0.00 | 0.00 | 0.000 | $0.00 | 0 | 0 | 0 |")
    lines += [
        "",
        "## Charts",
        "",
        "| # | Session | Trades | Net | Chart |",
        "|---:|---|---:|---:|---|",
    ]
    for row in chart_rows:
        lines.append("| {idx} | {session} | {trades} | ${net_usd:,.2f} | [{chart}]({chart}) |".format(**row))
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype NQ all-day 1m Supertrend wick-retest next-open entry.")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--sample-manifest", type=Path, default=REPO / "nq/case_studies/nq_1m_10am_open_random_100/chart_manifest.csv")
    parser.add_argument("--max-trades", type=int, default=4)
    parser.add_argument("--st-minutes", type=int, default=1)
    parser.add_argument("--target-pts", type=float, default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    suffix = "_target%g" % args.target_pts if args.target_pts is not None else ""
    output_root = args.output_root or REPO / ("nq/case_studies/nq_%dm_st_wick_retest_next_open%s_sample_100" % (args.st_minutes, suffix))
    run(
        output_root,
        args.sample_manifest,
        force=not args.no_force,
        max_trades=args.max_trades,
        st_minutes=args.st_minutes,
        target_pts=args.target_pts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
