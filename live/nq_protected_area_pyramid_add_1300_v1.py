"""NQ protected-area pyramid-add to 13:00 — diagnostic 1m path replay.

Rules (user-specified trial vs approach_trade_v1):
  - Same approach entry: above area → BUY limit @ area_high;
    below area → SELL limit @ area_low. Arm from 09:30 NY.
  - Scale-in: 1 contract on first fill, then +1 at each subsequent 1m
    bar open while not stopped (until 13:00).
  - Hard flatten: exit ALL open units when the clock hits 13:00
    (open of first bar with time >= 13:00).
  - Stop: 1m candle *close* beyond the far side of the area (not wick).
  - On stop: one opposing re-entry allowed (immediate 1-lot at stop close,
    then resume +1/min). If that reverse attempt also stops → done.
  - No new work after 13:00; one reverse max per frozen candidate.

Frozen events from seed-bias review / parent V1 ledgers. Not a promotion claim.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_protected_area_pyramid_add_1300_v1 --email
  python -m live.nq_protected_area_pyramid_add_1300_v1 --email --smoke
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
HUB = REPO / "live" / "state" / "nq_protected_area_pyramid_add_1300_v1"
STUDY_ID = "nq_protected_area_pyramid_add_1300_v1"
PARENT_HASH = "402795e0a05e2fbc"
DSR = "TRL-2026-00192"
NY = pytz.timezone("America/New_York")
POINT_VALUE = 20.0
FEE = 1.50
ARM_START = time(9, 30)
FLAT_AT = time(13, 0)  # hard exit all; no adds / no new arms at or after
MAX_REVERSALS = 1


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
            "trial_subclass": "protected_area_pyramid_add_1300",
            "is_independent": "TRUE",
            "market": "NQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "entry": "limit_approach_from_outside",
                    "add": "1_per_minute_while_alive",
                    "flat_at": "13:00",
                    "sl": "close_beyond_far_area_edge",
                    "max_reversals": MAX_REVERSALS,
                    "parent_hash": PARENT_HASH,
                }
            ),
            "fixed_parameters_ref": "live/nq_protected_area_pyramid_add_1300_v1.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Pyramid +1/min to 13:00 flat; one opposing re-entry after close-beyond stop",
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


def _bar_time(ts: pd.Timestamp) -> time:
    return _localize(ts).time()


def _can_arm(ts: pd.Timestamp) -> bool:
    t = _bar_time(ts)
    return ARM_START <= t < FLAT_AT


def _at_or_after_flat(ts: pd.Timestamp) -> bool:
    return _bar_time(ts) >= FLAT_AT


def _pnl_pts(side: str, entry: float, exit_px: float) -> float:
    return (exit_px - entry) if side == "long" else (entry - exit_px)


@dataclass
class Unit:
    side: str
    entry_ts: pd.Timestamp
    entry_px: float
    attempt: int  # 1 = first direction, 2 = reverse


@dataclass
class Campaign:
    side: str
    attempt: int
    units: List[Unit] = field(default_factory=list)
    entry_bar_ts: Optional[pd.Timestamp] = None
    realized: float = 0.0
    exits: List[dict] = field(default_factory=list)
    mfe_pts: float = 0.0  # vs first-fill avg / last add — track vs avg entry
    mae_pts: float = 0.0
    max_qty: int = 0
    end_reason: str = ""

    @property
    def qty(self) -> int:
        return len(self.units)

    @property
    def avg_entry(self) -> float:
        if not self.units:
            return float("nan")
        return float(np.mean([u.entry_px for u in self.units]))


def _flatten(camp: Campaign, ts: pd.Timestamp, px: float, reason: str) -> None:
    if not camp.units:
        return
    for u in list(camp.units):
        pts = _pnl_pts(u.side, u.entry_px, px)
        net = pts * POINT_VALUE - FEE  # exit fee; entry fee already charged at add
        camp.realized += net
        camp.exits.append(
            {
                "exit_ts": ts.isoformat(),
                "exit_px": float(px),
                "qty": 1,
                "side": u.side,
                "attempt": u.attempt,
                "entry_ts": u.entry_ts.isoformat(),
                "entry_px": float(u.entry_px),
                "points": float(pts),
                "net_usd": float(net),
                "reason": reason,
            }
        )
    camp.units.clear()
    camp.end_reason = reason


def _add_unit(camp: Campaign, ts: pd.Timestamp, px: float) -> None:
    # Entry fee on add
    camp.realized -= FEE
    camp.units.append(Unit(side=camp.side, entry_ts=ts, entry_px=float(px), attempt=camp.attempt))
    camp.max_qty = max(camp.max_qty, camp.qty)
    if camp.entry_bar_ts is None:
        camp.entry_bar_ts = ts


def _update_excursions(camp: Campaign, hi: float, lo: float) -> None:
    if not camp.units:
        return
    avg = camp.avg_entry
    fav = _pnl_pts(camp.side, avg, hi if camp.side == "long" else lo)
    adv = _pnl_pts(camp.side, avg, lo if camp.side == "long" else hi)
    camp.mfe_pts = max(camp.mfe_pts, fav)
    camp.mae_pts = min(camp.mae_pts, adv)


def _stopped(camp: Campaign, area_lo: float, area_hi: float, cl: float) -> bool:
    return (camp.side == "long" and cl < area_lo) or (camp.side == "short" and cl > area_hi)


def simulate_candidate(row: pd.Series, bars: pd.DataFrame) -> Tuple[dict, List[dict]]:
    cand_id = str(row["candidate_id"])
    if pd.notna(row.get("candidate_status")) and str(row["candidate_status"]) != "COMPLETED":
        return {
            "candidate_id": cand_id,
            "seed_id": row.get("seed_id", ""),
            "status": "SKIP_NO_CANDIDATE",
            "filled": False,
            "net_usd": 0.0,
        }, []

    complete = _localize(pd.Timestamp(row["structure_complete_at"]))
    expiry = _localize(pd.Timestamp(row["seed_expiry"]))
    area_lo, area_hi = _area_bounds(row)
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

    camp: Optional[Campaign] = None
    campaigns: List[Campaign] = []
    reversals_used = 0
    pending_reverse: Optional[str] = None  # long|short to open next opportunity
    status = "NO_FILL"
    done = False

    for ts, bar in win.iterrows():
        if done:
            break
        ts = _localize(pd.Timestamp(ts))
        hi = float(bar["high"])
        lo = float(bar["low"])
        cl = float(bar["close"])
        op = float(bar["open"])

        # --- Manage open campaign ---
        if camp is not None and camp.qty > 0:
            # 13:00 hard flatten (before add / stop)
            if _at_or_after_flat(ts):
                _flatten(camp, ts, op, "flat_1300")
                campaigns.append(camp)
                camp = None
                pending_reverse = None
                status = "FLAT_1300"
                done = True
                break

            # +1 at open of each minute after the entry bar
            if camp.entry_bar_ts is not None and ts > camp.entry_bar_ts:
                _add_unit(camp, ts, op)

            _update_excursions(camp, hi, lo)

            # Close-based stop on full book
            if _stopped(camp, area_lo, area_hi, cl):
                stopped_side = camp.side
                _flatten(camp, ts, cl, "sl_close_beyond_area")
                campaigns.append(camp)
                camp = None
                status = "STOPPED"
                if reversals_used < MAX_REVERSALS and _can_arm(ts):
                    # One opposing re-entry on the cross
                    pending_reverse = "short" if stopped_side == "long" else "long"
                    reversals_used += 1
                else:
                    pending_reverse = None
                    done = True
                    break
            else:
                continue

        # --- Flat: timeout / expiry / arm / reverse ---
        if _at_or_after_flat(ts):
            # No new entries at/after 13:00
            if pending_reverse is not None:
                pending_reverse = None
            if campaigns:
                status = status if status != "NO_FILL" else "FLAT_1300"
            done = True
            break

        if ts > expiry:
            status = "EXPIRED_NO_FILL" if not campaigns else "EXPIRED"
            done = True
            break

        if not _can_arm(ts) and pending_reverse is None:
            continue

        # Immediate reverse after stop-through: open 1 at this bar's close already
        # handled below on a later bar — if pending set on stop bar, open next bar
        # at open (cleaner path) OR same-bar after stop. Same-bar: open at stop close.
        if pending_reverse is not None:
            # Same-bar reverse uses stop close; later bars use open (already through).
            side = pending_reverse
            same_bar = (
                bool(campaigns)
                and campaigns[-1].end_reason == "sl_close_beyond_area"
                and bool(campaigns[-1].exits)
                and campaigns[-1].exits[-1]["exit_ts"] == ts.isoformat()
            )
            fill_px = cl if same_bar else op
            # Re-entry on cross: allow fill once we are through to the far side.
            through = (side == "short" and fill_px <= area_lo) or (
                side == "long" and fill_px >= area_hi
            )
            if through and _can_arm(ts):
                camp = Campaign(side=side, attempt=1 + reversals_used)
                _add_unit(camp, ts, fill_px)
                pending_reverse = None
                status = "OPEN_REVERSE"
                _update_excursions(camp, hi, lo)
            continue

        # Initial approach arm (first attempt only; reverse uses pending path)
        if campaigns or camp is not None:
            continue
        if not _can_arm(ts):
            continue

        if op > area_hi:
            armed_side, limit_px = "long", area_hi
        elif op < area_lo:
            armed_side, limit_px = "short", area_lo
        else:
            continue

        filled = False
        fill_px = limit_px
        if armed_side == "long" and lo <= limit_px:
            filled = True
        elif armed_side == "short" and hi >= limit_px:
            filled = True

        if not filled:
            continue

        camp = Campaign(side=armed_side, attempt=1)
        _add_unit(camp, ts, fill_px)
        status = "OPEN"
        _update_excursions(camp, hi, lo)
        if _stopped(camp, area_lo, area_hi, cl):
            _flatten(camp, ts, cl, "sl_close_beyond_area")
            campaigns.append(camp)
            camp = None
            status = "STOPPED"
            if reversals_used < MAX_REVERSALS and _can_arm(ts):
                pending_reverse = "short" if armed_side == "long" else "long"
                reversals_used += 1
                # Open reverse same bar at stop close
                side = pending_reverse
                camp = Campaign(side=side, attempt=2)
                _add_unit(camp, ts, cl)
                pending_reverse = None
                status = "OPEN_REVERSE"
                _update_excursions(camp, hi, lo)
            else:
                done = True
                break

    # Leftover flatten (data end / unfinished)
    if camp is not None and camp.qty > 0:
        last_ts = _localize(pd.Timestamp(win.index[-1]))
        last_cl = float(win.iloc[-1]["close"])
        reason = "flat_1300" if _at_or_after_flat(last_ts) else "data_end_flatten"
        _flatten(camp, last_ts, last_cl, reason)
        campaigns.append(camp)
        status = "FLATTENED"

    all_exits: List[dict] = []
    total_net = 0.0
    max_qty = 0
    sides = set()
    reasons = set()
    n_attempts = len(campaigns)
    first_side = campaigns[0].side if campaigns else ""
    for c in campaigns:
        total_net += c.realized
        max_qty = max(max_qty, c.max_qty)
        sides.add(c.side)
        for e in c.exits:
            e2 = dict(e)
            e2["candidate_id"] = cand_id
            e2["seed_id"] = row["seed_id"]
            all_exits.append(e2)
            reasons.add(e["reason"])

    filled = len(campaigns) > 0
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
        "status": status,
        "filled": filled,
        "side": first_side,
        "sides": ",".join(sorted(sides)),
        "n_attempts": n_attempts,
        "reversals_used": reversals_used,
        "max_qty": max_qty,
        "n_units_exited": len(all_exits),
        "net_usd": float(total_net),
        "exit_reasons": ",".join(sorted(reasons)),
        "stopped_any": any(c.end_reason == "sl_close_beyond_area" for c in campaigns),
        "flat_1300_any": any(c.end_reason == "flat_1300" for c in campaigns),
        "mfe_pts": float(max((c.mfe_pts for c in campaigns), default=float("nan"))),
        "mae_pts": float(min((c.mae_pts for c in campaigns), default=float("nan"))),
        "entry_ts": campaigns[0].entry_bar_ts.isoformat() if campaigns and campaigns[0].entry_bar_ts else "",
        "entry_px": campaigns[0].units[0].entry_px if campaigns and False else (
            float(all_exits[0]["entry_px"]) if all_exits else np.nan
        ),
    }
    # Fix entry_px from first campaign first exit's entry
    if campaigns and campaigns[0].exits:
        out["entry_px"] = float(campaigns[0].exits[0]["entry_px"])
        out["entry_ts"] = campaigns[0].exits[0]["entry_ts"]
    return out, all_exits


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
            "add": "1_per_min",
            "flat_at": "13:00",
            "sl": "close_beyond_area",
            "max_reversals": MAX_REVERSALS,
            "arm": "0930-1300",
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

        trade_rows: List[dict] = []
        exit_rows: List[dict] = []
        for i, (_, row) in enumerate(ledger.iterrows()):
            if (i + 1) % 10 == 0 or i == 0:
                _progress("sim %d/%d" % (i + 1, len(ledger)))
            tr, exits = simulate_candidate(row, bars)
            trade_rows.append(tr)
            exit_rows.extend(exits)

        trades = pd.DataFrame(trade_rows)
        exits = pd.DataFrame(exit_rows)
        trades.to_csv(HUB / "trades.csv", index=False)
        exits.to_csv(HUB / "unit_exits.csv", index=False)

        filled = trades[trades["filled"] == True]  # noqa: E712
        net = float(filled["net_usd"].sum()) if len(filled) else 0.0
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

        avg_max_qty = float(filled["max_qty"].mean()) if len(filled) else 0.0
        n_rev = int(filled["reversals_used"].clip(upper=1).sum()) if len(filled) else 0
        n_flat = int(filled["flat_1300_any"].sum()) if len(filled) else 0
        n_stop = int(filled["stopped_any"].sum()) if len(filled) else 0

        summary: Dict[str, Any] = {
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
            "avg_max_qty": avg_max_qty,
            "unit_exits": int(len(exits)),
            "candidates_with_reverse": n_rev,
            "flat_1300_campaigns": n_flat,
            "stopped_campaigns": n_stop,
            "smoke": smoke,
        }
        pd.DataFrame([summary]).to_csv(HUB / "summary.csv", index=False)

        stance = "research"
        if net > 0 and ns >= 1.0 and len(filled) >= 20:
            stance = "research — interesting; needs causality plugin + OOS before promote"
        elif net <= 0:
            stance = "reject / weak on this rule set"

        lines = [
            "# NQ Protected-Area Pyramid-Add → 13:00 V1",
            "",
            "STATUS: RESEARCH TRIAL (pandas 1m path)",
            "Parent structure ledger hash: `%s`" % PARENT_HASH,
            "",
            "## Rules",
            "- Arm 09:30–13:00 NY; hard flatten all at 13:00.",
            "- Above area → BUY limit @ area_high; below → SELL limit @ area_low.",
            "- +1 contract on first fill, then +1 at each subsequent 1m open while alive.",
            "- SL: 1m **close** beyond far side of area (wick alone does not stop).",
            "- On stop: one opposing re-entry at stop close, resume +1/min; second stop ends.",
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
            "| Long / short net (1st side) | $%+.0f / $%+.0f |"
            % (summary["long_net"], summary["short_net"]),
            "| Avg peak qty | %.1f |" % avg_max_qty,
            "| Unit exits | %d |" % summary["unit_exits"],
            "| With reverse / flat-1300 / stopped | %d / %d / %d |" % (n_rev, n_flat, n_stop),
            "",
            "## Exit mix (per unit)",
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
