from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nq_15m_ma200_supertrend_100_week_charts import plot_candles, recent_week_starts, shade_rth
from .nq_ma500_retest_weekly_replay import (
    TICK_SIZE,
    adverse_market_fill,
    adverse_stop_fill,
    drawdown,
    weekly_c3_info,
    weekly_ohlc,
)
from .replay_audit import POINT_VALUES
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
FEE_PER_UNIT = 1.50


def load_15m_for_market(market_name: str, ma_window: int) -> pd.DataFrame:
    cfg = MARKETS[market_name]
    print("Loading %s 1m source..." % cfg.instrument, flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    one_min = concat_all_1m(by_day).sort_index()
    bars = (
        one_min.resample("15min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    ma_col = "ma%d" % ma_window
    bars[ma_col] = pd.to_numeric(bars["close"], errors="coerce").rolling(ma_window).mean()
    return bars


def to_hourly_with_ma(week: pd.DataFrame, ma_col: str) -> pd.DataFrame:
    hourly = (
        week.resample("1h", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            ma500=(ma_col, "last"),
        )
        .dropna(subset=["open", "high", "low", "close", "ma500"])
    )
    return hourly


def pnl_points(side: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if side == "long" else entry - exit_price


def close_trade(
    rows: list[dict[str, object]],
    *,
    week_start: pd.Timestamp,
    side: str,
    entry_ts: pd.Timestamp,
    entry_price: float,
    exit_ts: pd.Timestamp,
    exit_price: float,
    reason: str,
    mae_pts: float,
    mfe_pts: float,
    point_value: float,
) -> None:
    pts = pnl_points(side, entry_price, exit_price)
    rows.append(
        {
            "week_start": week_start.date().isoformat(),
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "reason": reason,
            "points": pts,
            "gross": pts * point_value,
            "fee": FEE_PER_UNIT,
            "net": pts * point_value - FEE_PER_UNIT,
            "mae_pts": mae_pts,
            "mfe_pts": mfe_pts,
        }
    )


def simulate_week(
    bars_1h: pd.DataFrame,
    *,
    week_start: pd.Timestamp,
    midpoint: float,
    pwh: float,
    pwl: float,
    max_trades: int,
    risk_pts: float,
    target_pts: float,
    point_value: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    armed_side: Optional[str] = None
    waiting_reclaim_side: Optional[str] = None
    pos: Optional[dict[str, object]] = None

    for i, (ts, row) in enumerate(bars_1h.iterrows()):
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        ma = float(row["ma500"])

        if pos:
            side = str(pos["side"])
            entry = float(pos["entry_price"])
            if side == "long":
                pos["mae_pts"] = min(float(pos["mae_pts"]), l - entry)
                pos["mfe_pts"] = max(float(pos["mfe_pts"]), h - entry)
                stop = entry - risk_pts
                target = entry + target_pts
                if l <= stop:
                    fill = adverse_stop_fill(side, stop, o)
                    close_trade(
                        trades,
                        week_start=week_start,
                        side=side,
                        entry_ts=pos["entry_ts"],
                        entry_price=entry,
                        exit_ts=ts,
                        exit_price=fill,
                        reason="stop",
                        mae_pts=float(pos["mae_pts"]),
                        mfe_pts=float(pos["mfe_pts"]),
                        point_value=point_value,
                    )
                    events.append({"ts": ts, "event": "exit_stop", "side": side, "price": fill})
                    pos = None
                elif h >= target:
                    close_trade(
                        trades,
                        week_start=week_start,
                        side=side,
                        entry_ts=pos["entry_ts"],
                        entry_price=entry,
                        exit_ts=ts,
                        exit_price=target,
                        reason="target",
                        mae_pts=float(pos["mae_pts"]),
                        mfe_pts=float(pos["mfe_pts"]),
                        point_value=point_value,
                    )
                    events.append({"ts": ts, "event": "exit_target", "side": side, "price": target})
                    pos = None
            else:
                pos["mae_pts"] = min(float(pos["mae_pts"]), entry - h)
                pos["mfe_pts"] = max(float(pos["mfe_pts"]), entry - l)
                stop = entry + risk_pts
                target = entry - target_pts
                if h >= stop:
                    fill = adverse_stop_fill(side, stop, o)
                    close_trade(
                        trades,
                        week_start=week_start,
                        side=side,
                        entry_ts=pos["entry_ts"],
                        entry_price=entry,
                        exit_ts=ts,
                        exit_price=fill,
                        reason="stop",
                        mae_pts=float(pos["mae_pts"]),
                        mfe_pts=float(pos["mfe_pts"]),
                        point_value=point_value,
                    )
                    events.append({"ts": ts, "event": "exit_stop", "side": side, "price": fill})
                    pos = None
                elif l <= target:
                    close_trade(
                        trades,
                        week_start=week_start,
                        side=side,
                        entry_ts=pos["entry_ts"],
                        entry_price=entry,
                        exit_ts=ts,
                        exit_price=target,
                        reason="target",
                        mae_pts=float(pos["mae_pts"]),
                        mfe_pts=float(pos["mfe_pts"]),
                        point_value=point_value,
                    )
                    events.append({"ts": ts, "event": "exit_target", "side": side, "price": target})
                    pos = None

        # The hourly close is the only close/level confirmation.
        if len(trades) >= max_trades:
            armed_side = None
            waiting_reclaim_side = None
        elif pos is None:
            desired = "long" if c > midpoint and ma > midpoint else "short" if c < midpoint and ma < midpoint else None
            if desired:
                if waiting_reclaim_side == "long" and c > midpoint and ma > midpoint:
                    armed_side = "long"
                    waiting_reclaim_side = None
                    events.append({"ts": ts, "event": "reclaim_arm", "side": "long", "price": midpoint})
                elif waiting_reclaim_side == "short" and c < midpoint and ma < midpoint:
                    armed_side = "short"
                    waiting_reclaim_side = None
                    events.append({"ts": ts, "event": "reclaim_arm", "side": "short", "price": midpoint})
                elif waiting_reclaim_side is None:
                    armed_side = desired
                    events.append({"ts": ts, "event": "arm", "side": desired, "price": midpoint})
            elif waiting_reclaim_side is None:
                armed_side = None

        # Limit at previous-week 50%. If the bar opens through the level, require reclaim first.
        if pos is None and armed_side and len(trades) < max_trades:
            if armed_side == "long":
                if o < midpoint:
                    waiting_reclaim_side = "long"
                    armed_side = None
                    events.append({"ts": ts, "event": "gap_through_wait_reclaim", "side": "long", "price": midpoint})
                elif l <= midpoint:
                    pos = {
                        "side": "long",
                        "entry_ts": ts,
                        "entry_price": midpoint,
                        "mae_pts": 0.0,
                        "mfe_pts": 0.0,
                    }
                    armed_side = None
                    events.append({"ts": ts, "event": "entry", "side": "long", "price": midpoint})
            else:
                if o > midpoint:
                    waiting_reclaim_side = "short"
                    armed_side = None
                    events.append({"ts": ts, "event": "gap_through_wait_reclaim", "side": "short", "price": midpoint})
                elif h >= midpoint:
                    pos = {
                        "side": "short",
                        "entry_ts": ts,
                        "entry_price": midpoint,
                        "mae_pts": 0.0,
                        "mfe_pts": 0.0,
                    }
                    armed_side = None
                    events.append({"ts": ts, "event": "entry", "side": "short", "price": midpoint})

        if i == len(bars_1h) - 1 and pos:
            side = str(pos["side"])
            fill = adverse_market_fill(side, c)
            close_trade(
                trades,
                week_start=week_start,
                side=side,
                entry_ts=pos["entry_ts"],
                entry_price=float(pos["entry_price"]),
                exit_ts=ts,
                exit_price=fill,
                reason="week_end",
                mae_pts=float(pos["mae_pts"]),
                mfe_pts=float(pos["mfe_pts"]),
                point_value=point_value,
            )
            events.append({"ts": ts, "event": "exit_week_end", "side": side, "price": fill})
            pos = None

    return pd.DataFrame(trades), pd.DataFrame(events)


def summarize(trades: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        return {"trades": 0, "net": 0.0, "closed_dd": 0.0, "win_rate": 0.0, "pf": 0.0, "targets": 0, "stops": 0}
    eq = trades["net"].cumsum()
    wins = trades[trades["net"] > 0]
    losses = trades[trades["net"] < 0]
    loss_sum = abs(float(losses["net"].sum()))
    return {
        "trades": int(len(trades)),
        "net": float(trades["net"].sum()),
        "closed_dd": drawdown(eq),
        "win_rate": 100.0 * len(wins) / len(trades),
        "pf": float(wins["net"].sum()) / loss_sum if loss_sum > 0 else np.inf,
        "targets": int((trades["reason"] == "target").sum()),
        "stops": int((trades["reason"] == "stop").sum()),
    }


def plot_week(
    out_path: Path,
    week_15m: pd.DataFrame,
    week_1h: pd.DataFrame,
    week_start: pd.Timestamp,
    prev_levels: dict[str, float],
    trades: pd.DataFrame,
    events: pd.DataFrame,
    c3_info: Optional[dict[str, object]],
    title: str,
    instrument: str,
    weekly_context: Optional[dict[str, object]] = None,
) -> None:
    week_end = week_start + pd.Timedelta(days=7)
    if weekly_context is not None:
        from .ym_weekly_chart_context import draw_weekly_context_panel

        weekly_context = dict(weekly_context)
        weekly_context["shown_week"] = week_start.date().isoformat()
        fig = plt.figure(figsize=(20, 9.5))
        gs = fig.add_gridspec(2, 2, height_ratios=[4, 1], width_ratios=[1.0, 1.8], hspace=0.08, wspace=0.06)
        ax = fig.add_subplot(gs[0, :])
    else:
        fig, axes = plt.subplots(2, 1, figsize=(20, 9.5), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05})
        ax, eq_ax = axes

    shade_rth(ax, week_start, week_end)
    plot_candles(ax, week_1h, width_days=(60 / (24 * 60)) * 0.68)
    ax.plot(week_15m.index, week_15m["ma500"], color="#1f3a93", linewidth=1.55, label="15m MA500")

    specs = [
        ("prev_high", "PWH", "#7b1fa2", "-"),
        ("prev_low", "PWL", "#7b1fa2", "-"),
        ("prev_mid", "PW 50%", "#555555", "--"),
        ("prev_close", "PWC", "#f57c00", "-."),
    ]
    x_text = week_1h.index[0] + (week_1h.index[-1] - week_1h.index[0]) * 0.01
    for key, label, color, linestyle in specs:
        value = prev_levels[key]
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
        waits = events[events["event"].astype(str).str.contains("reclaim|gap", na=False)]
        if not waits.empty:
            ax.scatter(waits["ts"], waits["price"], color="#f9a825", marker="D", s=20, zorder=7, label="gap/reclaim state")

    title_color = "#222222"
    c3_label = "No weekly C3"
    if c3_info:
        title_color = "#008c5a" if c3_info["direction"] == "bullish" else "#c62828"
        c3_label = "Weekly C3 %s %s" % (str(c3_info["direction"]).upper(), "hit" if c3_info["hit"] else "miss")
    ax.set_title("%s - %s" % (title, c3_label), color=title_color)
    ax.set_ylabel(instrument)
    ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=8, tz=week_1h.index.tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=week_1h.index.tz))
    for label in ax.get_xticklabels():
        label.set_rotation(78)
        label.set_fontsize(7)

    if weekly_context is not None:
        draw_weekly_context_panel(fig, gs, 1, weekly_context, instrument)
        fig.text(0.5, 0.02, "Time (America/New_York)", ha="center", fontsize=8)
    else:
        if not trades.empty:
            eq = trades.sort_values("exit_ts").set_index("exit_ts")["net"].cumsum()
            eq_ax.step(eq.index, eq.values, where="post", color="#1f3a93", linewidth=1.35)
            eq_ax.axhline(0, color="#777777", linewidth=0.7)
        eq_ax.set_ylabel("Closed $")
        eq_ax.grid(True, color="#e6e6e6", linewidth=0.5)
        eq_ax.xaxis.set_major_locator(mdates.HourLocator(interval=8, tz=week_1h.index.tz))
        eq_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=week_1h.index.tz))
        eq_ax.set_xlabel("Time (America/New_York)")
        for label in eq_ax.get_xticklabels():
            label.set_rotation(78)
            label.set_fontsize(7)
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def run_market(market_name: str, output_root: Path, charts: int, max_trades: int, risk_pts: float, target_pts: float, force: bool) -> dict[str, object]:
    cfg = MARKETS[market_name]
    instrument = cfg.instrument
    point_value = POINT_VALUES[instrument]
    if output_root.exists() and force:
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    bars = load_15m_for_market(market_name, 500)
    bars = bars[bars["ma500"].notna()].copy()
    weeks = recent_week_starts(bars, 9999)

    all_trades: list[pd.DataFrame] = []
    week_rows: list[dict[str, object]] = []
    chart_candidates: list[tuple[float, pd.Timestamp, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float], Optional[dict[str, object]]]] = []
    for week_start in weeks:
        week_end = week_start + pd.Timedelta(days=7)
        prev = weekly_ohlc(bars, week_start - pd.Timedelta(days=7), week_start)
        if not prev:
            continue
        prev_levels = {
            "prev_high": prev["high"],
            "prev_low": prev["low"],
            "prev_mid": prev["low"] + 0.5 * (prev["high"] - prev["low"]),
            "prev_close": prev["close"],
        }
        week_15m = bars[(bars.index >= week_start) & (bars.index < week_end)].copy()
        if week_15m.empty:
            continue
        week_1h = to_hourly_with_ma(week_15m, "ma500")
        if week_1h.empty:
            continue
        trades, events = simulate_week(
            week_1h,
            week_start=week_start,
            midpoint=prev_levels["prev_mid"],
            pwh=prev_levels["prev_high"],
            pwl=prev_levels["prev_low"],
            max_trades=max_trades,
            risk_pts=risk_pts,
            target_pts=target_pts,
            point_value=point_value,
        )
        stats = summarize(trades)
        c3_info = weekly_c3_info(bars, week_start)
        week_rows.append(
            {
                "week_start": week_start.date().isoformat(),
                "trades": stats["trades"],
                "net": stats["net"],
                "closed_dd": stats["closed_dd"],
                "win_rate": stats["win_rate"],
                "pf": stats["pf"],
                "targets": stats["targets"],
                "stops": stats["stops"],
                "prev_high": prev_levels["prev_high"],
                "prev_low": prev_levels["prev_low"],
                "prev_mid": prev_levels["prev_mid"],
                "prev_close": prev_levels["prev_close"],
                "weekly_c3": "" if not c3_info else "%s_%s" % (c3_info["direction"], "hit" if c3_info["hit"] else "miss"),
            }
        )
        if not trades.empty:
            all_trades.append(trades)
            score = abs(float(stats["net"])) + int(stats["trades"]) * 200.0
            chart_candidates.append((score, week_start, week_15m, week_1h, trades, events, prev_levels, c3_info))

    trades_all = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    weeks_df = pd.DataFrame(week_rows)
    trades_all.to_csv(output_root / "trades.csv", index=False)
    weeks_df.to_csv(output_root / "weekly_summary.csv", index=False)
    summary = summarize(trades_all)
    summary["weeks"] = int(len(weeks_df))
    summary["active_weeks"] = int((weeks_df["trades"] > 0).sum()) if not weeks_df.empty else 0
    pd.DataFrame([summary]).to_csv(output_root / "summary.csv", index=False)

    chart_rows = []
    chart_candidates.sort(key=lambda x: x[0], reverse=True)
    for idx, (_, week_start, week_15m, week_1h, trades, events, prev_levels, c3_info) in enumerate(chart_candidates[:charts], start=1):
        rel = Path("charts") / ("%03d_%s.png" % (idx, week_start.date().isoformat()))
        title = "%s weekly 50%% MA500 bias - %s - net $%.0f - %d trades" % (
            instrument,
            week_start.date().isoformat(),
            trades["net"].sum(),
            len(trades),
        )
        plot_week(output_root / rel, week_15m, week_1h, week_start, prev_levels, trades, events, c3_info, title, instrument)
        chart_rows.append(
            {
                "idx": idx,
                "week_start": week_start.date().isoformat(),
                "weekly_c3": "" if not c3_info else "%s_%s" % (c3_info["direction"], "hit" if c3_info["hit"] else "miss"),
                "net": float(trades["net"].sum()),
                "trades": int(len(trades)),
                "chart": str(rel),
            }
        )

    net_dd = summary["net"] / abs(summary["closed_dd"]) if summary["closed_dd"] else 0.0
    lines = [
        "# %s Previous-Week 50%% + MA500 Bias Retest" % instrument,
        "",
        "Mechanical first pass from the chart notes. Previous-week 50%% is the entry level. Bias is active only after an **hourly close** and the current 15m MA500 are both above the level for longs, or both below for shorts. A limit is placed at the 50%% level for the first touch/retest. If the hourly bar opens through the level, the system waits for an hourly reclaim before arming the retest. Max `%d` trades per week, target `%.1f` pts, stop `%.1f` pts, %s point value `$%.2f`, stop/market exits use 1 tick adverse slippage and `$%.2f` fee." % (
            max_trades,
            target_pts,
            risk_pts,
            instrument,
            point_value,
            FEE_PER_UNIT,
        ),
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Weeks | %d |" % summary["weeks"],
        "| Active weeks | %d |" % summary["active_weeks"],
        "| Trades | %d |" % summary["trades"],
        "| Net | $%s |" % f"{summary['net']:,.2f}",
        "| Closed DD | $%s |" % f"{summary['closed_dd']:,.2f}",
        "| Net / DD | %.2f |" % net_dd,
        "| Win rate | %.1f%% |" % summary["win_rate"],
        "| PF | %.2f |" % summary["pf"],
        "| Targets | %d |" % summary["targets"],
        "| Stops | %d |" % summary["stops"],
        "",
        "## Charts",
        "",
        "| # | Week | Weekly C3 | Net | Trades | Chart |",
        "|---:|---|---|---:|---:|---|",
    ]
    for row in chart_rows:
        lines.append("| {idx} | {week_start} | {weekly_c3} | ${net:,.2f} | {trades} | [{chart}]({chart}) |".format(**row))
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)
    return {"market": market_name, "instrument": instrument, **summary, "index": str(output_root / "INDEX.md")}


