"""Turtle-soup structure study on close5-confirmed failed breaks.

After the existing close5 OUT -> close5 IN failure confirm, instead of
fading the OR boundary we turtle-soup the **swing created by the failed
break** (the failed extreme):

  1. touch break
  2. 5m close outside OR (before 10:30)
  3. 5m close back inside within 2 candles
  4. limit entry at the failed-extreme swing
  5. stop = swing +/- (OR_width / 5)   ~1/5 R
  6. size 5: scale 4 at the opposite OR boundary, leave 1 runner

Runner variants (a priori):
  - opp_1r     : runner targets opposite 1R; stop stays at swing stop
  - opp_1r_be  : same, but stop moves to entry after the 4-lot scale
  - eod        : runner held to 15:59; stop stays / + BE after scale

Analytic 1m tape, pessimistic same-bar (stop before target, fill before
stop). Charts 5 winners + 5 losers with gates.

Usage: python -m live.q1_fakeout_turtle_soup_study
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .q1_fakeout_loss_autopsy import OUT, POINT_VALUE, TICK, Trade, rth
from .q1_fakeout_structure_followup import load_gby, scan_close5_fades
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates

CHARTS = (
    Path(__file__).resolve().parents[1]
    / "live"
    / "state"
    / "q1_fakeout_satellite"
    / "charts"
    / "turtle_soup"
)
FEE_PER_UNIT = 1.50
EOD = time(15, 59)
ENTRY_QTY = 5
SCALE_QTY = 4
RUNNER_QTY = 1
STOP_R_FRAC = 0.2  # 1/5 of OR width


@dataclass
class BookResult:
    name: str
    sessions: int = 0
    fills: int = 0
    full_stop: int = 0  # stopped before any scale
    scaled: int = 0  # hit opposite boundary with the 4
    runner_tp: int = 0
    runner_sl: int = 0
    runner_eod: int = 0
    pnl_usd: float = 0.0
    wins_usd: float = 0.0
    losses_usd: float = 0.0
    risk_pts: List[float] = field(default_factory=list)
    risk_usd: List[float] = field(default_factory=list)

    def row(self) -> Dict[str, object]:
        pf = self.wins_usd / abs(self.losses_usd) if self.losses_usd else float("inf")
        return {
            "variant": self.name,
            "sessions": self.sessions,
            "fills": self.fills,
            "fill_rate_pct": round(100.0 * self.fills / self.sessions, 1) if self.sessions else 0,
            "full_stop": self.full_stop,
            "scaled_4": self.scaled,
            "runner_tp": self.runner_tp,
            "runner_sl": self.runner_sl,
            "runner_eod": self.runner_eod,
            "scale_rate_of_fills_pct": round(100.0 * self.scaled / self.fills, 1) if self.fills else 0,
            "net_usd": round(self.pnl_usd, 2),
            "usd_per_fill": round(self.pnl_usd / self.fills, 2) if self.fills else 0,
            "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
            "avg_risk_pts": round(sum(self.risk_pts) / len(self.risk_pts), 2) if self.risk_pts else "",
            "avg_risk_usd_5ct": round(sum(self.risk_usd) / len(self.risk_usd), 2) if self.risk_usd else "",
        }


def levels(t: Trade) -> Tuple[float, float, float, float]:
    """entry, stop, scale_tp (opp OR bound), runner_tp (opp 1R)."""
    short = t.direction == "Short"
    entry = float(t.failed_extreme)
    stop_dist = max(STOP_R_FRAC * t.r, TICK)
    if short:
        stop = entry + stop_dist
        scale_tp = t.or_low
        runner_tp = t.or_low - t.r
    else:
        stop = entry - stop_dist
        scale_tp = t.or_high
        runner_tp = t.or_high + t.r
    return entry, stop, scale_tp, runner_tp


def simulate_book(
    res: BookResult,
    t: Trade,
    day_df: pd.DataFrame,
    runner_mode: str,
) -> Optional[Dict[str, object]]:
    """Multi-leg turtle-soup book. Returns per-trade record if filled."""
    res.sessions += 1
    entry, stop0, scale_tp, runner_tp = levels(t)
    short = t.direction == "Short"
    after = rth(day_df)
    after = after[after.index > t.confirm_ts]
    if after.empty:
        return None

    filled = False
    entry_px = entry_ts = None
    stop = stop0
    remaining = ENTRY_QTY
    scaled = False
    pnl = 0.0
    exit_bits: List[str] = []
    last_exit_ts = last_exit_px = None
    scale_ts = scale_px = None
    runner_outcome = ""

    for ts, row in after.iterrows():
        if ts.time() >= EOD:
            if filled and remaining > 0:
                px = float(row["close"])
                sign = -1.0 if short else 1.0
                pnl += (px - entry_px) * sign * remaining * POINT_VALUE
                exit_bits.append("eod_x%d" % remaining)
                last_exit_ts, last_exit_px = ts, px
                runner_outcome = "eod"
                remaining = 0
            break

        if not filled:
            touched = row["high"] >= entry if short else row["low"] <= entry
            if not touched:
                continue
            filled, entry_px, entry_ts = True, float(entry), ts
            # same-bar stop after fill (pessimistic)
            stopped = row["high"] >= stop if short else row["low"] <= stop
            if stopped:
                sign = -1.0 if short else 1.0
                pnl += (float(stop) - entry_px) * sign * remaining * POINT_VALUE
                exit_bits.append("sl_x%d" % remaining)
                last_exit_ts, last_exit_px = ts, float(stop)
                runner_outcome = "full_stop"
                remaining = 0
                break
            continue

        # filled, manage
        stopped = row["high"] >= stop if short else row["low"] <= stop
        hit_scale = (not scaled) and (row["low"] <= scale_tp if short else row["high"] >= scale_tp)
        hit_runner = scaled and runner_mode.startswith("opp_1r") and (
            row["low"] <= runner_tp if short else row["high"] >= runner_tp
        )

        if stopped:
            sign = -1.0 if short else 1.0
            pnl += (float(stop) - entry_px) * sign * remaining * POINT_VALUE
            exit_bits.append("sl_x%d" % remaining)
            last_exit_ts, last_exit_px = ts, float(stop)
            runner_outcome = "full_stop" if not scaled else "runner_sl"
            remaining = 0
            break

        if hit_scale:
            sign = -1.0 if short else 1.0
            pnl += (float(scale_tp) - entry_px) * sign * SCALE_QTY * POINT_VALUE
            remaining -= SCALE_QTY
            scaled = True
            scale_ts, scale_px = ts, float(scale_tp)
            exit_bits.append("scale4@opp_bound")
            if "be" in runner_mode:
                stop = entry_px  # move stop to entry after scale
            # same-bar runner target after scale? allow if also hit (optimistic for scale first)
            if remaining > 0 and runner_mode.startswith("opp_1r"):
                hit_r = row["low"] <= runner_tp if short else row["high"] >= runner_tp
                if hit_r:
                    pnl += (float(runner_tp) - entry_px) * sign * remaining * POINT_VALUE
                    exit_bits.append("runner_tp")
                    last_exit_ts, last_exit_px = ts, float(runner_tp)
                    runner_outcome = "runner_tp"
                    remaining = 0
                    break
            continue

        if hit_runner:
            sign = -1.0 if short else 1.0
            pnl += (float(runner_tp) - entry_px) * sign * remaining * POINT_VALUE
            exit_bits.append("runner_tp")
            last_exit_ts, last_exit_px = ts, float(runner_tp)
            runner_outcome = "runner_tp"
            remaining = 0
            break

    if not filled:
        return None
    if remaining > 0:
        px = float(after.iloc[-1]["close"])
        sign = -1.0 if short else 1.0
        pnl += (px - entry_px) * sign * remaining * POINT_VALUE
        exit_bits.append("eod_x%d" % remaining)
        last_exit_ts, last_exit_px = after.index[-1], px
        runner_outcome = "eod"

    pnl -= FEE_PER_UNIT * ENTRY_QTY
    risk_pts = abs(stop0 - entry_px)
    risk_usd = risk_pts * POINT_VALUE * ENTRY_QTY

    res.fills += 1
    res.pnl_usd += pnl
    res.risk_pts.append(risk_pts)
    res.risk_usd.append(risk_usd)
    if pnl >= 0:
        res.wins_usd += pnl
    else:
        res.losses_usd += pnl
    if runner_outcome == "full_stop":
        res.full_stop += 1
    else:
        if scaled:
            res.scaled += 1
        if runner_outcome == "runner_tp":
            res.runner_tp += 1
        elif runner_outcome == "runner_sl":
            res.runner_sl += 1
        elif runner_outcome == "eod":
            res.runner_eod += 1

    return {
        "trade_id": t.trade_id,
        "variant": res.name,
        "session": t.session.isoformat(),
        "direction": t.direction,
        "break_side": t.break_side,
        "or_high": t.or_high,
        "or_low": t.or_low,
        "r": t.r,
        "failed_extreme": t.failed_extreme,
        "break_ts": t.break_ts,
        "close_out_ts": getattr(t, "close_out_ts", None),
        "confirm_ts": t.confirm_ts,
        "entry_ts": entry_ts,
        "entry_px": entry_px,
        "stop0": stop0,
        "scale_tp": scale_tp,
        "runner_tp": runner_tp,
        "scaled": scaled,
        "scale_ts": scale_ts,
        "scale_px": scale_px,
        "runner_outcome": runner_outcome,
        "exit_bits": "|".join(exit_bits),
        "last_exit_ts": last_exit_ts,
        "last_exit_px": last_exit_px,
        "pnl_usd": round(pnl, 2),
        "risk_pts": round(risk_pts, 2),
        "risk_usd_5ct": round(risk_usd, 2),
    }


def _xi(idx, ts):
    if ts is None:
        return None
    ts = pd.Timestamp(ts)
    try:
        return idx.index(ts)
    except ValueError:
        for i, t in enumerate(idx):
            if t >= ts:
                return i
        return None


def draw(rec: Dict, t: Trade, day_df: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bars = rth(day_df)
    fig, ax = plt.subplots(figsize=(15, 8))
    x = list(range(len(bars)))
    idx = list(bars.index)
    up = bars["close"] >= bars["open"]
    ax.vlines(x, bars["low"], bars["high"], color="#999", lw=0.55, zorder=1)
    ax.vlines([i for i, u in zip(x, up) if u], bars["open"][up], bars["close"][up], color="#1a9850", lw=2.2, zorder=2)
    ax.vlines(
        [i for i, u in zip(x, up) if not u], bars["close"][~up], bars["open"][~up], color="#d73027", lw=2.2, zorder=2
    )
    for level, style, color, label in [
        (t.or_high, "-", "#222", "OR high"),
        (t.or_low, "-", "#222", "OR low"),
        (rec["entry_px"], "-.", "#2166ac", "entry @ failed swing"),
        (rec["stop0"], ":", "#e08214", "SL = swing +/- R/5"),
        (rec["scale_tp"], "--", "#1a9850", "scale 4 @ opp OR"),
        (rec["runner_tp"], "--", "#66c2a5", "runner TP opp 1R"),
    ]:
        ax.axhline(level, ls=style, color=color, lw=1.1, label=label, zorder=3)

    gates = [
        (t.break_ts, "1 touch break", "D", "#542788", None),
        (getattr(t, "close_out_ts", None), "2 close5 OUT", "s", "#e08214", None),
        (t.confirm_ts, "3 close5 IN", "s", "#2166ac", None),
        (rec["entry_ts"], "4 turtle-soup fill @ swing", "^" if t.direction == "Long" else "v", "#2166ac", rec["entry_px"]),
        (rec["scale_ts"], "5 scale 4 @ opp OR", "o", "#1a9850", rec["scale_px"]),
        (rec["last_exit_ts"], "6 last exit (%s)" % rec["runner_outcome"], "X",
         "#d73027" if "sl" in rec["runner_outcome"] or rec["runner_outcome"] == "full_stop" else "#1a9850",
         rec["last_exit_px"]),
    ]
    for ts, label, marker, color, yforce in gates:
        i = _xi(idx, ts)
        if i is None:
            continue
        y = float(yforce) if yforce is not None else float(bars.iloc[i]["close"])
        ax.scatter([i], [y], marker=marker, s=160, color=color, zorder=6, edgecolors="white", linewidths=0.6)
        ax.annotate(
            label, xy=(i, y), xytext=(8, 12), textcoords="offset points",
            fontsize=8, color=color, fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=color, lw=0.7),
        )
    hours = [i for i, ts in enumerate(idx) if ts.minute == 0]
    ax.set_xticks(hours)
    ax.set_xticklabels([idx[i].strftime("%H:%M") for i in hours])
    tag = "WIN" if rec["pnl_usd"] >= 0 else "LOSS"
    ax.set_title(
        "Turtle soup @ failed swing | %s %s %s | pnl $%.0f | R=%.2f risk=%.1fpts ($%.0f/5ct) | %s"
        % (t.session, t.direction, tag, rec["pnl_usd"], t.r, rec["risk_pts"], rec["risk_usd_5ct"], rec["exit_bits"])
    )
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


def spread(rows: List[pd.Series], n: int) -> List[pd.Series]:
    if len(rows) <= n:
        return rows
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    (CHARTS / "winners").mkdir(exist_ok=True)
    (CHARTS / "losers").mkdir(exist_ok=True)

    gby = load_gby()
    cfg = MARKETS["nq"]
    regime = set(_regime_dates(cfg, gby))
    fades = scan_close5_fades(gby, regime)
    print("close5 fade signals: %d" % len(fades), flush=True)

    modes = {
        "TS_opp1r": "opp_1r",
        "TS_opp1r_be": "opp_1r_be",
        "TS_eod": "eod",
        "TS_eod_be": "eod_be",
    }
    books: Dict[str, BookResult] = {k: BookResult(k) for k in modes}
    all_recs: List[Dict[str, object]] = []

    for t in fades:
        for name, mode in modes.items():
            rec = simulate_book(books[name], t, gby[t.session], mode)
            if rec:
                all_recs.append(rec)

    vdf = pd.DataFrame([b.row() for b in books.values()])
    tdf = pd.DataFrame(all_recs)
    vdf.to_csv(OUT / "turtle_soup_stats.csv", index=False)
    tdf.to_csv(OUT / "turtle_soup_trades.csv", index=False)

    # yearly for primary book
    primary = tdf[tdf["variant"] == "TS_opp1r_be"].copy()
    primary["year"] = pd.to_datetime(primary["entry_ts"], utc=True).dt.year
    yearly = primary.groupby("year").agg(net=("pnl_usd", "sum"), n=("pnl_usd", "count"), wins=("pnl_usd", lambda s: (s >= 0).sum()))
    yearly["win_pct"] = (100.0 * yearly["wins"] / yearly["n"]).round(1)
    yearly = yearly.reset_index()
    yearly.to_csv(OUT / "turtle_soup_yearly_opp1r_be.csv", index=False)

    print(vdf.to_string(index=False), flush=True)
    print("\nYearly TS_opp1r_be:", flush=True)
    print(yearly.to_string(index=False), flush=True)

    # charts from primary book
    fade_by_id = {t.trade_id: t for t in fades}
    wins = primary[primary["pnl_usd"] >= 0].sort_values(["year", "pnl_usd"], ascending=[True, False])
    losses = primary[primary["pnl_usd"] < 0].sort_values(["year", "pnl_usd"], ascending=[True, True])
    win_rows = spread([r for _, r in wins.iterrows()], 5)
    loss_rows = spread([r for _, r in losses.iterrows()], 5)

    lines = [
        "# Turtle soup @ failed-break swing — gate charts",
        "",
        "Structure: close5 OUT → close5 IN → **limit at failed extreme** (turtle-soup the swing),",
        "stop = swing ± R/5, size 5 = scale 4 at opposite OR boundary + 1 runner to opp 1R",
        "(stop → entry after scale). Variant charted: `TS_opp1r_be`.",
        "",
        "## Winners (5)",
        "",
    ]
    for r in win_rows:
        t = fade_by_id[str(r["trade_id"])]
        path = CHARTS / "winners" / ("%s_%s_pnl%.0f.png" % (t.session, t.direction, r["pnl_usd"]))
        draw(r.to_dict(), t, gby[t.session], path)
        lines.append("- `%s` %s $%.0f — ![](winners/%s)" % (t.session, t.direction, r["pnl_usd"], path.name))
        print("winner", path.name, flush=True)
    lines += ["", "## Losers (5)", ""]
    for r in loss_rows:
        t = fade_by_id[str(r["trade_id"])]
        path = CHARTS / "losers" / ("%s_%s_pnl%.0f.png" % (t.session, t.direction, r["pnl_usd"]))
        draw(r.to_dict(), t, gby[t.session], path)
        lines.append("- `%s` %s $%.0f — ![](losers/%s)" % (t.session, t.direction, r["pnl_usd"], path.name))
        print("loser", path.name, flush=True)
    (CHARTS / "INDEX.md").write_text("\n".join(lines))

    md = [
        "# Turtle soup of the failed-break swing (close5-confirmed)",
        "",
        "Universe: same close5 OUT→IN q1-regime signals as A1 (%d sessions)." % len(fades),
        "Entry = limit at the **failed extreme** (the swing the fakeout made).",
        "Stop = that swing ± **R/5**. Size **5**: scale **4** at opposite OR boundary, **1 runner**.",
        "",
        "## Book stats (NQ, 1-tick analytic, $1.50/RT/unit)",
        "",
    ]
    hdr = list(vdf.columns)
    md.append("| " + " | ".join(hdr) + " |")
    md.append("|" + "---|" * len(hdr))
    for _, r in vdf.iterrows():
        md.append("| " + " | ".join(str(r[c]) for c in hdr) + " |")
    md.append("")
    md.append("## Yearly (`TS_opp1r_be`)")
    md.append("")
    md.append("| year | net | n | wins | win% |")
    md.append("|---:|---:|---:|---:|---:|")
    for _, r in yearly.iterrows():
        md.append("| %d | $%.0f | %d | %d | %.1f |" % (r["year"], r["net"], r["n"], r["wins"], r["win_pct"]))
    neg = int((yearly["net"] < 0).sum())
    md.append("")
    md.append("Negative years: %d / %d. Charts: `charts/turtle_soup/`." % (neg, len(yearly)))
    (OUT / "TURTLE_SOUP_SUMMARY.md").write_text("\n".join(md))
    print("outputs -> %s ; charts -> %s" % (OUT, CHARTS), flush=True)


if __name__ == "__main__":
    main()
