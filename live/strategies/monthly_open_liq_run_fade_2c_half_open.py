"""2-contract liq-run fade: half + open targets, fixed $ risk SL, optional reverse.

Primary:
  - Resting limit qty=2 at plan.entry after arm_after_ts
  - Stop qty=2 at entry ± primary_stop_pts (default risk $1000 → 25 pts)
  - Target half qty=1 at mid(entry, month_open); target open qty=1 at month_open

Reverse (config ``enable_reverse``):
  - Only after a **full initial stop** (position flat with no half taken)
  - Limit opposite at stop price; target = |primary_entry − month_open|
  - Reverse SL = reverse_stop_pts (default risk $2000 → 50 pts); qty=2
  - Armed in ``on_fill`` immediately (does not wait for next bar)

Strategy type: ``monthly_open_liq_run_fade_2c_half_open``
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


def _f(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MonthlyOpenLiqRunFade2cHalfOpenStrategy(StrategyPlugin):
    strategy_type = "monthly_open_liq_run_fade_2c_half_open"
    version = "v2"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 2,
            "qty_half": 1,
            "qty_open": 1,
            "timeframe": "1m",
            "month_plans": {},
            # Primary fade risk (default $1k → 25 pts @ 2×$20)
            "risk_usd": 1000.0,
            "primary_risk_usd": 1000.0,
            # Reverse continuation risk (default $2k → 50 pts)
            "reverse_risk_usd": 2000.0,
            "point_value": 20.0,
            "enable_reverse": True,
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "1m")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        mode = str(trade.get("mode") or state.get("mode") or "primary")
        plan = dict(state.get("plan") or {})
        month_end = str(plan.get("month_end_ts") or "")

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "direction": "Long" if fill.side == "buy" else "Short",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                    "mode": mode,
                }
            )
            state["in_trade"] = True
            state["limit_armed"] = False
            state["active_trade_id"] = fill.trade_id
            state["half_done"] = False
            state["open_done"] = False
            state["primary_rem"] = int(fill.quantity)
            state["phase"] = "in_trade_%s" % mode
            if mode == "primary":
                state["primary_entry"] = float(fill.price)
                state["primary_side"] = "long" if fill.side == "buy" else "short"
                orders = self._primary_brackets(fill.trade_id, str(trade["direction"]), state)
            else:
                orders = self._reverse_brackets(fill.trade_id, str(trade["direction"]), state)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        # PaperBroker fill.reason is bracket_role → "target" / "stop" (not intent reason)
        if role in {"target_half", "target_open", "target", "rev_target"}:
            if mode == "reverse":
                rem = max(0, int(state.get("primary_rem") or 0) - int(fill.quantity))
                state["primary_rem"] = rem
                if rem <= 0 or int(context.position_quantity) == 0:
                    trade["status"] = "closed"
                    trade["exit_ts"] = fill.ts
                    trade["exit_reason"] = "rev_target"
                    state["in_trade"] = False
                    state["active_trade_id"] = ""
                    state["reverse_done"] = True
                    state["done"] = True
                    state["phase"] = "done_reverse"
                    cancels = self._cancel_reduce(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

            if not state.get("half_done"):
                state["half_done"] = True
                rem = max(0, int(state.get("primary_rem") or 0) - int(fill.quantity))
                state["primary_rem"] = rem
                if rem > 0:
                    cancels = self._cancel_reduce(context, fill.trade_id)
                    direction = str(trade.get("direction") or "")
                    orders = self._remaining_after_half(fill.trade_id, direction, state, rem)
                    self._commit_state(state)
                    return StrategyActions(orders, cancels, [], [], [])
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = "target_half"
                state["in_trade"] = False
                state["active_trade_id"] = ""
                state["done"] = True
                state["phase"] = "done_primary"
                cancels = self._cancel_reduce(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

            rem = max(0, int(state.get("primary_rem") or 0) - int(fill.quantity))
            state["primary_rem"] = rem
            if rem <= 0 or int(context.position_quantity) == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = "target_open"
                state["open_done"] = True
                state["in_trade"] = False
                state["active_trade_id"] = ""
                state["done"] = True
                state["phase"] = "done_primary"
                cancels = self._cancel_reduce(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])
            self._commit_state(state)
            return StrategyActions.empty()

        if role in {"stop", "rev_stop", "eom", "flatten"}:
            rem = max(0, int(state.get("primary_rem") or 0) - int(fill.quantity))
            state["primary_rem"] = rem
            flat = rem <= 0 or int(context.position_quantity) == 0

            if flat:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels = self._cancel_reduce(context, fill.trade_id)

                if mode == "primary" and role == "stop" and not state.get("half_done"):
                    if bool(self.config.get("enable_reverse")) and not state.get("reverse_done"):
                        stop_px = (
                            _f(trade.get("stop"))
                            or _f(state.get("primary_stop"))
                            or float(fill.price)
                        )
                        state["reverse_entry"] = stop_px
                        state["pending_reverse"] = True
                        state["done"] = False
                        state["phase"] = "arm_reverse"
                        rev_orders, rev_ok = self._build_reverse_entry(
                            state, live_after_ts=fill.ts, month_end=month_end
                        )
                        if rev_ok:
                            orders.extend(rev_orders)
                            state["pending_reverse"] = False
                            state["limit_armed"] = True
                            state["phase"] = "armed_reverse"
                    else:
                        state["done"] = True
                        state["phase"] = "done_after_stop"
                elif mode == "reverse":
                    state["reverse_done"] = True
                    state["done"] = True
                    state["phase"] = "done_reverse"
                else:
                    state["done"] = True
                    state["phase"] = "done_%s" % role

                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])

            self._commit_state(state)
            return StrategyActions.empty()

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_bar(self, bar, context: StrategyContext) -> StrategyActions:
        dt = pd.Timestamp(bar.ts)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        ny = dt.tz_convert("America/New_York")
        month_key = "%04d-%02d" % (int(ny.year), int(ny.month))
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if state.get("month_key") != month_key:
            if context.position_quantity != 0 or state.get("in_trade"):
                cancels.extend(self._cancel_all(context))
                if context.position_quantity != 0:
                    orders.append(self._flatten(context, bar.ts, "eom"))
            state = self._fresh_month(month_key, prior=dict(state))
            state["plan"] = dict((self.config.get("month_plans") or {}).get(month_key) or {})

        plan = dict(state.get("plan") or {})
        if not plan:
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        arm_after = str(plan.get("arm_after_ts") or "")
        month_end = str(plan.get("month_end_ts") or "")
        if month_end and bar.ts >= month_end:
            cancels.extend(self._cancel_all(context))
            if context.position_quantity != 0:
                orders.append(self._flatten(context, bar.ts, "eom"))
            state["done"] = True
            state["pending_reverse"] = False
            state["phase"] = "month_end"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if state.get("done") and not state.get("pending_reverse"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if arm_after and bar.ts < arm_after:
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        month_open = _f(plan.get("month_open"))
        entry = _f(plan.get("entry"))
        side_key = str(plan.get("side") or "")
        if month_open is None or entry is None or side_key not in {"long", "short"}:
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if (
            state.get("pending_reverse")
            and not state.get("in_trade")
            and not state.get("limit_armed")
            and not self._has_entry(context)
            and not state.get("reverse_done")
        ):
            rev_orders, rev_ok = self._build_reverse_entry(
                state, live_after_ts=bar.ts, month_end=month_end
            )
            if rev_ok:
                orders.extend(rev_orders)
                state["pending_reverse"] = False
                state["limit_armed"] = True
                state["phase"] = "armed_reverse"
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])
            state["pending_reverse"] = False
            state["done"] = True

        if (
            not state.get("in_trade")
            and not state.get("limit_armed")
            and not self._has_entry(context)
            and not state.get("primary_armed_once")
            and not state.get("done")
            and not state.get("pending_reverse")
            and state.get("mode", "primary") == "primary"
        ):
            tid = self._new_trade_id(state)
            stop_pts = self._primary_stop_pts(plan)
            if side_key == "long":
                stop = entry - stop_pts
                target_half = 0.5 * (entry + month_open)
            else:
                stop = entry + stop_pts
                target_half = 0.5 * (entry + month_open)
            state["trades"][tid] = {
                "direction": "Long" if side_key == "long" else "Short",
                "side_key": side_key,
                "status": "armed",
                "mode": "primary",
                "entry": float(entry),
                "stop": float(stop),
                "target_half": float(target_half),
                "target": float(month_open),
            }
            state["primary_stop"] = float(stop)
            state["mode"] = "primary"
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=tid,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="buy" if side_key == "long" else "sell",
                    order_type="limit",
                    quantity=int(self.config.get("entry_qty") or 2),
                    limit_price=float(entry),
                    reason="entry",
                    requires_verification=True,
                    bracket_role="entry",
                    live_after_ts=bar.ts,
                    expires_after_ts=month_end,
                )
            )
            state["limit_armed"] = True
            state["primary_armed_once"] = True
            state["phase"] = "armed_primary"

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    def _primary_stop_pts(self, plan: Dict[str, Any]) -> float:
        if plan.get("primary_stop_pts") is not None:
            sp = _f(plan.get("primary_stop_pts"))
            if sp and sp > 0:
                return sp
        risk = float(
            self.config.get("primary_risk_usd")
            or self.config.get("risk_usd")
            or 1000.0
        )
        qty = int(self.config.get("entry_qty") or 2)
        pv = float(self.config.get("point_value") or 20.0)
        return risk / max(qty * pv, 1e-9)

    def _reverse_stop_pts(self, plan: Dict[str, Any]) -> float:
        if plan.get("reverse_stop_pts") is not None:
            sp = _f(plan.get("reverse_stop_pts"))
            if sp and sp > 0:
                return sp
        risk = float(self.config.get("reverse_risk_usd") or 2000.0)
        qty = int(self.config.get("entry_qty") or 2)
        pv = float(self.config.get("point_value") or 20.0)
        return risk / max(qty * pv, 1e-9)

    def _build_reverse_entry(
        self, state: Dict[str, Any], *, live_after_ts: str, month_end: str
    ) -> Tuple[List[OrderIntent], bool]:
        plan = dict(state.get("plan") or {})
        month_open = _f(plan.get("month_open"))
        rev_entry = _f(state.get("reverse_entry"))
        prim_entry = _f(state.get("primary_entry"))
        prim_side = str(state.get("primary_side") or "")
        if (
            rev_entry is None
            or prim_entry is None
            or month_open is None
            or prim_side not in {"long", "short"}
        ):
            return [], False
        rev_side = "short" if prim_side == "long" else "long"
        open_dist = abs(prim_entry - month_open)
        if open_dist <= 0:
            return [], False
        stop_pts = self._reverse_stop_pts(plan)
        tid = self._new_trade_id(state)
        if rev_side == "short":
            stop = rev_entry + stop_pts
            target = rev_entry - open_dist
        else:
            stop = rev_entry - stop_pts
            target = rev_entry + open_dist
        state["trades"][tid] = {
            "direction": "Long" if rev_side == "long" else "Short",
            "side_key": rev_side,
            "status": "armed",
            "mode": "reverse",
            "entry": float(rev_entry),
            "stop": float(stop),
            "target": float(target),
            "open_dist": float(open_dist),
        }
        state["mode"] = "reverse"
        order = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=tid,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy" if rev_side == "long" else "sell",
            order_type="limit",
            quantity=int(self.config.get("entry_qty") or 2),
            limit_price=float(rev_entry),
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=live_after_ts,
            expires_after_ts=month_end,
        )
        return [order], True

    def _primary_brackets(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        stop = _f(trade.get("stop"))
        half = _f(trade.get("target_half"))
        open_t = _f(trade.get("target"))
        qty = int(self.config.get("entry_qty") or 2)
        qh = int(self.config.get("qty_half") or 1)
        qo = int(self.config.get("qty_open") or 1)
        fill = _f(trade.get("entry_price"))
        stop_pts = self._primary_stop_pts(plan)
        if fill is not None and open_t is not None:
            if direction == "Long":
                stop = fill - stop_pts
                half = 0.5 * (fill + open_t)
            else:
                stop = fill + stop_pts
                half = 0.5 * (fill + open_t)
            trade["stop"] = stop
            trade["target_half"] = half
            state["primary_stop"] = stop
            state["primary_entry"] = fill
        if stop is None or half is None or open_t is None:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=float(stop),
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
                quantity=qh,
                limit_price=float(half),
                reason="target_half",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                expires_after_ts=expiry,
            ),
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=qo,
                limit_price=float(open_t),
                reason="target_open",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                expires_after_ts=expiry,
            ),
        ]

    def _remaining_after_half(
        self, trade_id: str, direction: str, state: Dict[str, Any], rem: int
    ) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        stop = _f(trade.get("stop"))
        open_t = _f(trade.get("target"))
        if stop is None or open_t is None or rem <= 0:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=rem,
                stop_price=float(stop),
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
                quantity=rem,
                limit_price=float(open_t),
                reason="target_open",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                expires_after_ts=expiry,
            ),
        ]

    def _reverse_brackets(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        qty = int(self.config.get("entry_qty") or 2)
        fill = _f(trade.get("entry_price"))
        stop_pts = self._reverse_stop_pts(plan)
        open_dist = _f(trade.get("open_dist"))
        stop = _f(trade.get("stop"))
        target = _f(trade.get("target"))
        if fill is not None and open_dist is not None and open_dist > 0:
            if direction == "Long":
                stop = fill - stop_pts
                target = fill + open_dist
            else:
                stop = fill + stop_pts
                target = fill - open_dist
            trade["stop"] = stop
            trade["target"] = target
        if stop is None or target is None:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=float(stop),
                reason="rev_stop",
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
                limit_price=float(target),
                reason="rev_target",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                expires_after_ts=expiry,
            ),
        ]

    def _flatten(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        trade_id = (
            str(context.strategy_open_orders[0].trade_id)
            if context.strategy_open_orders
            else new_id("trade")
        )
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
            bracket_role="flatten",
            live_after_ts=ts,
        )

    def _has_entry(self, context: StrategyContext) -> bool:
        for o in context.strategy_open_orders:
            if o.bracket_role == "entry" and not bool(o.reduce_only):
                return True
        return False

    def _cancel_all(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "month_roll")
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and bool(o.reduce_only):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "position_flat"))
        return out

    def _fresh_month(self, month_key: str, *, prior: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prior = prior or {}
        return {
            "month_key": month_key,
            "plan": {},
            "in_trade": False,
            "limit_armed": False,
            "primary_armed_once": False,
            "pending_reverse": False,
            "reverse_done": False,
            "half_done": False,
            "open_done": False,
            "done": False,
            "mode": "primary",
            "phase": "flat",
            "active_trade_id": "",
            "primary_entry": None,
            "primary_side": "",
            "primary_stop": None,
            "primary_rem": 0,
            "reverse_entry": None,
            "trade_seq": int(prior.get("trade_seq") or 0),
            "trades": {},
        }

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "month_key" not in raw:
            raw = self._fresh_month("")
        if "trades" not in raw or not isinstance(raw["trades"], dict):
            raw["trades"] = {}
        self.state = raw
        return raw

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {"status": "new"}
        return trades[trade_id]

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        seq = int(state.get("trade_seq") or 0) + 1
        state["trade_seq"] = seq
        mk = str(state.get("month_key") or "xx")
        return "%s_%s_t%d" % (self.instance.strategy_id, mk.replace("-", ""), seq)
