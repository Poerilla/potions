from __future__ import annotations

import json
import tempfile
from pathlib import Path

from potions.live.config_runner import build_strategy_instance, init_from_config
from potions.live.broker import PaperBroker
from potions.live.engine import Engine
from potions.live.models import Bar, OrderIntent, StrategyInstance, as_row
from potions.live.notifications import DiskNotificationSink
from potions.live.registry import StrategyRegistry
from potions.live.risk import RiskManager
from potions.live.store import FlatFileStore
from potions.live.verification import SpoofVerificationProvider


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_flat_file_store_writes_and_reads_bars():
    tmp, store = make_store()
    try:
        bar = Bar("MNQ", "D", "2025-01-02", 1, 2, 0.5, 1.5, 100)
        store.append_bar(bar)
        assert store.read_bars("MNQ", "D")[0].close == 1.5
        assert (Path(tmp.name) / "bars" / "MNQ_D.csv").exists()
    finally:
        tmp.cleanup()


def test_paper_broker_order_lifecycle_and_bracket_attach():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="MNQ",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=100.0,
            bracket_stop_price=90.0,
            bracket_target_price=110.0,
            bracket_role="entry",
            requires_verification=False,
        )
        broker.submit_order_intent(intent)
        fills = broker.process_bar(Bar("MNQ", "D", "2025-04-01", 101, 105, 99, 104))
        assert len(fills) == 1
        assert len([o for o in broker.reconcile_orders() if o.status == "submitted"]) == 2

        fills = broker.process_bar(Bar("MNQ", "D", "2025-04-02", 104, 111, 103, 110))
        assert len(fills) == 1
        open_orders = [o for o in broker.reconcile_orders() if o.status == "submitted"]
        assert open_orders == []
        pos = broker.reconcile_positions()[0]
        assert pos.quantity == 0
        assert pos.realized_pnl == 10.0
    finally:
        tmp.cleanup()


def test_paper_broker_market_close_fills_at_same_bar_close_only():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store)
        entry = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="MNQ",
            account_mode="paper",
            side="buy",
            order_type="market",
            quantity=1,
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(Bar("MNQ", "D", "2025-04-01", 100, 105, 99, 104))

        close_intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="MNQ",
            account_mode="paper",
            side="sell",
            order_type="market_close",
            quantity=1,
            reason="month_end_flatten",
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts="2025-04-01",
        )
        broker.submit_order_intent(close_intent)
        assert broker.process_bar(Bar("MNQ", "D", "2025-04-01", 100, 105, 99, 104)) == []

        fills = broker.process_market_close_bar(Bar("MNQ", "D", "2025-04-01", 100, 105, 99, 104))
        assert len(fills) == 1
        assert fills[0].price == 104
        assert fills[0].reason == "close"
        assert broker.reconcile_positions()[0].quantity == 0
    finally:
        tmp.cleanup()


def test_paper_broker_modify_entry_updates_future_bracket_and_live_after():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store)
        intent = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="YM",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=100.0,
            bracket_stop_price=90.0,
            bracket_target_price=110.0,
            bracket_role="entry",
            live_after_ts="2025-04-01T10:00:00-04:00",
            requires_verification=False,
        )
        order = broker.submit_order_intent(intent)
        broker.modify_order(
            order.broker_order_id,
            limit_price=101.0,
            reason="refresh_entry",
            bracket_stop_price=95.0,
            bracket_target_price=120.0,
            live_after_ts="2025-04-01T11:00:00-04:00",
        )
        same_bar = Bar("YM", "1h", "2025-04-01T11:00:00-04:00", 102, 103, 100, 101)
        assert broker.process_bar(same_bar) == []

        next_bar = Bar("YM", "1h", "2025-04-01T12:00:00-04:00", 102, 103, 100, 101)
        fills = broker.process_bar(next_bar)
        assert len(fills) == 1
        assert fills[0].price == 101.0

        open_orders = sorted(
            [o for o in broker.reconcile_orders() if o.reduce_only],
            key=lambda item: item.order_type,
        )
        assert len(open_orders) == 2
        assert {o.stop_price for o in open_orders if o.order_type == "stop"} == {95.0}
        assert {o.limit_price for o in open_orders if o.order_type == "limit"} == {120.0}
    finally:
        tmp.cleanup()


