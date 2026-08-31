"""Monday opening-range breakout with DD cuts + optional shifted primary.

Rules (NY clock, 15m bars)
--------------------------
- Monday OR high/low; R = high − low.
- Tue→Fri: long on close > Mon high, short on close < Mon low.
- Enter ``entry_qty`` (default 3). Stop distance 1R; target ``reward_R`` × R.
- DD cuts toward stop: drop ``dd30_qty`` @ 30%, flatten last ``dd50_qty`` @ 50%
  (no runner past 50%).
- Optional HTF filter: skip when last completed 1h bar has both MA50/150 and
  OBV vs OBV-SMA20 opposed to the trade.
- Optional shifted primary: after flat@50%, arm opposite Mon extreme breakout
  with the same structure (does not count toward max primary/week).
- Max ``max_trades_per_week`` primary entries/week; Fri week-end flatten @ NY 15:59
  (not daily — Tue–Thu hold through the week).
- Optional ``week_sitout_after_pts``: after realized week net (price points) reaches
  this threshold, skip further primary/shifted entries until the next Monday week
  (XAUUSD ``M2_S2_R3`` core: 100; USDJPY ``M2_S3_R1``: ~3). Open trades still
  manage to TP/SL/week_end.
- Optional ``skip_after_win_streak`` / ``skip_after_win_n``: after N consecutive
  *taken* wins, skip the next M entry signals (primary or shifted). Used by
  USDJPY ``M2_S3_R2`` (2W→skip1), EURUSD/GBPUSD (1W→skip1).
- Optional ``skip_entry_months``: list of calendar months (1–12, NY) with no new
  primary/shifted entries (XAUUSD core: July, September, December).
"""

from __future__ import annotations

import json
from datetime import datetime, time as dt_time, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot

NY = pytz.timezone("America/New_York")
UTC = pytz.UTC
# Friday week-end flatten clock (America/New_York). Left-labeled 15m bars that
# cover this instant (ts=15:45 → [15:45, 16:00)) trigger flatten when processed.
WEEK_END_FLATTEN_NY = dt_time(15, 59)
BAR_MINUTES_15M = 15


def _friday_week_end_due(dt: datetime) -> bool:
    """True on Friday once the bar covers/passes NY ``WEEK_END_FLATTEN_NY``.

    Uses left-labeled bar start ``dt``: bar end = dt + 15m. Flatten when
    bar_end > 15:59 Friday so the 15:45 bar (covers 15:59) fires, not Tue–Thu.
    """
    if dt.weekday() != 4:
        return False
    bar_end = dt + timedelta(minutes=BAR_MINUTES_15M)
    end_clock = bar_end.timetz().replace(tzinfo=None) if bar_end.tzinfo else bar_end.time()
    return end_clock > WEEK_END_FLATTEN_NY


