"""Intraday ATR SuperTrend DCA (15m-oriented).

Rules
-----
- Evaluate only on completed bars of ``config.timeframe`` (default ``15m``).
- Trade only inside London cash open → NY cash close.
- Direction from SuperTrend: bullish → long, bearish → short.
- Scale in ``add_qty`` each eligible bar while side holds, up to ``max_adds``.
- Exit modes:
  - ``close`` (default): flatten only when the bar *closes* beyond the trail
    (no resting stop → wicks do not exit).
  - ``wick``: resting protective stop at the SuperTrend trail (wick can fill).
- Also flatten on ST flip (close-confirmed) and session end.
"""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any, Dict, List, Optional

import pytz

from ..models import Bar, CancelIntent, OrderIntent, StrategyActions
from .atr_supertrend_dca import TrendPoint
from .base import StrategyContext, StrategyPlugin


NY = "America/New_York"
LDN = "Europe/London"
NY_TZ = pytz.timezone(NY)
LDN_TZ = pytz.timezone(LDN)
LONDON_OPEN = time(8, 0)
NY_CLOSE = time(16, 0)


def _in_session(ts: str) -> bool:
    dt = datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    ny = dt.astimezone(NY_TZ)
    d = ny.date()
    lo = LDN_TZ.localize(datetime.combine(d, LONDON_OPEN)).astimezone(NY_TZ)
    hi = NY_TZ.localize(datetime.combine(d, NY_CLOSE))
    return lo <= ny <= hi


