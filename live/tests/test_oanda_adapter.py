from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from potions.live.models import OrderIntent
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
