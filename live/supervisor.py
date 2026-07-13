from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .models import OrderIntent, utc_now_iso
from .store import FlatFileStore


RUNNING = "running"
ENTRY_FROZEN = "entry_frozen"
RECONCILING = "reconciling"
EMERGENCY_FLATTEN = "emergency_flatten"
BLOCKED = "blocked"


@dataclass(frozen=True)
class RuntimeFault:
    event: str
    reason: str
    provider: str = ""
    severity: str = "warning"
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: str = ""

    def row(self) -> Dict[str, Any]:
        out = asdict(self)
        out["ts"] = self.ts or utc_now_iso()
        return out


@dataclass(frozen=True)
class RuntimeStatus:
    mode: str
    reason: str = ""
    provider: str = ""
    updated_at: str = ""
    last_reconciliation_at: str = ""


class RuntimeSupervisor:
    """Provider-neutral operational state gate.

    The broker/feed adapter owns connectivity and reconciliation details; this
    supervisor owns the simple runtime contract used by strategies and risk:
    new entries require ``running`` but reduce-only exits remain allowed.
    """

    def __init__(
        self,
        store: FlatFileStore,
        provider: str = "",
        heartbeat_freeze_ms: int = 1000,
        order_ambiguity_ms: int = 4000,
    ):
        self.store = store
        self.store.ensure()
        self.provider = provider
        self.heartbeat_freeze_ms = int(heartbeat_freeze_ms)
        self.order_ambiguity_ms = int(order_ambiguity_ms)
        existing = self.store.read_json("runtime_status.json")
        self._status = RuntimeStatus(
            mode=str(existing.get("mode") or RUNNING),
            reason=str(existing.get("reason") or ""),
            provider=str(existing.get("provider") or provider),
            updated_at=str(existing.get("updated_at") or utc_now_iso()),
            last_reconciliation_at=str(existing.get("last_reconciliation_at") or ""),
        )
        self._persist()

    @property
    def mode(self) -> str:
        return self._status.mode

    def status(self) -> RuntimeStatus:
        return self._status

    def entries_allowed(self, intent: Optional[OrderIntent] = None) -> bool:
        if intent is not None and intent.reduce_only:
            return True
        return self._status.mode == RUNNING

    def block_reason(self, intent: Optional[OrderIntent] = None) -> str:
        if self.entries_allowed(intent):
            return "ok"
        return self._status.reason or self._status.mode

    def mark_running(self, reason: str = "reconciled") -> RuntimeStatus:
        return self._set_mode(RUNNING, reason)

    def freeze_entries(self, reason: str, payload: Optional[Dict[str, Any]] = None) -> RuntimeStatus:
        self._fault("entry_frozen", reason, "warning", payload)
        return self._set_mode(ENTRY_FROZEN, reason)

    def start_reconciliation(self, reason: str, payload: Optional[Dict[str, Any]] = None) -> RuntimeStatus:
        self._fault("reconciling", reason, "warning", payload)
        return self._set_mode(RECONCILING, reason)

    def mark_reconciled(self, reason: str = "broker_state_reconciled") -> RuntimeStatus:
        self._append_reconciliation_event({"event": "reconciled", "reason": reason})
        self._status = RuntimeStatus(
            mode=RUNNING,
            reason=reason,
            provider=self.provider,
            updated_at=utc_now_iso(),
            last_reconciliation_at=utc_now_iso(),
        )
        self._persist()
        return self._status

    def trigger_emergency_flatten(self, reason: str, payload: Optional[Dict[str, Any]] = None) -> RuntimeStatus:
        self._fault("emergency_flatten", reason, "critical", payload)
        return self._set_mode(EMERGENCY_FLATTEN, reason)

    def block(self, reason: str, payload: Optional[Dict[str, Any]] = None) -> RuntimeStatus:
        self._fault("blocked", reason, "critical", payload)
        return self._set_mode(BLOCKED, reason)

    def observe_heartbeat_age(self, age_ms: float, source: str = "") -> RuntimeStatus:
        if float(age_ms) > self.heartbeat_freeze_ms:
            return self.freeze_entries(
                "heartbeat_missing_over_%dms" % self.heartbeat_freeze_ms,
                {"age_ms": float(age_ms), "source": source},
            )
        return self._status

    def observe_order_ambiguity_age(self, age_ms: float, order_ref: str = "") -> RuntimeStatus:
        if float(age_ms) > self.order_ambiguity_ms:
            return self.block(
                "order_ambiguity_over_%dms" % self.order_ambiguity_ms,
                {"age_ms": float(age_ms), "order_ref": order_ref},
            )
        return self.freeze_entries("order_ambiguity_pending", {"age_ms": float(age_ms), "order_ref": order_ref})

    def _set_mode(self, mode: str, reason: str) -> RuntimeStatus:
        self._status = RuntimeStatus(mode=mode, reason=reason, provider=self.provider, updated_at=utc_now_iso())
        self._persist()
        return self._status

    def _persist(self) -> None:
        self.store.write_json(
            "runtime_status.json",
            {
                "mode": self._status.mode,
                "reason": self._status.reason,
                "provider": self._status.provider,
                "updated_at": self._status.updated_at,
                "last_reconciliation_at": self._status.last_reconciliation_at,
                "heartbeat_freeze_ms": self.heartbeat_freeze_ms,
                "order_ambiguity_ms": self.order_ambiguity_ms,
            },
        )

    def _fault(
        self,
        event: str,
        reason: str,
        severity: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        fault = RuntimeFault(
            event=event,
            reason=reason,
            provider=self.provider,
            severity=severity,
            payload=payload or {},
            ts=utc_now_iso(),
        )
        self.store.append_event("runtime_faults", fault.row())

    def _append_reconciliation_event(self, payload: Dict[str, Any]) -> None:
        self.store.append_event("reconciliation_events", dict(payload, provider=self.provider))


def elapsed_ms_since(ts: str, now: Optional[datetime] = None) -> float:
    if not ts:
        return 0.0
    raw = str(ts)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        left = datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    right = now or datetime.utcnow()
    if right.tzinfo is None and left.tzinfo is not None:
        right = right.replace(tzinfo=left.tzinfo)
    return max(0.0, (right - left).total_seconds() * 1000.0)
