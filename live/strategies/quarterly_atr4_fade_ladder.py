"""Open-week ±4×ATR fade with ATR scale ladder + BE runner.

Research variant of ``quarterly_atr4_fade`` (also supports monthly periods):

1. Opening week of the period (quarter or month) defines mid + ATR(14);
   levels = mid ±4×ATR.
2. Entry modes:
   - ``first_only``: fade the first touch of ±4 (optionally side-filtered).
   - ``second_only``: after first touch, wait for opposite ±4 (abort on same-side
     ±8); then fade that opposite touch (the reverse path).
3. Size ``entry_qty`` (default 10). Protective stop = ``risk_atr_mult`` × ATR.
4. Scale: ``scale_qty`` off every ``scale_atr_step`` ATR of favorable move, up
   through ``be_after_atr`` (default: 2 off at +2/+4/+6/+8 ATR → tp1–tp4).
   Optional ``scale_qtys`` list overrides uniform sizing (e.g. ``[1,2,2,3]`` at
   +2/+4/+6/+8); residual = ``entry_qty - sum(scale_qtys)`` is the EOQ runner.
5. After the ``be_after_atr`` scale fills, remaining stop → break-even; no further
   TP — flatten residual (2 runners with defaults) at period end.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

ATR_LEN = 14


class QuarterlyAtr4FadeLadderStrategy(StrategyPlugin):
    strategy_type = "quarterly_atr4_fade_ladder"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.00001,
            "entry_qty": 10,
            "scale_qty": 2,
            # Optional per-level qtys at +step, +2*step, … through be_after_atr.
            # When set, overrides uniform scale_qty (0 skips that ATR rung).
            "scale_qtys": None,
            "scale_atr_step": 2.0,
            "be_after_atr": 8.0,
            "atr_len": ATR_LEN,
            "atr_mult": 4.0,
            "risk_atr_mult": 2.0,
            # first_only | second_only
            "trade_mode": "first_only",
            # empty / None = both; else e.g. ["lower"] or ["upper"]
            "allowed_sides": ["lower"],
            "max_trades_per_quarter": 1,
            # quarter | month — month uses calendar-month open week + EOM flatten
            "period": "quarter",
            "timeframe": "4h",
            "record_levels": False,
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "4h")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_4h_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["entry_pending"] = False
            state["phase"] = "in_trade"
            orders = self._exit_orders(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role.startswith("tp"):
            trade[role + "_hit"] = True
            hit_atr = float(trade.get(role + "_atr") or 0.0)
            be_after = float(self.config.get("be_after_atr") or 8.0)
            cancels = self._cancel_open_roles(
                context, fill.trade_id, {"stop"} | self._tp_roles(trade)
            )
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                move_be = hit_atr + 1e-12 >= be_after
                if move_be:
                    trade["be_armed"] = True
                orders.extend(
                    self._remaining_exit_orders(
                        fill.trade_id,
                        str(trade.get("direction") or ""),
                        state,
                        remaining_qty=abs(int(context.position_quantity)),
                        move_be=bool(trade.get("be_armed")),
                    )
                )
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"stop", "quarter_close", "month_close", "period_close"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                state["trades_done"] = int(state.get("trades_done") or 0) + 1
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                max_trades = int(
                    self.config.get("max_trades_per_period")
                    or self.config.get("max_trades_per_quarter")
                    or 1
                )
                if int(state.get("trades_done") or 0) >= max_trades:
                    state["done"] = True
                    state["phase"] = "done" if role != "stop" else "stopped"
                else:
                    state["phase"] = "watching"
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    # ------------------------------------------------------------------

    def _period_mode(self) -> str:
        p = str(self.config.get("period") or "quarter").strip().lower()
        return "month" if p in {"month", "monthly", "m"} else "quarter"

    def _close_reason(self) -> str:
        return "month_close" if self._period_mode() == "month" else "quarter_close"

    def _bar_hours(self) -> float:
        tf = str(self.config.get("timeframe") or "4h").strip().lower()
        if tf.endswith("h") and tf[:-1].replace(".", "", 1).isdigit():
            return float(tf[:-1])
        if tf.endswith("m") and tf[:-1].isdigit():
            return float(tf[:-1]) / 60.0
        return 4.0

    def _on_4h_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        period = self._period_mode()
        qkey = _month_key(dt) if period == "month" else _quarter_key(dt)
        state = self._state()
        close_reason = self._close_reason()
        if state.get("quarter_key") != qkey:
            orders0: List[OrderIntent] = []
            cancels0: List[CancelIntent] = []
            if context.position_quantity != 0 or state.get("current_leg_open"):
                cancels0.extend(self._cancel_all_open(context))
                if context.position_quantity != 0:
                    orders0.append(self._close_all(context, bar.ts, close_reason))
                self._commit_state(state)
                if context.position_quantity != 0:
                    return StrategyActions(orders0, cancels0, [], [], [])
            state = self._fresh_quarter_state(qkey, prior=state)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        self._update_atr(state, bar)

        q_start, q_end = (_month_bounds(dt) if period == "month" else _quarter_bounds(dt))
        week0, week1 = _week_bounds(q_start)
        ow_left = max(week0, q_start)

        in_open_week = ow_left <= dt < week1
        if in_open_week:
            hi = float(state["ow_high"]) if state.get("ow_high") is not None else bar.high
            lo = float(state["ow_low"]) if state.get("ow_low") is not None else bar.low
            state["ow_high"] = max(hi, bar.high)
            state["ow_low"] = min(lo, bar.low)
            state["ow_bar_count"] = int(state.get("ow_bar_count") or 0) + 1
            state["phase"] = "building_open_week"

        if (not state.get("levels_ready")) and dt >= week1 and state.get("ow_high") is not None:
            atr = _to_float(state.get("atr"))
            ow_hi = float(state["ow_high"])
            ow_lo = float(state["ow_low"])
            if atr is None or atr <= 0 or ow_hi <= ow_lo:
                state["done"] = True
                state["phase"] = "bad_levels"
            else:
                mid = 0.5 * (ow_hi + ow_lo)
                mult = float(self.config.get("atr_mult") or 4.0)
                state["ow_mid"] = mid
                state["ow_range"] = ow_hi - ow_lo
                state["atr14"] = atr
                state["upper"] = mid + mult * atr
                state["lower"] = mid - mult * atr
                state["upper8"] = mid + 2.0 * mult * atr
                state["lower8"] = mid - 2.0 * mult * atr
                state["levels_ready"] = True
                state["phase"] = "watching_first_touch"
                if not bool(self.config.get("suppress_alerts")):
                    alerts.append(
                        Alert.create(
                            self.instance.strategy_id,
                            "info",
                            "atr4_fade_ladder levels ready mid=%.6f ±4ATR (%s)" % (mid, period),
                        )
                    )

        if bool(self.config.get("record_levels")) and state.get("levels_ready"):
            levels.extend(self._levels(bar.ts, state))

        if state.get("done"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("current_leg_open") or context.position_quantity != 0:
            if _is_last_bar_of_period(dt, q_end, self._bar_hours()):
                cancels.extend(self._cancel_all_open(context))
                if context.position_quantity != 0:
                    orders.append(self._close_all(context, bar.ts, close_reason))
                state["done"] = True
                state["phase"] = "period_end"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if not state.get("levels_ready"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        max_trades = int(
            self.config.get("max_trades_per_period")
            or self.config.get("max_trades_per_quarter")
            or 1
        )
        if int(state.get("trades_done") or 0) >= max_trades:
            state["done"] = True
            state["phase"] = "done"
            self._commit_state(state)
            return StrategyActions.empty()

        mode = str(self.config.get("trade_mode") or "first_only").strip().lower()
        if mode == "second_only":
            orders.extend(self._maybe_arm_second(bar, state))
        else:
            orders.extend(self._maybe_arm_first(bar, state))

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _maybe_arm_first(self, bar: Bar, state: Dict[str, Any]) -> List[OrderIntent]:
        if state.get("first_side") or state.get("entry_pending"):
            return []
        upper = float(state["upper"])
        lower = float(state["lower"])
        hit_up = bar.high >= upper
        hit_dn = bar.low <= lower
        if hit_up and hit_dn:
            state["done"] = True
            state["phase"] = "dual_touch_skip"
            return []
        if not (hit_up or hit_dn):
            return []
        side = "upper" if hit_up else "lower"
        state["first_side"] = side
        if not self._side_allowed(side):
            state["done"] = True
            state["phase"] = "side_filtered"
            return []
        entry = self._arm_entry(bar.ts, state, side)
        if entry is None:
            return []
        state["entry_pending"] = True
        state["phase"] = "entry_sent"
        return [entry]

    def _maybe_arm_second(self, bar: Bar, state: Dict[str, Any]) -> List[OrderIntent]:
        """Path-watch first touch → opposite ±4, then fade that touch."""
        if state.get("entry_pending"):
            return []
        upper = float(state["upper"])
        lower = float(state["lower"])
        upper8 = float(state["upper8"])
        lower8 = float(state["lower8"])

        if not state.get("first_side"):
            hit_up = bar.high >= upper
            hit_dn = bar.low <= lower
            if hit_up and hit_dn:
                state["done"] = True
                state["phase"] = "dual_touch_skip"
                return []
            if hit_up or hit_dn:
                side = "upper" if hit_up else "lower"
                state["first_side"] = side
                state["phase"] = "watching_opposite"
            return []

        first = str(state.get("first_side") or "")
        # Fail path: same-side ±8 before opposite ±4.
        if first == "upper" and bar.high >= upper8:
            state["done"] = True
            state["phase"] = "fail_8_skip"
            return []
        if first == "lower" and bar.low <= lower8:
            state["done"] = True
            state["phase"] = "fail_8_skip"
            return []

        # Win path: opposite ±4 → take the reverse fade there.
        if first == "upper" and bar.low <= lower:
            side = "lower"
        elif first == "lower" and bar.high >= upper:
            side = "upper"
        else:
            return []

        if not self._side_allowed(side):
            state["done"] = True
            state["phase"] = "side_filtered"
            return []
        entry = self._arm_entry(bar.ts, state, side)
        if entry is None:
            return []
        state["entry_pending"] = True
        state["phase"] = "second_entry_sent"
        return [entry]

    def _side_allowed(self, side: str) -> bool:
        allowed = self.config.get("allowed_sides")
        if allowed is None:
            return True
        if isinstance(allowed, str):
            allowed = [x.strip() for x in allowed.split(",") if x.strip()]
        if not isinstance(allowed, (list, tuple)) or len(allowed) == 0:
            return True
        return side in {str(x).strip().lower() for x in allowed}

    # ------------------------------------------------------------------

    def _update_atr(self, state: Dict[str, Any], bar: Bar) -> None:
        prev_close = _to_float(state.get("prev_close"))
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        atr_len = int(self.config.get("atr_len") or ATR_LEN)
        n = int(state.get("atr_n") or 0) + 1
        atr = _to_float(state.get("atr"))
        if atr is None:
            seed = list(state.get("atr_seed") or [])
            seed.append(tr)
            state["atr_seed"] = seed[-atr_len:]
            if len(state["atr_seed"]) >= atr_len:
                atr = sum(float(x) for x in state["atr_seed"]) / float(atr_len)
                state["atr"] = atr
                state.pop("atr_seed", None)
        else:
            alpha = 1.0 / float(atr_len)
            state["atr"] = atr + alpha * (tr - atr)
        state["atr_n"] = n
        state["prev_close"] = close

    def _scale_ladder(self, atr: float) -> List[Tuple[str, float, int]]:
        """Return [(role, atr_multiple, qty), ...] up through be_after_atr."""
        step = float(self.config.get("scale_atr_step") or 2.0)
        be_after = float(self.config.get("be_after_atr") or 8.0)
        entry_qty = int(self.config.get("entry_qty") or 10)
        if step <= 0 or atr <= 0 or entry_qty <= 0:
            return []
        raw_qtys = self.config.get("scale_qtys")
        per_level: Optional[List[int]] = None
        if raw_qtys is not None:
            try:
                per_level = [max(0, int(x)) for x in list(raw_qtys)]
            except (TypeError, ValueError):
                per_level = None
        scale_qty = int(self.config.get("scale_qty") or 2)
        if per_level is None and scale_qty <= 0:
            return []
        out: List[Tuple[str, float, int]] = []
        used = 0
        mult = step
        idx = 1
        while mult <= be_after + 1e-12 and used < entry_qty:
            if per_level is not None:
                if idx - 1 >= len(per_level):
                    break
                qty = min(int(per_level[idx - 1]), entry_qty - used)
            else:
                qty = min(scale_qty, entry_qty - used)
            if qty > 0:
                out.append(("tp%d" % idx, mult, qty))
                used += qty
            idx += 1
            mult += step
        return out

    def _arm_entry(self, ts: str, state: Dict[str, Any], side: str) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 10)
        if qty <= 0:
            return None
        levels = self._trade_levels(state, side)
        if levels is None:
            return None
        direction, stop, ladder = levels
        trade_id = self._new_trade_id(state)
        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "side": side,
            "stop": stop,
            "entry_qty": qty,
            "ladder": [
                {"role": r, "atr": a, "price": px, "qty": q} for r, a, px, q in ladder
            ],
            "be_armed": False,
            "leg": int(state.get("trades_done") or 0) + 1,
        }
        for role, atr_m, _px, _qty in ladder:
            state["trades"][trade_id][role + "_atr"] = atr_m
        state["active_trade_id"] = trade_id
        side_ord = "sell" if direction == "Short" else "buy"
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
            expires_after_ts=_period_expiry(
                state.get("quarter_key") or "", self._period_mode()
            ),
        )

    def _trade_levels(
        self, state: Dict[str, Any], side: str
    ) -> Optional[Tuple[str, float, List[Tuple[str, float, float, int]]]]:
        """Return direction, stop, and ladder of (role, atr_mult, price, qty)."""
        upper = _to_float(state.get("upper"))
        lower = _to_float(state.get("lower"))
        atr = _to_float(state.get("atr14")) or _to_float(state.get("atr"))
        if upper is None or lower is None or atr is None or atr <= 0:
            return None
        risk = float(self.config.get("risk_atr_mult") or 2.0) * atr
        raw_ladder = self._scale_ladder(atr)
        priced: List[Tuple[str, float, float, int]] = []
        if side == "upper":
            direction = "Short"
            entry_ref = upper
            stop = entry_ref + risk
            for role, atr_m, qty in raw_ladder:
                priced.append((role, atr_m, entry_ref - atr_m * atr, qty))
        elif side == "lower":
            direction = "Long"
            entry_ref = lower
            stop = entry_ref - risk
            for role, atr_m, qty in raw_ladder:
                priced.append((role, atr_m, entry_ref + atr_m * atr, qty))
        else:
            return None
        return direction, stop, priced

    def _tp_roles(self, trade: Dict[str, Any]) -> set:
        roles = set()
        for item in trade.get("ladder") or []:
            role = str(item.get("role") or "")
            if role:
                roles.add(role)
        return roles

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        qty = int(trade.get("entry_qty") or 0)
        direction = direction or str(trade.get("direction") or "")
        ladder = list(trade.get("ladder") or [])
        if stop is None or qty <= 0 or not direction:
            return []
        # Materialize limit prices from stored ladder atr multiples if needed.
        atr = _to_float(state.get("atr14")) or _to_float(state.get("atr"))
        side = str(trade.get("side") or "")
        upper = _to_float(state.get("upper"))
        lower = _to_float(state.get("lower"))
        priced_ladder: List[Tuple[str, float, int]] = []
        for item in ladder:
            role = str(item["role"])
            q = int(item["qty"])
            px = _to_float(item.get("price"))
            if px is None and atr is not None:
                atr_m = float(item["atr"])
                if side == "lower" and lower is not None:
                    px = lower + atr_m * atr
                elif side == "upper" and upper is not None:
                    px = upper - atr_m * atr
            if px is None or q <= 0:
                continue
            item["price"] = px
            priced_ladder.append((role, px, q))

        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _period_expiry(str(state.get("quarter_key") or ""), self._period_mode())
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
        for role, px, q in priced_ladder:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=q,
                    limit_price=px,
                    reason=role,
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role=role,
                    expires_after_ts=expiry,
                )
            )
        return out

    def _remaining_exit_orders(
        self,
        trade_id: str,
        direction: str,
        state: Dict[str, Any],
        *,
        remaining_qty: int,
        move_be: bool,
    ) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        direction = direction or str(trade.get("direction") or "")
        ladder = list(trade.get("ladder") or [])
        pending: List[Tuple[str, float, int]] = []
        for item in ladder:
            role = str(item["role"])
            if trade.get(role + "_hit"):
                continue
            px = _to_float(item.get("price"))
            if px is None:
                continue
            pending.append((role, px, int(item["qty"])))
        rem = max(0, int(remaining_qty))
        if rem <= 0 or not direction:
            return []
        stop = _to_float(trade.get("entry_price")) if move_be else _to_float(trade.get("stop"))
        if stop is None:
            stop = _to_float(trade.get("stop"))
        if stop is None:
            return []
        if move_be:
            trade["stop"] = stop
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _period_expiry(str(state.get("quarter_key") or ""), self._period_mode())
        out: List[OrderIntent] = [
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
            )
        ]
        for role, px, q in pending:
            q = min(q, rem)
            if q <= 0:
                continue
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=q,
                    limit_price=px,
                    reason=role,
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role=role,
                    expires_after_ts=expiry,
                )
            )
        return out

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
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

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "quarter_roll")
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and bool(o.reduce_only):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "position_flat"))
        return out

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: set) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and (o.reason in roles or o.bracket_role in roles):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "rebuild_exits"))
        return out

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        out: List[LevelUpdate] = []
        for name, key in (("upper", "upper"), ("mid", "ow_mid"), ("lower", "lower")):
            px = _to_float(state.get(key))
            if px is None:
                continue
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, name, px, ts))
        return out

    def _fresh_quarter_state(self, qkey: str, prior: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prior = prior or {}
        return {
            "quarter_key": qkey,
            "ow_high": None,
            "ow_low": None,
            "ow_mid": None,
            "ow_range": None,
            "ow_bar_count": 0,
            "atr": prior.get("atr"),
            "atr_n": prior.get("atr_n") or 0,
            "atr_seed": list(prior.get("atr_seed") or []),
            "prev_close": prior.get("prev_close"),
            "atr14": None,
            "upper": None,
            "lower": None,
            "upper8": None,
            "lower8": None,
            "levels_ready": False,
            "first_side": "",
            "entry_pending": False,
            "trades_done": 0,
            "current_leg_open": False,
            "active_trade_id": "",
            "done": False,
            "phase": "new_quarter",
            "trades": {},
            "trade_seq": int(prior.get("trade_seq") or 0),
        }

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "quarter_key" not in raw:
            raw = self._fresh_quarter_state("")
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


def _parse_dt(ts: str) -> datetime:
    t = pd_timestamp(ts)
    return t.to_pydatetime() if hasattr(t, "to_pydatetime") else t


def pd_timestamp(ts: str):
    import pandas as pd

    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("America/New_York")


def _quarter_key(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return "%dQ%d" % (dt.year, q)


def _month_key(dt: datetime) -> str:
    return "%dM%02d" % (dt.year, dt.month)


def _quarter_bounds(dt: datetime):
    import pandas as pd

    q = (dt.month - 1) // 3 + 1
    month0 = 1 + (q - 1) * 3
    t0 = pd.Timestamp(year=dt.year, month=month0, day=1, tz="America/New_York")
    t1 = t0 + pd.offsets.MonthBegin(3)
    return t0, t1


def _month_bounds(dt: datetime):
    import pandas as pd

    t0 = pd.Timestamp(year=dt.year, month=dt.month, day=1, tz="America/New_York")
    t1 = t0 + pd.offsets.MonthBegin(1)
    return t0, t1


def _week_bounds(ts):
    import pandas as pd

    local = pd.Timestamp(ts)
    if local.tzinfo is None:
        local = local.tz_localize("America/New_York")
    else:
        local = local.tz_convert("America/New_York")
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    return monday, monday + pd.Timedelta(days=7)


def _is_last_bar_of_period(dt: datetime, period_end, bar_hours: float = 4.0) -> bool:
    import pandas as pd

    ts = pd.Timestamp(dt)
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/New_York")
    hours = float(bar_hours) if bar_hours and bar_hours > 0 else 4.0
    return (ts + pd.Timedelta(hours=hours)) >= period_end and ts < period_end


def _is_last_bar_of_quarter(dt: datetime, q_end) -> bool:
    return _is_last_bar_of_period(dt, q_end, 4.0)


def _period_expiry(pkey: str, period: str = "quarter") -> str:
    import pandas as pd

    if not pkey:
        return ""
    try:
        if period == "month" or "M" in pkey:
            if "M" not in pkey:
                return ""
            year_s, month_s = pkey.split("M", 1)
            t0 = pd.Timestamp(
                year=int(year_s), month=int(month_s), day=1, tz="America/New_York"
            )
            t1 = t0 + pd.offsets.MonthBegin(1)
            return t1.tz_convert("UTC").isoformat().replace("+00:00", "Z")
        return _quarter_expiry(pkey)
    except Exception:
        return ""


def _quarter_expiry(qkey: str) -> str:
    import pandas as pd

    if not qkey or "Q" not in qkey:
        return ""
    try:
        year_s, q_s = qkey.split("Q", 1)
        year = int(year_s)
        q = int(q_s)
        month0 = 1 + (q - 1) * 3
        t0 = pd.Timestamp(year=year, month=month0, day=1, tz="America/New_York")
        t1 = t0 + pd.offsets.MonthBegin(3)
        return t1.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
