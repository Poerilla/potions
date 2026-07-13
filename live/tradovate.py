from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .broker import BaseBroker
from .live_feed import FeedHealth, LiveFeedAdapter, PersistedLiveFeedAdapter
from .models import Bar, BrokerOrder, Fill, OrderIntent, Position, as_row, new_id, utc_now_iso
from .store import FlatFileStore
from .supervisor import RuntimeSupervisor


REQUIRED_OPENAPI_ROUTES: Tuple[str, ...] = (
    "/auth/accesstokenrequest",
    "/auth/renewaccesstoken",
    "/account/list",
    "/contract/find",
    "/contract/suggest",
    "/contract/rollcontract",
    "/order/placeorder",
    "/order/placeoco",
    "/order/placeoso",
    "/order/cancelorder",
    "/order/modifyorder",
    "/order/liquidateposition",
    "/order/liquidatepositions",
    "/position/list",
    "/user/syncrequest",
)

DEFAULT_INSTRUMENTS = ("MNQ", "NQ", "MYM")
WEBSOCKET_HEARTBEAT_SECONDS = 2.5


class TradovateAdapterError(RuntimeError):
    pass


class TradovateConfigurationError(TradovateAdapterError):
    pass


class TradovateProtocolError(TradovateAdapterError):
    pass


class TradovateRoutingBlocked(TradovateAdapterError):
    pass


@dataclass(frozen=True)
class TradovateOpenApiCatalog:
    path: Path = field(default_factory=lambda: Path(__file__).resolve().with_name("openapi.json"))
    spec: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "TradovateOpenApiCatalog":
        spec_path = Path(path) if path is not None else Path(__file__).resolve().with_name("openapi.json")
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        return cls(path=spec_path, spec=raw)

    def validate_required_routes(self, routes: Iterable[str] = REQUIRED_OPENAPI_ROUTES) -> None:
        paths = self.spec.get("paths") or {}
        missing = [route for route in routes if route not in paths]
        if missing:
            raise TradovateConfigurationError(
                "Tradovate OpenAPI spec %s is missing required routes: %s" % (self.path, ", ".join(missing))
            )

    def server_urls(self) -> List[str]:
        return [str(item.get("url")) for item in self.spec.get("servers", []) if item.get("url")]

    def operation_id(self, route: str, method: str = "post") -> str:
        route_obj = (self.spec.get("paths") or {}).get(route) or {}
        method_obj = route_obj.get(method.lower()) or {}
        return str(method_obj.get("operationId") or "")

    def request_schema_ref(self, route: str, method: str = "post") -> str:
        route_obj = (self.spec.get("paths") or {}).get(route) or {}
        method_obj = route_obj.get(method.lower()) or {}
        body = method_obj.get("requestBody") or {}
        content = body.get("content") or {}
        schema = (content.get("application/json") or {}).get("schema") or {}
        return str(schema.get("$ref") or "")

    def schema_required(self, schema_name: str) -> List[str]:
        schema = ((self.spec.get("components") or {}).get("schemas") or {}).get(schema_name) or {}
        return [str(item) for item in schema.get("required") or []]


