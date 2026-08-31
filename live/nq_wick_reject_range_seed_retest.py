"""NQ 4h WICK_REJECT → range-seed → 1h break → limit retest (Phases 0–3).

Frozen model (not a directional fade):
  seed wick-reject 4h high/low → wait 1h close outside → rest limit at
  broken boundary → stop at opposite edge ±1 tick → scale 50/25/25 at
  0.5W / 1W / 2W. One trade per seed; no re-entry; no scale-in.

Hub: live/state/nq_wick_reject_range_seed_retest/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_range_seed_retest --email
  python -m live.nq_wick_reject_range_seed_retest --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import HUB as ATLAS_HUB
from .nq_structure_change_event_study import TICK
from .run_ledger import begin_run, complete_run, fail_run
from .structure_program_st_chart_bias_4h import to_4h
from .structure_program_st_chart_bias_levels import to_1h
from .structure_program_st_study import rth_slice
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_wick_reject_range_seed_retest"
NY = "America/New_York"
PEN_PRIMARY = 0.05
WIDTH_MIN_ATR = 0.25
WIDTH_MAX_ATR = 2.00
MAX_AGE_4H_BARS = 20
LIMIT_LIFE = pd.Timedelta(hours=24)
POINT_VALUE = 20.0
FEE = 1.50
STOP_BUFFER_TICKS = 1
MIN_SESSION_BARS = 300  # early-close / holiday exclude
SLIPPAGE_TICKS = 1  # controls only (market entries)


def _localize(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _is_early_close(rth: pd.DataFrame) -> bool:
    if rth is None or rth.empty:
        return True
    if len(rth) < MIN_SESSION_BARS:
        return True
    last_t = _localize(rth.index[-1]).time()
    return last_t < time(15, 45)


def load_wick_events(smoke: bool = False) -> pd.DataFrame:
    df = pd.read_csv(ATLAS_HUB / "structure_events.csv")
    m = (
        (df["event_type"] == "WICK_REJECT")
        & (df["structure_timeframe"] == "4h")
        & (df["event_family"] == "invalidation")
        & (pd.to_numeric(df["min_pen_ATR"], errors="coerce") == PEN_PRIMARY)
    )
    out = df.loc[m].copy()
    out = out.sort_values(["confirm_bar_close_ts", "event_id"]).reset_index(drop=True)
    if smoke:
        out = out.head(12)
    return out


def build_rth_tape(gby: Dict[date, pd.DataFrame]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[date, bool]]:
    """Return (1m RTH tape, 1h, 4h, early_close_by_day)."""
    frames = []
    early: Dict[date, bool] = {}
    for d in sorted(gby.keys()):
        rth = rth_slice(gby[d])
        early[d] = _is_early_close(rth)
        if rth is not None and not rth.empty:
            frames.append(rth)
    if not frames:
        empty = pd.DataFrame(columns=["open", "high", "low", "close"])
        return empty, empty, empty, early
    tape = pd.concat(frames)
    tape = tape[~tape.index.duplicated(keep="last")].sort_index()
    h1 = to_1h(tape)
    h4 = to_4h(tape)
    return tape, h1, h4, early


def _bar_slice(tape: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    t0 = _localize(t0)
    t1 = _localize(t1)
    # confirm window is [open, close); include last minute of bar if indexed at close-1m
    return tape[(tape.index >= t0) & (tape.index < t1)]


def _first_1m_after(tape: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Timestamp]:
    if tape is None or tape.empty:
        return None
    ts = _localize(ts)
    pos = tape.index.searchsorted(ts, side="right")
    if pos >= len(tape.index):
        return None
    return _localize(tape.index[pos])


def _atr_1m(tape: pd.DataFrame, asof: pd.Timestamp, n: int = 20) -> float:
    asof = _localize(asof)
    pos = tape.index.searchsorted(asof, side="left")
    if pos < 2:
        return float("nan")
    sub = tape.iloc[max(0, pos - n - 1) : pos]
    if len(sub) < 3:
        return float("nan")
    hi = sub["high"].to_numpy(dtype=float)
    lo = sub["low"].to_numpy(dtype=float)
    cl = sub["close"].to_numpy(dtype=float)
    prev = np.roll(cl, 1)
    prev[0] = cl[0]
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - prev), np.abs(lo - prev)))
    return float(np.mean(tr[-n:])) if len(tr) else float("nan")


@dataclass
class Seed:
    seed_id: str
    event_id: str
    slice: str
    high: float
    low: float
    width: float
    atr20_4h: float
    atr20_1m: float
    seed_close_ts: pd.Timestamp
    available_at: pd.Timestamp
    expires_at: pd.Timestamp  # close of 20th subsequent 4h bar (or wall fallback)
    state: str = "RANGE_SEEDED"
    side: str = ""
    break_confirm_ts: Optional[pd.Timestamp] = None
    order_live_at: Optional[pd.Timestamp] = None
    entry_limit: Optional[float] = None
    terminal_reason: str = ""
    # diagnostics
    first_break_side: str = ""
    both_sides_broke: int = 0
    retest_eligible: int = 0
    time_seed_to_break_min: float = float("nan")
    time_break_to_fill_min: float = float("nan")
    persist_1: int = 0
    persist_2: int = 0
    persist_4: int = 0
    reentry_inside: int = 0
    hit_0_5w: int = 0
    hit_1w: int = 0
    hit_2w: int = 0
    retest_hold: int = 0


def _expire_ts_from_4h(h4: pd.DataFrame, seed_close: pd.Timestamp) -> pd.Timestamp:
    seed_close = _localize(seed_close)
    if h4 is None or h4.empty:
        return seed_close + pd.Timedelta(hours=4 * MAX_AGE_4H_BARS)
    # 4h index = bar open (label=left); bar completes at open+4h
    opens = h4.index[h4.index > seed_close - pd.Timedelta(seconds=1)]
    # bars whose open >= seed_close are subsequent; also include in-progress next
    subsequent = [o for o in opens if _localize(o) >= seed_close]
    if len(subsequent) >= MAX_AGE_4H_BARS:
        o20 = _localize(subsequent[MAX_AGE_4H_BARS - 1])
        return o20 + pd.Timedelta(hours=4)
    return seed_close + pd.Timedelta(hours=4 * MAX_AGE_4H_BARS)


def make_seeds(
    events: pd.DataFrame,
    tape: pd.DataFrame,
    h4: pd.DataFrame,
    early: Dict[date, bool],
) -> Tuple[List[Seed], pd.DataFrame]:
    """Build eligible seeds (dedupe same confirm bar). One-active cancel applied later in time order."""
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

        expires = _expire_ts_from_4h(h4, close_ts)
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


def count_age_overlaps(seeds: List[Seed]) -> int:
    """How many seeds have another seed available_at inside their [available, expires) window."""
    ordered = sorted(seeds, key=lambda s: s.available_at)
    n = 0
    for i, seed in enumerate(ordered):
        for nxt in ordered[i + 1 :]:
            if nxt.available_at >= seed.expires_at:
                break
            n += 1
            break
    return n


def _1h_bars_after(h1: pd.DataFrame, after_ts: pd.Timestamp, until: pd.Timestamp) -> pd.DataFrame:
    after_ts = _localize(after_ts)
    until = _localize(until)
    if h1 is None or h1.empty:
        return pd.DataFrame()
    # bar end = open + 1h; only use completed bars whose end > available_at
    outs = []
    for ts, row in h1.iterrows():
        o = _localize(ts)
        end = o + pd.Timedelta(hours=1)
        if end <= after_ts:
            continue
        if o >= until:  # bar starts at/after expiry wall
            break
        outs.append((end, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
    if not outs:
        return pd.DataFrame()
    df = pd.DataFrame(outs, columns=["end_ts", "open", "high", "low", "close"])
    return df


def simulate_seed_path(seed: Seed, h1: pd.DataFrame, tape: pd.DataFrame) -> Seed:
    """Phase 0/1 path + arm RETEST_PENDING / INVALIDATED / EXPIRED (no fill yet)."""
    bars = _1h_bars_after(h1, seed.available_at, seed.expires_at + pd.Timedelta(hours=1))
    broke_high = False
    broke_low = False
    outside_streak = 0
    side = ""

    for _, b in bars.iterrows():
        end = _localize(b["end_ts"])
        if end > seed.expires_at and seed.state == "RANGE_SEEDED":
            seed.state = "EXPIRED"
            seed.terminal_reason = "max_age_4h"
            break
        cl = float(b["close"])

        if seed.state == "RANGE_SEEDED":
            if cl > seed.high:
                seed.side = "LONG"
                side = "LONG"
                seed.break_confirm_ts = end
                seed.order_live_at = _first_1m_after(tape, end)
                seed.entry_limit = seed.high
                seed.state = "RETEST_PENDING"
                seed.first_break_side = "high"
                broke_high = True
                seed.time_seed_to_break_min = (end - seed.available_at).total_seconds() / 60.0
                outside_streak = 1
            elif cl < seed.low:
                seed.side = "SHORT"
                side = "SHORT"
                seed.break_confirm_ts = end
                seed.order_live_at = _first_1m_after(tape, end)
                seed.entry_limit = seed.low
                seed.state = "RETEST_PENDING"
                seed.first_break_side = "low"
                broke_low = True
                seed.time_seed_to_break_min = (end - seed.available_at).total_seconds() / 60.0
                outside_streak = 1
            continue

        if seed.state == "RETEST_PENDING":
            # persistence / re-entry diagnostics on subsequent 1h closes
            if side == "LONG":
                if cl > seed.high:
                    outside_streak += 1
                elif cl < seed.high:
                    seed.reentry_inside = 1
                    # invalidate: close back inside (or through)
                    seed.state = "INVALIDATED"
                    seed.terminal_reason = "1h_close_back_inside"
                    break
                if cl < seed.low:
                    broke_low = True
                    seed.state = "INVALIDATED"
                    seed.terminal_reason = "opposite_1h_break"
                    break
            else:
                if cl < seed.low:
                    outside_streak += 1
                elif cl > seed.low:
                    seed.reentry_inside = 1
                    seed.state = "INVALIDATED"
                    seed.terminal_reason = "1h_close_back_inside"
                    break
                if cl > seed.high:
                    broke_high = True
                    seed.state = "INVALIDATED"
                    seed.terminal_reason = "opposite_1h_break"
                    break

            if end >= (seed.break_confirm_ts + LIMIT_LIFE):
                seed.state = "EXPIRED"
                seed.terminal_reason = "limit_life_24h"
                break
            if end > seed.expires_at:
                seed.state = "EXPIRED"
                seed.terminal_reason = "max_age_4h"
                break

    if seed.state == "RANGE_SEEDED":
        seed.state = "EXPIRED"
        seed.terminal_reason = seed.terminal_reason or "max_age_no_break"

    seed.persist_1 = int(outside_streak >= 1)
    seed.persist_2 = int(outside_streak >= 2)
    seed.persist_4 = int(outside_streak >= 4)
    seed.both_sides_broke = int(broke_high and broke_low)

    # forward expansion after first break (path study, even if later invalidated)
    if seed.break_confirm_ts is not None:
        _forward_expansion(seed, tape)

    return seed


def _forward_expansion(seed: Seed, tape: pd.DataFrame) -> None:
    """After break confirm, did price reach 0.5W/1W/2W in break direction before opposite stop?"""
    if seed.break_confirm_ts is None or tape is None or tape.empty:
        return
    t0 = _first_1m_after(tape, seed.break_confirm_ts)
    if t0 is None:
        return
    pos = tape.index.searchsorted(t0, side="left")
    w = seed.width
    if seed.side == "LONG":
        tp05, tp1, tp2 = seed.high + 0.5 * w, seed.high + 1.0 * w, seed.high + 2.0 * w
        stop = seed.low
    else:
        tp05, tp1, tp2 = seed.low - 0.5 * w, seed.low - 1.0 * w, seed.low - 2.0 * w
        stop = seed.high
    hit05 = hit1 = hit2 = 0
    retest_seen = 0
    retest_held = 0
    for j in range(pos, min(pos + 60 * 24 * 5, len(tape))):  # cap ~5 RTH-days of minutes
        ts = _localize(tape.index[j])
        if ts > seed.expires_at:
            break
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        if seed.side == "LONG":
            if l <= seed.high:
                retest_seen = 1
            if retest_seen and h > seed.high:
                retest_held = 1
            if l <= stop:
                break
            if h >= tp05:
                hit05 = 1
            if h >= tp1:
                hit1 = 1
            if h >= tp2:
                hit2 = 1
                break
        else:
            if h >= seed.low:
                retest_seen = 1
            if retest_seen and l < seed.low:
                retest_held = 1
            if h >= stop:
                break
            if l <= tp05:
                hit05 = 1
            if l <= tp1:
                hit1 = 1
            if l <= tp2:
                hit2 = 1
                break
    seed.hit_0_5w = hit05
    seed.hit_1w = hit1
    seed.hit_2w = hit2
    seed.retest_eligible = retest_seen
    seed.retest_hold = retest_held


def _adverse_stop_fill(side: str, stop: float, bar_open: float) -> Tuple[float, int]:
    if side == "LONG":
        if bar_open <= stop:
            return float(bar_open), 1
        return float(stop), 0
    if bar_open >= stop:
        return float(bar_open), 1
    return float(stop), 0


def _manage_scaleout(
    tape: pd.DataFrame,
    *,
    side: str,
    fill_ts: pd.Timestamp,
    entry: float,
    stop: float,
    targets: Sequence[float],
    qtys: Sequence[float],
    hard_end_ts: Optional[pd.Timestamp] = None,
) -> dict:
    """Stop-first 1m management with 50/25/25 scale-out."""
    idx = tape.index
    fill_ts = _localize(fill_ts)
    hard_end_ts = _localize(hard_end_ts) if hard_end_ts is not None else None
    pos0 = idx.searchsorted(fill_ts, side="right")
    remaining = 1.0
    next_tp = 0
    legs = []
    mfe = 0.0
    mae = 0.0
    gap_any = 0
    for j in range(pos0, len(idx)):
        ts = _localize(idx[j])
        o = float(tape["open"].iloc[j])
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        if hard_end_ts is not None and ts >= hard_end_ts and remaining > 1e-12:
            legs.append((ts, o, remaining, "expiry_flat"))
            remaining = 0.0
            break
        if side == "LONG":
            mfe = max(mfe, h - entry)
            mae = max(mae, entry - l)
            stopped = l <= stop
            if stopped and remaining > 1e-12:
                px, gap = _adverse_stop_fill(side, stop, o)
                gap_any |= gap
                legs.append((ts, px, remaining, "stop"))
                remaining = 0.0
                break
            while next_tp < len(targets) and remaining > 1e-12 and h >= targets[next_tp]:
                q = min(qtys[next_tp], remaining)
                legs.append((ts, float(targets[next_tp]), q, "TP%d" % (next_tp + 1)))
                remaining -= q
                next_tp += 1
        else:
            mfe = max(mfe, entry - l)
            mae = max(mae, h - entry)
            stopped = h >= stop
            if stopped and remaining > 1e-12:
                px, gap = _adverse_stop_fill(side, stop, o)
                gap_any |= gap
                legs.append((ts, px, remaining, "stop"))
                remaining = 0.0
                break
            while next_tp < len(targets) and remaining > 1e-12 and l <= targets[next_tp]:
                q = min(qtys[next_tp], remaining)
                legs.append((ts, float(targets[next_tp]), q, "TP%d" % (next_tp + 1)))
                remaining -= q
                next_tp += 1
        if remaining <= 1e-12:
            break
    if remaining > 1e-12:
        last_ts = _localize(idx[-1])
        last_c = float(tape["close"].iloc[-1])
        legs.append((last_ts, last_c, remaining, "tape_end"))
        remaining = 0.0

    net_pts = 0.0
    fees = FEE  # entry
    exit_ts = fill_ts
    reasons = []
    for ts, px, q, reason in legs:
        pts = (px - entry) if side == "LONG" else (entry - px)
        net_pts += pts * q
        fees += FEE * q
        exit_ts = ts
        reasons.append("%s@%.2f×%.2f" % (reason, px, q))
    risk = abs(entry - stop)
    r_mult = net_pts / risk if risk > 0 else 0.0
    net_usd = net_pts * POINT_VALUE - fees
    hit = {1: 0, 2: 0, 3: 0}
    for _, _, _, reason in legs:
        if reason.startswith("TP"):
            hit[int(reason[2])] = 1
    return {
        "exit_ts": exit_ts,
        "exit_reason": ";".join(reasons),
        "net_pts": net_pts,
        "net_usd": net_usd,
        "r_multiple": r_mult,
        "risk_pts": risk,
        "gap_through_stop": gap_any,
        "mfe_pts": mfe,
        "mae_pts": mae,
        "hit_tp1": hit[1],
        "hit_tp2": hit[2],
        "hit_tp3": hit[3],
        "stopped": int(any(leg[3] == "stop" for leg in legs)),
        "n_legs": len(legs),
    }


def _try_limit_fill(
    tape: pd.DataFrame,
    *,
    side: str,
    limit: float,
    live_at: pd.Timestamp,
    deadline: pd.Timestamp,
    invalidate_check,
) -> Optional[Tuple[pd.Timestamp, float]]:
    """Resting limit fill: first 1m that trades through limit while order live."""
    live_at = _localize(live_at)
    deadline = _localize(deadline)
    pos = tape.index.searchsorted(live_at, side="left")
    if pos < len(tape.index) and _localize(tape.index[pos]) < live_at:
        pos += 1
    for j in range(pos, len(tape)):
        ts = _localize(tape.index[j])
        if ts > deadline:
            return None
        if invalidate_check is not None and invalidate_check(ts, tape.iloc[j]):
            return None
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        if side == "LONG" and l <= limit:
            # fill at limit (resting); if gap open through, fill at open
            o = float(tape["open"].iloc[j])
            px = float(o) if o < limit else float(limit)
            return ts, px
        if side == "SHORT" and h >= limit:
            o = float(tape["open"].iloc[j])
            px = float(o) if o > limit else float(limit)
            return ts, px
    return None


def run_primary_trade(seed: Seed, tape: pd.DataFrame, h1: pd.DataFrame) -> Optional[dict]:
    """Primary: limit retest after 1h break confirm."""
    # re-walk to arm, but also need fill before invalidation — combined path
    bars = _1h_bars_after(h1, seed.available_at, seed.expires_at + pd.Timedelta(hours=1))
    side = ""
    break_ts = None
    live_at = None
    limit = None
    armed = False

    for _, b in bars.iterrows():
        end = _localize(b["end_ts"])
        cl = float(b["close"])
        if not armed:
            if end > seed.expires_at:
                return _seed_outcome_row(seed, "EXPIRED", "max_age_no_break", None)
            if cl > seed.high:
                side, break_ts, limit = "LONG", end, seed.high
                live_at = _first_1m_after(tape, end)
                armed = True
            elif cl < seed.low:
                side, break_ts, limit = "SHORT", end, seed.low
                live_at = _first_1m_after(tape, end)
                armed = True
            else:
                continue
            if live_at is None:
                return _seed_outcome_row(seed, "EXPIRED", "no_1m_after_break", None)
            deadline = min(break_ts + LIMIT_LIFE, seed.expires_at)

            # scan 1m for fill until next invalidating 1h close or deadline
            fill = _fill_until_invalidate(
                tape,
                h1_bars=bars,
                break_end=end,
                side=side,
                limit=float(limit),
                live_at=live_at,
                deadline=deadline,
                seed=seed,
            )
            if fill is None:
                return _seed_outcome_row(
                    seed,
                    seed.state if seed.state in ("INVALIDATED", "EXPIRED") else "EXPIRED",
                    seed.terminal_reason or "no_fill",
                    None,
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
            caus = int(seed.available_at < live_at <= fill_ts < mg["exit_ts"])
            return {
                "variant": "primary_limit_retest",
                "seed_id": seed.seed_id,
                "event_id": seed.event_id,
                "slice": seed.slice,
                "side": side,
                "range_high": seed.high,
                "range_low": seed.low,
                "width": seed.width,
                "available_at": seed.available_at.isoformat(),
                "break_confirm_ts": break_ts.isoformat(),
                "order_live_at": live_at.isoformat(),
                "fill_ts": fill_ts.isoformat(),
                "entry": entry,
                "stop": stop,
                "tp1": targets[0],
                "tp2": targets[1],
                "tp3": targets[2],
                "time_seed_to_break_min": (break_ts - seed.available_at).total_seconds() / 60.0,
                "time_break_to_fill_min": (fill_ts - break_ts).total_seconds() / 60.0,
                "time_fill_to_exit_min": (mg["exit_ts"] - fill_ts).total_seconds() / 60.0,
                "causality_ok": caus,
                **{k: mg[k] for k in mg if k != "exit_ts"},
                "exit_ts": mg["exit_ts"].isoformat(),
                "outcome": "FILLED",
                "terminal_reason": mg["exit_reason"],
            }
    return _seed_outcome_row(seed, "EXPIRED", "max_age_no_break", None)


def _fill_until_invalidate(
    tape: pd.DataFrame,
    *,
    h1_bars: pd.DataFrame,
    break_end: pd.Timestamp,
    side: str,
    limit: float,
    live_at: pd.Timestamp,
    deadline: pd.Timestamp,
    seed: Seed,
) -> Optional[Tuple[pd.Timestamp, float]]:
    """Fill resting limit; cancel on 1h close back inside / opposite break / deadline."""
    # map invalidation timestamps from subsequent 1h closes
    inv_ts = None
    inv_reason = ""
    for _, b in h1_bars.iterrows():
        end = _localize(b["end_ts"])
        if end <= break_end:
            continue
        cl = float(b["close"])
        if side == "LONG":
            if cl < seed.high:
                inv_ts, inv_reason = end, "1h_close_back_inside"
                break
            if cl < seed.low:
                inv_ts, inv_reason = end, "opposite_1h_break"
                break
        else:
            if cl > seed.low:
                inv_ts, inv_reason = end, "1h_close_back_inside"
                break
            if cl > seed.high:
                inv_ts, inv_reason = end, "opposite_1h_break"
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


def _seed_outcome_row(seed: Seed, outcome: str, reason: str, trade: Optional[dict]) -> dict:
    base = {
        "variant": "primary_limit_retest",
        "seed_id": seed.seed_id,
        "event_id": seed.event_id,
        "slice": seed.slice,
        "side": seed.side or "",
        "range_high": seed.high,
        "range_low": seed.low,
        "width": seed.width,
        "available_at": seed.available_at.isoformat(),
        "break_confirm_ts": seed.break_confirm_ts.isoformat() if seed.break_confirm_ts else "",
        "order_live_at": seed.order_live_at.isoformat() if seed.order_live_at else "",
        "fill_ts": "",
        "entry": np.nan,
        "stop": np.nan,
        "tp1": np.nan,
        "tp2": np.nan,
        "tp3": np.nan,
        "time_seed_to_break_min": seed.time_seed_to_break_min,
        "time_break_to_fill_min": np.nan,
        "time_fill_to_exit_min": np.nan,
        "causality_ok": 1,
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
    if trade:
        base.update(trade)
    return base


def run_control_immediate(seed: Seed, tape: pd.DataFrame, h1: pd.DataFrame) -> Optional[dict]:
    """Control: market next 1m open after 1h break confirm (no retest)."""
    return _run_break_entry(seed, tape, h1, variant="ctrl_immediate_break", mode="market_open")


def run_control_marketable(seed: Seed, tape: pd.DataFrame, h1: pd.DataFrame) -> Optional[dict]:
    """Control: fill at boundary price immediately after break (no path retest)."""
    return _run_break_entry(seed, tape, h1, variant="ctrl_marketable_boundary", mode="boundary")


def _run_break_entry(
    seed: Seed,
    tape: pd.DataFrame,
    h1: pd.DataFrame,
    *,
    variant: str,
    mode: str,
) -> Optional[dict]:
    bars = _1h_bars_after(h1, seed.available_at, seed.expires_at + pd.Timedelta(hours=1))
    for _, b in bars.iterrows():
        end = _localize(b["end_ts"])
        if end > seed.expires_at:
            break
        cl = float(b["close"])
        side = ""
        if cl > seed.high:
            side = "LONG"
        elif cl < seed.low:
            side = "SHORT"
        else:
            continue
        live_at = _first_1m_after(tape, end)
        if live_at is None:
            break
        pos = tape.index.searchsorted(live_at, side="left")
        if pos >= len(tape):
            break
        if _localize(tape.index[pos]) < live_at:
            pos += 1
        if pos >= len(tape):
            break
        fill_ts = _localize(tape.index[pos])
        o = float(tape["open"].iloc[pos])
        slip = SLIPPAGE_TICKS * TICK
        if mode == "market_open":
            entry = o + slip if side == "LONG" else o - slip
        else:
            # synthetic fill at boundary (diagnostic: break direction + range geometry, no retest)
            entry = seed.high if side == "LONG" else seed.low
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
        caus = int(seed.available_at < live_at <= fill_ts < mg["exit_ts"])
        return {
            "variant": variant,
            "seed_id": seed.seed_id,
            "event_id": seed.event_id,
            "slice": seed.slice,
            "side": side,
            "range_high": seed.high,
            "range_low": seed.low,
            "width": seed.width,
            "available_at": seed.available_at.isoformat(),
            "break_confirm_ts": end.isoformat(),
            "order_live_at": live_at.isoformat(),
            "fill_ts": fill_ts.isoformat(),
            "entry": entry,
            "stop": stop,
            "tp1": targets[0],
            "tp2": targets[1],
            "tp3": targets[2],
            "time_seed_to_break_min": (end - seed.available_at).total_seconds() / 60.0,
            "time_break_to_fill_min": (fill_ts - end).total_seconds() / 60.0,
            "time_fill_to_exit_min": (mg["exit_ts"] - fill_ts).total_seconds() / 60.0,
            "causality_ok": caus,
            **{k: mg[k] for k in mg if k != "exit_ts"},
            "exit_ts": mg["exit_ts"].isoformat(),
            "outcome": "FILLED",
            "terminal_reason": mg["exit_reason"],
        }
    return {
        "variant": variant,
        "seed_id": seed.seed_id,
        "event_id": seed.event_id,
        "slice": seed.slice,
        "side": "",
        "outcome": "EXPIRED",
        "terminal_reason": "max_age_no_break",
        "net_usd": 0.0,
        "r_multiple": 0.0,
        "causality_ok": 1,
        "stopped": 0,
        "hit_tp1": 0,
        "hit_tp2": 0,
        "hit_tp3": 0,
        "gap_through_stop": 0,
        "long_n": 0,
        "time_break_to_fill_min": np.nan,
        "time_fill_to_exit_min": np.nan,
    }


def _summarize_trades(df: pd.DataFrame, label: str) -> dict:
    filled = df[df["outcome"] == "FILLED"] if "outcome" in df.columns else df
    n = len(filled)
    if n == 0:
        return {
            "label": label,
            "n_seeds": int(len(df)),
            "n_filled": 0,
            "fill_rate": 0.0,
            "net_usd": 0.0,
            "avg_net": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_R": 0.0,
            "median_R": 0.0,
            "stop_rate": 0.0,
            "hit_tp1_rate": 0.0,
            "hit_tp2_rate": 0.0,
            "hit_tp3_rate": 0.0,
            "gap_through_n": 0,
            "causality_ok_n": 0,
            "long_n": 0,
            "short_n": 0,
            "long_net": 0.0,
            "short_net": 0.0,
            "top1_share": 0.0,
            "top3_share": 0.0,
            "top5_share": 0.0,
            "avg_time_fill_min": float("nan"),
            "avg_time_exit_min": float("nan"),
        }
    nets = filled["net_usd"].astype(float)
    wins = nets[nets > 0].sum()
    losses = -nets[nets < 0].sum()
    pf = float(wins / losses) if losses > 0 else (float("inf") if wins > 0 else 0.0)
    abs_sorted = nets.abs().sort_values(ascending=False)
    tot = float(nets.abs().sum()) or 1.0
    r = filled["r_multiple"].astype(float)
    return {
        "label": label,
        "n_seeds": int(len(df)),
        "n_filled": n,
        "fill_rate": n / len(df) if len(df) else 0.0,
        "net_usd": float(nets.sum()),
        "avg_net": float(nets.mean()),
        "win_rate": float((nets > 0).mean()),
        "profit_factor": pf,
        "avg_R": float(r.mean()),
        "median_R": float(r.median()),
        "stop_rate": float(filled["stopped"].mean()) if "stopped" in filled else 0.0,
        "hit_tp1_rate": float(filled["hit_tp1"].mean()) if "hit_tp1" in filled else 0.0,
        "hit_tp2_rate": float(filled["hit_tp2"].mean()) if "hit_tp2" in filled else 0.0,
        "hit_tp3_rate": float(filled["hit_tp3"].mean()) if "hit_tp3" in filled else 0.0,
        "gap_through_n": int(filled["gap_through_stop"].sum()) if "gap_through_stop" in filled else 0,
        "causality_ok_n": int(filled["causality_ok"].sum()) if "causality_ok" in filled else 0,
        "long_n": int((filled["side"] == "LONG").sum()),
        "short_n": int((filled["side"] == "SHORT").sum()),
        "long_net": float(filled.loc[filled["side"] == "LONG", "net_usd"].sum()),
        "short_net": float(filled.loc[filled["side"] == "SHORT", "net_usd"].sum()),
        "top1_share": float(abs_sorted.iloc[:1].sum() / tot),
        "top3_share": float(abs_sorted.iloc[:3].sum() / tot),
        "top5_share": float(abs_sorted.iloc[:5].sum() / tot),
        "avg_time_fill_min": float(filled["time_break_to_fill_min"].mean())
        if "time_break_to_fill_min" in filled
        else float("nan"),
        "avg_time_exit_min": float(filled["time_fill_to_exit_min"].mean())
        if "time_fill_to_exit_min" in filled
        else float("nan"),
    }


def write_summary_docs(
    hub: Path,
    census: pd.DataFrame,
    seeds_df: pd.DataFrame,
    summaries: List[dict],
    *,
    smoke: bool,
) -> str:
    elig = census[census["eligible"] == 1] if not census.empty else census
    n_events = len(census)
    n_elig = int(census["eligible"].sum()) if not census.empty else 0
    rej = census[census["eligible"] == 0]["reject_reason"].value_counts().to_dict() if n_events else {}

    path_n = len(seeds_df)
    n_break = int((seeds_df["first_break_side"] != "").sum()) if path_n else 0
    n_high = int((seeds_df["first_break_side"] == "high").sum()) if path_n else 0
    n_low = int((seeds_df["first_break_side"] == "low").sum()) if path_n else 0
    n_both = int(seeds_df["both_sides_broke"].sum()) if path_n else 0
    n_retest = int(seeds_df["retest_eligible"].sum()) if path_n else 0
    n_expire_nb = int(((seeds_df["state"] == "EXPIRED") & (seeds_df["first_break_side"] == "")).sum()) if path_n else 0

    primary = [s for s in summaries if s["label"].startswith("primary_")]
    stance = "PENDING"
    p_dev = next((s for s in summaries if s["label"] == "primary_limit_retest_dev"), None)
    p_ho = next((s for s in summaries if s["label"] == "primary_limit_retest_holdout"), None)
    p_all = next((s for s in summaries if s["label"] == "primary_limit_retest_ALL"), None)
    if p_dev and p_dev["n_filled"] < 10:
        stance = "REJECT — viability too thin (<%d fills on locked dev)" % 10
    elif p_dev and (p_dev["net_usd"] <= 0 or p_dev["avg_R"] <= 0):
        stance = "REJECT base model on locked dev (net/R ≤ 0)"
    elif p_dev and p_dev["net_usd"] > 0 and p_dev["avg_R"] > 0:
        if p_ho and p_ho["n_filled"] > 0 and (p_ho["net_usd"] <= 0 or p_ho["avg_R"] <= 0):
            stance = "RESEARCH — positive locked dev, failed holdout"
        elif p_ho and p_ho["n_filled"] > 0 and p_ho["net_usd"] > 0 and p_ho["avg_R"] > 0:
            stance = "RESEARCH — positive locked 75/25 (not promote; Engine plugin + causality next)"
        else:
            stance = "RESEARCH — positive locked dev; holdout thin"

    lines = [
        "# NQ WICK_REJECT range-seed breakout–retest",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Hub:** `live/state/nq_wick_reject_range_seed_retest/`",
        "**Model:** 4h WICK_REJECT seeds range → 1h close break → limit retest → opposite-edge stop → 0.5W/1W/2W 50/25/25.",
        "**Execution:** RTH 1m stop-first, gap-through stops, limit fill at boundary, $1.50/leg fee, NQ $20/pt.",
        "**Holdout:** atlas slice (earliest ~75% dev / latest ~25% holdout) — locked read.",
        ("**Mode:** SMOKE" if smoke else "**Mode:** FULL"),
        "",
        "## Phase 0 — viability census",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Atlas 4h WICK_REJECT (pen≥0.05) | %d |" % n_events,
        "| Eligible seeds (width/early/dedupe) | %d |" % n_elig,
        "| Rejected | %d |" % (n_events - n_elig),
        "",
        "Reject reasons: `%s`" % json.dumps(rej),
        "",
    ]
    if n_elig:
        lines += [
            "Width distribution (eligible):",
            "",
            "| Stat | points | ticks | ×4h ATR | ×1m ATR |",
            "|---|---:|---:|---:|---:|",
        ]
        for stat, fn in [("min", "min"), ("p25", lambda s: s.quantile(0.25)), ("median", "median"), ("p75", lambda s: s.quantile(0.75)), ("max", "max")]:
            sub = elig
            if callable(fn):
                wp, wt, wa, w1 = fn(sub["range_width"]), fn(sub["width_ticks"]), fn(sub["width_ATR"]), fn(sub["width_1m_ATR"])
            else:
                wp, wt, wa, w1 = sub["range_width"].agg(fn), sub["width_ticks"].agg(fn), sub["width_ATR"].agg(fn), sub["width_1m_ATR"].agg(fn)
            lines.append("| %s | %.2f | %.1f | %.3f | %.2f |" % (stat, wp, wt, wa, w1 if w1 == w1 else float("nan")))
        lines.append("")

    lines += [
        "## Phase 1 — directional revelation (eligible seeds)",
        "",
        "| Outcome | n | rate |",
        "|---|---:|---:|",
        "| Expire with no 1h break | %d | %.1f%% |" % (n_expire_nb, 100 * n_expire_nb / path_n if path_n else 0),
        "| First break high | %d | %.1f%% |" % (n_high, 100 * n_high / path_n if path_n else 0),
        "| First break low | %d | %.1f%% |" % (n_low, 100 * n_low / path_n if path_n else 0),
        "| Any 1h break | %d | %.1f%% |" % (n_break, 100 * n_break / path_n if path_n else 0),
        "| Both sides broke (path flag) | %d | %.1f%% |" % (n_both, 100 * n_both / path_n if path_n else 0),
        "| Retest touch after break | %d | %.1f%% |" % (n_retest, 100 * n_retest / path_n if path_n else 0),
        "",
    ]
    if path_n and n_break:
        br = seeds_df[seeds_df["first_break_side"] != ""]
        lines += [
            "Among first-breaks: persist≥1/2/4 1h closes outside = **%d / %d / %d**; "
            "re-entry inside rate = **%.1f%%**; hit 0.5W/1W/2W = **%d / %d / %d**; "
            "retest-hold = **%d**."
            % (
                int(br["persist_1"].sum()),
                int(br["persist_2"].sum()),
                int(br["persist_4"].sum()),
                100 * float(br["reentry_inside"].mean()),
                int(br["hit_0_5w"].sum()),
                int(br["hit_1w"].sum()),
                int(br["hit_2w"].sum()),
                int(br["retest_hold"].sum()),
            ),
            "",
        ]

    lines += [
        "## Phase 2–3 — locked primary + controls",
        "",
        "| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap | L/S n |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        lines.append(
            "| %s | %d | %d | %.0f%% | %+.0f | %+.0f | %.0f%% | %s | %+.3f | %+.3f | %.0f%% | %.0f/%.0f/%.0f | %d | %d/%d |"
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
                s["gap_through_n"],
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
        "Primary decision uses locked **dev** only; holdout is a frozen read.",
        "Do not promote to StrategyPlugin until Engine seed-state machine + cancel/replace are verified.",
        "",
        "## Concentration (primary ALL fills)",
        "",
    ]
    if p_all and p_all["n_filled"]:
        lines.append(
            "Top1/3/5 |net| share: **%.1f%% / %.1f%% / %.1f%%**."
            % (100 * p_all["top1_share"], 100 * p_all["top3_share"], 100 * p_all["top5_share"])
        )
    else:
        lines.append("No primary fills.")

    lines += [
        "",
        "## Guardrails",
        "",
        "- No structure-bias / RSI / TOD / SMT filters.",
        "- No target optimization; W-multiples frozen.",
        "- One seed per market; one trade per seed; no DCA / re-entry.",
        "- Early-close sessions excluded; width 0.25–2.00 × 4h ATR20.",
        "",
    ]
    text = "\n".join(lines)
    (hub / "SUMMARY.md").write_text(text, encoding="utf-8")
    (hub / "STATUS.md").write_text(
        "\n".join(
            [
                "# Status — NQ WICK_REJECT range-seed retest",
                "",
                "**Hub:** `live/state/nq_wick_reject_range_seed_retest/`",
                "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
                "**Stance:** %s" % stance,
                "",
                "| Phase | Status |",
                "|---|---|",
                "| 0 viability census | DONE |",
                "| 1 directional revelation | DONE |",
                "| 2 locked primary replay | DONE |",
                "| 3 fixed controls | DONE |",
                "| 4 bounded robustness | DEFERRED (diagnostics only if primary survives) |",
                "| StrategyPlugin | BLOCKED until stance promotes |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return stance


def build_email(hub: Path, summaries: List[dict], stance: str, census: pd.DataFrame) -> str:
    n_elig = int(census["eligible"].sum()) if not census.empty else 0
    lines = [
        "potions: NQ WICK_REJECT range-seed retest COMPLETE",
        "",
        "Hub: %s" % hub,
        "Eligible seeds: %d / %d atlas events" % (n_elig, len(census)),
        "Stance: %s" % stance,
        "",
        "Key books:",
    ]
    for s in summaries:
        if not s["label"].endswith(("_dev", "_holdout", "_ALL")):
            continue
        if "primary" not in s["label"] and "ctrl_" not in s["label"]:
            continue
        if s["label"].endswith("_ALL") and "ctrl_" in s["label"]:
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
    lines.append("")
    lines.append("See SUMMARY.md.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug="nq_wick_reject_range_seed_retest",
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={"smoke": args.smoke, "model": "range_seed_1h_break_limit_retest"},
    )
    try:
        if args.email:
            start = (
                "potions: NQ WICK_REJECT range-seed retest STARTED\n\n"
                "Hub: %s\nPhases 0–3 (census → revelation → primary → controls).\n"
                % hub
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            send_email(subject="potions: NQ WICK_REJECT range-seed retest STARTED", body=start)

        _progress(hub, "load WICK_REJECT events")
        events = load_wick_events(smoke=args.smoke)
        _progress(hub, "events n=%d" % len(events))

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
                    keep.update(days[max(0, i - 8) : i + 12])
            gby = {d: gby[d] for d in days if d in keep}

        _progress(hub, "build RTH tape / 1h / 4h")
        tape, h1, h4, early = build_rth_tape(gby)
        _progress(hub, "tape=%d 1h=%d 4h=%d" % (len(tape), len(h1), len(h4)))

        _progress(hub, "Phase 0 seed census")
        seeds, census = make_seeds(events, tape, h4, early)
        census.to_csv(hub / "phase0_census.csv", index=False)
        n_overlap = count_age_overlaps(seeds)
        _progress(hub, "eligible seeds=%d age_overlaps=%d" % (len(seeds), n_overlap))

        _progress(hub, "Phase 1 path study")
        path_rows = []
        for i, seed in enumerate(seeds):
            # copy for path diagnostics (state machine mutates)
            s = Seed(**{**seed.__dict__})
            simulate_seed_path(s, h1, tape)
            path_rows.append(
                {
                    "seed_id": s.seed_id,
                    "event_id": s.event_id,
                    "slice": s.slice,
                    "high": s.high,
                    "low": s.low,
                    "width": s.width,
                    "width_ATR": s.width / s.atr20_4h if s.atr20_4h else np.nan,
                    "state": s.state,
                    "terminal_reason": s.terminal_reason,
                    "first_break_side": s.first_break_side,
                    "both_sides_broke": s.both_sides_broke,
                    "retest_eligible": s.retest_eligible,
                    "retest_hold": s.retest_hold,
                    "time_seed_to_break_min": s.time_seed_to_break_min,
                    "persist_1": s.persist_1,
                    "persist_2": s.persist_2,
                    "persist_4": s.persist_4,
                    "reentry_inside": s.reentry_inside,
                    "hit_0_5w": s.hit_0_5w,
                    "hit_1w": s.hit_1w,
                    "hit_2w": s.hit_2w,
                }
            )
            if (i + 1) % 20 == 0:
                _progress(hub, "path %d/%d" % (i + 1, len(seeds)))
        seeds_df = pd.DataFrame(path_rows)
        seeds_df.to_csv(hub / "phase1_path.csv", index=False)

        _progress(hub, "Phase 2 primary + Phase 3 controls")
        primary_rows = []
        ctrl_imm = []
        ctrl_mkt = []
        for i, seed in enumerate(seeds):
            # fresh copies (path study mutated duplicates only)
            primary_rows.append(run_primary_trade(seed, tape, h1))
            ctrl_imm.append(run_control_immediate(seed, tape, h1))
            ctrl_mkt.append(run_control_marketable(seed, tape, h1))
            if (i + 1) % 20 == 0:
                _progress(hub, "trades %d/%d" % (i + 1, len(seeds)))

        trades_p = pd.DataFrame([r for r in primary_rows if r])
        trades_i = pd.DataFrame([r for r in ctrl_imm if r])
        trades_m = pd.DataFrame([r for r in ctrl_mkt if r])
        trades_p.to_csv(hub / "trades_primary.csv", index=False)
        trades_i.to_csv(hub / "trades_ctrl_immediate.csv", index=False)
        trades_m.to_csv(hub / "trades_ctrl_marketable.csv", index=False)

        summaries: List[dict] = []
        for name, df in [
            ("primary_limit_retest", trades_p),
            ("ctrl_immediate_break", trades_i),
            ("ctrl_marketable_boundary", trades_m),
        ]:
            for sl in ("dev", "holdout", "ALL"):
                sub = df if sl == "ALL" else df[df["slice"] == sl] if "slice" in df.columns else df
                summaries.append(_summarize_trades(sub, "%s_%s" % (name, sl)))
        pd.DataFrame(summaries).to_csv(hub / "summary.csv", index=False)

        stance = write_summary_docs(hub, census, seeds_df, summaries, smoke=args.smoke)
        body = build_email(hub, summaries, stance, census)
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")

        filled_n = int((trades_p["outcome"] == "FILLED").sum()) if len(trades_p) else 0
        net = float(trades_p.loc[trades_p["outcome"] == "FILLED", "net_usd"].sum()) if filled_n else 0.0
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "eligible_seeds": len(seeds),
                    "primary_fills": filled_n,
                    "primary_net_usd": net,
                    "stance": stance,
                    "smoke": args.smoke,
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
            meta={"stance": stance, "eligible_seeds": len(seeds)},
        )
        if args.email:
            send_email(subject="potions: NQ WICK_REJECT range-seed retest COMPLETE", body=body)
            _progress(hub, "email sent")
        _progress(hub, "DONE stance=%s fills=%d net=%+.0f" % (stance, filled_n, net))
    except Exception as e:
        fail_run(rid, notes=str(e))
        err = traceback.format_exc()
        _progress(hub, "FAILED: %s" % e)
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: NQ WICK_REJECT range-seed retest FAILED",
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        raise


if __name__ == "__main__":
    main()
