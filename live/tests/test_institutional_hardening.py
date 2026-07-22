from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from potions.live.causality import AUDIT, STRICT, CausalityGuard
from potions.live.engine import Engine
from potions.live.execution_scrutiny import NEEDS_TICK, OK, VIOLATION_RISK, classify_execution_row
from potions.live.instruments import asof_latest, get_instrument, point_value, rth_session, tick_size
from potions.live.models import Bar, FeatureSnapshot, OrderIntent, StrategyInstance, as_row
from potions.live.promotion import generate_promotion_status
from potions.live.replay_manifest import write_run_manifest
from potions.live.store import FlatFileStore


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_causality_guard_records_future_available_feature_in_audit_mode():
    tmp, store = make_store()
    try:
        guard = CausalityGuard(store, mode=AUDIT)
        bar = Bar("NQ", "1m", "2026-01-02T10:00:00-05:00", 1, 2, 1, 2)
        feature = FeatureSnapshot(
            feature_name="future_daily_close",
            strategy_id="s1",
            instrument="NQ",
            event_ts="2026-01-02T10:00:00-05:00",
            available_at_ts="2026-01-02T10:01:00-05:00",
            current_bar_ts=bar.ts,
            source="test",
        )
        violations = guard.record_features([feature], bar)
        assert len(violations) == 1
        assert violations[0].violation_type == "feature_available_after_current_bar"
        assert store.read_table("feature_snapshots")[0]["feature_name"] == "future_daily_close"
        assert store.read_table("causality_violations")[0]["scrutiny_classification"] == VIOLATION_RISK
    finally:
        tmp.cleanup()


def test_strict_causality_blocks_past_live_after_entry_but_not_reduce_only_exit():
    tmp, store = make_store()
    try:
        guard = CausalityGuard(store, mode=STRICT)
        inst = StrategyInstance("s1", "test", "v1", "NQ", "NQ", "paper", True, "1m", 1, 4)
        bar = Bar("NQ", "1m", "2026-01-02T10:00:00-05:00", 1, 2, 1, 2)
        entry = OrderIntent.create(
            "s1",
            "t1",
            "NQ",
            "paper",
            "buy",
            "stop",
            1,
            stop_price=3.0,
            live_after_ts="2026-01-02T09:59:00-05:00",
            requires_verification=False,
        )
        exit_intent = OrderIntent.create(
            "s1",
            "t1",
            "NQ",
            "paper",
            "sell",
            "stop",
            1,
            stop_price=1.0,
            live_after_ts="2026-01-02T09:59:00-05:00",
            reduce_only=True,
            requires_verification=False,
        )
        entry_decision = guard.validate_order_intent(inst, entry, bar)
        exit_decision = guard.validate_order_intent(inst, exit_intent, bar)
        assert not entry_decision.allowed
        assert entry_decision.violations[0].violation_type == "order_activation_before_current_bar"
        assert exit_decision.allowed
    finally:
        tmp.cleanup()


def test_execution_scrutiny_classification_codes():
    assert classify_execution_row({"latency_risk": "safe", "opposite_gate_known_before_v2b": True}) == OK
    assert classify_execution_row({"latency_risk": "ambiguous_same_1m_bar", "opposite_gate_known_before_v2b": True}) == NEEDS_TICK
    assert classify_execution_row({"latency_risk": "safe", "opposite_gate_known_before_v2b": False}) == VIOLATION_RISK


def test_run_manifest_records_causality_mode_and_output_hashes():
    tmp = tempfile.TemporaryDirectory()
    try:
        root = Path(tmp.name)
        data = root / "input.csv"
        out = root / "summary.csv"
        data.write_text("x\n1\n", encoding="utf-8")
        out.write_text("net\n10\n", encoding="utf-8")
        manifest = write_run_manifest(
            root,
            command=["pytest", "sample"],
            data_inputs=[data],
            output_paths=[out],
            strategy_config={"strategy": "demo"},
            broker_realism_config={"slippage_ticks": 1},
            causality_mode=STRICT,
            repo_root=Path.cwd(),
        )
        assert manifest["causality_mode"] == STRICT
        assert manifest["broker_realism_config"]["slippage_ticks"] == 1
        assert manifest["outputs"][0]["sha256"]
        assert (root / "run_manifest.json").exists()
        assert (root / "run_manifest.sha256").exists()
    finally:
        tmp.cleanup()


