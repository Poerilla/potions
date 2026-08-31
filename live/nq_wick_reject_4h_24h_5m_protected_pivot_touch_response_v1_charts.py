"""ECU chart packs A–F for nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1."""

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


def _plot_candles(ax, df: pd.DataFrame, width_min: float = 4.0) -> None:
    if df is None or df.empty:
        return
    width_days = (width_min / (24.0 * 60.0)) * 0.8
    x = mdates.date2num(pd.DatetimeIndex([_localize(t).to_pydatetime() for t in df.index]))
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    ax.vlines(x, lows, highs, color=colors, linewidth=0.6, alpha=0.9, zorder=3)
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


def _fname(
    study_id: str,
    seed_id: str,
    cand_id: str,
    complete_label: str,
    pack: str,
    outcome: str,
) -> str:
    safe = lambda s: "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))
    return "%s__%s__%s__%s__%s__%s.png" % (
        safe(study_id),
        safe(seed_id),
        safe(cand_id or "NONE"),
        safe(complete_label),
        safe(pack),
        safe(outcome or "NA"),
    )


def _header(ax, lines: List[str]) -> None:
    ax.set_title("\n".join(lines), fontsize=7, loc="left", family="monospace")


def _meta_lines(
    study_id: str,
    cfg_hash: str,
    data_version: str,
    policy: str,
    seed_id: str,
    cand_id: str,
    outcome: str,
) -> List[str]:
    return [
        "study_id=%s  config_hash=%s  instrument=NQ" % (study_id, cfg_hash),
        "seed_id=%s  candidate_id=%s  tz=America/New_York" % (seed_id, cand_id or "NONE"),
        "source=%s  policy=%s" % (data_version, policy),
        "pivot=strict 1L/1R 5m  generated=%s  outcome=%s"
        % (datetime.now().strftime("%Y-%m-%d %H:%M"), outcome),
    ]


