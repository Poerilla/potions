from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from ..models import FeatureSnapshot, StrategyInstance


def feature_snapshot(
    instance: StrategyInstance,
    feature_name: str,
    current_bar_ts: str,
    *,
    event_ts: Optional[str] = None,
    available_at_ts: Optional[str] = None,
    source: str = "",
    value_ref: str = "",
    metadata: Optional[Mapping[str, Any]] = None,
) -> FeatureSnapshot:
    """Create a compact point-in-time feature audit record.

    Strategies should call this at the moment a completed-bar decision is made.
    ``event_ts`` is the source event's timestamp; ``available_at_ts`` is when
    that source became usable by the strategy. Both default to the current bar
    timestamp for features derived directly from the completed bar.
    """

    ts = str(current_bar_ts)
    return FeatureSnapshot(
        feature_name=feature_name,
        strategy_id=instance.strategy_id,
        instrument=instance.instrument,
        event_ts=str(event_ts or ts),
        available_at_ts=str(available_at_ts or ts),
        current_bar_ts=ts,
        source=source,
        value_ref=str(value_ref),
        metadata_json=json.dumps(dict(metadata or {}), sort_keys=True, default=str),
    )
