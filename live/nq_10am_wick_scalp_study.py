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
TICK_SIZE = 0.25


@dataclass(frozen=True)
class Signal:
    session: date
    side: str
    ts: pd.Timestamp
    open_line: float
    signal_close: float
    wick_frac: float
    st_trend: int


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
    wick_frac: float
    st_trend: int


def stop_fill(side: str, stop: float, row: pd.Series, slippage_ticks: float) -> Optional[float]:
    if side == "long" and float(row["low"]) <= stop:
        return min(float(row["open"]), stop - slippage_ticks * TICK_SIZE)
    if side == "short" and float(row["high"]) >= stop:
        return max(float(row["open"]), stop + slippage_ticks * TICK_SIZE)
    return None


def wick_fraction(row: pd.Series, side: str) -> float:
    high = float(row["high"])
    low = float(row["low"])
    open_ = float(row["open"])
    close = float(row["close"])
    rng = max(high - low, TICK_SIZE)
    if side == "long":
        # Opposite wick for an upside expansion is the lower portion.
        return max(0.0, min(open_, close) - low) / rng
    # Opposite wick for a downside expansion is the upper portion.
    return max(0.0, high - max(open_, close)) / rng


def signal_from_bar(session: date, ts: pd.Timestamp, row: pd.Series, open_line: float, require_st: bool) -> Optional[Signal]:
    st_trend = int(row.get("supertrend_trend", 0) or 0)
    # Long: price flushed below the 10:00 open, then closed back above it.
    if float(row["low"]) < open_line and float(row["close"]) > open_line:
        wf = wick_fraction(row, "long")
        if wf >= 0.70 and (not require_st or st_trend == 1):
            return Signal(session, "long", ts, open_line, float(row["close"]), wf, st_trend)
    # Short mirror: price pushed above the 10:00 open, then closed back below it.
    if float(row["high"]) > open_line and float(row["close"]) < open_line:
        wf = wick_fraction(row, "short")
        if wf >= 0.70 and (not require_st or st_trend == -1):
            return Signal(session, "short", ts, open_line, float(row["close"]), wf, st_trend)
    return None


def enter_limit(signal: Signal, bars: pd.DataFrame, stop_pts: float, slippage_ticks: float) -> Optional[Trade]:
    entry_price = signal.signal_close
    side = signal.side
    after_signal = bars[bars.index > signal.ts]
    deadline = pd.Timestamp.combine(signal.session, time(11, 0)).tz_localize(NY)
    after_signal = after_signal[after_signal.index <= deadline]
    entry_ts: Optional[pd.Timestamp] = None
    for ts, row in after_signal.iterrows():
        if side == "long" and float(row["low"]) <= entry_price:
            entry_ts = pd.Timestamp(ts)
            break
        if side == "short" and float(row["high"]) >= entry_price:
            entry_ts = pd.Timestamp(ts)
            break
    if entry_ts is None:
        return None

    stop = entry_price - stop_pts if side == "long" else entry_price + stop_pts
    exit_ts = deadline
    exit_px = float(bars[bars.index <= deadline].iloc[-1]["close"])
    exit_reason = "time_1100"
    holding = bars[(bars.index >= entry_ts) & (bars.index <= deadline)]
    for ts, row in holding.iterrows():
        fill = stop_fill(side, stop, row, slippage_ticks)
        if fill is not None:
            exit_ts = pd.Timestamp(ts)
            exit_px = fill
            exit_reason = "stop"
            break
    pts = exit_px - entry_price if side == "long" else entry_price - exit_px
    net = pts * POINT_VALUE - FEE_PER_UNIT
    return Trade(
        session=signal.session,
        side=side,
        signal_ts=signal.ts,
        entry_ts=entry_ts,
        entry=entry_price,
        exit_ts=exit_ts,
        exit=exit_px,
        exit_reason=exit_reason,
        net_usd=net,
        wick_frac=signal.wick_frac,
        st_trend=signal.st_trend,
    )