def test_spoof_verification_auto_approves_paper_but_not_live():
    tmp, store = make_store()
    try:
        verifier = SpoofVerificationProvider(store)
        paper_intent = OrderIntent.create("s1", "t1", "MNQ", "paper", "buy", "market", 1)
        live_intent = OrderIntent.create("s1", "t2", "MNQ", "live", "buy", "market", 1)
        paper_req = verifier.request_verification(paper_intent)
        live_req = verifier.request_verification(live_intent)
        assert verifier.is_approved(paper_req.verification_id)
        assert not verifier.is_approved(live_req.verification_id)
    finally:
        tmp.cleanup()


def test_supertrend_wick_retest_enters_next_open_and_targets_same_bar():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="stwick",
            strategy_type="supertrend_wick_retest",
            version="v1",
            instrument="NQ",
            broker_instrument="NQ",
            account_mode="paper",
            enabled=True,
            timeframes="3m",
            max_contracts=1,
            max_open_orders=8,
            config_json=json.dumps(
                {
                    "timeframe": "3m",
                    "atr_len": 2,
                    "atr_mult": 0.5,
                    "target_pts": 2.0,
                    "entry_qty": 1,
                    "max_trades_per_day": 4,
                    "entry_cutoff": "15:45",
                    "eod_cutoff": "15:57",
                }
            ),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_health=False, slippage_ticks=0.0)
        engine.process_bar(Bar("NQ", "3m", "2025-04-01T09:30:00-04:00", 100, 101, 99, 100))
        engine.process_bar(Bar("NQ", "3m", "2025-04-01T09:33:00-04:00", 100, 101, 99, 100))
        engine.process_bar(Bar("NQ", "3m", "2025-04-01T09:36:00-04:00", 100, 103, 100, 102))
        fills = store.read_table("fills")
        assert [fill["reason"] for fill in fills] == ["entry", "target"]
        assert [float(fill["price"]) for fill in fills] == [100, 102]
        assert store.load_positions()[0].quantity == 0
    finally:
        tmp.cleanup()


def test_risk_blocks_conflicting_live_contract():
    tmp, store = make_store()
    try:
        store.upsert_row(
            "positions",
            "position_id",
            {
                "position_id": "other|MNQ|live",
                "strategy_id": "other",
                "instrument": "MNQ",
                "account_mode": "live",
                "quantity": "1",
                "avg_price": "100",
                "realized_pnl": "0",
                "updated_at": "",
            },
        )
        inst = StrategyInstance("s1", "yearly_orb_scaleout3", "v1", "MNQ", "MNQ", "live", True, "D", 3, 12)
        intent = OrderIntent.create("s1", "t1", "MNQ", "live", "buy", "market", 1)
        decision = RiskManager(store).validate_order_intent(inst, intent)
        assert not decision.allowed
        assert decision.reason == "live_contract_conflict"
    finally:
        tmp.cleanup()


def test_yearly_orb_paper_replay_creates_three_retest_orders():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="yorb",
            strategy_type="yearly_orb_scaleout3",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQH5",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=3,
            max_open_orders=24,
            config_json='{"batch_qty": 1}',
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store)
        bars = [
            Bar("MNQ", "D", "2025-01-02", 95, 100, 90, 95),
            Bar("MNQ", "D", "2025-02-03", 95, 101, 91, 96),
            Bar("MNQ", "D", "2025-03-31", 96, 102, 88, 95),
            Bar("MNQ", "D", "2025-04-01", 95, 100, 93, 96),
            Bar("MNQ", "D", "2025-04-02", 96, 99, 92, 95),
            Bar("MNQ", "D", "2025-04-03", 95, 101, 94, 99),
            Bar("MNQ", "D", "2025-04-04", 103, 106, 103, 105),
        ]
        engine.replay_bars(bars)
        orders = store.read_table("orders")
        assert len(orders) == 3
        assert {o["side"] for o in orders} == {"buy"}
        assert {o["order_type"] for o in orders} == {"limit"}
        assert all(o["status"] == "submitted" for o in orders)
        assert len(store.read_table("pending_verifications")) == 3
        assert all(v["status"] == "approved" for v in store.read_table("pending_verifications"))
    finally:
        tmp.cleanup()


