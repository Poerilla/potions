from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .broker import BaseBroker
from .live_feed import FeedHealth, LiveFeedAdapter, PersistedLiveFeedAdapter
from .models import Bar, BrokerOrder, Fill, OrderIntent, Position, as_row, new_id, utc_now_iso
from .store import FlatFileStore


class CqgAdapterError(RuntimeError):
    pass


class CqgConfigurationError(CqgAdapterError):
    pass


@dataclass(frozen=True)
class CqgWebApiConfig:
    env: str = "demo"
    endpoint: str = "wss://demoapi.cqg.com"
    private_label: str = "WebAPITest"
    client_id: str = "WebAPITest"
    client_version: str = "potions-cqg-adapter-dev"
    username: str = ""
    password: str = ""
    account_id: str = ""
    contract_map: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, environ: Optional[Dict[str, str]] = None) -> "CqgWebApiConfig":
        env = environ if environ is not None else os.environ
        cqg_env = env.get("CQG_ENV", "demo")
        endpoint = env.get("CQG_ENDPOINT") or ("wss://demoapi.cqg.com" if cqg_env == "demo" else "")
        return cls(
            env=cqg_env,
            endpoint=endpoint,
            private_label=env.get("CQG_PRIVATE_LABEL", "WebAPITest"),
            client_id=env.get("CQG_CLIENT_ID", "WebAPITest"),
            client_version=env.get("CQG_CLIENT_VERSION", "potions-cqg-adapter-dev"),
            username=env.get("CQG_USERNAME", ""),
            password=env.get("CQG_PASSWORD", ""),
            account_id=env.get("CQG_ACCOUNT_ID", ""),
            contract_map=parse_contract_map(env.get("CQG_CONTRACT_MAP", "")),
        )

    @classmethod
    def from_json_file(cls, path: Path, environ: Optional[Dict[str, str]] = None) -> "CqgWebApiConfig":
        base = cls.from_env(environ)
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        merged = {
            "env": raw.get("env", base.env),
            "endpoint": raw.get("endpoint", base.endpoint),
            "private_label": raw.get("private_label", base.private_label),
            "client_id": raw.get("client_id", base.client_id),
            "client_version": raw.get("client_version", base.client_version),
            "username": raw.get("username", base.username),
            "password": raw.get("password", base.password),
            "account_id": raw.get("account_id", base.account_id),
            "contract_map": dict(base.contract_map),
        }
        merged["contract_map"].update(raw.get("contract_map") or {})
        return cls(**merged)

    def validate_for_network(self) -> None:
        missing = []
        for field in ("endpoint", "private_label", "client_id", "client_version", "username", "password"):
            if not getattr(self, field):
                missing.append(field)
        if missing:
            raise CqgConfigurationError("Missing CQG config fields: %s" % ", ".join(missing))

    def cqg_symbol_for(self, instrument: str) -> str:
        key = instrument.upper()
        value = self.contract_map.get(key)
        if not value:
            raise CqgConfigurationError("No CQG contract mapping configured for %s" % key)
        return value


@dataclass(frozen=True)
class CqgContractRef:
    instrument: str
    cqg_symbol: str
    contract_id: str
    resolved_at: str
    price_scale: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)


class CqgProtocolCodec:
    def encode(self, message: Dict[str, Any]) -> bytes:
        raise NotImplementedError

    def decode(self, payload: bytes) -> Dict[str, Any]:
        raise NotImplementedError


class JsonCqgProtocolCodec(CqgProtocolCodec):
    """Offline codec for tests and saved CQG-like event replay.

    The live CQG wire format is protobuf. Keeping a JSON codec in this module
    lets tests exercise message construction and state transitions without
    requiring CQG credentials or vendored generated protocol files.
    """

    def encode(self, message: Dict[str, Any]) -> bytes:
        return json.dumps(message, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes) -> Dict[str, Any]:
        return json.loads(payload.decode("utf-8"))


