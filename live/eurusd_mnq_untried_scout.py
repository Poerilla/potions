"""Scout EURUSD ports of MNQ research ideas not yet tried on FX.

Wave A: NY ORB entry variants. Wave B: London / calendar structure.
Survivors (pass_scout_gate) are listed for broker-like follow-up.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .eurusd_mnq_untried_helpers import (
    HALF_SPREAD,
    NY_TZ,
    OR_END,
    OR_START,
    PIP,
    POINT_VALUE,
    RTH_END,
    TICK,
    Trade,
    eod_path,
    exit_long,
    exit_short,
    load_window,
    london_box,
    ny_sessions,
    opening_range,
    path_after,
    pnl_usd,
    prior_ma_bull_map,
    resample_5m_rth,
    rth_day,
    summarize,
)


REPO = Path(__file__).resolve().parents[1]
OUT_DEFAULT = REPO / "live" / "state" / "eurusd_mnq_untried_scout"
PHI_INV = (math.sqrt(5.0) - 1.0) / 2.0


# ---------- Wave A ----------


def _v2b_first_touch(
    path: pd.DataFrame, rh: float, rl: float
) -> Optional[Tuple[str, float, pd.Timestamp]]:
    trig_long = rh + TICK
    trig_short = rl - TICK
    for ts, bar in path.iterrows():
        if float(bar["high"]) >= trig_long:
            return "long", trig_long + HALF_SPREAD, pd.Timestamp(ts)
        if float(bar["low"]) <= trig_short:
            return "short", trig_short - HALF_SPREAD, pd.Timestamp(ts)
    return None


def sim_adaptive_v2b_only(one_m: pd.DataFrame, ma_bull: Dict[date, bool]) -> List[Trade]:
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        if not ma_bull.get(day, False):
            continue
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        path = eod_path(path_after(day_1m, None))
        hit = _v2b_first_touch(path, rh, rl)
        if hit is None:
            continue
        side, entry, ets = hit
        rest = path[path.index > ets]
        if rest.empty:
            continue
        if side == "long":
            stop, target = rl, rh + rv
            exit_px, reason, xts = exit_long(rest, entry, stop, target)
        else:
            stop, target = rh, rl - rv
            exit_px, reason, xts = exit_short(rest, entry, stop, target)
        trades.append(
            Trade("A1_adaptive_v2b_only", side, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
        )
    return trades


def sim_adaptive_v2b_v2d(one_m: pd.DataFrame, ma_bull: Dict[date, bool]) -> List[Trade]:
    """MA bull → v2b breakout; else v2d fade (break then limit at boundary)."""
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        path = eod_path(path_after(day_1m, None))
        if ma_bull.get(day, False):
            hit = _v2b_first_touch(path, rh, rl)
            if hit is None:
                continue
            side, entry, ets = hit
            rest = path[path.index > ets]
            if rest.empty:
                continue
            if side == "long":
                exit_px, reason, xts = exit_long(rest, entry, rl, rh + rv)
            else:
                exit_px, reason, xts = exit_short(rest, entry, rh, rl - rv)
            trades.append(
                Trade("A2_adaptive_v2b_v2d", side, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
            )
            continue
        # v2d fade: wait breakout opposite then limit at boundary
        broken: Optional[str] = None
        for ts, bar in path.iterrows():
            if broken is None:
                if float(bar["high"]) >= rh + TICK:
                    broken = "long_brk"
                elif float(bar["low"]) <= rl - TICK:
                    broken = "short_brk"
                continue
            if broken == "long_brk" and float(bar["high"]) >= rh - TICK:
                # fade short at RH
                entry = rh - HALF_SPREAD
                ets = pd.Timestamp(ts)
                rest = path[path.index > ets]
                if rest.empty:
                    break
                exit_px, reason, xts = exit_short(rest, entry, rh + rv, rl)
                trades.append(
                    Trade(
                        "A2_adaptive_v2b_v2d",
                        "short",
                        ets,
                        xts,
                        entry,
                        exit_px,
                        1.0,
                        reason,
                        pnl_usd("short", entry, exit_px),
                    )
                )
                break
            if broken == "short_brk" and float(bar["low"]) <= rl + TICK:
                entry = rl + HALF_SPREAD
                ets = pd.Timestamp(ts)
                rest = path[path.index > ets]
                if rest.empty:
                    break
                exit_px, reason, xts = exit_long(rest, entry, rl - rv, rh)
                trades.append(
                    Trade(
                        "A2_adaptive_v2b_v2d",
                        "long",
                        ets,
                        xts,
                        entry,
                        exit_px,
                        1.0,
                        reason,
                        pnl_usd("long", entry, exit_px),
                    )
                )
                break
    return trades


def sim_clean_break(one_m: pd.DataFrame) -> List[Trade]:
    """First 5m close beyond OR after 09:45; stop opposite OR; TP 2R; bullish+bearish."""
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        m5 = resample_5m_rth(day_1m)
        m5 = m5[m5.index.time >= OR_END]
        side = None
        brk_ts = None
        for ts, bar in m5.iterrows():
            if float(bar["close"]) > rh + TICK:
                side, brk_ts = "long", pd.Timestamp(ts)
                break
            if float(bar["close"]) < rl - TICK:
                side, brk_ts = "short", pd.Timestamp(ts)
                break
        if side is None or brk_ts is None:
            continue
        # enter at next 1m open after 5m close
        rest = eod_path(day_1m[day_1m.index > brk_ts + pd.Timedelta(minutes=5)])
        if rest.empty:
            rest = eod_path(day_1m[day_1m.index > brk_ts])
        if rest.empty:
            continue
        entry = float(rest.iloc[0]["open"]) + (HALF_SPREAD if side == "long" else -HALF_SPREAD)
        ets = pd.Timestamp(rest.index[0])
        path = rest.iloc[1:] if len(rest) > 1 else rest
        if side == "long":
            exit_px, reason, xts = exit_long(path, entry, rl, entry + 2 * rv)
        else:
            exit_px, reason, xts = exit_short(path, entry, rh, entry - 2 * rv)
        trades.append(
            Trade("A3_clean_break", side, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
        )
    return trades


def sim_v1b_pullback(one_m: pd.DataFrame) -> List[Trade]:
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        m5 = resample_5m_rth(day_1m)
        trade_bars = m5[m5.index.time >= OR_END]
        phase = "wait_brk"
        direction = None
        n = 0
        for ts, bar in trade_bars.iterrows():
            if n >= 2 and phase != "in":
                break
            h, l, c = float(bar["high"]), float(bar["low"]), float(bar["close"])
            if phase == "wait_fill":
                filled = False
                entry = target = stop = None
                if direction == "long" and l <= rh:
                    entry, target, stop = rh + HALF_SPREAD, rh + rv, rl
                    filled = True
                elif direction == "short" and h >= rl:
                    entry, target, stop = rl - HALF_SPREAD, rl - rv, rh
                    filled = True
                if filled:
                    phase = "in"
                    # resolve on remaining 1m after this 5m bar
                    rest = eod_path(day_1m[day_1m.index > ts + pd.Timedelta(minutes=5)])
                    if rest.empty:
                        rest = eod_path(day_1m[day_1m.index > ts])
                    if rest.empty:
                        phase = "wait_brk"
                        continue
                    if direction == "long":
                        exit_px, reason, xts = exit_long(rest, entry, stop, target)
                    else:
                        exit_px, reason, xts = exit_short(rest, entry, stop, target)
                    trades.append(
                        Trade(
                            "A4_v1b_pullback",
                            direction,
                            pd.Timestamp(ts),
                            xts,
                            entry,
                            exit_px,
                            1.0,
                            reason,
                            pnl_usd(direction, entry, exit_px),
                        )
                    )
                    n += 1
                    phase = "wait_brk"
                    direction = None
                else:
                    if direction == "long" and c < rl:
                        direction = "short"
                    elif direction == "short" and c > rh:
                        direction = "long"
                continue
            if phase == "wait_brk":
                if c > rh + TICK:
                    direction, phase = "long", "wait_fill"
                elif c < rl - TICK:
                    direction, phase = "short", "wait_fill"
    return trades


def sim_open_limit(one_m: pd.DataFrame) -> List[Trade]:
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, session_open = orb
        rv = rh - rl
        m5 = resample_5m_rth(day_1m)
        trade_bars = m5[m5.index.time >= OR_END]
        n = 0
        armed: Optional[str] = None
        for ts, bar in trade_bars.iterrows():
            if n >= 2:
                break
            c = float(bar["close"])
            if armed is None:
                if c > rh + TICK:
                    armed = "long"
                elif c < rl - TICK:
                    armed = "short"
                else:
                    continue
            # limit at session open; fill on subsequent 1m
            rest = eod_path(day_1m[day_1m.index > ts + pd.Timedelta(minutes=5)])
            if rest.empty:
                continue
            filled = False
            entry = ets = None
            for t2, b2 in rest.iterrows():
                if armed == "long" and float(b2["low"]) <= session_open:
                    entry = session_open + HALF_SPREAD
                    ets = pd.Timestamp(t2)
                    filled = True
                    break
                if armed == "short" and float(b2["high"]) >= session_open:
                    entry = session_open - HALF_SPREAD
                    ets = pd.Timestamp(t2)
                    filled = True
                    break
            if not filled:
                armed = None
                continue
            path = rest[rest.index > ets]
            if path.empty:
                armed = None
                continue
            if armed == "long":
                stop, target = session_open - rv, rh + rv
                exit_px, reason, xts = exit_long(path, entry, stop, target)
            else:
                stop, target = session_open + rv, rl - rv
                exit_px, reason, xts = exit_short(path, entry, stop, target)
            trades.append(
                Trade("A5_orb_open_limit", armed, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(armed, entry, exit_px))
            )
            n += 1
            armed = None
    return trades


def sim_breakout_close_limit(one_m: pd.DataFrame) -> List[Trade]:
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        m5 = resample_5m_rth(day_1m)
        trade_bars = m5[m5.index.time >= OR_END]
        n = 0
        for ts, bar in trade_bars.iterrows():
            if n >= 2:
                break
            c = float(bar["close"])
            side = None
            if c > rh + TICK:
                side = "long"
            elif c < rl - TICK:
                side = "short"
            if side is None:
                continue
            limit_px = c
            rest = eod_path(day_1m[day_1m.index > ts + pd.Timedelta(minutes=5)])
            filled = False
            entry = ets = None
            for t2, b2 in rest.iterrows():
                if side == "long" and float(b2["low"]) <= limit_px:
                    entry = limit_px + HALF_SPREAD
                    ets = pd.Timestamp(t2)
                    filled = True
                    break
                if side == "short" and float(b2["high"]) >= limit_px:
                    entry = limit_px - HALF_SPREAD
                    ets = pd.Timestamp(t2)
                    filled = True
                    break
            if not filled:
                continue
            path = rest[rest.index > ets]
            if path.empty:
                continue
            if side == "long":
                exit_px, reason, xts = exit_long(path, entry, rl, rh + rv)
            else:
                exit_px, reason, xts = exit_short(path, entry, rh, rl - rv)
            trades.append(
                Trade(
                    "A6_breakout_close_limit",
                    side,
                    ets,
                    xts,
                    entry,
                    exit_px,
                    1.0,
                    reason,
                    pnl_usd(side, entry, exit_px),
                )
            )
            n += 1
    return trades


def sim_swept_orb(one_m: pd.DataFrame) -> List[Trade]:
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        m5 = resample_5m_rth(day_1m)
        bars = list(m5[m5.index.time >= OR_END].iterrows())
        i = 0
        while i < len(bars):
            ts1, b1 = bars[i]
            c1 = float(b1["close"])
            brk1 = None
            if c1 > rh + TICK:
                brk1 = "long"
            elif c1 < rl - TICK:
                brk1 = "short"
            if brk1 is None:
                i += 1
                continue
            # need 1m inside OR after brk1 ends before opposite break
            after1 = day_1m[day_1m.index > ts1 + pd.Timedelta(minutes=5)]
            reclaimed = False
            j = i + 1
            brk2 = None
            ts2 = None
            c2 = None
            while j < len(bars):
                tsj, bj = bars[j]
                # check reclaim on 1m between brk1 end and this bar start
                mid = after1[(after1.index < tsj)]
                if not mid.empty and ((mid["low"] >= rl) & (mid["high"] <= rh)).any():
                    reclaimed = True
                cj = float(bj["close"])
                if reclaimed:
                    if brk1 == "long" and cj < rl - TICK:
                        brk2, ts2, c2 = "short", tsj, cj
                        break
                    if brk1 == "short" and cj > rh + TICK:
                        brk2, ts2, c2 = "long", tsj, cj
                        break
                j += 1
            if brk2 is None:
                break
            # skip if classic OR target of brk1 hit before fill
            pre = day_1m[(day_1m.index > ts1 + pd.Timedelta(minutes=5)) & (day_1m.index <= ts2)]
            if brk1 == "long" and not pre.empty and float(pre["high"].max()) >= rh + rv:
                i = j + 1
                continue
            if brk1 == "short" and not pre.empty and float(pre["low"].min()) <= rl - rv:
                i = j + 1
                continue
            limit_px = float(c2)
            rest = eod_path(day_1m[day_1m.index > ts2 + pd.Timedelta(minutes=5)])
            entry = ets = None
            for t2, b2 in rest.iterrows():
                if brk2 == "long" and float(b2["low"]) <= limit_px:
                    entry, ets = limit_px + HALF_SPREAD, pd.Timestamp(t2)
                    break
                if brk2 == "short" and float(b2["high"]) >= limit_px:
                    entry, ets = limit_px - HALF_SPREAD, pd.Timestamp(t2)
                    break
            if entry is None:
                i = j + 1
                continue
            path = rest[rest.index > ets]
            if path.empty:
                i = j + 1
                continue
            # 1 unit scout (MNQ used 2); SL -1R TP +1R
            if brk2 == "long":
                exit_px, reason, xts = exit_long(path, entry, entry - rv, entry + rv)
            else:
                exit_px, reason, xts = exit_short(path, entry, entry + rv, entry - rv)
            trades.append(
                Trade("A7_swept_orb", brk2, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(brk2, entry, exit_px))
            )
            i = j + 1
    return trades


# ---------- Wave B ----------


def sim_fib62_london(one_m: pd.DataFrame) -> List[Trade]:
    trades: List[Trade] = []
    for day in ny_sessions(one_m):
        # need pre-RTH for london box — slice from midnight NY
        lo = NY_TZ.localize(datetime.combine(day, time(0, 0)))
        hi = NY_TZ.localize(datetime.combine(day, RTH_END))
        day_full = one_m[(one_m.index >= lo) & (one_m.index < hi)]
        box = london_box(day_full, day)
        if box is None:
            continue
        L, H = box
        if H - L < 5 * PIP:
            continue
        entry_lvl = H - PHI_INV * (H - L)
        rth = rth_day(one_m, day)
        path = eod_path(rth)
        armed = False
        aborted = False
        ets = entry = None
        for ts, bar in path.iterrows():
            hi_b, lo_b = float(bar["high"]), float(bar["low"])
            if not armed:
                if hi_b >= H - TICK:
                    armed = True
                continue
            if lo_b <= L + TICK:
                aborted = True
                break
            if lo_b <= entry_lvl:
                entry = entry_lvl + HALF_SPREAD
                ets = pd.Timestamp(ts)
                break
        if aborted or entry is None:
            continue
        rest = path[path.index > ets]
        if rest.empty:
            continue
        exit_px, reason, xts = exit_long(rest, entry, L, H)
        trades.append(
            Trade("B1_fib62_london_long", "long", ets, xts, entry, exit_px, 1.0, reason, pnl_usd("long", entry, exit_px))
        )
    return trades


def sim_prior_month_sweep_daily(daily: pd.DataFrame) -> List[Trade]:
    """Simplified daily: sweep prior-month extreme then reclaim through month mid → fade back."""
    trades: List[Trade] = []
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)
    d["ym"] = d["date"].dt.to_period("M")
    months = list(d["ym"].unique())
    for mi in range(1, len(months)):
        prev = d[d["ym"] == months[mi - 1]]
        cur = d[d["ym"] == months[mi]].reset_index(drop=True)
        if prev.empty or len(cur) < 5:
            continue
        pm_h, pm_l = float(prev["high"].max()), float(prev["low"].min())
        # long: sweep pm_l then close back above pm_l
        swept_i = None
        for i, row in cur.iterrows():
            if float(row["low"]) <= pm_l:
                swept_i = i
                break
        if swept_i is not None:
            for j in range(swept_i + 1, len(cur)):
                row = cur.iloc[j]
                if float(row["close"]) > pm_l:
                    entry = float(row["close"]) + HALF_SPREAD
                    stop = float(cur.iloc[swept_i]["low"])
                    target = pm_l + 2 * (entry - stop)
                    # walk forward
                    exit_px, reason = entry, "eod"
                    xts = pd.Timestamp(row["date"])
                    for k in range(j + 1, len(cur)):
                        r2 = cur.iloc[k]
                        if float(r2["low"]) <= stop:
                            exit_px, reason = stop - HALF_SPREAD, "stop"
                            xts = pd.Timestamp(r2["date"])
                            break
                        if float(r2["high"]) >= target:
                            exit_px, reason = target - HALF_SPREAD, "target"
                            xts = pd.Timestamp(r2["date"])
                            break
                        exit_px = float(r2["close"]) - HALF_SPREAD
                        xts = pd.Timestamp(r2["date"])
                    trades.append(
                        Trade(
                            "B2_pm_sweep_daily_long",
                            "long",
                            pd.Timestamp(row["date"]),
                            xts,
                            entry,
                            exit_px,
                            1.0,
                            reason,
                            pnl_usd("long", entry, exit_px),
                        )
                    )
                    break
        # short: sweep pm_h then close back below
        swept_i = None
        for i, row in cur.iterrows():
            if float(row["high"]) >= pm_h:
                swept_i = i
                break
        if swept_i is not None:
            for j in range(swept_i + 1, len(cur)):
                row = cur.iloc[j]
                if float(row["close"]) < pm_h:
                    entry = float(row["close"]) - HALF_SPREAD
                    stop = float(cur.iloc[swept_i]["high"])
                    target = pm_h - 2 * (stop - entry)
                    exit_px, reason = entry, "eod"
                    xts = pd.Timestamp(row["date"])
                    for k in range(j + 1, len(cur)):
                        r2 = cur.iloc[k]
                        if float(r2["high"]) >= stop:
                            exit_px, reason = stop + HALF_SPREAD, "stop"
                            xts = pd.Timestamp(r2["date"])
                            break
                        if float(r2["low"]) <= target:
                            exit_px, reason = target + HALF_SPREAD, "target"
                            xts = pd.Timestamp(r2["date"])
                            break
                        exit_px = float(r2["close"]) + HALF_SPREAD
                        xts = pd.Timestamp(r2["date"])
                    trades.append(
                        Trade(
                            "B2_pm_sweep_daily_short",
                            "short",
                            pd.Timestamp(row["date"]),
                            xts,
                            entry,
                            exit_px,
                            1.0,
                            reason,
                            pnl_usd("short", entry, exit_px),
                        )
                    )
                    break
    return trades


def _session_open_px(one_m: pd.DataFrame, day: date, open_time: time, tz) -> Optional[float]:
    ts = tz.localize(datetime.combine(day, open_time))
    # first bar at/after open
    sub = one_m[one_m.index >= ts]
    if sub.empty:
        return None
    # same calendar day in that tz
    bar = sub.iloc[0]
    if bar.name.astimezone(tz).date() != day:
        return None
    return float(bar["open"])


def sim_midnight_flip(one_m: pd.DataFrame, label: str, open_tz, open_time: time) -> List[Trade]:
    """Hourly close flip vs session open; flatten 16:00 NY."""
    trades: List[Trade] = []
    # build hourly
    h1 = (
        one_m.resample("1h", label="left", closed="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna(subset=["open"])
    )
    for day in ny_sessions(one_m):
        m = _session_open_px(one_m, day, open_time, open_tz)
        if m is None:
            continue
        day_end = NY_TZ.localize(datetime.combine(day, RTH_END))
        day_start = open_tz.localize(datetime.combine(day, open_time))
        bars = h1[(h1.index >= day_start) & (h1.index < day_end)]
        side = None
        entry = ets = None
        for ts, bar in bars.iterrows():
            c = float(bar["close"])
            want = "long" if c > m else "short" if c < m else None
            if want is None:
                continue
            if side is None:
                side = want
                entry = c + (HALF_SPREAD if side == "long" else -HALF_SPREAD)
                ets = pd.Timestamp(ts)
                continue
            if want != side:
                # flip
                exit_px = c - (HALF_SPREAD if side == "long" else -HALF_SPREAD)
                trades.append(
                    Trade(
                        label,
                        side,
                        ets,
                        pd.Timestamp(ts),
                        entry,
                        exit_px,
                        1.0,
                        "flip",
                        pnl_usd(side, entry, exit_px),
                    )
                )
                side = want
                entry = c + (HALF_SPREAD if side == "long" else -HALF_SPREAD)
                ets = pd.Timestamp(ts)
        if side is not None and ets is not None:
            # flatten last RTH close
            rth = rth_day(one_m, day)
            if rth.empty:
                continue
            exit_px = float(rth.iloc[-1]["close"]) - (HALF_SPREAD if side == "long" else -HALF_SPREAD)
            trades.append(
                Trade(
                    label,
                    side,
                    ets,
                    pd.Timestamp(rth.index[-1]),
                    entry,
                    exit_px,
                    1.0,
                    "eod",
                    pnl_usd(side, entry, exit_px),
                )
            )
    return trades


def sim_atr_fade_touch(one_m: pd.DataFrame, daily: pd.DataFrame) -> List[Trade]:
    """From 10:00 NY, fade first touch of M±2×ATR; SL 3×ATR TP opposite 2×ATR."""
    trades: List[Trade] = []
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["atr"] = (pd.to_numeric(d["high"]) - pd.to_numeric(d["low"])).rolling(14).mean()
    atr_map = {pd.Timestamp(r["date"]).date(): float(r["atr"]) for _, r in d.iterrows() if pd.notna(r["atr"])}
    for day in ny_sessions(one_m):
        atr = atr_map.get(day)
        if atr is None or atr <= 0:
            continue
        m = _session_open_px(one_m, day, time(0, 0), NY_TZ)
        if m is None:
            continue
        rth = eod_path(rth_day(one_m, day))
        path = rth[rth.index.time >= time(10, 0)]
        if path.empty:
            continue
        up = m + 2 * atr
        dn = m - 2 * atr
        side = entry = ets = None
        for ts, bar in path.iterrows():
            if float(bar["high"]) >= up:
                side = "short"
                entry = up - HALF_SPREAD
                ets = pd.Timestamp(ts)
                break
            if float(bar["low"]) <= dn:
                side = "long"
                entry = dn + HALF_SPREAD
                ets = pd.Timestamp(ts)
                break
        if side is None:
            continue
        rest = path[path.index > ets]
        if rest.empty:
            continue
        if side == "long":
            exit_px, reason, xts = exit_long(rest, entry, m - 3 * atr, m + 2 * atr)
        else:
            exit_px, reason, xts = exit_short(rest, entry, m + 3 * atr, m - 2 * atr)
        trades.append(
            Trade("B3_atr_fade_touch_ny", side, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
        )
    return trades


def sim_c3_orb_fade(one_m: pd.DataFrame, daily: pd.DataFrame) -> List[Trade]:
    """If prior day was a C3 hit continuation day, fade the first OR break with 1R."""
    trades: List[Trade] = []
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.date
    d = d.sort_values("date").reset_index(drop=True)
    c3_hit_days = set()
    for i in range(len(d) - 2):
        c1, c2, c3 = d.iloc[i], d.iloc[i + 1], d.iloc[i + 2]
        bull = float(c2["high"]) > float(c1["high"]) and float(c2["close"]) > float(c1["high"])
        bear = float(c2["low"]) < float(c1["low"]) and float(c2["close"]) < float(c1["low"])
        if bull and float(c3["high"]) > float(c2["high"]):
            c3_hit_days.add(c3["date"])
        if bear and float(c3["low"]) < float(c2["low"]):
            c3_hit_days.add(c3["date"])
    sessions = ny_sessions(one_m)
    for idx, day in enumerate(sessions):
        if idx == 0 or sessions[idx - 1] not in c3_hit_days:
            continue
        day_1m = rth_day(one_m, day)
        orb = opening_range(day_1m)
        if orb is None:
            continue
        rh, rl, _ = orb
        rv = rh - rl
        path = eod_path(path_after(day_1m, None))
        hit = _v2b_first_touch(path, rh, rl)
        if hit is None:
            continue
        brk_side, _, ets = hit
        # fade opposite
        side = "short" if brk_side == "long" else "long"
        rest = path[path.index > ets]
        if rest.empty:
            continue
        if side == "short":
            entry = rh - HALF_SPREAD
            # wait touch
            filled = False
            for t2, b2 in rest.iterrows():
                if float(b2["high"]) >= rh - TICK:
                    entry = rh - HALF_SPREAD
                    ets = pd.Timestamp(t2)
                    filled = True
                    break
            if not filled:
                continue
            path2 = rest[rest.index > ets]
            if path2.empty:
                continue
            exit_px, reason, xts = exit_short(path2, entry, rh + rv, rl)
        else:
            filled = False
            for t2, b2 in rest.iterrows():
                if float(b2["low"]) <= rl + TICK:
                    entry = rl + HALF_SPREAD
                    ets = pd.Timestamp(t2)
                    filled = True
                    break
            if not filled:
                continue
            path2 = rest[rest.index > ets]
            if path2.empty:
                continue
            exit_px, reason, xts = exit_long(path2, entry, rl - rv, rh)
        trades.append(
            Trade("B4_c3_hit_orb_fade", side, ets, xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
        )
    return trades


def sim_candlestick_breakout(daily: pd.DataFrame, name: str, bar_df: Optional[pd.DataFrame] = None) -> List[Trade]:
    """C3 opening-candle breakout: SL 2R, TP 3R on subsequent bars of same series."""
    trades: List[Trade] = []
    work = (bar_df if bar_df is not None else daily).copy()
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"])
        work = work.sort_values("date").reset_index(drop=True)
    else:
        work = work.reset_index().rename(columns={"index": "date"})
        work["date"] = pd.to_datetime(work["date"])
    lookahead = 10
    tp_mult = 3.0
    for i in range(len(work) - 2):
        c1, c2, c3 = work.iloc[i], work.iloc[i + 1], work.iloc[i + 2]
        bull = float(c2["high"]) > float(c1["high"]) and float(c2["close"]) > float(c1["high"])
        bear = float(c2["low"]) < float(c1["low"]) and float(c2["close"]) < float(c1["low"])
        if not (bull or bear):
            continue
        # C3 is OC
        oc_h, oc_l = float(c3["high"]), float(c3["low"])
        R = oc_h - oc_l
        if R <= 0:
            continue
        side = "long" if bull else "short"
        # find breakout in next lookahead bars
        for j in range(i + 3, min(i + 3 + lookahead, len(work))):
            b = work.iloc[j]
            if side == "long" and float(b["close"]) > oc_h:
                entry = float(b["close"]) + HALF_SPREAD
                stop = entry - 2 * R
                target = entry + tp_mult * R
                exit_px, reason = entry, "eod"
                xts = pd.Timestamp(b["date"])
                for k in range(j + 1, min(j + 1 + 30, len(work))):
                    r2 = work.iloc[k]
                    if float(r2["low"]) <= stop:
                        exit_px, reason = stop - HALF_SPREAD, "stop"
                        xts = pd.Timestamp(r2["date"])
                        break
                    if float(r2["high"]) >= target:
                        exit_px, reason = target - HALF_SPREAD, "target"
                        xts = pd.Timestamp(r2["date"])
                        break
                    exit_px = float(r2["close"]) - HALF_SPREAD
                    xts = pd.Timestamp(r2["date"])
                trades.append(
                    Trade(name, side, pd.Timestamp(b["date"]), xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
                )
                break
            if side == "short" and float(b["close"]) < oc_l:
                entry = float(b["close"]) - HALF_SPREAD
                stop = entry + 2 * R
                target = entry - tp_mult * R
                exit_px, reason = entry, "eod"
                xts = pd.Timestamp(b["date"])
                for k in range(j + 1, min(j + 1 + 30, len(work))):
                    r2 = work.iloc[k]
                    if float(r2["high"]) >= stop:
                        exit_px, reason = stop + HALF_SPREAD, "stop"
                        xts = pd.Timestamp(r2["date"])
                        break
                    if float(r2["low"]) <= target:
                        exit_px, reason = target + HALF_SPREAD, "target"
                        xts = pd.Timestamp(r2["date"])
                        break
                    exit_px = float(r2["close"]) + HALF_SPREAD
                    xts = pd.Timestamp(r2["date"])
                trades.append(
                    Trade(name, side, pd.Timestamp(b["date"]), xts, entry, exit_px, 1.0, reason, pnl_usd(side, entry, exit_px))
                )
                break
    return trades


def _monthly_bars(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").sort_index()
    try:
        monthly = d.resample("ME")
    except ValueError:
        monthly = d.resample("M")
    return (
        monthly.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna(subset=["open"])
        .reset_index()
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD scout of untried MNQ ideas")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--skip-a", action="store_true")
    parser.add_argument("--skip-b", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    print("Loading EURUSD...", flush=True)
    one_m, daily, _ = load_window(args.start, args.end)
    print("  1m bars:", f"{len(one_m):,}", "sessions:", len(ny_sessions(one_m)), flush=True)
    ma_bull = prior_ma_bull_map(daily)

    rows = []
    jobs = []
    if not args.skip_a:
        jobs += [
            ("A1_adaptive_v2b_only", lambda: sim_adaptive_v2b_only(one_m, ma_bull)),
            ("A2_adaptive_v2b_v2d", lambda: sim_adaptive_v2b_v2d(one_m, ma_bull)),
            ("A3_clean_break", lambda: sim_clean_break(one_m)),
            ("A4_v1b_pullback", lambda: sim_v1b_pullback(one_m)),
            ("A5_orb_open_limit", lambda: sim_open_limit(one_m)),
            ("A6_breakout_close_limit", lambda: sim_breakout_close_limit(one_m)),
            ("A7_swept_orb", lambda: sim_swept_orb(one_m)),
        ]
    if not args.skip_b:
        jobs += [
            ("B1_fib62_london_long", lambda: sim_fib62_london(one_m)),
            ("B2_pm_sweep_daily", lambda: sim_prior_month_sweep_daily(daily)),
            ("B3_midnight_flip_ny", lambda: sim_midnight_flip(one_m, "B3_midnight_flip_ny", NY_TZ, time(0, 0))),
            (
                "B3_midnight_flip_london",
                lambda: sim_midnight_flip(one_m, "B3_midnight_flip_london", pytz.timezone("Europe/London"), time(0, 0)),
            ),
            ("B3_atr_fade_touch_ny", lambda: sim_atr_fade_touch(one_m, daily)),
            ("B4_c3_hit_orb_fade", lambda: sim_c3_orb_fade(one_m, daily)),
            ("B5_daily_c3_breakout", lambda: sim_candlestick_breakout(daily, "B5_daily_c3_breakout")),
            (
                "B5_monthly_c3_breakout",
                lambda: sim_candlestick_breakout(daily, "B5_monthly_c3_breakout", _monthly_bars(daily)),
            ),
        ]

    for name, fn in jobs:
        print("Running", name, "...", flush=True)
        trades = fn()
        s = summarize(trades, name)
        rows.append(s)
        print(
            "  net=$%s dd=$%s n=%d WR=%.1f Net/DD=%.2f gate=%s"
            % (
                f"{s['net_usd']:,.0f}",
                f"{s['closed_dd_usd']:,.0f}",
                s["trades"],
                s["win_rate_pct"],
                s["net_over_closed_dd"],
                s["pass_scout_gate"],
            ),
            flush=True,
        )

    summary = pd.DataFrame(rows).sort_values(["pass_scout_gate", "net_usd"], ascending=[False, False])
    summary.to_csv(out / "leaderboard.csv", index=False)
    survivors = summary[summary["pass_scout_gate"]].copy()
    survivors.to_csv(out / "survivors.csv", index=False)

    lines = [
        "# EURUSD — untried MNQ idea scout",
        "",
        "Pandas/path scout (closed-equity DD). Unit = 1 lot, fee $1.50, ~0.5 pip half-spread.",
        "ORB session: NY 09:30–09:45. Window %s → %s." % (args.start, args.end),
        "",
        "Pass gate: `(net > 0 and Net/closed-DD ≥ 1.0)` or `net ≥ $23.5k with positive Net/DD`.",
        "",
        "| Strategy | Net | Closed DD | Net/DD | Trades | WR | Gate |",
        "|---|---:|---:|---:|---:|---:|:---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            "| %s | $%s | $%s | %.2f | %d | %.1f%% | %s |"
            % (
                r["strategy"],
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_closed_dd"],
                r["trades"],
                r["win_rate_pct"],
                "PASS" if r["pass_scout_gate"] else "fail",
            )
        )
    lines.extend(
        [
            "",
            "## Survivors for broker-like",
            "",
        ]
    )
    if survivors.empty:
        lines.append("None cleared the scout gate.")
    else:
        for _, r in survivors.iterrows():
            lines.append("- **%s** — net $%s / Net/DD %.2f" % (r["strategy"], f"{r['net_usd']:,.0f}", r["net_over_closed_dd"]))
    lines.extend(
        [
            "",
            "## Deferred Wave C (only if a parent cleared)",
            "",
            "- v2b_child / open-limit child",
            "- v2b_m monthly-break bias",
            "- Monthly ORB overlap ST retest / stop-limit cycle",
            "- adaptive_experiment 60% retrace / strict clean-break forks",
            "",
            "## Already tried on FX (skipped)",
            "",
            "Yearly ORB, Monthly ORB restricted/boundary, ATR DCA, Hourly ST+PMC, ungated v2b OCO,",
            "prior-opposed / PMC / YORB / monthly-swing v2b gates, London sweep reversal, OR fade,",
            "WO gap, weekly-mid, 15m ST DCA/fade.",
            "",
            "CSV: `leaderboard.csv`",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "summary.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    print("Survivors:", 0 if survivors.empty else len(survivors), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
