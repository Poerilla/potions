from __future__ import annotations

from typing import Dict, Iterable, List

from .broker import BaseBroker
from .causality import CausalityGuard
from .models import Alert, Bar, Fill, OrderIntent, StrategyActions, StrategyInstance, as_row
from .notifications import NotificationSink
from .oanda import OandaRoutingBlocked
from .registry import StrategyRegistry
from .risk import RiskManager
from .store import FlatFileStore
from .strategies.base import StrategyContext, StrategyPlugin
from .verification import VerificationProvider


class StrategyManager:
    def __init__(
        self,
        store: FlatFileStore,
        broker: BaseBroker,
        risk: RiskManager,
        verification: VerificationProvider,
        notifications: NotificationSink,
        registry: StrategyRegistry = None,
        emit_order_alerts: bool = True,
        causality_guard: CausalityGuard = None,
    ):
        self.store = store
        self.broker = broker
        self.risk = risk
        self.verification = verification
        self.notifications = notifications
        self.registry = registry or StrategyRegistry()
        self.emit_order_alerts = emit_order_alerts
        self.causality_guard = causality_guard
        self._current_bar: Bar = None
        self.plugins: Dict[str, StrategyPlugin] = {}
        self.reload()

    def reload(self) -> None:
        self.store.ensure()
        self.plugins = {}
        for instance in self.store.load_strategy_instances():
            if instance.enabled:
                self.plugins[instance.strategy_id] = self.registry.create(self.store, instance)

    def on_bar_close(self, bar: Bar) -> StrategyActions:
        all_actions: List[StrategyActions] = []
        for plugin in self.plugins.values():
            if bar.instrument != plugin.instance.instrument:
                continue
            if bar.timeframe not in [tf.strip() for tf in plugin.instance.timeframes.split(",")]:
                continue
            context = self._context(plugin.instance)
            try:
                self._current_bar = bar
                actions = plugin.on_bar_close(bar, context)
                self._apply_actions(plugin.instance, actions)
                all_actions.append(actions)
            except Exception as exc:  # keep the loop alive; surface as alert.
                alert = Alert.create(plugin.instance.strategy_id, "engine_error", "Strategy error: %s" % exc)
                self._emit_alert(alert)
            finally:
                self._current_bar = None
        return StrategyActions.combine(all_actions)

    def on_fills(self, fills: Iterable[Fill]) -> None:
        for fill in fills:
            plugin = self.plugins.get(fill.strategy_id)
            if plugin is None:
                continue
            try:
                actions = plugin.on_fill(fill, self._context(plugin.instance))
                self._apply_actions(plugin.instance, actions)
            except Exception as exc:
                self._emit_alert(Alert.create(fill.strategy_id, "engine_error", "Fill callback error: %s" % exc))

    def startup_reconcile(self) -> None:
        for plugin in self.plugins.values():
            try:
                actions = plugin.on_startup_reconcile(self._context(plugin.instance))
                self._apply_actions(plugin.instance, actions)
            except Exception as exc:
                self._emit_alert(Alert.create(plugin.instance.strategy_id, "engine_error", "Startup reconcile error: %s" % exc))

    def _context(self, instance: StrategyInstance) -> StrategyContext:
        return StrategyContext(
            store=self.store,
            instance=instance,
            positions=self.broker.reconcile_positions(),
            open_orders=self.broker.reconcile_orders(),
        )

    def _apply_actions(self, instance: StrategyInstance, actions: StrategyActions) -> None:
        if self.causality_guard is not None and actions.causal_features and self._current_bar is not None:
            self.causality_guard.record_features(actions.causal_features, self._current_bar)
        elif actions.causal_features:
            self.store.append_rows("feature_snapshots", [as_row(feature) for feature in actions.causal_features])
        for level in actions.level_updates:
            self.store.add_level(level)
        for alert in actions.alerts:
            self._emit_alert(alert)
        for cancel in actions.cancel_intents:
            try:
                self.broker.cancel_order(cancel.broker_order_id, cancel.reason)
                if self.emit_order_alerts:
                    self._emit_alert(
                        Alert.create(
                            cancel.strategy_id,
                            "info",
                            "Cancelled order %s reason=%s (remote-acked then local)"
                            % (cancel.broker_order_id, cancel.reason),
                        )
                    )
            except Exception as exc:
                self._emit_alert(
                    Alert.create(
                        cancel.strategy_id,
                        "engine_error",
                        "Cancel failed (local left open): %s reason=%s err=%s"
                        % (cancel.broker_order_id, cancel.reason, exc),
                    )
                )
        for modify in actions.modify_intents:
            try:
                self.broker.modify_order(
                    modify.broker_order_id,
                    modify.limit_price,
                    modify.stop_price,
                    modify.reason,
                    bracket_stop_price=modify.bracket_stop_price,
                    bracket_target_price=modify.bracket_target_price,
                    live_after_ts=modify.live_after_ts,
                )
                if self.emit_order_alerts:
                    self._emit_alert(Alert.create(modify.strategy_id, "info", "Modified order %s" % modify.broker_order_id))
            except Exception as exc:
                self._emit_alert(Alert.create(modify.strategy_id, "engine_error", "Modify failed: %s" % exc))
        for intent in actions.order_intents:
            self._handle_order_intent(instance, intent)

    def _handle_order_intent(self, instance: StrategyInstance, intent: OrderIntent) -> None:
        if self.causality_guard is not None:
            decision = self.causality_guard.validate_order_intent(instance, intent, self._current_bar)
            if not decision.allowed:
                self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="causality_blocked"))
                self._emit_alert(
                    Alert.create(
                        intent.strategy_id,
                        "causality_block",
                        "Order blocked by causality guard: %s" % ",".join(v.violation_type for v in decision.violations),
                    )
                )
                return
        decision = self.risk.validate_order_intent(instance, intent)
        if not decision.allowed:
            self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="risk_blocked"))
            self._emit_alert(Alert.create(intent.strategy_id, "risk_block", "Order blocked: %s" % decision.reason))
            return
        if intent.requires_verification:
            req = self.verification.request_verification(intent)
            intent = OrderIntent.from_row(dict(as_row(intent), verification_id=req.verification_id))
            if not self.verification.is_approved(req.verification_id):
                self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="pending_verification"))
                self._emit_alert(Alert.create(intent.strategy_id, "order_pending_verification", "Order pending verification: %s" % req.verification_id))
                return
        try:
            order = self.broker.submit_order_intent(intent)
        except OandaRoutingBlocked as exc:
            self.store.upsert_row("order_intents", "intent_id", dict(as_row(intent), status="routing_blocked"))
            self._emit_alert(
                Alert.create(
                    intent.strategy_id,
                    "routing_block",
                    "Order blocked by broker routing: %s" % exc,
                )
            )
            return
        if self.emit_order_alerts:
            self._emit_alert(Alert.create(intent.strategy_id, "order_submitted", "Submitted %s %s %s" % (intent.side, intent.quantity, intent.instrument)))

    def _emit_alert(self, alert: Alert) -> None:
        self.store.add_alert(alert)
        self.notifications.send(alert)
