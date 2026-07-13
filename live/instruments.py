from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, time
from typing import Any, Dict, Iterable, Optional

from .causality import _parse_ts


@dataclass(frozen=True)
class RollPolicy:
    policy_id: str
    description: str
    version: str = "v1"


@dataclass(frozen=True)
class FuturesInstrument:
    instrument: str
    point_value: float
    tick_size: float
    rth_open: str
    rth_close: str
    timezone: str
    databento_parent: str
    tradovate_map_key: str
    broker_symbol_template: str
    roll_policy: RollPolicy

    def row(self) -> Dict[str, Any]:
        out = asdict(self)
        out["roll_policy"] = asdict(self.roll_policy)
        return out


DEFAULT_ROLL_POLICY = RollPolicy(
    policy_id="front_month_manual_or_vendor_resolved",
    description="Use the active broker-routable front month resolved by the configured provider; write roll_manifest.json when a concrete contract is selected.",
)


INSTRUMENTS: Dict[str, FuturesInstrument] = {
    "MNQ": FuturesInstrument("MNQ", 2.0, 0.25, "09:30", "16:00", "America/New_York", "MNQ.FUT", "MNQ", "{root}{month_code}{year_digit}", DEFAULT_ROLL_POLICY),
    "NQ": FuturesInstrument("NQ", 20.0, 0.25, "09:30", "16:00", "America/New_York", "NQ.FUT", "NQ", "{root}{month_code}{year_digit}", DEFAULT_ROLL_POLICY),
    "MYM": FuturesInstrument("MYM", 0.50, 1.0, "09:30", "16:00", "America/New_York", "MYM.FUT", "MYM", "{root}{month_code}{year_digit}", DEFAULT_ROLL_POLICY),
    "YM": FuturesInstrument("YM", 5.0, 1.0, "09:30", "16:00", "America/New_York", "YM.FUT", "YM", "{root}{month_code}{year_digit}", DEFAULT_ROLL_POLICY),
    "ES": FuturesInstrument("ES", 50.0, 0.25, "09:30", "16:00", "America/New_York", "ES.FUT", "ES", "{root}{month_code}{year_digit}", DEFAULT_ROLL_POLICY),
    "MES": FuturesInstrument("MES", 5.0, 0.25, "09:30", "16:00", "America/New_York", "MES.FUT", "MES", "{root}{month_code}{year_digit}", DEFAULT_ROLL_POLICY),
}


def get_instrument(instrument: str, session_date: Optional[date] = None) -> FuturesInstrument:
    key = str(instrument).upper()
    if key not in INSTRUMENTS:
        raise KeyError("Unknown futures instrument: %s" % instrument)
    return INSTRUMENTS[key]


def point_value(instrument: str) -> float:
    return get_instrument(instrument).point_value


def tick_size(instrument: str) -> float:
    return get_instrument(instrument).tick_size


def rth_session(instrument: str) -> tuple[time, time, str]:
    meta = get_instrument(instrument)
    return _parse_time(meta.rth_open), _parse_time(meta.rth_close), meta.timezone


def asof_latest(
    rows: Iterable[Dict[str, Any]],
    current_bar_ts: str,
    *,
    available_at_key: str = "available_at_ts",
    match: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return the latest point-in-time row knowable at ``current_bar_ts``.

    This is the flat-file semantic twin of the future KDB+ as-of join:
    records with ``available_at > current_bar_ts`` are invisible.
    """

    current = _parse_ts(current_bar_ts)
    if current is None:
        raise ValueError("current_bar_ts is not parseable: %s" % current_bar_ts)
    best = None
    best_ts = None
    for row in rows:
        if match and any(str(row.get(k)) != str(v) for k, v in match.items()):
            continue
        available_at = _parse_ts(str(row.get(available_at_key) or ""))
        if available_at is None or available_at > current:
            continue
        if best_ts is None or available_at > best_ts:
            best = dict(row)
            best_ts = available_at
    return best


def _parse_time(value: str) -> time:
    hour, minute = [int(part) for part in value.split(":", 1)]
    return time(hour, minute)

