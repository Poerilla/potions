"""Monday opening-range breakout with DD cuts + optional shifted primary.

Rules (NY clock, 15m bars)
--------------------------
- Monday OR high/low; R = high − low.
- Tue→Fri: long on close > Mon high, short on close < Mon low.
- Enter ``entry_qty`` (default 3). Stop distance 1R; target ``reward_R`` × R.
- DD cuts toward stop: drop ``dd30_qty`` @ 30%, flatten last ``dd50_qty`` @ 50%
  (no runner past 50%).
- Optional HTF filter: skip when last completed 1h bar has both MA50/150 and
  OBV vs OBV-SMA20 opposed to the trade.
- Optional shifted primary: after flat@50%, arm opposite Mon extreme breakout
  with the same structure (does not count toward max primary/week).
- Max ``max_trades_per_week`` primary entries/week; Fri week-end flatten.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

NY = pytz.timezone("America/New_York")
UTC = pytz.UTC


class MondayOrBreakoutStrategy(StrategyPlugin):
    strategy_type = "monday_or_breakout"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.00001,
            "entry_qty": 3,
            "dd30_qty": 2,
            "dd50_qty": 1,
            "shifted_entry_qty": None,  # default: same as entry_qty
            "shifted_dd30_qty": None,
            "shifted_dd50_qty": None,
            "dd30_frac": 0.30,
            "dd50_frac": 0.50,
            "reward_R": 2.0,
            "max_trades_per_week": 2,
            "skip_both_opposed": True,
            "shifted_primary": True,
            "obv_ma": 20,
            "min_R": 1e-5,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def _main_sizing(self) -> Tuple[int, int, int]:
        return (
            int(self.config["entry_qty"]),
            int(self.config["dd30_qty"]),
            int(self.config["dd50_qty"]),
        )

    def _shifted_sizing(self) -> Tuple[int, int, int]:
        e, d30, d50 = self._main_sizing()
        se = self.config.get("shifted_entry_qty")
        s30 = self.config.get("shifted_dd30_qty")
        s50 = self.config.get("shifted_dd50_qty")
        return (
            int(se) if se is not None else e,
            int(s30) if s30 is not None else d30,
            int(s50) if s50 is not None else d50,
        )
    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "15m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_15m(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            entry = float(fill.price)
            R = float(trade.get("R") or state.get("R") or 0.0)
            reward = float(self.config["reward_R"])
            f30 = float(self.config.get("dd30_frac") or 0.30)
            f50 = float(self.config.get("dd50_frac") or 0.50)
            if direction == "Long":
                stop = entry - R
                target = entry + reward * R
                dd30 = entry - f30 * R
                dd50 = entry - f50 * R
            else:
                stop = entry + R
                target = entry - reward * R
                dd30 = entry + f30 * R
                dd50 = entry + f50 * R
            trade.update(
                {
                    "status": "open",
                    "direction": direction,
                    "entry_price": entry,
                    "entry_qty": int(fill.quantity),
                    "remaining": int(fill.quantity),
                    "stop": stop,
                    "target": target,
                    "dd30": dd30,
                    "dd50": dd50,
                    "is_shifted": bool(trade.get("is_shifted")),
                    "dd30_qty": int(trade.get("dd30_qty") or self.config["dd30_qty"]),
                    "dd50_qty": int(trade.get("dd50_qty") or self.config["dd50_qty"]),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            orders.extend(self._exit_orders(fill.trade_id, direction, trade))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role == "dd30":
            rem = max(0, int(trade.get("remaining") or 0) - int(fill.quantity))
            trade["remaining"] = rem
            trade["cut_30"] = int(trade.get("cut_30") or 0) + int(fill.quantity)
            # Shrink target to remaining
            cancels.extend(self._cancel_roles(context, fill.trade_id, {"target"}))
            if rem > 0:
                orders.append(
                    self._limit_exit(
                        fill.trade_id,
                        trade["direction"],
                        rem,
                        float(trade["target"]),
                        "target",
                    )
                )
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"dd50", "stop", "target", "week_end", "flatten"}:
            rem = max(0, int(trade.get("remaining") or 0) - int(fill.quantity))
            trade["remaining"] = rem
            if role == "dd50":
                trade["cut_50"] = int(trade.get("cut_50") or 0) + int(fill.quantity)
                trade["flat_at_50"] = True
            if rem <= 0 or context.position_quantity == 0:
                trade["status"] = "closed"
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                cancels.extend(self._cancel_reduce(context, fill.trade_id))
                # Arm shifted primary after flat@50% (primary only)
                if (
                    bool(self.config.get("shifted_primary"))
                    and role == "dd50"
                    and not bool(trade.get("is_shifted"))
                    and not state.get("pending_shift_side")
                ):
                    direction = str(trade.get("direction") or "")
                    state["pending_shift_side"] = "Short" if direction == "Long" else "Long"
                    state["pending_shift_parent"] = fill.trade_id
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_15m(self, bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_ny(bar.ts)
        state = self._state()
        self._update_htf(state, bar, dt)

        week_key = _week_monday_key(dt)
        if state.get("week_monday") != week_key:
            # New week — flatten leftovers from prior week if any
            orders: List[OrderIntent] = []
            cancels: List[CancelIntent] = []
            if context.position_quantity != 0:
                cancels.extend(self._cancel_all(context))
                orders.append(self._flatten(context, bar.ts, "week_end"))
            state = self._fresh_week(week_key)
            self._commit_state(state)
            if orders or cancels:
                return StrategyActions(orders, cancels, [], [], [])

        orders = []
        cancels = []
        wd = dt.weekday()  # Mon=0 … Sun=6

        # Build Monday OR
        if wd == 0:
            hi = float(state["mon_high"]) if state.get("mon_high") is not None else bar.high
            lo = float(state["mon_low"]) if state.get("mon_low") is not None else bar.low
            state["mon_high"] = max(hi, bar.high)
            state["mon_low"] = min(lo, bar.low)
            state["R"] = float(state["mon_high"]) - float(state["mon_low"])
            self._commit_state(state)
            return StrategyActions.empty()

        # Sat/Sun — ignore
        if wd >= 5:
            self._commit_state(state)
            return StrategyActions.empty()

        R = float(state.get("R") or 0.0)
        mon_high = state.get("mon_high")
        mon_low = state.get("mon_low")
        if mon_high is None or mon_low is None or R < float(self.config["min_R"]):
            self._commit_state(state)
            return StrategyActions.empty()

        # Friday end-of-week flatten on last bars (after 16:00 NY Fri or last Fri bar handled via next Mon)
        # Explicit Fri flatten near end: if Friday and hour >= 16, flatten.
        if wd == 4 and dt.hour >= 16:
            if context.position_quantity != 0 or self._has_open_entry(context):
                cancels.extend(self._cancel_all(context))
                if context.position_quantity != 0:
                    orders.append(self._flatten(context, bar.ts, "week_end"))
                state["pending_shift_side"] = ""
                state["done_week"] = True
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if state.get("done_week"):
            self._commit_state(state)
            return StrategyActions.empty()

        if context.position_quantity != 0 or state.get("current_leg_open") or self._has_open_entry(context):
            self._commit_state(state)
            return StrategyActions.empty()

        close = float(bar.close)
        pending = state.get("pending_shift_side") or ""

        # Shifted sidecar first (owns opposite extreme)
        if pending:
            hit = (close < float(mon_low)) if pending == "Short" else (close > float(mon_high))
            if hit:
                side = "short" if pending == "Short" else "long"
                if self._htf_blocks(state, side):
                    self._commit_state(state)
                    return StrategyActions.empty()
                trade_id = new_id("trade")
                se, s30, s50 = self._shifted_sizing()
                self._trade(trade_id, state).update(
                    {
                        "status": "pending_entry",
                        "is_shifted": True,
                        "R": R,
                        "parent": state.get("pending_shift_parent") or "",
                        "dd30_qty": s30,
                        "dd50_qty": s50,
                    }
                )
                state["pending_shift_side"] = ""
                orders.append(self._entry_order(trade_id, pending, bar.ts, se))
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [])
            # Opposite extreme reserved while armed
            if (pending == "Short" and close < float(mon_low)) or (
                pending == "Long" and close > float(mon_high)
            ):
                self._commit_state(state)
                return StrategyActions.empty()

        primary_count = int(state.get("primary_count") or 0)
        if primary_count >= int(self.config["max_trades_per_week"]):
            self._commit_state(state)
            return StrategyActions.empty()

        direction = None
        if close > float(mon_high):
            direction = "Long"
        elif close < float(mon_low):
            direction = "Short"
        if direction is None:
            self._commit_state(state)
            return StrategyActions.empty()
        if pending and direction == pending:
            self._commit_state(state)
            return StrategyActions.empty()

        side = "long" if direction == "Long" else "short"
        if self._htf_blocks(state, side):
            self._commit_state(state)
            return StrategyActions.empty()

        trade_id = new_id("trade")
        me, m30, m50 = self._main_sizing()
        self._trade(trade_id, state).update(
            {
                "status": "pending_entry",
                "is_shifted": False,
                "R": R,
                "parent": "",
                "dd30_qty": m30,
                "dd50_qty": m50,
            }
        )
        state["primary_count"] = primary_count + 1
        orders.append(self._entry_order(trade_id, direction, bar.ts, me))
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    # --- HTF -----------------------------------------------------------------
    def _update_htf(self, state: Dict[str, Any], bar, dt: datetime) -> None:
        hour_key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
        cur = state.get("htf_hour_key")
        if cur != hour_key:
            if cur and state.get("htf_o") is not None:
                self._finalize_htf_hour(state)
            state["htf_hour_key"] = hour_key
            state["htf_o"] = float(bar.open)
            state["htf_h"] = float(bar.high)
            state["htf_l"] = float(bar.low)
            state["htf_c"] = float(bar.close)
            state["htf_v"] = float(bar.volume or 0.0)
        else:
            state["htf_h"] = max(float(state["htf_h"]), float(bar.high))
            state["htf_l"] = min(float(state["htf_l"]), float(bar.low))
            state["htf_c"] = float(bar.close)
            state["htf_v"] = float(state.get("htf_v") or 0.0) + float(bar.volume or 0.0)

    def _finalize_htf_hour(self, state: Dict[str, Any]) -> None:
        closes: List[float] = list(state.get("htf_closes") or [])
        obvs: List[float] = list(state.get("htf_obvs") or [])
        c = float(state["htf_c"])
        prev_c = closes[-1] if closes else c
        direction = 0.0 if c == prev_c else (1.0 if c > prev_c else -1.0)
        vol = float(state.get("htf_v") or 0.0)
        proxy = max(float(state["htf_h"]) - float(state["htf_l"]), 1e-8)
        use_vol = vol if vol > 0 else proxy
        prev_obv = obvs[-1] if obvs else 0.0
        obv = prev_obv + direction * use_vol
        closes.append(c)
        obvs.append(obv)
        # Keep tail for MA150 / OBV MA
        max_keep = 200
        if len(closes) > max_keep:
            closes = closes[-max_keep:]
            obvs = obvs[-max_keep:]
        state["htf_closes"] = closes
        state["htf_obvs"] = obvs
        ma50 = _sma(closes, 50)
        ma150 = _sma(closes, 150)
        obv_ma = _sma(obvs, int(self.config.get("obv_ma") or 20))
        state["htf_ma50"] = ma50
        state["htf_ma150"] = ma150
        state["htf_obv_ma"] = obv_ma
        state["htf_obv"] = obv
        if ma50 is not None and ma150 is not None:
            state["htf_ma_bull"] = bool(ma50 > ma150)
        if obv_ma is not None:
            state["htf_obv_bull"] = bool(obv > obv_ma)

    def _htf_blocks(self, state: Dict[str, Any], side: str) -> bool:
        if not bool(self.config.get("skip_both_opposed")):
            return False
        if "htf_ma_bull" not in state or "htf_obv_bull" not in state:
            return False
        ma_bull = bool(state["htf_ma_bull"])
        obv_bull = bool(state["htf_obv_bull"])
        if side == "long":
            return (not ma_bull) and (not obv_bull)
        return ma_bull and obv_bull

    # --- orders --------------------------------------------------------------
    def _entry_order(self, trade_id: str, direction: str, ts: str, qty: int) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy" if direction == "Long" else "sell",
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
        )

    def _exit_orders(self, trade_id: str, direction: str, trade: Dict[str, Any]) -> List[OrderIntent]:
        exit_side = "sell" if direction == "Long" else "buy"
        dd30_qty = int(trade.get("dd30_qty") if trade.get("dd30_qty") is not None else self.config["dd30_qty"])
        dd50_qty = int(trade.get("dd50_qty") if trade.get("dd50_qty") is not None else self.config["dd50_qty"])
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        out: List[OrderIntent] = []
        if dd30_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="stop",
                    quantity=dd30_qty,
                    stop_price=float(trade["dd30"]),
                    reason="dd30",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="dd30",
                )
            )
        if dd50_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="stop",
                    quantity=dd50_qty,
                    stop_price=float(trade["dd50"]),
                    reason="dd50",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="dd50",
                )
            )
        out.append(
            self._limit_exit(trade_id, direction, entry_qty, float(trade["target"]), "target")
        )
        return out

    def _limit_exit(
        self, trade_id: str, direction: str, qty: int, price: float, reason: str
    ) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if direction == "Long" else "buy",
            order_type="limit",
            quantity=qty,
            limit_price=price,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
        )

    def _flatten(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if context.position_quantity > 0 else "buy",
            order_type="market",
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            live_after_ts=ts,
        )

    def _cancel_roles(self, context: StrategyContext, trade_id: str, roles) -> List[CancelIntent]:
        role_set = set(roles)
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "mon_or_cancel_%s" % order.bracket_role)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.bracket_role in role_set
        ]

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "mon_or_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "mon_or_cancel_all")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    # --- state ---------------------------------------------------------------
    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "trades" not in raw:
            raw["trades"] = {}
        self.state = raw
        return raw

    def _fresh_week(self, week_key: str) -> Dict[str, Any]:
        prev_htf = {
            k: self.state.get(k)
            for k in (
                "htf_closes",
                "htf_obvs",
                "htf_ma50",
                "htf_ma150",
                "htf_obv",
                "htf_obv_ma",
                "htf_ma_bull",
                "htf_obv_bull",
                "htf_hour_key",
                "htf_o",
                "htf_h",
                "htf_l",
                "htf_c",
                "htf_v",
            )
            if k in self.state
        }
        state: Dict[str, Any] = {
            "week_monday": week_key,
            "mon_high": None,
            "mon_low": None,
            "R": 0.0,
            "primary_count": 0,
            "pending_shift_side": "",
            "pending_shift_parent": "",
            "current_leg_open": False,
            "active_trade_id": "",
            "done_week": False,
            "trades": {},
        }
        state.update(prev_htf)
        self.state = state
        return state

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]


def _parse_ny(ts: str) -> datetime:
    value = str(ts)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
        dt = UTC.localize(dt)
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(NY)


def _week_monday_key(dt: datetime) -> str:
    d = dt.date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def _sma(vals: List[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    return float(sum(vals[-n:]) / n)
