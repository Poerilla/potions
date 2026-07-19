"""Fade SuperTrend flips with DCA toward the new trailing stop.

On a close-confirmed ST flip:
- Flip bearish → DCA long, target = bearish ST (above), stop = entry − R
- Flip bullish → DCA short, target = bullish ST (below), stop = entry + R

R is the distance from the first entry fill to the ST trail at arming
(1R risk to a 1R target at the trail). Target is refreshed to the live trail;
stop stays fixed. Adds each bar while the fade thesis (ST side) holds, up to
``max_adds``. Session end flattens.
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


class IntradayStFadeDcaStrategy(StrategyPlugin):
    strategy_type = "intraday_st_fade_dca"
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
            px = float(fill.price)
            if not state.get("entry_px"):
                state["entry_px"] = px
                # Arm 1R stop from first fill vs target trail at arming.
                target = float(state.get("target_px") or 0.0)
                side = str(state.get("side") or "")
                if target > 0 and side in {"long", "short"}:
                    r = abs(target - px)
                    tick = float(self.config.get("tick_size") or 1e-5)
                    r = max(r, tick)
                    if side == "long":
                        state["stop_px"] = px - r
                    else:
                        state["stop_px"] = px + r
            state["side"] = (
                "long"
                if context.position_quantity > 0
                else "short"
                if context.position_quantity < 0
                else state.get("side")
            )
            self.state = state
            self.save_state()
            # Place/refresh brackets after we know stop from first fill.
            return self._brackets_only(context, state, fill.ts)
        if fill.reason in {"stop", "target", "session_end", "thesis_end", "close"}:
            if context.position_quantity == 0:
                self._clear_trade(state)
                self.state = state
                self.save_state()
        return StrategyActions.empty()

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

        if qty_pos != 0 and not in_sess:
            cancels.extend(self._cancel_exits(context, "session_end"))
            orders.append(self._flatten(trade_id, qty_pos, bar.ts, "session_end"))
            state["close_pending"] = "session_end"
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        if not in_sess:
            return StrategyActions.empty()

        flipped_bear = prev.bullish and (not now.bullish)
        flipped_bull = (not prev.bullish) and now.bullish

        if qty_pos != 0:
            side = "long" if qty_pos > 0 else "short"
            thesis_bullish_st = bool(state.get("thesis_bullish_st"))
            # Fade long requires bearish ST; fade short requires bullish ST.
            thesis_ok = (side == "long" and not now.bullish) or (side == "short" and now.bullish)
            if not thesis_ok:
                cancels.extend(self._cancel_exits(context, "thesis_end"))
                orders.append(self._flatten(trade_id, qty_pos, bar.ts, "thesis_end"))
                state["close_pending"] = "thesis_end"
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], [], [], [])

            # Close-only risk: exit if bar closes beyond fixed stop.
            stop_px = state.get("stop_px")
            if stop_px is not None:
                stop_px = float(stop_px)
                hit = (side == "long" and float(bar.close) < stop_px) or (
                    side == "short" and float(bar.close) > stop_px
                )
                if hit:
                    cancels.extend(self._cancel_exits(context, "stop"))
                    orders.append(self._flatten(trade_id, qty_pos, bar.ts, "stop"))
                    state["close_pending"] = "stop"
                    self.state = state
                    self.save_state()
                    return StrategyActions(orders, cancels, [], [], [], [])

            # Close-only target: exit if close reaches/through live ST trail.
            target = float(now.stop)
            state["target_px"] = target
            reached = (side == "long" and float(bar.close) >= target) or (
                side == "short" and float(bar.close) <= target
            )
            if reached:
                cancels.extend(self._cancel_exits(context, "target"))
                orders.append(self._flatten(trade_id, qty_pos, bar.ts, "target"))
                state["close_pending"] = "target"
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], [], [], [])

            adds = int(state.get("adds") or 0)
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

            # Resting limit at live trail; risk stop is close-only (above).
            cancels.extend(self._cancel_exits(context, "refresh_target"))
            if state.get("stop_px") is not None:
                orders.append(
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=trade_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side="sell" if side == "long" else "buy",
                        order_type="limit",
                        quantity=max(abs(qty_pos), 1),
                        limit_price=float(now.stop),
                        reason="target",
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role="target",
                        live_after_ts=bar.ts,
                    )
                )
            state["thesis_bullish_st"] = thesis_bullish_st
            state["active_trade_id"] = trade_id
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        # Flat — arm fade only on flip bars
        if state.get("close_pending"):
            state["close_pending"] = ""
            self._clear_trade(state)

        if not (flipped_bear or flipped_bull):
            self.state = state
            self.save_state()
            return StrategyActions.empty()

        if flipped_bear:
            side = "long"
            thesis_bullish_st = False
        else:
            side = "short"
            thesis_bullish_st = True

        trade_id = self._next_trade_id(state)
        state["active_trade_id"] = trade_id
        state["adds"] = 0
        state["side"] = side
        state["thesis_bullish_st"] = thesis_bullish_st
        state["target_px"] = float(now.stop)
        state["entry_px"] = 0.0
        state["stop_px"] = None
        self.state = state
        self.save_state()
        orders.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="buy" if side == "long" else "sell",
                order_type="market",
                quantity=add_qty,
                reason="entry",
                requires_verification=True,
                bracket_role="entry",
                live_after_ts=bar.ts,
            )
        )
        return StrategyActions(orders, cancels, [], [], [], [])

    def _brackets_only(self, context: StrategyContext, state: Dict[str, Any], ts: str) -> StrategyActions:
        qty = abs(int(context.position_quantity))
        if qty <= 0 or state.get("stop_px") is None:
            return StrategyActions.empty()
        side = str(state.get("side") or "")
        trade_id = state.get("active_trade_id") or ""
        target = float(state.get("target_px") or 0.0)
        cancels = self._cancel_exits(context, "post_fill_brackets")
        orders = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="sell" if side == "long" else "buy",
                order_type="limit",
                quantity=qty,
                limit_price=target,
                reason="target",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                live_after_ts=ts,
            )
        ]
        return StrategyActions(orders, cancels, [], [], [], [])

    def _clear_trade(self, state: Dict[str, Any]) -> None:
        state["active_trade_id"] = ""
        state["adds"] = 0
        state["side"] = ""
        state["close_pending"] = ""
        state["entry_px"] = 0.0
        state["stop_px"] = None
        state["target_px"] = 0.0
        state["thesis_bullish_st"] = None

    def _flatten(self, trade_id: str, qty_pos: int, ts: str, reason: str) -> OrderIntent:
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
        state.setdefault("entry_px", 0.0)
        state.setdefault("stop_px", None)
        state.setdefault("target_px", 0.0)
        state.setdefault("thesis_bullish_st", None)
        return state

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_t%d" % (self.instance.strategy_id, state["trade_seq"])

    def _cancel_exits(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only and order.order_type in {"stop", "limit"}:
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out
