#!/usr/bin/env python3
"""Enrich broker_run_ledger rows for OANDA-tick demo↔plugin parity hubs.

Idempotent: updates known run_ids with net/trades/replay window and corrected MATCH meta.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def _realized_pnl(state_root: Path) -> float:
    path = state_root / "positions.csv"
    if not path.exists() or path.stat().st_size == 0:
        return 0.0
    total = 0.0
    for row in csv.DictReader(path.open(encoding="utf-8")):
        try:
            total += float(row.get("realized_pnl") or 0.0)
        except ValueError:
            continue
    return total


def main() -> int:
    import sys

    sys.path.insert(0, str(REPO.parent))
    sys.path.insert(0, str(REPO / "v20-python" / "src"))
    from potions.live.run_ledger import complete_run  # noqa: WPS433

    updates = []

    # NAS100 full OANDA-tick parity (2026-08-31) — primary full-archive run
    nas_hub = REPO / "live" / "state" / "nas100_clean_break_demo_plugin_tick_parity_v1"
    nas_rc = json.loads((nas_hub / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    nas_pnl = _realized_pnl(nas_hub / "demo_tick")
    nas_demo = nas_rc.get("demo_meta") or {}
    updates.append(
        {
            "run_id": "brl_101f8ca4b5a1",
            "net_usd": nas_pnl,
            "trades": int(nas_demo.get("fills") or nas_rc.get("demo_vs_plugin", {}).get("a_n") or 0),
            "replay_start": str(nas_demo.get("first_5m") or ""),
            "replay_end": str(nas_demo.get("last_5m") or ""),
            "notes": "OANDA-tick demo↔plugin parity; research OHLC not used; backfill net/replay",
            "meta": {
                "verdict": nas_rc.get("verdict"),
                "match": bool((nas_rc.get("demo_vs_plugin") or {}).get("match")),
                "ticks": nas_demo.get("ticks"),
                "bars_5m": nas_demo.get("bars_5m"),
                "backfill": True,
                "skill": "potions-oanda-tick-demo-plugin-parity",
            },
        }
    )

    # USDJPY Monday+Asia full run (driver finished MISMATCH; hub later clarified MATCH)
    usd_hub = REPO / "live" / "state" / "usdjpy_live_demo_plugin_tick_parity_v1"
    usd_rc = json.loads((usd_hub / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    monday_pnl = float(((usd_rc.get("results") or [{}])[0].get("demo") or {}).get("realized_pnl") or 0.0)
    asia_pnl = 0.0
    for r in usd_rc.get("results") or []:
        if r.get("book") == "asia_range":
            asia_pnl = float((r.get("demo") or {}).get("realized_pnl") or 0.0)
    monday = next((r for r in (usd_rc.get("results") or []) if r.get("book") == "monday_or"), {})
    asia = next((r for r in (usd_rc.get("results") or []) if r.get("book") == "asia_range"), {})
    updates.append(
        {
            "run_id": "brl_30a2a67e1517",
            "net_usd": monday_pnl + asia_pnl,
            "trades": int((monday.get("demo") or {}).get("fills") or 0)
            + int((asia.get("demo") or {}).get("fills") or 0),
            "replay_start": str((monday.get("demo") or {}).get("first_bar") or ""),
            "replay_end": str((asia.get("demo") or {}).get("last_bar") or (monday.get("demo") or {}).get("last_bar") or ""),
            "notes": "OANDA-tick demo↔plugin parity; sorted fill-key MATCH (same-bar dd30/dd50 order); backfill",
            "meta": {
                "verdict": usd_rc.get("verdict"),
                "books": [r.get("book") for r in (usd_rc.get("results") or [])],
                "monday_match": bool((monday.get("demo_vs_plugin") or {}).get("match")),
                "asia_match": bool((asia.get("demo_vs_plugin") or {}).get("match")),
                "monday_sequence_match": (monday.get("demo_vs_plugin") or {}).get("sequence_match"),
                "monday_fills": (monday.get("demo") or {}).get("fills"),
                "asia_fills": (asia.get("demo") or {}).get("fills"),
                "backfill": True,
                "skill": "potions-oanda-tick-demo-plugin-parity",
            },
        }
    )

    for u in updates:
        ok = complete_run(
            u["run_id"],
            net_usd=u["net_usd"],
            trades=u["trades"],
            replay_start=u["replay_start"],
            replay_end=u["replay_end"],
            notes=u["notes"],
            meta=u["meta"],
            status="COMPLETE",
        )
        print(
            "%s run_id=%s net=%.4f trades=%s updated=%s"
            % (u["meta"].get("verdict"), u["run_id"], float(u["net_usd"]), u["trades"], ok)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
