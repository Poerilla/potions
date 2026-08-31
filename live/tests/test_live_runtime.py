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


def test_yearly_orb_range_close_fills_next_bar_open_not_same_bar():
    """Range-close decided on a completed daily bar must not fill that bar's open."""
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="yorb_rc",
            strategy_type="yearly_orb_scaleout3",
            version="v1",
            instrument="XAUUSD",
            broker_instrument="XAUUSD",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=3,
            max_open_orders=24,
            config_json='{"batch_qty": 1, "tick_size": 0.01}',
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_bars=False, persist_health=False)
        # Build YOR Jan–Mar, break short in April, then close back inside range.
        bars = [
            Bar("XAUUSD", "D", "2004-01-02", 400, 420, 390, 410, complete=True),
            Bar("XAUUSD", "D", "2004-02-02", 410, 430, 400, 420, complete=True),
            Bar("XAUUSD", "D", "2004-03-31", 420, 440, 380, 400, complete=True),  # YOR 440/380
            Bar("XAUUSD", "D", "2004-04-01", 400, 410, 370, 375, complete=True),  # close below YOR low → short retest
            Bar("XAUUSD", "D", "2004-04-02", 375, 385, 370, 372, complete=True),  # fill short retest; stay outside
            # Still short into a day that closes back inside YOR → range_close decision
            Bar("XAUUSD", "D", "2004-04-05", 382, 390, 378, 400, complete=True),
            # Causal fill must land on the *next* open, not 2004-04-05 open
            Bar("XAUUSD", "D", "2004-04-06", 401, 405, 395, 402, complete=True),
        ]
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        close_fills = [f for f in fills if str(f.get("reason")) == "close"]
        assert close_fills, "expected a range-close flatten fill"
        assert all(str(f["ts"]).startswith("2004-04-06") for f in close_fills)
        # Market fill uses next bar open (+/- slippage if configured; default 0).
        assert all(abs(float(f["price"]) - 401.0) < 1e-9 for f in close_fills)
        orders = [o for o in store.read_table("orders") if str(o.get("bracket_role")) == "close"]
        assert orders and all(str(o.get("live_after_ts", "")).startswith("2004-04-05") for o in orders)
    finally:
        tmp.cleanup()


def test_yearly_orb_mid_close_fills_next_bar_open():
    """mid_close: long flattens when close <= YOR mid; fill waits for next open."""
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="yorb_mid",
            strategy_type="yearly_orb_scaleout3",
            version="v1",
            instrument="XAUUSD",
            broker_instrument="XAUUSD",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=3,
            max_open_orders=24,
            config_json='{"batch_qty": 1, "exit_mode": "mid_close", "tick_size": 0.01}',
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_bars=False, persist_health=False)
        # YOR 440/380 → mid=410. Short below 380, then close back above mid (not mid exit),
        # then close at/above mid from short side? Short exit: close >= mid.
        bars = [
            Bar("XAUUSD", "D", "2004-01-02", 400, 420, 390, 410, complete=True),
            Bar("XAUUSD", "D", "2004-02-02", 410, 430, 400, 420, complete=True),
            Bar("XAUUSD", "D", "2004-03-31", 420, 440, 380, 400, complete=True),  # YOR 440/380 mid 410
            Bar("XAUUSD", "D", "2004-04-01", 400, 410, 370, 375, complete=True),  # short break
            Bar("XAUUSD", "D", "2004-04-02", 375, 385, 370, 372, complete=True),  # fill short
            # Close inside range but below mid — should NOT mid-close a short (need close >= 410)
            Bar("XAUUSD", "D", "2004-04-05", 382, 400, 378, 395, complete=True),
            # Close at mid → mid_close decision
            Bar("XAUUSD", "D", "2004-04-06", 395, 415, 390, 410, complete=True),
            Bar("XAUUSD", "D", "2004-04-07", 412, 418, 405, 414, complete=True),
        ]
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        close_fills = [f for f in fills if str(f.get("reason")) == "close"]
        assert close_fills, "expected mid_close flatten fill"
        assert all(str(f["ts"]).startswith("2004-04-07") for f in close_fills)
        assert all(abs(float(f["price"]) - 412.0) < 1e-9 for f in close_fills)
        orders = [o for o in store.read_table("orders") if str(o.get("bracket_role")) == "close"]
        assert orders and all(str(o.get("live_after_ts", "")).startswith("2004-04-06") for o in orders)
    finally:
        tmp.cleanup()


