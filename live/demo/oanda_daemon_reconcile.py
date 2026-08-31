"""OANDA daemon containment: bracket invariants, hard reconcile, FLAT_FOR_DAY.

Implements the strategy-local containment path:

  Broker truth → ownership → bracket coverage → entry permission
  → continuous reconcile → freeze / flatten-for-day.

Default mode is ``shadow`` (detect + log; no broker mutate / supervisor freeze).
Set ``POTIONS_OANDA_CONTAINMENT=live`` to enforce.

Emails: one **NY EOD digest** per demo per session (default). Immediate emails were
too noisy under ~2m watchdog. Override with ``POTIONS_OANDA_CONTAINMENT_EMAIL=eod|off|immediate``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import pytz

from ..models import BrokerOrder, Position, utc_now_iso
from ..oanda import OandaBroker
from ..store import FlatFileStore
from ..supervisor import (
    ENTRY_FROZEN,
    FLAT_FOR_DAY,
    RuntimeSupervisor,
)

NY_TZ = pytz.timezone("America/New_York")

# Watchdog / hard-reconcile cadences (seconds).
BRACKET_WATCHDOG_SECONDS = 120.0  # 1–5m exposed-position watchdog (default 2m)
HARD_RECONCILE_SECONDS = 900.0  # 15m daemon sweep
# Aug 14 hung-stream missed entries: pid alive but ticks frozen ~4h. Disarm well before that.
STREAM_STALE_SECONDS = 180.0  # no account/price heartbeat while armed → DISARMED / entry freeze

DAEMON_STATE_FILE = "daemon_strategy_state.json"
FLAT_FOR_DAY_FILE = "FLAT_FOR_DAY.json"
CONTAINMENT_EMAIL_DIGEST_FILE = "containment_email_digest.json"
# After this NY wall time, flush at most one digest email per session_date.
CONTAINMENT_EMAIL_EOD_HHMM = (16, 0)
CONTAINMENT_EMAIL_DIGEST_MAX_EVENTS = 40

# Persisted daemon lifecycle (subset of the full containment machine).
DISARMED = "DISARMED"
STARTUP_RECONCILING = "STARTUP_RECONCILING"
ARMED_FLAT = "ARMED_FLAT"
ENTRY_PENDING = "ENTRY_PENDING"
POSITION_OPEN_BRACKET_PENDING = "POSITION_OPEN_BRACKET_PENDING"
POSITION_PROTECTED = "POSITION_PROTECTED"
EXIT_PENDING = "EXIT_PENDING"
RECOVERY_RECONCILING = "RECOVERY_RECONCILING"
STATE_FLAT_FOR_DAY = "FLAT_FOR_DAY"
HALTED_MANUAL = "HALTED_MANUAL"

WORKING_STATUSES = frozenset({"submitted", "partially_filled", "working", "pendingnew"})

# Protective coverage while open (entry arms are NOT stop coverage).
_PROTECTIVE_STOP_ROLES = frozenset({"stop", "wide_stop", "runner_stop", "protective_stop", "sl"})
# Intentional resting entries while flat (ST+PMC LIMIT / v2b OCO STOP) — not orphans.
_ENTRY_ROLES = frozenset({"entry"})
# Back-compat alias used by older call sites / tests.
_STOP_ROLES = _PROTECTIVE_STOP_ROLES | _ENTRY_ROLES
_TP_ROLES = frozenset({"tp1", "tp2", "target", "take_profit", "runner_target"})
_PROTECTIVE_ORDER_TYPES = frozenset({"stop_loss", "take_profit", "trailing_stop_loss", "guaranteed_stop_loss"})


@dataclass(frozen=True)
class BracketExpectation:
    """What protective coverage a book owes while non-flat."""

    require_stop: bool = True
    require_tp: bool = True
    allow_runner_no_tp: bool = False
    entry_qty: float = 0.0
    strategy_type: str = ""


def expectation_for_strategy_type(strategy_type: str, *, entry_qty: float = 0.0) -> BracketExpectation:
    key = str(strategy_type or "").strip().lower()
    if key in {"v2b_scaleout", "v2b"}:
        # Full size expects stop + at least one TP; post-scale-out residual may be stop-only.
        return BracketExpectation(
            require_stop=True,
            require_tp=True,
            allow_runner_no_tp=True,
            entry_qty=float(entry_qty or 3.0),
            strategy_type=key,
        )
    if "st_pmc" in key or "hourly_st" in key:
        return BracketExpectation(
            require_stop=True,
            require_tp=True,
            allow_runner_no_tp=False,
            entry_qty=float(entry_qty or 0.0),
            strategy_type=key,
        )
    if "monday_or" in key or key.endswith("_or"):
        return BracketExpectation(
            require_stop=True,
            require_tp=True,
            allow_runner_no_tp=False,
            entry_qty=float(entry_qty or 0.0),
            strategy_type=key,
        )
    return BracketExpectation(
        require_stop=True,
        require_tp=True,
        allow_runner_no_tp=False,
        entry_qty=float(entry_qty or 0.0),
        strategy_type=key,
    )


@dataclass
class BracketInvariantResult:
    ok: bool
    classification: str  # ok | armed_entry | stop_only | open_without_brackets | orphan_protective | cross_book_entry | foreign_bleed | qty_mismatch
    ownership_certain: bool
    local_qty: float
    stop_qty: float
    tp_qty: float
    working_roles: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    recommended_action: str = "none"  # none | freeze_entries | flat_for_day | cancel_orphans

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContainmentCycleResult:
    mode: str
    phase: str
    state: str
    invariant: Optional[BracketInvariantResult]
    actions: List[str] = field(default_factory=list)
    shadow: bool = True
    flat_for_day: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        if self.invariant is not None:
            out["invariant"] = self.invariant.as_dict()
        return out


def containment_mode() -> str:
    raw = (os.environ.get("POTIONS_OANDA_CONTAINMENT") or "shadow").strip().lower()
    if raw in {"live", "enforce", "active"}:
        return "live"
    return "shadow"


def containment_email_mode() -> str:
    """How often containment emails fire: ``eod`` (default), ``off``, or ``immediate``."""
    raw = (os.environ.get("POTIONS_OANDA_CONTAINMENT_EMAIL") or "eod").strip().lower()
    if raw in {"off", "none", "0", "false", "no"}:
        return "off"
    if raw in {"immediate", "now", "each", "every"}:
        return "immediate"
    return "eod"


def ny_session_date(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now(tz=NY_TZ)
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    return dt.astimezone(NY_TZ).date().isoformat()


def ny_now(now: Optional[datetime] = None) -> datetime:
    dt = now or datetime.now(tz=NY_TZ)
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    return dt.astimezone(NY_TZ)


def ny_past_containment_email_eod(now: Optional[datetime] = None) -> bool:
    dt = ny_now(now)
    hh, mm = CONTAINMENT_EMAIL_EOD_HHMM
    return (dt.hour, dt.minute) >= (hh, mm)


def _is_working(order: Any) -> bool:
    status = str(getattr(order, "status", None) or (order.get("status") if isinstance(order, dict) else "") or "").lower()
    return status in WORKING_STATUSES


def _order_field(order: Any, name: str, default: Any = "") -> Any:
    if isinstance(order, dict):
        return order.get(name, default)
    return getattr(order, name, default)


def _position_qty(positions: Iterable[Any], *, instrument: str, strategy_ids: Optional[Set[str]] = None) -> float:
    inst = str(instrument or "").upper()
    total = 0.0
    for pos in positions:
        p_inst = str(_order_field(pos, "instrument") or "").upper()
        if p_inst != inst:
            continue
        sid = str(_order_field(pos, "strategy_id") or "")
        if strategy_ids is not None and sid and sid not in strategy_ids and sid != "oanda":
            continue
        total += float(_order_field(pos, "quantity") or 0.0)
    return total


def _working_orders(orders: Iterable[Any], *, instrument: str, strategy_id: str) -> List[Any]:
    inst = str(instrument or "").upper()
    sid = str(strategy_id or "")
    out: List[Any] = []
    for order in orders:
        if not _is_working(order):
            continue
        if str(_order_field(order, "instrument") or "").upper() != inst:
            continue
        if sid and str(_order_field(order, "strategy_id") or "") not in {"", sid}:
            continue
        out.append(order)
    return out


def _role_of(order: Any) -> str:
    role = str(_order_field(order, "bracket_role") or "").strip().lower()
    if role:
        return role
    otype = str(_order_field(order, "order_type") or "").strip().lower()
    reduce_only = str(_order_field(order, "reduce_only") or "").lower() in {"1", "true", "yes"}
    if otype in {"stop", "stop_loss"} and reduce_only:
        return "stop"
    if otype in {"limit", "take_profit"} and reduce_only:
        return "target"
    return otype or "unknown"


def _qty_of(order: Any) -> float:
    rem = _order_field(order, "remaining_quantity", None)
    if rem is not None and str(rem) != "":
        try:
            return abs(float(rem))
        except (TypeError, ValueError):
            pass
    try:
        return abs(float(_order_field(order, "quantity") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _is_true_protective(order: Any) -> bool:
    """True SL/TP / reduce-only — not intentional entry arms."""
    role = _role_of(order)
    otype = str(_order_field(order, "order_type") or "").lower()
    reduce_only = str(_order_field(order, "reduce_only") or "").lower() in {"1", "true", "yes"}
    if role in _ENTRY_ROLES:
        return False
    if role in (_PROTECTIVE_STOP_ROLES | _TP_ROLES):
        return True
    if otype in _PROTECTIVE_ORDER_TYPES:
        return True
    # Untagged working stop while flat is treated as leftover protective (not entry OCO).
    if otype == "stop":
        return True
    if reduce_only:
        return True
    return False


def _is_entry_arm(order: Any) -> bool:
    role = _role_of(order)
    if role in _ENTRY_ROLES:
        return True
    # Untagged working LIMIT while flat is treated as an entry arm (ST+PMC style).
    otype = str(_order_field(order, "order_type") or "").lower()
    if role in {"", "none"} and otype == "limit":
        return True
    return False


def evaluate_bracket_invariant(
    *,
    instrument: str,
    strategy_id: str,
    positions: Sequence[Any],
    orders: Sequence[Any],
    expectation: Optional[BracketExpectation] = None,
    broker_qty: Optional[float] = None,
    account_instrument_qty: Optional[float] = None,
) -> BracketInvariantResult:
    """Classify local (and optional broker) exposure vs protective coverage.

    Used both by the live daemon watchdog and by curated fault fixtures.

    Flat books with intentional ``bracket_role=entry`` rests are ``armed_entry`` /
    ``ok``, not ``orphan_protective``. True SL/TP leftovers remain orphans.
    When this strategy is flat but the shared account already holds the focus
    instrument, resting entries are ``cross_book_entry``.
    """
    expectation = expectation or BracketExpectation()
    local_qty = _position_qty(positions, instrument=instrument, strategy_ids={strategy_id, "oanda"})
    working = _working_orders(orders, instrument=instrument, strategy_id=strategy_id)
    roles = [_role_of(o) for o in working]
    tp_qty = sum(_qty_of(o) for o in working if _role_of(o) in _TP_ROLES)
    # While open, working STOP orders count as coverage even if bracket_role=entry
    # (Aug 13 stop_only books tagged the live protective as entry). LIMIT entry arms do not.
    stop_qty = sum(
        _qty_of(o)
        for o in working
        if _role_of(o) in _PROTECTIVE_STOP_ROLES
        or str(_order_field(o, "order_type") or "").lower() in ({"stop"} | _PROTECTIVE_ORDER_TYPES)
    )

    reasons: List[str] = []
    ownership_certain = True
    classification = "ok"
    recommended = "none"

    if broker_qty is not None and abs(float(broker_qty) - float(local_qty)) > 1e-9:
        reasons.append("local_qty=%s broker_qty=%s" % (local_qty, broker_qty))
        ownership_certain = False
        classification = "qty_mismatch"
        recommended = "flat_for_day"
        return BracketInvariantResult(
            ok=False,
            classification=classification,
            ownership_certain=ownership_certain,
            local_qty=local_qty,
            stop_qty=stop_qty,
            tp_qty=tp_qty,
            working_roles=roles,
            reasons=reasons,
            recommended_action=recommended,
        )

    abs_qty = abs(float(local_qty))
    if abs_qty < 1e-9:
        protectiveish = [o for o in working if _is_true_protective(o)]
        entry_arms = [o for o in working if _is_entry_arm(o) and not _is_true_protective(o)]
        if protectiveish:
            reasons.append("flat_with_working_protectives=%d" % len(protectiveish))
            return BracketInvariantResult(
                ok=False,
                classification="orphan_protective",
                ownership_certain=True,
                local_qty=local_qty,
                stop_qty=stop_qty,
                tp_qty=tp_qty,
                working_roles=roles,
                reasons=reasons,
                recommended_action="cancel_orphans",
            )
        if entry_arms and account_instrument_qty is not None and abs(float(account_instrument_qty)) > 1e-9:
            reasons.append(
                "flat_with_entry_arms=%d account_instrument_qty=%s" % (len(entry_arms), account_instrument_qty)
            )
            return BracketInvariantResult(
                ok=False,
                classification="cross_book_entry",
                ownership_certain=True,
                local_qty=local_qty,
                stop_qty=stop_qty,
                tp_qty=tp_qty,
                working_roles=roles,
                reasons=reasons,
                recommended_action="cancel_orphans",
            )
        if entry_arms:
            reasons.append("armed_entry_orders=%d" % len(entry_arms))
            return BracketInvariantResult(
                ok=True,
                classification="armed_entry",
                ownership_certain=True,
                local_qty=local_qty,
                stop_qty=stop_qty,
                tp_qty=tp_qty,
                working_roles=roles,
                reasons=reasons,
                recommended_action="none",
            )
        return BracketInvariantResult(
            ok=True,
            classification="ok",
            ownership_certain=True,
            local_qty=local_qty,
            stop_qty=stop_qty,
            tp_qty=tp_qty,
            working_roles=roles,
            reasons=[],
            recommended_action="none",
        )

    # Non-flat: require stop coverage; TP unless runner-allowed and size is residual (< entry).
    has_stop = stop_qty + 1e-9 >= abs_qty
    has_tp = tp_qty > 1e-9
    entry_qty = float(expectation.entry_qty or 0.0)
    is_residual_runner = bool(expectation.allow_runner_no_tp) and entry_qty > 0 and abs_qty + 1e-9 < entry_qty
    runner_ok = is_residual_runner and has_stop and not has_tp
    # Heuristic: full-size open (entry_qty-sized) with only stop → stop_only flag (Aug 13).
    if expectation.require_stop and not has_stop and not has_tp:
        classification = "open_without_brackets"
        reasons.append("open_qty=%s with no working stop/tp" % local_qty)
        recommended = "freeze_entries" if ownership_certain else "flat_for_day"
        return BracketInvariantResult(
            ok=False,
            classification=classification,
            ownership_certain=ownership_certain,
            local_qty=local_qty,
            stop_qty=stop_qty,
            tp_qty=tp_qty,
            working_roles=roles,
            reasons=reasons,
            recommended_action=recommended,
        )
    if expectation.require_stop and not has_stop:
        classification = "open_without_brackets"
        reasons.append("open_qty=%s missing stop coverage (stop_qty=%s)" % (local_qty, stop_qty))
        recommended = "freeze_entries"
        return BracketInvariantResult(
            ok=False,
            classification=classification,
            ownership_certain=ownership_certain,
            local_qty=local_qty,
            stop_qty=stop_qty,
            tp_qty=tp_qty,
            working_roles=roles,
            reasons=reasons,
            recommended_action=recommended,
        )
    if expectation.require_tp and not has_tp and not runner_ok:
        classification = "stop_only"
        reasons.append("open_qty=%s stop_only (tp_qty=0)" % local_qty)
        recommended = "freeze_entries"
        return BracketInvariantResult(
            ok=False,
            classification=classification,
            ownership_certain=True,
            local_qty=local_qty,
            stop_qty=stop_qty,
            tp_qty=tp_qty,
            working_roles=roles,
            reasons=reasons,
            recommended_action=recommended,
        )
    return BracketInvariantResult(
        ok=True,
        classification="ok",
        ownership_certain=True,
        local_qty=local_qty,
        stop_qty=stop_qty,
        tp_qty=tp_qty,
        working_roles=roles,
        reasons=[],
        recommended_action="none",
    )


def detect_foreign_bleed(
    positions: Sequence[Any],
    *,
    focus_instrument: str,
    strategy_id: str,
) -> BracketInvariantResult:
    """Flag strategy-owned rows on instruments outside the demo focus (shared-account bleed)."""
    focus = str(focus_instrument or "").upper()
    foreign: List[str] = []
    for pos in positions:
        qty = float(_order_field(pos, "quantity") or 0.0)
        if abs(qty) < 1e-9:
            continue
        inst = str(_order_field(pos, "instrument") or "").upper()
        sid = str(_order_field(pos, "strategy_id") or "")
        if inst != focus and sid in {strategy_id, "oanda"}:
            foreign.append("%s:%s" % (inst, qty))
    if not foreign:
        return BracketInvariantResult(
            ok=True,
            classification="ok",
            ownership_certain=True,
            local_qty=0.0,
            stop_qty=0.0,
            tp_qty=0.0,
            working_roles=[],
            reasons=[],
            recommended_action="none",
        )
    return BracketInvariantResult(
        ok=False,
        classification="foreign_bleed",
        ownership_certain=False,
        local_qty=0.0,
        stop_qty=0.0,
        tp_qty=0.0,
        working_roles=[],
        reasons=foreign,
        recommended_action="flat_for_day",
    )


def load_daemon_state(store: FlatFileStore) -> Dict[str, Any]:
    raw = store.read_json(DAEMON_STATE_FILE) or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "state": str(raw.get("state") or DISARMED),
        "updated_at": str(raw.get("updated_at") or ""),
        "reason": str(raw.get("reason") or ""),
        "session_date": str(raw.get("session_date") or ""),
        "last_invariant": raw.get("last_invariant") or {},
        "transitions": list(raw.get("transitions") or [])[-50:],
    }


def persist_daemon_state(store: FlatFileStore, state: Dict[str, Any]) -> None:
    store.write_json(DAEMON_STATE_FILE, state)


def transition_daemon_state(
    store: FlatFileStore,
    *,
    new_state: str,
    reason: str,
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cur = load_daemon_state(store)
    if cur.get("state") == new_state and cur.get("reason") == reason:
        return cur
    transitions = list(cur.get("transitions") or [])
    transitions.append(
        {
            "from": cur.get("state"),
            "to": new_state,
            "reason": reason,
            "ts": utc_now_iso(),
            "snapshot": snapshot or {},
        }
    )
    out = {
        "state": new_state,
        "updated_at": utc_now_iso(),
        "reason": reason,
        "session_date": cur.get("session_date") or ny_session_date(),
        "last_invariant": snapshot or cur.get("last_invariant") or {},
        "transitions": transitions[-50:],
    }
    persist_daemon_state(store, out)
    store.append_event(
        "reconciliation_events",
        {"event": "daemon_state_transition", "from": cur.get("state"), "to": new_state, "reason": reason},
    )
    return out


def read_flat_for_day(store: FlatFileStore) -> Optional[Dict[str, Any]]:
    path = store.root / FLAT_FOR_DAY_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_flat_for_day(store: FlatFileStore, payload: Dict[str, Any]) -> Path:
    path = store.root / FLAT_FOR_DAY_FILE
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def clear_flat_for_day_file(store: FlatFileStore) -> None:
    path = store.root / FLAT_FOR_DAY_FILE
    if path.exists():
        path.unlink()


def maybe_clear_flat_for_day_on_session_roll(
    store: FlatFileStore,
    supervisor: Optional[RuntimeSupervisor],
    *,
    session_date: Optional[str] = None,
) -> bool:
    """Clear FLAT_FOR_DAY when NY date rolls past the flag's session_date."""
    flag = read_flat_for_day(store)
    if not flag:
        return False
    today = session_date or ny_session_date()
    flagged_day = str(flag.get("session_date") or "")
    if flagged_day and flagged_day < today:
        clear_flat_for_day_file(store)
        if supervisor is not None:
            supervisor.clear_flat_for_day("ny_session_roll:%s->%s" % (flagged_day, today))
        transition_daemon_state(store, new_state=ARMED_FLAT, reason="flat_for_day_session_roll_clear")
        store.append_event(
            "reconciliation_events",
            {"event": "flat_for_day_cleared", "from_session": flagged_day, "to_session": today},
        )
        return True
    return False


