from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from potions.live.models import OrderIntent, Position, as_row
from potions.live.risk import RiskManager
from potions.live.store import FlatFileStore
from potions.live.supervisor import RuntimeSupervisor
from potions.live.tradovate import (
    TradovateBroker,
    TradovateConfig,
    TradovateMarketDataFeedAdapter,
    TradovateOpenApiCatalog,
    TradovateRoutingBlocked,
    TradovateWebApiClient,
    load_jsonl_events,
    parse_contract_map,
)


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_tradovate_openapi_catalog_validates_required_routes_and_schemas():
    catalog = TradovateOpenApiCatalog.load(Path("live/openapi.json"))
    catalog.validate_required_routes()
    assert catalog.operation_id("/order/placeorder") == "placeOrder"
    assert catalog.request_schema_ref("/order/placeoso") == "#/components/schemas/PlaceOSO"
    assert "orderType" in catalog.schema_required("PlaceOrder")


def test_tradovate_config_parses_contract_map_and_defaults():
    assert parse_contract_map("MNQ=MNQM6,NQ=NQM6,MYM=MYMM6") == {
        "MNQ": "MNQM6",
        "NQ": "NQM6",
        "MYM": "MYMM6",
    }
    assert parse_contract_map('{"mnq": "MNQM6"}') == {"MNQ": "MNQM6"}
    config = TradovateConfig.from_env(
        {
            "TRADOVATE_ENV": "demo",
            "TRADOVATE_USERNAME": "user",
            "TRADOVATE_PASSWORD": "pw",
            "TRADOVATE_ACCOUNT_ID": "123",
            "TRADOVATE_CONTRACT_MAP": "MNQ=MNQM6",
            "TRADOVATE_CONTRACT_ID_MAP": "MNQ=456",
        }
    )
    assert config.rest_endpoint == "https://demo.tradovateapi.com/v1"
    assert config.ws_endpoint == "wss://demo.tradovateapi.com/v1/websocket"
    assert config.symbol_for("mnq") == "MNQM6"
    assert config.contract_id_for("mnq") == 456


def test_tradovate_client_builds_auth_payload_and_websocket_frames():
    config = TradovateConfig(username="u", password="p", app_id="app", app_version="1", cid="2", secret="sec")
    client = TradovateWebApiClient(config)
    auth = client.build_access_token_body()
    assert auth["name"] == "u"
    assert auth["sec"] == "sec"

    frame = client.build_ws_request_frame("contract/rollcontract", request_id=7, body={"name": "MNQM6", "forward": True})
    assert frame == 'contract/rollcontract\n7\n\n{"forward": true, "name": "MNQM6"}'
    assert client.build_authorize_frame("token", request_id=8) == "authorize\n8\n\ntoken"
    assert client.heartbeat_frame() == "[]"
    assert client.heartbeat_due(datetime.utcnow() - timedelta(seconds=3))
    assert not client.heartbeat_due(datetime.utcnow())

    assert client.parse_ws_frame("o").frame_type == "o"
    assert client.parse_ws_frame("h").frame_type == "h"
    parsed = client.parse_ws_frame('a[{"s":200,"i":2}]')
    assert parsed.frame_type == "a"
    assert parsed.payload[0]["s"] == 200
    assert client.parse_ws_frame('c[3000,"Go away"]') .payload[0] == 3000


def test_tradovate_feed_resolves_contract_per_session_and_persists_raw_events():
    tmp, store = make_store()
    try:
        adapter = TradovateMarketDataFeedAdapter(store)
        adapter.on_raw_event(
            {
                "type": "contract_resolution",
                "instrument": "MNQ",
                "symbol": "MNQM6",
                "contract_id": "12345",
                "event_ts": "2026-01-02T14:29:59Z",
            }
        )
        assert adapter.contract_refs["MNQ"].contract_id == "12345"
        assert (Path(tmp.name) / "events" / "raw_market_data" / "tradovate" / "2026-01-02.jsonl").exists()

        fresh_adapter = TradovateMarketDataFeedAdapter(store)
        assert fresh_adapter.contract_refs == {}
    finally:
        tmp.cleanup()


def test_tradovate_feed_builds_completed_1m_and_derived_5m_from_trades():
    tmp, store = make_store()
    try:
        adapter = TradovateMarketDataFeedAdapter(store)
        adapter.resolve_contract("MNQ", "12345", symbol="MNQM6")
        emitted = []
        for i in range(6):
            emitted.extend(
                adapter.on_raw_event(
                    {
                        "type": "trade",
                        "instrument": "MNQ",
                        "price": 100.0 + i,
                        "quantity": 1,
                        "event_ts": "2026-01-02T14:%02d:05Z" % (30 + i),
                    }
                )
            )
        emitted.extend(adapter.flush())

        one_minute = store.read_bars("MNQ", "1m")
        five_minute = store.read_bars("MNQ", "5m")
        assert len(one_minute) == 6
        assert len(five_minute) == 1
        assert five_minute[0].open == 100.0
        assert five_minute[0].high == 104.0
        assert five_minute[0].close == 104.0
        assert any(bar.timeframe == "5m" for bar in emitted)
    finally:
        tmp.cleanup()


