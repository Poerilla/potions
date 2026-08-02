"""Q1 fakeout reversal satellite (OR-profile stable-tail-cell strategy).

Trades the strongest cross-market stable cell from the OR profile engine:
on narrow-OR days (trailing-250-session OR-width quartile q1), a morning
first break that fails quickly flips to an opposite-boundary break with
p = 0.86-0.93 in all four profiled futures markets (NQ/MNQ/YM/MYM,
14+ years of yearly sign stability).

Session flow (NY RTH, all thresholds fixed a priori from the tables):

1. Build opening range **09:30-09:45**; R = OR width.
2. Gate: OR width must be **q1** vs the trailing 250 completed sessions
   (needs >= ``min_history`` prior sessions; the history is maintained
   causally in plugin state and updated at OR finalize).
3. Watch for the first **touch** break (1m high/low pierces ORH/ORL)
   before ``break_cutoff`` (default 10:30 — late failed breaks flip at
   only ~0.46 and are excluded). Same-bar dual break -> skip session.
4. Failed break = a **5m-aligned close back inside the OR** within
   ``fail_cutoff_bars5`` (default 2) completed 5m candles of the break
   (the empirical p75 of failed-break re-entry timing). If the break hits
   1R first, or the cutoff lapses, the session is done (no trade).
5. On failure confirm: enter **market** toward the opposite boundary.
   - Stop = the failed-break extreme +/- 1 tick (tight risk at the wick).
   - ``tp_mode``:
     - ``split`` (default, entry_qty >= 2): 1 unit at the **opposite
       boundary** (the 0.92 traverse), rest at **opposite 1R** (the
       fakeout->opposite completion, p ~0.17-0.28).
     - ``opp_boundary``: all units at the opposite boundary.
6. One trade per session; EOD flatten 15:59.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class Q1FakeoutReversalStrategy(StrategyPlugin):
    strategy_type = "q1_fakeout_reversal"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 2,
            "tp_mode": "split",  # split | opp_boundary
            "or_width_trail": 250,
            "min_history": 50,
            "q_max_pctile": 25.0,  # q1 = trailing percentile < 25
            "break_cutoff": "10:30",
            "fail_cutoff_bars5": 2,
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

    # ------------------------------------------------------------------

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "1m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_1m_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)

        if fill.reason == "entry":
            trade.update(
                {
                    "status": "open",
                    "entry_price": float(fill.price),
                    "filled_qty": int(trade.get("filled_qty") or 0) + int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["phase"] = "in_trade"
            self._commit_state(state)
            return StrategyActions(
                self._exit_orders(fill.trade_id, str(trade.get("direction") or ""), state), [], [], [], []
            )

        if fill.reason in {"stop", "tp_opp_boundary", "tp_opp_1r", "eod_close", "eod"}:
            closed = int(trade.get("exit_qty") or 0) + int(fill.quantity)
            trade["exit_qty"] = closed
            if fill.reason == "stop" or closed >= int(trade.get("entry_qty") or 0):
                trade["status"] = "closed"
                state["current_leg_open"] = False
                state["done"] = True
                state["phase"] = "done"
                self._commit_state(state)
                return StrategyActions([], self._cancel_reduce_orders(context, fill.trade_id), [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    # ------------------------------------------------------------------

    def _on_1m_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        session = dt.date().isoformat()
        t = dt.time()
        state = self._state()
        if state.get("session_date") != session:
            state = self._fresh_session_state(session, prior=state)

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

        # -- OR build ----------------------------------------------------
        if t < self._time("or_end"):
            state["or_count"] = int(state.get("or_count", 0)) + 1
            state["or_high"] = bar.high if state.get("or_high") is None else max(float(state["or_high"]), bar.high)
            state["or_low"] = bar.low if state.get("or_low") is None else min(float(state["or_low"]), bar.low)
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            if int(state["or_count"]) >= 15 and not state.get("or_finalized"):
                state["or_finalized"] = True
                self._finalize_or(state, session)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if state.get("done") or not state.get("or_finalized") or not state.get("session_eligible"):
            self._commit_state(state)
            return StrategyActions.empty()
        if state.get("current_leg_open") or context.position_quantity != 0:
            self._commit_state(state)
            return StrategyActions.empty()

        or_high = float(state["or_high"])
        or_low = float(state["or_low"])
        r = or_high - or_low

        # -- watch for first touch break ---------------------------------
        if not state.get("break_side"):
            if t >= self._time("break_cutoff"):
                state["done"] = True
                state["phase"] = "no_morning_break"
                self._commit_state(state)
                return StrategyActions.empty()
            broke_up = bar.high > or_high
            broke_down = bar.low < or_low
            if broke_up and broke_down:
                state["done"] = True
                state["phase"] = "dual_break_skip"
            elif broke_up or broke_down:
                state["break_side"] = "up" if broke_up else "down"
                state["break_ts"] = bar.ts
                state["break_extreme"] = bar.high if broke_up else bar.low
                state["phase"] = "watching_fail"
            self._commit_state(state)
            return StrategyActions.empty()

        # -- after break: track extreme, abort on 1R, confirm failure ----
        side = str(state["break_side"])
        extreme = float(state.get("break_extreme") or (or_high if side == "up" else or_low))
        state["break_extreme"] = max(extreme, bar.high) if side == "up" else min(extreme, bar.low)

        hit_1r = bar.high >= or_high + r if side == "up" else bar.low <= or_low - r
        if hit_1r:
            state["done"] = True
            state["phase"] = "break_succeeded"
            self._commit_state(state)
            return StrategyActions.empty()

        bars5 = _bars5_between(str(state.get("break_ts") or bar.ts), bar.ts)
        if dt.minute % 5 == 4:  # this 1m close completes a 5m candle
            inside = or_low <= bar.close <= or_high
            if inside and bars5 <= int(self.config.get("fail_cutoff_bars5") or 2):
                entry = self._arm_entry(bar.ts, state, or_high, or_low, r)
                if entry is not None:
                    orders.append(entry)
                    state["phase"] = "entry_sent"
                    if not bool(self.config.get("suppress_alerts")):
                        alerts.append(
                            Alert.create(
                                self.instance.strategy_id,
                                "info",
                                "q1_fakeout_reversal: %s break failed, reversing" % side,
                            )
                        )
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], levels, alerts)

        if bars5 > int(self.config.get("fail_cutoff_bars5") or 2):
            state["done"] = True
            state["phase"] = "fail_window_lapsed"

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    # ------------------------------------------------------------------

    def _finalize_or(self, state: Dict[str, Any], session: str) -> None:
        or_high = _to_float(state.get("or_high"))
        or_low = _to_float(state.get("or_low"))
        width = (or_high - or_low) if (or_high is not None and or_low is not None) else None
        history: List[float] = [float(x) for x in (state.get("or_width_history") or [])]

        eligible = False
        if width is not None and width > 0:
            min_hist = int(self.config.get("min_history") or 50)
            trail = int(self.config.get("or_width_trail") or 250)
            if len(history) >= min_hist:
                window = history[-trail:]
                pctile = 100.0 * sum(1 for w in window if w <= width) / len(window)
                state["or_width_pctile"] = round(pctile, 1)
                eligible = pctile < float(self.config.get("q_max_pctile") or 25.0)
            # widths recorded regardless so the trail keeps building
            history.append(width)
            state["or_width_history"] = history[-(trail + 10) :]

        state["session_eligible"] = bool(eligible and self._regime_ok(session))
        state["phase"] = "watching_break" if state["session_eligible"] else "not_eligible"

    def _arm_entry(
        self, ts: str, state: Dict[str, Any], or_high: float, or_low: float, r: float
    ) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 2)
        if qty <= 0:
            return None
        tick = float(self.config.get("tick_size") or 0.25)
        side_break = str(state.get("break_side") or "")
        extreme = _to_float(state.get("break_extreme"))
        if extreme is None or side_break not in {"up", "down"}:
            return None
        trade_id = self._new_trade_id(state)
        if side_break == "up":
            direction, side = "Short", "sell"
            stop = extreme + tick
            tp_boundary = or_low
            tp_1r = or_low - r
        else:
            direction, side = "Long", "buy"
            stop = extreme - tick
            tp_boundary = or_high
            tp_1r = or_high + r

        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "break_side": side_break,
            "or_high": or_high,
            "or_low": or_low,
            "r": r,
            "stop": stop,
            "tp_opp_boundary": tp_boundary,
            "tp_opp_1r": tp_1r,
            "entry_qty": qty,
            "exit_qty": 0,
        }
        state["active_trade_id"] = trade_id
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=_session_expiry(ts),
        )

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp_boundary = _to_float(trade.get("tp_opp_boundary"))
        tp_1r = _to_float(trade.get("tp_opp_1r"))
        qty = int(trade.get("entry_qty") or 0)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or tp_boundary is None or tp_1r is None or qty <= 0 or not direction:
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
        mode = str(self.config.get("tp_mode") or "split")
        if mode == "split" and qty >= 2:
            out.append(self._tp_limit(trade_id, exit_side, 1, tp_boundary, "tp_opp_boundary", expiry))
            out.append(self._tp_limit(trade_id, exit_side, qty - 1, tp_1r, "tp_opp_1r", expiry))
        else:
            out.append(self._tp_limit(trade_id, exit_side, qty, tp_boundary, "tp_opp_boundary", expiry))
        return out

    def _tp_limit(
        self, trade_id: str, exit_side: str, qty: int, price: float, role: str, expiry: str
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

    # ------------------------------------------------------------------

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("session_date", "")
        state.setdefault("or_count", 0)
        state.setdefault("or_high", None)
        state.setdefault("or_low", None)
        state.setdefault("or_finalized", False)
        state.setdefault("session_eligible", False)
        state.setdefault("phase", "")
        state.setdefault("done", False)
        state.setdefault("break_side", "")
        state.setdefault("break_ts", "")
        state.setdefault("break_extreme", None)
        state.setdefault("trade_seq", 0)
        state.setdefault("current_leg_open", False)
        state.setdefault("active_trade_id", "")
        state.setdefault("trades", {})
        state.setdefault("or_width_history", [])
        return state

    def _fresh_session_state(self, session: str, prior: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "session_date": session,
            "or_count": 0,
            "or_high": None,
            "or_low": None,
            "or_finalized": False,
            "session_eligible": False,
            "phase": "building_or",
            "done": False,
            "break_side": "",
            "break_ts": "",
            "break_extreme": None,
            "trade_seq": 0,
            "current_leg_open": False,
            "active_trade_id": "",
            "trades": {},
            # trailing OR-width history persists across sessions (causal:
            # only completed prior sessions are in it when today is gated)
            "or_width_history": list(prior.get("or_width_history") or []),
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
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "q1fr_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "q1fr_eod")
            for order in context.strategy_open_orders
        ]

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


def _bars5_between(start_ts: str, end_ts: str) -> int:
    try:
        delta = _parse_dt(end_ts) - _parse_dt(start_ts)
        return int(delta.total_seconds() // 300)
    except (ValueError, TypeError):
        return 0


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
