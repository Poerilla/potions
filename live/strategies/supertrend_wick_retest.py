from __future__ import annotations

import json
from datetime import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..models import Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions
from .base import StrategyContext, StrategyPlugin


class SupertrendWickRetestStrategy(StrategyPlugin):
    """Supertrend wick-retest entry with next-bar-open execution.

    Rules:
    - Compute an RTH-session Supertrend on the incoming strategy timeframe.
    - Long setup: bullish ST, bar low touches ST, bar closes back above ST.
    - Short setup: bearish ST, bar high touches ST, bar closes back below ST.
    - Enter on the next bar open with a market order.
    - Keep the trade only if the touch bar confirms as a 1-left / 2-right
      swing low/high; otherwise flatten at the confirmation bar close.
    - Exit on fixed target, close through Supertrend, or EOD.
    """

    strategy_type = "supertrend_wick_retest"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "timeframe": "3m",
            "atr_len": 14,
            "atr_mult": 2.0,
            "target_pts": 50.0,
            "tick_size": 0.25,
            "entry_qty": 1,
            "max_trades_per_day": 4,
            "entry_cutoff": "15:45",
            "eod_cutoff": "15:59",
            "record_levels": False,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

        self._session_key = ""
        self._bars: List[Bar] = []
        self._trs: List[float] = []
        self._atr: Optional[float] = None
        self._final_upper: Optional[float] = None
        self._final_lower: Optional[float] = None
        self._trend = 1
        self._st: Optional[float] = None

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != str(self.config["timeframe"]) or not bar.complete:
            return StrategyActions.empty()
        session_key = self._session_date(bar.ts)
        if session_key != self._session_key:
            self._reset_session(session_key)

        idx, st_level, trend = self._update_supertrend(bar)
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []

        if bool(self.config.get("record_levels")) and st_level is not None:
            levels.append(
                LevelUpdate(
                    self.instance.strategy_id,
                    self.instance.instrument,
                    "supertrend_bull" if trend == 1 else "supertrend_bear",
                    st_level,
                    bar.ts,
                )
            )

        if self._is_eod(bar.ts) and context.position_quantity != 0:
            cancels.extend(self._cancel_reduce_orders(context, "eod_flat"))
            orders.append(self._close_order(context, bar.ts, "eod_flat"))
            state["close_pending"] = "eod_flat"
            self._save_state(state)
            return StrategyActions(orders, cancels, [], levels, [])

        if context.position_quantity != 0:
            close_reason = self._active_close_reason(bar, state, st_level)
            if close_reason and not self._has_close_order(context):
                cancels.extend(self._cancel_reduce_orders(context, close_reason))
                orders.append(self._close_order(context, bar.ts, close_reason))
                state["close_pending"] = close_reason
                self._save_state(state)
            return StrategyActions(orders, cancels, [], levels, [])

        if state.get("active_trade_id"):
            state["active_trade_id"] = ""
            state["close_pending"] = ""
            self._save_state(state)

        if state.get("pending_entry_trade_id"):
            return StrategyActions([], [], [], levels)
        if int(state.get("trades_today") or 0) >= int(self.config["max_trades_per_day"]):
            return StrategyActions([], [], [], levels)
        if not self._before_entry_cutoff(bar.ts):
            return StrategyActions([], [], [], levels)
        if st_level is None:
            return StrategyActions([], [], [], levels)

        side = self._setup_side(bar, st_level, trend)
        if side is None:
            return StrategyActions([], [], [], levels)

        trade_id = self._next_trade_id(state)
        state.update(
            {
                "pending_entry_trade_id": trade_id,
                "pending_side": side,
                "pending_signal_idx": idx,
                "pending_signal_ts": bar.ts,
                "pending_signal_st": st_level,
            }
        )
        orders.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="buy" if side == "long" else "sell",
                order_type="market",
                quantity=int(self.config["entry_qty"]),
                reason="entry",
                requires_verification=False,
                bracket_role="entry",
                live_after_ts=bar.ts,
            )
        )
        self._save_state(state)
        return StrategyActions(orders, [], [], levels, [])

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        orders: List[OrderIntent] = []
        if fill.reason == "entry":
            side = state.get("pending_side") or ("long" if fill.side == "buy" else "short")
            target_pts = float(self.config["target_pts"])
            target_px = float(fill.price) + target_pts if side == "long" else float(fill.price) - target_pts
            state.update(
                {
                    "active_trade_id": fill.trade_id,
                    "active_side": side,
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "signal_idx": int(state.get("pending_signal_idx") or 0),
                    "swing_checked": False,
                    "pending_entry_trade_id": "",
                    "pending_side": "",
                    "close_pending": "",
                }
            )
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=fill.trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="sell" if side == "long" else "buy",
                    order_type="limit",
                    quantity=int(fill.quantity),
                    limit_price=target_px,
                    reason="target_%g" % target_pts,
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="target",
                    oco_group="%s_exit" % fill.trade_id,
                )
            )
            self._save_state(state)
        elif fill.reason in {"target", "target_%g" % float(self.config["target_pts"]), "close", "trend_break_close", "not_swing_confirmed", "eod_flat", "market_close"}:
            if context.position_quantity == 0:
                state["active_trade_id"] = ""
                state["active_side"] = ""
                state["close_pending"] = ""
                state["trades_today"] = int(state.get("trades_today") or 0) + 1
                self._save_state(state)
        return StrategyActions(orders, [], [], [], [])

    def _update_supertrend(self, bar: Bar) -> Tuple[int, Optional[float], int]:
        prev_close = self._bars[-1].close if self._bars else None
        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev_close) if prev_close is not None else bar.high - bar.low,
            abs(bar.low - prev_close) if prev_close is not None else bar.high - bar.low,
        )
        self._trs.append(float(tr))
        alpha = 1.0 / float(self.config["atr_len"])
        self._atr = tr if self._atr is None else alpha * tr + (1.0 - alpha) * self._atr
        idx = len(self._bars)
        self._bars.append(bar)
        if len(self._trs) < int(self.config["atr_len"]):
            return idx, None, self._trend

        hl2 = (bar.high + bar.low) / 2.0
        basic_upper = hl2 + float(self.config["atr_mult"]) * float(self._atr)
        basic_lower = hl2 - float(self.config["atr_mult"]) * float(self._atr)
        if self._final_upper is None or len(self._bars) <= 1:
            self._final_upper = basic_upper
            self._final_lower = basic_lower
        else:
            prev_bar = self._bars[-2]
            if basic_upper < self._final_upper or prev_bar.close > self._final_upper:
                self._final_upper = basic_upper
            if basic_lower > self._final_lower or prev_bar.close < self._final_lower:
                self._final_lower = basic_lower

        if self._trend == 1:
            self._trend = -1 if bar.close < float(self._final_lower) else 1
        else:
            self._trend = 1 if bar.close > float(self._final_upper) else -1
        self._st = float(self._final_lower) if self._trend == 1 else float(self._final_upper)
        return idx, self._st, self._trend

    def _setup_side(self, bar: Bar, st_level: float, trend: int) -> Optional[str]:
        if trend == 1 and bar.low <= st_level and bar.close > st_level:
            return "long"
        if trend == -1 and bar.high >= st_level and bar.close < st_level:
            return "short"
        return None

    def _active_close_reason(self, bar: Bar, state: Dict[str, Any], st_level: Optional[float]) -> str:
        side = state.get("active_side", "")
        if not side:
            return ""
        if st_level is not None:
            if side == "long" and bar.close < st_level:
                return "trend_break_close"
            if side == "short" and bar.close > st_level:
                return "trend_break_close"
        signal_idx = int(state.get("signal_idx") or -1)
        if not bool(state.get("swing_checked")) and signal_idx >= 1 and len(self._bars) - 1 >= signal_idx + 2:
            state["swing_checked"] = True
            if not self._confirms_swing(signal_idx, side):
                self._save_state(state)
                return "not_swing_confirmed"
            self._save_state(state)
        return ""

    def _confirms_swing(self, signal_idx: int, side: str) -> bool:
        row = self._bars[signal_idx]
        prev = self._bars[signal_idx - 1]
        nxt1 = self._bars[signal_idx + 1]
        nxt2 = self._bars[signal_idx + 2]
        if side == "long":
            return row.low <= prev.low and row.low <= nxt1.low and row.low <= nxt2.low
        return row.high >= prev.high and row.high >= nxt1.high and row.high >= nxt2.high

    def _close_order(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        side = "sell" if context.position_quantity > 0 else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=self._state().get("active_trade_id") or self.instance.strategy_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market_close",
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            oco_group="%s_exit" % (self._state().get("active_trade_id") or self.instance.strategy_id),
            live_after_ts=ts,
        )

    def _cancel_reduce_orders(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, reason)
            for order in context.strategy_open_orders
            if order.reduce_only
        ]

    def _has_close_order(self, context: StrategyContext) -> bool:
        return any(order.reduce_only and order.order_type == "market_close" for order in context.strategy_open_orders)

    def _state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = dict(self.state or {})
        state.setdefault("trade_seq", 0)
        state.setdefault("trades_today", 0)
        state.setdefault("pending_entry_trade_id", "")
        state.setdefault("active_trade_id", "")
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        seq = int(state.get("trade_seq") or 0) + 1
        state["trade_seq"] = seq
        return "%s_%05d" % (self.instance.strategy_id, seq)

    def _reset_session(self, session_key: str) -> None:
        self._session_key = session_key
        self._bars = []
        self._trs = []
        self._atr = None
        self._final_upper = None
        self._final_lower = None
        self._trend = 1
        self._st = None
        state = self._state()
        state["trades_today"] = 0
        state["session"] = session_key
        self._save_state(state)

    def _session_date(self, ts: str) -> str:
        return pd.Timestamp(ts).tz_convert("America/New_York").date().isoformat()

    def _time_et(self, ts: str) -> time:
        return pd.Timestamp(ts).tz_convert("America/New_York").time()

    def _parse_time(self, value: str) -> time:
        hour, minute = str(value).split(":")[:2]
        return time(int(hour), int(minute))

    def _before_entry_cutoff(self, ts: str) -> bool:
        return self._time_et(ts) <= self._parse_time(str(self.config["entry_cutoff"]))

    def _is_eod(self, ts: str) -> bool:
        return self._time_et(ts) >= self._parse_time(str(self.config["eod_cutoff"]))
