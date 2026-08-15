"""OR + HTF turtle-soup on FX/CFD markets (Plan C companion).

For each configured FX market clock:
  A. OR turtle soup — close5 OUT→IN of that clock's OR, soup the swing,
     stop = R/5, 5ct, scale 4 @ opposite OR, runner opp 1R + BE
  B. HTF turtle soup — same geometry on failed breaks of prior 3d / 4w / 2m
     high-low (full-day extremes), risk still from that session's OR

Markets: US30/NAS100 (NY RTH), EURUSD & USDJPY (London + NY opens), XAU (NY open).

Usage:
  python -m live.fx_turtle_soup_study --markets us30 nas100
  python -m live.fx_turtle_soup_study --markets us30 nas100 eurusd_london eurusd_ny usdjpy_ny xauusd_ny
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .fx_or_markets import FX_MARKETS, FxMarket, load_market_gby, session_bars
from .q1_fakeout_loss_autopsy import Trade

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "fx_turtle_soup"
BREAK_CUTOFF_OFFSET_MIN = 45  # minutes after OR end for morning break cutoff
FAIL_CANDLES5 = 2
STOP_R_FRAC = 0.2
ENTRY_QTY = 5
SCALE_QTY = 4
FEE = 0.0  # mid-tape analytic; fees left at 0 for cross-market compare


@dataclass
class Book:
    name: str
    sessions: int = 0
    fills: int = 0
    full_stop: int = 0
    scaled: int = 0
    runner_tp: int = 0
    pnl: float = 0.0
    wins: float = 0.0
    losses: float = 0.0
    filled_qty: List[int] = field(default_factory=list)

    def row(self) -> Dict[str, object]:
        pf = self.wins / abs(self.losses) if self.losses else float("inf")
        return {
            "variant": self.name,
            "sessions": self.sessions,
            "fills": self.fills,
            "fill_rate_pct": round(100.0 * self.fills / self.sessions, 1) if self.sessions else 0,
            "full_stop": self.full_stop,
            "scaled_4": self.scaled,
            "scale_rate_pct": round(100.0 * self.scaled / self.fills, 1) if self.fills else 0,
            "runner_tp": self.runner_tp,
            "win_pct": "",
            "net_usd": round(self.pnl, 2),
            "usd_per_fill": round(self.pnl / self.fills, 2) if self.fills else 0,
            "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
            "avg_filled_qty": round(sum(self.filled_qty) / len(self.filled_qty), 2) if self.filled_qty else "",
        }


def _cutoff(clock_or_end: time) -> time:
    base = datetime_combine_minutes(clock_or_end, BREAK_CUTOFF_OFFSET_MIN)
    return base


def datetime_combine_minutes(t: time, add_min: int) -> time:
    total = t.hour * 60 + t.minute + add_min
    return time((total // 60) % 24, total % 60)


def build_day_ohlc(gby: Dict[date, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for day in sorted(gby):
        df = gby[day]
        if df is None or df.empty:
            continue
        rows.append(
            {
                "session": day,
                "high": float(df["high"].max()),
                "low": float(df["low"].min()),
                "iso_year": day.isocalendar()[0],
                "iso_week": day.isocalendar()[1],
                "year": day.year,
                "month": day.month,
            }
        )
    return pd.DataFrame(rows)


def htf_levels(sess: pd.DataFrame, day: date) -> List[Tuple[str, str, str, float]]:
    """Return (name, family, side, price) causal HTF levels."""
    prior = sess[sess["session"] < day]
    out: List[Tuple[str, str, str, float]] = []
    if len(prior) >= 3:
        w = prior.tail(3)
        out.append(("daily_3_high", "daily_3", "high", float(w["high"].max())))
        out.append(("daily_3_low", "daily_3", "low", float(w["low"].min())))
    weeks = prior.groupby(["iso_year", "iso_week"]).agg(high=("high", "max"), low=("low", "min")).reset_index()
    cur = day.isocalendar()
    weeks = weeks[~((weeks.iso_year == cur[0]) & (weeks.iso_week == cur[1]))]
    if len(weeks) >= 4:
        w = weeks.tail(4)
        out.append(("weekly_4_high", "weekly_4", "high", float(w["high"].max())))
        out.append(("weekly_4_low", "weekly_4", "low", float(w["low"].min())))
    months = prior.groupby(["year", "month"]).agg(high=("high", "max"), low=("low", "min")).reset_index()
    months = months[~((months.year == day.year) & (months.month == day.month))]
    if len(months) >= 2:
        w = months.tail(2)
        out.append(("monthly_2_high", "monthly_2", "high", float(w["high"].max())))
        out.append(("monthly_2_low", "monthly_2", "low", float(w["low"].min())))
    return out


def scan_fail(
    day: date,
    dense: pd.DataFrame,
    level: float,
    side: str,
    or_high: float,
    or_low: float,
    or_end: time,
    cutoff: time,
    eod: time,
    trade_id: str,
) -> Optional[Trade]:
    r = or_high - or_low
    if r <= 0:
        return None
    post = dense[dense.index.map(lambda ts: ts.time() >= or_end)]
    break_side = "up" if side == "high" else "down"
    break_ts = extreme = close_out_ts = confirm_ts = None
    for ts, row in post.iterrows():
        if ts.time() >= eod:
            break
        if break_ts is None:
            if ts.time() >= cutoff:
                return None
            pierced = row["high"] > level if break_side == "up" else row["low"] < level
            if not pierced:
                continue
            break_ts = ts
            extreme = row["high"] if break_side == "up" else row["low"]
            continue
        extreme = max(extreme, row["high"]) if break_side == "up" else min(extreme, row["low"])
        if ts.minute % 5 != 4:
            continue
        close = float(row["close"])
        outside = close > level if break_side == "up" else close < level
        inside = close <= level if break_side == "up" else close >= level
        if close_out_ts is None:
            if outside:
                if ts.time() >= cutoff:
                    return None
                close_out_ts = ts
            continue
        n5 = int((ts - close_out_ts).total_seconds() // 300)
        if inside and n5 <= FAIL_CANDLES5:
            confirm_ts = ts
            break
        if n5 > FAIL_CANDLES5:
            return None
    if confirm_ts is None or extreme is None:
        return None
    t = Trade(
        trade_id=trade_id,
        session=day,
        direction="Short" if break_side == "up" else "Long",
        entry_ts=confirm_ts,
        entry_price=0.0,
        exit_reasons=[],
        pnl_usd=0.0,
    )
    t.or_high, t.or_low, t.r = or_high, or_low, r
    t.break_side, t.break_ts, t.failed_extreme = break_side, break_ts, float(extreme)
    t.confirm_ts = confirm_ts
    t.close_out_ts = close_out_ts
    t.htf_level = level
    t.eod = eod
    t.tick = None  # set by caller
    return t


def simulate(book: Book, t: Trade, day_df: pd.DataFrame, point_value: float, tick: float) -> Optional[Dict]:
    book.sessions += 1
    short = t.direction == "Short"
    entry = float(t.failed_extreme)
    stop_dist = max(STOP_R_FRAC * t.r, tick)
    stop0 = entry + stop_dist if short else entry - stop_dist
    scale_tp = t.or_low if short else t.or_high
    runner_tp = (t.or_low - t.r) if short else (t.or_high + t.r)
    eod = getattr(t, "eod", time(15, 59))
    after = day_df[day_df.index > t.confirm_ts]
    if after.empty:
        return None

    filled = False
    entry_px = entry_ts = None
    stop = stop0
    remaining = ENTRY_QTY
    scaled = False
    pnl = 0.0
    runner_outcome = ""
    last_exit_ts = None

    for ts, row in after.iterrows():
        if ts.time() >= eod:
            if filled and remaining > 0:
                sign = -1.0 if short else 1.0
                pnl += (float(row["close"]) - entry_px) * sign * remaining * point_value
                runner_outcome = "eod"
                remaining = 0
            break
        if not filled:
            touched = row["high"] >= entry if short else row["low"] <= entry
            if not touched:
                continue
            filled, entry_px, entry_ts = True, float(entry), ts
            if (row["high"] >= stop) if short else (row["low"] <= stop):
                sign = -1.0 if short else 1.0
                pnl += (float(stop) - entry_px) * sign * remaining * point_value
                runner_outcome = "full_stop"
                remaining = 0
                last_exit_ts = ts
                break
            continue
        stopped = row["high"] >= stop if short else row["low"] <= stop
        if stopped:
            sign = -1.0 if short else 1.0
            pnl += (float(stop) - entry_px) * sign * remaining * point_value
            runner_outcome = "full_stop" if not scaled else "runner_sl"
            remaining = 0
            last_exit_ts = ts
            break
        if not scaled:
            hit = row["low"] <= scale_tp if short else row["high"] >= scale_tp
            if hit:
                sign = -1.0 if short else 1.0
                pnl += (float(scale_tp) - entry_px) * sign * SCALE_QTY * point_value
                remaining -= SCALE_QTY
                scaled = True
                stop = entry_px
                if remaining > 0:
                    hit_r = row["low"] <= runner_tp if short else row["high"] >= runner_tp
                    if hit_r:
                        pnl += (float(runner_tp) - entry_px) * sign * remaining * point_value
                        runner_outcome = "runner_tp"
                        remaining = 0
                        last_exit_ts = ts
                        break
                continue
        if scaled and remaining > 0:
            hit_r = row["low"] <= runner_tp if short else row["high"] >= runner_tp
            if hit_r:
                sign = -1.0 if short else 1.0
                pnl += (float(runner_tp) - entry_px) * sign * remaining * point_value
                runner_outcome = "runner_tp"
                remaining = 0
                last_exit_ts = ts
                break
    if not filled:
        return None
    if remaining > 0:
        sign = -1.0 if short else 1.0
        pnl += (float(after.iloc[-1]["close"]) - entry_px) * sign * remaining * point_value
        runner_outcome = "eod"
    pnl -= FEE * ENTRY_QTY
    book.fills += 1
    book.pnl += pnl
    book.filled_qty.append(ENTRY_QTY)
    if pnl >= 0:
        book.wins += pnl
    else:
        book.losses += pnl
    if runner_outcome == "full_stop":
        book.full_stop += 1
    elif scaled:
        book.scaled += 1
        if runner_outcome == "runner_tp":
            book.runner_tp += 1
    return {
        "trade_id": t.trade_id,
        "variant": book.name,
        "session": t.session.isoformat(),
        "direction": t.direction,
        "pnl_usd": round(pnl, 2),
        "runner_outcome": runner_outcome,
        "entry_ts": entry_ts,
        "r": t.r,
    }


def wick_ok(t: Trade, level: float, frac: float = 0.25) -> bool:
    return abs(t.failed_extreme - level) >= frac * t.r


def run_market(key: str) -> pd.DataFrame:
    mkt = FX_MARKETS[key]
    clock = mkt.clock
    cutoff = _cutoff(clock.or_end)
    print("=== %s (%s clock %s–%s) ===" % (key, clock.name, clock.or_start, clock.or_end), flush=True)
    gby = load_market_gby(mkt)
    day_ohlc = build_day_ohlc(gby)
    books: Dict[str, Book] = {}
    recs: List[Dict] = []

    def run(name: str, trades: Sequence[Trade]):
        b = books.setdefault(name, Book(name))
        for t in trades:
            dense = session_bars(gby[t.session], t.session, clock, dense=True)
            rec = simulate(b, t, dense, mkt.point_value, mkt.tick)
            if rec:
                recs.append(rec)

    or_signals: List[Trade] = []
    htf_by_fam: Dict[str, List[Trade]] = {"daily_3": [], "weekly_4": [], "monthly_2": []}

    for day in sorted(gby):
        raw = session_bars(gby[day], day, clock, dense=False)
        if raw.empty or len(raw) < clock.min_session_bars // 3:  # sparse ok threshold looser
            continue
        dense = session_bars(gby[day], day, clock, dense=True)
        orb = dense[dense.index.map(lambda ts: ts.time() < clock.or_end)]
        if len(orb) < clock.min_or_bars:
            continue
        or_high, or_low = float(orb["high"].max()), float(orb["low"].min())
        if or_high <= or_low:
            continue

        # A. OR fail
        t_or = scan_fail(
            day, dense, or_high, "high", or_high, or_low, clock.or_end, cutoff, clock.eod, "or_high_%s" % day
        )
        # try both sides — first confirm wins; prefer the side that confirms first
        t_or_lo = scan_fail(
            day, dense, or_low, "low", or_high, or_low, clock.or_end, cutoff, clock.eod, "or_low_%s" % day
        )
        pick = None
        for cand in (t_or, t_or_lo):
            if cand is None:
                continue
            if pick is None or cand.confirm_ts < pick.confirm_ts:
                pick = cand
        if pick is not None:
            or_signals.append(pick)

        # B. HTF
        mid = 0.5 * (or_high + or_low)
        levels = htf_levels(day_ohlc, day)
        for fam in htf_by_fam:
            cands = [lv for lv in levels if lv[1] == fam]
            cands.sort(key=lambda lv: abs(lv[3] - mid))
            for name, family, side, price in cands:
                t = scan_fail(
                    day, dense, price, side, or_high, or_low, clock.or_end, cutoff, clock.eod, "%s_%s" % (name, day)
                )
                if t is not None:
                    t.htf_level = price
                    htf_by_fam[fam].append(t)
                    break

    run("%s_or" % key, or_signals)
    run("%s_or_wick25" % key, [t for t in or_signals if wick_ok(t, t.or_high if t.break_side == "up" else t.or_low)])
    for fam, trades in htf_by_fam.items():
        run("%s_%s" % (key, fam), trades)
        run(
            "%s_%s_wick25" % (key, fam),
            [t for t in trades if wick_ok(t, float(getattr(t, "htf_level", t.failed_extreme)))],
        )

    vdf = pd.DataFrame([b.row() for b in books.values()])
    tdf = pd.DataFrame(recs)
    if not tdf.empty:
        wp = tdf.groupby("variant").apply(lambda s: round(100.0 * (s.pnl_usd >= 0).mean(), 1))
        vdf["win_pct"] = vdf["variant"].map(wp)
        tdf["year"] = pd.to_datetime(tdf["entry_ts"], utc=True).dt.year
        neg = {}
        for v in vdf["variant"]:
            y = tdf[tdf.variant == v].groupby("year").pnl_usd.sum()
            neg[v] = int((y < 0).sum()) if len(y) else ""
        vdf["neg_years"] = vdf["variant"].map(neg)
        vdf["n_years"] = vdf["variant"].map(
            lambda v: tdf[tdf.variant == v]["year"].nunique() if not tdf.empty else 0
        )

    OUT.mkdir(parents=True, exist_ok=True)
    vdf.to_csv(OUT / ("%s_stats.csv" % key), index=False)
    tdf.to_csv(OUT / ("%s_trades.csv" % key), index=False)
    print(vdf.sort_values("net_usd", ascending=False).to_string(index=False), flush=True)
    return vdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--markets",
        nargs="+",
        default=["us30", "nas100", "eurusd_london", "eurusd_ny", "usdjpy_ny", "xauusd_ny"],
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for key in args.markets:
        if key not in FX_MARKETS:
            print("unknown market %s; known: %s" % (key, sorted(FX_MARKETS)), flush=True)
            continue
        vdf = run_market(key)
        all_rows.append(vdf)
    if all_rows:
        big = pd.concat(all_rows, ignore_index=True)
        big.to_csv(OUT / "summary.csv", index=False)
        lines = [
            "# FX / CFD turtle soup (OR + HTF)",
            "",
            "Geometry: close5 OUT→IN → limit at failed extreme, stop = session-OR R/5,",
            "5 contracts, scale 4 at opposite OR boundary, 1 runner to opp 1R (BE after scale).",
            "Clocks: US30/NAS100 = NY RTH; EURUSD/USDJPY = London 03:00 OR and/or NY 08:00 OR; XAU = NY 08:00 OR.",
            "",
            "## Books",
            "",
        ]
        cols = list(big.columns)
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for _, r in big.sort_values("net_usd", ascending=False).iterrows():
            lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
        (OUT / "SUMMARY.md").write_text("\n".join(lines))
        print("-> %s" % (OUT / "SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
