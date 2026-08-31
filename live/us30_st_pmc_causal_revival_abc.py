"""US30 ST+PMC causal revival matrix — paths A / B / C (completed-hour, 1m fills).

Locked cells (no exit/threshold sweep):
  - path_a_prepost_pmc_3r
  - path_b_post_hour_pmc_retest_3r  (expiry 240m, one-shot)
  - path_c_continuation_break_3r
  - path_c_continuation_break_2r_10r
Control reference (not re-run): completed-hour ST-limit 2R→10R N/S 1.47
  from ``live/state/us30_st_pmc_runner_variants``.

Usage:
  python -m live.us30_st_pmc_causal_revival_abc --email
  python -m live.us30_st_pmc_causal_revival_abc --email --smoke
  python -m live.us30_st_pmc_causal_revival_abc --email --only path_a_prepost_pmc_3r
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_retest_replay import (
    DEFAULT_FEE_PER_UNIT,
    DEFAULT_SLIPPAGE_TICKS,
    read_bars_from_engine_bars,
)
from .hourly_st_pmc_strategyplugin_variants import _replay_hourly_with_1m
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "us30_st_pmc_causal_revival_abc"
SYM = "US30"
TICK = 0.1
DSR = "TRL-2026-00186"
CONTROL_NS = 1.47
CONTROL_NOTE = (
    "completed-hour ST-limit sl50_tp150_runners_2r_10r from "
    "live/state/us30_st_pmc_runner_variants (N/S 1.47) — locked control, not re-run"
)


@dataclass(frozen=True)
class Cell:
    name: str
    path: str
    stop_pts: float
    tp1_pts: float
    tp1_qty: int = 1
    entry_qty: int = 1
    runner_specs: tuple = ()
    runner_stop_to_be_after_tp1: bool = False
    retest_expiry_minutes: int = 240
    notes: str = ""

    @property
    def max_contracts(self) -> int:
        n = int(self.tp1_qty)
        for q, _ in self.runner_specs:
            n += int(q)
        return max(1, n)


CELLS: List[Cell] = [
    Cell(
        "path_a_prepost_pmc_3r",
        path="A",
        stop_pts=50.0,
        tp1_pts=150.0,
        notes="Path A: pre-posted PMC limit; fair 3R",
    ),
    Cell(
        "path_b_post_hour_pmc_retest_3r",
        path="B",
        stop_pts=50.0,
        tp1_pts=150.0,
        retest_expiry_minutes=240,
        notes="Path B: post-hour PMC one-shot retest; expiry 240m; fair 3R",
    ),
    Cell(
        "path_c_continuation_break_3r",
        path="C",
        stop_pts=50.0,
        tp1_pts=150.0,
        notes="Path C: post-hour H/L break → next 1m market; fair 3R",
    ),
    Cell(
        "path_c_continuation_break_2r_10r",
        path="C",
        stop_pts=50.0,
        tp1_pts=150.0,
        tp1_qty=1,
        runner_specs=((1, 300.0), (1, 1500.0)),
        runner_stop_to_be_after_tp1=True,
        notes="Path C + locked 2R→10R runner management cell",
    ),
]


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
            "trial_subclass": "us30_st_pmc_causal_revival_abc",
            "is_independent": "TRUE",
            "market": "US30",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "paths": ["A", "B", "C"],
                    "cells": [c.name for c in CELLS],
                    "fill_tape": "1m",
                    "signal": "completed_hour",
                    "stop_pts": 50,
                    "tp1_pts": 150,
                    "path_b_expiry_min": 240,
                    "no_exit_sweep": True,
                }
            ),
            "fixed_parameters_ref": "live/us30_st_pmc_causal_revival_abc.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "US30 ST+PMC causal revival A/B/C; fresh trial; no N/S 29.39 inheritance",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str = "COMPLETE") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _hourly_and_1m(*, smoke: bool = False):
    one_m_path = REPO / "fx" / "us30_1m.csv"
    daily = REPO / "fx" / "us30_daily.csv"
    gby = load_fx_1m_by_ny_date(one_m_path, SYM)
    one_m_df = concat_all_1m(gby)
    hourly_df = resample_hourly(one_m_df)
    if smoke:
        # ~90 calendar days of hourly bars
        cut = hourly_df.index.min() + pd_offset_days(90)
        hourly_df = hourly_df[hourly_df.index <= cut]
        one_m_df = one_m_df[one_m_df.index <= cut + pd_offset_days(1)]
    bars: List[Bar] = []
    for ts, row in hourly_df.iterrows():
        bars.append(
            Bar(
                instrument=SYM,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m_path),
            )
        )
    return bars, one_m_df, daily, one_m_path


def pd_offset_days(n: int):
    import pandas as pd

    return pd.Timedelta(days=int(n))


def _config_json(cell: Cell, daily: Path) -> str:
    payload: Dict[str, Any] = {
        "daily_bars_path": str(daily),
        "stop_pts": cell.stop_pts,
        "target_pts": cell.tp1_pts,
        "tick_size": TICK,
        "entry_qty": cell.entry_qty,
        "tp1_qty": cell.tp1_qty,
        "runner_qty": 0,
        "runner_specs": [{"qty": int(q), "target_pts": t} for q, t in cell.runner_specs],
        "runner_stop_to_be_after_tp1": bool(cell.runner_stop_to_be_after_tp1),
        "ma_filter": "none",
        "close_against_entry_exit": False,
        "st_flip_exit": False,
        "pmc_cross_exit": False,
        "record_levels": False,
        "retest_add_enabled": False,
        "bb_add_enabled": False,
        "revival_path": cell.path,
        "retest_expiry_minutes": int(cell.retest_expiry_minutes),
        "entry_level": "pmc",
        "continuation_trigger": "hour_extreme_break",
    }
    return json.dumps(payload, sort_keys=True)


def run_cell(
    cell: Cell,
    *,
    bars: Sequence[Bar],
    one_m,
    daily: Path,
    one_m_path: Path,
    force: bool,
) -> Dict[str, Any]:
    strategy_id = "us30_st_pmc_revival_%s" % cell.name
    state_root = HUB / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    need_1m_strategy = cell.path == "C"
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="hourly_st_pmc_causal_revival",
        version="v1",
        instrument=SYM,
        broker_instrument=SYM,
        account_mode="paper",
        enabled=True,
        timeframes="1h,1m" if need_1m_strategy else "1h",
        max_contracts=cell.max_contracts,
        max_open_orders=32,
        config_json=_config_json(cell, daily),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        tick_size={SYM: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    _replay_hourly_with_1m(
        engine,
        hourly_bars=list(bars),
        one_m=one_m,
        instrument=SYM,
        source=str(one_m_path),
        label=cell.name,
        always_1m=need_1m_strategy,
        signal_offset_minutes=60,
    )
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    audit_bars = read_bars_from_engine_bars(list(bars))
    units = units_from_live_fills(
        fills_path,
        strategy_id,
        match_within_trade_id=True,
        stop_pts=float(cell.stop_pts),
        runner_be_after_tp1=bool(cell.runner_stop_to_be_after_tp1),
    )
    audit = audit_units(
        name="US30 ST+PMC revival %s" % cell.name,
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m_path,
        bars=audit_bars,
        units=units,
        instrument=SYM,
        notes=cell.notes,
        output_root=HUB / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    stress = float(audit.intrabar_mtm_dd_usd or audit.close_mtm_dd_usd or 0.0)
    ns = (audit.net_usd / abs(stress)) if stress else 0.0
    wr = (100.0 * float(audit.win_units) / float(audit.units)) if audit.units else 0.0

    # Lightweight causality: feature available_at ordering + fill after live_after.
    feat_path = state_root / "feature_snapshots.csv"
    orders_path = state_root / "orders.csv"
    viol = 0
    if feat_path.exists():
        with feat_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ev = row.get("event_ts") or ""
                av = row.get("available_at_ts") or ""
                cur = row.get("current_bar_ts") or ""
                if not ev or not av or not cur:
                    viol += 1
                    continue
                try:
                    if pd_ts(ev) > pd_ts(av) or pd_ts(av) > pd_ts(cur):
                        viol += 1
                except Exception:
                    viol += 1
    fill_before_active = 0
    if fills_path.exists() and orders_path.exists():
        orders = {r["broker_order_id"]: r for r in csv.DictReader(orders_path.open())}
        for fill in csv.DictReader(fills_path.open()):
            if str(fill.get("reason") or "") != "entry":
                continue
            od = orders.get(str(fill.get("broker_order_id") or ""))
            if not od:
                continue
            la = od.get("live_after_ts") or ""
            ft = fill.get("ts") or ""
            if la and ft and pd_ts(ft) <= pd_ts(la):
                fill_before_active += 1

    return {
        "cell": cell.name,
        "path": cell.path,
        "net_usd": round(float(audit.net_usd), 2),
        "stress_dd_usd": round(stress, 2),
        "ns": round(ns, 3),
        "units": int(audit.units),
        "trades": int(audit.trades),
        "wr_pct": round(wr, 1),
        "max_open": int(audit.max_open_units),
        "feature_order_violations": viol,
        "fills_before_live_after": fill_before_active,
        "causal_ok": int(viol == 0 and fill_before_active == 0),
        "state_root": str(state_root.relative_to(REPO)),
        "notes": cell.notes,
    }


def pd_ts(value: str):
    import pandas as pd

    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)
    return ts


def write_outputs(rows: List[Dict[str, Any]], *, smoke: bool) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["cell"]
    with (HUB / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    lines = [
        "# US30 ST+PMC causal revival — paths A / B / C",
        "",
        "Fresh strategies under completed-hour causality. **No inheritance** of retired "
        "fair-3R N/S 29.39. Locked 1m broker-realistic path; no exit/threshold sweep.",
        "",
        "Control (reference only): %s" % CONTROL_NOTE,
        "",
        "## Results%s" % (" (SMOKE)" if smoke else ""),
        "",
        "| cell | path | net | stress | N/S | units | WR% | causal_ok | notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | %s | $%.0f | $%.0f | %.2f | %d | %.1f | %s | %s |"
            % (
                r["cell"],
                r["path"],
                r["net_usd"],
                r["stress_dd_usd"],
                r["ns"],
                r["units"],
                r["wr_pct"],
                "yes" if r["causal_ok"] else "NO",
                r["notes"],
            )
        )
    lines += [
        "",
        "| control_completed_hour_st_2r10r | ctrl | — | — | **%.2f** | — | — | yes | %s |"
        % (CONTROL_NS, CONTROL_NOTE),
        "",
        "## Stance",
        "",
    ]
    survivors = [r for r in rows if r["causal_ok"] and float(r["ns"]) > 1.0 and int(r["units"]) >= 30]
    if survivors:
        best = max(survivors, key=lambda r: float(r["ns"]))
        lines.append(
            "- Research retain candidate(s): **%s** (N/S %.2f). Still below demo bar unless "
            "forward evidence confirms; do not promote on this board alone."
            % (best["cell"], best["ns"])
        )
    else:
        lines.append(
            "- **No cell clears a research-retain bar** (causal + N/S>1 + n≥30). "
            "Old fair-3R remains an audit lesson — not a live-demo alpha."
        )
    lines += [
        "",
        "- Demo decision for legacy book: see "
        "`live/state/us30_st_pmc_signal_hour_attribution/DEMO_DECISION.md` "
        "(alpha_status: invalidated).",
        "",
        "Hub: `%s`" % HUB,
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = [
        "US30 ST+PMC causal revival A/B/C %s." % ("SMOKE" if smoke else "complete"),
        "Hub: %s" % HUB,
        "DSR: %s" % DSR,
        "Control ref: completed-hour 2R→10R N/S %.2f (not re-run)." % CONTROL_NS,
        "",
        "Results:",
    ]
    for r in rows:
        email.append(
            "  %s path=%s N/S=%.2f net=$%.0f units=%d causal=%s"
            % (r["cell"], r["path"], r["ns"], r["net_usd"], r["units"], r["causal_ok"])
        )
    if survivors:
        email.append(
            "Stance: research interest in %s — not demo-promote yet."
            % ", ".join(r["cell"] for r in survivors)
        )
    else:
        email.append("Stance: no independent merit cell; keep fair-3R retired.")
    (HUB / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    POINT_VALUES[SYM] = 1.0
    DEFAULT_TICK_SIZE[SYM] = TICK
    HUB.mkdir(parents=True, exist_ok=True)

    cells = CELLS
    if args.only:
        want = set(args.only)
        cells = [c for c in CELLS if c.name in want]
        if not cells:
            raise SystemExit("No cells matched --only %s" % sorted(want))

    # DSR before peek.
    _append_dsr()
    rid = begin_run(
        run_class="broker_like",
        variant_slug="us30_st_pmc_causal_revival_abc",
        instrument="US30",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="A/B/C revival matrix starting",
        meta={"cells": [c.name for c in cells], "smoke": bool(args.smoke)},
    )
    try:
        print("Loading US30 1m → hourly (completed-hour offset)…", flush=True)
        bars, one_m, daily, one_m_path = _hourly_and_1m(smoke=bool(args.smoke))
        print("Hourly=%d 1m=%d" % (len(bars), len(one_m)), flush=True)

        rows: List[Dict[str, Any]] = []
        for cell in cells:
            print("RUN %s (path %s)" % (cell.name, cell.path), flush=True)
            row = run_cell(
                cell,
                bars=bars,
                one_m=one_m,
                daily=daily,
                one_m_path=one_m_path,
                force=bool(args.force) or bool(args.smoke),
            )
            rows.append(row)
            print(
                "  Net=$%.0f Stress=$%.0f N/S=%.2f units=%d causal_ok=%s"
                % (row["net_usd"], row["stress_dd_usd"], row["ns"], row["units"], row["causal_ok"]),
                flush=True,
            )

        write_outputs(rows, smoke=bool(args.smoke))
        _mark_dsr("COMPLETE")
        best_ns = max((float(r["ns"]) for r in rows), default=0.0)
        complete_run(
            rid,
            net_usd=float(rows[0]["net_usd"]) if rows else None,
            stress_dd_usd=float(rows[0]["stress_dd_usd"]) if rows else None,
            ns=best_ns,
            trades=sum(int(r["trades"]) for r in rows),
            notes="revival A/B/C complete",
            meta={"rows": rows},
        )
        if args.email:
            send_email(
                subject="potions: US30 ST+PMC revival A/B/C %s"
                % ("SMOKE" if args.smoke else "complete"),
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        print("Wrote %s" % HUB, flush=True)
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _mark_dsr("FAILED")
        if args.email:
            send_email(
                subject="potions: US30 ST+PMC revival A/B/C FAILED",
                body="Hub: %s\nError: %s" % (HUB, exc),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
