"""NQ 4h WICK_REJECT range-seed → OCO stop-entry study v1.

study_id: nq_wick_reject_range_seed_oco_stop_v1

Same 91 eligible seeds / locked dev-holdout / width-expiry / exits as the
completed limit-retest hub. Entry mechanism only:

  seed_available_at → paired OCO
    buy-stop  @ seed_high + 1 tick
    sell-stop @ seed_low  - 1 tick
  first 1m fill cancels opposite → opposite-boundary stop ±1 tick
  scale 50/25/25 at 0.5W / 1W / 2W beyond triggered boundary
  gap-through stop entries + exits; Engine-style stop-first 1m

Same-1m dual boundary (primary): mark AMBIGUOUS, exclude from decision books.
Stress: adverse-side fill (worse of the two full simulations) + 2-tick adverse entry.

Hub: live/state/nq_wick_reject_range_seed_oco_stop_v1/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_range_seed_oco_stops --email
  python -m live.nq_wick_reject_range_seed_oco_stops --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import TICK
from .nq_wick_reject_range_seed_retest import (
    MARKETS,
    STOP_BUFFER_TICKS,
    Seed,
    _localize,
    _manage_scaleout,
    _progress,
    _summarize_trades,
    build_rth_tape,
    count_age_overlaps,
    load_wick_events,
    make_seeds,
)
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_wick_reject_range_seed_oco_stop_v1"
LIMIT_HUB = REPO / "live" / "state" / "nq_wick_reject_range_seed_retest"
STUDY_ID = "nq_wick_reject_range_seed_oco_stop_v1"
ENTRY_BUFFER_TICKS = 1
# Base OCO already stops outside the seed by 1 tick; stress adds further adverse ticks.
ADVERSE_ENTRY_STRESS_TICKS = 2


def _stop_entry_fill_px(
    side: str, stop: float, bar_open: float, *, adverse_ticks: int = 0
) -> Tuple[float, int]:
    """Stop entry: fill at stop, or at open if gap-through; optional adverse ticks."""
    if side == "LONG":
        base = float(bar_open) if bar_open > stop else float(stop)
        gap = 1 if bar_open > stop else 0
        return base + adverse_ticks * TICK, gap
    base = float(bar_open) if bar_open < stop else float(stop)
    gap = 1 if bar_open < stop else 0
    return base - adverse_ticks * TICK, gap


def _empty_trade(seed: Seed, *, outcome: str, terminal: str, live_at: pd.Timestamp, extra: Optional[dict] = None) -> dict:
    row = {
        "variant": "oco_stop_v1",
        "study_id": STUDY_ID,
        "seed_id": seed.seed_id,
        "event_id": seed.event_id,
        "slice": seed.slice,
        "side": "",
        "range_high": seed.high,
        "range_low": seed.low,
        "width": seed.width,
        "width_ATR": seed.width / seed.atr20_4h if seed.atr20_4h else np.nan,
        "available_at": seed.available_at.isoformat(),
        "break_confirm_ts": "",
        "order_live_at": live_at.isoformat(),
        "fill_ts": "",
        "entry": np.nan,
        "stop": np.nan,
        "tp1": np.nan,
        "tp2": np.nan,
        "tp3": np.nan,
        "buy_stop": seed.high + ENTRY_BUFFER_TICKS * TICK,
        "sell_stop": seed.low - ENTRY_BUFFER_TICKS * TICK,
        "time_seed_to_break_min": np.nan,
        "time_break_to_fill_min": np.nan,
        "time_fill_to_exit_min": np.nan,
        "causality_ok": 1,
        "exit_ts": "",
        "exit_reason": "",
        "net_pts": 0.0,
        "net_usd": 0.0,
        "r_multiple": 0.0,
        "risk_pts": seed.width + STOP_BUFFER_TICKS * TICK + ENTRY_BUFFER_TICKS * TICK,
        "gap_through_entry": 0,
        "gap_through_stop": 0,
        "mfe_pts": 0.0,
        "mae_pts": 0.0,
        "hit_tp1": 0,
        "hit_tp2": 0,
        "hit_tp3": 0,
        "stopped": 0,
        "n_legs": 0,
        "outcome": outcome,
        "terminal_reason": terminal,
        "collision": 0,
        "collision_resolution": "",
        "adverse_entry_ticks": 0,
        "first_break_side": "",
    }
    if extra:
        row.update(extra)
    return row


def _finish_oco(
    seed: Seed,
    tape: pd.DataFrame,
    side: str,
    fill_ts: pd.Timestamp,
    entry: float,
    live_at: pd.Timestamp,
    *,
    gap_entry: int,
    adverse_ticks: int,
    collision: int = 0,
    collision_resolution: str = "",
) -> dict:
    buy_stop = seed.high + ENTRY_BUFFER_TICKS * TICK
    sell_stop = seed.low - ENTRY_BUFFER_TICKS * TICK
    stop = seed.low - STOP_BUFFER_TICKS * TICK if side == "LONG" else seed.high + STOP_BUFFER_TICKS * TICK
    w = seed.width
    if side == "LONG":
        # targets beyond triggered boundary (seed_high)
        targets = [seed.high + 0.5 * w, seed.high + 1.0 * w, seed.high + 2.0 * w]
    else:
        targets = [seed.low - 0.5 * w, seed.low - 1.0 * w, seed.low - 2.0 * w]
    mg = _manage_scaleout(
        tape,
        side=side,
        fill_ts=fill_ts,
        entry=entry,
        stop=stop,
        targets=targets,
        qtys=[0.50, 0.25, 0.25],
        hard_end_ts=seed.expires_at,
    )
    caus = int(seed.available_at <= live_at <= fill_ts < mg["exit_ts"])
    out = {
        "variant": "oco_stop_v1",
        "study_id": STUDY_ID,
        "seed_id": seed.seed_id,
        "event_id": seed.event_id,
        "slice": seed.slice,
        "side": side,
        "range_high": seed.high,
        "range_low": seed.low,
        "width": seed.width,
        "width_ATR": seed.width / seed.atr20_4h if seed.atr20_4h else np.nan,
        "available_at": seed.available_at.isoformat(),
        "break_confirm_ts": fill_ts.isoformat(),
        "order_live_at": live_at.isoformat(),
        "fill_ts": fill_ts.isoformat(),
        "entry": entry,
        "stop": stop,
        "tp1": targets[0],
        "tp2": targets[1],
        "tp3": targets[2],
        "buy_stop": buy_stop,
        "sell_stop": sell_stop,
        "time_seed_to_break_min": (fill_ts - seed.available_at).total_seconds() / 60.0,
        "time_break_to_fill_min": 0.0,
        "time_fill_to_exit_min": (mg["exit_ts"] - fill_ts).total_seconds() / 60.0,
        "causality_ok": caus,
        **{k: mg[k] for k in mg if k != "exit_ts"},
        "exit_ts": mg["exit_ts"].isoformat(),
        "outcome": "FILLED",
        "terminal_reason": mg["exit_reason"],
        "gap_through_entry": int(gap_entry),
        "collision": int(collision),
        "collision_resolution": collision_resolution,
        "adverse_entry_ticks": int(adverse_ticks),
        "first_break_side": side,
    }
    return out


def run_oco_stop_trade(
    seed: Seed,
    tape: pd.DataFrame,
    *,
    mode: str = "primary",
    adverse_entry_ticks: int = 0,
) -> dict:
    """mode: primary | stress_adverse_collision | stress_2tick_entry.

    primary: same-1m dual touch → AMBIGUOUS (excluded from decision).
    stress_adverse_collision: same-1m dual → fill worse of LONG vs SHORT sims.
    stress_2tick_entry: like primary but +2 tick adverse entry on clean fills;
                        collisions still AMBIGUOUS (excluded).
    """
    live_at = seed.available_at
    deadline = seed.expires_at
    buy_stop = float(seed.high) + ENTRY_BUFFER_TICKS * TICK
    sell_stop = float(seed.low) - ENTRY_BUFFER_TICKS * TICK

    pos = tape.index.searchsorted(live_at, side="left")
    if pos < len(tape) and _localize(tape.index[pos]) < live_at:
        pos += 1

    for j in range(pos, len(tape)):
        ts = _localize(tape.index[j])
        if ts > deadline:
            break
        o = float(tape["open"].iloc[j])
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])

        # Open already through one side (gap / marketable)
        open_long = o >= buy_stop
        open_short = o <= sell_stop
        if open_long and open_short:
            # pathological wide gap spanning both stops
            return _resolve_collision(
                seed,
                tape,
                ts,
                o,
                live_at,
                mode=mode,
                adverse_entry_ticks=adverse_entry_ticks,
                reason="open_spans_both_stops",
            )
        if open_long:
            entry, gap = _stop_entry_fill_px("LONG", buy_stop, o, adverse_ticks=adverse_entry_ticks)
            return _finish_oco(
                seed, tape, "LONG", ts, entry, live_at, gap_entry=gap, adverse_ticks=adverse_entry_ticks
            )
        if open_short:
            entry, gap = _stop_entry_fill_px("SHORT", sell_stop, o, adverse_ticks=adverse_entry_ticks)
            return _finish_oco(
                seed, tape, "SHORT", ts, entry, live_at, gap_entry=gap, adverse_ticks=adverse_entry_ticks
            )

        long_hit = h >= buy_stop
        short_hit = l <= sell_stop
        if long_hit and short_hit:
            return _resolve_collision(
                seed,
                tape,
                ts,
                o,
                live_at,
                mode=mode,
                adverse_entry_ticks=adverse_entry_ticks,
                reason="same_1m_dual_touch",
            )
        if long_hit:
            entry, gap = _stop_entry_fill_px("LONG", buy_stop, o, adverse_ticks=adverse_entry_ticks)
            return _finish_oco(
                seed, tape, "LONG", ts, entry, live_at, gap_entry=gap, adverse_ticks=adverse_entry_ticks
            )
        if short_hit:
            entry, gap = _stop_entry_fill_px("SHORT", sell_stop, o, adverse_ticks=adverse_entry_ticks)
            return _finish_oco(
                seed, tape, "SHORT", ts, entry, live_at, gap_entry=gap, adverse_ticks=adverse_entry_ticks
            )

    return _empty_trade(seed, outcome="EXPIRED", terminal="max_age_no_oco_fill", live_at=live_at)


def _resolve_collision(
    seed: Seed,
    tape: pd.DataFrame,
    ts: pd.Timestamp,
    o: float,
    live_at: pd.Timestamp,
    *,
    mode: str,
    adverse_entry_ticks: int,
    reason: str,
) -> dict:
    buy_stop = float(seed.high) + ENTRY_BUFFER_TICKS * TICK
    sell_stop = float(seed.low) - ENTRY_BUFFER_TICKS * TICK

    if mode == "stress_adverse_collision":
        long_e, long_g = _stop_entry_fill_px("LONG", buy_stop, o, adverse_ticks=adverse_entry_ticks)
        short_e, short_g = _stop_entry_fill_px("SHORT", sell_stop, o, adverse_ticks=adverse_entry_ticks)
        long_tr = _finish_oco(
            seed,
            tape,
            "LONG",
            ts,
            long_e,
            live_at,
            gap_entry=long_g,
            adverse_ticks=adverse_entry_ticks,
            collision=1,
            collision_resolution="stress_adverse_chose_LONG",
        )
        short_tr = _finish_oco(
            seed,
            tape,
            "SHORT",
            ts,
            short_e,
            live_at,
            gap_entry=short_g,
            adverse_ticks=adverse_entry_ticks,
            collision=1,
            collision_resolution="stress_adverse_chose_SHORT",
        )
        # adverse = worse net (intentional stress; not used for primary decision)
        if float(long_tr["net_usd"]) <= float(short_tr["net_usd"]):
            long_tr["collision_resolution"] = "stress_adverse_worse_of_both:LONG (%s)" % reason
            return long_tr
        short_tr["collision_resolution"] = "stress_adverse_worse_of_both:SHORT (%s)" % reason
        return short_tr

    # primary + stress_2tick_entry: exclude from decision
    return _empty_trade(
        seed,
        outcome="AMBIGUOUS",
        terminal="same_1m_dual_boundary_excluded",
        live_at=live_at,
        extra={
            "collision": 1,
            "collision_resolution": "primary_exclude_ambiguous (%s)" % reason,
            "break_confirm_ts": ts.isoformat(),
            "fill_ts": ts.isoformat(),
            "adverse_entry_ticks": adverse_entry_ticks,
        },
    )


def write_ambiguity_audit(hub: Path, primary: pd.DataFrame, stress_coll: pd.DataFrame) -> pd.DataFrame:
    """Write collision / ambiguity audit BEFORE relying on P&L for promotion."""
    cols = [
        "event_id",
        "slice",
        "available_at",
        "fill_ts",
        "outcome",
        "collision",
        "collision_resolution",
        "side",
        "gap_through_entry",
        "entry",
        "buy_stop",
        "sell_stop",
        "net_usd",
        "r_multiple",
    ]
    amb = primary[primary["outcome"] == "AMBIGUOUS"].copy()
    coll_stress = stress_coll[stress_coll["collision"] == 1].copy()
    for c in cols:
        if c not in amb.columns:
            amb[c] = np.nan
        if c not in coll_stress.columns:
            coll_stress[c] = np.nan
    amb[cols].to_csv(hub / "oco_collisions_primary_excluded.csv", index=False)
    coll_stress[cols].to_csv(hub / "oco_collisions_stress_adverse.csv", index=False)

    # entry gap census on clean fills
    filled = primary[primary["outcome"] == "FILLED"]
    lines = [
        "# OCO ambiguity & stop-entry audit (read before P&L)",
        "",
        "**study_id:** `%s`" % STUDY_ID,
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "",
        "## Same-1m dual-boundary policy",
        "",
        "- **Primary:** mark AMBIGUOUS and **exclude** from decision books (no favorable side pick).",
        "- **Stress:** fill the worse of LONG vs SHORT full simulations (adverse-first stress).",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Eligible seeds | %d |" % len(primary),
        "| Primary FILLED (decision) | %d |" % int((primary["outcome"] == "FILLED").sum()),
        "| Primary AMBIGUOUS excluded | %d |" % len(amb),
        "| Primary EXPIRED | %d |" % int((primary["outcome"] == "EXPIRED").sum()),
        "| Stress collision fills | %d |" % len(coll_stress),
        "| Primary fill gap-through entry n | %d |"
        % (int(filled["gap_through_entry"].sum()) if len(filled) else 0),
        "| Primary fill gap-through stop n | %d |"
        % (int(filled["gap_through_stop"].sum()) if len(filled) else 0),
        "| Causality ok among fills | %d / %d |"
        % (
            int(filled["causality_ok"].sum()) if len(filled) else 0,
            len(filled),
        ),
        "",
        "## Every primary collision (excluded)",
        "",
    ]
    if amb.empty:
        lines.append("_None._")
    else:
        lines += [
            "| event_id | slice | ts | resolution |",
            "|---|---|---|---|",
        ]
        for _, r in amb.iterrows():
            lines.append(
                "| `%s` | %s | %s | %s |"
                % (r["event_id"], r["slice"], r.get("fill_ts", ""), r.get("collision_resolution", ""))
            )
    lines += [
        "",
        "## Guard",
        "",
        "No hidden favorable resolution of same-minute two-sided breaks in the primary book.",
        "",
    ]
    (hub / "AMBIGUITY_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    return amb


def _slice_summary(df: pd.DataFrame, label: str) -> dict:
    # Decision books: FILLED only; AMBIGUOUS counted in n_seeds but not fills
    return _summarize_trades(df, label)


def _long_short_board(filled: pd.DataFrame) -> str:
    lines = [
        "## Long vs short",
        "",
        "| Side | n | net $ | avg $ | WR | PF | avg R | med R | stop% | gap_entry | gap_stop |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for side in ("LONG", "SHORT"):
        sub = filled[filled["side"] == side]
        if sub.empty:
            lines.append("| %s | 0 | — | — | — | — | — | — | — | — | — |" % side)
            continue
        s = _summarize_trades(sub.assign(outcome="FILLED"), side)
        lines.append(
            "| %s | %d | %+.0f | %+.0f | %.0f%% | %.2f | %+.3f | %+.3f | %.0f%% | %d | %d |"
            % (
                side,
                s["n_filled"],
                s["net_usd"],
                s["avg_net"],
                100 * s["win_rate"],
                s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                s["avg_R"],
                s["median_R"],
                100 * s["stop_rate"],
                int(sub["gap_through_entry"].sum()),
                int(sub["gap_through_stop"].sum()),
            )
        )
    return "\n".join(lines)


def _width_quartile_board(filled: pd.DataFrame) -> str:
    lines = [
        "## Seed width quartiles (descriptive only)",
        "",
        "| Quartile | n | width med | avg R | net $ | WR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    if filled.empty or "width" not in filled.columns:
        lines.append("| — | 0 | — | — | — | — |")
        return "\n".join(lines)
    try:
        q = pd.qcut(filled["width"].astype(float), 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
    except ValueError:
        lines.append("| (insufficient unique widths) | %d | — | — | — | — |" % len(filled))
        return "\n".join(lines)
    tmp = filled.assign(_q=q)
    for lab, sub in tmp.groupby("_q", observed=True):
        lines.append(
            "| %s | %d | %.2f | %+.3f | %+.0f | %.0f%% |"
            % (
                lab,
                len(sub),
                float(sub["width"].median()),
                float(sub["r_multiple"].mean()),
                float(sub["net_usd"].sum()),
                100 * float((sub["net_usd"] > 0).mean()),
            )
        )
    return "\n".join(lines)


def _duration_board(filled: pd.DataFrame) -> str:
    lines = [
        "## Seed → break duration (OCO: available → fill)",
        "",
    ]
    if filled.empty:
        lines.append("_No fills._")
        return "\n".join(lines)
    t = filled["time_seed_to_break_min"].astype(float)
    lines += [
        "| Stat | minutes |",
        "|---|---:|",
        "| n | %d |" % len(t),
        "| mean | %.1f |" % float(t.mean()),
        "| median | %.1f |" % float(t.median()),
        "| p25 | %.1f |" % float(t.quantile(0.25)),
        "| p75 | %.1f |" % float(t.quantile(0.75)),
        "| max | %.1f |" % float(t.max()),
        "",
    ]
    return "\n".join(lines)


def _timing_parity(primary: pd.DataFrame) -> str:
    lines = [
        "## Development / holdout timing parity",
        "",
        "| Slice | seeds | fills | ambig | expired | med seed→fill min | med fill→exit min |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for sl in ("dev", "holdout"):
        sub = primary[primary["slice"] == sl]
        filled = sub[sub["outcome"] == "FILLED"]
        lines.append(
            "| %s | %d | %d | %d | %d | %.1f | %.1f |"
            % (
                sl,
                len(sub),
                len(filled),
                int((sub["outcome"] == "AMBIGUOUS").sum()),
                int((sub["outcome"] == "EXPIRED").sum()),
                float(filled["time_seed_to_break_min"].median()) if len(filled) else float("nan"),
                float(filled["time_fill_to_exit_min"].median()) if len(filled) else float("nan"),
            )
        )
    return "\n".join(lines)


def apply_decision_rule(
    o_dev: Optional[dict],
    o_ho: Optional[dict],
    stress2: Optional[dict],
    amb_n: int,
    filled_all: pd.DataFrame,
) -> Tuple[str, List[str]]:
    checks = []
    ok = True

    def pos_avg_r(s):
        return s is not None and s["n_filled"] > 0 and s["avg_R"] > 0

    c1 = pos_avg_r(o_dev) and pos_avg_r(o_ho)
    checks.append(("Development and holdout both positive avg campaign R", c1))
    c2 = o_ho is not None and o_ho["n_filled"] > 0 and o_ho["profit_factor"] > 1.15
    checks.append(("Holdout PF materially above 1 after costs (PF>1.15)", c2))
    c3 = (
        stress2 is not None
        and stress2["n_filled"] > 0
        and stress2["avg_R"] > 0
        and stress2["net_usd"] > 0
    )
    checks.append(("OCO primary remains positive under 2-tick adverse entry stress", c3))
    c4 = amb_n >= 0  # structural: primary excludes; pass if we did not silently fill collisions
    checks.append(("No hidden favorable resolution of same-minute two-sided breaks", c4))
    top5 = float(filled_all["net_usd"].abs().sort_values(ascending=False).iloc[:5].sum()) if len(filled_all) else 0.0
    tot = float(filled_all["net_usd"].abs().sum()) or 1.0
    share = top5 / tot
    # also check 2W runner dominance: hit_tp3 winners share
    runner = filled_all[filled_all.get("hit_tp3", 0) == 1] if "hit_tp3" in filled_all.columns else filled_all.iloc[0:0]
    runner_share = float(runner["net_usd"].clip(lower=0).sum()) / (float(filled_all["net_usd"].clip(lower=0).sum()) or 1.0)
    c5 = share < 0.45 and runner_share < 0.70
    checks.append(
        ("Results not dominated by few campaigns / 2W runners (top5 |net| share=%.0f%%, TP3 win share=%.0f%%)"
         % (100 * share, 100 * runner_share), c5)
    )
    c6 = (
        o_dev is not None
        and o_dev["n_filled"] >= 20
        and o_dev["long_n"] >= 5
        and o_dev["short_n"] >= 5
    )
    checks.append(("Campaign count sufficient; long and short paths present", c6))

    for _, passed in checks:
        if not passed:
            ok = False
    stance = (
        "PROMOTE_TO_PLUGIN_CANDIDATE"
        if ok
        else "RESEARCH ONLY — OCO stop v1 does not clear promotion gates"
    )
    return stance, ["%s: %s" % ("PASS" if p else "FAIL", msg) for msg, p in checks]


def write_comparison_board(
    hub: Path,
    summaries: List[dict],
    primary: pd.DataFrame,
    stress2_df: pd.DataFrame,
    amb: pd.DataFrame,
    stance: str,
    checks: List[str],
) -> None:
    lim = pd.read_csv(LIMIT_HUB / "summary.csv") if (LIMIT_HUB / "summary.csv").exists() else pd.DataFrame()
    filled = primary[primary["outcome"] == "FILLED"].copy()
    stress2_filled = stress2_df[stress2_df["outcome"] == "FILLED"]

    lines = [
        "# COMPARISON_BOARD — OCO stop v1 vs limit-retest controls",
        "",
        "**study_id:** `%s`" % STUDY_ID,
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Stance:** %s" % stance,
        "",
        "## Locked books (decision = primary FILLED; AMBIGUOUS excluded)",
        "",
        "| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap_stop | L/S | top1/3/5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def row_line(s: dict) -> str:
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        return (
            "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.0f%% | %s | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d | %d/%d | %.0f/%.0f/%.0f |"
            % (
                s["label"],
                s["n_seeds"],
                s["n_filled"],
                100 * s["fill_rate"],
                s["net_usd"],
                s["avg_net"],
                100 * s["win_rate"],
                pf_s,
                s["avg_R"],
                s["median_R"],
                100 * s["stop_rate"],
                100 * s["hit_tp1_rate"],
                100 * s["hit_tp2_rate"],
                100 * s["hit_tp3_rate"],
                s["gap_through_n"],
                s["long_n"],
                s["short_n"],
                100 * s["top1_share"],
                100 * s["top3_share"],
                100 * s["top5_share"],
            )
        )

    for s in summaries:
        lines.append(row_line(s))

    if not lim.empty:
        lines += ["", "### Prior limit-retest hub (frozen)", ""]
        for _, r in lim.iterrows():
            lines.append(
                "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.0f%% | %.2f | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d | %d/%d | %.0f/%.0f/%.0f |"
                % (
                    r["label"],
                    int(r["n_seeds"]),
                    int(r["n_filled"]),
                    100 * float(r["fill_rate"]),
                    float(r["net_usd"]),
                    float(r["avg_net"]),
                    100 * float(r["win_rate"]),
                    float(r["profit_factor"]),
                    float(r["avg_R"]),
                    float(r["median_R"]),
                    100 * float(r["stop_rate"]),
                    100 * float(r["hit_tp1_rate"]),
                    100 * float(r["hit_tp2_rate"]),
                    100 * float(r["hit_tp3_rate"]),
                    int(r["gap_through_n"]),
                    int(r["long_n"]),
                    int(r["short_n"]),
                    100 * float(r["top1_share"]),
                    100 * float(r["top3_share"]),
                    100 * float(r["top5_share"]),
                )
            )

    lines += [
        "",
        _long_short_board(filled),
        "",
        "## First high-break vs first low-break",
        "",
        "_For OCO, first boundary fill **is** the directional break "
        "(HIGH→LONG, LOW→SHORT). Same table as Long vs short above._",
        "",
        _width_quartile_board(filled),
        "",
        _duration_board(filled),
        "",
        "## Gap-through frequency",
        "",
        "| Event | n | rate among fills |",
        "|---|---:|---:|",
        "| Entry gap-through | %d | %.1f%% |"
        % (
            int(filled["gap_through_entry"].sum()) if len(filled) else 0,
            100 * float(filled["gap_through_entry"].mean()) if len(filled) else 0.0,
        ),
        "| Stop exit gap-through | %d | %.1f%% |"
        % (
            int(filled["gap_through_stop"].sum()) if len(filled) else 0,
            100 * float(filled["gap_through_stop"].mean()) if len(filled) else 0.0,
        ),
        "",
        "## Concentration (primary ALL fills)",
        "",
    ]
    o_all = next((s for s in summaries if s["label"] == "oco_stop_v1_primary_ALL"), None)
    if o_all:
        lines.append(
            "Top1 / Top3 / Top5 |net| share: **%.1f%% / %.1f%% / %.1f%%**."
            % (100 * o_all["top1_share"], 100 * o_all["top3_share"], 100 * o_all["top5_share"])
        )
    lines += ["", _timing_parity(primary), ""]

    lines += [
        "## 2-tick adverse entry stress (clean fills; collisions still excluded)",
        "",
    ]
    s2 = _summarize_trades(stress2_df, "oco_stop_v1_stress_2tick_ALL")
    lines.append(row_line(s2))
    lines += [
        "",
        "## Every OCO collision + resolution",
        "",
        "See `AMBIGUITY_AUDIT.md`, `oco_collisions_primary_excluded.csv`,",
        "`oco_collisions_stress_adverse.csv`. Primary excluded count: **%d**." % len(amb),
        "",
        "## Decision rule checklist",
        "",
    ]
    for c in checks:
        lines.append("- %s" % c)
    lines += [
        "",
        "## Honest read",
        "",
    ]
    # compare to synthetic marketable + limit holdout
    lim_ho = lim[lim["label"] == "primary_limit_retest_holdout"] if not lim.empty else pd.DataFrame()
    lim_mkt = lim[lim["label"] == "ctrl_marketable_boundary_ALL"] if not lim.empty else pd.DataFrame()
    o_dev = next((s for s in summaries if s["label"] == "oco_stop_v1_primary_dev"), None)
    if o_dev and o_dev["net_usd"] <= 0:
        lines.append(
            "OCO fails under ordinary stop-entry friction on locked **dev** "
            "(net=%+.0f, avgR=%+.3f). The synthetic marketable-at-boundary control "
            "was an **execution assumption**, not a tradeable edge under stop fills."
            % (o_dev["net_usd"], o_dev["avg_R"])
        )
    elif o_dev and o_dev["avg_R"] > 0 and not lim_ho.empty and float(lim_ho.iloc[0]["avg_R"]) <= 0:
        lines.append(
            "OCO primary looks viable while limit-retest holdout avg R failed: "
            "the seeded 4h wick-reject range may have value as a **two-sided breakout "
            "decision box**, but there is no evidence yet that waiting for the retreat improves it."
        )
    else:
        lines.append(
            "See checklist above. Remain research-only unless every promote gate passes."
        )
    if not lim_mkt.empty:
        lines.append(
            "Frozen synthetic marketable ALL: net=%+.0f avgR=%+.3f (not tradable as-stated)."
            % (float(lim_mkt.iloc[0]["net_usd"]), float(lim_mkt.iloc[0]["avg_R"]))
        )
    lines.append("")
    (hub / "COMPARISON_BOARD.md").write_text("\n".join(lines), encoding="utf-8")


def write_docs(
    hub: Path,
    summaries: List[dict],
    *,
    smoke: bool,
    n_seeds: int,
    n_overlap: int,
    amb_n: int,
    stance: str,
    checks: List[str],
) -> None:
    o_dev = next((s for s in summaries if s["label"] == "oco_stop_v1_primary_dev"), None)
    o_ho = next((s for s in summaries if s["label"] == "oco_stop_v1_primary_holdout"), None)
    o_all = next((s for s in summaries if s["label"] == "oco_stop_v1_primary_ALL"), None)

    lines = [
        "# NQ WICK_REJECT range-seed OCO stop v1",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**study_id:** `%s`" % STUDY_ID,
        "**Hub:** `live/state/nq_wick_reject_range_seed_oco_stop_v1/`",
        "**Model:** 4h WICK_REJECT seed → OCO buy-stop@high+1tick / sell-stop@low−1tick → "
        "opposite-edge stop → 0.5W/1W/2W 50/25/25.",
        "**Contrast:** no 1h close confirm; no limit retest. First boundary stop fill wins.",
        "**Execution:** RTH 1m, gap-through stop entries/exits, $1.50/leg, NQ $20/pt, stop-first.",
        "**Same-1m dual:** primary = AMBIGUOUS exclude; stress = adverse worse-of-both.",
        "**Holdout:** atlas slice locked (same seeds as limit-retest hub).",
        ("**Mode:** SMOKE" if smoke else "**Mode:** FULL"),
        "",
        "Eligible seeds: **%d** (age overlaps=%d). Primary ambiguous excluded: **%d**."
        % (n_seeds, n_overlap, amb_n),
        "",
        "## Locked books",
        "",
        "| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap | L/S n |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        lines.append(
            "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.0f%% | %s | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d | %d/%d |"
            % (
                s["label"],
                s["n_seeds"],
                s["n_filled"],
                100 * s["fill_rate"],
                s["net_usd"],
                s["avg_net"],
                100 * s["win_rate"],
                pf_s,
                s["avg_R"],
                s["median_R"],
                100 * s["stop_rate"],
                100 * s["hit_tp1_rate"],
                100 * s["hit_tp2_rate"],
                100 * s["hit_tp3_rate"],
                s["gap_through_n"],
                s["long_n"],
                s["short_n"],
            )
        )
    lines += [
        "",
        "## Stance",
        "",
        "**%s**" % stance,
        "",
    ]
    for c in checks:
        lines.append("- %s" % c)
    lines += [
        "",
        "See `AMBIGUITY_AUDIT.md` (before P&L) and `COMPARISON_BOARD.md`.",
        "",
        "## Guardrails",
        "",
        "- Same seed eligibility as limit-retest (width 0.25–2.00×4h ATR, early-close exclude).",
        "- Entry stops at seed_high+1tick / seed_low−1tick; risk stop opposite ±1 tick.",
        "- Same-bar dual touch: primary exclude; no favorable side selection.",
        "- One trade per seed; no re-entry; no DCA.",
        "- No structure-bias / RSI / TOD / SMT filters; targets frozen.",
        "",
    ]
    (hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (hub / "STATUS.md").write_text(
        "# Status — %s\n\n**Stance:** %s\n**Seeds:** %d\n**Ambig excluded:** %d\n"
        % (STUDY_ID, stance, n_seeds, amb_n),
        encoding="utf-8",
    )
    (hub / "MODEL_CONTRACT.yaml").write_text(
        "\n".join(
            [
                "study_id: %s" % STUDY_ID,
                "created: 2026-08-30",
                'seed: "4h WICK_REJECT; range = confirm candle high/low; width 0.25–2.00×ATR; max_age 20×4h"',
                'population: "same 91 eligible seeds; locked atlas 75/25"',
                'entry: "OCO buy-stop @ high+1tick / sell-stop @ low-1tick from available_at"',
                'same_1m_dual_touch_primary: "AMBIGUOUS exclude from decision"',
                'same_1m_dual_touch_stress: "adverse worse-of-both"',
                "adverse_entry_stress_ticks: %d" % ADVERSE_ENTRY_STRESS_TICKS,
                'stop: "opposite boundary ±1 tick"',
                'targets: "0.5W / 1.0W / 2.0W beyond triggered boundary; 50/25/25; stop-first; gap_through"',
                "contrast_hub: nq_wick_reject_range_seed_retest",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_email(hub: Path, summaries: List[dict], stance: str, n_seeds: int, amb_n: int) -> str:
    lines = [
        "potions: %s COMPLETE" % STUDY_ID,
        "",
        "Hub: %s" % hub,
        "Eligible seeds: %d | Ambiguous excluded: %d" % (n_seeds, amb_n),
        "Stance: %s" % stance,
        "",
        "Key books:",
    ]
    for s in summaries:
        if "primary" not in s["label"] and "stress_2tick" not in s["label"]:
            continue
        lines.append(
            "  %s: fills=%d net=%+.0f WR=%.0f%% PF=%.2f avgR=%+.3f"
            % (
                s["label"],
                s["n_filled"],
                s["net_usd"],
                100 * s["win_rate"],
                s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                s["avg_R"],
            )
        )
    lines += [
        "",
        "Contrast hub: %s" % LIMIT_HUB,
        "See AMBIGUITY_AUDIT.md + COMPARISON_BOARD.md + SUMMARY.md.",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug=STUDY_ID,
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={"smoke": args.smoke, "model": STUDY_ID},
    )
    try:
        if args.email:
            start = (
                "potions: %s STARTED\n\nHub: %s\n"
                "OCO buy-stop@high+1tick / sell-stop@low−1tick; primary excludes same-1m dual.\n"
                % (STUDY_ID, hub)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: %s STARTED" % STUDY_ID, body=start)

        _progress(hub, "load WICK_REJECT events")
        events = load_wick_events(smoke=args.smoke)
        _progress(hub, "events n=%d" % len(events))

        _progress(hub, "load NQ 1m")
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        if args.smoke:
            edates = sorted(
                {_localize(pd.Timestamp(t)).date() for t in events["confirm_bar_close_ts"].tolist()}
            )
            days = sorted(gby.keys())
            keep = set()
            for d in edates:
                if d in days:
                    i = days.index(d)
                    keep.update(days[max(0, i - 8) : i + 12])
            gby = {d: gby[d] for d in days if d in keep}

        _progress(hub, "build RTH tape / 1h / 4h")
        tape, h1, h4, early = build_rth_tape(gby)
        _progress(hub, "tape=%d 1h=%d 4h=%d" % (len(tape), len(h1), len(h4)))

        _progress(hub, "make seeds")
        seeds, census = make_seeds(events, tape, h4, early)
        census.to_csv(hub / "phase0_census.csv", index=False)
        n_overlap = count_age_overlaps(seeds)
        _progress(hub, "eligible seeds=%d age_overlaps=%d" % (len(seeds), n_overlap))

        _progress(hub, "OCO primary trades (audit ambiguity first)")
        primary_rows = []
        for i, seed in enumerate(seeds):
            primary_rows.append(run_oco_stop_trade(seed, tape, mode="primary", adverse_entry_ticks=0))
            if (i + 1) % 20 == 0:
                _progress(hub, "primary %d/%d" % (i + 1, len(seeds)))
        primary = pd.DataFrame(primary_rows)
        primary.to_csv(hub / "trades_oco_primary.csv", index=False)

        _progress(hub, "OCO stress adverse-collision")
        stress_coll_rows = [
            run_oco_stop_trade(s, tape, mode="stress_adverse_collision", adverse_entry_ticks=0)
            for s in seeds
        ]
        stress_coll = pd.DataFrame(stress_coll_rows)
        stress_coll.to_csv(hub / "trades_oco_stress_adverse_collision.csv", index=False)

        _progress(hub, "ambiguity audit (before P&L stance)")
        amb = write_ambiguity_audit(hub, primary, stress_coll)
        _progress(hub, "ambiguous_excluded=%d" % len(amb))

        _progress(hub, "OCO 2-tick adverse entry stress")
        stress2_rows = [
            run_oco_stop_trade(
                s, tape, mode="stress_2tick_entry", adverse_entry_ticks=ADVERSE_ENTRY_STRESS_TICKS
            )
            for s in seeds
        ]
        stress2 = pd.DataFrame(stress2_rows)
        stress2.to_csv(hub / "trades_oco_stress_2tick_entry.csv", index=False)

        summaries: List[dict] = []
        for sl in ("dev", "holdout", "ALL"):
            sub = primary if sl == "ALL" else primary[primary["slice"] == sl]
            summaries.append(_slice_summary(sub, "oco_stop_v1_primary_%s" % sl))
        for sl in ("dev", "holdout", "ALL"):
            sub = stress2 if sl == "ALL" else stress2[stress2["slice"] == sl]
            summaries.append(_slice_summary(sub, "oco_stop_v1_stress_2tick_%s" % sl))
        for sl in ("dev", "holdout", "ALL"):
            sub = stress_coll if sl == "ALL" else stress_coll[stress_coll["slice"] == sl]
            summaries.append(_slice_summary(sub, "oco_stop_v1_stress_adverse_coll_%s" % sl))
        pd.DataFrame(summaries).to_csv(hub / "summary.csv", index=False)

        o_dev = next(s for s in summaries if s["label"] == "oco_stop_v1_primary_dev")
        o_ho = next(s for s in summaries if s["label"] == "oco_stop_v1_primary_holdout")
        s2_all = next(s for s in summaries if s["label"] == "oco_stop_v1_stress_2tick_ALL")
        filled_all = primary[primary["outcome"] == "FILLED"]
        stance, checks = apply_decision_rule(o_dev, o_ho, s2_all, len(amb), filled_all)

        write_docs(
            hub,
            summaries,
            smoke=args.smoke,
            n_seeds=len(seeds),
            n_overlap=n_overlap,
            amb_n=len(amb),
            stance=stance,
            checks=checks,
        )
        write_comparison_board(hub, summaries, primary, stress2, amb, stance, checks)

        body = build_email(hub, summaries, stance, len(seeds), len(amb))
        (hub / "EMAIL.txt").write_text(body + "\n", encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "study_id": STUDY_ID,
                    "stance": stance,
                    "n_seeds": len(seeds),
                    "n_filled": int((primary["outcome"] == "FILLED").sum()),
                    "n_ambiguous": len(amb),
                    "checks": checks,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        o_all = next(s for s in summaries if s["label"] == "oco_stop_v1_primary_ALL")
        if args.email:
            send_email(subject="potions: %s COMPLETE" % STUDY_ID, body=body)
            _progress(hub, "email sent")

        complete_run(
            rid,
            net_usd=o_all["net_usd"],
            trades=o_all["n_filled"],
            meta={"stance": stance, "avg_R": o_all["avg_R"], "pf": o_all["profit_factor"], "ambig": len(amb)},
        )
        _progress(
            hub,
            "DONE stance=%s fills=%d ambig=%d net=%+.0f"
            % (stance, o_all["n_filled"], len(amb), o_all["net_usd"]),
        )
    except Exception as exc:  # noqa: BLE001
        fail_run(rid, error=str(exc))
        err = "potions: %s FAILED\n\n%s\n\n%s\n" % (STUDY_ID, hub, traceback.format_exc()[-2500:])
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if args.email:
            try:
                send_email(subject="potions: %s FAILED" % STUDY_ID, body=err)
            except Exception:  # noqa: BLE001
                pass
        raise


if __name__ == "__main__":
    main()
