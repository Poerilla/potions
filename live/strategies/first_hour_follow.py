"""NQ first-hour follow / fade from opening-candle close (5m tape).

Builds opening-candle OHLC on 5m bars (default 09:30–10:30). On the last
opening bar, enter in candle direction:

- ``market_close``: fill at close on the signal bar
- ``close_limit``: resting limit at close; cancel if SL swept before fill
- ``retrace_limit``: limit at body retrace; SL at candle extreme

Risk default: SL = candle open (body). Target: ``r_mult`` × body or × R.
Flatten at eod (RTH only).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TextIO

from ..models import Bar, CancelIntent, ModifyIntent, OrderIntent, StrategyActions
from .atr_supertrend_dca import TrendPoint
from .base import StrategyContext, StrategyPlugin
from .features import feature_snapshot


class FirstHourFollowStrategy(StrategyPlugin):
    strategy_type = "first_hour_follow"
    version = "v1"

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
            "tick_size": 0.25,
            "entry_qty": 1,
            "r_mult": 3.0,
            "fade": False,
            "fh_start": "09:30",
            "fh_end": "10:30",
            "bar_minutes": 5,
            "eod_cutoff": "15:59",
            "min_fh_bars": 10,
            "require_fh_body": "",  # "" | strong | mid | weak
            "strong_body_min": 0.66,
            "weak_body_max": 0.33,
            "require_sweep_side": "",  # "" | sweep_with_side | fade_follow_through
            # Optional YYYY-MM-DD allowlist (one date per line, or CSV with session_date).
            # When set, skip entry unless the NY session date is listed.
            "entry_dates_path": "",
            "session_levels_path": "",
            "st_trail": False,
            "st_atr_len": 14,
            "st_atr_mult": 3.0,
            "london_start": "03:00",
            "london_end": "09:30",
            "trail_approach_pts": 8.0,
            "trail_bounce_pts": 12.0,
            "trail_aggressive_pts": 25.0,
            "trail_log_path": "",
            # entry / risk
            # market_close: fill at FH close on signal bar
            # close_limit: resting limit at FH close (fill on later touch); cancel if SL swept first
            # retrace_limit: limit at close −/+ retrace_frac×body; SL forced to extreme
            "entry_mode": "market_close",  # market_close | close_limit | retrace_limit
            "retrace_frac": 0.0,  # body retrace from close (long: close - frac*body)
            "sl_mode": "open",  # open | body_frac | extreme
            "sl_body_frac": 0.5,  # used when sl_mode=body_frac
            "tp_mode": "body_mult",  # body_mult | r_mult (R = |entry_plan − SL|)
            # When set (e.g. [1,2,3]), place 1-lot TP limits at each R multiple
            # instead of a single target. Stop covers full entry_qty; no OCO
            # across rungs so partial scale-outs leave remaining TPs live.
            "tp_ladder_r": [],
            "suppress_alerts": True,
        }
        try:
            self.config.update(json.loads(instance.config_json or "{}"))
        except json.JSONDecodeError:
            pass
        self._session_levels: Dict[str, Dict[str, float]] = {}
        self._load_session_levels()
        self._entry_dates: Optional[set] = self._load_entry_dates()
        self._hourly: List[Bar] = []
        self._hour_key: Optional[Tuple[str, int]] = None
        self._hour_ohlc: Optional[Dict[str, float]] = None
        self._st_processed = 0
        self._st_trs: List[float] = []
        self._st_atr: Optional[float] = None
        self._st_final_upper: Optional[float] = None
        self._st_final_lower: Optional[float] = None
        self._st_bullish = True
        self._st_points: List[TrendPoint] = []
        self._st_from_1h = False
        self._trail_log: Optional[TextIO] = None
        path = str(self.config.get("trail_log_path") or "").strip()
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self._trail_log = p.open("a", encoding="utf-8")

    def on_bar_close(self, bar, context: StrategyContext) -> StrategyActions:
        if not bar.complete:
            return StrategyActions.empty()
        tf = str(bar.timeframe or "")
        if tf in {"1h", "1H", "60", "60min", "60m"}:
            return self._on_1h(bar, context)
        if tf not in {"5m", "5min", "5"}:
            return StrategyActions.empty()
        return self._on_5m(bar, context)

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        trade = self._trade(fill.trade_id, state)
        role = str(fill.reason or "")

        if role == "entry":
            direction = "Long" if fill.side == "buy" else "Short"
            planned_qty = int(trade.get("entry_qty") or fill.quantity)
            trade.update(
                {
                    "status": "open",
                    "direction": direction,
                    "entry_price": float(fill.price),
                    "entry_qty": max(planned_qty, int(fill.quantity)),
                    "filled_qty": int(fill.quantity),
                }
            )
            state["current_leg_open"] = True
            state["active_trade_id"] = fill.trade_id
            state["active_direction"] = direction
            state["phase"] = "in_trade"
            self._commit(state)
            return StrategyActions(
                self._exit_orders(fill.trade_id, direction, state, fill.ts),
                [],
                [],
                [],
                [],
            )

        # Ladder scale-outs: leave remaining TPs/stop live until flat.
        if role in {"tp1", "tp2", "tp3", "target", "tp"}:
            hits = list(trade.get("tp_hits") or [])
            hits.append(role)
            trade["tp_hits"] = hits
            if context.position_quantity == 0:
                trade["status"] = "closed"
                state["current_leg_open"] = False
                state["done"] = True
                state["phase"] = "done"
                self._commit(state)
                return StrategyActions([], self._cancel_reduce(context, fill.trade_id), [], [], [])
            self._commit(state)
            return StrategyActions.empty()

        if role in {"stop", "eod_close", "eod"}:
            if context.position_quantity == 0:
                trade["status"] = "closed"
                state["current_leg_open"] = False
                state["done"] = True
                state["phase"] = "done"
                if role == "stop" and bool(trade.get("trail_armed")):
                    trade["exit_kind"] = "st_trail"
                self._commit(state)
                return StrategyActions([], self._cancel_reduce(context, fill.trade_id), [], [], [])
            self._commit(state)
            return StrategyActions.empty()

        self._commit(state)
        return StrategyActions.empty()

    def _on_1h(self, bar, context: StrategyContext) -> StrategyActions:
        if not bool(self.config.get("st_trail")):
            return StrategyActions.empty()
        self._st_from_1h = True
        if not self._hourly or self._hourly[-1].ts != bar.ts:
            self._hourly.append(bar)
        self._current_trend_point()
        return StrategyActions.empty()

    def _on_5m(self, bar, context: StrategyContext) -> StrategyActions:
        dt = _parse_dt(bar.ts)
        session = dt.date().isoformat()
        t = dt.time()
        state = self._state()
        if state.get("session_date") != session:
            self._roll_session_levels(state, session)
            state = self._fresh(session)

        self._update_session_levels(state, bar, dt)
        self._update_hourly_from_5m(bar, dt)

        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        modifies: List[ModifyIntent] = []
        features = []

        fh_start = self._time("fh_start")
        fh_end = self._time("fh_end")
        eod = self._time("eod_cutoff")
        rth_close = time(16, 0)
        signal_t = self._signal_time()
        bar_mins = int(self.config.get("bar_minutes") or 5)
        bar_end = (datetime.combine(date(2000, 1, 1), t) + timedelta(minutes=bar_mins)).time()
        is_rth = fh_start <= t < rth_close

        if state.get("current_leg_open") and context.position_quantity != 0 and t <= fh_start:
            cancels.extend(self._cancel_all(context))
            orders.append(self._close_all(context, bar.ts, "eod_close"))
            state["done"] = True
            state["phase"] = "carry_flatten"
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        if is_rth and (t >= eod or bar_end > eod):
            cancels.extend(self._cancel_all(context))
            if context.position_quantity != 0:
                orders.append(self._close_all(context, bar.ts, "eod_close"))
            state["done"] = True
            state["phase"] = "eod"
            self._commit(state)
            return StrategyActions(orders, cancels, [], [], [])

        if state.get("current_leg_open") and context.position_quantity != 0:
            self._note_trail_approach(bar, state)
            if bool(self.config.get("st_trail")):
                modifies.extend(self._maybe_trail_stop(bar, context, state))

        # Pending limit entry: invalidate if planned SL is swept before fill.
        entry_mode_live = str(self.config.get("entry_mode") or "").strip().lower()
        if (
            state.get("entry_submitted")
            and not state.get("current_leg_open")
            and entry_mode_live in {"retrace_limit", "close_limit"}
            and not state.get("done")
        ):
            inv = self._maybe_invalidate_pending(bar, context, state)
            if inv is not None:
                return inv

        if state.get("done") or state.get("current_leg_open") or state.get("entry_submitted"):
            self._commit(state)
            return StrategyActions(orders, cancels, modifies, [], [], features)

        if fh_start <= t < fh_end:
            self._update_fh(state, bar)
            state["fh_bars"] = int(state.get("fh_bars") or 0) + 1
            state["phase"] = "building_fh"

        if t != signal_t:
            self._commit(state)
            return StrategyActions.empty()

        self._update_fh(state, bar)
        if int(state.get("fh_bars") or 0) < int(self.config["min_fh_bars"]):
            state["done"] = True
            state["phase"] = "fh_too_short"
            self._commit(state)
            return StrategyActions.empty()

        o = _to_float(state.get("fh_open"))
        h = _to_float(state.get("fh_high"))
        l = _to_float(state.get("fh_low"))
        c = _to_float(state.get("fh_close"))
        if None in (o, h, l, c):
            state["done"] = True
            state["phase"] = "fh_incomplete"
            self._commit(state)
            return StrategyActions.empty()

        body = abs(c - o)
        rng = h - l
        tick = float(self.config["tick_size"])
        if body < tick or rng < tick:
            state["done"] = True
            state["phase"] = "doji_or_flat"
            self._commit(state)
            return StrategyActions.empty()

        body_frac = body / rng
        req = str(self.config.get("require_fh_body") or "").strip().lower()
        if req == "strong" and body_frac < float(self.config["strong_body_min"]):
            state["done"] = True
            state["phase"] = "body_not_strong"
            state["skip_reason"] = "fh_body"
            self._commit(state)
            return StrategyActions.empty()
        if req == "weak" and body_frac > float(self.config["weak_body_max"]):
            state["done"] = True
            state["phase"] = "body_not_weak"
            self._commit(state)
            return StrategyActions.empty()
        if req == "mid" and not (
            float(self.config["weak_body_max"]) < body_frac < float(self.config["strong_body_min"])
        ):
            state["done"] = True
            state["phase"] = "body_not_mid"
            self._commit(state)
            return StrategyActions.empty()

        sweep_label = self._sweep_label(state, h, l, c > o)
        req_sw = str(self.config.get("require_sweep_side") or "").strip().lower()
        if req_sw and sweep_label != req_sw:
            state["done"] = True
            state["phase"] = "sweep_gate"
            state["skip_reason"] = sweep_label or "no_sweep"
            self._commit(state)
            return StrategyActions.empty()

        if self._entry_dates is not None:
            session = str(state.get("session_date") or "")
            if session not in self._entry_dates:
                state["done"] = True
                state["phase"] = "entry_dates_gate"
                state["skip_reason"] = "not_in_entry_dates"
                self._commit(state)
                return StrategyActions.empty()

        candle_long = c > o
        fade = bool(self.config.get("fade"))
        if fade:
            side = "sell" if candle_long else "buy"
        else:
            side = "buy" if candle_long else "sell"
        direction = 1 if side == "buy" else -1
        r_mult = float(self.config["r_mult"])
        entry_mode = str(self.config.get("entry_mode") or "market_close").strip().lower()
        retrace_frac = float(self.config.get("retrace_frac") or 0.0)
        sl_mode = str(self.config.get("sl_mode") or "open").strip().lower()
        tp_mode = str(self.config.get("tp_mode") or "body_mult").strip().lower()
        sl_body_frac = float(self.config.get("sl_body_frac") or 0.5)

        if entry_mode == "retrace_limit":
            # Limit at body retrace from close; SL at candle extreme.
            if side == "buy":
                entry_px = c - retrace_frac * body
                sl = l
            else:
                entry_px = c + retrace_frac * body
                sl = h
            if (side == "buy" and entry_px <= sl + tick) or (side == "sell" and entry_px >= sl - tick):
                state["done"] = True
                state["phase"] = "retrace_invalid_geometry"
                self._commit(state)
                return StrategyActions.empty()
        elif entry_mode == "close_limit":
            # Resting limit at FH close; SL from sl_mode (default open = candle body risk).
            entry_px = c
            if fade:
                sl = 2.0 * c - o
            elif sl_mode == "body_frac":
                risk_plan = sl_body_frac * body
                if risk_plan < tick:
                    state["done"] = True
                    state["phase"] = "sl_too_tight"
                    self._commit(state)
                    return StrategyActions.empty()
                sl = c - risk_plan if side == "buy" else c + risk_plan
            elif sl_mode == "extreme":
                sl = l if side == "buy" else h
            else:
                sl = o
        else:
            entry_px = c  # market_close at FH close
            if fade:
                sl = 2.0 * c - o
            elif sl_mode == "body_frac":
                risk_plan = sl_body_frac * body
                if risk_plan < tick:
                    state["done"] = True
                    state["phase"] = "sl_too_tight"
                    self._commit(state)
                    return StrategyActions.empty()
                sl = c - risk_plan if side == "buy" else c + risk_plan
            elif sl_mode == "extreme":
                sl = l if side == "buy" else h
            else:
                sl = o

        risk = abs(entry_px - sl)
        if risk < tick:
            state["done"] = True
            state["phase"] = "risk_too_small"
            self._commit(state)
            return StrategyActions.empty()

        if tp_mode == "r_mult":
            tp = entry_px + direction * r_mult * risk
        else:
            tp = entry_px + direction * r_mult * body

        ladder_raw = self.config.get("tp_ladder_r") or []
        if isinstance(ladder_raw, str):
            ladder_raw = [x for x in ladder_raw.replace(",", " ").split() if x]
        ladder_r: List[float] = []
        for x in ladder_raw:
            try:
                ladder_r.append(float(x))
            except (TypeError, ValueError):
                continue
        tp_ladder: List[float] = []
        if ladder_r:
            for rm in ladder_r:
                tp_ladder.append(entry_px + direction * float(rm) * risk)
            tp = tp_ladder[-1]

        qty = int(self.config["entry_qty"])
        if ladder_r and qty < len(ladder_r):
            qty = len(ladder_r)
        trade_id = self._new_trade_id(state)
        state["trades"][trade_id] = {
            "status": "pending_entry",
            "fh_open": o,
            "fh_high": h,
            "fh_low": l,
            "fh_close": c,
            "body": body,
            "entry_plan": entry_px,
            "stop_price": sl,
            "tp_price": tp,
            "tp_ladder": tp_ladder,
            "tp_ladder_r": ladder_r,
            "tp_hits": [],
            "entry_qty": qty,
            "candle_side": "long" if candle_long else "short",
            "fade": fade,
            "sweep_label": sweep_label,
            "trail_armed": False,
            "approach_n": 0,
            "bounce_n": 0,
            "aggressive_bounce_n": 0,
            "max_bounce_pts": 0.0,
            "entry_mode": entry_mode,
            "sl_mode": sl_mode,
            "tp_mode": tp_mode,
        }
        state["entry_submitted"] = True
        state["phase"] = "entry_submitted"
        state["active_trade_id"] = trade_id
        if entry_mode in {"retrace_limit", "close_limit"}:
            expiry = _session_expiry(session, self._time("eod_cutoff"))
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=side,
                    order_type="limit",
                    quantity=qty,
                    limit_price=entry_px,
                    reason="entry",
                    requires_verification=False,
                    bracket_role="entry",
                    live_after_ts=bar.ts,
                    expires_after_ts=expiry,
                )
            )
        else:
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=side,
                    order_type="market_close",
                    quantity=qty,
                    reason="entry",
                    requires_verification=False,
                    bracket_role="entry",
                    live_after_ts=bar.ts,
                )
            )
        levels = self._levels_for(session)
        features.append(
            feature_snapshot(
                self.instance,
                "fh_follow_entry",
                bar.ts,
                event_ts=bar.ts,
                available_at_ts=bar.ts,
                source="first_hour_follow.signal_bar",
                value_ref=str(c),
                metadata={
                    "fh_open": o,
                    "fh_high": h,
                    "fh_low": l,
                    "fh_close": c,
                    "body_frac": body_frac,
                    "sweep_label": sweep_label,
                    "require_sweep_side": req_sw,
                    "st_trail": bool(self.config.get("st_trail")),
                    "prev_day_high": levels.get("prev_day_high"),
                    "prev_day_low": levels.get("prev_day_low"),
                    "w_high": levels.get("w_high"),
                    "w_low": levels.get("w_low"),
                    "london_high": levels.get("london_high"),
                    "london_low": levels.get("london_low"),
                },
            )
        )
        self._commit(state)
        return StrategyActions(orders, cancels, modifies, [], [], features)

    def _maybe_trail_stop(
        self, bar, context: StrategyContext, state: Dict[str, Any]
    ) -> List[ModifyIntent]:
        trade_id = str(state.get("active_trade_id") or "")
        if not trade_id:
            return []
        trade = self._trade(trade_id, state)
        direction = str(trade.get("direction") or state.get("active_direction") or "")
        point = self._st_asof(bar.ts)
        if point is None:
            return []
        cur = _to_float(trade.get("stop_price"))
        if cur is None:
            return []
        new_stop = cur
        if direction == "Long" and point.bullish:
            new_stop = max(cur, float(point.stop))
        elif direction == "Short" and (not point.bullish):
            new_stop = min(cur, float(point.stop))
        tick = float(self.config["tick_size"])
        if abs(new_stop - cur) < tick:
            return []
        out: List[ModifyIntent] = []
        for order in context.strategy_open_orders:
            if order.trade_id != trade_id:
                continue
            if order.bracket_role not in {"stop", "protective_stop", "runner_stop"}:
                continue
            if str(order.order_type).lower() != "stop":
                continue
            out.append(
                ModifyIntent(
                    strategy_id=self.instance.strategy_id,
                    broker_order_id=order.broker_order_id,
                    reason="st_trail",
                    stop_price=new_stop,
                    live_after_ts=bar.ts,
                )
            )
        if out:
            trade["stop_price"] = new_stop
            trade["trail_armed"] = True
            trade["st_px"] = float(point.stop)
            trade["st_bullish"] = bool(point.bullish)
            self._log_trail(
                {
                    "event": "trail_modify",
                    "ts": bar.ts,
                    "trade_id": trade_id,
                    "session_date": state.get("session_date"),
                    "direction": direction,
                    "stop_price": new_stop,
                    "st_px": float(point.stop),
                    "st_bullish": bool(point.bullish),
                }
            )
        return out

    def _note_trail_approach(self, bar, state: Dict[str, Any]) -> None:
        if not bool(self.config.get("st_trail")):
            return
        trade_id = str(state.get("active_trade_id") or "")
        if not trade_id:
            return
        trade = self._trade(trade_id, state)
        trail = _to_float(trade.get("stop_price"))
        if trail is None:
            return
        direction = str(trade.get("direction") or state.get("active_direction") or "")
        approach = float(self.config.get("trail_approach_pts") or 8.0)
        bounce_need = float(self.config.get("trail_bounce_pts") or 12.0)
        aggressive = float(self.config.get("trail_aggressive_pts") or 25.0)
        hi = float(bar.high)
        lo = float(bar.low)
        close = float(bar.close)
        if direction == "Long":
            dist = lo - trail
            hit = lo <= trail
            away = close - trail
        elif direction == "Short":
            dist = trail - hi
            hit = hi >= trail
            away = trail - close
        else:
            return
        if dist > approach:
            return
        trade["approach_n"] = int(trade.get("approach_n") or 0) + 1
        bounce = (not hit) and away >= bounce_need
        agr = bounce and away >= aggressive
        if bounce:
            trade["bounce_n"] = int(trade.get("bounce_n") or 0) + 1
            trade["max_bounce_pts"] = max(float(trade.get("max_bounce_pts") or 0.0), float(away))
        if agr:
            trade["aggressive_bounce_n"] = int(trade.get("aggressive_bounce_n") or 0) + 1
        self._log_trail(
            {
                "event": "aggressive_bounce" if agr else ("bounce" if bounce else ("hit_bar" if hit else "approach")),
                "ts": bar.ts,
                "trade_id": trade_id,
                "session_date": state.get("session_date"),
                "direction": direction,
                "trail": trail,
                "high": hi,
                "low": lo,
                "close": close,
                "dist_pts": dist,
                "away_pts": away,
                "hit": hit,
                "bounce": bounce,
                "aggressive": agr,
            }
        )

    def _sweep_label(self, state: Dict[str, Any], fh_high: float, fh_low: float, candle_long: bool) -> str:
        levels = self._levels_for(str(state.get("session_date") or ""))
        pdh = levels.get("prev_day_high")
        pdl = levels.get("prev_day_low")
        pwh = levels.get("w_high")
        pwl = levels.get("w_low")
        lon_h = levels.get("london_high")
        lon_l = levels.get("london_low")
        hi_sweep = False
        lo_sweep = False
        if pdh is not None and fh_high >= pdh:
            hi_sweep = True
        if pwh is not None and fh_high >= pwh:
            hi_sweep = True
        if lon_h is not None and fh_high >= lon_h:
            hi_sweep = True
        if pdl is not None and fh_low <= pdl:
            lo_sweep = True
        if pwl is not None and fh_low <= pwl:
            lo_sweep = True
        if lon_l is not None and fh_low <= lon_l:
            lo_sweep = True
        if not (hi_sweep or lo_sweep):
            return "no_sweep"
        fade_ft = (hi_sweep and (not candle_long)) or (lo_sweep and candle_long)
        if fade_ft:
            return "fade_follow_through"
        return "sweep_with_side"

    def _levels_for(self, session: str) -> Dict[str, float]:
        out: Dict[str, float] = {}
        inc = (self.state or {}).get("level_accum") or {}
        for key in ("prev_day_high", "prev_day_low", "w_high", "w_low", "london_high", "london_low"):
            if key in inc and inc[key] not in (None, ""):
                try:
                    out[key] = float(inc[key])
                except (TypeError, ValueError):
                    pass
        file_lv = self._session_levels.get(session) or {}
        out.update({k: float(v) for k, v in file_lv.items() if v not in (None, "")})
        return out

    def _load_entry_dates(self) -> Optional[set]:
        path = str(self.config.get("entry_dates_path") or "").strip()
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return set()
        dates: set = set()
        text = p.read_text(encoding="utf-8")
        first = (text.splitlines() or [""])[0].strip().lower()
        if "session_date" in first and "," in first:
            import csv
            from io import StringIO

            reader = csv.DictReader(StringIO(text))
            for row in reader:
                day = str(row.get("session_date") or "").strip()[:10]
                if len(day) >= 10:
                    dates.add(day)
        else:
            for line in text.splitlines():
                day = line.strip().split(",")[0].strip()[:10]
                if len(day) >= 10 and day[0].isdigit():
                    dates.add(day)
        return dates

    def _load_session_levels(self) -> None:
        path = str(self.config.get("session_levels_path") or "").strip()
        if not path:
            return
        p = Path(path)
        if not p.exists():
            return
        import csv

        with p.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                day = str(row.get("session_date") or "")
                if not day:
                    continue
                item: Dict[str, float] = {}
                for key in ("prev_day_high", "prev_day_low", "w_high", "w_low", "london_high", "london_low"):
                    raw = row.get(key)
                    if raw in (None, ""):
                        continue
                    try:
                        item[key] = float(raw)
                    except (TypeError, ValueError):
                        continue
                if item:
                    self._session_levels[day] = item

    def _roll_session_levels(self, prev: Dict[str, Any], new_session: str) -> None:
        accum = dict(prev.get("level_accum") or {})
        day_h = _to_float(accum.get("rth_high"))
        day_l = _to_float(accum.get("rth_low"))
        if day_h is not None and day_l is not None:
            accum["prev_day_high"] = day_h
            accum["prev_day_low"] = day_l
            week_key = _iso_week(str(prev.get("session_date") or ""))
            new_week = _iso_week(new_session)
            if week_key and new_week and week_key != new_week:
                accum["w_high"] = _to_float(accum.get("week_high")) or day_h
                accum["w_low"] = _to_float(accum.get("week_low")) or day_l
                accum["week_high"] = None
                accum["week_low"] = None
            else:
                wh = _to_float(accum.get("week_high"))
                wl = _to_float(accum.get("week_low"))
                accum["week_high"] = day_h if wh is None else max(wh, day_h)
                accum["week_low"] = day_l if wl is None else min(wl, day_l)
        accum["rth_high"] = None
        accum["rth_low"] = None
        accum["london_high"] = None
        accum["london_low"] = None
        # stash onto instance state so _fresh can copy
        self._pending_accum = accum

    def _update_session_levels(self, state: Dict[str, Any], bar, dt: datetime) -> None:
        accum = state.setdefault("level_accum", dict(getattr(self, "_pending_accum", {}) or {}))
        t = dt.time()
        lon0 = self._time("london_start")
        lon1 = self._time("london_end")
        h = float(bar.high)
        l = float(bar.low)
        if lon0 <= t < lon1:
            lh = _to_float(accum.get("london_high"))
            ll = _to_float(accum.get("london_low"))
            accum["london_high"] = h if lh is None else max(lh, h)
            accum["london_low"] = l if ll is None else min(ll, l)
        if self._time("fh_start") <= t < time(16, 0):
            rh = _to_float(accum.get("rth_high"))
            rl = _to_float(accum.get("rth_low"))
            accum["rth_high"] = h if rh is None else max(rh, h)
            accum["rth_low"] = l if rl is None else min(rl, l)
        state["level_accum"] = accum

    def _update_hourly_from_5m(self, bar, dt: datetime) -> None:
        if not bool(self.config.get("st_trail")) or self._st_from_1h:
            return
        key = (dt.date().isoformat(), dt.hour)
        o, h, l, c = float(bar.open), float(bar.high), float(bar.low), float(bar.close)
        if self._hour_key is None:
            self._hour_key = key
            self._hour_ohlc = {"open": o, "high": h, "low": l, "close": c}
            return
        if key != self._hour_key:
            self._flush_hour_bar(bar.instrument)
            self._hour_key = key
            self._hour_ohlc = {"open": o, "high": h, "low": l, "close": c}
            return
        assert self._hour_ohlc is not None
        self._hour_ohlc["high"] = max(self._hour_ohlc["high"], h)
        self._hour_ohlc["low"] = min(self._hour_ohlc["low"], l)
        self._hour_ohlc["close"] = c

    def _flush_hour_bar(self, instrument: str) -> None:
        if self._hour_key is None or self._hour_ohlc is None:
            return
        day, hour = self._hour_key
        ts = "%sT%02d:00:00" % (day, hour)
        hb = Bar(
            instrument=instrument,
            timeframe="1h",
            ts=ts,
            open=self._hour_ohlc["open"],
            high=self._hour_ohlc["high"],
            low=self._hour_ohlc["low"],
            close=self._hour_ohlc["close"],
            volume=0.0,
            complete=True,
            source="5m_agg",
        )
        if not self._hourly or self._hourly[-1].ts != ts:
            self._hourly.append(hb)
            self._current_trend_point()

    def _current_trend_point(self) -> Optional[TrendPoint]:
        hourly = self._hourly
        if self._st_processed > len(hourly):
            self._st_processed = 0
            self._st_trs = []
            self._st_atr = None
            self._st_final_upper = None
            self._st_final_lower = None
            self._st_bullish = True
            self._st_points = []
        atr_len = int(self.config.get("st_atr_len") or 14)
        atr_mult = float(self.config.get("st_atr_mult") or 3.0)
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
                self._st_final_upper = (
                    basic_upper if basic_upper < prev_upper or prev_close > prev_upper else prev_upper
                )
                self._st_final_lower = (
                    basic_lower if basic_lower > prev_lower or prev_close < prev_lower else prev_lower
                )
                if self._st_bullish and bar.close < self._st_final_lower:
                    self._st_bullish = False
                elif (not self._st_bullish) and bar.close > self._st_final_upper:
                    self._st_bullish = True
            stop = self._st_final_lower if self._st_bullish else self._st_final_upper
            self._st_points.append(TrendPoint(ts=bar.ts, stop=float(stop), bullish=bool(self._st_bullish)))
            self._st_processed += 1
        return self._st_points[-1] if self._st_points else None

    def _st_asof(self, ts: str) -> Optional[TrendPoint]:
        """Hour-complete ST: left-label hour T is usable at T+1h."""
        if not self._st_points:
            return None
        cur = _parse_dt(ts)
        last: Optional[TrendPoint] = None
        for pt in self._st_points:
            avail = _parse_dt(pt.ts) + timedelta(hours=1)
            if avail <= cur:
                last = pt
            else:
                break
        return last

    def _log_trail(self, row: Dict[str, Any]) -> None:
        if self._trail_log is None:
            return
        self._trail_log.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        self._trail_log.flush()

    def _exit_orders(
        self, trade_id: str, direction: str, state: Dict[str, Any], ts: str
    ) -> List[OrderIntent]:
        trade = self._trade(trade_id, state)
        stop = float(trade["stop_price"])
        qty = int(trade.get("entry_qty") or self.config["entry_qty"])
        exit_side = "sell" if direction == "Long" else "buy"
        expiry = _session_expiry(str(state.get("session_date") or ""), self._time("eod_cutoff"))
        ladder = list(trade.get("tp_ladder") or [])
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
                live_after_ts=ts,
            )
        ]
        if ladder:
            # 1 lot per rung; no shared OCO so remaining TPs stay after scale-out.
            # Reduce-only stop auto-clamps to open position when a TP fills.
            for i, tp_px in enumerate(ladder):
                role = "tp%d" % (i + 1)
                out.append(
                    OrderIntent.create(
                        strategy_id=self.instance.strategy_id,
                        trade_id=trade_id,
                        instrument=self.instance.instrument,
                        account_mode=self.instance.account_mode,
                        side=exit_side,
                        order_type="limit",
                        quantity=1,
                        limit_price=float(tp_px),
                        reason=role,
                        requires_verification=False,
                        reduce_only=True,
                        bracket_role=role,
                        expires_after_ts=expiry,
                        live_after_ts=ts,
                    )
                )
            return out

        tp = float(trade["tp_price"])
        oco = "%s_fh_oco" % trade_id
        out[0] = OrderIntent.create(
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
            oco_group=oco,
            expires_after_ts=expiry,
            live_after_ts=ts,
        )
        out.append(
            OrderIntent.create(
                strategy_id=self.instance.strategy_id,
                trade_id=trade_id,
                instrument=self.instance.instrument,
                account_mode=self.instance.account_mode,
                side=exit_side,
                order_type="limit",
                quantity=qty,
                limit_price=tp,
                reason="tp",
                requires_verification=False,
                reduce_only=True,
                bracket_role="target",
                oco_group=oco,
                expires_after_ts=expiry,
                live_after_ts=ts,
            )
        )
        return out

    def _update_fh(self, state: Dict[str, Any], bar) -> None:
        o = float(bar.open)
        h = float(bar.high)
        l = float(bar.low)
        c = float(bar.close)
        if state.get("fh_open") is None:
            state["fh_open"] = o
            state["fh_high"] = h
            state["fh_low"] = l
        else:
            state["fh_high"] = max(float(state["fh_high"]), h)
            state["fh_low"] = min(float(state["fh_low"]), l)
        state["fh_close"] = c

    def _signal_time(self) -> time:
        end = self._time("fh_end")
        mins = int(self.config.get("bar_minutes") or 5)
        dt = datetime.combine(date(2000, 1, 1), end) - timedelta(minutes=mins)
        return dt.time()

    def _maybe_invalidate_pending(
        self, bar, context: StrategyContext, state: Dict[str, Any]
    ) -> Optional[StrategyActions]:
        """Cancel resting limit entry if planned SL is swept before fill."""
        trade_id = str(state.get("active_trade_id") or "")
        if not trade_id:
            return None
        trade = self._trade(trade_id, state)
        sl = _to_float(trade.get("stop_price"))
        if sl is None:
            return None
        side = "buy" if str(trade.get("candle_side") or "") == "long" else "sell"
        if bool(trade.get("fade")):
            side = "sell" if side == "buy" else "buy"
        # Prefer planned side from entry order if present
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and o.bracket_role == "entry":
                side = o.side
                break
        swept = (float(bar.low) <= sl) if side == "buy" else (float(bar.high) >= sl)
        if not swept:
            return None
        cancels = [
            CancelIntent(
                strategy_id=self.instance.strategy_id,
                broker_order_id=o.broker_order_id,
                reason="limit_sl_before_fill",
            )
            for o in context.strategy_open_orders
            if o.trade_id == trade_id
        ]
        trade["status"] = "cancelled"
        state["done"] = True
        state["entry_submitted"] = False
        state["phase"] = "limit_miss_sl_sweep"
        self._commit(state)
        return StrategyActions([], cancels, [], [], [])

    def _close_all(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(int(context.position_quantity))
        side = "sell" if context.position_quantity > 0 else "buy"
        trade_id = str(self._state().get("active_trade_id") or "eod")
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=trade_id,
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type="market_close",
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role="eod_close",
            live_after_ts=ts,
        )

    def _cancel_all(self, context: StrategyContext) -> List[CancelIntent]:
        return [
            CancelIntent(
                strategy_id=self.instance.strategy_id,
                broker_order_id=o.broker_order_id,
                reason="eod_cancel",
            )
            for o in context.strategy_open_orders
        ]

    def _cancel_reduce(self, context: StrategyContext, trade_id: str) -> List[CancelIntent]:
        out = []
        for o in context.strategy_open_orders:
            if o.trade_id == trade_id and o.reduce_only:
                out.append(
                    CancelIntent(
                        strategy_id=self.instance.strategy_id,
                        broker_order_id=o.broker_order_id,
                        reason="peer_filled",
                    )
                )
        return out

    def _fresh(self, session: str) -> Dict[str, Any]:
        accum = dict(getattr(self, "_pending_accum", {}) or {})
        prev_seq = int((self.state or {}).get("trade_seq") or 0)
        return {
            "session_date": session,
            "fh_open": None,
            "fh_high": None,
            "fh_low": None,
            "fh_close": None,
            "fh_bars": 0,
            "done": False,
            "entry_submitted": False,
            "current_leg_open": False,
            "active_trade_id": "",
            "active_direction": "",
            "phase": "new",
            "trade_seq": prev_seq,
            "trades": {},
            "level_accum": accum,
        }

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault("session_date", "")
        state.setdefault("trades", {})
        state.setdefault("trade_seq", 0)
        state.setdefault("level_accum", {})
        return state

    def _trade(self, trade_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        trades = state.setdefault("trades", {})
        if trade_id not in trades:
            trades[trade_id] = {}
        return trades[trade_id]

    def _new_trade_id(self, state: Dict[str, Any]) -> str:
        state["trade_seq"] = int(state.get("trade_seq") or 0) + 1
        return "%s_t%04d" % (self.instance.strategy_id, state["trade_seq"])

    def _commit(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.save_state()

    def _time(self, key: str) -> time:
        hh, mm = str(self.config[key]).split(":")
        return time(int(hh), int(mm))


def _parse_dt(ts: str) -> datetime:
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt
    try:
        from zoneinfo import ZoneInfo

        return dt.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    except Exception:
        import pytz

        return dt.astimezone(pytz.timezone("America/New_York")).replace(tzinfo=None)


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    return float(v)


def _session_expiry(session: str, cutoff: time) -> str:
    return "%sT16:00:00" % session


def _iso_week(session: str) -> Optional[Tuple[int, int]]:
    if not session:
        return None
    try:
        d = date.fromisoformat(session[:10])
    except ValueError:
        return None
    iso = d.isocalendar()
    return (int(iso[0]), int(iso[1]))
