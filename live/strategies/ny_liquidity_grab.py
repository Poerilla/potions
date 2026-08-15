"""NY liquidity grab — London session OCO at prior NY RTH high/low.

Thesis: London seeks the prior New York cash-session liquidity pool.
After London open, wait until price **trades into** the prior NY RTH range
(strictly between high and low), then rest an OCO pair of limits at those
boundaries. First boundary touch fills; the other leg cancels.

  - Touch NY low first  → Long at NY low, stop = low − R, target = high (+ optional beyond)
  - Touch NY high first → Short at NY high, stop = high + R, target = low (− optional beyond)

Risk = prior NY range ``R = high − low``. Default 1 lot, TP at opposite boundary (1R).
``tp_r_mult > 1`` aims beyond the opposite boundary.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class NyLiquidityGrabStrategy(StrategyPlugin):
    strategy_type = "ny_liquidity_grab"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.00001,
            "entry_qty": 1,
            "tp_r_mult": 1.0,  # 1.0 = opposite NY boundary; >1 aims beyond
            "rth_start": "03:00",  # London arm window start
            "eod_cutoff": "11:59",
            "use_regime_filter": True,
            "require_regime_dates": False,
            "regime_dates": [],
            # session_date -> {"high": float, "low": float, "ny_session": "YYYY-MM-DD"}
            "session_ny_ranges": {},
            "min_range_ticks": 10,
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
        role = str(fill.reason or "")

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            trade.update(
                {
                    "status": "open",
                    "direction": direction,
                    "entry_price": float(fill.price),
                    "entry_qty": int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = direction
            state["armed"] = False
            state["phase"] = "in_trade"
            self._commit_state(state)
            return StrategyActions(
                self._exit_orders(fill.trade_id, direction, state, fill.ts),
                self._cancel_other_entries(context, fill.trade_id),
                [],
                [],
                [],
            )

        if role in {"stop", "tp", "eod_close", "eod"}:
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

        if not self._in_session(t):
            self._commit_state(state)
            return StrategyActions.empty()

        if t >= self._time("eod_cutoff"):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eod_close"))
            state["done"] = True
            state["phase"] = "eod"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("done") or state.get("current_leg_open"):
            self._commit_state(state)
            return StrategyActions.empty()

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if state.get("armed") or self._has_open_entry_order(context):
            self._commit_state(state)
            return StrategyActions.empty()

        if not self._regime_ok(session):
            state["phase"] = "regime_skip"
            state["done"] = True
            self._commit_state(state)
            return StrategyActions.empty()

        ny = self._ny_range(session)
        if ny is None:
            state["phase"] = "no_ny_range"
            state["done"] = True
            self._commit_state(state)
            return StrategyActions.empty()

        ny_high, ny_low, r = ny
        tick = float(self.config["tick_size"])
        min_ticks = max(1, int(self.config.get("min_range_ticks") or 10))
        if r < min_ticks * tick:
            state["phase"] = "range_too_small"
            state["done"] = True
            self._commit_state(state)
            return StrategyActions.empty()

        state["ny_high"] = ny_high
        state["ny_low"] = ny_low
        state["ny_range"] = r

        # Arm only once close is strictly inside the prior NY range so both OCO
        # limits rest (non-marketable). If London opens outside, keep watching
        # until a later bar closes into (ny_low, ny_high).
        px = float(bar.close)
        if not (ny_low < px < ny_high):
            state["phase"] = "waiting_for_ny_range"
            self._commit_state(state)
            return StrategyActions.empty()

        trade_id = self._new_trade_id(state)
        oco = "%s_ny_grab_oco" % trade_id
        qty = int(self.config["entry_qty"])
        state["trades"][trade_id] = {
            "status": "armed",
            "ny_high": ny_high,
            "ny_low": ny_low,
            "ny_range": r,
            "entry_qty": qty,
        }
        # Buy limit at prior NY low (liquidity grab long); sell limit at NY high.
        orders.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="buy",
                order_type="limit",
                quantity=qty,
                limit_price=ny_low,
                reason="entry",
                requires_verification=False,
                bracket_role="entry",
                oco_group=oco,
                live_after_ts=bar.ts,
            )
        )
        orders.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="sell",
                order_type="limit",
                quantity=qty,
                limit_price=ny_high,
                reason="entry",
                requires_verification=False,
                bracket_role="entry",
                oco_group=oco,
                live_after_ts=bar.ts,
            )
        )
        state["armed"] = True
        state["active_trade_id"] = trade_id
        state["phase"] = "armed"
        if not bool(self.config.get("suppress_alerts")):
            alerts.append(Alert.create(self.instance.strategy_id, "info", "ny_liquidity_grab OCO armed"))
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any], ts: str) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        ny_high = float(trade.get("ny_high") if trade.get("ny_high") is not None else state.get("ny_high"))
        ny_low = float(trade.get("ny_low") if trade.get("ny_low") is not None else state.get("ny_low"))
        r = float(trade.get("ny_range") if trade.get("ny_range") is not None else state.get("ny_range") or (ny_high - ny_low))
        qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        tp_mult = float(self.config.get("tp_r_mult") or 1.0)
        exit_side = "sell" if direction == "Long" else "buy"
        if direction == "Long":
            stop_price = ny_low - r
            # Beyond opposite: high + (tp_mult-1)*R
            tp_price = ny_low + tp_mult * r
        else:
            stop_price = ny_high + r
            tp_price = ny_high - tp_mult * r
        expiry = _session_expiry(str(state.get("session_date") or ""), self._time("eod_cutoff"))
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=stop_price,
                reason="stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="stop",
                expires_after_ts=expiry,
                live_after_ts=ts,
            ),
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=qty,
                limit_price=tp_price,
                reason="tp",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                expires_after_ts=expiry,
                live_after_ts=ts,
            ),
        ]

    def _ny_range(self, session: str) -> Optional[tuple]:
        raw = (self.config.get("session_ny_ranges") or {}).get(session)
        if not raw:
            return None
        high = _to_float(raw.get("high") if isinstance(raw, dict) else None)
        low = _to_float(raw.get("low") if isinstance(raw, dict) else None)
        if high is None or low is None or high <= low:
            return None
        return high, low, high - low

    def _regime_ok(self, session: str) -> bool:
        if not bool(self.config.get("use_regime_filter")):
            return True
        if not self._regime_dates:
            return not bool(self.config.get("require_regime_dates"))
        return session in self._regime_dates

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("session_date", "")
        state.setdefault("armed", False)
        state.setdefault("done", False)
        state.setdefault("phase", "")
        state.setdefault("current_leg_open", False)
        state.setdefault("active_trade_id", "")
        state.setdefault("active_direction", "")
        state.setdefault("trade_seq", 0)
        state.setdefault("trades", {})
        state.setdefault("ny_high", None)
        state.setdefault("ny_low", None)
        state.setdefault("ny_range", None)
        return state

    def _fresh_session_state(self, session: str) -> Dict[str, Any]:
        return {
            "session_date": session,
            "armed": False,
            "done": False,
            "phase": "waiting",
            "current_leg_open": False,
            "active_trade_id": "",
            "active_direction": "",
            "trade_seq": 0,
            "trades": {},
            "ny_high": None,
            "ny_low": None,
            "ny_range": None,
        }

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        trade = trades.get(trade_id)
        if trade is None:
            trade = {}
            trades[trade_id] = trade
        return trade

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        session = str(state.get("session_date") or "nosession").replace("-", "")
        return "%s_%s_t%d" % (self.instance.strategy_id, session, state["trade_seq"])

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        trade_id = str(self._state().get("active_trade_id") or "eod")
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market_close",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts=ts,
        )

    def _cancel_other_entries(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "ny_grab_oco_fill")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and not order.reduce_only
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "ny_grab_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "ny_grab_eod")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry_order(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        high = _to_float(state.get("ny_high"))
        low = _to_float(state.get("ny_low"))
        if high is None or low is None:
            return []
        return [
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "ny_high", high, ts),
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "ny_low", low, ts),
        ]

    def _time(self, key: str) -> time:
        hh, mm = str(self.config[key]).split(":")
        return time(int(hh), int(mm))

    def _in_session(self, t: time) -> bool:
        return self._time("rth_start") <= t < time(16, 0)

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state


def _parse_dt(ts: str) -> datetime:
    from pytz import timezone

    NY = timezone("America/New_York")
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


def _session_expiry(session: str, eod: time) -> str:
    from pytz import timezone

    NY = timezone("America/New_York")
    try:
        session_day = date.fromisoformat(str(session)[:10])
    except ValueError:
        return str(session)
    return NY.localize(datetime.combine(session_day, eod)).isoformat()
