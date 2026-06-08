from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from potions.live.engine import Engine
from potions.live.models import Bar, StrategyInstance, as_row
from potions.live.store import FlatFileStore
from potions.live.v2b_prior_opposed_execution_scrutiny import _delay_classification, _latency_risk, _late_fill_estimate


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def _install_v2b(store: FlatFileStore, events):
    inst = StrategyInstance(
        strategy_id="v2b_gate",
        strategy_type="v2b_scaleout",
        version="v1",
        instrument="NQ",
        broker_instrument="NQ",
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=5,
        max_open_orders=12,
        config_json=json.dumps(
            {
                "mode": "oco_then_reverse",
                "entry_qty": 5,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "use_regime_filter": False,
                "dynamic_sizing_events": {"2026-01-02": events},
                "prior_opposite_only": True,
                "prior_opposite_entry_qty": 5,
                "prior_opposite_tp1_qty": 1,
                "prior_opposite_tp2_qty": 1,
            }
        ),
    )
    store.write_table("strategy_instances", [as_row(inst)])


def _run_opening_range(engine: Engine):
    for minute in range(30, 45):
        engine.process_bar(
            Bar(
                "NQ",
                "1m",
                "2026-01-02T09:%02d:00-05:00" % minute,
                100,
                101,
                99,
                100,
                complete=True,
            )
        )


def test_prior_opposite_v2b_gate_does_not_arm_without_prior_opposite_event():
    tmp, store = make_store()
    try:
        _install_v2b(store, [])
        engine = Engine(store=store, persist_health=False, slippage_ticks=0.0)
        _run_opening_range(engine)
        assert engine.broker.reconcile_orders() == []
    finally:
        tmp.cleanup()


def test_prior_opposite_v2b_gate_arms_only_the_direction_opposed_to_stpmc():
    tmp, store = make_store()
    try:
        _install_v2b(store, [{"ts": "2026-01-02T09:40:00-05:00", "side": "short"}])
        engine = Engine(store=store, persist_health=False, slippage_ticks=0.0)
        _run_opening_range(engine)
        orders = engine.broker.reconcile_orders()
        assert len(orders) == 1
        assert orders[0].side == "buy"
        assert orders[0].bracket_role == "entry"
        assert orders[0].live_after_ts == "2026-01-02T09:44:00-05:00"
    finally:
        tmp.cleanup()


def test_latency_classifier_marks_same_minute_and_pre_arm_touch_as_not_proven_safe():
    assert _latency_risk(60.0, pd.NaT) == "ambiguous_same_1m_bar"
    assert _latency_risk(300.0, pd.Timestamp("2026-01-02T09:45:00-05:00")) == "pre_arm_breakout_touch"
    assert _delay_classification(300.0, False, 0.2) == "safe"
    assert _delay_classification(60.0, False, 0.2) == "ambiguous_same_1m_bar"
    assert _delay_classification(300.0, True, 0.2) == "pre_arm_breakout_touch"


def test_late_fill_estimate_separates_retest_from_possible_miss():
    assert _late_fill_estimate("safe", False, False) == "bar_safe"
    assert _late_fill_estimate("ambiguous_same_1m_bar", True, True) == "later_level_retest"
    assert _late_fill_estimate("pre_arm_breakout_touch", False, True) == "later_trigger_touch_only"
    assert _late_fill_estimate("pre_arm_breakout_touch", False, False) == "no_later_touch_in_1m"
