"""Follow-up structure tests for the (binned) q1 fakeout satellite.

Two user-proposed structures:

A. **close5-confirmed boundary fade** — independent re-scan of q1 regime
   sessions: touch break -> first 5m close OUTSIDE the OR (break confirm,
   before 10:30) -> 5m close back INSIDE within 2 candles (failure confirm)
   -> limit entry at the broken boundary, fading toward the opposite
   boundary. Stop variants: failed extreme +/- tick, or the original-break
   1R (directional invalidation).

B. **invalidation add-on** — on the satellite's own 447 failure signals,
   trade WITH the 57%-majority outcome instead of against it: limit add at
   the OR midpoint in the ORIGINAL break direction (v2b would already be
   positioned that way), TP at the original-break 1R, stop at the opposite
   boundary (v2b's wide-stop geometry). Also reports the unconditional
   first-touch split (orig 1R vs opposite boundary vs neither) from the
   failure-confirm bar.

Analytic 1m-tape study, 1 unit, pessimistic same-bar ordering (stop before
target, fill before stop). Usage: python -m live.q1_fakeout_structure_followup
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, replace
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .q1_fakeout_loss_autopsy import (
    OUT,
    TICK,
    Trade,
    VariantResult,
    load_trades,
    reconstruct,
    rth,
    simulate,
)
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, load_1m_by_ny_date_any

BREAK_CUTOFF = time(10, 30)
Q_TRAIL, Q_MIN_HIST, Q_MAX_PCT = 250, 50, 25.0
FAIL_CANDLES5 = 2


def load_gby():
    cache = Path("/tmp/nq_gby.pkl")
    if cache.exists():
        return pickle.load(open(cache, "rb"))
    cfg = MARKETS["nq"]
    return load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)


# ----------------------------------------------------------------------
# Part A: independent close5-confirmed fade scan


def scan_close5_fades(gby, regime: set) -> List[Trade]:
    """Return pseudo-Trade records (fade direction) for the close5 sequence."""
    out: List[Trade] = []
    history: List[float] = []
    for day in sorted(gby):
        bars = rth(gby[day])
        orb = bars.between_time("09:30", "09:44")
        if len(orb) < 15:
            continue
        or_high, or_low = float(orb["high"].max()), float(orb["low"].min())
        r = or_high - or_low
        q1 = False
        if r > 0 and len(history) >= Q_MIN_HIST:
            window = history[-Q_TRAIL:]
            q1 = 100.0 * sum(1 for w in window if w <= r) / len(window) < Q_MAX_PCT
        if r > 0:
            history.append(r)
        if not q1 or day not in regime:
            continue

        post = bars[bars.index.time >= time(9, 45)]
        break_side, break_ts, extreme = "", None, None
        close_out_ts, confirm_ts = None, None
        aborted = False
        for ts, row in post.iterrows():
            if not break_side:
                if ts.time() >= BREAK_CUTOFF:
                    aborted = True
                    break
                up, dn = row["high"] > or_high, row["low"] < or_low
                if up and dn:
                    aborted = True
                    break
                if up or dn:
                    break_side = "up" if up else "down"
                    break_ts = ts
                    extreme = row["high"] if up else row["low"]
                continue
            extreme = max(extreme, row["high"]) if break_side == "up" else min(extreme, row["low"])
            hit_1r = row["high"] >= or_high + r if break_side == "up" else row["low"] <= or_low - r
            if close_out_ts is None and hit_1r:
                aborted = True  # break ran to 1R before any 5m close outside->inside sequence
                break
            if ts.minute % 5 != 4:
                continue
            close = float(row["close"])
            outside = close > or_high if break_side == "up" else close < or_low
            inside = or_low <= close <= or_high
            opp_outside = close < or_low if break_side == "up" else close > or_high
            if close_out_ts is None:
                if opp_outside:
                    aborted = True
                    break
                if outside:
                    if ts.time() >= BREAK_CUTOFF:
                        aborted = True
                        break
                    close_out_ts = ts
                continue
            # have close-outside; wait for close back inside within FAIL_CANDLES5
            n5 = int((ts - close_out_ts).total_seconds() // 300)
            if inside and n5 <= FAIL_CANDLES5:
                confirm_ts = ts
                break
            if n5 > FAIL_CANDLES5:
                aborted = True
                break
        if aborted or confirm_ts is None or not break_side:
            continue
        t = Trade(
            trade_id="close5_%s" % day.isoformat(),
            session=day,
            direction="Short" if break_side == "up" else "Long",
            entry_ts=confirm_ts,  # unused by simulate (limit entry)
            entry_price=0.0,
            exit_reasons=[],
            pnl_usd=0.0,
        )
        t.or_high, t.or_low, t.r = or_high, or_low, r
        t.break_side, t.break_ts, t.failed_extreme = break_side, break_ts, float(extreme)
        t.confirm_ts = confirm_ts
        if break_side == "up":
            t.stop = t.failed_extreme + TICK
            t.tp_bound, t.tp_1r = or_low, or_low - r
            t.invalidation = or_high + r
        else:
            t.stop = t.failed_extreme - TICK
            t.tp_bound, t.tp_1r = or_high, or_high + r
            t.invalidation = or_low - r
        out.append(t)
    return out


# ----------------------------------------------------------------------
# Part B: invalidation add-on on the satellite's 447 signals


def first_touch_split(trades: List[Trade], gby) -> Dict[str, int]:
    counts = {"orig_1r_first": 0, "opp_boundary_first": 0, "same_bar_both": 0, "neither": 0}
    for t in trades:
        after = rth(gby[t.session])
        after = after[after.index > t.confirm_ts]
        short = t.direction == "Short"  # fade direction; orig break is the other way
        res = "neither"
        for _, row in after.iterrows():
            hit_inval = row["high"] >= t.invalidation if short else row["low"] <= t.invalidation
            hit_trav = row["low"] <= t.tp_bound if short else row["high"] >= t.tp_bound
            if hit_inval and hit_trav:
                res = "same_bar_both"
                break
            if hit_inval:
                res = "orig_1r_first"
                break
            if hit_trav:
                res = "opp_boundary_first"
                break
        counts[res] += 1
    return counts


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gby = load_gby()
    cfg = MARKETS["nq"]
    regime = set(_regime_dates(cfg, gby))

    variants: Dict[str, VariantResult] = {}
    rows: List[Dict[str, object]] = []

    def run(name: str, trades: List[Trade], entry_fn, stop_fn, tp_fn):
        res = variants.setdefault(name, VariantResult(name))
        for t in trades:
            rec = simulate(res, t, gby[t.session], entry_fn(t), stop_fn(t), tp_fn(t))
            if rec:
                rows.append(rec)

    # ---- Part A
    fades = scan_close5_fades(gby, regime)
    print("Part A: close5-confirmed fade signals on q1 regime days: %d" % len(fades))
    boundary = lambda t: t.or_high if t.direction == "Short" else t.or_low
    run("A1_close5_fade_stop_extreme", fades, boundary, lambda t: t.stop, lambda t: t.tp_bound)
    run("A2_close5_fade_stop_invalidation", fades, boundary, lambda t: t.invalidation, lambda t: t.tp_bound)

    # ---- Part B
    base = load_trades()
    sat: List[Trade] = []
    for t in base:
        d = gby.get(t.session)
        if d is not None and reconstruct(t, d):
            sat.append(t)
    print("Part B: satellite failure signals reconstructed: %d" % len(sat))

    split = first_touch_split(sat, gby)
    n = sum(split.values())
    print("Unconditional first-touch from failure confirm:", {k: "%d (%.1f%%)" % (v, 100.0 * v / n) for k, v in split.items()})

    # add-on trades WITH the original break: flip direction, mid entry,
    # TP = orig 1R (t.invalidation), stop = opposite boundary -/+ tick.
    addons: List[Trade] = []
    for t in sat:
        flipped = replace(t, direction="Long" if t.direction == "Short" else "Short", trade_id="addon_" + t.trade_id)
        addons.append(flipped)
    mid = lambda t: (t.or_high + t.or_low) / 2.0
    # for the flipped (original-break-direction) trade: TP is the old invalidation
    # level; the protective stop sits at the OLD tp_bound (opposite boundary).
    run(
        "B1_addon_mid_tp_orig1r_stop_oppbound",
        addons,
        mid,
        lambda t: (t.tp_bound - TICK) if t.direction == "Long" else (t.tp_bound + TICK),
        lambda t: t.invalidation,
    )
    # tighter TP: back to the broken boundary only (half the distance)
    run(
        "B2_addon_mid_tp_broken_boundary",
        addons,
        mid,
        lambda t: (t.tp_bound - TICK) if t.direction == "Long" else (t.tp_bound + TICK),
        lambda t: t.or_high if t.direction == "Long" else t.or_low,
    )

    vdf = pd.DataFrame([v.row() for v in variants.values()])
    vdf.to_csv(OUT / "followup_variant_stats.csv", index=False)
    pd.DataFrame(rows).to_csv(OUT / "followup_variant_trades.csv", index=False)

    # yearly for the headline variants
    tdf = pd.DataFrame(rows)
    if not tdf.empty:
        tdf["year"] = pd.to_datetime(tdf["entry_ts"]).dt.year
        yearly = tdf.groupby(["variant", "year"])["pnl_usd"].agg(["sum", "count"]).reset_index()
        yearly.to_csv(OUT / "followup_yearly.csv", index=False)

    md = ["# Q1 fakeout structure follow-up (close5 fade + invalidation add-on)", ""]
    md.append("Part A signals (independent q1 scan, close5 out->in sequence): **%d sessions**." % len(fades))
    md.append("")
    md.append("Part B universe: the satellite's %d touch-failure signals. Unconditional first touch after the failure confirm:" % n)
    md.append("")
    md.append("| First touch | N | % |")
    md.append("|---|---:|---:|")
    for k, v in split.items():
        md.append("| %s | %d | %.1f |" % (k, v, 100.0 * v / n))
    md.append("")
    hdr = list(vdf.columns)
    md.append("| " + " | ".join(hdr) + " |")
    md.append("|" + "---|" * len(hdr))
    for _, r in vdf.iterrows():
        md.append("| " + " | ".join(str(r[c]) for c in hdr) + " |")
    md.append("")
    md.append("A1/A2 = limit fade at the broken boundary after touch-break -> 5m close outside (<10:30) -> 5m close back inside within 2 candles; stop at failed extreme (A1) or original-break 1R (A2); TP opposite boundary.")
    md.append("B1/B2 = limit add at OR mid in the ORIGINAL break direction after the satellite failure signal; stop past the opposite boundary; TP at original-break 1R (B1) or at the broken boundary (B2). 1 unit shown; the proposed 2-contract add scales linearly.")
    (OUT / "FOLLOWUP_SUMMARY.md").write_text("\n".join(md))
    print(vdf.to_string(index=False))
    print("outputs -> %s" % OUT)


if __name__ == "__main__":
    main()
