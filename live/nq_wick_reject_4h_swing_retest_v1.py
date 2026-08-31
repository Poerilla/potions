"""NQ WICK_REJECT 4h-confirm limit-retest — separate family from 1h model.

strategy_id: nq_wick_reject_4h_swing_retest_v1

Stage A (S1, this run):
  frozen 4h WICK_REJECT seed → later completed 4h close outside seed
  → resting limit retest of seed boundary → stop opposite ±1 tick
  → 0.5W/1W/2W @ 50/25/25
  seed expiry: 30 × 4h bars; primary order life: 48h

Stage B: timing/expiry diagnostics + order-life 24/48/72 (seed expiry fixed 30).
Stage C (S2): post-seed atlas CLOSE_BREAK outside seed → limit at new swing level
  (only after S1 clears positive locked avg R on both slices; --s2 / --s2-only).

Hub: live/state/nq_wick_reject_4h_swing_retest_v1/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_4h_swing_retest_v1 --email
  python -m live.nq_wick_reject_4h_swing_retest_v1 --s2-only --email
  python -m live.nq_wick_reject_4h_swing_retest_v1 --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import HUB as ATLAS_HUB
from .nq_structure_change_event_study import TICK
from .nq_wick_reject_range_seed_retest import (
    STOP_BUFFER_TICKS,
    Seed,
    _atr_1m,
    _bar_slice,
    _first_1m_after,
    _localize,
    _manage_scaleout,
    _summarize_trades,
    build_rth_tape,
    count_age_overlaps,
    load_wick_events,
)
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_wick_reject_4h_swing_retest_v1"
NY = "America/New_York"
PEN_PRIMARY = 0.05
WIDTH_MIN_ATR = 0.25
WIDTH_MAX_ATR = 2.00
MAX_AGE_4H_BARS = 30  # mechanical translation from 20 (1h model)
LIMIT_LIFE_PRIMARY = pd.Timedelta(hours=48)
ORDER_LIFE_HOURS = (24, 48, 72)  # Stage B; 48 = primary
BREAK_TYPE_S1 = "seed_boundary_4h_close"
BREAK_TYPE_S2 = "new_4h_swing_break"
STRATEGY_ID = "nq_wick_reject_4h_swing_retest_v1"


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _expire_ts_from_4h(h4: pd.DataFrame, seed_close: pd.Timestamp, n_bars: int) -> pd.Timestamp:
    seed_close = _localize(seed_close)
    if h4 is None or h4.empty:
        return seed_close + pd.Timedelta(hours=4 * n_bars)
    opens = h4.index[h4.index > seed_close - pd.Timedelta(seconds=1)]
    subsequent = [o for o in opens if _localize(o) >= seed_close]
    if len(subsequent) >= n_bars:
        o_n = _localize(subsequent[n_bars - 1])
        return o_n + pd.Timedelta(hours=4)
    return seed_close + pd.Timedelta(hours=4 * n_bars)


def make_seeds_30(
    events: pd.DataFrame,
    tape: pd.DataFrame,
    h4: pd.DataFrame,
    early: Dict,
) -> Tuple[List[Seed], pd.DataFrame]:
    """Same eligibility as 1h model; seed expiry = 30 completed 4h bars."""
    census_rows = []
    seeds: List[Seed] = []
    seen_bars = set()

    for _, ev in events.iterrows():
        eid = str(ev["event_id"])
        open_ts = _localize(pd.Timestamp(ev["confirm_bar_open_ts"]))
        close_ts = _localize(pd.Timestamp(ev["confirm_bar_close_ts"]))
        bar_key = (open_ts.isoformat(), close_ts.isoformat())
        atr4 = float(ev["atr_20"])
        pen = float(ev.get("penetration_ATR") or 0)
        day = close_ts.date()
        early_flag = bool(early.get(day, False))

        window = _bar_slice(tape, open_ts, close_ts)
        row = {
            "event_id": eid,
            "slice": ev.get("slice", ""),
            "confirm_bar_open_ts": open_ts.isoformat(),
            "confirm_bar_close_ts": close_ts.isoformat(),
            "atr20_4h": atr4,
            "penetration_ATR": pen,
            "early_close": int(early_flag),
            "duplicate_bar": int(bar_key in seen_bars),
            "eligible": 0,
            "reject_reason": "",
            "range_high": np.nan,
            "range_low": np.nan,
            "range_width": np.nan,
            "width_ATR": np.nan,
            "width_ticks": np.nan,
            "atr20_1m": np.nan,
            "width_1m_ATR": np.nan,
        }

        if pen < PEN_PRIMARY - 1e-12:
            row["reject_reason"] = "pen_lt_0.05"
            census_rows.append(row)
            continue
        if early_flag:
            row["reject_reason"] = "early_close_session"
            census_rows.append(row)
            continue
        if window.empty:
            row["reject_reason"] = "no_1m_in_confirm_bar"
            census_rows.append(row)
            continue
        if bar_key in seen_bars:
            row["reject_reason"] = "duplicate_confirm_bar"
            census_rows.append(row)
            continue

        hi = float(window["high"].max())
        lo = float(window["low"].min())
        w = hi - lo
        atr1 = _atr_1m(tape, close_ts)
        row.update(
            {
                "range_high": hi,
                "range_low": lo,
                "range_width": w,
                "width_ATR": w / atr4 if atr4 > 0 else np.nan,
                "width_ticks": w / TICK,
                "atr20_1m": atr1,
                "width_1m_ATR": w / atr1 if atr1 and atr1 > 0 else np.nan,
            }
        )
        if w < WIDTH_MIN_ATR * atr4:
            row["reject_reason"] = "width_lt_0.25_ATR"
            census_rows.append(row)
            continue
        if w > WIDTH_MAX_ATR * atr4:
            row["reject_reason"] = "width_gt_2.00_ATR"
            census_rows.append(row)
            continue

        available = _first_1m_after(tape, close_ts)
        if available is None:
            row["reject_reason"] = "no_1m_after_close"
            census_rows.append(row)
            continue

        expires = _expire_ts_from_4h(h4, close_ts, MAX_AGE_4H_BARS)
        seed = Seed(
            seed_id="SEED_%s" % eid,
            event_id=eid,
            slice=str(ev.get("slice", "")),
            high=hi,
            low=lo,
            width=w,
            atr20_4h=atr4,
            atr20_1m=atr1 if atr1 == atr1 else float("nan"),
            seed_close_ts=close_ts,
            available_at=available,
            expires_at=expires,
        )
        seen_bars.add(bar_key)
        row["eligible"] = 1
        row["reject_reason"] = ""
        census_rows.append(row)
        seeds.append(seed)

    return seeds, pd.DataFrame(census_rows)


def _4h_bars_after(h4: pd.DataFrame, after_ts: pd.Timestamp, until: pd.Timestamp) -> pd.DataFrame:
    """Completed 4h bars with end_ts > after_ts and bar open before until."""
    after_ts = _localize(after_ts)
    until = _localize(until)
    if h4 is None or h4.empty:
        return pd.DataFrame()
    outs = []
    for ts, row in h4.iterrows():
        o = _localize(ts)
        end = o + pd.Timedelta(hours=4)
        if end <= after_ts:
            continue
        if o >= until:
            break
        outs.append((end, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    if not outs:
        return pd.DataFrame()
    return pd.DataFrame(outs, columns=["end_ts", "open", "high", "low", "close"])


def load_atlas_4h_close_breaks() -> pd.DataFrame:
    """Frozen StructureProgramEngine_v1 CLOSE_BREAK events on 4h (identical atlas)."""
    df = pd.read_csv(ATLAS_HUB / "structure_events.csv")
    m = (df["structure_timeframe"] == "4h") & (df["event_type"] == "CLOSE_BREAK")
    out = df.loc[m].copy()
    out["confirm_ts"] = pd.to_datetime(out["confirm_bar_close_ts"], utc=True).dt.tz_convert(NY)
    out["available_at"] = pd.to_datetime(out["feature_available_at"], utc=True).dt.tz_convert(NY)
    return out.sort_values("confirm_ts").reset_index(drop=True)


def _first_swing_after(swings: pd.DataFrame, after_ts: pd.Timestamp, direction: str) -> Optional[pd.Timestamp]:
    after_ts = _localize(after_ts)
    sub = swings[(swings["break_direction"] == direction) & (swings["available_at"] > after_ts)]
    if sub.empty:
        return None
    return _localize(sub.iloc[0]["available_at"])


def phase0_timing_census(
    seeds: List[Seed],
    h4: pd.DataFrame,
    tape: pd.DataFrame,
    swings: pd.DataFrame,
) -> pd.DataFrame:
    """Feasibility census before P&L — S1 break + swing timing + retest windows."""
    rows = []
    for seed in seeds:
        bars = _4h_bars_after(h4, seed.available_at, seed.expires_at + pd.Timedelta(hours=4))
        first_above = None
        first_below = None
        for _, b in bars.iterrows():
            end = _localize(b["end_ts"])
            if end > seed.expires_at:
                break
            cl = float(b["close"])
            if first_above is None and cl > seed.high:
                first_above = end
            if first_below is None and cl < seed.low:
                first_below = end
            if first_above is not None and first_below is not None:
                break

        bull_swing = _first_swing_after(swings, seed.available_at, "bullish")
        bear_swing = _first_swing_after(swings, seed.available_at, "bearish")
        if bull_swing is not None and bull_swing > seed.expires_at:
            bull_swing = None
        if bear_swing is not None and bear_swing > seed.expires_at:
            bear_swing = None

        # S1 valid break = first 4h close outside (no swing AND)
        long_break = first_above
        short_break = first_below

        # choose first break chronologically for path metrics
        break_ts = None
        break_side = ""
        if long_break is not None and short_break is not None:
            if long_break <= short_break:
                break_ts, break_side = long_break, "LONG"
            else:
                break_ts, break_side = short_break, "SHORT"
        elif long_break is not None:
            break_ts, break_side = long_break, "LONG"
        elif short_break is not None:
            break_ts, break_side = short_break, "SHORT"

        seed_expired_before_break = int(break_ts is None)
        both_sides = int(first_above is not None and first_below is not None)

        seed_to_break_h = (
            (break_ts - seed.available_at).total_seconds() / 3600.0 if break_ts is not None else np.nan
        )

        # retest / fill timing under primary 48h life (diagnostic path, no invalidation cancel yet)
        retest_h = np.nan
        fill_h = np.nan
        retest_24 = retest_48 = retest_72 = 0
        break_expired_before_retest = 0
        if break_ts is not None:
            limit = seed.high if break_side == "LONG" else seed.low
            live_at = _first_1m_after(tape, break_ts)
            deadline = min(break_ts + LIMIT_LIFE_PRIMARY, seed.expires_at)
            fill = None
            if live_at is not None:
                fill = _scan_retest_touch(
                    tape,
                    side=break_side,
                    limit=limit,
                    live_at=live_at,
                    deadline=deadline,
                )
            if fill is not None:
                fill_ts, _ = fill
                fill_h = (fill_ts - break_ts).total_seconds() / 3600.0
                retest_h = fill_h
                retest_24 = int(fill_h <= 24)
                retest_48 = int(fill_h <= 48)
                retest_72 = int(fill_h <= 72)
            else:
                break_expired_before_retest = 1
                # also check unbounded touch within 72h for capture fractions
                if live_at is not None:
                    soft = _scan_retest_touch(
                        tape,
                        side=break_side,
                        limit=limit,
                        live_at=live_at,
                        deadline=break_ts + pd.Timedelta(hours=72),
                    )
                    if soft is not None:
                        soft_h = (soft[0] - break_ts).total_seconds() / 3600.0
                        retest_h = soft_h
                        retest_24 = int(soft_h <= 24)
                        retest_48 = int(soft_h <= 48)
                        retest_72 = int(soft_h <= 72)

        rows.append(
            {
                "seed_id": seed.seed_id,
                "event_id": seed.event_id,
                "slice": seed.slice,
                "seed_timestamp": seed.seed_close_ts.isoformat(),
                "seed_available_at": seed.available_at.isoformat(),
                "seed_expires_at": seed.expires_at.isoformat(),
                "seed_high": seed.high,
                "seed_low": seed.low,
                "seed_width": seed.width,
                "seed_width_ATR": seed.width / seed.atr20_4h if seed.atr20_4h else np.nan,
                "first_4h_close_above_seed_high": first_above.isoformat() if first_above else "",
                "first_4h_close_below_seed_low": first_below.isoformat() if first_below else "",
                "first_confirmed_bullish_4h_swing_after_seed": bull_swing.isoformat() if bull_swing else "",
                "first_confirmed_bearish_4h_swing_after_seed": bear_swing.isoformat() if bear_swing else "",
                "first_valid_4h_long_break_timestamp": long_break.isoformat() if long_break else "",
                "first_valid_4h_short_break_timestamp": short_break.isoformat() if short_break else "",
                "first_break_side": break_side,
                "seed_to_break_hours": seed_to_break_h,
                "break_to_first_retest_hours": retest_h,
                "break_to_limit_fill_hours": fill_h if break_expired_before_retest == 0 else np.nan,
                "retest_occurs_within_24h": retest_24,
                "retest_occurs_within_48h": retest_48,
                "retest_occurs_within_72h": retest_72,
                "seed_expired_before_break": seed_expired_before_break,
                "break_expired_before_retest": break_expired_before_retest,
                "both_sides_break_before_fill": both_sides,
            }
        )
    return pd.DataFrame(rows)


def _scan_retest_touch(
    tape: pd.DataFrame,
    *,
    side: str,
    limit: float,
    live_at: pd.Timestamp,
    deadline: pd.Timestamp,
) -> Optional[Tuple[pd.Timestamp, float]]:
    live_at = _localize(live_at)
    deadline = _localize(deadline)
    pos = tape.index.searchsorted(live_at, side="left")
    if pos < len(tape.index) and _localize(tape.index[pos]) < live_at:
        pos += 1
    for j in range(pos, len(tape)):
        ts = _localize(tape.index[j])
        if ts > deadline:
            return None
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        o = float(tape["open"].iloc[j])
        if side == "LONG" and l <= limit:
            px = float(o) if o < limit else float(limit)
            return ts, px
        if side == "SHORT" and h >= limit:
            px = float(o) if o > limit else float(limit)
            return ts, px
    return None


def _fill_until_invalidate_4h(
    tape: pd.DataFrame,
    *,
    h4_bars: pd.DataFrame,
    break_end: pd.Timestamp,
    side: str,
    limit: float,
    live_at: pd.Timestamp,
    deadline: pd.Timestamp,
    seed: Seed,
) -> Optional[Tuple[pd.Timestamp, float]]:
    """Fill resting limit; cancel on completed 4h close back inside / opposite / deadline."""
    inv_ts = None
    inv_reason = ""
    for _, b in h4_bars.iterrows():
        end = _localize(b["end_ts"])
        if end <= break_end:
            continue
        cl = float(b["close"])
        if side == "LONG":
            if cl < seed.high:
                inv_ts, inv_reason = end, "4h_close_back_inside"
                break
            if cl < seed.low:
                inv_ts, inv_reason = end, "opposite_4h_break"
                break
        else:
            if cl > seed.low:
                inv_ts, inv_reason = end, "4h_close_back_inside"
                break
            if cl > seed.high:
                inv_ts, inv_reason = end, "opposite_4h_break"
                break

    hard = deadline
    if inv_ts is not None:
        hard = min(hard, inv_ts)

    pos = tape.index.searchsorted(live_at, side="left")
    if pos < len(tape) and _localize(tape.index[pos]) < live_at:
        pos += 1
    for j in range(pos, len(tape)):
        ts = _localize(tape.index[j])
        if ts > hard:
            break
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        o = float(tape["open"].iloc[j])
        if side == "LONG" and l <= limit:
            px = float(o) if o < limit else float(limit)
            seed.state = "POSITION_OPEN"
            return ts, px
        if side == "SHORT" and h >= limit:
            px = float(o) if o > limit else float(limit)
            seed.state = "POSITION_OPEN"
            return ts, px

    if inv_ts is not None and (inv_ts <= deadline):
        seed.state = "INVALIDATED"
        seed.terminal_reason = inv_reason
    else:
        seed.state = "EXPIRED"
        seed.terminal_reason = "limit_life_or_age_no_fill"
    return None


def run_s1_trade(
    seed: Seed,
    tape: pd.DataFrame,
    h4: pd.DataFrame,
    *,
    limit_life: pd.Timedelta,
    variant: str,
) -> dict:
    """S1: 4h close beyond seed → limit at seed boundary; invalidate on 4h close back inside."""
    bars = _4h_bars_after(h4, seed.available_at, seed.expires_at + pd.Timedelta(hours=4))
    for _, b in bars.iterrows():
        end = _localize(b["end_ts"])
        cl = float(b["close"])
        if end > seed.expires_at:
            return _empty_outcome(seed, variant, "EXPIRED", "max_age_no_break")
        side = ""
        limit = None
        if cl > seed.high:
            side, limit = "LONG", seed.high
        elif cl < seed.low:
            side, limit = "SHORT", seed.low
        else:
            continue

        live_at = _first_1m_after(tape, end)
        if live_at is None:
            return _empty_outcome(seed, variant, "EXPIRED", "no_1m_after_break")
        deadline = min(end + limit_life, seed.expires_at)
        fill = _fill_until_invalidate_4h(
            tape,
            h4_bars=bars,
            break_end=end,
            side=side,
            limit=float(limit),
            live_at=live_at,
            deadline=deadline,
            seed=seed,
        )
        if fill is None:
            return _empty_outcome(
                seed,
                variant,
                seed.state if seed.state in ("INVALIDATED", "EXPIRED") else "EXPIRED",
                seed.terminal_reason or "no_fill",
                side=side,
                break_ts=end,
                live_at=live_at,
                deadline=deadline,
            )
        fill_ts, entry = fill
        stop = seed.low - STOP_BUFFER_TICKS * TICK if side == "LONG" else seed.high + STOP_BUFFER_TICKS * TICK
        w = seed.width
        if side == "LONG":
            targets = [seed.high + 0.5 * w, seed.high + 1.0 * w, seed.high + 2.0 * w]
        else:
            targets = [seed.low - 0.5 * w, seed.low - 1.0 * w, seed.low - 2.0 * w]
        mg = _manage_scaleout(
            tape,
            side=side,
            fill_ts=fill_ts,
            entry=entry,
            stop=stop,
            targets=targets,
            qtys=[0.50, 0.25, 0.25],
            hard_end_ts=seed.expires_at,
        )
        # hard assertions (soft flags)
        assert fill_ts <= deadline + pd.Timedelta(seconds=1), "fill after expiry"
        assert fill_ts >= live_at, "fill before order live"
        caus = int(seed.available_at < live_at <= fill_ts < mg["exit_ts"])
        return {
            "variant": variant,
            "strategy_id": STRATEGY_ID,
            "break_type": BREAK_TYPE_S1,
            "seed_id": seed.seed_id,
            "event_id": seed.event_id,
            "slice": seed.slice,
            "side": side,
            "seed_bar_close_ts": seed.seed_close_ts.isoformat(),
            "seed_available_at": seed.available_at.isoformat(),
            "seed_expires_at": seed.expires_at.isoformat(),
            "seed_high": seed.high,
            "seed_low": seed.low,
            "seed_width": seed.width,
            "range_width": seed.width,
            "break_confirm_ts": end.isoformat(),
            "break_available_at": live_at.isoformat(),
            "limit_submit_ts": live_at.isoformat(),
            "limit_active_ts": live_at.isoformat(),
            "limit_expiry_ts": deadline.isoformat(),
            "limit_fill_ts": fill_ts.isoformat(),
            "limit_fill_price": entry,
            "order_live_at": live_at.isoformat(),
            "fill_ts": fill_ts.isoformat(),
            "entry": entry,
            "stop_price": stop,
            "stop": stop,
            "target_0_5W": targets[0],
            "target_1W": targets[1],
            "target_2W": targets[2],
            "tp1": targets[0],
            "tp2": targets[1],
            "tp3": targets[2],
            "entry_to_stop_distance": abs(entry - stop),
            "limit_life_hours": int(limit_life.total_seconds() // 3600),
            "time_seed_to_break_min": (end - seed.available_at).total_seconds() / 60.0,
            "time_break_to_fill_min": (fill_ts - end).total_seconds() / 60.0,
            "time_fill_to_exit_min": (mg["exit_ts"] - fill_ts).total_seconds() / 60.0,
            "seed_to_break_hours": (end - seed.available_at).total_seconds() / 3600.0,
            "break_to_limit_fill_hours": (fill_ts - end).total_seconds() / 3600.0,
            "causality_ok": caus,
            "outcome_USD": mg["net_usd"],
            "outcome_R": mg["r_multiple"],
            "MAE_R": (mg["mae_pts"] / abs(entry - stop)) if abs(entry - stop) > 0 else 0.0,
            "MFE_R": (mg["mfe_pts"] / abs(entry - stop)) if abs(entry - stop) > 0 else 0.0,
            **{k: mg[k] for k in mg if k != "exit_ts"},
            "net_usd": mg["net_usd"],
            "r_multiple": mg["r_multiple"],
            "exit_ts": mg["exit_ts"].isoformat(),
            "exit_reason": mg["exit_reason"],
            "outcome": "FILLED",
            "terminal_reason": mg["exit_reason"],
        }
    return _empty_outcome(seed, variant, "EXPIRED", "max_age_no_break")


def detect_post_seed_confirmed_swing_break(
    seed: Seed,
    swings: pd.DataFrame,
) -> Optional[dict]:
    """S2: first atlas 4h CLOSE_BREAK after seed; trade only if outside seeded range.

    break_level = protected_swing_price (frozen StructureProgramEngine level that broke).
    """
    after = _localize(seed.available_at)
    sub = swings[swings["available_at"] > after]
    if sub.empty:
        return None
    ev = sub.iloc[0]
    confirm = _localize(ev["available_at"])
    if confirm > seed.expires_at:
        return None
    level = float(ev["protected_swing_price"])
    direction = str(ev["break_direction"])
    if direction == "bullish" and level > seed.high:
        return {
            "side": "LONG",
            "level": level,
            "available_at": confirm,
            "confirm_ts": _localize(ev["confirm_ts"]),
            "event_id": str(ev["event_id"]),
            "event_family": str(ev.get("event_family", "")),
        }
    if direction == "bearish" and level < seed.low:
        return {
            "side": "SHORT",
            "level": level,
            "available_at": confirm,
            "confirm_ts": _localize(ev["confirm_ts"]),
            "event_id": str(ev["event_id"]),
            "event_family": str(ev.get("event_family", "")),
        }
    return None


def _fill_until_invalidate_swing(
    tape: pd.DataFrame,
    *,
    h4_bars: pd.DataFrame,
    break_end: pd.Timestamp,
    side: str,
    limit: float,
    live_at: pd.Timestamp,
    deadline: pd.Timestamp,
    seed: Seed,
) -> Optional[Tuple[pd.Timestamp, float]]:
    """Cancel if completed 4h close reclaims back through the new swing level."""
    inv_ts = None
    inv_reason = ""
    for _, b in h4_bars.iterrows():
        end = _localize(b["end_ts"])
        if end <= break_end:
            continue
        cl = float(b["close"])
        if side == "LONG" and cl < limit:
            inv_ts, inv_reason = end, "4h_close_reclaim_swing"
            break
        if side == "SHORT" and cl > limit:
            inv_ts, inv_reason = end, "4h_close_reclaim_swing"
            break

    hard = deadline
    if inv_ts is not None:
        hard = min(hard, inv_ts)

    pos = tape.index.searchsorted(live_at, side="left")
    if pos < len(tape) and _localize(tape.index[pos]) < live_at:
        pos += 1
    for j in range(pos, len(tape)):
        ts = _localize(tape.index[j])
        if ts > hard:
            break
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        o = float(tape["open"].iloc[j])
        if side == "LONG" and l <= limit:
            px = float(o) if o < limit else float(limit)
            seed.state = "POSITION_OPEN"
            return ts, px
        if side == "SHORT" and h >= limit:
            px = float(o) if o > limit else float(limit)
            seed.state = "POSITION_OPEN"
            return ts, px

    if inv_ts is not None and (inv_ts <= deadline):
        seed.state = "INVALIDATED"
        seed.terminal_reason = inv_reason
    else:
        seed.state = "EXPIRED"
        seed.terminal_reason = "limit_life_or_age_no_fill"
    return None


def run_s2_trade(
    seed: Seed,
    tape: pd.DataFrame,
    h4: pd.DataFrame,
    swings: pd.DataFrame,
    *,
    limit_life: pd.Timedelta = LIMIT_LIFE_PRIMARY,
    variant: str = "s2_new_swing_48h",
) -> dict:
    """S2: first post-seed confirmed 4h CLOSE_BREAK outside seed → limit at swing level.

    Stop stays at opposite *original* seed boundary. Targets use seed_width from swing level.
    """
    sb = detect_post_seed_confirmed_swing_break(seed, swings)
    if sb is None:
        return _empty_outcome(seed, variant, "EXPIRED", "no_qualifying_first_swing_break")

    side = sb["side"]
    level = float(sb["level"])
    confirm_ts = sb["confirm_ts"]
    live_at = _first_1m_after(tape, sb["available_at"])
    if live_at is None:
        return _empty_outcome(seed, variant, "EXPIRED", "no_1m_after_swing", side=side, break_ts=confirm_ts)

    deadline = min(sb["available_at"] + limit_life, seed.expires_at)
    bars = _4h_bars_after(h4, seed.available_at, seed.expires_at + pd.Timedelta(hours=4))
    fill = _fill_until_invalidate_swing(
        tape,
        h4_bars=bars,
        break_end=confirm_ts,
        side=side,
        limit=level,
        live_at=live_at,
        deadline=deadline,
        seed=seed,
    )
    if fill is None:
        row = _empty_outcome(
            seed,
            variant,
            seed.state if seed.state in ("INVALIDATED", "EXPIRED") else "EXPIRED",
            seed.terminal_reason or "no_fill",
            side=side,
            break_ts=confirm_ts,
            live_at=live_at,
            deadline=deadline,
        )
        row["break_type"] = BREAK_TYPE_S2
        row["swing_event_id"] = sb["event_id"]
        row["swing_level"] = level
        return row

    fill_ts, entry = fill
    stop = seed.low - STOP_BUFFER_TICKS * TICK if side == "LONG" else seed.high + STOP_BUFFER_TICKS * TICK
    w = seed.width
    if side == "LONG":
        targets = [level + 0.5 * w, level + 1.0 * w, level + 2.0 * w]
    else:
        targets = [level - 0.5 * w, level - 1.0 * w, level - 2.0 * w]
    mg = _manage_scaleout(
        tape,
        side=side,
        fill_ts=fill_ts,
        entry=entry,
        stop=stop,
        targets=targets,
        qtys=[0.50, 0.25, 0.25],
        hard_end_ts=seed.expires_at,
    )
    caus = int(seed.available_at < live_at <= fill_ts < mg["exit_ts"])
    return {
        "variant": variant,
        "strategy_id": STRATEGY_ID,
        "break_type": BREAK_TYPE_S2,
        "swing_event_id": sb["event_id"],
        "swing_level": level,
        "seed_id": seed.seed_id,
        "event_id": seed.event_id,
        "slice": seed.slice,
        "side": side,
        "seed_bar_close_ts": seed.seed_close_ts.isoformat(),
        "seed_available_at": seed.available_at.isoformat(),
        "seed_expires_at": seed.expires_at.isoformat(),
        "seed_high": seed.high,
        "seed_low": seed.low,
        "seed_width": seed.width,
        "range_width": seed.width,
        "break_confirm_ts": confirm_ts.isoformat(),
        "break_available_at": live_at.isoformat(),
        "limit_submit_ts": live_at.isoformat(),
        "limit_active_ts": live_at.isoformat(),
        "limit_expiry_ts": deadline.isoformat(),
        "limit_fill_ts": fill_ts.isoformat(),
        "limit_fill_price": entry,
        "order_live_at": live_at.isoformat(),
        "fill_ts": fill_ts.isoformat(),
        "entry": entry,
        "stop_price": stop,
        "stop": stop,
        "target_0_5W": targets[0],
        "target_1W": targets[1],
        "target_2W": targets[2],
        "tp1": targets[0],
        "tp2": targets[1],
        "tp3": targets[2],
        "entry_to_stop_distance": abs(entry - stop),
        "limit_life_hours": int(limit_life.total_seconds() // 3600),
        "time_seed_to_break_min": (confirm_ts - seed.available_at).total_seconds() / 60.0,
        "time_break_to_fill_min": (fill_ts - confirm_ts).total_seconds() / 60.0,
        "time_fill_to_exit_min": (mg["exit_ts"] - fill_ts).total_seconds() / 60.0,
        "seed_to_break_hours": (confirm_ts - seed.available_at).total_seconds() / 3600.0,
        "break_to_limit_fill_hours": (fill_ts - confirm_ts).total_seconds() / 3600.0,
        "causality_ok": caus,
        "outcome_USD": mg["net_usd"],
        "outcome_R": mg["r_multiple"],
        "MAE_R": (mg["mae_pts"] / abs(entry - stop)) if abs(entry - stop) > 0 else 0.0,
        "MFE_R": (mg["mfe_pts"] / abs(entry - stop)) if abs(entry - stop) > 0 else 0.0,
        **{k: mg[k] for k in mg if k != "exit_ts"},
        "net_usd": mg["net_usd"],
        "r_multiple": mg["r_multiple"],
        "exit_ts": mg["exit_ts"].isoformat(),
        "exit_reason": mg["exit_reason"],
        "outcome": "FILLED",
        "terminal_reason": mg["exit_reason"],
    }


def _empty_outcome(
    seed: Seed,
    variant: str,
    outcome: str,
    reason: str,
    *,
    side: str = "",
    break_ts: Optional[pd.Timestamp] = None,
    live_at: Optional[pd.Timestamp] = None,
    deadline: Optional[pd.Timestamp] = None,
) -> dict:
    return {
        "variant": variant,
        "strategy_id": STRATEGY_ID,
        "break_type": BREAK_TYPE_S1,
        "seed_id": seed.seed_id,
        "event_id": seed.event_id,
        "slice": seed.slice,
        "side": side or seed.side or "",
        "seed_bar_close_ts": seed.seed_close_ts.isoformat(),
        "seed_available_at": seed.available_at.isoformat(),
        "seed_expires_at": seed.expires_at.isoformat(),
        "seed_high": seed.high,
        "seed_low": seed.low,
        "seed_width": seed.width,
        "range_width": seed.width,
        "break_confirm_ts": break_ts.isoformat() if break_ts else "",
        "break_available_at": live_at.isoformat() if live_at else "",
        "limit_submit_ts": live_at.isoformat() if live_at else "",
        "limit_active_ts": live_at.isoformat() if live_at else "",
        "limit_expiry_ts": deadline.isoformat() if deadline else "",
        "limit_fill_ts": "",
        "limit_fill_price": np.nan,
        "order_live_at": live_at.isoformat() if live_at else "",
        "fill_ts": "",
        "entry": np.nan,
        "stop_price": np.nan,
        "stop": np.nan,
        "target_0_5W": np.nan,
        "target_1W": np.nan,
        "target_2W": np.nan,
        "tp1": np.nan,
        "tp2": np.nan,
        "tp3": np.nan,
        "entry_to_stop_distance": seed.width + STOP_BUFFER_TICKS * TICK,
        "limit_life_hours": np.nan,
        "time_seed_to_break_min": (break_ts - seed.available_at).total_seconds() / 60.0
        if break_ts is not None
        else np.nan,
        "time_break_to_fill_min": np.nan,
        "time_fill_to_exit_min": np.nan,
        "seed_to_break_hours": (break_ts - seed.available_at).total_seconds() / 3600.0
        if break_ts is not None
        else np.nan,
        "break_to_limit_fill_hours": np.nan,
        "causality_ok": 1,
        "outcome_USD": 0.0,
        "outcome_R": 0.0,
        "MAE_R": 0.0,
        "MFE_R": 0.0,
        "exit_ts": "",
        "exit_reason": "",
        "net_pts": 0.0,
        "net_usd": 0.0,
        "r_multiple": 0.0,
        "risk_pts": seed.width + STOP_BUFFER_TICKS * TICK,
        "gap_through_stop": 0,
        "mfe_pts": 0.0,
        "mae_pts": 0.0,
        "hit_tp1": 0,
        "hit_tp2": 0,
        "hit_tp3": 0,
        "stopped": 0,
        "n_legs": 0,
        "outcome": outcome,
        "terminal_reason": reason,
    }


def _pct(s: pd.Series, q: float) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    return float(s.quantile(q))


def stage_b_timing_report(hub: Path, timing: pd.DataFrame, trades_by_life: Dict[int, pd.DataFrame]) -> str:
    """Report (do not optimize) seed-to-break / break-to-retest / expiry reasons."""
    lines = [
        "# Stage B — timing / expiry diagnostics (S1)",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Contract:** seed expiry fixed at 30 × 4h; order-life cases 24 / 48 / 72h.",
        "**Rule:** report only — no tuning this run.",
        "",
    ]
    broke = timing[timing["seed_expired_before_break"] == 0]
    s2b = broke["seed_to_break_hours"]
    b2r = broke["break_to_first_retest_hours"].dropna()
    lines += [
        "## Seed → first 4h break (hours)",
        "",
        "| p25 | median | p75 | p90 | n |",
        "|---:|---:|---:|---:|---:|",
        "| %.2f | %.2f | %.2f | %.2f | %d |"
        % (_pct(s2b, 0.25), _pct(s2b, 0.50), _pct(s2b, 0.75), _pct(s2b, 0.90), len(s2b)),
        "",
        "## Break → first retest touch (hours)",
        "",
        "| p25 | median | p75 | p90 | n |",
        "|---:|---:|---:|---:|---:|",
        "| %.2f | %.2f | %.2f | %.2f | %d |"
        % (_pct(b2r, 0.25), _pct(b2r, 0.50), _pct(b2r, 0.75), _pct(b2r, 0.90), len(b2r)),
        "",
        "## Retest order-life capture (among seeds with a 4h break)",
        "",
        "| Window | fraction |",
        "|---|---:|",
        "| ≤12h | (see soft scan below; primary flags 24/48/72) |",
        "| ≤24h | %.1f%% |" % (100 * float(broke["retest_occurs_within_24h"].mean()) if len(broke) else 0),
        "| ≤48h | %.1f%% |" % (100 * float(broke["retest_occurs_within_48h"].mean()) if len(broke) else 0),
        "| ≤72h | %.1f%% |" % (100 * float(broke["retest_occurs_within_72h"].mean()) if len(broke) else 0),
        "",
    ]
    # finer capture from filled books if present
    if 48 in trades_by_life:
        t48 = trades_by_life[48]
        filled = t48[t48["outcome"] == "FILLED"]
        if len(filled):
            hrs = filled["break_to_limit_fill_hours"].astype(float)
            lines += [
                "### Filled primary (48h book) capture cumulative",
                "",
                "| ≤12h | ≤24h | ≤36h | ≤48h | ≤72h |",
                "|---:|---:|---:|---:|---:|",
                "| %.0f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% |"
                % (
                    100 * float((hrs <= 12).mean()),
                    100 * float((hrs <= 24).mean()),
                    100 * float((hrs <= 36).mean()),
                    100 * float((hrs <= 48).mean()),
                    100 * float((hrs <= 72).mean()),
                ),
                "",
            ]

    # expiry taxonomy from primary 48h book
    t = trades_by_life.get(48, pd.DataFrame())
    if len(t):
        reasons = t["terminal_reason"].fillna("").astype(str)
        outcomes = t["outcome"].fillna("").astype(str)
        n = len(t)
        no_break = int(((outcomes != "FILLED") & reasons.str.contains("max_age_no_break")).sum())
        no_retest = int(
            (
                (outcomes != "FILLED")
                & reasons.str.contains("limit_life|no_fill|age_no_fill", regex=True)
            ).sum()
        )
        reentered = int(((outcomes != "FILLED") & reasons.str.contains("back_inside")).sum())
        opposite = int(((outcomes != "FILLED") & reasons.str.contains("opposite")).sum())
        lines += [
            "## Expired / non-fill taxonomy (48h primary book, n=%d seeds)" % n,
            "",
            "| Reason | n | rate |",
            "|---|---:|---:|",
            "| no break before seed expiry | %d | %.1f%% |" % (no_break, 100 * no_break / n),
            "| no retest (limit life / age) | %d | %.1f%% |" % (no_retest, 100 * no_retest / n),
            "| re-entered seed range (4h close) | %d | %.1f%% |" % (reentered, 100 * reentered / n),
            "| opposite side broke first | %d | %.1f%% |" % (opposite, 100 * opposite / n),
            "| FILLED | %d | %.1f%% |"
            % (int((outcomes == "FILLED").sum()), 100 * float((outcomes == "FILLED").mean())),
            "",
        ]

    lines += [
        "## Order-life cases (seed expiry fixed 30 × 4h)",
        "",
        "| Life | fills | fill% | net $ | avg R | med R | WR | PF |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for life in ORDER_LIFE_HOURS:
        df = trades_by_life.get(life, pd.DataFrame())
        s = _summarize_trades(df, "life_%dh" % life)
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        lines.append(
            "| %dh | %d | %.0f%% | %+.0f | %+.3f | %+.3f | %.0f%% | %s |"
            % (
                life,
                s["n_filled"],
                100 * s["fill_rate"],
                s["net_usd"],
                s["avg_R"],
                s["median_R"],
                100 * s["win_rate"],
                pf_s,
            )
        )
    lines += [
        "",
        "Primary decision book = **48h**. 24h = 1h-model control horizon; 72h = slower diagnostic.",
        "",
        "## S2 gate",
        "",
        "S2 (new post-seed confirmed 4h swing level retest) stays **DEFERRED** until S1 "
        "shows positive locked **dev and holdout** average R.",
        "",
    ]
    text = "\n".join(lines)
    (hub / "STAGE_B_TIMING.md").write_text(text, encoding="utf-8")
    return text


def write_summary(
    hub: Path,
    census: pd.DataFrame,
    timing: pd.DataFrame,
    summaries: List[dict],
    *,
    smoke: bool,
) -> str:
    n_events = len(census)
    n_elig = int(census["eligible"].sum()) if n_events else 0
    rej = census[census["eligible"] == 0]["reject_reason"].value_counts().to_dict() if n_events else {}
    n_break = int((timing["seed_expired_before_break"] == 0).sum()) if len(timing) else 0
    n_swing_bull = int((timing["first_confirmed_bullish_4h_swing_after_seed"] != "").sum()) if len(timing) else 0
    n_swing_bear = int((timing["first_confirmed_bearish_4h_swing_after_seed"] != "").sum()) if len(timing) else 0

    p_dev = next((s for s in summaries if s["label"] == "s1_4h_close_48h_dev"), None)
    p_ho = next((s for s in summaries if s["label"] == "s1_4h_close_48h_holdout"), None)
    p_all = next((s for s in summaries if s["label"] == "s1_4h_close_48h_ALL"), None)

    descriptive_only = bool(p_all and p_all["n_filled"] < 40)
    stance = "PENDING"
    if p_all and p_all["n_filled"] < 10:
        stance = "REJECT — viability too thin (<%d full-history fills)" % 10
    elif descriptive_only:
        stance = "DESCRIPTIVE ONLY — <%d full-history fills (1h model had 67)" % 40
    elif p_dev and (p_dev["net_usd"] <= 0 or p_dev["avg_R"] <= 0):
        stance = "REJECT S1 on locked dev (net/R ≤ 0)"
    elif p_dev and p_dev["avg_R"] > 0:
        if p_ho and p_ho["n_filled"] > 0 and p_ho["avg_R"] <= 0:
            stance = "RESEARCH — S1 positive locked dev, failed holdout avg R"
        elif p_ho and p_ho["n_filled"] > 0 and p_ho["avg_R"] > 0:
            stance = "RESEARCH — S1 positive locked avg R both slices (S2 gate OPEN; not promote)"
        else:
            stance = "RESEARCH — S1 positive locked dev; holdout thin"

    lines = [
        "# NQ WICK_REJECT 4h swing retest v1 — Stage A (S1)",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Hub:** `live/state/nq_wick_reject_4h_swing_retest_v1/`",
        "**strategy_id:** `%s`" % STRATEGY_ID,
        "**Model S1:** 4h WICK_REJECT seed → later **4h close** outside → limit retest **seed boundary** → "
        "opposite-edge stop ±1 tick → 0.5W/1W/2W 50/25/25.",
        "**Horizon:** seed expiry **30 × 4h**; primary order life **48h** (mechanical translation).",
        "**Compare-to:** 1h confirm + 24h life — 67 fills, dev avg R +0.177, holdout avg R −0.036.",
        "**Structure engine:** identical atlas `StructureProgramEngine_v1_existing` (no permissive redo).",
        ("**Mode:** SMOKE" if smoke else "**Mode:** FULL"),
        "",
        "## Phase 0 — timing census",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Atlas 4h WICK_REJECT (pen≥0.05) | %d |" % n_events,
        "| Eligible seeds (width/early/dedupe) | %d |" % n_elig,
        "| Rejected | %d |" % (n_events - n_elig),
        "| Any 4h close break before seed expiry | %d |" % n_break,
        "| Seed expired before break | %d |" % (n_elig - n_break),
        "| Atlas bullish CLOSE_BREAK in seed window | %d |" % n_swing_bull,
        "| Atlas bearish CLOSE_BREAK in seed window | %d |" % n_swing_bear,
        "",
        "Reject reasons: `%s`" % json.dumps(rej),
        "",
    ]
    if len(timing):
        broke = timing[timing["seed_expired_before_break"] == 0]
        lines += [
            "Among breaks: retest≤24/48/72h = **%d / %d / %d** of %d; "
            "both-sides-break flag = **%d**; break-expired-before-retest (48h) = **%d**."
            % (
                int(broke["retest_occurs_within_24h"].sum()) if len(broke) else 0,
                int(broke["retest_occurs_within_48h"].sum()) if len(broke) else 0,
                int(broke["retest_occurs_within_72h"].sum()) if len(broke) else 0,
                len(broke),
                int(timing["both_sides_break_before_fill"].sum()),
                int(broke["break_expired_before_retest"].sum()) if len(broke) else 0,
            ),
            "",
        ]

    lines += [
        "## Stage A — S1 primary (48h) vs 1h baseline",
        "",
        "| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | L/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        if "s1_4h_close_48h" not in s["label"] and "life_" not in s["label"]:
            continue
        if "life_" in s["label"] and not s["label"].endswith("_ALL"):
            continue
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        lines.append(
            "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.0f%% | %s | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d/%d |"
            % (
                s["label"],
                s["n_seeds"],
                s["n_filled"],
                100 * s["fill_rate"],
                s["net_usd"],
                s["avg_net"],
                100 * s["win_rate"],
                pf_s,
                s["avg_R"],
                s["median_R"],
                100 * s["stop_rate"],
                100 * s["hit_tp1_rate"],
                100 * s["hit_tp2_rate"],
                100 * s["hit_tp3_rate"],
                s["long_n"],
                s["short_n"],
            )
        )

    lines += [
        "",
        "## Stance",
        "",
        "**%s**" % stance,
        "",
        "- Identical seed population / atlas slice as the completed 1h model (expiry wall differs: 30 vs 20).",
        "- S2 not run this batch.",
        "- If fills < ~40–50, treat P&L as descriptive only.",
        "",
        "## Guardrails",
        "",
        "- No new 4h swing definition; atlas engine only.",
        "- No mixing S1/S2 levels.",
        "- No expiry tuning until first causal locked result known.",
        "- One trade per seed; no re-entry; no adds.",
        "",
    ]
    text = "\n".join(lines)
    (hub / "SUMMARY.md").write_text(text, encoding="utf-8")

    s2_gate = "OPEN" if (p_dev and p_ho and p_dev["avg_R"] > 0 and p_ho["avg_R"] > 0 and not descriptive_only) else "CLOSED"
    (hub / "STATUS.md").write_text(
        "\n".join(
            [
                "# Status — %s" % STRATEGY_ID,
                "",
                "**Hub:** `live/state/nq_wick_reject_4h_swing_retest_v1/`",
                "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
                "**Stance:** %s" % stance,
                "**S2 gate:** %s" % s2_gate,
                "",
                "| Stage | Status |",
                "|---|---|",
                "| Phase 0 timing census | DONE |",
                "| Stage A S1 (4h close + seed-boundary retest) | DONE |",
                "| Stage B timing/expiry + 24/48/72 | DONE |",
                "| Stage C S2 (new swing level) | DEFERRED |",
                "| StrategyPlugin | BLOCKED |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return stance


def build_email(hub: Path, stance: str, census: pd.DataFrame, summaries: List[dict], timing: pd.DataFrame) -> str:
    n_elig = int(census["eligible"].sum()) if not census.empty else 0
    p_all = next((s for s in summaries if s["label"] == "s1_4h_close_48h_ALL"), None)
    p_dev = next((s for s in summaries if s["label"] == "s1_4h_close_48h_dev"), None)
    p_ho = next((s for s in summaries if s["label"] == "s1_4h_close_48h_holdout"), None)
    n_break = int((timing["seed_expired_before_break"] == 0).sum()) if len(timing) else 0
    lines = [
        "potions: %s COMPLETE" % STRATEGY_ID,
        "",
        "Hub: %s" % hub,
        "Eligible seeds: %d / %d | 4h breaks: %d" % (n_elig, len(census), n_break),
        "Stance: %s" % stance,
        "",
        "S1 primary (48h) vs 1h baseline (67 fills, devR+0.177, hoR-0.036):",
    ]
    for s in (p_dev, p_ho, p_all):
        if not s:
            continue
        lines.append(
            "  %s: fills=%d net=%+.0f WR=%.0f%% PF=%.2f avgR=%+.3f"
            % (
                s["label"],
                s["n_filled"],
                s["net_usd"],
                100 * s["win_rate"],
                s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                s["avg_R"],
            )
        )
    lines += ["", "See SUMMARY.md + STAGE_B_TIMING.md. S2 deferred."]
    return "\n".join(lines)


def _s1_gate_open(summaries: List[dict]) -> bool:
    p_dev = next((s for s in summaries if s["label"] == "s1_4h_close_48h_dev"), None)
    p_ho = next((s for s in summaries if s["label"] == "s1_4h_close_48h_holdout"), None)
    p_all = next((s for s in summaries if s["label"] == "s1_4h_close_48h_ALL"), None)
    if not p_dev or not p_ho or not p_all:
        return False
    if p_all["n_filled"] < 40:
        return False
    return p_dev["avg_R"] > 0 and p_ho["avg_R"] > 0


def _append_s2_docs(hub: Path, s2_summaries: List[dict], s2_df: pd.DataFrame) -> str:
    p_dev = next((s for s in s2_summaries if s["label"] == "s2_new_swing_48h_dev"), None)
    p_ho = next((s for s in s2_summaries if s["label"] == "s2_new_swing_48h_holdout"), None)
    p_all = next((s for s in s2_summaries if s["label"] == "s2_new_swing_48h_ALL"), None)
    stance = "PENDING"
    if p_all and p_all["n_filled"] < 10:
        stance = "REJECT S2 — viability too thin"
    elif p_all and p_all["n_filled"] < 40:
        stance = "DESCRIPTIVE ONLY — S2 fills <40"
    elif p_dev and p_dev["avg_R"] <= 0:
        stance = "REJECT S2 on locked dev (avg R ≤ 0)"
    elif p_dev and p_dev["avg_R"] > 0 and p_ho and p_ho["avg_R"] <= 0:
        stance = "RESEARCH — S2 positive locked dev, failed holdout avg R"
    elif p_dev and p_ho and p_dev["avg_R"] > 0 and p_ho["avg_R"] > 0:
        stance = "RESEARCH — S2 positive locked avg R both slices (not promote)"
    else:
        stance = "RESEARCH — S2 inconclusive"

    lines = [
        "",
        "## Stage C — S2 (new post-seed 4h swing level)",
        "",
        "First atlas `CLOSE_BREAK` after seed; trade only if break_level outside seed; "
        "limit at **new swing level**; stop at opposite **original seed** boundary; 48h life.",
        "",
        "| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | L/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in s2_summaries:
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        lines.append(
            "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.0f%% | %s | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d/%d |"
            % (
                s["label"],
                s["n_seeds"],
                s["n_filled"],
                100 * s["fill_rate"],
                s["net_usd"],
                s["avg_net"],
                100 * s["win_rate"],
                pf_s,
                s["avg_R"],
                s["median_R"],
                100 * s["stop_rate"],
                100 * s["hit_tp1_rate"],
                100 * s["hit_tp2_rate"],
                100 * s["hit_tp3_rate"],
                s["long_n"],
                s["short_n"],
            )
        )
    reasons = (
        s2_df["terminal_reason"].fillna("").astype(str).value_counts().head(8).to_dict()
        if len(s2_df)
        else {}
    )
    lines += [
        "",
        "**S2 stance:** %s" % stance,
        "",
        "Non-fill / terminal reasons (top): `%s`" % json.dumps(reasons),
        "",
        "S1 and S2 are **not** combined — separate trial-ledger candidates.",
        "",
    ]
    summ_path = hub / "SUMMARY.md"
    if summ_path.exists():
        text = summ_path.read_text(encoding="utf-8")
        # strip prior Stage C block if re-run
        if "## Stage C — S2" in text:
            text = text.split("## Stage C — S2")[0].rstrip() + "\n"
        text = text.replace(
            "- S2 not run this batch.\n",
            "- S2 run as separate candidate (see Stage C).\n",
        )
        text += "\n".join(lines)
        summ_path.write_text(text, encoding="utf-8")
    status = hub / "STATUS.md"
    if status.exists():
        st = status.read_text(encoding="utf-8")
        st = st.replace("| Stage C S2 (new swing level) | DEFERRED |", "| Stage C S2 (new swing level) | DONE |")
        st = st.replace("**S2 gate:** OPEN", "**S2 gate:** OPEN (executed)")
        if "**S2 stance:**" not in st:
            st += "\n**S2 stance:** %s\n" % stance
        else:
            # refresh stance line
            lines_st = []
            for ln in st.splitlines():
                if ln.startswith("**S2 stance:**"):
                    lines_st.append("**S2 stance:** %s" % stance)
                else:
                    lines_st.append(ln)
            st = "\n".join(lines_st) + ("\n" if not st.endswith("\n") else "")
        status.write_text(st, encoding="utf-8")
    sb = hub / "STAGE_B_TIMING.md"
    if sb.exists():
        txt = sb.read_text(encoding="utf-8")
        txt = txt.replace(
            "S2 (new post-seed confirmed 4h swing level retest) stays **DEFERRED** until S1 "
            "shows positive locked **dev and holdout** average R.",
            "S2 gate opened after S1; Stage C executed — see SUMMARY Stage C / `trades_s2_48h.csv`.",
        )
        sb.write_text(txt, encoding="utf-8")
    return stance


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--s2", action="store_true", help="Also run S2 after S1 if gate opens")
    ap.add_argument("--s2-only", action="store_true", help="Run Stage C S2 only (requires prior S1 hub)")
    args = ap.parse_args()

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    if not args.s2_only:
        (hub / "PROGRESS.log").write_text("", encoding="utf-8")
    else:
        with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
            f.write("\n--- S2-only resume ---\n")

    (hub / "MODEL_CONTRACT.yaml").write_text(
        "\n".join(
            [
                "# Frozen research contract — separate family from 1h confirm model",
                "strategy_id: %s" % STRATEGY_ID,
                "created: %s" % datetime.now().strftime("%Y-%m-%d"),
                "seed:",
                "  source: existing frozen 4h WICK_REJECT (StructureProgramEngine_v1_existing)",
                "  penetration_min: 0.05 x 4h ATR20",
                "  width_allowed: [0.25, 2.00] x 4h ATR20",
                "  one_active_seed: true",
                "  seed_expiry_4h_bars: %d" % MAX_AGE_4H_BARS,
                "structure:",
                "  timeframe: 4h",
                "  swing_engine: StructureProgramEngine_v1_existing",
                "  use_only_completed_bars: true",
                "  note: identical atlas engine; no permissive redo",
                "model_S1:",
                "  break: completed 4h close outside seed high/low",
                "  entry: resting limit at seed boundary",
                "  stop: opposite seed boundary +/- 1 tick",
                "  targets: 0.5W / 1.0W / 2.0W @ 50/25/25",
                "  order_life_hours: 48",
                "  invalidate: completed 4h close back inside seed range",
                "  no_same_bar_fill: true",
                "  one_trade_per_seed: true",
                "  reentry: false",
                "model_S2:",
                "  status: DEFERRED until S1 positive locked avg R both slices",
                "  break: post-seed confirmed 4h swing/break outside seed",
                "  entry: limit at new swing/break level",
                "  stop: opposite original seed boundary",
                "order_life_cases_hours: [24, 48, 72]",
                "holdout: atlas slice column locked",
                "compare_to: nq_wick_reject_range_seed_retest (1h confirm, 24h life)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # refresh S2 status line in contract when running Stage C
    if args.s2_only or args.s2:
        raw = (hub / "MODEL_CONTRACT.yaml").read_text(encoding="utf-8")
        raw = raw.replace(
            "  status: DEFERRED until S1 positive locked avg R both slices",
            "  status: ACTIVE (Stage C) — first atlas CLOSE_BREAK outside seed",
        )
        (hub / "MODEL_CONTRACT.yaml").write_text(raw, encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug=STRATEGY_ID + ("_s2" if args.s2_only else ""),
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={
            "smoke": args.smoke,
            "model": "S2_new_swing" if args.s2_only else "S1_4h_close_seed_boundary_retest",
            "seed_expiry_4h_bars": MAX_AGE_4H_BARS,
            "order_life_hours": 48,
            "s2_only": args.s2_only,
        },
    )
    try:
        if args.email:
            if args.s2_only:
                start = (
                    "potions: %s Stage C S2 STARTED\n\nHub: %s\n"
                    "Post-seed atlas CLOSE_BREAK → limit at new swing level.\n" % (STRATEGY_ID, hub)
                )
                send_email(subject="potions: %s S2 STARTED" % STRATEGY_ID, body=start)
            else:
                start = (
                    "potions: %s STARTED\n\nHub: %s\n"
                    "Phase 0 → Stage A S1 (48h) → Stage B 24/48/72.\n"
                    "S2 via --s2 if gate opens.\n" % (STRATEGY_ID, hub)
                )
                (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
                send_email(subject="potions: %s STARTED" % STRATEGY_ID, body=start)

        _progress(hub, "load WICK_REJECT events")
        events = load_wick_events(smoke=args.smoke)
        _progress(hub, "events n=%d" % len(events))

        _progress(hub, "load atlas 4h CLOSE_BREAK swings")
        swings = load_atlas_4h_close_breaks()
        _progress(hub, "atlas 4h CLOSE_BREAK n=%d" % len(swings))

        _progress(hub, "load NQ 1m")
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        if args.smoke:
            edates = sorted(
                {_localize(pd.Timestamp(t)).date() for t in events["confirm_bar_close_ts"].tolist()}
            )
            days = sorted(gby.keys())
            keep = set()
            for d in edates:
                if d in days:
                    i = days.index(d)
                    keep.update(days[max(0, i - 12) : i + 20])
            gby = {d: gby[d] for d in days if d in keep}

        _progress(hub, "build RTH tape / 1h / 4h")
        tape, h1, h4, early = build_rth_tape(gby)
        _progress(hub, "tape=%d 1h=%d 4h=%d" % (len(tape), len(h1), len(h4)))

        _progress(hub, "make seeds (expiry=30×4h)")
        seeds, census = make_seeds_30(events, tape, h4, early)
        if not args.s2_only:
            census.to_csv(hub / "phase0_seed_census.csv", index=False)
        n_overlap = count_age_overlaps(seeds)
        _progress(hub, "eligible seeds=%d age_overlaps=%d" % (len(seeds), n_overlap))

        s2_stance = None
        s2_filled = 0
        s2_net = 0.0

        if args.s2_only:
            # load prior S1 summaries for email context
            prior = pd.read_csv(hub / "summary.csv") if (hub / "summary.csv").exists() else pd.DataFrame()
            _progress(hub, "Stage C S2 trades (48h)")
            rows = []
            for i, seed in enumerate(seeds):
                s = deepcopy(seed)
                rows.append(run_s2_trade(s, tape, h4, swings))
                if (i + 1) % 20 == 0:
                    _progress(hub, "s2 %d/%d" % (i + 1, len(seeds)))
            s2_df = pd.DataFrame(rows)
            s2_df.to_csv(hub / "trades_s2_48h.csv", index=False)
            s2_summaries = []
            for sl in ("dev", "holdout", "ALL"):
                sub = s2_df if sl == "ALL" else s2_df[s2_df["slice"] == sl]
                s2_summaries.append(_summarize_trades(sub, "s2_new_swing_48h_%s" % sl))
            # merge into summary.csv
            if len(prior):
                keep = prior[~prior["label"].astype(str).str.startswith("s2_")]
                merged = pd.concat([keep, pd.DataFrame(s2_summaries)], ignore_index=True)
            else:
                merged = pd.DataFrame(s2_summaries)
            merged.to_csv(hub / "summary.csv", index=False)
            s2_stance = _append_s2_docs(hub, s2_summaries, s2_df)
            s2_filled = int((s2_df["outcome"] == "FILLED").sum())
            s2_net = float(s2_df.loc[s2_df["outcome"] == "FILLED", "net_usd"].sum()) if s2_filled else 0.0
            body = (
                "potions: %s Stage C S2 COMPLETE\n\nHub: %s\nS2 stance: %s\n"
                "fills=%d net=%+.0f\n\n"
                % (STRATEGY_ID, hub, s2_stance, s2_filled, s2_net)
            )
            for s in s2_summaries:
                body += "  %s: fills=%d net=%+.0f WR=%.0f%% PF=%.2f avgR=%+.3f\n" % (
                    s["label"],
                    s["n_filled"],
                    s["net_usd"],
                    100 * s["win_rate"],
                    s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                    s["avg_R"],
                )
            body += "\nSeparate from S1 — not a combined chooser.\n"
            (hub / "EMAIL_S2.txt").write_text(body, encoding="utf-8")
            rc = {}
            if (hub / "RUN_COMPLETE.json").exists():
                rc = json.loads((hub / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
            rc.update(
                {
                    "s2_48h_fills": s2_filled,
                    "s2_48h_net_usd": s2_net,
                    "s2_stance": s2_stance,
                    "s2_deferred": False,
                    "s2_summaries": s2_summaries,
                }
            )
            (hub / "RUN_COMPLETE.json").write_text(json.dumps(rc, indent=2, default=str), encoding="utf-8")
            complete_run(
                rid,
                net_usd=s2_net,
                trades=s2_filled,
                meta={"s2_stance": s2_stance, "eligible_seeds": len(seeds)},
            )
            if args.email:
                send_email(subject="potions: %s S2 COMPLETE" % STRATEGY_ID, body=body)
                _progress(hub, "email sent")
            _progress(hub, "DONE S2 stance=%s fills=%d net=%+.0f" % (s2_stance, s2_filled, s2_net))
            return

        _progress(hub, "Phase 0 timing census")
        timing = phase0_timing_census(seeds, h4, tape, swings)
        timing.to_csv(hub / "phase0_timing_census.csv", index=False)
        n_break = int((timing["seed_expired_before_break"] == 0).sum())
        _progress(
            hub,
            "breaks=%d/%d retest48=%d"
            % (
                n_break,
                len(timing),
                int(timing.loc[timing["seed_expired_before_break"] == 0, "retest_occurs_within_48h"].sum())
                if n_break
                else 0,
            ),
        )

        trades_by_life: Dict[int, pd.DataFrame] = {}
        summaries: List[dict] = []
        for life in ORDER_LIFE_HOURS:
            _progress(hub, "Stage A/B S1 trades limit_life=%dh" % life)
            rows = []
            for i, seed in enumerate(seeds):
                s = deepcopy(seed)
                rows.append(
                    run_s1_trade(
                        s,
                        tape,
                        h4,
                        limit_life=pd.Timedelta(hours=life),
                        variant="s1_4h_close_%dh" % life,
                    )
                )
                if (i + 1) % 20 == 0:
                    _progress(hub, "life %dh %d/%d" % (life, i + 1, len(seeds)))
            df = pd.DataFrame(rows)
            df.to_csv(hub / ("trades_s1_%dh.csv" % life), index=False)
            trades_by_life[life] = df
            for sl in ("dev", "holdout", "ALL"):
                sub = df if sl == "ALL" else df[df["slice"] == sl]
                label = "s1_4h_close_%dh_%s" % (life, sl) if life == 48 else "life_%dh_%s" % (life, sl)
                summaries.append(_summarize_trades(sub, label))

        pd.DataFrame(summaries).to_csv(hub / "summary.csv", index=False)
        stage_b_timing_report(hub, timing, trades_by_life)
        stance = write_summary(hub, census, timing, summaries, smoke=args.smoke)

        run_s2 = args.s2 or _s1_gate_open(summaries)
        if run_s2 and _s1_gate_open(summaries):
            _progress(hub, "S1 gate OPEN — Stage C S2")
            rows = []
            for i, seed in enumerate(seeds):
                s = deepcopy(seed)
                rows.append(run_s2_trade(s, tape, h4, swings))
                if (i + 1) % 20 == 0:
                    _progress(hub, "s2 %d/%d" % (i + 1, len(seeds)))
            s2_df = pd.DataFrame(rows)
            s2_df.to_csv(hub / "trades_s2_48h.csv", index=False)
            s2_summaries = []
            for sl in ("dev", "holdout", "ALL"):
                sub = s2_df if sl == "ALL" else s2_df[s2_df["slice"] == sl]
                s2_summaries.append(_summarize_trades(sub, "s2_new_swing_48h_%s" % sl))
            summaries.extend(s2_summaries)
            pd.DataFrame(summaries).to_csv(hub / "summary.csv", index=False)
            s2_stance = _append_s2_docs(hub, s2_summaries, s2_df)
            s2_filled = int((s2_df["outcome"] == "FILLED").sum())
            s2_net = float(s2_df.loc[s2_df["outcome"] == "FILLED", "net_usd"].sum()) if s2_filled else 0.0
        elif run_s2:
            _progress(hub, "S2 requested but S1 gate CLOSED — skip")

        body = build_email(hub, stance, census, summaries, timing)
        if s2_stance:
            body += "\nS2 stance: %s fills=%d net=%+.0f\n" % (s2_stance, s2_filled, s2_net)
        else:
            body = body.replace("S2 deferred.", "S2 deferred (gate closed or not requested).")
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")

        t48 = trades_by_life[48]
        filled_n = int((t48["outcome"] == "FILLED").sum())
        net = float(t48.loc[t48["outcome"] == "FILLED", "net_usd"].sum()) if filled_n else 0.0
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "strategy_id": STRATEGY_ID,
                    "eligible_seeds": len(seeds),
                    "s1_48h_fills": filled_n,
                    "s1_48h_net_usd": net,
                    "stance": stance,
                    "smoke": args.smoke,
                    "s2_deferred": s2_stance is None,
                    "s2_stance": s2_stance,
                    "s2_48h_fills": s2_filled,
                    "s2_48h_net_usd": s2_net,
                    "summaries": summaries,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        complete_run(
            rid,
            net_usd=net,
            trades=filled_n,
            meta={
                "stance": stance,
                "eligible_seeds": len(seeds),
                "s2_deferred": s2_stance is None,
                "s2_stance": s2_stance,
            },
        )
        if args.email:
            send_email(subject="potions: %s COMPLETE" % STRATEGY_ID, body=body)
            _progress(hub, "email sent")
        _progress(hub, "DONE stance=%s fills=%d net=%+.0f" % (stance, filled_n, net))
    except Exception as e:
        fail_run(rid, notes=str(e))
        err = traceback.format_exc()
        _progress(hub, "FAILED: %s" % e)
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: %s FAILED" % STRATEGY_ID,
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        raise


if __name__ == "__main__":
    main()
