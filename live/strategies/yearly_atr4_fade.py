"""Yearly first-month ±4×ATR first-touch fade (daily).

Yearly analogue of ``quarterly_atr4_fade`` for FX/metals yearly-ORB names:

1. Calendar January is the formation window. Year open = first January open.
   First-month ATR = mean daily true range of January (``jan_mean_tr``), or
   Wilder ATR(14) frozen at January close (``atr14_jan_close``).
2. After January completes, fade the first touch of ``anchor ± atr_mult×ATR``.
   Default anchor is year open (market open); ``fm_mid`` uses January mid.
3. Touch upper first → short; touch lower first → long. Same-bar dual touch
   skips the year.
4. Scale: 1@anchor + runner @ opposite ±4×ATR. Risk = ``risk_atr_mult`` × ATR
   beyond the theoretical entry. Runner fill may reverse once.
5. Flatten residual at year change (``live_after_ts`` = first bar of new year).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..models import Alert, Bar, CancelIntent, LevelUpdate, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

ATR_LEN = 14


class YearlyAtr4FadeStrategy(StrategyPlugin):
    strategy_type = "yearly_atr4_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.01,
            "entry_qty": 2,
            "tp1_qty": 1,
            "atr_len": ATR_LEN,
            "atr_mult": 4.0,
            "risk_atr_mult": 2.0,
            # year_open | fm_mid
            "anchor": "year_open",
            # jan_mean_tr | atr14_jan_close
            "atr_source": "jan_mean_tr",
            "max_trades_per_year": 2,
            "allowed_sides": None,
            "timeframe": "D",
            "record_levels": False,
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "D")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_daily_bar(bar, context)

    def on_daily_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        return self.on_bar_close(bar, context)

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
            state["entry_pending"] = False
            state["phase"] = "in_trade"
            orders = self._exit_orders(fill.trade_id, str(trade.get("direction") or ""), state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role == "tp1":
            trade["tp1_hit"] = True
            cancels = self._cancel_open_roles(context, fill.trade_id, {"stop", "runner_tp"})
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                orders.extend(self._runner_exit_orders(fill.trade_id, str(trade.get("direction") or ""), state))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role == "year_change":
            # Prior-year flatten after the year already rolled — do not consume
            # the new year's trade budget or mark the year done.
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                state["prior_year_flatten"] = False
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        if role in {"stop", "runner_tp"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                trade["exit_reason"] = role
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                state["trades_done"] = int(state.get("trades_done") or 0) + 1
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                orders = []
                max_n = int(self.config.get("max_trades_per_year") or 2)
                if (
                    role == "runner_tp"
                    and int(state.get("trades_done") or 0) < max_n
                    and not state.get("done")
                ):
                    reverse = self._arm_reverse(fill.ts, state, str(trade.get("direction") or ""))
                    if reverse is not None:
                        orders.append(reverse)
                        state["phase"] = "reverse_armed"
                else:
                    if int(state.get("trades_done") or 0) >= max_n:
                        state["done"] = True
                        state["phase"] = "done"
                    elif role == "stop":
                        state["done"] = True
                        state["phase"] = "stopped"
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_daily_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_ts(bar.ts)
        year = int(dt.year)
        month = int(dt.month)
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        if state.get("year") != year:
            # Roll immediately so January of the new year still builds. Flatten
            # any leftover on the next open (live_after_ts = this bar).
            if context.position_quantity != 0 or state.get("current_leg_open"):
                cancels.extend(self._cancel_all_open(context, "year_change_reset"))
            prior_pos = int(context.position_quantity)
            state = self._fresh_year_state(year, prior=state)
            if prior_pos != 0:
                orders.append(self._close_all_qty(prior_pos, bar.ts, "year_change"))
                state["prior_year_flatten"] = True

        self._update_atr(state, bar)

        levels: List[LevelUpdate] = []
        alerts: List[Alert] = []

        if month == 1:
            if state.get("year_open") is None:
                state["year_open"] = float(bar.open)
            hi = float(state["fm_high"]) if state.get("fm_high") is not None else bar.high
            lo = float(state["fm_low"]) if state.get("fm_low") is not None else bar.low
            state["fm_high"] = max(hi, bar.high)
            state["fm_low"] = min(lo, bar.low)
            state["fm_bar_count"] = int(state.get("fm_bar_count") or 0) + 1
            tr = _last_tr(state, bar)
            state["jan_tr_sum"] = float(state.get("jan_tr_sum") or 0.0) + tr
            state["jan_tr_n"] = int(state.get("jan_tr_n") or 0) + 1
            state["phase"] = "building_first_month"

        if (not state.get("levels_ready")) and month >= 2:
            self._finalize_levels(state)
            if state.get("levels_ready") and not bool(self.config.get("suppress_alerts")):
                alerts.append(
                    Alert.create(
                        self.instance.strategy_id,
                        "info",
                        "yearly_atr4_fade levels ready anchor=%.6f ±%.0fATR"
                        % (
                            float(state.get("anchor_px") or 0.0),
                            float(self.config.get("atr_mult") or 4.0),
                        ),
                    )
                )

        if bool(self.config.get("record_levels")) and state.get("levels_ready"):
            levels.extend(self._levels(bar.ts, state))

        if state.get("done"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if state.get("current_leg_open") or context.position_quantity != 0:
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if month < 2 or not state.get("levels_ready"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

        if int(state.get("trades_done") or 0) >= int(self.config.get("max_trades_per_year") or 2):
            state["done"] = True
            state["phase"] = "done"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], levels, alerts)

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
                if not self._side_allowed(side):
                    state["done"] = True
                    state["phase"] = "side_filtered"
                else:
                    state["first_side"] = side
                    entry = self._arm_entry(bar.ts, state, side)
                    if entry is not None:
                        orders.append(entry)
                        state["entry_pending"] = True
                        state["phase"] = "entry_sent"

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], levels, alerts)

    def _finalize_levels(self, state: Dict[str, Any]) -> None:
        fm_hi = _to_float(state.get("fm_high"))
        fm_lo = _to_float(state.get("fm_low"))
        year_open = _to_float(state.get("year_open"))
        n_jan = int(state.get("jan_tr_n") or 0)
        if fm_hi is None or fm_lo is None or year_open is None or fm_hi <= fm_lo or n_jan < 5:
            state["done"] = True
            state["phase"] = "bad_levels"
            return
        src = str(self.config.get("atr_source") or "jan_mean_tr")
        if src == "atr14_jan_close":
            atr = _to_float(state.get("atr"))
        else:
            atr = float(state.get("jan_tr_sum") or 0.0) / float(n_jan)
        if atr is None or atr <= 0:
            state["done"] = True
            state["phase"] = "bad_levels"
            return
        mid = 0.5 * (fm_hi + fm_lo)
        anchor_mode = str(self.config.get("anchor") or "year_open")
        anchor = mid if anchor_mode == "fm_mid" else year_open
        mult = float(self.config.get("atr_mult") or 4.0)
        state["fm_mid"] = mid
        state["fm_range"] = fm_hi - fm_lo
        state["jan_atr"] = atr
        state["anchor_px"] = anchor
        state["upper"] = anchor + mult * atr
        state["lower"] = anchor - mult * atr
        state["levels_ready"] = True
        state["phase"] = "watching_first_touch"

    def _update_atr(self, state: Dict[str, Any], bar: Bar) -> None:
        prev_close = _to_float(state.get("prev_close"))
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        state["_last_tr"] = tr
        atr_len = int(self.config.get("atr_len") or ATR_LEN)
        n = int(state.get("atr_n") or 0) + 1
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
            expires_after_ts=_year_expiry(int(state.get("year") or 0)),
        )

    def _arm_reverse(self, ts: str, state: Dict[str, Any], prior_direction: str) -> Optional[OrderIntent]:
        side = "lower" if prior_direction == "Short" else "upper"
        if not self._side_allowed(side):
            state["done"] = True
            state["phase"] = "side_filtered"
            return None
        state["entry_pending"] = False
        return self._arm_entry(ts, state, side)

    def _trade_levels(
        self, state: Dict[str, Any], side: str
    ) -> Optional[Tuple[str, float, float, float]]:
        upper = _to_float(state.get("upper"))
        lower = _to_float(state.get("lower"))
        anchor = _to_float(state.get("anchor_px"))
        atr = _to_float(state.get("jan_atr"))
        if upper is None or lower is None or anchor is None or atr is None or atr <= 0:
            return None
        risk = float(self.config.get("risk_atr_mult") or 2.0) * atr
        if side == "upper":
            direction = "Short"
            entry_ref = upper
            stop = entry_ref + risk
            tp1 = anchor
            runner_tp = lower
        elif side == "lower":
            direction = "Long"
            entry_ref = lower
            stop = entry_ref - risk
            tp1 = anchor
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
        expiry = _year_expiry(int(state.get("year") or 0))
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
        expiry = _year_expiry(int(state.get("year") or 0))
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

    def _close_all_qty(self, position_quantity: int, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(position_quantity))
        side = "sell" if position_quantity > 0 else "buy"
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

    def _cancel_all_open(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, reason)
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
        for name, key in (("upper", "upper"), ("anchor", "anchor_px"), ("lower", "lower")):
            px = _to_float(state.get(key))
            if px is None:
                continue
            out.append(LevelUpdate(self.instance.strategy_id, self.instance.instrument, name, px, ts))
        return out

    def _side_allowed(self, side: str) -> bool:
        raw = self.config.get("allowed_sides")
        if raw is None or raw == "" or raw == []:
            return True
        if isinstance(raw, str):
            allowed = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            allowed = [str(x) for x in raw]
        if not allowed:
            return True
        return side in allowed

    def _fresh_year_state(self, year: int, prior: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prior = prior or {}
        return {
            "year": year,
            "year_open": None,
            "fm_high": None,
            "fm_low": None,
            "fm_mid": None,
            "fm_range": None,
            "fm_bar_count": 0,
            "jan_tr_sum": 0.0,
            "jan_tr_n": 0,
            "jan_atr": None,
            "anchor_px": None,
            "atr": prior.get("atr"),
            "atr_n": prior.get("atr_n") or 0,
            "atr_seed": list(prior.get("atr_seed") or []),
            "prev_close": prior.get("prev_close"),
            "upper": None,
            "lower": None,
            "levels_ready": False,
            "first_side": "",
            "entry_pending": False,
            "trades_done": 0,
            "current_leg_open": False,
            "active_trade_id": "",
            "prior_year_flatten": False,
            "done": False,
            "phase": "new_year",
            "trades": {},
            "trade_seq": int(prior.get("trade_seq") or 0),
        }

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "year" not in raw:
            raw = self._fresh_year_state(0)
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


def _parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text[:10])


def _year_expiry(year: int) -> str:
    if not year:
        return ""
    return "%d-01-01T00:00:00" % (int(year) + 1)


def _last_tr(state: Dict[str, Any], bar: Bar) -> float:
    cached = _to_float(state.get("_last_tr"))
    if cached is not None:
        return cached
    prev = _to_float(state.get("prev_close"))
    high = float(bar.high)
    low = float(bar.low)
    if prev is None:
        return high - low
    return max(high - low, abs(high - prev), abs(low - prev))


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
