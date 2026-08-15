"""Structure-program + 1m SuperTrend StrategyPlugin (broker-like).

Mirrors the research study ``structure_sl`` / ``split15`` / ``scale4`` /
``structure_sl_scale_run`` plans:
15m L-H-LL-HH / H-L-HH-LL structure lists (20 each), program flips after
2 opposing takeouts, ST-break signal → limit at structure key, risk stop
beyond structure, then scale plan.

Plans:
  split15 — 15ct, 5@1R→BE, 5@EOD, 5@6R (default)
  scale4 — 4ct, 2@1R→BE, 2@3R
  scale_run — 15ct, 5@+22pts, 5@+50, 5@+200; fav ST-flip → BE (hold); no EOD
"""

from __future__ import annotations

import csv
import json
from collections import deque
from datetime import datetime, time
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import pytz

from ..models import Bar, CancelIntent, OrderIntent, StrategyActions, new_id
from .base import StrategyContext, StrategyPlugin

NY = pytz.timezone("America/New_York")
NY_OPEN = time(9, 30)
NY_CLOSE = time(16, 0)


def _parse_time_cfg(value, default: time) -> time:
    if value is None or value == "":
        return default
    if isinstance(value, time):
        return value
    s = str(value).strip()
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def _ts_le(left: str, right: str) -> bool:
    """True when left timestamp <= right (ISO strings, tz-aware safe)."""
    try:
        ldt = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        rdt = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
        if ldt.tzinfo is None:
            ldt = NY.localize(ldt)
        if rdt.tzinfo is None:
            rdt = NY.localize(rdt)
        return ldt <= rdt
    except Exception:
        return str(left) <= str(right)


