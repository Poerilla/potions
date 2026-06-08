from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Dict, Iterable, List, Optional

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


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
            "size_model": "single_2r",  # single_2r | ladder3_runner
            "record_levels": False,
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
            state["entry_bar_ts"] = fill.ts
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

        if role in {"failed_clean_close", "ambiguous_break_close", "target", "stop", "boundary_stop", "runner_stop", "eod_close"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["done"] = True
                state["phase"] = "closed"
                state["active_trade_id"] = ""
                state["pending_clean_validation"] = False
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
        if state.get("session_date") != session:
            state = self._fresh_session_state(session)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        if not self._in_rth(t):
            self._commit_state(state)
            return StrategyActions.empty()

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if t >= self._time("eod_cutoff"):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_position(context, bar.ts, "eod_close"))
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
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("done") or not state.get("or_finalized"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("pending_clean_validation") and state.get("entry_bar_ts") == bar.ts:
            exits, exit_cancels = self._validate_breakout_bar(bar, state, context)
            orders.extend(exits)
            cancels.extend(exit_cancels)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if context.position_quantity == 0 and not state.get("pending_clean_validation") and state.get("entry_armed"):
            first_break_num = self._break_num_after_or(t)
            required = int(self.config.get("required_break_num") or 0)
            high = _to_float(state.get("or_high"))
            low = _to_float(state.get("or_low"))
            if high is not None and low is not None:
                down = bar.low <= low - float(self.config["tick_size"])
                if down:
                    cancels.extend(self._cancel_all_open(context))
                    state["done"] = True
                    state["phase"] = "initial_break_down"
                elif required and first_break_num >= required:
                    # If the required 09:45 candle did not trigger the long
                    # stop, this variant is done for the session.
                    cancels.extend(self._cancel_all_open(context))
                    state["done"] = True
                    state["phase"] = "missed_required_break"

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

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
            return [self._close_position(context, bar.ts, "ambiguous_break_close")], self._cancel_trade_orders(context, trade_id)

        if ambiguous:
            state["phase"] = "ambiguous_break_close"
            state["pending_clean_validation"] = False
            return [self._close_position(context, bar.ts, "ambiguous_break_close")], self._cancel_trade_orders(context, trade_id)

        if bar.close <= high:
            state["phase"] = "failed_clean_close"
            state["pending_clean_validation"] = False
            return [self._close_position(context, bar.ts, "failed_clean_close")], self._cancel_trade_orders(context, trade_id)

        state["pending_clean_validation"] = False
        state["phase"] = "clean_validated"
        trade = self._trade(trade_id, state)
        trade["status"] = "open"
        trade["clean_validated"] = True
        return self._exit_orders(trade_id, bar.ts, state), []

    def _exit_orders(self, trade_id: str, ts: str, state: Dict[str, Any]) -> List[OrderIntent]:
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

    def _close_position(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
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

    def _time(self, key: str) -> time:
        hh, mm = str(self.config[key]).split(":")
        return time(int(hh), int(mm))

    def _in_rth(self, t: time) -> bool:
        return self._time("rth_start") <= t < time(16, 0)

    def _break_num_after_or(self, t: time) -> int:
        start = self._time("or_end")
        return max(0, int(((t.hour * 60 + t.minute) - (start.hour * 60 + start.minute)) / 5) + 1)


def _parse_dt(ts: str) -> datetime:
    value = str(ts)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _session_expiry(ts: str) -> str:
    if len(str(ts)) >= 10:
        return str(ts)[:10] + "T15:59:00"
    try:
        return date.fromisoformat(str(ts)).isoformat() + "T15:59:00"
    except ValueError:
        return str(ts)
