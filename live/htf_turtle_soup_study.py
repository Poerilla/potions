"""Turtle-soup failed breaks of HTF highs/lows (not the OR).

Same execution geometry as the OR turtle-soup book, but the *level* that
fails is a prior HTF extreme:

  - daily_3  : high/low of the prior 3 complete RTH sessions
  - weekly_4 : high/low of the prior 4 complete ISO weeks
  - monthly_2: high/low of the prior 2 complete calendar months

Per session (regime-gated, MA50>MA150):
  1. Build today's OR (09:30-09:45) — used only for risk / scale targets
  2. For each HTF level, watch a morning touch break (before 10:30)
  3. 5m close OUT beyond the level → 5m close back IN within 2 candles
  4. Limit turtle-soup at the failed-extreme swing
  5. Stop = swing ± (today's OR width)/5; size 5; scale 4 at opposite OR
     boundary; 1 runner to opp 1R with stop→BE after scale

Also reports the wick≥0.25R quality filter that helped on the OR soup.

Usage: python -m live.htf_turtle_soup_study [--markets nq]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .q1_fakeout_loss_autopsy import OUT as OR_OUT
from .q1_fakeout_loss_autopsy import POINT_VALUE, TICK, Trade, rth
from .q1_fakeout_structure_followup import load_gby
from .q1_fakeout_turtle_soup_levers import Book, simulate, yearly_summary
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "htf_turtle_soup"
BREAK_CUTOFF = time(10, 30)
FAIL_CANDLES5 = 2
LEVEL_SPECS = {
    "daily_3": "prior 3 RTH sessions high/low",
    "weekly_4": "prior 4 complete ISO weeks high/low",
    "monthly_2": "prior 2 complete calendar months high/low",
}


@dataclass
class HtfLevel:
    name: str  # e.g. daily_3_high
    family: str  # daily_3
    side: str  # high | low
    price: float


def build_session_table(gby: Dict[date, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for day in sorted(gby):
        bars = rth(gby[day])
        if bars.empty:
            continue
        rows.append(
            {
                "session": day,
                "high": float(bars["high"].max()),
                "low": float(bars["low"].min()),
                "open": float(bars.iloc[0]["open"]),
                "close": float(bars.iloc[-1]["close"]),
            }
        )
    df = pd.DataFrame(rows).sort_values("session").reset_index(drop=True)
    df["session"] = pd.to_datetime(df["session"]).dt.date
    df["iso_year"] = pd.to_datetime(df["session"]).dt.isocalendar().year.astype(int)
    df["iso_week"] = pd.to_datetime(df["session"]).dt.isocalendar().week.astype(int)
    df["year"] = pd.to_datetime(df["session"]).dt.year
    df["month"] = pd.to_datetime(df["session"]).dt.month
    return df


def levels_for_session(sess: pd.DataFrame, day: date) -> List[HtfLevel]:
    """Causal HTF levels knowable before today's open (prior completed periods)."""
    prior = sess[sess["session"] < day]
    out: List[HtfLevel] = []
    if len(prior) >= 3:
        win = prior.tail(3)
        out.append(HtfLevel("daily_3_high", "daily_3", "high", float(win["high"].max())))
        out.append(HtfLevel("daily_3_low", "daily_3", "low", float(win["low"].min())))

    # prior 4 complete ISO weeks (exclude current week)
    cur_y = day.isocalendar()[0]
    cur_w = day.isocalendar()[1]
    weeks = (
        prior.groupby(["iso_year", "iso_week"], sort=True)
        .agg(high=("high", "max"), low=("low", "min"))
        .reset_index()
    )
    weeks = weeks[~((weeks.iso_year == cur_y) & (weeks.iso_week == cur_w))]
    if len(weeks) >= 4:
        win = weeks.tail(4)
        out.append(HtfLevel("weekly_4_high", "weekly_4", "high", float(win["high"].max())))
        out.append(HtfLevel("weekly_4_low", "weekly_4", "low", float(win["low"].min())))

    months = (
        prior.groupby(["year", "month"], sort=True)
        .agg(high=("high", "max"), low=("low", "min"))
        .reset_index()
    )
    months = months[~((months.year == day.year) & (months.month == day.month))]
    if len(months) >= 2:
        win = months.tail(2)
        out.append(HtfLevel("monthly_2_high", "monthly_2", "high", float(win["high"].max())))
        out.append(HtfLevel("monthly_2_low", "monthly_2", "low", float(win["low"].min())))
    return out