def simulate_day(
    session: date,
    rth: pd.DataFrame,
    *,
    stop_pts: float,
    require_st: bool,
    slippage_ticks: float,
) -> list[Trade]:
    marker = ten_am_open(rth)
    if marker is None:
        return []
    _marker_ts, open_line = marker
    bars = compute_supertrend(rth.copy(), atr_len=14, multiplier=2.0)
    start = pd.Timestamp.combine(session, time(10, 1)).tz_localize(NY)
    deadline = pd.Timestamp.combine(session, time(11, 0)).tz_localize(NY)
    scan = bars[(bars.index >= start) & (bars.index < deadline)]
    trades: list[Trade] = []
    blocked_until: Optional[pd.Timestamp] = None
    for ts, row in scan.iterrows():
        if blocked_until is not None and ts <= blocked_until:
            continue
        signal = signal_from_bar(session, pd.Timestamp(ts), row, open_line, require_st=require_st)
        if signal is None:
            continue
        trade = enter_limit(signal, bars, stop_pts=stop_pts, slippage_ticks=slippage_ticks)
        if trade is None:
            continue
        trades.append(trade)
        blocked_until = trade.exit_ts
        if len(trades) >= 2:
            break
        # Reversal is implicit: after a stopped long, continue scanning later bars
        # for the opposite wick/reclaim pattern. No same-direction retry.
        if trade.exit_reason != "stop":
            break
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
        "stops": sum(1 for t in trades if t.exit_reason == "stop"),
        "time_exits": sum(1 for t in trades if t.exit_reason == "time_1100"),
    }


def plot_day(output_root: Path, idx: int, session: date, rth: pd.DataFrame, trades: Sequence[Trade]) -> str:
    marker = ten_am_open(rth)
    if marker is None:
        return ""
    marker_ts, marker_open = marker
    df = compute_supertrend(rth.copy(), atr_len=14, multiplier=2.0)
    fig, (ax, vol_ax) = plt.subplots(2, 1, figsize=(18, 8.5), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04})
    plot_candles(ax, df, width_days=(1 / (24 * 60)) * 0.72)
    bull = df["supertrend"].where(df["supertrend_trend"] == 1)
    bear = df["supertrend"].where(df["supertrend_trend"] == -1)
    ax.plot(df.index, bull, color="#009c5b", linewidth=1.15, label="1m ST ATR14 x 2 bull")
    ax.plot(df.index, bear, color="#d62728", linewidth=1.15, label="1m ST ATR14 x 2 bear")
    ax.axhline(marker_open, color="#0057b8", linewidth=1.35, alpha=0.9, label="10:00 open")
    ax.axvline(marker_ts, color="#0057b8", linewidth=1.0, linestyle="--", alpha=0.7)
    ax.axvline(pd.Timestamp.combine(session, time(11, 0)).tz_localize(NY), color="#333333", linewidth=1.0, linestyle="--", alpha=0.65)
    colors = {"long": "#006dce", "short": "#7b3fb2"}
    for t in trades:
        color = colors[t.side]
        ax.scatter([t.signal_ts], [t.entry], color=color, marker="D", s=70, zorder=10)
        ax.scatter([t.entry_ts], [t.entry], color=color, marker="^" if t.side == "long" else "v", s=110, zorder=11)
        ax.scatter([t.exit_ts], [t.exit], color=color, marker="x", s=90, zorder=11)
        ax.plot([t.entry_ts, t.exit_ts], [t.entry, t.exit], color=color, linewidth=1.2, alpha=0.8)
        stop = t.entry - 10.0 if t.side == "long" else t.entry + 10.0
        ax.axhline(stop, color=color, linestyle=":", linewidth=0.85, alpha=0.5)
        ax.annotate(
            "%s $%.0f" % (t.side.upper(), t.net_usd),
            xy=(t.entry_ts, t.entry),
            xytext=(8, 18 if t.side == "long" else -24),
            textcoords="offset points",
            color=color,
            fontsize=8,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": color, "lw": 0.8},
        )
    ax.set_title("NQ 10:00 wick expansion scalp prototype - %s - %d trade(s)" % (session.isoformat(), len(trades)))
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