class DaemonContainmentController:
    """Per-demo containment loop (shadow by default)."""

    def __init__(
        self,
        *,
        store: FlatFileStore,
        broker: OandaBroker,
        supervisor: Optional[RuntimeSupervisor],
        instrument: str,
        strategy_id: str,
        strategy_type: str = "v2b_scaleout",
        entry_qty: float = 0.0,
        output_root: Optional[Path] = None,
        mode: Optional[str] = None,
        bracket_watchdog_s: float = BRACKET_WATCHDOG_SECONDS,
        hard_reconcile_s: float = HARD_RECONCILE_SECONDS,
        stream_stale_s: float = STREAM_STALE_SECONDS,
        email_on_action: bool = True,
        clock: Optional[Any] = None,
    ):
        import time as _time

        self.store = store
        self.broker = broker
        self.supervisor = supervisor
        self.instrument = str(instrument).upper()
        self.strategy_id = str(strategy_id)
        self.strategy_type = str(strategy_type or "")
        self.expectation = expectation_for_strategy_type(self.strategy_type, entry_qty=float(entry_qty or 0.0))
        self.output_root = Path(output_root) if output_root is not None else store.root.parent
        self.mode = (mode or containment_mode()).lower()
        self.shadow = self.mode != "live"
        self.bracket_watchdog_s = float(bracket_watchdog_s)
        self.hard_reconcile_s = float(hard_reconcile_s)
        self.stream_stale_s = float(stream_stale_s)
        self.email_on_action = bool(email_on_action)
        self.email_mode = containment_email_mode() if email_on_action else "off"
        self._clock = clock or _time.time
        self._last_watchdog_at = 0.0
        self._last_hard_at = 0.0
        # Fresh at construct so bootstrap is not immediately stream-stale.
        self._last_stream_at = float(self._clock())
        self._stream_stale_latched = False

    def note_stream_activity(self) -> None:
        """Call on every price tick / account heartbeat so stream age stays fresh."""
        self._last_stream_at = float(self._clock())

    def note_stream_reconnected(self) -> ContainmentCycleResult:
        """After stream reconnect: refresh activity, REST hard-reconcile, then rearm if safe."""
        self._last_stream_at = float(self._clock())
        transition_daemon_state(self.store, new_state=RECOVERY_RECONCILING, reason="stream_reconnected")
        result = self.run_cycle(phase="recovery", force=True)
        if (
            result.invariant is not None
            and result.invariant.ok
            and not result.flat_for_day
            and self._stream_stale_latched
            and not self.shadow
            and self.supervisor is not None
            and self.supervisor.mode == ENTRY_FROZEN
            and "stream_stale" in str(self.supervisor.block_reason() or "")
        ):
            self.supervisor.mark_running("stream_reconnected_reconciled")
            self._stream_stale_latched = False
            abs_qty = abs(float(result.invariant.local_qty))
            transition_daemon_state(
                self.store,
                new_state=POSITION_PROTECTED if abs_qty > 1e-9 else ARMED_FLAT,
                reason="stream_reconnected_rearmed",
                snapshot=result.invariant.as_dict(),
            )
            result.actions.append("stream_rearmed")
        elif result.invariant is not None and result.invariant.ok and not result.flat_for_day:
            self._stream_stale_latched = False
            result.actions.append("stream_reconciled_ok")
        return result

    def stream_age_s(self) -> float:
        return max(0.0, float(self._clock()) - float(self._last_stream_at))

    def _stream_stale_invariant(self) -> Optional[BracketInvariantResult]:
        age = self.stream_age_s()
        if age + 1e-9 < float(self.stream_stale_s):
            return None
        return BracketInvariantResult(
            ok=False,
            classification="stream_stale",
            ownership_certain=True,
            local_qty=0.0,
            stop_qty=0.0,
            tp_qty=0.0,
            working_roles=[],
            reasons=["stream_age_s=%.1f threshold=%.1f" % (age, self.stream_stale_s)],
            recommended_action="freeze_entries",
        )

    def bootstrap(self) -> ContainmentCycleResult:
        maybe_clear_flat_for_day_on_session_roll(self.store, self.supervisor)
        self.note_stream_activity()
        transition_daemon_state(self.store, new_state=STARTUP_RECONCILING, reason="bootstrap")
        result = self.run_cycle(phase="startup", force=True)
        flag = read_flat_for_day(self.store)
        if flag and str(flag.get("session_date") or "") == ny_session_date():
            transition_daemon_state(
                self.store,
                new_state=STATE_FLAT_FOR_DAY,
                reason=str(flag.get("reason") or "flat_for_day_persisted"),
                snapshot=flag,
            )
            if self.supervisor is not None and not self.shadow:
                self.supervisor.mark_flat_for_day(str(flag.get("reason") or "flat_for_day_persisted"), flag)
        return result

    def maybe_run(self, *, force: bool = False) -> Optional[ContainmentCycleResult]:
        now = float(self._clock())
        maybe_clear_flat_for_day_on_session_roll(self.store, self.supervisor)
        due_hard = force or (now - self._last_hard_at >= self.hard_reconcile_s)
        due_watch = force or (now - self._last_watchdog_at >= self.bracket_watchdog_s)
        due_stream = self._stream_stale_invariant() is not None
        if not due_hard and not due_watch and not due_stream:
            self._maybe_flush_eod_email()
            return None
        if due_hard:
            phase = "hard_reconcile"
        elif due_stream and not due_watch:
            phase = "stream_watchdog"
        else:
            phase = "bracket_watchdog"
        result = self.run_cycle(phase=phase, force=True)
        self._last_watchdog_at = now
        if due_hard:
            self._last_hard_at = now
        self._maybe_flush_eod_email()
        return result

    def run_cycle(self, *, phase: str, force: bool = False) -> ContainmentCycleResult:
        del force  # cycle is explicit when called
        positions = list(self.broker.reconcile_positions())
        orders = list(self.broker.reconcile_orders())
        # Scope-filtered broker mirrors hide sibling-instrument bleed — read the
        # flat-file store unscoped for shared-account foreign-position checks.
        store_positions = list(self.store.read_table("positions"))
        local_qty_before = _position_qty(
            positions, instrument=self.instrument, strategy_ids={self.strategy_id, "oanda"}
        )
        broker_qty: Optional[float] = None
        account_instrument_qty: Optional[float] = None
        hard_qty_mismatch = False
        # Prefer freshly fetched account when client present (hard phases).
        if phase in {"startup", "hard_reconcile", "recovery"} and self.broker.client is not None:
            try:
                body = self.broker.client.account_details()
                account = body.get("account") or body
                if hasattr(account, "dict"):
                    account = account.dict()
                account = dict(account) if isinstance(account, dict) else {}
                account_instrument_qty = self.broker.instrument_net_qty_from_account(
                    account, instrument=self.instrument
                )
                owned = self.broker._owned_scoped_positions_from_account(  # noqa: SLF001 — intentional
                    account,
                    authority={self.strategy_id},
                )
                broker_qty = sum(
                    float(p.quantity)
                    for p in owned
                    if str(p.instrument or "").upper() == self.instrument
                )
                # Opposite-side or both-nonzero unexplained delta → hard mismatch.
                # One-sided drift (local flat / broker open or ghost local) → soft adopt.
                if broker_qty is not None and abs(float(broker_qty) - float(local_qty_before)) > 1e-9:
                    bq = float(broker_qty)
                    lq = float(local_qty_before)
                    if bq * lq < 0:
                        hard_qty_mismatch = True
                    elif abs(bq) > 1e-9 and abs(lq) > 1e-9:
                        hard_qty_mismatch = True
                if not hard_qty_mismatch:
                    # Soft drift: adopt broker truth into local mirror.
                    self.broker.reconcile_from_account_details(body)
                    positions = list(self.broker.reconcile_positions())
                    orders = list(self.broker.reconcile_orders())
                    store_positions = list(self.store.read_table("positions"))
                    broker_qty = None  # after adopt, bracket check uses local only
                    # Keep account-wide focus qty for cross-book entry detection.
                    account_instrument_qty = self.broker.instrument_net_qty_from_account(
                        account, instrument=self.instrument
                    )
                else:
                    positions = list(self.broker.reconcile_positions())
                    orders = list(self.broker.reconcile_orders())
            except Exception as exc:
                self.store.append_event(
                    "reconciliation_events",
                    {"event": "containment_account_details_error", "error": str(exc), "phase": phase},
                )

        bleed = detect_foreign_bleed(
            store_positions, focus_instrument=self.instrument, strategy_id=self.strategy_id
        )
        if hard_qty_mismatch:
            invariant = evaluate_bracket_invariant(
                instrument=self.instrument,
                strategy_id=self.strategy_id,
                positions=positions,
                orders=orders,
                expectation=self.expectation,
                broker_qty=broker_qty,
                account_instrument_qty=account_instrument_qty,
            )
        else:
            invariant = evaluate_bracket_invariant(
                instrument=self.instrument,
                strategy_id=self.strategy_id,
                positions=positions,
                orders=orders,
                expectation=self.expectation,
                broker_qty=None,
                account_instrument_qty=account_instrument_qty,
            )
        if not bleed.ok:
            invariant = bleed

        stream_inv = self._stream_stale_invariant()
        details: Dict[str, Any] = {"phase": phase, "mode": self.mode, "stream_age_s": self.stream_age_s()}
        if stream_inv is not None and invariant.ok:
            # Healthy book but dead stream (Aug 14 hung-pid missed entries).
            invariant = stream_inv
        elif stream_inv is not None:
            details["also_stream_stale"] = stream_inv.as_dict()

        actions: List[str] = []
        flat_for_day = False

        if invariant.ok:
            abs_qty = abs(float(invariant.local_qty))
            new_state = POSITION_PROTECTED if abs_qty > 1e-9 else ARMED_FLAT
            transition_daemon_state(
                self.store,
                new_state=new_state,
                reason="invariant_ok",
                snapshot=invariant.as_dict(),
            )
            # Still sweep remote entry orphans + flat protectives.
            actions.extend(self._maybe_sweep_orphans(invariant))
            result = ContainmentCycleResult(
                mode=self.mode,
                phase=phase,
                state=new_state,
                invariant=invariant,
                actions=actions,
                shadow=self.shadow,
                flat_for_day=False,
                details=details,
            )
            self._emit(result)
            return result

        # Fault path.
        transition_daemon_state(
            self.store,
            new_state=RECOVERY_RECONCILING,
            reason=invariant.classification,
            snapshot=invariant.as_dict(),
        )
        actions.append("detect:%s" % invariant.classification)

        if invariant.recommended_action == "cancel_orphans":
            actions.extend(self._cancel_orphan_protectives(invariant))
        elif invariant.recommended_action == "freeze_entries":
            actions.extend(self._freeze_for_missing_brackets(invariant))
        elif invariant.recommended_action == "flat_for_day":
            actions.extend(self._flat_for_day(invariant))
            flat_for_day = True

        state = load_daemon_state(self.store).get("state") or RECOVERY_RECONCILING
        result = ContainmentCycleResult(
            mode=self.mode,
            phase=phase,
            state=str(state),
            invariant=invariant,
            actions=actions,
            shadow=self.shadow,
            flat_for_day=flat_for_day,
            details=details,
        )
        self._emit(result)
        if (not invariant.ok) and self.email_on_action and self.email_mode != "off":
            if self.email_mode == "immediate":
                self._send_containment_email(result)
            else:
                self._record_email_digest(result)
        return result

    def _maybe_sweep_orphans(self, invariant: BracketInvariantResult) -> List[str]:
        actions: List[str] = []
        try:
            sweep = self.broker.maybe_sweep_remote_order_authority()
            if sweep and not sweep.get("skipped") and int(sweep.get("orphans_cancelled") or 0) > 0:
                actions.append("orphan_entry_cancel:%s" % sweep.get("orphans_cancelled"))
        except Exception as exc:
            actions.append("orphan_entry_sweep_error:%s" % exc)
        # Healthy flat books may still carry remote STOP_LOSS ghosts — sweep in live
        # only. Shadow would-cancel is reserved for explicit orphan/cross_book faults
        # so intentional ST+PMC entry arms are not spammed as orphan_protective.
        if abs(float(invariant.local_qty)) < 1e-9 and not self.shadow:
            actions.extend(self._cancel_orphan_protectives(invariant))
        return actions

    def _cancel_orphan_protectives(self, invariant: BracketInvariantResult) -> List[str]:
        actions: List[str] = []
        if self.shadow:
            actions.append("shadow_would_cancel_orphan_protectives")
            self.store.append_event(
                "reconciliation_events",
                {
                    "event": "containment_would_cancel_orphans",
                    "classification": invariant.classification,
                    "reasons": invariant.reasons,
                },
            )
            return actions
        try:
            n = self.broker.sweep_orphan_protectives_when_flat(
                strategy_id=self.strategy_id,
                instrument=self.instrument,
                reason="containment_orphan_protective",
            )
            actions.append("cancel_orphan_protectives:%s" % n)
        except Exception as exc:
            actions.append("cancel_orphan_protectives_error:%s" % exc)
        return actions

    def _freeze_for_missing_brackets(self, invariant: BracketInvariantResult) -> List[str]:
        actions: List[str] = []
        new_state = DISARMED if invariant.classification == "stream_stale" else POSITION_OPEN_BRACKET_PENDING
        transition_daemon_state(
            self.store,
            new_state=new_state,
            reason=invariant.classification,
            snapshot=invariant.as_dict(),
        )
        if invariant.classification == "stream_stale":
            self._stream_stale_latched = True
        if self.shadow:
            actions.append("shadow_would_freeze_entries")
            self.store.append_event(
                "reconciliation_events",
                {
                    "event": "containment_would_freeze_entries",
                    "classification": invariant.classification,
                    "reasons": invariant.reasons,
                },
            )
            return actions
        if self.supervisor is not None:
            reason_prefix = "stream_stale" if invariant.classification == "stream_stale" else "bracket_invariant"
            self.supervisor.freeze_entries(
                "%s:%s" % (reason_prefix, invariant.classification),
                invariant.as_dict(),
            )
            actions.append("freeze_entries")
        else:
            actions.append("freeze_skipped_no_supervisor")
        return actions

    def _flat_for_day(self, invariant: BracketInvariantResult) -> List[str]:
        actions: List[str] = []
        payload = {
            "reason": invariant.classification,
            "asof": utc_now_iso(),
            "session_date": ny_session_date(),
            "instrument": self.instrument,
            "strategy_id": self.strategy_id,
            "mode": self.mode,
            "invariant": invariant.as_dict(),
        }
        write_flat_for_day(self.store, payload)
        transition_daemon_state(
            self.store,
            new_state=STATE_FLAT_FOR_DAY,
            reason=invariant.classification,
            snapshot=payload,
        )
        if self.shadow:
            actions.append("shadow_would_flat_for_day")
            self.store.append_event(
                "reconciliation_events",
                {"event": "containment_would_flat_for_day", **payload},
            )
            return actions
        # Cancel owned working orders + flatten focus instrument first; then pin FLAT_FOR_DAY
        # so go_flat's emergency_flatten mode does not stick as the day policy.
        try:
            for order in list(self.broker.reconcile_orders()):
                if str(order.strategy_id or "") != self.strategy_id:
                    continue
                if order.status in WORKING_STATUSES:
                    self.broker.cancel_order(order.broker_order_id, reason="flat_for_day")
            self.broker.go_flat([self.instrument])
            actions.append("flattened:%s" % self.instrument)
        except Exception as exc:
            actions.append("flatten_error:%s" % exc)
        if self.supervisor is not None:
            self.supervisor.mark_flat_for_day(invariant.classification, payload)
            actions.append("supervisor_flat_for_day")
        return actions

    def _emit(self, result: ContainmentCycleResult) -> None:
        self.store.append_event(
            "reconciliation_events",
            {"event": "containment_cycle", **result.as_dict()},
        )

    def _digest_path(self) -> Path:
        return self.store.root / CONTAINMENT_EMAIL_DIGEST_FILE

    def _load_email_digest(self) -> Dict[str, Any]:
        path = self._digest_path()
        today = ny_session_date()
        empty = {
            "session_date": today,
            "by_class": {},
            "events": [],
            "email_sent_at": "",
            "email_sent_for_session": "",
        }
        if not path.exists():
            return empty
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return empty
        if not isinstance(raw, dict):
            return empty
        if str(raw.get("session_date") or "") != today:
            return empty
        raw.setdefault("by_class", {})
        raw.setdefault("events", [])
        raw.setdefault("email_sent_at", "")
        raw.setdefault("email_sent_for_session", "")
        return raw

    def _save_email_digest(self, digest: Dict[str, Any]) -> None:
        path = self._digest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _record_email_digest(self, result: ContainmentCycleResult) -> None:
        digest = self._load_email_digest()
        inv = result.invariant
        classification = inv.classification if inv is not None else "?"
        by_class = dict(digest.get("by_class") or {})
        by_class[classification] = int(by_class.get(classification) or 0) + 1
        events = list(digest.get("events") or [])
        events.append(
            {
                "ts": utc_now_iso(),
                "phase": result.phase,
                "state": result.state,
                "classification": classification,
                "actions": list(result.actions),
                "reasons": list(inv.reasons) if inv is not None else [],
            }
        )
        if len(events) > CONTAINMENT_EMAIL_DIGEST_MAX_EVENTS:
            events = events[-CONTAINMENT_EMAIL_DIGEST_MAX_EVENTS:]
        digest.update(
            {
                "session_date": ny_session_date(),
                "by_class": by_class,
                "events": events,
            }
        )
        self._save_email_digest(digest)
        self.store.append_event(
            "reconciliation_events",
            {
                "event": "containment_email_digest_recorded",
                "classification": classification,
                "n_events": len(events),
                "by_class": by_class,
            },
        )

    def _maybe_flush_eod_email(self) -> None:
        if not self.email_on_action or self.email_mode != "eod":
            return
        if not ny_past_containment_email_eod():
            return
        digest = self._load_email_digest()
        today = ny_session_date()
        if str(digest.get("email_sent_for_session") or "") == today:
            return
        by_class = dict(digest.get("by_class") or {})
        events = list(digest.get("events") or [])
        if not by_class and not events:
            # Still mark sent so we don't re-check forever with empty digests.
            digest["email_sent_for_session"] = today
            digest["email_sent_at"] = utc_now_iso()
            digest["session_date"] = today
            self._save_email_digest(digest)
            return
        subject = "potions: OANDA containment EOD digest %s [%s] %s" % (
            "SHADOW" if self.shadow else "LIVE",
            ",".join("%s=%s" % (k, by_class[k]) for k in sorted(by_class)) or "ok",
            self.strategy_id,
        )
        lines = [
            "EOD containment digest (one email per demo per NY session)",
            "demo=%s" % self.output_root,
            "strategy_id=%s instrument=%s" % (self.strategy_id, self.instrument),
            "mode=%s shadow=%s session=%s" % (self.mode, self.shadow, today),
            "counts=%s" % json.dumps(by_class, sort_keys=True),
            "n_events_kept=%d (cap %d)" % (len(events), CONTAINMENT_EMAIL_DIGEST_MAX_EVENTS),
            "",
            "Recent events:",
        ]
        for ev in events[-20:]:
            lines.append(
                "- %s %s class=%s actions=%s reasons=%s"
                % (
                    ev.get("ts"),
                    ev.get("phase"),
                    ev.get("classification"),
                    ",".join(ev.get("actions") or []) or "-",
                    ";".join(ev.get("reasons") or []) or "-",
                )
            )
        lines.append("hub=%s" % self.store.root)
        try:
            from ..notify_email import send_email

            send_email(subject=subject, body="\n".join(lines))
            digest["email_sent_for_session"] = today
            digest["email_sent_at"] = utc_now_iso()
            digest["session_date"] = today
            self._save_email_digest(digest)
            self.store.append_event(
                "reconciliation_events",
                {
                    "event": "containment_email_eod_sent",
                    "session_date": today,
                    "by_class": by_class,
                    "n_events": len(events),
                },
            )
        except Exception as exc:
            self.store.append_event(
                "reconciliation_events",
                {"event": "containment_email_error", "error": str(exc), "phase": "eod"},
            )

    def _send_containment_email(self, result: ContainmentCycleResult) -> None:
        try:
            from ..notify_email import send_email

            inv = result.invariant.as_dict() if result.invariant else {}
            subject = "potions: OANDA containment %s [%s] %s" % (
                "SHADOW" if result.shadow else "LIVE",
                result.invariant.classification if result.invariant else "?",
                self.strategy_id,
            )
            body = "\n".join(
                [
                    "demo=%s" % self.output_root,
                    "strategy_id=%s instrument=%s" % (self.strategy_id, self.instrument),
                    "mode=%s phase=%s state=%s" % (result.mode, result.phase, result.state),
                    "actions=%s" % ",".join(result.actions),
                    "invariant=%s" % json.dumps(inv, sort_keys=True),
                    "hub=%s" % (self.store.root),
                ]
            )
            send_email(subject=subject, body=body)
        except Exception as exc:
            self.store.append_event(
                "reconciliation_events",
                {"event": "containment_email_error", "error": str(exc)},
            )


