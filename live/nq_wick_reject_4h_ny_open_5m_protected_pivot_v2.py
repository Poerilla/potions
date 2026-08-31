"""NQ 4h WICK_REJECT → NY-open 5m protected-pivot study (V2).

Descriptive only: no trades, fills, stops, targets, P&L, plugin, or S1/S2 coupling.

Hub: live/state/nq_wick_reject_4h_ny_open_5m_protected_pivot_v2/
No-cutoff diagnostic hub: ..._v2_no_cutoff/ (formation through obs_end only)

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_ny_open_5m_protected_pivot_v2 --smoke --email
  python -m live.nq_wick_reject_4h_ny_open_5m_protected_pivot_v2 --email
  python -m live.nq_wick_reject_4h_ny_open_5m_protected_pivot_v2 --no-cutoff --email
"""

from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import HUB as ATLAS_HUB
from .nq_structure_change_event_study import TICK
from .nq_wick_reject_4h_swing_retest_v1 import make_seeds_30
from .nq_wick_reject_range_seed_retest import (
    Seed,
    _localize,
    build_rth_tape,
    load_wick_events,
)
from .run_ledger import begin_run, complete_run, fail_run
from .structure_program_st_study import rth_slice
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB_BASE = REPO / "live" / "state" / "nq_wick_reject_4h_ny_open_5m_protected_pivot_v2"
STUDY_ID_BASE = "nq_wick_reject_4h_ny_open_5m_protected_pivot_v2"
NY = "America/New_York"
NY_OPEN = time(9, 30)
FORMATION_CUTOFF_DEFAULT = time(10, 30)
OBS_END = time(13, 0)
INSET_START = time(9, 20)
DATA_VERSION = "nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst"
SMOKE_CHART_CAP = 5

