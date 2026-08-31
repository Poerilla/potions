"""CHOP20 dynamic range: 1m path proof across NQ / YM / MYM / MNQ.

Structure: touch_broken_boundary + max_age_60 + 0.5R/1R/4R
(daily signal only; fills on 1m RTH with stop-first).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_1m_cross_market --email
  python -m live.chop20_dynamic_range_1m_cross_market --email --markets nq,ym
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path[:0] = [str(SCRIPTS)]

from chop_range_breakout_charts import (  # noqa: E402
    DetectorParams,
    add_range_metrics,
    load_bars,
)
from nq_chop_dynamic_range_loss_profile import Variant, _points, _stop_price, _target  # noqa: E402

NY = pytz.timezone("America/New_York")
HUB = REPO / "live" / "state" / "chop20_dynamic_range_1m_boundary60_xmarket"
DSR = "TRL-2026-00177"
VARIANT = Variant(
    "touch_broken_boundary_max_age_60",
    stop_mode="touch_broken_boundary",
    max_range_age_bars=60,
    runner_r=4.0,
)
TARGET_RS = (0.5, 1.0, 4.0)

DAILY_PATHS = {
    "nq": REPO / "nq" / "nq_daily.csv",
    "ym": REPO / "ym" / "ym_daily.csv",
    "mym": REPO / "mym" / "mym_daily.csv",
    "mnq": REPO / "mnq" / "mnq_daily.csv",
}
POINT_VALUES = {"nq": 20.0, "ym": 5.0, "mym": 0.5, "mnq": 2.0}
TICK_SIZES = {"nq": 0.25, "ym": 1.0, "mym": 1.0, "mnq": 0.25}
FEE = 1.50
DEFAULT_MARKETS = ("nq", "ym", "mym", "mnq")


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "chop20_1m_boundary60_xmarket",
            "is_independent": "TRUE",
            "market": "NQ,YM,MYM,MNQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "variant": VARIANT.name,
                    "stop_mode": "touch_broken_boundary",
                    "max_range_age_bars": 60,
                    "targets_r": [0.5, 1.0, 4.0],
                    "fill_tape": "1m",
                    "same_bar": "stop_first",
                    "markets": list(DEFAULT_MARKETS),
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_1m_cross_market.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Cross-market 1m path proof of CHOP20 boundary60 structure",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str = "COMPLETE") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _date_s(value) -> str:
    return pd.Timestamp(value).tz_localize(None).date().isoformat()


def _entry_price(direction: str, close: float, slip_ticks: int, tick: float) -> float:
    slip = slip_ticks * tick
    return float(close + slip if direction == "long" else close - slip)


def _exit_price(direction: str, price: float, slip_ticks: int, tick: float) -> float:
    slip = slip_ticks * tick
    return float(price - slip if direction == "long" else price + slip)


def _rth_session(df: pd.DataFrame, day: date) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    part = df.copy()
    if part.index.tz is None:
        part.index = part.index.tz_localize(NY)
    else:
        part.index = part.index.tz_convert(NY)
    part = part[part.index.date == day]
    if part.empty:
        return part
    t = part.index.time
    return part[(t >= time(9, 30)) & (t < time(16, 0))]


@dataclass
class OpenTrade:
    trade_id: int
    direction: str
    entry_ts: pd.Timestamp
    entry: float
    range_high: float
    range_low: float
    width: float
    range_id: int
    range_idx: int
    range_confirmed_ts: str
    attempt_number: int
    breakout_gap_r: float
    units_remaining: int = 3
    filled_targets: set = field(default_factory=set)
    best_filled_r: float = 0.0
    runner_r: float = 4.0
    mfe_pts: float = 0.0
    mae_pts: float = 0.0
    last_managed_ts: Optional[pd.Timestamp] = None
    entry_day_idx: int = 0


def build_daily_signal_frame(market: str) -> pd.DataFrame:
    path = DAILY_PATHS[market]
    bars = load_bars(path, "D")
    return add_range_metrics(bars, DetectorParams())


def simulate_1m(
    daily: pd.DataFrame,
    gby: Dict[date, pd.DataFrame],
    *,
    hub: Path,
    market: str,
    point_value: float,
    tick_size: float,
    slippage_ticks: int = 1,
    fee_per_unit: float = FEE,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    variant = VARIANT
    active: Optional[dict] = None
    range_group_start_idx: Optional[int] = None
    range_group_id = 0
    range_id = 0
    trade_id = 0
    attempts_by_range: Dict[int, int] = {}
    open_trade: Optional[OpenTrade] = None
    trades: List[dict] = []
    unit_exits: List[dict] = []
    equity_rows: List[dict] = []
    realized = 0.0
    peak_mtm = 0.0
    max_mtm_dd = 0.0
    last_flatten_day: Optional[date] = None
    n = len(daily)
    _progress(hub, "[%s] Simulating %d daily bars …" % (market.upper(), n))

    def add_exit(ot: OpenTrade, exit_ts: pd.Timestamp, exit_px: float, target_r: float, reason: str) -> None:
        nonlocal realized
        unit_number = 4 - ot.units_remaining
        pts = _points(ot.direction, ot.entry, exit_px)
        net = pts * point_value - fee_per_unit
        unit_exits.append(
            {
                "market": market.upper(),
                "trade_id": ot.trade_id,
                "unit_number": unit_number,
                "direction": ot.direction,
                "entry_ts": ot.entry_ts.isoformat(),
                "exit_ts": exit_ts.isoformat(),
                "entry_price": ot.entry,
                "exit_price": float(exit_px),
                "target_r": float(target_r),
                "reason": reason,
                "points": pts,
                "net_usd": net,
            }
        )
        realized += net
        ot.units_remaining -= 1

    def close_trade_record(ot: OpenTrade, exit_ts: pd.Timestamp) -> None:
        exits = [e for e in unit_exits if e["trade_id"] == ot.trade_id]
        reasons = sorted({e["reason"] for e in exits})
        runner_label = ("tp_%gr" % ot.runner_r).replace(".", "_")
        if set(reasons) == {"tp_0_5r", "tp_1r", "tp_4r"} or set(reasons) == {
            "tp_0_5r",
            "tp_1r",
            runner_label,
        }:
            exit_reason = "all_targets"
        elif any(str(r).startswith("stop_") for r in reasons):
            exit_reason = "stop_after_targets" if len(reasons) > 1 else reasons[-1]
        else:
            exit_reason = ",".join(reasons)
        net = float(sum(e["net_usd"] for e in exits))
        trades.append(
            {
                "market": market.upper(),
                "trade_id": ot.trade_id,
                "direction": ot.direction,
                "range_id": ot.range_id,
                "attempt_number": ot.attempt_number,
                "range_confirmed_ts": ot.range_confirmed_ts,
                "entry_ts": ot.entry_ts.isoformat(),
                "exit_ts": exit_ts.isoformat(),
                "range_age_bars": int(ot.entry_day_idx - ot.range_idx),
                "entry": float(ot.entry),
                "range_high": float(ot.range_high),
                "range_low": float(ot.range_low),
                "range_width_r": float(ot.width),
                "breakout_gap_r": float(ot.breakout_gap_r),
                "mfe_pts": float(ot.mfe_pts),
                "mae_pts": float(ot.mae_pts),
                "exit_reason": exit_reason,
                "units": len(exits),
                "winning_units": int(sum(1 for e in exits if e["net_usd"] > 0)),
                "net_usd": net,
            }
        )

    def manage_1m_until(ot: OpenTrade, end_ts: pd.Timestamp) -> Optional[OpenTrade]:
        nonlocal realized, peak_mtm, max_mtm_dd
        cursor = ot.last_managed_ts if ot.last_managed_ts is not None else ot.entry_ts
        day0 = cursor.tz_convert(NY).date() if cursor.tzinfo else cursor.date()
        day1 = end_ts.tz_convert(NY).date() if end_ts.tzinfo else end_ts.date()
        d = day0
        while d <= day1 and ot is not None and ot.units_remaining > 0:
            sess = _rth_session(gby.get(d), d)
            if not sess.empty:
                for ts, row in sess.iterrows():
                    ts = pd.Timestamp(ts)
                    if ts.tzinfo is None:
                        ts = NY.localize(ts)
                    if ts <= cursor:
                        continue
                    if ts > end_ts:
                        break
                    hi = float(row["high"])
                    lo = float(row["low"])
                    cl = float(row["close"])
                    if ot.direction == "long":
                        ot.mfe_pts = max(ot.mfe_pts, hi - ot.entry)
                        ot.mae_pts = min(ot.mae_pts, lo - ot.entry)
                    else:
                        ot.mfe_pts = max(ot.mfe_pts, ot.entry - lo)
                        ot.mae_pts = min(ot.mae_pts, ot.entry - hi)

                    stop = _stop_price(
                        {
                            "direction": ot.direction,
                            "range_high": ot.range_high,
                            "range_low": ot.range_low,
                            "width": ot.width,
                            "entry": ot.entry,
                            "best_filled_r": ot.best_filled_r,
                        },
                        variant,
                    )
                    stopped = False
                    if stop is not None:
                        if ot.direction == "long" and lo <= stop:
                            stopped = True
                        elif ot.direction == "short" and hi >= stop:
                            stopped = True
                    if stopped:
                        px = _exit_price(ot.direction, float(stop), slippage_ticks, tick_size)
                        while ot.units_remaining > 0:
                            add_exit(ot, ts, px, 0.0, "stop_%s" % variant.stop_mode)
                        close_trade_record(ot, ts)
                        return None

                    for r in TARGET_RS:
                        label = ("tp_%gr" % r).replace(".", "_")
                        if label in ot.filled_targets or ot.units_remaining <= 0:
                            continue
                        tgt = _target(ot.direction, ot.entry, ot.width, r)
                        hit = (ot.direction == "long" and hi >= tgt) or (
                            ot.direction == "short" and lo <= tgt
                        )
                        if hit:
                            add_exit(ot, ts, tgt, r, label)
                            ot.filled_targets.add(label)
                            ot.best_filled_r = max(ot.best_filled_r, float(r))

                    ot.last_managed_ts = ts
                    if ot.units_remaining <= 0:
                        close_trade_record(ot, ts)
                        return None

                    open_mtm = _points(ot.direction, ot.entry, cl) * point_value * ot.units_remaining
                    mtm_eq = realized + open_mtm
                    peak_mtm = max(peak_mtm, mtm_eq)
                    max_mtm_dd = min(max_mtm_dd, mtm_eq - peak_mtm)
            d = (pd.Timestamp(d) + pd.Timedelta(days=1)).date()
        return ot

    for i, row in daily.iterrows():
        i = int(i)
        date_s = _date_s(row["date"])
        day = pd.Timestamp(row["date"]).tz_localize(None).date()
        close = float(row["close"])

        if bool(row["is_range_like"]):
            if range_group_start_idx is None:
                range_group_id += 1
                range_group_start_idx = i
            range_id += 1
            active = {
                "range_id": range_id,
                "range_group_id": range_group_id,
                "range_idx": i,
                "range_group_start_idx": range_group_start_idx,
                "range_confirmed_ts": date_s,
                "range_high": float(row["range_high_20"]),
                "range_low": float(row["range_low_20"]),
                "width": float(row["range_20"]),
            }
        else:
            range_group_start_idx = None

        if open_trade is not None:
            sess = _rth_session(gby.get(day), day)
            if not sess.empty:
                end_ts = sess.index[-1]
                if end_ts.tzinfo is None:
                    end_ts = NY.localize(end_ts)
                open_trade = manage_1m_until(open_trade, end_ts)
                if open_trade is None:
                    last_flatten_day = day

        if open_trade is None and active is not None and i > active["range_idx"] and last_flatten_day != day:
            range_age = i - active["range_idx"]
            direction = ""
            if variant.max_range_age_bars is None or range_age <= variant.max_range_age_bars:
                if close > active["range_high"]:
                    direction = "long"
                elif close < active["range_low"]:
                    direction = "short"
            if direction and variant.sides != "both" and direction != variant.sides:
                direction = ""
            gap_r = 0.0
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
                else:
                    sess = _rth_session(gby.get(day), day)
                    if sess.empty:
                        direction = ""
                    else:
                        entry_bar_ts = sess.index[-1]
                        if entry_bar_ts.tzinfo is None:
                            entry_bar_ts = NY.localize(entry_bar_ts)
                        entry_px = _entry_price(direction, close, slippage_ticks, tick_size)
                        attempts_by_range[active["range_id"]] = attempts
                        trade_id += 1
                        open_trade = OpenTrade(
                            trade_id=trade_id,
                            direction=direction,
                            entry_ts=entry_bar_ts,
                            entry=entry_px,
                            range_high=float(active["range_high"]),
                            range_low=float(active["range_low"]),
                            width=float(active["width"]),
                            range_id=int(active["range_id"]),
                            range_idx=int(active["range_idx"]),
                            range_confirmed_ts=str(active["range_confirmed_ts"]),
                            attempt_number=attempts,
                            breakout_gap_r=float(gap_r),
                            runner_r=float(variant.runner_r),
                            last_managed_ts=entry_bar_ts,
                            entry_day_idx=i,
                        )

        open_mtm = 0.0
        open_units = 0
        if open_trade is not None:
            open_units = open_trade.units_remaining
            open_mtm = _points(open_trade.direction, open_trade.entry, close) * point_value * open_units
        mtm_eq = realized + open_mtm
        peak_mtm = max(peak_mtm, mtm_eq)
        max_mtm_dd = min(max_mtm_dd, mtm_eq - peak_mtm)
        equity_rows.append(
            {
                "date": date_s,
                "closed_equity": realized,
                "mtm_equity": mtm_eq,
                "open_units": open_units,
            }
        )
        if (i + 1) % 500 == 0 or (i + 1) == n:
            _progress(
                hub,
                "  [%s] daily %d/%d trades=%d realized=$%+.0f"
                % (market.upper(), i + 1, n, trade_id, realized),
            )

    if open_trade is not None and open_trade.units_remaining > 0:
        last_day = pd.Timestamp(daily.iloc[-1]["date"]).tz_localize(None).date()
        sess = _rth_session(gby.get(last_day), last_day)
        if not sess.empty:
            ts = sess.index[-1]
            if ts.tzinfo is None:
                ts = NY.localize(ts)
            px = _exit_price(open_trade.direction, float(sess.iloc[-1]["close"]), slippage_ticks, tick_size)
            while open_trade.units_remaining > 0:
                add_exit(open_trade, ts, px, 0.0, "data_end")
            close_trade_record(open_trade, ts)

    equity = pd.DataFrame(equity_rows)
    if not equity.empty:
        equity["closed_drawdown"] = equity["closed_equity"] - equity["closed_equity"].cummax()
        equity["mtm_drawdown"] = equity["mtm_equity"] - equity["mtm_equity"].cummax()
        equity.attrs["max_mtm_dd_1m_path"] = float(max_mtm_dd)
    return pd.DataFrame(trades), pd.DataFrame(unit_exits), equity


def _summarize(market: str, trades: pd.DataFrame, exits: pd.DataFrame, equity: pd.DataFrame) -> dict:
    net = float(trades["net_usd"].sum()) if not trades.empty else 0.0
    closed_dd = float(equity["closed_drawdown"].min()) if not equity.empty else 0.0
    mtm_dd = float(equity["mtm_drawdown"].min()) if not equity.empty else 0.0
    ns = (net / abs(mtm_dd)) if mtm_dd else 0.0
    wins = trades[trades["net_usd"] > 0] if not trades.empty else trades
    wr = (100.0 * len(wins) / len(trades)) if len(trades) else 0.0
    return {
        "market": market.upper(),
        "variant": VARIANT.name,
        "trades": int(len(trades)),
        "units": int(len(exits)),
        "net_usd": net,
        "closed_drawdown": closed_dd,
        "mtm_drawdown": mtm_dd,
        "net_stress": ns,
        "win_rate": wr,
        "long_net": float(trades.loc[trades.direction == "long", "net_usd"].sum()) if not trades.empty else 0.0,
        "short_net": float(trades.loc[trades.direction == "short", "net_usd"].sum()) if not trades.empty else 0.0,
        "avg_trade": float(trades["net_usd"].mean()) if not trades.empty else 0.0,
        "median_trade": float(trades["net_usd"].median()) if not trades.empty else 0.0,
        "start": _date_s(trades["entry_ts"].iloc[0]) if not trades.empty else "",
        "end": _date_s(trades["exit_ts"].iloc[-1]) if not trades.empty else "",
    }


def run_one(market: str, hub: Path) -> dict:
    m = market.lower()
    out = hub / m
    out.mkdir(parents=True, exist_ok=True)
    rid = begin_run(
        run_class="pandas",
        variant_slug="%s_%s_1m" % (m, VARIANT.name),
        instrument=m.upper(),
        hub_path=str(out.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "fill_tape": "1m",
            "same_bar": "stop_first",
            "stop_mode": "touch_broken_boundary",
            "max_range_age_bars": 60,
            "targets_r": [0.5, 1.0, 4.0],
        },
    )
    try:
        _progress(hub, "Loading %s daily + CHOP20 …" % m.upper())
        daily = build_daily_signal_frame(m)
        cfg = MARKETS[m]
        if cfg.start is not None:
            daily = daily[pd.to_datetime(daily["date"]).dt.date >= cfg.start].reset_index(drop=True)
        _progress(
            hub,
            "  %s daily bars=%d (%s → %s)"
            % (m.upper(), len(daily), _date_s(daily.iloc[0]["date"]), _date_s(daily.iloc[-1]["date"])),
        )
        _progress(hub, "Loading %s 1m …" % m.upper())
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), m)
        _progress(hub, "  %s 1m sessions=%d" % (m.upper(), len(gby)))
        trades, exits, equity = simulate_1m(
            daily,
            gby,
            hub=hub,
            market=m,
            point_value=POINT_VALUES[m],
            tick_size=TICK_SIZES[m],
        )
        summary = _summarize(m, trades, exits, equity)
        trades.to_csv(out / "trades.csv", index=False)
        exits.to_csv(out / "unit_exits.csv", index=False)
        equity.to_csv(out / "equity_curve.csv", index=False)
        pd.DataFrame([summary]).to_csv(out / "summary.csv", index=False)
        if not exits.empty:
            mix = (
                exits.groupby("reason", as_index=False)
                .agg(units=("net_usd", "count"), net_usd=("net_usd", "sum"))
                .sort_values("net_usd", ascending=False)
            )
            mix.to_csv(out / "exit_mix.csv", index=False)
        complete_run(
            rid,
            net_usd=summary["net_usd"],
            stress_dd_usd=summary["mtm_drawdown"],
            close_mtm_dd_usd=summary["closed_drawdown"],
            ns=summary["net_stress"],
            trades=summary["trades"],
            units=summary["units"],
            equity_curve_path=out / "equity_curve.csv",
            notes="1m path CHOP20 boundary60",
            meta={"win_rate": summary["win_rate"]},
        )
        _progress(
            hub,
            "DONE %s net=$%+.0f N/S=%.2f trades=%d"
            % (m.upper(), summary["net_usd"], summary["net_stress"], summary["trades"]),
        )
        return summary
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-1500:])
        raise


def run(*, markets: Sequence[str], email: bool) -> pd.DataFrame:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rows = []
    errors = []
    for m in markets:
        try:
            rows.append(run_one(m, HUB))
        except Exception:
            errors.append("%s:\n%s" % (m, traceback.format_exc()[-2000:]))
            _progress(HUB, "FAILED %s" % m.upper())
    board = pd.DataFrame(rows)
    if not board.empty:
        board = board.sort_values("net_stress", ascending=False).reset_index(drop=True)
        board.to_csv(HUB / "summary_board.csv", index=False)

    lines = [
        "# CHOP20 Dynamic Range — 1m Cross-Market Path Proof",
        "",
        "Variant: `%s`" % VARIANT.name,
        "",
        "- Daily CHOP20 range + close breakout = **signal only**",
        "- Entry = daily close (+1 tick adverse) at last RTH 1m",
        "- Stop = touch broken range boundary; targets 0.5R / 1R / 4R",
        "- Max range age = 60 daily bars; **stop-first** same-bar on 1m",
        "- Path-aware pandas replay (not StrategyPlugin yet)",
        "",
        "| Market | Trades | Net | MTM DD | N/S | WR | Long | Short |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in board.iterrows() if not board.empty else []:
        lines.append(
            "| %s | %d | $%+.0f | $%+.0f | %.2f | %.0f%% | $%+.0f | $%+.0f |"
            % (
                r["market"],
                int(r["trades"]),
                r["net_usd"],
                r["mtm_drawdown"],
                r["net_stress"],
                r["win_rate"],
                r["long_net"],
                r["short_net"],
            )
        )
    if errors:
        lines += ["", "## Errors", ""] + ["```\n%s\n```" % e for e in errors]
    best = board.iloc[0] if not board.empty else None
    stance = "research"
    if best is not None and float(best["net_stress"]) >= 2.0 and float(best["net_usd"]) > 0:
        stance = "research — structure portable on best markets; see HA mill / causality"
    elif best is not None and float(best["net_usd"]) <= 0:
        stance = "reject on weak markets; NQ path still research"
    lines += ["", "**Stance:** %s" % stance, "", "DSR: `%s`" % DSR, "", "Hub: `%s`" % HUB, ""]
    (HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    body = "potions: CHOP20 1m cross-market DONE\n\n" + "\n".join(lines)
    (HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
    _mark_dsr("COMPLETE" if not errors else "FAILED")
    if email:
        send_email(subject="potions: CHOP20 1m boundary60 cross-market", body=body)
    return board


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--email", action="store_true")
    p.add_argument("--markets", default=",".join(DEFAULT_MARKETS))
    args = p.parse_args()
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    run(markets=markets, email=bool(args.email))


if __name__ == "__main__":
    main()
