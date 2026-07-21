"""Hourly ST + PMC break → limit at prior opposite SuperTrend trail.

Variant of ``hourly_st_pmc_retest``:

- Bullish: hourly close above prior-month close and ST bullish → buy limit at the
  last bearish SuperTrend trail value; stop at the current bullish trail;
  target = entry + reward_R × (entry − stop).
- Bearish: hourly close below PMC and ST bearish → sell limit at the last bullish
  trail; stop at the current bearish trail; target = entry − reward_R × (stop − entry).
- Default MA filter matches promoted sleeve: ``bull_prior_only``.
- Entries only during London cash open → NY cash close; classify fills as London
  (pre–09:30 NY) vs NY (09:30–16:00).
"""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple

import pytz

from ..models import Bar, FeatureSnapshot, StrategyActions
from .atr_supertrend_dca import TrendPoint
from .base import StrategyContext
from .features import feature_snapshot
from .hourly_st_pmc_retest import HourlyStPmcRetestStrategy


NY = "America/New_York"
LDN = "Europe/London"
NY_TZ = pytz.timezone(NY)
LDN_TZ = pytz.timezone(LDN)
LONDON_OPEN = time(8, 0)
NY_OPEN = time(9, 30)
NY_CLOSE = time(16, 0)


def in_london_ny_session(ts: str) -> bool:
    """True for London cash open through the NY 14:00 hour (left-labeled).

    The 15:00 NY hour is used to cancel resting entry limits so they cannot
    fill on the first post-session bar (engine fills before ``on_bar_close``).
    """
    dt = datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    ny = dt.astimezone(NY_TZ)
    d = ny.date()
    lo = LDN_TZ.localize(datetime.combine(d, LONDON_OPEN)).astimezone(NY_TZ)
    # Last arming hour is 14:00 NY (bar covers 14:00–15:00).
    hi = NY_TZ.localize(datetime.combine(d, time(15, 0)))
    return lo <= ny < hi


def session_bucket(ts: str) -> str:
    """Classify a timestamp as london / ny / off for win tracking.

    Arming stops before the 15:00 NY hour, but fills on that hour (from limits
    armed at 14:00) still count as NY.
    """
    dt = datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    ny = dt.astimezone(NY_TZ)
    d = ny.date()
    lo = LDN_TZ.localize(datetime.combine(d, LONDON_OPEN)).astimezone(NY_TZ)
    ny_open = NY_TZ.localize(datetime.combine(d, NY_OPEN))
    ny_fill_end = NY_TZ.localize(datetime.combine(d, time(16, 0)))
    if lo <= ny < ny_open:
        return "london"
    if ny_open <= ny < ny_fill_end:
        return "ny"
    return "off"


class HourlyStPmcBreakPrevTrailStrategy(HourlyStPmcRetestStrategy):
    strategy_type = "hourly_st_pmc_break_prev_trail"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        try:
            raw = json.loads(instance.config_json or "{}")
        except json.JSONDecodeError:
            raw = {}
        defaults = {
            "ma_filter": "none",
            "reward_R": 3.0,
            "min_r_pts": 0.0005,  # 5 pips EURUSD
            "session_gate": True,
        }
        for key, value in defaults.items():
            if key not in raw:
                self.config[key] = value
        self._last_bearish_stop: Optional[float] = None
        self._last_bullish_stop: Optional[float] = None

    def _on_hourly_bar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        hourly = self._hourly_bars(bar)
        now = self._current_trend_point(hourly)
        if now is None:
            return StrategyActions.empty()
        self._remember_trail(now)

        session_on = (not bool(self.config.get("session_gate"))) or in_london_ny_session(bar.ts)
        # Always cancel resting entries once the arming window ends (incl. 15:00 NY
        # cancel hour), even if still "managing" an open position.
        if context.position_quantity == 0 and not session_on:
            cancels = self._cancel_entry_limits(context, "session_off")
            state = self._state()
            if state.get("pending_entry_trade_id"):
                state["pending_entry_trade_id"] = ""
                self.state = state
                self.save_state()
            return StrategyActions([], cancels, [], [], [], [])

        actions = super()._on_hourly_bar(bar, context)
        if context.position_quantity != 0 and not session_on:
            # Flat path already returned; here strip any stray entry limits.
            extra_cancels = self._cancel_entry_limits(context, "session_off")
            if extra_cancels:
                actions = StrategyActions(
                    list(actions.order_intents),
                    list(actions.cancel_intents) + extra_cancels,
                    list(actions.modify_intents),
                    list(actions.level_updates),
                    list(actions.alerts),
                    list(actions.causal_features),
                )
        extras: List[FeatureSnapshot] = [
            feature_snapshot(
                self.instance,
                "session_bucket",
                bar.ts,
                source="hourly_st_pmc_break_prev_trail.session",
                value_ref=session_bucket(bar.ts),
                metadata={
                    "in_session": session_on,
                    "last_bearish_stop": self._last_bearish_stop,
                    "last_bullish_stop": self._last_bullish_stop,
                },
            )
        ]
        return StrategyActions(
            list(actions.order_intents),
            list(actions.cancel_intents),
            list(actions.modify_intents),
            list(actions.level_updates),
            list(actions.alerts),
            list(actions.causal_features) + extras,
        )

    def _remember_trail(self, point: TrendPoint) -> None:
        if point.bullish:
            self._last_bullish_stop = float(point.stop)
        else:
            self._last_bearish_stop = float(point.stop)

    def _desired_entry(
        self,
        close: float,
        pmc: float,
        point: TrendPoint,
        ma_context: Dict[str, str],
    ) -> Optional[Tuple[str, float, float, float]]:
        reward_r = float(self.config.get("reward_R") or 3.0)
        min_r = float(self.config.get("min_r_pts") or 0.0)
        tick = float(self.config.get("tick_size") or 1e-5)

        if close > pmc and point.bullish and self._ma_filter_allows("buy", ma_context):
            entry = self._last_bearish_stop
            stop = float(point.stop)
            if entry is None:
                return None
            risk = float(entry) - stop
            if risk < max(min_r, tick):
                return None
            target = float(entry) + reward_r * risk
            return ("buy", float(entry), stop, target)

        if close < pmc and (not point.bullish) and self._ma_filter_allows("sell", ma_context):
            entry = self._last_bullish_stop
            stop = float(point.stop)
            if entry is None:
                return None
            risk = stop - float(entry)
            if risk < max(min_r, tick):
                return None
            target = float(entry) - reward_r * risk
            return ("sell", float(entry), stop, target)

        return None

    def _entry_gate_feature(
        self,
        bar: Bar,
        pmc: float,
        point: TrendPoint,
        ma_context: Dict[str, str],
        desired: Optional[Tuple[str, float, float, float]],
    ) -> FeatureSnapshot:
        feat = super()._entry_gate_feature(bar, pmc, point, ma_context, desired)
        try:
            meta = json.loads(feat.metadata_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        meta.update(
            {
                "entry_mode": "pmc_break_prev_opposite_trail",
                "reward_R": self.config.get("reward_R"),
                "last_bearish_stop": self._last_bearish_stop,
                "last_bullish_stop": self._last_bullish_stop,
                "session_bucket": session_bucket(bar.ts),
            }
        )
        return feature_snapshot(
            self.instance,
            "hourly_st_pmc_entry_gate",
            bar.ts,
            source="hourly_st_pmc_break_prev_trail.entry_rules",
            value_ref=feat.value_ref,
            metadata=meta,
        )
