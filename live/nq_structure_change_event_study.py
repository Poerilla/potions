"""NQ structure-change event atlas (Phases 1–4) + outcome/R-unit audit.

Pure event study on frozen StructureProgramEngine (L/R=2, list=20, takeouts=2).
Primary TF = 4h RTH; secondary = 1h RTH. No strategy prototypes (Phase 5 gated).

Outcome directions (audit fix):
  CLOSE_BREAK   → same as break
  WICK_REJECT   → opposite of wick breach
  CLOSE_RECLAIM → reclaim direction (opposite of prior break)
  TOUCH_ONLY    → no directional hypothesis (absolute excursion only)

R units: ATR_20 (structure TF) and structural-stop |entry − protected swing|.

Usage:
  python -m live.nq_structure_change_event_study --smoke
  python -m live.nq_structure_change_event_study --email
  python -m live.nq_structure_change_event_study --start 2020-01-01 --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .structure_program_st_chart_bias_4h import to_4h
from .structure_program_st_chart_bias_levels import to_1h
from .structure_program_st_study import (
    Structure,
    StructureProgramEngine,
    confirm_swings,
    rth_slice,
    try_form_structures,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_structure_change_event_study"
NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
ENGINE_VERSION = "StructureProgramEngine_v1_existing"
PEN_PRIMARY = 0.05
RECLAIM_WINDOW_BARS = 3  # structure-TF bars after CLOSE_BREAK
LOOKBACK_DAYS_4H = 40
LOOKBACK_DAYS_1H = 15
ATR_LEN = 20
HOLDOUT_FRAC = 0.25
SAMPLE_DESC_N = 30
TICK = 0.25  # NQ


@dataclass
class WatchLevel:
    structure_id: str
    kind: str  # bull | bear
    key: float
    p4: float
    formed_ts: pd.Timestamp
    formed_bar_i: int
    transition: str  # LH-LL-HH | HL-HH-LL
    evented_inv: bool = False
    evented_cont: bool = False
    pending_break: Optional[dict] = None  # awaiting reclaim window
    pending_age: int = 0


@dataclass
class WalkState:
    eng: StructureProgramEngine
    buf: List[pd.DataFrame] = field(default_factory=list)
    watches: List[WatchLevel] = field(default_factory=list)
    atr_tr: List[float] = field(default_factory=list)
    atr: Optional[float] = None
    bar_i: int = 0
    struct_seq: int = 0
    prev_close: Optional[float] = None


def _localize(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def _bar_end(ts: pd.Timestamp, hours: float) -> pd.Timestamp:
    return _localize(ts) + pd.Timedelta(hours=hours)


def _true_range(hi: float, lo: float, prev_close: Optional[float]) -> float:
    if prev_close is None:
        return hi - lo
    return max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))


def _update_atr(st: WalkState, hi: float, lo: float, close: float) -> Optional[float]:
    tr = _true_range(hi, lo, st.prev_close)
    st.atr_tr.append(tr)
    st.prev_close = close
    if len(st.atr_tr) < ATR_LEN:
        st.atr = None
        return None
    # Wilder-ish simple SMA of last ATR_LEN TRs (frozen diagnostic, not optimized)
    st.atr = float(np.mean(st.atr_tr[-ATR_LEN:]))
    return st.atr


def _session_bucket(ts: pd.Timestamp) -> str:
    t = _localize(ts)
    hm = t.hour * 60 + t.minute
    if 9 * 60 + 30 <= hm < 10 * 60 + 30:
        return "NY_OPEN"
    if 10 * 60 + 30 <= hm < 12 * 60:
        return "NY_AM"
    if 12 * 60 <= hm < 14 * 60:
        return "NY_MIDDAY"
    if 14 * 60 <= hm < 15 * 60 + 30:
        return "NY_PM"
    if 15 * 60 + 30 <= hm < 16 * 60:
        return "NY_CLOSE"
    return "GLOBEX"


def _week_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


def _bias_label(ready: bool, program: Optional[str]) -> str:
    if not ready or program is None:
        return "neutral"
    if program == "buy":
        return "bullish"
    if program == "sell":
        return "bearish"
    return "neutral"


def _ingest_bar(
    st: WalkState,
    ts: pd.Timestamp,
    row: pd.Series,
    by_confirm: Dict[pd.Timestamp, list],
) -> List[Structure]:
    """Mirror chart_bias_4h ingest; return newly formed structures."""
    new: List[Structure] = []
    for sw in by_confirm.get(ts, []):
        if st.eng.swings and st.eng.swings[-1][1] == sw[1]:
            prev = st.eng.swings[-1]
            if sw[1] == "H" and sw[2] >= prev[2]:
                st.eng.swings[-1] = sw
            elif sw[1] == "L" and sw[2] <= prev[2]:
                st.eng.swings[-1] = sw
            else:
                continue
        else:
            st.eng.swings.append(sw)
        for formed in try_form_structures(st.eng.swings):
            sig = (formed.kind, round(formed.key, 4), round(formed.p4, 4), str(formed.formed_ts))
            if sig in st.eng._seen_structure_keys:
                continue
            st.eng._seen_structure_keys.add(sig)
            if formed.kind == "bull":
                st.eng.bull.append(formed)
            else:
                st.eng.bear.append(formed)
            new.append(formed)
    st.eng._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
    return new


def _classify_vs_level(
    *,
    hi: float,
    lo: float,
    close: float,
    level: float,
    direction: str,  # bullish break = above; bearish = below
    atr: float,
    min_pen: float,
) -> Tuple[Optional[str], float, float]:
    """Return (event_type or None, penetration_pts, penetration_ATR)."""
    if atr <= 0:
        return None, 0.0, 0.0
    if direction == "bullish":
        extreme = hi
        pen_pts = extreme - level
        close_beyond = close > level
        wick_beyond = hi > level and close <= level
        touch = hi >= level
    else:
        extreme = lo
        pen_pts = level - extreme
        close_beyond = close < level
        wick_beyond = lo < level and close >= level
        touch = lo <= level
    if not touch or pen_pts < 0:
        return None, 0.0, 0.0
    pen_atr = pen_pts / atr
    if close_beyond and pen_atr >= min_pen:
        return "CLOSE_BREAK", pen_pts, pen_atr
    if wick_beyond and pen_atr >= min_pen:
        return "WICK_REJECT", pen_pts, pen_atr
    if touch and pen_atr < min_pen:
        return "TOUCH_ONLY", pen_pts, pen_atr
    if close_beyond and pen_atr < min_pen:
        return "TOUCH_ONLY", pen_pts, pen_atr
    return None, pen_pts, pen_atr


def _body_metrics(o: float, h: float, l: float, c: float, level: float, atr: float, direction: str):
    body = abs(c - o)
    full = max(h - l, 1e-9)
    if direction == "bullish":
        body_dist = (c - level) / atr if atr else 0.0
        wick = max(0.0, h - max(o, c))
    else:
        body_dist = (level - c) / atr if atr else 0.0
        wick = max(0.0, min(o, c) - l)
    ratio = wick / body if body > 1e-9 else (999.0 if wick > 0 else 0.0)
    return body_dist, ratio, body / full


def _opp_dir(direction: str) -> str:
    return "bearish" if direction == "bullish" else "bullish"


def _primary_outcome_direction(event_type: str, break_direction: str) -> Optional[str]:
    """Economically correct expansion hypothesis for each event class."""
    if event_type == "CLOSE_BREAK":
        return break_direction
    if event_type in ("WICK_REJECT", "CLOSE_RECLAIM"):
        return _opp_dir(break_direction)
    if event_type == "TOUCH_ONLY":
        return None
    return break_direction


def _session_windows(
    start: pd.Timestamp, session_dates: Sequence[date]
) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp], bool]:
    """First eligible RTH session end + two-session end; observability flag.

    Post-close / after-RTH entries use the *next* RTH day as session 1 so
    session and two-session horizons never collapse to the same timestamp.
    """
    start = _localize(start)
    d0 = start.date()
    sess_set = set(session_dates)
    future = [d for d in session_dates if d >= d0]
    if not future:
        return None, None, False
    close_d0 = pd.Timestamp(datetime.combine(d0, RTH_CLOSE), tz=NY)
    if d0 in sess_set and start < close_d0:
        sess1_day = d0
        rest = [d for d in future if d > d0]
    else:
        rest0 = [d for d in future if d > d0] if d0 in sess_set else future
        if not rest0:
            return None, None, False
        sess1_day = rest0[0]
        rest = rest0[1:]
    sess_end = pd.Timestamp(datetime.combine(sess1_day, RTH_CLOSE), tz=NY)
    if not rest:
        return sess_end, sess_end, False  # not fully observable for two sessions
    sess2_end = pd.Timestamp(datetime.combine(rest[0], RTH_CLOSE), tz=NY)
    return sess_end, sess2_end, True


def _signed_excursions(entry: float, h: float, l: float, c: float, direction: str) -> Tuple[float, float, float]:
    """Favorable pts, adverse pts, signed close return pts for direction."""
    if direction == "bullish":
        return h - entry, entry - l, c - entry
    return entry - l, h - entry, entry - c


def _legacy_aliases(out: dict) -> None:
    for legacy, modern in [
        ("forward_5m_return_R", "forward_5m_return_ATR"),
        ("forward_15m_return_R", "forward_15m_return_ATR"),
        ("forward_30m_return_R", "forward_30m_return_ATR"),
        ("forward_60m_return_R", "forward_60m_return_ATR"),
        ("forward_1session_return_R", "forward_1session_return_ATR"),
        ("forward_2session_return_R", "forward_2session_return_ATR"),
        ("forward_MAE_R", "forward_MAE_ATR"),
        ("forward_MFE_R", "forward_MFE_ATR"),
        ("expansion_short_1R_60m", "expansion_short_1R_60m_ATR"),
        ("expansion_session_2R", "expansion_session_2R_ATR"),
        ("expansion_multi_3R", "expansion_multi_3R_ATR"),
        ("expansion_failed", "expansion_failed_ATR"),
        ("time_to_1R_min", "time_to_1R_min_ATR"),
    ]:
        out[legacy] = out.get(modern, np.nan)


def _measure_direction_path(
    tape: pd.DataFrame,
    pos: int,
    start: pd.Timestamp,
    entry: float,
    direction: Optional[str],
    denoms: Dict[str, float],
    sess_end: Optional[pd.Timestamp],
    end_2s: Optional[pd.Timestamp],
) -> dict:
    """Single path pass: point excursions + per-denom hit flags/timing."""
    horizons = {"forward_5m_return": 5, "forward_15m_return": 15, "forward_30m_return": 30, "forward_60m_return": 60}
    st = {
        "mfe_pts": 0.0,
        "mae_pts": 0.0,
        "fav_60": 0.0,
        "fav_sess": 0.0,
        "fav_multi": 0.0,
        "ret_h": {k: np.nan for k in horizons},
        "ret_sess": np.nan,
        "ret_2s": np.nan,
        "immediate": 0,
        "abs_mfe": 0.0,
        "per_denom": {
            u: {
                "time_1r": np.nan,
                "time_1r_60": np.nan,
                "hit": False,
                "opp_first": False,
                "failed": 0,
            }
            for u in denoms
        },
    }
    if sess_end is None or end_2s is None:
        return st
    idx = tape.index
    atr_ref = denoms.get("ATR") or 1.0
    for j in range(pos, len(idx)):
        ts = idx[j]
        if ts > end_2s:
            break
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        c = float(tape["close"].iloc[j])
        mins = (ts - start).total_seconds() / 60.0
        if direction is None:
            up, dn = h - entry, entry - l
            fav, adv, ret = max(up, dn), 0.0, abs(c - entry)
            st["abs_mfe"] = max(st["abs_mfe"], fav)
        else:
            fav, adv, ret = _signed_excursions(entry, h, l, c, direction)
        st["mfe_pts"] = max(st["mfe_pts"], fav)
        st["mae_pts"] = max(st["mae_pts"], adv)
        if mins <= 60:
            st["fav_60"] = max(st["fav_60"], fav)
        if ts <= sess_end:
            st["fav_sess"] = max(st["fav_sess"], fav)
            st["ret_sess"] = ret
        st["fav_multi"] = max(st["fav_multi"], fav)
        st["ret_2s"] = ret
        if direction is not None:
            if mins <= 5 and adv >= 0.25 * atr_ref and fav < 0.25 * atr_ref:
                st["immediate"] = 1
            for unit, denom in denoms.items():
                if denom <= 0:
                    continue
                pdn = st["per_denom"][unit]
                if not pdn["hit"] and fav / denom >= 1.0:
                    pdn["hit"] = True
                    pdn["time_1r"] = mins
                    if mins <= 60:
                        pdn["time_1r_60"] = mins
                if not pdn["hit"] and adv / denom >= 1.0:
                    pdn["opp_first"] = True
        for k, m in horizons.items():
            if mins <= m:
                st["ret_h"][k] = ret
    for k, m in horizons.items():
        end_t = start + pd.Timedelta(minutes=m)
        j2 = idx.searchsorted(end_t, side="right") - 1
        if j2 < pos:
            continue
        c = float(tape["close"].iloc[j2])
        if direction is None:
            st["ret_h"][k] = abs(c - entry)
        elif direction == "bullish":
            st["ret_h"][k] = c - entry
        else:
            st["ret_h"][k] = entry - c
    for unit, pdn in st["per_denom"].items():
        pdn["failed"] = int(pdn["opp_first"] and not pdn["hit"])
    return st


def _apply_path_to_out(out: dict, tag: str, st: dict, denoms: Dict[str, float], use_abs: bool) -> None:
    mfe_pts = st["abs_mfe"] if use_abs else st["mfe_pts"]
    mae_pts = 0.0 if use_abs else st["mae_pts"]
    ret_sess = 0.0 if np.isnan(st["ret_sess"]) else st["ret_sess"]
    ret_2s = 0.0 if np.isnan(st["ret_2s"]) else st["ret_2s"]
    for unit, denom in denoms.items():
        if denom <= 0 or np.isnan(denom):
            continue
        pref = tag
        pdn = st["per_denom"][unit]
        out["%sforward_MAE_%s" % (pref, unit)] = mae_pts / denom
        out["%sforward_MFE_%s" % (pref, unit)] = mfe_pts / denom
        for hk, pts in st["ret_h"].items():
            out["%s%s_%s" % (pref, hk, unit)] = (pts / denom) if not np.isnan(pts) else np.nan
        out["%sforward_1session_return_%s" % (pref, unit)] = ret_sess / denom
        out["%sforward_2session_return_%s" % (pref, unit)] = ret_2s / denom
        out["%sexpansion_short_1R_60m_%s" % (pref, unit)] = int(st["fav_60"] / denom >= 1.0)
        out["%sexpansion_session_2R_%s" % (pref, unit)] = int(st["fav_sess"] / denom >= 2.0)
        out["%sexpansion_multi_3R_%s" % (pref, unit)] = int(st["fav_multi"] / denom >= 3.0)
        out["%sexpansion_failed_%s" % (pref, unit)] = int(pdn["failed"])
        out["%stime_to_1R_min_%s" % (pref, unit)] = pdn["time_1r"]
        out["%stime_to_1R_within_60m_%s" % (pref, unit)] = pdn["time_1r_60"]
        out["%sexpansion_hit_1R_any_%s" % (pref, unit)] = int(mfe_pts / denom >= 1.0)
    if tag == "":
        out["immediate_retrace_flag"] = int(st["immediate"])


def _empty_forward_out() -> dict:
    out: dict = {
        "entry_price": np.nan,
        "r_atr_points": np.nan,
        "r_structural_points": np.nan,
        "stop_distance_points": np.nan,
        "stop_distance_1m_ATR": np.nan,
        "stop_distance_4h_ATR": np.nan,
        "forward_observable_two_session": 0,
        "session_end_ts": "",
        "two_session_end_ts": "",
        "outcome_direction": "",
        "break_direction": "",
        "immediate_retrace_flag": 0,
        "forward_abs_MFE_ATR": np.nan,
        "forward_abs_MFE_structR": np.nan,
        "expansion_same_direction_flag": 0,
        "expansion_opposite_direction_flag": 0,
    }
    for tag in ("", "break_"):
        for unit in ("ATR", "structR"):
            for k in (
                "forward_5m_return",
                "forward_15m_return",
                "forward_30m_return",
                "forward_60m_return",
                "forward_1session_return",
                "forward_2session_return",
                "forward_MAE",
                "forward_MFE",
            ):
                out["%s%s_%s" % (tag, k, unit)] = np.nan
            for k in (
                "expansion_short_1R_60m",
                "expansion_session_2R",
                "expansion_multi_3R",
                "expansion_failed",
                "expansion_hit_1R_any",
            ):
                out["%s%s_%s" % (tag, k, unit)] = 0
            out["%stime_to_1R_min_%s" % (tag, unit)] = np.nan
            out["%stime_to_1R_within_60m_%s" % (tag, unit)] = np.nan
    _legacy_aliases(out)
    return out


def _forward_path(
    tape: pd.DataFrame,
    start_ts: pd.Timestamp,
    *,
    atr: float,
    break_direction: str,
    outcome_direction: Optional[str],
    structural_stop_pts: float,
    atr_1m: Optional[float],
    session_dates: Sequence[date],
) -> dict:
    """Path-aware forwards in ATR and structural-stop R; outcome + break dirs."""
    out = _empty_forward_out()
    if atr is None or atr <= 0 or tape is None or tape.empty:
        return out
    start = _localize(start_ts)
    idx = tape.index
    pos = idx.searchsorted(start, side="left")
    if pos >= len(idx):
        return out
    entry = float(tape["open"].iloc[pos])
    stop_pts = float(structural_stop_pts) if structural_stop_pts and structural_stop_pts > 0 else float(atr)
    stop_pts = max(stop_pts, TICK)
    sess_end, end_2s, observable = _session_windows(start, session_dates)
    denoms = {"ATR": float(atr), "structR": float(stop_pts)}
    out["entry_price"] = entry
    out["r_atr_points"] = float(atr)
    out["r_structural_points"] = stop_pts
    out["stop_distance_points"] = stop_pts
    out["stop_distance_1m_ATR"] = stop_pts / atr_1m if atr_1m and atr_1m > 0 else np.nan
    out["stop_distance_4h_ATR"] = stop_pts / atr
    out["forward_observable_two_session"] = int(observable)
    out["session_end_ts"] = sess_end.isoformat() if sess_end is not None else ""
    out["two_session_end_ts"] = end_2s.isoformat() if end_2s is not None else ""
    out["outcome_direction"] = outcome_direction or ""
    out["break_direction"] = break_direction

    st_out = _measure_direction_path(
        tape, pos, start, entry, outcome_direction, denoms, sess_end, end_2s
    )
    _apply_path_to_out(out, "", st_out, denoms, use_abs=(outcome_direction is None))
    abs_pts = st_out["abs_mfe"] if outcome_direction is None else max(st_out["mfe_pts"], st_out["mae_pts"])
    out["forward_abs_MFE_ATR"] = abs_pts / atr
    out["forward_abs_MFE_structR"] = abs_pts / stop_pts

    st_brk = _measure_direction_path(
        tape, pos, start, entry, break_direction, denoms, sess_end, end_2s
    )
    _apply_path_to_out(out, "break_", st_brk, denoms, use_abs=False)

    _legacy_aliases(out)
    out["expansion_same_direction_flag"] = int(out.get("expansion_hit_1R_any_ATR") or 0)
    out["expansion_opposite_direction_flag"] = int(
        (out.get("forward_MAE_ATR") or 0) >= 1.0 and not out["expansion_same_direction_flag"]
    )
    return out


def _vol_bucket(atr: Optional[float], atr_hist: List[float]) -> str:
    if atr is None or not atr_hist:
        return "UNK"
    arr = np.asarray(atr_hist[-252:], dtype=float)
    if len(arr) < 20:
        return "UNK"
    pct = float((arr <= atr).mean())
    if pct < 0.33:
        return "LOW"
    if pct < 0.66:
        return "MID"
    return "HIGH"


def walk_tf(
    *,
    gby: Dict[date, pd.DataFrame],
    tf_name: str,
    hours: float,
    resample_fn,
    lookback_days: int,
    days: List[date],
    min_pen: float,
) -> Tuple[List[dict], pd.DataFrame]:
    """Walk one structure TF; return event rows + causal snapshot frame."""
    st = WalkState(eng=StructureProgramEngine())
    events: List[dict] = []
    snaps: List[dict] = []
    atr_hist: List[float] = []

    print("Walking %s engine over %d days (pen>=%.3f)…" % (tf_name, len(days), min_pen), flush=True)
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        bars = resample_fn(rth)
        if bars.empty:
            continue
        frames = [b for b in st.buf[-lookback_days:] if b is not None and not b.empty]
        frames.append(bars)
        combined = pd.concat(frames)
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        day_start = bars.index[0]
        day_swings = confirm_swings(combined)
        by_confirm: Dict[pd.Timestamp, list] = {}
        for sw in day_swings:
            if sw[0] < day_start:
                continue
            by_confirm.setdefault(sw[0], []).append(sw)

        for ts, row in bars.iterrows():
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            atr = _update_atr(st, h, l, c)
            if atr is not None:
                atr_hist.append(atr)
            new_structs = _ingest_bar(st, ts, row, by_confirm)
            for ns in new_structs:
                st.struct_seq += 1
                sid = "%s_%s_%d" % (tf_name, ns.kind, st.struct_seq)
                trans = "LH-LL-HH" if ns.kind == "bull" else "HL-HH-LL"
                st.watches.append(
                    WatchLevel(
                        structure_id=sid,
                        kind=ns.kind,
                        key=float(ns.key),
                        p4=float(ns.p4),
                        formed_ts=_localize(ns.formed_ts),
                        formed_bar_i=st.bar_i,
                        transition=trans,
                    )
                )

            bar_end = _bar_end(ts, hours)
            feature_at = bar_end
            order_active = feature_at + pd.Timedelta(minutes=1)
            prior_bias = _bias_label(st.eng.ready, st.eng.program)

            # age pending reclaim watches
            for w in st.watches:
                if w.pending_break is not None:
                    w.pending_age += 1
                    # reclaim check: close back inside
                    if w.kind == "bull":
                        # invalidation was bearish (below key); reclaim = close back above key
                        reclaimed = c > w.key
                        inv_dir = "bearish"
                    else:
                        reclaimed = c < w.key
                        inv_dir = "bullish"
                    if reclaimed and w.pending_age <= RECLAIM_WINDOW_BARS:
                        pb = w.pending_break
                        break_dir = str(pb.get("break_direction") or pb.get("event_direction"))
                        reclaim_dir = _opp_dir(break_dir)
                        events.append(
                            {
                                **pb,
                                "event_id": "%s_RECLAIM_%d" % (pb["event_id"], st.bar_i),
                                "event_type": "CLOSE_RECLAIM",
                                "event_direction": break_dir,  # original breach dir
                                "break_direction": break_dir,
                                "outcome_direction": reclaim_dir,
                                "confirm_bar_open_ts": _localize(ts).isoformat(),
                                "confirm_bar_close_ts": bar_end.isoformat(),
                                "feature_available_at": feature_at.isoformat(),
                                "order_active_ts": order_active.isoformat(),
                                "reclaim_time_bars": w.pending_age,
                                "penetration_points": abs(c - w.key),
                                "penetration_ATR": abs(c - w.key) / atr if atr else np.nan,
                            }
                        )
                        w.pending_break = None
                    elif w.pending_age > RECLAIM_WINDOW_BARS:
                        w.pending_break = None

            # classify interactions on invalidation + continuation levels
            for w in list(st.watches):
                age = st.bar_i - w.formed_bar_i
                if age < 1:
                    continue  # no same-bar self-trigger on formation
                if atr is None:
                    continue
                # invalidation direction
                inv_dir = "bearish" if w.kind == "bull" else "bullish"
                cont_dir = "bullish" if w.kind == "bull" else "bearish"
                targets = []
                if not w.evented_inv:
                    targets.append(("invalidation", w.key, inv_dir))
                if not w.evented_cont:
                    targets.append(("continuation", w.p4, cont_dir))
                for family, level, direction in targets:
                    etype, pen_pts, pen_atr = _classify_vs_level(
                        hi=h, lo=l, close=c, level=level, direction=direction, atr=atr, min_pen=min_pen
                    )
                    if etype is None:
                        continue
                    body_dist, wick_ratio, _ = _body_metrics(o, h, l, c, level, atr, direction)
                    eid = "%s_%s_%s_%d" % (w.structure_id, family[:3].upper(), etype[:5], st.bar_i)
                    out_dir = _primary_outcome_direction(etype, direction)
                    row_ev = {
                        "event_id": eid,
                        "market": "NQ",
                        "symbol": "NQ",
                        "structure_engine_version": ENGINE_VERSION,
                        "structure_timeframe": tf_name,
                        "prior_bias": prior_bias,
                        "new_bias": prior_bias,  # updated below if program flipped this bar
                        "transition_type": w.transition if family == "invalidation" else "continuation_p4",
                        "event_family": family,
                        "protected_swing_price": level,
                        "protected_swing_timestamp": w.formed_ts.isoformat(),
                        "swing_confirmed_at": w.formed_ts.isoformat(),
                        "swing_age_bars": age,
                        "structure_id": w.structure_id,
                        "structure_kind": w.kind,
                        "event_type": etype,
                        "event_direction": direction,  # breach / break direction
                        "break_direction": direction,
                        "outcome_direction": out_dir if out_dir else "",
                        "confirm_bar_open_ts": _localize(ts).isoformat(),
                        "confirm_bar_close_ts": bar_end.isoformat(),
                        "feature_available_at": feature_at.isoformat(),
                        "order_active_ts": order_active.isoformat(),
                        "penetration_points": pen_pts,
                        "penetration_ticks": pen_pts / TICK,
                        "penetration_ATR": pen_atr,
                        "body_close_distance_ATR": body_dist,
                        "wick_to_body_ratio": wick_ratio,
                        "entry_session": _session_bucket(order_active),
                        "entry_hour_NY": int(_localize(order_active).hour),
                        "day_of_week": _localize(order_active).day_name(),
                        "week_of_month": _week_of_month(_localize(order_active).date()),
                        "month": int(_localize(order_active).month),
                        "atr_20": atr,
                        "vol_bucket": _vol_bucket(atr, atr_hist),
                        "min_pen_ATR": min_pen,
                        "reclaim_time_bars": np.nan,
                        "slice": "dev",  # filled later
                    }
                    # program may have flipped via takeouts on this bar
                    row_ev["new_bias"] = _bias_label(st.eng.ready, st.eng.program)
                    events.append(row_ev)
                    # Zero-buffer robustness twin for TOUCH_ONLY (pen>0 but <0.05)
                    if etype == "TOUCH_ONLY" and pen_atr > 0:
                        zb = dict(row_ev)
                        zb["event_id"] = eid + "_ZB"
                        zb["min_pen_ATR"] = 0.0
                        zb_type = (
                            "CLOSE_BREAK"
                            if (direction == "bullish" and c > level)
                            or (direction == "bearish" and c < level)
                            else "WICK_REJECT"
                        )
                        zb["event_type"] = zb_type
                        zb["outcome_direction"] = _primary_outcome_direction(zb_type, direction) or ""
                        events.append(zb)
                    if family == "invalidation":
                        w.evented_inv = True
                        if etype == "CLOSE_BREAK":
                            w.pending_break = dict(row_ev)
                            w.pending_age = 0
                    else:
                        w.evented_cont = True

            snaps.append(
                {
                    "structure_bar_ts": _localize(ts).isoformat(),
                    "structure_feature_available_at": feature_at.isoformat(),
                    "program": st.eng.program or "",
                    "ready": bool(st.eng.ready),
                    "bias": _bias_label(st.eng.ready, st.eng.program),
                    "atr_20": atr if atr is not None else np.nan,
                    "session_date": d.isoformat(),
                    "tf": tf_name,
                }
            )
            st.bar_i += 1

        st.buf.append(bars)
        st.buf = st.buf[-lookback_days:]
        if di % 250 == 0:
            print(
                "  %s %d/%d days | events %d | prog=%s ready=%s"
                % (tf_name, di, len(days), len(events), st.eng.program, st.eng.ready),
                flush=True,
            )

    print("%s done: %d events, %d snaps" % (tf_name, len(events), len(snaps)), flush=True)
    return events, pd.DataFrame(snaps)


def _build_1m_tape(gby: Dict[date, pd.DataFrame], days: List[date]) -> pd.DataFrame:
    frames = []
    for d in days:
        rth = rth_slice(gby.get(d))
        if rth is not None and not rth.empty:
            frames.append(rth)
    if not frames:
        return pd.DataFrame()
    tape = pd.concat(frames)
    tape = tape[~tape.index.duplicated(keep="last")].sort_index()
    return tape


def _atr_1m_at(tape: pd.DataFrame, ts: pd.Timestamp, n: int = 20) -> Optional[float]:
    """Simple SMA true-range ATR on 1m tape ending at/before ts."""
    if tape is None or tape.empty:
        return None
    ts = _localize(ts)
    pos = tape.index.searchsorted(ts, side="right") - 1
    if pos < n:
        return None
    window = tape.iloc[pos - n : pos + 1]
    prev = None
    trs = []
    for _, r in window.iterrows():
        h, l, c = float(r["high"]), float(r["low"]), float(r["close"])
        trs.append(_true_range(h, l, prev))
        prev = c
    if len(trs) < n:
        return None
    return float(np.mean(trs[-n:]))


def enrich_forwards(events: List[dict], tape: pd.DataFrame, session_dates: List[date]) -> pd.DataFrame:
    rows = []
    n = len(events)
    for i, ev in enumerate(events):
        if i % 500 == 0 and i:
            print("  enrich %d/%d" % (i, n), flush=True)
        atr = float(ev.get("atr_20") or 0)
        oa = _localize(pd.Timestamp(ev["order_active_ts"]))
        break_dir = str(ev.get("break_direction") or ev.get("event_direction") or "bullish")
        etype = str(ev.get("event_type") or "")
        out_raw = ev.get("outcome_direction")
        if out_raw is None or (isinstance(out_raw, float) and np.isnan(out_raw)) or out_raw == "":
            out_dir = _primary_outcome_direction(etype, break_dir)
        else:
            out_dir = str(out_raw)
        # structural stop = |entry open − protected swing|; entry resolved inside _forward_path
        level = float(ev.get("protected_swing_price") or 0)
        # provisional entry ≈ first open at oa (same as path)
        idx = tape.index
        pos = idx.searchsorted(oa, side="left")
        entry_approx = float(tape["open"].iloc[pos]) if pos < len(idx) else level
        stop_pts = abs(entry_approx - level) if level else atr
        # wick reject: stop beyond wick extreme ≈ level + penetration in break dir
        if etype == "WICK_REJECT":
            pen = float(ev.get("penetration_points") or 0)
            stop_pts = max(stop_pts, pen, TICK)
        atr_1m = _atr_1m_at(tape, oa)
        fwd = _forward_path(
            tape,
            oa,
            atr=atr,
            break_direction=break_dir,
            outcome_direction=out_dir,
            structural_stop_pts=stop_pts,
            atr_1m=atr_1m,
            session_dates=session_dates,
        )
        # touch_ts approx = first 1m breach inside confirm bar window
        touch = oa
        try:
            bar_open = _localize(pd.Timestamp(ev["confirm_bar_open_ts"]))
            bar_close = _localize(pd.Timestamp(ev["confirm_bar_close_ts"]))
            sl = tape.index.searchsorted(bar_open, side="left")
            sr = tape.index.searchsorted(bar_close, side="right")
            for j in range(sl, min(sr, len(tape))):
                h = float(tape["high"].iloc[j])
                l = float(tape["low"].iloc[j])
                if break_dir == "bullish" and h > level:
                    touch = tape.index[j]
                    break
                if break_dir == "bearish" and l < level:
                    touch = tape.index[j]
                    break
        except Exception:
            pass
        row = dict(ev)
        row["break_direction"] = break_dir
        row["outcome_direction"] = out_dir if out_dir else ""
        row["touch_ts"] = _localize(touch).isoformat()
        row.update(fwd)
        # recompute structural stop with actual entry_price from path
        if pd.notna(row.get("entry_price")) and level:
            actual_stop = abs(float(row["entry_price"]) - level)
            if etype == "WICK_REJECT":
                actual_stop = max(actual_stop, float(ev.get("penetration_points") or 0), TICK)
            row["stop_distance_points"] = max(actual_stop, TICK)
        rows.append(row)
    return pd.DataFrame(rows)


def matched_controls(
    events_df: pd.DataFrame,
    snaps: pd.DataFrame,
    tape: pd.DataFrame,
    session_dates: List[date],
    *,
    n_per_event: int = 1,
    seed: int = 42,
) -> pd.DataFrame:
    """Matched non-event samples: same hour, DOW, vol bucket, prior bias; full forward horizon."""
    rng = np.random.default_rng(seed)
    if events_df.empty or snaps.empty:
        return pd.DataFrame()
    snaps_r = snaps.copy().reset_index(drop=True)
    snaps_r["avail"] = pd.to_datetime(
        snaps_r["structure_feature_available_at"], utc=True
    ).dt.tz_convert(NY)
    snaps_r["hour"] = snaps_r["avail"].dt.hour
    snaps_r["dow"] = snaps_r["avail"].dt.day_name()
    vb: List[str] = []
    hist: List[float] = []
    for a in snaps_r["atr_20"].tolist():
        if pd.notna(a):
            hist.append(float(a))
            vb.append(_vol_bucket(float(a), hist))
        else:
            vb.append("UNK")
    snaps_r["vol_bucket"] = vb

    candidates: Dict[Tuple, List[int]] = defaultdict(list)
    for i, r in snaps_r.iterrows():
        key = (int(r["hour"]), str(r["dow"]), str(r["vol_bucket"]), str(r["bias"]))
        candidates[key].append(i)

    event_times = set(str(x) for x in events_df["feature_available_at"].tolist())
    controls = []
    used = set()
    for _, ev in events_df.iterrows():
        oa_ev = _localize(pd.Timestamp(ev["order_active_ts"]))
        atr = float(ev.get("atr_20") or 0)
        key = (int(ev["entry_hour_NY"]), str(ev["day_of_week"]), str(ev["vol_bucket"]), str(ev["prior_bias"]))
        pool = [i for i in candidates.get(key, []) if i not in used]
        if not pool:
            key2 = (int(ev["entry_hour_NY"]), str(ev["day_of_week"]), str(ev["prior_bias"]))
            pool = [
                i
                for i, r in snaps_r.iterrows()
                if int(r["hour"]) == key2[0]
                and str(r["dow"]) == key2[1]
                and str(r["bias"]) == key2[2]
                and i not in used
            ]
        if not pool:
            continue
        # prefer fully observable two-session windows
        rng.shuffle(pool)
        pick = None
        for cand in pool[: min(40, len(pool))]:
            s = snaps_r.iloc[cand]
            feature_at = _localize(pd.Timestamp(s["avail"]))
            order_active = feature_at + pd.Timedelta(minutes=1)
            _, _, obs = _session_windows(order_active, session_dates)
            if str(s["structure_feature_available_at"]) in event_times:
                continue
            if not obs:
                continue
            pick = cand
            break
        if pick is None:
            pick = int(pool[0])
        used.add(pick)
        s = snaps_r.iloc[pick]
        feature_at = _localize(pd.Timestamp(s["avail"]))
        order_active = feature_at + pd.Timedelta(minutes=1)
        break_dir = str(ev.get("break_direction") or ev.get("event_direction"))
        out_dir_raw = ev.get("outcome_direction")
        if out_dir_raw is None or out_dir_raw == "" or (isinstance(out_dir_raw, float) and np.isnan(out_dir_raw)):
            out_dir = _primary_outcome_direction(str(ev["event_type"]), break_dir)
        else:
            out_dir = str(out_dir_raw)
        ctl_atr = atr if atr > 0 else float(s.get("atr_20") or 1.0)
        level = float(ev.get("protected_swing_price") or 0)
        pos = tape.index.searchsorted(order_active, side="left")
        entry_approx = float(tape["open"].iloc[pos]) if pos < len(tape) else level
        stop_pts = abs(entry_approx - level) if level else ctl_atr
        atr_1m = _atr_1m_at(tape, order_active)
        fwd = _forward_path(
            tape,
            order_active,
            atr=ctl_atr,
            break_direction=break_dir,
            outcome_direction=out_dir if out_dir else break_dir,
            structural_stop_pts=stop_pts,
            atr_1m=atr_1m,
            session_dates=session_dates,
        )
        controls.append(
            {
                "control_id": "CTL_%s_%d" % (ev["event_id"], pick),
                "matched_event_id": ev["event_id"],
                "matched_event_type": ev["event_type"],
                "market": "NQ",
                "structure_timeframe": ev["structure_timeframe"],
                "prior_bias": s["bias"],
                "event_type": "CONTROL",
                "event_direction": break_dir,
                "break_direction": break_dir,
                "outcome_direction": out_dir if out_dir else break_dir,
                "feature_available_at": feature_at.isoformat(),
                "order_active_ts": order_active.isoformat(),
                "entry_session": _session_bucket(order_active),
                "entry_hour_NY": int(order_active.hour),
                "day_of_week": order_active.day_name(),
                "vol_bucket": s["vol_bucket"],
                "atr_20": float(s["atr_20"]) if pd.notna(s["atr_20"]) else atr,
                "protected_swing_price": level,
                **fwd,
            }
        )
    return pd.DataFrame(controls)


def _summarize_group(df: pd.DataFrame, unit: str = "ATR") -> dict:
    if df is None or df.empty:
        return {
            "n": 0,
            "med_fwd_15m": np.nan,
            "med_fwd_60m": np.nan,
            "rate_1R_60m": np.nan,
            "rate_2R_sess": np.nan,
            "rate_3R_multi": np.nan,
            "med_MAE": np.nan,
            "med_MFE": np.nan,
            "med_time_1R": np.nan,
            "med_time_1R_60": np.nan,
            "fail_rate": np.nan,
            "n_1R_60": 0,
            "n_2R": 0,
            "n_3R": 0,
            "n_1R_any": 0,
        }
    c15 = "forward_15m_return_%s" % unit
    c60 = "forward_60m_return_%s" % unit
    # legacy fallback
    if c15 not in df.columns:
        c15, c60 = "forward_15m_return_R", "forward_60m_return_R"
        e1 = "expansion_short_1R_60m"
        e2 = "expansion_session_2R"
        e3 = "expansion_multi_3R"
        mae, mfe = "forward_MAE_R", "forward_MFE_R"
        t1 = "time_to_1R_min"
        fail = "expansion_failed"
        t160 = None
        h1 = "expansion_same_direction_flag"
    else:
        e1 = "expansion_short_1R_60m_%s" % unit
        e2 = "expansion_session_2R_%s" % unit
        e3 = "expansion_multi_3R_%s" % unit
        mae, mfe = "forward_MAE_%s" % unit, "forward_MFE_%s" % unit
        t1 = "time_to_1R_min_%s" % unit
        t160 = "time_to_1R_within_60m_%s" % unit
        fail = "expansion_failed_%s" % unit
        h1 = "expansion_hit_1R_any_%s" % unit
    def _med(col):
        if col not in df.columns:
            return np.nan
        s = pd.to_numeric(df[col], errors="coerce")
        return float(s.median()) if s.notna().any() else np.nan

    def _mean(col):
        if col not in df.columns:
            return np.nan
        s = pd.to_numeric(df[col], errors="coerce")
        return float(s.mean()) if len(s) else np.nan

    def _sum(col):
        if col not in df.columns:
            return 0
        return int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

    return {
        "n": int(len(df)),
        "med_fwd_15m": _med(c15),
        "med_fwd_60m": _med(c60),
        "rate_1R_60m": _mean(e1),
        "rate_2R_sess": _mean(e2),
        "rate_3R_multi": _mean(e3),
        "med_MAE": _med(mae),
        "med_MFE": _med(mfe),
        "med_time_1R": _med(t1),
        "med_time_1R_60": _med(t160) if t160 else np.nan,
        "fail_rate": _mean(fail),
        "n_1R_60": _sum(e1),
        "n_2R": _sum(e2),
        "n_3R": _sum(e3),
        "n_1R_any": _sum(h1),
    }


def _fmt_row(name: str, s: dict) -> str:
    if s["n"] == 0:
        return "| %s | 0 | — | — | — | — | — | — | — | — |" % name
    return (
        "| %s | %d | %.3f | %.3f | %.1f%% | %.1f%% | %.1f%% | %.2f | %.2f | %s |"
        % (
            name,
            s["n"],
            s["med_fwd_15m"],
            s["med_fwd_60m"],
            100 * s["rate_1R_60m"],
            100 * s["rate_2R_sess"],
            100 * s["rate_3R_multi"],
            s["med_MAE"],
            s["med_MFE"],
            ("%.0f" % s["med_time_1R"]) if pd.notna(s["med_time_1R"]) else "—",
        )
    )


def _nesting_check(df: pd.DataFrame, unit: str = "ATR") -> dict:
    """Verify 3R_two_session ⊆ conceptually vs 2R_session counts (horizons differ)."""
    if df is None or df.empty:
        return {
            "ok": True,
            "n": 0,
            "n_2R": 0,
            "n_3R": 0,
            "n_3R_not_2R": 0,
            "n_2R_not_3R": 0,
            "rates_equal": False,
            "sets_identical": True,
        }
    e2 = "expansion_session_2R_%s" % unit
    e3 = "expansion_multi_3R_%s" % unit
    if e2 not in df.columns:
        e2, e3 = "expansion_session_2R", "expansion_multi_3R"
    if e2 not in df.columns or e3 not in df.columns:
        return {
            "ok": False,
            "n": int(len(df)),
            "n_2R": 0,
            "n_3R": 0,
            "n_3R_not_2R": 0,
            "n_2R_not_3R": 0,
            "rates_equal": False,
            "sets_identical": True,
        }
    n2 = int(df[e2].sum())
    n3 = int(df[e3].sum())
    n3_not_2 = int(((df[e3] == 1) & (df[e2] == 0)).sum())
    n2_not_3 = int(((df[e2] == 1) & (df[e3] == 0)).sum())
    # Same-window invariant would require n3<=n2; with distinct horizons n3_not_2 can be >0.
    # Flag suspicious when rates equal AND sets differ, or when session_end==two_session_end often.
    return {
        "ok": True,  # informational; detailed in audit
        "n": int(len(df)),
        "n_2R": n2,
        "n_3R": n3,
        "n_3R_not_2R": n3_not_2,
        "n_2R_not_3R": n2_not_3,
        "rates_equal": bool(n2 == n3 and n2 > 0),
        "sets_identical": bool(n3_not_2 == 0 and n2_not_3 == 0 and n2 == n3),
    }


def assign_holdout(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_ts"] = pd.to_datetime(out["feature_available_at"], utc=True)
    out = out.sort_values("_ts")
    n = len(out)
    cut = int(n * (1.0 - HOLDOUT_FRAC))
    out["slice"] = ["dev"] * cut + ["holdout"] * (n - cut)
    return out.drop(columns=["_ts"])



EXAMPLE_COLS = [
    "event_id", "event_type", "break_direction", "outcome_direction", "protected_swing_price",
    "touch_ts", "confirm_bar_close_ts", "feature_available_at", "order_active_ts",
    "entry_price", "atr_20", "r_atr_points", "stop_distance_points", "stop_distance_1m_ATR",
    "stop_distance_4h_ATR", "forward_15m_return_ATR", "forward_60m_return_ATR",
    "forward_1session_return_ATR", "forward_2session_return_ATR",
    "forward_MAE_ATR", "forward_MFE_ATR", "forward_MAE_structR", "forward_MFE_structR",
    "expansion_short_1R_60m_ATR", "expansion_session_2R_ATR", "expansion_multi_3R_ATR",
    "expansion_short_1R_60m_structR", "expansion_session_2R_structR", "expansion_multi_3R_structR",
    "break_expansion_short_1R_60m_ATR", "break_forward_MFE_ATR",
    "time_to_1R_min_ATR", "time_to_1R_within_60m_ATR", "forward_observable_two_session", "slice",
]


def write_outcome_audit(hub: Path, events: pd.DataFrame, controls: pd.DataFrame) -> dict:
    """OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md + example CSVs + nesting checks."""
    hub.mkdir(parents=True, exist_ok=True)
    ex_dir = hub / "audit_examples"
    ex_dir.mkdir(exist_ok=True)

    e4 = events[
        (events["structure_timeframe"] == "4h")
        & (events["event_family"] == "invalidation")
        & (events["min_pen_ATR"] == PEN_PRIMARY)
    ].copy()
    e4_dev = e4[e4["slice"] == "dev"]
    c4 = controls[controls["structure_timeframe"] == "4h"] if not controls.empty else controls

    # --- direction correctness ---
    dir_ok = True
    dir_notes = []
    for et, rule in [
        ("CLOSE_BREAK", "same as break"),
        ("WICK_REJECT", "opposite of break"),
        ("CLOSE_RECLAIM", "opposite of break (reclaim)"),
    ]:
        sub = e4[e4["event_type"] == et]
        if sub.empty:
            dir_notes.append("%s: no rows" % et)
            continue
        bad = 0
        for _, r in sub.iterrows():
            bd = str(r.get("break_direction") or r.get("event_direction"))
            od = str(r.get("outcome_direction") or "")
            expect = bd if et == "CLOSE_BREAK" else _opp_dir(bd)
            if od != expect:
                bad += 1
        if bad:
            dir_ok = False
        dir_notes.append("%s: %d/%d rows match rule (%s)" % (et, len(sub) - bad, len(sub), rule))

    touch = e4[e4["event_type"] == "TOUCH_ONLY"]
    touch_ok = True
    if not touch.empty:
        # outcome_direction should be empty
        nonempty = int((touch["outcome_direction"].astype(str).str.len() > 0).sum())
        if nonempty:
            touch_ok = False
        dir_notes.append("TOUCH_ONLY: %d/%d have empty outcome_direction" % (len(touch) - nonempty, len(touch)))

    # --- R unit diagnostics ---
    stop = pd.to_numeric(e4_dev.get("stop_distance_points"), errors="coerce")
    atr = pd.to_numeric(e4_dev.get("atr_20"), errors="coerce")
    s1m = pd.to_numeric(e4_dev.get("stop_distance_1m_ATR"), errors="coerce")
    s4h = pd.to_numeric(e4_dev.get("stop_distance_4h_ATR"), errors="coerce")

    def _pct(s, q):
        s = s.dropna()
        return float(s.quantile(q)) if len(s) else np.nan

    r_diag = {
        "median_stop_points": float(stop.median()) if stop.notna().any() else np.nan,
        "p25_stop_points": _pct(stop, 0.25),
        "p75_stop_points": _pct(stop, 0.75),
        "p95_stop_points": _pct(stop, 0.95),
        "median_atr_points": float(atr.median()) if atr.notna().any() else np.nan,
        "median_stop_in_1m_ATR": float(s1m.median()) if s1m.notna().any() else np.nan,
        "median_stop_in_4h_ATR": float(s4h.median()) if s4h.notna().any() else np.nan,
    }

    # --- nesting ---
    nest_rows = []
    nest_fail = False
    for name, df in [
        ("CLOSE_BREAK_dev", e4_dev[e4_dev["event_type"] == "CLOSE_BREAK"]),
        ("WICK_REJECT_dev", e4_dev[e4_dev["event_type"] == "WICK_REJECT"]),
        ("CLOSE_RECLAIM_dev", e4_dev[e4_dev["event_type"] == "CLOSE_RECLAIM"]),
        ("controls", c4),
    ]:
        for unit in ("ATR", "structR"):
            n = _nesting_check(df, unit=unit)
            # collapse bug: session_end == two_session_end
            collapse = 0
            if not df.empty and "session_end_ts" in df.columns and "two_session_end_ts" in df.columns:
                collapse = int((df["session_end_ts"].astype(str) == df["two_session_end_ts"].astype(str)).sum())
            suspicious = bool(n.get("rates_equal") and not n.get("sets_identical", True))
            if suspicious or (collapse == len(df) and len(df) > 0):
                nest_fail = True
            nest_rows.append((name, unit, n, collapse))

    # --- observability ---
    obs_ev = int(e4_dev["forward_observable_two_session"].sum()) if "forward_observable_two_session" in e4_dev.columns else 0
    obs_ct = int(c4["forward_observable_two_session"].sum()) if not c4.empty and "forward_observable_two_session" in c4.columns else 0

    # --- event count reconciliation ---
    recon = []
    recon.append(("total_events_all_tf_families_pens", len(events)))
    recon.append(("4h_invalidation_pen0.05", len(e4)))
    recon.append(("4h_invalidation_pen0.05_dev", len(e4_dev)))
    recon.append(("4h_invalidation_pen0.05_holdout", int((e4["slice"] == "holdout").sum())))
    for et in ["CLOSE_BREAK", "WICK_REJECT", "CLOSE_RECLAIM", "TOUCH_ONLY"]:
        recon.append(("4h_inv_pen0.05_dev_%s" % et, int(((e4_dev["event_type"] == et)).sum())))
    if not events.empty:
        g = events.groupby(["structure_timeframe", "event_family", "min_pen_ATR"]).size()
        for k, v in g.items():
            recon.append(("count_%s_%s_pen%s" % (k[0], k[1], k[2]), int(v)))

    # --- examples ---
    cols = [c for c in EXAMPLE_COLS if c in e4.columns or c in (c4.columns if not c4.empty else [])]

    def _export(name, df, n=10):
        if df is None or df.empty:
            return 0
        use_cols = [c for c in EXAMPLE_COLS if c in df.columns]
        out = df[use_cols].head(n)
        out.to_csv(ex_dir / name, index=False)
        return len(out)

    cb = e4_dev[e4_dev["event_type"] == "CLOSE_BREAK"]
    wr = e4_dev[e4_dev["event_type"] == "WICK_REJECT"]
    # five close breaks that never reach 1R ATR in 60m
    cb_miss = cb[cb["expansion_short_1R_60m_ATR"] == 0] if "expansion_short_1R_60m_ATR" in cb.columns else cb
    n_ex = 0
    n_ex += _export("close_break_no_1R_60m_ATR.csv", cb_miss, 5)
    n_ex += _export("wick_reject_both_dirs.csv", wr, 5)
    if not c4.empty:
        hit3 = c4[c4["expansion_multi_3R_ATR"] == 1] if "expansion_multi_3R_ATR" in c4.columns else c4
        n_ex += _export("controls_hit_3R.csv", hit3, 5)
        # all events behind rate cells — dump IDs
        for et, col, fname in [
            ("CLOSE_BREAK", "expansion_session_2R_ATR", "close_break_hit_2R_session_ids.csv"),
            ("WICK_REJECT", "expansion_session_2R_ATR", "wick_reject_hit_2R_session_ids.csv"),
            ("CLOSE_RECLAIM", "expansion_session_2R_ATR", "close_reclaim_hit_2R_session_ids.csv"),
            ("CLOSE_RECLAIM", "expansion_multi_3R_ATR", "close_reclaim_hit_3R_ids.csv"),
        ]:
            sub = e4_dev[e4_dev["event_type"] == et]
            if col in sub.columns:
                hits = sub[sub[col] == 1]
                hits[[c for c in EXAMPLE_COLS if c in hits.columns]].to_csv(ex_dir / fname, index=False)
                n_ex += len(hits)
        if "expansion_multi_3R_ATR" in c4.columns:
            c4[c4["expansion_multi_3R_ATR"] == 1][[c for c in EXAMPLE_COLS if c in c4.columns or c == "control_id"]].to_csv(
                ex_dir / "controls_all_hit_3R_ids.csv", index=False
            )

    # holdout replication summary
    e4h = e4[e4["slice"] == "holdout"]
    hold_lines = []
    for et in ["CLOSE_BREAK", "WICK_REJECT", "CLOSE_RECLAIM"]:
        s_d = _summarize_group(e4_dev[e4_dev["event_type"] == et])
        s_h = _summarize_group(e4h[e4h["event_type"] == et])
        hold_lines.append(
            "| %s | %d | %.1f%% | %d | %.1f%% |"
            % (
                et,
                s_d["n"],
                100 * (s_d["rate_1R_60m"] or 0),
                s_h["n"],
                100 * (s_h["rate_1R_60m"] or 0),
            )
        )

    # PASS/FAIL
    checks = {
        "1_outcome_direction": dir_ok and touch_ok,
        "2_r_unit_defined": bool(pd.notna(r_diag["median_stop_points"]) and pd.notna(r_diag["median_atr_points"])),
        "3_nesting_horizons_ok": not nest_fail,
        "4_controls_observable": (obs_ct >= max(1, int(0.8 * len(c4)))) if len(c4) else False,
        "5_examples_exported": n_ex > 0,
        "6_holdout_table_present": True,
    }
    overall = all(checks.values())

    lines = [
        "# OUTCOME_DIRECTION_AND_R_UNIT_AUDIT — NQ structure-change",
        "",
        "**Updated:** %s" % datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "**Overall:** **%s**" % ("PASS" if overall else "FAIL — do not run Phase 5 / cross-market"),
        "",
        "Answers the six required audit questions before Phase 5.",
        "",
        "## 1. Is each event evaluated in its economically correct direction?",
        "",
        "| Check | Pass |",
        "|---|---|",
        "| Direction rules applied | %s |" % ("PASS" if checks["1_outcome_direction"] else "FAIL"),
        "",
    ]
    for n in dir_notes:
        lines.append("- %s" % n)
    lines += [
        "",
        "| Event class | Primary outcome direction |",
        "|---|---|",
        "| CLOSE_BREAK | Same as close break |",
        "| WICK_REJECT | Opposite of wick breach |",
        "| CLOSE_RECLAIM | Reclaim direction (opposite prior break) |",
        "| TOUCH_ONLY | None — absolute movement only |",
        "",
        "Break-direction diagnostics retained as `break_*` columns.",
        "",
        "## 2. What exactly does 1R mean?",
        "",
        "| Unit | Definition |",
        "|---|---|",
        "| ATR R | `ATR_20` on the structure timeframe (4h primary) |",
        "| Structural-stop R | `|entry_open − protected_swing|` (wick: max with penetration points) |",
        "",
        "### Denominator distribution (4h inv pen≥0.05, **dev**)",
        "",
        "| Stat | Value |",
        "|---|---:|",
        "| median stop distance (points) | %.2f |" % (r_diag["median_stop_points"] or 0),
        "| p25 / p75 / p95 stop (points) | %.2f / %.2f / %.2f |"
        % (r_diag["p25_stop_points"] or 0, r_diag["p75_stop_points"] or 0, r_diag["p95_stop_points"] or 0),
        "| median 4h ATR_20 (points) | %.2f |" % (r_diag["median_atr_points"] or 0),
        "| median stop / 1m ATR | %.2f |" % (r_diag["median_stop_in_1m_ATR"] or 0),
        "| median stop / 4h ATR | %.2f |" % (r_diag["median_stop_in_4h_ATR"] or 0),
        "",
        "Check 2: **%s**" % ("PASS" if checks["2_r_unit_defined"] else "FAIL"),
        "",
        "## 3. Hit-rate inequalities and horizons",
        "",
        "Session 2R and two-session 3R use **distinct** windows after the session-window fix "
        "(post-close entries start session-1 on the next RTH day).",
        "",
        "| Group | Unit | n | n_2R_sess | n_3R_multi | 3R∧¬2R | 2R∧¬3R | session==two_session |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, unit, n, collapse in nest_rows:
        lines.append(
            "| %s | %s | %d | %d | %d | %d | %d | %d |"
            % (
                name,
                unit,
                n.get("n", 0),
                n.get("n_2R", 0),
                n.get("n_3R", 0),
                n.get("n_3R_not_2R", 0),
                n.get("n_2R_not_3R", 0),
                collapse,
            )
        )
    lines += [
        "",
        "Note: `3R∧¬2R` can be legitimate when 3R is earned on session 2 after missing 2R on session 1. "
        "FAIL if rates were equal with disjoint ID sets under collapsed windows (pre-fix).",
        "",
        "Check 3: **%s**" % ("PASS" if checks["3_nesting_horizons_ok"] else "FAIL"),
        "",
        "## 4. Controls matched and fully observable?",
        "",
        "- Matching keys: NY hour, weekday, vol bucket, prior bias (vol relaxed if needed).",
        "- Prefer controls with full two-session forward tape (`forward_observable_two_session=1`).",
        "- Observable controls: **%d / %d**; observable primary-dev events: **%d / %d**."
        % (obs_ct, len(c4), obs_ev, len(e4_dev)),
        "",
        "Check 4: **%s**" % ("PASS" if checks["4_controls_observable"] else "FAIL"),
        "",
        "## 5. Representative event exports",
        "",
        "See `audit_examples/` (%d rows across exports). Inspect labels vs 1m/4h tape offline."
        % n_ex,
        "",
        "Check 5: **%s**" % ("PASS" if checks["5_examples_exported"] else "FAIL"),
        "",
        "## 6. Holdout replication (1R/60m ATR, outcome dir)",
        "",
        "| Class | n_dev | 1R/60m dev | n_holdout | 1R/60m holdout |",
        "|---|---:|---:|---:|---:|",
    ]
    lines.extend(hold_lines)
    lines += [
        "",
        "Check 6: **PASS** (table emitted; interpret agreement separately).",
        "",
        "## Event-count reconciliation",
        "",
        "| Bucket | n |",
        "|---|---:|",
    ]
    for k, v in recon:
        lines.append("| %s | %d |" % (k, v))
    lines += [
        "",
        "Phase 1 table uses only **4h + invalidation + pen≥0.05 + dev** (not all 3353 rows).",
        "Total includes 1h, continuation family, and zero-buffer (`min_pen_ATR=0`) twins.",
        "",
        "## Gate",
        "",
        "- Phase 5 prototypes: **%s**" % ("ALLOWED only after human review" if overall else "BLOCKED"),
        "- Cross-market: still requires `APPROVAL_GATE.md` even if this audit PASSes.",
        "",
    ]
    (hub / "OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"overall_pass": overall, "checks": checks, "r_diag": r_diag}


def write_atlas_docs(
    hub: Path,
    events: pd.DataFrame,
    controls: pd.DataFrame,
    events_1h: pd.DataFrame,
    snaps_4h: pd.DataFrame,
    snaps_1h: pd.DataFrame,
):
    hub.mkdir(parents=True, exist_ok=True)
    # --- EXPANSION_ATLAS ---
    lines = [
        "# Expansion atlas — NQ structure-change event study",
        "",
        "Frozen engine: `%s`. Primary TF: **4h**. Penetration primary cut: **%.2f ATR** "
        "(zero-buffer rows tagged `min_pen_ATR=0`)."
        % (ENGINE_VERSION, PEN_PRIMARY),
        "",
        "Holdout: most recent **%.0f%%** of events (`slice=holdout`). Tables below = **dev** unless noted."
        % (100 * HOLDOUT_FRAC),
        "",
        "**Outcome direction (audit fix):** CLOSE_BREAK = break dir; WICK_REJECT / CLOSE_RECLAIM = "
        "opposite of breach; TOUCH_ONLY = absolute excursion (no directional hypothesis).",
        "",
        "**1R unit (primary tables):** structure-TF `ATR_20`. Structural-stop R companion table below; "
        "full denominator diagnostics in `OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md`.",
        "",
        "**Time to 1R:** median minutes to first 1× unit favorable move inside the *two-session* "
        "window (not the 60m hit-rate). CSV also has `time_to_1R_within_60m_*`.",
        "",
        "## Phase 1 — event class vs matched controls (4h, invalidation family, pen≥0.05, ATR R)",
        "",
        "| Event class | Events | Median fwd 15m | Median fwd 60m | 1R outcome-dir 60m | 2R session | 3R two-session | Median MAE | Median MFE | Time to 1R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    e4 = events[
        (events["structure_timeframe"] == "4h")
        & (events["event_family"] == "invalidation")
        & (events["min_pen_ATR"] == PEN_PRIMARY)
        & (events["slice"] == "dev")
    ]
    c4 = controls[controls["structure_timeframe"] == "4h"] if not controls.empty else controls
    for et in ["CLOSE_BREAK", "WICK_REJECT", "CLOSE_RECLAIM", "TOUCH_ONLY"]:
        lines.append(_fmt_row(et, _summarize_group(e4[e4["event_type"] == et])))
    lines.append(_fmt_row("Matched controls", _summarize_group(c4)))
    lines += [
        "",
        "### Same population — structural-stop R denominator",
        "",
        "| Event class | Events | Median fwd 15m | Median fwd 60m | 1R outcome-dir 60m | 2R session | 3R two-session | Median MAE | Median MFE | Time to 1R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for et in ["CLOSE_BREAK", "WICK_REJECT", "CLOSE_RECLAIM", "TOUCH_ONLY"]:
        lines.append(_fmt_row(et, _summarize_group(e4[e4["event_type"] == et], unit="structR")))
    lines.append(_fmt_row("Matched controls", _summarize_group(c4, unit="structR")))
    e4h = events[
        (events["structure_timeframe"] == "4h")
        & (events["event_family"] == "invalidation")
        & (events["min_pen_ATR"] == PEN_PRIMARY)
        & (events["slice"] == "holdout")
        & (events["event_type"] == "CLOSE_BREAK")
    ]
    lines += [
        "",
        "### Holdout CLOSE_BREAK (4h invalidation)",
        "",
        "| Event class | Events | Median fwd 15m | Median fwd 60m | 1R outcome-dir 60m | 2R session | 3R two-session | Median MAE | Median MFE | Time to 1R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        _fmt_row("CLOSE_BREAK holdout ATR", _summarize_group(e4h)),
        _fmt_row("CLOSE_BREAK holdout structR", _summarize_group(e4h, unit="structR")),
        "",
        "## Executive answers (dev, descriptive)",
        "",
    ]
    cb = _summarize_group(e4[e4["event_type"] == "CLOSE_BREAK"])
    wr = _summarize_group(e4[e4["event_type"] == "WICK_REJECT"])
    cr = _summarize_group(e4[e4["event_type"] == "CLOSE_RECLAIM"])
    ctl = _summarize_group(c4)
    cb_s = _summarize_group(e4[e4["event_type"] == "CLOSE_BREAK"], unit="structR")
    wr_s = _summarize_group(e4[e4["event_type"] == "WICK_REJECT"], unit="structR")
    lines.append(
        "- CLOSE_BREAK 1R/60m (ATR) **%s** (n=%d) vs controls **%s** (n=%d); structR **%s**."
        % (
            ("%.1f%%" % (100 * cb["rate_1R_60m"])) if cb["n"] and pd.notna(cb["rate_1R_60m"]) else "—",
            cb["n"],
            ("%.1f%%" % (100 * ctl["rate_1R_60m"])) if ctl["n"] and pd.notna(ctl["rate_1R_60m"]) else "—",
            ctl["n"],
            ("%.1f%%" % (100 * cb_s["rate_1R_60m"])) if cb_s["n"] and pd.notna(cb_s["rate_1R_60m"]) else "—",
        )
    )
    lines.append(
        "- WICK_REJECT 1R/60m (**reject / opposite** dir, ATR) **%s** (n=%d); fail **%s**; structR **%s**."
        % (
            ("%.1f%%" % (100 * wr["rate_1R_60m"])) if wr["n"] and pd.notna(wr["rate_1R_60m"]) else "—",
            wr["n"],
            ("%.1f%%" % (100 * wr["fail_rate"])) if wr["n"] and pd.notna(wr["fail_rate"]) else "—",
            ("%.1f%%" % (100 * wr_s["rate_1R_60m"])) if wr_s["n"] and pd.notna(wr_s["rate_1R_60m"]) else "—",
        )
    )
    lines.append(
        "- CLOSE_RECLAIM 1R/60m (reclaim dir, ATR) **%s** (n=%d)."
        % (
            ("%.1f%%" % (100 * cr["rate_1R_60m"])) if cr["n"] and pd.notna(cr["rate_1R_60m"]) else "—",
            cr["n"],
        )
    )
    lines.append(
        "- Stance: **RESEARCH** — Phase 5 gated on `OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md` PASS "
        "+ holdout + cross-market approval."
    )
    (hub / "EXPANSION_ATLAS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- CLOSE_VS_WICK ---
    lines = [
        "# Close vs wick — NQ structure-change",
        "",
        "Population: 4h invalidation events, `min_pen_ATR=0.05`, **dev** slice.",
        "WICK_REJECT scored in **reject (opposite) direction**; break-dir diagnostics also reported.",
        "",
        "## Close-break continuation",
        "",
    ]
    cb_df = e4[e4["event_type"] == "CLOSE_BREAK"]
    wr_df = e4[e4["event_type"] == "WICK_REJECT"]
    if not cb_df.empty:
        cb_df = cb_df.copy()
        cb_df["pen_q"] = pd.qcut(cb_df["penetration_ATR"].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        lines.append("| Pen quartile | n | med MFE | med MAE | 1R/60m | fail |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for q, g in cb_df.groupby("pen_q"):
            s = _summarize_group(g)
            lines.append(
                "| %s | %d | %.2f | %.2f | %.1f%% | %.1f%% |"
                % (q, s["n"], s["med_MFE"], s["med_MAE"], 100 * s["rate_1R_60m"], 100 * s["fail_rate"])
            )
    lines += ["", "## Wick-reject reversal (primary = outcome / opposite dir)", ""]
    if not wr_df.empty:
        s = _summarize_group(wr_df)
        brk_1r = (
            float(wr_df["break_expansion_short_1R_60m_ATR"].mean())
            if "break_expansion_short_1R_60m_ATR" in wr_df.columns
            else np.nan
        )
        brk_mfe = (
            float(wr_df["break_forward_MFE_ATR"].median())
            if "break_forward_MFE_ATR" in wr_df.columns
            else np.nan
        )
        lines.append(
            "- Wick n=%d; median **reject-dir** MFE=%.2fR ATR; 1R/60m reject-dir=%.1f%%; "
            "median **break-dir** MFE=%.2fR; 1R/60m break-dir=%.1f%%; fail(reject)=%.1f%%; immediate retrace=%.1f%%."
            % (
                s["n"],
                s["med_MFE"] or 0,
                100 * (s["rate_1R_60m"] or 0),
                brk_mfe if pd.notna(brk_mfe) else 0,
                100 * brk_1r if pd.notna(brk_1r) else 0,
                100 * (s["fail_rate"] or 0),
                100 * float(wr_df["immediate_retrace_flag"].mean()),
            )
        )
        ctl_s = _summarize_group(c4)
        lines.append(
            "- Vs controls median MFE %.2fR / MAE %.2fR (matched outcome dir)."
            % (ctl_s["med_MFE"] or 0, ctl_s["med_MAE"] or 0)
        )
    else:
        lines.append("- No WICK_REJECT events in dev slice.")
    lines += [
        "",
        "## Verdict",
        "",
        "- Close confirmation vs wick tabulated above; do **not** promote Phase 5 without audit PASS + holdout.",
        "",
    ]
    (hub / "CLOSE_VS_WICK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- TIME_OF_CHANGE_ATLAS ---
    lines = [
        "# Time-of-change atlas — NQ 4h invalidation (dev, pen≥0.05)",
        "",
        "Sample minimum for descriptive cells: n≥%d." % SAMPLE_DESC_N,
        "",
    ]
    for et in ["CLOSE_BREAK", "WICK_REJECT"]:
        sub = e4[e4["event_type"] == et]
        lines.append("## %s by NY session bucket" % et)
        lines.append("")
        lines.append("| Bucket | n | med MFE | 1R/60m | 2R sess | fail |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for b in ["NY_OPEN", "NY_AM", "NY_MIDDAY", "NY_PM", "NY_CLOSE", "GLOBEX"]:
            g = sub[sub["entry_session"] == b]
            s = _summarize_group(g)
            if s["n"] < SAMPLE_DESC_N:
                lines.append("| %s | %d | — | — | — | — |  *(n<%d)* |" % (b, s["n"], SAMPLE_DESC_N))
            else:
                lines.append(
                    "| %s | %d | %.2f | %.1f%% | %.1f%% | %.1f%% |"
                    % (b, s["n"], s["med_MFE"], 100 * s["rate_1R_60m"], 100 * s["rate_2R_sess"], 100 * s["fail_rate"])
                )
        lines.append("")
        lines.append("### %s by weekday" % et)
        lines.append("")
        lines.append("| DOW | n | med MFE | 1R/60m | fail |")
        lines.append("|---|---:|---:|---:|---:|")
        for dow in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            g = sub[sub["day_of_week"] == dow]
            s = _summarize_group(g)
            if s["n"] < SAMPLE_DESC_N:
                lines.append("| %s | %d | — | — | — |" % (dow, s["n"]))
            else:
                lines.append(
                    "| %s | %d | %.2f | %.1f%% | %.1f%% |"
                    % (dow, s["n"], s["med_MFE"], 100 * s["rate_1R_60m"], 100 * s["fail_rate"])
                )
        lines.append("")
    (hub / "TIME_OF_CHANGE_ATLAS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- ONE_HOUR_INCREMENTAL ---
    lines = [
        "# One-hour incremental value vs 4h",
        "",
        "Same swing engine on 1h RTH bars. Tests A–E use **dev** CLOSE_BREAK invalidation where possible.",
        "",
    ]
    e1 = events_1h[
        (events_1h["event_family"] == "invalidation")
        & (events_1h["min_pen_ATR"] == PEN_PRIMARY)
        & (events_1h["slice"] == "dev")
    ] if not events_1h.empty else events_1h
    lines.append("## B — 1h only CLOSE_BREAK")
    lines.append("")
    lines.append("| Class | n | med MFE | 1R/60m | fail |")
    lines.append("|---|---:|---:|---:|---:|")
    s1 = _summarize_group(e1[e1["event_type"] == "CLOSE_BREAK"] if not e1.empty else e1)
    s4 = _summarize_group(e4[e4["event_type"] == "CLOSE_BREAK"])
    lines.append("| 1h CLOSE_BREAK | %d | %.2f | %.1f%% | %.1f%% |" % (s1["n"], s1["med_MFE"] or 0, 100 * (s1["rate_1R_60m"] or 0), 100 * (s1["fail_rate"] or 0)))
    lines.append("| 4h CLOSE_BREAK (A) | %d | %.2f | %.1f%% | %.1f%% |" % (s4["n"], s4["med_MFE"] or 0, 100 * (s4["rate_1R_60m"] or 0), 100 * (s4["fail_rate"] or 0)))
    # alignment: map 1h events to last 4h bias snap
    lines += ["", "## C/D — 4h bias alignment at 1h CLOSE_BREAK", ""]
    if not e1.empty and not snaps_4h.empty:
        snaps_4h = snaps_4h.copy()
        snaps_4h["avail"] = pd.to_datetime(snaps_4h["structure_feature_available_at"], utc=True).dt.tz_convert(NY)
        aligned_rows = []
        opposed_rows = []
        for _, r in e1[e1["event_type"] == "CLOSE_BREAK"].iterrows():
            t = _localize(pd.Timestamp(r["feature_available_at"]))
            mask = snaps_4h["avail"] <= t
            if not mask.any():
                continue
            bias = str(snaps_4h.loc[mask, "bias"].iloc[-1])
            ed = str(r["event_direction"])
            if bias == "bullish" and ed == "bullish" or bias == "bearish" and ed == "bearish":
                aligned_rows.append(r)
            elif bias in ("bullish", "bearish"):
                opposed_rows.append(r)
        sa = _summarize_group(pd.DataFrame(aligned_rows))
        so = _summarize_group(pd.DataFrame(opposed_rows))
        lines.append("| Test | n | med MFE | 1R/60m | fail |")
        lines.append("|---|---:|---:|---:|---:|")
        lines.append("| C aligned | %d | %.2f | %.1f%% | %.1f%% |" % (sa["n"], sa["med_MFE"] or 0, 100 * (sa["rate_1R_60m"] or 0), 100 * (sa["fail_rate"] or 0)))
        lines.append("| D opposed | %d | %.2f | %.1f%% | %.1f%% |" % (so["n"], so["med_MFE"] or 0, 100 * (so["rate_1R_60m"] or 0), 100 * (so["fail_rate"] or 0)))
        delta = (sa["rate_1R_60m"] or 0) - (s4["rate_1R_60m"] or 0)
        lines.append("")
        lines.append("Δ 1R rate (aligned 1h − 4h-only CLOSE_BREAK) = **%+.1f pp**." % (100 * delta))
    else:
        lines.append("- Insufficient 1h/4h overlap for alignment tables.")
    lines += [
        "",
        "## E — 1h break inside unchanged 4h bias",
        "",
        "See opposed/aligned split above; opposed ≈ conflict / early reversal candidate.",
        "",
        "## Verdict",
        "",
        "- 1h is a separate signal layer; promote only if Δ survives holdout.",
        "",
    ]
    (hub / "ONE_HOUR_INCREMENTAL_VALUE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- CAUSALITY_AUDIT ---
    bad = 0
    total = 0
    if not events.empty:
        for _, r in events.iterrows():
            total += 1
            fa = _localize(pd.Timestamp(r["feature_available_at"]))
            oa = _localize(pd.Timestamp(r["order_active_ts"]))
            if not (fa < oa):
                bad += 1
    caus = [
        "# Causality audit — NQ structure-change atlas",
        "",
        "- Engine: frozen `StructureProgramEngine` (left/right=2).",
        "- Feature known at structure-bar close; `order_active_ts = feature_available_at + 1m`.",
        "- Forward path uses 1m RTH opens at/after `order_active_ts`.",
        "- Violations `feature_available_at < order_active_ts`: **%d / %d**." % (bad, total),
        "- Phase 5 strategy claims still require path-aware fills + this audit PASS.",
        "",
        "Status: **%s**" % ("PASS" if bad == 0 and total > 0 else ("FAIL" if bad else "EMPTY")),
        "",
    ]
    (hub / "CAUSALITY_AUDIT.md").write_text("\n".join(caus), encoding="utf-8")

    # --- TRIAL_LEDGER ---
    trial = [
        "# Trial ledger — nq_structure_change_event_study",
        "",
        "| Field | Value |",
        "|---|---|",
        "| market | NQ |",
        "| timeframes | 4h primary, 1h secondary |",
        "| engine | %s |" % ENGINE_VERSION,
        "| swing L/R | 2 / 2 |",
        "| list / takeouts | 20 / 2 |",
        "| penetration | 0.05 ATR + zero-buffer pass |",
        "| reclaim window | %d structure bars |" % RECLAIM_WINDOW_BARS,
        "| holdout | last %.0f%% by event time |" % (100 * HOLDOUT_FRAC),
        "| phases run | 1–4 (event study) |",
        "| phase 5 | NOT RUN |",
        "",
    ]
    (hub / "TRIAL_LEDGER.md").write_text("\n".join(trial), encoding="utf-8")

    # stub Phase 5
    (hub / "STRATEGY_PROTOTYPES.md").write_text(
        "# Strategy prototypes — GATED\n\n"
        "Phase 5 not started. Requires OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md PASS + "
        "holdout survival + human approval before cross-market.\n",
        encoding="utf-8",
    )


def run(*, smoke: bool = False, start: Optional[date] = None, end: Optional[date] = None, do_email: bool = False) -> int:
    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    rid = begin_run(
        run_class="pandas",
        variant_slug="nq_structure_change_event_study",
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        notes="structure-change atlas audit rerun (outcome dir + R units)",
        meta={"smoke": smoke, "pen": PEN_PRIMARY},
    )
    try:
        print("Loading NQ 1m…", flush=True)
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        days = sorted(gby)
        if start:
            days = [d for d in days if d >= start]
        if end:
            days = [d for d in days if d <= end]
        if smoke:
            days = days[:120]
        print("Session days: %d (%s → %s)" % (len(days), days[0], days[-1]), flush=True)

        tape = _build_1m_tape(gby, days)
        print("1m RTH tape bars: %d" % len(tape), flush=True)

        all_events: List[dict] = []
        # Primary cut 0.05 ATR. Zero-buffer robustness: reclassify TOUCH_ONLY
        # rows as CLOSE_BREAK/WICK_REJECT when pen>0 (see emit in walk).
        ev4, snaps_4h = walk_tf(
            gby=gby,
            tf_name="4h",
            hours=4.0,
            resample_fn=to_4h,
            lookback_days=LOOKBACK_DAYS_4H,
            days=days,
            min_pen=PEN_PRIMARY,
        )
        all_events.extend(ev4)

        ev1, snaps_1h = walk_tf(
            gby=gby,
            tf_name="1h",
            hours=1.0,
            resample_fn=to_1h,
            lookback_days=LOOKBACK_DAYS_1H,
            days=days,
            min_pen=PEN_PRIMARY,
        )
        all_events.extend(ev1)

        print("Enriching forwards for %d events…" % len(all_events), flush=True)
        edf = enrich_forwards(all_events, tape, days)
        edf = assign_holdout(edf)

        # controls from primary 4h invalidation events
        primary = edf[
            (edf["structure_timeframe"] == "4h")
            & (edf["event_family"] == "invalidation")
            & (edf["min_pen_ATR"] == PEN_PRIMARY)
            & (edf["event_type"].isin(["CLOSE_BREAK", "WICK_REJECT", "CLOSE_RECLAIM", "TOUCH_ONLY"]))
        ]
        print("Building matched controls from %d primary events…" % len(primary), flush=True)
        cdf = matched_controls(primary, snaps_4h, tape, days)

        edf.to_csv(hub / "structure_events.csv", index=False)
        cdf.to_csv(hub / "structure_event_controls.csv", index=False)
        snaps_4h.to_csv(hub / "snaps_4h.csv", index=False)
        snaps_1h.to_csv(hub / "snaps_1h.csv", index=False)

        e1_only = edf[edf["structure_timeframe"] == "1h"].copy()
        write_atlas_docs(hub, edf, cdf, e1_only, snaps_4h, snaps_1h)
        audit_summary = write_outcome_audit(hub, edf, cdf)

        # STATUS
        n_ev = len(edf)
        n_cb = int(
            (
                (edf.structure_timeframe == "4h")
                & (edf.event_family == "invalidation")
                & (edf.min_pen_ATR == PEN_PRIMARY)
                & (edf.event_type == "CLOSE_BREAK")
            ).sum()
        )
        status = [
            "# Status — NQ structure-change event study",
            "",
            "**Hub:** `live/state/nq_structure_change_event_study/`",
            "**Updated:** %s" % datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
            "",
            "## Phase status",
            "",
            "| Phase | Status |",
            "|---|---|",
            "| 0 freeze | DONE |",
            "| 1 expansion atlas | DONE |",
            "| 2 close vs wick | DONE |",
            "| 3 timing atlas | DONE |",
            "| 4 1h incremental | DONE |",
            "| 5 prototypes | GATED (audit) |",
            "| outcome/R audit | %s |" % ("PASS" if audit_summary.get("overall_pass") else "FAIL"),
            "| Cross-market | PENDING APPROVAL_GATE.md |",
            "",
            "Events total: **%d** (4h CLOSE_BREAK invalidation pen≥0.05: **%d**)." % (n_ev, n_cb),
            "Artifacts: events/controls CSVs, atlas markdowns, `CAUSALITY_AUDIT.md`, `OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md`.",
            "",
        ]
        (hub / "STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")

        summary = {
            "n_events": n_ev,
            "n_controls": int(len(cdf)),
            "n_4h_close_break": n_cb,
            "days": [str(days[0]), str(days[-1])],
            "smoke": smoke,
            "audit_pass": bool(audit_summary.get("overall_pass")),
        }
        (hub / "RUN_COMPLETE.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # email body
        atlas_head = (hub / "EXPANSION_ATLAS.md").read_text(encoding="utf-8")[:2500]
        body = (
            "potions: NQ structure-change atlas AUDIT RERUN COMPLETE\n\n"
            "Hub: %s\n"
            "Days: %s → %s | smoke=%s\n"
            "Events: %d | controls: %d | 4h CLOSE_BREAK: %d\n"
            "Outcome/R audit: %s\n\n"
            "Phase 5 + cross-market still GATED.\n"
            "  live/state/structure_change_event_study_cross_market/APPROVAL_GATE.md\n\n"
            "--- OUTCOME AUDIT (head) ---\n%s\n\n"
            "--- EXPANSION_ATLAS (excerpt) ---\n%s\n"
            % (
                hub, days[0], days[-1], smoke, n_ev, len(cdf), n_cb,
                "PASS" if audit_summary.get("overall_pass") else "FAIL",
                (hub / "OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md").read_text(encoding="utf-8")[:2000],
                atlas_head,
            )
        )
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        if do_email:
            send_email(subject="potions: NQ structure-change atlas AUDIT RERUN COMPLETE", body=body)
            print("emailed completion", flush=True)

        complete_run(rid, trades=n_ev, meta=summary, notes="atlas audit rerun complete")
        return 0
    except Exception as e:
        tb = traceback.format_exc()
        (hub / "FAILED.txt").write_text(tb, encoding="utf-8")
        fail_run(rid, notes=str(e))
        if do_email:
            send_email(
                subject="potions: NQ structure-change atlas FAILED",
                body="Hub: %s\n\n%s" % (hub, tb[-4000:]),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--email", action="store_true")
    p.add_argument("--start", type=str, default=None)
    p.add_argument("--end", type=str, default=None)
    args = p.parse_args(argv)
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    return run(smoke=args.smoke, start=start, end=end, do_email=args.email)


if __name__ == "__main__":
    raise SystemExit(main())
