from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..models import (
    OPEN_ORDER_STATUSES,
    Bar,
    BrokerOrder,
    Fill,
    Position,
    StrategyActions,
    StrategyInstance,
)
from ..store import FlatFileStore


@dataclass(frozen=True)
class StrategyContext:
    store: FlatFileStore
    instance: StrategyInstance
    positions: List[Position]
    open_orders: List[BrokerOrder]

    @property
    def position_quantity(self) -> int:
        total = 0
        for pos in self.positions:
            if (
                pos.strategy_id == self.instance.strategy_id
                and pos.instrument == self.instance.instrument
                and pos.account_mode == self.instance.account_mode
            ):
                total += pos.quantity
        return total

    @property
    def strategy_open_orders(self) -> List[BrokerOrder]:
        return [
            order
            for order in self.open_orders
            if order.strategy_id == self.instance.strategy_id
            and order.instrument == self.instance.instrument
            and order.account_mode == self.instance.account_mode
            and order.status in OPEN_ORDER_STATUSES
        ]


class StrategyPlugin:
    strategy_type = "base"
    version = "v1"

    def __init__(self, store: FlatFileStore, instance: StrategyInstance):
        self.store = store
        self.instance = instance
        self.state = store.get_state(instance.strategy_id)

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        return StrategyActions.empty()

    def on_daily_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        return StrategyActions.empty()

    def on_fill(self, fill: Fill, context: StrategyContext) -> StrategyActions:
        return StrategyActions.empty()

    def on_position_update(self, position: Position, context: StrategyContext) -> StrategyActions:
        return StrategyActions.empty()

    def on_startup_reconcile(self, context: StrategyContext) -> StrategyActions:
        return StrategyActions.empty()

    def save_state(self) -> None:
        self.store.put_state(self.instance.strategy_id, self.state)
