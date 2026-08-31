"""Causality audit for CHOP20 causal-entry variant hubs.

Checks (promotion contract)::

  available_at < entry_ts
  exit_ts > entry_ts
  range_confirm_date <= signal_day
  range_age <= 60
  entry_mode in {close_to_globex, close_to_next_rth}

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_causal_entry_audit --email
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "live" / "state" / "chop20_dynamic_range_causal_entry_variants"
HUB = REPO / "live" / "state" / "chop20_dynamic_range_causal_entry_audit"
DSR = "TRL-2026-00181"
MAX_AGE = 60
ALLOWED_MODES = {"close_to_globex", "close_to_next_rth"}


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
            "trial_subclass": "chop20_causal_entry",
            "is_independent": "TRUE",
            "market": "NQ,MNQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "checks": [
                        "available_at_before_entry",
                        "exit_after_entry",
                        "range_confirm_before_signal",
                        "range_age_le_60",
                        "entry_mode_allowed",
                    ],
                    "source": str(SOURCE.relative_to(REPO)),
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_causal_entry_audit.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Causal entry variant path audit",
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


def audit_trades(path: Path, slug: str) -> Dict:
    issues: List[str] = []
    checks = {
        "slug": slug,
        "trades": 0,
        "available_before_entry_ok": 0,
        "exit_after_entry_ok": 0,
        "range_confirm_ok": 0,
        "range_age_ok": 0,
        "entry_mode_ok": 0,
        "issues": 0,
        "pass": False,
    }
    if not path.exists():
        issues.append("missing trades.csv")
        checks["issues"] = 1
        checks["issue_list"] = issues
        return checks
    trades = pd.read_csv(path)
    checks["trades"] = len(trades)
    if trades.empty:
        checks["pass"] = True
        checks["issue_list"] = []
        return checks
    for _, t in trades.iterrows():
        mode = str(t.get("entry_mode", ""))
        if mode in ALLOWED_MODES:
            checks["entry_mode_ok"] += 1
        else:
            issues.append("trade %s bad entry_mode=%s" % (t["trade_id"], mode))
        aa = pd.to_datetime(t["daily_feature_available_at"], utc=True)
        et = pd.to_datetime(t["entry_ts"], utc=True)
        xt = pd.to_datetime(t["exit_ts"], utc=True)
        if aa < et:
            checks["available_before_entry_ok"] += 1
        else:
            issues.append("trade %s available_at >= entry" % t["trade_id"])
        if xt > et:
            checks["exit_after_entry_ok"] += 1
        else:
            issues.append("trade %s exit<=entry" % t["trade_id"])
        confirm = pd.Timestamp(str(t["range_confirmed_ts"])).tz_localize(None).date()
        signal_day = pd.Timestamp(str(t.get("signal_day", confirm))).tz_localize(None).date()
        if confirm <= signal_day:
            checks["range_confirm_ok"] += 1
        else:
            issues.append("trade %s confirm after signal" % t["trade_id"])
        age = int(t["range_age_bars"])
        if 0 < age <= MAX_AGE:
            checks["range_age_ok"] += 1
        else:
            issues.append("trade %s age=%s" % (t["trade_id"], age))
    checks["issues"] = len(issues)
    checks["pass"] = len(issues) == 0
    checks["issue_list"] = issues[:40]
    return checks


def run(*, email: bool) -> pd.DataFrame:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="audit",
        variant_slug="chop20_causal_entry_audit",
        instrument="MULTI",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="causal entry audit",
    )
    try:
        rows = []
        if not SOURCE.exists():
            raise FileNotFoundError("missing source hub %s" % SOURCE)
        for child in sorted(SOURCE.iterdir()):
            trades_p = child / "trades.csv"
            if not trades_p.exists():
                continue
            _progress("audit %s …" % child.name)
            rows.append(audit_trades(trades_p, child.name))
        board = pd.DataFrame([{k: v for k, v in r.items() if k != "issue_list"} for r in rows])
        board.to_csv(HUB / "causality_checks.csv", index=False)
        with (HUB / "issues.json").open("w") as fh:
            json.dump({r["slug"]: r.get("issue_list", []) for r in rows}, fh, indent=2)
        all_pass = all(bool(r["pass"]) for r in rows if r["trades"] > 0)
        any_trades = any(r["trades"] > 0 for r in rows)
        status = "PASS" if all_pass and any_trades else ("FAIL" if any_trades else "NO_DATA")
        lines = [
            "# LOOKAHEAD_REVIEW — CHOP20 causal entry variants",
            "",
            "**Status:** %s" % status,
            "",
            "## Contract",
            "",
            "1. Daily CHOP20 + close breakout known at `daily_feature_available_at` (last RTH 1m).",
            "2. Entry fill strictly **after** availability (`close_to_globex` or `close_to_next_rth`).",
            "3. Management only on bars after `entry_ts`; stop-first.",
            "4. Range confirm ≤ signal day; age ≤ 60.",
            "",
            "## Checks",
            "",
            "| slug | trades | avail<entry | exit>entry | confirm | age | mode | Pass |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for r in rows:
            if r["trades"] == 0:
                lines.append("| %s | 0 | — | — | — | — | — | EMPTY |" % r["slug"])
                continue
            lines.append(
                "| %s | %d | %d | %d | %d | %d | %d | %s |"
                % (
                    r["slug"],
                    r["trades"],
                    r["available_before_entry_ok"],
                    r["exit_after_entry_ok"],
                    r["range_confirm_ok"],
                    r["range_age_ok"],
                    r["entry_mode_ok"],
                    "PASS" if r["pass"] else "FAIL",
                )
            )
        lines += [
            "",
            "## Residual",
            "",
            "- Still pandas path — StrategyPlugin `live_after_ts` / feature_snapshots required for Tier-1.",
            "- Tick path inside 1m bar unknown; stop-first is pessimistic.",
            "",
            "Hub: `%s`" % HUB,
            "Source: `%s`" % SOURCE,
            "DSR: `%s`" % DSR,
            "",
        ]
        text = "\n".join(lines)
        (HUB / "LOOKAHEAD_REVIEW.md").write_text(text)
        (HUB / "SUMMARY.md").write_text(text)
        (HUB / "EMAIL.txt").write_text(text)
        complete_run(rid, trades=int(board["trades"].sum()) if not board.empty else 0, notes=status)
        _mark_dsr("COMPLETE")
        if email:
            send_email(subject="potions: CHOP20 causal entry audit %s" % status, body=text)
        return board
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-1500:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: CHOP20 causal entry audit FAILED", body=err[-4000:])
        raise


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    run(email=args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
