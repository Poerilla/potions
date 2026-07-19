"""Hourly SuperTrend day-bias DCA (prev-day pullback).

Bias (causal): on NY day D, use completed hourly ST on D−1. If ≥70% of that
day's hourly bars were bullish ST → long bias; ≥70% bearish → short; else flat
(no new entries). Current-day ST only sets *tomorrow's* bias.

Entries: 1 unit (0.5 lot in FX replay) at prev-day pullback fraction f of the
range; SL at prev-day extreme. Max ``max_adds`` per calendar month, never two
entries on the same NY day. Adds only while bias still matches open side.

Exit: unit/campaign stop, or flatten at period rollover (week / month).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, time
from typing import Any, Dict, List, Optional

import pytz

from ..models import CancelIntent, OrderIntent, StrategyActions
from .atr_supertrend_dca import TrendPoint
from .base import StrategyContext, StrategyPlugin


NY = "America/New_York"
NY_TZ = pytz.timezone(NY)


def _ny_date(ts: str) -> date:
    dt = datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    return dt.astimezone(NY_TZ).date()


def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return "%d-W%02d" % (iso[0], iso[1])


def _month_key(d: date) -> str:
    return "%d-%02d" % (d.year, d.month)


class HourlyStDaybiasDcaStrategy(StrategyPlugin):
    strategy_type = "hourly_st_daybias_dca"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "timeframe": "1h",
            "atr_len": 14,
            "atr_mult": 3.0,
            "pullback_frac": 0.30,
            "bias_thresh": 0.70,
            "exit_period": "week",  # week | month
            "add_qty": 1,
            "max_adds": 5,
            "tick_size": 1e-5,
            # 0 = disabled; else take-profit at k × hourly ATR from fill price
            "tp_atr_mult": 0.0,
            # wick = resting stop (intrabar); close = exit only if 1h closes beyond SL
            "stop_mode": "wick",
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._hourly_cache: Optional[List] = None
        self._st_processed = 0
        self._st_trs: List[float] = []
        self._st_atr: Optional[float] = None
        self._st_final_upper: Optional[float] = None
        self._st_final_lower: Optional[float] = None
        self._st_bullish = True
        self._st_points: List[TrendPoint] = []

    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != str(self.config.get("timeframe") or "1h") or not bar.complete:
            return StrategyActions.empty()
        return self._on_hourly(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if fill.reason in {"entry", "add"}:
            state["active_trade_id"] = fill.trade_id
            state["pending_entry_trade_id"] = ""
            state["side"] = (
                "long"
                if context.position_quantity > 0
                else "short"
                if context.position_quantity < 0
                else str(state.get("side") or "")
            )
            state["adds"] = int(state.get("adds") or 0) + max(1, int(float(fill.quantity or 1)))
            entry_day = _ny_date(fill.ts)
            state["last_entry_day"] = entry_day.isoformat()
            mkey = _month_key(entry_day)
            month_counts = dict(state.get("month_entry_count") or {})
            month_counts[mkey] = int(month_counts.get(mkey) or 0) + 1
            state["month_entry_count"] = month_counts
            lot_stops = list(state.get("lot_stops") or [])
            stop_px = state.get("pending_stop")
            if stop_px is not None:
                lot_stops.append(float(stop_px))
            state["lot_stops"] = lot_stops
            state["campaign_stop"] = self._aggregate_stop(str(state.get("side") or ""), lot_stops)
            side = str(state.get("side") or "")
            tp_mult = float(self.config.get("tp_atr_mult") or 0.0)
            if tp_mult > 0 and self._st_atr is not None and side in {"long", "short"}:
                tp_px = float(fill.price) + tp_mult * float(self._st_atr) * (1 if side == "long" else -1)
                lot_tps = list(state.get("lot_tps") or [])
                lot_tps.append(tp_px)
                state["lot_tps"] = lot_tps
                state["campaign_tp"] = min(lot_tps) if side == "long" else max(lot_tps)
            state["period_key"] = state.get("period_key") or self._period_key(entry_day)
            self.state = state
            self.save_state()
            # Refresh full-size protective stop (+ optional TP) at aggregate level
            if context.position_quantity != 0 and state.get("campaign_stop") is not None:
                cancels.extend(self._cancel_stops(context, "refresh_campaign_stop"))
                cancels.extend(self._cancel_targets(context, "refresh_campaign_tp"))
                tid = str(state["active_trade_id"])
                qty_pos = int(context.position_quantity)
                orders.append(self._protective_stop(state, tid, qty_pos, float(state["campaign_stop"]), fill.ts))
                if state.get("campaign_tp") is not None:
                    orders.append(self._protective_tp(state, tid, qty_pos, float(state["campaign_tp"]), fill.ts))
                return StrategyActions(orders, cancels, [], [], [], [])

        elif fill.reason in {"stop", "protective_stop"}:
            # Research: any lot stop → flatten entire campaign
            if context.position_quantity != 0:
                cancels.extend(self._cancel_entry_limits(context, "stop_flatten"))
                cancels.extend(self._cancel_stops(context, "stop_flatten"))
                cancels.extend(self._cancel_targets(context, "stop_flatten"))
                orders.append(
                    self._flatten(
                        state,
                        fill.trade_id or state.get("active_trade_id") or self._next_trade_id(state),
                        int(context.position_quantity),
                        fill.ts,
                        "stop",
                    )
                )
                state["close_pending"] = "stop"
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], [], [], [])
            self._reset_campaign(state)
            self.state = state
            self.save_state()

        elif fill.reason in {"target", "tp"}:
            if context.position_quantity != 0:
                cancels.extend(self._cancel_entry_limits(context, "tp_flatten"))
                cancels.extend(self._cancel_stops(context, "tp_flatten"))
                cancels.extend(self._cancel_targets(context, "tp_flatten"))
                orders.append(
                    self._flatten(
                        state,
                        fill.trade_id or state.get("active_trade_id") or self._next_trade_id(state),
                        int(context.position_quantity),
                        fill.ts,
                        "tp",
                    )
                )
                state["close_pending"] = "tp"
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], [], [], [])
            self._reset_campaign(state)
            self.state = state
            self.save_state()

        elif fill.reason in {"period_end", "close", "eod_mark"}:
            if context.position_quantity == 0:
                self._reset_campaign(state)
                self.state = state
                self.save_state()

        return StrategyActions.empty()

    def _on_hourly(self, bar, context: StrategyContext) -> StrategyActions:
        hourly = self._hourly_bars(bar)
        now = self._current_trend_point(hourly)
        if now is None:
            return StrategyActions.empty()

        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        d = _ny_date(bar.ts)
        cur_day_s = state.get("cur_day") or ""
        qty = int(context.position_quantity)
        add_qty = max(1, int(self.config["add_qty"]))
        max_adds = max(1, int(self.config["max_adds"]))
        frac = float(self.config["pullback_frac"])
        thresh = float(self.config["bias_thresh"])
        tick = float(self.config["tick_size"])

        # ---- Day rollover: finalize prior day → tomorrow's bias ----
        if cur_day_s and cur_day_s != d.isoformat():
            prev_d = date.fromisoformat(cur_day_s)
            n = int(state.get("day_st_n") or 0)
            bull_n = int(state.get("day_st_bull") or 0)
            if n > 0:
                bull_frac = bull_n / float(n)
                bear_frac = 1.0 - bull_frac
                if bull_frac >= thresh:
                    state["bias"] = "long"
                elif bear_frac >= thresh:
                    state["bias"] = "short"
                else:
                    state["bias"] = ""
            else:
                state["bias"] = ""
            state["prev_high"] = float(state.get("day_high") or 0.0)
            state["prev_low"] = float(state.get("day_low") or 0.0)
            state["prev_day"] = cur_day_s

            # Period rollover flatten at first bar of new period
            new_pkey = self._period_key(d)
            old_pkey = str(state.get("period_key") or "")
            if qty != 0 and old_pkey and old_pkey != new_pkey:
                cancels.extend(self._cancel_entry_limits(context, "period_end"))
                cancels.extend(self._cancel_stops(context, "period_end"))
                cancels.extend(self._cancel_targets(context, "period_end"))
                tid = state.get("active_trade_id") or self._next_trade_id(state)
                orders.append(self._flatten(state, tid, qty, bar.ts, "period_end"))
                state["close_pending"] = "period_end"
                state["cur_day"] = d.isoformat()
                state["day_high"] = float(bar.high)
                state["day_low"] = float(bar.low)
                state["day_st_n"] = 0
                state["day_st_bull"] = 0
                self.state = state
                self.save_state()
                return StrategyActions(orders, cancels, [], [], [], [])

            # Reset day accumulators
            state["day_high"] = float(bar.high)
            state["day_low"] = float(bar.low)
            state["day_st_n"] = 0
            state["day_st_bull"] = 0
        elif not cur_day_s:
            state["day_high"] = float(bar.high)
            state["day_low"] = float(bar.low)
            state["day_st_n"] = 0
            state["day_st_bull"] = 0

        state["cur_day"] = d.isoformat()
        state["day_high"] = max(float(state.get("day_high") or bar.high), float(bar.high))
        state["day_low"] = min(float(state.get("day_low") or bar.low), float(bar.low))
        state["day_st_n"] = int(state.get("day_st_n") or 0) + 1
        if now.bullish:
            state["day_st_bull"] = int(state.get("day_st_bull") or 0) + 1

        # Re-read qty after possible flatten path above
        if state.get("close_pending") and qty == 0:
            state["close_pending"] = ""

        bias = str(state.get("bias") or "") or None
        prev_high = float(state.get("prev_high") or 0.0)
        prev_low = float(state.get("prev_low") or 0.0)
        span_ok = prev_high > prev_low
        mkey = _month_key(d)
        month_used = int((state.get("month_entry_count") or {}).get(mkey) or 0)
        last_entry = str(state.get("last_entry_day") or "")
        entered_today = last_entry == d.isoformat()
        side_open = str(state.get("side") or "")
        pkey = self._period_key(d)

        # Period-end flatten on Friday / month-end from 16:00 NY (match research close)
        if qty != 0 and self._is_period_end_bar(bar, d):
            cancels.extend(self._cancel_entry_limits(context, "period_end"))
            cancels.extend(self._cancel_stops(context, "period_end"))
            cancels.extend(self._cancel_targets(context, "period_end"))
            tid = state.get("active_trade_id") or self._next_trade_id(state)
            orders.append(self._flatten(state, tid, qty, bar.ts, "period_end"))
            state["close_pending"] = "period_end"
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        # In position: stop management; maybe add
        if qty != 0:
            if not state.get("period_key"):
                state["period_key"] = pkey
            camp_stop = state.get("campaign_stop")
            camp_tp = state.get("campaign_tp")
            stop_mode = str(self.config.get("stop_mode") or "wick").strip().lower()
            tid = str(state.get("active_trade_id") or self._next_trade_id(state))

            # close mode: no resting stop; flatten if hourly close beyond SL
            if stop_mode == "close" and camp_stop is not None:
                cancels.extend(self._cancel_stops(context, "close_stop_mode"))
                closed_through = (side_open == "long" and float(bar.close) < float(camp_stop)) or (
                    side_open == "short" and float(bar.close) > float(camp_stop)
                )
                if closed_through:
                    cancels.extend(self._cancel_entry_limits(context, "close_sl"))
                    cancels.extend(self._cancel_targets(context, "close_sl"))
                    orders.append(self._flatten(state, tid, qty, bar.ts, "stop"))
                    state["close_pending"] = "stop"
                    self.state = state
                    self.save_state()
                    return StrategyActions(orders, cancels, [], [], [], [])
            elif camp_stop is not None:
                existing_stops = [
                    o
                    for o in context.strategy_open_orders
                    if o.reduce_only and o.order_type == "stop"
                ]
                need_refresh = True
                if len(existing_stops) == 1 and existing_stops[0].stop_price is not None:
                    if abs(float(existing_stops[0].stop_price) - float(camp_stop)) <= tick / 2.0:
                        if int(existing_stops[0].quantity) == abs(qty):
                            need_refresh = False
                if need_refresh:
                    cancels.extend(self._cancel_stops(context, "refresh_campaign_stop"))
                    orders.append(self._protective_stop(state, tid, qty, float(camp_stop), bar.ts))

            if camp_tp is not None:
                existing_tps = [
                    o
                    for o in context.strategy_open_orders
                    if o.reduce_only
                    and o.order_type == "limit"
                    and (o.bracket_role or "") in {"target", "tp"}
                ]
                tp_ok = False
                if len(existing_tps) == 1 and existing_tps[0].limit_price is not None:
                    if abs(float(existing_tps[0].limit_price) - float(camp_tp)) <= tick / 2.0:
                        if int(existing_tps[0].quantity) == abs(qty):
                            tp_ok = True
                if not tp_ok:
                    cancels.extend(self._cancel_targets(context, "refresh_campaign_tp"))
                    orders.append(self._protective_tp(state, tid, qty, float(camp_tp), bar.ts))

            can_add = (
                bias is not None
                and bias == side_open
                and not entered_today
                and month_used < max_adds
                and int(state.get("adds") or 0) < max_adds
                and abs(qty) < int(self.instance.max_contracts)
                and span_ok
            )
            if can_add:
                lvl = self._entry_level(bias, prev_high, prev_low, frac)
                stop = prev_low if bias == "long" else prev_high
                day_lo = float(state.get("day_low") or bar.low)
                day_hi = float(state.get("day_high") or bar.high)
                # Wick mode: skip if stop already tagged today. Close mode: allow wicks.
                if bias == "long" and lvl <= stop:
                    can_add = False
                if bias == "short" and lvl >= stop:
                    can_add = False
                if stop_mode != "close":
                    if bias == "long" and day_lo <= stop:
                        can_add = False
                    if bias == "short" and day_hi >= stop:
                        can_add = False
                if can_add:
                    state["pending_stop"] = float(stop)
                    orders.extend(
                        self._place_or_refresh_limit(
                            context,
                            state,
                            bias,
                            lvl,
                            stop,
                            add_qty,
                            bar.ts,
                            reason="add",
                            cancels=cancels,
                        )
                    )
            else:
                cancels.extend(self._cancel_entry_limits(context, "no_add"))

            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        # Flat — new campaign entry
        if state.get("close_pending"):
            state["close_pending"] = ""
        self._reset_campaign(state, keep_bias=True)

        can_enter = (
            bias in {"long", "short"}
            and not entered_today
            and month_used < max_adds
            and span_ok
        )
        if not can_enter:
            cancels.extend(self._cancel_entry_limits(context, "no_entry"))
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        lvl = self._entry_level(bias, prev_high, prev_low, frac)
        stop = prev_low if bias == "long" else prev_high
        if bias == "long" and lvl <= stop:
            cancels.extend(self._cancel_entry_limits(context, "bad_geometry"))
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])
        if bias == "short" and lvl >= stop:
            cancels.extend(self._cancel_entry_limits(context, "bad_geometry"))
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])
        # If today already traded through the stop, geometry is dead for new entries
        day_lo = float(state.get("day_low") or bar.low)
        day_hi = float(state.get("day_high") or bar.high)
        if bias == "long" and day_lo <= stop:
            cancels.extend(self._cancel_entry_limits(context, "stop_already_tagged"))
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])
        if bias == "short" and day_hi >= stop:
            cancels.extend(self._cancel_entry_limits(context, "stop_already_tagged"))
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], [], [], [])

        state["pending_stop"] = float(stop)
        state["period_key"] = pkey
        state["side"] = bias
        orders.extend(
            self._place_or_refresh_limit(
                context,
                state,
                bias,
                lvl,
                stop,
                add_qty,
                bar.ts,
                reason="entry",
                cancels=cancels,
            )
        )
        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], [], [], [])

    def _place_or_refresh_limit(
        self,
        context: StrategyContext,
        state: Dict[str, Any],
        bias: str,
        lvl: float,
        stop: float,
        qty: int,
        ts: str,
        *,
        reason: str,
        cancels: List[CancelIntent],
    ) -> List[OrderIntent]:
        tick = float(self.config["tick_size"])
        side = "buy" if bias == "long" else "sell"
        existing = [
            o
            for o in context.strategy_open_orders
            if (not o.reduce_only) and o.order_type == "limit"
        ]
        if len(existing) == 1 and existing[0].side == side and existing[0].limit_price is not None:
            if abs(float(existing[0].limit_price) - lvl) <= tick / 2.0:
                if int(existing[0].quantity) == qty:
                    return []
        cancels.extend(self._cancel_entry_limits(context, "refresh_entry"))
        trade_id = state.get("active_trade_id") or state.get("pending_entry_trade_id") or self._next_trade_id(state)
        if reason == "entry":
            trade_id = self._next_trade_id(state)
            state["pending_entry_trade_id"] = trade_id
            state["active_trade_id"] = trade_id
        else:
            state["pending_entry_trade_id"] = trade_id
        # No bracket stop on the limit — arm protective stop only after fill
        # (avoids same-bar entry+stop on the fill hour).
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=side,
                order_type="limit",
                quantity=qty,
                limit_price=float(lvl),
                reason=reason,
                requires_verification=True,
                bracket_role=reason,
                live_after_ts=ts,
            )
        ]

    def _is_period_end_bar(self, bar, d: date) -> bool:
        period = str(self.config.get("exit_period") or "week").lower()
        dt = datetime.fromisoformat(str(bar.ts))
        if dt.tzinfo is None:
            dt = NY_TZ.localize(dt)
        ny = dt.astimezone(NY_TZ)
        # FX Fridays often print into 20:00–21:00 NY; arm from 16:00 onward
        if ny.time() < time(16, 0):
            return False
        if period == "week":
            return d.weekday() == 4
        if d.month == 12:
            last = date(d.year, 12, 31)
        else:
            last = date(d.year, d.month + 1, 1) - timedelta(days=1)
        return d == last

    def _entry_level(self, side: str, high: float, low: float, frac: float) -> float:
        span = high - low
        if side == "long":
            return low + frac * span
        return high - frac * span

    def _aggregate_stop(self, side: str, lot_stops: List[float]) -> Optional[float]:
        if not lot_stops:
            return None
        if side == "long":
            return max(lot_stops)  # first hit among long stops
        if side == "short":
            return min(lot_stops)
        return None

    def _period_key(self, d: date) -> str:
        period = str(self.config.get("exit_period") or "week").lower()
        if period == "month":
            return _month_key(d)
        return _week_key(d)

    def _protective_stop(
        self, state: Dict[str, Any], trade_id: str, qty_pos: int, stop: float, ts: str
    ) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if qty_pos > 0 else "buy",
            order_type="stop",
            quantity=abs(qty_pos),
            stop_price=float(stop),
            reason="protective_stop",
            requires_verification=False,
            reduce_only=True,
            bracket_role="stop",
            live_after_ts=ts,
        )

    def _protective_tp(
        self, state: Dict[str, Any], trade_id: str, qty_pos: int, tp: float, ts: str
    ) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if qty_pos > 0 else "buy",
            order_type="limit",
            quantity=abs(qty_pos),
            limit_price=float(tp),
            reason="target",
            requires_verification=False,
            reduce_only=True,
            bracket_role="target",
            live_after_ts=ts,
        )

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

    def _reset_campaign(self, state: Dict[str, Any], keep_bias: bool = False) -> None:
        state["active_trade_id"] = ""
        state["pending_entry_trade_id"] = ""
        state["adds"] = 0
        state["side"] = ""
        state["lot_stops"] = []
        state["lot_tps"] = []
        state["campaign_stop"] = None
        state["campaign_tp"] = None
        state["pending_stop"] = None
        state["period_key"] = ""
        state["close_pending"] = ""
        if not keep_bias:
            pass

    def _hourly_bars(self, bar) -> List:
        if self._hourly_cache is None:
            self._hourly_cache = list(self.store.read_bars(self.instance.instrument, "1h"))
        if not self._hourly_cache or self._hourly_cache[-1].ts != bar.ts:
            self._hourly_cache.append(bar)
        return self._hourly_cache

    def _current_trend_point(self, hourly: List) -> Optional[TrendPoint]:
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
        state.setdefault("pending_entry_trade_id", "")
        state.setdefault("adds", 0)
        state.setdefault("side", "")
        state.setdefault("close_pending", "")
        state.setdefault("bias", "")
        state.setdefault("cur_day", "")
        state.setdefault("prev_day", "")
        state.setdefault("prev_high", 0.0)
        state.setdefault("prev_low", 0.0)
        state.setdefault("day_high", 0.0)
        state.setdefault("day_low", 0.0)
        state.setdefault("day_st_n", 0)
        state.setdefault("day_st_bull", 0)
        state.setdefault("last_entry_day", "")
        state.setdefault("month_entry_count", {})
        state.setdefault("lot_stops", [])
        state.setdefault("lot_tps", [])
        state.setdefault("campaign_stop", None)
        state.setdefault("campaign_tp", None)
        state.setdefault("pending_stop", None)
        state.setdefault("period_key", "")
        return state

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_t%d" % (self.instance.strategy_id, state["trade_seq"])

    def _cancel_stops(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only and order.order_type == "stop":
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out

    def _cancel_targets(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only and order.order_type == "limit" and (order.bracket_role or "") in {
                "target",
                "tp",
            }:
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out

    def _cancel_entry_limits(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if (not order.reduce_only) and order.order_type == "limit":
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out
