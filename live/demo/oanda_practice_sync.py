"""Query OANDA practice account and optionally repair local demo position CSVs.

Practice only. Does not place/cancel orders. Safe to run while demos are up for a
read-only snapshot; ``--repair-demo-positions`` rewrites each ``*_oanda`` demo's
``state/positions.csv`` to the live open qty for that demo's focus instrument
(clears stale multi-instrument contamination from account-wide bootstrap).

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    set -a && source live/demo/.env && set +a
    python3 -m potions.live.demo.oanda_practice_sync
    python3 -m potions.live.demo.oanda_practice_sync --repair-demo-positions
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..oanda import OandaApiClient, OandaBroker, OandaConfig
from ..store import FlatFileStore
from . import DEMO_ROOT

OANDA_TO_ROOT = {
    "EUR_USD": "EURUSD",
    "USD_JPY": "USDJPY",
    "GBP_USD": "GBPUSD",
    "AUD_JPY": "AUDJPY",
    "NAS100_USD": "NAS100",
    "SPX500_USD": "SPX500",
    "US30_USD": "US30",
    "XAU_USD": "XAUUSD",
    "XAG_USD": "XAGUSD",
}

DEMO_FOCUS = {
    "eurusd_v2b_ungated_oanda": "EURUSD",
    "nas100_v2b_ungated_oanda": "NAS100",
    "spx500_v2b_ungated_oanda": "SPX500",
    "us30_v2b_ungated_oanda": "US30",
    "usdjpy_monday_or_ungated_oanda": "USDJPY",
    "us30_hourly_st_pmc_sl50_tp150_3r_oanda": "US30",
    "nas100_hourly_st_pmc_sl50_tp150_3r_oanda": "NAS100",
    "us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda": "US30",
    "nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda": "NAS100",
}

POSITION_FIELDS = [
    "position_id",
    "strategy_id",
    "instrument",
    "account_mode",
    "quantity",
    "avg_price",
    "realized_pnl",
    "updated_at",
]


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "dict"):
        return dict(obj.dict())
    if isinstance(obj, dict):
        return dict(obj)
    return {"value": str(obj)}


def _root_instrument(name: str) -> str:
    name = str(name or "")
    return OANDA_TO_ROOT.get(name, name.replace("_", ""))


def fetch_account(config: OandaConfig) -> Tuple[Dict[str, Any], OandaBroker, Path]:
    snap_root = DEMO_ROOT / "oanda_practice_snapshot"
    snap_root.mkdir(parents=True, exist_ok=True)
    store = FlatFileStore(snap_root / "_broker_scratch")
    store.ensure()
    client = OandaApiClient(config=config, store=store)
    broker = OandaBroker(store, config=config, client=client, allow_live_routing=False)
    body = client.account_details()
    broker.reconcile_from_account_details(body)
    return body, broker, snap_root


def summarize(body: Dict[str, Any], broker: OandaBroker) -> Dict[str, Any]:
    account = _as_dict(body.get("account") or body)
    positions = []
    for p in broker.reconcile_positions():
        if float(getattr(p, "quantity", 0) or 0) == 0:
            continue
        positions.append(
            {
                "instrument": p.instrument,
                "quantity": float(p.quantity),
                "avg_price": float(p.avg_price) if p.avg_price is not None else None,
                "position_id": p.position_id,
                "strategy_id": p.strategy_id,
                "updated_at": p.updated_at,
            }
        )
    trades = []
    for t in account.get("trades") or []:
        t = _as_dict(t)
        trades.append(
            {
                "id": t.get("id"),
                "instrument": _root_instrument(str(t.get("instrument") or "")),
                "oanda_instrument": t.get("instrument"),
                "units": t.get("currentUnits") or t.get("initialUnits"),
                "price": t.get("price"),
                "unrealizedPL": t.get("unrealizedPL"),
                "has_sl": t.get("stopLossOrder") is not None,
                "has_tp": t.get("takeProfitOrder") is not None,
            }
        )
    orders = []
    for o in account.get("orders") or []:
        o = _as_dict(o)
        orders.append(
            {
                "id": o.get("id"),
                "type": o.get("type"),
                "instrument": _root_instrument(str(o.get("instrument") or "")),
                "oanda_instrument": o.get("instrument"),
                "units": o.get("units"),
                "state": o.get("state"),
                "price": o.get("price"),
                "stopLossOnFill": o.get("stopLossOnFill"),
                "takeProfitOnFill": o.get("takeProfitOnFill"),
            }
        )
    return {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "env": str(broker.config.env),
        "account_id": broker.config.account_id,
        "last_transaction_id": broker.last_transaction_id,
        "NAV": account.get("NAV"),
        "balance": account.get("balance"),
        "unrealizedPL": account.get("unrealizedPL"),
        "positions": positions,
        "trades": trades,
        "orders": orders,
    }


def local_open_positions(demo_dir: Path) -> Dict[str, float]:
    path = demo_dir / "state" / "positions.csv"
    out: Dict[str, float] = {}
    if not path.exists() or path.stat().st_size == 0:
        return out
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                qty = float(row.get("quantity") or 0)
            except ValueError:
                continue
            if qty == 0:
                continue
            inst = str(row.get("instrument") or "")
            out[inst] = out.get(inst, 0.0) + qty
    return out


def write_focus_positions(
    demo_dir: Path,
    *,
    focus: str,
    live_qty: Optional[float],
    live_avg: Optional[float],
    strategy_id: str,
) -> None:
    state = demo_dir / "state"
    state.mkdir(parents=True, exist_ok=True)
    path = state / "positions.csv"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: List[Dict[str, Any]] = []
    if live_qty is not None and float(live_qty) != 0:
        rows.append(
            {
                "position_id": "%s|%s|paper" % (strategy_id, focus),
                "strategy_id": strategy_id,
                "instrument": focus,
                "account_mode": "paper",
                "quantity": float(live_qty),
                "avg_price": live_avg if live_avg is not None else "",
                "realized_pnl": 0,
                "updated_at": now,
            }
        )
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=POSITION_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def compare_and_maybe_repair(*, repair: bool) -> int:
    config = OandaConfig.from_env()
    config.validate_for_network()
    if str(config.env).lower() != "practice":
        print("REFUSING non-practice OANDA_ENV=%s" % config.env)
        return 2

    body, broker, snap_root = fetch_account(config)
    summary = summarize(body, broker)
    (snap_root / "account_snapshot.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    live_by = {p["instrument"]: p for p in summary["positions"]}
    print(
        "OANDA practice %s  NAV=%s  unreal=%s  lastTx=%s"
        % (summary["account_id"], summary["NAV"], summary["unrealizedPL"], summary["last_transaction_id"])
    )
    print("LIVE positions:")
    if not summary["positions"]:
        print("  (flat)")
    for p in summary["positions"]:
        print("  %-8s qty=%+g avg=%s" % (p["instrument"], p["quantity"], p["avg_price"]))
    print("LIVE pending orders: %d" % len(summary["orders"]))
    for o in summary["orders"]:
        print(
            "  id=%s %-8s %-6s units=%s state=%s"
            % (o["id"], o["instrument"], o["type"], o["units"], o["state"])
        )

    lines = [
        "# OANDA practice sync",
        "",
        "Fetched: `%s`" % summary["fetched_at"],
        "Account: `%s` (%s)" % (summary["account_id"], summary["env"]),
        "NAV=%s balance=%s unreal=%s lastTx=%s"
        % (summary["NAV"], summary["balance"], summary["unrealizedPL"], summary["last_transaction_id"]),
        "",
        "## Live positions",
        "",
    ]
    if not summary["positions"]:
        lines.append("(flat)")
    else:
        lines.append("| Instrument | Qty | Avg |")
        lines.append("|---|---:|---:|")
        for p in summary["positions"]:
            lines.append("| %s | %+g | %s |" % (p["instrument"], p["quantity"], p["avg_price"]))
    lines.extend(["", "## Demo local vs live", "", "| Demo | Focus | Local | Live focus | Action |", "|---|---|---|---|---|"])

    print("\nDemo comparison:")
    for demo_name, focus in sorted(DEMO_FOCUS.items()):
        demo_dir = DEMO_ROOT / demo_name
        if not demo_dir.is_dir():
            continue
        local = local_open_positions(demo_dir)
        live_p = live_by.get(focus)
        live_qty = float(live_p["quantity"]) if live_p else None
        foreign = [k for k in local if k != focus]
        focus_local = local.get(focus)
        needs = False
        reason = "ok"
        if foreign:
            needs = True
            reason = "stale_foreign=%s" % ",".join(sorted(foreign))
        elif (focus_local or 0) != (live_qty or 0):
            # treat None and 0 as flat
            fl = focus_local or 0.0
            ll = live_qty or 0.0
            if fl != ll:
                needs = True
                reason = "qty_mismatch local=%s live=%s" % (focus_local, live_qty)

        action = "none"
        if repair and needs:
            write_focus_positions(
                demo_dir,
                focus=focus,
                live_qty=live_qty,
                live_avg=float(live_p["avg_price"]) if live_p and live_p.get("avg_price") is not None else None,
                strategy_id=demo_name,
            )
            action = "repaired_positions_csv"
        elif needs:
            action = "needs_repair"
        print(
            "  %s focus=%s local=%s live=%s -> %s (%s)"
            % (demo_name, focus, local, live_qty, action, reason)
        )
        lines.append(
            "| `%s` | %s | `%s` | %s | %s |"
            % (demo_name, focus, local, live_qty if live_qty is not None else "flat", action if action != "none" else reason)
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Shared practice account: open risk is account-wide; each demo CSV should only mirror its **focus** instrument.",
            "- Order CSVs are not rewritten here (daemon race). Compare LIVE pending orders above to each demo `state/orders.csv`.",
            "- Snapshot JSON: `live/demo/oanda_practice_snapshot/account_snapshot.json`",
            "",
        ]
    )
    report = snap_root / "REPORT.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nWrote %s" % report)
    print("Wrote %s" % (snap_root / "account_snapshot.json"))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair-demo-positions",
        action="store_true",
        help="Rewrite each *_oanda demo positions.csv to live focus-instrument qty only",
    )
    args = parser.parse_args(argv)
    return compare_and_maybe_repair(repair=bool(args.repair_demo_positions))


if __name__ == "__main__":
    raise SystemExit(main())
