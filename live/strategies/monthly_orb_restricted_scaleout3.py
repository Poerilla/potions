from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from ..models import Alert, Bar, CancelIntent, LevelUpdate, ModifyIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class MonthlyOrbRestrictedScaleout3Strategy(StrategyPlugin):
    strategy_type = "monthly_orb_restricted_scaleout3"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self._daily_bars_cache: Optional[List[Bar]] = None
        self.config = {
            "or_sessions": 3,
            "max_trades_per_month": 2,
            "batch_qty": 1,
            "tp25_frac": 0.25,
            "full_target_mult": 1.0,
            "allow_shorts": True,
            "entry_mode": "limit_retest",
            "flatten_month_end": True,
            "month_end_dates": [],
            "record_levels": False,
            "failed_break_retrace_frac": 0.25,
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
        state = self._state_for_month(_month_key(fill.ts))
        if fill.reason == "entry" and context.position_quantity != 0:
            state["active_trade_id"] = fill.trade_id
            state["active_entry"] = fill.price
            state["active_direction"] = "long" if fill.side == "buy" else "short"
            if self._entry_mode() == "boundary_stop":
                range_high = _to_float(state.get("range_high"))
                range_low = _to_float(state.get("range_low"))
                if range_high is not None and range_low is not None and range_high > range_low:
                    range_val = range_high - range_low
                    state["active_target"] = (
                        range_high + range_val * float(self.config["full_target_mult"])
                        if fill.side == "buy"
                        else range_low - range_val * float(self.config["full_target_mult"])
                    )
                    self.state = state
                    self.save_state()
                    return StrategyActions(
                        self._boundary_stop_exit_orders(fill, range_high, range_low),
                        [],
                        [],
                        [],
                        [],
                    )
        if fill.reason == "target":
            target = _to_float(state.get("active_target"))
            entry = _to_float(state.get("active_entry"))
            if target is not None and entry is not None and abs(fill.price - target) < 1e-9:
                for order in context.strategy_open_orders:
                    if order.trade_id == fill.trade_id and order.bracket_role in {"runner_stop", "stop"}:
                        self.state = state
                        self.save_state()
                        return StrategyActions(
                            [],
                            [],
                            [
                                ModifyIntent(
                                    strategy_id=self.instance.strategy_id,
                                    broker_order_id=order.broker_order_id,
                                    reason="runner_stop_to_breakeven",
                                    stop_price=entry,
                                )
                            ],
                            [],
                            [],
                        )
        if context.position_quantity == 0 and not self._has_open_entry_order(context):
            state["phase"] = "wait_breakout"
            state["active_trade_id"] = ""
            state["active_entry"] = None
            state["active_target"] = None
            state["active_direction"] = ""
        self.state = state
        self.save_state()
        return StrategyActions.empty()

    def _on_daily_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_date(bar.ts)
        key = f"{dt.year:04d}-{dt.month:02d}"
        state = self._state_for_month(key)
        bars = self._daily_bars(bar)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        if state.get("month_key") != key:
            state = self._fresh_month_state(key)

        month_bar_count = self._month_bar_count(bars, dt.year, dt.month)
        if month_bar_count <= int(self.config["or_sessions"]):
            high = _to_float(state.get("range_high"))
            low = _to_float(state.get("range_low"))
            state["range_high"] = bar.high if high is None else max(high, bar.high)
            state["range_low"] = bar.low if low is None else min(low, bar.low)
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            if (
                self._entry_mode() == "boundary_stop"
                and month_bar_count == int(self.config["or_sessions"])
                and int(state.get("trade_count", 0)) < int(self.config["max_trades_per_month"])
                and context.position_quantity == 0
                and not self._has_open_entry_order(context)
            ):
                range_high = _to_float(state.get("range_high"))
                range_low = _to_float(state.get("range_low"))
                if range_high is not None and range_low is not None and range_high > range_low:
                    orders.extend(self._boundary_stop_orders(bar.ts, range_high, range_low, state))
            self.state = state
            self.save_state()
            return StrategyActions(orders, [], [], levels, alerts)

        range_high = _to_float(state.get("range_high"))
        range_low = _to_float(state.get("range_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            self.state = state
            self.save_state()
            return StrategyActions.empty()
        range_val = range_high - range_low
        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if self._is_month_end_bar(bar.ts):
            for order in context.strategy_open_orders:
                cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, "month_end_flatten"))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "month_end_flatten", order_type="market_close"))
                alerts.append(Alert.create(self.instance.strategy_id, "info", "Monthly ORB month-end flatten requested"))
            state["phase"] = "month_end_flatten"
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, alerts)

        retrace_frac = float(self.config.get("failed_break_retrace_frac", 0.25))
        if (
            self._entry_mode() == "boundary_stop"
            and context.position_quantity != 0
            and self._failed_breakout_retrace_close(
                bar.close, range_high, range_low, range_val, context.position_quantity, retrace_frac
            )
        ):
            orders.extend(
                self._flatten_failed_breakout(context, bar.ts, cancels, reason="range_close")
            )
            alerts.append(
                Alert.create(
                    self.instance.strategy_id,
                    "info",
                    "Monthly ORB failed-breakout flatten requested (%.0f%% range retrace)" % (retrace_frac * 100),
                )
            )

        if _parse_date(bar.ts).month != int(key[-2:]):
            for order in context.strategy_open_orders:
                cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, "month_end"))

        if int(state.get("trade_count", 0)) >= int(self.config["max_trades_per_month"]):
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, alerts)

        flat = context.position_quantity == 0 and not self._has_open_entry_order(context)
        if self._entry_mode() == "boundary_stop":
            if flat and int(state.get("trade_count", 0)) < int(self.config["max_trades_per_month"]):
                orders.extend(self._boundary_stop_orders(bar.ts, range_high, range_low, state))
        elif flat and state.get("phase") in {"wait_breakout", ""}:
            prior_close = _to_float(state.get("prior_close"))
            fresh_long = bar.close > range_high and (prior_close is None or prior_close <= range_high)
            fresh_short = (
                bool(self.config.get("allow_shorts"))
                and bar.close < range_low
                and (prior_close is None or prior_close >= range_low)
            )
            if fresh_long:
                orders.extend(self._entry_ladder("long", bar.ts, range_high, range_low, range_val, state))
            elif fresh_short:
                orders.extend(self._entry_ladder("short", bar.ts, range_high, range_low, range_val, state))

        state["prior_close"] = bar.close
        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _state_for_month(self, key: str) -> Dict[str, Any]:
        if not self.state or self.state.get("month_key") != key:
            return self._fresh_month_state(key)
        return dict(self.state)

    def _fresh_month_state(self, key: str) -> Dict[str, Any]:
        return {
            "month_key": key,
            "range_high": None,
            "range_low": None,
            "prior_close": None,
            "phase": "wait_breakout",
            "trade_count": 0,
            "trade_seq": 0,
            "active_trade_id": "",
            "active_entry": None,
            "active_target": None,
            "active_direction": "",
        }

    def _entry_ladder(
        self,
        direction: str,
        ts: str,
        range_high: float,
        range_low: float,
        range_val: float,
        state: Dict[str, Any],
    ) -> List[OrderIntent]:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        state["trade_count"] = int(state.get("trade_count", 0)) + 1
        state["phase"] = "wait_fill"
        trade_id = "%s_%s_%02d" % (self.instance.strategy_id, state["month_key"].replace("-", ""), state["trade_seq"])
        qty = int(self.config["batch_qty"])
        if direction == "long":
            side = "buy"
            entry = range_high
            stop = range_low
            target = range_high + range_val * float(self.config["full_target_mult"])
            tp25 = entry + (target - entry) * float(self.config["tp25_frac"])
        else:
            side = "sell"
            entry = range_low
            stop = range_high
            target = range_low - range_val * float(self.config["full_target_mult"])
            tp25 = entry - (entry - target) * float(self.config["tp25_frac"])
        state["active_trade_id"] = trade_id
        state["active_entry"] = entry
        state["active_target"] = target
        state["active_direction"] = direction
        base = dict(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=qty,
            limit_price=entry,
            requires_verification=True,
            bracket_stop_price=stop,
            live_after_ts=ts,
            expires_after_ts=_month_expiry(ts),
        )
        return [
            OrderIntent.create(**base, reason=f"{direction}_tp25_entry", bracket_role="entry", bracket_target_price=tp25),
            OrderIntent.create(**base, reason=f"{direction}_tp_entry", bracket_role="entry", bracket_target_price=target),
            OrderIntent.create(**base, reason=f"{direction}_runner_entry", bracket_role="runner_entry"),
        ]

    def _boundary_stop_orders(
        self,
        ts: str,
        range_high: float,
        range_low: float,
        state: Dict[str, Any],
    ) -> List[OrderIntent]:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        state["trade_count"] = int(state.get("trade_count", 0)) + 1
        state["phase"] = "wait_fill"
        trade_id = "%s_%s_%02d" % (self.instance.strategy_id, state["month_key"].replace("-", ""), state["trade_seq"])
        oco = "%s_entry_oco" % trade_id
        out = [
            self._boundary_stop_parent("long", trade_id, ts, range_high, range_low, oco),
        ]
        if bool(self.config.get("allow_shorts")):
            out.append(self._boundary_stop_parent("short", trade_id, ts, range_high, range_low, oco))
        return out

    def _boundary_stop_parent(
        self,
        direction: str,
        trade_id: str,
        ts: str,
        range_high: float,
        range_low: float,
        oco: str,
    ) -> OrderIntent:
        if direction == "long":
            side = "buy"
            stop_price = range_high
        else:
            side = "sell"
            stop_price = range_low
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="stop",
            quantity=3 * int(self.config["batch_qty"]),
            stop_price=stop_price,
            reason=f"{direction}_boundary_stop_entry",
            requires_verification=True,
            bracket_role="entry",
            oco_group=oco,
            live_after_ts=ts,
            expires_after_ts=_month_expiry(ts),
        )

    def _boundary_stop_exit_orders(
        self,
        fill,
        range_high: float,
        range_low: float,
    ) -> List[OrderIntent]:
        qty = int(self.config["batch_qty"])
        range_val = range_high - range_low
        long_entry = fill.side == "buy"
        direction = "long" if long_entry else "short"
        entry = range_high if long_entry else range_low
        stop = range_low if long_entry else range_high
        target = range_high + range_val * float(self.config["full_target_mult"]) if long_entry else range_low - range_val * float(self.config["full_target_mult"])
        tp25 = entry + (target - entry) * float(self.config["tp25_frac"]) if long_entry else entry - (entry - target) * float(self.config["tp25_frac"])
        exit_side = "sell" if long_entry else "buy"
        common = dict(
            strategy_id=self.instance.strategy_id,
            trade_id=fill.trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=exit_side,
            requires_verification=False,
            reduce_only=True,
            live_after_ts=fill.ts,
        )
        return [
            OrderIntent.create(
                **common,
                order_type="stop",
                quantity=3 * qty,
                stop_price=stop,
                reason=f"{direction}_protective_stop",
                bracket_role="stop",
            ),
            OrderIntent.create(
                **common,
                order_type="limit",
                quantity=qty,
                limit_price=tp25,
                reason="target",
                bracket_role="target",
            ),
            OrderIntent.create(
                **common,
                order_type="limit",
                quantity=qty,
                limit_price=target,
                reason="target",
                bracket_role="target",
            ),
        ]

    def _close_all(self, context: StrategyContext, ts: str, reason: str, order_type: str = "market") -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if context.position_quantity > 0 else "buy",
            order_type=order_type,
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts=ts,
        )

    def _daily_bars(self, bar: Bar) -> List[Bar]:
        if self._daily_bars_cache is None:
            self._daily_bars_cache = self.store.read_bars(self.instance.instrument, "D")
        elif not self._daily_bars_cache or self._daily_bars_cache[-1].ts != bar.ts:
            self._daily_bars_cache.append(bar)
        return self._daily_bars_cache

    def _month_bar_count(self, bars: List[Bar], year: int, month: int) -> int:
        return len([b for b in bars if _parse_date(b.ts).year == year and _parse_date(b.ts).month == month])

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        high = _to_float(state.get("range_high"))
        low = _to_float(state.get("range_low"))
        out: List[LevelUpdate] = []
        if high is not None:
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, "monthly_orb_high", high, ts))
        if low is not None:
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, "monthly_orb_low", low, ts))
        return out

    def _has_open_entry_order(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _has_open_reduce_order(self, context: StrategyContext) -> bool:
        return any(order.reduce_only for order in context.strategy_open_orders)

    def _has_pending_close_order(self, context: StrategyContext) -> bool:
        return any(
            order.reduce_only and order.bracket_role == "close"
            for order in context.strategy_open_orders
        )

    def _failed_breakout_retrace_close(
        self,
        close: float,
        range_high: float,
        range_low: float,
        range_val: float,
        position_quantity: int,
        retrace_frac: float,
    ) -> bool:
        """True when close has retraced more than retrace_frac of the OR width back inside."""
        frac = max(0.0, min(float(retrace_frac), 1.0))
        if position_quantity > 0:
            return close < range_high - frac * range_val
        if position_quantity < 0:
            return close > range_low + frac * range_val
        return False

    def _flatten_failed_breakout(
        self,
        context: StrategyContext,
        ts: str,
        cancels: List[CancelIntent],
        reason: str,
    ) -> List[OrderIntent]:
        for order in context.strategy_open_orders:
            cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        if context.position_quantity == 0 or self._has_pending_close_order(context):
            return []
        return [self._close_all(context, ts, reason, order_type="market_close")]

    def _entry_mode(self) -> str:
        return str(self.config.get("entry_mode") or "limit_retest")

    def _is_month_end_bar(self, ts: str) -> bool:
        if not bool(self.config.get("flatten_month_end", True)):
            return False
        day = str(ts)[:10]
        month_end_dates = self.config.get("month_end_dates") or []
        return day in {str(value)[:10] for value in month_end_dates}


def _parse_date(ts: str) -> date:
    text = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text[:10]).date()


def _month_key(ts: str) -> str:
    d = _parse_date(ts)
    return f"{d.year:04d}-{d.month:02d}"


def _month_expiry(ts: str) -> str:
    d = _parse_date(ts)
    if d.month == 12:
        return f"{d.year:04d}-12-31T23:59:59"
    return f"{d.year:04d}-{d.month + 1:02d}-01T00:00:00"


def _to_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    return float(value)