class CqgProtobufCodec(CqgProtocolCodec):
    """Adapter boundary for generated CQG protobuf classes.

    Drop CQG's generated *_pb2.py files into an isolated import path and pass
    the module here. This class intentionally refuses to guess field names when
    the generated protocol is absent; the JSON codec covers tests/offline work.
    """

    def __init__(self, proto_module: Any = None):
        if proto_module is None:
            try:
                from .cqg_proto import websocket_api_2_pb2 as proto_module  # type: ignore
            except Exception as exc:  # pragma: no cover - depends on local generated files.
                raise CqgConfigurationError(
                    "CQG protobuf files are not installed. Generate/vendor CQG *_pb2.py files under live/cqg_proto first."
                ) from exc
        self.proto = proto_module

    def encode(self, message: Dict[str, Any]) -> bytes:
        raise NotImplementedError("CQG protobuf field mapping must be enabled after generated proto files are installed")

    def decode(self, payload: bytes) -> Dict[str, Any]:
        raise NotImplementedError("CQG protobuf field mapping must be enabled after generated proto files are installed")


class CqgWebApiClient:
    """Low-level CQG session/message boundary.

    The network methods are deliberately thin. The production path should use
    CQG-generated protobuf classes through :class:`CqgProtobufCodec`; tests and
    saved-message replays use :class:`JsonCqgProtocolCodec`.
    """

    def __init__(
        self,
        config: CqgWebApiConfig,
        store: Optional[FlatFileStore] = None,
        codec: Optional[CqgProtocolCodec] = None,
        transport_factory: Optional[Callable[[str], Any]] = None,
    ):
        self.config = config
        self.store = store
        self.codec = codec or JsonCqgProtocolCodec()
        self.transport_factory = transport_factory
        self.transport: Any = None
        self._request_id = 0

    def next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def build_logon_message(self) -> Dict[str, Any]:
        return {
            "type": "logon",
            "request_id": self.next_request_id(),
            "private_label": self.config.private_label,
            "client_id": self.config.client_id,
            "client_version": self.config.client_version,
            "username": self.config.username,
            "password": "***" if self.config.password else "",
            "max_collapsing_level": "none",
        }

    def build_symbol_resolution_request(self, instrument: str) -> Dict[str, Any]:
        return {
            "type": "resolve_symbol",
            "request_id": self.next_request_id(),
            "instrument": instrument.upper(),
            "cqg_symbol": self.config.cqg_symbol_for(instrument),
        }

    def build_market_data_subscription(
        self,
        contract_ref: CqgContractRef,
        level: str = "trades",
    ) -> Dict[str, Any]:
        return {
            "type": "market_data_subscription",
            "request_id": self.next_request_id(),
            "instrument": contract_ref.instrument,
            "contract_id": contract_ref.contract_id,
            "level": level,
            "require_realtime": True,
        }

    def build_trade_subscription(self) -> Dict[str, Any]:
        return {
            "type": "trade_subscription",
            "request_id": self.next_request_id(),
            "account_id": self.config.account_id,
            "scopes": ["orders", "fills", "positions"],
        }

    def build_account_request(self) -> Dict[str, Any]:
        return {"type": "account_request", "request_id": self.next_request_id(), "account_id": self.config.account_id}

    def build_order_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"type": "order_request", "request_id": self.next_request_id(), "order": payload}

    def record_session_event(self, event: Dict[str, Any]) -> None:
        if self.store is not None:
            self.store.append_event("cqg_session_events", event)

    def connect(self) -> None:
        self.config.validate_for_network()
        if self.transport_factory is None:
            raise CqgConfigurationError(
                "No CQG transport factory configured. Install websockets/protobuf path before network smoke tests."
            )
        self.transport = self.transport_factory(self.config.endpoint)
        self.record_session_event({"event": "connect", "endpoint": self.config.endpoint, "env": self.config.env})

    def disconnect(self) -> None:
        self.transport = None
        self.record_session_event({"event": "disconnect", "endpoint": self.config.endpoint})

    def encode(self, message: Dict[str, Any]) -> bytes:
        return self.codec.encode(message)

    def decode(self, payload: bytes) -> Dict[str, Any]:
        return self.codec.decode(payload)


