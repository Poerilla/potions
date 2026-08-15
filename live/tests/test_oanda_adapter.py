from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from potions.live.models import OrderIntent, Position, as_row
from potions.live.oanda import (
    OandaBroker,
    OandaConfig,
    OandaMarketDataFeedAdapter,
    OandaRoutingBlocked,
    format_oanda_price,
    oanda_order_type,
    parse_instrument_map,
    parse_oanda_ts,
)
from potions.live.store import FlatFileStore
from potions.live.supervisor import RuntimeSupervisor


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_parse_oanda_ts_accepts_nanosecond_rfc3339():
    dt = parse_oanda_ts("2026-07-22T01:22:15.703925140+00:00")
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 22
    assert dt.hour == 1
    assert dt.minute == 22
    assert dt.second == 15
    assert dt.microsecond == 703925
    assert parse_oanda_ts("2026-07-22T01:22:15.703925Z").microsecond == 703925


def test_oanda_config_parses_instrument_map_and_practice_defaults():
    assert parse_instrument_map("EURUSD=EUR_USD,XAUUSD=XAU_USD") == {
        "EURUSD": "EUR_USD",
        "XAUUSD": "XAU_USD",
    }
    assert parse_instrument_map('{"eurusd": "EUR_USD"}') == {"EURUSD": "EUR_USD"}
    config = OandaConfig.from_env(
        {
            "OANDA_ENV": "practice",
            "OANDA_TOKEN": "secret",
            "OANDA_ACCOUNT_ID": "101-002-39860312-001",
            "OANDA_INSTRUMENT_MAP": "EURUSD=EUR_USD,XAUUSD=XAU_USD",
        }
    )
    assert config.api_url == "https://api-fxpractice.oanda.com"
    assert config.stream_url == "https://stream-fxpractice.oanda.com"
    assert config.hostname() == "api-fxpractice.oanda.com"
    assert config.symbol_for("eurusd") == "EUR_USD"
    assert config.symbol_for("XAUUSD") == "XAU_USD"
    assert config.internal_for("EUR_USD") == "EURUSD"


def test_oanda_live_env_defaults_and_blocks_without_allow_flag():
    config = OandaConfig.from_env({"OANDA_ENV": "live", "OANDA_TOKEN": "t", "OANDA_ACCOUNT_ID": "1"})
    assert config.api_url == "https://api-fxtrade.oanda.com"
    tmp, store = make_store()
    try:
        with pytest.raises(Exception):
            OandaBroker(store, config=config, allow_live_routing=False)
    finally:
        tmp.cleanup()


def test_oanda_feed_resolves_instrument_and_persists_raw_events():
    tmp, store = make_store()
    try:
        adapter = OandaMarketDataFeedAdapter(store)
        adapter.on_raw_event(
            {
                "type": "instrument_resolution",
                "instrument": "EURUSD",
                "oanda_instrument": "EUR_USD",
                "event_ts": "2026-01-02T14:29:59Z",
            }
        )
        assert adapter.instrument_refs["EURUSD"].oanda_instrument == "EUR_USD"
        assert (Path(tmp.name) / "events" / "raw_market_data" / "oanda" / "2026-01-02.jsonl").exists()
        fresh = OandaMarketDataFeedAdapter(store)
        assert fresh.instrument_refs == {}
    finally:
        tmp.cleanup()


def test_oanda_feed_builds_completed_1m_and_derived_5m_from_prices():
    tmp, store = make_store()
    try:
        adapter = OandaMarketDataFeedAdapter(store)
        adapter.resolve_instrument("XAUUSD", "XAU_USD")
        emitted = []
        for i in range(6):
            emitted.extend(
                adapter.on_raw_event(
                    {
                        "type": "price",
                        "instrument": "XAUUSD",
                        "price": 2400.0 + i,
                        "quantity": 1,
                        "event_ts": "2026-01-02T14:%02d:05Z" % (30 + i),
                    }
                )
            )
        emitted.extend(adapter.flush())
        one_minute = store.read_bars("XAUUSD", "1m")
        five_minute = store.read_bars("XAUUSD", "5m")
        assert len(one_minute) == 6
        assert len(five_minute) == 1
        assert five_minute[0].open == 2400.0
        assert five_minute[0].high == 2404.0
        assert five_minute[0].close == 2404.0
        assert any(bar.timeframe == "5m" for bar in emitted)
    finally:
        tmp.cleanup()


