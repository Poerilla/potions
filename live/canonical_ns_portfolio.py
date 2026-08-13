"""Phase 4 — portfolio N/S under HOLD_ONE sleeve / prior-opposed HP gates.

Builds admissible portfolios from the canonical N/S ledger (no signal regen).

Score::

    Portfolio N/S = sum(sleeve forced-flat nets) / |sum(sleeve reachable stresses)|

Joint stress here is a **conservative additive upper bound** (absolute stresses
summed). Campaign-aligned joint MTM remains the overlap driver's job for
simultaneous HP clearance.

Constraints:

- one book per economic sleeve / HOLD_ONE group (NQ/MNQ, YM/MYM, ES/MES, …)
- at most one prior-opposed HP size-up across ES/YM/NQ
- size-ups admitted only when null decision is SIZE-UP VALIDATED or
  PROVISIONAL / BORDERLINE PAPER

Hub::

    live/state/canonical_ns_research/portfolio/

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.canonical_ns_portfolio --email
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .canonical_ns_research import HUB as NS_HUB, SLEEVE_MAP
from .fx_v2b_london_ungated import REPO
from .notify_email import send_email

PORT_HUB = NS_HUB / "portfolio"
PRIOR_OPPOSED_BOOKS = {
    "nq_prior_opposed_rl",
    "es_prior_opposed_legacy",
    "ym_prior_opposed_rl",
}
ADMIT_DECISIONS = {
    "SIZE-UP VALIDATED",
    "PROVISIONAL PAPER",
    "BORDERLINE PAPER",
}


def _progress(msg: str) -> None:
    PORT_HUB.mkdir(parents=True, exist_ok=True)
    with (PORT_HUB / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        pass


def _safe(x: Any, default: float = float("nan")) -> float:
    try:
        v = float(x)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _decision_from_notes(notes: str) -> str:
    m = re.search(r"decision=([A-Z0-9 _/-]+)", str(notes or ""))
    if not m:
        return ""
    return m.group(1).strip().split(" p_master")[0].strip()


def _hold_one_group(market: str) -> str:
    m = str(market).upper()
    for r in SLEEVE_MAP:
        if r["market"] == m:
            return str(r["hold_one_group"])
    return m


def load_ledger(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["hold_one"] = df["market"].map(_hold_one_group)
    df["decision"] = df["notes"].map(_decision_from_notes)
    return df


def select_core_baselines(ledger: pd.DataFrame) -> pd.DataFrame:
    """Best rankable baseline/filter per HOLD_ONE group (finite core)."""
    core = ledger[
        (ledger["rankable"] == True)  # noqa: E712
        & (ledger["candidate_type"].isin(["baseline", "filter"]))
        & (ledger["finite"] == True)  # noqa: E712
        & (ledger["inventory"] == False)  # noqa: E712
        & (ledger["USD_normalized"] == True)  # noqa: E712
        & (ledger["strategy_family"] != "prior_opposed_10r")
    ].copy()
    if core.empty:
        return core
    core = core.sort_values("candidate_NS", ascending=False)
    return core.groupby("hold_one", as_index=False).first()


def select_admitted_overlays(ledger: pd.DataFrame) -> pd.DataFrame:
    ov = ledger[
        (ledger["candidate_type"] == "size_up")
        & (ledger["delta_NS"].notna())
        & (ledger["source_hub"].astype(str).str.contains("nulls", na=False))
    ].copy()
    if ov.empty:
        return ov
    ov = ov[ov["decision"].isin(ADMIT_DECISIONS)].copy()
    # Prefer exact null-validated multipliers; drop sensitivity ladder source.
    ov = ov.sort_values(["delta_NS"], ascending=False)
    ov = ov.drop_duplicates(
        subset=["book_id", "condition_set", "multiplier"], keep="first"
    )
    return ov


def portfolio_metrics(rows: Sequence[pd.Series]) -> Dict[str, float]:
    nets = [_safe(r["candidate_net"], 0.0) for r in rows]
    stresses = [abs(_safe(r["candidate_reachable_stress"], 0.0)) for r in rows]
    net = float(sum(nets))
    stress = float(sum(stresses))
    ns = net / stress if stress > 1e-9 else float("nan")
    return {"net": net, "stress": stress, "ns": ns, "n_sleeves": float(len(rows))}


def enumerate_portfolios(
    baselines: pd.DataFrame,
    overlays: pd.DataFrame,
    *,
    max_overlays: int = 2,
) -> List[Dict[str, Any]]:
    """Enumerate HOLD_ONE-legal portfolios of core sleeves ± admitted overlays."""
    results: List[Dict[str, Any]] = []
    base_rows = [baselines.iloc[i] for i in range(len(baselines))]
    base_m = portfolio_metrics(base_rows)
    results.append(
        {
            "label": "core_baselines_only",
            "overlays": "",
            "prior_opposed_hp_n": 0,
            "hold_one_ok": True,
            **base_m,
            "delta_NS_vs_core": 0.0,
            "notes": "finite core sleeves only (one per HOLD_ONE group)",
        }
    )

    ov_list = [overlays.iloc[i] for i in range(len(overlays))]
    for k in range(1, min(max_overlays, len(ov_list)) + 1):
        for combo in itertools.combinations(ov_list, k):
            ov_sleeves = [str(o["hold_one"]) for o in combo]
            if len(ov_sleeves) != len(set(ov_sleeves)):
                continue  # two overlays on same HOLD_ONE group
            # Sleeve uniqueness vs core + among overlays
            ok = True
            prior_n = 0
            labels = []
            for o in combo:
                if str(o["book_id"]) in PRIOR_OPPOSED_BOOKS:
                    prior_n += 1
                labels.append(
                    "%s@%.2f×(%s)"
                    % (o["book_id"], float(o["multiplier"]), o["decision"] or "?")
                )
            if prior_n > 1:
                ok = False
            # Rebuild sleeve set: start from baselines, replace overlapping hold_one
            used = {}
            for r in base_rows:
                used[str(r["hold_one"])] = r
            for o in combo:
                used[str(o["hold_one"])] = o
            rows = list(used.values())
            m = portfolio_metrics(rows)
            results.append(
                {
                    "label": "core+overlays",
                    "overlays": "; ".join(labels),
                    "prior_opposed_hp_n": prior_n,
                    "hold_one_ok": ok,
                    **m,
                    "delta_NS_vs_core": m["ns"] - base_m["ns"]
                    if math.isfinite(m["ns"]) and math.isfinite(base_m["ns"])
                    else float("nan"),
                    "notes": "HOLD_ONE enforced; additive stress upper bound"
                    if ok
                    else "REJECTED: >1 prior-opposed HP",
                }
            )
    return results


def write_summary(
    baselines: pd.DataFrame,
    overlays: pd.DataFrame,
    portfolios: pd.DataFrame,
) -> str:
    lines = [
        "# Canonical portfolio N/S (Phase 4)",
        "",
        "Hub: `live/state/canonical_ns_research/portfolio/`",
        "",
        "```text",
        "Portfolio N/S = sum(sleeve nets) / |sum(sleeve reachable stresses)|",
        "```",
        "",
        "Joint stress is a **conservative additive upper bound**. Simultaneous",
        "prior-opposed HP still requires the overlap gate",
        "(`HOLD_ONE_HP_PER_SESSION`) before stacking.",
        "",
        "## Constraints",
        "",
        "- One book per HOLD_ONE group (NQ/MNQ · YM/MYM · ES/MES · FX sleeves).",
        "- At most **one** prior-opposed HP size-up across ES/YM/NQ.",
        "- Overlays admitted only from null hubs with SIZE-UP VALIDATED /",
        "  PROVISIONAL PAPER / BORDERLINE PAPER.",
        "",
        "## Core baselines (one per HOLD_ONE)",
        "",
        "| hold_one | market | book | N/S | net | stress |",
        "|---|---|---|---:|---:|---:|",
    ]
    for _, r in baselines.sort_values("candidate_NS", ascending=False).iterrows():
        lines.append(
            "| %s | %s | %s | **%.2f** | %+.0f | %.0f |"
            % (
                r["hold_one"],
                r["market"],
                str(r["book_id"])[:40],
                _safe(r["candidate_NS"]),
                _safe(r["candidate_net"]),
                abs(_safe(r["candidate_reachable_stress"])),
            )
        )
    lines.extend(["", "## Admitted overlays", ""])
    if overlays.empty:
        lines.append("_None — no SIZE-UP VALIDATED / PROVISIONAL null survivors._")
    else:
        lines.append("| market | book | mult | ΔN/S | decision |")
        lines.append("|---|---|---:|---:|---|")
        for _, r in overlays.iterrows():
            lines.append(
                "| %s | %s | %.2f× | **%+.2f** | %s |"
                % (
                    r["market"],
                    str(r["book_id"])[:36],
                    float(r["multiplier"]),
                    _safe(r["delta_NS"]),
                    r["decision"],
                )
            )
    legal = portfolios[portfolios["hold_one_ok"] == True].copy()  # noqa: E712
    legal = legal.sort_values("ns", ascending=False)
    lines.extend(
        [
            "",
            "## Portfolio ranking (HOLD_ONE legal)",
            "",
            "| rank | net | stress | **N/S** | ΔN/S vs core | overlays |",
            "|---:|---:|---:|---:|---:|---|",
        ]
    )
    for i, (_, r) in enumerate(legal.head(15).iterrows(), 1):
        lines.append(
            "| %d | %+.0f | %.0f | **%.2f** | %+.2f | %s |"
            % (
                i,
                r["net"],
                r["stress"],
                r["ns"],
                r["delta_NS_vs_core"] if math.isfinite(r["delta_NS_vs_core"]) else 0.0,
                (r["overlays"] or "_(core only)_")[:70],
            )
        )
    best = legal.iloc[0] if len(legal) else None
    lines.extend(["", "## Stance", ""])
    if best is None:
        lines.append("No legal portfolios.")
    else:
        lines.append(
            "Best HOLD_ONE portfolio N/S **%.2f** (net %+.0f / stress %.0f)."
            % (best["ns"], best["net"], best["stress"])
        )
        if best["overlays"]:
            lines.append("Overlays: `%s`." % best["overlays"])
        else:
            lines.append("Best is core baselines only (no admitted overlay improved additive N/S, or none admitted).")
        lines.append(
            "Prior-opposed HP stacking remains blocked (`prior_opposed_hp_n≤1`); "
            "NQ OR-norm provisional @1.25×/@2× is the only futures HP overlay currently admissible."
        )
    lines.append("")
    return "\n".join(lines)


def run(*, email: bool = False) -> Path:
    PORT_HUB.mkdir(parents=True, exist_ok=True)
    (PORT_HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress("START canonical_ns_portfolio Phase 4")
    ledger_path = NS_HUB / "CANDIDATE_LEDGER.csv"
    if not ledger_path.exists():
        raise FileNotFoundError("missing %s — run live.canonical_ns_research first" % ledger_path)
    ledger = load_ledger(ledger_path)
    baselines = select_core_baselines(ledger)
    overlays = select_admitted_overlays(ledger)
    _progress(
        "baselines=%d overlays_admitted=%d" % (len(baselines), len(overlays))
    )
    ports = enumerate_portfolios(baselines, overlays, max_overlays=2)
    pdf = pd.DataFrame(ports)
    pdf.to_csv(PORT_HUB / "portfolios.csv", index=False)
    baselines.to_csv(PORT_HUB / "core_baselines.csv", index=False)
    overlays.to_csv(PORT_HUB / "admitted_overlays.csv", index=False)
    summary = write_summary(baselines, overlays, pdf)
    (PORT_HUB / "SUMMARY.md").write_text(summary, encoding="utf-8")

    legal = pdf[pdf["hold_one_ok"] == True].sort_values("ns", ascending=False)  # noqa: E712
    best = legal.iloc[0] if len(legal) else None
    body_lines = [
        "canonical_ns_portfolio Phase 4 complete",
        "hub: live/state/canonical_ns_research/portfolio/",
        "core baselines: %d" % len(baselines),
        "admitted overlays: %d" % len(overlays),
        "",
    ]
    if best is not None:
        body_lines.append(
            "Best HOLD_ONE Portfolio N/S=%.2f (net=%+.0f stress=%.0f)"
            % (best["ns"], best["net"], best["stress"])
        )
        body_lines.append("overlays: %s" % (best["overlays"] or "(core only)"))
        body_lines.append("ΔN/S vs core: %+.2f" % best["delta_NS_vs_core"])
    body_lines.extend(
        [
            "",
            "Stance: additive joint stress; HOLD_ONE prior-opposed HP.",
            "See SUMMARY.md.",
        ]
    )
    body = "\n".join(body_lines)
    (PORT_HUB / "EMAIL.txt").write_text(body + "\n", encoding="utf-8")
    (PORT_HUB / "RUN_COMPLETE.json").write_text(
        json.dumps(
            {
                "ok": True,
                "n_baselines": int(len(baselines)),
                "n_overlays": int(len(overlays)),
                "best_ns": float(best["ns"]) if best is not None else None,
                "hub": str(PORT_HUB),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _progress(
        "DONE best_ns=%s"
        % (("%.2f" % best["ns"]) if best is not None else "n/a")
    )
    if email:
        send_email(subject="potions: canonical_ns_portfolio Phase 4 complete", body=body)
    return PORT_HUB / "SUMMARY.md"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        run(email=bool(args.email))
    except Exception:
        tb = traceback.format_exc()
        _progress("CRASH\n" + tb)
        if args.email:
            send_email(
                subject="potions: canonical_ns_portfolio CRASH",
                body="hub=%s\n%s" % (PORT_HUB, tb[-2500:]),
            )
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
