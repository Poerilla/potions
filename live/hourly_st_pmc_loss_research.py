from __future__ import annotations

import argparse
import csv
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import (
    concat_all_1m,
    load_1m_by_ny_date_any,
    load_prev_month_close_map,
    resample_hourly,
)


REPO = Path(__file__).resolve().parents[1]
POINT_VALUE = POINT_VALUES["YM"]
FEE_PER_UNIT = 1.50
SLIPPAGE_TICKS = 1.0
TICK_SIZE = 1.0


@dataclass(frozen=True)
class PendingEntry:
    side: str
    limit_price: float
    stop_pts: float
    tp1_pts: float
    tp1_qty: int
    runner_qty: int
    runner_tp_pts: Optional[float]
    live_after_ts: pd.Timestamp
    signal_ts: pd.Timestamp


@dataclass(frozen=True)
class OpenUnit:
    variant: str
    trade_id: str
    unit_id: str
    side: str
    entry_ts: pd.Timestamp
    entry_price: float
    stop_price: float
    target_price: Optional[float]
    bucket: str
    entry_row_pos: int
    tp1_reached: bool = False


@dataclass(frozen=True)
class UnitExit:
    variant: str
    trade_id: str
    unit_id: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    exit_reason: str
    bucket: str
    points: float
    usd: float
    entry_row_pos: int


@dataclass(frozen=True)
class VariantConfig:
    name: str
    stop_pts: float = 50.0
    tp1_pts: float = 150.0
    tp1_qty: int = 1
    runner_qty: int = 0
    runner_tp_pts: Optional[float] = None
    runner_stop_to_be_after_tp1: bool = False
    ma_filter: str = "none"  # none, directional_current, directional_prior, bull_prior_only, bear_prior_only
    close_against_entry_exit: bool = False
    st_flip_exit: bool = False
    pmc_cross_exit: bool = False
    notes: str = ""

    @property
    def entry_qty(self) -> int:
        return int(self.tp1_qty) + int(self.runner_qty)


@dataclass(frozen=True)
class SimResult:
    config: VariantConfig
    exits: List[UnitExit]
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int
    final_open_units: int


def _ts_after(left: pd.Timestamp, right: pd.Timestamp) -> bool:
    return pd.Timestamp(left) > pd.Timestamp(right)


def load_hourly(dbn: Path, daily_path: Path, atr_len: int, atr_mult: float) -> pd.DataFrame:
    print("Loading YM 1m source...", flush=True)
    gby = load_1m_by_ny_date_any(dbn.resolve(), "ym")
    print("Resampling to hourly and computing Supertrend/MA context...", flush=True)
    hourly = compute_supertrend(
        resample_hourly(concat_all_1m(gby)),
        atr_len=atr_len,
        multiplier=atr_mult,
    ).copy()
    hourly = hourly.sort_index()
    hourly["ma50"] = pd.to_numeric(hourly["close"], errors="coerce").rolling(50).mean()
    hourly["ma150"] = pd.to_numeric(hourly["close"], errors="coerce").rolling(150).mean()
    hourly["ma50_prior"] = hourly["ma50"].shift(1)
    hourly["ma150_prior"] = hourly["ma150"].shift(1)
    hourly["ma_regime"] = np.where(
        hourly["ma50"] > hourly["ma150"],
        "bull",
        np.where(hourly["ma50"] < hourly["ma150"], "bear", "unknown"),
    )
    hourly["ma_regime_prior"] = np.where(
        hourly["ma50_prior"] > hourly["ma150_prior"],
        "bull",
        np.where(hourly["ma50_prior"] < hourly["ma150_prior"], "bear", "unknown"),
    )
    hourly["ma_spread"] = hourly["ma50"] - hourly["ma150"]
    hourly["ma_spread_prior"] = hourly["ma50_prior"] - hourly["ma150_prior"]

    trend = pd.to_numeric(hourly["supertrend_trend"], errors="coerce")
    flips = trend.ne(trend.shift(1)).fillna(False).astype(int)
    hourly["bars_since_st_flip"] = hourly.groupby(flips.cumsum()).cumcount()
    hourly["st_flip"] = flips.astype(bool)

    pmc_map = load_prev_month_close_map(daily_path)
    hourly["prev_month_close"] = [
        pmc_map.get((int(ts.year), int(ts.month)), np.nan) for ts in hourly.index
    ]
    hourly["pmc_side"] = np.where(
        hourly["close"] > hourly["prev_month_close"],
        "above",
        np.where(hourly["close"] < hourly["prev_month_close"], "below", "at"),
    )
    hourly["hour"] = [int(ts.hour) for ts in hourly.index]
    hourly["day_of_week"] = [int(ts.dayofweek) for ts in hourly.index]
    hourly["month"] = [int(ts.month) for ts in hourly.index]
    hourly["year"] = [int(ts.year) for ts in hourly.index]
    hourly["rth"] = [
        bool(pd.Timestamp("09:30").time() <= ts.time() < pd.Timestamp("16:00").time())
        for ts in hourly.index
    ]
    return hourly


