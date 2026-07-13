from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from ..models import Alert, Bar, FeatureSnapshot, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot


@dataclass(frozen=True)
class TrendPoint:
    ts: str
    stop: float
    bullish: bool


class AtrSupertrendDcaStrategy(StrategyPlugin):
    strategy_type = "atr_supertrend_dca"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self._daily_bars_cache: Optional[List[Bar]] = None
        self.config = {
            "signal_tf": "weekly",
            "atr_len": 14,
            "atr_mult": 3.0,
            "initial_qty": 3,
            "add_qty": 1,
            "max_contracts": instance.max_contracts,
            "add_interval": 2,
            "schedule": "fixed",
            "ladder": [1, 1, 2, 2, 2, 1],
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
            "record_levels": False,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "D" or not bar.complete:
            return StrategyActions.empty()
        return self._on_daily_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        if fill.side == "buy" and context.position_quantity > 0 and not state.get("entry_guard"):
            state["entry_guard"] = fill.price
            state["entry_day"] = _day_key(fill.ts)
            state["active_trade_id"] = fill.trade_id
        if context.position_quantity == 0 and fill.side == "sell" and not state.get("guard_paused"):
            state["entry_guard"] = None
            state["entry_day"] = ""
            state["active_trade_id"] = ""
            state["eligible_add_count"] = 0
            state["scale_event_count"] = 0
        self.state = state
        self.save_state()
        return StrategyActions.empty()

    def _on_daily_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        daily_bars = self._daily_bars(bar)
        if len(daily_bars) < int(self.config["atr_len"]) + 3:
            return StrategyActions.empty()

        state = self._state()
        daily_points = _supertrend(daily_bars, int(self.config["atr_len"]), float(self.config["atr_mult"]))
        weekly_points = _supertrend(
            _completed_weekly_bars(daily_bars, _parse_date(bar.ts)),
            int(self.config["atr_len"]),
            float(self.config["atr_mult"]),
        )
        if len(daily_points) < 2:
            return StrategyActions.empty()

        daily_now = daily_points[-1]
        daily_prev = daily_points[-2]
        weekly_now = weekly_points[-1] if weekly_points else None
        weekly_prev = weekly_points[-2] if len(weekly_points) >= 2 else None

        signal_tf = str(self.config["signal_tf"]).lower()
        sig_now = weekly_now if signal_tf == "weekly" else daily_now
        sig_prev = weekly_prev if signal_tf == "weekly" else daily_prev
        if sig_now is None or sig_prev is None:
            return StrategyActions.empty()

        sig_up = sig_now.bullish
        sig_down = not sig_now.bullish
        primary_flip_up = sig_now.bullish and not sig_prev.bullish
        primary_flip_down = (not sig_now.bullish) and sig_prev.bullish
        weekly_down = weekly_now is not None and not weekly_now.bullish
        weekly_allows_long = signal_tf == "weekly" or not bool(self.config["daily_use_weekly_flat"]) or not weekly_down

        orders: List[OrderIntent] = []
        levels: List[LevelUpdate] = []
        causal_features: List[FeatureSnapshot] = self._signal_features(
            bar,
            daily_now,
            daily_prev,
            weekly_now,
            weekly_prev,
            sig_now,
            sig_prev,
            state,
            weekly_allows_long,
        )
        if bool(self.config.get("record_levels")):
            levels.append(
                LevelUpdate(self.instance.strategy_id, self.instance.instrument, "daily_supertrend_stop", daily_now.stop, bar.ts)
            )
            if weekly_now is not None:
                levels.append(
                    LevelUpdate(
                        self.instance.strategy_id,
                        self.instance.instrument,
                        "weekly_supertrend_stop",
                        weekly_now.stop,
                        bar.ts,
                    )
                )

        flat = context.position_quantity == 0 and not self._has_open_entry_order(context)
        long_open = context.position_quantity > 0
        has_reduce_order = self._has_open_reduce_order(context)
        day_key = _day_key(bar.ts)

        guard = _to_float(state.get("entry_guard"))
        entry_day = str(state.get("entry_day") or "")
        pause_day = str(state.get("guard_pause_day") or "")
        guard_after_entry = not entry_day or day_key > entry_day
        guard_after_pause = not pause_day or day_key > pause_day

        if flat and weekly_allows_long and not state.get("guard_paused") and primary_flip_up:
            trade_id = self._new_trade_id(state, bar.ts)
            qty = min(self._initial_qty(), self.instance.max_contracts)
            orders.append(self._market_entry(trade_id, qty, bar.ts, "primary_bull_flip"))
            state["entry_guard"] = None
            state["entry_day"] = ""
            state["eligible_add_count"] = 0
            state["scale_event_count"] = 1

        if (
            flat
            and weekly_allows_long
            and state.get("guard_paused")
            and bool(self.config["use_entry_guard"])
            and guard is not None
            and sig_up
            and guard_after_pause
            and bar.close > guard
        ):
            trade_id = self._new_trade_id(state, bar.ts)
            qty = min(self._initial_qty(), self.instance.max_contracts)
            orders.append(self._market_entry(trade_id, qty, bar.ts, "entry_guard_reclaim"))
            state["guard_paused"] = False
            state["guard_pause_day"] = ""
            state["eligible_add_count"] = 0
            state["scale_event_count"] = 1

        if long_open and not has_reduce_order:
            weekly_flat_exit = signal_tf == "daily" and bool(self.config["daily_use_weekly_flat"]) and weekly_down
            primary_bear_exit = primary_flip_down
            guard_exit = (
                bool(self.config["use_entry_guard"])
                and sig_up
                and guard is not None
                and guard_after_entry
                and bar.close < guard
            )
            if weekly_flat_exit:
                orders.append(self._close_all(context, bar.ts, "weekly_bearish"))
                self._clear_active_state(state)
            elif primary_bear_exit:
                orders.append(self._close_all(context, bar.ts, "primary_bearish"))
                self._clear_active_state(state)
            elif guard_exit:
                orders.append(self._close_all(context, bar.ts, "initial_entry_guard"))
                state["guard_paused"] = True
                state["guard_pause_day"] = day_key

        if (
            long_open
            and not has_reduce_order
            and self._is_add_bar(bar)
            and sig_up
            and weekly_allows_long
            and bar.close > sig_now.stop
            and (not bool(self.config["use_entry_guard"]) or guard is None or bar.close > guard)
        ):
            next_count = int(state.get("eligible_add_count", 0)) + 1
            state["eligible_add_count"] = next_count
            if next_count % int(self.config["add_interval"]) == 0 and context.position_quantity < self.instance.max_contracts:
                qty = min(self._next_add_qty(state), self.instance.max_contracts - context.position_quantity)
                if qty > 0:
                    trade_id = str(state.get("active_trade_id") or self._new_trade_id(state, bar.ts))
                    orders.append(self._market_entry(trade_id, qty, bar.ts, "friday_add"))
                    state["scale_event_count"] = int(state.get("scale_event_count", 0)) + 1

        if flat and sig_down:
            self._clear_active_state(state)
            state["guard_paused"] = False
            state["guard_pause_day"] = ""

        state["last_daily_bar"] = bar.ts
        self.state = state
        self.save_state()
        return StrategyActions(
            orders,
            [],
            [],
            levels,
            [Alert.create(self.instance.strategy_id, "order_submitted", "ATR Supertrend intent created") for _ in orders],
            causal_features,
        )

    def _signal_features(
        self,
        bar: Bar,
        daily_now: TrendPoint,
        daily_prev: TrendPoint,
        weekly_now: Optional[TrendPoint],
        weekly_prev: Optional[TrendPoint],
        sig_now: TrendPoint,
        sig_prev: TrendPoint,
        state: Dict[str, Any],
        weekly_allows_long: bool,
    ) -> List[FeatureSnapshot]:
        signal_tf = str(self.config["signal_tf"]).lower()
        guard = _to_float(state.get("entry_guard"))
        primary_flip_up = sig_now.bullish and not sig_prev.bullish
        primary_flip_down = (not sig_now.bullish) and sig_prev.bullish
        return [
            feature_snapshot(
                self.instance,
                "atr_supertrend_signal",
                bar.ts,
                event_ts=sig_now.ts,
                available_at_ts=bar.ts,
                source="%s_supertrend_completed_bars" % signal_tf,
                value_ref="bull" if sig_now.bullish else "bear",
                metadata={
                    "signal_tf": signal_tf,
                    "signal_stop": sig_now.stop,
                    "signal_prev_stop": sig_prev.stop,
                    "primary_flip_up": primary_flip_up,
                    "primary_flip_down": primary_flip_down,
                    "daily_stop": daily_now.stop,
                    "daily_bullish": daily_now.bullish,
                    "daily_prev_stop": daily_prev.stop,
                    "daily_prev_bullish": daily_prev.bullish,
                    "weekly_stop": weekly_now.stop if weekly_now else None,
                    "weekly_bullish": weekly_now.bullish if weekly_now else None,
                    "weekly_prev_stop": weekly_prev.stop if weekly_prev else None,
                    "weekly_prev_bullish": weekly_prev.bullish if weekly_prev else None,
                    "weekly_allows_long": weekly_allows_long,
                    "atr_len": self.config.get("atr_len"),
                    "atr_mult": self.config.get("atr_mult"),
                },
            ),
            feature_snapshot(
                self.instance,
                "atr_entry_guard",
                bar.ts,
                event_ts=str(state.get("entry_day") or bar.ts),
                available_at_ts=bar.ts,
                source="atr_supertrend_dca.entry_guard_state",
                value_ref=guard if guard is not None else "",
                metadata={
                    "use_entry_guard": self.config.get("use_entry_guard"),
                    "guard_paused": state.get("guard_paused"),
                    "guard_pause_day": state.get("guard_pause_day"),
                    "entry_day": state.get("entry_day"),
                    "entry_guard": guard,
                    "bar_close": bar.close,
                },
            ),
        ]

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("trade_seq", 0)
        state.setdefault("eligible_add_count", 0)
        state.setdefault("scale_event_count", 0)
        state.setdefault("guard_paused", False)
        state.setdefault("guard_pause_day", "")
        state.setdefault("entry_guard", None)
        state.setdefault("entry_day", "")
        state.setdefault("active_trade_id", "")
        return state

    def _initial_qty(self) -> int:
        if str(self.config.get("schedule", "")).lower() == "ladder112221":
            ladder = list(self.config.get("ladder") or [1, 1, 2, 2, 2, 1])
            return int(ladder[0])
        return int(self.config["initial_qty"])

    def _next_add_qty(self, state: Dict[str, Any]) -> int:
        if str(self.config.get("schedule", "")).lower() == "ladder112221":
            ladder = list(self.config.get("ladder") or [1, 1, 2, 2, 2, 1])
            idx = int(state.get("scale_event_count", 0))
            if idx < len(ladder):
                return int(ladder[idx])
        return int(self.config["add_qty"])

    def _is_add_bar(self, bar: Bar) -> bool:
        if not bool(self.config["add_on_friday_close"]):
            return False
        return _parse_date(bar.ts).weekday() == 4

    def _new_trade_id(self, state: Dict[str, Any], ts: str) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        trade_id = "%s_%s_%03d" % (self.instance.strategy_id, _day_key(ts).replace("-", ""), state["trade_seq"])
        state["active_trade_id"] = trade_id
        return trade_id

    def _market_entry(self, trade_id: str, qty: int, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy",
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
        )

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if context.position_quantity > 0 else "buy",
            order_type="market",
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts=ts,
        )

    def _has_open_entry_order(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _has_open_reduce_order(self, context: StrategyContext) -> bool:
        return any(order.reduce_only for order in context.strategy_open_orders)

    def _clear_active_state(self, state: Dict[str, Any]) -> None:
        state["entry_guard"] = None
        state["entry_day"] = ""
        state["active_trade_id"] = ""
        state["eligible_add_count"] = 0
        state["scale_event_count"] = 0

    def _daily_bars(self, bar: Bar) -> List[Bar]:
        if self._daily_bars_cache is None:
            self._daily_bars_cache = self.store.read_bars(self.instance.instrument, "D")
        elif not self._daily_bars_cache or self._daily_bars_cache[-1].ts != bar.ts:
            self._daily_bars_cache.append(bar)
        return self._daily_bars_cache


def _supertrend(bars: List[Bar], atr_len: int, atr_mult: float) -> List[TrendPoint]:
    if len(bars) < atr_len + 1:
        return []
    trs: List[float] = []
    for idx, bar in enumerate(bars):
        if idx == 0:
            trs.append(bar.high - bar.low)
        else:
            prev_close = bars[idx - 1].close
            trs.append(max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close)))
    atrs = _rma(trs, atr_len)
    points: List[TrendPoint] = []
    final_upper: Optional[float] = None
    final_lower: Optional[float] = None
    bullish = True
    for idx, bar in enumerate(bars):
        atr = atrs[idx]
        if atr is None:
            continue
        hl2 = (bar.high + bar.low) / 2.0
        basic_upper = hl2 + atr_mult * atr
        basic_lower = hl2 - atr_mult * atr
        if final_upper is None or final_lower is None:
            final_upper = basic_upper
            final_lower = basic_lower
            bullish = bar.close >= hl2
        else:
            prev_upper = final_upper
            prev_lower = final_lower
            prev_close = bars[idx - 1].close
            final_upper = basic_upper if basic_upper < prev_upper or prev_close > prev_upper else prev_upper
            final_lower = basic_lower if basic_lower > prev_lower or prev_close < prev_lower else prev_lower
            if bullish and bar.close < final_lower:
                bullish = False
            elif (not bullish) and bar.close > final_upper:
                bullish = True
        stop = final_lower if bullish else final_upper
        points.append(TrendPoint(ts=bar.ts, stop=stop, bullish=bullish))
    return points


