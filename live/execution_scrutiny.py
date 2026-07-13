from __future__ import annotations

from typing import Any, Dict


OK = "OK"
NEEDS_TICK = "NEEDS_TICK"
VIOLATION_RISK = "VIOLATION_RISK"


def classify_execution_row(row: Dict[str, Any]) -> str:
    """Classify execution certainty for a replay row.

    ``NEEDS_TICK`` means bar data is insufficient, not that the strategy is
    invalid. ``VIOLATION_RISK`` is reserved for causal/order impossibilities and
    should correspond to a CausalViolation.
    """

    if _false(row.get("opposite_gate_known_before_v2b"), default=True):
        return VIOLATION_RISK
    latency_risk = str(row.get("latency_risk") or "")
    if latency_risk and latency_risk != "safe":
        return NEEDS_TICK
    if _truthy(row.get("pre_arm_breakout_touch")):
        return NEEDS_TICK
    return OK


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _false(value: Any, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return not default
    return str(value).strip().lower() in {"0", "false", "no", "n"}