def variants() -> List[VariantConfig]:
    return [
        VariantConfig("base_1x_50sl_150tp", notes="Current one-unit 50/150 replay rule in fast broker-like simulator."),
        VariantConfig(
            "ma_directional_current",
            ma_filter="directional_current",
            notes="Long only when current hourly MA50>MA150; short only when MA50<MA150.",
        ),
        VariantConfig(
            "ma_directional_prior",
            ma_filter="directional_prior",
            notes="Long only when prior completed hourly MA50>MA150; short only when prior MA50<MA150.",
        ),
        VariantConfig(
            "ma_bull_prior_only",
            ma_filter="bull_prior_only",
            notes="V2B-style prior MA50>MA150 on/off gate; keeps both ST/PMC long and short signals.",
        ),
        VariantConfig(
            "ma_bear_prior_only",
            ma_filter="bear_prior_only",
            notes="Inverse prior MA50<MA150 gate; useful to see whether losses cluster in bearish regimes.",
        ),
        VariantConfig(
            "close_against_entry_next_open",
            close_against_entry_exit=True,
            notes="If an hourly close is adverse to entry, flatten next bar open with market slippage.",
        ),
        VariantConfig(
            "st_flip_exit_next_open",
            st_flip_exit=True,
            notes="If hourly Supertrend flips against the position, flatten next bar open.",
        ),
        VariantConfig(
            "pmc_cross_exit_next_open",
            pmc_cross_exit=True,
            notes="If close crosses back through prior month close against the position, flatten next bar open.",
        ),
        VariantConfig(
            "ma_directional_prior_close_against",
            ma_filter="directional_prior",
            close_against_entry_exit=True,
            notes="Directional prior MA filter plus adverse-close flatten.",
        ),
        VariantConfig("sl40_tp120_3r", stop_pts=40.0, tp1_pts=120.0, notes="Tighter 40 point stop, 3R target."),
        VariantConfig("sl40_tp150_fixed", stop_pts=40.0, tp1_pts=150.0, notes="Tighter 40 point stop, original 150 target."),
        VariantConfig("sl35_tp105_3r", stop_pts=35.0, tp1_pts=105.0, notes="Tighter 35 point stop, 3R target."),
        VariantConfig("sl35_tp150_fixed", stop_pts=35.0, tp1_pts=150.0, notes="Tighter 35 point stop, original 150 target."),
        VariantConfig("sl25_tp75_3r", stop_pts=25.0, tp1_pts=75.0, notes="Very tight 25 point stop, 3R target."),
        VariantConfig("sl25_tp150_fixed", stop_pts=25.0, tp1_pts=150.0, notes="Very tight 25 point stop, original 150 target."),
        VariantConfig(
            "scaleout2_tp3r_runner6r",
            stop_pts=50.0,
            tp1_pts=150.0,
            tp1_qty=1,
            runner_qty=1,
            runner_tp_pts=300.0,
            runner_stop_to_be_after_tp1=True,
            notes="Enter 2: one off at 3R, runner target 6R, runner stop moves to entry after TP1.",
        ),
        VariantConfig(
            "scaleout2_tp3r_runner6r_ma_directional_prior",
            stop_pts=50.0,
            tp1_pts=150.0,
            tp1_qty=1,
            runner_qty=1,
            runner_tp_pts=300.0,
            runner_stop_to_be_after_tp1=True,
            ma_filter="directional_prior",
            notes="Scaleout 2 with prior completed hourly MA direction filter.",
        ),
        VariantConfig(
            "scaleout2_tp3r_runner6r_close_against",
            stop_pts=50.0,
            tp1_pts=150.0,
            tp1_qty=1,
            runner_qty=1,
            runner_tp_pts=300.0,
            runner_stop_to_be_after_tp1=True,
            close_against_entry_exit=True,
            notes="Scaleout 2 with adverse-close flatten.",
        ),
    ]


def desired_entry(row: pd.Series, cfg: VariantConfig) -> Optional[Tuple[str, float]]:
    st = row.get("supertrend")
    trend = row.get("supertrend_trend")
    pmc = row.get("prev_month_close")
    close = row.get("close")
    if not np.isfinite(st) or not np.isfinite(pmc) or pd.isna(trend):
        return None
    side: Optional[str] = None
    if float(close) > float(pmc) and int(trend) == 1:
        side = "long"
    elif float(close) < float(pmc) and int(trend) == -1:
        side = "short"
    if side is None:
        return None
    if not _ma_filter_allows(row, cfg.ma_filter, side):
        return None
    return side, float(st)


