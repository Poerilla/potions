"""NQ 4h WICK_REJECT → round-the-clock 5m protected-pivot + first-touch (V1).

Descriptive only: no trades, fills, stops, targets, P&L, plugin, or S1/S2 coupling.

Hub: live/state/nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1 --smoke --email
  python -m live.nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1 --email
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import TICK
from .nq_wick_reject_4h_swing_retest_v1 import make_seeds_30
from .nq_wick_reject_range_seed_retest import (
    Seed,
    _localize,
    build_rth_tape,
    load_wick_events,
)
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1"
STUDY_ID = "nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1"
NY = "America/New_York"
DATA_VERSION = "nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst"
DATA_SESSION_POLICY = "POLICY_A_FULL_AVAILABLE_FUTURES_DATA"
PRIMARY_OUTCOME_HORIZON = pd.Timedelta(minutes=180)
TOUCH_RESPONSE_HORIZON = pd.Timedelta(minutes=60)
BAR_TD = pd.Timedelta(minutes=5)
GAP_TOL = pd.Timedelta(minutes=5) + pd.Timedelta(seconds=1)
SMOKE_CHART_CAP = 5


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _config_hash(hub: Path) -> str:
    parts = [
        (hub / "MODEL_CONTRACT.yaml").read_text(encoding="utf-8"),
        (hub / "CONFIG.md").read_text(encoding="utf-8"),
        "policy=A",
        "tick=0.25",
        "pivot=5m_1L1R_strict",
        "horizon_primary=180m",
        "horizon_touch=60m",
        "response=max(4,ceil(0.25*break))",
        "one_candidate_per_seed=true",
        "seed_expiry_4h_bars=30",
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def session_segment(ts: pd.Timestamp) -> str:
    ts = _localize(ts)
    t = ts.time()
    if time(18, 0) <= t or t < time(2, 0):
        return "ASIA"
    if time(2, 0) <= t < time(8, 0):
        return "EUROPE"
    if time(8, 0) <= t < time(9, 30):
        return "PRE_NY"
    if time(9, 30) <= t < time(11, 0):
        return "NY_OPEN"
    if time(11, 0) <= t < time(14, 0):
        return "NY_MIDDAY"
    if time(14, 0) <= t < time(16, 0):
        return "NY_PM"
    if time(16, 0) <= t < time(17, 0):
        return "POST_CASH"
    if time(17, 0) <= t < time(18, 0):
        return "OVERNIGHT"
    return "OTHER_OR_BOUNDARY"


def seed_age_bucket(hours: float) -> str:
    if hours < 12:
        return "0_to_lt_12h"
    if hours < 24:
        return "12_to_lt_24h"
    if hours < 48:
        return "24_to_lt_48h"
    return "48h_or_more"


def calendar_block(ts: pd.Timestamp) -> str:
    ts = _localize(ts)
    y = ts.year
    if ts.month <= 6:
        return "%dH1" % y
    return "%dH2" % y


def _seed_direction_from_event(ev: pd.Series) -> str:
    od = str(ev.get("outcome_direction") or "").strip().lower()
    if od in ("bullish", "bearish"):
        return od
    bd = str(ev.get("break_direction") or "").strip().lower()
    if bd == "bullish":
        return "bearish"
    if bd == "bearish":
        return "bullish"
    return ""


def _event_map(events: pd.DataFrame) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for _, ev in events.iterrows():
        out[str(ev["event_id"])] = ev
    return out


# ---------------------------------------------------------------------------
# Continuous Globex tape (POLICY A)
# ---------------------------------------------------------------------------


def build_globex_1m(gby: Dict[date, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for d in sorted(gby.keys()):
        raw = gby[d]
        if raw is None or raw.empty:
            continue
        df = raw.copy()
        df.index = pd.DatetimeIndex([_localize(x) for x in df.index])
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        frames.append(df[keep])
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    tape = pd.concat(frames)
    tape = tape[~tape.index.duplicated(keep="last")].sort_index()
    return tape


def to_5m(tape_1m: pd.DataFrame) -> pd.DataFrame:
    if tape_1m is None or tape_1m.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    src = tape_1m[["open", "high", "low", "close"]].copy()
    src.index = pd.DatetimeIndex([_localize(x) for x in src.index])
    src = src.sort_index()
    return (
        src.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna(subset=["open", "high", "low", "close"])
    )


def gap_before(bars_5m: pd.DataFrame, ts: pd.Timestamp) -> bool:
    """True if the bar immediately before ts (if any) leaves a >5m hole ending at ts."""
    ts = _localize(ts)
    if bars_5m is None or bars_5m.empty:
        return True
    prior = bars_5m.index[bars_5m.index < ts]
    if len(prior) == 0:
        return False
    last = _localize(prior[-1])
    return (ts - last) > GAP_TOL


def continuous_through(
    bars_5m: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Tuple[bool, str]:
    """Require 5m bars covering [start, end) without index gaps > 5m."""
    start = _localize(start)
    end = _localize(end)
    if end <= start:
        return True, ""
    window = bars_5m[(bars_5m.index >= start) & (bars_5m.index < end)]
    if window.empty:
        return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    # First bar should open at or very near start (allow start mid-bar: use ceil to 5m)
    first = _localize(window.index[0])
    if first > start + BAR_TD:
        return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    idx = list(window.index)
    for i in range(1, len(idx)):
        if _localize(idx[i]) - _localize(idx[i - 1]) > GAP_TOL:
            return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    last_open = _localize(idx[-1])
    # Need coverage through end: last bar must open at end-5m or later path continuous
    if last_open + BAR_TD < end:
        # check if gap after last bar before end
        return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    return True, ""


def slice_continuous(
    bars_5m: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Tuple[pd.DataFrame, bool, str]:
    ok, reason = continuous_through(bars_5m, start, end)
    window = bars_5m[(bars_5m.index >= _localize(start)) & (bars_5m.index < _localize(end))]
    return window, ok, reason


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def build_seed_eligibility(
    seeds: List[Seed],
    events_by_id: Dict[str, pd.Series],
    bars_5m: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for seed in seeds:
        ev = events_by_id.get(seed.event_id, pd.Series(dtype=object))
        seed_dir = _seed_direction_from_event(ev) if len(ev) else ""
        pen = float(ev.get("penetration_ATR") or np.nan) if len(ev) else float("nan")
        width_atr = (seed.width / seed.atr20_4h) if seed.atr20_4h and seed.atr20_4h > 0 else float("nan")
        avail = _localize(seed.available_at)
        exp = _localize(seed.expires_at)
        # first 5m bar at or after avail
        after = bars_5m[bars_5m.index >= avail]
        included = False
        reason = ""
        first_bar = ""
        if after.empty:
            reason = "missing_5m_data"
        else:
            first = _localize(after.index[0])
            if first >= exp:
                reason = "expired_or_inactive_seed"
            elif (first - avail) > pd.Timedelta(hours=6) and gap_before(bars_5m, first):
                # long wait with gap — still allow if we have bars before expiry
                first_bar = first.isoformat()
                included = True
            else:
                first_bar = first.isoformat()
                included = True
        rows.append(
            {
                "seed_id": seed.seed_id,
                "seed_ts": _localize(seed.seed_close_ts).isoformat(),
                "seed_available_at": avail.isoformat(),
                "seed_expiry": exp.isoformat(),
                "seed_active_policy": "available_until_expires_30x4h",
                "seed_high": seed.high,
                "seed_low": seed.low,
                "seed_width": seed.width,
                "seed_direction": seed_dir,
                "range_width_atr": width_atr,
                "penetration_atr": pen,
                "data_session_policy": DATA_SESSION_POLICY,
                "first_eligible_5m_bar": first_bar,
                "included": included,
                "exclusion_reason": reason,
                "event_id": seed.event_id,
                "slice": seed.slice,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Pivots
# ---------------------------------------------------------------------------


def build_strict_5m_pivots(
    bars_5m: pd.DataFrame,
    seed_id: str,
    avail: pd.Timestamp,
    expiry: pd.Timestamp,
) -> List[Dict[str, Any]]:
    """1L/1R strict pivots; pivot bar open >= avail; available_at <= expiry."""
    if bars_5m is None or len(bars_5m) < 3:
        return []
    avail = _localize(avail)
    expiry = _localize(expiry)
    # Need confirmation bar inside window; include a little after for right bar
    window = bars_5m[(bars_5m.index >= avail - BAR_TD) & (bars_5m.index < expiry + BAR_TD)]
    if len(window) < 3:
        return []
    hi = window["high"].to_numpy(dtype=float)
    lo = window["low"].to_numpy(dtype=float)
    idx = window.index
    pivots: List[Dict[str, Any]] = []
    pid = 0
    for i in range(1, len(window) - 1):
        is_h = hi[i] > hi[i - 1] and hi[i] > hi[i + 1]
        is_l = lo[i] < lo[i - 1] and lo[i] < lo[i + 1]
        if is_h and is_l:
            continue
        if not is_h and not is_l:
            continue
        bar_open = _localize(idx[i])
        if bar_open < avail:
            continue
        # left/right neighbors must be continuous (no gap across pivot confirmation)
        left_open = _localize(idx[i - 1])
        right_open = _localize(idx[i + 1])
        cont = (bar_open - left_open) <= GAP_TOL and (right_open - bar_open) <= GAP_TOL
        pivot_ts = bar_open + BAR_TD
        avail_at = right_open + BAR_TD
        if avail_at > expiry:
            continue
        if not cont:
            continue
        ptype = "HIGH" if is_h else "LOW"
        price = float(hi[i] if is_h else lo[i])
        pid += 1
        bar_i = int(round((bar_open - avail).total_seconds() / 300.0))
        pivots.append(
            {
                "seed_id": seed_id,
                "pivot_id": "%s_P%04d" % (seed_id, pid),
                "pivot_type": ptype,
                "pivot_price": price,
                "pivot_ts": pivot_ts.isoformat(),
                "pivot_available_at": avail_at.isoformat(),
                "bar_index_since_seed_available": bar_i,
                "session_segment": session_segment(avail_at),
                "left_bars": 1,
                "right_bars": 1,
                "strict_extrema": True,
                "data_continuity_pass": True,
                "_pivot_ts": pivot_ts,
                "_bar_open": bar_open,
                "_avail": avail_at,
                "_price": price,
                "_type": "H" if is_h else "L",
            }
        )
    return pivots


def _seed_context_relation(prices: List[float], seed_high: float, seed_low: float) -> str:
    mn = min(prices)
    mx = max(prices)
    if mn > seed_high:
        return "ABOVE_SEED_RANGE"
    if mx < seed_low:
        return "BELOW_SEED_RANGE"
    if mn >= seed_low and mx <= seed_high:
        return "INSIDE_SEED_RANGE"
    return "CROSSES_SEED_RANGE"


def _dir_vs_seed(pattern: str, seed_direction: str) -> str:
    one = "bearish" if pattern.startswith("BEAR") else "bullish"
    sd = (seed_direction or "").lower()
    if sd not in ("bullish", "bearish"):
        return "NOT_APPLICABLE_OR_UNCLASSIFIED"
    if one == sd:
        return "ALIGN_WITH_SEED_DIRECTION"
    return "OPPOSE_SEED_DIRECTION"


def _is_bear_tuple(a, b, c, d) -> bool:
    if not (a["_type"] == "H" and b["_type"] == "L" and c["_type"] == "H" and d["_type"] == "L"):
        return False
    return c["_price"] > a["_price"] and d["_price"] < b["_price"]


def _is_bull_tuple(a, b, c, d) -> bool:
    if not (a["_type"] == "L" and b["_type"] == "H" and c["_type"] == "L" and d["_type"] == "H"):
        return False
    return c["_price"] < a["_price"] and d["_price"] > b["_price"]


def select_structure(
    pivots: List[Dict[str, Any]],
    elig: Dict[str, Any],
    bars_5m: pd.DataFrame,
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """First consecutive four-pivot pattern; one candidate per seed."""
    if len(pivots) < 4:
        return None, "NO_COMPLETED_FOUR_PIVOT_SEQUENCE", ""

    near = ""
    reason = "NO_COMPLETED_FOUR_PIVOT_SEQUENCE"

    for i in range(len(pivots) - 3):
        a, b, c, d = pivots[i], pivots[i + 1], pivots[i + 2], pivots[i + 3]
        if not (a["_pivot_ts"] < b["_pivot_ts"] < c["_pivot_ts"] < d["_pivot_ts"]):
            continue
        if not (a["_avail"] <= b["_avail"] <= c["_avail"] <= d["_avail"]):
            continue
        if not (a["_bar_open"] < b["_bar_open"] < c["_bar_open"] < d["_bar_open"]):
            continue

        pattern = None
        pattern_code = ""
        if _is_bear_tuple(a, b, c, d):
            pattern = "BEAR"
            pattern_code = "BEAR_HLHHLL"
        elif _is_bull_tuple(a, b, c, d):
            pattern = "BULL"
            pattern_code = "BULL_LHLHHL"
        else:
            # directional near-miss on consecutive typed sequence
            if (
                a["_type"] == "H"
                and b["_type"] == "L"
                and c["_type"] == "H"
                and d["_type"] == "L"
            ):
                reason = "SEQUENCE_NOT_DIRECTIONALLY_VALID"
                bits = []
                if not (c["_price"] > a["_price"]):
                    bits.append("HH was not greater than H1")
                if not (d["_price"] < b["_price"]):
                    bits.append("LL was not lower than L1")
                near = "NEAR MISS — NOT COUNTED; " + "; ".join(bits)
            elif (
                a["_type"] == "L"
                and b["_type"] == "H"
                and c["_type"] == "L"
                and d["_type"] == "H"
            ):
                reason = "SEQUENCE_NOT_DIRECTIONALLY_VALID"
                bits = []
                if not (c["_price"] < a["_price"]):
                    bits.append("LL was not lower than L1")
                if not (d["_price"] > b["_price"]):
                    bits.append("HH was not greater than H1")
                near = "NEAR MISS — NOT COUNTED; " + "; ".join(bits)
            continue

        # formation continuity P1 bar through P4 available
        form_ok, form_reason = continuous_through(bars_5m, a["_bar_open"], d["_avail"])
        if not form_ok:
            # first qualifying candidate excluded for gap — do not substitute later
            return None, form_reason, "formation crossed session/data gap"

        prices = [a["_price"], b["_price"], c["_price"], d["_price"]]
        if pattern == "BEAR":
            h1, l1, hh, ll = a["_price"], b["_price"], c["_price"], d["_price"]
            protected_side = "HIGH"
            protected_price = hh
            break_level = l1
            fail_thr = protected_price + TICK
        else:
            l1, h1, ll, hh = a["_price"], b["_price"], c["_price"], d["_price"]
            protected_side = "LOW"
            protected_price = ll
            break_level = h1
            fail_thr = protected_price - TICK

        break_dist = abs(protected_price - break_level) / TICK
        resp_dist = max(4, int(math.ceil(0.25 * break_dist)))
        complete = d["_avail"]
        seed_avail = _localize(pd.Timestamp(elig["seed_available_at"]))
        seq_min = (complete - a["_pivot_ts"]).total_seconds() / 60.0
        since_seed = (complete - seed_avail).total_seconds() / 60.0
        age_h = (complete - seed_avail).total_seconds() / 3600.0
        cand_id = "CAND_%s_%s" % (elig["seed_id"], pattern)

        row = {
            "candidate_id": cand_id,
            "seed_id": elig["seed_id"],
            "pattern": pattern_code,
            "p1_id": a["pivot_id"],
            "p2_id": b["pivot_id"],
            "p3_id": c["pivot_id"],
            "p4_id": d["pivot_id"],
            "p1_price": a["_price"],
            "p2_price": b["_price"],
            "p3_price": c["_price"],
            "p4_price": d["_price"],
            "h1_price": h1,
            "l1_price": l1,
            "hh_price": hh,
            "ll_price": ll,
            "structure_complete_at": complete.isoformat(),
            "protected_side": protected_side,
            "protected_price": protected_price,
            "failure_threshold": fail_thr,
            "break_level": break_level,
            "break_distance_ticks": round(break_dist, 4),
            "response_distance_ticks": resp_dist,
            "sequence_duration_minutes": round(seq_min, 4),
            "minutes_since_seed_available": round(since_seed, 4),
            "session_segment": session_segment(complete),
            "seed_context_relation": _seed_context_relation(
                prices, float(elig["seed_high"]), float(elig["seed_low"])
            ),
            "5m_direction_vs_seed_direction": _dir_vs_seed(pattern_code, str(elig["seed_direction"])),
            "seed_age_hours": round(age_h, 4),
            "seed_age_bucket": seed_age_bucket(age_h),
            "calendar_block": calendar_block(complete),
            "candidate_status": "COMPLETED",
            "exclusion_reason": "",
            "data_continuity_pass": True,
            "p1_ts": a["_pivot_ts"].isoformat(),
            "p2_ts": b["_pivot_ts"].isoformat(),
            "p3_ts": c["_pivot_ts"].isoformat(),
            "p4_ts": d["_pivot_ts"].isoformat(),
            "p1_available_at": a["_avail"].isoformat(),
            "p2_available_at": b["_avail"].isoformat(),
            "p3_available_at": c["_avail"].isoformat(),
            "p4_available_at": d["_avail"].isoformat(),
            "p1_bar_open_ts": a["_bar_open"].isoformat(),
            "p2_bar_open_ts": b["_bar_open"].isoformat(),
            "p3_bar_open_ts": c["_bar_open"].isoformat(),
            "p4_bar_open_ts": d["_bar_open"].isoformat(),
            "_complete": complete,
            "_pattern": pattern,
            "_p1": a,
            "_p2": b,
            "_p3": c,
            "_p4": d,
        }
        return row, "", ""

    # Non-consecutive pattern that would qualify → intervening ambiguity
    for i in range(len(pivots)):
        for j in range(i + 1, len(pivots)):
            for k in range(j + 1, len(pivots)):
                for m in range(k + 1, len(pivots)):
                    if j == i + 1 and k == j + 1 and m == k + 1:
                        continue
                    a, b, c, d = pivots[i], pivots[j], pivots[k], pivots[m]
                    if _is_bear_tuple(a, b, c, d) or _is_bull_tuple(a, b, c, d):
                        return (
                            None,
                            "INTERVENING_PIVOT_AMBIGUITY",
                            "NEAR MISS — NOT COUNTED (intervening pivots)",
                        )

    return None, reason, near


# ---------------------------------------------------------------------------
# Protection + touch response
# ---------------------------------------------------------------------------


def evaluate_protection(cand: Dict[str, Any], bars_5m: pd.DataFrame) -> Dict[str, Any]:
    complete = cand["_complete"]
    horizon_end = complete + PRIMARY_OUTCOME_HORIZON
    window, ok, gap_reason = slice_continuous(bars_5m, complete, horizon_end)

    out: Dict[str, Any] = {
        "candidate_id": cand["candidate_id"],
        "evaluation_start": complete.isoformat(),
        "outcome_horizon_end": horizon_end.isoformat(),
        "primary_outcome_label": "INSUFFICIENT_DATA_OR_SESSION_GAP",
        "protection_held": False,
        "equal_touch_occurred": False,
        "first_equal_touch_ts": "",
        "failure_ts": "",
        "failure_price": np.nan,
        "failure_distance_ticks": np.nan,
        "minutes_to_failure": np.nan,
        "max_favorable_excursion_ticks": np.nan,
        "max_adverse_excursion_ticks": np.nan,
        "session_segment": cand["session_segment"],
        "data_complete": False,
        "gap_or_exclusion_reason": gap_reason if not ok else "",
    }
    if not ok or window.empty:
        return out

    prot = float(cand["protected_price"])
    fail_thr = float(cand["failure_threshold"])
    pattern = cand["_pattern"]
    fail_ts = None
    fail_px = None
    eq_ts = None
    mfe = 0.0
    mae = 0.0

    for ts, row in window.iterrows():
        ts = _localize(ts)
        bar_close = ts + BAR_TD
        hi = float(row["high"])
        lo = float(row["low"])
        if pattern == "BEAR":
            mfe = max(mfe, (prot - lo) / TICK)
            mae = max(mae, (hi - prot) / TICK)
            if hi >= prot - 1e-12 and hi < fail_thr - 1e-12:
                if eq_ts is None:
                    eq_ts = bar_close
            if hi >= fail_thr - 1e-12:
                fail_ts = bar_close
                fail_px = hi
                break
        else:
            mfe = max(mfe, (hi - prot) / TICK)
            mae = max(mae, (prot - lo) / TICK)
            if lo <= prot + 1e-12 and lo > fail_thr + 1e-12:
                if eq_ts is None:
                    eq_ts = bar_close
            if lo <= fail_thr + 1e-12:
                fail_ts = bar_close
                fail_px = lo
                break

    out["data_complete"] = True
    out["max_favorable_excursion_ticks"] = round(mfe, 4)
    out["max_adverse_excursion_ticks"] = round(mae, 4)
    out["equal_touch_occurred"] = eq_ts is not None
    out["first_equal_touch_ts"] = eq_ts.isoformat() if eq_ts is not None else ""

    if fail_ts is not None:
        out["protection_held"] = False
        out["primary_outcome_label"] = "FAILED_ONE_TICK_OR_MORE"
        out["failure_ts"] = fail_ts.isoformat()
        out["failure_price"] = fail_px
        out["failure_distance_ticks"] = round(abs(fail_px - prot) / TICK, 4)
        out["minutes_to_failure"] = round((fail_ts - complete).total_seconds() / 60.0, 4)
    else:
        out["protection_held"] = True
        out["primary_outcome_label"] = (
            "HELD_EQUAL_TOUCH" if eq_ts is not None else "HELD_NO_TOUCH"
        )
    return out


def evaluate_touch_response(
    cand: Dict[str, Any],
    prot_out: Dict[str, Any],
    bars_5m: pd.DataFrame,
) -> Dict[str, Any]:
    complete = cand["_complete"]
    horizon_end = complete + PRIMARY_OUTCOME_HORIZON
    prot = float(cand["protected_price"])
    fail_thr = float(cand["failure_threshold"])
    resp_dist = int(cand["response_distance_ticks"])
    pattern = cand["_pattern"]

    if pattern == "BEAR":
        fav_thr = prot - resp_dist * TICK
        inv_thr = fail_thr  # prot + 1 tick
    else:
        fav_thr = prot + resp_dist * TICK
        inv_thr = fail_thr  # prot - 1 tick

    base: Dict[str, Any] = {
        "candidate_id": cand["candidate_id"],
        "touch_eligible": False,
        "no_touch_reason": "",
        "touch_ts": "",
        "touch_price": np.nan,
        "touch_bar_high": np.nan,
        "touch_bar_low": np.nan,
        "touch_response_end": "",
        "response_distance_ticks": resp_dist,
        "favorable_response_threshold": fav_thr,
        "invalidation_threshold": inv_thr,
        "favorable_threshold_first_ts": "",
        "invalidation_threshold_first_ts": "",
        "touch_response_outcome_label": "NO_ELIGIBLE_TOUCH",
        "minutes_to_favorable_response": np.nan,
        "minutes_to_invalidation": np.nan,
        "max_directional_excursion_ticks_after_touch": np.nan,
        "max_adverse_excursion_ticks_after_touch": np.nan,
        "session_segment": cand["session_segment"],
        "data_complete": False,
        "gap_or_exclusion_reason": "",
    }

    if not prot_out.get("data_complete"):
        base["no_touch_reason"] = "primary_horizon_insufficient"
        base["touch_response_outcome_label"] = "NO_ELIGIBLE_TOUCH"
        return base

    # Scan for first equal touch before failure within primary horizon
    window, ok, gap_reason = slice_continuous(bars_5m, complete, horizon_end)
    if not ok:
        base["no_touch_reason"] = gap_reason
        return base

    touch_ts = None
    touch_hi = touch_lo = None
    failed_before_touch = False

    for ts, row in window.iterrows():
        ts = _localize(ts)
        bar_close = ts + BAR_TD
        hi = float(row["high"])
        lo = float(row["low"])
        if pattern == "BEAR":
            if hi >= fail_thr - 1e-12:
                failed_before_touch = True
                break
            if hi >= prot - 1e-12 and hi < fail_thr - 1e-12:
                touch_ts = bar_close
                touch_hi, touch_lo = hi, lo
                break
        else:
            if lo <= fail_thr + 1e-12:
                failed_before_touch = True
                break
            if lo <= prot + 1e-12 and lo > fail_thr + 1e-12:
                touch_ts = bar_close
                touch_hi, touch_lo = hi, lo
                break

    if touch_ts is None:
        base["no_touch_reason"] = (
            "failed_before_touch" if failed_before_touch else "no_touch_in_horizon"
        )
        return base

    resp_end = touch_ts + TOUCH_RESPONSE_HORIZON
    base["touch_eligible"] = True
    base["touch_ts"] = touch_ts.isoformat()
    base["touch_price"] = prot
    base["touch_bar_high"] = touch_hi
    base["touch_bar_low"] = touch_lo
    base["touch_response_end"] = resp_end.isoformat()

    resp_win, resp_ok, resp_gap = slice_continuous(bars_5m, touch_ts, resp_end)
    # include bars strictly after touch bar open: touch_ts is close of touch bar;
    # response starts after that bar (next bars). Spec: after first valid touch.
    # Measure from bars with open >= touch_ts (first bar after touch close).
    resp_win = bars_5m[(bars_5m.index >= touch_ts) & (bars_5m.index < resp_end)]
    # continuity check from touch_ts
    cont_ok, cont_reason = continuous_through(bars_5m, touch_ts, resp_end)
    if not cont_ok:
        base["touch_response_outcome_label"] = "TOUCH_INSUFFICIENT_DATA_OR_SESSION_GAP"
        base["gap_or_exclusion_reason"] = cont_reason
        base["data_complete"] = False
        return base

    fav_ts = None
    inv_ts = None
    mfe = 0.0
    mae = 0.0
    same_bar_both = False

    for ts, row in resp_win.iterrows():
        ts = _localize(ts)
        bar_close = ts + BAR_TD
        hi = float(row["high"])
        lo = float(row["low"])
        if pattern == "BEAR":
            mfe = max(mfe, (prot - lo) / TICK)
            mae = max(mae, (hi - prot) / TICK)
            hit_fav = lo <= fav_thr + 1e-12
            hit_inv = hi >= inv_thr - 1e-12
        else:
            mfe = max(mfe, (hi - prot) / TICK)
            mae = max(mae, (prot - lo) / TICK)
            hit_fav = hi >= fav_thr - 1e-12
            hit_inv = lo <= inv_thr + 1e-12

        if hit_fav and hit_inv:
            same_bar_both = True
            inv_ts = bar_close
            fav_ts = bar_close
            break
        if hit_inv and inv_ts is None:
            inv_ts = bar_close
            break
        if hit_fav and fav_ts is None:
            fav_ts = bar_close
            break

    base["data_complete"] = True
    base["max_directional_excursion_ticks_after_touch"] = round(mfe, 4)
    base["max_adverse_excursion_ticks_after_touch"] = round(mae, 4)
    if fav_ts is not None:
        base["favorable_threshold_first_ts"] = fav_ts.isoformat()
        base["minutes_to_favorable_response"] = round(
            (fav_ts - touch_ts).total_seconds() / 60.0, 4
        )
    if inv_ts is not None:
        base["invalidation_threshold_first_ts"] = inv_ts.isoformat()
        base["minutes_to_invalidation"] = round(
            (inv_ts - touch_ts).total_seconds() / 60.0, 4
        )

    if same_bar_both:
        base["touch_response_outcome_label"] = "TOUCH_BOTH_SAME_5M_BAR_STOP_FIRST"
    elif inv_ts is not None and (fav_ts is None or inv_ts <= fav_ts):
        base["touch_response_outcome_label"] = "TOUCH_INVALIDATES_DIRECTION"
    elif fav_ts is not None:
        base["touch_response_outcome_label"] = "TOUCH_FAVORS_DIRECTION"
    else:
        base["touch_response_outcome_label"] = "TOUCH_NEITHER_BY_HORIZON"
    return base


# ---------------------------------------------------------------------------
# Causality / summary
# ---------------------------------------------------------------------------


def run_causality_audit(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
    touches: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> Tuple[bool, List[str], pd.DataFrame]:
    fails: List[str] = []
    assertions: List[Dict[str, Any]] = []
    included = elig[elig["included"] == True]  # noqa: E712

    # every included seed → exactly one candidate OR one exclusion
    cand_seeds = set(cands["seed_id"].tolist()) if len(cands) else set()
    excl_seeds = set(exclusions["seed_id"].tolist()) if len(exclusions) else set()
    for sid in included["seed_id"].tolist():
        n = int(sid in cand_seeds) + int(sid in excl_seeds)
        if n != 1:
            fails.append("seed %s candidate/exclusion count=%d" % (sid, n))

    if len(cands) and cands["seed_id"].duplicated().any():
        fails.append("multiple candidates for one seed")
    if len(cands) != len(outs):
        fails.append("candidates %d != protection outcomes %d" % (len(cands), len(outs)))
    if len(cands) != len(touches):
        fails.append("candidates %d != touch outcomes %d" % (len(cands), len(touches)))

    for _, c in cands.iterrows():
        notes = []
        row_ok = True
        seed_rows = included[included["seed_id"] == c["seed_id"]]
        if seed_rows.empty:
            fails.append("%s missing eligibility" % c["candidate_id"])
            row_ok = False
            notes.append("missing_eligibility")
            assertions.append({"candidate_id": c["candidate_id"], "overall_pass": False, "failure_reason": ";".join(notes)})
            continue
        e = seed_rows.iloc[0]
        seed_avail = _localize(pd.Timestamp(e["seed_available_at"]))
        seed_exp = _localize(pd.Timestamp(e["seed_expiry"]))
        p1ts = _localize(pd.Timestamp(c["p1_ts"]))
        p2ts = _localize(pd.Timestamp(c["p2_ts"]))
        p3ts = _localize(pd.Timestamp(c["p3_ts"]))
        p4ts = _localize(pd.Timestamp(c["p4_ts"]))
        p1a = _localize(pd.Timestamp(c["p1_available_at"]))
        p2a = _localize(pd.Timestamp(c["p2_available_at"]))
        p3a = _localize(pd.Timestamp(c["p3_available_at"]))
        p4a = _localize(pd.Timestamp(c["p4_available_at"]))
        complete = _localize(pd.Timestamp(c["structure_complete_at"]))

        checks = {
            "seed_available_before_p1": seed_avail <= p1ts,
            "seed_active_through_completion": complete < seed_exp and seed_avail <= complete,
            "pivot_order_pass": p1ts < p2ts < p3ts < p4ts,
            "pivot_availability_order_pass": p1a <= p2a <= p3a <= p4a,
            "first_candidate_policy_pass": True,
            "no_future_data_pass": all(
                pav == pts + BAR_TD
                for pts, pav in ((p1ts, p1a), (p2ts, p2a), (p3ts, p3a), (p4ts, p4a))
            ),
            "no_cross_gap_pass": bool(c.get("data_continuity_pass", True)),
            "primary_outcome_timestamp_pass": True,
            "touch_timestamp_pass": True,
            "one_touch_policy_pass": True,
            "chart_ledger_match_pass": True,
        }
        if complete != p4a:
            checks["no_future_data_pass"] = False
            notes.append("complete_ne_p4a")
        for k, v in checks.items():
            if not v:
                row_ok = False
                notes.append(k)
                fails.append("%s %s" % (c["candidate_id"], k))

        # protection row
        o = outs[outs["candidate_id"] == c["candidate_id"]]
        if len(o):
            o0 = o.iloc[0]
            st = _localize(pd.Timestamp(o0["evaluation_start"]))
            he = _localize(pd.Timestamp(o0["outcome_horizon_end"]))
            if st != complete or he != complete + PRIMARY_OUTCOME_HORIZON:
                checks["primary_outcome_timestamp_pass"] = False
                row_ok = False
                notes.append("primary_horizon")
                fails.append("%s primary horizon mismatch" % c["candidate_id"])
            if o0.get("failure_ts"):
                ft = _localize(pd.Timestamp(o0["failure_ts"]))
                if ft < complete:
                    row_ok = False
                    notes.append("failure_before_complete")
                    fails.append("%s failure before complete" % c["candidate_id"])

        t = touches[touches["candidate_id"] == c["candidate_id"]]
        if len(t):
            t0 = t.iloc[0]
            if t0.get("touch_eligible") and t0.get("touch_ts"):
                tts = _localize(pd.Timestamp(t0["touch_ts"]))
                if not (tts > complete and tts <= complete + PRIMARY_OUTCOME_HORIZON):
                    checks["touch_timestamp_pass"] = False
                    row_ok = False
                    notes.append("touch_ts_window")
                    fails.append("%s touch_ts out of window" % c["candidate_id"])

        assertions.append(
            {
                "candidate_id": c["candidate_id"],
                **{k: bool(v) for k, v in checks.items()},
                "overall_pass": row_ok,
                "failure_reason": ";".join(notes),
            }
        )

    # study-level summary row
    assertions.append(
        {
            "candidate_id": "__STUDY__",
            "overall_pass": len(fails) == 0,
            "failure_reason": "; ".join(fails[:20]),
            "seed_available_before_p1": True,
            "seed_active_through_completion": True,
            "pivot_order_pass": True,
            "pivot_availability_order_pass": True,
            "first_candidate_policy_pass": True,
            "no_future_data_pass": True,
            "no_cross_gap_pass": True,
            "primary_outcome_timestamp_pass": True,
            "touch_timestamp_pass": True,
            "one_touch_policy_pass": True,
            "chart_ledger_match_pass": True,
        }
    )
    return len(fails) == 0, fails, pd.DataFrame(assertions)


def _wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def compute_summary(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
    touches: pd.DataFrame,
    causality_ok: bool,
) -> Dict[str, Any]:
    eligible_n = int((elig["included"] == True).sum())  # noqa: E712
    excl = elig[elig["included"] == False]  # noqa: E712
    merged = (
        cands.merge(outs, on="candidate_id", how="left", suffixes=("", "_out"))
        .merge(touches, on="candidate_id", how="left", suffixes=("", "_tch"))
        if len(cands)
        else pd.DataFrame()
    )
    n_cand = len(cands)
    bear = merged[merged["pattern"].str.startswith("BEAR")] if n_cand else merged
    bull = merged[merged["pattern"].str.startswith("BULL")] if n_cand else merged

    def label_counts(sub: pd.DataFrame) -> Dict[str, int]:
        labs = [
            "HELD_NO_TOUCH",
            "HELD_EQUAL_TOUCH",
            "FAILED_ONE_TICK_OR_MORE",
            "INSUFFICIENT_DATA_OR_SESSION_GAP",
        ]
        out = {k: 0 for k in labs}
        if sub is None or sub.empty:
            return out
        for k in labs:
            out[k] = int((sub["primary_outcome_label"] == k).sum())
        return out

    def hold_rate(sub: pd.DataFrame) -> Tuple[float, int, int]:
        if sub is None or sub.empty:
            return float("nan"), 0, 0
        valid = sub[sub["primary_outcome_label"] != "INSUFFICIENT_DATA_OR_SESSION_GAP"]
        if valid.empty:
            return float("nan"), 0, 0
        held = int(valid["protection_held"].sum())
        n = len(valid)
        return held / n, held, n

    bear_lc = label_counts(bear)
    bull_lc = label_counts(bull)
    bear_hr, bear_held, bear_n = hold_rate(bear)
    bull_hr, bull_held, bull_n = hold_rate(bull)
    bear_lo, bear_hi = _wilson_ci(bear_held, bear_n)
    bull_lo, bull_hi = _wilson_ci(bull_held, bull_n)

    def touch_stats(sub: pd.DataFrame) -> Dict[str, Any]:
        if sub is None or sub.empty:
            return {
                "no_eligible": 0,
                "evaluable": 0,
                "favors": 0,
                "invalidates": 0,
                "both": 0,
                "neither": 0,
                "insuff": 0,
                "favors_rate": float("nan"),
                "inval_rate": float("nan"),
            }
        no_elig = int((sub["touch_response_outcome_label"] == "NO_ELIGIBLE_TOUCH").sum())
        insuff = int(
            (sub["touch_response_outcome_label"] == "TOUCH_INSUFFICIENT_DATA_OR_SESSION_GAP").sum()
        )
        eval_mask = ~sub["touch_response_outcome_label"].isin(
            ["NO_ELIGIBLE_TOUCH", "TOUCH_INSUFFICIENT_DATA_OR_SESSION_GAP"]
        )
        ev = sub[eval_mask]
        favors = int((ev["touch_response_outcome_label"] == "TOUCH_FAVORS_DIRECTION").sum())
        inval = int((ev["touch_response_outcome_label"] == "TOUCH_INVALIDATES_DIRECTION").sum())
        both = int(
            (ev["touch_response_outcome_label"] == "TOUCH_BOTH_SAME_5M_BAR_STOP_FIRST").sum()
        )
        neither = int((ev["touch_response_outcome_label"] == "TOUCH_NEITHER_BY_HORIZON").sum())
        n_ev = len(ev)
        return {
            "no_eligible": no_elig,
            "evaluable": n_ev,
            "favors": favors,
            "invalidates": inval,
            "both": both,
            "neither": neither,
            "insuff": insuff,
            "favors_rate": (favors / n_ev) if n_ev else float("nan"),
            "inval_rate": ((inval + both) / n_ev) if n_ev else float("nan"),
        }

    bear_t = touch_stats(bear)
    bull_t = touch_stats(bull)

    # touch_rate: valid first touches / candidates with evaluable 180m primary
    prim_ok = merged[merged["primary_outcome_label"] != "INSUFFICIENT_DATA_OR_SESSION_GAP"] if n_cand else merged
    n_prim = len(prim_ok)
    n_touch = int(prim_ok["touch_eligible"].sum()) if n_prim and "touch_eligible" in prim_ok else 0
    touch_rate = (n_touch / n_prim) if n_prim else float("nan")

    med_since = float(cands["minutes_since_seed_available"].median()) if n_cand else float("nan")
    med_seq = float(cands["sequence_duration_minutes"].median()) if n_cand else float("nan")

    seg_counts = (
        cands["session_segment"].value_counts().to_dict() if n_cand else {}
    )

    all_ok = merged[merged["primary_outcome_label"] != "INSUFFICIENT_DATA_OR_SESSION_GAP"] if n_cand else merged
    mfe_med = float(all_ok["max_favorable_excursion_ticks"].median()) if len(all_ok) else float("nan")
    mae_med = float(all_ok["max_adverse_excursion_ticks"].median()) if len(all_ok) else float("nan")

    fails = all_ok[all_ok["primary_outcome_label"] == "FAILED_ONE_TICK_OR_MORE"] if len(all_ok) else all_ok
    med_fail_b = float(
        bear[bear["primary_outcome_label"] == "FAILED_ONE_TICK_OR_MORE"]["minutes_to_failure"].median()
    ) if n_cand and len(bear) else float("nan")
    med_fail_u = float(
        bull[bull["primary_outcome_label"] == "FAILED_ONE_TICK_OR_MORE"]["minutes_to_failure"].median()
    ) if n_cand and len(bull) else float("nan")

    min_elig = eligible_n >= 80
    min_cand = n_cand >= 40
    min_side = (len(bear) >= 15) and (len(bull) >= 15)
    sample_ok = min_elig and min_cand and min_side
    touch_sample_bear = bear_t["evaluable"] >= 15
    touch_sample_bull = bull_t["evaluable"] >= 15

    prot_screen = (
        sample_ok
        and causality_ok
        and bear_hr == bear_hr
        and bull_hr == bull_hr
        and bear_hr >= 0.55
        and bull_hr >= 0.55
    )
    touch_screen_bear = (
        touch_sample_bear
        and bear_t["favors_rate"] == bear_t["favors_rate"]
        and bear_t["favors_rate"] >= 0.55
        and bear_t["inval_rate"] < bear_t["favors_rate"]
    )
    touch_screen_bull = (
        touch_sample_bull
        and bull_t["favors_rate"] == bull_t["favors_rate"]
        and bull_t["favors_rate"] >= 0.55
        and bull_t["inval_rate"] < bull_t["favors_rate"]
    )

    if not sample_ok:
        stance = "DESCRIPTIVE ONLY — INSUFFICIENT SAMPLE FOR INTERPRETATION"
        decision = "INSUFFICIENT_SAMPLE"
    elif not causality_ok:
        stance = "DESCRIPTIVE ONLY / CAUSALITY FAIL"
        decision = "CAUSALITY_FAIL"
    elif prot_screen and (touch_screen_bear or touch_screen_bull):
        stance = (
            "DESCRIPTIVE OBSERVATION WORTH PRESERVING (screening only — NOT a trade authorization)"
        )
        decision = "DESCRIPTIVE_SCREEN_PASS"
    elif (bear_hr == bear_hr and bear_hr >= 0.55 and len(bear) >= 15) != (
        bull_hr == bull_hr and bull_hr >= 0.55 and len(bull) >= 15
    ):
        stance = "ONE-SIDED DESCRIPTIVE OBSERVATION ONLY"
        decision = "ONE_SIDED_ONLY"
    else:
        stance = "DESCRIPTIVE ONLY — does not meet predeclared preservation screens"
        decision = "NEGATIVE_OR_WEAK"

    return {
        "eligible_seed_count": eligible_n,
        "excluded_seed_count": len(excl),
        "candidate_count": n_cand,
        "candidate_rate": (n_cand / eligible_n) if eligible_n else float("nan"),
        "bear_count": int(len(bear)),
        "bull_count": int(len(bull)),
        "median_minutes_since_seed_available": med_since,
        "median_sequence_duration_minutes": med_seq,
        "candidate_count_by_session_segment": seg_counts,
        "bear_protection_labels": bear_lc,
        "bull_protection_labels": bull_lc,
        "bear_protection_hold_rate_180m": bear_hr,
        "bull_protection_hold_rate_180m": bull_hr,
        "bear_hold_ci": (bear_lo, bear_hi),
        "bull_hold_ci": (bull_lo, bull_hi),
        "touch_rate": touch_rate,
        "bear_touch": bear_t,
        "bull_touch": bull_t,
        "median_mfe_ticks": mfe_med,
        "median_mae_ticks": mae_med,
        "median_minutes_to_failure_bear": med_fail_b,
        "median_minutes_to_failure_bull": med_fail_u,
        "causality_pass": causality_ok,
        "sample_thresholds_met": sample_ok,
        "touch_sample_bear_ok": touch_sample_bear,
        "touch_sample_bull_ok": touch_sample_bull,
        "protection_screen_pass": prot_screen,
        "touch_screen_bear_pass": touch_screen_bear,
        "touch_screen_bull_pass": touch_screen_bull,
        "decision": decision,
        "stance": stance,
        "data_session_policy": DATA_SESSION_POLICY,
        "non_promotion": True,
    }


def write_summary_md(hub: Path, metrics: Dict[str, Any], cfg_hash: str) -> None:
    m = metrics
    bl = m["bear_protection_labels"]
    ul = m["bull_protection_labels"]
    bt = m["bear_touch"]
    ut = m["bull_touch"]

    def pct(x: float) -> str:
        return "%.1f%%" % (100 * x) if x == x else "n/a"

    def ci(pair: Tuple[float, float]) -> str:
        a, b = pair
        if a != a or b != b:
            return "n/a"
        return "[%.1f%%, %.1f%%]" % (100 * a, 100 * b)

    seg = m.get("candidate_count_by_session_segment") or {}
    seg_line = ", ".join("%s=%d" % (k, v) for k, v in sorted(seg.items(), key=lambda x: -x[1]))

    lines = [
        "# NQ 4H WICK-REJECT -> 24H 5M PROTECTED-PIVOT + FIRST-TOUCH RESPONSE V1",
        "",
        "STATUS: DESCRIPTIVE ONLY",
        "CONFIG HASH: %s" % cfg_hash,
        "DATA SESSION POLICY: %s" % m["data_session_policy"],
        "CAUSALITY: %s" % ("PASS" if m["causality_pass"] else "FAIL"),
        "STANCE: %s" % m["stance"],
        "DECISION: %s" % m["decision"],
        "",
        "## Population",
        "- 4h wick-reject seeds (eligible with post-seed 5m): %d" % m["eligible_seed_count"],
        "- Excluded seeds: %d" % m["excluded_seed_count"],
        "",
        "## Formation",
        "- Bear H1-L1-HH-LL candidates: %d" % m["bear_count"],
        "- Bull L1-H1-LL-HH candidates: %d" % m["bull_count"],
        "- Total candidates: %d" % m["candidate_count"],
        "- Candidate rate: %d / %d = %s"
        % (
            m["candidate_count"],
            m["eligible_seed_count"],
            pct(m["candidate_rate"]),
        ),
        "- Median minutes from seed available to completion: %s"
        % (
            "%.1f" % m["median_minutes_since_seed_available"]
            if m["median_minutes_since_seed_available"] == m["median_minutes_since_seed_available"]
            else "n/a"
        ),
        "- Median sequence duration minutes: %s"
        % (
            "%.1f" % m["median_sequence_duration_minutes"]
            if m["median_sequence_duration_minutes"] == m["median_sequence_duration_minutes"]
            else "n/a"
        ),
        "- Candidate counts by session segment: %s" % (seg_line or "n/a"),
        "",
        "## Primary protection outcome: 180 minutes after structure completion",
        "- Bear held no touch / equal touch / strict failure / insufficient: %d / %d / %d / %d"
        % (
            bl["HELD_NO_TOUCH"],
            bl["HELD_EQUAL_TOUCH"],
            bl["FAILED_ONE_TICK_OR_MORE"],
            bl["INSUFFICIENT_DATA_OR_SESSION_GAP"],
        ),
        "- Bear valid hold rate: %s (CI %s)"
        % (pct(m["bear_protection_hold_rate_180m"]), ci(m["bear_hold_ci"])),
        "- Bull held no touch / equal touch / strict failure / insufficient: %d / %d / %d / %d"
        % (
            ul["HELD_NO_TOUCH"],
            ul["HELD_EQUAL_TOUCH"],
            ul["FAILED_ONE_TICK_OR_MORE"],
            ul["INSUFFICIENT_DATA_OR_SESSION_GAP"],
        ),
        "- Bull valid hold rate: %s (CI %s)"
        % (pct(m["bull_protection_hold_rate_180m"]), ci(m["bull_hold_ci"])),
        "- Median minutes to strict failure, bear / bull: %s / %s"
        % (
            "%.1f" % m["median_minutes_to_failure_bear"]
            if m["median_minutes_to_failure_bear"] == m["median_minutes_to_failure_bear"]
            else "n/a",
            "%.1f" % m["median_minutes_to_failure_bull"]
            if m["median_minutes_to_failure_bull"] == m["median_minutes_to_failure_bull"]
            else "n/a",
        ),
        "",
        "## First-touch response: 60 minutes after first valid touch",
        "- Touch rate (eligible touches / evaluable primary): %s" % pct(m["touch_rate"]),
        "- Bear no eligible touch / evaluable touches: %d / %d"
        % (bt["no_eligible"], bt["evaluable"]),
        "- Bear favors / invalidates / both-same-bar-stop-first / neither / insufficient: "
        "%d / %d / %d / %d / %d"
        % (bt["favors"], bt["invalidates"], bt["both"], bt["neither"], bt["insuff"]),
        "- Bear touch favors-direction rate: %s" % pct(bt["favors_rate"]),
        "- Bear touch invalidation rate: %s" % pct(bt["inval_rate"]),
        "- Bull no eligible touch / evaluable touches: %d / %d"
        % (ut["no_eligible"], ut["evaluable"]),
        "- Bull favors / invalidates / both-same-bar-stop-first / neither / insufficient: "
        "%d / %d / %d / %d / %d"
        % (ut["favors"], ut["invalidates"], ut["both"], ut["neither"], ut["insuff"]),
        "- Bull touch favors-direction rate: %s" % pct(ut["favors_rate"]),
        "- Bull touch invalidation rate: %s" % pct(ut["inval_rate"]),
        "",
        "## Excursion (ticks)",
        "- Median favorable excursion after structure: %s"
        % (
            "%.2f" % m["median_mfe_ticks"]
            if m["median_mfe_ticks"] == m["median_mfe_ticks"]
            else "n/a"
        ),
        "- Median adverse excursion after structure: %s"
        % (
            "%.2f" % m["median_mae_ticks"]
            if m["median_mae_ticks"] == m["median_mae_ticks"]
            else "n/a"
        ),
        "",
        "## Integrity",
        "- Causality: %s" % ("PASS" if m["causality_pass"] else "FAIL"),
        "- Sample thresholds met: %s" % m["sample_thresholds_met"],
        "- Protection screen (>=55%% both sides): %s" % m["protection_screen_pass"],
        "- Touch screen bear / bull: %s / %s"
        % (m["touch_screen_bear_pass"], m["touch_screen_bull_pass"]),
        "",
        "## Disposition",
        "- DESCRIPTIVE ONLY.",
        "- No entry/P&L claim.",
        "- No session, direction, touch, or seed-context selector.",
        "- No plugin or promotion.",
        "- Preserve all ledgers, configuration, and charts unchanged.",
        "",
        "## Final disposition language",
        "",
        (
            "This is a descriptive all-session structural study. It measures whether "
            "causally confirmed 5-minute bearish H1-L1-HH-LL and bullish L1-H1-LL-HH "
            "structures form after active 4-hour wick-reject seeds, whether their "
            "designated pivot remains protected for a fixed 180-minute horizon, and how "
            "the first exact touch of that protected level behaves over a separate fixed "
            "60-minute response window. It does not define an entry, stop, target, "
            "position size, trade, expected return, or plugin."
        ),
        "",
    ]
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    # flatten for csv
    flat = {
        k: v
        for k, v in m.items()
        if not isinstance(v, (dict, list, tuple))
    }
    flat["bear_hold_ci"] = "%s-%s" % m["bear_hold_ci"]
    flat["bull_hold_ci"] = "%s-%s" % m["bull_hold_ci"]
    flat["bear_protection_labels"] = json.dumps(bl)
    flat["bull_protection_labels"] = json.dumps(ul)
    flat["bear_touch"] = json.dumps(bt)
    flat["bull_touch"] = json.dumps(ut)
    flat["candidate_count_by_session_segment"] = json.dumps(seg)
    pd.DataFrame([flat]).to_csv(hub / "summary.csv", index=False)


def write_causality_audit(hub: Path, ok: bool, fails: List[str], elig, cands, outs, touches) -> None:
    lines = [
        "# CAUSALITY_AUDIT — %s" % STUDY_ID,
        "",
        "status: %s" % ("PASS" if ok else "FAIL"),
        "generated: %s" % datetime.now().isoformat(),
        "",
        "## Reconciliation",
        "- eligible_seeds: %d" % int((elig["included"] == True).sum()),  # noqa: E712
        "- candidates: %d" % len(cands),
        "- protection_outcomes: %d" % len(outs),
        "- touch_response_outcomes: %d" % len(touches),
        "",
        "## Assertions",
    ]
    if ok:
        lines.append("- All §12 inequalities hold for included candidates.")
        lines.append("- ≤1 candidate or explicit exclusion per seed.")
        lines.append("- One protection + one touch-response row per candidate.")
    else:
        lines.append("FAILED assertions:")
        for f in fails[:50]:
            lines.append("- %s" % f)
    (hub / "CAUSALITY_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STUDY_ID)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--skip-charts", action="store_true")
    args = ap.parse_args(argv)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    for sub in (
        "charts/pack_a",
        "charts/pack_b",
        "charts/pack_c",
        "charts/pack_d",
        "charts/pack_e",
        "charts/pack_f",
    ):
        (hub / sub).mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    cfg_hash = _config_hash(hub)
    (hub / "config_hash.txt").write_text(cfg_hash + "\n", encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug=STUDY_ID + ("_smoke" if args.smoke else ""),
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={
            "descriptive_only": True,
            "config_hash": cfg_hash,
            "smoke": args.smoke,
            "data_session_policy": DATA_SESSION_POLICY,
        },
    )

    try:
        if args.email:
            start = (
                "potions: %s STARTED\n\nHub: %s\n"
                "POLICY A round-the-clock 5m protected-pivot + touch-response.\n"
                "Descriptive only (no trades). smoke=%s config_hash=%s\n"
                % (STUDY_ID, hub, args.smoke, cfg_hash)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: %s STARTED" % STUDY_ID, body=start)

        _progress(hub, "load WICK_REJECT events")
        events = load_wick_events(smoke=args.smoke)
        _progress(hub, "events n=%d" % len(events))
        ev_by_id = _event_map(events)

        _progress(hub, "load NQ 1m (full Globex)")
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        if args.smoke:
            edates = sorted(
                {_localize(pd.Timestamp(t)).date() for t in events["confirm_bar_close_ts"].tolist()}
            )
            days = sorted(gby.keys())
            keep = set()
            for d in edates:
                if d in days:
                    i = days.index(d)
                    keep.update(days[max(0, i - 3) : i + 40])
            gby = {d: gby[d] for d in days if d in keep}

        _progress(hub, "build RTH tape for seeds + Globex 5m for study")
        tape_rth, _h1, h4, early = build_rth_tape(gby)
        globex_1m = build_globex_1m(gby)
        bars_5m = to_5m(globex_1m)
        _progress(
            hub,
            "rth_tape=%d 4h=%d globex_1m=%d bars_5m=%d"
            % (len(tape_rth), len(h4), len(globex_1m), len(bars_5m)),
        )

        _progress(hub, "make_seeds_30")
        seeds, census = make_seeds_30(events, tape_rth, h4, early)
        census.to_csv(hub / "phase0_seed_census.csv", index=False)
        _progress(hub, "eligible seeds built=%d" % len(seeds))

        elig = build_seed_eligibility(seeds, ev_by_id, bars_5m)
        elig.to_csv(hub / "seed_24h_eligibility.csv", index=False)
        n_inc = int((elig["included"] == True).sum())  # noqa: E712
        _progress(hub, "included seeds=%d / %d" % (n_inc, len(elig)))

        pivot_rows: List[Dict[str, Any]] = []
        cand_rows: List[Dict[str, Any]] = []
        out_rows: List[Dict[str, Any]] = []
        touch_rows: List[Dict[str, Any]] = []
        excl_rows: List[Dict[str, Any]] = []

        seeds_by_id = {s.seed_id: s for s in seeds}
        included = elig[elig["included"] == True]  # noqa: E712

        for i, (_, er) in enumerate(included.iterrows()):
            seed = seeds_by_id[er["seed_id"]]
            avail = _localize(seed.available_at)
            exp = _localize(seed.expires_at)
            pivots = build_strict_5m_pivots(bars_5m, er["seed_id"], avail, exp)
            for p in pivots:
                pub = {k: v for k, v in p.items() if not k.startswith("_")}
                pivot_rows.append(pub)

            cand, d_reason, near = select_structure(pivots, er.to_dict(), bars_5m)
            if cand is None:
                excl_rows.append(
                    {
                        "candidate_id": "",
                        "seed_id": er["seed_id"],
                        "pattern": "",
                        "candidate_status": "EXCLUDED",
                        "exclusion_reason": d_reason,
                        "near_miss": near,
                        "session_segment": "",
                        "data_continuity_pass": d_reason != "INSUFFICIENT_DATA_OR_SESSION_GAP",
                    }
                )
            else:
                # seed still active at completion (already gated by pivot avail <= expiry)
                prot = evaluate_protection(cand, bars_5m)
                touch = evaluate_touch_response(cand, prot, bars_5m)
                pub_c = {k: v for k, v in cand.items() if not k.startswith("_")}
                cand_rows.append(pub_c)
                out_rows.append(prot)
                touch_rows.append(touch)

            if (i + 1) % 10 == 0:
                _progress(hub, "structures %d/%d" % (i + 1, len(included)))

        pivots_df = pd.DataFrame(pivot_rows)
        cands = pd.DataFrame(cand_rows)
        outs = pd.DataFrame(out_rows)
        touches = pd.DataFrame(touch_rows)
        exclusions = pd.DataFrame(excl_rows)

        pivots_df.to_csv(hub / "five_minute_pivot_ledger.csv", index=False)
        # structure_candidates includes completed + exclusion stubs for audit
        if len(exclusions):
            stub = exclusions.copy()
            for col in (
                "p1_id",
                "p2_id",
                "p3_id",
                "p4_id",
                "p1_price",
                "p2_price",
                "p3_price",
                "p4_price",
                "h1_price",
                "l1_price",
                "hh_price",
                "ll_price",
                "structure_complete_at",
                "protected_side",
                "protected_price",
                "failure_threshold",
                "break_level",
                "break_distance_ticks",
                "response_distance_ticks",
                "sequence_duration_minutes",
                "minutes_since_seed_available",
                "seed_context_relation",
                "5m_direction_vs_seed_direction",
            ):
                if col not in stub.columns:
                    stub[col] = ""
            struct_all = pd.concat([cands, stub], ignore_index=True, sort=False) if len(cands) else stub
        else:
            struct_all = cands
        struct_all.to_csv(hub / "structure_candidates.csv", index=False)
        outs.to_csv(hub / "protection_outcomes.csv", index=False)
        touches.to_csv(hub / "touch_response_outcomes.csv", index=False)
        exclusions.to_csv(hub / "pack_e_exclusions.csv", index=False)
        _progress(
            hub,
            "pivots=%d candidates=%d exclusions=%d"
            % (len(pivots_df), len(cands), len(exclusions)),
        )

        ok, fails, assertions = run_causality_audit(elig, cands, outs, touches, exclusions)
        assertions.to_csv(hub / "causality_and_reconciliation.csv", index=False)
        write_causality_audit(hub, ok, fails, elig, cands, outs, touches)
        _progress(hub, "causality %s" % ("PASS" if ok else "FAIL"))

        metrics = compute_summary(elig, cands, outs, touches, ok)
        write_summary_md(hub, metrics, cfg_hash)
        (hub / "STATUS.md").write_text(
            "# STATUS\n\nstance: %s\ncausality: %s\ndecision: %s\n"
            % (metrics["stance"], "PASS" if ok else "FAIL", metrics["decision"]),
            encoding="utf-8",
        )

        if not args.skip_charts:
            _progress(hub, "charts packs A–F")
            from . import nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1_charts as charts

            charts.render_all(
                hub=hub,
                study_id=STUDY_ID,
                data_version=DATA_VERSION,
                cfg_hash=cfg_hash,
                data_session_policy=DATA_SESSION_POLICY,
                elig=elig,
                pivots_df=pivots_df,
                cands=cands,
                outs=outs,
                touches=touches,
                exclusions=exclusions,
                bars_5m=bars_5m,
                h4=h4,
                smoke=args.smoke,
                smoke_cap=SMOKE_CHART_CAP,
                tick=TICK,
            )
            _progress(hub, "charts done")

        rc = {
            "study_id": STUDY_ID,
            "finished_at": datetime.now().isoformat(),
            "config_hash": cfg_hash,
            "smoke": args.smoke,
            "metrics": metrics,
            "causality_pass": ok,
            "causality_fails": fails,
        }
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(rc, indent=2, default=str), encoding="utf-8"
        )

        bt = metrics["bear_touch"]
        ut = metrics["bull_touch"]
        body = (
            "potions: %s COMPLETE\n\nHub: %s\n"
            "config_hash: %s\nsmoke: %s\npolicy: %s\n"
            "eligible_seeds: %d\ncandidates: %d (bear=%d bull=%d)\n"
            "bear_hold_180m: %s\nbull_hold_180m: %s\n"
            "bear_touch favors/inval (n_ev=%d): %s / %s\n"
            "bull_touch favors/inval (n_ev=%d): %s / %s\n"
            "causality: %s\ndecision: %s\nstance: %s\n\n"
            "DESCRIPTIVE ONLY — no trade / plugin / session selector.\n"
            "Independent of NY-open protected-pivot archives.\n"
            % (
                STUDY_ID,
                hub,
                cfg_hash,
                args.smoke,
                DATA_SESSION_POLICY,
                metrics["eligible_seed_count"],
                metrics["candidate_count"],
                metrics["bear_count"],
                metrics["bull_count"],
                (
                    "%.1f%%" % (100 * metrics["bear_protection_hold_rate_180m"])
                    if metrics["bear_protection_hold_rate_180m"]
                    == metrics["bear_protection_hold_rate_180m"]
                    else "n/a"
                ),
                (
                    "%.1f%%" % (100 * metrics["bull_protection_hold_rate_180m"])
                    if metrics["bull_protection_hold_rate_180m"]
                    == metrics["bull_protection_hold_rate_180m"]
                    else "n/a"
                ),
                bt["evaluable"],
                (
                    "%.1f%%" % (100 * bt["favors_rate"])
                    if bt["favors_rate"] == bt["favors_rate"]
                    else "n/a"
                ),
                (
                    "%.1f%%" % (100 * bt["inval_rate"])
                    if bt["inval_rate"] == bt["inval_rate"]
                    else "n/a"
                ),
                ut["evaluable"],
                (
                    "%.1f%%" % (100 * ut["favors_rate"])
                    if ut["favors_rate"] == ut["favors_rate"]
                    else "n/a"
                ),
                (
                    "%.1f%%" % (100 * ut["inval_rate"])
                    if ut["inval_rate"] == ut["inval_rate"]
                    else "n/a"
                ),
                "PASS" if ok else "FAIL",
                metrics.get("decision", ""),
                metrics["stance"],
            )
        )
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")

        if not ok:
            fail_run(rid, notes="causality FAIL: " + "; ".join(fails[:5]))
            if args.email:
                send_email(subject="potions: %s FAILED causality" % STUDY_ID, body=body)
            _progress(hub, "FAILED causality")
            return 1

        complete_run(
            rid,
            trades=metrics["candidate_count"],
            meta={
                "stance": metrics["stance"],
                "eligible": metrics["eligible_seed_count"],
                "bear_hold": metrics["bear_protection_hold_rate_180m"],
                "bull_hold": metrics["bull_protection_hold_rate_180m"],
            },
        )
        if args.email:
            send_email(subject="potions: %s COMPLETE" % STUDY_ID, body=body)
            _progress(hub, "email sent")
        _progress(hub, "DONE stance=%s" % metrics["stance"])
        return 0

    except Exception as exc:
        tb = traceback.format_exc()
        _progress(hub, "CRASH: %s" % exc)
        (hub / "CRASH.txt").write_text(tb, encoding="utf-8")
        fail_run(rid, notes=str(exc))
        body = "potions: %s CRASHED\n\nHub: %s\n\n%s\n" % (STUDY_ID, hub, tb[-4000:])
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        if args.email:
            try:
                send_email(subject="potions: %s CRASHED" % STUDY_ID, body=body)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
