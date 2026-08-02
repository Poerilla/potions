"""Loss autopsy + trade-structure what-ifs for the q1 fakeout reversal satellite.

Questions (from review of the rejected satellite):

1. Of the baseline stop-outs, how many are **directional invalidation**
   (the original break resumes and reaches its own 1R after clipping us)
   vs **shakeouts** (price still traverses to the opposite boundary after
   our stop) vs chop (neither)?
2. Can the 0.92 flip cell be monetised with a better-structured trade —
   deeper limit entries (at the failed extreme, at a retest of the broken
   level, at a pre-entry 5m swing incl. the London session) with the stop
   moved to the true invalidation level (original-break 1R)?

Analytic 1m-tape event study over the 447 actual NQ trades of the
broker-like replay (entries/exits read from the replay fills; levels
reconstructed deterministically with the plugin's own rules). Same-bar
ambiguity is resolved pessimistically (stop before target, fill before
stop). Also renders 100 loser / 100 winner charts for visual validation.

Usage:  python -m live.q1_fakeout_loss_autopsy [--no-charts]
"""

from __future__ import annotations

import argparse
import pickle
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / "live" / "state" / "q1_fakeout_satellite"
FILLS = STATE / "states" / "nq_q1_fakeout_split" / "fills.csv"
OUT = STATE / "autopsy"
CHARTS = STATE / "charts"

TICK = 0.25
POINT_VALUE = 20.0
FEE = 1.50  # per unit round trip
OR_END = time(9, 45)
BREAK_CUTOFF = time(10, 30)
EOD = time(15, 59)


@dataclass
class Trade:
    trade_id: str
    session: date
    direction: str  # Long/Short (the reversal trade)
    entry_ts: pd.Timestamp
    entry_price: float
    exit_reasons: List[str]
    pnl_usd: float  # actual replay pnl (2 units, fees included)
    # reconstructed levels
    or_high: float = 0.0
    or_low: float = 0.0
    r: float = 0.0
    break_side: str = ""  # side of the ORIGINAL failed break
    break_ts: Optional[pd.Timestamp] = None
    failed_extreme: float = 0.0
    stop: float = 0.0  # as traded
    tp_bound: float = 0.0  # opposite boundary
    tp_1r: float = 0.0  # opposite 1R
    invalidation: float = 0.0  # original-break 1R level
    confirm_ts: Optional[pd.Timestamp] = None
    stop_ts: Optional[pd.Timestamp] = None
    loser_class: str = ""
    minutes_to_stop: Optional[int] = None


def load_trades() -> List[Trade]:
    fills = pd.read_csv(FILLS, parse_dates=["ts"])
    trades: List[Trade] = []
    for tid, grp in fills.groupby("trade_id", sort=True):
        grp = grp.sort_values("ts")
        ent = grp[grp["reason"] == "entry"].iloc[0]
        exits = grp[grp["reason"] != "entry"]
        direction = "Long" if ent["side"] == "buy" else "Short"
        sign = 1.0 if direction == "Long" else -1.0
        pnl = 0.0
        for _, ex in exits.iterrows():
            pnl += sign * (float(ex["price"]) - float(ent["price"])) * float(ex["quantity"]) * POINT_VALUE
        pnl -= FEE * float(ent["quantity"])
        stop_rows = exits[exits["reason"] == "stop"]
        t = Trade(
            trade_id=str(tid),
            session=pd.Timestamp(ent["ts"]).date(),
            direction=direction,
            entry_ts=pd.Timestamp(ent["ts"]),
            entry_price=float(ent["price"]),
            exit_reasons=list(exits["reason"]),
            pnl_usd=pnl,
            stop_ts=pd.Timestamp(stop_rows.iloc[0]["ts"]) if len(stop_rows) else None,
        )
        trades.append(t)
    return trades


def rth(df: pd.DataFrame) -> pd.DataFrame:
    return df.between_time("09:30", "15:59")


