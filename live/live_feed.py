from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .models import Bar, utc_now_iso
from .store import FlatFileStore


TIMEFRAME_SECONDS: Dict[str, int] = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
}


@dataclass(frozen=True)
class FeedHealth:
    status: str
    raw_events: int
    completed_bars: int
    incomplete_bars: int
    duplicate_bars: int
    out_of_order_bars: int
    missing_bars: int
    unsupported_timeframes: int
    last_event_ts: str = ""
    last_completed_bar_ts: str = ""
    stale_seconds: float = 0.0
    stale: bool = False


class LiveFeedAdapter(ABC):
    @abstractmethod
    def on_raw_event(self, event: Dict[str, Any]) -> List[Bar]:
        raise NotImplementedError

    @abstractmethod
    def on_completed_bar(self, timeframe: str, bar: Bar) -> None:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> FeedHealth:
        raise NotImplementedError


class PersistedLiveFeedAdapter(LiveFeedAdapter):
    """Provider-neutral signal feed boundary.

    This adapter intentionally does not connect to a vendor websocket. It is a
    thin live-readiness layer that persists raw feed payloads, validates
    completed bars, tracks feed quality, and emits only completed bars to the
    supplied callback. Provider adapters can translate Databento/Tradovate
    messages into the simple bar payload accepted here.
    """

    def __init__(
        self,
        store: FlatFileStore,
        on_bar: Optional[Callable[[Bar], None]] = None,
        allowed_timeframes: Sequence[str] = ("1m", "5m", "15m", "1h"),
        stale_after_seconds: float = 30.0,
        clock: Callable[[], datetime] = datetime.utcnow,
    ):
        self.store = store
        self.store.ensure()
        self.on_bar = on_bar
        self.allowed_timeframes = set(allowed_timeframes)
        self.stale_after_seconds = float(stale_after_seconds)
        self.clock = clock
        self._raw_events = 0
        self._completed_bars = 0
        self._incomplete_bars = 0
        self._duplicate_bars = 0
        self._out_of_order_bars = 0
        self._missing_bars = 0
        self._unsupported_timeframes = 0
        self._seen_keys: set[Tuple[str, str, str]] = set()
        self._last_ts_by_stream: Dict[Tuple[str, str], str] = {}
        self._last_event_wallclock: Optional[datetime] = None
        self._last_event_ts = ""
        self._last_completed_bar_ts = ""

    def on_raw_event(self, event: Dict[str, Any]) -> List[Bar]:
        self._raw_events += 1
        self._last_event_wallclock = self.clock()
        self._last_event_ts = str(event.get("ts") or event.get("event_ts") or utc_now_iso())
        self.store.append_event("market_data_raw", dict(event))
        if str(event.get("type") or "bar") != "bar":
            return []
        bar = Bar.from_row(event)
        self.on_completed_bar(bar.timeframe, bar)
        return [bar] if bar.complete and bar.timeframe in self.allowed_timeframes else []

    def on_completed_bar(self, timeframe: str, bar: Bar) -> None:
        if timeframe not in self.allowed_timeframes:
            self._unsupported_timeframes += 1
            self.store.append_event(
                "market_data_quality",
                {"event": "unsupported_timeframe", "timeframe": timeframe, "bar_ts": bar.ts, "instrument": bar.instrument},
            )
            return
        if not bar.complete:
            self._incomplete_bars += 1
            self.store.append_event(
                "market_data_quality",
                {"event": "incomplete_bar_ignored", "timeframe": timeframe, "bar_ts": bar.ts, "instrument": bar.instrument},
            )
            return
        key = (bar.instrument, timeframe, bar.ts)
        if key in self._seen_keys:
            self._duplicate_bars += 1
            self.store.append_event(
                "market_data_quality",
                {"event": "duplicate_bar", "timeframe": timeframe, "bar_ts": bar.ts, "instrument": bar.instrument},
            )
            return
        self._seen_keys.add(key)

        stream_key = (bar.instrument, timeframe)
        last_ts = self._last_ts_by_stream.get(stream_key)
        if last_ts and str(bar.ts) <= str(last_ts):
            self._out_of_order_bars += 1
            self.store.append_event(
                "market_data_quality",
                {
                    "event": "out_of_order_bar",
                    "timeframe": timeframe,
                    "bar_ts": bar.ts,
                    "last_bar_ts": last_ts,
                    "instrument": bar.instrument,
                },
            )
            return
        if last_ts:
            missing = _missing_bar_count(last_ts, bar.ts, timeframe)
            if missing > 0:
                self._missing_bars += missing
                self.store.append_event(
                    "market_data_quality",
                    {
                        "event": "missing_bars",
                        "timeframe": timeframe,
                        "bar_ts": bar.ts,
                        "last_bar_ts": last_ts,
                        "missing_bars": missing,
                        "instrument": bar.instrument,
                    },
                )
        self._last_ts_by_stream[stream_key] = str(bar.ts)
        self._completed_bars += 1
        self._last_completed_bar_ts = str(bar.ts)
        self.store.append_bar(bar)
        self.store.append_event(
            "market_data_completed_bars",
            {
                "event": "completed_bar",
                "instrument": bar.instrument,
                "timeframe": bar.timeframe,
                "bar_ts": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            },
        )
        if self.on_bar is not None:
            self.on_bar(bar)

    def health(self) -> FeedHealth:
        now = self.clock()
        stale_seconds = 0.0
        stale = False
        if self._last_event_wallclock is not None:
            stale_seconds = max(0.0, (now - self._last_event_wallclock).total_seconds())
            stale = stale_seconds > self.stale_after_seconds
        status = "stale" if stale else "ok"
        if self._unsupported_timeframes or self._out_of_order_bars:
            status = "degraded"
        return FeedHealth(
            status=status,
            raw_events=self._raw_events,
            completed_bars=self._completed_bars,
            incomplete_bars=self._incomplete_bars,
            duplicate_bars=self._duplicate_bars,
            out_of_order_bars=self._out_of_order_bars,
            missing_bars=self._missing_bars,
            unsupported_timeframes=self._unsupported_timeframes,
            last_event_ts=self._last_event_ts,
            last_completed_bar_ts=self._last_completed_bar_ts,
            stale_seconds=stale_seconds,
            stale=stale,
        )


