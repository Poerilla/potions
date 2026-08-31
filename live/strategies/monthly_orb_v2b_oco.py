"""Monthly ORB stop entry with configurable scaleout (daily decision bars).

Rules
-----
- OR = first ``or_sessions`` **daily** bars of the NY calendar month.
  ``feed_timeframe`` may be ``D`` (default), ``1m``, or ``4H``: intraday feeds
  aggregate to daily OHLC and run decisions on day close; PaperBroker still
  fills resting stops on the fine tape.
- ``entry_mode=oco``: after OR, OCO stops long @ ORH / short @ ORL.
- ``entry_mode=first_break_opposite``: do **not** arm after OR; wait for the
  first OR break, ignore it, then arm a stop in the **opposite** direction
  (break ORH → short @ ORL; break ORL → long @ ORH). After a filled campaign
  ends, wait for a new ignored break before the next arm.
- ``entry_mode=first_break_opposite_swing_limit``: same ignored first break, then
  wait for a **confirmed 3-bar swing** in the breakout direction (swing high
  after ORH break, swing low after ORL break). Place a **limit** at the swing
  pivot to fade. Targets use the same absolute OR-boundary FBO prices
  (from ORL for shorts / ORH for longs); stop is **1R beyond the fill** so risk
  distance matches classic FBO (R = OR width).
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
  Set ``entry_filter_rearm=False`` to check CSV only at arm time (no
  cancel/retry loop on resting entries).
- ``arm_rsi_buckets`` + ``arm_rsi_csv``: at the moment an FBO/opposite
  (or swing-limit) entry is ready to arm, require the latest completed
  hourly RSI bucket (causal CSV: ``ts,rsi14,rsi_bucket``) to be in the
  allow-list (e.g. ``["rsi_55_70"]``). Reject policy via
  ``arm_filter_on_reject``: ``retry`` (legacy day-filter behavior),
  ``skip_candidate`` (abandon this arm; wait for a new ignored break),
  or ``skip_month`` (no further entries this calendar month).
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
        self._arm_rsi_rows: Optional[List[Tuple[str, str, Optional[float]]]] = None  # (ts_iso, bucket, rsi14)
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
            "entry_mode": "oco",  # oco | first_break_opposite | first_break_opposite_swing_limit
            # After a first_break_opposite campaign stop_close, treat the failed
            # side as the new "ignored break" and arm the other OR boundary.
            "flip_after_stop": False,
            # When swing-limit entry fills, use absolute FBO targets from the OR
            # boundary (ORL for shorts / ORH for longs) and 1R stop from fill.
            "swing_limit_fbo_targets": True,
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
            # When True (default), resting entries are cancelled/re-armed each day
            # the CSV disallows them. False = arm-time CSV check only (static).
            "entry_filter_rearm": True,
            # Arm-time hourly RSI gate (causal feature CSV from HA mill).
            "arm_rsi_csv": None,
            "arm_rsi_buckets": [],  # e.g. ["rsi_55_70"]; empty disables
            # retry | skip_candidate | skip_month
            "arm_filter_on_reject": "retry",
            # D | 1m | 4H — intraday feeds synthesize daily decision bars.
            "feed_timeframe": "D",
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._agg_day: Optional[date] = None
        self._agg_open: Optional[float] = None
        self._agg_high: Optional[float] = None
        self._agg_low: Optional[float] = None
        self._agg_close: Optional[float] = None
        self._agg_volume: float = 0.0
        self._agg_last_ts: str = ""

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if not bar.complete:
            return StrategyActions.empty()
        feed = self._feed_tf()
        if feed == "D":
            if bar.timeframe != "D":
                return StrategyActions.empty()
            return self._on_daily_bar(bar, context)
        # Intraday fill tape: aggregate NY-calendar days → daily decisions.
        if not self._bar_matches_feed(bar, feed):
            return StrategyActions.empty()
        return self._on_intraday_feed_bar(bar, context)

    def flush_intraday_day(self, context: StrategyContext) -> StrategyActions:
        """Finalize the open NY day (call after last feed bar)."""
        if self._agg_day is None:
            return StrategyActions.empty()
        daily = self._finalize_agg_daily()
        return self._on_daily_bar(daily, context)

    def _feed_tf(self) -> str:
        raw = str(self.config.get("feed_timeframe") or "D").strip().lower()
        if raw in {"d", "1d", "daily"}:
            return "D"
        if raw in {"1m", "1min", "m1"}:
            return "1m"
        if raw in {"4h", "4hour", "h4"}:
            return "4H"
        return raw.upper() if raw else "D"

    def _bar_matches_feed(self, bar: Bar, feed: str) -> bool:
        tf = str(bar.timeframe or "").strip()
        if feed == "1m":
            return tf.lower() in {"1m", "1min", "m1"}
        if feed == "4H":
            return tf.upper() in {"4H", "4HOUR"}
        return tf == feed

    def _on_intraday_feed_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        day = _ny_date(bar.ts)
        actions = StrategyActions.empty()
        if self._agg_day is not None and day != self._agg_day:
            daily = self._finalize_agg_daily()
            actions = self._on_daily_bar(daily, context)
            self._start_agg(bar, day)
            return actions
        if self._agg_day is None:
            self._start_agg(bar, day)
        else:
            self._update_agg(bar)
        return actions

    def _start_agg(self, bar: Bar, day: date) -> None:
        self._agg_day = day
        self._agg_open = float(bar.open)
        self._agg_high = float(bar.high)
        self._agg_low = float(bar.low)
        self._agg_close = float(bar.close)
        self._agg_volume = float(bar.volume or 0.0)
        self._agg_last_ts = str(bar.ts)

    def _update_agg(self, bar: Bar) -> None:
        self._agg_high = max(float(self._agg_high or bar.high), float(bar.high))
        self._agg_low = min(float(self._agg_low or bar.low), float(bar.low))
        self._agg_close = float(bar.close)
        self._agg_volume = float(self._agg_volume or 0.0) + float(bar.volume or 0.0)
        self._agg_last_ts = str(bar.ts)

    def _finalize_agg_daily(self) -> Bar:
        day = self._agg_day
        assert day is not None
        daily = Bar(
            instrument=self.instance.instrument,
            timeframe="D",
            # Date-only ts matches daily CSV / entry_filter_csv keys.
            ts=day.isoformat(),
            open=float(self._agg_open),
            high=float(self._agg_high),
            low=float(self._agg_low),
            close=float(self._agg_close),
            volume=float(self._agg_volume or 0.0),
            complete=True,
            source="synth_from_%s" % self._feed_tf(),
        )
        self._agg_day = None
        self._agg_open = self._agg_high = self._agg_low = self._agg_close = None
        self._agg_volume = 0.0
        self._agg_last_ts = ""
        return daily

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
            if self._entry_mode() == "first_break_opposite_swing_limit" and bool(
                self.config.get("swing_limit_fbo_targets", True)
            ):
                # 1R beyond fill preserves classic FBO risk distance (R = OR width).
                r = float(range_high) - float(range_low)
                stop0 = entry - r if direction == "long" else entry + r
                state["use_fbo_anchor_targets"] = True
            else:
                state["use_fbo_anchor_targets"] = False
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
                fbo_like = self._entry_mode() in {
                    "first_break_opposite",
                    "first_break_opposite_swing_limit",
                }
                state["phase"] = "wait_first_break" if fbo_like else "wait_breakout"
                state["first_break_side"] = ""
                state["opposite_armed"] = False
                state["swing_armed"] = False
                state["swing_pivot"] = None
                state["break_bar_ts"] = ""
                state["use_fbo_anchor_targets"] = False
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
            elif month_bar_count == or_sessions and self._entry_mode() in {
                "first_break_opposite",
                "first_break_opposite_swing_limit",
            }:
                state["phase"] = "wait_first_break"
                state["first_break_side"] = ""
                state["swing_armed"] = False
                state["swing_pivot"] = None
                state["break_bar_ts"] = ""
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

        # Entry-direction filter: optionally cancel resting entry stops whose
        # direction is no longer allowed (legacy daily re-arm). Arm-time-static
        # mode leaves resting orders alone after a successful arm.
        if bool(self.config.get("entry_filter_rearm", True)) and context.position_quantity == 0:
            for order in context.strategy_open_orders:
                if order.reduce_only:
                    continue
                direction = "long" if order.side == "buy" else "short"
                if not self._entry_dir_allowed(bar.ts, direction):
                    cancels.append(
                        CancelIntent(self.instance.strategy_id, order.broker_order_id, "entry_filter_block")
                    )
                    state["opposite_armed"] = False
                    state["swing_armed"] = False
                    if self._entry_mode() == "first_break_opposite":
                        state["phase"] = "arm_opposite"
                    elif self._entry_mode() == "first_break_opposite_swing_limit":
                        state["phase"] = "wait_swing"

        flat = context.position_quantity == 0 and not self._has_open_entry_order(context)
        room = int(state.get("trade_count", 0)) < int(self.config["max_trades_per_month"])
        if str(state.get("phase") or "") == "arm_filter_skip_month":
            room = False
        if flat and room:
            mode = self._entry_mode()
            if mode == "first_break_opposite":
                orders.extend(self._first_break_opposite_orders(bar, range_high, range_low, state))
            elif mode == "first_break_opposite_swing_limit":
                orders.extend(self._first_break_swing_limit_orders(bar, range_high, range_low, state))
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
        anchor = bool(state.get("use_fbo_anchor_targets"))
        if direction == "long":
            # Classic FBO longs enter @ ORH; keep those absolute targets when fading
            # via a better swing-low limit fill.
            base = float(range_high) if anchor else entry
            tp1 = base + tp1_r * r
            tp2 = base + tp2_r * r
            runner_tp = base + runner_r * r if runner_r is not None else None
            stop = float(entry - r) if anchor else float(range_low)
            exit_side = "sell"
        else:
            base = float(range_low) if anchor else entry
            tp1 = base - tp1_r * r
            tp2 = base - tp2_r * r
            runner_tp = base - runner_r * r if runner_r is not None else None
            stop = float(entry + r) if anchor else float(range_high)
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
            "swing_armed": False,
            "swing_pivot": None,
            "break_bar_ts": "",
            "use_fbo_anchor_targets": False,
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
        # After an arm-time filter skip, wait for a full close back inside the OR
        # before a new ignored-break cycle (avoids re-arming the same breakout).
        if str(state.get("phase") or "") == "wait_inside_after_filter_skip":
            if bar.high < float(range_high) and bar.low > float(range_low):
                state["phase"] = "wait_first_break"
                state["first_break_side"] = ""
                state["opposite_armed"] = False
            return []

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
        ok, reason = self._arm_filters_ok(bar.ts, opposite)
        if not ok:
            self._apply_arm_filter_reject(state, reason=reason)
            return []
        stop_price = float(range_low) if opposite == "short" else float(range_high)
        state["opposite_armed"] = True
        state["phase"] = "wait_fill"
        return [self._single_boundary_stop(opposite, bar.ts, stop_price, state)]

    def _first_break_swing_limit_orders(
        self,
        bar: Bar,
        range_high: float,
        range_low: float,
        state: Dict[str, Any],
    ) -> List[OrderIntent]:
        """Ignore first OR break, then limit-fade at the confirmed 3-bar swing."""
        break_side = str(state.get("first_break_side") or "")
        if not break_side:
            long_hit = bar.high >= float(range_high)
            short_hit = bar.low <= float(range_low)
            if long_hit and short_hit:
                return []
            if not long_hit and not short_hit:
                return []
            break_side = "long" if long_hit else "short"
            state["first_break_side"] = break_side
            state["break_bar_ts"] = str(bar.ts)
            state["phase"] = "wait_swing"
            state["swing_armed"] = False
            state["swing_pivot"] = None
            # Swing needs three completed bars; confirm on a later close.
            return []

        if bool(state.get("swing_armed")):
            return []

        opposite = "short" if break_side == "long" else "long"
        if opposite == "short" and not bool(self.config.get("allow_shorts", True)):
            return []
        ok, reason = self._arm_filters_ok(bar.ts, opposite)
        if not ok:
            self._apply_arm_filter_reject(state, reason=reason)
            return []

        pivot = self._confirmed_breakout_swing(
            bar,
            break_side=break_side,
            break_bar_ts=str(state.get("break_bar_ts") or ""),
            range_high=float(range_high),
            range_low=float(range_low),
        )
        if pivot is None:
            state["phase"] = "wait_swing"
            return []

        state["swing_pivot"] = pivot
        state["swing_armed"] = True
        state["phase"] = "wait_fill"
        return [self._swing_limit_entry(opposite, bar.ts, float(pivot), state)]

    def _confirmed_breakout_swing(
        self,
        bar: Bar,
        *,
        break_side: str,
        break_bar_ts: str,
        range_high: float,
        range_low: float,
    ) -> Optional[float]:
        """Return pivot price once the 3rd candle of a post-break swing has closed.

        Swing high (after ORH break): high[i-1] > high[i-2] and high[i-1] > high[i].
        Swing low (after ORL break): low[i-1] < low[i-2] and low[i-1] < low[i].
        The pivot bar itself must be on/after the ignored breakout bar.
        """
        bars = self._daily_bars(bar)
        dt = _parse_date(bar.ts)
        month = [b for b in bars if _parse_date(b.ts).year == dt.year and _parse_date(b.ts).month == dt.month]
        if len(month) < 3:
            return None
        # Confirm on the latest closed bar as candle #3.
        a, b, c = month[-3], month[-2], month[-1]
        if str(c.ts) != str(bar.ts):
            return None
        break_ts = str(break_bar_ts or "")
        if break_ts and str(b.ts) < break_ts:
            return None
        if break_side == "long":
            # Fade short from swing high created by the upside break.
            if float(b.high) > float(a.high) and float(b.high) > float(c.high) and float(b.high) >= float(range_high):
                return float(b.high)
            return None
        # Fade long from swing low created by the downside break.
        if float(b.low) < float(a.low) and float(b.low) < float(c.low) and float(b.low) <= float(range_low):
            return float(b.low)
        return None

    def _swing_limit_entry(
        self,
        direction: str,
        ts: str,
        limit_price: float,
        state: Dict[str, Any],
    ) -> OrderIntent:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        trade_id = "%s_%s_%02d" % (
            self.instance.strategy_id,
            state["month_key"].replace("-", ""),
            state["trade_seq"],
        )
        tp1_qty, tp2_qty, runner_qty = self._unit_quantities()
        qty = tp1_qty + tp2_qty + runner_qty
        side = "buy" if direction == "long" else "sell"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=qty,
            limit_price=limit_price,
            reason="%s_swing_limit_entry" % direction,
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=_month_expiry(ts),
        )

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
            # Prefer stored D bars when present; otherwise start fresh (1m/4H feed).
            stored = self.store.read_bars(self.instance.instrument, "D")
            self._daily_bars_cache = list(stored) if stored else []
        if not self._daily_bars_cache or self._daily_bars_cache[-1].ts != bar.ts:
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

    def _arm_rsi_buckets(self) -> List[str]:
        raw = self.config.get("arm_rsi_buckets") or []
        if isinstance(raw, str):
            raw = [p.strip() for p in raw.split(",") if p.strip()]
        return [str(x).strip() for x in raw if str(x).strip()]

    def _arm_rsi_series(self) -> List[Tuple[str, str, Optional[float]]]:
        if self._arm_rsi_rows is not None:
            return self._arm_rsi_rows
        rows: List[Tuple[str, str, Optional[float]]] = []
        path = self.config.get("arm_rsi_csv")
        if path and self._arm_rsi_buckets():
            import csv as _csv

            with open(str(path), newline="", encoding="utf-8") as fh:
                for row in _csv.DictReader(fh):
                    ts = str(row.get("ts") or row.get("available_ts") or "").strip()
                    bucket = str(row.get("rsi_bucket") or "").strip()
                    rsi_raw = row.get("rsi14")
                    rsi14 = float(rsi_raw) if rsi_raw not in (None, "") else None
                    if not ts:
                        continue
                    # Normalize to comparable UTC Z strings for binary search.
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if dt.tzinfo is not None:
                            from datetime import timezone

                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                        else:
                            ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        pass
                    rows.append((ts, bucket, rsi14))
            rows.sort(key=lambda x: x[0])
        self._arm_rsi_rows = rows
        return rows

    def _arm_rsi_row_at(self, ts: str) -> Optional[Tuple[str, str, Optional[float]]]:
        series = self._arm_rsi_series()
        if not series:
            return None
        day = str(ts)[:10]
        decision = day + "T23:59:59Z"
        lo, hi = 0, len(series)
        while lo < hi:
            mid = (lo + hi) // 2
            if series[mid][0] <= decision:
                lo = mid + 1
            else:
                hi = mid
        if lo <= 0:
            return None
        return series[lo - 1]

    def _arm_rsi_bucket_at(self, ts: str) -> Optional[str]:
        row = self._arm_rsi_row_at(ts)
        return row[1] if row else None

    def _arm_rsi14_at(self, ts: str) -> Optional[float]:
        row = self._arm_rsi_row_at(ts)
        return row[2] if row else None

    def _arm_rsi_ok(self, ts: str, direction: str) -> bool:
        buckets = self._arm_rsi_buckets()
        if not buckets:
            return True
        if not self.config.get("arm_rsi_csv"):
            return False
        got = self._arm_rsi_bucket_at(ts)
        rsi14 = self._arm_rsi14_at(ts)
        for bucket in buckets:
            if bucket == "rsi_with_side":
                if direction == "long" and rsi14 is not None and rsi14 >= 55:
                    return True
                if direction == "short" and rsi14 is not None and rsi14 <= 45:
                    return True
            elif got == bucket:
                return True
        return False

    def _arm_filters_ok(self, ts: str, direction: str) -> Tuple[bool, str]:
        """CSV direction + optional arm-time RSI bucket. Returns (ok, reject_reason)."""
        if not self._entry_dir_allowed(ts, direction):
            return False, "entry_filter_csv"
        if self._arm_rsi_buckets():
            if not self._arm_rsi_ok(ts, direction):
                return False, "arm_rsi_bucket"
        return True, ""

    def _apply_arm_filter_reject(self, state: Dict[str, Any], *, reason: str) -> None:
        policy = str(self.config.get("arm_filter_on_reject") or "retry").strip().lower()
        state["arm_filter_reject_reason"] = reason
        state["opposite_armed"] = False
        state["swing_armed"] = False
        if policy in {"skip_candidate", "skip_cand", "candidate"}:
            # Abandon this opposite-arm opportunity; require a return inside OR
            # before a new ignored-break cycle (no day-by-day RSI retry).
            state["phase"] = "wait_inside_after_filter_skip"
            state["opposite_armed"] = False
            state["swing_armed"] = False
            state["swing_pivot"] = None
            # keep first_break_side for diagnostics; cleared when back inside
        elif policy in {"skip_month", "month"}:
            state["phase"] = "arm_filter_skip_month"
            state["first_break_side"] = ""
            state["swing_pivot"] = None
            state["break_bar_ts"] = ""
        else:
            # retry: stay in arm_opposite / wait_swing and try again next bar.
            if self._entry_mode() == "first_break_opposite_swing_limit":
                state["phase"] = "wait_swing"
            else:
                state["phase"] = "arm_opposite"

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


def _ny_date(ts: str) -> date:
    """NY calendar date for a bar timestamp (UTC or naive ISO)."""
    text = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.fromisoformat(text[:10])
    if dt.tzinfo is None:
        # Bare dates / naive timestamps: treat as already NY calendar dates.
        return dt.date()
    try:
        from zoneinfo import ZoneInfo

        return dt.astimezone(ZoneInfo("America/New_York")).date()
    except Exception:
        import pytz

        return dt.astimezone(pytz.timezone("America/New_York")).date()


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
