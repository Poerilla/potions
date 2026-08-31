"""NQ 4h WICK_REJECT → round-the-clock 1m protected-AREA reaction (V1).

Descriptive only: no trades, fills, stops, targets, P&L, plugin, or S1/S2 coupling.
Measures MFE/MAE asymmetry after first interaction with a bounded pivot area.

Hub: live/state/nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1 --smoke --email
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1 --email
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from datetime import date, datetime, time
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
HUB = REPO / "live" / "state" / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
STUDY_ID = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
NY = "America/New_York"
DATA_VERSION = "nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst"
DATA_SESSION_POLICY = "POLICY_A_FULL_AVAILABLE_FUTURES_DATA"
STRUCTURE_HORIZON = pd.Timedelta(minutes=180)
REACTION_HORIZON = pd.Timedelta(minutes=60)
BAR_TD = pd.Timedelta(minutes=1)
GAP_TOL = pd.Timedelta(minutes=1) + pd.Timedelta(seconds=1)
SMOKE_CHART_CAP = 5
AREA_WIDTH_MIN = 4
AREA_WIDTH_MAX = 12


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
        "pivot=1m_1L1R_strict",
        "horizon_structure=180m",
        "horizon_reaction=60m",
        "area_width=min(12,max(4,ceil(0.25*break)))",
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


def area_width_ticks(break_distance_ticks: float) -> int:
    return int(min(AREA_WIDTH_MAX, max(AREA_WIDTH_MIN, math.ceil(0.25 * break_distance_ticks))))


def response_distance_ticks(break_distance_ticks: float) -> int:
    return int(max(4, math.ceil(0.25 * break_distance_ticks)))


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


def gap_before(bars_1m: pd.DataFrame, ts: pd.Timestamp) -> bool:
    ts = _localize(ts)
    if bars_1m is None or bars_1m.empty:
        return True
    prior = bars_1m.index[bars_1m.index < ts]
    if len(prior) == 0:
        return False
    last = _localize(prior[-1])
    return (ts - last) > GAP_TOL


def continuous_through(
    bars_1m: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Tuple[bool, str]:
    """Require 1m bars covering [start, end) without index gaps > 1m."""
    start = _localize(start)
    end = _localize(end)
    if end <= start:
        return True, ""
    window = bars_1m[(bars_1m.index >= start) & (bars_1m.index < end)]
    if window.empty:
        return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    first = _localize(window.index[0])
    if first > start + BAR_TD:
        return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    idx = list(window.index)
    for i in range(1, len(idx)):
        if _localize(idx[i]) - _localize(idx[i - 1]) > GAP_TOL:
            return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    last_open = _localize(idx[-1])
    if last_open + BAR_TD < end:
        return False, "INSUFFICIENT_DATA_OR_SESSION_GAP"
    return True, ""


def slice_continuous(
    bars_1m: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Tuple[pd.DataFrame, bool, str]:
    ok, reason = continuous_through(bars_1m, start, end)
    window = bars_1m[(bars_1m.index >= _localize(start)) & (bars_1m.index < _localize(end))]
    return window, ok, reason


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def build_seed_eligibility(
    seeds: List[Seed],
    events_by_id: Dict[str, pd.Series],
    bars_1m: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for seed in seeds:
        ev = events_by_id.get(seed.event_id, pd.Series(dtype=object))
        seed_dir = _seed_direction_from_event(ev) if len(ev) else ""
        pen = float(ev.get("penetration_ATR") or np.nan) if len(ev) else float("nan")
        width_atr = (seed.width / seed.atr20_4h) if seed.atr20_4h and seed.atr20_4h > 0 else float("nan")
        avail = _localize(seed.available_at)
        exp = _localize(seed.expires_at)
        after = bars_1m[bars_1m.index >= avail]
        included = False
        reason = ""
        first_bar = ""
        if after.empty:
            reason = "missing_1m_data"
        else:
            first = _localize(after.index[0])
            if first >= exp:
                reason = "expired_or_inactive_seed"
            else:
                first_bar = first.isoformat()
                included = True
                if (first - avail) > pd.Timedelta(hours=6) and gap_before(bars_1m, first):
                    pass  # still included; gap recorded only if formation crosses it
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
                "first_eligible_1m_bar": first_bar,
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


def build_strict_1m_pivots(
    bars_1m: pd.DataFrame,
    seed_id: str,
    avail: pd.Timestamp,
    expiry: pd.Timestamp,
) -> List[Dict[str, Any]]:
    """1L/1R strict pivots; pivot bar open >= avail; available_at <= expiry."""
    if bars_1m is None or len(bars_1m) < 3:
        return []
    avail = _localize(avail)
    expiry = _localize(expiry)
    window = bars_1m[(bars_1m.index >= avail - BAR_TD) & (bars_1m.index < expiry + BAR_TD)]
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
        bar_i = int(round((bar_open - avail).total_seconds() / 60.0))
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
    bars_1m: pd.DataFrame,
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

        form_ok, form_reason = continuous_through(bars_1m, a["_bar_open"], d["_avail"])
        if not form_ok:
            return None, form_reason, "formation crossed session/data gap"

        prices = [a["_price"], b["_price"], c["_price"], d["_price"]]
        if pattern == "BEAR":
            h1, l1, hh, ll = a["_price"], b["_price"], c["_price"], d["_price"]
            protected_side = "HIGH"
            protected_price = hh
            break_level = l1
            structure_ref = ll
            break_dist = (hh - l1) / TICK
            aw = area_width_ticks(break_dist)
            inner = protected_price
            outer = protected_price + aw * TICK
        else:
            l1, h1, ll, hh = a["_price"], b["_price"], c["_price"], d["_price"]
            protected_side = "LOW"
            protected_price = ll
            break_level = h1
            structure_ref = hh
            break_dist = (h1 - ll) / TICK
            aw = area_width_ticks(break_dist)
            inner = protected_price
            outer = protected_price - aw * TICK

        resp_dist = response_distance_ticks(break_dist)
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
            "structure_reference_price": structure_ref,
            "protected_side": protected_side,
            "protected_pivot_price": protected_price,
            "break_level": break_level,
            "break_distance_ticks": round(break_dist, 4),
            "area_width_ticks": aw,
            "inner_area_edge": inner,
            "outer_area_edge": outer,
            "response_distance_ticks": resp_dist,
            "sequence_duration_minutes": round(seq_min, 4),
            "minutes_since_seed_available": round(since_seed, 4),
            "session_segment": session_segment(complete),
            "seed_context_relation": _seed_context_relation(
                prices, float(elig["seed_high"]), float(elig["seed_low"])
            ),
            "one_minute_direction_vs_seed_direction": _dir_vs_seed(
                pattern_code, str(elig["seed_direction"])
            ),
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

    # Bounded intervening scan: 1m pivots are dense; full O(n^4) is intractable.
    # Ambiguity only matters near the first formation attempt (early pivots / short span).
    n_scan = min(len(pivots), 160)
    max_span = 48
    for i in range(n_scan):
        for j in range(i + 1, min(i + max_span, n_scan)):
            for k in range(j + 1, min(j + max_span, n_scan)):
                for m in range(k + 1, min(k + max_span, n_scan)):
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
# Contact depth / structure + contact excursions
# ---------------------------------------------------------------------------


def classify_area_contact(
    pattern: str,
    prot: float,
    outer: float,
    highest: float,
    lowest: float,
) -> str:
    if pattern == "BEAR":
        if highest < prot - 1e-12:
            return "NO_AREA_CONTACT"
        if highest < prot + TICK - 1e-12:
            return "TOUCH_ONLY"
        if highest < outer - 1e-12:
            return "SHALLOW_TRADE_THROUGH"
        return "DEEP_TRADE_THROUGH"
    # BULL
    if lowest > prot + 1e-12:
        return "NO_AREA_CONTACT"
    if lowest > prot - TICK + 1e-12:
        return "TOUCH_ONLY"
    if lowest > outer + 1e-12:
        return "SHALLOW_TRADE_THROUGH"
    return "DEEP_TRADE_THROUGH"


def evaluate_structure_excursion(cand: Dict[str, Any], bars_1m: pd.DataFrame) -> Dict[str, Any]:
    complete = cand["_complete"]
    horizon_end = complete + STRUCTURE_HORIZON
    window, ok, gap_reason = slice_continuous(bars_1m, complete, horizon_end)
    pattern = cand["_pattern"]
    struct_ref = float(cand["structure_reference_price"])
    prot = float(cand["protected_pivot_price"])
    outer = float(cand["outer_area_edge"])

    out: Dict[str, Any] = {
        "candidate_id": cand["candidate_id"],
        "evaluation_start": complete.isoformat(),
        "structure_horizon_end": horizon_end.isoformat(),
        "structure_reference_price": struct_ref,
        "mfe_structure_ticks": np.nan,
        "mae_structure_ticks": np.nan,
        "structure_excursion_rr": np.nan,
        "zero_mae_flag": False,
        "highest_high_in_window": np.nan,
        "lowest_low_in_window": np.nan,
        "mfe_timestamp": "",
        "mae_timestamp": "",
        "area_contact_classification": "INSUFFICIENT_DATA_OR_SESSION_GAP",
        "first_contact_ts": "",
        "first_contact_bar_high": np.nan,
        "first_contact_bar_low": np.nan,
        "first_contact_depth_ticks": np.nan,
        "data_complete": False,
        "gap_or_exclusion_reason": gap_reason if not ok else "",
    }
    if not ok or window.empty:
        return out

    hi_arr = window["high"].to_numpy(dtype=float)
    lo_arr = window["low"].to_numpy(dtype=float)
    idx = window.index
    highest = float(np.max(hi_arr))
    lowest = float(np.min(lo_arr))
    out["highest_high_in_window"] = highest
    out["lowest_low_in_window"] = lowest

    if pattern == "BEAR":
        mfe = (struct_ref - lowest) / TICK
        mae = (highest - struct_ref) / TICK
        mfe_i = int(np.argmin(lo_arr))
        mae_i = int(np.argmax(hi_arr))
    else:
        mfe = (highest - struct_ref) / TICK
        mae = (struct_ref - lowest) / TICK
        mfe_i = int(np.argmax(hi_arr))
        mae_i = int(np.argmin(lo_arr))

    mfe = max(0.0, float(mfe))
    mae = max(0.0, float(mae))
    out["mfe_structure_ticks"] = round(mfe, 4)
    out["mae_structure_ticks"] = round(mae, 4)
    out["zero_mae_flag"] = mae <= 1e-12
    if mae > 1e-12:
        out["structure_excursion_rr"] = round(mfe / mae, 6)
    out["mfe_timestamp"] = (_localize(idx[mfe_i]) + BAR_TD).isoformat()
    out["mae_timestamp"] = (_localize(idx[mae_i]) + BAR_TD).isoformat()

    depth_class = classify_area_contact(pattern, prot, outer, highest, lowest)
    out["area_contact_classification"] = depth_class

    # First area contact (reach protected pivot)
    first_ts = None
    first_hi = first_lo = None
    depth_ticks = np.nan
    for ts, row in window.iterrows():
        ts = _localize(ts)
        hi = float(row["high"])
        lo = float(row["low"])
        if pattern == "BEAR":
            if hi >= prot - 1e-12:
                first_ts = ts
                first_hi, first_lo = hi, lo
                depth_ticks = max(0.0, (hi - prot) / TICK)
                break
        else:
            if lo <= prot + 1e-12:
                first_ts = ts
                first_hi, first_lo = hi, lo
                depth_ticks = max(0.0, (prot - lo) / TICK)
                break

    if first_ts is not None:
        out["first_contact_ts"] = first_ts.isoformat()
        out["first_contact_bar_high"] = first_hi
        out["first_contact_bar_low"] = first_lo
        out["first_contact_depth_ticks"] = round(float(depth_ticks), 4)
    elif depth_class == "NO_AREA_CONTACT":
        pass
    out["data_complete"] = True
    return out


def evaluate_contact_reaction(
    cand: Dict[str, Any],
    struct_out: Dict[str, Any],
    bars_1m: pd.DataFrame,
) -> Dict[str, Any]:
    pattern = cand["_pattern"]
    prot = float(cand["protected_pivot_price"])
    outer = float(cand["outer_area_edge"])
    aw = int(cand["area_width_ticks"])
    resp_dist = int(cand["response_distance_ticks"])
    if pattern == "BEAR":
        fav_thr = prot - resp_dist * TICK
    else:
        fav_thr = prot + resp_dist * TICK

    base: Dict[str, Any] = {
        "candidate_id": cand["candidate_id"],
        "area_contact_classification": struct_out.get("area_contact_classification", ""),
        "contact_eligible": False,
        "no_contact_reason": "",
        "first_contact_ts": "",
        "contact_reference_price": prot,
        "reaction_horizon_end": "",
        "area_width_ticks": aw,
        "outer_area_edge": outer,
        "response_distance_ticks": resp_dist,
        "favorable_response_threshold": fav_thr,
        "mfe_contact_ticks": np.nan,
        "mae_contact_ticks": np.nan,
        "contact_excursion_rr": np.nan,
        "zero_mae_flag": False,
        "highest_high_in_reaction_window": np.nan,
        "lowest_low_in_reaction_window": np.nan,
        "mfe_contact_timestamp": "",
        "mae_contact_timestamp": "",
        "path_order_label": "",
        "favorable_response_first_ts": "",
        "outer_area_breach_first_ts": "",
        "data_complete": False,
        "gap_or_exclusion_reason": "",
    }

    if not struct_out.get("data_complete"):
        base["no_contact_reason"] = "structure_horizon_insufficient"
        base["path_order_label"] = "INSUFFICIENT_DATA_OR_SESSION_GAP"
        return base

    depth = struct_out.get("area_contact_classification", "")
    if depth == "NO_AREA_CONTACT" or not struct_out.get("first_contact_ts"):
        base["no_contact_reason"] = "NO_AREA_CONTACT"
        base["path_order_label"] = "NO_AREA_CONTACT"
        return base

    contact_open = _localize(pd.Timestamp(struct_out["first_contact_ts"]))
    # first_contact_ts stored as bar open; reaction includes that bar for 60m
    reaction_end = contact_open + REACTION_HORIZON
    base["first_contact_ts"] = contact_open.isoformat()
    base["reaction_horizon_end"] = reaction_end.isoformat()
    base["contact_eligible"] = True

    cont_ok, cont_reason = continuous_through(bars_1m, contact_open, reaction_end)
    if not cont_ok:
        base["path_order_label"] = "INSUFFICIENT_DATA_OR_SESSION_GAP"
        base["gap_or_exclusion_reason"] = cont_reason
        base["no_contact_reason"] = "INSUFFICIENT_DATA_OR_SESSION_GAP"
        base["data_complete"] = False
        return base

    resp_win = bars_1m[(bars_1m.index >= contact_open) & (bars_1m.index < reaction_end)]
    if resp_win.empty:
        base["path_order_label"] = "INSUFFICIENT_DATA_OR_SESSION_GAP"
        base["gap_or_exclusion_reason"] = "empty_reaction_window"
        return base

    hi_arr = resp_win["high"].to_numpy(dtype=float)
    lo_arr = resp_win["low"].to_numpy(dtype=float)
    idx = resp_win.index
    highest = float(np.max(hi_arr))
    lowest = float(np.min(lo_arr))
    base["highest_high_in_reaction_window"] = highest
    base["lowest_low_in_reaction_window"] = lowest

    if pattern == "BEAR":
        mfe = (prot - lowest) / TICK
        mae = (highest - prot) / TICK
        mfe_i = int(np.argmin(lo_arr))
        mae_i = int(np.argmax(hi_arr))
    else:
        mfe = (highest - prot) / TICK
        mae = (prot - lowest) / TICK
        mfe_i = int(np.argmax(hi_arr))
        mae_i = int(np.argmin(lo_arr))

    mfe = max(0.0, float(mfe))
    mae = max(0.0, float(mae))
    base["mfe_contact_ticks"] = round(mfe, 4)
    base["mae_contact_ticks"] = round(mae, 4)
    base["zero_mae_flag"] = mae <= 1e-12
    if mae > 1e-12:
        base["contact_excursion_rr"] = round(mfe / mae, 6)
    base["mfe_contact_timestamp"] = (_localize(idx[mfe_i]) + BAR_TD).isoformat()
    base["mae_contact_timestamp"] = (_localize(idx[mae_i]) + BAR_TD).isoformat()

    # Path ordering diagnostic
    fav_ts = None
    outer_ts = None
    same_bar_adverse = False
    for ts, row in resp_win.iterrows():
        ts = _localize(ts)
        bar_close = ts + BAR_TD
        hi = float(row["high"])
        lo = float(row["low"])
        if pattern == "BEAR":
            hit_fav = lo <= fav_thr + 1e-12
            hit_outer = hi >= outer - 1e-12
        else:
            hit_fav = hi >= fav_thr - 1e-12
            hit_outer = lo <= outer + 1e-12
        if hit_fav and hit_outer:
            same_bar_adverse = True
            fav_ts = bar_close
            outer_ts = bar_close
            break
        if hit_outer and outer_ts is None:
            outer_ts = bar_close
            break
        if hit_fav and fav_ts is None:
            fav_ts = bar_close
            break

    if fav_ts is not None:
        base["favorable_response_first_ts"] = fav_ts.isoformat()
    if outer_ts is not None:
        base["outer_area_breach_first_ts"] = outer_ts.isoformat()

    if same_bar_adverse:
        base["path_order_label"] = "BOTH_SAME_1M_BAR_ADVERSE_FIRST"
    elif outer_ts is not None and (fav_ts is None or outer_ts <= fav_ts):
        base["path_order_label"] = "OUTER_AREA_BREACH_FIRST"
    elif fav_ts is not None:
        base["path_order_label"] = "FAVORABLE_RESPONSE_FIRST"
    else:
        base["path_order_label"] = "NEITHER_BY_REACTION_HORIZON"

    base["data_complete"] = True
    return base


# ---------------------------------------------------------------------------
# Causality / aggregates
# ---------------------------------------------------------------------------


def run_causality_audit(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> Tuple[bool, List[str], pd.DataFrame]:
    fails: List[str] = []
    assertions: List[Dict[str, Any]] = []
    included = elig[elig["included"] == True]  # noqa: E712

    cand_seeds = set(cands["seed_id"].tolist()) if len(cands) else set()
    excl_seeds = set(exclusions["seed_id"].tolist()) if len(exclusions) else set()
    for sid in included["seed_id"].tolist():
        n = int(sid in cand_seeds) + int(sid in excl_seeds)
        if n != 1:
            fails.append("seed %s candidate/exclusion count=%d" % (sid, n))

    if len(cands) and cands["seed_id"].duplicated().any():
        fails.append("multiple candidates for one seed")
    if len(cands) != len(structs):
        fails.append("candidates %d != structure outcomes %d" % (len(cands), len(structs)))
    if len(cands) != len(contacts):
        fails.append("candidates %d != contact outcomes %d" % (len(cands), len(contacts)))

    for _, c in cands.iterrows():
        notes = []
        row_ok = True
        seed_rows = included[included["seed_id"] == c["seed_id"]]
        if seed_rows.empty:
            fails.append("%s missing eligibility" % c["candidate_id"])
            assertions.append(
                {
                    "candidate_id": c["candidate_id"],
                    "overall_pass": False,
                    "failure_reason": "missing_eligibility",
                }
            )
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
            "no_cross_gap_formation_pass": bool(c.get("data_continuity_pass", True)),
            "structure_horizon_timestamp_pass": True,
            "first_contact_timestamp_pass": True,
            "reaction_horizon_timestamp_pass": True,
            "chart_ledger_match_pass": True,
        }
        if complete != p4a:
            checks["no_future_data_pass"] = False
            notes.append("complete_ne_p4a")

        o = structs[structs["candidate_id"] == c["candidate_id"]]
        if len(o):
            o0 = o.iloc[0]
            st = _localize(pd.Timestamp(o0["evaluation_start"]))
            he = _localize(pd.Timestamp(o0["structure_horizon_end"]))
            if st != complete or he != complete + STRUCTURE_HORIZON:
                checks["structure_horizon_timestamp_pass"] = False
                notes.append("structure_horizon")
            if o0.get("first_contact_ts"):
                fcts = _localize(pd.Timestamp(o0["first_contact_ts"]))
                if not (fcts >= complete and fcts < complete + STRUCTURE_HORIZON):
                    checks["first_contact_timestamp_pass"] = False
                    notes.append("first_contact_ts_window")

        t = contacts[contacts["candidate_id"] == c["candidate_id"]]
        if len(t):
            t0 = t.iloc[0]
            if t0.get("contact_eligible") and t0.get("first_contact_ts") and t0.get("data_complete"):
                fcts = _localize(pd.Timestamp(t0["first_contact_ts"]))
                rhe = _localize(pd.Timestamp(t0["reaction_horizon_end"]))
                if rhe != fcts + REACTION_HORIZON:
                    checks["reaction_horizon_timestamp_pass"] = False
                    notes.append("reaction_horizon")

        for k, v in checks.items():
            if not v:
                row_ok = False
                notes.append(k)
                fails.append("%s %s" % (c["candidate_id"], k))

        assertions.append(
            {
                "candidate_id": c["candidate_id"],
                **{k: bool(v) for k, v in checks.items()},
                "overall_pass": row_ok,
                "failure_reason": ";".join(notes),
            }
        )

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
            "no_cross_gap_formation_pass": True,
            "structure_horizon_timestamp_pass": True,
            "first_contact_timestamp_pass": True,
            "reaction_horizon_timestamp_pass": True,
            "chart_ledger_match_pass": True,
        }
    )
    return len(fails) == 0, fails, pd.DataFrame(assertions)


def _safe_mean(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.mean()) if len(s) else float("nan")


def _safe_median(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.median()) if len(s) else float("nan")


def _safe_quantile(s: pd.Series, q: float) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.quantile(q)) if len(s) else float("nan")


def _top_mfe_contribution(mfe: pd.Series, k: int) -> float:
    s = pd.to_numeric(mfe, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    total = float(s.sum())
    if total <= 0:
        return 0.0
    top = float(s.nlargest(min(k, len(s))).sum())
    return 100.0 * top / total


def _calendar_concentration_note(blocks: pd.Series) -> str:
    if blocks is None or blocks.empty:
        return "n/a"
    vc = blocks.value_counts()
    if vc.empty:
        return "n/a"
    top = vc.iloc[0]
    n = int(vc.sum())
    pct = 100.0 * top / n if n else 0.0
    return "top_block=%s share=%.1f%% (n=%d)" % (vc.index[0], pct, n)


def _excursion_stats(
    mfe: pd.Series,
    mae: pd.Series,
    rr: pd.Series,
    zero_mae: pd.Series,
    path_labels: Optional[pd.Series] = None,
    calendar_blocks: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    mfe_n = pd.to_numeric(mfe, errors="coerce")
    mae_n = pd.to_numeric(mae, errors="coerce")
    valid = mfe_n.notna() & mae_n.notna()
    mfe_v = mfe_n[valid]
    mae_v = mae_n[valid]
    zero_n = int(pd.Series(zero_mae).fillna(False).astype(bool).sum()) if len(zero_mae) else 0
    mean_mfe = _safe_mean(mfe_v)
    mean_mae = _safe_mean(mae_v)
    mean_rr = (mean_mfe / mean_mae) if (mean_mae == mean_mae and mean_mae > 0) else float("nan")

    rr_n = pd.to_numeric(rr, errors="coerce")
    zm = pd.Series(zero_mae).reindex(rr_n.index).fillna(False).astype(bool) if len(rr) else pd.Series(dtype=bool)
    rr_indiv = rr_n[~zm & rr_n.notna()]

    path_counts = {
        "favorable_response_first_count": 0,
        "outer_area_breach_first_count": 0,
        "both_same_bar_adverse_first_count": 0,
        "neither_by_horizon_count": 0,
    }
    if path_labels is not None and len(path_labels):
        path_counts["favorable_response_first_count"] = int(
            (path_labels == "FAVORABLE_RESPONSE_FIRST").sum()
        )
        path_counts["outer_area_breach_first_count"] = int(
            (path_labels == "OUTER_AREA_BREACH_FIRST").sum()
        )
        path_counts["both_same_bar_adverse_first_count"] = int(
            (path_labels == "BOTH_SAME_1M_BAR_ADVERSE_FIRST").sum()
        )
        path_counts["neither_by_horizon_count"] = int(
            (path_labels == "NEITHER_BY_REACTION_HORIZON").sum()
        )

    return {
        "record_count": int(valid.sum()),
        "zero_mae_count": zero_n,
        "mean_mfe_ticks": mean_mfe,
        "mean_mae_ticks": mean_mae,
        "mean_excursion_rr": mean_rr,
        "median_mfe_ticks": _safe_median(mfe_v),
        "median_mae_ticks": _safe_median(mae_v),
        "median_excursion_rr": _safe_median(rr_indiv),
        "p25_mfe_ticks": _safe_quantile(mfe_v, 0.25),
        "p75_mfe_ticks": _safe_quantile(mfe_v, 0.75),
        "p25_mae_ticks": _safe_quantile(mae_v, 0.25),
        "p75_mae_ticks": _safe_quantile(mae_v, 0.75),
        **path_counts,
        "top_1_mfe_contribution_pct": _top_mfe_contribution(mfe_v, 1),
        "top_3_mfe_contribution_pct": _top_mfe_contribution(mfe_v, 3),
        "calendar_block_concentration_note": _calendar_concentration_note(
            calendar_blocks if calendar_blocks is not None else pd.Series(dtype=object)
        ),
    }


def build_aggregate_summary(
    cands: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
) -> pd.DataFrame:
    if not len(cands):
        return pd.DataFrame()

    merged = cands.merge(structs, on="candidate_id", how="left", suffixes=("", "_s")).merge(
        contacts, on="candidate_id", how="left", suffixes=("", "_c")
    )

    struct_ok = merged[merged["data_complete"] == True]  # noqa: E712
    # Prefer structure data_complete from structs (first merge keeps it as data_complete)
    if "data_complete_s" in merged.columns:
        struct_ok = merged[merged["data_complete"] == True]  # noqa: E712

    contact_ok = merged[
        (merged.get("contact_eligible", False) == True)  # noqa: E712
        & (merged.get("data_complete_c", merged.get("data_complete", False)) == True)  # noqa: E712
    ]
    # contact data_complete column after merge: contacts use data_complete -> may be data_complete_c
    if "data_complete_c" in merged.columns:
        contact_ok = merged[
            (merged["contact_eligible"] == True)  # noqa: E712
            & (merged["data_complete_c"] == True)  # noqa: E712
        ]
    else:
        # if only one data_complete, use contact_eligible + finite mfe_contact
        contact_ok = merged[
            (merged["contact_eligible"] == True)  # noqa: E712
            & merged["mfe_contact_ticks"].notna()
        ]

    rows = []

    def add_struct(label: str, sub: pd.DataFrame) -> None:
        stats = _excursion_stats(
            sub["mfe_structure_ticks"],
            sub["mae_structure_ticks"],
            sub["structure_excursion_rr"],
            sub["zero_mae_flag"],
            path_labels=None,
            calendar_blocks=sub["calendar_block"] if "calendar_block" in sub.columns else None,
        )
        mean_rr = stats["mean_excursion_rr"]
        if stats["record_count"] <= 0:
            interp = "INSUFFICIENT_SAMPLE"
        elif mean_rr == mean_rr and mean_rr > 1.0 and stats["mean_mfe_ticks"] > stats["mean_mae_ticks"]:
            interp = "MEAN_MFE_GT_MEAN_MAE"
        else:
            interp = "MEAN_MFE_NOT_GT_MEAN_MAE"
        rows.append({"population_label": label, **stats, "interpretation_status": interp})

    def add_contact(label: str, sub: pd.DataFrame) -> None:
        zm_col = "zero_mae_flag_c" if "zero_mae_flag_c" in sub.columns else "zero_mae_flag"
        # After merge, contact zero_mae may collide — prefer contact columns
        if "zero_mae_flag_c" not in sub.columns and "mfe_contact_ticks" in sub.columns:
            # structure zero_mae_flag kept; contact also named zero_mae_flag -> pandas suffixes
            pass
        path_col = "path_order_label"
        stats = _excursion_stats(
            sub["mfe_contact_ticks"],
            sub["mae_contact_ticks"],
            sub["contact_excursion_rr"],
            sub[zm_col] if zm_col in sub.columns else sub.get("zero_mae_flag", pd.Series(dtype=bool)),
            path_labels=sub[path_col] if path_col in sub.columns else None,
            calendar_blocks=sub["calendar_block"] if "calendar_block" in sub.columns else None,
        )
        mean_rr = stats["mean_excursion_rr"]
        if stats["record_count"] <= 0:
            interp = "INSUFFICIENT_SAMPLE"
        elif mean_rr == mean_rr and mean_rr > 1.0 and stats["mean_mfe_ticks"] > stats["mean_mae_ticks"]:
            interp = "MEAN_MFE_GT_MEAN_MAE"
        else:
            interp = "MEAN_MFE_NOT_GT_MEAN_MAE"
        rows.append({"population_label": label, **stats, "interpretation_status": interp})

    # Structure populations — use struct data_complete
    s_ok = merged[merged["data_complete"] == True].copy()  # noqa: E712
    # When both have data_complete, left (struct) keeps name data_complete
    add_struct("ALL_VALID_CANDIDATES", s_ok)
    add_struct("BEAR_VALID_CANDIDATES", s_ok[s_ok["pattern"].str.startswith("BEAR")])
    add_struct("BULL_VALID_CANDIDATES", s_ok[s_ok["pattern"].str.startswith("BULL")])

    # Contact populations
    if "data_complete_c" in merged.columns:
        c_ok = merged[
            (merged["contact_eligible"] == True) & (merged["data_complete_c"] == True)  # noqa: E712
        ].copy()
        # contact zero_mae_flag likely zero_mae_flag_c
        if "zero_mae_flag_c" not in c_ok.columns and "zero_mae_flag" in c_ok.columns:
            # may be structure's — rebuild from contact mae
            c_ok = c_ok.copy()
            c_ok["zero_mae_flag_c"] = pd.to_numeric(c_ok["mae_contact_ticks"], errors="coerce").fillna(1) <= 1e-12
    else:
        c_ok = merged[
            (merged["contact_eligible"] == True) & merged["mfe_contact_ticks"].notna()  # noqa: E712
        ].copy()
        c_ok["zero_mae_flag_c"] = pd.to_numeric(c_ok["mae_contact_ticks"], errors="coerce").fillna(1) <= 1e-12

    add_contact("ALL_VALID_CONTACTS", c_ok)
    add_contact("BEAR_VALID_CONTACTS", c_ok[c_ok["pattern"].str.startswith("BEAR")])
    add_contact("BULL_VALID_CONTACTS", c_ok[c_ok["pattern"].str.startswith("BULL")])

    depth_col = "area_contact_classification"
    if depth_col + "_c" in c_ok.columns:
        depth_col = "area_contact_classification_c"
    # Prefer contact classification from contacts table
    if "area_contact_classification" in c_ok.columns:
        add_contact("TOUCH_ONLY_CONTACTS", c_ok[c_ok["area_contact_classification"] == "TOUCH_ONLY"])
        add_contact(
            "SHALLOW_TRADE_THROUGH_CONTACTS",
            c_ok[c_ok["area_contact_classification"] == "SHALLOW_TRADE_THROUGH"],
        )
        add_contact(
            "DEEP_TRADE_THROUGH_CONTACTS",
            c_ok[c_ok["area_contact_classification"] == "DEEP_TRADE_THROUGH"],
        )

    return pd.DataFrame(rows)


def compute_summary(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
    agg: pd.DataFrame,
    causality_ok: bool,
) -> Dict[str, Any]:
    eligible_n = int((elig["included"] == True).sum())  # noqa: E712
    excl = elig[elig["included"] == False]  # noqa: E712
    n_cand = len(cands)
    bear = cands[cands["pattern"].str.startswith("BEAR")] if n_cand else cands
    bull = cands[cands["pattern"].str.startswith("BULL")] if n_cand else cands

    merged = (
        cands.merge(structs, on="candidate_id", how="left", suffixes=("", "_s")).merge(
            contacts, on="candidate_id", how="left", suffixes=("", "_c")
        )
        if n_cand
        else pd.DataFrame()
    )

    def side_block(sub: pd.DataFrame, pattern_prefix: str) -> Dict[str, Any]:
        if sub is None or sub.empty:
            return {
                "candidate_count": 0,
                "evaluable_count": 0,
                "gap_incomplete_count": 0,
                "depth_counts": {},
                "first_contact_count": 0,
            }
        s_ok = sub[sub["data_complete"] == True]  # noqa: E712
        gap_n = int((sub["data_complete"] != True).sum())  # noqa: E712
        depth = (
            s_ok["area_contact_classification"].value_counts().to_dict() if len(s_ok) else {}
        )
        if "data_complete_c" in sub.columns:
            c_ok = sub[(sub["contact_eligible"] == True) & (sub["data_complete_c"] == True)]  # noqa: E712
        else:
            c_ok = sub[(sub["contact_eligible"] == True) & sub["mfe_contact_ticks"].notna()]  # noqa: E712
        return {
            "candidate_count": len(sub),
            "evaluable_count": len(s_ok),
            "gap_incomplete_count": gap_n,
            "depth_counts": depth,
            "first_contact_count": len(c_ok),
        }

    bear_m = merged[merged["pattern"].str.startswith("BEAR")] if n_cand else merged
    bull_m = merged[merged["pattern"].str.startswith("BULL")] if n_cand else merged

    def agg_row(label: str) -> Dict[str, Any]:
        if agg is None or agg.empty:
            return {}
        r = agg[agg["population_label"] == label]
        return r.iloc[0].to_dict() if len(r) else {}

    bear_struct = agg_row("BEAR_VALID_CANDIDATES")
    bull_struct = agg_row("BULL_VALID_CANDIDATES")
    all_struct = agg_row("ALL_VALID_CANDIDATES")
    bear_contact = agg_row("BEAR_VALID_CONTACTS")
    bull_contact = agg_row("BULL_VALID_CONTACTS")
    all_contact = agg_row("ALL_VALID_CONTACTS")

    med_since = float(cands["minutes_since_seed_available"].median()) if n_cand else float("nan")
    med_seq = float(cands["sequence_duration_minutes"].median()) if n_cand else float("nan")
    seg_counts = cands["session_segment"].value_counts().to_dict() if n_cand else {}

    # Primary question on contact populations
    def primary_pass(row: Dict[str, Any]) -> bool:
        if not row or not row.get("record_count"):
            return False
        mmfe = row.get("mean_mfe_ticks", float("nan"))
        mmae = row.get("mean_mae_ticks", float("nan"))
        mrr = row.get("mean_excursion_rr", float("nan"))
        return (
            mmfe == mmfe
            and mmae == mmae
            and mrr == mrr
            and mmfe > mmae
            and mrr > 1.0
        )

    bear_q = primary_pass(bear_contact)
    bull_q = primary_pass(bull_contact)

    sample_ok = eligible_n >= 40 and n_cand >= 20 and len(bear) >= 8 and len(bull) >= 8

    if not causality_ok:
        stance = "DESCRIPTIVE ONLY / CAUSALITY FAIL"
        decision = "CAUSALITY_FAIL"
    elif not sample_ok:
        stance = "DESCRIPTIVE ONLY — INSUFFICIENT SAMPLE FOR INTERPRETATION"
        decision = "INSUFFICIENT_SAMPLE"
    elif bear_q and bull_q:
        stance = (
            "DESCRIPTIVE OBSERVATION — both sides mean contact MFE/MAE > 1 "
            "(NOT a trade authorization)"
        )
        decision = "BOTH_SIDES_MEAN_ASYMMETRY"
    elif bear_q or bull_q:
        stance = "ONE-SIDED DESCRIPTIVE ASYMMETRY ONLY"
        decision = "ONE_SIDED_ASYMMETRY"
    else:
        stance = "DESCRIPTIVE ONLY — contact mean MFE/MAE asymmetry not supported"
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
        "bear_side": side_block(bear_m, "BEAR"),
        "bull_side": side_block(bull_m, "BULL"),
        "all_structure": all_struct,
        "bear_structure": bear_struct,
        "bull_structure": bull_struct,
        "all_contact": all_contact,
        "bear_contact": bear_contact,
        "bull_contact": bull_contact,
        "bear_primary_question_pass": bear_q,
        "bull_primary_question_pass": bull_q,
        "causality_pass": causality_ok,
        "sample_thresholds_met": sample_ok,
        "decision": decision,
        "stance": stance,
        "data_session_policy": DATA_SESSION_POLICY,
        "non_promotion": True,
    }


def _fmt(x: Any, nd: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if v != v:
        return "n/a"
    return ("%." + str(nd) + "f") % v


def write_summary_md(hub: Path, metrics: Dict[str, Any], cfg_hash: str, agg: pd.DataFrame) -> None:
    m = metrics
    bs = m["bear_side"]
    us = m["bull_side"]
    bstr = m["bear_structure"]
    ustr = m["bull_structure"]
    bct = m["bear_contact"]
    uct = m["bull_contact"]
    astr = m["all_structure"]
    act = m["all_contact"]

    seg = m.get("candidate_count_by_session_segment") or {}
    seg_line = ", ".join("%s=%d" % (k, v) for k, v in sorted(seg.items(), key=lambda x: -x[1]))

    def depth_line(d: Dict[str, int]) -> str:
        keys = [
            "NO_AREA_CONTACT",
            "TOUCH_ONLY",
            "SHALLOW_TRADE_THROUGH",
            "DEEP_TRADE_THROUGH",
        ]
        return " / ".join("%s=%d" % (k, int(d.get(k, 0))) for k in keys)

    def side_exc(label: str, st: Dict, ct: Dict, side: Dict) -> List[str]:
        return [
            "### %s" % label,
            "- Candidates / evaluable / gap-incomplete: %d / %d / %d"
            % (side["candidate_count"], side["evaluable_count"], side["gap_incomplete_count"]),
            "- Contact depth (evaluable): %s" % depth_line(side.get("depth_counts") or {}),
            "- First-contact evaluable: %d" % side["first_contact_count"],
            "- Structure mean MFE / MAE / RR: %s / %s / %s"
            % (
                _fmt(st.get("mean_mfe_ticks")),
                _fmt(st.get("mean_mae_ticks")),
                _fmt(st.get("mean_excursion_rr"), 3),
            ),
            "- Structure median MFE / MAE / indiv RR: %s / %s / %s"
            % (
                _fmt(st.get("median_mfe_ticks")),
                _fmt(st.get("median_mae_ticks")),
                _fmt(st.get("median_excursion_rr"), 3),
            ),
            "- Contact mean MFE / MAE / RR: %s / %s / %s"
            % (
                _fmt(ct.get("mean_mfe_ticks")),
                _fmt(ct.get("mean_mae_ticks")),
                _fmt(ct.get("mean_excursion_rr"), 3),
            ),
            "- Contact median MFE / MAE / indiv RR: %s / %s / %s"
            % (
                _fmt(ct.get("median_mfe_ticks")),
                _fmt(ct.get("median_mae_ticks")),
                _fmt(ct.get("median_excursion_rr"), 3),
            ),
            "- Path order fav / outer / same-bar-adv / neither: %d / %d / %d / %d"
            % (
                int(ct.get("favorable_response_first_count") or 0),
                int(ct.get("outer_area_breach_first_count") or 0),
                int(ct.get("both_same_bar_adverse_first_count") or 0),
                int(ct.get("neither_by_horizon_count") or 0),
            ),
            "- Top-1 / top-3 contact MFE contribution: %s%% / %s%%"
            % (
                _fmt(ct.get("top_1_mfe_contribution_pct"), 1),
                _fmt(ct.get("top_3_mfe_contribution_pct"), 1),
            ),
            "- Zero-MAE contact count: %d" % int(ct.get("zero_mae_count") or 0),
            "- Interpretation: %s" % (ct.get("interpretation_status") or "n/a"),
            "",
        ]

    lines = [
        "# NQ 4H WICK-REJECT -> 24H 1M PROTECTED-AREA REACTION STUDY V1",
        "",
        "STATUS: DESCRIPTIVE ONLY",
        "CONFIG HASH: %s" % cfg_hash,
        "DATA SESSION POLICY: %s" % m["data_session_policy"],
        "CAUSALITY: %s" % ("PASS" if m["causality_pass"] else "FAIL"),
        "STANCE: %s" % m["stance"],
        "DECISION: %s" % m["decision"],
        "",
        "## Population",
        "- 4h wick-reject seeds (eligible with post-seed 1m): %d" % m["eligible_seed_count"],
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
            _fmt(100 * m["candidate_rate"], 1) + "%"
            if m["candidate_rate"] == m["candidate_rate"]
            else "n/a",
        ),
        "- Median minutes from seed available to completion: %s"
        % _fmt(m["median_minutes_since_seed_available"], 1),
        "- Median sequence duration minutes: %s" % _fmt(m["median_sequence_duration_minutes"], 1),
        "- Candidate counts by session segment: %s" % (seg_line or "n/a"),
        "",
        "## Primary question (contact reaction)",
        "- Bear mean(MFE)>mean(MAE) and mean RR>1: %s" % m["bear_primary_question_pass"],
        "- Bull mean(MFE)>mean(MAE) and mean RR>1: %s" % m["bull_primary_question_pass"],
        "",
        "## Excursion by direction",
        "",
    ]
    lines.extend(side_exc("Bearish", bstr, bct, bs))
    lines.extend(side_exc("Bullish", ustr, uct, us))
    lines.extend(
        [
            "### Pooled (descriptive only)",
            "- Structure mean MFE / MAE / RR: %s / %s / %s"
            % (
                _fmt(astr.get("mean_mfe_ticks")),
                _fmt(astr.get("mean_mae_ticks")),
                _fmt(astr.get("mean_excursion_rr"), 3),
            ),
            "- Contact mean MFE / MAE / RR: %s / %s / %s"
            % (
                _fmt(act.get("mean_mfe_ticks")),
                _fmt(act.get("mean_mae_ticks")),
                _fmt(act.get("mean_excursion_rr"), 3),
            ),
            "",
            "## Integrity",
            "- Causality: %s" % ("PASS" if m["causality_pass"] else "FAIL"),
            "- Sample thresholds met: %s" % m["sample_thresholds_met"],
            "",
            "## Disposition",
            "- DESCRIPTIVE ONLY.",
            "- No entry/P&L claim.",
            "- Excursion R-to-R is asymmetry only, not tradable reward/risk.",
            "- No session, direction, area-depth, or seed-context selector.",
            "- No plugin or promotion.",
            "- Preserve all ledgers, configuration, and charts unchanged.",
            "",
            "## Final disposition language",
            "",
            (
                "This is a descriptive all-session structural study. It measures whether "
                "causally confirmed 1-minute bearish H1-L1-HH-LL and bullish L1-H1-LL-HH "
                "structures form after active 4-hour wick-reject seeds, and whether price "
                "reacts from a bounded protected-pivot AREA such that average favorable "
                "excursion exceeds average adverse excursion over fixed horizons. A touch "
                "or trade-through is classified, not auto-failed. It does not define an "
                "entry, stop, target, position size, trade, expected return, or plugin."
            ),
            "",
        ]
    )
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    flat = {k: v for k, v in m.items() if not isinstance(v, (dict, list, tuple))}
    for key in (
        "bear_side",
        "bull_side",
        "all_structure",
        "bear_structure",
        "bull_structure",
        "all_contact",
        "bear_contact",
        "bull_contact",
        "candidate_count_by_session_segment",
    ):
        flat[key] = json.dumps(m.get(key), default=str)
    pd.DataFrame([flat]).to_csv(hub / "summary.csv", index=False)
    if agg is not None and len(agg):
        agg.to_csv(hub / "aggregate_excursion_summary.csv", index=False)


def write_causality_audit(hub: Path, ok: bool, fails: List[str], elig, cands, structs, contacts) -> None:
    lines = [
        "# CAUSALITY_AUDIT — %s" % STUDY_ID,
        "",
        "status: %s" % ("PASS" if ok else "FAIL"),
        "generated: %s" % datetime.now().isoformat(),
        "",
        "## Reconciliation",
        "- eligible_seeds: %d" % int((elig["included"] == True).sum()),  # noqa: E712
        "- candidates: %d" % len(cands),
        "- structure_excursion_outcomes: %d" % len(structs),
        "- contact_reaction_outcomes: %d" % len(contacts),
        "",
        "## Assertions",
    ]
    if ok:
        lines.append("- All causality inequalities hold for included candidates.")
        lines.append("- ≤1 candidate or explicit exclusion per seed.")
        lines.append("- One structure + one contact-reaction row per candidate.")
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
                "POLICY A round-the-clock 1m protected-AREA reaction (MFE/MAE).\n"
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

        _progress(hub, "build RTH tape for seeds + Globex 1m for study")
        tape_rth, _h1, h4, early = build_rth_tape(gby)
        bars_1m = build_globex_1m(gby)
        _progress(
            hub,
            "rth_tape=%d 4h=%d globex_1m=%d" % (len(tape_rth), len(h4), len(bars_1m)),
        )

        _progress(hub, "make_seeds_30")
        seeds, census = make_seeds_30(events, tape_rth, h4, early)
        census.to_csv(hub / "phase0_seed_census.csv", index=False)
        _progress(hub, "eligible seeds built=%d" % len(seeds))

        elig = build_seed_eligibility(seeds, ev_by_id, bars_1m)
        elig.to_csv(hub / "seed_24h_eligibility.csv", index=False)
        n_inc = int((elig["included"] == True).sum())  # noqa: E712
        _progress(hub, "included seeds=%d / %d" % (n_inc, len(elig)))

        pivot_rows: List[Dict[str, Any]] = []
        cand_rows: List[Dict[str, Any]] = []
        struct_rows: List[Dict[str, Any]] = []
        contact_rows: List[Dict[str, Any]] = []
        excl_rows: List[Dict[str, Any]] = []

        seeds_by_id = {s.seed_id: s for s in seeds}
        included = elig[elig["included"] == True]  # noqa: E712

        for i, (_, er) in enumerate(included.iterrows()):
            seed = seeds_by_id[er["seed_id"]]
            avail = _localize(seed.available_at)
            exp = _localize(seed.expires_at)
            pivots = build_strict_1m_pivots(bars_1m, er["seed_id"], avail, exp)
            for p in pivots:
                pub = {k: v for k, v in p.items() if not k.startswith("_")}
                pivot_rows.append(pub)

            cand, d_reason, near = select_structure(pivots, er.to_dict(), bars_1m)
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
                struct_out = evaluate_structure_excursion(cand, bars_1m)
                contact_out = evaluate_contact_reaction(cand, struct_out, bars_1m)
                pub_c = {k: v for k, v in cand.items() if not k.startswith("_")}
                cand_rows.append(pub_c)
                struct_rows.append(struct_out)
                contact_rows.append(contact_out)

            if (i + 1) % 10 == 0:
                _progress(hub, "structures %d/%d" % (i + 1, len(included)))

        pivots_df = pd.DataFrame(pivot_rows)
        cands = pd.DataFrame(cand_rows)
        structs = pd.DataFrame(struct_rows)
        contacts = pd.DataFrame(contact_rows)
        exclusions = pd.DataFrame(excl_rows)

        pivots_df.to_csv(hub / "one_minute_pivot_ledger.csv", index=False)
        if len(exclusions):
            stub = exclusions.copy()
            for col in (
                "p1_id",
                "p2_id",
                "p3_id",
                "p4_id",
                "h1_price",
                "l1_price",
                "hh_price",
                "ll_price",
                "structure_complete_at",
                "structure_reference_price",
                "protected_side",
                "protected_pivot_price",
                "break_level",
                "break_distance_ticks",
                "area_width_ticks",
                "inner_area_edge",
                "outer_area_edge",
                "response_distance_ticks",
                "sequence_duration_minutes",
                "minutes_since_seed_available",
                "seed_context_relation",
                "one_minute_direction_vs_seed_direction",
            ):
                if col not in stub.columns:
                    stub[col] = ""
            struct_all = (
                pd.concat([cands, stub], ignore_index=True, sort=False) if len(cands) else stub
            )
        else:
            struct_all = cands
        struct_all.to_csv(hub / "structure_candidates.csv", index=False)
        structs.to_csv(hub / "structure_excursion_outcomes.csv", index=False)
        contacts.to_csv(hub / "contact_reaction_outcomes.csv", index=False)
        exclusions.to_csv(hub / "pack_e_exclusions.csv", index=False)
        _progress(
            hub,
            "pivots=%d candidates=%d exclusions=%d"
            % (len(pivots_df), len(cands), len(exclusions)),
        )

        ok, fails, assertions = run_causality_audit(elig, cands, structs, contacts, exclusions)
        assertions.to_csv(hub / "causality_and_reconciliation.csv", index=False)
        write_causality_audit(hub, ok, fails, elig, cands, structs, contacts)
        _progress(hub, "causality %s" % ("PASS" if ok else "FAIL"))

        agg = build_aggregate_summary(cands, structs, contacts)
        metrics = compute_summary(elig, cands, structs, contacts, agg, ok)
        write_summary_md(hub, metrics, cfg_hash, agg)
        (hub / "STATUS.md").write_text(
            "# STATUS\n\nstance: %s\ncausality: %s\ndecision: %s\n"
            % (metrics["stance"], "PASS" if ok else "FAIL", metrics["decision"]),
            encoding="utf-8",
        )

        if not args.skip_charts:
            _progress(hub, "charts packs A–F")
            from . import nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_charts as charts

            charts.render_all(
                hub=hub,
                study_id=STUDY_ID,
                data_version=DATA_VERSION,
                cfg_hash=cfg_hash,
                data_session_policy=DATA_SESSION_POLICY,
                elig=elig,
                pivots_df=pivots_df,
                cands=cands,
                structs=structs,
                contacts=contacts,
                exclusions=exclusions,
                bars_1m=bars_1m,
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

        bct = metrics["bear_contact"]
        uct = metrics["bull_contact"]
        body = (
            "potions: %s COMPLETE\n\nHub: %s\n"
            "config_hash: %s\nsmoke: %s\npolicy: %s\n"
            "eligible_seeds: %d\ncandidates: %d (bear=%d bull=%d)\n"
            "bear_contact mean MFE/MAE/RR (n=%s): %s / %s / %s\n"
            "bull_contact mean MFE/MAE/RR (n=%s): %s / %s / %s\n"
            "primary_q bear/bull: %s / %s\n"
            "causality: %s\ndecision: %s\nstance: %s\n\n"
            "DESCRIPTIVE ONLY — no trade / plugin / session selector.\n"
            "Excursion RR = asymmetry only (not tradable R).\n"
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
                bct.get("record_count", "n/a"),
                _fmt(bct.get("mean_mfe_ticks")),
                _fmt(bct.get("mean_mae_ticks")),
                _fmt(bct.get("mean_excursion_rr"), 3),
                uct.get("record_count", "n/a"),
                _fmt(uct.get("mean_mfe_ticks")),
                _fmt(uct.get("mean_mae_ticks")),
                _fmt(uct.get("mean_excursion_rr"), 3),
                metrics["bear_primary_question_pass"],
                metrics["bull_primary_question_pass"],
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
                "bear_contact_rr": bct.get("mean_excursion_rr"),
                "bull_contact_rr": uct.get("mean_excursion_rr"),
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
