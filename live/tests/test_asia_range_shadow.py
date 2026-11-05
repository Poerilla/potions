from __future__ import annotations

import tempfile
from pathlib import Path

from potions.live.asia_range_shadow import (
    append_shadow_campaign,
    load_shadow_book,
    load_shadow_meta,
    mark_shadow_session_evaluated,
    save_shadow_book,
    shadow_observation_sessions,
)


def test_shadow_campaign_append_is_session_idempotent_and_preserves_seed_meta():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shadow_campaigns.json"
        save_shadow_book(path, [1.0, -2.0], meta={"seed": "fixture"})
        first = append_shadow_campaign(
            path,
            3.0,
            session_date="2026-11-02",
            source="candle_sim_unfiltered",
        )
        second = append_shadow_campaign(
            path,
            999.0,
            session_date="2026-11-02",
            source="duplicate",
        )
        assert first == [1.0, -2.0, 3.0]
        assert second == first
        assert load_shadow_book(path) == first
        assert shadow_observation_sessions(path) == ["2026-11-02"]
        meta = load_shadow_meta(path) or {}
        assert meta["seed"] == "fixture"
        assert meta["observation_count"] == 3


def test_no_campaign_evaluation_does_not_change_roll_observation_count():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shadow_campaigns.json"
        save_shadow_book(path, [1.0, -2.0], meta={"seed": "fixture"})
        mark_shadow_session_evaluated(
            path,
            "2026-11-03",
            source="candle_sim_unfiltered",
            outcome="no_campaign",
        )
        assert load_shadow_book(path) == [1.0, -2.0]
        meta = load_shadow_meta(path) or {}
        assert meta["evaluated_sessions"] == ["2026-11-03"]
        assert meta["last_evaluated_outcome"] == "no_campaign"
