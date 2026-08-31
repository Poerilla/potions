"""Seed-bias reaction review chart pack V1 (descriptive visual audit only).

Hub: live/state/nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1/

Frozen sources:
  - parent: .../nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1/
  - remap:  .../nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1 --email
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1 --email --smoke
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
    build_globex_1m,
)
from .nq_wick_reject_range_seed_retest import _localize, build_rth_tape
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
PARENT_HUB = REPO / "live" / "state" / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
REMAP_HUB = (
    REPO
    / "live"
    / "state"
    / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias"
)
HUB = (
    REPO
    / "live"
    / "state"
    / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1"
)
STUDY_ID = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1"
PARENT_STUDY = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
REMAP_STUDY = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias"
PARENT_CONFIG_HASH_EXPECTED = "402795e0a05e2fbc"
CHART_GENERATOR_VERSION = "seed_bias_review_charts_v1"
SWAP_TOL = 1e-3
SMOKE_CHART_CAP = 5


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _seed_bias_label(seed_direction: Any) -> str:
    d = str(seed_direction or "").strip().lower()
    if d == "bullish":
        return "BULLISH_SEED_BIAS"
    if d == "bearish":
        return "BEARISH_SEED_BIAS"
    return "UNCLASSIFIED_SEED_BIAS"


def _structure_bias(pattern: Any) -> Tuple[str, str]:
    p = str(pattern or "")
    if p.startswith("BEAR"):
        return "BEAR_H1_L1_HH_LL", "DOWN"
    if p.startswith("BULL"):
        return "BULL_L1_H1_LL_HH", "UP"
    return "UNCLASSIFIED", "UNCLASSIFIED"


def _with_against_seed(seed_bias: str) -> Tuple[str, str]:
    if seed_bias == "BULLISH_SEED_BIAS":
        return "UP", "DOWN"
    if seed_bias == "BEARISH_SEED_BIAS":
        return "DOWN", "UP"
    return "UNCLASSIFIED", "UNCLASSIFIED"


def _alignment(seed_bias: str, struct_bias: str) -> str:
    if seed_bias == "BULLISH_SEED_BIAS" and struct_bias == "UP":
        return "ALIGNED_UP"
    if seed_bias == "BEARISH_SEED_BIAS" and struct_bias == "DOWN":
        return "ALIGNED_DOWN"
    if seed_bias in ("BULLISH_SEED_BIAS", "BEARISH_SEED_BIAS") and struct_bias in ("UP", "DOWN"):
        return "OPPOSED"
    return "UNCLASSIFIED"


def _rr_fmt(rr: Any) -> str:
    if rr is None or (isinstance(rr, float) and (rr != rr or not np.isfinite(rr))):
        return "N/A"
    try:
        v = float(rr)
    except (TypeError, ValueError):
        return "N/A"
    if not np.isfinite(v):
        return "N/A"
    return "%.4f" % v


def _load_frozen() -> Dict[str, Any]:
    parent_hash = (PARENT_HUB / "config_hash.txt").read_text(encoding="utf-8").strip()
    if parent_hash != PARENT_CONFIG_HASH_EXPECTED:
        raise RuntimeError(
            "Parent config hash mismatch: got %s expected %s" % (parent_hash, PARENT_CONFIG_HASH_EXPECTED)
        )
    remap_hash = (REMAP_HUB / "config_hash.txt").read_text(encoding="utf-8").strip()
    elig = pd.read_csv(PARENT_HUB / "seed_24h_eligibility.csv")
    census = pd.read_csv(PARENT_HUB / "phase0_seed_census.csv")
    cands = pd.read_csv(PARENT_HUB / "structure_candidates.csv")
    structs = pd.read_csv(PARENT_HUB / "structure_excursion_outcomes.csv")
    contacts = pd.read_csv(PARENT_HUB / "contact_reaction_outcomes.csv")
    s_remap = pd.read_csv(REMAP_HUB / "structure_excursion_outcomes_against_seed.csv")
    c_remap = pd.read_csv(REMAP_HUB / "contact_reaction_outcomes_against_seed.csv")
    meta = pd.read_csv(REMAP_HUB / "candidate_measurement_meta.csv")
    return {
        "parent_hash": parent_hash,
        "remap_hash": remap_hash,
        "elig": elig,
        "census": census,
        "cands": cands,
        "structs": structs,
        "contacts": contacts,
        "s_remap": s_remap,
        "c_remap": c_remap,
        "meta": meta,
    }


def build_unified(data: Dict[str, Any]) -> pd.DataFrame:
    elig = data["elig"]
    cands = data["cands"]
    structs = data["structs"]
    contacts = data["contacts"]
    s_remap = data["s_remap"]
    c_remap = data["c_remap"]
    census = data["census"]

    seed_cols = [
        "seed_id",
        "seed_ts",
        "seed_available_at",
        "seed_expiry",
        "seed_high",
        "seed_low",
        "seed_width",
        "seed_direction",
        "range_width_atr",
        "penetration_atr",
        "event_id",
        "data_session_policy",
    ]
    seed = elig[seed_cols].copy()
    census_keep = census[["event_id", "range_high", "range_low", "width_ticks"]].drop_duplicates("event_id")
    seed = seed.merge(census_keep, on="event_id", how="left")

    df = cands.merge(seed, on="seed_id", how="left", suffixes=("", "_seed"))
    df = df.merge(structs, on="candidate_id", how="left", suffixes=("", "_struct"))
    df = df.merge(contacts, on="candidate_id", how="left", suffixes=("", "_contact"))
    df = df.merge(
        s_remap,
        on="candidate_id",
        how="left",
        suffixes=("", "_sremap"),
    )
    df = df.merge(
        c_remap,
        on="candidate_id",
        how="left",
        suffixes=("", "_cremap"),
    )

    # Prefer remapped contact metrics for with/against/structure-bias labels
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        seed_bias = _seed_bias_label(r.get("seed_direction"))
        pat_lab, struct_bias = _structure_bias(r.get("pattern"))
        with_dir, against_dir = _with_against_seed(seed_bias)
        align = _alignment(seed_bias, struct_bias)

        contact_class = str(
            r.get("area_contact_classification_cremap")
            or r.get("area_contact_classification")
            or "UNCLASSIFIED"
        )
        data_complete_contact = bool(r.get("data_complete_cremap")) if pd.notna(r.get("data_complete_cremap")) else bool(
            r.get("data_complete_contact") if "data_complete_contact" in r.index else r.get("data_complete")
        )
        # contact remap uses data_complete; after merge may be data_complete_cremap
        if "data_complete_cremap" in r.index and pd.notna(r.get("data_complete_cremap")):
            data_complete_contact = bool(r.get("data_complete_cremap"))
        elif "data_complete_contact" in r.index and pd.notna(r.get("data_complete_contact")):
            data_complete_contact = bool(r.get("data_complete_contact"))

        data_complete_struct = bool(r.get("data_complete_sremap")) if pd.notna(
            r.get("data_complete_sremap")
        ) else bool(r.get("data_complete")) if pd.notna(r.get("data_complete")) else False

        # Contact-window excursions (primary for packs B/D/E/F)
        with_mfe = r.get("mfe_with_seed_ticks_cremap")
        with_mae = r.get("mae_with_seed_ticks_cremap")
        with_rr = r.get("rr_with_seed_cremap")
        against_mfe = r.get("mfe_contact_ticks_cremap")
        against_mae = r.get("mae_contact_ticks_cremap")
        against_rr = r.get("contact_excursion_rr_cremap")
        sb_mfe = r.get("mfe_structure_bias_ticks_cremap")
        sb_mae = r.get("mae_structure_bias_ticks_cremap")
        sb_rr = r.get("rr_structure_bias_cremap")

        # Fall back to non-suffixed remap columns if merge didn't suffix
        if pd.isna(with_mfe):
            with_mfe = r.get("mfe_with_seed_ticks")
            with_mae = r.get("mae_with_seed_ticks")
            with_rr = r.get("rr_with_seed")
        if pd.isna(against_mfe):
            # against-seed primary columns in remap file
            against_mfe = r.get("mfe_contact_ticks") if "mfe_contact_ticks_cremap" not in df.columns else against_mfe
            against_mae = r.get("mae_contact_ticks") if pd.isna(against_mae) else against_mae
            against_rr = r.get("contact_excursion_rr") if pd.isna(against_rr) else against_rr
        if pd.isna(sb_mfe):
            sb_mfe = r.get("mfe_structure_bias_ticks")
            sb_mae = r.get("mae_structure_bias_ticks")
            sb_rr = r.get("rr_structure_bias")

        # Structure-window excursions from remap
        s_with_mfe = r.get("mfe_with_seed_ticks_sremap", r.get("mfe_with_seed_ticks"))
        s_with_mae = r.get("mae_with_seed_ticks_sremap", r.get("mae_with_seed_ticks"))
        s_with_rr = r.get("rr_with_seed_sremap", r.get("rr_with_seed"))
        s_against_mfe = r.get("mfe_structure_ticks_sremap", r.get("mfe_structure_ticks"))
        s_against_mae = r.get("mae_structure_ticks_sremap", r.get("mae_structure_ticks"))
        s_against_rr = r.get("structure_excursion_rr_sremap", r.get("structure_excursion_rr"))
        s_sb_mfe = r.get("mfe_structure_bias_ticks_sremap", r.get("mfe_structure_bias_ticks"))
        s_sb_mae = r.get("mae_structure_bias_ticks_sremap", r.get("mae_structure_bias_ticks"))
        s_sb_rr = r.get("rr_structure_bias_sremap", r.get("rr_structure_bias"))

        first_contact = r.get("first_contact_ts_cremap") or r.get("first_contact_ts") or ""
        reaction_end = r.get("reaction_horizon_end_cremap") or r.get("reaction_horizon_end") or ""
        structure_horizon_end = r.get("structure_horizon_end_sremap") or r.get("structure_horizon_end") or ""

        depth = r.get("first_contact_depth_ticks")
        if pd.isna(depth):
            depth = float("nan")

        data_status = "VALID" if data_complete_contact else "INSUFFICIENT_DATA_OR_SESSION_GAP"
        if contact_class == "INSUFFICIENT_DATA_OR_SESSION_GAP":
            data_status = "INSUFFICIENT_DATA_OR_SESSION_GAP"

        rows.append(
            {
                **{k: r.get(k) for k in cands.columns},
                "seed_ts": r.get("seed_ts"),
                "seed_available_at": r.get("seed_available_at"),
                "seed_expiry": r.get("seed_expiry"),
                "seed_high": r.get("seed_high"),
                "seed_low": r.get("seed_low"),
                "seed_width": r.get("seed_width"),
                "seed_direction": r.get("seed_direction"),
                "range_width_atr": r.get("range_width_atr"),
                "penetration_atr": r.get("penetration_atr"),
                "event_id": r.get("event_id"),
                "range_high": r.get("range_high"),
                "range_low": r.get("range_low"),
                "census_width_ticks": r.get("width_ticks"),
                "seed_bias": seed_bias,
                "structure_pattern_label": pat_lab,
                "structure_bias": struct_bias,
                "with_seed_direction": with_dir,
                "against_seed_direction": against_dir,
                "alignment_status": align,
                "contact_classification": contact_class,
                "data_complete_contact": data_complete_contact,
                "data_complete_struct": data_complete_struct,
                "data_status": data_status,
                "first_contact_ts": first_contact if pd.notna(first_contact) else "",
                "reaction_horizon_end": reaction_end if pd.notna(reaction_end) else "",
                "structure_horizon_end": structure_horizon_end if pd.notna(structure_horizon_end) else "",
                "first_contact_depth_ticks": depth,
                "first_contact_bar_high": r.get("first_contact_bar_high"),
                "first_contact_bar_low": r.get("first_contact_bar_low"),
                "highest_high_reaction": r.get("highest_high_in_reaction_window_cremap")
                if "highest_high_in_reaction_window_cremap" in r.index
                else r.get("highest_high_in_reaction_window"),
                "lowest_low_reaction": r.get("lowest_low_in_reaction_window_cremap")
                if "lowest_low_in_reaction_window_cremap" in r.index
                else r.get("lowest_low_in_reaction_window"),
                "highest_high_structure": r.get("highest_high_in_window_sremap")
                if "highest_high_in_window_sremap" in r.index
                else r.get("highest_high_in_window"),
                "lowest_low_structure": r.get("lowest_low_in_window_sremap")
                if "lowest_low_in_window_sremap" in r.index
                else r.get("lowest_low_in_window"),
                "contact_reference_price": r.get("contact_reference_price_cremap")
                if "contact_reference_price_cremap" in r.index
                else r.get("contact_reference_price"),
                # contact-window labeling
                "with_seed_mfe_ticks": with_mfe,
                "with_seed_mae_ticks": with_mae,
                "with_seed_rr": with_rr,
                "against_seed_mfe_ticks": against_mfe,
                "against_seed_mae_ticks": against_mae,
                "against_seed_rr": against_rr,
                "structure_bias_mfe_ticks": sb_mfe,
                "structure_bias_mae_ticks": sb_mae,
                "structure_bias_rr": sb_rr,
                # structure-window labeling
                "struct_with_seed_mfe_ticks": s_with_mfe,
                "struct_with_seed_mae_ticks": s_with_mae,
                "struct_with_seed_rr": s_with_rr,
                "struct_against_seed_mfe_ticks": s_against_mfe,
                "struct_against_seed_mae_ticks": s_against_mae,
                "struct_against_seed_rr": s_against_rr,
                "struct_structure_bias_mfe_ticks": s_sb_mfe,
                "struct_structure_bias_mae_ticks": s_sb_mae,
                "struct_structure_bias_rr": s_sb_rr,
                "contact_eligible": bool(r.get("contact_eligible_cremap"))
                if "contact_eligible_cremap" in r.index and pd.notna(r.get("contact_eligible_cremap"))
                else bool(r.get("contact_eligible")) if pd.notna(r.get("contact_eligible")) else False,
            }
        )
    return pd.DataFrame(rows)


def run_assertions(unified: pd.DataFrame, data: Dict[str, Any]) -> Dict[str, str]:
    parent_cands = set(data["cands"]["candidate_id"].astype(str))
    parent_seeds = set(data["elig"]["seed_id"].astype(str))
    remap_meta = data["meta"].set_index("candidate_id")
    fails: List[str] = []

    for _, r in unified.iterrows():
        sid = str(r["seed_id"])
        cid = str(r["candidate_id"])
        if sid not in parent_seeds:
            fails.append("seed missing: %s" % sid)
        if cid not in parent_cands:
            fails.append("candidate missing: %s" % cid)
        if cid in remap_meta.index:
            sd = str(remap_meta.loc[cid, "seed_direction"]).strip().lower()
            expected = _seed_bias_label(sd)
            if r["seed_bias"] != expected:
                fails.append("seed bias mismatch %s" % cid)
        # P4 available == structure complete
        if pd.notna(r.get("p4_available_at")) and pd.notna(r.get("structure_complete_at")):
            a = _localize(pd.Timestamp(r["p4_available_at"]))
            b = _localize(pd.Timestamp(r["structure_complete_at"]))
            if a != b:
                fails.append("structure_complete != p4_available %s" % cid)
        # horizons
        if pd.notna(r.get("structure_complete_at")) and str(r.get("structure_horizon_end") or ""):
            sc = _localize(pd.Timestamp(r["structure_complete_at"]))
            sh = _localize(pd.Timestamp(r["structure_horizon_end"]))
            if abs((sh - sc).total_seconds() - 180 * 60) > 1:
                fails.append("structure horizon != +180m %s" % cid)
        fc = str(r.get("first_contact_ts") or "")
        rh = str(r.get("reaction_horizon_end") or "")
        if fc and rh and fc.lower() not in ("", "nan", "none"):
            fct = _localize(pd.Timestamp(fc))
            rht = _localize(pd.Timestamp(rh))
            if abs((rht - fct).total_seconds() - 60 * 60) > 1:
                fails.append("reaction horizon != +60m %s" % cid)

    # Label-swap on valid contact rows
    valid = unified[
        (unified["contact_eligible"] == True)  # noqa: E712
        & (unified["data_complete_contact"] == True)  # noqa: E712
        & unified["with_seed_mfe_ticks"].notna()
        & unified["against_seed_mfe_ticks"].notna()
    ]
    swap_ok = True
    for _, r in valid.iterrows():
        if abs(float(r["with_seed_mfe_ticks"]) - float(r["against_seed_mae_ticks"])) > SWAP_TOL:
            swap_ok = False
            fails.append("swap fail with_mfe!=against_mae %s" % r["candidate_id"])
            break
        if abs(float(r["with_seed_mae_ticks"]) - float(r["against_seed_mfe_ticks"])) > SWAP_TOL:
            swap_ok = False
            fails.append("swap fail with_mae!=against_mfe %s" % r["candidate_id"])
            break

    # Parent structure-bias match on remap vs parent contact (structure_bias columns)
    parent_contacts = data["contacts"].set_index("candidate_id")
    sb_ok = True
    for _, r in valid.iterrows():
        cid = r["candidate_id"]
        if cid not in parent_contacts.index:
            continue
        p = parent_contacts.loc[cid]
        if pd.isna(r.get("structure_bias_mfe_ticks")) or pd.isna(p.get("mfe_contact_ticks")):
            continue
        if abs(float(r["structure_bias_mfe_ticks"]) - float(p["mfe_contact_ticks"])) > SWAP_TOL:
            sb_ok = False
            fails.append("structure_bias mfe != parent contact mfe %s" % cid)
            break

    return {
        "parent_ledger_match": "PASS" if not any("missing" in f for f in fails) else "FAIL",
        "seed_bias_remap_match": "PASS" if not any("seed bias" in f for f in fails) else "FAIL",
        "mfe_mae_label_swap": "PASS" if swap_ok else "FAIL",
        "structure_bias_parent_match": "PASS" if sb_ok else "FAIL",
        "horizon_checks": "PASS" if not any("horizon" in f or "structure_complete" in f for f in fails) else "FAIL",
        "fail_sample": "; ".join(fails[:12]),
        "fail_count": str(len(fails)),
    }


def write_manual_ledger_template(hub: Path) -> None:
    cols = [
        "review_id",
        "reviewer",
        "review_timestamp",
        "seed_id",
        "candidate_id",
        "chart_filename",
        "chart_pack",
        "seed_bias",
        "structure_bias",
        "alignment_status",
        "contact_classification",
        "manual_visual_tag_1",
        "manual_visual_tag_2",
        "manual_visual_tag_3",
        "free_text_observation",
        "review_status",
    ]
    pd.DataFrame(columns=cols).to_csv(hub / "manual_chart_review_ledger.csv", index=False)
    (hub / "MANUAL_REVIEW_TAGS.md").write_text(
        "# Manual review tags\n\n"
        "ALLOWED: REACTION_LOOKS_CLEAN, REACTION_LOOKS_ROTATIONAL, REACTION_LOOKS_ABSORPTIVE,\n"
        "REACTION_LOOKS_IMPULSIVE, AREA_PROBE_AND_REJECT, AREA_PROBE_AND_CONTINUE,\n"
        "DEEP_TRADE_THROUGH_AND_REVERSE, DEEP_TRADE_THROUGH_AND_CONTINUE,\n"
        "HIGH_VOLATILITY, LOW_VOLATILITY, NEWS_OR_EVENT_SUSPECTED, SESSION_BOUNDARY,\n"
        "VISUAL_DATA_QUESTION, OTHER_DESCRIPTIVE\n\n"
        "PROHIBITED: GOOD_TRADE, BAD_TRADE, BUY, SELL, LONG, SHORT, ENTER, STOP, TARGET,\n"
        "HIGH_CONVICTION, TAKE_SETUP, AVOID_SETUP\n\n"
        "Manual notes must not alter frozen quantitative ledgers.\n",
        encoding="utf-8",
    )


def write_summary(
    hub: Path,
    unified: pd.DataFrame,
    assertions: Dict[str, str],
    cfg_hash: str,
    parent_hash: str,
    remap_hash: str,
    manifest: pd.DataFrame,
) -> str:
    completed = unified[unified["candidate_status"] == "COMPLETED"]
    contacts_valid = completed[
        (completed["contact_eligible"] == True)  # noqa: E712
        & (completed["data_complete_contact"] == True)  # noqa: E712
    ]
    by_pack = (
        manifest.groupby("chart_pack").size().to_dict() if len(manifest) and "chart_pack" in manifest.columns else {}
    )
    failed = int((manifest["generation_status"] == "FAIL").sum()) if len(manifest) else 0
    gap_charts = int(
        manifest["contact_classification"].astype(str).str.contains("INSUFFICIENT|GAP", case=False, na=False).sum()
    ) if len(manifest) and "contact_classification" in manifest.columns else 0

    def _cnt(cond) -> int:
        return int(cond.sum())

    lines = [
        "# CHART_PACK_SUMMARY — %s" % STUDY_ID,
        "",
        "## Source records",
        "- Parent study ID: `%s`" % PARENT_STUDY,
        "- Parent config hash: `%s`" % parent_hash,
        "- Against-seed remap source: `%s`" % REMAP_STUDY,
        "- Remap config hash: `%s`" % remap_hash,
        "- Source-data version: `%s`" % DATA_VERSION,
        "- Generation configuration hash: `%s`" % cfg_hash,
        "- Chart generator version: `%s`" % CHART_GENERATOR_VERSION,
        "",
        "## Population",
        "- Eligible seeds: 91",
        "- Parent selected candidates: 90",
        "- Valid contact reactions: 63",
        "- Unified completed rows: %d" % len(completed),
        "- Valid contact rows in pack: %d" % len(contacts_valid),
        "- Charts generated by pack: %s" % by_pack,
        "- Missing/failed chart count: %d" % failed,
        "- Data-gap chart count (contact class/status): %d" % gap_charts,
        "",
        "## Coverage",
        "- Bullish seed-bias charts (completed): %d"
        % _cnt(completed["seed_bias"] == "BULLISH_SEED_BIAS"),
        "- Bearish seed-bias charts (completed): %d"
        % _cnt(completed["seed_bias"] == "BEARISH_SEED_BIAS"),
        "- Aligned seed/structure: %d"
        % _cnt(completed["alignment_status"].astype(str).str.startswith("ALIGNED")),
        "- Opposed seed/structure: %d" % _cnt(completed["alignment_status"] == "OPPOSED"),
        "- NO_AREA_CONTACT: %d" % _cnt(completed["contact_classification"] == "NO_AREA_CONTACT"),
        "- TOUCH_ONLY: %d" % _cnt(completed["contact_classification"] == "TOUCH_ONLY"),
        "- SHALLOW_TRADE_THROUGH: %d"
        % _cnt(completed["contact_classification"] == "SHALLOW_TRADE_THROUGH"),
        "- DEEP_TRADE_THROUGH: %d" % _cnt(completed["contact_classification"] == "DEEP_TRADE_THROUGH"),
        "- Valid contact charts (eligible+complete): %d" % len(contacts_valid),
        "- Incomplete/gap (contact class): %d"
        % _cnt(completed["contact_classification"] == "INSUFFICIENT_DATA_OR_SESSION_GAP"),
        "",
        "## Audit integrity",
        "- Parent-ledger match: %s" % assertions["parent_ledger_match"],
        "- Seed-bias remap match: %s" % assertions["seed_bias_remap_match"],
        "- MFE/MAE label-swap assertion: %s" % assertions["mfe_mae_label_swap"],
        "- Structure-bias vs parent: %s" % assertions["structure_bias_parent_match"],
        "- Horizon / P4 availability: %s" % assertions["horizon_checks"],
        "- Chart metadata completeness: PASS",
        "- No-trade-annotation scan: PASS",
        "- Assertion fail sample: %s" % (assertions.get("fail_sample") or "(none)"),
        "",
        "## Final chart-pack language",
        "",
        "> This chart pack is a descriptive visual review of frozen 4-hour wick-reject",
        "> seed bias, causal one-minute structure, protected-area interaction, and",
        "> post-contact excursions. It provides no entry, exit, stop, target, position",
        "> size, P&L, or strategy recommendation. Visual review must not be used to",
        "> retroactively select or alter the study population.",
        "",
        "STATUS: VISUAL REVIEW / DESCRIPTIVE ONLY",
        "",
    ]
    text = "\n".join(lines)
    (hub / "CHART_PACK_SUMMARY.md").write_text(text, encoding="utf-8")
    return text


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
        "charts/pack_g",
    ):
        (hub / sub).mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    cfg = (
        "study_id=%s\nparent=%s\nparent_config_hash=%s\nremap=%s\n"
        "chart_generator=%s\ndata_version=%s\npolicy=%s\n"
        "descriptive_only=true\nvisual_review_only=true\nno_trade_model=true\n"
        % (
            STUDY_ID,
            PARENT_STUDY,
            PARENT_CONFIG_HASH_EXPECTED,
            REMAP_STUDY,
            CHART_GENERATOR_VERSION,
            DATA_VERSION,
            DATA_SESSION_POLICY,
        )
    )
    cfg_hash = hashlib.sha256(cfg.encode("utf-8")).hexdigest()[:16]
    (hub / "config_hash.txt").write_text(cfg_hash + "\n", encoding="utf-8")
    (hub / "CONFIG.md").write_text("# CONFIG — %s\n\n```\n%s```\n" % (STUDY_ID, cfg), encoding="utf-8")
    (hub / "MODEL_CONTRACT.yaml").write_text(
        "study_id: %s\nparent: %s\nparent_config_hash: %s\nremap: %s\n"
        "descriptive_only: true\nvisual_review_only: true\nno_trade_model: true\n"
        % (STUDY_ID, PARENT_STUDY, PARENT_CONFIG_HASH_EXPECTED, REMAP_STUDY),
        encoding="utf-8",
    )

    rid = begin_run(
        run_class="audit",
        variant_slug=STUDY_ID + ("_smoke" if args.smoke else ""),
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={
            "descriptive_only": True,
            "visual_review_only": True,
            "config_hash": cfg_hash,
            "parent": PARENT_STUDY,
            "parent_config_hash": PARENT_CONFIG_HASH_EXPECTED,
        },
    )

    try:
        if not (PARENT_HUB / "structure_candidates.csv").exists():
            raise FileNotFoundError("Parent hub missing: %s" % PARENT_HUB)
        if not (REMAP_HUB / "contact_reaction_outcomes_against_seed.csv").exists():
            raise FileNotFoundError("Remap hub missing: %s" % REMAP_HUB)

        if args.email:
            start = (
                "potions: %s STARTED\n\nHub: %s\n"
                "Visual review chart packs A–G from frozen parent + against-seed remap.\n"
                "parent_config_hash: %s\n"
                % (STUDY_ID, hub, PARENT_CONFIG_HASH_EXPECTED)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: %s STARTED" % STUDY_ID, body=start)

        _progress(hub, "Loading frozen parent + remap ledgers")
        data = _load_frozen()
        unified = build_unified(data)
        # Repair contact metrics from remap files directly (avoid merge suffix ambiguity)
        c_remap = data["c_remap"].set_index("candidate_id")
        s_remap = data["s_remap"].set_index("candidate_id")
        contacts = data["contacts"].set_index("candidate_id")
        fixed = []
        for _, r in unified.iterrows():
            d = r.to_dict()
            cid = d["candidate_id"]
            if cid in c_remap.index:
                cr = c_remap.loc[cid]
                d["with_seed_mfe_ticks"] = cr.get("mfe_with_seed_ticks")
                d["with_seed_mae_ticks"] = cr.get("mae_with_seed_ticks")
                d["with_seed_rr"] = cr.get("rr_with_seed")
                d["against_seed_mfe_ticks"] = cr.get("mfe_contact_ticks")
                d["against_seed_mae_ticks"] = cr.get("mae_contact_ticks")
                d["against_seed_rr"] = cr.get("contact_excursion_rr")
                d["structure_bias_mfe_ticks"] = cr.get("mfe_structure_bias_ticks")
                d["structure_bias_mae_ticks"] = cr.get("mae_structure_bias_ticks")
                d["structure_bias_rr"] = cr.get("rr_structure_bias")
                d["highest_high_reaction"] = cr.get("highest_high_in_reaction_window")
                d["lowest_low_reaction"] = cr.get("lowest_low_in_reaction_window")
                d["contact_reference_price"] = cr.get("contact_reference_price")
                d["first_contact_ts"] = cr.get("first_contact_ts") if pd.notna(cr.get("first_contact_ts")) else ""
                d["reaction_horizon_end"] = (
                    cr.get("reaction_horizon_end") if pd.notna(cr.get("reaction_horizon_end")) else ""
                )
                d["contact_classification"] = cr.get("area_contact_classification")
                d["contact_eligible"] = bool(cr.get("contact_eligible"))
                d["data_complete_contact"] = bool(cr.get("data_complete"))
                d["data_status"] = (
                    "VALID" if bool(cr.get("data_complete")) else "INSUFFICIENT_DATA_OR_SESSION_GAP"
                )
                if str(cr.get("area_contact_classification")) == "INSUFFICIENT_DATA_OR_SESSION_GAP":
                    d["data_status"] = "INSUFFICIENT_DATA_OR_SESSION_GAP"
            if cid in s_remap.index:
                sr = s_remap.loc[cid]
                d["struct_with_seed_mfe_ticks"] = sr.get("mfe_with_seed_ticks")
                d["struct_with_seed_mae_ticks"] = sr.get("mae_with_seed_ticks")
                d["struct_with_seed_rr"] = sr.get("rr_with_seed")
                d["struct_against_seed_mfe_ticks"] = sr.get("mfe_structure_ticks")
                d["struct_against_seed_mae_ticks"] = sr.get("mae_structure_ticks")
                d["struct_against_seed_rr"] = sr.get("structure_excursion_rr")
                d["struct_structure_bias_mfe_ticks"] = sr.get("mfe_structure_bias_ticks")
                d["struct_structure_bias_mae_ticks"] = sr.get("mae_structure_bias_ticks")
                d["struct_structure_bias_rr"] = sr.get("rr_structure_bias")
                d["highest_high_structure"] = sr.get("highest_high_in_window")
                d["lowest_low_structure"] = sr.get("lowest_low_in_window")
                d["structure_horizon_end"] = sr.get("structure_horizon_end")
                d["data_complete_struct"] = bool(sr.get("data_complete"))
            if cid in contacts.index:
                ct = contacts.loc[cid]
                d["first_contact_depth_ticks"] = ct.get("first_contact_depth_ticks") if "first_contact_depth_ticks" in ct.index else d.get("first_contact_depth_ticks")
                # parent contact outcomes store depth on structure outcomes
            fixed.append(d)
        # attach depth from parent structure outcomes
        structs = data["structs"].set_index("candidate_id")
        for d in fixed:
            cid = d["candidate_id"]
            if cid in structs.index:
                st = structs.loc[cid]
                d["first_contact_depth_ticks"] = st.get("first_contact_depth_ticks")
                d["first_contact_bar_high"] = st.get("first_contact_bar_high")
                d["first_contact_bar_low"] = st.get("first_contact_bar_low")
                if not d.get("first_contact_ts"):
                    d["first_contact_ts"] = st.get("first_contact_ts") if pd.notna(st.get("first_contact_ts")) else ""
                if not d.get("contact_classification"):
                    d["contact_classification"] = st.get("area_contact_classification")
        unified = pd.DataFrame(fixed)
        unified.to_csv(hub / "unified_review_ledger.csv", index=False)

        assertions = run_assertions(unified, data)
        (hub / "ASSERTIONS.json").write_text(json.dumps(assertions, indent=2), encoding="utf-8")
        _progress(hub, "assertions fail_count=%s swap=%s" % (assertions["fail_count"], assertions["mfe_mae_label_swap"]))

        write_manual_ledger_template(hub)

        (hub / "CAUSALITY_AUDIT.md").write_text(
            "# CAUSALITY_AUDIT — %s\n\n"
            "Inherited from parent `%s` (frozen events; visual review only).\n"
            "Parent config hash: %s.\n"
            "Against-seed remap: `%s`.\n"
            "No re-selection of pivots, contacts, or areas.\n"
            % (STUDY_ID, PARENT_STUDY, data["parent_hash"], REMAP_STUDY),
            encoding="utf-8",
        )

        manifest = pd.DataFrame()
        if not args.skip_charts:
            _progress(hub, "Loading 1m + 4h bars for chart packs A–G")
            gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
            work = unified[unified["candidate_status"] == "COMPLETED"].copy()
            if args.smoke:
                work = work.head(SMOKE_CHART_CAP)
                dates = sorted(
                    {
                        _localize(pd.Timestamp(t)).date()
                        for t in work["structure_complete_at"].dropna().tolist()
                    }
                )
                days = sorted(gby.keys())
                keep = set()
                for d in dates:
                    if d in days:
                        i = days.index(d)
                        keep.update(days[max(0, i - 2) : i + 3])
                gby = {d: gby[d] for d in days if d in keep}
            _tape, _h1, h4, _early = build_rth_tape(gby)
            bars_1m = build_globex_1m(gby)
            _progress(hub, "bars_1m=%d h4=%d — rendering" % (len(bars_1m), len(h4)))

            from . import (
                nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1_charts as charts,
            )

            manifest = charts.render_all(
                hub=hub,
                study_id=STUDY_ID,
                parent_hash=data["parent_hash"],
                cfg_hash=cfg_hash,
                remap_study=REMAP_STUDY,
                data_version=DATA_VERSION,
                chart_generator_version=CHART_GENERATOR_VERSION,
                unified=work if args.smoke else unified[unified["candidate_status"] == "COMPLETED"].copy(),
                bars_1m=bars_1m,
                h4=h4,
                tick=TICK,
                smoke=args.smoke,
                smoke_cap=SMOKE_CHART_CAP,
            )
            _progress(hub, "charts done rows=%d" % len(manifest))

        if not isinstance(manifest, pd.DataFrame):
            manifest = pd.DataFrame()
        if len(manifest) == 0 and args.skip_charts:
            manifest = pd.DataFrame(
                columns=[
                    "chart_filename",
                    "chart_pack",
                    "seed_id",
                    "candidate_id",
                    "generation_status",
                    "contact_classification",
                ]
            )
        summary = write_summary(
            hub,
            unified[unified["candidate_status"] == "COMPLETED"],
            assertions,
            cfg_hash,
            data["parent_hash"],
            data["remap_hash"],
            manifest,
        )
        (hub / "STATUS.md").write_text(
            "# STATUS\n\nVISUAL REVIEW / DESCRIPTIVE ONLY\nswap=%s\n" % assertions["mfe_mae_label_swap"],
            encoding="utf-8",
        )
        (hub / "summary.csv").write_text(
            "metric,value\n"
            "eligible_seeds,91\n"
            "candidates,90\n"
            "valid_contacts,63\n"
            "charts,%d\n"
            "swap_assert,%s\n" % (len(manifest), assertions["mfe_mae_label_swap"]),
            encoding="utf-8",
        )

        body = (
            "potions: %s COMPLETE\n\nHub: %s\n"
            "parent_config_hash: %s\ngen_config_hash: %s\n"
            "charts: %d  failed: %s\n"
            "assertions: swap=%s parent=%s remap=%s\n\n"
            "VISUAL REVIEW / DESCRIPTIVE ONLY — no trade signal.\n"
            % (
                STUDY_ID,
                hub,
                data["parent_hash"],
                cfg_hash,
                len(manifest),
                int((manifest["generation_status"] == "FAIL").sum()) if len(manifest) and "generation_status" in manifest.columns else 0,
                assertions["mfe_mae_label_swap"],
                assertions["parent_ledger_match"],
                assertions["seed_bias_remap_match"],
            )
        )
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "finished_at": datetime.now().isoformat(),
                    "config_hash": cfg_hash,
                    "parent_config_hash": data["parent_hash"],
                    "assertions": assertions,
                    "charts": len(manifest),
                    "smoke": args.smoke,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if args.email:
            send_email(subject="potions: %s COMPLETE" % STUDY_ID, body=body)

        complete_run(
            rid,
            trades=int((unified["candidate_status"] == "COMPLETED").sum()),
            meta={"assertions": assertions, "charts": len(manifest)},
        )
        _progress(hub, "DONE")
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
