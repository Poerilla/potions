"""NQ protected-area approach trade — diagnostic 1m path replay.

Rules (user-specified trial):
  - After structure_complete_at, during RTH 09:30–16:00 NY only:
      * If price is above the protected area → arm BUY limit at area_high
        (approach from above).
      * If price is below the protected area → arm SELL limit at area_low
        (approach from below).
  - Size: 4 contracts.
  - Scale: exit 3 when those 3 are +$1000 combined (~16.6667 pts each).
  - Runner: 1 contract to +$2000 (~100 pts).
  - Stop: 1m candle *close* beyond the far side of the area (not wick).
  - One attempt per frozen candidate; arming window ends at seed_expiry.

Frozen events from seed-bias review / parent V1 ledgers. Not a promotion claim.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_protected_area_approach_trade_v1 --email
  python -m live.nq_protected_area_approach_trade_v1 --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

from .notify_email import send_email
from .nq_structure_change_event_study import TICK
from .nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1 import build_globex_1m
from .nq_wick_reject_range_seed_retest import _localize
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
LEDGER = (
    REPO
    / "live"
    / "state"
    / "nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1"
    / "unified_review_ledger.csv"
)
HUB = REPO / "live" / "state" / "nq_protected_area_approach_trade_v1"
STUDY_ID = "nq_protected_area_approach_trade_v1"
PARENT_HASH = "402795e0a05e2fbc"
DSR = "TRL-2026-00191"
NY = pytz.timezone("America/New_York")
POINT_VALUE = 20.0
FEE = 1.50
QTY = 4
SCALE_QTY = 3
RUNNER_QTY = 1
# $1000 on 3 contracts → pts each; $2000 on 1 contract
TP_SCALE_PTS = 1000.0 / (SCALE_QTY * POINT_VALUE)  # 16.666...
TP_RUNNER_PTS = 2000.0 / POINT_VALUE  # 100.0
ARM_START = time(9, 30)
ARM_END = time(16, 0)


def _progress(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "protected_area_approach_trade",
            "is_independent": "TRUE",
            "market": "NQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "qty": QTY,
                    "scale_qty": SCALE_QTY,
                    "scale_usd": 1000,
                    "runner_usd": 2000,
                    "sl": "close_beyond_far_area_edge",
                    "arm": "RTH_0930_1600",
                    "entry": "limit_approach_from_outside",
                    "parent_hash": PARENT_HASH,
                }
            ),
            "fixed_parameters_ref": "live/nq_protected_area_approach_trade_v1.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Approach-from-outside protected-area limit trial on frozen V1 candidates",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ","):
            for old in ("PENDING", "RUNNING", "COMPLETE", "FAILED"):
                tok = ",%s," % old
                if tok in ln:
                    ln = ln.replace(tok, ",%s," % status, 1)
                    break
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _area_bounds(row: pd.Series) -> Tuple[float, float]:
    lo = min(float(row["inner_area_edge"]), float(row["outer_area_edge"]))
    hi = max(float(row["inner_area_edge"]), float(row["outer_area_edge"]))
    return lo, hi


def _in_arm_window(ts: pd.Timestamp) -> bool:
    t = _localize(ts).timetz().replace(tzinfo=None) if False else _localize(ts).time()
    return ARM_START <= t < ARM_END


def _rth_day(ts: pd.Timestamp) -> date:
    return _localize(ts).date()


@dataclass
class Position:
    side: str  # long|short
    entry_ts: pd.Timestamp
    entry_px: float
    area_lo: float
    area_hi: float
    qty_left: int = QTY
    scale_done: bool = False
    runner_done: bool = False
    realized: float = 0.0
    exits: List[dict] = field(default_factory=list)
    mfe_pts: float = 0.0
    mae_pts: float = 0.0


def _pnl_pts(side: str, entry: float, exit_px: float) -> float:
    return (exit_px - entry) if side == "long" else (entry - exit_px)


def _add_exit(pos: Position, ts: pd.Timestamp, px: float, qty: int, reason: str) -> None:
    pts = _pnl_pts(pos.side, pos.entry_px, px)
    net = pts * POINT_VALUE * qty - FEE * qty
    pos.realized += net
    pos.qty_left -= qty
    pos.exits.append(
        {
            "exit_ts": ts.isoformat(),
            "exit_px": float(px),
            "qty": int(qty),
            "points": float(pts),
            "net_usd": float(net),
            "reason": reason,
        }
    )


def simulate_candidate(row: pd.Series, bars: pd.DataFrame) -> dict:
    cand_id = str(row["candidate_id"])
    if pd.notna(row.get("candidate_status")) and str(row["candidate_status"]) != "COMPLETED":
        return {"candidate_id": cand_id, "seed_id": row.get("seed_id", ""), "status": "SKIP_NO_CANDIDATE", "filled": False, "net_usd": 0.0}, []

    complete = _localize(pd.Timestamp(row["structure_complete_at"]))
    expiry = _localize(pd.Timestamp(row["seed_expiry"]))
    area_lo, area_hi = _area_bounds(row)
    # Manage from first bar strictly after structure complete through seed expiry + 1 day buffer
    end = max(expiry, complete) + timedelta(days=1)
    win = bars[(bars.index > complete) & (bars.index <= end)]
    if win.empty:
        return {
            "candidate_id": cand_id,
            "seed_id": row["seed_id"],
            "status": "NO_BARS",
            "filled": False,
            "net_usd": 0.0,
        }, []

    armed_side: Optional[str] = None  # buy|sell
    limit_px: Optional[float] = None
    pos: Optional[Position] = None
    status = "NO_FILL"

    for ts, bar in win.iterrows():
        ts = _localize(pd.Timestamp(ts))
        hi = float(bar["high"])
        lo = float(bar["low"])
        cl = float(bar["close"])

        # Manage open position
        if pos is not None:
            fav = _pnl_pts(pos.side, pos.entry_px, hi if pos.side == "long" else lo)
            adv = _pnl_pts(pos.side, pos.entry_px, lo if pos.side == "long" else hi)
            pos.mfe_pts = max(pos.mfe_pts, fav)
            pos.mae_pts = min(pos.mae_pts, adv)

            # Targets on path (intrabar); scale then runner
            if not pos.scale_done and pos.qty_left >= SCALE_QTY:
                tp = (
                    pos.entry_px + TP_SCALE_PTS
                    if pos.side == "long"
                    else pos.entry_px - TP_SCALE_PTS
                )
                hit = (pos.side == "long" and hi >= tp) or (pos.side == "short" and lo <= tp)
                if hit:
                    _add_exit(pos, ts, tp, SCALE_QTY, "tp_scale_1000usd")
                    pos.scale_done = True

            if pos.scale_done and not pos.runner_done and pos.qty_left >= RUNNER_QTY:
                tp = (
                    pos.entry_px + TP_RUNNER_PTS
                    if pos.side == "long"
                    else pos.entry_px - TP_RUNNER_PTS
                )
                hit = (pos.side == "long" and hi >= tp) or (pos.side == "short" and lo <= tp)
                if hit:
                    _add_exit(pos, ts, tp, pos.qty_left, "tp_runner_2000usd")
                    pos.runner_done = True

            # Close-based stop on remaining (after target checks)
            if pos.qty_left > 0:
                stopped = (pos.side == "long" and cl < area_lo) or (
                    pos.side == "short" and cl > area_hi
                )
                if stopped:
                    # Fill at close (close-through); no adverse tick added — close is the signal
                    _add_exit(pos, ts, cl, pos.qty_left, "sl_close_beyond_area")

            if pos.qty_left <= 0:
                status = "CLOSED"
                break
            continue

        # Flat: arming / fill logic
        if ts > expiry:
            status = "EXPIRED_NO_FILL"
            break

        if not _in_arm_window(ts):
            armed_side = None
            limit_px = None
            continue

        # Side of market relative to area (using prior close / this bar open proxy = previous close)
        # Use bar open as "where we are" before this minute's range for arming.
        op = float(bar["open"])
        if op > area_hi:
            armed_side = "buy"
            limit_px = area_hi
        elif op < area_lo:
            armed_side = "sell"
            limit_px = area_lo
        else:
            # Inside area — do not newly arm; cancel resting
            armed_side = None
            limit_px = None
            continue

        # Fill if this bar's range trades through the limit while approaching from outside
        if armed_side == "buy" and lo <= limit_px:
            # Must have been approaching from above: open was above area
            fill = float(limit_px)
            pos = Position(
                side="long",
                entry_ts=ts,
                entry_px=fill,
                area_lo=area_lo,
                area_hi=area_hi,
            )
            status = "OPEN"
            # same-bar manage: targets / stop after entry on this bar
            fav = _pnl_pts("long", fill, hi)
            adv = _pnl_pts("long", fill, lo)
            pos.mfe_pts = fav
            pos.mae_pts = adv
            if hi >= fill + TP_SCALE_PTS:
                _add_exit(pos, ts, fill + TP_SCALE_PTS, SCALE_QTY, "tp_scale_1000usd")
                pos.scale_done = True
            if pos.scale_done and pos.qty_left > 0 and hi >= fill + TP_RUNNER_PTS:
                _add_exit(pos, ts, fill + TP_RUNNER_PTS, pos.qty_left, "tp_runner_2000usd")
                pos.runner_done = True
            if pos.qty_left > 0 and cl < area_lo:
                _add_exit(pos, ts, cl, pos.qty_left, "sl_close_beyond_area")
            if pos.qty_left <= 0:
                status = "CLOSED"
                break
        elif armed_side == "sell" and hi >= limit_px:
            fill = float(limit_px)
            pos = Position(
                side="short",
                entry_ts=ts,
                entry_px=fill,
                area_lo=area_lo,
                area_hi=area_hi,
            )
            status = "OPEN"
            fav = _pnl_pts("short", fill, lo)
            adv = _pnl_pts("short", fill, hi)
            pos.mfe_pts = fav
            pos.mae_pts = adv
            if lo <= fill - TP_SCALE_PTS:
                _add_exit(pos, ts, fill - TP_SCALE_PTS, SCALE_QTY, "tp_scale_1000usd")
                pos.scale_done = True
            if pos.scale_done and pos.qty_left > 0 and lo <= fill - TP_RUNNER_PTS:
                _add_exit(pos, ts, fill - TP_RUNNER_PTS, pos.qty_left, "tp_runner_2000usd")
                pos.runner_done = True
            if pos.qty_left > 0 and cl > area_hi:
                _add_exit(pos, ts, cl, pos.qty_left, "sl_close_beyond_area")
            if pos.qty_left <= 0:
                status = "CLOSED"
                break

    # Flatten leftover at data end / expiry
    if pos is not None and pos.qty_left > 0:
        last_ts = _localize(pd.Timestamp(win.index[-1]))
        last_cl = float(win.iloc[-1]["close"])
        _add_exit(pos, last_ts, last_cl, pos.qty_left, "data_end_flatten")
        status = "FLATTENED"

    out = {
        "candidate_id": cand_id,
        "seed_id": row["seed_id"],
        "pattern": row.get("pattern", ""),
        "structure_bias": row.get("structure_bias", ""),
        "seed_bias": row.get("seed_bias", ""),
        "area_lo": area_lo,
        "area_hi": area_hi,
        "structure_complete_at": complete.isoformat(),
        "seed_expiry": expiry.isoformat(),
        "status": status if pos is not None else status,
        "filled": pos is not None,
        "side": pos.side if pos else "",
        "entry_ts": pos.entry_ts.isoformat() if pos else "",
        "entry_px": pos.entry_px if pos else np.nan,
        "net_usd": float(pos.realized) if pos else 0.0,
        "mfe_pts": float(pos.mfe_pts) if pos else np.nan,
        "mae_pts": float(pos.mae_pts) if pos else np.nan,
        "n_exits": len(pos.exits) if pos else 0,
        "exit_reasons": ",".join(sorted({e["reason"] for e in pos.exits})) if pos else "",
        "scale_hit": bool(pos.scale_done) if pos else False,
        "runner_hit": bool(pos.runner_done) if pos else False,
        "stopped": bool(pos and any(e["reason"] == "sl_close_beyond_area" for e in pos.exits)),
    }
    return out, (pos.exits if pos else [])


def run(*, email: bool, smoke: bool, smoke_cap: int = 10) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="pandas",
        variant_slug=STUDY_ID,
        instrument="NQ",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "qty": QTY,
            "tp_scale_usd": 1000,
            "tp_runner_usd": 2000,
            "sl": "close_beyond_area",
            "arm": "0930-1600",
        },
    )
    try:
        _progress("load unified review ledger")
        ledger = pd.read_csv(LEDGER)
        ledger = ledger[ledger["candidate_status"].fillna("COMPLETED") == "COMPLETED"].copy()
        ledger = ledger[pd.notna(ledger["structure_complete_at"])].copy()
        if smoke:
            ledger = ledger.head(smoke_cap)
        _progress("candidates=%d" % len(ledger))

        _progress("load NQ 1m DBN")
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        if smoke:
            days = sorted(gby.keys())
            keep = set()
            for ts in ledger["structure_complete_at"]:
                d = _localize(pd.Timestamp(ts)).date()
                if d in days:
                    i = days.index(d)
                    keep.update(days[max(0, i - 1) : i + 8])
            gby = {d: gby[d] for d in days if d in keep}
        bars = build_globex_1m(gby)
        _progress("1m bars=%d" % len(bars))

        trade_rows = []
        exit_rows = []
        for i, (_, row) in enumerate(ledger.iterrows()):
            if (i + 1) % 10 == 0 or i == 0:
                _progress("sim %d/%d" % (i + 1, len(ledger)))
            result = simulate_candidate(row, bars)
            if isinstance(result, tuple):
                tr, exits = result
            else:
                tr, exits = result, []
            trade_rows.append(tr)
            for e in exits:
                e2 = dict(e)
                e2["candidate_id"] = tr["candidate_id"]
                e2["seed_id"] = tr["seed_id"]
                e2["side"] = tr["side"]
                e2["entry_ts"] = tr["entry_ts"]
                e2["entry_px"] = tr["entry_px"]
                exit_rows.append(e2)

        trades = pd.DataFrame(trade_rows)
        exits = pd.DataFrame(exit_rows)
        trades.to_csv(HUB / "trades.csv", index=False)
        exits.to_csv(HUB / "unit_exits.csv", index=False)

        filled = trades[trades["filled"] == True]  # noqa: E712
        net = float(filled["net_usd"].sum()) if len(filled) else 0.0
        # crude equity on trade close order
        if len(filled):
            eq = filled.sort_values("entry_ts")["net_usd"].cumsum()
            dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
        else:
            dd = 0.0
        ns = (net / abs(dd)) if dd else 0.0
        wins = filled[filled["net_usd"] > 0] if len(filled) else filled
        wr = 100.0 * len(wins) / len(filled) if len(filled) else 0.0

        by_side = (
            filled.groupby("side")["net_usd"].agg(["count", "sum", "mean"]).reset_index()
            if len(filled)
            else pd.DataFrame()
        )
        by_side.to_csv(HUB / "by_side.csv", index=False)
        reason = (
            exits.groupby("reason")["net_usd"].agg(["count", "sum"]).reset_index()
            if len(exits)
            else pd.DataFrame()
        )
        reason.to_csv(HUB / "exit_mix.csv", index=False)

        summary = {
            "study_id": STUDY_ID,
            "parent_hash": PARENT_HASH,
            "candidates": int(len(trades)),
            "fills": int(len(filled)),
            "fill_rate": float(len(filled) / len(trades)) if len(trades) else 0.0,
            "net_usd": net,
            "closed_dd_usd": dd,
            "ns": ns,
            "win_rate": wr,
            "avg_trade": float(filled["net_usd"].mean()) if len(filled) else 0.0,
            "median_trade": float(filled["net_usd"].median()) if len(filled) else 0.0,
            "long_net": float(filled.loc[filled.side == "long", "net_usd"].sum()) if len(filled) else 0.0,
            "short_net": float(filled.loc[filled.side == "short", "net_usd"].sum()) if len(filled) else 0.0,
            "scale_hits": int(filled["scale_hit"].sum()) if len(filled) else 0,
            "runner_hits": int(filled["runner_hit"].sum()) if len(filled) else 0,
            "stops": int(filled["stopped"].sum()) if len(filled) else 0,
            "tp_scale_pts": TP_SCALE_PTS,
            "tp_runner_pts": TP_RUNNER_PTS,
            "smoke": smoke,
        }
        pd.DataFrame([summary]).to_csv(HUB / "summary.csv", index=False)

        stance = "research"
        if net > 0 and ns >= 1.0 and len(filled) >= 20:
            stance = "research — interesting; needs causality plugin + OOS before promote"
        elif net <= 0:
            stance = "reject / weak on this rule set"

        lines = [
            "# NQ Protected-Area Approach Trade V1",
            "",
            "STATUS: RESEARCH TRIAL (pandas 1m path)",
            "Parent structure ledger hash: `%s`" % PARENT_HASH,
            "",
            "## Rules",
            "- Arm RTH 09:30–16:00 only; cancel outside window.",
            "- Above area → BUY limit @ area_high (approach from above).",
            "- Below area → SELL limit @ area_low (approach from below).",
            "- 4 contracts; take 3 off at +$1000 combined (%.4f pts); runner to +$2000 (%.1f pts)."
            % (TP_SCALE_PTS, TP_RUNNER_PTS),
            "- SL: 1m **close** beyond far side of area (wick alone does not stop).",
            "- One attempt per frozen completed candidate through seed_expiry.",
            "",
            "## Results",
            "| Metric | Value |",
            "|---|---:|",
            "| Candidates | %d |" % summary["candidates"],
            "| Fills | %d (%.0f%%) |" % (summary["fills"], 100 * summary["fill_rate"]),
            "| Net | $%+.0f |" % net,
            "| Closed DD | $%+.0f |" % dd,
            "| N/S | %.2f |" % ns,
            "| Win rate | %.0f%% |" % wr,
            "| Long / short net | $%+.0f / $%+.0f |" % (summary["long_net"], summary["short_net"]),
            "| Scale / runner / stops | %d / %d / %d |"
            % (summary["scale_hits"], summary["runner_hits"], summary["stops"]),
            "",
            "## Exit mix",
            "",
        ]
        if len(reason):
            lines += ["| reason | n | net |", "|---|---:|---:|"]
            for _, r in reason.sort_values("sum", ascending=False).iterrows():
                lines.append("| %s | %d | $%+.0f |" % (r["reason"], int(r["count"]), r["sum"]))
        lines += [
            "",
            "**Stance:** %s" % stance,
            "",
            "Hub: `%s`" % HUB,
            "DSR: `%s`" % DSR,
            "smoke=%s" % smoke,
            "",
        ]
        body = "\n".join(lines)
        (HUB / "SUMMARY.md").write_text(body, encoding="utf-8")
        (HUB / "EMAIL.txt").write_text("potions: %s\n\n%s\n" % (STUDY_ID, body), encoding="utf-8")
        (HUB / "RUN_COMPLETE.json").write_text(json.dumps(summary, indent=2) + "\n")

        complete_run(
            rid,
            net_usd=net,
            stress_dd_usd=dd,
            close_mtm_dd_usd=dd,
            ns=ns,
            trades=int(len(filled)),
            notes=stance,
            meta=summary,
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(subject="potions: %s complete" % STUDY_ID, body=(HUB / "EMAIL.txt").read_text())
        _progress("DONE net=$%+.0f N/S=%.2f fills=%d stance=%s" % (net, ns, len(filled), stance))
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: %s FAILED" % STUDY_ID, body=err[-4000:])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--smoke-cap", type=int, default=10)
    args = ap.parse_args()
    run(email=bool(args.email), smoke=bool(args.smoke), smoke_cap=int(args.smoke_cap))


if __name__ == "__main__":
    main()
