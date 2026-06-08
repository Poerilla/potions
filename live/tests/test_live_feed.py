from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from potions.live.live_feed import PersistedLiveFeedAdapter, compare_csv_for_replay_parity
from potions.live.store import FlatFileStore


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def test_persisted_live_feed_emits_only_completed_supported_bars():
    tmp, store = make_store()
    try:
        emitted = []
        adapter = PersistedLiveFeedAdapter(store, on_bar=emitted.append)
        adapter.on_raw_event(
            {
                "type": "bar",
                "instrument": "NQ",
                "timeframe": "1m",
                "ts": "2026-01-02T09:30:00-05:00",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 10,
                "complete": True,
                "source": "test",
            }
        )
        adapter.on_raw_event(
            {
                "type": "bar",
                "instrument": "NQ",
                "timeframe": "1m",
                "ts": "2026-01-02T09:31:00-05:00",
                "open": 100.5,
                "high": 101,
                "low": 100,
                "close": 100.75,
                "volume": 10,
                "complete": False,
                "source": "test",
            }
        )
        health = adapter.health()
        assert len(emitted) == 1
        assert health.completed_bars == 1
        assert health.incomplete_bars == 1
        assert store.read_bars("NQ", "1m")[0].close == 100.5
    finally:
        tmp.cleanup()


def test_persisted_live_feed_tracks_duplicate_out_of_order_missing_and_stale():
    tmp, store = make_store()
    try:
        now = [datetime(2026, 1, 2, 14, 30, 0)]

        def clock():
            return now[0]

        adapter = PersistedLiveFeedAdapter(store, stale_after_seconds=10, clock=clock)
        base = {
            "type": "bar",
            "instrument": "NQ",
            "timeframe": "1m",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 1,
            "complete": True,
            "source": "test",
        }
        adapter.on_raw_event(dict(base, ts="2026-01-02T09:30:00-05:00"))
        adapter.on_raw_event(dict(base, ts="2026-01-02T09:30:00-05:00"))
        adapter.on_raw_event(dict(base, ts="2026-01-02T09:29:00-05:00"))
        adapter.on_raw_event(dict(base, ts="2026-01-02T09:33:00-05:00"))
        now[0] = now[0] + timedelta(seconds=11)
        health = adapter.health()
        assert health.duplicate_bars == 1
        assert health.out_of_order_bars == 1
        assert health.missing_bars == 2
        assert health.stale
    finally:
        tmp.cleanup()


def test_compare_csv_for_replay_parity_reports_field_mismatch(tmp_path):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    left.write_text("intent_id,side,quantity\nintent_1,buy,1\n", encoding="utf-8")
    right.write_text("intent_id,side,quantity\nintent_1,sell,1\n", encoding="utf-8")
    mismatches = compare_csv_for_replay_parity(left, right, "intent_id", ["side", "quantity"])
    assert len(mismatches) == 1
    assert mismatches[0].field == "side"