def _ma_filter_allows(row: pd.Series, mode: str, side: str) -> bool:
    if mode == "none":
        return True
    if mode == "directional_current":
        regime = str(row.get("ma_regime") or "unknown")
        return (side == "long" and regime == "bull") or (side == "short" and regime == "bear")
    if mode == "directional_prior":
        regime = str(row.get("ma_regime_prior") or "unknown")
        return (side == "long" and regime == "bull") or (side == "short" and regime == "bear")
    if mode == "bull_prior_only":
        return str(row.get("ma_regime_prior") or "unknown") == "bull"
    if mode == "bear_prior_only":
        return str(row.get("ma_regime_prior") or "unknown") == "bear"
    raise ValueError("Unknown MA filter: %s" % mode)


def simulate_variant(hourly: pd.DataFrame, cfg: VariantConfig) -> SimResult:
    rows = list(hourly.itertuples(index=True, name="Bar"))
    pending: Optional[PendingEntry] = None
    open_units: List[OpenUnit] = []
    pending_market_exit: Optional[str] = None
    exits: List[UnitExit] = []
    trade_seq = 0
    unit_seq = 0
    realized_usd = 0.0
    peak_close_usd = 0.0
    closed_dd_usd = 0.0
    intrabar_dd_usd = 0.0
    max_open_units = 0

    for pos, row in enumerate(rows):
        ts = pd.Timestamp(row.Index)
        o = float(row.open)
        h = float(row.high)
        l = float(row.low)
        c = float(row.close)

        if open_units and pending_market_exit:
            new_exits = _exit_all_market(open_units, row, pending_market_exit, cfg.name)
            exits.extend(new_exits)
            realized_usd += sum(item.usd for item in new_exits)
            open_units = []
            pending_market_exit = None
            pending = None

        if open_units:
            open_units, new_exits, tp1_hit = _process_brackets(open_units, row, cfg)
            if new_exits:
                exits.extend(new_exits)
                realized_usd += sum(item.usd for item in new_exits)
            if cfg.runner_stop_to_be_after_tp1 and tp1_hit and open_units:
                open_units = [
                    replace(unit, stop_price=unit.entry_price, tp1_reached=True)
                    if unit.bucket == "runner"
                    else unit
                    for unit in open_units
                ]

        if pending is not None and not open_units and _ts_after(ts, pending.live_after_ts):
            if _entry_touched(pending.side, pending.limit_price, h, l):
                trade_seq += 1
                trade_id = "%s_t%d" % (cfg.name, trade_seq)
                entry_price = pending.limit_price
                open_units = []
                for _ in range(pending.tp1_qty):
                    unit_seq += 1
                    open_units.append(
                        _make_unit(
                            cfg.name,
                            trade_id,
                            unit_seq,
                            pending.side,
                            ts,
                            entry_price,
                            pending.stop_pts,
                            pending.tp1_pts,
                            "tp1",
                            pos,
                        )
                    )
                for _ in range(pending.runner_qty):
                    unit_seq += 1
                    if pending.runner_tp_pts is None:
                        target_pts = pending.tp1_pts
                    else:
                        target_pts = pending.runner_tp_pts
                    open_units.append(
                        _make_unit(
                            cfg.name,
                            trade_id,
                            unit_seq,
                            pending.side,
                            ts,
                            entry_price,
                            pending.stop_pts,
                            target_pts,
                            "runner",
                            pos,
                        )
                    )
                pending = None
                open_units, new_exits, tp1_hit = _process_brackets(open_units, row, cfg)
                if new_exits:
                    exits.extend(new_exits)
                    realized_usd += sum(item.usd for item in new_exits)
                if cfg.runner_stop_to_be_after_tp1 and tp1_hit and open_units:
                    open_units = [
                        replace(unit, stop_price=unit.entry_price, tp1_reached=True)
                        if unit.bucket == "runner"
                        else unit
                        for unit in open_units
                    ]

        max_open_units = max(max_open_units, len(open_units))
        close_equity = realized_usd + sum(_open_unit_pnl_usd(unit, c) for unit in open_units)
        stress_equity = realized_usd + sum(_open_unit_stress_usd(unit, h, l) for unit in open_units)
        peak_close_usd = max(peak_close_usd, close_equity)
        closed_dd_usd = min(closed_dd_usd, close_equity - peak_close_usd)
        intrabar_dd_usd = min(intrabar_dd_usd, stress_equity - peak_close_usd)

        if open_units:
            pending_market_exit = _exit_signal(open_units, row, cfg)
            continue

        # Flat at the end of the completed bar: strategy can refresh/cancel the
        # resting entry for the next hour, but this new order cannot fill on the
        # same confirmation bar.
        desired = desired_entry(pd.Series(row._asdict()), cfg)
        if desired is None:
            pending = None
            continue
        side, limit_price = desired
        pending = PendingEntry(
            side=side,
            limit_price=limit_price,
            stop_pts=cfg.stop_pts,
            tp1_pts=cfg.tp1_pts,
            tp1_qty=cfg.tp1_qty,
            runner_qty=cfg.runner_qty,
            runner_tp_pts=cfg.runner_tp_pts,
            live_after_ts=ts,
            signal_ts=ts,
        )

    if open_units:
        final_row = rows[-1]
        new_exits = _exit_all_close(open_units, final_row, "open_mark", cfg.name)
        exits.extend(new_exits)
        realized_usd += sum(item.usd for item in new_exits)
        open_units = []

    return SimResult(
        config=cfg,
        exits=exits,
        closed_dd_usd=closed_dd_usd,
        intrabar_stress_dd_usd=intrabar_dd_usd,
        max_open_units=max_open_units,
        final_open_units=len(open_units),
    )


