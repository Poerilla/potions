"""15m structure-program + 1m SuperTrend limit entries (NQ RTH research).

Structure (15m RTH swings):
  Bullish: L → H → LL → HH  (key = LL; taken out if price trades below LL)
  Bearish: H → L → HH → LL  (key = HH; taken out if price trades above HH)

Lists: last 20 bullish + last 20 bearish (FIFO). No trading until both full.
Program: 2 bearish takeouts → BUY; 2 bullish takeouts → SELL (counters reset on flip).

Variants:
  core — ST-break signal; buy/sell limit at prior ST stop; SL = structure key.
  structure_sl — same ST-break signal; limit at structure key; stop = key ± risk_pts
                 (default 50). Pending may span sessions (max 3 RTH closes).
  structure_sl_scale — structure_sl entry with risk_pts (default 8), 4 contracts:
                 take 2 off at +1R, move stop to BE, runners target +3R (or ST flip / BE).
  structure_sl_scale_run — structure_sl entry, risk_pts (default 8), 15 contracts in 5-lots:
                 take 5 @ +22 pts, 5 @ +50, 5 @ +200; favourable ST-flip → stop to BE
                 (do not flatten); adverse ST-flip flattens. Path hits 25/100/200 logged.
  touch_st_align — watch structure key → touch+trade-through → wait ST flip aligned
                 with program bias → market entry on flip; SL = new ST trail; at +25
                 scale 5 and tighten SL to ±12; then 5 @ +50 / 5 @ +200; fav ST→BE.
  touch_st_align_fade20 — same, but if still through for 20 consecutive minutes,
                 fade the structure level (limit @ key, opposite side, stop = key ±25)
                 instead of waiting for the continuation ST flip.

All variants record MAE/MFE. Outputs under live/state/structure_program_st/<variant>/.

Usage:
  python -m live.structure_program_st_study --variant core --charts 20
  python -m live.structure_program_st_study --variant structure_sl --charts 50
  python -m live.structure_program_st_study --variant structure_sl_scale --risk-pts 8 --charts 50
  python -m live.structure_program_st_study --variant structure_sl_scale_run --risk-pts 8 --charts 50
  python -m live.structure_program_st_study --variant touch_st_align --start 2020-01-01
  python -m live.structure_program_st_study --variant touch_st_align_fade20 --start 2020-01-01
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "live" / "state" / "structure_program_st"

NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
LIST_SIZE = 20
TAKEOUTS_TO_FLIP = 2
SWING_LEFT = 2
SWING_RIGHT = 2
ATR_LEN = 14
ATR_MULT = 3.0
POINT_VALUE = 20.0  # NQ
FEE_RT = 3.0  # $1.50/side × 1 contract
DEFAULT_RISK_PTS = 50.0
STRUCTURE_SL_PENDING_MAX_CLOSES = 3
SCALE_ENTRY_QTY = 4
SCALE_OFF_QTY = 2
SCALE_RUNNER_QTY = 2
SCALE_R_MULT = 1.0
RUNNER_R_MULT = 3.0
# structure_sl_scale_run — absolute-pt ladder, 5-contract batches
RUN_ENTRY_QTY = 15
RUN_BATCH_QTY = 5
RUN_TP1_PTS = 22.0
RUN_TP2_PTS = 50.0
RUN_TP3_PTS = 200.0
RUN_HIT_THRESHOLDS = (25.0, 100.0, 200.0)
FEE_PER_CONTRACT_RT = 3.0  # $1.50/side
STRUCTURE_SL_VARIANTS = {"structure_sl", "structure_sl_scale", "structure_sl_scale_run"}
TOUCH_ALIGN_VARIANT = "touch_st_align"
TOUCH_ALIGN_FADE20_VARIANT = "touch_st_align_fade20"
TOUCH_ALIGN_VARIANTS = {TOUCH_ALIGN_VARIANT, TOUCH_ALIGN_FADE20_VARIANT}
TOUCH_ALIGN_TP1_PTS = 25.0
TOUCH_ALIGN_TIGHT_SL = 12.0
TOUCH_ALIGN_FADE20_MIN = 20  # consecutive 1m bars still through before fade
RUN_VARIANTS = {"structure_sl_scale_run", TOUCH_ALIGN_VARIANT, TOUCH_ALIGN_FADE20_VARIANT}


@dataclass
class Structure:
    kind: str  # bull | bear
    formed_ts: pd.Timestamp
    p1: float
    p2: float
    p3: float  # LL (bull) or HH (bear) mid pivot of the 4
    p4: float  # confirming HH (bull) or LL (bear)
    key: float  # invalidate / SL level
    taken_out: bool = False
    taken_out_ts: Optional[pd.Timestamp] = None


@dataclass
class Trade:
    trade_id: int
    side: str
    program: str
    variant: str
    signal_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry: float
    limit_px: float
    stop: float
    exit_ts: pd.Timestamp
    exit: float
    exit_reason: str
    pnl_pts: float
    pnl_usd: float
    structure_key: float
    st_at_signal: float
    mae_pts: float
    mfe_pts: float
    risk_pts: float
    qty: float = 1.0
    scaled: bool = False
    scale_px: float = float("nan")
    runner_target: float = float("nan")
    hit_25: bool = False
    hit_100: bool = False
    hit_200: bool = False
    st_be_armed: bool = False


def rth_slice(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(NY)
    else:
        out.index = out.index.tz_convert(NY)
    t = out.index.time
    return out[(t >= RTH_OPEN) & (t < RTH_CLOSE)]


def to_15m(rth_1m: pd.DataFrame) -> pd.DataFrame:
    if rth_1m.empty:
        return rth_1m
    ohlc = rth_1m.resample("15min", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum") if "volume" in rth_1m.columns else ("close", "count"),
    )
    return ohlc.dropna(subset=["open", "high", "low", "close"])


def confirm_swings(
    bars_15: pd.DataFrame,
    left: int = SWING_LEFT,
    right: int = SWING_RIGHT,
) -> List[Tuple[pd.Timestamp, str, float, int]]:
    """Return newly confirmable swings ending at each bar; causal at i+right."""
    if len(bars_15) < left + right + 1:
        return []
    highs = bars_15["high"].to_numpy(dtype=float)
    lows = bars_15["low"].to_numpy(dtype=float)
    idx = list(bars_15.index)
    out: List[Tuple[pd.Timestamp, str, float, int]] = []
    for i in range(left, len(bars_15) - right):
        h = highs[i]
        l = lows[i]
        is_sh = all(h > highs[i - k] for k in range(1, left + 1)) and all(
            h >= highs[i + k] for k in range(1, right + 1)
        )
        is_sl = all(l < lows[i - k] for k in range(1, left + 1)) and all(
            l <= lows[i + k] for k in range(1, right + 1)
        )
        # prefer the extreme that is more decisive if both (rare)
        if is_sh and is_sl:
            if (h - lows[i]) >= (highs[i] - l):
                is_sl = False
            else:
                is_sh = False
        if is_sh:
            out.append((idx[i + right], "H", float(h), i))
        elif is_sl:
            out.append((idx[i + right], "L", float(l), i))
    return out


def try_form_structures(
    swings: Sequence[Tuple[pd.Timestamp, str, float, int]],
) -> List[Structure]:
    """Scan trailing swing stream for new L-H-LL-HH / H-L-HH-LL completions."""
    formed: List[Structure] = []
    if len(swings) < 4:
        return formed
    # only check windows that end at the newest swing
    w = swings[-4:]
    kinds = [s[1] for s in w]
    px = [s[2] for s in w]
    ts = w[-1][0]
    if kinds == ["L", "H", "L", "H"] and px[2] < px[0] and px[3] > px[1]:
        formed.append(
            Structure(
                kind="bull",
                formed_ts=ts,
                p1=px[0],
                p2=px[1],
                p3=px[2],
                p4=px[3],
                key=px[2],
            )
        )
    if kinds == ["H", "L", "H", "L"] and px[2] > px[0] and px[3] < px[1]:
        formed.append(
            Structure(
                kind="bear",
                formed_ts=ts,
                p1=px[0],
                p2=px[1],
                p3=px[2],
                p4=px[3],
                key=px[2],
            )
        )
    return formed


class StructureProgramEngine:
    def __init__(self, list_size: int = LIST_SIZE, takeouts: int = TAKEOUTS_TO_FLIP):
        self.bull: Deque[Structure] = deque(maxlen=list_size)
        self.bear: Deque[Structure] = deque(maxlen=list_size)
        self.swings: List[Tuple[pd.Timestamp, str, float, int]] = []
        self.program: Optional[str] = None  # buy | sell
        self.bear_takeouts = 0
        self.bull_takeouts = 0
        self.takeouts_needed = takeouts
        self.list_size = list_size
        self._seen_structure_keys = set()

    @property
    def ready(self) -> bool:
        return len(self.bull) >= self.list_size and len(self.bear) >= self.list_size

    def ingest_day_15m(self, bars_15: pd.DataFrame) -> List[Structure]:
        """Walk 15m bars in order: confirm swings at bar i, then apply takeouts at i."""
        new_structs: List[Structure] = []
        if bars_15.empty:
            return new_structs
        # Map confirm_ts -> swing payload for this day
        day_swings = confirm_swings(bars_15)
        by_confirm: Dict[pd.Timestamp, List[Tuple[pd.Timestamp, str, float, int]]] = {}
        for sw in day_swings:
            by_confirm.setdefault(sw[0], []).append(sw)

        for ts, row in bars_15.iterrows():
            for sw in by_confirm.get(ts, []):
                if self.swings and self.swings[-1][1] == sw[1]:
                    prev = self.swings[-1]
                    if sw[1] == "H" and sw[2] >= prev[2]:
                        self.swings[-1] = sw
                    elif sw[1] == "L" and sw[2] <= prev[2]:
                        self.swings[-1] = sw
                    else:
                        continue
                else:
                    self.swings.append(sw)
                for st in try_form_structures(self.swings):
                    sig = (st.kind, round(st.key, 4), round(st.p4, 4), str(st.formed_ts))
                    if sig in self._seen_structure_keys:
                        continue
                    self._seen_structure_keys.add(sig)
                    if st.kind == "bull":
                        self.bull.append(st)
                    else:
                        self.bear.append(st)
                    new_structs.append(st)
            self._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
        return new_structs

    def _apply_takeouts_bar(self, ts: pd.Timestamp, hi: float, lo: float) -> None:
        for st in self.bear:
            if st.taken_out:
                continue
            if hi > st.key:
                st.taken_out = True
                st.taken_out_ts = ts
                self.bear_takeouts += 1
                if self.bear_takeouts >= self.takeouts_needed:
                    self.program = "buy"
                    self.bear_takeouts = 0
                    self.bull_takeouts = 0
        for st in self.bull:
            if st.taken_out:
                continue
            if lo < st.key:
                st.taken_out = True
                st.taken_out_ts = ts
                self.bull_takeouts += 1
                if self.bull_takeouts >= self.takeouts_needed:
                    self.program = "sell"
                    self.bear_takeouts = 0
                    self.bull_takeouts = 0

    def latest_key(self, kind: str) -> Optional[float]:
        dq = self.bull if kind == "bull" else self.bear
        if not dq:
            return None
        return float(dq[-1].key)

    def latest(self, kind: str) -> Optional[Structure]:
        dq = self.bull if kind == "bull" else self.bear
        if not dq:
            return None
        return dq[-1]


def simulate_day_entries(
    day_1m: pd.DataFrame,
    engine: StructureProgramEngine,
    *,
    pending: Optional[dict],
    position: Optional[dict],
    next_trade_id: int,
    warmup_1m: Optional[pd.DataFrame] = None,
    variant: str = "core",
    risk_pts: float = DEFAULT_RISK_PTS,
) -> Tuple[List[Trade], Optional[dict], Optional[dict], int]:
    """Process one RTH 1m session for ST signals / fills / exits."""
    trades: List[Trade] = []
    if day_1m.empty:
        return trades, pending, position, next_trade_id
    if (not engine.ready or engine.program is None) and position is None and pending is None:
        return trades, pending, position, next_trade_id

    # Warm ST with prior RTH bars so overnight positions see a continuous trail.
    if warmup_1m is not None and not warmup_1m.empty:
        tape = pd.concat([warmup_1m, day_1m])
        tape = tape[~tape.index.duplicated(keep="last")].sort_index()
    else:
        tape = day_1m
    st_df = compute_supertrend(tape, atr_len=ATR_LEN, multiplier=ATR_MULT)
    day_start = day_1m.index[0]
    day_end = day_1m.index[-1]
    for i in range(len(st_df)):
        ts = st_df.index[i]
        if ts < day_start:
            continue  # warmup only
        row = st_df.iloc[i]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        st_px = row["supertrend"]
        trend = int(row["supertrend_trend"]) if not pd.isna(row["supertrend_trend"]) else 0
        if pd.isna(st_px):
            continue
        st_px = float(st_px)

        # manage open position first
        if position is not None:
            closed = _manage_open_bar(
                position,
                ts=ts,
                h=h,
                l=l,
                c=c,
                st_px=st_px,
                trend=trend,
                variant=variant,
            )
            if closed is not None:
                trades.append(closed)
                position = None
                pending = None
                continue

        # --- touch_st_align(+fade20): watch key → through → ST flip or fade ---
        if variant in TOUCH_ALIGN_VARIANTS:
            fade20 = variant == TOUCH_ALIGN_FADE20_VARIANT

            def _open_touch_pos(
                *,
                side: str,
                prog: str,
                entry: float,
                stop0: float,
                structure_key: float,
                entry_kind: str,
            ) -> dict:
                sign = 1.0 if side == "long" else -1.0
                return {
                    "side": side,
                    "program": prog,
                    "signal_ts": ts,
                    "entry_ts": ts,
                    "entry": entry,
                    "limit_px": float(structure_key),
                    "stop": stop0,
                    "structure_key": float(structure_key),
                    "st_at_signal": float(st_px),
                    "risk_pts": abs(entry - stop0),
                    "trade_id": next_trade_id,
                    "mae_pts": 0.0,
                    "mfe_pts": 0.0,
                    "qty": float(RUN_ENTRY_QTY),
                    "qty_open": float(RUN_ENTRY_QTY),
                    "scaled": False,
                    "scaled2": False,
                    "realized_usd": 0.0,
                    "scale_px": float("nan"),
                    "scale_ts": None,
                    "tp1": entry + sign * TOUCH_ALIGN_TP1_PTS,
                    "tp2": entry + sign * RUN_TP2_PTS,
                    "tp_runner": entry + sign * RUN_TP3_PTS,
                    "exit_legs": [],
                    "hit_25": False,
                    "hit_100": False,
                    "hit_200": False,
                    "st_be_armed": False,
                    "tight_sl": TOUCH_ALIGN_TIGHT_SL,
                    "entry_kind": entry_kind,
                }

            if position is None and pending is not None:
                # fade limit fill (armed after 20m through)
                if str(pending.get("phase") or "") == "fade_limit":
                    side = str(pending["side"])
                    lim = float(pending["limit_px"])
                    stop_p = float(pending["stop"])
                    blown = (side == "long" and l <= stop_p) or (side == "short" and h >= stop_p)
                    filled = (side == "long" and l <= lim) or (side == "short" and h >= lim)
                    cancel_prog = engine.program is not None and (
                        # fade is opposite of original program; cancel if program flips to agree with fade
                        (pending.get("orig_side") == "long" and engine.program != "buy")
                        or (pending.get("orig_side") == "short" and engine.program != "sell")
                    )
                    if blown or cancel_prog or not engine.ready:
                        pending = None
                    elif filled:
                        position = _open_touch_pos(
                            side=side,
                            prog=str(pending.get("program") or ""),
                            entry=lim,
                            stop0=stop_p,
                            structure_key=float(pending["structure_key"]),
                            entry_kind="fade20",
                        )
                        next_trade_id += 1
                        pending = None
                else:
                    side = str(pending["side"])
                    cancel_prog = engine.program is not None and (
                        (side == "long" and engine.program != "buy")
                        or (side == "short" and engine.program != "sell")
                    )
                    if cancel_prog or not engine.ready or engine.program is None:
                        pending = None
                    else:
                        sk = float(pending["structure_key"])
                        phase = str(pending.get("phase") or "watch")
                        if phase == "watch" and not bool(pending.get("touched")):
                            fresh = engine.latest_key("bull" if side == "long" else "bear")
                            if fresh is not None:
                                sk = float(fresh)
                                pending["structure_key"] = sk
                                pending["limit_px"] = sk
                        still_through = False
                        if side == "long":
                            if l <= sk:
                                pending["touched"] = True
                            if l < sk:
                                pending["through"] = True
                            still_through = c < sk
                        else:
                            if h >= sk:
                                pending["touched"] = True
                            if h > sk:
                                pending["through"] = True
                            still_through = c > sk
                        if still_through:
                            pending["through_streak"] = int(pending.get("through_streak") or 0) + 1
                        else:
                            pending["through_streak"] = 0
                        if bool(pending.get("through")):
                            pending["phase"] = "wait_flip"
                            phase = "wait_flip"

                        # fade20: still through for N minutes → fade limit @ key
                        if (
                            fade20
                            and phase == "wait_flip"
                            and int(pending.get("through_streak") or 0) >= TOUCH_ALIGN_FADE20_MIN
                        ):
                            fade_side = "short" if side == "long" else "long"
                            # same risk size as first TP rung (±25 beyond the level)
                            fade_stop = (
                                sk + TOUCH_ALIGN_TP1_PTS
                                if fade_side == "short"
                                else sk - TOUCH_ALIGN_TP1_PTS
                            )
                            pending = {
                                "phase": "fade_limit",
                                "side": fade_side,
                                "orig_side": side,
                                "program": pending["program"],
                                "signal_ts": ts,
                                "limit_px": float(sk),
                                "stop": float(fade_stop),
                                "structure_key": float(sk),
                                "st_at_signal": float(st_px),
                                "risk_pts": TOUCH_ALIGN_TP1_PTS,
                                "rth_closes": int(pending.get("rth_closes") or 0),
                                "touched": True,
                                "through": True,
                                "through_streak": int(pending.get("through_streak") or 0),
                            }
                        elif phase == "wait_flip":
                            loc = st_df.index.get_loc(ts)
                            if not (
                                isinstance(loc, slice)
                                or isinstance(loc, np.ndarray)
                                or int(loc) < 1
                            ):
                                prev = st_df.iloc[int(loc) - 1]
                                prev_trend = (
                                    int(prev["supertrend_trend"])
                                    if not pd.isna(prev["supertrend_trend"])
                                    else 0
                                )
                                prev_st = prev["supertrend"]
                                flip = False
                                if not pd.isna(prev_st):
                                    prev_st = float(prev_st)
                                    if (
                                        side == "long"
                                        and prev_trend == -1
                                        and trend == 1
                                        and c > prev_st
                                    ):
                                        flip = True
                                    elif (
                                        side == "short"
                                        and prev_trend == 1
                                        and trend == -1
                                        and c < prev_st
                                    ):
                                        flip = True
                                if flip:
                                    entry = c
                                    stop0 = float(st_px)
                                    bad_stop = (side == "long" and stop0 >= entry) or (
                                        side == "short" and stop0 <= entry
                                    )
                                    if not bad_stop:
                                        position = _open_touch_pos(
                                            side=side,
                                            prog=str(pending["program"]),
                                            entry=entry,
                                            stop0=stop0,
                                            structure_key=float(pending["structure_key"]),
                                            entry_kind="cont_flip",
                                        )
                                        next_trade_id += 1
                                        pending = None

            if position is None and pending is not None and ts == day_end:
                pending["rth_closes"] = int(pending.get("rth_closes") or 0) + 1
                if pending["rth_closes"] >= STRUCTURE_SL_PENDING_MAX_CLOSES:
                    pending = None

            if position is None and pending is None and engine.ready and engine.program is not None:
                prog = engine.program
                if prog == "buy":
                    sk = engine.latest_key("bull")
                    side = "long"
                else:
                    sk = engine.latest_key("bear")
                    side = "short"
                if sk is not None:
                    pending = {
                        "phase": "watch",
                        "side": side,
                        "program": prog,
                        "signal_ts": ts,
                        "limit_px": float(sk),
                        "stop": float("nan"),
                        "structure_key": float(sk),
                        "st_at_signal": float(st_px),
                        "risk_pts": 0.0,
                        "rth_closes": 0,
                        "touched": False,
                        "through": False,
                        "through_streak": 0,
                    }
            continue

        # fill / manage pending limit
        if position is None and pending is not None:
            side = pending["side"]
            lim = float(pending["limit_px"])
            stop_p = float(pending["stop"])
            blown = (side == "long" and l <= stop_p) or (side == "short" and h >= stop_p)
            filled = (side == "long" and l <= lim) or (side == "short" and h >= lim)
            cancel_st = False
            if variant == "core":
                cancel_st = (side == "long" and trend != 1) or (side == "short" and trend != -1)
            cancel_prog = engine.program is not None and (
                (side == "long" and engine.program != "buy") or (side == "short" and engine.program != "sell")
            )
            if blown:
                pending = None
            elif filled:
                rp = float(pending.get("risk_pts") or risk_pts)
                scale_on = variant == "structure_sl_scale"
                run_on = variant in RUN_VARIANTS
                sign = 1.0 if side == "long" else -1.0
                if run_on:
                    qty0 = float(RUN_ENTRY_QTY)
                    tp1 = lim + sign * RUN_TP1_PTS
                    tp2 = lim + sign * RUN_TP2_PTS
                    tp_runner = lim + sign * RUN_TP3_PTS
                elif scale_on:
                    qty0 = float(SCALE_ENTRY_QTY)
                    tp1 = lim + sign * SCALE_R_MULT * rp
                    tp2 = float("nan")
                    tp_runner = lim + sign * RUNNER_R_MULT * rp
                else:
                    qty0 = 1.0
                    tp1 = tp2 = tp_runner = float("nan")
                position = {
                    **pending,
                    "entry_ts": ts,
                    "entry": lim,
                    "trade_id": next_trade_id,
                    "mae_pts": 0.0,
                    "mfe_pts": 0.0,
                    "qty": qty0,
                    "qty_open": qty0,
                    "scaled": False,
                    "scaled2": False,
                    "realized_usd": 0.0,
                    "scale_px": float("nan"),
                    "scale_ts": None,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp_runner": tp_runner,
                    "exit_legs": [],
                    "hit_25": False,
                    "hit_100": False,
                    "hit_200": False,
                    "st_be_armed": False,
                }
                next_trade_id += 1
                pending = None
            elif cancel_st or cancel_prog:
                pending = None

        # pending expiry
        if position is None and pending is not None and ts == day_end:
            if variant == "core":
                pending = None
            else:
                pending["rth_closes"] = int(pending.get("rth_closes") or 0) + 1
                if pending["rth_closes"] >= STRUCTURE_SL_PENDING_MAX_CLOSES:
                    pending = None

        # arm new signal (flat, ready, RTH)
        if position is None and pending is None and engine.ready and engine.program is not None:
            loc = st_df.index.get_loc(ts)
            if isinstance(loc, slice) or (isinstance(loc, np.ndarray)) or int(loc) < 1:
                continue
            prev = st_df.iloc[int(loc) - 1]
            prev_trend = int(prev["supertrend_trend"]) if not pd.isna(prev["supertrend_trend"]) else 0
            prev_st = prev["supertrend"]
            if pd.isna(prev_st):
                continue
            prev_st = float(prev_st)
            prog = engine.program
            if prog == "buy" and prev_trend == -1 and trend == 1 and c > prev_st:
                sk = engine.latest_key("bull")
                if sk is None or not (sk < prev_st):
                    continue
                pending = _arm_pending(
                    variant=variant,
                    side="long",
                    prog=prog,
                    ts=ts,
                    prev_st=prev_st,
                    sk=sk,
                    risk_pts=risk_pts,
                )
            elif prog == "sell" and prev_trend == 1 and trend == -1 and c < prev_st:
                sk = engine.latest_key("bear")
                if sk is None or not (sk > prev_st):
                    continue
                pending = _arm_pending(
                    variant=variant,
                    side="short",
                    prog=prog,
                    ts=ts,
                    prev_st=prev_st,
                    sk=sk,
                    risk_pts=risk_pts,
                )
    return trades, pending, position, next_trade_id


def _arm_pending(
    *,
    variant: str,
    side: str,
    prog: str,
    ts: pd.Timestamp,
    prev_st: float,
    sk: float,
    risk_pts: float,
) -> dict:
    if variant == "core":
        return {
            "side": side,
            "program": prog,
            "signal_ts": ts,
            "limit_px": prev_st,
            "stop": sk,
            "structure_key": sk,
            "st_at_signal": prev_st,
            "risk_pts": abs(prev_st - sk),
            "rth_closes": 0,
        }
    # structure_sl (+ scale): limit at structure key, fixed risk beyond
    stop = sk - risk_pts if side == "long" else sk + risk_pts
    return {
        "side": side,
        "program": prog,
        "signal_ts": ts,
        "limit_px": sk,
        "stop": stop,
        "structure_key": sk,
        "st_at_signal": prev_st,
        "risk_pts": risk_pts,
        "rth_closes": 0,
    }


def _manage_open_bar(
    position: dict,
    *,
    ts: pd.Timestamp,
    h: float,
    l: float,
    c: float,
    st_px: float,
    trend: int,
    variant: str,
) -> Optional[Trade]:
    """Update MAE/MFE; apply scale/runner/stop/ST. Return Trade when fully flat."""
    side = position["side"]
    stop = float(position["stop"])
    entry = float(position["entry"])
    sign = 1.0 if side == "long" else -1.0
    if side == "long":
        position["mae_pts"] = max(float(position.get("mae_pts") or 0.0), entry - l)
        position["mfe_pts"] = max(float(position.get("mfe_pts") or 0.0), h - entry)
    else:
        position["mae_pts"] = max(float(position.get("mae_pts") or 0.0), h - entry)
        position["mfe_pts"] = max(float(position.get("mfe_pts") or 0.0), entry - l)

    mfe = float(position["mfe_pts"])
    if mfe >= 25.0:
        position["hit_25"] = True
    if mfe >= 100.0:
        position["hit_100"] = True
    if mfe >= 200.0:
        position["hit_200"] = True

    qty_open = float(position.get("qty_open") or position.get("qty") or 1.0)
    scale_on = variant == "structure_sl_scale"
    run_on = variant in RUN_VARIANTS
    touch_align = variant in TOUCH_ALIGN_VARIANTS
    managed = scale_on or run_on

    def _realize(qty: float, px: float, tag: str) -> None:
        pnl_pts = sign * (px - entry)
        usd = pnl_pts * POINT_VALUE * qty - FEE_PER_CONTRACT_RT * qty
        position["realized_usd"] = float(position.get("realized_usd") or 0.0) + usd
        legs = list(position.get("exit_legs") or [])
        legs.append("%s@%.2f x%.0f" % (tag, px, qty))
        position["exit_legs"] = legs
        position["qty_open"] = float(position["qty_open"]) - qty

    def _compose_reason(final_tag: str) -> str:
        tags = []
        for leg in position.get("exit_legs") or []:
            tags.append(str(leg).split("@", 1)[0])
        # de-dupe consecutive
        out: List[str] = []
        for t in tags:
            if not out or out[-1] != t:
                out.append(t)
        if not out:
            return final_tag
        if out[-1] != final_tag:
            out.append(final_tag)
        return "+".join(out)

    def _be_armed() -> bool:
        return bool(position.get("scaled") or position.get("st_be_armed"))

    # 1) stop (incl. BE after scale / fav ST) — pessimistic vs targets same bar
    hit_stop = (side == "long" and l <= stop) or (side == "short" and h >= stop)
    if hit_stop:
        if managed and _be_armed():
            tag = "be_stop"
        elif touch_align and position.get("scaled"):
            tag = "tight_stop"
        elif variant in STRUCTURE_SL_VARIANTS or touch_align:
            tag = "risk_stop"
        else:
            tag = "structure_stop"
        _realize(qty_open, stop, tag)
        return _finalize_trade(position, ts=ts, exit_px=stop, reason=_compose_reason(tag), variant=variant)

    # 2a) classic scale: 2 @ +1R then BE
    if scale_on and not position.get("scaled"):
        tp1 = float(position["tp1"])
        hit_tp1 = (side == "long" and h >= tp1) or (side == "short" and l <= tp1)
        if hit_tp1:
            _realize(float(SCALE_OFF_QTY), tp1, "scale_1r")
            position["scaled"] = True
            position["scale_px"] = tp1
            position["scale_ts"] = ts
            position["stop"] = entry  # breakeven
            qty_open = float(position["qty_open"])
            be = entry
            hit_be = (side == "long" and l <= be) or (side == "short" and h >= be)
            if hit_be and qty_open > 0:
                _realize(qty_open, be, "be_stop")
                return _finalize_trade(
                    position, ts=ts, exit_px=be, reason="scale_1r+be_stop", variant=variant
                )

    # 2b) run ladder: scale_run 5@22→BE; touch_st_align 5@25→±12 SL; then 5@50 / 5@200
    if run_on and float(position.get("qty_open") or 0) > 0:
        if not position.get("scaled"):
            tp1 = float(position["tp1"])
            hit_tp1 = (side == "long" and h >= tp1) or (side == "short" and l <= tp1)
            if hit_tp1:
                tag1 = "scale_25" if touch_align else "scale_22"
                _realize(float(RUN_BATCH_QTY), tp1, tag1)
                position["scaled"] = True
                position["scale_px"] = tp1
                position["scale_ts"] = ts
                if touch_align:
                    tight = float(position.get("tight_sl") or TOUCH_ALIGN_TIGHT_SL)
                    position["stop"] = entry - tight if side == "long" else entry + tight
                    position["risk_pts"] = tight
                else:
                    position["stop"] = entry
                qty_open = float(position["qty_open"])
                new_stop = float(position["stop"])
                hit_new = (side == "long" and l <= new_stop) or (side == "short" and h >= new_stop)
                if hit_new and qty_open > 0:
                    tag = "tight_stop" if touch_align else "be_stop"
                    _realize(qty_open, new_stop, tag)
                    return _finalize_trade(
                        position, ts=ts, exit_px=new_stop, reason=_compose_reason(tag), variant=variant
                    )
        if position.get("scaled") and not position.get("scaled2") and float(position.get("qty_open") or 0) > 0:
            tp2 = float(position["tp2"])
            hit_tp2 = (side == "long" and h >= tp2) or (side == "short" and l <= tp2)
            if hit_tp2:
                q = min(float(RUN_BATCH_QTY), float(position["qty_open"]))
                _realize(q, tp2, "scale_50")
                position["scaled2"] = True
        if position.get("scaled2") and float(position.get("qty_open") or 0) > 0:
            tpr = float(position["tp_runner"])
            hit_runner = (side == "long" and h >= tpr) or (side == "short" and l <= tpr)
            if hit_runner:
                q = float(position["qty_open"])
                _realize(q, tpr, "runner_200")
                return _finalize_trade(
                    position, ts=ts, exit_px=tpr, reason=_compose_reason("runner_200"), variant=variant
                )

    # 3) classic runner +3R
    if scale_on and position.get("scaled") and float(position.get("qty_open") or 0) > 0:
        tpr = float(position["tp_runner"])
        hit_runner = (side == "long" and h >= tpr) or (side == "short" and l <= tpr)
        if hit_runner:
            _realize(float(position["qty_open"]), tpr, "runner_3r")
            return _finalize_trade(position, ts=ts, exit_px=tpr, reason="scale_1r+runner_3r", variant=variant)

    # 4) ST flip
    st_exit = (side == "long" and trend == -1 and c < st_px) or (
        side == "short" and trend == 1 and c > st_px
    )
    if st_exit and float(position.get("qty_open") or 0) > 0:
        favourable = (side == "long" and c > entry) or (side == "short" and c < entry)
        if run_on and favourable:
            # Hold: trail protection to BE instead of flattening winners.
            position["stop"] = entry
            position["st_be_armed"] = True
            return None
        q = float(position["qty_open"])
        _realize(q, c, "st_flip")
        if scale_on:
            reason = "scale_1r+st_flip" if position.get("scaled") else "st_flip"
        else:
            reason = _compose_reason("st_flip")
        return _finalize_trade(position, ts=ts, exit_px=c, reason=reason, variant=variant)
    return None


def _finalize_trade(
    position: dict,
    *,
    ts: pd.Timestamp,
    exit_px: float,
    reason: str,
    variant: str,
) -> Trade:
    entry = float(position["entry"])
    qty = float(position.get("qty") or 1.0)
    pnl_usd = float(position.get("realized_usd") or 0.0)
    # pts on a 1-contract equivalent for ranking (total $ / (point_value * entry qty))
    pnl_pts = pnl_usd / (POINT_VALUE * qty) if qty else 0.0
    # re-express as total contract-points for clarity in summary
    pnl_pts_total = pnl_usd / POINT_VALUE if POINT_VALUE else 0.0
    return Trade(
        trade_id=int(position["trade_id"]),
        side=str(position["side"]),
        program=str(position["program"]),
        variant=variant,
        signal_ts=position["signal_ts"],
        entry_ts=position["entry_ts"],
        entry=entry,
        limit_px=float(position["limit_px"]),
        stop=float(position["stop"]),
        exit_ts=ts,
        exit=float(exit_px),
        exit_reason=reason,
        pnl_pts=round(pnl_pts_total, 4),
        pnl_usd=round(pnl_usd, 2),
        structure_key=float(position["structure_key"]),
        st_at_signal=float(position["st_at_signal"]),
        mae_pts=round(float(position.get("mae_pts") or 0.0), 4),
        mfe_pts=round(float(position.get("mfe_pts") or 0.0), 4),
        risk_pts=float(position.get("risk_pts") or 0.0),
        qty=qty,
        scaled=bool(position.get("scaled")),
        scale_px=float(position["scale_px"]) if position.get("scaled") else float("nan"),
        runner_target=float(position.get("tp_runner") or float("nan")),
        hit_25=bool(position.get("hit_25")),
        hit_100=bool(position.get("hit_100")),
        hit_200=bool(position.get("hit_200")),
        st_be_armed=bool(position.get("st_be_armed")),
    )


def run_study(
    *,
    variant: str = "core",
    start: Optional[date] = None,
    end: Optional[date] = None,
    max_days: Optional[int] = None,
    risk_pts: float = DEFAULT_RISK_PTS,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
) -> pd.DataFrame:
    out_dir = OUT_ROOT / variant
    cfg = MARKETS["nq"]
    if gby is None:
        print("Loading NQ 1m…", flush=True)
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), "nq")
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]
    if max_days:
        days = days[:max_days]

    engine = StructureProgramEngine()
    pending = None
    position = None
    next_id = 1
    all_trades: List[Trade] = []
    ready_day: Optional[date] = None
    n_structs_bull = n_structs_bear = 0
    recent_rth: List[pd.DataFrame] = []

    print("Running variant=%s risk_pts=%.1f over %d days…" % (variant, risk_pts, len(days)), flush=True)
    for di, day in enumerate(days, 1):
        raw = gby.get(day)
        rth = rth_slice(raw)
        if rth.empty or len(rth) < 60:
            continue
        bars_15 = to_15m(rth)
        new_s = engine.ingest_day_15m(bars_15)
        n_structs_bull += sum(1 for s in new_s if s.kind == "bull")
        n_structs_bear += sum(1 for s in new_s if s.kind == "bear")
        if ready_day is None and engine.ready:
            ready_day = day
            print(
                "Lists full on %s (bull=%d bear=%d program=%s)"
                % (day, len(engine.bull), len(engine.bear), engine.program),
                flush=True,
            )

        warmup = pd.concat(recent_rth) if recent_rth else None
        day_trades, pending, position, next_id = simulate_day_entries(
            rth,
            engine,
            pending=pending,
            position=position,
            next_trade_id=next_id,
            warmup_1m=warmup,
            variant=variant,
            risk_pts=risk_pts,
        )
        all_trades.extend(day_trades)
        recent_rth.append(rth)
        recent_rth = recent_rth[-3:]
        if di % 250 == 0:
            print(
                "  %d/%d days | structs bull/bear formed %d/%d | trades %d | program=%s"
                % (di, len(days), n_structs_bull, n_structs_bear, len(all_trades), engine.program),
                flush=True,
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(t) for t in all_trades])
    if not df.empty:
        df.to_csv(out_dir / "trades.csv", index=False)
        _write_mae_profile(df, out_dir)
        if variant in RUN_VARIANTS:
            _write_extension_hits(df, out_dir)
    meta = {
        "variant": variant,
        "risk_pts": risk_pts,
        "ready_day": str(ready_day),
        "n_days": len(days),
        "n_trades": len(df),
        "structs_bull_formed": n_structs_bull,
        "structs_bear_formed": n_structs_bear,
        "final_program": engine.program,
        "bull_list": len(engine.bull),
        "bear_list": len(engine.bear),
    }
    pd.Series(meta).to_csv(out_dir / "meta.csv")
    _write_summary(df, meta, out_dir)
    print("Wrote %d trades → %s" % (len(df), out_dir), flush=True)
    return df


def _write_mae_profile(df: pd.DataFrame, out_dir: Path) -> None:
    """MAE / MFE tables + bucket histogram."""
    rows = []
    for label, sub in [("all", df), ("winners", df[df.pnl_usd > 0]), ("losers", df[df.pnl_usd <= 0])]:
        if sub.empty:
            continue
        mae = sub["mae_pts"]
        mfe = sub["mfe_pts"]
        rows.append(
            {
                "cohort": label,
                "n": len(sub),
                "mae_mean": round(float(mae.mean()), 2),
                "mae_median": round(float(mae.median()), 2),
                "mae_p75": round(float(mae.quantile(0.75)), 2),
                "mae_p90": round(float(mae.quantile(0.90)), 2),
                "mae_p95": round(float(mae.quantile(0.95)), 2),
                "mae_max": round(float(mae.max()), 2),
                "mfe_mean": round(float(mfe.mean()), 2),
                "mfe_median": round(float(mfe.median()), 2),
                "mfe_p90": round(float(mfe.quantile(0.90)), 2),
                "pct_mae_le_10": round(100.0 * (mae <= 10).mean(), 1),
                "pct_mae_le_25": round(100.0 * (mae <= 25).mean(), 1),
                "pct_mae_le_50": round(100.0 * (mae <= 50).mean(), 1),
                "pct_mae_le_75": round(100.0 * (mae <= 75).mean(), 1),
            }
        )
    prof = pd.DataFrame(rows)
    prof.to_csv(out_dir / "mae_profile.csv", index=False)

    bins = [0, 5, 10, 15, 25, 35, 50, 75, 100, 150, 250, 10_000]
    labels = ["0-5", "5-10", "10-15", "15-25", "25-35", "35-50", "50-75", "75-100", "100-150", "150-250", "250+"]
    hist = pd.cut(df["mae_pts"], bins=bins, labels=labels, include_lowest=True)
    hist_df = hist.value_counts().reindex(labels).fillna(0).astype(int).rename("n").reset_index()
    hist_df.columns = ["mae_bucket", "n"]
    hist_df["pct"] = (100.0 * hist_df["n"] / max(len(df), 1)).round(1)
    hist_df.to_csv(out_dir / "mae_histogram.csv", index=False)


def _write_extension_hits(df: pd.DataFrame, out_dir: Path) -> None:
    """How often trades reach 25 / 100 / 200 pts of MFE (path touch while open).

    hit_* flags update from running MFE, so a later BE/risk death still counts if
    the threshold was touched first. ``*_no_risk_mae`` requires MAE never reached
    the initial risk distance (never tagged a full risk-stop MAE).
    """
    out_rows = []
    cohorts = [
        ("all", df),
        ("winners", df[df.pnl_usd > 0]),
        ("losers", df[df.pnl_usd <= 0]),
    ]
    if "st_be_armed" in df.columns:
        cohorts.append(("st_be_armed", df[df["st_be_armed"] == True]))
    for label, sub in cohorts:
        if sub.empty:
            continue
        risk = sub["risk_pts"].astype(float)
        clean = sub["mae_pts"].astype(float) < risk
        out_rows.append(
            {
                "cohort": label,
                "n": len(sub),
                "pct_hit_25": round(100.0 * sub["hit_25"].astype(bool).mean(), 1),
                "pct_hit_100": round(100.0 * sub["hit_100"].astype(bool).mean(), 1),
                "pct_hit_200": round(100.0 * sub["hit_200"].astype(bool).mean(), 1),
                "pct_hit_25_no_risk_mae": round(100.0 * (sub["hit_25"].astype(bool) & clean).mean(), 1),
                "pct_hit_100_no_risk_mae": round(100.0 * (sub["hit_100"].astype(bool) & clean).mean(), 1),
                "pct_hit_200_no_risk_mae": round(100.0 * (sub["hit_200"].astype(bool) & clean).mean(), 1),
                "mfe_mean": round(float(sub["mfe_pts"].mean()), 2),
                "mfe_median": round(float(sub["mfe_pts"].median()), 2),
                "mfe_p90": round(float(sub["mfe_pts"].quantile(0.90)), 2),
                "mfe_max": round(float(sub["mfe_pts"].max()), 2),
                "st_be_share_pct": round(100.0 * sub["st_be_armed"].astype(bool).mean(), 1)
                if "st_be_armed" in sub.columns
                else 0.0,
            }
        )
    pd.DataFrame(out_rows).to_csv(out_dir / "extension_hits.csv", index=False)


def _write_summary(df: pd.DataFrame, meta: dict, out_dir: Path) -> None:
    variant = str(meta.get("variant") or "core")
    if variant == "structure_sl_scale_run":
        blurb = (
            "ST-break → limit @ structure; **risk %.0f pts**; **15 contracts** — "
            "5 @ +%.0f pts, 5 @ +%.0f, 5 @ +%.0f; favourable ST-flip → BE (hold), "
            "adverse ST-flip flattens. Pending up to %d RTH closes. Extension hits profiled."
            % (
                float(meta.get("risk_pts") or 8.0),
                RUN_TP1_PTS,
                RUN_TP2_PTS,
                RUN_TP3_PTS,
                STRUCTURE_SL_PENDING_MAX_CLOSES,
            )
        )
    elif variant == TOUCH_ALIGN_VARIANT:
        blurb = (
            "Structure key touch+trade-through → wait ST flip aligned with program → "
            "**market entry** on flip; initial SL = new ST trail; **15 contracts** — "
            "5 @ +%.0f (then SL→±%.0f), 5 @ +%.0f, 5 @ +%.0f; fav ST→BE. Pending ≤%d RTH closes."
            % (
                TOUCH_ALIGN_TP1_PTS,
                TOUCH_ALIGN_TIGHT_SL,
                RUN_TP2_PTS,
                RUN_TP3_PTS,
                STRUCTURE_SL_PENDING_MAX_CLOSES,
            )
        )
    elif variant == TOUCH_ALIGN_FADE20_VARIANT:
        blurb = (
            "Same as touch_st_align, but if still through for **%d** consecutive minutes → "
            "**fade limit @ structure key** (opposite side, stop = key ±%.0f) instead of "
            "waiting for continuation ST flip. Ladder 5@+%.0f/±%.0f then +%.0f/+%.0f; fav ST→BE."
            % (
                TOUCH_ALIGN_FADE20_MIN,
                TOUCH_ALIGN_TP1_PTS,
                TOUCH_ALIGN_TP1_PTS,
                TOUCH_ALIGN_TIGHT_SL,
                RUN_TP2_PTS,
                RUN_TP3_PTS,
            )
        )
    elif variant == "structure_sl_scale":
        blurb = (
            "ST-break → limit @ structure; **risk %.0f pts**; **4 contracts** — "
            "scale 2 @ +1R (%.0f pts), stop → BE, runners 2 @ +3R (%.0f pts) or ST flip. "
            "Pending up to %d RTH closes. MAE/MFE profiled."
            % (
                float(meta.get("risk_pts") or 8.0),
                float(meta.get("risk_pts") or 8.0) * SCALE_R_MULT,
                float(meta.get("risk_pts") or 8.0) * RUNNER_R_MULT,
                STRUCTURE_SL_PENDING_MAX_CLOSES,
            )
        )
    elif variant == "structure_sl":
        blurb = (
            "ST-break signal (1m ATR SuperTrend 14×3); **limit at structure key**; "
            "stop = key ± %.0f pts. Pending may span up to %d RTH closes. MAE/MFE profiled."
            % (float(meta.get("risk_pts") or DEFAULT_RISK_PTS), STRUCTURE_SL_PENDING_MAX_CLOSES)
        )
    else:
        blurb = (
            "ST-break signal; **limit at prior ST stop**; SL at structure key. "
            "Entries RTH only; exit on structure stop or ST flip."
        )
    lines = [
        "# Structure-program ST — **%s** (NQ RTH)" % variant,
        "",
        "15m swing structures (L-H-LL-HH / H-L-HH-LL), last-20 bull & bear lists, "
        "program flips after 2 opposing takeouts. " + blurb,
        "",
        "## Meta",
        "",
    ]
    for k, v in meta.items():
        lines.append("- **%s:** %s" % (k, v))
    lines.append("")
    if df is None or df.empty:
        lines.append("No trades.")
        (out_dir / "SUMMARY.md").write_text("\n".join(lines))
        return
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]
    pf = wins.pnl_usd.sum() / abs(losses.pnl_usd.sum()) if len(losses) and losses.pnl_usd.sum() != 0 else float("inf")
    lines += [
        "## Results",
        "",
        "| metric | value |",
        "|---|---|",
        "| trades | %d |" % len(df),
        "| net $ | %.0f |" % df.pnl_usd.sum(),
        "| win%% | %.1f |" % (100.0 * (df.pnl_usd > 0).mean()),
        "| PF | %.3f |" % pf,
        "| avg $/trade | %.1f |" % df.pnl_usd.mean(),
        "| long / short | %d / %d |" % ((df.side == "long").sum(), (df.side == "short").sum()),
        "| MAE mean / median | %.1f / %.1f |" % (df.mae_pts.mean(), df.mae_pts.median()),
        "| MFE mean / median | %.1f / %.1f |" % (df.mfe_pts.mean(), df.mfe_pts.median()),
    ]
    if "scaled" in df.columns and df["scaled"].fillna(False).any():
        lines.append(
            "| scaled campaigns | %d (%.0f%%) |"
            % (int(df.scaled.sum()), 100.0 * df.scaled.mean())
        )
    lines += [
        "",
        "### By exit reason",
        "",
        _md_agg(df.groupby("exit_reason").pnl_usd.agg(["count", "sum", "mean"])),
        "",
        "### By year",
        "",
    ]
    yr = df.copy()
    yr["year"] = pd.to_datetime(yr["entry_ts"], utc=True).dt.year
    lines.append(_md_agg(yr.groupby("year").pnl_usd.agg(["count", "sum", "mean"])))
    lines.append("")
    mae_path = out_dir / "mae_profile.csv"
    if mae_path.exists():
        lines.append("### MAE / MFE profile")
        lines.append("")
        lines.append(_md_agg(pd.read_csv(mae_path).set_index("cohort")))
        lines.append("")
        hist_path = out_dir / "mae_histogram.csv"
        if hist_path.exists():
            lines.append("### MAE histogram (pts)")
            lines.append("")
            lines.append(_md_agg(pd.read_csv(hist_path).set_index("mae_bucket")))
            lines.append("")
    ext_path = out_dir / "extension_hits.csv"
    if ext_path.exists():
        lines.append("### Extension hits (25 / 100 / 200 pts MFE while open)")
        lines.append("")
        lines.append(
            "Path touch rates. `*_no_risk_mae` = also never saw MAE ≥ risk "
            "(did not tag a full risk-stop drawdown before/while extending)."
        )
        lines.append("")
        lines.append(_md_agg(pd.read_csv(ext_path).set_index("cohort")))
        lines.append("")
        if "st_be_armed" in df.columns:
            n_be = int(df["st_be_armed"].astype(bool).sum())
            lines.append(
                "- Favourable ST→BE armed on **%d / %d** trades (%.0f%%)."
                % (n_be, len(df), 100.0 * n_be / max(len(df), 1))
            )
            lines.append("")
    (out_dir / "SUMMARY.md").write_text("\n".join(lines))


def _md_agg(frame: pd.DataFrame) -> str:
    cols = list(frame.reset_index().columns)
    rows = [frame.reset_index()]
    df = rows[0]
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def chart_trades(
    df: pd.DataFrame,
    gby: Dict[date, pd.DataFrame],
    out_dir: Path,
    n: int = 20,
    variant: str = "core",
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    charts = out_dir / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    for old in charts.glob("*.png"):
        old.unlink()
    if df.empty:
        return
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]
    pick = []
    for src in (wins, losses):
        if src.empty:
            continue
        step = max(1, len(src) // max(1, n // 2))
        pick.append(src.iloc[::step].head(n // 2 + 1))
    sample = pd.concat(pick).drop_duplicates(subset=["trade_id"]).sort_values("entry_ts").head(n)
    if len(sample) < n:
        sample = df.iloc[:: max(1, len(df) // n)].head(n)

    for _, t in sample.iterrows():
        entry_ts = pd.Timestamp(t.entry_ts)
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize(NY)
        else:
            entry_ts = entry_ts.tz_convert(NY)
        d0 = entry_ts.date()
        all_days = sorted(gby)
        if d0 not in all_days:
            all_days_arr = [d for d in all_days if abs((d - d0).days) < 10]
            if not all_days_arr:
                continue
            d0 = min(all_days_arr, key=lambda d: abs((d - d0).days))
        di = all_days.index(d0)
        window_days = all_days[max(0, di - 1) : min(len(all_days), di + 2)]
        frames_15 = []
        st_pieces = []
        for d in window_days:
            rth = rth_slice(gby[d])
            if rth.empty:
                continue
            b15 = to_15m(rth)
            frames_15.append(b15)
            st1 = compute_supertrend(rth, atr_len=ATR_LEN, multiplier=ATR_MULT)
            st_on_15 = st1[["supertrend", "supertrend_trend"]].reindex(b15.index, method="ffill")
            st_pieces.append(st_on_15)
        if not frames_15:
            continue
        bars = pd.concat(frames_15)
        st_ov = pd.concat(st_pieces)

        fig, ax = plt.subplots(figsize=(16, 8))
        x = np.arange(len(bars))
        up = bars["close"] >= bars["open"]
        ax.vlines(x, bars["low"], bars["high"], color="#888", lw=0.6, zorder=1)
        ax.vlines(x[up], bars["open"][up], bars["close"][up], color="#1a9850", lw=2.0, zorder=2)
        ax.vlines(x[~up], bars["close"][~up], bars["open"][~up], color="#d73027", lw=2.0, zorder=2)

        bull = st_ov["supertrend"].where(st_ov["supertrend_trend"] == 1)
        bear = st_ov["supertrend"].where(st_ov["supertrend_trend"] == -1)
        ax.plot(x, bull.to_numpy(), color="#009c5b", lw=1.8, label="1m ST bull", zorder=5)
        ax.plot(x, bear.to_numpy(), color="#d62728", lw=1.8, label="1m ST bear", zorder=5)

        if variant in STRUCTURE_SL_VARIANTS:
            rp = float(t.risk_pts) if pd.notna(t.get("risk_pts", float("nan"))) else DEFAULT_RISK_PTS
            ax.axhline(float(t.limit_px), color="#1565c0", ls="--", lw=1.3, label="Entry @ structure %.1f" % float(t.limit_px))
            init_stop = float(t.entry) - rp if t.side == "long" else float(t.entry) + rp
            ax.axhline(init_stop, color="#ef6c00", ls=":", lw=1.3, label="Risk stop (±%.0f) %.1f" % (rp, init_stop))
            ax.axhline(float(t.st_at_signal), color="#7b1fa2", ls="-.", lw=1.0, alpha=0.85, label="ST stop @ signal %.1f" % float(t.st_at_signal))
            if variant == "structure_sl_scale":
                sign = 1.0 if t.side == "long" else -1.0
                tp1 = float(t.entry) + sign * SCALE_R_MULT * rp
                tpr = float(t.entry) + sign * RUNNER_R_MULT * rp
                ax.axhline(tp1, color="#2e7d32", ls="--", lw=1.0, label="Scale +1R %.1f" % tp1)
                ax.axhline(tpr, color="#00695c", ls="--", lw=1.0, label="Runner +3R %.1f" % tpr)
                ax.axhline(float(t.entry), color="#455a64", ls=":", lw=1.0, alpha=0.7, label="BE after scale")
            elif variant == "structure_sl_scale_run":
                sign = 1.0 if t.side == "long" else -1.0
                e = float(t.entry)
                ax.axhline(e + sign * RUN_TP1_PTS, color="#2e7d32", ls="--", lw=1.0, label="Scale +22 %.1f" % (e + sign * RUN_TP1_PTS))
                ax.axhline(e + sign * RUN_TP2_PTS, color="#00695c", ls="--", lw=1.0, label="Scale +50 %.1f" % (e + sign * RUN_TP2_PTS))
                ax.axhline(e + sign * RUN_TP3_PTS, color="#004d40", ls="--", lw=1.0, label="Runner +200 %.1f" % (e + sign * RUN_TP3_PTS))
                ax.axhline(e, color="#455a64", ls=":", lw=1.0, alpha=0.7, label="BE (after scale22 / fav ST)")
        else:
            ax.axhline(float(t.stop), color="#ef6c00", ls=":", lw=1.3, label="Structure SL %.1f" % float(t.stop))
            ax.axhline(float(t.limit_px), color="#1565c0", ls="--", lw=1.2, label="Limit/ST stop %.1f" % float(t.limit_px))

        def _xi(ts) -> Optional[int]:
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize(NY)
            else:
                ts = ts.tz_convert(NY)
            for i, bt in enumerate(bars.index):
                if bt <= ts < bt + pd.Timedelta(minutes=15):
                    return i
            deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(bars.index)]
            return min(deltas)[1] if deltas else None

        ei = _xi(t.entry_ts)
        xi = _xi(t.exit_ts)
        si = _xi(t.signal_ts) if "signal_ts" in t.index else None
        color = "#1a9850" if float(t.pnl_usd) > 0 else "#d73027"
        if si is not None:
            ax.scatter([si], [float(t.st_at_signal)], marker="o", s=70, color="#7b1fa2", edgecolors="white", zorder=7, label="ST signal")
        if ei is not None:
            ax.scatter(
                [ei],
                [float(t.entry)],
                marker="^" if t.side == "long" else "v",
                s=160,
                color=color,
                edgecolors="white",
                zorder=8,
                label="Entry",
            )
        if xi is not None:
            ax.scatter([xi], [float(t.exit)], marker="X", s=140, color=color, edgecolors="white", zorder=8, label="Exit")
        if ei is not None and xi is not None and xi > ei:
            ax.axvspan(ei, xi, color=color, alpha=0.10, zorder=0)

        for d in window_days[1:]:
            for i, bt in enumerate(bars.index):
                if bt.date() == d:
                    ax.axvline(i, color="#bbb", lw=0.8, ls="--", zorder=0)
                    break

        mae = float(t.mae_pts) if "mae_pts" in t.index and pd.notna(t.mae_pts) else float("nan")
        ax.set_title(
            "NQ 15m + 1m ST [%s] | #%d %s %s | %+0.1f pts ($%+.0f) MAE %.1f | %s → %s | %s"
            % (
                variant,
                int(t.trade_id),
                str(t.side).upper(),
                str(t.program).upper(),
                float(t.pnl_pts),
                float(t.pnl_usd),
                mae,
                pd.Timestamp(t.entry_ts).strftime("%Y-%m-%d %H:%M"),
                pd.Timestamp(t.exit_ts).strftime("%Y-%m-%d %H:%M"),
                t.exit_reason,
            )
        )
        ax.legend(loc="upper left", fontsize=8)
        ax.set_xlim(-1, len(bars))
        step = max(1, len(bars) // 12)
        ax.set_xticks(x[::step])
        ax.set_xticklabels([bars.index[i].strftime("%m-%d %H:%M") for i in x[::step]], rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("NQ")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fname = "%s_%s_%s_mae%.0f_pnl%+.0f.png" % (
            pd.Timestamp(t.entry_ts).strftime("%Y-%m-%d"),
            t.side,
            t.exit_reason,
            mae if mae == mae else 0,
            float(t.pnl_usd),
        )
        fig.savefig(charts / fname, dpi=110)
        plt.close(fig)

    pngs = sorted(charts.glob("*.png"))
    lines = [
        "# Structure-program ST charts — %s (NQ)" % variant,
        "",
        "15-minute RTH candles (3 sessions), 1-minute SuperTrend 14×3 overlay, entry/exit + MAE in title.",
        "",
    ]
    for p in pngs:
        lines.append("- [%s](%s)" % (p.name, p.name))
    (charts / "INDEX.md").write_text("\n".join(lines))
    print("Charts: %d → %s" % (len(pngs), charts), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--variant",
        choices=[
            "core",
            "structure_sl",
            "structure_sl_scale",
            "structure_sl_scale_run",
            "touch_st_align",
            "touch_st_align_fade20",
        ],
        default="structure_sl_scale",
    )
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--risk-pts", type=float, default=None)
    ap.add_argument("--charts", type=int, default=50)
    ap.add_argument("--charts-only", action="store_true")
    args = ap.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    out_dir = OUT_ROOT / args.variant
    if args.risk_pts is None:
        risk_pts = (
            8.0
            if args.variant
            in {
                "structure_sl_scale",
                "structure_sl_scale_run",
                TOUCH_ALIGN_VARIANT,
                TOUCH_ALIGN_FADE20_VARIANT,
            }
            else DEFAULT_RISK_PTS
        )
    else:
        risk_pts = float(args.risk_pts)

    gby = None
    if args.charts_only:
        trades_path = out_dir / "trades.csv"
        df = pd.read_csv(trades_path, parse_dates=["signal_ts", "entry_ts", "exit_ts"])
    else:
        print("Loading NQ 1m…", flush=True)
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        df = run_study(
            variant=args.variant,
            start=start,
            end=end,
            max_days=args.max_days,
            risk_pts=risk_pts,
            gby=gby,
        )

    if args.charts and not df.empty:
        if gby is None:
            print("Loading NQ 1m for charts…", flush=True)
            gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        chart_trades(df, gby, out_dir, n=args.charts, variant=args.variant)


if __name__ == "__main__":
    main()