def run_markets(markets: Sequence[str], output_root: Path, charts: int, max_trades: int, risk_pts: float, target_pts: float, force: bool) -> None:
    if output_root.exists() and force:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for market_name in markets:
        rows.append(
            run_market(
                market_name,
                output_root / market_name,
                charts,
                max_trades,
                risk_pts,
                target_pts,
                force=False,
            )
        )
        pd.DataFrame(rows).to_csv(output_root / "summary.csv", index=False)
    lines = [
        "# Previous-Week 50% + MA500 Bias Retest - Cross Market",
        "",
        "| Market | Instrument | Weeks | Active Weeks | Trades | Net | Closed DD | Net / DD | Win % | PF | Targets | Stops | Report |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        net_dd = row["net"] / abs(row["closed_dd"]) if row["closed_dd"] else 0.0
        rel = Path(row["index"]).resolve().relative_to(output_root.resolve())
        lines.append(
            "| {market} | {instrument} | {weeks} | {active_weeks} | {trades} | ${net:,.2f} | ${closed_dd:,.2f} | {net_dd:.2f} | {win_rate:.1f}% | {pf:.2f} | {targets} | {stops} | [{rel}]({rel}) |".format(
                net_dd=net_dd,
                rel=rel,
                **row,
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay NQ previous-week 50% MA500 bias retest.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/weekly_mid_ma500_bias_retest")
    parser.add_argument("--market", action="append", choices=sorted(MARKETS), help="Market to run. Repeatable.")
    parser.add_argument("--charts", type=int, default=80)
    parser.add_argument("--max-trades", type=int, default=6)
    parser.add_argument("--risk-pts", type=float, default=50.0)
    parser.add_argument("--target-pts", type=float, default=300.0)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    markets = args.market or ["nq"]
    if len(markets) == 1:
        default_single = args.output_root
        if args.output_root == REPO / "live/state/weekly_mid_ma500_bias_retest":
            default_single = REPO / ("live/state/%s_weekly_mid_ma500_bias_retest" % markets[0])
        run_market(markets[0], default_single, args.charts, args.max_trades, args.risk_pts, args.target_pts, force=not args.no_force)
    else:
        run_markets(markets, args.output_root, args.charts, args.max_trades, args.risk_pts, args.target_pts, force=not args.no_force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
