"""Tests for NQ-lead NAS100 synced follower strategy."""

from __future__ import annotations

import json
from pathlib import Path

from potions.live.models import Bar, BrokerOrder, StrategyInstance
from potions.live.nq_lead_nas100_sync import build_coupled_nq_stream, load_nq_lead_campaigns
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


def test_coupled_enters_only_after_nq_bar_complete(tmp_path: Path):
    plugin = _plugin(tmp_path, {}, coupled_stream=True)
    ctx = _ctx(plugin)
    # Nothing is preloaded, including the later NQ stop.
    quiet = plugin.on_bar_close(_bar("2021-03-04T11:04:00-05:00", 12800.0), ctx)
    assert list(quiet.order_intents) == []
    plugin.ingest_coupled_event(
        {
            "kind": "campaign",
            "session": "2021-03-04",
            "available_at_ts": "2021-03-04T11:03:00-05:00",
            "campaign_id": "nq_c1",
            "side": "long",
            "t_nq_entry": "2021-03-04T11:02:00-05:00",
            "p_nq_entry": 12765.0,
            "or_high_nq": 12765.0,
            "or_low_nq": 12649.0,
            "mapped_or_high": 12765.0,
            "mapped_or_low": 12649.0,
            "map_ratio": 1.0,
            "t_nq_stop": "2021-03-04T11:03:00-05:00",
        }
    )
    stored = plugin.state["coupled_campaigns"]["2021-03-04"][0]
    assert "t_nq_stop" not in stored
    # Completion timestamp itself is not yet a later bar.
    assert list(plugin.on_bar_close(_bar("2021-03-04T11:03:00-05:00", 12800.0), ctx).order_intents) == []
    plugin.ingest_coupled_event(
        {
            "kind": "milestone",
            "campaign_id": "nq_c1",
            "milestone": "stop",
            "t_nq": "2021-03-04T11:03:00-05:00",
            "available_at_ts": "2021-03-04T11:04:00-05:00",
        }
    )
    # Stop bar is complete at 11:04, so the 11:04 NAS bar still does not know it.
    actions = plugin.on_bar_close(_bar("2021-03-04T11:04:00-05:00", 12800.0), ctx)
    assert len(actions.order_intents) == 1
    assert actions.order_intents[0].side == "buy"


def test_coupled_skips_once_exit_bar_is_complete(tmp_path: Path):
    plugin = _plugin(tmp_path, {}, coupled_stream=True)
    ctx = _ctx(plugin)
    plugin.ingest_coupled_event(
        {
            "kind": "campaign",
            "session": "2021-03-04",
            "available_at_ts": "2021-03-04T11:03:00-05:00",
            "campaign_id": "nq_c1",
            "side": "long",
            "t_nq_entry": "2021-03-04T11:02:00-05:00",
            "p_nq_entry": 12765.0,
            "mapped_or_high": 12765.0,
            "mapped_or_low": 12649.0,
        }
    )
    plugin.ingest_coupled_event(
        {
            "kind": "milestone",
            "campaign_id": "nq_c1",
            "milestone": "stop",
            "t_nq": "2021-03-04T11:02:00-05:00",
            "available_at_ts": "2021-03-04T11:03:00-05:00",
        }
    )
    actions = plugin.on_bar_close(_bar("2021-03-04T11:04:00-05:00", 12800.0), ctx)
    assert list(actions.order_intents) == []
    audit = plugin.state.get("sync_audit") or []
    assert audit[-1]["skip_reason"] == "nq_already_stopped"


def test_build_coupled_stream_splits_exits(tmp_path: Path):
    root = tmp_path / "nq"
    state = root / "states" / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3"
    state.mkdir(parents=True)
    (state / "unit_trades.csv").write_text(
        "candidate,trade_id,unit_id,direction,entry_ts,entry_price,exit_ts,exit_price,exit_reason,net_usd\n"
        "c,tid,1,Long,2021-03-04T11:02:00-05:00,12765.62,2021-03-04T12:21:00-05:00,12648.88,wide_stop,-1\n",
        encoding="utf-8",
    )
    (state / "orders.csv").write_text(
        "trade_id,bracket_role,stop_price\n"
        "tid,entry,12765.25\n"
        "tid,wide_stop,12648.75\n",
        encoding="utf-8",
    )
    events = build_coupled_nq_stream(root)
    campaigns = [ev for ev in events if ev["kind"] == "campaign"]
    milestones = [ev for ev in events if ev["kind"] == "milestone"]
    assert len(campaigns) == 1
    assert campaigns[0]["available_at_ts"].startswith("2021-03-04T11:03:00")
    assert "t_nq_stop" not in campaigns[0]
    assert "t_nq_tp1" not in campaigns[0]
    assert milestones[0]["milestone"] == "stop"
    assert milestones[0]["available_at_ts"].startswith("2021-03-04T12:22:00")


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
