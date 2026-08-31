from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pytz

from ..models import (
    Alert,
    Bar,
    CancelIntent,
    FeatureSnapshot,
    LevelUpdate,
    OrderIntent,
    StrategyActions,
    new_id,
)
from .base import StrategyContext, StrategyPlugin

NY = pytz.timezone("America/New_York")


class V2BCleanBreakStrategy(StrategyPlugin):
    """Bullish-only v2b clean-break StrategyPlugin.

    The legacy clean-break studies were 5-minute candidate detectors.  This
    plugin keeps the same economic rules, but uses the broker-like runtime:
    stop entries are resting orders, fills occur from later bars, and the
    clean-close test is evaluated only after the breakout candle completes.
    """

    strategy_type = "v2b_clean_break"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "variant": "bullish_2r_rl_stop",
            "tick_size": 0.25,
            "entry_offset_ticks": 2,
            "rth_start": "09:30",
            "or_end": "09:45",
            "eod_cutoff": "15:55",
            "required_break_num": 0,
            "stop_mode": "opposite",  # opposite | boundary
            # single_2r | ladder3_runner | pyramid_outside_max8 | pyramid_outside
            "size_model": "single_2r",
            "max_pyramid_qty": 8,
            # Pyramid add cadence: every N eligible outside candles (1 = each).
            "pyramid_add_every_n": 1,
            # outside = low > OR high; opposing = outside + bearish close < open.
            "pyramid_add_mode": "outside",
            # Trail stop once bar high reaches this fraction of the way to 2R target.
            # 0 disables trail + target brackets (legacy close-into-range only).
            "trail_at_frac": 0.0,
            # Where to park the trailed stop: entry (BE) | or_high
            "trail_to": "entry",
            # When trail is armed, also rest a 2R target for the full book.
            "pyramid_place_2r_target": True,
            # Validation-only stress knobs (default off = parent behavior).
            "trail_delay_bars": 0,
            "miss_add_every_n": 0,
            "add_alternate_skip": False,
            "soft_exit_delay_bars": 0,
            "record_levels": False,
            # Validation helper for HTF-signal / finer-fill replays. When fills
            # arrive from a 1m tape, map entry fill timestamps to their parent
            # 5m signal bucket before running the clean-break validation.
            "fill_to_signal_minutes": 0,
            "fill_signal_bucket_end": False,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "5m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_5m_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason

        if role == "entry":
            trade.update(
                {
                    "direction": "Long",
                    "entry_price": fill.price,
                    "entry_ts": fill.ts,
                    "status": "pending_clean_validation",
                    "tp1_hit": False,
                    "tp2_hit": False,
                    "clean_validated": False,
                }
            )
            state["active_trade_id"] = fill.trade_id
            state["entry_bar_ts"] = self._signal_bucket_ts(fill.ts)
            state["pending_clean_validation"] = True
            state["entry_armed"] = False
            state["phase"] = "pending_clean_validation"
            self._commit_state(state)
            return StrategyActions.empty()

        if role == "tp1":
            trade["tp1_hit"] = True
            self._commit_state(state)
            return StrategyActions.empty()

        if role == "tp2":
            trade["tp2_hit"] = True
            if str(self.config.get("size_model")) == "ladder3_runner" and context.position_quantity > 0:
                cancels = self._cancel_open_roles(context, fill.trade_id, {"boundary_stop"})
                orders = [self._runner_stop_order(fill.trade_id, fill.ts, state)]
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])

        if role == "add":
            trade["adds_done"] = int(trade.get("adds_done") or 0) + int(fill.quantity)
            trade["add_pending"] = False
            state["add_pending"] = False
            orders: List[OrderIntent] = []
            cancels: List[CancelIntent] = []
            if bool(trade.get("trail_armed")) and context.position_quantity > 0:
                refresh_orders, refresh_cancels = self._refresh_pyramid_brackets(
                    fill.trade_id, fill.ts, state, context
                )
                orders.extend(refresh_orders)
                cancels.extend(refresh_cancels)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {
            "failed_clean_close",
            "ambiguous_break_close",
            "target",
            "stop",
            "trail_stop",
            "boundary_stop",
            "runner_stop",
            "eod_close",
            "close_back_into_range",
        }:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["done"] = True
                state["phase"] = "closed"
                state["active_trade_id"] = ""
                state["pending_clean_validation"] = False
                state["add_pending"] = False
                cancels = self._cancel_trade_orders(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_5m_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        session = dt.date().isoformat()
        t = dt.time()
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []
        features: List[FeatureSnapshot] = []

        if state.get("session_date") != session:
            # Flatten any leftover position before wiping session state (prior EOD miss).
            if context.position_quantity != 0:
                prior_tid = str(state.get("active_trade_id") or "")
                cancels.extend(self._cancel_all_open(context))
                orders.append(
                    self._close_position(
                        context, bar.ts, "eod_close", trade_id=prior_tid or None
                    )
                )
                state = self._fresh_session_state(session)
                state["done"] = True
                state["phase"] = "prior_session_flatten"
                self._commit_state(state)
                features.append(
                    self._feature(
                        "v2b_clean_break_prior_session_flatten",
                        bar,
                        state,
                        value_ref="position_quantity",
                        metadata={"position_quantity": context.position_quantity},
                    )
                )
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            state = self._fresh_session_state(session)

        if not self._in_rth(t):
            self._commit_state(state)
            return StrategyActions.empty()

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if t >= self._time("eod_cutoff"):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(
                    self._close_position(
                        context,
                        bar.ts,
                        "eod_close",
                        trade_id=str(state.get("active_trade_id") or "") or None,
                    )
                )
            state["done"] = True
            state["phase"] = "eod"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if t < self._time("or_end"):
            state["or_count"] = int(state.get("or_count", 0)) + 1
            state["or_high"] = bar.high if state.get("or_high") is None else max(float(state["or_high"]), bar.high)
            state["or_low"] = bar.low if state.get("or_low") is None else min(float(state["or_low"]), bar.low)
            if state["or_count"] >= 3 and not state.get("or_finalized"):
                state["or_finalized"] = True
                state["phase"] = "armed"
                entry = self._entry_order(bar.ts, state)
                if entry is not None:
                    orders.append(entry)
                    state["entry_armed"] = True
                    alerts.append(Alert.create(self.instance.strategy_id, "info", "v2b clean-break long stop armed"))
                    features.append(
                        self._feature(
                            "v2b_clean_break_or_finalized",
                            bar,
                            state,
                            value_ref="or_high/or_low/entry_stop",
                            metadata={
                                "entry_stop": entry.stop_price,
                                "entry_offset_ticks": int(self.config.get("entry_offset_ticks") or 0),
                                "or_count": int(state.get("or_count") or 0),
                            },
                        )
                    )
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        if state.get("done") or not state.get("or_finalized"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        if state.get("pending_clean_validation") and state.get("entry_bar_ts") == bar.ts:
            exits, exit_cancels = self._validate_breakout_bar(bar, state, context)
            orders.extend(exits)
            cancels.extend(exit_cancels)
            features.append(
                self._feature(
                    "v2b_clean_break_clean_validation",
                    bar,
                    state,
                    value_ref="breakout_bar_close/or_high/or_low",
                    metadata={
                        "entry_bar_ts": state.get("entry_bar_ts", ""),
                        "active_trade_id": state.get("active_trade_id", ""),
                        "outcome_roles": [o.bracket_role for o in exits],
                        "exit_cancels": len(exit_cancels),
                    },
                )
            )
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        # Pyramid-outside management: +1 on eligible outside candles (cadence /
        # opposing modes), optional trail@frac-to-2R; flatten if close into OR.
        if (
            self._is_pyramid_outside()
            and context.position_quantity > 0
            and not state.get("pending_clean_validation")
            and not state.get("done")
        ):
            pyramid_orders, pyramid_cancels, pyramid_features = self._manage_pyramid_outside(bar, state, context)
            orders.extend(pyramid_orders)
            cancels.extend(pyramid_cancels)
            features.extend(pyramid_features)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        if context.position_quantity == 0 and not state.get("pending_clean_validation") and state.get("entry_armed"):
            first_break_num = self._break_num_after_or(t)
            required = int(self.config.get("required_break_num") or 0)
            high = _to_float(state.get("or_high"))
            low = _to_float(state.get("or_low"))
            if high is not None and low is not None:
                down = bar.low <= low - float(self.config["tick_size"])
                if down:
                    features.append(
                        self._feature(
                            "v2b_clean_break_entry_guard",
                            bar,
                            state,
                            value_ref="or_low/tick/bar_low",
                            metadata={"decision": "initial_break_down", "required_break_num": required},
                        )
                    )
                    cancels.extend(self._cancel_all_open(context))
                    state["done"] = True
                    state["phase"] = "initial_break_down"
                elif required and first_break_num >= required:
                    # If the required 09:45 candle did not trigger the long
                    # stop, this variant is done for the session.
                    cancels.extend(self._cancel_all_open(context))
                    state["done"] = True
                    state["phase"] = "missed_required_break"
                    features.append(
                        self._feature(
                            "v2b_clean_break_entry_guard",
                            bar,
                            state,
                            value_ref="required_break_num/first_break_num",
                            metadata={
                                "decision": "missed_required_break",
                                "required_break_num": required,
                                "first_break_num": first_break_num,
                            },
                        )
                    )

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts, features)

    def _validate_breakout_bar(self, bar: Bar, state: Dict[str, Any], context: StrategyContext) -> tuple[List[OrderIntent], List[CancelIntent]]:
        trade_id = str(state.get("active_trade_id") or "")
        high = _to_float(state.get("or_high"))
        low = _to_float(state.get("or_low"))
        if trade_id == "" or high is None or low is None:
            return [], []
        tick = float(self.config["tick_size"])
        first_break_num = self._break_num_after_or(_parse_dt(bar.ts).time())
        required = int(self.config.get("required_break_num") or 0)
        ambiguous = bar.low <= low - tick

        if required and first_break_num != required:
            state["done"] = True
            state["phase"] = "entry_not_required_break"
            return [self._close_position(context, bar.ts, "ambiguous_break_close", trade_id=trade_id)], self._cancel_trade_orders(context, trade_id)

        if ambiguous:
            state["phase"] = "ambiguous_break_close"
            state["pending_clean_validation"] = False
            return [self._close_position(context, bar.ts, "ambiguous_break_close", trade_id=trade_id)], self._cancel_trade_orders(context, trade_id)

        if bar.close <= high:
            state["phase"] = "failed_clean_close"
            state["pending_clean_validation"] = False
            return [self._close_position(context, bar.ts, "failed_clean_close", trade_id=trade_id)], self._cancel_trade_orders(context, trade_id)

        state["pending_clean_validation"] = False
        state["phase"] = "clean_validated"
        trade = self._trade(trade_id, state)
        trade["status"] = "open"
        trade["clean_validated"] = True
        return self._exit_orders(trade_id, bar.ts, state), []

    def _exit_orders(self, trade_id: str, ts: str, state: Dict[str, Any]) -> List[OrderIntent]:
        # Pyramid-outside: no immediate brackets — managed on subsequent 5m closes
        # (optional trail stop + 2R target armed later when progress hits trail_at_frac).
        if self._is_pyramid_outside():
            return []
        params = self._params(state)
        if params is None:
            return []
        expiry = _session_expiry(ts)
        qty = int(self.config.get("entry_qty", 1))
        if str(self.config.get("size_model")) == "ladder3_runner":
            return [
                self._reduce_order(trade_id, ts, "stop", qty, stop=params["boundary_stop"], role="boundary_stop", expiry=expiry),
                self._reduce_order(trade_id, ts, "limit", 1, limit=params["tp1"], role="tp1", expiry=expiry),
                self._reduce_order(trade_id, ts, "limit", 1, limit=params["tp2"], role="tp2", expiry=expiry),
            ]
        role = "boundary_stop" if str(self.config.get("stop_mode")) == "boundary" else "stop"
        return [
            self._reduce_order(trade_id, ts, "stop", qty, stop=params["stop"], role=role, expiry=expiry),
            self._reduce_order(trade_id, ts, "limit", qty, limit=params["tp2"], role="target", expiry=expiry),
        ]

    def _is_pyramid_outside(self) -> bool:
        model = str(self.config.get("size_model") or "")
        return model == "pyramid_outside_max8" or model.startswith("pyramid_outside")

    def _manage_pyramid_outside(
        self, bar: Bar, state: Dict[str, Any], context: StrategyContext
    ) -> tuple[List[OrderIntent], List[CancelIntent], List[FeatureSnapshot]]:
        """Pyramid outside OR with optional cadence / opposing / trail@frac-to-2R."""
        high = _to_float(state.get("or_high"))
        trade_id = str(state.get("active_trade_id") or "")
        if high is None or trade_id == "":
            return [], [], []

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        features: List[FeatureSnapshot] = []
        trade = self._trade(trade_id, state)
        features.append(
            self._feature(
                "v2b_clean_break_pyramid_manage",
                bar,
                state,
                value_ref="bar_vs_or_high",
                metadata={
                    "trade_id": trade_id,
                    "position_quantity": context.position_quantity,
                    "max_pyramid_qty": int(self.config.get("max_pyramid_qty") or 8),
                    "bar_close_above_or_high": float(bar.close) > high,
                    "bar_low_above_or_high": float(bar.low) > high,
                    "trail_armed": bool(trade.get("trail_armed")),
                    "add_pending": bool(state.get("add_pending")),
                },
            )
        )

        # Soft-exit delay (validation S7): pending flatten from prior bar.
        if int(state.get("soft_exit_delay_left") or 0) > 0:
            left = int(state["soft_exit_delay_left"]) - 1
            state["soft_exit_delay_left"] = left
            if left <= 0:
                state["phase"] = "close_back_into_range"
                state["done"] = True
                state["add_pending"] = False
                return (
                    [self._close_position(context, bar.ts, "close_back_into_range", trade_id=trade_id)],
                    self._cancel_trade_orders(context, trade_id),
                    features,
                )
            # Still delayed — skip soft-exit re-trigger this bar; continue trail/adds.
        elif float(bar.close) <= high:
            features.append(
                self._feature(
                    "v2b_clean_break_soft_exit_check",
                    bar,
                    state,
                    value_ref="bar_close/or_high",
                    metadata={
                        "decision": "delay" if int(self.config.get("soft_exit_delay_bars") or 0) > 0 else "flatten",
                        "soft_exit_delay_bars": int(self.config.get("soft_exit_delay_bars") or 0),
                    },
                )
            )
            delay = max(0, int(self.config.get("soft_exit_delay_bars") or 0))
            if delay > 0:
                state["soft_exit_delay_left"] = delay
                state["phase"] = "soft_exit_pending"
                # Do not flatten yet.
            else:
                state["phase"] = "close_back_into_range"
                state["done"] = True
                state["add_pending"] = False
                return (
                    [self._close_position(context, bar.ts, "close_back_into_range", trade_id=trade_id)],
                    self._cancel_trade_orders(context, trade_id),
                    features,
                )

        # Arm trail once bar high reaches trail_at_frac of the path to 2R.
        # Optional delay (S4): observe trigger, then wait N completed bars before BE stop.
        trail_frac = float(self.config.get("trail_at_frac") or 0.0)
        if trail_frac > 0 and not bool(trade.get("trail_armed")):
            params = self._params(state)
            entry = _to_float(trade.get("entry_price"))
            if params is not None and entry is not None:
                target = float(params["tp2"])
                trigger = entry + trail_frac * (target - entry)
                features.append(
                    self._feature(
                        "v2b_clean_break_trail_check",
                        bar,
                        state,
                        value_ref="bar_high/trail_trigger",
                        metadata={
                            "trade_id": trade_id,
                            "entry": entry,
                            "target_2r": target,
                            "trail_frac": trail_frac,
                            "trail_trigger": trigger,
                            "trail_trigger_seen": bool(trade.get("trail_trigger_seen")),
                            "trail_delay_bars": int(self.config.get("trail_delay_bars") or 0),
                        },
                    )
                )
                delay_need = max(0, int(self.config.get("trail_delay_bars") or 0))
                if bool(trade.get("trail_trigger_seen")):
                    left = int(trade.get("trail_delay_left") or 0) - 1
                    trade["trail_delay_left"] = left
                    if left <= 0:
                        trade["trail_armed"] = True
                        trade["trail_armed_ts"] = bar.ts
                        state["phase"] = "trail_armed"
                        arm_orders, arm_cancels = self._refresh_pyramid_brackets(
                            trade_id, bar.ts, state, context
                        )
                        orders.extend(arm_orders)
                        cancels.extend(arm_cancels)
                elif float(bar.high) >= trigger:
                    trade["trail_trigger"] = trigger
                    trade["trail_trigger_seen"] = True
                    trade["trail_trigger_ts"] = bar.ts
                    if delay_need <= 0:
                        trade["trail_armed"] = True
                        trade["trail_armed_ts"] = bar.ts
                        state["phase"] = "trail_armed"
                        arm_orders, arm_cancels = self._refresh_pyramid_brackets(
                            trade_id, bar.ts, state, context
                        )
                        orders.extend(arm_orders)
                        cancels.extend(arm_cancels)
                    else:
                        trade["trail_delay_left"] = delay_need
                        state["phase"] = "trail_trigger_pending"

        max_qty = max(1, int(self.config.get("max_pyramid_qty") or 8))
        if context.position_quantity >= max_qty:
            return orders, cancels, features
        if bool(state.get("add_pending")):
            return orders, cancels, features
        # Candle must not trade back into the range (low stays strictly above OR high).
        if float(bar.low) <= high:
            return orders, cancels, features

        add_mode = str(self.config.get("pyramid_add_mode") or "outside").lower()
        if add_mode == "opposing" and float(bar.close) >= float(bar.open):
            # Opposing = bearish (red) pullback candle while still fully outside OR.
            return orders, cancels, features

        # Count eligible outside bars for every-N cadence.
        eligible_n = int(trade.get("eligible_outside_bars") or 0) + 1
        trade["eligible_outside_bars"] = eligible_n
        every_n = max(1, int(self.config.get("pyramid_add_every_n") or 1))
        features.append(
            self._feature(
                "v2b_clean_break_pyramid_add_gate",
                bar,
                state,
                value_ref="outside_bar_cadence",
                metadata={
                    "trade_id": trade_id,
                    "add_mode": add_mode,
                    "eligible_outside_bars": eligible_n,
                    "add_every_n": every_n,
                    "cadence_hit": eligible_n % every_n == 0,
                    "position_quantity": context.position_quantity,
                },
            )
        )
        if eligible_n % every_n != 0:
            return orders, cancels, features

        # Validation S5: miss every Nth cadence-eligible add.
        miss_n = int(self.config.get("miss_add_every_n") or 0)
        add_attempts = int(trade.get("add_attempts") or 0) + 1
        trade["add_attempts"] = add_attempts
        if miss_n > 0 and add_attempts % miss_n == 0:
            trade["missed_adds"] = int(trade.get("missed_adds") or 0) + 1
            return orders, cancels, features

        # Validation S6: alternate skip (no fractional CFD lot assumed).
        if bool(self.config.get("add_alternate_skip")) and (add_attempts % 2 == 0):
            trade["missed_adds"] = int(trade.get("missed_adds") or 0) + 1
            return orders, cancels, features

        # Avoid stacking a second add while an unmatched add order is still open.
        if any(
            (not o.reduce_only) and o.bracket_role == "add" and o.trade_id == trade_id
            for o in context.strategy_open_orders
        ):
            return orders, cancels, features

        trade["add_pending"] = True
        state["add_pending"] = True
        orders.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="buy",
                order_type="market",
                quantity=1,
                reason="pyramid_outside_add",
                requires_verification=False,
                reduce_only=False,
                bracket_role="add",
                live_after_ts=bar.ts,
                expires_after_ts=_session_expiry(bar.ts),
            )
        )
        features.append(
            self._feature(
                "v2b_clean_break_pyramid_add_order",
                bar,
                state,
                value_ref="market_add_after_completed_outside_bar",
                metadata={
                    "trade_id": trade_id,
                    "add_attempts": add_attempts,
                    "new_add_pending": True,
                },
            )
        )
        return orders, cancels, features

    def _refresh_pyramid_brackets(
        self,
        trade_id: str,
        ts: str,
        state: Dict[str, Any],
        context: StrategyContext,
    ) -> tuple[List[OrderIntent], List[CancelIntent]]:
        """Place/replace trail stop (+ optional 2R target) for current position size."""
        qty = abs(int(context.position_quantity))
        if qty <= 0:
            return [], []
        params = self._params(state)
        trade = self._trade(trade_id, state)
        entry = _to_float(trade.get("entry_price"))
        if params is None or entry is None:
            return [], []

        trail_to = str(self.config.get("trail_to") or "entry").lower()
        if trail_to == "or_high":
            stop_px = float(params["boundary_stop"])
        else:
            stop_px = float(entry)

        expiry = _session_expiry(ts)
        cancels = self._cancel_open_roles(context, trade_id, {"trail_stop", "target", "stop"})
        orders: List[OrderIntent] = [
            self._reduce_order(
                trade_id, ts, "stop", qty, stop=stop_px, role="trail_stop", expiry=expiry
            )
        ]
        trade["trail_stop"] = stop_px
        if bool(self.config.get("pyramid_place_2r_target", True)):
            orders.append(
                self._reduce_order(
                    trade_id, ts, "limit", qty, limit=float(params["tp2"]), role="target", expiry=expiry
                )
            )
            trade["target"] = float(params["tp2"])
        return orders, cancels

    def _runner_stop_order(self, trade_id: str, ts: str, state: Dict[str, Any]) -> OrderIntent:
        params = self._params(state)
        stop = params["tp1"] if params is not None else 0.0
        return self._reduce_order(trade_id, ts, "stop", 1, stop=stop, role="runner_stop", expiry=_session_expiry(ts))

    def _entry_order(self, ts: str, state: Dict[str, Any]) -> Optional[OrderIntent]:
        high = _to_float(state.get("or_high"))
        low = _to_float(state.get("or_low"))
        if high is None or low is None or high <= low:
            return None
        trade_id = self._new_trade_id(state)
        state["trades"][trade_id] = {
            "direction": "Long",
            "status": "armed",
            "range_high": high,
            "range_low": low,
            "range_value": high - low,
        }
        tick = float(self.config["tick_size"])
        entry_offset = int(self.config.get("entry_offset_ticks", 2)) * tick
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy",
            order_type="stop",
            quantity=int(self.config.get("entry_qty", 1)),
            stop_price=high + entry_offset,
            reason="v2b_clean_break_entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=_session_expiry(ts),
        )

    def _reduce_order(
        self,
        trade_id: str,
        ts: str,
        order_type: str,
        qty: int,
        role: str,
        expiry: str,
        limit: Optional[float] = None,
        stop: Optional[float] = None,
    ) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell",
            order_type=order_type,
            quantity=qty,
            limit_price=limit,
            stop_price=stop,
            reason="v2b_clean_break_%s" % role,
            requires_verification=False,
            reduce_only=True,
            bracket_role=role,
            live_after_ts=ts,
            expires_after_ts=expiry,
        )

    def _close_position(
        self,
        context: StrategyContext,
        ts: str,
        reason: str,
        trade_id: Optional[str] = None,
    ) -> OrderIntent:
        tid = str(trade_id or (self.state or {}).get("active_trade_id") or "") or new_id("trade")
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=tid,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if context.position_quantity > 0 else "buy",
            order_type="market_close",
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            live_after_ts=ts,
        )

    def _params(self, state: Dict[str, Any]) -> Optional[Dict[str, float]]:
        high = _to_float(state.get("or_high"))
        low = _to_float(state.get("or_low"))
        if high is None or low is None or high <= low:
            return None
        tick = float(self.config["tick_size"])
        entry_offset = int(self.config.get("entry_offset_ticks", 2)) * tick
        entry = high + entry_offset
        rng = high - low
        stop = high if str(self.config.get("stop_mode")) == "boundary" else low
        return {
            "entry": entry,
            "tp1": entry + rng,
            "tp2": entry + 2.0 * rng,
            "stop": stop,
            "boundary_stop": high,
        }

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("session_date", "")
        state.setdefault("or_count", 0)
        state.setdefault("or_high", None)
        state.setdefault("or_low", None)
        state.setdefault("or_finalized", False)
        state.setdefault("phase", "")
        state.setdefault("done", False)
        state.setdefault("trade_seq", 0)
        state.setdefault("entry_armed", False)
        state.setdefault("active_trade_id", "")
        state.setdefault("entry_bar_ts", "")
        state.setdefault("pending_clean_validation", False)
        state.setdefault("trades", {})
        return state

    def _fresh_session_state(self, session: str) -> Dict[str, Any]:
        return {
            "session_date": session,
            "or_count": 0,
            "or_high": None,
            "or_low": None,
            "or_finalized": False,
            "phase": "building_or",
            "done": False,
            "trade_seq": 0,
            "entry_armed": False,
            "active_trade_id": "",
            "entry_bar_ts": "",
            "pending_clean_validation": False,
            "soft_exit_delay_left": 0,
            "trades": {},
        }

    def _commit_state(self, state: Dict[str, Any]) -> None:
        if state != (self.state or {}):
            self.state = state
            self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_%s_%02d" % (
            self.instance.strategy_id,
            str(state.get("session_date", "")).replace("-", ""),
            int(state["trade_seq"]),
        )

    def _cancel_trade_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_clean_break_trade_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id
        ]

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: Iterable[str]) -> List[CancelIntent]:
        role_set = set(roles)
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_clean_break_cancel_%s" % order.bracket_role)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.bracket_role in role_set
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_clean_break_cancel")
            for order in context.strategy_open_orders
        ]

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        high = _to_float(state.get("or_high"))
        low = _to_float(state.get("or_low"))
        if high is None or low is None:
            return []
        return [
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "v2b_clean_or_high", high, ts),
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "v2b_clean_or_low", low, ts),
        ]

    def _feature(
        self,
        feature_name: str,
        bar: Bar,
        state: Dict[str, Any],
        *,
        value_ref: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FeatureSnapshot:
        meta: Dict[str, Any] = {
            "session_date": state.get("session_date", ""),
            "phase": state.get("phase", ""),
            "or_count": int(state.get("or_count") or 0),
            "or_high": state.get("or_high"),
            "or_low": state.get("or_low"),
            "bar_open": bar.open,
            "bar_high": bar.high,
            "bar_low": bar.low,
            "bar_close": bar.close,
            "bar_timeframe": bar.timeframe,
            "variant": self.config.get("variant"),
            "size_model": self.config.get("size_model"),
        }
        if metadata:
            meta.update(metadata)
        return FeatureSnapshot(
            feature_name=feature_name,
            strategy_id=self.instance.strategy_id,
            instrument=self.instance.instrument,
            event_ts=bar.ts,
            available_at_ts=bar.ts,
            current_bar_ts=bar.ts,
            source=bar.source,
            value_ref=value_ref,
            metadata_json=json.dumps(meta, sort_keys=True, default=str),
        )

    def _time(self, key: str) -> time:
        hh, mm = str(self.config[key]).split(":")
        return time(int(hh), int(mm))

    def _in_rth(self, t: time) -> bool:
        return self._time("rth_start") <= t < time(16, 0)

    def _break_num_after_or(self, t: time) -> int:
        start = self._time("or_end")
        return max(0, int(((t.hour * 60 + t.minute) - (start.hour * 60 + start.minute)) / 5) + 1)

    def _signal_bucket_ts(self, ts: str) -> str:
        minutes = int(self.config.get("fill_to_signal_minutes") or 0)
        if minutes <= 1:
            return ts
        dt = _parse_dt(ts)
        bucket_minute = (dt.minute // minutes) * minutes
        bucket_dt = dt.replace(minute=bucket_minute, second=0, microsecond=0)
        if bool(self.config.get("fill_signal_bucket_end")):
            bucket_dt = bucket_dt + timedelta(minutes=minutes - 1)
        return bucket_dt.isoformat()


def _parse_dt(ts: str) -> datetime:
    """Parse bar/event timestamps into America/New_York for session clocks.

    Research replays stamp bars with NY offsets (``-04:00``/``-05:00``) or naive
    NY wall clock. Live OANDA bars are true UTC (``Z`` / ``+00:00``). Session
    gates (``rth_start``, ``or_end``, ``eod_cutoff``) are NY wall times, so always
    convert before comparing.
    """
    value = str(ts)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    if dt.tzinfo is None:
        return NY.localize(dt)
    return dt.astimezone(NY)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _session_expiry(ts: str) -> str:
    """NY cash-session order expiry at 15:59 America/New_York."""
    dt = _parse_dt(ts)
    expiry = NY.localize(datetime.combine(dt.date(), time(15, 59)))
    return expiry.isoformat()
