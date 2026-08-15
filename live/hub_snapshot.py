"""Deterministic strategy-hub snapshots, boards, emails, and change logs.

Produces decision-oriented INTERIM / COMPLETE reports without dumping raw
worker commands. Preserves raw artifacts; writes derived status/report outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .exit_attribution import attribute_hub_unit_trades
from .regime_overlap import duplicate_sleeve_warnings

REPO = Path(__file__).resolve().parents[1]

KNOWN_VARIANTS = (
    "sl50_tp150_3r_1mfill",
    "sl50_tp150_runners_2r_10r",
    "sl50_tp150_runners_2r_indef",
)

VARIANT_LABEL = {
    "sl50_tp150_3r_1mfill": "3R",
    "sl50_tp150_runners_2r_10r": "2R→10R",
    "sl50_tp150_runners_2r_indef": "indef",
}

JPY_MARKETS = frozenset({"usdjpy", "audjpy"})
MIN_SAMPLE_UNITS = 30

# Decision labels (deterministic gates; promote is never auto-assigned).
LABEL_PROMOTE = "PROMOTE"
LABEL_RETAIN = "RETAIN"
LABEL_RESEARCH = "RESEARCH"
LABEL_REJECT = "REJECT"
LABEL_PENDING_NORM = "PENDING_NORMALIZATION"
LABEL_PENDING_ACCT = "PENDING_ACCOUNTING"
LABEL_INSUFFICIENT = "INSUFFICIENT_SAMPLE"
LABEL_INCOMPLETE = "INCOMPLETE"
LABEL_NOT_RANKABLE = "NOT_RANKABLE"

STATUS_COMPLETE = "COMPLETE"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

WORKER_PATTERNS = (
    "live.fx_index_metals_st_pmc_runner_variants",
    "live.futures_st_pmc_runner_variants",
    "live.us30_st_pmc_runner_variants",
    "live.st_pmc_runner_length_sweep",
    "live.indefinite_lot_accounting",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hub_path(hub: str) -> Path:
    p = Path(hub)
    if not p.is_absolute():
        p = REPO / p
    return p


def _f(v: object) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except Exception:
        return None


def _i(v: object) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "") else None
    except Exception:
        return None


def _money(v: object) -> str:
    try:
        x = float(v)
    except Exception:
        return str(v)
    sign = "-" if x < 0 else ""
    ax = abs(x)
    if ax >= 1000:
        return "%s$%.1fk" % (sign, ax / 1000.0)
    return "%s$%.0f" % (sign, ax)


def _load_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _infer_hub_market(hub: Path) -> Optional[str]:
    name = hub.name.lower()
    if name.startswith("us30"):
        return "us30"
    return None


def _audit_path(hub: Path, market: str, variant: str) -> Path:
    sid = "%s_hourly_st_pmc_%s" % (market, variant) if market else (
        "hourly_st_pmc_%s" % variant
    )
    # FX / futures layout: hub/<market>/audits/<sid>/<sid>/reports/...
    if market:
        nested = hub / market / "audits" / sid / sid / "reports" / "MTM_AUDIT.md"
        if nested.exists():
            return nested
    # US30 flat layout: hub/audits/<sid>/<sid>/reports/...
    flat = hub / "audits" / sid / sid / "reports" / "MTM_AUDIT.md"
    if flat.exists():
        return flat
    if market:
        return hub / market / "audits" / sid / sid / "reports" / "MTM_AUDIT.md"
    return flat


def _audit_exists(hub: Path, market: str, variant: str) -> bool:
    return _audit_path(hub, market, variant).exists()


def _filter_active_jobs_for_hub(
    hub: Path, active: Sequence[Dict[str, Any]], expected_markets: Sequence[str]
) -> List[Dict[str, Any]]:
    """Keep only workers that belong to this hub family / markets."""
    name = hub.name.lower()
    want = {m.lower() for m in expected_markets if m}
    out: List[Dict[str, Any]] = []
    for j in active:
        cmd = str(j.get("command") or "")
        pat = str(j.get("pattern") or "")
        mkt = str(j.get("market") or "").lower()
        if "fx_index_metals" in name:
            if "fx_index_metals" not in cmd and "fx_index_metals" not in pat:
                if j.get("status") != "lot_accounting":
                    continue
            if want and mkt and mkt not in want:
                continue
        elif name.startswith("us30"):
            if "us30_st_pmc" not in cmd and "us30_st_pmc" not in pat:
                if j.get("status") != "lot_accounting" or (
                    mkt and mkt != "us30"
                ):
                    continue
        elif "futures" in name:
            if "futures_st_pmc" not in cmd and "futures_st_pmc" not in pat:
                if j.get("status") != "lot_accounting":
                    continue
            if want and mkt and mkt not in want:
                continue
        else:
            if want and mkt and mkt not in want:
                continue
        out.append(j)
    return out


def _parse_mtm_audit(path: Path) -> Optional[dict]:
    """Derive summary-like metrics from MTM_AUDIT.md when summary.csv lags."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")

    def _cell(label: str) -> Optional[str]:
        m = re.search(
            r"\|\s*%s\s*\|\s*([^|]+)\|" % re.escape(label), text, re.I
        )
        return m.group(1).strip() if m else None

    def _num(label: str) -> Optional[float]:
        raw = _cell(label)
        if raw is None:
            return None
        raw = raw.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            return float(raw)
        except Exception:
            return None

    units = _num("Units")
    net = _num("Net dollars")
    stress = _num("Intrabar stress MTM DD")
    ns = _num("Net / intrabar stress DD")
    max_open = _num("Max open units")
    wr = None
    win = _num("Winning units")
    lose = _num("Losing units")
    if win is not None and lose is not None and (win + lose) > 0:
        wr = 100.0 * win / (win + lose)
    # Calendar EOY flatten is distinct from terminal forced_flat_open marks in the audit.
    eoy = 0
    m_eoy = re.search(r"eoy_flatten(?:_units)?\s*[=:]\s*(\d+)", text, re.I)
    if m_eoy:
        eoy = int(m_eoy.group(1))
    terminal_open = 0
    m_term = re.search(r"forced_flat_open\s*=\s*(\d+)", text, re.I)
    if m_term:
        terminal_open = int(m_term.group(1))
    if units is None and net is None:
        return None
    return {
        "units": int(units) if units is not None else 0,
        "trades": int(units) if units is not None else 0,
        "net_usd": net,
        "stress_dd_usd": stress,
        "ns": ns,
        "wr_pct": wr,
        "max_open": int(max_open) if max_open is not None else None,
        "eoy_flatten_units": eoy,
        "terminal_open_lots": terminal_open,
        "notes": "reachable; sourced_from_MTM_AUDIT",
        "_metric_source_hint": "MTM_AUDIT.md",
    }


