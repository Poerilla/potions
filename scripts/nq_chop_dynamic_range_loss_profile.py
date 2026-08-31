#!/usr/bin/env python3
"""Loss profile and structure sweep for the NQ CHOP20 range walkthrough."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from chop_range_breakout_charts import DEFAULT_SOURCES, DetectorParams, ROOT, add_range_metrics, load_bars


DEFAULT_BASE = ROOT / "live" / "state" / "nq_chop20_dynamic_range_breakout_walkthrough"
DEFAULT_OUT = DEFAULT_BASE / "loss_profile"
POINT_VALUE = 20.0
TICK_SIZE = 0.25


@dataclass(frozen=True)
class Variant:
    name: str
    sides: str = "both"
    stop_mode: str = "close_back_inside"
    max_attempts_per_range: Optional[int] = None
    max_range_age_bars: Optional[int] = None
    max_breakout_gap_r: Optional[float] = None
    be_after_r: Optional[float] = None
    runner_r: float = 4.0


def _date_s(value) -> str:
    return pd.Timestamp(value).tz_localize(None).date().isoformat()


def _fmt_money(value: float) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"${value:,.0f}"


def _fmt_float(value: float, digits: int = 2) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"{value:,.{digits}f}"


def _entry_price(direction: str, close: float, slip_ticks: int) -> float:
    slip = slip_ticks * TICK_SIZE
    return float(close + slip if direction == "long" else close - slip)


def _exit_price(direction: str, price: float, slip_ticks: int) -> float:
    slip = slip_ticks * TICK_SIZE
    return float(price - slip if direction == "long" else price + slip)


def _points(direction: str, entry: float, exit_price: float) -> float:
    return float(exit_price - entry if direction == "long" else entry - exit_price)


def _target(direction: str, entry: float, width: float, r: float) -> float:
    return float(entry + width * r if direction == "long" else entry - width * r)


def _stop_price(trade: dict, variant: Variant) -> Optional[float]:
    if variant.stop_mode == "touch_broken_boundary":
        stop = trade["range_high"] if trade["direction"] == "long" else trade["range_low"]
    elif variant.stop_mode == "touch_25pct_inside":
        stop = (
            trade["range_high"] - 0.25 * trade["width"]
            if trade["direction"] == "long"
            else trade["range_low"] + 0.25 * trade["width"]
        )
    elif variant.stop_mode == "touch_50pct_inside":
        stop = (
            trade["range_high"] - 0.50 * trade["width"]
            if trade["direction"] == "long"
            else trade["range_low"] + 0.50 * trade["width"]
        )
    else:
        return None

    if variant.be_after_r is not None and trade["best_filled_r"] >= variant.be_after_r:
        if trade["direction"] == "long":
            stop = max(float(stop), float(trade["entry"]))
        else:
            stop = min(float(stop), float(trade["entry"]))
    return float(stop)


def _stop_hit(row: pd.Series, direction: str, stop: float) -> bool:
    if direction == "long":
        return float(row["low"]) <= stop
    return float(row["high"]) >= stop


def _target_hit(row: pd.Series, direction: str, price: float) -> bool:
    if direction == "long":
        return float(row["high"]) >= price
    return float(row["low"]) <= price


def _close_exit_hit(row: pd.Series, trade: dict, variant: Variant) -> bool:
    close = float(row["close"])
    if variant.stop_mode == "close_entry_fail":
        return close <= trade["entry"] if trade["direction"] == "long" else close >= trade["entry"]
    if variant.stop_mode == "close_back_inside":
        return close <= trade["range_high"] if trade["direction"] == "long" else close >= trade["range_low"]
    return False


def _close_trade(
    d: pd.DataFrame,
    trade: dict,
    unit_exits: List[dict],
    exit_idx: int,
) -> dict:
    exits = [e for e in unit_exits if e["trade_id"] == trade["trade_id"]]
    reasons = sorted({e["reason"] for e in exits})
    if reasons == ["tp_0_5r", "tp_1r", f"tp_{trade['runner_r']:g}r"]:
        exit_reason = "all_targets"
    elif any(r.startswith("stop_") for r in reasons):
        exit_reason = "stop_after_targets" if len(reasons) > 1 else reasons[-1]
    elif "range_close_cancel" in reasons and len(reasons) > 1:
        exit_reason = "partial_targets_then_range_cancel"
    else:
        exit_reason = ",".join(reasons)

    window = d.iloc[trade["entry_idx"] + 1 : exit_idx + 1]
    if window.empty:
        mfe = 0.0
        mae = 0.0
    elif trade["direction"] == "long":
        mfe = float(window["high"].max() - trade["entry"])
        mae = float(window["low"].min() - trade["entry"])
    else:
        mfe = float(trade["entry"] - window["low"].min())
        mae = float(trade["entry"] - window["high"].max())
    net = float(sum(e["net_usd"] for e in exits))
    return {
        "trade_id": trade["trade_id"],
        "direction": trade["direction"],
        "range_id": trade["range_id"],
        "attempt_number": trade["attempt_number"],
        "range_confirmed_ts": trade["range_confirmed_ts"],
        "entry_ts": trade["entry_ts"],
        "exit_ts": _date_s(d.iloc[exit_idx]["date"]),
        "range_age_bars": int(trade["entry_idx"] - trade["range_idx"]),
        "bars_held": int(exit_idx - trade["entry_idx"]),
        "entry": float(trade["entry"]),
        "range_high": float(trade["range_high"]),
        "range_low": float(trade["range_low"]),
        "range_width_r": float(trade["width"]),
        "breakout_gap_r": float(trade["breakout_gap_r"]),
        "mfe_r": float(mfe / trade["width"]) if trade["width"] else np.nan,
        "mae_r": float(mae / trade["width"]) if trade["width"] else np.nan,
        "exit_reason": exit_reason,
        "units": len(exits),
        "winning_units": int(sum(1 for e in exits if e["net_usd"] > 0)),
        "net_usd": net,
    }


def simulate_variant(d: pd.DataFrame, variant: Variant, slippage_ticks: int, fee_per_unit: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    active: Optional[dict] = None
    range_group_start_idx: Optional[int] = None
    range_group_id = 0
    range_id = 0
    trade_id = 0
    attempts_by_range: Dict[int, int] = {}
    open_trade: Optional[dict] = None
    trades: List[dict] = []
    unit_exits: List[dict] = []
    equity_rows: List[dict] = []
    realized = 0.0
    last_flatten_idx: Optional[int] = None

    target_rs: Sequence[float] = (0.5, 1.0, float(variant.runner_r))

    def add_exit(trade: dict, row: pd.Series, unit_number: int, exit_px: float, target_r: float, reason: str) -> None:
        nonlocal realized
        pts = _points(trade["direction"], trade["entry"], exit_px)
        net = pts * POINT_VALUE - fee_per_unit
        item = {
            "trade_id": trade["trade_id"],
            "unit_number": unit_number,
            "direction": trade["direction"],
            "entry_ts": trade["entry_ts"],
            "exit_ts": _date_s(row["date"]),
            "entry_price": trade["entry"],
            "exit_price": float(exit_px),
            "target_r": float(target_r),
            "reason": reason,
            "points": pts,
            "net_usd": net,
        }
        unit_exits.append(item)
        realized += net

    for i, row in d.iterrows():
        date_s = _date_s(row["date"])
        close = float(row["close"])
        closed_this_bar = False

        if open_trade is not None and int(i) > open_trade["entry_idx"]:
            stop = _stop_price(open_trade, variant)
            if stop is not None and open_trade["units_remaining"] > 0 and _stop_hit(row, open_trade["direction"], stop):
                px = _exit_price(open_trade["direction"], stop, slippage_ticks)
                while open_trade["units_remaining"] > 0:
                    unit_number = 4 - open_trade["units_remaining"]
                    add_exit(open_trade, row, unit_number, px, 0.0, f"stop_{variant.stop_mode}")
                    open_trade["units_remaining"] -= 1
            else:
                for r in target_rs:
                    label = f"tp_{r:g}r".replace(".", "_")
                    if label in open_trade["filled_targets"] or open_trade["units_remaining"] <= 0:
                        continue
                    target = _target(open_trade["direction"], open_trade["entry"], open_trade["width"], r)
                    if _target_hit(row, open_trade["direction"], target):
                        unit_number = 4 - open_trade["units_remaining"]
                        add_exit(open_trade, row, unit_number, target, r, label)
                        open_trade["units_remaining"] -= 1
                        open_trade["filled_targets"].add(label)
                        open_trade["best_filled_r"] = max(open_trade["best_filled_r"], float(r))

                if open_trade["units_remaining"] > 0 and _close_exit_hit(row, open_trade, variant):
                    px = _exit_price(open_trade["direction"], close, slippage_ticks)
                    reason = "entry_close_fail" if variant.stop_mode == "close_entry_fail" else "range_close_cancel"
                    while open_trade["units_remaining"] > 0:
                        unit_number = 4 - open_trade["units_remaining"]
                        add_exit(open_trade, row, unit_number, px, 0.0, reason)
                        open_trade["units_remaining"] -= 1

            if open_trade is not None and open_trade["units_remaining"] <= 0:
                trades.append(_close_trade(d, open_trade, unit_exits, int(i)))
                open_trade = None
                last_flatten_idx = int(i)
                closed_this_bar = True

        if open_trade is not None and int(i) == len(d) - 1:
            px = _exit_price(open_trade["direction"], close, slippage_ticks)
            while open_trade["units_remaining"] > 0:
                unit_number = 4 - open_trade["units_remaining"]
                add_exit(open_trade, row, unit_number, px, 0.0, "data_end")
                open_trade["units_remaining"] -= 1
            trades.append(_close_trade(d, open_trade, unit_exits, int(i)))
            open_trade = None
            last_flatten_idx = int(i)
            closed_this_bar = True

        if bool(row["is_range_like"]):
            if range_group_start_idx is None:
                range_group_id += 1
                range_group_start_idx = int(i)
            range_id += 1
            active = {
                "range_id": range_id,
                "range_group_id": range_group_id,
                "range_idx": int(i),
                "range_group_start_idx": range_group_start_idx,
                "range_start_ts": _date_s(d.iloc[range_group_start_idx]["date"]),
                "range_confirmed_ts": date_s,
                "range_high": float(row["range_high_20"]),
                "range_low": float(row["range_low_20"]),
                "width": float(row["range_20"]),
            }
        else:
            range_group_start_idx = None

        if open_trade is None and active is not None and int(i) > active["range_idx"] and not closed_this_bar and last_flatten_idx != int(i):
            range_age = int(i) - active["range_idx"]
            if variant.max_range_age_bars is not None and range_age > variant.max_range_age_bars:
                pass
            else:
                direction = ""
                if close > active["range_high"]:
                    direction = "long"
                elif close < active["range_low"]:
                    direction = "short"
                if direction and variant.sides != "both" and direction != variant.sides:
                    direction = ""
                if direction:
                    gap_r = (
                        (close - active["range_high"]) / active["width"]
                        if direction == "long"
                        else (active["range_low"] - close) / active["width"]
                    )
                    if variant.max_breakout_gap_r is not None and gap_r > variant.max_breakout_gap_r:
                        direction = ""
                if direction:
                    attempts = attempts_by_range.get(active["range_id"], 0) + 1
                    if variant.max_attempts_per_range is not None and attempts > variant.max_attempts_per_range:
                        direction = ""
                if direction:
                    attempts_by_range[active["range_id"]] = attempts
                    trade_id += 1
                    open_trade = {
                        **active,
                        "trade_id": trade_id,
                        "attempt_number": attempts,
                        "direction": direction,
                        "entry_idx": int(i),
                        "entry_ts": date_s,
                        "entry_close": close,
                        "entry": _entry_price(direction, close, slippage_ticks),
                        "breakout_gap_r": float(gap_r),
                        "units_remaining": 3,
                        "filled_targets": set(),
                        "best_filled_r": 0.0,
                        "runner_r": float(variant.runner_r),
                    }

        open_mtm = 0.0
        open_units = 0
        if open_trade is not None:
            open_units = open_trade["units_remaining"]
            open_mtm = _points(open_trade["direction"], open_trade["entry"], close) * POINT_VALUE * open_units
        equity_rows.append(
            {
                "date": date_s,
                "closed_equity": realized,
                "mtm_equity": realized + open_mtm,
                "open_units": open_units,
            }
        )

    equity = pd.DataFrame(equity_rows)
    if not equity.empty:
        equity["closed_drawdown"] = equity["closed_equity"] - equity["closed_equity"].cummax()
        equity["mtm_drawdown"] = equity["mtm_equity"] - equity["mtm_equity"].cummax()
    return pd.DataFrame(trades), pd.DataFrame(unit_exits), equity


def summarize_variant(name: str, trades: pd.DataFrame, exits: pd.DataFrame, equity: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "variant": name,
            "trades": 0,
            "units": 0,
            "net_usd": 0.0,
            "closed_drawdown": 0.0,
            "mtm_drawdown": 0.0,
            "net_stress": np.nan,
            "win_rate": np.nan,
            "profit_factor": np.nan,
        }
    gross_profit = float(exits.loc[exits["net_usd"] > 0, "net_usd"].sum())
    gross_loss = float(exits.loc[exits["net_usd"] < 0, "net_usd"].sum())
    closed_dd = float(equity["closed_drawdown"].min())
    mtm_dd = float(equity["mtm_drawdown"].min())
    net = float(trades["net_usd"].sum())
    return {
        "variant": name,
        "trades": int(len(trades)),
        "units": int(len(exits)),
        "net_usd": net,
        "closed_drawdown": closed_dd,
        "mtm_drawdown": mtm_dd,
        "net_stress": net / abs(mtm_dd) if mtm_dd < 0 else np.nan,
        "win_rate": float((trades["net_usd"] > 0).mean()),
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss < 0 else np.nan,
        "avg_trade": float(trades["net_usd"].mean()),
        "median_trade": float(trades["net_usd"].median()),
        "best_trade": float(trades["net_usd"].max()),
        "worst_trade": float(trades["net_usd"].min()),
        "long_net": float(trades.loc[trades["direction"] == "long", "net_usd"].sum()),
        "short_net": float(trades.loc[trades["direction"] == "short", "net_usd"].sum()),
    }


def add_loss_columns(trades: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    d = trades.copy()
    idx = {_date_s(row["date"]): int(i) for i, row in daily.iterrows()}
    d["entry_idx"] = d["breakout_ts"].map(idx)
    d["range_idx"] = d["range_confirmed_ts"].map(idx)
    d["range_age_bars"] = d["entry_idx"] - d["range_idx"]
    d["breakout_gap_r"] = np.where(
        d["direction"] == "long",
        (d["entry_close"] - d["range_high"]) / d["range_width_r"],
        (d["range_low"] - d["entry_close"]) / d["range_width_r"],
    )
    d["mfe_r"] = d["mfe_pts"] / d["range_width_r"]
    d["mae_r"] = d["mae_pts"] / d["range_width_r"]
    d["result"] = np.where(d["net_usd"] > 0, "winner", "loser")
    d["age_bin"] = pd.cut(
        d["range_age_bars"],
        bins=[-1, 5, 20, 60, 126, 252, 99999],
        labels=["0-5", "6-20", "21-60", "61-126", "127-252", "253+"],
    )
    d["gap_bin"] = pd.cut(
        d["breakout_gap_r"],
        bins=[-np.inf, 0.1, 0.25, 0.5, 1.0, np.inf],
        labels=["<=0.10R", "0.10-0.25R", "0.25-0.50R", "0.50-1.00R", ">1.00R"],
    )
    d["attempt_bin"] = pd.cut(
        d["attempt_number"],
        bins=[0, 1, 2, 3, 999],
        labels=["1", "2", "3", "4+"],
    )
    d["width_quartile"] = pd.qcut(d["range_width_r"], 4, duplicates="drop")
    return d


def grouped_profile(df: pd.DataFrame, key: str) -> pd.DataFrame:
    return (
        df.groupby(key, observed=False)
        .agg(
            trades=("trade_id", "size"),
            losers=("net_usd", lambda s: int((s < 0).sum())),
            net_usd=("net_usd", "sum"),
            avg_trade=("net_usd", "mean"),
            win_rate=("net_usd", lambda s: float((s > 0).mean())),
            worst_trade=("net_usd", "min"),
            median_age_bars=("range_age_bars", "median"),
            median_gap_r=("breakout_gap_r", "median"),
            median_mae_r=("mae_r", "median"),
        )
        .reset_index()
    )


def write_md(
    out_dir: Path,
    base_summary: dict,
    profiles: Dict[str, pd.DataFrame],
    sweep: pd.DataFrame,
    worst: pd.DataFrame,
    loss_stats: dict,
) -> None:
    best = sweep.sort_values(["net_stress", "net_usd"], ascending=[False, False]).head(8)

    def add_profile_table(lines: List[str], title: str, df: pd.DataFrame, key_col: str) -> None:
        lines.extend(
            [
                f"## {title}",
                "",
                "| Bucket | Trades | Losers | Net | Win | Worst | Median Age | Median Gap | Median MAE |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in df.iterrows():
            lines.append(
                f"| {row[key_col]} | {int(row['trades'])} | {int(row['losers'])} | "
                f"{_fmt_money(float(row['net_usd']))} | {_fmt_float(float(row['win_rate']) * 100.0, 1)}% | "
                f"{_fmt_money(float(row['worst_trade']))} | {_fmt_float(float(row['median_age_bars']), 1)} | "
                f"{_fmt_float(float(row['median_gap_r']), 2)}R | {_fmt_float(float(row['median_mae_r']), 2)}R |"
            )
        lines.append("")

    lines = [
        "# NQ CHOP20 Dynamic Range Loss Profile",
        "",
        "Loss anatomy for the daily close-confirmed CHOP20 range breakout walkthrough.",
        "",
        "## Base Loss Profile",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Base trades | {int(base_summary['trades']):,} |",
        f"| Base net | {_fmt_money(base_summary['net_usd'])} |",
        f"| Base MTM stress DD | {_fmt_money(base_summary['mtm_drawdown'])} |",
        f"| Base Net / Stress | {_fmt_float(base_summary['net_stress'], 2)} |",
        f"| Losing trades | {loss_stats['losing_trades']:,} |",
        f"| Losing-trade net | {_fmt_money(loss_stats['losing_trade_net'])} |",
        f"| Winning-trade net | {_fmt_money(loss_stats['winning_trade_net'])} |",
        f"| Losers that first moved at least 0.5R favorably | {loss_stats['losers_mfe_ge_0_5r']:,} |",
        f"| Losers that first moved at least 1R favorably | {loss_stats['losers_mfe_ge_1r']:,} |",
        "",
        "## What The Losses Say",
        "",
        "- The raw rule is not symmetric on NQ: long breakouts carried the book, while short breakouts were the major drag.",
        "- The largest loss bucket is not failed targets; it is the close-back-inside exit waiting too long before admitting the breakout failed.",
        "- A meaningful number of losing campaigns had useful favorable movement first, so stop-to-breakeven after the first partial is worth testing on intraday data.",
        "- Some entries fire from stale range references long after the range was formed. That can create huge breakout gaps and poor invalidation geometry.",
        "",
    ]
    add_profile_table(lines, "By Direction", profiles["direction"], "direction")
    add_profile_table(lines, "By Exit Reason", profiles["exit_reason"], "exit_reason")
    add_profile_table(lines, "By Range Age", profiles["range_age"], "age_bin")
    add_profile_table(lines, "By Breakout Gap", profiles["breakout_gap"], "gap_bin")
    lines.extend(
        [
            "## Structure Sweep",
        "",
        "| Variant | Trades | Net | MTM DD | Net/Stress | Win | PF | Worst | Long Net | Short Net |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in best.iterrows():
        lines.append(
            f"| `{row['variant']}` | {int(row['trades'])} | {_fmt_money(float(row['net_usd']))} | "
            f"{_fmt_money(float(row['mtm_drawdown']))} | {_fmt_float(float(row['net_stress']), 2)} | "
            f"{_fmt_float(float(row['win_rate']) * 100.0, 1)}% | {_fmt_float(float(row['profit_factor']), 2)} | "
            f"{_fmt_money(float(row['worst_trade']))} | {_fmt_money(float(row['long_net']))} | {_fmt_money(float(row['short_net']))} |"
        )
    lines.extend(
        [
            "",
            "## More Sensible Next Structures",
            "",
            "1. Treat the breakout boundary as a real stop zone, not only a close-cancel line. The daily diagnostic strongly dislikes waiting for a daily close after the breakout has already failed.",
            "2. Separate long and short logic. The long side deserves further testing; the short side needs an additional regime filter or a different exit shape before it should be trusted.",
            "3. Add a freshness rule. Very old ranges can still be visually meaningful, but the current unlimited-memory version creates stale geometry and oversized failed-breakout losses.",
            "4. Test stop-to-breakeven after the 0.5R partial on 1m/tick data. It addresses the exact loser class where the trade worked briefly, then reversed.",
            "5. Prefer the next serious pass on 4h/1h or 1m bars. Daily OHLC cannot prove target/stop sequencing, especially when a boundary stop and a target are both touched in the same daily candle.",
            "",
            "## Worst Losses",
            "",
            "| Trade | Entry | Dir | Exit | Net | Age | Gap | MFE | MAE | Reason |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for _, row in worst.head(10).iterrows():
        lines.append(
            f"| {int(row['trade_id'])} | {row['breakout_ts']} | {row['direction']} | {row['exit_ts']} | "
            f"{_fmt_money(float(row['net_usd']))} | {int(row['range_age_bars'])} | "
            f"{_fmt_float(float(row['breakout_gap_r']), 2)}R | {_fmt_float(float(row['mfe_r']), 2)}R | "
            f"{_fmt_float(float(row['mae_r']), 2)}R | {row['exit_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- [loss_trades.csv](loss_trades.csv)",
            "- [loss_by_direction.csv](loss_by_direction.csv)",
            "- [loss_by_exit_reason.csv](loss_by_exit_reason.csv)",
            "- [loss_by_attempt.csv](loss_by_attempt.csv)",
            "- [loss_by_range_age.csv](loss_by_range_age.csv)",
            "- [loss_by_breakout_gap.csv](loss_by_breakout_gap.csv)",
            "- [loss_by_width_quartile.csv](loss_by_width_quartile.csv)",
            "- [structure_sweep.csv](structure_sweep.csv)",
            "- [worst_losses.csv](worst_losses.csv)",
            "",
            "## Caution",
            "",
            "The sweep is still daily-resolution. Variants with touch stops are directionally useful because they show whether tighter invalidation helps, but they require 1m/tick replay before ranking.",
        ]
    )
    (out_dir / "LOSS_PROFILE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=DEFAULT_BASE)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCES["D"]["NQ"])
    p.add_argument("--slippage-ticks", type=int, default=1)
    p.add_argument("--fee-per-unit", type=float, default=1.50)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    base_trades = pd.read_csv(args.base / "trades.csv")
    base_summary = pd.read_csv(args.base / "summary.csv").iloc[0].to_dict()
    bars = load_bars(args.source, "D")
    daily = add_range_metrics(bars, DetectorParams())

    profiled = add_loss_columns(base_trades, daily)
    losses = profiled[profiled["net_usd"] < 0].copy()
    worst = profiled.sort_values("net_usd").head(20)
    profiles = {
        "direction": grouped_profile(profiled, "direction"),
        "exit_reason": grouped_profile(profiled, "exit_reason"),
        "attempt": grouped_profile(profiled, "attempt_bin"),
        "range_age": grouped_profile(profiled, "age_bin"),
        "breakout_gap": grouped_profile(profiled, "gap_bin"),
        "width_quartile": grouped_profile(profiled, "width_quartile"),
    }

    variants = [
        Variant("base_close_back_inside"),
        Variant("base_long_only", sides="long"),
        Variant("base_short_only", sides="short"),
        Variant("base_one_attempt_per_range", max_attempts_per_range=1),
        Variant("base_max_age_60", max_range_age_bars=60),
        Variant("base_max_age_60_long_only", sides="long", max_range_age_bars=60),
        Variant("base_max_age_60_short_only", sides="short", max_range_age_bars=60),
        Variant("base_max_age_126", max_range_age_bars=126),
        Variant("base_max_age_252", max_range_age_bars=252),
        Variant("base_gap_lte_0_5r", max_breakout_gap_r=0.5),
        Variant("base_gap_lte_1r", max_breakout_gap_r=1.0),
        Variant("close_entry_fail", stop_mode="close_entry_fail"),
        Variant("close_entry_fail_long_only", sides="long", stop_mode="close_entry_fail"),
        Variant("close_entry_fail_short_only", sides="short", stop_mode="close_entry_fail"),
        Variant("touch_broken_boundary_stop", stop_mode="touch_broken_boundary"),
        Variant("touch_broken_boundary_stop_be_after_0_5r", stop_mode="touch_broken_boundary", be_after_r=0.5),
        Variant("touch_25pct_inside_stop", stop_mode="touch_25pct_inside"),
        Variant("touch_25pct_inside_stop_be_after_0_5r", stop_mode="touch_25pct_inside", be_after_r=0.5),
        Variant("touch_50pct_inside_stop", stop_mode="touch_50pct_inside"),
        Variant("touch_broken_boundary_long_only", sides="long", stop_mode="touch_broken_boundary"),
        Variant("touch_broken_boundary_short_only", sides="short", stop_mode="touch_broken_boundary"),
        Variant("touch_broken_boundary_max_age_126", stop_mode="touch_broken_boundary", max_range_age_bars=126),
        Variant("touch_broken_boundary_max_age_60", stop_mode="touch_broken_boundary", max_range_age_bars=60),
        Variant(
            "touch_broken_boundary_max_age_60_long_only",
            sides="long",
            stop_mode="touch_broken_boundary",
            max_range_age_bars=60,
        ),
        Variant("touch_broken_boundary_gap_lte_0_5r", stop_mode="touch_broken_boundary", max_breakout_gap_r=0.5),
        Variant("touch_broken_boundary_runner_2r", stop_mode="touch_broken_boundary", runner_r=2.0),
        Variant(
            "touch_broken_boundary_runner_2r_max_age_60",
            stop_mode="touch_broken_boundary",
            max_range_age_bars=60,
            runner_r=2.0,
        ),
        Variant("touch_broken_boundary_runner_3r", stop_mode="touch_broken_boundary", runner_r=3.0),
    ]
    sweep_rows = []
    for variant in variants:
        trades, exits, equity = simulate_variant(daily, variant, args.slippage_ticks, args.fee_per_unit)
        sweep_rows.append(summarize_variant(variant.name, trades, exits, equity))
    sweep = pd.DataFrame(sweep_rows).sort_values(["net_stress", "net_usd"], ascending=[False, False])

    loss_stats = {
        "losing_trades": int(len(losses)),
        "losing_trade_net": float(losses["net_usd"].sum()),
        "winning_trade_net": float(profiled.loc[profiled["net_usd"] > 0, "net_usd"].sum()),
        "losers_mfe_ge_0_5r": int((losses["mfe_r"] >= 0.5).sum()),
        "losers_mfe_ge_1r": int((losses["mfe_r"] >= 1.0).sum()),
    }

    profiled.to_csv(out_dir / "loss_trades.csv", index=False)
    losses.to_csv(out_dir / "losers_only.csv", index=False)
    worst.to_csv(out_dir / "worst_losses.csv", index=False)
    for name, df in profiles.items():
        df.to_csv(out_dir / f"loss_by_{name}.csv", index=False)
    sweep.to_csv(out_dir / "structure_sweep.csv", index=False)
    write_md(out_dir, base_summary, profiles, sweep, worst, loss_stats)
    print(f"WROTE {out_dir}")
    print(sweep.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
