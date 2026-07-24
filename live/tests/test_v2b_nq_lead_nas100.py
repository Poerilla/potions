"""Tests for NQ-lead NAS100 synced follower strategy."""

from __future__ import annotations

import json
from pathlib import Path

from potions.live.models import Bar, BrokerOrder, StrategyInstance
from potions.live.nq_lead_nas100_sync import load_nq_lead_campaigns
from potions.live.registry import StrategyRegistry
from potions.live.store import FlatFileStore
from potions.live.strategies.base import StrategyContext
from potions.live.strategies.v2b_nq_lead_nas100 import V2BNqLeadNas100Strategy


def _bar(ts: str, close: float, high: float | None = None, low: float | None = None) -> Bar:
    h = close if high is None else high
    l = close if low is None else low
    return Bar(
        instrument="NAS100",
        timeframe="1m",
        ts=ts,
        open=close,
        high=h,
        low=l,
        close=close,
        volume=1.0,
        complete=True,
        source="test",
    )


def _plugin(tmp_path: Path, campaigns: dict, **cfg) -> V2BNqLeadNas100Strategy:
    store = FlatFileStore(tmp_path / "state")
    store.ensure()
    config = {
        "tick_size": 0.1,
        "entry_qty": 3,
        "tp1_qty": 1,
        "tp2_qty": 1,
        "t_max_seconds": 60,
        "delta_early_seconds": 30,
        "nq_lead_campaigns": campaigns,
        "record_sync_audit": True,
    }
    config.update(cfg)
    instance = StrategyInstance(
        strategy_id="test_nq_lead_nas100",
        strategy_type="v2b_nq_lead_nas100",
        version="v1",
        instrument="NAS100",
        broker_instrument="NAS100",
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=5,
        max_open_orders=16,
        config_json=json.dumps(config),
    )
    return V2BNqLeadNas100Strategy(store, instance)


def _ctx(plugin: V2BNqLeadNas100Strategy, qty: int = 0) -> StrategyContext:
    return StrategyContext(store=plugin.store, instance=plugin.instance, positions=[], open_orders=[])


def test_registry_resolves_nq_lead_type():
    reg = StrategyRegistry()
    assert "v2b_nq_lead_nas100" in reg._types
    assert reg._types["v2b_nq_lead_nas100"] is V2BNqLeadNas100Strategy


def test_sync_enter_within_60s(tmp_path: Path):
    campaigns = {
        "2021-03-04": [
            {
                "campaign_id": "nq_c1",
                "side": "long",
                "t_nq_entry": "2021-03-04T11:02:00-05:00",
                "p_nq_entry": 12765.0,
                "or_high_nq": 12765.0,
                "or_low_nq": 12649.0,
                "mapped_or_high": 12765.0,
                "mapped_or_low": 12649.0,
                "map_ratio": 1.0,
                "t_nq_tp1": None,
                "t_nq_stop": None,
                "t_nq_eod": None,
            }
        ]
    }
    plugin = _plugin(tmp_path, campaigns)
    ctx = _ctx(plugin)
    # Same minute as NQ entry, structure ok (close >= mapped OR high)
    actions = plugin.on_bar_close(_bar("2021-03-04T11:02:00-05:00", 12770.0), ctx)
    assert len(actions.order_intents) == 1
    assert actions.order_intents[0].order_type == "market"
    assert actions.order_intents[0].side == "buy"
    assert actions.order_intents[0].quantity == 3
    audit = plugin.state.get("sync_audit") or []
    assert audit and audit[-1]["state"] == "entered"
    assert abs(float(audit[-1]["entry_delta_seconds"])) <= 60


def test_late_bar_skips_sync_window(tmp_path: Path):
    campaigns = {
        "2021-03-04": [
            {
                "campaign_id": "nq_c1",
                "side": "long",
                "t_nq_entry": "2021-03-04T11:02:00-05:00",
                "p_nq_entry": 12765.0,
                "or_high_nq": 12765.0,
                "or_low_nq": 12649.0,
                "mapped_or_high": 12765.0,
                "mapped_or_low": 12649.0,
                "map_ratio": 1.0,
                "t_nq_tp1": None,
                "t_nq_stop": None,
                "t_nq_eod": None,
            }
        ]
    }
    plugin = _plugin(tmp_path, campaigns)
    ctx = _ctx(plugin)
    # +5 minutes → skip
    actions = plugin.on_bar_close(_bar("2021-03-04T11:07:00-05:00", 12800.0), ctx)
    assert list(actions.order_intents) == []
    audit = plugin.state.get("sync_audit") or []
    assert audit and audit[-1]["state"] == "skipped"
    assert audit[-1]["skip_reason"] == "sync_window_expired"


def test_nq_tp1_before_nas_skips_scaled(tmp_path: Path):
    campaigns = {
        "2021-03-04": [
            {
                "campaign_id": "nq_c1",
                "side": "long",
                "t_nq_entry": "2021-03-04T11:02:00-05:00",
                "p_nq_entry": 12765.0,
                "or_high_nq": 12765.0,
                "or_low_nq": 12649.0,
                "mapped_or_high": 12765.0,
                "mapped_or_low": 12649.0,
                "map_ratio": 1.0,
                "t_nq_tp1": "2021-03-04T11:02:30-05:00",
                "t_nq_stop": None,
                "t_nq_eod": None,
            }
        ]
    }
    plugin = _plugin(tmp_path, campaigns)
    ctx = _ctx(plugin)
    # Bar at 11:03 — within 60s of entry but after NQ TP1
    actions = plugin.on_bar_close(_bar("2021-03-04T11:03:00-05:00", 12850.0), ctx)
    assert list(actions.order_intents) == []
    audit = plugin.state.get("sync_audit") or []
    assert audit and audit[-1]["skip_reason"] == "nq_already_scaled"


def test_load_nq_lead_campaigns_from_book():
    root = Path("live/state/nq_v2b_prior_opposed_stpmc_broker_like")
    if not (root / "states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv").exists():
        return  # skip if book not present in CI
    camps = load_nq_lead_campaigns(root, start=__import__("datetime").date(2021, 3, 4))
    assert "2021-03-04" in camps
    ev = camps["2021-03-04"][0]
    assert ev["side"] in {"long", "short"}
    assert ev["or_high_nq"] > ev["or_low_nq"]
    assert "t_nq_entry" in ev
