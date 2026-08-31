"""US30 PMC confirmed fade × causal 4h StructureProgramEngine bias overlay.

Pre-registered trial TRL-2026-00189 (see
``live/state/us30_pmc_failed_break_fade_structure_bias/RESEARCH_PLAN.md``).

Reuses parent confirmed tape (TRL-2026-00187); attaches causal 4h bias at
``confirm_ts``; Phase 1 descriptive split; Phase 2 baseline | aligned_only |
aligned_plus_neut; scale-out diagnostics (report only).

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.us30_pmc_failed_break_fade_structure_bias --email
  python -m live.us30_pmc_failed_break_fade_structure_bias --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .structure_program_st_chart_bias_4h import LOOKBACK_DAYS, to_4h
from .structure_program_st_study import StructureProgramEngine, rth_slice
from .us30_pmc_failed_break_fade import (
    ENTRY_QTY,
    FEE_PER_UNIT,
    POINT_VALUE,
    TP_LADDER,
    TP_QTY,
    OpenFade,
    _localize,
    _manage_open,
    _metrics,
    _runner_share,
    _yearly,
)

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "us30_pmc_failed_break_fade_structure_bias"
PARENT_HUB = REPO / "live" / "state" / "us30_pmc_failed_break_fade"
PARENT_CONFIRMED = PARENT_HUB / "replay" / "confirmed"
ONE_M = REPO / "fx" / "us30_1m.csv"
SYM = "US30"
NY = "America/New_York"
DSR = "TRL-2026-00189"
PARENT_DSR = "TRL-2026-00187"
BAR_HOURS = 4

ALIGN_GROUPS = ("ALIGNED", "OPPOSED", "NEUTRAL", "UNAVAILABLE")
PHASE2_VARIANTS = ("baseline", "aligned_only", "aligned_plus_neut")
SCALE_PLANS = ("full_1r_2r_4r", "no_runner_cap_2r", "reduced_runner_50_50")


# ---------------------------------------------------------------------------
# Causal 4h bias timeline
# ---------------------------------------------------------------------------


def _bias_label(ready: bool, program: Optional[str]) -> str:
    if not ready:
        return "UNAVAILABLE"
    if program == "buy":
        return "BULLISH"
    if program == "sell":
        return "BEARISH"
    return "NEUTRAL"


def _alignment(bias: str, side: str) -> str:
    if bias == "UNAVAILABLE":
        return "UNAVAILABLE"
    if bias == "NEUTRAL":
        return "NEUTRAL"
    if bias == "BULLISH":
        return "ALIGNED" if side == "LONG" else "OPPOSED"
    if bias == "BEARISH":
        return "ALIGNED" if side == "SHORT" else "OPPOSED"
    return "UNAVAILABLE"


def build_causal_4h_snapshots(gby: Dict[date, pd.DataFrame], *, smoke: bool = False) -> pd.DataFrame:
    """Walk StructureProgramEngine on completed 4h RTH bars; record causal snaps.

    ``structure_feature_available_at`` = bar_start + 4h (= structure_bar_end_ts).
    """
    eng = StructureProgramEngine()
    buf: List[pd.DataFrame] = []
    rows: List[dict] = []
    days = sorted(gby)
    if smoke:
        days = days[:80]

    # Per-bar ingest: replicate _ingest_4h_day but snapshot after each bar.
    from .structure_program_st_study import confirm_swings, try_form_structures
    from .structure_program_st_chart_bias_4h import _active_key

    print("Walking causal 4h StructureProgramEngine over %d days…" % len(days), flush=True)
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        b4 = to_4h(rth)
        if b4.empty:
            continue

        frames = [b for b in buf[-LOOKBACK_DAYS:] if b is not None and not b.empty]
        frames.append(b4)
        combined = pd.concat(frames)
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        day_start = b4.index[0]

        day_swings = confirm_swings(combined)
        by_confirm: Dict[pd.Timestamp, list] = {}
        for sw in day_swings:
            if sw[0] < day_start:
                continue
            by_confirm.setdefault(sw[0], []).append(sw)

        for ts, row in b4.iterrows():
            for sw in by_confirm.get(ts, []):
                if eng.swings and eng.swings[-1][1] == sw[1]:
                    prev = eng.swings[-1]
                    if sw[1] == "H" and sw[2] >= prev[2]:
                        eng.swings[-1] = sw
                    elif sw[1] == "L" and sw[2] <= prev[2]:
                        eng.swings[-1] = sw
                    else:
                        continue
                else:
                    eng.swings.append(sw)
                for st in try_form_structures(eng.swings):
                    sig = (st.kind, round(st.key, 4), round(st.p4, 4), str(st.formed_ts))
                    if sig in eng._seen_structure_keys:
                        continue
                    eng._seen_structure_keys.add(sig)
                    if st.kind == "bull":
                        eng.bull.append(st)
                    else:
                        eng.bear.append(st)
            eng._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
            bar_end = pd.Timestamp(ts) + pd.Timedelta(hours=BAR_HOURS)
            if bar_end.tzinfo is None:
                bar_end = bar_end.tz_localize(NY)
            rows.append(
                {
                    "structure_bar_ts": pd.Timestamp(ts).isoformat(),
                    "structure_bar_end_ts": bar_end.isoformat(),
                    "structure_feature_available_at": bar_end.isoformat(),
                    "program": eng.program if eng.program is not None else "",
                    "ready": bool(eng.ready),
                    "bias": _bias_label(bool(eng.ready), eng.program),
                    "active_key": _active_key(eng),
                    "session_date": d.isoformat(),
                }
            )

        buf.append(b4)
        buf = buf[-LOOKBACK_DAYS:]
        if di % 250 == 0:
            print(
                "  %d/%d days | snaps %d | prog=%s ready=%s"
                % (di, len(days), len(rows), eng.program, eng.ready),
                flush=True,
            )

    print("Causal 4h snapshots: %d" % len(rows), flush=True)
    return pd.DataFrame(rows)


def lookup_bias_at(
    snaps: pd.DataFrame,
    confirm_ts: pd.Timestamp,
) -> Tuple[str, Optional[dict]]:
    """Last completed 4h structural state with available_at ≤ confirm_ts."""
    if snaps is None or snaps.empty:
        return "UNAVAILABLE", None
    conf = _localize(pd.Timestamp(confirm_ts))
    avail = pd.to_datetime(snaps["structure_feature_available_at"], utc=True).dt.tz_convert(NY)
    mask = avail <= conf
    if not mask.any():
        return "UNAVAILABLE", None
    i = int(np.where(mask.to_numpy())[0][-1])
    row = snaps.iloc[i]
    bias = str(row["bias"])
    return bias, row.to_dict()


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _r_multiples(tdf: pd.DataFrame) -> List[float]:
    out: List[float] = []
    for _, r in tdf.iterrows():
        risk = float(r.get("risk_r") or 0)
        if risk <= 0:
            continue
        one_r = risk * POINT_VALUE * float(r.get("units") or ENTRY_QTY)
        out.append(float(r["net_usd"]) / one_r if one_r else 0.0)
    return out


def metrics_from_subset(
    tdf: pd.DataFrame,
    udf: pd.DataFrame,
) -> Dict[str, float]:
    if tdf is None or tdf.empty:
        return {
            "net_usd": 0.0,
            "stress_dd_usd": 0.0,
            "ns": 0.0,
            "trades": 0,
            "units": 0,
            "win_rate": 0.0,
            "pf": 0.0,
            "avg_r": 0.0,
            "median_r": 0.0,
            "long_net": 0.0,
            "short_net": 0.0,
            "runner_net_share": 0.0,
            "close_mtm_dd_usd": 0.0,
            "hit_1r_rate": 0.0,
            "hit_2r_rate": 0.0,
            "hit_4r_rate": 0.0,
            "median_mae": 0.0,
            "median_mfe": 0.0,
        }
    tdf = tdf.sort_values("entry_ts")
    realized = 0.0
    peak = 0.0
    max_dd = 0.0
    for net in tdf["net_usd"].astype(float):
        realized += float(net)
        peak = max(peak, realized)
        max_dd = min(max_dd, realized - peak)
    m = _metrics(tdf, realized, max_dd)
    ids = set(tdf["trade_id"].astype(int))
    u_sub = udf[udf["trade_id"].astype(int).isin(ids)] if udf is not None and not udf.empty else pd.DataFrame()
    m["runner_net_share"] = _runner_share(u_sub)
    r_vals = _r_multiples(tdf)
    m["median_r"] = float(np.median(r_vals)) if r_vals else 0.0
    m["avg_r"] = float(np.mean(r_vals)) if r_vals else 0.0
    for col, key in (("hit_1r", "hit_1r_rate"), ("hit_2r", "hit_2r_rate"), ("hit_4r", "hit_4r_rate")):
        if col in tdf.columns:
            m[key] = float(tdf[col].astype(bool).mean())
        else:
            m[key] = 0.0
    m["median_mae"] = float(tdf["mae_pts"].median()) if "mae_pts" in tdf.columns else 0.0
    m["median_mfe"] = float(tdf["mfe_pts"].median()) if "mfe_pts" in tdf.columns else 0.0
    return m


def group_table_row(name: str, m: Dict[str, float]) -> dict:
    return {
        "group": name,
        "N": int(m.get("trades") or 0),
        "net_usd": float(m.get("net_usd") or 0),
        "stress_dd_usd": float(m.get("stress_dd_usd") or 0),
        "ns": float(m.get("ns") or 0),
        "pf": float(m.get("pf") or 0),
        "wr": float(m.get("win_rate") or 0),
        "median_r": float(m.get("median_r") or 0),
        "median_mae": float(m.get("median_mae") or 0),
        "median_mfe": float(m.get("median_mfe") or 0),
        "hit_1r": float(m.get("hit_1r_rate") or 0),
        "hit_2r": float(m.get("hit_2r_rate") or 0),
        "hit_4r": float(m.get("hit_4r_rate") or 0),
        "runner_share": float(m.get("runner_net_share") or 0),
        "long_net": float(m.get("long_net") or 0),
        "short_net": float(m.get("short_net") or 0),
    }


# ---------------------------------------------------------------------------
# Scale-out re-management (diagnostics)
# ---------------------------------------------------------------------------


def _targets_for_plan(plan: str, entry: float, stop: float, side: str) -> List[Tuple[float, int, str]]:
    risk = abs(entry - stop)
    if risk <= 0:
        return []
    if plan == "full_1r_2r_4r":
        ladder = list(zip(TP_LADDER, TP_QTY, ("tp_1r", "tp_2r", "tp_4r")))
    elif plan == "no_runner_cap_2r":
        # Fold 4R runner into 2R: 2@1R + 2@2R (cap).
        ladder = [(1.0, 2, "tp_1r"), (2.0, 2, "tp_2r")]
    elif plan == "reduced_runner_50_50":
        ladder = [(1.0, 2, "tp_1r"), (2.0, 2, "tp_2r")]
    else:
        raise ValueError(plan)
    out = []
    for mult, qty, label in ladder:
        if side == "LONG":
            out.append((entry + mult * risk, qty, label))
        else:
            out.append((entry - mult * risk, qty, label))
    return out


def resim_scale_plan(
    trades: pd.DataFrame,
    gby: Dict[date, pd.DataFrame],
    plan: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    """Re-manage parent entries/stops under an alternate scale-out ladder."""
    units: List[dict] = []
    out_trades: List[dict] = []
    realized = 0.0
    peak = 0.0
    max_dd = 0.0
    for _, tr in trades.sort_values("entry_ts").iterrows():
        session = date.fromisoformat(str(tr["session"])[:10])
        rth = rth_slice(gby.get(session))
        if rth.empty:
            continue
        entry_ts = _localize(pd.Timestamp(tr["entry_ts"]))
        side = str(tr["side"])
        entry = float(tr["entry"])
        stop = float(tr["stop"])
        risk_r = float(tr["risk_r"])
        targets = _targets_for_plan(plan, entry, stop, side)
        qty = sum(q for _, q, _ in targets) or ENTRY_QTY
        ot = OpenFade(
            trade_id=int(tr["trade_id"]),
            control="confirmed",
            side=side,
            session=session,
            entry_ts=entry_ts,
            entry=entry,
            stop=stop,
            risk_r=risk_r,
            targets=targets,
            units_remaining=qty,
            pmc=float(tr.get("pmc") or 0),
            sweep_ts=str(tr.get("sweep_ts") or ""),
            failure_ts=str(tr.get("failure_ts") or ""),
            confirm_ts=str(tr.get("confirm_ts") or ""),
        )
        manage_bars = rth.loc[entry_ts:]
        still, exits, d_real, stress = _manage_open(ot, manage_bars)
        if still is not None and still.units_remaining > 0 and not manage_bars.empty:
            last_ts = _localize(manage_bars.index[-1])
            px = float(manage_bars.iloc[-1]["close"])
            while still.units_remaining > 0:
                pts = (px - still.entry) if still.side == "LONG" else (still.entry - px)
                net = pts * POINT_VALUE - FEE_PER_UNIT
                exits.append(
                    {
                        "trade_id": still.trade_id,
                        "control": "confirmed",
                        "side": still.side,
                        "session": session.isoformat(),
                        "unit_qty": 1,
                        "entry_ts": still.entry_ts.isoformat(),
                        "exit_ts": last_ts.isoformat(),
                        "entry": still.entry,
                        "exit": px,
                        "reason": "session_end",
                        "target_r": "",
                        "points": pts,
                        "net_usd": net,
                    }
                )
                d_real += net
                still.units_remaining -= 1
        units.extend(exits)
        realized += d_real
        peak = max(peak, realized)
        max_dd = min(max_dd, realized - peak)
        exit_ts = exits[-1]["exit_ts"] if exits else entry_ts.isoformat()
        reasons = sorted({e["reason"] for e in exits})
        row = dict(tr)
        row.update(
            {
                "net_usd": float(sum(e["net_usd"] for e in exits)),
                "stress_usd": float(stress),
                "units": qty,
                "exit_ts": exit_ts,
                "exit_reasons": ",".join(reasons),
                "hit_1r": any(e["reason"] == "tp_1r" for e in exits),
                "hit_2r": any(e["reason"] == "tp_2r" for e in exits),
                "hit_4r": any(e["reason"] == "tp_4r" for e in exits),
                "stopped": any(e["reason"] == "stop" for e in exits),
                "mfe_pts": ot.mfe,
                "mae_pts": ot.mae,
                "scale_plan": plan,
            }
        )
        out_trades.append(row)
    tdf = pd.DataFrame(out_trades)
    udf = pd.DataFrame(units)
    m = metrics_from_subset(tdf, udf)
    return tdf, udf, m


# ---------------------------------------------------------------------------
# DSR / stance / IO
# ---------------------------------------------------------------------------


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "us30_pmc_failed_break_fade_structure_bias",
            "parent_trial_id": PARENT_DSR,
            "is_independent": "FALSE",
            "market": "US30",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "parent": "confirmed_pmc_fade",
                    "structure_tf": "4h",
                    "engine": "StructureProgramEngine",
                    "phase2": list(PHASE2_VARIANTS),
                    "scale_diag": list(SCALE_PLANS),
                    "parent_dsr": PARENT_DSR,
                }
            ),
            "fixed_parameters_ref": "live/us30_pmc_failed_break_fade_structure_bias.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Confirmed PMC fade × causal 4h structure-bias ALIGNED/OPPOSED overlay",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str = "COMPLETE") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def decide_stance(
    phase1: Dict[str, Dict[str, float]],
    phase2: Dict[str, Dict[str, float]],
    scale_by_variant: Dict[str, Dict[str, Dict[str, float]]],
    aligned_long: Dict[str, float],
    aligned_short: Dict[str, float],
) -> Tuple[str, str]:
    base = phase2.get("baseline") or {}
    al = phase2.get("aligned_only") or {}
    an = phase2.get("aligned_plus_neut") or {}
    g_al = phase1.get("ALIGNED") or {}
    g_op = phase1.get("OPPOSED") or {}

    base_ns = float(base.get("ns") or 0)
    al_ns = float(al.get("ns") or 0)
    an_ns = float(an.get("ns") or 0)
    al_n = int(al.get("trades") or 0)
    al_net = float(al.get("net_usd") or 0)
    al_stress = float(al.get("stress_dd_usd") or 0)
    base_stress = float(base.get("stress_dd_usd") or 0)
    al_runner = float(al.get("runner_net_share") or 0)
    base_runner = float(base.get("runner_net_share") or 0)

    # Opposed wins → discovery, do not invent story
    if float(g_op.get("ns") or 0) > float(g_al.get("ns") or 0) and float(g_op.get("net_usd") or 0) > float(
        g_al.get("net_usd") or 0
    ):
        return (
            "DISCOVERY_OPPOSED_WINS",
            "OPPOSED group outperforms ALIGNED — mark discovery; do not invent alignment story. Archive promote path.",
        )

    # Directional branch dominance
    al_long_net = float(aligned_long.get("net_usd") or 0)
    al_short_net = float(aligned_short.get("net_usd") or 0)
    if al_n >= 10 and abs(al_long_net) + abs(al_short_net) > 0:
        dominant = max(abs(al_long_net), abs(al_short_net))
        total = abs(al_long_net) + abs(al_short_net)
        if dominant / total >= 0.85 and al_net > 0:
            branch = "LONG" if abs(al_long_net) >= abs(al_short_net) else "SHORT"
            return (
                "DESCRIPTIVE_ONE_BRANCH",
                "ALIGNED benefit concentrated in %s branch — descriptive only until separately validated."
                % branch,
            )

    # Runner removal collapse
    scale_al = (scale_by_variant.get("aligned_only") or {}).get("no_runner_cap_2r") or {}
    if al_net > 0 and float(scale_al.get("net_usd") or 0) <= 0 and al_ns > base_ns:
        return (
            "NO_DEMO_RUNNER_DEPENDENT",
            "ALIGNED lift collapses when runner capped at 2R — no demo until tail dependency characterized.",
        )

    if al_ns <= base_ns or al_net < 0:
        return (
            "ARCHIVE_OVERLAY",
            "ALIGNED N/S ≤ baseline or ALIGNED net negative — archive structure-bias overlay; "
            "close fade workstream if no other path.",
        )

    if al_ns > base_ns and al_n <= 50:
        return (
            "SHADOW_ONLY",
            "ALIGNED improves N/S but N≲50 — shadow log only; no demo.",
        )

    # aligned+neutral works, aligned-only does not (relative to baseline)
    if an_ns > base_ns and al_ns <= base_ns:
        return (
            "OPPOSED_SKIP_THROTTLE",
            "aligned+neutral lifts vs baseline while aligned-only does not — consider OPPOSED-skip throttle.",
        )

    # stress_dd is negative; "lower stress" = smaller magnitude drawdown
    lower_stress = (
        abs(al_stress) < abs(base_stress)
        if al_stress < 0 and base_stress < 0
        else al_stress >= base_stress
    )
    runner_ok = al_runner <= base_runner + 0.05 or base_runner <= 0
    if al_ns > base_ns and al_net > 0 and lower_stress and runner_ok and al_n > 50:
        return (
            "PLUGIN_PORT_CANDIDATE",
            "ALIGNED improves N/S with lower stress and runner share not worse — StrategyPlugin port candidate "
            "(eligibility filter only, no size-up).",
        )

    if al_ns > base_ns and al_net > 0:
        return (
            "RESEARCH_ALIGNED_LIFT",
            "ALIGNED improves vs baseline but gates for plugin port not fully clear — research / shadow.",
        )

    return (
        "RESEARCH_INCONCLUSIVE",
        "No clear ALIGNED eligibility filter; keep descriptive tables; do not promote.",
    )


def write_summary(
    hub: Path,
    phase1_rows: List[dict],
    phase2_rows: List[dict],
    branch_rows: List[dict],
    scale_rows: List[dict],
    stance: str,
    rationale: str,
    n_snaps: int,
) -> str:
    lines = [
        "# US30 PMC confirmed fade × 4h structure-bias",
        "",
        "**Hub:** `live/state/us30_pmc_failed_break_fade_structure_bias/`",
        "**DSR:** `%s` (parent `%s`)" % (DSR, PARENT_DSR),
        "**Status:** Phase 1 descriptive + Phase 2 variants COMPLETE — %s." % stance,
        "",
        "## Frozen base (parent confirmed)",
        "",
        "| Param | Value |",
        "|---|---|",
        "| Level | PMC only |",
        "| Signal | 5m reclaim + 1 confirmation bar ≤60m |",
        "| Entry | next 1m open after confirmation |",
        "| Stop | sweep extreme ± 1 tick |",
        "| Scale-out | 50%@1R / 25%@2R / 25%@4R (2/1/1) |",
        "| Costs | fee $1.50/unit + 1-tick adverse entry/stop |",
        "| Structure | causal 4h StructureProgramEngine (unchanged) |",
        "",
        "Causal snaps: **%d** completed 4h bars. Bias attached at `confirm_ts` with "
        "`structure_feature_available_at ≤ confirm_ts < entry_ts`." % n_snaps,
        "",
        "## Phase 1 — descriptive alignment (no filter)",
        "",
        "| Group | N | Net | N/S | PF | WR | Median R | MAE | MFE | 1R | 2R | 4R | runner_share |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in phase1_rows:
        lines.append(
            "| %s | %d | %.0f | %.2f | %.2f | %.1f%% | %.2f | %.1f | %.1f | %.0f%% | %.0f%% | %.0f%% | %.0f%% |"
            % (
                r["group"],
                int(r["N"]),
                float(r["net_usd"]),
                float(r["ns"]),
                float(r["pf"]),
                100.0 * float(r["wr"]),
                float(r["median_r"]),
                float(r["median_mae"]),
                float(r["median_mfe"]),
                100.0 * float(r["hit_1r"]),
                100.0 * float(r["hit_2r"]),
                100.0 * float(r["hit_4r"]),
                100.0 * float(r["runner_share"]),
            )
        )
    lines.extend(["", "### ALIGNED branches", ""])
    lines.append("| Branch | N | Net | N/S | WR | runner_share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in branch_rows:
        lines.append(
            "| %s | %d | %.0f | %.2f | %.1f%% | %.0f%% |"
            % (
                r["group"],
                int(r["N"]),
                float(r["net_usd"]),
                float(r["ns"]),
                100.0 * float(r["wr"]),
                100.0 * float(r["runner_share"]),
            )
        )
    lines.extend(
        [
            "",
            "## Phase 2 — strategy variants (same fills)",
            "",
            "| Variant | N | Net | Stress | N/S | WR | PF | Runner share |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in phase2_rows:
        lines.append(
            "| %s | %d | %.0f | %.0f | %.2f | %.1f%% | %.2f | %.0f%% |"
            % (
                r["variant"],
                int(r["N"]),
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                float(r["ns"]),
                100.0 * float(r["wr"]),
                float(r["pf"]),
                100.0 * float(r["runner_share"]),
            )
        )
    lines.extend(
        [
            "",
            "## Scale-out diagnostics (report only)",
            "",
            "| Scope | Plan | N | Net | N/S | WR | hit_1r | hit_2r | hit_4r | runner_share |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in scale_rows:
        lines.append(
            "| %s | %s | %d | %.0f | %.2f | %.1f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% |"
            % (
                r["scope"],
                r["plan"],
                int(r["N"]),
                float(r["net_usd"]),
                float(r["ns"]),
                100.0 * float(r["wr"]),
                100.0 * float(r["hit_1r"]),
                100.0 * float(r["hit_2r"]),
                100.0 * float(r["hit_4r"]),
                100.0 * float(r["runner_share"]),
            )
        )
    lines.extend(
        [
            "",
            "_`no_runner_cap_2r` and `reduced_runner_50_50` both use 2@1R + 2@2R "
            "(fold/eliminate 4R); reported separately per plan._",
            "",
            "## Stance",
            "",
            "**%s** — %s" % (stance, rationale),
            "",
            "## Decision gates (reference)",
            "",
            "| Result | Action |",
            "|---|---|",
            "| ALIGNED N/S ≤ baseline or negative | Archive overlay |",
            "| ALIGNED improves but N ≲ 50 | Shadow only; no demo |",
            "| ALIGNED improves, lower stress, stable, runner not worse | Plugin port candidate |",
            "| aligned+neutral works, aligned-only does not | OPPOSED-skip throttle |",
            "| One directional branch drives benefit | Descriptive only |",
            "| Runner removal collapses result | No demo until characterized |",
            "",
            "No size-up / no scale-in / no extra filters in this trial.",
        ]
    )
    text = "\n".join(lines) + "\n"
    (hub / "SUMMARY.md").write_text(text)
    return text


def write_email(
    hub: Path,
    phase2_rows: List[dict],
    stance: str,
    rationale: str,
) -> str:
    lines = [
        "US30 PMC fade × 4h structure-bias overlay complete.",
        "Hub: %s" % hub,
        "DSR: %s (parent %s)" % (DSR, PARENT_DSR),
        "",
        "Phase 2 variants:",
    ]
    for r in phase2_rows:
        lines.append(
            "  %s  N=%d net=$%.0f stress=$%.0f N/S=%.2f WR=%.1f%% runner=%.0f%%"
            % (
                r["variant"],
                int(r["N"]),
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                float(r["ns"]),
                100.0 * float(r["wr"]),
                100.0 * float(r["runner_share"]),
            )
        )
    lines.extend(["", "Stance: %s" % stance, rationale, ""])
    body = "\n".join(lines)
    (hub / "EMAIL.txt").write_text(body)
    return body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="US30 PMC fade × 4h structure-bias overlay")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--hub", type=Path, default=HUB)
    ap.add_argument("--parent-confirmed", type=Path, default=PARENT_CONFIRMED)
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub: Path = args.hub
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "phase1").mkdir(exist_ok=True)
    (hub / "phase2").mkdir(exist_ok=True)
    (hub / "scaleout").mkdir(exist_ok=True)
    (hub / "causality").mkdir(exist_ok=True)
    run_log = hub / "run.log"

    def log(msg: str) -> None:
        line = "[%s] %s" % (datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), msg)
        print(line, flush=True)
        with run_log.open("a") as fh:
            fh.write(line + "\n")

    try:
        hub_rel = str(hub.relative_to(REPO))
    except ValueError:
        hub_rel = str(hub)

    # DSR before peek
    _append_dsr()
    rid = begin_run(
        run_class="pandas",
        variant_slug="us30_pmc_failed_break_fade_structure_bias",
        instrument=SYM,
        hub_path=hub_rel,
        dsr_trial_id=DSR,
        meta={"parent_dsr": PARENT_DSR, "smoke": bool(args.smoke)},
        notes="structure-bias overlay on confirmed PMC fade",
    )

    try:
        parent = Path(args.parent_confirmed)
        trades_path = parent / "trades.csv"
        units_path = parent / "units.csv"
        if not trades_path.exists():
            raise FileNotFoundError("parent confirmed trades missing: %s" % trades_path)

        log("loading parent confirmed tape …")
        trades = pd.read_csv(trades_path)
        units = pd.read_csv(units_path) if units_path.exists() else pd.DataFrame()
        if args.smoke:
            trades = trades.head(25).copy()
            if not units.empty:
                ids = set(trades["trade_id"].astype(int))
                units = units[units["trade_id"].astype(int).isin(ids)].copy()
        log("parent confirmed N=%d" % len(trades))

        log("loading US30 1m for 4h structure walk …")
        gby = load_fx_1m_by_ny_date(ONE_M, SYM)
        log("sessions=%d" % len(gby))

        snaps = build_causal_4h_snapshots(gby, smoke=args.smoke)
        snaps.to_csv(hub / "causality" / "structure_4h_snapshots.csv", index=False)

        # Attach bias + causality chain per trade
        aligned_rows: List[dict] = []
        for _, tr in trades.iterrows():
            conf_raw = tr.get("confirm_ts")
            if conf_raw is None or str(conf_raw) in ("", "nan", "None"):
                bias, snap = "UNAVAILABLE", None
                conf_ts = None
            else:
                conf_ts = _localize(pd.Timestamp(conf_raw))
                bias, snap = lookup_bias_at(snaps, conf_ts)
            side = str(tr["side"])
            align = _alignment(bias, side)
            entry_ts = _localize(pd.Timestamp(tr["entry_ts"]))
            row = dict(tr)
            row["structure_bias"] = bias
            row["alignment"] = align
            row["fade_confirmation_close_ts"] = conf_ts.isoformat() if conf_ts is not None else ""
            row["entry_submit_ts"] = entry_ts.isoformat()
            row["entry_fill_ts"] = entry_ts.isoformat()
            if snap is not None:
                row["structure_bar_ts"] = snap.get("structure_bar_ts", "")
                row["structure_bar_end_ts"] = snap.get("structure_bar_end_ts", "")
                row["structure_feature_available_at"] = snap.get("structure_feature_available_at", "")
                row["structure_program"] = snap.get("program", "")
                row["structure_ready"] = snap.get("ready", False)
                row["structure_active_key"] = snap.get("active_key", "")
                # causality check
                avail = _localize(pd.Timestamp(snap["structure_feature_available_at"]))
                row["causality_ok"] = bool(
                    avail <= conf_ts < entry_ts if conf_ts is not None else False
                )
            else:
                row["structure_bar_ts"] = ""
                row["structure_bar_end_ts"] = ""
                row["structure_feature_available_at"] = ""
                row["structure_program"] = ""
                row["structure_ready"] = False
                row["structure_active_key"] = ""
                row["causality_ok"] = conf_ts is None  # unavailable before any bar
            aligned_rows.append(row)

        adf = pd.DataFrame(aligned_rows)
        adf.to_csv(hub / "phase1" / "trades_aligned.csv", index=False)
        causality_ok_frac = float(adf["causality_ok"].mean()) if len(adf) else 0.0
        log("alignment attached; causality_ok=%.1f%%" % (100.0 * causality_ok_frac))

        # Phase 1 groups
        phase1_metrics: Dict[str, Dict[str, float]] = {}
        phase1_rows: List[dict] = []
        for g in ALIGN_GROUPS:
            sub = adf[adf["alignment"] == g]
            u_sub = (
                units[units["trade_id"].astype(int).isin(set(sub["trade_id"].astype(int)))]
                if not units.empty and not sub.empty
                else pd.DataFrame()
            )
            m = metrics_from_subset(sub, u_sub)
            phase1_metrics[g] = m
            phase1_rows.append(group_table_row(g, m))
            log("Phase1 %s N=%d net=%.0f ns=%.2f" % (g, m["trades"], m["net_usd"], m["ns"]))

        pd.DataFrame(phase1_rows).to_csv(hub / "phase1" / "by_alignment.csv", index=False)

        # ALIGNED long/short branches
        branch_rows: List[dict] = []
        branch_metrics: Dict[str, Dict[str, float]] = {}
        for label, mask in (
            ("ALIGNED_LONG", (adf["alignment"] == "ALIGNED") & (adf["side"] == "LONG")),
            ("ALIGNED_SHORT", (adf["alignment"] == "ALIGNED") & (adf["side"] == "SHORT")),
        ):
            sub = adf[mask]
            u_sub = (
                units[units["trade_id"].astype(int).isin(set(sub["trade_id"].astype(int)))]
                if not units.empty and not sub.empty
                else pd.DataFrame()
            )
            m = metrics_from_subset(sub, u_sub)
            branch_metrics[label] = m
            branch_rows.append(group_table_row(label, m))
        pd.DataFrame(branch_rows).to_csv(hub / "phase1" / "aligned_branches.csv", index=False)

        # Phase 2 variants (same fills)
        variant_masks = {
            "baseline": adf["alignment"].notna(),  # all
            "aligned_only": adf["alignment"] == "ALIGNED",
            "aligned_plus_neut": adf["alignment"].isin(["ALIGNED", "NEUTRAL"]),
        }
        phase2_metrics: Dict[str, Dict[str, float]] = {}
        phase2_rows: List[dict] = []
        for vname, mask in variant_masks.items():
            sub = adf[mask]
            u_sub = (
                units[units["trade_id"].astype(int).isin(set(sub["trade_id"].astype(int)))]
                if not units.empty and not sub.empty
                else pd.DataFrame()
            )
            m = metrics_from_subset(sub, u_sub)
            phase2_metrics[vname] = m
            row = group_table_row(vname, m)
            row["variant"] = vname
            phase2_rows.append(row)
            out = hub / "phase2" / vname
            out.mkdir(parents=True, exist_ok=True)
            sub.to_csv(out / "trades.csv", index=False)
            u_sub.to_csv(out / "units.csv", index=False)
            (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
            _yearly(sub).to_csv(out / "yearly.csv", index=False)
            log("Phase2 %s N=%d net=%.0f ns=%.2f" % (vname, m["trades"], m["net_usd"], m["ns"]))
        pd.DataFrame(phase2_rows).to_csv(hub / "phase2" / "variants.csv", index=False)

        # Scale-out diagnostics
        log("scale-out diagnostics …")
        scale_rows: List[dict] = []
        scale_by_variant: Dict[str, Dict[str, Dict[str, float]]] = {}
        scopes = {
            "ALL": adf,
            "ALIGNED": adf[adf["alignment"] == "ALIGNED"],
            "OPPOSED": adf[adf["alignment"] == "OPPOSED"],
            "NEUTRAL": adf[adf["alignment"] == "NEUTRAL"],
            "UNAVAILABLE": adf[adf["alignment"] == "UNAVAILABLE"],
            "baseline": adf,
            "aligned_only": adf[adf["alignment"] == "ALIGNED"],
            "aligned_plus_neut": adf[adf["alignment"].isin(["ALIGNED", "NEUTRAL"])],
        }
        for scope_name, scope_df in scopes.items():
            scale_by_variant[scope_name] = {}
            if scope_df.empty:
                for plan in SCALE_PLANS:
                    m = metrics_from_subset(pd.DataFrame(), pd.DataFrame())
                    scale_by_variant[scope_name][plan] = m
                    scale_rows.append(
                        {
                            "scope": scope_name,
                            "plan": plan,
                            **{k: group_table_row(plan, m)[k] for k in (
                                "N", "net_usd", "ns", "wr", "hit_1r", "hit_2r", "hit_4r", "runner_share"
                            )},
                        }
                    )
                continue
            for plan in SCALE_PLANS:
                if plan == "full_1r_2r_4r":
                    # reuse parent fills for this subset
                    u_sub = (
                        units[units["trade_id"].astype(int).isin(set(scope_df["trade_id"].astype(int)))]
                        if not units.empty
                        else pd.DataFrame()
                    )
                    m = metrics_from_subset(scope_df, u_sub)
                    tdf_p, udf_p = scope_df, u_sub
                else:
                    tdf_p, udf_p, m = resim_scale_plan(scope_df, gby, plan)
                scale_by_variant[scope_name][plan] = m
                out = hub / "scaleout" / ("%s__%s" % (scope_name, plan))
                out.mkdir(parents=True, exist_ok=True)
                tdf_p.to_csv(out / "trades.csv", index=False)
                udf_p.to_csv(out / "units.csv", index=False)
                (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
                scale_rows.append(
                    {
                        "scope": scope_name,
                        "plan": plan,
                        "N": int(m.get("trades") or 0),
                        "net_usd": float(m.get("net_usd") or 0),
                        "ns": float(m.get("ns") or 0),
                        "wr": float(m.get("win_rate") or 0),
                        "hit_1r": float(m.get("hit_1r_rate") or 0),
                        "hit_2r": float(m.get("hit_2r_rate") or 0),
                        "hit_4r": float(m.get("hit_4r_rate") or 0),
                        "runner_share": float(m.get("runner_net_share") or 0),
                    }
                )
                log(
                    "scale %s/%s N=%d net=%.0f ns=%.2f"
                    % (scope_name, plan, m["trades"], m["net_usd"], m["ns"])
                )
        pd.DataFrame(scale_rows).to_csv(hub / "scaleout" / "diagnostics.csv", index=False)

        stance, rationale = decide_stance(
            phase1_metrics,
            phase2_metrics,
            scale_by_variant,
            branch_metrics.get("ALIGNED_LONG") or {},
            branch_metrics.get("ALIGNED_SHORT") or {},
        )
        write_summary(
            hub,
            phase1_rows,
            phase2_rows,
            branch_rows,
            scale_rows,
            stance,
            rationale,
            n_snaps=len(snaps),
        )
        body = write_email(hub, phase2_rows, stance, rationale)

        # Board
        pd.DataFrame(phase2_rows).to_csv(hub / "summary.csv", index=False)

        # Update RESEARCH_PLAN status
        plan = hub / "RESEARCH_PLAN.md"
        if plan.exists():
            import re

            txt = plan.read_text()
            txt2, n = re.subn(
                r"\*\*Status:\*\*[^\n]*",
                "**Status:** Phase 1/2 COMPLETE — %s." % stance,
                txt,
                count=1,
            )
            if n:
                plan.write_text(txt2)

        base = phase2_metrics.get("baseline") or {}
        complete_run(
            rid,
            net_usd=float((phase2_metrics.get("aligned_only") or {}).get("net_usd") or 0),
            stress_dd_usd=float((phase2_metrics.get("aligned_only") or {}).get("stress_dd_usd") or 0),
            close_mtm_dd_usd=float((phase2_metrics.get("aligned_only") or {}).get("close_mtm_dd_usd") or 0),
            ns=float((phase2_metrics.get("aligned_only") or {}).get("ns") or 0),
            trades=int((phase2_metrics.get("aligned_only") or {}).get("trades") or 0),
            notes="stance=%s baseline_ns=%.2f" % (stance, float(base.get("ns") or 0)),
            meta={
                "stance": stance,
                "phase1": phase1_metrics,
                "phase2": phase2_metrics,
                "causality_ok_frac": causality_ok_frac,
            },
        )
        _mark_dsr("COMPLETE")

        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                    "stance": stance,
                    "rationale": rationale,
                    "phase1": phase1_metrics,
                    "phase2": phase2_metrics,
                    "dsr": DSR,
                    "parent_dsr": PARENT_DSR,
                    "causality_ok_frac": causality_ok_frac,
                },
                indent=2,
                default=str,
            )
        )

        if args.email:
            send_email(
                subject="potions: US30 PMC fade × structure-bias complete — %s" % stance,
                body=body,
            )
            log("email sent")
        log("done stance=%s" % stance)
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _mark_dsr("FAILED")
        tb = traceback.format_exc()
        log("FAILED: %s" % exc)
        (hub / "EMAIL.txt").write_text("FAILED\n%s\n%s" % (exc, tb))
        if args.email:
            send_email(
                subject="potions: US30 PMC fade × structure-bias FAILED",
                body="Hub: %s\n%s\n%s" % (hub, exc, tb[-2000:]),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