# Runtime (set in main): archived V2 uses 10:30; --no-cutoff uses obs_end only.
HUB = HUB_BASE
STUDY_ID = STUDY_ID_BASE
FORMATION_CUTOFF = FORMATION_CUTOFF_DEFAULT
NO_CUTOFF = False


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _config_hash(hub: Path) -> str:
    cutoff_label = "none_obs_end_only" if NO_CUTOFF else "10:30"
    parts = [
        (hub / "MODEL_CONTRACT.yaml").read_text(encoding="utf-8"),
        "pivot_timeframe=5m",
        "pivot_left=1",
        "pivot_right=1",
        "strict_extrema=true",
        "equal_level_policy=reject",
        "tick=0.25",
        "ny_open=09:30",
        "formation_cutoff=%s" % cutoff_label,
        "obs_end=13:00",
        "seed_expiry_4h_bars=30",
        "protection_bar_timeframe=5m",
        "parent=nq_wick_reject_4h_ny_open_1m_protected_pivot_v1",
        "parent_status=archived_negative",
        "parent_config_hash=ea16e8de589a75c2",
        "v2_cutoff_hub=nq_wick_reject_4h_ny_open_5m_protected_pivot_v2",
        "v2_cutoff_hash=d3b30d168b0bb59b",
        "no_cutoff=%s" % ("true" if NO_CUTOFF else "false"),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _ts_at(d: date, t: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(d, t), tz=NY)


def _next_ny_open_on_or_after(ts: pd.Timestamp) -> pd.Timestamp:
    ts = _localize(ts)
    cand = _ts_at(ts.date(), NY_OPEN)
    if ts <= cand:
        return cand
    return _ts_at(ts.date() + timedelta(days=1), NY_OPEN)


def _advance_ny_open(ts: pd.Timestamp) -> pd.Timestamp:
    ts = _localize(ts)
    return _ts_at(ts.date() + timedelta(days=1), NY_OPEN)


def _day_rth(gby: Dict[date, pd.DataFrame], d: date) -> pd.DataFrame:
    raw = gby.get(d)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    rth = rth_slice(raw)
    if rth is None or rth.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    out = rth.copy()
    out.index = pd.DatetimeIndex([_localize(x) for x in out.index])
    return out.sort_index()


def _window_1m(day: pd.DataFrame, t0: time, t1: time) -> pd.DataFrame:
    if day is None or day.empty:
        return day.iloc[0:0]
    d = _localize(day.index[0]).date()
    a = _ts_at(d, t0)
    b = _ts_at(d, t1)
    return day[(day.index >= a) & (day.index < b)]


def _complete_1m_open_to_obs(day: pd.DataFrame) -> bool:
    """Require near-complete 1m coverage 09:30–13:00 ET (source tape for 5m)."""
    if day is None or day.empty:
        return False
    w = _window_1m(day, NY_OPEN, OBS_END)
    if w.empty:
        return False
    d = _localize(day.index[0]).date()
    need_open = _ts_at(d, NY_OPEN)
    need_last = _ts_at(d, time(12, 55))
    if _localize(w.index[0]) > need_open:
        return False
    if _localize(w.index[-1]) < need_last:
        return False
    # Full session 09:30–13:00 = 210 minutes; allow tiny gaps.
    return len(w) >= 200


def _to_5m(day_1m: pd.DataFrame) -> pd.DataFrame:
    """Left-labeled / left-closed 5m OHLC from RTH 1m (session-aligned)."""
    if day_1m is None or day_1m.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    src = day_1m.copy()
    src.index = pd.DatetimeIndex([_localize(x) for x in src.index])
    src = src.sort_index()
    out = (
        src.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna(subset=["open", "high", "low", "close"])
    )
    return out


def _seed_direction_from_event(ev: pd.Series) -> str:
    od = str(ev.get("outcome_direction") or "").strip().lower()
    if od in ("bullish", "bearish"):
        return od
    bd = str(ev.get("break_direction") or "").strip().lower()
    # WICK_REJECT outcome opposite break
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
# Eligibility
# ---------------------------------------------------------------------------


def build_eligibility(
    seeds: List[Seed],
    events_by_id: Dict[str, pd.Series],
    gby: Dict[date, pd.DataFrame],
    early: Dict[date, bool],
) -> pd.DataFrame:
    rows = []
    for seed in seeds:
        ev = events_by_id.get(seed.event_id, pd.Series(dtype=object))
        seed_dir = _seed_direction_from_event(ev) if len(ev) else ""
        pen = float(ev.get("penetration_ATR") or np.nan) if len(ev) else float("nan")
        width_atr = (seed.width / seed.atr20_4h) if seed.atr20_4h and seed.atr20_4h > 0 else float("nan")

        t = _next_ny_open_on_or_after(seed.available_at)
        last_reason = "expired_or_inactive_seed"
        assigned = None

        while t < _localize(seed.expires_at):
            d = t.date()
            active = _localize(seed.available_at) <= t < _localize(seed.expires_at)
            if not active:
                last_reason = "expired_or_inactive_seed"
                break
            if t < _localize(seed.available_at):
                last_reason = "before_seed_available"
                t = _advance_ny_open(t)
                continue

            day = _day_rth(gby, d)
            is_early = bool(early.get(d, True))
            if day.empty:
                last_reason = "holiday"
                t = _advance_ny_open(t)
                continue
            if is_early:
                last_reason = "early_close"
                t = _advance_ny_open(t)
                continue
            if not _complete_1m_open_to_obs(day):
                last_reason = "missing_1m_data"
                t = _advance_ny_open(t)
                continue

            age_h = (t - _localize(seed.available_at)).total_seconds() / 3600.0
            assigned = {
                "seed_id": seed.seed_id,
                "seed_ts": _localize(seed.seed_close_ts).isoformat(),
                "seed_available_at": _localize(seed.available_at).isoformat(),
                "seed_high": seed.high,
                "seed_low": seed.low,
                "seed_width": seed.width,
                "seed_direction": seed_dir,
                "seed_expiry": _localize(seed.expires_at).isoformat(),
                "range_width_atr": width_atr,
                "penetration_atr": pen,
                "ny_date": d.isoformat(),
                "ny_open_ts": t.isoformat(),
                "seed_age_hours": round(age_h, 4),
                "seed_active_at_open": True,
                "eligible_after_seed": True,
                "selected_first_eligible_open": True,
                "included": True,
                "exclusion_reason": "",
                "event_id": seed.event_id,
                "slice": seed.slice,
            }
            break

        if assigned is None:
            # Record last attempted open context when possible
            t_fail = _next_ny_open_on_or_after(seed.available_at)
            d_fail = t_fail.date()
            age_h = (t_fail - _localize(seed.available_at)).total_seconds() / 3600.0
            active = _localize(seed.available_at) <= t_fail < _localize(seed.expires_at)
            rows.append(
                {
                    "seed_id": seed.seed_id,
                    "seed_ts": _localize(seed.seed_close_ts).isoformat(),
                    "seed_available_at": _localize(seed.available_at).isoformat(),
                    "seed_high": seed.high,
                    "seed_low": seed.low,
                    "seed_width": seed.width,
                    "seed_direction": seed_dir,
                    "seed_expiry": _localize(seed.expires_at).isoformat(),
                    "range_width_atr": width_atr,
                    "penetration_atr": pen,
                    "ny_date": d_fail.isoformat(),
                    "ny_open_ts": t_fail.isoformat(),
                    "seed_age_hours": round(age_h, 4),
                    "seed_active_at_open": bool(active),
                    "eligible_after_seed": _localize(seed.available_at) <= t_fail,
                    "selected_first_eligible_open": False,
                    "included": False,
                    "exclusion_reason": last_reason,
                    "event_id": seed.event_id,
                    "slice": seed.slice,
                }
            )
        else:
            rows.append(assigned)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Strict 5m pivots
# ---------------------------------------------------------------------------


def build_strict_5m_pivots(
    day_5m: pd.DataFrame,
    seed_id: str,
    ny_date: str,
    open_ts: pd.Timestamp,
) -> List[Dict[str, Any]]:
    """1-left / 1-right strict 5m pivots with close-based causality clocks.

    pivot_ts = close of the pivot 5m bar
    pivot_available_at = close of the following (right) 5m bar
    """
    if day_5m is None or len(day_5m) < 3:
        return []
    hi = day_5m["high"].to_numpy(dtype=float)
    lo = day_5m["low"].to_numpy(dtype=float)
    idx = day_5m.index
    pivots: List[Dict[str, Any]] = []
    open_ts = _localize(open_ts)
    cutoff = _ts_at(open_ts.date(), FORMATION_CUTOFF)
    bar_td = pd.Timedelta(minutes=5)
    pid = 0
    for i in range(1, len(day_5m) - 1):
        is_h = hi[i] > hi[i - 1] and hi[i] > hi[i + 1]
        is_l = lo[i] < lo[i - 1] and lo[i] < lo[i + 1]
        if is_h and is_l:
            continue  # equal_high_low_policy: reject
        if not is_h and not is_l:
            continue
        bar_open = _localize(idx[i])
        # Pivot bar must begin no earlier than NY open.
        if bar_open < open_ts:
            continue
        pivot_ts = bar_open + bar_td  # close of pivot bar
        avail = _localize(idx[i + 1]) + bar_td  # close of right confirmation bar
        ptype = "H" if is_h else "L"
        price = float(hi[i] if is_h else lo[i])
        pid += 1
        bar_i = int(round((bar_open - open_ts).total_seconds() / 300.0))
        inside = (bar_open >= open_ts) and (avail <= cutoff)
        pivots.append(
            {
                "seed_id": seed_id,
                "ny_date": ny_date,
                "pivot_id": "%s_%s_P%04d" % (seed_id, ny_date, pid),
                "pivot_type": ptype,
                "pivot_price": price,
                "pivot_ts": pivot_ts.isoformat(),
                "pivot_available_at": avail.isoformat(),
                "pivot_bar_open_ts": bar_open.isoformat(),
                "bar_index_from_open": bar_i,
                "inside_open_window": bool(inside),
                "left_bars": 1,
                "right_bars": 1,
                "strict_extrema": True,
                "timeframe": "5m",
                "_pivot_ts": pivot_ts,
                "_bar_open": bar_open,
                "_avail": avail,
                "_price": price,
                "_type": ptype,
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
    one_m = "bearish" if pattern == "BEAR" else "bullish"
    sd = (seed_direction or "").lower()
    if sd not in ("bullish", "bearish"):
        return "NOT_APPLICABLE_OR_UNCLASSIFIED"
    if one_m == sd:
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
    open_ts: pd.Timestamp,
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """Return (candidate_row_or_None, pack_d_reason, near_miss_note)."""
    cutoff = _ts_at(open_ts.date(), FORMATION_CUTOFF)
    obs = _ts_at(open_ts.date(), OBS_END)
    # Pivot bars begin >= NY open; P4 available by formation cutoff
    # (10:30 default, or obs_end when --no-cutoff).
    window = [
        p
        for p in pivots
        if p["_bar_open"] >= open_ts and p["_avail"] <= cutoff and p["_avail"] < obs
    ]
    if len(window) < 4:
        return None, "NO_COMPLETED_FOUR_PIVOT_SEQUENCE", ""

    # Consecutive 4-tuples only
    for i in range(len(window) - 3):
        a, b, c, d = window[i], window[i + 1], window[i + 2], window[i + 3]
        # causality ordering
        if not (a["_pivot_ts"] < b["_pivot_ts"] < c["_pivot_ts"] < d["_pivot_ts"]):
            continue
        if not (a["_avail"] <= b["_avail"] <= c["_avail"] <= d["_avail"]):
            continue
        # consecutive pivots must be on distinct bars (min separation 1)
        if not (
            a["_bar_open"] < b["_bar_open"] < c["_bar_open"] < d["_bar_open"]
        ):
            continue
        pattern = None
        if _is_bear_tuple(a, b, c, d):
            pattern = "BEAR"
        elif _is_bull_tuple(a, b, c, d):
            pattern = "BULL"
        else:
            continue
        if d["_avail"] > cutoff:
            continue
        if d["_avail"] >= obs:
            continue

        prices = [a["_price"], b["_price"], c["_price"], d["_price"]]
        if pattern == "BEAR":
            h1, l1, hh, ll = a["_price"], b["_price"], c["_price"], d["_price"]
            protected_side = "HIGH"
            protected_price = hh
            break_level = l1
        else:
            l1, h1, ll, hh = a["_price"], b["_price"], c["_price"], d["_price"]
            protected_side = "LOW"
            protected_price = ll
            break_level = h1

        complete = d["_avail"]
        break_dist = abs(protected_price - break_level) / TICK
        seq_min = (complete - a["_pivot_ts"]).total_seconds() / 60.0
        from_open = (complete - open_ts).total_seconds() / 60.0
        cand_id = "CAND_%s_%s" % (elig["seed_id"], elig["ny_date"])
        row = {
            "candidate_id": cand_id,
            "seed_id": elig["seed_id"],
            "ny_date": elig["ny_date"],
            "pattern": pattern,
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
            "break_level": break_level,
            "break_distance_ticks": round(break_dist, 4),
            "sequence_duration_minutes": round(seq_min, 4),
            "minutes_from_open_to_completion": round(from_open, 4),
            "seed_age_hours": elig["seed_age_hours"],
            "seed_context_relation": _seed_context_relation(
                prices, float(elig["seed_high"]), float(elig["seed_low"])
            ),
            "5m_direction_vs_seed_direction": _dir_vs_seed(pattern, str(elig["seed_direction"])),
            "eligible_for_protection_test": True,
            "exclusion_reason": "",
            "_complete": complete,
            "_p1": a,
            "_p2": b,
            "_p3": c,
            "_p4": d,
        }
        return row, "", ""

    # Near-miss: non-consecutive same-type pattern
    near = ""
    reason = "NO_COMPLETED_FOUR_PIVOT_SEQUENCE"
    for i in range(len(window)):
        for j in range(i + 1, len(window)):
            for k in range(j + 1, len(window)):
                for m in range(k + 1, len(window)):
                    a, b, c, d = window[i], window[j], window[k], window[m]
                    if j != i + 1 or k != j + 1 or m != k + 1:
                        if _is_bear_tuple(a, b, c, d) or _is_bull_tuple(a, b, c, d):
                            if d["_avail"] <= cutoff and d["_avail"] < obs:
                                reason = "INTERVENING_PIVOT_AMBIGUITY"
                                near = "NEAR MISS — NOT COUNTED (intervening pivots)"
                                return None, reason, near
                    # directional fail examples on consecutive-ish
                    if (
                        a["_type"] == "H"
                        and b["_type"] == "L"
                        and c["_type"] == "H"
                        and d["_type"] == "L"
                        and j == i + 1
                        and k == j + 1
                        and m == k + 1
                    ):
                        if not (c["_price"] > a["_price"] and d["_price"] < b["_price"]):
                            reason = "SEQUENCE_NOT_DIRECTIONALLY_VALID"
                            bits = []
                            if not (c["_price"] > a["_price"]):
                                bits.append("HH was not greater than H1")
                            if not (d["_price"] < b["_price"]):
                                bits.append("LL was not lower than L1")
                            near = "NEAR MISS — NOT COUNTED; " + "; ".join(bits)
                    if (
                        a["_type"] == "L"
                        and b["_type"] == "H"
                        and c["_type"] == "L"
                        and d["_type"] == "H"
                        and j == i + 1
                        and k == j + 1
                        and m == k + 1
                    ):
                        if not (c["_price"] < a["_price"] and d["_price"] > b["_price"]):
                            reason = "SEQUENCE_NOT_DIRECTIONALLY_VALID"
                            bits = []
                            if not (c["_price"] < a["_price"]):
                                bits.append("LL was not lower than L1")
                            if not (d["_price"] > b["_price"]):
                                bits.append("HH was not greater than H1")
                            near = "NEAR MISS — NOT COUNTED; " + "; ".join(bits)

    # Check cutoff failures: type-valid but P4 after formation cutoff (N/A when no-cutoff)
    if not NO_CUTOFF:
        for i in range(len(pivots) - 3):
            a, b, c, d = pivots[i], pivots[i + 1], pivots[i + 2], pivots[i + 3]
            if a["_bar_open"] < open_ts:
                continue
            if _is_bear_tuple(a, b, c, d) or _is_bull_tuple(a, b, c, d):
                if d["_avail"] > cutoff:
                    reason = "FINAL_PIVOT_AFTER_CUTOFF"
                    near = "NEAR MISS — NOT COUNTED; P4 confirmation occurred after 10:30"
                    break

    return None, reason, near


# ---------------------------------------------------------------------------
# Protection outcomes
# ---------------------------------------------------------------------------


def evaluate_protection(
    cand: Dict[str, Any],
    day_5m: pd.DataFrame,
) -> Dict[str, Any]:
    """Protection vs completed 5m highs/lows after structure_complete_at."""
    complete = cand["_complete"]
    d = complete.date()
    obs_end = _ts_at(d, OBS_END)
    # First observational 5m bar is the left-labeled bar that opens at/after complete.
    bars = day_5m[(day_5m.index >= complete) & (day_5m.index < obs_end)]
    expected_bars = max(0, int((obs_end - complete).total_seconds() // 300))
    data_complete = True
    if expected_bars >= 2 and len(bars) < max(1, int(0.85 * expected_bars)):
        data_complete = False

    out = {
        "candidate_id": cand["candidate_id"],
        "evaluation_start": complete.isoformat(),
        "observation_end": obs_end.isoformat(),
        "protection_held": False,
        "outcome_label": "INSUFFICIENT_DATA",
        "equal_touch_occurred": False,
        "first_equal_touch_ts": "",
        "failure_ts": "",
        "failure_price": np.nan,
        "failure_distance_ticks": np.nan,
        "minutes_to_failure": np.nan,
        "max_favorable_excursion_ticks": np.nan,
        "max_adverse_excursion_ticks": np.nan,
        "session_outcome": "",
        "data_complete": data_complete,
        "held_to_1030": False,
        "held_to_1100": False,
        "held_to_1300": False,
        "observation_timeframe": "5m",
    }
    if not data_complete or bars.empty:
        out["outcome_label"] = "INSUFFICIENT_DATA"
        out["session_outcome"] = "INSUFFICIENT_DATA"
        return out

    prot = float(cand["protected_price"])
    pattern = cand["pattern"]
    fail_ts = None
    fail_px = None
    eq_ts = None
    mfe = 0.0
    mae = 0.0
    bar_td = pd.Timedelta(minutes=5)

    for ts, row in bars.iterrows():
        ts = _localize(ts)
        bar_close = ts + bar_td
        hi = float(row["high"])
        lo = float(row["low"])
        if pattern == "BEAR":
            mfe = max(mfe, (prot - lo) / TICK)
            mae = max(mae, (hi - prot) / TICK)
            if abs(hi - prot) < 1e-9 or hi == prot:
                if eq_ts is None:
                    eq_ts = bar_close
            if hi > prot + TICK - 1e-12:
                fail_ts = bar_close
                fail_px = hi
                break
        else:
            mfe = max(mfe, (hi - prot) / TICK)
            mae = max(mae, (prot - lo) / TICK)
            if abs(lo - prot) < 1e-9 or lo == prot:
                if eq_ts is None:
                    eq_ts = bar_close
            if lo < prot - TICK + 1e-12:
                fail_ts = bar_close
                fail_px = lo
                break

    out["max_favorable_excursion_ticks"] = round(mfe, 4)
    out["max_adverse_excursion_ticks"] = round(mae, 4)
    out["equal_touch_occurred"] = eq_ts is not None
    out["first_equal_touch_ts"] = eq_ts.isoformat() if eq_ts is not None else ""

    def _broken_before(t_end: time) -> bool:
        end = _ts_at(d, t_end)
        sub = bars[bars.index < end]
        if sub.empty:
            return False
        if pattern == "BEAR":
            return float(sub["high"].max()) > prot + TICK - 1e-12
        return float(sub["low"].min()) < prot - TICK + 1e-12

    out["held_to_1030"] = not _broken_before(FORMATION_CUTOFF_DEFAULT)
    out["held_to_1100"] = not _broken_before(time(11, 0))
    out["held_to_1300"] = fail_ts is None

    if fail_ts is not None:
        out["protection_held"] = False
        out["outcome_label"] = "FAILED_ONE_TICK_OR_MORE"
        out["failure_ts"] = fail_ts.isoformat()
        out["failure_price"] = fail_px
        out["failure_distance_ticks"] = round(abs(fail_px - prot) / TICK, 4)
        out["minutes_to_failure"] = round((fail_ts - complete).total_seconds() / 60.0, 4)
        out["session_outcome"] = "FAILED"
    else:
        out["protection_held"] = True
        out["outcome_label"] = "HELD_EQUAL_TOUCH" if eq_ts is not None else "HELD_NO_TOUCH"
        out["session_outcome"] = "HELD"

    return out


# ---------------------------------------------------------------------------
# Causality + summary
# ---------------------------------------------------------------------------


def run_causality_audit(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
) -> Tuple[bool, List[str], pd.DataFrame]:
    fails: List[str] = []
    assertions: List[Dict[str, Any]] = []
    included = elig[elig["included"] == True]  # noqa: E712
    # one NY open per seed among included
    if included["seed_id"].duplicated().any():
        fails.append("duplicate included NY open for a seed")

    for _, c in cands.iterrows():
        seed_rows = included[included["seed_id"] == c["seed_id"]]
        row_ok = True
        notes = []
        if seed_rows.empty:
            fails.append("%s missing eligibility row" % c["candidate_id"])
            row_ok = False
            notes.append("missing_eligibility")
            assertions.append(
                {
                    "candidate_id": c["candidate_id"],
                    "pass": False,
                    "notes": ";".join(notes),
                }
            )
            continue
        e = seed_rows.iloc[0]
        ny_open = _localize(pd.Timestamp(e["ny_open_ts"]))
        seed_avail = _localize(pd.Timestamp(e["seed_available_at"]))
        if "p1_ts" not in c.index:
            fails.append("%s missing p1_ts" % c["candidate_id"])
            row_ok = False
            notes.append("missing_p1_ts")
            assertions.append(
                {
                    "candidate_id": c["candidate_id"],
                    "pass": False,
                    "notes": ";".join(notes),
                }
            )
            continue
        p1ts = _localize(pd.Timestamp(c["p1_ts"]))
        p2ts = _localize(pd.Timestamp(c["p2_ts"]))
        p3ts = _localize(pd.Timestamp(c["p3_ts"]))
        p4ts = _localize(pd.Timestamp(c["p4_ts"]))
        p1a = _localize(pd.Timestamp(c["p1_available_at"]))
        p2a = _localize(pd.Timestamp(c["p2_available_at"]))
        p3a = _localize(pd.Timestamp(c["p3_available_at"]))
        p4a = _localize(pd.Timestamp(c["p4_available_at"]))
        p1_open = _localize(pd.Timestamp(c["p1_bar_open_ts"]))
        complete = _localize(pd.Timestamp(c["structure_complete_at"]))
        cutoff = _ts_at(ny_open.date(), FORMATION_CUTOFF)
        obs = _ts_at(ny_open.date(), OBS_END)

        if not (seed_avail <= ny_open):
            fails.append("%s seed_available_at > ny_open" % c["candidate_id"])
            row_ok = False
            notes.append("seed_after_open")
        if not (p1_open >= ny_open):
            fails.append("%s p1 bar open before ny_open" % c["candidate_id"])
            row_ok = False
            notes.append("p1_before_open")
        if not (p1ts < p2ts < p3ts < p4ts):
            fails.append("%s pivot_ts order" % c["candidate_id"])
            row_ok = False
            notes.append("pivot_ts_order")
        if not (p1a <= p2a <= p3a <= p4a):
            fails.append("%s pivot_available order" % c["candidate_id"])
            row_ok = False
            notes.append("avail_order")
        # 5m: available_at must be pivot_ts + 5m (close of following bar)
        for label, pts, pav in (
            ("p1", p1ts, p1a),
            ("p2", p2ts, p2a),
            ("p3", p3ts, p3a),
            ("p4", p4ts, p4a),
        ):
            if pav != pts + pd.Timedelta(minutes=5):
                fails.append("%s %s available_at != pivot_ts+5m" % (c["candidate_id"], label))
                row_ok = False
                notes.append("%s_avail_lag" % label)
        if complete != p4a:
            fails.append("%s structure_complete_at != p4.available" % c["candidate_id"])
            row_ok = False
            notes.append("complete_ne_p4a")
        if (not NO_CUTOFF) and complete > cutoff:
            fails.append("%s complete after cutoff" % c["candidate_id"])
            row_ok = False
            notes.append("after_cutoff")
        if not (complete < obs):
            fails.append("%s complete not before obs end" % c["candidate_id"])
            row_ok = False
            notes.append("complete_ge_obs")
        assertions.append(
            {
                "candidate_id": c["candidate_id"],
                "pass": row_ok,
                "ny_open_ts": ny_open.isoformat(),
                "p1_bar_open_ts": p1_open.isoformat(),
                "p4_available_at": p4a.isoformat(),
                "structure_complete_at": complete.isoformat(),
                "notes": ";".join(notes),
            }
        )

    # outcomes
    for _, o in outs.iterrows():
        if o.get("failure_ts"):
            ft = _localize(pd.Timestamp(o["failure_ts"]))
            st = _localize(pd.Timestamp(o["evaluation_start"]))
            if ft < st:
                fails.append("%s failure before complete" % o["candidate_id"])

    # reconciliation
    n_cand = len(cands)
    n_out = len(outs)
    if n_cand != n_out:
        fails.append("candidate count %d != outcome count %d" % (n_cand, n_out))
    # every eligible open ≤1 candidate
    if len(cands) and cands.duplicated(subset=["seed_id", "ny_date"]).any():
        fails.append("multiple candidates for one seed-open")

    return len(fails) == 0, fails, pd.DataFrame(assertions)


def write_causality_audit(hub: Path, ok: bool, fails: List[str], elig, cands, outs) -> None:
    lines = [
        "# CAUSALITY_AUDIT — %s" % STUDY_ID,
        "",
        "status: %s" % ("PASS" if ok else "FAIL"),
        "generated: %s" % datetime.now().isoformat(),
        "",
        "## Reconciliation",
        "- eligible_seed_opens: %d" % int((elig["included"] == True).sum()),  # noqa: E712
        "- candidates: %d" % len(cands),
        "- outcomes: %d" % len(outs),
        "- insufficient_data outcomes: %d"
        % (int((outs["outcome_label"] == "INSUFFICIENT_DATA").sum()) if len(outs) else 0),
        "",
        "## Assertions",
    ]
    if ok:
        lines.append("- All §12 inequalities hold for included candidates.")
        lines.append("- ≤1 NY open per seed; ≤1 candidate per eligible open.")
    else:
        lines.append("FAILED assertions:")
        for f in fails:
            lines.append("- %s" % f)
    (hub / "CAUSALITY_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_summary(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
    causality_ok: bool,
) -> Dict[str, Any]:
    eligible_n = int((elig["included"] == True).sum())  # noqa: E712
    merged = cands.merge(outs, on="candidate_id", how="left") if len(cands) else pd.DataFrame()
    n_cand = len(cands)
    bear = merged[merged["pattern"] == "BEAR"] if n_cand else merged
    bull = merged[merged["pattern"] == "BULL"] if n_cand else merged

    def hold_rate(sub: pd.DataFrame) -> float:
        if sub is None or sub.empty:
            return float("nan")
        # exclude insufficient from denominator? Spec: eligible candidates — use data_complete
        ok = sub[sub["data_complete"] == True]  # noqa: E712
        if ok.empty:
            return float("nan")
        return float(ok["protection_held"].mean())

    def hold_to(sub: pd.DataFrame, col: str) -> float:
        ok = sub[sub["data_complete"] == True] if sub is not None and len(sub) else sub  # noqa
        if ok is None or ok.empty:
            return float("nan")
        return float(ok[col].mean())

    bear_hr = hold_rate(bear)
    bull_hr = hold_rate(bull)
    all_ok = merged[merged["data_complete"] == True] if n_cand else merged  # noqa: E712

    med_fail = float("nan")
    if n_cand and len(all_ok):
        fails = all_ok[all_ok["outcome_label"] == "FAILED_ONE_TICK_OR_MORE"]["minutes_to_failure"]
        if len(fails):
            med_fail = float(fails.median())

    med_complete = float("nan")
    med_complete_clock = ""
    if n_cand:
        completes = pd.to_datetime(cands["structure_complete_at"], utc=True).dt.tz_convert(NY)
        med_complete_clock = completes.quantile(0.5).strftime("%H:%M:%S") if len(completes) else ""

    min_elig = eligible_n >= 80
    min_cand = n_cand >= 40
    min_side = (len(bear) >= 15) and (len(bull) >= 15)
    sample_ok = min_elig and min_cand and min_side

    mfe_med = float(all_ok["max_favorable_excursion_ticks"].median()) if len(all_ok) else float("nan")
    mae_med = float(all_ok["max_adverse_excursion_ticks"].median()) if len(all_ok) else float("nan")
    excursion_ok = (
        (mfe_med == mfe_med)
        and (mae_med == mae_med)
        and (mfe_med > mae_med * 1.1)
    )

    rates_ok = (
        (bear_hr == bear_hr)
        and (bull_hr == bull_hr)
        and bear_hr >= 0.55
        and bull_hr >= 0.55
    )
    one_side_ok = False
    if bear_hr == bear_hr and bull_hr == bull_hr:
        one_side_ok = (bear_hr >= 0.55) != (bull_hr >= 0.55) and (
            (bear_hr >= 0.55 and len(bear) >= 15) or (bull_hr >= 0.55 and len(bull) >= 15)
        )

    # Hard stop: <40 candidates → insufficient sample; archive without further tuning.
    if n_cand < 40:
        stance = (
            "DESCRIPTIVE ONLY / INSUFFICIENT SAMPLE — archive without further tuning "
            "(hard stop: total_candidates < 40)"
        )
        decision = "INSUFFICIENT_SAMPLE_ARCHIVE"
    elif not causality_ok:
        stance = "DESCRIPTIVE ONLY / CAUSALITY FAIL — archive"
        decision = "CAUSALITY_FAIL"
    elif rates_ok and sample_ok and excursion_ok:
        stance = "WORTH FURTHER RESEARCH (screening only — NOT a trade authorization)"
        decision = "BOTH_SIDES_PASS_SCREEN"
    elif one_side_ok and min_cand:
        stance = (
            "ONE-SIDED DESCRIPTIVE OBSERVATION ONLY — no entry study, no rule selection, no hybrid"
        )
        decision = "ONE_SIDED_ONLY"
    elif sample_ok and not rates_ok:
        stance = (
            "DESCRIPTIVE ONLY / NEGATIVE RESULT — archive the whole NY-open protected-pivot family"
        )
        decision = "NEGATIVE_ARCHIVE_FAMILY"
    else:
        stance = "DESCRIPTIVE ONLY / NOT WORTH FURTHER RESEARCH"
        decision = "NEGATIVE_OR_UNDER_SAMPLED"

    return {
        "eligible_seed_count": eligible_n,
        "candidate_count": n_cand,
        "candidate_rate": (n_cand / eligible_n) if eligible_n else float("nan"),
        "bear_count": int(len(bear)),
        "bull_count": int(len(bull)),
        "median_completion_clock": med_complete_clock,
        "bear_protection_hold_rate": bear_hr,
        "bull_protection_hold_rate": bull_hr,
        "hold_rate_to_10_30": hold_to(all_ok, "held_to_1030") if n_cand else float("nan"),
        "hold_rate_to_11_00": hold_to(all_ok, "held_to_1100") if n_cand else float("nan"),
        "hold_rate_to_13_00": hold_to(all_ok, "held_to_1300") if n_cand else float("nan"),
        "median_minutes_to_failure": med_fail,
        "median_mfe_ticks": mfe_med,
        "median_mae_ticks": mae_med,
        "causality_pass": causality_ok,
        "sample_thresholds_met": sample_ok,
        "decision": decision,
        "stance": stance,
        "parent_study": "nq_wick_reject_4h_ny_open_1m_protected_pivot_v1",
        "parent_status": "archived_negative",
        "non_promotion": True,
    }


def write_summary_md(hub: Path, metrics: Dict[str, Any], cfg_hash: str) -> None:
    m = metrics
    lines = [
        "# SUMMARY — %s" % STUDY_ID,
        "",
        "**Status:** RESEARCH / DESCRIPTIVE ONLY",
        "**config_hash:** `%s`" % cfg_hash,
        "**Stance:** %s" % m["stance"],
        "**Decision:** %s" % m.get("decision", ""),
        "**Parent:** %s (%s)" % (m.get("parent_study", ""), m.get("parent_status", "")),
        "",
        "## Population",
        "- eligible_seed_count: %d" % m["eligible_seed_count"],
        "- candidate_count: %d" % m["candidate_count"],
        "- candidate_rate: %.3f" % (m["candidate_rate"] if m["candidate_rate"] == m["candidate_rate"] else -1),
        "- bear_count: %d" % m["bear_count"],
        "- bull_count: %d" % m["bull_count"],
        "",
        "## Protection (through 13:00 ET, 5m observation)",
        "- bear_protection_hold_rate: %s"
        % ("%.1f%%" % (100 * m["bear_protection_hold_rate"]) if m["bear_protection_hold_rate"] == m["bear_protection_hold_rate"] else "n/a"),
        "- bull_protection_hold_rate: %s"
        % ("%.1f%%" % (100 * m["bull_protection_hold_rate"]) if m["bull_protection_hold_rate"] == m["bull_protection_hold_rate"] else "n/a"),
        "- hold_rate_to_10_30: %s"
        % ("%.1f%%" % (100 * m["hold_rate_to_10_30"]) if m["hold_rate_to_10_30"] == m["hold_rate_to_10_30"] else "n/a"),
        "- hold_rate_to_11_00: %s"
        % ("%.1f%%" % (100 * m["hold_rate_to_11_00"]) if m["hold_rate_to_11_00"] == m["hold_rate_to_11_00"] else "n/a"),
        "- hold_rate_to_13_00: %s"
        % ("%.1f%%" % (100 * m["hold_rate_to_13_00"]) if m["hold_rate_to_13_00"] == m["hold_rate_to_13_00"] else "n/a"),
        "- median_minutes_to_failure: %s"
        % ("%.1f" % m["median_minutes_to_failure"] if m["median_minutes_to_failure"] == m["median_minutes_to_failure"] else "n/a"),
        "- median_mfe_ticks: %s"
        % ("%.2f" % m["median_mfe_ticks"] if m["median_mfe_ticks"] == m["median_mfe_ticks"] else "n/a"),
        "- median_mae_ticks: %s"
        % ("%.2f" % m["median_mae_ticks"] if m["median_mae_ticks"] == m["median_mae_ticks"] else "n/a"),
        "",
        "## Causality",
        "- pass: %s" % m["causality_pass"],
        "",
        "## Screen (predeclared)",
        "- both-side hold ≥55%% with n≥15 each and total≥40: %s"
        % (
            "YES"
            if (
                m["candidate_count"] >= 40
                and m["bear_count"] >= 15
                and m["bull_count"] >= 15
                and m["bear_protection_hold_rate"] == m["bear_protection_hold_rate"]
                and m["bull_protection_hold_rate"] == m["bull_protection_hold_rate"]
                and m["bear_protection_hold_rate"] >= 0.55
                and m["bull_protection_hold_rate"] >= 0.55
            )
            else "NO"
        ),
        "",
        "## Non-promotion",
        "- This study does **not** authorize trades, stops, targets, sizing, plugins, or S1/S2 combination.",
        "- V1 remains archived negative; V2 is an independent descriptive branch (no timeframe chooser).",
        "- Positive hold rates are research-screening signals only.",
        "",
    ]
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame([m]).to_csv(hub / "summary.csv", index=False)


# ---------------------------------------------------------------------------
# Charts (import companion)
# ---------------------------------------------------------------------------


def generate_charts(
    hub: Path,
    elig: pd.DataFrame,
    pivots_df: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
    pack_d_meta: List[Dict[str, Any]],
    gby: Dict[date, pd.DataFrame],
    h4: pd.DataFrame,
    cfg_hash: str,
    smoke: bool,
) -> None:
    from . import nq_wick_reject_4h_ny_open_5m_protected_pivot_v2_charts as charts

    charts.render_all(
        hub=hub,
        study_id=STUDY_ID,
        data_version=DATA_VERSION,
        cfg_hash=cfg_hash,
        elig=elig,
        pivots_df=pivots_df,
        cands=cands,
        outs=outs,
        pack_d_meta=pack_d_meta,
        gby=gby,
        h4=h4,
        smoke=smoke,
        smoke_cap=SMOKE_CHART_CAP,
        tick=TICK,
        formation_cutoff=FORMATION_CUTOFF,
        no_cutoff=NO_CUTOFF,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    global HUB, STUDY_ID, FORMATION_CUTOFF, NO_CUTOFF

    ap = argparse.ArgumentParser(description=STUDY_ID_BASE)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--skip-charts", action="store_true")
    ap.add_argument(
        "--no-cutoff",
        action="store_true",
        help="Diagnostic: drop 10:30 formation cutoff; P4 may complete any time before 13:00. "
        "Writes a separate hub (..._v2_no_cutoff); does not overwrite archived V2.",
    )
    args = ap.parse_args(argv)

    NO_CUTOFF = bool(args.no_cutoff)
    if NO_CUTOFF:
        STUDY_ID = STUDY_ID_BASE + "_no_cutoff"
        HUB = HUB_BASE.parent / STUDY_ID
        FORMATION_CUTOFF = OBS_END
    else:
        STUDY_ID = STUDY_ID_BASE
        HUB = HUB_BASE
        FORMATION_CUTOFF = FORMATION_CUTOFF_DEFAULT

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    for sub in ("charts/pack_a", "charts/pack_b", "charts/pack_c", "charts/pack_d"):
        (hub / sub).mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    cfg_hash = _config_hash(hub)
    (hub / "config_hash.txt").write_text(cfg_hash + "\n", encoding="utf-8")
    # stamp contract
    raw = (hub / "MODEL_CONTRACT.yaml").read_text(encoding="utf-8")
    if "config_hash:" not in raw:
        raw = raw.rstrip() + "\n\nconfig_hash: %s\ncreated: %s\n" % (
            cfg_hash,
            datetime.now().strftime("%Y-%m-%d"),
        )
        (hub / "MODEL_CONTRACT.yaml").write_text(raw, encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug=STUDY_ID + ("_smoke" if args.smoke else ""),
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={
            "descriptive_only": True,
            "config_hash": cfg_hash,
            "smoke": args.smoke,
            "no_cutoff": NO_CUTOFF,
            "formation_cutoff": "none_obs_end_only" if NO_CUTOFF else "10:30",
        },
    )

    try:
        if args.email:
            start = (
                "potions: %s STARTED\n\nHub: %s\n"
                "Descriptive protected-pivot study (no trades).\n"
                "no_cutoff=%s formation_cutoff=%s smoke=%s config_hash=%s\n"
                % (
                    STUDY_ID,
                    hub,
                    NO_CUTOFF,
                    "none (obs_end 13:00)" if NO_CUTOFF else "10:30",
                    args.smoke,
                    cfg_hash,
                )
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: %s STARTED" % STUDY_ID, body=start)

        _progress(hub, "load WICK_REJECT events (no_cutoff=%s)" % NO_CUTOFF)
        events = load_wick_events(smoke=args.smoke)
        _progress(hub, "events n=%d" % len(events))
        ev_by_id = _event_map(events)

        _progress(hub, "load NQ 1m")
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
                    keep.update(days[max(0, i - 5) : i + 25])
            gby = {d: gby[d] for d in days if d in keep}

        _progress(hub, "build RTH tape / 4h")
        tape, _h1, h4, early = build_rth_tape(gby)
        _progress(hub, "tape=%d 4h=%d" % (len(tape), len(h4)))

        _progress(hub, "make_seeds_30")
        seeds, census = make_seeds_30(events, tape, h4, early)
        census.to_csv(hub / "phase0_seed_census.csv", index=False)
        _progress(hub, "eligible seeds=%d" % len(seeds))

        _progress(hub, "seed_ny_open_eligibility")
        elig = build_eligibility(seeds, ev_by_id, gby, early)
        elig.to_csv(hub / "seed_ny_open_eligibility.csv", index=False)
        n_inc = int((elig["included"] == True).sum())  # noqa: E712
        _progress(hub, "included NY opens=%d / seeds=%d" % (n_inc, len(elig)))

        pivot_rows: List[Dict[str, Any]] = []
        cand_rows: List[Dict[str, Any]] = []
        out_rows: List[Dict[str, Any]] = []
        pack_d_meta: List[Dict[str, Any]] = []

        included = elig[elig["included"] == True]  # noqa: E712
        for i, (_, er) in enumerate(included.iterrows()):
            d = date.fromisoformat(str(er["ny_date"]))
            open_ts = _localize(pd.Timestamp(er["ny_open_ts"]))
            day_1m = _day_rth(gby, d)
            day_5m = _to_5m(day_1m)
            pivots = build_strict_5m_pivots(day_5m, er["seed_id"], er["ny_date"], open_ts)
            for p in pivots:
                pub = {k: v for k, v in p.items() if not k.startswith("_")}
                pivot_rows.append(pub)

            cand, d_reason, near = select_structure(pivots, er.to_dict(), open_ts)
            if cand is None:
                pack_d_meta.append(
                    {
                        "seed_id": er["seed_id"],
                        "ny_date": er["ny_date"],
                        "reason": d_reason,
                        "near_miss": near,
                    }
                )
            else:
                # attach explicit pivot timestamps for audit
                cand["p1_ts"] = cand["_p1"]["_pivot_ts"].isoformat()
                cand["p2_ts"] = cand["_p2"]["_pivot_ts"].isoformat()
                cand["p3_ts"] = cand["_p3"]["_pivot_ts"].isoformat()
                cand["p4_ts"] = cand["_p4"]["_pivot_ts"].isoformat()
                cand["p1_available_at"] = cand["_p1"]["_avail"].isoformat()
                cand["p2_available_at"] = cand["_p2"]["_avail"].isoformat()
                cand["p3_available_at"] = cand["_p3"]["_avail"].isoformat()
                cand["p4_available_at"] = cand["_p4"]["_avail"].isoformat()
                cand["p1_bar_open_ts"] = cand["_p1"]["_bar_open"].isoformat()
                cand["p2_bar_open_ts"] = cand["_p2"]["_bar_open"].isoformat()
                cand["p3_bar_open_ts"] = cand["_p3"]["_bar_open"].isoformat()
                cand["p4_bar_open_ts"] = cand["_p4"]["_bar_open"].isoformat()
                out = evaluate_protection(cand, day_5m)
                pub_c = {k: v for k, v in cand.items() if not k.startswith("_")}
                cand_rows.append(pub_c)
                out_rows.append(out)

            if (i + 1) % 10 == 0:
                _progress(hub, "structures %d/%d" % (i + 1, len(included)))

        pivots_df = pd.DataFrame(pivot_rows)
        cands = pd.DataFrame(cand_rows)
        outs = pd.DataFrame(out_rows)
        pivots_df.to_csv(hub / "five_minute_pivot_ledger.csv", index=False)
        cands.to_csv(hub / "structure_candidates.csv", index=False)
        outs.to_csv(hub / "protection_outcomes.csv", index=False)
        pd.DataFrame(pack_d_meta).to_csv(hub / "pack_d_reasons.csv", index=False)
        _progress(
            hub,
            "pivots=%d candidates=%d outcomes=%d pack_d=%d"
            % (len(pivots_df), len(cands), len(outs), len(pack_d_meta)),
        )

        ok, fails, assertions = run_causality_audit(elig, cands, outs)
        assertions.to_csv(hub / "causality_assertions.csv", index=False)
        write_causality_audit(hub, ok, fails, elig, cands, outs)
        _progress(hub, "causality %s" % ("PASS" if ok else "FAIL"))

        metrics = compute_summary(elig, cands, outs, ok)
        write_summary_md(hub, metrics, cfg_hash)
        (hub / "STATUS.md").write_text(
            "# STATUS\n\nstance: %s\ncausality: %s\n" % (metrics["stance"], "PASS" if ok else "FAIL"),
            encoding="utf-8",
        )

        if not args.skip_charts:
            _progress(hub, "charts packs A–D")
            generate_charts(
                hub, elig, pivots_df, cands, outs, pack_d_meta, gby, h4, cfg_hash, args.smoke
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
        (hub / "RUN_COMPLETE.json").write_text(json.dumps(rc, indent=2, default=str), encoding="utf-8")

        body = (
            "potions: %s COMPLETE\n\nHub: %s\n"
            "config_hash: %s\nsmoke: %s\nno_cutoff: %s\n"
            "formation_cutoff: %s\n"
            "parent: nq_wick_reject_4h_ny_open_1m_protected_pivot_v1 (archived_negative)\n"
            "v2_cutoff_ref: nq_wick_reject_4h_ny_open_5m_protected_pivot_v2 "
            "(hash d3b30d168b0bb59b, insufficient_sample n=7)\n"
            "eligible_opens: %d\ncandidates: %d (bear=%d bull=%d)\n"
            "bear_hold: %s\nbull_hold: %s\n"
            "causality: %s\n"
            "decision: %s\n"
            "stance: %s\n\n"
            "DESCRIPTIVE ONLY — no trade / plugin / S1-S2 promotion.\n"
            "Independent of V1; not a timeframe chooser.\n"
            "%s"
            % (
                STUDY_ID,
                hub,
                cfg_hash,
                args.smoke,
                NO_CUTOFF,
                "none (obs_end 13:00)" if NO_CUTOFF else "10:30",
                metrics["eligible_seed_count"],
                metrics["candidate_count"],
                metrics["bear_count"],
                metrics["bull_count"],
                (
                    "%.1f%%" % (100 * metrics["bear_protection_hold_rate"])
                    if metrics["bear_protection_hold_rate"] == metrics["bear_protection_hold_rate"]
                    else "n/a"
                ),
                (
                    "%.1f%%" % (100 * metrics["bull_protection_hold_rate"])
                    if metrics["bull_protection_hold_rate"] == metrics["bull_protection_hold_rate"]
                    else "n/a"
                ),
                "PASS" if ok else "FAIL",
                metrics.get("decision", ""),
                metrics["stance"],
                (
                    "NOTE: window-widening diagnostic vs frozen V2; not a rescue of the family archive.\n"
                    if NO_CUTOFF
                    else ""
                ),
            )
        )
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")

        if not ok:
            fail_run(rid, error="causality FAIL: " + "; ".join(fails[:5]))
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
                "bear_hold": metrics["bear_protection_hold_rate"],
                "bull_hold": metrics["bull_protection_hold_rate"],
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
        fail_run(rid, error=str(exc))
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
