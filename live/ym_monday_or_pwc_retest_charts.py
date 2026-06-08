from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Literal, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .nq_15m_ma200_supertrend_100_week_charts import plot_candles, shade_rth
from .nq_ma500_retest_weekly_replay import TICK_SIZE, adverse_stop_fill, weekly_c3_info, weekly_ohlc
from .nq_weekly_mid_ma500_bias_replay import to_hourly_with_ma
from .replay_audit import POINT_VALUES
from .ym_weekly_chart_context import compute_weekly_context, draw_weekly_context_panel


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
FEE_PER_UNIT = 1.50
RISK_PTS = 50.0
TARGET_PTS = 300.0
OR_END = time(9, 0)


@dataclass
class OpeningRange:
    high: float
    low: float
    start: pd.Timestamp
    end: pd.Timestamp


def read_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
    df = df.set_index("ts").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    df["ma500"] = df["close"].rolling(500).mean()
    return df


def monday_opening_range(day_15m: pd.DataFrame) -> Optional[OpeningRange]:
    if day_15m.empty:
        return None
    day = day_15m.index[0].normalize()
    if day.weekday() != 0:
        return None
    or_start = day
    or_end = day + pd.Timedelta(hours=9)
    window = day_15m[(day_15m.index > or_start) & (day_15m.index <= or_end)]
    if window.empty:
        return None
    return OpeningRange(
        high=float(window["high"].max()),
        low=float(window["low"].min()),
        start=or_start,
        end=or_end,
    )