def test_oanda_feed_blocks_delayed_data():
    tmp, store = make_store()
    try:
        adapter = OandaMarketDataFeedAdapter(store)
        adapter.resolve_instrument("EURUSD")
        adapter.on_raw_event({"type": "market_data_status", "instrument": "EURUSD", "status": "delayed"})
        assert adapter.is_blocking_entries()
        assert adapter.blocking_reason() == "delayed"
        status = json.loads((Path(tmp.name) / "market_data_status.json").read_text(encoding="utf-8"))
        assert status["provider"] == "oanda"
        assert status["status"] == "blocked"
    finally:
        tmp.cleanup()


def test_oanda_broker_maps_market_order_with_brackets_and_reconciles_fill():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"EURUSD": "EUR_USD"})
        broker = OandaBroker(store, config=config)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="EURUSD",
            account_mode="paper",
            side="buy",
            order_type="market",
            quantity=1000,
            bracket_stop_price=1.0800,
            bracket_target_price=1.1000,
            requires_verification=False,
            bracket_role="entry",
        )
        order = broker.submit_order_intent(intent)
        payload = broker.order_intent_to_oanda_order(intent, order)
        assert payload["type"] == "MARKET"
        assert payload["timeInForce"] == "FOK"
        assert payload["instrument"] == "EUR_USD"
        assert payload["units"] == "1000"
        assert payload["stopLossOnFill"]["price"] == format_oanda_price(1.0800, 5)
        assert payload["takeProfitOnFill"]["price"] == format_oanda_price(1.1000, 5)
        assert payload["clientExtensions"]["id"] == order.broker_order_id
        assert payload["timeInForce"] == "FOK"

        fill = broker.on_fill(
            {
                "broker_order_id": order.broker_order_id,
                "quantity": 1000,
                "price": 1.0900,
                "event_ts": "2026-01-02T15:00:00Z",
            }
        )
        assert fill.price == 1.0900
        positions = broker.reconcile_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 1000
        assert positions[0].instrument == "EURUSD"
    finally:
        tmp.cleanup()


def test_oanda_broker_blocks_live_routing_without_flag():
    tmp, store = make_store()
    try:
        config = OandaConfig(env="practice", account_id="101-002-39860312-001")
        broker = OandaBroker(store, config=config, allow_live_routing=False)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="EURUSD",
            account_mode="live",
            side="buy",
            order_type="market",
            quantity=1,
            requires_verification=False,
        )
        with pytest.raises(OandaRoutingBlocked):
            broker.submit_order_intent(intent)
    finally:
        tmp.cleanup()


def test_oanda_go_flat_cancels_and_emits_close_payloads():
    tmp, store = make_store()
    try:
        supervisor = RuntimeSupervisor(store, provider="oanda")
        config = OandaConfig(account_id="101-002-39860312-001")
        broker = OandaBroker(store, config=config, supervisor=supervisor)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="XAUUSD",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=10,
            limit_price=2400.0,
            requires_verification=False,
        )
        broker.submit_order_intent(intent)
        payloads = broker.go_flat(instruments=["XAUUSD"])
        assert len(payloads) == 1
        assert payloads[0]["instrument"] == "XAU_USD"
        assert broker.reconcile_orders() == []
    finally:
        tmp.cleanup()


def test_oanda_order_type_maps_market_close_to_market():
    assert oanda_order_type("market_close") == "MARKET"
    assert oanda_order_type("market") == "MARKET"