def render_all(
    hub: Path,
    study_id: str,
    data_version: str,
    cfg_hash: str,
    data_session_policy: str,
    elig: pd.DataFrame,
    pivots_df: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
    touches: pd.DataFrame,
    exclusions: pd.DataFrame,
    bars_5m: pd.DataFrame,
    h4: pd.DataFrame,
    smoke: bool,
    smoke_cap: int,
    tick: float,
) -> None:
    manifest: List[Dict[str, Any]] = []
    included = elig[elig["included"] == True]  # noqa: E712
    cands_by_seed = (
        {r["seed_id"]: r.to_dict() for _, r in cands.iterrows()} if len(cands) else {}
    )
    outs_by_id = (
        {r["candidate_id"]: r.to_dict() for _, r in outs.iterrows()} if len(outs) else {}
    )
    touch_by_id = (
        {r["candidate_id"]: r.to_dict() for _, r in touches.iterrows()} if len(touches) else {}
    )
    excl_by_seed = (
        {r["seed_id"]: r.to_dict() for _, r in exclusions.iterrows()} if len(exclusions) else {}
    )

    seed_rows = included.to_dict(orient="records")
    cand_rows = cands.to_dict(orient="records") if len(cands) else []
    if smoke:
        seed_rows = seed_rows[:smoke_cap]
        cand_rows = cand_rows[:smoke_cap]

    # Pack A + E: per eligible seed
    for er_d in seed_rows:
        seed_id = er_d["seed_id"]
        cand = cands_by_seed.get(seed_id)
        excl = excl_by_seed.get(seed_id)
        outcome = "FORMED"
        if cand is None:
            outcome = str(excl["exclusion_reason"]) if excl is not None else "NO_CANDIDATE"
        complete_label = "NA"
        if cand is not None:
            complete_label = _localize(pd.Timestamp(cand["structure_complete_at"])).strftime(
                "%Y-%m-%d_%H%MET"
            )
        try:
            path = _render_pack_a(
                hub,
                study_id,
                cfg_hash,
                data_version,
                data_session_policy,
                er_d,
                cand,
                excl,
                pivots_df,
                bars_5m,
                h4,
                outcome,
                complete_label,
                tick,
            )
            manifest.append({"pack": "A", "seed_id": seed_id, "path": str(path), "outcome": outcome})
        except Exception as exc:
            manifest.append({"pack": "A", "seed_id": seed_id, "path": "", "outcome": "ERR:%s" % exc})

        if cand is None:
            try:
                path = _render_pack_e(
                    hub,
                    study_id,
                    cfg_hash,
                    data_version,
                    data_session_policy,
                    er_d,
                    excl,
                    pivots_df,
                    bars_5m,
                    h4,
                    outcome,
                )
                manifest.append(
                    {"pack": "E", "seed_id": seed_id, "path": str(path), "outcome": outcome}
                )
            except Exception as exc:
                manifest.append(
                    {"pack": "E", "seed_id": seed_id, "path": "", "outcome": "ERR:%s" % exc}
                )

    # Packs B, C, D per candidate
    for c in cand_rows:
        o = outs_by_id.get(c["candidate_id"], {})
        t = touch_by_id.get(c["candidate_id"], {})
        complete_label = _localize(pd.Timestamp(c["structure_complete_at"])).strftime(
            "%Y-%m-%d_%H%MET"
        )
        primary = str(o.get("primary_outcome_label", "NA")) if len(o) else "NA"
        try:
            path = _render_pack_b(
                hub, study_id, cfg_hash, data_version, data_session_policy, c, bars_5m, tick, complete_label, primary
            )
            manifest.append(
                {"pack": "B", "candidate_id": c["candidate_id"], "path": str(path), "outcome": primary}
            )
        except Exception as exc:
            manifest.append(
                {"pack": "B", "candidate_id": c["candidate_id"], "path": "", "outcome": "ERR:%s" % exc}
            )
        try:
            path = _render_pack_c(
                hub, study_id, cfg_hash, data_version, data_session_policy, c, o, bars_5m, tick, complete_label, primary
            )
            manifest.append(
                {"pack": "C", "candidate_id": c["candidate_id"], "path": str(path), "outcome": primary}
            )
        except Exception as exc:
            manifest.append(
                {"pack": "C", "candidate_id": c["candidate_id"], "path": "", "outcome": "ERR:%s" % exc}
            )
        if t and bool(t.get("touch_eligible")):
            tlab = str(t.get("touch_response_outcome_label", "NA"))
            try:
                path = _render_pack_d(
                    hub,
                    study_id,
                    cfg_hash,
                    data_version,
                    data_session_policy,
                    c,
                    t,
                    bars_5m,
                    tick,
                    complete_label,
                    tlab,
                )
                manifest.append(
                    {
                        "pack": "D",
                        "candidate_id": c["candidate_id"],
                        "path": str(path),
                        "outcome": tlab,
                    }
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

    # Pack F contact sheet
    try:
        path = _render_pack_f(hub, study_id, cfg_hash, cands, outs, touches, smoke, smoke_cap)
        manifest.append({"pack": "F", "path": str(path), "outcome": "CONTACT_SHEET"})
    except Exception as exc:
        manifest.append({"pack": "F", "path": "", "outcome": "ERR:%s" % exc})

    pd.DataFrame(manifest).to_csv(hub / "chart_manifest.csv", index=False)
    (hub / "CHART_SPEC.md").write_text(
        "# CHART_SPEC\n\nPacks A–F per study plan. No entries/stops/targets/P&L.\n",
        encoding="utf-8",
    )
    (hub / "INDEX.md").write_text(
        "# INDEX\n\nSee chart_manifest.csv (%d rows).\n" % len(manifest), encoding="utf-8"
    )


def _seed_h4_window(h4: pd.DataFrame, seed_ts: pd.Timestamp, expiry: pd.Timestamp) -> pd.DataFrame:
    seed_ts = _localize(seed_ts)
    expiry = _localize(expiry)
    if h4 is None or h4.empty:
        return h4
    idx = pd.DatetimeIndex([_localize(x) for x in h4.index])
    h = h4.copy()
    h.index = idx
    # two bars before seed
    before = h[h.index < seed_ts].tail(2)
    mid = h[(h.index >= seed_ts) & (h.index <= expiry)]
    return pd.concat([before, mid]).sort_index()


def _render_pack_a(
    hub, study_id, cfg_hash, data_version, policy, er, cand, excl, pivots_df, bars_5m, h4, outcome, complete_label, tick
):
    seed_id = er["seed_id"]
    seed_ts = _localize(pd.Timestamp(er["seed_ts"]))
    avail = _localize(pd.Timestamp(er["seed_available_at"]))
    exp = _localize(pd.Timestamp(er["seed_expiry"]))
    hi, lo = float(er["seed_high"]), float(er["seed_low"])
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [1, 1.4]})
    ax4, ax5 = axes
    h4w = _seed_h4_window(h4, seed_ts, exp)
    _plot_candles(ax4, h4w, width_min=200)
    ax4.axhline(hi, color="#5b7c99", lw=1.2, label="SEED HIGH")
    ax4.axhline(lo, color="#5b7c99", lw=1.2, label="SEED LOW")
    ax4.axhspan(lo, hi, color="#5b7c99", alpha=0.15)
    ax4.axvline(seed_ts.to_pydatetime(), color="black", lw=1.0)
    ax4.set_ylabel("4h")
    ax4.legend(loc="upper left", fontsize=7)

    if cand is not None:
        complete = _localize(pd.Timestamp(cand["structure_complete_at"]))
        t0 = complete - pd.Timedelta(hours=3)
        t1 = complete + pd.Timedelta(minutes=180)
        w5 = bars_5m[(bars_5m.index >= t0) & (bars_5m.index < t1)]
        _plot_candles(ax5, w5, width_min=4)
        ax5.axvline(avail.to_pydatetime(), color="black", lw=1.0, label="SEED AVAILABLE")
        ax5.axvline(complete.to_pydatetime(), color="#333", lw=1.2, label="STRUCTURE AVAILABLE")
        for lab, key, color in (
            ("P1", "p1_bar_open_ts", "#d35400"),
            ("P2", "p2_bar_open_ts", "#d35400"),
            ("P3", "p3_bar_open_ts", "#1a1a1a"),
            ("P4", "p4_bar_open_ts", "#168a5a"),
        ):
            ts = _localize(pd.Timestamp(cand[key]))
            px = float(cand["p1_price" if lab == "P1" else "p2_price" if lab == "P2" else "p3_price" if lab == "P3" else "p4_price"])
            ax5.scatter([ts.to_pydatetime()], [px], s=40, zorder=6, color=color)
            ax5.annotate(lab, (ts.to_pydatetime(), px), fontsize=7)
        ax5.axhline(float(cand["protected_price"]), color="#111", lw=1.5)
    else:
        t0 = avail
        t1 = min(exp, avail + pd.Timedelta(hours=12))
        w5 = bars_5m[(bars_5m.index >= t0) & (bars_5m.index < t1)]
        _plot_candles(ax5, w5, width_min=4)
        ax5.axvline(avail.to_pydatetime(), color="black", lw=1.0, label="SEED AVAILABLE")
        ax5.text(
            0.01,
            0.98,
            outcome,
            transform=ax5.transAxes,
            va="top",
            fontsize=9,
            color="#555",
            fontweight="bold",
        )
    ax5.set_ylabel("5m")
    ax5.legend(loc="upper left", fontsize=7)
    cand_id = cand["candidate_id"] if cand is not None else "NONE"
    _header(
        ax4,
        _meta_lines(study_id, cfg_hash, data_version, policy, seed_id, cand_id, outcome)
        + [
            "seed_width=%.2f (%.0f ticks) dir=%s width_atr=%s pen_atr=%s"
            % (
                float(er["seed_width"]),
                float(er["seed_width"]) / tick,
                er.get("seed_direction", ""),
                er.get("range_width_atr", ""),
                er.get("penetration_atr", ""),
            )
        ],
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    fname = _fname(study_id, seed_id, cand_id, complete_label, "context", outcome)
    path = hub / "charts" / "pack_a" / fname
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _render_pack_e(
    hub, study_id, cfg_hash, data_version, policy, er, excl, pivots_df, bars_5m, h4, outcome
):
    seed_id = er["seed_id"]
    avail = _localize(pd.Timestamp(er["seed_available_at"]))
    exp = _localize(pd.Timestamp(er["seed_expiry"]))
    hi, lo = float(er["seed_high"]), float(er["seed_low"])
    fig, ax = plt.subplots(figsize=(14, 6))
    t1 = min(exp, avail + pd.Timedelta(hours=24))
    w5 = bars_5m[(bars_5m.index >= avail) & (bars_5m.index < t1)]
    _plot_candles(ax, w5, width_min=4)
    ax.axhline(hi, color="#5b7c99", lw=1)
    ax.axhline(lo, color="#5b7c99", lw=1)
    ax.axvline(avail.to_pydatetime(), color="black", lw=1)
    if pivots_df is not None and len(pivots_df):
        pv = pivots_df[pivots_df["seed_id"] == seed_id]
        for _, p in pv.iterrows():
            ts = _localize(pd.Timestamp(p["pivot_ts"]))
            if ts > t1:
                continue
            ax.scatter(
                [ts.to_pydatetime()],
                [float(p["pivot_price"])],
                s=18,
                color="#888",
                zorder=5,
            )
    banner = outcome
    if excl is not None and excl.get("near_miss"):
        banner = "%s | %s" % (outcome, excl.get("near_miss"))
    ax.text(0.01, 0.98, banner, transform=ax.transAxes, va="top", fontsize=9, fontweight="bold")
    _header(ax, _meta_lines(study_id, cfg_hash, data_version, policy, seed_id, "NONE", outcome))
    fig.autofmt_xdate()
    fig.tight_layout()
    fname = _fname(study_id, seed_id, "NONE", "NA", "audit", outcome)
    path = hub / "charts" / "pack_e" / fname
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _render_pack_b(
    hub, study_id, cfg_hash, data_version, policy, c, bars_5m, tick, complete_label, primary
):
    complete = _localize(pd.Timestamp(c["structure_complete_at"]))
    p1o = _localize(pd.Timestamp(c["p1_bar_open_ts"]))
    t0 = p1o - pd.Timedelta(minutes=30)
    t1 = complete + pd.Timedelta(minutes=180)
    w = bars_5m[(bars_5m.index >= t0) & (bars_5m.index < t1)]
    fig, ax = plt.subplots(figsize=(14, 7))
    _plot_candles(ax, w, width_min=4)
    color = "#c43d3d" if str(c["pattern"]).startswith("BEAR") else "#168a5a"
    xs, ys = [], []
    for lab, ots, px in (
        ("P1", c["p1_bar_open_ts"], c["p1_price"]),
        ("P2", c["p2_bar_open_ts"], c["p2_price"]),
        ("P3", c["p3_bar_open_ts"], c["p3_price"]),
        ("P4", c["p4_bar_open_ts"], c["p4_price"]),
    ):
        ts = _localize(pd.Timestamp(ots)).to_pydatetime()
        xs.append(ts)
        ys.append(float(px))
        ax.scatter([ts], [float(px)], s=50, color=color, zorder=6)
        ax.annotate(lab, (ts, float(px)), fontsize=8)
    ax.plot(xs, ys, color=color, lw=1.2, alpha=0.8)
    ax.axvline(complete.to_pydatetime(), color="#333", lw=1.2, label="STRUCTURE AVAILABLE")
    ax.axhline(float(c["protected_price"]), color="#111", lw=2.0, label="PROTECTED")
    ax.axhline(float(c["failure_threshold"]), color="#111", lw=1.0, ls="--", label="FAIL+1tick")
    ax.axhline(float(c["break_level"]), color="#666", lw=1.0, label="BREAK")
    ax.legend(loc="upper left", fontsize=7)
    _header(
        ax,
        _meta_lines(study_id, cfg_hash, data_version, policy, c["seed_id"], c["candidate_id"], primary)
        + [
            "pattern=%s seg=%s ctx=%s vs_seed=%s break_dist=%s resp_dist=%s seq_min=%s"
            % (
                c["pattern"],
                c.get("session_segment", ""),
                c.get("seed_context_relation", ""),
                c.get("5m_direction_vs_seed_direction", ""),
                c.get("break_distance_ticks", ""),
                c.get("response_distance_ticks", ""),
                c.get("sequence_duration_minutes", ""),
            )
        ],
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    fname = _fname(study_id, c["seed_id"], c["candidate_id"], complete_label, "formation", primary)
    path = hub / "charts" / "pack_b" / fname
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _render_pack_c(
    hub, study_id, cfg_hash, data_version, policy, c, o, bars_5m, tick, complete_label, primary
):
    complete = _localize(pd.Timestamp(c["structure_complete_at"]))
    end = complete + pd.Timedelta(minutes=180)
    w = bars_5m[(bars_5m.index >= complete) & (bars_5m.index < end)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, w, width_min=4)
    ax.axvspan(complete.to_pydatetime(), end.to_pydatetime(), color="#888", alpha=0.08)
    ax.axvline(complete.to_pydatetime(), color="#333", lw=1.2)
    ax.axvline(end.to_pydatetime(), color="#333", lw=1.0, ls=":")
    ax.axhline(float(c["protected_price"]), color="#111", lw=2.0)
    ax.axhline(float(c["failure_threshold"]), color="#111", lw=1.0, ls="--")
    if o is not None and o.get("failure_ts"):
        fts = _localize(pd.Timestamp(o["failure_ts"]))
        ax.scatter(
            [fts.to_pydatetime()],
            [float(o["failure_price"])],
            marker="x",
            s=80,
            color="red",
            zorder=7,
            label="FIRST FAILURE",
        )
    if o is not None and o.get("first_equal_touch_ts"):
        ets = _localize(pd.Timestamp(o["first_equal_touch_ts"]))
        ax.scatter(
            [ets.to_pydatetime()],
            [float(c["protected_price"])],
            s=60,
            color="#e67e22",
            zorder=7,
            label="EQ TOUCH",
        )
    ax.text(
        0.01,
        0.98,
        primary,
        transform=ax.transAxes,
        va="top",
        fontsize=11,
        fontweight="bold",
        color="#222",
    )
    mfe = o.get("max_favorable_excursion_ticks", "") if o else ""
    mae = o.get("max_adverse_excursion_ticks", "") if o else ""
    _header(
        ax,
        _meta_lines(study_id, cfg_hash, data_version, policy, c["seed_id"], c["candidate_id"], primary)
        + ["MFE_ticks=%s MAE_ticks=%s" % (mfe, mae)],
    )
    ax.legend(loc="upper right", fontsize=7)
    fig.autofmt_xdate()
    fig.tight_layout()
    fname = _fname(study_id, c["seed_id"], c["candidate_id"], complete_label, "protection", primary)
    path = hub / "charts" / "pack_c" / fname
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _render_pack_d(
    hub, study_id, cfg_hash, data_version, policy, c, t, bars_5m, tick, complete_label, tlab
):
    touch_ts = _localize(pd.Timestamp(t["touch_ts"]))
    end = _localize(pd.Timestamp(t["touch_response_end"]))
    t0 = touch_ts - pd.Timedelta(minutes=30)
    w = bars_5m[(bars_5m.index >= t0) & (bars_5m.index < end)]
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, w, width_min=4)
    ax.axvspan(touch_ts.to_pydatetime(), end.to_pydatetime(), color="#4a90d9", alpha=0.08)
    ax.axhline(float(c["protected_price"]), color="#111", lw=2.0)
    ax.axhline(float(t["invalidation_threshold"]), color="#111", lw=1.0, ls="--")
    ax.axhline(float(t["favorable_response_threshold"]), color="#168a5a", lw=1.0, ls="-.")
    ax.axvline(end.to_pydatetime(), color="#333", lw=1.0, ls=":")
    # touch bar highlight
    touch_open = touch_ts - pd.Timedelta(minutes=5)
    ax.axvspan(touch_open.to_pydatetime(), touch_ts.to_pydatetime(), color="#4a90d9", alpha=0.25)
    ax.scatter(
        [touch_ts.to_pydatetime()],
        [float(c["protected_price"])],
        s=70,
        color="#4a90d9",
        zorder=7,
        label="FIRST TOUCH",
    )
    if t.get("favorable_threshold_first_ts") and tlab == "TOUCH_FAVORS_DIRECTION":
        fts = _localize(pd.Timestamp(t["favorable_threshold_first_ts"]))
        ax.scatter(
            [fts.to_pydatetime()],
            [float(t["favorable_response_threshold"])],
            s=60,
            color="#168a5a",
            zorder=7,
            label="FIRST FAVORABLE",
        )
    if t.get("invalidation_threshold_first_ts") and tlab in (
        "TOUCH_INVALIDATES_DIRECTION",
        "TOUCH_BOTH_SAME_5M_BAR_STOP_FIRST",
    ):
        its = _localize(pd.Timestamp(t["invalidation_threshold_first_ts"]))
        ax.scatter(
            [its.to_pydatetime()],
            [float(t["invalidation_threshold"])],
            marker="x",
            s=80,
            color="red",
            zorder=7,
            label="FIRST INVALIDATION",
        )
    ax.text(0.01, 0.98, tlab, transform=ax.transAxes, va="top", fontsize=11, fontweight="bold")
    _header(
        ax,
        _meta_lines(study_id, cfg_hash, data_version, policy, c["seed_id"], c["candidate_id"], tlab)
        + [
            "touch_hi=%s touch_lo=%s resp_dist=%s"
            % (t.get("touch_bar_high"), t.get("touch_bar_low"), t.get("response_distance_ticks"))
        ],
    )
    ax.legend(loc="upper right", fontsize=7)
    fig.autofmt_xdate()
    fig.tight_layout()
    fname = _fname(study_id, c["seed_id"], c["candidate_id"], complete_label, "touch", tlab)
    path = hub / "charts" / "pack_d" / fname
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _render_pack_f(hub, study_id, cfg_hash, cands, outs, touches, smoke, smoke_cap):
    rows = []
    if len(cands):
        m = cands.merge(outs, on="candidate_id", how="left", suffixes=("", "_o"))
        m = m.merge(touches, on="candidate_id", how="left", suffixes=("", "_t"))
        if smoke:
            m = m.head(smoke_cap)
        for _, r in m.iterrows():
            rows.append(
                [
                    str(r.get("seed_id", ""))[:18],
                    str(r.get("candidate_id", ""))[:22],
                    str(r.get("pattern", ""))[:12],
                    str(r.get("session_segment", ""))[:10],
                    str(r.get("structure_complete_at", ""))[11:19],
                    "%.2f" % float(r["protected_price"]) if pd.notna(r.get("protected_price")) else "",
                    str(r.get("primary_outcome_label", ""))[:22],
                    str(r.get("touch_response_outcome_label", ""))[:28],
                ]
            )
    fig, ax = plt.subplots(figsize=(16, max(4, 0.35 * max(len(rows), 1) + 2)))
    ax.axis("off")
    cols = [
        "seed",
        "candidate",
        "pattern",
        "segment",
        "complete",
        "prot",
        "primary",
        "touch",
    ]
    if not rows:
        rows = [["NONE"] * len(cols)]
    table = ax.table(cellText=rows, colLabels=cols, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    table.scale(1, 1.2)
    ax.set_title(
        "%s contact sheet | hash=%s | DESCRIPTIVE ONLY" % (study_id, cfg_hash),
        fontsize=9,
        loc="left",
        family="monospace",
    )
    fig.tight_layout()
    path = hub / "charts" / "pack_f" / ("%s__contact_sheet.png" % study_id)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