@dataclass(frozen=True)
class ParityMismatch:
    row: int
    key: str
    field: str
    left: str
    right: str


def compare_csv_for_replay_parity(left: Path, right: Path, key: str, fields: Sequence[str]) -> List[ParityMismatch]:
    """Compare live-shadow output to offline replay output.

    The first intended use is order-intent parity: compare strategy_id, side,
    quantity, order_type, limit/stop price, live_after_ts, and expiry.
    """

    left_rows = _csv_by_key(left, key)
    right_rows = _csv_by_key(right, key)
    mismatches: List[ParityMismatch] = []
    all_keys = sorted(set(left_rows) | set(right_rows))
    for idx, item_key in enumerate(all_keys, start=1):
        if item_key not in left_rows:
            mismatches.append(ParityMismatch(idx, item_key, "__row__", "missing_left", ""))
            continue
        if item_key not in right_rows:
            mismatches.append(ParityMismatch(idx, item_key, "__row__", "", "missing_right"))
            continue
        for field in fields:
            left_value = str(left_rows[item_key].get(field, ""))
            right_value = str(right_rows[item_key].get(field, ""))
            if left_value != right_value:
                mismatches.append(ParityMismatch(idx, item_key, field, left_value, right_value))
    return mismatches


def feed_health_row(health: FeedHealth) -> Dict[str, str]:
    return {key: str(value) for key, value in asdict(health).items()}


def _csv_by_key(path: Path, key: str) -> Dict[str, Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {str(row.get(key, "")): row for row in rows}


def _missing_bar_count(left_ts: str, right_ts: str, timeframe: str) -> int:
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if not seconds:
        return 0
    left = _parse_ts(left_ts)
    right = _parse_ts(right_ts)
    if left is None or right is None or right <= left:
        return 0
    intervals = int((right - left).total_seconds() // seconds)
    return max(0, intervals - 1)


def _parse_ts(value: str) -> Optional[datetime]:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
