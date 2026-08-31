"""Hourly ST+PMC causal revival paths A / B / C (new strategies).

These are **not** the retired fair-3R book. Fresh trial record; PMC-level or
continuation mechanics under completed-hour causality.

Path A — pre-posted PMC limit:
  On each completed hour with ST+PMC, rest a limit at PMC (known earlier).
  Fills may occur on subsequent 1m tape; ST is for gate/management only.

Path B — post-hour PMC retest (one-shot):
  On completed hour with ST+PMC, arm a PMC limit on that signal bar, one retest,
  cancel after ``retest_expiry_minutes`` (default 240). No refresh.

Path C — post-hour continuation:
  On completed hour with ST+PMC, wait for a 1m break of that hour's high (long)
  / low (short); enter market on the **next** executable 1m bar.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..models import (
    Bar,
    CancelIntent,
    FeatureSnapshot,
    ModifyIntent,
    OrderIntent,
    StrategyActions,
)
from .features import feature_snapshot
from .hourly_st_pmc_retest import HourlyStPmcRetestStrategy


class HourlyStPmcCausalRevivalStrategy(HourlyStPmcRetestStrategy):
    strategy_type = "hourly_st_pmc_causal_revival"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        # Defaults for revival; instance config_json overrides.
        self.config.setdefault("revival_path", "A")
        self.config.setdefault("retest_expiry_minutes", 240)
        self.config.setdefault("entry_level", "pmc")  # pmc only for A/B
        self.config.setdefault("continuation_trigger", "hour_extreme_break")

    def on_bar_close(self, bar: Bar, context) -> StrategyActions:
        if not bar.complete:
            return StrategyActions.empty()
        path = str(self.config.get("revival_path") or "A").upper()
        if bar.timeframe == "1m":
            if path == "C":
                return self._path_c_on_1m(bar, context)
            return StrategyActions.empty()
        if bar.timeframe != "1h":
            return StrategyActions.empty()
        if path == "A":
            return self._path_a_on_hour(bar, context)
        if path == "B":
            return self._path_b_on_hour(bar, context)
        if path == "C":
            return self._path_c_on_hour(bar, context)
        return StrategyActions.empty()

    # --- shared thesis ---
    def _thesis(
        self, bar: Bar, context
    ) -> Optional[Tuple[str, float, float, float, Any, float, Dict[str, str]]]:
        hourly = self._hourly_bars(bar)
        now = self._current_trend_point(hourly)
        if now is None:
            return None
        ma_context = self._ma_context(hourly)
        pmc = self._prev_month_close(bar.ts)
        if pmc is None:
            return None
        desired = self._desired_entry_pmc(bar.close, pmc, now, ma_context)
        if desired is None:
            return None
        side, limit_px, stop_px, target_px = desired
        return side, limit_px, stop_px, target_px, now, pmc, ma_context

    def _desired_entry_pmc(self, close, pmc, point, ma_context):
        stop_pts = float(self.config["stop_pts"])
        target_pts = float(self.config["target_pts"])
        # Entry at PMC; stop/target measured from PMC (filled price ≈ PMC on touch).
        if close > pmc and point.bullish and self._ma_filter_allows("buy", ma_context):
            return ("buy", float(pmc), float(pmc) - stop_pts, float(pmc) + target_pts)
        if close < pmc and not point.bullish and self._ma_filter_allows("sell", ma_context):
            return ("sell", float(pmc), float(pmc) + stop_pts, float(pmc) - target_pts)
        return None

    def _signal_features_revival(self, bar, pmc, now, ma_context, path: str):
        return [
            feature_snapshot(
                self.instance,
                "hourly_st_pmc_revival_signal",
                bar.ts,
                event_ts=now.ts,
                available_at_ts=bar.ts,
                source="completed_1h_supertrend_and_pmc",
                value_ref="%s:%s" % (path, "bull" if now.bullish else "bear"),
                metadata={
                    "revival_path": path,
                    "bar_close": bar.close,
                    "bar_high": bar.high,
                    "bar_low": bar.low,
                    "supertrend_stop": now.stop,
                    "supertrend_bullish": now.bullish,
                    "prev_month_close": pmc,
                    "ma_context": ma_context,
                },
            ),
            feature_snapshot(
                self.instance,
                "prev_month_close",
                bar.ts,
                event_ts=self._pmc_event_ts(bar.ts) or bar.ts,
                available_at_ts=self._pmc_event_ts(bar.ts) or bar.ts,
                source="daily_bars_path.prior_month_close",
                value_ref=str(pmc),
                metadata={"daily_bars_path": self.config.get("daily_bars_path")},
            ),
        ]

    def _expiry_ts(self, bar_ts: str) -> str:
        mins = int(float(self.config.get("retest_expiry_minutes") or 240))
        ts = pd.Timestamp(bar_ts)
        return (ts + timedelta(minutes=mins)).isoformat()

    # --- Path A ---
    def _path_a_on_hour(self, bar: Bar, context) -> StrategyActions:
        # Reuse parent hourly flow but with PMC limit via temporary override.
        thesis = self._thesis(bar, context)
        features: List[FeatureSnapshot] = []
        if thesis is None:
            hourly = self._hourly_bars(bar)
            now = self._current_trend_point(hourly)
            pmc = self._prev_month_close(bar.ts)
            if now is not None and pmc is not None:
                features = self._signal_features_revival(
                    bar, pmc, now, self._ma_context(hourly), "A"
                )
            cancels = self._cancel_entry_limits(context, "regime_off")
            state = self._state()
            if state.get("pending_entry_trade_id"):
                state["pending_entry_trade_id"] = ""
                self.state = state
                self.save_state()
            return StrategyActions([], cancels, [], [], [], features)

        side, limit_px, stop_px, target_px, now, pmc, ma_context = thesis
        features = self._signal_features_revival(bar, pmc, now, ma_context, "A")
        features.append(
            feature_snapshot(
                self.instance,
                "hourly_st_pmc_revival_entry_gate",
                bar.ts,
                event_ts=now.ts,
                available_at_ts=bar.ts,
                source="path_a_prepost_pmc",
                value_ref="%s:allowed" % side,
                metadata={
                    "side": side,
                    "limit_price": limit_px,
                    "stop_price": stop_px,
                    "target_price": target_px,
                    "prev_month_close": pmc,
                },
            )
        )

        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []

        if context.position_quantity != 0:
            cancels.extend(self._cancel_entry_limits(context, "in_position"))
            return StrategyActions([], cancels, [], [], [], features)

        if state.get("active_trade_id"):
            self._clear_position_state(state)
            self.state = state
            self.save_state()

        desired_buckets = self._entry_buckets(side, limit_px, stop_px, target_px)
        existing = self._open_entry_limits(context)
        tick = float(self.config["tick_size"])
        if existing:
            same_side = all(o.side == side for o in existing)
            same_px = all(
                o.limit_price is not None and abs(float(o.limit_price) - limit_px) <= tick / 2.0
                for o in existing
            )
            roles = {o.bracket_role or "entry" for o in existing}
            want = {b["role"] for b in desired_buckets}
            if same_side and same_px and roles == want and len(existing) == len(desired_buckets):
                return StrategyActions([], [], [], [], [], features)
            if same_side and roles == want and len(existing) == len(desired_buckets):
                state["pending_entry_trade_id"] = existing[0].trade_id
                by_role = {o.bracket_role or "entry": o for o in existing}
                for bucket in desired_buckets:
                    existing_o = by_role[bucket["role"]]
                    modifies.append(
                        ModifyIntent(
                            self.instance.strategy_id,
                            existing_o.broker_order_id,
                            "refresh_entry",
                            limit_price=limit_px,
                            bracket_stop_price=bucket["stop"],
                            bracket_target_price=bucket["target"],
                            live_after_ts=bar.ts,
                        )
                    )
                self.state = state
                self.save_state()
                return StrategyActions([], [], modifies, [], [], features)

        cancels.extend(self._cancel_entry_limits(context, "refresh_entry"))
        trade_id = self._next_trade_id(state)
        state["pending_entry_trade_id"] = trade_id
        for bucket in desired_buckets:
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=side,
                    order_type="limit",
                    quantity=int(bucket["qty"]),
                    limit_price=limit_px,
                    reason="entry" if bucket["role"] == "entry" else str(bucket["role"]),
                    requires_verification=True,
                    bracket_role=bucket["role"],
                    bracket_stop_price=bucket["stop"],
                    bracket_target_price=bucket["target"],
                    live_after_ts=bar.ts,
                )
            )
        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], [], [], features)

    # --- Path B ---
    def _path_b_on_hour(self, bar: Bar, context) -> StrategyActions:
        thesis = self._thesis(bar, context)
        state = self._state()
        features: List[FeatureSnapshot] = []
        cancels: List[CancelIntent] = []
        orders: List[OrderIntent] = []

        if context.position_quantity != 0:
            cancels.extend(self._cancel_entry_limits(context, "in_position"))
            return StrategyActions([], cancels, [], [], [], features)

        # One-shot: if a pending one-shot is still working, do not refresh.
        if self._open_entry_limits(context):
            return StrategyActions.empty()

        if thesis is None:
            return StrategyActions.empty()

        side, limit_px, stop_px, target_px, now, pmc, ma_context = thesis
        # Avoid re-arming the same signal hour twice.
        if str(state.get("path_b_last_signal_ts") or "") == str(bar.ts):
            return StrategyActions.empty()

        features = self._signal_features_revival(bar, pmc, now, ma_context, "B")
        features.append(
            feature_snapshot(
                self.instance,
                "hourly_st_pmc_revival_entry_gate",
                bar.ts,
                event_ts=now.ts,
                available_at_ts=bar.ts,
                source="path_b_post_hour_pmc_retest",
                value_ref="%s:oneshot" % side,
                metadata={
                    "side": side,
                    "limit_price": limit_px,
                    "expires_after_ts": self._expiry_ts(bar.ts),
                    "retest_expiry_minutes": self.config.get("retest_expiry_minutes"),
                },
            )
        )

        if state.get("active_trade_id"):
            self._clear_position_state(state)

        trade_id = self._next_trade_id(state)
        state["pending_entry_trade_id"] = trade_id
        state["path_b_last_signal_ts"] = bar.ts
        expiry = self._expiry_ts(bar.ts)
        for bucket in self._entry_buckets(side, limit_px, stop_px, target_px):
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=side,
                    order_type="limit",
                    quantity=int(bucket["qty"]),
                    limit_price=limit_px,
                    reason="entry" if bucket["role"] == "entry" else str(bucket["role"]),
                    requires_verification=True,
                    bracket_role=bucket["role"],
                    bracket_stop_price=bucket["stop"],
                    bracket_target_price=bucket["target"],
                    live_after_ts=bar.ts,
                    expires_after_ts=expiry,
                )
            )
        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], [], [], features)

    # --- Path C ---
    def _path_c_on_hour(self, bar: Bar, context) -> StrategyActions:
        thesis = self._thesis(bar, context)
        state = self._state()
        features: List[FeatureSnapshot] = []
        cancels: List[CancelIntent] = []

        if context.position_quantity != 0:
            # Clear pending continuation while in a trade.
            state["path_c_armed"] = False
            state["path_c_break_seen"] = False
            self.state = state
            self.save_state()
            cancels.extend(self._cancel_entry_limits(context, "in_position"))
            return StrategyActions([], cancels, [], [], [], features)

        if thesis is None:
            state["path_c_armed"] = False
            state["path_c_break_seen"] = False
            self.state = state
            self.save_state()
            return StrategyActions.empty()

        side, _limit, stop_px, target_px, now, pmc, ma_context = thesis
        # Stops/targets for market entry measured from trigger bar later; store R distances.
        features = self._signal_features_revival(bar, pmc, now, ma_context, "C")
        state["path_c_armed"] = True
        state["path_c_side"] = side
        state["path_c_hour_high"] = float(bar.high)
        state["path_c_hour_low"] = float(bar.low)
        state["path_c_signal_ts"] = bar.ts
        state["path_c_break_seen"] = False
        state["path_c_enter_next"] = False
        # Absolute brackets will be set from fill via entry buckets using trigger close.
        state["path_c_stop_pts"] = float(self.config["stop_pts"])
        state["path_c_target_pts"] = float(self.config["target_pts"])
        self.state = state
        self.save_state()
        features.append(
            feature_snapshot(
                self.instance,
                "hourly_st_pmc_revival_entry_gate",
                bar.ts,
                event_ts=now.ts,
                available_at_ts=bar.ts,
                source="path_c_continuation_arm",
                value_ref="%s:armed" % side,
                metadata={
                    "side": side,
                    "hour_high": bar.high,
                    "hour_low": bar.low,
                    "trigger": self.config.get("continuation_trigger"),
                },
            )
        )
        return StrategyActions([], cancels, [], [], [], features)

    def _path_c_on_1m(self, bar: Bar, context) -> StrategyActions:
        state = self._state()
        if context.position_quantity != 0 or not bool(state.get("path_c_armed")):
            return StrategyActions.empty()
        if state.get("pending_entry_trade_id"):
            return StrategyActions.empty()

        side = str(state.get("path_c_side") or "")
        hour_high = float(state.get("path_c_hour_high") or 0.0)
        hour_low = float(state.get("path_c_hour_low") or 0.0)
        orders: List[OrderIntent] = []

        if bool(state.get("path_c_enter_next")):
            # Enter on this bar (next after break observation).
            stop_pts = float(state.get("path_c_stop_pts") or self.config["stop_pts"])
            target_pts = float(state.get("path_c_target_pts") or self.config["target_pts"])
            entry_ref = float(bar.open)
            if side == "buy":
                stop_px = entry_ref - stop_pts
                target_px = entry_ref + target_pts
            else:
                stop_px = entry_ref + stop_pts
                target_px = entry_ref - target_pts
            trade_id = self._next_trade_id(state)
            state["pending_entry_trade_id"] = trade_id
            state["path_c_armed"] = False
            state["path_c_enter_next"] = False
            state["path_c_break_seen"] = False
            for bucket in self._entry_buckets(side, entry_ref, stop_px, target_px):
                orders.append(
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=trade_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side=side,
                        order_type="market",
                        quantity=int(bucket["qty"]),
                        reason="entry" if bucket["role"] == "entry" else str(bucket["role"]),
                        requires_verification=True,
                        bracket_role=bucket["role"],
                        bracket_stop_price=bucket["stop"],
                        bracket_target_price=bucket["target"],
                        live_after_ts=bar.ts,
                    )
                )
            self.state = state
            self.save_state()
            return StrategyActions(orders, [], [], [], [], [])

        # Detect break on this bar; enter on the *next* 1m bar.
        if not bool(state.get("path_c_break_seen")):
            broke = False
            if side == "buy" and float(bar.high) >= hour_high - 1e-9:
                broke = True
            elif side == "sell" and float(bar.low) <= hour_low + 1e-9:
                broke = True
            if broke:
                state["path_c_break_seen"] = True
                state["path_c_enter_next"] = True
                self.state = state
                self.save_state()
        return StrategyActions.empty()
