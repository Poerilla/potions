"""Weekly/daily delivery scale-in helpers for Yearly ORB.

Mirrors ``scripts/yearly_orb_delivery_scalein_study.py`` swing/signal rules so the
StrategyPlugin can arm the same add-on intents through PaperBroker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DeliverySwing:
    kind: str
    value: float
    pivot_idx: int
    confirm_idx: int
    pivot_high: float
    pivot_low: float


SwingKey = Tuple[str, int, int, float]


def swing_key(swing: DeliverySwing) -> SwingKey:
    return (swing.kind, int(swing.pivot_idx), int(swing.confirm_idx), round(float(swing.value), 6))


def encode_swing_key(key: SwingKey) -> str:
    return "%s|%d|%d|%.6f" % (key[0], key[1], key[2], key[3])


def decode_swing_key(text: str) -> SwingKey:
    kind, pivot, confirm, value = text.split("|", 3)
    return (kind, int(pivot), int(confirm), float(value))


def _parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text[:10])


def _week_end_friday(ts: str) -> str:
    dt = _parse_ts(ts)
    delta = (4 - dt.weekday()) % 7
    return (dt + timedelta(days=delta)).date().isoformat()


def build_daily_swings(bars: Sequence[Dict[str, Any]]) -> List[DeliverySwing]:
    swings: List[DeliverySwing] = []
    if len(bars) < 3:
        return swings
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    for i in range(1, len(bars) - 1):
        confirm_idx = i + 1
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            swings.append(
                DeliverySwing("low", lows[i], i, confirm_idx, highs[i], lows[i])
            )
        if highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            swings.append(
                DeliverySwing("high", highs[i], i, confirm_idx, highs[i], lows[i])
            )
    return swings


def build_weekly_swings_on_daily(bars: Sequence[Dict[str, Any]]) -> List[DeliverySwing]:
    """Confirmed weekly pivots expressed in daily-row coordinates."""
    if not bars:
        return []
    weeks: Dict[str, List[int]] = {}
    order: List[str] = []
    for idx, bar in enumerate(bars):
        key = _week_end_friday(str(bar["ts"]))
        if key not in weeks:
            weeks[key] = []
            order.append(key)
        weeks[key].append(idx)

    weekly_rows: List[Dict[str, Any]] = []
    for key in order:
        idxs = weeks[key]
        high_idx = max(idxs, key=lambda i: float(bars[i]["high"]))
        low_idx = min(idxs, key=lambda i: float(bars[i]["low"]))
        weekly_rows.append(
            {
                "end_idx": max(idxs),
                "high": float(bars[high_idx]["high"]),
                "low": float(bars[low_idx]["low"]),
                "high_idx": high_idx,
                "low_idx": low_idx,
            }
        )

    swings: List[DeliverySwing] = []
    if len(weekly_rows) < 3:
        return swings
    highs = [float(r["high"]) for r in weekly_rows]
    lows = [float(r["low"]) for r in weekly_rows]
    for i in range(1, len(weekly_rows) - 1):
        confirm_idx = int(weekly_rows[i + 1]["end_idx"])
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            low_idx = int(weekly_rows[i]["low_idx"])
            swings.append(
                DeliverySwing(
                    "low",
                    lows[i],
                    low_idx,
                    confirm_idx,
                    float(bars[low_idx]["high"]),
                    float(bars[low_idx]["low"]),
                )
            )
        if highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            high_idx = int(weekly_rows[i]["high_idx"])
            swings.append(
                DeliverySwing(
                    "high",
                    highs[i],
                    high_idx,
                    confirm_idx,
                    float(bars[high_idx]["high"]),
                    float(bars[high_idx]["low"]),
                )
            )
    return swings


def previous_opposite_swing(
    swings: Sequence[DeliverySwing],
    direction: str,
    signal_swing: DeliverySwing,
    min_idx: int,
) -> Optional[DeliverySwing]:
    needed = "low" if direction == "long" else "high"
    prior = [
        swing
        for swing in swings
        if swing.kind == needed
        and swing.pivot_idx < signal_swing.pivot_idx
        and swing.pivot_idx >= min_idx
        and swing.confirm_idx < signal_swing.confirm_idx
    ]
    return prior[-1] if prior else None


def leg_stop(
    bars: Sequence[Dict[str, Any]],
    swings: Sequence[DeliverySwing],
    direction: str,
    signal_swing: DeliverySwing,
    min_idx: int,
) -> Optional[float]:
    prior = previous_opposite_swing(swings, direction, signal_swing, min_idx)
    start_idx = prior.pivot_idx if prior is not None else max(min_idx, signal_swing.pivot_idx - 5)
    stop_slice = range(start_idx, signal_swing.pivot_idx + 1)
    if not stop_slice:
        return None
    if direction == "long":
        stop_idx = min(stop_slice, key=lambda i: float(bars[i]["low"]))
        return float(bars[stop_idx]["low"])
    stop_idx = max(stop_slice, key=lambda i: float(bars[i]["high"]))
    return float(bars[stop_idx]["high"])


def find_delivery_signal(
    bars: Sequence[Dict[str, Any]],
    swings: Sequence[DeliverySwing],
    idx: int,
    direction: str,
    range_high: float,
    range_low: float,
    min_confirm_idx: int,
    used: set[SwingKey],
) -> Optional[DeliverySwing]:
    close = float(bars[idx]["close"])
    candidates: List[DeliverySwing] = []
    for swing in swings:
        key = swing_key(swing)
        if key in used:
            continue
        if swing.confirm_idx >= idx or swing.confirm_idx < min_confirm_idx or swing.pivot_idx < min_confirm_idx:
            continue
        if direction == "long":
            if swing.kind == "high" and swing.value > range_high and close > swing.value:
                candidates.append(swing)
        else:
            if swing.kind == "low" and swing.value < range_low and close < swing.value:
                candidates.append(swing)
    if not candidates:
        return None
    if direction == "long":
        return max(candidates, key=lambda swing: (swing.value, swing.confirm_idx))
    return min(candidates, key=lambda swing: (swing.value, -swing.confirm_idx))


def make_delivery_levels(
    bars: Sequence[Dict[str, Any]],
    swings: Sequence[DeliverySwing],
    idx: int,
    direction: str,
    signal_swing: DeliverySwing,
    min_idx: int,
    target_R: float,
) -> Optional[Tuple[float, float, float, SwingKey]]:
    entry = float(bars[idx]["close"])
    stop = leg_stop(bars, swings, direction, signal_swing, min_idx)
    if stop is None:
        return None
    if direction == "long":
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + risk * target_R
    else:
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - risk * target_R
    return entry, stop, target, swing_key(signal_swing)