def test_instrument_master_and_flat_file_asof_semantics():
    assert point_value("MNQ") == 2.0
    assert tick_size("YM") == 1.0
    assert get_instrument("ES").databento_parent == "ES.FUT"
    start, end, tz = rth_session("NQ")
    assert (start.hour, start.minute, end.hour, end.minute, tz) == (9, 30, 16, 0, "America/New_York")
    rows = [
        {"name": "ma", "value": "old", "available_at_ts": "2026-01-02T09:00:00-05:00"},
        {"name": "ma", "value": "future", "available_at_ts": "2026-01-02T10:01:00-05:00"},
        {"name": "atr", "value": "other", "available_at_ts": "2026-01-02T09:30:00-05:00"},
    ]
    row = asof_latest(rows, "2026-01-02T10:00:00-05:00", match={"name": "ma"})
    assert row["value"] == "old"


def test_promotion_status_blocks_missing_strict_null_dsr_and_tick_rows():
    tmp = tempfile.TemporaryDirectory()
    try:
        root = Path(tmp.name)
        (root / "summary.csv").write_text("net\n1\n", encoding="utf-8")
        (root / "run_manifest.json").write_text(json.dumps({"causality_mode": AUDIT}), encoding="utf-8")
        with (root / "execution_scrutiny.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["campaign_id", "scrutiny_classification"])
            writer.writeheader()
            writer.writerow({"campaign_id": "t1", "scrutiny_classification": NEEDS_TICK})
        status = generate_promotion_status(root)
        assert status.current_state == "hardened_realism"
        assert "causality_mode_not_strict" in status.blocking_reasons
        assert "tick_escalation_required" in status.blocking_reasons
        assert "missing_null_results" in status.blocking_reasons
        assert "missing_campaign_dsr" in status.blocking_reasons
        assert (root / "promotion_status.json").exists()
    finally:
        tmp.cleanup()


def test_v2b_scaleout_emits_opening_range_and_entry_gate_snapshots():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="v2b_snapshot",
            strategy_type="v2b_scaleout",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=2,
            max_open_orders=8,
            config_json=json.dumps({"use_regime_filter": False, "entry_qty": 1, "tp1_qty": 1, "tp2_qty": 0}),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_health=False)
        for minute in range(15):
            ts = "2026-01-02T09:%02d:00-05:00" % (30 + minute)
            engine.process_bar(Bar("MNQ", "1m", ts, 100 + minute * 0.1, 101 + minute * 0.1, 99, 100))
        names = {row["feature_name"] for row in store.read_table("feature_snapshots")}
        assert {"v2b_opening_range", "v2b_regime_filter", "v2b_entry_gate"}.issubset(names)
    finally:
        tmp.cleanup()


def test_v2b_scaleout_builds_or_from_true_utc_bar_timestamps():
    """OANDA/live bars are UTC (Z). Session clocks are NY wall; do not compare raw UTC hours."""
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="v2b_utc_or",
            strategy_type="v2b_scaleout",
            version="v1",
            instrument="EURUSD",
            broker_instrument="EURUSD",
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=3,
            max_open_orders=8,
            config_json=json.dumps(
                {
                    "mode": "oco_then_reverse",
                    "use_regime_filter": False,
                    "entry_qty": 3,
                    "tp1_qty": 1,
                    "tp2_qty": 1,
                    "prior_opposite_only": False,
                }
            ),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_health=False)
        # 2026-07-22 is EDT: NY 09:30–09:44 == UTC 13:30–13:44.
        for minute in range(15):
            ts = "2026-07-22T13:%02d:00Z" % (30 + minute)
            engine.process_bar(Bar("EURUSD", "1m", ts, 1.10, 1.101, 1.099, 1.1005))
        state_rows = store.read_table("strategy_state")
        assert state_rows
        state = json.loads(state_rows[0]["state_json"])
        assert state["or_count"] == 15
        assert state["or_finalized"] is True
        assert state["regime_ok"] is True
        assert state["phase"] == "armed"
        intents = store.read_table("order_intents")
        assert len(intents) >= 2
        sides = {row["side"] for row in intents if not _as_bool(row.get("reduce_only"))}
        assert sides == {"buy", "sell"}
    finally:
        tmp.cleanup()


