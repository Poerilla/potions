"""Filter sweep for EURUSD 15m ST close-beyond-trail DCA and fade-on-flip DCA.

Filters
-------
- prev_week_mid align: long only below prior-week 50% ((H+L)/2); short only above
- prev_week_mid opposite: reverse
- ma50/150 align: long only if prior-day MA50>MA150; short only if MA50<MA150
- ma50/150 opposite: reverse

Fade weekly (as requested):
- align: fade bullish (short) only below mid; fade bearish (long) only above mid
- opposite: reverse

Fast pandas path (close-beyond-trail / close-only risk). Not broker stress MTM;
use to rank filters before any Engine confirmation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

from .eurusd_intraday_ma_st_research import compute_supertrend_fast
from .eurusd_intraday_st_dca_replay import _resample_15m
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
LDN = "Europe/London"
NY_TZ = pytz.timezone(NY)
LDN_TZ = pytz.timezone(LDN)
LONDON_OPEN = time(8, 0)
NY_CLOSE = time(16, 0)
POINT_VALUE = 50_000.0  # half-lot unit
FEE = 0.75
ADD_QTY = 1.0
MAX_ADDS = 5
HALF_SPREAD = 0.5 * 1e-5 * 10
OUT_DEFAULT = REPO / "live" / "state" / "eurusd_intraday_st_dca_filters"


@dataclass
class Trade:
    book: str
    filter_name: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: float
    reason: str
    usd: float


def _session_mask(index: pd.DatetimeIndex) -> np.ndarray:
    ny = index.tz_convert(NY)
    mask = np.zeros(len(index), dtype=bool)
    day_keys = pd.Index(ny.date)
    pos = np.arange(len(index))
    for d in pd.unique(day_keys):
        idxs = pos[day_keys == d]
        lo = pd.Timestamp(LDN_TZ.localize(datetime.combine(d, LONDON_OPEN)).astimezone(NY_TZ))
        hi = pd.Timestamp(NY_TZ.localize(datetime.combine(d, NY_CLOSE)))
        ix = index[idxs]
        mask[idxs] = (ix >= lo) & (ix <= hi)
    return mask


def _prev_week_mid(m15: pd.DataFrame) -> pd.Series:
    """Prior completed ISO week midpoint ((H+L)/2), causal on 15m bars."""
    ny = m15.index.tz_convert(NY)
    weeks = ny.to_period("W-SUN")
    weekly = (
        m15.assign(_week=weeks)
        .groupby("_week", sort=True)
        .agg(high=("high", "max"), low=("low", "min"))
    )
    weekly["mid"] = (weekly["high"] + weekly["low"]) * 0.5
    # shift so bar in week W sees week W-1 mid
    weekly["prev_mid"] = weekly["mid"].shift(1)
    mapped = weeks.map(weekly["prev_mid"])
    return pd.Series(mapped.to_numpy(dtype=float), index=m15.index)


def _daily_ma_regime(daily: pd.DataFrame, m15_index: pd.DatetimeIndex) -> pd.Series:
    """Prior-day MA50 vs MA150 regime: 1 bull, -1 bear, 0 unknown. Causal on 15m."""
    d = daily.copy()
    if d.index.tz is None:
        d.index = d.index.tz_localize(NY)
    else:
        d.index = d.index.tz_convert(NY)
    d = d.sort_index()
    close = pd.to_numeric(d["close"], errors="coerce")
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    regime = pd.Series(0, index=d.index, dtype=int)
    regime = regime.mask(ma50 > ma150, 1).mask(ma50 < ma150, -1)
    # prior completed day only
    regime = regime.shift(1)
    # map each 15m bar to prior day's regime via asof
    day_index = m15_index.tz_convert(NY).normalize()
    # build daily series reindexed forward to 15m
    daily_reg = regime.copy()
    daily_reg.index = daily_reg.index.normalize()
    out = day_index.map(daily_reg)
    return pd.Series(pd.to_numeric(out, errors="coerce").fillna(0).astype(int).to_numpy(), index=m15_index)


def _pnl(side: str, entry: float, exit_: float, qty: float) -> float:
    if side == "long":
        pts = (exit_ - entry) * qty
    else:
        pts = (entry - exit_) * qty
    return pts * POINT_VALUE - FEE * abs(qty)


def _summarize(trades: List[Trade], name: str) -> dict:
    if not trades:
        return {
            "strategy": name,
            "trades": 0,
            "units": 0.0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "closed_dd_usd": 0.0,
            "net_over_closed_dd": 0.0,
            "avg_usd": 0.0,
        }
    usd = np.array([t.usd for t in trades], dtype=float)
    qty = np.array([t.qty for t in trades], dtype=float)
    eq = np.cumsum(usd)
    peak = np.maximum.accumulate(eq)
    closed_dd = float((eq - peak).min())
    wins = float(usd[usd > 0].sum())
    losses = float(-usd[usd < 0].sum())
    pf = wins / losses if losses > 0 else float("inf")
    net = float(usd.sum())
    return {
        "strategy": name,
        "trades": int(len(trades)),
        "units": float(qty.sum()),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else None,
        "closed_dd_usd": round(closed_dd, 2),
        "net_over_closed_dd": round(net / abs(closed_dd), 3) if closed_dd else 0.0,
        "avg_usd": round(net / len(trades), 2),
    }


Gate = Callable[[str, int, float, float, int], bool]


def _gate_none(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    return True


def _gate_week_align_follow(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    if not np.isfinite(week_mid):
        return False
    if side == "long":
        return px < week_mid
    return px > week_mid


def _gate_week_opposite_follow(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    if not np.isfinite(week_mid):
        return False
    if side == "long":
        return px > week_mid
    return px < week_mid


def _gate_ma_align_follow(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    if ma_reg == 0:
        return False
    if side == "long":
        return ma_reg == 1
    return ma_reg == -1


def _gate_ma_opposite_follow(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    if ma_reg == 0:
        return False
    if side == "long":
        return ma_reg == -1
    return ma_reg == 1


def _gate_week_align_fade(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    """Fade bullish (short) only below mid; fade bearish (long) only above mid."""
    if not np.isfinite(week_mid):
        return False
    if side == "short":  # fading bullish flip
        return px < week_mid
    return px > week_mid  # fading bearish flip → long only above mid


def _gate_week_opposite_fade(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    if not np.isfinite(week_mid):
        return False
    if side == "short":
        return px > week_mid
    return px < week_mid


def _gate_ma_align_fade(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    """Fade with MA: long fades only in bull MA; short fades only in bear MA."""
    if ma_reg == 0:
        return False
    if side == "long":
        return ma_reg == 1
    return ma_reg == -1


def _gate_ma_opposite_fade(side: str, i: int, px: float, week_mid: float, ma_reg: int) -> bool:
    if ma_reg == 0:
        return False
    if side == "long":
        return ma_reg == -1
    return ma_reg == 1


def run_follow_close(
    st: pd.DataFrame,
    week_mid: np.ndarray,
    ma_reg: np.ndarray,
    in_sess: np.ndarray,
    gate: Gate,
    filter_name: str,
) -> List[Trade]:
    trail = st["supertrend"].to_numpy(dtype=float)
    trend = st["supertrend_trend"].to_numpy(dtype=float)
    o = st["open"].to_numpy(dtype=float)
    c = st["close"].to_numpy(dtype=float)
    index = st.index
    trades: List[Trade] = []
    side: Optional[str] = None
    entries: List[Tuple[int, float, float]] = []
    adds = 0

    def flatten(i: int, px: float, reason: str) -> None:
        nonlocal side, entries, adds
        if not entries:
            side = None
            return
        qty = sum(q for _, _, q in entries)
        entry_px = sum(p * q for _, p, q in entries) / qty
        usd = _pnl(side, entry_px, px, qty)
        trades.append(
            Trade("follow_close", filter_name, side, index[entries[0][0]], index[i], entry_px, px, qty, reason, usd)
        )
        side = None
        entries = []
        adds = 0

    for i in range(1, len(st)):
        if not in_sess[i]:
            if side is not None:
                px = o[i] - HALF_SPREAD if side == "long" else o[i] + HALF_SPREAD
                flatten(i, px, "session_end")
            continue

        t_now = int(trend[i]) if not np.isnan(trend[i]) else 0
        t_prev = int(trend[i - 1]) if not np.isnan(trend[i - 1]) else 0
        tr = trail[i]

        if side == "long":
            if t_now == -1 or (np.isfinite(tr) and c[i] < tr):
                flatten(i, c[i] - HALF_SPREAD, "trail_close")
                # fall through — may re-enter same bar only if flat and gate ok
            else:
                if adds < MAX_ADDS and gate(side, i, c[i], week_mid[i], int(ma_reg[i])):
                    entries.append((i, o[i] + HALF_SPREAD, ADD_QTY))
                    adds += 1
                continue
        elif side == "short":
            if t_now == 1 or (np.isfinite(tr) and c[i] > tr):
                flatten(i, c[i] + HALF_SPREAD, "trail_close")
            else:
                if adds < MAX_ADDS and gate(side, i, c[i], week_mid[i], int(ma_reg[i])):
                    entries.append((i, o[i] - HALF_SPREAD, ADD_QTY))
                    adds += 1
                continue

        # flat — enter if prior+current agree
        if side is not None:
            continue
        if t_prev == 1 and t_now == 1:
            want = "long"
        elif t_prev == -1 and t_now == -1:
            want = "short"
        else:
            continue
        px = o[i] + HALF_SPREAD if want == "long" else o[i] - HALF_SPREAD
        if not gate(want, i, px, week_mid[i], int(ma_reg[i])):
            continue
        side = want
        entries = [(i, px, ADD_QTY)]
        adds = 1

    if side is not None:
        flatten(len(st) - 1, c[-1], "eod")
    return trades


def run_fade(
    st: pd.DataFrame,
    week_mid: np.ndarray,
    ma_reg: np.ndarray,
    in_sess: np.ndarray,
    gate: Gate,
    filter_name: str,
) -> List[Trade]:
    trail = st["supertrend"].to_numpy(dtype=float)
    trend = st["supertrend_trend"].to_numpy(dtype=float)
    o = st["open"].to_numpy(dtype=float)
    c = st["close"].to_numpy(dtype=float)
    index = st.index
    trades: List[Trade] = []
    side: Optional[str] = None
    entries: List[Tuple[int, float, float]] = []
    adds = 0
    stop_px: Optional[float] = None
    target_trail_side: Optional[str] = None  # ST side required for thesis

    def flatten(i: int, px: float, reason: str) -> None:
        nonlocal side, entries, adds, stop_px, target_trail_side
        if not entries:
            side = None
            stop_px = None
            target_trail_side = None
            return
        qty = sum(q for _, _, q in entries)
        entry_px = sum(p * q for _, p, q in entries) / qty
        usd = _pnl(side, entry_px, px, qty)
        trades.append(
            Trade("fade", filter_name, side, index[entries[0][0]], index[i], entry_px, px, qty, reason, usd)
        )
        side = None
        entries = []
        adds = 0
        stop_px = None
        target_trail_side = None

    for i in range(1, len(st)):
        if not in_sess[i]:
            if side is not None:
                px = o[i] - HALF_SPREAD if side == "long" else o[i] + HALF_SPREAD
                flatten(i, px, "session_end")
            continue

        t_now = int(trend[i]) if not np.isnan(trend[i]) else 0
        t_prev = int(trend[i - 1]) if not np.isnan(trend[i - 1]) else 0
        tr = trail[i]
        flipped_bear = t_prev == 1 and t_now == -1
        flipped_bull = t_prev == -1 and t_now == 1

        if side is not None:
            thesis_ok = (side == "long" and t_now == -1) or (side == "short" and t_now == 1)
            if not thesis_ok:
                flatten(i, c[i] - HALF_SPREAD if side == "long" else c[i] + HALF_SPREAD, "thesis_end")
            elif stop_px is not None and (
                (side == "long" and c[i] < stop_px) or (side == "short" and c[i] > stop_px)
            ):
                flatten(i, c[i] - HALF_SPREAD if side == "long" else c[i] + HALF_SPREAD, "stop")
            elif np.isfinite(tr) and (
                (side == "long" and c[i] >= tr) or (side == "short" and c[i] <= tr)
            ):
                flatten(i, tr - HALF_SPREAD if side == "long" else tr + HALF_SPREAD, "target")
            else:
                if adds < MAX_ADDS and gate(side, i, c[i], week_mid[i], int(ma_reg[i])):
                    px = o[i] + HALF_SPREAD if side == "long" else o[i] - HALF_SPREAD
                    entries.append((i, px, ADD_QTY))
                    adds += 1
                continue

        if side is not None:
            continue
        if not (flipped_bear or flipped_bull):
            continue
        want = "long" if flipped_bear else "short"
        px = o[i] + HALF_SPREAD if want == "long" else o[i] - HALF_SPREAD
        if not gate(want, i, px, week_mid[i], int(ma_reg[i])):
            continue
        if not np.isfinite(tr):
            continue
        r = abs(tr - px)
        if r <= 0:
            continue
        side = want
        entries = [(i, px, ADD_QTY)]
        adds = 1
        stop_px = px - r if want == "long" else px + r
        target_trail_side = "bear" if want == "long" else "bull"

    if side is not None:
        flatten(len(st) - 1, c[-1], "eod")
    return trades


FOLLOW_GATES = [
    ("none", _gate_none),
    ("week_mid_align", _gate_week_align_follow),
    ("week_mid_opposite", _gate_week_opposite_follow),
    ("ma50_150_align", _gate_ma_align_follow),
    ("ma50_150_opposite", _gate_ma_opposite_follow),
]

FADE_GATES = [
    ("none", _gate_none),
    ("week_mid_align", _gate_week_align_fade),
    ("week_mid_opposite", _gate_week_opposite_fade),
    ("ma50_150_align", _gate_ma_align_fade),
    ("ma50_150_opposite", _gate_ma_opposite_fade),
]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD ST DCA filter sweep")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args(argv)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    print("Loading EURUSD...", flush=True)
    one_m_path, daily_path = ensure_eurusd_platform_files(REPO)
    gby = load_fx_1m_by_ny_date(one_m_path, "EURUSD")
    one_m = concat_all_1m(gby).sort_index()
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    m15 = _resample_15m(one_m)
    print("  15m bars:", len(m15), flush=True)

    print("  SuperTrend + session + week mid + MA regime...", flush=True)
    st = compute_supertrend_fast(m15, atr_len=14, multiplier=3.0)
    in_sess = _session_mask(st.index)
    week_mid = _prev_week_mid(st).to_numpy(dtype=float)
    daily = pd.read_csv(daily_path)
    # normalize daily columns
    if "timestamp" in daily.columns:
        daily["ts"] = pd.to_datetime(daily["timestamp"], utc=True)
        daily = daily.set_index("ts")
    elif "date" in daily.columns:
        daily["ts"] = pd.to_datetime(daily["date"])
        daily = daily.set_index("ts")
    ma_reg = _daily_ma_regime(daily, st.index).to_numpy(dtype=int)

    rows = []
    all_trades = []

    print("Follow close-beyond-trail filters...", flush=True)
    for name, gate in FOLLOW_GATES:
        trades = run_follow_close(st, week_mid, ma_reg, in_sess, gate, name)
        s = _summarize(trades, "follow_close|%s" % name)
        rows.append(s)
        all_trades.extend(trades)
        print(
            "  %-22s net=$%s dd=$%s n=%d WR=%.1f Net/DD=%.2f"
            % (
                name,
                f"{s['net_usd']:,.0f}",
                f"{s['closed_dd_usd']:,.0f}",
                s["trades"],
                s["win_rate_pct"],
                s["net_over_closed_dd"],
            ),
            flush=True,
        )

    print("Fade-on-flip DCA filters...", flush=True)
    for name, gate in FADE_GATES:
        trades = run_fade(st, week_mid, ma_reg, in_sess, gate, name)
        s = _summarize(trades, "fade|%s" % name)
        rows.append(s)
        all_trades.extend(trades)
        print(
            "  %-22s net=$%s dd=$%s n=%d WR=%.1f Net/DD=%.2f"
            % (
                name,
                f"{s['net_usd']:,.0f}",
                f"{s['closed_dd_usd']:,.0f}",
                s["trades"],
                s["win_rate_pct"],
                s["net_over_closed_dd"],
            ),
            flush=True,
        )

    summary = pd.DataFrame(rows).sort_values(["net_usd"], ascending=False)
    summary_path = out / "filter_sweep.csv"
    summary.to_csv(summary_path, index=False)

    # mark candidates vs FX baseline rough bar
    baseline_net = 23534.0
    lines = [
        "# EURUSD 15m ST DCA — filter sweep",
        "",
        "Close-beyond-trail follow + fade-on-flip. Pandas path (closed-equity DD only).",
        "Unit = 0.5 lot (PV $50k), fee $0.75/unit. Window %s → %s." % (args.start, args.end),
        "",
        "| Strategy | Filter | Net | Closed DD | Net/DD | Trades | WR |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        book, filt = str(r["strategy"]).split("|", 1)
        flag = " **" if r["net_usd"] > baseline_net and r["net_over_closed_dd"] >= 1.0 else ""
        lines.append(
            "| %s | %s | $%s | $%s | %.2f | %d | %.1f%%%s |"
            % (
                book,
                filt,
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_closed_dd"],
                r["trades"],
                r["win_rate_pct"],
                flag,
            )
        )
    lines.extend(
        [
            "",
            "Filters:",
            "- **week_mid_align (follow):** long only below prior-week 50%; short only above.",
            "- **week_mid_opposite (follow):** reverse of align.",
            "- **week_mid_align (fade):** fade bullish (short) only below mid; fade bearish (long) only above.",
            "- **week_mid_opposite (fade):** reverse.",
            "- **ma50_150_align:** trade/fade with prior-day MA50 vs MA150 regime.",
            "- **ma50_150_opposite:** against that regime.",
            "",
            "`**` = net > FX baseline (~$23.5k) and Net/closed-DD ≥ 1.0 (still needs broker stress).",
            "",
            "CSV: `%s`" % summary_path,
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "summary.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
