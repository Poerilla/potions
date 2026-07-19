"""Monthly ORB stop entry with configurable scaleout (daily bars).

Rules
-----
- OR = first ``or_sessions`` daily bars of the calendar month.
- ``entry_mode=oco``: after OR, OCO stops long @ ORH / short @ ORL.
- ``entry_mode=first_break_opposite``: do **not** arm after OR; wait for the
  first OR break, ignore it, then arm a stop in the **opposite** direction
  (break ORH → short @ ORL; break ORL → long @ ORH). After a filled campaign
  ends, wait for a new ignored break before the next arm.
- Max ``max_trades_per_month`` filled campaigns.
- Structure: ``tp1_qty`` @ TP1=``tp1_r``·R, ``tp2_qty`` @ TP2=``tp2_r``·R,
  runner = ``entry_qty - tp1 - tp2`` (optional ``runner_r`` target, else open).
- ``be_after``: ``tp1`` (default) or ``tp2`` — when protective stop → BE.
- ``stop_mode=close``: no resting stop; flatten only when daily **close**
  is beyond the campaign stop (wicks allowed).
- ``eod_stop_to_or_mid``: after each daily close while flat-risk still open,
  ratchet campaign stop to OR midpoint (tighten only).
- ``entry_filter_csv``: optional path to a CSV ``date,long_ok,short_ok``.
  On each daily close the pending/resting entry stop is only kept if the
  filter row for that date allows its direction (signal must be computed
  from data available at that close — the fill can occur next bar onward).
- Flatten at month-end close.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class MonthlyOrbV2bOcoStrategy(StrategyPlugin):
    strategy_type = "monthly_orb_v2b_oco"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self._daily_bars_cache: Optional[List[Bar]] = None
        self._entry_filter_cache: Optional[Dict[str, Tuple[bool, bool]]] = None
        self.config = {
            "or_sessions": 3,
            "max_trades_per_month": 2,
            "entry_qty": 4,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "tp1_r": 1.0,
            "tp2_r": 2.0,
            "runner_r": None,  # if set, runner limit at this R multiple; else no runner TP
            "be_after": "tp1",  # tp1 | tp2
            "entry_mode": "oco",  # oco | first_break_opposite
            # After a first_break_opposite campaign stop_close, treat the failed
            # side as the new "ignored break" and arm the other OR boundary.
            "flip_after_stop": False,
            # After each daily close while in a trade, ratchet protective stop to
            # OR midpoint (only tightens; BE after TP1 still wins if tighter).
            "eod_stop_to_or_mid": False,
            "allow_shorts": True,
            "stop_mode": "close",
            "flatten_month_end": True,
            "month_end_dates": [],
            "record_levels": False,
            # Optional CSV (date,long_ok,short_ok) gating entry direction per day.
            "entry_filter_csv": None,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "D" or not bar.complete:
            return StrategyActions.empty()
        return self._on_daily_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state_for_month(_month_key(fill.ts))
        # PaperBroker sets fill.reason = order.bracket_role (see broker._fill_order).
        reason = str(fill.reason or "")

        if reason == "entry" and context.position_quantity != 0:
            range_high = _to_float(state.get("range_high"))
            range_low = _to_float(state.get("range_low"))
            if range_high is None or range_low is None or range_high <= range_low:
                self.state = state
                self.save_state()
                return StrategyActions.empty()
            direction = "long" if fill.side == "buy" else "short"
            entry = float(fill.price)
            stop0 = float(range_low) if direction == "long" else float(range_high)
            state["active_trade_id"] = fill.trade_id
            state["active_entry"] = entry
            state["active_direction"] = direction
            state["campaign_stop"] = stop0
            state["tp1_hit"] = False
            state["tp2_hit"] = False
            state["trade_count"] = int(state.get("trade_count", 0)) + 1
            state["phase"] = "in_trade"
            self.state = state
            self.save_state()
            cancels = [
                CancelIntent(self.instance.strategy_id, o.broker_order_id, "entry_filled_cancel_oco")
                for o in context.strategy_open_orders
                if (not o.reduce_only) and o.broker_order_id != fill.broker_order_id
            ]
            return StrategyActions(
                self._exit_orders(fill, direction, entry, range_high, range_low, state),
                cancels,
                [],
                [],
                [],
            )

        if reason == "tp1":
            state["tp1_hit"] = True
            self.state = state
            self.save_state()
            if self._be_after() == "tp1":
                return self._move_stop_to_be(fill, context, state)
            return StrategyActions.empty()

        if reason == "tp2":
            state["tp2_hit"] = True
            self.state = state
            self.save_state()
            if self._be_after() == "tp2":
                return self._move_stop_to_be(fill, context, state)
            return StrategyActions.empty()

        if context.position_quantity == 0 and not self._has_open_entry_order(context):
            if bool(state.get("pending_flip")) and self._entry_mode() == "first_break_opposite":
                # Failed fade side becomes the ignored break → arm the other way.
                failed = str(state.get("flip_from_side") or "")
                state["first_break_side"] = failed
                state["opposite_armed"] = False
                state["phase"] = "arm_opposite"
                state["pending_flip"] = False
                state["flip_from_side"] = ""
            else:
                state["phase"] = (
                    "wait_first_break" if self._entry_mode() == "first_break_opposite" else "wait_breakout"
                )
                state["first_break_side"] = ""
                state["opposite_armed"] = False
            state["active_trade_id"] = ""
            state["active_entry"] = None
            state["active_direction"] = ""
            state["campaign_stop"] = None
            state["tp1_hit"] = False
            state["tp2_hit"] = False
            self.state = state
            self.save_state()
        return StrategyActions.empty()

    def _be_after(self) -> str:
        return str(self.config.get("be_after") or "tp1").strip().lower()

    def _move_stop_to_be(self, fill, context: StrategyContext, state: Dict[str, Any]) -> StrategyActions:
        entry = _to_float(state.get("active_entry"))
        if entry is None:
            return StrategyActions.empty()
        state["campaign_stop"] = entry
        self.state = state
        self.save_state()
        if self._stop_mode() == "wick" and context.position_quantity != 0:
            return self._refresh_wick_stop(context, fill.trade_id, entry, abs(context.position_quantity))
        return StrategyActions.empty()

    def _on_daily_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_date(bar.ts)
        key = "%04d-%02d" % (dt.year, dt.month)
        state = self._state_for_month(key)
        bars = self._daily_bars(bar)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        if state.get("month_key") != key:
            state = self._fresh_month_state(key)

        month_bar_count = self._month_bar_count(bars, dt.year, dt.month)
        or_sessions = int(self.config["or_sessions"])

        # Build OR — never arm OCO on the OR-complete bar for first_break_opposite
        if month_bar_count <= or_sessions:
            high = _to_float(state.get("range_high"))
            low = _to_float(state.get("range_low"))
            state["range_high"] = bar.high if high is None else max(high, bar.high)
            state["range_low"] = bar.low if low is None else min(low, bar.low)
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            if (
                self._entry_mode() == "oco"
                and month_bar_count == or_sessions
                and int(state.get("trade_count", 0)) < int(self.config["max_trades_per_month"])
                and context.position_quantity == 0
                and not self._has_open_entry_order(context)
            ):
                rh = _to_float(state.get("range_high"))
                rl = _to_float(state.get("range_low"))
                if rh is not None and rl is not None and rh > rl:
                    orders.extend(self._boundary_stop_orders(bar.ts, rh, rl, state))
            elif month_bar_count == or_sessions and self._entry_mode() == "first_break_opposite":
                state["phase"] = "wait_first_break"
                state["first_break_side"] = ""
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, alerts)

        range_high = _to_float(state.get("range_high"))
        range_low = _to_float(state.get("range_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            self.state = state
            self.save_state()
            return StrategyActions.empty()
        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        # Month-end flatten
        if self._is_month_end_bar(bar.ts):
            for order in context.strategy_open_orders:
                cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, "month_end_flatten"))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "month_end_flatten", order_type="market_close"))
                alerts.append(Alert.create(self.instance.strategy_id, "info", "Monthly ORB v2b month-end flatten"))
            state["phase"] = "month_end_flatten"
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, alerts)

        # Close-only protective stop
        if context.position_quantity != 0 and self._stop_mode() == "close":
            cancels.extend(self._cancel_roles(context, {"stop", "wide_stop", "runner_stop"}, "close_stop_mode"))
            camp_stop = _to_float(state.get("campaign_stop"))
            if camp_stop is not None:
                long_side = context.position_quantity > 0
                closed_through = (long_side and bar.close < camp_stop) or (
                    (not long_side) and bar.close > camp_stop
                )
                if closed_through:
                    cancels.extend(self._cancel_reduce(context, "close_sl"))
                    orders.append(self._close_all(context, bar.ts, "stop_close", order_type="market_close"))
                    state["phase"] = "stop_close"
                    if (
                        bool(self.config.get("flip_after_stop"))
                        and self._entry_mode() == "first_break_opposite"
                        and int(state.get("trade_count", 0)) < int(self.config["max_trades_per_month"])
                    ):
                        state["pending_flip"] = True
                        state["flip_from_side"] = str(state.get("active_direction") or "")
                    self.state = state
                    self.save_state()
                    return StrategyActions(orders, cancels, [], levels, alerts)

            # EOD: ratchet protective stop to OR mid (for tomorrow). Today's close
            # already evaluated against the prior stop above.
            if context.position_quantity != 0 and bool(self.config.get("eod_stop_to_or_mid")):
                mid = 0.5 * (float(range_high) + float(range_low))
                cur = _to_float(state.get("campaign_stop"))
                long_side = context.position_quantity > 0
                if cur is None:
                    state["campaign_stop"] = mid
                elif long_side:
                    state["campaign_stop"] = max(cur, mid)  # only tighten
                else:
                    state["campaign_stop"] = min(cur, mid)

        # Entry-direction filter: cancel resting entry stops whose direction is
        # no longer allowed by today's signal; they re-arm when allowed again.
        if context.position_quantity == 0:
            for order in context.strategy_open_orders:
                if order.reduce_only:
                    continue
                direction = "long" if order.side == "buy" else "short"
                if not self._entry_dir_allowed(bar.ts, direction):
                    cancels.append(
                        CancelIntent(self.instance.strategy_id, order.broker_order_id, "entry_filter_block")
                    )
                    state["opposite_armed"] = False
                    if self._entry_mode() == "first_break_opposite":
                        state["phase"] = "arm_opposite"

        flat = context.position_quantity == 0 and not self._has_open_entry_order(context)
        room = int(state.get("trade_count", 0)) < int(self.config["max_trades_per_month"])
        if flat and room:
            if self._entry_mode() == "first_break_opposite":
                orders.extend(self._first_break_opposite_orders(bar, range_high, range_low, state))
            else:
                orders.extend(self._boundary_stop_orders(bar.ts, range_high, range_low, state))

        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _unit_quantities(self) -> Tuple[int, int, int]:
        entry = max(1, int(self.config.get("entry_qty") or 1))
        tp1 = max(0, int(self.config.get("tp1_qty") if self.config.get("tp1_qty") is not None else 1))
        tp2 = max(0, int(self.config.get("tp2_qty") if self.config.get("tp2_qty") is not None else 1))
        if tp1 + tp2 > entry:
            overflow = tp1 + tp2 - entry
            cut = min(overflow, tp2)
            tp2 -= cut
            overflow -= cut
            tp1 = max(0, tp1 - overflow)
        runner = max(0, entry - tp1 - tp2)
        return tp1, tp2, runner

    def _exit_orders(
        self,
        fill,
        direction: str,
        entry: float,
        range_high: float,
        range_low: float,
        state: Dict[str, Any],
    ) -> List[OrderIntent]:
        tp1_qty, tp2_qty, runner_qty = self._unit_quantities()
        entry_qty = tp1_qty + tp2_qty + runner_qty
        r = float(range_high) - float(range_low)
        tp1_r = float(self.config.get("tp1_r") or 1.0)
        tp2_r = float(self.config.get("tp2_r") or 2.0)
        runner_r_raw = self.config.get("runner_r")
        runner_r = float(runner_r_raw) if runner_r_raw not in {None, ""} else None
        if direction == "long":
            tp1 = entry + tp1_r * r
            tp2 = entry + tp2_r * r
            runner_tp = entry + runner_r * r if runner_r is not None else None
            stop = float(range_low)
            exit_side = "sell"
        else:
            tp1 = entry - tp1_r * r
            tp2 = entry - tp2_r * r
            runner_tp = entry - runner_r * r if runner_r is not None else None
            stop = float(range_high)
            exit_side = "buy"
        state["campaign_stop"] = stop
        common = dict(
            strategy_id=self.instance.strategy_id,
            trade_id=fill.trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=exit_side,
            requires_verification=False,
            reduce_only=True,
            live_after_ts=fill.ts,
            expires_after_ts=_month_expiry(fill.ts),
        )
        out: List[OrderIntent] = []
        if self._stop_mode() == "wick" and entry_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="stop",
                    quantity=entry_qty,
                    stop_price=stop,
                    reason="v2b_wide_stop",
                    bracket_role="stop",
                )
            )
        if tp1_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=tp1,
                    reason="v2b_tp1",
                    bracket_role="tp1",
                )
            )
        if tp2_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=tp2,
                    reason="v2b_tp2",
                    bracket_role="tp2",
                )
            )
        if runner_qty > 0 and runner_tp is not None:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=runner_tp,
                    reason="v2b_runner_tp",
                    bracket_role="tp3",
                )
            )
        return out

    def _refresh_wick_stop(
        self,
        context: StrategyContext,
        trade_id: str,
        stop_price: float,
        qty: int,
    ) -> StrategyActions:
        cancels = self._cancel_roles(context, {"stop", "wide_stop", "runner_stop"}, "runner_stop_to_breakeven")
        exit_side = "sell" if context.position_quantity > 0 else "buy"
        order = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=exit_side,
            order_type="stop",
            quantity=qty,
            stop_price=stop_price,
            reason="v2b_runner_stop",
            requires_verification=False,
            reduce_only=True,
            bracket_role="runner_stop",
        )
        return StrategyActions([order], cancels, [], [], [])

    def _boundary_stop_orders(
        self,
        ts: str,
        range_high: float,
        range_low: float,
        state: Dict[str, Any],
    ) -> List[OrderIntent]:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        state["phase"] = "wait_fill"
        trade_id = "%s_%s_%02d" % (
            self.instance.strategy_id,
            state["month_key"].replace("-", ""),
            state["trade_seq"],
        )
        oco = "%s_entry_oco" % trade_id
        tp1_qty, tp2_qty, runner_qty = self._unit_quantities()
        qty = tp1_qty + tp2_qty + runner_qty
        out = [self._boundary_stop_parent("long", trade_id, ts, range_high, qty, oco)]
        if bool(self.config.get("allow_shorts")):
            out.append(self._boundary_stop_parent("short", trade_id, ts, range_low, qty, oco))
        return out

    def _boundary_stop_parent(
        self,
        direction: str,
        trade_id: str,
        ts: str,
        stop_price: float,
        qty: int,
        oco: str,
    ) -> OrderIntent:
        side = "buy" if direction == "long" else "sell"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="stop",
            quantity=qty,
            stop_price=stop_price,
            reason="%s_boundary_stop_entry" % direction,
            requires_verification=True,
            bracket_role="entry",
            oco_group=oco,
            live_after_ts=ts,
            expires_after_ts=_month_expiry(ts),
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
            bracket_role="close",
            live_after_ts=ts,
        )

    def _state_for_month(self, key: str) -> Dict[str, Any]:
        if not self.state or self.state.get("month_key") != key:
            return self._fresh_month_state(key)
        return dict(self.state)

    def _fresh_month_state(self, key: str) -> Dict[str, Any]:
        return {
            "month_key": key,
            "range_high": None,
            "range_low": None,
            "phase": "wait_first_break" if self._entry_mode() == "first_break_opposite" else "wait_breakout",
            "trade_count": 0,
            "trade_seq": 0,
            "active_trade_id": "",
            "active_entry": None,
            "active_direction": "",
            "campaign_stop": None,
            "tp1_hit": False,
            "tp2_hit": False,
            "first_break_side": "",
            "opposite_armed": False,
            "pending_flip": False,
            "flip_from_side": "",
        }

    def _first_break_opposite_orders(
        self,
        bar: Bar,
        range_high: float,
        range_low: float,
        state: Dict[str, Any],
    ) -> List[OrderIntent]:
        """Ignore first OR break, then arm stop in the opposite direction."""
        break_side = str(state.get("first_break_side") or "")
        if not break_side:
            long_hit = bar.high >= float(range_high)
            short_hit = bar.low <= float(range_low)
            if long_hit and short_hit:
                return []  # ambiguous — keep waiting
            if not long_hit and not short_hit:
                return []
            # Record ignored break; arm opposite on this bar close (fills next bar+).
            break_side = "long" if long_hit else "short"
            state["first_break_side"] = break_side
            state["phase"] = "arm_opposite"
            state["opposite_armed"] = False
        if bool(state.get("opposite_armed")):
            return []
        opposite = "short" if break_side == "long" else "long"
        if opposite == "short" and not bool(self.config.get("allow_shorts", True)):
            return []
        if not self._entry_dir_allowed(bar.ts, opposite):
            return []  # keep phase=arm_opposite; retry next daily close
        stop_price = float(range_low) if opposite == "short" else float(range_high)
        state["opposite_armed"] = True
        return [self._single_boundary_stop(opposite, bar.ts, stop_price, state)]

    def _single_boundary_stop(
        self,
        direction: str,
        ts: str,
        stop_price: float,
        state: Dict[str, Any],
    ) -> OrderIntent:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        state["phase"] = "wait_fill"
        trade_id = "%s_%s_%02d" % (
            self.instance.strategy_id,
            state["month_key"].replace("-", ""),
            state["trade_seq"],
        )
        tp1_qty, tp2_qty, runner_qty = self._unit_quantities()
        qty = tp1_qty + tp2_qty + runner_qty
        return self._boundary_stop_parent(direction, trade_id, ts, stop_price, qty, oco="")

    def _daily_bars(self, bar: Bar) -> List[Bar]:
        if self._daily_bars_cache is None:
            self._daily_bars_cache = self.store.read_bars(self.instance.instrument, "D")
        elif not self._daily_bars_cache or self._daily_bars_cache[-1].ts != bar.ts:
            self._daily_bars_cache.append(bar)
        return self._daily_bars_cache

    def _month_bar_count(self, bars: List[Bar], year: int, month: int) -> int:
        return len([b for b in bars if _parse_date(b.ts).year == year and _parse_date(b.ts).month == month])

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        high = _to_float(state.get("range_high"))
        low = _to_float(state.get("range_low"))
        out: List[LevelUpdate] = []
        if high is not None:
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, "monthly_orb_high", high, ts))
        if low is not None:
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, "monthly_orb_low", low, ts))
        return out

    def _has_open_entry_order(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _cancel_roles(self, context: StrategyContext, roles: set, reason: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if str(order.bracket_role or "") in roles:
                out.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return out

    def _cancel_reduce(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, reason)
            for o in context.strategy_open_orders
            if o.reduce_only
        ]

    def _entry_filter(self) -> Dict[str, Tuple[bool, bool]]:
        if self._entry_filter_cache is None:
            table: Dict[str, Tuple[bool, bool]] = {}
            path = self.config.get("entry_filter_csv")
            if path:
                import csv as _csv

                with open(str(path), newline="", encoding="utf-8") as fh:
                    for row in _csv.DictReader(fh):
                        table[str(row["date"])[:10]] = (
                            str(row["long_ok"]).strip().lower() in {"1", "true", "yes"},
                            str(row["short_ok"]).strip().lower() in {"1", "true", "yes"},
                        )
            self._entry_filter_cache = table
        return self._entry_filter_cache

    def _entry_dir_allowed(self, ts: str, direction: str) -> bool:
        table = self._entry_filter()
        if not table:
            return True
        row = table.get(str(ts)[:10])
        if row is None:
            return True
        return row[0] if direction == "long" else row[1]

    def _stop_mode(self) -> str:
        return str(self.config.get("stop_mode") or "close").strip().lower()

    def _entry_mode(self) -> str:
        return str(self.config.get("entry_mode") or "oco").strip().lower()

    def _is_month_end_bar(self, ts: str) -> bool:
        if not bool(self.config.get("flatten_month_end", True)):
            return False
        day = str(ts)[:10]
        month_end_dates = self.config.get("month_end_dates") or []
        return day in {str(value)[:10] for value in month_end_dates}


def _parse_date(ts: str) -> date:
    text = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text[:10]).date()


def _month_key(ts: str) -> str:
    d = _parse_date(ts)
    return "%04d-%02d" % (d.year, d.month)


def _month_expiry(ts: str) -> str:
    d = _parse_date(ts)
    if d.month == 12:
        return "%04d-12-31T23:59:59" % d.year
    return "%04d-%02d-01T00:00:00" % (d.year, d.month + 1)


def _to_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    return float(value)
