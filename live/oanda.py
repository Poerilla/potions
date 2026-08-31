from __future__ import annotations

import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .broker import BaseBroker
from .live_feed import FeedHealth, LiveFeedAdapter, PersistedLiveFeedAdapter
from .models import Bar, BrokerOrder, Fill, OrderIntent, Position, as_row, new_id, utc_now_iso
from .store import FlatFileStore
from .supervisor import RuntimeSupervisor


DEFAULT_INSTRUMENTS = ("EURUSD", "XAUUSD", "NAS100", "SPX500", "US30")
DEFAULT_INSTRUMENT_MAP = {
    "EURUSD": "EUR_USD",
    "XAUUSD": "XAU_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
    "AUDJPY": "AUD_JPY",
    "XAGUSD": "XAG_USD",
    "NAS100": "NAS100_USD",
    "SPX500": "SPX500_USD",  # US SPX 500 CFD — ES proxy
    "US30": "US30_USD",  # US Wall St 30 CFD — YM proxy
}
# OANDA instrument displayPrecision (reject PRICE_PRECISION_EXCEEDED if exceeded).
DEFAULT_DISPLAY_PRECISION = {
    "EURUSD": 5,
    "GBPUSD": 5,
    "USDJPY": 3,
    "AUDJPY": 3,
    "XAUUSD": 3,
    "XAGUSD": 3,
    "NAS100": 1,
    "SPX500": 1,
    "US30": 1,
}
DEFAULT_PRIMARY_ACCOUNT = "101-002-39860312-001"
DEFAULT_SECONDARY_ACCOUNT = "101-002-39860312-002"
# Trade-linked protective orders must never be swept as entry orphans.
_OANDA_PROTECTIVE_ORDER_TYPES = frozenset(
    {
        "STOP_LOSS",
        "TAKE_PROFIT",
        "TRAILING_STOP_LOSS",
        "GUARANTEED_STOP_LOSS",
    }
)
_OANDA_ENTRY_ORPHAN_ORDER_TYPES = frozenset(
    {
        "LIMIT",
        "STOP",
        "MARKET_IF_TOUCHED",
    }
)
_REMOTE_AUTHORITY_SWEEP_SECONDS = 60.0
_CANCEL_RESUBMIT_MODIFY_REASONS = frozenset(
    {
        "refresh_entry",
        "modify",
        "",
    }
)


class OandaAdapterError(RuntimeError):
    pass


class OandaConfigurationError(OandaAdapterError):
    pass


class OandaRoutingBlocked(OandaAdapterError):
    pass


def _ensure_v20_deps() -> None:
    """v20 requires ``ujson`` + ``requests``. Fall back to stdlib ``json`` if ujson is missing."""
    try:
        import ujson  # noqa: F401
    except ImportError:
        import json as _json

        sys.modules["ujson"] = _json
    try:
        import requests  # noqa: F401
    except ImportError as exc:
        raise OandaConfigurationError(
            "OANDA network mode requires the 'requests' package (v20 dependency). "
            "Install with: python3 -m pip install --user requests ujson"
        ) from exc


def _ensure_v20_on_path() -> Path:
    """Prepend vendored v20-python/src so `import v20` works without a global install."""
    _ensure_v20_deps()
    root = Path(__file__).resolve().parents[1] / "v20-python" / "src"
    path = str(root)
    if path not in sys.path:
        sys.path.insert(0, path)
    return root


@dataclass(frozen=True)
class OandaConfig:
    env: str = "practice"
    api_url: str = "https://api-fxpractice.oanda.com"
    stream_url: str = "https://stream-fxpractice.oanda.com"
    token: str = ""
    account_id: str = DEFAULT_PRIMARY_ACCOUNT
    instrument_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_INSTRUMENT_MAP))
    application: str = "potions-oanda-adapter"

    @classmethod
    def from_env(cls, environ: Optional[Dict[str, str]] = None) -> "OandaConfig":
        env = environ if environ is not None else os.environ
        oanda_env = (env.get("OANDA_ENV") or "practice").strip().lower() or "practice"
        if oanda_env in {"practice", "fxpractice", "demo"}:
            oanda_env = "practice"
            default_api = "https://api-fxpractice.oanda.com"
            default_stream = "https://stream-fxpractice.oanda.com"
        elif oanda_env in {"live", "fxtrade", "trade"}:
            oanda_env = "live"
            default_api = "https://api-fxtrade.oanda.com"
            default_stream = "https://stream-fxtrade.oanda.com"
        else:
            raise OandaConfigurationError("OANDA_ENV must be practice or live, got %r" % oanda_env)
        instrument_map = dict(DEFAULT_INSTRUMENT_MAP)
        instrument_map.update(parse_instrument_map(env.get("OANDA_INSTRUMENT_MAP", "")))
        return cls(
            env=oanda_env,
            api_url=(env.get("OANDA_API_URL") or default_api).rstrip("/"),
            stream_url=(env.get("OANDA_STREAM_URL") or default_stream).rstrip("/"),
            token=env.get("OANDA_TOKEN", ""),
            account_id=(env.get("OANDA_ACCOUNT_ID") or DEFAULT_PRIMARY_ACCOUNT).strip(),
            instrument_map=instrument_map,
            application=env.get("OANDA_APPLICATION", "potions-oanda-adapter"),
        )

    @classmethod
    def from_json_file(cls, path: Path, environ: Optional[Dict[str, str]] = None) -> "OandaConfig":
        base = cls.from_env(environ)
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        instrument_map = dict(base.instrument_map)
        instrument_map.update({str(k).upper(): str(v) for k, v in (raw.get("instrument_map") or {}).items()})
        return cls(
            env=str(raw.get("env", base.env)).strip().lower() or base.env,
            api_url=str(raw.get("api_url", base.api_url)).rstrip("/"),
            stream_url=str(raw.get("stream_url", base.stream_url)).rstrip("/"),
            token=str(raw.get("token", base.token)),
            account_id=str(raw.get("account_id", base.account_id)),
            instrument_map=instrument_map,
            application=str(raw.get("application", base.application)),
        )

    def validate_for_network(self) -> None:
        missing = []
        for field_name in ("api_url", "token", "account_id"):
            if not getattr(self, field_name):
                missing.append(field_name)
        if missing:
            raise OandaConfigurationError("Missing OANDA config fields: %s" % ", ".join(missing))

    def hostname(self) -> str:
        url = self.api_url
        if "://" in url:
            url = url.split("://", 1)[1]
        return url.split("/", 1)[0]

    def stream_hostname(self) -> str:
        url = self.stream_url
        if "://" in url:
            url = url.split("://", 1)[1]
        return url.split("/", 1)[0].rstrip("/")

    def symbol_for(self, instrument: str) -> str:
        key = instrument.upper().replace("/", "").replace("_", "")
        # Accept both EURUSD and EUR_USD style keys in the map.
        if instrument.upper() in self.instrument_map:
            return self.instrument_map[instrument.upper()]
        compact = {k.replace("_", ""): v for k, v in self.instrument_map.items()}
        if key in compact:
            return compact[key]
        if "_" in instrument:
            return instrument.upper()
        # EURUSD -> EUR_USD heuristic for unknown pairs (last 3 = quote).
        raw = instrument.upper()
        if len(raw) == 6:
            return "%s_%s" % (raw[:3], raw[3:])
        return raw

    def internal_for(self, oanda_instrument: str) -> str:
        target = oanda_instrument.upper()
        for internal, mapped in self.instrument_map.items():
            if mapped.upper() == target:
                return internal
        return target.replace("_", "")