def test_tradovate_feed_parses_chart_events_and_blocks_delayed_data():
    tmp, store = make_store()
    try:
        adapter = TradovateMarketDataFeedAdapter(store)
        bars = []
        for i in range(5):
            bars.append(
                {
                    "timestamp": "2026-01-02T14:%02d:00Z" % (30 + i),
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100.5 + i,
                    "upVolume": 2,
                    "downVolume": 1,
                }
            )
        emitted = adapter.on_raw_event({"e": "chart", "instrument": "MNQ", "d": {"charts": [{"id": 1, "bars": bars}]}})
        assert len(store.read_bars("MNQ", "1m")) == 5
        assert any(bar.timeframe == "5m" for bar in emitted)

        adapter.on_raw_event({"type": "market_data_status", "instrument": "MNQ", "status": "delayed"})
        assert adapter.is_blocking_entries()
        assert adapter.blocking_reason() == "delayed"
        status = json.loads((Path(tmp.name) / "market_data_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "blocked"
    finally:
        tmp.cleanup()


def test_tradovate_broker_maps_placeoso_and_reconciles_fill_to_position():
    tmp, store = make_store()
    try:
        config = TradovateConfig(account_id="123", account_spec="acct", contract_map={"MNQ": "MNQM6"})
        broker = TradovateBroker(store, config=config, server_oco_validated=True)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="MNQ",
            account_mode="paper",
            side="buy",
            order_type="stop",
            quantity=2,
            stop_price=20000.25,
            bracket_stop_price=19900.25,
            bracket_target_price=20100.25,
            requires_verification=False,
            bracket_role="entry",
        )
        order = broker.submit_order_intent(intent)
        endpoint, payload = broker.order_intent_to_tradovate_request(intent, order)
        assert endpoint == "/order/placeoso"
        assert payload["accountId"] == 123
        assert payload["symbol"] == "MNQM6"
        assert payload["orderType"] == "Stop"
        assert payload["isAutomated"] is True
        assert payload["bracket1"]["orderType"] == "Limit"
        assert payload["bracket2"]["orderType"] == "Stop"

        fill = broker.on_fill(
            {
                "broker_order_id": order.broker_order_id,
                "quantity": 2,
                "price": 20001.0,
                "timestamp": "2026-01-02T14:31:00Z",
            }
        )
        assert fill.quantity == 2
        assert broker.reconcile_orders() == []
        positions = broker.reconcile_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 2
        assert positions[0].avg_price == 20001.0
        assert (Path(tmp.name) / "events" / "tradovate_order_events.jsonl").exists()
    finally:
        tmp.cleanup()


def test_tradovate_broker_blocks_live_bracket_without_demo_validated_server_oco():
    tmp, store = make_store()
    try:
        config = TradovateConfig(env="demo", account_id="123", account_spec="acct", contract_map={"MNQ": "MNQM6"})
        broker = TradovateBroker(store, config=config, allow_live_routing=True, server_oco_validated=False)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="MNQ",
            account_mode="live",
            side="buy",
            order_type="stop",
            quantity=1,
            stop_price=20000.25,
            bracket_stop_price=19900.25,
            bracket_target_price=20100.25,
            requires_verification=False,
        )
        with pytest.raises(TradovateRoutingBlocked):
            broker.submit_order_intent(intent)
    finally:
        tmp.cleanup()


def test_runtime_supervisor_freezes_entries_but_allows_reduce_only():
    tmp, store = make_store()
    try:
        from potions.live.models import StrategyInstance

        supervisor = RuntimeSupervisor(store, provider="tradovate")
        supervisor.observe_heartbeat_age(1001, "feed")
        risk = RiskManager(store, supervisor=supervisor)
        instance = StrategyInstance(
            strategy_id="s1",
            strategy_type="v2b",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
        )
        entry = OrderIntent.create("s1", "t1", "MNQ", "paper", "buy", "market", 1, requires_verification=False)
        exit_intent = OrderIntent.create(
            "s1",
            "t1",
            "MNQ",
            "paper",
            "sell",
            "market",
            1,
            requires_verification=False,
            reduce_only=True,
        )
        assert not risk.validate_order_intent(instance, entry).allowed
        assert risk.validate_order_intent(instance, exit_intent).allowed
    finally:
        tmp.cleanup()


def test_tradovate_emergency_flatten_persists_runtime_status_and_liquidation_payload():
    tmp, store = make_store()
    try:
        config = TradovateConfig(account_id="123", account_spec="acct", contract_map={"MNQ": "MNQM6"}, contract_id_map={"MNQ": "456"})
        supervisor = RuntimeSupervisor(store, provider="tradovate")
        broker = TradovateBroker(store, config=config, supervisor=supervisor)
        position = Position("s1|MNQ|paper", "s1", "MNQ", "paper", 1, 20000.0)
        store.upsert_row("positions", "position_id", as_row(position))
        broker = TradovateBroker(store, config=config, supervisor=supervisor)
        payloads = broker.go_flat(["MNQ"])
        assert payloads == [{"accountId": 123, "contractId": 456, "admin": False, "customTag50": "potions_flat"}]
        status = json.loads((Path(tmp.name) / "runtime_status.json").read_text(encoding="utf-8"))
        assert status["mode"] == "emergency_flatten"
    finally:
        tmp.cleanup()
