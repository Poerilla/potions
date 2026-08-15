"""Canonical v2d — fade the OR breakout (logical inverse of v2b).

Session flow (configurable clock; default NY RTH):

1. Build opening range ``rth_start``–``or_end``.
2. Detect break of OR high (+1 tick) or OR low (−1 tick).
3. Arm a **stop** fade back through the broken boundary (±1 tick):
   - Upside break → sell stop at ``or_high - tick``
   - Downside break → buy stop at ``or_low + tick``
4. On fill (flat sizing, default 1 unit):
   - Target = opposite OR boundary
   - Stop = broken edge ± 1R (where v2b's breakout target would be)
5. Bracket-then-reverse: max 1 fade-Long + 1 fade-Short per session.
6. Flatten at ``eod_cutoff``.

Same-bar rule: do not fill a fade on the bar that registered its breakout.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class V2DFadeStrategy(StrategyPlugin):
    strategy_type = "v2d_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 1,
            "rth_start": "09:30",
            "or_end": "09:45",
            "eod_cutoff": "15:55",
            "session_end": "16:00",
            "use_regime_filter": True,
            "require_regime_dates": False,
            "regime_dates": [],
            "record_levels": False,
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._regime_dates = set(str(x) for x in self.config.get("regime_dates", []))

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "1m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_1m_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "direction": "Long" if fill.side == "buy" else "Short",
                    "entry_price": float(fill.price),
                    "entry_qty": int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = trade["direction"]
            state["phase"] = "in_trade"
            # Clear the matching armed flag for this direction.
            if trade["direction"] == "Long":
                state["armed_long"] = False
            else:
                state["armed_short"] = False
            self._commit_state(state)
            return StrategyActions(self._exit_orders(fill.trade_id, trade["direction"], state), [], [], [], [])

        if role in {"stop", "tp", "eod_close", "eod"}:
            direction = str(trade.get("direction") or state.get("active_direction") or "")
            trade["status"] = "closed"
            state["current_leg_open"] = False
            state["active_trade_id"] = ""
            state["active_direction"] = ""
            if direction == "Long":
                state["traded_long"] = True
                state["armed_long"] = False
            elif direction == "Short":
                state["traded_short"] = True
                state["armed_short"] = False
            if state.get("traded_long") and state.get("traded_short"):
                state["done"] = True
                state["phase"] = "done"
            else:
                state["phase"] = "watching"
            self._commit_state(state)
            return StrategyActions([], self._cancel_reduce_orders(context, fill.trade_id), [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_1m_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
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
        tick = float(self.config.get("tick_size") or 0.25)

        if not self._in_session(t):
            self._commit_state(state)
            return StrategyActions.empty()

        if t >= self._time("eod_cutoff"):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eod_close", order_type="market_close"))
            state["done"] = True
            state["phase"] = "eod"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if t < self._time("or_end"):
            state["or_count"] = int(state.get("or_count", 0)) + 1
            state["or_high"] = bar.high if state.get("or_high") is None else max(float(state["or_high"]), bar.high)
            state["or_low"] = bar.low if state.get("or_low") is None else min(float(state["or_low"]), bar.low)
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            # Finalize OR once we have reached or_end on next bars; also allow early finalize at 15 bars.
            if int(state["or_count"]) >= 15 and not state.get("or_finalized"):
                state["or_finalized"] = True
                state["regime_ok"] = self._regime_ok(session)
                state["phase"] = "watching" if state["regime_ok"] else "regime_skip"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if not state.get("or_finalized"):
            state["or_finalized"] = True
            state["regime_ok"] = self._regime_ok(session)
            state["phase"] = "watching" if state["regime_ok"] else "regime_skip"

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if state.get("done") or not state.get("regime_ok") or not state.get("or_finalized"):
            self._commit_state(state)
            return StrategyActions.empty()

        or_high = _to_float(state.get("or_high"))
        or_low = _to_float(state.get("or_low"))
        if or_high is None or or_low is None or or_high <= or_low:
            self._commit_state(state)
            return StrategyActions.empty()
        r = or_high - or_low

        # Detect breaks. Resting fade stops go live after this bar (same-bar skip).
        new_up = False
        new_down = False
        if not state.get("long_break_done") and bar.high >= or_high + tick:
            state["long_break_done"] = True
            new_up = True
            if not state.get("traded_short"):
                state["armed_short"] = True
        if not state.get("short_break_done") and bar.low <= or_low - tick:
            state["short_break_done"] = True
            new_down = True
            if not state.get("traded_long"):
                state["armed_long"] = True

        if context.position_quantity != 0 or state.get("current_leg_open"):
            self._commit_state(state)
            return StrategyActions.empty()

        # Already have a resting fade stop — wait for fill / cancel.
        if self._has_open_entry_order(context):
            self._commit_state(state)
            return StrategyActions.empty()

        # Place at most one resting fade stop when newly armed (or soft-armed from prior).
        side_break = ""
        if new_up and new_down:
            mid = (or_high + or_low) / 2.0
            side_break = "up" if bar.open >= mid else "down"
        elif new_up and state.get("armed_short") and not state.get("traded_short"):
            side_break = "up"
        elif new_down and state.get("armed_long") and not state.get("traded_long"):
            side_break = "down"
        elif (not new_up) and (not new_down):
            # Prior soft-arm without resting order yet (e.g. after opposite leg closed).
            if state.get("armed_short") and not state.get("traded_short"):
                side_break = "up"
            elif state.get("armed_long") and not state.get("traded_long"):
                side_break = "down"

        if side_break:
            fade = self._arm_fade(bar.ts, state, or_high, or_low, r, tick, side_break)
            if fade is not None:
                orders.append(fade)
                state["phase"] = "fade_armed"
                if not bool(self.config.get("suppress_alerts")):
                    alerts.append(
                        Alert.create(
                            self.instance.strategy_id,
                            "info",
                            "v2d_fade armed after %s break" % side_break,
                        )
                    )

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _arm_fade(
        self,
        ts: str,
        state: Dict[str, Any],
        or_high: float,
        or_low: float,
        r: float,
        tick: float,
        side_break: str,
    ) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 1)
        if qty <= 0:
            return None
        trade_id = self._new_trade_id(state)
        if side_break == "up":
            direction = "Short"
            side = "sell"
            entry = or_high - tick
            stop = or_high + r
            tp = or_low
            state["armed_short"] = False  # resting order replaces soft arm
        elif side_break == "down":
            direction = "Long"
            side = "buy"
            entry = or_low + tick
            stop = or_low - r
            tp = or_high
            state["armed_long"] = False
        else:
            return None

        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "break_side": side_break,
            "or_high": or_high,
            "or_low": or_low,
            "r": r,
            "entry": entry,
            "stop": stop,
            "tp": tp,
            "entry_qty": qty,
        }
        state["active_trade_id"] = trade_id
        state["active_direction"] = direction
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="stop",
            quantity=qty,
            stop_price=entry,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=self._session_expiry(ts),
        )

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp = _to_float(trade.get("tp"))
        qty = int(trade.get("entry_qty") or self.config.get("entry_qty") or 1)
        if stop is None or tp is None or qty <= 0:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = self._session_expiry(str(state.get("session_date", "")))
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=stop,
                reason="stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="stop",
                expires_after_ts=expiry,
            ),
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=qty,
                limit_price=tp,
                reason="tp",
                requires_verification=False,
                reduce_only=True,
                bracket_role="tp",
                expires_after_ts=expiry,
            ),
        ]

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("session_date", "")
        state.setdefault("or_count", 0)
        state.setdefault("or_high", None)
        state.setdefault("or_low", None)
        state.setdefault("or_finalized", False)
        state.setdefault("regime_ok", False)
        state.setdefault("phase", "")
        state.setdefault("done", False)
        state.setdefault("long_break_done", False)
        state.setdefault("short_break_done", False)
        state.setdefault("armed_long", False)
        state.setdefault("armed_short", False)
        state.setdefault("traded_long", False)
        state.setdefault("traded_short", False)
        state.setdefault("trade_seq", 0)
        state.setdefault("current_leg_open", False)
        state.setdefault("active_trade_id", "")
        state.setdefault("active_direction", "")
        state.setdefault("trades", {})
        return state

    def _fresh_session_state(self, session: str) -> Dict[str, Any]:
        return {
            "session_date": session,
            "or_count": 0,
            "or_high": None,
            "or_low": None,
            "or_finalized": False,
            "regime_ok": False,
            "phase": "building_or",
            "done": False,
            "long_break_done": False,
            "short_break_done": False,
            "armed_long": False,
            "armed_short": False,
            "traded_long": False,
            "traded_short": False,
            "trade_seq": 0,
            "current_leg_open": False,
            "active_trade_id": "",
            "active_direction": "",
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

    def _regime_ok(self, session: str) -> bool:
        if not bool(self.config.get("use_regime_filter", True)):
            return True
        if not self._regime_dates:
            return not bool(self.config.get("require_regime_dates", False))
        return session in self._regime_dates

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_%s_%02d" % (
            self.instance.strategy_id,
            str(state.get("session_date", "")).replace("-", ""),
            int(state["trade_seq"]),
        )

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
            bracket_role=reason,
            live_after_ts=ts,
        )

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2d_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2d_eod")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry_order(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        high = _to_float(state.get("or_high"))
        low = _to_float(state.get("or_low"))
        if high is None or low is None:
            return []
        return [
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "or_high", high, ts),
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "or_low", low, ts),
        ]

    def _time(self, key: str) -> time:
        hh, mm = str(self.config[key]).split(":")
        return time(int(hh), int(mm))

    def _in_session(self, t: time) -> bool:
        return self._time("rth_start") <= t < self._time("session_end")

    def _session_expiry(self, ts: str) -> str:
        cutoff = str(self.config.get("eod_cutoff") or "15:55")
        if len(str(ts)) >= 10:
            return str(ts)[:10] + "T%s:00" % cutoff
        try:
            return date.fromisoformat(str(ts)).isoformat() + "T%s:00" % cutoff
        except ValueError:
            return str(ts)


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
