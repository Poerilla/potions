"""Exit-mechanism attribution for S_1_1_3 + long-horizon runner books.

Distinguishes true 10R-target contribution from BE-protected EOD-survivor P&L
so reports do not mislabel EOD-held runners as a \"10R moonshot\".
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Map raw exit_reason → attribution bucket
BUCKET_MAP = {
    "tp1": "tp1",
    "tp2": "tp2",
    "wide_stop": "hard_stop",
    "stop": "hard_stop",
    "hard_stop": "hard_stop",
    "runner_stop": "break_even_stop",
    "be_stop": "break_even_stop",
    "break_even": "break_even_stop",
    "eod_close": "eod_mark",
    "eod": "eod_mark",
    "eod_mark": "eod_mark",
    "session_close": "eod_mark",
    "runner_tp": "true_10r_target",
    "target_10r": "true_10r_target",
    "tp_runner": "true_10r_target",
}

BUCKETS = (
    "tp1",
    "tp2",
    "hard_stop",
    "break_even_stop",
    "eod_mark",
    "true_10r_target",
    "other",
)

# If true 10R target P&L is below this fraction of total |or| of positive contrib,
# do not describe the book as a 10R moonshot.
TRUE_10R_MATERIAL_FRAC = 0.20


def attribute_unit_trades(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": False, "error": "missing_unit_trades", "path": str(path)}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return attribute_rows(rows, source=str(path))


def attribute_rows(
    rows: Sequence[dict], *, source: str = "", strategy_id: str = ""
) -> Dict[str, Any]:
    by_bucket: Dict[str, float] = {b: 0.0 for b in BUCKETS}
    counts: Dict[str, int] = {b: 0 for b in BUCKETS}
    true_10r_hits = 0
    trades = set()
    for r in rows:
        tid = r.get("trade_id") or ""
        if tid:
            trades.add(tid)
        reason = str(r.get("exit_reason") or "").strip().lower()
        bucket = BUCKET_MAP.get(reason, "other")
        pnl = float(r.get("net_usd") or 0.0)
        by_bucket[bucket] = by_bucket.get(bucket, 0.0) + pnl
        counts[bucket] = counts.get(bucket, 0) + 1
        if bucket == "true_10r_target":
            true_10r_hits += 1

    total_pnl = sum(by_bucket.values())
    n_units = len(rows)
    true_10r_pnl = by_bucket.get("true_10r_target", 0.0)
    eod_pnl = by_bucket.get("eod_mark", 0.0)
    be_pnl = by_bucket.get("break_even_stop", 0.0)

    # Materiality: share of total P&L (if total>0) or share of positive bucket sum.
    if total_pnl > 0:
        true_10r_share = true_10r_pnl / total_pnl
    else:
        pos = sum(v for v in by_bucket.values() if v > 0)
        true_10r_share = (true_10r_pnl / pos) if pos > 0 else 0.0

    eod_survivor_dominant = (eod_pnl + be_pnl) > max(true_10r_pnl, 0.0) and (
        true_10r_share < TRUE_10R_MATERIAL_FRAC
    )
    is_10r_moonshot = true_10r_share >= TRUE_10R_MATERIAL_FRAC and true_10r_hits > 0

    if is_10r_moonshot:
        book_label = "v2b S_1_1_3 + 1×10R runner"
    elif eod_survivor_dominant or (true_10r_hits == 0 and (eod_pnl or be_pnl)):
        book_label = (
            "v2b S_1_1_3 + 1 BE-protected long-horizon / EOD-survivor runner"
        )
    else:
        book_label = "v2b S_1_1_3 + long-horizon runner (mixed attribution)"

    return {
        "ok": True,
        "source": source,
        "strategy_id": strategy_id
        or (rows[0].get("candidate") if rows else ""),
        "trades": len(trades),
        "units": n_units,
        "total_net_usd": round(total_pnl, 2),
        "pnl_by_exit": {k: round(v, 2) for k, v in by_bucket.items()},
        "count_by_exit": dict(counts),
        "true_10r_target_hits": true_10r_hits,
        "true_10r_target_hit_pct": round(
            100.0 * true_10r_hits / n_units, 2
        )
        if n_units
        else 0.0,
        "true_10r_pnl_share": round(true_10r_share, 4),
        "is_10r_moonshot": bool(is_10r_moonshot),
        "eod_survivor_dominant": bool(eod_survivor_dominant),
        "book_label": book_label,
    }


def attribute_hub_unit_trades(hub: Path) -> List[Dict[str, Any]]:
    """Scan ``*/states/*/unit_trades.csv`` under a plus-1x10R hub."""
    out: List[Dict[str, Any]] = []
    for path in sorted(hub.glob("*/states/*/unit_trades.csv")):
        sid = path.parent.name
        row = attribute_unit_trades(path)
        row["market"] = path.parts[-4] if len(path.parts) >= 4 else ""
        row["strategy_id"] = sid
        out.append(row)
    return out


def candidate_status_gates(
    *,
    full_stack_reachable_stress: bool,
    lot_correct: bool,
    open_inventory_reported: bool,
    margin_reported: bool,
    exact_book_regime_overlap: bool,
    causality_violations: int,
    sufficient_sample: bool,
) -> Dict[str, Any]:
    """Gates required before promoting a long-horizon runner candidate."""
    fails = []
    if not full_stack_reachable_stress:
        fails.append("missing_full_stack_reachable_stress")
    if not lot_correct:
        fails.append("missing_lot_correct_accounting")
    if not open_inventory_reported:
        fails.append("missing_open_inventory_report")
    if not margin_reported:
        fails.append("missing_margin_or_notional_report")
    if not exact_book_regime_overlap:
        fails.append("missing_exact_book_regime_overlap")
    if causality_violations:
        fails.append("causality_violations=%d" % causality_violations)
    if not sufficient_sample:
        fails.append("insufficient_completed_trade_sample")
    return {
        "candidate_ready": not fails,
        "failed_gates": fails,
    }