def _rma(values: List[float], length: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < length:
        return out
    seed = sum(values[:length]) / float(length)
    out[length - 1] = seed
    prev = seed
    for idx in range(length, len(values)):
        prev = (prev * (length - 1) + values[idx]) / float(length)
        out[idx] = prev
    return out


def _completed_weekly_bars(daily_bars: List[Bar], current_day: date) -> List[Bar]:
    groups: Dict[tuple[int, int], List[Bar]] = {}
    for bar in daily_bars:
        d = _parse_date(bar.ts)
        if d > current_day:
            continue
        iso = d.isocalendar()
        groups.setdefault((iso[0], iso[1]), []).append(bar)
    out: List[Bar] = []
    for key in sorted(groups.keys()):
        group = sorted(groups[key], key=lambda b: b.ts)
        last_day = _parse_date(group[-1].ts)
        if key == current_day.isocalendar()[:2] and current_day.weekday() < 4:
            continue
        if last_day > current_day:
            continue
        out.append(
            Bar(
                instrument=group[-1].instrument,
                timeframe="W",
                ts=group[-1].ts,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(b.volume for b in group),
                complete=True,
                source="daily_aggregate",
            )
        )
    return out


def _parse_date(ts: str) -> date:
    text = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text[:10]).date()


def _day_key(ts: str) -> str:
    return _parse_date(ts).isoformat()


def _to_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    return float(value)
