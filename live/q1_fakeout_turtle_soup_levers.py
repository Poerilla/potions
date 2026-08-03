"""Turtle-soup levers + stop-out autopsy + scale-in experiment.

Experiments on the close5-confirmed failed-break universe:

1. **Stop-out autopsy** — after a full stop on the baseline book, did price
   still reach the opposite OR / opp 1R? (shakeout that could have won)
2. **Levers** (baseline geometry = limit @ failed extreme, 5ct, scale 4 @
   opp OR + runner opp1r with BE after scale):
   - stop floor in ticks: max(R/5, N ticks)
   - stop fraction: R/4, R/5, R/6, R/8
   - entry buffer: soup N ticks beyond the failed extreme (deeper retest)
   - filters: min wick beyond OR (as fraction of R), break before 10:00
3. **Scale-in** — instead of 5@swing, arm up to 5 equal-spaced limits
   spanning the average MAE of baseline *winning* trades toward the stop;
   remaining contracts stay unfilled if price never reaches them. Stop sits
   one tick beyond the last rung (or at max(R/5, floor) if wider).

Usage: python -m live.q1_fakeout_turtle_soup_levers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .q1_fakeout_loss_autopsy import OUT, POINT_VALUE, TICK, Trade, rth
from .q1_fakeout_structure_followup import load_gby, scan_close5_fades
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates

FEE = 1.50
EOD = time(15, 59)
ENTRY_QTY = 5
SCALE_QTY = 4


@dataclass
class Book:
    name: str
    sessions: int = 0
    fills: int = 0  # sessions with ≥1 contract filled
    contracts_filled: float = 0.0
    full_stop: int = 0
    scaled: int = 0
    runner_tp: int = 0
    runner_sl: int = 0
    runner_eod: int = 0
    pnl: float = 0.0
    wins: float = 0.0
    losses: float = 0.0
    risk_usd: List[float] = field(default_factory=list)
    filled_qty: List[int] = field(default_factory=list)

    def row(self) -> Dict[str, object]:
        pf = self.wins / abs(self.losses) if self.losses else float("inf")
        return {
            "variant": self.name,
            "sessions": self.sessions,
            "fills": self.fills,
            "fill_rate_pct": round(100.0 * self.fills / self.sessions, 1) if self.sessions else 0,
            "avg_filled_qty": round(sum(self.filled_qty) / len(self.filled_qty), 2) if self.filled_qty else "",
            "full_stop": self.full_stop,
            "scaled_4": self.scaled,
            "scale_rate_pct": round(100.0 * self.scaled / self.fills, 1) if self.fills else 0,
            "runner_tp": self.runner_tp,
            "net_usd": round(self.pnl, 2),
            "usd_per_fill": round(self.pnl / self.fills, 2) if self.fills else 0,
            "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
            "avg_risk_usd": round(sum(self.risk_usd) / len(self.risk_usd), 2) if self.risk_usd else "",
            "win_pct": "",  # filled below
        }


def stop_dist(r: float, frac: float, floor_ticks: int) -> float:
    return max(frac * r, floor_ticks * TICK, TICK)


def geometry(
    t: Trade,
    frac: float = 0.2,
    floor_ticks: int = 1,
    entry_buffer_ticks: int = 0,
) -> Tuple[float, float, float, float]:
    short = t.direction == "Short"
    buf = entry_buffer_ticks * TICK
    if short:
        entry = float(t.failed_extreme) + buf  # deeper = higher for short
        stop = entry + stop_dist(t.r, frac, floor_ticks)
        scale_tp, runner_tp = t.or_low, t.or_low - t.r
    else:
        entry = float(t.failed_extreme) - buf
        stop = entry - stop_dist(t.r, frac, floor_ticks)
        scale_tp, runner_tp = t.or_high, t.or_high + t.r
    return entry, stop, scale_tp, runner_tp


def simulate(
    book: Book,
    t: Trade,
    day_df: pd.DataFrame,
    frac: float = 0.2,
    floor_ticks: int = 1,
    entry_buffer_ticks: int = 0,
    scale_in_width: Optional[float] = None,
    max_qty: int = ENTRY_QTY,
) -> Optional[Dict[str, object]]:
    """Single-shot or scale-in turtle soup. BE after scale, runner to opp 1R."""
    book.sessions += 1
    entry0, stop0, scale_tp, runner_tp = geometry(t, frac, floor_ticks, entry_buffer_ticks)
    short = t.direction == "Short"
    after = rth(day_df)
    after = after[after.index > t.confirm_ts]
    if after.empty:
        return None

    # Build entry ladder (prices from entry0 toward the stop)
    if scale_in_width is None or scale_in_width <= 0 or max_qty <= 1:
        ladder = [entry0]
        qty_each = [max_qty]
    else:
        # max_qty equal-spaced limits spanning scale_in_width toward stop
        width = min(scale_in_width, abs(stop0 - entry0) - TICK)
        if width <= 0:
            ladder, qty_each = [entry0], [max_qty]
        else:
            # N rungs, equal intervals; 1 contract each until max_qty
            n = max_qty
            step = width / (n - 1) if n > 1 else 0.0
            if short:
                ladder = [entry0 + i * step for i in range(n)]
            else:
                ladder = [entry0 - i * step for i in range(n)]
            qty_each = [1] * n
            # stop one tick beyond last rung if that is tighter than stop0? keep stop0 (outer)
            # but ensure stop is beyond last rung
            if short:
                stop0 = max(stop0, ladder[-1] + TICK)
            else:
                stop0 = min(stop0, ladder[-1] - TICK)

    pending = list(zip(ladder, qty_each))  # unfilled limits
    pos_qty = 0
    # weighted avg entry for PnL
    cost_pts = 0.0  # sum(px * qty)
    stop = stop0
    scaled = False
    remaining_after_scale_target = SCALE_QTY  # how many of open go to scale tp
    pnl = 0.0
    exit_bits: List[str] = []
    first_entry_ts = first_entry_px = None
    last_exit_ts = last_exit_px = None
    scale_ts = None
    runner_outcome = ""
    peak_qty = 0

    def avg_entry() -> float:
        return cost_pts / pos_qty if pos_qty else entry0

    for ts, row in after.iterrows():
        if ts.time() >= EOD:
            if pos_qty > 0:
                px = float(row["close"])
                sign = -1.0 if short else 1.0
                pnl += (px - avg_entry()) * sign * pos_qty * POINT_VALUE
                exit_bits.append("eod_x%d" % pos_qty)
                last_exit_ts, last_exit_px = ts, px
                runner_outcome = "eod"
                pos_qty = 0
            break

        # fill any touched ladder rungs (adverse direction)
        still = []
        for px, q in pending:
            touched = row["high"] >= px if short else row["low"] <= px
            if touched:
                pos_qty += q
                cost_pts += px * q
                peak_qty = max(peak_qty, pos_qty)
                if first_entry_ts is None:
                    first_entry_ts, first_entry_px = ts, px
                exit_bits.append("add%d@%.2f" % (q, px) if len(exit_bits) or pos_qty > q else "entry%d@%.2f" % (q, px))
            else:
                still.append((px, q))
        pending = still

        if pos_qty == 0:
            continue

        # stop (pessimistic before targets)
        stopped = row["high"] >= stop if short else row["low"] <= stop
        if stopped:
            sign = -1.0 if short else 1.0
            pnl += (float(stop) - avg_entry()) * sign * pos_qty * POINT_VALUE
            exit_bits.append("sl_x%d" % pos_qty)
            last_exit_ts, last_exit_px = ts, float(stop)
            runner_outcome = "full_stop" if not scaled else "runner_sl"
            pos_qty = 0
            break

        # scale 4 at opposite OR (from current open size, up to SCALE_QTY)
        if not scaled:
            hit_scale = row["low"] <= scale_tp if short else row["high"] >= scale_tp
            if hit_scale:
                take = min(SCALE_QTY, pos_qty)
                # Prefer leaving 1 runner if we have >=5; if fewer, scale all but 1 if qty>=2
                if pos_qty >= ENTRY_QTY:
                    take = SCALE_QTY
                elif pos_qty >= 2:
                    take = pos_qty - 1
                else:
                    take = 0
                if take > 0:
                    sign = -1.0 if short else 1.0
                    ae = avg_entry()
                    pnl += (float(scale_tp) - ae) * sign * take * POINT_VALUE
                    # reduce position; adjust cost basis proportionally
                    cost_pts *= (pos_qty - take) / pos_qty
                    pos_qty -= take
                    scaled = True
                    scale_ts = ts
                    exit_bits.append("scale%d@opp" % take)
                    stop = ae  # BE after scale
                    # same-bar runner tp
                    if pos_qty > 0:
                        hit_r = row["low"] <= runner_tp if short else row["high"] >= runner_tp
                        if hit_r:
                            pnl += (float(runner_tp) - avg_entry()) * sign * pos_qty * POINT_VALUE
                            exit_bits.append("runner_tp")
                            last_exit_ts, last_exit_px = ts, float(runner_tp)
                            runner_outcome = "runner_tp"
                            pos_qty = 0
                            break
                continue

        # runner tp
        if scaled and pos_qty > 0:
            hit_r = row["low"] <= runner_tp if short else row["high"] >= runner_tp
            if hit_r:
                sign = -1.0 if short else 1.0
                pnl += (float(runner_tp) - avg_entry()) * sign * pos_qty * POINT_VALUE
                exit_bits.append("runner_tp")
                last_exit_ts, last_exit_px = ts, float(runner_tp)
                runner_outcome = "runner_tp"
                pos_qty = 0
                break

    if first_entry_ts is None:
        return None
    if pos_qty > 0:
        px = float(after.iloc[-1]["close"])
        sign = -1.0 if short else 1.0
        pnl += (px - avg_entry()) * sign * pos_qty * POINT_VALUE
        exit_bits.append("eod_x%d" % pos_qty)
        last_exit_ts, last_exit_px = after.index[-1], px
        runner_outcome = "eod"

    pnl -= FEE * peak_qty
    # risk = stop distance from first rung * peak qty (conservative) / or from avg
    risk = abs(stop0 - entry0) * POINT_VALUE * peak_qty

    book.fills += 1
    book.pnl += pnl
    book.contracts_filled += peak_qty
    book.filled_qty.append(peak_qty)
    book.risk_usd.append(risk)
    if pnl >= 0:
        book.wins += pnl
    else:
        book.losses += pnl
    if runner_outcome == "full_stop":
        book.full_stop += 1
    else:
        if scaled:
            book.scaled += 1
        if runner_outcome == "runner_tp":
            book.runner_tp += 1
        elif runner_outcome == "runner_sl":
            book.runner_sl += 1
        elif runner_outcome == "eod":
            book.runner_eod += 1

    return {
        "trade_id": t.trade_id,
        "variant": book.name,
        "session": t.session.isoformat(),
        "direction": t.direction,
        "r": t.r,
        "entry_ts": first_entry_ts,
        "entry_px": first_entry_px,
        "stop0": stop0,
        "peak_qty": peak_qty,
        "scaled": scaled,
        "runner_outcome": runner_outcome,
        "exit_bits": "|".join(exit_bits),
        "last_exit_ts": last_exit_ts,
        "pnl_usd": round(pnl, 2),
        "risk_usd": round(risk, 2),
    }


def autopsy_full_stops(baseline_recs: List[Dict], fades: Dict[str, Trade], gby) -> pd.DataFrame:
    rows = []
    for rec in baseline_recs:
        if rec["runner_outcome"] != "full_stop":
            continue
        t = fades[rec["trade_id"]]
        after = rth(gby[t.session])
        after = after[after.index > pd.Timestamp(rec["last_exit_ts"])]
        short = t.direction == "Short"
        _, _, scale_tp, runner_tp = geometry(t)
        hit_scale = hit_runner = hit_inval = False
        # invalidation = original break 1R
        inval = t.or_high + t.r if t.break_side == "up" else t.or_low - t.r
        for _, row in after.iterrows():
            if short:
                if row["low"] <= scale_tp:
                    hit_scale = True
                if row["low"] <= runner_tp:
                    hit_runner = True
                if row["high"] >= inval:
                    hit_inval = True
                    break
                if hit_scale:
                    break
            else:
                if row["high"] >= scale_tp:
                    hit_scale = True
                if row["high"] >= runner_tp:
                    hit_runner = True
                if row["low"] <= inval:
                    hit_inval = True
                    break
                if hit_scale:
                    break
        if hit_scale and hit_inval:
            cls = "same_bar_both"
        elif hit_scale:
            cls = "shakeout_would_reach_opp_OR"
        elif hit_inval:
            cls = "invalidation_continuation"
        else:
            cls = "chop_neither"
        rows.append(
            {
                "trade_id": rec["trade_id"],
                "session": rec["session"],
                "pnl_usd": rec["pnl_usd"],
                "cause": cls,
                "would_hit_opp_1r": hit_runner,
            }
        )
    return pd.DataFrame(rows)


def passes_filter(t: Trade, kind: str) -> bool:
    if kind == "none":
        return True
    wick = abs(t.failed_extreme - (t.or_high if t.break_side == "up" else t.or_low))
    if kind == "wick_ge_0.25R":
        return wick >= 0.25 * t.r
    if kind == "wick_ge_0.5R":
        return wick >= 0.5 * t.r
    if kind == "break_before_1000":
        return t.break_ts is not None and pd.Timestamp(t.break_ts).time() < time(10, 0)
    if kind == "wick_ge_0.25R_and_before_1000":
        return wick >= 0.25 * t.r and t.break_ts is not None and pd.Timestamp(t.break_ts).time() < time(10, 0)
    return True


def yearly_summary(tdf: pd.DataFrame, variant: str) -> pd.DataFrame:
    sub = tdf[tdf["variant"] == variant].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["year"] = pd.to_datetime(sub["entry_ts"], utc=True).dt.year
    g = sub.groupby("year").agg(net=("pnl_usd", "sum"), n=("pnl_usd", "count"), wins=("pnl_usd", lambda s: int((s >= 0).sum())))
    g["win_pct"] = (100.0 * g["wins"] / g["n"]).round(1)
    return g.reset_index()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gby = load_gby()
    cfg = MARKETS["nq"]
    regime = set(_regime_dates(cfg, gby))
    fades_list = scan_close5_fades(gby, regime)
    fades = {t.trade_id: t for t in fades_list}
    print("signals:", len(fades_list), flush=True)

    # ---- baseline for MAE + autopsy
    base = Book("baseline_R5")
    base_recs: List[Dict] = []
    for t in fades_list:
        rec = simulate(base, t, gby[t.session])
        if rec:
            base_recs.append(rec)
    print("baseline:", base.row(), flush=True)

    # winner MAE
    maes = []
    for rec in base_recs:
        if rec["pnl_usd"] < 0:
            continue
        t = fades[rec["trade_id"]]
        bars = rth(gby[t.session])
        bars = bars[(bars.index > pd.Timestamp(rec["entry_ts"])) & (bars.index <= pd.Timestamp(rec["last_exit_ts"]))]
        if bars.empty:
            continue
        short = t.direction == "Short"
        if short:
            mae = max(0.0, float(bars["high"].max()) - float(rec["entry_px"]))
        else:
            mae = max(0.0, float(rec["entry_px"]) - float(bars["low"].min()))
        maes.append(mae)
    mae_mean = float(pd.Series(maes).mean()) if maes else 0.0
    mae_med = float(pd.Series(maes).median()) if maes else 0.0
    print("winner MAE pts: mean=%.3f median=%.3f n=%d" % (mae_mean, mae_med, len(maes)), flush=True)

    # ---- autopsy
    adf = autopsy_full_stops(base_recs, fades, gby)
    adf.to_csv(OUT / "turtle_soup_stopout_autopsy.csv", index=False)
    cause = adf["cause"].value_counts()
    print("stop-out autopsy:\n", cause, flush=True)
    print("of shakeouts, would also hit opp 1R:", int(adf[adf.cause.str.startswith("shakeout")].would_hit_opp_1r.sum()), "/", int((adf.cause.str.startswith("shakeout")).sum()), flush=True)

    # ---- lever grid
    books: Dict[str, Book] = {}
    all_recs: List[Dict] = []

    def run(name: str, universe: Sequence[Trade], **kw):
        b = books.setdefault(name, Book(name))
        for t in universe:
            rec = simulate(b, t, gby[t.session], **kw)
            if rec:
                all_recs.append(rec)

    # stop fraction / floor
    for frac, label in [(0.25, "R4"), (0.2, "R5"), (0.167, "R6"), (0.125, "R8")]:
        run("stop_%s" % label, fades_list, frac=frac, floor_ticks=1)
    for ft in [2, 4, 6, 8]:
        run("floor_%dticks_R5" % ft, fades_list, frac=0.2, floor_ticks=ft)
    # entry buffer
    for bt in [1, 2, 4]:
        run("buf_%dticks_R5" % bt, fades_list, frac=0.2, floor_ticks=1, entry_buffer_ticks=bt)
    run("buf_2_floor4", fades_list, frac=0.2, floor_ticks=4, entry_buffer_ticks=2)
    # filters on baseline geometry
    for fk in ["wick_ge_0.25R", "wick_ge_0.5R", "break_before_1000", "wick_ge_0.25R_and_before_1000"]:
        uni = [t for t in fades_list if passes_filter(t, fk)]
        run("filt_%s" % fk, uni, frac=0.2, floor_ticks=1)
    # scale-in
    run("scalein_mae_mean", fades_list, frac=0.2, floor_ticks=1, scale_in_width=mae_mean, max_qty=5)
    run("scalein_mae_median", fades_list, frac=0.2, floor_ticks=1, scale_in_width=mae_med, max_qty=5)
    run("scalein_mae_mean_floor4", fades_list, frac=0.2, floor_ticks=4, scale_in_width=mae_mean, max_qty=5)
    # combo: best-looking filter + floor + scale-in (picked after we see table — also run a priori candidates)
    uni25 = [t for t in fades_list if passes_filter(t, "wick_ge_0.25R")]
    run("combo_wick25_floor4_scalein", uni25, frac=0.2, floor_ticks=4, scale_in_width=mae_mean, max_qty=5)
    run("combo_wick25_floor4", uni25, frac=0.2, floor_ticks=4)

    vdf = pd.DataFrame([b.row() for b in books.values()])
    # win pct
    tdf = pd.DataFrame(all_recs)
    winpct = tdf.groupby("variant").apply(lambda s: round(100.0 * (s.pnl_usd >= 0).mean(), 1))
    vdf["win_pct"] = vdf["variant"].map(winpct)
    # neg years
    neg_years = {}
    for v in vdf["variant"]:
        y = yearly_summary(tdf, v)
        neg_years[v] = int((y["net"] < 0).sum()) if len(y) else ""
    vdf["neg_years"] = vdf["variant"].map(neg_years)
    vdf["n_years"] = vdf["variant"].map(lambda v: len(yearly_summary(tdf, v)))
    vdf.to_csv(OUT / "turtle_soup_levers_stats.csv", index=False)
    tdf.to_csv(OUT / "turtle_soup_levers_trades.csv", index=False)

    # yearly for top variants
    for v in ["stop_R5", "floor_4ticks_R5", "scalein_mae_mean", "combo_wick25_floor4", "combo_wick25_floor4_scalein"]:
        y = yearly_summary(tdf, v)
        if len(y):
            y.to_csv(OUT / ("turtle_soup_levers_yearly_%s.csv" % v), index=False)

    # markdown
    md = [
        "# Turtle soup levers + stop-out autopsy + scale-in",
        "",
        "## Winner MAE (baseline R/5 book, used for scale-in width)",
        "",
        "- mean MAE of winners: **%.2f pts** (n=%d)" % (mae_mean, len(maes)),
        "- median MAE of winners: **%.2f pts**" % mae_med,
        "- baseline avg stop distance: ~R/5 (mean risk on fills in baseline study ~4.3 pts)",
        "",
        "## Stop-out autopsy (baseline full stops — could they have won?)",
        "",
        "After the full stop was hit, first subsequent touch:",
        "",
        "| Cause | N | % |",
        "|---|---:|---:|",
    ]
    n = len(adf)
    for c, k in cause.items():
        md.append("| %s | %d | %.1f |" % (c, k, 100.0 * k / n))
    shake = adf[adf["cause"].str.startswith("shakeout")]
    md.append("")
    md.append(
        "Of shakeouts that would reach opp OR: %d; of those also hit opp 1R: %d."
        % (len(shake), int(shake["would_hit_opp_1r"].sum()))
    )
    md.append("")
    md.append("## Lever grid (all BE-after-scale, runner opp 1R)")
    md.append("")
    cols = [
        "variant", "sessions", "fills", "fill_rate_pct", "avg_filled_qty", "full_stop",
        "scaled_4", "scale_rate_pct", "win_pct", "net_usd", "usd_per_fill", "profit_factor",
        "avg_risk_usd", "neg_years", "n_years",
    ]
    md.append("| " + " | ".join(cols) + " |")
    md.append("|" + "---|" * len(cols))
    for _, r in vdf.sort_values("net_usd", ascending=False).iterrows():
        md.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    (OUT / "TURTLE_SOUP_LEVERS_SUMMARY.md").write_text("\n".join(md))
    print(vdf.sort_values("net_usd", ascending=False).to_string(index=False), flush=True)
    print("-> %s" % (OUT / "TURTLE_SOUP_LEVERS_SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
