"""Tiny OANDA practice EURUSD market place → Account Changes reconcile → flatten.

Run before enabling the four ungated OANDA demos overnight.
Practice only (`OANDA_ENV=practice`); never sets ``allow_live_routing``.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Optional

from ..models import Fill, OrderIntent, as_row
from ..oanda import OandaApiClient, OandaBroker, OandaConfig
from ..store import FlatFileStore


def _local_fills(store: FlatFileStore, *, broker_order_id: str, strategy_id: str) -> list:
    rows = store.read_table("fills")
    out = []
    for row in rows:
        if row.get("broker_order_id") == broker_order_id or row.get("strategy_id") == strategy_id:
            out.append(Fill.from_row(row))
    return out


def run_practice_order_smoke(
    *,
    oanda_config_path: str = "",
    units: int = 1,
    state_root: Optional[Path] = None,
) -> int:
    config = (
        OandaConfig.from_json_file(Path(oanda_config_path))
        if oanda_config_path
        else OandaConfig.from_env()
    )
    config.validate_for_network()
    if str(config.env).lower() != "practice":
        print("REFUSING non-practice OANDA_ENV=%s" % config.env)
        return 2

    tmp = None
    if state_root is None:
        tmp = tempfile.TemporaryDirectory(prefix="oanda_practice_smoke_")
        state_root = Path(tmp.name)
    store = FlatFileStore(state_root)
    store.ensure()
    client = OandaApiClient(config=config, store=store)
    broker = OandaBroker(store, config=config, client=client, allow_live_routing=False)

    print(
        "Practice order smoke: env=%s account=%s units=%d state=%s"
        % (config.env, config.account_id, units, state_root)
    )
    broker.reconcile_from_account_details()
    since = broker.last_transaction_id
    print("  reconciled lastTransactionID=%s" % since)

    intent = OrderIntent.create(
        strategy_id="practice_order_smoke",
        trade_id="practice_order_smoke_1",
        instrument="EURUSD",
        account_mode="paper",
        side="buy",
        order_type="market",
        quantity=max(1, int(units)),
        reason="smoke_entry",
        requires_verification=False,
        bracket_role="entry",
    )
    order = broker.submit_order_intent(intent)
    print("  submitted market buy broker_order_id=%s qty=%d" % (order.broker_order_id, order.quantity))

    # Immediate MARKET fills are mirrored from the create response into fills.csv.
    local_fills = _local_fills(store, broker_order_id=order.broker_order_id, strategy_id="practice_order_smoke")
    changes_fills = []
    for attempt in range(8):
        if local_fills:
            break
        time.sleep(0.5)
        body = client.account_changes(since_transaction_id=broker.last_transaction_id or since)
        changes_fills.extend(broker.apply_account_changes(body))
        local_fills = _local_fills(store, broker_order_id=order.broker_order_id, strategy_id="practice_order_smoke")
        if local_fills or changes_fills:
            break

    fills = local_fills or changes_fills
    if fills:
        for fill in fills:
            print(
                "  fill fill_id=%s side=%s qty=%s price=%s reason=%s"
                % (fill.fill_id, fill.side, fill.quantity, fill.price, fill.reason)
            )
            store.append_event("practice_smoke", {"event": "fill", **as_row(fill)})
    else:
        broker.reconcile_from_account_details()
        open_pos = [p for p in broker.reconcile_positions() if p.instrument == "EURUSD" and abs(p.quantity) != 0]
        if not open_pos:
            print("FAIL: no fill and no EURUSD position after market order")
            if tmp is not None:
                tmp.cleanup()
            return 1
        print("  WARN: no local fill mirrored; EURUSD position present — continuing to flatten")

    payloads = broker.go_flat(instruments=["EURUSD"])
    print("  flatten payloads=%d" % len(payloads))
    time.sleep(0.5)
    if broker.last_transaction_id:
        try:
            body = client.account_changes(since_transaction_id=broker.last_transaction_id)
            broker.apply_account_changes(body)
        except Exception:
            pass
    broker.reconcile_from_account_details()
    remaining = [
        p
        for p in broker.reconcile_positions()
        if p.instrument == "EURUSD" and p.strategy_id == "oanda" and abs(p.quantity) != 0
    ]
    if remaining:
        print("FAIL: EURUSD still open after flatten qty=%s" % remaining[0].quantity)
        if tmp is not None:
            tmp.cleanup()
        return 1

    store.append_event(
        "practice_smoke",
        {
            "event": "smoke_ok",
            "fills": len(fills),
            "last_transaction_id": broker.last_transaction_id,
            "account_id": config.account_id,
        },
    )
    print(
        "OANDA practice order smoke ok: fills=%d lastTransactionID=%s"
        % (len(fills), broker.last_transaction_id)
    )
    if tmp is not None:
        tmp.cleanup()
    return 0
