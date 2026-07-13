from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from .models import Bar

RTH_OPEN = time(9, 30)
RTH_OPEN_WIDEN_END = time(9, 35)
RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class SpreadModel:
    """Synthetic half-spread overlay for last-sale OHLC replay.

    ``half_spread_ticks`` is applied per side: buys pay ``+half_spread``,
    sells receive ``-half_spread`` before adverse slippage ticks.
    """

    rth_half_spread_ticks: float = 0.5
    eth_half_spread_ticks: float = 1.0
    open_widen_half_spread_ticks: float = 1.0
    low_volume_threshold: float = 50.0
    low_volume_multiplier: float = 1.5
    tick_size: float = 0.25

    def half_spread_points(self, bar: Bar) -> float:
        ts = _bar_time(bar.ts)
        half_ticks = self.rth_half_spread_ticks
        if ts is None:
            return half_ticks * self.tick_size
        if ts < RTH_OPEN or ts >= RTH_CLOSE:
            half_ticks = max(half_ticks, self.eth_half_spread_ticks)
        elif RTH_OPEN <= ts < RTH_OPEN_WIDEN_END:
            half_ticks = max(half_ticks, self.open_widen_half_spread_ticks)
        volume = float(bar.volume or 0.0)
        if volume > 0 and volume < self.low_volume_threshold:
            half_ticks *= self.low_volume_multiplier
        return half_ticks * self.tick_size

    def adjust_fill_price(self, side: str, base_price: float, bar: Bar) -> float:
        half = self.half_spread_points(bar)
        if side == "buy":
            return base_price + half
        return base_price - half

    def limit_touch_ok(self, side: str, bar: Bar, limit_price: float) -> bool:
        """Conservative limit fill: price must trade through spread-adjusted level."""
        half = self.half_spread_points(bar)
        if side == "buy":
            return bar.low <= limit_price - half
        return bar.high >= limit_price + half


def _bar_time(ts: str) -> Optional[time]:
    text = str(ts)
    if "T" in text:
        body = text.split("T", 1)[1]
    else:
        body = text
    for sep in ("-", "+", "Z"):
        if sep in body:
            body = body.split(sep, 1)[0]
            break
    try:
        parts = body.split(":")
        return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return None