def _load_lot_correct(hub: Path) -> Dict[Tuple[str, str], dict]:
    out: Dict[Tuple[str, str], dict] = {}
    for name in ("LOT_CORRECT_ACCOUNTING.csv", "lot_correct_accounting.csv"):
        path = hub / name
        if not path.exists():
            continue
        for r in _load_csv(path):
            key = (str(r.get("market") or "").lower(), str(r.get("variant") or ""))
            out[key] = r
    return out


def _usd_norm_markets(hub: Path) -> Dict[str, dict]:
    """Parse FAIR_3R_USD_NORMALIZED.md for markets with published USD figures."""
    path = hub / "FAIR_3R_USD_NORMALIZED.md"
    found: Dict[str, dict] = {}
    if not path.exists():
        return found
    text = path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(
        r"\|\s*\d+\s*\|\s*\*?\*?([A-Za-z0-9]+)\*?\*?\s*\|[^|]*\|[^|]*\$([0-9,\.\-]+)\s*\|[^|]*\$([0-9,\.\-]+)\s*\|\s*\*?\*?([0-9.\-]+)",
        text,
    ):
        mkt = m.group(1).lower()
        found[mkt] = {
            "net_usd": float(m.group(2).replace(",", "")),
            "stress_dd_usd": float(m.group(3).replace(",", "")),
            "ns": float(m.group(4)),
            "source": "FAIR_3R_USD_NORMALIZED.md",
        }
    # Also mark USDJPY bridge section as normalized even if table parse fails
    if "usdjpy" in text.lower() and "usd-normalized" in text.lower():
        found.setdefault("usdjpy", {"source": "FAIR_3R_USD_NORMALIZED.md"})
    return found


