"""OR break → N×R extension → fade (mean reversion).

Session flow (NY RTH):

1. Build opening range **09:30–09:45**.
2. Detect the **first** break of OR high or OR low (same-bar dual break → skip).
3. Arm a **limit** fade at the ``fade_r_mult`` extension (default **2R**):
   - Upside break → sell limit at ``or_high + fade_r_mult * R``
   - Downside break → buy limit at ``or_low - fade_r_mult * R``
4. On fill (flat sizing, default 1 unit):
   - Stop = ``stop_r_mult * R`` beyond the fade entry (default **1R**)
   - Target = **OR boundary** (mean reversion)

Optional ``tp_mode``:

- ``or_boundary`` (default): single TP at the broken OR edge
- ``one_r``: single TP at the 1R level (halfway back from boundary geometry)
- ``split``: requires ``entry_qty >= 2`` — half at 1R, half at OR boundary
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class Or2RFadeStrategy(StrategyPlugin):
    strategy_type = "or_2r_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 1,
            "fade_r_mult": 2.0,  # entry at OR_edge ± fade_r_mult * R
            "stop_r_mult": 1.0,  # SL distance beyond entry in R
            "tp_mode": "or_boundary",  # or_boundary | one_r | split
            "rth_start": "09:30",
            "or_end": "09:45",
            "eod_cutoff": "15:59",
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
            state["fade_armed"] = False
            self._commit_state(state)
            return StrategyActions(self._exit_orders(fill.trade_id, trade["direction"], state), [], [], [], [])

        if role in {"stop", "tp", "tp_1r", "tp_or", "eod_close", "eod"}:
            trade["status"] = "closed"
            state["current_leg_open"] = False
            state["done"] = True
            state["phase"] = "done"
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

        if not self._in_rth(t):
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
            if int(state["or_count"]) >= 15 and not state.get("or_finalized"):
                state["or_finalized"] = True
                state["regime_ok"] = self._regime_ok(session)
                state["phase"] = "watching_break" if state["regime_ok"] else "regime_skip"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if state.get("done") or not state.get("regime_ok") or not state.get("or_finalized"):
            self._commit_state(state)
            return StrategyActions.empty()

        if context.position_quantity != 0 or state.get("current_leg_open"):
            self._commit_state(state)
            return StrategyActions.empty()

        # Already have a resting fade limit.
        if state.get("fade_armed") or self._has_open_entry_order(context):
            self._commit_state(state)
            return StrategyActions.empty()

        or_high = _to_float(state.get("or_high"))
        or_low = _to_float(state.get("or_low"))
        if or_high is None or or_low is None or or_high <= or_low:
            self._commit_state(state)
            return StrategyActions.empty()

        r = or_high - or_low
        broke_up = bar.high >= or_high
        broke_down = bar.low <= or_low
        if not state.get("break_side"):
            if broke_up and broke_down:
                # Ambiguous same-bar dual break — skip the session.
                state["done"] = True
                state["phase"] = "dual_break_skip"
                self._commit_state(state)
                return StrategyActions.empty()
            if broke_up:
                state["break_side"] = "up"
                state["phase"] = "fade_armed"
            elif broke_down:
                state["break_side"] = "down"
                state["phase"] = "fade_armed"
            else:
                self._commit_state(state)
                return StrategyActions.empty()

            fade = self._arm_fade(bar.ts, state, or_high, or_low, r)
            if fade is not None:
                orders.append(fade)
                state["fade_armed"] = True
                if not bool(self.config.get("suppress_alerts")):
                    alerts.append(
                        Alert.create(
                            self.instance.strategy_id,
                            "info",
                            "or_2r_fade armed after %s break" % state["break_side"],
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
    ) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 1)
        if qty <= 0:
            return None
        fade_mult = float(self.config.get("fade_r_mult") or 2.0)
        stop_mult = float(self.config.get("stop_r_mult") or 1.0)
        if fade_mult <= 0 or stop_mult <= 0:
            return None
        trade_id = self._new_trade_id(state)
        side_break = str(state.get("break_side") or "")
        if side_break == "up":
            # Fade short at +fade_mult R.
            direction = "Short"
            side = "sell"
            entry = or_high + fade_mult * r
            stop = entry + stop_mult * r
            tp_1r = or_high + r
            tp_or = or_high
        elif side_break == "down":
            direction = "Long"
            side = "buy"
            entry = or_low - fade_mult * r
            stop = entry - stop_mult * r
            tp_1r = or_low - r
            tp_or = or_low
        else:
            return None

        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "break_side": side_break,
            "or_high": or_high,
            "or_low": or_low,
            "r": r,
            "fade_r_mult": fade_mult,
            "stop_r_mult": stop_mult,
            "entry": entry,
            "stop": stop,
            "tp_1r": tp_1r,
            "tp_or": tp_or,
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
            order_type="limit",
            quantity=qty,
            limit_price=entry,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=_session_expiry(ts),
        )

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp_1r = _to_float(trade.get("tp_1r"))
        tp_or = _to_float(trade.get("tp_or"))
        qty = int(trade.get("entry_qty") or self.config.get("entry_qty") or 1)
        if stop is None or tp_1r is None or tp_or is None or qty <= 0:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _session_expiry(str(state.get("session_date", "")))
        out: List[OrderIntent] = [
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
            )
        ]
        mode = str(self.config.get("tp_mode") or "or_boundary")
        if mode == "one_r":
            out.append(self._tp_limit(trade_id, exit_side, qty, tp_1r, "tp_1r", expiry))
        elif mode == "split" and qty >= 2:
            q1 = qty // 2
            q2 = qty - q1
            out.append(self._tp_limit(trade_id, exit_side, q1, tp_1r, "tp_1r", expiry))
            out.append(self._tp_limit(trade_id, exit_side, q2, tp_or, "tp_or", expiry))
        else:
            # Default: whole size to OR boundary (2R reward).
            out.append(self._tp_limit(trade_id, exit_side, qty, tp_or, "tp_or", expiry))
        return out

    def _tp_limit(
        self,
        trade_id: str,
        exit_side: str,
        qty: int,
        price: float,
        role: str,
        expiry: str,
    ) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=exit_side,
            order_type="limit",
            quantity=qty,
            limit_price=price,
            reason=role,
            requires_verification=False,
            reduce_only=True,
            bracket_role=role,
            expires_after_ts=expiry,
        )

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
        state.setdefault("break_side", "")
        state.setdefault("fade_armed", False)
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
            "break_side": "",
            "fade_armed": False,
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
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "or2r_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "or2r_eod")
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

    def _in_rth(self, t: time) -> bool:
        return self._time("rth_start") <= t < time(16, 0)


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