def test_hourly_st_pmc_retest_registers_and_places_limit():
    tmp, store = make_store()
    try:
        assert "hourly_st_pmc_retest" in StrategyRegistry().available()
        daily = Path(__file__).resolve().parents[2] / "ym" / "ym_daily.csv"
        inst = StrategyInstance(
            strategy_id="ym_st_pmc_test",
            strategy_type="hourly_st_pmc_retest",
            version="v1",
            instrument="YM",
            broker_instrument="YM",
            account_mode="paper",
            enabled=True,
            timeframes="1h",
            max_contracts=1,
            max_open_orders=8,
            config_json=(
                '{"daily_bars_path": "%s", "stop_pts": 50, "target_pts": 150, '
                '"tick_size": 1.0, "entry_qty": 1}'
            )
            % str(daily),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        plugin = StrategyRegistry().create(store, inst)
        assert plugin.strategy_type == "hourly_st_pmc_retest"
    finally:
        tmp.cleanup()


def test_v2b_scaleout_honors_zero_tp2_qty():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="v2b_zero_tp2",
            strategy_type="v2b_scaleout",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=5,
            max_open_orders=16,
            config_json='{"entry_qty": 5, "tp1_qty": 1, "tp2_qty": 0}',
        )
        plugin = StrategyRegistry().create(store, inst)
        assert plugin._unit_quantities() == (1, 0, 4)
    finally:
        tmp.cleanup()


def test_v2b_deploy_mode_can_require_regime_dates():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="v2b_requires_regime_dates",
            strategy_type="v2b_scaleout",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=1,
            max_open_orders=8,
            config_json='{"entry_qty": 1, "tp1_qty": 1, "tp2_qty": 0, "require_regime_dates": true}',
        )
        plugin = StrategyRegistry().create(store, inst)
        assert not plugin._regime_ok("2026-01-02")
    finally:
        tmp.cleanup()


def test_config_runner_initializes_v2b_1_0_0(tmp_path):
    state_root = tmp_path / "state"
    config_path = tmp_path / "engine.conf.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"state_root": str(state_root)},
                "strategy": {
                    "strategy_id": "mnq_v2b_1_0_0_demo",
                    "strategy_type": "v2b_scaleout",
                    "instrument": "MNQ",
                    "broker_instrument": "MNQM6",
                    "account_mode": "paper",
                    "timeframes": "1m",
                    "max_contracts": 1,
                    "config": {
                        "mode": "oco_then_reverse",
                        "entry_qty": 1,
                        "tp1_qty": 1,
                        "tp2_qty": 0,
                        "use_regime_filter": True,
                    },
                },
                "broker": {"provider": "paper", "mode": "paper", "allow_live_routing": False},
            }
        ),
        encoding="utf-8",
    )

    root, instance = init_from_config(config_path)
    assert root == state_root
    assert instance.strategy_type == "v2b_scaleout"
    assert instance.max_contracts == 1
    assert json.loads(instance.config_json)["tp2_qty"] == 0

    store = FlatFileStore(state_root)
    rows = store.read_table("strategy_instances")
    assert len(rows) == 1
    assert rows[0]["strategy_id"] == "mnq_v2b_1_0_0_demo"


def test_config_runner_blocks_non_paper_broker_mode():
    config = {
        "strategy": {
            "strategy_id": "mnq_v2b_live",
            "strategy_type": "v2b_scaleout",
            "instrument": "MNQ",
            "account_mode": "paper",
            "config": {"entry_qty": 1, "tp1_qty": 1, "tp2_qty": 0},
        },
        "broker": {"provider": "tradovate", "mode": "broker-live", "allow_live_routing": False},
    }
    try:
        build_strategy_instance(config)
    except NotImplementedError as exc:
        assert "Only the local PaperBroker" in str(exc)
    else:
        raise AssertionError("broker-live should not be enabled by the bootstrap runner")
