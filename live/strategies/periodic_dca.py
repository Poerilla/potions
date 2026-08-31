"""Buy-and-hold periodic DCA: 1 lot on first bar open of each month or quarter.

Optional gate: only buy when the *prior completed* daily ATR Supertrend is bullish
(causal at period-open fill).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models import Bar, OrderIntent, StrategyActions
from .atr_supertrend_dca import _supertrend
from .base import StrategyContext, StrategyPlugin


def _parse_ts(ts: str) -> datetime:
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def _period_key(ts: str, cadence: str) -> str:
    dt = _parse_ts(ts)
    if cadence == "quarterly":
        q = (dt.month - 1) // 3 + 1
        return "%04d-Q%d" % (dt.year, q)
    return "%04d-%02d" % (dt.year, dt.month)


class PeriodicDcaStrategy(StrategyPlugin):
    """Accumulate longs: market buy ``qty`` on first bar of each month/quarter.

    Submitted on that bar's ``on_bar_close`` with empty ``live_after_ts`` so
    PaperBroker fills the same bar at open (calendar period open).

    When ``require_daily_supertrend_bullish`` is set, the buy is skipped unless
    Supertrend on bars *before* the current bar is bullish (prior close). The
    period is still consumed so a mid-period flip does not fire a late buy.
    """

    strategy_type = "periodic_dca"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self._daily_bars_cache: Optional[List[Bar]] = None
        cfg: Dict[str, Any] = {}
        raw = getattr(instance, "config_json", "") or ""
        if raw:
            try:
                cfg = json.loads(raw)
            except json.JSONDecodeError:
                cfg = {}
        self.config = {
            "cadence": str(cfg.get("cadence") or "monthly").lower(),  # monthly | quarterly
            "qty": int(cfg.get("qty") or 1),
            "side": str(cfg.get("side") or "buy").lower(),
            "suppress_alerts": bool(cfg.get("suppress_alerts", True)),
            "require_daily_supertrend_bullish": bool(
                cfg.get("require_daily_supertrend_bullish", False)
            ),
            "atr_len": int(cfg.get("atr_len") or 14),
            "atr_mult": float(cfg.get("atr_mult") or 3.0),
        }
        if self.config["cadence"] not in {"monthly", "quarterly"}:
            raise ValueError("periodic_dca cadence must be monthly|quarterly")
        if self.config["side"] not in {"buy", "sell"}:
            raise ValueError("periodic_dca side must be buy|sell")

    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        daily_bars = self._daily_bars(bar)
        state = dict(self.state or {})
        cadence = self.config["cadence"]
        key = _period_key(bar.ts, cadence)
        last = str(state.get("last_period_key") or "")
        if key == last:
            return StrategyActions.empty()

        qty = int(self.config["qty"])
        if qty <= 0:
            return StrategyActions.empty()

        # Consume the period even on skip so we do not DCA mid-period later.
        state["last_period_key"] = key
        state["last_period_ts"] = bar.ts

        if bool(self.config["require_daily_supertrend_bullish"]):
            prior = daily_bars[:-1]  # exclude current bar (open fill is causal)
            atr_len = int(self.config["atr_len"])
            points = _supertrend(prior, atr_len, float(self.config["atr_mult"]))
            if len(points) < 1 or not points[-1].bullish:
                state["skip_count"] = int(state.get("skip_count") or 0) + 1
                state["last_skip_ts"] = bar.ts
                state["last_skip_reason"] = "supertrend_not_bullish"
                self.state = state
                self.save_state()
                return StrategyActions.empty()

        n = int(state.get("buy_count") or 0) + 1
        trade_id = "%s_%s_%03d" % (self.instance.strategy_id, key, n)
        role = "entry" if n == 1 else "add"
        intent = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=self.config["side"],
            order_type="market",
            quantity=qty,
            reason=role,
            requires_verification=True,
            bracket_role=role,
            live_after_ts="",  # fill this bar at open
        )
        state["buy_count"] = n
        state["last_buy_ts"] = bar.ts
        self.state = state
        self.save_state()
        return StrategyActions([intent], [], [], [], [])

    def _daily_bars(self, bar: Bar) -> List[Bar]:
        if self._daily_bars_cache is None:
            self._daily_bars_cache = list(self.store.read_bars(self.instance.instrument, "D"))
        if not self._daily_bars_cache or self._daily_bars_cache[-1].ts != bar.ts:
            self._daily_bars_cache.append(bar)
        return self._daily_bars_cache
