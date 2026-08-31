"""Quarterly open-week ±4×ATR first-touch fade with mid scaleout + reverse.

Matches the quarterly 4h chart study levels:

1. Opening week of the quarter (ISO week containing quarter start, clipped to
   the quarter) defines range high/low/mid and ATR(14) at the week close.
2. After the opening week completes, wait for the first touch of mid±4×ATR.
3. Touch upper first → short 2 contracts; touch lower first → long 2.
4. Risk = half the opening-week range (stop beyond entry by 0.5×range).
5. Scale: 1 off at mid ("halfway of the range"), runner at the opposite ±4×ATR.
6. When the runner completes at the opposite ±4×ATR, reverse with the same
   structure (2 contracts). Max 2 trades per quarter.
7. Flatten any residual at quarter end.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

ATR_LEN = 14


class QuarterlyAtr4FadeStrategy(StrategyPlugin):
    strategy_type = "quarterly_atr4_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.00001,
            "entry_qty": 2,
            "tp1_qty": 1,
            "atr_len": ATR_LEN,
            "atr_mult": 4.0,
            "risk_range_frac": 0.5,
            "max_trades_per_quarter": 2,
            "timeframe": "4h",
            "record_levels": False,
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "4h")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_4h_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason

        if role == "entry":
            trade.update(
                {
                    "status": "open",
                    "entry_price": float(fill.price),
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["phase"] = "in_trade"
            orders = self._exit_orders(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role == "tp1":
            trade["tp1_hit"] = True
            # Keep stop + runner_tp; cancel nothing essential. Qty on stop stays
            # full until broker reduce-only clips; rebuild stop for remaining.
            cancels = self._cancel_open_roles(context, fill.trade_id, {"stop", "runner_tp"})
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                orders.extend(self._runner_exit_orders(fill.trade_id, str(trade.get("direction") or ""), state))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"stop", "runner_tp", "quarter_close"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                state["trades_done"] = int(state.get("trades_done") or 0) + 1
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                orders: List[OrderIntent] = []
                # Reverse only when the runner completes at the opposite ±4×ATR.
                if role == "runner_tp" and int(state.get("trades_done") or 0) < int(
                    self.config.get("max_trades_per_quarter") or 2
                ):
                    reverse = self._arm_reverse(fill.ts, state, str(trade.get("direction") or ""))
                    if reverse is not None:
                        orders.append(reverse)
                        state["phase"] = "reverse_armed"
                else:
                    if int(state.get("trades_done") or 0) >= int(self.config.get("max_trades_per_quarter") or 2):
                        state["done"] = True
                        state["phase"] = "done"
                    elif role == "stop":
                        state["done"] = True
                        state["phase"] = "stopped"
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    # ------------------------------------------------------------------

    def _on_4h_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        qkey = _quarter_key(dt)
        state = self._state()
        if state.get("quarter_key") != qkey:
            # Flatten residual from prior quarter before rolling state.
            orders0: List[OrderIntent] = []
            cancels0: List[CancelIntent] = []
            if context.position_quantity != 0 or state.get("current_leg_open"):
                cancels0.extend(self._cancel_all_open(context))
                if context.position_quantity != 0:
                    orders0.append(self._close_all(context, bar.ts, "quarter_close"))
                self._commit_state(state)
                # Defer fresh quarter until flat on a later bar if still open.
                if context.position_quantity != 0:
                    return StrategyActions(orders0, cancels0, [], [], [])
            state = self._fresh_quarter_state(qkey, prior=state)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        # Maintain Wilder ATR on every 4h bar (causal).
        self._update_atr(state, bar)

        q_start, q_end = _quarter_bounds(dt)
        week0, week1 = _week_bounds(q_start)
        ow_left = max(week0, q_start)

        in_open_week = ow_left <= dt < week1
        if in_open_week:
            hi = float(state["ow_high"]) if state.get("ow_high") is not None else bar.high
            lo = float(state["ow_low"]) if state.get("ow_low") is not None else bar.low
            state["ow_high"] = max(hi, bar.high)
            state["ow_low"] = min(lo, bar.low)
            state["ow_bar_count"] = int(state.get("ow_bar_count") or 0) + 1
            state["phase"] = "building_open_week"

        # Finalize levels on the first bar at/after opening-week end.
        if (not state.get("levels_ready")) and dt >= week1 and state.get("ow_high") is not None:
            atr = _to_float(state.get("atr"))
            ow_hi = float(state["ow_high"])
            ow_lo = float(state["ow_low"])
            if atr is None or atr <= 0 or ow_hi <= ow_lo:
                state["done"] = True
                state["phase"] = "bad_levels"
            else:
                mid = 0.5 * (ow_hi + ow_lo)
                mult = float(self.config.get("atr_mult") or 4.0)
                state["ow_mid"] = mid
                state["ow_range"] = ow_hi - ow_lo
                state["atr14"] = atr
                state["upper"] = mid + mult * atr
                state["lower"] = mid - mult * atr
                state["levels_ready"] = True
                state["phase"] = "watching_first_touch"
                if not bool(self.config.get("suppress_alerts")):
                    alerts.append(
                        Alert.create(
                            self.instance.strategy_id,
                            "info",
                            "quarterly_atr4_fade levels ready mid=%.6f ±4ATR" % mid,
                        )
                    )

        if bool(self.config.get("record_levels")) and state.get("levels_ready"):
            levels.extend(self._levels(bar.ts, state))

        # Quarter-end flatten on last bars of the quarter window.
        if dt >= q_end - _bar_delta() or (hasattr(dt, "month") and _next_bar_crosses_quarter(dt, q_end)):
            # Use explicit: if this bar's timestamp is still in quarter but next
            # period would leave — flatten when bar is the last we will see.
            pass

        # Detect end of quarter: bar is still in quarter; if we're past last day
        # of quarter month end we still process. Flatten when quarter rolls
        # (handled at top). Also flatten on final bar of quarter if identifiable.
        if state.get("done"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("current_leg_open") or context.position_quantity != 0:
            # Opportunity to flatten if this is the last bar of the quarter.
            if _is_last_bar_of_quarter(dt, q_end):
                cancels.extend(self._cancel_all_open(context))
                if context.position_quantity != 0:
                    orders.append(self._close_all(context, bar.ts, "quarter_close"))
                state["done"] = True
                state["phase"] = "quarter_end"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if not state.get("levels_ready"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if int(state.get("trades_done") or 0) >= int(self.config.get("max_trades_per_quarter") or 2):
            state["done"] = True
            state["phase"] = "done"
            self._commit_state(state)
            return StrategyActions.empty()

        # First-touch entry (only when no trade yet this quarter, or reverse
        # was armed via market on fill — reverse path uses market immediately).
        if not state.get("first_side") and not state.get("entry_pending"):
            upper = float(state["upper"])
            lower = float(state["lower"])
            hit_up = bar.high >= upper
            hit_dn = bar.low <= lower
            if hit_up and hit_dn:
                state["done"] = True
                state["phase"] = "dual_touch_skip"
            elif hit_up or hit_dn:
                side = "upper" if hit_up else "lower"
                state["first_side"] = side
                entry = self._arm_entry(bar.ts, state, side)
                if entry is not None:
                    orders.append(entry)
                    state["entry_pending"] = True
                    state["phase"] = "entry_sent"

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    # ------------------------------------------------------------------

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
        n = int(state.get("atr_n") or 0) + 1
        atr = _to_float(state.get("atr"))
        if atr is None:
            # Seed with SMA of TR until atr_len samples.
            seed = list(state.get("atr_seed") or [])
            seed.append(tr)
            state["atr_seed"] = seed[-atr_len:]
            if len(state["atr_seed"]) >= atr_len:
                atr = sum(float(x) for x in state["atr_seed"]) / float(atr_len)
                state["atr"] = atr
                state.pop("atr_seed", None)
        else:
            alpha = 1.0 / float(atr_len)
            state["atr"] = atr + alpha * (tr - atr)
        state["atr_n"] = n
        state["prev_close"] = close

    def _arm_entry(self, ts: str, state: Dict[str, Any], side: str) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 2)
        if qty <= 0:
            return None
        levels = self._trade_levels(state, side)
        if levels is None:
            return None
        direction, stop, tp1, runner_tp = levels
        trade_id = self._new_trade_id(state)
        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "side": side,
            "stop": stop,
            "tp1": tp1,
            "runner_tp": runner_tp,
            "entry_qty": qty,
            "tp1_qty": int(self.config.get("tp1_qty") or 1),
            "tp1_hit": False,
            "leg": int(state.get("trades_done") or 0) + 1,
        }
        state["active_trade_id"] = trade_id
        side_ord = "sell" if direction == "Short" else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side_ord,
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
            expires_after_ts=_quarter_expiry(state.get("quarter_key") or ""),
        )

    def _arm_reverse(self, ts: str, state: Dict[str, Any], prior_direction: str) -> Optional[OrderIntent]:
        # Prior Short (from upper) → reverse Long at lower; Prior Long → Short.
        side = "lower" if prior_direction == "Short" else "upper"
        state["entry_pending"] = False
        return self._arm_entry(ts, state, side)

    def _trade_levels(
        self, state: Dict[str, Any], side: str
    ) -> Optional[Tuple[str, float, float, float]]:
        upper = _to_float(state.get("upper"))
        lower = _to_float(state.get("lower"))
        mid = _to_float(state.get("ow_mid"))
        rng = _to_float(state.get("ow_range"))
        if upper is None or lower is None or mid is None or rng is None or rng <= 0:
            return None
        risk = float(self.config.get("risk_range_frac") or 0.5) * rng
        if side == "upper":
            # Short at upper; stop above; TP1 mid; runner lower.
            direction = "Short"
            entry_ref = upper
            stop = entry_ref + risk
            tp1 = mid
            runner_tp = lower
        elif side == "lower":
            direction = "Long"
            entry_ref = lower
            stop = entry_ref - risk
            tp1 = mid
            runner_tp = upper
        else:
            return None
        return direction, stop, tp1, runner_tp

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        tp1 = _to_float(trade.get("tp1"))
        runner_tp = _to_float(trade.get("runner_tp"))
        qty = int(trade.get("entry_qty") or 0)
        tp1_qty = int(trade.get("tp1_qty") or self.config.get("tp1_qty") or 1)
        tp1_qty = min(tp1_qty, qty)
        runner_qty = max(0, qty - tp1_qty)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or tp1 is None or runner_tp is None or qty <= 0 or not direction:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _quarter_expiry(str(state.get("quarter_key") or ""))
        out: List[OrderIntent] = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=stop,
                reason="stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="stop",
                expires_after_ts=expiry,
            )
        ]
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
                    limit_price=tp1,
                    reason="tp1",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp1",
                    expires_after_ts=expiry,
                )
            )
        if runner_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=runner_tp,
                    reason="runner_tp",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="runner_tp",
                    expires_after_ts=expiry,
                )
            )
        return out

    def _runner_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        runner_tp = _to_float(trade.get("runner_tp"))
        qty = int(trade.get("entry_qty") or 0)
        tp1_qty = int(trade.get("tp1_qty") or 1)
        rem = max(0, qty - tp1_qty)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or runner_tp is None or rem <= 0 or not direction:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _quarter_expiry(str(state.get("quarter_key") or ""))
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=rem,
                stop_price=stop,
                reason="stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="stop",
                expires_after_ts=expiry,
            ),
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=rem,
                limit_price=runner_tp,
                reason="runner_tp",
                requires_verification=False,
                reduce_only=True,
                bracket_role="runner_tp",
                expires_after_ts=expiry,
            ),
        ]

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        trade_id = str(self._state().get("active_trade_id") or new_id("t"))
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

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, "quarter_roll")
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and bool(o.reduce_only):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "position_flat"))
        return out

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: set) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and (o.reason in roles or o.bracket_role in roles):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "rebuild_exits"))
        return out

    def _levels(self, ts: str, state: Dict[str, Any]) -> List[LevelUpdate]:
        out: List[LevelUpdate] = []
        for name, key in (("upper", "upper"), ("mid", "ow_mid"), ("lower", "lower")):
            px = _to_float(state.get(key))
            if px is None:
                continue
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, name, px, ts))
        return out

    def _fresh_quarter_state(self, qkey: str, prior: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prior = prior or {}
        return {
            "quarter_key": qkey,
            "ow_high": None,
            "ow_low": None,
            "ow_mid": None,
            "ow_range": None,
            "ow_bar_count": 0,
            "atr": prior.get("atr"),
            "atr_n": prior.get("atr_n") or 0,
            "atr_seed": list(prior.get("atr_seed") or []),
            "prev_close": prior.get("prev_close"),
            "atr14": None,
            "upper": None,
            "lower": None,
            "levels_ready": False,
            "first_side": "",
            "entry_pending": False,
            "trades_done": 0,
            "current_leg_open": False,
            "active_trade_id": "",
            "done": False,
            "phase": "new_quarter",
            "trades": {},
            "trade_seq": int(prior.get("trade_seq") or 0),
        }

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "quarter_key" not in raw:
            raw = self._fresh_quarter_state("")
        if "trades" not in raw or not isinstance(raw["trades"], dict):
            raw["trades"] = {}
        self.state = raw
        return raw

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        trade = trades.get(trade_id)
        if trade is None:
            trade = {}
            trades[trade_id] = trade
        return trade

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq") or 0) + 1
        return "%s_t%d" % (self.instance.strategy_id, int(state["trade_seq"]))


def _parse_dt(ts: str) -> datetime:
    t = pd_timestamp(ts)
    return t.to_pydatetime() if hasattr(t, "to_pydatetime") else t


def pd_timestamp(ts: str):
    import pandas as pd

    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("America/New_York")


def _quarter_key(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return "%dQ%d" % (dt.year, q)


def _quarter_bounds(dt: datetime):
    import pandas as pd

    q = (dt.month - 1) // 3 + 1
    month0 = 1 + (q - 1) * 3
    t0 = pd.Timestamp(year=dt.year, month=month0, day=1, tz="America/New_York")
    t1 = t0 + pd.offsets.MonthBegin(3)
    return t0, t1


def _week_bounds(ts):
    import pandas as pd

    local = pd.Timestamp(ts)
    if local.tzinfo is None:
        local = local.tz_localize("America/New_York")
    else:
        local = local.tz_convert("America/New_York")
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    return monday, monday + pd.Timedelta(days=7)


def _bar_delta():
    import pandas as pd

    return pd.Timedelta(hours=4)


def _is_last_bar_of_quarter(dt: datetime, q_end) -> bool:
    import pandas as pd

    # 4h bar left-labeled; last bar of quarter starts < q_end and next would be >= q_end.
    ts = pd.Timestamp(dt)
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/New_York")
    return (ts + pd.Timedelta(hours=4)) >= q_end and ts < q_end


def _next_bar_crosses_quarter(dt: datetime, q_end) -> bool:
    return _is_last_bar_of_quarter(dt, q_end)


def _quarter_expiry(qkey: str) -> str:
    import pandas as pd

    if not qkey or "Q" not in qkey:
        return ""
    try:
        year_s, q_s = qkey.split("Q", 1)
        year = int(year_s)
        q = int(q_s)
        month0 = 1 + (q - 1) * 3
        t0 = pd.Timestamp(year=year, month=month0, day=1, tz="America/New_York")
        t1 = t0 + pd.offsets.MonthBegin(3)
        return t1.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