class IntradayStDcaStrategy(StrategyPlugin):
    strategy_type = "intraday_st_dca"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "timeframe": "15m",
            "atr_len": 14,
            "atr_mult": 3.0,
            "add_qty": 1,
            "max_adds": 5,
            "tick_size": 1e-5,
            "session_gate": True,
            # "close" = exit only if bar closes beyond trail; "wick" = resting stop
            "exit_mode": "close",
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._bars_cache: Optional[List[Bar]] = None
        self._tf = str(self.config.get("timeframe") or "15m")
        self._st_processed = 0
        self._st_trs: List[float] = []
        self._st_atr: Optional[float] = None
        self._st_final_upper: Optional[float] = None
        self._st_final_lower: Optional[float] = None
        self._st_bullish = True
        self._st_points: List[TrendPoint] = []

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != self._tf or not bar.complete:
            return StrategyActions.empty()
        return self._on_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        if fill.reason in {"entry", "add"}:
            state["active_trade_id"] = fill.trade_id
            state["adds"] = int(state.get("adds") or 0) + 1
            state["side"] = (
                "long"
                if context.position_quantity > 0
                else "short"
                if context.position_quantity < 0
                else state.get("side")
            )
            self.state = state
            self.save_state()
        elif fill.reason in {
            "stop",
            "protective_stop",
            "trail_close",
            "close",
            "session_end",
            "st_flip",
        }:
            if context.position_quantity == 0:
                state["active_trade_id"] = ""
                state["adds"] = 0
                state["side"] = ""
                state["close_pending"] = ""
                self.state = state
                self.save_state()
        return StrategyActions.empty()

    def _exit_mode(self) -> str:
        mode = str(self.config.get("exit_mode") or "close").strip().lower()
        return mode if mode in {"close", "wick"} else "close"

    def _on_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        bars = self._bars(bar)
        now = self._current_trend_point(bars)
        if now is None or len(self._st_points) < 2:
            return StrategyActions.empty()
        prev = self._st_points[-2]
        in_sess = (not bool(self.config.get("session_gate"))) or _in_session(bar.ts)

        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        qty_pos = int(context.position_quantity)
        add_qty = max(1, int(self.config["add_qty"]))
        max_adds = max(1, int(self.config["max_adds"]))
        trade_id = state.get("active_trade_id") or self._next_trade_id(state)
        exit_mode = self._exit_mode()

        if qty_pos != 0 and not in_sess:
            cancels.extend(self._cancel_stops(context, "session_end"))
            orders.append(self._flatten(state, trade_id, qty_pos, bar.ts, "session_end"))
            state["close_pending"] = "session_end"
            state["active_trade_id"] = trade_id
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        if not in_sess:
            return StrategyActions.empty()

        want_long = bool(now.bullish)
        want_short = not want_long

        if qty_pos != 0:
            side = "long" if qty_pos > 0 else "short"
            # Close-confirmed flip against position
            if (side == "long" and want_short) or (side == "short" and want_long):
                cancels.extend(self._cancel_stops(context, "st_flip"))
                orders.append(self._flatten(state, trade_id, qty_pos, bar.ts, "st_flip"))
                state["close_pending"] = "st_flip"
                state["active_trade_id"] = trade_id
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], [], [], [])

            # Close-only trail: exit if close is beyond the protective ST level
            if exit_mode == "close":
                trail = float(now.stop)
                closed_through = (side == "long" and float(bar.close) < trail) or (
                    side == "short" and float(bar.close) > trail
                )
                if closed_through:
                    cancels.extend(self._cancel_stops(context, "trail_close"))
                    orders.append(self._flatten(state, trade_id, qty_pos, bar.ts, "trail_close"))
                    state["close_pending"] = "trail_close"
                    state["active_trade_id"] = trade_id
                    self.state = state
                    self.save_state()
                    return StrategyActions(orders, cancels, [], [], [], [])

            adds = int(state.get("adds") or 0)
            planned_qty = abs(qty_pos)
            if adds < max_adds and abs(qty_pos) < int(self.instance.max_contracts):
                room = min(
                    add_qty,
                    int(self.instance.max_contracts) - abs(qty_pos),
                    max_adds - adds,
                )
                if room > 0:
                    orders.append(
                        OrderIntent.create(
                            strategy_id=self.instance.strategy_id,
                            trade_id=trade_id,
                            instrument=self.instance.instrument,
                            account_mode=self.instance.account_mode,
                            side="buy" if side == "long" else "sell",
                            order_type="market",
                            quantity=room,
                            reason="add",
                            requires_verification=True,
                            bracket_role="add",
                            live_after_ts=bar.ts,
                        )
                    )
                    planned_qty += room

            if exit_mode == "wick":
                # Resting protective stop for full (planned) size at current trail.
                cancels.extend(self._cancel_stops(context, "refresh_trail"))
                orders.append(
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=trade_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side="sell" if side == "long" else "buy",
                        order_type="stop",
                        quantity=planned_qty,
                        stop_price=float(now.stop),
                        reason="protective_stop",
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role="stop",
                        live_after_ts=bar.ts,
                    )
                )
            else:
                # Ensure no leftover resting stops from a prior mode.
                cancels.extend(self._cancel_stops(context, "close_exit_mode"))

            state["active_trade_id"] = trade_id
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        # Flat — enter if prior completed ST side is clear
        if state.get("close_pending"):
            state["close_pending"] = ""
        prior_long = prev.bullish
        prior_short = not prev.bullish
        if not (prior_long or prior_short):
            self.state = state
            self.save_state()
            return StrategyActions.empty()
        if prior_long and want_long:
            side = "long"
        elif prior_short and want_short:
            side = "short"
        else:
            self.state = state
            self.save_state()
            return StrategyActions.empty()

        trade_id = self._next_trade_id(state)
        state["active_trade_id"] = trade_id
        state["adds"] = 0
        state["side"] = side
        self.state = state
        self.save_state()
        entry_kwargs: Dict[str, Any] = {
            "strategy_id": self.instance.strategy_id,
            "trade_id": trade_id,
            "instrument": self.instance.instrument,
            "account_mode": self.instance.account_mode,
            "side": "buy" if side == "long" else "sell",
            "order_type": "market",
            "quantity": add_qty,
            "reason": "entry",
            "requires_verification": True,
            "bracket_role": "entry",
            "live_after_ts": bar.ts,
        }
        if exit_mode == "wick":
            entry_kwargs["bracket_stop_price"] = float(now.stop)
        orders.append(OrderIntent.create(**entry_kwargs))
        return StrategyActions(orders, cancels, [], [], [], [])

    def _flatten(self, state: Dict[str, Any], trade_id: str, qty_pos: int, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if qty_pos > 0 else "buy",
            order_type="market",
            quantity=abs(qty_pos),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="close",
            live_after_ts=ts,
        )

    def _bars(self, bar: Bar) -> List[Bar]:
        if self._bars_cache is None:
            self._bars_cache = list(self.store.read_bars(self.instance.instrument, self._tf))
        if not self._bars_cache or self._bars_cache[-1].ts != bar.ts:
            self._bars_cache.append(bar)
        return self._bars_cache

    def _current_trend_point(self, hourly: List[Bar]) -> Optional[TrendPoint]:
        if self._st_processed > len(hourly):
            self._reset_supertrend_cache()
        atr_len = int(self.config["atr_len"])
        atr_mult = float(self.config["atr_mult"])
        for idx in range(self._st_processed, len(hourly)):
            bar = hourly[idx]
            if idx == 0:
                tr = bar.high - bar.low
            else:
                prev_close = hourly[idx - 1].close
                tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
            self._st_trs.append(float(tr))
            if idx < atr_len - 1:
                self._st_processed += 1
                continue
            if idx == atr_len - 1:
                atr = sum(self._st_trs[:atr_len]) / float(atr_len)
                self._st_atr = atr
                hl2 = (bar.high + bar.low) / 2.0
                self._st_final_upper = hl2 + atr_mult * atr
                self._st_final_lower = hl2 - atr_mult * atr
                self._st_bullish = bar.close >= hl2
            else:
                assert self._st_atr is not None
                assert self._st_final_upper is not None
                assert self._st_final_lower is not None
                atr = (self._st_atr * (atr_len - 1) + tr) / float(atr_len)
                self._st_atr = atr
                hl2 = (bar.high + bar.low) / 2.0
                basic_upper = hl2 + atr_mult * atr
                basic_lower = hl2 - atr_mult * atr
                prev_upper = self._st_final_upper
                prev_lower = self._st_final_lower
                prev_close = hourly[idx - 1].close
                self._st_final_upper = (
                    basic_upper if basic_upper < prev_upper or prev_close > prev_upper else prev_upper
                )
                self._st_final_lower = (
                    basic_lower if basic_lower > prev_lower or prev_close < prev_lower else prev_lower
                )
                if self._st_bullish and bar.close < self._st_final_lower:
                    self._st_bullish = False
                elif (not self._st_bullish) and bar.close > self._st_final_upper:
                    self._st_bullish = True
            stop = self._st_final_lower if self._st_bullish else self._st_final_upper
            self._st_points.append(TrendPoint(ts=bar.ts, stop=float(stop), bullish=bool(self._st_bullish)))
            self._st_processed += 1
        return self._st_points[-1] if self._st_points else None

    def _reset_supertrend_cache(self) -> None:
        self._st_processed = 0
        self._st_trs = []
        self._st_atr = None
        self._st_final_upper = None
        self._st_final_lower = None
        self._st_bullish = True
        self._st_points = []

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("trade_seq", 0)
        state.setdefault("active_trade_id", "")
        state.setdefault("adds", 0)
        state.setdefault("side", "")
        state.setdefault("close_pending", "")
        return state

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_t%d" % (self.instance.strategy_id, state["trade_seq"])

    def _cancel_stops(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only and order.order_type in {"stop", "limit"}:
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out
