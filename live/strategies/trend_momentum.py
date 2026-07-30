"""Trend–momentum: with-trend momentum bar after pullback, trail completed pullbacks.

Assumptions (v1 — see live/state/trend_momentum/SPEC.md):
- Trend = last 2 confirmed swing highs/lows (HH+HL / LH+LL).
- Momentum bar = same-color body >= momentum_atr_mult * ATR(atr_len).
- Entry = stop 1 tick beyond momentum bar; live_after_ts = bar.ts.
- Initial stop = bar midpoint (or far side if narrow vs ATR).
- Trail = tighten only to completed pullback swing after trend resumes.
- Flatten on structure flip to opposite / none.
"""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytz

from ..models import Bar, CancelIntent, Fill, ModifyIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

NY_TZ = pytz.timezone("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


class TrendMomentumStrategy(StrategyPlugin):
    strategy_type = "trend_momentum"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 1,
            "max_contracts": 1,
            "atr_len": 14,
            "momentum_atr_mult": 1.0,
            "swing_lookback": 2,
            "min_pullback_bars": 2,
            "narrow_atr_frac": 0.5,
            "require_above_sma200": False,
            "momentum_near_sma10": False,
            "sma10_top_frac": 0.25,
            "signal_tf": "",  # empty → any timeframe on the instance
            "rth_only": False,
            "trend_end_flatten": True,
            "trend_end_mode": "opposite",  # opposite | opposite_or_none | off
            "history_bars": 500,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        # In-memory OHLC for indicators (replay starts fresh; not persisted).
        self._bars: List[Dict[str, float]] = []

    # ------------------------------------------------------------------ API
    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if not bar.complete:
            return StrategyActions.empty()
        signal_tf = str(self.config.get("signal_tf") or "").strip()
        if signal_tf and bar.timeframe != signal_tf:
            return StrategyActions.empty()
        if bool(self.config.get("rth_only")) and not _in_rth(bar.ts):
            # Still update history off-RTH so ATR/swings stay continuous when
            # rth_only is false; when true, skip entirely outside RTH.
            return StrategyActions.empty()

        self._append_bar(bar)
        trend = self._trend_direction()
        state = self._state()
        state["trend"] = trend
        state["atr"] = self._atr()

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []

        qty = int(context.position_quantity)

        # --- manage open trade ---
        if qty != 0:
            actions = self._manage_open(bar, context, trend, state)
            self._commit_state(state)
            return actions

        # Flat: cancel stale working entry if trend died / flipped
        if state.get("pending_entry_trade_id"):
            pending_dir = str(state.get("pending_direction") or "")
            want = "Long" if trend == "up" else ("Short" if trend == "down" else "")
            if not want or want != pending_dir:
                cancels.extend(self._cancel_entries(context, "trend_invalid"))
                state["pending_entry_trade_id"] = ""
                state["pending_direction"] = ""
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        if self._has_working_entry(context):
            self._commit_state(state)
            return StrategyActions.empty()

        if trend not in {"up", "down"}:
            self._commit_state(state)
            return StrategyActions.empty()

        if not self._is_momentum_bar(trend):
            self._commit_state(state)
            return StrategyActions.empty()

        if not self._pullback_gate(trend):
            self._commit_state(state)
            return StrategyActions.empty()

        if not self._sma_filters(bar, trend):
            self._commit_state(state)
            return StrategyActions.empty()

        trade_id = new_id("trade")
        tick = float(self.config["tick_size"])
        last = self._bars[-1]
        atr = float(state.get("atr") or 0.0)
        bar_range = float(last["high"] - last["low"])
        mid = (float(last["high"]) + float(last["low"])) / 2.0
        narrow = atr > 0 and bar_range < float(self.config["narrow_atr_frac"]) * atr

        if trend == "up":
            entry_px = float(last["high"]) + tick
            stop_px = float(last["low"]) - tick if narrow else mid
            direction = "Long"
            side = "buy"
        else:
            entry_px = float(last["low"]) - tick
            stop_px = float(last["high"]) + tick if narrow else mid
            direction = "Short"
            side = "sell"

        entry_qty = min(int(self.config["entry_qty"]), int(self.config.get("max_contracts") or self.instance.max_contracts or 1))
        if entry_qty <= 0:
            self._commit_state(state)
            return StrategyActions.empty()

        orders.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=side,
                order_type="stop",
                quantity=entry_qty,
                stop_price=entry_px,
                reason="entry",
                requires_verification=True,
                bracket_role="entry",
                live_after_ts=bar.ts,
            )
        )
        state["pending_entry_trade_id"] = trade_id
        state["pending_direction"] = direction
        state["pending_stop"] = stop_px
        state["pending_entry_price"] = entry_px
        state["mom_high"] = float(last["high"])
        state["mom_low"] = float(last["low"])
        state["mom_mid"] = mid
        state["mom_narrow"] = bool(narrow)
        self._commit_state(state)
        return StrategyActions(orders, cancels, modifies, [], [])

    def on_fill(self, fill: Fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        role = fill.reason

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            stop_px = float(state.get("pending_stop") or 0.0)
            if stop_px <= 0:
                # Fallback mid of stored momentum bar
                stop_px = float(state.get("mom_mid") or fill.price)
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = direction
            state["entry_price"] = float(fill.price)
            state["stop_price"] = stop_px
            state["pending_entry_trade_id"] = ""
            state["pending_direction"] = ""
            state["opposite_count"] = 0
            state["pullback_extreme"] = None
            state["extreme_since_entry"] = float(fill.price)
            self._commit_state(state)
            exit_side = "sell" if direction == "Long" else "buy"
            qty = abs(int(fill.quantity))
            return StrategyActions(
                [
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=fill.trade_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side=exit_side,
                        order_type="stop",
                        quantity=qty,
                        stop_price=stop_px,
                        reason="stop",
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role="stop",
                    )
                ],
                self._cancel_entries(context, "filled_cancel_other"),
                [],
                [],
                [],
            )

        if role in {"stop", "trend_end", "eod_close", "flatten"}:
            state["active_trade_id"] = ""
            state["active_direction"] = ""
            state["stop_price"] = None
            state["opposite_count"] = 0
            state["pullback_extreme"] = None
            self._commit_state(state)
            return StrategyActions([], self._cancel_reduce(context, fill.trade_id), [], [], [])

        return StrategyActions.empty()

    # ------------------------------------------------------------- management
    def _manage_open(
        self,
        bar: Bar,
        context: StrategyContext,
        trend: str,
        state: Dict[str, Any],
    ) -> StrategyActions:
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []

        direction = str(state.get("active_direction") or ("Long" if context.position_quantity > 0 else "Short"))
        trade_id = str(state.get("active_trade_id") or "")
        stop_px = state.get("stop_price")
        if stop_px is not None:
            stop_px = float(stop_px)

        prior_extreme = state.get("extreme_since_entry")
        prior_extreme_f = float(prior_extreme) if prior_extreme is not None else None

        # Track extreme since entry for "trend resume"
        if direction == "Long":
            state["extreme_since_entry"] = max(
                float(prior_extreme_f if prior_extreme_f is not None else bar.high), float(bar.high)
            )
        else:
            state["extreme_since_entry"] = min(
                float(prior_extreme_f if prior_extreme_f is not None else bar.low), float(bar.low)
            )

        # Trend-end flatten (structure flip). Default: opposite only —
        # flattening on "none" is too chatty with short swing lookbacks (A9 fine-tune).
        mode = str(self.config.get("trend_end_mode") or "opposite")
        if bool(self.config.get("trend_end_flatten")) and mode != "off":
            if mode == "opposite_or_none":
                bad = (direction == "Long" and trend in {"down", "none"}) or (
                    direction == "Short" and trend in {"up", "none"}
                )
            else:
                bad = (direction == "Long" and trend == "down") or (
                    direction == "Short" and trend == "up"
                )
            if bad:
                cancels.extend(self._cancel_reduce(context, trade_id))
                orders.append(self._flatten(context, bar.ts, "trend_end"))
                state["active_trade_id"] = ""
                state["active_direction"] = ""
                return StrategyActions(orders, cancels, modifies, [], [])

        # Pullback trail
        bullish = bar.close > bar.open
        bearish = bar.close < bar.open
        opp = int(state.get("opposite_count") or 0)
        pb = state.get("pullback_extreme")

        if direction == "Long":
            if bearish:
                opp += 1
                pb = float(bar.low) if pb is None else min(float(pb), float(bar.low))
            elif bullish and opp >= int(self.config["min_pullback_bars"]) and pb is not None:
                # Resume: with-trend close that exceeds the extreme before this bar
                resumed = prior_extreme_f is None or float(bar.high) > prior_extreme_f
                if resumed:
                    new_stop = float(pb)
                    if stop_px is None or new_stop > stop_px:
                        stop_px = new_stop
                        state["stop_price"] = stop_px
                        modifies.extend(self._modify_stop(context, trade_id, stop_px, "trail_pullback"))
                    opp = 0
                    pb = None
            elif bullish:
                opp = 0
                pb = None
        else:  # Short
            if bullish:
                opp += 1
                pb = float(bar.high) if pb is None else max(float(pb), float(bar.high))
            elif bearish and opp >= int(self.config["min_pullback_bars"]) and pb is not None:
                resumed = prior_extreme_f is None or float(bar.low) < prior_extreme_f
                if resumed:
                    new_stop = float(pb)
                    if stop_px is None or new_stop < stop_px:
                        stop_px = new_stop
                        state["stop_price"] = stop_px
                        modifies.extend(self._modify_stop(context, trade_id, stop_px, "trail_pullback"))
                    opp = 0
                    pb = None
            elif bearish:
                opp = 0
                pb = None

        state["opposite_count"] = opp
        state["pullback_extreme"] = pb
        return StrategyActions(orders, cancels, modifies, [], [])

    # ----------------------------------------------------------- indicators
    def _append_bar(self, bar: Bar) -> None:
        self._bars.append(
            {
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
            }
        )
        max_n = int(self.config.get("history_bars") or 260)
        if len(self._bars) > max_n:
            self._bars = self._bars[-max_n:]

    def _atr(self) -> Optional[float]:
        n = int(self.config["atr_len"])
        if len(self._bars) < n + 1:
            return None
        trs: List[float] = []
        for i in range(1, len(self._bars)):
            h = self._bars[i]["high"]
            l = self._bars[i]["low"]
            pc = self._bars[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        window = trs[-n:]
        if len(window) < n:
            return None
        return sum(window) / float(n)

    def _sma(self, length: int) -> Optional[float]:
        if len(self._bars) < length:
            return None
        closes = [b["close"] for b in self._bars[-length:]]
        return sum(closes) / float(length)

    def _confirmed_swings(self) -> Tuple[List[float], List[float]]:
        lb = int(self.config["swing_lookback"])
        highs: List[float] = []
        lows: List[float] = []
        bars = self._bars
        if len(bars) < 2 * lb + 1:
            return highs, lows
        # Last confirmable pivot index is len-1-lb
        last_i = len(bars) - 1 - lb
        for i in range(lb, last_i + 1):
            h = bars[i]["high"]
            l = bars[i]["low"]
            left_h = [bars[j]["high"] for j in range(i - lb, i)]
            right_h = [bars[j]["high"] for j in range(i + 1, i + lb + 1)]
            left_l = [bars[j]["low"] for j in range(i - lb, i)]
            right_l = [bars[j]["low"] for j in range(i + 1, i + lb + 1)]
            if h > max(left_h) and h > max(right_h):
                highs.append(h)
            if l < min(left_l) and l < min(right_l):
                lows.append(l)
        return highs, lows

    def _trend_direction(self) -> str:
        highs, lows = self._confirmed_swings()
        if len(highs) < 2 or len(lows) < 2:
            return "none"
        hh = highs[-1] > highs[-2]
        hl = lows[-1] > lows[-2]
        lh = highs[-1] < highs[-2]
        ll = lows[-1] < lows[-2]
        if hh and hl:
            return "up"
        if lh and ll:
            return "down"
        return "none"

    def _is_momentum_bar(self, trend: str) -> bool:
        if len(self._bars) < 2:
            return False
        atr = self._atr()
        if atr is None or atr <= 0:
            return False
        last = self._bars[-1]
        body = abs(last["close"] - last["open"])
        if body < float(self.config["momentum_atr_mult"]) * atr:
            return False
        if trend == "up":
            return last["close"] > last["open"]
        if trend == "down":
            return last["close"] < last["open"]
        return False

    def _pullback_gate(self, trend: str) -> bool:
        need = int(self.config["min_pullback_bars"])
        if need <= 0:
            return True
        # Count opposite closes immediately before the current (momentum) bar.
        if len(self._bars) < need + 1:
            return False
        prior = self._bars[-(need + 1) : -1]
        if trend == "up":
            return all(b["close"] < b["open"] for b in prior)
        if trend == "down":
            return all(b["close"] > b["open"] for b in prior)
        return False

    def _sma_filters(self, bar: Bar, trend: str) -> bool:
        if bool(self.config.get("require_above_sma200")):
            sma200 = self._sma(200)
            if sma200 is None:
                return False
            if trend == "up" and bar.close < sma200:
                return False
            if trend == "down" and bar.close > sma200:
                return False
        if bool(self.config.get("momentum_near_sma10")):
            sma10 = self._sma(10)
            if sma10 is None:
                return False
            last = self._bars[-1]
            # First close beyond SMA10 and close in top/bottom fraction of bar
            rng = max(last["high"] - last["low"], 1e-12)
            if trend == "up":
                if last["close"] <= sma10:
                    return False
                if (last["close"] - last["low"]) / rng < (1.0 - float(self.config["sma10_top_frac"])):
                    return False
            else:
                if last["close"] >= sma10:
                    return False
                if (last["high"] - last["close"]) / rng < (1.0 - float(self.config["sma10_top_frac"])):
                    return False
        return True

    # -------------------------------------------------------------- helpers
    def _state(self) -> Dict[str, Any]:
        return dict(self.state or {})

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _has_working_entry(self, context: StrategyContext) -> bool:
        for order in context.strategy_open_orders:
            if order.bracket_role == "entry" and not order.reduce_only:
                return True
        return False

    def _cancel_entries(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.bracket_role == "entry" and not order.reduce_only:
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only and (not trade_id or order.trade_id == trade_id):
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, "tm_cancel_reduce"))
        return out

    def _modify_stop(
        self, context: StrategyContext, trade_id: str, stop_px: float, reason: str
    ) -> List[ModifyIntent]:
        out: List[ModifyIntent] = []
        for order in context.strategy_open_orders:
            if order.trade_id == trade_id and order.bracket_role == "stop" and order.reduce_only:
                out.append(
                    ModifyIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=order.broker_order_id,
                        reason=reason,
                        stop_price=stop_px,
                    )
                )
        return out

    def _flatten(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self._state().get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            live_after_ts=ts,
        )


def _in_rth(ts: str) -> bool:
    dt = datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    else:
        dt = dt.astimezone(NY_TZ)
    t = dt.time()
    return RTH_OPEN <= t < RTH_CLOSE


def default_config(tick_size: float, **overrides: Any) -> Dict[str, Any]:
    cfg = {
        "tick_size": float(tick_size),
        "entry_qty": 1,
        "max_contracts": 1,
        "atr_len": 14,
        "momentum_atr_mult": 1.0,
        "swing_lookback": 2,
        "min_pullback_bars": 2,
        "narrow_atr_frac": 0.5,
        "require_above_sma200": False,
        "momentum_near_sma10": False,
        "trend_end_flatten": True,
        "rth_only": False,
    }
    cfg.update(overrides)
    return cfg