class OneMinuteBarBuilder:
    def __init__(self, instrument: str):
        self.instrument = instrument
        self._current_key: Optional[datetime] = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0.0

    def on_trade(self, price: float, quantity: float, ts: str) -> List[Bar]:
        event_dt = parse_cqg_ts(ts)
        minute_key = event_dt.replace(second=0, microsecond=0)
        emitted: List[Bar] = []
        if self._current_key is None:
            self._start(minute_key, price, quantity)
            return emitted
        if minute_key != self._current_key:
            emitted.append(self._bar())
            self._start(minute_key, price, quantity)
            return emitted
        self._high = max(self._high, price)
        self._low = min(self._low, price)
        self._close = price
        self._volume += quantity
        return emitted

    def flush(self) -> List[Bar]:
        if self._current_key is None:
            return []
        bar = self._bar()
        self._current_key = None
        return [bar]

    def _start(self, minute_key: datetime, price: float, quantity: float) -> None:
        self._current_key = minute_key
        self._open = price
        self._high = price
        self._low = price
        self._close = price
        self._volume = quantity

    def _bar(self) -> Bar:
        assert self._current_key is not None
        return Bar(
            instrument=self.instrument,
            timeframe="1m",
            ts=isoformat_utc(self._current_key),
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            complete=True,
            source="cqg",
        )


class FiveMinuteBarAggregator:
    def __init__(self, instrument: str):
        self.instrument = instrument
        self._bucket_key: Optional[datetime] = None
        self._bars: List[Bar] = []

    def on_bar(self, bar: Bar) -> List[Bar]:
        if bar.timeframe != "1m":
            return []
        dt = parse_cqg_ts(bar.ts)
        bucket = dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
        emitted: List[Bar] = []
        if self._bucket_key is not None and bucket != self._bucket_key:
            emitted.extend(self._flush_if_complete())
            self._bars = []
        self._bucket_key = bucket
        self._bars.append(bar)
        if len(self._bars) >= 5:
            emitted.extend(self._flush_if_complete())
            self._bars = []
            self._bucket_key = None
        return emitted

    def flush(self) -> List[Bar]:
        return self._flush_if_complete()

    def _flush_if_complete(self) -> List[Bar]:
        if len(self._bars) < 5:
            return []
        bars = self._bars[:5]
        return [
            Bar(
                instrument=self.instrument,
                timeframe="5m",
                ts=bars[-1].ts,
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
                volume=sum(bar.volume for bar in bars),
                complete=True,
                source="cqg_1m_aggregate",
            )
        ]


