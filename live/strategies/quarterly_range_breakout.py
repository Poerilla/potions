"""Quarterly prior-range honest breakout (daily bars).

Breakout requires a daily **close** outside the prior-quarter range:
  close > prior_high → market long; close < prior_low → market short.
  Fills next open via ``live_after_ts``.

Honest risk / scale:
  - SL fixed at prior-range **mid** (halfway). No BE move.
  - Scale **2** contracts every **0.2 ×** prior width from entry
    (0.2 / 0.4 / 0.6 / 0.8 for an 8-lot book).
  - Multiple breakouts per quarter while flat; flatten at quarter end.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from ..models import Bar, CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin


class QuarterlyRangeBreakoutStrategy(StrategyPlugin):
    strategy_type = "quarterly_range_breakout"
    version = "v2_mid_sidecar"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 8,
            "scale_qty": 2,
            "scale_step_width_mult": 0.2,
            "timeframe": "D",
            "suppress_alerts": True,
            # None / empty / both → long+short. Use ["long"] for longs-only.
            "allowed_sides": ["long", "short"],
            # Empty → no Monthly-OR gate. Example: ["mor_up"] arms only when
            # causal Monthly OR direction is up (first-3-session OR; ready after
            # 3rd daily close). Matches HP tag ``mor_dir`` / Monthly OR direction.
            "require_mor_dirs": [],
            # Empty → no Yearly-ORB gate. Example: ["yor_up"] (Jan–Mar H/L OR;
            # ready Apr 1). Matches HP tag ``yor_dir``.
            "require_yor_dirs": [],
            # Empty → no Weekly-ATR-align gate. Example: ["w_atr_aligned"]
            # (Weekly ATR SuperTrend 14×3 vs trade side). Matches HP ``w_atr_align``.
            "require_w_atr_aligns": [],
            # Large-width mid-stop sidecar (separate strategy instance when enabled
            # via driver): main publishes signals; sidecar_only instance enters with
            # same risk magnitude, targets 1R..4R, carries past EOQ on BE stop, and
            # never blocks main (separate position).
            "enable_mid_sidecar": False,
            "mode": "main",  # main | sidecar_only
            "main_strategy_id": "",
            "sidecar_min_width_quantile": 0.75,
            "sidecar_min_hist": 8,
            "sidecar_min_prior_width": 0.0,
            "sidecar_r_targets": [1.0, 2.0, 3.0, 4.0],
            "sidecar_eoq": "be_carry",  # be_carry | flatten
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        want = str(self.config.get("timeframe") or "D")
        if bar.timeframe != want or not bar.complete:
            return StrategyActions.empty()
        return self._on_daily(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")
        sidecar_only = self._sidecar_only()

        if role in {"entry", "sidecar_entry"}:
            entry = float(fill.price)
            width = float(state.get("prior_width") or 0.0)
            direction = str(trade.get("direction") or "")
            mid = _to_float(state.get("prior_mid"))
            is_sidecar = bool(trade.get("is_sidecar")) or role == "sidecar_entry" or sidecar_only
            scale_qty = int(self.config.get("scale_qty") or 2)
            entry_qty = int(trade.get("entry_qty") or self.config.get("entry_qty") or 8)
            if is_sidecar:
                risk_pts = float(
                    trade.get("risk_pts")
                    or state.get("pending_sidecar_risk_pts")
                    or 0.0
                )
                if risk_pts <= 0 and mid is not None:
                    risk_pts = abs(entry - float(mid))
                if direction == "long":
                    stop_px = entry - risk_pts
                else:
                    stop_px = entry + risk_pts
                # 1R..4R profit ladder (same R as stop magnitude).
                r_tgts = [float(x) for x in (self.config.get("sidecar_r_targets") or [1, 2, 3, 4])]
                targets = []
                for mult in r_tgts:
                    dist = risk_pts * mult
                    targets.append(entry + dist if direction == "long" else entry - dist)
            else:
                step = float(self.config.get("scale_step_width_mult") or 0.2)
                n_scales = max(1, entry_qty // max(scale_qty, 1))
                targets = []
                for i in range(1, n_scales + 1):
                    dist = step * i * width
                    targets.append(entry + dist if direction == "long" else entry - dist)
                stop_px = float(mid) if mid is not None else None
                risk_pts = abs(entry - float(stop_px)) if stop_px is not None else 0.0
            trade.update(
                {
                    "status": "open",
                    "is_sidecar": is_sidecar,
                    "entry_price": entry,
                    "entry_ts": fill.ts,
                    "filled_qty": int(fill.quantity),
                    "risk_pts": float(risk_pts),
                    "stop": stop_px,
                    "targets": targets,
                    "scale_qty": scale_qty,
                    "scales_done": 0,
                    "remaining_qty": entry_qty,
                    "be_active": False,
                }
            )
            if is_sidecar:
                state["sidecar_open"] = True
                state["sidecar_pending"] = False
                state["sidecar_trade_id"] = fill.trade_id
                state["pending_sidecar_risk_pts"] = None
            else:
                state["main_open"] = True
                state["main_entry_pending"] = False
                state["main_trade_id"] = fill.trade_id
                state["last_main_risk_pts"] = float(risk_pts)
            state["active_trade_id"] = fill.trade_id
            self._sync_leg_flags(state)
            orders = self._exit_orders(fill.trade_id, direction, state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role.startswith("tp") or role == "scale":
            scales_done = int(trade.get("scales_done") or 0) + 1
            trade["scales_done"] = scales_done
            booked = max(0, int(trade.get("remaining_qty") or 0) - int(fill.quantity))
            trade["remaining_qty"] = booked
            rem_qty = booked
            # Only resize the protective stop; leave resting TP limits alone so
            # same-bar multi-target fills and the original ladder stay intact.
            cancels = self._cancel_open_roles(context, fill.trade_id, {"stop"})
            orders: List[OrderIntent] = []
            if rem_qty > 0:
                stop = _to_float(trade.get("stop"))
                direction = str(trade.get("direction") or "")
                if stop is not None and direction in {"long", "short"}:
                    exit_side = "sell" if direction == "long" else "buy"
                    orders.append(
                        OrderIntent.create(
                            strategy_id=self.instance.strategy_id,
                            trade_id=fill.trade_id,
                            instrument=self.instance.instrument,
                            account_mode=self.instance.account_mode,
                            side=exit_side,
                            order_type="stop",
                            quantity=rem_qty,
                            stop_price=float(stop),
                            reason="stop",
                            requires_verification=False,
                            reduce_only=True,
                            bracket_role="stop",
                            expires_after_ts=self._exit_expiry(state, trade),
                        )
                    )
            else:
                cancels.extend(
                    self._cancel_open_roles(
                        context,
                        fill.trade_id,
                        {"stop", "tp1", "tp2", "tp3", "tp4", "scale"},
                    )
                )
                self._close_trade_book(state, trade, fill.ts, role)
            if rem_qty <= 0 and (
                bool(trade.get("is_sidecar")) or sidecar_only
            ):
                state["sidecar_open"] = False
                state["sidecar_pending"] = False
                if str(state.get("sidecar_trade_id") or "") == str(fill.trade_id):
                    state["sidecar_trade_id"] = ""
                self._sync_leg_flags(state)
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"stop", "quarter_close"}:
            direction = str(trade.get("direction") or "")
            was_sidecar = bool(trade.get("is_sidecar")) or sidecar_only
            if role == "quarter_close":
                # Main EOQ flatten only (sidecar_only never emits quarter_close).
                for _tid, tr in list((state.get("trades") or {}).items()):
                    if str(tr.get("status") or "") == "open":
                        tr["remaining_qty"] = 0
                        self._close_trade_book(state, tr, fill.ts, role)
                state["main_open"] = False
                state["main_entry_pending"] = False
                self._sync_leg_flags(state)
                cancels = self._cancel_all_open(context, "position_flat")
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

            trade["remaining_qty"] = 0
            self._close_trade_book(state, trade, fill.ts, role)
            cancels = self._cancel_reduce_orders(context, fill.trade_id)
            # Main publishes sidecar signal for the separate sidecar instance.
            if (
                role == "stop"
                and not was_sidecar
                and not sidecar_only
                and direction in {"long", "short"}
                and self._sidecar_enabled()
                and self._width_is_large(state)
            ):
                risk_pts = float(
                    trade.get("risk_pts") or state.get("last_main_risk_pts") or 0.0
                )
                sigs = list(state.get("sidecar_signals") or [])
                sigs.append(
                    {
                        "id": "%s_%s" % (fill.trade_id, fill.ts),
                        "ts": fill.ts,
                        "direction": direction,
                        "risk_pts": risk_pts,
                        "prior_width": float(state.get("prior_width") or 0.0),
                        "prior_mid": state.get("prior_mid"),
                    }
                )
                state["sidecar_signals"] = sigs[-50:]
            self._commit_state(state)
            return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _close_trade_book(
        self, state: Dict[str, Any], trade: Dict[str, Any], ts: str, reason: str
    ) -> None:
        trade["status"] = "closed"
        trade["exit_ts"] = ts
        trade["exit_reason"] = reason
        if bool(trade.get("is_sidecar")) or self._sidecar_only():
            state["sidecar_open"] = False
            state["sidecar_trade_id"] = ""
            state["sidecar_pending"] = False
        else:
            state["main_open"] = False
            state["main_trade_id"] = ""
            state["main_entry_pending"] = False
        self._sync_leg_flags(state)

    def _sync_leg_flags(self, state: Dict[str, Any]) -> None:
        state["current_leg_open"] = bool(state.get("main_open") or state.get("sidecar_open"))
        state["entry_pending"] = bool(
            state.get("main_entry_pending") or state.get("sidecar_pending")
        )
        if state.get("main_open") and state.get("main_trade_id"):
            state["active_trade_id"] = state["main_trade_id"]
        elif state.get("sidecar_open") and state.get("sidecar_trade_id"):
            state["active_trade_id"] = state["sidecar_trade_id"]
        elif not state.get("main_entry_pending") and not state.get("sidecar_pending"):
            state["active_trade_id"] = ""

    def _sidecar_only(self) -> bool:
        return str(self.config.get("mode") or "main").strip().lower() == "sidecar_only"

    def _on_daily(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if self._sidecar_only():
            return self._on_daily_sidecar(bar, context)
        return self._on_daily_main(bar, context)

    def _on_daily_sidecar(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        """Separate-position sidecar: consume main signals, BE carry at EOQ, 1R..4R."""
        dt = _parse_ts(bar.ts)
        qkey = _quarter_key(dt)
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if state.get("quarter_key") != qkey:
            eoq_mode = str(self.config.get("sidecar_eoq") or "be_carry").strip().lower()
            if eoq_mode == "flatten" and (
                state.get("sidecar_open")
                or context.position_quantity != 0
                or state.get("sidecar_pending")
            ):
                cancels.extend(self._cancel_all_open(context, "quarter_roll"))
                if context.position_quantity != 0:
                    orders.append(
                        self._close_all_qty(context.position_quantity, bar.ts, "quarter_close")
                    )
                self._commit_state(state)
                if context.position_quantity != 0:
                    return StrategyActions(orders, cancels, [], [], [])
                state = self._roll_quarter_preserve_sidecar(state, qkey, dt)
            else:
                # Roll calendar first so re-armed exits use the new quarter (or GTC).
                state = self._roll_quarter_preserve_sidecar(state, qkey, dt)
                if state.get("sidecar_open") or context.position_quantity != 0:
                    # Carry past EOQ: move SL to BE, do not flatten.
                    sc_id = str(
                        state.get("sidecar_trade_id") or state.get("active_trade_id") or ""
                    )
                    trade = self._trade(sc_id, state) if sc_id else {}
                    if trade and str(trade.get("status") or "") == "open":
                        entry = _to_float(trade.get("entry_price"))
                        rem_raw = trade.get("remaining_qty")
                        rem = (
                            int(rem_raw)
                            if rem_raw is not None
                            else int(abs(context.position_quantity) or 0)
                        )
                        pos_qty = int(context.position_quantity or 0)
                        if rem <= 0 and pos_qty == 0:
                            # Final TP may leave a ghost open book; clear so new signals arm.
                            self._close_trade_book(state, trade, bar.ts, "flat_reconcile")
                        elif entry is not None and rem > 0:
                            # Move protective stop to BE only; keep resting TP limits.
                            cancels.extend(
                                self._cancel_open_roles(context, sc_id, {"stop"})
                            )
                            trade["stop"] = float(entry)
                            trade["be_active"] = True
                            direction = str(trade.get("direction") or "")
                            if direction in {"long", "short"}:
                                exit_side = "sell" if direction == "long" else "buy"
                                orders.append(
                                    OrderIntent.create(
                                        strategy_id=self.instance.strategy_id,
                                        trade_id=sc_id,
                                        instrument=self.instance.instrument,
                                        account_mode=self.instance.account_mode,
                                        side=exit_side,
                                        order_type="stop",
                                        quantity=rem,
                                        stop_price=float(entry),
                                        reason="stop",
                                        requires_verification=False,
                                        reduce_only=True,
                                        bracket_role="stop",
                                        expires_after_ts=self._exit_expiry(state, trade),
                                    )
                                )

        # Broker flat but sidecar flag still open (missed final-TP close).
        if (
            int(context.position_quantity or 0) == 0
            and state.get("sidecar_open")
            and not state.get("sidecar_pending")
        ):
            sc_id = str(state.get("sidecar_trade_id") or state.get("active_trade_id") or "")
            if sc_id:
                trade = self._trade(sc_id, state)
                if str(trade.get("status") or "") == "open":
                    self._close_trade_book(state, trade, bar.ts, "flat_reconcile")
            else:
                state["sidecar_open"] = False
                self._sync_leg_flags(state)

        self._update_building(state, bar)

        # Consume published signals from main strategy state.
        main_id = str(self.config.get("main_strategy_id") or "").strip()
        if main_id and not state.get("sidecar_open") and not state.get("sidecar_pending"):
            main_state = self.store.get_state(main_id) or {}
            consumed = set(str(x) for x in (state.get("consumed_signal_ids") or []))
            for sig in list(main_state.get("sidecar_signals") or []):
                sid = str(sig.get("id") or "")
                if not sid or sid in consumed:
                    continue
                direction = str(sig.get("direction") or "")
                risk_pts = float(sig.get("risk_pts") or 0.0)
                if direction not in {"long", "short"} or risk_pts <= 0:
                    consumed.add(sid)
                    continue
                intent = self._arm_entry(
                    bar.ts,
                    state,
                    direction=direction,
                    is_sidecar=True,
                    risk_pts=risk_pts,
                )
                if intent is not None:
                    orders.append(intent)
                    state["sidecar_pending"] = True
                    consumed.add(sid)
                    state["pending_sidecar_risk_pts"] = risk_pts
                    break  # one live sidecar at a time
            state["consumed_signal_ids"] = list(consumed)[-100:]

        self._sync_leg_flags(state)
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    def _on_daily_main(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_ts(bar.ts)
        qkey = _quarter_key(dt)
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if state.get("quarter_key") != qkey:
            if (
                context.position_quantity != 0
                or state.get("main_open")
                or state.get("main_entry_pending")
            ):
                cancels.extend(self._cancel_all_open(context, "quarter_roll"))
                if context.position_quantity != 0:
                    orders.append(self._close_all_qty(context.position_quantity, bar.ts, "quarter_close"))
                self._commit_state(state)
                if context.position_quantity != 0:
                    return StrategyActions(orders, cancels, [], [], [])
            state = self._roll_quarter(state, qkey, dt)

        self._update_building(state, bar)
        self._update_monthly_or(state, bar)
        self._update_yearly_or(state, bar)
        self._update_weekly_atr(state, bar)

        if not state.get("prior_ready"):
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        prior_high = float(state["prior_high"])
        prior_low = float(state["prior_low"])
        cl = float(bar.close)

        if not state.get("main_open") and not state.get("main_entry_pending"):
            direction = None
            if cl > prior_high:
                direction = "long"
            elif cl < prior_low:
                direction = "short"
            if direction is not None and not self._side_allowed(direction):
                direction = None
            if direction is not None and not self._mor_dir_allowed(state):
                direction = None
            if direction is not None and not self._yor_dir_allowed(state):
                direction = None
            if direction is not None and not self._w_atr_align_allowed(state, direction):
                direction = None
            if direction is not None:
                intent = self._arm_entry(bar.ts, state, direction=direction)
                if intent is not None:
                    orders.append(intent)
                    state["main_entry_pending"] = True
                    self._sync_leg_flags(state)

        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    def _roll_quarter_preserve_sidecar(
        self, state: Dict[str, Any], qkey: str, dt: datetime
    ) -> Dict[str, Any]:
        """Quarter roll for sidecar runner: keep open trade, advance calendar prior."""
        prior_high = state.get("q_high")
        prior_low = state.get("q_low")
        prior_ready = prior_high is not None and prior_low is not None
        width = (float(prior_high) - float(prior_low)) if prior_ready else 0.0
        mid = (float(prior_high) + float(prior_low)) * 0.5 if prior_ready else None
        hist = [float(x) for x in (state.get("prior_width_hist") or []) if x is not None]
        prev_w = state.get("prior_width")
        if prev_w is not None and float(prev_w) > 0:
            hist = hist + [float(prev_w)]
        state["quarter_key"] = qkey
        state["year"] = int(dt.year)
        state["quarter"] = int((dt.month - 1) // 3 + 1)
        state["q_high"] = None
        state["q_low"] = None
        state["prior_high"] = float(prior_high) if prior_ready else None
        state["prior_low"] = float(prior_low) if prior_ready else None
        state["prior_mid"] = float(mid) if mid is not None else None
        state["prior_width"] = float(width) if prior_ready and width > 0 else 0.0
        state["prior_ready"] = bool(prior_ready and width > 0)
        state["prior_width_hist"] = hist
        # Keep sidecar_open / trades / consumed ids.
        self.state = state
        return state

    def _require_mor_dirs(self) -> Set[str]:
        raw = self.config.get("require_mor_dirs") or []
        out: Set[str] = set()
        if isinstance(raw, str):
            parts = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, (list, tuple, set)):
            parts = [str(s).strip() for s in raw if str(s).strip()]
        else:
            return out
        for p in parts:
            key = p.lower()
            if not key.startswith("mor_"):
                key = "mor_%s" % key
            out.add(key)
        return out

    def _mor_dir_allowed(self, state: Dict[str, Any]) -> bool:
        want = self._require_mor_dirs()
        if not want:
            return True
        return str(state.get("mor_dir") or "mor_na") in want

    def _require_yor_dirs(self) -> Set[str]:
        raw = self.config.get("require_yor_dirs") or []
        out: Set[str] = set()
        if isinstance(raw, str):
            parts = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, (list, tuple, set)):
            parts = [str(s).strip() for s in raw if str(s).strip()]
        else:
            return out
        for p in parts:
            key = p.lower()
            if not key.startswith("yor_"):
                key = "yor_%s" % key
            out.add(key)
        return out

    def _yor_dir_allowed(self, state: Dict[str, Any]) -> bool:
        want = self._require_yor_dirs()
        if not want:
            return True
        return str(state.get("yor_dir") or "yor_na") in want

    def _require_w_atr_aligns(self) -> Set[str]:
        raw = self.config.get("require_w_atr_aligns") or []
        out: Set[str] = set()
        if isinstance(raw, str):
            parts = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, (list, tuple, set)):
            parts = [str(s).strip() for s in raw if str(s).strip()]
        else:
            return out
        for p in parts:
            key = p.lower()
            if not key.startswith("w_atr_"):
                key = "w_atr_%s" % key
            out.add(key)
        return out

    def _w_atr_align_for(self, state: Dict[str, Any], direction: str) -> str:
        trend = str(state.get("w_atr_trend") or "w_atr_na")
        if trend in {"", "w_atr_na"} or not direction:
            return "w_atr_na"
        d = direction.lower()
        if (d == "long" and trend == "w_atr_bull") or (d == "short" and trend == "w_atr_bear"):
            return "w_atr_aligned"
        if (d == "long" and trend == "w_atr_bear") or (d == "short" and trend == "w_atr_bull"):
            return "w_atr_opposed"
        return "w_atr_na"

    def _w_atr_align_allowed(self, state: Dict[str, Any], direction: str) -> bool:
        want = self._require_w_atr_aligns()
        if not want:
            return True
        return self._w_atr_align_for(state, direction) in want

    def _update_monthly_or(self, state: Dict[str, Any], bar: Bar) -> None:
        """Causal Monthly OR direction (first 3 sessions; ready after 3rd close)."""
        dt = _parse_ts(bar.ts)
        mkey = "%d-%02d" % (dt.year, dt.month)
        hi = float(bar.high)
        lo = float(bar.low)
        cl = float(bar.close)
        if state.get("month_key") != mkey:
            state["month_key"] = mkey
            state["month_sess"] = 0
            state["mor_high"] = None
            state["mor_low"] = None
            state["mor_ready"] = False
            state["mtd_high"] = None
            state["mtd_low"] = None
            state["mor_dir"] = "mor_na"
        state["month_sess"] = int(state.get("month_sess") or 0) + 1
        sess = int(state["month_sess"])
        if state.get("mtd_high") is None:
            state["mtd_high"] = hi
            state["mtd_low"] = lo
        else:
            state["mtd_high"] = max(float(state["mtd_high"]), hi)
            state["mtd_low"] = min(float(state["mtd_low"]), lo)
        if sess <= 3:
            if state.get("mor_high") is None:
                state["mor_high"] = hi
                state["mor_low"] = lo
            else:
                state["mor_high"] = max(float(state["mor_high"]), hi)
                state["mor_low"] = min(float(state["mor_low"]), lo)
            if sess >= 3:
                state["mor_ready"] = True
        if not state.get("mor_ready"):
            state["mor_dir"] = "mor_na"
            return
        mor_high = float(state["mor_high"])
        mor_low = float(state["mor_low"])
        mtd_high = float(state["mtd_high"])
        mtd_low = float(state["mtd_low"])
        m_up = mtd_high > mor_high
        m_dn = mtd_low < mor_low
        if cl > mor_high:
            state["mor_dir"] = "mor_up"
        elif cl < mor_low:
            state["mor_dir"] = "mor_down"
        elif m_up and not m_dn:
            state["mor_dir"] = "mor_up"
        elif m_dn and not m_up:
            state["mor_dir"] = "mor_down"
        elif m_up and m_dn:
            state["mor_dir"] = "mor_both"
        else:
            state["mor_dir"] = "mor_inside"

    def _update_yearly_or(self, state: Dict[str, Any], bar: Bar) -> None:
        """Causal Yearly ORB direction (Jan–Mar H/L; ready Apr 1)."""
        dt = _parse_ts(bar.ts)
        ykey = int(dt.year)
        hi = float(bar.high)
        lo = float(bar.low)
        cl = float(bar.close)
        if int(state.get("yor_year") or 0) != ykey:
            state["yor_year"] = ykey
            state["yor_high"] = None
            state["yor_low"] = None
            state["yor_ready"] = False
            state["ytd_high"] = None
            state["ytd_low"] = None
            state["yor_dir"] = "yor_na"
        if state.get("ytd_high") is None:
            state["ytd_high"] = hi
            state["ytd_low"] = lo
        else:
            state["ytd_high"] = max(float(state["ytd_high"]), hi)
            state["ytd_low"] = min(float(state["ytd_low"]), lo)
        # Build OR over Jan–Mar sessions.
        if dt.month <= 3:
            if state.get("yor_high") is None:
                state["yor_high"] = hi
                state["yor_low"] = lo
            else:
                state["yor_high"] = max(float(state["yor_high"]), hi)
                state["yor_low"] = min(float(state["yor_low"]), lo)
        # Ready from Apr 1 onward once OR levels exist.
        if dt.month >= 4 and state.get("yor_high") is not None and state.get("yor_low") is not None:
            state["yor_ready"] = True
        if not state.get("yor_ready"):
            state["yor_dir"] = "yor_na"
            return
        yor_high = float(state["yor_high"])
        yor_low = float(state["yor_low"])
        ytd_high = float(state["ytd_high"])
        ytd_low = float(state["ytd_low"])
        broke_up = ytd_high > yor_high
        broke_dn = ytd_low < yor_low
        if cl > yor_high:
            state["yor_dir"] = "yor_up"
        elif cl < yor_low:
            state["yor_dir"] = "yor_down"
        elif broke_up and not broke_dn:
            state["yor_dir"] = "yor_up"
        elif broke_dn and not broke_up:
            state["yor_dir"] = "yor_down"
        elif broke_up and broke_dn:
            state["yor_dir"] = "yor_both"
        else:
            state["yor_dir"] = "yor_inside"

    def _update_weekly_atr(self, state: Dict[str, Any], bar: Bar) -> None:
        """Causal Weekly ATR SuperTrend (14, ×3) on W-FRI bars; decision-bar complete."""
        dt = _parse_ts(bar.ts)
        week_key = _week_end_friday_key(dt)
        hi = float(bar.high)
        lo = float(bar.low)
        op = float(bar.open)
        cl = float(bar.close)
        cur = str(state.get("w_week_key") or "")
        if cur and cur != week_key:
            # Previous week complete → step SuperTrend, then start new week.
            self._finalize_weekly_atr_bar(state)
            state["w_week_key"] = week_key
            state["w_open"] = op
            state["w_high"] = hi
            state["w_low"] = lo
            state["w_close"] = cl
        elif not cur:
            state["w_week_key"] = week_key
            state["w_open"] = op
            state["w_high"] = hi
            state["w_low"] = lo
            state["w_close"] = cl
        else:
            state["w_high"] = max(float(state["w_high"]), hi)
            state["w_low"] = min(float(state["w_low"]), lo)
            state["w_close"] = cl
        # On Friday (week-end session), finalize this week's bar same day so
        # decision-bar gates see the completed week (mor_up-style causality).
        if dt.weekday() == 4 and state.get("w_week_key") == week_key:
            self._finalize_weekly_atr_bar(state, keep_week=True)

    def _finalize_weekly_atr_bar(self, state: Dict[str, Any], *, keep_week: bool = False) -> None:
        if state.get("w_open") is None:
            return
        o = float(state["w_open"])
        h = float(state["w_high"])
        l = float(state["w_low"])
        c = float(state["w_close"])
        # Avoid double-finalizing the same Friday week.
        last_key = str(state.get("w_st_last_week") or "")
        cur_key = str(state.get("w_week_key") or "")
        if keep_week and last_key == cur_key:
            return
        atr_len = 14
        mult = 3.0
        n = int(state.get("w_st_n") or 0)
        prev_close = state.get("w_st_prev_close")
        if prev_close is None:
            tr = h - l
        else:
            pc = float(prev_close)
            tr = max(h - l, abs(h - pc), abs(l - pc))
        alpha = 1.0 / float(atr_len)
        if n == 0:
            atr_run = float(tr)
        else:
            atr_run = (1.0 - alpha) * float(state.get("w_st_atr") or tr) + alpha * float(tr)
        state["w_st_atr"] = atr_run
        atr_ok = n >= (atr_len - 1)
        atr = atr_run if atr_ok else float("nan")
        hl2 = 0.5 * (h + l)
        if (not atr_ok) or atr != atr:
            basic_upper = hl2
            basic_lower = hl2
            final_upper = basic_upper
            final_lower = basic_lower
            trend = 1
        else:
            basic_upper = hl2 + mult * atr
            basic_lower = hl2 - mult * atr
            prev_fu = state.get("w_st_final_upper")
            prev_fl = state.get("w_st_final_lower")
            prev_trend = int(state.get("w_st_trend") or 1)
            prev_c = float(prev_close) if prev_close is not None else c
            if (
                prev_fu is None
                or basic_upper < float(prev_fu)
                or prev_c > float(prev_fu)
            ):
                final_upper = basic_upper
            else:
                final_upper = float(prev_fu)
            if (
                prev_fl is None
                or basic_lower > float(prev_fl)
                or prev_c < float(prev_fl)
            ):
                final_lower = basic_lower
            else:
                final_lower = float(prev_fl)
            if prev_trend == 1:
                trend = -1 if c < final_lower else 1
            else:
                trend = 1 if c > final_upper else -1
        state["w_st_final_upper"] = final_upper
        state["w_st_final_lower"] = final_lower
        state["w_st_trend"] = int(trend)
        state["w_st_prev_close"] = c
        state["w_st_n"] = n + 1
        state["w_st_last_week"] = cur_key
        # Trend only published once ATR warmup completes (matches research ST).
        if atr_ok:
            state["w_atr_trend"] = "w_atr_bull" if trend == 1 else "w_atr_bear"
        else:
            state["w_atr_trend"] = "w_atr_na"
        if not keep_week:
            state["w_open"] = None
            state["w_high"] = None
            state["w_low"] = None
            state["w_close"] = None
            state["w_week_key"] = ""

    def _side_allowed(self, direction: str) -> bool:
        raw = self.config.get("allowed_sides")
        if raw is None:
            return True
        if isinstance(raw, str):
            sides = [s.strip().lower() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, (list, tuple, set)):
            sides = [str(s).strip().lower() for s in raw if str(s).strip()]
        else:
            return True
        if not sides:
            return True
        return direction.lower() in sides

    def _sidecar_enabled(self) -> bool:
        return bool(self.config.get("enable_mid_sidecar"))

    def _width_is_large(self, state: Dict[str, Any]) -> bool:
        width = float(state.get("prior_width") or 0.0)
        if width <= 0:
            return False
        abs_min = float(self.config.get("sidecar_min_prior_width") or 0.0)
        if abs_min > 0 and width >= abs_min:
            return True
        hist = [float(x) for x in (state.get("prior_width_hist") or []) if x is not None]
        need = int(self.config.get("sidecar_min_hist") or 8)
        if len(hist) < need:
            return False
        q = float(self.config.get("sidecar_min_width_quantile") or 0.75)
        q = min(max(q, 0.0), 1.0)
        hist_sorted = sorted(hist)
        # Inclusive quantile threshold (type-7-ish): index at q*(n-1).
        idx = int(round(q * (len(hist_sorted) - 1)))
        thresh = hist_sorted[max(0, min(idx, len(hist_sorted) - 1))]
        return width >= float(thresh)

    def _arm_entry(
        self,
        ts: str,
        state: Dict[str, Any],
        *,
        direction: str,
        is_sidecar: bool = False,
        risk_pts: Optional[float] = None,
    ) -> Optional[OrderIntent]:
        qty = int(self.config.get("entry_qty") or 8)
        if qty <= 0:
            return None
        trade_id = self._new_trade_id(state)
        state["trades"][trade_id] = {
            "direction": direction,
            "status": "armed",
            "is_sidecar": bool(is_sidecar),
            "entry_qty": qty,
            "scale_qty": int(self.config.get("scale_qty") or 2),
            "scales_done": 0,
            "remaining_qty": qty,
            "risk_pts": float(risk_pts) if risk_pts is not None else None,
        }
        state["active_trade_id"] = trade_id
        if is_sidecar:
            state["sidecar_trade_id"] = trade_id
        else:
            # New primary leg may earn its own sidecar if it later stops at mid.
            state["main_trade_id"] = trade_id
            state["sidecar_used"] = False
            state["sidecar_pending"] = False
            state["pending_sidecar_risk_pts"] = None
        side_ord = "buy" if direction == "long" else "sell"
        reason = "sidecar_entry" if is_sidecar else "entry"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side_ord,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=True,
            bracket_role=reason,
            live_after_ts=ts,
            expires_after_ts=_quarter_expiry(str(state.get("quarter_key") or "")),
        )

    def _exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        targets = list(trade.get("targets") or [])
        qty = int(trade.get("entry_qty") or 0)
        scale_qty = int(trade.get("scale_qty") or 2)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or qty <= 0 or not direction or not targets:
            return []
        exit_side = "sell" if direction == "long" else "buy"
        expiry = self._exit_expiry(state, trade)
        out: List[OrderIntent] = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=stop,
                reason="stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="stop",
                expires_after_ts=expiry,
            )
        ]
        remaining = qty
        for i, px in enumerate(targets):
            q = min(scale_qty, remaining)
            if q <= 0:
                break
            remaining -= q
            reason = "tp%d" % (i + 1)
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=q,
                    limit_price=float(px),
                    reason=reason,
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role=reason,
                    expires_after_ts=expiry,
                )
            )
        return out

    def _exit_expiry(self, state: Dict[str, Any], trade: Dict[str, Any]) -> str:
        """Sidecar BE-carry runners are GTC; main (and pre-BE sidecar) use EOQ."""
        if bool(trade.get("be_active")) or (
            self._sidecar_only() and bool(trade.get("is_sidecar"))
        ):
            # Sidecar may span quarters to 4R; do not expire exits at EOQ.
            return ""
        return _quarter_expiry(str(state.get("quarter_key") or ""))

    def _remaining_exit_orders(
        self, trade_id: str, direction: str, state: Dict[str, Any], rem_qty: int
    ) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = _to_float(trade.get("stop"))
        targets = list(trade.get("targets") or [])
        scales_done = int(trade.get("scales_done") or 0)
        scale_qty = int(trade.get("scale_qty") or 2)
        direction = direction or str(trade.get("direction") or "")
        if stop is None or rem_qty <= 0 or not direction:
            return []
        exit_side = "sell" if direction == "long" else "buy"
        expiry = self._exit_expiry(state, trade)
        out: List[OrderIntent] = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=rem_qty,
                stop_price=stop,
                reason="stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="stop",
                expires_after_ts=expiry,
            )
        ]
        remaining = rem_qty
        for i, px in enumerate(targets):
            if i < scales_done:
                continue
            q = min(scale_qty, remaining)
            if q <= 0:
                break
            remaining -= q
            reason = "tp%d" % (i + 1)
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=q,
                    limit_price=float(px),
                    reason=reason,
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role=reason,
                    expires_after_ts=expiry,
                )
            )
        return out

    def _close_all_qty(self, position_quantity: int, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(position_quantity))
        side = "sell" if position_quantity > 0 else "buy"
        trade_id = str(self._state().get("active_trade_id") or new_id("t"))
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="flatten",
            live_after_ts=ts,
        )

    def _cancel_all_open(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, o.broker_order_id, reason)
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and bool(o.reduce_only):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "position_flat"))
        return out

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: Set[str]) -> List[CancelIntent]:
        out: List[CancelIntent] = []
        for o in context.strategy_open_orders:
            # BrokerOrder has bracket_role only (reason lives on OrderIntent / Fill).
            role = str(getattr(o, "bracket_role", "") or getattr(o, "reason", "") or "")
            if o.trade_id == trade_id and role in roles:
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "rebuild_exits"))
        return out

    def _update_building(self, state: Dict[str, Any], bar: Bar) -> None:
        hi = float(bar.high)
        lo = float(bar.low)
        if state.get("q_high") is None:
            state["q_high"] = hi
            state["q_low"] = lo
        else:
            state["q_high"] = max(float(state["q_high"]), hi)
            state["q_low"] = min(float(state["q_low"]), lo)

    def _roll_quarter(self, state: Dict[str, Any], qkey: str, dt: datetime) -> Dict[str, Any]:
        prior_high = state.get("q_high")
        prior_low = state.get("q_low")
        prior_ready = prior_high is not None and prior_low is not None
        width = (float(prior_high) - float(prior_low)) if prior_ready else 0.0
        mid = (float(prior_high) + float(prior_low)) * 0.5 if prior_ready else None
        # Expanding history of *previous* prior widths (excludes the new prior).
        hist = [float(x) for x in (state.get("prior_width_hist") or []) if x is not None]
        prev_w = state.get("prior_width")
        if prev_w is not None and float(prev_w) > 0:
            hist = hist + [float(prev_w)]
        # Preserve Monthly OR bookkeeping across quarter rolls (same calendar month
        # can span a quarter boundary only at Q starts on the 1st; still keep).
        fresh = {
            "quarter_key": qkey,
            "year": int(dt.year),
            "quarter": int((dt.month - 1) // 3 + 1),
            "q_high": None,
            "q_low": None,
            "prior_high": float(prior_high) if prior_ready else None,
            "prior_low": float(prior_low) if prior_ready else None,
            "prior_mid": float(mid) if mid is not None else None,
            "prior_width": float(width) if prior_ready and width > 0 else 0.0,
            "prior_ready": bool(prior_ready and width > 0),
            "prior_width_hist": hist,
            "current_leg_open": False,
            "entry_pending": False,
            "main_open": False,
            "sidecar_open": False,
            "main_entry_pending": False,
            "sidecar_pending": False,
            "sidecar_used": False,
            "main_trade_id": "",
            "sidecar_trade_id": "",
            "last_main_risk_pts": None,
            "pending_sidecar_risk_pts": None,
            "sidecar_signals": list(state.get("sidecar_signals") or []),
            "active_trade_id": "",
            "trades": {},
            "trade_seq": int(state.get("trade_seq") or 0),
            "month_key": state.get("month_key"),
            "month_sess": state.get("month_sess"),
            "mor_high": state.get("mor_high"),
            "mor_low": state.get("mor_low"),
            "mor_ready": state.get("mor_ready"),
            "mtd_high": state.get("mtd_high"),
            "mtd_low": state.get("mtd_low"),
            "mor_dir": state.get("mor_dir") or "mor_na",
            # Yearly ORB + Weekly ATR SuperTrend persist across quarter rolls.
            "yor_year": state.get("yor_year"),
            "yor_high": state.get("yor_high"),
            "yor_low": state.get("yor_low"),
            "yor_ready": state.get("yor_ready"),
            "ytd_high": state.get("ytd_high"),
            "ytd_low": state.get("ytd_low"),
            "yor_dir": state.get("yor_dir") or "yor_na",
            "w_week_key": state.get("w_week_key"),
            "w_open": state.get("w_open"),
            "w_high": state.get("w_high"),
            "w_low": state.get("w_low"),
            "w_close": state.get("w_close"),
            "w_st_atr": state.get("w_st_atr"),
            "w_st_n": state.get("w_st_n"),
            "w_st_prev_close": state.get("w_st_prev_close"),
            "w_st_final_upper": state.get("w_st_final_upper"),
            "w_st_final_lower": state.get("w_st_final_lower"),
            "w_st_trend": state.get("w_st_trend"),
            "w_st_last_week": state.get("w_st_last_week"),
            "w_atr_trend": state.get("w_atr_trend") or "w_atr_na",
        }
        self.state = fresh
        return fresh

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if "quarter_key" not in raw:
            raw = {
                "quarter_key": "",
                "q_high": None,
                "q_low": None,
                "prior_ready": False,
                "trades": {},
                "trade_seq": 0,
            }
        if "trades" not in raw or not isinstance(raw["trades"], dict):
            raw["trades"] = {}
        self.state = raw
        return raw

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        trade = trades.get(trade_id)
        if trade is None:
            trade = {}
            trades[trade_id] = trade
        return trade

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq") or 0) + 1
        return "%s_t%d" % (self.instance.strategy_id, int(state["trade_seq"]))


def _parse_ts(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text[:10])


def _quarter_key(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return "%dQ%d" % (dt.year, q)


def _week_end_friday_key(dt: datetime) -> str:
    """W-FRI week key (Mon–Fri belong to that Friday's week end)."""
    # Monday=0 … Friday=4; Sat/Sun map forward to the coming Friday.
    days_ahead = (4 - dt.weekday()) % 7
    fri = (dt + timedelta(days=days_ahead)).date()
    return fri.isoformat()


def _quarter_expiry(qkey: str) -> str:
    if not qkey or "Q" not in qkey:
        return ""
    try:
        year_s, q_s = qkey.split("Q", 1)
        year = int(year_s)
        q = int(q_s)
    except ValueError:
        return ""
    if q >= 4:
        return "%d-01-01T00:00:00" % (year + 1)
    month = q * 3 + 1
    return "%d-%02d-01T00:00:00" % (year, month)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