def test_apply_account_changes_returns_fills_and_writes_fills_csv():
    tmp, store = make_store()
    try:
        config = OandaConfig(env="practice", account_id="101-002-39860312-001")
        broker = OandaBroker(store, config=config, allow_live_routing=False)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="EURUSD",
            account_mode="paper",
            side="buy",
            order_type="market",
            quantity=3,
            reason="entry",
            bracket_role="entry",
            requires_verification=False,
        )
        order = broker.submit_order_intent(intent)
        fills = broker.apply_account_changes(
            {
                "lastTransactionID": "42",
                "changes": {
                    "transactions": [
                        {
                            "type": "ORDER_FILL",
                            "id": "tx-1",
                            "broker_order_id": order.broker_order_id,
                            "units": "3",
                            "price": "1.1000",
                            "time": "2026-07-23T14:00:00.000000000Z",
                        }
                    ]
                },
            }
        )
        assert len(fills) == 1
        assert fills[0].quantity == 3
        assert fills[0].price == 1.1
        assert fills[0].reason == "entry"
        assert broker.last_transaction_id == "42"
        assert (Path(tmp.name) / "fills.csv").exists()
    finally:
        tmp.cleanup()


class _FakeOandaClient:
    def __init__(self, pending=None):
        self.pending = list(pending or [])
        self.cancelled = []
        self.created = []
        self.replaced = []
        self._next_id = 1000

    def account_details(self):
        return {
            "lastTransactionID": "99",
            "account": {
                "lastTransactionID": "99",
                "orders": list(self.pending),
                "positions": [],
            },
        }

    def cancel_order(self, order_id, account_id=None):
        self.cancelled.append(str(order_id))
        self.pending = [o for o in self.pending if str(o.get("id")) != str(order_id)]
        return {"orderCancelTransaction": {"id": str(order_id), "orderID": str(order_id)}}

    def create_order(self, order_body, account_id=None):
        self._next_id += 1
        rid = str(self._next_id)
        self.created.append({"id": rid, "order": order_body})
        ext = (order_body or {}).get("clientExtensions") or {}
        self.pending.append(
            {
                "id": rid,
                "type": order_body.get("type") or "LIMIT",
                "state": "PENDING",
                "instrument": order_body.get("instrument"),
                "units": order_body.get("units"),
                "price": order_body.get("price"),
                "clientExtensions": ext,
            }
        )
        return {"orderCreateTransaction": {"id": rid}, "lastTransactionID": rid}

    def replace_order(self, order_id, order_body, account_id=None):
        self.replaced.append(str(order_id))
        self._next_id += 1
        rid = str(self._next_id)
        self.pending = [o for o in self.pending if str(o.get("id")) != str(order_id)]
        ext = (order_body or {}).get("clientExtensions") or {}
        self.pending.append(
            {
                "id": rid,
                "type": order_body.get("type") or "LIMIT",
                "state": "PENDING",
                "instrument": order_body.get("instrument"),
                "clientExtensions": ext,
            }
        )
        return {"orderCreateTransaction": {"id": rid}, "orderCancelTransaction": {"orderID": str(order_id)}}


def test_oanda_orphan_sweep_cancels_remote_not_in_local_active():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        client = _FakeOandaClient(
            pending=[
                {
                    "id": "817",
                    "type": "LIMIT",
                    "state": "PENDING",
                    "instrument": "NAS100_USD",
                    "clientExtensions": {
                        "id": "ord_zombie",
                        "tag": "nas100_hourly_st_pmc_sl50_tp150_3r_oanda",
                    },
                },
                {
                    "id": "1237",
                    "type": "TAKE_PROFIT",
                    "state": "PENDING",
                    "tradeID": "1236",
                    "clientExtensions": {},
                },
                {
                    "id": "900",
                    "type": "LIMIT",
                    "state": "PENDING",
                    "instrument": "NAS100_USD",
                    "clientExtensions": {
                        "id": "ord_other",
                        "tag": "other_strategy",
                    },
                },
            ]
        )
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            authority_strategy_ids=["nas100_hourly_st_pmc_sl50_tp150_3r_oanda"],
        )
        sweep = broker.sweep_remote_order_authority(cancel_orphans=True, reason="unit_test", force_fetch=True)
        assert sweep["orphans_cancelled"] == 1
        assert "817" in client.cancelled
        assert "1237" not in client.cancelled  # protective
        assert "900" not in client.cancelled  # other strategy
        assert all(str(o.get("id")) != "817" for o in client.pending)
    finally:
        tmp.cleanup()


