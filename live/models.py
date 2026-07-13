from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4


AccountMode = str  # paper | live
OrderSide = str  # buy | sell
OrderType = str  # market | limit | stop


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid4().hex[:12])


def as_row(obj: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in asdict(obj).items():
        if value is None:
            out[key] = ""
        elif isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def parse_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


@dataclass(frozen=True)
class Bar:
    instrument: str
    timeframe: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    complete: bool = True
    source: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Bar":
        return cls(
            instrument=str(row["instrument"]),
            timeframe=str(row["timeframe"]),
            ts=str(row["ts"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume") or 0.0),
            complete=parse_bool(row.get("complete", "true")),
            source=str(row.get("source", "")),
        )


@dataclass(frozen=True)
class StrategyInstance:
    strategy_id: str
    strategy_type: str
    version: str
    instrument: str
    broker_instrument: str
    account_mode: AccountMode = "paper"
    enabled: bool = True
    timeframes: str = "D"
    max_contracts: int = 3
    max_open_orders: int = 12
    config_json: str = "{}"

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "StrategyInstance":
        return cls(
            strategy_id=str(row["strategy_id"]),
            strategy_type=str(row["strategy_type"]),
            version=str(row.get("version", "v1")),
            instrument=str(row["instrument"]),
            broker_instrument=str(row.get("broker_instrument") or row["instrument"]),
            account_mode=str(row.get("account_mode", "paper")),
            enabled=parse_bool(row.get("enabled", "true")),
            timeframes=str(row.get("timeframes", "D")),
            max_contracts=parse_int(row.get("max_contracts"), 3),
            max_open_orders=parse_int(row.get("max_open_orders"), 12),
            config_json=str(row.get("config_json", "{}") or "{}"),
        )


@dataclass(frozen=True)
class Job:
    job_id: str
    job_type: str
    status: str = "pending"
    scheduled_for: str = ""
    payload_json: str = "{}"
    attempts: int = 0
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, job_type: str, payload_json: str = "{}", scheduled_for: str = "") -> "Job":
        now = utc_now_iso()
        return cls(
            job_id=new_id("job"),
            job_type=job_type,
            scheduled_for=scheduled_for,
            payload_json=payload_json,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    strategy_id: str
    trade_id: str
    instrument: str
    account_mode: AccountMode
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    reason: str = ""
    status: str = "created"
    requires_verification: bool = True
    verification_id: str = ""
    parent_intent_id: str = ""
    reduce_only: bool = False
    bracket_role: str = ""  # entry | stop | target | runner_stop | close
    bracket_stop_price: Optional[float] = None
    bracket_target_price: Optional[float] = None
    oco_group: str = ""
    tif: str = "GTC"
    live_after_ts: str = ""
    expires_after_ts: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(
        cls,
        strategy_id: str,
        trade_id: str,
        instrument: str,
        account_mode: AccountMode,
        side: OrderSide,
        order_type: OrderType,
        quantity: int,
        **kwargs: Any,
    ) -> "OrderIntent":
        now = utc_now_iso()
        return cls(
            intent_id=new_id("intent"),
            strategy_id=strategy_id,
            trade_id=trade_id,
            instrument=instrument,
            account_mode=account_mode,
            side=side,
            order_type=order_type,
            quantity=quantity,
            created_at=now,
            updated_at=now,
            **kwargs,
        )

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "OrderIntent":
        return cls(
            intent_id=str(row["intent_id"]),
            strategy_id=str(row["strategy_id"]),
            trade_id=str(row["trade_id"]),
            instrument=str(row["instrument"]),
            account_mode=str(row.get("account_mode", "paper")),
            side=str(row["side"]),
            order_type=str(row["order_type"]),
            quantity=parse_int(row["quantity"]),
            limit_price=parse_float(row.get("limit_price")),
            stop_price=parse_float(row.get("stop_price")),
            reason=str(row.get("reason", "")),
            status=str(row.get("status", "created")),
            requires_verification=parse_bool(row.get("requires_verification", "true")),
            verification_id=str(row.get("verification_id", "")),
            parent_intent_id=str(row.get("parent_intent_id", "")),
            reduce_only=parse_bool(row.get("reduce_only", "false")),
            bracket_role=str(row.get("bracket_role", "")),
            bracket_stop_price=parse_float(row.get("bracket_stop_price")),
            bracket_target_price=parse_float(row.get("bracket_target_price")),
            oco_group=str(row.get("oco_group", "")),
            tif=str(row.get("tif", "GTC")),
            live_after_ts=str(row.get("live_after_ts", "")),
            expires_after_ts=str(row.get("expires_after_ts", "")),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )


@dataclass(frozen=True)
class BrokerOrder:
    broker_order_id: str
    intent_id: str
    strategy_id: str
    trade_id: str
    instrument: str
    account_mode: AccountMode
    side: OrderSide
    order_type: OrderType
    quantity: int
    remaining_quantity: int
    status: str = "submitted"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    reduce_only: bool = False
    bracket_role: str = ""
    parent_order_id: str = ""
    oco_group: str = ""
    live_after_ts: str = ""
    expires_after_ts: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_intent(cls, intent: OrderIntent) -> "BrokerOrder":
        now = utc_now_iso()
        return cls(
            broker_order_id=new_id("ord"),
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            trade_id=intent.trade_id,
            instrument=intent.instrument,
            account_mode=intent.account_mode,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            remaining_quantity=intent.quantity,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            reduce_only=intent.reduce_only,
            bracket_role=intent.bracket_role,
            oco_group=intent.oco_group,
            live_after_ts=intent.live_after_ts,
            expires_after_ts=intent.expires_after_ts,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "BrokerOrder":
        return cls(
            broker_order_id=str(row["broker_order_id"]),
            intent_id=str(row["intent_id"]),
            strategy_id=str(row["strategy_id"]),
            trade_id=str(row["trade_id"]),
            instrument=str(row["instrument"]),
            account_mode=str(row.get("account_mode", "paper")),
            side=str(row["side"]),
            order_type=str(row["order_type"]),
            quantity=parse_int(row["quantity"]),
            remaining_quantity=parse_int(row.get("remaining_quantity"), parse_int(row["quantity"])),
            status=str(row.get("status", "submitted")),
            limit_price=parse_float(row.get("limit_price")),
            stop_price=parse_float(row.get("stop_price")),
            reduce_only=parse_bool(row.get("reduce_only", "false")),
            bracket_role=str(row.get("bracket_role", "")),
            parent_order_id=str(row.get("parent_order_id", "")),
            oco_group=str(row.get("oco_group", "")),
            live_after_ts=str(row.get("live_after_ts", "")),
            expires_after_ts=str(row.get("expires_after_ts", "")),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )


@dataclass(frozen=True)
class Fill:
    fill_id: str
    broker_order_id: str
    intent_id: str
    strategy_id: str
    trade_id: str
    instrument: str
    account_mode: AccountMode
    side: OrderSide
    quantity: int
    price: float
    ts: str
    reason: str = ""


@dataclass(frozen=True)
class Position:
    position_id: str
    strategy_id: str
    instrument: str
    account_mode: AccountMode
    quantity: int
    avg_price: float
    realized_pnl: float = 0.0
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Position":
        return cls(
            position_id=str(row["position_id"]),
            strategy_id=str(row["strategy_id"]),
            instrument=str(row["instrument"]),
            account_mode=str(row.get("account_mode", "paper")),
            quantity=parse_int(row.get("quantity")),
            avg_price=float(row.get("avg_price") or 0.0),
            realized_pnl=float(row.get("realized_pnl") or 0.0),
            updated_at=str(row.get("updated_at", "")),
        )


@dataclass(frozen=True)
class LevelUpdate:
    strategy_id: str
    instrument: str
    level_name: str
    price: float
    active_from: str
    active_to: str = ""
    metadata_json: str = "{}"


@dataclass(frozen=True)
class Alert:
    alert_id: str
    strategy_id: str
    level: str
    message: str
    payload_json: str = "{}"
    status: str = "new"
    created_at: str = ""

    @classmethod
    def create(cls, strategy_id: str, level: str, message: str, payload_json: str = "{}") -> "Alert":
        return cls(
            alert_id=new_id("alert"),
            strategy_id=strategy_id,
            level=level,
            message=message,
            payload_json=payload_json,
            created_at=utc_now_iso(),
        )


@dataclass(frozen=True)
class VerificationRequest:
    verification_id: str
    intent_id: str
    strategy_id: str
    account_mode: AccountMode
    status: str
    challenge: str
    created_at: str
    approved_at: str = ""


@dataclass(frozen=True)
class FeatureSnapshot:
    feature_name: str
    strategy_id: str
    instrument: str
    event_ts: str
    available_at_ts: str
    current_bar_ts: str
    source: str = ""
    value_ref: str = ""
    metadata_json: str = "{}"


@dataclass(frozen=True)
class CausalViolation:
    violation_id: str
    strategy_id: str
    instrument: str
    violation_type: str
    current_bar_ts: str
    offending_ts: str
    severity: str
    action_taken: str
    feature_name: str = ""
    intent_id: str = ""
    scrutiny_classification: str = ""
    details_json: str = "{}"
    created_at: str = ""


@dataclass(frozen=True)
class CancelIntent:
    strategy_id: str
    broker_order_id: str
    reason: str


@dataclass(frozen=True)
class ModifyIntent:
    strategy_id: str
    broker_order_id: str
    reason: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    bracket_stop_price: Optional[float] = None
    bracket_target_price: Optional[float] = None
    live_after_ts: Optional[str] = None


@dataclass(frozen=True)
class StrategyActions:
    order_intents: Sequence[OrderIntent]
    cancel_intents: Sequence[CancelIntent]
    modify_intents: Sequence[ModifyIntent]
    level_updates: Sequence[LevelUpdate]
    alerts: Sequence[Alert]
    causal_features: Sequence[FeatureSnapshot] = ()

    @classmethod
    def empty(cls) -> "StrategyActions":
        return cls([], [], [], [], [])

    @classmethod
    def combine(cls, actions: Sequence["StrategyActions"]) -> "StrategyActions":
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []
        causal_features: List[FeatureSnapshot] = []
        for action in actions:
            orders.extend(action.order_intents)
            cancels.extend(action.cancel_intents)
            modifies.extend(action.modify_intents)
            levels.extend(action.level_updates)
            alerts.extend(action.alerts)
            causal_features.extend(action.causal_features)
        return cls(orders, cancels, modifies, levels, alerts, causal_features)