@dataclass(frozen=True)
class OandaInstrumentRef:
    instrument: str
    oanda_instrument: str
    resolved_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class OandaApiClient:
    """Thin wrapper around vendored ``v20.Context``; injectable for offline tests."""

    def __init__(
        self,
        config: OandaConfig,
        store: Optional[FlatFileStore] = None,
        context: Any = None,
        context_factory: Optional[Callable[[OandaConfig], Any]] = None,
    ):
        self.config = config
        self.store = store
        self._context = context
        self._context_factory = context_factory or default_v20_context
        self.last_transaction_id: str = ""
        self.account_snapshot: Dict[str, Any] = {}

    @property
    def ctx(self) -> Any:
        if self._context is None:
            self._context = self._context_factory(self.config)
        return self._context

    def record_session_event(self, event: Dict[str, Any]) -> None:
        if self.store is not None:
            self.store.append_event("oanda_session_events", event)

    def list_accounts(self) -> Any:
        response = self.ctx.account.list()
        self.record_session_event({"event": "account_list", "status": getattr(response, "status", "")})
        return response

    def account_details(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        response = self.ctx.account.get(account_id)
        body = response_body(response)
        account = body.get("account") or {}
        if hasattr(account, "dict"):
            account = account.dict()
        self.account_snapshot = dict(account) if isinstance(account, dict) else {"raw": account}
        self.last_transaction_id = str(
            body.get("lastTransactionID")
            or self.account_snapshot.get("lastTransactionID")
            or self.last_transaction_id
            or ""
        )
        self.record_session_event(
            {
                "event": "account_details",
                "account_id": account_id,
                "last_transaction_id": self.last_transaction_id,
            }
        )
        return body

    def account_changes(self, since_transaction_id: Optional[str] = None, account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        since = since_transaction_id or self.last_transaction_id
        if not since:
            raise OandaConfigurationError("account_changes requires lastTransactionID; call account_details first")
        response = self.ctx.account.changes(account_id, sinceTransactionID=since)
        body = response_body(response)
        self.last_transaction_id = str(body.get("lastTransactionID") or self.last_transaction_id)
        self.record_session_event(
            {"event": "account_changes", "account_id": account_id, "last_transaction_id": self.last_transaction_id}
        )
        return body

    def account_instruments(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        response = self.ctx.account.instruments(account_id)
        body = response_body(response)
        self.record_session_event({"event": "account_instruments", "account_id": account_id})
        return body

    def pricing_get(self, instruments: Iterable[str], account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        names = ",".join(instruments)
        response = self.ctx.pricing.get(account_id, instruments=names)
        body = response_body(response)
        self.record_session_event({"event": "pricing_get", "instruments": names})
        return body

    def pricing_stream(self, instruments: Iterable[str], account_id: Optional[str] = None, snapshot: bool = True) -> Any:
        """Open OANDA pricing stream (uses stream hostname). Iterate ``response.parts()``."""
        account_id = account_id or self.config.account_id
        names = ",".join(instruments)
        stream_ctx = default_v20_stream_context(self.config)
        response = stream_ctx.pricing.stream(account_id, instruments=names, snapshot=snapshot)
        self.record_session_event({"event": "pricing_stream_open", "instruments": names, "status": getattr(response, "status", "")})
        return response

    def create_order(self, order_body: Dict[str, Any], account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        response = self.ctx.order.create(account_id, order=order_body)
        body = response_body(response)
        self.record_session_event({"event": "order_create", "account_id": account_id})
        return body

    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        response = self.ctx.order.cancel(account_id, order_id)
        body = response_body(response)
        self.record_session_event({"event": "order_cancel", "order_id": order_id})
        return body

    def replace_order(self, order_id: str, order_body: Dict[str, Any], account_id: Optional[str] = None) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        response = self.ctx.order.replace(account_id, order_id, order=order_body)
        body = response_body(response)
        self.record_session_event({"event": "order_replace", "order_id": order_id})
        return body

    def close_position(self, instrument: str, account_id: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        account_id = account_id or self.config.account_id
        response = self.ctx.position.close(account_id, instrument, **kwargs)
        body = response_body(response)
        self.record_session_event({"event": "position_close", "instrument": instrument})
        return body

    def candles(self, instrument: str, **kwargs: Any) -> Dict[str, Any]:
        response = self.ctx.instrument.candles(instrument, **kwargs)
        return response_body(response)


def default_v20_context(config: OandaConfig) -> Any:
    _ensure_v20_on_path()
    import v20  # type: ignore

    config.validate_for_network()
    return v20.Context(
        hostname=config.hostname(),
        token=config.token,
        application=config.application,
        port=443,
        ssl=True,
        datetime_format="RFC3339",
    )


def default_v20_stream_context(config: OandaConfig) -> Any:
    _ensure_v20_on_path()
    import v20  # type: ignore

    config.validate_for_network()
    return v20.Context(
        hostname=config.stream_hostname(),
        token=config.token,
        application=config.application,
        port=443,
        ssl=True,
        datetime_format="RFC3339",
    )


class OneMinuteBarBuilder:
    def __init__(self, instrument: str, source: str = "oanda"):
        self.instrument = instrument
        self.source = source
        self._current_key: Optional[datetime] = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0.0

    def on_trade(self, price: float, quantity: float, ts: str) -> List[Bar]:
        event_dt = parse_oanda_ts(ts)
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


class QuoteOneMinuteBarBuilder:
    """Build 1m mid OHLC for signals with parallel bid/ask OHLC for paper fills."""

    def __init__(self, instrument: str, source: str = "oanda_quote"):
        self.instrument = instrument
        self.source = source
        self._current_key: Optional[datetime] = None
        self._mid = _SideBucket()
        self._bid = _SideBucket()
        self._ask = _SideBucket()
        self._volume = 0.0

    def on_quote(self, *, bid: float, ask: float, mid: Optional[float] = None, quantity: float = 0.0, ts: str) -> List[Bar]:
        mid_px = float(mid) if mid is not None else (float(bid) + float(ask)) / 2.0
        event_dt = parse_oanda_ts(ts)
        minute_key = event_dt.replace(second=0, microsecond=0)
        emitted: List[Bar] = []
        if self._current_key is None:
            self._start(minute_key, bid=float(bid), ask=float(ask), mid=mid_px, quantity=quantity)
            return emitted
        if minute_key != self._current_key:
            emitted.append(self._bar())
            self._start(minute_key, bid=float(bid), ask=float(ask), mid=mid_px, quantity=quantity)
            return emitted
        self._mid.update(mid_px)
        self._bid.update(float(bid))
        self._ask.update(float(ask))
        self._volume += quantity
        return emitted

    def flush(self) -> List[Bar]:
        if self._current_key is None:
            return []
        bar = self._bar()
        self._current_key = None
        return [bar]

    def _start(self, minute_key: datetime, *, bid: float, ask: float, mid: float, quantity: float) -> None:
        self._current_key = minute_key
        self._mid = _SideBucket.start(mid)
        self._bid = _SideBucket.start(bid)
        self._ask = _SideBucket.start(ask)
        self._volume = quantity

    def _bar(self) -> Bar:
        assert self._current_key is not None
        return Bar(
            instrument=self.instrument,
            timeframe="1m",
            ts=isoformat_utc(self._current_key),
            open=self._mid.open,
            high=self._mid.high,
            low=self._mid.low,
            close=self._mid.close,
            volume=self._volume,
            complete=True,
            source=self.source,
            bid_open=self._bid.open,
            bid_high=self._bid.high,
            bid_low=self._bid.low,
            bid_close=self._bid.close,
            ask_open=self._ask.open,
            ask_high=self._ask.high,
            ask_low=self._ask.low,
            ask_close=self._ask.close,
        )


class _SideBucket:
    __slots__ = ("open", "high", "low", "close")

    def __init__(self) -> None:
        self.open = 0.0
        self.high = 0.0
        self.low = 0.0
        self.close = 0.0

    @classmethod
    def start(cls, price: float) -> "_SideBucket":
        bucket = cls()
        bucket.open = price
        bucket.high = price
        bucket.low = price
        bucket.close = price
        return bucket

    def update(self, price: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price


class FiveMinuteBarAggregator:
    def __init__(self, instrument: str, source: str = "oanda_1m_aggregate"):
        self.instrument = instrument
        self.source = source
        self._bucket_key: Optional[datetime] = None
        self._bars: List[Bar] = []

    def on_bar(self, bar: Bar) -> List[Bar]:
        if bar.timeframe != "1m":
            return []
        dt = parse_oanda_ts(bar.ts)
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


class FifteenMinuteBarAggregator:
    """Aggregate 1m bars into 15m bars with left label / left closed (matches Monday OR research).

    Bucket ``:00–:14`` emits a completed 15m bar whose ``ts`` is the bucket start.
    """

    def __init__(self, instrument: str, source: str = "oanda_1m_aggregate"):
        self.instrument = instrument
        self.source = source
        self._bucket_key: Optional[datetime] = None
        self._bars: List[Bar] = []

    def on_bar(self, bar: Bar) -> List[Bar]:
        if bar.timeframe != "1m":
            return []
        dt = parse_oanda_ts(bar.ts)
        bucket = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
        emitted: List[Bar] = []
        if self._bucket_key is not None and bucket != self._bucket_key:
            emitted.extend(self._flush_bucket())
            self._bars = []
        self._bucket_key = bucket
        self._bars.append(bar)
        # Complete when we have the last minute of the bucket (:14, :29, :44, :59).
        if dt.minute % 15 == 14:
            emitted.extend(self._flush_bucket())
            self._bars = []
            self._bucket_key = None
        return emitted

    def flush(self) -> List[Bar]:
        return self._flush_bucket()

    def _flush_bucket(self) -> List[Bar]:
        if not self._bars or self._bucket_key is None:
            return []
        bars = list(self._bars)
        return [
            Bar(
                instrument=self.instrument,
                timeframe="15m",
                ts=isoformat_utc(self._bucket_key),
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
                volume=sum(bar.volume for bar in bars),
                complete=True,
                source=self.source,
                bid_open=bars[0].bid_open,
                bid_high=max((b.bid_high for b in bars if b.bid_high is not None), default=None),
                bid_low=min((b.bid_low for b in bars if b.bid_low is not None), default=None),
                bid_close=bars[-1].bid_close,
                ask_open=bars[0].ask_open,
                ask_high=max((b.ask_high for b in bars if b.ask_high is not None), default=None),
                ask_low=min((b.ask_low for b in bars if b.ask_low is not None), default=None),
                ask_close=bars[-1].ask_close,
            )
        ]


class HourlyBarAggregator:
    """Aggregate 1m bars into 1h bars with left label / left closed (matches ST+PMC research).

    Bucket ``HH:00–HH:59`` emits a completed 1h bar whose ``ts`` is the hour start.
    """

    def __init__(self, instrument: str, source: str = "oanda_1m_aggregate"):
        self.instrument = instrument
        self.source = source
        self._bucket_key: Optional[datetime] = None
        self._bars: List[Bar] = []

    def on_bar(self, bar: Bar) -> List[Bar]:
        if bar.timeframe != "1m":
            return []
        dt = parse_oanda_ts(bar.ts)
        bucket = dt.replace(minute=0, second=0, microsecond=0)
        emitted: List[Bar] = []
        if self._bucket_key is not None and bucket != self._bucket_key:
            emitted.extend(self._flush_bucket())
            self._bars = []
        self._bucket_key = bucket
        self._bars.append(bar)
        if dt.minute == 59:
            emitted.extend(self._flush_bucket())
            self._bars = []
            self._bucket_key = None
        return emitted

    def flush(self) -> List[Bar]:
        return self._flush_bucket()

    def _flush_bucket(self) -> List[Bar]:
        if not self._bars or self._bucket_key is None:
            return []
        bars = list(self._bars)
        return [
            Bar(
                instrument=self.instrument,
                timeframe="1h",
                ts=isoformat_utc(self._bucket_key),
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
                volume=sum(bar.volume for bar in bars),
                complete=True,
                source=self.source,
                bid_open=bars[0].bid_open,
                bid_high=max((b.bid_high for b in bars if b.bid_high is not None), default=None),
                bid_low=min((b.bid_low for b in bars if b.bid_low is not None), default=None),
                bid_close=bars[-1].bid_close,
                ask_open=bars[0].ask_open,
                ask_high=max((b.ask_high for b in bars if b.ask_high is not None), default=None),
                ask_low=min((b.ask_low for b in bars if b.ask_low is not None), default=None),
                ask_close=bars[-1].ask_close,
            )
        ]


class OandaMarketDataFeedAdapter(LiveFeedAdapter):
    BLOCKING_STATUSES = {"access_denied", "delayed", "downgraded", "stale", "unresolved_instrument", "permission_denied"}

    def __init__(
        self,
        store: FlatFileStore,
        config: Optional[OandaConfig] = None,
        on_bar: Optional[Callable[[Bar], None]] = None,
        stale_after_seconds: float = 30.0,
        clock: Callable[[], datetime] = datetime.utcnow,
        supervisor: Optional[RuntimeSupervisor] = None,
    ):
        self.store = store
        self.store.ensure()
        self.config = config or OandaConfig.from_env()
        self.supervisor = supervisor
        self._persisted = PersistedLiveFeedAdapter(
            store,
            on_bar=on_bar,
            allowed_timeframes=("1m", "5m", "15m", "1h", "D"),
            stale_after_seconds=stale_after_seconds,
            clock=clock,
        )
        self.instrument_refs: Dict[str, OandaInstrumentRef] = {}
        self._minute_builders: Dict[str, OneMinuteBarBuilder] = {}
        self._five_minute_aggregators: Dict[str, FiveMinuteBarAggregator] = {}
        self._blocking_reason = ""
        self._market_status = "init"
        self._write_market_data_status()

    def resolve_instrument(
        self,
        instrument: str,
        oanda_instrument: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OandaInstrumentRef:
        ref = OandaInstrumentRef(
            instrument=instrument.upper(),
            oanda_instrument=oanda_instrument or self.config.symbol_for(instrument),
            resolved_at=utc_now_iso(),
            metadata=metadata or {},
        )
        self.instrument_refs[ref.instrument] = ref
        self._blocking_reason = ""
        self.store.append_event("oanda_session_events", {"event": "instrument_resolved", **as_ref_row(ref)})
        self._write_market_data_status()
        return ref

    def on_raw_event(self, event: Dict[str, Any]) -> List[Bar]:
        event = dict(event)
        self._persist_raw_market_event(event)
        event_type = str(event.get("type") or event.get("event") or "")
        if event_type in {"instrument_resolution", "symbol_resolution"}:
            self.resolve_instrument(
                str(event["instrument"]),
                oanda_instrument=str(event.get("oanda_instrument") or event.get("symbol") or ""),
                metadata=dict(event.get("metadata") or {}),
            )
            return []
        if event_type == "market_data_status":
            self._handle_market_data_status(event)
            return []
        if event_type in {"trade", "price", "pricing"}:
            return self._handle_price_event(event)
        if event_type == "bar":
            return self._handle_bar_event(event)
        if event_type == "candle":
            return self._handle_candle_event(event)
        # Pricing stream PRICE object
        if str(event.get("type") or "").upper() == "PRICE" or event.get("bids") or event.get("asks"):
            return self._handle_price_event(dict(event, type="price"))
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
            self.supervisor.freeze_entries("oanda_feed_stale", {"stale_seconds": base.stale_seconds})
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
            self.store.append_event("market_data_quality", {"event": "oanda_blocking_status", **event})
            if self.supervisor is not None:
                self.supervisor.freeze_entries("oanda_market_data_%s" % self._blocking_reason, event)
        elif status in {"ok", "realtime", "subscribed", "tradeable"}:
            self._blocking_reason = ""
        self._write_market_data_status()

    def _handle_price_event(self, event: Dict[str, Any]) -> List[Bar]:
        instrument = self._resolve_internal_instrument(event)
        if not instrument:
            self._blocking_reason = "unresolved_instrument"
            self._write_market_data_status()
            self.store.append_event("market_data_quality", {"event": "oanda_price_without_instrument", **event})
            return []
        if instrument not in self.instrument_refs:
            self.resolve_instrument(instrument, oanda_instrument=str(event.get("oanda_instrument") or event.get("instrument") or ""))
        price = mid_price_from_event(event)
        if price is None:
            return []
        qty = float(event.get("quantity") or event.get("volume") or event.get("liquidity") or 0.0)
        event_ts = str(event.get("event_ts") or event.get("ts") or event.get("time") or event.get("timestamp") or utc_now_iso())
        builder = self._minute_builders.setdefault(instrument, OneMinuteBarBuilder(instrument))
        emitted: List[Bar] = []
        for bar in builder.on_trade(price, qty, event_ts):
            emitted.extend(self._persist_1m_and_derived_5m(bar))
        return emitted

    def _handle_bar_event(self, event: Dict[str, Any]) -> List[Bar]:
        bar = Bar.from_row(dict(event, source=event.get("source") or "oanda"))
        emitted = self._persisted.on_raw_event(dict(as_row(bar), type="bar"))
        self._append_bar_audit(bar, "vendor_bar", "")
        if bar.timeframe == "1m" and emitted:
            emitted.extend(self._derive_5m(bar))
        return emitted

    def _handle_candle_event(self, event: Dict[str, Any]) -> List[Bar]:
        instrument = self._resolve_internal_instrument(event)
        if not instrument:
            return []
        mid = event.get("mid") or event
        bar = Bar(
            instrument=instrument,
            timeframe=str(event.get("timeframe") or event.get("granularity") or "1m").replace("M", "m").replace("H", "h"),
            ts=str(event.get("time") or event.get("ts") or event.get("event_ts") or utc_now_iso()),
            open=float(mid.get("o") if isinstance(mid, dict) else event.get("open")),
            high=float(mid.get("h") if isinstance(mid, dict) else event.get("high")),
            low=float(mid.get("l") if isinstance(mid, dict) else event.get("low")),
            close=float(mid.get("c") if isinstance(mid, dict) else event.get("close")),
            volume=float(event.get("volume") or 0.0),
            complete=bool(event.get("complete", True)),
            source="oanda",
        )
        if bar.timeframe.lower() in {"m1", "1m", "m"}:
            bar = replace(bar, timeframe="1m")
        return self._handle_bar_event(as_row(bar))

    def _resolve_internal_instrument(self, event: Dict[str, Any]) -> str:
        if event.get("instrument") and "_" not in str(event.get("instrument")):
            return str(event["instrument"]).upper()
        raw = str(event.get("instrument") or event.get("oanda_instrument") or "")
        if not raw:
            return ""
        if "_" in raw:
            return self.config.internal_for(raw)
        return raw.upper()

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
        day = str(event.get("event_ts") or event.get("ts") or event.get("time") or event.get("timestamp") or utc_now_iso())[:10]
        self.store.append_event("raw_market_data/oanda/%s" % day, event)

    def _write_market_data_status(self) -> None:
        health = self._persisted.health()
        self.store.write_json(
            "market_data_status.json",
            {
                "provider": "oanda",
                "status": "blocked" if self._blocking_reason else self._market_status,
                "blocking_reason": self._blocking_reason,
                "updated_at": utc_now_iso(),
                "instrument_refs": {instrument: as_ref_row(ref) for instrument, ref in self.instrument_refs.items()},
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


class OandaBroker(BaseBroker):
    def __init__(
        self,
        store: FlatFileStore,
        config: Optional[OandaConfig] = None,
        client: Optional[OandaApiClient] = None,
        allow_live_routing: bool = False,
        supervisor: Optional[RuntimeSupervisor] = None,
        authority_strategy_ids: Optional[Iterable[str]] = None,
        position_scope_instruments: Optional[Iterable[str]] = None,
    ):
        self.store = store
        self.store.ensure()
        self.config = config or OandaConfig.from_env()
        self.client = client
        self.allow_live_routing = bool(allow_live_routing)
        self.supervisor = supervisor
        if self.config.env != "practice" and not self.allow_live_routing:
            raise OandaConfigurationError("OANDA live routing is disabled unless allow_live_routing=True")
        # Shared practice account is account-wide; demos scope to their focus instrument so
        # reconcile_from_account_details does not bleed sibling NAS100/US30/etc. into local CSV.
        scope = {
            str(inst).strip().upper()
            for inst in (position_scope_instruments or [])
            if str(inst).strip()
        }
        self._position_scope_instruments: Optional[Set[str]] = scope or None
        self._orders_cache: Dict[str, BrokerOrder] = {order.broker_order_id: order for order in self.store.load_orders()}
        self._intents_cache: Dict[str, OrderIntent] = {intent.intent_id: intent for intent in self.store.load_order_intents()}
        loaded_positions = list(self.store.load_positions())
        if self._position_scope_instruments is not None:
            loaded_positions = [
                pos for pos in loaded_positions if str(pos.instrument or "").upper() in self._position_scope_instruments
            ]
        self._positions_cache: Dict[str, Position] = {pos.position_id: pos for pos in loaded_positions}
        self._active_order_ids = {
            order.broker_order_id: True
            for order in self._orders_cache.values()
            if order.status in {"submitted", "partially_filled", "working", "pendingnew"}
        }
        self._oanda_order_ids: Dict[str, str] = {}
        self._authority_strategy_ids: Set[str] = {
            str(sid).strip() for sid in (authority_strategy_ids or []) if str(sid).strip()
        }
        self.last_transaction_id: str = ""
        self._pending_fills: List[Fill] = []
        self._display_precision: Dict[str, int] = dict(DEFAULT_DISPLAY_PRECISION)
        self._last_authority_sweep_at: float = 0.0
        self._pending_remote_snapshot: List[Dict[str, Any]] = []
        self._pending_gate_off_sweep_strategy_ids: Set[str] = set()
        self._account_trades_cache: List[Dict[str, Any]] = []
        self._account_trades_cache_at: float = 0.0
        self._cross_book_cache_ttl_s: float = 30.0

    def display_precision_for(self, instrument: str) -> int:
        key = str(instrument or "").upper()
        if key in self._display_precision:
            return int(self._display_precision[key])
        # Fall back via OANDA name → internal.
        internal = self.config.internal_for(key) if "_" in key else key
        return int(self._display_precision.get(internal, 5))

    def get_active_contract(self, instrument: str) -> str:
        return self.config.symbol_for(instrument)

    def get_bars(self, instrument: str, timeframe: str, limit: int = 500) -> List[Bar]:
        bars = self.store.read_bars(instrument, timeframe)
        return bars[-limit:]

    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        self._assert_routing_allowed(intent)
        self._assert_cross_book_entry_allowed(intent)
        intent = replace(intent, status="submitted", updated_at=utc_now_iso())
        order = BrokerOrder.from_intent(intent)
        self._intents_cache[intent.intent_id] = intent
        self._orders_cache[order.broker_order_id] = order
        self._active_order_ids[order.broker_order_id] = True
        self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="submitted"))
        self.store.upsert_row("orders", "broker_order_id", as_row(order))
        payload = self.order_intent_to_oanda_order(intent, order)
        self._emit_order_event({"event": "submit", "oanda_order": payload, **as_row(order)})
        self._send_create_order(payload, order.broker_order_id)
        return order

    def register_authority_strategy(self, strategy_id: str) -> None:
        sid = str(strategy_id or "").strip()
        if sid:
            self._authority_strategy_ids.add(sid)

    def register_authority_strategies(self, strategy_ids: Iterable[str]) -> None:
        for strategy_id in strategy_ids:
            self.register_authority_strategy(strategy_id)

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
            raise ValueError("Cannot modify OANDA order %s in status %s" % (broker_order_id, order.status))
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
        intent = self._intents_cache.get(updated.intent_id)
        if intent is None:
            intent = OrderIntent.create(
                strategy_id=updated.strategy_id,
                trade_id=updated.trade_id,
                instrument=updated.instrument,
                account_mode=updated.account_mode,
                side=updated.side,
                order_type=updated.order_type,
                quantity=updated.quantity,
                limit_price=updated.limit_price,
                stop_price=updated.stop_price,
                reason=reason or "modify",
                bracket_stop_price=bracket_stop_price,
                bracket_target_price=bracket_target_price,
                requires_verification=False,
                bracket_role=updated.bracket_role,
                live_after_ts=updated.live_after_ts,
            )
        else:
            intent = replace(
                intent,
                limit_price=updated.limit_price,
                stop_price=updated.stop_price,
                bracket_stop_price=bracket_stop_price if bracket_stop_price is not None else intent.bracket_stop_price,
                bracket_target_price=bracket_target_price if bracket_target_price is not None else intent.bracket_target_price,
                live_after_ts=updated.live_after_ts if updated.live_after_ts is not None else intent.live_after_ts,
            )
            self._intents_cache[intent.intent_id] = intent
        payload = self.order_intent_to_oanda_order(intent, updated)
        remote_id = self._resolve_remote_order_id(broker_order_id)
        self._emit_order_event(
            {"event": "modify", "oanda_order_id": remote_id, "oanda_order": payload, "reason": reason, **as_row(updated)}
        )
        if self.client is None:
            return updated
        # Prefer cancel + resubmit for resting entry refreshes so OANDA never keeps a
        # ghost id after replace, and every cancel is audited in oanda_order_events.
        prefer_cancel_resubmit = self._should_cancel_resubmit_modify(order, reason)
        if prefer_cancel_resubmit:
            self._cancel_resubmit_remote_order(
                broker_order_id=broker_order_id,
                remote_id=remote_id,
                payload=payload,
                reason=reason or "refresh_entry",
            )
            return updated
        if remote_id:
            try:
                raw = self.client.replace_order(remote_id, payload)
                raw = _jsonable(raw) if not isinstance(raw, dict) else {k: _jsonable(v) for k, v in raw.items()}
                self._emit_order_event({"event": "network_order_response", "action": "replace", "response": raw})
                new_remote = self._extract_remote_order_id_from_replace(raw)
                if new_remote:
                    self._oanda_order_ids[broker_order_id] = str(new_remote)
                if remote_id and remote_id in self._oanda_order_ids.values() and self._oanda_order_ids.get(broker_order_id) != remote_id:
                    # Old remote id must not remain mapped to any local order.
                    stale = [lid for lid, rid in self._oanda_order_ids.items() if rid == remote_id and lid != broker_order_id]
                    for lid in stale:
                        self._oanda_order_ids.pop(lid, None)
                if self._oanda_order_ids.get(broker_order_id) == remote_id and new_remote and str(new_remote) != remote_id:
                    self._oanda_order_ids[broker_order_id] = str(new_remote)
                if remote_id and self._oanda_order_ids.get(broker_order_id) == remote_id and not new_remote:
                    # Replace without a new id is unsafe — force cancel+resubmit next.
                    self._emit_order_event(
                        {
                            "event": "replace_id_unchanged",
                            "broker_order_id": broker_order_id,
                            "oanda_order_id": remote_id,
                            "reason": reason,
                        }
                    )
            except Exception as exc:
                self._emit_order_event({"event": "network_order_error", "action": "replace", "error": str(exc)})
                raise
        return updated

    def cancel_order(self, broker_order_id: str, reason: str = "") -> BrokerOrder:
        """Cancel remote first; only then commit local cancelled + schedule reconcile.

        Local must not leave ``_active_order_ids`` until OANDA acks (or we prove
        there is no remote rest). Otherwise gate-off creates orphan LIMITs that
        keep filling on the shared practice account.
        """
        order = self._get_order(broker_order_id)
        if order.status in {"filled", "cancelled"}:
            return order

        remote_id = self._resolve_remote_order_id(broker_order_id)
        self._emit_order_event(
            {
                "event": "cancel_requested",
                "broker_order_id": broker_order_id,
                "oanda_order_id": remote_id or "",
                "reason": reason,
                "strategy_id": order.strategy_id,
                "instrument": order.instrument,
                "order_type": order.order_type,
                "bracket_role": order.bracket_role,
            }
        )

        if self.client is not None:
            if not remote_id:
                remote_id = self._force_resolve_remote_order_id(broker_order_id)
            if remote_id:
                try:
                    raw = self.client.cancel_order(remote_id)
                    self._emit_order_event(
                        {
                            "event": "network_order_response",
                            "action": "cancel",
                            "phase": "remote_ack_before_local",
                            "oanda_order_id": remote_id,
                            "broker_order_id": broker_order_id,
                            "reason": reason,
                            "response": _jsonable(raw),
                        }
                    )
                    self._oanda_order_ids.pop(broker_order_id, None)
                except Exception as exc:
                    self._emit_order_event(
                        {
                            "event": "network_order_error",
                            "action": "cancel",
                            "phase": "remote_before_local",
                            "oanda_order_id": remote_id,
                            "broker_order_id": broker_order_id,
                            "reason": reason,
                            "error": str(exc),
                            "local_still_open": True,
                        }
                    )
                    raise
            else:
                # Live client but no remote row after force resolve → never placed
                # (or already gone). Safe to commit local-only cancel.
                self._emit_order_event(
                    {
                        "event": "cancel_local_only_no_remote",
                        "broker_order_id": broker_order_id,
                        "reason": reason,
                        "strategy_id": order.strategy_id,
                    }
                )

        updated = replace(order, status="cancelled", updated_at=utc_now_iso())
        self._orders_cache[updated.broker_order_id] = updated
        self._active_order_ids.pop(updated.broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        self._emit_order_event(
            {
                "event": "cancel",
                "phase": "local_committed_after_remote",
                "oanda_order_id": remote_id or "",
                "reason": reason,
                **as_row(updated),
            }
        )

        reason_l = str(reason or "").lower()
        if any(token in reason_l for token in ("regime_off", "thesis_off", "year_end", "refresh_entry", "go_flat", "in_position", "v2b_eod")):
            # Defer orphan sweep to the next authority timer / poll so a gate-off batch
            # of N local cancels does not issue N account_details fetches.
            self._pending_gate_off_sweep_strategy_ids.add(order.strategy_id)
        return updated

    def _force_resolve_remote_order_id(self, broker_order_id: str) -> str:
        """Refresh account pending orders once, then resolve clientExtensions.id map."""
        rid = self._resolve_remote_order_id(broker_order_id)
        if rid or self.client is None:
            return rid
        try:
            body = self.client.account_details()
            account = body.get("account") or body
            if hasattr(account, "dict"):
                account = account.dict()
            raw_orders = []
            for raw_order in account.get("orders") or []:
                if hasattr(raw_order, "dict"):
                    raw_order = raw_order.dict()
                raw_orders.append(dict(raw_order))
            self._ingest_remote_pending_orders(raw_orders)
            self.last_transaction_id = str(
                body.get("lastTransactionID") or account.get("lastTransactionID") or self.last_transaction_id
            )
            self._emit_order_event(
                {
                    "event": "cancel_force_resolve_remote",
                    "broker_order_id": broker_order_id,
                    "pending_n": len(raw_orders),
                }
            )
        except Exception as exc:
            self._emit_order_event(
                {
                    "event": "network_order_error",
                    "action": "cancel_force_resolve",
                    "broker_order_id": broker_order_id,
                    "error": str(exc),
                }
            )
            raise
        return self._resolve_remote_order_id(broker_order_id)

    def reconcile_orders(self) -> List[BrokerOrder]:
        return [self._orders_cache[order_id] for order_id in self._active_order_ids if order_id in self._orders_cache]

    def reconcile_positions(self) -> List[Position]:
        return list(self._positions_cache.values())

    def reconcile_from_account_details(self, body: Optional[Dict[str, Any]] = None) -> None:
        if self.supervisor is not None:
            self.supervisor.start_reconciliation("oanda_account_details")
        if body is None:
            if self.client is None:
                raise OandaConfigurationError("reconcile_from_account_details needs a client or body")
            body = self.client.account_details()
        account = body.get("account") or body
        if hasattr(account, "dict"):
            account = account.dict()
        self.last_transaction_id = str(body.get("lastTransactionID") or account.get("lastTransactionID") or "")
        self.store.append_event(
            "reconciliation_events",
            {"event": "oanda_account_details_start", "last_transaction_id": self.last_transaction_id},
        )
        raw_orders = []
        for raw_order in account.get("orders") or []:
            if hasattr(raw_order, "dict"):
                raw_order = raw_order.dict()
            raw_orders.append(dict(raw_order))
            self.on_order_status(dict(raw_order, type="order_status"))
        self._ingest_remote_pending_orders(raw_orders)
        trades_cache = []
        for raw_trade in account.get("trades") or []:
            if hasattr(raw_trade, "dict"):
                raw_trade = raw_trade.dict()
            trades_cache.append(dict(raw_trade))
        self._account_trades_cache = trades_cache
        self._account_trades_cache_at = time.time()
        self._rewrite_positions_from_account(account, reason="startup_reconcile")
        sweep = self.sweep_remote_order_authority(
            pending_orders=raw_orders,
            cancel_orphans=True,
            reason="startup_reconcile",
            force_fetch=False,
        )
        self.store.append_event(
            "reconciliation_events",
            {
                "event": "oanda_account_details_done",
                "orders": len(list(self._orders_cache.values())),
                "positions": len(list(self._positions_cache.values())),
                "last_transaction_id": self.last_transaction_id,
                "remote_pending": int(sweep.get("remote_pending") or 0),
                "orphans_cancelled": int(sweep.get("orphans_cancelled") or 0),
            },
        )
        if self.supervisor is not None:
            self.supervisor.mark_reconciled("oanda_account_details_reconciled")

    def maybe_sweep_remote_order_authority(self, *, min_interval_s: float = _REMOTE_AUTHORITY_SWEEP_SECONDS) -> Dict[str, Any]:
        import time

        now = time.time()
        pending_gate = set(self._pending_gate_off_sweep_strategy_ids)
        if pending_gate:
            self._pending_gate_off_sweep_strategy_ids.clear()
            return self.sweep_remote_order_authority(
                strategy_ids=pending_gate,
                cancel_orphans=True,
                reason="orphan_after_gate_off",
                force_fetch=True,
            )
        if self._last_authority_sweep_at and (now - self._last_authority_sweep_at) < float(min_interval_s):
            return {"skipped": True, "age_s": now - self._last_authority_sweep_at}
        return self.sweep_remote_order_authority(cancel_orphans=True, reason="timer_sweep", force_fetch=True)

    def sweep_remote_order_authority(
        self,
        *,
        pending_orders: Optional[List[Dict[str, Any]]] = None,
        strategy_ids: Optional[Iterable[str]] = None,
        cancel_orphans: bool = True,
        reason: str = "orphan_sweep",
        force_fetch: bool = False,
    ) -> Dict[str, Any]:
        """Pull remote pending orders tagged for this broker and cancel orphans.

        Orphans = entry-style rests whose clientExtensions.id is not in local
        ``_active_order_ids``. Protective SL/TP (trade-linked) are never cancelled.
        """
        import time

        owned = set(self._authority_strategy_ids_resolved())
        if strategy_ids is not None:
            owned = {str(sid).strip() for sid in strategy_ids if str(sid).strip()}
        account_snapshot: Optional[Dict[str, Any]] = None
        if pending_orders is None:
            if force_fetch and self.client is not None:
                body = self.client.account_details()
                account = body.get("account") or body
                if hasattr(account, "dict"):
                    account = account.dict()
                account_snapshot = dict(account) if isinstance(account, dict) else None
                pending_orders = []
                for raw_order in account.get("orders") or []:
                    if hasattr(raw_order, "dict"):
                        raw_order = raw_order.dict()
                    pending_orders.append(dict(raw_order))
                self.last_transaction_id = str(
                    body.get("lastTransactionID") or account.get("lastTransactionID") or self.last_transaction_id
                )
            else:
                pending_orders = list(self._pending_remote_snapshot)
        self._ingest_remote_pending_orders(pending_orders)
        remote_for_owned: List[Dict[str, Any]] = []
        orphans: List[Dict[str, Any]] = []
        for raw in pending_orders or []:
            meta = self._remote_order_meta(raw)
            if meta["order_type"] in _OANDA_PROTECTIVE_ORDER_TYPES:
                continue
            if meta["order_type"] not in _OANDA_ENTRY_ORPHAN_ORDER_TYPES:
                continue
            if not meta["strategy_id"] or meta["strategy_id"] not in owned:
                continue
            remote_for_owned.append(meta)
            local_id = meta["client_id"]
            if not local_id or local_id not in self._active_order_ids:
                orphans.append(meta)
        local_open = len(self._active_order_ids)
        remote_pending = len(remote_for_owned)
        cancelled = 0
        if cancel_orphans and self.client is not None:
            for meta in orphans:
                remote_id = str(meta.get("remote_id") or "")
                if not remote_id:
                    continue
                try:
                    raw = self.client.cancel_order(remote_id)
                    cancelled += 1
                    self._emit_order_event(
                        {
                            "event": "cancel",
                            "oanda_order_id": remote_id,
                            "reason": reason,
                            "broker_order_id": meta.get("client_id") or "",
                            "strategy_id": meta.get("strategy_id") or "",
                            "orphan": True,
                        }
                    )
                    self._emit_order_event(
                        {"event": "network_order_response", "action": "orphan_cancel", "response": _jsonable(raw)}
                    )
                    local_id = str(meta.get("client_id") or "")
                    if local_id:
                        self._oanda_order_ids.pop(local_id, None)
                        local_order = self._orders_cache.get(local_id)
                        if local_order is not None and local_order.status in {
                            "submitted",
                            "partially_filled",
                            "working",
                            "pendingnew",
                        }:
                            updated = replace(local_order, status="cancelled", updated_at=utc_now_iso())
                            self._orders_cache[local_id] = updated
                            self._active_order_ids.pop(local_id, None)
                            self.store.upsert_row("orders", "broker_order_id", as_row(updated))
                except Exception as exc:
                    self._emit_order_event(
                        {
                            "event": "network_order_error",
                            "action": "orphan_cancel",
                            "oanda_order_id": remote_id,
                            "error": str(exc),
                            "reason": reason,
                        }
                    )
        # When we already paid for account_details, also refresh owned scoped positions so
        # stopLossOnFill exits clear local ghosts within ~60s (changes.positions is often empty).
        if account_snapshot is not None and self._position_scope_instruments is not None:
            self._rewrite_positions_from_account(account_snapshot, reason="authority_sweep:%s" % reason)
        result = {
            "owned_strategy_ids": sorted(owned),
            "local_open": local_open,
            "remote_pending": remote_pending,
            "orphans_seen": len(orphans),
            "orphans_cancelled": cancelled,
            "pending_gt_local": remote_pending > local_open,
            "reason": reason,
        }
        if remote_pending > local_open:
            self._emit_order_event({"event": "pending_remote_gt_local_open", **result})
        self._emit_order_event({"event": "remote_order_authority_sweep", **result})
        self._last_authority_sweep_at = time.time()
        return result

    def sweep_orphan_protectives_when_flat(
        self,
        *,
        strategy_id: str,
        instrument: str,
        reason: str = "orphan_protective_flat",
        pending_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """Cancel strategy-owned protective rests when local+broker focus exposure is flat.

        Entry orphan sweep never cancels ``STOP_LOSS`` / ``TAKE_PROFIT``. After a flat
        book those can linger (Aug 14 NAS/SPX v2b). Also cancels local working stops
        tagged to this strategy on the focus instrument when qty==0.
        """
        inst = str(instrument or "").upper()
        sid = str(strategy_id or "").strip()
        if not sid or not inst:
            return 0
        local_qty = sum(
            float(p.quantity or 0.0)
            for p in self._positions_cache.values()
            if str(p.instrument or "").upper() == inst
            and str(p.strategy_id or "") in {sid, "oanda", ""}
        )
        if abs(local_qty) > 1e-9:
            return 0
        if pending_orders is None:
            if self.client is not None:
                try:
                    body = self.client.account_details()
                    account = body.get("account") or body
                    if hasattr(account, "dict"):
                        account = account.dict()
                    pending_orders = []
                    for raw_order in account.get("orders") or []:
                        if hasattr(raw_order, "dict"):
                            raw_order = raw_order.dict()
                        pending_orders.append(dict(raw_order))
                    # Confirm broker-owned qty still flat for this tag/instrument.
                    owned = self._owned_scoped_positions_from_account(
                        dict(account) if isinstance(account, dict) else {},
                        authority={sid},
                    )
                    broker_qty = sum(
                        float(p.quantity or 0.0)
                        for p in owned
                        if str(p.instrument or "").upper() == inst
                    )
                    if abs(broker_qty) > 1e-9:
                        return 0
                    open_trade_ids = self._open_trade_ids_from_account(
                        dict(account) if isinstance(account, dict) else {},
                        instrument=inst,
                        authority={sid},
                    )
                except Exception as exc:
                    self._emit_order_event(
                        {"event": "orphan_protective_sweep_error", "error": str(exc), "reason": reason}
                    )
                    pending_orders = list(self._pending_remote_snapshot)
                    open_trade_ids = set()
            else:
                pending_orders = list(self._pending_remote_snapshot)
                open_trade_ids = set()
        else:
            open_trade_ids = set()

        cancelled = 0
        oanda_inst = self.config.symbol_for(inst)
        for raw in pending_orders or []:
            meta = self._remote_order_meta(raw)
            otype = meta["order_type"]
            remote_id = str(meta.get("remote_id") or "")
            if not remote_id:
                continue
            trade_id = str(raw.get("tradeID") or raw.get("tradeId") or "")
            tagged = meta["strategy_id"] == sid
            linked_orphan = bool(trade_id) and trade_id not in open_trade_ids and (
                otype in _OANDA_PROTECTIVE_ORDER_TYPES
            )
            same_instrument = self.config.internal_for(meta["instrument"] or oanda_inst).upper() == inst
            if otype in _OANDA_PROTECTIVE_ORDER_TYPES and same_instrument and (tagged or linked_orphan):
                if self.client is None:
                    cancelled += 1
                    continue
                try:
                    self.client.cancel_order(remote_id)
                    cancelled += 1
                    self._emit_order_event(
                        {
                            "event": "cancel",
                            "oanda_order_id": remote_id,
                            "reason": reason,
                            "orphan_protective": True,
                            "strategy_id": sid,
                            "tradeID": trade_id,
                        }
                    )
                except Exception as exc:
                    self._emit_order_event(
                        {
                            "event": "network_order_error",
                            "action": "orphan_protective_cancel",
                            "oanda_order_id": remote_id,
                            "error": str(exc),
                            "reason": reason,
                        }
                    )
            # Local-mirrored entry stops left working while flat (Aug 14 style).
            if (
                otype in _OANDA_ENTRY_ORPHAN_ORDER_TYPES
                and same_instrument
                and tagged
                and meta["client_id"]
                and meta["client_id"] not in self._active_order_ids
            ):
                if self.client is None:
                    cancelled += 1
                    continue
                try:
                    self.client.cancel_order(remote_id)
                    cancelled += 1
                    self._emit_order_event(
                        {
                            "event": "cancel",
                            "oanda_order_id": remote_id,
                            "reason": reason,
                            "orphan_entry_while_flat": True,
                            "strategy_id": sid,
                        }
                    )
                except Exception as exc:
                    self._emit_order_event(
                        {
                            "event": "network_order_error",
                            "action": "orphan_flat_entry_cancel",
                            "oanda_order_id": remote_id,
                            "error": str(exc),
                        }
                    )

        # Mirror: cancel local working protective rows when flat — never intentional entry arms.
        for order_id, order in list(self._orders_cache.items()):
            if order_id not in self._active_order_ids:
                continue
            if str(order.instrument or "").upper() != inst:
                continue
            if str(order.strategy_id or "") != sid:
                continue
            role = str(order.bracket_role or "").lower()
            otype = str(order.order_type or "").lower()
            if role in {"entry"}:
                continue
            if role in {"stop", "wide_stop", "runner_stop", "tp1", "tp2", "target", "sl", "protective_stop"} or otype in {
                "stop_loss",
                "take_profit",
            }:
                try:
                    self.cancel_order(order_id, reason=reason)
                    cancelled += 1
                except Exception as exc:
                    self._emit_order_event(
                        {
                            "event": "local_orphan_protective_cancel_error",
                            "broker_order_id": order_id,
                            "error": str(exc),
                        }
                    )
        self._emit_order_event(
            {
                "event": "orphan_protective_sweep",
                "reason": reason,
                "strategy_id": sid,
                "instrument": inst,
                "cancelled": cancelled,
            }
        )
        return cancelled

    def _open_trade_ids_from_account(
        self,
        account: Dict[str, Any],
        *,
        instrument: str,
        authority: Set[str],
    ) -> Set[str]:
        inst = str(instrument or "").upper()
        open_ids: Set[str] = set()
        for raw_trade in account.get("trades") or []:
            if hasattr(raw_trade, "dict"):
                raw_trade = raw_trade.dict()
            raw_trade = dict(raw_trade)
            trade_inst = self.config.internal_for(str(raw_trade.get("instrument") or "")).upper()
            if trade_inst != inst:
                continue
            tid = str(raw_trade.get("id") or raw_trade.get("tradeID") or "")
            if not tid:
                continue
            tag = self._strategy_tag_for_open_trade(tid)
            if tag and tag not in authority:
                continue
            # Untagged open trades on focus instrument: still treat as open so we do not
            # cancel foreign protectives linked to live trades we cannot attribute.
            open_ids.add(tid)
        return open_ids

    def apply_account_changes(self, body: Dict[str, Any]) -> List[Fill]:
        changes = body.get("changes") or {}
        if hasattr(changes, "dict"):
            changes = changes.dict()
        fills: List[Fill] = []
        for key in ("ordersCreated", "ordersFilled", "ordersCancelled", "ordersTriggered"):
            for raw_order in changes.get(key) or []:
                if hasattr(raw_order, "dict"):
                    raw_order = raw_order.dict()
                self.on_order_status(dict(raw_order, type="order_status"))
        for raw_trade in changes.get("tradesOpened") or []:
            if hasattr(raw_trade, "dict"):
                raw_trade = raw_trade.dict()
            self._emit_order_event({"event": "trade_opened", **dict(raw_trade)})
        closed_scoped: Set[str] = set()
        for raw_trade in changes.get("tradesClosed") or []:
            if hasattr(raw_trade, "dict"):
                raw_trade = raw_trade.dict()
            raw_trade = dict(raw_trade)
            self._emit_order_event({"event": "trade_closed", **raw_trade})
            if self._position_scope_instruments is not None:
                inst = self.config.internal_for(str(raw_trade.get("instrument") or "")).upper()
                if inst in self._position_scope_instruments:
                    closed_scoped.add(inst)
        for raw_fill in changes.get("transactions") or []:
            if hasattr(raw_fill, "dict"):
                raw_fill = raw_fill.dict()
            if str(raw_fill.get("type") or "").endswith("FILL") or raw_fill.get("type") in {"ORDER_FILL", "MarketOrderFill"}:
                fill_id = str(raw_fill.get("id") or raw_fill.get("fill_id") or "")
                if fill_id and any(f.fill_id == fill_id for f in self._pending_fills):
                    continue
                # Skip if already mirrored into fills.csv (e.g. from create response).
                if fill_id:
                    existing = [r for r in self.store.read_table("fills") if r.get("fill_id") == fill_id]
                    if existing:
                        continue
                try:
                    fills.append(self.on_fill(dict(raw_fill, type="fill")))
                except KeyError:
                    self._emit_order_event({"event": "fill_unmatched", **dict(raw_fill)})
        # Broker-linked SL/TP fills often cannot match a local order id (stopLossOnFill).
        # Without this, strategy-owned position rows ghost after the broker is flat —
        # heartbeats show open_positions>0 with orders=0 until the next full reconcile.
        if self._position_scope_instruments is not None:
            raw_positions = changes.get("positions") or []
            if raw_positions:
                self._sync_scoped_positions_from_changes(raw_positions)
            elif closed_scoped and self.client is not None:
                local_open_scoped = any(
                    str(p.instrument or "").upper() in closed_scoped and float(p.quantity or 0) != 0
                    for p in self._positions_cache.values()
                )
                if local_open_scoped:
                    try:
                        details = self.client.account_details()
                        account = details.get("account") or details
                        if hasattr(account, "dict"):
                            account = account.dict()
                        self._rewrite_positions_from_account(
                            dict(account) if isinstance(account, dict) else {},
                            reason="trades_closed_ghost_refresh",
                        )
                        self.last_transaction_id = str(
                            details.get("lastTransactionID")
                            or (account.get("lastTransactionID") if isinstance(account, dict) else "")
                            or self.last_transaction_id
                        )
                    except Exception as exc:
                        self._emit_order_event(
                            {
                                "event": "trades_closed_ghost_refresh_error",
                                "instruments": sorted(closed_scoped),
                                "error": str(exc),
                            }
                        )
        self.last_transaction_id = str(body.get("lastTransactionID") or self.last_transaction_id)
        self.store.append_event(
            "reconciliation_events",
            {"event": "oanda_account_changes_applied", "last_transaction_id": self.last_transaction_id},
        )
        return fills

    def _rewrite_positions_from_account(self, account: Dict[str, Any], *, reason: str) -> None:
        """Rewrite local positions from an account snapshot (owned-tag aware when scoped)."""
        self._positions_cache = {}
        authority = self._authority_strategy_ids_resolved()
        if self._position_scope_instruments is not None and authority:
            # Shared practice account: only mirror trades opened by this demo's strategy tag.
            for position in self._owned_scoped_positions_from_account(account, authority=authority):
                self._positions_cache[position.position_id] = position
        else:
            for raw_position in account.get("positions") or []:
                if hasattr(raw_position, "dict"):
                    raw_position = raw_position.dict()
                position = self._position_from_oanda(raw_position)
                if position.quantity == 0:
                    continue
                if (
                    self._position_scope_instruments is not None
                    and str(position.instrument or "").upper() not in self._position_scope_instruments
                ):
                    continue
                self._positions_cache[position.position_id] = position
        if self._position_scope_instruments is not None:
            # Full rewrite drops stale foreign / ghost rows left by prior account-wide upserts.
            self.store.write_table("positions", [as_row(p) for p in self._positions_cache.values()])
        else:
            for position in self._positions_cache.values():
                self.store.upsert_row("positions", "position_id", as_row(position))
        self._emit_order_event(
            {
                "event": "owned_scoped_positions_rewritten",
                "reason": reason,
                "positions": [
                    {
                        "instrument": p.instrument,
                        "quantity": p.quantity,
                        "strategy_id": p.strategy_id,
                    }
                    for p in self._positions_cache.values()
                ],
            }
        )

    def _sync_scoped_positions_from_changes(self, raw_positions: List[Any]) -> None:
        """Apply Account Changes position snapshots for scoped instruments (broker truth).

        When authority strategies are registered, only **flat** snapshots clear local
        rows. Non-zero account qty is not imported (sibling demos share instruments on
        the practice account); ownership is restored via matched fills or full
        ``reconcile_from_account_details``.
        """
        if not raw_positions:
            return
        authority = self._authority_strategy_ids_resolved()
        touched: Set[str] = set()
        for raw_position in raw_positions:
            if hasattr(raw_position, "dict"):
                raw_position = raw_position.dict()
            position = self._position_from_oanda(dict(raw_position))
            inst = str(position.instrument or "").upper()
            if inst not in self._position_scope_instruments:
                continue
            qty = float(position.quantity or 0)
            if authority and qty != 0:
                # Sibling sleeve inventory — do not stamp into this demo.
                continue
            touched.add(inst)
            # Drop strategy-owned / ghost rows for this instrument, then mirror broker qty.
            for pid, pos in list(self._positions_cache.items()):
                if str(pos.instrument or "").upper() == inst:
                    del self._positions_cache[pid]
            if qty != 0:
                self._positions_cache[position.position_id] = position
        if not touched:
            return
        self.store.write_table("positions", [as_row(p) for p in self._positions_cache.values()])
        self._emit_order_event(
            {
                "event": "scoped_positions_synced_from_changes",
                "instruments": sorted(touched),
                "open": [
                    {"instrument": p.instrument, "quantity": p.quantity, "strategy_id": p.strategy_id}
                    for p in self._positions_cache.values()
                    if str(p.instrument or "").upper() in touched
                ],
            }
        )

    def _tx_dict_for_id(self, tx_id: str) -> Dict[str, Any]:
        if self.client is None or not tx_id:
            return {}
        try:
            resp = self.client.ctx.transaction.get(self.config.account_id, str(tx_id))
        except Exception:
            return {}
        body = getattr(resp, "body", None) or {}
        raw = body.get("transaction") if isinstance(body, dict) else None
        if raw is None:
            return {}
        if hasattr(raw, "dict"):
            return dict(raw.dict())
        return dict(raw) if isinstance(raw, dict) else {}

    def _strategy_tag_for_open_trade(self, trade_id: str) -> Optional[str]:
        fill = self._tx_dict_for_id(str(trade_id))
        order_id = str(fill.get("orderID") or fill.get("order_id") or "")
        if not order_id:
            return None
        order_tx = self._tx_dict_for_id(order_id)
        extensions = order_tx.get("clientExtensions") or {}
        if hasattr(extensions, "dict"):
            extensions = extensions.dict()
        if not isinstance(extensions, dict):
            extensions = {}
        tag = str(extensions.get("tag") or "").strip()
        return tag or None

    def _owned_scoped_positions_from_account(
        self,
        account: Dict[str, Any],
        *,
        authority: Set[str],
    ) -> List[Position]:
        """Build positions for scoped instruments owned by authority strategy tags."""
        scope = self._position_scope_instruments or set()
        # Accumulate owned qty/avg per (strategy, instrument).
        buckets: Dict[Tuple[str, str], Dict[str, float]] = {}
        for raw_trade in account.get("trades") or []:
            if hasattr(raw_trade, "dict"):
                raw_trade = raw_trade.dict()
            raw_trade = dict(raw_trade)
            trade_id = str(raw_trade.get("id") or "")
            inst = self.config.internal_for(str(raw_trade.get("instrument") or "")).upper()
            if not trade_id or inst not in scope:
                continue
            try:
                qty = float(raw_trade.get("currentUnits") or raw_trade.get("initialUnits") or 0)
            except (TypeError, ValueError):
                continue
            if qty == 0:
                continue
            try:
                avg = float(raw_trade.get("price") or 0)
            except (TypeError, ValueError):
                avg = 0.0
            tag = self._strategy_tag_for_open_trade(trade_id)
            if not tag or tag not in authority:
                continue
            key = (tag, inst)
            cur = buckets.get(key) or {"qty": 0.0, "avg_price": avg}
            old_qty = float(cur["qty"])
            new_qty = old_qty + qty
            if new_qty != 0 and old_qty != 0:
                cur["avg_price"] = (old_qty * float(cur["avg_price"]) + qty * avg) / new_qty
            else:
                cur["avg_price"] = avg
            cur["qty"] = new_qty
            buckets[key] = cur
        account_mode = "paper" if self.config.env == "practice" else "live"
        out: List[Position] = []
        for (strategy_id, inst), vals in buckets.items():
            out.append(
                Position(
                    position_id="%s|%s|%s" % (strategy_id, inst, account_mode),
                    strategy_id=strategy_id,
                    instrument=inst,
                    account_mode=account_mode,
                    quantity=float(vals["qty"]),
                    avg_price=float(vals["avg_price"]),
                    realized_pnl=0.0,
                    updated_at=utc_now_iso(),
                )
            )
        return out

    def attach_bracket(self, parent_order: BrokerOrder, intent: OrderIntent) -> List[BrokerOrder]:
        # Prefer SL/TP on fill at submit time; local attach is paper/practice only.
        if parent_order.account_mode == "live":
            raise OandaRoutingBlocked("Live bracket attach should use stopLossOnFill/takeProfitOnFill at submit")
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
        return children

    def process_bar(self, bar: Bar) -> List[Fill]:
        # Drain fills mirrored from create/close responses so Engine can on_fills
        # after strategy submissions (same loop PaperBroker uses for bar fills).
        fills = list(self._pending_fills)
        self._pending_fills = []
        return fills

    def process_market_close_bar(self, bar: Bar) -> List[Fill]:
        return self.process_bar(bar)

    def on_order_status(self, event: Dict[str, Any]) -> Optional[BrokerOrder]:
        broker_order_id = str(event.get("broker_order_id") or event.get("clientOrderID") or "")
        extensions = event.get("clientExtensions")
        if not broker_order_id and isinstance(extensions, dict):
            broker_order_id = str(extensions.get("id") or "")
        oanda_order_id = str(event.get("id") or event.get("orderID") or event.get("order_id") or "")
        if broker_order_id and oanda_order_id:
            self._oanda_order_ids[broker_order_id] = oanda_order_id
        if not broker_order_id and oanda_order_id:
            for local_id, remote_id in self._oanda_order_ids.items():
                if remote_id == oanda_order_id:
                    broker_order_id = local_id
                    break
        if not broker_order_id:
            return None
        order = self._orders_cache.get(broker_order_id)
        if order is None:
            return None
        # Never resurrect terminal local orders from a stale remote PENDING.
        # Those are orphans for sweep_remote_order_authority to cancel.
        if order.status in {"cancelled", "filled", "rejected"}:
            self._active_order_ids.pop(broker_order_id, None)
            self._emit_order_event(
                {
                    "event": "order_status_ignored_terminal_local",
                    "broker_order_id": broker_order_id,
                    "local_status": order.status,
                    "remote_state": event.get("state") or event.get("status"),
                    "oanda_order_id": oanda_order_id,
                }
            )
            return order
        status = normalize_oanda_order_status(str(event.get("state") or event.get("status") or order.status))
        remaining = int(
            float(
                event.get("remaining_quantity")
                if event.get("remaining_quantity") is not None
                else event.get("units")
                if event.get("units") is not None
                else order.remaining_quantity
            )
        )
        if remaining < 0:
            remaining = abs(remaining)
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
        broker_order_id = self._resolve_fill_broker_order_id(event)
        if not broker_order_id:
            # Never guess by instrument: on a shared practice account that attaches
            # sibling fills to the wrong resting order (false local fill → remote orphan).
            raise KeyError("fill missing client order id")
        order = self._get_order(broker_order_id)
        if order.status in {"cancelled", "filled", "rejected"}:
            self._emit_order_event(
                {
                    "event": "fill_ignored_terminal_local",
                    "broker_order_id": broker_order_id,
                    "local_status": order.status,
                    "oanda_order_id": str(event.get("orderID") or event.get("order_id") or ""),
                    "fill_id": str(event.get("fill_id") or event.get("id") or ""),
                    "price": event.get("price") or event.get("fillPrice"),
                    "units": event.get("units") or event.get("quantity"),
                }
            )
            raise KeyError("fill for terminal local order %s" % broker_order_id)
        units = event.get("units") or event.get("quantity") or event.get("fillQty") or order.remaining_quantity
        quantity = abs(int(float(units)))
        price = float(event.get("price") or event.get("fillPrice") or event.get("averagePrice") or event.get("pl") or 0)
        if price == 0 and event.get("tradeOpened"):
            trade = event["tradeOpened"]
            if hasattr(trade, "dict"):
                trade = trade.dict()
            price = float(trade.get("price") or price)
        intent = self._intents_cache.get(order.intent_id)
        fill_reason = (
            order.bracket_role
            or (intent.reason if intent is not None else "")
            or str(event.get("reason") or "")
            or order.order_type
        )
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
            ts=str(event.get("event_ts") or event.get("time") or event.get("timestamp") or event.get("ts") or utc_now_iso()),
            reason=fill_reason,
        )
        remaining = max(order.remaining_quantity - quantity, 0)
        status = "filled" if remaining == 0 else "partially_filled"
        updated = replace(order, status=status, remaining_quantity=remaining, updated_at=utc_now_iso())
        self._orders_cache[order.broker_order_id] = updated
        if status == "filled":
            self._active_order_ids.pop(order.broker_order_id, None)
        else:
            self._active_order_ids[order.broker_order_id] = True
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        self.store.append_rows("fills", [as_row(fill)])
        self._apply_fill_to_position(fill)
        self._cancel_local_oco_peers(updated)
        self._emit_order_event({"event": "fill", **as_row(fill)})
        return fill

    def _resolve_fill_broker_order_id(self, event: Dict[str, Any]) -> str:
        """Map an OANDA fill to a local broker order id without instrument guessing."""
        broker_order_id = str(event.get("broker_order_id") or event.get("clientOrderID") or "")
        extensions = event.get("clientExtensions")
        if not broker_order_id and isinstance(extensions, dict):
            broker_order_id = str(extensions.get("id") or "")
        oanda_order_id = str(event.get("orderID") or event.get("order_id") or "")
        if not broker_order_id and oanda_order_id:
            for local_id, remote_id in self._oanda_order_ids.items():
                if remote_id == oanda_order_id:
                    broker_order_id = local_id
                    break
        return broker_order_id

    def go_flat(self, instruments: Iterable[str] = DEFAULT_INSTRUMENTS) -> List[Dict[str, Any]]:
        if self.supervisor is not None:
            self.supervisor.trigger_emergency_flatten("oanda_go_flat_requested")
        payloads: List[Dict[str, Any]] = []
        for order_id in list(self._active_order_ids):
            self.cancel_order(order_id, reason="go_flat")
        # Refresh positions from OANDA when possible so we only close open sides.
        # Sending longUnits=ALL + shortUnits=ALL when one side is flat rejects the whole closeout.
        if self.client is not None:
            try:
                self.reconcile_from_account_details()
            except Exception as exc:
                self._emit_order_event({"event": "go_flat_reconcile_error", "error": str(exc)})
        open_by_instrument: Dict[str, float] = {}
        for pos in self.reconcile_positions():
            # Prefer account-level rows from reconcile_from_account_details (strategy_id=oanda)
            # so we do not double-count strategy-local mirrors.
            if pos.strategy_id != "oanda" or pos.quantity == 0:
                continue
            open_by_instrument[pos.instrument] = float(pos.quantity)
        for instrument in instruments:
            qty = float(open_by_instrument.get(instrument, 0.0))
            oanda_instrument = self.config.symbol_for(instrument)
            if self.client is None:
                # Offline scaffold: emit dual-side close payload (historical CLI behavior).
                payload = {"instrument": oanda_instrument, "longUnits": "ALL", "shortUnits": "ALL"}
                payloads.append(payload)
                self._emit_order_event({"event": "close_position", "oanda_payload": payload})
                continue
            if qty == 0:
                continue
            payload = {"instrument": oanda_instrument}
            if qty > 0:
                payload["longUnits"] = "ALL"
            if qty < 0:
                payload["shortUnits"] = "ALL"
            payloads.append(payload)
            self._emit_order_event({"event": "close_position", "oanda_payload": payload})
            try:
                kwargs = {k: v for k, v in payload.items() if k != "instrument"}
                raw = self.client.close_position(oanda_instrument, **kwargs)
                raw = _jsonable(raw) if not isinstance(raw, dict) else {k: _jsonable(v) for k, v in raw.items()}
                self._emit_order_event({"event": "network_order_response", "action": "close_position", "response": raw})
                if raw.get("lastTransactionID"):
                    self.last_transaction_id = str(raw["lastTransactionID"])
                for key in ("longOrderFillTransaction", "shortOrderFillTransaction", "orderFillTransaction"):
                    fill_tx = raw.get(key)
                    if isinstance(fill_tx, dict) and fill_tx:
                        try:
                            fill = self.on_fill(dict(fill_tx, type="fill"))
                            self._pending_fills.append(fill)
                        except KeyError:
                            self._emit_order_event({"event": "fill_unmatched_on_close", "fill": fill_tx})
            except Exception as exc:
                self._emit_order_event({"event": "network_order_error", "action": "close_position", "error": str(exc)})
        return payloads

    def order_intent_to_oanda_order(self, intent: OrderIntent, order: BrokerOrder) -> Dict[str, Any]:
        units = int(order.quantity) if order.side.lower() == "buy" else -int(order.quantity)
        order_type = oanda_order_type(order.order_type)
        precision = self.display_precision_for(order.instrument)
        # OANDA MARKET orders only accept FOK/IOC (not GTC).
        if order_type == "MARKET":
            tif_key = str(intent.tif or "FOK").strip().lower()
            if tif_key not in {"fok", "ioc"}:
                tif_key = "fok"
            tif = oanda_tif(tif_key)
        else:
            tif = oanda_tif(intent.tif or "GTC")
        body: Dict[str, Any] = {
            "type": order_type,
            "instrument": self.get_active_contract(order.instrument),
            "units": str(units),
            "timeInForce": tif,
            "positionFill": "DEFAULT",
            "clientExtensions": {
                "id": order.broker_order_id[:128],
                "tag": order.strategy_id[:128],
                "comment": ("trade=%s intent=%s" % (order.trade_id, order.intent_id))[:128],
            },
        }
        if order_type == "LIMIT" and intent.limit_price is not None:
            body["price"] = format_oanda_price(intent.limit_price, precision)
        if order_type == "STOP" and intent.stop_price is not None:
            body["price"] = format_oanda_price(intent.stop_price, precision)
        if intent.bracket_stop_price is not None:
            body["stopLossOnFill"] = {
                "price": format_oanda_price(intent.bracket_stop_price, precision),
                "timeInForce": "GTC",
            }
        if intent.bracket_target_price is not None:
            body["takeProfitOnFill"] = {
                "price": format_oanda_price(intent.bracket_target_price, precision),
                "timeInForce": "GTC",
            }
        return body

    def _send_create_order(self, payload: Dict[str, Any], order_ref: str) -> None:
        if self.client is None:
            return
        try:
            raw = self.client.create_order(payload)
            raw = _jsonable(raw) if not isinstance(raw, dict) else {k: _jsonable(v) for k, v in raw.items()}
            self._emit_order_event({"event": "network_order_response", "action": "create", "order_ref": order_ref, "response": raw})
            order_create = raw.get("orderCreateTransaction") or raw.get("orderFillTransaction") or {}
            if hasattr(order_create, "dict"):
                order_create = order_create.dict()
            remote_id = str(order_create.get("id") or "")
            if not remote_id and isinstance(raw.get("orderFillTransaction"), dict):
                remote_id = str(raw["orderFillTransaction"].get("orderID") or raw["orderFillTransaction"].get("id") or "")
            if remote_id:
                self._oanda_order_ids[order_ref] = remote_id
            # Immediate MARKET fills arrive on the create response — mirror them locally
            # and queue for Engine.process_bar → manager.on_fills.
            fill_tx = raw.get("orderFillTransaction")
            if isinstance(fill_tx, dict) and fill_tx:
                try:
                    fill = self.on_fill(dict(fill_tx, type="fill", broker_order_id=order_ref))
                    self._pending_fills.append(fill)
                except KeyError:
                    self._emit_order_event({"event": "fill_unmatched_on_create", "order_ref": order_ref, "fill": fill_tx})
            reject = raw.get("orderRejectTransaction") or raw.get("orderCancelTransaction")
            if isinstance(reject, dict) and str(reject.get("type") or "").endswith("REJECT"):
                self._emit_order_event({"event": "order_rejected", "order_ref": order_ref, "reject": reject})
                order = self._orders_cache.get(order_ref)
                if order is not None:
                    updated = replace(order, status="rejected", remaining_quantity=0, updated_at=utc_now_iso())
                    self._orders_cache[order_ref] = updated
                    self._active_order_ids.pop(order_ref, None)
                    self.store.upsert_row("orders", "broker_order_id", as_row(updated))
            if raw.get("lastTransactionID"):
                self.last_transaction_id = str(raw["lastTransactionID"])
        except Exception as exc:
            if self.supervisor is not None:
                self.supervisor.observe_order_ambiguity_age(self.supervisor.order_ambiguity_ms + 1, order_ref)
            self._emit_order_event({"event": "network_order_error", "action": "create", "order_ref": order_ref, "error": str(exc)})
            raise

    def _emit_order_event(self, event: Dict[str, Any]) -> None:
        self.store.append_event("oanda_order_events", _jsonable(event))


    def instrument_net_qty_from_account(self, account: Dict[str, Any], *, instrument: str) -> float:
        """Net open units for ``instrument`` across all strategy tags (shared account)."""
        inst = str(instrument or "").upper()
        if not inst:
            return 0.0
        total = 0.0
        for raw_trade in account.get("trades") or []:
            if hasattr(raw_trade, "dict"):
                raw_trade = raw_trade.dict()
            raw_trade = dict(raw_trade)
            trade_inst = self.config.internal_for(str(raw_trade.get("instrument") or "")).upper()
            if trade_inst != inst:
                continue
            try:
                total += float(raw_trade.get("currentUnits") or raw_trade.get("initialUnits") or 0)
            except (TypeError, ValueError):
                continue
        return float(total)

    def _refresh_account_trades_cache(self, *, force: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        if (
            not force
            and self._account_trades_cache_at
            and (now - self._account_trades_cache_at) < self._cross_book_cache_ttl_s
        ):
            return list(self._account_trades_cache)
        if self.client is None:
            return list(self._account_trades_cache)
        try:
            body = self.client.account_details()
            account = body.get("account") or body
            if hasattr(account, "dict"):
                account = account.dict()
            trades = []
            for raw in (account.get("trades") or []) if isinstance(account, dict) else []:
                if hasattr(raw, "dict"):
                    raw = raw.dict()
                trades.append(dict(raw))
            self._account_trades_cache = trades
            self._account_trades_cache_at = now
            if isinstance(account, dict):
                # Keep pending snapshot warm for orphan sweeps.
                pending = []
                for raw_order in account.get("orders") or []:
                    if hasattr(raw_order, "dict"):
                        raw_order = raw_order.dict()
                    pending.append(dict(raw_order))
                self._pending_remote_snapshot = pending
        except Exception as exc:
            self._emit_order_event({"event": "cross_book_account_refresh_error", "error": str(exc)})
        return list(self._account_trades_cache)

    def _local_strategy_qty(self, *, strategy_id: str, instrument: str) -> float:
        inst = str(instrument or "").upper()
        sid = str(strategy_id or "").strip()
        return sum(
            float(p.quantity or 0.0)
            for p in self._positions_cache.values()
            if str(p.instrument or "").upper() == inst and str(p.strategy_id or "") in {sid, "oanda", ""}
        )

    def _assert_cross_book_entry_allowed(self, intent: OrderIntent) -> None:
        """Block new non-reduce entries when another book already holds the instrument.

        Shared practice account: ST+PMC 3r must not re-arm LIMITs while runners (or
        any sibling) own NAS100/US30/etc. Always-on — independent of containment shadow.
        """
        if intent.reduce_only:
            return
        inst = str(intent.instrument or "").upper()
        if not inst:
            return
        local_qty = self._local_strategy_qty(strategy_id=str(intent.strategy_id or ""), instrument=inst)
        if abs(local_qty) > 1e-9:
            return
        trades = self._refresh_account_trades_cache()
        account_qty = self.instrument_net_qty_from_account({"trades": trades}, instrument=inst)
        if abs(account_qty) < 1e-9:
            return
        self._emit_order_event(
            {
                "event": "cross_book_entry_blocked",
                "strategy_id": intent.strategy_id,
                "instrument": inst,
                "account_qty": account_qty,
                "local_qty": local_qty,
                "reason": intent.reason,
                "bracket_role": intent.bracket_role,
            }
        )
        raise OandaRoutingBlocked(
            "cross_book_instrument_open: %s account_qty=%s local_qty=%s" % (inst, account_qty, local_qty)
        )

    def _assert_routing_allowed(self, intent: OrderIntent) -> None:
        if self.supervisor is not None and not self.supervisor.entries_allowed(intent):
            raise OandaRoutingBlocked("Runtime supervisor blocks new entries: %s" % self.supervisor.block_reason(intent))
        if intent.account_mode == "live" and not self.allow_live_routing:
            raise OandaRoutingBlocked("OANDA live order routing disabled")
        if self.config.env != "practice" and not self.allow_live_routing:
            raise OandaRoutingBlocked("OANDA non-practice env requires allow_live_routing=True")

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

    def _position_from_oanda(self, raw: Dict[str, Any]) -> Position:
        instrument = self.config.internal_for(str(raw.get("instrument") or ""))
        strategy_id = str(raw.get("strategy_id") or "oanda")
        account_mode = "paper" if self.config.env == "practice" else "live"
        long_units = raw.get("long") or {}
        short_units = raw.get("short") or {}
        if hasattr(long_units, "dict"):
            long_units = long_units.dict()
        if hasattr(short_units, "dict"):
            short_units = short_units.dict()
        long_qty = int(float(long_units.get("units") or 0))
        short_qty = int(float(short_units.get("units") or 0))
        quantity = long_qty + short_qty
        avg_price = 0.0
        if long_qty:
            avg_price = float(long_units.get("averagePrice") or 0.0)
        elif short_qty:
            avg_price = float(short_units.get("averagePrice") or 0.0)
        return Position(
            position_id="%s|%s|%s" % (strategy_id, instrument, account_mode),
            strategy_id=strategy_id,
            instrument=instrument,
            account_mode=account_mode,
            quantity=quantity,
            avg_price=avg_price,
            realized_pnl=float(raw.get("pl") or 0.0),
            updated_at=utc_now_iso(),
        )

    def _authority_strategy_ids_resolved(self) -> Set[str]:
        ids = set(self._authority_strategy_ids)
        for order in self._orders_cache.values():
            if order.strategy_id:
                ids.add(str(order.strategy_id))
        for intent in self._intents_cache.values():
            if intent.strategy_id:
                ids.add(str(intent.strategy_id))
        return ids

    def _remote_order_meta(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        extensions = raw.get("clientExtensions") or {}
        if hasattr(extensions, "dict"):
            extensions = extensions.dict()
        if not isinstance(extensions, dict):
            extensions = {}
        client_id = str(extensions.get("id") or raw.get("clientOrderID") or raw.get("broker_order_id") or "")
        strategy_id = str(extensions.get("tag") or raw.get("strategy_id") or "")
        remote_id = str(raw.get("id") or raw.get("orderID") or raw.get("order_id") or "")
        order_type = str(raw.get("type") or raw.get("orderType") or "").upper()
        instrument = str(raw.get("instrument") or "")
        return {
            "raw": raw,
            "client_id": client_id,
            "strategy_id": strategy_id,
            "remote_id": remote_id,
            "order_type": order_type,
            "instrument": instrument,
        }

    def _ingest_remote_pending_orders(self, pending_orders: Optional[List[Dict[str, Any]]]) -> None:
        snapshot: List[Dict[str, Any]] = []
        for raw in pending_orders or []:
            if hasattr(raw, "dict"):
                raw = raw.dict()
            meta = self._remote_order_meta(dict(raw))
            snapshot.append(dict(raw))
            client_id = meta["client_id"]
            remote_id = meta["remote_id"]
            if client_id and remote_id and client_id in self._orders_cache:
                self._oanda_order_ids[client_id] = remote_id
        self._pending_remote_snapshot = snapshot

    def _resolve_remote_order_id(self, broker_order_id: str) -> str:
        remote_id = str(self._oanda_order_ids.get(broker_order_id) or "")
        if remote_id:
            return remote_id
        for raw in self._pending_remote_snapshot:
            meta = self._remote_order_meta(raw)
            if meta["client_id"] == broker_order_id and meta["remote_id"]:
                self._oanda_order_ids[broker_order_id] = meta["remote_id"]
                return meta["remote_id"]
        return ""

    def _cancel_remote_by_client_id(self, broker_order_id: str, *, reason: str) -> None:
        remote_id = self._resolve_remote_order_id(broker_order_id)
        if not remote_id or self.client is None:
            return
        try:
            raw = self.client.cancel_order(remote_id)
            self._emit_order_event(
                {
                    "event": "cancel",
                    "oanda_order_id": remote_id,
                    "reason": reason,
                    "broker_order_id": broker_order_id,
                    "resolved_without_map": True,
                }
            )
            self._emit_order_event({"event": "network_order_response", "action": "cancel", "response": _jsonable(raw)})
            self._oanda_order_ids.pop(broker_order_id, None)
        except Exception as exc:
            self._emit_order_event(
                {
                    "event": "network_order_error",
                    "action": "cancel",
                    "oanda_order_id": remote_id,
                    "broker_order_id": broker_order_id,
                    "error": str(exc),
                }
            )

    def _should_cancel_resubmit_modify(self, order: BrokerOrder, reason: str) -> bool:
        reason_key = str(reason or "").strip().lower()
        if reason_key.startswith("refresh_entry") or reason_key in _CANCEL_RESUBMIT_MODIFY_REASONS:
            return True
        if order.reduce_only:
            return False
        return str(order.order_type or "").lower() == "limit"

    def _cancel_resubmit_remote_order(
        self,
        *,
        broker_order_id: str,
        remote_id: str,
        payload: Dict[str, Any],
        reason: str,
    ) -> None:
        old_remote = str(remote_id or "")
        if self.client is None:
            return
        if old_remote:
            try:
                raw = self.client.cancel_order(old_remote)
                self._emit_order_event(
                    {
                        "event": "cancel",
                        "oanda_order_id": old_remote,
                        "reason": reason,
                        "broker_order_id": broker_order_id,
                        "cancel_before_resubmit": True,
                    }
                )
                self._emit_order_event(
                    {"event": "network_order_response", "action": "cancel_before_resubmit", "response": _jsonable(raw)}
                )
            except Exception as exc:
                self._emit_order_event(
                    {
                        "event": "network_order_error",
                        "action": "cancel_before_resubmit",
                        "oanda_order_id": old_remote,
                        "error": str(exc),
                    }
                )
                # Still attempt create — remote may already be gone.
            self._oanda_order_ids.pop(broker_order_id, None)
            # Ensure old remote id is not mapped to any local order.
            for lid, rid in list(self._oanda_order_ids.items()):
                if rid == old_remote:
                    self._oanda_order_ids.pop(lid, None)
        self._send_create_order(payload, broker_order_id)
        new_remote = str(self._oanda_order_ids.get(broker_order_id) or "")
        if old_remote and old_remote in self._oanda_order_ids.values():
            raise OandaAdapterError(
                "cancel+resubmit left old OANDA id %s mapped after refresh of %s" % (old_remote, broker_order_id)
            )
        self._emit_order_event(
            {
                "event": "cancel_resubmit",
                "broker_order_id": broker_order_id,
                "old_oanda_order_id": old_remote,
                "new_oanda_order_id": new_remote,
                "reason": reason,
            }
        )

    def _extract_remote_order_id_from_replace(self, raw: Dict[str, Any]) -> str:
        for key in ("orderCreateTransaction", "orderFillTransaction", "orderCancelTransaction"):
            tx = raw.get(key) or {}
            if hasattr(tx, "dict"):
                tx = tx.dict()
            if isinstance(tx, dict):
                rid = str(tx.get("id") or tx.get("orderID") or "")
                if rid and key == "orderCreateTransaction":
                    return rid
                if rid and key == "orderFillTransaction":
                    return str(tx.get("orderID") or rid)
        order_created = raw.get("orderCreated") or raw.get("order")
        if hasattr(order_created, "dict"):
            order_created = order_created.dict()
        if isinstance(order_created, dict):
            return str(order_created.get("id") or "")
        return ""

    def _get_order(self, broker_order_id: str) -> BrokerOrder:
        order = self._orders_cache.get(broker_order_id)
        if order is None:
            raise KeyError("Broker order not found: %s" % broker_order_id)
        return order


def parse_instrument_map(raw: str) -> Dict[str, str]:
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
            raise OandaConfigurationError("OANDA_INSTRUMENT_MAP entries must look like EURUSD=EUR_USD")
        key, value = item.split("=", 1)
        out[key.strip().upper()] = value.strip()
    return out


def parse_oanda_ts(value: str) -> datetime:
    """Parse OANDA RFC3339 timestamps (may include nanoseconds; Python 3.8 only accepts µs)."""
    import re

    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # Truncate fractional seconds to 6 digits (microseconds) for fromisoformat.
    raw = re.sub(
        r"(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$|\Z)",
        r"\1",
        raw,
    )
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_oanda_price(price: float, precision: Optional[int] = None) -> str:
    """Format a price for OANDA order payloads.

    When ``precision`` is set (instrument ``displayPrecision``), round half-up to
    that many decimals — required to avoid ``PRICE_PRECISION_EXCEEDED`` rejects.
    """
    if precision is not None:
        from decimal import Decimal, ROUND_HALF_UP

        quant = Decimal(1).scaleb(-int(precision))
        rounded = Decimal(str(float(price))).quantize(quant, rounding=ROUND_HALF_UP)
        return format(rounded, "f")
    # Legacy trim (offline / unspecified): keep meaningful digits only.
    text = ("%.10f" % float(price)).rstrip("0").rstrip(".")
    return text if text else "0"


def oanda_order_type(order_type: str) -> str:
    lookup = {
        "market": "MARKET",
        "market_close": "MARKET",
        "limit": "LIMIT",
        "stop": "STOP",
        "stop_limit": "STOP",
    }
    key = str(order_type).strip().lower()
    if key not in lookup:
        raise OandaConfigurationError("Unsupported OANDA order type: %s" % order_type)
    return lookup[key]


def oanda_tif(tif: str) -> str:
    lookup = {"gtc": "GTC", "day": "GFD", "gfd": "GFD", "fok": "FOK", "ioc": "IOC"}
    key = str(tif or "GTC").strip().lower()
    return lookup.get(key, "GTC")


def normalize_oanda_order_status(status: str) -> str:
    key = str(status).strip().lower()
    mapping = {
        "pending": "working",
        "pendingnew": "pendingnew",
        "working": "working",
        "open": "working",
        "filled": "filled",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "triggered": "filled",
        "partially_filled": "partially_filled",
    }
    return mapping.get(key, key or "working")


def mid_price_from_event(event: Dict[str, Any]) -> Optional[float]:
    if event.get("price") is not None:
        return float(event["price"])
    if event.get("closeoutBid") is not None and event.get("closeoutAsk") is not None:
        return (float(event["closeoutBid"]) + float(event["closeoutAsk"])) / 2.0
    bid, ask = bid_ask_from_event(event)
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if bid is not None:
        return bid
    if ask is not None:
        return ask
    return None


def bid_ask_from_event(event: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    bid = None
    ask = None
    if event.get("bid") is not None:
        bid = float(event["bid"])
    if event.get("ask") is not None:
        ask = float(event["ask"])
    if bid is None and event.get("closeoutBid") is not None:
        bid = float(event["closeoutBid"])
    if ask is None and event.get("closeoutAsk") is not None:
        ask = float(event["closeoutAsk"])
    bids = event.get("bids") or []
    asks = event.get("asks") or []
    if bid is None and bids:
        first = bids[0]
        bid = float(first.get("price") if isinstance(first, dict) else first)
    if ask is None and asks:
        first = asks[0]
        ask = float(first.get("price") if isinstance(first, dict) else first)
    return bid, ask


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "dict"):
        try:
            return _jsonable(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _jsonable(vars(value))
        except Exception:
            pass
    return str(value)


def response_body(response: Any) -> Dict[str, Any]:
    if response is None:
        return {}
    if isinstance(response, dict):
        return {str(k): _jsonable(v) for k, v in response.items()}
    body = getattr(response, "body", None)
    if isinstance(body, dict):
        return {str(k): _jsonable(v) for k, v in body.items()}
    if body is not None and hasattr(body, "dict"):
        return _jsonable(body.dict())
    # v20 Response often exposes named attributes
    out: Dict[str, Any] = {}
    for key in (
        "account",
        "accounts",
        "prices",
        "instruments",
        "orderCreateTransaction",
        "orderFillTransaction",
        "orderRejectTransaction",
        "relatedTransactionIDs",
        "lastTransactionID",
        "changes",
        "state",
        "candles",
        "errorCode",
        "errorMessage",
    ):
        if hasattr(response, key):
            value = getattr(response, key)
            if value is not None:
                out[key] = _jsonable(value)
    if out:
        return out
    return {"raw": str(response)}


def as_ref_row(ref: OandaInstrumentRef) -> Dict[str, Any]:
    return {
        "instrument": ref.instrument,
        "oanda_instrument": ref.oanda_instrument,
        "resolved_at": ref.resolved_at,
        "metadata": json.dumps(ref.metadata, sort_keys=True),
    }


def load_jsonl_events(path: Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
