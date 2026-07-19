from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..models import Alert, Bar, CancelIntent, FeatureSnapshot, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot


class V2BScaleoutStrategy(StrategyPlugin):
    """Intraday v2b opening-range breakout scaleout.

    This is the live-orderable version of the v2b family.  The research-only
    long-priority scanner is intentionally not implemented here because it can
    select a later long before an earlier short.  Supported modes are:

    - ``oco_then_reverse``: arm both sides after the OR; first fill owns leg 1,
      then the opposite side may arm after leg 1 exits.
    - ``strict_long_then_short``: arm long only; short can arm only after a
      filled long exits.
    """

    strategy_type = "v2b_scaleout"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "mode": "oco_then_reverse",
            "tick_size": 0.25,
            "entry_qty": 2,
            "tp1_qty": None,        # default: 1 (legacy)
            "tp2_qty": None,        # default: 1 (legacy); runner = entry_qty - tp1_qty - tp2_qty
            "rth_start": "09:30",
            "or_end": "09:45",
            "eod_cutoff": "15:59",
            "use_regime_filter": True,
            "require_regime_dates": False,
            "regime_dates": [],
            "record_levels": False,
            "dynamic_sizing_events": {},
            "prior_opposite_only": False,
            "prior_opposite_entry_qty": None,
            "prior_opposite_tp1_qty": None,
            "prior_opposite_tp2_qty": None,
            # After entry, flatten if no opposite ST event by this many minutes
            # (uses dynamic_sizing_events with the same opposite-side lookup).
            "invalidate_without_opposite_minutes": None,
            # Optional yearly-ORB (or other) directional gate:
            # session_date -> "Long" | "Short". Missing/empty = no arm that day
            # when use_session_direction_bias is True.
            "use_session_direction_bias": False,
            "session_direction_bias": {},
            # Optional day/month open alignment gate (checked vs bar close at arm):
            # Long only if price > ref_open (often day or yesterday) and price > month_open;
            # Short only if price < ref_open and price < month_open.
            # Failed checks skip arm without marking entry_armed so later bars retry.
            # Entries remain opening-range boundary stops (OR high/low ± tick).
            # When arm_open_filter_at_or_only is True, only attempt the open-filter
            # arm at OR finalize (no mid-session catch-up arms).
            "use_open_alignment_filter": False,
            "arm_open_filter_at_or_only": False,
            "session_day_opens": {},
            "session_month_opens": {},
            # Optional previous-month-close direction gate (checked vs bar close at arm):
            # mode "fade":  Long if price < PMC; Short if price > PMC
            # mode "follow": Long if price > PMC; Short if price < PMC
            # Failed checks skip arm without marking entry_armed so later bars retry.
            "use_pmc_fade_filter": False,
            "pmc_bias_mode": "fade",
            "session_prev_month_closes": {},
            # Optional per-session earliest arm timestamp (ISO). Arms only when
            # bar.ts >= this instant (e.g. after an hourly ST sweep). Missing → no delay.
            "session_arm_after_ts": {},
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._regime_dates = set(str(x) for x in self.config.get("regime_dates", []))

    def _unit_quantities(self, trade: Optional[Dict[str, Any]] = None) -> tuple[int, int, int]:
        """Return ``(tp1_qty, tp2_qty, runner_qty)``.

        Legacy behaviour: ``tp1_qty=1``, ``tp2_qty=1``,
        ``runner_qty = entry_qty - 2``. New per-bucket knobs ``tp1_qty`` and
        ``tp2_qty`` let a sweep express asymmetric ladders like 4 / 2 / 1.
        The runner is whatever remains of the entry after TP1 and TP2.
        """

        trade = trade or {}
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        tp1_raw = trade.get("tp1_qty", self.config.get("tp1_qty"))
        tp2_raw = trade.get("tp2_qty", self.config.get("tp2_qty"))
        tp1 = 1 if tp1_raw is None else int(tp1_raw)
        tp2 = 1 if tp2_raw is None else int(tp2_raw)
        if tp1 < 0:
            tp1 = 0
        if tp2 < 0:
            tp2 = 0
        if tp1 + tp2 > entry_qty:
            # Clamp so the ladder never exceeds the entry size.
            overflow = (tp1 + tp2) - entry_qty
            take_from_tp2 = min(tp2, overflow)
            tp2 -= take_from_tp2
            overflow -= take_from_tp2
            tp1 -= overflow
            if tp1 < 0:
                tp1 = 0
        runner = max(0, entry_qty - tp1 - tp2)
        return tp1, tp2, runner

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "1m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_1m_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            sizing = dict((trade.get("sizing_by_direction") or {}).get(direction) or {})
            trade.update(
                {
                    "direction": direction,
                    "entry_price": fill.price,
                    "entry_ts": fill.ts,
                    "status": "open",
                    "tp1_hit": False,
                    "entry_qty": int(sizing.get("entry_qty") or fill.quantity),
                    "tp1_qty": sizing.get("tp1_qty"),
                    "tp2_qty": sizing.get("tp2_qty"),
                }
            )
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = direction
            state["entry_armed"] = []
            state["current_leg_open"] = True
            orders = self._initial_exit_orders(fill.trade_id, direction, state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role == "tp1":
            trade["tp1_hit"] = True
            cancels = self._cancel_open_roles(context, fill.trade_id, {"wide_stop", "tp2"})
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                direction = str(trade.get("direction") or state.get("active_direction") or "")
                # Rebuild TP2 behind the runner stop so same-bar ambiguity is
                # pessimistic: runner stop is checked before TP2.
                orders.extend(self._runner_exit_orders(fill.trade_id, direction, state))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"wide_stop", "runner_stop", "tp2", "eod_close", "invalidate_no_opposite_st"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                state["current_leg_open"] = False
                state["legs_done"] = int(state.get("legs_done", 0)) + 1
                state["last_exit_ts"] = fill.ts
                state["last_exit_direction"] = str(trade.get("direction") or state.get("active_direction") or "")
                state["active_trade_id"] = ""
                state["active_direction"] = ""
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                orders = self._maybe_arm_next_leg(fill.ts, state, context)
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_1m_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        session = dt.date().isoformat()
        t = dt.time()
        state = self._state()
        if state.get("session_date") != session:
            state = self._fresh_session_state(session)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []
        causal_features: List[FeatureSnapshot] = []

        if not self._in_rth(t):
            self._commit_state(state)
            return StrategyActions.empty()

        state["last_bar_close"] = float(bar.close)

        if t >= self._time("eod_cutoff"):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eod_close", order_type="market_close"))
            state["done"] = True
            state["phase"] = "eod"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, causal_features)

        invalidate = self._maybe_invalidate_without_opposite(bar, state, context)
        if invalidate is not None:
            return invalidate

        if t < self._time("or_end"):
            state["or_count"] = int(state.get("or_count", 0)) + 1
            state["or_high"] = bar.high if state.get("or_high") is None else max(float(state["or_high"]), bar.high)
            state["or_low"] = bar.low if state.get("or_low") is None else min(float(state["or_low"]), bar.low)
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            if state["or_count"] >= 15 and not state.get("or_finalized"):
                state["or_finalized"] = True
                state["phase"] = "armed" if self._regime_ok(session) else "regime_skip"
                state["regime_ok"] = self._regime_ok(session)
                causal_features.extend(self._opening_range_features(bar.ts, state))
                if state["regime_ok"]:
                    directions = self._directions_for_session(session)
                    causal_features.extend(self._entry_gate_features(bar.ts, state, directions, price=bar.close))
                    orders.extend(self._arm_initial_entries(bar.ts, state, directions, price=bar.close))
                    if bool(self.config.get("use_open_alignment_filter")) and bool(
                        self.config.get("arm_open_filter_at_or_only")
                    ):
                        # One shot at OR finalize — do not catch up mid-session.
                        state["open_filter_arm_attempted"] = True
                    if directions and not bool(self.config.get("suppress_alerts")):
                        alerts.append(Alert.create(self.instance.strategy_id, "info", "v2b opening range armed"))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, causal_features)

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        if state.get("regime_ok") and not state.get("done") and not state.get("current_leg_open") and int(state.get("legs_done", 0)) == 0:
            if not self._has_open_entry_order(context):
                # Skip catch-up arms when open-filter is OR-end-only.
                if bool(self.config.get("use_open_alignment_filter")) and bool(
                    self.config.get("arm_open_filter_at_or_only")
                ) and bool(state.get("open_filter_arm_attempted")):
                    pass
                else:
                    causal_features.extend(self._opening_range_features(bar.ts, state))
                    directions = self._directions_for_session(session)
                    causal_features.extend(self._entry_gate_features(bar.ts, state, directions, price=bar.close))
                    orders.extend(self._arm_initial_entries(bar.ts, state, directions, price=bar.close))

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts, causal_features)

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("session_date", "")
        state.setdefault("or_count", 0)
        state.setdefault("or_high", None)
        state.setdefault("or_low", None)
        state.setdefault("or_finalized", False)
        state.setdefault("regime_ok", False)
        state.setdefault("phase", "")
        state.setdefault("done", False)
        state.setdefault("trade_seq", 0)
        state.setdefault("legs_done", 0)
        state.setdefault("current_leg_open", False)
        state.setdefault("active_trade_id", "")
        state.setdefault("active_direction", "")
        state.setdefault("entry_armed", [])
        state.setdefault("trades", {})
        return state

    def _fresh_session_state(self, session: str) -> Dict[str, Any]:
        return {
            "session_date": session,
            "or_count": 0,
            "or_high": None,
            "or_low": None,
            "or_finalized": False,
            "regime_ok": False,
            "phase": "building_or",
            "done": False,
            "trade_seq": 0,
            "legs_done": 0,
            "current_leg_open": False,
            "active_trade_id": "",
            "active_direction": "",
            "entry_armed": [],
            "open_filter_arm_attempted": False,
            "last_bar_close": None,
            "last_exit_ts": "",
            "last_exit_direction": "",
            "opposite_confirmed": False,
            "invalidated": False,
            "trades": {},
        }

    def _maybe_invalidate_without_opposite(
        self,
        bar: Bar,
        state: Dict[str, Any],
        context: StrategyContext,
    ) -> Optional[StrategyActions]:
        raw = self.config.get("invalidate_without_opposite_minutes")
        if raw is None or raw == "":
            return None
        if context.position_quantity == 0 or not state.get("current_leg_open"):
            return None
        if state.get("invalidated") or state.get("opposite_confirmed"):
            return None
        trade_id = str(state.get("active_trade_id") or "")
        trade = self._trade(trade_id, state) if trade_id else {}
        direction = str(trade.get("direction") or state.get("active_direction") or "")
        entry_ts = str(trade.get("entry_ts") or "")
        if direction not in {"Long", "Short"} or not entry_ts:
            return None
        if self._prior_opposite_event_for_entry(bar.ts, direction) is not None:
            state["opposite_confirmed"] = True
            self._commit_state(state)
            return None
        try:
            deadline = _parse_dt(entry_ts) + timedelta(minutes=int(raw))
        except Exception:
            return None
        if _parse_dt(bar.ts) < deadline:
            return None
        # Past deadline with no opposite ST event yet — flatten and stop re-arming.
        state["invalidated"] = True
        state["done"] = True
        state["phase"] = "invalidated_no_opposite"
        cancels = self._cancel_all_open(context)
        orders = [self._close_all(context, bar.ts, "invalidate_no_opposite_st", order_type="market")]
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

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

    def _directions_for_session(self, session: str) -> List[str]:
        """Return which entry sides may arm today.

        With ``use_session_direction_bias``, only the mapped Long/Short may arm
        (missing/empty map → none). Without bias, honour ``mode``.
        """
        if bool(self.config.get("use_session_direction_bias")):
            bias = str((self.config.get("session_direction_bias") or {}).get(session) or "").strip()
            if bias in {"Long", "Short"}:
                return [bias]
            return []
        if str(self.config.get("mode", "oco_then_reverse")) == "strict_long_then_short":
            return ["Long"]
        return ["Long", "Short"]

    def _open_alignment_ok(self, session: str, direction: str, price: Optional[float]) -> bool:
        """Long above day+month open; Short below both. No-op when filter off."""
        if not bool(self.config.get("use_open_alignment_filter")):
            return True
        if price is None:
            return False
        day_open = _to_float((self.config.get("session_day_opens") or {}).get(session))
        month_open = _to_float((self.config.get("session_month_opens") or {}).get(session))
        if day_open is None or month_open is None:
            return False
        if direction == "Long":
            return float(price) > day_open and float(price) > month_open
        if direction == "Short":
            return float(price) < day_open and float(price) < month_open
        return False

    def _pmc_fade_ok(self, session: str, direction: str, price: Optional[float]) -> bool:
        """PMC direction gate. No-op when filter off.

        ``pmc_bias_mode``:
        - ``fade`` (default): Long below PMC, Short above PMC
        - ``follow``: Long above PMC, Short below PMC
        """
        if not bool(self.config.get("use_pmc_fade_filter")):
            return True
        if price is None:
            return False
        pmc = _to_float((self.config.get("session_prev_month_closes") or {}).get(session))
        if pmc is None:
            return False
        mode = str(self.config.get("pmc_bias_mode") or "fade").strip().lower()
        above = float(price) > float(pmc)
        below = float(price) < float(pmc)
        if mode == "follow":
            if direction == "Long":
                return above
            if direction == "Short":
                return below
            return False
        # fade
        if direction == "Long":
            return below
        if direction == "Short":
            return above
        return False

    def _direction_filters_ok(self, session: str, direction: str, price: Optional[float]) -> bool:
        return self._open_alignment_ok(session, direction, price) and self._pmc_fade_ok(session, direction, price)

    def _arm_time_ok(self, session: str, ts: str) -> bool:
        """True when session has no arm-after delay, or bar.ts has reached it."""
        raw = (self.config.get("session_arm_after_ts") or {}).get(session)
        if raw is None or raw == "":
            return True
        try:
            return _parse_dt(ts) >= _parse_dt(str(raw))
        except Exception:
            return False

    def _arm_initial_entries(
        self,
        ts: str,
        state: Dict[str, Any],
        directions: Optional[Sequence[str]] = None,
        *,
        price: Optional[float] = None,
    ) -> List[OrderIntent]:
        session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
        if not self._arm_time_ok(session, ts):
            return []
        if directions is None:
            directions = self._directions_for_session(session)
        if not directions:
            return []
        return self._entry_orders(ts, state, list(directions), price=price)

    def _maybe_arm_next_leg(self, ts: str, state: Dict[str, Any], context: StrategyContext) -> List[OrderIntent]:
        if state.get("done"):
            return []
        if int(state.get("legs_done", 0)) >= 2:
            state["phase"] = "done"
            return []
        if context.position_quantity != 0 or self._has_open_entry_order(context):
            return []
        last_direction = str(state.get("last_exit_direction") or "")
        if last_direction not in {"Long", "Short"}:
            return []
        opposite = "Short" if last_direction == "Long" else "Long"
        session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
        allowed = set(self._directions_for_session(session))
        if opposite not in allowed:
            # Directional bias / long-only modes: do not reverse into the banned side.
            state["phase"] = "done"
            return []
        # Prefer last bar close so PMC / open filters can evaluate on reverse arm.
        ref_price = _to_float(state.get("last_bar_close"))
        return self._entry_orders(ts, state, [opposite], price=ref_price)

    def _entry_orders(
        self,
        ts: str,
        state: Dict[str, Any],
        directions: Sequence[str],
        *,
        price: Optional[float] = None,
    ) -> List[OrderIntent]:
        range_high = _to_float(state.get("or_high"))
        range_low = _to_float(state.get("or_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            return []
        session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
        armed = set(str(x) for x in state.get("entry_armed", []))
        # Only OCO if multiple directions survive open-alignment / PMC filtering.
        filtered = [
            d
            for d in directions
            if d not in armed and self._direction_filters_ok(session, d, price)
        ]
        if not filtered:
            return []
        trade_id = self._new_trade_id(state)
        oco = "%s_entry_oco" % trade_id if len(filtered) > 1 else ""
        out: List[OrderIntent] = []
        for direction in filtered:
            sizing = self._sizing_for_entry(ts, direction)
            if sizing is None:
                continue
            state["trades"][trade_id] = {
                "direction": direction,
                "status": "armed",
                "range_high": range_high,
                "range_low": range_low,
                "range_value": range_high - range_low,
                "sizing_by_direction": {
                    direction: {
                        "entry_qty": int(sizing["entry_qty"]),
                        "tp1_qty": int(sizing["tp1_qty"]),
                        "tp2_qty": int(sizing["tp2_qty"]),
                    }
                },
            }
            out.append(self._entry_order(trade_id, direction, ts, range_high, range_low, oco, int(sizing["entry_qty"])))
            armed.add(direction)
        state["entry_armed"] = sorted(armed)
        return out

    def _opening_range_features(self, ts: str, state: Dict[str, Any]) -> List[FeatureSnapshot]:
        range_high = _to_float(state.get("or_high"))
        range_low = _to_float(state.get("or_low"))
        if range_high is None or range_low is None:
            return []
        return [
            feature_snapshot(
                self.instance,
                "v2b_opening_range",
                ts,
                source="completed_1m_opening_range",
                value_ref="%.8f/%.8f" % (range_high, range_low),
                metadata={
                    "session": state.get("session_date"),
                    "or_count": state.get("or_count"),
                    "or_finalized": state.get("or_finalized"),
                    "range_value": range_high - range_low,
                    "regime_ok": state.get("regime_ok"),
                    "mode": self.config.get("mode"),
                },
            ),
            feature_snapshot(
                self.instance,
                "v2b_regime_filter",
                ts,
                event_ts=str(state.get("session_date") or ts),
                source="config.regime_dates",
                value_ref=str(bool(state.get("regime_ok"))),
                metadata={
                    "use_regime_filter": self.config.get("use_regime_filter"),
                    "require_regime_dates": self.config.get("require_regime_dates"),
                    "regime_dates_count": len(self._regime_dates),
                },
            ),
        ]

    def _entry_gate_features(
        self,
        ts: str,
        state: Dict[str, Any],
        directions: Sequence[str],
        *,
        price: Optional[float] = None,
    ) -> List[FeatureSnapshot]:
        range_high = _to_float(state.get("or_high"))
        range_low = _to_float(state.get("or_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            return []
        out: List[FeatureSnapshot] = []
        session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
        armed = set(str(x) for x in state.get("entry_armed", []))
        for direction in directions:
            prior_event = self._prior_opposite_event_for_entry(ts, direction)
            sizing = self._sizing_for_entry(ts, direction)
            open_ok = self._open_alignment_ok(session, direction, price)
            pmc_ok = self._pmc_fade_ok(session, direction, price)
            allowed = direction not in armed and sizing is not None and open_ok and pmc_ok
            event_ts = str(prior_event.get("ts")) if prior_event else ts
            out.append(
                feature_snapshot(
                    self.instance,
                    "v2b_entry_gate",
                    ts,
                    event_ts=event_ts,
                    available_at_ts=event_ts if prior_event else ts,
                    source="v2b_scaleout.dynamic_sizing_events" if prior_event else "v2b_scaleout.opening_range",
                    value_ref="%s:%s" % (direction, "allowed" if allowed else "blocked"),
                    metadata={
                        "direction": direction,
                        "already_armed": direction in armed,
                        "prior_opposite_only": self.config.get("prior_opposite_only"),
                        "has_prior_opposite_event": prior_event is not None,
                        "prior_event": prior_event or {},
                        "sizing": sizing or {},
                        "range_high": range_high,
                        "range_low": range_low,
                        "open_alignment_ok": open_ok,
                        "use_open_alignment_filter": bool(self.config.get("use_open_alignment_filter")),
                        "pmc_fade_ok": pmc_ok,
                        "use_pmc_fade_filter": bool(self.config.get("use_pmc_fade_filter")),
                        "pmc_bias_mode": str(self.config.get("pmc_bias_mode") or "fade"),
                    },
                )
            )
        return out

    def _entry_order(self, trade_id: str, direction: str, ts: str, range_high: float, range_low: float, oco: str, quantity: int) -> OrderIntent:
        tick = float(self.config["tick_size"])
        if direction == "Long":
            side = "buy"
            stop_price = range_high + tick
        else:
            side = "sell"
            stop_price = range_low - tick
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="stop",
            quantity=quantity,
            stop_price=stop_price,
            reason="v2b_%s_entry" % direction.lower(),
            requires_verification=True,
            bracket_role="entry",
            oco_group=oco,
            live_after_ts=ts,
            expires_after_ts=_session_expiry(ts),
        )

    def _sizing_for_entry(self, ts: str, direction: str) -> Optional[Dict[str, int]]:
        base = {
            "entry_qty": int(self.config["entry_qty"]),
            "tp1_qty": 1 if self.config.get("tp1_qty") is None else int(self.config.get("tp1_qty")),
            "tp2_qty": 1 if self.config.get("tp2_qty") is None else int(self.config.get("tp2_qty")),
        }
        if not self.config.get("dynamic_sizing_events"):
            return base
        has_prior_opposite = self._prior_opposite_event_for_entry(ts, direction) is not None
        if bool(self.config.get("prior_opposite_only")) and not has_prior_opposite:
            return None
        if has_prior_opposite and self.config.get("prior_opposite_entry_qty") is not None:
            return {
                "entry_qty": int(self.config.get("prior_opposite_entry_qty")),
                "tp1_qty": int(self.config.get("prior_opposite_tp1_qty")),
                "tp2_qty": int(self.config.get("prior_opposite_tp2_qty")),
            }
        return base

    def _has_prior_opposite_event(self, ts: str, direction: str) -> bool:
        return self._prior_opposite_event_for_entry(ts, direction) is not None

    def _prior_opposite_event_for_entry(self, ts: str, direction: str) -> Optional[Dict[str, Any]]:
        dt = _parse_dt(ts)
        session = dt.date().isoformat()
        wanted = "short" if direction == "Long" else "long"
        events = (self.config.get("dynamic_sizing_events") or {}).get(session, [])
        best: Optional[Dict[str, Any]] = None
        best_ts: Optional[Any] = None
        for event in events:
            try:
                # Prefer available_at_ts when present (e.g. ST hour-complete).
                event_ts = _parse_dt(str(event.get("available_at_ts") or event.get("ts") or ""))
            except Exception:
                continue
            if str(event.get("side") or "").lower() == wanted and event_ts < dt:
                if best is None or best_ts is None or event_ts > best_ts:
                    best = dict(event)
                    best_ts = event_ts
        return best

    def _initial_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        params = self._params(direction, state)
        if params is None:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        trade = self._trade(trade_id, state)
        tp1_qty, tp2_qty, _runner_qty = self._unit_quantities(trade)
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        out: List[OrderIntent] = []
        out.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=entry_qty,
                stop_price=params["init_sl"],
                reason="v2b_wide_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="wide_stop",
                expires_after_ts=_session_expiry(str(state.get("session_date", ""))),
            )
        )
        if tp1_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=params["tp1"],
                    reason="v2b_tp1",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp1",
                    expires_after_ts=_session_expiry(str(state.get("session_date", ""))),
                )
            )
        if tp2_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=params["tp2"],
                    reason="v2b_tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=_session_expiry(str(state.get("session_date", ""))),
                )
            )
        return out

    def _runner_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        params = self._params(direction, state)
        if params is None:
            return []
        trade = self._trade(trade_id, state)
        _tp1_qty, tp2_qty, runner_qty = self._unit_quantities(trade)
        # After TP1 fills, the remaining position is tp2_qty + runner_qty.
        # Cover the whole remaining stack with a runner stop, and put a TP2 limit
        # for the tp2_qty bucket. The implicit "runner" rides until either the
        # runner stop or the session EOD flatten.
        if runner_qty <= 0 and tp2_qty <= 0:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _session_expiry(str(state.get("session_date", "")))
        out: List[OrderIntent] = []
        runner_stack = max(0, tp2_qty + runner_qty)
        if runner_stack > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="stop",
                    quantity=runner_stack,
                    stop_price=params["runner_sl"],
                    reason="v2b_runner_stop",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="runner_stop",
                    expires_after_ts=expiry,
                )
            )
        if tp2_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=params["tp2"],
                    reason="v2b_tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=expiry,
                )
            )
        return out

    def _params(self, direction: str, state: Dict[str, Any]) -> Optional[Dict[str, float]]:
        range_high = _to_float(state.get("or_high"))
        range_low = _to_float(state.get("or_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            return None
        range_value = range_high - range_low
        tick = float(self.config["tick_size"])
        if direction == "Long":
            return {
                "entry": range_high + tick,
                "init_sl": range_low,
                "tp1": range_high + range_value,
                "tp2": range_high + 2.0 * range_value,
                "runner_sl": range_high + tick,
            }
        return {
            "entry": range_low - tick,
            "init_sl": range_high,
            "tp1": range_low - range_value,
            "tp2": range_low - 2.0 * range_value,
            "runner_sl": range_low - tick,
        }

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

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: Iterable[str]) -> List[CancelIntent]:
        role_set = set(roles)
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_cancel_%s" % order.bracket_role)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.bracket_role in role_set
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "v2b_eod")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry_order(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        high = _to_float(state.get("or_high"))
        low = _to_float(state.get("or_low"))
        if high is None or low is None:
            return []
        return [
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "v2b_or_high", high, ts),
            LevelUpdate(self.instance.strategy_id, self.instance.instrument, "v2b_or_low", low, ts),
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


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def _session_expiry(ts: str) -> str:
    # Date-only inputs come from persisted state.  ISO timestamp inputs come
    # from bars.  Both produce a sortable same-day 15:59 expiry.
    if len(str(ts)) >= 10:
        return str(ts)[:10] + "T15:59:00"
    try:
        return date.fromisoformat(str(ts)).isoformat() + "T15:59:00"
    except ValueError:
        return str(ts)
