#!/usr/bin/env python3
"""Dynamic NQ CHOP20 range-breakout walkthrough.

This is a daily-bar diagnostic built on the same causal CHOP/efficiency range
detector used by ``chop_range_breakout_charts.py``. It answers a narrow
research question: once a daily range is detected, does buying/selling a later
close-confirmed breakout have useful follow-through?

Rules in this first pass:

- NQ daily bars only.
- Range detector is CHOP20 + efficiency20 + prior-only width percentile.
- The active range updates on every completed range-like daily bar.
- Flat strategy enters 3 units at the daily close when close breaks the active
  range high/low.
- One trade at a time.
- Unlimited attempts are allowed on the active range until a newer range-like
  bar updates the reference box.
- Targets are 0.5R, 1R, and 4R, one unit each.
- Remaining units exit when a later daily close moves back into/through the
  breakout side of the range.

The close-entry assumption is intentionally labeled as diagnostic. A production
variant would need a broker-specific market-on-close/next-open decision and
lower-timeframe sequencing around target fills.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from chop_range_breakout_charts import (
    DEFAULT_SOURCES,
    DetectorParams,
    ROOT,
    _bar_width_days,
    add_range_metrics,
    load_bars,
    plot_candles,
)


DEFAULT_OUTPUT = ROOT / "live" / "state" / "nq_chop20_dynamic_range_breakout_walkthrough"
POINT_VALUE = 20.0
TICK_SIZE = 0.25


@dataclass
class ActiveRange:
    range_id: int
    range_group_id: int
    group_start_idx: int
    confirmed_idx: int
    group_start_ts: str
    confirmed_ts: str
    high: float
    low: float
    width: float
    chop_20: float
    efficiency_20: float
    range_atr_20: float
    range_atr_percentile_252: float
    raw_regime: str
    confirmed_regime: str


@dataclass
class OpenTrade:
    trade_id: int
    range_ref: ActiveRange
    attempt_number: int
    direction: str
    entry_idx: int
    entry_ts: str
    entry_close: float
    entry_price: float
    units_remaining: int = 3
    targets: Dict[str, float] = field(default_factory=dict)
    filled_targets: set[str] = field(default_factory=set)
    exit_unit_numbers: List[int] = field(default_factory=list)


@dataclass
class TradeRecord:
    trade_id: int
    range_id: int
    range_group_id: int
    attempt_number: int
    direction: str
    range_start_ts: str
    range_confirmed_ts: str
    breakout_ts: str
    entry_close: float
    entry_price: float
    range_high: float
    range_low: float
    range_width_r: float
    chop_20: float
    efficiency_20: float
    range_atr_20: float
    range_atr_percentile_252: float
    exit_ts: str
    bars_held: int
    exit_reason: str
    units: int
    winning_units: int
    gross_points: float
    net_usd: float
    mfe_pts: float
    mae_pts: float
    chart: str = ""


@dataclass
class UnitExit:
    trade_id: int
    unit_number: int
    direction: str
    entry_ts: str
    exit_ts: str
    entry_price: float
    exit_price: float
    target_r: float
    reason: str
    points: float
    net_usd: float


def _ts(value) -> str:
    return pd.Timestamp(value).tz_localize(None).date().isoformat()


def _fmt_money(value: float) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"${value:,.0f}"


def _fmt_float(value: float, digits: int = 2) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"{value:,.{digits}f}"


def _exit_price(side: str, close: float, slippage_ticks: int) -> float:
    slip = slippage_ticks * TICK_SIZE
    return float(close - slip if side == "long" else close + slip)


def _entry_price(direction: str, close: float, slippage_ticks: int) -> float:
    slip = slippage_ticks * TICK_SIZE
    return float(close + slip if direction == "long" else close - slip)


def _target_price(direction: str, entry: float, width: float, multiple: float) -> float:
    return float(entry + width * multiple if direction == "long" else entry - width * multiple)


def _points(direction: str, entry: float, exit_price: float) -> float:
    return float(exit_price - entry if direction == "long" else entry - exit_price)


def _range_invalidated(direction: str, close: float, range_high: float, range_low: float) -> bool:
    if direction == "long":
        return close <= range_high
    return close >= range_low


def _trade_mfe_mae(d: pd.DataFrame, trade: OpenTrade, exit_idx: int) -> tuple[float, float]:
    window = d.iloc[trade.entry_idx + 1 : exit_idx + 1]
    if window.empty:
        return 0.0, 0.0
    if trade.direction == "long":
        mfe = float(window["high"].max() - trade.entry_price)
        mae = float(window["low"].min() - trade.entry_price)
    else:
        mfe = float(trade.entry_price - window["low"].min())
        mae = float(trade.entry_price - window["high"].max())
    return mfe, mae


def _make_unit_exit(
    trade: OpenTrade,
    unit_number: int,
    exit_ts: str,
    exit_price: float,
    target_r: float,
    reason: str,
    fee_per_unit: float,
) -> UnitExit:
    points = _points(trade.direction, trade.entry_price, exit_price)
    net_usd = points * POINT_VALUE - fee_per_unit
    return UnitExit(
        trade_id=trade.trade_id,
        unit_number=unit_number,
        direction=trade.direction,
        entry_ts=trade.entry_ts,
        exit_ts=exit_ts,
        entry_price=trade.entry_price,
        exit_price=float(exit_price),
        target_r=float(target_r),
        reason=reason,
        points=points,
        net_usd=net_usd,
    )


def _finalize_trade(
    d: pd.DataFrame,
    trade: OpenTrade,
    unit_exits: List[UnitExit],
    exit_idx: int,
    chart: str = "",
) -> TradeRecord:
    exits = [e for e in unit_exits if e.trade_id == trade.trade_id]
    reasons = {e.reason for e in exits}
    if reasons == {"tp_0_5r", "tp_1r", "tp_4r"}:
        exit_reason = "all_targets"
    elif "range_close_cancel" in reasons and len(reasons) > 1:
        exit_reason = "partial_targets_then_range_cancel"
    elif "range_close_cancel" in reasons:
        exit_reason = "range_close_cancel"
    elif "data_end" in reasons:
        exit_reason = "data_end"
    else:
        exit_reason = ",".join(sorted(reasons))
    mfe, mae = _trade_mfe_mae(d, trade, exit_idx)
    gross_points = float(sum(e.points for e in exits))
    net_usd = float(sum(e.net_usd for e in exits))
    return TradeRecord(
        trade_id=trade.trade_id,
        range_id=trade.range_ref.range_id,
        range_group_id=trade.range_ref.range_group_id,
        attempt_number=trade.attempt_number,
        direction=trade.direction,
        range_start_ts=trade.range_ref.group_start_ts,
        range_confirmed_ts=trade.range_ref.confirmed_ts,
        breakout_ts=trade.entry_ts,
        entry_close=trade.entry_close,
        entry_price=trade.entry_price,
        range_high=trade.range_ref.high,
        range_low=trade.range_ref.low,
        range_width_r=trade.range_ref.width,
        chop_20=trade.range_ref.chop_20,
        efficiency_20=trade.range_ref.efficiency_20,
        range_atr_20=trade.range_ref.range_atr_20,
        range_atr_percentile_252=trade.range_ref.range_atr_percentile_252,
        exit_ts=_ts(d.iloc[exit_idx]["date"]),
        bars_held=int(exit_idx - trade.entry_idx),
        exit_reason=exit_reason,
        units=len(exits),
        winning_units=int(sum(1 for e in exits if e.net_usd > 0)),
        gross_points=gross_points,
        net_usd=net_usd,
        mfe_pts=mfe,
        mae_pts=mae,
        chart=chart,
    )


def simulate(
    d: pd.DataFrame,
    slippage_ticks: int,
    fee_per_unit: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    active_range: Optional[ActiveRange] = None
    open_trade: Optional[OpenTrade] = None
    trades: List[TradeRecord] = []
    unit_exits: List[UnitExit] = []
    active_ranges: List[ActiveRange] = []
    equity_rows: List[dict] = []
    attempts_by_range: Dict[int, int] = {}

    range_id = 0
    range_group_id = 0
    range_group_start_idx: Optional[int] = None
    trade_id = 0
    realized = 0.0
    last_flatten_idx: Optional[int] = None

    for i, row in d.iterrows():
        date_s = _ts(row["date"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        closed_this_bar = False

        if open_trade is not None and i > open_trade.entry_idx:
            for label, target_r in (("tp_0_5r", 0.5), ("tp_1r", 1.0), ("tp_4r", 4.0)):
                if label in open_trade.filled_targets or open_trade.units_remaining <= 0:
                    continue
                target = open_trade.targets[label]
                hit = high >= target if open_trade.direction == "long" else low <= target
                if not hit:
                    continue
                unit_number = 4 - open_trade.units_remaining
                unit_exit = _make_unit_exit(
                    open_trade,
                    unit_number=unit_number,
                    exit_ts=date_s,
                    exit_price=target,
                    target_r=target_r,
                    reason=label,
                    fee_per_unit=fee_per_unit,
                )
                unit_exits.append(unit_exit)
                realized += unit_exit.net_usd
                open_trade.exit_unit_numbers.append(unit_number)
                open_trade.units_remaining -= 1
                open_trade.filled_targets.add(label)

            if open_trade.units_remaining > 0 and _range_invalidated(
                open_trade.direction,
                close,
                open_trade.range_ref.high,
                open_trade.range_ref.low,
            ):
                exit_price = _exit_price(open_trade.direction, close, slippage_ticks)
                while open_trade.units_remaining > 0:
                    unit_number = 4 - open_trade.units_remaining
                    unit_exit = _make_unit_exit(
                        open_trade,
                        unit_number=unit_number,
                        exit_ts=date_s,
                        exit_price=exit_price,
                        target_r=0.0,
                        reason="range_close_cancel",
                        fee_per_unit=fee_per_unit,
                    )
                    unit_exits.append(unit_exit)
                    realized += unit_exit.net_usd
                    open_trade.exit_unit_numbers.append(unit_number)
                    open_trade.units_remaining -= 1

            if open_trade is not None and open_trade.units_remaining <= 0:
                trades.append(_finalize_trade(d, open_trade, unit_exits, int(i)))
                open_trade = None
                last_flatten_idx = int(i)
                closed_this_bar = True

        if open_trade is not None and i == len(d) - 1:
            exit_price = _exit_price(open_trade.direction, close, slippage_ticks)
            while open_trade.units_remaining > 0:
                unit_number = 4 - open_trade.units_remaining
                unit_exit = _make_unit_exit(
                    open_trade,
                    unit_number=unit_number,
                    exit_ts=date_s,
                    exit_price=exit_price,
                    target_r=0.0,
                    reason="data_end",
                    fee_per_unit=fee_per_unit,
                )
                unit_exits.append(unit_exit)
                realized += unit_exit.net_usd
                open_trade.units_remaining -= 1
            trades.append(_finalize_trade(d, open_trade, unit_exits, int(i)))
            open_trade = None
            last_flatten_idx = int(i)
            closed_this_bar = True

        if bool(row["is_range_like"]):
            if range_group_start_idx is None:
                range_group_id += 1
                range_group_start_idx = int(i)
            range_id += 1
            active_range = ActiveRange(
                range_id=range_id,
                range_group_id=range_group_id,
                group_start_idx=range_group_start_idx,
                confirmed_idx=int(i),
                group_start_ts=_ts(d.iloc[range_group_start_idx]["date"]),
                confirmed_ts=date_s,
                high=float(row["range_high_20"]),
                low=float(row["range_low_20"]),
                width=float(row["range_20"]),
                chop_20=float(row["chop_20"]),
                efficiency_20=float(row["efficiency_20"]),
                range_atr_20=float(row["range_atr_20"]),
                range_atr_percentile_252=float(row["range_atr_percentile_252"]),
                raw_regime=str(row["raw_regime"]),
                confirmed_regime=str(row["confirmed_regime"]),
            )
            active_ranges.append(active_range)
        else:
            range_group_start_idx = None

        if (
            open_trade is None
            and active_range is not None
            and int(i) > active_range.confirmed_idx
            and not closed_this_bar
            and last_flatten_idx != int(i)
        ):
            direction = ""
            if close > active_range.high:
                direction = "long"
            elif close < active_range.low:
                direction = "short"
            if direction:
                trade_id += 1
                attempts_by_range[active_range.range_id] = attempts_by_range.get(active_range.range_id, 0) + 1
                entry = _entry_price(direction, close, slippage_ticks)
                targets = {
                    "tp_0_5r": _target_price(direction, entry, active_range.width, 0.5),
                    "tp_1r": _target_price(direction, entry, active_range.width, 1.0),
                    "tp_4r": _target_price(direction, entry, active_range.width, 4.0),
                }
                open_trade = OpenTrade(
                    trade_id=trade_id,
                    range_ref=active_range,
                    attempt_number=attempts_by_range[active_range.range_id],
                    direction=direction,
                    entry_idx=int(i),
                    entry_ts=date_s,
                    entry_close=close,
                    entry_price=entry,
                    targets=targets,
                )

        open_mtm = 0.0
        open_units = 0
        if open_trade is not None:
            open_units = open_trade.units_remaining
            mtm_points = _points(open_trade.direction, open_trade.entry_price, close)
            open_mtm = mtm_points * POINT_VALUE * open_units
        equity_rows.append(
            {
                "date": date_s,
                "closed_equity": realized,
                "mtm_equity": realized + open_mtm,
                "open_units": open_units,
                "active_range_id": active_range.range_id if active_range else "",
                "open_trade_id": open_trade.trade_id if open_trade else "",
            }
        )

    trades_df = pd.DataFrame([asdict(t) for t in trades])
    exits_df = pd.DataFrame([asdict(e) for e in unit_exits])
    ranges_df = pd.DataFrame([asdict(r) for r in active_ranges])
    equity_df = pd.DataFrame(equity_rows)
    if not equity_df.empty:
        equity_df["closed_peak"] = equity_df["closed_equity"].cummax()
        equity_df["closed_drawdown"] = equity_df["closed_equity"] - equity_df["closed_peak"]
        equity_df["mtm_peak"] = equity_df["mtm_equity"].cummax()
        equity_df["mtm_drawdown"] = equity_df["mtm_equity"] - equity_df["mtm_peak"]
    return trades_df, exits_df, ranges_df, equity_df


def summarize(trades: pd.DataFrame, exits: pd.DataFrame, equity: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trades": 0,
            "units": 0,
            "net_usd": 0.0,
            "closed_drawdown": 0.0,
            "mtm_drawdown": 0.0,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "net_stress": np.nan,
        }
    gross_profit = float(exits.loc[exits["net_usd"] > 0, "net_usd"].sum()) if not exits.empty else 0.0
    gross_loss = float(exits.loc[exits["net_usd"] < 0, "net_usd"].sum()) if not exits.empty else 0.0
    closed_dd = float(equity["closed_drawdown"].min()) if not equity.empty else np.nan
    mtm_dd = float(equity["mtm_drawdown"].min()) if not equity.empty else np.nan
    net = float(trades["net_usd"].sum())
    return {
        "trades": int(len(trades)),
        "units": int(len(exits)),
        "net_usd": net,
        "closed_drawdown": closed_dd,
        "mtm_drawdown": mtm_dd,
        "win_rate": float((trades["net_usd"] > 0).mean()),
        "profit_factor": float(gross_profit / abs(gross_loss)) if gross_loss < 0 else np.nan,
        "net_stress": float(net / abs(mtm_dd)) if mtm_dd < 0 else np.nan,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "avg_trade": float(trades["net_usd"].mean()),
        "median_trade": float(trades["net_usd"].median()),
        "best_trade": float(trades["net_usd"].max()),
        "worst_trade": float(trades["net_usd"].min()),
        "avg_bars_held": float(trades["bars_held"].mean()),
        "median_bars_held": float(trades["bars_held"].median()),
    }


def yearly_summary(trades: pd.DataFrame, equity: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    y = trades.copy()
    y["year"] = pd.to_datetime(y["exit_ts"]).dt.year
    rows = []
    eq = equity.copy()
    eq["year"] = pd.to_datetime(eq["date"]).dt.year
    for year, g in y.groupby("year"):
        eq_y = eq[eq["year"] == year]
        rows.append(
            {
                "year": int(year),
                "trades": int(len(g)),
                "units": int(g["units"].sum()),
                "net_usd": float(g["net_usd"].sum()),
                "closed_drawdown": float(eq_y["closed_drawdown"].min()) if not eq_y.empty else np.nan,
                "mtm_drawdown": float(eq_y["mtm_drawdown"].min()) if not eq_y.empty else np.nan,
                "win_rate": float((g["net_usd"] > 0).mean()),
                "profit_factor": _profit_factor_for_trade_ids(trades, year),
            }
        )
    return pd.DataFrame(rows).sort_values("year")


def _profit_factor_for_trade_ids(trades: pd.DataFrame, year: int) -> float:
    g = trades[pd.to_datetime(trades["exit_ts"]).dt.year == year]
    gp = float(g.loc[g["net_usd"] > 0, "net_usd"].sum())
    gl = float(g.loc[g["net_usd"] < 0, "net_usd"].sum())
    return gp / abs(gl) if gl < 0 else np.nan


def plot_equity(equity: pd.DataFrame, out_path: Path) -> None:
    if equity.empty:
        return
    dates = pd.to_datetime(equity["date"])
    fig, (ax, dd) = plt.subplots(
        2,
        1,
        figsize=(14, 7.5),
        sharex=True,
        gridspec_kw={"height_ratios": [3.2, 1.2], "hspace": 0.06},
    )
    fig.patch.set_facecolor("#f7f8fa")
    for a in (ax, dd):
        a.set_facecolor("#fbfcfd")
        a.grid(True, alpha=0.25, linewidth=0.6)
    ax.plot(dates, equity["closed_equity"], color="#2563eb", linewidth=1.35, label="Closed equity")
    ax.plot(dates, equity["mtm_equity"], color="#111827", linewidth=0.85, alpha=0.65, label="MTM equity")
    ax.set_title("NQ CHOP20 Dynamic Daily Range Breakout - Equity", loc="left", fontweight="bold")
    ax.set_ylabel("USD")
    ax.legend(loc="upper left")
    dd.fill_between(dates, equity["mtm_drawdown"], 0, color="#dc2626", alpha=0.18, label="MTM drawdown")
    dd.plot(dates, equity["closed_drawdown"], color="#b91c1c", linewidth=0.9, label="Closed drawdown")
    dd.set_ylabel("Drawdown")
    dd.legend(loc="lower left")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_trade_chart(d: pd.DataFrame, trade: pd.Series, exits: pd.DataFrame, out_path: Path) -> None:
    entry_idx = int(d.index[d["date"].dt.strftime("%Y-%m-%d") == trade["breakout_ts"]][0])
    exit_idx = int(d.index[d["date"].dt.strftime("%Y-%m-%d") == trade["exit_ts"]][0])
    start_idx = max(0, entry_idx - 70)
    end_idx = min(len(d) - 1, exit_idx + 35)
    plot = d.iloc[start_idx : end_idx + 1].copy()
    dates = pd.to_datetime(plot["date"])
    fig, (ax, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(17, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [4.8, 1.35, 1.1], "hspace": 0.08},
    )
    fig.patch.set_facecolor("#f7f8fa")
    for a in (ax, ax2, ax3):
        a.set_facecolor("#fbfcfd")
        a.grid(True, alpha=0.25, linewidth=0.6)

    plot_candles(ax, plot, width_days=_bar_width_days("D"))
    range_high = float(trade["range_high"])
    range_low = float(trade["range_low"])
    entry_ts = pd.Timestamp(trade["breakout_ts"])
    exit_ts = pd.Timestamp(trade["exit_ts"])
    confirmed_ts = pd.Timestamp(trade["range_confirmed_ts"])
    start_ts = pd.Timestamp(trade["range_start_ts"])
    ax.axhspan(range_low, range_high, color="#2563eb", alpha=0.065, label="Active range")
    ax.axhline(range_high, color="#1d4ed8", linewidth=1.1)
    ax.axhline(range_low, color="#1d4ed8", linewidth=1.1)
    ax.axvspan(start_ts, confirmed_ts, color="#f59e0b", alpha=0.12, label="Range-like window")
    ax.axvline(entry_ts, color="#111827", linewidth=1.1, linestyle="--", label="Breakout close entry")
    ax.axvline(exit_ts, color="#7f1d1d", linewidth=1.0, linestyle=":", label="Final exit")

    direction = str(trade["direction"])
    entry = float(trade["entry_price"])
    width = float(trade["range_width_r"])
    color = "#047857" if direction == "long" else "#b91c1c"
    marker = "^" if direction == "long" else "v"
    ax.scatter([entry_ts], [entry], marker=marker, s=90, color=color, edgecolor="#111827", linewidth=0.5, zorder=9)
    target_levels = []
    for r, style in ((0.5, "--"), (1.0, "--"), (4.0, "-.")):
        target = _target_price(direction, entry, width, r)
        target_levels.append(target)
        ax.axhline(target, color=color, linewidth=0.75, linestyle=style, alpha=0.72)
        ax.text(dates.iloc[-1], target, f" {r:g}R", va="center", ha="left", fontsize=8, color=color)

    trade_exits = exits[exits["trade_id"] == int(trade["trade_id"])]
    for _, ex in trade_exits.iterrows():
        x = pd.Timestamp(ex["exit_ts"])
        y = float(ex["exit_price"])
        ax.scatter([x], [y], marker="o", s=55, color="#f97316", edgecolor="#111827", linewidth=0.45, zorder=10)
        ax.text(x, y, f" {ex['reason']}", fontsize=7.5, va="bottom", ha="left", color="#111827")

    plotted_exits = trade_exits["exit_price"].astype(float).tolist()
    y_candidates = [float(plot["low"].min()), float(plot["high"].max()), range_low, range_high, entry]
    y_candidates.extend(target_levels)
    y_candidates.extend(plotted_exits)
    y_min = float(min(y_candidates))
    y_max = float(max(y_candidates))
    pad = (y_max - y_min) * 0.06 if y_max > y_min else 1.0
    ax.set_ylim(y_min - pad, y_max + pad)
    ax.set_ylabel("NQ daily price")
    ax.set_title(
        f"NQ dynamic CHOP20 range trade {int(trade['trade_id']):03d} | {direction.upper()} | "
        f"net {_fmt_money(float(trade['net_usd']))} | {trade['breakout_ts']} to {trade['exit_ts']}",
        loc="left",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(loc="upper left", fontsize=8, ncol=4)

    ax2.plot(plot["date"], plot["chop_20"], color="#7c3aed", linewidth=1.05, label="CHOP(20)")
    ax2.axhline(61.8, color="#7c3aed", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2_t = ax2.twinx()
    ax2_t.plot(plot["date"], plot["efficiency_20"], color="#0891b2", linewidth=1.0, label="Efficiency(20)")
    ax2_t.axhline(0.35, color="#0891b2", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.set_ylim(0, 100)
    ax2_t.set_ylim(0, 1)
    ax2.set_ylabel("CHOP")
    ax2_t.set_ylabel("Efficiency")
    lines, labels = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_t.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=8, ncol=2)

    ax3.plot(plot["date"], plot["range_atr_percentile_252"], color="#374151", linewidth=1.05, label="Range/ATR prior-252 pct")
    ax3.axhspan(0.20, 0.80, color="#10b981", alpha=0.08)
    ax3.axhline(0.20, color="#6b7280", linestyle="--", linewidth=0.8)
    ax3.axhline(0.80, color="#6b7280", linestyle="--", linewidth=0.8)
    ax3.set_ylim(-0.02, 1.02)
    ax3.set_ylabel("Width pct")
    ax3.legend(loc="upper left", fontsize=8)
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for label in ax3.get_xticklabels():
        label.set_rotation(45)
        label.set_ha("right")
    fig.subplots_adjust(left=0.055, right=0.94, top=0.93, bottom=0.11)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def write_index(
    out_dir: Path,
    summary: dict,
    yearly: pd.DataFrame,
    trades: pd.DataFrame,
    exit_mix: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    lines = [
        "# NQ CHOP20 Dynamic Daily Range Breakout Walkthrough",
        "",
        "Daily-bar diagnostic for close-confirmed breakouts from causal CHOP20 range boxes. This is not a broker-like StrategyPlugin replay yet.",
        "",
        "## Rules",
        "",
        "- Active range updates on every completed daily bar classified as `RANGING` or `COMPRESSED_RANGE`.",
        "- When flat, buy the daily close above the active range high or sell short the daily close below the active range low.",
        "- One campaign at a time; unlimited later attempts are allowed on the same active range until a newer range-like bar updates it.",
        "- Three units: 1 exits at `0.5R`, 1 exits at `1R`, and 1 exits at `4R`, where `R` is the active range width.",
        "- Any remaining units exit when a later daily close returns into/through the breakout side of the range.",
        f"- Diagnostic realism: `{args.slippage_ticks}` tick adverse slippage on close-entry/cancel/data-end exits, `${args.fee_per_unit:.2f}` per closed unit, limit targets at target price.",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Trades | {summary['trades']:,} |",
        f"| Unit exits | {summary['units']:,} |",
        f"| Net | {_fmt_money(summary['net_usd'])} |",
        f"| Closed DD | {_fmt_money(summary['closed_drawdown'])} |",
        f"| MTM stress DD | {_fmt_money(summary['mtm_drawdown'])} |",
        f"| Net / Stress | {_fmt_float(summary['net_stress'], 2)} |",
        f"| Win rate | {_fmt_float(summary['win_rate'] * 100.0, 1)}% |",
        f"| Profit factor | {_fmt_float(summary['profit_factor'], 2)} |",
        f"| Avg / median trade | {_fmt_money(summary['avg_trade'])} / {_fmt_money(summary['median_trade'])} |",
        f"| Best / worst trade | {_fmt_money(summary['best_trade'])} / {_fmt_money(summary['worst_trade'])} |",
        f"| Avg / median bars held | {_fmt_float(summary['avg_bars_held'], 1)} / {_fmt_float(summary['median_bars_held'], 1)} |",
        "",
        "![Equity](equity_curve.png)",
        "",
        "## Yearly",
        "",
        "| Year | Trades | Net | MTM DD | Win | PF |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in yearly.iterrows():
        lines.append(
            f"| {int(row['year'])} | {int(row['trades'])} | {_fmt_money(float(row['net_usd']))} | "
            f"{_fmt_money(float(row['mtm_drawdown']))} | {_fmt_float(float(row['win_rate']) * 100.0, 1)}% | "
            f"{_fmt_float(float(row['profit_factor']), 2)} |"
        )
    lines.extend(
        [
            "",
            "## Exit Mix",
            "",
            "| Exit reason | Units | Net |",
            "|---|---:|---:|",
        ]
    )
    for _, row in exit_mix.iterrows():
        lines.append(f"| {row['reason']} | {int(row['units'])} | {_fmt_money(float(row['net_usd']))} |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- [trades.csv](trades.csv)",
            "- [unit_exits.csv](unit_exits.csv)",
            "- [active_ranges.csv](active_ranges.csv)",
            "- [equity_curve.csv](equity_curve.csv)",
            "- [yearly_summary.csv](yearly_summary.csv)",
            "- [charts/](charts/)",
            "",
            "## Trade Charts",
            "",
            "| # | Entry | Dir | Exit | Net | Reason | Chart |",
            "|---:|---|---|---|---:|---|---|",
        ]
    )
    for _, row in trades.iterrows():
        chart = str(row.get("chart", ""))
        chart_link = f"[chart]({chart})" if chart else ""
        lines.append(
            f"| {int(row['trade_id'])} | {row['breakout_ts']} | {row['direction']} | {row['exit_ts']} | "
            f"{_fmt_money(float(row['net_usd']))} | {row['exit_reason']} | {chart_link} |"
        )
    lines.extend(
        [
            "",
            "## Causality Notes",
            "",
            "- The range state and active range high/low are known only after each completed daily candle.",
            "- The strategy only enters on a later daily close outside the active range.",
            "- Daily highs/lows are used to model resting target fills after entry; same-day target sequencing inside a daily bar is not tick-proven.",
            "- A production version should re-run this through 1m or tick data before promotion.",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCES["D"]["NQ"])
    p.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--max-charts", type=int, default=0, help="0 writes every trade chart")
    p.add_argument("--slippage-ticks", type=int, default=1)
    p.add_argument("--fee-per-unit", type=float, default=1.50)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out
    chart_dir = out_dir / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    params = DetectorParams()
    bars = load_bars(args.source, "D")
    regimes = add_range_metrics(bars, params)
    trades, exits, ranges, equity = simulate(
        regimes,
        slippage_ticks=int(args.slippage_ticks),
        fee_per_unit=float(args.fee_per_unit),
    )

    chart_limit = len(trades) if int(args.max_charts) <= 0 else min(int(args.max_charts), len(trades))
    if not trades.empty:
        for idx in range(chart_limit):
            row = trades.iloc[idx]
            fname = (
                f"{int(row['trade_id']):03d}_{row['breakout_ts']}_{row['direction']}_"
                f"range_{row['range_confirmed_ts']}_to_{row['exit_ts']}.png"
            )
            rel = Path("charts") / fname
            plot_trade_chart(regimes, row, exits, out_dir / rel)
            trades.loc[trades.index[idx], "chart"] = str(rel)

    plot_equity(equity, out_dir / "equity_curve.png")
    yearly = yearly_summary(trades, equity)
    exit_mix = (
        exits.groupby("reason", as_index=False)
        .agg(units=("net_usd", "size"), net_usd=("net_usd", "sum"))
        .sort_values("net_usd", ascending=False)
        if not exits.empty
        else pd.DataFrame(columns=["reason", "units", "net_usd"])
    )
    summary = summarize(trades, exits, equity)

    regimes.to_csv(out_dir / "daily_regimes.csv", index=False)
    ranges.to_csv(out_dir / "active_ranges.csv", index=False)
    trades.to_csv(out_dir / "trades.csv", index=False)
    exits.to_csv(out_dir / "unit_exits.csv", index=False)
    equity.to_csv(out_dir / "equity_curve.csv", index=False)
    yearly.to_csv(out_dir / "yearly_summary.csv", index=False)
    exit_mix.to_csv(out_dir / "exit_mix.csv", index=False)
    pd.DataFrame([summary]).to_csv(out_dir / "summary.csv", index=False)
    write_index(out_dir, summary, yearly, trades, exit_mix, args)

    print(f"WROTE {out_dir}")
    print(pd.DataFrame([summary]).to_string(index=False))


if __name__ == "__main__":
    main()
