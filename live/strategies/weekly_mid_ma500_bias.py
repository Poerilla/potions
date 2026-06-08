from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from ..models import Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions
from .base import StrategyContext, StrategyPlugin


class WeeklyMidMa500BiasStrategy(StrategyPlugin):
    """Previous-week 50% retest with hourly close + 15m MA500 bias.

    The plugin consumes 15-minute bars. The MA500 is a rolling average of those
    15-minute closes. Bias updates only on completed hourly closes.
    """

    strategy_type = "weekly_mid_ma500_bias"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "ma_window": 500,
            "entry_qty": 1,
            "max_trades_per_week": 6,
            "risk_pts": 50.0,
            "target_pts": 300.0,
            "record_levels": False,
            "stop_after_weekly_win": False,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "15m" or not bar.complete:
            return StrategyActions.empty()
        state = self._state()
        ts = _parse_ts(bar.ts)
        week_start = _week_start(ts)
        state_changed = False
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []

        if state.get("week_start") and state.get("week_start") != week_start:
            prev = state.get("current_week_ohlc") or {}
            if prev:
                state["prev_week_ohlc"] = prev
            state["current_week_ohlc"] = {}
            state["week_start"] = week_start
            state["trades_this_week"] = 0
            state["weekly_has_win"] = False
            state["bias_side"] = ""
            state["pending_entry_trade_id"] = ""
            state_changed = True
            cancels.extend(self._cancel_entry_orders(context, "new_week"))
            if context.position_quantity != 0:
                orders.append(self._close_order(context, "week_roll_close", bar.ts))
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], levels, [])
        elif not state.get("week_start"):
            state["week_start"] = week_start
            state["current_week_ohlc"] = {}
            state.setdefault("prev_week_ohlc", {})
            state["trades_this_week"] = 0
            state["weekly_has_win"] = False
            state["bias_side"] = ""
            state_changed = True

        state["current_week_ohlc"] = self._update_ohlc(state.get("current_week_ohlc") or {}, bar)
        ma = self._update_ma(state, bar.close)
        state_changed = True

        prev = state.get("prev_week_ohlc") or {}
        if not prev or ma is None:
            if state_changed:
                self.state = state
                self.save_state()
            return StrategyActions(orders, cancels, [], levels, [])

        midpoint = float(prev["low"]) + 0.5 * (float(prev["high"]) - float(prev["low"]))
        if bool(self.config.get("record_levels")):
            levels.extend(
                [
                    LevelUpdate(self.instance.strategy_id, self.instance.instrument, "prev_week_high", float(prev["high"]), bar.ts),
                    LevelUpdate(self.instance.strategy_id, self.instance.instrument, "prev_week_low", float(prev["low"]), bar.ts),
                    LevelUpdate(self.instance.strategy_id, self.instance.instrument, "prev_week_mid", midpoint, bar.ts),
                    LevelUpdate(self.instance.strategy_id, self.instance.instrument, "ma500_15m", ma, bar.ts),
                ]
            )

        if context.position_quantity != 0:
            cancels.extend(self._cancel_entry_orders(context, "in_position"))
            if state.get("pending_entry_trade_id"):
                state["pending_entry_trade_id"] = ""
                state_changed = True
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, [])

        if state.get("active_trade_id"):
            state["active_trade_id"] = ""
            state_changed = True

        if not _is_hourly_close(ts):
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, [])

        side = ""
        if bar.close > midpoint and ma > midpoint:
            side = "buy"
        elif bar.close < midpoint and ma < midpoint:
            side = "sell"

        if (
            not side
            or int(state.get("trades_this_week") or 0) >= int(self.config["max_trades_per_week"])
            or (bool(self.config.get("stop_after_weekly_win")) and bool(state.get("weekly_has_win")))
        ):
            cancels.extend(self._cancel_entry_orders(context, "bias_off_or_max_trades"))
            state["bias_side"] = ""
            state["pending_entry_trade_id"] = ""
            self.state = state
            self.save_state()
            return StrategyActions([], cancels, [], levels, [])

        state["bias_side"] = side
        desired = self._desired_order(side, midpoint, state, bar.ts)
        existing = self._open_entry_orders(context)
        if existing:
            same = len(existing) == 1 and existing[0].side == side and existing[0].limit_price is not None and abs(existing[0].limit_price - midpoint) <= 1e-9
            if same:
                state["pending_entry_trade_id"] = existing[0].trade_id
                self.state = state
                self.save_state()
                return StrategyActions([], [], [], levels, [])
            cancels.extend(self._cancel_entry_orders(context, "refresh_bias_entry"))

        orders.append(desired)
        state["pending_entry_trade_id"] = desired.trade_id
        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], levels, [])

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        if fill.reason == "entry":
            state["active_trade_id"] = fill.trade_id
            state["pending_entry_trade_id"] = ""
            state["active_entry_price"] = float(fill.price)
            state["active_side"] = "long" if fill.side == "buy" else "short"
            state["trades_this_week"] = int(state.get("trades_this_week") or 0) + int(fill.quantity)
        elif fill.reason in {"target", "stop", "protective_stop", "close"}:
            if self._is_winning_exit(fill, state):
                state["weekly_has_win"] = True
            if context.position_quantity == 0:
                state["active_trade_id"] = ""
                state["pending_entry_trade_id"] = ""
                state["active_entry_price"] = 0.0
                state["active_side"] = ""
        self.state = state
        self.save_state()
        return StrategyActions.empty()

    def _is_winning_exit(self, fill, state: Dict[str, Any]) -> bool:
        if fill.reason == "target":
            return True
        if fill.reason in {"stop", "protective_stop"}:
            return False
        entry = float(state.get("active_entry_price") or 0.0)
        side = str(state.get("active_side") or "")
        if not entry or not side:
            return False
        if side == "long":
            return float(fill.price) > entry
        if side == "short":
            return float(fill.price) < entry
        return False

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("closes", [])
        state.setdefault("weekly_has_win", False)
        return state

    def _update_ma(self, state: Dict[str, Any], close: float) -> Optional[float]:
        window = int(self.config["ma_window"])
        closes = [float(x) for x in state.get("closes", [])]
        closes.append(float(close))
        if len(closes) > window:
            closes = closes[-window:]
        state["closes"] = closes
        if len(closes) < window:
            return None
        return sum(closes) / float(window)

    def _update_ohlc(self, ohlc: Dict[str, Any], bar: Bar) -> Dict[str, float]:
        if not ohlc:
            return {"open": float(bar.open), "high": float(bar.high), "low": float(bar.low), "close": float(bar.close)}
        return {
            "open": float(ohlc["open"]),
            "high": max(float(ohlc["high"]), float(bar.high)),
            "low": min(float(ohlc["low"]), float(bar.low)),
            "close": float(bar.close),
        }

    def _desired_order(self, side: str, midpoint: float, state: Dict[str, Any], ts: str) -> OrderIntent:
        trade_id = state.get("pending_entry_trade_id") or self._next_trade_id(state)
        risk = float(self.config["risk_pts"])
        target = float(self.config["target_pts"])
        stop = midpoint - risk if side == "buy" else midpoint + risk
        target_px = midpoint + target if side == "buy" else midpoint - target
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=int(self.config["entry_qty"]),
            limit_price=midpoint,
            reason="entry",
            requires_verification=False,
            bracket_role="entry",
            bracket_stop_price=stop,
            bracket_target_price=target_px,
            live_after_ts=ts,
        )

    def _close_order(self, context: StrategyContext, reason: str, ts: str) -> OrderIntent:
        qty = abs(context.position_quantity)
        side = "sell" if context.position_quantity > 0 else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=self.state.get("active_trade_id") or self.state.get("pending_entry_trade_id") or "week_close",
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts=ts,
        )

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        n = int(state.get("trade_seq") or 0) + 1
        state["trade_seq"] = n
        return "%s-WMID-%05d" % (self.instance.strategy_id, n)

    def _open_entry_orders(self, context: StrategyContext):
        return [order for order in context.strategy_open_orders if not order.reduce_only and (order.bracket_role or "") == "entry"]

    def _cancel_entry_orders(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [CancelIntent(self.instance.strategy_id, order.broker_order_id, reason) for order in self._open_entry_orders(context)]


def _parse_ts(ts: str) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    if out.tzinfo is None:
        out = out.tz_localize("America/New_York")
    return out


def _week_start(ts: pd.Timestamp) -> str:
    return (ts.normalize() - pd.Timedelta(days=ts.weekday())).date().isoformat()


def _is_hourly_close(ts: pd.Timestamp) -> bool:
    return ts.minute == 0
