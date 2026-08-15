"""Fade the phantom exit of a source strategy (ST+PMC / v2b).

Does **not** take the source trade. Watches a precomputed phantom schedule:
when the source's would-be TP is hit → enter the **opposite** side;
when the source's would-be SL is hit → enter the **same** side at that SL.

Fade trade uses ``stop_pts`` / ``target_pts`` (index-point risk sweep).
Phantoms loaded from ``phantoms_path`` JSON (list of trigger events).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

NY = pytz.timezone("America/New_York")


class PhantomExitFadeStrategy(StrategyPlugin):
    strategy_type = "phantom_exit_fade"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.1,
            "entry_qty": 1,
            "stop_pts": 50.0,
            "target_pts": 150.0,
            "phantoms_path": "",
            "timeframe": "1m",
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._phantoms: List[Dict[str, Any]] = []
        path = str(self.config.get("phantoms_path") or "")
        if path and Path(path).exists():
            self._phantoms = json.loads(Path(path).read_text(encoding="utf-8"))
            self._phantoms = sorted(self._phantoms, key=lambda p: str(p.get("trigger_ts") or ""))

    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        tf = str(self.config.get("timeframe") or "1m")
        if bar.timeframe != tf or not bar.complete:
            return StrategyActions.empty()
        state = self._state()
        idx = int(state.get("phantom_idx") or 0)
        # Skip phantoms that fire while a fade leg is already open.
        if state.get("current_leg_open") or state.get("awaiting_entry"):
            while idx < len(self._phantoms):
                trig_ts = str(self._phantoms[idx].get("trigger_ts") or "")
                if not trig_ts or bar.ts < trig_ts:
                    break
                idx += 1
            state["phantom_idx"] = idx
            self._commit_state(state)
            return StrategyActions.empty()
        while idx < len(self._phantoms):
            ph = self._phantoms[idx]
            trig_ts = str(ph.get("trigger_ts") or "")
            if not trig_ts or bar.ts < trig_ts:
                break
            # Fire on first bar at/after trigger (range touch preferred; else gap-in).
            trig_px = float(ph["trigger_price"])
            touched = float(bar.low) <= trig_px <= float(bar.high)
            if not touched and bar.ts >= trig_ts:
                touched = True
            if not touched:
                break
            intent = self._entry_intent(ph, bar.ts, state)
            state["phantom_idx"] = idx + 1
            self._commit_state(state)
            if intent is None:
                idx = int(state["phantom_idx"])
                continue
            return StrategyActions([intent], [], [], [], [])
        state["phantom_idx"] = idx
        self._commit_state(state)
        return StrategyActions.empty()

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason
        if role == "entry":
            side = str(fill.side).lower()
            direction = "Long" if side == "buy" else "Short"
            entry = float(fill.price)
            stop_pts = float(self.config["stop_pts"])
            target_pts = float(self.config["target_pts"])
            if direction == "Long":
                stop = entry - stop_pts
                target = entry + target_pts
            else:
                stop = entry + stop_pts
                target = entry - target_pts
            trade.update(
                {
                    "status": "open",
                    "direction": direction,
                    "entry_price": entry,
                    "entry_qty": int(fill.quantity),
                    "stop": stop,
                    "target": target,
                }
            )
            state["current_leg_open"] = True
            state["awaiting_entry"] = False
            state["active_trade_id"] = fill.trade_id
            self._commit_state(state)
            return StrategyActions(self._exit_orders(fill.trade_id, direction, state), [], [], [], [])

        if role in {"stop", "target", "eod_close", "eod", "flatten"}:
            trade["status"] = "closed"
            state["current_leg_open"] = False
            state["awaiting_entry"] = False
            state["active_trade_id"] = ""
            self._commit_state(state)
            return StrategyActions([], self._cancel_reduce(context, fill.trade_id), [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _entry_intent(self, ph: Dict[str, Any], ts: str, state: Dict[str, Any]) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 1)
        if qty <= 0:
            return None
        fade_side = str(ph.get("fade_side") or "").lower()
        if fade_side not in {"buy", "sell"}:
            return None
        trade_id = new_id("trade")
        state.setdefault("trades", {})[trade_id] = {
            "status": "armed",
            "source_trade_id": ph.get("source_trade_id"),
            "source_exit_reason": ph.get("source_exit_reason"),
            "trigger_price": float(ph["trigger_price"]),
            "fade_side": fade_side,
        }
        state["active_trade_id"] = trade_id
        state["awaiting_entry"] = True
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=fade_side,
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=False,
            bracket_role="entry",
            live_after_ts=ts,
        )

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = float(trade["stop"])
        target = float(trade["target"])
        qty = int(trade.get("entry_qty") or 1)
        exit_side = "sell" if direction == "Long" else "buy"
        return [
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
            ),
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=qty,
                limit_price=target,
                reason="target",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
            ),
        ]

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.trade_id == trade_id and order.reduce_only:
                out.append(
                    CancelIntent(
                        cancel_id=new_id("cancel"),
                        strategy_id=self.instance.strategy_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        broker_order_id=order.broker_order_id,
                        intent_id=order.intent_id,
                        reason="fade_flat",
                    )
                )
        return out

    def _state(self) -> Dict[str, Any]:
        if not self.state:
            self.state = {
                "phantom_idx": 0,
                "current_leg_open": False,
                "awaiting_entry": False,
                "active_trade_id": "",
                "trades": {},
            }
        return self.state

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()