def test_oanda_modify_refresh_entry_cancel_resubmits_and_drops_old_remote_id():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"US30": "US30_USD"})
        client = _FakeOandaClient()
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            authority_strategy_ids=["us30_st"],
        )
        intent = OrderIntent.create(
            strategy_id="us30_st",
            trade_id="t1",
            instrument="US30",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=50000.0,
            reason="entry",
            requires_verification=False,
            bracket_role="entry",
            bracket_stop_price=49900.0,
            bracket_target_price=50300.0,
        )
        order = broker.submit_order_intent(intent)
        old_remote = broker._oanda_order_ids[order.broker_order_id]
        assert old_remote
        updated = broker.modify_order(
            order.broker_order_id,
            limit_price=50100.0,
            reason="refresh_entry",
            bracket_stop_price=50000.0,
            bracket_target_price=50400.0,
        )
        assert updated.limit_price == 50100.0
        assert old_remote in client.cancelled
        assert client.replaced == []
        new_remote = broker._oanda_order_ids[order.broker_order_id]
        assert new_remote
        assert new_remote != old_remote
        assert old_remote not in broker._oanda_order_ids.values()
        events = (Path(tmp.name) / "events" / "oanda_order_events.jsonl").read_text(encoding="utf-8")
        assert "cancel_before_resubmit" in events or "cancel_resubmit" in events
    finally:
        tmp.cleanup()


def test_oanda_cancel_resolves_remote_id_from_pending_snapshot():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        intent = OrderIntent.create(
            strategy_id="nas100_st",
            trade_id="t1",
            instrument="NAS100",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=28000.0,
            reason="entry",
            requires_verification=False,
        )
        # Offline submit first (no client) so local open exists without remote map.
        broker = OandaBroker(store, config=config, client=None, authority_strategy_ids=["nas100_st"])
        order = broker.submit_order_intent(intent)
        assert order.broker_order_id not in broker._oanda_order_ids or not broker._oanda_order_ids.get(order.broker_order_id)

        client = _FakeOandaClient(
            pending=[
                {
                    "id": "555",
                    "type": "LIMIT",
                    "state": "PENDING",
                    "instrument": "NAS100_USD",
                    "clientExtensions": {"id": order.broker_order_id, "tag": "nas100_st"},
                }
            ]
        )
        broker.client = client
        broker._ingest_remote_pending_orders(client.pending)
        broker.cancel_order(order.broker_order_id, reason="regime_off")
        assert "555" in client.cancelled
        assert broker.reconcile_orders() == []
    finally:
        tmp.cleanup()


def test_oanda_reconcile_does_not_resurrect_cancelled_local_orders():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        client = _FakeOandaClient()
        broker = OandaBroker(store, config=config, client=client, authority_strategy_ids=["nas100_st"])
        intent = OrderIntent.create(
            strategy_id="nas100_st",
            trade_id="t1",
            instrument="NAS100",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=28000.0,
            reason="entry",
            requires_verification=False,
        )
        order = broker.submit_order_intent(intent)
        remote_id = broker._oanda_order_ids[order.broker_order_id]
        broker.cancel_order(order.broker_order_id, reason="regime_off")
        # Remote ghost still pending (simulate cancel never reaching OANDA previously).
        client.pending = [
            {
                "id": remote_id,
                "type": "LIMIT",
                "state": "PENDING",
                "instrument": "NAS100_USD",
                "clientExtensions": {"id": order.broker_order_id, "tag": "nas100_st"},
            }
        ]
        client.cancelled = []
        sweep = broker.reconcile_from_account_details()
        assert broker.reconcile_orders() == []
        assert order.broker_order_id not in broker._active_order_ids
        assert broker._orders_cache[order.broker_order_id].status == "cancelled"
        # Orphan sweep should cancel the remote ghost.
        assert remote_id in client.cancelled
    finally:
        tmp.cleanup()