class CqgMarketDataFeedAdapter(LiveFeedAdapter):
    BLOCKING_STATUSES = {"access_denied", "delayed", "downgraded", "stale", "unresolved_contract", "collapsing"}

    def __init__(
        self,
        store: FlatFileStore,
        config: Optional[CqgWebApiConfig] = None,
        on_bar: Optional[Callable[[Bar], None]] = None,
        stale_after_seconds: float = 30.0,
        clock: Callable[[], datetime] = datetime.utcnow,
    ):
        self.store = store
        self.store.ensure()
        self.config = config or CqgWebApiConfig.from_env()
        self._persisted = PersistedLiveFeedAdapter(
            store,
            on_bar=on_bar,
            allowed_timeframes=("1m", "5m", "15m", "1h", "D"),
            stale_after_seconds=stale_after_seconds,
            clock=clock,
        )
        self.contract_refs: Dict[str, CqgContractRef] = {}
        self._minute_builders: Dict[str, OneMinuteBarBuilder] = {}
        self._five_minute_aggregators: Dict[str, FiveMinuteBarAggregator] = {}
        self._blocking_reason = ""
        self._market_status = "init"
        self._write_market_data_status()

    def resolve_contract(
        self,
        instrument: str,
        contract_id: str,
        cqg_symbol: Optional[str] = None,
        price_scale: int = 2,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CqgContractRef:
        ref = CqgContractRef(
            instrument=instrument.upper(),
            cqg_symbol=cqg_symbol or self.config.contract_map.get(instrument.upper(), ""),
            contract_id=str(contract_id),
            resolved_at=utc_now_iso(),
            price_scale=price_scale,
            metadata=metadata or {},
        )
        self.contract_refs[ref.instrument] = ref
        self._blocking_reason = ""
        self.store.append_event("cqg_session_events", {"event": "contract_resolved", **as_ref_row(ref)})
        self._write_market_data_status()
        return ref

    def on_raw_event(self, event: Dict[str, Any]) -> List[Bar]:
        event = dict(event)
        event_type = str(event.get("type") or "")
        self._persist_raw_market_event(event)
        if event_type == "symbol_resolution":
            self.resolve_contract(
                str(event["instrument"]),
                str(event["contract_id"]),
                cqg_symbol=str(event.get("cqg_symbol") or ""),
                price_scale=int(event.get("price_scale") or 2),
                metadata=dict(event.get("metadata") or {}),
            )
            return []
        if event_type == "market_data_status":
            self._handle_market_data_status(event)
            return []
        if event_type == "trade":
            return self._handle_trade_event(event)
        if event_type == "bar":
            return self._handle_bar_event(event)
        return self._persisted.on_raw_event(event)

    def on_completed_bar(self, timeframe: str, bar: Bar) -> None:
        self._persisted.on_completed_bar(timeframe, bar)
        self._append_bar_audit(bar, "completed_bar", "")

    def health(self) -> FeedHealth:
        base = self._persisted.health()
        if self._blocking_reason:
            return replace(base, status="blocked")
        return base

    def is_blocking_entries(self) -> bool:
        base = self._persisted.health()
        return bool(self._blocking_reason or base.stale)

    def blocking_reason(self) -> str:
        if self._blocking_reason:
            return self._blocking_reason
        health = self._persisted.health()
        if health.stale:
            return "stale"
        return ""

    def flush(self) -> List[Bar]:
        emitted: List[Bar] = []
        for builder in self._minute_builders.values():
            for bar in builder.flush():
                emitted.extend(self._persist_1m_and_derived_5m(bar))
        return emitted

    def _handle_market_data_status(self, event: Dict[str, Any]) -> None:
        status = str(event.get("status") or event.get("status_code") or "").strip().lower()
        self._market_status = status or "unknown"
        if status in self.BLOCKING_STATUSES or event.get("delayed") or event.get("access_denied"):
            self._blocking_reason = status or "market_data_blocked"
            self.store.append_event("market_data_quality", {"event": "cqg_blocking_status", **event})
        elif status in {"ok", "realtime", "subscribed"}:
            self._blocking_reason = ""
        self._write_market_data_status()

    def _handle_trade_event(self, event: Dict[str, Any]) -> List[Bar]:
        instrument = str(event["instrument"]).upper()
        if instrument not in self.contract_refs:
            self._blocking_reason = "unresolved_contract"
            self._write_market_data_status()
            self.store.append_event("market_data_quality", {"event": "cqg_trade_without_contract_ref", **event})
            return []
        price = float(event.get("price"))
        qty = float(event.get("quantity") or event.get("volume") or 0.0)
        event_ts = str(event.get("event_ts") or event.get("ts") or utc_now_iso())
        builder = self._minute_builders.setdefault(instrument, OneMinuteBarBuilder(instrument))
        emitted: List[Bar] = []
        for bar in builder.on_trade(price, qty, event_ts):
            emitted.extend(self._persist_1m_and_derived_5m(bar))
        return emitted

    def _handle_bar_event(self, event: Dict[str, Any]) -> List[Bar]:
        bar = Bar.from_row(dict(event, source=event.get("source") or "cqg"))
        emitted = self._persisted.on_raw_event(dict(as_row(bar), type="bar"))
        self._append_bar_audit(bar, "vendor_bar", "")
        if bar.timeframe == "1m" and emitted:
            emitted_5m = []
            agg = self._five_minute_aggregators.setdefault(bar.instrument, FiveMinuteBarAggregator(bar.instrument))
            for five in agg.on_bar(bar):
                self._persisted.on_completed_bar("5m", five)
                self._append_bar_audit(five, "derived_5m", "")
                emitted_5m.append(five)
            emitted.extend(emitted_5m)
        return emitted

    def _persist_1m_and_derived_5m(self, bar: Bar) -> List[Bar]:
        emitted: List[Bar] = []
        emitted.extend(self._persisted.on_raw_event(dict(as_row(bar), type="bar")))
        self._append_bar_audit(bar, "derived_1m", "")
        agg = self._five_minute_aggregators.setdefault(bar.instrument, FiveMinuteBarAggregator(bar.instrument))
        for five in agg.on_bar(bar):
            self._persisted.on_completed_bar("5m", five)
            self._append_bar_audit(five, "derived_5m", "")
            emitted.append(five)
        return emitted

    def _persist_raw_market_event(self, event: Dict[str, Any]) -> None:
        day = str(event.get("event_ts") or event.get("ts") or utc_now_iso())[:10]
        self.store.append_event("raw_market_data/cqg/%s" % day, event)

    def _write_market_data_status(self) -> None:
        health = self._persisted.health()
        self.store.write_json(
            "market_data_status.json",
            {
                "provider": "cqg",
                "status": "blocked" if self._blocking_reason else self._market_status,
                "blocking_reason": self._blocking_reason,
                "updated_at": utc_now_iso(),
                "contract_refs": {instrument: as_ref_row(ref) for instrument, ref in self.contract_refs.items()},
                "feed_health": {key: str(value) for key, value in health.__dict__.items()},
            },
        )

    def _append_bar_audit(self, bar: Bar, event: str, details: str) -> None:
        path = self.store.root / "feed_broker_bar_audit.csv"
        exists = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["ts", "event", "instrument", "timeframe", "bar_ts", "source", "status", "details"],
            )
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "ts": utc_now_iso(),
                    "event": event,
                    "instrument": bar.instrument,
                    "timeframe": bar.timeframe,
                    "bar_ts": bar.ts,
                    "source": bar.source,
                    "status": "blocked" if self._blocking_reason else "ok",
                    "details": details,
                }
            )