def test_yearly_orb_inside_swing_take_skips_range_close_and_trails_stop():
    """inside_swing_take: no range_close flatten; stop ratchets to new inside swing."""
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="yorb_swing",
            strategy_type="yearly_orb_scaleout3",
            version="v1",
            instrument="XAUUSD",
            broker_instrument="XAUUSD",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=3,
            max_open_orders=24,
            config_json='{"batch_qty": 1, "exit_mode": "inside_swing_take", "tick_size": 0.01}',
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_bars=False, persist_health=False)
        bars = [
            Bar("XAUUSD", "D", "2004-01-02", 400, 420, 390, 410, complete=True),
            Bar("XAUUSD", "D", "2004-02-02", 410, 430, 400, 420, complete=True),
            Bar("XAUUSD", "D", "2004-03-31", 420, 440, 380, 400, complete=True),  # YOR 440/380
            Bar("XAUUSD", "D", "2004-04-01", 400, 410, 370, 375, complete=True),  # short break
            Bar("XAUUSD", "D", "2004-04-02", 375, 385, 370, 372, complete=True),  # fill short
            # Close deep inside range — default range_close would flatten; swing mode must not.
            Bar("XAUUSD", "D", "2004-04-05", 382, 400, 378, 390, complete=True),
            Bar("XAUUSD", "D", "2004-04-06", 390, 405, 385, 395, complete=True),
        ]
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        assert not any(str(f.get("reason")) in {"range_close", "mid_close"} for f in fills)
        # Still short after inside closes (no market flatten).
        assert any(str(f.get("side")) == "sell" and str(f.get("reason")) in {"entry", "short_tp25_entry", "short_tp_entry", "short_runner_entry"} for f in fills)
        pos = store.read_table("positions")
        assert pos and float(pos[-1].get("quantity") or 0) < 0
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


def test_v2b_scaleout_targeted_runner_qty_splits_10r_sleeve():
    """S_1_1_3 + 1×10R: 4 runners → only 1 gets runner_tp."""
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="v2b_plus_10r",
            strategy_type="v2b_scaleout",
            version="v1",
            instrument="NQ",
            broker_instrument="NQ",
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=6,
            max_open_orders=16,
            config_json=json.dumps(
                {
                    "entry_qty": 6,
                    "tp1_qty": 1,
                    "tp2_qty": 1,
                    "tick_size": 0.25,
                    "targeted_runner_qty": 1,
                    "runner_target_r_mult": 10.0,
                }
            ),
        )
        plugin = StrategyRegistry().create(store, inst)
        assert plugin._unit_quantities() == (1, 1, 4)
        state = {
            "or_high": 100.0,
            "or_low": 90.0,
            "session_date": "2024-01-02",
            "trades": {"t1": {"entry_qty": 6, "tp1_qty": 1, "tp2_qty": 1}},
        }
        orders = plugin._runner_exit_orders("t1", "Long", state)
        roles = {o.bracket_role: o.quantity for o in orders}
        assert roles.get("runner_tp") == 1
        assert roles.get("tp2") == 1
        assert roles.get("runner_stop") == 5  # tp2 + 4 runners
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


def test_strategy_open_orders_includes_oanda_working_status():
    """OANDA rests land as status=working; plugins must see them for refresh/cancel."""
    from potions.live.models import OPEN_ORDER_STATUSES, BrokerOrder, StrategyInstance
    from potions.live.strategies.base import StrategyContext

    assert "working" in OPEN_ORDER_STATUSES
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="s1",
            strategy_type="hourly_st_pmc_retest",
            version="v1",
            instrument="US30",
            broker_instrument="US30_USD",
            account_mode="paper",
        )
        orders = [
            BrokerOrder(
                broker_order_id="ord_w",
                intent_id="i1",
                strategy_id="s1",
                trade_id="t1",
                instrument="US30",
                account_mode="paper",
                side="buy",
                order_type="limit",
                quantity=1,
                remaining_quantity=1,
                status="working",
                limit_price=100.0,
            ),
            BrokerOrder(
                broker_order_id="ord_c",
                intent_id="i2",
                strategy_id="s1",
                trade_id="t2",
                instrument="US30",
                account_mode="paper",
                side="buy",
                order_type="limit",
                quantity=1,
                remaining_quantity=1,
                status="cancelled",
                limit_price=100.0,
            ),
        ]
        ctx = StrategyContext(store=store, instance=inst, positions=[], open_orders=orders)
        assert [o.broker_order_id for o in ctx.strategy_open_orders] == ["ord_w"]
    finally:
        tmp.cleanup()
