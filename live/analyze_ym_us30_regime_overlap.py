"""YM prior-opposed vs US30 ST+PMC (and cross pairs): session overlap / correlation.

Compares NY-session entry dates + direction between:
  - YM prior-opposed resting-limit S_1_1_3
  - US30 ST+PMC fair 3R (50/150)
  - US30 prior-opposed (gambit)
  - YM ST+PMC fair 3R

Ideal for separate liquidity regimes: low same-day same-direction overlap.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from .notify_email import send_email
from .regime_overlap import book_identity, overlap_metrics

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "ym_us30_regime_overlap"


def _ny_day(ts: str) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        # assume already NY-naive wall
        return str(t.date())
    return str(t.tz_convert("America/New_York").date())


def _dir(d: str) -> str:
    return "L" if str(d).lower().startswith("l") else "S"


def _load_unit_trades(path: Path) -> List[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    # one row per campaign (first unit)
    by = {}
    for r in rows:
        tid = r["trade_id"]
        if tid not in by:
            by[tid] = {
                "trade_id": tid,
                "day": _ny_day(r["entry_ts"]),
                "dir": _dir(r["direction"]),
                "entry_ts": r["entry_ts"],
                "net_usd": 0.0,
            }
        by[tid]["net_usd"] += float(r.get("net_usd") or 0)
    return list(by.values())


def _load_st_pmc_campaigns(unit_fills: Path) -> List[dict]:
    rows = list(csv.DictReader(unit_fills.open(encoding="utf-8")))
    by = {}
    for r in rows:
        tid = r["trade_id"]
        if tid not in by:
            by[tid] = {
                "trade_id": tid,
                "day": _ny_day(r["entry_ts"]),
                "dir": _dir(r["direction"]),
                "entry_ts": r["entry_ts"],
                "net_usd": 0.0,
            }
        # unit_fills may have usd or points
        if r.get("usd") not in (None, ""):
            by[tid]["net_usd"] += float(r["usd"])
        elif r.get("points") not in (None, ""):
            # defer PV — store points for now in net_usd field tagged later
            by[tid]["net_usd"] += float(r["points"])
            by[tid]["points_mode"] = True
    return list(by.values())


def _day_dir_set(camps: Sequence[dict]) -> Set[Tuple[str, str]]:
    return {(c["day"], c["dir"]) for c in camps}


def _day_set(camps: Sequence[dict]) -> Set[str]:
    return {c["day"] for c in camps}


def _daily_net(camps: Sequence[dict]) -> Dict[str, float]:
    out: Dict[str, float] = defaultdict(float)
    for c in camps:
        out[c["day"]] += float(c["net_usd"])
    return dict(out)


def _corr(a: Dict[str, float], b: Dict[str, float]) -> Tuple[Optional[float], int]:
    keys = sorted(set(a) & set(b))
    if len(keys) < 5:
        return None, len(keys)
    xa = [a[k] for k in keys]
    xb = [b[k] for k in keys]
    ma = sum(xa) / len(xa)
    mb = sum(xb) / len(xb)
    num = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    da = math.sqrt(sum((x - ma) ** 2 for x in xa))
    db = math.sqrt(sum((y - mb) ** 2 for y in xb))
    if da < 1e-12 or db < 1e-12:
        return None, len(keys)
    return num / (da * db), len(keys)


def _overlap_stats(
    name_a: str,
    a: List[dict],
    name_b: str,
    b: List[dict],
    *,
    identity_a: Optional[dict] = None,
    identity_b: Optional[dict] = None,
) -> dict:
    """Delegate to four-class classifier (no Jaccard-OR-|ρ| separable rule)."""
    return overlap_metrics(
        name_a,
        a,
        name_b,
        b,
        identity_a=identity_a or book_identity(market="", strategy=name_a),
        identity_b=identity_b or book_identity(market="", strategy=name_b),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    st = REPO / "live" / "state"
    ym_po = _load_unit_trades(
        st
        / "ym_v2b_prior_opposed_stpmc_resting_limit"
        / "states"
        / "ym_v2b_prior_opposed_stpmc_only_S_1_1_3"
        / "unit_trades.csv"
    )
    us30_po = _load_unit_trades(
        st / "us30_futures_strats_sweep" / "states" / "us30_v2b_oco_prior_opposed_S_1_1_3" / "unit_trades.csv"
    )
    us30_st = _load_st_pmc_campaigns(
        st
        / "us30_st_pmc_runner_variants"
        / "audits_lot_correct"
        / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"
        / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct"
        / "unit_fills.csv"
    )
    # Convert US30 ST points → USD (PV=1)
    for c in us30_st:
        if c.pop("points_mode", False):
            pass  # already PV=1

    ym_st_path = (
        st
        / "futures_st_pmc_runner_variants"
        / "audits_lot_correct"
        / "ym_hourly_st_pmc_sl50_tp150_3r_1mfill"
        / "ym_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct"
        / "unit_fills.csv"
    )
    ym_st = _load_st_pmc_campaigns(ym_st_path) if ym_st_path.exists() else []
    for c in ym_st:
        if c.pop("points_mode", False):
            c["net_usd"] = c["net_usd"] * 5.0  # YM $5/pt

    id_ym_po = book_identity(
        market="ym",
        strategy="v2b_prior_opposed",
        version="stpmc_only",
        book="S_1_1_3",
        strategy_id="ym_v2b_prior_opposed_stpmc_only_S_1_1_3",
        hub="ym_v2b_prior_opposed_stpmc_resting_limit",
    )
    id_us30_po = book_identity(
        market="us30",
        strategy="v2b_prior_opposed",
        book="S_1_1_3",
        strategy_id="us30_v2b_oco_prior_opposed_S_1_1_3",
        hub="us30_futures_strats_sweep",
    )
    id_us30_st = book_identity(
        market="us30",
        strategy="st_pmc",
        book="sl50_tp150_3r_1mfill",
        strategy_id="us30_hourly_st_pmc_sl50_tp150_3r_1mfill",
        hub="us30_st_pmc_runner_variants",
    )
    id_ym_st = book_identity(
        market="ym",
        strategy="st_pmc",
        book="sl50_tp150_3r_1mfill",
        strategy_id="ym_hourly_st_pmc_sl50_tp150_3r_1mfill",
        hub="futures_st_pmc_runner_variants",
    )

    pairs = [
        ("YM prior-opposed", ym_po, id_ym_po, "US30 ST+PMC 3R", us30_st, id_us30_st),
        ("YM prior-opposed", ym_po, id_ym_po, "US30 prior-opposed", us30_po, id_us30_po),
        ("YM ST+PMC 3R", ym_st, id_ym_st, "US30 ST+PMC 3R", us30_st, id_us30_st),
        ("YM ST+PMC 3R", ym_st, id_ym_st, "US30 prior-opposed", us30_po, id_us30_po),
        ("YM prior-opposed", ym_po, id_ym_po, "YM ST+PMC 3R", ym_st, id_ym_st),
        ("US30 prior-opposed", us30_po, id_us30_po, "US30 ST+PMC 3R", us30_st, id_us30_st),
    ]

    results = []
    for na, a, ia, nb, b, ib in pairs:
        if not a or not b:
            results.append(
                {
                    "pair": "%s vs %s" % (na, nb),
                    "pair_key": "%s|%s" % (na, nb),
                    "status": "missing_data",
                }
            )
            continue
        row = _overlap_stats(na, a, nb, b, identity_a=ia, identity_b=ib)
        row["pair_key"] = "%s|%s" % (na, nb)
        row["pair_display"] = "%s vs %s" % (na, nb)
        results.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "overlap_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = [
            "pair",
            "a_campaigns",
            "b_campaigns",
            "a_days",
            "b_days",
            "shared_days",
            "day_jaccard",
            "dir_agree_rate_on_shared",
            "same_day_same_dir_events",
            "a_only_days",
            "b_only_days",
            "daily_net_corr",
            "shared_day_pnl_corr",
            "union_day_pnl_corr",
            "corr_days",
            "regime_class",
            "recommended_sizing",
            "regime_separable",
        ]
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in results:
            if "status" not in r:
                w.writerow(r)

    (OUT / "overlap.json").write_text(json.dumps(results, indent=2) + "\n")

    # Primary question: YM PO vs US30 ST+PMC
    primary = next(r for r in results if r.get("pair_key") == "YM prior-opposed|US30 ST+PMC 3R")

    lines = [
        "# YM ↔ US30 regime overlap",
        "",
        "Join key: NY session date (+ direction). Independent `trade_id`s — not joined across markets.",
        "Classifier: SEPARATE_REGIMES | CONDITIONAL_OVERLAP | SAME_SLEEVE | UNRESOLVED",
        "(Legacy OR rule `Jaccard < t OR |ρ| < t` removed.)",
        "",
        "## Primary: YM prior-opposed vs US30 ST+PMC 3R",
        "",
        "| metric | value |",
        "|---|---:|",
        "| YM PO campaigns / days | %s / %s |" % (primary["a_campaigns"], primary["a_days"]),
        "| US30 ST campaigns / days | %s / %s |" % (primary["b_campaigns"], primary["b_days"]),
        "| Shared session days | %s (Jaccard %.1f%%) |"
        % (primary["shared_days"], 100 * primary["day_jaccard"]),
        "| Dir agree on shared days | %s |" % primary["dir_agree_rate_on_shared"],
        "| Same-day same-dir events | %s |" % primary["same_day_same_dir_events"],
        "| Shared-day P&L correlation | %s (n=%s) |"
        % (primary.get("shared_day_pnl_corr", primary.get("daily_net_corr")), primary["corr_days"]),
        "| Union-day P&L correlation | %s |" % primary.get("union_day_pnl_corr"),
        "| Regime class | **%s** |" % primary.get("regime_class"),
        "| Recommended sizing | %s |" % primary.get("recommended_sizing"),
        "",
        "## All pairs",
        "",
        "| pair | shared days | Jaccard | dir-agree | shared ρ | union ρ | class |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        if r.get("status"):
            lines.append("| %s | — | — | — | — | — | %s |" % (r["pair"], r["status"]))
            continue
        lines.append(
            "| %s | %s | %.2f | %s | %s | %s | %s |"
            % (
                r.get("pair_display") or r["pair"],
                r["shared_days"],
                r["day_jaccard"],
                r["dir_agree_rate_on_shared"],
                r.get("shared_day_pnl_corr", r.get("daily_net_corr")),
                r.get("union_day_pnl_corr"),
                r.get("regime_class"),
            )
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- **SEPARATE_REGIMES** — low date overlap AND low shared-day relationship; independent allocations (still under portfolio caps).",
        "- **CONDITIONAL_OVERLAP** — sparse co-occurrence but high shared-day agreement/correlation; shared risk cap when both fire.",
        "- **SAME_SLEEVE** — meaningful overlap + high agreement/correlation; one shared allocation.",
        "- **UNRESOLVED** — insufficient sample or inconsistent/missing accounting.",
        "",
        "## Exact-book identities",
        "",
    ]
    for r in results:
        if r.get("status"):
            continue
        ia, ib = r.get("identity_a") or {}, r.get("identity_b") or {}
        lines.append(
            "- `%s` vs `%s`"
            % (ia.get("strategy_id") or ia.get("label"), ib.get("strategy_id") or ib.get("label"))
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "- `overlap_summary.csv`, `overlap.json`",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    cls = primary.get("regime_class") or "UNRESOLVED"
    email = [
        "YM ↔ US30 regime overlap — analysis",
        "",
        "Question: do YM prior-opposed and US30 ST+PMC (and cross pairs)",
        "share execution days / direction enough that they are one risk sleeve?",
        "Join: NY session date (+ direction). Not trade_id across markets.",
        "",
        "VERDICT (primary YM PO vs US30 ST+PMC 3R): %s" % cls,
        "Sizing: %s" % primary.get("recommended_sizing"),
        "",
        "Primary metrics:",
        "  shared days %d / union %d (Jaccard %.0f%%)"
        % (primary["shared_days"], primary["union_days"], 100 * primary["day_jaccard"]),
        "  dir-agree on shared days: %s" % primary["dir_agree_rate_on_shared"],
        "  same-day same-dir events: %d" % primary["same_day_same_dir_events"],
        "  shared-day PnL ρ: %s (n=%s)"
        % (primary.get("shared_day_pnl_corr", primary.get("daily_net_corr")), primary["corr_days"]),
        "  union-day PnL ρ: %s" % primary.get("union_day_pnl_corr"),
        "  YM-only / US30-only days: %d / %d" % (primary["a_only_days"], primary["b_only_days"]),
        "  identity_a: %s" % (primary.get("identity_a") or {}).get("strategy_id"),
        "  identity_b: %s" % (primary.get("identity_b") or {}).get("strategy_id"),
        "",
        "Cross-check pairs:",
    ]
    for r in results:
        if r.get("status") or r is primary:
            continue
        email.append(
            "  %s | Jaccard=%.2f ρ=%s dir-agree=%s class=%s"
            % (
                r["pair"],
                r["day_jaccard"],
                r.get("shared_day_pnl_corr", r.get("daily_net_corr")),
                r["dir_agree_rate_on_shared"],
                r.get("regime_class"),
            )
        )
    email += [
        "",
        "Note: low Jaccard + high conditional ρ/dir-agree => CONDITIONAL_OVERLAP,",
        "not SEPARATE_REGIMES. Exact book identity required for each conclusion.",
        "",
        "Hub: live/state/ym_us30_regime_overlap/",
    ]
    body = "\n".join(email) + "\n"
    (OUT / "EMAIL.txt").write_text(body)
    if args.email:
        send_email(subject="potions: YM↔US30 regime overlap analysis", body=body)
        print("emailed overlap analysis", flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
