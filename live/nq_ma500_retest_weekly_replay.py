from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nq_15m_ma200_supertrend_100_week_charts import load_15m, plot_candles, recent_week_starts, shade_rth


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"

POINT_VALUE = 20.0
TICK_SIZE = 0.25
FEE_PER_UNIT = 1.50


@dataclass
class Position:
    side: str
    entry_ts: pd.Timestamp
    entry_price: float
    stop_price: float
    target_price: float
    protected: bool = False
    mae_pts: float = 0.0
    mfe_pts: float = 0.0


def adverse_stop_fill(side: str, stop_price: float, bar_open: float) -> float:
    if side == "long":
        base = min(stop_price, bar_open)
        return base - TICK_SIZE
    base = max(stop_price, bar_open)
    return base + TICK_SIZE


def adverse_market_fill(side: str, close_price: float) -> float:
    if side == "long":
        return close_price - TICK_SIZE
    return close_price + TICK_SIZE


def pnl_points(side: str, entry: float, exit_price: float) -> float:
    if side == "long":
        return exit_price - entry
    return entry - exit_price


def close_position(
    pos: Position,
    exit_ts: pd.Timestamp,
    exit_price: float,
    reason: str,
    rows: list[dict[str, object]],
) -> None:
    pts = pnl_points(pos.side, pos.entry_price, exit_price)
    rows.append(
        {
            "entry_ts": pos.entry_ts,
            "exit_ts": exit_ts,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "reason": reason,
            "points": pts,
            "gross": pts * POINT_VALUE,
            "fee": FEE_PER_UNIT,
            "net": pts * POINT_VALUE - FEE_PER_UNIT,
            "mae_pts": pos.mae_pts,
            "mfe_pts": pos.mfe_pts,
            "protected": pos.protected,
        }
    )


