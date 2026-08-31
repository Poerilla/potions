"""CHOP20 boundary60 — causal entry variants + NQ/MNQ HP gates on 1m path.

Same structure as the non-causal same-day close path:
  daily CHOP20 range + close breakout = signal only
  stop = touch broken boundary; targets 0.5R / 1R / 4R; max age 60; stop-first

Entry modes (locked, not optimized)::

  close_to_globex   — available_at = last RTH 1m of signal day; fill on the
                      first 1m bar strictly after available_at (post-close /
                      Globex tape), adverse 1 tick vs that bar's open.
  close_to_next_rth — same available_at; fill on next session's first RTH
                      minute (≈09:30), adverse 1 tick vs that bar's open.

HP gates (NQ / MNQ best notables from the HA mill — re-simulated, not
post-hoc subsets)::

  nq  rsi_align=rsi_with_side
  nq  rsi_bucket=rsi_gt70
  mnq week_of_month=3

Features for HP are as-of available_at (completed hour / calendar of signal
day). HA size-ups are **not** run — descriptive research only.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_causal_entry_variants --email
  python -m live.chop20_dynamic_range_causal_entry_variants --email --smoke
  python -m live.chop20_dynamic_range_causal_entry_variants --email --markets nq
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
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
HUB = REPO / "live" / "state" / "chop20_dynamic_range_causal_entry_variants"
DSR = "TRL-2026-00180"
VARIANT = Variant(
    "touch_broken_boundary_max_age_60",
    stop_mode="touch_broken_boundary",
    max_range_age_bars=60,
    runner_r=4.0,
)
TARGET_RS = (0.5, 1.0, 4.0)

DAILY_PATHS = {
    "nq": REPO / "nq" / "nq_daily.csv",
    "mnq": REPO / "mnq" / "mnq_daily.csv",
}
POINT_VALUES = {"nq": 20.0, "mnq": 2.0}
TICK_SIZES = {"nq": 0.25, "mnq": 0.25}
FEE = 1.50
DEFAULT_MARKETS = ("nq", "mnq")
ENTRY_MODES = ("close_to_globex", "close_to_next_rth")

# Best HP notables from chop20 HA mill (NQ/MNQ) — filter only, no size-up.
HP_SPECS: Tuple[Tuple[str, Optional[Tuple[str, object]], str], ...] = (
    ("baseline", None, "no HP gate"),
    ("hp_rsi_with_side", ("rsi_align", "rsi_with_side"), "Hourly RSI vs trade"),
    ("hp_rsi_gt70", ("rsi_bucket", "rsi_gt70"), "Hourly RSI bucket"),
    ("hp_wom3", ("week_of_month", 3), "Week of month"),
)


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
            "trial_subclass": "chop20_causal_entry_hp",
            "is_independent": "TRUE",
            "market": "NQ,MNQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "variant": VARIANT.name,
                    "entry_modes": list(ENTRY_MODES),
                    "hp_gates": [h[0] for h in HP_SPECS],
                    "targets_r": [0.5, 1.0, 4.0],
                    "fill_tape": "1m",
                    "same_bar": "stop_first",
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_causal_entry_variants.py",
            "num_params_varied": "2",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Causal close→Globex / next-RTH entry + NQ/MNQ HP filter gates",
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


def _localize_ts(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        return NY.localize(ts)
    return ts.tz_convert(NY)


def _entry_price(direction: str, px: float, slip_ticks: int, tick: float) -> float:
    slip = slip_ticks * tick
    return float(px + slip if direction == "long" else px - slip)


def _exit_price(direction: str, price: float, slip_ticks: int, tick: float) -> float:
    slip = slip_ticks * tick
    return float(price - slip if direction == "long" else price + slip)


def _day_frame(df: Optional[pd.DataFrame], day: date) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    part = df.copy()
    if part.index.tz is None:
        part.index = part.index.tz_localize(NY)
    else:
        part.index = part.index.tz_convert(NY)
    return part[part.index.date == day]


def _rth_session(df: Optional[pd.DataFrame], day: date) -> pd.DataFrame:
    part = _day_frame(df, day)
    if part.empty:
        return part
    t = part.index.time
    return part[(t >= time(9, 30)) & (t < time(16, 0))]


def _last_rth_bar(gby: Dict[date, pd.DataFrame], day: date) -> Tuple[Optional[pd.Timestamp], Optional[pd.Series]]:
    sess = _rth_session(gby.get(day), day)
    if sess.empty:
        return None, None
    ts = _localize_ts(sess.index[-1])
    return ts, sess.iloc[-1]


def _last_ny_day_bar(gby: Dict[date, pd.DataFrame], day: date) -> Tuple[Optional[pd.Timestamp], Optional[pd.Series]]:
    """Last 1m of the NY calendar day (FX / metals / 24h CFD daily close)."""
    part = _day_frame(gby.get(day), day)
    if part.empty:
        return None, None
    ts = _localize_ts(part.index[-1])
    return ts, part.iloc[-1]


def _last_avail_bar(
    gby: Dict[date, pd.DataFrame],
    day: date,
    *,
    session_mode: str,
) -> Tuple[Optional[pd.Timestamp], Optional[pd.Series]]:
    if session_mode == "ny_day":
        return _last_ny_day_bar(gby, day)
    return _last_rth_bar(gby, day)


def _first_bar_after(
    gby: Dict[date, pd.DataFrame],
    available_at: pd.Timestamp,
    *,
    rth_only: bool,
    max_days: int = 10,
) -> Tuple[Optional[pd.Timestamp], Optional[pd.Series], Optional[date]]:
    """First executable 1m after available_at (Globex continuum or next RTH)."""
    d0 = available_at.tz_convert(NY).date()
    for offset in range(0, max_days + 1):
        d = d0 + timedelta(days=offset)
        part = _rth_session(gby.get(d), d) if rth_only else _day_frame(gby.get(d), d)
        if part.empty:
            continue
        for ts, row in part.iterrows():
            ts = _localize_ts(ts)
            if ts <= available_at:
                continue
            if rth_only and offset == 0:
                # next RTH must be a later session day
                continue
            return ts, row, d
    return None, None, None


def build_daily_signal_frame(market: str) -> pd.DataFrame:
    bars = load_bars(DAILY_PATHS[market], "D")
    return add_range_metrics(bars, DetectorParams())


def _load_hourly_feat(market: str) -> Optional[pd.DataFrame]:
    """Causal hourly RSI features (ts shifted +1h = available_at)."""
    try:
        from .intraday_condition_profile import build_feature_frames
        from .chop20_dynamic_range_ha_conditions import _seed_daily_cache
    except Exception:
        return None
    sym = market.upper()
    try:
        _seed_daily_cache(sym)
        feats = build_feature_frames(sym)
        return feats["h1"][["ts", "rsi14", "rsi_bucket"]].sort_values("ts")
    except Exception as exc:
        print("  hourly feat load failed for %s: %s" % (sym, exc), flush=True)
        return None


def _asof_row(df: Optional[pd.DataFrame], ts: pd.Timestamp) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    sub = df[df["ts"] <= ts]
    if sub.empty:
        return None
    return sub.iloc[-1]


def _hp_at(
    available_at: pd.Timestamp,
    direction: str,
    h1: Optional[pd.DataFrame],
    *,
    hp_feats: Optional[Dict[str, pd.DataFrame]] = None,
    signal_price: Optional[float] = None,
    atr_edges: Optional[Sequence[float]] = None,
    hour_ny: Optional[int] = None,
) -> Dict[str, object]:
    """Feature snapshot at daily-close availability (signal time).

    Extended pack (hp_feats) mirrors HA mill annotate_campaigns so overlay
    filter gates can be re-sim'd on the causal 1m path.
    """
    aa = available_at.tz_convert(NY)
    out: Dict[str, object] = {
        "week_of_month": int((aa.day - 1) // 7 + 1),
        "dow": aa.day_name(),
        "hour_ny": int(aa.hour if hour_ny is None else hour_ny),
        "rsi14": np.nan,
        "rsi_bucket": "na",
        "rsi_align": "rsi_na",
        "obv_align": "obv_na",
        "ma5_align": "ma_na",
        "ma5_cross_align": "cross_none",
        "atr_q": "atr_na",
        "week_half_align": "week_na",
        "day_half_align": "day_na",
    }
    h1_use = h1
    if hp_feats is not None and "h1" in hp_feats:
        h1_use = hp_feats["h1"]
    row = _asof_row(h1_use, aa)
    if row is not None:
        rsi = float(row["rsi14"]) if "rsi14" in row and pd.notna(row["rsi14"]) else float("nan")
        bucket = str(row["rsi_bucket"]) if "rsi_bucket" in row else "na"
        out["rsi14"] = rsi
        out["rsi_bucket"] = bucket
        if np.isnan(rsi):
            out["rsi_align"] = "rsi_na"
        elif (direction == "long" and rsi >= 55) or (direction == "short" and rsi <= 45):
            out["rsi_align"] = "rsi_with_side"
        elif (direction == "long" and rsi <= 45) or (direction == "short" and rsi >= 55):
            out["rsi_align"] = "rsi_against_side"
        else:
            out["rsi_align"] = "rsi_neutral"
        if "obv_cross" in row and pd.notna(row["obv_cross"]):
            oc = str(row["obv_cross"])
            if (direction == "long" and oc == "obv_above_ma") or (direction == "short" and oc == "obv_below_ma"):
                out["obv_align"] = "obv_aligned"
            elif (direction == "long" and oc == "obv_below_ma") or (direction == "short" and oc == "obv_above_ma"):
                out["obv_align"] = "obv_opposed"
            else:
                out["obv_align"] = "obv_flat"
    if hp_feats is not None:
        mrow = _asof_row(hp_feats.get("m5"), aa)
        if mrow is not None and "ma_state" in mrow and pd.notna(mrow["ma_state"]):
            ms = str(mrow["ma_state"])
            if (direction == "long" and ms == "ma_bull") or (direction == "short" and ms == "ma_bear"):
                out["ma5_align"] = "ma_aligned"
            elif (direction == "long" and ms == "ma_bear") or (direction == "short" and ms == "ma_bull"):
                out["ma5_align"] = "ma_opposed"
            else:
                out["ma5_align"] = "ma_flat"
            mc = str(mrow["ma_cross"]) if "ma_cross" in mrow and pd.notna(mrow["ma_cross"]) else "ma_no_cross"
            if mc == "ma_no_cross":
                out["ma5_cross_align"] = "cross_none"
            elif (direction == "long" and mc == "ma_cross_up") or (direction == "short" and mc == "ma_cross_down"):
                out["ma5_cross_align"] = "cross_aligned"
            else:
                out["ma5_cross_align"] = "cross_opposed"
        drow = _asof_row(hp_feats.get("d1"), aa)
        px = signal_price
        if drow is not None:
            if atr_edges is not None and len(atr_edges) >= 5 and "atr14" in drow and pd.notna(drow["atr14"]):
                atr = float(drow["atr14"])
                # atr_edges = [min, q25, q50, q75, max] style cut edges length 5
                try:
                    q = pd.cut([atr], bins=list(atr_edges), labels=["atr_q1", "atr_q2", "atr_q3", "atr_q4"], include_lowest=True)
                    out["atr_q"] = str(q[0]) if pd.notna(q[0]) else "atr_na"
                except Exception:
                    out["atr_q"] = "atr_na"
            if px is not None:
                for mid_col, key, name in (
                    ("prev_week_mid", "week_half_align", "week"),
                    ("prev_day_mid", "day_half_align", "day"),
                ):
                    if mid_col in drow and pd.notna(drow[mid_col]):
                        mid = float(drow[mid_col])
                        half = "lower_half" if px < mid else "upper_half"
                        good = (direction == "long" and half == "lower_half") or (
                            direction == "short" and half == "upper_half"
                        )
                        out[key] = ("%s_aligned" % name) if good else ("%s_opposed" % name)
    return out

def _hp_pass(snap: Dict[str, object], gate: Optional[Tuple[str, object]]) -> bool:
    if gate is None:
        return True
    col, want = gate
    got = snap.get(col)
    if col in ("week_of_month", "hour_ny") and got is not None and want is not None:
        try:
            return int(got) == int(want)
        except Exception:
            return got == want
    return got == want


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
    available_at: pd.Timestamp
    entry_mode: str
    hp_label: str
    signal_day: str
    units_remaining: int = 3
    filled_targets: set = field(default_factory=set)
    best_filled_r: float = 0.0
    runner_r: float = 4.0
    mfe_pts: float = 0.0
    mae_pts: float = 0.0
    last_managed_ts: Optional[pd.Timestamp] = None
    entry_day_idx: int = 0


@dataclass
class PendingSignal:
    direction: str
    available_at: pd.Timestamp
    range_high: float
    range_low: float
    width: float
    range_id: int
    range_idx: int
    range_confirmed_ts: str
    attempt_number: int
    breakout_gap_r: float
    signal_day: str
    signal_day_idx: int
    daily_close: float
    hp_snap: Dict[str, object]


def simulate_1m(
    daily: pd.DataFrame,
    gby: Dict[date, pd.DataFrame],
    *,
    hub: Path,
    market: str,
    entry_mode: str,
    hp_label: str,
    hp_gate: Optional[Tuple[str, object]],
    h1: Optional[pd.DataFrame],
    point_value: float,
    tick_size: float,
    slippage_ticks: int = 1,
    fee_per_unit: float = FEE,
    session_mode: str = "rth",
    hp_feats: Optional[Dict[str, pd.DataFrame]] = None,
    atr_edges: Optional[Sequence[float]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """session_mode: ``rth`` (futures cash close) or ``ny_day`` (FX/metals/CFD daily)."""
    variant = VARIANT
    active: Optional[dict] = None
    range_group_start_idx: Optional[int] = None
    range_group_id = 0
    range_id = 0
    trade_id = 0
    attempts_by_range: Dict[int, int] = {}
    open_trade: Optional[OpenTrade] = None
    pending: Optional[PendingSignal] = None
    trades: List[dict] = []
    unit_exits: List[dict] = []
    equity_rows: List[dict] = []
    realized = 0.0
    peak_mtm = 0.0
    max_mtm_dd = 0.0
    last_flatten_day: Optional[date] = None
    n = len(daily)
    # next_rth on futures/CFD → manage RTH only; FX ny_day next-session → full day
    rth_manage = entry_mode == "close_to_next_rth" and session_mode == "rth"
    next_rth_cash = entry_mode == "close_to_next_rth" and session_mode == "ny_day" and market.lower() in (
        "nas100",
        "us30",
        "spx500",
    )
    if next_rth_cash:
        rth_manage = True
    _progress(
        hub,
        "[%s/%s/%s] Simulating %d daily bars (session=%s) …"
        % (market.upper(), entry_mode, hp_label, n, session_mode),
    )

    def add_exit(ot: OpenTrade, exit_ts: pd.Timestamp, exit_px: float, target_r: float, reason: str) -> None:
        nonlocal realized
        unit_number = 4 - ot.units_remaining
        pts = _points(ot.direction, ot.entry, exit_px)
        net = pts * point_value - fee_per_unit
        unit_exits.append(
            {
                "market": market.upper(),
                "entry_mode": entry_mode,
                "hp_label": hp_label,
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
                "entry_mode": entry_mode,
                "hp_label": hp_label,
                "trade_id": ot.trade_id,
                "direction": ot.direction,
                "range_id": ot.range_id,
                "attempt_number": ot.attempt_number,
                "range_confirmed_ts": ot.range_confirmed_ts,
                "signal_day": ot.signal_day,
                "daily_feature_available_at": ot.available_at.isoformat(),
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

    def manage_bars(ot: OpenTrade, bars: pd.DataFrame, end_ts: Optional[pd.Timestamp] = None) -> Optional[OpenTrade]:
        nonlocal realized, peak_mtm, max_mtm_dd
        cursor = ot.last_managed_ts if ot.last_managed_ts is not None else ot.entry_ts
        if bars is None or bars.empty:
            return ot
        for ts, row in bars.iterrows():
            ts = _localize_ts(ts)
            if ts <= cursor:
                continue
            if end_ts is not None and ts > end_ts:
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
        return ot

    def try_fill_pending(day: date) -> None:
        nonlocal pending, open_trade, trade_id
        if pending is None or open_trade is not None:
            return
        rth_only = entry_mode == "close_to_next_rth" and (session_mode == "rth" or next_rth_cash)
        next_session_only = entry_mode == "close_to_next_rth" and session_mode == "ny_day" and not next_rth_cash
        signal_d = pd.Timestamp(pending.signal_day).date()
        if (rth_only or next_session_only) and day <= signal_d:
            return
        # Search from available_at across calendar days so Fri→Sun Globex is not missed
        # when the daily loop skips non-session dates.
        d0 = pending.available_at.tz_convert(NY).date()
        fill_ts = None
        fill_row = None
        for offset in range(0, 8):
            d = d0 + timedelta(days=offset)
            if (rth_only or next_session_only) and d <= signal_d:
                continue
            if not rth_only and not next_session_only and d > day:
                break
            if (rth_only or next_session_only) and d > day:
                break
            part = _rth_session(gby.get(d), d) if rth_only else _day_frame(gby.get(d), d)
            if part.empty:
                continue
            for ts2, row2 in part.iterrows():
                ts2 = _localize_ts(ts2)
                if ts2 <= pending.available_at:
                    continue
                fill_ts, fill_row = ts2, row2
                break
            if fill_ts is not None:
                break
        if fill_ts is None or fill_row is None:
            return
        entry_px = _entry_price(pending.direction, float(fill_row["open"]), slippage_ticks, tick_size)
        trade_id += 1
        open_trade = OpenTrade(
            trade_id=trade_id,
            direction=pending.direction,
            entry_ts=fill_ts,
            entry=entry_px,
            range_high=float(pending.range_high),
            range_low=float(pending.range_low),
            width=float(pending.width),
            range_id=int(pending.range_id),
            range_idx=int(pending.range_idx),
            range_confirmed_ts=str(pending.range_confirmed_ts),
            attempt_number=int(pending.attempt_number),
            breakout_gap_r=float(pending.breakout_gap_r),
            available_at=pending.available_at,
            entry_mode=entry_mode,
            hp_label=hp_label,
            signal_day=pending.signal_day,
            runner_r=float(variant.runner_r),
            last_managed_ts=fill_ts,
            entry_day_idx=int(pending.signal_day_idx),
        )
        pending = None

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

        # Fill pending before managing (entry bar may be today's open).
        try_fill_pending(day)

        # Manage open trade on today's bars.
        if open_trade is not None:
            bars = _rth_session(gby.get(day), day) if rth_manage else _day_frame(gby.get(day), day)
            open_trade = manage_bars(open_trade, bars)
            if open_trade is None:
                last_flatten_day = day

        # After session close is known: may create a new pending signal.
        avail_ts, _ = _last_avail_bar(gby, day, session_mode=session_mode)
        if (
            open_trade is None
            and pending is None
            and active is not None
            and i > active["range_idx"]
            and last_flatten_day != day
            and avail_ts is not None
        ):
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
                    rth_only = entry_mode == "close_to_next_rth"
                    ets, _, _ = _first_bar_after(gby, avail_ts, rth_only=rth_only)
                    hour_ny = int(ets.tz_convert(NY).hour) if ets is not None else None
                    snap = _hp_at(
                        avail_ts,
                        direction,
                        h1,
                        hp_feats=hp_feats,
                        signal_price=float(close),
                        atr_edges=atr_edges,
                        hour_ny=hour_ny,
                    )
                    if not _hp_pass(snap, hp_gate):
                        direction = ""
                    else:
                        attempts_by_range[active["range_id"]] = attempts
                        pending = PendingSignal(
                            direction=direction,
                            available_at=avail_ts,
                            range_high=float(active["range_high"]),
                            range_low=float(active["range_low"]),
                            width=float(active["width"]),
                            range_id=int(active["range_id"]),
                            range_idx=int(active["range_idx"]),
                            range_confirmed_ts=str(active["range_confirmed_ts"]),
                            attempt_number=attempts,
                            breakout_gap_r=float(gap_r),
                            signal_day=date_s,
                            signal_day_idx=i,
                            daily_close=close,
                            hp_snap=snap,
                        )
                        # Same-day Globex fill can happen after available_at today.
                        if entry_mode == "close_to_globex":
                            try_fill_pending(day)
                            if open_trade is not None:
                                # Manage remaining post-entry bars today.
                                bars = _day_frame(gby.get(day), day)
                                open_trade = manage_bars(open_trade, bars)
                                if open_trade is None:
                                    last_flatten_day = day

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
                "  [%s/%s/%s] daily %d/%d trades=%d realized=$%+.0f"
                % (market.upper(), entry_mode, hp_label, i + 1, n, trade_id, realized),
            )

    if open_trade is not None and open_trade.units_remaining > 0:
        last_day = pd.Timestamp(daily.iloc[-1]["date"]).tz_localize(None).date()
        bars = _rth_session(gby.get(last_day), last_day) if rth_manage else _day_frame(gby.get(last_day), last_day)
        if not bars.empty:
            ts = _localize_ts(bars.index[-1])
            px = _exit_price(open_trade.direction, float(bars.iloc[-1]["close"]), slippage_ticks, tick_size)
            while open_trade.units_remaining > 0:
                add_exit(open_trade, ts, px, 0.0, "data_end")
            close_trade_record(open_trade, ts)

    equity = pd.DataFrame(equity_rows)
    if not equity.empty:
        equity["closed_drawdown"] = equity["closed_equity"] - equity["closed_equity"].cummax()
        equity["mtm_drawdown"] = equity["mtm_equity"] - equity["mtm_equity"].cummax()
        equity.attrs["max_mtm_dd_1m_path"] = float(max_mtm_dd)
    return pd.DataFrame(trades), pd.DataFrame(unit_exits), equity


def _summarize(market: str, entry_mode: str, hp_label: str, trades: pd.DataFrame, exits: pd.DataFrame, equity: pd.DataFrame) -> dict:
    net = float(trades["net_usd"].sum()) if not trades.empty else 0.0
    closed_dd = float(equity["closed_drawdown"].min()) if not equity.empty else 0.0
    mtm_dd = float(equity["mtm_drawdown"].min()) if not equity.empty else 0.0
    ns = (net / abs(mtm_dd)) if mtm_dd else 0.0
    wins = trades[trades["net_usd"] > 0] if not trades.empty else trades
    wr = (100.0 * len(wins) / len(trades)) if len(trades) else 0.0
    causal_ok = 0
    if not trades.empty and "daily_feature_available_at" in trades.columns:
        for _, t in trades.iterrows():
            aa = pd.to_datetime(t["daily_feature_available_at"], utc=True)
            et = pd.to_datetime(t["entry_ts"], utc=True)
            if aa < et:
                causal_ok += 1
    return {
        "market": market.upper(),
        "entry_mode": entry_mode,
        "hp_label": hp_label,
        "variant": VARIANT.name,
        "trades": int(len(trades)),
        "units": int(len(exits)),
        "net_usd": net,
        "closed_drawdown": closed_dd,
        "mtm_drawdown": mtm_dd,
        "net_stress": ns,
        "win_rate": wr,
        "causal_available_before_entry": causal_ok,
        "long_net": float(trades.loc[trades.direction == "long", "net_usd"].sum()) if not trades.empty else 0.0,
        "short_net": float(trades.loc[trades.direction == "short", "net_usd"].sum()) if not trades.empty else 0.0,
        "avg_trade": float(trades["net_usd"].mean()) if not trades.empty else 0.0,
    }


def _hp_specs_for_market(market: str) -> List[Tuple[str, Optional[Tuple[str, object]], str]]:
    m = market.lower()
    out = []
    for label, gate, note in HP_SPECS:
        if label == "baseline":
            out.append((label, gate, note))
        elif label == "hp_wom3" and m == "mnq":
            out.append((label, gate, note))
        elif label in ("hp_rsi_with_side", "hp_rsi_gt70") and m == "nq":
            out.append((label, gate, note))
    return out


def run_market(market: str, hub: Path, *, smoke: bool) -> List[dict]:
    m = market.lower()
    summaries: List[dict] = []
    _progress(hub, "Loading %s daily + CHOP20 …" % m.upper())
    daily = build_daily_signal_frame(m)
    cfg = MARKETS[m]
    if cfg.start is not None:
        daily = daily[pd.to_datetime(daily["date"]).dt.date >= cfg.start].reset_index(drop=True)
    if smoke:
        daily = daily.tail(400).reset_index(drop=True)
    _progress(
        hub,
        "  %s daily bars=%d (%s → %s)"
        % (m.upper(), len(daily), _date_s(daily.iloc[0]["date"]), _date_s(daily.iloc[-1]["date"])),
    )
    _progress(hub, "Loading %s 1m …" % m.upper())
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), m)
    if smoke:
        keep = set(pd.to_datetime(daily["date"]).dt.date.tolist())
        # also keep a few days after last signal for next-RTH fills
        last = max(keep)
        for i in range(1, 8):
            keep.add(last + timedelta(days=i))
        gby = {d: v for d, v in gby.items() if d in keep or any(abs((d - x).days) <= 5 for x in keep)}
    _progress(hub, "  %s 1m sessions=%d" % (m.upper(), len(gby)))
    _progress(hub, "Loading %s hourly HP features …" % m.upper())
    h1 = _load_hourly_feat(m)

    for entry_mode in ENTRY_MODES:
        for hp_label, hp_gate, _note in _hp_specs_for_market(m):
            slug = "%s__%s__%s" % (m, entry_mode, hp_label)
            out = hub / slug
            out.mkdir(parents=True, exist_ok=True)
            rid = begin_run(
                run_class="pandas",
                variant_slug=slug,
                instrument=m.upper(),
                hub_path=str(out.relative_to(REPO)),
                dsr_trial_id=DSR,
                meta={
                    "entry_mode": entry_mode,
                    "hp_label": hp_label,
                    "fill_tape": "1m",
                    "same_bar": "stop_first",
                },
            )
            try:
                trades, exits, equity = simulate_1m(
                    daily,
                    gby,
                    hub=hub,
                    market=m,
                    entry_mode=entry_mode,
                    hp_label=hp_label,
                    hp_gate=hp_gate,
                    h1=h1,
                    point_value=POINT_VALUES[m],
                    tick_size=TICK_SIZES[m],
                )
                summary = _summarize(m, entry_mode, hp_label, trades, exits, equity)
                trades.to_csv(out / "trades.csv", index=False)
                exits.to_csv(out / "unit_exits.csv", index=False)
                equity.to_csv(out / "equity_curve.csv", index=False)
                pd.DataFrame([summary]).to_csv(out / "summary.csv", index=False)
                complete_run(
                    rid,
                    net_usd=summary["net_usd"],
                    stress_dd_usd=summary["mtm_drawdown"],
                    close_mtm_dd_usd=summary["closed_drawdown"],
                    ns=summary["net_stress"],
                    trades=summary["trades"],
                    units=summary["units"],
                    equity_curve_path=out / "equity_curve.csv",
                    notes="causal entry + HP gate 1m path",
                    meta=summary,
                )
                summaries.append(summary)
                _progress(
                    hub,
                    "DONE %s net=$%+.0f N/S=%.2f trades=%d causal=%d/%d"
                    % (
                        slug,
                        summary["net_usd"],
                        summary["net_stress"],
                        summary["trades"],
                        summary["causal_available_before_entry"],
                        summary["trades"],
                    ),
                )
            except Exception:
                err = traceback.format_exc()
                fail_run(rid, notes=err[-1500:])
                raise
    return summaries


def _write_summary(hub: Path, rows: List[dict], *, smoke: bool) -> str:
    board = pd.DataFrame(rows)
    board.to_csv(hub / "summary_board.csv", index=False)
    # Reference non-causal same-day board if present
    legacy = REPO / "live" / "state" / "chop20_dynamic_range_1m_boundary60_xmarket" / "summary_board.csv"
    lines = [
        "# CHOP20 boundary60 — Causal entry variants + HP gates",
        "",
        "Generated: %s" % datetime.now().isoformat(timespec="seconds"),
        "Smoke: %s" % smoke,
        "DSR: %s" % DSR,
        "",
        "## Contract",
        "",
        "- Daily CHOP20 + close breakout = **signal only**; `available_at` = last RTH 1m.",
        "- **close_to_globex**: first 1m bar with `ts > available_at` (post-close / Globex).",
        "- **close_to_next_rth**: first RTH minute of the next session.",
        "- Fill = entry-bar **open** ±1 tick adverse; stop-first 1m management.",
        "- Same stop/targets/age as boundary60 structure.",
        "- HP gates filter at signal time (no size-up).",
        "",
        "## Board",
        "",
        "| market | entry_mode | hp | trades | net | MTM DD | N/S | WR | causal |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in board.sort_values(["market", "entry_mode", "hp_label"]).iterrows():
        lines.append(
            "| %s | %s | %s | %d | $%+.0f | $%+.0f | %.2f | %.0f%% | %d/%d |"
            % (
                r["market"],
                r["entry_mode"],
                r["hp_label"],
                int(r["trades"]),
                float(r["net_usd"]),
                float(r["mtm_drawdown"]),
                float(r["net_stress"]),
                float(r["win_rate"]),
                int(r["causal_available_before_entry"]),
                int(r["trades"]),
            )
        )
    # Stance
    base = board[board["hp_label"] == "baseline"] if not board.empty else board
    lines += ["", "## Stance", ""]
    if not base.empty:
        for _, r in base.iterrows():
            ok = int(r["causal_available_before_entry"]) == int(r["trades"]) and int(r["trades"]) > 0
            lines.append(
                "- **%s / %s baseline**: net=$%+.0f N/S=%.2f n=%d — timing %s"
                % (
                    r["market"],
                    r["entry_mode"],
                    float(r["net_usd"]),
                    float(r["net_stress"]),
                    int(r["trades"]),
                    "PASS (available_at < entry)" if ok else "FAIL/empty",
                )
            )
    hp = board[board["hp_label"] != "baseline"] if not board.empty else board
    if not hp.empty:
        lines.append("- **HP filters**: compare ΔN/S / Δnet vs same-market baseline; thin N → research only.")
        for _, r in hp.iterrows():
            b = base[(base["market"] == r["market"]) & (base["entry_mode"] == r["entry_mode"])]
            if b.empty:
                continue
            b0 = b.iloc[0]
            dns = float(r["net_stress"]) - float(b0["net_stress"])
            dnet = float(r["net_usd"]) - float(b0["net_usd"])
            lines.append(
                "  - %s / %s / %s: ΔN/S=%+.2f Δnet=$%+.0f (n=%d vs %d)"
                % (
                    r["market"],
                    r["entry_mode"],
                    r["hp_label"],
                    dns,
                    dnet,
                    int(r["trades"]),
                    int(b0["trades"]),
                )
            )
    lines += [
        "",
        "- **HA size-ups**: not run — descriptive research only; no live gate.",
        "- **Same-day last-RTH fill**: retired for promotion; kept only as prior diagnostic.",
        "- **StrategyPlugin port**: only after choosing one causal entry mode.",
        "",
    ]
    if legacy.exists():
        lines += ["## Prior non-causal same-day board (reference)", "", "```", legacy.read_text()[:800], "```", ""]
    lines += ["Hub: `%s`" % hub, ""]
    text = "\n".join(lines)
    (hub / "SUMMARY.md").write_text(text)
    (hub / "EMAIL.txt").write_text(text)
    return text


def run(*, markets: Sequence[str], email: bool, smoke: bool) -> pd.DataFrame:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="pandas",
        variant_slug="chop20_causal_entry_hp_board",
        instrument="MULTI",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="causal entry variants running",
    )
    try:
        rows: List[dict] = []
        for m in markets:
            rows.extend(run_market(m, HUB, smoke=smoke))
        text = _write_summary(HUB, rows, smoke=smoke)
        board = pd.DataFrame(rows)
        net = float(board["net_usd"].sum()) if not board.empty else 0.0
        complete_run(
            rid,
            net_usd=net,
            trades=int(board["trades"].sum()) if not board.empty else 0,
            notes="causal entry + HP board complete",
            meta={"smoke": smoke, "markets": list(markets)},
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(
                subject="potions: CHOP20 causal entry + HP %s" % ("smoke" if smoke else "complete"),
                body=text,
            )
        return board
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-1500:])
        _mark_dsr("FAILED")
        if email:
            send_email(
                subject="potions: CHOP20 causal entry FAILED",
                body=err[-4000:],
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--markets", default="nq,mnq", help="comma markets")
    args = p.parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    run(markets=markets, email=args.email, smoke=args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