def _make_unit(
    variant: str,
    trade_id: str,
    unit_seq: int,
    side: str,
    ts: pd.Timestamp,
    entry_price: float,
    stop_pts: float,
    target_pts: float,
    bucket: str,
    entry_row_pos: int,
) -> OpenUnit:
    if side == "long":
        stop = entry_price - stop_pts
        target = entry_price + target_pts
    else:
        stop = entry_price + stop_pts
        target = entry_price - target_pts
    return OpenUnit(
        variant=variant,
        trade_id=trade_id,
        unit_id=str(unit_seq),
        side=side,
        entry_ts=ts,
        entry_price=entry_price,
        stop_price=stop,
        target_price=target,
        bucket=bucket,
        entry_row_pos=entry_row_pos,
    )


def _entry_touched(side: str, limit: float, high: float, low: float) -> bool:
    return low <= limit if side == "long" else high >= limit


def _process_brackets(
    units: List[OpenUnit],
    row,
    cfg: VariantConfig,
) -> Tuple[List[OpenUnit], List[UnitExit], bool]:
    ts = pd.Timestamp(row.Index)
    o, h, l = float(row.open), float(row.high), float(row.low)
    exits: List[UnitExit] = []
    survivors: List[OpenUnit] = []
    tp1_hit = False

    # Stops first, matching PaperBroker priority under same-bar ambiguity.
    for unit in units:
        stop_px = _stop_fill_price(unit.side, unit.stop_price, o, h, l)
        if stop_px is not None:
            exits.append(_unit_exit(unit, ts, stop_px, "stop"))
        else:
            survivors.append(unit)

    still_open: List[OpenUnit] = []
    for unit in survivors:
        target = unit.target_price
        target_hit = False
        if target is not None:
            target_hit = (unit.side == "long" and h >= target) or (unit.side == "short" and l <= target)
        if target_hit:
            tp1_hit = tp1_hit or unit.bucket == "tp1"
            exits.append(_unit_exit(unit, ts, float(target), "target" if unit.bucket == "tp1" else "runner_target"))
        else:
            still_open.append(unit)

    return still_open, exits, tp1_hit


def _stop_fill_price(side: str, stop: float, open_: float, high: float, low: float) -> Optional[float]:
    if side == "long" and low <= stop:
        base = min(stop, open_)
        return base - SLIPPAGE_TICKS * TICK_SIZE
    if side == "short" and high >= stop:
        base = max(stop, open_)
        return base + SLIPPAGE_TICKS * TICK_SIZE
    return None


def _exit_signal(units: Sequence[OpenUnit], row, cfg: VariantConfig) -> Optional[str]:
    if not units:
        return None
    unit = units[0]
    close = float(row.close)
    trend = int(row.supertrend_trend) if not pd.isna(row.supertrend_trend) else 0
    pmc = float(row.prev_month_close) if np.isfinite(row.prev_month_close) else math.nan
    if cfg.close_against_entry_exit:
        if unit.side == "long" and close < unit.entry_price:
            return "close_against_entry"
        if unit.side == "short" and close > unit.entry_price:
            return "close_against_entry"
    if cfg.st_flip_exit:
        if unit.side == "long" and trend == -1:
            return "st_flip_against"
        if unit.side == "short" and trend == 1:
            return "st_flip_against"
    if cfg.pmc_cross_exit and np.isfinite(pmc):
        if unit.side == "long" and close < pmc:
            return "pmc_cross_against"
        if unit.side == "short" and close > pmc:
            return "pmc_cross_against"
    return None


def _exit_all_market(units: Sequence[OpenUnit], row, reason: str, variant: str) -> List[UnitExit]:
    ts = pd.Timestamp(row.Index)
    out: List[UnitExit] = []
    for unit in units:
        if unit.side == "long":
            price = float(row.open) - SLIPPAGE_TICKS * TICK_SIZE
        else:
            price = float(row.open) + SLIPPAGE_TICKS * TICK_SIZE
        out.append(_unit_exit(unit, ts, price, reason))
    return out


