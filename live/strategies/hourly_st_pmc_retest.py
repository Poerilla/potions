from __future__ import annotations

import csv
import json
import math
from collections import deque
from datetime import date
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from ..models import Alert, Bar, CancelIntent, FeatureSnapshot, LevelUpdate, ModifyIntent, OrderIntent, StrategyActions
from .atr_supertrend_dca import TrendPoint
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot


class HourlyStPmcRetestStrategy(StrategyPlugin):
    """Hourly ATR Supertrend retest with prior-month-close bias filter.

    Rules:
    - Above prior calendar month close and bullish hourly ST → resting buy limit at ST stop.
    - Below prior calendar month close and bearish hourly ST → resting sell limit at ST stop.
    - Bracket: configurable stop/target points (default 50 / 150).
    - One entry at a time by default; limit is refreshed each hourly bar when flat.
    - Optional DCA: while in position and thesis still holds, market-add up to
      ``max_adds`` units (each with its own stop/target from the add price).
    - Optional retest add: while in position, rest a limit at the **original**
      entry with the **same** absolute stop/target (shared risk levels).
    - Optional BB add (1m Bollinger 20/2σ): while in position and price already
      in favor, add on lower-band touch (long) / upper-band touch (short) when
      mid is sloping favorably; add SL = original entry, TP = inherited target.
    """

    strategy_type = "hourly_st_pmc_retest"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "daily_bars_path": "",
            "atr_len": 14,
            "atr_mult": 3.0,
            "stop_pts": 50.0,
            "target_pts": 150.0,
            "tick_size": 1.0,
            "entry_qty": 1,
            "tp1_qty": 0,
            "runner_qty": 0,
            "runner_target_pts": 0.0,
            "runner_stop_to_be_after_tp1": False,
            # Optional multi-runner list: [{"qty": 1, "target_pts": 300}, {"qty": 1, "target_pts": null}]
            # null/omitted target_pts => indefinite (stop only; optional year-end flatten).
            "runner_specs": [],
            "year_end_flatten_runners": False,
            "runners_do_not_block_entries": False,
            "ma_filter": "none",
            "close_against_entry_exit": False,
            "st_flip_exit": False,
            "pmc_cross_exit": False,
            "record_levels": False,
            # DCA (off by default — baseline is single unit)
            "dca_enabled": False,
            "add_qty": 1,
            "max_adds": 1,
            # Retest add at original entry (same SL/TP absolute levels)
            "retest_add_enabled": False,
            "retest_add_qty": 1,
            "max_retest_adds": 1,
            # Favourable BB-touch adds on 1m (charts: length=20, std=2.0)
            "bb_add_enabled": False,
            "bb_len": 20,
            "bb_std": 2.0,
            "bb_add_qty": 1,
            "max_bb_adds": 3,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._pmc_ts_map: Dict[Tuple[int, int], str] = {}
        self._month_end_close: Dict[Tuple[int, int], float] = {}
        self._month_end_ts: Dict[Tuple[int, int], str] = {}
        self._pmc_map = self._load_prev_month_close_map()
        self._hourly_cache: Optional[List[Bar]] = None
        self._st_processed = 0
        self._st_trs: List[float] = []
        self._st_atr: Optional[float] = None
        self._st_final_upper: Optional[float] = None
        self._st_final_lower: Optional[float] = None
        self._st_bullish = True
        self._st_points: List[TrendPoint] = []
        self._ma_processed = 0
        self._ma_prefix: List[float] = [0.0]
        bb_len = max(2, int(float(self.config.get("bb_len") or 20)))
        self._bb_closes: Deque[float] = deque(maxlen=bb_len + 1)
        self._bb_mid_prev: Optional[float] = None

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if not bar.complete:
            return StrategyActions.empty()
        if bar.timeframe == "1m":
            return self._on_1m_bar(bar, context)
        if bar.timeframe != "1h":
            return StrategyActions.empty()
        return self._on_hourly_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        modifies: List[ModifyIntent] = []
        reason = str(fill.reason or "")
        is_runner_entry = reason == "runner_entry" or reason.startswith("runner_entry")
        if reason in {"entry", "add", "retest_add", "bb_add"} or is_runner_entry:
            state["active_trade_id"] = fill.trade_id
            state["pending_entry_trade_id"] = ""
            state["close_pending"] = ""
            state["adds"] = int(state.get("adds") or 0) + max(1, int(float(fill.quantity or 1)))
            if fill.reason in {"add", "retest_add", "bb_add"}:
                if bool(self.config.get("bb_add_enabled")) or fill.reason == "bb_add":
                    state["bb_add_count"] = int(state.get("bb_add_count") or 0) + 1
                else:
                    state["retest_add_count"] = int(state.get("retest_add_count") or 0) + 1
            if reason == "entry":
                qty = max(1, int(float(fill.quantity or 1)))
                state["blocking_qty"] = int(state.get("blocking_qty") or 0) + qty
                if state.get("anchor_entry") in (None, "", 0, 0.0):
                    entry_px = float(fill.price)
                    stop_pts = float(self.config["stop_pts"])
                    target_pts = float(self.config["target_pts"])
                    side = str(fill.side or "").lower()
                    state["anchor_entry"] = entry_px
                    state["anchor_side"] = "buy" if side == "buy" else "sell"
                    if state["anchor_side"] == "buy":
                        state["anchor_stop"] = entry_px - stop_pts
                        state["anchor_target"] = entry_px + target_pts
                    else:
                        state["anchor_stop"] = entry_px + stop_pts
                        state["anchor_target"] = entry_px - target_pts
            if is_runner_entry:
                runner_entries = dict(state.get("runner_entry_price_by_trade") or {})
                runner_entries[fill.trade_id] = float(fill.price)
                state["runner_entry_price_by_trade"] = runner_entries
            self.state = state
            self.save_state()
        elif reason == "target":
            # Primary TP (or any target): drop blocking qty first, then BE runners on TP1.
            qty = max(1, int(float(fill.quantity or 1)))
            blocking = int(state.get("blocking_qty") or 0)
            if blocking > 0:
                state["blocking_qty"] = max(0, blocking - qty)
            if bool(self.config.get("runner_stop_to_be_after_tp1")):
                runner_entries = dict(state.get("runner_entry_price_by_trade") or {})
                entry_price = runner_entries.get(fill.trade_id)
                if entry_price in (None, "", 0, 0.0):
                    entry_price = state.get("anchor_entry")
                if entry_price is not None:
                    for order in context.strategy_open_orders:
                        if (
                            order.trade_id == fill.trade_id
                            and order.reduce_only
                            and order.order_type == "stop"
                            and str(order.bracket_role or "").startswith("runner_stop")
                        ):
                            modifies.append(
                                ModifyIntent(
                                    self.instance.strategy_id,
                                    order.broker_order_id,
                                    "runner_stop_to_breakeven",
                                    stop_price=float(entry_price),
                                    live_after_ts=fill.ts,
                                )
                            )
            if context.position_quantity == 0:
                self._clear_position_state(state)
            self.state = state
            self.save_state()
        elif reason in {"stop", "protective_stop", "close", "year_end_flatten"}:
            if reason == "stop":
                qty = max(1, int(float(fill.quantity or 1)))
                state["blocking_qty"] = max(0, int(state.get("blocking_qty") or 0) - qty)
            if context.position_quantity == 0:
                self._clear_position_state(state)
            self.state = state
            self.save_state()
        elif reason == "runner_stop" or reason.startswith("runner_stop"):
            if context.position_quantity == 0:
                self._clear_position_state(state)
                self.state = state
                self.save_state()
        return StrategyActions([], [], modifies, [], [])

    def _on_hourly_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        hourly = self._hourly_bars(bar)
        now = self._current_trend_point(hourly)
        if now is None:
            return StrategyActions.empty()

        ma_context = self._ma_context(hourly)
        pmc = self._prev_month_close(bar.ts)
        if pmc is None:
            return StrategyActions.empty()

        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []
        levels: List[LevelUpdate] = []
        causal_features: List[FeatureSnapshot] = self._signal_features(bar, pmc, now, ma_context)

        bar_year = _parse_date(bar.ts).year
        prev_year = state.get("last_bar_year")
        if (
            bool(self.config.get("year_end_flatten_runners"))
            and prev_year is not None
            and int(prev_year) < bar_year
            and context.position_quantity != 0
            and self._open_close_order(context) is None
        ):
            flatten_qty = abs(context.position_quantity)
            # Drop resting brackets/entries so the market flatten is clean.
            cancels.extend(self._cancel_protective_orders(context, "year_end_flatten"))
            cancels.extend(self._cancel_entry_limits(context, "year_end_flatten"))
            exit_side = "sell" if context.position_quantity > 0 else "buy"
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=state.get("active_trade_id") or self._next_trade_id(state),
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="market",
                    quantity=flatten_qty,
                    reason="year_end_flatten",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="year_end_flatten",
                    live_after_ts=bar.ts,
                )
            )
            state["close_pending"] = "year_end_flatten"
            state["year_end_flatten_events"] = int(state.get("year_end_flatten_events") or 0) + 1
            state["year_end_flatten_qty"] = int(state.get("year_end_flatten_qty") or 0) + flatten_qty
            by_year = dict(state.get("year_end_flatten_by_year") or {})
            # Attribute inventory to the year that just ended.
            ended = str(int(prev_year))
            by_year[ended] = int(by_year.get(ended) or 0) + flatten_qty
            state["year_end_flatten_by_year"] = by_year
            state["last_bar_year"] = bar_year
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, [], causal_features)
        state["last_bar_year"] = bar_year

        if bool(self.config.get("record_levels")):
            levels.append(
                LevelUpdate(
                    self.instance.strategy_id,
                    self.instance.instrument,
                    "hourly_st_bull" if now.bullish else "hourly_st_bear",
                    now.stop,
                    bar.ts,
                )
            )
            levels.append(
                LevelUpdate(
                    self.instance.strategy_id,
                    self.instance.instrument,
                    "prev_month_close",
                    pmc,
                    bar.ts,
                )
            )

        blocking_qty = int(state.get("blocking_qty") or 0)
        runners_only = context.position_quantity != 0 and blocking_qty <= 0
        allow_stack = bool(self.config.get("runners_do_not_block_entries")) and runners_only

        if context.position_quantity != 0 and not allow_stack:
            retest_on = bool(self.config.get("retest_add_enabled"))
            cancels.extend(
                self._cancel_entry_limits(
                    context,
                    "in_position",
                    preserve_retest=retest_on,
                )
            )
            state_changed = False
            if state.get("pending_entry_trade_id") and not retest_on:
                state["pending_entry_trade_id"] = ""
                state_changed = True
            close_reason = self._close_reason(bar, pmc, now, context)
            if close_reason and self._open_close_order(context) is None:
                exit_side = "sell" if context.position_quantity > 0 else "buy"
                orders.append(
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=state.get("active_trade_id") or self._next_trade_id(state),
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side=exit_side,
                        order_type="market",
                        quantity=abs(context.position_quantity),
                        reason=close_reason,
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role="close",
                        live_after_ts=bar.ts,
                    )
                )
                state["close_pending"] = close_reason
                state_changed = True
                if retest_on:
                    cancels.extend(self._cancel_entry_limits(context, "thesis_off", preserve_retest=False))
            else:
                add_order = None
                # BB adds are evaluated on 1m bars; hourly only does classic retest/DCA.
                if retest_on and not bool(self.config.get("bb_add_enabled")):
                    add_order = self._maybe_retest_add(bar, pmc, now, ma_context, context, state)
                elif not retest_on and not bool(self.config.get("bb_add_enabled")):
                    add_order = self._maybe_dca_add(bar, pmc, now, ma_context, context, state)
                if add_order is not None:
                    orders.append(add_order)
                    state_changed = True
            if state_changed:
                self.state = state
                self.save_state()
            return StrategyActions(orders, cancels, [], levels, [], causal_features)

        if context.position_quantity == 0 and state.get("active_trade_id"):
            self._clear_position_state(state)
            self.state = state
            self.save_state()
        elif allow_stack:
            # Keep runner inventory; clear primary anchors so a new campaign can arm.
            state["pending_entry_trade_id"] = ""
            state["anchor_entry"] = None
            state["anchor_stop"] = None
            state["anchor_target"] = None
            state["anchor_side"] = ""
            state["blocking_qty"] = 0
            self.state = state
            self.save_state()

        desired = self._desired_entry(bar.close, pmc, now, ma_context)
        causal_features.append(self._entry_gate_feature(bar, pmc, now, ma_context, desired))
        if desired is None:
            cancels.extend(self._cancel_entry_limits(context, "regime_off"))
            if state.get("pending_entry_trade_id"):
                state["pending_entry_trade_id"] = ""
                self.state = state
                self.save_state()
            return StrategyActions([], cancels, [], levels, [], causal_features)

        side, limit_px, stop_px, target_px = desired
        desired_buckets = self._entry_buckets(side, limit_px, stop_px, target_px)
        existing_limits = self._open_entry_limits(context)
        tick = float(self.config["tick_size"])
        if existing_limits:
            same_side = all(order.side == side for order in existing_limits)
            roles = {order.bracket_role or "entry" for order in existing_limits}
            desired_roles = {bucket["role"] for bucket in desired_buckets}
            same_price = all(
                order.limit_price is not None and abs(order.limit_price - limit_px) <= tick / 2.0
                for order in existing_limits
            )
            if same_side and same_price and roles == desired_roles and len(existing_limits) == len(desired_buckets):
                return StrategyActions([], [], [], levels, [], causal_features)
            if same_side and roles == desired_roles and len(existing_limits) == len(desired_buckets):
                state["pending_entry_trade_id"] = existing_limits[0].trade_id
                by_role = {order.bracket_role or "entry": order for order in existing_limits}
                for bucket in desired_buckets:
                    existing = by_role[bucket["role"]]
                    modifies.append(
                        ModifyIntent(
                            self.instance.strategy_id,
                            existing.broker_order_id,
                            "refresh_entry",
                            limit_price=limit_px,
                            bracket_stop_price=bucket["stop"],
                            bracket_target_price=bucket["target"],
                            live_after_ts=bar.ts,
                        )
                    )
                self.state = state
                self.save_state()
                return StrategyActions([], [], modifies, levels, [], causal_features)

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
        return StrategyActions(orders, cancels, [], levels, [], causal_features)

    def _signal_features(
        self,
        bar: Bar,
        pmc: float,
        point: TrendPoint,
        ma_context: Dict[str, str],
    ) -> List[FeatureSnapshot]:
        pmc_event_ts = self._pmc_event_ts(bar.ts)
        return [
            feature_snapshot(
                self.instance,
                "hourly_st_pmc_signal",
                bar.ts,
                event_ts=point.ts,
                available_at_ts=bar.ts,
                source="completed_1h_supertrend_and_pmc",
                value_ref="bull" if point.bullish else "bear",
                metadata={
                    "bar_close": bar.close,
                    "supertrend_stop": point.stop,
                    "supertrend_bullish": point.bullish,
                    "prev_month_close": pmc,
                    "close_above_pmc": bar.close > pmc,
                    "ma_context": ma_context,
                    "ma_filter": self.config.get("ma_filter"),
                    "atr_len": self.config.get("atr_len"),
                    "atr_mult": self.config.get("atr_mult"),
                },
            ),
            feature_snapshot(
                self.instance,
                "prev_month_close",
                bar.ts,
                event_ts=pmc_event_ts or bar.ts,
                available_at_ts=pmc_event_ts or bar.ts,
                source="daily_bars_path.prior_month_close",
                value_ref=pmc,
                metadata={"pmc_event_ts": pmc_event_ts, "daily_bars_path": self.config.get("daily_bars_path")},
            ),
        ]

    def _entry_gate_feature(
        self,
        bar: Bar,
        pmc: float,
        point: TrendPoint,
        ma_context: Dict[str, str],
        desired: Optional[Tuple[str, float, float, float]],
    ) -> FeatureSnapshot:
        if desired is None:
            side = ""
            value_ref = "blocked"
            limit_px = stop_px = target_px = None
        else:
            side, limit_px, stop_px, target_px = desired
            value_ref = "%s:allowed" % side
        return feature_snapshot(
            self.instance,
            "hourly_st_pmc_entry_gate",
            bar.ts,
            source="hourly_st_pmc_retest.entry_rules",
            value_ref=value_ref,
            metadata={
                "side": side,
                "limit_price": limit_px,
                "stop_price": stop_px,
                "target_price": target_px,
                "bar_close": bar.close,
                "prev_month_close": pmc,
                "supertrend_stop": point.stop,
                "supertrend_bullish": point.bullish,
                "ma_context": ma_context,
                "ma_filter": self.config.get("ma_filter"),
            },
        )

    def _desired_entry(
        self,
        close: float,
        pmc: float,
        point: TrendPoint,
        ma_context: Dict[str, str],
    ) -> Optional[Tuple[str, float, float, float]]:
        stop_pts = float(self.config["stop_pts"])
        target_pts = float(self.config["target_pts"])
        st = float(point.stop)
        if close > pmc and point.bullish and self._ma_filter_allows("buy", ma_context):
            return ("buy", st, st - stop_pts, st + target_pts)
        if close < pmc and not point.bullish and self._ma_filter_allows("sell", ma_context):
            return ("sell", st, st + stop_pts, st - target_pts)
        return None

    def _entry_buckets(self, side: str, limit_px: float, stop_px: float, target_px: float) -> List[Dict[str, Any]]:
        tp1_qty = int(float(self.config.get("tp1_qty") or 0))
        runner_qty = int(float(self.config.get("runner_qty") or 0))
        if tp1_qty <= 0 and runner_qty <= 0 and not self.config.get("runner_specs"):
            tp1_qty = int(float(self.config.get("entry_qty") or 1))

        buckets: List[Dict[str, Any]] = []
        if tp1_qty > 0:
            buckets.append({"role": "entry", "qty": tp1_qty, "stop": stop_px, "target": target_px})

        specs = self.config.get("runner_specs") or []
        if not specs and runner_qty > 0:
            specs = [
                {
                    "qty": runner_qty,
                    "target_pts": float(self.config.get("runner_target_pts") or self.config.get("target_pts") or 0.0),
                }
            ]
        for i, spec in enumerate(specs):
            if not isinstance(spec, dict):
                continue
            qty = int(float(spec.get("qty") or 0))
            if qty <= 0:
                continue
            raw_t = spec.get("target_pts", None)
            if raw_t is None or raw_t == "" or (isinstance(raw_t, float) and math.isnan(raw_t)):
                runner_target: Optional[float] = None
            else:
                tpts = float(raw_t)
                runner_target = limit_px + tpts if side == "buy" else limit_px - tpts
            role = "runner_entry" if i == 0 else "runner_entry_%d" % (i + 1)
            buckets.append({"role": role, "qty": qty, "stop": stop_px, "target": runner_target})
        return buckets

    def _ma_context(self, hourly: List[Bar]) -> Dict[str, str]:
        if self._ma_processed > len(hourly):
            self._ma_processed = 0
            self._ma_prefix = [0.0]
        for idx in range(self._ma_processed, len(hourly)):
            self._ma_prefix.append(self._ma_prefix[-1] + float(hourly[idx].close))
            self._ma_processed += 1
        n = len(hourly)
        current = "unknown"
        prior = "unknown"
        if n >= 150:
            ma50 = (self._ma_prefix[n] - self._ma_prefix[n - 50]) / 50.0
            ma150 = (self._ma_prefix[n] - self._ma_prefix[n - 150]) / 150.0
            current = "bull" if ma50 > ma150 else "bear" if ma50 < ma150 else "flat"
        if n >= 151:
            end = n - 1
            ma50_prior = (self._ma_prefix[end] - self._ma_prefix[end - 50]) / 50.0
            ma150_prior = (self._ma_prefix[end] - self._ma_prefix[end - 150]) / 150.0
            prior = "bull" if ma50_prior > ma150_prior else "bear" if ma50_prior < ma150_prior else "flat"
        return {"current": current, "prior": prior}

    def _ma_filter_allows(self, side: str, ma_context: Dict[str, str]) -> bool:
        mode = str(self.config.get("ma_filter") or "none")
        if mode == "none":
            return True
        if mode == "directional_current":
            return (side == "buy" and ma_context["current"] == "bull") or (
                side == "sell" and ma_context["current"] == "bear"
            )
        if mode == "directional_prior":
            return (side == "buy" and ma_context["prior"] == "bull") or (
                side == "sell" and ma_context["prior"] == "bear"
            )
        if mode == "bull_prior_only":
            return ma_context["prior"] == "bull"
        if mode == "bear_prior_only":
            return ma_context["prior"] == "bear"
        return True

    def _close_reason(
        self,
        bar: Bar,
        pmc: float,
        point: TrendPoint,
        context: StrategyContext,
    ) -> str:
        qty = context.position_quantity
        avg_price = self._position_avg_price(context)
        if qty == 0 or avg_price is None:
            return ""
        if bool(self.config.get("close_against_entry_exit")):
            if qty > 0 and bar.close < avg_price:
                return "close_against_entry"
            if qty < 0 and bar.close > avg_price:
                return "close_against_entry"
        if bool(self.config.get("st_flip_exit")):
            if qty > 0 and not point.bullish:
                return "st_flip_against"
            if qty < 0 and point.bullish:
                return "st_flip_against"
        if bool(self.config.get("pmc_cross_exit")):
            if qty > 0 and bar.close < pmc:
                return "pmc_cross_against"
            if qty < 0 and bar.close > pmc:
                return "pmc_cross_against"
        return ""

    def _position_avg_price(self, context: StrategyContext) -> Optional[float]:
        for pos in context.positions:
            if (
                pos.strategy_id == self.instance.strategy_id
                and pos.instrument == self.instance.instrument
                and pos.account_mode == self.instance.account_mode
            ):
                return float(pos.avg_price)
        return None

    def _load_prev_month_close_map(self) -> Dict[Tuple[int, int], float]:
        raw_path = str(self.config.get("daily_bars_path") or "")
        if not raw_path:
            return {}
        path = Path(raw_path)
        if raw_path and not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / raw_path
        if not path.exists():
            return {}
        rows: List[Tuple[date, float]] = []
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                d = date.fromisoformat(str(row["date"])[:10])
                rows.append((d, float(row["close"])))
        rows.sort(key=lambda item: item[0])
        by_month: Dict[Tuple[int, int], Tuple[date, float]] = {}
        for d, close in rows:
            # Sorted ascending → last row per calendar month is the month-end close.
            by_month[(d.year, d.month)] = (d, close)
        self._month_end_close = {k: float(v[1]) for k, v in by_month.items()}
        self._month_end_ts = {k: v[0].isoformat() for k, v in by_month.items()}
        # Compat map: months present in the CSV → that month's prior-month close.
        out: Dict[Tuple[int, int], float] = {}
        for (y, m) in by_month:
            py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
            if (py, pm) in by_month:
                prev_day, prev_close = by_month[(py, pm)]
                out[(y, m)] = prev_close
                self._pmc_ts_map[(y, m)] = prev_day.isoformat()
        return out

    @staticmethod
    def _prior_calendar_month(d: date) -> Tuple[int, int]:
        return (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)

    def _prev_month_close(self, ts: str) -> Optional[float]:
        """Prior calendar-month last close (does not require current month in CSV)."""
        d = _parse_date(ts)
        py, pm = self._prior_calendar_month(d)
        if (py, pm) in self._month_end_close:
            return float(self._month_end_close[(py, pm)])
        # Fallback for older callers / partial loads.
        return self._pmc_map.get((d.year, d.month))

    def _pmc_event_ts(self, ts: str) -> str:
        d = _parse_date(ts)
        py, pm = self._prior_calendar_month(d)
        if (py, pm) in self._month_end_ts:
            return self._month_end_ts[(py, pm)]
        return self._pmc_ts_map.get((d.year, d.month), "")

    def _hourly_bars(self, bar: Bar) -> List[Bar]:
        if self._hourly_cache is None:
            self._hourly_cache = self.store.read_bars(self.instance.instrument, "1h")
        if not self._hourly_cache or self._hourly_cache[-1].ts != bar.ts:
            self._hourly_cache.append(bar)
        return self._hourly_cache

    def _current_trend_point(self, hourly: List[Bar]) -> Optional[TrendPoint]:
        if self._st_processed > len(hourly):
            self._reset_supertrend_cache()
        atr_len = int(self.config["atr_len"])
        atr_mult = float(self.config["atr_mult"])
        for idx in range(self._st_processed, len(hourly)):
            bar = hourly[idx]
            if idx == 0:
                tr = bar.high - bar.low
            else:
                prev_close = hourly[idx - 1].close
                tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
            self._st_trs.append(float(tr))
            if idx < atr_len - 1:
                self._st_processed += 1
                continue
            if idx == atr_len - 1:
                atr = sum(self._st_trs[:atr_len]) / float(atr_len)
                self._st_atr = atr
                hl2 = (bar.high + bar.low) / 2.0
                self._st_final_upper = hl2 + atr_mult * atr
                self._st_final_lower = hl2 - atr_mult * atr
                self._st_bullish = bar.close >= hl2
            else:
                assert self._st_atr is not None
                assert self._st_final_upper is not None
                assert self._st_final_lower is not None
                atr = (self._st_atr * (atr_len - 1) + tr) / float(atr_len)
                self._st_atr = atr
                hl2 = (bar.high + bar.low) / 2.0
                basic_upper = hl2 + atr_mult * atr
                basic_lower = hl2 - atr_mult * atr
                prev_upper = self._st_final_upper
                prev_lower = self._st_final_lower
                prev_close = hourly[idx - 1].close
                self._st_final_upper = basic_upper if basic_upper < prev_upper or prev_close > prev_upper else prev_upper
                self._st_final_lower = basic_lower if basic_lower > prev_lower or prev_close < prev_lower else prev_lower
                if self._st_bullish and bar.close < self._st_final_lower:
                    self._st_bullish = False
                elif (not self._st_bullish) and bar.close > self._st_final_upper:
                    self._st_bullish = True
            stop = self._st_final_lower if self._st_bullish else self._st_final_upper
            self._st_points.append(TrendPoint(ts=bar.ts, stop=float(stop), bullish=bool(self._st_bullish)))
            self._st_processed += 1
        return self._st_points[-1] if self._st_points else None

    def _reset_supertrend_cache(self) -> None:
        self._st_processed = 0
        self._st_trs = []
        self._st_atr = None
        self._st_final_upper = None
        self._st_final_lower = None
        self._st_bullish = True
        self._st_points = []

    def _maybe_dca_add(
        self,
        bar: Bar,
        pmc: float,
        now: TrendPoint,
        ma_context: Dict[str, str],
        context: StrategyContext,
        state: Dict[str, Any],
    ) -> Optional[OrderIntent]:
        if not bool(self.config.get("dca_enabled")):
            return None
        if state.get("close_pending"):
            return None
        max_adds = max(1, int(float(self.config.get("max_adds") or 1)))
        add_qty = max(1, int(float(self.config.get("add_qty") or 1)))
        qty = abs(int(context.position_quantity))
        if qty <= 0 or qty >= max_adds:
            return None
        if qty + add_qty > int(self.instance.max_contracts):
            return None
        # One working add/entry limit at a time.
        if self._open_entry_limits(context):
            return None
        desired = self._desired_entry(bar.close, pmc, now, ma_context)
        if desired is None:
            return None
        side, limit_px, stop_px, target_px = desired
        pos_side = "buy" if context.position_quantity > 0 else "sell"
        if side != pos_side:
            return None
        trade_id = self._next_trade_id(state)
        state["pending_entry_trade_id"] = trade_id
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=add_qty,
            limit_price=limit_px,
            reason="add",
            requires_verification=True,
            bracket_role="entry",
            bracket_stop_price=stop_px,
            bracket_target_price=target_px,
            live_after_ts=bar.ts,
        )

    def _maybe_retest_add(
        self,
        bar: Bar,
        pmc: float,
        now: TrendPoint,
        ma_context: Dict[str, str],
        context: StrategyContext,
        state: Dict[str, Any],
    ) -> Optional[OrderIntent]:
        """Rest another limit at the original entry with shared SL/TP (up to max_retest_adds)."""
        if not bool(self.config.get("retest_add_enabled")):
            return None
        if state.get("close_pending"):
            return None
        anchor = state.get("anchor_entry")
        stop_px = state.get("anchor_stop")
        target_px = state.get("anchor_target")
        anchor_side = str(state.get("anchor_side") or "")
        if anchor in (None, "", 0, 0.0) or stop_px in (None, "") or target_px in (None, ""):
            return None
        add_qty = max(1, int(float(self.config.get("retest_add_qty") or 1)))
        max_retests = max(1, int(float(self.config.get("max_retest_adds") or 1)))
        entry_qty = max(1, int(float(self.config.get("entry_qty") or self.config.get("tp1_qty") or 1)))
        retest_count = int(state.get("retest_add_count") or 0)
        if retest_count >= max_retests:
            return None
        max_pos = entry_qty + max_retests * add_qty
        qty = abs(int(context.position_quantity))
        if qty <= 0 or qty >= max_pos:
            return None
        if qty + add_qty > int(self.instance.max_contracts):
            return None
        # Keep a single working retest limit.
        if self._open_retest_limits(context):
            return None
        desired = self._desired_entry(bar.close, pmc, now, ma_context)
        if desired is None:
            return None
        side, _limit_px, _stop, _target = desired
        pos_side = "buy" if context.position_quantity > 0 else "sell"
        if side != pos_side or side != anchor_side:
            return None
        trade_id = self._next_trade_id(state)
        state["pending_entry_trade_id"] = trade_id
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=add_qty,
            limit_price=float(anchor),
            reason="add",
            requires_verification=True,
            # PaperBroker stamps fill.reason from bracket_role; keep "add" so audits count units.
            bracket_role="add",
            bracket_stop_price=float(stop_px),
            bracket_target_price=float(target_px),
            live_after_ts=bar.ts,
        )

    def _on_1m_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        """Maintain 1m Bollinger state; fire favourable BB-touch adds while in position."""
        self._bb_closes.append(float(bar.close))
        if not bool(self.config.get("bb_add_enabled")):
            return StrategyActions.empty()
        if context.position_quantity == 0:
            return StrategyActions.empty()
        state = self._state()
        order = self._maybe_bb_add(bar, context, state)
        if order is None:
            return StrategyActions.empty()
        self.state = state
        self.save_state()
        return StrategyActions([order], [], [], [], [], [])

    def _bb_bands(self) -> Optional[Tuple[float, float, float, Optional[float]]]:
        """Return (mid, upper, lower, prior_mid) using chart-matching BB(20, 2σ)."""
        length = max(2, int(float(self.config.get("bb_len") or 20)))
        n_std = float(self.config.get("bb_std") or 2.0)
        if len(self._bb_closes) < length:
            return None
        window = list(self._bb_closes)[-length:]
        mean = sum(window) / float(length)
        # pandas rolling().std() default ddof=1
        if length < 2:
            return None
        var = sum((x - mean) ** 2 for x in window) / float(length - 1)
        std = math.sqrt(var)
        upper = mean + n_std * std
        lower = mean - n_std * std
        prior_mid = None
        if len(self._bb_closes) >= length + 1:
            prev_window = list(self._bb_closes)[-(length + 1) : -1]
            prior_mid = sum(prev_window) / float(length)
        return mean, upper, lower, prior_mid

    def _maybe_bb_add(
        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
    ) -> Optional[OrderIntent]:
        """Add on 1m BB touch when price is already in favor; SL@entry, inherit TP."""
        if state.get("close_pending"):
            return None
        anchor = state.get("anchor_entry")
        target_px = state.get("anchor_target")
        anchor_side = str(state.get("anchor_side") or "")
        if anchor in (None, "", 0, 0.0) or target_px in (None, ""):
            return None
        anchor_f = float(anchor)
        target_f = float(target_px)
        add_qty = max(1, int(float(self.config.get("bb_add_qty") or 1)))
        max_adds = max(1, int(float(self.config.get("max_bb_adds") or 3)))
        entry_qty = max(1, int(float(self.config.get("entry_qty") or self.config.get("tp1_qty") or 1)))
        bb_count = int(state.get("bb_add_count") or 0)
        if bb_count >= max_adds:
            return None
        qty = abs(int(context.position_quantity))
        max_pos = entry_qty + max_adds * add_qty
        if qty <= 0 or qty >= max_pos:
            return None
        if qty + add_qty > int(self.instance.max_contracts):
            return None
        if self._open_retest_limits(context):
            return None
        if state.get("pending_entry_trade_id"):
            return None

        bands = self._bb_bands()
        if bands is None:
            return None
        mid, upper, lower, prior_mid = bands
        if prior_mid is None:
            return None

        pos_side = "buy" if context.position_quantity > 0 else "sell"
        if anchor_side and pos_side != anchor_side:
            return None
        tick = float(self.config.get("tick_size") or 0.1)
        half = tick / 2.0

        if pos_side == "buy":
            # Long: above entry, mid rising, touch lower band (still above entry).
            if float(bar.close) <= anchor_f:
                return None
            if mid <= prior_mid:
                return None
            if float(bar.low) > lower + half:
                return None
            if lower <= anchor_f + half:
                return None  # band not in-favor → SL@entry would be wrong side / zero risk
            side = "buy"
            stop_px = anchor_f
        else:
            # Short: below entry, mid falling, touch upper band (still below entry).
            if float(bar.close) >= anchor_f:
                return None
            if mid >= prior_mid:
                return None
            if float(bar.high) < upper - half:
                return None
            if upper >= anchor_f - half:
                return None
            side = "sell"
            stop_px = anchor_f

        trade_id = self._next_trade_id(state)
        state["pending_entry_trade_id"] = trade_id
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=add_qty,
            reason="bb_add",
            requires_verification=True,
            # PaperBroker stamps fill.reason from bracket_role.
            bracket_role="add",
            bracket_stop_price=float(stop_px),
            bracket_target_price=target_f,
            live_after_ts=bar.ts,
        )

    def _clear_position_state(self, state: Dict[str, Any]) -> None:
        state["active_trade_id"] = ""
        state["pending_entry_trade_id"] = ""
        state["close_pending"] = ""
        state["adds"] = 0
        state["retest_add_count"] = 0
        state["bb_add_count"] = 0
        state["runner_entry_price_by_trade"] = {}
        state["anchor_entry"] = None
        state["anchor_stop"] = None
        state["anchor_target"] = None
        state["anchor_side"] = ""
        state["blocking_qty"] = 0

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("trade_seq", 0)
        state.setdefault("active_trade_id", "")
        state.setdefault("pending_entry_trade_id", "")
        state.setdefault("close_pending", "")
        state.setdefault("adds", 0)
        state.setdefault("retest_add_count", 0)
        state.setdefault("bb_add_count", 0)
        state.setdefault("runner_entry_price_by_trade", {})
        state.setdefault("anchor_entry", None)
        state.setdefault("anchor_stop", None)
        state.setdefault("anchor_target", None)
        state.setdefault("anchor_side", "")
        state.setdefault("blocking_qty", 0)
        state.setdefault("last_bar_year", None)
        state.setdefault("year_end_flatten_events", 0)
        state.setdefault("year_end_flatten_qty", 0)
        state.setdefault("year_end_flatten_by_year", {})
        return state

    def _cancel_protective_orders(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        cancels: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if not order.reduce_only:
                continue
            if order.order_type not in {"stop", "limit"}:
                continue
            cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return cancels

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_t%d" % (self.instance.strategy_id, state["trade_seq"])

    def _open_entry_limits(self, context: StrategyContext):
        orders = []
        for order in context.strategy_open_orders:
            if order.reduce_only:
                continue
            # strategy_open_orders already filters OPEN_ORDER_STATUSES (incl. OANDA working)
            if order.order_type == "limit":
                orders.append(order)
        return orders

    def _open_retest_limits(self, context: StrategyContext):
        orders = []
        for order in context.strategy_open_orders:
            if order.reduce_only:
                continue
            if order.order_type not in {"limit", "market"}:
                continue
            if order.bracket_role == "add" or order.reason in {"add", "bb_add", "retest_add"}:
                orders.append(order)
        return orders

    def _open_close_order(self, context: StrategyContext):
        for order in context.strategy_open_orders:
            if (
                order.reduce_only
                and order.order_type == "market"
                and order.bracket_role in {"close", "year_end_flatten"}
            ):
                return order
        return None

    def _cancel_entry_limits(
        self,
        context: StrategyContext,
        reason: str,
        *,
        preserve_retest: bool = False,
    ) -> List[CancelIntent]:
        cancels: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only:
                continue
            if order.order_type != "limit":
                continue
            if preserve_retest and (order.bracket_role == "add" or order.reason in {"add", "bb_add"}):
                continue
            cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return cancels


def _parse_date(ts: str) -> date:
    return date.fromisoformat(str(ts)[:10])
