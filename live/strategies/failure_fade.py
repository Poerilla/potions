"""Quarterly prior-extreme failure_fade + one-shot reclaim (daily bars).

Primary (failure_fade):
  First daily touch of prior-quarter high/low with wick-through and close back
  inside the prior range → market fade (``live_after_ts`` → next open).
  SL = touch-candle adverse extreme. 5 @ 15% into prior range; BE on first
  ISO week-close back in prior range; 5 @ 62% into prior range.

Reclaim (same plugin, once, only after primary ``stop`` / BE-stop):
  Significant level = original fade SL. Wait close through then close back →
  market same direction. SL = prior entry ± 2× prior risk. Same size/exits;
  TP1 = new entry ± 14% of prior width; TP2 kept from the failed fade.

Non-fade first touches (on-level / close-through) skip the quarter.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models import Bar, CancelIntent, ModifyIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

ON_LEVEL_FRAC = 0.005
ON_LEVEL_MIN_PTS = 1.0


class FailureFadeStrategy(StrategyPlugin):
    strategy_type = "failure_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 10,
            "tp1_qty": 5,
            "tp1_pct": 0.15,
            "tp2_pct": 0.62,
            "reclaim_tp1_pct": 0.14,
            "enable_reclaim": True,
            "timeframe": "D",
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "D")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_daily(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")
        phase = str(trade.get("phase") or "fade")

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                }
            )
            # Reclaim TP1 is measured from actual fill.
            if phase == "reclaim":
                width = float(state.get("prior_width") or 0.0)
                pct = float(self.config.get("reclaim_tp1_pct") or 0.14)
                direction = str(trade.get("direction") or "")
                if direction == "long":
                    trade["tp1"] = float(fill.price) + pct * width
                else:
                    trade["tp1"] = float(fill.price) - pct * width
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["leg_phase"] = phase
            if phase == "fade":
                state["program_phase"] = "in_fade"
            else:
                state["program_phase"] = "in_reclaim"
            orders = self._exit_orders(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role == "tp1":
            trade["tp1_hit"] = True
            cancels = self._cancel_open_roles(context, fill.trade_id, {"stop", "tp2", "runner_tp"})
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                orders.extend(self._runner_exit_orders(fill.trade_id, str(trade.get("direction") or ""), state))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"stop", "tp2", "runner_tp", "quarter_close", "be_stop"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                # Classify BE stop when we had armed BE and stop ~ entry.
                exit_reason = role
                if role == "stop" and bool(trade.get("be_armed")):
                    entry = _to_float(trade.get("entry_price"))
                    stop0 = _to_float(trade.get("stop"))
                    fill_px = float(fill.price)
                    if entry is not None and abs(fill_px - entry) <= abs((stop0 or entry) - entry) * 0.25 + 1e-6:
                        exit_reason = "be_stop"
                    elif entry is not None and abs(fill_px - entry) < 1e-6:
                        exit_reason = "be_stop"
                # Prefer explicit: if stop price was moved to entry, treat as be_stop.
                if role == "stop" and bool(trade.get("be_armed")):
                    cur_stop = _to_float(trade.get("stop"))
                    entry = _to_float(trade.get("entry_price"))
                    if cur_stop is not None and entry is not None and abs(cur_stop - entry) < 1e-9:
                        exit_reason = "be_stop"
                trade["exit_reason"] = exit_reason
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                orders: List[OrderIntent] = []

                if phase == "fade":
                    state["fade_done"] = True
                    failed = exit_reason in {"stop", "be_stop"}
                    if failed and bool(self.config.get("enable_reclaim", True)) and not state.get("reclaim_used"):
                        # Arm reclaim watch using original sweep SL and fade risk.
                        state["reclaim_level"] = float(trade.get("stop0") or trade.get("stop") or 0.0)
                        state["parent_entry"] = float(trade.get("entry_price") or 0.0)
                        state["parent_risk"] = abs(
                            float(state["parent_entry"]) - float(state["reclaim_level"])
                        )
                        state["parent_tp2"] = float(trade.get("tp2") or 0.0)
                        state["parent_direction"] = str(trade.get("direction") or "")
                        state["parent_exit_reason"] = exit_reason
                        state["reclaim_pierced"] = False
                        state["program_phase"] = "reclaim_watch"
                    else:
                        state["program_phase"] = "done"
                        state["done"] = True
                else:
                    state["reclaim_used"] = True
                    state["program_phase"] = "done"
                    state["done"] = True

                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    # ------------------------------------------------------------------

    def _on_daily(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_ts(bar.ts)
        qkey = _quarter_key(dt)
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []

        # Quarter roll: flatten residual, seal prior H/L, start fresh watch.
        if state.get("quarter_key") != qkey:
            if context.position_quantity != 0 or state.get("current_leg_open"):
                cancels.extend(self._cancel_all_open(context, "quarter_roll"))
                if context.position_quantity != 0:
                    orders.append(self._close_all_qty(context.position_quantity, bar.ts, "quarter_close"))
                self._commit_state(state)
                if context.position_quantity != 0:
                    return StrategyActions(orders, cancels, modifies, [], [])
            state = self._roll_quarter(state, qkey, dt)

        # Build current quarter extremes (for next quarter's prior).
        self._update_building(state, bar)

        # Levels ready only after we have a sealed prior quarter.
        if not state.get("prior_ready"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, modifies, [], [])

        # Week-close BE while in a fade/reclaim position.
        if state.get("current_leg_open") and context.position_quantity != 0:
            modifies.extend(self._maybe_arm_be(bar, context, state, dt))

        if state.get("done") and state.get("program_phase") not in {"reclaim_watch"}:
            self._commit_state(state)
            return StrategyActions(orders, cancels, modifies, [], [])

        # First-touch fade arm (once).
        if (
            not state.get("touch_seen")
            and not state.get("fade_done")
            and not state.get("current_leg_open")
            and state.get("program_phase") == "watching"
        ):
            cls = self._classify_touch(bar, state)
            if cls is not None:
                extreme, setup, direction = cls
                state["touch_seen"] = True
                state["touch_date"] = bar.ts[:10]
                if setup != "failure_fade":
                    state["done"] = True
                    state["program_phase"] = "skipped_non_fade"
                    state["skip_setup"] = setup
                else:
                    stop0 = float(bar.low) if direction == "long" else float(bar.high)
                    tp1, tp2 = self._fade_targets(state, direction)
                    intent = self._arm_entry(
                        bar.ts,
                        state,
                        direction=direction,
                        phase="fade",
                        stop0=stop0,
                        stop=stop0,
                        tp1=tp1,
                        tp2=tp2,
                        extreme=extreme,
                    )
                    if intent is not None:
                        orders.append(intent)
                        state["program_phase"] = "fade_entry_pending"

        # Reclaim watch / arm.
        if state.get("program_phase") == "reclaim_watch" and not state.get("current_leg_open"):
            armed = self._maybe_arm_reclaim(bar, state)
            if armed is not None:
                orders.append(armed)
                state["program_phase"] = "reclaim_entry_pending"
                state["reclaim_used"] = True

        self._commit_state(state)
        return StrategyActions(orders, cancels, modifies, [], [])

    def _maybe_arm_reclaim(self, bar: Bar, state: Dict[str, Any]) -> Optional[OrderIntent]:
        level = _to_float(state.get("reclaim_level"))
        direction = str(state.get("parent_direction") or "")
        risk = float(state.get("parent_risk") or 0.0)
        parent_entry = float(state.get("parent_entry") or 0.0)
        tp2 = float(state.get("parent_tp2") or 0.0)
        if level is None or risk <= 0 or not direction:
            state["program_phase"] = "done"
            state["done"] = True
            return None
        cl = float(bar.close)
        pierced = bool(state.get("reclaim_pierced"))
        if not pierced:
            if direction == "long" and cl < level:
                state["reclaim_pierced"] = True
            elif direction == "short" and cl > level:
                state["reclaim_pierced"] = True
            return None
        # Already pierced — wait for close back through.
        if direction == "long" and cl > level:
            stop = parent_entry - 2.0 * risk
            # tp1 filled on entry fill from actual price; placeholder = level for now
            return self._arm_entry(
                bar.ts,
                state,
                direction=direction,
                phase="reclaim",
                stop0=stop,
                stop=stop,
                tp1=cl,  # overwritten on fill
                tp2=tp2,
                extreme=str(state.get("extreme") or ""),
            )
        if direction == "short" and cl < level:
            stop = parent_entry + 2.0 * risk
            return self._arm_entry(
                bar.ts,
                state,
                direction=direction,
                phase="reclaim",
                stop0=stop,
                stop=stop,
                tp1=cl,
                tp2=tp2,
                extreme=str(state.get("extreme") or ""),
            )
        return None

    def _maybe_arm_be(
        self, bar: Bar, context: StrategyContext, state: Dict[str, Any], dt: datetime
    ) -> List[ModifyIntent]:
        trade_id = str(state.get("active_trade_id") or "")
        if not trade_id:
            return []
        trade = self._trade(trade_id, state)
        if bool(trade.get("be_armed")):
            return []
        week = _week_id(dt)
        # Playbook arms on ISO week-ending bar; Fri (weekday>=4) is the daily proxy.
        is_week_end = dt.weekday() >= 4
        if not is_week_end:
            state["last_be_week"] = week
            return []
        if trade.get("be_checked_week") == list(week):
            return []
        prior_high = float(state.get("prior_high") or 0.0)
        prior_low = float(state.get("prior_low") or 0.0)
        cl = float(bar.close)
        trade["be_checked_week"] = list(week)
        state["last_be_week"] = week
        if not (prior_low <= cl <= prior_high):
            return []
        entry = _to_float(trade.get("entry_price"))
        if entry is None:
            return []
        trade["be_armed"] = True
        trade["stop"] = float(entry)
        trade["be_armed_ts"] = bar.ts
        out: List[ModifyIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and (o.reason == "stop" or o.bracket_role == "stop"):
                out.append(
                    ModifyIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=o.broker_order_id,
                        reason="failure_fade_be",
                        stop_price=float(entry),
                    )
                )
        return out

    def _classify_touch(
        self, bar: Bar, state: Dict[str, Any]
    ) -> Optional[Tuple[str, str, str]]:
        prior_high = float(state["prior_high"])
        prior_low = float(state["prior_low"])
        width = float(state["prior_width"])
        if width <= 0:
            return None
        hi = float(bar.high)
        lo = float(bar.low)
        cl = float(bar.close)
        tol = max(ON_LEVEL_MIN_PTS, ON_LEVEL_FRAC * width)
        took_high = hi >= prior_high
        took_low = lo <= prior_low
        if not took_high and not took_low:
            return None
        if took_high and took_low:
            if (prior_low - lo) > (hi - prior_high):
                took_high = False
            else:
                took_low = False
        if took_low:
            if cl > prior_low + tol:
                return "prior_low", "failure_fade", "long"
            if abs(cl - prior_low) <= tol:
                return "prior_low", "on_level_cont", "short"
            return "prior_low", "close_through_cont", "short"
        if cl < prior_high - tol:
            return "prior_high", "failure_fade", "short"
        if abs(cl - prior_high) <= tol:
            return "prior_high", "on_level_cont", "long"
        return "prior_high", "close_through_cont", "long"

    def _fade_targets(self, state: Dict[str, Any], direction: str) -> Tuple[float, float]:
        prior_high = float(state["prior_high"])
        prior_low = float(state["prior_low"])
        width = float(state["prior_width"])
        p1 = float(self.config.get("tp1_pct") or 0.15)
        p2 = float(self.config.get("tp2_pct") or 0.62)
        if direction == "long":
            return prior_low + p1 * width, prior_low + p2 * width
        return prior_high - p1 * width, prior_high - p2 * width

    def _arm_entry(
        self,
        ts: str,
        state: Dict[str, Any],
        *,
        direction: str,
        phase: str,
        stop0: float,
        stop: float,
        tp1: float,
        tp2: float,
        extreme: str,
    ) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 10)
        if qty <= 0:
            return None
        trade_id = self._new_trade_id(state)
        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "phase": phase,
            "extreme": extreme,
            "stop0": float(stop0),
            "stop": float(stop),
            "tp1": float(tp1),
            "tp2": float(tp2),
            "entry_qty": qty,
            "tp1_qty": int(self.config.get("tp1_qty") or 5),
            "tp1_hit": False,
            "be_armed": False,
        }
        if extreme:
            state["extreme"] = extreme
        state["active_trade_id"] = trade_id
        side_ord = "buy" if direction == "long" else "sell"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side_ord,
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=_quarter_expiry(str(state.get("quarter_key") or "")),
        )

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp1 = _to_float(trade.get("tp1"))
        tp2 = _to_float(trade.get("tp2"))
        qty = int(trade.get("entry_qty") or 0)
        tp1_qty = min(int(trade.get("tp1_qty") or self.config.get("tp1_qty") or 5), qty)
        runner_qty = max(0, qty - tp1_qty)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or tp1 is None or tp2 is None or qty <= 0 or not direction:
            return []
        exit_side = "sell" if direction == "long" else "buy"
        expiry = _quarter_expiry(str(state.get("quarter_key") or ""))
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
        if tp1_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=tp1,
                    reason="tp1",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp1",
                    expires_after_ts=expiry,
                )
            )
        if runner_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=tp2,
                    reason="tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=expiry,
                )
            )
        return out

    def _runner_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp2 = _to_float(trade.get("tp2"))
        qty = int(trade.get("entry_qty") or 0)
        tp1_qty = int(trade.get("tp1_qty") or 5)
        rem = max(0, qty - tp1_qty)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or tp2 is None or rem <= 0 or not direction:
            return []
        exit_side = "sell" if direction == "long" else "buy"
        expiry = _quarter_expiry(str(state.get("quarter_key") or ""))
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=rem,
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
                quantity=rem,
                limit_price=tp2,
                reason="tp2",
                requires_verification=False,
                reduce_only=True,
                bracket_role="tp2",
                expires_after_ts=expiry,
            ),
        ]

    def _close_all_qty(self, position_quantity: int, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(position_quantity))
        side = "sell" if position_quantity > 0 else "buy"
        trade_id = str(self._state().get("active_trade_id") or new_id("t"))
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

    def _cancel_all_open(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, reason)
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and bool(o.reduce_only):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "position_flat"))
        return out

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: Set[str]) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and (o.reason in roles or o.bracket_role in roles):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "rebuild_exits"))
        return out

    def _update_building(self, state: Dict[str, Any], bar: Bar) -> None:
        hi = float(bar.high)
        lo = float(bar.low)
        if state.get("q_high") is None:
            state["q_high"] = hi
            state["q_low"] = lo
        else:
            state["q_high"] = max(float(state["q_high"]), hi)
            state["q_low"] = min(float(state["q_low"]), lo)
        state["q_bar_count"] = int(state.get("q_bar_count") or 0) + 1

    def _roll_quarter(self, state: Dict[str, Any], qkey: str, dt: datetime) -> Dict[str, Any]:
        prior_high = state.get("q_high")
        prior_low = state.get("q_low")
        prior_ready = prior_high is not None and prior_low is not None
        width = (float(prior_high) - float(prior_low)) if prior_ready else 0.0
        fresh = {
            "quarter_key": qkey,
            "year": int(dt.year),
            "quarter": int((dt.month - 1) // 3 + 1),
            "q_high": None,
            "q_low": None,
            "q_bar_count": 0,
            "prior_high": float(prior_high) if prior_ready else None,
            "prior_low": float(prior_low) if prior_ready else None,
            "prior_width": float(width) if prior_ready and width > 0 else 0.0,
            "prior_ready": bool(prior_ready and width > 0),
            "prior_label": str(state.get("quarter_key") or ""),
            "touch_seen": False,
            "fade_done": False,
            "reclaim_used": False,
            "reclaim_pierced": False,
            "reclaim_level": None,
            "parent_entry": None,
            "parent_risk": None,
            "parent_tp2": None,
            "parent_direction": "",
            "parent_exit_reason": "",
            "current_leg_open": False,
            "active_trade_id": "",
            "leg_phase": "",
            "program_phase": "watching" if (prior_ready and width > 0) else "building_first_quarter",
            "done": False if (prior_ready and width > 0) else True,
            "skip_setup": "",
            "extreme": "",
            "last_be_week": None,
            "trades": {},
            "trade_seq": int(state.get("trade_seq") or 0),
        }
        self.state = fresh
        return fresh

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "quarter_key" not in raw:
            raw = {
                "quarter_key": "",
                "q_high": None,
                "q_low": None,
                "prior_ready": False,
                "program_phase": "init",
                "done": True,
                "trades": {},
                "trade_seq": 0,
            }
        if "trades" not in raw or not isinstance(raw["trades"], dict):
            raw["trades"] = {}
        self.state = raw
        return raw

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        trade = trades.get(trade_id)
        if trade is None:
            trade = {}
            trades[trade_id] = trade
        return trade

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq") or 0) + 1
        return "%s_t%d" % (self.instance.strategy_id, int(state["trade_seq"]))


def _parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text[:10])


def _quarter_key(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return "%dQ%d" % (dt.year, q)


def _week_id(dt: datetime) -> Tuple[int, int]:
    iso = dt.isocalendar()
    return int(iso[0]), int(iso[1])


def _quarter_expiry(qkey: str) -> str:
    # Expire at start of next quarter (YYYYQn → next).
    if not qkey or "Q" not in qkey:
        return ""
    try:
        year_s, q_s = qkey.split("Q", 1)
        year = int(year_s)
        q = int(q_s)
    except ValueError:
        return ""
    if q >= 4:
        return "%d-01-01T00:00:00" % (year + 1)
    month = q * 3 + 1
    return "%d-%02d-01T00:00:00" % (year, month)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