def _exit_all_close(units: Sequence[OpenUnit], row, reason: str, variant: str) -> List[UnitExit]:
    ts = pd.Timestamp(row.Index)
    return [_unit_exit(unit, ts, float(row.close), reason) for unit in units]


def _unit_exit(unit: OpenUnit, exit_ts: pd.Timestamp, exit_price: float, reason: str) -> UnitExit:
    points = (exit_price - unit.entry_price) if unit.side == "long" else (unit.entry_price - exit_price)
    usd = points * POINT_VALUE - FEE_PER_UNIT
    return UnitExit(
        variant=unit.variant,
        trade_id=unit.trade_id,
        unit_id=unit.unit_id,
        side=unit.side,
        entry_ts=unit.entry_ts,
        exit_ts=exit_ts,
        entry_price=unit.entry_price,
        exit_price=exit_price,
        exit_reason=reason,
        bucket=unit.bucket,
        points=points,
        usd=usd,
        entry_row_pos=unit.entry_row_pos,
    )


def _open_unit_pnl_usd(unit: OpenUnit, close: float) -> float:
    points = (close - unit.entry_price) if unit.side == "long" else (unit.entry_price - close)
    return points * POINT_VALUE


def _open_unit_stress_usd(unit: OpenUnit, high: float, low: float) -> float:
    points = (low - unit.entry_price) if unit.side == "long" else (unit.entry_price - high)
    return points * POINT_VALUE


def summarize_exits(result: SimResult) -> Dict[str, object]:
    exits = result.exits
    trades = len({item.trade_id for item in exits})
    wins = [item for item in exits if item.usd > 0]
    losses = [item for item in exits if item.usd < 0]
    gross_win = sum(item.usd for item in wins)
    gross_loss = abs(sum(item.usd for item in losses))
    net = sum(item.usd for item in exits)
    return {
        "variant": result.config.name,
        "units": len(exits),
        "trades": trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": 100.0 * len(wins) / len(exits) if exits else 0.0,
        "net_usd": net,
        "gross_win_usd": gross_win,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_win / gross_loss if gross_loss else float("inf"),
        "closed_dd_usd": result.closed_dd_usd,
        "intrabar_stress_dd_usd": result.intrabar_stress_dd_usd,
        "net_over_stress": net / abs(result.intrabar_stress_dd_usd) if result.intrabar_stress_dd_usd else 0.0,
        "avg_win_usd": gross_win / len(wins) if wins else 0.0,
        "avg_loss_usd": -gross_loss / len(losses) if losses else 0.0,
        "max_open_units": result.max_open_units,
        "final_open_units": result.final_open_units,
        "config_notes": result.config.notes,
    }


