"""NQ CHOP20 dynamic range: 1m path-aware proof of best daily structure.

Structure under test (from loss-profile sweep):
  ``touch_broken_boundary_max_age_60``
  - daily close breakout of active CHOP20 range
  - max range age 60 daily bars
  - stop = touch broken range boundary (OR near side)
  - scale 1@0.5R / 1@1R / 1@4R

Causality contract (Platform HTF/finer-tape):
  - Daily bars are **signal-only** (range + breakout decision).
  - Entry is the RTH daily close (last available 1m close that session) + 1 tick adverse.
  - Resting stop / targets fill on the **1m** tape with **stop-first** same-bar policy.
  - Management bars are strictly after the entry fill timestamp.

This is a path-aware research replay (not yet a StrategyPlugin). Artifacts under
``live/state/nq_chop20_dynamic_range_1m_boundary60/``.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_chop20_dynamic_range_1m_replay --email
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
    DEFAULT_SOURCES,
    DetectorParams,
    add_range_metrics,
    load_bars,
)
from nq_chop_dynamic_range_loss_profile import (  # noqa: E402
    Variant,
    _entry_price,
    _exit_price,
    _points,
    _stop_price,
    _target,
)

NY = pytz.timezone("America/New_York")
DEFAULT_OUT = REPO / "live" / "state" / "nq_chop20_dynamic_range_1m_boundary60"
DSR = "TRL-2026-00176"
POINT_VALUE = 20.0
TICK_SIZE = 0.25
FEE = 1.50
VARIANT = Variant(
    "touch_broken_boundary_max_age_60",
    stop_mode="touch_broken_boundary",
    max_range_age_bars=60,
    runner_r=4.0,
)
TARGET_RS = (0.5, 1.0, 4.0)


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
            "trial_subclass": "nq_chop20_1m_boundary60",
            "is_independent": "TRUE",
            "market": "NQ",
            "replay_window_start": "",
            "replay_window_end": "",
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
                }
            ),
            "fixed_parameters_ref": "live/nq_chop20_dynamic_range_1m_replay.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "1m path proof of daily CHOP20 boundary-stop + max_age_60 + 0.5/1/4R",
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


def build_daily_signal_frame() -> pd.DataFrame:
    bars = load_bars(DEFAULT_SOURCES["D"]["NQ"], "D")
    return add_range_metrics(bars, DetectorParams())


def simulate_1m(
    daily: pd.DataFrame,
    gby: Dict[date, pd.DataFrame],
    *,
    hub: Path,
    slippage_ticks: int = 1,
    fee_per_unit: float = FEE,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Walk daily for signals; manage open trades on 1m with stop-first."""
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
    _progress(hub, "Simulating %d daily bars with 1m management …" % n)

    def add_exit(ot: OpenTrade, exit_ts: pd.Timestamp, exit_px: float, target_r: float, reason: str) -> None:
        nonlocal realized
        unit_number = 4 - ot.units_remaining
        pts = _points(ot.direction, ot.entry, exit_px)
        net = pts * POINT_VALUE - fee_per_unit
        unit_exits.append(
            {
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
        runner_label = "tp_%gr" % ot.runner_r
        runner_label = runner_label.replace(".", "_")
        if set(reasons) == {"tp_0_5r", "tp_1r", "tp_4r"} or set(reasons) == {"tp_0_5r", "tp_1r", runner_label}:
            exit_reason = "all_targets"
        elif any(str(r).startswith("stop_") for r in reasons):
            exit_reason = "stop_after_targets" if len(reasons) > 1 else reasons[-1]
        else:
            exit_reason = ",".join(reasons)
        net = float(sum(e["net_usd"] for e in exits))
        trades.append(
            {
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
        """Process new 1m bars with entry_ts < ts <= end_ts and ts > last_managed_ts."""
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
                        px = _exit_price(ot.direction, float(stop), slippage_ticks)
                        while ot.units_remaining > 0:
                            add_exit(ot, ts, px, 0.0, "stop_%s" % variant.stop_mode)
                        close_trade_record(ot, ts)
                        return None

                    for r in TARGET_RS:
                        label = ("tp_%gr" % r).replace(".", "_")
                        if label in ot.filled_targets or ot.units_remaining <= 0:
                            continue
                        tgt = _target(ot.direction, ot.entry, ot.width, r)
                        hit = (ot.direction == "long" and hi >= tgt) or (ot.direction == "short" and lo <= tgt)
                        if hit:
                            add_exit(ot, ts, tgt, r, label)
                            ot.filled_targets.add(label)
                            ot.best_filled_r = max(ot.best_filled_r, float(r))

                    ot.last_managed_ts = ts
                    if ot.units_remaining <= 0:
                        close_trade_record(ot, ts)
                        return None

                    open_mtm = _points(ot.direction, ot.entry, cl) * POINT_VALUE * ot.units_remaining
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

        # Update active range on range-like bars (same as daily diagnostic).
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
                "range_start_ts": _date_s(daily.iloc[range_group_start_idx]["date"]),
                "range_confirmed_ts": date_s,
                "range_high": float(row["range_high_20"]),
                "range_low": float(row["range_low_20"]),
                "width": float(row["range_20"]),
            }
        else:
            range_group_start_idx = None

        # Manage open trade through end of this session (1m RTH).
        if open_trade is not None:
            sess = _rth_session(gby.get(day), day)
            if not sess.empty:
                end_ts = sess.index[-1]
                if end_ts.tzinfo is None:
                    end_ts = NY.localize(end_ts)
                open_trade = manage_1m_until(open_trade, end_ts)
                if open_trade is None:
                    last_flatten_day = day

        # New entry only when flat; signal = daily close outside active range.
        if open_trade is None and active is not None and i > active["range_idx"] and last_flatten_day != day:
            range_age = i - active["range_idx"]
            if variant.max_range_age_bars is not None and range_age > variant.max_range_age_bars:
                direction = ""
            else:
                direction = ""
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
                if direction:
                    sess = _rth_session(gby.get(day), day)
                    if sess.empty:
                        direction = ""
                    else:
                        entry_bar_ts = sess.index[-1]
                        if entry_bar_ts.tzinfo is None:
                            entry_bar_ts = NY.localize(entry_bar_ts)
                        entry_close_1m = float(sess.iloc[-1]["close"])
                        # Prefer daily close for entry geometry; fall back to last 1m close.
                        entry_px = _entry_price(direction, close, slippage_ticks)
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
            open_mtm = _points(open_trade.direction, open_trade.entry, close) * POINT_VALUE * open_units
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
            _progress(hub, "  daily %d/%d trades=%d realized=$%+.0f" % (i + 1, n, trade_id, realized))

    # Flatten any leftover at data end.
    if open_trade is not None and open_trade.units_remaining > 0:
        last_day = pd.Timestamp(daily.iloc[-1]["date"]).tz_localize(None).date()
        sess = _rth_session(gby.get(last_day), last_day)
        if not sess.empty:
            ts = sess.index[-1]
            if ts.tzinfo is None:
                ts = NY.localize(ts)
            px = _exit_price(open_trade.direction, float(sess.iloc[-1]["close"]), slippage_ticks)
            while open_trade.units_remaining > 0:
                add_exit(open_trade, ts, px, 0.0, "data_end")
            close_trade_record(open_trade, ts)

    equity = pd.DataFrame(equity_rows)
    if not equity.empty:
        equity["closed_drawdown"] = equity["closed_equity"] - equity["closed_equity"].cummax()
        equity["mtm_drawdown"] = equity["mtm_equity"] - equity["mtm_equity"].cummax()
        equity.attrs["max_mtm_dd_1m_path"] = float(max_mtm_dd)
    return pd.DataFrame(trades), pd.DataFrame(unit_exits), equity


def _summarize(trades: pd.DataFrame, exits: pd.DataFrame, equity: pd.DataFrame) -> dict:
    net = float(trades["net_usd"].sum()) if not trades.empty else 0.0
    closed_dd = float(equity["closed_drawdown"].min()) if not equity.empty else 0.0
    mtm_dd = float(equity["mtm_drawdown"].min()) if not equity.empty else 0.0
    ns = (net / abs(mtm_dd)) if mtm_dd else 0.0
    wins = trades[trades["net_usd"] > 0] if not trades.empty else trades
    wr = (100.0 * len(wins) / len(trades)) if len(trades) else 0.0
    gp = float(wins["net_usd"].sum()) if len(wins) else 0.0
    loss = trades[trades["net_usd"] <= 0] if not trades.empty else trades
    gl = float((-loss["net_usd"]).sum()) if len(loss) else 0.0
    pf = (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)
    return {
        "variant": VARIANT.name,
        "trades": int(len(trades)),
        "units": int(len(exits)),
        "net_usd": net,
        "closed_drawdown": closed_dd,
        "mtm_drawdown": mtm_dd,
        "net_stress": ns,
        "win_rate": wr,
        "profit_factor": pf if np.isfinite(pf) else None,
        "long_net": float(trades.loc[trades.direction == "long", "net_usd"].sum()) if not trades.empty else 0.0,
        "short_net": float(trades.loc[trades.direction == "short", "net_usd"].sum()) if not trades.empty else 0.0,
        "avg_trade": float(trades["net_usd"].mean()) if not trades.empty else 0.0,
        "median_trade": float(trades["net_usd"].median()) if not trades.empty else 0.0,
    }


def run(*, output_root: Path, email: bool) -> dict:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="pandas",
        variant_slug=VARIANT.name + "_1m",
        instrument="NQ",
        hub_path=str(output_root.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "fill_tape": "1m",
            "same_bar": "stop_first",
            "stop_mode": "touch_broken_boundary",
            "max_range_age_bars": 60,
            "targets_r": [0.5, 1.0, 4.0],
            "note": "daily signal / 1m path fills; not StrategyPlugin yet",
        },
    )
    try:
        _progress(output_root, "Loading NQ daily + CHOP20 metrics …")
        daily = build_daily_signal_frame()
        _progress(output_root, "  daily bars=%d (%s → %s)" % (len(daily), _date_s(daily.iloc[0]["date"]), _date_s(daily.iloc[-1]["date"])))

        cfg = MARKETS["nq"]
        _progress(output_root, "Loading NQ 1m DBN …")
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), "nq")
        _progress(output_root, "  1m sessions=%d" % len(gby))

        trades, exits, equity = simulate_1m(daily, gby, hub=output_root)
        summary = _summarize(trades, exits, equity)

        trades.to_csv(output_root / "trades.csv", index=False)
        exits.to_csv(output_root / "unit_exits.csv", index=False)
        equity.to_csv(output_root / "equity_curve.csv", index=False)
        pd.DataFrame([summary]).to_csv(output_root / "summary.csv", index=False)

        # Exit mix
        if not exits.empty:
            mix = (
                exits.groupby("reason", as_index=False)
                .agg(units=("net_usd", "size"), net_usd=("net_usd", "sum"))
                .sort_values("net_usd", ascending=False)
            )
            mix.to_csv(output_root / "exit_mix.csv", index=False)
        else:
            mix = pd.DataFrame()

        net = summary["net_usd"]
        mtm_dd = summary["mtm_drawdown"]
        ns = summary["net_stress"]
        if ns >= 2.0 and summary["trades"] >= 40:
            stance = "research — 1m path supports daily structure"
        elif net > 0 and summary["trades"] >= 20:
            stance = "weak — needs plugin/hardening"
        else:
            stance = "reject / thin"

        lines = [
            "# NQ CHOP20 Dynamic Range — 1m Path Proof",
            "",
            "Variant: `%s`" % VARIANT.name,
            "",
            "- Daily CHOP20 range + close breakout = **signal only**",
            "- Entry = daily close (+1 tick adverse) at last RTH 1m of the signal day",
            "- Stop = touch broken range boundary; targets 0.5R / 1R / 4R",
            "- Max range age = 60 daily bars",
            "- 1m fills with **stop-first** same-bar policy",
            "- Not a StrategyPlugin yet (path-aware research replay)",
            "",
            "| Metric | Daily diagnostic (same structure) | 1m path |",
            "|---|---:|---:|",
            "| Trades | 75 | %d |" % summary["trades"],
            "| Net | $483,732 | $%s |" % ("{:,.0f}".format(net)),
            "| MTM DD | $-57,100 | $%s |" % ("{:,.0f}".format(mtm_dd)),
            "| Net/Stress | 8.47 | %.2f |" % ns,
            "| Win rate | 36.0%% | %.1f%% |" % summary["win_rate"],
            "| Long net | $410,632 | $%s |" % ("{:,.0f}".format(summary["long_net"])),
            "| Short net | $73,100 | $%s |" % ("{:,.0f}".format(summary["short_net"])),
            "",
            "**Stance:** %s" % stance,
            "",
            "DSR: `%s`" % DSR,
            "",
            "Hub: `%s`" % output_root,
            "",
        ]
        if not mix.empty:
            lines += ["## Exit mix (1m)", "", "| Reason | Units | Net |", "|---|---:|---:|"]
            for _, r in mix.iterrows():
                lines.append("| %s | %d | $%+.0f |" % (r["reason"], int(r["units"]), float(r["net_usd"])))
            lines.append("")
        (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n")
        (output_root / "RESEARCH_CONTRACT.yaml").write_text(
            "\n".join(
                [
                    "variant: %s" % VARIANT.name,
                    "signal_tf: daily",
                    "fill_tf: 1m",
                    "same_bar_policy: stop_first",
                    "entry: daily_close_plus_1tick",
                    "stop: touch_broken_boundary",
                    "max_range_age_bars: 60",
                    "targets_r: [0.5, 1.0, 4.0]",
                    "plugin: false",
                    "dsr: %s" % DSR,
                ]
            )
            + "\n"
        )

        complete_run(
            rid,
            net_usd=net,
            stress_dd_usd=mtm_dd,
            close_mtm_dd_usd=summary["closed_drawdown"],
            ns=ns,
            trades=summary["trades"],
            notes=stance,
        )
        _mark_dsr("COMPLETE")
        body = "potions: NQ CHOP20 1m boundary60 proof DONE\n\n" + "\n".join(lines)
        (output_root / "EMAIL.txt").write_text(body)
        if email:
            send_email(subject="potions: NQ CHOP20 1m boundary-stop max_age_60", body=body)
        _progress(output_root, "DONE net=$%+.0f N/S=%.2f trades=%d stance=%s" % (net, ns, summary["trades"], stance))
        summary["stance"] = stance
        return summary
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _mark_dsr("FAILED")
        err = traceback.format_exc()
        (output_root / "EMAIL.txt").write_text("FAILED\n\n" + err)
        if email:
            send_email(subject="potions: NQ CHOP20 1m boundary60 FAILED", body=err[-4000:])
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    run(output_root=args.output_root, email=bool(args.email))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
