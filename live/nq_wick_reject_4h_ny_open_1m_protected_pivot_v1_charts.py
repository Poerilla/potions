"""ECU chart packs A–D for nq_wick_reject_4h_ny_open_1m_protected_pivot_v1."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nq_wick_reject_range_seed_retest import _localize
from .structure_program_st_study import rth_slice

NY = "America/New_York"
NY_OPEN = time(9, 30)
FORMATION_CUTOFF = time(10, 30)
OBS_END = time(13, 0)


def _ts_at(d: date, t: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(d, t), tz=NY)


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


def _plot_candles(ax, df: pd.DataFrame, width_min: float = 0.7) -> None:
    if df is None or df.empty:
        return
    # width in days for matplotlib date axis
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


def _header(ax, lines: List[str]) -> None:
    ax.set_title("\n".join(lines), fontsize=8, loc="left", family="monospace")


def _session_guides(ax, d: date, shade_formation: bool = True) -> None:
    o = _ts_at(d, NY_OPEN)
    c = _ts_at(d, FORMATION_CUTOFF)
    e = _ts_at(d, OBS_END)
    ax.axvline(o, color="#1a1a1a", lw=1.0, zorder=5)
    ax.axvline(c, color="#555555", lw=0.9, ls="--", zorder=5)
    ax.axvline(e, color="#333333", lw=0.9, ls=":", zorder=5)
    if shade_formation:
        ax.axvspan(o, c, color="#cfe8ff", alpha=0.35, zorder=1)


def _banner(ax, text: str, color: str = "#222222") -> None:
    ax.text(
        0.5,
        0.98,
        text,
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=11,
        fontweight="bold",
        color=color,
        bbox={"facecolor": "white", "edgecolor": color, "alpha": 0.9, "pad": 4},
        zorder=20,
    )


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def render_all(
    hub: Path,
    study_id: str,
    data_version: str,
    cfg_hash: str,
    elig: pd.DataFrame,
    pivots_df: pd.DataFrame,
    cands: pd.DataFrame,
    outs: pd.DataFrame,
    pack_d_meta: List[Dict[str, Any]],
    gby: Dict[date, pd.DataFrame],
    h4: pd.DataFrame,
    smoke: bool,
    smoke_cap: int,
    tick: float,
) -> None:
    gen_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    included = elig[elig["included"] == True].copy()  # noqa: E712
    cand_by_key = {}
    if len(cands):
        for _, r in cands.iterrows():
            cand_by_key[(r["seed_id"], r["ny_date"])] = r
    out_by_id = {}
    if len(outs):
        for _, r in outs.iterrows():
            out_by_id[r["candidate_id"]] = r
    d_reason = {(m["seed_id"], m["ny_date"]): m for m in pack_d_meta}

    manifest = []

    def cap(n: int) -> int:
        return min(n, smoke_cap) if smoke else n

    # ---- Pack A ----
    rows_a = included.head(cap(len(included))) if smoke else included
    for _, er in rows_a.iterrows():
        path = hub / "charts" / "pack_a" / ("%s_%s.png" % (er["seed_id"], er["ny_date"]))
        _chart_pack_a(
            path,
            er,
            cand_by_key.get((er["seed_id"], er["ny_date"])),
            out_by_id,
            pivots_df,
            gby,
            h4,
            study_id,
            data_version,
            cfg_hash,
            gen_ts,
            tick,
        )
        manifest.append({"pack": "A", "path": str(path.relative_to(hub)), "seed_id": er["seed_id"]})

    # ---- Pack B / C ----
    rows_c = cands.head(cap(len(cands))) if smoke else cands
    for _, cand in rows_c.iterrows():
        er = included[included["seed_id"] == cand["seed_id"]].iloc[0]
        d = date.fromisoformat(str(cand["ny_date"]))
        day = _day_rth(gby, d)
        out = out_by_id.get(cand["candidate_id"])
        pb = hub / "charts" / "pack_b" / ("%s.png" % cand["candidate_id"])
        pc = hub / "charts" / "pack_c" / ("%s.png" % cand["candidate_id"])
        _chart_pack_b(pb, er, cand, out, day, study_id, data_version, cfg_hash, gen_ts, tick)
        _chart_pack_c(pc, er, cand, out, day, study_id, data_version, cfg_hash, gen_ts, tick)
        manifest.append({"pack": "B", "path": str(pb.relative_to(hub)), "candidate_id": cand["candidate_id"]})
        manifest.append({"pack": "C", "path": str(pc.relative_to(hub)), "candidate_id": cand["candidate_id"]})

    # ---- Pack D ----
    d_items = pack_d_meta[: cap(len(pack_d_meta))] if smoke else pack_d_meta
    for meta in d_items:
        erows = included[(included["seed_id"] == meta["seed_id"]) & (included["ny_date"] == meta["ny_date"])]
        if erows.empty:
            continue
        er = erows.iloc[0]
        path = hub / "charts" / "pack_d" / ("%s_%s.png" % (meta["seed_id"], meta["ny_date"]))
        _chart_pack_d(
            path,
            er,
            meta,
            pivots_df,
            gby,
            study_id,
            data_version,
            cfg_hash,
            gen_ts,
            tick,
        )
        manifest.append({"pack": "D", "path": str(path.relative_to(hub)), "reason": meta.get("reason", "")})

    pd.DataFrame(manifest).to_csv(hub / "chart_manifest.csv", index=False)
    (hub / "CHART_SPEC.md").write_text(
        "\n".join(
            [
                "# CHART_SPEC — %s" % study_id,
                "",
                "Packs A–D generated from immutable ledgers.",
                "No entry/stop/target/P&L annotations.",
                "config_hash: %s" % cfg_hash,
                "data_version: %s" % data_version,
                "timezone: America/New_York",
                "generated: %s" % gen_ts,
                "smoke: %s" % smoke,
                "",
            ]
        ),
        encoding="utf-8",
    )
    idx = ["# Chart INDEX", "", "| Pack | File | Notes |", "|------|------|-------|"]
    for m in manifest:
        idx.append(
            "| %s | `%s` | %s |"
            % (m["pack"], m["path"], m.get("candidate_id") or m.get("seed_id") or m.get("reason", ""))
        )
    (hub / "INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")


def _chart_pack_a(path, er, cand, out_by_id, pivots_df, gby, h4, study_id, data_version, cfg_hash, gen_ts, tick):
    d = date.fromisoformat(str(er["ny_date"]))
    seed_ts = _localize(pd.Timestamp(er["seed_ts"]))
    # 4h window: 2 bars before seed through NY open bar
    if h4 is not None and not h4.empty:
        h4i = h4.copy()
        h4i.index = pd.DatetimeIndex([_localize(x) for x in h4i.index])
        before = h4i[h4i.index < seed_ts].tail(2)
        around = h4i[(h4i.index >= seed_ts - pd.Timedelta(hours=4)) & (h4i.index <= _ts_at(d, time(16, 0)))]
        h4_plot = pd.concat([before, around]).sort_index()
        h4_plot = h4_plot[~h4_plot.index.duplicated(keep="last")]
    else:
        h4_plot = pd.DataFrame()

    day = _day_rth(gby, d)
    inset = day[(day.index >= _ts_at(d, time(9, 20))) & (day.index < _ts_at(d, time(10, 40)))]
    out_panel = day[(day.index >= _ts_at(d, NY_OPEN)) & (day.index < _ts_at(d, OBS_END))]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={"height_ratios": [1.2, 1.0, 1.0]})
    ax0, ax1, ax2 = axes
    outcome = ""
    if cand is not None:
        o = out_by_id.get(cand["candidate_id"])
        outcome = o["outcome_label"] if o is not None else ""
    _header(
        ax0,
        [
            "%s | Pack A | %s | NY %s" % (study_id, er["seed_id"], er["ny_date"]),
            "data=%s | hash=%s | tz=America/New_York | gen=%s" % (data_version, cfg_hash, gen_ts),
            "seed_dir=%s pen_ATR=%.3f width_ATR=%.3f age_h=%.1f active=%s"
            % (
                er["seed_direction"],
                float(er["penetration_atr"]) if pd.notna(er["penetration_atr"]) else float("nan"),
                float(er["range_width_atr"]) if pd.notna(er["range_width_atr"]) else float("nan"),
                float(er["seed_age_hours"]),
                er["seed_active_at_open"],
            ),
            "outcome=%s" % (outcome or "(no candidate)"),
        ],
    )
    _plot_candles(ax0, h4_plot, width_min=180)
    sh, sl = float(er["seed_high"]), float(er["seed_low"])
    ax0.axhspan(sl, sh, color="#ffe9a8", alpha=0.35, zorder=1)
    ax0.axhline(sh, color="#b8860b", lw=1.0, label="SEED HIGH")
    ax0.axhline(sl, color="#b8860b", lw=1.0, label="SEED LOW")
    ax0.axvline(seed_ts, color="#8B4513", lw=1.2)
    ax0.axvline(_localize(pd.Timestamp(er["seed_available_at"])), color="#8B4513", lw=0.8, ls="--")
    ax0.axvline(_ts_at(d, NY_OPEN), color="black", lw=1.0)
    ax0.text(0.01, 0.02, "W=%.2f (%.0f ticks)" % (float(er["seed_width"]), float(er["seed_width"]) / tick), transform=ax0.transAxes, fontsize=8)
    ax0.set_ylabel("4h")

    _plot_candles(ax1, inset, width_min=1)
    _session_guides(ax1, d)
    _mark_pivots(ax1, pivots_df, er["seed_id"], er["ny_date"], cand)
    ax1.set_ylabel("1m 09:20–10:40")

    _plot_candles(ax2, out_panel, width_min=1)
    _session_guides(ax2, d)
    if cand is not None:
        prot = float(cand["protected_price"])
        ax2.axhline(prot, color="#000080", lw=1.5)
        if cand["pattern"] == "BEAR":
            ax2.axhline(prot + tick, color="#aa0000", lw=1.0, ls="--")
        else:
            ax2.axhline(prot - tick, color="#aa0000", lw=1.0, ls="--")
        ax2.axvline(_localize(pd.Timestamp(cand["structure_complete_at"])), color="#444", lw=1.0)
    ax2.set_ylabel("1m to 13:00")
    fig.autofmt_xdate()
    _save(fig, path)


def _mark_pivots(ax, pivots_df, seed_id, ny_date, cand):
    if pivots_df is None or pivots_df.empty:
        return
    sub = pivots_df[(pivots_df["seed_id"] == seed_id) & (pivots_df["ny_date"] == ny_date)]
    for _, p in sub.iterrows():
        ts = _localize(pd.Timestamp(p["pivot_ts"]))
        ax.scatter([ts], [float(p["pivot_price"])], s=12, c="#666666", zorder=6, marker="o")
    if cand is None:
        return
    ids = [cand["p1_id"], cand["p2_id"], cand["p3_id"], cand["p4_id"]]
    prices = [cand["p1_price"], cand["p2_price"], cand["p3_price"], cand["p4_price"]]
    # use pivot ledger for timestamps
    xs, ys = [], []
    for i, pid in enumerate(ids):
        row = sub[sub["pivot_id"] == pid]
        if row.empty:
            continue
        ts = _localize(pd.Timestamp(row.iloc[0]["pivot_ts"]))
        px = float(prices[i])
        xs.append(ts)
        ys.append(px)
        ax.scatter([ts], [px], s=60, c="#000000", zorder=8, marker="o")
        ax.annotate("P%d" % (i + 1), (ts, px), textcoords="offset points", xytext=(0, 8), fontsize=8, ha="center")
    if len(xs) >= 2:
        ax.plot(xs, ys, color="#222222", lw=1.0, zorder=7)


def _chart_pack_b(path, er, cand, out, day, study_id, data_version, cfg_hash, gen_ts, tick):
    d = date.fromisoformat(str(cand["ny_date"]))
    complete = _localize(pd.Timestamp(cand["structure_complete_at"]))
    end = max(complete + pd.Timedelta(minutes=15), _ts_at(d, time(10, 45)))
    main = day[(day.index >= _ts_at(d, time(9, 20))) & (day.index <= end)]
    ext = day[(day.index >= _ts_at(d, NY_OPEN)) & (day.index < _ts_at(d, OBS_END))]

    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [1.3, 1.0]})
    _header(
        ax0,
        [
            "%s | Pack B | %s | %s | %s" % (study_id, cand["candidate_id"], cand["seed_id"], cand["ny_date"]),
            "pivot=1L/1R strict | hash=%s | %s" % (cfg_hash, data_version),
            "seed_dir=%s | pattern=%s | ctx=%s | vs_seed=%s | age_h=%.1f"
            % (
                er["seed_direction"],
                cand["pattern"],
                cand["seed_context_relation"],
                cand["1m_direction_vs_seed_direction"],
                float(cand["seed_age_hours"]),
            ),
            "gen=%s | break_dist=%.1f ticks | dur=%.0f min"
            % (gen_ts, float(cand["break_distance_ticks"]), float(cand["sequence_duration_minutes"])),
        ],
    )
    _plot_candles(ax0, main, width_min=1)
    _session_guides(ax0, d)
    ax0.axvline(complete, color="#000080", lw=1.2)
    ax0.text(complete, ax0.get_ylim()[1] if ax0.get_ylim() else 0, " STRUCTURE AVAILABLE", fontsize=7, va="top")
    _annotate_structure(ax0, cand, tick)
    ax0.set_ylabel("formation")

    _plot_candles(ax1, ext, width_min=1)
    _session_guides(ax1, d)
    prot = float(cand["protected_price"])
    ax1.axhline(prot, color="#000080", lw=1.5)
    ax1.axhline(float(cand["break_level"]), color="#666666", lw=0.9, ls=":")
    ax1.set_ylabel("to 13:00")
    fig.autofmt_xdate()
    _save(fig, path)


def _annotate_structure(ax, cand, tick):
    labels = {
        "BEAR": ["P1 H1", "P2 L1", "P3 HH / PROTECTED HIGH", "P4 LL / STRUCTURE CONFIRMED"],
        "BULL": ["P1 L1", "P2 H1", "P3 LL / PROTECTED LOW", "P4 HH / STRUCTURE CONFIRMED"],
    }
    labs = labels[cand["pattern"]]
    ts_keys = ["p1_ts", "p2_ts", "p3_ts", "p4_ts"]
    px_keys = ["p1_price", "p2_price", "p3_price", "p4_price"]
    xs, ys = [], []
    for i, (tk, pk) in enumerate(zip(ts_keys, px_keys)):
        ts = _localize(pd.Timestamp(cand[tk]))
        px = float(cand[pk])
        xs.append(ts)
        ys.append(px)
        ax.scatter([ts], [px], s=70, c="#000", zorder=8)
        ax.annotate(labs[i] + "\n%.2f" % px, (ts, px), textcoords="offset points", xytext=(0, 10), fontsize=7, ha="center")
    ax.plot(xs, ys, color="#222", lw=1.1, zorder=7)
    prot = float(cand["protected_price"])
    ax.axhline(prot, color="#000080", lw=1.6, label="protected")
    if cand["pattern"] == "BEAR":
        ax.axhline(prot + tick, color="#aa0000", lw=1.0, ls="--")
    else:
        ax.axhline(prot - tick, color="#aa0000", lw=1.0, ls="--")
    ax.axhline(float(cand["break_level"]), color="#666", lw=0.9, ls=":")
    # brackets as text
    if cand["pattern"] == "BEAR":
        ax.text(
            0.99,
            0.02,
            "HH-H1=%.1ft  L1-LL=%.1ft"
            % (
                (float(cand["hh_price"]) - float(cand["h1_price"])) / tick,
                (float(cand["l1_price"]) - float(cand["ll_price"])) / tick,
            ),
            transform=ax.transAxes,
            ha="right",
            fontsize=8,
        )
    else:
        ax.text(
            0.99,
            0.02,
            "L1-LL=%.1ft  HH-H1=%.1ft"
            % (
                (float(cand["l1_price"]) - float(cand["ll_price"])) / tick,
                (float(cand["hh_price"]) - float(cand["h1_price"])) / tick,
            ),
            transform=ax.transAxes,
            ha="right",
            fontsize=8,
        )


def _chart_pack_c(path, er, cand, out, day, study_id, data_version, cfg_hash, gen_ts, tick):
    d = date.fromisoformat(str(cand["ny_date"]))
    complete = _localize(pd.Timestamp(cand["structure_complete_at"]))
    panel = day[(day.index >= complete) & (day.index < _ts_at(d, OBS_END))]
    fig, ax = plt.subplots(1, 1, figsize=(12, 5.5))
    label = out["outcome_label"] if out is not None else "UNKNOWN"
    banners = {
        "HELD_NO_TOUCH": ("HELD TO 13:00 — NO TOUCH", "#0a7a3e"),
        "HELD_EQUAL_TOUCH": ("HELD TO 13:00 — EQUAL TOUCH", "#0a7a3e"),
        "FAILED_ONE_TICK_OR_MORE": ("FAILED — PROTECTED LEVEL BROKEN", "#a00000"),
        "INSUFFICIENT_DATA": ("INSUFFICIENT DATA — NO OUTCOME CLAIM", "#666666"),
    }
    ban, col = banners.get(label, (label, "#222"))
    _header(
        ax,
        [
            "%s | Pack C | %s | %s" % (study_id, cand["candidate_id"], cand["ny_date"]),
            "hash=%s | %s | gen=%s" % (cfg_hash, data_version, gen_ts),
        ],
    )
    _plot_candles(ax, panel, width_min=1)
    ax.axvspan(complete, _ts_at(d, OBS_END), color="#e8e8e8", alpha=0.4, zorder=1)
    ax.axvline(complete, color="#000080", lw=1.2)
    prot = float(cand["protected_price"])
    ax.axhline(prot, color="#000080", lw=2.0)
    if cand["pattern"] == "BEAR":
        ax.axhline(prot + tick, color="#aa0000", lw=1.1, ls="--")
    else:
        ax.axhline(prot - tick, color="#aa0000", lw=1.1, ls="--")
    _banner(ax, ban, col)
    if out is not None:
        ax.text(
            0.01,
            0.02,
            "MFE=%.1ft MAE=%.1ft"
            % (
                float(out["max_favorable_excursion_ticks"]) if pd.notna(out["max_favorable_excursion_ticks"]) else float("nan"),
                float(out["max_adverse_excursion_ticks"]) if pd.notna(out["max_adverse_excursion_ticks"]) else float("nan"),
            ),
            transform=ax.transAxes,
            fontsize=8,
        )
        if label == "FAILED_ONE_TICK_OR_MORE" and out.get("failure_ts"):
            fts = _localize(pd.Timestamp(out["failure_ts"]))
            ax.scatter([fts], [float(out["failure_price"])], s=80, c="red", zorder=10, marker="X")
            ax.annotate(
                "FIRST FAILURE\n%s\n%.2f (%.1ft)"
                % (fts.strftime("%H:%M"), float(out["failure_price"]), float(out["failure_distance_ticks"])),
                (fts, float(out["failure_price"])),
                textcoords="offset points",
                xytext=(8, 8),
                fontsize=7,
                color="#a00000",
            )
        if label == "HELD_EQUAL_TOUCH" and out.get("first_equal_touch_ts"):
            ets = _localize(pd.Timestamp(out["first_equal_touch_ts"]))
            ax.annotate("EQ TOUCH", (ets, prot), textcoords="offset points", xytext=(0, -12), fontsize=7, ha="center")
    fig.autofmt_xdate()
    _save(fig, path)


def _chart_pack_d(path, er, meta, pivots_df, gby, study_id, data_version, cfg_hash, gen_ts, tick):
    d = date.fromisoformat(str(er["ny_date"]))
    day = _day_rth(gby, d)
    panel = day[(day.index >= _ts_at(d, time(9, 20))) & (day.index < _ts_at(d, time(10, 45)))]
    fig, ax = plt.subplots(1, 1, figsize=(12, 5.5))
    reason = str(meta.get("reason") or "OTHER_DOCUMENTED_REASON")
    near = str(meta.get("near_miss") or "")
    _header(
        ax,
        [
            "%s | Pack D | %s | %s" % (study_id, er["seed_id"], er["ny_date"]),
            "hash=%s | %s | gen=%s" % (cfg_hash, data_version, gen_ts),
        ],
    )
    _plot_candles(ax, panel, width_min=1)
    _session_guides(ax, d)
    sh, sl = float(er["seed_high"]), float(er["seed_low"])
    ax.axhspan(sl, sh, color="#ffe9a8", alpha=0.3, zorder=1)
    ax.axhline(sh, color="#b8860b", lw=1.0)
    ax.axhline(sl, color="#b8860b", lw=1.0)
    if pivots_df is not None and not pivots_df.empty:
        sub = pivots_df[(pivots_df["seed_id"] == er["seed_id"]) & (pivots_df["ny_date"] == er["ny_date"])]
        sub = sub[sub["inside_open_window"] == True]  # noqa: E712
        for _, p in sub.iterrows():
            ax.scatter(
                [_localize(pd.Timestamp(p["pivot_ts"]))],
                [float(p["pivot_price"])],
                s=18,
                c="#444",
                zorder=6,
            )
    _banner(ax, reason, "#663399")
    if near:
        ax.text(0.5, 0.90, near, transform=ax.transAxes, ha="center", fontsize=8, color="#663399")
    fig.autofmt_xdate()
    _save(fig, path)
