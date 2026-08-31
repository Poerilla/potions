"""Monthly-open liquidity-run fade (1:1) with open-touch / post-TP re-entry.

Precomputed ``month_plans`` from the driver (HP months + detect_liquidity_run).
On ``timeframe`` bars (default **1m**):

- After ``arm_after_ts``: resting limit at ``entry`` (``p_liq``)
- On fill: stop at ``stop`` (full 1R), target at ``month_open``
- After **target**: re-arm limit immediately (TP @ open counts as arm)
- After **stop**: wait until price touches month open, then re-arm
- Unlimited re-entries until ``month_end_ts``; flatten at month end

Strategy type: ``monthly_open_liq_run_fade``
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


def _f(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MonthlyOpenLiqRunFadeStrategy(StrategyPlugin):
    strategy_type = "monthly_open_liq_run_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 10,
            "timeframe": "1m",
            "month_plans": {},
            "suppress_alerts": True,
            "max_reentries": 0,  # 0 = unlimited
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

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "direction": "Long" if fill.side == "buy" else "Short",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                }
            )
            state["in_trade"] = True
            state["limit_armed"] = False
            state["active_trade_id"] = fill.trade_id
            state["phase"] = "in_trade"
            orders = self._exit_bracket(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"target", "target_open", "stop", "eom", "flatten"}:
            if int(context.position_quantity) == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels = self._cancel_reduce(context, fill.trade_id)
                # Re-arm policy
                if role in {"target", "target_open"}:
                    # TP @ open arms next limit immediately
                    state["limit_armed"] = False
                    state["wait_open_touch"] = False
                    state["phase"] = "rearm_now"
                    state["n_reentries"] = int(state.get("n_reentries") or 0) + (
                        1 if int(state.get("n_fills") or 0) >= 1 else 0
                    )
                elif role == "stop":
                    state["wait_open_touch"] = True
                    state["phase"] = "wait_open"
                    state["n_reentries"] = int(state.get("n_reentries") or 0) + (
                        1 if int(state.get("n_fills") or 0) >= 1 else 0
                    )
                else:
                    state["phase"] = "flat"
                    state["wait_open_touch"] = False
                state["n_fills"] = int(state.get("n_fills") or 0) + 1
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_bar(self, bar, context: StrategyContext) -> StrategyActions:
        import pandas as pd

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
        if arm_after and bar.ts < arm_after:
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if month_end and bar.ts >= month_end:
            cancels.extend(self._cancel_all(context))
            if context.position_quantity != 0:
                orders.append(self._flatten(context, bar.ts, "eom"))
            state["done"] = True
            state["phase"] = "month_end"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if state.get("done"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        month_open = _f(plan.get("month_open"))
        entry = _f(plan.get("entry"))
        stop = _f(plan.get("stop"))
        side_key = str(plan.get("side") or "")  # long|short
        if month_open is None or entry is None or stop is None or side_key not in {"long", "short"}:
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        # Open-touch re-arm after stop
        if state.get("wait_open_touch") and not state.get("in_trade"):
            if float(bar.low) <= month_open <= float(bar.high):
                state["wait_open_touch"] = False
                state["phase"] = "rearm_now"

        max_re = int(self.config.get("max_reentries") or 0)
        n_re = int(state.get("n_reentries") or 0)
        # n_fills counts completed trades; first entry allowed when n_fills==0
        can_reenter = max_re <= 0 or n_re < max_re or int(state.get("n_fills") or 0) == 0

        want_arm = (
            not state.get("in_trade")
            and not state.get("wait_open_touch")
            and not state.get("limit_armed")
            and not self._has_entry(context)
            and can_reenter
            and (
                state.get("phase") in {"rearm_now", "armed", "flat", ""}
                or int(state.get("n_fills") or 0) == 0
            )
        )
        # First arm once past arm_after
        if int(state.get("n_fills") or 0) == 0 and not state.get("limit_armed") and not state.get("in_trade"):
            if not state.get("wait_open_touch"):
                want_arm = True

        if want_arm and can_reenter:
            # Cap: if max_reentries set and this would be reentry beyond cap
            if int(state.get("n_fills") or 0) > 0 and max_re > 0 and n_re >= max_re:
                want_arm = False

        if want_arm:
            tid = self._new_trade_id(state)
            direction = "Long" if side_key == "long" else "Short"
            state["trades"][tid] = {
                "direction": direction,
                "side_key": side_key,
                "status": "armed",
                "entry": float(entry),
                "stop": float(stop),
                "target": float(month_open),
            }
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=tid,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="buy" if side_key == "long" else "sell",
                    order_type="limit",
                    quantity=int(self.config.get("entry_qty") or 10),
                    limit_price=float(entry),
                    reason="entry",
                    requires_verification=True,
                    bracket_role="entry",
                    live_after_ts=bar.ts,
                    expires_after_ts=month_end,
                )
            )
            state["limit_armed"] = True
            state["phase"] = "armed"

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    def _exit_bracket(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _f(trade.get("stop"))
        target = _f(trade.get("target"))
        qty = int(self.config.get("entry_qty") or 10)
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
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
                limit_price=float(target),
                reason="target_open",
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
            "wait_open_touch": False,
            "phase": "flat",
            "done": False,
            "n_fills": 0,
            "n_reentries": 0,
            "active_trade_id": "",
            # Keep global seq so trade_ids stay unique across months
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
