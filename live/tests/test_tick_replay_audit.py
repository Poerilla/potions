from __future__ import annotations

from potions.live.tick_replay_audit import adverse_synthetic_path, bar_replay_outcome, bracket_outcome_on_path


def test_adverse_long_path_hits_stop_before_target():
    path = adverse_synthetic_path("long", 100.0, 105.0, 97.0, 103.0)
    outcome = bracket_outcome_on_path(path, side="long", stop_price=98.0, target_price=104.0)
    assert outcome == "stop"


def test_bar_replay_stop_first_when_both_touch():
    outcome = bar_replay_outcome(side="long", stop_price=98.0, target_price=104.0, o=100.0, h=105.0, l=97.0)
    assert outcome == "stop"
