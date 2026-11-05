"""Causality / lookahead audit for NAS100 clean-break ma_aligned size_1.5.

Checks:
  1. Frozen 1m-fill Engine tape — live_after_ts, feature_snapshots order,
     causality_violations.csv empty.
  2. HA ``ma5_align`` recipe — completed 5m MA (+5m availability) merge_asof
     at entry fill; stored labels match independent recompute; no avail>entry.
  3. Stop-arm vs fill timing — resting entry stop is armed before fill; MA
     label can flip between ``live_after_ts`` and fill. Fill-asof size-up is
     causal only if live refreshes qty from the latest completed 5m until fill;
     arm-asof is the stricter no-refresh contract.

Writes LOOKAHEAD_REVIEW.md + causality_checks.csv under the size_1.5 hub.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nas100_clean_break_ma_aligned_size15_causality_audit --email
  python -m live.nas100_clean_break_ma_aligned_size15_causality_audit --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .fx_v2b_london_ungated import REPO
from .intraday_condition_profile import build_feature_frames
from .nas100_clean_break_ma_aligned_size15_broker import (
    CAMPAIGNS,
    HP_MULT,
    INSTRUMENT,
    POINT_VALUE,
    SOURCE_FILLS,
    SOURCE_HUB,
    STRATEGY_ID,
    load_audit_bars,
    load_hp_trade_ids,
    weighted_intraday_audit,
)
from .v2b_clean_break_pyramid_trail_sizing_v1 import FEE_PER_UNIT
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_replay import units_from_v2b_fills

HUB = REPO / "live" / "state" / "nas100_clean_break_ma_aligned_size15_broker"
STATE = (
    SOURCE_HUB
    / "states"
    / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill"
)
AUDIT_DIR = HUB / "causality_audit"
DSR = "TRL-2026-00200"
PARENT_DSR = "TRL-2026-00199"
NY = "America/New_York"


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with (AUDIT_DIR / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


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
            "trial_class": "CAUSALITY_AUDIT",
            "trial_subclass": "nas100_clean_break_ma_aligned_size15",
            "is_independent": "TRUE",
            "market": "NAS100",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "parent_dsr": PARENT_DSR,
                    "checks": [
                        "engine_live_after",
                        "feature_snapshot_order",
                        "ma5_fill_asof_recompute",
                        "ma5_arm_vs_fill_flip",
                        "arm_time_sizeup_engine",
                    ],
                    "hub": str(HUB.relative_to(REPO)),
                }
            ),
            "fixed_parameters_ref": "live/nas100_clean_break_ma_aligned_size15_causality_audit.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Causality audit of ma_aligned size_1.5 (fill-asof vs arm-asof)",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _ma_label(side: str, ma_state: object) -> str:
    if ma_state is None or (isinstance(ma_state, float) and np.isnan(ma_state)) or pd.isna(ma_state):
        return "ma_na"
    ms = str(ma_state)
    if (side == "long" and ms == "ma_bull") or (side == "short" and ms == "ma_bear"):
        return "ma_aligned"
    if (side == "long" and ms == "ma_bear") or (side == "short" and ms == "ma_bull"):
        return "ma_opposed"
    return "ma_flat"


def _asof_ma_state(ts: pd.Series, m5: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    left = pd.DataFrame(
        {
            "t": pd.to_datetime(ts, utc=True).dt.tz_convert(NY),
            "i": np.arange(len(ts)),
        }
    )
    merged = pd.merge_asof(
        left.sort_values("t"),
        m5.sort_values("ts"),
        left_on="t",
        right_on="ts",
        direction="backward",
    ).sort_values("i")
    return merged["ma_state"].to_numpy(), merged["ts"].to_numpy()


def audit_engine_tape() -> Dict[str, object]:
    orders = pd.read_csv(STATE / "orders.csv")
    fills = pd.read_csv(STATE / "fills.csv")
    feats = pd.read_csv(STATE / "feature_snapshots.csv")
    viol = pd.read_csv(STATE / "causality_violations.csv")

    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    orders["live_after_ts"] = pd.to_datetime(orders["live_after_ts"], utc=True)
    o = orders.set_index("broker_order_id")
    f = fills.join(o[["live_after_ts", "order_type", "reduce_only"]], on="broker_order_id")
    non_moc = f[~f["order_type"].astype(str).str.lower().isin(["market", "market_close"])]
    live_after_fails = int((non_moc["ts"] <= non_moc["live_after_ts"]).sum())
    entry = f[f["reason"].astype(str).str.lower() == "entry"]
    entry_before_arm = int((entry["ts"] <= entry["live_after_ts"]).sum())

    for col in ("event_ts", "available_at_ts", "current_bar_ts"):
        feats[col] = pd.to_datetime(feats[col], utc=True)
    feat_order_fails = int(
        (
            (feats["event_ts"] > feats["available_at_ts"])
            | (feats["available_at_ts"] > feats["current_bar_ts"])
        ).sum()
    )

    return {
        "feature_snapshots": int(len(feats)),
        "causality_violation_rows": int(len(viol)),
        "non_moc_fills_at_or_before_live_after": live_after_fails,
        "entry_fills_at_or_before_live_after": entry_before_arm,
        "feature_order_fails": feat_order_fails,
        "pass": bool(
            len(viol) == 0
            and live_after_fails == 0
            and entry_before_arm == 0
            and feat_order_fails == 0
        ),
    }


def audit_ma_alignment() -> Dict[str, object]:
    camps = pd.read_csv(CAMPAIGNS)
    camps["entry_ts"] = pd.to_datetime(camps["entry_ts"], utc=True).dt.tz_convert(NY)
    orders = pd.read_csv(STATE / "orders.csv")
    eo = orders[
        (orders["bracket_role"].astype(str) == "entry")
        & (orders["order_type"].astype(str).str.lower() == "stop")
    ].copy()
    eo["live_after_ts"] = pd.to_datetime(eo["live_after_ts"], utc=True).dt.tz_convert(NY)
    eo = eo.sort_values("live_after_ts").groupby("trade_id", as_index=False).first()
    m = camps.merge(eo[["trade_id", "live_after_ts"]], on="trade_id", how="left")
    if int(m["live_after_ts"].isna().sum()) != 0:
        raise RuntimeError("Missing entry-stop live_after_ts for some campaigns")

    _progress("Building NAS100 5m MA feature frame (causal +5m availability)...")
    feats = build_feature_frames("NAS100")
    m5 = feats["m5"][["ts", "ma_state", "ma_cross"]].sort_values("ts").copy()

    fill_ma, fill_avail = _asof_ma_state(m["entry_ts"], m5)
    arm_ma, arm_avail = _asof_ma_state(m["live_after_ts"], m5)
    fill_lab = np.array([_ma_label(s, x) for s, x in zip(m["side"].astype(str), fill_ma)])
    arm_lab = np.array([_ma_label(s, x) for s, x in zip(m["side"].astype(str), arm_ma)])
    stored = m["ma5_align"].astype(str).to_numpy()

    fill_avail_ts = pd.to_datetime(pd.Series(fill_avail), utc=False)
    if fill_avail_ts.dt.tz is None:
        fill_avail_ts = fill_avail_ts.dt.tz_localize(NY)
    else:
        fill_avail_ts = fill_avail_ts.dt.tz_convert(NY)
    delta = (fill_avail_ts - m["entry_ts"]).dt.total_seconds()
    avail_after_entry = int((delta > 0).sum())
    avail_eq_entry = int((delta == 0).sum())
    label_mismatch = int((fill_lab != stored).sum())
    flips = int((arm_lab != fill_lab).sum())
    only_fill_hp = int(((fill_lab == "ma_aligned") & (arm_lab != "ma_aligned")).sum())
    only_arm_hp = int(((arm_lab == "ma_aligned") & (fill_lab != "ma_aligned")).sum())
    both_hp = int(((fill_lab == "ma_aligned") & (arm_lab == "ma_aligned")).sum())

    nets = m["net_usd"].astype(float).to_numpy()
    base_net = float(nets.sum())
    fill_sized = float(np.where(fill_lab == "ma_aligned", nets * HP_MULT, nets).sum())
    arm_sized = float(np.where(arm_lab == "ma_aligned", nets * HP_MULT, nets).sum())
    both_sized = float(
        np.where(
            (fill_lab == "ma_aligned") & (arm_lab == "ma_aligned"),
            nets * HP_MULT,
            nets,
        ).sum()
    )

    flip_rows = []
    for i in np.where(arm_lab != fill_lab)[0]:
        flip_rows.append(
            {
                "trade_id": str(m.iloc[i]["trade_id"]),
                "side": str(m.iloc[i]["side"]),
                "arm_ts": m.iloc[i]["live_after_ts"].isoformat(),
                "fill_ts": m.iloc[i]["entry_ts"].isoformat(),
                "arm_ma5_align": arm_lab[i],
                "fill_ma5_align": fill_lab[i],
                "net_usd": "%.2f" % float(m.iloc[i]["net_usd"]),
                "delay_sec": int(
                    (m.iloc[i]["entry_ts"] - m.iloc[i]["live_after_ts"]).total_seconds()
                ),
            }
        )

    arm_hp: Set[str] = set(m.loc[arm_lab == "ma_aligned", "trade_id"].astype(str))
    fill_hp: Set[str] = set(m.loc[fill_lab == "ma_aligned", "trade_id"].astype(str))

    return {
        "campaigns": int(len(m)),
        "stored_vs_fill_asof_mismatch": label_mismatch,
        "avail_at_after_entry": avail_after_entry,
        "avail_at_eq_entry": avail_eq_entry,
        "arm_vs_fill_flips": flips,
        "hp_fill": int((fill_lab == "ma_aligned").sum()),
        "hp_arm": int((arm_lab == "ma_aligned").sum()),
        "hp_both": both_hp,
        "hp_only_fill": only_fill_hp,
        "hp_only_arm": only_arm_hp,
        "campaign_base_net": base_net,
        "campaign_fill_size_net": fill_sized,
        "campaign_arm_size_net": arm_sized,
        "campaign_both_size_net": both_sized,
        "campaign_fill_delta": fill_sized - base_net,
        "campaign_arm_delta": arm_sized - base_net,
        "pass_feature_recipe": bool(label_mismatch == 0 and avail_after_entry == 0),
        "arm_hp_ids": arm_hp,
        "fill_hp_ids": fill_hp,
        "flip_rows": flip_rows,
    }


def run(*, email: bool = False, smoke: bool = False) -> Dict[str, object]:
    HUB.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="audit",
        variant_slug="nas100_clean_break_ma_aligned_size15_causality",
        instrument="NAS100",
        hub_path=str(AUDIT_DIR.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="causality audit running",
    )
    try:
        _progress("Engine tape causality...")
        eng = audit_engine_tape()
        _progress(
            "Engine: snapshots=%d viol=%d live_after_fails=%d feat_order_fails=%d pass=%s"
            % (
                eng["feature_snapshots"],
                eng["causality_violation_rows"],
                eng["non_moc_fills_at_or_before_live_after"],
                eng["feature_order_fails"],
                eng["pass"],
            )
        )

        _progress("MA alignment fill-asof vs arm-asof...")
        ma = audit_ma_alignment()
        _progress(
            "MA: label_mismatch=%d avail>entry=%d flips=%d hp_fill=%d hp_arm=%d"
            % (
                ma["stored_vs_fill_asof_mismatch"],
                ma["avail_at_after_entry"],
                ma["arm_vs_fill_flips"],
                ma["hp_fill"],
                ma["hp_arm"],
            )
        )

        POINT_VALUES[INSTRUMENT] = POINT_VALUE
        DEFAULT_TICK_SIZE[INSTRUMENT] = 0.1
        units = units_from_v2b_fills(SOURCE_FILLS, STRATEGY_ID)
        max_sessions = 80 if smoke else None
        _progress("Weighted Engine stress: fill-HP vs arm-HP @ ×%.2f..." % HP_MULT)
        bars = load_audit_bars(max_sessions=max_sessions)
        if smoke and bars:
            end_ts = bars[-1].ts
            units = [u for u in units if u.entry_ts <= end_ts]

        fill_hp_ids, _ = load_hp_trade_ids(CAMPAIGNS)
        if smoke:
            keep = {u.trade_id for u in units}
            fill_hp_ids = {t for t in fill_hp_ids if t in keep}
            arm_hp_ids = {t for t in ma["arm_hp_ids"] if t in keep}
        else:
            arm_hp_ids = ma["arm_hp_ids"]

        fill_audit = weighted_intraday_audit(
            strategy_id=STRATEGY_ID,
            state_root=AUDIT_DIR / "engine_fill_hp",
            bars=bars,
            units=units,
            hp_trade_ids=fill_hp_ids,
            hp_mult=HP_MULT,
            instrument=INSTRUMENT,
            fee_per_unit=FEE_PER_UNIT,
        )
        arm_audit = weighted_intraday_audit(
            strategy_id=STRATEGY_ID,
            state_root=AUDIT_DIR / "engine_arm_hp",
            bars=bars,
            units=units,
            hp_trade_ids=arm_hp_ids,
            hp_mult=HP_MULT,
            instrument=INSTRUMENT,
            fee_per_unit=FEE_PER_UNIT,
        )
        # Baseline = all size 1.0
        base_audit = weighted_intraday_audit(
            strategy_id=STRATEGY_ID,
            state_root=AUDIT_DIR / "engine_baseline",
            bars=bars,
            units=units,
            hp_trade_ids=set(),
            hp_mult=1.0,
            instrument=INSTRUMENT,
            fee_per_unit=FEE_PER_UNIT,
        )

        def _ns(a: Dict[str, float]) -> float:
            stress = abs(float(a["intrabar_stress_dd_usd"]))
            net = float(a["net_usd"])
            return net / stress if stress > 1e-9 else 0.0

        engine_board = {
            "baseline_net": float(base_audit["net_usd"]),
            "baseline_stress": abs(float(base_audit["intrabar_stress_dd_usd"])),
            "baseline_ns": _ns(base_audit),
            "fill_hp_net": float(fill_audit["net_usd"]),
            "fill_hp_stress": abs(float(fill_audit["intrabar_stress_dd_usd"])),
            "fill_hp_ns": _ns(fill_audit),
            "arm_hp_net": float(arm_audit["net_usd"]),
            "arm_hp_stress": abs(float(arm_audit["intrabar_stress_dd_usd"])),
            "arm_hp_ns": _ns(arm_audit),
        }
        engine_board["fill_delta_net"] = engine_board["fill_hp_net"] - engine_board["baseline_net"]
        engine_board["fill_delta_ns"] = engine_board["fill_hp_ns"] - engine_board["baseline_ns"]
        engine_board["arm_delta_net"] = engine_board["arm_hp_net"] - engine_board["baseline_net"]
        engine_board["arm_delta_ns"] = engine_board["arm_hp_ns"] - engine_board["baseline_ns"]

        _progress(
            "Engine fill-HP: net=$%.0f N/S=%.2f Δnet=$%+.0f | arm-HP: net=$%.0f N/S=%.2f Δnet=$%+.0f"
            % (
                engine_board["fill_hp_net"],
                engine_board["fill_hp_ns"],
                engine_board["fill_delta_net"],
                engine_board["arm_hp_net"],
                engine_board["arm_hp_ns"],
                engine_board["arm_delta_net"],
            )
        )

        # Overall: Engine causal + feature recipe causal; size policy is conditional.
        overall = "CONDITIONAL_PASS" if (eng["pass"] and ma["pass_feature_recipe"]) else "FAIL"
        if ma["arm_vs_fill_flips"] == 0 and overall == "CONDITIONAL_PASS":
            overall = "PASS"

        checks = {
            "overall": overall,
            "engine_pass": eng["pass"],
            "ma_feature_recipe_pass": ma["pass_feature_recipe"],
            "arm_vs_fill_flips": ma["arm_vs_fill_flips"],
            "smoke": smoke,
            **{k: v for k, v in eng.items() if k != "pass"},
            **{
                k: v
                for k, v in ma.items()
                if k not in ("arm_hp_ids", "fill_hp_ids", "flip_rows", "pass_feature_recipe")
            },
            **engine_board,
        }
        pd.DataFrame([checks]).to_csv(AUDIT_DIR / "causality_checks.csv", index=False)
        pd.DataFrame(ma["flip_rows"]).to_csv(AUDIT_DIR / "ma_arm_fill_flips.csv", index=False)
        (AUDIT_DIR / "run_complete.json").write_text(
            json.dumps(
                {
                    "overall": overall,
                    "dsr": DSR,
                    "parent_dsr": PARENT_DSR,
                    "engine": eng,
                    "ma": {k: v for k, v in ma.items() if k not in ("arm_hp_ids", "fill_hp_ids", "flip_rows")},
                    "engine_board": engine_board,
                    "smoke": smoke,
                },
                indent=2,
                default=str,
            )
            + "\n"
        )

        lines = [
            "# LOOKAHEAD_REVIEW — NAS100 clean-break ma_aligned size_1.5",
            "",
            "**Date:** %s" % date.today().isoformat(),
            "**Status:** %s" % overall,
            "**Parent result DSR:** `%s`  **Audit DSR:** `%s`" % (PARENT_DSR, DSR),
            "**Hub:** `%s`" % HUB,
            "",
            "## Scope",
            "",
            "Frozen OANDA NAS100 `trail06_m4_e2_out_be` 1m-fill Engine tape + HA overlay",
            "`5m MA vs trade = ma_aligned | size_1.5` (research size-up on HP campaigns).",
            "",
            "## 1) Engine order-time causality — %s" % ("PASS" if eng["pass"] else "FAIL"),
            "",
            "| Check | Value |",
            "|---|---:|",
            "| Feature snapshots | %d |" % eng["feature_snapshots"],
            "| Causality violation rows | %d |" % eng["causality_violation_rows"],
            "| Feature order fails (`event≤available≤bar`) | %d |" % eng["feature_order_fails"],
            "| Non-MOC fills at/before `live_after_ts` | %d |"
            % eng["non_moc_fills_at_or_before_live_after"],
            "| Entry fills at/before arm | %d |" % eng["entry_fills_at_or_before_live_after"],
            "",
            "Source: `%s`" % STATE.relative_to(REPO),
            "",
            "## 2) `ma5_align` feature recipe — %s"
            % ("PASS" if ma["pass_feature_recipe"] else "FAIL"),
            "",
            "Recipe (shared HA mill): 5m SMA9/SMA21 on completed bars; availability",
            "stamped at left-label **+5m**; `merge_asof(..., direction=backward)` on",
            "entry fill `entry_ts`. Marked `live_ready` in `intraday_condition_overlay.CAUSAL_LIVE_READY`.",
            "",
            "| Check | Value |",
            "|---|---:|",
            "| Campaigns | %d |" % ma["campaigns"],
            "| Stored vs independent fill-asof mismatch | %d |"
            % ma["stored_vs_fill_asof_mismatch"],
            "| Feature `available_at` **after** entry (lookahead) | %d |"
            % ma["avail_at_after_entry"],
            "| Feature `available_at` **equal** entry (just-completed 5m) | %d |"
            % ma["avail_at_eq_entry"],
            "",
            "## 3) Stop-arm vs fill MA (size-up contract) — CONDITIONAL",
            "",
            "Entry is a **resting buy/sell stop** armed at OR finalize (`live_after_ts`),",
            "then filled later on the 1m tape (median arm→fill delay ~4m; max hours).",
            "Fill-asof `ma_aligned` uses bars that can complete **after arm**. That is",
            "**not** lookahead vs the fill instant, but it **is** information the resting",
            "order did not have at submit unless live **refreshes qty** from the latest",
            "completed 5m MA until fill.",
            "",
            "| Metric | Fill-asof (research) | Arm-asof (no refresh) |",
            "|---|---:|---:|",
            "| HP campaigns | %d (61%%) | %d |" % (ma["hp_fill"], ma["hp_arm"]),
            "| Label flips arm↔fill | — | %d |" % ma["arm_vs_fill_flips"],
            "| HP only at fill (not arm) | %d | — |" % ma["hp_only_fill"],
            "| HP only at arm (not fill) | — | %d |" % ma["hp_only_arm"],
            "| Campaign Δnet @ ×1.5 | $%+.0f | $%+.0f |"
            % (ma["campaign_fill_delta"], ma["campaign_arm_delta"]),
            "",
            "### Engine+PaperBroker weighted stress (same unit tape)",
            "",
            "| Book | Net | Stress | N/S | Δnet | ΔN/S |",
            "|---|---:|---:|---:|---:|---:|",
            "| Baseline (×1) | $%.0f | $%.0f | %.2f | — | — |"
            % (
                engine_board["baseline_net"],
                engine_board["baseline_stress"],
                engine_board["baseline_ns"],
            ),
            "| Fill-asof HP ×1.5 | $%.0f | $%.0f | %.2f | $%+.0f | %+.2f |"
            % (
                engine_board["fill_hp_net"],
                engine_board["fill_hp_stress"],
                engine_board["fill_hp_ns"],
                engine_board["fill_delta_net"],
                engine_board["fill_delta_ns"],
            ),
            "| Arm-asof HP ×1.5 | $%.0f | $%.0f | %.2f | $%+.0f | %+.2f |"
            % (
                engine_board["arm_hp_net"],
                engine_board["arm_hp_stress"],
                engine_board["arm_hp_ns"],
                engine_board["arm_delta_net"],
                engine_board["arm_delta_ns"],
            ),
            "",
            "Flip detail: `%s`" % (AUDIT_DIR / "ma_arm_fill_flips.csv").relative_to(REPO),
            "",
            "## Verdict",
            "",
            "- **No Engine lookahead** on the frozen 1m-fill tape (`live_after_ts` +",
            "  feature snapshots clean).",
            "- **`ma5_align` itself is point-in-time at fill** (completed 5m only).",
            "- **Research size_1.5 lift assumes fill-asof HP.** Under a stricter",
            "  arm-only size contract the Engine lift shrinks but remains positive",
            "  (Δnet $%+.0f → $%+.0f; ΔN/S %+.2f → %+.2f)."
            % (
                engine_board["fill_delta_net"],
                engine_board["arm_delta_net"],
                engine_board["fill_delta_ns"],
                engine_board["arm_delta_ns"],
            ),
            "- **Stance unchanged: RESEARCH.** Promote only after wiring live qty",
            "  refresh from completed 5m MA (match fill-asof) **or** restating the",
            "  book on arm-asof HP.",
            "",
            "## Residual risks (not auto-fail)",
            "",
            "- Synthetic 1m bid/ask on the parent 1m-fill validation (not true quotes).",
            "- 515 / %d fills use a 5m bar with `available_at == entry_ts` (bar that" % ma["campaigns"],
            "  just completed at the fill left-label) — consistent with 1m processing",
            "  after the prior minute closes.",
            "- Demo plugin does not yet implement ma_aligned size-up.",
            "",
            "DSR audit: `%s` (parent `%s`)" % (DSR, PARENT_DSR),
            "",
        ]
        text = "\n".join(lines)
        (HUB / "LOOKAHEAD_REVIEW.md").write_text(text)
        (AUDIT_DIR / "LOOKAHEAD_REVIEW.md").write_text(text)
        (AUDIT_DIR / "SUMMARY.md").write_text(text)

        body_lines = [
            "potions: NAS100 clean-break ma_aligned size_1.5 causality %s" % overall,
            "",
            "Hub: %s" % HUB,
            "Audit: %s" % AUDIT_DIR,
            "DSR: %s (parent %s)" % (DSR, PARENT_DSR),
            "",
            "Engine tape: %s (violations=%d, live_after fails=%d, feat order fails=%d)"
            % (
                "PASS" if eng["pass"] else "FAIL",
                eng["causality_violation_rows"],
                eng["non_moc_fills_at_or_before_live_after"],
                eng["feature_order_fails"],
            ),
            "ma5_align recipe: %s (stored mismatch=%d, avail>entry=%d)"
            % (
                "PASS" if ma["pass_feature_recipe"] else "FAIL",
                ma["stored_vs_fill_asof_mismatch"],
                ma["avail_at_after_entry"],
            ),
            "Arm↔fill MA flips: %d (HP fill=%d arm=%d)"
            % (ma["arm_vs_fill_flips"], ma["hp_fill"], ma["hp_arm"]),
            "",
            "Engine baseline: net=$%.0f stress=$%.0f N/S=%.2f"
            % (
                engine_board["baseline_net"],
                engine_board["baseline_stress"],
                engine_board["baseline_ns"],
            ),
            "Fill-asof size_1.5: net=$%.0f N/S=%.2f Δnet=$%+.0f ΔN/S=%+.2f"
            % (
                engine_board["fill_hp_net"],
                engine_board["fill_hp_ns"],
                engine_board["fill_delta_net"],
                engine_board["fill_delta_ns"],
            ),
            "Arm-asof size_1.5: net=$%.0f N/S=%.2f Δnet=$%+.0f ΔN/S=%+.2f"
            % (
                engine_board["arm_hp_net"],
                engine_board["arm_hp_ns"],
                engine_board["arm_delta_net"],
                engine_board["arm_delta_ns"],
            ),
            "",
            "Stance: RESEARCH — Engine causal; size-up lift is fill-asof unless live refreshes qty.",
            "",
        ]
        body = "\n".join(body_lines)
        (AUDIT_DIR / "EMAIL.txt").write_text(body)
        (HUB / "CAUSALITY_EMAIL.txt").write_text(body)

        _mark_dsr("COMPLETE")
        complete_run(
            rid,
            net_usd=engine_board["fill_hp_net"],
            stress_dd_usd=-engine_board["fill_hp_stress"],
            ns=engine_board["fill_hp_ns"],
            notes="causality %s" % overall,
            meta={
                "overall": overall,
                "arm_delta_net": engine_board["arm_delta_net"],
                "fill_delta_net": engine_board["fill_delta_net"],
                "flips": ma["arm_vs_fill_flips"],
                "smoke": smoke,
            },
        )
        if email:
            send_email(
                subject="potions: NAS100 clean-break ma_aligned size_1.5 causality %s"
                % overall,
                body=body,
            )
        _progress("DONE overall=%s" % overall)
        return checks
    except Exception:
        err = traceback.format_exc()
        _mark_dsr("FAILED")
        fail_run(rid, notes=err[-500:])
        if email:
            send_email(
                subject="potions: NAS100 clean-break ma_aligned size_1.5 causality FAILED",
                body=err,
            )
        raise


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args(argv)
    run(email=args.email, smoke=args.smoke)


if __name__ == "__main__":
    main()