def reconstruct(t: Trade, day_df: pd.DataFrame) -> bool:
    bars = rth(day_df)
    orb = bars.between_time("09:30", "09:44")
    if orb.empty:
        return False
    t.or_high = float(orb["high"].max())
    t.or_low = float(orb["low"].min())
    t.r = t.or_high - t.or_low
    post = bars[bars.index.time >= OR_END]
    break_side = ""
    extreme = None
    for ts, row in post.iterrows():
        if not break_side:
            if ts.time() >= BREAK_CUTOFF:
                return False
            up = row["high"] > t.or_high
            dn = row["low"] < t.or_low
            if up and dn:
                return False
            if up or dn:
                break_side = "up" if up else "down"
                t.break_ts = ts
                extreme = row["high"] if up else row["low"]
        else:
            if ts >= t.entry_ts:  # entry fill bar: confirm bar was the previous one
                break
            extreme = max(extreme, row["high"]) if break_side == "up" else min(extreme, row["low"])
    if not break_side or extreme is None:
        return False
    t.break_side = break_side
    t.failed_extreme = float(extreme)
    t.confirm_ts = t.entry_ts - pd.Timedelta(minutes=1)
    if break_side == "up":
        t.stop = t.failed_extreme + TICK
        t.tp_bound, t.tp_1r = t.or_low, t.or_low - t.r
        t.invalidation = t.or_high + t.r
    else:
        t.stop = t.failed_extreme - TICK
        t.tp_bound, t.tp_1r = t.or_high, t.or_high + t.r
        t.invalidation = t.or_low - t.r
    return True


def classify_loser(t: Trade, day_df: pd.DataFrame) -> None:
    """After the actual stop-out, what happened first: traverse or invalidation?"""
    if t.stop_ts is None:
        return
    after = rth(day_df)
    after = after[after.index > t.stop_ts]
    short = t.direction == "Short"
    for _, row in after.iterrows():
        hit_traverse = row["low"] <= t.tp_bound if short else row["high"] >= t.tp_bound
        hit_inval = row["high"] >= t.invalidation if short else row["low"] <= t.invalidation
        if hit_inval and hit_traverse:
            t.loser_class = "same_bar_both"
            return
        if hit_inval:
            t.loser_class = "invalidation_continuation"
            return
        if hit_traverse:
            t.loser_class = "shakeout_then_traverse"
            return
    t.loser_class = "chop_neither"


# ----------------------------------------------------------------------
# What-if variants (single unit, analytic, pessimistic same-bar ordering)


@dataclass
class VariantResult:
    name: str
    sessions: int = 0
    fills: int = 0
    tp: int = 0
    sl: int = 0
    eod: int = 0
    pnl_usd: float = 0.0
    risk_pts: List[float] = field(default_factory=list)
    wins_usd: float = 0.0
    losses_usd: float = 0.0

    def row(self) -> Dict[str, object]:
        per_fill = self.pnl_usd / self.fills if self.fills else 0.0
        pf = self.wins_usd / abs(self.losses_usd) if self.losses_usd else float("inf")
        return {
            "variant": self.name,
            "sessions": self.sessions,
            "fills": self.fills,
            "fill_rate_pct": round(100.0 * self.fills / self.sessions, 1) if self.sessions else 0,
            "tp": self.tp,
            "sl": self.sl,
            "eod": self.eod,
            "tp_rate_of_fills_pct": round(100.0 * self.tp / self.fills, 1) if self.fills else 0,
            "net_usd_1unit": round(self.pnl_usd, 2),
            "usd_per_fill": round(per_fill, 2),
            "usd_per_session": round(self.pnl_usd / self.sessions, 2) if self.sessions else 0,
            "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
            "avg_risk_pts": round(sum(self.risk_pts) / len(self.risk_pts), 2) if self.risk_pts else "",
        }


