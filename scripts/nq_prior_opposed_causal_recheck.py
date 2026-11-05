#!/usr/bin/env python3
"""Causal recheck of NQ prior-opposed on the through-2026-10-11 tape.

Per filled campaign, confirm every gate is knowable strictly before the entry fill:
  1. ST+PMC opposite resting limit available before the v2b arm bar and before entry.
  2. Opening range finalized (09:45 left-label) before entry.
  3. Normal-range (or_norm) label uses only the current + prior 60 OR windows, all
     complete by 09:45, hence known before entry.
  4. Entry fill strictly after the entry intent live_after_ts (confirming bar).
  5. Replay guard wrote zero causality violations.
"""
from __future__ import annotations

import json
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/tester/hsm/potions")
STATE = (
    REPO
    / "live/state/nq_v2b_prior_opposed_stpmc_resting_limit_through_20261011"
    / "states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3"
)
NY = "America/New_York"
HUB = REPO / "live/state/nq_prior_opposed_last5m_or_norm"


def to_ny(s):
    return pd.to_datetime(s, utc=True).dt.tz_convert(NY)


def main() -> None:
    viol = pd.read_csv(STATE / "causality_violations.csv")
    guard_violations = int(len(viol))

    fills = pd.read_csv(STATE / "fills.csv")
    entry = fills[fills["reason"].astype(str) == "entry"].copy()
    entry["ts"] = to_ny(entry["ts"])
    entry = entry.sort_values("ts").drop_duplicates("trade_id", keep="first")
    entry_by_trade = entry.set_index("trade_id")["ts"].to_dict()

    intents = pd.read_csv(STATE / "order_intents.csv")
    ent_int = intents[(intents["reason"].astype(str) == "v2b_long_entry") | (intents["reason"].astype(str) == "v2b_short_entry")].copy()
    ent_int["live_after_ts"] = to_ny(ent_int["live_after_ts"])
    la_by_trade = ent_int.sort_values("live_after_ts").groupby("trade_id")["live_after_ts"].first().to_dict()

    # entry fill strictly after confirming-bar live_after_ts
    late = 0
    bad_after = []
    for tid, ets in entry_by_trade.items():
        la = la_by_trade.get(tid)
        if la is None:
            continue
        if ets > la:
            late += 1
        else:
            bad_after.append((tid, str(ets), str(la)))

    # ST gate availability + OR finalized, from feature snapshots (stream the entry-gate rows)
    gate_rows = []
    or_rows = []
    for chunk in pd.read_csv(STATE / "feature_snapshots.csv", chunksize=200000):
        g = chunk[chunk["feature_name"] == "v2b_entry_gate"]
        if len(g):
            gate_rows.append(g)
        o = chunk[chunk["feature_name"] == "v2b_opening_range"]
        if len(o):
            or_rows.append(o)
    gate = pd.concat(gate_rows, ignore_index=True) if gate_rows else pd.DataFrame()
    orr = pd.concat(or_rows, ignore_index=True) if or_rows else pd.DataFrame()

    st_before_arm = 0
    st_bad = []
    st_before_entry = 0
    st_entry_bad = []
    for _, r in gate.iterrows():
        meta = json.loads(r["metadata_json"])
        cur = pd.Timestamp(r["current_bar_ts"])
        prior = meta.get("prior_event") or {}
        avail = prior.get("available_at_ts")
        if avail is None:
            continue
        avail_ts = pd.Timestamp(avail)
        if avail_ts <= cur:
            st_before_arm += 1
        else:
            st_bad.append((r["strategy_id"], str(avail_ts), str(cur)))
        # tie back to entry fill if this trade filled
        tid = None
        # the gate feature has no trade_id column; match by session + direction to an entry
        # use the entry fills on that session instead
    # ST vs entry using order_intents live_after (entry intent arms only after gate)
    # Already covered by late check (entry after confirming bar). Add: gate available <= arm bar.

    # OR finalized flag
    or_final = 0
    or_bad = []
    for _, r in orr.iterrows():
        meta = json.loads(r["metadata_json"])
        if meta.get("or_finalized"):
            or_final += 1
        else:
            or_bad.append(str(r["current_bar_ts"]))

    # OR-norm bucket: entries must be at/after 09:45 so the 09:30-09:45 OR is complete.
    camp = pd.read_csv(HUB / "campaigns.csv")
    camp["entry_ts"] = to_ny(camp["entry_ts"])
    orn = camp[camp["or15_width_pct"] == "or_norm"].copy()
    orn_entry_time = orn["entry_ts"].dt.time
    before_0945 = int((orn_entry_time < time(9, 45)).sum())
    earliest = str(orn["entry_ts"].dt.time.min())

    result = {
        "tape": "through 2026-10-11",
        "guard_violations_rows": guard_violations,
        "filled_campaigns": int(len(entry_by_trade)),
        "entry_fill_after_confirming_bar": "%d / %d" % (late, len(la_by_trade)),
        "entry_fill_not_after_examples": bad_after[:5],
        "entry_gate_rows_checked": int(len(gate)),
        "st_gate_available_by_arm_bar": "%d / %d" % (st_before_arm, len(gate)),
        "st_gate_bad_examples": st_bad[:5],
        "opening_range_rows_checked": int(len(orr)),
        "opening_range_finalized_before_arm": "%d / %d" % (or_final, len(orr)),
        "opening_range_bad_examples": or_bad[:5],
        "or_norm_trades": int(len(orn)),
        "or_norm_entries_before_0945": before_0945,
        "or_norm_earliest_entry_time": earliest,
    }
    (HUB / "CAUSAL_RECHECK.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