@dataclass(frozen=True)
class TradovateConfig:
    env: str = "demo"
    rest_endpoint: str = "https://demo.tradovateapi.com/v1"
    ws_endpoint: str = "wss://demo.tradovateapi.com/v1/websocket"
    md_ws_endpoint: str = "wss://demo.tradovateapi.com/v1/websocket"
    username: str = ""
    password: str = ""
    app_id: str = "potions-live"
    app_version: str = "potions-tradovate-adapter-dev"
    cid: str = ""
    secret: str = ""
    account_id: str = ""
    account_spec: str = ""
    contract_map: Dict[str, str] = field(default_factory=dict)
    contract_id_map: Dict[str, str] = field(default_factory=dict)
    openapi_path: Path = field(default_factory=lambda: Path(__file__).resolve().with_name("openapi.json"))

    @classmethod
    def from_env(cls, environ: Optional[Dict[str, str]] = None) -> "TradovateConfig":
        env = environ if environ is not None else os.environ
        tradovate_env = env.get("TRADOVATE_ENV", "demo").strip().lower() or "demo"
        default_rest = "https://demo.tradovateapi.com/v1" if tradovate_env == "demo" else "https://live.tradovateapi.com/v1"
        default_ws = default_rest.replace("https://", "wss://") + "/websocket"
        return cls(
            env=tradovate_env,
            rest_endpoint=(env.get("TRADOVATE_REST_ENDPOINT") or default_rest).rstrip("/"),
            ws_endpoint=env.get("TRADOVATE_WS_ENDPOINT") or default_ws,
            md_ws_endpoint=env.get("TRADOVATE_MD_WS_ENDPOINT") or env.get("TRADOVATE_WS_ENDPOINT") or default_ws,
            username=env.get("TRADOVATE_USERNAME", ""),
            password=env.get("TRADOVATE_PASSWORD", ""),
            app_id=env.get("TRADOVATE_APP_ID", "potions-live"),
            app_version=env.get("TRADOVATE_APP_VERSION", "potions-tradovate-adapter-dev"),
            cid=env.get("TRADOVATE_CID", ""),
            secret=env.get("TRADOVATE_SECRET", ""),
            account_id=env.get("TRADOVATE_ACCOUNT_ID", ""),
            account_spec=env.get("TRADOVATE_ACCOUNT_SPEC") or env.get("TRADOVATE_USERNAME", ""),
            contract_map=parse_contract_map(env.get("TRADOVATE_CONTRACT_MAP", "")),
            contract_id_map=parse_contract_map(env.get("TRADOVATE_CONTRACT_ID_MAP", "")),
            openapi_path=Path(env.get("TRADOVATE_OPENAPI_PATH") or Path(__file__).resolve().with_name("openapi.json")),
        )

    @classmethod
    def from_json_file(cls, path: Path, environ: Optional[Dict[str, str]] = None) -> "TradovateConfig":
        base = cls.from_env(environ)
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        merged = {
            "env": raw.get("env", base.env),
            "rest_endpoint": raw.get("rest_endpoint", base.rest_endpoint),
            "ws_endpoint": raw.get("ws_endpoint", base.ws_endpoint),
            "md_ws_endpoint": raw.get("md_ws_endpoint", base.md_ws_endpoint),
            "username": raw.get("username", base.username),
            "password": raw.get("password", base.password),
            "app_id": raw.get("app_id", base.app_id),
            "app_version": raw.get("app_version", base.app_version),
            "cid": str(raw.get("cid", base.cid)),
            "secret": raw.get("secret", base.secret),
            "account_id": str(raw.get("account_id", base.account_id)),
            "account_spec": raw.get("account_spec", base.account_spec),
            "contract_map": dict(base.contract_map),
            "contract_id_map": dict(base.contract_id_map),
            "openapi_path": Path(raw.get("openapi_path", base.openapi_path)),
        }
        merged["contract_map"].update({str(k).upper(): str(v) for k, v in (raw.get("contract_map") or {}).items()})
        merged["contract_id_map"].update({str(k).upper(): str(v) for k, v in (raw.get("contract_id_map") or {}).items()})
        return cls(**merged)

    def validate_for_auth(self) -> None:
        missing = []
        for field_name in ("rest_endpoint", "username", "password", "app_id", "app_version"):
            if not getattr(self, field_name):
                missing.append(field_name)
        if missing:
            raise TradovateConfigurationError("Missing Tradovate config fields: %s" % ", ".join(missing))

    def account_id_int(self) -> int:
        if not self.account_id:
            raise TradovateConfigurationError("TRADOVATE_ACCOUNT_ID is required")
        return int(float(self.account_id))

    def symbol_for(self, instrument: str) -> str:
        key = instrument.upper()
        return self.contract_map.get(key, key)

    def contract_id_for(self, instrument: str) -> Optional[int]:
        key = instrument.upper()
        value = self.contract_id_map.get(key)
        if value is None:
            value = self.contract_map.get(key)
        if value is None:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None


@dataclass(frozen=True)
class TradovateToken:
    access_token: str
    md_access_token: str = ""
    user_id: str = ""
    expires_at: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_response(cls, raw: Dict[str, Any]) -> "TradovateToken":
        return cls(
            access_token=str(raw.get("accessToken") or raw.get("access_token") or ""),
            md_access_token=str(raw.get("mdAccessToken") or raw.get("md_access_token") or ""),
            user_id=str(raw.get("userId") or raw.get("user_id") or ""),
            expires_at=str(raw.get("expirationTime") or raw.get("expiresAt") or ""),
            raw=dict(raw),
        )


@dataclass(frozen=True)
class TradovateWsFrame:
    frame_type: str
    payload: Any = None