def scan_active_jobs(extra_patterns: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Structured active-job list (PID/command kept for JSON, not email)."""
    patterns = list(WORKER_PATTERNS) + list(extra_patterns or [])
    jobs: List[Dict[str, Any]] = []
    seen_pids = set()
    for pat in patterns:
        try:
            out = subprocess.check_output(["pgrep", "-af", pat], text=True)
        except subprocess.CalledProcessError:
            continue
        except FileNotFoundError:
            break
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if "notify_when_done" in ln or "run_completion_report" in ln:
                continue
            if "hub_snapshot" in ln or "run_complete_status" in ln:
                continue
            # Skip orchestrator / shell wrappers (keep real python -m workers).
            if "bash -c" in ln or "/bin/bash" in ln:
                continue
            if "tee -a" in ln and "orchestrator" in ln:
                continue
            parts = ln.split(None, 1)
            try:
                pid = int(parts[0])
            except Exception:
                continue
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            cmd = parts[1] if len(parts) > 1 else ln
            if " -m live." not in cmd and "live." not in cmd:
                continue
            market, variants, status = _parse_job_cmd(cmd)
            if market.startswith("$") or "{" in market:
                market = ""
            progress, active_variant = _progress_from_log(market, variants) if market else (None, "")
            variant = active_variant or (variants[0] if variants else "")
            jobs.append(
                {
                    "pid": pid,
                    "market": market,
                    "variant": variant,
                    "variants": variants,
                    "status": status,
                    "progress": progress,
                    "command": cmd[:300],
                    "pattern": pat,
                }
            )
    return jobs


def _parse_job_cmd(cmd: str) -> Tuple[str, List[str], str]:
    market = ""
    variants: List[str] = []
    m = re.search(r"--markets?\s+(\S+)", cmd)
    if m:
        market = m.group(1).split(",")[0].lower()
    m = re.search(r"--only\s+(.+)$", cmd)
    if m:
        for tok in m.group(1).strip().split():
            if tok.startswith("-"):
                break
            if tok.startswith("sl50_tp150"):
                variants.append(tok)
    if not variants:
        if "runners_2r_indef" in cmd:
            variants = ["sl50_tp150_runners_2r_indef"]
        elif "runners_2r_10r" in cmd:
            variants = ["sl50_tp150_runners_2r_10r"]
        elif "3r_1mfill" in cmd:
            variants = ["sl50_tp150_3r_1mfill"]
    status = "running"
    if "indefinite_lot_accounting" in cmd:
        status = "lot_accounting"
        variants = variants or ["lot_correct"]
    return market, variants, status


def _progress_from_log(
    market: str, variants: Sequence[str]
) -> Tuple[Optional[str], str]:
    hub = REPO / "live" / "state" / "fx_index_metals_st_pmc_runner_variants"
    for suffix in ("", "_3r"):
        path = hub / ("run_%s%s.log" % (market, suffix))
        if not path.exists():
            continue
        text = path.read_text(errors="replace")
        done = re.findall(r"(sl50_tp150_\S+)\s+done:", text)
        prog = re.findall(r"(sl50_tp150_\S+)\s+hourly\s+(\d+)/(\d+)", text)
        if not prog and not done:
            continue
        active_v = ""
        if prog:
            v, a, b = prog[-1]
            # If last progress line is for a variant already marked done, keep it
            # only when no later RUN line started another variant.
            active_v = v
            label = VARIANT_LABEL.get(v, v)
            pct = 100 * int(a) / max(int(b), 1)
            bit = "%s %s/%s (%.0f%%)" % (label, a, b, pct)
            done_labs = [
                VARIANT_LABEL.get(d, d)
                for d in done
                if d != v
            ]
            if done_labs:
                bit += "; done=%s" % ",".join(done_labs)
            return bit, active_v
        if done:
            return (
                "done=%s" % ",".join(VARIANT_LABEL.get(d, d) for d in done),
                done[-1],
            )
    if variants:
        return "running", variants[-1]
    return None, ""


def evaluate_row_eligibility(
    row: dict,
    *,
    market: str,
    variant: str,
    audit_ok: bool,
    usd_norm: Optional[dict],
    lot_correct: Optional[dict],
    accounting_warnings: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Eligibility gates for Comparable Core Board membership."""
    is_jpy = market in JPY_MARKETS
    is_indef = "indef" in variant
    units = _i(row.get("units")) or 0
    eoy = _i(row.get("eoy_flatten_units")) or 0
    warnings = list(accounting_warnings or [])

    # Prefer lot-correct / reachable when present.
    metric_source = str(row.get("_metric_source_hint") or "summary.csv_raw")
    net = _f(row.get("net_usd"))
    stress = _f(row.get("stress_dd_usd"))
    ns = _f(row.get("ns"))
    max_open = _i(row.get("max_open"))
    open_lots = eoy
    reachable = False
    lot_ok = False
    forced_flat = None
    mtm_net = None
    margin = None
    hold_median = None
    hold_p90 = None

    if lot_correct:
        lot_ok = True
        reachable = lot_correct.get("reachable_stress_dd_usd") not in (None, "")
        metric_source = "LOT_CORRECT_ACCOUNTING.csv"
        forced_flat = _f(lot_correct.get("forced_flat_equity_usd"))
        mtm_net = _f(lot_correct.get("continuous_terminal_equity_usd"))
        stress = _f(lot_correct.get("reachable_stress_dd_usd")) or stress
        net = forced_flat if forced_flat is not None else net
        ns = _f(lot_correct.get("ns_forced_flat_reachable")) or ns
        max_open = _i(lot_correct.get("max_open_units")) or max_open
        open_lots = _i(lot_correct.get("open_lots_terminal")) or open_lots
        margin = _f(lot_correct.get("max_gross_notional"))
        hold_median = _f(lot_correct.get("hold_hours_median"))
        hold_p90 = _f(lot_correct.get("hold_hours_p90"))
        raw_stress = _f(lot_correct.get("raw_intrabar_stress_dd_usd"))
        if raw_stress is not None and stress is not None and abs(raw_stress) > abs(stress) + 1e-6:
            # Explicit: raw must not override reachable.
            warnings.append("raw_intrabar_stress_superseded_by_reachable")
    else:
        # Heuristic: MTM notes often include reachable stop stress for plugin replays.
        notes = str(row.get("notes") or "")
        if "reachable" in notes.lower() or audit_ok:
            reachable = audit_ok
        if is_indef:
            # Do not present raw FIFO/summary net as forced-flat.
            warnings.append("forced_flat_pending_lot_correct_accounting")

    # Non-JPY FX/index/metals are already USD. JPY rows need a published
    # USD-normalized figure for *this* variant — do not reuse a 3R-only bridge
    # to green-light runner/indef native-JPY boards.
    usd_normalized = not is_jpy
    if is_jpy:
        if (
            usd_norm
            and "net_usd" in usd_norm
            and variant == "sl50_tp150_3r_1mfill"
        ):
            usd_normalized = True
            net = usd_norm.get("net_usd", net)
            stress = usd_norm.get("stress_dd_usd", stress)
            ns = usd_norm.get("ns", ns)
            metric_source = "FAIR_3R_USD_NORMALIZED.md"
        else:
            usd_normalized = False

    sufficient = units >= MIN_SAMPLE_UNITS
    variant_complete = audit_ok and units > 0
    unresolved_warning = any(
        (not w.startswith("raw_intrabar")) for w in warnings
    )

    gates = {
        "variant_complete": variant_complete,
        "usd_normalized": usd_normalized,
        "reachable_stress": bool(reachable),
        "lot_correct": bool(lot_ok) if (is_indef or lot_correct is not None) else True,
        "sufficient_sample": sufficient,
        "eoy_units_flat": (open_lots == 0) if not is_indef else False,
        "no_unresolved_accounting_warning": not unresolved_warning,
        "not_indefinite": not is_indef,
    }
    # Flat-book board: require eoy flat. Indef never enters.
    board_ok = all(
        [
            gates["variant_complete"],
            gates["usd_normalized"],
            gates["reachable_stress"],
            gates["lot_correct"] if is_indef else True,
            gates["sufficient_sample"],
            gates["eoy_units_flat"],
            gates["no_unresolved_accounting_warning"],
            gates["not_indefinite"],
        ]
    )

    reasons: List[str] = []
    if not gates["variant_complete"]:
        reasons.append("variant_incomplete_or_missing_audit")
    if not gates["usd_normalized"]:
        reasons.append("native_jpy_not_usd_normalized")
    if not gates["reachable_stress"]:
        reasons.append("reachable_stress_missing")
    if is_indef:
        reasons.append("indefinite_inventory_not_rankable_vs_flat_books")
    if not gates["sufficient_sample"]:
        reasons.append("insufficient_sample_units<%d" % MIN_SAMPLE_UNITS)
    if not is_indef and not gates["eoy_units_flat"]:
        reasons.append("eoy_open_units_nonzero")
    if unresolved_warning:
        reasons.append("unresolved_accounting_warning")
    if is_indef and not lot_ok:
        reasons.append("pending_lot_correct_forced_flat_accounting")

    label = _decision_label(
        board_ok=board_ok,
        is_indef=is_indef,
        is_jpy=is_jpy,
        usd_normalized=usd_normalized,
        sufficient=sufficient,
        variant_complete=variant_complete,
        lot_ok=lot_ok,
        reasons=reasons,
    )

    return {
        "market": market,
        "variant": variant,
        "book_label": VARIANT_LABEL.get(variant, variant),
        "decision_label": label,
        "comparable_core_eligible": board_ok,
        "gates": gates,
        "exclusion_reasons": reasons,
        "metrics": {
            "net_usd": net,
            "stress_dd_usd": stress,
            "ns": ns,
            "units": units,
            "wr_pct": _f(row.get("wr_pct")),
            "max_open": max_open,
            "eoy_open_lots": open_lots,
            "forced_flat_net_pnl": forced_flat,  # only when lot-correct
            "mark_to_market_net_pnl": mtm_net,
            "reachable_full_stack_stress": stress if (reachable and lot_ok) else (
                stress if reachable and not is_indef else None
            ),
            "max_gross_notional": margin,
            "hold_hours_median": hold_median,
            "hold_hours_p90": hold_p90,
            "metric_source": metric_source,
            "raw_net_usd": _f(row.get("net_usd")),
            "raw_stress_dd_usd": _f(row.get("stress_dd_usd")),
            "raw_ns": _f(row.get("ns")),
            "lot_correct_available": lot_ok,
        },
        "accounting_warnings": warnings,
        "audit_ok": audit_ok,
    }


def _decision_label(
    *,
    board_ok: bool,
    is_indef: bool,
    is_jpy: bool,
    usd_normalized: bool,
    sufficient: bool,
    variant_complete: bool,
    lot_ok: bool,
    reasons: Sequence[str],
) -> str:
    if not variant_complete:
        return LABEL_INCOMPLETE
    if not sufficient:
        return LABEL_INSUFFICIENT
    if is_jpy and not usd_normalized:
        return LABEL_PENDING_NORM
    if is_indef and not lot_ok:
        return LABEL_PENDING_ACCT
    if is_indef:
        return LABEL_RESEARCH  # inventory research, still NOT on core board
    if board_ok:
        return LABEL_RETAIN
    return LABEL_NOT_RANKABLE


def build_snapshot(
    hub: Path,
    *,
    markets: Optional[Sequence[str]] = None,
    expected_variants: Sequence[str] = KNOWN_VARIANTS,
    prior: Optional[Dict[str, Any]] = None,
    worker_patterns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    rows = _load_csv(hub / "summary.csv")
    lot_map = _load_lot_correct(hub)
    usd_map = _usd_norm_markets(hub)
    hub_default_market = _infer_hub_market(hub)
    want = {m.lower() for m in markets} if markets else None

    evaluations: List[Dict[str, Any]] = []
    by_market: Dict[str, Dict[str, Any]] = {}
    present_markets = set()
    seen_keys: set = set()

    for r in rows:
        m = str(r.get("market") or "").lower() or (hub_default_market or "")
        if want and m not in want:
            continue
        v = str(r.get("variant") or "")
        if m:
            present_markets.add(m)
        seen_keys.add((m, v))
        audit_ok = _audit_exists(hub, m, v)
        ev = evaluate_row_eligibility(
            r,
            market=m,
            variant=v,
            audit_ok=audit_ok,
            usd_norm=usd_map.get(m),
            lot_correct=lot_map.get((m, v)),
        )
        evaluations.append(ev)
        entry = by_market.setdefault(m, {"market": m, "variants": {}, "exceptions": []})
        entry["variants"][v] = ev
        if ev["exclusion_reasons"]:
            entry["exceptions"].extend(
                "%s: %s" % (v, "; ".join(ev["exclusion_reasons"]))
            )

    # Discover markets from hub dirs when summary is partial
    if want:
        for m in want:
            present_markets.add(m)
    elif hub_default_market:
        present_markets.add(hub_default_market)
    else:
        for child in hub.iterdir() if hub.exists() else []:
            if child.is_dir() and (child / "audits").exists():
                present_markets.add(child.name.lower())

    # Synthesize rows from completed MTM audits missing in summary.csv
    expected_markets = list(want) if want else sorted(present_markets)
    for m in expected_markets:
        for v in expected_variants:
            if (m, v) in seen_keys:
                continue
            audit_p = _audit_path(hub, m, v)
            parsed = _parse_mtm_audit(audit_p)
            if not parsed:
                continue
            present_markets.add(m)
            seen_keys.add((m, v))
            ev = evaluate_row_eligibility(
                parsed,
                market=m,
                variant=v,
                audit_ok=True,
                usd_norm=usd_map.get(m),
                lot_correct=lot_map.get((m, v)),
            )
            evaluations.append(ev)
            entry = by_market.setdefault(
                m, {"market": m, "variants": {}, "exceptions": []}
            )
            entry["variants"][v] = ev
            if ev["exclusion_reasons"]:
                entry["exceptions"].extend(
                    "%s: %s" % (v, "; ".join(ev["exclusion_reasons"]))
                )

    incomplete_jobs: List[Dict[str, Any]] = []
    for m in expected_markets:
        present = set((by_market.get(m) or {}).get("variants") or {})
        missing = [v for v in expected_variants if v not in present]
        # Also treat present-but-incomplete
        for v in present:
            ev = by_market[m]["variants"][v]
            if ev["decision_label"] == LABEL_INCOMPLETE:
                incomplete_jobs.append(
                    {
                        "market": m,
                        "variant": v,
                        "reason": "incomplete_audit_or_units",
                    }
                )
        for v in missing:
            incomplete_jobs.append(
                {"market": m, "variant": v, "reason": "missing_from_summary"}
            )

    active = scan_active_jobs(worker_patterns)
    active = _filter_active_jobs_for_hub(hub, active, expected_markets)

    required = []
    for m in expected_markets:
        for v in expected_variants:
            required.append((m, v))
    completed_required = 0
    for m, v in required:
        ev = ((by_market.get(m) or {}).get("variants") or {}).get(v)
        if ev and ev["decision_label"] not in {LABEL_INCOMPLETE} and ev.get("audit_ok"):
            # Count as complete job if in summary with audit (indef research ok)
            if ev["metrics"]["units"]:
                completed_required += 1

    total_required = len(required)
    complete_flag = (not active) and (not incomplete_jobs) and (
        completed_required >= total_required if total_required else bool(evaluations)
    )

    if active:
        status = STATUS_IN_PROGRESS
    elif incomplete_jobs and evaluations:
        status = STATUS_PARTIAL
    elif complete_flag:
        status = STATUS_COMPLETE
    elif not evaluations:
        status = STATUS_FAILED
    else:
        status = STATUS_PARTIAL

    boards = _partition_boards(evaluations)
    sleeve_warn = duplicate_sleeve_warnings(
        sorted(present_markets), strategy="st_pmc", book="mixed"
    )

    decision_summary = _decision_counts(evaluations)
    blocks = _blocks_final_judgment(status, incomplete_jobs, active, evaluations)
    portfolio_action = _portfolio_action(sleeve_warn, blocks, status)

    change = compare_snapshots(prior, None)  # placeholder; filled after assemble
    snap: Dict[str, Any] = {
        "schema": "potions.hub_snapshot.v1",
        "hub": str(hub.relative_to(REPO)) if str(hub).startswith(str(REPO)) else str(hub),
        "status": status,
        "complete": complete_flag,
        "generated_at_utc": _utc_now(),
        "completed_required_jobs": completed_required,
        "total_required_jobs": total_required,
        "active_jobs": [
            {
                "market": j.get("market") or "?",
                "variant": j.get("variant") or "?",
                "status": j.get("status"),
                "progress": j.get("progress"),
                "pid": j.get("pid"),
                "command": j.get("command"),
            }
            for j in active
        ],
        "incomplete_jobs": incomplete_jobs,
        "accounting_mode": "lot-correct-preferred",
        "currency_note": (
            "JPY pairs need USD normalization before cross-market N/S boards"
        ),
        "has_fair_3r_usd_normalized": bool(usd_map) or (hub / "FAIR_3R_USD_NORMALIZED.md").exists(),
        "decision_summary": decision_summary,
        "blocks_final_judgment": blocks,
        "portfolio_action_required": portfolio_action,
        "duplicate_sleeve_warnings": sleeve_warn,
        "boards": boards,
        "markets": by_market,
        "evaluations": evaluations,
        "change_since_prior_snapshot": [],
    }
    snap["change_since_prior_snapshot"] = compare_snapshots(prior, snap)
    return snap


def _partition_boards(evaluations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    core = [e for e in evaluations if e["comparable_core_eligible"]]
    # Tested / Not Promoted: eligible RETAIN rows awaiting human promote, plus
    # any explicit REJECT / complete-but-not-promoted non-indef evaluations.
    tested = [
        e
        for e in evaluations
        if "indef" not in e["variant"]
        and e["decision_label"]
        in {LABEL_RETAIN, LABEL_REJECT, LABEL_RESEARCH}
    ]
    pending = [
        e
        for e in evaluations
        if e["decision_label"]
        in {
            LABEL_PENDING_NORM,
            LABEL_PENDING_ACCT,
            LABEL_INSUFFICIENT,
            LABEL_INCOMPLETE,
            LABEL_NOT_RANKABLE,
        }
        and "indef" not in e["variant"]
    ]
    indef = [e for e in evaluations if "indef" in e["variant"]]
    # Sort core by N/S desc
    core_sorted = sorted(
        core, key=lambda e: -(e["metrics"].get("ns") or 0.0)
    )
    tested_sorted = sorted(
        tested, key=lambda e: -(e["metrics"].get("ns") or 0.0)
    )
    return {
        "comparable_core_board": {
            "title": "Comparable Core Board",
            "rankable": bool(core_sorted),
            "rows": core_sorted,
        },
        "tested_not_promoted": {
            "title": "Tested / Not Promoted",
            "rankable": False,
            "rows": tested_sorted,
        },
        "pending_non_comparable": {
            "title": "Pending / Non-Comparable",
            "rankable": False,
            "rows": pending,
        },
        "indefinite_inventory_research": {
            "title": "INDEFINITE INVENTORY RESEARCH — NOT RANKABLE",
            "rankable": False,
            "rows": indef,
        },
    }


def _decision_counts(evaluations: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {k: [] for k in (
        LABEL_PROMOTE,
        LABEL_RETAIN,
        LABEL_RESEARCH,
        LABEL_REJECT,
        LABEL_PENDING_NORM,
        LABEL_PENDING_ACCT,
        LABEL_INSUFFICIENT,
        LABEL_INCOMPLETE,
        LABEL_NOT_RANKABLE,
    )}
    for e in evaluations:
        key = "%s %s" % (e["market"].upper(), e["book_label"])
        out.setdefault(e["decision_label"], []).append(key)
    return out


def _blocks_final_judgment(
    status: str,
    incomplete: Sequence[dict],
    active: Sequence[dict],
    evaluations: Sequence[dict],
) -> List[str]:
    blocks = []
    if status != STATUS_COMPLETE:
        blocks.append("hub_status=%s" % status)
    if active:
        blocks.append("%d_active_jobs" % len(active))
    if incomplete:
        blocks.append("%d_incomplete_jobs" % len(incomplete))
    pending_norm = [
        e for e in evaluations if e["decision_label"] == LABEL_PENDING_NORM
    ]
    if pending_norm:
        blocks.append(
            "usd_normalization_pending:%s"
            % ",".join(sorted({e["market"] for e in pending_norm}))
        )
    pending_acct = [
        e for e in evaluations if e["decision_label"] == LABEL_PENDING_ACCT
    ]
    if pending_acct:
        blocks.append("lot_correct_accounting_pending")
    return blocks


def _portfolio_action(
    sleeve_warn: Sequence[dict], blocks: Sequence[str], status: str
) -> Dict[str, Any]:
    actions = []
    for w in sleeve_warn:
        actions.append(w.get("message") or w.get("warning"))
    if status != STATUS_COMPLETE:
        actions.append("No final promotion until required jobs finish.")
    if any("usd_normalization" in b for b in blocks):
        actions.append("Normalize JPY results before cross-market ranking.")
    return {
        "required": bool(actions),
        "actions": actions,
    }


def compare_snapshots(
    prior: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]
) -> List[str]:
    """Human-readable change lines vs immediately preceding snapshot."""
    if not current:
        return ["= No current snapshot"]
    if not prior:
        return ["+ Initial snapshot (no prior)"]

    lines: List[str] = []
    prev_done = {
        (e["market"], e["variant"])
        for e in prior.get("evaluations") or []
        if e.get("audit_ok") and (e.get("metrics") or {}).get("units")
    }
    cur_done = {
        (e["market"], e["variant"])
        for e in current.get("evaluations") or []
        if e.get("audit_ok") and (e.get("metrics") or {}).get("units")
    }
    newly = sorted(cur_done - prev_done)
    # Group by market for 2R→10R + indef completions
    by_m: Dict[str, List[str]] = {}
    for m, v in newly:
        by_m.setdefault(m, []).append(VARIANT_LABEL.get(v, v))
    for m, labs in sorted(by_m.items()):
        lines.append("+ %s %s completed" % (m.upper(), " and ".join(labs)))

    prev_promote = set((prior.get("decision_summary") or {}).get(LABEL_PROMOTE) or [])
    cur_promote = set((current.get("decision_summary") or {}).get(LABEL_PROMOTE) or [])
    if cur_promote - prev_promote:
        for p in sorted(cur_promote - prev_promote):
            lines.append("+ Promoted: %s" % p)
    else:
        lines.append("= No new promoted strategy")

    active = current.get("active_jobs") or []
    if active:
        mkts = sorted(
            {
                (j.get("market") or "?").upper()
                for j in active
                if j.get("market") and not str(j.get("market")).startswith("$")
            }
        )
        if mkts:
            lines.append("! %s runner variants still active" % "/".join(mkts))
        else:
            lines.append("! %d worker(s) still active" % len(active))

    prev_status = prior.get("status")
    cur_status = current.get("status")
    if prev_status != cur_status:
        lines.append("~ status %s → %s" % (prev_status, cur_status))

    if not lines:
        lines.append("= No material change")
    return lines


def load_prior_snapshot(hub: Path) -> Optional[Dict[str, Any]]:
    """Load the immediately preceding snapshot (not the one about to be overwritten)."""
    snap_dir = hub / "snapshots"
    latest = hub / "LATEST_SNAPSHOT.json"
    if snap_dir.exists():
        files = sorted(snap_dir.glob("SNAPSHOT_*.json"))
        # LATEST equals newest archived file; prior is the second-newest.
        if len(files) >= 2:
            try:
                return json.loads(files[-2].read_text(encoding="utf-8"))
            except Exception:
                pass
        elif len(files) == 1 and not latest.exists():
            try:
                return json.loads(files[0].read_text(encoding="utf-8"))
            except Exception:
                pass
    if latest.exists():
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            return None
    status = hub / "STATUS.json"
    if status.exists():
        try:
            return json.loads(status.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def write_snapshot_artifacts(
    hub: Path, snap: Dict[str, Any], *, email: bool = False
) -> Dict[str, Path]:
    hub.mkdir(parents=True, exist_ok=True)
    snap_dir = hub / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    stamp = (
        str(snap.get("generated_at_utc") or _utc_now())
        .replace(":", "")
        .replace("+00:00", "Z")
    )
    paths: Dict[str, Path] = {}

    # Machine-readable
    latest = hub / "LATEST_SNAPSHOT.json"
    archived = snap_dir / ("SNAPSHOT_%s.json" % stamp)
    blob = json.dumps(snap, indent=2, sort_keys=True) + "\n"
    latest.write_text(blob, encoding="utf-8")
    archived.write_text(blob, encoding="utf-8")
    paths["latest_snapshot"] = latest
    paths["archived_snapshot"] = archived

    # Also refresh STATUS.json / RUN_COMPLETE.json compatibility shim
    compat = _compat_run_complete(snap)
    (hub / "STATUS.json").write_text(
        json.dumps(compat, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (hub / "RUN_COMPLETE.json").write_text(
        json.dumps(compat, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["status"] = hub / "STATUS.json"

    # Change log
    change_path = hub / "SNAPSHOT_CHANGELOG.txt"
    change_lines = [
        "CHANGE SINCE PRIOR SNAPSHOT",
        "generated_at_utc=%s status=%s" % (snap["generated_at_utc"], snap["status"]),
        "",
    ] + list(snap.get("change_since_prior_snapshot") or [])
    change_path.write_text("\n".join(change_lines) + "\n", encoding="utf-8")
    paths["changelog"] = change_path

    # Email + markdown
    email_body = render_email(snap)
    email_path = hub / "COMPLETION_EMAIL.txt"
    email_path.write_text(email_body, encoding="utf-8")
    paths["email"] = email_path

    md = render_markdown_report(snap)
    md_path = hub / "COMPLETION_REPORT.md"
    md_path.write_text(md, encoding="utf-8")
    paths["report"] = md_path

    if email:
        from .notify_email import send_email

        subject = _email_subject(snap)
        send_email(subject=subject, body=email_body)
    return paths


def _compat_run_complete(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible STATUS/RUN_COMPLETE shape."""
    markets = {}
    for m, entry in (snap.get("markets") or {}).items():
        variants = {}
        for v, ev in (entry.get("variants") or {}).items():
            metrics = ev.get("metrics") or {}
            variants[v] = {
                "class": str(ev.get("decision_label") or "").lower(),
                "net_usd": metrics.get("net_usd"),
                "stress_dd_usd": metrics.get("stress_dd_usd"),
                "ns": metrics.get("ns"),
                "units": metrics.get("units"),
                "wr_pct": metrics.get("wr_pct"),
                "max_open": metrics.get("max_open"),
                "eoy_flatten_units": metrics.get("eoy_open_lots"),
                "audit_ok": ev.get("audit_ok"),
                "rankable": ev.get("comparable_core_eligible"),
                "exclusion_reasons": ev.get("exclusion_reasons"),
                "metric_source": metrics.get("metric_source"),
            }
        markets[m] = {
            "market": m,
            "variants": variants,
            "exceptions": entry.get("exceptions") or [],
        }
    return {
        "hub": snap.get("hub"),
        "generated_at": snap.get("generated_at_utc"),
        "generated_at_utc": snap.get("generated_at_utc"),
        "status": snap.get("status"),
        "complete": snap.get("complete"),
        "completed_required_jobs": snap.get("completed_required_jobs"),
        "total_required_jobs": snap.get("total_required_jobs"),
        "accounting_mode": snap.get("accounting_mode"),
        "currency_note": snap.get("currency_note"),
        "has_fair_3r_usd_normalized": snap.get("has_fair_3r_usd_normalized"),
        "active_jobs": snap.get("active_jobs"),
        "incomplete_jobs": snap.get("incomplete_jobs"),
        "workers_still_running": [
            "%(market)s %(variant)s pid=%(pid)s" % j
            for j in (snap.get("active_jobs") or [])
        ],
        "incomplete_markets": _incomplete_markets_compat(snap),
        "decision_summary": snap.get("decision_summary"),
        "blocks_final_judgment": snap.get("blocks_final_judgment"),
        "change_since_prior_snapshot": snap.get("change_since_prior_snapshot"),
        "duplicate_sleeve_warnings": snap.get("duplicate_sleeve_warnings"),
        "markets": markets,
        "snapshot_schema": snap.get("schema"),
    }


def _incomplete_markets_compat(snap: Dict[str, Any]) -> List[dict]:
    by: Dict[str, List[str]] = {}
    for j in snap.get("incomplete_jobs") or []:
        if j.get("reason") == "missing_from_summary":
            by.setdefault(j["market"], []).append(j["variant"])
    return [{"market": m, "missing_variants": vs} for m, vs in sorted(by.items())]


def _email_subject(snap: Dict[str, Any]) -> str:
    hub = str(snap.get("hub") or "hub").rstrip("/").split("/")[-1]
    st = snap.get("status")
    if st == STATUS_COMPLETE and snap.get("complete"):
        kind = "completion"
    elif st == STATUS_IN_PROGRESS:
        kind = "IN PROGRESS snapshot"
    else:
        kind = "INTERIM SNAPSHOT"
    n = snap.get("completed_required_jobs"), snap.get("total_required_jobs")
    return "potions: %s %s — %s/%s jobs" % (hub, kind, n[0], n[1])


def render_email(snap: Dict[str, Any]) -> str:
    st = snap.get("status")
    is_final = st == STATUS_COMPLETE and snap.get("complete")
    title = (
        "COMPLETION REPORT"
        if is_final
        else ("IN PROGRESS SNAPSHOT" if st == STATUS_IN_PROGRESS else "INTERIM SNAPSHOT")
    )
    lines = [
        title,
        "status: %s" % st,
        "generated_at_utc: %s" % snap.get("generated_at_utc"),
        "completed_required_jobs: %s / %s"
        % (snap.get("completed_required_jobs"), snap.get("total_required_jobs")),
        "accounting_mode: %s" % snap.get("accounting_mode"),
        "",
        "CHANGE SINCE PRIOR SNAPSHOT",
    ]
    for c in snap.get("change_since_prior_snapshot") or []:
        lines.append(c)
    lines += ["", "DECISION STATE"]
    ds = snap.get("decision_summary") or {}
    for lab in (
        LABEL_PROMOTE,
        LABEL_RETAIN,
        LABEL_RESEARCH,
        LABEL_REJECT,
        LABEL_PENDING_NORM,
        LABEL_PENDING_ACCT,
        LABEL_INSUFFICIENT,
        LABEL_INCOMPLETE,
        LABEL_NOT_RANKABLE,
    ):
        items = ds.get(lab) or []
        if items:
            lines.append("%s (%d): %s" % (lab, len(items), ", ".join(items[:12])))
            if len(items) > 12:
                lines.append("  … +%d more" % (len(items) - 12))
    lines += ["", "BLOCKS FINAL JUDGMENT"]
    blocks = snap.get("blocks_final_judgment") or []
    if blocks:
        for b in blocks:
            lines.append("- %s" % b)
    else:
        lines.append("- none")
    pa = snap.get("portfolio_action_required") or {}
    lines += ["", "PORTFOLIO ACTION REQUIRED: %s" % ("YES" if pa.get("required") else "no")]
    for a in pa.get("actions") or []:
        lines.append("- %s" % a)

    # Active jobs (concise — no PIDs/commands)
    active = snap.get("active_jobs") or []
    lines += ["", "Active jobs: %d" % len(active)]
    for j in active:
        prog = j.get("progress") or j.get("status") or "running"
        lines.append(
            "- %s: %s, %s"
            % (
                (j.get("market") or "?").upper(),
                VARIANT_LABEL.get(j.get("variant") or "", j.get("variant") or "?"),
                prog,
            )
        )
    incomplete = snap.get("incomplete_jobs") or []
    if incomplete:
        lines += ["", "Incomplete jobs: %d" % len(incomplete)]
        for j in incomplete[:12]:
            lines.append(
                "- %s %s (%s)"
                % (
                    j.get("market", "").upper(),
                    VARIANT_LABEL.get(j.get("variant") or "", j.get("variant")),
                    j.get("reason"),
                )
            )

    boards = snap.get("boards") or {}
    core = (boards.get("comparable_core_board") or {}).get("rows") or []
    lines += ["", "COMPARABLE CORE BOARD (rankable only if all gates pass)"]
    if not core:
        lines.append("(empty — no row passed eligibility gates)")
    else:
        for i, e in enumerate(core[:15], 1):
            m = e["metrics"]
            lines.append(
                "%d. %s %s  N/S=%s net=%s stress=%s  [%s] src=%s"
                % (
                    i,
                    e["market"].upper(),
                    e["book_label"],
                    ("%.2f" % m["ns"]) if m.get("ns") is not None else "?",
                    _money(m.get("net_usd")),
                    _money(m.get("stress_dd_usd")),
                    e["decision_label"],
                    m.get("metric_source"),
                )
            )

    tested = (boards.get("tested_not_promoted") or {}).get("rows") or []
    if tested:
        lines += ["", "TESTED / NOT PROMOTED (awaiting human promote)"]
        for e in tested[:10]:
            m = e["metrics"]
            lines.append(
                "- %s %s N/S=%s [%s]"
                % (
                    e["market"].upper(),
                    e["book_label"],
                    ("%.2f" % m["ns"]) if m.get("ns") is not None else "?",
                    e["decision_label"],
                )
            )

    indef = (boards.get("indefinite_inventory_research") or {}).get("rows") or []
    if indef:
        lines += ["", "INDEFINITE INVENTORY RESEARCH — NOT RANKABLE"]
        for e in indef:
            m = e["metrics"]
            if m.get("lot_correct_available") and m.get("forced_flat_net_pnl") is not None:
                ff = _money(m.get("forced_flat_net_pnl"))
                rs = _money(m.get("reachable_full_stack_stress") or m.get("stress_dd_usd"))
                src = "lot-correct"
            else:
                ff = "pending"
                rs = "pending"
                src = "raw_archive_not_eligible"
            lines.append(
                "%s  forced-flat=%s | reachable stress=%s | max inv=%s | EOY open=%s | margin=%s  [%s] (%s)"
                % (
                    e["market"].upper(),
                    ff,
                    rs,
                    m.get("max_open"),
                    m.get("eoy_open_lots"),
                    _money(m.get("max_gross_notional")) if m.get("max_gross_notional") else "n/a",
                    e["decision_label"],
                    src,
                )
            )
            # Optional raw diagnostic (explicitly labeled, never as forced-flat)
            if not m.get("lot_correct_available") and m.get("raw_net_usd") is not None:
                lines.append(
                    "  raw/archive (not forced-flat): net=%s stress=%s"
                    % (_money(m.get("raw_net_usd")), _money(m.get("raw_stress_dd_usd")))
                )

    pending = (boards.get("pending_non_comparable") or {}).get("rows") or []
    if pending:
        lines += ["", "PENDING / NON-COMPARABLE"]
        for e in pending[:10]:
            lines.append(
                "- %s %s [%s]: %s"
                % (
                    e["market"].upper(),
                    e["book_label"],
                    e["decision_label"],
                    "; ".join(e.get("exclusion_reasons") or []) or "n/a",
                )
            )

    for w in snap.get("duplicate_sleeve_warnings") or []:
        lines += ["", "DUPLICATE SLEEVE: %s" % w.get("message")]

    attr = snap.get("exit_attribution") or []
    if attr:
        lines += ["", "EXIT ATTRIBUTION (10R / EOD-survivor)"]
        for a in attr[:8]:
            lines.append(
                "- %s [%s]: true_10R_hits=%s (%.1f%%) share=%.0f%% → %s"
                % (
                    (a.get("market") or a.get("strategy_id") or "?").upper(),
                    a.get("book_label"),
                    a.get("true_10r_target_hits"),
                    float(a.get("true_10r_target_hit_pct") or 0),
                    100.0 * float(a.get("true_10r_pnl_share") or 0),
                    "10R moonshot" if a.get("is_10r_moonshot") else "EOD-survivor / mixed",
                )
            )

    lines += [
        "",
        "Hub: %s" % snap.get("hub"),
        "Report: COMPLETION_REPORT.md",
        "Snapshot: LATEST_SNAPSHOT.json",
        "",
        "Note: PID/host/command live in hub status JSON only.",
    ]
    return "\n".join(lines) + "\n"


def render_markdown_report(snap: Dict[str, Any]) -> str:
    st = snap.get("status")
    is_final = st == STATUS_COMPLETE and snap.get("complete")
    title = "Completion report" if is_final else "Interim snapshot report"
    lines = [
        "# %s — %s" % (title, snap.get("hub")),
        "",
        "| field | value |",
        "|---|---|",
        "| status | **%s** |" % st,
        "| generated_at_utc | %s |" % snap.get("generated_at_utc"),
        "| completed_required_jobs | %s / %s |"
        % (snap.get("completed_required_jobs"), snap.get("total_required_jobs")),
        "| accounting_mode | %s |" % snap.get("accounting_mode"),
        "| complete | %s |" % snap.get("complete"),
        "",
        "## Change since prior snapshot",
        "",
    ]
    for c in snap.get("change_since_prior_snapshot") or []:
        lines.append("- `%s`" % c)

    lines += ["", "## Decision summary", ""]
    ds = snap.get("decision_summary") or {}
    for lab, items in ds.items():
        if items:
            lines.append("- **%s**: %s" % (lab, ", ".join(items)))

    lines += ["", "### Blocks final judgment", ""]
    for b in snap.get("blocks_final_judgment") or ["none"]:
        lines.append("- %s" % b)

    pa = snap.get("portfolio_action_required") or {}
    lines += ["", "### Portfolio action", ""]
    if pa.get("required"):
        for a in pa.get("actions") or []:
            lines.append("- %s" % a)
    else:
        lines.append("- none")

    boards = snap.get("boards") or {}
    lines += _md_board(boards.get("comparable_core_board"))
    lines += _md_board(boards.get("tested_not_promoted"))
    lines += _md_board(boards.get("pending_non_comparable"))
    lines += _md_indef_board(boards.get("indefinite_inventory_research"))

    lines += [
        "",
        "## Diagnostics",
        "",
        "- Active jobs (detail in `LATEST_SNAPSHOT.json`): **%d**"
        % len(snap.get("active_jobs") or []),
        "- Incomplete jobs: **%d**" % len(snap.get("incomplete_jobs") or []),
        "- Raw metrics remain in `summary.csv` / MTM audits; eligible metrics note `metric_source`.",
        "",
    ]
    for w in snap.get("duplicate_sleeve_warnings") or []:
        lines.append("- **Duplicate sleeve:** %s" % w.get("message"))

    attr = snap.get("exit_attribution") or []
    if attr:
        lines += [
            "",
            "## Exit attribution (10R / EOD-survivor)",
            "",
            "| market / id | book label | TP1 | TP2 | hard stop | BE stop | EOD | true 10R | 10R hits | moonshot? |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for a in attr:
            pnl = a.get("pnl_by_exit") or {}
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s | %s | %s (%.1f%%) | %s |"
                % (
                    a.get("market") or a.get("strategy_id"),
                    a.get("book_label"),
                    _money(pnl.get("tp1")),
                    _money(pnl.get("tp2")),
                    _money(pnl.get("hard_stop")),
                    _money(pnl.get("break_even_stop")),
                    _money(pnl.get("eod_mark")),
                    _money(pnl.get("true_10r_target")),
                    a.get("true_10r_target_hits"),
                    float(a.get("true_10r_target_hit_pct") or 0),
                    "yes" if a.get("is_10r_moonshot") else "no",
                )
            )

    lines += [
        "",
        "## Artifacts",
        "",
        "- `LATEST_SNAPSHOT.json`, `snapshots/SNAPSHOT_*.json`",
        "- `COMPLETION_EMAIL.txt`, `SNAPSHOT_CHANGELOG.txt`",
        "- `STATUS.json` / `RUN_COMPLETE.json` (compat shim)",
        "",
    ]
    return "\n".join(lines) + "\n"


def _md_board(board: Optional[Dict[str, Any]]) -> List[str]:
    if not board:
        return []
    lines = [
        "",
        "## %s" % board.get("title"),
        "",
        "Rankable: **%s**" % ("yes" if board.get("rankable") and board.get("rows") else "no"),
        "",
        "| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for e in board.get("rows") or []:
        m = e["metrics"]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                e["market"],
                e["book_label"],
                _money(m.get("net_usd")),
                _money(m.get("stress_dd_usd")),
                ("%.2f" % m["ns"]) if m.get("ns") is not None else "",
                m.get("units"),
                m.get("max_open"),
                m.get("eoy_open_lots"),
                e["decision_label"],
                m.get("metric_source"),
                "; ".join(e.get("exclusion_reasons") or []) or "—",
            )
        )
    if not board.get("rows"):
        lines.append("| — | — | | | | | | | | | empty |")
    return lines


def _md_indef_board(board: Optional[Dict[str, Any]]) -> List[str]:
    if not board:
        return []
    lines = [
        "",
        "## %s" % board.get("title"),
        "",
        "Headline: Forced-flat net | reachable full-stack stress | max inventory | EOY open lots | margin",
        "",
        "Forced-flat / reachable figures appear only from `LOT_CORRECT_ACCOUNTING.csv`. Raw archive nets are labeled separately and are not eligible.",
        "",
        "| market | forced-flat | reachable stress | max inv | EOY | margin | MTM (sep) | hold med/p90 h | label | source |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for e in board.get("rows") or []:
        m = e["metrics"]
        lot_ok = m.get("lot_correct_available")
        ff = (
            _money(m.get("forced_flat_net_pnl"))
            if lot_ok and m.get("forced_flat_net_pnl") is not None
            else "pending"
        )
        rs = (
            _money(m.get("reachable_full_stack_stress") or m.get("stress_dd_usd"))
            if lot_ok
            else "pending"
        )
        hold = ""
        if m.get("hold_hours_median") is not None:
            hold = "%.0f / %.0f" % (
                m.get("hold_hours_median") or 0,
                m.get("hold_hours_p90") or 0,
            )
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                e["market"],
                ff,
                rs,
                m.get("max_open"),
                m.get("eoy_open_lots"),
                _money(m.get("max_gross_notional")) if m.get("max_gross_notional") else "n/a",
                _money(m.get("mark_to_market_net_pnl")) if m.get("mark_to_market_net_pnl") is not None else "—",
                hold or "—",
                e["decision_label"],
                m.get("metric_source"),
            )
        )
        if not lot_ok and m.get("raw_net_usd") is not None:
            lines.append(
                "| %s | raw/archive net %s | raw stress %s | | | | | | (not forced-flat) | summary.csv_raw |"
                % (
                    e["market"],
                    _money(m.get("raw_net_usd")),
                    _money(m.get("raw_stress_dd_usd")),
                )
            )
    return lines


def maybe_attach_exit_attribution(hub: Path, snap: Dict[str, Any]) -> None:
    """If hub looks like a plus-1x10R book, attach attribution section."""
    if "10r" not in str(hub).lower() and "plus_1x10" not in str(hub).lower():
        return
    rows = attribute_hub_unit_trades(hub)
    if not rows:
        return
    snap["exit_attribution"] = rows
    snap["duplicate_sleeve_warnings"] = list(snap.get("duplicate_sleeve_warnings") or [])
    snap["duplicate_sleeve_warnings"].extend(
        duplicate_sleeve_warnings(
            [r.get("market") for r in rows if r.get("market")],
            strategy="v2b_prior_opposed",
            book="S_1_1_3_plus_1x10R",
        )
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hub",
        default="live/state/fx_index_metals_st_pmc_runner_variants",
    )
    ap.add_argument("--markets", nargs="*", default=None)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--json", action="store_true", help="Print snapshot JSON")
    ap.add_argument("--require-complete", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub = _hub_path(args.hub)
    # Prior = current LATEST before overwrite
    prior = None
    latest = hub / "LATEST_SNAPSHOT.json"
    if latest.exists():
        try:
            prior = json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            prior = None
    elif (hub / "STATUS.json").exists():
        try:
            prior = json.loads((hub / "STATUS.json").read_text(encoding="utf-8"))
        except Exception:
            prior = None

    snap = build_snapshot(hub, markets=args.markets, prior=prior)
    maybe_attach_exit_attribution(hub, snap)

    if args.write or args.email:
        paths = write_snapshot_artifacts(hub, snap, email=args.email)
        for k, p in paths.items():
            print("Wrote %s -> %s" % (k, p), flush=True)
        print(
            "status=%s complete=%s subject_kind=%s"
            % (snap["status"], snap["complete"], _email_subject(snap)),
            flush=True,
        )
    elif args.json:
        print(json.dumps(snap, indent=2, sort_keys=True))
    else:
        print(render_email(snap))

    if args.require_complete and not snap.get("complete"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
