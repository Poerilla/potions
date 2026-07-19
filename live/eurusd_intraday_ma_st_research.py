"""EURUSD intraday research: 3-MA + PMC, 3m/5m ST break, 15m ST DCA.

Pure pandas path study (completed-bar causal). Session: London cash open
(08:00 Europe/London) → NY cash close (16:00 America/New_York).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_prev_month_close_map


def compute_supertrend_fast(df: pd.DataFrame, atr_len: int = 14, multiplier: float = 3.0) -> pd.DataFrame:
    """NumPy SuperTrend (same rules as build_ym_1m_atr_supertrend_sample.compute_supertrend)."""
    out = df.copy()
    high = out["high"].to_numpy(dtype=float)
    low = out["low"].to_numpy(dtype=float)
    close = out["close"].to_numpy(dtype=float)
    n = len(out)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = pd.Series(tr).ewm(alpha=1.0 / float(atr_len), adjust=False, min_periods=atr_len).mean().to_numpy()
    hl2 = (high + low) * 0.5
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    final_upper = np.empty(n, dtype=float)
    final_lower = np.empty(n, dtype=float)
    trend = np.empty(n, dtype=np.int64)
    st = np.full(n, np.nan, dtype=float)
    for i in range(n):
        if i == 0 or np.isnan(atr[i]):
            final_upper[i] = basic_upper[i]
            final_lower[i] = basic_lower[i]
            trend[i] = 1
            continue
        if np.isnan(final_upper[i - 1]) or basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]
        if np.isnan(final_lower[i - 1]) or basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]
        prev_trend = int(trend[i - 1])
        if prev_trend == 1:
            trend[i] = -1 if close[i] < final_lower[i] else 1
        else:
            trend[i] = 1 if close[i] > final_upper[i] else -1
        st[i] = final_lower[i] if trend[i] == 1 else final_upper[i]
    out["atr"] = atr
    out["supertrend"] = st
    out["supertrend_trend"] = trend
    return out


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
LDN = "Europe/London"
NY_TZ = pytz.timezone(NY)
LDN_TZ = pytz.timezone(LDN)
POINT_VALUE = 100_000.0
FEE_PER_UNIT = 1.50
TICK = 1e-5
HALF_SPREAD = 0.5 * TICK * 10  # ~0.5 pip in price
LONDON_OPEN = time(8, 0)
NY_CLOSE = time(16, 0)

OUT_DEFAULT = REPO / "live" / "state" / "eurusd_intraday_ma_st_research"


@dataclass
class Trade:
    strategy: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: float
    reason: str
    points: float
    usd: float


def _resample(df_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    rule = "%dmin" % minutes
    out = (
        df_1m.resample(rule, label="right", closed="right")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
        .dropna(subset=["open"])
    )
    return out


def _session_mask(index: pd.DatetimeIndex) -> np.ndarray:
    """True when bar timestamp is inside London open → NY close for its NY calendar day."""
    if index.tz is None:
        raise ValueError("index must be tz-aware")
    ny = index.tz_convert(NY)
    mask = np.zeros(len(index), dtype=bool)
    # Group by NY calendar date; session = that day's London 08:00 → NY 16:00.
    day_keys = pd.Index(ny.date)
    pos = np.arange(len(index))
    for d in pd.unique(day_keys):
        idxs = pos[day_keys == d]
        lo = pd.Timestamp(LDN_TZ.localize(datetime.combine(d, LONDON_OPEN)).astimezone(NY_TZ))
        hi = pd.Timestamp(NY_TZ.localize(datetime.combine(d, NY_CLOSE)))
        ix = index[idxs]
        mask[idxs] = (ix >= lo) & (ix <= hi)
    return mask


def _attach_pmc(df: pd.DataFrame, pmc_map: Dict[Tuple[int, int], float]) -> pd.Series:
    ny = df.index.tz_convert(NY)
    keys = list(zip(ny.year, ny.month))
    return pd.Series([pmc_map.get(k, np.nan) for k in keys], index=df.index)


def _pnl(side: str, entry: float, exit_: float, qty: float) -> Tuple[float, float]:
    if side == "long":
        pts = (exit_ - entry) * qty
    else:
        pts = (entry - exit_) * qty
    usd = pts * POINT_VALUE - FEE_PER_UNIT * abs(qty)
    return pts, usd


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
            "stress_dd_usd": 0.0,
            "net_over_stress": 0.0,
            "avg_usd": 0.0,
        }
    df = pd.DataFrame(
        [
            {
                "usd": t.usd,
                "qty": t.qty,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
                "side": t.side,
                "entry": t.entry,
                "exit": t.exit,
            }
            for t in trades
        ]
    )
    eq = df["usd"].cumsum()
    peak = eq.cummax()
    closed_dd = float((eq - peak).min())
    # Proxy stress ≈ closed path (no bar path in this fast pass)
    stress = closed_dd
    wins = df.loc[df["usd"] > 0, "usd"].sum()
    losses = -df.loc[df["usd"] < 0, "usd"].sum()
    pf = float(wins / losses) if losses > 0 else float("inf")
    net = float(df["usd"].sum())
    return {
        "strategy": name,
        "trades": int(len(df)),
        "units": float(df["qty"].abs().sum()),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((df["usd"] > 0).mean()), 2),
        "profit_factor": round(pf, 3) if np.isfinite(pf) else None,
        "closed_dd_usd": round(closed_dd, 2),
        "stress_dd_usd": round(stress, 2),
        "net_over_stress": round(net / abs(stress), 3) if stress else 0.0,
        "avg_usd": round(float(df["usd"].mean()), 2),
    }


# ---------- 3-MA + PMC ----------


def run_ma3(
    bars: pd.DataFrame,
    pmc: pd.Series,
    *,
    fast: int,
    mid: int,
    slow: int,
    mode: str,  # follow | opposing
    name: str,
) -> List[Trade]:
    """EMA stack on completed bars; enter on stack flip; exit on stack break / session end."""
    df = bars
    ema_f = df["close"].ewm(span=fast, adjust=False).mean().to_numpy()
    ema_m = df["close"].ewm(span=mid, adjust=False).mean().to_numpy()
    ema_s = df["close"].ewm(span=slow, adjust=False).mean().to_numpy()
    bull = (ema_f > ema_m) & (ema_m > ema_s)
    bear = (ema_f < ema_m) & (ema_m < ema_s)
    bull_sig = np.roll(bull, 1)
    bear_sig = np.roll(bear, 1)
    bull_sig[0] = False
    bear_sig[0] = False
    in_sess = df["in_session"].to_numpy(dtype=bool)
    opens = df["open"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    pmc_v = pmc.reindex(df.index).to_numpy(dtype=float)
    index = df.index

    trades: List[Trade] = []
    side: Optional[str] = None
    entry = 0.0
    entry_i = 0
    qty = 1.0

    for i in range(len(df)):
        if not in_sess[i]:
            if side is not None:
                px = opens[i] - HALF_SPREAD if side == "long" else opens[i] + HALF_SPREAD
                pts, usd = _pnl(side, entry, px, qty)
                trades.append(Trade(name, side, index[entry_i], index[i], entry, px, qty, "session_end", pts, usd))
                side = None
            continue

        if side == "long" and not bull_sig[i]:
            px = opens[i] - HALF_SPREAD
            pts, usd = _pnl(side, entry, px, qty)
            trades.append(Trade(name, side, index[entry_i], index[i], entry, px, qty, "stack_break", pts, usd))
            side = None
        elif side == "short" and not bear_sig[i]:
            px = opens[i] + HALF_SPREAD
            pts, usd = _pnl(side, entry, px, qty)
            trades.append(Trade(name, side, index[entry_i], index[i], entry, px, qty, "stack_break", pts, usd))
            side = None

        if side is not None:
            continue

        p = pmc_v[i]
        if np.isnan(p):
            continue
        above = opens[i] > p
        below = opens[i] < p
        if mode == "follow":
            if bull_sig[i] and above:
                side, entry_i, entry = "long", i, opens[i] + HALF_SPREAD
            elif bear_sig[i] and below:
                side, entry_i, entry = "short", i, opens[i] - HALF_SPREAD
        else:
            if bull_sig[i] and below:
                side, entry_i, entry = "long", i, opens[i] + HALF_SPREAD
            elif bear_sig[i] and above:
                side, entry_i, entry = "short", i, opens[i] - HALF_SPREAD

    if side is not None:
        px = closes[-1]
        pts, usd = _pnl(side, entry, px, qty)
        trades.append(Trade(name, side, index[entry_i], index[-1], entry, px, qty, "eod", pts, usd))
    return trades

# ---------- SuperTrend break ----------


def run_st_break(
    bars: pd.DataFrame,
    *,
    atr_len: int,
    atr_mult: float,
    name: str,
) -> List[Trade]:
    """Long when bearish ST broken; short when bullish ST broken; SL at new trail; session only."""
    print("  compute_supertrend...", flush=True)
    st = compute_supertrend_fast(bars, atr_len=atr_len, multiplier=atr_mult)
    st_now = st["supertrend"].to_numpy(dtype=float)
    trend_now = st["supertrend_trend"].to_numpy(dtype=float)
    st_prev = np.roll(st_now, 1)
    trend_prev = np.roll(trend_now, 1)
    st_prev[0] = np.nan
    trend_prev[0] = np.nan
    hi = st["high"].to_numpy(dtype=float)
    lo = st["low"].to_numpy(dtype=float)
    o = st["open"].to_numpy(dtype=float)
    c = st["close"].to_numpy(dtype=float)
    in_sess = bars["in_session"].to_numpy(dtype=bool)
    index = st.index

    trades: List[Trade] = []
    side: Optional[str] = None
    entry = 0.0
    entry_i = 0
    qty = 1.0

    for i in range(1, len(st)):
        if not in_sess[i]:
            if side is not None:
                px = o[i] - HALF_SPREAD if side == "long" else o[i] + HALF_SPREAD
                pts, usd = _pnl(side, entry, px, qty)
                trades.append(Trade(name, side, index[entry_i], index[i], entry, px, qty, "session_end", pts, usd))
                side = None
            continue

        trail = st_prev[i]
        tr_prev = trend_prev[i]
        if np.isnan(trail) or np.isnan(tr_prev):
            continue

        cur_trail = st_now[i]
        if side is not None and not np.isnan(cur_trail):
            if side == "long" and lo[i] <= cur_trail:
                px = min(o[i], cur_trail) - HALF_SPREAD
                pts, usd = _pnl(side, entry, px, qty)
                trades.append(Trade(name, side, index[entry_i], index[i], entry, px, qty, "trail_stop", pts, usd))
                side = None
            elif side == "short" and hi[i] >= cur_trail:
                px = max(o[i], cur_trail) + HALF_SPREAD
                pts, usd = _pnl(side, entry, px, qty)
                trades.append(Trade(name, side, index[entry_i], index[i], entry, px, qty, "trail_stop", pts, usd))
                side = None

        if side is not None:
            continue

        if int(tr_prev) == -1 and hi[i] >= trail:
            side = "long"
            entry_i = i
            entry = trail + HALF_SPREAD
        elif int(tr_prev) == 1 and lo[i] <= trail:
            side = "short"
            entry_i = i
            entry = trail - HALF_SPREAD

    if side is not None:
        px = c[-1]
        pts, usd = _pnl(side, entry, px, qty)
        trades.append(Trade(name, side, index[entry_i], index[-1], entry, px, qty, "eod", pts, usd))
    return trades

# ---------- 15m ST DCA ----------


def run_st_dca(
    bars: pd.DataFrame,
    *,
    atr_len: int,
    atr_mult: float,
    add_qty: float,
    max_adds: int,
    name: str,
) -> List[Trade]:
    """DCA 0.5 lots up to max_adds while ST side holds; exit all on trail hit."""
    print("  compute_supertrend...", flush=True)
    st = compute_supertrend_fast(bars, atr_len=atr_len, multiplier=atr_mult)
    trail = st["supertrend"].to_numpy(dtype=float)
    trend = st["supertrend_trend"].to_numpy(dtype=float)
    trend_sig = np.roll(trend, 1)
    trail_sig = np.roll(trail, 1)
    trend_sig[0] = np.nan
    trail_sig[0] = np.nan
    hi = st["high"].to_numpy(dtype=float)
    lo = st["low"].to_numpy(dtype=float)
    o = st["open"].to_numpy(dtype=float)
    c = st["close"].to_numpy(dtype=float)
    in_sess = bars["in_session"].to_numpy(dtype=bool)
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
        entry_i = entries[0][0]
        pts, usd = _pnl(side, entry_px, px, qty)
        trades.append(Trade(name, side, index[entry_i], index[i], entry_px, px, qty, reason, pts, usd))
        side = None
        entries = []
        adds = 0

    for i in range(1, len(st)):
        if not in_sess[i]:
            if side is not None:
                px = o[i] - HALF_SPREAD if side == "long" else o[i] + HALF_SPREAD
                flatten(i, px, "session_end")
            continue

        tprev = trend_sig[i]
        if np.isnan(tprev) or np.isnan(trail_sig[i]):
            continue

        tr = trail[i]
        if side == "long" and not np.isnan(tr) and lo[i] <= tr:
            flatten(i, min(o[i], tr) - HALF_SPREAD, "trail_stop")
            continue
        if side == "short" and not np.isnan(tr) and hi[i] >= tr:
            flatten(i, max(o[i], tr) + HALF_SPREAD, "trail_stop")
            continue

        want = "long" if int(tprev) == 1 else "short" if int(tprev) == -1 else None
        if want is None:
            continue

        if side is not None and side != want:
            flatten(i, o[i] - HALF_SPREAD if side == "long" else o[i] + HALF_SPREAD, "st_flip")

        if side is None:
            side = want
            px = o[i] + HALF_SPREAD if side == "long" else o[i] - HALF_SPREAD
            entries.append((i, px, add_qty))
            adds = 1
        elif side == want and adds < max_adds:
            px = o[i] + HALF_SPREAD if side == "long" else o[i] - HALF_SPREAD
            entries.append((i, px, add_qty))
            adds += 1

    if side is not None:
        flatten(len(st) - 1, c[-1], "eod")
    return trades


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD intraday MA / ST research")
    parser.add_argument("--start", type=str, default="2015-01-01")
    parser.add_argument("--end", type=str, default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--skip-st", action="store_true")
    parser.add_argument("--skip-ma", action="store_true")
    parser.add_argument("--skip-dca", action="store_true")
    args = parser.parse_args(argv)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)

    print("Loading EURUSD 1m...", flush=True)
    one_m_path, daily_path = ensure_eurusd_platform_files(REPO)
    gby = load_fx_1m_by_ny_date(one_m_path, "EURUSD")
    one_m = concat_all_1m(gby).sort_index()
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    print("  bars:", f"{len(one_m):,}", flush=True)
    pmc_map = load_prev_month_close_map(daily_path)

    summaries = []
    all_trades = {}

    # Prepare 5m for MA (intraday)
    print("Building 5m + session mask...", flush=True)
    m5 = _resample(one_m, 5)
    print("  computing session mask (5m)...", flush=True)
    m5["in_session"] = _session_mask(m5.index)
    pmc5 = _attach_pmc(m5, pmc_map)

    if not args.skip_ma:
        print("Running 3-MA + PMC variants...", flush=True)
        for mode in ("follow", "opposing"):
            name = "ma3_ema9_21_50_5m_%s_pmc" % mode
            trades = run_ma3(m5, pmc5, fast=9, mid=21, slow=50, mode=mode, name=name)
            all_trades[name] = trades
            s = _summarize(trades, name)
            summaries.append(s)
            print(" ", s, flush=True)
        # Also 15m MA
        m15 = _resample(one_m, 15)
        m15["in_session"] = _session_mask(m15.index)
        pmc15 = _attach_pmc(m15, pmc_map)
        for mode in ("follow", "opposing"):
            name = "ma3_ema9_21_50_15m_%s_pmc" % mode
            trades = run_ma3(m15, pmc15, fast=9, mid=21, slow=50, mode=mode, name=name)
            all_trades[name] = trades
            s = _summarize(trades, name)
            summaries.append(s)
            print(" ", s, flush=True)

    if not args.skip_st:
        for minutes in (3, 5):
            print("Building %dm SuperTrend break..." % minutes, flush=True)
            b = _resample(one_m, minutes)
            b["in_session"] = _session_mask(b.index)
            # Restrict to session bars + small pad for ST warmup continuity — keep all bars for ST continuity
            name = "st_break_%dm_atr14x3_london_ny" % minutes
            trades = run_st_break(b, atr_len=14, atr_mult=3.0, name=name)
            all_trades[name] = trades
            s = _summarize(trades, name)
            summaries.append(s)
            print(" ", s, flush=True)

    # Always run 15m DCA (user asked if ST break doesn't work — run anyway for comparison)
    if not args.skip_dca:
        print("Building 15m ST DCA...", flush=True)
        m15 = _resample(one_m, 15)
        m15["in_session"] = _session_mask(m15.index)
        name = "st_dca_15m_atr14x3_0p5x5_london_ny"
        trades = run_st_dca(m15, atr_len=14, atr_mult=3.0, add_qty=0.5, max_adds=5, name=name)
        all_trades[name] = trades
        s = _summarize(trades, name)
        summaries.append(s)
        print(" ", s, flush=True)

    summary_df = pd.DataFrame(summaries).sort_values("net_over_stress", ascending=False)
    summary_df.to_csv(out / "summary.csv", index=False)

    # Write trades for top / all
    for name, trades in all_trades.items():
        if not trades:
            continue
        pd.DataFrame([t.__dict__ for t in trades]).to_csv(out / ("trades_%s.csv" % name), index=False)

    lines = [
        "# EURUSD Intraday MA / SuperTrend Research",
        "",
        "Window: **%s → %s** (America/New_York). Session: London 08:00 → NY 16:00."
        % (args.start, args.end),
        "",
        "Fee $%.2f/unit · ~0.5 pip half-spread · completed-bar causal pandas path." % FEE_PER_UNIT,
        "",
        "| Strategy | Trades | Net | Closed DD | Net/DD | Win% | PF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary_df.iterrows():
        lines.append(
            "| %s | %d | $%s | $%s | %s | %s | %s |"
            % (
                r["strategy"],
                int(r["trades"]),
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_stress"],
                r["win_rate_pct"],
                r["profit_factor"],
            )
        )
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "- **3-MA:** EMA 9/21/50 stack; long on bull stack, short on bear; "
            "`follow` = side with PMC, `opposing` = fade PMC.",
            "- **ST break 3m/5m:** long when prior bearish trail taken; short when prior bullish trail taken; "
            "SL trails at current SuperTrend; flatten at NY close.",
            "- **15m ST DCA:** 0.5 lot adds while ST side holds, max 5; exit on trail hit.",
            "",
            "Baseline FX sleeve (promoted): Hourly ST+PMC 25/75 MA bull ~$23.5k / 1.49 Net/Stress (full sample).",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "run_meta.json").write_text(
        json.dumps({"start": args.start, "end": args.end, "fee": FEE_PER_UNIT}, indent=2),
        encoding="utf-8",
    )
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