class StructureProgramStStrategy(StrategyPlugin):
    strategy_type = "structure_program_st"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "plan": "split15",  # split15 | scale4 | scale_run
            "risk_pts": 12.0,
            "atr_len": 14,
            "atr_mult": 3.0,
            "list_size": 20,
            "takeouts_to_flip": 2,
            "swing_left": 2,
            "swing_right": 2,
            "pending_max_closes": 3,
            "rth_only": True,
            "session_open": "09:30",
            "session_close": "16:00",  # exclusive end for bar filter
            "eod_time": "15:59",
            "st_flip_exit": True,
            # modes: off | always | adverse | after_n | adverse_after_n | fav_be
            "st_flip_mode": "adverse",
            "st_flip_min_bars": 0,  # used by after_n / adverse_after_n
            "history_bars": 800,
            # absolute-pt ladder (scale_run); 0 = use R-multiples from risk
            "tp1_pts": 0.0,
            "tp2_pts": 0.0,
            "tp3_pts": 0.0,
            "eod_flatten": True,
            # entry: touch = research (cancel if SL first); sweep_reclaim = require SL
            # then reclaim; resting = submit limit on arm (no ST wait for fill gate).
            "entry_mode": "touch",
            # signals: internal = ST break; external = CSV; structure_only = program+key, no ST
            "signal_source": "internal",
            "external_signals_csv": "",
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._session_open = _parse_time_cfg(self.config.get("session_open"), NY_OPEN)
        self._session_close = _parse_time_cfg(self.config.get("session_close"), NY_CLOSE)
        self._eod_time = _parse_time_cfg(self.config.get("eod_time"), time(15, 59))
        plan = str(self.config.get("plan") or "split15")
        if plan == "scale4":
            self.config.setdefault("entry_qty", 4)
            self.config.setdefault("scale_qty", 2)
            self.config.setdefault("eod_qty", 0)
            self.config.setdefault("runner_qty", 2)
            self.config.setdefault("runner_r", 3.0)
            self.config.setdefault("st_flip_after_scale", True)
            self.config.setdefault("eod_flatten", True)
        elif plan == "scale_run":
            self.config.setdefault("entry_qty", 15)
            self.config.setdefault("scale_qty", 5)  # first batch @ tp1
            self.config.setdefault("scale2_qty", 5)  # second batch @ tp2
            self.config.setdefault("eod_qty", 0)
            self.config.setdefault("runner_qty", 5)
            self.config.setdefault("tp1_pts", 22.0)
            self.config.setdefault("tp2_pts", 50.0)
            self.config.setdefault("tp3_pts", 200.0)
            self.config.setdefault("runner_r", 0.0)  # unused; absolute tp3
            self.config.setdefault("st_flip_after_scale", True)
            self.config.setdefault("st_flip_mode", "fav_be")
            self.config.setdefault("eod_flatten", False)
        elif plan == "touch_st_align":
            # Touch+through structure → ST flip market; SL=ST trail; +25→±12 then 50/200
            self.config.setdefault("entry_qty", 15)
            self.config.setdefault("scale_qty", 5)
            self.config.setdefault("scale2_qty", 5)
            self.config.setdefault("eod_qty", 0)
            self.config.setdefault("runner_qty", 5)
            self.config.setdefault("tp1_pts", 25.0)
            self.config.setdefault("tp2_pts", 50.0)
            self.config.setdefault("tp3_pts", 200.0)
            self.config.setdefault("tight_sl_pts", 12.0)
            self.config.setdefault("runner_r", 0.0)
            self.config.setdefault("st_flip_after_scale", True)
            self.config.setdefault("st_flip_mode", "fav_be")
            self.config.setdefault("eod_flatten", False)
            self.config.setdefault("pending_max_closes", 3)
            self.config.setdefault("fade_after_through_mins", 0)
        elif plan == "touch_st_align_fade20":
            self.config.setdefault("entry_qty", 15)
            self.config.setdefault("scale_qty", 5)
            self.config.setdefault("scale2_qty", 5)
            self.config.setdefault("eod_qty", 0)
            self.config.setdefault("runner_qty", 5)
            self.config.setdefault("tp1_pts", 25.0)
            self.config.setdefault("tp2_pts", 50.0)
            self.config.setdefault("tp3_pts", 200.0)
            self.config.setdefault("tight_sl_pts", 12.0)
            self.config.setdefault("runner_r", 0.0)
            self.config.setdefault("st_flip_after_scale", True)
            self.config.setdefault("st_flip_mode", "fav_be")
            self.config.setdefault("eod_flatten", False)
            self.config.setdefault("pending_max_closes", 3)
            self.config.setdefault("fade_after_through_mins", 20)
        elif plan == "vwap_scalein":
            # VWAP split entries inside structure; SL at structure extreme; 15m reclaim re-arm
            self.config.setdefault("entry_qty", 15)
            self.config.setdefault("slice_qty", 3)
            self.config.setdefault("n_slices", 5)
            self.config.setdefault("scale_qty", 5)
            self.config.setdefault("scale2_qty", 5)
            self.config.setdefault("eod_qty", 0)
            self.config.setdefault("runner_qty", 5)
            self.config.setdefault("tp1_pts", 25.0)
            self.config.setdefault("tp2_pts", 50.0)
            self.config.setdefault("tp3_pts", 200.0)
            self.config.setdefault("tight_sl_pts", 12.0)
            self.config.setdefault("st_flip_after_scale", True)
            self.config.setdefault("st_flip_mode", "fav_be")
            # Structure VWAP is RTH-intraday; flatten so BE winners don't span years of RTH-only tape
            self.config.setdefault("eod_flatten", True)
            self.config.setdefault("pending_max_closes", 60)
        else:
            self.config.setdefault("entry_qty", 15)
            self.config.setdefault("scale_qty", 5)
            self.config.setdefault("eod_qty", 5)
            self.config.setdefault("runner_qty", 5)
            self.config.setdefault("runner_r", 6.0)
            self.config.setdefault("st_flip_after_scale", False)
            self.config.setdefault("eod_flatten", True)

        # in-memory (replay-fresh) series — not fully persisted
        self._bars_1m: List[Dict[str, float]] = []
        self._swings: List[Tuple[str, str, float]] = []  # confirm_ts, H|L, px
        self._bull: Deque[Dict[str, Any]] = deque(maxlen=int(self.config["list_size"]))
        self._bear: Deque[Dict[str, Any]] = deque(maxlen=int(self.config["list_size"]))
        self._bucket: Optional[Dict[str, Any]] = None
        self._seen_struct = set()
        # SuperTrend: EWM ATR matching research compute_supertrend; 2-session warm
        self._warm_sessions: Deque[List[Dict[str, float]]] = deque(maxlen=2)
        self._session_bars: List[Dict[str, float]] = []
        self._st_session: Optional[str] = None
        self._st_atr: Optional[float] = None
        self._st_final_upper: Optional[float] = None
        self._st_final_lower: Optional[float] = None
        self._st_bull: bool = True
        self._st_stop: Optional[float] = None
        self._st_prev_close: Optional[float] = None
        self._st_bar_i: int = 0  # bars since (re)seed including warm
        self._st_warm_n: int = 0
        self._ext_signals: List[Dict[str, Any]] = []
        self._ext_i: int = 0
        if str(self.config.get("signal_source") or "internal") == "external":
            self._load_external_signals(str(self.config.get("external_signals_csv") or ""))

    def _load_external_signals(self, path: str) -> None:
        """Load analytic (or other) arms: signal_ts, side, limit_px, stop."""
        if not path:
            return
        p = Path(path)
        if not p.exists():
            return
        rows: List[Dict[str, Any]] = []
        with p.open(newline="") as fh:
            for raw in csv.DictReader(fh):
                side = str(raw.get("side") or "").lower()
                if side in {"buy", "long"}:
                    side = "long"
                elif side in {"sell", "short"}:
                    side = "short"
                else:
                    continue
                ts = str(raw.get("signal_ts") or raw.get("event_ts") or "")
                if not ts:
                    continue
                lim = raw.get("limit_px") or raw.get("structure_key") or raw.get("entry")
                stop = raw.get("stop") or raw.get("pending_stop")
                if lim is None or stop is None or lim == "" or stop == "":
                    risk = float(self.config.get("risk_pts") or 8.0)
                    lim_f = float(lim) if lim not in (None, "") else None
                    if lim_f is None:
                        continue
                    stop_f = lim_f - risk if side == "long" else lim_f + risk
                else:
                    lim_f = float(lim)
                    stop_f = float(stop)
                rows.append(
                    {
                        "signal_ts": ts,
                        "side": side,
                        "limit_px": lim_f,
                        "stop": stop_f,
                        "structure_key": lim_f,
                        "st_at_signal": float(raw["st_at_signal"])
                        if raw.get("st_at_signal") not in (None, "")
                        else lim_f,
                        "risk_pts": float(raw["risk_pts"])
                        if raw.get("risk_pts") not in (None, "")
                        else float(self.config.get("risk_pts") or 8.0),
                    }
                )
        rows.sort(key=lambda r: r["signal_ts"])
        self._ext_signals = rows

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != "1m" or not bar.complete:
            return StrategyActions.empty()
        # dense RTH gaps (holidays) arrive as NaN — skip before ST/structure update
        try:
            if not (
                float(bar.open) == float(bar.open)
                and float(bar.high) == float(bar.high)
                and float(bar.low) == float(bar.low)
                and float(bar.close) == float(bar.close)
            ):
                return StrategyActions.empty()
        except (TypeError, ValueError):
            return StrategyActions.empty()
        dt = _parse_dt(bar.ts)
        if bool(self.config.get("rth_only", True)) and not _in_session(
            dt.time(), self._session_open, self._session_close
        ):
            return StrategyActions.empty()

        session = dt.date().isoformat()
        state = self._state()
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []

        # session roll (pending expiry + ST warm reset) before consuming this bar
        if state.get("session_date") != session:
            if state.get("pending_entry_trade_id"):
                closes = int(state.get("pending_rth_closes") or 0) + 1
                state["pending_rth_closes"] = closes
                if closes >= int(self.config["pending_max_closes"]):
                    cancels.extend(self._cancel_entries(context, "pending_expire"))
                    state["pending_entry_trade_id"] = ""
                    state["pending_side"] = ""
            if state.get("touch_phase"):
                tc = int(state.get("touch_rth_closes") or 0) + 1
                state["touch_rth_closes"] = tc
                if tc >= int(self.config.get("pending_max_closes") or 3):
                    state["touch_phase"] = ""
                    state["touch_touched"] = False
                    state["touch_through"] = False
            state["session_date"] = session
            state["eod_done"] = False
            self._roll_st_session(session)
            if cancels and not state.get("pending_entry_trade_id"):
                self._commit_state(state)
                # still consume bar for ST/structure below after returning cancels? 
                # Prefer cancelling first; structure updates on subsequent bars.
                self._append_1m(bar)
                self._update_15m(bar)
                return StrategyActions([], cancels, [], [], [])

        self._append_1m(bar)
        st_stop = self._st_stop
        st_bull = bool(self._st_bull)
        self._update_15m(bar)

        qty = int(context.position_quantity)
        is_eod = dt.time() >= self._eod_time

        # --- manage open ---
        if qty != 0 and state.get("active_trade_id"):
            actions = self._manage_open(bar, context, state, st_stop, st_bull, is_eod)
            # VWAP scale-in: after manage, may still add another slice same bar
            if (
                str(self.config.get("plan") or "") == "vwap_scalein"
                and state.get("active_trade_id")
                and abs(int(context.position_quantity)) > 0
            ):
                add = self._manage_vwap_scalein(
                    bar, context, state, list(actions.cancels), st_stop, st_bull, dt
                )
                merged_orders = list(actions.orders) + list(add.orders)
                merged_cancels = list(actions.cancels) + list(add.cancels)
                self._commit_state(state)
                if merged_orders or merged_cancels:
                    return StrategyActions(merged_orders, merged_cancels, [], [], [])
                return actions
            self._commit_state(state)
            return actions

        # orphan position (entry fill without recognized reason) — adopt + arm exits
        if qty != 0 and not state.get("active_trade_id"):
            direction = "Long" if qty > 0 else "Short"
            trade_id = str(state.get("pending_entry_trade_id") or new_id("trade"))
            state["active_trade_id"] = trade_id
            state["pending_entry_trade_id"] = ""
            state["filled_qty"] = abs(qty)
            state["scaled"] = False
            state["scaled2"] = False
            state["st_be_armed"] = False
            state["bars_held"] = 0
            entry = float(state.get("pending_limit") or 0.0)
            state["entry_price"] = entry
            risk = float(self.config["risk_pts"])
            stop = float(state["pending_stop"]) if state.get("pending_stop") is not None else (
                entry - risk if direction == "Long" else entry + risk
            )
            state["stop_price"] = stop
            self._set_targets(state, entry, direction)
            state["active_direction"] = direction
            self._commit_state(state)
            return StrategyActions(
                self._initial_exits(trade_id, direction, state, bar.ts),
                cancels,
                [],
                [],
                [],
            )

        signal_source = str(self.config.get("signal_source") or "internal")
        entry_mode = str(self.config.get("entry_mode") or "touch").lower()

        # Touch-through → ST-align market entry (plan touch_st_align / fade20)
        if str(self.config.get("plan") or "") in {"touch_st_align", "touch_st_align_fade20"}:
            actions = self._manage_touch_st_align(bar, context, state, cancels, st_stop, st_bull)
            self._commit_state(state)
            return actions

        # VWAP split scale-in inside structure
        if str(self.config.get("plan") or "") == "vwap_scalein":
            actions = self._manage_vwap_scalein(bar, context, state, cancels, st_stop, st_bull, dt)
            self._commit_state(state)
            return actions

        # Resting structure limit: program+key only (no ST arm gate)
        if signal_source == "structure_only":
            actions = self._manage_structure_resting(bar, context, state, cancels)
            self._commit_state(state)
            return actions

        # --- arm / cancel / fill pending (touch / sweep_reclaim) ---
        if state.get("pending_entry_trade_id"):
            actions = self._manage_pending_entry(bar, context, state, cancels)
            self._commit_state(state)
            return actions

        if self._has_working_entry(context):
            self._commit_state(state)
            return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()

        # Arm next signal (internal ST break or external analytic arms)
        if signal_source == "external":
            armed = self._arm_external_signal(bar, state)
            if armed and entry_mode == "resting":
                orders.append(self._entry_limit_intent(state, bar.ts))
            self._commit_state(state)
            return StrategyActions(orders, cancels, [], [], []) if (orders or cancels or armed) else StrategyActions.empty()

        ready = len(self._bull) >= int(self.config["list_size"]) and len(self._bear) >= int(
            self.config["list_size"]
        )
        prog = state.get("program")
        if not ready or prog not in {"buy", "sell"} or st_stop is None:
            self._commit_state(state)
            return StrategyActions.empty()

        # need prior bar ST for break detect
        if len(self._bars_1m) < 2:
            self._commit_state(state)
            return StrategyActions.empty()
        prev = self._bars_1m[-2]
        prev_bull = bool(prev.get("st_bull"))
        prev_stop = prev.get("st_stop")
        if prev_stop is None:
            self._commit_state(state)
            return StrategyActions.empty()

        signal = None
        sk = None
        if prog == "buy" and (not prev_bull) and st_bull and float(bar.close) > float(prev_stop):
            sk = self._latest_key("bull")
            if sk is not None and sk < float(prev_stop):
                signal = "long"
        elif prog == "sell" and prev_bull and (not st_bull) and float(bar.close) < float(prev_stop):
            sk = self._latest_key("bear")
            if sk is not None and sk > float(prev_stop):
                signal = "short"

        if signal is None or sk is None:
            self._commit_state(state)
            return StrategyActions.empty()

        risk = float(self.config["risk_pts"])
        stop_px = sk - risk if signal == "long" else sk + risk
        self._arm_pending_state(
            state,
            side=signal,
            limit_px=float(sk),
            stop_px=float(stop_px),
            st_signal=float(prev_stop),
            structure_key=float(sk),
        )
        self._commit_state(state)
        return StrategyActions(orders, cancels, [], [], [])

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        role = str(fill.reason or "")
        # PaperBroker stamps fill.reason from bracket_role (else order_type)
        if role == "entry" or (
            not state.get("active_trade_id")
            and fill.trade_id == state.get("pending_entry_trade_id")
        ):
            # VWAP scale-in add-on onto existing campaign
            if (
                str(self.config.get("plan") or "") == "vwap_scalein"
                and state.get("active_trade_id")
                and fill.trade_id == state.get("active_trade_id")
                and int(state.get("filled_qty") or 0) > 0
            ):
                old_q = int(state["filled_qty"])
                old_e = float(state.get("entry_price") or fill.price)
                add_q = int(fill.quantity)
                new_q = old_q + add_q
                state["entry_price"] = (old_e * old_q + float(fill.price) * add_q) / float(new_q)
                state["filled_qty"] = new_q
                state["vwap_slices"] = int(state.get("vwap_slices") or 0) + 1
                state["pending_entry_trade_id"] = ""
                state["pending_order_submitted"] = False
                direction = str(state.get("active_direction") or ("Long" if fill.side == "buy" else "Short"))
                if not bool(state.get("scaled")) and not bool(state.get("st_be_armed")):
                    # keep structure extreme stop until first profit scale
                    if state.get("vwap_struct_stop") is not None:
                        state["stop_price"] = float(state["vwap_struct_stop"])
                self._set_targets(state, float(state["entry_price"]), direction)
                self._commit_state(state)
                return StrategyActions(
                    self._initial_exits(fill.trade_id, direction, state, fill.ts),
                    self._cancel_reduce(context, fill.trade_id),
                    [],
                    [],
                    [],
                )

            state["active_trade_id"] = fill.trade_id
            state["pending_entry_trade_id"] = ""
            state["pending_order_submitted"] = False
            # one-shot per structure key for structure_only resting
            ck = state.get("pending_structure_key")
            if ck is not None:
                state["structure_resting_consumed_key"] = float(ck)
            state["entry_price"] = float(fill.price)
            state["filled_qty"] = int(fill.quantity)
            state["scaled"] = False
            state["scaled2"] = False
            state["st_be_armed"] = False
            state["bars_held"] = 0
            state["qty_eod"] = 0
            state["qty_runner"] = 0
            if str(self.config.get("plan") or "") == "vwap_scalein":
                state["vwap_slices"] = int(state.get("vwap_slices") or 0) + 1
            direction = "Long" if fill.side == "buy" else "Short"
            state["active_direction"] = direction
            risk = float(self.config["risk_pts"])
            entry = float(fill.price)
            stop = entry - risk if direction == "Long" else entry + risk
            # prefer precomputed pending stop (structure-based)
            if state.get("pending_stop") is not None:
                stop = float(state["pending_stop"])
            if state.get("vwap_struct_stop") is not None and str(self.config.get("plan") or "") == "vwap_scalein":
                stop = float(state["vwap_struct_stop"])
            state["stop_price"] = stop
            self._set_targets(state, entry, direction)
            self._commit_state(state)
            return StrategyActions(
                self._initial_exits(fill.trade_id, direction, state, fill.ts),
                [],
                [],
                [],
                [],
            )

        if role in {"scale_1r", "scale_22", "scale_25"}:
            state["scaled"] = True
            entry = float(state.get("entry_price") or fill.price)
            tight = float(self.config.get("tight_sl_pts") or 0.0)
            direction = str(state.get("active_direction") or "")
            if tight > 0:
                state["stop_price"] = entry - tight if direction == "Long" else entry + tight
            else:
                state["stop_price"] = entry
            rem = int(state.get("filled_qty") or 0) - int(self.config["scale_qty"])
            if self._is_scale_run():
                # next: scale2 @ tp2, then runner @ tp3 — no EOD bucket
                state["qty_eod"] = 0
                state["qty_scale2"] = min(int(self.config.get("scale2_qty") or 5), rem)
                state["qty_runner"] = rem - int(state["qty_scale2"])
                self._commit_state(state)
                return StrategyActions(
                    self._post_scale22_exits(
                        fill.trade_id, direction, state, fill.ts
                    ),
                    self._cancel_reduce(context, fill.trade_id),
                    [],
                    [],
                    [],
                )
            state["qty_eod"] = min(int(self.config["eod_qty"]), rem)
            state["qty_runner"] = rem - int(state["qty_eod"])
            self._commit_state(state)
            # replace stop with BE + add runner target; cancel old stop via modify path = cancel+replace
            return StrategyActions(
                self._post_scale_exits(fill.trade_id, direction, state, fill.ts),
                self._cancel_reduce(context, fill.trade_id),
                [],
                [],
                [],
            )

        if role == "scale_50":
            state["scaled2"] = True
            rem = abs(int(context.position_quantity))
            state["qty_scale2"] = 0
            state["qty_runner"] = rem
            state["stop_price"] = float(state.get("entry_price") or fill.price)
            self._commit_state(state)
            return StrategyActions(
                self._post_scale50_exits(
                    fill.trade_id, str(state.get("active_direction") or ""), state, fill.ts
                ),
                self._cancel_reduce(context, fill.trade_id),
                [],
                [],
                [],
            )

        exit_roles = {
            "stop",
            "be_stop",
            "tight_stop",
            "risk_stop",
            "runner_tp",
            "eod",
            "st_flip",
            "flatten",
            "market",
            "take_profit",
            "target",
        }
        if role in exit_roles or abs(int(context.position_quantity)) == 0:
            # if partial, keep managing
            if abs(int(context.position_quantity)) == 0:
                if str(self.config.get("plan") or "") == "vwap_scalein":
                    # structure stop-out only → wait for 15m close back inside structure
                    if role in {"risk_stop", "structure_stop", "stop"}:
                        state["vwap_wait_reclaim"] = True
                        if state.get("vwap_struct_bottom") is not None:
                            state["vwap_wait_bottom"] = state.get("vwap_struct_bottom")
                            state["vwap_wait_top"] = state.get("vwap_struct_top")
                    state["vwap_slices"] = 0
                state["active_trade_id"] = ""
                state["scaled"] = False
                state["entry_price"] = None
                self._commit_state(state)
                return StrategyActions([], self._cancel_reduce(context, fill.trade_id), [], [], [])
            self._commit_state(state)
            return StrategyActions.empty()

        self._commit_state(state)
        return StrategyActions.empty()

    # ---------------------------------------------------------------- entry
    def _arm_pending_state(
        self,
        state: Dict[str, Any],
        *,
        side: str,
        limit_px: float,
        stop_px: float,
        st_signal: float,
        structure_key: float,
    ) -> None:
        trade_id = new_id("trade")
        state["pending_entry_trade_id"] = trade_id
        state["pending_side"] = side
        state["pending_rth_closes"] = 0
        state["pending_limit"] = float(limit_px)
        state["pending_stop"] = float(stop_px)
        state["pending_st_signal"] = float(st_signal)
        state["pending_structure_key"] = float(structure_key)
        state["pending_qty"] = int(self.config["entry_qty"])
        state["pending_stop_seen"] = False
        state["active_direction"] = "Long" if side == "long" else "Short"

    def _entry_limit_intent(self, state: Dict[str, Any], ts: str) -> OrderIntent:
        p_side = str(state.get("pending_side") or "")
        side = "buy" if p_side == "long" else "sell"
        lim = _round_tick(float(state["pending_limit"]), float(self.config["tick_size"]))
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(state["pending_entry_trade_id"]),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=int(state.get("pending_qty") or self.config["entry_qty"]),
            limit_price=lim,
            reason="entry",
            requires_verification=False,
            bracket_role="entry",
            live_after_ts=ts,
        )

    def _structure_bounds(self, prog: str) -> Optional[Tuple[float, float, float]]:
        """bottom, top, key for latest structure matching program."""
        if prog == "buy":
            if not self._bull:
                return None
            st = self._bull[-1]
            bottom = float(st["key"])
            top = float(st.get("extreme") or st["key"])
            key = bottom
        elif prog == "sell":
            if not self._bear:
                return None
            st = self._bear[-1]
            top = float(st["key"])
            bottom = float(st.get("extreme") or st["key"])
            key = top
        else:
            return None
        if bottom > top:
            bottom, top = top, bottom
        return bottom, top, key

    def _manage_vwap_scalein(
        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
        cancels: List[CancelIntent],
        st_stop: Optional[float],
        st_bull: bool,
        dt,
    ) -> StrategyActions:
        """Split VWAP entries inside structure; SL at extreme; 15m reclaim re-arm."""
        orders: List[OrderIntent] = []
        ready = len(self._bull) >= int(self.config["list_size"]) and len(self._bear) >= int(
            self.config["list_size"]
        )
        prog = state.get("program")
        session = dt.date().isoformat()

        # session VWAP
        if state.get("vwap_session") != session:
            state["vwap_session"] = session
            state["vwap_num"] = 0.0
            state["vwap_den"] = 0.0
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        vol = float(getattr(bar, "volume", 0.0) or 0.0)
        if vol <= 0:
            vol = 1.0
        tp = (hi + lo + cl) / 3.0
        state["vwap_num"] = float(state.get("vwap_num") or 0.0) + tp * vol
        state["vwap_den"] = float(state.get("vwap_den") or 0.0) + vol
        vwap = float(state["vwap_num"]) / float(state["vwap_den"]) if state["vwap_den"] else cl

        # 15m close reclaim after stop — vs *current* structure (not stale post-stop bounds)
        bucket_key = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0).isoformat()
        prev_bucket = state.get("vwap_bucket")
        if prev_bucket and prev_bucket != bucket_key and state.get("vwap_wait_reclaim"):
            prev_close = state.get("vwap_prev_bucket_close")
            cur = self._structure_bounds(str(prog)) if prog in {"buy", "sell"} else None
            if prev_close is not None and cur is not None:
                b, t_, _k = cur
                if float(b) <= float(prev_close) <= float(t_):
                    state["vwap_wait_reclaim"] = False
                    state["vwap_slices"] = 0
        if prev_bucket != bucket_key:
            state["vwap_prev_bucket_close"] = state.get("vwap_bucket_close")
            state["vwap_bucket"] = bucket_key
        state["vwap_bucket_close"] = cl

        working = self._has_working_entry(context)
        pending = bool(state.get("pending_entry_trade_id"))

        if state.get("vwap_wait_reclaim"):
            return StrategyActions.empty()

        if not ready or prog not in {"buy", "sell"}:
            return StrategyActions.empty()

        bounds = self._structure_bounds(str(prog))
        if bounds is None:
            return StrategyActions.empty()
        bottom, top, key = bounds
        side = "long" if prog == "buy" else "short"
        stop0 = bottom if side == "long" else top
        state["vwap_struct_stop"] = stop0
        state["vwap_struct_bottom"] = bottom
        state["vwap_struct_top"] = top

        n_slices = int(self.config.get("n_slices") or 5)
        slice_qty = int(self.config.get("slice_qty") or 3)
        slices_done = int(state.get("vwap_slices") or 0)
        filled_qty = int(state.get("filled_qty") or 0) if state.get("active_trade_id") else 0
        max_qty = int(self.config.get("entry_qty") or n_slices * slice_qty)
        if slices_done >= n_slices or filled_qty >= max_qty:
            return StrategyActions.empty()
        if working or pending:
            return StrategyActions.empty()

        # must be inside structure (price or VWAP)
        inside = (bottom <= cl <= top) or (bottom <= vwap <= top)
        if not inside:
            return StrategyActions.empty()
        if not (bottom <= vwap <= top):
            return StrategyActions.empty()

        # require usable room between VWAP and structure stop (parity with analytic)
        min_risk = float(self.config.get("tight_sl_pts") or 12.0)
        if side == "long" and (float(vwap) - float(stop0)) < min_risk:
            return StrategyActions.empty()
        if side == "short" and (float(stop0) - float(vwap)) < min_risk:
            return StrategyActions.empty()

        # spacing: at most one slice per 15m bucket
        if state.get("vwap_last_slice_bucket") == bucket_key:
            return StrategyActions.empty()

        # arm limit at VWAP
        self._arm_pending_state(
            state,
            side=side,
            limit_px=float(vwap),
            stop_px=float(stop0),
            st_signal=float(st_stop or vwap),
            structure_key=float(key),
        )
        # keep same campaign id when adding
        if state.get("active_trade_id"):
            state["pending_entry_trade_id"] = str(state["active_trade_id"])
        state["pending_qty"] = slice_qty
        state["vwap_last_slice_bucket"] = bucket_key
        # only submit if non-marketable-ish: long wants price above limit
        if (side == "long" and cl > vwap) or (side == "short" and cl < vwap):
            orders.append(self._entry_limit_intent(state, bar.ts))
            state["pending_order_submitted"] = True
        elif (side == "long" and lo <= vwap) or (side == "short" and hi >= vwap):
            # already touching — submit for next-bar fill
            orders.append(self._entry_limit_intent(state, bar.ts))
            state["pending_order_submitted"] = True
        return StrategyActions(orders, cancels, [], [], []) if orders else StrategyActions.empty()

    def _manage_touch_st_align(
        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
        cancels: List[CancelIntent],
        st_stop: Optional[float],
        st_bull: bool,
    ) -> StrategyActions:
        """Watch structure key → touch+through → ST flip (or fade20 limit @ key)."""
        orders: List[OrderIntent] = []
        ready = len(self._bull) >= int(self.config["list_size"]) and len(self._bear) >= int(
            self.config["list_size"]
        )
        prog = state.get("program")
        working = self._has_working_entry(context)
        pending = bool(state.get("pending_entry_trade_id"))
        fade_mins = int(self.config.get("fade_after_through_mins") or 0)
        entry_kind = str(state.get("touch_entry_kind") or "cont_flip")

        if working or pending:
            # Cancel if original program flips away (fade is opposite of orig side).
            orig = str(state.get("touch_orig_side") or state.get("pending_side") or "")
            bad = (orig == "long" and prog != "buy") or (orig == "short" and prog != "sell")
            if entry_kind == "fade20":
                # fade pending: also blow cancel if stop traded through before fill
                p_stop = state.get("pending_stop")
                p_side = str(state.get("pending_side") or "")
                blown = False
                if p_stop is not None:
                    blown = (p_side == "long" and float(bar.low) <= float(p_stop)) or (
                        p_side == "short" and float(bar.high) >= float(p_stop)
                    )
                if blown or bad or (not ready) or prog not in {"buy", "sell"}:
                    cancels.extend(self._cancel_entries(context, "touch_align_cancel"))
                    state["pending_entry_trade_id"] = ""
                    state["pending_side"] = ""
                    state["touch_phase"] = ""
                    state["touch_entry_kind"] = ""
                    return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
                # ensure fade limit is live once
                if pending and not working and not bool(state.get("pending_order_submitted")):
                    orders.append(self._entry_limit_intent(state, bar.ts))
                    state["pending_order_submitted"] = True
                    return StrategyActions(orders, cancels, [], [], [])
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            if bad or (not ready) or prog not in {"buy", "sell"}:
                cancels.extend(self._cancel_entries(context, "touch_align_cancel"))
                state["pending_entry_trade_id"] = ""
                state["pending_side"] = ""
                state["touch_phase"] = ""
                state["touch_entry_kind"] = ""
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()

        if not ready or prog not in {"buy", "sell"} or st_stop is None:
            state["touch_phase"] = ""
            return StrategyActions.empty()

        side = "long" if prog == "buy" else "short"
        sk = self._latest_key("bull" if prog == "buy" else "bear")
        if sk is None:
            return StrategyActions.empty()

        phase = str(state.get("touch_phase") or "")
        if not phase:
            state["touch_phase"] = "watch"
            state["touch_key"] = float(sk)
            state["touch_touched"] = False
            state["touch_through"] = False
            state["touch_through_streak"] = 0
            state["touch_rth_closes"] = 0
            state["touch_orig_side"] = side
            state["touch_entry_kind"] = ""
            phase = "watch"

        if str(state.get("touch_orig_side") or side) != side and phase != "fade_limit":
            state["touch_phase"] = ""
            return StrategyActions.empty()

        if phase == "watch" and not bool(state.get("touch_touched")):
            state["touch_key"] = float(sk)

        key = float(state.get("touch_key") or sk)
        lo = float(bar.low)
        hi = float(bar.high)
        c = float(bar.close)
        still_through = False
        if side == "long":
            if lo <= key:
                state["touch_touched"] = True
            if lo < key:
                state["touch_through"] = True
            still_through = c < key
        else:
            if hi >= key:
                state["touch_touched"] = True
            if hi > key:
                state["touch_through"] = True
            still_through = c > key
        if still_through:
            state["touch_through_streak"] = int(state.get("touch_through_streak") or 0) + 1
        else:
            state["touch_through_streak"] = 0
        if bool(state.get("touch_through")):
            state["touch_phase"] = "wait_flip"
            phase = "wait_flip"

        # fade20: still through N minutes → fade limit @ key (opposite), stop = key ±25
        if (
            fade_mins > 0
            and phase == "wait_flip"
            and int(state.get("touch_through_streak") or 0) >= fade_mins
        ):
            fade_side = "short" if side == "long" else "long"
            tp1 = float(self.config.get("tp1_pts") or 25.0)
            fade_stop = key + tp1 if fade_side == "short" else key - tp1
            self._arm_pending_state(
                state,
                side=fade_side,
                limit_px=float(key),
                stop_px=float(fade_stop),
                st_signal=float(st_stop),
                structure_key=float(key),
            )
            state["touch_phase"] = "fade_limit"
            state["touch_entry_kind"] = "fade20"
            state["touch_orig_side"] = side
            state["pending_order_submitted"] = False
            # only arm when non-marketable: fade sell needs price below key; fade buy above
            if (fade_side == "short" and c < key) or (fade_side == "long" and c > key):
                orders.append(self._entry_limit_intent(state, bar.ts))
                state["pending_order_submitted"] = True
                return StrategyActions(orders, cancels, [], [], [])
            return StrategyActions.empty()

        if phase != "wait_flip":
            return StrategyActions.empty()

        if len(self._bars_1m) < 2:
            return StrategyActions.empty()
        prev = self._bars_1m[-2]
        prev_bull = bool(prev.get("st_bull"))
        prev_stop = prev.get("st_stop")
        if prev_stop is None:
            return StrategyActions.empty()
        prev_stop = float(prev_stop)
        flip = False
        if side == "long" and (not prev_bull) and st_bull and c > prev_stop:
            flip = True
        elif side == "short" and prev_bull and (not st_bull) and c < prev_stop:
            flip = True
        if not flip:
            return StrategyActions.empty()

        stop0 = float(st_stop)
        bad_stop = (side == "long" and stop0 >= c) or (side == "short" and stop0 <= c)
        if bad_stop:
            state["touch_phase"] = "watch"
            state["touch_touched"] = False
            state["touch_through"] = False
            state["touch_through_streak"] = 0
            state["touch_key"] = float(sk)
            return StrategyActions.empty()

        self._arm_pending_state(
            state,
            side=side,
            limit_px=float(key),
            stop_px=stop0,
            st_signal=stop0,
            structure_key=float(key),
        )
        state["touch_phase"] = ""
        state["touch_touched"] = False
        state["touch_through"] = False
        state["touch_through_streak"] = 0
        state["touch_entry_kind"] = "cont_flip"
        state["touch_orig_side"] = side
        trade_id = str(state["pending_entry_trade_id"])
        qty = int(state.get("pending_qty") or self.config["entry_qty"])
        order = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side="buy" if side == "long" else "sell",
            order_type="market",
            quantity=qty,
            reason="entry",
            requires_verification=False,
            bracket_role="entry",
            live_after_ts=bar.ts,
        )
        orders.append(order)
        return StrategyActions(orders, cancels, [], [], [])

    def _manage_structure_resting(
        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
        cancels: List[CancelIntent],
    ) -> StrategyActions:
        """Program+structure resting limit — no ST break required.

        Places a limit at the latest structure key for the active program and
        leaves it working across sessions (until fill, stop blow, program flip,
        key change, or pending_max_closes).

        Guards against marketable-limit churn:
          - submit the entry intent once per arm
          - only arm when the limit is non-marketable (price must pull back)
          - after fill / blow / program flip, consume that key until a new
            structure key prints
        """
        orders: List[OrderIntent] = []
        ready = len(self._bull) >= int(self.config["list_size"]) and len(self._bear) >= int(
            self.config["list_size"]
        )
        prog = state.get("program")
        working = self._has_working_entry(context)
        pending = bool(state.get("pending_entry_trade_id"))

        def _clear_pending() -> None:
            state["pending_entry_trade_id"] = ""
            state["pending_side"] = ""
            state["pending_stop_seen"] = False
            state["pending_order_submitted"] = False

        def _consume_key() -> None:
            ck = state.get("pending_structure_key")
            if ck is None:
                ck = state.get("pending_limit")
            if ck is not None:
                state["structure_resting_consumed_key"] = float(ck)

        # Cancel / hold while armed
        if pending or working:
            p_side = str(state.get("pending_side") or "")
            p_stop = state.get("pending_stop")
            p_lim = state.get("pending_limit")
            bad = (p_side == "long" and prog != "buy") or (p_side == "short" and prog != "sell")
            blown = False
            if p_stop is not None:
                blown = (p_side == "long" and float(bar.low) <= float(p_stop)) or (
                    p_side == "short" and float(bar.high) >= float(p_stop)
                )
            new_sk = None
            if prog == "buy":
                new_sk = self._latest_key("bull")
            elif prog == "sell":
                new_sk = self._latest_key("bear")
            key_changed = (
                new_sk is not None
                and p_lim is not None
                and abs(float(new_sk) - float(p_lim)) > 1e-9
            )
            if bad or blown or (not ready) or prog not in {"buy", "sell"}:
                if blown or bad:
                    _consume_key()
                cancels.extend(self._cancel_entries(context, "structure_pending_cancel"))
                _clear_pending()
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            if key_changed:
                cancels.extend(self._cancel_entries(context, "structure_key_update"))
                _clear_pending()
                pending = False
                working = False
                # fall through — may arm the new key this bar
            else:
                if (
                    pending
                    and not working
                    and not bool(state.get("pending_order_submitted"))
                ):
                    orders.append(self._entry_limit_intent(state, bar.ts))
                    state["pending_order_submitted"] = True
                    return StrategyActions(orders, cancels, [], [], [])
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()

        if not ready or prog not in {"buy", "sell"}:
            return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()

        sk = self._latest_key("bull" if prog == "buy" else "bear")
        if sk is None:
            return StrategyActions.empty()
        consumed = state.get("structure_resting_consumed_key")
        if consumed is not None and abs(float(sk) - float(consumed)) < 1e-9:
            return StrategyActions.empty()

        side = "long" if prog == "buy" else "short"
        px = float(bar.close)
        # Resting only: buy limit needs price above key; sell limit needs price below.
        if side == "long" and px <= float(sk):
            return StrategyActions.empty()
        if side == "short" and px >= float(sk):
            return StrategyActions.empty()

        risk = float(self.config["risk_pts"])
        stop_px = sk - risk if side == "long" else sk + risk
        self._arm_pending_state(
            state,
            side=side,
            limit_px=float(sk),
            stop_px=float(stop_px),
            st_signal=float(self._st_stop or sk),
            structure_key=float(sk),
        )
        orders.append(self._entry_limit_intent(state, bar.ts))
        state["pending_order_submitted"] = True
        return StrategyActions(orders, cancels, [], [], [])

    def _arm_external_signal(self, bar: Bar, state: Dict[str, Any]) -> bool:
        """Arm next CSV signal once bar.ts >= signal_ts (consume in order)."""
        if self._ext_i >= len(self._ext_signals):
            return False
        # skip signals that are still in the future
        while self._ext_i < len(self._ext_signals):
            sig = self._ext_signals[self._ext_i]
            if _ts_le(sig["signal_ts"], bar.ts):
                break
            return False
        sig = self._ext_signals[self._ext_i]
        self._ext_i += 1
        self._arm_pending_state(
            state,
            side=str(sig["side"]),
            limit_px=float(sig["limit_px"]),
            stop_px=float(sig["stop"]),
            st_signal=float(sig.get("st_at_signal") or sig["limit_px"]),
            structure_key=float(sig.get("structure_key") or sig["limit_px"]),
        )
        return True

    def _manage_pending_entry(
        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
        cancels: List[CancelIntent],
    ) -> StrategyActions:
        """touch: blown cancels (research). sweep_reclaim: blown arms reclaim gate."""
        p_stop = state.get("pending_stop")
        p_lim = state.get("pending_limit")
        p_side = str(state.get("pending_side") or "")
        entry_mode = str(self.config.get("entry_mode") or "touch").lower()
        prog = state.get("program")
        # External signals ignore live program flips for cancel (signal already chosen).
        bad = False
        if str(self.config.get("signal_source") or "internal") != "external":
            bad = (p_side == "long" and prog != "buy") or (p_side == "short" and prog != "sell")
        blown = False
        if p_stop is not None:
            blown = (p_side == "long" and float(bar.low) <= float(p_stop)) or (
                p_side == "short" and float(bar.high) >= float(p_stop)
            )
        touched = False
        if p_lim is not None:
            touched = (p_side == "long" and float(bar.low) <= float(p_lim)) or (
                p_side == "short" and float(bar.high) >= float(p_lim)
            )
        reclaimed = False
        if p_lim is not None:
            # after a stop sweep, require trade back through entry
            reclaimed = (p_side == "long" and float(bar.high) >= float(p_lim)) or (
                p_side == "short" and float(bar.low) <= float(p_lim)
            )

        if entry_mode == "sweep_reclaim":
            if bad:
                state["pending_entry_trade_id"] = ""
                state["pending_side"] = ""
                state["pending_stop_seen"] = False
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            if blown:
                state["pending_stop_seen"] = True
            if not bool(state.get("pending_stop_seen")):
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            if not reclaimed:
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            # fall through to submit entry
        else:
            # touch (research): same-bar blown-before-fill cancels
            if blown or bad:
                state["pending_entry_trade_id"] = ""
                state["pending_side"] = ""
                state["pending_stop_seen"] = False
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()
            if not touched:
                return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()

        if self._has_working_entry(context):
            return StrategyActions([], cancels, [], [], []) if cancels else StrategyActions.empty()

        trade_id = str(state["pending_entry_trade_id"])
        qty = int(state.get("pending_qty") or self.config["entry_qty"])
        side = "buy" if p_side == "long" else "sell"
        lim = _round_tick(float(p_lim), float(self.config["tick_size"]))
        order = OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="limit",
            quantity=qty,
            limit_price=lim,
            reason="entry",
            requires_verification=False,
            bracket_role="entry",
            live_after_ts=bar.ts,
        )
        return StrategyActions([order], cancels, [], [], [])

    # ---------------------------------------------------------------- manage
    def _manage_open(
        self,
        bar: Bar,
        context: StrategyContext,
        state: Dict[str, Any],
        st_stop: Optional[float],
        st_bull: bool,
        is_eod: bool,
    ) -> StrategyActions:
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        direction = str(state.get("active_direction") or "")
        trade_id = str(state.get("active_trade_id") or "")
        qty = abs(int(context.position_quantity))
        scaled = bool(state.get("scaled"))
        flip_ok = (not scaled) or bool(self.config.get("st_flip_after_scale"))
        mode = str(self.config.get("st_flip_mode") or "always").lower()
        if mode == "off":
            flip_ok = False
        min_bars = int(self.config.get("st_flip_min_bars") or 0)
        bars_held = int(state.get("bars_held") or 0) + 1
        state["bars_held"] = bars_held

        # ST flip
        if (
            bool(self.config.get("st_flip_exit"))
            and flip_ok
            and st_stop is not None
            and qty > 0
        ):
            entry = state.get("entry_price")
            adverse = False
            favourable = False
            if entry is not None:
                if direction == "Long":
                    adverse = float(bar.close) < float(entry)
                    favourable = float(bar.close) > float(entry)
                elif direction == "Short":
                    adverse = float(bar.close) > float(entry)
                    favourable = float(bar.close) < float(entry)
            bars_ok = bars_held >= min_bars
            st_signal = False
            if direction == "Long" and (not st_bull) and float(bar.close) < float(st_stop):
                st_signal = True
            if direction == "Short" and st_bull and float(bar.close) > float(st_stop):
                st_signal = True

            if st_signal:
                if mode == "fav_be":
                    # Research structure_sl_scale_run: fav → BE hold; adverse → flatten
                    if favourable and not bool(state.get("st_be_armed")):
                        state["st_be_armed"] = True
                        state["stop_price"] = float(entry)
                        # cancel working stops/targets and re-arm with BE stop + remaining TPs
                        cancels.extend(self._cancel_reduce(context, trade_id))
                        orders.extend(
                            self._rearm_after_st_be(trade_id, direction, state, bar.ts, qty)
                        )
                        return StrategyActions(orders, cancels, [], [], [])
                    if adverse:
                        cancels.extend(self._cancel_reduce(context, trade_id))
                        orders.append(self._flatten(context, bar.ts, "st_flip", qty))
                        state["active_trade_id"] = ""
                        return StrategyActions(orders, cancels, [], [], [])
                    # flat at entry on flip: treat as adverse flatten
                    if not favourable and not adverse:
                        cancels.extend(self._cancel_reduce(context, trade_id))
                        orders.append(self._flatten(context, bar.ts, "st_flip", qty))
                        state["active_trade_id"] = ""
                        return StrategyActions(orders, cancels, [], [], [])
                else:
                    mode_ok = True
                    if mode == "adverse":
                        mode_ok = adverse
                    elif mode == "after_n":
                        mode_ok = bars_ok
                    elif mode == "adverse_after_n":
                        mode_ok = adverse and bars_ok
                    # mode == always: mode_ok stays True
                    if mode_ok:
                        cancels.extend(self._cancel_reduce(context, trade_id))
                        orders.append(self._flatten(context, bar.ts, "st_flip", qty))
                        state["active_trade_id"] = ""
                        return StrategyActions(orders, cancels, [], [], [])

        # EOD: flatten eod bucket (or all if never scaled). Disabled for scale_run.
        # If eod_flatten but eod_qty==0 (vwap_scalein runner ladder), flatten remainder.
        if (
            bool(self.config.get("eod_flatten", True))
            and is_eod
            and not state.get("eod_done")
            and qty > 0
        ):
            state["eod_done"] = True
            eod_qty = int(state.get("qty_eod") or 0)
            if (not scaled) or eod_qty <= 0:
                cancels.extend(self._cancel_reduce(context, trade_id))
                orders.append(self._flatten(context, bar.ts, "eod", qty))
                state["active_trade_id"] = ""
                return StrategyActions(orders, cancels, [], [], [])
            eod_qty = min(eod_qty, qty)
            orders.append(self._flatten(context, bar.ts, "eod", eod_qty))
            state["qty_eod"] = 0
            return StrategyActions(orders, cancels, [], [], [])

        return StrategyActions.empty()

    def _is_scale_run(self) -> bool:
        return str(self.config.get("plan") or "") in {
            "scale_run",
            "touch_st_align",
            "touch_st_align_fade20",
            "vwap_scalein",
        }

    def _scale1_role(self) -> str:
        plan = str(self.config.get("plan") or "")
        if plan in {"touch_st_align", "touch_st_align_fade20", "vwap_scalein"}:
            return "scale_25"
        return "scale_22" if self._is_scale_run() else "scale_1r"

    def _set_targets(self, state: Dict[str, Any], entry: float, direction: str) -> None:
        risk = float(self.config["risk_pts"])
        sign = 1.0 if direction == "Long" else -1.0
        tp1_pts = float(self.config.get("tp1_pts") or 0.0)
        tp2_pts = float(self.config.get("tp2_pts") or 0.0)
        tp3_pts = float(self.config.get("tp3_pts") or 0.0)
        if tp1_pts > 0:
            state["tp1"] = entry + sign * tp1_pts
        else:
            state["tp1"] = entry + sign * risk
        if tp2_pts > 0:
            state["tp2"] = entry + sign * tp2_pts
        else:
            state["tp2"] = float("nan")
        if tp3_pts > 0:
            state["tp_runner"] = entry + sign * tp3_pts
        else:
            runner_r = float(self.config.get("runner_r") or 3.0)
            state["tp_runner"] = entry + sign * runner_r * risk

    def _initial_exits(self, trade_id: str, direction: str, state: Dict[str, Any], ts: str) -> List[OrderIntent]:
        tick = float(self.config["tick_size"])
        stop = _round_tick(float(state["stop_price"]), tick)
        tp1 = _round_tick(float(state["tp1"]), tick)
        scale_qty = int(self.config["scale_qty"])
        entry_qty = int(self.config["entry_qty"])
        # VWAP scale-in may be partial — size stop/TP to filled qty, not full entry_qty
        filled = int(state.get("filled_qty") or 0)
        stop_qty = filled if filled > 0 else entry_qty
        scale_qty = min(scale_qty, stop_qty)
        exit_side = "sell" if direction == "Long" else "buy"
        scale_role = self._scale1_role()
        out = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=stop_qty,
                stop_price=stop,
                reason="risk_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="risk_stop",
                live_after_ts=ts,
            ),
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=scale_qty,
                limit_price=tp1,
                reason=scale_role,
                requires_verification=False,
                reduce_only=True,
                bracket_role=scale_role,
                live_after_ts=ts,
            ),
        ]
        return out

    def _post_scale_exits(self, trade_id: str, direction: str, state: Dict[str, Any], ts: str) -> List[OrderIntent]:
        tick = float(self.config["tick_size"])
        be = _round_tick(float(state["entry_price"]), tick)
        tpr = _round_tick(float(state["tp_runner"]), tick)
        runner_qty = int(state.get("qty_runner") or 0)
        eod_qty = int(state.get("qty_eod") or 0)
        rem = runner_qty + eod_qty
        exit_side = "sell" if direction == "Long" else "buy"
        out = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=rem,
                stop_price=be,
                reason="be_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="be_stop",
                live_after_ts=ts,
            )
        ]
        if runner_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=tpr,
                    reason="runner_tp",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="runner_tp",
                    live_after_ts=ts,
                )
            )
        return out

    def _post_scale22_exits(self, trade_id: str, direction: str, state: Dict[str, Any], ts: str) -> List[OrderIntent]:
        """After first scale: BE (scale_run) or ±tight_sl (touch_st_align) + +50 batch."""
        tick = float(self.config["tick_size"])
        entry = float(state["entry_price"])
        tight = float(self.config.get("tight_sl_pts") or 0.0)
        if tight > 0:
            stop_px = entry - tight if direction == "Long" else entry + tight
            stop_reason = "tight_stop"
        else:
            stop_px = entry
            stop_reason = "be_stop"
        stop_px = _round_tick(stop_px, tick)
        tp2 = _round_tick(float(state["tp2"]), tick)
        scale2_qty = int(state.get("qty_scale2") or 0)
        runner_qty = int(state.get("qty_runner") or 0)
        rem = scale2_qty + runner_qty
        exit_side = "sell" if direction == "Long" else "buy"
        out = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=rem,
                stop_price=stop_px,
                reason=stop_reason,
                requires_verification=False,
                reduce_only=True,
                bracket_role=stop_reason,
                live_after_ts=ts,
            )
        ]
        if scale2_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=scale2_qty,
                    limit_price=tp2,
                    reason="scale_50",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="scale_50",
                    live_after_ts=ts,
                )
            )
        return out

    def _post_scale50_exits(self, trade_id: str, direction: str, state: Dict[str, Any], ts: str) -> List[OrderIntent]:
        """After +50 scale: BE stop + +200 runner."""
        tick = float(self.config["tick_size"])
        be = _round_tick(float(state["entry_price"]), tick)
        tpr = _round_tick(float(state["tp_runner"]), tick)
        runner_qty = int(state.get("qty_runner") or 0)
        exit_side = "sell" if direction == "Long" else "buy"
        out = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=runner_qty,
                stop_price=be,
                reason="be_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="be_stop",
                live_after_ts=ts,
            )
        ]
        if runner_qty > 0:
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=runner_qty,
                    limit_price=tpr,
                    reason="runner_tp",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="runner_tp",
                    live_after_ts=ts,
                )
            )
        return out

    def _rearm_after_st_be(
        self, trade_id: str, direction: str, state: Dict[str, Any], ts: str, qty: int
    ) -> List[OrderIntent]:
        """Favourable ST-flip: BE stop + remaining ladder targets for open qty."""
        tick = float(self.config["tick_size"])
        be = _round_tick(float(state["entry_price"]), tick)
        exit_side = "sell" if direction == "Long" else "buy"
        out = [
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="stop",
                quantity=qty,
                stop_price=be,
                reason="be_stop",
                requires_verification=False,
                reduce_only=True,
                bracket_role="be_stop",
                live_after_ts=ts,
            )
        ]
        # Restage unfinished ladder from current open size
        if not bool(state.get("scaled")):
            tp1 = _round_tick(float(state["tp1"]), tick)
            q = min(int(self.config["scale_qty"]), qty)
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=q,
                    limit_price=tp1,
                    reason=self._scale1_role(),
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role=self._scale1_role(),
                    live_after_ts=ts,
                )
            )
        elif not bool(state.get("scaled2")):
            tp2 = _round_tick(float(state["tp2"]), tick)
            q = min(int(self.config.get("scale2_qty") or 5), qty)
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=q,
                    limit_price=tp2,
                    reason="scale_50",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="scale_50",
                    live_after_ts=ts,
                )
            )
        else:
            tpr = _round_tick(float(state["tp_runner"]), tick)
            out.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=exit_side,
                    order_type="limit",
                    quantity=qty,
                    limit_price=tpr,
                    reason="runner_tp",
                    requires_verification=False,
                    reduce_only=True,
                    bracket_role="runner_tp",
                    live_after_ts=ts,
                )
            )
        return out

    def _flatten(self, context: StrategyContext, ts: str, reason: str, qty: int) -> OrderIntent:
        side = "sell" if context.position_quantity > 0 else "buy"
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=str(self.state.get("active_trade_id") or new_id("trade")),
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market",
            quantity=abs(int(qty)),
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role=reason,
            live_after_ts=ts,
        )

    # -------------------------------------------------------------- structure
    def _roll_st_session(self, session: str) -> None:
        if self._session_bars:
            self._warm_sessions.append(list(self._session_bars))
        self._session_bars = []
        self._st_session = session
        self._seed_st_from_warm()

    def _seed_st_from_warm(self) -> None:
        """Seed SuperTrend state from up to 2 prior RTH sessions (exact research EWM)."""
        warm: List[Dict[str, float]] = []
        for sess in self._warm_sessions:
            warm.extend(sess)
        state = _supertrend_state(
            warm, atr_len=int(self.config["atr_len"]), mult=float(self.config["atr_mult"])
        )
        self._st_atr = state["atr"]
        self._st_final_upper = state["final_upper"]
        self._st_final_lower = state["final_lower"]
        self._st_bull = state["bull"]
        self._st_stop = state["stop"]
        self._st_prev_close = state["prev_close"]
        self._st_bar_i = state["bar_i"]

    def _append_1m(self, bar: Bar) -> None:
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        atr_len = int(self.config["atr_len"])
        mult = float(self.config["atr_mult"])
        alpha = 1.0 / float(atr_len)
        if self._st_prev_close is None:
            tr = hi - lo
        else:
            pc = float(self._st_prev_close)
            tr = max(hi - lo, abs(hi - pc), abs(lo - pc))
        if self._st_atr is None:
            self._st_atr = tr
        else:
            self._st_atr = (1.0 - alpha) * float(self._st_atr) + alpha * tr
        self._st_bar_i = int(self._st_bar_i or 0) + 1
        atr_ok = self._st_bar_i >= atr_len and self._st_atr is not None
        st_stop: Optional[float] = None
        st_bull = bool(self._st_bull)
        if atr_ok:
            hl2 = 0.5 * (hi + lo)
            basic_upper = hl2 + mult * float(self._st_atr)
            basic_lower = hl2 - mult * float(self._st_atr)
            if self._st_final_upper is None or self._st_final_lower is None:
                self._st_final_upper = basic_upper
                self._st_final_lower = basic_lower
                st_bull = True
            else:
                prev_upper = float(self._st_final_upper)
                prev_lower = float(self._st_final_lower)
                pc = float(self._st_prev_close) if self._st_prev_close is not None else cl
                self._st_final_upper = (
                    basic_upper if (basic_upper < prev_upper or pc > prev_upper) else prev_upper
                )
                self._st_final_lower = (
                    basic_lower if (basic_lower > prev_lower or pc < prev_lower) else prev_lower
                )
                if st_bull:
                    st_bull = False if cl < self._st_final_lower else True
                else:
                    st_bull = True if cl > self._st_final_upper else False
            st_stop = self._st_final_lower if st_bull else self._st_final_upper
            self._st_bull = st_bull
            self._st_stop = st_stop
        else:
            self._st_stop = None
        self._st_prev_close = cl
        row = {
            "ts": bar.ts,
            "open": float(bar.open),
            "high": hi,
            "low": lo,
            "close": cl,
            "st_stop": self._st_stop,
            "st_bull": bool(self._st_bull),
        }
        self._session_bars.append(row)
        self._bars_1m.append(row)
        max_n = int(self.config["history_bars"])
        if len(self._bars_1m) > max_n:
            self._bars_1m = self._bars_1m[-max_n:]

    def _supertrend_now(self) -> Tuple[Optional[float], bool]:
        return self._st_stop, bool(self._st_bull)

    def _update_15m(self, bar: Bar) -> None:
        dt = _parse_dt(bar.ts)
        # bucket start = floor to 15m
        minute = (dt.minute // 15) * 15
        bucket_ts = dt.replace(minute=minute, second=0, microsecond=0)
        key = bucket_ts.isoformat()
        if self._bucket is None or self._bucket["key"] != key:
            # finalize previous
            if self._bucket is not None:
                self._on_15m_close(self._bucket)
            self._bucket = {
                "key": key,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "end_ts": bar.ts,
            }
        else:
            self._bucket["high"] = max(float(self._bucket["high"]), float(bar.high))
            self._bucket["low"] = min(float(self._bucket["low"]), float(bar.low))
            self._bucket["close"] = float(bar.close)
            self._bucket["end_ts"] = bar.ts

        # takeouts on forming bar extremes (causal with completed structures)
        self._apply_takeouts(float(bar.high), float(bar.low), bar.ts)

    def _on_15m_close(self, bucket: Dict[str, Any]) -> None:
        # confirm swings using trailing completed 15m bars stored lightly
        hist = list(self.state.get("bars_15") or [])
        hist.append(
            {
                "ts": bucket["end_ts"],
                "high": bucket["high"],
                "low": bucket["low"],
                "close": bucket["close"],
            }
        )
        if len(hist) > 400:
            hist = hist[-400:]
        self.state["bars_15"] = hist
        left = int(self.config["swing_left"])
        right = int(self.config["swing_right"])
        if len(hist) < left + right + 1:
            return
        i = len(hist) - right - 1
        if i < left:
            return
        highs = [float(x["high"]) for x in hist]
        lows = [float(x["low"]) for x in hist]
        h = highs[i]
        l = lows[i]
        is_sh = all(h > highs[i - k] for k in range(1, left + 1)) and all(
            h >= highs[i + k] for k in range(1, right + 1)
        )
        is_sl = all(l < lows[i - k] for k in range(1, left + 1)) and all(
            l <= lows[i + k] for k in range(1, right + 1)
        )
        if is_sh and is_sl:
            if (h - lows[i]) >= (highs[i] - l):
                is_sl = False
            else:
                is_sh = False
        confirm_ts = hist[i + right]["ts"]
        if is_sh:
            self._add_swing(confirm_ts, "H", h)
        elif is_sl:
            self._add_swing(confirm_ts, "L", l)

    def _add_swing(self, ts: str, kind: str, px: float) -> None:
        if self._swings and self._swings[-1][1] == kind:
            prev = self._swings[-1]
            if kind == "H" and px >= prev[2]:
                self._swings[-1] = (ts, kind, px)
            elif kind == "L" and px <= prev[2]:
                self._swings[-1] = (ts, kind, px)
            else:
                return
        else:
            self._swings.append((ts, kind, px))
        if len(self._swings) < 4:
            return
        w = self._swings[-4:]
        kinds = [s[1] for s in w]
        pxs = [s[2] for s in w]
        if kinds == ["L", "H", "L", "H"] and pxs[2] < pxs[0] and pxs[3] > pxs[1]:
            sig = ("bull", round(pxs[2], 4), round(pxs[3], 4), ts)
            if sig not in self._seen_struct:
                self._seen_struct.add(sig)
                self._bull.append(
                    {
                        "kind": "bull",
                        "key": pxs[2],
                        "extreme": pxs[3],  # HH
                        "taken_out": False,
                        "ts": ts,
                    }
                )
        if kinds == ["H", "L", "H", "L"] and pxs[2] > pxs[0] and pxs[3] < pxs[1]:
            sig = ("bear", round(pxs[2], 4), round(pxs[3], 4), ts)
            if sig not in self._seen_struct:
                self._seen_struct.add(sig)
                self._bear.append(
                    {
                        "kind": "bear",
                        "key": pxs[2],
                        "extreme": pxs[3],  # LL
                        "taken_out": False,
                        "ts": ts,
                    }
                )

    def _apply_takeouts(self, hi: float, lo: float, ts: str) -> None:
        state = self._state()
        bear_n = int(state.get("bear_takeouts") or 0)
        bull_n = int(state.get("bull_takeouts") or 0)
        need = int(self.config["takeouts_to_flip"])
        for st in self._bear:
            if st.get("taken_out"):
                continue
            if hi > float(st["key"]):
                st["taken_out"] = True
                bear_n += 1
                if bear_n >= need:
                    state["program"] = "buy"
                    bear_n = 0
                    bull_n = 0
        for st in self._bull:
            if st.get("taken_out"):
                continue
            if lo < float(st["key"]):
                st["taken_out"] = True
                bull_n += 1
                if bull_n >= need:
                    state["program"] = "sell"
                    bear_n = 0
                    bull_n = 0
        state["bear_takeouts"] = bear_n
        state["bull_takeouts"] = bull_n
        self.state = state

    def _latest_key(self, kind: str) -> Optional[float]:
        dq = self._bull if kind == "bull" else self._bear
        if not dq:
            return None
        return float(dq[-1]["key"])

    # ---------------------------------------------------------------- utils
    def _state(self) -> Dict[str, Any]:
        if not isinstance(self.state, dict):
            self.state = {}
        return self.state

    def _commit_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _has_working_entry(self, context: StrategyContext) -> bool:
        for o in context.strategy_open_orders:
            if o.reduce_only:
                continue
            role = str(getattr(o, "bracket_role", "") or "")
            if role == "entry" or (role == "" and o.order_type == "limit"):
                return True
        return False

    def _cancel_entries(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        out = []
        for o in context.strategy_open_orders:
            if o.reduce_only:
                continue
            role = str(getattr(o, "bracket_role", "") or "")
            if role == "entry" or (role == "" and o.order_type == "limit"):
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, reason))
        return out

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and o.reduce_only:
                out.append(CancelIntent(self.instance.strategy_id, o.broker_order_id, "replace_exits"))
        return out


