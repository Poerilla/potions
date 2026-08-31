"""Chart packs A–G for seed-bias reaction review V1 (descriptive only)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_charts import (
    _plot_candles,
    _seed_h4_window,
    _shade_area,
)
from .nq_wick_reject_range_seed_retest import _localize

NY = "America/New_York"
PROHIBITED_WORDS = (
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "ENTER",
    "ENTRY",
    "STOP",
    "TARGET",
    "P&L",
    "PNL",
    "POSITION SIZE",
    "TAKE_SETUP",
    "AVOID_SETUP",
    "GOOD_TRADE",
    "BAD_TRADE",
)


def _safe(s: Any) -> str:
    return "".join(ch if str(ch).isalnum() or ch in "-_" else "_" for ch in str(s))


def _ts_label(ts: Any) -> str:
    if ts is None or (isinstance(ts, float) and np.isnan(ts)):
        return "NA"
    s = str(ts).strip()
    if s.lower() in ("", "nan", "none", "nat"):
        return "NA"
    t = _localize(pd.Timestamp(ts))
    return t.strftime("%Y-%m-%d_%H%MET")


def _fmt_ts(ts: Any) -> str:
    if ts is None or (isinstance(ts, float) and np.isnan(ts)):
        return "NO_CONTACT"
    s = str(ts).strip()
    if s.lower() in ("", "nan", "none", "nat"):
        return "NO_CONTACT"
    return _localize(pd.Timestamp(ts)).strftime("%Y-%m-%d %H:%M ET")


def _rr(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if not np.isfinite(x):
        return "N/A"
    return "%.3f" % x


def _num(v: Any, nd: int = 1) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "NA"
    if not np.isfinite(x):
        return "NA"
    return ("%." + str(nd) + "f") % x


def _seed_short(bias: str) -> str:
    if bias == "BULLISH_SEED_BIAS":
        return "BULL_SEED"
    if bias == "BEARISH_SEED_BIAS":
        return "BEAR_SEED"
    return "UNCL_SEED"


def _struct_short(bias: str) -> str:
    if bias == "UP":
        return "BULL_STRUCTURE"
    if bias == "DOWN":
        return "BEAR_STRUCTURE"
    return "UNCL_STRUCTURE"


def _fname(
    pack: str,
    seed_id: str,
    cand_id: str,
    complete_ts: Any,
    seed_bias: str,
    struct_bias: str,
    contact_class: str,
    data_status: str,
) -> str:
    return (
        "%s__%s__%s__%s__%s__%s__%s__%s.png"
        % (
            _safe(pack),
            _safe(seed_id),
            _safe(cand_id or "NONE"),
            _safe(_ts_label(complete_ts)),
            _safe(_seed_short(seed_bias)),
            _safe(_struct_short(struct_bias)),
            _safe(contact_class),
            _safe(data_status),
        )
    )


def _header_footer(
    study_id: str,
    parent_hash: str,
    remap_study: str,
    data_version: str,
    chart_generator_version: str,
    cfg_hash: str,
    row: Dict[str, Any],
) -> Tuple[str, str]:
    ny_date = "NA"
    if row.get("structure_complete_at"):
        ny_date = _localize(pd.Timestamp(row["structure_complete_at"])).strftime("%Y-%m-%d")
    header = (
        "study_id: %s\n"
        "instrument: NQ\n"
        "seed_id: %s\n"
        "candidate_id: %s\n"
        "NY date: %s\n"
        "timezone: America/New_York\n"
        "parent config hash: %s\n"
        "against-seed remap source: %s\n"
        "source data version: %s\n"
        "4-hour seed bias: %s\n"
        "1-minute structure pattern: %s\n"
        "1-minute structure bias: %s\n"
        "with-seed direction: %s\n"
        "against-seed direction: %s\n"
        "contact classification: %s\n"
        "data completeness: %s"
        % (
            study_id,
            row.get("seed_id"),
            row.get("candidate_id"),
            ny_date,
            parent_hash,
            remap_study,
            data_version,
            row.get("seed_bias"),
            row.get("structure_pattern_label"),
            row.get("structure_bias"),
            row.get("with_seed_direction"),
            row.get("against_seed_direction"),
            row.get("contact_classification"),
            row.get("data_status"),
        )
    )
    footer = (
        "seed_ts: %s | seed_available_at: %s | structure_complete_at: %s\n"
        "first_contact_ts: %s | structure_horizon_end: %s | reaction_horizon_end: %s\n"
        "chart_generated_at: %s | chart_generator_version: %s | chart_configuration_hash: %s"
        % (
            _fmt_ts(row.get("seed_ts")),
            _fmt_ts(row.get("seed_available_at")),
            _fmt_ts(row.get("structure_complete_at")),
            _fmt_ts(row.get("first_contact_ts")) if str(row.get("first_contact_ts") or "") else "NO_CONTACT",
            _fmt_ts(row.get("structure_horizon_end")),
            _fmt_ts(row.get("reaction_horizon_end"))
            if str(row.get("reaction_horizon_end") or "")
            else "NOT_APPLICABLE",
            datetime.now().strftime("%Y-%m-%d %H:%M ET"),
            chart_generator_version,
            cfg_hash,
        )
    )
    return header, footer


def _scan_no_trade(text: str) -> bool:
    """Word-boundary scan so labels like CENTER do not trip ENTER."""
    import re

    u = text.upper()
    for w in PROHIBITED_WORDS:
        if re.search(r"(?<![A-Z0-9_])%s(?![A-Z0-9_])" % re.escape(w), u):
            return False
    return True


def _pivot_labels(pattern: str) -> Dict[str, str]:
    if str(pattern).startswith("BEAR"):
        return {
            "p1": "P1 H1",
            "p2": "P2 L1 / BREAK LEVEL",
            "p3": "P3 HH / PROTECTED AREA CENTER",
            "p4": "P4 LL / STRUCTURE CONFIRMED",
        }
    return {
        "p1": "P1 L1",
        "p2": "P2 H1 / BREAK LEVEL",
        "p3": "P3 LL / PROTECTED AREA CENTER",
        "p4": "P4 HH / STRUCTURE CONFIRMED",
    }


def _side(pattern: Any) -> str:
    return "BEAR" if str(pattern).startswith("BEAR") else "BULL"


def _excursion_box(row: Dict[str, Any], prefix: str = "") -> str:
    def g(k: str) -> Any:
        return row.get(prefix + k) if prefix else row.get(k)

    return (
        "4H Seed Bias: %s\n"
        "1M Structure Bias: %s\n"
        "With Seed Direction: %s\n"
        "Against Seed Direction: %s\n"
        "Contact Classification: %s\n"
        "With Seed: MFE %s ticks  MAE %s ticks  RR %s\n"
        "Against Seed: MFE %s ticks  MAE %s ticks  RR %s\n"
        "Structure Bias: MFE %s ticks  MAE %s ticks  RR %s"
        % (
            row.get("seed_bias"),
            row.get("structure_bias"),
            row.get("with_seed_direction"),
            row.get("against_seed_direction"),
            row.get("contact_classification"),
            _num(g("with_seed_mfe_ticks")),
            _num(g("with_seed_mae_ticks")),
            _rr(g("with_seed_rr")),
            _num(g("against_seed_mfe_ticks")),
            _num(g("against_seed_mae_ticks")),
            _rr(g("against_seed_rr")),
            _num(g("structure_bias_mfe_ticks")),
            _num(g("structure_bias_mae_ticks")),
            _rr(g("structure_bias_rr")),
        )
    )


def _manifest_row(
    path: Path,
    pack: str,
    row: Dict[str, Any],
    study_id: str,
    parent_hash: str,
    remap_study: str,
    status: str,
    err: str = "",
) -> Dict[str, Any]:
    return {
        "chart_filename": path.name if path else "",
        "chart_pack": pack,
        "seed_id": row.get("seed_id"),
        "candidate_id": row.get("candidate_id"),
        "source_study_id": study_id,
        "parent_config_hash": parent_hash,
        "against_seed_bias_source": remap_study,
        "seed_bias": row.get("seed_bias"),
        "structure_bias": row.get("structure_bias"),
        "alignment_status": row.get("alignment_status"),
        "contact_classification": row.get("contact_classification"),
        "structure_complete_at": row.get("structure_complete_at"),
        "first_contact_ts": row.get("first_contact_ts"),
        "structure_horizon_end": row.get("structure_horizon_end"),
        "reaction_horizon_end": row.get("reaction_horizon_end"),
        "with_seed_mfe_ticks": row.get("with_seed_mfe_ticks"),
        "with_seed_mae_ticks": row.get("with_seed_mae_ticks"),
        "with_seed_rr": row.get("with_seed_rr"),
        "against_seed_mfe_ticks": row.get("against_seed_mfe_ticks"),
        "against_seed_mae_ticks": row.get("against_seed_mae_ticks"),
        "against_seed_rr": row.get("against_seed_rr"),
        "structure_bias_mfe_ticks": row.get("structure_bias_mfe_ticks"),
        "structure_bias_mae_ticks": row.get("structure_bias_mae_ticks"),
        "structure_bias_rr": row.get("structure_bias_rr"),
        "data_complete": row.get("data_status"),
        "generation_timestamp": datetime.now().isoformat(),
        "generation_status": status,
        "generation_error": err,
    }


def render_all(
    hub: Path,
    study_id: str,
    parent_hash: str,
    cfg_hash: str,
    remap_study: str,
    data_version: str,
    chart_generator_version: str,
    unified: pd.DataFrame,
    bars_1m: pd.DataFrame,
    h4: pd.DataFrame,
    tick: float,
    smoke: bool = False,
    smoke_cap: int = 5,
) -> pd.DataFrame:
    rows = unified.to_dict(orient="records")
    if smoke:
        rows = rows[:smoke_cap]
    # sort calendar ascending, seed_id tie-break
    rows = sorted(
        rows,
        key=lambda r: (
            str(r.get("structure_complete_at") or ""),
            str(r.get("seed_id") or ""),
        ),
    )

    manifest: List[Dict[str, Any]] = []
    ctx = dict(
        study_id=study_id,
        parent_hash=parent_hash,
        cfg_hash=cfg_hash,
        remap_study=remap_study,
        data_version=data_version,
        chart_generator_version=chart_generator_version,
        tick=tick,
    )

    for row in rows:
        for pack, fn in (
            ("A_context", _render_pack_a),
            ("C_structure_path", _render_pack_c),
        ):
            try:
                path = fn(hub, row, bars_1m, h4, **ctx)
                manifest.append(_manifest_row(path, pack, row, study_id, parent_hash, remap_study, "OK"))
            except Exception as exc:
                manifest.append(
                    _manifest_row(Path(""), pack, row, study_id, parent_hash, remap_study, "FAIL", str(exc))
                )

        # Pack B + D: valid first-contact records
        has_contact = (
            bool(row.get("contact_eligible"))
            and bool(row.get("data_complete_contact"))
            and str(row.get("first_contact_ts") or "")
            and str(row.get("first_contact_ts")).lower() not in ("nan", "none", "")
        )
        if has_contact:
            for pack, fn in (
                ("B_contact", _render_pack_b),
                ("D_bias_compare", _render_pack_d),
            ):
                try:
                    path = fn(hub, row, bars_1m, h4, **ctx)
                    manifest.append(
                        _manifest_row(path, pack, row, study_id, parent_hash, remap_study, "OK")
                    )
                except Exception as exc:
                    manifest.append(
                        _manifest_row(
                            Path(""), pack, row, study_id, parent_hash, remap_study, "FAIL", str(exc)
                        )
                    )

    # Pack E contact sheets
    try:
        for path, meta in _render_pack_e(hub, rows, **ctx):
            manifest.append(meta)
    except Exception as exc:
        manifest.append(
            {
                "chart_filename": "",
                "chart_pack": "E_depth_sheet",
                "generation_status": "FAIL",
                "generation_error": str(exc),
            }
        )

    # Pack F extremes
    try:
        for path, meta in _render_pack_f(hub, rows, **ctx):
            manifest.append(meta)
    except Exception as exc:
        manifest.append(
            {
                "chart_filename": "",
                "chart_pack": "F_extreme",
                "generation_status": "FAIL",
                "generation_error": str(exc),
            }
        )

    # Pack G calendar
    try:
        for path, meta in _render_pack_g(hub, rows, **ctx):
            manifest.append(meta)
    except Exception as exc:
        manifest.append(
            {
                "chart_filename": "",
                "chart_pack": "G_calendar",
                "generation_status": "FAIL",
                "generation_error": str(exc),
            }
        )

    mdf = pd.DataFrame(manifest)
    mdf.to_csv(hub / "chart_manifest.csv", index=False)
    (hub / "CHART_SPEC.md").write_text(
        "# CHART_SPEC — seed bias review V1\n\n"
        "Packs A–G. Descriptive visual review only.\n"
        "No entries/stops/targets/P&L/position size/trade recommendations.\n",
        encoding="utf-8",
    )
    (hub / "INDEX.md").write_text(
        "# INDEX\n\nSee chart_manifest.csv (%d rows) and CHART_PACK_SUMMARY.md.\n" % len(mdf),
        encoding="utf-8",
    )
    return mdf


def _apply_meta(fig, header: str, footer: str) -> None:
    fig.suptitle(header, fontsize=5.5, family="monospace", x=0.01, ha="left", va="top", y=0.995)
    fig.text(0.01, 0.005, footer, fontsize=5, family="monospace", ha="left", va="bottom")
    assert _scan_no_trade(header + "\n" + footer)


def _render_pack_a(hub, row, bars_1m, h4, **ctx):
    study_id = ctx["study_id"]
    tick = ctx["tick"]
    header, footer = _header_footer(
        study_id,
        ctx["parent_hash"],
        ctx["remap_study"],
        ctx["data_version"],
        ctx["chart_generator_version"],
        ctx["cfg_hash"],
        row,
    )
    seed_ts = _localize(pd.Timestamp(row["seed_ts"]))
    avail = _localize(pd.Timestamp(row["seed_available_at"]))
    exp = _localize(pd.Timestamp(row["seed_expiry"]))
    complete = _localize(pd.Timestamp(row["structure_complete_at"]))
    hi, lo = float(row["seed_high"]), float(row["seed_low"])
    mid = 0.5 * (hi + lo)
    width_pts = hi - lo
    width_ticks = width_pts / tick

    fig, axes = plt.subplots(2, 1, figsize=(15, 10), gridspec_kw={"height_ratios": [1.0, 1.35]})
    ax4, ax1 = axes

    h4w = _seed_h4_window(h4, seed_ts, max(exp, complete))
    _plot_candles(ax4, h4w, width_min=200)
    ax4.axhspan(lo, hi, color="#5b7c99", alpha=0.18, label="4H SEED RANGE")
    ax4.axhline(hi, color="#5b7c99", lw=1.1, label="SEED HIGH")
    ax4.axhline(lo, color="#5b7c99", lw=1.1, label="SEED LOW")
    ax4.axhline(mid, color="#5b7c99", lw=0.8, ls=":", label="SEED MIDPOINT — REFERENCE ONLY")
    if pd.notna(row.get("range_high")):
        ax4.axhline(float(row["range_high"]), color="#7a6f5d", lw=0.9, ls="--", label="SWEPT STRUCT HIGH")
    if pd.notna(row.get("range_low")):
        ax4.axhline(float(row["range_low"]), color="#7a6f5d", lw=0.9, ls="--", label="SWEPT STRUCT LOW")
    ax4.axvline(seed_ts.to_pydatetime(), color="black", lw=1.0, label="seed_ts")
    ax4.axvline(avail.to_pydatetime(), color="#333333", lw=0.9, ls="--", label="seed_available_at")
    ax4.axvline(exp.to_pydatetime(), color="#888888", lw=0.8, ls=":", label="seed_expiry")
    ax4.axvline(complete.to_pydatetime(), color="black", lw=1.1, label="STRUCTURE AVAILABLE")
    seed_color = "#2a6f6f" if row["seed_bias"] == "BULLISH_SEED_BIAS" else "#b85c38"
    ax4.text(
        0.01,
        0.98,
        "WICK_REJECT SEED  bias=%s  width=%.2f pts / %.0f ticks\n"
        "range_width_atr=%s  penetration_atr=%s\n"
        "1m structure bias=%s  with-seed=%s  against-seed=%s"
        % (
            row["seed_bias"],
            width_pts,
            width_ticks,
            _num(row.get("range_width_atr"), 3),
            _num(row.get("penetration_atr"), 3),
            row["structure_bias"],
            row["with_seed_direction"],
            row["against_seed_direction"],
        ),
        transform=ax4.transAxes,
        fontsize=7,
        va="top",
        color=seed_color,
        family="monospace",
    )
    ax4.set_ylabel("4H")
    ax4.legend(loc="upper right", fontsize=5, ncol=2)

    # 1m formation panel
    p1 = _localize(pd.Timestamp(row["p1_bar_open_ts"]))
    w0 = p1 - timedelta(minutes=15)
    w1 = complete + timedelta(minutes=15)
    fc = str(row.get("first_contact_ts") or "")
    if fc and fc.lower() not in ("nan", "none", ""):
        fct = _localize(pd.Timestamp(fc))
        w1 = max(w1, fct + timedelta(minutes=5))
    win = bars_1m[(bars_1m.index >= w0) & (bars_1m.index < w1)]
    _plot_candles(ax1, win, width_min=0.8)
    side = _side(row["pattern"])
    path_color = "#c43d3d" if side == "BEAR" else "#2a6f6f"
    labs = _pivot_labels(row["pattern"])
    xs, ys = [], []
    for key, lab_key in (("p1", "p1"), ("p2", "p2"), ("p3", "p3"), ("p4", "p4")):
        ts = _localize(pd.Timestamp(row["%s_ts" % key]))
        px = float(row["%s_price" % key])
        avail_p = _localize(pd.Timestamp(row["%s_available_at" % key]))
        ax1.scatter([ts.to_pydatetime()], [px], s=36, zorder=6, color=path_color)
        ax1.annotate(
            "%s\n%s\navail %s" % (labs[lab_key], px, avail_p.strftime("%H:%M")),
            (ts.to_pydatetime(), px),
            textcoords="offset points",
            xytext=(4, 6),
            fontsize=5,
            color=path_color,
        )
        xs.append(ts.to_pydatetime())
        ys.append(px)
    if xs:
        ax1.plot(xs, ys, color=path_color, lw=1.2, alpha=0.85, label="1M STRUCTURE PATH")
    _shade_area(ax1, side, float(row["protected_pivot_price"]), float(row["outer_area_edge"]))
    ax1.axhline(float(row["break_level"]), color="#666666", lw=0.8, ls=":", label="BREAK LEVEL")
    ax1.axhline(
        float(row["structure_reference_price"]),
        color="#6b3fa0",
        lw=0.9,
        label="STRUCTURE REFERENCE (P4)",
    )
    ax1.axvline(complete.to_pydatetime(), color="black", lw=1.2, label="STRUCTURE AVAILABLE")
    if fc and fc.lower() not in ("nan", "none", ""):
        ax1.axvline(
            _localize(pd.Timestamp(fc)).to_pydatetime(),
            color="#2c5aa0",
            lw=1.2,
            label="FIRST AREA CONTACT",
        )
    aw = float(row["area_width_ticks"])
    ax1.text(
        0.01,
        0.02,
        "PROTECTED REACTION AREA — DESCRIPTIVE ONLY\n"
        "area_width=%s ticks (%.2f pts)  contact=%s  depth=%s ticks"
        % (int(aw), aw * tick, row.get("contact_classification"), _num(row.get("first_contact_depth_ticks"))),
        transform=ax1.transAxes,
        fontsize=6,
        family="monospace",
        color="#6b5a20",
    )
    ax1.set_ylabel("1M")
    ax1.legend(loc="upper right", fontsize=5, ncol=2)

    _apply_meta(fig, header, footer)
    fig.tight_layout(rect=[0, 0.04, 1, 0.82])
    out = hub / "charts" / "pack_a" / _fname(
        "A_context",
        row["seed_id"],
        row["candidate_id"],
        row["structure_complete_at"],
        row["seed_bias"],
        row["structure_bias"],
        row["contact_classification"],
        row["data_status"],
    )
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_b(hub, row, bars_1m, h4, **ctx):
    header, footer = _header_footer(
        ctx["study_id"],
        ctx["parent_hash"],
        ctx["remap_study"],
        ctx["data_version"],
        ctx["chart_generator_version"],
        ctx["cfg_hash"],
        row,
    )
    tick = ctx["tick"]
    contact = _localize(pd.Timestamp(row["first_contact_ts"]))
    end = _localize(pd.Timestamp(row["reaction_horizon_end"]))
    w0 = contact - timedelta(minutes=20)
    w1 = end + timedelta(minutes=10)
    win = bars_1m[(bars_1m.index >= w0) & (bars_1m.index < w1)]
    fig, ax = plt.subplots(figsize=(15, 7))
    _plot_candles(ax, win, width_min=0.8)
    side = _side(row["pattern"])
    _shade_area(ax, side, float(row["protected_pivot_price"]), float(row["outer_area_edge"]))
    ax.axvline(contact.to_pydatetime(), color="#2c5aa0", lw=1.4, label="FIRST AREA CONTACT")
    ax.axvline(end.to_pydatetime(), color="#555555", lw=1.0, ls="--", label="REACTION OBSERVATION END")
    # outside measurement window shade
    ax.axvspan(end.to_pydatetime(), w1.to_pydatetime(), color="#999999", alpha=0.08, label="OUTSIDE MEASUREMENT WINDOW")
    if pd.notna(row.get("highest_high_reaction")):
        ax.axhline(float(row["highest_high_reaction"]), color="#4a6fa5", lw=0.8, ls=":", label="REACTION HIGH")
    if pd.notna(row.get("lowest_low_reaction")):
        ax.axhline(float(row["lowest_low_reaction"]), color="#7a5a8a", lw=0.8, ls=":", label="REACTION LOW")
    if pd.notna(row.get("first_contact_bar_high")):
        ax.scatter(
            [contact.to_pydatetime()],
            [float(row["first_contact_bar_high"])],
            s=40,
            color="#2c5aa0",
            zorder=6,
            marker="^",
        )
    if pd.notna(row.get("first_contact_bar_low")):
        ax.scatter(
            [contact.to_pydatetime()],
            [float(row["first_contact_bar_low"])],
            s=40,
            color="#2c5aa0",
            zorder=6,
            marker="v",
        )
    box = _excursion_box(row)
    ax.text(
        0.99,
        0.98,
        box,
        transform=ax.transAxes,
        fontsize=6,
        family="monospace",
        va="top",
        ha="right",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#888"),
    )
    ax.set_title("REACTION PATH REVIEW — NO TRADE SIGNAL", fontsize=10, pad=8)
    ax.text(
        0.01,
        0.02,
        "contact depth=%s ticks  area_width=%s ticks\n"
        "DESCRIPTIVE EXCURSION AXES ONLY (with-seed / against-seed / structure-bias)"
        % (_num(row.get("first_contact_depth_ticks")), _num(row.get("area_width_ticks"), 0)),
        transform=ax.transAxes,
        fontsize=6,
        family="monospace",
    )
    ax.legend(loc="upper left", fontsize=5)
    _apply_meta(fig, header, footer)
    fig.tight_layout(rect=[0, 0.05, 1, 0.78])
    out = hub / "charts" / "pack_b" / _fname(
        "B_contact",
        row["seed_id"],
        row["candidate_id"],
        row["structure_complete_at"],
        row["seed_bias"],
        row["structure_bias"],
        row["contact_classification"],
        row["data_status"],
    )
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_c(hub, row, bars_1m, h4, **ctx):
    header, footer = _header_footer(
        ctx["study_id"],
        ctx["parent_hash"],
        ctx["remap_study"],
        ctx["data_version"],
        ctx["chart_generator_version"],
        ctx["cfg_hash"],
        row,
    )
    complete = _localize(pd.Timestamp(row["structure_complete_at"]))
    end = _localize(pd.Timestamp(row["structure_horizon_end"])) if str(row.get("structure_horizon_end") or "") else complete + timedelta(minutes=180)
    w0 = complete - timedelta(minutes=15)
    w1 = end + timedelta(minutes=10)
    win = bars_1m[(bars_1m.index >= w0) & (bars_1m.index < w1)]
    fig, ax = plt.subplots(figsize=(15, 7))
    _plot_candles(ax, win, width_min=0.8)
    side = _side(row["pattern"])
    _shade_area(ax, side, float(row["protected_pivot_price"]), float(row["outer_area_edge"]))
    ax.axhline(float(row["structure_reference_price"]), color="#6b3fa0", lw=1.0, label="STRUCTURE REFERENCE")
    ax.axvline(complete.to_pydatetime(), color="black", lw=1.2, label="STRUCTURE AVAILABLE")
    ax.axvline(end.to_pydatetime(), color="#555555", lw=1.0, label="STRUCTURE OBSERVATION END")
    ax.axvspan(end.to_pydatetime(), w1.to_pydatetime(), color="#999999", alpha=0.08, label="OUTSIDE MEASUREMENT WINDOW")
    fc = str(row.get("first_contact_ts") or "")
    if fc and fc.lower() not in ("nan", "none", ""):
        ax.axvline(
            _localize(pd.Timestamp(fc)).to_pydatetime(),
            color="#2c5aa0",
            lw=1.2,
            label="FIRST AREA CONTACT",
        )
    if pd.notna(row.get("highest_high_structure")):
        ax.axhline(float(row["highest_high_structure"]), color="#4a6fa5", lw=0.8, ls=":", label="WINDOW HIGH")
    if pd.notna(row.get("lowest_low_structure")):
        ax.axhline(float(row["lowest_low_structure"]), color="#7a5a8a", lw=0.8, ls=":", label="WINDOW LOW")
    box = (
        "THIS CHART MEASURES EXCURSION FROM STRUCTURE COMPLETION.\n"
        "IT IS NOT A TRADE PATH.\n\n"
        "With Seed: MFE %s MAE %s RR %s\n"
        "Against Seed: MFE %s MAE %s RR %s\n"
        "Structure Bias: MFE %s MAE %s RR %s\n"
        "contact=%s  data=%s  seed=%s  structure=%s"
        % (
            _num(row.get("struct_with_seed_mfe_ticks")),
            _num(row.get("struct_with_seed_mae_ticks")),
            _rr(row.get("struct_with_seed_rr")),
            _num(row.get("struct_against_seed_mfe_ticks")),
            _num(row.get("struct_against_seed_mae_ticks")),
            _rr(row.get("struct_against_seed_rr")),
            _num(row.get("struct_structure_bias_mfe_ticks")),
            _num(row.get("struct_structure_bias_mae_ticks")),
            _rr(row.get("struct_structure_bias_rr")),
            row.get("contact_classification"),
            row.get("data_status"),
            row.get("seed_bias"),
            row.get("structure_bias"),
        )
    )
    ax.text(
        0.99,
        0.98,
        box,
        transform=ax.transAxes,
        fontsize=6,
        family="monospace",
        va="top",
        ha="right",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#888"),
    )
    ax.legend(loc="upper left", fontsize=5)
    _apply_meta(fig, header, footer)
    fig.tight_layout(rect=[0, 0.05, 1, 0.78])
    out = hub / "charts" / "pack_c" / _fname(
        "C_structure_path",
        row["seed_id"],
        row["candidate_id"],
        row["structure_complete_at"],
        row["seed_bias"],
        row["structure_bias"],
        row["contact_classification"],
        row["data_status"],
    )
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _render_pack_d(hub, row, bars_1m, h4, **ctx):
    header, footer = _header_footer(
        ctx["study_id"],
        ctx["parent_hash"],
        ctx["remap_study"],
        ctx["data_version"],
        ctx["chart_generator_version"],
        ctx["cfg_hash"],
        row,
    )
    contact = _localize(pd.Timestamp(row["first_contact_ts"]))
    end = _localize(pd.Timestamp(row["reaction_horizon_end"]))
    w0 = contact - timedelta(minutes=15)
    w1 = end + timedelta(minutes=5)
    win = bars_1m[(bars_1m.index >= w0) & (bars_1m.index < w1)]
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), gridspec_kw={"width_ratios": [2.2, 1.0]})
    ax, axb = axes
    _plot_candles(ax, win, width_min=0.8)
    side = _side(row["pattern"])
    _shade_area(ax, side, float(row["protected_pivot_price"]), float(row["outer_area_edge"]))
    ax.axvline(contact.to_pydatetime(), color="#2c5aa0", lw=1.2, label="FIRST AREA CONTACT")
    ax.axvline(end.to_pydatetime(), color="#555555", lw=1.0, ls="--", label="REACTION OBSERVATION END")
    if pd.notna(row.get("highest_high_reaction")):
        ax.axhline(float(row["highest_high_reaction"]), color="#4a6fa5", lw=0.8, ls=":")
    if pd.notna(row.get("lowest_low_reaction")):
        ax.axhline(float(row["lowest_low_reaction"]), color="#7a5a8a", lw=0.8, ls=":")
    ax.legend(loc="upper left", fontsize=5)

    seed_u = "UP" if row["seed_bias"] == "BULLISH_SEED_BIAS" else (
        "DOWN" if row["seed_bias"] == "BEARISH_SEED_BIAS" else "NA"
    )
    compare = (
        "4H Seed Bias: %s\n"
        "1M Structure Bias: %s\n"
        "Relationship: %s\n\n"
        "With-seed MFE/MAE/RR:\n  %s / %s / %s\n"
        "Against-seed MFE/MAE/RR:\n  %s / %s / %s\n"
        "Structure-bias MFE/MAE/RR:\n  %s / %s / %s\n\n"
        "Contact class: %s\n"
        "Max depth through area: %s ticks\n"
        "First contact: %s\n\n"
        "ALIGNMENT STATUS IS CONTEXT ONLY\n"
        "— NOT A FILTER OR SELECTOR."
        % (
            seed_u,
            row["structure_bias"],
            row["alignment_status"],
            _num(row.get("with_seed_mfe_ticks")),
            _num(row.get("with_seed_mae_ticks")),
            _rr(row.get("with_seed_rr")),
            _num(row.get("against_seed_mfe_ticks")),
            _num(row.get("against_seed_mae_ticks")),
            _rr(row.get("against_seed_rr")),
            _num(row.get("structure_bias_mfe_ticks")),
            _num(row.get("structure_bias_mae_ticks")),
            _rr(row.get("structure_bias_rr")),
            row.get("contact_classification"),
            _num(row.get("first_contact_depth_ticks")),
            _fmt_ts(row.get("first_contact_ts")),
        )
    )
    axb.axis("off")
    axb.text(0.02, 0.98, compare, transform=axb.transAxes, fontsize=7, family="monospace", va="top")
    _apply_meta(fig, header, footer)
    fig.tight_layout(rect=[0, 0.05, 1, 0.78])
    out = hub / "charts" / "pack_d" / _fname(
        "D_bias_compare",
        row["seed_id"],
        row["candidate_id"],
        row["structure_complete_at"],
        row["seed_bias"],
        row["structure_bias"],
        row["contact_classification"],
        row["data_status"],
    )
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _tile_text(row: Dict[str, Any], fname: str = "") -> str:
    return (
        "seed=%s\ncand=%s\n"
        "4h=%s\n1m=%s\nalign=%s\n"
        "contact=%s\narea=%s depth=%s\n"
        "withRR=%s againstRR=%s structRR=%s\n"
        "data=%s\n%s"
        % (
            row.get("seed_id"),
            row.get("candidate_id"),
            _seed_short(str(row.get("seed_bias"))),
            row.get("structure_bias"),
            row.get("alignment_status"),
            row.get("contact_classification"),
            _num(row.get("area_width_ticks"), 0),
            _num(row.get("first_contact_depth_ticks")),
            _rr(row.get("with_seed_rr")),
            _rr(row.get("against_seed_rr")),
            _rr(row.get("structure_bias_rr")),
            row.get("data_status"),
            fname[:48] if fname else "",
        )
    )


def _render_pack_e(hub, rows, **ctx):
    study_id = ctx["study_id"]
    parent_hash = ctx["parent_hash"]
    remap_study = ctx["remap_study"]
    out_paths = []
    classes = [
        "NO_AREA_CONTACT",
        "TOUCH_ONLY",
        "SHALLOW_TRADE_THROUGH",
        "DEEP_TRADE_THROUGH",
        "INSUFFICIENT_DATA_OR_SESSION_GAP",
    ]
    splits = [
        ("BULLISH_SEED_BIAS", lambda r: r.get("seed_bias") == "BULLISH_SEED_BIAS"),
        ("BEARISH_SEED_BIAS", lambda r: r.get("seed_bias") == "BEARISH_SEED_BIAS"),
        ("ALIGNED", lambda r: str(r.get("alignment_status", "")).startswith("ALIGNED")),
        ("OPPOSED", lambda r: r.get("alignment_status") == "OPPOSED"),
    ]
    for clas in classes:
        for split_name, pred in splits:
            group = [r for r in rows if r.get("contact_classification") == clas and pred(r)]
            group = sorted(
                group,
                key=lambda r: (str(r.get("structure_complete_at") or ""), str(r.get("seed_id") or "")),
            )
            if not group:
                continue
            per_page = 12
            pages = [group[i : i + per_page] for i in range(0, len(group), per_page)]
            for pi, page in enumerate(pages, start=1):
                fig, axes = plt.subplots(3, 4, figsize=(16, 10))
                axes = axes.flatten()
                for i, ax in enumerate(axes):
                    ax.axis("off")
                    if i < len(page):
                        ax.text(
                            0.02,
                            0.98,
                            _tile_text(page[i]),
                            transform=ax.transAxes,
                            fontsize=6,
                            family="monospace",
                            va="top",
                        )
                        ax.set_facecolor("#f3f1ea")
                        for spine in ax.spines.values():
                            spine.set_visible(True)
                            spine.set_color("#aaaaaa")
                fig.suptitle(
                    "AUDIT INDEX ONLY — DO NOT SELECT SETUPS FROM THIS PAGE\n"
                    "E_depth_sheet  class=%s  split=%s  page=%02d  n=%d"
                    % (clas, split_name, pi, len(page)),
                    fontsize=9,
                    family="monospace",
                )
                day = "MULTI"
                if page:
                    day = _localize(pd.Timestamp(page[0]["structure_complete_at"])).strftime("%Y-%m-%d")
                fname = "E_depth_sheet__%s__%s__%s__PAGE_%02d.png" % (
                    _safe(day),
                    _safe(split_name),
                    _safe(clas),
                    pi,
                )
                out = hub / "charts" / "pack_e" / fname
                fig.tight_layout(rect=[0, 0.02, 1, 0.92])
                fig.savefig(out, dpi=110)
                plt.close(fig)
                meta = {
                    "chart_filename": fname,
                    "chart_pack": "E_depth_sheet",
                    "seed_id": "",
                    "candidate_id": "",
                    "source_study_id": study_id,
                    "parent_config_hash": parent_hash,
                    "against_seed_bias_source": remap_study,
                    "seed_bias": split_name,
                    "structure_bias": "",
                    "alignment_status": split_name if split_name in ("ALIGNED", "OPPOSED") else "",
                    "contact_classification": clas,
                    "generation_timestamp": datetime.now().isoformat(),
                    "generation_status": "OK",
                    "generation_error": "",
                    "data_complete": "",
                }
                out_paths.append((out, meta))
    return out_paths


def _render_pack_f(hub, rows, **ctx):
    study_id = ctx["study_id"]
    parent_hash = ctx["parent_hash"]
    remap_study = ctx["remap_study"]
    out_paths = []
    # Only valid contacts for excursion ranking
    valid = [
        r
        for r in rows
        if bool(r.get("contact_eligible"))
        and bool(r.get("data_complete_contact"))
        and pd.notna(r.get("with_seed_mfe_ticks"))
    ]
    specs = [
        ("F_extreme_with_seed_mfe", "with_seed_mfe_ticks", "with_seed_mae_ticks", "with_seed_rr"),
        ("F_extreme_against_seed_mfe", "against_seed_mfe_ticks", "against_seed_mae_ticks", "against_seed_rr"),
        ("F_extreme_structure_bias_mfe", "structure_bias_mfe_ticks", "structure_bias_mae_ticks", "structure_bias_rr"),
        ("F_extreme_with_seed_mae", "with_seed_mae_ticks", "with_seed_mfe_ticks", "with_seed_rr"),
        ("F_extreme_against_seed_mae", "against_seed_mae_ticks", "against_seed_mfe_ticks", "against_seed_rr"),
        ("F_extreme_structure_bias_mae", "structure_bias_mae_ticks", "structure_bias_mfe_ticks", "structure_bias_rr"),
    ]
    for pack_name, primary, secondary, rr_key in specs:
        ranked = sorted(
            [r for r in valid if pd.notna(r.get(primary))],
            key=lambda r: float(r[primary]),
            reverse=True,
        )[:10]
        total = sum(float(r[primary]) for r in valid if pd.notna(r.get(primary))) or 1.0
        top1 = float(ranked[0][primary]) / total if ranked else 0.0
        top3 = sum(float(r[primary]) for r in ranked[:3]) / total if ranked else 0.0
        fig, axes = plt.subplots(2, 5, figsize=(16, 8))
        axes = axes.flatten()
        for i, ax in enumerate(axes):
            ax.axis("off")
            if i >= len(ranked):
                continue
            r = ranked[i]
            contrib = float(r[primary]) / total
            txt = (
                "RANK %02d\n"
                "seed=%s\ncand=%s\n"
                "ts=%s\n"
                "seed_bias=%s\nstruct_bias=%s\n"
                "contact=%s\n"
                "prim=%s  sec=%s\nRR=%s\n"
                "%% of pop=%s\n"
                "top1_conc=%s top3_conc=%s"
                % (
                    i + 1,
                    r.get("seed_id"),
                    r.get("candidate_id"),
                    _fmt_ts(r.get("first_contact_ts")),
                    r.get("seed_bias"),
                    r.get("structure_bias"),
                    r.get("contact_classification"),
                    _num(r.get(primary)),
                    _num(r.get(secondary)),
                    _rr(r.get(rr_key)),
                    "%.1f%%" % (100 * contrib),
                    "%.1f%%" % (100 * top1),
                    "%.1f%%" % (100 * top3),
                )
            )
            ax.text(0.02, 0.98, txt, transform=ax.transAxes, fontsize=5.5, family="monospace", va="top")
            ax.set_facecolor("#f0eee8")
        fig.suptitle(
            "RANKED FOR CONCENTRATION AUDIT — NOT SETUP SELECTION\n%s  n_valid=%d"
            % (pack_name, len(valid)),
            fontsize=9,
            family="monospace",
        )
        fname = "%s__TOP10.png" % pack_name
        # also write rank-1 named file for deterministic pattern
        out = hub / "charts" / "pack_f" / fname
        fig.tight_layout(rect=[0, 0.02, 1, 0.90])
        fig.savefig(out, dpi=110)
        plt.close(fig)
        out_paths.append(
            (
                out,
                {
                    "chart_filename": fname,
                    "chart_pack": pack_name,
                    "seed_id": ranked[0]["seed_id"] if ranked else "",
                    "candidate_id": ranked[0]["candidate_id"] if ranked else "",
                    "source_study_id": study_id,
                    "parent_config_hash": parent_hash,
                    "against_seed_bias_source": remap_study,
                    "generation_timestamp": datetime.now().isoformat(),
                    "generation_status": "OK",
                    "generation_error": "",
                },
            )
        )
        # per-rank stub filenames for first ranks (spec examples)
        for i, r in enumerate(ranked[:3], start=1):
            stub = "%s__RANK_%02d__%s__%s.png" % (
                pack_name,
                i,
                _safe(r["seed_id"]),
                _safe(r["candidate_id"]),
            )
            stub_path = hub / "charts" / "pack_f" / stub
            if not stub_path.exists():
                # lightweight pointer chart
                fig, ax = plt.subplots(figsize=(8, 3))
                ax.axis("off")
                ax.text(
                    0.02,
                    0.95,
                    "RANKED FOR CONCENTRATION AUDIT — NOT SETUP SELECTION\n" + _tile_text(r, stub),
                    transform=ax.transAxes,
                    fontsize=7,
                    family="monospace",
                    va="top",
                )
                fig.savefig(stub_path, dpi=100)
                plt.close(fig)
                out_paths.append(
                    (
                        stub_path,
                        {
                            "chart_filename": stub,
                            "chart_pack": pack_name,
                            "seed_id": r["seed_id"],
                            "candidate_id": r["candidate_id"],
                            "source_study_id": study_id,
                            "parent_config_hash": parent_hash,
                            "against_seed_bias_source": remap_study,
                            "seed_bias": r.get("seed_bias"),
                            "structure_bias": r.get("structure_bias"),
                            "alignment_status": r.get("alignment_status"),
                            "contact_classification": r.get("contact_classification"),
                            "with_seed_mfe_ticks": r.get("with_seed_mfe_ticks"),
                            "with_seed_mae_ticks": r.get("with_seed_mae_ticks"),
                            "with_seed_rr": r.get("with_seed_rr"),
                            "against_seed_mfe_ticks": r.get("against_seed_mfe_ticks"),
                            "against_seed_mae_ticks": r.get("against_seed_mae_ticks"),
                            "against_seed_rr": r.get("against_seed_rr"),
                            "structure_bias_mfe_ticks": r.get("structure_bias_mfe_ticks"),
                            "structure_bias_mae_ticks": r.get("structure_bias_mae_ticks"),
                            "structure_bias_rr": r.get("structure_bias_rr"),
                            "generation_timestamp": datetime.now().isoformat(),
                            "generation_status": "OK",
                            "generation_error": "",
                        },
                    )
                )
    return out_paths


def _agg_period(rows: List[Dict[str, Any]], key_fn) -> pd.DataFrame:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        k = key_fn(r)
        buckets.setdefault(k, []).append(r)
    out = []
    for period, items in sorted(buckets.items()):
        contacts = [
            x
            for x in items
            if bool(x.get("contact_eligible")) and bool(x.get("data_complete_contact"))
        ]
        def mean_rr(key):
            vals = [float(x[key]) for x in contacts if pd.notna(x.get(key)) and np.isfinite(float(x[key]))]
            return float(np.mean(vals)) if vals else float("nan")

        def med_rr(key):
            vals = [float(x[key]) for x in contacts if pd.notna(x.get(key)) and np.isfinite(float(x[key]))]
            return float(np.median(vals)) if vals else float("nan")

        mfes = [float(x["with_seed_mfe_ticks"]) for x in contacts if pd.notna(x.get("with_seed_mfe_ticks"))]
        total = sum(mfes) or 1.0
        top1 = (max(mfes) / total) if mfes else float("nan")
        gap = sum(1 for x in items if x.get("data_status") != "VALID")
        out.append(
            {
                "period": period,
                "candidate_count": len(items),
                "valid_contact_count": len(contacts),
                "bullish_seed_count": sum(1 for x in items if x.get("seed_bias") == "BULLISH_SEED_BIAS"),
                "bearish_seed_count": sum(1 for x in items if x.get("seed_bias") == "BEARISH_SEED_BIAS"),
                "aligned_count": sum(
                    1 for x in items if str(x.get("alignment_status", "")).startswith("ALIGNED")
                ),
                "opposed_count": sum(1 for x in items if x.get("alignment_status") == "OPPOSED"),
                "mean_with_seed_rr": mean_rr("with_seed_rr"),
                "mean_against_seed_rr": mean_rr("against_seed_rr"),
                "mean_structure_bias_rr": mean_rr("structure_bias_rr"),
                "median_with_seed_rr": med_rr("with_seed_rr"),
                "median_against_seed_rr": med_rr("against_seed_rr"),
                "median_structure_bias_rr": med_rr("structure_bias_rr"),
                "top1_mfe_concentration": top1,
                "data_gap_count": gap,
            }
        )
    return pd.DataFrame(out)


def _render_pack_g(hub, rows, **ctx):
    study_id = ctx["study_id"]
    parent_hash = ctx["parent_hash"]
    remap_study = ctx["remap_study"]
    out_paths = []

    def month_key(r):
        return _localize(pd.Timestamp(r["structure_complete_at"])).strftime("%Y-%m")

    def quarter_key(r):
        t = _localize(pd.Timestamp(r["structure_complete_at"]))
        q = (t.month - 1) // 3 + 1
        return "%dQ%d" % (t.year, q)

    def year_key(r):
        return _localize(pd.Timestamp(r["structure_complete_at"])).strftime("%Y")

    def session_key(r):
        return str(r.get("session_segment") or "UNKNOWN")

    for label, key_fn in (
        ("month", month_key),
        ("quarter", quarter_key),
        ("year", year_key),
        ("session", session_key),
    ):
        agg = _agg_period(rows, key_fn)
        agg.to_csv(hub / "charts" / "pack_g" / ("G_calendar__%s__table.csv" % label), index=False)
        # multi-page table charts
        per = 14
        pages = [agg.iloc[i : i + per] for i in range(0, len(agg), per)] or [agg]
        for pi, page in enumerate(pages, start=1):
            fig, ax = plt.subplots(figsize=(16, 9))
            ax.axis("off")
            lines = [
                "AUDIT CALENDAR REVIEW — DESCRIPTIVE ONLY (NOT A RULE)",
                "grouping=%s page=%02d" % (label, pi),
                "",
            ]
            hdr = (
                "period | n | contacts | bull | bear | align | oppose | "
                "meanW | meanA | meanS | medW | medA | medS | top1MFE | gaps"
            )
            lines.append(hdr)
            lines.append("-" * len(hdr))
            for _, r in page.iterrows():
                thin = " THIN N — DESCRIPTIVE ONLY" if int(r["valid_contact_count"]) < 5 else ""
                lines.append(
                    "%s | %d | %d | %d | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %d%s"
                    % (
                        r["period"],
                        int(r["candidate_count"]),
                        int(r["valid_contact_count"]),
                        int(r["bullish_seed_count"]),
                        int(r["bearish_seed_count"]),
                        int(r["aligned_count"]),
                        int(r["opposed_count"]),
                        _rr(r["mean_with_seed_rr"]),
                        _rr(r["mean_against_seed_rr"]),
                        _rr(r["mean_structure_bias_rr"]),
                        _rr(r["median_with_seed_rr"]),
                        _rr(r["median_against_seed_rr"]),
                        _rr(r["median_structure_bias_rr"]),
                        ("%.1f%%" % (100 * float(r["top1_mfe_concentration"])))
                        if pd.notna(r["top1_mfe_concentration"])
                        else "NA",
                        int(r["data_gap_count"]),
                        thin,
                    )
                )
            ax.text(
                0.01,
                0.99,
                "\n".join(lines),
                transform=ax.transAxes,
                fontsize=6.5,
                family="monospace",
                va="top",
            )
            fname = "G_calendar__%s__PAGE_%02d.png" % (label, pi)
            out = hub / "charts" / "pack_g" / fname
            fig.savefig(out, dpi=110)
            plt.close(fig)
            out_paths.append(
                (
                    out,
                    {
                        "chart_filename": fname,
                        "chart_pack": "G_calendar_%s" % label,
                        "seed_id": "",
                        "candidate_id": "",
                        "source_study_id": study_id,
                        "parent_config_hash": parent_hash,
                        "against_seed_bias_source": remap_study,
                        "generation_timestamp": datetime.now().isoformat(),
                        "generation_status": "OK",
                        "generation_error": "",
                    },
                )
            )
    return out_paths
