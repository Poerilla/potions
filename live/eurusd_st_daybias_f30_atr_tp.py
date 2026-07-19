"""f30-week day-bias DCA: ATR take-profit sweep (pandas) + failure-mode note.

Compares baseline (SL / week-end only) vs TP at k × hourly ATR(14) from avg entry.
Also reports whether ATR TP would have rescued broker early-stops.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .eurusd_hourly_st_daybias_dca import (
    ADD_QTY,
    BIAS_THRESH,
    FEE,
    HALF_SPREAD,
    MAX_ADDS,
    NY,
    POINT_VALUE,
    _month_key,
    _ny_date,
    _period_end_day,
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
OUT = REPO / "live" / "state" / "eurusd_st_daybias_f30_atr_tp"
FRAC = 0.30
PERIOD = "week"


@dataclass
class Lot:
    side: str
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    qty: float
    tp: Optional[float] = None


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


def _atr_asof(atr: pd.Series, ts: pd.Timestamp) -> Optional[float]:
    v = atr.asof(ts)
    if pd.isna(v) or float(v) <= 0:
        return None
    return float(v)


def run_variant(
    day_df: pd.DataFrame,
    by_day: Dict[date, pd.DataFrame],
    atr: pd.Series,
    *,
    tp_atr_mult: Optional[float],
    name: str,
) -> Tuple[List[ClosedTrade], dict]:
    trades: List[ClosedTrade] = []
    camp: Optional[Campaign] = None
    month_entry_count: Dict[str, int] = {}
    touch_days = 0
    n_tp = 0
    n_stop = 0
    n_period = 0

    dates = [d for d in day_df["date"].tolist()]
    prev_map = {day_df.iloc[i]["date"]: day_df.iloc[i - 1] for i in range(1, len(day_df))}

    def flatten(exit_ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal camp, n_tp, n_stop, n_period
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
        if reason == "tp":
            n_tp += 1
        elif reason == "stop":
            n_stop += 1
        elif reason == "period_end":
            n_period += 1
        camp = None

    def camp_tp() -> Optional[float]:
        if camp is None or not camp.lots:
            return None
        # Campaign TP from average entry using first lot's ATR-based tp distance
        # (each lot stores absolute tp; use nearest TP among lots — first hit)
        tps = [l.tp for l in camp.lots if l.tp is not None]
        if not tps:
            return None
        if camp.side == "long":
            return min(tps)  # first TP hit going up
        return max(tps)

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
        hi, lo = float(prev["high"]), float(prev["low"])
        if hi <= lo:
            continue
        mkey = _month_key(d)
        month_used = month_entry_count.get(mkey, 0)

        idx = bars.index
        hi_a = bars["high"].to_numpy(dtype=float)
        lo_a = bars["low"].to_numpy(dtype=float)
        cl_a = bars["close"].to_numpy(dtype=float)
        n_bars = len(hi_a)
        is_period_end_day = d.weekday() == 4
        can_enter = (
            bias is not None
            and month_used < MAX_ADDS
            and (
                camp is None
                or (d not in camp.entry_days and camp.side == bias and len(camp.lots) < MAX_ADDS)
            )
        )
        lvl = entry_level(bias, hi, lo, FRAC) if bias in {"long", "short"} else None
        stop_lvl = lo if bias == "long" else hi if bias == "short" else None

        for i in range(n_bars):
            hi_b, lo_b = hi_a[i], lo_a[i]
            if camp is not None and camp.lots:
                # Stop first (pessimistic vs TP on same bar)
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
                    can_enter = False
                    continue

                tp = camp_tp()
                if tp is not None:
                    hit_tp = (camp.side == "long" and hi_b >= tp) or (
                        camp.side == "short" and lo_b <= tp
                    )
                    if hit_tp:
                        px = tp - HALF_SPREAD if camp.side == "long" else tp + HALF_SPREAD
                        flatten(pd.Timestamp(idx[i]), px, "tp")
                        can_enter = False
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

            ts = pd.Timestamp(idx[i])
            a = _atr_asof(atr, ts)
            tp_px = None
            if tp_atr_mult is not None and a is not None:
                if bias == "long":
                    tp_px = entry + tp_atr_mult * a
                else:
                    tp_px = entry - tp_atr_mult * a

            if camp is None:
                camp = Campaign(side=bias, period_key=pkey)
            camp.lots.append(Lot(bias, ts, entry, stop_lvl, ADD_QTY, tp_px))
            camp.entry_days.append(d)
            month_entry_count[mkey] = month_used + 1
            month_used += 1
            touch_days += 1
            can_enter = False
            # Keep walking bars so same-day stop/TP can fire (prior bug: break skipped them).
            continue

    if camp is not None and camp.lots:
        last_d = dates[-1]
        last_bars = by_day.get(last_d)
        if last_bars is not None and not last_bars.empty:
            px = float(last_bars.iloc[-1]["close"])
            px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
            flatten(pd.Timestamp(last_bars.index[-1]), px, "eod_mark")

    usd = np.array([t.usd for t in trades], dtype=float) if trades else np.array([])
    if len(usd):
        eq = np.cumsum(usd)
        dd = float((eq - np.maximum.accumulate(eq)).min())
        net = float(usd.sum())
    else:
        dd, net = 0.0, 0.0
    stats = {
        "strategy": name,
        "tp_atr_mult": tp_atr_mult if tp_atr_mult is not None else 0.0,
        "campaigns": len(trades),
        "lots": float(sum(t.qty for t in trades)),
        "net_usd": round(net, 2),
        "closed_dd_usd": round(dd, 2),
        "net_over_closed_dd": round(net / abs(dd), 3) if dd else 0.0,
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2) if len(usd) else 0.0,
        "avg_usd": round(net / len(trades), 2) if trades else 0.0,
        "n_tp": n_tp,
        "n_stop": n_stop,
        "n_period_end": n_period,
        "entry_days": touch_days,
        "median_hold_h": round(
            float(np.median([(t.exit_ts - t.entry_ts).total_seconds() / 3600 for t in trades])),
            2,
        )
        if trades
        else 0.0,
    }
    return trades, stats


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="f30 week ATR TP sweep")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--mults", default="0,1,2,3,4,5", help="0 = no TP baseline")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    mults = [float(x) for x in args.mults.split(",") if x.strip()]

    print("Loading...", flush=True)
    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    one_m = concat_all_1m(load_fx_1m_by_ny_date(one_m_path, "EURUSD")).sort_index()
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    hourly = resample_hourly(one_m)
    atr = _hourly_atr(hourly)
    hourly = compute_supertrend_fast(hourly, atr_len=14, multiplier=3.0)
    day_df, by_day = build_day_tables(hourly, one_m)
    print("  days=%d atr_median_pips=%.1f" % (len(day_df), float(atr.median()) * 1e4), flush=True)

    rows = []
    for m in mults:
        tp = None if m <= 0 else m
        name = "f30_week_no_tp" if tp is None else "f30_week_tp_%gatr" % m
        print("Running", name, "...", flush=True)
        trades, stats = run_variant(day_df, by_day, atr, tp_atr_mult=tp, name=name)
        rows.append(stats)
        print(
            "  net=$%s dd=$%s Net/DD=%.2f WR=%.1f%% hold=%.1fh tp/stop/pe=%d/%d/%d"
            % (
                f"{stats['net_usd']:,.0f}",
                f"{stats['closed_dd_usd']:,.0f}",
                stats["net_over_closed_dd"],
                stats["win_rate_pct"],
                stats["median_hold_h"],
                stats["n_tp"],
                stats["n_stop"],
                stats["n_period_end"],
            ),
            flush=True,
        )
        if tp == 3.0 and trades:
            pd.DataFrame([t.__dict__ for t in trades]).to_csv(out / "trades_tp_3atr.csv", index=False)

    summary = pd.DataFrame(rows).sort_values("net_usd", ascending=False)
    summary.to_csv(out / "leaderboard.csv", index=False)
    (out / "summary.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")

    # Failure-mode cross-check note (static from prior analysis + TP implication)
    lines = [
        "# f30 week — ATR take-profit sweep (pandas)",
        "",
        "Baseline hold = stop or Friday close. TP variants exit at **k × hourly ATR(14)**",
        "from each lot's entry (campaign exits when nearest lot TP is tagged; stop still",
        "pessimistic vs TP on the same bar).",
        "",
        f"Window {args.start} → {args.end}. Unit = half-lot (PV $50k), fee $0.75.",
        "",
        "## Broker vs pandas failure mode (why hold kills broker)",
        "",
        "Matched would-be winners (research period_end +, broker −):",
        "- **75%** are broker STOP while research PERIOD_END",
        "- Broker hold median **~1h** vs research **~74h** on those paths",
        "- MFE before broker stop: only **~0.65 ATR** — price never runs before the stop",
        "- Share that reach k×ATR *before* broker stop: 1× **29%**, 2× **12%**, 3× **7%**, 4× **2%**, 5× **0%**",
        "",
        "**Implication:** ATR TP does **not** fix the main broker failure mode. Those trades",
        "die at the prev-day extreme before a 1–3 ATR run develops. TP can still change the",
        "pandas book (bank winners earlier) but is unlikely to close the broker gap alone.",
        "",
        "## Pandas TP leaderboard",
        "",
        "| Strategy | TP | Net | Closed DD | Net/DD | WR | Med hold h | TP exits | Stop | Period |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        tp_s = "—" if r["tp_atr_mult"] == 0 else "%g×ATR" % r["tp_atr_mult"]
        lines.append(
            "| %s | %s | $%s | $%s | %.2f | %.1f%% | %.1f | %d | %d | %d |"
            % (
                r["strategy"],
                tp_s,
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_closed_dd"],
                r["win_rate_pct"],
                r["median_hold_h"],
                r["n_tp"],
                r["n_stop"],
                r["n_period_end"],
            )
        )
    lines.extend(["", "CSV: `leaderboard.csv`", ""])
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
