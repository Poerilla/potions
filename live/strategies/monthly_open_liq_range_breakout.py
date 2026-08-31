"""Monthly-open envelope range breakout sidecar (4h close → limit).

After liq-run levels are known (``arm_after_ts``), the chart horizontals define
``[range_low, range_high]``. On a **4h close** outside that range (bucket must
start at/after ``arm_after_ts``), arm a resting limit at the broken boundary.
SL = 2× liq-run size (configurable to range size); target = range height.
Max 2 attempts: after a stop, wait for another 4h close outside + re-arm.

Session-gap rule (``require_trade_through`` default on): void resting entry if
overnight/weekend open gaps through the limit or opens adversely (especially
near SL). Require price to retag the entry level before re-arm.

Config ``breakout_mode``:

- ``follow`` (default) — trade with the 4h close breakout
- ``fade`` — fade the breakout (limit at boundary, opposite direction)

When ``fade`` + ``scale_half_range``:

- Scale **half** the entry at range midpoint (half the envelope)
- Runner at the opposite boundary (full fade back)

Strategy type: ``monthly_open_liq_range_breakout``
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from ..entry_gap import entry_limit_gap_blocked, session_gap as _session_gap

NY = "America/New_York"


def _f(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_4h_ny(ts: pd.Timestamp) -> pd.Timestamp:
    ny = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(NY)
    h = (int(ny.hour) // 4) * 4
    return ny.replace(hour=h, minute=0, second=0, microsecond=0)


class MonthlyOpenLiqRangeBreakoutStrategy(StrategyPlugin):
    strategy_type = "monthly_open_liq_range_breakout"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 10,
            "timeframe": "1m",
            "month_plans": {},
            "max_attempts": 2,
            # "2x_liq" | "range"
            "sl_mode": "2x_liq",
            # "follow" | "fade"
            "breakout_mode": "follow",
            # fade only: 1/2 @ range mid, 1/2 @ opposite boundary
            "scale_half_range": False,
            "tp1_qty": None,
            "tp2_qty": None,
            "require_trade_through": True,
            "gap_near_sl_frac": 0.15,
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

        if role == "entry":
            entry_qty = int(fill.quantity)
            tp1_qty, tp2_qty = self._scale_quantities(entry_qty)
            trade.update(
                {
                    "status": "open",
                    "direction": "Long" if fill.side == "buy" else "Short",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": entry_qty,
                    "entry_qty": entry_qty,
                    "tp1_qty": tp1_qty,
                    "tp2_qty": tp2_qty,
                    "tp_half_hit": False,
                }
            )
            state["in_trade"] = True
            state["limit_armed"] = False
            state["pending_side"] = ""
            state["active_trade_id"] = fill.trade_id
            state["phase"] = "in_trade"
            state["n_attempts"] = int(state.get("n_attempts") or 0) + 1
            orders = self._exit_bracket(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role == "tp_half":
            trade["tp_half_hit"] = True
            cancels = self._cancel_reduce(context, fill.trade_id)
            orders: List[OrderIntent] = []
            if int(context.position_quantity) != 0:
                orders.extend(
                    self._exit_bracket(
                        fill.trade_id,
                        str(trade.get("direction") or ""),
                        state,
                        runner_only=True,
                    )
                )
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"target", "target_range", "tp_full", "stop", "eom", "flatten"}:
            if int(context.position_quantity) == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels = self._cancel_reduce(context, fill.trade_id)
                if role in {"target", "target_range", "tp_full"}:
                    # Hit objective — done for the month
                    state["done"] = True
                    state["phase"] = "done_target"
                elif role == "stop":
                    max_att = int(self.config.get("max_attempts") or 2)
                    if int(state.get("n_attempts") or 0) >= max_att:
                        state["done"] = True
                        state["phase"] = "done_max_attempts"
                    else:
                        # Wait for another 4h close outside range
                        state["phase"] = "wait_breakout"
                        state["pending_side"] = ""
                else:
                    state["done"] = True
                    state["phase"] = "month_end"
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_bar(self, bar, context: StrategyContext) -> StrategyActions:
        dt = pd.Timestamp(bar.ts)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        ny = dt.tz_convert(NY)
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
            state["phase"] = "month_end"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if state.get("done"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        # No breakout signal / arming during liq-run window
        if arm_after and bar.ts < arm_after:
            self._update_4h_bucket(state, dt, float(bar.close), process_close=False)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        range_high = _f(plan.get("range_high"))
        range_low = _f(plan.get("range_low"))
        range_size = _f(plan.get("range_size"))
        ext = _f(plan.get("ext_pts"))
        if (
            range_high is None
            or range_low is None
            or range_size is None
            or range_size <= 0
            or ext is None
            or ext <= 0
        ):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        closed = self._update_4h_bucket(state, dt, float(bar.close), process_close=True)
        if closed is not None and not state.get("in_trade") and not state.get("limit_armed"):
            closed_bucket, closed_close = closed
            # Bucket must start at/after arm_after (no liq-window breakout)
            arm_ts = pd.Timestamp(arm_after)
            if arm_ts.tzinfo is None:
                arm_ts = arm_ts.tz_localize("UTC")
            arm_ny = arm_ts.tz_convert(NY)
            if closed_bucket >= arm_ny:
                side = self._signal_side(closed_close, range_high, range_low)
                if side:
                    state["pending_side"] = side
                    state["phase"] = "signal_%s" % side

        # Arm limit at boundary for pending breakout
        max_att = int(self.config.get("max_attempts") or 2)
        can_attempt = int(state.get("n_attempts") or 0) < max_att
        pending = str(state.get("pending_side") or "")
        want_arm = (
            can_attempt
            and pending in {"long", "short"}
            and not state.get("in_trade")
            and not state.get("limit_armed")
            and not state.get("entry_await_retag")
            and not self._has_entry(context)
        )
        if want_arm:
            tid = self._new_trade_id(state)
            direction = "Long" if pending == "long" else "Short"
            entry = self._entry_level(pending, range_high, range_low)
            sl_mode = str(self.config.get("sl_mode") or "2x_liq")
            risk = float(2.0 * ext) if sl_mode == "2x_liq" else float(range_size)
            range_mid = 0.5 * (float(range_high) + float(range_low))
            if self._fade_mode():
                if pending == "short":
                    stop = entry + risk
                    target_half = range_mid
                    target_full = float(range_low)
                    target = target_full
                else:
                    stop = entry - risk
                    target_half = range_mid
                    target_full = float(range_high)
                    target = target_full
            elif pending == "long":
                stop = entry - risk
                target_half = None
                target_full = None
                target = entry + float(range_size)
            else:
                stop = entry + risk
                target_half = None
                target_full = None
                target = entry - float(range_size)
            state["trades"][tid] = {
                "direction": direction,
                "side_key": pending,
                "status": "armed",
                "entry": entry,
                "stop": stop,
                "target": target,
                "target_half": target_half,
                "target_full": target_full,
                "risk_pts": risk,
            }
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=tid,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="buy" if pending == "long" else "sell",
                    order_type="limit",
                    quantity=int(int(self.config.get("entry_qty") or 10)),
                    limit_price=float(entry),
                    reason="entry",
                    requires_verification=True,
                    bracket_role="entry",
                    bracket_stop_price=float(stop),
                    bracket_target_price=float(target),
                    live_after_ts=bar.ts,
                    expires_after_ts=month_end,
                )
            )
            state["limit_armed"] = True
            state["armed_side"] = pending
            state["armed_entry"] = float(entry)
            state["armed_stop"] = float(stop)
            state["phase"] = "armed_%s" % pending
            # Clear pending so we don't re-arm until next 4h close after a stop
            state["pending_side"] = ""

        if bool(self.config.get("require_trade_through", True)) and (
            state.get("limit_armed") or self._has_entry(context)
        ):
            gap_cancels, gap_state = self._gap_void_entry(context, bar, state)
            cancels.extend(gap_cancels)
            state.update(gap_state)

        if state.get("entry_await_retag"):
            armed_side = str(state.get("armed_side") or state.get("pending_side") or "")
            entry_lvl = _f(state.get("armed_entry"))
            if not entry_lvl and armed_side:
                entry_lvl = self._entry_level(
                    armed_side,
                    float(range_high),
                    float(range_low),
                )
            if armed_side and entry_lvl is not None and _retag_cleared(armed_side, float(entry_lvl), bar):
                state["entry_await_retag"] = False
                if not state.get("in_trade") and not state.get("done"):
                    state["pending_side"] = armed_side
                    state["phase"] = "retag_%s" % armed_side

        state["prev_close"] = float(bar.close)
        state["prev_bar_ts"] = str(bar.ts)
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    def _update_4h_bucket(
        self,
        state: Dict[str, Any],
        dt: pd.Timestamp,
        close: float,
        *,
        process_close: bool,
    ) -> Optional[tuple]:
        """Track NY 4h buckets on 1m closes. Returns (bucket_start, close) when a bucket ends."""
        bucket = _bucket_4h_ny(dt)
        cur = state.get("cur_4h_bucket")
        out = None
        if cur is None:
            state["cur_4h_bucket"] = bucket.isoformat()
            state["cur_4h_close"] = float(close)
            return None
        cur_ts = pd.Timestamp(cur)
        if cur_ts.tzinfo is None:
            # isoformat from NY-aware may keep offset
            try:
                cur_ts = pd.Timestamp(cur)
            except Exception:
                cur_ts = bucket
        if bucket != cur_ts:
            if process_close:
                out = (cur_ts, float(state.get("cur_4h_close") or close))
            state["cur_4h_bucket"] = bucket.isoformat()
            state["cur_4h_close"] = float(close)
        else:
            state["cur_4h_close"] = float(close)
        return out

    def _fade_mode(self) -> bool:
        return str(self.config.get("breakout_mode") or "follow").lower() == "fade"

    def _scale_half_range(self) -> bool:
        return bool(self.config.get("scale_half_range")) and self._fade_mode()

    def _signal_side(self, closed_close: float, range_high: float, range_low: float) -> str:
        if closed_close > range_high:
            return "short" if self._fade_mode() else "long"
        if closed_close < range_low:
            return "long" if self._fade_mode() else "short"
        return ""

    def _entry_level(self, pending: str, range_high: float, range_low: float) -> float:
        """Limit price at the broken envelope boundary."""
        if self._fade_mode():
            return float(range_high if pending == "short" else range_low)
        return float(range_high if pending == "long" else range_low)

    def _scale_quantities(self, entry_qty: int) -> tuple:
        if not self._scale_half_range():
            return 0, 0
        tp1_raw = self.config.get("tp1_qty")
        tp2_raw = self.config.get("tp2_qty")
        if tp1_raw is None and tp2_raw is None:
            tp1 = max(1, entry_qty // 2)
            tp2 = max(0, entry_qty - tp1)
        else:
            tp1 = int(tp1_raw or 0)
            tp2 = int(tp2_raw or 0)
            if tp1 + tp2 > entry_qty:
                overflow = tp1 + tp2 - entry_qty
                tp2 = max(0, tp2 - overflow)
        return tp1, tp2

    def _exit_bracket(
        self,
        trade_id: str,
        direction: str,
        state: Dict[str, Any],
        *,
        runner_only: bool = False,
    ) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _f(trade.get("stop"))
        target = _f(trade.get("target"))
        target_half = _f(trade.get("target_half"))
        target_full = _f(trade.get("target_full"))
        entry_qty = int(trade.get("entry_qty") or self.config.get("entry_qty") or 10)
        tp1_qty = int(trade.get("tp1_qty") or 0)
        tp2_qty = int(trade.get("tp2_qty") or 0)
        if runner_only:
            tp1_qty = 0
        elif tp1_qty <= 0 and tp2_qty <= 0:
            tp1_qty, tp2_qty = self._scale_quantities(entry_qty)
        qty = tp2_qty if runner_only else entry_qty
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        if stop is None or target is None:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        orders: List[OrderIntent] = []
        if qty > 0:
            orders.append(
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
                )
            )
        if self._scale_half_range() and tp1_qty > 0 and target_half is not None and not runner_only:
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=float(target_half),
                    reason="tp_half",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="target",
                    expires_after_ts=expiry,
                )
            )
        runner_target = target_full if target_full is not None else target
        runner_qty = tp2_qty if self._scale_half_range() else qty
        if runner_qty > 0:
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=float(runner_target),
                    reason="tp_full" if self._scale_half_range() else "target_range",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="target",
                    expires_after_ts=expiry,
                )
            )
        return orders

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

    def _gap_void_entry(self, context: StrategyContext, bar, state: Dict[str, Any]) -> tuple:
        """Cancel resting entry after session-gap adverse open; require retag."""
        prev_close = _f(state.get("prev_close"))
        prev_ts = str(state.get("prev_bar_ts") or "")
        if prev_close is None or not _session_gap(prev_ts, bar.ts):
            return [], {}

        near_sl = float(self.config.get("gap_near_sl_frac") or 0.15)
        cancels: List[CancelIntent] = []
        updates: Dict[str, Any] = {}
        for o in context.strategy_open_orders:
            if o.bracket_role != "entry" or bool(o.reduce_only):
                continue
            if o.limit_price is None:
                continue
            side_key = _order_side_key(o.side, str(state.get("armed_side") or ""))
            entry = float(o.limit_price)
            stop = _f(state.get("armed_stop"))
            if stop is None:
                trade = self._trade(str(o.trade_id), state)
                stop = _f(trade.get("stop"))
            order_side = "buy" if side_key == "long" else "sell"
            blocked = entry_limit_gap_blocked(
                side=order_side,
                entry=entry,
                stop=stop,
                prev_close=prev_close,
                bar_open=float(bar.open),
                session_gap=True,
                near_sl_frac=near_sl,
            )
            if not blocked:
                continue
            cancels.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "gap_void"))
            updates.update(
                {
                    "limit_armed": False,
                    "entry_await_retag": True,
                    "armed_side": side_key,
                    "armed_entry": entry,
                    "armed_stop": stop,
                    "phase": "%s_gap_void" % side_key,
                }
            )
        return cancels, updates

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
            "pending_side": "",
            "phase": "wait_breakout",
            "done": False,
            "n_attempts": 0,
            "active_trade_id": "",
            "cur_4h_bucket": None,
            "cur_4h_close": None,
            "prev_close": None,
            "prev_bar_ts": None,
            "entry_await_retag": False,
            "armed_side": "",
            "armed_entry": None,
            "armed_stop": None,
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


def _retag_cleared(side_key: str, entry: float, bar) -> bool:
    if side_key in {"long", "buy"}:
        return float(bar.high) >= entry
    return float(bar.low) <= entry


def _order_side_key(order_side: str, armed_side: str) -> str:
    if armed_side in {"long", "short"}:
        return armed_side
    return "long" if order_side == "buy" else "short"
