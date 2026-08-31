"""NQ V2B × WICK_REJECT seeded-range causal state label (descriptive + optional skip CF).

Does NOT change V2B execution in the descriptive pass.
Does NOT require retest limit fills — uses resolved 1h break direction as state.
Does NOT size up aligned trades.

States at V2B order_active_ts (entry order live_after):
  ALIGNED_BREAK   — active seed with break_available_at < V2B arm; direction agrees
  OPPOSED_BREAK   — active seed broken; direction disagrees
  UNRESOLVED_SEED — active seed available but not yet broken
  NO_ACTIVE_SEED  — no seed in [available_at, expires_at) window

Primary book: NQ prior-opposed V2B resting-limit hour-complete.
Secondary: MNQ equivalent (execution-scale confirmation only).

Hub: live/state/nq_v2b_wick_range_alignment/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_v2b_wick_range_alignment --email
  python -m live.nq_v2b_wick_range_alignment --skip-opposed-cf --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import nq_wick_reject_range_seed_retest as nq_rt
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_v2b_wick_range_alignment"
SEED_HUB = REPO / "live" / "state" / "nq_wick_reject_range_seed_retest"
NY = "America/New_York"

PRIMARY = {
    "market": "nq",
    "instrument": "NQ",
    "point_value": 20.0,
    "fee": 1.50,
    "state_root": REPO
    / "live"
    / "state"
    / "nq_v2b_prior_opposed_stpmc_resting_limit"
    / "states"
    / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3",
    "strategy_id": "nq_v2b_prior_opposed_stpmc_only_S_1_1_3",
}

SECONDARY = {
    "market": "mnq",
    "instrument": "MNQ",
    "point_value": 2.0,
    "fee": 1.50,
    "state_root": REPO
    / "live"
    / "state"
    / "mnq_v2b_prior_opposed_stpmc_resting_limit"
    / "states"
    / "mnq_v2b_prior_opposed_stpmc_only_S_1_1_3",
    "strategy_id": "mnq_v2b_prior_opposed_stpmc_only_S_1_1_3",
}

STATES = ("ALIGNED_BREAK", "OPPOSED_BREAK", "UNRESOLVED_SEED", "NO_ACTIVE_SEED")


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _localize(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


@dataclass
class StructureState:
    seed_id: str
    available_at: pd.Timestamp
    expires_at: pd.Timestamp
    break_available_at: Optional[pd.Timestamp]  # 1h break confirm (None if unresolved)
    break_side: str  # LONG / SHORT / ""
    high: float
    low: float
    width: float
    slice: str


def build_structure_states(*, smoke: bool = False) -> List[StructureState]:
    """Rebuild path states from frozen NQ atlas events + 1m tape."""
    events = nq_rt.load_wick_events(smoke=smoke)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    if smoke:
        edates = sorted({_localize(pd.Timestamp(t)).date() for t in events["confirm_bar_close_ts"]})
        days = sorted(gby.keys())
        keep = set()
        for d in edates:
            if d in days:
                i = days.index(d)
                keep.update(days[max(0, i - 8) : i + 12])
        gby = {d: gby[d] for d in days if d in keep}
    tape, h1, h4, early = nq_rt.build_rth_tape(gby)
    seeds, _census = nq_rt.make_seeds(events, tape, h4, early)
    out: List[StructureState] = []
    for seed in seeds:
        s = nq_rt.Seed(**{**seed.__dict__})
        nq_rt.simulate_seed_path(s, h1, tape)
        side = ""
        if s.first_break_side == "high":
            side = "LONG"
        elif s.first_break_side == "low":
            side = "SHORT"
        out.append(
            StructureState(
                seed_id=s.seed_id,
                available_at=s.available_at,
                expires_at=s.expires_at,
                break_available_at=s.break_confirm_ts,
                break_side=side,
                high=s.high,
                low=s.low,
                width=s.width,
                slice=s.slice,
            )
        )
    return out


def load_v2b_campaigns(cfg: dict) -> pd.DataFrame:
    root = Path(cfg["state_root"])
    fills = pd.read_csv(root / "fills.csv")
    orders = pd.read_csv(root / "orders.csv")
    units = pd.read_csv(root / "unit_trades.csv")

    sid = cfg["strategy_id"]
    fills = fills[fills["strategy_id"].astype(str) == sid].copy()
    orders = orders[orders["strategy_id"].astype(str) == sid].copy()
    entry_fills = fills[fills["reason"].astype(str) == "entry"].copy()
    entry_orders = orders[orders["bracket_role"].astype(str) == "entry"].copy()

    entry_fills["ts"] = pd.to_datetime(entry_fills["ts"], utc=True).dt.tz_convert(NY)
    entry_orders["live_after_ts"] = pd.to_datetime(entry_orders["live_after_ts"], utc=True).dt.tz_convert(NY)

    joined = entry_fills.merge(
        entry_orders[["broker_order_id", "live_after_ts", "limit_price", "created_at"]],
        on="broker_order_id",
        how="left",
        suffixes=("", "_ord"),
    )

    # Campaign aggregates from unit_trades
    units = units[units["candidate"].astype(str) == sid].copy() if "candidate" in units.columns else units
    units["entry_ts"] = pd.to_datetime(units["entry_ts"], utc=True).dt.tz_convert(NY)
    units["exit_ts"] = pd.to_datetime(units["exit_ts"], utc=True).dt.tz_convert(NY)
    units["net_usd"] = pd.to_numeric(units["net_usd"], errors="coerce")

    camp_rows = []
    for trade_id, g in units.groupby("trade_id"):
        g = g.sort_values("entry_ts")
        entry_ts = g["entry_ts"].iloc[0]
        exit_ts = g["exit_ts"].max()
        direction = str(g["direction"].iloc[0]).upper()
        side = "LONG" if direction.startswith("L") else "SHORT"
        net = float(g["net_usd"].sum())
        reasons = g["exit_reason"].astype(str)
        hit_tp1 = int(reasons.str.contains("tp1", case=False).any())
        hit_tp2 = int(reasons.str.contains("tp2", case=False).any())
        # runner: tp3 / runner_stop / leftover after tp2
        hit_runner = int(
            reasons.str.contains("runner|tp3", case=False).any()
            or (hit_tp2 and reasons.str.contains("eod|runner", case=False).any())
        )
        stopped = int(reasons.str.contains("stop|wide_stop", case=False).any() and not hit_tp1)
        stop_any = int(reasons.str.contains("stop", case=False).any())
        camp_rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "net_usd": net,
                "n_units": int(len(g)),
                "hit_tp1": hit_tp1,
                "hit_tp2": hit_tp2,
                "hit_runner": hit_runner,
                "stopped": stop_any,
                "stop_before_tp1": stopped,
                "exit_reasons": ";".join(sorted(set(reasons.tolist()))),
            }
        )
    camps = pd.DataFrame(camp_rows)

    # Attach order_active_ts from entry order live_after
    live_map = {}
    for _, row in joined.iterrows():
        live_map[str(row["trade_id"])] = row["live_after_ts"]
    camps["order_active_ts"] = camps["trade_id"].map(live_map)
    # Fallback: entry_ts if missing
    miss = camps["order_active_ts"].isna()
    camps.loc[miss, "order_active_ts"] = camps.loc[miss, "entry_ts"]

    # R from entry→first exit path using fills mid prices: risk ≈ |entry−wide stop| unknown;
    # use unit net / (|entry−exit| proxy). Prefer PF/WR; R from equal-risk assumption:
    # reconstruct risk from first stop/tp geometry if available — else R = net / median_|loss|
    losses = camps.loc[camps["net_usd"] < 0, "net_usd"].abs()
    risk_proxy = float(losses.median()) if len(losses) else 1.0
    camps["r_multiple"] = camps["net_usd"] / risk_proxy if risk_proxy > 0 else 0.0
    camps["risk_proxy_usd"] = risk_proxy

    # Calendar blocks
    camps["year"] = camps["entry_ts"].dt.year
    camps["month"] = camps["entry_ts"].dt.month
    camps["dow"] = camps["entry_ts"].dt.day_name()
    return camps


def classify_campaign(order_active: pd.Timestamp, side: str, states: Sequence[StructureState]) -> dict:
    """Most recent active seed relative to V2B arm time (causal)."""
    t = _localize(order_active)
    active = [s for s in states if s.available_at < t <= s.expires_at]
    if not active:
        return {
            "structure_state": "NO_ACTIVE_SEED",
            "seed_id": "",
            "break_side": "",
            "break_available_at": "",
            "structure_usable": 0,
        }
    # Most recent by available_at
    active = sorted(active, key=lambda s: s.available_at)
    seed = active[-1]
    if seed.break_available_at is None or not (seed.break_available_at < t):
        return {
            "structure_state": "UNRESOLVED_SEED",
            "seed_id": seed.seed_id,
            "break_side": "",
            "break_available_at": "",
            "structure_usable": 0,
        }
    # Usable resolved break
    aligned = seed.break_side == side
    return {
        "structure_state": "ALIGNED_BREAK" if aligned else "OPPOSED_BREAK",
        "seed_id": seed.seed_id,
        "break_side": seed.break_side,
        "break_available_at": seed.break_available_at.isoformat(),
        "structure_usable": 1,
    }


def annotate_campaigns(camps: pd.DataFrame, states: Sequence[StructureState]) -> pd.DataFrame:
    rows = []
    for _, c in camps.iterrows():
        lab = classify_campaign(c["order_active_ts"], c["side"], states)
        rows.append(lab)
    return pd.concat([camps.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def _equity_stress(nets: pd.Series) -> Tuple[float, float]:
    if nets is None or len(nets) == 0:
        return 0.0, 0.0
    eq = nets.astype(float).cumsum()
    dd = eq - eq.cummax()
    stress = float(dd.min())
    net = float(eq.iloc[-1])
    ns = net / abs(stress) if stress < 0 else (float("inf") if net > 0 else 0.0)
    return stress, ns


def summarize_by_state(camps: pd.DataFrame, label: str) -> List[dict]:
    out = []
    for state in list(STATES) + ["ALL"]:
        sub = camps if state == "ALL" else camps[camps["structure_state"] == state]
        n = len(sub)
        if n == 0:
            out.append(
                {
                    "book": label,
                    "state": state,
                    "n": 0,
                    "net_usd": 0.0,
                    "stress_dd_usd": 0.0,
                    "ns": 0.0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "avg_R": 0.0,
                    "median_R": 0.0,
                    "hit_tp1": 0.0,
                    "hit_tp2": 0.0,
                    "hit_runner": 0.0,
                    "stop_rate": 0.0,
                    "long_n": 0,
                    "short_n": 0,
                    "avg_net": 0.0,
                }
            )
            continue
        nets = sub["net_usd"].astype(float)
        wins = float(nets[nets > 0].sum())
        losses = float(-nets[nets < 0].sum())
        pf = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
        stress, ns = _equity_stress(nets)
        out.append(
            {
                "book": label,
                "state": state,
                "n": n,
                "net_usd": float(nets.sum()),
                "stress_dd_usd": stress,
                "ns": ns,
                "win_rate": float((nets > 0).mean()),
                "profit_factor": pf,
                "avg_R": float(sub["r_multiple"].mean()),
                "median_R": float(sub["r_multiple"].median()),
                "hit_tp1": float(sub["hit_tp1"].mean()),
                "hit_tp2": float(sub["hit_tp2"].mean()),
                "hit_runner": float(sub["hit_runner"].mean()),
                "stop_rate": float(sub["stopped"].mean()),
                "long_n": int((sub["side"] == "LONG").sum()),
                "short_n": int((sub["side"] == "SHORT").sum()),
                "avg_net": float(nets.mean()),
            }
        )
    return out


def calendar_blocks(camps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for state in STATES:
        sub = camps[camps["structure_state"] == state]
        if sub.empty:
            continue
        for (y, m), g in sub.groupby(["year", "month"]):
            rows.append(
                {
                    "state": state,
                    "year": int(y),
                    "month": int(m),
                    "n": int(len(g)),
                    "net_usd": float(g["net_usd"].sum()),
                    "win_rate": float((g["net_usd"] > 0).mean()),
                }
            )
    return pd.DataFrame(rows)


def matched_exposure_skip_opposed(camps: pd.DataFrame) -> dict:
    """Baseline vs skip OPPOSED_BREAK only — report trade count + exposure-aware metrics."""
    baseline = camps
    filtered = camps[camps["structure_state"] != "OPPOSED_BREAK"]
    b_net = float(baseline["net_usd"].sum())
    f_net = float(filtered["net_usd"].sum())
    b_stress, b_ns = _equity_stress(baseline["net_usd"])
    f_stress, f_ns = _equity_stress(filtered.sort_values("entry_ts")["net_usd"])
    skipped = camps[camps["structure_state"] == "OPPOSED_BREAK"]
    return {
        "baseline_n": int(len(baseline)),
        "filtered_n": int(len(filtered)),
        "skipped_n": int(len(skipped)),
        "skipped_net_usd": float(skipped["net_usd"].sum()) if len(skipped) else 0.0,
        "baseline_net": b_net,
        "filtered_net": f_net,
        "delta_net": f_net - b_net,
        "baseline_stress": b_stress,
        "filtered_stress": f_stress,
        "baseline_ns": b_ns,
        "filtered_ns": f_ns,
        "baseline_avg_net": b_net / len(baseline) if len(baseline) else 0.0,
        "filtered_avg_net": f_net / len(filtered) if len(filtered) else 0.0,
        "baseline_pf": _pf(baseline["net_usd"]),
        "filtered_pf": _pf(filtered["net_usd"]),
    }


def _pf(nets: pd.Series) -> float:
    nets = nets.astype(float)
    wins = float(nets[nets > 0].sum())
    losses = float(-nets[nets < 0].sum())
    return wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)


def opposed_is_harmful(summaries: List[dict]) -> bool:
    """True if OPPOSED_BREAK is materially worse than NO_ACTIVE_SEED and ALIGNED on avg net / WR."""
    opposed = next((s for s in summaries if s["state"] == "OPPOSED_BREAK"), None)
    aligned = next((s for s in summaries if s["state"] == "ALIGNED_BREAK"), None)
    none = next((s for s in summaries if s["state"] == "NO_ACTIVE_SEED"), None)
    if not opposed or opposed["n"] < 15:
        return False
    refs = [s for s in (aligned, none) if s and s["n"] >= 15]
    if not refs:
        return False
    ref_avg = float(np.mean([s["avg_net"] for s in refs]))
    ref_wr = float(np.mean([s["win_rate"] for s in refs]))
    # Material: avg net worse by ≥25% of |ref| or WR ≥5pp worse and avg net worse
    worse_net = opposed["avg_net"] < ref_avg - 0.25 * abs(ref_avg if ref_avg != 0 else 1.0)
    worse_wr = opposed["win_rate"] <= ref_wr - 0.05 and opposed["avg_net"] < ref_avg
    return bool(worse_net or worse_wr)


def write_docs(
    hub: Path,
    *,
    primary_camps: pd.DataFrame,
    secondary_camps: Optional[pd.DataFrame],
    summaries: List[dict],
    cal: pd.DataFrame,
    cf: Optional[dict],
    n_states: int,
    smoke: bool,
) -> str:
    # Core comparison
    core = [s for s in summaries if s["book"] == "NQ_primary" and s["state"] in ("ALIGNED_BREAK", "OPPOSED_BREAK", "NO_ACTIVE_SEED")]
    harmful = opposed_is_harmful([s for s in summaries if s["book"] == "NQ_primary"])
    if harmful and cf:
        stance = (
            "OPPOSED_BREAK harmful on descriptive read — matched-exposure skip-opposed CF reported. "
            "Still research; no StrategyPlugin until CF + causality review."
        )
    elif harmful:
        stance = "OPPOSED_BREAK looks harmful — run skip-opposed CF next (--skip-opposed-cf)."
    else:
        stance = (
            "DESCRIPTIVE ONLY — opposed-break not clearly harmful (or thin n). "
            "No size-up; no hybrid P&L; no plugin yet."
        )

    lines = [
        "# NQ V2B × WICK_REJECT range-seed alignment (causal state label)",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Hub:** `live/state/nq_v2b_wick_range_alignment/`",
        "**V2B book:** prior-opposed resting-limit hour-complete (`S_1_1_3`).",
        "**Structure:** frozen NQ WICK_REJECT range seeds (break direction label; retest fill NOT required).",
        "**Mode:** %s" % ("SMOKE" if smoke else "FULL"),
        "",
        "## Stance",
        "",
        stance,
        "",
        "## Causal rule",
        "",
        "```",
        "if structure.break_available_at < V2B.order_active_ts: usable",
        "else: unavailable",
        "```",
        "",
        "Active seed window: `available_at < order_active_ts <= expires_at`.",
        "Most recent active seed wins. No post-entry retest fill filter.",
        "",
        "## Structure seed count",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Frozen seeds with path state | %d |" % n_states,
        "| V2B primary campaigns | %d |" % len(primary_camps),
        "",
        "## Core comparison (NQ primary)",
        "",
        "| State | n | net $ | stress $ | N/S | WR | PF | avg R | med R | TP1/2/R% | stop% | L/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        if s["book"] != "NQ_primary":
            continue
        if s["state"] not in ("ALIGNED_BREAK", "OPPOSED_BREAK", "NO_ACTIVE_SEED", "UNRESOLVED_SEED", "ALL"):
            continue
        lines.append(
            "| %s | %d | %+.0f | %+.0f | %.2f | %.0f%% | %.2f | %+.3f | %+.3f | %.0f/%.0f/%.0f | %.0f%% | %d/%d |"
            % (
                s["state"],
                s["n"],
                s["net_usd"],
                s["stress_dd_usd"],
                s["ns"] if s["ns"] != float("inf") else 99.0,
                100 * s["win_rate"],
                s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                s["avg_R"],
                s["median_R"],
                100 * s["hit_tp1"],
                100 * s["hit_tp2"],
                100 * s["hit_runner"],
                100 * s["stop_rate"],
                s["long_n"],
                s["short_n"],
            )
        )

    if secondary_camps is not None and len(secondary_camps):
        lines.extend(
            [
                "",
                "## Secondary MNQ (execution-scale confirmation)",
                "",
                "| State | n | net $ | WR | PF | avg net |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for s in summaries:
            if s["book"] != "MNQ_secondary":
                continue
            if s["state"] not in ("ALIGNED_BREAK", "OPPOSED_BREAK", "NO_ACTIVE_SEED", "ALL"):
                continue
            lines.append(
                "| %s | %d | %+.0f | %.0f%% | %.2f | %+.0f |"
                % (
                    s["state"],
                    s["n"],
                    s["net_usd"],
                    100 * s["win_rate"],
                    s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                    s["avg_net"],
                )
            )

    if cf:
        lines.extend(
            [
                "",
                "## Matched-exposure CF: skip OPPOSED_BREAK only",
                "",
                "| Book | n | net $ | stress $ | N/S | PF | avg $/trade |",
                "|---|---:|---:|---:|---:|---:|---:|",
                "| baseline V2B | %d | %+.0f | %+.0f | %.2f | %.2f | %+.0f |"
                % (
                    cf["baseline_n"],
                    cf["baseline_net"],
                    cf["baseline_stress"],
                    cf["baseline_ns"] if cf["baseline_ns"] != float("inf") else 99.0,
                    cf["baseline_pf"] if cf["baseline_pf"] != float("inf") else 99.0,
                    cf["baseline_avg_net"],
                ),
                "| skip OPPOSED_BREAK | %d | %+.0f | %+.0f | %.2f | %.2f | %+.0f |"
                % (
                    cf["filtered_n"],
                    cf["filtered_net"],
                    cf["filtered_stress"],
                    cf["filtered_ns"] if cf["filtered_ns"] != float("inf") else 99.0,
                    cf["filtered_pf"] if cf["filtered_pf"] != float("inf") else 99.0,
                    cf["filtered_avg_net"],
                ),
                "",
                "Skipped %d opposed campaigns (their net %+.0f). Δ net = %+.0f."
                % (cf["skipped_n"], cf["skipped_net_usd"], cf["delta_net"]),
                "",
                "Judge on exposure-aware metrics, not N/S alone.",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No size-up on ALIGNED_BREAK.",
            "- No hybrid wick-retest + V2B P&L portfolio.",
            "- No joint tuning of seed width / V2B conditions.",
            "- Retest-fill states deferred (sample too selective).",
            "",
        ]
    )
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (hub / "STATUS.md").write_text(
        "# Status — V2B × wick-range alignment\n\n**Stance:** %s\n**Plugin:** blocked\n" % stance,
        encoding="utf-8",
    )
    if len(cal):
        cal.to_csv(hub / "calendar_blocks.csv", index=False)
    return stance


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument(
        "--skip-opposed-cf",
        action="store_true",
        help="Force matched-exposure skip-opposed counterfactual even if descriptive gate is soft",
    )
    ap.add_argument("--no-secondary", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug="nq_v2b_wick_range_alignment",
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={"smoke": args.smoke, "seed_hub": str(SEED_HUB.relative_to(REPO))},
    )
    try:
        if args.email:
            start = (
                "potions: V2B × wick-range alignment STARTED\n\n"
                "Hub: %s\nDescriptive state labels first; skip-opposed CF only if harmful.\n"
                % hub
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: V2B × wick-range alignment STARTED", body=start)

        _progress(hub, "build structure states from frozen NQ seeds")
        states = build_structure_states(smoke=args.smoke)
        pd.DataFrame(
            [
                {
                    "seed_id": s.seed_id,
                    "available_at": s.available_at.isoformat(),
                    "expires_at": s.expires_at.isoformat(),
                    "break_available_at": s.break_available_at.isoformat() if s.break_available_at else "",
                    "break_side": s.break_side,
                    "high": s.high,
                    "low": s.low,
                    "width": s.width,
                    "slice": s.slice,
                }
                for s in states
            ]
        ).to_csv(hub / "structure_states.csv", index=False)
        _progress(hub, "structure states n=%d" % len(states))

        _progress(hub, "load NQ V2B campaigns")
        primary = load_v2b_campaigns(PRIMARY)
        if args.smoke:
            primary = primary.head(40).copy()
        primary = annotate_campaigns(primary, states)
        primary.to_csv(hub / "campaigns_nq_primary.csv", index=False)

        summaries = summarize_by_state(primary, "NQ_primary")
        cal = calendar_blocks(primary)
        secondary = None
        if not args.no_secondary and SECONDARY["state_root"].exists():
            _progress(hub, "load MNQ V2B campaigns (secondary)")
            # MNQ uses NQ structure labels only as scale check — same NQ seed timestamps
            # are NOT valid on MNQ price path. Secondary reports V2B outcomes only if we
            # map by clock using NQ seeds as a shared macro clock (research diagnostic).
            secondary = load_v2b_campaigns(SECONDARY)
            if args.smoke:
                secondary = secondary.head(40).copy()
            secondary = annotate_campaigns(secondary, states)
            secondary.to_csv(hub / "campaigns_mnq_secondary.csv", index=False)
            summaries.extend(summarize_by_state(secondary, "MNQ_secondary"))
        else:
            _progress(hub, "MNQ secondary skipped")

        pd.DataFrame(summaries).to_csv(hub / "summary_by_state.csv", index=False)

        harmful = opposed_is_harmful([s for s in summaries if s["book"] == "NQ_primary"])
        cf = None
        if args.skip_opposed_cf or harmful:
            _progress(hub, "matched-exposure skip-opposed CF")
            cf = matched_exposure_skip_opposed(primary.sort_values("entry_ts"))
            (hub / "skip_opposed_cf.json").write_text(json.dumps(cf, indent=2), encoding="utf-8")

        stance = write_docs(
            hub,
            primary_camps=primary,
            secondary_camps=secondary,
            summaries=summaries,
            cal=cal,
            cf=cf,
            n_states=len(states),
            smoke=args.smoke,
        )
        (hub / "MODEL_CONTRACT.yaml").write_text(
            "\n".join(
                [
                    "study_id: nq_v2b_wick_range_alignment",
                    "v2b_book: nq_v2b_prior_opposed_stpmc_resting_limit S_1_1_3",
                    "structure: frozen nq_wick_reject_range_seed_retest seeds",
                    "require_retest_fill: false",
                    "size_up_aligned: false",
                    "hybrid_portfolio: false",
                    "action_if_opposed_harmful: skip_opposed_only_matched_exposure",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        # Email body
        core_lines = []
        for s in summaries:
            if s["book"] == "NQ_primary" and s["state"] in ("ALIGNED_BREAK", "OPPOSED_BREAK", "NO_ACTIVE_SEED"):
                core_lines.append(
                    "  %s: n=%d net=%+.0f WR=%.0f%% avg$=%+.0f"
                    % (s["state"], s["n"], s["net_usd"], 100 * s["win_rate"], s["avg_net"])
                )
        body = "\n".join(
            [
                "potions: V2B × wick-range alignment COMPLETE",
                "",
                "Hub: %s" % hub,
                "Stance: %s" % stance,
                "",
                "NQ primary by state:",
                *core_lines,
                "",
                ("Skip-opposed CF: " + json.dumps(cf)) if cf else "Skip-opposed CF: not run",
                "",
                "See SUMMARY.md.",
            ]
        )
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "stance": stance,
                    "harmful_opposed": harmful,
                    "cf": cf,
                    "summaries": summaries,
                    "smoke": args.smoke,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        all_row = next((s for s in summaries if s["book"] == "NQ_primary" and s["state"] == "ALL"), {})
        complete_run(
            rid,
            net_usd=float(all_row.get("net_usd") or 0.0),
            stress_dd_usd=float(all_row.get("stress_dd_usd") or 0.0),
            ns=float(all_row.get("ns") or 0.0) if all_row.get("ns") != float("inf") else None,
            trades=int(all_row.get("n") or 0),
            meta={"stance": stance, "harmful_opposed": harmful},
        )
        if args.email:
            send_email(subject="potions: V2B × wick-range alignment COMPLETE", body=body)
            _progress(hub, "email sent")
        _progress(hub, "DONE")
        return 0
    except Exception as e:
        fail_run(rid, notes=str(e))
        err = traceback.format_exc()
        _progress(hub, "FAILED: %s" % e)
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: V2B × wick-range alignment FAILED",
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
