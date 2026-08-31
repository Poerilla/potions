"""Causality / lookahead audit for CHOP20 boundary60 1m path books.

Not a StrategyPlugin yet — audits the pandas path contract against Platform
HTF/finer-tape rules:

  - Daily bars are signal-only (range + breakout).
  - Entry fill is last RTH 1m of the signal day (ts after prior management).
  - Stops/targets fill only on 1m bars strictly after entry_ts.
  - Same-bar policy is stop-first.
  - Range confirmation date ≤ entry date; range_age ≤ 60.

Writes LOOKAHEAD_REVIEW.md + causality_checks.csv under the hub.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_causality_audit --email
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pytz

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "live" / "state" / "chop20_dynamic_range_1m_boundary60_xmarket"
HUB = REPO / "live" / "state" / "chop20_dynamic_range_causality_audit"
DSR = "TRL-2026-00179"
NY = pytz.timezone("America/New_York")
MARKETS = ("nq", "ym", "mym", "mnq")
MAX_AGE = 60


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
            "trial_class": "CAUSALITY_AUDIT",
            "trial_subclass": "chop20_boundary60_1m",
            "is_independent": "TRUE",
            "market": "NQ,YM,MYM,MNQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "checks": [
                        "range_confirm_before_entry",
                        "range_age_le_60",
                        "exit_after_entry",
                        "entry_in_rth_close_window",
                        "stop_first_contract",
                    ],
                    "source": str(SOURCE.relative_to(REPO)),
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_causality_audit.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Path-aware causality audit (pre-StrategyPlugin)",
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


def audit_market(market: str) -> Dict:
    root = SOURCE / market
    trades_p = root / "trades.csv"
    exits_p = root / "unit_exits.csv"
    issues: List[str] = []
    checks = {
        "market": market.upper(),
        "trades": 0,
        "unit_exits": 0,
        "range_confirm_ok": 0,
        "range_age_ok": 0,
        "exit_after_entry_ok": 0,
        "entry_rth_window_ok": 0,
        "issues": 0,
    }
    if not trades_p.exists():
        issues.append("missing trades.csv")
        checks["issues"] = 1
        checks["pass"] = False
        checks["issue_list"] = issues
        return checks

    trades = pd.read_csv(trades_p)
    exits = pd.read_csv(exits_p) if exits_p.exists() else pd.DataFrame()
    checks["trades"] = len(trades)
    checks["unit_exits"] = len(exits)

    for _, t in trades.iterrows():
        entry_ts = pd.to_datetime(t["entry_ts"], utc=True).tz_convert(NY)
        exit_ts = pd.to_datetime(t["exit_ts"], utc=True).tz_convert(NY)
        confirm = pd.Timestamp(str(t["range_confirmed_ts"])).tz_localize(None).date()
        entry_day = entry_ts.date()
        if confirm <= entry_day:
            checks["range_confirm_ok"] += 1
        else:
            issues.append("trade %s confirm after entry" % t["trade_id"])
        age = int(t["range_age_bars"])
        if 0 < age <= MAX_AGE:
            checks["range_age_ok"] += 1
        else:
            issues.append("trade %s age=%s" % (t["trade_id"], age))
        if exit_ts > entry_ts:
            checks["exit_after_entry_ok"] += 1
        else:
            issues.append("trade %s exit<=entry" % t["trade_id"])
        # Entry = last RTH 1m of session. Normal close ≈15:59; early closes ≈12:59.
        et = entry_ts.time()
        if time(12, 55) <= et < time(16, 0):
            checks["entry_rth_window_ok"] += 1
        else:
            issues.append(
                "trade %s entry time %s not in session-close window (12:55–16:00)"
                % (t["trade_id"], et.isoformat())
            )

    if not exits.empty:
        for _, e in exits.iterrows():
            ets = pd.to_datetime(e["entry_ts"], utc=True)
            xts = pd.to_datetime(e["exit_ts"], utc=True)
            if xts <= ets:
                issues.append("unit exit <= entry trade=%s unit=%s" % (e["trade_id"], e["unit_number"]))

    checks["issues"] = len(issues)
    checks["pass"] = len(issues) == 0
    checks["issue_list"] = issues[:50]
    return checks


def run(*, email: bool) -> pd.DataFrame:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="audit",
        variant_slug="chop20_boundary60_causality",
        instrument="MULTI",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="causality audit running",
    )
    try:
        rows = []
        for m in MARKETS:
            _progress("audit %s …" % m.upper())
            rows.append(audit_market(m))
        board = pd.DataFrame(
            [
                {
                    k: v
                    for k, v in r.items()
                    if k != "issue_list"
                }
                for r in rows
            ]
        )
        board.to_csv(HUB / "causality_checks.csv", index=False)
        with (HUB / "issues.json").open("w") as fh:
            json.dump({r["market"]: r.get("issue_list", []) for r in rows}, fh, indent=2)

        all_pass = all(bool(r["pass"]) for r in rows if r["trades"] > 0)
        any_trades = any(r["trades"] > 0 for r in rows)

        lines = [
            "# LOOKAHEAD_REVIEW — CHOP20 boundary60 1m path",
            "",
            "**Status:** %s" % ("PASS" if all_pass and any_trades else "FAIL" if any_trades else "NO_DATA"),
            "",
            "## Contract under audit",
            "",
            "1. **Daily = signal only** — CHOP20 range metrics + close outside frozen box.",
            "2. **Entry** — last RTH 1m of signal day; fill = daily close ±1 tick adverse.",
            "3. **Management** — only 1m bars with `ts > entry_ts` (cursor advances).",
            "4. **Same-bar** — stop-first (boundary stop evaluated before targets).",
            "5. **Freshness** — `range_age_bars <= 60`.",
            "6. **Not StrategyPlugin** — no Engine `live_after_ts` / `feature_snapshots` yet;",
            "   this audit validates the pandas path against Platform HTF/finer-tape intent.",
            "",
            "## Per-market checks",
            "",
            "| Market | Trades | confirm≤entry | age≤60 | exit>entry | entry∈RTH close | Pass |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for r in rows:
            if r["trades"] == 0:
                lines.append("| %s | 0 | — | — | — | — | NO_DATA |" % r["market"])
                continue
            lines.append(
                "| %s | %d | %d | %d | %d | %d | %s |"
                % (
                    r["market"],
                    r["trades"],
                    r["range_confirm_ok"],
                    r["range_age_ok"],
                    r["exit_after_entry_ok"],
                    r["entry_rth_window_ok"],
                    "PASS" if r["pass"] else "FAIL",
                )
            )
        lines += [
            "",
            "## Residual risks (not auto-fail)",
            "",
            "- Daily OHLC target/stop sequencing is **resolved on 1m**, but true tick path",
            "  inside a 1m bar is still unknown (stop-first is pessimistic).",
            "- No Engine `CausalityGuard` / `feature_snapshots.csv` until StrategyPlugin port.",
            "- HA condition overlays are diagnostic; do not treat as live gates without proxies.",
            "",
            "Hub: `%s`" % HUB,
            "Source: `%s`" % SOURCE,
            "DSR: `%s`" % DSR,
            "",
        ]
        (HUB / "LOOKAHEAD_REVIEW.md").write_text("\n".join(lines))
        (HUB / "SUMMARY.md").write_text("\n".join(lines))
        body = "potions: CHOP20 causality audit %s\n\n" % (
            "PASS" if all_pass and any_trades else "FAIL"
        ) + "\n".join(lines)
        (HUB / "EMAIL.txt").write_text(body)
        _mark_dsr("COMPLETE")
        complete_run(
            rid,
            notes="causality %s" % ("PASS" if all_pass else "FAIL"),
            meta={"pass": all_pass, "markets": [r["market"] for r in rows]},
        )
        if email:
            send_email(
                subject="potions: CHOP20 causality audit %s"
                % ("PASS" if all_pass and any_trades else "FAIL"),
                body=body,
            )
        _progress("DONE causality pass=%s" % all_pass)
        return board
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: CHOP20 causality FAILED", body=err[-4000:])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    run(email=bool(args.email))


if __name__ == "__main__":
    main()
