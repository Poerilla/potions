"""ECU chart packs A–C for opposed-bias mirror audit V1.

Pack A: structure window — same path, original vs opposed labels.
Pack B: contact reaction window — descriptive inversion only.
Pack C: reconciliation contact sheets.

No reverse-trade arrows, entries, stops, targets, P&L, or recommendations.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_charts import (
    _fname,
    _plot_candles,
    _shade_area,
)
from .nq_wick_reject_range_seed_retest import _localize


def _safe(s: Any) -> str:
    return "".join(ch if str(ch).isalnum() or ch in "-_" else "_" for ch in str(s))


def _banner(study_id: str, cfg_hash: str, parent_hash: str, seed_id: str, cand_id: str, note: str) -> str:
    return (
        "study_id=%s  config_hash=%s  parent_hash=%s\n"
        "seed_id=%s  candidate_id=%s\n"
        "%s\n"
        "generated=%s"
        % (
            study_id,
            cfg_hash,
            parent_hash,
            seed_id,
            cand_id,
            note,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    )


def render_all(
    hub: Path,
    study_id: str,
    parent_hash: str,
    cfg_hash: str,
    data_version: str,
    data_session_policy: str,
    elig: pd.DataFrame,
    cands_all: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
    s_out: pd.DataFrame,
    c_out: pd.DataFrame,
    bars_1m: pd.DataFrame,
    smoke: bool = False,
    smoke_cap: int = 5,
) -> None:
    for sub in ("charts/pack_a", "charts/pack_b", "charts/pack_c"):
        (hub / sub).mkdir(parents=True, exist_ok=True)

    cands = cands_all[cands_all["candidate_status"] == "COMPLETED"].copy()
    s_by = (
        {r["candidate_id"]: r.to_dict() for _, r in s_out.iterrows()} if len(s_out) else {}
    )
    c_by = (
        {r["candidate_id"]: r.to_dict() for _, r in c_out.iterrows()} if len(c_out) else {}
    )
    rows = cands.to_dict(orient="records")
    if smoke:
        rows = rows[:smoke_cap]

    manifest: List[Dict[str, Any]] = []
    for cand in rows:
        cid = cand["candidate_id"]
        sid = cand["seed_id"]
        srow = s_by.get(cid) or {}
        crow = c_by.get(cid) or {}
        complete_label = _localize(pd.Timestamp(cand["structure_complete_at"])).strftime(
            "%Y-%m-%d_%H%MET"
        )
        try:
            path = _render_pack_a(
                hub, study_id, cfg_hash, parent_hash, cand, srow, bars_1m, complete_label
            )
            manifest.append({"pack": "A", "candidate_id": cid, "seed_id": sid, "path": str(path)})
        except Exception as exc:
            manifest.append(
                {"pack": "A", "candidate_id": cid, "seed_id": sid, "path": "", "err": str(exc)}
            )
        if crow and bool(crow.get("data_complete")):
            try:
                path = _render_pack_b(
                    hub, study_id, cfg_hash, parent_hash, cand, crow, bars_1m, complete_label
                )
                manifest.append(
                    {"pack": "B", "candidate_id": cid, "seed_id": sid, "path": str(path)}
                )
            except Exception as exc:
                manifest.append(
                    {"pack": "B", "candidate_id": cid, "seed_id": sid, "path": "", "err": str(exc)}
                )

    try:
        for path in _render_pack_c(
            hub, study_id, cfg_hash, parent_hash, cands, c_out, smoke, smoke_cap
        ):
            manifest.append({"pack": "C", "path": str(path)})
    except Exception as exc:
        manifest.append({"pack": "C", "path": "", "err": str(exc)})

    pd.DataFrame(manifest).to_csv(hub / "chart_manifest.csv", index=False)
    (hub / "CHART_SPEC.md").write_text(
        "# CHART_SPEC — opposed-bias mirror audit\n\n"
        "Pack A: structure mirror overlay.\n"
        "Pack B: contact mirror overlay.\n"
        "Pack C: reconciliation contact sheets.\n\n"
        "No entries/stops/targets/P&L/trade-R/reverse-trade arrows.\n",
        encoding="utf-8",
    )
    (hub / "INDEX.md").write_text(
        "# INDEX\n\nSee chart_manifest.csv (%d rows).\n" % len(manifest), encoding="utf-8"
    )


def _render_pack_a(hub, study_id, cfg_hash, parent_hash, cand, srow, bars_1m, complete_label):
    complete = _localize(pd.Timestamp(cand["structure_complete_at"]))
    end = complete + timedelta(minutes=180)
    win = bars_1m[(bars_1m.index >= complete - timedelta(minutes=5)) & (bars_1m.index < end)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, win, width_min=0.8)
    side = "BEAR" if str(cand.get("pattern", "")).startswith("BEAR") else "BULL"
    _shade_area(ax, side, float(cand["protected_pivot_price"]), float(cand["outer_area_edge"]))
    ref = float(srow.get("structure_reference_price") or cand.get("structure_reference_price"))
    ax.axhline(ref, color="#6b3fa0", lw=1.1, label="STRUCT REF (P4)")
    ax.axvline(complete.to_pydatetime(), color="black", lw=1.2, label="STRUCTURE COMPLETE")
    ax.axvline(end.to_pydatetime(), color="#555555", lw=1.0, ls="--", label="180m HORIZON")
    if pd.notna(srow.get("highest_high_in_window")):
        ax.axhline(float(srow["highest_high_in_window"]), color="#168a5a", lw=0.9, ls=":", label="WINDOW HIGH")
    if pd.notna(srow.get("lowest_low_in_window")):
        ax.axhline(float(srow["lowest_low_in_window"]), color="#c43d3d", lw=0.9, ls=":", label="WINDOW LOW")
    note = (
        "ORIGINAL bias %s  MFE=%s MAE=%s RR=%s\n"
        "OPPOSED  bias %s  MFE=%s MAE=%s RR=%s\n"
        "SAME PRICE PATH — FAVORABLE/ADVERSE LABELS MIRRORED"
        % (
            srow.get("original_bias_direction"),
            srow.get("original_mfe_ticks"),
            srow.get("original_mae_ticks"),
            srow.get("original_rr"),
            srow.get("opposed_bias_direction"),
            srow.get("opposed_mfe_ticks"),
            srow.get("opposed_mae_ticks"),
            srow.get("opposed_rr"),
        )
    )
    ax.text(0.01, 0.02, note, transform=ax.transAxes, fontsize=8, family="monospace", va="bottom")
    ax.legend(loc="upper left", fontsize=6)
    fig.suptitle(
        _banner(
            study_id,
            cfg_hash,
            parent_hash,
            cand["seed_id"],
            cand["candidate_id"],
            "SAME PRICE PATH — FAVORABLE/ADVERSE LABELS MIRRORED",
        ),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    out = hub / "charts" / "pack_a" / _fname(
        study_id, cand["seed_id"], cand["candidate_id"], complete_label, "A", "STRUCTURE_MIRROR"
    )
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_b(hub, study_id, cfg_hash, parent_hash, cand, crow, bars_1m, complete_label):
    contact = _localize(pd.Timestamp(crow["first_contact_ts"]))
    end = _localize(pd.Timestamp(crow["reaction_horizon_end"]))
    win = bars_1m[(bars_1m.index >= contact) & (bars_1m.index < end)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, win, width_min=0.8)
    side = "BEAR" if str(cand.get("pattern", "")).startswith("BEAR") else "BULL"
    _shade_area(ax, side, float(cand["protected_pivot_price"]), float(cand["outer_area_edge"]))
    ref = float(crow.get("contact_reference_price") or cand.get("protected_pivot_price"))
    ax.axhline(ref, color="#c9a227", lw=1.1, label="CONTACT REF (P3)")
    ax.axvline(contact.to_pydatetime(), color="#d35400", lw=1.2, label="FIRST CONTACT")
    ax.axvline(end.to_pydatetime(), color="#555555", lw=1.0, ls="--", label="60m HORIZON")
    if pd.notna(crow.get("highest_high_in_window")):
        ax.axhline(float(crow["highest_high_in_window"]), color="#168a5a", lw=0.9, ls=":", label="REACTION HIGH")
    if pd.notna(crow.get("lowest_low_in_window")):
        ax.axhline(float(crow["lowest_low_in_window"]), color="#c43d3d", lw=0.9, ls=":", label="REACTION LOW")
    note = (
        "ORIGINAL bias %s  MFE=%s MAE=%s RR=%s\n"
        "OPPOSED  bias %s  MFE=%s MAE=%s RR=%s\n"
        "DESCRIPTIVE INVERSION ONLY — NOT A REVERSE TRADE"
        % (
            crow.get("original_bias_direction"),
            crow.get("original_mfe_ticks"),
            crow.get("original_mae_ticks"),
            crow.get("original_rr"),
            crow.get("opposed_bias_direction"),
            crow.get("opposed_mfe_ticks"),
            crow.get("opposed_mae_ticks"),
            crow.get("opposed_rr"),
        )
    )
    ax.text(0.01, 0.02, note, transform=ax.transAxes, fontsize=8, family="monospace", va="bottom")
    ax.legend(loc="upper left", fontsize=6)
    fig.suptitle(
        _banner(
            study_id,
            cfg_hash,
            parent_hash,
            cand["seed_id"],
            cand["candidate_id"],
            "DESCRIPTIVE INVERSION ONLY — NOT A REVERSE TRADE",
        ),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    out = hub / "charts" / "pack_b" / _fname(
        study_id, cand["seed_id"], cand["candidate_id"], complete_label, "B", "CONTACT_MIRROR"
    )
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_c(hub, study_id, cfg_hash, parent_hash, cands, c_out, smoke, smoke_cap):
    if not len(c_out):
        return []
    merged = cands.merge(c_out, on="candidate_id", how="left", suffixes=("", "_opp"))
    if smoke:
        merged = merged.head(smoke_cap)
    outs: List[Path] = []
    for side, df_side in (
        ("BEAR", merged[merged["pattern"].astype(str).str.startswith("BEAR")]),
        ("BULL", merged[merged["pattern"].astype(str).str.startswith("BULL")]),
    ):
        if not len(df_side):
            continue
        depth_col = "parent_contact_classification"
        for depth, df_d in df_side.groupby(df_side[depth_col].fillna("NA").astype(str)):
            for complete_flag, df in df_d.groupby(df_d["data_complete"].fillna(False)):
                rows = df.to_dict(orient="records")
                if not rows:
                    continue
                n = len(rows)
                cols = 3
                rws = int(np.ceil(n / float(cols)))
                fig, axes = plt.subplots(rws, cols, figsize=(14, max(3.0, 2.2 * rws)))
                axes_arr = np.array(axes).reshape(-1)
                for i, ax in enumerate(axes_arr):
                    ax.axis("off")
                    if i >= n:
                        continue
                    r = rows[i]
                    txt = (
                        "seed=%s\ncand=%s\norig=%s opp=%s\n"
                        "orig_RR=%s opp_RR=%s\nswap=%s recip=%s\n"
                        "complete=%s depth=%s"
                        % (
                            r.get("seed_id"),
                            r.get("candidate_id"),
                            r.get("original_bias_direction"),
                            r.get("opposed_bias_direction"),
                            r.get("original_rr"),
                            r.get("opposed_rr"),
                            r.get("mfe_mae_swap_pass"),
                            r.get("rr_reciprocal_pass"),
                            r.get("data_complete"),
                            r.get("parent_contact_classification"),
                        )
                    )
                    ax.text(
                        0.02,
                        0.98,
                        txt,
                        transform=ax.transAxes,
                        va="top",
                        fontsize=7,
                        family="monospace",
                    )
                fig.suptitle(
                    "%s | %s | complete=%s | parent=%s"
                    % (side, depth, complete_flag, parent_hash),
                    fontsize=10,
                )
                fig.tight_layout(rect=[0, 0, 1, 0.95])
                fname = "%s__pack_c__%s__%s__complete_%s.png" % (
                    study_id,
                    side,
                    _safe(depth),
                    complete_flag,
                )
                out = hub / "charts" / "pack_c" / fname
                fig.savefig(out, dpi=110)
                plt.close(fig)
                outs.append(out)
    return outs