@dataclass(frozen=True)
class TradovateContractRef:
    instrument: str
    symbol: str
    contract_id: str
    resolved_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class TradovateWebApiClient:
    def __init__(
        self,
        config: TradovateConfig,
        store: Optional[FlatFileStore] = None,
        catalog: Optional[TradovateOpenApiCatalog] = None,
        http_requester: Optional[Callable[[str, str, Optional[Dict[str, Any]], Optional[str]], Dict[str, Any]]] = None,
    ):
        self.config = config
        self.store = store
        self.catalog = catalog or TradovateOpenApiCatalog.load(config.openapi_path)
        self.catalog.validate_required_routes()
        self.http_requester = http_requester or self._urllib_request_json
        self._request_id = 0
        self.token: Optional[TradovateToken] = None

    def next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def build_access_token_body(self) -> Dict[str, Any]:
        return {
            "name": self.config.username,
            "password": self.config.password,
            "appId": self.config.app_id,
            "appVersion": self.config.app_version,
            "cid": self.config.cid,
            "sec": self.config.secret,
        }

    def build_renew_access_token_body(self) -> Dict[str, Any]:
        return {}

    def request_access_token(self) -> TradovateToken:
        self.config.validate_for_auth()
        raw = self.request_json("POST", "/auth/accesstokenrequest", self.build_access_token_body())
        self.token = TradovateToken.from_response(raw)
        self.record_session_event({"event": "access_token_received", "user_id": self.token.user_id})
        return self.token

    def renew_access_token(self, access_token: Optional[str] = None) -> TradovateToken:
        token = access_token or (self.token.access_token if self.token else "")
        raw = self.request_json("POST", "/auth/renewaccesstoken", self.build_renew_access_token_body(), token)
        self.token = TradovateToken.from_response(raw)
        self.record_session_event({"event": "access_token_renewed", "user_id": self.token.user_id})
        return self.token

    def request_json(
        self,
        method: str,
        route: str,
        body: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.http_requester(method.upper(), route, body, access_token)

    def build_ws_request_frame(
        self,
        endpoint: str,
        request_id: Optional[int] = None,
        query: str = "",
        body: Any = None,
    ) -> str:
        rid = self.next_request_id() if request_id is None else int(request_id)
        if body is None:
            body_text = ""
        elif isinstance(body, str):
            body_text = body
        else:
            body_text = json.dumps(body, sort_keys=True)
        return "%s\n%d\n%s\n%s" % (endpoint, rid, query or "", body_text)

    def build_authorize_frame(self, access_token: str, request_id: Optional[int] = None) -> str:
        return self.build_ws_request_frame("authorize", request_id=request_id, body=access_token)

    def build_user_sync_frame(self, request_id: Optional[int] = None, split_responses: bool = True) -> str:
        return self.build_ws_request_frame("user/syncrequest", request_id=request_id, body={"splitResponses": split_responses})

    def build_contract_roll_frame(self, symbol: str, request_id: Optional[int] = None) -> str:
        return self.build_ws_request_frame(
            "contract/rollcontract",
            request_id=request_id,
            body={"name": symbol, "forward": True, "ifExpired": True},
        )

    def heartbeat_frame(self) -> str:
        return "[]"

    def heartbeat_due(self, last_received_at: datetime, now: Optional[datetime] = None) -> bool:
        now = now or datetime.utcnow()
        return (now - last_received_at).total_seconds() >= WEBSOCKET_HEARTBEAT_SECONDS

    def parse_ws_frame(self, raw: str) -> TradovateWsFrame:
        if raw == "[]":
            return TradovateWsFrame("client_heartbeat", [])
        if not raw:
            raise TradovateProtocolError("Empty Tradovate websocket frame")
        frame_type = raw[0]
        payload_text = raw[1:]
        if frame_type not in {"o", "h", "a", "c"}:
            raise TradovateProtocolError("Unsupported Tradovate websocket frame type: %s" % frame_type)
        if not payload_text:
            return TradovateWsFrame(frame_type, None)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise TradovateProtocolError("Invalid Tradovate websocket JSON payload") from exc
        return TradovateWsFrame(frame_type, payload)

    def record_raw_frame(self, raw: str, stream: str = "tradovate_session_events") -> None:
        if self.store is not None:
            self.store.append_event(stream, {"event": "raw_ws_frame", "raw": raw})

    def record_session_event(self, event: Dict[str, Any]) -> None:
        if self.store is not None:
            self.store.append_event("tradovate_session_events", event)

    def _urllib_request_json(
        self,
        method: str,
        route: str,
        body: Optional[Dict[str, Any]],
        access_token: Optional[str],
    ) -> Dict[str, Any]:
        url = self.config.rest_endpoint.rstrip("/") + route
        data = None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = "Bearer %s" % access_token
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec - endpoint is user-configured broker API.
                payload = resp.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise TradovateAdapterError("Tradovate HTTP %s for %s: %s" % (exc.code, route, text)) from exc


class OneMinuteBarBuilder:
    def __init__(self, instrument: str, source: str = "tradovate"):
        self.instrument = instrument
        self.source = source
        self._current_key: Optional[datetime] = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0.0

    def on_trade(self, price: float, quantity: float, ts: str) -> List[Bar]:
        event_dt = parse_tradovate_ts(ts)
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
            source=self.source,
        )


class FiveMinuteBarAggregator:
    def __init__(self, instrument: str, source: str = "tradovate_1m_aggregate"):
        self.instrument = instrument
        self.source = source
        self._bucket_key: Optional[datetime] = None
        self._bars: List[Bar] = []

    def on_bar(self, bar: Bar) -> List[Bar]:
        if bar.timeframe != "1m":
            return []
        dt = parse_tradovate_ts(bar.ts)
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
                source=self.source,
            )
        ]


