from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pytz

from ..models import Alert, Bar, CancelIntent, FeatureSnapshot, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot

NY = pytz.timezone("America/New_York")
UTC = pytz.UTC


class V2BScaleoutStrategy(StrategyPlugin):
    """Intraday v2b opening-range breakout scaleout.

    This is the live-orderable version of the v2b family.  The research-only
    long-priority scanner is intentionally not implemented here because it can
    select a later long before an earlier short.  Supported modes are:

    - ``oco_then_reverse``: arm both sides after the OR; first fill owns leg 1,
      then the opposite side may arm after leg 1 exits.
    - ``strict_long_then_short``: arm long only; short can arm only after a
      filled long exits.

    Optional ``entry_mode``:
    - ``oco`` (default): arm boundary stops when the OR finalizes.
    - ``first_break_opposite`` (FBO): ignore the first OR break, then arm a
      single stop in the opposite direction (no classic reverse leg).
    """

    strategy_type = "v2b_scaleout"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "mode": "oco_then_reverse",
            # oco | first_break_opposite (failed-breakout / FBO)
            "entry_mode": "oco",
            "tick_size": 0.25,
            "entry_qty": 2,
            "tp1_qty": None,        # default: 1 (legacy)
            "tp2_qty": None,        # default: 1 (legacy); runner = entry_qty - tp1_qty - tp2_qty
            "rth_start": "09:30",
            "or_end": "09:45",
            # Bars required inside [rth_start, or_end) before OR finalizes / arms.
            # Default 15 = classic 15-minute OR; set 120 for a 2-hour OR window.
            "or_bars": 15,
            "eod_cutoff": "15:59",
            # How many OCO campaigns (initial arm → optional reverse) per session.
            # Default 1 = classic v2b. Set 2 to allow one re-entry on the same OR.
            "max_campaigns": 1,
            "use_regime_filter": True,
            "require_regime_dates": False,
            "regime_dates": [],
            "record_levels": False,
            "dynamic_sizing_events": {},
            "prior_opposite_only": False,
            "prior_opposite_entry_qty": None,
            "prior_opposite_tp1_qty": None,
            "prior_opposite_tp2_qty": None,
            # Same-session ST+PMC same-side gate (continuation / prior-aligned).
            "prior_aligned_only": False,
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
            # Optional precomputed OR levels (e.g. overnight Asia range). When the
            # session date is present, seed or_high/or_low and finalize on the first
            # in-session bar instead of accumulating [rth_start, or_end).
            # session_date -> {"high": float, "low": float}
            "session_or_ranges": {},
            # Calendar blackout (NY month 1–12). Same knob as monday_or_breakout.
            "skip_entry_months": [],
            # Shadow rolling WR/PF sit-out (unfiltered campaign nets). See
            # live/asia_range_shadow.py — taken-only windows freeze after PF dips.
            "shadow_roll_window": 0,
            "shadow_min_wr": 0.40,
            "shadow_min_pf": 1.0,
            # Seed nets and/or path to JSON book updated by the live demo EOD sim.
            "shadow_campaigns_seed": [],
            "shadow_campaigns_path": "",
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

        if role in {"wide_stop", "runner_stop", "tp2", "runner_tp", "eod_close", "invalidate_no_opposite_st"}:
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

        # Precomputed OR (Asia / overnight): seed + finalize before live OR accumulate.
        if not state.get("or_finalized"):
            preset = self._session_or_range(session)
            if preset is not None:
                hi, lo = preset
                state["or_high"] = hi
                state["or_low"] = lo
                state["or_count"] = max(1, int(self.config.get("or_bars") or 15))
                state["or_finalized"] = True
                state["regime_ok"] = self._session_tradeable(session, state)
                if state["regime_ok"] and self._is_fbo():
                    state["phase"] = "wait_first_break"
                    state["first_break_side"] = ""
                    state["opposite_armed"] = False
                else:
                    state["phase"] = "armed" if state["regime_ok"] else "regime_skip"
                causal_features.extend(self._opening_range_features(bar.ts, state))
                if state["regime_ok"] and not self._is_fbo():
                    directions = self._directions_for_session(session)
                    causal_features.extend(self._entry_gate_features(bar.ts, state, directions, price=bar.close))
                    orders.extend(self._arm_initial_entries(bar.ts, state, directions, price=bar.close))
                    if directions and not bool(self.config.get("suppress_alerts")):
                        alerts.append(Alert.create(self.instance.strategy_id, "info", "v2b opening range armed"))
                elif state["regime_ok"] and self._is_fbo() and not bool(self.config.get("suppress_alerts")):
                    alerts.append(Alert.create(self.instance.strategy_id, "info", "v2b FBO waiting first break"))
                if bool(self.config.get("record_levels")):
                    levels.extend(self._levels(bar.ts, state))
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], levels, alerts, causal_features)

        if t < self._time("or_end"):
            state["or_count"] = int(state.get("or_count", 0)) + 1
            state["or_high"] = bar.high if state.get("or_high") is None else max(float(state["or_high"]), bar.high)
            state["or_low"] = bar.low if state.get("or_low") is None else min(float(state["or_low"]), bar.low)
            if bool(self.config.get("record_levels")):
                levels.extend(self._levels(bar.ts, state))
            or_bars = max(1, int(self.config.get("or_bars") or 15))
            if state["or_count"] >= or_bars and not state.get("or_finalized"):
                state["or_finalized"] = True
                state["regime_ok"] = self._session_tradeable(session, state)
                if state["regime_ok"] and self._is_fbo():
                    state["phase"] = "wait_first_break"
                    state["first_break_side"] = ""
                    state["opposite_armed"] = False
                else:
                    state["phase"] = "armed" if state["regime_ok"] else "regime_skip"
                causal_features.extend(self._opening_range_features(bar.ts, state))
                if state["regime_ok"] and not self._is_fbo():
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
                elif state["regime_ok"] and self._is_fbo() and not bool(self.config.get("suppress_alerts")):
                    alerts.append(Alert.create(self.instance.strategy_id, "info", "v2b FBO waiting first break"))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts, causal_features)

        if bool(self.config.get("record_levels")):
            levels.extend(self._levels(bar.ts, state))

        # Late finalize: OR window ended before or_bars (sparse tape) — arm once
        # when we have a usable range.
        if (
            not state.get("or_finalized")
            and state.get("or_high") is not None
            and state.get("or_low") is not None
            and float(state["or_high"]) > float(state["or_low"])
        ):
            state["or_finalized"] = True
            state["regime_ok"] = self._session_tradeable(session, state)
            if state["regime_ok"] and self._is_fbo():
                state["phase"] = "wait_first_break"
                state["first_break_side"] = ""
                state["opposite_armed"] = False
            else:
                state["phase"] = "armed" if state["regime_ok"] else "regime_skip"
            causal_features.extend(self._opening_range_features(bar.ts, state))

        if state.get("regime_ok") and not state.get("done") and not state.get("current_leg_open") and int(state.get("legs_done", 0)) == 0:
            if not self._has_open_entry_order(context):
                if self._is_fbo():
                    causal_features.extend(self._opening_range_features(bar.ts, state))
                    orders.extend(self._first_break_opposite_orders(bar, state))
                # Skip catch-up arms when open-filter is OR-end-only.
                elif bool(self.config.get("use_open_alignment_filter")) and bool(
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
        state.setdefault("campaigns_done", 0)
        state.setdefault("current_leg_open", False)
        state.setdefault("active_trade_id", "")
        state.setdefault("active_direction", "")
        state.setdefault("entry_armed", [])
        state.setdefault("trades", {})
        return state

    def _fresh_session_state(self, session: str) -> Dict[str, Any]:
        prev = dict(self.state or {})
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
            "campaigns_done": 0,
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
            "first_break_side": "",
            "opposite_armed": False,
            "trades": {},
            # Persist shadow book across calendar sessions.
            "shadow_campaigns": list(prev.get("shadow_campaigns") or []),
        }

    def _entry_mode(self) -> str:
        return str(self.config.get("entry_mode") or "oco").strip().lower()

    def _is_fbo(self) -> bool:
        return self._entry_mode() == "first_break_opposite"

    def _first_break_opposite_orders(self, bar: Bar, state: Dict[str, Any]) -> List[OrderIntent]:
        """Ignore first OR break, then arm a stop in the opposite direction."""
        if not self._before_entry_cutoff(bar.ts):
            return []
        range_high = _to_float(state.get("or_high"))
        range_low = _to_float(state.get("or_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            return []
        session = str(state.get("session_date") or _parse_dt(bar.ts).date().isoformat())
        if not self._arm_time_ok(session, bar.ts):
            return []
        break_side = str(state.get("first_break_side") or "")
        if not break_side:
            long_hit = float(bar.high) >= float(range_high)
            short_hit = float(bar.low) <= float(range_low)
            if long_hit and short_hit:
                return []  # ambiguous — keep waiting
            if not long_hit and not short_hit:
                return []
            break_side = "Long" if long_hit else "Short"
            state["first_break_side"] = break_side
            state["phase"] = "arm_opposite"
            state["opposite_armed"] = False
        if bool(state.get("opposite_armed")):
            return []
        opposite = "Short" if break_side == "Long" else "Long"
        allowed = set(self._directions_for_session(session))
        if opposite not in allowed:
            return []
        state["opposite_armed"] = True
        return self._entry_orders(bar.ts, state, [opposite], price=float(bar.close))

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

    def _skip_entry_months(self) -> set:
        raw = self.config.get("skip_entry_months") or []
        out = set()
        if isinstance(raw, (list, tuple)):
            for m in raw:
                try:
                    mi = int(m)
                except (TypeError, ValueError):
                    continue
                if 1 <= mi <= 12:
                    out.add(mi)
        return out

    def _month_entry_blocked(self, session: str) -> bool:
        months = self._skip_entry_months()
        if not months:
            return False
        try:
            month = int(str(session)[5:7])
        except (TypeError, ValueError):
            return False
        return month in months

    def _shadow_nets(self, state: Dict[str, Any]) -> List[float]:
        nets = list(state.get("shadow_campaigns") or [])
        if nets:
            return [float(x) for x in nets]
        path = str(self.config.get("shadow_campaigns_path") or "").strip()
        if path:
            try:
                from ..asia_range_shadow import load_shadow_book

                loaded = load_shadow_book(Path(path))
                if loaded:
                    state["shadow_campaigns"] = list(loaded)
                    return loaded
            except Exception:
                pass
        seed = self.config.get("shadow_campaigns_seed") or []
        out: List[float] = []
        for x in seed:
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                continue
        if out:
            state["shadow_campaigns"] = list(out)
        return out

    def _shadow_roll_decision(self, state: Dict[str, Any]) -> Tuple[bool, Dict[str, float]]:
        """Return (blocked, meta) for the shadow rolling WR/PF gate."""
        try:
            window = int(self.config.get("shadow_roll_window") or 0)
        except (TypeError, ValueError):
            window = 0
        if window <= 0:
            return False, {"n": 0.0, "wr": 0.0, "pf": 0.0, "bad_wr": 0.0, "bad_pf": 0.0, "warmup": 0.0}
        try:
            min_wr = float(self.config.get("shadow_min_wr") or 0.40)
        except (TypeError, ValueError):
            min_wr = 0.40
        try:
            min_pf = float(self.config.get("shadow_min_pf") or 1.0)
        except (TypeError, ValueError):
            min_pf = 1.0
        from ..asia_range_shadow import gate_blocks

        blocked, meta = gate_blocks(
            self._shadow_nets(state),
            window=window,
            min_wr=min_wr,
            min_pf=min_pf,
        )
        return bool(blocked), dict(meta)

    def _shadow_roll_blocked(self, state: Dict[str, Any]) -> bool:
        blocked, _meta = self._shadow_roll_decision(state)
        return bool(blocked)

    def session_gate_decision(self, session: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Live-parity row fields: skip/take + reason + shadow WR/PF."""
        st = state if state is not None else dict(self.state or {})
        from ..asia_range_shadow import gate_reason

        month_block = self._month_entry_blocked(session)
        roll_block, meta = self._shadow_roll_decision(st)
        regime_ok = self._regime_ok(session)
        if not regime_ok:
            reason = "regime"
            allowed = False
        elif month_block:
            reason = "month"
            allowed = False
        elif roll_block:
            reason = gate_reason(meta, month_block=False)
            allowed = False
        else:
            reason = "take"
            allowed = True
        return {
            "session_date": session,
            "shadow_50_wr": float(meta.get("wr") or 0.0),
            "shadow_50_pf": float(meta.get("pf") or 0.0)
            if meta.get("pf") != float("inf")
            else 999.0,
            "shadow_n": int(meta.get("n") or 0),
            "decision": "take" if allowed else "skip",
            "reason": reason,
            "warmup": bool(float(meta.get("warmup") or 0.0) >= 1.0),
        }

    def _session_tradeable(self, session: str, state: Dict[str, Any]) -> bool:
        """Regime + calendar blackout + shadow rolling WR/PF gate."""
        return self.session_gate_decision(session, state).get("decision") == "take"

    def _session_or_range(self, session: str) -> Optional[Tuple[float, float]]:
        """Return precomputed (high, low) for session, or None."""
        raw = (self.config.get("session_or_ranges") or {}).get(session)
        if not isinstance(raw, dict):
            return None
        high = _to_float(raw.get("high"))
        low = _to_float(raw.get("low"))
        if high is None or low is None or high <= low:
            return None
        return float(high), float(low)

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
        # FBO is a single opposite-of-failed-break campaign — no reverse leg.
        if self._is_fbo():
            return self._finish_campaign(ts, state, context)
        if int(state.get("legs_done", 0)) >= 2:
            return self._finish_campaign(ts, state, context)
        if context.position_quantity != 0 or self._has_open_entry_order(context):
            return []
        last_direction = str(state.get("last_exit_direction") or "")
        if last_direction not in {"Long", "Short"}:
            return []
        if not self._reverse_allowed(ts, state):
            state["reverse_suppressed"] = True
            return self._finish_campaign(ts, state, context)
        opposite = "Short" if last_direction == "Long" else "Long"
        session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
        allowed = set(self._directions_for_session(session))
        if opposite not in allowed:
            # Directional bias / long-only modes: do not reverse into the banned side.
            return self._finish_campaign(ts, state, context)
        # Prefer last bar close so PMC / open filters can evaluate on reverse arm.
        ref_price = _to_float(state.get("last_bar_close"))
        return self._entry_orders(ts, state, [opposite], price=ref_price)

    def _finish_campaign(self, ts: str, state: Dict[str, Any], context: StrategyContext) -> List[OrderIntent]:
        """End the current OCO campaign; optionally re-arm a fresh OCO on the same OR."""
        state["campaigns_done"] = int(state.get("campaigns_done", 0)) + 1
        max_campaigns = max(1, int(self.config.get("max_campaigns") or 1))
        if state["campaigns_done"] >= max_campaigns:
            state["done"] = True
            state["phase"] = "done"
            return []
        # Re-entry: reset leg state and arm a new campaign on the existing OR.
        state["legs_done"] = 0
        state["entry_armed"] = []
        state["last_exit_ts"] = ""
        state["last_exit_direction"] = ""
        state["opposite_confirmed"] = False
        state["invalidated"] = False
        state["reverse_suppressed"] = False
        state["first_break_side"] = ""
        state["opposite_armed"] = False
        session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
        ref_price = _to_float(state.get("last_bar_close"))
        if self._is_fbo():
            state["phase"] = "wait_first_break"
            return []
        state["phase"] = "reentry_armed"
        directions = self._directions_for_session(session)
        return self._arm_initial_entries(ts, state, directions, price=ref_price)

    def _reverse_allowed(self, ts: str, state: Dict[str, Any]) -> bool:
        """OR-profile asymmetric reverse gate (`reverse_only_when` config).

        When unset/empty, reverse is unconditional (legacy). When set, all
        configured conditions must hold at reverse-arm time:
          - max_first_leg_exit_time: NY clock of first-leg exit (e.g. \"12:00\")
          - or_width_q_allow: list of allowed OR-width quartiles; session
            quartile supplied via config ``session_or_width_q`` {date: \"q1\"..}
        """
        gate = self.config.get("reverse_only_when") or {}
        if not gate:
            return True
        exit_ts = str(state.get("last_exit_ts") or ts)
        max_t = str(gate.get("max_first_leg_exit_time") or "").strip()
        if max_t:
            try:
                hh, mm = max_t.split(":")
                if _parse_dt(exit_ts).time() >= time(int(hh), int(mm)):
                    return False
            except (ValueError, TypeError):
                pass
        allow_q = gate.get("or_width_q_allow")
        if allow_q:
            session = str(state.get("session_date") or _parse_dt(ts).date().isoformat())
            qmap = self.config.get("session_or_width_q") or {}
            q = str(qmap.get(session) or "")
            if q not in {str(x) for x in allow_q}:
                return False
        return True

    def _entry_orders(
        self,
        ts: str,
        state: Dict[str, Any],
        directions: Sequence[str],
        *,
        price: Optional[float] = None,
    ) -> List[OrderIntent]:
        if not self._before_entry_cutoff(ts):
            return []
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
            prior_opp = self._prior_opposite_event_for_entry(ts, direction)
            prior_aligned = self._prior_aligned_event_for_entry(ts, direction)
            prior_event = prior_opp or prior_aligned
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
                        "prior_aligned_only": self.config.get("prior_aligned_only"),
                        "has_prior_opposite_event": prior_opp is not None,
                        "has_prior_aligned_event": prior_aligned is not None,
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
            expires_after_ts=self._entry_expiry(ts),
        )

    def _before_entry_cutoff(self, ts: str) -> bool:
        """False once ``entry_cutoff_time`` (NY) has passed — no new arming."""
        cutoff = str(self.config.get("entry_cutoff_time") or "").strip()
        if not cutoff:
            return True
        try:
            hh, mm = cutoff.split(":")
            return _parse_dt(str(ts)).time() < time(int(hh), int(mm))
        except (ValueError, TypeError):
            return True

    def _entry_expiry(self, ts: str) -> str:
        """Entry stops expire at ``entry_cutoff_time`` (NY) when configured.

        OR-profile time gate: breaks triggering after ~10:30 hit 1R at only
        0.29-0.44 vs 0.54-0.59 pooled (stable 16 years, all four profiled
        markets), so unarmed resting entry stops can be expired early via
        ``entry_cutoff_time`` (e.g. ``"10:30"``). Exit orders keep the
        session-end expiry. Default (unset) preserves legacy behaviour.
        """
        cutoff = str(self.config.get("entry_cutoff_time") or "").strip()
        if not cutoff:
            return _session_expiry(ts)
        try:
            hh, mm = cutoff.split(":")
            cutoff_t = time(int(hh), int(mm))
            session_day = _parse_dt(str(ts)).date()
        except (ValueError, TypeError):
            return _session_expiry(ts)
        return NY.localize(datetime.combine(session_day, cutoff_t)).isoformat()

    def _sizing_for_entry(self, ts: str, direction: str) -> Optional[Dict[str, int]]:
        base = {
            "entry_qty": int(self.config["entry_qty"]),
            "tp1_qty": 1 if self.config.get("tp1_qty") is None else int(self.config.get("tp1_qty")),
            "tp2_qty": 1 if self.config.get("tp2_qty") is None else int(self.config.get("tp2_qty")),
        }
        if not self.config.get("dynamic_sizing_events"):
            return base
        has_prior_opposite = self._prior_opposite_event_for_entry(ts, direction) is not None
        has_prior_aligned = self._prior_aligned_event_for_entry(ts, direction) is not None
        if bool(self.config.get("prior_opposite_only")) and not has_prior_opposite:
            return None
        if bool(self.config.get("prior_aligned_only")) and not has_prior_aligned:
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

    def _prior_event_for_entry(self, ts: str, direction: str, *, same_side: bool) -> Optional[Dict[str, Any]]:
        dt = _parse_dt(ts)
        session = dt.date().isoformat()
        if same_side:
            wanted = "long" if direction == "Long" else "short"
        else:
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

    def _prior_opposite_event_for_entry(self, ts: str, direction: str) -> Optional[Dict[str, Any]]:
        return self._prior_event_for_entry(ts, direction, same_side=False)

    def _prior_aligned_event_for_entry(self, ts: str, direction: str) -> Optional[Dict[str, Any]]:
        return self._prior_event_for_entry(ts, direction, same_side=True)

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
        # Optional runner take-profit (default unset = ride to EOD / runner stop).
        # OR-profile runner ladder: set runner_target_r_mult=3.0 so the runner
        # block banks at 3R when the state's P(2R|1R)·P(3R|2R) chain is strong.
        #
        # targeted_runner_qty (optional): apply runner_tp to only N of the
        # runner block; the remainder stay EOD/BE. Used for prior-opposed
        # S_1_1_3 + 1×10R (3 EOD runners + 1 targeted @ 10R).
        runner_tp = _to_float(params.get("runner_tp"))
        if runner_qty > 0 and runner_tp is not None:
            targeted_raw = trade.get("targeted_runner_qty", self.config.get("targeted_runner_qty"))
            if targeted_raw is None or str(targeted_raw).strip() == "":
                tp_qty = runner_qty  # legacy: whole runner block
            else:
                tp_qty = max(0, min(runner_qty, int(targeted_raw)))
            if tp_qty > 0:
                out.append(
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=trade_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side=exit_side,
                        order_type="limit",
                        quantity=tp_qty,
                        limit_price=runner_tp,
                        reason="v2b_runner_tp",
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role="runner_tp",
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
        runner_mult = _to_float(self.config.get("runner_target_r_mult"))
        if direction == "Long":
            out = {
                "entry": range_high + tick,
                "init_sl": range_low,
                "tp1": range_high + range_value,
                "tp2": range_high + 2.0 * range_value,
                "runner_sl": range_high + tick,
            }
            if runner_mult is not None and runner_mult > 0:
                out["runner_tp"] = range_high + runner_mult * range_value
            return out
        out = {
            "entry": range_low - tick,
            "init_sl": range_high,
            "tp1": range_low - range_value,
            "tp2": range_low - 2.0 * range_value,
            "runner_sl": range_low - tick,
        }
        if runner_mult is not None and runner_mult > 0:
            out["runner_tp"] = range_low - runner_mult * range_value
        return out

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
    """Parse bar/event timestamps into America/New_York for session clocks.

    Research replays stamp bars with NY offsets (``-04:00``/``-05:00``). Live
    OANDA bars are true UTC (``Z``). Session gates (``rth_start``, ``or_end``,
    ``eod_cutoff``) are NY wall times, so always convert before comparing.
    Naive timestamps are treated as already-NY wall clock.
    """
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


def _session_expiry(ts: str) -> str:
    """NY cash-session order expiry at 15:59 America/New_York.

    Emits an offset ISO stamp (e.g. ``...T15:59:00-04:00``) so PaperBroker
    expiry compares correctly against live UTC ``Z`` bars once ``_ts_after``
    is timezone-aware. Date-only and bar ISO inputs both resolve via the
    session calendar day in NY.
    """
    raw = str(ts).strip()
    try:
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            session_day = date.fromisoformat(raw[:10])
        else:
            session_day = _parse_dt(raw).date()
    except ValueError:
        return raw
    return NY.localize(datetime.combine(session_day, time(15, 59))).isoformat()