def _parse_dt(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return NY.localize(dt)
    return dt.astimezone(NY)


def _in_rth(t: time) -> bool:
    return NY_OPEN <= t < NY_CLOSE


def _in_session(t: time, start: time, end: time) -> bool:
    return start <= t < end


def _round_tick(px: float, tick: float) -> float:
    if tick <= 0:
        return px
    return round(px / tick) * tick


def _supertrend_state(
    rows: List[Dict[str, float]], *, atr_len: int, mult: float
) -> Dict[str, Any]:
    """Run research EWM SuperTrend over rows; return ending state for incremental follow-on."""
    out: Dict[str, Any] = {
        "atr": None,
        "final_upper": None,
        "final_lower": None,
        "bull": True,
        "stop": None,
        "prev_close": None,
        "bar_i": 0,
    }
    if not rows:
        return out
    alpha = 1.0 / float(atr_len)
    atr: Optional[float] = None
    final_upper: Optional[float] = None
    final_lower: Optional[float] = None
    bull = True
    prev_close: Optional[float] = None
    stop: Optional[float] = None
    for i, row in enumerate(rows, start=1):
        hi = float(row["high"])
        lo = float(row["low"])
        cl = float(row["close"])
        if prev_close is None:
            tr = hi - lo
        else:
            tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        atr = tr if atr is None else (1.0 - alpha) * atr + alpha * tr
        if i >= atr_len and atr is not None:
            hl2 = 0.5 * (hi + lo)
            basic_upper = hl2 + mult * atr
            basic_lower = hl2 - mult * atr
            if final_upper is None or final_lower is None:
                final_upper = basic_upper
                final_lower = basic_lower
                bull = True
            else:
                pc = prev_close if prev_close is not None else cl
                final_upper = basic_upper if (basic_upper < final_upper or pc > final_upper) else final_upper
                final_lower = basic_lower if (basic_lower > final_lower or pc < final_lower) else final_lower
                if bull:
                    bull = False if cl < final_lower else True
                else:
                    bull = True if cl > final_upper else False
            stop = final_lower if bull else final_upper
        else:
            stop = None
        prev_close = cl
    out.update(
        {
            "atr": atr,
            "final_upper": final_upper,
            "final_lower": final_lower,
            "bull": bull,
            "stop": stop,
            "prev_close": prev_close,
            "bar_i": len(rows),
        }
    )
    return out
