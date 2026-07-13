from __future__ import annotations

import json
import tempfile
from pathlib import Path

from potions.live.cqg import (
    CqgBroker,
    CqgMarketDataFeedAdapter,
    CqgWebApiConfig,
    JsonCqgProtocolCodec,
    parse_contract_map,
    price_to_scaled,
    scaled_to_price,
)
from potions.live.models import OrderIntent
from potions.live.store import FlatFileStore


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_cqg_config_parses_contract_map_from_env_styles():
    assert parse_contract_map("MNQ=F.US.MNQM26,NQ=F.US.NQM26") == {
        "MNQ": "F.US.MNQM26",
        "NQ": "F.US.NQM26",
    }
    assert parse_contract_map('{"mnq": "F.US.MNQM26"}') == {"MNQ": "F.US.MNQM26"}
    config = CqgWebApiConfig.from_env(
        {
            "CQG_ENV": "demo",
            "CQG_USERNAME": "user",
            "CQG_PASSWORD": "pw",
            "CQG_ACCOUNT_ID": "123",
            "CQG_CONTRACT_MAP": "MNQ=F.US.MNQM26",
        }
    )
    assert config.endpoint == "wss://demoapi.cqg.com"
    assert config.cqg_symbol_for("mnq") == "F.US.MNQM26"


def test_cqg_json_codec_round_trips_message_dicts():
    codec = JsonCqgProtocolCodec()
    message = {"type": "logon", "request_id": 1, "client_id": "WebAPITest"}
    assert codec.decode(codec.encode(message)) == message


def test_cqg_feed_resolves_contract_per_session_and_persists_raw_events():
    tmp, store = make_store()
    try:
        adapter = CqgMarketDataFeedAdapter(store)
        adapter.on_raw_event(
            {
                "type": "symbol_resolution",
                "instrument": "MNQ",
                "cqg_symbol": "F.US.MNQM26",
                "contract_id": "session_contract_1",
                "price_scale": 2,
                "event_ts": "2026-01-02T14:29:59Z",
            }
        )
        assert adapter.contract_refs["MNQ"].contract_id == "session_contract_1"
        assert (Path(tmp.name) / "events" / "raw_market_data" / "cqg" / "2026-01-02.jsonl").exists()

        fresh_adapter = CqgMarketDataFeedAdapter(store)
        assert fresh_adapter.contract_refs == {}
    finally:
        tmp.cleanup()


def test_cqg_feed_builds_completed_1m_and_derived_5m_bars():
    tmp, store = make_store()
    try:
        adapter = CqgMarketDataFeedAdapter(store)
        adapter.resolve_contract("MNQ", "session_contract_1", cqg_symbol="F.US.MNQM26")
        emitted = []
        for i in range(6):
            minute = 30 + i
            emitted.extend(
                adapter.on_raw_event(
                    {
                        "type": "trade",
                        "instrument": "MNQ",
                        "price": 100.0 + i,
                        "quantity": 1,
                        "event_ts": "2026-01-02T14:%02d:05Z" % minute,
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


def test_cqg_feed_blocks_delayed_or_access_denied_market_data():
    tmp, store = make_store()
    try:
        adapter = CqgMarketDataFeedAdapter(store)
        adapter.on_raw_event({"type": "market_data_status", "instrument": "MNQ", "status": "delayed"})
        assert adapter.is_blocking_entries()
        assert adapter.blocking_reason() == "delayed"
        status = json.loads((Path(tmp.name) / "market_data_status.json").read_text(encoding="utf-8"))
        assert status["status"] == "blocked"
    finally:
        tmp.cleanup()


def test_cqg_broker_maps_order_intent_and_reconciles_fill_to_position():
    tmp, store = make_store()
    try:
        config = CqgWebApiConfig(account_id="acct1", contract_map={"MNQ": "F.US.MNQM26"})
        broker = CqgBroker(store, config=config)
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
        payload = broker.order_intent_to_cqg_payload(intent, order)
        assert payload["account_id"] == "acct1"
        assert payload["cqg_symbol"] == "F.US.MNQM26"
        assert payload["bracket"]["stop_price"] == 19900.25

        fill = broker.on_fill(
            {
                "broker_order_id": order.broker_order_id,
                "quantity": 2,
                "price": 20001.0,
                "event_ts": "2026-01-02T14:31:00Z",
            }
        )
        assert fill.quantity == 2
        assert broker.reconcile_orders() == []
        positions = broker.reconcile_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 2
        assert positions[0].avg_price == 20001.0
        assert (Path(tmp.name) / "events" / "cqg_order_events.jsonl").exists()
    finally:
        tmp.cleanup()


def test_cqg_price_scaling_helpers():
    assert price_to_scaled(5949.75, 2) == 594975
    assert scaled_to_price(594975, 2) == 5949.75

