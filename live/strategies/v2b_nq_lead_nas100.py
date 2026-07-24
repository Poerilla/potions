"""NAS100 follower that only enters when an NQ prior-opposed lead is in sync.

``strategy_type = v2b_nq_lead_nas100``

- Lead campaigns are injected via ``config.nq_lead_campaigns`` (session-keyed).
- Consumes **NAS100** 1m bars only (Engine single-instrument constraint).
- Enters with a market order inside ``[t_nq - delta_early, t_nq + t_max]`` when
  structure (mapped OR) passes; otherwise skips.
- After entry, manages local CFD ``S_1_1_1`` scaleout / EOD (NQ gates entry only).

Does not modify ``v2b_scaleout`` / standalone prior-opposed strategies.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pytz

from ..models import CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

NY = pytz.timezone("America/New_York")
UTC = pytz.UTC


class V2BNqLeadNas100Strategy(StrategyPlugin):
    strategy_type = "v2b_nq_lead_nas100"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.1,
            "entry_qty": 3,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "rth_start": "09:30",
            "eod_cutoff": "15:59",
            "t_max_seconds": 60,
            "delta_early_seconds": 30,
            "nq_lead_campaigns": {},
            "record_sync_audit": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "1m" or not bar.complete:
            return StrategyActions.empty()
        return self._on_1m_bar(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = fill.reason

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            trade.update(
                {
                    "direction": direction,
                    "entry_price": fill.price,
                    "entry_ts": fill.ts,
                    "status": "open",
                    "tp1_hit": False,
                    "entry_qty": int(fill.quantity),
                    "tp1_qty": int(self.config.get("tp1_qty") or 1),
                    "tp2_qty": int(self.config.get("tp2_qty") or 1),
                }
            )
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = direction
            state["current_leg_open"] = True
            state["nas_candidate_state"] = "entered"
            orders = self._initial_exit_orders(fill.trade_id, direction, state)
            self._commit_state(state)
            return StrategyActions(orders, [], [], [], [])

        if role == "tp1":
            trade["tp1_hit"] = True
            cancels = self._cancel_open_roles(context, fill.trade_id, {"wide_stop", "tp2"})
            orders: List[OrderIntent] = []
            if context.position_quantity != 0:
                direction = str(trade.get("direction") or state.get("active_direction") or "")
                orders.extend(self._runner_exit_orders(fill.trade_id, direction, state))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        if role in {"wide_stop", "runner_stop", "tp2", "eod_close"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                trade["exit_ts"] = fill.ts
                state["current_leg_open"] = False
                state["legs_done"] = int(state.get("legs_done", 0)) + 1
                state["active_trade_id"] = ""
                state["active_direction"] = ""
                cancels = self._cancel_reduce_orders(context, fill.trade_id)
                self._commit_state(state)
                return StrategyActions([], cancels, [], [], [])

        self._commit_state(state)
        return StrategyActions.empty()

    def _on_1m_bar(self, bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        session = dt.date().isoformat()
        t = dt.time()
        state = self._state()
        if state.get("session_date") != session:
            # Preserve cross-session audit / finished set / trade book.
            prev_audit = list(state.get("sync_audit") or [])
            prev_finished = list(state.get("finished_campaign_ids") or [])
            prev_trades = dict(state.get("trades") or {})
            prev_seq = int(state.get("trade_seq") or 0)
            state = self._fresh_session_state(session)
            state["sync_audit"] = prev_audit
            state["finished_campaign_ids"] = prev_finished
            state["trades"] = prev_trades
            state["trade_seq"] = prev_seq

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        if not self._in_rth(t):
            self._commit_state(state)
            return StrategyActions.empty()

        if t >= self._time("eod_cutoff"):
            cancels.extend(self._cancel_all_open(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eod_close", order_type="market_close"))
            # Expire any still-pending campaigns at EOD.
            self._skip_pending(state, bar.ts, "eod_session_end")
            state["done"] = True
            state["phase"] = "eod"
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], [])

        # Already in a trade or entry working — just hold exits.
        if context.position_quantity != 0 or self._has_open_entry(context):
            self._commit_state(state)
            return StrategyActions.empty()

        if state.get("nas_candidate_state") in {"entered", "skipped"} and state.get("active_campaign_id"):
            # One CFD attempt per lead campaign; move to next pending if any.
            pass

        campaign = self._active_or_next_campaign(state, dt)
        if campaign is None:
            self._commit_state(state)
            return StrategyActions.empty()

        # Ensure OR levels on state for exit geometry.
        mapped_hi = campaign.get("mapped_or_high")
        mapped_lo = campaign.get("mapped_or_low")
        if mapped_hi is not None and mapped_lo is not None:
            state["or_high"] = float(mapped_hi)
            state["or_low"] = float(mapped_lo)

        t_nq = _parse_dt(str(campaign["t_nq_entry"]))
        t_max = float(self.config.get("t_max_seconds") or 60)
        early = float(self.config.get("delta_early_seconds") or 30)
        window_start = t_nq - timedelta(seconds=early)
        window_end = t_nq + timedelta(seconds=t_max)

        # Milestone: NQ already scaled/stopped before we can enter.
        for key, reason in (("t_nq_tp1", "nq_already_scaled"), ("t_nq_stop", "nq_already_stopped")):
            raw = campaign.get(key)
            if not raw:
                continue
            try:
                milestone = _parse_dt(str(raw))
            except Exception:
                continue
            if milestone <= dt and dt >= t_nq:
                self._mark_skip(state, campaign, bar.ts, reason)
                self._commit_state(state)
                return StrategyActions.empty()

        if dt < window_start:
            self._commit_state(state)
            return StrategyActions.empty()

        if dt > window_end:
            self._mark_skip(state, campaign, bar.ts, "sync_window_expired")
            self._commit_state(state)
            return StrategyActions.empty()

        # Time sync: |bar_ts - t_nq| <= T_max (also allow early side within delta_early).
        delta_s = (dt - t_nq).total_seconds()
        if abs(delta_s) > t_max and delta_s > 0:
            self._mark_skip(state, campaign, bar.ts, "sync_window_expired")
            self._commit_state(state)
            return StrategyActions.empty()
        if delta_s < -early:
            self._commit_state(state)
            return StrategyActions.empty()

        side = str(campaign.get("side") or "").lower()
        if not self._structure_ok(bar, campaign, side):
            # Still inside window — wait for a later bar; if this is the last
            # second of the window the next bar will expire.
            if dt >= window_end:
                self._mark_skip(state, campaign, bar.ts, "structure_failed")
            self._commit_state(state)
            return StrategyActions.empty()

        # Fire market entry.
        direction = "Long" if side == "long" else "Short"
        trade_id = self._new_trade_id(state)
        qty = int(self.config.get("entry_qty") or 3)
        entry = OrderIntent.create(
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
            live_after_ts=bar.ts,
            expires_after_ts=_session_expiry(bar.ts),
        )
        state["active_campaign_id"] = campaign["campaign_id"]
        state["nas_candidate_state"] = "pending_fill"
        state["entry_delta_seconds"] = delta_s
        state["phase"] = "entered_signal"
        finished = list(state.get("finished_campaign_ids") or [])
        cid = campaign["campaign_id"]
        if cid and cid not in finished:
            finished.append(cid)
        state["finished_campaign_ids"] = finished
        audit = {
            "campaign_id": campaign["campaign_id"],
            "side": side,
            "t_nq": campaign["t_nq_entry"],
            "t_nas": bar.ts,
            "entry_delta_seconds": delta_s,
            "state": "entered",
            "skip_reason": "",
            "nas_signal_px": float(bar.close),
            "nq_entry": float(campaign.get("p_nq_entry") or 0),
            "mapped_or_high": campaign.get("mapped_or_high"),
            "mapped_or_low": campaign.get("mapped_or_low"),
            "map_ratio": campaign.get("map_ratio"),
        }
        self._append_audit(state, audit)
        trade = self._trade(trade_id, state)
        trade["campaign_id"] = campaign["campaign_id"]
        trade["entry_qty"] = qty
        trade["tp1_qty"] = int(self.config.get("tp1_qty") or 1)
        trade["tp2_qty"] = int(self.config.get("tp2_qty") or 1)
        self._commit_state(state)
        return StrategyActions([entry], [], [], [], [])

    def _structure_ok(self, bar, campaign: Dict[str, Any], side: str) -> bool:
        hi = campaign.get("mapped_or_high")
        lo = campaign.get("mapped_or_low")
        if hi is None or lo is None:
            return False
        px = float(bar.close)
        if side == "long":
            return px >= float(hi)
        if side == "short":
            return px <= float(lo)
        return False

    def _active_or_next_campaign(self, state: Dict[str, Any], dt: datetime) -> Optional[Dict[str, Any]]:
        session = str(state.get("session_date") or dt.date().isoformat())
        events = list((self.config.get("nq_lead_campaigns") or {}).get(session, []))
        done = set(state.get("finished_campaign_ids") or [])
        active_id = state.get("active_campaign_id")
        if active_id and state.get("nas_candidate_state") in {"pending", "pending_fill"}:
            for ev in events:
                if ev.get("campaign_id") == active_id:
                    return dict(ev)
        for ev in events:
            cid = ev.get("campaign_id")
            if cid in done:
                continue
            # Only consider campaigns whose window has not long expired before session start handling.
            t_nq = _parse_dt(str(ev["t_nq_entry"]))
            t_max = float(self.config.get("t_max_seconds") or 60)
            if dt > t_nq + timedelta(seconds=t_max + 120) and cid not in done:
                # Too late even to observe — mark skipped once.
                self._mark_skip(state, ev, dt.isoformat(), "sync_window_expired")
                continue
            state["active_campaign_id"] = cid
            state["nas_candidate_state"] = "pending"
            return dict(ev)
        return None

    def _mark_skip(self, state: Dict[str, Any], campaign: Dict[str, Any], ts: str, reason: str) -> None:
        cid = campaign.get("campaign_id")
        finished = list(state.get("finished_campaign_ids") or [])
        if cid and cid not in finished:
            finished.append(cid)
        state["finished_campaign_ids"] = finished
        state["nas_candidate_state"] = "skipped"
        state["active_campaign_id"] = ""
        state["last_skip_reason"] = reason
        self._append_audit(
            state,
            {
                "campaign_id": cid,
                "side": campaign.get("side"),
                "t_nq": campaign.get("t_nq_entry"),
                "t_nas": ts,
                "entry_delta_seconds": None,
                "state": "skipped",
                "skip_reason": reason,
                "nas_signal_px": None,
                "nq_entry": campaign.get("p_nq_entry"),
                "mapped_or_high": campaign.get("mapped_or_high"),
                "mapped_or_low": campaign.get("mapped_or_low"),
                "map_ratio": campaign.get("map_ratio"),
            },
        )

    def _skip_pending(self, state: Dict[str, Any], ts: str, reason: str) -> None:
        if state.get("nas_candidate_state") == "pending" and state.get("active_campaign_id"):
            session = str(state.get("session_date") or "")
            for ev in (self.config.get("nq_lead_campaigns") or {}).get(session, []):
                if ev.get("campaign_id") == state.get("active_campaign_id"):
                    self._mark_skip(state, ev, ts, reason)
                    return

    def _append_audit(self, state: Dict[str, Any], row: Dict[str, Any]) -> None:
        if not self.config.get("record_sync_audit", True):
            return
        audit = list(state.get("sync_audit") or [])
        audit.append(row)
        state["sync_audit"] = audit

    def _unit_quantities(self, trade: Optional[Dict[str, Any]] = None) -> tuple:
        trade = trade or {}
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        tp1 = int(trade.get("tp1_qty") if trade.get("tp1_qty") is not None else self.config.get("tp1_qty") or 1)
        tp2 = int(trade.get("tp2_qty") if trade.get("tp2_qty") is not None else self.config.get("tp2_qty") or 1)
        runner = max(0, entry_qty - tp1 - tp2)
        return tp1, tp2, runner

    def _params(self, direction: str, state: Dict[str, Any]) -> Optional[Dict[str, float]]:
        range_high = _to_float(state.get("or_high"))
        range_low = _to_float(state.get("or_low"))
        if range_high is None or range_low is None or range_high <= range_low:
            return None
        range_value = range_high - range_low
        tick = float(self.config["tick_size"])
        if direction == "Long":
            return {
                "entry": range_high + tick,
                "init_sl": range_low,
                "tp1": range_high + range_value,
                "tp2": range_high + 2.0 * range_value,
                "runner_sl": range_high + tick,
            }
        return {
            "entry": range_low - tick,
            "init_sl": range_high,
            "tp1": range_low - range_value,
            "tp2": range_low - 2.0 * range_value,
            "runner_sl": range_low - tick,
        }

    def _initial_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        params = self._params(direction, state)
        if params is None:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        trade = self._trade(trade_id, state)
        tp1_qty, tp2_qty, _runner = self._unit_quantities(trade)
        entry_qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        expiry = _session_expiry(str(state.get("session_date", "")))
        out: List[OrderIntent] = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=entry_qty,
                stop_price=params["init_sl"],
                reason="v2b_wide_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="wide_stop",
                expires_after_ts=expiry,
            )
        ]
        if tp1_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp1_qty,
                    limit_price=params["tp1"],
                    reason="v2b_tp1",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp1",
                    expires_after_ts=expiry,
                )
            )
        if tp2_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=params["tp2"],
                    reason="v2b_tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=expiry,
                )
            )
        return out

    def _runner_exit_orders(self, trade_id: str, direction: str, state: Dict[str, Any]) -> List[OrderIntent]:
        params = self._params(direction, state)
        if params is None:
            return []
        trade = self._trade(trade_id, state)
        _tp1, tp2_qty, runner_qty = self._unit_quantities(trade)
        if runner_qty <= 0 and tp2_qty <= 0:
            return []
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _session_expiry(str(state.get("session_date", "")))
        out: List[OrderIntent] = []
        runner_stack = max(0, tp2_qty + runner_qty)
        if runner_stack > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="stop",
                    quantity=runner_stack,
                    stop_price=params["runner_sl"],
                    reason="v2b_runner_stop",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="runner_stop",
                    expires_after_ts=expiry,
                )
            )
        if tp2_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=tp2_qty,
                    limit_price=params["tp2"],
                    reason="v2b_tp2",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="tp2",
                    expires_after_ts=expiry,
                )
            )
        return out

    def _close_all(self, context: StrategyContext, ts: str, reason: str, order_type: str = "market") -> OrderIntent:
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="sell" if context.position_quantity > 0 else "buy",
            order_type=order_type,
            quantity=abs(context.position_quantity),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            live_after_ts=ts,
        )

    def _cancel_open_roles(self, context: StrategyContext, trade_id: str, roles: Iterable[str]) -> List[CancelIntent]:
        role_set = set(roles)
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "nq_lead_cancel_%s" % order.bracket_role)
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.bracket_role in role_set
        ]

    def _cancel_reduce_orders(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "nq_lead_leg_closed")
            for order in context.strategy_open_orders
            if order.trade_id == trade_id and order.reduce_only
        ]

    def _cancel_all_open(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(self.instance.strategy_id, order.broker_order_id, "nq_lead_eod")
            for order in context.strategy_open_orders
        ]

    def _has_open_entry(self, context: StrategyContext) -> bool:
        return any(o.bracket_role == "entry" for o in context.strategy_open_orders)

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq", 0)) + 1
        return "%s_%s_%02d" % (
            self.instance.strategy_id,
            str(state.get("session_date", "")).replace("-", ""),
            int(state["trade_seq"]),
        )

    def _state(self) -> Dict[str, Any]:
        raw = self.state if isinstance(self.state, dict) else {}
        if not raw:
            return self._fresh_session_state("")
        return dict(raw)

    def _fresh_session_state(self, session: str) -> Dict[str, Any]:
        return {
            "session_date": session,
            "phase": "idle",
            "done": False,
            "or_high": None,
            "or_low": None,
            "trade_seq": 0,
            "trades": {},
            "active_trade_id": "",
            "active_direction": "",
            "current_leg_open": False,
            "legs_done": 0,
            "active_campaign_id": "",
            "nas_candidate_state": "",
            "finished_campaign_ids": [],
            "sync_audit": [],
            "entry_delta_seconds": None,
            "last_skip_reason": "",
        }

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {"trade_id": trade_id}
        return trades[trade_id]

    def _time(self, key: str) -> time:
        raw = str(self.config.get(key) or "15:59")
        hh, mm = raw.split(":")[:2]
        return time(int(hh), int(mm))

    def _in_rth(self, t: time) -> bool:
        return self._time("rth_start") <= t <= self._time("eod_cutoff")


def _parse_dt(ts: str) -> datetime:
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = NY.localize(dt)
    return dt.astimezone(NY)


def _session_expiry(ts: str) -> str:
    try:
        session_day = _parse_dt(ts).date()
    except Exception:
        session_day = datetime.now(tz=NY).date()
    # 15:59 America/New_York with correct DST offset
    local = NY.localize(datetime.combine(session_day, time(15, 59)))
    return local.isoformat()


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