def test_oanda_on_fill_rejects_untagged_instrument_fallback():
    """Shared-account sibling fills must not attach to an active order by instrument."""
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"US30": "US30_USD"})
        broker = OandaBroker(store, config=config)
        intent = OrderIntent.create(
            strategy_id="us30_v2b_ungated_oanda",
            trade_id="t_runner",
            instrument="US30",
            account_mode="paper",
            side="buy",
            order_type="stop",
            quantity=2,
            stop_price=54009.05,
            reason="runner_stop",
            requires_verification=False,
            reduce_only=True,
            bracket_role="runner_stop",
        )
        order = broker.submit_order_intent(intent)
        assert order.broker_order_id in broker._active_order_ids
        with pytest.raises(KeyError):
            broker.on_fill(
                {
                    "instrument": "US30_USD",
                    "units": "1.0",
                    "price": 53783.8,
                    "time": "2026-08-11T19:56:47.655745093Z",
                    "type": "ORDER_FILL",
                    "id": "1226",
                }
            )
        assert broker._orders_cache[order.broker_order_id].status != "filled"
        assert order.broker_order_id in broker._active_order_ids
        fills = store.read_table("fills")
        assert fills == []
    finally:
        tmp.cleanup()


def test_oanda_on_fill_resolves_via_remote_order_id_map():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"US30": "US30_USD"})
        broker = OandaBroker(store, config=config)
        intent = OrderIntent.create(
            strategy_id="us30_v2b",
            trade_id="t1",
            instrument="US30",
            account_mode="paper",
            side="buy",
            order_type="stop",
            quantity=2,
            stop_price=54009.05,
            reason="runner_stop",
            requires_verification=False,
            reduce_only=True,
            bracket_role="runner_stop",
        )
        order = broker.submit_order_intent(intent)
        broker._oanda_order_ids[order.broker_order_id] = "1255"
        fill = broker.on_fill(
            {
                "orderID": "1255",
                "units": "2.0",
                "price": 54071.5,
                "time": "2026-08-12T12:30:01Z",
                "id": "1256",
            }
        )
        assert fill.broker_order_id == order.broker_order_id
        assert fill.price == 54071.5
        assert broker._orders_cache[order.broker_order_id].status == "filled"
    finally:
        tmp.cleanup()


def test_oanda_on_fill_ignores_terminal_local_order():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"US30": "US30_USD"})
        broker = OandaBroker(store, config=config)
        intent = OrderIntent.create(
            strategy_id="us30_v2b",
            trade_id="t1",
            instrument="US30",
            account_mode="paper",
            side="buy",
            order_type="stop",
            quantity=2,
            stop_price=54009.05,
            reason="runner_stop",
            requires_verification=False,
            reduce_only=True,
            bracket_role="runner_stop",
        )
        order = broker.submit_order_intent(intent)
        broker.on_fill(
            {
                "broker_order_id": order.broker_order_id,
                "quantity": 2,
                "price": 54009.05,
                "event_ts": "2026-08-11T19:56:49Z",
            }
        )
        assert broker._orders_cache[order.broker_order_id].status == "filled"
        with pytest.raises(KeyError):
            broker.on_fill(
                {
                    "broker_order_id": order.broker_order_id,
                    "orderID": "999",
                    "units": "2.0",
                    "price": 54071.5,
                    "id": "1256",
                }
            )
        fills = store.read_table("fills")
        assert len(fills) == 1
        assert float(fills[0]["price"]) == 54009.05
    finally:
        tmp.cleanup()


