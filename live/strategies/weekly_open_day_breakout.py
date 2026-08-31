"""Weekly open-day breakout with candle-risk limit entry (4h decisions).

Matches the weekly level charts (open-day H/L + mid ±4×ATR(14) guides):

1. Build Monday session open-day H/L for the ISO week; snap ATR(14) at the
   last Monday session bar.
2. After open-day completes, wait for a 4h candle that **closes** outside the
   open-day range (breakout candle).
3. Arm a **limit** at the breakout candle close. Stop mode is config-driven
   (candle extreme or far side of open-day range).
4. Scale is config-driven. Default **2/1/1** (entry 4): 2 @ candle-R, 1 @
   open-day-R, runner to Friday NY flatten. Variant **2/1/1/1** (entry 5):
   same first two, 1 @ 4×R_init, runner (1) to **20×R_init** with BE stop
   and no Friday flatten (may hold across weeks). OD-frac scale
   (``exit_mode=scale_od_frac``): TPs / runner as multiples of open-day range
   (e.g. 0.5× / 1× / EOW or 3×).
5. Max **2** campaigns per week (while flat). After a campaign ends, wait for
   a 4h close back inside the open-day range before hunting the next breakout.
6. Optional: skip weeks whose Monday is a US federal holiday or has fewer
   than ``min_open_day_bars`` 4h session bars (thin / non-trading Monday).
7. Optional ``allow_weeks_of_month`` entry gate (calendar week-of-month on the
   arming session date; same formula as HA mills).
8. Friday flatten fires on the completed Friday **13:00 NY** 4h bar (after the
   09:00–13:00 session bar) so 1m market closes can fill before the Friday
   cash close — not on the 17:00-stamped bar that leaves only Sunday 1m.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time as dt_time, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

import pytz

from ..models import Alert, Bar, CancelIntent, FeatureSnapshot, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot

NY = pytz.timezone("America/New_York")
ATR_LEN = 14
# Completion-stamped threshold: fire after Friday 09:00–13:00 bar completes.
FRIDAY_FLATTEN_COMPLETION_NY = dt_time(13, 0)


@lru_cache(maxsize=1)
def _us_federal_holidays() -> Set[date]:
    """Causal US federal holiday calendar (Monday holiday / observed)."""
    try:
        import pandas as pd
        import pandas.tseries.holiday as hol

        cal = hol.USFederalHolidayCalendar()
        days = cal.holidays(start="2010-01-01", end="2030-12-31")
        return {pd.Timestamp(d).date() for d in days}
    except Exception:
        return set()


def _parse_dt(ts: str) -> datetime:
    raw = str(ts).replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(NY)


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return x


def _week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    year = int(iso[0]) if not hasattr(iso, "year") else int(iso.year)
    week = int(iso[1]) if not hasattr(iso, "week") else int(iso.week)
    return "%04d-W%02d" % (year, week)


def _ny_date_str(dt: datetime) -> str:
    return dt.date().isoformat()


def _week_of_month(dt: datetime) -> int:
    """Calendar week-of-month; same formula as HA mills / yearly_orb."""
    return ((int(dt.day) - 1) // 7) + 1


def _parse_hhmm(raw: Any, default: dt_time) -> dt_time:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        hh, mm = text.split(":")[:2]
        return dt_time(int(hh), int(mm))
    except Exception:
        return default


def _friday_flatten_due(dt: datetime, *, completion_clock: dt_time = FRIDAY_FLATTEN_COMPLETION_NY) -> bool:
    """True once Friday's midday 4h bar has completed (default 13:00 NY).

    ``dt`` is the completion-stamped 4h bar time (left edge + 4h in the 1m
    driver). Firing at 13:00 leaves Friday afternoon 1m prints available for
    the market flatten; firing at 17:00 leaves only Sunday reopen fills.
    """
    if dt.weekday() != 4:
        return False
    clock = dt.timetz().replace(tzinfo=None)
    return clock >= completion_clock


def _session_dt(completion_dt: datetime) -> datetime:
    """Left-edge / session time for a completion-stamped 4h bar (+4h in the 1m driver)."""
    return completion_dt - timedelta(hours=4)


class WeeklyOpenDayBreakoutStrategy(StrategyPlugin):
    strategy_type = "weekly_open_day_breakout"
    version = "v6"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.00001,
            "entry_qty": 4,
            "tp1_qty": 2,
            "tp2_qty": 1,
            "tp3_qty": 0,
            "runner_qty": 1,
            "tp3_r_mult": None,  # e.g. 4.0 × R_init
            "runner_r_mult": None,  # e.g. 20.0 × R_init; None → Friday flatten runner
            # scale_od_frac: TP / runner distances as multiples of open-day range.
            "tp1_od_mult": 0.5,
            "tp2_od_mult": 1.0,
            "tp3_od_mult": None,
            "runner_od_mult": None,  # e.g. 3.0; None → Friday flatten when friday_flatten
            "stop_mode": "od_far",  # candle | od_far
            "friday_flatten": True,
            # Completion-stamped HH:MM NY — default 13:00 so 1m can fill Fri PM.
            "friday_flatten_completion_ny": "13:00",
            "hold_across_weeks": False,
            "skip_candle_gt_od": False,
            "skip_candle_gt_atr_room": False,
            "skip_us_holiday_monday": False,
            "min_open_day_bars": 0,  # e.g. 5 → skip thin / non-trading Mondays
            "atr_len": ATR_LEN,
            "atr_mult": 4.0,
            "timeframe": "4h",
            "max_trades_per_week": 2,
            # scale | oco_od_r | scale_od_frac
            "exit_mode": "scale",
            "record_levels": False,
            "suppress_alerts": True,
            "be_after": "tp2",  # tp1 | tp2 | tp3 | none
            # Optional causal regime gates (checked at arm time).
            "require_bull_200dma": False,
            "require_high_vol": False,
            "ma_len": 200,
            "vol_ret_days": 20,
            "vol_median_lookback": 252,
            # Optional calendar week-of-month allowlist (1..5); empty → all.
            "allow_weeks_of_month": [],
            # Time-based pyramid: add ``add_qty`` every ``add_every_hours`` while in trade.
            # Added size shares the same SL / TP prices; extras ride runner / EOW.
            "add_every_hours": 0.0,
            "add_qty": 1,
            "max_adds": 0,  # 0 = unlimited until flat / Friday
            # Entry: breakout_close (legacy) | swing_close (limit at first causal swing).
            "entry_mode": "breakout_close",
            # Breakout detect: gated (week+regime before recording) | structural (first OD close).
            "breakout_mode": "gated",
            # Reject continuation "fractals" (e.g. green bar with slightly lower wick).
            "swing_require_pullback": True,
            # Swing vs bull×hivol: True = confirm swing even while regime off (arm deferred);
            # False = only hunt/confirm swing once week+regime are already on.
            # With gated + True, week gate still applies at detect but regime is deferred to arm.
            "swing_before_regime": False,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "4h").lower()
        tf = str(bar.timeframe or "").lower()
        if want in {"4h", "4hour"} and tf not in {"4h", "4hour"}:
            return StrategyActions.empty()
        if not bar.complete:
            return StrategyActions.empty()
        return self._on_4h(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(str(fill.trade_id), state)
        reason = str(fill.reason or "")
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if reason == "entry" and context.position_quantity != 0:
            direction = "long" if fill.side == "buy" else "short"
            entry = float(fill.price)
            trade.update(
                {
                    "status": "open",
                    "direction": direction,
                    "entry_price": entry,
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                    "adds_done": 0,
                    "add_pending": False,
                    "tp1_hit": False,
                    "tp2_hit": False,
                    "tp3_hit": False,
                    "runner_hit": False,
                }
            )
            state["active_trade_id"] = fill.trade_id
            state["in_trade"] = True
            state["entry_pending"] = False
            state["phase"] = "in_trade"
            state["campaigns_done"] = int(state.get("campaigns_done") or 0) + 1
            cancels.extend(
                CancelIntent(self.instance.strategy_id, o.broker_order_id, "entry_filled")
                for o in context.strategy_open_orders
                if (not o.reduce_only) and o.broker_order_id != fill.broker_order_id
            )
            orders.extend(self._exit_orders(fill, trade, state))
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        if reason in {"time_add", "add"} or str(getattr(fill, "bracket_role", "") or "") == "add":
            trade["add_pending"] = False
            trade["adds_done"] = int(trade.get("adds_done") or 0) + 1
            trade["filled_qty"] = int(trade.get("filled_qty") or 0) + int(fill.quantity)
            # Same SL price; resize stop to cover full remaining position. TP prices unchanged.
            remaining = abs(int(context.position_quantity))
            if remaining > 0:
                cancels.extend(
                    CancelIntent(self.instance.strategy_id, o.broker_order_id, "add_resize_stop")
                    for o in context.strategy_open_orders
                    if o.reduce_only
                    and str(o.bracket_role or "") == "stop"
                    and o.trade_id == fill.trade_id
                )
                stop_px = _to_float(trade.get("stop"))
                direction = str(trade.get("direction") or "")
                if stop_px is not None and direction:
                    exit_side = "sell" if direction == "long" else "buy"
                    orders.append(
                        OrderIntent.create(
                            strategy_id=self.instance.strategy_id,
                            trade_id=fill.trade_id,
                            instrument=self.instance.instrument,
                            account_mode=self.instance.account_mode,
                            side=exit_side,
                            order_type="stop",
                            quantity=remaining,
                            stop_price=float(stop_px),
                            reason="od_range_stop" if str(self.config.get("stop_mode") or "od_far") != "candle" else "candle_stop",
                            bracket_role="stop",
                            requires_verification=False,
                            reduce_only=True,
                            live_after_ts=fill.ts,
                        )
                    )
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        if reason == "tp1":
            trade["tp1_hit"] = True
            flat = context.position_quantity == 0
            if flat:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = reason
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels.extend(self._cancel_reduce(context, fill.trade_id))
                state["need_inside_before_breakout"] = True
                state["phase"] = "wait_inside"
                state["last_exit_reason"] = reason
                self._commit(state)
                return StrategyActions(orders, cancels, [], [], [])
            self._commit(state)
            if str(self.config.get("be_after") or "").lower() == "tp1":
                return self._move_stop_to_be(fill, context, trade, state)
            return StrategyActions.empty()

        if reason == "tp2":
            trade["tp2_hit"] = True
            flat = context.position_quantity == 0
            if flat:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = reason
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels.extend(self._cancel_reduce(context, fill.trade_id))
                state["need_inside_before_breakout"] = True
                state["phase"] = "wait_inside"
                state["last_exit_reason"] = reason
                self._commit(state)
                return StrategyActions(orders, cancels, [], [], [])
            self._commit(state)
            if str(self.config.get("be_after") or "tp2").lower() == "tp2":
                return self._move_stop_to_be(fill, context, trade, state)
            return StrategyActions.empty()

        if reason == "tp3":
            trade["tp3_hit"] = True
            self._commit(state)
            if str(self.config.get("be_after") or "").lower() == "tp3":
                return self._move_stop_to_be(fill, context, trade, state)
            return StrategyActions.empty()

        if reason == "runner":
            trade["runner_hit"] = True
            flat = context.position_quantity == 0
            if flat:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = reason
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels.extend(self._cancel_reduce(context, fill.trade_id))
                state["need_inside_before_breakout"] = True
                state["phase"] = "wait_inside"
                state["last_exit_reason"] = reason
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        if reason in {"stop", "week_close", "friday_flatten"}:
            if reason == "friday_flatten":
                trade["runner_hit"] = True
            flat = context.position_quantity == 0
            if flat:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = reason
                state["in_trade"] = False
                state["active_trade_id"] = ""
                cancels.extend(self._cancel_reduce(context, fill.trade_id))
                state["need_inside_before_breakout"] = True
                state["phase"] = "wait_inside"
                state["last_exit_reason"] = reason
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        self._commit(state)
        return StrategyActions.empty()

    # ------------------------------------------------------------------

    def _on_4h(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        wkey = _week_key(dt)
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        if state.get("week_key") != wkey:
            hold = bool(self.config.get("hold_across_weeks"))
            has_pos = context.position_quantity != 0 or bool(state.get("in_trade"))
            if hold and has_pos:
                # Keep runner / open position; only cancel naked entry limits.
                cancels.extend(
                    CancelIntent(self.instance.strategy_id, o.broker_order_id, "week_roll_entry")
                    for o in context.strategy_open_orders
                    if not o.reduce_only
                )
                state["entry_pending"] = False
                state["armed_trade_id"] = ""
                state = self._fresh_week_keep_trade(wkey, prior=state)
            elif context.position_quantity != 0 or state.get("in_trade") or state.get("entry_pending"):
                cancels.extend(self._cancel_all(context))
                if context.position_quantity != 0:
                    orders.append(self._close_all(context, bar.ts, "week_close"))
                self._commit(state)
                if context.position_quantity != 0:
                    return StrategyActions(orders, cancels, [], [], [])
                state = self._fresh_week(wkey, prior=state)
            else:
                state = self._fresh_week(wkey, prior=state)

        self._update_atr(state, bar)
        session = _session_dt(dt)
        day = _ny_date_str(session)
        self._update_daily_closes(state, session, bar)
        features: List[FeatureSnapshot] = []

        flatten_clock = _parse_hhmm(
            self.config.get("friday_flatten_completion_ny"), FRIDAY_FLATTEN_COMPLETION_NY
        )
        if bool(self.config.get("friday_flatten", True)) and _friday_flatten_due(
            dt, completion_clock=flatten_clock
        ):
            if context.position_quantity != 0 or state.get("entry_pending") or state.get("in_trade"):
                cancels.extend(self._cancel_all(context))
                if context.position_quantity != 0:
                    orders.append(self._close_all(context, bar.ts, "friday_flatten"))
                state["entry_pending"] = False
                state["phase"] = "friday_flat"
                state["week_done"] = True
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts)
            state["week_done"] = True
            self._commit(state)
            return StrategyActions.empty()

        if state.get("week_done"):
            self._commit(state)
            return StrategyActions.empty()

        # --- Open-day build (Monday session only) ---
        if not state.get("open_day_done"):
            if session.weekday() != 0:
                if state.get("open_day"):
                    self._finalize_open_day(state)
                    if state.get("levels_ready"):
                        features.append(
                            feature_snapshot(
                                self.instance,
                                "wod_open_day_levels",
                                bar.ts,
                                source="monday_session.4h",
                                value_ref="%.6f/%.6f" % (float(state["od_high"]), float(state["od_low"])),
                                metadata={
                                    "open_day": state.get("open_day"),
                                    "od_range": state.get("od_range"),
                                    "atr14": state.get("atr14"),
                                    "open_day_bars": state.get("open_day_bars"),
                                },
                            )
                        )
                elif 1 <= session.weekday() <= 5 and not state.get("open_day_skip"):
                    # Tue–Fri with no Monday session bars → non-trading Monday week.
                    # Do not trip on Sunday (weekday 6) bars that open the ISO week.
                    state["open_day_done"] = True
                    state["levels_ready"] = False
                    state["week_done"] = True
                    state["phase"] = "no_monday_session"
                    state["open_day_skip"] = "no_monday_bars"
                self._commit(state)
                if not state.get("levels_ready"):
                    return StrategyActions(orders, cancels, [], levels, alerts, features)
            elif not state.get("open_day"):
                state["open_day"] = day
                state["od_high"] = float(bar.high)
                state["od_low"] = float(bar.low)
                state["open_day_bars"] = 1
                state["phase"] = "building_open_day"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            else:
                state["od_high"] = max(float(state["od_high"]), float(bar.high))
                state["od_low"] = min(float(state["od_low"]), float(bar.low))
                state["open_day_bars"] = int(state.get("open_day_bars") or 0) + 1
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)

        if bool(self.config.get("record_levels")) and state.get("levels_ready"):
            levels.extend(self._level_updates(bar.ts, state))

        if state.get("in_trade") or context.position_quantity != 0:
            add_orders, add_cancels = self._maybe_time_add(bar, context, state, dt)
            orders.extend(add_orders)
            cancels.extend(add_cancels)
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("entry_pending"):
            od_hi = float(state["od_high"])
            od_lo = float(state["od_low"])
            if od_lo <= float(bar.close) <= od_hi:
                cancels.extend(
                    CancelIntent(self.instance.strategy_id, o.broker_order_id, "back_inside_cancel")
                    for o in context.strategy_open_orders
                    if not o.reduce_only
                )
                state["entry_pending"] = False
                state["need_inside_before_breakout"] = False
                state["phase"] = "wait_breakout"
                state["armed_trade_id"] = ""
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if not state.get("levels_ready"):
            self._commit(state)
            return StrategyActions.empty()

        max_trades = int(self.config.get("max_trades_per_week") or 0)
        if max_trades > 0 and int(state.get("campaigns_done") or 0) >= max_trades:
            state["phase"] = "week_trade_cap"
            self._commit(state)
            return StrategyActions.empty()

        od_hi = float(state["od_high"])
        od_lo = float(state["od_low"])
        inside = od_lo <= float(bar.close) <= od_hi

        if state.get("need_inside_before_breakout"):
            if inside:
                state["need_inside_before_breakout"] = False
                state["phase"] = "wait_breakout"
                state.pop("pending_breakout", None)
                state.pop("post_bo_bars", None)
                state.pop("pending_swing", None)
                state.pop("swing_hunt_active", None)
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        entry_mode = str(self.config.get("entry_mode") or "breakout_close").lower()
        breakout_mode = str(self.config.get("breakout_mode") or "gated").lower()

        # Causal swing entry path.
        if entry_mode == "swing_close" and (
            str(state.get("phase") or "") in {"wait_swing", "wait_swing_gate"}
            or state.get("pending_breakout")
            or state.get("pending_swing")
        ):
            return self._on_wait_swing(
                bar, context, session, day, state, orders, cancels, levels, alerts, features
            )

        direction = None
        if float(bar.close) > od_hi:
            direction = "long"
        elif float(bar.close) < od_lo:
            direction = "short"
        if direction is None:
            self._commit(state)
            return StrategyActions.empty()

        candle_hi = float(bar.high)
        candle_lo = float(bar.low)
        candle_close = float(bar.close)
        candle_r = candle_hi - candle_lo
        od_r = float(state["od_range"])
        if candle_r <= 0 or od_r <= 0:
            self._commit(state)
            return StrategyActions.empty()

        if bool(self.config.get("skip_candle_gt_od")) and candle_r > od_r:
            self._commit(state)
            return StrategyActions.empty()

        if bool(self.config.get("skip_candle_gt_atr_room")):
            atr4_up = _to_float(state.get("atr4_up"))
            atr4_dn = _to_float(state.get("atr4_dn"))
            if atr4_up is not None and atr4_dn is not None:
                room = (atr4_up - candle_close) if direction == "long" else (candle_close - atr4_dn)
                if room <= 0 or candle_r > room:
                    self._commit(state)
                    return StrategyActions.empty()

        wom = _week_of_month(session)
        week_ok = self._week_of_month_ok(session)
        regime_ok = self._regime_ok(state)
        swing_before_regime = bool(self.config.get("swing_before_regime", False))
        # Gated + swing_before_regime: week still required at detect; bull×hivol deferred to arm.
        defer_regime_at_detect = (
            entry_mode == "swing_close" and swing_before_regime and breakout_mode != "structural"
        )

        if breakout_mode != "structural":
            features.append(
                feature_snapshot(
                    self.instance,
                    "wod_week_of_month_gate",
                    bar.ts,
                    source="calendar.session_date",
                    value_ref="%s:%s" % (wom, "allowed" if week_ok else "blocked"),
                    metadata={
                        "session_date": day,
                        "week_of_month": wom,
                        "allow_weeks_of_month": list(self._allow_weeks_of_month()),
                        "allowed": week_ok,
                    },
                )
            )
            if not week_ok:
                state["phase"] = "week_of_month_block"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            features.append(
                feature_snapshot(
                    self.instance,
                    "wod_regime_gate",
                    bar.ts,
                    source="daily_closes.ma_vol",
                    value_ref="ok" if regime_ok else "blocked",
                    metadata={
                        "require_bull_200dma": bool(self.config.get("require_bull_200dma")),
                        "require_high_vol": bool(self.config.get("require_high_vol")),
                        "allowed": regime_ok,
                        "deferred_to_arm": defer_regime_at_detect and not regime_ok,
                    },
                )
            )
            if not regime_ok and not defer_regime_at_detect:
                state["phase"] = "regime_block"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)

        features.append(
            feature_snapshot(
                self.instance,
                "wod_breakout_detect",
                bar.ts,
                source="weekly_open_day_breakout.4h_close",
                value_ref="%s:%.6f" % (direction, candle_close),
                metadata={
                    "direction": direction,
                    "od_high": od_hi,
                    "od_low": od_lo,
                    "candle_r": candle_r,
                    "od_r": od_r,
                    "breakout_mode": breakout_mode,
                    "entry_mode": entry_mode,
                    "swing_before_regime": swing_before_regime,
                    "week_of_month": wom,
                },
            )
        )

        if entry_mode == "swing_close":
            state["pending_breakout"] = {
                "direction": direction,
                "candle_hi": candle_hi,
                "candle_lo": candle_lo,
                "candle_close": candle_close,
                "candle_r": candle_r,
                "breakout_ts": bar.ts,
                "breakout_mode": breakout_mode,
                "swing_before_regime": swing_before_regime,
            }
            state["post_bo_bars"] = [
                {
                    "ts": bar.ts,
                    "open": float(bar.open),
                    "high": candle_hi,
                    "low": candle_lo,
                    "close": candle_close,
                }
            ]
            state.pop("pending_swing", None)
            # After-regime hunt: freeze bar clock until week+regime clear, then restart.
            state["swing_hunt_active"] = bool(swing_before_regime or (week_ok and regime_ok))
            state["phase"] = "wait_swing"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        entry = self._arm_limit(bar, direction, candle_hi, candle_lo, candle_close, candle_r, state)
        if entry is not None:
            orders.append(entry)
            state["entry_pending"] = True
            state["phase"] = "limit_armed"
            features.append(
                feature_snapshot(
                    self.instance,
                    "wod_breakout_arm",
                    bar.ts,
                    source="weekly_open_day_breakout.4h_close",
                    value_ref="%s:%.6f" % (direction, candle_close),
                    metadata={
                        "direction": direction,
                        "od_high": od_hi,
                        "od_low": od_lo,
                        "candle_r": candle_r,
                        "od_r": od_r,
                        "week_of_month": wom,
                    },
                )
            )
            if not bool(self.config.get("suppress_alerts")):
                alerts.append(
                    Alert.create(
                        self.instance.strategy_id,
                        "info",
                        "weekly_open_day_breakout arm %s close=%.6f R=%.6f" % (direction, candle_close, candle_r),
                    )
                )
        self._commit(state)
        return StrategyActions(orders, cancels, [], levels, alerts, features)

    # ------------------------------------------------------------------



    @staticmethod
    def _is_pullback_swing_bar(direction: str, open_: float, high: float, low: float, close: float) -> bool:
        """True if candle looks like a pullback trough/peak, not trend continuation.

        Long swing-low: bearish body OR close in lower half of range.
        Short swing-high: bullish body OR close in upper half of range.
        """
        span = float(high) - float(low)
        mid = 0.5 * (float(high) + float(low))
        if direction == "long":
            if float(close) < float(open_):
                return True
            if span > 0 and float(close) <= mid:
                return True
            return False
        if direction == "short":
            if float(close) > float(open_):
                return True
            if span > 0 and float(close) >= mid:
                return True
            return False
        return False

    def _on_wait_swing(
        self,
        bar: Bar,
        context: StrategyContext,
        session: datetime,
        day: str,
        state: Dict[str, Any],
        orders: List[OrderIntent],
        cancels: List[CancelIntent],
        levels: List[LevelUpdate],
        alerts: List[Alert],
        features: List[FeatureSnapshot],
    ) -> StrategyActions:
        """After breakout: confirm first 1-bar fractal swing, arm limit at swing close."""
        pending = dict(state.get("pending_breakout") or {})
        pending_swing = dict(state.get("pending_swing") or {})
        direction = str((pending_swing.get("direction") or pending.get("direction") or ""))
        swing_before_regime = bool(
            pending.get("swing_before_regime")
            if "swing_before_regime" in pending
            else self.config.get("swing_before_regime", False)
        )

        # If swing already confirmed but gates were blocked, retry arm when gates clear.
        if pending_swing and pending:
            wom = _week_of_month(session)
            week_ok = self._week_of_month_ok(session)
            regime_ok = self._regime_ok(state)
            features.append(
                feature_snapshot(
                    self.instance,
                    "wod_week_of_month_gate",
                    bar.ts,
                    source="calendar.session_date",
                    value_ref="%s:%s" % (wom, "allowed" if week_ok else "blocked"),
                    metadata={
                        "session_date": day,
                        "week_of_month": wom,
                        "allow_weeks_of_month": list(self._allow_weeks_of_month()),
                        "allowed": week_ok,
                    },
                )
            )
            features.append(
                feature_snapshot(
                    self.instance,
                    "wod_regime_gate",
                    bar.ts,
                    source="daily_closes.ma_vol",
                    value_ref="ok" if regime_ok else "blocked",
                    metadata={
                        "require_bull_200dma": bool(self.config.get("require_bull_200dma")),
                        "require_high_vol": bool(self.config.get("require_high_vol")),
                        "allowed": regime_ok,
                    },
                )
            )
            if week_ok and regime_ok:
                swing_close = float(pending_swing["close"])
                swing_ts = str(pending_swing.get("ts") or bar.ts)
                entry = self._arm_swing_limit(bar, state, pending, swing_close, swing_ts)
                if entry is not None:
                    orders.append(entry)
                    state["entry_pending"] = True
                    state["phase"] = "limit_armed"
                    state.pop("pending_breakout", None)
                    state.pop("post_bo_bars", None)
                    state.pop("pending_swing", None)
                    state.pop("swing_hunt_active", None)
                    features.append(
                        feature_snapshot(
                            self.instance,
                            "wod_swing_entry_arm",
                            bar.ts,
                            source="weekly_open_day_breakout.swing_close",
                            value_ref="%s:%.6f" % (direction, swing_close),
                            metadata={
                                "direction": direction,
                                "swing_close": swing_close,
                                "swing_ts": swing_ts,
                                "breakout_close": pending.get("candle_close"),
                                "breakout_ts": pending.get("breakout_ts"),
                                "breakout_mode": pending.get("breakout_mode"),
                                "swing_before_regime": swing_before_regime,
                                "week_of_month": wom,
                                "deferred_gate": True,
                            },
                        )
                    )
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            # Still blocked — keep waiting (do not hunt a new swing).
            state["phase"] = "wait_swing_gate"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        if not pending:
            state["phase"] = "wait_breakout"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        week_ok = self._week_of_month_ok(session)
        regime_ok = self._regime_ok(state)
        gates_ok = week_ok and regime_ok

        # After-regime mode: do not confirm swings until gates are on; restart bar clock then.
        if not swing_before_regime:
            if not gates_ok:
                state["swing_hunt_active"] = False
                state["phase"] = "wait_swing"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            if not state.get("swing_hunt_active"):
                state["post_bo_bars"] = [
                    {
                        "ts": bar.ts,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                    }
                ]
                state["swing_hunt_active"] = True
                state["phase"] = "wait_swing"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)

        post = list(state.get("post_bo_bars") or [])
        post.append(
            {
                "ts": bar.ts,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
            }
        )
        if len(post) > 64:
            post = post[-64:]
        state["post_bo_bars"] = post

        swing_close = None
        swing_ts = None
        require_pb = bool(self.config.get("swing_require_pullback", True))
        if len(post) >= 3:
            i = len(post) - 2
            prev_h, prev_l = float(post[i - 1]["high"]), float(post[i - 1]["low"])
            cand_o = float(post[i].get("open", post[i]["close"]))
            cand_h, cand_l = float(post[i]["high"]), float(post[i]["low"])
            cand_c = float(post[i]["close"])
            next_h, next_l = float(post[i + 1]["high"]), float(post[i + 1]["low"])
            is_fractal = False
            if direction == "short" and cand_h > prev_h and cand_h > next_h:
                is_fractal = True
            elif direction == "long" and cand_l < prev_l and cand_l < next_l:
                is_fractal = True
            if is_fractal and (
                (not require_pb)
                or self._is_pullback_swing_bar(direction, cand_o, cand_h, cand_l, cand_c)
            ):
                swing_close = cand_c
                swing_ts = str(post[i]["ts"])

        if swing_close is None:
            state["phase"] = "wait_swing"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        wom = _week_of_month(session)
        features.append(
            feature_snapshot(
                self.instance,
                "wod_week_of_month_gate",
                bar.ts,
                source="calendar.session_date",
                value_ref="%s:%s" % (wom, "allowed" if week_ok else "blocked"),
                metadata={
                    "session_date": day,
                    "week_of_month": wom,
                    "allow_weeks_of_month": list(self._allow_weeks_of_month()),
                    "allowed": week_ok,
                },
            )
        )
        features.append(
            feature_snapshot(
                self.instance,
                "wod_regime_gate",
                bar.ts,
                source="daily_closes.ma_vol",
                value_ref="ok" if regime_ok else "blocked",
                metadata={
                    "require_bull_200dma": bool(self.config.get("require_bull_200dma")),
                    "require_high_vol": bool(self.config.get("require_high_vol")),
                    "allowed": regime_ok,
                },
            )
        )
        if not week_ok or not regime_ok:
            if not swing_before_regime:
                # Should not reach here (hunt gated above); keep waiting.
                state["phase"] = "wait_swing"
                self._commit(state)
                return StrategyActions(orders, cancels, [], levels, alerts, features)
            state["pending_swing"] = {
                "close": swing_close,
                "ts": swing_ts,
                "confirm_ts": bar.ts,
                "direction": direction,
            }
            state["phase"] = "wait_swing_gate"
            self._commit(state)
            return StrategyActions(orders, cancels, [], levels, alerts, features)

        entry = self._arm_swing_limit(bar, state, pending, float(swing_close), str(swing_ts or bar.ts))
        if entry is not None:
            orders.append(entry)
            state["entry_pending"] = True
            state["phase"] = "limit_armed"
            state.pop("pending_breakout", None)
            state.pop("post_bo_bars", None)
            state.pop("pending_swing", None)
            state.pop("swing_hunt_active", None)
            features.append(
                feature_snapshot(
                    self.instance,
                    "wod_swing_entry_arm",
                    bar.ts,
                    source="weekly_open_day_breakout.swing_close",
                    value_ref="%s:%.6f" % (direction, swing_close),
                    metadata={
                        "direction": direction,
                        "swing_close": swing_close,
                        "swing_ts": swing_ts,
                        "breakout_close": pending.get("candle_close"),
                        "breakout_ts": pending.get("breakout_ts"),
                        "breakout_mode": pending.get("breakout_mode"),
                        "swing_before_regime": swing_before_regime,
                        "week_of_month": wom,
                    },
                )
            )
        self._commit(state)
        return StrategyActions(orders, cancels, [], levels, alerts, features)

    def _arm_swing_limit(
        self,
        bar: Bar,
        state: Dict[str, Any],
        pending: Dict[str, Any],
        swing_close: float,
        swing_ts: str,
    ) -> Optional[OrderIntent]:
        """Arm at swing close; SL/TP = breakout geometry shifted by (swing - breakout)."""
        direction = str(pending.get("direction") or "")
        bo_close = float(pending["candle_close"])
        candle_hi = float(pending["candle_hi"])
        candle_lo = float(pending["candle_lo"])
        candle_r = float(pending["candle_r"])
        probe = self._arm_limit(bar, direction, candle_hi, candle_lo, bo_close, candle_r, state)
        if probe is None:
            return None
        trade_id = str(state.get("armed_trade_id") or "")
        trade = self._trade(trade_id, state)
        delta = float(swing_close) - bo_close
        trade["limit_price"] = float(swing_close)
        trade["stop"] = float(trade["stop"]) + delta
        for key in ("tp1", "tp2", "tp3", "runner_tp"):
            px = _to_float(trade.get(key))
            if px is not None:
                trade[key] = float(px) + delta
        trade["breakout_ts"] = pending.get("breakout_ts")
        trade["swing_ts"] = swing_ts
        trade["swing_close"] = float(swing_close)
        trade["entry_mode"] = "swing_close"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy" if direction == "long" else "sell",
            order_type="limit",
            quantity=int(trade.get("entry_qty") or self.config.get("entry_qty") or 3),
            limit_price=float(swing_close),
            reason="weekly_od_swing_limit",
            bracket_role="entry",
            requires_verification=False,
            reduce_only=False,
            live_after_ts=bar.ts,
        )

    # ------------------------------------------------------------------

    def _maybe_time_add(

        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
        dt: datetime,
    ) -> tuple:
        """Pyramid ``add_qty`` every ``add_every_hours`` while a campaign is open."""
        hours = float(self.config.get("add_every_hours") or 0.0)
        add_qty = int(self.config.get("add_qty") or 0)
        if hours <= 0 or add_qty <= 0:
            return [], []
        if context.position_quantity == 0 or not state.get("in_trade"):
            return [], []
        trade_id = str(state.get("active_trade_id") or "")
        if not trade_id:
            return [], []
        trade = self._trade(trade_id, state)
        if trade.get("add_pending"):
            return [], []
        # Don't stack a working entry/add while one is already live.
        if any((not o.reduce_only) for o in context.strategy_open_orders if o.trade_id == trade_id):
            return [], []
        adds_done = int(trade.get("adds_done") or 0)
        max_adds = int(self.config.get("max_adds") or 0)
        if max_adds > 0 and adds_done >= max_adds:
            return [], []
        entry_raw = trade.get("entry_ts")
        if not entry_raw:
            return [], []
        entry_ts = _parse_dt(str(entry_raw))
        elapsed_h = (dt - entry_ts).total_seconds() / 3600.0
        next_due = hours * float(adds_done + 1)
        if elapsed_h + 1e-9 < next_due:
            return [], []
        direction = str(trade.get("direction") or "")
        if direction not in {"long", "short"}:
            return [], []
        side = "buy" if direction == "long" else "sell"
        trade["add_pending"] = True
        order = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=add_qty,
            reason="time_add",
            bracket_role="add",
            requires_verification=False,
            reduce_only=False,
            live_after_ts=bar.ts,
        )
        return [order], []

    def _finalize_open_day(self, state: Dict[str, Any]) -> None:
        atr = _to_float(state.get("atr"))
        od_hi = _to_float(state.get("od_high"))
        od_lo = _to_float(state.get("od_low"))
        state["open_day_done"] = True
        if atr is None or atr <= 0 or od_hi is None or od_lo is None or od_hi <= od_lo:
            state["levels_ready"] = False
            state["week_done"] = True
            state["phase"] = "bad_open_day"
            return

        od_day = str(state.get("open_day") or "")
        od_date: Optional[date] = None
        if od_day:
            try:
                od_date = date.fromisoformat(od_day)
            except ValueError:
                od_date = None
        n_bars = int(state.get("open_day_bars") or 0)
        min_bars = int(self.config.get("min_open_day_bars") or 0)
        if min_bars > 0 and n_bars < min_bars:
            state["levels_ready"] = False
            state["week_done"] = True
            state["phase"] = "thin_monday"
            state["open_day_skip"] = "thin_monday_bars=%d<%d" % (n_bars, min_bars)
            return
        if bool(self.config.get("skip_us_holiday_monday")) and od_date is not None:
            if od_date in _us_federal_holidays():
                state["levels_ready"] = False
                state["week_done"] = True
                state["phase"] = "holiday_monday"
                state["open_day_skip"] = "us_holiday_monday"
                return

        mid = 0.5 * (od_hi + od_lo)
        mult = float(self.config.get("atr_mult") or 4.0)
        state["od_mid"] = mid
        state["od_range"] = od_hi - od_lo
        state["atr14"] = atr
        state["atr4_up"] = mid + mult * atr
        state["atr4_dn"] = mid - mult * atr
        state["levels_ready"] = True
        state["need_inside_before_breakout"] = False
        state["phase"] = "wait_breakout"

    def _arm_limit(
        self,
        bar: Bar,
        direction: str,
        candle_hi: float,
        candle_lo: float,
        candle_close: float,
        candle_r: float,
        state: Dict[str, Any],
    ) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 4)
        if qty <= 0:
            return None
        od_r = float(state["od_range"])
        od_hi = float(state["od_high"])
        od_lo = float(state["od_low"])
        stop_mode = str(self.config.get("stop_mode") or "od_far").lower()
        if stop_mode == "candle":
            stop = candle_lo if direction == "long" else candle_hi
        else:
            stop = od_lo if direction == "long" else od_hi
        r_init = abs(candle_close - stop)
        if r_init <= 0:
            return None
        side = "buy" if direction == "long" else "sell"

        trade_id = self._new_trade_id(state)
        exit_mode = str(self.config.get("exit_mode") or "scale").lower()
        if exit_mode == "oco_od_r":
            # Full-size OCO: target = 1× open-day range from entry; SL at OD far side.
            tp1 = candle_close + od_r if direction == "long" else candle_close - od_r
            tp2 = tp1
            tp3 = None
            runner_tp = None
            tp1_qty = qty
            tp2_qty = 0
            tp3_qty = 0
            runner_qty = 0
        elif exit_mode == "scale_od_frac":
            # Scale on OD-range fractions: e.g. 1@0.5×OD, 1@1×OD (BE), runner EOW/3×OD.
            tp1_qty = int(self.config.get("tp1_qty") or 1)
            tp2_qty = int(self.config.get("tp2_qty") or 1)
            tp3_qty = int(self.config.get("tp3_qty") or 0)
            runner_qty = int(self.config.get("runner_qty") or max(0, qty - tp1_qty - tp2_qty - tp3_qty))
            tp1_m = float(self.config.get("tp1_od_mult") if self.config.get("tp1_od_mult") is not None else 0.5)
            tp2_m = float(self.config.get("tp2_od_mult") if self.config.get("tp2_od_mult") is not None else 1.0)
            tp3_m = _to_float(self.config.get("tp3_od_mult"))
            runner_m = _to_float(self.config.get("runner_od_mult"))
            if direction == "long":
                tp1 = candle_close + tp1_m * od_r
                tp2 = candle_close + tp2_m * od_r
                tp3 = (candle_close + tp3_m * od_r) if tp3_m else None
                runner_tp = (candle_close + runner_m * od_r) if runner_m else None
            else:
                tp1 = candle_close - tp1_m * od_r
                tp2 = candle_close - tp2_m * od_r
                tp3 = (candle_close - tp3_m * od_r) if tp3_m else None
                runner_tp = (candle_close - runner_m * od_r) if runner_m else None
        else:
            tp1_qty = int(self.config.get("tp1_qty") or 2)
            tp2_qty = int(self.config.get("tp2_qty") or 1)
            tp3_qty = int(self.config.get("tp3_qty") or 0)
            runner_qty = int(self.config.get("runner_qty") or max(0, qty - tp1_qty - tp2_qty - tp3_qty))
            tp3_mult = _to_float(self.config.get("tp3_r_mult"))
            runner_mult = _to_float(self.config.get("runner_r_mult"))
            if direction == "long":
                tp1 = candle_close + candle_r
                tp2 = candle_close + od_r
                tp3 = (candle_close + tp3_mult * r_init) if tp3_mult else None
                runner_tp = (candle_close + runner_mult * r_init) if runner_mult else None
            else:
                tp1 = candle_close - candle_r
                tp2 = candle_close - od_r
                tp3 = (candle_close - tp3_mult * r_init) if tp3_mult else None
                runner_tp = (candle_close - runner_mult * r_init) if runner_mult else None
        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "limit_price": candle_close,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "runner_tp": runner_tp,
            "candle_r": candle_r,
            "od_r": od_r,
            "r_init": r_init,
            "entry_qty": qty,
            "tp1_qty": tp1_qty,
            "tp2_qty": tp2_qty,
            "tp3_qty": tp3_qty,
            "runner_qty": runner_qty,
            "exit_mode": exit_mode,
            "breakout_ts": bar.ts,
            "tp1_hit": False,
            "tp2_hit": False,
            "tp3_hit": False,
            "runner_hit": False,
            "adds_done": 0,
            "add_pending": False,
        }
        state["armed_trade_id"] = trade_id
        state["active_trade_id"] = trade_id
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=qty,
            limit_price=candle_close,
            reason="weekly_od_breakout_limit",
            bracket_role="entry",
            requires_verification=False,
            reduce_only=False,
            live_after_ts=bar.ts,
        )

    def _exit_orders(self, fill, trade: Dict[str, Any], state: Dict[str, Any]) -> List[OrderIntent]:
        direction = str(trade.get("direction") or "")
        entry = float(fill.price)
        stop = float(trade["stop"])
        tp1 = float(trade["tp1"])
        tp2 = float(trade["tp2"])
        tp3 = _to_float(trade.get("tp3"))
        runner_tp = _to_float(trade.get("runner_tp"))
        planned = _to_float(trade.get("limit_price"))
        if planned is not None and abs(entry - planned) > 1e-12:
            delta = entry - planned
            tp1 += delta
            tp2 += delta
            if tp3 is not None:
                tp3 += delta
            if runner_tp is not None:
                runner_tp += delta
        tp1_qty = int(trade.get("tp1_qty") or 2)
        tp2_qty = int(trade.get("tp2_qty") or 1)
        tp3_qty = int(trade.get("tp3_qty") or 0)
        runner_qty = int(trade.get("runner_qty") or 0)
        entry_qty = int(trade.get("entry_qty") or (tp1_qty + tp2_qty + tp3_qty + runner_qty))
        exit_side = "sell" if direction == "long" else "buy"
        common = dict(
            strategy_id=self.instance.strategy_id,
            trade_id=fill.trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=exit_side,
            requires_verification=False,
            reduce_only=True,
            live_after_ts=fill.ts,
        )
        stop_mode = str(self.config.get("stop_mode") or "od_far").lower()
        stop_reason = "candle_stop" if stop_mode == "candle" else "od_range_stop"
        exit_mode = str(trade.get("exit_mode") or self.config.get("exit_mode") or "").lower()
        oco = ""
        if exit_mode == "oco_od_r":
            oco = new_id("oco")
        out: List[OrderIntent] = []
        out.append(
            OrderIntent.create(
                **common,
                order_type="stop",
                quantity=entry_qty,
                stop_price=stop,
                reason=stop_reason,
                bracket_role="stop",
                oco_group=oco,
            )
        )
        if tp1_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=tp1,
                    reason=("tp1_od_r" if oco else ("tp1_half_od" if exit_mode == "scale_od_frac" else "tp1_candle_r")),
                    bracket_role="tp1",
                    oco_group=oco,
                )
            )
        if tp2_qty > 0:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=tp2,
                    reason="tp2_od_r" if exit_mode != "scale_od_frac" else "tp2_1od",
                    bracket_role="tp2",
                )
            )
        if tp3_qty > 0 and tp3 is not None:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=tp3_qty,
                    limit_price=tp3,
                    reason="tp3_4r" if exit_mode != "scale_od_frac" else "tp3_od",
                    bracket_role="tp3",
                )
            )
        if runner_qty > 0 and runner_tp is not None:
            out.append(
                OrderIntent.create(
                    **common,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=runner_tp,
                    reason="runner_od" if exit_mode == "scale_od_frac" else "runner_20r",
                    bracket_role="runner",
                )
            )
        trade["stop"] = stop
        trade["tp1"] = tp1
        trade["tp2"] = tp2
        trade["tp3"] = tp3
        trade["runner_tp"] = runner_tp
        trade["be_price"] = entry
        return out

    def _move_stop_to_be(
        self,
        fill,
        context: StrategyContext,
        trade: Dict[str, Any],
        state: Dict[str, Any],
    ) -> StrategyActions:
        be = _to_float(trade.get("be_price")) or _to_float(trade.get("entry_price"))
        if be is None:
            return StrategyActions.empty()
        remaining = abs(int(context.position_quantity))
        if remaining <= 0:
            return StrategyActions.empty()
        cancels = [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "be_replace_stop")
            for o in context.strategy_open_orders
            if o.reduce_only and str(o.bracket_role or "") == "stop" and o.trade_id == fill.trade_id
        ]
        direction = str(trade.get("direction") or "")
        exit_side = "sell" if direction == "long" else "buy"
        order = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=fill.trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=exit_side,
            order_type="stop",
            quantity=remaining,
            stop_price=float(be),
            reason="be_stop",
            bracket_role="stop",
            requires_verification=False,
            reduce_only=True,
            live_after_ts=fill.ts,
        )
        trade["stop"] = float(be)
        trade["be_set"] = True
        self._commit(state)
        return StrategyActions([order], cancels, [], [], [])

    def _update_daily_closes(self, state: Dict[str, Any], session: datetime, bar: Bar) -> None:
        """Maintain NY-session daily closes for causal MA / vol regime gates."""
        day = _ny_date_str(session)
        keep = (
            int(self.config.get("ma_len") or 200)
            + int(self.config.get("vol_median_lookback") or 252)
            + int(self.config.get("vol_ret_days") or 20)
            + 40
        )
        if state.get("daily_day") and state.get("daily_day") != day and state.get("daily_close") is not None:
            closes = list(state.get("daily_closes") or [])
            closes.append(float(state["daily_close"]))
            state["daily_closes"] = closes[-keep:]
        state["daily_day"] = day
        state["daily_close"] = float(bar.close)

    def _allow_weeks_of_month(self) -> Set[int]:
        raw = self.config.get("allow_weeks_of_month") or []
        out: Set[int] = set()
        if isinstance(raw, str):
            raw = [p.strip() for p in raw.split(",") if p.strip()]
        for item in raw:
            try:
                wi = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= wi <= 5:
                out.add(wi)
        return out

    def _week_of_month_ok(self, session: datetime) -> bool:
        allow = self._allow_weeks_of_month()
        if not allow:
            return True
        return _week_of_month(session) in allow

    def _regime_ok(self, state: Dict[str, Any]) -> bool:
        need_bull = bool(self.config.get("require_bull_200dma"))
        need_hvol = bool(self.config.get("require_high_vol"))
        if not need_bull and not need_hvol:
            return True
        closes = list(state.get("daily_closes") or [])
        if state.get("daily_close") is not None:
            closes = closes + [float(state["daily_close"])]
        ma_len = int(self.config.get("ma_len") or 200)
        if len(closes) < ma_len:
            return False
        px = float(closes[-1])
        ma = sum(float(x) for x in closes[-ma_len:]) / float(ma_len)
        if need_bull and px < ma:
            return False
        if not need_hvol:
            return True
        ret_n = int(self.config.get("vol_ret_days") or 20)
        look = int(self.config.get("vol_median_lookback") or 252)
        if len(closes) < ret_n + 5:
            return False
        rets: List[float] = []
        for i in range(1, len(closes)):
            p0 = float(closes[i - 1])
            p1 = float(closes[i])
            if p0 > 0:
                rets.append((p1 - p0) / p0)
        if len(rets) < ret_n:
            return False
        import math

        vols: List[float] = []
        for end_i in range(ret_n - 1, len(rets)):
            window = rets[end_i - ret_n + 1 : end_i + 1]
            mean = sum(window) / float(len(window))
            var = sum((x - mean) ** 2 for x in window) / float(len(window))
            vols.append(math.sqrt(var) * math.sqrt(252.0))
        if len(vols) < 30:
            return False
        cur = vols[-1]
        hist = vols[:-1][-look:]
        if not hist:
            return False
        med = sorted(hist)[len(hist) // 2]
        return cur >= med

    def _update_atr(self, state: Dict[str, Any], bar: Bar) -> None:
        prev_close = _to_float(state.get("prev_close"))
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        atr_len = int(self.config.get("atr_len") or ATR_LEN)
        atr = _to_float(state.get("atr"))
        if atr is None:
            seed = list(state.get("atr_seed") or [])
            seed.append(tr)
            state["atr_seed"] = seed[-atr_len:]
            if len(state["atr_seed"]) >= atr_len:
                state["atr"] = sum(float(x) for x in state["atr_seed"]) / float(atr_len)
                state.pop("atr_seed", None)
        else:
            alpha = 1.0 / float(atr_len)
            state["atr"] = atr + alpha * (tr - atr)
        state["prev_close"] = close
        if state.get("weekly_open") in (None, ""):
            state["weekly_open"] = float(bar.open)

    def _fresh_week(self, wkey: str, *, prior: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "week_key": wkey,
            "open_day": "",
            "open_day_done": False,
            "open_day_bars": 0,
            "open_day_skip": "",
            "levels_ready": False,
            "week_done": False,
            "od_high": None,
            "od_low": None,
            "od_mid": None,
            "od_range": None,
            "atr14": None,
            "atr4_up": None,
            "atr4_dn": None,
            "weekly_open": None,
            "phase": "new_week",
            "need_inside_before_breakout": False,
            "entry_pending": False,
            "in_trade": False,
            "pending_breakout": None,
            "post_bo_bars": [],
            "pending_swing": None,
            "swing_hunt_active": False,
            "active_trade_id": "",
            "armed_trade_id": "",
            "campaigns_done": 0,
            "trades": {},
            "trade_seq": int(prior.get("trade_seq") or 0),
            "atr": prior.get("atr"),
            "atr_seed": list(prior.get("atr_seed") or []),
            "prev_close": prior.get("prev_close"),
            "daily_closes": list(prior.get("daily_closes") or []),
            "daily_day": prior.get("daily_day"),
            "daily_close": prior.get("daily_close"),
        }

    def _fresh_week_keep_trade(self, wkey: str, *, prior: Dict[str, Any]) -> Dict[str, Any]:
        fresh = self._fresh_week(wkey, prior=prior)
        fresh["trades"] = dict(prior.get("trades") or {})
        fresh["trade_seq"] = int(prior.get("trade_seq") or 0)
        fresh["in_trade"] = bool(prior.get("in_trade"))
        fresh["active_trade_id"] = str(prior.get("active_trade_id") or "")
        fresh["campaigns_done"] = 0
        if fresh["in_trade"]:
            fresh["phase"] = "in_trade_carry"
            fresh["need_inside_before_breakout"] = True
        return fresh

    def _state(self) -> Dict[str, Any]:
        if not self.state:
            self.state = self._fresh_week("", prior={})
        if "trades" not in self.state or not isinstance(self.state.get("trades"), dict):
            self.state["trades"] = {}
        return self.state

    def _commit(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        seq = int(state.get("trade_seq") or 0) + 1
        state["trade_seq"] = seq
        return new_id("wod")

    def _cancel_all(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "week_roll")
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "flat_cancel")
            for o in context.strategy_open_orders
            if o.reduce_only and o.trade_id == trade_id
        ]

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self._state().get("active_trade_id") or new_id("wod")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            bracket_role="close",
            requires_verification=False,
            reduce_only=True,
            live_after_ts=ts,
        )

    def _level_updates(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        out: List[LevelUpdate] = []
        sid = self.instance.strategy_id
        inst = self.instance.instrument
        for name, key in (
            ("od_high", "od_high"),
            ("od_low", "od_low"),
            ("od_mid", "od_mid"),
            ("atr4_up", "atr4_up"),
            ("atr4_dn", "atr4_dn"),
        ):
            v = _to_float(state.get(key))
            if v is not None:
                out.append(LevelUpdate(sid, inst, name, v, ts))
        return out
