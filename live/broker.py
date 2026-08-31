from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pytz

from .models import (
    Bar,
    BrokerOrder,
    Fill,
    OrderIntent,
    Position,
    as_row,
    new_id,
    parse_float,
    parse_int,
    utc_now_iso,
)
from .directional_path import pessimistic_limit_fill_allowed
from .entry_gap import entry_limit_gap_blocked, session_gap as _session_gap
from .spread_model import SpreadModel
from .store import FlatFileStore


DEFAULT_TICK_SIZE: Dict[str, float] = {
    "NQ": 0.25,
    "MNQ": 0.25,
    "ES": 0.25,
    "MES": 0.25,
    "YM": 1.0,
    "MYM": 1.0,
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "USDJPY": 0.001,
    "AUDJPY": 0.001,
    "XAUUSD": 0.01,
    "XAGUSD": 0.001,
}


_FILL_PRIORITY: Dict[str, int] = {
    "market": 0,
    "stop": 1,
    "limit": 2,
    "market_close": 3,
}


class BaseBroker(ABC):
    @abstractmethod
    def get_active_contract(self, instrument: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_bars(self, instrument: str, timeframe: str, limit: int = 500) -> List[Bar]:
        raise NotImplementedError

    @abstractmethod
    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        raise NotImplementedError

    @abstractmethod
    def modify_order(
        self,
        broker_order_id: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reason: str = "",
        bracket_stop_price: Optional[float] = None,
        bracket_target_price: Optional[float] = None,
        live_after_ts: Optional[str] = None,
    ) -> BrokerOrder:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str, reason: str = "") -> BrokerOrder:
        raise NotImplementedError

    @abstractmethod
    def reconcile_orders(self) -> List[BrokerOrder]:
        raise NotImplementedError

    @abstractmethod
    def reconcile_positions(self) -> List[Position]:
        raise NotImplementedError

    @abstractmethod
    def attach_bracket(self, parent_order: BrokerOrder, intent: OrderIntent) -> List[BrokerOrder]:
        raise NotImplementedError