def run(output_root: Path, sample_manifest: Path, require_st: bool, force: bool) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    sample = pd.read_csv(sample_manifest)
    sessions = [pd.Timestamp(s).date() for s in sample["session"].astype(str)]
    cfg = MARKETS["nq"]
    print("Loading NQ 1m bars...", flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    trade_rows: list[dict[str, object]] = []
    chart_rows: list[dict[str, object]] = []
    all_trades: list[Trade] = []
    for idx, session in enumerate(sessions, start=1):
        rth = _rth_bars(by_day.get(session), session)
        if rth.empty:
            continue
        trades = simulate_day(session, rth, stop_pts=10.0, require_st=require_st, slippage_ticks=1.0)
        all_trades.extend(trades)
        chart = plot_day(output_root, idx, session, rth, trades)
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
                    "wick_frac": "%.4f" % t.wick_frac,
                    "st_trend": t.st_trend,
                }
            )
        if idx % 25 == 0:
            print("  processed %d/%d" % (idx, len(sessions)), flush=True)
    pd.DataFrame(trade_rows).to_csv(output_root / "trades.csv", index=False)
    pd.DataFrame(chart_rows).to_csv(output_root / "chart_manifest.csv", index=False)
    stats = summarize(all_trades)
    lines = [
        "# NQ 10:00 Wick Expansion Scalp Prototype",
        "",
        "Sample: the same 100 sessions from `nq/case_studies/nq_1m_10am_open_random_100/chart_manifest.csv`.",
        "",
        "Rule assumptions encoded:",
        "",
        "- Reference line is the 10:00 ET candle open.",
        "- Scan 1-minute bars from 10:01 through 10:59 ET.",
        "- Long signal: bar trades below the 10:00 open, has a lower wick >= 70% of its range, and closes back above the 10:00 open.",
        "- Short signal: bar trades above the 10:00 open, has an upper wick >= 70% of its range, and closes back below the 10:00 open.",
        "- Optional filter currently %s: signal bar Supertrend `ATR(14) x 2.0` must agree with the signal direction." % ("ON" if require_st else "OFF"),
        "- Entry is a limit at the signal-bar close, active until 11:00.",
        "- Stop is 10 NQ points with 1-tick adverse stop slippage. Exit all open exposure at 11:00.",
        "- Max 2 trades per day; after a non-stopped time exit, no retry.",
        "",
        "## Summary",
        "",
        "| Trades | Net | Closed DD | Win % | PF | Avg Trade | Stops | 11:00 exits |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if stats:
        lines.append(
            "| {trades:.0f} | ${net_usd:,.2f} | ${closed_dd_usd:,.2f} | {win_rate_pct:.2f} | {profit_factor:.3f} | ${avg_trade:,.2f} | {stops:.0f} | {time_exits:.0f} |".format(
                **stats
            )
        )
    else:
        lines.append("| 0 | $0.00 | $0.00 | 0.00 | 0.000 | $0.00 | 0 | 0 |")
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
    parser = argparse.ArgumentParser(description="Prototype NQ 10:00 wick expansion scalp on the 100-day chart sample.")
    parser.add_argument("--output-root", type=Path, default=REPO / "nq/case_studies/nq_10am_wick_expansion_scalp_sample_100")
    parser.add_argument("--sample-manifest", type=Path, default=REPO / "nq/case_studies/nq_1m_10am_open_random_100/chart_manifest.csv")
    parser.add_argument("--require-st", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    run(args.output_root, args.sample_manifest, require_st=args.require_st, force=not args.no_force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
