"""f30-week: session-prev extreme + stop = extreme ± p·ATR (clear would-be winners).

Charts previously used the prior *calendar* NY date with bars — Mondays often
got **Sunday** (thin session). Here prev = prior weekday session (Sun/Sat → Friday).

Stop:
  long:  prev_session_low  - p * hourly_ATR(14)
  short: prev_session_high + p * hourly_ATR(14)

Sweep p including p* ≈ 2.80 that clears all 41 would-be-winner paths.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .eurusd_hourly_st_daybias_dca import (
    ADD_QTY,
    HALF_SPREAD,
    MAX_ADDS,
    NY,
    _month_key,
    _pnl,
    _week_key,
    bias_for_day,
    build_day_tables,
    entry_level,
)
from .eurusd_intraday_ma_st_research import compute_supertrend_fast
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "eurusd_st_daybias_f30_wide_sl"
FRAC = 0.30
# From would-be-winner MAE analysis (session prev): max p_need + epsilon
P_STAR = 2.80


@dataclass
class Lot:
    side: str
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    qty: float


@dataclass
class Campaign:
    side: str
    period_key: str
    lots: List[Lot] = field(default_factory=list)
    entry_days: List[date] = field(default_factory=list)


@dataclass
class ClosedTrade:
    strategy: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: float
    reason: str
    usd: float
    n_lots: int


def prior_session_day(d: date, day_set: set) -> Optional[date]:
    """Walk back to prior Mon–Fri session that exists in data (skip Sat/Sun)."""
    cur = d - timedelta(days=1)
    for _ in range(14):
        if cur in day_set and cur.weekday() < 5:
            return cur
        cur -= timedelta(days=1)
    return None


def _hourly_atr(hourly: pd.DataFrame, atr_len: int = 14) -> pd.Series:
    prev = hourly["close"].shift(1)
    tr = pd.concat(
        [
            hourly["high"] - hourly["low"],
            (hourly["high"] - prev).abs(),
            (hourly["low"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(atr_len).mean()


def _summarize(trades: Sequence[ClosedTrade], name: str, p: float) -> dict:
    if not trades:
        return {
            "strategy": name,
            "p": p,
            "campaigns": 0,
            "lots": 0.0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "closed_dd_usd": 0.0,
            "net_over_closed_dd": 0.0,
            "median_hold_h": 0.0,
            "n_stop": 0,
            "n_period_end": 0,
        }
    usd = np.array([t.usd for t in trades], dtype=float)
    eq = np.cumsum(usd)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    net = float(usd.sum())
    holds = [(t.exit_ts - t.entry_ts).total_seconds() / 3600 for t in trades]
    return {
        "strategy": name,
        "p": p,
        "campaigns": len(trades),
        "lots": float(sum(t.qty for t in trades)),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2),
        "closed_dd_usd": round(dd, 2),
        "net_over_closed_dd": round(net / abs(dd), 3) if dd else 0.0,
        "median_hold_h": round(float(np.median(holds)), 2),
        "n_stop": sum(1 for t in trades if t.reason == "stop"),
        "n_period_end": sum(1 for t in trades if t.reason == "period_end"),
    }


def run_variant(
    day_df: pd.DataFrame,
    by_day: Dict[date, pd.DataFrame],
    atr: pd.Series,
    day_ohlc: Dict[date, Tuple[float, float]],
    day_set: set,
    *,
    p: float,
    name: str,
) -> Tuple[List[ClosedTrade], dict]:
    trades: List[ClosedTrade] = []
    camp: Optional[Campaign] = None
    month_entry_count: Dict[str, int] = {}
    touch_days = 0

    dates = [d for d in day_df["date"].tolist()]
    # prev row for ST bias still uses calendar prior trading day in day_df
    prev_map = {day_df.iloc[i]["date"]: day_df.iloc[i - 1] for i in range(1, len(day_df))}

    def flatten(exit_ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal camp
        if camp is None or not camp.lots:
            camp = None
            return
        qty = sum(l.qty for l in camp.lots)
        entry_px = sum(l.entry * l.qty for l in camp.lots) / qty
        usd = sum(_pnl(camp.side, l.entry, exit_px, l.qty) for l in camp.lots)
        trades.append(
            ClosedTrade(
                name,
                camp.side,
                camp.lots[0].entry_ts,
                exit_ts,
                entry_px,
                exit_px,
                qty,
                reason,
                usd,
                len(camp.lots),
            )
        )
        camp = None

    for d in dates:
        prev = prev_map.get(d)
        if prev is None:
            continue
        bars = by_day.get(d)
        if bars is None or bars.empty:
            continue

        pkey = _week_key(d)
        if camp is not None and camp.period_key != pkey:
            px = float(bars.iloc[0]["open"])
            px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
            flatten(pd.Timestamp(bars.index[0]), px, "period_end")

        bias = bias_for_day(prev)
        # Session prev for extremes / entry geometry (Friday before Monday)
        sess = prior_session_day(d, day_set)
        if sess is None or sess not in day_ohlc:
            continue
        hi, lo = day_ohlc[sess]
        if hi <= lo:
            continue

        mkey = _month_key(d)
        month_used = month_entry_count.get(mkey, 0)
        idx = bars.index
        hi_a = bars["high"].to_numpy(dtype=float)
        lo_a = bars["low"].to_numpy(dtype=float)
        cl_a = bars["close"].to_numpy(dtype=float)
        n_bars = len(hi_a)
        is_fri = d.weekday() == 4

        can_enter = (
            bias is not None
            and month_used < MAX_ADDS
            and (
                camp is None
                or (d not in camp.entry_days and camp.side == bias and len(camp.lots) < MAX_ADDS)
            )
        )
        lvl = entry_level(bias, hi, lo, FRAC) if bias in {"long", "short"} else None

        for i in range(n_bars):
            hi_b, lo_b = hi_a[i], lo_a[i]
            ts = pd.Timestamp(idx[i])

            if camp is not None and camp.lots:
                stopped = False
                stop_px = None
                for lot in camp.lots:
                    if camp.side == "long" and lo_b <= lot.stop:
                        stopped = True
                        stop_px = lot.stop - HALF_SPREAD
                        break
                    if camp.side == "short" and hi_b >= lot.stop:
                        stopped = True
                        stop_px = lot.stop + HALF_SPREAD
                        break
                if stopped:
                    flatten(ts, float(stop_px), "stop")
                    can_enter = False
                    continue

            if camp is not None and is_fri and i == n_bars - 1:
                px = cl_a[i]
                px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
                flatten(ts, px, "period_end")
                continue

            if not can_enter or lvl is None or bias is None:
                continue
            touched = (bias == "long" and lo_b <= lvl) or (bias == "short" and hi_b >= lvl)
            if not touched:
                continue

            a = atr.asof(ts)
            if pd.isna(a) or float(a) <= 0:
                continue
            a = float(a)
            if bias == "long":
                stop_lvl = lo - p * a
                entry = lvl + HALF_SPREAD
                if entry <= stop_lvl or lo_b <= stop_lvl:
                    continue
            else:
                stop_lvl = hi + p * a
                entry = lvl - HALF_SPREAD
                if entry >= stop_lvl or hi_b >= stop_lvl:
                    continue

            if camp is None:
                camp = Campaign(side=bias, period_key=pkey)
            camp.lots.append(Lot(bias, ts, entry, stop_lvl, ADD_QTY))
            camp.entry_days.append(d)
            month_entry_count[mkey] = month_used + 1
            month_used += 1
            touch_days += 1
            can_enter = False
            continue

    if camp is not None and camp.lots:
        last_d = dates[-1]
        last_bars = by_day.get(last_d)
        if last_bars is not None and not last_bars.empty:
            px = float(last_bars.iloc[-1]["close"])
            px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
            flatten(pd.Timestamp(last_bars.index[-1]), px, "eod_mark")

    stats = _summarize(trades, name, p)
    stats["entry_days"] = touch_days
    return trades, stats


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument(
        "--ps",
        default="0,0.5,1,1.5,2,2.5,%.2f,3" % P_STAR,
        help="comma list of p multipliers",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    ps = [float(x) for x in args.ps.split(",") if x.strip()]

    print("Loading...", flush=True)
    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    one_m = concat_all_1m(load_fx_1m_by_ny_date(one_m_path, "EURUSD")).sort_index()
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    hourly = resample_hourly(one_m)
    atr = _hourly_atr(hourly)
    hourly_st = compute_supertrend_fast(hourly, atr_len=14, multiplier=3.0)
    day_df, by_day = build_day_tables(hourly_st, one_m)
    day_set = set(day_df["date"].tolist())
    day_ohlc = {
        row["date"]: (float(row["high"]), float(row["low"])) for _, row in day_df.iterrows()
    }
    print("  days=%d  p* (would-be clear)=%.2f" % (len(day_df), P_STAR), flush=True)

    # Note on chart prev
    mon = [d for d in day_df["date"].tolist() if d.weekday() == 0]
    sun_prev = 0
    for d in mon:
        # consecutive prior in day_df
        idx = day_df.index[day_df["date"] == d]
        if len(idx) == 0:
            continue
        i = int(idx[0])
        if i == 0:
            continue
        prev_d = day_df.iloc[i - 1]["date"]
        if prev_d.weekday() == 6:
            sun_prev += 1
    print("  Monday sessions with Sunday as consecutive prev: %d / %d" % (sun_prev, len(mon)), flush=True)

    rows = []
    for p in ps:
        name = "f30_week_sess_sl_p%.2fatr" % p
        print("Running", name, "...", flush=True)
        trades, stats = run_variant(
            day_df, by_day, atr, day_ohlc, day_set, p=p, name=name
        )
        rows.append(stats)
        print(
            "  net=$%s dd=$%s Net/DD=%.2f WR=%.1f%% hold=%.1fh stop/pe=%d/%d"
            % (
                f"{stats['net_usd']:,.0f}",
                f"{stats['closed_dd_usd']:,.0f}",
                stats["net_over_closed_dd"],
                stats["win_rate_pct"],
                stats["median_hold_h"],
                stats["n_stop"],
                stats["n_period_end"],
            ),
            flush=True,
        )

    summary = pd.DataFrame(rows).sort_values("net_usd", ascending=False)
    summary.to_csv(out / "leaderboard.csv", index=False)

    # copy requirements if present
    req = REPO / "live" / "state" / "eurusd_st_daybias_f30_close_sl" / "p_atr_wouldbe_requirements.csv"
    note_req = ""
    if req.exists():
        rdf = pd.read_csv(req)
        note_req = (
            "Would-be-winner set (n=%d): p_need median=%.2f, p95=%.2f, p_max=%.2f "
            "(session prev). p*=%.2f clears all.\n"
            % (
                len(rdf),
                float(rdf["p_need_sess_prev"].median()),
                float(rdf["p_need_sess_prev"].quantile(0.95)),
                float(rdf["p_need_sess_prev"].max()),
                P_STAR,
            )
        )

    lines = [
        "# f30 week — wider SL: session extreme ± p·ATR",
        "",
        "## What the charts used as “previous day extreme”",
        "",
        "Charts / original research used the **prior NY date that has bars** in the",
        "day table (consecutive groupby). For **Mondays that is often Sunday**",
        "(%d/%d Mondays in-sample) — a thin/partial session, not Friday’s full range."
        % (sun_prev, len(mon)),
        "",
        "**Fix here:** previous session = prior Mon–Fri day with bars (Sun/Sat skipped → Friday).",
        "",
        "## Stop definition",
        "",
        "```",
        "long  stop = prev_session_low  - p * hourly_ATR(14)",
        "short stop = prev_session_high + p * hourly_ATR(14)",
        "```",
        "",
        "Entry still at 30% pullback of that same session range. Bias still from",
        "prior calendar day’s ST fraction (unchanged).",
        "",
        note_req,
        "## Sweep (pandas, break-fixed, session prev)",
        "",
        "| Strategy | p | Net | Closed DD | Net/DD | WR | Med hold | Stops | Period |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            "| %s | %.2f | $%s | $%s | %.2f | %.1f%% | %.1f | %d | %d |"
            % (
                r["strategy"],
                r["p"],
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_closed_dd"],
                r["win_rate_pct"],
                r["median_hold_h"],
                r["n_stop"],
                r["n_period_end"],
            )
        )
    lines.extend(
        [
            "",
            f"p* = **{P_STAR}** is the smallest round value that keeps all 41 would-be-winner",
            "paths alive to Friday given session-prev extremes (from MAE/ATR analysis).",
            "",
            "CSV: `leaderboard.csv` · requirements: `../eurusd_st_daybias_f30_close_sl/p_atr_wouldbe_requirements.csv`",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
