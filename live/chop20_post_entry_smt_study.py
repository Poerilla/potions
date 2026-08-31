"""Post-entry NAS100 ↔ SPX500 CHOP20 peer-confirmation (SMT-style) event study.

Descriptive + locked-horizon classification + causal forward tables + one
frozen counterfactual action set. Not an entry filter.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_post_entry_smt_study --email
  python -m live.chop20_post_entry_smt_study --email --smoke
  python -m live.chop20_post_entry_smt_study --email --primary nas100 --peer spx500
  python -m live.chop20_post_entry_smt_study --email --both-directions
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run, log_run

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path[:0] = [str(SCRIPTS)]

from chop_range_breakout_charts import DetectorParams, add_range_metrics, load_bars  # noqa: E402

NY = pytz.timezone("America/New_York")
HUB = REPO / "live" / "state" / "chop20_post_entry_smt_nas100_spx500"
SOURCE = REPO / "live" / "state" / "chop20_dynamic_range_causal_entry_fx_metals"
DSR = "TRL-2026-00185"

FAST_CONFIRM_MINS = 5
LATE_CONFIRM_MINS = 30
MAX_OBSERVATION_MINS = 60

STATES = (
    "ALREADY_CONFIRMED",
    "CONFIRMS_FAST",
    "CONFIRMS_LATE",
    "NO_CONFIRM",
    "OPPOSITE_BREAK",
    "PEER_LEVEL_UNAVAILABLE",
)

MARKET_PATHS = {
    "nas100": {
        "symbol": "NAS100",
        "daily": REPO / "fx" / "nas100_daily.csv",
        "one_m": REPO / "fx" / "nas100_1m.csv",
        "point_value": 1.0,
        "tick": 0.1,
    },
    "spx500": {
        "symbol": "SPX500",
        "daily": REPO / "fx" / "spx500_daily.csv",
        "one_m": REPO / "fx" / "spx500_1m.csv",
        "point_value": 1.0,
        "tick": 0.1,
    },
}


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
            "trial_subclass": "chop20_post_entry_smt",
            "is_independent": "TRUE",
            "market": "NAS100,SPX500",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "fast_mins": FAST_CONFIRM_MINS,
                    "late_mins": LATE_CONFIRM_MINS,
                    "max_obs_mins": MAX_OBSERVATION_MINS,
                    "level_family": "CHOP20",
                    "primary_default": "NAS100",
                    "peer_default": "SPX500",
                    "entry_mode": "close_to_globex",
                    "actions": [
                        "baseline",
                        "suppress_adds_after_30m_no_confirm",
                        "flatten_after_opposite",
                        "tighten_stop_after_opposite",
                    ],
                }
            ),
            "fixed_parameters_ref": "live/chop20_post_entry_smt_study.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Post-entry peer confirmation event study; descriptive then frozen actions",
        }
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(",".join(str(row.get(f, "")) for f in fields) + "\n")


def _mark_dsr(status: str = "COMPLETE") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    out = []
    for ln in lines:
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _ts(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return NY.localize(ts.to_pydatetime().replace(tzinfo=None))
    return ts.tz_convert(NY)


def _minutes_between(a: pd.Timestamp, b: pd.Timestamp) -> float:
    return (b - a).total_seconds() / 60.0


@dataclass
class Tape1m:
    ts: np.ndarray  # datetime64[ns, tz] as int64 ns UTC for searchsorted
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    ts_index: pd.DatetimeIndex

    @classmethod
    def from_gby(cls, gby: Dict[date, pd.DataFrame], start: date, end: date) -> "Tape1m":
        frames = []
        d = start
        while d <= end:
            part = gby.get(d)
            if part is not None and not part.empty:
                frames.append(part)
            d += timedelta(days=1)
        if not frames:
            empty = pd.DatetimeIndex([], tz=NY)
            z = np.array([], dtype=float)
            return cls(ts=np.array([], dtype="datetime64[ns]"), open=z, high=z, low=z, close=z, ts_index=empty)
        df = pd.concat(frames).sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize(NY)
        else:
            df.index = df.index.tz_convert(NY)
        return cls(
            ts=df.index.asi8,
            open=df["open"].to_numpy(dtype=float),
            high=df["high"].to_numpy(dtype=float),
            low=df["low"].to_numpy(dtype=float),
            close=df["close"].to_numpy(dtype=float),
            ts_index=df.index,
        )

    @staticmethod
    def _key_ns(t: pd.Timestamp) -> int:
        return int(pd.Timestamp(t).tz_convert("UTC").value)

    def iat_or_before(self, t: pd.Timestamp) -> int:
        if len(self.ts) == 0:
            return -1
        return int(np.searchsorted(self.ts, self._key_ns(t), side="right") - 1)

    def iat_after(self, t: pd.Timestamp) -> int:
        if len(self.ts) == 0:
            return 0
        return int(np.searchsorted(self.ts, self._key_ns(t), side="right"))

    def price_at(self, t: pd.Timestamp) -> Optional[float]:
        i = self.iat_or_before(t)
        if i < 0:
            return None
        return float(self.close[i])

    def first_cross(
        self,
        *,
        level: float,
        side: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> Optional[pd.Timestamp]:
        """First completed 1m bar in (start, end] that crosses level in ``side``."""
        i0 = self.iat_after(start)
        i1 = self.iat_or_before(end)
        if i0 < 0 or i1 < i0 or i0 >= len(self.ts):
            return None
        if side == "long":
            for i in range(i0, i1 + 1):
                if self.high[i] >= level:
                    return self.ts_index[i]
        else:
            for i in range(i0, i1 + 1):
                if self.low[i] <= level:
                    return self.ts_index[i]
        return None


def build_daily_levels(market_key: str) -> pd.DataFrame:
    cfg = MARKET_PATHS[market_key]
    daily = add_range_metrics(load_bars(cfg["daily"], "D"), DetectorParams())
    daily = daily.reset_index(drop=True)
    active_high = np.nan
    active_low = np.nan
    active_width = np.nan
    active_age = np.nan
    active_confirmed = ""
    active_idx = -1
    rows = []
    for i, row in daily.iterrows():
        i = int(i)
        day = pd.Timestamp(row["date"]).tz_localize(None).date()
        if bool(row["is_range_like"]):
            active_high = float(row["range_high_20"])
            active_low = float(row["range_low_20"])
            active_width = float(row["range_20"])
            active_confirmed = str(pd.Timestamp(row["date"]).date())
            active_idx = i
            active_age = 0.0
        elif active_idx >= 0:
            active_age = float(i - active_idx)
        # Daily features for day D known at last 1m of day D (approx 23:59 NY).
        avail = NY.localize(datetime(day.year, day.month, day.day, 23, 59))
        rows.append(
            {
                "date": day,
                "available_at": avail,
                "close": float(row["close"]),
                "atr_20": float(row["atr_20"]) if pd.notna(row["atr_20"]) else np.nan,
                "is_range_like": bool(row["is_range_like"]),
                # Contemporaneous CHOP20 window (preferred peer threshold).
                "range_high_20": float(row["range_high_20"]) if pd.notna(row["range_high_20"]) else np.nan,
                "range_low_20": float(row["range_low_20"]) if pd.notna(row["range_low_20"]) else np.nan,
                "range_20": float(row["range_20"]) if pd.notna(row["range_20"]) else np.nan,
                # Last range-like active (diagnostic / strategy-mirrored).
                "active_range_high": active_high,
                "active_range_low": active_low,
                "active_range_width": active_width,
                "active_range_age": active_age,
                "active_range_confirmed": active_confirmed,
            }
        )
    return pd.DataFrame(rows)


def freeze_peer_levels(peer_daily: pd.DataFrame, t0: pd.Timestamp) -> Optional[dict]:
    """Peer CHOP20 rolling window frozen at last daily bar known *before* t0's day.

    Uses prior-day ``range_high_20`` / ``range_low_20`` so the same-day peer
    extremes cannot auto-confirm the break. Levels are fixed at primary break.
    """
    known = peer_daily[peer_daily["available_at"] <= t0]
    if len(known) < 2:
        return None
    # Prior completed daily bar (not the signal-day bar itself).
    row = known.iloc[-2]
    if not np.isfinite(row["range_high_20"]) or not np.isfinite(row["range_low_20"]):
        return None
    if not np.isfinite(row["range_20"]) or float(row["range_20"]) <= 0:
        return None
    return {
        "peer_reference_type": "CHOP20_rolling_range_20_prior_day",
        "peer_range_high": float(row["range_high_20"]),
        "peer_range_low": float(row["range_low_20"]),
        "peer_range_width": float(row["range_20"]),
        "peer_range_age": float(row["active_range_age"]) if np.isfinite(row["active_range_age"]) else np.nan,
        "peer_range_confirmed": str(row["active_range_confirmed"]),
        "peer_is_range_like": bool(row["is_range_like"]),
        "peer_atr_20": float(row["atr_20"]) if np.isfinite(row["atr_20"]) else np.nan,
        "peer_daily_asof": row["date"],
        "peer_close_asof_daily": float(row["close"]),
    }


def classify(
    *,
    side: str,
    t0: pd.Timestamp,
    exit_ts: pd.Timestamp,
    session_start: pd.Timestamp,
    peer_levels: Optional[dict],
    peer_tape: Tape1m,
) -> dict:
    out = {
        "confirmation_class": "PEER_LEVEL_UNAVAILABLE",
        "peer_break_level_same_direction": np.nan,
        "peer_break_level_opposite_direction": np.nan,
        "peer_state_at_primary_break": "UNAVAILABLE",
        "peer_same_direction_break_ts": "",
        "peer_opposite_direction_break_ts": "",
        "peer_delay_minutes": np.nan,
        "peer_normalized_distance_to_same_break": np.nan,
        "peer_normalized_distance_to_opposite_break": np.nan,
        "peer_distance_range_frac": np.nan,
        "peer_price_at_t0": np.nan,
    }
    if peer_levels is None:
        return out

    same_lvl = peer_levels["peer_range_high"] if side == "long" else peer_levels["peer_range_low"]
    opp_lvl = peer_levels["peer_range_low"] if side == "long" else peer_levels["peer_range_high"]
    out["peer_break_level_same_direction"] = same_lvl
    out["peer_break_level_opposite_direction"] = opp_lvl

    px = peer_tape.price_at(t0)
    out["peer_price_at_t0"] = px if px is not None else np.nan
    atr = peer_levels["peer_atr_20"]
    width = peer_levels["peer_range_width"]
    if px is not None and np.isfinite(atr) and atr > 0:
        # Positive ⇒ not yet confirmed.
        if side == "long":
            out["peer_normalized_distance_to_same_break"] = (same_lvl - px) / atr
            out["peer_normalized_distance_to_opposite_break"] = (px - opp_lvl) / atr
            out["peer_distance_range_frac"] = (same_lvl - px) / width
        else:
            out["peer_normalized_distance_to_same_break"] = (px - same_lvl) / atr
            out["peer_normalized_distance_to_opposite_break"] = (opp_lvl - px) / atr
            out["peer_distance_range_frac"] = (px - same_lvl) / width

    already = peer_tape.first_cross(level=same_lvl, side=side, start=session_start - timedelta(minutes=1), end=t0)
    # If peer price is already beyond the level at t0, treat as confirmed even
    # when no fresh cross prints inside today's session window.
    if already is None and px is not None:
        if side == "long" and px >= same_lvl:
            already = t0
        elif side == "short" and px <= same_lvl:
            already = t0
    if already is not None:
        out["confirmation_class"] = "ALREADY_CONFIRMED"
        out["peer_state_at_primary_break"] = "ALREADY_CONFIRMED"
        out["peer_same_direction_break_ts"] = already.isoformat()
        out["peer_delay_minutes"] = _minutes_between(t0, already)  # ≤0
        return out

    out["peer_state_at_primary_break"] = "UNCONFIRMED"
    obs_end = min(exit_ts, t0 + timedelta(minutes=MAX_OBSERVATION_MINS))
    same_after = peer_tape.first_cross(level=same_lvl, side=side, start=t0, end=obs_end)
    opp_side = "short" if side == "long" else "long"
    opp_after = peer_tape.first_cross(level=opp_lvl, side=opp_side, start=t0, end=obs_end)

    if same_after is not None:
        out["peer_same_direction_break_ts"] = same_after.isoformat()
        out["peer_delay_minutes"] = _minutes_between(t0, same_after)
    if opp_after is not None:
        out["peer_opposite_direction_break_ts"] = opp_after.isoformat()

    if opp_after is not None and (same_after is None or opp_after < same_after):
        out["confirmation_class"] = "OPPOSITE_BREAK"
        return out

    if same_after is not None:
        delay = out["peer_delay_minutes"]
        if delay <= FAST_CONFIRM_MINS:
            out["confirmation_class"] = "CONFIRMS_FAST"
        elif delay <= LATE_CONFIRM_MINS:
            out["confirmation_class"] = "CONFIRMS_LATE"
        else:
            out["confirmation_class"] = "NO_CONFIRM"
        return out

    out["confirmation_class"] = "NO_CONFIRM"
    return out


def state_asof(
    *,
    side: str,
    t0: pd.Timestamp,
    decision_ts: pd.Timestamp,
    session_start: pd.Timestamp,
    peer_levels: Optional[dict],
    peer_tape: Tape1m,
) -> str:
    """Peer state knowable at ``decision_ts`` (completed bars only)."""
    if peer_levels is None:
        return "PEER_LEVEL_UNAVAILABLE"
    if decision_ts < t0:
        return "TOO_EARLY"
    same_lvl = peer_levels["peer_range_high"] if side == "long" else peer_levels["peer_range_low"]
    opp_lvl = peer_levels["peer_range_low"] if side == "long" else peer_levels["peer_range_high"]
    already = peer_tape.first_cross(level=same_lvl, side=side, start=session_start - timedelta(minutes=1), end=t0)
    if already is None:
        px = peer_tape.price_at(t0)
        if px is not None:
            if side == "long" and px >= same_lvl:
                already = t0
            elif side == "short" and px <= same_lvl:
                already = t0
    if already is not None:
        return "ALREADY_CONFIRMED"
    obs_end = min(decision_ts, t0 + timedelta(minutes=MAX_OBSERVATION_MINS))
    same_after = peer_tape.first_cross(level=same_lvl, side=side, start=t0, end=obs_end)
    opp_side = "short" if side == "long" else "long"
    opp_after = peer_tape.first_cross(level=opp_lvl, side=opp_side, start=t0, end=obs_end)
    if opp_after is not None and (same_after is None or opp_after < same_after):
        return "OPPOSITE_BREAK"
    if same_after is not None:
        delay = _minutes_between(t0, same_after)
        if delay <= FAST_CONFIRM_MINS:
            return "CONFIRMS_FAST"
        if delay <= LATE_CONFIRM_MINS:
            return "CONFIRMS_LATE"
        return "NO_CONFIRM"
    # Deadline not reached yet → still pending, treat as provisional NO_CONFIRM for table.
    if decision_ts < t0 + timedelta(minutes=LATE_CONFIRM_MINS):
        return "PENDING_UNCONFIRMED"
    return "NO_CONFIRM"


def load_campaigns(primary: str, entry_mode: str = "close_to_globex") -> Tuple[pd.DataFrame, pd.DataFrame]:
    slug = "%s__%s__baseline" % (primary, entry_mode)
    trades = pd.read_csv(SOURCE / slug / "trades.csv")
    exits = pd.read_csv(SOURCE / slug / "unit_exits.csv")
    return trades, exits


def campaign_outcome_flags(exits: pd.DataFrame, trade_id: int) -> dict:
    part = exits[exits["trade_id"] == trade_id]
    reasons = set(part["reason"].astype(str))
    stop = any(r.startswith("stop_") for r in reasons)
    return {
        "primary_stop_flag": int(stop),
        "primary_tp_0_5_flag": int("tp_0_5r" in reasons),
        "primary_tp_1_flag": int("tp_1r" in reasons),
        "primary_tp_4_flag": int("tp_4r" in reasons or "tp_4_0r" in reasons),
        "units": int(len(part)),
        "winning_units": int((part["net_usd"] > 0).sum()),
    }


def forward_from_decision(
    *,
    trade: pd.Series,
    exits: pd.DataFrame,
    decision_ts: pd.Timestamp,
    primary_tape: Tape1m,
) -> dict:
    """Forward outcomes from decision_ts among residual units (causal)."""
    tid = int(trade["trade_id"])
    side = str(trade["direction"])
    width = float(trade["range_width_r"])
    entry = float(trade["entry"])
    exit_ts = _ts(trade["exit_ts"])
    part = exits[exits["trade_id"] == tid].copy()
    part["exit_ts"] = part["exit_ts"].map(_ts)
    still = part[part["exit_ts"] > decision_ts]
    already_stopped = bool(
        ((part["exit_ts"] <= decision_ts) & part["reason"].astype(str).str.startswith("stop_")).any()
    )
    if exit_ts <= decision_ts or already_stopped or still.empty:
        return {
            "open_at_decision": 0,
            "forward_stop": np.nan,
            "forward_net_usd": np.nan,
            "forward_net_R": np.nan,
            "forward_mfe_R": np.nan,
            "forward_mae_R": np.nan,
            "residual_units": 0,
        }

    # Mark-to-market reference at decision close.
    px0 = primary_tape.price_at(decision_ts)
    if px0 is None:
        px0 = entry

    # Path MFE/MAE from decision to final residual exits (price vs decision mark).
    i0 = primary_tape.iat_after(decision_ts)
    i1 = primary_tape.iat_or_before(exit_ts)
    mfe = 0.0
    mae = 0.0
    if i0 >= 0 and i1 >= i0:
        if side == "long":
            mfe = float(np.max(primary_tape.high[i0 : i1 + 1]) - px0)
            mae = float(np.min(primary_tape.low[i0 : i1 + 1]) - px0)
        else:
            mfe = float(px0 - np.min(primary_tape.low[i0 : i1 + 1]))
            mae = float(px0 - np.max(primary_tape.high[i0 : i1 + 1]))

    # Forward $: residual unit nets, but adjust by MTM already earned to decision
    # so we credit only incremental PnL after decision. Approx: sum residual nets
    # minus mark-to-market of those units from entry→decision.
    fwd_usd = 0.0
    pv = 1.0
    for _, u in still.iterrows():
        pts_full = float(u["points"])
        pts_to_dec = (px0 - entry) if side == "long" else (entry - px0)
        fwd_usd += (pts_full - pts_to_dec) * pv - 0.0  # fee already in historical; leave as-is incremental pts

    stop_fwd = int(any(str(r).startswith("stop_") for r in still["reason"]))
    return {
        "open_at_decision": 1,
        "forward_stop": stop_fwd,
        "forward_net_usd": fwd_usd,
        "forward_net_R": fwd_usd / width if width > 0 else np.nan,
        "forward_mfe_R": mfe / width if width > 0 else np.nan,
        "forward_mae_R": mae / width if width > 0 else np.nan,
        "residual_units": int(len(still)),
    }


def simulate_actions(
    *,
    trade: pd.Series,
    exits: pd.DataFrame,
    t0: pd.Timestamp,
    class_row: dict,
    peer_levels: Optional[dict],
    peer_tape: Tape1m,
    primary_tape: Tape1m,
    session_start: pd.Timestamp,
) -> dict:
    """Counterfactual residual management (causal timestamps)."""
    tid = int(trade["trade_id"])
    side = str(trade["direction"])
    width = float(trade["range_width_r"])
    entry = float(trade["entry"])
    entry_ts = _ts(trade["entry_ts"])
    exit_ts = _ts(trade["exit_ts"])
    part = exits[exits["trade_id"] == tid].copy()
    part["exit_ts"] = part["exit_ts"].map(_ts)
    baseline_net = float(part["net_usd"].sum())

    def flatten_at(ts_fill: pd.Timestamp, keep_unit_numbers: Optional[set] = None) -> float:
        """Replay residual exits: units exiting after ts_fill get flattened at ts_fill open."""
        keep_unit_numbers = keep_unit_numbers or set()
        i = primary_tape.iat_after(ts_fill - timedelta(seconds=1))
        if i < 0 or i >= len(primary_tape.ts):
            return baseline_net
        # Next executable minute after state observation: use that bar open.
        fill_px = float(primary_tape.open[i])
        total = 0.0
        for _, u in part.iterrows():
            un = int(u["unit_number"])
            if un in keep_unit_numbers or u["exit_ts"] <= ts_fill:
                total += float(u["net_usd"])
                continue
            pts = (fill_px - entry) if side == "long" else (entry - fill_px)
            total += pts * 1.0 - 1.50
        return total

    # 1) Suppress adds after 30m no-confirm: keep unit 1 only if still open & unconfirmed.
    no_add_net = baseline_net
    decision_30 = t0 + timedelta(minutes=LATE_CONFIRM_MINS)
    st30 = state_asof(
        side=side,
        t0=t0,
        decision_ts=decision_30,
        session_start=session_start,
        peer_levels=peer_levels,
        peer_tape=peer_tape,
    )
    if exit_ts > decision_30 and st30 in ("NO_CONFIRM", "PENDING_UNCONFIRMED", "OPPOSITE_BREAK"):
        # Observe at bar close decision_30 → act next minute.
        act = decision_30 + timedelta(minutes=1)
        no_add_net = flatten_at(act, keep_unit_numbers={1})

    # 2) Flatten after opposite break.
    flat_opp_net = baseline_net
    opp_ts_s = class_row.get("peer_opposite_direction_break_ts") or ""
    if class_row.get("confirmation_class") == "OPPOSITE_BREAK" and opp_ts_s:
        opp_ts = _ts(opp_ts_s)
        act = opp_ts + timedelta(minutes=1)
        if act < exit_ts:
            flat_opp_net = flatten_at(act, keep_unit_numbers=set())

    # 3) Tighten stop to entry after opposite (approx: if residual MAE after act hits entry, flatten then).
    tight_net = baseline_net
    if class_row.get("confirmation_class") == "OPPOSITE_BREAK" and opp_ts_s:
        opp_ts = _ts(opp_ts_s)
        act = opp_ts + timedelta(minutes=1)
        if act < exit_ts:
            i0 = primary_tape.iat_after(act - timedelta(seconds=1))
            i1 = primary_tape.iat_or_before(exit_ts)
            stop_hit_i = None
            if i0 >= 0 and i1 >= i0:
                for i in range(i0, i1 + 1):
                    if side == "long" and primary_tape.low[i] <= entry:
                        stop_hit_i = i
                        break
                    if side == "short" and primary_tape.high[i] >= entry:
                        stop_hit_i = i
                        break
            if stop_hit_i is not None:
                fill_ts = primary_tape.ts_index[stop_hit_i]
                tight_net = flatten_at(fill_ts, keep_unit_numbers=set())
            # else unchanged path (never tagged entry)

    return {
        "baseline_net_usd": baseline_net,
        "baseline_net_R": baseline_net / width if width > 0 else np.nan,
        "no_add_30m_net_usd": no_add_net,
        "no_add_30m_net_R": no_add_net / width if width > 0 else np.nan,
        "flatten_opposite_net_usd": flat_opp_net,
        "flatten_opposite_net_R": flat_opp_net / width if width > 0 else np.nan,
        "tighten_opposite_net_usd": tight_net,
        "tighten_opposite_net_R": tight_net / width if width > 0 else np.nan,
        "state_at_30m": st30,
        "entry_ts": entry_ts.isoformat(),
    }


def run_pair(
    hub: Path,
    *,
    primary: str,
    peer: str,
    entry_mode: str,
    smoke: bool,
    primary_gby: Dict[date, pd.DataFrame],
    peer_gby: Dict[date, pd.DataFrame],
    peer_daily: pd.DataFrame,
) -> pd.DataFrame:
    trades, exits = load_campaigns(primary, entry_mode)
    if smoke:
        # Recent campaigns so truncated 1m windows still cover the path.
        trades = trades.tail(12).copy()
    _progress(hub, "Pair %s→%s campaigns=%d" % (primary.upper(), peer.upper(), len(trades)))

    events = []
    cond_rows = []
    action_rows = []

    for _, tr in trades.iterrows():
        side = str(tr["direction"])
        entry_ts = _ts(tr["entry_ts"])
        exit_ts = _ts(tr["exit_ts"])
        avail = _ts(tr["daily_feature_available_at"])
        # Post-entry clock: confirmation windows run from fill, not from the
        # 23:59 daily available_at (overnight 0–60m is mostly empty for CFDs).
        t0 = entry_ts
        signal_day = pd.Timestamp(tr["signal_day"]).date()
        session_start = NY.localize(datetime(signal_day.year, signal_day.month, signal_day.day, 0, 0))
        width = float(tr["range_width_r"])
        mae_r = float(tr["mae_pts"]) / width if width > 0 else np.nan
        mfe_r = float(tr["mfe_pts"]) / width if width > 0 else np.nan
        net_r = float(tr["net_usd"]) / width if width > 0 else np.nan
        flags = campaign_outcome_flags(exits, int(tr["trade_id"]))

        # Load local tapes around campaign.
        start_d = signal_day - timedelta(days=2)
        end_d = max(exit_ts.date(), (t0 + timedelta(minutes=MAX_OBSERVATION_MINS)).date()) + timedelta(days=1)
        peer_tape = Tape1m.from_gby(peer_gby, start_d, end_d)
        primary_tape = Tape1m.from_gby(primary_gby, start_d, end_d)

        # Freeze peer levels at signal available_at (when primary break is known).
        levels = freeze_peer_levels(peer_daily, avail)
        cls = classify(
            side=side,
            t0=t0,
            exit_ts=exit_ts,
            session_start=session_start,
            peer_levels=levels,
            peer_tape=peer_tape,
        )

        event = {
            "event_id": "%s_%s_%s" % (primary, entry_mode, int(tr["trade_id"])),
            "session_date": signal_day.isoformat(),
            "primary_market": primary.upper(),
            "peer_market": peer.upper(),
            "strategy_id": "chop20_boundary60_%s" % entry_mode,
            "campaign_id": int(tr["trade_id"]),
            "signal_ts": avail.isoformat(),
            "primary_entry_ts": entry_ts.isoformat(),
            "primary_entry_side": side,
            "primary_entry_price": float(tr["entry"]),
            "primary_reference_type": "CHOP20_trade_range",
            "primary_range_high": float(tr["range_high"]),
            "primary_range_low": float(tr["range_low"]),
            "primary_range_age": float(tr["range_age_bars"]),
            "primary_break_level": float(tr["range_high"] if side == "long" else tr["range_low"]),
            "primary_break_ts": avail.isoformat(),
            "peer_observation_t0": t0.isoformat(),
            "peer_observation_anchor": "primary_entry_ts",
            "primary_outcome_R": net_r,
            "primary_MAE_R": mae_r,
            "primary_MFE_R": mfe_r,
            "primary_net_usd": float(tr["net_usd"]),
            "primary_exit_ts": exit_ts.isoformat(),
            "primary_holding_minutes": _minutes_between(entry_ts, exit_ts),
            "primary_exit_reason": str(tr["exit_reason"]),
            "year": signal_day.year,
            "hour_ny_break": int(t0.hour),
            **flags,
            **({} if levels is None else {
                "peer_reference_type": levels["peer_reference_type"],
                "peer_range_high": levels["peer_range_high"],
                "peer_range_low": levels["peer_range_low"],
                "peer_range_age": levels["peer_range_age"],
                "peer_atr_20": levels["peer_atr_20"],
            }),
            **cls,
        }
        events.append(event)

        # Conditional risk at +5 / +15 / +30 among still-open.
        for mins in (5, 15, 30):
            dec = t0 + timedelta(minutes=mins)
            st = state_asof(
                side=side,
                t0=t0,
                decision_ts=dec,
                session_start=session_start,
                peer_levels=levels,
                peer_tape=peer_tape,
            )
            fwd = forward_from_decision(trade=tr, exits=exits, decision_ts=dec, primary_tape=primary_tape)
            cond_rows.append(
                {
                    "event_id": event["event_id"],
                    "primary_market": primary.upper(),
                    "peer_market": peer.upper(),
                    "side": side,
                    "decision_mins": mins,
                    "decision_ts": dec.isoformat(),
                    "peer_state": st,
                    "year": signal_day.year,
                    **fwd,
                }
            )

        act = simulate_actions(
            trade=tr,
            exits=exits,
            t0=t0,
            class_row=cls,
            peer_levels=levels,
            peer_tape=peer_tape,
            primary_tape=primary_tape,
            session_start=session_start,
        )
        action_rows.append(
            {
                "event_id": event["event_id"],
                "primary_market": primary.upper(),
                "peer_market": peer.upper(),
                "side": side,
                "confirmation_class": cls["confirmation_class"],
                "year": signal_day.year,
                **act,
            }
        )

    ev = pd.DataFrame(events)
    cond = pd.DataFrame(cond_rows)
    acts = pd.DataFrame(action_rows)
    pair_dir = hub / ("%s_vs_%s" % (primary, peer))
    pair_dir.mkdir(parents=True, exist_ok=True)
    ev.to_csv(pair_dir / "events.csv", index=False)
    cond.to_csv(pair_dir / "conditional_risk.csv", index=False)
    acts.to_csv(pair_dir / "counterfactual_actions.csv", index=False)
    _write_pair_reports(pair_dir, ev, cond, acts, primary=primary, peer=peer)
    return ev


def _agg_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if df.empty:
        return pd.DataFrame()
    for state, g in df.groupby("confirmation_class"):
        net = g["primary_outcome_R"]
        wins = (net > 0).sum()
        gross_win = float(net[net > 0].sum()) if (net > 0).any() else 0.0
        gross_loss = float(-net[net <= 0].sum()) if (net <= 0).any() else 0.0
        pf = gross_win / gross_loss if gross_loss > 0 else (np.inf if gross_win > 0 else np.nan)
        stress = float(net[net < 0].sum())  # sum of negative R as stress proxy
        rows.append(
            {
                "confirmation_class": state,
                "n": int(len(g)),
                "share": float(len(g) / len(df)),
                "net_R": float(net.sum()),
                "median_R": float(net.median()),
                "mean_R": float(net.mean()),
                "profit_factor": float(pf) if np.isfinite(pf) else np.nan,
                "win_rate": float(wins / len(g)),
                "stop_rate": float(g["primary_stop_flag"].mean()),
                "hit_0_5R": float(g["primary_tp_0_5_flag"].mean()),
                "hit_1R": float(g["primary_tp_1_flag"].mean()),
                "hit_4R": float(g["primary_tp_4_flag"].mean()),
                "median_MAE_R": float(g["primary_MAE_R"].median()),
                "p90_MAE_R": float(g["primary_MAE_R"].quantile(0.9)),
                "median_MFE_R": float(g["primary_MFE_R"].median()),
                "N_over_stress": float(net.sum() / abs(stress)) if stress < 0 else np.nan,
                "median_hold_min": float(g["primary_holding_minutes"].median()),
                "median_peer_delay_min": float(g["peer_delay_minutes"].median(skipna=True)),
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def _write_pair_reports(
    pair_dir: Path,
    ev: pd.DataFrame,
    cond: pd.DataFrame,
    acts: pd.DataFrame,
    *,
    primary: str,
    peer: str,
) -> None:
    outcomes = _agg_outcomes(ev)
    outcomes.to_csv(pair_dir / "outcome_by_state.csv", index=False)

    # Long / short splits
    side_rows = []
    for side, sg in ev.groupby("primary_entry_side"):
        o = _agg_outcomes(sg)
        o.insert(0, "side", side)
        side_rows.append(o)
    if side_rows:
        pd.concat(side_rows, ignore_index=True).to_csv(pair_dir / "outcome_by_state_side.csv", index=False)

    # Year-by-year
    yrows = []
    for (year, state), g in ev.groupby(["year", "confirmation_class"]):
        yrows.append(
            {
                "year": int(year),
                "confirmation_class": state,
                "n": int(len(g)),
                "net_R": float(g["primary_outcome_R"].sum()),
                "mean_R": float(g["primary_outcome_R"].mean()),
                "stop_rate": float(g["primary_stop_flag"].mean()),
                "win_rate": float((g["primary_outcome_R"] > 0).mean()),
            }
        )
    pd.DataFrame(yrows).sort_values(["year", "confirmation_class"]).to_csv(
        pair_dir / "outcome_by_state_year.csv", index=False
    )

    # Confirmation heatmap: hour × state
    heat = (
        ev.groupby(["hour_ny_break", "confirmation_class"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=[c for c in STATES if c in ev["confirmation_class"].unique()], fill_value=0)
    )
    heat["total"] = heat.sum(axis=1)
    for c in list(heat.columns):
        if c != "total":
            heat["rate_%s" % c] = heat[c] / heat["total"].replace(0, np.nan)
    heat.to_csv(pair_dir / "confirmation_heatmap_hour.csv")

    # Lead-lag delay distribution
    delays = ev.loc[ev["peer_delay_minutes"].notna(), "peer_delay_minutes"]
    bins = [-1e9, 0, 5, 15, 30, 60, 1e9]
    labels = ["already(<=0)", "1-5", "6-15", "16-30", "31-60", ">60_or_none_path"]
    delay_tab = pd.cut(delays, bins=bins, labels=labels).value_counts().rename_axis("delay_bucket").reset_index(name="n")
    delay_tab.to_csv(pair_dir / "leadlag_delay_distribution.csv", index=False)

    # Transition: side → state → win/loss
    trans = (
        ev.assign(outcome_bin=np.where(ev["primary_outcome_R"] > 0, "win", "loss_or_flat"))
        .groupby(["primary_entry_side", "confirmation_class", "outcome_bin"])
        .size()
        .reset_index(name="n")
    )
    trans.to_csv(pair_dir / "transition_table.csv", index=False)

    # Conditional forward table
    if not cond.empty:
        cagg = (
            cond[cond["open_at_decision"] == 1]
            .groupby(["decision_mins", "peer_state"])
            .agg(
                n=("event_id", "count"),
                forward_stop_rate=("forward_stop", "mean"),
                mean_fwd_R=("forward_net_R", "mean"),
                median_fwd_mfe_R=("forward_mfe_R", "median"),
                median_fwd_mae_R=("forward_mae_R", "median"),
            )
            .reset_index()
        )
        cagg.to_csv(pair_dir / "conditional_risk_summary.csv", index=False)

    # Counterfactual summary
    if not acts.empty:
        arows = [
            {
                "action": "baseline",
                "net_usd": float(acts["baseline_net_usd"].sum()),
                "net_R": float(acts["baseline_net_R"].sum()),
                "mean_R": float(acts["baseline_net_R"].mean()),
            },
            {
                "action": "suppress_adds_after_30m_no_confirm",
                "net_usd": float(acts["no_add_30m_net_usd"].sum()),
                "net_R": float(acts["no_add_30m_net_R"].sum()),
                "mean_R": float(acts["no_add_30m_net_R"].mean()),
            },
            {
                "action": "flatten_after_opposite",
                "net_usd": float(acts["flatten_opposite_net_usd"].sum()),
                "net_R": float(acts["flatten_opposite_net_R"].sum()),
                "mean_R": float(acts["flatten_opposite_net_R"].mean()),
            },
            {
                "action": "tighten_stop_after_opposite",
                "net_usd": float(acts["tighten_opposite_net_usd"].sum()),
                "net_R": float(acts["tighten_opposite_net_R"].sum()),
                "mean_R": float(acts["tighten_opposite_net_R"].mean()),
            },
        ]
        pd.DataFrame(arows).to_csv(pair_dir / "counterfactual_summary.csv", index=False)

    # Pair SUMMARY
    lines = [
        "# Post-entry SMT — %s primary / %s peer" % (primary.upper(), peer.upper()),
        "",
        "Level family: CHOP20 active range (frozen at primary break / signal available_at).",
        "Windows: fast 0–%dm, late 6–%dm, expiry min(exit, +%dm)."
        % (FAST_CONFIRM_MINS, LATE_CONFIRM_MINS, MAX_OBSERVATION_MINS),
        "",
        "## State counts",
        "",
        outcomes.to_string(index=False) if not outcomes.empty else "(empty)",
        "",
        "## Stance (descriptive)",
        "",
    ]
    focus = outcomes[outcomes["confirmation_class"].isin(["NO_CONFIRM", "OPPOSITE_BREAK", "ALREADY_CONFIRMED", "CONFIRMS_FAST"])]
    if not focus.empty:
        base = outcomes[outcomes["confirmation_class"] == "ALREADY_CONFIRMED"]
        base_stop = float(base["stop_rate"].iloc[0]) if not base.empty else np.nan
        for _, r in focus.iterrows():
            lines.append(
                "- **%s** n=%d share=%.0f%% stop=%.0f%% mean_R=%+.2f N/stress=%s"
                % (
                    r["confirmation_class"],
                    r["n"],
                    100 * r["share"],
                    100 * r["stop_rate"],
                    r["mean_R"],
                    ("%.2f" % r["N_over_stress"]) if pd.notna(r["N_over_stress"]) else "n/a",
                )
            )
        if pd.notna(base_stop):
            lines.append("")
            lines.append("ALREADY_CONFIRMED stop_rate=%.0f%% (sync reference)." % (100 * base_stop))
    lines.extend(["", "Hub: `%s`" % pair_dir])
    (pair_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_hub_summary(hub: Path, pair_summaries: List[str], smoke: bool) -> str:
    body = [
        "# CHOP20 post-entry peer confirmation (SMT-style)",
        "",
        "Generated: %s" % datetime.now().isoformat(timespec="seconds"),
        "Smoke: %s" % smoke,
        "DSR: %s" % DSR,
        "",
        "## Contract",
        "",
        "- Post-entry / post-break layer only (not an entry filter).",
        "- Primary break known at daily signal `available_at`; peer levels frozen then.",
        "- Confirmation clock (`t0`) = **primary entry fill** (post-entry layer; avoids empty overnight 23:59+60m window).",
        "- Peer levels = peer prior-day CHOP20 rolling range_high_20/low_20.",
        "- Classification uses completed 1m bars; action fills on next minute.",
        "- Locked windows: fast 0–5m, late 6–30m, obs max 60m or primary exit.",
        "- Source campaigns: `%s/*__close_to_globex__baseline`" % SOURCE,
        "",
        "## Pairs",
        "",
    ]
    for s in pair_summaries:
        body.append(s)
        body.append("")
    body.append("Hub: `%s`" % hub)
    text = "\n".join(body) + "\n"
    (hub / "SUMMARY.md").write_text(text, encoding="utf-8")
    return text


def run(
    *,
    email: bool,
    smoke: bool,
    primary: str,
    peer: str,
    both_directions: bool,
    entry_mode: str,
) -> int:
    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="ha",
        variant_slug="chop20_post_entry_smt",
        instrument=primary.upper(),
        hub_path=str(hub.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "primary": primary,
            "peer": peer,
            "both_directions": both_directions,
            "fast": FAST_CONFIRM_MINS,
            "late": LATE_CONFIRM_MINS,
            "max_obs": MAX_OBSERVATION_MINS,
        },
        notes="Post-entry CHOP20 NAS100↔SPX500 peer confirmation study",
    )
    try:
        pairs = [(primary, peer)]
        if both_directions and (peer, primary) not in pairs:
            pairs.append((peer, primary))

        # Preload dailies + 1m once.
        needed = sorted({m for p in pairs for m in p})
        dailies = {}
        gbys = {}
        for m in needed:
            _progress(hub, "Building %s daily CHOP20 levels …" % m.upper())
            dailies[m] = build_daily_levels(m)
            _progress(hub, "Loading %s 1m …" % m.upper())
            gbys[m] = load_fx_1m_by_ny_date(MARKET_PATHS[m]["one_m"], MARKET_PATHS[m]["symbol"])
            # Full tapes kept even on smoke — campaigns are few; filtering by
            # last-N dates previously dropped the smoke trade window.

        pair_summaries = []
        all_net = 0.0
        all_n = 0
        for prim, pr in pairs:
            ev = run_pair(
                hub,
                primary=prim,
                peer=pr,
                entry_mode=entry_mode,
                smoke=smoke,
                primary_gby=gbys[prim],
                peer_gby=gbys[pr],
                peer_daily=dailies[pr],
            )
            all_n += len(ev)
            all_net += float(ev["primary_net_usd"].sum()) if not ev.empty else 0.0
            pair_summaries.append((hub / ("%s_vs_%s" % (prim, pr)) / "SUMMARY.md").read_text())

        summary = _write_hub_summary(hub, pair_summaries, smoke)

        # Phone email
        email_lines = [
            "CHOP20 post-entry SMT study %s" % ("SMOKE" if smoke else "COMPLETE"),
            "Hub: %s" % hub,
            "DSR: %s" % DSR,
            "Windows: fast 0-%dm late 6-%dm max %dm" % (FAST_CONFIRM_MINS, LATE_CONFIRM_MINS, MAX_OBSERVATION_MINS),
            "",
        ]
        for prim, pr in pairs:
            pdir = hub / ("%s_vs_%s" % (prim, pr))
            oc = pd.read_csv(pdir / "outcome_by_state.csv") if (pdir / "outcome_by_state.csv").exists() else pd.DataFrame()
            email_lines.append("%s → %s" % (prim.upper(), pr.upper()))
            if oc.empty:
                email_lines.append("  (no events)")
            else:
                for _, r in oc.iterrows():
                    email_lines.append(
                        "  %s n=%d stop=%.0f%% meanR=%+.2f hit4=%.0f%%"
                        % (
                            r["confirmation_class"],
                            r["n"],
                            100 * r["stop_rate"],
                            r["mean_R"],
                            100 * r["hit_4R"],
                        )
                    )
            cf = pdir / "counterfactual_summary.csv"
            if cf.exists():
                cfd = pd.read_csv(cf)
                email_lines.append("  actions:")
                for _, r in cfd.iterrows():
                    email_lines.append("    %s netR=%+.1f" % (r["action"], r["net_R"]))
            email_lines.append("")
        email_lines.append("Stance: descriptive first; promote action only if conditional forward tables agree.")
        email_txt = "\n".join(email_lines) + "\n"
        (hub / "EMAIL.txt").write_text(email_txt, encoding="utf-8")

        complete_run(
            rid,
            net_usd=all_net,
            trades=all_n,
            meta={"pairs": ["%s_vs_%s" % p for p in pairs], "smoke": smoke},
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(subject="potions: CHOP20 post-entry SMT %s" % ("smoke" if smoke else "complete"), body=email_txt)
        _progress(hub, "DONE n=%d" % all_n)
        return 0
    except Exception:
        err = traceback.format_exc()
        _progress(hub, "FAILED\n" + err)
        fail_run(rid, notes=err[-500:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: CHOP20 post-entry SMT FAILED", body=err[-4000:])
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--primary", default="nas100", choices=sorted(MARKET_PATHS))
    p.add_argument("--peer", default="spx500", choices=sorted(MARKET_PATHS))
    p.add_argument("--both-directions", action="store_true", help="Also run peer as primary")
    p.add_argument("--entry-mode", default="close_to_globex", choices=["close_to_globex", "close_to_next_rth"])
    args = p.parse_args(list(argv) if argv is not None else None)
    return run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        primary=args.primary.lower(),
        peer=args.peer.lower(),
        both_directions=bool(args.both_directions),
        entry_mode=args.entry_mode,
    )


if __name__ == "__main__":
    raise SystemExit(main())
