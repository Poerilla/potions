from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

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
from .yearly_orb_delivery_helpers import (
    SwingKey,
    build_daily_swings,
    build_weekly_swings_on_daily,
    decode_swing_key,
    encode_swing_key,
    find_delivery_signal,
    make_delivery_levels,
)


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
            # range_close: close back inside YOR (optional inside_frac depth)
            # mid_close: long closes when close <= YOR mid; short when close >= mid
            # inside_swing_take: no range/mid market flatten; protective stop trails
            #   to the most recent confirmed inside-range swing (exit = take swing)
            "exit_mode": "range_close",  # range_close | mid_close | inside_swing_take
            "entry_mode": "limit_retest",  # limit_retest | oco_stop
            # Research: yearly_orb_delivery_scalein_*_inside_range_swing_range_close
            "delivery_scalein": False,
            "delivery_scale_swing_timeframe": "weekly",  # weekly | daily
            "delivery_scale_qty": 1,
            "delivery_target_R": 2.0,
            # Optional entry calendar filters (diagnostic / research gates).
            # Empty list = no restriction. Week-of-month = ((day-1)//7)+1 on bar date.
            "allow_weeks_of_month": [],
            "skip_entry_months": [],
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def _unit_quantities(self) -> tuple[int, int, int]:
        """Return ``(tp25_qty, tp_qty, runner_qty)``.

        Per-unit knobs (``tp25_qty``, ``tp_qty``, ``runner_qty``) override the
        legacy ``batch_qty``-only behaviour. Explicit ``0`` disables that bucket.
        Missing knobs fall back to ``batch_qty`` so existing configs are unchanged.
        """

        default = int(self.config["batch_qty"])

        def _qty(key: str) -> int:
            if key not in self.config or self.config.get(key) is None:
                return default
            return int(self.config[key])

        return _qty("tp25_qty"), _qty("tp_qty"), _qty("runner_qty")

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "D" or not bar.complete:
            return StrategyActions.empty()
        return self._on_completed_daily_bar(bar, context)

    def on_daily_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        return self.on_bar_close(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state_for_year(_parse_ts(fill.ts).year)
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        yor_high = _to_float(state.get("yor_high"))
        yor_low = _to_float(state.get("yor_low"))
        delivery_tid = str(state.get("delivery_trade_id") or "")
        base_tid = str(state.get("active_trade_id") or "")

        if fill.trade_id == delivery_tid:
            if context.position_quantity == 0:
                self._clear_position_state(state)
            elif fill.reason not in {"entry", "runner_entry"} and not self._delivery_has_open_position(
                context, delivery_tid
            ):
                # Add-on completed while base still open — allow another scale-in.
                state["delivery_trade_id"] = ""
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [])

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
                    state["active_stop_price"] = stop

        if fill.reason in {"entry", "runner_entry"} and context.position_quantity != 0:
            state["active_trade_id"] = fill.trade_id
            state["active_entry"] = fill.price
            state["active_direction"] = "long" if fill.side == "buy" else "short"
            state["base_remaining_qty"] = int(state.get("base_remaining_qty") or 0) + int(fill.quantity)
            fill_idx = self._bar_index_for_ts(state, fill.ts)
            if fill_idx is not None and int(state.get("base_fill_bar_idx", -1)) < 0:
                state["base_fill_bar_idx"] = fill_idx
            if yor_high is not None and yor_low is not None and yor_high > yor_low:
                rng = yor_high - yor_low
                if fill.side == "buy":
                    state["active_tp"] = yor_high + rng * float(self.config["tp_full_mult"])
                else:
                    state["active_tp"] = yor_low - rng * float(self.config["tp_full_mult"])
            state["full_tp_seen"] = "false"

        elif fill.trade_id == base_tid and fill.reason not in {"entry", "runner_entry"}:
            state["base_remaining_qty"] = max(0, int(state.get("base_remaining_qty") or 0) - int(fill.quantity))
            if int(state.get("base_remaining_qty") or 0) == 0 and delivery_tid and context.position_quantity != 0:
                orders.append(
                    self._close_delivery_intent(
                        context, delivery_tid, "base_closed", live_after_ts=fill.ts
                    )
                )
                cancels.extend(self._cancel_delivery_orders(context, delivery_tid, "base_closed"))

        if context.position_quantity == 0:
            self._clear_position_state(state)

        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], [], [])

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
                orders.append(self._close_position_intent(context, "year_change", live_after_ts=bar.ts))
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
        exit_mode = self._exit_mode()
        range_close_exit = bool(
            range_ready
            and exit_mode != "inside_swing_take"
            and self._range_close_exit(bar.close, context.position_quantity, state, yor_high, yor_low)
        )
        exit_reason = "mid_close" if exit_mode == "mid_close" else "range_close"

        if range_ready and context.position_quantity != 0 and range_close_exit:
            causal_features.append(self._range_close_feature(bar, state, yor_high, yor_low))
            delivery_tid = str(state.get("delivery_trade_id") or "")
            if delivery_tid:
                cancels.extend(self._cancel_delivery_orders(context, delivery_tid, exit_reason))
            orders.append(self._close_position_intent(context, exit_reason, live_after_ts=bar.ts))
            alerts.append(
                Alert.create(
                    self.instance.strategy_id,
                    "info",
                    "Yearly ORB %s exit requested" % exit_reason.replace("_", "-"),
                )
            )

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
                state["active_stop_price"] = active_entry
                delivery_tid = str(state.get("delivery_trade_id") or "")
                if delivery_tid:
                    # Research: cancel pending scale-in once base full TP (unit 2) is seen.
                    pending_cancels = self._cancel_delivery_pending_entries(context, delivery_tid, "base_tp_cancel")
                    if pending_cancels:
                        cancels.extend(pending_cancels)
                        if not self._delivery_has_open_position(context, delivery_tid):
                            state["delivery_trade_id"] = ""

        # Confirm inside-range swings using prior bar as pivot after current bar closes.
        prior_bars = list(state.get("last_bars", []))
        swing_low_updated = False
        swing_high_updated = False
        if range_ready and len(prior_bars) >= 2:
            b2 = prior_bars[-2]
            b1 = prior_bars[-1]
            pivot_inside = float(b1["high"]) <= yor_high and float(b1["low"]) >= yor_low
            if pivot_inside and float(b1["low"]) < float(b2["low"]) and float(b1["low"]) <= bar.low:
                state["last_inside_swing_low"] = float(b1["low"])
                swing_low_updated = True
                causal_features.append(self._swing_feature(bar.ts, "inside_swing_low", b1, yor_high, yor_low))
            if pivot_inside and float(b1["high"]) > float(b2["high"]) and float(b1["high"]) >= bar.high:
                state["last_inside_swing_high"] = float(b1["high"])
                swing_high_updated = True
                causal_features.append(self._swing_feature(bar.ts, "inside_swing_high", b1, yor_high, yor_low))

        if (
            exit_mode == "inside_swing_take"
            and range_ready
            and context.position_quantity != 0
            and (swing_low_updated or swing_high_updated)
            and not range_close_exit
        ):
            trail_mods = self._trail_stop_to_inside_swing(
                context,
                state,
                swing_low_updated=swing_low_updated,
                swing_high_updated=swing_high_updated,
            )
            if trail_mods:
                modifies.extend(trail_mods)
                causal_features.append(self._swing_trail_feature(bar, state, yor_high, yor_low))
                alerts.append(
                    Alert.create(
                        self.instance.strategy_id,
                        "info",
                        "Yearly ORB inside-swing stop trail requested",
                    )
                )

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
        entry_calendar_ok = self._entry_calendar_ok(dt)
        if has_open_entry_order and not entry_calendar_ok:
            # Drop resting entries outside the allow-list so fills don't sneak into
            # blocked weeks/months (matches diagnostic filters on entry_ts calendar).
            for open_order in context.strategy_open_orders:
                if open_order.reduce_only:
                    continue
                cancels.append(
                    CancelIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=open_order.broker_order_id,
                        reason="entry_calendar_gate",
                    )
                )
            has_open_entry_order = False
        flat = context.position_quantity == 0 and not has_open_entry_order
        if range_ready and flat and self._in_trade_window(month) and entry_calendar_ok:
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
        elif range_ready and flat and self._in_trade_window(month) and not entry_calendar_ok:
            causal_features.append(
                self._entry_gate_feature(bar, state, yor_high, yor_low, "entry_calendar_blocked", False)
            )

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
        year_bars = list(state.get("year_bars", []))
        year_bars.append(
            {
                "ts": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
        )
        state["year_bars"] = year_bars

        if (
            self._delivery_enabled()
            and range_ready
            and context.position_quantity != 0
            and not range_close_exit
            and state.get("full_tp_seen") != "true"
            and not str(state.get("delivery_trade_id") or "")
            and int(state.get("base_remaining_qty") or 0) > 0
            and int(state.get("base_fill_bar_idx", -1)) >= 0
        ):
            delivery_orders = self._maybe_arm_delivery(bar, state, yor_high, yor_low)
            if delivery_orders:
                orders.extend(delivery_orders)
                alerts.append(
                    Alert.create(
                        self.instance.strategy_id,
                        "order_pending_verification",
                        "Yearly ORB delivery scale-in intent created",
                    )
                )

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
                "year_bars": [],
                "trade_seq": 0,
                "active_trade_id": "",
                "active_entry": None,
                "active_tp": None,
                "active_direction": "",
                "full_tp_seen": "false",
                "active_stop_price": None,
                "base_remaining_qty": 0,
                "base_fill_bar_idx": -1,
                "delivery_trade_id": "",
                "delivery_used_swings": [],
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
                "exit_mode": self._exit_mode(),
                "active_direction": state.get("active_direction"),
            },
        )

    def _swing_trail_feature(
        self,
        bar: Bar,
        state: Dict[str, Any],
        yor_high: float,
        yor_low: float,
    ) -> FeatureSnapshot:
        return feature_snapshot(
            self.instance,
            "yearly_orb_inside_swing_stop_trail",
            bar.ts,
            source="yearly_orb_scaleout3.inside_swing_take",
            value_ref=state.get("active_stop_price"),
            metadata={
                "year": state.get("year"),
                "yor_high": yor_high,
                "yor_low": yor_low,
                "active_direction": state.get("active_direction"),
                "last_inside_swing_low": state.get("last_inside_swing_low"),
                "last_inside_swing_high": state.get("last_inside_swing_high"),
                "active_stop_price": state.get("active_stop_price"),
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
        state["active_stop_price"] = stop
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

    def _close_position_intent(
        self,
        context: StrategyContext,
        reason: str,
        *,
        live_after_ts: Optional[str] = None,
    ) -> OrderIntent:
        """Flatten with a market order.

        Completed daily bars decide after the close is known. Without
        ``live_after_ts``, Engine+PaperBroker would submit the market order on
        the same bar-close pass and fill it on that bar's **open** — lookahead.
        Pass the decision bar timestamp so the fill waits for the **next** bar
        open (``bar.ts > live_after_ts``).
        """
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
            live_after_ts=str(live_after_ts or ""),
        )

    def _delivery_enabled(self) -> bool:
        return bool(self.config.get("delivery_scalein"))

    def _clear_position_state(self, state: Dict[str, Any]) -> None:
        state["active_trade_id"] = ""
        state["active_entry"] = None
        state["active_tp"] = None
        state["active_direction"] = ""
        state["active_stop_price"] = None
        state["full_tp_seen"] = "false"
        state["base_remaining_qty"] = 0
        state["base_fill_bar_idx"] = -1
        state["delivery_trade_id"] = ""
        # Keep delivery_used_swings for the year so the same swing cannot re-fire
        # after a completed base trade flips back into another cycle. Research
        # resets used swings per base trade; mirror that:
        state["delivery_used_swings"] = []

    def _bar_index_for_ts(self, state: Dict[str, Any], ts: str) -> Optional[int]:
        day = str(ts)[:10]
        year_bars = list(state.get("year_bars") or [])
        for idx in range(len(year_bars) - 1, -1, -1):
            if str(year_bars[idx].get("ts", ""))[:10] == day:
                return idx
        return len(year_bars) - 1 if year_bars else None

    def _used_swing_set(self, state: Dict[str, Any]) -> Set[SwingKey]:
        out: Set[SwingKey] = set()
        for raw in state.get("delivery_used_swings") or []:
            try:
                out.add(decode_swing_key(str(raw)))
            except (TypeError, ValueError):
                continue
        return out

    def _maybe_arm_delivery(
        self,
        bar: Bar,
        state: Dict[str, Any],
        yor_high: float,
        yor_low: float,
    ) -> List[OrderIntent]:
        direction = str(state.get("active_direction") or "")
        if direction not in {"long", "short"}:
            return []
        if direction == "long" and bar.close <= yor_high:
            return []
        if direction == "short" and bar.close >= yor_low:
            return []

        year_bars = list(state.get("year_bars") or [])
        if len(year_bars) < 5:
            return []
        idx = len(year_bars) - 1
        min_idx = int(state.get("base_fill_bar_idx", -1))
        if min_idx < 0 or min_idx >= idx:
            return []

        tf = str(self.config.get("delivery_scale_swing_timeframe") or "weekly").lower()
        swings = build_weekly_swings_on_daily(year_bars) if tf == "weekly" else build_daily_swings(year_bars)
        used = self._used_swing_set(state)
        signal = find_delivery_signal(
            year_bars,
            swings,
            idx,
            direction,
            yor_high,
            yor_low,
            min_idx,
            used,
        )
        if signal is None:
            return []
        levels = make_delivery_levels(
            year_bars,
            swings,
            idx,
            direction,
            signal,
            min_idx,
            float(self.config.get("delivery_target_R") or 2.0),
        )
        if levels is None:
            return []
        entry, stop, target, key = levels
        qty = int(self.config.get("delivery_scale_qty") or 1)
        if qty <= 0:
            return []

        trade_seq = int(state.get("trade_seq", 0)) + 1
        state["trade_seq"] = trade_seq
        trade_id = "%s_%s_del_%02d" % (self.instance.strategy_id, state["year"], trade_seq)
        state["delivery_trade_id"] = trade_id
        used_list = list(state.get("delivery_used_swings") or [])
        used_list.append(encode_swing_key(key))
        state["delivery_used_swings"] = used_list

        side = "buy" if direction == "long" else "sell"
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=side,
                order_type="limit",
                quantity=qty,
                limit_price=entry,
                reason="delivery_scale_entry",
                requires_verification=True,
                bracket_role="entry",
                bracket_stop_price=stop,
                bracket_target_price=target,
                live_after_ts=bar.ts,
                expires_after_ts="%s-12-31T23:59:59" % state["year"],
            )
        ]

    def _cancel_delivery_orders(
        self,
        context: StrategyContext,
        delivery_tid: str,
        reason: str,
    ) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.trade_id == delivery_tid:
                out.append(
                    CancelIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=order.broker_order_id,
                        reason=reason,
                    )
                )
        return out

    def _cancel_delivery_pending_entries(
        self,
        context: StrategyContext,
        delivery_tid: str,
        reason: str,
    ) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.trade_id == delivery_tid and not order.reduce_only:
                out.append(
                    CancelIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=order.broker_order_id,
                        reason=reason,
                    )
                )
        return out

    def _delivery_has_open_position(self, context: StrategyContext, delivery_tid: str) -> bool:
        # Net position is aggregated; treat any reduce-only resting for the
        # delivery trade id as evidence the add-on fill is still open.
        return any(
            order.trade_id == delivery_tid and order.reduce_only
            for order in context.strategy_open_orders
        )

    def _close_delivery_intent(
        self,
        context: StrategyContext,
        delivery_tid: str,
        reason: str,
        *,
        live_after_ts: Optional[str] = None,
    ) -> OrderIntent:
        qty = abs(context.position_quantity)
        # Close remaining net when base is flat; qty should be the add-on residue.
        side = "sell" if context.position_quantity > 0 else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=delivery_tid,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts=str(live_after_ts or ""),
        )

    def _in_or_window(self, month: int) -> bool:
        return int(self.config["or_start_month"]) <= month <= int(self.config["or_end_month"])

    def _in_trade_window(self, month: int) -> bool:
        return int(self.config["trade_start_month"]) <= month <= int(self.config["trade_end_month"])

    def _skip_entry_months(self) -> Set[int]:
        raw = self.config.get("skip_entry_months") or []
        out: Set[int] = set()
        if isinstance(raw, (list, tuple)):
            for m in raw:
                try:
                    mi = int(m)
                except (TypeError, ValueError):
                    continue
                if 1 <= mi <= 12:
                    out.add(mi)
        return out

    def _allow_weeks_of_month(self) -> Set[int]:
        raw = self.config.get("allow_weeks_of_month") or []
        out: Set[int] = set()
        if isinstance(raw, (list, tuple)):
            for w in raw:
                try:
                    wi = int(w)
                except (TypeError, ValueError):
                    continue
                if 1 <= wi <= 5:
                    out.add(wi)
        return out

    @staticmethod
    def _week_of_month(dt: datetime) -> int:
        # Same formula as yearly_daily_condition_profile / HA mills.
        return ((int(dt.day) - 1) // 7) + 1

    def _entry_calendar_ok(self, dt: datetime) -> bool:
        skip_months = self._skip_entry_months()
        if skip_months and int(dt.month) in skip_months:
            return False
        allow_weeks = self._allow_weeks_of_month()
        if allow_weeks and self._week_of_month(dt) not in allow_weeks:
            return False
        return True

    def _entry_mode(self) -> str:
        return str(self.config.get("entry_mode") or "limit_retest")

    def _exit_mode(self) -> str:
        mode = str(self.config.get("exit_mode") or "range_close").strip().lower()
        if mode in {"mid", "midpoint", "yor_mid"}:
            return "mid_close"
        if mode in {"swing", "swing_take", "inside_swing", "inside_swing_take"}:
            return "inside_swing_take"
        if mode in {"range", "range_close", ""}:
            return "range_close"
        return mode

    def _entry_swing_stop(self, fill_side: str, state: Dict[str, Any]) -> Optional[float]:
        if fill_side == "buy":
            return _to_float(state.get("last_inside_swing_low"))
        return _to_float(state.get("last_inside_swing_high"))

    def _has_open_reduce_order_for_trade(self, context: StrategyContext, trade_id: str) -> bool:
        return any(order.reduce_only and order.trade_id == trade_id for order in context.strategy_open_orders)

    def _trail_stop_to_inside_swing(
        self,
        context: StrategyContext,
        state: Dict[str, Any],
        *,
        swing_low_updated: bool,
        swing_high_updated: bool,
    ) -> List[ModifyIntent]:
        """Ratchet protective stop to the latest confirmed inside-range swing.

        Longs trail on swing lows (stop only moves up). Shorts trail on swing
        highs (stop only moves down). Exit occurs when price takes that stop.
        """
        direction = str(state.get("active_direction") or "")
        trade_id = str(state.get("active_trade_id") or "")
        if not trade_id or direction not in {"long", "short"}:
            return []
        if direction == "long" and not swing_low_updated:
            return []
        if direction == "short" and not swing_high_updated:
            return []
        new_stop = (
            _to_float(state.get("last_inside_swing_low"))
            if direction == "long"
            else _to_float(state.get("last_inside_swing_high"))
        )
        if new_stop is None:
            return []
        cur_stop = _to_float(state.get("active_stop_price"))
        if cur_stop is not None:
            if direction == "long" and new_stop <= cur_stop + 1e-12:
                return []
            if direction == "short" and new_stop >= cur_stop - 1e-12:
                return []
        out: List[ModifyIntent] = []
        for order in context.strategy_open_orders:
            if order.trade_id != trade_id:
                continue
            if order.bracket_role not in {"runner_stop", "stop", "protective_stop"}:
                continue
            if str(order.order_type).lower() != "stop":
                continue
            out.append(
                ModifyIntent(
                    strategy_id=self.instance.strategy_id,
                    broker_order_id=order.broker_order_id,
                    reason="inside_swing_stop_trail",
                    stop_price=new_stop,
                )
            )
        if out:
            state["active_stop_price"] = new_stop
        return out

    def _range_close_exit(
        self,
        close: float,
        position_quantity: int,
        state: Dict[str, Any],
        yor_high: float,
        yor_low: float,
    ) -> bool:
        if self._exit_mode() == "inside_swing_take":
            return False

        inside_frac = _to_float(self.config.get("range_close_inside_frac"))
        if self._exit_mode() == "mid_close":
            inside_frac = 0.5 if inside_frac is None else inside_frac

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