def simulate_week(
    week: pd.DataFrame,
    *,
    ma_col: str,
    risk_pts: float,
    target_pts: float,
    protect_trigger_pts: float,
    protect_profit_pts: float,
    max_units: int,
    rearm_when_protected: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    positions: list[Position] = []
    orientation: Optional[str] = None
    next_limit_side: Optional[str] = None
    next_limit_price: Optional[float] = None

    valid = week[week[ma_col].notna()].copy()
    if valid.empty:
        return pd.DataFrame(), pd.DataFrame()

    for i, (ts, row) in enumerate(valid.iterrows()):
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        ma = float(row[ma_col])

        # Fill any limit armed from the previous completed 15m candle.
        if next_limit_side and next_limit_price is not None:
            can_add = len(positions) < max_units
            if positions and rearm_when_protected:
                can_add = can_add and all(p.protected and p.side == next_limit_side for p in positions)
            elif positions:
                can_add = False

            filled = False
            if can_add and next_limit_side == "long" and l <= next_limit_price:
                entry = next_limit_price
                positions.append(
                    Position(
                        side="long",
                        entry_ts=ts,
                        entry_price=entry,
                        stop_price=entry - risk_pts,
                        target_price=entry + target_pts,
                    )
                )
                filled = True
            elif can_add and next_limit_side == "short" and h >= next_limit_price:
                entry = next_limit_price
                positions.append(
                    Position(
                        side="short",
                        entry_ts=ts,
                        entry_price=entry,
                        stop_price=entry + risk_pts,
                        target_price=entry - target_pts,
                    )
                )
                filled = True
            if filled:
                events.append({"ts": ts, "event": "entry", "side": next_limit_side, "price": next_limit_price})

        # Manage open positions conservatively: stop first, then target.
        survivors: list[Position] = []
        for pos in positions:
            if pos.side == "long":
                pos.mae_pts = min(pos.mae_pts, l - pos.entry_price)
                pos.mfe_pts = max(pos.mfe_pts, h - pos.entry_price)
                if not pos.protected and h >= pos.entry_price + protect_trigger_pts:
                    pos.stop_price = pos.entry_price + protect_profit_pts
                    pos.protected = True
                    events.append({"ts": ts, "event": "protect", "side": pos.side, "price": pos.stop_price})
                if l <= pos.stop_price:
                    fill = adverse_stop_fill(pos.side, pos.stop_price, o)
                    close_position(pos, ts, fill, "stop", trades)
                    events.append({"ts": ts, "event": "exit_stop", "side": pos.side, "price": fill})
                    continue
                if h >= pos.target_price:
                    close_position(pos, ts, pos.target_price, "target", trades)
                    events.append({"ts": ts, "event": "exit_target", "side": pos.side, "price": pos.target_price})
                    continue
            else:
                pos.mae_pts = min(pos.mae_pts, pos.entry_price - h)
                pos.mfe_pts = max(pos.mfe_pts, pos.entry_price - l)
                if not pos.protected and l <= pos.entry_price - protect_trigger_pts:
                    pos.stop_price = pos.entry_price - protect_profit_pts
                    pos.protected = True
                    events.append({"ts": ts, "event": "protect", "side": pos.side, "price": pos.stop_price})
                if h >= pos.stop_price:
                    fill = adverse_stop_fill(pos.side, pos.stop_price, o)
                    close_position(pos, ts, fill, "stop", trades)
                    events.append({"ts": ts, "event": "exit_stop", "side": pos.side, "price": fill})
                    continue
                if l <= pos.target_price:
                    close_position(pos, ts, pos.target_price, "target", trades)
                    events.append({"ts": ts, "event": "exit_target", "side": pos.side, "price": pos.target_price})
                    continue
            survivors.append(pos)
        positions = survivors

        desired = "long" if c > ma else "short" if c < ma else orientation
        if desired and orientation and desired != orientation and positions:
            for pos in positions:
                fill = adverse_market_fill(pos.side, c)
                close_position(pos, ts, fill, "ma_close_flip", trades)
                events.append({"ts": ts, "event": "exit_flip", "side": pos.side, "price": fill})
            positions = []
        orientation = desired

        # Arm/update the next-bar retest limit from this completed candle.
        next_limit_side = orientation
        next_limit_price = ma if orientation else None
        if orientation:
            events.append({"ts": ts, "event": "arm", "side": orientation, "price": ma})

        # Flatten at the final weekly bar.
        if i == len(valid) - 1 and positions:
            for pos in positions:
                fill = adverse_market_fill(pos.side, c)
                close_position(pos, ts, fill, "week_end", trades)
                events.append({"ts": ts, "event": "exit_week_end", "side": pos.side, "price": fill})
            positions = []

    return pd.DataFrame(trades), pd.DataFrame(events)


def drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float((equity - equity.cummax()).min())


def summarize_trades(trades: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        return {
            "trades": 0,
            "net": 0.0,
            "closed_dd": 0.0,
            "win_rate": 0.0,
            "pf": 0.0,
            "avg_net": 0.0,
            "targets": 0,
            "stops": 0,
            "flips": 0,
        }
    equity = trades["net"].cumsum()
    wins = trades[trades["net"] > 0]
    losses = trades[trades["net"] < 0]
    gross_win = float(wins["net"].sum())
    gross_loss = abs(float(losses["net"].sum()))
    return {
        "trades": int(len(trades)),
        "net": float(trades["net"].sum()),
        "closed_dd": drawdown(equity),
        "win_rate": 100.0 * len(wins) / len(trades),
        "pf": gross_win / gross_loss if gross_loss > 0 else np.inf,
        "avg_net": float(trades["net"].mean()),
        "targets": int((trades["reason"] == "target").sum()),
        "stops": int((trades["reason"] == "stop").sum()),
        "flips": int((trades["reason"] == "ma_close_flip").sum()),
    }


def weekly_ohlc(bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> Optional[dict[str, float]]:
    window = bars[(bars.index >= start) & (bars.index < end)].copy()
    if window.empty:
        return None
    return {
        "open": float(window["open"].iloc[0]),
        "high": float(window["high"].max()),
        "low": float(window["low"].min()),
        "close": float(window["close"].iloc[-1]),
    }


def weekly_c3_info(bars: pd.DataFrame, week_start: pd.Timestamp) -> Optional[dict[str, object]]:
    c1_start = week_start - pd.Timedelta(days=14)
    c2_start = week_start - pd.Timedelta(days=7)
    c1 = weekly_ohlc(bars, c1_start, c2_start)
    c2 = weekly_ohlc(bars, c2_start, week_start)
    c3 = weekly_ohlc(bars, week_start, week_start + pd.Timedelta(days=7))
    if not c1 or not c2 or not c3:
        return None

    direction: Optional[str] = None
    c2_extreme: Optional[float] = None
    if c2["high"] > c1["high"] and c2["close"] > c1["high"]:
        direction = "bullish"
        c2_extreme = c2["high"]
    elif c2["low"] < c1["low"] and c2["close"] < c1["low"]:
        direction = "bearish"
        c2_extreme = c2["low"]
    if not direction or c2_extreme is None:
        return None

    if direction == "bullish":
        hit = c3["high"] > c2_extreme or c3["close"] > c2_extreme
        closed_beyond = c3["close"] > c2_extreme
    else:
        hit = c3["low"] < c2_extreme or c3["close"] < c2_extreme
        closed_beyond = c3["close"] < c2_extreme
    return {
        "direction": direction,
        "hit": bool(hit),
        "closed_beyond": bool(closed_beyond),
        "c1_start": c1_start.date().isoformat(),
        "c2_start": c2_start.date().isoformat(),
        "c2_extreme": c2_extreme,
    }


def plot_week(
    out_path: Path,
    week: pd.DataFrame,
    week_start: pd.Timestamp,
    ma_col: str,
    trades: pd.DataFrame,
    events: pd.DataFrame,
    title: str,
    chart_bars: str,
    prev_levels: Optional[dict[str, float]],
    c3_info: Optional[dict[str, object]],
) -> None:
    week_end = week_start + pd.Timedelta(days=7)
    candle_bars = week
    candle_width_minutes = 15
    candle_label = "15m candles"
    if chart_bars == "1h":
        candle_bars = (
            week.resample("1h", label="right", closed="right")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna(subset=["open", "high", "low", "close"])
        )
        candle_width_minutes = 60
        candle_label = "1h candles"
    fig, (ax, eq_ax) = plt.subplots(2, 1, figsize=(20, 9.5), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05})
    shade_rth(ax, week_start, week_end)
    plot_candles(ax, candle_bars, width_days=(candle_width_minutes / (24 * 60)) * 0.68)
    ax.plot(week.index, week[ma_col], color="#1f3a93", linewidth=1.8, label="15m MA500")
    if prev_levels:
        level_specs = [
            ("prev_high", "Prev week high", "#7b1fa2", "-"),
            ("prev_low", "Prev week low", "#7b1fa2", "-"),
            ("prev_mid", "Prev week 50%", "#6d6d6d", "--"),
            ("prev_close", "Prev week close", "#f57c00", "-."),
        ]
        x_text = week.index[0] + (week.index[-1] - week.index[0]) * 0.01
        for key, label, color, linestyle in level_specs:
            value = prev_levels.get(key)
            if value is None or pd.isna(value):
                continue
            ax.axhline(value, color=color, linestyle=linestyle, linewidth=1.0, alpha=0.8, label=label)
            ax.text(
                x_text,
                value,
                "%s %.2f" % (label, value),
                color=color,
                fontsize=7,
                va="bottom",
                ha="left",
                alpha=0.9,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.55, "pad": 1.0},
                zorder=9,
            )

    if not trades.empty:
        for _, tr in trades.iterrows():
            color = "#008c5a" if tr["side"] == "long" else "#c62828"
            marker = "^" if tr["side"] == "long" else "v"
            ax.scatter([tr["entry_ts"]], [tr["entry_price"]], color=color, marker=marker, s=42, zorder=8)
            ax.scatter([tr["exit_ts"]], [tr["exit_price"]], color="#111111", marker="x", s=42, zorder=8)
            ax.plot([tr["entry_ts"], tr["exit_ts"]], [tr["entry_price"], tr["exit_price"]], color=color, linewidth=0.9, alpha=0.65)
    if not events.empty:
        protected = events[events["event"] == "protect"]
        if not protected.empty:
            ax.scatter(protected["ts"], protected["price"], color="#f9a825", marker="D", s=22, zorder=7, label="SL locked")

    title_color = "#222222"
    c3_label = "No weekly C3"
    if c3_info:
        is_bull = c3_info["direction"] == "bullish"
        title_color = "#008c5a" if is_bull else "#c62828"
        arrow = "BULL" if is_bull else "BEAR"
        hit = "hit" if c3_info["hit"] else "miss"
        c3_label = "Weekly C3 %s %s | C2 extreme %.2f" % (arrow, hit, c3_info["c2_extreme"])
        ax.text(
            0.012,
            0.985,
            c3_label,
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=10,
            color="white",
            bbox={
                "facecolor": title_color,
                "edgecolor": "none",
                "alpha": 0.85,
                "boxstyle": "round,pad=0.25",
            },
            zorder=12,
        )
    ax.set_title("%s - %s, original 15m MA500 - %s" % (title, candle_label, c3_label), color=title_color)
    ax.set_ylabel("NQ")
    ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
    ax.legend(loc="upper left", fontsize=9)

    if not trades.empty:
        eq = trades.sort_values("exit_ts").set_index("exit_ts")["net"].cumsum()
        eq_ax.step(eq.index, eq.values, where="post", color="#1f3a93", linewidth=1.35)
        eq_ax.axhline(0, color="#777777", linewidth=0.7)
    eq_ax.set_ylabel("Closed $")
    eq_ax.grid(True, color="#e6e6e6", linewidth=0.5)
    eq_ax.xaxis.set_major_locator(mdates.HourLocator(interval=8, tz=week.index.tz))
    eq_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=week.index.tz))
    eq_ax.set_xlabel("Time (America/New_York)")
    for label in eq_ax.get_xticklabels():
        label.set_rotation(78)
        label.set_fontsize(7)
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def run_variant(
    bars: pd.DataFrame,
    out_root: Path,
    *,
    name: str,
    max_units: int,
    rearm_when_protected: bool,
    charts: int,
    risk_pts: float,
    target_pts: float,
    protect_trigger_pts: float,
    protect_profit_pts: float,
    chart_bars: str,
) -> dict[str, object]:
    ma_col = "ma500"
    variant_root = out_root / name
    (variant_root / "charts").mkdir(parents=True, exist_ok=True)
    weeks = recent_week_starts(bars[bars[ma_col].notna()], 9999)
    all_trades: list[pd.DataFrame] = []
    week_rows: list[dict[str, object]] = []
    chart_candidates: list[tuple[float, pd.Timestamp, pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[dict[str, float]], Optional[dict[str, object]]]] = []

    for week_start in weeks:
        week_end = week_start + pd.Timedelta(days=7)
        week = bars[(bars.index >= week_start) & (bars.index < week_end)].copy()
        prev_week = bars[(bars.index >= week_start - pd.Timedelta(days=7)) & (bars.index < week_start)].copy()
        if week.empty:
            continue
        prev_levels = None
        if not prev_week.empty:
            prev_high = float(prev_week["high"].max())
            prev_low = float(prev_week["low"].min())
            prev_levels = {
                "prev_high": prev_high,
                "prev_low": prev_low,
                "prev_mid": prev_low + 0.5 * (prev_high - prev_low),
                "prev_close": float(prev_week["close"].iloc[-1]),
            }
        c3_info = weekly_c3_info(bars, week_start)
        trades, events = simulate_week(
            week,
            ma_col=ma_col,
            risk_pts=risk_pts,
            target_pts=target_pts,
            protect_trigger_pts=protect_trigger_pts,
            protect_profit_pts=protect_profit_pts,
            max_units=max_units,
            rearm_when_protected=rearm_when_protected,
        )
        if not trades.empty:
            trades.insert(0, "week_start", week_start.date().isoformat())
            all_trades.append(trades)
        stats = summarize_trades(trades)
        row = {
            "week_start": week_start.date().isoformat(),
            "week_end": (week_end - pd.Timedelta(days=1)).date().isoformat(),
            "bars": len(week),
        }
        row.update(stats)
        week_rows.append(row)
        chart_score = abs(float(stats["net"])) + int(stats["trades"]) * 100.0
        if not trades.empty:
            chart_candidates.append((chart_score, week_start, week, trades, events, prev_levels, c3_info))

    trades_all = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    weeks_df = pd.DataFrame(week_rows)
    trades_all.to_csv(variant_root / "trades.csv", index=False)
    weeks_df.to_csv(variant_root / "weekly_summary.csv", index=False)

    chart_rows: list[dict[str, object]] = []
    chart_candidates.sort(key=lambda x: x[0], reverse=True)
    for idx, (_, week_start, week, trades, events, prev_levels, c3_info) in enumerate(chart_candidates[:charts], start=1):
        rel = Path("charts") / ("%03d_%s.png" % (idx, week_start.date().isoformat()))
        title = "%s - %s - net $%.0f - %d trades" % (
            name,
            week_start.date().isoformat(),
            trades["net"].sum(),
            len(trades),
        )
        plot_week(variant_root / rel, week, week_start, ma_col, trades, events, title, chart_bars, prev_levels, c3_info)
        c3_label = ""
        if c3_info:
            c3_label = "%s_%s" % (c3_info["direction"], "hit" if c3_info["hit"] else "miss")
        chart_rows.append(
            {
                "idx": idx,
                "week_start": week_start.date().isoformat(),
                "net": float(trades["net"].sum()),
                "trades": int(len(trades)),
                "weekly_c3": c3_label,
                "chart": str(rel),
            }
        )

    summary = summarize_trades(trades_all)
    summary["weeks"] = int(len(weeks_df))
    summary["active_weeks"] = int((weeks_df["trades"] > 0).sum()) if not weeks_df.empty else 0
    summary["max_units"] = max_units
    summary["rearm_when_protected"] = rearm_when_protected
    summary["risk_pts"] = risk_pts
    summary["target_pts"] = target_pts
    summary["protect_trigger_pts"] = protect_trigger_pts
    summary["protect_profit_pts"] = protect_profit_pts

    lines = [
        "# NQ MA500 Weekly Retest Replay - %s" % name,
        "",
        "Rules: 15m MA500 is computed from completed 15m closes. If the latest completed close is below MA500, arm/update a short limit at MA500 for the next bar; if above, arm/update a long limit. A close through the MA exits any opposite position at that bar close and flips orientation. One NQ contract per unit; risk %.1f pts (~$%.0f), target %.1f pts, stop locks to %.1f pts profit after %.1f pts favorable move. Stops/market exits include 1 tick adverse slippage and $%.2f per closed unit. Same-bar stop/target ambiguity is stop-first." % (
            risk_pts,
            risk_pts * POINT_VALUE,
            target_pts,
            protect_profit_pts,
            protect_trigger_pts,
            FEE_PER_UNIT,
        ),
        "",
        "Charts render `%s` price candles, but the MA line and replay decisions remain the original completed-bar `15m MA500`. Horizontal context lines show the previous calendar week's high, low, close, and 50%% high-low midpoint. Weekly C3 uses the same local candle-theory rule as the monthly C3 work: C1 range, C2 closes beyond C1 high/low, the current week is C3." % chart_bars,
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Weeks | %d |" % summary["weeks"],
        "| Active weeks | %d |" % summary["active_weeks"],
        "| Trades | %d |" % summary["trades"],
        "| Net | $%s |" % f"{summary['net']:,.2f}",
        "| Closed DD | $%s |" % f"{summary['closed_dd']:,.2f}",
        "| Net / DD | %.2f |" % (summary["net"] / abs(summary["closed_dd"]) if summary["closed_dd"] else 0.0),
        "| Win rate | %.1f%% |" % summary["win_rate"],
        "| PF | %.2f |" % summary["pf"],
        "| Targets | %d |" % summary["targets"],
        "| Stops | %d |" % summary["stops"],
        "| MA close flips | %d |" % summary["flips"],
        "",
        "## Charts",
        "",
        "| # | Week | Weekly C3 | Net | Trades | Chart |",
        "|---:|---|---|---:|---:|---|",
    ]
    for row in chart_rows:
        lines.append("| {idx} | {week_start} | {weekly_c3} | ${net:,.2f} | {trades} | [{chart}]({chart}) |".format(**row))
    (variant_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return {"name": name, **summary, "index": str(variant_root / "INDEX.md")}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay NQ 15m MA500 weekly retest strategy.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/nq_ma500_weekly_retest")
    parser.add_argument("--charts", type=int, default=60)
    parser.add_argument("--risk-pts", type=float, default=25.0)
    parser.add_argument("--target-pts", type=float, default=200.0)
    parser.add_argument("--protect-trigger-pts", type=float, default=100.0)
    parser.add_argument("--protect-profit-pts", type=float, default=10.0)
    parser.add_argument("--chart-bars", choices=["15m", "1h"], default="1h")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)

    if args.output_root.exists() and not args.no_force:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    bars = load_15m(500)
    bars = bars[bars["ma500"].notna()].copy()

    summaries = [
        run_variant(
            bars,
            args.output_root,
            name="single_unit",
            max_units=1,
            rearm_when_protected=False,
            charts=args.charts,
            risk_pts=args.risk_pts,
            target_pts=args.target_pts,
            protect_trigger_pts=args.protect_trigger_pts,
            protect_profit_pts=args.protect_profit_pts,
            chart_bars=args.chart_bars,
        ),
        run_variant(
            bars,
            args.output_root,
            name="protected_rearm_max3",
            max_units=3,
            rearm_when_protected=True,
            charts=args.charts,
            risk_pts=args.risk_pts,
            target_pts=args.target_pts,
            protect_trigger_pts=args.protect_trigger_pts,
            protect_profit_pts=args.protect_profit_pts,
            chart_bars=args.chart_bars,
        ),
    ]
    pd.DataFrame(summaries).to_csv(args.output_root / "summary.csv", index=False)
    lines = [
        "# NQ 15m MA500 Weekly Retest Replay",
        "",
        "First-pass research replay of the MA500 retest idea. This is standalone research, not yet a `StrategyPlugin`. Charts use `%s` candles over the original 15m MA500 replay." % args.chart_bars,
        "",
        "| Variant | Weeks | Active Weeks | Trades | Net | Closed DD | Net / DD | Win % | PF | Targets | Stops | MA flips | Report |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summaries:
        net_dd = row["net"] / abs(row["closed_dd"]) if row["closed_dd"] else 0.0
        rel = Path(row["index"]).relative_to(args.output_root)
        lines.append(
            "| {name} | {weeks} | {active_weeks} | {trades} | ${net:,.2f} | ${closed_dd:,.2f} | {net_dd:.2f} | {win_rate:.1f}% | {pf:.2f} | {targets} | {stops} | {flips} | [{rel}]({rel}) |".format(
                net_dd=net_dd, rel=rel, **row
            )
        )
    (args.output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
