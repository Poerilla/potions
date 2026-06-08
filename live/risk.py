from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import OrderIntent, StrategyInstance
from .store import FlatFileStore


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str = ""


class RiskManager:
    def __init__(self, store: FlatFileStore):
        self.store = store

    def validate_order_intent(self, instance: StrategyInstance, intent: OrderIntent) -> RiskDecision:
        if not instance.enabled:
            return RiskDecision(False, "strategy_disabled")
        if intent.instrument != instance.instrument:
            return RiskDecision(False, "instrument_mismatch")
        if intent.account_mode not in {"paper", "live"}:
            return RiskDecision(False, "invalid_account_mode")
        if intent.account_mode == "live" and instance.account_mode != "live":
            return RiskDecision(False, "strategy_not_live")
        if intent.quantity <= 0:
            return RiskDecision(False, "quantity<=0")
        if intent.reduce_only:
            return RiskDecision(True, "reduce_only")
        projected = self._projected_exposure_with_intent(instance, intent)
        if projected > instance.max_contracts:
            return RiskDecision(False, "max_contracts_exceeded")
        if self._open_order_count(instance.strategy_id, instance.instrument, instance.account_mode) >= instance.max_open_orders:
            return RiskDecision(False, "max_open_orders_exceeded")
        if intent.account_mode == "live" and not self._live_contract_available(instance, intent):
            return RiskDecision(False, "live_contract_conflict")
        return RiskDecision(True, "ok")

    def _projected_exposure_with_intent(self, instance: StrategyInstance, intent: OrderIntent) -> int:
        """Maximum possible absolute contract exposure assuming ``intent`` is
        approved.

        Open entry orders are grouped by ``oco_group`` and only the largest leg
        in each group counts, because OCO peers cancel each other on fill.
        Orders without an OCO group count as their own group (so a ladder of
        three same-side limits still sums correctly).
        """

        groups = self._entry_order_groups(instance.strategy_id, instance.instrument, instance.account_mode)
        if not intent.reduce_only:
            key = intent.oco_group or intent.intent_id or "__incoming__"
            groups[key] = max(groups.get(key, 0), int(intent.quantity))
        open_pos = self._open_quantity(instance.strategy_id, instance.instrument, instance.account_mode)
        return open_pos + sum(groups.values())

    def _entry_order_groups(self, strategy_id: str, instrument: str, account_mode: str) -> Dict[str, int]:
        groups: Dict[str, int] = {}
        for row in self.store.table_rows_view("orders"):
            if (
                row.get("strategy_id") != strategy_id
                or row.get("instrument") != instrument
                or row.get("account_mode") != account_mode
                or row.get("status") not in {"submitted", "partially_filled"}
                or row.get("reduce_only") == "true"
            ):
                continue
            key = row.get("oco_group") or row.get("broker_order_id") or row.get("intent_id") or row.get("trade_id")
            qty = abs(int(float(row.get("remaining_quantity") or row.get("quantity") or 0)))
            groups[key] = max(groups.get(key, 0), qty)
        return groups

    def _open_quantity(self, strategy_id: str, instrument: str, account_mode: str) -> int:
        qty = 0
        for row in self.store.table_rows_view("positions"):
            if row.get("strategy_id") == strategy_id and row.get("instrument") == instrument and row.get("account_mode") == account_mode:
                qty += abs(int(float(row.get("quantity") or 0)))
        return qty

    def _open_order_count(self, strategy_id: str, instrument: str, account_mode: str) -> int:
        n = 0
        for row in self.store.table_rows_view("orders"):
            if (
                row.get("strategy_id") == strategy_id
                and row.get("instrument") == instrument
                and row.get("account_mode") == account_mode
                and row.get("status") in {"submitted", "partially_filled"}
            ):
                n += 1
        return n

    def _open_entry_order_quantity(self, strategy_id: str, instrument: str, account_mode: str) -> int:
        return sum(self._entry_order_groups(strategy_id, instrument, account_mode).values())

    def _live_contract_available(self, instance: StrategyInstance, intent: OrderIntent) -> bool:
        for row in self.store.table_rows_view("positions"):
            if row.get("account_mode") != "live":
                continue
            if row.get("instrument") != intent.instrument:
                continue
            if row.get("strategy_id") == instance.strategy_id:
                continue
            if int(float(row.get("quantity") or 0)) != 0:
                return False
        for row in self.store.table_rows_view("orders"):
            if row.get("account_mode") != "live":
                continue
            if row.get("instrument") != intent.instrument:
                continue
            if row.get("strategy_id") == instance.strategy_id:
                continue
            if row.get("status") in {"submitted", "partially_filled"}:
                return False
        return True
