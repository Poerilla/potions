from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
            "ma_filter": "none",
            "close_against_entry_exit": False,
            "st_flip_exit": False,
            "pmc_cross_exit": False,
            "record_levels": False,
            # DCA (off by default — baseline is single unit)
            "dca_enabled": False,
            "add_qty": 1,
            "max_adds": 1,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._pmc_ts_map: Dict[Tuple[int, int], str] = {}
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

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "1h" or not bar.complete:
            return StrategyActions.empty()
        return self._on_hourly_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        modifies: List[ModifyIntent] = []
        if fill.reason in {"entry", "runner_entry", "add"}:
            state["active_trade_id"] = fill.trade_id
            state["pending_entry_trade_id"] = ""
            state["close_pending"] = ""
            state["adds"] = int(state.get("adds") or 0) + max(1, int(float(fill.quantity or 1)))
            if fill.reason == "runner_entry":
                runner_entries = dict(state.get("runner_entry_price_by_trade") or {})
                runner_entries[fill.trade_id] = float(fill.price)
                state["runner_entry_price_by_trade"] = runner_entries
            self.state = state
            self.save_state()
        elif fill.reason == "target":
            if bool(self.config.get("runner_stop_to_be_after_tp1")):
                runner_entries = dict(state.get("runner_entry_price_by_trade") or {})
                entry_price = runner_entries.get(fill.trade_id)
                if entry_price is not None:
                    for order in context.strategy_open_orders:
                        if (
                            order.trade_id == fill.trade_id
                            and order.reduce_only
                            and order.order_type == "stop"
                            and order.bracket_role == "runner_stop"
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
                state["active_trade_id"] = ""
                state["pending_entry_trade_id"] = ""
                state["close_pending"] = ""
                state["adds"] = 0
                self.state = state
                self.save_state()
        elif fill.reason in {"stop", "protective_stop", "close"}:
            if context.position_quantity == 0:
                state["active_trade_id"] = ""
                state["pending_entry_trade_id"] = ""
                state["close_pending"] = ""
                state["adds"] = 0
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

        if context.position_quantity != 0:
            cancels.extend(self._cancel_entry_limits(context, "in_position"))
            state_changed = False
            if state.get("pending_entry_trade_id"):
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
            else:
                add_order = self._maybe_dca_add(bar, pmc, now, ma_context, context, state)
                if add_order is not None:
                    orders.append(add_order)
                    state_changed = True
            if state_changed:
                self.state = state
                self.save_state()
            return StrategyActions(orders, cancels, [], levels, [], causal_features)

        if state.get("active_trade_id"):
            state["active_trade_id"] = ""
            state["close_pending"] = ""
            state["adds"] = 0
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
                    reason="entry",
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

    def _entry_buckets(self, side: str, limit_px: float, stop_px: float, target_px: float) -> List[Dict[str, float]]:
        tp1_qty = int(float(self.config.get("tp1_qty") or 0))
        runner_qty = int(float(self.config.get("runner_qty") or 0))
        if tp1_qty <= 0 and runner_qty <= 0:
            tp1_qty = int(float(self.config.get("entry_qty") or 1))

        buckets: List[Dict[str, float]] = []
        if tp1_qty > 0:
            buckets.append({"role": "entry", "qty": tp1_qty, "stop": stop_px, "target": target_px})
        if runner_qty > 0:
            runner_target_pts = float(self.config.get("runner_target_pts") or self.config.get("target_pts") or 0.0)
            runner_target = limit_px + runner_target_pts if side == "buy" else limit_px - runner_target_pts
            buckets.append({"role": "runner_entry", "qty": runner_qty, "stop": stop_px, "target": runner_target})
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
            by_month[(d.year, d.month)] = (d, close)
        out: Dict[Tuple[int, int], float] = {}
        for (y, m) in by_month:
            py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
            if (py, pm) in by_month:
                prev_day, prev_close = by_month[(py, pm)]
                out[(y, m)] = prev_close
                self._pmc_ts_map[(y, m)] = prev_day.isoformat()
        return out

    def _prev_month_close(self, ts: str) -> Optional[float]:
        d = _parse_date(ts)
        return self._pmc_map.get((d.year, d.month))

    def _pmc_event_ts(self, ts: str) -> str:
        d = _parse_date(ts)
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

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("trade_seq", 0)
        state.setdefault("active_trade_id", "")
        state.setdefault("pending_entry_trade_id", "")
        state.setdefault("close_pending", "")
        state.setdefault("adds", 0)
        state.setdefault("runner_entry_price_by_trade", {})
        return state

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_t%d" % (self.instance.strategy_id, state["trade_seq"])

    def _open_entry_limits(self, context: StrategyContext):
        orders = []
        for order in context.strategy_open_orders:
            if order.reduce_only:
                continue
            if order.order_type == "limit" and order.status in {"submitted", "partially_filled"}:
                orders.append(order)
        return orders

    def _open_close_order(self, context: StrategyContext):
        for order in context.strategy_open_orders:
            if order.reduce_only and order.order_type == "market" and order.bracket_role == "close":
                return order
        return None

    def _cancel_entry_limits(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        cancels: List[CancelIntent] = []
        for order in context.strategy_open_orders:
            if order.reduce_only:
                continue
            if order.order_type == "limit":
                cancels.append(CancelIntent(self.instance.strategy_id, order.broker_order_id, reason))
        return cancels


def _parse_date(ts: str) -> date:
    return date.fromisoformat(str(ts)[:10])