def test_oanda_reconcile_positions_respects_instrument_scope():
    """Shared-account NAS100/SPX must not bleed into a US30-scoped demo store."""
    tmp, store = make_store()
    try:
        # Stale foreign row from a prior account-wide upsert.
        store.write_table(
            "positions",
            [
                {
                    "position_id": "oanda|NAS100|paper",
                    "strategy_id": "oanda",
                    "instrument": "NAS100",
                    "account_mode": "paper",
                    "quantity": 3,
                    "avg_price": 29967.6,
                    "realized_pnl": 0,
                    "updated_at": "2026-08-13T17:00:00Z",
                },
                {
                    "position_id": "ghost|US30|paper",
                    "strategy_id": "us30_hourly_st_pmc_sl50_tp150_3r_oanda",
                    "instrument": "US30",
                    "account_mode": "paper",
                    "quantity": 2,
                    "avg_price": 53779.3,
                    "realized_pnl": 0,
                    "updated_at": "2026-08-12T22:27:48Z",
                },
            ],
        )
        config = OandaConfig(
            account_id="101-002-39860312-001",
            instrument_map={"US30": "US30_USD", "NAS100": "NAS100_USD", "SPX500": "SPX500_USD"},
        )

        class _Client(_FakeOandaClient):
            def account_details(self):
                return {
                    "lastTransactionID": "1372",
                    "account": {
                        "lastTransactionID": "1372",
                        "orders": [],
                        "positions": [
                            {
                                "instrument": "NAS100_USD",
                                "long": {"units": "3.0", "averagePrice": "29967.6"},
                                "short": {"units": "0"},
                            },
                            {
                                "instrument": "SPX500_USD",
                                "long": {"units": "3.0", "averagePrice": "7792.8"},
                                "short": {"units": "0"},
                            },
                        ],
                    },
                }

        broker = OandaBroker(
            store,
            config=config,
            client=_Client(),
            position_scope_instruments=["US30"],
        )
        # Scoped init drops foreign NAS100 from cache even before reconcile.
        assert all(p.instrument == "US30" for p in broker.reconcile_positions())
        broker.reconcile_from_account_details()
        # Account is flat US30 → local store must be flat (ghost cleared, no NAS/SPX bleed).
        assert broker.reconcile_positions() == []
        assert store.read_table("positions") == []
    finally:
        tmp.cleanup()


def test_oanda_reconcile_skips_sibling_same_instrument_inventory():
    """NAS100+3 owned by v2b must not appear in ST+PMC 3r scoped store."""
    tmp, store = make_store()
    try:
        config = OandaConfig(
            env="practice",
            account_id="101-002-39860312-001",
            instrument_map={"NAS100": "NAS100_USD"},
        )
        strategy_id = "nas100_hourly_st_pmc_sl50_tp150_3r_oanda"
        store.write_table(
            "positions",
            [
                {
                    "position_id": "%s|NAS100|paper" % strategy_id,
                    "strategy_id": strategy_id,
                    "instrument": "NAS100",
                    "account_mode": "paper",
                    "quantity": 3,
                    "avg_price": 29967.6,
                    "realized_pnl": 0,
                    "updated_at": "2026-08-13T17:50:00Z",
                }
            ],
        )

        class _Client(_FakeOandaClient):
            def account_details(self):
                return {
                    "lastTransactionID": "1332",
                    "account": {
                        "lastTransactionID": "1332",
                        "orders": [],
                        "trades": [
                            {
                                "id": "1331",
                                "instrument": "NAS100_USD",
                                "currentUnits": "3.0",
                                "price": "29967.6",
                            }
                        ],
                        "positions": [
                            {
                                "instrument": "NAS100_USD",
                                "long": {"units": "3.0", "averagePrice": "29967.6"},
                                "short": {"units": "0"},
                            }
                        ],
                    },
                }

        class _Tx:
            def get(self, account_id, tx_id):
                class _Resp:
                    body = {}

                if str(tx_id) == "1331":
                    _Resp.body = {
                        "transaction": {
                            "id": "1331",
                            "type": "ORDER_FILL",
                            "orderID": "1327",
                            "instrument": "NAS100_USD",
                            "units": "3.0",
                            "price": "29967.6",
                        }
                    }
                elif str(tx_id) == "1327":
                    _Resp.body = {
                        "transaction": {
                            "id": "1327",
                            "type": "STOP_ORDER",
                            "instrument": "NAS100_USD",
                            "units": "3.0",
                            "clientExtensions": {
                                "id": "ord_33abbb3f212a",
                                "tag": "nas100_v2b_ungated_oanda",
                            },
                        }
                    }
                return _Resp()

        client = _Client()
        client.ctx = type("Ctx", (), {"transaction": _Tx()})()
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            authority_strategy_ids=[strategy_id],
            position_scope_instruments=["NAS100"],
        )
        broker.reconcile_from_account_details()
        assert broker.reconcile_positions() == []
        assert store.read_table("positions") == []
    finally:
        tmp.cleanup()