def pnl_points(side: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if side == "long" else entry - exit_price


def bullish_or_breakout(o: float, h: float, l: float, c: float, or_high: float) -> bool:
    """Close above OR high after trading at/through the boundary; wick-only pierces do not count."""
    if c <= or_high:
        return False
    return l <= or_high


def bearish_or_breakout(o: float, h: float, l: float, c: float, or_low: float) -> bool:
    """Close below OR low after trading at/through the boundary; wick-only pierces do not count."""
    if c >= or_low:
        return False
    return h >= or_low


def simulate_monday(
    monday_15m: pd.DataFrame,
    week_15m: pd.DataFrame,
    *,
    pwc: float,
    opening_range: OpeningRange,
    point_value: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    armed_side: Optional[str] = None
    pos: Optional[dict[str, object]] = None

    monday_end = opening_range.start + pd.Timedelta(days=1)
    signal_bars = monday_15m[monday_15m.index > opening_range.end].copy()
    manage_bars = week_15m[week_15m.index > opening_range.end].copy()

    signal_idx = set(signal_bars.index)
    for ts, row in manage_bars.iterrows():
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        is_signal_bar = ts in signal_idx and ts < monday_end

        if pos:
            side = str(pos["side"])
            entry = float(pos["entry_price"])
            if side == "long":
                pos["mae_pts"] = min(float(pos["mae_pts"]), l - entry)
                pos["mfe_pts"] = max(float(pos["mfe_pts"]), h - entry)
                stop = entry - RISK_PTS
                target = entry + TARGET_PTS
                if l <= stop:
                    fill = adverse_stop_fill(side, stop, o)
                    pts = pnl_points(side, entry, fill)
                    trades.append(
                        {
                            "entry_ts": pos["entry_ts"],
                            "exit_ts": ts,
                            "side": side,
                            "entry_price": entry,
                            "exit_price": fill,
                            "reason": "stop",
                            "points": pts,
                            "net": pts * point_value - FEE_PER_UNIT,
                        }
                    )
                    events.append({"ts": ts, "event": "stop", "side": side, "price": fill})
                    pos = None
                elif h >= target:
                    pts = pnl_points(side, entry, target)
                    trades.append(
                        {
                            "entry_ts": pos["entry_ts"],
                            "exit_ts": ts,
                            "side": side,
                            "entry_price": entry,
                            "exit_price": target,
                            "reason": "target",
                            "points": pts,
                            "net": pts * point_value - FEE_PER_UNIT,
                        }
                    )
                    events.append({"ts": ts, "event": "target", "side": side, "price": target})
                    pos = None
            else:
                pos["mae_pts"] = min(float(pos["mae_pts"]), entry - h)
                pos["mfe_pts"] = max(float(pos["mfe_pts"]), entry - l)
                stop = entry + RISK_PTS
                target = entry - TARGET_PTS
                if h >= stop:
                    fill = adverse_stop_fill(side, stop, o)
                    pts = pnl_points(side, entry, fill)
                    trades.append(
                        {
                            "entry_ts": pos["entry_ts"],
                            "exit_ts": ts,
                            "side": side,
                            "entry_price": entry,
                            "exit_price": fill,
                            "reason": "stop",
                            "points": pts,
                            "net": pts * point_value - FEE_PER_UNIT,
                        }
                    )
                    events.append({"ts": ts, "event": "stop", "side": side, "price": fill})
                    pos = None
                elif l <= target:
                    pts = pnl_points(side, entry, target)
                    trades.append(
                        {
                            "entry_ts": pos["entry_ts"],
                            "exit_ts": ts,
                            "side": side,
                            "entry_price": entry,
                            "exit_price": target,
                            "reason": "target",
                            "points": pts,
                            "net": pts * point_value - FEE_PER_UNIT,
                        }
                    )
                    events.append({"ts": ts, "event": "target", "side": side, "price": target})
                    pos = None
            if pos:
                continue

        if not is_signal_bar:
            continue

        if armed_side == "long" and l <= pwc:
            pos = {
                "side": "long",
                "entry_ts": ts,
                "entry_price": pwc,
                "mae_pts": l - pwc,
                "mfe_pts": h - pwc,
            }
            events.append({"ts": ts, "event": "entry_long", "side": "long", "price": pwc})
            armed_side = None
            continue
        if armed_side == "short" and h >= pwc:
            pos = {
                "side": "short",
                "entry_ts": ts,
                "entry_price": pwc,
                "mae_pts": pwc - h,
                "mfe_pts": pwc - l,
            }
            events.append({"ts": ts, "event": "entry_short", "side": "short", "price": pwc})
            armed_side = None
            continue

        if bullish_or_breakout(o, h, l, c, opening_range.high) and armed_side != "long":
            armed_side = "long"
            events.append({"ts": ts, "event": "breakout_long", "side": "long", "price": c})
        elif bearish_or_breakout(o, h, l, c, opening_range.low) and armed_side != "short":
            armed_side = "short"
            events.append({"ts": ts, "event": "breakout_short", "side": "short", "price": c})

    if pos:
        side = str(pos["side"])
        entry = float(pos["entry_price"])
        last = manage_bars.iloc[-1]
        fill = float(last["close"]) - TICK_SIZE if side == "long" else float(last["close"]) + TICK_SIZE
        pts = pnl_points(side, entry, fill)
        trades.append(
            {
                "entry_ts": pos["entry_ts"],
                "exit_ts": manage_bars.index[-1],
                "side": side,
                "entry_price": entry,
                "exit_price": fill,
                "reason": "week_end",
                "points": pts,
                "net": pts * point_value - FEE_PER_UNIT,
            }
        )
        events.append({"ts": manage_bars.index[-1], "event": "week_end", "side": side, "price": fill})

    return pd.DataFrame(trades), pd.DataFrame(events)


def plot_week_or(
    out_path: Path,
    week_15m: pd.DataFrame,
    week_1h: pd.DataFrame,
    week_start: pd.Timestamp,
    prev_levels: dict[str, float],
    opening_range: OpeningRange,
    trades: pd.DataFrame,
    events: pd.DataFrame,
    c3_info: Optional[dict[str, object]],
    weekly_context: Optional[dict[str, object]],
    breakout: Optional[Literal["long", "short", "none"]],
) -> None:
    week_end = week_start + pd.Timedelta(days=7)
    if weekly_context is not None:
        weekly_context = dict(weekly_context)
        weekly_context["shown_week"] = week_start.date().isoformat()
        fig = plt.figure(figsize=(20, 9.5))
        gs = fig.add_gridspec(2, 2, height_ratios=[4, 1], width_ratios=[1.0, 1.8], hspace=0.08, wspace=0.06)
        ax = fig.add_subplot(gs[0, :])
    else:
        fig, ax = plt.subplots(1, 1, figsize=(20, 8))

    shade_rth(ax, week_start, week_end)
    ax.axvspan(opening_range.start, opening_range.end, color="#fff3e0", alpha=0.35, zorder=0)
    plot_candles(ax, week_1h, width_days=(60 / (24 * 60)) * 0.68)
    ax.plot(week_15m.index, week_15m["ma500"], color="#1f3a93", linewidth=1.55, label="15m MA500")

    specs = [
        ("prev_high", "PWH", "#7b1fa2", "-"),
        ("prev_low", "PWL", "#7b1fa2", "-"),
        ("prev_mid", "PW 50%", "#555555", "--"),
        ("prev_close", "PWC", "#f57c00", "-."),
        ("or_high", "OR High", "#00838f", "-"),
        ("or_low", "OR Low", "#00838f", "-"),
    ]
    level_values = dict(prev_levels)
    level_values["or_high"] = opening_range.high
    level_values["or_low"] = opening_range.low
    x_text = week_1h.index[0] + (week_1h.index[-1] - week_1h.index[0]) * 0.01
    for key, label, color, linestyle in specs:
        value = level_values[key]
        ax.axhline(value, color=color, linestyle=linestyle, linewidth=1.0, alpha=0.82, label=label)
        ax.text(x_text, value, "%s %.2f" % (label, value), color=color, fontsize=7, va="bottom", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.58, "pad": 1.0})

    if not trades.empty:
        for _, tr in trades.iterrows():
            color = "#008c5a" if tr["side"] == "long" else "#c62828"
            marker = "^" if tr["side"] == "long" else "v"
            ax.scatter([tr["entry_ts"]], [tr["entry_price"]], color=color, marker=marker, s=46, zorder=8)
            ax.scatter([tr["exit_ts"]], [tr["exit_price"]], color="#111111", marker="x", s=46, zorder=8)
            ax.plot([tr["entry_ts"], tr["exit_ts"]], [tr["entry_price"], tr["exit_price"]], color=color, linewidth=0.9, alpha=0.7)
    if not events.empty:
        bo = events[events["event"].astype(str).str.contains("breakout", na=False)]
        if not bo.empty:
            ax.scatter(bo["ts"], bo["price"], color="#f9a825", marker="D", s=28, zorder=7, label="OR breakout")

    net = float(trades["net"].sum()) if not trades.empty else 0.0
    title_color = "#222222"
    c3_label = "No weekly C3"
    if c3_info:
        title_color = "#008c5a" if c3_info["direction"] == "bullish" else "#c62828"
        c3_label = "Weekly C3 %s %s" % (str(c3_info["direction"]).upper(), "hit" if c3_info["hit"] else "miss")
    bo_label = "no breakout" if breakout in {None, "none"} else "%s breakout" % breakout
    ax.set_title(
        "YM Monday OR→PWC retest week %s | OR %.2f-%.2f | %s | %d trades | net $%.0f | %s"
        % (week_start.date().isoformat(), opening_range.low, opening_range.high, bo_label, len(trades), net, c3_label),
        color=title_color,
        fontsize=11,
    )
    ax.set_ylabel("YM")
    ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=8, tz=week_1h.index.tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=week_1h.index.tz))
    for label in ax.get_xticklabels():
        label.set_rotation(78)
        label.set_fontsize(7)

    if weekly_context is not None:
        draw_weekly_context_panel(fig, gs, 1, weekly_context, "YM")
        fig.text(0.5, 0.02, "Time (America/New_York)", ha="center", fontsize=8)
    else:
        ax.set_xlabel("Time (America/New_York)")
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def breakout_side(events: pd.DataFrame) -> Optional[Literal["long", "short", "none"]]:
    if events.empty:
        return "none"
    for event in ("breakout_long", "breakout_short"):
        if (events["event"] == event).any():
            return "long" if event.endswith("long") else "short"
    return "none"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YM Monday opening-range breakout + PWC retest day charts.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts/ym_monday_or_pwc_retest",
    )
    parser.add_argument("--year-from", type=int, default=2010)
    parser.add_argument("--year-to", type=int, default=2026)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    if args.output_root.exists() and not args.no_force:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    bars = read_bars(args.source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    point_value = POINT_VALUES["YM"]
    bars["date"] = bars.index.normalize()
    rows: list[dict[str, object]] = []

    for day, day_15m in bars.groupby("date"):
        monday = pd.Timestamp(day)
        if monday.tzinfo is None:
            monday = monday.tz_localize(NY)
        else:
            monday = monday.tz_convert(NY)
        if monday.weekday() != 0:
            continue
        if monday.year < args.year_from or monday.year > args.year_to:
            continue
        opening_range = monday_opening_range(day_15m)
        if not opening_range:
            continue
        week_start = monday.normalize()
        week_end = week_start + pd.Timedelta(days=7)
        week_15m = bars[(bars.index >= week_start) & (bars.index < week_end)].copy()
        if week_15m.empty:
            continue
        prev = weekly_ohlc(bars, week_start - pd.Timedelta(days=7), week_start)
        if not prev:
            continue
        prev_levels = {
            "prev_high": float(prev["high"]),
            "prev_low": float(prev["low"]),
            "prev_mid": float(prev["low"]) + 0.5 * (float(prev["high"]) - float(prev["low"])),
            "prev_close": float(prev["close"]),
        }
        week_1h = to_hourly_with_ma(week_15m, "ma500")
        if week_1h.empty:
            continue
        trades, events = simulate_monday(
            day_15m,
            week_15m,
            pwc=prev_levels["prev_close"],
            opening_range=opening_range,
            point_value=point_value,
        )
        bo = breakout_side(events)
        weekly_context = compute_weekly_context(bars, week_start)
        c3_info = weekly_c3_info(bars, week_start)

        year_dir = args.output_root / str(monday.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        out_path = year_dir / ("%s.png" % week_start.date().isoformat())
        plot_week_or(
            out_path,
            week_15m,
            week_1h,
            week_start,
            prev_levels,
            opening_range,
            trades,
            events,
            c3_info,
            weekly_context,
            bo,
        )
        rows.append(
            {
                "week_start": week_start.date().isoformat(),
                "year": int(week_start.year),
                "or_high": opening_range.high,
                "or_low": opening_range.low,
                "pwc": prev_levels["prev_close"],
                "breakout": bo or "none",
                "trades": int(len(trades)),
                "net": float(trades["net"].sum()) if not trades.empty else 0.0,
                "targets": int((trades["reason"] == "target").sum()) if not trades.empty else 0,
                "stops": int((trades["reason"] == "stop").sum()) if not trades.empty else 0,
                "chart": out_path.name,
            }
        )

    index = pd.DataFrame(rows).sort_values(["year", "week_start"]) if rows else pd.DataFrame()
    index.to_csv(args.output_root / "monday_index.csv", index=False)

    trade_days = index[index["trades"] > 0] if not index.empty else pd.DataFrame()
    no_trade = index[index["trades"] == 0] if not index.empty else pd.DataFrame()
    lines = [
        "# YM Monday Opening-Range → PWC Retest Charts",
        "",
        "Strategy: Monday midnight–09:00 ET defines the weekly opening range. After 09:00 Monday, a 15m bar must **cross and close** outside the range (wick-only pierces do not count) to arm a limit at **PWC**. Stop **50** pts, target **300** pts, no daily trade cap. Full-week hourly charts with PWH/PWL/PW50/PWC, OR High/Low, 15m MA500, and weekly context panel.",
        "",
        "Index: [monday_index.csv](monday_index.csv)",
        "",
        "| Year | Weeks | Trade Weeks | No-Trade Weeks | Net | Folder |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    if not index.empty:
        for year, grp in index.groupby("year"):
            folder = "%d/" % int(year)
            td = int((grp["trades"] > 0).sum())
            lines.append(
                "| %d | %d | %d | %d | $%.2f | [%s](%s) |"
                % (int(year), len(grp), td, len(grp) - td, float(grp["net"].sum()), folder, folder)
            )
        for year, grp in index.groupby("year"):
            year_dir = args.output_root / str(int(year))
            year_lines = [
                "# YM Monday OR→PWC %d" % int(year),
                "",
                "| Week | OR Low | OR High | PWC | Breakout | Trades | Net | Chart |",
                "|---|---:|---:|---:|---|---:|---:|---|",
            ]
            for _, row in grp.iterrows():
                year_lines.append(
                    "| {week_start} | {or_low:.2f} | {or_high:.2f} | {pwc:.2f} | {breakout} | {trades} | ${net:,.2f} | [{chart}]({chart}) |".format(**row)
                )
            (year_dir / "INDEX.md").write_text("\n".join(year_lines), encoding="utf-8")
    (args.output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    print("Weeks charted: %d (trade weeks %d, no-trade %d)" % (len(index), len(trade_days), len(no_trade)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