def simulate(
    res: VariantResult,
    t: Trade,
    day_df: pd.DataFrame,
    entry_level: Optional[float],
    stop_level: float,
    tp_level: float,
    entry_is_market: bool = False,
) -> Optional[Dict[str, object]]:
    """Simulate one variant on one session. Returns per-trade record if filled."""
    res.sessions += 1
    if entry_level is None:
        return None
    short = t.direction == "Short"
    after = rth(day_df)
    after = after[after.index > t.confirm_ts]
    filled = False
    entry_px = None
    entry_ts = None
    outcome, exit_px, exit_ts = "", None, None
    for ts, row in after.iterrows():
        if ts.time() >= EOD:
            if filled:
                outcome, exit_px, exit_ts = "eod", float(row["close"]), ts
            break
        if not filled:
            if entry_is_market:
                filled, entry_px, entry_ts = True, float(row["open"]), ts
            else:
                touched = row["high"] >= entry_level if short else row["low"] <= entry_level
                if touched:
                    filled, entry_px, entry_ts = True, float(entry_level), ts
            if not filled:
                continue
            # pessimistic: same-bar stop after fill
            stopped = row["high"] >= stop_level if short else row["low"] <= stop_level
            if stopped:
                outcome, exit_px, exit_ts = "sl", float(stop_level), ts
                break
            continue
        stopped = row["high"] >= stop_level if short else row["low"] <= stop_level
        hit_tp = row["low"] <= tp_level if short else row["high"] >= tp_level
        if stopped:  # stop-first pessimism
            outcome, exit_px, exit_ts = "sl", float(stop_level), ts
            break
        if hit_tp:
            outcome, exit_px, exit_ts = "tp", float(tp_level), ts
            break
    if not filled:
        return None
    if not outcome:  # data ended intraday
        outcome, exit_px, exit_ts = "eod", float(after.iloc[-1]["close"]), after.index[-1]
    sign = 1.0 if not short else -1.0
    pnl = (exit_px - entry_px) * sign * POINT_VALUE - FEE
    res.fills += 1
    res.pnl_usd += pnl
    res.risk_pts.append(abs(stop_level - entry_px))
    if pnl >= 0:
        res.wins_usd += pnl
    else:
        res.losses_usd += pnl
    setattr(res, "_last", None)
    if outcome == "tp":
        res.tp += 1
    elif outcome == "sl":
        res.sl += 1
    else:
        res.eod += 1
    return {
        "trade_id": t.trade_id,
        "variant": res.name,
        "entry_ts": entry_ts,
        "entry_px": entry_px,
        "outcome": outcome,
        "exit_ts": exit_ts,
        "exit_px": exit_px,
        "pnl_usd": round(pnl, 2),
    }


def swing_level(t: Trade, day_df: pd.DataFrame) -> Optional[float]:
    """Nearest confirmed 5m fractal swing beyond the failed extreme, formed
    03:00 NY -> confirm bar (includes the London session). Causal: the swing
    needs 2 closed 5m bars after its extreme, all before the confirm bar."""
    pre = day_df.between_time("03:00", "15:59")
    pre = pre[pre.index <= t.confirm_ts]
    if len(pre) < 30:
        return None
    b5 = pre.resample("5min").agg({"high": "max", "low": "min"}).dropna()
    if len(b5) < 5:
        return None
    b5 = b5.iloc[:-1]  # last 5m bucket may be partial at confirm time
    short = t.direction == "Short"
    candidates: List[float] = []
    vals = b5["high" if short else "low"].tolist()
    for i in range(2, len(vals) - 2):
        v = vals[i]
        if short and v > max(vals[i - 2], vals[i - 1], vals[i + 1], vals[i + 2]):
            if v > t.failed_extreme:
                candidates.append(v)
        elif not short and v < min(vals[i - 2], vals[i - 1], vals[i + 1], vals[i + 2]):
            if v < t.failed_extreme:
                candidates.append(v)
    if not candidates:
        return None
    return min(candidates) if short else max(candidates)


# ----------------------------------------------------------------------