def _as_bool(value) -> bool:
    return str(value).lower() in {"1", "true", "yes"}


def test_hourly_st_pmc_emits_signal_pmc_and_entry_gate_snapshots():
    tmp, store = make_store()
    try:
        daily_path = Path(tmp.name) / "ym_daily.csv"
        daily_path.write_text(
            "date,open,high,low,close,volume\n"
            "2026-03-31,100,101,99,100,1\n"
            "2026-04-01,100,102,99,101,1\n",
            encoding="utf-8",
        )
        inst = StrategyInstance(
            strategy_id="st_pmc_snapshot",
            strategy_type="hourly_st_pmc_retest",
            version="v1",
            instrument="YM",
            broker_instrument="YM",
            account_mode="paper",
            enabled=True,
            timeframes="1h",
            max_contracts=1,
            max_open_orders=8,
            config_json=json.dumps({"daily_bars_path": str(daily_path), "atr_len": 2, "atr_mult": 1.0}),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_health=False)
        engine.process_bar(Bar("YM", "1h", "2026-04-01T09:00:00-05:00", 100, 101, 99, 100))
        engine.process_bar(Bar("YM", "1h", "2026-04-01T10:00:00-05:00", 100, 103, 100, 102))
        names = {row["feature_name"] for row in store.read_table("feature_snapshots")}
        assert {"hourly_st_pmc_signal", "prev_month_close", "hourly_st_pmc_entry_gate"}.issubset(names)
    finally:
        tmp.cleanup()


def test_yearly_orb_emits_range_swing_and_entry_gate_snapshots():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="yorb_snapshot",
            strategy_type="yearly_orb_scaleout3",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=3,
            max_open_orders=24,
            config_json=json.dumps({"batch_qty": 1}),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_health=False)
        bars = [
            Bar("MNQ", "D", "2026-01-02", 95, 100, 90, 95),
            Bar("MNQ", "D", "2026-02-03", 95, 101, 91, 96),
            Bar("MNQ", "D", "2026-03-31", 96, 102, 88, 95),
            Bar("MNQ", "D", "2026-04-01", 95, 100, 93, 96),
            Bar("MNQ", "D", "2026-04-02", 96, 99, 92, 95),
            Bar("MNQ", "D", "2026-04-03", 95, 101, 94, 99),
            Bar("MNQ", "D", "2026-04-04", 103, 106, 103, 105),
        ]
        engine.replay_bars(bars)
        names = {row["feature_name"] for row in store.read_table("feature_snapshots")}
        assert "yearly_orb_range" in names
        assert "yearly_orb_inside_swing_low" in names
        assert "yearly_orb_entry_gate" in names
    finally:
        tmp.cleanup()


def test_atr_supertrend_dca_emits_signal_and_guard_snapshots():
    tmp, store = make_store()
    try:
        inst = StrategyInstance(
            strategy_id="atr_snapshot",
            strategy_type="atr_supertrend_dca",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=3,
            max_open_orders=8,
            config_json=json.dumps({"signal_tf": "daily", "atr_len": 2, "atr_mult": 1.0, "initial_qty": 1}),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(store=store, persist_health=False)
        bars = [
            Bar("MNQ", "D", "2026-01-01", 100, 101, 99, 100),
            Bar("MNQ", "D", "2026-01-02", 100, 102, 99, 101),
            Bar("MNQ", "D", "2026-01-05", 101, 103, 100, 102),
            Bar("MNQ", "D", "2026-01-06", 102, 104, 101, 103),
            Bar("MNQ", "D", "2026-01-07", 103, 105, 102, 104),
        ]
        engine.replay_bars(bars)
        names = {row["feature_name"] for row in store.read_table("feature_snapshots")}
        assert {"atr_supertrend_signal", "atr_entry_guard"}.issubset(names)
    finally:
        tmp.cleanup()
