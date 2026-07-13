from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models import (
    Alert,
    Bar,
    CancelIntent,
    FeatureSnapshot,
    LevelUpdate,
    ModifyIntent,
    OrderIntent,
    StrategyActions,
    new_id,
)
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot


class YearlyOrbScaleout3Strategy(StrategyPlugin):
    strategy_type = "yearly_orb_scaleout3"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "or_start_month": 1,
            "or_end_month": 3,
            "trade_start_month": 4,
            "trade_end_month": 12,
            "batch_qty": 1,
            "tp25_qty": None,   # default: batch_qty
            "tp_qty": None,     # default: batch_qty
            "runner_qty": None, # default: batch_qty
            "tp25_frac": 0.25,
            "tp_full_mult": 1.0,
            "require_fresh_break": True,
            "range_close_inside_frac": None,
            "entry_mode": "limit_retest",  # limit_retest | oco_stop
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def _unit_quantities(self) -> tuple[int, int, int]:
        """Return ``(tp25_qty, tp_qty, runner_qty)``.

        Per-unit knobs (``tp25_qty``, ``tp_qty``, ``runner_qty``) override the
        legacy ``batch_qty``-only behaviour. Missing knobs fall back to
        ``batch_qty`` so existing configs are unchanged.
        """

        default = int(self.config["batch_qty"])
        tp25 = int(self.config.get("tp25_qty") or default)
        tp = int(self.config.get("tp_qty") or default)
        runner = int(self.config.get("runner_qty") or default)
        return tp25, tp, runner

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "D" or not bar.complete:
            return StrategyActions.empty()
        return self._on_completed_daily_bar(bar, context)

    def on_daily_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        return self.on_bar_close(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state_for_year(_parse_ts(fill.ts).year)
        orders: List[OrderIntent] = []
        yor_high = _to_float(state.get("yor_high"))
        yor_low = _to_float(state.get("yor_low"))
        if (
            self._entry_mode() == "oco_stop"
            and fill.reason == "entry"
            and context.position_quantity != 0
            and yor_high is not None
            and yor_low is not None
            and yor_high > yor_low
        ):
            if not self._has_open_reduce_order_for_trade(context, fill.trade_id):
                stop = self._entry_swing_stop(fill.side, state)
                if stop is not None:
                    orders.extend(self._oco_exit_orders(fill, yor_high, yor_low, stop))

        if fill.reason in {"entry", "runner_entry"} and context.position_quantity != 0:
            state["active_trade_id"] = fill.trade_id
            state["active_entry"] = fill.price
            state["active_direction"] = "long" if fill.side == "buy" else "short"
            if yor_high is not None and yor_low is not None and yor_high > yor_low:
                rng = yor_high - yor_low
                if fill.side == "buy":
                    state["active_tp"] = yor_high + rng * float(self.config["tp_full_mult"])
                else:
                    state["active_tp"] = yor_low - rng * float(self.config["tp_full_mult"])
            state["full_tp_seen"] = "false"

        if context.position_quantity == 0:
            state["active_trade_id"] = ""
            state["active_entry"] = None
            state["active_tp"] = None
            state["active_direction"] = ""
            state["full_tp_seen"] = "false"

        self.state = state
        self.save_state()
        return StrategyActions(orders, [], [], [], [])

    def _on_completed_daily_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_ts(bar.ts)
        year = dt.year
        month = dt.month
        state = self._state_for_year(year)
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []
        causal_features: List[FeatureSnapshot] = []

        if state.get("new_year_reset_needed"):
            if context.position_quantity != 0:
                orders.append(self._close_position_intent(context, "year_change"))
            for open_order in context.strategy_open_orders:
                cancels.append(
                    CancelIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=open_order.broker_order_id,
                        reason="year_change_reset",
                    )
                )
            state["new_year_reset_needed"] = False

        yor_high = _to_float(state.get("yor_high"))
        yor_low = _to_float(state.get("yor_low"))
        range_ready = yor_high is not None and yor_low is not None and yor_high > yor_low
        if range_ready:
            causal_features.append(self._range_feature(bar.ts, state, yor_high, yor_low))
        range_close_exit = bool(
            range_ready and self._range_close_exit(bar.close, context.position_quantity, state, yor_high, yor_low)
        )

        if range_ready and context.position_quantity != 0 and range_close_exit:
            causal_features.append(self._range_close_feature(bar, state, yor_high, yor_low))
            orders.append(self._close_position_intent(context, "range_close"))
            alerts.append(Alert.create(self.instance.strategy_id, "info", "Yearly ORB range-close exit requested"))

        if range_ready and context.position_quantity != 0:
            active_tp = _to_float(state.get("active_tp"))
            active_entry = _to_float(state.get("active_entry"))
            active_direction = state.get("active_direction", "")
            full_tp_seen = state.get("full_tp_seen") == "true"
            touched = (
                active_direction == "long"
                and active_tp is not None
                and bar.high >= active_tp
            ) or (
                active_direction == "short"
                and active_tp is not None
                and bar.low <= active_tp
            )
            if touched and not full_tp_seen and active_entry is not None:
                for order in context.strategy_open_orders:
                    if order.trade_id == state.get("active_trade_id") and order.bracket_role in {"runner_stop", "stop"}:
                        modifies.append(
                            ModifyIntent(
                                strategy_id=self.instance.strategy_id,
                                broker_order_id=order.broker_order_id,
                                reason="runner_stop_to_breakeven",
                                stop_price=active_entry,
                            )
                        )
                state["full_tp_seen"] = "true"

        # Confirm inside-range swings using prior bar as pivot after current bar closes.
        prior_bars = list(state.get("last_bars", []))
        if range_ready and len(prior_bars) >= 2:
            b2 = prior_bars[-2]
            b1 = prior_bars[-1]
            pivot_inside = float(b1["high"]) <= yor_high and float(b1["low"]) >= yor_low
            if pivot_inside and float(b1["low"]) < float(b2["low"]) and float(b1["low"]) <= bar.low:
                state["last_inside_swing_low"] = float(b1["low"])
                causal_features.append(self._swing_feature(bar.ts, "inside_swing_low", b1, yor_high, yor_low))
            if pivot_inside and float(b1["high"]) > float(b2["high"]) and float(b1["high"]) >= bar.high:
                state["last_inside_swing_high"] = float(b1["high"])
                causal_features.append(self._swing_feature(bar.ts, "inside_swing_high", b1, yor_high, yor_low))

        if self._in_or_window(month):
            yor_high = bar.high if yor_high is None else max(yor_high, bar.high)
            yor_low = bar.low if yor_low is None else min(yor_low, bar.low)
            state["yor_high"] = yor_high
            state["yor_low"] = yor_low
            state["yor_available_ts"] = bar.ts
            levels.extend(self._range_levels(bar.ts, yor_high, yor_low))
            range_ready = yor_high is not None and yor_low is not None and yor_high > yor_low
            if range_ready:
                causal_features.append(self._range_feature(bar.ts, state, yor_high, yor_low))

        has_open_entry_order = any(not o.reduce_only for o in context.strategy_open_orders)
        flat = context.position_quantity == 0 and not has_open_entry_order
        if range_ready and flat and self._in_trade_window(month):
            if self._entry_mode() == "oco_stop":
                oco_orders = self._oco_entry_orders(bar.ts, yor_high, yor_low, state)
                if oco_orders:
                    causal_features.append(self._entry_gate_feature(bar, state, yor_high, yor_low, "oco_stop", True))
                    orders.extend(oco_orders)
                    alerts.append(
                        Alert.create(
                            self.instance.strategy_id,
                            "order_pending_verification",
                            "Yearly ORB OCO stop entry intents created",
                        )
                    )
            else:
                prior_close = float(prior_bars[-1]["close"]) if prior_bars else None
                fresh_long = bar.close > yor_high and (
                    not self.config["require_fresh_break"] or prior_close is None or prior_close <= yor_high
                )
                fresh_short = bar.close < yor_low and (
                    not self.config["require_fresh_break"] or prior_close is None or prior_close >= yor_low
                )
                if fresh_long and _to_float(state.get("last_inside_swing_low")) is not None:
                    causal_features.append(self._entry_gate_feature(bar, state, yor_high, yor_low, "long_limit_retest", True, prior_close))
                    orders.extend(self._entry_ladder("long", bar.ts, yor_high, yor_low, state))
                    alerts.append(Alert.create(self.instance.strategy_id, "order_pending_verification", "Yearly ORB long retest order intent created"))
                elif fresh_short and _to_float(state.get("last_inside_swing_high")) is not None:
                    causal_features.append(self._entry_gate_feature(bar, state, yor_high, yor_low, "short_limit_retest", True, prior_close))
                    orders.extend(self._entry_ladder("short", bar.ts, yor_high, yor_low, state))
                    alerts.append(Alert.create(self.instance.strategy_id, "order_pending_verification", "Yearly ORB short retest order intent created"))
                else:
                    causal_features.append(self._entry_gate_feature(bar, state, yor_high, yor_low, "limit_retest", False, prior_close))

        prior_bars.append(
            {
                "ts": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
        )
        state["last_bars"] = prior_bars[-3:]
        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, modifies, levels, alerts, causal_features)

    def _state_for_year(self, year: int) -> Dict[str, Any]:
        current = self.state or {}
        if current.get("year") != year:
            current = {
                "year": year,
                "yor_high": None,
                "yor_low": None,
                "yor_available_ts": "",
                "last_inside_swing_low": None,
                "last_inside_swing_high": None,
                "last_bars": [],
                "trade_seq": 0,
                "active_trade_id": "",
                "active_entry": None,
                "active_tp": None,
                "active_direction": "",
                "full_tp_seen": "false",
                "new_year_reset_needed": True,
            }
        return current

    def _range_levels(self, ts: str, high: float, low: float) -> List[LevelUpdate]:
        return [
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "yearly_orb_high", high, ts),
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "yearly_orb_low", low, ts),
        ]

    def _range_feature(self, ts: str, state: Dict[str, Any], high: float, low: float) -> FeatureSnapshot:
        return feature_snapshot(
            self.instance,
            "yearly_orb_range",
            ts,
            event_ts=str(state.get("yor_available_ts") or ts),
            available_at_ts=str(state.get("yor_available_ts") or ts),
            source="completed_daily_jan_mar_range",
            value_ref="%.8f/%.8f" % (high, low),
            metadata={
                "year": state.get("year"),
                "or_start_month": self.config.get("or_start_month"),
                "or_end_month": self.config.get("or_end_month"),
                "range_value": high - low,
                "entry_mode": self._entry_mode(),
            },
        )

    def _swing_feature(
        self,
        current_bar_ts: str,
        feature_name: str,
        pivot_bar: Dict[str, Any],
        yor_high: float,
        yor_low: float,
    ) -> FeatureSnapshot:
        price = pivot_bar["low"] if feature_name == "inside_swing_low" else pivot_bar["high"]
        return feature_snapshot(
            self.instance,
            "yearly_orb_%s" % feature_name,
            current_bar_ts,
            event_ts=str(pivot_bar["ts"]),
            available_at_ts=current_bar_ts,
            source="confirmed_daily_inside_range_pivot",
            value_ref=price,
            metadata={
                "pivot_ts": pivot_bar["ts"],
                "pivot_open": pivot_bar["open"],
                "pivot_high": pivot_bar["high"],
                "pivot_low": pivot_bar["low"],
                "pivot_close": pivot_bar["close"],
                "yearly_or_high": yor_high,
                "yearly_or_low": yor_low,
            },
        )

    def _entry_gate_feature(
        self,
        bar: Bar,
        state: Dict[str, Any],
        yor_high: float,
        yor_low: float,
        gate: str,
        allowed: bool,
        prior_close: Optional[float] = None,
    ) -> FeatureSnapshot:
        prior_bars = list(state.get("last_bars", []))
        prior_ts = str(prior_bars[-1]["ts"]) if prior_bars else bar.ts
        return feature_snapshot(
            self.instance,
            "yearly_orb_entry_gate",
            bar.ts,
            event_ts=prior_ts,
            available_at_ts=bar.ts,
            source="yearly_orb_scaleout3.entry_rules",
            value_ref="%s:%s" % (gate, "allowed" if allowed else "blocked"),
            metadata={
                "year": state.get("year"),
                "gate": gate,
                "allowed": allowed,
                "bar_close": bar.close,
                "prior_close": prior_close,
                "yor_high": yor_high,
                "yor_low": yor_low,
                "last_inside_swing_low": state.get("last_inside_swing_low"),
                "last_inside_swing_high": state.get("last_inside_swing_high"),
                "require_fresh_break": self.config.get("require_fresh_break"),
                "entry_mode": self._entry_mode(),
            },
        )

    def _range_close_feature(self, bar: Bar, state: Dict[str, Any], yor_high: float, yor_low: float) -> FeatureSnapshot:
        return feature_snapshot(
            self.instance,
            "yearly_orb_range_close_exit",
            bar.ts,
            source="yearly_orb_scaleout3.range_close",
            value_ref=bar.close,
            metadata={
                "year": state.get("year"),
                "bar_close": bar.close,
                "yor_high": yor_high,
                "yor_low": yor_low,
                "inside_frac": self.config.get("range_close_inside_frac"),
                "active_direction": state.get("active_direction"),
            },
        )

    def _entry_ladder(self, direction: str, ts: str, yor_high: float, yor_low: float, state: Dict[str, Any]) -> List[OrderIntent]:
        rng = yor_high - yor_low
        trade_seq = int(state.get("trade_seq", 0)) + 1
        state["trade_seq"] = trade_seq
        trade_id = "%s_%s_%02d" % (self.instance.strategy_id, state["year"], trade_seq)
        tp25_qty, tp_qty, runner_qty = self._unit_quantities()
        if direction == "long":
            side = "buy"
            entry = yor_high
            stop = float(state["last_inside_swing_low"])
            tp = yor_high + rng * float(self.config["tp_full_mult"])
            tp25 = entry + (tp - entry) * float(self.config["tp25_frac"])
        else:
            side = "sell"
            entry = yor_low
            stop = float(state["last_inside_swing_high"])
            tp = yor_low - rng * float(self.config["tp_full_mult"])
            tp25 = entry - (entry - tp) * float(self.config["tp25_frac"])
        state["active_trade_id"] = trade_id
        state["active_entry"] = entry
        state["active_tp"] = tp
        state["active_direction"] = direction
        state["full_tp_seen"] = "false"
        base = dict(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            limit_price=entry,
            requires_verification=True,
            bracket_stop_price=stop,
            live_after_ts=ts,
            expires_after_ts="%s-12-31T23:59:59" % state["year"],
        )
        out: List[OrderIntent] = []
        if tp25_qty > 0:
            out.append(OrderIntent.create(**base, quantity=tp25_qty, reason="%s_tp25_entry" % direction, bracket_role="entry", bracket_target_price=tp25))
        if tp_qty > 0:
            out.append(OrderIntent.create(**base, quantity=tp_qty, reason="%s_tp_entry" % direction, bracket_role="entry", bracket_target_price=tp))
        if runner_qty > 0:
            out.append(OrderIntent.create(**base, quantity=runner_qty, reason="%s_runner_entry" % direction, bracket_role="runner_entry"))
        return out

    def _oco_entry_orders(self, ts: str, yor_high: float, yor_low: float, state: Dict[str, Any]) -> List[OrderIntent]:
        long_stop = _to_float(state.get("last_inside_swing_low"))
        short_stop = _to_float(state.get("last_inside_swing_high"))
        directions: List[str] = []
        if long_stop is not None:
            directions.append("long")
        if short_stop is not None:
            directions.append("short")
        if not directions:
            return []
        trade_seq = int(state.get("trade_seq", 0)) + 1
        state["trade_seq"] = trade_seq
        trade_id = "%s_%s_%02d" % (self.instance.strategy_id, state["year"], trade_seq)
        tp25_qty, tp_qty, runner_qty = self._unit_quantities()
        qty = tp25_qty + tp_qty + runner_qty
        oco = "%s_entry_oco" % trade_id if len(directions) > 1 else ""
        expires = "%s-12-31T23:59:59" % state["year"]
        out: List[OrderIntent] = []
        if "long" in directions:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="buy",
                    order_type="stop",
                    quantity=qty,
                    stop_price=yor_high,
                    reason="long_oco_entry",
                    requires_verification=True,
                    bracket_role="entry",
                    oco_group=oco,
                    live_after_ts=ts,
                    expires_after_ts=expires,
                )
            )
        if "short" in directions:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="sell",
                    order_type="stop",
                    quantity=qty,
                    stop_price=yor_low,
                    reason="short_oco_entry",
                    requires_verification=True,
                    bracket_role="entry",
                    oco_group=oco,
                    live_after_ts=ts,
                    expires_after_ts=expires,
                )
            )
        return out

    def _oco_exit_orders(self, fill, yor_high: float, yor_low: float, stop: float) -> List[OrderIntent]:
        tp25_qty, tp_qty, runner_qty = self._unit_quantities()
        total_qty = tp25_qty + tp_qty + runner_qty
        rng = yor_high - yor_low
        long_entry = fill.side == "buy"
        entry = yor_high if long_entry else yor_low
        tp = yor_high + rng * float(self.config["tp_full_mult"]) if long_entry else yor_low - rng * float(self.config["tp_full_mult"])
        tp25 = entry + (tp - entry) * float(self.config["tp25_frac"]) if long_entry else entry - (entry - tp) * float(self.config["tp25_frac"])
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
        out: List[OrderIntent] = []
        out.append(
            OrderIntent.create(
                **common,
                order_type="stop",
                quantity=total_qty,
                stop_price=stop,
                reason="protective_stop",
                bracket_role="stop",
            )
        )
        if tp25_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp25_qty,
                    limit_price=tp25,
                    reason="target",
                    bracket_role="target",
                )
            )
        if tp_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp_qty,
                    limit_price=tp,
                    reason="target",
                    bracket_role="target",
                )
            )
        return out

    def _close_position_intent(self, context: StrategyContext, reason: str) -> OrderIntent:
        qty = abs(context.position_quantity)
        side = "sell" if context.position_quantity > 0 else "buy"
        trade_id = str(self.state.get("active_trade_id") or new_id("trade"))
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
        )

    def _in_or_window(self, month: int) -> bool:
        return int(self.config["or_start_month"]) <= month <= int(self.config["or_end_month"])

    def _in_trade_window(self, month: int) -> bool:
        return int(self.config["trade_start_month"]) <= month <= int(self.config["trade_end_month"])

    def _entry_mode(self) -> str:
        return str(self.config.get("entry_mode") or "limit_retest")

    def _entry_swing_stop(self, fill_side: str, state: Dict[str, Any]) -> Optional[float]:
        if fill_side == "buy":
            return _to_float(state.get("last_inside_swing_low"))
        return _to_float(state.get("last_inside_swing_high"))

    def _has_open_reduce_order_for_trade(self, context: StrategyContext, trade_id: str) -> bool:
        return any(order.reduce_only and order.trade_id == trade_id for order in context.strategy_open_orders)

    def _range_close_exit(
        self,
        close: float,
        position_quantity: int,
        state: Dict[str, Any],
        yor_high: float,
        yor_low: float,
    ) -> bool:
        inside_frac = _to_float(self.config.get("range_close_inside_frac"))
        if inside_frac is None:
            return yor_low <= close <= yor_high

        rng = yor_high - yor_low
        active_direction = state.get("active_direction", "")
        is_long = position_quantity > 0 or active_direction == "long"
        is_short = position_quantity < 0 or active_direction == "short"
        if is_long:
            return close <= yor_high - (rng * inside_frac)
        if is_short:
            return close >= yor_low + (rng * inside_frac)
        return False


def _parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text[:10])


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