class CqgBroker(BaseBroker):
    """CQG broker boundary for demo/sim first order routing.

    CQG is the order/fill/position truth when this broker is enabled. Local CSV
    state is an audit mirror and restart aid; fills should arrive through
    :meth:`on_fill`, not through completed-bar simulation.
    """

    def __init__(
        self,
        store: FlatFileStore,
        config: Optional[CqgWebApiConfig] = None,
        client: Optional[CqgWebApiClient] = None,
        allow_live_routing: bool = False,
        use_native_compound_orders: bool = False,
    ):
        self.store = store
        self.store.ensure()
        self.config = config or CqgWebApiConfig.from_env()
        self.client = client
        self.allow_live_routing = bool(allow_live_routing)
        self.use_native_compound_orders = bool(use_native_compound_orders)
        if self.config.env != "demo" and not self.allow_live_routing:
            raise CqgConfigurationError("CQG production routing is disabled unless allow_live_routing=True")
        self._orders_cache: Dict[str, BrokerOrder] = {order.broker_order_id: order for order in self.store.load_orders()}
        self._intents_cache: Dict[str, OrderIntent] = {intent.intent_id: intent for intent in self.store.load_order_intents()}
        self._positions_cache: Dict[str, Position] = {pos.position_id: pos for pos in self.store.load_positions()}
        self._active_order_ids = {
            order.broker_order_id: True
            for order in self._orders_cache.values()
            if order.status in {"submitted", "partially_filled"}
        }

    def get_active_contract(self, instrument: str) -> str:
        return self.config.contract_map.get(instrument.upper(), instrument)

    def get_bars(self, instrument: str, timeframe: str, limit: int = 500) -> List[Bar]:
        bars = self.store.read_bars(instrument, timeframe)
        return bars[-limit:]

    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        self._require_trade_subscription_first()
        intent = replace(intent, status="submitted", updated_at=utc_now_iso())
        order = BrokerOrder.from_intent(intent)
        self._intents_cache[intent.intent_id] = intent
        self._orders_cache[order.broker_order_id] = order
        self._active_order_ids[order.broker_order_id] = True
        self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="submitted"))
        self.store.upsert_row("orders", "broker_order_id", as_row(order))
        payload = self.order_intent_to_cqg_payload(intent, order)
        self._emit_order_event({"event": "submit", "cqg_payload": payload, **as_row(order)})
        self._send_order_payload(payload)
        return order

    def modify_order(
        self,
        broker_order_id: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reason: str = "",
        bracket_stop_price: Optional[float] = None,
        bracket_target_price: Optional[float] = None,
        live_after_ts: Optional[str] = None,
    ) -> BrokerOrder:
        order = self._get_order(broker_order_id)
        if order.status not in {"submitted", "partially_filled"}:
            raise ValueError("Cannot modify CQG order %s in status %s" % (broker_order_id, order.status))
        updated = replace(
            order,
            limit_price=limit_price if limit_price is not None else order.limit_price,
            stop_price=stop_price if stop_price is not None else order.stop_price,
            live_after_ts=live_after_ts if live_after_ts is not None else order.live_after_ts,
            updated_at=utc_now_iso(),
        )
        self._orders_cache[updated.broker_order_id] = updated
        self._active_order_ids[updated.broker_order_id] = True
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        payload = {"action": "modify", "broker_order_id": broker_order_id, "reason": reason, **self._cqg_order_fields(updated)}
        self._emit_order_event({"event": "modify", "cqg_payload": payload, **as_row(updated)})
        self._send_order_payload(payload)
        return updated

    def cancel_order(self, broker_order_id: str, reason: str = "") -> BrokerOrder:
        order = self._get_order(broker_order_id)
        if order.status in {"filled", "cancelled"}:
            return order
        updated = replace(order, status="cancelled", updated_at=utc_now_iso())
        self._orders_cache[updated.broker_order_id] = updated
        self._active_order_ids.pop(updated.broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        payload = {"action": "cancel", "broker_order_id": broker_order_id, "reason": reason}
        self._emit_order_event({"event": "cancel", "cqg_payload": payload, **as_row(updated)})
        self._send_order_payload(payload)
        return updated

    def reconcile_orders(self) -> List[BrokerOrder]:
        return [self._orders_cache[order_id] for order_id in self._active_order_ids]

    def reconcile_positions(self) -> List[Position]:
        return list(self._positions_cache.values())

    def attach_bracket(self, parent_order: BrokerOrder, intent: OrderIntent) -> List[BrokerOrder]:
        if self.use_native_compound_orders:
            self._emit_order_event(
                {
                    "event": "native_bracket_expected",
                    "parent_order_id": parent_order.broker_order_id,
                    "intent_id": intent.intent_id,
                    "mode": "native_cqg_compound",
                }
            )
            return []
        if parent_order.status != "filled":
            return []
        children: List[BrokerOrder] = []
        oco = intent.oco_group or ("%s_bracket" % parent_order.broker_order_id)
        exit_side = "sell" if parent_order.side == "buy" else "buy"
        if intent.bracket_stop_price is not None:
            children.append(
                self.submit_order_intent(
                    OrderIntent.create(
                        strategy_id=parent_order.strategy_id,
                        trade_id=parent_order.trade_id,
                        instrument=parent_order.instrument,
                        account_mode=parent_order.account_mode,
                        side=exit_side,
                        order_type="stop",
                        quantity=parent_order.quantity,
                        stop_price=intent.bracket_stop_price,
                        reason="protective_stop",
                        requires_verification=False,
                        parent_intent_id=intent.intent_id,
                        reduce_only=True,
                        bracket_role="runner_stop" if intent.bracket_role == "runner_entry" else "stop",
                        oco_group=oco,
                    )
                )
            )
        if intent.bracket_target_price is not None:
            children.append(
                self.submit_order_intent(
                    OrderIntent.create(
                        strategy_id=parent_order.strategy_id,
                        trade_id=parent_order.trade_id,
                        instrument=parent_order.instrument,
                        account_mode=parent_order.account_mode,
                        side=exit_side,
                        order_type="limit",
                        quantity=parent_order.quantity,
                        limit_price=intent.bracket_target_price,
                        reason="target",
                        requires_verification=False,
                        parent_intent_id=intent.intent_id,
                        reduce_only=True,
                        bracket_role="target",
                        oco_group=oco,
                    )
                )
            )
        if children:
            self._emit_order_event(
                {
                    "event": "local_managed_oco_bracket",
                    "parent_order_id": parent_order.broker_order_id,
                    "child_order_ids": ",".join(order.broker_order_id for order in children),
                    "unsafe_for_live_until_demo_validated": True,
                }
            )
        return children

    def process_bar(self, bar: Bar) -> List[Fill]:
        return []

    def process_market_close_bar(self, bar: Bar) -> List[Fill]:
        return []

    def on_order_status(self, event: Dict[str, Any]) -> Optional[BrokerOrder]:
        broker_order_id = str(event.get("broker_order_id") or event.get("cl_order_id") or "")
        if not broker_order_id:
            return None
        order = self._orders_cache.get(broker_order_id)
        if order is None:
            return None
        status = str(event.get("status") or order.status).lower()
        remaining = int(float(event.get("remaining_quantity") if event.get("remaining_quantity") is not None else order.remaining_quantity))
        updated = replace(order, status=status, remaining_quantity=remaining, updated_at=utc_now_iso())
        self._orders_cache[broker_order_id] = updated
        if status in {"submitted", "partially_filled", "working", "parked"}:
            self._active_order_ids[broker_order_id] = True
        else:
            self._active_order_ids.pop(broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        self._emit_order_event({"event": "order_status", **event})
        return updated

    def on_fill(self, event: Dict[str, Any]) -> Fill:
        broker_order_id = str(event.get("broker_order_id") or event.get("cl_order_id") or "")
        order = self._get_order(broker_order_id)
        quantity = int(float(event.get("quantity") or event.get("fill_qty") or order.remaining_quantity))
        price = float(event.get("price") or event.get("fill_price"))
        fill = Fill(
            fill_id=str(event.get("fill_id") or new_id("fill")),
            broker_order_id=order.broker_order_id,
            intent_id=order.intent_id,
            strategy_id=order.strategy_id,
            trade_id=order.trade_id,
            instrument=order.instrument,
            account_mode=order.account_mode,
            side=order.side,
            quantity=quantity,
            price=price,
            ts=str(event.get("event_ts") or event.get("ts") or utc_now_iso()),
            reason=order.bracket_role or order.order_type,
        )
        remaining = max(order.remaining_quantity - quantity, 0)
        status = "filled" if remaining == 0 else "partially_filled"
        updated = replace(order, remaining_quantity=remaining, status=status, updated_at=utc_now_iso())
        self._orders_cache[order.broker_order_id] = updated
        if status == "filled":
            self._active_order_ids.pop(order.broker_order_id, None)
        else:
            self._active_order_ids[order.broker_order_id] = True
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        self.store.append_rows("fills", [as_row(fill)])
        self.store.append_event("fills", as_row(fill))
        self._apply_fill_to_position(fill)
        if updated.oco_group:
            self._cancel_local_oco_peers(updated)
        self._emit_order_event({"event": "fill", **event, **as_row(fill)})
        return fill

    def go_flat(self, account_id: Optional[str] = None) -> List[BrokerOrder]:
        payload = {"action": "go_flat", "account_id": account_id or self.config.account_id}
        self._emit_order_event({"event": "go_flat", "cqg_payload": payload})
        self._send_order_payload(payload)
        for order_id in list(self._active_order_ids):
            self.cancel_order(order_id, reason="go_flat")
        flatten_orders: List[BrokerOrder] = []
        for pos in self.reconcile_positions():
            if pos.quantity == 0:
                continue
            side = "sell" if pos.quantity > 0 else "buy"
            flatten_orders.append(
                self.submit_order_intent(
                    OrderIntent.create(
                        strategy_id=pos.strategy_id,
                        trade_id="go_flat",
                        instrument=pos.instrument,
                        account_mode=pos.account_mode,
                        side=side,
                        order_type="market",
                        quantity=abs(pos.quantity),
                        reason="go_flat",
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role="close",
                    )
                )
            )
        return flatten_orders

    def order_intent_to_cqg_payload(self, intent: OrderIntent, order: BrokerOrder) -> Dict[str, Any]:
        payload = {"action": "new_order", **self._cqg_order_fields(order)}
        payload["client_order_id"] = order.broker_order_id
        payload["intent_id"] = intent.intent_id
        payload["account_id"] = self.config.account_id
        payload["tif"] = intent.tif
        payload["reduce_only"] = intent.reduce_only
        if intent.bracket_stop_price is not None or intent.bracket_target_price is not None:
            payload["bracket"] = {
                "stop_price": intent.bracket_stop_price,
                "target_price": intent.bracket_target_price,
                "native_requested": self.use_native_compound_orders,
            }
        return payload

    def _cqg_order_fields(self, order: BrokerOrder) -> Dict[str, Any]:
        contract = self.get_active_contract(order.instrument)
        return {
            "instrument": order.instrument,
            "cqg_symbol": contract,
            "order_type": order.order_type,
            "side": order.side,
            "quantity": order.quantity,
            "remaining_quantity": order.remaining_quantity,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
            "oco_group": order.oco_group,
            "live_after_ts": order.live_after_ts,
            "expires_after_ts": order.expires_after_ts,
        }

    def _send_order_payload(self, payload: Dict[str, Any]) -> None:
        if self.client is None:
            return
        message = self.client.build_order_request(payload)
        encoded = self.client.encode(message)
        self._emit_order_event({"event": "encoded_order_request", "request_id": message.get("request_id"), "bytes": len(encoded)})

    def _emit_order_event(self, event: Dict[str, Any]) -> None:
        self.store.append_event("cqg_order_events", event)

    def _require_trade_subscription_first(self) -> None:
        self.store.append_event(
            "cqg_session_events",
            {"event": "trade_subscription_required_before_orders", "account_id": self.config.account_id},
        )

    def _apply_fill_to_position(self, fill: Fill) -> None:
        key = "%s|%s|%s" % (fill.strategy_id, fill.instrument, fill.account_mode)
        pos = self._positions_cache.get(key)
        signed_qty = fill.quantity if fill.side == "buy" else -fill.quantity
        if pos is None:
            new_qty = signed_qty
            avg_price = fill.price
            realized = 0.0
        else:
            old_qty = pos.quantity
            new_qty = old_qty + signed_qty
            avg_price = pos.avg_price
            realized = pos.realized_pnl
            if old_qty == 0 or (old_qty > 0 and signed_qty > 0) or (old_qty < 0 and signed_qty < 0):
                total_abs = abs(old_qty) + abs(signed_qty)
                avg_price = ((abs(old_qty) * pos.avg_price) + (abs(signed_qty) * fill.price)) / max(total_abs, 1)
            else:
                closing_qty = min(abs(old_qty), abs(signed_qty))
                realized += (fill.price - pos.avg_price) * closing_qty if old_qty > 0 else (pos.avg_price - fill.price) * closing_qty
                if new_qty == 0:
                    avg_price = 0.0
                elif abs(signed_qty) > abs(old_qty):
                    avg_price = fill.price
        updated = Position(
            position_id=key,
            strategy_id=fill.strategy_id,
            instrument=fill.instrument,
            account_mode=fill.account_mode,
            quantity=new_qty,
            avg_price=avg_price,
            realized_pnl=realized,
            updated_at=utc_now_iso(),
        )
        self._positions_cache[key] = updated
        self.store.upsert_row("positions", "position_id", as_row(updated))

    def _cancel_local_oco_peers(self, filled_order: BrokerOrder) -> None:
        for order in list(self._orders_cache.values()):
            if order.broker_order_id == filled_order.broker_order_id:
                continue
            if order.oco_group and order.oco_group == filled_order.oco_group and order.status in {"submitted", "partially_filled"}:
                self.cancel_order(order.broker_order_id, reason="local_oco_peer_filled")

    def _get_order(self, broker_order_id: str) -> BrokerOrder:
        order = self._orders_cache.get(broker_order_id)
        if order is None:
            raise KeyError("Broker order not found: %s" % broker_order_id)
        return order


def parse_contract_map(raw: str) -> Dict[str, str]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        parsed = json.loads(raw)
        return {str(k).upper(): str(v) for k, v in parsed.items()}
    out: Dict[str, str] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        if "=" not in item:
            raise CqgConfigurationError("CQG_CONTRACT_MAP entries must look like MNQ=F.US.MNQM26")
        key, value = item.split("=", 1)
        out[key.strip().upper()] = value.strip()
    return out


def parse_cqg_ts(value: str) -> datetime:
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def price_to_scaled(price: float, price_scale: int = 2) -> int:
    return int(round(float(price) * (10 ** int(price_scale))))


def scaled_to_price(scaled_price: int, price_scale: int = 2) -> float:
    return float(scaled_price) / float(10 ** int(price_scale))


def as_ref_row(ref: CqgContractRef) -> Dict[str, Any]:
    return {
        "instrument": ref.instrument,
        "cqg_symbol": ref.cqg_symbol,
        "contract_id": ref.contract_id,
        "resolved_at": ref.resolved_at,
        "price_scale": ref.price_scale,
        "metadata": ref.metadata,
    }


def load_jsonl_events(path: Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