class PaperBroker(BaseBroker):
    """Paper broker that fills resting orders against completed OHLC bars.

    Realism knobs:
    - ``slippage_ticks``: adverse ticks applied to market and stop fills (limits
      never slip beyond their limit price). Default ``0`` keeps legacy
      behaviour; replay drivers should set ``1`` for futures realism.
    - ``tick_size``: per-instrument tick size lookup overriding
      :data:`DEFAULT_TICK_SIZE`.
    - ``strict_moc``: if True, ``market_close`` orders only fill on a bar whose
      timestamp matches ``order.live_after_ts`` (prevents accidental same-bar
      lookahead from intraday strategies). Daily strategies are unaffected.
    - ``spread_model``: optional synthetic half-spread overlay for last-sale OHLC.
    - ``directional_adverse_path``: when True, block limit fills that would be
      unreachable on the conservative open->extreme path when a paired stop
      would trigger first.
    """

    def __init__(
        self,
        store: FlatFileStore,
        slippage_ticks: float = 0.0,
        tick_size: Optional[Dict[str, float]] = None,
        strict_moc: bool = False,
        spread_model: Optional[SpreadModel] = None,
        directional_adverse_path: bool = True,
        log_events: bool = True,
        persist_modifications: bool = True,
    ):
        self.store = store
        self.store.ensure()
        self.slippage_ticks = float(slippage_ticks)
        self.tick_size: Dict[str, float] = dict(DEFAULT_TICK_SIZE)
        if tick_size:
            self.tick_size.update({k.upper(): float(v)
                                  for k, v in tick_size.items()})
        self.strict_moc = bool(strict_moc)
        self.spread_model = spread_model
        self.directional_adverse_path = bool(directional_adverse_path)
        self.log_events = bool(log_events)
        self.persist_modifications = bool(persist_modifications)
        self._orders_cache: Dict[str, BrokerOrder] = {
            order.broker_order_id: order for order in self.store.load_orders()}
        self._intents_cache: Dict[str, OrderIntent] = {
            intent.intent_id: intent for intent in self.store.load_order_intents()}
        self._positions_cache: Dict[str, Position] = {
            pos.position_id: pos for pos in self.store.load_positions()}
        self._active_order_ids = {
            order.broker_order_id: True
            for order in self._orders_cache.values()
            if order.status in {"submitted", "partially_filled"}
        }
        self._last_bar_close: Dict[str, float] = {}
        self._last_bar_ts: Dict[str, str] = {}

    def get_active_contract(self, instrument: str) -> str:
        return instrument

    def get_bars(self, instrument: str, timeframe: str, limit: int = 500) -> List[Bar]:
        bars = self.store.read_bars(instrument, timeframe)
        return bars[-limit:]

    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        intent = replace(intent, status="submitted", updated_at=utc_now_iso())
        order = BrokerOrder.from_intent(intent)
        self._intents_cache[intent.intent_id] = intent
        self._orders_cache[order.broker_order_id] = order
        self._active_order_ids[order.broker_order_id] = True
        self.store.upsert_row("order_intents", "intent_id", dict(
            as_row(intent), status="submitted"))
        self.store.upsert_row("orders", "broker_order_id", as_row(order))
        if self.log_events:
            self.store.append_event(
                "broker_actions", {"event": "submit", **as_row(order)})
        return order

    def modify_order(
        self,
        broker_order_id: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reason: str = "",
        bracket_stop_price: Optional[float] = None,
        bracket_target_price: Optional[float] = None,
        live_after_ts: Optional[str] = None,
    ) -> BrokerOrder:
        order = self._get_order(broker_order_id)
        if order.status not in {"submitted", "partially_filled"}:
            raise ValueError("Cannot modify order %s in status %s" %
                             (broker_order_id, order.status))
        updated = replace(
            order,
            limit_price=limit_price if limit_price is not None else order.limit_price,
            stop_price=stop_price if stop_price is not None else order.stop_price,
            live_after_ts=live_after_ts if live_after_ts is not None else order.live_after_ts,
            updated_at=utc_now_iso(),
        )
        self._orders_cache[updated.broker_order_id] = updated
        self._active_order_ids[updated.broker_order_id] = True
        intent = self._intents_cache.get(updated.intent_id)
        if intent is not None and (bracket_stop_price is not None or bracket_target_price is not None):
            intent = replace(
                intent,
                bracket_stop_price=bracket_stop_price if bracket_stop_price is not None else intent.bracket_stop_price,
                bracket_target_price=bracket_target_price if bracket_target_price is not None else intent.bracket_target_price,
                live_after_ts=live_after_ts if live_after_ts is not None else intent.live_after_ts,
                updated_at=utc_now_iso(),
            )
            self._intents_cache[intent.intent_id] = intent
            if self.persist_modifications:
                self.store.upsert_row("order_intents", "intent_id", dict(
                    as_row(intent), status="submitted"))
        if self.persist_modifications:
            self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        if self.log_events:
            self.store.append_event(
                "broker_actions",
                {"event": "modify", "reason": reason, **as_row(updated)},
            )
        return updated

    def cancel_order(self, broker_order_id: str, reason: str = "") -> BrokerOrder:
        order = self._get_order(broker_order_id)
        if order.status in {"filled", "cancelled"}:
            return order
        updated = replace(order, status="cancelled", updated_at=utc_now_iso())
        self._orders_cache[updated.broker_order_id] = updated
        self._active_order_ids.pop(updated.broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        if self.log_events:
            self.store.append_event(
                "broker_actions",
                {"event": "cancel", "reason": reason, **as_row(updated)},
            )
        return updated

    def reconcile_orders(self) -> List[BrokerOrder]:
        return [self._orders_cache[order_id] for order_id in self._active_order_ids]

    def reconcile_positions(self) -> List[Position]:
        return list(self._positions_cache.values())

    def attach_bracket(self, parent_order: BrokerOrder, intent: OrderIntent) -> List[BrokerOrder]:
        if parent_order.status != "filled":
            return []
        children: List[BrokerOrder] = []
        oco = intent.oco_group or ("%s_bracket" % parent_order.broker_order_id)
        exit_side = "sell" if parent_order.side == "buy" else "buy"
        if intent.bracket_stop_price is not None:
            stop_intent = OrderIntent.create(
                strategy_id=parent_order.strategy_id,
                trade_id=parent_order.trade_id,
                instrument=parent_order.instrument,
                account_mode=parent_order.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=parent_order.quantity,
                stop_price=intent.bracket_stop_price,
                reason="protective_stop",
                requires_verification=False,
                parent_intent_id=intent.intent_id,
                reduce_only=True,
                bracket_role=(
                    "runner_stop"
                    if str(intent.bracket_role or "").startswith("runner_entry")
                    else "stop"
                ),
                oco_group=oco,
            )
            stop_intent = replace(
                stop_intent, status="submitted", updated_at=utc_now_iso())
            stop_order = BrokerOrder.from_intent(stop_intent)
            stop_order = replace(
                stop_order, parent_order_id=parent_order.broker_order_id)
            self._intents_cache[stop_intent.intent_id] = stop_intent
            self._orders_cache[stop_order.broker_order_id] = stop_order
            self._active_order_ids[stop_order.broker_order_id] = True
            self.store.upsert_row("order_intents", "intent_id", dict(
                as_row(stop_intent), status="submitted"))
            self.store.upsert_row(
                "orders", "broker_order_id", as_row(stop_order))
            children.append(stop_order)
        if intent.bracket_target_price is not None:
            target_intent = OrderIntent.create(
                strategy_id=parent_order.strategy_id,
                trade_id=parent_order.trade_id,
                instrument=parent_order.instrument,
                account_mode=parent_order.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=parent_order.quantity,
                limit_price=intent.bracket_target_price,
                reason="target",
                requires_verification=False,
                parent_intent_id=intent.intent_id,
                reduce_only=True,
                bracket_role="target",
                oco_group=oco,
            )
            target_intent = replace(
                target_intent, status="submitted", updated_at=utc_now_iso())
            target_order = BrokerOrder.from_intent(target_intent)
            target_order = replace(
                target_order, parent_order_id=parent_order.broker_order_id)
            self._intents_cache[target_intent.intent_id] = target_intent
            self._orders_cache[target_order.broker_order_id] = target_order
            self._active_order_ids[target_order.broker_order_id] = True
            self.store.upsert_row("order_intents", "intent_id", dict(
                as_row(target_intent), status="submitted"))
            self.store.upsert_row(
                "orders", "broker_order_id", as_row(target_order))
            children.append(target_order)
        if children:
            if self.log_events:
                self.store.append_event(
                    "broker_actions",
                    {
                        "event": "attach_bracket",
                        "parent_order_id": parent_order.broker_order_id,
                        "child_order_ids": ",".join(o.broker_order_id for o in children),
                        "ts": utc_now_iso(),
                    },
                )
        return children

    def process_bar(self, bar: Bar) -> List[Fill]:
        """Fill eligible submitted orders against one completed bar.

        Call this before strategy evaluation for the same bar to prevent
        same-confirmation-bar fills.
        """
        return self._process_bar(bar, market_close_only=False)

    def process_market_close_bar(self, bar: Bar) -> List[Fill]:
        """Fill market-close orders at the current bar close.

        This is used by broker-like replays to model scheduled end-of-month
        15:59 flattening on daily bars. Normal market orders still fill at the
        next tradable bar open.
        """
        return self._process_bar(bar, market_close_only=True)

    def _process_bar(self, bar: Bar, market_close_only: bool = False) -> List[Fill]:
        fills: List[Fill] = []
        cancelled_in_bar = set()
        ordered_ids = self._priority_sorted_active_ids()
        for order_id in ordered_ids:
            if order_id not in self._active_order_ids:
                continue
            order = self._orders_cache[order_id]
            if order.broker_order_id in cancelled_in_bar:
                continue
            if order.instrument != bar.instrument:
                continue
            if order.status != "submitted":
                continue
            if market_close_only:
                if order.order_type != "market_close":
                    continue
                if order.live_after_ts and _ts_before(bar.ts, order.live_after_ts):
                    continue
                if self.strict_moc and order.live_after_ts and str(bar.ts) != str(order.live_after_ts):
                    continue
            else:
                if order.order_type == "market_close":
                    continue
                if order.live_after_ts and not _ts_after(bar.ts, order.live_after_ts):
                    continue
            if order.expires_after_ts and _ts_after(bar.ts, order.expires_after_ts):
                self.cancel_order(order.broker_order_id,
                                  reason="expired_before_bar")
                continue
            fill_qty = order.remaining_quantity
            if order.reduce_only:
                pos_qty = self._position_qty(
                    order.strategy_id, order.instrument, order.account_mode)
                if pos_qty == 0:
                    self.cancel_order(order.broker_order_id,
                                      reason="reduce_only_no_position")
                    continue
                if order.side == "sell" and pos_qty <= 0:
                    self.cancel_order(order.broker_order_id,
                                      reason="reduce_only_wrong_side")
                    continue
                if order.side == "buy" and pos_qty >= 0:
                    self.cancel_order(order.broker_order_id,
                                      reason="reduce_only_wrong_side")
                    continue
                fill_qty = min(order.remaining_quantity, abs(pos_qty))
            pos_qty = self._position_qty(
                order.strategy_id, order.instrument, order.account_mode)
            if not self._directional_fill_allowed(order, bar, pos_qty):
                continue
            price = self._fill_price(order, bar)
            if price is None:
                continue
            fill = self._fill_order(
                order, price, bar.ts, fill_qty=fill_qty, bar=bar)
            fills.append(fill)
            order_after_fill = self._get_order(order.broker_order_id)
            intent = self._get_intent(order.intent_id)
            if not order_after_fill.reduce_only:
                self.attach_bracket(order_after_fill, intent)
            if order_after_fill.oco_group:
                cancelled_in_bar.update(
                    self._cancel_oco_peers(order_after_fill))
        self._last_bar_close[bar.instrument] = float(bar.close)
        self._last_bar_ts[bar.instrument] = str(bar.ts)
        return fills

    def _priority_sorted_active_ids(self) -> List[str]:
        """Stable sort of active orders so stops are evaluated before limits
        within the same bar. This makes same-bar stop+target ambiguity
        deterministically pessimistic for protective exits.
        """

        snapshot = list(self._active_order_ids)
        return sorted(
            snapshot,
            key=lambda oid: (
                _FILL_PRIORITY.get(self._orders_cache[oid].order_type, 9),
                self._orders_cache[oid].created_at or "",
                oid,
            ),
        )

    def _fill_price(self, order: BrokerOrder, bar: Bar) -> Optional[float]:
        base = self._base_fill_price(order, bar)
        if base is None:
            return None
        # Real bid/ask on the bar already encodes spread — do not double-apply SpreadModel.
        if self.spread_model is not None and not bar.has_quote_book() and order.order_type in {"market", "market_close", "stop", "limit"}:
            tick = self.tick_size.get(order.instrument.upper(), 0.25)
            model = SpreadModel(
                tick_size=tick,
                rth_half_spread_ticks=self.spread_model.rth_half_spread_ticks,
                eth_half_spread_ticks=self.spread_model.eth_half_spread_ticks,
                open_widen_half_spread_ticks=self.spread_model.open_widen_half_spread_ticks,
                low_volume_threshold=self.spread_model.low_volume_threshold,
                low_volume_multiplier=self.spread_model.low_volume_multiplier,
            )
            base = model.adjust_fill_price(order.side, base, bar)
        if order.order_type in {"market", "market_close", "stop"} and self.slippage_ticks > 0:
            tick = self.tick_size.get(order.instrument.upper(), 0.25)
            slip = self.slippage_ticks * tick
            if order.side == "buy":
                return base + slip
            return base - slip
        return base

    def _base_fill_price(self, order: BrokerOrder, bar: Bar) -> Optional[float]:
        quotes = bar.has_quote_book()
        if order.order_type == "market":
            if quotes:
                return float(bar.ask_open if order.side == "buy" else bar.bid_open)
            return bar.open
        if order.order_type == "market_close":
            if quotes:
                return float(bar.ask_close if order.side == "buy" else bar.bid_close)
            return bar.close
        if order.order_type == "limit":
            if order.limit_price is None:
                return None
            if not order.reduce_only:
                intent = self._intents_cache.get(order.intent_id)
                prev_close = self._last_bar_close.get(order.instrument)
                prev_ts = self._last_bar_ts.get(order.instrument)
                stop = intent.bracket_stop_price if intent is not None else None
                if entry_limit_gap_blocked(
                    side=order.side,
                    entry=float(order.limit_price),
                    stop=stop,
                    prev_close=prev_close,
                    bar_open=float(bar.open),
                    session_gap=_session_gap(prev_ts or "", bar.ts),
                ):
                    return None
            touched = False
            if self.spread_model is not None and not quotes:
                touched = self.spread_model.limit_touch_ok(
                    order.side, bar, order.limit_price)
            elif order.side == "buy":
                touched = bar.low <= order.limit_price
            else:
                touched = bar.high >= order.limit_price
            if not touched:
                return None
            # Limit fills at the limit; with quotes, buys cannot fill above ask and sells below bid.
            if quotes:
                if order.side == "buy":
                    if float(bar.ask_low) > order.limit_price:
                        return None
                    return min(order.limit_price, float(bar.ask_close))
                if float(bar.bid_high) < order.limit_price:
                    return None
                return max(order.limit_price, float(bar.bid_close))
            return order.limit_price
        if order.order_type == "stop":
            if order.stop_price is None:
                return None
            # Trigger on mid OHLC; fill on the tradeable side (ask for buys, bid for sells).
            if order.side == "buy" and bar.high >= order.stop_price:
                if quotes:
                    return max(order.stop_price, float(bar.ask_open))
                return max(order.stop_price, bar.open)
            if order.side == "sell" and bar.low <= order.stop_price:
                if quotes:
                    return min(order.stop_price, float(bar.bid_open))
                return min(order.stop_price, bar.open)
        return None

    def _directional_fill_allowed(self, order: BrokerOrder, bar: Bar, position_qty: int) -> bool:
        if not self.directional_adverse_path or order.order_type != "limit":
            return True
        peer_stop, peer_target = self._oco_peer_prices(order)
        return pessimistic_limit_fill_allowed(
            order,
            bar,
            position_qty=position_qty,
            peer_stop_price=peer_stop,
            peer_target_price=peer_target,
        )

    def _oco_peer_prices(self, order: BrokerOrder) -> tuple[Optional[float], Optional[float]]:
        if not order.oco_group:
            return None, None
        stop_price: Optional[float] = None
        target_price: Optional[float] = None
        for peer in self._orders_cache.values():
            if peer.broker_order_id == order.broker_order_id:
                continue
            if peer.oco_group != order.oco_group:
                continue
            if peer.status not in {"submitted", "partially_filled"}:
                continue
            if peer.order_type == "stop" and peer.stop_price is not None:
                stop_price = peer.stop_price
            if peer.order_type == "limit" and peer.limit_price is not None:
                target_price = peer.limit_price
        if order.order_type == "stop" and order.stop_price is not None:
            stop_price = order.stop_price
        if order.order_type == "limit" and order.limit_price is not None:
            target_price = order.limit_price
        return stop_price, target_price

    def _fill_order(
        self,
        order: BrokerOrder,
        price: float,
        ts: str,
        fill_qty: Optional[int] = None,
        bar: Optional[Bar] = None,
    ) -> Fill:
        fill_qty = fill_qty if fill_qty is not None else order.remaining_quantity
        mid_price = float(bar.close) if bar is not None else None
        bid_price = float(
            bar.bid_close) if bar is not None and bar.bid_close is not None else None
        ask_price = float(
            bar.ask_close) if bar is not None and bar.ask_close is not None else None
        spread = None
        if bid_price is not None and ask_price is not None:
            spread = ask_price - bid_price
        fill = Fill(
            fill_id=new_id("fill"),
            broker_order_id=order.broker_order_id,
            intent_id=order.intent_id,
            strategy_id=order.strategy_id,
            trade_id=order.trade_id,
            instrument=order.instrument,
            account_mode=order.account_mode,
            side=order.side,
            quantity=fill_qty,
            price=price,
            ts=ts,
            reason=order.bracket_role or order.order_type,
            mid_price=mid_price,
            bid_price=bid_price,
            ask_price=ask_price,
            spread=spread,
        )
        remaining = max(order.remaining_quantity - fill_qty, 0)
        updated = replace(
            order,
            remaining_quantity=remaining,
            status="filled" if remaining == 0 else "partially_filled",
            updated_at=utc_now_iso(),
        )
        self._orders_cache[updated.broker_order_id] = updated
        if updated.status in {"submitted", "partially_filled"}:
            self._active_order_ids[updated.broker_order_id] = True
        else:
            self._active_order_ids.pop(updated.broker_order_id, None)
        self.store.upsert_row("orders", "broker_order_id", as_row(updated))
        self.store.append_rows("fills", [as_row(fill)])
        self._apply_fill_to_position(fill)
        if self.log_events:
            self.store.append_event("fills", as_row(fill))
        return fill

    def flush_state(self) -> None:
        self.store.write_table("order_intents", [as_row(
            intent) for intent in self._intents_cache.values()])
        self.store.write_table(
            "orders", [as_row(order) for order in self._orders_cache.values()])
        self.store.write_table("positions", [as_row(
            pos) for pos in self._positions_cache.values()])

    def _position_qty(self, strategy_id: str, instrument: str, account_mode: str) -> int:
        for pos in self._positions_cache.values():
            if pos.strategy_id == strategy_id and pos.instrument == instrument and pos.account_mode == account_mode:
                return pos.quantity
        return 0

    def _apply_fill_to_position(self, fill: Fill) -> None:
        key = "%s|%s|%s" % (
            fill.strategy_id, fill.instrument, fill.account_mode)
        pos = self._positions_cache.get(key)
        signed_qty = fill.quantity if fill.side == "buy" else -fill.quantity
        if pos is None:
            new_qty = signed_qty
            avg_price = fill.price
            realized = 0.0
        else:
            old_qty = pos.quantity
            new_qty = old_qty + signed_qty
            avg_price = pos.avg_price
            realized = pos.realized_pnl
            if old_qty == 0 or (old_qty > 0 and signed_qty > 0) or (old_qty < 0 and signed_qty < 0):
                total_abs = abs(old_qty) + abs(signed_qty)
                avg_price = ((abs(old_qty) * pos.avg_price) +
                             (abs(signed_qty) * fill.price)) / max(total_abs, 1)
            else:
                closing_qty = min(abs(old_qty), abs(signed_qty))
                if old_qty > 0:
                    realized += (fill.price - pos.avg_price) * closing_qty
                else:
                    realized += (pos.avg_price - fill.price) * closing_qty
                if new_qty == 0:
                    avg_price = 0.0
                elif abs(signed_qty) > abs(old_qty):
                    avg_price = fill.price
        updated = Position(
            position_id=key,
            strategy_id=fill.strategy_id,
            instrument=fill.instrument,
            account_mode=fill.account_mode,
            quantity=new_qty,
            avg_price=avg_price,
            realized_pnl=realized,
            updated_at=utc_now_iso(),
        )
        self._positions_cache[updated.position_id] = updated
        self.store.upsert_row("positions", "position_id", as_row(updated))

    def _cancel_oco_peers(self, filled_order: BrokerOrder) -> List[str]:
        cancelled: List[str] = []
        for order in self._orders_cache.values():
            if order.broker_order_id == filled_order.broker_order_id:
                continue
            if order.oco_group and order.oco_group == filled_order.oco_group and order.status == "submitted":
                self.cancel_order(order.broker_order_id,
                                  reason="oco_peer_filled")
                cancelled.append(order.broker_order_id)
        return cancelled

    def _get_order(self, broker_order_id: str) -> BrokerOrder:
        order = self._orders_cache.get(broker_order_id)
        if order is None:
            raise KeyError("Broker order not found: %s" % broker_order_id)
        return order

    def _get_intent(self, intent_id: str) -> OrderIntent:
        intent = self._intents_cache.get(intent_id)
        if intent is not None:
            return intent
        raise KeyError("Order intent not found: %s" % intent_id)


_NY = pytz.timezone("America/New_York")


def _parse_cmp_ts(value: str) -> Optional[datetime]:
    """Parse ISO timestamps for order live/expiry gates.

    Naive datetimes are treated as America/New_York wall clock (research /
    session-local convention). Aware values (including ``Z``) convert to UTC.
    Date-only strings return ``None`` so callers keep legacy string compare.
    """
    raw = str(value).strip()
    if not raw or ("T" not in raw and len(raw) <= 10):
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = _NY.localize(dt)
    return dt.astimezone(pytz.UTC)


def _ts_after(left: str, right: str) -> bool:
    """True when ``left`` is strictly after ``right``.

    Timezone-aware for full ISO timestamps so UTC live bars compare correctly
    against NY-session expiry stamps. Date-only values keep sortable string
    compare (expire once any same-day ISO timestamp is seen).
    """

    if not right:
        return True
    left_dt = _parse_cmp_ts(left)
    right_dt = _parse_cmp_ts(right)
    if left_dt is None or right_dt is None:
        return str(left) > str(right)
    return left_dt > right_dt


def _ts_before(left: str, right: str) -> bool:
    if not right:
        return False
    left_dt = _parse_cmp_ts(left)
    right_dt = _parse_cmp_ts(right)
    if left_dt is None or right_dt is None:
        return str(left) < str(right)
    return left_dt < right_dt


class TradovateBroker(BaseBroker):
    """Real broker adapter boundary.

    This is intentionally inert in v0. It documents where auth/session/order
    routing will live without risking accidental live order placement.
    """

    def __init__(self, config_path: Optional[Path] = None, allow_live_routing: bool = False):
        self.config_path = Path(config_path) if config_path else None
        self.allow_live_routing = allow_live_routing
        if allow_live_routing:
            raise NotImplementedError(
                "Tradovate live routing is not implemented in v0")

    def get_active_contract(self, instrument: str) -> str:
        raise NotImplementedError("Tradovate adapter shell only")

    def get_bars(self, instrument: str, timeframe: str, limit: int = 500) -> List[Bar]:
        raise NotImplementedError("Tradovate adapter shell only")

    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        raise NotImplementedError("Tradovate adapter shell only")

    def modify_order(
        self,
        broker_order_id: str,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reason: str = "",
        bracket_stop_price: Optional[float] = None,
        bracket_target_price: Optional[float] = None,
        live_after_ts: Optional[str] = None,
    ) -> BrokerOrder:
        raise NotImplementedError("Tradovate adapter shell only")

    def cancel_order(self, broker_order_id: str, reason: str = "") -> BrokerOrder:
        raise NotImplementedError("Tradovate adapter shell only")

    def reconcile_orders(self) -> List[BrokerOrder]:
        raise NotImplementedError("Tradovate adapter shell only")

    def reconcile_positions(self) -> List[Position]:
        raise NotImplementedError("Tradovate adapter shell only")

    def attach_bracket(self, parent_order: BrokerOrder, intent: OrderIntent) -> List[BrokerOrder]:
        raise NotImplementedError("Tradovate adapter shell only")
