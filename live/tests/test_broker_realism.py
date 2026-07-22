from __future__ import annotations

import tempfile
from pathlib import Path

from potions.live.broker import PaperBroker
from potions.live.models import Bar, OrderIntent, StrategyInstance
from potions.live.replay_audit import Bar as AuditBar
from potions.live.replay_audit import Unit, audit_units
from potions.live.risk import RiskManager
from potions.live.spread_model import SpreadModel
from potions.live.store import FlatFileStore


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_stop_gap_through_uses_open_then_adverse_slippage():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25})
        buy_stop = OrderIntent.create(
            "s1",
            "buy_gap",
            "MNQ",
            "paper",
            "buy",
            "stop",
            1,
            stop_price=100.0,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        sell_stop = OrderIntent.create(
            "s1",
            "sell_gap",
            "MNQ",
            "paper",
            "sell",
            "stop",
            1,
            stop_price=90.0,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(buy_stop)
        broker.submit_order_intent(sell_stop)

        buy_fills = broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:31:00-05:00", 103.0, 104.0, 102.5, 103.5))
        assert len(buy_fills) == 1
        assert buy_fills[0].trade_id == "buy_gap"
        assert buy_fills[0].price == 103.25

        sell_fills = broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:32:00-05:00", 87.0, 88.0, 86.0, 86.5))
        assert len(sell_fills) == 1
        assert sell_fills[0].trade_id == "sell_gap"
        assert sell_fills[0].price == 86.75
    finally:
        tmp.cleanup()


def test_stop_orders_are_processed_before_limits_on_same_bar():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25})
        entry = OrderIntent.create(
            "s1",
            "ambiguous_exit",
            "MNQ",
            "paper",
            "buy",
            "market",
            1,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:31:00-05:00", 100.0, 101.0, 99.5, 100.5))

        stop = OrderIntent.create(
            "s1",
            "ambiguous_exit",
            "MNQ",
            "paper",
            "sell",
            "stop",
            1,
            stop_price=98.0,
            reduce_only=True,
            bracket_role="stop",
            oco_group="exit_oco",
            live_after_ts="2026-01-01T09:31:00-05:00",
            requires_verification=False,
        )
        target = OrderIntent.create(
            "s1",
            "ambiguous_exit",
            "MNQ",
            "paper",
            "sell",
            "limit",
            1,
            limit_price=104.0,
            reduce_only=True,
            bracket_role="target",
            oco_group="exit_oco",
            live_after_ts="2026-01-01T09:31:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(target)
        broker.submit_order_intent(stop)

        fills = broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:32:00-05:00", 100.5, 105.0, 97.5, 103.0))
        assert len(fills) == 1
        assert fills[0].reason == "stop"
        assert fills[0].price == 97.75
        assert broker.reconcile_positions()[0].quantity == 0
        assert broker.reconcile_orders() == []
    finally:
        tmp.cleanup()


def test_strict_market_close_requires_exact_timestamp_and_slips_like_market_fill():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25}, strict_moc=True)
        entry = OrderIntent.create(
            "s1",
            "strict_moc",
            "MNQ",
            "paper",
            "buy",
            "market",
            1,
            live_after_ts="2026-01-01T15:58:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(Bar("MNQ", "1m", "2026-01-01T15:59:00-05:00", 100.0, 101.0, 99.5, 100.5))

        close = OrderIntent.create(
            "s1",
            "strict_moc",
            "MNQ",
            "paper",
            "sell",
            "market_close",
            1,
            reduce_only=True,
            bracket_role="close",
            live_after_ts="2026-01-01T16:00:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(close)

        early = broker.process_market_close_bar(Bar("MNQ", "1m", "2026-01-01T15:59:00-05:00", 100.5, 101.0, 100.0, 100.75))
        assert early == []

        fills = broker.process_market_close_bar(Bar("MNQ", "1m", "2026-01-01T16:00:00-05:00", 100.75, 101.0, 100.5, 100.8))
        assert len(fills) == 1
        assert fills[0].price == 100.55
        assert broker.reconcile_positions()[0].quantity == 0
    finally:
        tmp.cleanup()


def test_risk_projection_collapses_oco_group_and_sums_ladders():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store)
        risk = RiskManager(store)
        instance = StrategyInstance("s1", "v2b_scaleout", "v1", "MNQ", "MNQ", "paper", True, "1m", 2, 20)
        first_oco = OrderIntent.create("s1", "t1", "MNQ", "paper", "buy", "stop", 2, stop_price=101.0, oco_group="entry_oco")
        second_oco = OrderIntent.create("s1", "t1", "MNQ", "paper", "sell", "stop", 2, stop_price=99.0, oco_group="entry_oco")
        ladder = OrderIntent.create("s1", "t2", "MNQ", "paper", "buy", "limit", 1, limit_price=98.0)

        assert risk.validate_order_intent(instance, first_oco).allowed
        broker.submit_order_intent(first_oco)
        assert risk.validate_order_intent(instance, second_oco).allowed
        broker.submit_order_intent(second_oco)

        decision = risk.validate_order_intent(instance, ladder)
        assert not decision.allowed
        assert decision.reason == "max_contracts_exceeded"
    finally:
        tmp.cleanup()


def test_audit_units_subtracts_per_unit_fee_from_net_and_equity_curve():
    tmp = tempfile.TemporaryDirectory()
    try:
        root = Path(tmp.name)
        bars = [
            AuditBar("2026-01-01", 100.0, 101.0, 99.0, 100.0),
            AuditBar("2026-01-02", 110.0, 111.0, 109.0, 110.0),
            AuditBar("2026-01-03", 110.0, 111.0, 109.0, 110.0),
        ]
        units = [
            Unit(
                candidate="fee_test",
                trade_id="t1",
                unit_id="u1",
                direction="Long",
                entry_ts="2026-01-01",
                entry_price=100.0,
                exit_ts="2026-01-02",
                exit_price=110.0,
                exit_reason="target",
            )
        ]
        result = audit_units(
            name="Fee test",
            slug="fee_test",
            source=root / "fills.csv",
            bar_source=root / "bars.csv",
            bars=bars,
            units=units,
            instrument="MNQ",
            notes="fee test",
            output_root=root,
            fee_per_unit=1.50,
        )
        assert result.net_points == 10.0
        assert result.net_usd == 18.5
        equity_csv = (root / "fee_test" / "equity_curve.csv").read_text()
        assert "9.250000" in equity_csv
    finally:
        tmp.cleanup()


def test_spread_model_makes_market_buy_more_expensive():
    tmp, store = make_store()
    try:
        spread = SpreadModel(rth_half_spread_ticks=1.0, tick_size=0.25)
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25}, spread_model=spread)
        entry = OrderIntent.create(
            "s1",
            "spread_entry",
            "MNQ",
            "paper",
            "buy",
            "market",
            1,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        fills = broker.process_bar(Bar("MNQ", "1m", "2026-01-01T10:00:00-05:00", 100.0, 101.0, 99.5, 100.5, volume=500))
        assert len(fills) == 1
        assert fills[0].price == 100.5
    finally:
        tmp.cleanup()


def test_directional_path_blocks_limit_when_stop_would_hit_first():
    tmp, store = make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=0, tick_size={"MNQ": 0.25}, directional_adverse_path=True)
        entry = OrderIntent.create(
            "s1",
            "dir_path",
            "MNQ",
            "paper",
            "buy",
            "market",
            1,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:31:00-05:00", 100.0, 101.0, 99.5, 100.5))

        stop = OrderIntent.create(
            "s1",
            "dir_path",
            "MNQ",
            "paper",
            "sell",
            "stop",
            1,
            stop_price=98.0,
            reduce_only=True,
            bracket_role="stop",
            oco_group="exit_oco",
            live_after_ts="2026-01-01T09:31:00-05:00",
            requires_verification=False,
        )
        target = OrderIntent.create(
            "s1",
            "dir_path",
            "MNQ",
            "paper",
            "sell",
            "limit",
            1,
            limit_price=104.0,
            reduce_only=True,
            bracket_role="target",
            oco_group="exit_oco",
            live_after_ts="2026-01-01T09:31:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(target)
        broker.submit_order_intent(stop)

        fills = broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:32:00-05:00", 100.5, 105.0, 97.5, 103.0))
        assert len(fills) == 1
        assert fills[0].reason == "stop"
    finally:
        tmp.cleanup()


def test_paper_broker_ny_expiry_not_tripped_by_utc_noon_bar():
    """expires_after_ts at NY 15:59 must survive UTC bars that are still morning ET."""
    from potions.live.broker import _ts_after
    from potions.live.strategies.v2b_scaleout import _session_expiry

    exp = _session_expiry("2026-07-22")
    assert exp.endswith("-04:00") or exp.endswith("-05:00")
    assert not _ts_after("2026-07-22T16:00:00Z", exp)  # 12:00 ET
    assert _ts_after("2026-07-22T20:00:00Z", exp)  # 16:00 ET

    tmp, store = make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=0.0, tick_size={"EURUSD": 0.00001})
        intent = OrderIntent.create(
            "s1",
            "t1",
            "EURUSD",
            "paper",
            "buy",
            "limit",
            1,
            limit_price=1.1400,
            reduce_only=True,
            bracket_role="tp2",
            expires_after_ts=exp,
            requires_verification=False,
        )
        # Need a short position so reduce-only buy is eligible.
        entry = OrderIntent.create(
            "s1",
            "t1",
            "EURUSD",
            "paper",
            "sell",
            "market",
            2,
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(
            Bar(
                "EURUSD",
                "1m",
                "2026-07-22T13:50:00Z",
                1.1414,
                1.1415,
                1.1413,
                1.1414,
                bid_open=1.1413,
                bid_high=1.1413,
                bid_low=1.1413,
                bid_close=1.1413,
                ask_open=1.1415,
                ask_high=1.1415,
                ask_low=1.1415,
                ask_close=1.1415,
            )
        )
        order = broker.submit_order_intent(intent)
        assert order.status == "submitted"
        # Noon ET UTC bar previously string-expired naive 15:59 stamps.
        broker.process_bar(Bar("EURUSD", "1m", "2026-07-22T16:00:00Z", 1.1410, 1.1411, 1.1409, 1.1410))
        assert broker._get_order(order.broker_order_id).status == "submitted"
    finally:
        tmp.cleanup()