def draw_chart(t: Trade, day_df: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bars = rth(day_df)
    fig, ax = plt.subplots(figsize=(14, 7))
    x = range(len(bars))
    idx = list(bars.index)
    up = bars["close"] >= bars["open"]
    ax.vlines(x, bars["low"], bars["high"], color="#999", lw=0.6, zorder=1)
    ax.vlines([i for i, u in zip(x, up) if u], bars["open"][up], bars["close"][up], color="#1a9850", lw=2.4, zorder=2)
    ax.vlines(
        [i for i, u in zip(x, up) if not u], bars["close"][~up], bars["open"][~up], color="#d73027", lw=2.4, zorder=2
    )
    for level, style, color, label in [
        (t.or_high, "-", "#333", "OR high"),
        (t.or_low, "-", "#333", "OR low"),
        (t.invalidation, "--", "#d73027", "orig 1R (invalidation)"),
        (t.tp_1r, "--", "#1a9850", "opp 1R"),
        (t.stop, ":", "#e08214", "stop (failed extreme)"),
    ]:
        ax.axhline(level, ls=style, color=color, lw=1.0, label=label)

    def xi(ts: pd.Timestamp) -> Optional[int]:
        try:
            return idx.index(ts)
        except ValueError:
            return None

    ei = xi(t.entry_ts)
    if ei is not None:
        ax.scatter([ei], [t.entry_price], marker="^" if t.direction == "Long" else "v", s=140, color="#2166ac", zorder=5, label="entry")
    if t.stop_ts is not None:
        si = xi(t.stop_ts)
        if si is not None:
            ax.scatter([si], [t.stop], marker="x", s=120, color="#d73027", zorder=5, label="stop-out")
    hours = [i for i, ts in enumerate(idx) if ts.minute == 0]
    ax.set_xticks(hours)
    ax.set_xticklabels([idx[i].strftime("%H:%M") for i in hours])
    tag = "WIN" if t.pnl_usd >= 0 else "LOSS"
    ax.set_title(
        "%s  %s  %s  pnl $%.0f  %s" % (t.session, t.direction, tag, t.pnl_usd, t.loser_class or "")
    )
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def spread_sample(items: List[Trade], n: int) -> List[Trade]:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-charts", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    cache = Path("/tmp/nq_gby.pkl")
    if cache.exists():
        gby = pickle.load(open(cache, "rb"))
    else:
        cfg = MARKETS["nq"]
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)

    trades = load_trades()
    ok: List[Trade] = []
    for t in trades:
        day_df = gby.get(t.session)
        if day_df is None or not reconstruct(t, day_df):
            continue
        if t.pnl_usd < 0 and t.stop_ts is not None:
            classify_loser(t, day_df)
            t.minutes_to_stop = int((t.stop_ts - t.entry_ts).total_seconds() // 60)
        ok.append(t)
    losers = [t for t in ok if t.pnl_usd < 0]
    winners = [t for t in ok if t.pnl_usd >= 0]
    print("reconstructed %d/%d trades; losers %d winners %d" % (len(ok), len(trades), len(losers), len(winners)))

    # ---- loser cause table
    cause = pd.Series([t.loser_class for t in losers if t.loser_class]).value_counts()
    mins = pd.Series([t.minutes_to_stop for t in losers if t.minutes_to_stop is not None])
    cause_df = cause.rename_axis("cause").reset_index(name="n")
    cause_df["pct"] = (100.0 * cause_df["n"] / cause_df["n"].sum()).round(1)
    cause_df.to_csv(OUT / "loser_causes.csv", index=False)

    # ---- variants
    variants: Dict[str, VariantResult] = {}
    per_trade_rows: List[Dict[str, object]] = []

    def run(name: str, entry_fn, stop_fn, tp_fn, market_entry=False):
        res = variants.setdefault(name, VariantResult(name))
        for t in ok:
            day_df = gby[t.session]
            rec = simulate(res, t, day_df, entry_fn(t, day_df), stop_fn(t), tp_fn(t), entry_is_market=market_entry)
            if rec:
                per_trade_rows.append(rec)

    run("V0_asis_1unit_tp_bound", lambda t, d: t.entry_price, lambda t: t.stop, lambda t: t.tp_bound, market_entry=True)
    run("V5_asis_entry_deep_stop", lambda t, d: t.entry_price, lambda t: t.invalidation, lambda t: t.tp_bound, market_entry=True)
    run("V3_retest_broken_level", lambda t, d: t.or_high if t.direction == "Short" else t.or_low, lambda t: t.invalidation, lambda t: t.tp_bound)
    run("V3b_retest_stop_extreme", lambda t, d: t.or_high if t.direction == "Short" else t.or_low, lambda t: t.stop, lambda t: t.tp_bound)
    run("V1_limit_at_failed_extreme", lambda t, d: t.failed_extreme, lambda t: t.invalidation, lambda t: t.tp_bound)
    run("V1b_limit_extreme_tp_opp1r", lambda t, d: t.failed_extreme, lambda t: t.invalidation, lambda t: t.tp_1r)
    run("V4_swing_5m_london", swing_level, lambda t: t.invalidation, lambda t: t.tp_bound)

    vdf = pd.DataFrame([v.row() for v in variants.values()])
    vdf.to_csv(OUT / "variant_stats.csv", index=False)
    pd.DataFrame(per_trade_rows).to_csv(OUT / "variant_trades.csv", index=False)

    # ---- yearly stability of the best-looking variants is left to the reader (CSV has ts)

    # ---- charts
    n_l = n_w = 0
    if not args.no_charts:
        (CHARTS / "losers").mkdir(parents=True, exist_ok=True)
        (CHARTS / "winners").mkdir(parents=True, exist_ok=True)
        for t in spread_sample(losers, 100):
            draw_chart(t, gby[t.session], CHARTS / "losers" / ("%s_%s.png" % (t.session, t.direction)))
            n_l += 1
        for t in spread_sample(winners, 100):
            draw_chart(t, gby[t.session], CHARTS / "winners" / ("%s_%s.png" % (t.session, t.direction)))
            n_w += 1
        lines = ["# q1 fakeout charts", "", "## Losers (%d)" % n_l, ""]
        lines += ["- ![](losers/%s)" % p.name for p in sorted((CHARTS / "losers").glob("*.png"))]
        lines += ["", "## Winners (%d)" % n_w, ""]
        lines += ["- ![](winners/%s)" % p.name for p in sorted((CHARTS / "winners").glob("*.png"))]
        (CHARTS / "INDEX.md").write_text("\n".join(lines))
        print("charts: %d losers, %d winners -> %s" % (n_l, n_w, CHARTS))

    # ---- summary
    md = ["# Q1 fakeout satellite — loss autopsy & structure what-ifs", ""]
    md.append("Reconstructed %d of %d replay trades. Losers %d, winners %d (trade-level, actual replay PnL)." % (len(ok), len(trades), len(losers), len(winners)))
    md.append("")
    md.append("## Why do we stop out? (after the actual stop, first touch by EOD)")
    md.append("")
    md.append("| Cause | N | % |")
    md.append("|---|---:|---:|")
    for _, r in cause_df.iterrows():
        md.append("| %s | %d | %.1f |" % (r["cause"], r["n"], r["pct"]))
    md.append("")
    md.append("Minutes from entry to stop: median %.0f, p25 %.0f, p75 %.0f." % (mins.median(), mins.quantile(0.25), mins.quantile(0.75)))
    md.append("")
    md.append("## Trade-structure variants (1 unit, analytic 1m tape, pessimistic same-bar ordering)")
    md.append("")
    hdr = list(vdf.columns)
    md.append("| " + " | ".join(hdr) + " |")
    md.append("|" + "---|" * len(hdr))
    for _, r in vdf.iterrows():
        md.append("| " + " | ".join(str(r[c]) for c in hdr) + " |")
    md.append("")
    md.append("Variant key: V0 = as traded (single unit, TP at opposite boundary); V5 = same market entry but stop moved to the original-break 1R (directional invalidation); V3/V3b = limit entry on a retest of the broken OR level (stop at invalidation / at failed extreme); V1/V1b = limit entry at the failed extreme itself (old stop becomes entry), stop at invalidation; V4 = limit at the nearest confirmed 5m swing beyond the failed extreme (03:00 NY onward, includes London).")
    (OUT / "SUMMARY.md").write_text("\n".join(md))
    print(vdf.to_string(index=False))
    print("outputs -> %s" % OUT)


if __name__ == "__main__":
    main()
