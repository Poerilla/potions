from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from .models import Bar, CausalViolation, FeatureSnapshot, OrderIntent, StrategyInstance, as_row, new_id, utc_now_iso
from .store import FlatFileStore


AUDIT = "audit"
STRICT = "strict"
OK = "OK"
VIOLATION_RISK = "VIOLATION_RISK"


class CausalityError(ValueError):
    pass


@dataclass(frozen=True)
class CausalityDecision:
    allowed: bool
    violations: List[CausalViolation]


class CausalityGuard:
    """Point-in-time guard for feature availability and order activation.

    The guard is intentionally provider-neutral. Strategies can opt into rich
    feature snapshots immediately, while the order activation check protects the
    current StrategyPlugin path without requiring strategy rewrites.
    """

    def __init__(self, store: FlatFileStore, mode: str = AUDIT):
        if mode not in {AUDIT, STRICT}:
            raise ValueError("causality mode must be %s or %s" % (AUDIT, STRICT))
        self.store = store
        self.mode = mode

    @property
    def strict(self) -> bool:
        return self.mode == STRICT

    def record_features(self, features: Iterable[FeatureSnapshot], current_bar: Bar) -> List[CausalViolation]:
        features = list(features)
        if features:
            self.store.append_rows("feature_snapshots", [as_row(item) for item in features])
        violations: List[CausalViolation] = []
        for feature in features:
            violations.extend(self.validate_feature(feature, current_bar))
        self._persist_violations(violations)
        return violations

    def validate_feature(self, feature: FeatureSnapshot, current_bar: Bar) -> List[CausalViolation]:
        violations: List[CausalViolation] = []
        event_ts = _parse_ts(feature.event_ts)
        available_at = _parse_ts(feature.available_at_ts)
        bar_ts = _parse_ts(feature.current_bar_ts or current_bar.ts)
        actual_bar_ts = _parse_ts(current_bar.ts)

        if event_ts is None or available_at is None or bar_ts is None:
            violations.append(
                self._violation(
                    strategy_id=feature.strategy_id,
                    instrument=feature.instrument,
                    violation_type="feature_timestamp_missing",
                    current_bar_ts=current_bar.ts,
                    offending_ts=feature.available_at_ts or feature.event_ts,
                    feature_name=feature.feature_name,
                    details={"event_ts": feature.event_ts, "available_at_ts": feature.available_at_ts},
                )
            )
            return violations

        if _gt(event_ts, available_at):
            violations.append(
                self._violation(
                    strategy_id=feature.strategy_id,
                    instrument=feature.instrument,
                    violation_type="event_after_available_at",
                    current_bar_ts=current_bar.ts,
                    offending_ts=feature.event_ts,
                    feature_name=feature.feature_name,
                    details={"available_at_ts": feature.available_at_ts},
                )
            )
        if _gt(available_at, actual_bar_ts) or _gt(bar_ts, actual_bar_ts):
            violations.append(
                self._violation(
                    strategy_id=feature.strategy_id,
                    instrument=feature.instrument,
                    violation_type="feature_available_after_current_bar",
                    current_bar_ts=current_bar.ts,
                    offending_ts=feature.available_at_ts,
                    feature_name=feature.feature_name,
                    details={"feature_current_bar_ts": feature.current_bar_ts},
                )
            )
        return violations

    def validate_order_intent(
        self,
        instance: StrategyInstance,
        intent: OrderIntent,
        current_bar: Optional[Bar],
    ) -> CausalityDecision:
        if current_bar is None or intent.reduce_only:
            return CausalityDecision(True, [])
        violations: List[CausalViolation] = []
        if intent.live_after_ts:
            live_after = _parse_ts(intent.live_after_ts)
            bar_ts = _parse_ts(current_bar.ts)
            if live_after is None or bar_ts is None:
                violations.append(
                    self._violation(
                        strategy_id=intent.strategy_id,
                        instrument=intent.instrument,
                        violation_type="order_live_after_unparseable",
                        current_bar_ts=current_bar.ts,
                        offending_ts=intent.live_after_ts,
                        intent_id=intent.intent_id,
                        details={"order_type": intent.order_type, "reason": intent.reason},
                    )
                )
            elif _lt(live_after, bar_ts):
                violations.append(
                    self._violation(
                        strategy_id=intent.strategy_id,
                        instrument=intent.instrument,
                        violation_type="order_activation_before_current_bar",
                        current_bar_ts=current_bar.ts,
                        offending_ts=intent.live_after_ts,
                        intent_id=intent.intent_id,
                        details={
                            "order_type": intent.order_type,
                            "reason": intent.reason,
                            "instance_strategy_id": instance.strategy_id,
                        },
                    )
                )
        self._persist_violations(violations)
        return CausalityDecision(not (self.strict and violations), violations)

    def _violation(
        self,
        strategy_id: str,
        instrument: str,
        violation_type: str,
        current_bar_ts: str,
        offending_ts: str,
        feature_name: str = "",
        intent_id: str = "",
        details: Optional[dict] = None,
    ) -> CausalViolation:
        return CausalViolation(
            violation_id=new_id("causal"),
            strategy_id=strategy_id,
            instrument=instrument,
            violation_type=violation_type,
            current_bar_ts=str(current_bar_ts),
            offending_ts=str(offending_ts),
            severity="error",
            action_taken="blocked" if self.strict else "recorded",
            feature_name=feature_name,
            intent_id=intent_id,
            scrutiny_classification=VIOLATION_RISK,
            details_json=json.dumps(details or {}, sort_keys=True),
            created_at=utc_now_iso(),
        )

    def _persist_violations(self, violations: Iterable[CausalViolation]) -> None:
        rows = [as_row(item) for item in violations]
        if not rows:
            return
        self.store.append_rows("causality_violations", rows)
        for row in rows:
            self.store.append_event("causality_violations", row)


def _parse_ts(value: str) -> Optional[datetime]:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw + "T00:00:00")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _lt(left: datetime, right: datetime) -> bool:
    return left < right


def _gt(left: datetime, right: datetime) -> bool:
    return left > right

