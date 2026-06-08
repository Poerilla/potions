from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models import Alert, Bar, CancelIntent, ModifyIntent, OrderIntent, StrategyActions
from .atr_supertrend_dca import _supertrend
from .base import StrategyContext, StrategyPlugin


class MonthlyOrbOverlapStRetestStrategy(StrategyPlugin):
    """Broker-like 4h replay for the overlap-range daily-ST retest branch.

    This is intentionally the deployable subset of the research artifact:
    long-only, breakout-only, max two active primary packages, confirmed daily
    Supertrend filter, and one 5-contract daily-ST retest limit add per runner.
    """

    strategy_type = "monthly_orb_overlap_st_retest"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "daily_bars_path": "",
            "or_sessions": 3,
            "max_attempts_per_cluster": 2,
            "max_concurrent_trades": 2,
            "close_stop_frac": 0.25,
            "retest_qty": 5,
            "atr_len": 14,
            "atr_mult": 3.0,
            "daily_close_4h_ts": [],
            "record_levels": False,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._daily_bars = self._load_daily_bars()
        self._ranges = self._monthly_ranges(self._daily_bars)
        self._st_by_day = self._confirmed_daily_supertrend(self._daily_bars)
        self._daily_close_ts = {str(ts) for ts in self.config.get("daily_close_4h_ts", [])}
        if not self._daily_close_ts:
            try:
                self.store.add_alert(
                    Alert.create(
                        self.instance.strategy_id,
                        "warning",
                        "monthly_orb_overlap_st_retest started with empty daily_close_4h_ts; "
                        "daily-close range-exits will never fire until this list is populated.",
                    )
                )
            except Exception:
                pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "4H" or not bar.complete:
            return StrategyActions.empty()

        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []
        alerts: List[Alert] = []

        day = _day_key(bar.ts)
        self._activate_ranges(state, day)
        cluster = state.get("active_cluster")
        st_stop, st_bullish = self._st_by_day.get(day, (None, False))

        if cluster is not None:
            modifies.extend(self._maybe_extend_targets(state, context, cluster, bar))

        daily_orders, daily_cancels = self._daily_close_exits(state, context, bar)
        orders.extend(daily_orders)
        cancels.extend(daily_cancels)
        retest_orders, retest_cancels = self._retest_close_exits(state, context, bar, st_stop)
        orders.extend(retest_orders)
        cancels.extend(retest_cancels)

        if st_bullish and st_stop is not None:
            retest_actions = self._manage_retest_limits(state, context, bar, st_stop)
            orders.extend(retest_actions[0])
            cancels.extend(retest_actions[1])
            modifies.extend(retest_actions[2])
        else:
            cancels.extend(self._cancel_pending_retests(state, context, "daily_st_not_bullish"))

        primary_actions = self._manage_primary_breakout(state, context, bar, st_bullish)
        orders.extend(primary_actions[0])
        cancels.extend(primary_actions[1])

        state["last_bar_ts"] = bar.ts
        self.state = state
        self.save_state()
        if orders:
            alerts.append(Alert.create(self.instance.strategy_id, "order_submitted", "Monthly overlap ST-retest intents created"))
        return StrategyActions(orders, cancels, modifies, [], alerts)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        orders: List[OrderIntent] = []
        trade = state["trades"].get(fill.trade_id)
        if trade is None:
            parent_id = self._parent_from_retest(fill.trade_id)
            if parent_id and parent_id in state["trades"]:
                trade = self._new_retest_trade(state, parent_id, fill.trade_id)
            else:
                self.state = state
                self.save_state()
                return StrategyActions.empty()

        if trade.get("kind") == "primary":
            orders.extend(self._on_primary_fill(state, trade, fill))
        elif trade.get("kind") == "retest":
            orders.extend(self._on_retest_fill(state, trade, fill))

        self.state = state
        self.save_state()
        return StrategyActions(orders, [], [], [], [])

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("range_idx", 0)
        state.setdefault("next_cluster_id", 1)
        state.setdefault("active_cluster", None)
        state.setdefault("attempts_by_cluster", {})
        state.setdefault("trade_seq", 0)
        state.setdefault("trades", {})
        state.setdefault("last_bar_ts", "")
        return state

    def _load_daily_bars(self) -> List[Bar]:
        raw_path = str(self.config.get("daily_bars_path") or "")
        path = Path(raw_path)
        if raw_path and not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / raw_path
        if not path.exists():
            return []
        out: List[Bar] = []
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                out.append(
                    Bar(
                        instrument=self.instance.instrument,
                        timeframe="D",
                        ts=str(row.get("date") or row.get("ts")),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                        complete=True,
                        source=str(path),
                    )
                )
        out.sort(key=lambda b: b.ts)
        return out

    def _monthly_ranges(self, daily_bars: List[Bar]) -> List[Dict[str, Any]]:
        months: Dict[str, List[Bar]] = {}
        for bar in daily_bars:
            months.setdefault(_day_key(bar.ts)[:7], []).append(bar)
        ranges: List[Dict[str, Any]] = []
        for period in sorted(months):
            bars = sorted(months[period], key=lambda b: b.ts)
            if len(bars) < int(self.config["or_sessions"]) + 1:
                continue
            rb = bars[: int(self.config["or_sessions"])]
            ranges.append(
                {
                    "period": period,
                    "start_date": _day_key(bars[0].ts),
                    "complete_date": _day_key(rb[-1].ts),
                    "activation_date": _day_key(bars[int(self.config["or_sessions"])].ts),
                    "end_date": _day_key(bars[-1].ts),
                    "high": max(b.high for b in rb),
                    "low": min(b.low for b in rb),
                }
            )
        return ranges

    def _confirmed_daily_supertrend(self, daily_bars: List[Bar]) -> Dict[str, Tuple[Optional[float], bool]]:
        points = _supertrend(daily_bars, int(self.config["atr_len"]), float(self.config["atr_mult"]))
        by_ts = {p.ts[:10]: p for p in points}
        out: Dict[str, Tuple[Optional[float], bool]] = {}
        previous = None
        for bar in daily_bars:
            day = _day_key(bar.ts)
            out[day] = (previous.stop, previous.bullish) if previous is not None else (None, False)
            previous = by_ts.get(day, previous)
        return out

    def _activate_ranges(self, state: Dict[str, Any], day: str) -> None:
        idx = int(state.get("range_idx", 0))
        while idx < len(self._ranges) and day >= self._ranges[idx]["activation_date"]:
            current = self._ranges[idx]
            previous = self._ranges[idx - 1] if idx else None
            cluster = state.get("active_cluster")
            if cluster is not None and _overlap(cluster["high"], cluster["low"], current["high"], current["low"]):
                cluster["end_period"] = current["period"]
                cluster["end_date"] = current["end_date"]
                cluster["high"] = max(float(cluster["high"]), float(current["high"]))
                cluster["low"] = min(float(cluster["low"]), float(current["low"]))
                if current["period"] not in cluster["months"]:
                    cluster["months"].append(current["period"])
                state["active_cluster"] = cluster
            else:
                state["active_cluster"] = None
                if previous is not None and _overlap(previous["high"], previous["low"], current["high"], current["low"]):
                    cluster_id = int(state.get("next_cluster_id", 1))
                    state["next_cluster_id"] = cluster_id + 1
                    cluster = {
                        "cluster_id": cluster_id,
                        "start_period": previous["period"],
                        "end_period": current["period"],
                        "start_date": current["activation_date"],
                        "end_date": current["end_date"],
                        "high": max(float(previous["high"]), float(current["high"])),
                        "low": min(float(previous["low"]), float(current["low"])),
                        "months": [previous["period"], current["period"]],
                    }
                    state["active_cluster"] = cluster
                    state["attempts_by_cluster"].setdefault(str(cluster_id), 0)
            idx += 1
        state["range_idx"] = idx

    def _manage_primary_breakout(
        self,
        state: Dict[str, Any],
        context: StrategyContext,
        bar: Bar,
        st_bullish: bool,
    ) -> Tuple[List[OrderIntent], List[CancelIntent]]:
        cluster = state.get("active_cluster")
        if cluster is None:
            return [], self._cancel_pending_primaries(state, context, "no_active_overlap_cluster")
        if not st_bullish:
            return [], self._cancel_pending_primaries(state, context, "daily_st_filter_bearish")
        cluster_id = str(cluster["cluster_id"])
        attempts = int(state["attempts_by_cluster"].get(cluster_id, 0))
        if attempts >= int(self.config["max_attempts_per_cluster"]):
            return [], []
        if self._pending_primary_for_cluster(state, cluster_id):
            return [], []
        if self._primary_active_count(state) >= int(self.config["max_concurrent_trades"]):
            return [], []

        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        trade_id = "%s_%s_%03d" % (self.instance.strategy_id, str(bar.ts)[:10].replace("-", ""), state["trade_seq"])
        high = float(cluster["high"])
        low = float(cluster["low"])
        rng = high - low
        state["trades"][trade_id] = {
            "kind": "primary",
            "status": "pending",
            "cluster_id": int(cluster["cluster_id"]),
            "cluster_key": cluster_id,
            "months": "+".join(cluster.get("months", [])),
            "range_high": high,
            "range_low": low,
            "range_size": rng,
            "tp50": high + 0.5 * rng,
            "tp1": high + rng,
            "tp2": high + 2.0 * rng,
            "entry_fills_seen": 0,
            "primary_open_qty": 0,
            "runner_open": False,
            "tp1_hit": False,
            "attempt_counted": False,
            "extension_used": False,
            "retest_trade_id": "",
            "retest_done": False,
        }
        orders = [
            self._entry_stop(trade_id, high, "entry", bar.ts),
            self._entry_stop(trade_id, high, "entry", bar.ts),
            self._entry_stop(trade_id, high, "runner_entry", bar.ts),
        ]
        return orders, []

    def _manage_retest_limits(
        self,
        state: Dict[str, Any],
        context: StrategyContext,
        bar: Bar,
        st_stop: float,
    ) -> Tuple[List[OrderIntent], List[CancelIntent], List[ModifyIntent]]:
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []
        for trade_id, trade in list(state["trades"].items()):
            if trade.get("kind") != "primary" or not trade.get("runner_open") or trade.get("retest_done"):
                continue
            retest_id = str(trade.get("retest_trade_id") or "")
            if retest_id and self._trade_open_or_pending(state, retest_id):
                for order in context.strategy_open_orders:
                    if order.trade_id == retest_id and not order.reduce_only and order.order_type == "limit":
                        if order.limit_price is None or abs(order.limit_price - st_stop) > 1e-9:
                            modifies.append(ModifyIntent(self.instance.strategy_id, order.broker_order_id, "move_daily_st_retest_limit", limit_price=st_stop))
                continue
            if retest_id and state["trades"].get(retest_id, {}).get("status") == "closed":
                continue
            retest_id = "%s_retest" % trade_id
            trade["retest_trade_id"] = retest_id
            self._new_retest_trade(state, trade_id, retest_id)
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=retest_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side="buy",
                    order_type="limit",
                    quantity=int(self.config["retest_qty"]),
                    limit_price=st_stop,
                    reason="daily_st_limit_retest_scalein",
                    requires_verification=True,
                    bracket_role="entry",
                    live_after_ts=bar.ts,
                )
            )
        return orders, cancels, modifies

    def _daily_close_exits(
        self,
        state: Dict[str, Any],
        context: StrategyContext,
        bar: Bar,
    ) -> Tuple[List[OrderIntent], List[CancelIntent]]:
        if bar.ts not in self._daily_close_ts:
            return [], []
        out: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        for trade_id, trade in list(state["trades"].items()):
            if trade.get("kind") != "primary" or int(trade.get("primary_open_qty", 0)) <= 0:
                continue
            close_line = float(trade["range_high"]) - float(self.config["close_stop_frac"]) * float(trade["range_size"])
            if bar.close <= close_line:
                trade_orders, trade_cancels = self._close_trade_orders(state, context, trade_id, bar.ts, "range_close_25pct")
                out.extend(trade_orders)
                cancels.extend(trade_cancels)
        return out, cancels

    def _retest_close_exits(
        self,
        state: Dict[str, Any],
        context: StrategyContext,
        bar: Bar,
        st_stop: Optional[float],
    ) -> Tuple[List[OrderIntent], List[CancelIntent]]:
        if st_stop is None:
            return [], []
        out: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        for trade_id, trade in list(state["trades"].items()):
            if trade.get("kind") == "retest" and int(trade.get("open_qty", 0)) > 0 and bar.close < st_stop:
                out.extend(self._close_specific_trade(context, trade_id, int(trade["open_qty"]), bar.ts, "st_close"))
                cancels.extend(self._cancel_reduce_orders_for_trade(context, trade_id, "st_close_cancel_targets"))
        return out, cancels

    def _maybe_extend_targets(
        self,
        state: Dict[str, Any],
        context: StrategyContext,
        cluster: Dict[str, Any],
        bar: Bar,
    ) -> List[ModifyIntent]:
        modifies: List[ModifyIntent] = []
        high = float(cluster["high"])
        low = float(cluster["low"])
        rng = high - low
        for trade_id, trade in state["trades"].items():
            if trade.get("kind") != "primary" or int(trade.get("cluster_id", -1)) != int(cluster["cluster_id"]):
                continue
            if trade.get("extension_used") or int(trade.get("primary_open_qty", 0)) <= 0:
                continue
            if high <= float(trade["range_high"]) or bar.close <= high:
                continue
            trade["range_high"] = high
            trade["range_low"] = low
            trade["range_size"] = rng
            trade["tp50"] = high + 0.5 * rng
            trade["tp1"] = high + rng
            trade["tp2"] = high + 2.0 * rng
            trade["extension_used"] = True
            for order in context.strategy_open_orders:
                if order.trade_id == trade_id and order.reduce_only:
                    target = None
                    if order.bracket_role == "tp50":
                        target = float(trade["tp50"])
                    elif order.bracket_role == "tp1":
                        target = float(trade["tp1"])
                    elif order.bracket_role == "runner_target":
                        target = float(trade["tp2"])
                    if target is not None:
                        modifies.append(ModifyIntent(self.instance.strategy_id, order.broker_order_id, "extend_overlap_target", limit_price=target))
                retest_id = str(trade.get("retest_trade_id") or "")
                if retest_id and order.trade_id == retest_id and order.reduce_only and order.bracket_role == "retest_target":
                    modifies.append(ModifyIntent(self.instance.strategy_id, order.broker_order_id, "extend_retest_target", limit_price=float(trade["tp2"])))
        return modifies

    def _on_primary_fill(self, state: Dict[str, Any], trade: Dict[str, Any], fill) -> List[OrderIntent]:
        orders: List[OrderIntent] = []
        trade["status"] = "open"
        if not trade.get("attempt_counted"):
            key = str(trade["cluster_id"])
            state["attempts_by_cluster"][key] = int(state["attempts_by_cluster"].get(key, 0)) + 1
            trade["attempt_counted"] = True
        if fill.reason == "entry" and fill.side == "buy":
            trade["entry_fills_seen"] = int(trade.get("entry_fills_seen", 0)) + fill.quantity
            trade["primary_open_qty"] = int(trade.get("primary_open_qty", 0)) + fill.quantity
            target_role = "tp50" if int(trade.get("entry_fills_seen", 0)) <= 1 else "tp1"
            target_price = float(trade[target_role])
            orders.append(self._target_order(fill.trade_id, fill.quantity, target_price, target_role, fill.ts))
        elif fill.reason == "runner_entry" and fill.side == "buy":
            trade["primary_open_qty"] = int(trade.get("primary_open_qty", 0)) + fill.quantity
            trade["runner_open"] = True
            orders.append(self._target_order(fill.trade_id, fill.quantity, float(trade["tp2"]), "runner_target", fill.ts))
        elif fill.side == "sell":
            trade["primary_open_qty"] = max(int(trade.get("primary_open_qty", 0)) - fill.quantity, 0)
            if fill.reason == "tp1":
                trade["tp1_hit"] = True
            if fill.reason in {"runner_target", "range_close_25pct", "month_end"}:
                trade["runner_open"] = False
            if int(trade["primary_open_qty"]) <= 0:
                trade["status"] = "closed"
                trade["runner_open"] = False
        return orders

    def _on_retest_fill(self, state: Dict[str, Any], trade: Dict[str, Any], fill) -> List[OrderIntent]:
        orders: List[OrderIntent] = []
        parent = state["trades"].get(str(trade.get("parent_trade_id") or ""))
        if fill.side == "buy" and fill.reason == "entry":
            trade["status"] = "open"
            trade["open_qty"] = int(trade.get("open_qty", 0)) + fill.quantity
            target = float(parent["tp2"]) if parent is not None else fill.price
            orders.append(self._target_order(fill.trade_id, fill.quantity, target, "retest_target", fill.ts))
        elif fill.side == "sell":
            trade["open_qty"] = max(int(trade.get("open_qty", 0)) - fill.quantity, 0)
            if int(trade["open_qty"]) <= 0:
                trade["status"] = "closed"
                if parent is not None:
                    parent["retest_done"] = True
        return orders

    def _close_trade_orders(
        self,
        state: Dict[str, Any],
        context: StrategyContext,
        trade_id: str,
        ts: str,
        reason: str,
    ) -> Tuple[List[OrderIntent], List[CancelIntent]]:
        out: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        trade = state["trades"].get(trade_id)
        if trade is None:
            return out, cancels
        qty = int(trade.get("primary_open_qty", 0))
        out.extend(self._close_specific_trade(context, trade_id, qty, ts, reason))
        cancels.extend(self._cancel_reduce_orders_for_trade(context, trade_id, "%s_cancel_targets" % reason))
        retest_id = str(trade.get("retest_trade_id") or "")
        retest = state["trades"].get(retest_id)
        if retest is not None and int(retest.get("open_qty", 0)) > 0:
            out.extend(self._close_specific_trade(context, retest_id, int(retest["open_qty"]), ts, reason))
            cancels.extend(self._cancel_reduce_orders_for_trade(context, retest_id, "%s_cancel_retest_targets" % reason))
        return out, cancels

    def _close_specific_trade(self, context: StrategyContext, trade_id: str, qty: int, ts: str, reason: str) -> List[OrderIntent]:
        if qty <= 0:
            return []
        return [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side="sell",
                order_type="market_close",
                quantity=qty,
                reason=reason,
                requires_verification=False,
                reduce_only=True,
                bracket_role=reason,
                live_after_ts=ts,
            )
        ]

    def _cancel_reduce_orders_for_trade(self, context: StrategyContext, trade_id: str, reason: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, reason)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _new_retest_trade(self, state: Dict[str, Any], parent_id: str, retest_id: str) -> Dict[str, Any]:
        trade = state["trades"].get(retest_id)
        if trade is None:
            trade = {
                "kind": "retest",
                "status": "pending",
                "parent_trade_id": parent_id,
                "open_qty": 0,
            }
            state["trades"][retest_id] = trade
        return trade

    def _entry_stop(self, trade_id: str, price: float, role: str, ts: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy",
            order_type="stop",
            quantity=1,
            stop_price=price,
            reason="overlap_breakout_stop",
            requires_verification=True,
            bracket_role=role,
            live_after_ts=ts,
        )

    def _target_order(self, trade_id: str, qty: int, price: float, role: str, ts: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell",
            order_type="limit",
            quantity=qty,
            limit_price=price,
            reason=role,
            requires_verification=False,
            reduce_only=True,
            bracket_role=role,
            live_after_ts=ts,
        )

    def _pending_primary_for_cluster(self, state: Dict[str, Any], cluster_key: str) -> bool:
        for trade in state["trades"].values():
            if trade.get("kind") == "primary" and str(trade.get("cluster_id")) == cluster_key and trade.get("status") in {"pending", "open"}:
                return True
        return False

    def _primary_active_count(self, state: Dict[str, Any]) -> int:
        return sum(
            1
            for trade in state["trades"].values()
            if trade.get("kind") == "primary" and trade.get("status") in {"pending", "open"}
        )

    def _trade_open_or_pending(self, state: Dict[str, Any], trade_id: str) -> bool:
        trade = state["trades"].get(trade_id)
        return trade is not None and trade.get("status") in {"pending", "open"}

    def _cancel_pending_primaries(self, state: Dict[str, Any], context: StrategyContext, reason: str) -> List[CancelIntent]:
        pending = {
            trade_id
            for trade_id, trade in state["trades"].items()
            if trade.get("kind") == "primary" and trade.get("status") == "pending"
        }
        cancels = [CancelIntent(self.instance.strategy_id, order.broker_order_id, reason) for order in context.strategy_open_orders if order.trade_id in pending and not order.reduce_only]
        if cancels:
            for trade_id in pending:
                state["trades"][trade_id]["status"] = "cancelled"
        return cancels

    def _cancel_pending_retests(self, state: Dict[str, Any], context: StrategyContext, reason: str) -> List[CancelIntent]:
        pending = {
            trade_id
            for trade_id, trade in state["trades"].items()
            if trade.get("kind") == "retest" and trade.get("status") == "pending"
        }
        cancels = [CancelIntent(self.instance.strategy_id, order.broker_order_id, reason) for order in context.strategy_open_orders if order.trade_id in pending and not order.reduce_only]
        if cancels:
            for trade_id in pending:
                state["trades"][trade_id]["status"] = "cancelled"
                parent_id = str(state["trades"][trade_id].get("parent_trade_id") or "")
                if parent_id in state["trades"]:
                    state["trades"][parent_id]["retest_trade_id"] = ""
        return cancels

    def _parent_from_retest(self, trade_id: str) -> str:
        return trade_id[: -len("_retest")] if trade_id.endswith("_retest") else ""


def _parse_date(ts: str) -> date:
    text = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text[:10]).date()


def _day_key(ts: str) -> str:
    return _parse_date(ts).isoformat()


def _overlap(high1: float, low1: float, high2: float, low2: float) -> bool:
    return max(low1, low2) <= min(high1, high2)
