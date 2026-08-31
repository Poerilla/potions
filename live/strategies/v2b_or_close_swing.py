"""NQ v2b-style OR breakout with close+swing limit entry (ungated).

Session clock is RTH 09:30–16:00 America/New_York on **5m** bars:

1. Build the classic **15-minute opening range** from 5m bars whose left
   edge is in ``[rth_start, or_end)`` (default 09:30–09:45 → three 5m bars).
2. Wait for a 5m candle that **closes** outside the OR (not OCO / stop).
3. Wait for the first causal 1-bar fractal swing after that breakout
   (pullback candle required by default) and arm a **limit** at the swing
   close.
4. Risk uses v2b OR geometry (SL = far OR edge, TP1=1R, TP2=2R) **shifted**
   by ``(swing_close − OR near edge)`` so R distance matches the classic
   book while entry is at the swing.
5. No bull / vol / MA regime filter. One campaign per session. EOD flatten.

Designed for Engine signal-on-5m + PaperBroker fills-on-1m replays.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pytz

from ..models import Alert, Bar, CancelIntent, FeatureSnapshot, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot

NY = pytz.timezone("America/New_York")


class V2BOrCloseSwingStrategy(StrategyPlugin):
    strategy_type = "v2b_or_close_swing"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            # NQ book-of-record S_1_1_3
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "rth_start": "09:30",
            "or_end": "09:45",
            # Number of 5m bars expected inside [rth_start, or_end) (15m OR → 3).
            "or_bars": 3,
            # Flatten on/after this left-label 5m bar (15:55–16:00 is last RTH bar).
            "eod_cutoff": "15:55",
            "session_end": "16:00",
            "bar_minutes": 5,
            "max_campaigns": 1,
            "swing_require_pullback": True,
            "record_levels": False,
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    # ------------------------------------------------------------------
    # Engine hooks
    # ------------------------------------------------------------------

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        tf = str(bar.timeframe or "").lower()
        if tf not in {"5m", "5min", "5minute"} or not bar.complete:
            return StrategyActions.empty()
        return self._on_5m(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            trade.update(
                {
                    "direction": direction,
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "status": "open",
                    "tp1_hit": False,
                }
            )
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = direction
            state["entry_pending"] = False
            state["phase"] = "in_trade"
            orders = self._initial_exit_orders(fill.trade_id, direction, state)
            self._commit(state)
            return StrategyActions(orders, [], [], [], [])

        if role == "tp1":
            trade["tp1_hit"] = True
            cancels = self._cancel_open_roles(context, fill.trade_id, {"wide_stop", "tp2"})
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                direction = str(trade.get("direction") or state.get("active_direction") or "")
                orders.extend(self._runner_exit_orders(fill.trade_id, direction, state))
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"wide_stop", "runner_stop", "tp2", "runner_tp", "eod_close"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                state["campaigns_done"] = int(state.get("campaigns_done") or 0) + 1
                state["active_trade_id"] = ""
                state["active_direction"] = ""
                state["phase"] = "done" if int(state.get("campaigns_done") or 0) >= int(self.config["max_campaigns"]) else "flat"
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                self._commit(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit(state)
        return StrategyActions.empty()

    # ------------------------------------------------------------------
    # 5m path
    # ------------------------------------------------------------------

    def _on_5m(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        session = dt.date().isoformat()
        t = dt.time()
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []
        features: List[FeatureSnapshot] = []

        rth_start = self._time("rth_start")
        session_end = self._time("session_end")
        eod_cutoff = self._time("eod_cutoff")

        # Session roll: flatten any leftover broker position before starting a new day.
        if state.get("session_date") and state.get("session_date") != session:
            if context.position_quantity != 0 or self._has_open_entry(context):
                cancels.extend(self._cancel_all_open(context))
                if context.position_quantity != 0:
                    orders.append(self._close_all(context, bar.ts, "eod_close"))
                state["phase"] = "flatten_roll"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            state = self._fresh_session(session)
        elif state.get("session_date") != session:
            state = self._fresh_session(session)

        if t < rth_start or t >= session_end:
            self._commit(state)
            return StrategyActions.empty()

        # EOD flatten on last RTH 5m bar (left-label >= eod_cutoff).
        if t >= eod_cutoff:
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eod_close"))
            state["phase"] = "eod"
            state["done"] = True
            state["entry_pending"] = False
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        # Build OR from left-labeled 5m bars in [09:30, 09:45).
        or_end = self._time("or_end")
        need = int(self.config.get("or_bars") or 3)
        if t < or_end:
            hi = float(bar.high)
            lo = float(bar.low)
            state["or_high"] = hi if state.get("or_high") is None else max(float(state["or_high"]), hi)
            state["or_low"] = lo if state.get("or_low") is None else min(float(state["or_low"]), lo)
            state["or_bars"] = int(state.get("or_bars") or 0) + 1
            state["phase"] = "build_or"
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        if not state.get("or_ready"):
            oh = _to_float(state.get("or_high"))
            ol = _to_float(state.get("or_low"))
            n_or = int(state.get("or_bars") or 0)
            if oh is None or ol is None or oh <= ol or n_or < need:
                state["phase"] = "or_invalid"
                state["done"] = True
                self._commit(state)
                return StrategyActions.empty()
            state["or_ready"] = True
            state["phase"] = "wait_breakout"
            features.append(
                feature_snapshot(
                    self.instance,
                    "v2b_or_ready",
                    bar.ts,
                    source="v2b_or_close_swing.5m",
                    value_ref="%.6f:%.6f" % (oh, ol),
                    metadata={"or_high": oh, "or_low": ol, "or_bars": n_or},
                )
            )

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if state.get("done") or str(state.get("phase")) in {"eod", "or_invalid", "done"}:
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        if context.position_quantity != 0 or state.get("entry_pending") or self._has_open_entry(context):
            # Keep resting limit / manage only via fills + EOD.
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        max_c = int(self.config.get("max_campaigns") or 1)
        if max_c > 0 and int(state.get("campaigns_done") or 0) >= max_c:
            state["phase"] = "done"
            self._commit(state)
            return StrategyActions.empty()

        phase = str(state.get("phase") or "wait_breakout")
        if phase == "wait_swing" or state.get("pending_breakout"):
            return self._on_wait_swing(bar, state, orders, cancels, levels, alerts, features)

        if phase != "wait_breakout":
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        oh = float(state["or_high"])
        ol = float(state["or_low"])
        close = float(bar.close)
        direction = None
        if close > oh:
            direction = "Long"
        elif close < ol:
            direction = "Short"
        if direction is None:
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        features.append(
            feature_snapshot(
                self.instance,
                "v2b_or_breakout_detect",
                bar.ts,
                source="v2b_or_close_swing.5m_close",
                value_ref="%s:%.6f" % (direction, close),
                metadata={
                    "direction": direction,
                    "or_high": oh,
                    "or_low": ol,
                    "breakout_close": close,
                    "breakout_high": float(bar.high),
                    "breakout_low": float(bar.low),
                },
            )
        )
        state["pending_breakout"] = {
            "direction": direction,
            "breakout_ts": bar.ts,
            "breakout_close": close,
            "breakout_high": float(bar.high),
            "breakout_low": float(bar.low),
            "breakout_open": float(bar.open),
        }
        state["post_bo_bars"] = [
            {
                "ts": bar.ts,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": close,
            }
        ]
        state["phase"] = "wait_swing"
        self._commit(state)
        return StrategyActions(orders, cancels, [], levels, alerts, features)

    def _on_wait_swing(
        self,
        bar: Bar,
        state: Dict[str, Any],
        orders: List[OrderIntent],
        cancels: List[CancelIntent],
        levels: List[LevelUpdate],
        alerts: List[Alert],
        features: List[FeatureSnapshot],
    ) -> StrategyActions:
        pending = dict(state.get("pending_breakout") or {})
        direction = str(pending.get("direction") or "")
        if not pending or direction not in {"Long", "Short"}:
            state["phase"] = "wait_breakout"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        post = list(state.get("post_bo_bars") or [])
        post.append(
            {
                "ts": bar.ts,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
            }
        )
        if len(post) > 96:
            post = post[-96:]
        state["post_bo_bars"] = post

        swing_close = None
        swing_ts = None
        require_pb = bool(self.config.get("swing_require_pullback", True))
        if len(post) >= 3:
            i = len(post) - 2
            prev_h, prev_l = float(post[i - 1]["high"]), float(post[i - 1]["low"])
            cand_o = float(post[i].get("open", post[i]["close"]))
            cand_h, cand_l = float(post[i]["high"]), float(post[i]["low"])
            cand_c = float(post[i]["close"])
            next_h, next_l = float(post[i + 1]["high"]), float(post[i + 1]["low"])
            is_fractal = False
            if direction == "Short" and cand_h > prev_h and cand_h > next_h:
                is_fractal = True
            elif direction == "Long" and cand_l < prev_l and cand_l < next_l:
                is_fractal = True
            if is_fractal and (
                (not require_pb) or _is_pullback_swing_bar(direction, cand_o, cand_h, cand_l, cand_c)
            ):
                swing_close = cand_c
                swing_ts = str(post[i]["ts"])

        if swing_close is None:
            state["phase"] = "wait_swing"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        entry = self._arm_swing_limit(bar, state, pending, float(swing_close), str(swing_ts or bar.ts))
        if entry is not None:
            orders.append(entry)
            state["entry_pending"] = True
            state["phase"] = "limit_armed"
            state.pop("pending_breakout", None)
            state.pop("post_bo_bars", None)
            features.append(
                feature_snapshot(
                    self.instance,
                    "v2b_swing_entry_arm",
                    bar.ts,
                    source="v2b_or_close_swing.swing_close",
                    value_ref="%s:%.6f" % (direction, swing_close),
                    metadata={
                        "direction": direction,
                        "swing_close": swing_close,
                        "swing_ts": swing_ts,
                        "breakout_close": pending.get("breakout_close"),
                        "breakout_ts": pending.get("breakout_ts"),
                        "or_high": state.get("or_high"),
                        "or_low": state.get("or_low"),
                        "limit_price": float(swing_close),
                        "stop": float(state.get("armed_stop") or 0.0),
                        "tp1": float(state.get("armed_tp1") or 0.0),
                        "tp2": float(state.get("armed_tp2") or 0.0),
                    },
                )
            )
            if not bool(self.config.get("suppress_alerts")):
                alerts.append(
                    Alert.create(
                        self.instance.strategy_id,
                        "info",
                        "v2b_or_close_swing arm %s @ %.2f" % (direction, swing_close),
                    )
                )
        self._commit(state)
        return StrategyActions(orders, cancels, [], levels, alerts, features)

    def _arm_swing_limit(
        self,
        bar: Bar,
        state: Dict[str, Any],
        pending: Dict[str, Any],
        swing_close: float,
        swing_ts: str,
    ) -> Optional[OrderIntent]:
        direction = str(pending.get("direction") or "")
        params = self._or_params(direction, state)
        if params is None:
            return None
        # Shift classic OR-edge geometry so entry is at swing close.
        delta = float(swing_close) - float(params["entry"])
        stop = float(params["init_sl"]) + delta
        tp1 = float(params["tp1"]) + delta
        tp2 = float(params["tp2"]) + delta
        runner_sl = float(swing_close)  # BE after TP1

        trade_id = self._new_trade_id(state)
        trade = self._trade(trade_id, state)
        trade.update(
            {
                "direction": direction,
                "limit_price": float(swing_close),
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "runner_sl": runner_sl,
                "or_high": float(state["or_high"]),
                "or_low": float(state["or_low"]),
                "breakout_ts": pending.get("breakout_ts"),
                "breakout_close": pending.get("breakout_close"),
                "swing_ts": swing_ts,
                "swing_close": float(swing_close),
                "entry_qty": int(self.config["entry_qty"]),
                "tp1_qty": int(self.config["tp1_qty"]),
                "tp2_qty": int(self.config["tp2_qty"]),
                "status": "armed",
            }
        )
        state["armed_trade_id"] = trade_id
        state["armed_stop"] = stop
        state["armed_tp1"] = tp1
        state["armed_tp2"] = tp2

        side = "buy" if direction == "Long" else "sell"
        live_after = _completion_ts(bar.ts, int(self.config.get("bar_minutes") or 5))
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=int(self.config["entry_qty"]),
            limit_price=float(swing_close),
            reason="entry",
            requires_verification=False,
            reduce_only=False,
            bracket_role="entry",
            live_after_ts=live_after,
            expires_after_ts=_session_expiry(str(state.get("session_date") or bar.ts)),
        )

    # ------------------------------------------------------------------
    # Exits (v2b S_1_1_3 ladder)
    # ------------------------------------------------------------------

    def _unit_quantities(self, trade: Dict[str, Any]) -> tuple:
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        tp1 = int(trade.get("tp1_qty") if trade.get("tp1_qty") is not None else self.config["tp1_qty"])
        tp2 = int(trade.get("tp2_qty") if trade.get("tp2_qty") is not None else self.config["tp2_qty"])
        runner = max(0, entry_qty - tp1 - tp2)
        return tp1, tp2, runner

    def _or_params(self, direction: str, state: Dict[str, Any]) -> Optional[Dict[str, float]]:
        oh = _to_float(state.get("or_high"))
        ol = _to_float(state.get("or_low"))
        if oh is None or ol is None or oh <= ol:
            return None
        r = oh - ol
        if direction == "Long":
            return {"entry": oh, "init_sl": ol, "tp1": oh + r, "tp2": oh + 2.0 * r}
        return {"entry": ol, "init_sl": oh, "tp1": ol - r, "tp2": ol - 2.0 * r}

    def _initial_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp1 = _to_float(trade.get("tp1"))
        tp2 = _to_float(trade.get("tp2"))
        if stop is None:
            return []
        tp1_qty, tp2_qty, _runner = self._unit_quantities(trade)
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        exit_side = "sell" if direction == "Long" else "buy"
        exp = _session_expiry(str(state.get("session_date") or ""))
        out: List[OrderIntent] = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=entry_qty,
                stop_price=float(stop),
                reason="wide_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="wide_stop",
                expires_after_ts=exp,
            )
        ]
        if tp1_qty > 0 and tp1 is not None:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=float(tp1),
                    reason="tp1",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp1",
                    expires_after_ts=exp,
                )
            )
        if tp2_qty > 0 and tp2 is not None:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=float(tp2),
                    reason="tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=exp,
                )
            )
        return out

    def _runner_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        _tp1_qty, tp2_qty, runner_qty = self._unit_quantities(trade)
        stack = max(0, tp2_qty + runner_qty)
        if stack <= 0:
            return []
        runner_sl = _to_float(trade.get("runner_sl")) or _to_float(trade.get("entry_price"))
        tp2 = _to_float(trade.get("tp2"))
        if runner_sl is None:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        exp = _session_expiry(str(state.get("session_date") or ""))
        out: List[OrderIntent] = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=stack,
                stop_price=float(runner_sl),
                reason="runner_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="runner_stop",
                expires_after_ts=exp,
            )
        ]
        if tp2_qty > 0 and tp2 is not None:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=float(tp2),
                    reason="tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=exp,
                )
            )
        return out

    # ------------------------------------------------------------------
    # State / helpers
    # ------------------------------------------------------------------

    def _state(self) -> Dict[str, Any]:
        if not self.state:
            self.state = self._fresh_session("")
        if "trades" not in self.state or not isinstance(self.state.get("trades"), dict):
            self.state["trades"] = {}
        return self.state

    def _commit(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _fresh_session(self, session: str) -> Dict[str, Any]:
        state = {
            "session_date": session,
            "phase": "build_or",
            "or_high": None,
            "or_low": None,
            "or_bars": 0,
            "or_ready": False,
            "pending_breakout": None,
            "post_bo_bars": [],
            "entry_pending": False,
            "campaigns_done": 0,
            "active_trade_id": "",
            "active_direction": "",
            "armed_trade_id": "",
            "trade_seq": 0,
            "trades": {},
            "done": False,
        }
        self.state = state
        if session:
            self.save_state()
        return state

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq") or 0) + 1
        return "%s_%s_%02d" % (
            self.instance.strategy_id,
            str(state.get("session_date", "")).replace("-", ""),
            int(state["trade_seq"]),
        )

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        oh = _to_float(state.get("or_high"))
        ol = _to_float(state.get("or_low"))
        if oh is None or ol is None:
            return []
        return [
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "v2b_or_high", oh, ts),
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "v2b_or_low", ol, ts),
        ]

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self._state().get("active_trade_id") or new_id("trade")),
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

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: Iterable[str]) -> List[CancelIntent]:
        role_set = set(roles)
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_ocs_cancel_%s" % order.bracket_role)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.bracket_role in role_set
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_ocs_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_ocs_eod")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _time(self, key: str) -> time:
        hh, mm = str(self.config[key]).split(":")
        return time(int(hh), int(mm))


def _is_pullback_swing_bar(direction: str, open_: float, high: float, low: float, close: float) -> bool:
    span = float(high) - float(low)
    mid = 0.5 * (float(high) + float(low))
    if direction == "Long":
        if float(close) < float(open_):
            return True
        return span > 0 and float(close) <= mid
    if direction == "Short":
        if float(close) > float(open_):
            return True
        return span > 0 and float(close) >= mid
    return False


def _parse_dt(ts: str) -> datetime:
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


def _completion_ts(ts: str, bar_minutes: int) -> str:
    dt = _parse_dt(ts) + timedelta(minutes=int(bar_minutes))
    return dt.astimezone(pytz.UTC).isoformat().replace("+00:00", "Z")


def _session_expiry(ts: str) -> str:
    raw = str(ts).strip()
    try:
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            session_day = date.fromisoformat(raw[:10])
        else:
            session_day = _parse_dt(raw).date()
    except ValueError:
        return raw
    return NY.localize(datetime.combine(session_day, time(15, 55))).isoformat()