def evaluate_fixture_book(
    *,
    positions_csv: Path,
    orders_csv: Path,
    instrument: str,
    strategy_id: str,
    strategy_type: str = "v2b_scaleout",
    entry_qty: float = 3.0,
    broker_qty: Optional[float] = None,
    account_instrument_qty: Optional[float] = None,
) -> BracketInvariantResult:
    """Pure detector over curated CSV fixtures (no broker)."""
    import csv

    def _rows(path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    return evaluate_bracket_invariant(
        instrument=instrument,
        strategy_id=strategy_id,
        positions=_rows(positions_csv),
        orders=_rows(orders_csv),
        expectation=expectation_for_strategy_type(strategy_type, entry_qty=entry_qty),
        broker_qty=broker_qty,
        account_instrument_qty=account_instrument_qty,
    )


def install_containment(
    runner: Any,
    *,
    instrument: str,
    strategy_id: str,
    strategy_type: str,
    entry_qty: float = 0.0,
    clock: Optional[Any] = None,
) -> Optional[DaemonContainmentController]:
    """Attach a ``DaemonContainmentController`` onto an OANDA demo runner.

    Expects ``runner.engine``, ``runner.store``, ``runner.output_root``.
    No-op (returns None) when the broker is not ``OandaBroker``.
    """
    broker = getattr(getattr(runner, "engine", None), "broker", None)
    if not isinstance(broker, OandaBroker):
        runner.containment = None  # type: ignore[attr-defined]
        return None
    supervisor = getattr(broker, "supervisor", None)
    controller = DaemonContainmentController(
        store=runner.store,
        broker=broker,
        supervisor=supervisor,
        instrument=instrument,
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        entry_qty=float(entry_qty or 0.0),
        output_root=getattr(runner, "output_root", None),
        clock=clock,
    )
    runner.containment = controller  # type: ignore[attr-defined]
    return controller


def containment_note_activity(runner: Any) -> None:
    """Mark stream/price activity on the runner's containment controller (if any)."""
    controller = getattr(runner, "containment", None)
    if controller is not None:
        controller.note_stream_activity()


def containment_on_reconnect(runner: Any, *, append_progress_fn: Any) -> None:
    """REST reconcile + optional rearm after a pricing stream reconnect."""
    controller = getattr(runner, "containment", None)
    if controller is None:
        return
    try:
        result = controller.note_stream_reconnected()
        append_progress_fn(
            runner.output_root,
            "containment reconnect mode=%s state=%s actions=%s ok=%s"
            % (
                result.mode,
                result.state,
                ",".join(result.actions) or "-",
                None if result.invariant is None else result.invariant.ok,
            ),
        )
    except Exception as exc:
        append_progress_fn(runner.output_root, "WARN containment reconnect failed: %s" % exc)


def containment_bootstrap(runner: Any, *, append_progress_fn: Any) -> None:
    controller = getattr(runner, "containment", None)
    if controller is None:
        return
    try:
        result = controller.bootstrap()
        append_progress_fn(
            runner.output_root,
            "containment bootstrap mode=%s state=%s actions=%s ok=%s"
            % (
                result.mode,
                result.state,
                ",".join(result.actions) or "-",
                None if result.invariant is None else result.invariant.ok,
            ),
        )
    except Exception as exc:
        append_progress_fn(runner.output_root, "WARN containment bootstrap failed: %s" % exc)


def containment_poll(runner: Any, *, append_progress_fn: Any, force: bool = False) -> None:
    controller = getattr(runner, "containment", None)
    if controller is None:
        return
    try:
        result = controller.maybe_run(force=force)
    except Exception as exc:
        append_progress_fn(runner.output_root, "WARN containment cycle failed: %s" % exc)
        return
    if result is None:
        return
    if result.invariant is not None and not result.invariant.ok:
        append_progress_fn(
            runner.output_root,
            "containment %s class=%s actions=%s shadow=%s"
            % (
                result.phase,
                result.invariant.classification,
                ",".join(result.actions) or "-",
                result.shadow,
            ),
        )


def oanda_broker_with_supervisor(
    store: FlatFileStore,
    *,
    config: Any,
    client: Any,
    strategy_id: str,
    instrument: str,
    allow_live_routing: bool = False,
) -> OandaBroker:
    """Build an ``OandaBroker`` with sticky ``RuntimeSupervisor`` (for non-v2b runners)."""
    supervisor = RuntimeSupervisor(store, provider="oanda")
    return OandaBroker(
        store,
        config=config,
        client=client,
        allow_live_routing=allow_live_routing,
        supervisor=supervisor,
        authority_strategy_ids=[strategy_id],
        position_scope_instruments=[instrument],
    )
