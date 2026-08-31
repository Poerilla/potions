"""Adverse execution stress for US30 ST+PMC continuation v1 (path C 2R→10R).

Re-runs the locked preferred cell under slippage_ticks ∈ {1,2,4,8}.
Writes live/state/us30_st_pmc_causal_revival_abc/continuation_audit/execution_stress/.

Usage:
  PYTHONPATH=... python -m live.us30_st_pmc_continuation_exec_stress --email
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .hourly_st_pmc_retest_replay import (
    DEFAULT_FEE_PER_UNIT,
    read_bars_from_engine_bars,
)
from .hourly_st_pmc_strategyplugin_variants import _replay_hourly_with_1m
from .models import StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .us30_st_pmc_causal_revival_abc import (
    CELLS,
    HUB,
    REPO,
    SYM,
    TICK,
    _config_json,
    _hourly_and_1m,
)
from .verification import QuietPaperVerificationProvider

DSR = "TRL-2026-00188"
OUT = HUB / "continuation_audit" / "execution_stress"
CELL_NAME = "path_c_continuation_break_2r_10r"
TICKS = (1, 2, 4, 8)


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
            "trial_class": "EXECUTION_STRESS",
            "trial_subclass": "us30_st_pmc_continuation_slippage",
            "is_independent": "FALSE",
            "market": "US30",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {"cell": CELL_NAME, "slippage_ticks": list(TICKS), "parent_dsr": "TRL-2026-00186"}
            ),
            "fixed_parameters_ref": "live/us30_st_pmc_continuation_exec_stress.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "0.50",
            "status": "PENDING",
            "notes": "Adverse slippage stress for continuation v1 preferred cell",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def run_slip(cell, *, bars, one_m, daily, one_m_path, slippage_ticks: float) -> Dict[str, Any]:
    strategy_id = "us30_cont_v1_slip_%g" % slippage_ticks
    state_root = OUT / "states" / strategy_id
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="hourly_st_pmc_causal_revival",
        version="v1",
        instrument=SYM,
        broker_instrument=SYM,
        account_mode="paper",
        enabled=True,
        timeframes="1h,1m",
        max_contracts=cell.max_contracts,
        max_open_orders=32,
        config_json=_config_json(cell, daily),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=float(slippage_ticks),
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
        label=strategy_id,
        always_1m=True,
        signal_offset_minutes=60,
    )
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(
        fills_path,
        strategy_id,
        match_within_trade_id=True,
        stop_pts=float(cell.stop_pts),
        runner_be_after_tp1=bool(cell.runner_stop_to_be_after_tp1),
    )
    audit = audit_units(
        name="US30 continuation slip %g" % slippage_ticks,
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m_path,
        bars=read_bars_from_engine_bars(list(bars)),
        units=units,
        instrument=SYM,
        notes="adverse execution stress",
        output_root=OUT / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    stress = float(audit.intrabar_mtm_dd_usd or audit.close_mtm_dd_usd or 0.0)
    ns = (audit.net_usd / abs(stress)) if stress else 0.0
    return {
        "slippage_ticks": slippage_ticks,
        "net_usd": round(float(audit.net_usd), 2),
        "stress_dd_usd": round(stress, 2),
        "ns": round(ns, 3),
        "units": int(audit.units),
        "trades": int(audit.trades),
        "max_open": int(audit.max_open_units),
        "state_root": str(state_root.relative_to(REPO)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--ticks", nargs="*", type=float, default=None)
    args = ap.parse_args()
    ticks = tuple(args.ticks) if args.ticks else TICKS

    POINT_VALUES[SYM] = 1.0
    DEFAULT_TICK_SIZE[SYM] = TICK
    OUT.mkdir(parents=True, exist_ok=True)
    cell = next(c for c in CELLS if c.name == CELL_NAME)

    _append_dsr()
    rid = begin_run(
        run_class="audit",
        variant_slug="us30_st_pmc_continuation_exec_stress",
        instrument="US30",
        hub_path=str(OUT.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="continuation adverse slippage stress",
        meta={"ticks": list(ticks)},
    )
    try:
        print("Loading bars…", flush=True)
        bars, one_m, daily, one_m_path = _hourly_and_1m(smoke=False)
        rows: List[Dict[str, Any]] = []
        for t in ticks:
            print("RUN slippage_ticks=%g" % t, flush=True)
            row = run_slip(
                cell, bars=bars, one_m=one_m, daily=daily, one_m_path=one_m_path, slippage_ticks=t
            )
            rows.append(row)
            print(
                "  net=$%.0f stress=$%.0f N/S=%.2f units=%d"
                % (row["net_usd"], row["stress_dd_usd"], row["ns"], row["units"]),
                flush=True,
            )

        fields = list(rows[0].keys())
        with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow(r)

        lines = [
            "# Continuation v1 — adverse execution stress (Engine)",
            "",
            "Cell: `%s` (frozen contract `us30_st_pmc_completed_hour_continuation_v1`)" % CELL_NAME,
            "DSR: `%s` (parent TRL-2026-00186)" % DSR,
            "",
            "| slippage_ticks | net | stress | N/S | units | trades |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            lines.append(
                "| %g | $%.0f | $%.0f | %.2f | %d | %d |"
                % (r["slippage_ticks"], r["net_usd"], r["stress_dd_usd"], r["ns"], r["units"], r["trades"])
            )
        base = rows[0]
        harsh = rows[-1]
        ok = all(float(r["ns"]) > 0 for r in rows)
        lines += [
            "",
            "## Stance",
            "",
            "- Baseline ticks=1 N/S %.2f; harshest ticks=%g N/S %.2f."
            % (base["ns"], harsh["slippage_ticks"], harsh["ns"]),
            "- Economically credible under ordinary adverse cases: **%s**."
            % ("YES" if ok else "NO — edge flips or vanishes under stress"),
            "- Still **not demo-promote**; stress is necessary not sufficient.",
            "",
        ]
        (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Append section into CONTINUATION_AUDIT.md
        audit_md = HUB / "CONTINUATION_AUDIT.md"
        if audit_md.exists():
            text = audit_md.read_text(encoding="utf-8")
            marker = "## 5b. Engine adverse slippage (authoritative)"
            block = [
                "",
                marker,
                "",
                "Full Engine re-run of preferred cell (DSR %s). See `%s`."
                % (DSR, OUT.relative_to(HUB)),
                "",
                "| slippage_ticks | net | stress | N/S | units |",
                "|---:|---:|---:|---:|---:|",
            ]
            for r in rows:
                block.append(
                    "| %g | $%.0f | $%.0f | %.2f | %d |"
                    % (r["slippage_ticks"], r["net_usd"], r["stress_dd_usd"], r["ns"], r["units"])
                )
            block.append("")
            block_txt = "\n".join(block)
            if marker in text:
                # replace from marker to next ## or end
                pre, _, rest = text.partition(marker)
                # drop old 5b through next ## 
                idx = rest.find("\n## ")
                if idx >= 0:
                    text = pre.rstrip() + block_txt + rest[idx + 1 :]
                else:
                    text = pre.rstrip() + block_txt
            else:
                # insert before "## 6."
                if "## 6. Correct next decision" in text:
                    text = text.replace(
                        "## 6. Correct next decision",
                        block_txt.lstrip() + "\n## 6. Correct next decision",
                    )
                else:
                    text = text.rstrip() + "\n" + block_txt
            audit_md.write_text(text, encoding="utf-8")

        email = [
            "US30 ST+PMC continuation Engine execution stress complete.",
            "Hub: %s" % OUT,
            "DSR: %s" % DSR,
            "",
        ]
        for r in rows:
            email.append(
                "  ticks=%g N/S=%.2f net=$%.0f units=%d"
                % (r["slippage_ticks"], r["ns"], r["net_usd"], r["units"])
            )
        email.append(
            "Stance: %s under ticks≤%g; demo=false."
            % ("credible" if ok else "NOT credible", ticks[-1])
        )
        (OUT / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")

        _mark_dsr("COMPLETE")
        complete_run(
            rid,
            net_usd=float(harsh["net_usd"]),
            stress_dd_usd=float(harsh["stress_dd_usd"]),
            ns=float(harsh["ns"]),
            trades=int(harsh["trades"]),
            units=int(harsh["units"]),
            notes="continuation exec stress complete",
            meta={"rows": rows},
        )
        if args.email:
            send_email(
                subject="potions: US30 continuation execution stress complete",
                body=(OUT / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        print("Wrote %s" % OUT, flush=True)
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _mark_dsr("FAILED")
        if args.email:
            send_email(
                subject="potions: US30 continuation execution stress FAILED",
                body="Hub: %s\nError: %s" % (OUT, exc),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
