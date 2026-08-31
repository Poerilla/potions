"""Remap V1 protected-area reaction excursions against the 4h seed bias.

Frozen V1 events/windows are reused (no re-selection). Favorable/adverse are
redefined so "favorable" = opposite the 4h WICK_REJECT seed direction.

Hub: live/state/nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias --email
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
    _excursion_stats,
    _fmt,
)
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
SRC_HUB = REPO / "live" / "state" / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"
HUB = (
    REPO
    / "live"
    / "state"
    / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias"
)
STUDY_ID = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias"
PARENT_STUDY = "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1"


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _opp(direction: str) -> str:
    d = (direction or "").strip().lower()
    if d == "bullish":
        return "bearish"
    if d == "bearish":
        return "bullish"
    return ""


def _excursion_from_window(
    ref: float,
    highest: float,
    lowest: float,
    favorable_dir: str,
) -> Tuple[float, float, bool, float]:
    """Return mfe, mae, zero_mae_flag, rr (nan if mae==0)."""
    fav = (favorable_dir or "").strip().lower()
    if fav not in ("bullish", "bearish") or not np.isfinite(ref):
        return float("nan"), float("nan"), False, float("nan")
    if not (np.isfinite(highest) and np.isfinite(lowest)):
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


def _load_parent() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    elig = pd.read_csv(SRC_HUB / "seed_24h_eligibility.csv")
    cands = pd.read_csv(SRC_HUB / "structure_candidates.csv")
    structs = pd.read_csv(SRC_HUB / "structure_excursion_outcomes.csv")
    contacts = pd.read_csv(SRC_HUB / "contact_reaction_outcomes.csv")
    return elig, cands, structs, contacts


def remap_ledgers(
    elig: pd.DataFrame,
    cands: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    seed_dir = elig.set_index("seed_id")["seed_direction"].to_dict()
    rows_s: List[Dict[str, Any]] = []
    rows_c: List[Dict[str, Any]] = []
    meta_rows: List[Dict[str, Any]] = []

    for _, cand in cands.iterrows():
        cid = cand["candidate_id"]
        sid = cand["seed_id"]
        sd = str(seed_dir.get(sid, "") or "").strip().lower()
        against = _opp(sd)
        with_bias = sd if sd in ("bullish", "bearish") else ""
        pattern = str(cand.get("pattern") or "")
        struct_fav = "bearish" if pattern.startswith("BEAR") else "bullish"
        vs = str(cand.get("one_minute_direction_vs_seed_direction") or "")

        st = structs[structs["candidate_id"] == cid]
        ct = contacts[contacts["candidate_id"] == cid]
        if st.empty or ct.empty:
            continue
        s = st.iloc[0]
        c = ct.iloc[0]

        meta_rows.append(
            {
                "candidate_id": cid,
                "seed_id": sid,
                "pattern": pattern,
                "seed_direction": sd,
                "measurement_favorable_dir": against,
                "measurement_mode": "AGAINST_SEED_BIAS",
                "structure_favorable_dir": struct_fav,
                "one_minute_direction_vs_seed_direction": vs,
                "structure_data_complete": bool(s.get("data_complete")),
                "contact_eligible": bool(c.get("contact_eligible")),
                "contact_data_complete": bool(c.get("data_complete")),
                "area_contact_classification": c.get("area_contact_classification")
                or s.get("area_contact_classification"),
                "calendar_block": cand.get("calendar_block"),
                "session_segment": cand.get("session_segment"),
            }
        )

        # Structure window remap
        s_ref = float(s["structure_reference_price"]) if pd.notna(s["structure_reference_price"]) else float("nan")
        s_hi = float(s["highest_high_in_window"]) if pd.notna(s["highest_high_in_window"]) else float("nan")
        s_lo = float(s["lowest_low_in_window"]) if pd.notna(s["lowest_low_in_window"]) else float("nan")
        mfe_a, mae_a, z_a, rr_a = _excursion_from_window(s_ref, s_hi, s_lo, against)
        mfe_w, mae_w, z_w, rr_w = _excursion_from_window(s_ref, s_hi, s_lo, with_bias)
        mfe_p, mae_p, z_p, rr_p = _excursion_from_window(s_ref, s_hi, s_lo, struct_fav)
        rows_s.append(
            {
                "candidate_id": cid,
                "evaluation_start": s.get("evaluation_start"),
                "structure_horizon_end": s.get("structure_horizon_end"),
                "structure_reference_price": s_ref,
                "highest_high_in_window": s_hi,
                "lowest_low_in_window": s_lo,
                "data_complete": bool(s.get("data_complete")),
                "gap_or_exclusion_reason": s.get("gap_or_exclusion_reason", ""),
                "seed_direction": sd,
                "favorable_dir_against_seed": against,
                "mfe_structure_ticks": mfe_a,
                "mae_structure_ticks": mae_a,
                "structure_excursion_rr": rr_a,
                "zero_mae_flag": z_a,
                "mfe_with_seed_ticks": mfe_w,
                "mae_with_seed_ticks": mae_w,
                "rr_with_seed": rr_w,
                "mfe_structure_bias_ticks": mfe_p,
                "mae_structure_bias_ticks": mae_p,
                "rr_structure_bias": rr_p,
            }
        )

        # Contact window remap
        c_ref = float(c["contact_reference_price"]) if pd.notna(c["contact_reference_price"]) else float("nan")
        c_hi = (
            float(c["highest_high_in_reaction_window"])
            if pd.notna(c.get("highest_high_in_reaction_window"))
            else float("nan")
        )
        c_lo = (
            float(c["lowest_low_in_reaction_window"])
            if pd.notna(c.get("lowest_low_in_reaction_window"))
            else float("nan")
        )
        cmfe_a, cmae_a, cz_a, crr_a = _excursion_from_window(c_ref, c_hi, c_lo, against)
        cmfe_w, cmae_w, cz_w, crr_w = _excursion_from_window(c_ref, c_hi, c_lo, with_bias)
        cmfe_p, cmae_p, cz_p, crr_p = _excursion_from_window(c_ref, c_hi, c_lo, struct_fav)
        rows_c.append(
            {
                "candidate_id": cid,
                "area_contact_classification": c.get("area_contact_classification"),
                "contact_eligible": bool(c.get("contact_eligible")),
                "no_contact_reason": c.get("no_contact_reason", ""),
                "first_contact_ts": c.get("first_contact_ts", ""),
                "contact_reference_price": c_ref,
                "reaction_horizon_end": c.get("reaction_horizon_end", ""),
                "highest_high_in_reaction_window": c_hi,
                "lowest_low_in_reaction_window": c_lo,
                "data_complete": bool(c.get("data_complete")),
                "gap_or_exclusion_reason": c.get("gap_or_exclusion_reason", ""),
                "path_order_label_structure_keyed": c.get("path_order_label", ""),
                "seed_direction": sd,
                "favorable_dir_against_seed": against,
                "mfe_contact_ticks": cmfe_a,
                "mae_contact_ticks": cmae_a,
                "contact_excursion_rr": crr_a,
                "zero_mae_flag": cz_a,
                "mfe_with_seed_ticks": cmfe_w,
                "mae_with_seed_ticks": cmae_w,
                "rr_with_seed": crr_w,
                "mfe_structure_bias_ticks": cmfe_p,
                "mae_structure_bias_ticks": cmae_p,
                "rr_structure_bias": crr_p,
            }
        )

    return pd.DataFrame(meta_rows), pd.DataFrame(rows_s), pd.DataFrame(rows_c)


def _interp(stats: Dict[str, Any]) -> str:
    mean_rr = stats["mean_excursion_rr"]
    if stats["record_count"] < 10:
        return "INSUFFICIENT_SAMPLE"
    if (
        mean_rr == mean_rr
        and mean_rr > 1.0
        and stats["mean_mfe_ticks"] > stats["mean_mae_ticks"]
    ):
        return "MEAN_MFE_GT_MEAN_MAE"
    return "MEAN_MFE_NOT_GT_MEAN_MAE"


def _zero_mae_series(mae: pd.Series) -> pd.Series:
    x = pd.to_numeric(mae, errors="coerce")
    return (x.fillna(0) <= 1e-12) & x.notna()


def build_aggregates(meta: pd.DataFrame, structs: pd.DataFrame, contacts: pd.DataFrame) -> pd.DataFrame:
    s = structs.add_prefix("s_")
    s = s.rename(columns={"s_candidate_id": "candidate_id"})
    c = contacts.add_prefix("c_")
    c = c.rename(columns={"c_candidate_id": "candidate_id"})
    m = meta.merge(s, on="candidate_id", how="left").merge(c, on="candidate_id", how="left")

    m["structure_ok"] = m["s_data_complete"].fillna(False).astype(bool)
    m["contact_ok"] = (
        m["c_contact_eligible"].fillna(False).astype(bool)
        & m["c_data_complete"].fillna(False).astype(bool)
    )

    out_rows: List[Dict[str, Any]] = []

    def add_structure(label: str, df: pd.DataFrame) -> None:
        stats = _excursion_stats(
            df["s_mfe_structure_ticks"],
            df["s_mae_structure_ticks"],
            df["s_structure_excursion_rr"],
            df["s_zero_mae_flag"],
            calendar_blocks=df["calendar_block"] if "calendar_block" in df.columns else None,
        )
        out_rows.append(
            {"population_label": label, **stats, "interpretation_status": _interp(stats)}
        )

    def add_contact(label: str, df: pd.DataFrame, mfe: str, mae: str, rr: str) -> None:
        stats = _excursion_stats(
            df[mfe],
            df[mae],
            df[rr],
            _zero_mae_series(df[mae]),
            path_labels=df["c_path_order_label_structure_keyed"]
            if "c_path_order_label_structure_keyed" in df.columns
            else None,
            calendar_blocks=df["calendar_block"] if "calendar_block" in df.columns else None,
        )
        out_rows.append(
            {"population_label": label, **stats, "interpretation_status": _interp(stats)}
        )

    add_structure("ALL_VALID_CANDIDATES_AGAINST_SEED", m[m["structure_ok"]])
    add_structure(
        "BEAR_VALID_CANDIDATES_AGAINST_SEED",
        m[m["structure_ok"] & m["pattern"].astype(str).str.startswith("BEAR")],
    )
    add_structure(
        "BULL_VALID_CANDIDATES_AGAINST_SEED",
        m[m["structure_ok"] & m["pattern"].astype(str).str.startswith("BULL")],
    )

    against = ("c_mfe_contact_ticks", "c_mae_contact_ticks", "c_contact_excursion_rr")
    add_contact("ALL_VALID_CONTACTS_AGAINST_SEED", m[m["contact_ok"]], *against)
    add_contact(
        "BEAR_VALID_CONTACTS_AGAINST_SEED",
        m[m["contact_ok"] & m["pattern"].astype(str).str.startswith("BEAR")],
        *against,
    )
    add_contact(
        "BULL_VALID_CONTACTS_AGAINST_SEED",
        m[m["contact_ok"] & m["pattern"].astype(str).str.startswith("BULL")],
        *against,
    )
    add_contact(
        "ALIGN_CONTACTS_AGAINST_SEED",
        m[
            m["contact_ok"]
            & (m["one_minute_direction_vs_seed_direction"] == "ALIGN_WITH_SEED_DIRECTION")
        ],
        *against,
    )
    add_contact(
        "OPPOSE_CONTACTS_AGAINST_SEED",
        m[
            m["contact_ok"]
            & (m["one_minute_direction_vs_seed_direction"] == "OPPOSE_SEED_DIRECTION")
        ],
        *against,
    )

    with_cols = ("c_mfe_with_seed_ticks", "c_mae_with_seed_ticks", "c_rr_with_seed")
    struct_cols = (
        "c_mfe_structure_bias_ticks",
        "c_mae_structure_bias_ticks",
        "c_rr_structure_bias",
    )
    add_contact("ALL_VALID_CONTACTS_WITH_SEED", m[m["contact_ok"]], *with_cols)
    add_contact("ALL_VALID_CONTACTS_STRUCTURE_BIAS", m[m["contact_ok"]], *struct_cols)
    add_contact(
        "BEAR_VALID_CONTACTS_WITH_SEED",
        m[m["contact_ok"] & m["pattern"].astype(str).str.startswith("BEAR")],
        *with_cols,
    )
    add_contact(
        "BULL_VALID_CONTACTS_WITH_SEED",
        m[m["contact_ok"] & m["pattern"].astype(str).str.startswith("BULL")],
        *with_cols,
    )
    add_contact(
        "BEAR_VALID_CONTACTS_STRUCTURE_BIAS",
        m[m["contact_ok"] & m["pattern"].astype(str).str.startswith("BEAR")],
        *struct_cols,
    )
    add_contact(
        "BULL_VALID_CONTACTS_STRUCTURE_BIAS",
        m[m["contact_ok"] & m["pattern"].astype(str).str.startswith("BULL")],
        *struct_cols,
    )

    return pd.DataFrame(out_rows)


def _row(agg: pd.DataFrame, label: str) -> Dict[str, Any]:
    if agg is None or not len(agg):
        return {}
    hit = agg[agg["population_label"] == label]
    if hit.empty:
        return {}
    return hit.iloc[0].to_dict()


def write_reports(hub: Path, meta: pd.DataFrame, structs: pd.DataFrame, contacts: pd.DataFrame, agg: pd.DataFrame) -> Dict[str, Any]:
    def g(label: str) -> Dict[str, Any]:
        return _row(agg, label)

    all_c = g("ALL_VALID_CONTACTS_AGAINST_SEED")
    bear_c = g("BEAR_VALID_CONTACTS_AGAINST_SEED")
    bull_c = g("BULL_VALID_CONTACTS_AGAINST_SEED")
    align_c = g("ALIGN_CONTACTS_AGAINST_SEED")
    oppose_c = g("OPPOSE_CONTACTS_AGAINST_SEED")
    with_all = g("ALL_VALID_CONTACTS_WITH_SEED")
    struct_all = g("ALL_VALID_CONTACTS_STRUCTURE_BIAS")

    def pass_q(row: Dict[str, Any]) -> bool:
        if not row or int(row.get("record_count") or 0) < 10:
            return False
        mfe = float(row.get("mean_mfe_ticks") or 0)
        mae = float(row.get("mean_mae_ticks") or 0)
        rr = float(row.get("mean_excursion_rr") or 0)
        return mfe > mae and rr > 1.0

    bear_pass = pass_q(bear_c)
    bull_pass = pass_q(bull_c)
    pooled_pass = pass_q(all_c)

    if bear_pass and bull_pass:
        decision = "BOTH_SIDES_ASYMMETRY_AGAINST_SEED"
        stance = "DESCRIPTIVE — against-seed contact asymmetry on both structure sides"
    elif bear_pass or bull_pass:
        decision = "ONE_SIDED_ASYMMETRY_AGAINST_SEED"
        stance = "ONE-SIDED DESCRIPTIVE ASYMMETRY ONLY (against seed bias)"
    elif pooled_pass:
        decision = "POOLED_ONLY_ASYMMETRY_AGAINST_SEED"
        stance = "POOLED DESCRIPTIVE ASYMMETRY ONLY (against seed bias)"
    else:
        decision = "NO_ASYMMETRY_AGAINST_SEED"
        stance = "DESCRIPTIVE ONLY — against-seed contact mean MFE/MAE asymmetry not supported"

    m = {
        "study_id": STUDY_ID,
        "parent_study": PARENT_STUDY,
        "measurement_mode": "AGAINST_SEED_BIAS",
        "candidates": int(len(meta)),
        "bear_candidates": int(meta["pattern"].astype(str).str.startswith("BEAR").sum()),
        "bull_candidates": int(meta["pattern"].astype(str).str.startswith("BULL").sum()),
        "bear_primary_question_pass": bear_pass,
        "bull_primary_question_pass": bull_pass,
        "pooled_primary_question_pass": pooled_pass,
        "decision": decision,
        "stance": stance,
        "all_contact": all_c,
        "bear_contact": bear_c,
        "bull_contact": bull_c,
        "align_contact": align_c,
        "oppose_contact": oppose_c,
        "with_seed_all_contact": with_all,
        "structure_bias_all_contact": struct_all,
    }

    lines = [
        "# NQ 4H WICK-REJECT → 24H 1M PROTECTED-AREA REACTION — AGAINST SEED BIAS",
        "",
        "STATUS: DESCRIPTIVE ONLY",
        "PARENT: %s" % PARENT_STUDY,
        "MEASUREMENT: favorable = opposite of 4h seed_direction (AGAINST_SEED_BIAS)",
        "EVENTS: frozen from parent (no re-selection)",
        "STANCE: %s" % stance,
        "DECISION: %s" % decision,
        "",
        "## Method",
        "- Same structure/contact windows and reference prices as V1.",
        "- Remap MFE/MAE so favorable excursion is **against** the 4h WICK_REJECT seed bias.",
        "- Structure pattern still defines the protected area / contact event.",
        "- Path-order labels remain structure-keyed (diagnostic only; not remapped).",
        "- Contrast rows: WITH_SEED and STRUCTURE_BIAS (parent definition).",
        "",
        "## Population",
        "- Candidates (from parent): %d (bear=%d bull=%d)"
        % (m["candidates"], m["bear_candidates"], m["bull_candidates"]),
        "- Align / oppose vs seed: %d / %d"
        % (
            int((meta["one_minute_direction_vs_seed_direction"] == "ALIGN_WITH_SEED_DIRECTION").sum()),
            int((meta["one_minute_direction_vs_seed_direction"] == "OPPOSE_SEED_DIRECTION").sum()),
        ),
        "",
        "## Primary question (contact reaction, against seed bias)",
        "- Bear structures mean(MFE)>mean(MAE) and mean RR>1: %s" % bear_pass,
        "- Bull structures mean(MFE)>mean(MAE) and mean RR>1: %s" % bull_pass,
        "- Pooled: %s" % pooled_pass,
        "",
        "## Contact excursions — AGAINST seed bias",
        "- All mean MFE / MAE / RR (n=%s): %s / %s / %s"
        % (
            all_c.get("record_count"),
            _fmt(all_c.get("mean_mfe_ticks"), 2),
            _fmt(all_c.get("mean_mae_ticks"), 2),
            _fmt(all_c.get("mean_excursion_rr"), 3),
        ),
        "- All median MFE / MAE / indiv RR: %s / %s / %s"
        % (
            _fmt(all_c.get("median_mfe_ticks"), 2),
            _fmt(all_c.get("median_mae_ticks"), 2),
            _fmt(all_c.get("median_excursion_rr"), 3),
        ),
        "- Bear mean MFE / MAE / RR (n=%s): %s / %s / %s"
        % (
            bear_c.get("record_count"),
            _fmt(bear_c.get("mean_mfe_ticks"), 2),
            _fmt(bear_c.get("mean_mae_ticks"), 2),
            _fmt(bear_c.get("mean_excursion_rr"), 3),
        ),
        "- Bull mean MFE / MAE / RR (n=%s): %s / %s / %s"
        % (
            bull_c.get("record_count"),
            _fmt(bull_c.get("mean_mfe_ticks"), 2),
            _fmt(bull_c.get("mean_mae_ticks"), 2),
            _fmt(bull_c.get("mean_excursion_rr"), 3),
        ),
        "- Align-with-seed structures mean RR (n=%s): %s"
        % (align_c.get("record_count"), _fmt(align_c.get("mean_excursion_rr"), 3)),
        "- Oppose-seed structures mean RR (n=%s): %s"
        % (oppose_c.get("record_count"), _fmt(oppose_c.get("mean_excursion_rr"), 3)),
        "",
        "## Contrast (same windows)",
        "- WITH seed bias pooled contact mean RR (n=%s): %s"
        % (with_all.get("record_count"), _fmt(with_all.get("mean_excursion_rr"), 3)),
        "- STRUCTURE bias (parent) pooled contact mean RR (n=%s): %s"
        % (struct_all.get("record_count"), _fmt(struct_all.get("mean_excursion_rr"), 3)),
        "",
        "## Disposition",
        "- DESCRIPTIVE ONLY — no entry/P&L/plugin.",
        "- Does not promote against-seed or with-seed filters.",
        "- Parent V1 hub remains the structure-bias measurement record.",
        "",
    ]
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email = (
        "potions: %s COMPLETE\n\n"
        "Hub: %s\n"
        "Parent: %s\n"
        "mode: AGAINST_SEED_BIAS (favorable = opp 4h seed)\n"
        "candidates: %d\n"
        "against_seed contact mean MFE/MAE/RR (n=%s): %s / %s / %s\n"
        "bear/bull against_seed RR (n=%s/%s): %s / %s\n"
        "with_seed / structure_bias pooled RR: %s / %s\n"
        "primary_q bear/bull: %s / %s\n"
        "decision: %s\n"
        "stance: %s\n\n"
        "DESCRIPTIVE ONLY — remapped from frozen V1 windows.\n"
        % (
            STUDY_ID,
            hub,
            PARENT_STUDY,
            m["candidates"],
            all_c.get("record_count"),
            _fmt(all_c.get("mean_mfe_ticks"), 2),
            _fmt(all_c.get("mean_mae_ticks"), 2),
            _fmt(all_c.get("mean_excursion_rr"), 3),
            bear_c.get("record_count"),
            bull_c.get("record_count"),
            _fmt(bear_c.get("mean_excursion_rr"), 3),
            _fmt(bull_c.get("mean_excursion_rr"), 3),
            _fmt(with_all.get("mean_excursion_rr"), 3),
            _fmt(struct_all.get("mean_excursion_rr"), 3),
            bear_pass,
            bull_pass,
            decision,
            stance,
        )
    )
    (hub / "EMAIL.txt").write_text(email, encoding="utf-8")

    flat = {
        k: v
        for k, v in m.items()
        if not isinstance(v, (dict, list, tuple))
    }
    for key in (
        "all_contact",
        "bear_contact",
        "bull_contact",
        "align_contact",
        "oppose_contact",
        "with_seed_all_contact",
        "structure_bias_all_contact",
    ):
        flat[key] = json.dumps(m.get(key), default=str)
    pd.DataFrame([flat]).to_csv(hub / "summary.csv", index=False)
    agg.to_csv(hub / "aggregate_excursion_summary.csv", index=False)
    (hub / "STATUS.md").write_text(
        "status: COMPLETE\nstance: %s\ndecision: %s\n" % (stance, decision),
        encoding="utf-8",
    )
    return m


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STUDY_ID)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    cfg = (
        "parent=%s\nmode=AGAINST_SEED_BIAS\nfavorable=opposite(seed_direction)\n"
        "events=frozen_parent_windows\n" % PARENT_STUDY
    )
    cfg_hash = hashlib.sha256(cfg.encode("utf-8")).hexdigest()[:16]
    (hub / "config_hash.txt").write_text(cfg_hash + "\n", encoding="utf-8")
    (hub / "CONFIG.md").write_text(
        "# CONFIG — %s\n\n%s\n" % (STUDY_ID, cfg),
        encoding="utf-8",
    )
    (hub / "MODEL_CONTRACT.yaml").write_text(
        "study_id: %s\nparent: %s\nmeasurement: against_seed_bias\n"
        "descriptive_only: true\nno_trade_model: true\n" % (STUDY_ID, PARENT_STUDY),
        encoding="utf-8",
    )

    rid = begin_run(
        run_class="pandas",
        variant_slug=STUDY_ID,
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={
            "descriptive_only": True,
            "config_hash": cfg_hash,
            "parent": PARENT_STUDY,
            "measurement_mode": "AGAINST_SEED_BIAS",
        },
    )

    try:
        if not (SRC_HUB / "structure_candidates.csv").exists():
            raise FileNotFoundError("Parent hub missing: %s" % SRC_HUB)

        if args.email:
            start = (
                "potions: %s STARTED\n\nHub: %s\n"
                "Remap V1 windows: favorable = against 4h seed bias.\n"
                % (STUDY_ID, hub)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: %s STARTED" % STUDY_ID, body=start)

        _progress(hub, "Loading parent ledgers from %s" % SRC_HUB)
        elig, cands, structs, contacts = _load_parent()
        _progress(
            hub,
            "Parent rows: elig=%d cands=%d structs=%d contacts=%d"
            % (len(elig), len(cands), len(structs), len(contacts)),
        )

        meta, s_out, c_out = remap_ledgers(elig, cands, structs, contacts)
        meta.to_csv(hub / "candidate_measurement_meta.csv", index=False)
        s_out.to_csv(hub / "structure_excursion_outcomes_against_seed.csv", index=False)
        c_out.to_csv(hub / "contact_reaction_outcomes_against_seed.csv", index=False)
        # also copy parent causality pointer
        (hub / "CAUSALITY_AUDIT.md").write_text(
            "# CAUSALITY_AUDIT — %s\n\n"
            "Inherited from parent `%s` (frozen events; measurement remap only).\n"
            "See parent CAUSALITY_AUDIT.md — parent status PASS required.\n"
            % (STUDY_ID, PARENT_STUDY),
            encoding="utf-8",
        )

        _progress(hub, "Building aggregates")
        agg = build_aggregates(meta, s_out, c_out)
        metrics = write_reports(hub, meta, s_out, c_out, agg)

        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "finished_at": datetime.now().isoformat(),
                    "decision": metrics["decision"],
                    "stance": metrics["stance"],
                    "config_hash": cfg_hash,
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
                "decision": metrics["decision"],
                "against_seed_contact_rr": (metrics.get("all_contact") or {}).get(
                    "mean_excursion_rr"
                ),
            },
        )
        _progress(hub, "DONE decision=%s" % metrics["decision"])
        return 0
    except Exception as e:
        err = traceback.format_exc()
        (hub / "CRASH.txt").write_text(err, encoding="utf-8")
        _progress(hub, "CRASH: %s" % e)
        fail_run(rid, error=str(e))
        if args.email:
            send_email(
                subject="potions: %s CRASHED" % STUDY_ID,
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
