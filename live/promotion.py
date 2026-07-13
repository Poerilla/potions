from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


PROMOTION_STATES = (
    "research",
    "broker_like",
    "hardened_realism",
    "null_tested",
    "causality_passed",
    "tick_escalated",
    "paper_eligible",
)


@dataclass(frozen=True)
class PromotionStatus:
    current_state: str
    required_artifacts: List[str]
    missing_artifacts: List[str]
    required_causality_mode: str = "strict"
    actual_causality_mode: str = ""
    causality_violations: int = 0
    tick_escalation_count: int = 0
    violation_risk_count: int = 0
    null_seed_count: int = 0
    dsr_status: str = "missing"
    campaign_psr_dsr_status: str = "missing"
    blocking_reasons: List[str] = field(default_factory=list)

    def row(self) -> Dict[str, object]:
        return asdict(self)


def generate_promotion_status(
    root: Path,
    *,
    required_causality_mode: str = "strict",
    minimum_null_seeds: int = 1,
    require_campaign_dsr: bool = True,
    write: bool = True,
) -> PromotionStatus:
    root = Path(root)
    manifest_path = root / "run_manifest.json"
    execution_scrutiny_path = root / "execution_scrutiny.csv"
    causality_csv = root / "causality_violations.csv"
    causality_jsonl = root / "events" / "causality_violations.jsonl"
    null_summary = root / "null_summary.csv"
    dsr_ledger = root / "dsr_ledger.csv"
    campaign_dsr = root / "campaign_dsr.csv"
    summary_csv = root / "summary.csv"

    required = [
        "run_manifest.json",
        "summary.csv",
        "execution_scrutiny.csv",
        "causality_violations.csv or events/causality_violations.jsonl",
        "null_summary.csv",
        "dsr_ledger.csv",
        "campaign_dsr.csv",
    ]
    missing: List[str] = []
    if not manifest_path.exists():
        missing.append("run_manifest.json")
    if not summary_csv.exists():
        missing.append("summary.csv")
    if not execution_scrutiny_path.exists():
        missing.append("execution_scrutiny.csv")
    if not causality_csv.exists() and not causality_jsonl.exists():
        missing.append("causality_violations.csv or events/causality_violations.jsonl")
    if not null_summary.exists():
        missing.append("null_summary.csv")
    if not dsr_ledger.exists():
        missing.append("dsr_ledger.csv")
    if require_campaign_dsr and not campaign_dsr.exists():
        missing.append("campaign_dsr.csv")

    manifest = _read_json(manifest_path)
    actual_causality_mode = str(manifest.get("causality_mode") or "")
    violations = _count_causality_violations(causality_csv, causality_jsonl)
    scrutiny_counts = _scrutiny_counts(execution_scrutiny_path)
    null_seed_count = _null_seed_count(null_summary)
    dsr_status = "present" if dsr_ledger.exists() else "missing"
    campaign_status = "present" if campaign_dsr.exists() else "missing"

    blocking: List[str] = []
    if actual_causality_mode != required_causality_mode:
        blocking.append("causality_mode_not_strict")
    if violations > 0:
        blocking.append("causality_violations>0")
    if scrutiny_counts["needs_tick"] > 0:
        blocking.append("tick_escalation_required")
    if scrutiny_counts["violation_risk"] > 0:
        blocking.append("execution_violation_risk")
    if null_seed_count < minimum_null_seeds:
        blocking.append("missing_null_results")
    if dsr_status == "missing":
        blocking.append("missing_dsr_ledger")
    if require_campaign_dsr and campaign_status == "missing":
        blocking.append("missing_campaign_dsr")
    blocking.extend("missing:%s" % item for item in missing)

    state = _state_from_artifacts(
        manifest_exists=manifest_path.exists(),
        summary_exists=summary_csv.exists(),
        null_seed_count=null_seed_count,
        actual_mode=actual_causality_mode,
        required_mode=required_causality_mode,
        violations=violations,
        tick_escalation_count=scrutiny_counts["needs_tick"],
        blocking=blocking,
    )
    status = PromotionStatus(
        current_state=state,
        required_artifacts=required,
        missing_artifacts=missing,
        required_causality_mode=required_causality_mode,
        actual_causality_mode=actual_causality_mode,
        causality_violations=violations,
        tick_escalation_count=scrutiny_counts["needs_tick"],
        violation_risk_count=scrutiny_counts["violation_risk"],
        null_seed_count=null_seed_count,
        dsr_status=dsr_status,
        campaign_psr_dsr_status=campaign_status,
        blocking_reasons=blocking,
    )
    if write:
        root.mkdir(parents=True, exist_ok=True)
        (root / "promotion_status.json").write_text(json.dumps(status.row(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return status


def _state_from_artifacts(
    *,
    manifest_exists: bool,
    summary_exists: bool,
    null_seed_count: int,
    actual_mode: str,
    required_mode: str,
    violations: int,
    tick_escalation_count: int,
    blocking: List[str],
) -> str:
    if not manifest_exists:
        return "research"
    if not summary_exists:
        return "broker_like"
    if null_seed_count <= 0:
        return "hardened_realism"
    if actual_mode != required_mode or violations > 0:
        return "null_tested"
    if tick_escalation_count > 0:
        return "causality_passed"
    if blocking:
        return "tick_escalated"
    return "paper_eligible"


def _read_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _count_causality_violations(csv_path: Path, jsonl_path: Path) -> int:
    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8") as fh:
            return sum(1 for _row in csv.DictReader(fh))
    if jsonl_path.exists():
        return sum(1 for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip())
    return 0


def _scrutiny_counts(path: Path) -> Dict[str, int]:
    counts = {"ok": 0, "needs_tick": 0, "violation_risk": 0}
    if not path.exists():
        return counts
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            klass = str(row.get("scrutiny_classification") or "").upper()
            if klass == "OK":
                counts["ok"] += 1
            elif klass == "NEEDS_TICK":
                counts["needs_tick"] += 1
            elif klass == "VIOLATION_RISK":
                counts["violation_risk"] += 1
    return counts


def _null_seed_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if "seed" in (reader.fieldnames or []):
            return len({row.get("seed") for row in reader if row.get("seed") not in {"", None}})
        return sum(1 for _row in reader)

