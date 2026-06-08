#!/usr/bin/env python3
"""
Backtest: **midnight-open flip**, **1 contract**, hourly bars **[00:00, 16:00) NY**.

**Profit modes** (``--profit-mode``):

- ``baseline`` — flip on hourly **close** vs midnight open **M**; session exit at 16:00.
- ``baseline_sl11`` — same as baseline, but **limit entries only from 11:00 NY** onward;
  **stop at M** on **1 m** once the **entry hourly bar has closed** (11:00 entry → SL from 12:00).
- ``atr_cross`` — **ATR extension** then **cross back through M**; limit @ **M** on the
  **hour after** the cross bar; **chop** = ≥2 hourly closes **above M** before any extension;
  then **baseline** flip + **16:00** exit.
- ``atr_cross_opp`` — fade: opposite side after extension/cross; chop = ≥2 closes **below** M.
- ``atr_fade_touch`` — first **1 m** touch **M±2×ATR** from **10:00**; hour open on near side;
  **one trade/day**; **SL 3×ATR**, **TP** opposite **2×ATR**, or **16:00**.
- ``atr_fade_touch_reclaim`` — from **10:00**, **15 m** reclaim setup then limit @ **2×ATR**
  (short: green cross above, red close below; long: opposite); same exits as ``atr_fade_touch``.
- ``baseline_sl11_opp`` — entries **before 11:00** only; **TP at M** after entry hour (vs SL).
- ``weekly_baseline`` / ``weekly_baseline_4h`` / ``weekly_baseline_1d`` — baseline vs
  **weekly open**; TP at **±½ prior week range** (1 m); flips on bar **close** vs level;
  **16:00** flatten. Bars: **1h** (default), **4h**, or **session daily** (one bar 00:00–16:00).
- ``v2b_tp`` — from **09:45**, favorable **v2b** TP on **1 m** (**long** ``RH+Range``,
  **short** ``RL−Range``); if not hit, **still flip** on hourly close vs **M** (often bleeds).
- ``v2b_only`` — after **09:45**, **only** favorable v2b TP + **16:00** flatten (no flip
  re-entries during RTH); best match for “take profit at ORB target” without churn.

Also ``--analyze-mfe`` prints **MFE** (max favorable excursion) for positions still open at
09:45 under baseline — input for a fixed-point profit distance if v2b TP underperforms.

Example::

  python3 backtest_midnight_open_flip.py --instrument mnq --profit-mode baseline
  python3 backtest_midnight_open_flip.py --instrument all --profit-mode v2b_tp
  python3 backtest_midnight_open_flip.py --instrument mnq --analyze-mfe
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytz

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402

NY = pytz.timezone('America/New_York')
ORB_LO = mdata.ORB_LO
ORB_HI = mdata.ORB_HI
ORB_READY = ORB_HI  # targets active once 09:45 bar has printed

USD_PER_POINT = {'mnq': 2.0, 'nq': 20.0}
ENTRY_EARLIEST = time(11, 0)  # baseline_sl11: no limit fills before this (bar left edge NY)
ATR_FADE_ENTRY_EARLIEST = time(10, 0)  # atr_fade_touch: no new entries before this NY
ATR_FADE_ENTRY_MULT = 2.0  # limit @ M ± 2×ATR
ATR_FADE_SL_MULT = 3.0  # stop @ M ± 3×ATR
ATR_FADE_TP_MULT = 2.0  # target opposite M ∓ 2×ATR
ATR_LEN = 14
ATR_WARMUP_DAYS = 10

WEEKLY_BAR_TF: dict[str, str] = {
    'weekly_baseline': '1h',
    'weekly_baseline_4h': '4h',
    'weekly_baseline_1d': '1d',
}
BAR_TF_HOURS: dict[str, float] = {'1h': 1.0, '4h': 4.0, '1d': 16.0}

ProfitMode = str  # 'baseline' | 'weekly_baseline' | ...


@dataclass(frozen=True)
class DayWeekCtx:
    weekly_open: float
    prior_week_range: float


@dataclass
class Trade:
    session: date
    side: str
    entry_time: pd.Timestamp
    entry_px: float
    exit_time: pd.Timestamp
    exit_px: float
    reason_exit: str
    usd_per_point: float

    @property
    def pnl_usd(self) -> float:
        if self.side == 'long':
            pts = self.exit_px - self.entry_px
        else:
            pts = self.entry_px - self.exit_px
        return pts * self.usd_per_point


def orb_v2b_targets(sess_1m: pd.DataFrame, session_day: date) -> tuple[float, float, float, float, float] | None:
    """``(rh, rl, range, target_long, target_short)`` or None."""
    if sess_1m.empty:
        return None
    orb = sess_1m[
        sess_1m.index.map(lambda t: t.date() == session_day and ORB_LO <= t.time() < ORB_HI)
    ]
    if orb.empty:
        return None
    rh = float(orb['high'].max())
    rl = float(orb['low'].min())
    rv = rh - rl
    if rv <= 0:
        return None
    return rh, rl, rv, rh + rv, rl - rv


def _limit_short_fills(M: float, o: float, h: float) -> bool:
    return (o >= M) or (h >= M)


def _limit_long_fills(M: float, o: float, low: float) -> bool:
    return (o <= M) or (low <= M)


def week_monday(d: date) -> date:
    """ISO week anchor (Monday) for calendar date ``d``."""
    return d - timedelta(days=d.weekday())


def build_week_context_by_day(gby: dict[date, pd.DataFrame]) -> dict[date, DayWeekCtx]:
    """
    Per calendar day: **weekly open** = open of the first 1 m in that Mon-start week;
    **prior_week_range** = prior Mon-start week's high − low (all 1 m in ``gby`` for those days).
    """
    week_days: dict[date, list[date]] = defaultdict(list)
    week_hi: dict[date, float] = {}
    week_lo: dict[date, float] = {}
    week_first: dict[date, tuple[pd.Timestamp, float]] = {}

    for d in sorted(gby.keys()):
        raw = gby.get(d)
        if raw is None or raw.empty:
            continue
        wm = week_monday(d)
        week_days[wm].append(d)
        hi = float(raw['high'].max())
        lo = float(raw['low'].min())
        week_hi[wm] = max(week_hi.get(wm, -np.inf), hi)
        week_lo[wm] = min(week_lo.get(wm, np.inf), lo)
        t0 = raw.index.min()
        o0 = float(raw.loc[t0, 'open'])
        if wm not in week_first or t0 < week_first[wm][0]:
            week_first[wm] = (t0, o0)

    week_range = {wm: week_hi[wm] - week_lo[wm] for wm in week_hi}
    week_open = {wm: week_first[wm][1] for wm in week_first}

    out: dict[date, DayWeekCtx] = {}
    for d in gby:
        wm = week_monday(d)
        prev_wm = wm - timedelta(days=7)
        out[d] = DayWeekCtx(
            weekly_open=float(week_open.get(wm, float('nan'))),
            prior_week_range=float(week_range.get(prev_wm, float('nan'))),
        )
    return out


def _scan_1m_half_week_tp(
    sess_1m: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    pos: str,
    entry_px: float,
    half_range: float,
) -> tuple[pd.Timestamp, float, str] | None:
    """Long: entry + ½ prior week range; short: entry − ½ prior week range."""
    if t_start >= t_end or sess_1m.empty or not (np.isfinite(half_range) and half_range > 0):
        return None
    if pos == 'long':
        target = entry_px + half_range
    else:
        target = entry_px - half_range
    chunk = sess_1m[(sess_1m.index >= t_start) & (sess_1m.index < t_end)]
    for ts, bar in chunk.iterrows():
        hi, lo = float(bar['high']), float(bar['low'])
        if pos == 'long' and hi >= target - 1e-9:
            return ts, target, 'tp_half_week'
        if pos == 'short' and lo <= target + 1e-9:
            return ts, target, 'tp_half_week'
    return None


def _scan_1m_tp_at_midnight(
    sess_1m: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    pos: str,
    M: float,
) -> tuple[pd.Timestamp, float, str] | None:
    """Take profit at **M** (long: high reaches M; short: low reaches M). Opposite of SL at M."""
    if t_start >= t_end or sess_1m.empty or not np.isfinite(M):
        return None
    chunk = sess_1m[(sess_1m.index >= t_start) & (sess_1m.index < t_end)]
    for ts, bar in chunk.iterrows():
        hi, lo = float(bar['high']), float(bar['low'])
        if pos == 'long' and hi >= M - 1e-9:
            return ts, M, 'tp_M'
        if pos == 'short' and lo <= M + 1e-9:
            return ts, M, 'tp_M'
    return None


def _scan_1m_sl_midnight(
    sess_1m: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    pos: str,
    M: float,
) -> tuple[pd.Timestamp, float, str] | None:
    """Stop at midnight open **M** (long: low <= M; short: high >= M)."""
    if t_start >= t_end or sess_1m.empty or not np.isfinite(M):
        return None
    chunk = sess_1m[(sess_1m.index >= t_start) & (sess_1m.index < t_end)]
    for ts, bar in chunk.iterrows():
        hi, lo = float(bar['high']), float(bar['low'])
        if pos == 'long' and lo <= M + 1e-9:
            return ts, M, 'sl_M'
        if pos == 'short' and hi >= M - 1e-9:
            return ts, M, 'sl_M'
    return None


def _entry_earliest_ts(session_day: date) -> pd.Timestamp:
    return NY.localize(datetime.combine(session_day, ENTRY_EARLIEST))


def _scan_1m_fixed_tp(
    sess_1m: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    pos: str,
    entry_px: float,
    tp_pts: float,
) -> tuple[pd.Timestamp, float, str] | None:
    if t_start >= t_end or sess_1m.empty or tp_pts <= 0:
        return None
    if pos == 'long':
        target = entry_px + tp_pts
    else:
        target = entry_px - tp_pts
    chunk = sess_1m[(sess_1m.index >= t_start) & (sess_1m.index < t_end)]
    for ts, bar in chunk.iterrows():
        hi, lo = float(bar['high']), float(bar['low'])
        if pos == 'long' and hi >= target - 1e-9:
            return ts, target, f'fixed_tp_{tp_pts:g}'
        if pos == 'short' and lo <= target + 1e-9:
            return ts, target, f'fixed_tp_{tp_pts:g}'
    return None


def _scan_1m_v2b_tp(
    sess_1m: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    pos: str,
    entry_px: float,
    target_long: float,
    target_short: float,
) -> tuple[pd.Timestamp, float, str] | None:
    """Only take v2b TP if target is **favorable** vs entry (not a loss exit)."""
    if t_start >= t_end or sess_1m.empty:
        return None
    use_long = pos == 'long' and target_long > entry_px + 1e-9
    use_short = pos == 'short' and target_short < entry_px - 1e-9
    if not (use_long or use_short):
        return None
    chunk = sess_1m[(sess_1m.index >= t_start) & (sess_1m.index < t_end)]
    for ts, bar in chunk.iterrows():
        hi, lo = float(bar['high']), float(bar['low'])
        if use_long and hi >= target_long - 1e-9:
            return ts, target_long, 'v2b_tp'
        if use_short and lo <= target_short + 1e-9:
            return ts, target_short, 'v2b_tp'
    return None


def _orb_ready_ts(session_day: date) -> pd.Timestamp:
    return NY.localize(datetime.combine(session_day, ORB_READY))


def hourly_atr_series(hourly: pd.DataFrame, length: int = ATR_LEN) -> pd.Series:
    """Wilder-style ATR on hourly OHLC (uses prior close for TR)."""
    pc = hourly['close'].shift(1)
    tr = pd.concat(
        [
            hourly['high'] - hourly['low'],
            (hourly['high'] - pc).abs(),
            (hourly['low'] - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False, min_periods=1).mean()


def build_hourly_with_warmup(
    gby: dict[date, pd.DataFrame],
    session_day: date,
    *,
    warmup_days: int = ATR_WARMUP_DAYS,
) -> pd.DataFrame:
    """Prior session hours + ``session_day`` [00:00,16:00) hourly bars for ATR context."""
    d0 = session_day - timedelta(days=warmup_days)
    parts: list[pd.DataFrame] = []
    for d in sorted(gby.keys()):
        if d < d0 or d > session_day:
            continue
        raw = gby.get(d)
        if raw is None or raw.empty:
            continue
        h = mdata.resample_1h_midnight_to_1600(raw, d)
        if not h.empty:
            parts.append(h)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def atr_on_1m_bars(sess_1m: pd.DataFrame, hourly_warm: pd.DataFrame) -> pd.Series:
    """Hourly ATR (prior bar) forward-filled onto each 1 m timestamp."""
    if sess_1m.empty or hourly_warm.empty:
        return pd.Series(dtype=float)
    atr_h = hourly_atr_series(hourly_warm.sort_index()).shift(1)
    out: list[float] = []
    idx = sess_1m.sort_index().index
    for ts in idx:
        prior = atr_h[atr_h.index <= ts]
        out.append(float(prior.iloc[-1]) if not prior.empty else float('nan'))
    return pd.Series(out, index=idx)


def _reclaim_15m_arm_after(
    session_day: date,
    M: float,
    sess_1m: pd.DataFrame,
    atr_s: pd.Series,
    entry_mult: float,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """
    15 m reclaim entry arming (limit allowed from returned timestamp onward).

    **Short:** green cross (open < band, close > band) then red close < band.
    **Long:** red cross (open > band, close < band) then green close > band.
    """
    bars15 = mdata._resample_session_ohlcv(sess_1m, session_day, '15min')
    if bars15.empty:
        return None, None
    entry_earliest = NY.localize(datetime.combine(session_day, ATR_FADE_ENTRY_EARLIEST))
    arm_short: pd.Timestamp | None = None
    arm_long: pd.Timestamp | None = None
    short_need_reclaim = False
    long_need_reclaim = False

    for ts, row in bars15.sort_index().iterrows():
        if ts < entry_earliest:
            continue
        atr = float(atr_s.loc[ts]) if ts in atr_s.index else float('nan')
        if not (np.isfinite(atr) and atr > 0):
            continue
        o, c = float(row['open']), float(row['close'])
        entry_up = M + entry_mult * atr
        entry_lo = M - entry_mult * atr
        bar_end = ts + pd.Timedelta(minutes=15)

        if arm_short is None and not short_need_reclaim:
            if o < entry_up - 1e-9 and c > entry_up + 1e-9 and c > o:
                short_need_reclaim = True
        elif arm_short is None and short_need_reclaim:
            if c < entry_up - 1e-9 and c < o:
                arm_short = bar_end
                short_need_reclaim = False

        if arm_long is None and not long_need_reclaim:
            if o > entry_lo + 1e-9 and c < entry_lo - 1e-9 and c < o:
                long_need_reclaim = True
        elif arm_long is None and long_need_reclaim:
            if c > entry_lo + 1e-9 and c > o:
                arm_long = bar_end
                long_need_reclaim = False

    return arm_short, arm_long


def _hourly_opens_ny(sess_1m: pd.DataFrame) -> dict[pd.Timestamp, float]:
    """NY hour bucket → open of first 1 m in that hour."""
    out: dict[pd.Timestamp, float] = {}
    for ts, bar in sess_1m.sort_index().iterrows():
        h0 = pd.Timestamp(ts).replace(minute=0, second=0, microsecond=0)
        if h0 not in out:
            out[h0] = float(bar['open'])
    return out


def simulate_session_atr_fade_touch(
    session_day: date,
    M: float,
    sess_1m: pd.DataFrame,
    hourly_warm: pd.DataFrame,
    usd_per_point: float,
    *,
    entry_atr_mult: float | None = None,
    entry_offset_pts: float | None = None,
    entry_style: str = 'touch',
) -> list[Trade]:
    """
    **atr_fade_touch** session simulation (from **10:00 NY**).

    ``entry_style='touch'``: first **1 m** touch of **M±2×ATR**; hour open on near side.
    ``entry_style='reclaim_15m'``: **15 m** cross + reclaim, then limit @ band.
    **SL** **M±3×ATR**, **TP** opposite **M∓2×ATR**; **one trade/day**; **16:00** flatten.
    """
    entry_mult = ATR_FADE_ENTRY_MULT if entry_atr_mult is None else float(entry_atr_mult)
    use_reclaim = entry_style == 'reclaim_15m'
    trades: list[Trade] = []
    if not (np.isfinite(M)) or sess_1m.empty or hourly_warm.empty:
        return trades

    entry_earliest = NY.localize(datetime.combine(session_day, ATR_FADE_ENTRY_EARLIEST))
    hour_opens = _hourly_opens_ny(sess_1m) if not use_reclaim else {}
    atr_s = atr_on_1m_bars(sess_1m, hourly_warm)
    arm_short, arm_long = (
        _reclaim_15m_arm_after(session_day, M, sess_1m, atr_s, entry_mult) if use_reclaim else (None, None)
    )
    pos: str | None = None
    entry_px = entry_ts = sl_px = tp_px = None

    def close_pos(exit_ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal pos, entry_px, entry_ts, sl_px, tp_px
        if pos is None:
            return
        trades.append(
            Trade(session_day, pos, entry_ts, entry_px, exit_ts, exit_px, reason, usd_per_point)
        )
        pos = None

    def manage_open_position(ts: pd.Timestamp, hi: float, lo: float) -> None:
        if pos == 'short':
            if hi >= sl_px - 1e-9:
                close_pos(ts, sl_px, 'sl_atr')
            elif lo <= tp_px + 1e-9:
                close_pos(ts, tp_px, 'tp_opposite_band')
        elif pos == 'long':
            if lo <= sl_px + 1e-9:
                close_pos(ts, sl_px, 'sl_atr')
            elif hi >= tp_px - 1e-9:
                close_pos(ts, tp_px, 'tp_opposite_band')

    for ts, bar in sess_1m.sort_index().iterrows():
        atr = float(atr_s.loc[ts]) if ts in atr_s.index else float('nan')
        if not (np.isfinite(atr) and atr > 0):
            continue
        hi, lo = float(bar['high']), float(bar['low'])
        if entry_offset_pts is not None:
            off = float(entry_offset_pts)
            entry_up = M + off
            entry_lo = M - off
        else:
            entry_up = M + entry_mult * atr
            entry_lo = M - entry_mult * atr

        if pos is not None:
            manage_open_position(ts, hi, lo)
            continue

        if trades:
            continue

        if ts < entry_earliest:
            continue

        if use_reclaim:
            if arm_short is not None and ts >= arm_short and hi >= entry_up - 1e-9:
                pos = 'short'
                entry_px, entry_ts = entry_up, ts
                sl_px = M + ATR_FADE_SL_MULT * atr
                tp_px = M - ATR_FADE_TP_MULT * atr
                manage_open_position(ts, hi, lo)
            elif arm_long is not None and ts >= arm_long and lo <= entry_lo + 1e-9:
                pos = 'long'
                entry_px, entry_ts = entry_lo, ts
                sl_px = M - ATR_FADE_SL_MULT * atr
                tp_px = M + ATR_FADE_TP_MULT * atr
                manage_open_position(ts, hi, lo)
        else:
            h0 = pd.Timestamp(ts).replace(minute=0, second=0, microsecond=0)
            h_open = hour_opens.get(h0)
            if h_open is None:
                continue

            if hi >= entry_up - 1e-9 and h_open < entry_up - 1e-9:
                pos = 'short'
                entry_px, entry_ts = entry_up, ts
                sl_px = M + ATR_FADE_SL_MULT * atr
                tp_px = M - ATR_FADE_TP_MULT * atr
                manage_open_position(ts, hi, lo)
            elif lo <= entry_lo + 1e-9 and h_open > entry_lo + 1e-9:
                pos = 'long'
                entry_px, entry_ts = entry_lo, ts
                sl_px = M - ATR_FADE_SL_MULT * atr
                tp_px = M + ATR_FADE_TP_MULT * atr
                manage_open_position(ts, hi, lo)

    if pos is not None and not sess_1m.empty:
        last_ts = sess_1m.index.max()
        close_pos(last_ts, float(sess_1m.loc[last_ts, 'close']), 'session_16:00')

    return trades


def simulate_session_atr_cross(
    session_day: date,
    M: float,
    hourly: pd.DataFrame,
    hourly_warm: pd.DataFrame,
    usd_per_point: float,
    *,
    invert_entry: bool = False,
    chop_closes_below: bool = False,
) -> list[Trade]:
    """
    Extension (|move| >= hourly ATR from M) → cross back through M → limit @ M next hour.

    Default: up-ext + cross down → **long**; chop = ≥2 closes **above** M pre-extension.
    ``invert_entry``: fade — up-ext + cross down → **short** (and vice versa).
    ``chop_closes_below``: chop = ≥2 closes **below** M pre-extension.
    Post-entry: baseline flip + 16:00.
    """
    trades: list[Trade] = []
    h = hourly.sort_index()
    if not (np.isfinite(M)) or len(h) < 3 or hourly_warm.empty:
        return trades

    hw = hourly_warm.sort_index()
    atr_all = hourly_atr_series(hw).shift(1)  # ATR known at bar open

    extended_up = False
    extended_down = False
    any_extension = False
    closes_above_pre = 0
    closes_below_pre = 0
    chop = False
    setup_done = False
    pending_setup: str | None = None  # armed for **next** bar after cross

    pos: str | None = None
    entry_px = 0.0
    entry_ts = h.index[0]
    pending_flip: str | None = None
    last_i = len(h) - 1

    def close_trade(exit_ts: pd.Timestamp, exit_px: float, reason: str, arm: str | None) -> None:
        nonlocal pos, pending_flip, entry_px, entry_ts
        if pos is None:
            return
        trades.append(
            Trade(session_day, pos, entry_ts, entry_px, exit_ts, exit_px, reason, usd_per_point)
        )
        pos = None
        pending_flip = arm

    def open_position(side: str, ts_open: pd.Timestamp, reason: str) -> None:
        nonlocal pos, entry_px, entry_ts, pending_setup, pending_flip, setup_done
        pos = side
        entry_px = M
        entry_ts = ts_open
        pending_setup = None
        pending_flip = None
        setup_done = True

    for i in range(len(h)):
        row = h.iloc[i]
        ts = h.index[i]
        o, hi, lo, cl = map(float, (row['open'], row['high'], row['low'], row['close']))
        atr = float(atr_all.loc[ts]) if ts in atr_all.index else float('nan')

        # --- setup limit on bar after cross ---
        if (
            not chop
            and pos is None
            and pending_setup == 'long'
            and _limit_long_fills(M, o, lo)
        ):
            open_position('long', ts, 'atr_cross_long')
        elif (
            not chop
            and pos is None
            and pending_setup == 'short'
            and _limit_short_fills(M, o, hi)
        ):
            open_position('short', ts, 'atr_cross_short')

        # --- baseline flip limits (after first fill) ---
        if setup_done and pos is None and pending_flip == 'short' and _limit_short_fills(M, o, hi):
            pos, entry_px, entry_ts, pending_flip = 'short', M, ts, None
        elif setup_done and pos is None and pending_flip == 'long' and _limit_long_fills(M, o, lo):
            pos, entry_px, entry_ts, pending_flip = 'long', M, ts, None

        # --- baseline flip exits ---
        if pos == 'short' and cl > M:
            close_trade(ts, cl, 'close>M', 'long')
        elif pos == 'long' and cl < M:
            close_trade(ts, cl, 'close<M', 'short')

        if i == last_i and pos is not None:
            close_trade(ts, cl, 'session_16:00', None)

        if chop or setup_done:
            continue

        # --- chop / extension tracking (before first extension) ---
        if not any_extension:
            if cl > M:
                closes_above_pre += 1
            if cl < M:
                closes_below_pre += 1
            if chop_closes_below:
                if closes_below_pre >= 2:
                    chop = True
                    continue
            elif closes_above_pre >= 2:
                chop = True
                continue

        if np.isfinite(atr) and atr > 0:
            if hi >= M + atr - 1e-9:
                extended_up = True
                any_extension = True
            if lo <= M - atr + 1e-9:
                extended_down = True
                any_extension = True

        if i == 0:
            continue

        prev_cl = float(h.iloc[i - 1]['close'])
        if extended_up and prev_cl > M and cl < M:
            pending_setup = 'short' if invert_entry else 'long'
        elif extended_down and prev_cl < M and cl > M:
            pending_setup = 'long' if invert_entry else 'short'

    return trades


def _session_bar_end(session_day: date, ts: pd.Timestamp, bar_tf: str) -> pd.Timestamp:
    if bar_tf == '1d':
        return NY.localize(datetime.combine(session_day, mdata.SESSION_HI))
    return ts + pd.Timedelta(hours=BAR_TF_HOURS[bar_tf])


def simulate_session_daily_bar(
    session_day: date,
    level: float,
    bar: pd.DataFrame,
    sess_1m: pd.DataFrame,
    usd_per_point: float,
    *,
    tp_half_week_range: float | None = None,
) -> list[Trade]:
    """Single session daily candle: bias from **open** vs level; one pass through the day."""
    trades: list[Trade] = []
    if bar.empty or not np.isfinite(level):
        return trades
    row = bar.iloc[0]
    ts = bar.index[0]
    o, hi, lo, cl = map(float, (row['open'], row['high'], row['low'], row['close']))
    if abs(o - level) < 1e-9:
        return trades
    bar_end = _session_bar_end(session_day, ts, '1d')
    half_week = (
        float(tp_half_week_range)
        if tp_half_week_range is not None and np.isfinite(tp_half_week_range)
        else float('nan')
    )
    use_half_week_tp = np.isfinite(half_week) and half_week > 0
    pos: str | None = None
    entry_px = 0.0
    entry_ts = ts
    pending: str | None = 'short' if o < level else 'long'

    def close_trade(exit_ts: pd.Timestamp, exit_px: float, reason: str, arm: str | None) -> None:
        nonlocal pos, pending, entry_px, entry_ts
        if pos is None:
            return
        trades.append(
            Trade(session_day, pos, entry_ts, entry_px, exit_ts, exit_px, reason, usd_per_point)
        )
        pos = None
        pending = arm

    if pending == 'short' and _limit_short_fills(level, o, hi):
        pos, entry_px, entry_ts, pending = 'short', level, ts, None
    elif pending == 'long' and _limit_long_fills(level, o, lo):
        pos, entry_px, entry_ts, pending = 'long', level, ts, None

    if use_half_week_tp and pos:
        hit = _scan_1m_half_week_tp(sess_1m, ts, bar_end, pos, entry_px, half_week)
        if hit:
            exit_ts, exit_px, reason = hit
            close_trade(exit_ts, exit_px, reason, 'long' if pos == 'short' else 'short')

    if pos == 'short' and cl > level:
        close_trade(ts, cl, 'close>level', 'long')
    elif pos == 'long' and cl < level:
        close_trade(ts, cl, 'close<level', 'short')

    if pos is not None:
        close_trade(ts, cl, 'session_16:00', None)

    return trades


def simulate_session(
    session_day: date,
    level: float,
    bars: pd.DataFrame,
    sess_1m: pd.DataFrame,
    usd_per_point: float,
    *,
    profit_mode: ProfitMode = 'baseline',
    fixed_tp_pts: float = 0.0,
    tp_half_week_range: float | None = None,
    bar_tf: str = '1h',
) -> list[Trade]:
    trades: list[Trade] = []
    if not (np.isfinite(level)) or bars is None or bars.empty:
        return trades

    h = bars.sort_index()
    if bar_tf == '1d' and len(h) == 1:
        return simulate_session_daily_bar(
            session_day, level, h, sess_1m, usd_per_point, tp_half_week_range=tp_half_week_range
        )
    if len(h) < 2:
        return trades

    c0 = float(h.iloc[0]['close'])
    if abs(c0 - level) < 1e-9:
        return trades

    use_sl11 = profit_mode == 'baseline_sl11'
    use_sl11_opp = profit_mode == 'baseline_sl11_opp'
    entry_earliest = (
        _entry_earliest_ts(session_day) if (use_sl11 or use_sl11_opp) else None
    )
    half_week = (
        float(tp_half_week_range)
        if tp_half_week_range is not None and np.isfinite(tp_half_week_range)
        else float('nan')
    )
    use_half_week_tp = np.isfinite(half_week) and half_week > 0

    use_v2b = profit_mode in ('v2b_tp', 'v2b_only')
    use_fixed = profit_mode == 'fixed_tp' and fixed_tp_pts > 0
    orb = orb_v2b_targets(sess_1m, session_day) if (use_v2b or use_fixed) else None
    flip_after_orb = profit_mode not in ('v2b_only', 'fixed_tp')
    orb_ready = _orb_ready_ts(session_day) if orb else None
    target_long = target_short = float('nan')
    if orb:
        _, _, _, target_long, target_short = orb

    pos: str | None = None
    entry_px = 0.0
    entry_ts = h.index[0]
    sl_active_from: pd.Timestamp | None = None
    pending: str | None = 'short' if c0 < level else 'long'
    last_i = len(h) - 1

    def close_trade(exit_ts: pd.Timestamp, exit_px: float, reason: str, arm: str | None) -> None:
        nonlocal pos, pending, entry_px, entry_ts, sl_active_from
        if pos is None:
            return
        trades.append(
            Trade(session_day, pos, entry_ts, entry_px, exit_ts, exit_px, reason, usd_per_point)
        )
        pos = None
        sl_active_from = None
        pending = arm

    def open_position(side: str, ts_open: pd.Timestamp) -> None:
        nonlocal pos, entry_px, entry_ts, pending, sl_active_from
        pos = side
        entry_px = level
        entry_ts = ts_open
        pending = None
        sl_active_from = ts_open + pd.Timedelta(hours=1) if (use_sl11 or use_sl11_opp) else None

    for i in range(1, len(h)):
        row = h.iloc[i]
        ts = h.index[i]
        o, hi, lo, cl = map(float, (row['open'], row['high'], row['low'], row['close']))
        bar_end = _session_bar_end(session_day, ts, bar_tf)
        if use_sl11:
            may_enter = ts >= entry_earliest
        elif use_sl11_opp:
            may_enter = ts < entry_earliest
        else:
            may_enter = True

        # --- limit entry (hourly OHLC at bar open) ---
        if may_enter and pos is None and pending == 'short' and _limit_short_fills(level, o, hi):
            open_position('short', ts)
        elif may_enter and pos is None and pending == 'long' and _limit_long_fills(level, o, lo):
            open_position('long', ts)

        # --- ½ prior-week range TP on 1m ---
        if use_half_week_tp and pos:
            hit = _scan_1m_half_week_tp(sess_1m, ts, bar_end, pos, entry_px, half_week)
            if hit:
                exit_ts, exit_px, reason = hit
                arm = 'long' if pos == 'short' else 'short'
                close_trade(exit_ts, exit_px, reason, arm)

        # --- midnight SL (sl11) or TP at M (sl11_opp), after entry hour ---
        if (use_sl11 or use_sl11_opp) and pos and sl_active_from is not None and bar_end > sl_active_from:
            t_lo = max(ts, sl_active_from)
            if use_sl11:
                hit = _scan_1m_sl_midnight(sess_1m, t_lo, bar_end, pos, level)
            else:
                hit = _scan_1m_tp_at_midnight(sess_1m, t_lo, bar_end, pos, level)
            if hit:
                exit_ts, exit_px, reason = hit
                arm = 'long' if pos == 'short' else 'short'
                close_trade(exit_ts, exit_px, reason, arm)

        # --- v2b TP on 1m after ORB (before flip on this hour) ---
        if orb and pos and bar_end > orb_ready:
            t_lo = max(ts, orb_ready)
            hit = None
            if use_v2b:
                hit = _scan_1m_v2b_tp(
                    sess_1m, t_lo, bar_end, pos, entry_px, target_long, target_short
                )
            elif use_fixed:
                hit = _scan_1m_fixed_tp(sess_1m, t_lo, bar_end, pos, entry_px, fixed_tp_pts)
            if hit:
                exit_ts, exit_px, reason = hit
                arm = None
                if flip_after_orb:
                    arm = 'long' if pos == 'short' else 'short'
                close_trade(exit_ts, exit_px, reason, arm)

        # --- flip on hourly close vs M (disabled after ORB in v2b_only) ---
        allow_flip = flip_after_orb or (orb_ready is None) or (bar_end <= orb_ready)
        if allow_flip:
            if pos == 'short' and cl > level:
                close_trade(ts, cl, 'close>level', 'long' if flip_after_orb else None)
            elif pos == 'long' and cl < level:
                close_trade(ts, cl, 'close<level', 'short' if flip_after_orb else None)

        # no new limits after ORB in v2b_only
        if profit_mode in ('v2b_only', 'fixed_tp') and orb_ready and ts >= orb_ready:
            pending = None

        # --- session flatten ---
        if i == last_i and pos is not None:
            close_trade(ts, cl, 'session_16:00', None)

    return trades


def analyze_mfe_at_orb(
    session_day: date,
    M: float,
    hourly: pd.DataFrame,
    sess_1m: pd.DataFrame,
) -> list[dict]:
    """
  For baseline simulation: MFE in **points** from entry to exit (or 09:45 if still open)
  for each leg that was open at ORB ready.
    """
    trades = simulate_session(
        session_day, M, hourly, sess_1m, 1.0, profit_mode='baseline'
    )
    if not trades:
        return []

    orb_ready = _orb_ready_ts(session_day)
    out: list[dict] = []
    for t in trades:
        entry = pd.Timestamp(t.entry_time)
        exit_ = pd.Timestamp(t.exit_time)
        if entry >= orb_ready:
            continue
        path_end = min(exit_, orb_ready + pd.Timedelta(minutes=1))
        path = sess_1m[(sess_1m.index >= entry) & (sess_1m.index < path_end)]
        if path.empty:
            continue
        if t.side == 'long':
            mfe = float(path['high'].max()) - t.entry_px
        else:
            mfe = t.entry_px - float(path['low'].min())
        out.append(
            {
                'session': session_day.isoformat(),
                'side': t.side,
                'entry_px': t.entry_px,
                'mfe_pts': round(mfe, 2),
                'held_past_orb': exit_ > orb_ready,
            }
        )
    return out


def run_backtest(
    instrument: str,
    dbn_path: Path,
    *,
    weekdays_only: bool,
    profit_mode: ProfitMode,
    fixed_tp_pts: float = 0.0,
) -> tuple[list[Trade], dict]:
    inst = instrument.lower()
    usd_pp = USD_PER_POINT[inst]
    gby = mdata.load_1m_by_ny_date(dbn_path.resolve(), inst)
    all_days = sorted(gby.keys())
    session_days = [d for d in all_days if not weekdays_only or d.weekday() < 5]
    bar_tf_weekly = WEEKLY_BAR_TF.get(profit_mode)
    week_ctx = build_week_context_by_day(gby) if bar_tf_weekly else None

    all_trades: list[Trade] = []
    skipped = 0
    no_bars = 0
    skipped_week = 0

    for d in session_days:
        raw = gby.get(d)
        sess = mdata.slice_session_1m(raw, d)
        tf = bar_tf_weekly or '1h'
        session_bars = mdata.resample_session_bars(raw, d, tf)
        min_bars = 1 if tf == '1d' else 2
        if session_bars is None or len(session_bars) < min_bars:
            no_bars += 1
            continue

        if bar_tf_weekly:
            assert week_ctx is not None
            wk = week_ctx.get(d)
            if wk is None:
                skipped_week += 1
                continue
            level = wk.weekly_open
            half_range = 0.5 * wk.prior_week_range
            if not (np.isfinite(level) and np.isfinite(half_range) and half_range > 0):
                skipped_week += 1
                continue
            ref = float(session_bars.sort_index().iloc[0]['open' if tf == '1d' else 'close'])
            if abs(ref - level) < 1e-9:
                skipped += 1
                continue
            all_trades.extend(
                simulate_session(
                    d,
                    level,
                    session_bars,
                    sess,
                    usd_pp,
                    profit_mode='baseline',
                    tp_half_week_range=half_range,
                    bar_tf=tf,
                )
            )
            continue

        hourly = session_bars
        c0 = float(hourly.sort_index().iloc[0]['close'])
        M = mdata.ny_midnight_open_px(sess)
        if not np.isfinite(M) or abs(c0 - M) < 1e-9:
            skipped += 1
            continue
        if profit_mode in ('atr_fade_touch', 'atr_fade_touch_reclaim'):
            hw = build_hourly_with_warmup(gby, d)
            style = 'reclaim_15m' if profit_mode == 'atr_fade_touch_reclaim' else 'touch'
            all_trades.extend(
                simulate_session_atr_fade_touch(d, M, sess, hw, usd_pp, entry_style=style)
            )
        elif profit_mode in ('atr_cross', 'atr_cross_opp'):
            hw = build_hourly_with_warmup(gby, d)
            all_trades.extend(
                simulate_session_atr_cross(
                    d,
                    M,
                    hourly.sort_index(),
                    hw,
                    usd_pp,
                    invert_entry=(profit_mode == 'atr_cross_opp'),
                    chop_closes_below=(profit_mode == 'atr_cross_opp'),
                )
            )
        else:
            all_trades.extend(
                simulate_session(
                    d,
                    M,
                    hourly,
                    sess,
                    usd_pp,
                    profit_mode=profit_mode,
                    fixed_tp_pts=fixed_tp_pts,
                    bar_tf='1h',
                )
            )

    meta = {
        'instrument': inst.upper(),
        'profit_mode': profit_mode,
        'bar_tf': bar_tf_weekly or '1h',
        'dbn': str(dbn_path.resolve()),
        'date_first': session_days[0].isoformat() if session_days else '',
        'date_last': session_days[-1].isoformat() if session_days else '',
        'n_calendar_days': len(session_days),
        'weekdays_only': weekdays_only,
        'skipped': skipped,
        'no_bars': no_bars,
        'skipped_week': skipped_week,
    }
    return all_trades, meta


def print_summary(trades: list[Trade], meta: dict) -> None:
    inst = meta['instrument']
    mode = meta.get('profit_mode', 'baseline')
    bar_tf = meta.get('bar_tf', '')
    mode_label = f'{mode}' + (f' ({bar_tf} bars)' if bar_tf and bar_tf != '1h' else '')
    if bar_tf and mode.startswith('weekly') and bar_tf == '1h':
        mode_label = f'{mode} (1h bars)'
    if not trades:
        print(f'## {inst} ({mode_label}) — no trades\n', flush=True)
        return
    pnl = np.array([t.pnl_usd for t in trades], dtype=float)
    wins = pnl > 0
    reasons = pd.Series([t.reason_exit for t in trades]).value_counts()
    top_reasons = ', '.join(f'{k}={v}' for k, v in reasons.head(5).items())
    lines = [
        f'## Midnight-open flip — {inst} x1 · **{mode_label}**',
        '',
        f'- **DBN:** `{meta["dbn"]}`',
        f'- **Session range:** {meta["date_first"]} → {meta["date_last"]} '
        f'({meta["n_calendar_days"]} weekdays)',
        f'- Skipped: {meta["skipped"]} (flat first bar vs level), {meta["no_bars"]} (insufficient bars)'
        + (f' · bar_tf={meta.get("bar_tf", "1h")}' if meta.get('bar_tf') else '')
        + (
            f', {meta.get("skipped_week", 0)} (no weekly context)'
            if meta.get('skipped_week')
            else ''
        ),
        f'- **Trades:** {len(trades)}',
        f'- **Total P&L (USD):** {pnl.sum():,.2f}',
        f'- **Avg / trade:** {pnl.mean():,.2f}',
        f'- **Median / trade:** {np.median(pnl):,.2f}',
        f'- **Win rate:** {100.0 * wins.mean():.1f}%',
        f'- **Best / worst:** {pnl.max():,.2f} / {pnl.min():,.2f}',
        f'- **Exit reasons (top):** {top_reasons}',
        '',
    ]
    print('\n'.join(lines), flush=True)


def print_mfe_report(mfe_rows: list[dict], instrument: str) -> None:
    if not mfe_rows:
        print('No MFE rows.', flush=True)
        return
    pts = np.array([r['mfe_pts'] for r in mfe_rows], dtype=float)
    pct = [10, 25, 50, 75, 90]
    qs = np.percentile(pts, pct)
    print(f'\n## MFE at 09:45 — {instrument} (baseline legs entered before ORB)\n', flush=True)
    print(f'- **Legs:** {len(pts)}', flush=True)
    print(f'- **Mean MFE:** {pts.mean():.1f} pts', flush=True)
    for p, q in zip(pct, qs):
        usd = q * USD_PER_POINT[instrument.lower()]
        print(f'- **P{p} MFE:** {q:.1f} pts (${usd:,.0f})', flush=True)
    held = sum(1 for r in mfe_rows if r['held_past_orb'])
    print(f'- Still open past 09:45 (eventually): {held} ({100*held/len(mfe_rows):.1f}%)', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--instrument', choices=['mnq', 'nq', 'all'], default='mnq')
    ap.add_argument(
        '--profit-mode',
        choices=[
            'baseline',
            'baseline_sl11',
            'v2b_tp',
            'v2b_only',
            'fixed_tp',
            'compare',
            'compare_v2b',
            'compare_sl11',
            'atr_cross',
            'compare_atr_cross',
            'weekly_baseline',
            'weekly_baseline_4h',
            'weekly_baseline_1d',
            'compare_weekly',
            'compare_weekly_bars',
            'atr_cross_opp',
            'baseline_sl11_opp',
            'compare_opposites',
            'atr_fade_touch',
            'atr_fade_touch_reclaim',
            'compare_atr_fade_touch',
        ],
        default='atr_fade_touch',
        help='compare_opposites = atr_cross/sl11 vs their opposites',
    )
    ap.add_argument('--dbn-mnq', type=Path, default=mdata.DEFAULT_DBN)
    ap.add_argument('--dbn-nq', type=Path, default=mdata.DEFAULT_DBN_NQ)
    ap.add_argument('--include-weekends', action='store_true')
    ap.add_argument(
        '--fixed-tp-pts',
        type=float,
        default=50.0,
        help='Points from entry for --profit-mode fixed_tp (after ORB)',
    )
    ap.add_argument(
        '--sweep-fixed-tp',
        action='store_true',
        help='Sweep fixed_tp at 25/50/75/100 pts (MNQ, no flip after ORB)',
    )
    ap.add_argument(
        '--analyze-mfe',
        action='store_true',
        help='Print MFE percentiles for baseline (MNQ only unless --instrument set)',
    )
    args = ap.parse_args()
    weekdays_only = not args.include_weekends

    instruments = ['mnq', 'nq'] if args.instrument == 'all' else [args.instrument]
    dbn_for = {'mnq': args.dbn_mnq, 'nq': args.dbn_nq}
    if args.profit_mode == 'compare':
        modes = ['baseline', 'v2b_tp']
    elif args.profit_mode == 'compare_v2b':
        modes = ['baseline', 'v2b_tp', 'v2b_only']
    elif args.profit_mode == 'compare_sl11':
        modes = ['baseline', 'baseline_sl11']
    elif args.profit_mode == 'compare_atr_cross':
        modes = ['baseline', 'atr_cross']
    elif args.profit_mode == 'compare_weekly':
        modes = ['baseline', 'weekly_baseline']
    elif args.profit_mode == 'compare_weekly_bars':
        modes = ['baseline', 'weekly_baseline', 'weekly_baseline_4h', 'weekly_baseline_1d']
    elif args.profit_mode == 'compare_opposites':
        modes = ['atr_cross', 'atr_cross_opp', 'baseline_sl11', 'baseline_sl11_opp']
    elif args.profit_mode == 'compare_atr_fade_touch':
        modes = ['atr_fade_touch', 'atr_fade_touch_reclaim']
    else:
        modes = [args.profit_mode]

    for inst in instruments:
        dbn = dbn_for[inst]
        if not dbn.is_file():
            print(f'Missing DBN for {inst.upper()}: {dbn}', file=sys.stderr)
            return 1

        if args.sweep_fixed_tp:
            for pts in (25.0, 50.0, 75.0, 100.0):
                trades, meta = run_backtest(
                    inst, dbn, weekdays_only=weekdays_only,
                    profit_mode='fixed_tp', fixed_tp_pts=pts,
                )
                meta['profit_mode'] = f'fixed_tp_{pts:g}pt'
                print_summary(trades, meta)
            continue

        if args.analyze_mfe:
            gby = mdata.load_1m_by_ny_date(dbn.resolve(), inst)
            session_days = [d for d in sorted(gby) if not weekdays_only or d.weekday() < 5]
            mfe_rows: list[dict] = []
            for d in session_days:
                raw = gby.get(d)
                sess = mdata.slice_session_1m(raw, d)
                M = mdata.ny_midnight_open_px(sess)
                hourly = mdata.resample_1h_midnight_to_1600(raw, d)
                if hourly is None or len(hourly) < 2:
                    continue
                c0 = float(hourly.sort_index().iloc[0]['close'])
                if not np.isfinite(M) or abs(c0 - M) < 1e-9:
                    continue
                mfe_rows.extend(analyze_mfe_at_orb(d, M, hourly, sess))
            print_mfe_report(mfe_rows, inst.upper())
            continue

        for mode in modes:
            ftp = args.fixed_tp_pts if mode == 'fixed_tp' else 0.0
            trades, meta = run_backtest(
                inst, dbn, weekdays_only=weekdays_only,
                profit_mode=mode, fixed_tp_pts=ftp,
            )
            print_summary(trades, meta)
            if trades:
                out_csv = HERE / f'backtest_midnight_open_flip_trades_{inst}_{mode}.csv'
                pd.DataFrame(
                    [
                        {
                            'session': t.session.isoformat(),
                            'side': t.side,
                            'entry_time': str(t.entry_time),
                            'entry_px': t.entry_px,
                            'exit_time': str(t.exit_time),
                            'exit_px': t.exit_px,
                            'reason_exit': t.reason_exit,
                            'pnl_usd': round(t.pnl_usd, 2),
                        }
                        for t in trades
                    ]
                ).to_csv(out_csv, index=False)
                print(f'Wrote {out_csv}', flush=True)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