def test_oanda_reconcile_keeps_authority_owned_inventory():
    tmp, store = make_store()
    try:
        config = OandaConfig(
            env="practice",
            account_id="101-002-39860312-001",
            instrument_map={"NAS100": "NAS100_USD"},
        )
        strategy_id = "nas100_v2b_ungated_oanda"

        class _Client(_FakeOandaClient):
            def account_details(self):
                return {
                    "lastTransactionID": "1332",
                    "account": {
                        "lastTransactionID": "1332",
                        "orders": [],
                        "trades": [
                            {
                                "id": "1331",
                                "instrument": "NAS100_USD",
                                "currentUnits": "3.0",
                                "price": "29967.6",
                            }
                        ],
                        "positions": [
                            {
                                "instrument": "NAS100_USD",
                                "long": {"units": "3.0", "averagePrice": "29967.6"},
                                "short": {"units": "0"},
                            }
                        ],
                    },
                }

        class _Tx:
            def get(self, account_id, tx_id):
                class _Resp:
                    body = {}

                if str(tx_id) == "1331":
                    _Resp.body = {
                        "transaction": {
                            "id": "1331",
                            "type": "ORDER_FILL",
                            "orderID": "1327",
                        }
                    }
                elif str(tx_id) == "1327":
                    _Resp.body = {
                        "transaction": {
                            "id": "1327",
                            "type": "STOP_ORDER",
                            "clientExtensions": {"tag": strategy_id},
                        }
                    }
                return _Resp()

        client = _Client()
        client.ctx = type("Ctx", (), {"transaction": _Tx()})()
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            authority_strategy_ids=[strategy_id],
            position_scope_instruments=["NAS100"],
        )
        broker.reconcile_from_account_details()
        pos = broker.reconcile_positions()
        assert len(pos) == 1
        assert pos[0].strategy_id == strategy_id
        assert float(pos[0].quantity) == 3.0
        assert float(pos[0].avg_price) == 29967.6
    finally:
        tmp.cleanup()


def test_apply_account_changes_does_not_import_sibling_open_qty_when_authority_set():
    tmp, store = make_store()
    try:
        config = OandaConfig(
            env="practice",
            account_id="101-002-39860312-001",
            instrument_map={"NAS100": "NAS100_USD"},
        )
        strategy_id = "nas100_hourly_st_pmc_sl50_tp150_3r_oanda"
        broker = OandaBroker(
            store,
            config=config,
            authority_strategy_ids=[strategy_id],
            position_scope_instruments=["NAS100"],
        )
        broker.apply_account_changes(
            {
                "lastTransactionID": "1331",
                "changes": {
                    "transactions": [],
                    "positions": [
                        {
                            "instrument": "NAS100_USD",
                            "long": {"units": "3.0", "averagePrice": "29967.6"},
                            "short": {"units": "0"},
                        }
                    ],
                },
            }
        )
        assert broker.reconcile_positions() == []
        assert store.read_table("positions") == []
    finally:
        tmp.cleanup()