def exits_to_frame(exits: Iterable[UnitExit], hourly: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for item in exits:
        entry_row = hourly.iloc[item.entry_row_pos]
        exit_idx = hourly.index.get_indexer([item.exit_ts], method="nearest")[0]
        exit_row = hourly.iloc[exit_idx] if exit_idx >= 0 else entry_row
        ma_regime = str(entry_row.get("ma_regime") or "unknown")
        ma_prior = str(entry_row.get("ma_regime_prior") or "unknown")
        rows.append(
            {
                "variant": item.variant,
                "trade_id": item.trade_id,
                "unit_id": item.unit_id,
                "bucket": item.bucket,
                "side": item.side,
                "entry_ts": item.entry_ts.isoformat(),
                "exit_ts": item.exit_ts.isoformat(),
                "entry_price": item.entry_price,
                "exit_price": item.exit_price,
                "exit_reason": item.exit_reason,
                "points": item.points,
                "usd": item.usd,
                "result": "win" if item.usd > 0 else "loss",
                "entry_hour": int(entry_row.get("hour", item.entry_ts.hour)),
                "entry_rth": bool(entry_row.get("rth", False)),
                "entry_day_of_week": int(entry_row.get("day_of_week", item.entry_ts.dayofweek)),
                "entry_month": int(entry_row.get("month", item.entry_ts.month)),
                "entry_year": int(entry_row.get("year", item.entry_ts.year)),
                "entry_ma_regime": ma_regime,
                "entry_ma_regime_prior": ma_prior,
                "entry_ma_spread": float(entry_row.get("ma_spread", np.nan)),
                "entry_ma_spread_prior": float(entry_row.get("ma_spread_prior", np.nan)),
                "ma_direction_aligned": (
                    (item.side == "long" and ma_regime == "bull")
                    or (item.side == "short" and ma_regime == "bear")
                ),
                "ma_prior_direction_aligned": (
                    (item.side == "long" and ma_prior == "bull")
                    or (item.side == "short" and ma_prior == "bear")
                ),
                "entry_st_trend": int(entry_row.get("supertrend_trend", 0))
                if not pd.isna(entry_row.get("supertrend_trend", np.nan))
                else 0,
                "entry_pmc_side": str(entry_row.get("pmc_side") or "unknown"),
                "entry_bars_since_st_flip": int(entry_row.get("bars_since_st_flip", -1)),
                "exit_ma_regime": str(exit_row.get("ma_regime") or "unknown"),
                "exit_st_trend": int(exit_row.get("supertrend_trend", 0))
                if not pd.isna(exit_row.get("supertrend_trend", np.nan))
                else 0,
            }
        )
    return pd.DataFrame(rows)


def load_actual_broker_units(path: Path, hourly: pd.DataFrame, variant_name: str = "actual_engine_base") -> pd.DataFrame:
    rows: List[UnitExit] = []
    if not path.exists():
        return pd.DataFrame()
    reader = csv.DictReader(path.open(newline="", encoding="utf-8"))
    for n, row in enumerate(reader, start=1):
        entry_ts = pd.Timestamp(row["entry_ts"])
        exit_ts = pd.Timestamp(row["exit_ts"])
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize(hourly.index.tz)
        else:
            entry_ts = entry_ts.tz_convert(hourly.index.tz)
        if exit_ts.tzinfo is None:
            exit_ts = exit_ts.tz_localize(hourly.index.tz)
        else:
            exit_ts = exit_ts.tz_convert(hourly.index.tz)
        idx = hourly.index.get_indexer([entry_ts], method="nearest")[0]
        entry_price = float(row["entry_price"])
        exit_price = float(row["exit_price"])
        side = "long" if str(row["direction"]).lower().startswith("long") else "short"
        points = (exit_price - entry_price) if side == "long" else (entry_price - exit_price)
        rows.append(
            UnitExit(
                variant=variant_name,
                trade_id=row.get("trade_id") or "%s_t%d" % (variant_name, n),
                unit_id=str(row.get("unit_id") or n),
                side=side,
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                entry_price=entry_price,
                exit_price=exit_price,
                exit_reason=str(row.get("exit_reason") or ""),
                bucket="unit",
                points=points,
                usd=points * POINT_VALUE - FEE_PER_UNIT,
                entry_row_pos=max(idx, 0),
            )
        )
    return exits_to_frame(rows, hourly)


def aggregate(df: pd.DataFrame, by: Sequence[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out_rows = []
    for key, group in df.groupby(list(by), dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        wins = group[group["usd"] > 0]
        losses = group[group["usd"] < 0]
        gross_win = float(wins["usd"].sum())
        gross_loss = abs(float(losses["usd"].sum()))
        row = {col: key[idx] for idx, col in enumerate(by)}
        row.update(
            {
                "units": len(group),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate_pct": 100.0 * len(wins) / len(group) if len(group) else 0.0,
                "net_usd": float(group["usd"].sum()),
                "profit_factor": gross_win / gross_loss if gross_loss else float("inf"),
                "avg_win_usd": gross_win / len(wins) if len(wins) else 0.0,
                "avg_loss_usd": -gross_loss / len(losses) if len(losses) else 0.0,
            }
        )
        out_rows.append(row)
    return pd.DataFrame(out_rows).sort_values(["net_usd"], ascending=True)


def loss_streaks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["streak_len", "count", "worst_streak_usd", "avg_streak_usd"])
    work = df.sort_values("exit_ts").copy()
    streaks: List[Tuple[int, float, str, str]] = []
    cur_len = 0
    cur_usd = 0.0
    start = ""
    end = ""
    for row in work.itertuples(index=False):
        if float(row.usd) < 0:
            if cur_len == 0:
                start = str(row.exit_ts)
            cur_len += 1
            cur_usd += float(row.usd)
            end = str(row.exit_ts)
        elif cur_len:
            streaks.append((cur_len, cur_usd, start, end))
            cur_len = 0
            cur_usd = 0.0
    if cur_len:
        streaks.append((cur_len, cur_usd, start, end))
    if not streaks:
        return pd.DataFrame(columns=["streak_len", "count", "worst_streak_usd", "avg_streak_usd"])
    raw = pd.DataFrame(streaks, columns=["streak_len", "streak_usd", "start_exit_ts", "end_exit_ts"])
    summary = (
        raw.groupby("streak_len")
        .agg(count=("streak_len", "size"), worst_streak_usd=("streak_usd", "min"), avg_streak_usd=("streak_usd", "mean"))
        .reset_index()
        .sort_values("streak_len", ascending=False)
    )
    return summary


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_outputs(
    output_root: Path,
    hourly: pd.DataFrame,
    summaries: List[Dict[str, object]],
    base_df: pd.DataFrame,
    actual_df: pd.DataFrame,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summaries).sort_values("net_over_stress", ascending=False)
    write_csv(summary_df, output_root / "variant_summary.csv")
    if not base_df.empty:
        write_csv(base_df, output_root / "base_fast_trades_enriched.csv")
    if not actual_df.empty:
        write_csv(actual_df, output_root / "actual_engine_base_trades_enriched.csv")

    profile_df = actual_df if not actual_df.empty else base_df
    profile_name = "actual_engine_base" if not actual_df.empty else "base_fast"
    profile_files: List[Tuple[str, pd.DataFrame]] = [
        ("loss_profile_by_side_ma_prior.csv", aggregate(profile_df, ["side", "entry_ma_regime_prior"])),
        ("loss_profile_by_side_ma_current.csv", aggregate(profile_df, ["side", "entry_ma_regime"])),
        ("loss_profile_by_ma_prior_alignment.csv", aggregate(profile_df, ["ma_prior_direction_aligned"])),
        ("loss_profile_by_hour.csv", aggregate(profile_df, ["entry_hour"])),
        ("loss_profile_by_rth.csv", aggregate(profile_df, ["entry_rth"])),
        ("loss_profile_by_month.csv", aggregate(profile_df, ["entry_month"])),
        ("loss_profile_by_year.csv", aggregate(profile_df, ["entry_year"])),
        ("loss_profile_by_exit_reason.csv", aggregate(profile_df, ["exit_reason"])),
    ]
    for filename, df in profile_files:
        write_csv(df, output_root / filename)
    streak_df = loss_streaks(profile_df)
    write_csv(streak_df, output_root / "loss_streaks.csv")
    _write_markdown(output_root, summary_df, profile_files, streak_df, profile_name)
    _write_plots(output_root, summary_df, profile_files)


def _money(value: object) -> str:
    try:
        return "$%s" % f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_ratio(value: object) -> str:
    try:
        if math.isinf(float(value)):
            return "inf"
        return "%.2f" % float(value)
    except (TypeError, ValueError):
        return str(value)


def _write_markdown(
    output_root: Path,
    summary_df: pd.DataFrame,
    profile_files: List[Tuple[str, pd.DataFrame]],
    streak_df: pd.DataFrame,
    profile_name: str,
) -> None:
    lines = [
        "# YM Hourly ST + PMC Loss Research",
        "",
        "This batch profiles the existing broker-like loss tape and runs fast broker-like variants.",
        "",
        "Simulation assumptions:",
        "- Resting entry limits fill before the current bar's strategy refresh/cancel, matching the Engine/PaperBroker ordering.",
        "- Fresh or modified entry limits become live only after the confirming hourly bar.",
        "- Protective stops fill before targets in same-bar ambiguity.",
        "- Stops and market exits carry 1 tick adverse slippage; unit exits include a $1.50 fee.",
        "- Scaleout runner stop moves to entry after TP1, effective from the next bar because the sequence inside that TP1 bar is unknowable.",
        "",
        "## Variant Sweep",
        "",
        "| Rank | Variant | Units | Trades | Net | Stress DD | Net/Stress | PF | Win Rate | Max Open | Notes |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rank, row in enumerate(summary_df.itertuples(index=False), start=1):
        lines.append(
            "| %d | `%s` | %s | %s | %s | %s | %s | %s | %.1f%% | %s | %s |"
            % (
                rank,
                row.variant,
                f"{int(row.units):,}",
                f"{int(row.trades):,}",
                _money(row.net_usd),
                _money(row.intrabar_stress_dd_usd),
                _fmt_ratio(row.net_over_stress),
                _fmt_ratio(row.profit_factor),
                float(row.win_rate_pct),
                int(row.max_open_units),
                str(row.config_notes).replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## Loss Profile Source",
            "",
            f"Loss profiling tables use `{profile_name}`.",
            "",
            "## Key Profile Tables",
            "",
        ]
    )
    for filename, df in profile_files:
        lines.append(f"- `{filename}` ({len(df)} rows)")
    lines.extend(
        [
            "- `loss_streaks.csv` (%d rows)" % len(streak_df),
            "",
            "## Quick Reads To Check First",
            "",
            "- `loss_profile_by_side_ma_prior.csv`: whether shorts lose inside bullish hourly MA regimes, or longs lose inside bearish regimes.",
            "- `loss_profile_by_hour.csv`: whether losses cluster around specific sessions.",
            "- `loss_profile_by_exit_reason.csv`: whether proposed clip rules reduce loss dollars or mostly cut winners.",
            "- `variant_summary.csv`: the horse race between MA filters, tighter stops, adverse-close exits, and the 2-lot 3R/6R scaleout.",
            "",
            "## Charts",
            "",
            "- `charts/variant_net_vs_stress.png`",
            "- `charts/profile_side_ma_prior_net.png`",
            "- `charts/profile_hour_net.png`",
            "",
        ]
    )
    (output_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _write_plots(output_root: Path, summary_df: pd.DataFrame, profile_files: List[Tuple[str, pd.DataFrame]]) -> None:
    charts = output_root / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    if not summary_df.empty:
        plot = summary_df.sort_values("net_over_stress", ascending=True).tail(12)
        fig, ax = plt.subplots(figsize=(12, 7))
        y = np.arange(len(plot))
        ax.barh(y, plot["net_over_stress"], color="#2878b5")
        ax.set_yticks(y)
        ax.set_yticklabels(plot["variant"], fontsize=8)
        ax.set_xlabel("Net / |Intrabar stress DD|")
        ax.set_title("YM hourly ST+PMC variant efficiency")
        ax.grid(True, axis="x", alpha=0.3)
        fig.tight_layout()
        fig.savefig(charts / "variant_net_vs_stress.png", dpi=140)
        plt.close(fig)

    tables = {name: df for name, df in profile_files}
    side_ma = tables.get("loss_profile_by_side_ma_prior.csv")
    if side_ma is not None and not side_ma.empty:
        labels = [f"{r.side}/{r.entry_ma_regime_prior}" for r in side_ma.itertuples(index=False)]
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ["#2878b5" if v >= 0 else "#c43d3d" for v in side_ma["net_usd"]]
        ax.bar(labels, side_ma["net_usd"], color=colors)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_ylabel("Net USD")
        ax.set_title("Broker-like loss profile by side and prior hourly MA regime")
        ax.tick_params(axis="x", rotation=35)
        ax.grid(True, axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(charts / "profile_side_ma_prior_net.png", dpi=140)
        plt.close(fig)

    by_hour = tables.get("loss_profile_by_hour.csv")
    if by_hour is not None and not by_hour.empty:
        by_hour = by_hour.sort_values("entry_hour")
        fig, ax = plt.subplots(figsize=(11, 5))
        colors = ["#2878b5" if v >= 0 else "#c43d3d" for v in by_hour["net_usd"]]
        ax.bar(by_hour["entry_hour"].astype(str), by_hour["net_usd"], color=colors)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Entry hour (America/New_York)")
        ax.set_ylabel("Net USD")
        ax.set_title("Broker-like loss/profile by entry hour")
        ax.grid(True, axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(charts / "profile_hour_net.png", dpi=140)
        plt.close(fig)


def run(args: argparse.Namespace) -> None:
    with _lock(args.output_root / "hourly_st_pmc_loss_research.lock"):
        hourly = load_hourly(args.dbn, args.daily, args.atr_len, args.atr_mult)
        if args.max_bars:
            hourly = hourly.iloc[: args.max_bars].copy()
        print("Hourly bars: %s" % f"{len(hourly):,}", flush=True)

        summaries: List[Dict[str, object]] = []
        base_df = pd.DataFrame()
        for idx, cfg in enumerate(variants(), start=1):
            print("Running %d/%d %s..." % (idx, len(variants()), cfg.name), flush=True)
            result = simulate_variant(hourly, cfg)
            summaries.append(summarize_exits(result))
            if cfg.name == "base_1x_50sl_150tp":
                base_df = exits_to_frame(result.exits, hourly)

        actual_df = load_actual_broker_units(args.actual_unit_fills, hourly) if args.actual_unit_fills else pd.DataFrame()
        write_outputs(args.output_root, hourly, summaries, base_df, actual_df)
        print("Wrote %s" % (args.output_root / "README.md"), flush=True)


class _lock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: Optional[int] = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = self.path.read_text(encoding="utf-8").strip() if self.path.exists() else ""
            pid_text = owner.splitlines()[0].strip() if owner else ""
            if pid_text.isdigit() and _pid_is_running(int(pid_text)):
                raise RuntimeError("Loss research already running: pid %s (%s)" % (pid_text, self.path))
            self.path.unlink(missing_ok=True)
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(self.fd, ("%d\n" % os.getpid()).encode("utf-8"))
        os.close(self.fd)
        self.fd = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.path.unlink(missing_ok=True)


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile YM hourly ST+PMC losses and sweep broker-like variants.")
    parser.add_argument(
        "--dbn",
        type=Path,
        default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    )
    parser.add_argument("--daily", type=Path, default=REPO / "ym" / "ym_daily.csv")
    parser.add_argument(
        "--actual-unit-fills",
        type=Path,
        default=REPO
        / "live"
        / "state"
        / "hourly_st_pmc_retest"
        / "audits"
        / "ym_hourly_st_pmc_retest"
        / "ym_hourly_st_pmc_retest"
        / "unit_fills.csv",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "hourly_st_pmc_loss_research",
    )
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--max-bars", type=int, default=None)
    args = parser.parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