def scan_htf_fail(
    day: date,
    day_df: pd.DataFrame,
    level: HtfLevel,
    or_high: float,
    or_low: float,
) -> Optional[Trade]:
    """close5 OUT beyond HTF level → close5 IN; return Trade ready for soup sim."""
    r = or_high - or_low
    if r <= 0:
        return None
    bars = rth(day_df)
    post = bars[bars.index.time >= time(9, 45)]
    break_side = "up" if level.side == "high" else "down"
    lvl = level.price
    break_ts = extreme = close_out_ts = confirm_ts = None

    for ts, row in post.iterrows():
        if break_ts is None:
            if ts.time() >= BREAK_CUTOFF:
                return None
            pierced = row["high"] > lvl if break_side == "up" else row["low"] < lvl
            if not pierced:
                continue
            break_ts = ts
            extreme = row["high"] if break_side == "up" else row["low"]
            continue
        extreme = max(extreme, row["high"]) if break_side == "up" else min(extreme, row["low"])
        if ts.minute % 5 != 4:
            continue
        close = float(row["close"])
        outside = close > lvl if break_side == "up" else close < lvl
        inside = close <= lvl if break_side == "up" else close >= lvl
        if close_out_ts is None:
            if outside:
                if ts.time() >= BREAK_CUTOFF:
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
        trade_id="%s_%s" % (level.name, day.isoformat()),
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
    t.htf_level = lvl
    t.htf_name = level.name
    t.htf_family = level.family
    if break_side == "up":
        t.stop = t.failed_extreme + TICK
        t.tp_bound, t.tp_1r = or_low, or_low - r
        t.invalidation = or_high + r
    else:
        t.stop = t.failed_extreme - TICK
        t.tp_bound, t.tp_1r = or_high, or_high + r
        t.invalidation = or_low - r
    return t


def wick_ok(t: Trade, min_frac: float = 0.25) -> bool:
    lvl = float(getattr(t, "htf_level", 0.0))
    wick = abs(t.failed_extreme - lvl)
    return wick >= min_frac * t.r


