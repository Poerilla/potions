"""EURUSD hourly SuperTrend day-bias DCA (prev-day mid pullback).

Bias (causal): for trading day D, look at completed hourly ST on day D−1.
If ≥70% of that day's hourly bars were bullish ST → bull day; if ≥70% bearish → bear.
Otherwise no new entries (open campaigns still only exit on SL / period end).

Entries (0.5 lot, max 5 per calendar month, never two on the same day):
  Bull: limit at prev-day low + f·(H−L); SL = prev-day low
  Bear: limit at prev-day high − f·(H−L); SL = prev-day high
  f ∈ {0.50, 0.40, 0.30}

Hold until unit SL or flatten at period end (week = Fri 16:00 NY; month = month-end).
Adds only on subsequent days while bias still matches campaign side.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .eurusd_intraday_ma_st_research import compute_supertrend_fast
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
OUT_DEFAULT = REPO / "live" / "state" / "eurusd_hourly_st_daybias_dca"

POINT_VALUE = 50_000.0  # one unit = 0.5 lot
FEE = 0.75
HALF_SPREAD = 0.5 * 1e-5 * 10
ADD_QTY = 1.0  # one half-lot unit
MAX_ADDS = 5
BIAS_THRESH = 0.70


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
    period_key: str


def _pnl(side: str, entry: float, exit_: float, qty: float) -> float:
    if side == "long":
        pts = (exit_ - entry) * qty
    else:
        pts = (entry - exit_) * qty
    return pts * POINT_VALUE - FEE * abs(qty)


def _summarize(trades: Sequence[ClosedTrade], name: str) -> dict:
    if not trades:
        return {
            "strategy": name,
            "campaigns": 0,
            "lots": 0.0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "closed_dd_usd": 0.0,
            "net_over_closed_dd": 0.0,
            "avg_usd": 0.0,
            "entry_days": 0,
        }
    usd = np.array([t.usd for t in trades], dtype=float)
    lots = np.array([t.qty for t in trades], dtype=float)
    eq = np.cumsum(usd)
    peak = np.maximum.accumulate(eq)
    closed_dd = float((eq - peak).min())
    net = float(usd.sum())
    return {
        "strategy": name,
        "campaigns": int(len(trades)),
        "lots": float(lots.sum()),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2),
        "closed_dd_usd": round(closed_dd, 2),
        "net_over_closed_dd": round(net / abs(closed_dd), 3) if closed_dd else 0.0,
        "avg_usd": round(net / len(trades), 2),
        "entry_days": int(sum(t.n_lots for t in trades)),
    }


def _ny_date(ts: pd.Timestamp) -> date:
    return ts.astimezone(NY_TZ).date()


def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return "%d-W%02d" % (iso[0], iso[1])


def _month_key(d: date) -> str:
    return "%d-%02d" % (d.year, d.month)


def _period_end_day(d: date, period: str) -> date:
    if period == "week":
        # Friday of that ISO week (or earlier if Friday missing — handled at flatten time)
        return d + timedelta(days=(4 - d.weekday()) % 7)
    # month: last calendar day of month
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def build_day_tables(hourly: pd.DataFrame, one_m: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[date, pd.DataFrame]]:
    """Per-NY-day: OHLC, ST bull fraction; plus 1m bars by day."""
    h = hourly.copy()
    h["ny_date"] = h.index.map(_ny_date)
    rows = []
    for d, g in h.groupby("ny_date", sort=True):
        trend = g["supertrend_trend"].to_numpy(dtype=float)
        valid = ~np.isnan(trend)
        n = int(valid.sum())
        if n == 0:
            bull_frac = np.nan
            bear_frac = np.nan
        else:
            bull_frac = float((trend[valid] == 1).sum()) / n
            bear_frac = float((trend[valid] == -1).sum()) / n
        rows.append(
            {
                "date": d,
                "open": float(g["open"].iloc[0]),
                "high": float(g["high"].max()),
                "low": float(g["low"].min()),
                "close": float(g["close"].iloc[-1]),
                "bull_frac": bull_frac,
                "bear_frac": bear_frac,
                "n_hourly": n,
            }
        )
    day_df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    by_day: Dict[date, pd.DataFrame] = {}
    one_m = one_m.copy()
    one_m["ny_date"] = one_m.index.map(_ny_date)
    for d, g in one_m.groupby("ny_date", sort=True):
        by_day[d] = g[["open", "high", "low", "close"]].sort_index()
    return day_df, by_day


def bias_for_day(prev_row: pd.Series) -> Optional[str]:
    bf, br = prev_row["bull_frac"], prev_row["bear_frac"]
    if pd.isna(bf) or pd.isna(br):
        return None
    if bf >= BIAS_THRESH:
        return "long"
    if br >= BIAS_THRESH:
        return "short"
    return None


def entry_level(side: str, high: float, low: float, frac: float) -> float:
    """frac=0.5 mid; smaller frac = deeper pullback toward supportive extreme."""
    span = high - low
    if side == "long":
        return low + frac * span
    return high - frac * span


def run_variant(
    day_df: pd.DataFrame,
    by_day: Dict[date, pd.DataFrame],
    *,
    frac: float,
    period: str,
    name: str,
) -> Tuple[List[ClosedTrade], dict]:
    trades: List[ClosedTrade] = []
    camp: Optional[Campaign] = None
    month_entry_count: Dict[str, int] = {}
    touch_days = 0
    entry_opportunities = 0

    dates = [d for d in day_df["date"].tolist()]
    prev_map = {day_df.iloc[i]["date"]: day_df.iloc[i - 1] for i in range(1, len(day_df))}

    def flatten(exit_ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal camp
        if camp is None or not camp.lots:
            camp = None
            return
        qty = sum(l.qty for l in camp.lots)
        entry_px = sum(l.entry * l.qty for l in camp.lots) / qty
        # fee charged per lot on close
        usd = 0.0
        for lot in camp.lots:
            usd += _pnl(camp.side, lot.entry, exit_px, lot.qty)
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
                camp.period_key,
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

        # Period-end flatten at first bar of a new period if campaign from prior period
        pkey = _week_key(d) if period == "week" else _month_key(d)
        if camp is not None and camp.period_key != pkey:
            # flatten at open of new period
            px = float(bars.iloc[0]["open"])
            if camp.side == "long":
                px -= HALF_SPREAD
            else:
                px += HALF_SPREAD
            flatten(pd.Timestamp(bars.index[0]), px, "period_end")

        bias = bias_for_day(prev)
        hi, lo = float(prev["high"]), float(prev["low"])
        if hi <= lo:
            continue
        if bias in {"long", "short"}:
            entry_opportunities += 1

        mkey = _month_key(d)
        month_used = month_entry_count.get(mkey, 0)

        idx = bars.index
        hi_a = bars["high"].to_numpy(dtype=float)
        lo_a = bars["low"].to_numpy(dtype=float)
        cl_a = bars["close"].to_numpy(dtype=float)
        n_bars = len(hi_a)
        is_period_end_day = (period == "week" and d.weekday() == 4) or (
            period == "month" and d == _period_end_day(d, "month")
        )
        can_enter = (
            bias is not None
            and month_used < MAX_ADDS
            and (camp is None or (d not in camp.entry_days and camp.side == bias and len(camp.lots) < MAX_ADDS))
        )
        lvl = entry_level(bias, hi, lo, frac) if bias in {"long", "short"} else None
        stop_lvl = lo if bias == "long" else hi if bias == "short" else None

        for i in range(n_bars):
            hi_b, lo_b = hi_a[i], lo_a[i]
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
                    flatten(pd.Timestamp(idx[i]), float(stop_px), "stop")
                    can_enter = False  # no same-bar / same-day re-entry after stop
                    continue

            if camp is not None and is_period_end_day and i == n_bars - 1:
                px = cl_a[i]
                px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
                flatten(pd.Timestamp(idx[i]), px, "period_end")
                continue

            if not can_enter or lvl is None or stop_lvl is None:
                continue
            touched = (bias == "long" and lo_b <= lvl) or (bias == "short" and hi_b >= lvl)
            if not touched:
                continue
            entry = lvl + HALF_SPREAD if bias == "long" else lvl - HALF_SPREAD
            if bias == "long" and (entry <= stop_lvl or lo_b <= stop_lvl):
                continue
            if bias == "short" and (entry >= stop_lvl or hi_b >= stop_lvl):
                continue

            if camp is None:
                camp = Campaign(side=bias, period_key=pkey)
            camp.lots.append(Lot(bias, pd.Timestamp(idx[i]), entry, stop_lvl, ADD_QTY))
            camp.entry_days.append(d)
            month_entry_count[mkey] = month_used + 1
            month_used += 1
            touch_days += 1
            can_enter = False
            # Do NOT break — keep walking the day's bars so same-day stop/TP can fire.
            continue

    # open mark at end
    if camp is not None and camp.lots:
        last_d = dates[-1]
        last_bars = by_day.get(last_d)
        if last_bars is not None and not last_bars.empty:
            px = float(last_bars.iloc[-1]["close"])
            px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
            flatten(pd.Timestamp(last_bars.index[-1]), px, "eod_mark")

    stats = {
        "bias_opportunity_days": entry_opportunities,
        "touch_and_enter_days": touch_days,
        "months_with_entries": sum(1 for v in month_entry_count.values() if v > 0),
    }
    return trades, stats


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD hourly ST day-bias DCA")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--fracs", default="0.50,0.40,0.30")
    args = parser.parse_args(list(argv) if argv is not None else None)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    fracs = [float(x.strip()) for x in args.fracs.split(",") if x.strip()]

    print("Loading EURUSD 1m → hourly ST...", flush=True)
    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    gby = load_fx_1m_by_ny_date(one_m_path, "EURUSD")
    one_m = concat_all_1m(gby).sort_index()
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    hourly = resample_hourly(one_m)
    print("  hourly bars:", f"{len(hourly):,}", flush=True)
    hourly = compute_supertrend_fast(hourly, atr_len=14, multiplier=3.0)
    day_df, by_day = build_day_tables(hourly, one_m)
    print("  NY days:", len(day_df), flush=True)

    # Bias day counts
    biases = []
    for i in range(1, len(day_df)):
        b = bias_for_day(day_df.iloc[i - 1])
        biases.append(b)
    n_bull = sum(1 for b in biases if b == "long")
    n_bear = sum(1 for b in biases if b == "short")
    n_flat = sum(1 for b in biases if b is None)
    print("  bias days bull/bear/flat:", n_bull, n_bear, n_flat, flush=True)

    rows = []
    all_trades = {}
    for frac in fracs:
        for period in ("week", "month"):
            name = "st_daybias_dca_f%.0f_%s" % (frac * 100, period)
            print("Running", name, "...", flush=True)
            trades, stats = run_variant(day_df, by_day, frac=frac, period=period, name=name)
            s = _summarize(trades, name)
            s.update(stats)
            s["frac"] = frac
            s["period"] = period
            rows.append(s)
            all_trades[name] = trades
            print(
                "  net=$%s dd=$%s camps=%d lots=%.1f WR=%.1f touches=%d opp_days=%d"
                % (
                    f"{s['net_usd']:,.0f}",
                    f"{s['closed_dd_usd']:,.0f}",
                    s["campaigns"],
                    s["lots"],
                    s["win_rate_pct"],
                    s["touch_and_enter_days"],
                    s["bias_opportunity_days"],
                ),
                flush=True,
            )

    summary = pd.DataFrame(rows).sort_values("net_usd", ascending=False)
    summary.to_csv(out / "leaderboard.csv", index=False)
    (out / "summary.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")

    # Sample trade dump for best
    if rows:
        best = summary.iloc[0]["strategy"]
        tdf = pd.DataFrame([t.__dict__ for t in all_trades[best]])
        if not tdf.empty:
            tdf.to_csv(out / ("trades_%s.csv" % best), index=False)

    lines = [
        "# EURUSD hourly ST day-bias DCA",
        "",
        "Prev-day hourly ST ≥70% bull/bear sets next-day bias. Enter 0.5 lot at prev-day",
        "pullback fraction f (50/40/30%), SL at prev-day extreme. DCA up to 5×/month,",
        "one entry per day. Exit on lot SL or period end (week=Fri close / month=month-end).",
        "",
        "Unit = 0.5 lot (PV $50k), fee $0.75/half-lot. Window %s → %s." % (args.start, args.end),
        "",
        "Bias day counts: bull **%d** / bear **%d** / flat **%d**." % (n_bull, n_bear, n_flat),
        "",
        "| Strategy | f | Period | Net | Closed DD | Net/DD | Camps | Lots | WR | Entry days | Opp days |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            "| %s | %.0f%% | %s | $%s | $%s | %.2f | %d | %.1f | %.1f%% | %d | %d |"
            % (
                r["strategy"],
                100 * r["frac"],
                r["period"],
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_closed_dd"],
                r["campaigns"],
                r["lots"],
                r["win_rate_pct"],
                r["touch_and_enter_days"],
                r["bias_opportunity_days"],
            )
        )
    lines.extend(
        [
            "",
            "Opp days = sessions with a clear 70% ST bias from the prior day.",
            "Entry days = days that actually filled an add (touch of f-level).",
            "",
            "CSV: `leaderboard.csv`",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
