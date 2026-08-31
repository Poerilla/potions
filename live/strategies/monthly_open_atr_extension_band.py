"""Monthly-open extension mean-band fade on 1h bars (Engine plugin).

Uses precomputed causal month plans (rolling band, pct75/max entry variants) from
the driver config. After the opening week, arms entries toward month open.

Entry triggers:
  - ``resting_limit`` (default): resting limit at band entry; optional gap-void + retag.
  - ``traverse_reclaim``: (1) hourly close *through* the entry (long: close below;
    short: close above), then (2) reverse and hourly close back *in favour*
    (long: close back above entry with close≥open; short: close back below with
    close≤open) → market entry. Same SL/target from the month plan.
  - ``first_week_ohlc_flip``: week-1 NY 4h OHLC/OLHC liquidity-run filter. Need
    ≥2 consecutive 4h candles that open+close on the same side of month open,
    then a 4h close on the opposite side (still in week 1). Trade the flip
    direction (opposite of the run): **market** on the confirming 4h close;
    SL = run swing extreme. Ladder typically 1/1/1 → band-med / band-max in
    the trade direction / runner to EOM; BE only after the main (band-max) TP.

Optional ladder: scale at band-med / month-open / runner. Runner stop moves to
BE only after the month-open target fills. Optional ``runner_target_r_mult``
places a runner limit **past** month-open by that many initial-R (entry→stop).

Gap rule (resting_limit only): void fills that would occur after price gaps
through the entry vs the prior bar close. After a gap-through, cancel the
resting entry and wait until price re-tags the level before re-arming the limit.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(ts: str) -> datetime:
    import pandas as pd

    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.to_pydatetime()


def _parse_ladder(raw: Any) -> Tuple[int, int, int]:
    """Return (med_qty, target_qty, runner_qty). Empty / zeros → flat single target."""
    if raw is None or raw == "" or raw is False:
        return 0, 0, 0
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace("-", "/").split("/") if p.strip()]
        vals = [int(float(p)) for p in parts]
    elif isinstance(raw, (list, tuple)):
        vals = [int(float(x)) for x in raw]
    else:
        return 0, 0, 0
    while len(vals) < 3:
        vals.append(0)
    return int(vals[0]), int(vals[1]), int(vals[2])


class MonthlyOpenAtrExtensionBandStrategy(StrategyPlugin):
    strategy_type = "monthly_open_atr_extension_band"
    version = "v5"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 10,
            "entry_mode": "pct75",
            "sl_mode": "mean_max",
            "rolling_window": 6,
            "timeframe": "1h",
            "month_plans": {},
            "suppress_alerts": True,
            # Week-of-month filter: 1..5 from calendar day ((day-1)//7 + 1).
            "skip_entry_weeks": [],
            # Ladder qtys at band-med / month-open / runner. 0/0/0 = flat target.
            "ladder_qtys": [0, 0, 0],
            # Runner TP past month-open by N × initial R (0 = no runner TP; EOM/BE only).
            "runner_target_r_mult": 0.0,
            # resting_limit | traverse_reclaim | first_week_ohlc_flip
            "entry_trigger": "resting_limit",
            # Void overnight (or any) gap-through fills; require retag before re-arm.
            "require_trade_through": True,
            # Min consecutive same-side 4h O&C candles for liquidity run (ohlc flip).
            "ohlc_run_min_bars": 2,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "1h")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_1h_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "direction": "Long" if fill.side == "buy" else "Short",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["phase"] = "in_trade"
            side_key = str(trade.get("side_key") or "")
            if side_key == "long":
                state["long_done"] = True
                state["long_armed"] = False
            elif side_key == "short":
                state["short_done"] = True
                state["short_armed"] = False
            orders = self._exit_orders(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role == "target_med":
            trade["med_hit"] = True
            rem = max(0, abs(int(context.position_quantity)))
            cancels.extend(self._cancel_roles(context, fill.trade_id, {"stop"}))
            stop = _to_float(trade.get("stop"))
            direction = str(trade.get("direction") or "")
            if rem > 0 and stop is not None and direction:
                orders.append(self._stop_order(fill.trade_id, direction, rem, float(stop), state))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role == "target_open":
            trade["target_hit"] = True
            rem = max(0, abs(int(context.position_quantity)))
            if rem > 0 and bool(trade.get("runner_qty")):
                # Move runner stop to BE (entry); cancel old stop + leftover target.
                cancels.extend(self._cancel_roles(context, fill.trade_id, {"stop", "target"}))
                entry_px = _to_float(trade.get("entry_price")) or _to_float(trade.get("entry"))
                if entry_px is not None:
                    trade["stop"] = float(entry_px)
                    trade["be_armed"] = True
                    orders.append(self._stop_order(fill.trade_id, str(trade.get("direction") or ""), rem, float(entry_px), state))
                runner_tp = self._runner_target_price(trade)
                if runner_tp is not None:
                    trade["runner_target"] = float(runner_tp)
                    orders.append(
                        self._runner_target_order(
                            fill.trade_id,
                            str(trade.get("direction") or ""),
                            rem,
                            float(runner_tp),
                            state,
                        )
                    )
            elif rem == 0:
                cancels.extend(self._cancel_reduce_orders(context, fill.trade_id))
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"target_runner", "runner_tp"}:
            rem = max(0, abs(int(context.position_quantity)))
            if rem == 0:
                cancels.extend(self._cancel_reduce_orders(context, fill.trade_id))
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"stop", "eom", "flatten"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_1h_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        import pandas as pd

        dt = _parse_ts(bar.ts)
        ny = pd.Timestamp(dt).tz_convert("America/New_York")
        month_key = "%04d-%02d" % (int(ny.year), int(ny.month))
        week = int((int(ny.day) - 1) // 7) + 1
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        if state.get("month_key") != month_key:
            if context.position_quantity != 0 or state.get("current_leg_open"):
                cancels.extend(self._cancel_all_open(context))
                if context.position_quantity != 0:
                    orders.append(self._close_all(context, bar.ts, "eom"))
            prior = dict(state)
            state = self._fresh_month_state(month_key, prior=prior)
            state["plan"] = dict((self.config.get("month_plans") or {}).get(month_key) or {})

        plan = dict(state.get("plan") or {})
        prev_close = _to_float(state.get("prev_close"))

        if not plan:
            state["prev_close"] = float(bar.close)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        watch_start = str(plan.get("watch_start_ts") or "")
        month_end = str(plan.get("month_end_ts") or "")
        if watch_start and bar.ts < watch_start:
            state["prev_close"] = float(bar.close)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if month_end and bar.ts >= month_end:
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eom"))
            state["done"] = True
            state["phase"] = "month_end"
            state["prev_close"] = float(bar.close)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if _is_last_bar_of_month(ny, month_end):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eom"))
            state["done"] = True
            state["phase"] = "eom_flatten"
            state["prev_close"] = float(bar.close)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("done"):
            state["prev_close"] = float(bar.close)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        skip_weeks = {int(w) for w in (self.config.get("skip_entry_weeks") or [])}
        week_blocked = week in skip_weeks
        require_tt = bool(self.config.get("require_trade_through", True))
        entry_trigger = str(self.config.get("entry_trigger") or "resting_limit").lower()
        reclaim_mode = entry_trigger in {"traverse_reclaim", "reclaim", "close_reclaim"}
        ohlc_flip_mode = entry_trigger in {
            "first_week_ohlc_flip",
            "ohlc_flip",
            "first_week_ohlc",
            "week1_ohlc_flip",
        }
        expiry = month_end or ""

        # Entering a skipped week: cancel resting entries so fills cannot occur in-week.
        if week_blocked:
            for side_key in ("long", "short"):
                if self._has_open_entry(context, side_key):
                    cancels.extend(self._cancel_entry_side(context, side_key))
                    state["%s_armed" % side_key] = False
            state["phase"] = "week_skip_%d" % week

        if ohlc_flip_mode:
            flip_orders, flip_cancels = self._ohlc_flip_on_bar(
                bar=bar,
                ny=ny,
                week=week,
                week_blocked=week_blocked,
                state=state,
                plan=plan,
                context=context,
                expiry=expiry,
            )
            orders.extend(flip_orders)
            cancels.extend(flip_cancels)
            state["prev_close"] = float(bar.close)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        for side_key in ("long", "short"):
            leg = plan.get(side_key)
            if not leg:
                continue
            entry_px = _to_float(dict(leg).get("entry"))
            done_key = "%s_done" % side_key
            armed_key = "%s_armed" % side_key
            await_key = "%s_await_retag" % side_key
            trav_key = "%s_traversed" % side_key

            if reclaim_mode:
                if (
                    state.get(done_key)
                    or state.get(armed_key)
                    or week_blocked
                    or state.get("current_leg_open")
                    or self._has_open_entry(context, side_key)
                    or entry_px is None
                ):
                    continue
                close_px = float(bar.close)
                open_px = float(bar.open)
                if not state.get(trav_key):
                    if _traversed_close(side_key, entry_px, close_px):
                        state[trav_key] = True
                        state["phase"] = "%s_traversed" % side_key
                    continue
                # Already traversed: wait for reverse + close in favour.
                if _reclaim_close_in_favour(side_key, entry_px, open_px, close_px):
                    entry = self._arm_side(
                        bar.ts,
                        state,
                        side_key,
                        dict(leg),
                        expiry,
                        order_type="market",
                        fill_price=close_px,
                    )
                    if entry is not None:
                        orders.append(entry)
                        state[armed_key] = True
                        state["phase"] = "%s_reclaim_entry" % side_key
                continue

            # resting_limit path
            if require_tt and entry_px is not None and prev_close is not None:
                if _gapped_through(side_key, entry_px, prev_close, float(bar.open)):
                    # Void any resting entry; require a retag before re-arm.
                    cancels.extend(self._cancel_entry_side(context, side_key))
                    state[armed_key] = False
                    state[await_key] = True
                    state["phase"] = "%s_gap_void" % side_key

            if state.get(await_key) and entry_px is not None:
                if _retag_cleared(side_key, entry_px, bar):
                    state[await_key] = False
                    state["phase"] = "%s_retag_ok" % side_key

            if (
                not state.get(done_key)
                and not state.get(armed_key)
                and not state.get(await_key)
                and not week_blocked
                and not self._has_open_entry(context, side_key)
                and not state.get("current_leg_open")
            ):
                entry = self._arm_side(bar.ts, state, side_key, dict(leg), expiry)
                if entry is not None:
                    orders.append(entry)
                    state[armed_key] = True
                    state["phase"] = "%s_armed" % side_key

        state["prev_close"] = float(bar.close)
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _ohlc_flip_on_bar(
        self,
        *,
        bar: Bar,
        ny,
        week: int,
        week_blocked: bool,
        state: Dict[str, Any],
        plan: Dict[str, Any],
        context: StrategyContext,
        expiry: str,
    ) -> Tuple[List[OrderIntent], List[CancelIntent]]:
        """Week-1 4h liquidity-run → opposite close → arm band-entry fade with swing SL."""
        import pandas as pd

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        month_open = _to_float(plan.get("month_open"))
        if month_open is None:
            return orders, cancels

        # Finalize / update NY-aligned 4h buckets from 1h bars.
        bucket = pd.Timestamp(ny).floor("4h")
        bucket_key = bucket.isoformat()
        cur = dict(state.get("ohlc4h_bucket") or {})
        just_closed = None
        if cur.get("key") and cur.get("key") != bucket_key:
            just_closed = {
                "open": float(cur["open"]),
                "high": float(cur["high"]),
                "low": float(cur["low"]),
                "close": float(cur["close"]),
                "week": int(cur.get("week") or 0),
                "ts": str(cur.get("key") or ""),
            }
            self._ohlc_flip_on_4h_close(just_closed, state=state, month_open=float(month_open))
            cur = {}
        if not cur:
            cur = {
                "key": bucket_key,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "week": int(week),
            }
        else:
            cur["high"] = max(float(cur["high"]), float(bar.high))
            cur["low"] = min(float(cur["low"]), float(bar.low))
            cur["close"] = float(bar.close)
            # Keep week from bucket open (do not let a week-boundary 4h reclassify).
        state["ohlc4h_bucket"] = cur

        side_key = str(state.get("ohlc_side") or "")
        if not side_key or not state.get("ohlc_ready") or not state.get("ohlc_entry_pending"):
            return orders, cancels
        if (
            state.get("%s_done" % side_key)
            or state.get("%s_armed" % side_key)
            or state.get("current_leg_open")
            or self._has_open_entry(context, side_key)
            or week_blocked
        ):
            state["ohlc_entry_pending"] = False
            return orders, cancels

        # Continuation targets in the flip direction use the opposite band leg
        # (short after upside run → take profits into the downside band).
        opp_key = "long" if side_key == "short" else "short"
        opp = dict(plan.get(opp_key) or {})
        if not opp:
            state["phase"] = "ohlc_no_band_%s" % opp_key
            state["ohlc_entry_pending"] = False
            return orders, cancels
        swing_stop = _to_float(state.get("ohlc_swing_stop"))
        # Prefer confirming 4h close when the signal just printed.
        fill_px = float(just_closed["close"]) if just_closed is not None else float(bar.close)
        med = _to_float(opp.get("med"))
        # Main TP = band extreme in trade direction (band_max on opposite leg).
        target = _to_float(opp.get("band_max"))
        if target is None:
            target = _to_float(opp.get("entry"))
        if swing_stop is None or med is None or target is None:
            state["phase"] = "ohlc_levels_incomplete"
            state["ohlc_entry_pending"] = False
            return orders, cancels
        leg = {
            "entry": fill_px,
            "stop": float(swing_stop),
            "med": float(med),
            "target": float(target),
        }
        entry = self._arm_side(
            bar.ts,
            state,
            side_key,
            leg,
            expiry,
            order_type="market",
            fill_price=fill_px,
            stop_override=float(swing_stop),
        )
        state["ohlc_entry_pending"] = False
        if entry is not None:
            orders.append(entry)
            state["%s_armed" % side_key] = True
            state["phase"] = "ohlc_%s_mkt_entry" % side_key
        else:
            state["phase"] = "ohlc_%s_arm_reject" % side_key
        return orders, cancels

    def _ohlc_flip_on_4h_close(
        self, candle: Dict[str, Any], *, state: Dict[str, Any], month_open: float
    ) -> None:
        if state.get("ohlc_ready") or state.get("ohlc_failed"):
            return
        week = int(candle.get("week") or 0)
        if week != 1:
            # Pattern must complete inside week 1; later 4h closes abort further hunting.
            if week > 1:
                state["ohlc_failed"] = True
                state["phase"] = "ohlc_missed_week1"
            return

        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])
        side = _ohlc_same_side(month_open, o, c)
        run_side = str(state.get("ohlc_run_side") or "")
        run_n = int(state.get("ohlc_run_n") or 0)
        run_hi = _to_float(state.get("ohlc_run_hi"))
        run_lo = _to_float(state.get("ohlc_run_lo"))
        min_run = max(2, int(self.config.get("ohlc_run_min_bars") or 2))

        # Flip: after a completed run, opposite-side close.
        if run_side and run_n >= min_run:
            if run_side == "above" and c < month_open:
                state["ohlc_ready"] = True
                state["ohlc_entry_pending"] = True
                state["ohlc_side"] = "short"
                state["ohlc_swing_stop"] = float(run_hi if run_hi is not None else h)
                state["phase"] = "ohlc_flip_short"
                return
            if run_side == "below" and c > month_open:
                state["ohlc_ready"] = True
                state["ohlc_entry_pending"] = True
                state["ohlc_side"] = "long"
                state["ohlc_swing_stop"] = float(run_lo if run_lo is not None else l)
                state["phase"] = "ohlc_flip_long"
                return

        # Extend or reset liquidity-run streak (O&C both on same side of open).
        if side and side == run_side:
            state["ohlc_run_n"] = run_n + 1
            state["ohlc_run_hi"] = max(float(run_hi if run_hi is not None else h), h)
            state["ohlc_run_lo"] = min(float(run_lo if run_lo is not None else l), l)
            state["phase"] = "ohlc_run_%s_n%d" % (side, int(state["ohlc_run_n"]))
        elif side:
            state["ohlc_run_side"] = side
            state["ohlc_run_n"] = 1
            state["ohlc_run_hi"] = h
            state["ohlc_run_lo"] = l
            state["phase"] = "ohlc_run_%s_n1" % side
        else:
            # Straddle / cross candle resets the run (must be clean O&C same side).
            state["ohlc_run_side"] = ""
            state["ohlc_run_n"] = 0
            state["ohlc_run_hi"] = None
            state["ohlc_run_lo"] = None
            state["phase"] = "ohlc_run_reset"

    def _arm_side(
        self,
        ts: str,
        state: Dict[str, Any],
        side_key: str,
        leg: Dict[str, Any],
        expiry: str,
        *,
        order_type: str = "limit",
        fill_price: Optional[float] = None,
        stop_override: Optional[float] = None,
    ) -> Optional[OrderIntent]:
        med_q, tgt_q, run_q = _parse_ladder(self.config.get("ladder_qtys"))
        ladder_total = med_q + tgt_q + run_q
        qty = ladder_total if ladder_total > 0 else int(self.config.get("entry_qty") or 10)
        entry = _to_float(leg.get("entry"))
        stop = _to_float(stop_override) if stop_override is not None else _to_float(leg.get("stop"))
        target = _to_float(leg.get("target"))
        med = _to_float(leg.get("med"))
        if qty <= 0 or entry is None or stop is None or target is None:
            return None
        if side_key == "long":
            direction = "Long"
            side = "buy"
            if not (stop < entry):
                return None
            if med is not None and not (entry < med <= target + 1e-9):
                med = None
        else:
            direction = "Short"
            side = "sell"
            if not (stop > entry):
                return None
            if med is not None and not (entry > med >= target - 1e-9):
                med = None
        if ladder_total > 0 and med_q > 0 and med is None:
            return None
        trade_id = self._new_trade_id(state)
        otype = str(order_type or "limit").lower()
        # Plan entry defines levels; market reclaim fills near confirming close.
        ref_entry = float(fill_price) if (otype == "market" and fill_price is not None) else float(entry)
        initial_r = abs(float(entry) - float(stop))
        state["trades"][trade_id] = {
            "direction": direction,
            "side_key": side_key,
            "status": "armed",
            "entry": float(entry),
            "stop": stop,
            "initial_stop": stop,
            "initial_r": initial_r,
            "target": target,
            "med": med,
            "entry_qty": qty,
            "med_qty": med_q if ladder_total > 0 else 0,
            "target_qty": tgt_q if ladder_total > 0 else qty,
            "runner_qty": run_q if ladder_total > 0 else 0,
            "med_hit": False,
            "target_hit": False,
            "be_armed": False,
        }
        kwargs: Dict[str, Any] = {
            "strategy_id": self.instance.strategy_id,
            "trade_id": trade_id,
            "instrument": self.instance.instrument,
            "account_mode": self.instance.account_mode,
            "side": side,
            "order_type": otype,
            "quantity": qty,
            "reason": "entry",
            "requires_verification": True,
            "bracket_role": "entry",
            "live_after_ts": ts,
            "expires_after_ts": expiry,
        }
        if otype == "limit":
            kwargs["limit_price"] = float(entry)
        else:
            # Market: optional limit hint unused by broker; keep for audit.
            kwargs["limit_price"] = float(ref_entry)
        return OrderIntent.create(**kwargs)

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        target = _to_float(trade.get("target"))
        med = _to_float(trade.get("med"))
        qty = int(trade.get("entry_qty") or self.config.get("entry_qty") or 10)
        med_q = int(trade.get("med_qty") or 0)
        tgt_q = int(trade.get("target_qty") or 0)
        run_q = int(trade.get("runner_qty") or 0)
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        if stop is None or qty <= 0:
            return []
        out: List[OrderIntent] = [self._stop_order(trade_id, direction, qty, float(stop), state)]
        # Flat book: single target at month open for full size.
        if med_q <= 0 and run_q <= 0:
            if target is None:
                return out
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="sell" if direction == "Long" else "buy",
                    order_type="limit",
                    quantity=qty,
                    limit_price=target,
                    reason="target_open",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="target",
                    expires_after_ts=expiry,
                )
            )
            return out
        if med_q > 0 and med is not None:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="sell" if direction == "Long" else "buy",
                    order_type="limit",
                    quantity=med_q,
                    limit_price=med,
                    reason="target_med",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp_med",
                    expires_after_ts=expiry,
                )
            )
        if tgt_q > 0 and target is not None:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="sell" if direction == "Long" else "buy",
                    order_type="limit",
                    quantity=tgt_q,
                    limit_price=target,
                    reason="target_open",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="target",
                    expires_after_ts=expiry,
                )
            )
        return out

    def _runner_target_price(self, trade: Dict[str, Any]) -> Optional[float]:
        """Limit past month-open TP by runner_target_r_mult × initial R."""
        mult = _to_float(self.config.get("runner_target_r_mult")) or 0.0
        if mult <= 0:
            return None
        target = _to_float(trade.get("target"))
        r = _to_float(trade.get("initial_r"))
        if r is None or r <= 0:
            entry = _to_float(trade.get("entry_price")) or _to_float(trade.get("entry"))
            stop0 = _to_float(trade.get("initial_stop")) or _to_float(trade.get("stop"))
            if entry is None or stop0 is None:
                return None
            r = abs(float(entry) - float(stop0))
        if target is None or r <= 0:
            return None
        direction = str(trade.get("direction") or "")
        if direction == "Long":
            return float(target) + float(mult) * float(r)
        if direction == "Short":
            return float(target) - float(mult) * float(r)
        return None

    def _runner_target_order(
        self, trade_id: str, direction: str, qty: int, limit_px: float, state: Dict[str, Any]
    ) -> OrderIntent:
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if direction == "Long" else "buy",
            order_type="limit",
            quantity=qty,
            limit_price=limit_px,
            reason="target_runner",
            requires_verification=False,
            reduce_only=True,
            bracket_role="runner_tp",
            expires_after_ts=expiry,
        )

    def _stop_order(
        self, trade_id: str, direction: str, qty: int, stop: float, state: Dict[str, Any]
    ) -> OrderIntent:
        plan = dict(state.get("plan") or {})
        expiry = str(plan.get("month_end_ts") or "")
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if direction == "Long" else "buy",
            order_type="stop",
            quantity=qty,
            stop_price=stop,
            reason="stop",
            requires_verification=False,
            reduce_only=True,
            bracket_role="stop",
            expires_after_ts=expiry,
        )

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        trade_id = str(context.strategy_open_orders[0].trade_id) if context.strategy_open_orders else new_id("trade")
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="flatten",
            live_after_ts=ts,
        )

    def _has_open_entry(self, context: StrategyContext, side_key: str) -> bool:
        want = "buy" if side_key == "long" else "sell"
        for o in context.strategy_open_orders:
            if o.bracket_role == "entry" and not bool(o.reduce_only) and o.side == want:
                return True
        return False

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "month_roll")
            for o in context.strategy_open_orders
        ]

    def _cancel_entry_side(self, context: StrategyContext, side_key: str) -> List[CancelIntent]:
        want = "buy" if side_key == "long" else "sell"
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.bracket_role == "entry" and not bool(o.reduce_only) and o.side == want:
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "gap_void"))
        return out

    def _cancel_roles(self, context: StrategyContext, trade_id: str, roles: set) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and str(o.bracket_role or "") in roles:
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "role_replace"))
        return out

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and bool(o.reduce_only):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "position_flat"))
        return out

    def _fresh_month_state(self, month_key: str, prior: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prior = prior or {}
        return {
            "month_key": month_key,
            "plan": {},
            "long_done": False,
            "short_done": False,
            "long_armed": False,
            "short_armed": False,
            "long_await_retag": False,
            "short_await_retag": False,
            "long_traversed": False,
            "short_traversed": False,
            "current_leg_open": False,
            "active_trade_id": "",
            "done": False,
            "phase": "new_month",
            "prev_close": prior.get("prev_close"),
            "trades": {},
            "trade_seq": int(prior.get("trade_seq") or 0),
            # first_week_ohlc_flip
            "ohlc4h_bucket": {},
            "ohlc_run_side": "",
            "ohlc_run_n": 0,
            "ohlc_run_hi": None,
            "ohlc_run_lo": None,
            "ohlc_ready": False,
            "ohlc_failed": False,
            "ohlc_entry_pending": False,
            "ohlc_side": "",
            "ohlc_swing_stop": None,
        }

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "month_key" not in raw:
            raw = self._fresh_month_state("")
        if "trades" not in raw or not isinstance(raw["trades"], dict):
            raw["trades"] = {}
        self.state = raw
        return raw

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {"status": "new"}
        return trades[trade_id]

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        seq = int(state.get("trade_seq") or 0) + 1
        state["trade_seq"] = seq
        return "%s_t%d" % (self.instance.strategy_id, seq)


def _ohlc_same_side(month_open: float, open_px: float, close_px: float) -> str:
    """Return 'above'/'below' when O and C are both strictly on one side of month open."""
    if open_px > month_open and close_px > month_open:
        return "above"
    if open_px < month_open and close_px < month_open:
        return "below"
    return ""


def _gapped_through(side_key: str, entry: float, prev_close: float, bar_open: float) -> bool:
    if side_key == "long":
        return prev_close > entry and bar_open < entry
    return prev_close < entry and bar_open > entry


def _traversed_close(side_key: str, entry: float, close_px: float) -> bool:
    """Hourly close through the entry level (extension confirm)."""
    if side_key == "long":
        return close_px < entry
    return close_px > entry


def _reclaim_close_in_favour(
    side_key: str, entry: float, open_px: float, close_px: float
) -> bool:
    """Reverse back through entry with candle close in fade direction."""
    if side_key == "long":
        # Back above entry + bullish close
        return close_px > entry and close_px >= open_px
    # Back below entry + bearish close
    return close_px < entry and close_px <= open_px


def _retag_cleared(side_key: str, entry: float, bar: Bar) -> bool:
    if side_key == "long":
        return float(bar.high) >= entry
    return float(bar.low) <= entry


def _is_last_bar_of_month(ny_ts, month_end_iso: str) -> bool:
    import pandas as pd

    if not month_end_iso:
        return False
    end = pd.Timestamp(month_end_iso)
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    ny_end = end.tz_convert("America/New_York")
    return (ny_ts + pd.Timedelta(hours=1)) >= ny_end and ny_ts < ny_end