def run_market(market: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if market == "nq":
        gby = load_gby()
    else:
        from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

        cfg = MARKETS[market]
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)

    cfg = MARKETS[market]
    regime = set(_regime_dates(cfg, gby))
    sess = build_session_table(gby)
    print("%s: %d sessions, %d regime" % (market, len(sess), len(regime)), flush=True)

    # collect signals per family
    by_family: Dict[str, List[Trade]] = {k: [] for k in LEVEL_SPECS}
    any_signals: List[Trade] = []
    # dedupe: one trade per session per family (first level that confirms; prefer closer to price)
    for day in sorted(gby):
        if day not in regime:
            continue
        bars = rth(gby[day])
        orb = bars.between_time("09:30", "09:44")
        if len(orb) < 15:
            continue
        or_high, or_low = float(orb["high"].max()), float(orb["low"].min())
        if or_high <= or_low:
            continue
        levels = levels_for_session(sess, day)
        # mid of OR as proximity anchor
        mid = 0.5 * (or_high + or_low)
        for family in LEVEL_SPECS:
            cands = [lv for lv in levels if lv.family == family]
            # nearest level to OR mid first
            cands.sort(key=lambda lv: abs(lv.price - mid))
            picked = None
            for lv in cands:
                t = scan_htf_fail(day, gby[day], lv, or_high, or_low)
                if t is not None:
                    picked = t
                    break
            if picked is not None:
                by_family[family].append(picked)
                any_signals.append(picked)

    print("signals:", {k: len(v) for k, v in by_family.items()}, "any", len(any_signals), flush=True)

    books: Dict[str, Book] = {}
    all_recs: List[Dict] = []
    signal_rows: List[Dict] = []

    def run(name: str, trades: List[Trade], wick_filter: bool = False):
        b = books.setdefault(name, Book(name))
        for t in trades:
            if wick_filter and not wick_ok(t):
                b.sessions += 1  # still count as eligible session attempt? skip without counting session
                # don't inflate sessions — only simulate filter-passers; count filter universe as sessions
                continue
            rec = simulate(b, t, gby[t.session], frac=0.2, floor_ticks=1)
            if rec:
                rec["htf_name"] = getattr(t, "htf_name", "")
                rec["htf_family"] = getattr(t, "htf_family", "")
                rec["htf_level"] = getattr(t, "htf_level", "")
                rec["wick_pts"] = abs(t.failed_extreme - float(getattr(t, "htf_level", t.failed_extreme)))
                all_recs.append(rec)

    # fix wick-filter session counting: prefilter universe
    def run_filtered(name: str, trades: List[Trade], wick_filter: bool = False):
        uni = [t for t in trades if (not wick_filter or wick_ok(t))]
        b = books.setdefault(name, Book(name))
        for t in uni:
            rec = simulate(b, t, gby[t.session], frac=0.2, floor_ticks=1)
            if rec:
                rec["htf_name"] = getattr(t, "htf_name", "")
                rec["htf_family"] = getattr(t, "htf_family", "")
                rec["htf_level"] = getattr(t, "htf_level", "")
                rec["wick_pts"] = abs(t.failed_extreme - float(getattr(t, "htf_level", t.failed_extreme)))
                all_recs.append(rec)

    for family, trades in by_family.items():
        for t in trades:
            signal_rows.append(
                {
                    "session": t.session.isoformat(),
                    "family": family,
                    "htf_name": t.htf_name,
                    "htf_level": t.htf_level,
                    "direction": t.direction,
                    "r": t.r,
                    "failed_extreme": t.failed_extreme,
                    "wick_pts": abs(t.failed_extreme - t.htf_level),
                    "wick_ok_0_25R": wick_ok(t),
                }
            )
        run_filtered("%s_%s" % (market, family), trades, wick_filter=False)
        run_filtered("%s_%s_wick25" % (market, family), trades, wick_filter=True)

    # pooled: all families (may double-count same session if multiple families fire)
    run_filtered("%s_all_families" % market, any_signals, wick_filter=False)
    run_filtered("%s_all_families_wick25" % market, any_signals, wick_filter=True)

    # OR turtle-soup baseline on same tape for reference (reuse prior numbers if nq)
    vdf = pd.DataFrame([b.row() for b in books.values()])
    tdf = pd.DataFrame(all_recs)
    if not tdf.empty:
        winpct = tdf.groupby("variant").apply(lambda s: round(100.0 * (s.pnl_usd >= 0).mean(), 1))
        vdf["win_pct"] = vdf["variant"].map(winpct)
        neg = {}
        nyr = {}
        for v in vdf["variant"]:
            y = yearly_summary(tdf, v)
            neg[v] = int((y["net"] < 0).sum()) if len(y) else ""
            nyr[v] = len(y)
        vdf["neg_years"] = vdf["variant"].map(neg)
        vdf["n_years"] = vdf["variant"].map(nyr)

    sdf = pd.DataFrame(signal_rows)
    sdf.to_csv(OUT / ("%s_signals.csv" % market), index=False)
    vdf.to_csv(OUT / ("%s_stats.csv" % market), index=False)
    tdf.to_csv(OUT / ("%s_trades.csv" % market), index=False)

    md = [
        "# HTF turtle soup — %s" % market.upper(),
        "",
        "Failed break of prior HTF high/low (close5 OUT→IN), then turtle-soup the swing.",
        "Risk/targets from **that day's OR**: stop = R/5, 5ct, scale 4 @ opposite OR, runner opp 1R + BE.",
        "",
        "## Level definitions (causal)",
        "",
    ]
    for k, desc in LEVEL_SPECS.items():
        md.append("- **%s**: %s" % (k, desc))
    md.append("")
    md.append("## Signal counts")
    md.append("")
    if len(sdf):
        md.append("| Family | Signals | Wick≥0.25R |")
        md.append("|---|---:|---:|")
        for fam in LEVEL_SPECS:
            sub = sdf[sdf.family == fam]
            md.append("| %s | %d | %d |" % (fam, len(sub), int(sub.wick_ok_0_25R.sum()) if len(sub) else 0))
    md.append("")
    md.append("## Books")
    md.append("")
    cols = [
        "variant", "sessions", "fills", "fill_rate_pct", "full_stop", "scaled_4",
        "scale_rate_pct", "win_pct", "net_usd", "usd_per_fill", "profit_factor",
        "avg_risk_usd", "neg_years", "n_years",
    ]
    # ensure cols exist
    for c in cols:
        if c not in vdf.columns:
            vdf[c] = ""
    md.append("| " + " | ".join(cols) + " |")
    md.append("|" + "---|" * len(cols))
    for _, r in vdf.sort_values("net_usd", ascending=False).iterrows():
        md.append("| " + " | ".join(str(r[c]) for c in cols) + " |")

    # yearly for each family baseline
    md.append("")
    md.append("## Yearly nets (unfiltered)")
    for fam in LEVEL_SPECS:
        v = "%s_%s" % (market, fam)
        y = yearly_summary(tdf, v) if not tdf.empty else pd.DataFrame()
        if y.empty:
            continue
        y.to_csv(OUT / ("%s_%s_yearly.csv" % (market, fam)), index=False)
        md.append("")
        md.append("### %s" % fam)
        md.append("")
        md.append("| year | net | n | win% |")
        md.append("|---:|---:|---:|---:|")
        for _, r in y.iterrows():
            md.append("| %d | $%.0f | %d | %.1f |" % (r["year"], r["net"], r["n"], r["win_pct"]))

    (OUT / ("%s_SUMMARY.md" % market)).write_text("\n".join(md))
    print(vdf.sort_values("net_usd", ascending=False).to_string(index=False), flush=True)
    print("-> %s" % (OUT / ("%s_SUMMARY.md" % market)), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", nargs="+", default=["nq"])
    args = ap.parse_args()
    for m in args.markets:
        run_market(m.lower())


if __name__ == "__main__":
    main()
