"""Path diagnostic: 2c half+open @ $2k risk + reverse after full initial stop.

Primary (same as r1000 family, risk=$2000 → 50 pts):
  - 2 @ p_liq; 1@half, 1@open; SL = stop_pts

Reverse (only if ``stop_full`` — both contracts stopped before any half fill):
  - Limit in opposite direction at the stop price
  - Target distance = |primary_entry − month_open|
  - Reverse SL = same stop_pts beyond reverse entry
  - Qty = 2

Hub: ``…/liq_run_fade_2c_half_open_r2000_reverse_path/``
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    FEATURES_CSV,
    LiquidityRun,
    _ny_ts,
    detect_liquidity_run,
    select_months,
)
from .monthly_open_liq_run_fade_2c_half_open_r1000 import (
    FEE,
    PV,
    QTY,
    QTY_HALF,
    QTY_OPEN,
    TICK,
    _leg_pnl,
    _progress,
    _score,
    _slip,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_2c_half_open_r2000_reverse_path"
)
NY = "America/New_York"
RISK_USD = 2000.0
STOP_PTS = RISK_USD / (QTY * PV)  # 50.0
DSR = "TRL-2026-00148"


@dataclass
class LegTrade:
    year: int
    month: int
    leg: str  # primary | reverse
    side: str
    month_open: float
    entry: float
    stop: float
    target: float
    target_half: float
    stop_pts: float
    open_dist: float
    entry_ts: str
    exit_ts: str
    exit_reason: str
    pnl_usd: float
    tp_half: int
    tp_open: int
    universe: str
    triggered_reverse: int = 0


def _simulate_reverse(
    *,
    bars: pd.DataFrame,
    start_ts,
    t1: pd.Timestamp,
    primary_side: str,
    primary_entry: float,
    month_open: float,
    stop_lvl: float,
    stop_pts: float,
    year: int,
    month: int,
    universe: str,
) -> Optional[LegTrade]:
    """Limit reverse at stop_lvl; target |entry−open|; SL = stop_pts."""
    rev_side = "short" if primary_side == "long" else "long"
    open_dist = abs(float(primary_entry) - float(month_open))
    if open_dist <= 0:
        return None
    entry_lvl = float(stop_lvl)
    if rev_side == "short":
        target = entry_lvl - open_dist
        stop = entry_lvl + stop_pts
    else:
        target = entry_lvl + open_dist
        stop = entry_lvl - stop_pts

    after = bars[(bars.index > pd.Timestamp(start_ts)) & (bars.index < t1)]
    if after.empty:
        return None

    filled = False
    fill_px = entry_lvl
    fill_ts = None
    pnl = 0.0

    for ts, row in after.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        if not filled:
            tagged = (rev_side == "short" and hi >= entry_lvl) or (
                rev_side == "long" and lo <= entry_lvl
            )
            # Also fill if price already through (marketable limit after stop)
            if rev_side == "short" and lo <= entry_lvl <= hi:
                tagged = True
            if rev_side == "long" and lo <= entry_lvl <= hi:
                tagged = True
            if rev_side == "short" and hi < entry_lvl:
                # already below sell limit → marketable
                tagged = True
            if rev_side == "long" and lo > entry_lvl:
                tagged = True
            if not tagged:
                continue
            filled = True
            fill_px = _slip(rev_side, entry_lvl, is_entry=True)
            fill_ts = ts
            pnl -= FEE * QTY
            if rev_side == "short":
                target = fill_px - open_dist
                stop = fill_px + stop_pts
            else:
                target = fill_px + open_dist
                stop = fill_px - stop_pts

        assert filled
        hit_stop = (hi >= stop) if rev_side == "short" else (lo <= stop)
        hit_tgt = (lo <= target) if rev_side == "short" else (hi >= target)
        if hit_stop and hit_tgt:
            # stop before target same-bar
            exit_px = _slip(rev_side, stop, is_entry=False)
            pnl += _leg_pnl(rev_side, fill_px, exit_px, QTY)
            return LegTrade(
                year=year,
                month=month,
                leg="reverse",
                side=rev_side,
                month_open=month_open,
                entry=fill_px,
                stop=stop,
                target=target,
                target_half=target,
                stop_pts=stop_pts,
                open_dist=open_dist,
                entry_ts=str(fill_ts),
                exit_ts=str(ts),
                exit_reason="rev_stop",
                pnl_usd=pnl,
                tp_half=0,
                tp_open=0,
                universe=universe,
            )
        if hit_stop:
            exit_px = _slip(rev_side, stop, is_entry=False)
            pnl += _leg_pnl(rev_side, fill_px, exit_px, QTY)
            return LegTrade(
                year=year,
                month=month,
                leg="reverse",
                side=rev_side,
                month_open=month_open,
                entry=fill_px,
                stop=stop,
                target=target,
                target_half=target,
                stop_pts=stop_pts,
                open_dist=open_dist,
                entry_ts=str(fill_ts),
                exit_ts=str(ts),
                exit_reason="rev_stop",
                pnl_usd=pnl,
                tp_half=0,
                tp_open=0,
                universe=universe,
            )
        if hit_tgt:
            exit_px = _slip(rev_side, target, is_entry=False)
            pnl += _leg_pnl(rev_side, fill_px, exit_px, QTY)
            return LegTrade(
                year=year,
                month=month,
                leg="reverse",
                side=rev_side,
                month_open=month_open,
                entry=fill_px,
                stop=stop,
                target=target,
                target_half=target,
                stop_pts=stop_pts,
                open_dist=open_dist,
                entry_ts=str(fill_ts),
                exit_ts=str(ts),
                exit_reason="rev_target",
                pnl_usd=pnl,
                tp_half=0,
                tp_open=1,
                universe=universe,
            )

    if not filled:
        return LegTrade(
            year=year,
            month=month,
            leg="reverse",
            side=rev_side,
            month_open=month_open,
            entry=entry_lvl,
            stop=stop,
            target=target,
            target_half=target,
            stop_pts=stop_pts,
            open_dist=open_dist,
            entry_ts="",
            exit_ts="",
            exit_reason="rev_no_fill",
            pnl_usd=0.0,
            tp_half=0,
            tp_open=0,
            universe=universe,
        )

    last = after.iloc[-1]
    exit_px = _slip(rev_side, float(last["close"]), is_entry=False)
    pnl += _leg_pnl(rev_side, fill_px, exit_px, QTY)
    return LegTrade(
        year=year,
        month=month,
        leg="reverse",
        side=rev_side,
        month_open=month_open,
        entry=fill_px,
        stop=stop,
        target=target,
        target_half=target,
        stop_pts=stop_pts,
        open_dist=open_dist,
        entry_ts=str(fill_ts),
        exit_ts=str(after.index[-1]),
        exit_reason="rev_eom",
        pnl_usd=pnl,
        tp_half=0,
        tp_open=0,
        universe=universe,
    )


def simulate_primary_then_reverse(
    *,
    bars: pd.DataFrame,
    liq: LiquidityRun,
    t1: pd.Timestamp,
    universe: str,
    stop_pts: float = STOP_PTS,
) -> List[LegTrade]:
    month_open = float(liq.month_open)
    p_liq = float(liq.p_liq)
    stop_pts = float(stop_pts)
    if liq.side == "up":
        side = "short"
        entry_lvl = p_liq
        stop = p_liq + stop_pts
        target_half = 0.5 * (p_liq + month_open)
        target_open = month_open
    else:
        side = "long"
        entry_lvl = p_liq
        stop = p_liq - stop_pts
        target_half = 0.5 * (p_liq + month_open)
        target_open = month_open

    after = bars[(bars.index > pd.Timestamp(liq.t_liq)) & (bars.index < t1)]
    open_dist = abs(entry_lvl - month_open)
    out: List[LegTrade] = []
    if after.empty:
        return out

    filled = False
    fill_px = entry_lvl
    fill_ts = None
    rem = QTY
    half_done = False
    open_done = False
    pnl = 0.0

    def hit_stop(hi, lo):
        return (hi >= stop) if side == "short" else (lo <= stop)

    def hit_half(hi, lo):
        return (lo <= target_half) if side == "short" else (hi >= target_half)

    def hit_open(hi, lo):
        return (lo <= target_open) if side == "short" else (hi >= target_open)

    def pack_primary(ts, reason, exit_px, triggered=0):
        return LegTrade(
            year=liq.year,
            month=liq.month,
            leg="primary",
            side=side,
            month_open=month_open,
            entry=fill_px,
            stop=stop,
            target=target_open,
            target_half=target_half,
            stop_pts=stop_pts,
            open_dist=abs(fill_px - month_open),
            entry_ts=str(fill_ts),
            exit_ts=str(ts),
            exit_reason=reason,
            pnl_usd=pnl,
            tp_half=int(half_done),
            tp_open=int(open_done),
            universe=universe,
            triggered_reverse=triggered,
        )

    for ts, row in after.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        if not filled:
            tagged = (side == "short" and hi >= entry_lvl) or (side == "long" and lo <= entry_lvl)
            if not tagged:
                continue
            filled = True
            fill_px = _slip(side, entry_lvl, is_entry=True)
            fill_ts = ts
            pnl -= FEE * QTY
            if side == "short":
                stop = fill_px + stop_pts
                target_half = 0.5 * (fill_px + month_open)
            else:
                stop = fill_px - stop_pts
                target_half = 0.5 * (fill_px + month_open)
            target_open = month_open

        if hit_stop(hi, lo):
            exit_px = _slip(side, stop, is_entry=False)
            pnl += _leg_pnl(side, fill_px, exit_px, rem)
            reason = "stop_full" if not half_done else ("stop_after_half" if not open_done else "stop")
            trig = 1 if reason == "stop_full" else 0
            out.append(pack_primary(ts, reason, exit_px, triggered=trig))
            if reason == "stop_full":
                rev = _simulate_reverse(
                    bars=bars,
                    start_ts=ts,
                    t1=t1,
                    primary_side=side,
                    primary_entry=fill_px,
                    month_open=month_open,
                    stop_lvl=stop,
                    stop_pts=stop_pts,
                    year=liq.year,
                    month=liq.month,
                    universe=universe,
                )
                if rev is not None:
                    out.append(rev)
            return out

        if not half_done and hit_half(hi, lo):
            exit_px = _slip(side, target_half, is_entry=False)
            pnl += _leg_pnl(side, fill_px, exit_px, QTY_HALF)
            rem -= QTY_HALF
            half_done = True
            if rem <= 0:
                out.append(pack_primary(ts, "half_only", exit_px))
                return out
            if hit_open(hi, lo):
                exit_px2 = _slip(side, target_open, is_entry=False)
                pnl += _leg_pnl(side, fill_px, exit_px2, rem)
                open_done = True
                rem = 0
                out.append(pack_primary(ts, "half_open", exit_px2))
                return out
            continue

        if half_done and not open_done and hit_open(hi, lo):
            exit_px = _slip(side, target_open, is_entry=False)
            pnl += _leg_pnl(side, fill_px, exit_px, rem)
            open_done = True
            rem = 0
            out.append(pack_primary(ts, "half_open", exit_px))
            return out

    if not filled:
        return out
    last = after.iloc[-1]
    exit_px = _slip(side, float(last["close"]), is_entry=False)
    pnl += _leg_pnl(side, fill_px, exit_px, rem)
    reason = "eom_after_half" if half_done else "eom_flat"
    out.append(pack_primary(after.index[-1], reason, exit_px))
    return out


def _score_legs(legs: Sequence[LegTrade], *, leg: Optional[str] = None) -> Dict[str, float]:
    rows = [t for t in legs if t.exit_reason not in {"", "rev_no_fill"} and "no_fill" not in t.exit_reason]
    if leg:
        rows = [t for t in rows if t.leg == leg]
    # treat rev_no_fill as zero / skip
    rows = [t for t in rows if t.exit_reason != "rev_no_fill"]
    if not rows:
        return {
            "n": 0.0,
            "net_usd": 0.0,
            "stress": 0.0,
            "ns": 0.0,
            "wr": 0.0,
            "n_rev_target": 0.0,
            "n_rev_stop": 0.0,
            "n_stop_full": 0.0,
        }
    nets = np.array([t.pnl_usd for t in rows], dtype=float)
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    dd = float((eq - peak).min())
    stress = abs(dd)
    net = float(nets.sum())
    return {
        "n": float(len(rows)),
        "net_usd": net,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else 0.0,
        "wr": float((nets > 0).sum()) / len(rows),
        "n_rev_target": float(sum(1 for t in rows if t.exit_reason == "rev_target")),
        "n_rev_stop": float(sum(1 for t in rows if t.exit_reason == "rev_stop")),
        "n_stop_full": float(sum(1 for t in rows if t.exit_reason == "stop_full")),
        "avg_usd": float(nets.mean()),
    }


def run(*, output_root: Path, email: bool = False) -> int:
    if output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    # DSR before peek
    dsr_path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    if dsr_path.exists():
        with dsr_path.open("a", encoding="utf-8") as fh:
            fh.write(
                "%s,2026-08-26,cursor,PATH_SIM,nq_liq_2c_half_open_r2000_reverse,,True,NQ,"
                "2010-06-06,2026-06-16,FULL_SAMPLE,False,,,\"{\\\"risk_usd\\\":2000,\\\"reverse_after\\\":\\\"stop_full\\\",\\\"rev_target\\\":\\\"abs(entry-open)\\\"}\","
                "%s/,1,,,,,,,,,,,TRUE,False,1.00,,RUNNING,,,\"2c half+open $2k; reverse after full stop only; path before 1m broker.\",False\n"
                % (DSR, output_root.relative_to(REPO))
            )

    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)

    win_by = {}
    month_opens = {}
    all_keys = []
    for year, month, m0, m1 in month_windows(bars, None, None):
        key = (int(year), int(month))
        win_by[key] = (m0, m1)
        all_keys.append(key)
        seg = bars_ny[(bars_ny.index >= _ny_ts(m0)) & (bars_ny.index < _ny_ts(m1))]
        if not seg.empty:
            month_opens[key] = float(seg["open"].iloc[0])

    feats = pd.read_csv(FEATURES_CSV)
    feats = feats[feats["market"].astype(str).str.upper() == "NQ"]
    sel = select_months(feats)
    hp_keys = [(int(r.year), int(r.month)) for r in sel.itertuples(index=False)]
    for r in sel.itertuples(index=False):
        month_opens[(int(r.year), int(r.month))] = float(r.month_open)

    _progress(output_root, "RUN risk=$%.0f stop_pts=%.1f reverse_after=stop_full" % (RISK_USD, STOP_PTS))

    def collect(keys, universe):
        legs = []
        for year, month in keys:
            if (year, month) not in win_by:
                continue
            t0, t1 = win_by[(year, month)]
            t0n, t1n = _ny_ts(t0), _ny_ts(t1)
            mo = month_opens.get((year, month))
            if mo is None:
                continue
            liq = detect_liquidity_run(
                bars_1h=bars_ny,
                year=year,
                month=month,
                month_open=float(mo),
                t0=t0n,
                t1=t1n,
            )
            if liq is None:
                continue
            legs.extend(
                simulate_primary_then_reverse(
                    bars=bars_ny, liq=liq, t1=t1n, universe=universe, stop_pts=STOP_PTS
                )
            )
        return legs

    all_legs = collect(all_keys, "all")
    hp_legs = collect(hp_keys, "hp")
    pd.DataFrame([asdict(t) for t in all_legs]).to_csv(output_root / "legs_all.csv", index=False)
    pd.DataFrame([asdict(t) for t in hp_legs]).to_csv(output_root / "legs_hp.csv", index=False)

    scores = {}
    for label, legs in (("all", all_legs), ("hp", hp_legs)):
        scores["%s_primary" % label] = _score_legs(legs, leg="primary")
        scores["%s_reverse" % label] = _score_legs(legs, leg="reverse")
        scores["%s_combined" % label] = _score_legs(legs, leg=None)

    (output_root / "metrics.json").write_text(json.dumps(scores, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def row(name, s):
        return "| %s | %d | %.0f%% | %+.0f | %.0f | %.2f | %d | %d | %d |" % (
            name,
            int(s.get("n") or 0),
            100 * float(s.get("wr") or 0),
            float(s.get("net_usd") or 0),
            float(s.get("stress") or 0),
            float(s.get("ns") or 0),
            int(s.get("n_stop_full") or 0),
            int(s.get("n_rev_target") or 0),
            int(s.get("n_rev_stop") or 0),
        )

    lines = [
        "# NQ 2c half+open $2k + reverse after full stop (1h path)",
        "",
        "- Primary: 2 @ p_liq; 1@half 1@open; SL = **50 pts** ($2000 / 2 / $20)",
        "- Reverse **only** after ``stop_full`` (no half fill yet)",
        "- Reverse: limit opposite @ stop; target = **|entry − open|**; SL = 50 pts; qty 2",
        "",
        "| Book | N | WR | Net $ | Stress $ | N/S | stop_full | rev_tgt | rev_stop |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        row("hp primary", scores["hp_primary"]),
        row("hp reverse", scores["hp_reverse"]),
        row("hp combined", scores["hp_combined"]),
        row("all primary", scores["all_primary"]),
        row("all reverse", scores["all_reverse"]),
        row("all combined", scores["all_combined"]),
        "",
        "Hub: `%s`" % output_root,
        "",
    ]
    hp_rev = scores["hp_reverse"]
    hp_pri = scores["hp_primary"]
    hp_comb = scores["hp_combined"]
    if float(hp_rev.get("net_usd") or 0) > 0 and float(hp_comb.get("ns") or 0) >= float(hp_pri.get("ns") or 0):
        stance = "reverse **helps** on path HP — proceed to 1m broker with reverse on."
    elif float(hp_rev.get("net_usd") or 0) > 0:
        stance = "reverse positive but combined N/S not clearly better — still try 1m broker."
    else:
        stance = "reverse **not worth it** on path HP — 1m broker primary-only (or reverse off)."
    lines.append("Stance: %s" % stance)
    summary = "\n".join(lines) + "\n"
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "scores": scores, "stance": stance}, indent=2) + "\n", encoding="utf-8"
    )
    _progress(output_root, "DONE %s" % json.dumps({k: scores[k].get("net_usd") for k in scores}))

    for key, s in scores.items():
        log_run(
            run_class="pandas",
            variant_slug="nq_liq_2c_half_open_r2000_rev_%s" % key,
            instrument="NQ",
            hub_path=str(output_root.relative_to(REPO)),
            net_usd=float(s.get("net_usd") or 0),
            stress_dd_usd=-float(s.get("stress") or 0),
            ns=float(s.get("ns") or 0),
            trades=int(s.get("n") or 0),
            dsr_trial_id=DSR,
            meta={"risk_usd": RISK_USD, "book": key},
            notes="path 2c $2k reverse-after-full-stop",
        )
    if email:
        send_email(subject="potions: NQ 2c $2k reverse-after-full-stop path", body=summary)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        return run(output_root=args.output_root, email=args.email)
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: 2c reverse path FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