def test_apply_account_changes_clears_scoped_position_ghost_on_broker_flat():
    """stopLossOnFill exits may not match a local order; changes.positions must clear ghosts."""
    tmp, store = make_store()
    try:
        config = OandaConfig(
            env="practice",
            account_id="101-002-39860312-001",
            instrument_map={"US30": "US30_USD"},
        )
        broker = OandaBroker(store, config=config, position_scope_instruments=["US30"])
        ghost = Position(
            position_id="us30_hourly_st_pmc_sl50_tp150_3r_oanda|US30|paper",
            strategy_id="us30_hourly_st_pmc_sl50_tp150_3r_oanda",
            instrument="US30",
            account_mode="paper",
            quantity=2.0,
            avg_price=53800.0,
            realized_pnl=0.0,
            updated_at="2026-08-12T22:00:00Z",
        )
        broker._positions_cache[ghost.position_id] = ghost
        store.write_table("positions", [as_row(ghost)])
        assert len(broker.reconcile_positions()) == 1

        broker.apply_account_changes(
            {
                "lastTransactionID": "1371",
                "changes": {
                    "transactions": [
                        {
                            "type": "ORDER_FILL",
                            "id": "1371",
                            "orderID": "1366",
                            "instrument": "US30_USD",
                            "units": "-1.0",
                            "price": "53646.0",
                            "reason": "STOP_LOSS_ORDER",
                            "time": "2026-08-13T15:28:43.082057123Z",
                        }
                    ],
                    "positions": [
                        {
                            "instrument": "US30_USD",
                            "pl": "-100.0",
                            "long": {"units": "0.0", "averagePrice": "0"},
                            "short": {"units": "0.0"},
                        }
                    ],
                },
            }
        )
        assert broker.reconcile_positions() == []
        assert store.read_table("positions") == []
        assert broker.last_transaction_id == "1371"
    finally:
        tmp.cleanup()


def test_apply_account_changes_refreshes_owned_positions_when_trades_closed_omit_positions():
    """Account Changes often omit positions; tradesClosed + local ghost must re-pull owned qty."""
    tmp, store = make_store()
    try:
        config = OandaConfig(
            env="practice",
            account_id="101-002-39860312-001",
            instrument_map={"US30": "US30_USD"},
        )
        strategy_id = "us30_hourly_st_pmc_sl50_tp150_3r_oanda"
        ghost = Position(
            position_id="%s|US30|paper" % strategy_id,
            strategy_id=strategy_id,
            instrument="US30",
            account_mode="paper",
            quantity=2.0,
            avg_price=53800.0,
            realized_pnl=0.0,
            updated_at="2026-08-13T01:00:00Z",
        )
        store.write_table("positions", [as_row(ghost)])

        class _Client(_FakeOandaClient):
            def account_details(self):
                return {
                    "lastTransactionID": "1298",
                    "account": {
                        "lastTransactionID": "1298",
                        "orders": [],
                        "trades": [],
                        "positions": [
                            {
                                "instrument": "US30_USD",
                                "long": {"units": "0.0", "averagePrice": "0"},
                                "short": {"units": "0.0"},
                            }
                        ],
                    },
                }

        broker = OandaBroker(
            store,
            config=config,
            client=_Client(),
            authority_strategy_ids=[strategy_id],
            position_scope_instruments=["US30"],
        )
        assert len(broker.reconcile_positions()) == 1

        broker.apply_account_changes(
            {
                "lastTransactionID": "1298",
                "changes": {
                    "tradesClosed": [
                        {
                            "id": "1239",
                            "instrument": "US30_USD",
                            "currentUnits": "0.0",
                            "initialUnits": "1.0",
                            "averageClosePrice": "53730.7",
                        }
                    ],
                    "transactions": [
                        {
                            "type": "ORDER_FILL",
                            "id": "1298",
                            "orderID": "1241",
                            "instrument": "US30_USD",
                            "units": "-1.0",
                            "price": "53730.7",
                            "reason": "STOP_LOSS_ORDER",
                            "time": "2026-08-13T01:15:05.168126634Z",
                        }
                    ],
                    # positions intentionally omitted — production stream often does this
                },
            }
        )
        assert broker.reconcile_positions() == []
        assert store.read_table("positions") == []
    finally:
        tmp.cleanup()
