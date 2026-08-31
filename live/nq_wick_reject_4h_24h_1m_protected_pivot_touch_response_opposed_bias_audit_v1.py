"""Opposed-bias mirror audit for protected-pivot touch-response V1.

Re-labels parent favorable/adverse excursions opposite the original four-pivot
structural bias. Frozen parent events/windows only — not a reverse-trade study.

Hub: live/state/nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_opposed_bias_audit_v1/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_opposed_bias_audit_v1 --email
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_opposed_bias_audit_v1 --email --skip-charts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import TICK
from .nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1 import (
    DATA_SESSION_POLICY,
    DATA_VERSION,
    _excursion_stats,
    _fmt,
    build_globex_1m,
)
from .nq_wick_reject_range_seed_retest import _localize, build_rth_tape
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
SRC_HUB = REPO / "live" / "state" / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
HUB = (
    REPO
    / "live"
    / "state"
    / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_opposed_bias_audit_v1"
)
STUDY_ID = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_opposed_bias_audit_v1"
PARENT_STUDY = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
PARENT_CONFIG_HASH_EXPECTED = "402795e0a05e2fbc"
SWAP_TOL = 1e-6
RR_RECIP_TOL = 1e-4
SMOKE_CHART_CAP = 5


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _side(pattern: Any) -> str:
    p = str(pattern or "")
    if p.startswith("BEAR"):
        return "BEAR"
    if p.startswith("BULL"):
        return "BULL"
    return ""


def _bias_dirs(side: str) -> Tuple[str, str]:
    if side == "BEAR":
        return "DOWN", "UP"
    if side == "BULL":
        return "UP", "DOWN"
    return "", ""


def _fav_word(direction: str) -> str:
    d = (direction or "").upper()
    if d == "DOWN":
        return "bearish"
    if d == "UP":
        return "bullish"
    return ""


def _finite(x: Any) -> bool:
    try:
        return bool(np.isfinite(float(x)))
    except (TypeError, ValueError):
        return False


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _near(a: Any, b: Any, tol: float = SWAP_TOL) -> bool:
    if not (_finite(a) and _finite(b)):
        return (not _finite(a)) and (not _finite(b))
    return abs(float(a) - float(b)) <= tol


def _has_ts(x: Any) -> bool:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return False
    try:
        if pd.isna(x):
            return False
    except Exception:
        pass
    s = str(x).strip().lower()
    return bool(s) and s not in ("nan", "nat", "none", "")


def _ts_eq(a: Any, b: Any) -> bool:
    ha, hb = _has_ts(a), _has_ts(b)
    if not ha and not hb:
        return True
    if not ha or not hb:
        return False
    try:
        return pd.Timestamp(a) == pd.Timestamp(b)
    except Exception:
        return str(a).strip() == str(b).strip()


def _excursion_from_window(
    ref: float,
    highest: float,
    lowest: float,
    favorable_dir: str,
) -> Tuple[float, float, bool, float]:
    fav = _fav_word(favorable_dir)
    if fav not in ("bullish", "bearish") or not _finite(ref):
        return float("nan"), float("nan"), False, float("nan")
    if not (_finite(highest) and _finite(lowest)):
        return float("nan"), float("nan"), False, float("nan")
    if fav == "bearish":
        mfe = (ref - lowest) / TICK
        mae = (highest - ref) / TICK
    else:
        mfe = (highest - ref) / TICK
        mae = (ref - lowest) / TICK
    mfe = max(0.0, float(mfe))
    mae = max(0.0, float(mae))
    zero = mae <= 1e-12
    rr = (mfe / mae) if mae > 1e-12 else float("nan")
    return round(mfe, 4), round(mae, 4), zero, (round(rr, 6) if rr == rr else float("nan"))


def _load_parent() -> Tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    parent_hash = (SRC_HUB / "config_hash.txt").read_text(encoding="utf-8").strip()
    elig = pd.read_csv(SRC_HUB / "seed_24h_eligibility.csv")
    cands = pd.read_csv(SRC_HUB / "structure_candidates.csv")
    structs = pd.read_csv(SRC_HUB / "structure_excursion_outcomes.csv")
    contacts = pd.read_csv(SRC_HUB / "contact_reaction_outcomes.csv")
    exclusions = pd.read_csv(SRC_HUB / "pack_e_exclusions.csv")
    return parent_hash, elig, cands, structs, contacts, exclusions


def build_tables(
    parent_hash: str,
    elig: pd.DataFrame,
    cands_all: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    cands = cands_all[cands_all["candidate_status"] == "COMPLETED"].copy()
    struct_by = {r["candidate_id"]: r for _, r in structs.iterrows()}
    contact_by = {r["candidate_id"]: r for _, r in contacts.iterrows()}

    recon_rows: List[Dict[str, Any]] = []
    struct_rows: List[Dict[str, Any]] = []
    contact_rows: List[Dict[str, Any]] = []
    hash_ok = parent_hash == PARENT_CONFIG_HASH_EXPECTED

    for _, cand in cands.iterrows():
        cid = cand["candidate_id"]
        side = _side(cand.get("pattern"))
        orig_dir, opp_dir = _bias_dirs(side)
        s = struct_by.get(cid)
        c = contact_by.get(cid)
        parent_exists = s is not None and c is not None
        fails: List[str] = []
        if not hash_ok:
            fails.append("parent_config_hash_mismatch")
        if not parent_exists:
            fails.append("missing_parent_structure_or_contact_row")

        s_ref = _f(s["structure_reference_price"]) if s is not None else float("nan")
        c_ref = _f(c["contact_reference_price"]) if c is not None else float("nan")
        cand_s_ref = _f(cand.get("structure_reference_price"))
        cand_c_ref = _f(cand.get("protected_pivot_price"))
        aw = cand.get("area_width_ticks")
        aw_c = c.get("area_width_ticks") if c is not None else None

        candidate_match = parent_exists
        timestamp_match = False
        reference_match = False
        area_match = False
        horizon_match = False

        if parent_exists:
            timestamp_match = _ts_eq(cand.get("structure_complete_at"), s.get("evaluation_start"))
            # Only reconcile first-contact when parent recorded a contact.
            if _has_ts(c.get("first_contact_ts")) or _has_ts(s.get("first_contact_ts")):
                timestamp_match = timestamp_match and _ts_eq(
                    s.get("first_contact_ts"), c.get("first_contact_ts")
                )
            if not timestamp_match:
                fails.append("timestamp_mismatch")

            reference_match = _near(s_ref, cand_s_ref, 1e-6) and _near(c_ref, cand_c_ref, 1e-6)
            if not reference_match:
                fails.append("reference_mismatch")

            area_match = True
            if aw_c is not None and pd.notna(aw) and pd.notna(aw_c):
                area_match = int(float(aw)) == int(float(aw_c))
            if not area_match:
                fails.append("area_mismatch")

            horizon_match = _has_ts(s.get("structure_horizon_end"))
            if bool(c.get("contact_eligible")):
                horizon_match = horizon_match and _has_ts(c.get("reaction_horizon_end"))
            if not horizon_match:
                fails.append("horizon_mismatch")

        overall = (
            hash_ok
            and candidate_match
            and timestamp_match
            and reference_match
            and area_match
            and horizon_match
        )
        recon_rows.append(
            {
                "candidate_id": cid,
                "parent_config_hash": parent_hash,
                "parent_pattern": cand.get("pattern"),
                "parent_candidate_exists": parent_exists,
                "parent_structure_complete_at": cand.get("structure_complete_at"),
                "parent_first_contact_ts": (s.get("first_contact_ts") if s is not None else ""),
                "parent_structure_reference_price": s_ref,
                "parent_contact_reference_price": c_ref,
                "parent_area_width_ticks": aw,
                "parent_structure_horizon_end": (
                    s.get("structure_horizon_end") if s is not None else ""
                ),
                "parent_reaction_horizon_end": (
                    c.get("reaction_horizon_end") if c is not None else ""
                ),
                "candidate_match_pass": candidate_match,
                "timestamp_match_pass": timestamp_match,
                "reference_match_pass": reference_match,
                "area_match_pass": area_match,
                "horizon_match_pass": horizon_match,
                "overall_reconciliation_pass": overall,
                "failure_reason": ";".join(fails),
            }
        )

        if s is None:
            continue

        s_hi = _f(s.get("highest_high_in_window"))
        s_lo = _f(s.get("lowest_low_in_window"))
        orig_mfe = _f(s.get("mfe_structure_ticks"))
        orig_mae = _f(s.get("mae_structure_ticks"))
        orig_rr = _f(s.get("structure_excursion_rr"))
        chk_mfe, chk_mae, _, _ = _excursion_from_window(s_ref, s_hi, s_lo, orig_dir)
        opp_mfe, opp_mae, opp_zero, opp_rr = _excursion_from_window(s_ref, s_hi, s_lo, opp_dir)
        data_ok = bool(s.get("data_complete"))

        swap_pass = False
        recip_pass = False
        if data_ok and _finite(orig_mfe) and _finite(orig_mae):
            swap_pass = (_near(orig_mfe, opp_mae) and _near(orig_mae, opp_mfe)) or (
                _near(chk_mfe, opp_mae) and _near(chk_mae, opp_mfe)
            )
            if _finite(orig_rr) and _finite(opp_rr) and orig_mae > 1e-12 and opp_mae > 1e-12:
                recip_pass = abs(float(opp_rr) * float(orig_rr) - 1.0) <= RR_RECIP_TOL
            elif orig_mae <= 1e-12 or opp_mae <= 1e-12:
                recip_pass = True
            else:
                recip_pass = swap_pass

        struct_rows.append(
            {
                "candidate_id": cid,
                "parent_pattern": cand.get("pattern"),
                "original_bias_direction": orig_dir,
                "opposed_bias_direction": opp_dir,
                "structure_reference_price": s_ref,
                "evaluation_start": s.get("evaluation_start"),
                "structure_horizon_end": s.get("structure_horizon_end"),
                "highest_high_in_window": s_hi,
                "lowest_low_in_window": s_lo,
                "original_mfe_ticks": orig_mfe,
                "original_mae_ticks": orig_mae,
                "original_rr": orig_rr,
                "opposed_mfe_ticks": opp_mfe,
                "opposed_mae_ticks": opp_mae,
                "opposed_rr": opp_rr,
                "zero_mae_original_flag": bool(s.get("zero_mae_flag")),
                "zero_mae_opposed_flag": opp_zero,
                "mfe_mae_swap_pass": swap_pass if data_ok else False,
                "rr_reciprocal_pass": recip_pass if data_ok else False,
                "data_complete": data_ok,
                "gap_or_exclusion_reason": s.get("gap_or_exclusion_reason", ""),
            }
        )

        if c is None:
            continue

        c_hi = _f(c.get("highest_high_in_reaction_window"))
        c_lo = _f(c.get("lowest_low_in_reaction_window"))
        corig_mfe = _f(c.get("mfe_contact_ticks"))
        corig_mae = _f(c.get("mae_contact_ticks"))
        corig_rr = _f(c.get("contact_excursion_rr"))
        contact_ok = bool(c.get("contact_eligible")) and bool(c.get("data_complete"))
        cchk_mfe, cchk_mae, _, _ = _excursion_from_window(c_ref, c_hi, c_lo, orig_dir)
        copp_mfe, copp_mae, copp_zero, copp_rr = _excursion_from_window(c_ref, c_hi, c_lo, opp_dir)

        c_swap = False
        c_recip = False
        if contact_ok and _finite(corig_mfe) and _finite(corig_mae):
            c_swap = (_near(corig_mfe, copp_mae) and _near(corig_mae, copp_mfe)) or (
                _near(cchk_mfe, copp_mae) and _near(cchk_mae, copp_mfe)
            )
            if _finite(corig_rr) and _finite(copp_rr) and corig_mae > 1e-12 and copp_mae > 1e-12:
                c_recip = abs(float(copp_rr) * float(corig_rr) - 1.0) <= RR_RECIP_TOL
            elif corig_mae <= 1e-12 or copp_mae <= 1e-12:
                c_recip = True
            else:
                c_recip = c_swap

        contact_rows.append(
            {
                "candidate_id": cid,
                "parent_pattern": cand.get("pattern"),
                "original_bias_direction": orig_dir,
                "opposed_bias_direction": opp_dir,
                "contact_reference_price": c_ref,
                "first_contact_ts": c.get("first_contact_ts", ""),
                "reaction_horizon_end": c.get("reaction_horizon_end", ""),
                "highest_high_in_window": c_hi,
                "lowest_low_in_window": c_lo,
                "original_mfe_ticks": corig_mfe,
                "original_mae_ticks": corig_mae,
                "original_rr": corig_rr,
                "opposed_mfe_ticks": copp_mfe,
                "opposed_mae_ticks": copp_mae,
                "opposed_rr": copp_rr,
                "zero_mae_original_flag": bool(c.get("zero_mae_flag")),
                "zero_mae_opposed_flag": copp_zero,
                "mfe_mae_swap_pass": c_swap if contact_ok else False,
                "rr_reciprocal_pass": c_recip if contact_ok else False,
                "parent_contact_classification": c.get("area_contact_classification", ""),
                "parent_path_order_label": c.get("path_order_label", ""),
                "data_complete": contact_ok,
                "gap_or_exclusion_reason": c.get("gap_or_exclusion_reason", "")
                or c.get("no_contact_reason", ""),
            }
        )

    recon = pd.DataFrame(recon_rows)
    s_out = pd.DataFrame(struct_rows)
    c_out = pd.DataFrame(contact_rows)
    n_elig = int((elig["included"] == True).sum())  # noqa: E712
    meta = {
        "parent_config_hash": parent_hash,
        "eligible_seeds": n_elig,
        "candidates": int(len(cands)),
        "bear_candidates": int(cands["pattern"].astype(str).str.startswith("BEAR").sum()),
        "bull_candidates": int(cands["pattern"].astype(str).str.startswith("BULL").sum()),
        "recon_pass_all": bool(len(recon) and recon["overall_reconciliation_pass"].all()),
        "recon_fail_n": int((~recon["overall_reconciliation_pass"]).sum()) if len(recon) else 0,
    }
    return recon, s_out, c_out, meta


def _pop_stats(label: str, df: pd.DataFrame, evaluable: pd.Series) -> Dict[str, Any]:
    full_n = int(len(df))
    incomplete = int((~evaluable).sum()) if full_n else 0
    sub = df.loc[evaluable].copy() if full_n else df.iloc[0:0].copy()
    empty = {
        "population_label": label,
        "record_count": 0,
        "incomplete_count": incomplete,
        "zero_mae_count": 0,
        "mean_original_mfe_ticks": float("nan"),
        "mean_original_mae_ticks": float("nan"),
        "mean_original_rr": float("nan"),
        "mean_opposed_mfe_ticks": float("nan"),
        "mean_opposed_mae_ticks": float("nan"),
        "mean_opposed_rr": float("nan"),
        "median_original_mfe_ticks": float("nan"),
        "median_original_mae_ticks": float("nan"),
        "median_original_rr": float("nan"),
        "median_opposed_mfe_ticks": float("nan"),
        "median_opposed_mae_ticks": float("nan"),
        "median_opposed_rr": float("nan"),
        "top_1_original_mfe_contribution_pct": float("nan"),
        "top_3_original_mfe_contribution_pct": float("nan"),
        "top_1_opposed_mfe_contribution_pct": float("nan"),
        "top_3_opposed_mfe_contribution_pct": float("nan"),
        # Empty slices are not identity failures — they simply have no evaluable rows.
        "identity_summary_pass": True,
        "interpretation_status": "INSUFFICIENT_SAMPLE",
    }
    if not len(sub):
        return empty

    orig = _excursion_stats(
        sub["original_mfe_ticks"],
        sub["original_mae_ticks"],
        sub["original_rr"],
        sub["zero_mae_original_flag"],
    )
    opp = _excursion_stats(
        sub["opposed_mfe_ticks"],
        sub["opposed_mae_ticks"],
        sub["opposed_rr"],
        sub["zero_mae_opposed_flag"],
    )
    id_ok = (
        _near(orig["mean_mfe_ticks"], opp["mean_mae_ticks"], 1e-6)
        and _near(orig["mean_mae_ticks"], opp["mean_mfe_ticks"], 1e-6)
        and bool(sub["mfe_mae_swap_pass"].all())
    )
    m_o = orig["mean_excursion_rr"]
    m_p = opp["mean_excursion_rr"]
    if _finite(m_o) and _finite(m_p) and float(m_o) > 0 and float(m_p) > 0:
        id_ok = id_ok and abs(float(m_o) * float(m_p) - 1.0) <= max(RR_RECIP_TOL, 1e-6)

    return {
        "population_label": label,
        "record_count": int(orig["record_count"]),
        "incomplete_count": incomplete,
        "zero_mae_count": int(orig["zero_mae_count"]),
        "mean_original_mfe_ticks": orig["mean_mfe_ticks"],
        "mean_original_mae_ticks": orig["mean_mae_ticks"],
        "mean_original_rr": orig["mean_excursion_rr"],
        "mean_opposed_mfe_ticks": opp["mean_mfe_ticks"],
        "mean_opposed_mae_ticks": opp["mean_mae_ticks"],
        "mean_opposed_rr": opp["mean_excursion_rr"],
        "median_original_mfe_ticks": orig["median_mfe_ticks"],
        "median_original_mae_ticks": orig["median_mae_ticks"],
        "median_original_rr": orig["median_excursion_rr"],
        "median_opposed_mfe_ticks": opp["median_mfe_ticks"],
        "median_opposed_mae_ticks": opp["median_mae_ticks"],
        "median_opposed_rr": opp["median_excursion_rr"],
        "top_1_original_mfe_contribution_pct": orig["top_1_mfe_contribution_pct"],
        "top_3_original_mfe_contribution_pct": orig["top_3_mfe_contribution_pct"],
        "top_1_opposed_mfe_contribution_pct": opp["top_1_mfe_contribution_pct"],
        "top_3_opposed_mfe_contribution_pct": opp["top_3_mfe_contribution_pct"],
        "identity_summary_pass": bool(id_ok),
        "interpretation_status": "MATHEMATICAL_MIRROR_ONLY",
    }


def build_aggregates(s_out: pd.DataFrame, c_out: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if len(s_out):
        s_ok = s_out["data_complete"].fillna(False).astype(bool)
        bear = s_out["parent_pattern"].astype(str).str.startswith("BEAR")
        bull = s_out["parent_pattern"].astype(str).str.startswith("BULL")
        rows.append(_pop_stats("BEAR_STRUCTURE", s_out[bear], s_ok[bear]))
        rows.append(_pop_stats("BULL_STRUCTURE", s_out[bull], s_ok[bull]))
        rows.append(_pop_stats("ALL_STRUCTURE", s_out, s_ok))
    if len(c_out):
        c_ok = c_out["data_complete"].fillna(False).astype(bool)
        bear = c_out["parent_pattern"].astype(str).str.startswith("BEAR")
        bull = c_out["parent_pattern"].astype(str).str.startswith("BULL")
        rows.append(_pop_stats("BEAR_CONTACT", c_out[bear], c_ok[bear]))
        rows.append(_pop_stats("BULL_CONTACT", c_out[bull], c_ok[bull]))
        rows.append(_pop_stats("ALL_CONTACT", c_out, c_ok))
        for depth in sorted(
            {str(x) for x in c_out["parent_contact_classification"].dropna().unique()}
        ):
            if not depth or depth == "nan":
                continue
            mask = c_out["parent_contact_classification"].astype(str) == depth
            if mask.any():
                rows.append(_pop_stats("CONTACT_%s" % depth, c_out[mask], c_ok[mask]))
    return pd.DataFrame(rows)


def _row(agg: pd.DataFrame, label: str) -> Dict[str, Any]:
    if agg is None or not len(agg):
        return {}
    hit = agg[agg["population_label"] == label]
    if hit.empty:
        return {}
    return hit.iloc[0].to_dict()


def _recip_label(row: Dict[str, Any]) -> str:
    if not row:
        return "FAIL"
    o = row.get("mean_original_rr")
    p = row.get("mean_opposed_rr")
    if _finite(o) and _finite(p) and float(o) > 0 and abs(float(o) * float(p) - 1.0) <= 1e-3:
        return "PASS"
    return "FAIL"


def write_reports(
    hub: Path,
    meta: Dict[str, Any],
    recon: pd.DataFrame,
    s_out: pd.DataFrame,
    c_out: pd.DataFrame,
    agg: pd.DataFrame,
) -> Dict[str, Any]:
    bear_s = _row(agg, "BEAR_STRUCTURE")
    bull_s = _row(agg, "BULL_STRUCTURE")
    bear_c = _row(agg, "BEAR_CONTACT")
    bull_c = _row(agg, "BULL_CONTACT")

    s_eval = s_out[s_out["data_complete"] == True] if len(s_out) else s_out  # noqa: E712
    c_eval = c_out[c_out["data_complete"] == True] if len(c_out) else c_out  # noqa: E712
    s_id = bool(len(s_eval) and s_eval["mfe_mae_swap_pass"].all() and s_eval["rr_reciprocal_pass"].all())
    c_id = bool(len(c_eval) and c_eval["mfe_mae_swap_pass"].all() and c_eval["rr_reciprocal_pass"].all())
    if len(agg):
        agg_check = agg[pd.to_numeric(agg["record_count"], errors="coerce").fillna(0) > 0]
        agg_id = bool(len(agg_check) and agg_check["identity_summary_pass"].all())
    else:
        agg_id = False
    recon_ok = bool(meta.get("recon_pass_all"))
    hash_ok = meta.get("parent_config_hash") == PARENT_CONFIG_HASH_EXPECTED
    recon_status = "PASS" if (recon_ok and hash_ok and s_id and c_id and agg_id) else "FAIL"

    lines = [
        "NQ 4H WICK-REJECT -> 24H 1M PROTECTED-AREA",
        "OPPOSED-BIAS MIRROR AUDIT V1",
        "",
        "STATUS:",
        "DESCRIPTIVE ONLY / MATHEMATICAL MIRROR AUDIT",
        "",
        "PARENT:",
        PARENT_STUDY,
        "",
        "PARENT CONFIG HASH:",
        str(meta.get("parent_config_hash")),
        "",
        "RECONCILIATION:",
        recon_status,
        "",
        "Population matching",
        "- Parent eligible seeds / audit eligible seeds: 91 / %d" % meta["eligible_seeds"],
        "- Parent candidates / audit candidates: 90 / %d" % meta["candidates"],
        "- Parent bear / audit bear: 52 / %d" % meta["bear_candidates"],
        "- Parent bull / audit bull: 38 / %d" % meta["bull_candidates"],
        "- Parent structure evaluable / audit structure evaluable:",
        "  bear 39 / %s" % bear_s.get("record_count"),
        "  bull 32 / %s" % bull_s.get("record_count"),
        "- Parent contact evaluable / audit contact evaluable:",
        "  bear 34 / %s" % bear_c.get("record_count"),
        "  bull 29 / %s" % bull_c.get("record_count"),
        "",
        "Structure completion, unchanged 180-minute windows",
        "- Bear original RR / opposed RR: %s / %s"
        % (_fmt(bear_s.get("mean_original_rr"), 3), _fmt(bear_s.get("mean_opposed_rr"), 3)),
        "- Bear reciprocal identity: %s" % _recip_label(bear_s),
        "- Bull original RR / opposed RR: %s / %s"
        % (_fmt(bull_s.get("mean_original_rr"), 3), _fmt(bull_s.get("mean_opposed_rr"), 3)),
        "- Bull reciprocal identity: %s" % _recip_label(bull_s),
        "",
        "Contact reaction, unchanged 60-minute windows",
        "- Bear original MFE / MAE: %s / %s ticks"
        % (_fmt(bear_c.get("mean_original_mfe_ticks"), 2), _fmt(bear_c.get("mean_original_mae_ticks"), 2)),
        "- Bear opposed MFE / MAE: %s / %s ticks"
        % (_fmt(bear_c.get("mean_opposed_mfe_ticks"), 2), _fmt(bear_c.get("mean_opposed_mae_ticks"), 2)),
        "- Bear original RR / opposed RR: %s / %s"
        % (_fmt(bear_c.get("mean_original_rr"), 3), _fmt(bear_c.get("mean_opposed_rr"), 3)),
        "- Bear median original RR / opposed RR: %s / %s"
        % (_fmt(bear_c.get("median_original_rr"), 3), _fmt(bear_c.get("median_opposed_rr"), 3)),
        "- Bear concentration: top-1 %s%%, top-3 %s%%"
        % (
            _fmt(bear_c.get("top_1_original_mfe_contribution_pct"), 1),
            _fmt(bear_c.get("top_3_original_mfe_contribution_pct"), 1),
        ),
        "",
        "- Bull original MFE / MAE: %s / %s ticks"
        % (_fmt(bull_c.get("mean_original_mfe_ticks"), 2), _fmt(bull_c.get("mean_original_mae_ticks"), 2)),
        "- Bull opposed MFE / MAE: %s / %s ticks"
        % (_fmt(bull_c.get("mean_opposed_mfe_ticks"), 2), _fmt(bull_c.get("mean_opposed_mae_ticks"), 2)),
        "- Bull original RR / opposed RR: %s / %s"
        % (_fmt(bull_c.get("mean_original_rr"), 3), _fmt(bull_c.get("mean_opposed_rr"), 3)),
        "- Bull median original RR / opposed RR: %s / %s"
        % (_fmt(bull_c.get("median_original_rr"), 3), _fmt(bull_c.get("median_opposed_rr"), 3)),
        "- Bull concentration: top-1 %s%%, top-3 %s%%"
        % (
            _fmt(bull_c.get("top_1_original_mfe_contribution_pct"), 1),
            _fmt(bull_c.get("top_3_original_mfe_contribution_pct"), 1),
        ),
        "",
        "Interpretation",
        "- Opposed-bias values are an inverse labeling of the same parent price paths.",
        "- They do not validate reverse trading.",
        "- They do not authorize a bias selector, entry study, P&L study, or plugin.",
        "",
        "Disposition",
        "- Preserve parent study unchanged.",
        "- Preserve this audit unchanged.",
        "- No further reverse-bias variant work on this same sample.",
        "",
        "Final language",
        "",
        '"This opposed-bias audit uses the exact same candidates, protected areas,',
        "reference prices, first contacts, price windows, and data as the parent",
        "study. It reverses only the label for favorable and adverse movement. The",
        "resulting MFE/MAE and R-to-R values are therefore a mathematical mirror of",
        "the parent measurements, not independent evidence for a reverse trade or",
        'strategy."',
        "",
    ]
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email = (
        "potions: %s COMPLETE\n\n"
        "Hub: %s\n"
        "Parent: %s\n"
        "parent_config_hash: %s\n"
        "RECONCILIATION: %s\n"
        "eligible/candidates bear/bull: %d / %d / %d / %d\n"
        "structure bear orig/opp RR: %s / %s (recip %s)\n"
        "structure bull orig/opp RR: %s / %s (recip %s)\n"
        "contact bear orig/opp RR: %s / %s median %s / %s\n"
        "contact bull orig/opp RR: %s / %s median %s / %s\n\n"
        "DESCRIPTIVE ONLY / MATHEMATICAL MIRROR — not a reverse trade study.\n"
        "Preserve parent + audit; no reverse-bias variant on this sample.\n"
        % (
            STUDY_ID,
            hub,
            PARENT_STUDY,
            meta.get("parent_config_hash"),
            recon_status,
            meta["eligible_seeds"],
            meta["candidates"],
            meta["bear_candidates"],
            meta["bull_candidates"],
            _fmt(bear_s.get("mean_original_rr"), 3),
            _fmt(bear_s.get("mean_opposed_rr"), 3),
            _recip_label(bear_s),
            _fmt(bull_s.get("mean_original_rr"), 3),
            _fmt(bull_s.get("mean_opposed_rr"), 3),
            _recip_label(bull_s),
            _fmt(bear_c.get("mean_original_rr"), 3),
            _fmt(bear_c.get("mean_opposed_rr"), 3),
            _fmt(bear_c.get("median_original_rr"), 3),
            _fmt(bear_c.get("median_opposed_rr"), 3),
            _fmt(bull_c.get("mean_original_rr"), 3),
            _fmt(bull_c.get("mean_opposed_rr"), 3),
            _fmt(bull_c.get("median_original_rr"), 3),
            _fmt(bull_c.get("median_opposed_rr"), 3),
        )
    )
    (hub / "EMAIL.txt").write_text(email, encoding="utf-8")
    (hub / "STATUS.md").write_text(
        "status: COMPLETE\nreconciliation: %s\nstance: DESCRIPTIVE ONLY / MATHEMATICAL MIRROR AUDIT\n"
        % recon_status,
        encoding="utf-8",
    )
    out = {
        "study_id": STUDY_ID,
        "parent_study": PARENT_STUDY,
        "parent_config_hash": meta.get("parent_config_hash"),
        "reconciliation": recon_status,
        "eligible_seeds": meta["eligible_seeds"],
        "candidates": meta["candidates"],
        "bear_candidates": meta["bear_candidates"],
        "bull_candidates": meta["bull_candidates"],
        "structure_identity_pass": s_id,
        "contact_identity_pass": c_id,
        "aggregate_identity_pass": agg_id,
        "bear_structure": bear_s,
        "bull_structure": bull_s,
        "bear_contact": bear_c,
        "bull_contact": bull_c,
    }
    flat = {k: v for k, v in out.items() if not isinstance(v, (dict, list, tuple))}
    for key in ("bear_structure", "bull_structure", "bear_contact", "bull_contact"):
        flat[key] = json.dumps(out.get(key), default=str)
    pd.DataFrame([flat]).to_csv(hub / "summary.csv", index=False)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STUDY_ID)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--skip-charts", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    for sub in ("charts/pack_a", "charts/pack_b", "charts/pack_c"):
        (hub / sub).mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    cfg = (
        "parent=%s\nparent_config_hash=%s\nmode=OPPOSED_STRUCTURE_BIAS_MIRROR\n"
        "descriptive_only=true\nmirror_audit_only=true\nno_trade_model=true\n"
        % (PARENT_STUDY, PARENT_CONFIG_HASH_EXPECTED)
    )
    cfg_hash = hashlib.sha256(cfg.encode("utf-8")).hexdigest()[:16]
    (hub / "config_hash.txt").write_text(cfg_hash + "\n", encoding="utf-8")
    (hub / "CONFIG.md").write_text("# CONFIG — %s\n\n%s\n" % (STUDY_ID, cfg), encoding="utf-8")
    (hub / "MODEL_CONTRACT.yaml").write_text(
        "study_id: %s\nparent: %s\nparent_config_hash: %s\n"
        "measurement: opposed_structure_bias_mirror\ndescriptive_only: true\n"
        "mirror_audit_only: true\nno_trade_model: true\n"
        % (STUDY_ID, PARENT_STUDY, PARENT_CONFIG_HASH_EXPECTED),
        encoding="utf-8",
    )

    rid = begin_run(
        run_class="audit",
        variant_slug=STUDY_ID + ("_smoke" if args.smoke else ""),
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={
            "descriptive_only": True,
            "mirror_audit_only": True,
            "config_hash": cfg_hash,
            "parent": PARENT_STUDY,
            "parent_config_hash": PARENT_CONFIG_HASH_EXPECTED,
        },
    )

    try:
        if not (SRC_HUB / "structure_candidates.csv").exists():
            raise FileNotFoundError("Parent hub missing: %s" % SRC_HUB)

        if args.email:
            start = (
                "potions: %s STARTED\n\nHub: %s\n"
                "Mirror audit: opposed structure-bias labels on frozen V1 windows.\n"
                "parent_config_hash expected: %s\n"
                % (STUDY_ID, hub, PARENT_CONFIG_HASH_EXPECTED)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: %s STARTED" % STUDY_ID, body=start)

        _progress(hub, "Loading parent ledgers from %s" % SRC_HUB)
        parent_hash, elig, cands_all, structs, contacts, exclusions = _load_parent()
        _progress(
            hub,
            "Parent hash=%s elig=%d cands_all=%d structs=%d contacts=%d"
            % (parent_hash, len(elig), len(cands_all), len(structs), len(contacts)),
        )

        recon, s_out, c_out, meta = build_tables(
            parent_hash, elig, cands_all, structs, contacts
        )
        recon.to_csv(hub / "parent_reconciliation.csv", index=False)
        s_out.to_csv(hub / "opposed_structure_excursions.csv", index=False)
        c_out.to_csv(hub / "opposed_contact_excursions.csv", index=False)

        s_eval = s_out[s_out["data_complete"] == True] if len(s_out) else s_out  # noqa: E712
        c_eval = c_out[c_out["data_complete"] == True] if len(c_out) else c_out  # noqa: E712
        swap_fail_s = int((~s_eval["mfe_mae_swap_pass"]).sum()) if len(s_eval) else 0
        swap_fail_c = int((~c_eval["mfe_mae_swap_pass"]).sum()) if len(c_eval) else 0
        recip_fail_s = int((~s_eval["rr_reciprocal_pass"]).sum()) if len(s_eval) else 0
        recip_fail_c = int((~c_eval["rr_reciprocal_pass"]).sum()) if len(c_eval) else 0
        if swap_fail_s or swap_fail_c or recip_fail_s or recip_fail_c:
            msg = (
                "STATUS: RECONCILIATION FAILURE — identity assertions failed "
                "(struct_swap=%d struct_recip=%d contact_swap=%d contact_recip=%d)"
                % (swap_fail_s, recip_fail_s, swap_fail_c, recip_fail_c)
            )
            _progress(hub, msg)
            (hub / "RECONCILIATION_FAILURE.txt").write_text(msg + "\n", encoding="utf-8")
            raise RuntimeError(msg)

        _progress(hub, "Building aggregates")
        agg = build_aggregates(s_out, c_out)
        agg.to_csv(hub / "opposed_bias_aggregate_summary.csv", index=False)

        (hub / "CAUSALITY_AUDIT.md").write_text(
            "# CAUSALITY_AUDIT — %s\n\n"
            "Inherited from parent `%s` (frozen events; label mirror only).\n"
            "Parent config hash: %s (expected %s).\n"
            "See parent CAUSALITY_AUDIT.md — parent status PASS required.\n"
            % (STUDY_ID, PARENT_STUDY, parent_hash, PARENT_CONFIG_HASH_EXPECTED),
            encoding="utf-8",
        )

        metrics = write_reports(hub, meta, recon, s_out, c_out, agg)
        if metrics["reconciliation"] == "FAIL":
            raise RuntimeError("STATUS: RECONCILIATION FAILURE — see SUMMARY.md")

        if not args.skip_charts:
            _progress(hub, "Loading 1m bars for chart packs A–C")
            gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
            if args.smoke:
                cands = cands_all[cands_all["candidate_status"] == "COMPLETED"]
                dates = sorted(
                    {
                        _localize(pd.Timestamp(t)).date()
                        for t in cands["structure_complete_at"].dropna().tolist()
                    }
                )
                days = sorted(gby.keys())
                keep = set()
                for d in dates[:SMOKE_CHART_CAP]:
                    if d in days:
                        i = days.index(d)
                        keep.update(days[max(0, i - 2) : i + 3])
                gby = {d: gby[d] for d in days if d in keep}
            _tape, _h1, _h4, _early = build_rth_tape(gby)
            bars_1m = build_globex_1m(gby)
            _progress(hub, "bars_1m=%d — rendering charts" % len(bars_1m))
            from . import (
                nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_opposed_bias_audit_v1_charts as charts,
            )

            charts.render_all(
                hub=hub,
                study_id=STUDY_ID,
                parent_hash=parent_hash,
                cfg_hash=cfg_hash,
                data_version=DATA_VERSION,
                data_session_policy=DATA_SESSION_POLICY,
                elig=elig,
                cands_all=cands_all,
                structs=structs,
                contacts=contacts,
                s_out=s_out,
                c_out=c_out,
                bars_1m=bars_1m,
                smoke=args.smoke,
                smoke_cap=SMOKE_CHART_CAP,
            )
            _progress(hub, "charts done")

        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "finished_at": datetime.now().isoformat(),
                    "reconciliation": metrics["reconciliation"],
                    "config_hash": cfg_hash,
                    "parent_config_hash": parent_hash,
                    "smoke": args.smoke,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if args.email:
            body = (hub / "EMAIL.txt").read_text(encoding="utf-8")
            send_email(subject="potions: %s COMPLETE" % STUDY_ID, body=body)

        complete_run(
            rid,
            trades=int(metrics["candidates"]),
            meta={
                "reconciliation": metrics["reconciliation"],
                "bear_structure_opposed_rr": (metrics.get("bear_structure") or {}).get(
                    "mean_opposed_rr"
                ),
                "bull_structure_opposed_rr": (metrics.get("bull_structure") or {}).get(
                    "mean_opposed_rr"
                ),
            },
        )
        _progress(hub, "DONE reconciliation=%s" % metrics["reconciliation"])
        return 0
    except Exception as e:
        err = traceback.format_exc()
        (hub / "CRASH.txt").write_text(err, encoding="utf-8")
        _progress(hub, "CRASH: %s" % e)
        fail_run(rid, notes=str(e), meta={"traceback": err[-2000:]})
        if args.email:
            send_email(
                subject="potions: %s CRASHED" % STUDY_ID,
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
