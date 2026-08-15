"""Empty dynamic_sizing_events must not bypass prior_opposite_only."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pytz

from potions.live.models import StrategyInstance, as_row
from potions.live.store import FlatFileStore
from potions.live.strategies.v2b_scaleout import V2BScaleoutStrategy

NY = pytz.timezone("America/New_York")


def _plugin(**cfg) -> V2BScaleoutStrategy:
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    inst = StrategyInstance(
        strategy_id="test_prior_opp",
        strategy_type="v2b_scaleout",
        version="v1",
        instrument="US30",
        broker_instrument="US30",
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=1,
        max_open_orders=16,
        config_json=json.dumps(cfg),
    )
    store.write_table("strategy_instances", [as_row(inst)])
    plugin = V2BScaleoutStrategy(store, inst)
    plugin._tmp = tmp  # keep alive for test duration
    return plugin


class TestPriorOppositeEmptyEventsGate(unittest.TestCase):
    def test_empty_events_blocks_when_prior_opposite_only(self):
        plugin = _plugin(
            entry_qty=1,
            tp1_qty=0,
            tp2_qty=0,
            prior_opposite_only=True,
            dynamic_sizing_events={},
        )
        ts = NY.localize(datetime(2026, 8, 12, 4, 0)).isoformat()
        self.assertIsNone(plugin._sizing_for_entry(ts, "Long"))
        self.assertIsNone(plugin._sizing_for_entry(ts, "Short"))
        plugin._tmp.cleanup()

    def test_prior_event_allows_opposite_side_only(self):
        events = {
            "2026-08-12": [
                {
                    "ts": "2026-08-12T03:30:00-04:00",
                    "available_at_ts": "2026-08-12T03:30:00-04:00",
                    "side": "long",
                }
            ]
        }
        plugin = _plugin(
            entry_qty=1,
            tp1_qty=0,
            tp2_qty=0,
            prior_opposite_only=True,
            prior_opposite_entry_qty=1,
            prior_opposite_tp1_qty=0,
            prior_opposite_tp2_qty=0,
            dynamic_sizing_events=events,
        )
        ts = NY.localize(datetime(2026, 8, 12, 4, 0)).isoformat()
        self.assertIsNotNone(plugin._sizing_for_entry(ts, "Short"))
        self.assertIsNone(plugin._sizing_for_entry(ts, "Long"))
        plugin._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