class TradovateMarketDataFeedAdapter(LiveFeedAdapter):
    BLOCKING_STATUSES = {"access_denied", "delayed", "downgraded", "stale", "unresolved_contract", "permission_denied"}

    def __init__(
        self,
        store: FlatFileStore,
        config: Optional[TradovateConfig] = None,
        on_bar: Optional[Callable[[Bar], None]] = None,
        stale_after_seconds: float = 30.0,
        clock: Callable[[], datetime] = datetime.utcnow,
        supervisor: Optional[RuntimeSupervisor] = None,
    ):
        self.store = store
        self.store.ensure()
        self.config = config or TradovateConfig.from_env()
        self.supervisor = supervisor
        self._persisted = PersistedLiveFeedAdapter(
            store,
            on_bar=on_bar,
            allowed_timeframes=("1m", "5m", "15m", "1h", "D"),
            stale_after_seconds=stale_after_seconds,
            clock=clock,
        )
        self.contract_refs: Dict[str, TradovateContractRef] = {}
        self.chart_subscriptions: Dict[str, str] = {}
        self._minute_builders: Dict[str, OneMinuteBarBuilder] = {}
        self._five_minute_aggregators: Dict[str, FiveMinuteBarAggregator] = {}
        self._blocking_reason = ""
        self._market_status = "init"
        self._write_market_data_status()

    def resolve_contract(
        self,
        instrument: str,
        contract_id: str,
        symbol: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TradovateContractRef:
        ref = TradovateContractRef(
            instrument=instrument.upper(),
            symbol=symbol or self.config.symbol_for(instrument),
            contract_id=str(contract_id),
            resolved_at=utc_now_iso(),
            metadata=metadata or {},
        )
        self.contract_refs[ref.instrument] = ref
        self._blocking_reason = ""
        self.store.append_event("tradovate_session_events", {"event": "contract_resolved", **as_ref_row(ref)})
        self._write_market_data_status()
        return ref

    def register_chart_subscription(self, instrument: str, subscription_id: Any) -> None:
        self.chart_subscriptions[str(subscription_id)] = instrument.upper()
        self.store.append_event(
            "tradovate_session_events",
            {"event": "chart_subscription_registered", "instrument": instrument.upper(), "subscription_id": str(subscription_id)},
        )

    def on_raw_event(self, event: Dict[str, Any]) -> List[Bar]:
        event = dict(event)
        self._persist_raw_market_event(event)
        if event.get("e") == "chart":
            return self._handle_chart_event(event)
        if event.get("e") == "md":
            return self._handle_market_data_event(event)
        event_type = str(event.get("type") or "")
        if event_type in {"symbol_resolution", "contract_resolution"}:
            self.resolve_contract(
                str(event["instrument"]),
                str(event["contract_id"]),
                symbol=str(event.get("symbol") or event.get("tradovate_symbol") or ""),
                metadata=dict(event.get("metadata") or {}),
            )
            return []
        if event_type == "chart_subscription":
            self.register_chart_subscription(str(event["instrument"]), event.get("subscription_id"))
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
        if self.supervisor is not None and base.stale:
            self.supervisor.freeze_entries("tradovate_feed_stale", {"stale_seconds": base.stale_seconds})
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
            self.store.append_event("market_data_quality", {"event": "tradovate_blocking_status", **event})
            if self.supervisor is not None:
                self.supervisor.freeze_entries("tradovate_market_data_%s" % self._blocking_reason, event)
        elif status in {"ok", "realtime", "subscribed"}:
            self._blocking_reason = ""
        self._write_market_data_status()

    def _handle_trade_event(self, event: Dict[str, Any]) -> List[Bar]:
        instrument = str(event["instrument"]).upper()
        if instrument not in self.contract_refs:
            self._blocking_reason = "unresolved_contract"
            self._write_market_data_status()
            self.store.append_event("market_data_quality", {"event": "tradovate_trade_without_contract_ref", **event})
            return []
        price = float(event.get("price"))
        qty = float(event.get("quantity") or event.get("volume") or event.get("size") or 0.0)
        event_ts = str(event.get("event_ts") or event.get("ts") or event.get("timestamp") or utc_now_iso())
        builder = self._minute_builders.setdefault(instrument, OneMinuteBarBuilder(instrument))
        emitted: List[Bar] = []
        for bar in builder.on_trade(price, qty, event_ts):
            emitted.extend(self._persist_1m_and_derived_5m(bar))
        return emitted

    def _handle_bar_event(self, event: Dict[str, Any]) -> List[Bar]:
        bar = Bar.from_row(dict(event, source=event.get("source") or "tradovate"))
        emitted = self._persisted.on_raw_event(dict(as_row(bar), type="bar"))
        self._append_bar_audit(bar, "vendor_bar", "")
        if bar.timeframe == "1m" and emitted:
            emitted.extend(self._derive_5m(bar))
        return emitted

    def _handle_chart_event(self, event: Dict[str, Any]) -> List[Bar]:
        payload = event.get("d") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        emitted: List[Bar] = []
        for chart in payload.get("charts", []):
            sub_id = str(chart.get("id") or event.get("subscription_id") or "")
            instrument = str(event.get("instrument") or self.chart_subscriptions.get(sub_id) or "").upper()
            if not instrument:
                self.store.append_event("market_data_quality", {"event": "tradovate_chart_without_instrument", **event})
                continue
            if chart.get("eoh"):
                self.store.append_event("tradovate_session_events", {"event": "chart_end_of_history", "instrument": instrument, "subscription_id": sub_id})
                continue
            for raw_bar in chart.get("bars", []):
                bar = tradovate_chart_bar_to_bar(raw_bar, instrument, str(event.get("timeframe") or "1m"))
                emitted.extend(self._persisted.on_raw_event(dict(as_row(bar), type="bar")))
                self._append_bar_audit(bar, "tradovate_chart_bar", "")
                if bar.timeframe == "1m":
                    emitted.extend(self._derive_5m(bar))
        return emitted

    def _handle_market_data_event(self, event: Dict[str, Any]) -> List[Bar]:
        payload = event.get("d") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        if "charts" in payload:
            return self._handle_chart_event(dict(event, d=payload))
        return []

    def _persist_1m_and_derived_5m(self, bar: Bar) -> List[Bar]:
        emitted: List[Bar] = []
        emitted.extend(self._persisted.on_raw_event(dict(as_row(bar), type="bar")))
        self._append_bar_audit(bar, "derived_1m", "")
        emitted.extend(self._derive_5m(bar))
        return emitted

    def _derive_5m(self, bar: Bar) -> List[Bar]:
        emitted: List[Bar] = []
        agg = self._five_minute_aggregators.setdefault(bar.instrument, FiveMinuteBarAggregator(bar.instrument))
        for five in agg.on_bar(bar):
            self._persisted.on_completed_bar("5m", five)
            self._append_bar_audit(five, "derived_5m", "")
            emitted.append(five)
        return emitted

    def _persist_raw_market_event(self, event: Dict[str, Any]) -> None:
        day = str(event.get("event_ts") or event.get("ts") or event.get("timestamp") or utc_now_iso())[:10]
        self.store.append_event("raw_market_data/tradovate/%s" % day, event)

    def _write_market_data_status(self) -> None:
        health = self._persisted.health()
        self.store.write_json(
            "market_data_status.json",
            {
                "provider": "tradovate",
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


class TradovateBroker(BaseBroker):
    def __init__(
        self,
        store: FlatFileStore,
        config: Optional[TradovateConfig] = None,
        client: Optional[TradovateWebApiClient] = None,
        allow_live_routing: bool = False,
        server_oco_validated: bool = False,
        supervisor: Optional[RuntimeSupervisor] = None,
    ):
        self.store = store
        self.store.ensure()
        self.config = config or TradovateConfig.from_env()
        self.client = client
        self.allow_live_routing = bool(allow_live_routing)
        self.server_oco_validated = bool(server_oco_validated)
        self.supervisor = supervisor
        if self.config.env != "demo" and not self.allow_live_routing:
            raise TradovateConfigurationError("Tradovate live routing is disabled unless allow_live_routing=True")
        self._orders_cache: Dict[str, BrokerOrder] = {order.broker_order_id: order for order in self.store.load_orders()}
        self._intents_cache: Dict[str, OrderIntent] = {intent.intent_id: intent for intent in self.store.load_order_intents()}
        self._positions_cache: Dict[str, Position] = {pos.position_id: pos for pos in self.store.load_positions()}
        self._active_order_ids = {
            order.broker_order_id: True
            for order in self._orders_cache.values()
            if order.status in {"submitted", "partially_filled", "working", "pendingnew"}
        }
        self._tradovate_order_ids: Dict[str, str] = {}

    def get_active_contract(self, instrument: str) -> str:
        return self.config.symbol_for(instrument)

    def get_bars(self, instrument: str, timeframe: str, limit: int = 500) -> List[Bar]:
        bars = self.store.read_bars(instrument, timeframe)
        return bars[-limit:]

    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        self._require_user_sync_first()
        self._assert_routing_allowed(intent)
        intent = replace(intent, status="submitted", updated_at=utc_now_iso())
        order = BrokerOrder.from_intent(intent)
        self._intents_cache[intent.intent_id] = intent
        self._orders_cache[order.broker_order_id] = order
        self._active_order_ids[order.broker_order_id] = True
        self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="submitted"))
        self.store.upsert_row("orders", "broker_order_id", as_row(order))
        endpoint, payload = self.order_intent_to_tradovate_request(intent, order)
        self._emit_order_event({"event": "submit", "endpoint": endpoint, "tradovate_payload": payload, **as_row(order)})
        self._send_order_payload(endpoint, payload, order.broker_order_id)
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
        if order.status not in {"submitted", "partially_filled", "working", "pendingnew"}:
            raise ValueError("Cannot modify Tradovate order %s in status %s" % (broker_order_id, order.status))
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
        payload = self._modify_payload(updated, broker_order_id)
        payload["text"] = reason or payload.get("text", "")
        self._emit_order_event({"event": "modify", "endpoint": "/order/modifyorder", "tradovate_payload": payload, **as_row(updated)})
        self._send_order_payload("/order/modifyorder", payload, broker_order_id)
        return updated

    def cancel_order(self, broker_order_id: str, reason: str = "") -> BrokerOrder:
        order = self._get_order(broker_order_id)
        if order.status in {"filled", "cancelled"}:
            return order
        updated = replace(order, status="cancelled", updated_at=utc_now_iso())
        self._orders_cache[updated.broker_order_id] = updated
        self._active_order_ids.pop(updated.broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        payload = self._cancel_payload(broker_order_id, reason)
        self._emit_order_event({"event": "cancel", "endpoint": "/order/cancelorder", "tradovate_payload": payload, **as_row(updated)})
        self._send_order_payload("/order/cancelorder", payload, broker_order_id)
        return updated

    def reconcile_orders(self) -> List[BrokerOrder]:
        return [self._orders_cache[order_id] for order_id in self._active_order_ids if order_id in self._orders_cache]

    def reconcile_positions(self) -> List[Position]:
        return list(self._positions_cache.values())

    def reconcile_from_broker_snapshot(
        self,
        orders: Iterable[Dict[str, Any]],
        positions: Iterable[Dict[str, Any]],
    ) -> None:
        if self.supervisor is not None:
            self.supervisor.start_reconciliation("tradovate_snapshot_reconcile")
        self.store.append_event("reconciliation_events", {"event": "tradovate_snapshot_start"})
        for raw_order in orders:
            self.on_order_status(raw_order)
        self._positions_cache = {}
        for raw_position in positions:
            position = self._position_from_tradovate(raw_position)
            self._positions_cache[position.position_id] = position
            self.store.upsert_row("positions", "position_id", as_row(position))
        self.store.append_event(
            "reconciliation_events",
            {
                "event": "tradovate_snapshot_done",
                "orders": len(list(self._orders_cache.values())),
                "positions": len(list(self._positions_cache.values())),
            },
        )
        if self.supervisor is not None:
            self.supervisor.mark_reconciled("tradovate_snapshot_reconciled")

    def attach_bracket(self, parent_order: BrokerOrder, intent: OrderIntent) -> List[BrokerOrder]:
        if self.server_oco_validated:
            self._emit_order_event(
                {
                    "event": "native_bracket_expected",
                    "parent_order_id": parent_order.broker_order_id,
                    "intent_id": intent.intent_id,
                    "mode": "tradovate_oso_oco",
                }
            )
            return []
        if parent_order.account_mode == "live":
            raise TradovateRoutingBlocked("Live bracket attach requires demo-validated Tradovate server-side OCO/OSO")
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
                        bracket_role="stop",
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
        broker_order_id = str(event.get("broker_order_id") or event.get("clOrdId") or event.get("cl_order_id") or "")
        tradovate_order_id = str(event.get("orderId") or event.get("id") or "")
        if broker_order_id and tradovate_order_id:
            self._tradovate_order_ids[broker_order_id] = tradovate_order_id
        if not broker_order_id and tradovate_order_id:
            for local_id, remote_id in self._tradovate_order_ids.items():
                if remote_id == tradovate_order_id:
                    broker_order_id = local_id
                    break
        if not broker_order_id:
            return None
        order = self._orders_cache.get(broker_order_id)
        if order is None:
            return None
        status = normalize_tradovate_order_status(str(event.get("ordStatus") or event.get("status") or order.status))
        remaining = int(float(event.get("remaining_quantity") if event.get("remaining_quantity") is not None else event.get("leavesQty") if event.get("leavesQty") is not None else order.remaining_quantity))
        updated = replace(order, status=status, remaining_quantity=remaining, updated_at=utc_now_iso())
        self._orders_cache[broker_order_id] = updated
        if status in {"submitted", "partially_filled", "working", "pendingnew"}:
            self._active_order_ids[broker_order_id] = True
        else:
            self._active_order_ids.pop(broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        self._emit_order_event({"event": "order_status", **event})
        return updated

    def on_fill(self, event: Dict[str, Any]) -> Fill:
        broker_order_id = str(event.get("broker_order_id") or event.get("clOrdId") or event.get("cl_order_id") or "")
        order = self._get_order(broker_order_id)
        quantity = int(float(event.get("quantity") or event.get("fillQty") or event.get("fill_qty") or order.remaining_quantity))
        price = float(event.get("price") or event.get("fillPrice") or event.get("fill_price"))
        fill = Fill(
            fill_id=str(event.get("fill_id") or event.get("id") or new_id("fill")),
            broker_order_id=order.broker_order_id,
            intent_id=order.intent_id,
            strategy_id=order.strategy_id,
            trade_id=order.trade_id,
            instrument=order.instrument,
            account_mode=order.account_mode,
            side=order.side,
            quantity=quantity,
            price=price,
            ts=str(event.get("event_ts") or event.get("timestamp") or event.get("ts") or utc_now_iso()),
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

    def go_flat(self, instruments: Iterable[str] = DEFAULT_INSTRUMENTS) -> List[Dict[str, Any]]:
        if self.supervisor is not None:
            self.supervisor.trigger_emergency_flatten("tradovate_go_flat_requested")
        payloads: List[Dict[str, Any]] = []
        for order_id in list(self._active_order_ids):
            self.cancel_order(order_id, reason="go_flat")
        for instrument in instruments:
            contract_id = self._contract_id_for_liquidation(instrument)
            if contract_id is None:
                continue
            payload = {"accountId": self.config.account_id_int(), "contractId": contract_id, "admin": False, "customTag50": "potions_flat"}
            payloads.append(payload)
            self._emit_order_event({"event": "liquidate_position", "endpoint": "/order/liquidateposition", "tradovate_payload": payload})
            self._send_order_payload("/order/liquidateposition", payload, "liquidate_%s" % instrument.upper())
        return payloads

    def order_intent_to_tradovate_request(self, intent: OrderIntent, order: BrokerOrder) -> Tuple[str, Dict[str, Any]]:
        base = self._base_order_payload(order)
        if intent.bracket_stop_price is not None or intent.bracket_target_price is not None:
            if order.account_mode == "live" and not self.server_oco_validated:
                raise TradovateRoutingBlocked("Live bracket order requires demo-validated Tradovate OSO/OCO")
            if self.server_oco_validated:
                bracket1, bracket2 = self._bracket_payloads(intent, order)
                if bracket2:
                    base["bracket1"] = bracket1
                    base["bracket2"] = bracket2
                    return "/order/placeoso", base
                if bracket1:
                    base["bracket1"] = bracket1
                    return "/order/placeoso", base
        return "/order/placeorder", base

    def build_oco_request(self, first: OrderIntent, first_order: BrokerOrder, other: OrderIntent) -> Tuple[str, Dict[str, Any]]:
        payload = self._base_order_payload(first_order)
        payload["other"] = self._restrained_order_payload(other, first_order.broker_order_id + "_other")
        return "/order/placeoco", payload

    def _base_order_payload(self, order: BrokerOrder) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "accountSpec": self.config.account_spec or self.config.username,
            "accountId": self.config.account_id_int(),
            "clOrdId": order.broker_order_id,
            "action": "Buy" if order.side.lower() == "buy" else "Sell",
            "symbol": self.get_active_contract(order.instrument),
            "orderQty": int(order.quantity),
            "orderType": tradovate_order_type(order.order_type),
            "timeInForce": tradovate_tif("GTC"),
            "text": "strategy=%s trade=%s intent=%s" % (order.strategy_id, order.trade_id, order.intent_id),
            "customTag50": order.strategy_id[:50],
            "isAutomated": True,
        }
        if order.order_type == "limit" and order.limit_price is not None:
            payload["price"] = order.limit_price
        if order.order_type == "stop" and order.stop_price is not None:
            payload["price"] = order.stop_price
        return payload

    def _restrained_order_payload(self, intent: OrderIntent, client_order_id: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "action": "Buy" if intent.side.lower() == "buy" else "Sell",
            "clOrdId": client_order_id,
            "orderType": tradovate_order_type(intent.order_type),
            "timeInForce": tradovate_tif(intent.tif),
            "text": intent.reason,
        }
        if intent.order_type == "limit" and intent.limit_price is not None:
            payload["price"] = intent.limit_price
        if intent.order_type == "stop" and intent.stop_price is not None:
            payload["price"] = intent.stop_price
        return payload

    def _bracket_payloads(self, intent: OrderIntent, order: BrokerOrder) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        exit_side = "sell" if order.side.lower() == "buy" else "buy"
        target = None
        stop = None
        if intent.bracket_target_price is not None:
            target_intent = OrderIntent.create(
                strategy_id=order.strategy_id,
                trade_id=order.trade_id,
                instrument=order.instrument,
                account_mode=order.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=order.quantity,
                limit_price=intent.bracket_target_price,
                reason="target",
                tif=intent.tif,
            )
            target = self._restrained_order_payload(target_intent, order.broker_order_id + "_target")
        if intent.bracket_stop_price is not None:
            stop_intent = OrderIntent.create(
                strategy_id=order.strategy_id,
                trade_id=order.trade_id,
                instrument=order.instrument,
                account_mode=order.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=order.quantity,
                stop_price=intent.bracket_stop_price,
                reason="protective_stop",
                tif=intent.tif,
            )
            stop = self._restrained_order_payload(stop_intent, order.broker_order_id + "_stop")
        return target or stop, stop if target else None

    def _modify_payload(self, order: BrokerOrder, broker_order_id: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "orderId": int(float(self._tradovate_order_ids.get(broker_order_id, "0") or 0)),
            "clOrdId": broker_order_id,
            "orderQty": int(order.quantity),
            "orderType": tradovate_order_type(order.order_type),
            "timeInForce": "GTC",
            "isAutomated": True,
        }
        if order.limit_price is not None:
            payload["price"] = order.limit_price
        if order.stop_price is not None:
            payload["price"] = order.stop_price
        return payload

    def _cancel_payload(self, broker_order_id: str, reason: str) -> Dict[str, Any]:
        payload = {
            "orderId": int(float(self._tradovate_order_ids.get(broker_order_id, "0") or 0)),
            "clOrdId": broker_order_id,
            "customTag50": reason[:50],
            "isAutomated": True,
        }
        return payload

    def _send_order_payload(self, endpoint: str, payload: Dict[str, Any], order_ref: str) -> None:
        if self.client is None:
            return
        try:
            if self.client.token is None:
                self._emit_order_event({"event": "network_order_not_sent", "reason": "no_access_token", "endpoint": endpoint, "order_ref": order_ref})
                return
            raw = self.client.request_json("POST", endpoint, payload, self.client.token.access_token)
            self._emit_order_event({"event": "network_order_response", "endpoint": endpoint, "order_ref": order_ref, "response": raw})
            if isinstance(raw, dict) and raw.get("orderId"):
                self._tradovate_order_ids[order_ref] = str(raw.get("orderId"))
        except Exception as exc:
            if self.supervisor is not None:
                self.supervisor.observe_order_ambiguity_age(self.supervisor.order_ambiguity_ms + 1, order_ref)
            self._emit_order_event({"event": "network_order_error", "endpoint": endpoint, "order_ref": order_ref, "error": str(exc)})
            raise

    def _emit_order_event(self, event: Dict[str, Any]) -> None:
        self.store.append_event("tradovate_order_events", event)

    def _require_user_sync_first(self) -> None:
        self.store.append_event(
            "tradovate_session_events",
            {"event": "user_syncrequest_required_before_orders", "account_id": self.config.account_id},
        )

    def _assert_routing_allowed(self, intent: OrderIntent) -> None:
        if self.supervisor is not None and not self.supervisor.entries_allowed(intent):
            raise TradovateRoutingBlocked("Runtime supervisor blocks new entries: %s" % self.supervisor.block_reason(intent))
        if intent.account_mode == "live" and not self.allow_live_routing:
            raise TradovateRoutingBlocked("Tradovate live order routing disabled")
        if intent.account_mode == "live" and (intent.bracket_stop_price or intent.bracket_target_price) and not self.server_oco_validated:
            raise TradovateRoutingBlocked("Tradovate live bracket/OCO requires demo validation first")

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
            if order.oco_group and order.oco_group == filled_order.oco_group and order.status in {"submitted", "partially_filled", "working"}:
                self.cancel_order(order.broker_order_id, reason="local_oco_peer_filled")

    def _position_from_tradovate(self, raw: Dict[str, Any]) -> Position:
        instrument = str(raw.get("instrument") or raw.get("symbol") or raw.get("contractId") or "")
        strategy_id = str(raw.get("strategy_id") or "tradovate")
        account_mode = "paper" if self.config.env == "demo" else "live"
        quantity = int(float(raw.get("quantity") or raw.get("netPos") or raw.get("netPosition") or 0))
        avg_price = float(raw.get("avg_price") or raw.get("netPrice") or raw.get("averagePrice") or 0.0)
        return Position(
            position_id="%s|%s|%s" % (strategy_id, instrument, account_mode),
            strategy_id=strategy_id,
            instrument=instrument,
            account_mode=account_mode,
            quantity=quantity,
            avg_price=avg_price,
            realized_pnl=float(raw.get("realized_pnl") or raw.get("realizedPnl") or 0.0),
            updated_at=utc_now_iso(),
        )

    def _contract_id_for_liquidation(self, instrument: str) -> Optional[int]:
        for pos in self.reconcile_positions():
            if pos.instrument.upper() == instrument.upper() and pos.quantity != 0:
                return self.config.contract_id_for(instrument)
        return None

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
            raise TradovateConfigurationError("TRADOVATE_CONTRACT_MAP entries must look like MNQ=MNQM6")
        key, value = item.split("=", 1)
        out[key.strip().upper()] = value.strip()
    return out


def parse_tradovate_ts(value: str) -> datetime:
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tradovate_order_type(order_type: str) -> str:
    lookup = {"market": "Market", "limit": "Limit", "stop": "Stop", "stop_limit": "StopLimit"}
    key = str(order_type).strip().lower()
    if key not in lookup:
        raise TradovateConfigurationError("Unsupported Tradovate order type: %s" % order_type)
    return lookup[key]


def tradovate_tif(tif: str) -> str:
    text = str(tif or "GTC").strip().upper()
    if text in {"DAY", "FOK", "GTC", "GTD", "IOC"}:
        return "Day" if text == "DAY" else text
    return "GTC"


def normalize_tradovate_order_status(status: str) -> str:
    text = status.strip().lower()
    if text in {"filled", "complete"}:
        return "filled"
    if text in {"cancelled", "canceled"}:
        return "cancelled"
    if text in {"partiallyfilled", "partialfilled", "partially_filled"}:
        return "partially_filled"
    if text in {"working", "pendingnew", "submitted", "accepted"}:
        return "submitted"
    if text in {"rejected"}:
        return "rejected"
    return text or "submitted"


def tradovate_chart_bar_to_bar(raw_bar: Dict[str, Any], instrument: str, timeframe: str) -> Bar:
    volume = float(raw_bar.get("volume") or 0.0)
    if not volume:
        volume = float(raw_bar.get("upVolume") or 0.0) + float(raw_bar.get("downVolume") or 0.0)
    return Bar(
        instrument=instrument,
        timeframe=timeframe,
        ts=str(raw_bar.get("timestamp") or raw_bar.get("ts")),
        open=float(raw_bar["open"]),
        high=float(raw_bar["high"]),
        low=float(raw_bar["low"]),
        close=float(raw_bar["close"]),
        volume=volume,
        complete=True,
        source="tradovate_chart",
    )


def as_ref_row(ref: TradovateContractRef) -> Dict[str, Any]:
    return {
        "instrument": ref.instrument,
        "symbol": ref.symbol,
        "contract_id": ref.contract_id,
        "resolved_at": ref.resolved_at,
        "metadata": ref.metadata,
    }


def load_jsonl_events(path: Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
