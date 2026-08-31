"""Chart packs A–F for nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nq_wick_reject_range_seed_retest import _localize

NY = "America/New_York"


def _plot_candles(ax, df: pd.DataFrame, width_min: float = 0.8) -> None:
    if df is None or df.empty:
        return
    width_days = (width_min / (24.0 * 60.0)) * 0.8
    x = mdates.date2num(pd.DatetimeIndex([_localize(t).to_pydatetime() for t in df.index]))
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    ax.vlines(x, lows, highs, color=colors, linewidth=0.5, alpha=0.9, zorder=3)
    span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 0.0
    min_body = max(span * 0.001, 1e-6)
    for xi, o, c, color in zip(x, opens, closes, colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.2,
                alpha=0.85,
                zorder=4,
            )
        )


def _fname(study_id, seed_id, cand_id, complete_label, pack, outcome) -> str:
    safe = lambda s: "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))
    return "%s__%s__%s__%s__%s__%s.png" % (
        safe(study_id),
        safe(seed_id),
        safe(cand_id or "NONE"),
        safe(complete_label),
        safe(pack),
        safe(outcome or "NA"),
    )


def _meta_lines(study_id, cfg_hash, data_version, policy, seed_id, cand_id, outcome) -> List[str]:
    return [
        "study_id=%s  config_hash=%s  instrument=NQ" % (study_id, cfg_hash),
        "seed_id=%s  candidate_id=%s  tz=America/New_York" % (seed_id, cand_id or "NONE"),
        "source=%s  policy=%s" % (data_version, policy),
        "pivot=strict 1L/1R 1m  generated=%s  outcome=%s"
        % (datetime.now().strftime("%Y-%m-%d %H:%M"), outcome),
    ]


def _seed_h4_window(h4: pd.DataFrame, seed_ts: pd.Timestamp, expiry: pd.Timestamp) -> pd.DataFrame:
    seed_ts = _localize(seed_ts)
    expiry = _localize(expiry)
    if h4 is None or h4.empty:
        return h4
    idx = pd.DatetimeIndex([_localize(x) for x in h4.index])
    h = h4.copy()
    h.index = idx
    before = h[h.index < seed_ts].tail(2)
    mid = h[(h.index >= seed_ts) & (h.index <= expiry)]
    return pd.concat([before, mid]).sort_index()


def _shade_area(ax, pattern: str, prot: float, outer: float) -> None:
    lo = min(prot, outer)
    hi = max(prot, outer)
    ax.axhspan(lo, hi, color="#c9a227", alpha=0.22, zorder=1, label="PROTECTED AREA")
    ax.axhline(prot, color="#c9a227", lw=1.2, label="PROTECTED PIVOT")
    ax.axhline(outer, color="#c9a227", lw=0.8, ls="--", label="OUTER EDGE")


def render_all(
    hub: Path,
    study_id: str,
    data_version: str,
    cfg_hash: str,
    data_session_policy: str,
    elig: pd.DataFrame,
    pivots_df: pd.DataFrame,
    cands: pd.DataFrame,
    structs: pd.DataFrame,
    contacts: pd.DataFrame,
    exclusions: pd.DataFrame,
    bars_1m: pd.DataFrame,
    h4: pd.DataFrame,
    smoke: bool,
    smoke_cap: int,
    tick: float,
) -> None:
    manifest: List[Dict[str, Any]] = []
    included = elig[elig["included"] == True]  # noqa: E712
    cands_by_seed = {r["seed_id"]: r.to_dict() for _, r in cands.iterrows()} if len(cands) else {}
    struct_by_id = (
        {r["candidate_id"]: r.to_dict() for _, r in structs.iterrows()} if len(structs) else {}
    )
    contact_by_id = (
        {r["candidate_id"]: r.to_dict() for _, r in contacts.iterrows()} if len(contacts) else {}
    )
    excl_by_seed = (
        {r["seed_id"]: r.to_dict() for _, r in exclusions.iterrows()} if len(exclusions) else {}
    )

    seed_rows = included.to_dict(orient="records")
    cand_rows = cands.to_dict(orient="records") if len(cands) else []
    if smoke:
        seed_rows = seed_rows[:smoke_cap]
        cand_rows = cand_rows[:smoke_cap]

    for er_d in seed_rows:
        seed_id = er_d["seed_id"]
        cand = cands_by_seed.get(seed_id)
        excl = excl_by_seed.get(seed_id)
        outcome = "FORMED" if cand is not None else (
            str(excl["exclusion_reason"]) if excl is not None else "NO_CANDIDATE"
        )
        complete_label = "NA"
        if cand is not None:
            complete_label = _localize(pd.Timestamp(cand["structure_complete_at"])).strftime(
                "%Y-%m-%d_%H%MET"
            )
        try:
            path = _render_pack_a(
                hub, study_id, cfg_hash, data_version, data_session_policy,
                er_d, cand, excl, pivots_df, bars_1m, h4, outcome, complete_label, tick,
            )
            manifest.append({"pack": "A", "seed_id": seed_id, "path": str(path), "outcome": outcome})
        except Exception as exc:
            manifest.append({"pack": "A", "seed_id": seed_id, "path": "", "outcome": "ERR:%s" % exc})

        if cand is None:
            try:
                path = _render_pack_e(
                    hub, study_id, cfg_hash, data_version, data_session_policy,
                    er_d, excl, bars_1m, h4, outcome,
                )
                manifest.append({"pack": "E", "seed_id": seed_id, "path": str(path), "outcome": outcome})
            except Exception as exc:
                manifest.append({"pack": "E", "seed_id": seed_id, "path": "", "outcome": "ERR:%s" % exc})

    for c in cand_rows:
        o = struct_by_id.get(c["candidate_id"], {})
        t = contact_by_id.get(c["candidate_id"], {})
        complete_label = _localize(pd.Timestamp(c["structure_complete_at"])).strftime(
            "%Y-%m-%d_%H%MET"
        )
        depth = str(o.get("area_contact_classification", "NA")) if o else "NA"
        try:
            path = _render_pack_b(
                hub, study_id, cfg_hash, data_version, data_session_policy,
                c, bars_1m, tick, complete_label, depth,
            )
            manifest.append(
                {"pack": "B", "candidate_id": c["candidate_id"], "path": str(path), "outcome": depth}
            )
        except Exception as exc:
            manifest.append(
                {"pack": "B", "candidate_id": c["candidate_id"], "path": "", "outcome": "ERR:%s" % exc}
            )
        try:
            path = _render_pack_c(
                hub, study_id, cfg_hash, data_version, data_session_policy,
                c, o, bars_1m, tick, complete_label, depth,
            )
            manifest.append(
                {"pack": "C", "candidate_id": c["candidate_id"], "path": str(path), "outcome": depth}
            )
        except Exception as exc:
            manifest.append(
                {"pack": "C", "candidate_id": c["candidate_id"], "path": "", "outcome": "ERR:%s" % exc}
            )
        if t and bool(t.get("contact_eligible")) and bool(t.get("data_complete")):
            tlab = str(t.get("path_order_label", "NA"))
            try:
                path = _render_pack_d(
                    hub, study_id, cfg_hash, data_version, data_session_policy,
                    c, t, bars_1m, tick, complete_label, tlab,
                )
                manifest.append(
                    {"pack": "D", "candidate_id": c["candidate_id"], "path": str(path), "outcome": tlab}
                )
            except Exception as exc:
                manifest.append(
                    {
                        "pack": "D",
                        "candidate_id": c["candidate_id"],
                        "path": "",
                        "outcome": "ERR:%s" % exc,
                    }
                )

    try:
        path = _render_pack_f(hub, study_id, cfg_hash, cands, structs, contacts, smoke, smoke_cap)
        manifest.append({"pack": "F", "path": str(path), "outcome": "CONTACT_SHEET"})
    except Exception as exc:
        manifest.append({"pack": "F", "path": "", "outcome": "ERR:%s" % exc})

    pd.DataFrame(manifest).to_csv(hub / "chart_manifest.csv", index=False)
    (hub / "CHART_SPEC.md").write_text(
        "# CHART_SPEC\n\nPacks A–F. Protected AREA shaded. No entries/stops/targets/P&L.\n",
        encoding="utf-8",
    )
    (hub / "INDEX.md").write_text(
        "# INDEX\n\nSee chart_manifest.csv (%d rows).\n" % len(manifest), encoding="utf-8"
    )


def _render_pack_a(
    hub, study_id, cfg_hash, data_version, policy, er, cand, excl, pivots_df, bars_1m, h4, outcome, complete_label, tick
):
    seed_id = er["seed_id"]
    seed_ts = _localize(pd.Timestamp(er["seed_ts"]))
    avail = _localize(pd.Timestamp(er["seed_available_at"]))
    exp = _localize(pd.Timestamp(er["seed_expiry"]))
    hi, lo = float(er["seed_high"]), float(er["seed_low"])
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [1, 1.4]})
    ax4, ax1 = axes
    h4w = _seed_h4_window(h4, seed_ts, exp)
    _plot_candles(ax4, h4w, width_min=200)
    ax4.axhline(hi, color="#5b7c99", lw=1.2, label="SEED HIGH")
    ax4.axhline(lo, color="#5b7c99", lw=1.2, label="SEED LOW")
    ax4.axhspan(lo, hi, color="#5b7c99", alpha=0.15)
    ax4.axvline(seed_ts.to_pydatetime(), color="black", lw=1.0)
    ax4.set_ylabel("4H")
    ax4.legend(loc="upper left", fontsize=7)

    if cand is not None:
        complete = _localize(pd.Timestamp(cand["structure_complete_at"]))
        w0 = avail - timedelta(minutes=30)
        w1 = complete + timedelta(minutes=30)
        win = bars_1m[(bars_1m.index >= w0) & (bars_1m.index < w1)]
        _plot_candles(ax1, win, width_min=0.8)
        for key, color in (("p1_ts", "#1f4e79"), ("p2_ts", "#1f4e79"), ("p3_ts", "#c9a227"), ("p4_ts", "#6b3fa0")):
            if cand.get(key):
                ax1.axvline(_localize(pd.Timestamp(cand[key])).to_pydatetime(), color=color, lw=0.9)
        _shade_area(
            ax1,
            "BEAR" if str(cand["pattern"]).startswith("BEAR") else "BULL",
            float(cand["protected_pivot_price"]),
            float(cand["outer_area_edge"]),
        )
        ax1.axvline(complete.to_pydatetime(), color="black", lw=1.2, label="STRUCTURE COMPLETE")
    else:
        win = bars_1m[(bars_1m.index >= avail) & (bars_1m.index < min(exp, avail + timedelta(hours=6)))]
        _plot_candles(ax1, win, width_min=0.8)
        ax1.text(0.02, 0.95, outcome, transform=ax1.transAxes, fontsize=8, va="top")

    ax1.set_ylabel("1M")
    ax1.legend(loc="upper left", fontsize=6)
    fig.suptitle(
        "\n".join(_meta_lines(study_id, cfg_hash, data_version, policy, seed_id, cand["candidate_id"] if cand else "", outcome)),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    out = hub / "charts" / "pack_a" / _fname(study_id, seed_id, cand["candidate_id"] if cand else "NONE", complete_label, "A", outcome)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_b(hub, study_id, cfg_hash, data_version, policy, c, bars_1m, tick, complete_label, outcome):
    complete = _localize(pd.Timestamp(c["structure_complete_at"]))
    p1 = _localize(pd.Timestamp(c["p1_bar_open_ts"]))
    w0 = p1 - timedelta(minutes=10)
    w1 = complete + timedelta(minutes=5)
    win = bars_1m[(bars_1m.index >= w0) & (bars_1m.index < w1)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, win, width_min=0.8)
    for key, color, lab in (
        ("p1_ts", "#1f4e79", "P1"),
        ("p2_ts", "#2e7d32", "P2"),
        ("p3_ts", "#c9a227", "P3"),
        ("p4_ts", "#6b3fa0", "P4"),
    ):
        ts = _localize(pd.Timestamp(c[key]))
        ax.axvline(ts.to_pydatetime(), color=color, lw=1.0, label=lab)
    _shade_area(
        ax,
        "BEAR" if str(c["pattern"]).startswith("BEAR") else "BULL",
        float(c["protected_pivot_price"]),
        float(c["outer_area_edge"]),
    )
    ax.axhline(float(c["break_level"]), color="#888888", lw=0.8, ls=":", label="BREAK LEVEL")
    ax.legend(loc="upper left", fontsize=6)
    fig.suptitle(
        "\n".join(_meta_lines(study_id, cfg_hash, data_version, policy, c["seed_id"], c["candidate_id"], outcome)),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    out = hub / "charts" / "pack_b" / _fname(study_id, c["seed_id"], c["candidate_id"], complete_label, "B", outcome)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_c(hub, study_id, cfg_hash, data_version, policy, c, o, bars_1m, tick, complete_label, outcome):
    complete = _localize(pd.Timestamp(c["structure_complete_at"]))
    end = complete + timedelta(minutes=180)
    win = bars_1m[(bars_1m.index >= complete) & (bars_1m.index < end)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, win, width_min=0.8)
    _shade_area(
        ax,
        "BEAR" if str(c["pattern"]).startswith("BEAR") else "BULL",
        float(c["protected_pivot_price"]),
        float(c["outer_area_edge"]),
    )
    ax.axhline(float(c["structure_reference_price"]), color="#6b3fa0", lw=1.0, label="STRUCT REF (P4)")
    if o.get("first_contact_ts"):
        ax.axvline(
            _localize(pd.Timestamp(o["first_contact_ts"])).to_pydatetime(),
            color="#d35400",
            lw=1.2,
            label="FIRST AREA CONTACT",
        )
    note = "MFE=%s MAE=%s RR=%s depth=%s" % (
        o.get("mfe_structure_ticks"),
        o.get("mae_structure_ticks"),
        o.get("structure_excursion_rr"),
        o.get("area_contact_classification"),
    )
    ax.text(0.01, 0.02, note, transform=ax.transAxes, fontsize=8, family="monospace")
    ax.legend(loc="upper left", fontsize=6)
    fig.suptitle(
        "\n".join(_meta_lines(study_id, cfg_hash, data_version, policy, c["seed_id"], c["candidate_id"], outcome)),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    out = hub / "charts" / "pack_c" / _fname(study_id, c["seed_id"], c["candidate_id"], complete_label, "C", outcome)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_d(hub, study_id, cfg_hash, data_version, policy, c, t, bars_1m, tick, complete_label, outcome):
    contact = _localize(pd.Timestamp(t["first_contact_ts"]))
    end = _localize(pd.Timestamp(t["reaction_horizon_end"]))
    win = bars_1m[(bars_1m.index >= contact) & (bars_1m.index < end)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, win, width_min=0.8)
    _shade_area(
        ax,
        "BEAR" if str(c["pattern"]).startswith("BEAR") else "BULL",
        float(c["protected_pivot_price"]),
        float(c["outer_area_edge"]),
    )
    ax.axhline(float(t["favorable_response_threshold"]), color="#168a5a", lw=1.0, ls="--", label="FAV RESPONSE")
    note = "MFE=%s MAE=%s RR=%s path=%s" % (
        t.get("mfe_contact_ticks"),
        t.get("mae_contact_ticks"),
        t.get("contact_excursion_rr"),
        t.get("path_order_label"),
    )
    ax.text(0.01, 0.02, note, transform=ax.transAxes, fontsize=8, family="monospace")
    ax.legend(loc="upper left", fontsize=6)
    fig.suptitle(
        "\n".join(_meta_lines(study_id, cfg_hash, data_version, policy, c["seed_id"], c["candidate_id"], outcome)),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    out = hub / "charts" / "pack_d" / _fname(study_id, c["seed_id"], c["candidate_id"], complete_label, "D", outcome)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_e(hub, study_id, cfg_hash, data_version, policy, er, excl, bars_1m, h4, outcome):
    seed_id = er["seed_id"]
    avail = _localize(pd.Timestamp(er["seed_available_at"]))
    exp = _localize(pd.Timestamp(er["seed_expiry"]))
    fig, ax = plt.subplots(figsize=(14, 5))
    win = bars_1m[(bars_1m.index >= avail) & (bars_1m.index < min(exp, avail + timedelta(hours=8)))]
    _plot_candles(ax, win, width_min=0.8)
    ax.text(0.02, 0.95, "EXCLUDED: %s" % outcome, transform=ax.transAxes, fontsize=9, va="top")
    fig.suptitle(
        "\n".join(_meta_lines(study_id, cfg_hash, data_version, policy, seed_id, "", outcome)),
        fontsize=7,
        family="monospace",
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    out = hub / "charts" / "pack_e" / _fname(study_id, seed_id, "NONE", "NA", "E", outcome)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_f(hub, study_id, cfg_hash, cands, structs, contacts, smoke, smoke_cap):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    merged = cands.merge(structs, on="candidate_id", how="left").merge(
        contacts, on="candidate_id", how="left", suffixes=("_s", "_c")
    ) if len(cands) else pd.DataFrame()
    if smoke and len(merged):
        merged = merged.head(smoke_cap)

    ax0, ax1 = axes
    if len(merged) and "mfe_structure_ticks" in merged.columns:
        for pref, color in (("BEAR", "#c43d3d"), ("BULL", "#168a5a")):
            sub = merged[merged["pattern"].str.startswith(pref)]
            if len(sub):
                ax0.scatter(
                    sub["mae_structure_ticks"],
                    sub["mfe_structure_ticks"],
                    s=28,
                    alpha=0.7,
                    c=color,
                    label=pref,
                )
        ax0.set_xlabel("MAE structure (ticks)")
        ax0.set_ylabel("MFE structure (ticks)")
        ax0.plot([0, 1], [0, 1], transform=ax0.transAxes, ls="--", color="#999", lw=0.8)
        ax0.legend(fontsize=7)
        ax0.set_title("Structure excursion")

    if len(merged) and "mfe_contact_ticks" in merged.columns:
        ok = merged[merged["mfe_contact_ticks"].notna()]
        for pref, color in (("BEAR", "#c43d3d"), ("BULL", "#168a5a")):
            sub = ok[ok["pattern"].str.startswith(pref)]
            if len(sub):
                ax1.scatter(
                    sub["mae_contact_ticks"],
                    sub["mfe_contact_ticks"],
                    s=28,
                    alpha=0.7,
                    c=color,
                    label=pref,
                )
        ax1.set_xlabel("MAE contact (ticks)")
        ax1.set_ylabel("MFE contact (ticks)")
        ax1.legend(fontsize=7)
        ax1.set_title("Contact reaction excursion")

    fig.suptitle("%s contact sheet  hash=%s" % (study_id, cfg_hash), fontsize=9)
    fig.tight_layout()
    out = hub / "charts" / "pack_f" / ("%s__contact_sheet.png" % study_id)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out