class MondayOrBreakoutStrategy(StrategyPlugin):
    strategy_type = "monday_or_breakout"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.00001,
            "entry_qty": 3,
            "dd30_qty": 2,
            "dd50_qty": 1,
            "shifted_entry_qty": None,  # default: same as entry_qty
            "shifted_dd30_qty": None,
            "shifted_dd50_qty": None,
            "dd30_frac": 0.30,
            "dd50_frac": 0.50,
            "reward_R": 2.0,
            "max_trades_per_week": 2,
            "skip_both_opposed": True,
            "shifted_primary": True,
            "obv_ma": 20,
            "min_R": 1e-5,
            # 0 / None = disabled. XAUUSD M2_S2_R3 core uses 100 (gold price pts).
            "week_sitout_after_pts": 0.0,
            "week_sitout_blocks_shifted": True,
            # 0 = off. After this many consecutive taken wins, skip next skip_after_win_n signals.
            "skip_after_win_streak": 0,
            "skip_after_win_n": 1,
            # Calendar months (1–12, America/New_York) with no new entries. XAUUSD: [7,9,12].
            "skip_entry_months": [],
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def _main_sizing(self) -> Tuple[int, int, int]:
        return (
            int(self.config["entry_qty"]),
            int(self.config["dd30_qty"]),
            int(self.config["dd50_qty"]),
        )

    def _shifted_sizing(self) -> Tuple[int, int, int]:
        e, d30, d50 = self._main_sizing()
        se = self.config.get("shifted_entry_qty")
        s30 = self.config.get("shifted_dd30_qty")
        s50 = self.config.get("shifted_dd50_qty")
        return (
            int(se) if se is not None else e,
            int(s30) if s30 is not None else d30,
            int(s50) if s50 is not None else d50,
        )
    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "15m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_15m(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            entry = float(fill.price)
            R = float(trade.get("R") or state.get("R") or 0.0)
            reward = float(self.config["reward_R"])
            f30 = float(self.config.get("dd30_frac") or 0.30)
            f50 = float(self.config.get("dd50_frac") or 0.50)
            if direction == "Long":
                stop = entry - R
                target = entry + reward * R
                dd30 = entry - f30 * R
                dd50 = entry - f50 * R
            else:
                stop = entry + R
                target = entry - reward * R
                dd30 = entry + f30 * R
                dd50 = entry + f50 * R
            trade.update(
                {
                    "status": "open",
                    "direction": direction,
                    "entry_price": entry,
                    "entry_qty": int(fill.quantity),
                    "remaining": int(fill.quantity),
                    "stop": stop,
                    "target": target,
                    "dd30": dd30,
                    "dd50": dd50,
                    "is_shifted": bool(trade.get("is_shifted")),
                    "dd30_qty": int(trade.get("dd30_qty") or self.config["dd30_qty"]),
                    "dd50_qty": int(trade.get("dd50_qty") or self.config["dd50_qty"]),
                    "realized_pts": 0.0,
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            orders.extend(self._exit_orders(fill.trade_id, direction, trade))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role == "dd30":
            rem = max(0, int(trade.get("remaining") or 0) - int(fill.quantity))
            trade["remaining"] = rem
            trade["cut_30"] = int(trade.get("cut_30") or 0) + int(fill.quantity)
            self._accumulate_week_pts(state, trade, fill)
            # Shrink target to remaining
            cancels.extend(self._cancel_roles(context, fill.trade_id, {"target"}))
            if rem > 0:
                orders.append(
                    self._limit_exit(
                        fill.trade_id,
                        trade["direction"],
                        rem,
                        float(trade["target"]),
                        "target",
                    )
                )
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"dd50", "stop", "target", "week_end", "flatten"}:
            rem = max(0, int(trade.get("remaining") or 0) - int(fill.quantity))
            trade["remaining"] = rem
            self._accumulate_week_pts(state, trade, fill)
            if role == "dd50":
                trade["cut_50"] = int(trade.get("cut_50") or 0) + int(fill.quantity)
                trade["flat_at_50"] = True
            if rem <= 0 or context.position_quantity == 0:
                trade["status"] = "closed"
                state["current_leg_open"] = False
                state["active_trade_id"] = ""
                cancels.extend(self._cancel_reduce(context, fill.trade_id))
                self._on_trade_closed(state, trade)
                # Arm shifted primary after flat@50% (primary only) — unless week sitout / skip blocks it
                if (
                    bool(self.config.get("shifted_primary"))
                    and role == "dd50"
                    and not bool(trade.get("is_shifted"))
                    and not state.get("pending_shift_side")
                    and not self._week_sitout_active(state, for_shifted=True)
                    and int(state.get("skip_rem") or 0) <= 0
                ):
                    direction = str(trade.get("direction") or "")
                    state["pending_shift_side"] = "Short" if direction == "Long" else "Long"
                    state["pending_shift_parent"] = fill.trade_id
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])
        self._commit_state(state)
        return StrategyActions.empty()

    def _on_15m(self, bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_ny(bar.ts)
        state = self._state()
        self._update_htf(state, bar, dt)

        week_key = _week_monday_key(dt)
        if state.get("week_monday") != week_key:
            # New week — flatten leftovers from prior week if any
            orders: List[OrderIntent] = []
            cancels: List[CancelIntent] = []
            if context.position_quantity != 0:
                cancels.extend(self._cancel_all(context))
                orders.append(self._flatten(context, bar.ts, "week_end"))
            state = self._fresh_week(week_key)
            self._commit_state(state)
            if orders or cancels:
                return StrategyActions(orders, cancels, [], [], [])

        orders = []
        cancels = []
        wd = dt.weekday()  # Mon=0 … Sun=6

        # Build Monday OR
        if wd == 0:
            hi = float(state["mon_high"]) if state.get("mon_high") is not None else bar.high
            lo = float(state["mon_low"]) if state.get("mon_low") is not None else bar.low
            state["mon_high"] = max(hi, bar.high)
            state["mon_low"] = min(lo, bar.low)
            state["R"] = float(state["mon_high"]) - float(state["mon_low"])
            state["mon_last_ts"] = bar.ts
            state["mon_available_at_ts"] = bar.ts
            self._commit_state(state)
            return StrategyActions.empty()

        # Sat/Sun — ignore
        if wd >= 5:
            self._commit_state(state)
            return StrategyActions.empty()

        R = float(state.get("R") or 0.0)
        mon_high = state.get("mon_high")
        mon_low = state.get("mon_low")
        if mon_high is None or mon_low is None or R < float(self.config["min_R"]):
            self._commit_state(state)
            return StrategyActions.empty()

        # Friday week-end flatten at NY 15:59 (left-labeled 15m: fires on 15:45 bar).
        # Not daily — Tue–Thu never hit this path.
        if _friday_week_end_due(dt):
            if context.position_quantity != 0 or self._has_open_entry(context):
                cancels.extend(self._cancel_all(context))
                if context.position_quantity != 0:
                    orders.append(self._flatten(context, bar.ts, "week_end"))
                state["pending_shift_side"] = ""
                state["done_week"] = True
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if state.get("done_week"):
            self._commit_state(state)
            return StrategyActions.empty()

        if context.position_quantity != 0 or state.get("current_leg_open") or self._has_open_entry(context):
            self._commit_state(state)
            return StrategyActions.empty()

        close = float(bar.close)
        pending = state.get("pending_shift_side") or ""

        # Calendar month blackout (NY): no new primary/shifted entries.
        if self._month_entry_blocked(dt):
            if pending:
                state["pending_shift_side"] = ""
            self._commit_state(state)
            return StrategyActions.empty()

        # Week sitout: skip new risk after heat threshold (open trades still managed).
        if self._week_sitout_active(state, for_shifted=False) and not pending:
            self._commit_state(state)
            return StrategyActions.empty()

        # Shifted sidecar first (owns opposite extreme)
        if pending:
            if self._week_sitout_active(state, for_shifted=True):
                state["pending_shift_side"] = ""
                self._commit_state(state)
                return StrategyActions.empty()
            hit = (close < float(mon_low)) if pending == "Short" else (close > float(mon_high))
            if hit:
                side = "short" if pending == "Short" else "long"
                htf_block = self._htf_blocks(state, side)
                features = self._decision_features(
                    bar,
                    state,
                    pending,
                    side=side,
                    stage="shifted",
                    htf_blocked=htf_block,
                    allowed=not htf_block,
                )
                if htf_block:
                    self._commit_state(state)
                    return StrategyActions([], [], [], [], [], features)
                if self._consume_skip_signal(state):
                    state["pending_shift_side"] = ""
                    self._commit_state(state)
                    features.extend(
                        self._operational_gate_features(
                            bar, state, pending, stage="shifted", reason="skip_after_win"
                        )
                    )
                    return StrategyActions([], [], [], [], [], features)
                trade_id = new_id("trade")
                se, s30, s50 = self._shifted_sizing()
                self._trade(trade_id, state).update(
                    {
                        "status": "pending_entry",
                        "is_shifted": True,
                        "R": R,
                        "parent": state.get("pending_shift_parent") or "",
                        "dd30_qty": s30,
                        "dd50_qty": s50,
                    }
                )
                state["pending_shift_side"] = ""
                orders.append(self._entry_order(trade_id, pending, bar.ts, se))
                self._commit_state(state)
                return StrategyActions(orders, cancels, [], [], [], features)
            # Opposite extreme reserved while armed
            if (pending == "Short" and close < float(mon_low)) or (
                pending == "Long" and close > float(mon_high)
            ):
                self._commit_state(state)
                return StrategyActions.empty()

        if self._week_sitout_active(state, for_shifted=False):
            self._commit_state(state)
            return StrategyActions.empty()

        primary_count = int(state.get("primary_count") or 0)
        if primary_count >= int(self.config["max_trades_per_week"]):
            self._commit_state(state)
            return StrategyActions.empty()

        direction = None
        if close > float(mon_high):
            direction = "Long"
        elif close < float(mon_low):
            direction = "Short"
        if direction is None:
            self._commit_state(state)
            return StrategyActions.empty()
        if pending and direction == pending:
            self._commit_state(state)
            return StrategyActions.empty()

        side = "long" if direction == "Long" else "short"
        htf_block = self._htf_blocks(state, side)
        features = self._decision_features(
            bar,
            state,
            direction,
            side=side,
            stage="primary",
            htf_blocked=htf_block,
            allowed=not htf_block,
        )
        if htf_block:
            self._commit_state(state)
            return StrategyActions([], [], [], [], [], features)
        if self._consume_skip_signal(state):
            self._commit_state(state)
            features.extend(
                self._operational_gate_features(
                    bar, state, direction, stage="primary", reason="skip_after_win"
                )
            )
            return StrategyActions([], [], [], [], [], features)

        trade_id = new_id("trade")
        me, m30, m50 = self._main_sizing()
        self._trade(trade_id, state).update(
            {
                "status": "pending_entry",
                "is_shifted": False,
                "R": R,
                "parent": "",
                "dd30_qty": m30,
                "dd50_qty": m50,
            }
        )
        state["primary_count"] = primary_count + 1
        orders.append(self._entry_order(trade_id, direction, bar.ts, me))
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [], features)

    # --- HTF -----------------------------------------------------------------
    def _update_htf(self, state: Dict[str, Any], bar, dt: datetime) -> None:
        hour_key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
        cur = state.get("htf_hour_key")
        if cur != hour_key:
            if cur and state.get("htf_o") is not None:
                self._finalize_htf_hour(state, available_at_ts=dt.isoformat())
            state["htf_hour_key"] = hour_key
            state["htf_o"] = float(bar.open)
            state["htf_h"] = float(bar.high)
            state["htf_l"] = float(bar.low)
            state["htf_c"] = float(bar.close)
            state["htf_v"] = float(bar.volume or 0.0)
        else:
            state["htf_h"] = max(float(state["htf_h"]), float(bar.high))
            state["htf_l"] = min(float(state["htf_l"]), float(bar.low))
            state["htf_c"] = float(bar.close)
            state["htf_v"] = float(state.get("htf_v") or 0.0) + float(bar.volume or 0.0)

    def _finalize_htf_hour(self, state: Dict[str, Any], *, available_at_ts: str) -> None:
        closes: List[float] = list(state.get("htf_closes") or [])
        obvs: List[float] = list(state.get("htf_obvs") or [])
        c = float(state["htf_c"])
        prev_c = closes[-1] if closes else c
        direction = 0.0 if c == prev_c else (1.0 if c > prev_c else -1.0)
        vol = float(state.get("htf_v") or 0.0)
        proxy = max(float(state["htf_h"]) - float(state["htf_l"]), 1e-8)
        use_vol = vol if vol > 0 else proxy
        prev_obv = obvs[-1] if obvs else 0.0
        obv = prev_obv + direction * use_vol
        closes.append(c)
        obvs.append(obv)
        # Keep tail for MA150 / OBV MA
        max_keep = 200
        if len(closes) > max_keep:
            closes = closes[-max_keep:]
            obvs = obvs[-max_keep:]
        state["htf_closes"] = closes
        state["htf_obvs"] = obvs
        ma50 = _sma(closes, 50)
        ma150 = _sma(closes, 150)
        obv_ma = _sma(obvs, int(self.config.get("obv_ma") or 20))
        state["htf_ma50"] = ma50
        state["htf_ma150"] = ma150
        state["htf_obv_ma"] = obv_ma
        state["htf_obv"] = obv
        if ma50 is not None and ma150 is not None:
            state["htf_ma_bull"] = bool(ma50 > ma150)
        if obv_ma is not None:
            state["htf_obv_bull"] = bool(obv > obv_ma)
        state["htf_last_event_ts"] = str(state.get("htf_hour_key") or available_at_ts)
        state["htf_last_available_at_ts"] = available_at_ts

    def _htf_blocks(self, state: Dict[str, Any], side: str) -> bool:
        if not bool(self.config.get("skip_both_opposed")):
            return False
        if "htf_ma_bull" not in state or "htf_obv_bull" not in state:
            return False
        ma_bull = bool(state["htf_ma_bull"])
        obv_bull = bool(state["htf_obv_bull"])
        if side == "long":
            return (not ma_bull) and (not obv_bull)
        return ma_bull and obv_bull

    def _decision_features(
        self,
        bar,
        state: Dict[str, Any],
        direction: str,
        *,
        side: str,
        stage: str,
        htf_blocked: bool,
        allowed: bool,
    ) -> List[Any]:
        """Feature snapshots for a Monday-OR entry decision.

        The plugin runs on 15m bars. The driver uses left-labeled bars, so a
        signal created on bar ``ts`` can only fill on a later 15m bar because
        PaperBroker requires ``fill_bar.ts > live_after_ts``.
        """

        mon_high = state.get("mon_high")
        mon_low = state.get("mon_low")
        R = float(state.get("R") or 0.0)
        out = [
            feature_snapshot(
                self.instance,
                "monday_or_range",
                bar.ts,
                event_ts=str(state.get("mon_last_ts") or bar.ts),
                available_at_ts=str(state.get("mon_available_at_ts") or state.get("mon_last_ts") or bar.ts),
                source="completed_15m_monday_range",
                value_ref="%s/%s" % (mon_high, mon_low),
                metadata={
                    "week_monday": state.get("week_monday"),
                    "R": R,
                    "stage": stage,
                    "direction": direction,
                    "primary_count": state.get("primary_count"),
                    "max_trades_per_week": self.config.get("max_trades_per_week"),
                },
            ),
            feature_snapshot(
                self.instance,
                "monday_or_breakout_gate",
                bar.ts,
                source="completed_15m_close",
                value_ref="%s:%s" % (direction, "allowed" if allowed else "blocked"),
                metadata={
                    "stage": stage,
                    "direction": direction,
                    "side": side,
                    "close": float(bar.close),
                    "mon_high": mon_high,
                    "mon_low": mon_low,
                    "R": R,
                    "htf_blocked": bool(htf_blocked),
                    "skip_both_opposed": bool(self.config.get("skip_both_opposed")),
                },
            ),
        ]
        if "htf_ma_bull" in state or "htf_obv_bull" in state:
            out.append(
                feature_snapshot(
                    self.instance,
                    "monday_or_htf_filter",
                    bar.ts,
                    event_ts=str(state.get("htf_last_event_ts") or state.get("htf_hour_key") or bar.ts),
                    available_at_ts=str(state.get("htf_last_available_at_ts") or bar.ts),
                    source="completed_1h_from_15m",
                    value_ref="%s:%s" % (side, "blocked" if htf_blocked else "allowed"),
                    metadata={
                        "side": side,
                        "ma_bull": state.get("htf_ma_bull"),
                        "obv_bull": state.get("htf_obv_bull"),
                        "ma50": state.get("htf_ma50"),
                        "ma150": state.get("htf_ma150"),
                        "obv": state.get("htf_obv"),
                        "obv_ma": state.get("htf_obv_ma"),
                        "obv_ma_len": self.config.get("obv_ma"),
                    },
                )
            )
        return out

    def _operational_gate_features(
        self,
        bar,
        state: Dict[str, Any],
        direction: str,
        *,
        stage: str,
        reason: str,
    ) -> List[Any]:
        return [
            feature_snapshot(
                self.instance,
                "monday_or_operational_gate",
                bar.ts,
                source="strategy_state",
                value_ref="%s:%s" % (direction, reason),
                metadata={
                    "stage": stage,
                    "reason": reason,
                    "skip_rem": state.get("skip_rem"),
                    "consec_wins": state.get("consec_wins"),
                    "week_sitout": state.get("week_sitout"),
                    "skip_entry_months": self.config.get("skip_entry_months"),
                    "week_sitout_after_pts": self.config.get("week_sitout_after_pts"),
                },
            )
        ]

    # --- orders --------------------------------------------------------------
    def _entry_order(self, trade_id: str, direction: str, ts: str, qty: int) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy" if direction == "Long" else "sell",
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=True,
            bracket_role="entry",
            live_after_ts=ts,
        )

    def _exit_orders(self, trade_id: str, direction: str, trade: Dict[str, Any]) -> List[OrderIntent]:
        exit_side = "sell" if direction == "Long" else "buy"
        dd30_qty = int(trade.get("dd30_qty") if trade.get("dd30_qty") is not None else self.config["dd30_qty"])
        dd50_qty = int(trade.get("dd50_qty") if trade.get("dd50_qty") is not None else self.config["dd50_qty"])
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        out: List[OrderIntent] = []
        if dd30_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="stop",
                    quantity=dd30_qty,
                    stop_price=float(trade["dd30"]),
                    reason="dd30",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="dd30",
                )
            )
        if dd50_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="stop",
                    quantity=dd50_qty,
                    stop_price=float(trade["dd50"]),
                    reason="dd50",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="dd50",
                )
            )
        out.append(
            self._limit_exit(trade_id, direction, entry_qty, float(trade["target"]), "target")
        )
        return out

    def _limit_exit(
        self, trade_id: str, direction: str, qty: int, price: float, reason: str
    ) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if direction == "Long" else "buy",
            order_type="limit",
            quantity=qty,
            limit_price=price,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
        )

    def _flatten(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if context.position_quantity > 0 else "buy",
            order_type="market",
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            live_after_ts=ts,
        )

    def _cancel_roles(self, context: StrategyContext, trade_id: str, roles) -> List[CancelIntent]:
        role_set = set(roles)
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "mon_or_cancel_%s" % order.bracket_role)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.bracket_role in role_set
        ]

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "mon_or_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "mon_or_cancel_all")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry(self, context: StrategyContext) -> bool:
        return any(not order.reduce_only for order in context.strategy_open_orders)

    # --- state ---------------------------------------------------------------
    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "trades" not in raw:
            raw["trades"] = {}
        self.state = raw
        return raw

    def _fresh_week(self, week_key: str) -> Dict[str, Any]:
        prev_htf = {
            k: self.state.get(k)
            for k in (
                "htf_closes",
                "htf_obvs",
                "htf_ma50",
                "htf_ma150",
                "htf_obv",
                "htf_obv_ma",
                "htf_ma_bull",
                "htf_obv_bull",
                "htf_hour_key",
                "htf_last_event_ts",
                "htf_last_available_at_ts",
                "htf_o",
                "htf_h",
                "htf_l",
                "htf_c",
                "htf_v",
            )
            if k in self.state
        }
        # Win-streak skip is book-lifetime (not Mon-week local).
        prev_skip = {
            k: self.state.get(k)
            for k in ("consec_wins", "skip_rem")
            if k in self.state
        }
        state: Dict[str, Any] = {
            "week_monday": week_key,
            "mon_high": None,
            "mon_low": None,
            "mon_last_ts": "",
            "mon_available_at_ts": "",
            "R": 0.0,
            "primary_count": 0,
            "pending_shift_side": "",
            "pending_shift_parent": "",
            "current_leg_open": False,
            "active_trade_id": "",
            "done_week": False,
            "week_realized_pts": 0.0,
            "week_sitout": False,
            "consec_wins": int(prev_skip.get("consec_wins") or 0),
            "skip_rem": int(prev_skip.get("skip_rem") or 0),
            "trades": {},
        }
        state.update(prev_htf)
        self.state = state
        return state

    def _week_sitout_threshold(self) -> float:
        try:
            return float(self.config.get("week_sitout_after_pts") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _skip_entry_months(self) -> set:
        raw = self.config.get("skip_entry_months") or []
        out = set()
        if isinstance(raw, (list, tuple)):
            for m in raw:
                try:
                    mi = int(m)
                except (TypeError, ValueError):
                    continue
                if 1 <= mi <= 12:
                    out.add(mi)
        return out

    def _month_entry_blocked(self, dt: datetime) -> bool:
        months = self._skip_entry_months()
        if not months:
            return False
        return int(dt.month) in months

    def _week_sitout_active(self, state: Dict[str, Any], *, for_shifted: bool) -> bool:
        thr = self._week_sitout_threshold()
        if thr <= 0:
            return False
        if for_shifted and not bool(self.config.get("week_sitout_blocks_shifted", True)):
            return False
        if state.get("week_sitout"):
            return True
        return float(state.get("week_realized_pts") or 0.0) >= thr

    def _skip_streak_need(self) -> int:
        try:
            return int(self.config.get("skip_after_win_streak") or 0)
        except (TypeError, ValueError):
            return 0

    def _skip_streak_n(self) -> int:
        try:
            return max(1, int(self.config.get("skip_after_win_n") or 1))
        except (TypeError, ValueError):
            return 1

    def _consume_skip_signal(self, state: Dict[str, Any]) -> bool:
        """If a post-win skip is armed, consume one signal and return True (do not enter)."""
        if self._skip_streak_need() <= 0:
            return False
        rem = int(state.get("skip_rem") or 0)
        if rem <= 0:
            return False
        state["skip_rem"] = rem - 1
        return True

    def _on_trade_closed(self, state: Dict[str, Any], trade: Dict[str, Any]) -> None:
        need = self._skip_streak_need()
        if need <= 0:
            return
        pts = float(trade.get("realized_pts") or 0.0)
        if pts > 0:
            consec = int(state.get("consec_wins") or 0) + 1
            if consec >= need:
                state["skip_rem"] = int(state.get("skip_rem") or 0) + self._skip_streak_n()
                state["consec_wins"] = 0
            else:
                state["consec_wins"] = consec
        else:
            state["consec_wins"] = 0

    def _accumulate_week_pts(self, state: Dict[str, Any], trade: Dict[str, Any], fill) -> None:
        """Add realized price points from a reduce fill; arm week sitout if threshold hit."""
        thr = self._week_sitout_threshold()
        entry = trade.get("entry_price")
        if entry is None:
            return
        qty = float(fill.quantity or 0)
        px = float(fill.price)
        direction = str(trade.get("direction") or "")
        if direction == "Long":
            pts = (px - float(entry)) * qty
        elif direction == "Short":
            pts = (float(entry) - px) * qty
        else:
            return
        trade["realized_pts"] = float(trade.get("realized_pts") or 0.0) + pts
        state["week_realized_pts"] = float(state.get("week_realized_pts") or 0.0) + pts
        if thr > 0 and float(state["week_realized_pts"]) >= thr:
            state["week_sitout"] = True

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]


def _parse_ny(ts: str) -> datetime:
    value = str(ts).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    # OANDA can emit nanosecond fractions; fromisoformat (3.8) accepts ≤6 digits.
    if "." in value:
        head, rest = value.split(".", 1)
        frac = ""
        tz = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                frac += ch
            else:
                tz = rest[i:]
                break
        value = "%s.%s%s" % (head, (frac + "000000")[:6], tz)
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
        dt = UTC.localize(dt)
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(NY)


def _week_monday_key(dt: datetime) -> str:
    d = dt.date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def _sma(vals: List[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    return float(sum(vals[-n:]) / n)
