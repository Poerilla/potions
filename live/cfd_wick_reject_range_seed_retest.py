"""CFD replication of frozen NQ WICK_REJECT range-seed limit-retest.

Research / portability study only — NOT a demo candidate.
Does not change session definitions, penetration, range-age, targets,
retest life, or stop logic per CFD. No CHOP20 filters.

Markets (order): NAS100 → SPX500 → US30

Hub: live/state/cfd_wick_reject_range_seed_retest/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.cfd_wick_reject_range_seed_retest --email
  python -m live.cfd_wick_reject_range_seed_retest --market NAS100 --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import nq_wick_reject_range_seed_retest as nq_rt
from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .nq_structure_change_event_study import (
    HOLDOUT_FRAC,
    LOOKBACK_DAYS_4H,
    PEN_PRIMARY,
    assign_holdout,
    walk_tf,
)
from .run_ledger import begin_run, complete_run, fail_run
from .structure_program_st_chart_bias_4h import to_4h

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "cfd_wick_reject_range_seed_retest"
NY = "America/New_York"

# Same decision-box as NQ; CFD economics only (tick / point value / fee).
DEFAULT_MARKETS = ("NAS100", "SPX500", "US30")
MIN_RTH_DAYS = 500  # below → insufficient (not failed)
MIN_ELIGIBLE_SEEDS = 15


@dataclass(frozen=True)
class CfdSpec:
    key: str
    symbol: str
    one_m: Path
    tick: float
    point_value: float
    fee: float
    role: str


SPECS: Dict[str, CfdSpec] = {
    "NAS100": CfdSpec(
        "nas100",
        "NAS100",
        REPO / "fx" / "nas100_1m.csv",
        0.1,
        1.0,
        1.50,
        "implementation_parity_vs_NQ",
    ),
    "SPX500": CfdSpec(
        "spx500",
        "SPX500",
        REPO / "fx" / "spx500_1m.csv",
        0.1,
        1.0,
        1.50,
        "independent_index_cfd",
    ),
    "US30": CfdSpec(
        "us30",
        "US30",
        REPO / "fx" / "us30_1m.csv",
        0.1,
        1.0,
        1.50,
        "independent_index_cfd",
    ),
}


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _apply_economics(spec: CfdSpec) -> None:
    """Patch frozen NQ retest module economics without changing decision rules."""
    nq_rt.TICK = float(spec.tick)
    nq_rt.POINT_VALUE = float(spec.point_value)
    nq_rt.FEE = float(spec.fee)


def _stress_ns(filled: pd.DataFrame) -> Tuple[float, float]:
    """Close-to-close campaign equity stress (max DD) and N/S."""
    if filled is None or filled.empty:
        return 0.0, 0.0
    df = filled.copy()
    df["_ts"] = pd.to_datetime(df["fill_ts"], utc=True, errors="coerce")
    df = df.sort_values("_ts")
    eq = df["net_usd"].astype(float).cumsum()
    peak = eq.cummax()
    dd = eq - peak
    stress = float(dd.min()) if len(dd) else 0.0
    net = float(eq.iloc[-1]) if len(eq) else 0.0
    ns = net / abs(stress) if stress < 0 else (float("inf") if net > 0 else 0.0)
    return stress, ns


def _tp_contribution(filled: pd.DataFrame) -> dict:
    if filled is None or filled.empty:
        return {"tp1_share": 0.0, "tp2_share": 0.0, "runner_share": 0.0, "stop_share": 0.0}
    # Approximate from hit flags + net: fraction of fills that reached each stage.
    return {
        "tp1_hit_rate": float(filled["hit_tp1"].mean()) if "hit_tp1" in filled else 0.0,
        "tp2_hit_rate": float(filled["hit_tp2"].mean()) if "hit_tp2" in filled else 0.0,
        "runner_hit_rate": float(filled["hit_tp3"].mean()) if "hit_tp3" in filled else 0.0,
        "stop_rate": float(filled["stopped"].mean()) if "stopped" in filled else 0.0,
    }


def build_wick_events(
    *,
    gby: Dict[date, pd.DataFrame],
    spec: CfdSpec,
    smoke: bool,
) -> Tuple[pd.DataFrame, dict]:
    days = sorted(gby)
    if smoke:
        days = days[:120]
    meta = {
        "rth_days": len(days),
        "first_day": days[0].isoformat() if days else "",
        "last_day": days[-1].isoformat() if days else "",
        "insufficient": False,
        "insufficient_reason": "",
    }
    if len(days) < MIN_RTH_DAYS and not smoke:
        meta["insufficient"] = True
        meta["insufficient_reason"] = "rth_days<%d" % MIN_RTH_DAYS
        return pd.DataFrame(), meta

    ev4, _snaps = walk_tf(
        gby=gby,
        tf_name="4h",
        hours=4.0,
        resample_fn=to_4h,
        lookback_days=LOOKBACK_DAYS_4H,
        days=days,
        min_pen=PEN_PRIMARY,
    )
    if not ev4:
        meta["insufficient"] = True
        meta["insufficient_reason"] = "no_structure_events"
        return pd.DataFrame(), meta

    edf = pd.DataFrame(ev4)
    edf["market"] = spec.key
    edf["symbol"] = spec.symbol
    edf["penetration_ticks"] = pd.to_numeric(edf["penetration_points"], errors="coerce") / spec.tick
    # Holdout on 4h invalidation pen=0.05 population (same frac as NQ).
    primary = edf[
        (edf["structure_timeframe"] == "4h")
        & (edf["event_family"] == "invalidation")
        & (pd.to_numeric(edf["min_pen_ATR"], errors="coerce") == PEN_PRIMARY)
    ].copy()
    primary = assign_holdout(primary)
    wick = primary[
        (primary["event_type"] == "WICK_REJECT")
        & (pd.to_numeric(primary["min_pen_ATR"], errors="coerce") == PEN_PRIMARY)
    ].copy()
    wick = wick.sort_values(["confirm_bar_close_ts", "event_id"]).reset_index(drop=True)
    meta["atlas_4h_inv"] = int(len(primary))
    meta["wick_reject_n"] = int(len(wick))
    meta["holdout_frac"] = HOLDOUT_FRAC
    return wick, meta


def run_market(
    *,
    hub: Path,
    spec: CfdSpec,
    smoke: bool,
) -> dict:
    mhub = hub / spec.key
    mhub.mkdir(parents=True, exist_ok=True)
    (mhub / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress(hub, "%s: start" % spec.symbol)

    out: dict = {
        "symbol": spec.symbol,
        "key": spec.key,
        "role": spec.role,
        "status": "pending",
        "hub": str(mhub.relative_to(REPO)),
    }

    if not spec.one_m.exists():
        out["status"] = "insufficient"
        out["reason"] = "missing_1m:%s" % spec.one_m
        (mhub / "STATUS.md").write_text(
            "# %s — insufficient\n\nMissing 1m history: `%s`\n" % (spec.symbol, spec.one_m),
            encoding="utf-8",
        )
        return out

    _progress(hub, "%s: load 1m" % spec.symbol)
    gby = load_fx_1m_by_ny_date(spec.one_m, spec.symbol)
    if smoke:
        days = sorted(gby)[:120]
        gby = {d: gby[d] for d in days}

    _progress(hub, "%s: build WICK_REJECT atlas (4h)" % spec.symbol)
    events, atlas_meta = build_wick_events(gby=gby, spec=spec, smoke=smoke)
    (mhub / "atlas_meta.json").write_text(json.dumps(atlas_meta, indent=2), encoding="utf-8")
    out.update(atlas_meta)

    if atlas_meta.get("insufficient"):
        out["status"] = "insufficient"
        out["reason"] = atlas_meta.get("insufficient_reason", "insufficient")
        (mhub / "STATUS.md").write_text(
            "# %s — insufficient\n\n%s\n\n```json\n%s\n```\n"
            % (spec.symbol, out["reason"], json.dumps(atlas_meta, indent=2)),
            encoding="utf-8",
        )
        return out

    events.to_csv(mhub / "structure_events_wick_reject.csv", index=False)
    _progress(hub, "%s: wick events n=%d" % (spec.symbol, len(events)))

    _apply_economics(spec)
    _progress(hub, "%s: build RTH tape" % spec.symbol)
    tape, h1, h4, early = nq_rt.build_rth_tape(gby)
    _progress(hub, "%s: tape=%d 1h=%d 4h=%d" % (spec.symbol, len(tape), len(h1), len(h4)))

    _progress(hub, "%s: Phase 0 census" % spec.symbol)
    seeds, census = nq_rt.make_seeds(events, tape, h4, early)
    census.to_csv(mhub / "phase0_census.csv", index=False)
    n_elig = len(seeds)
    out["eligible_seeds"] = n_elig
    out["rejected"] = int(len(census) - n_elig) if len(census) else 0
    if n_elig < MIN_ELIGIBLE_SEEDS and not smoke:
        out["status"] = "insufficient"
        out["reason"] = "eligible_seeds<%d" % MIN_ELIGIBLE_SEEDS
        _write_census_only(mhub, spec, census, seeds, out)
        return out

    # --- census-first artifact (before P&L) ---
    path_rows = []
    for i, seed in enumerate(seeds):
        s = nq_rt.Seed(**{**seed.__dict__})
        nq_rt.simulate_seed_path(s, h1, tape)
        path_rows.append(
            {
                "seed_id": s.seed_id,
                "event_id": s.event_id,
                "slice": s.slice,
                "high": s.high,
                "low": s.low,
                "width": s.width,
                "width_ATR": s.width / s.atr20_4h if s.atr20_4h else np.nan,
                "state": s.state,
                "terminal_reason": s.terminal_reason,
                "first_break_side": s.first_break_side,
                "break_confirm_ts": s.break_confirm_ts.isoformat() if s.break_confirm_ts else "",
                "both_sides_broke": s.both_sides_broke,
                "retest_eligible": s.retest_eligible,
                "retest_hold": s.retest_hold,
                "time_seed_to_break_min": s.time_seed_to_break_min,
                "persist_1": s.persist_1,
                "persist_2": s.persist_2,
                "persist_4": s.persist_4,
                "reentry_inside": s.reentry_inside,
                "hit_0_5w": s.hit_0_5w,
                "hit_1w": s.hit_1w,
                "hit_2w": s.hit_2w,
            }
        )
        if (i + 1) % 25 == 0:
            _progress(hub, "%s: path %d/%d" % (spec.symbol, i + 1, len(seeds)))
    seeds_df = pd.DataFrame(path_rows)
    seeds_df.to_csv(mhub / "phase1_path.csv", index=False)

    n_break = int((seeds_df["first_break_side"].astype(str).str.len() > 0).sum()) if len(seeds_df) else 0
    n_orders = n_break  # retest order placed after each confirmed break
    out["confirmed_breaks"] = n_break
    out["retest_orders_placed"] = n_orders
    _write_census_doc(mhub, spec, census, seeds_df, out)
    _progress(hub, "%s: census written (breaks=%d) — P&L next" % (spec.symbol, n_break))

    primary_rows = []
    for i, seed in enumerate(seeds):
        primary_rows.append(nq_rt.run_primary_trade(seed, tape, h1))
        if (i + 1) % 25 == 0:
            _progress(hub, "%s: trades %d/%d" % (spec.symbol, i + 1, len(seeds)))
    trades = pd.DataFrame([r for r in primary_rows if r])
    trades.to_csv(mhub / "trades_primary.csv", index=False)

    filled = trades[trades["outcome"] == "FILLED"] if len(trades) else trades
    expired = trades[trades["outcome"] != "FILLED"] if len(trades) else trades
    out["limit_fills"] = int(len(filled))
    out["expired_cancelled"] = int(len(expired))
    out["fill_rate"] = float(len(filled) / len(trades)) if len(trades) else 0.0

    summaries = []
    for sl in ("dev", "holdout", "ALL"):
        sub = trades if sl == "ALL" else trades[trades["slice"] == sl] if "slice" in trades.columns else trades
        s = nq_rt._summarize_trades(sub, "primary_limit_retest_%s" % sl)
        fsub = sub[sub["outcome"] == "FILLED"] if "outcome" in sub.columns else sub
        stress, ns = _stress_ns(fsub)
        s["stress_dd_usd"] = stress
        s["ns"] = ns
        s.update(_tp_contribution(fsub))
        # width / stop distance on filled
        if len(fsub):
            s["median_width"] = float(fsub["width"].median())
            s["median_risk_pts"] = float(fsub["risk_pts"].median()) if "risk_pts" in fsub else float("nan")
            s["mean_stop_distance"] = float(fsub["risk_pts"].mean()) if "risk_pts" in fsub else float("nan")
        else:
            s["median_width"] = float("nan")
            s["median_risk_pts"] = float("nan")
            s["mean_stop_distance"] = float("nan")
        summaries.append(s)
    pd.DataFrame(summaries).to_csv(mhub / "summary.csv", index=False)
    out["summaries"] = summaries

    # Stance vs decision matrix (local read; parent synthesizes)
    hold = next((s for s in summaries if s["label"].endswith("_holdout")), None)
    dev = next((s for s in summaries if s["label"].endswith("_dev")), None)
    out["dev_avg_R"] = float(dev["avg_R"]) if dev else float("nan")
    out["holdout_avg_R"] = float(hold["avg_R"]) if hold else float("nan")
    out["dev_net"] = float(dev["net_usd"]) if dev else 0.0
    out["holdout_net"] = float(hold["net_usd"]) if hold else 0.0
    out["dev_ns"] = float(dev.get("ns") or 0.0) if dev else 0.0
    out["holdout_ns"] = float(hold.get("ns") or 0.0) if hold else 0.0
    out["status"] = "complete"
    _write_market_summary(mhub, spec, census, seeds_df, summaries, out, smoke=smoke)
    _progress(
        hub,
        "%s: DONE fills=%d holdout_avgR=%+.3f"
        % (spec.symbol, out["limit_fills"], out["holdout_avg_R"]),
    )
    return out


def _write_census_only(mhub: Path, spec: CfdSpec, census: pd.DataFrame, seeds: list, out: dict) -> None:
    lines = [
        "# %s — census only (insufficient)" % spec.symbol,
        "",
        "**Status:** insufficient — %s" % out.get("reason", ""),
        "**Eligible seeds:** %d" % out.get("eligible_seeds", 0),
        "",
    ]
    if len(census):
        reasons = census.loc[census["eligible"] == 0, "reject_reason"].value_counts().to_dict()
        lines.append("Reject reasons: `%s`" % reasons)
    (mhub / "CENSUS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (mhub / "STATUS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_census_doc(
    mhub: Path,
    spec: CfdSpec,
    census: pd.DataFrame,
    seeds_df: pd.DataFrame,
    out: dict,
) -> None:
    n_events = int(out.get("wick_reject_n", len(census)))
    n_elig = int(out.get("eligible_seeds", 0))
    reasons = {}
    if len(census):
        reasons = census.loc[census["eligible"] == 0, "reject_reason"].value_counts().to_dict()
    width = seeds_df["width"] if len(seeds_df) and "width" in seeds_df else pd.Series(dtype=float)
    w_atr = seeds_df["width_ATR"] if len(seeds_df) and "width_ATR" in seeds_df else pd.Series(dtype=float)
    lines = [
        "# %s — range-seed census (pre-P&L)" % spec.symbol,
        "",
        "**Model:** frozen NQ WICK_REJECT → 1h break → limit retest (CFD economics only).",
        "**Role:** %s" % spec.role,
        "**Horizon:** %s → %s (%d RTH days)"
        % (out.get("first_day"), out.get("last_day"), out.get("rth_days", 0)),
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Atlas 4h WICK_REJECT (pen≥0.05) | %d |" % n_events,
        "| Eligible seeds | %d |" % n_elig,
        "| Rejected | %d |" % out.get("rejected", 0),
        "| 1h confirmed breaks | %d |" % out.get("confirmed_breaks", 0),
        "| Retest orders placed | %d |" % out.get("retest_orders_placed", 0),
        "",
        "Reject reasons: `%s`" % reasons,
        "",
        "## Seed-width distribution (eligible)",
        "",
        "| Stat | points | ×4h ATR |",
        "|---|---:|---:|",
    ]
    if len(width):
        for name, q in [("min", 0.0), ("p25", 0.25), ("median", 0.5), ("p75", 0.75), ("max", 1.0)]:
            lines.append(
                "| %s | %.2f | %.3f |"
                % (name, float(width.quantile(q)), float(w_atr.quantile(q)) if len(w_atr) else float("nan"))
            )
    else:
        lines.append("| — | — | — |")
    lines.append("")
    (mhub / "CENSUS.md").write_text("\n".join(lines), encoding="utf-8")


def _write_market_summary(
    mhub: Path,
    spec: CfdSpec,
    census: pd.DataFrame,
    seeds_df: pd.DataFrame,
    summaries: List[dict],
    out: dict,
    *,
    smoke: bool,
) -> None:
    lines = [
        "# %s WICK_REJECT range-seed limit-retest (CFD replication)" % spec.symbol,
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Hub:** `%s/`" % mhub.relative_to(REPO),
        "**Stance:** RESEARCH only — not a demo candidate.",
        "**Model:** frozen NQ decision box; tick=%.2g point_value=%.2g fee=$%.2f"
        % (spec.tick, spec.point_value, spec.fee),
        "**Role:** %s" % spec.role,
        "**Mode:** %s" % ("SMOKE" if smoke else "FULL"),
        "",
        "See `CENSUS.md` for pre-P&L seed census.",
        "",
        "## Primary limit-retest",
        "",
        "| Book | seeds | fills | fill% | net $ | stress $ | N/S | WR | PF | avg R | med R | stop% | TP1/2/R% | gap | L/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.2f | %.0f%% | %.2f | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d | %d/%d |"
            % (
                s["label"],
                s["n_seeds"],
                s["n_filled"],
                100 * s["fill_rate"],
                s["net_usd"],
                s.get("stress_dd_usd", 0.0),
                s.get("ns", 0.0) if s.get("ns", 0.0) != float("inf") else 99.0,
                100 * s["win_rate"],
                s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                s["avg_R"],
                s["median_R"],
                100 * s["stop_rate"],
                100 * s.get("tp1_hit_rate", s["hit_tp1_rate"]),
                100 * s.get("tp2_hit_rate", s["hit_tp2_rate"]),
                100 * s.get("runner_hit_rate", s["hit_tp3_rate"]),
                s["gap_through_n"],
                s["long_n"],
                s["short_n"],
            )
        )
    lines.extend(
        [
            "",
            "## Local read",
            "",
            "- Dev avg R **%+.3f** / holdout avg R **%+.3f**"
            % (out.get("dev_avg_R", float("nan")), out.get("holdout_avg_R", float("nan"))),
            "- Fills %d / expired-cancelled %d (fill rate %.0f%%)"
            % (out.get("limit_fills", 0), out.get("expired_cancelled", 0), 100 * out.get("fill_rate", 0.0)),
            "- Top5 |net| share (ALL): see summary top5_share.",
            "",
            "Parent decision matrix: `../DECISION_MATRIX.md`.",
            "",
        ]
    )
    (mhub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (mhub / "STATUS.md").write_text(
        "# Status — %s CFD limit-retest\n\n**Status:** complete (research only)\n**Holdout avg R:** %+.3f\n"
        % (spec.symbol, out.get("holdout_avg_R", float("nan"))),
        encoding="utf-8",
    )
    (mhub / "MODEL_CONTRACT.yaml").write_text(
        "\n".join(
            [
                "study_id: cfd_wick_reject_range_seed_retest",
                "symbol: %s" % spec.symbol,
                "inherits: nq_wick_reject_range_seed_retest",
                "demo_candidate: false",
                'seed: "4h WICK_REJECT; pen>=0.05; width 0.25–2.00×ATR; max_age 20×4h"',
                'break: "1h body close outside seeded boundary"',
                'entry: "resting limit at broken boundary; 24h life"',
                'stop: "opposite boundary ±1 tick"',
                'targets: "0.5W/1W/2W 50/25/25"',
                "tick: %s" % spec.tick,
                "point_value: %s" % spec.point_value,
                "fee: %s" % spec.fee,
                "chop20_filter: false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _decision_matrix(results: List[dict]) -> Tuple[str, str]:
    """Return (matrix_md, stance_line)."""
    by = {r["symbol"]: r for r in results}
    nas = by.get("NAS100", {})
    spx = by.get("SPX500", {})
    us30 = by.get("US30", {})

    def _hold_pos(r: dict) -> Optional[bool]:
        if r.get("status") != "complete":
            return None
        ar = r.get("holdout_avg_R")
        if ar is None or (isinstance(ar, float) and ar != ar):
            return None
        return float(ar) > 0

    nas_h = _hold_pos(nas)
    nas_dev = (nas.get("dev_avg_R") or 0) > 0 if nas.get("status") == "complete" else None
    spx_h = _hold_pos(spx)
    us30_h = _hold_pos(us30)

    # NQ reference (frozen hub): holdout avg R failed
    nq_hold_fail = True
    nq_dev_pos = True

    if all(r.get("status") == "insufficient" for r in results):
        stance = "INSUFFICIENT_DATA — mark markets insufficient, not failed."
    elif all(r.get("status") == "complete" and not _hold_pos(r) for r in results if r.get("status") == "complete") and any(
        r.get("status") == "complete" for r in results
    ):
        stance = (
            "ALL_CFDs_FAIL_HOLDOUT — treat NQ result as likely sample-specific or futures-path-specific. "
            "Still research only."
        )
    elif nas_h and nq_hold_fail is False:
        # unreachable placeholder — NQ holdout known failed; kept for contract completeness
        stance = "NAS100_AND_NQ_HOLDOUT_POS — Nasdaq-complex research candidate; no demo until Engine port."
    elif nas_dev and nas_h is False:
        stance = (
            "NAS100_MATCHES_NQ_PATTERN — positive development, fails holdout. "
            "Still research only; supports data-path/execution portability only."
        )
    elif nas_h and (spx_h or us30_h):
        stance = "BROADER_INDEX_HOLD — stronger evidence of index mechanism; still no demo."
    elif nas_h:
        stance = "NAS100_HOLDOUT_POS_ONLY — Nasdaq-complex research signal; SPX/US30 weak or incomplete; no demo."
    else:
        stance = "RESEARCH — see per-market holdout; not a demo candidate."

    # Refine with SPX/US30 both holding
    if nas_h and spx_h and us30_h:
        stance = (
            "SPX500_US30_ALSO_HOLD — stronger evidence of broader index mechanism. "
            "Still research only; no demo until Engine port + overlap measured."
        )

    lines = [
        "# CFD decision matrix — WICK_REJECT limit-retest replication",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**NQ reference:** locked primary holdout avg R failed (research signal only).",
        "**Demo:** blocked for all CFD rows.",
        "",
        "## Matrix",
        "",
        "| Rule | Result |",
        "|---|---|",
        "| NAS100 matches NQ (dev+/holdout−) | %s |"
        % ("YES" if (nas_dev and nas_h is False) else "no / partial"),
        "| NAS100 + NQ both holdout+ | no (NQ holdout failed) |",
        "| SPX500 holdout+ | %s |" % ("YES" if spx_h else ("insufficient" if spx.get("status") == "insufficient" else "no")),
        "| US30 holdout+ | %s |" % ("YES" if us30_h else ("insufficient" if us30.get("status") == "insufficient" else "no")),
        "| All CFDs fail holdout | %s |"
        % (
            "YES"
            if all(r.get("status") == "complete" and not _hold_pos(r) for r in results if r.get("status") == "complete")
            and any(r.get("status") == "complete" for r in results)
            else "no"
        ),
        "",
        "## Stance",
        "",
        stance,
        "",
        "## Per-market snapshot",
        "",
        "| Market | status | elig | fills | fill% | dev avgR | hold avgR | hold net | hold N/S |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sym in DEFAULT_MARKETS:
        r = by.get(sym, {})
        if not r:
            lines.append("| %s | missing | — | — | — | — | — | — | — |" % sym)
            continue
        if r.get("status") != "complete":
            lines.append(
                "| %s | %s | %s | — | — | — | — | — | — |"
                % (sym, r.get("status"), r.get("eligible_seeds", "—"))
            )
            continue
        hold = next((s for s in r.get("summaries", []) if s["label"].endswith("_holdout")), {})
        lines.append(
            "| %s | complete | %d | %d | %.0f%% | %+.3f | %+.3f | %+.0f | %.2f |"
            % (
                sym,
                r.get("eligible_seeds", 0),
                r.get("limit_fills", 0),
                100 * r.get("fill_rate", 0.0),
                r.get("dev_avg_R", float("nan")),
                r.get("holdout_avg_R", float("nan")),
                hold.get("net_usd", 0.0),
                hold.get("ns", 0.0) if hold.get("ns", 0.0) != float("inf") else 99.0,
            )
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No CHOP20 filters.",
            "- No per-CFD rule retune.",
            "- NAS100 ≠ independent confirmation of NQ.",
            "- XAUUSD not in this batch (separate metals family if ever run).",
            "",
        ]
    )
    return "\n".join(lines), stance


def write_parent_docs(hub: Path, results: List[dict], *, smoke: bool) -> str:
    # Cross-market census board first
    census_lines = [
        "# Cross-market range-seed census",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Note:** Census compiled before / with P&L; do not re-tune rules from this board.",
        "",
        "| Market | RTH days | horizon | wick events | eligible | breaks | orders | fills | fill% | status |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for sym in DEFAULT_MARKETS:
        r = next((x for x in results if x["symbol"] == sym), {})
        census_lines.append(
            "| %s | %s | %s→%s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                sym,
                r.get("rth_days", "—"),
                r.get("first_day", "—"),
                r.get("last_day", "—"),
                r.get("wick_reject_n", "—"),
                r.get("eligible_seeds", "—"),
                r.get("confirmed_breaks", "—"),
                r.get("retest_orders_placed", "—"),
                r.get("limit_fills", "—"),
                ("%.0f%%" % (100 * r["fill_rate"])) if "fill_rate" in r else "—",
                r.get("status", "—"),
            )
        )
    census_lines.append("")
    (hub / "CENSUS_BOARD.md").write_text("\n".join(census_lines), encoding="utf-8")

    matrix, stance = _decision_matrix(results)
    (hub / "DECISION_MATRIX.md").write_text(matrix, encoding="utf-8")

    summary = [
        "# CFD WICK_REJECT range-seed limit-retest replication",
        "",
        "**Hub:** `live/state/cfd_wick_reject_range_seed_retest/`",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Frozen model:** NQ `nq_wick_reject_range_seed_retest` decision box (no rule changes).",
        "**Role:** portability / research — **not** a demo candidate.",
        "**V2B:** separate conditional-exposure experiment (not combined here).",
        "**Mode:** %s" % ("SMOKE" if smoke else "FULL"),
        "",
        "## Stance",
        "",
        stance,
        "",
        "See `CENSUS_BOARD.md` and `DECISION_MATRIX.md`.",
        "",
        "## Markets",
        "",
    ]
    for r in results:
        summary.append(
            "- **%s** (`%s/`): %s — holdout avgR=%s"
            % (
                r["symbol"],
                r.get("key", ""),
                r.get("status"),
                ("%+.3f" % r["holdout_avg_R"]) if r.get("status") == "complete" else "n/a",
            )
        )
    summary.append("")
    (hub / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")
    (hub / "STATUS.md").write_text(
        "# Status — CFD limit-retest replication\n\n**Stance:** %s\n**Demo:** blocked\n"
        % stance,
        encoding="utf-8",
    )
    (hub / "MODEL_CONTRACT.yaml").write_text(
        "\n".join(
            [
                "study_id: cfd_wick_reject_range_seed_retest",
                "inherits: nq_wick_reject_range_seed_retest",
                "demo_candidate: false",
                "markets: [NAS100, SPX500, US30]",
                "chop20_filter: false",
                "v2b_hybrid: false",
                "purpose: portability_replication",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return stance


def build_email(hub: Path, results: List[dict], stance: str) -> str:
    lines = [
        "potions: CFD WICK_REJECT limit-retest replication COMPLETE",
        "",
        "Hub: %s" % hub,
        "Stance: %s" % stance,
        "Demo: blocked (research only)",
        "",
    ]
    for r in results:
        if r.get("status") != "complete":
            lines.append("  %s: %s (%s)" % (r["symbol"], r.get("status"), r.get("reason", "")))
            continue
        lines.append(
            "  %s: elig=%d fills=%d fill=%.0f%% devR=%+.3f holdR=%+.3f holdNet=%+.0f"
            % (
                r["symbol"],
                r.get("eligible_seeds", 0),
                r.get("limit_fills", 0),
                100 * r.get("fill_rate", 0.0),
                r.get("dev_avg_R", float("nan")),
                r.get("holdout_avg_R", float("nan")),
                r.get("holdout_net", 0.0),
            )
        )
    lines.extend(["", "See CENSUS_BOARD.md + DECISION_MATRIX.md.", ""])
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument(
        "--market",
        action="append",
        default=[],
        help="Repeatable; default NAS100 SPX500 US30",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    markets = [m.upper() for m in (args.market or list(DEFAULT_MARKETS))]
    for m in markets:
        if m not in SPECS:
            raise SystemExit("unknown market %s; choose from %s" % (m, sorted(SPECS)))

    rid = begin_run(
        run_class="pandas",
        variant_slug="cfd_wick_reject_range_seed_retest",
        instrument=",".join(markets),
        hub_path=str(hub.relative_to(REPO)),
        meta={"smoke": args.smoke, "markets": markets, "demo_candidate": False},
    )
    try:
        if args.email:
            start = (
                "potions: CFD WICK_REJECT limit-retest STARTED\n\n"
                "Hub: %s\nMarkets: %s\nFrozen NQ model; research only; no demo.\n"
                % (hub, ",".join(markets))
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: CFD WICK_REJECT limit-retest STARTED", body=start)

        results: List[dict] = []
        for sym in markets:
            results.append(run_market(hub=hub, spec=SPECS[sym], smoke=args.smoke))
            # Write census board incrementally (before finishing all P&L if multi-market)
            write_parent_docs(hub, results, smoke=args.smoke)

        stance = write_parent_docs(hub, results, smoke=args.smoke)
        body = build_email(hub, results, stance)
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"stance": stance, "smoke": args.smoke, "results": results}, indent=2, default=str),
            encoding="utf-8",
        )

        # Ledger: one row per completed market + parent
        nets = [r.get("holdout_net", 0.0) for r in results if r.get("status") == "complete"]
        complete_run(
            rid,
            net_usd=float(sum(nets)) if nets else 0.0,
            trades=int(sum(r.get("limit_fills", 0) for r in results)),
            meta={"stance": stance, "markets": [r.get("status") for r in results]},
        )
        if args.email:
            send_email(subject="potions: CFD WICK_REJECT limit-retest COMPLETE", body=body)
            _progress(hub, "email sent")
        _progress(hub, "DONE %s" % stance[:80])
        return 0
    except Exception as e:
        fail_run(rid, notes=str(e))
        err = traceback.format_exc()
        _progress(hub, "FAILED: %s" % e)
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: CFD WICK_REJECT limit-retest FAILED",
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
