"""Batch StrategyPlugin replay: prior-opposed S_1_1_3 + 1×10R for futures.

Extends the resting-limit prior-opposed book with one targeted runner at 10×R
(3 EOD runners remain). Plugin: ``v2b_scaleout`` via
``nq_v2b_prior_opposed_replay --book S_1_1_3_plus_1x10R``.

Hub: ``live/state/prior_opposed_plus_1x10R_futures/``
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import List, Optional, Sequence

from .nq_v2b_prior_opposed_replay import PRIOR_OPPOSED_MARKETS, run
from .notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "prior_opposed_plus_1x10R_futures"
DEFAULT_MARKETS = ("nq", "mnq", "ym")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--markets", nargs="*", default=list(DEFAULT_MARKETS), choices=PRIOR_OPPOSED_MARKETS)
    ap.add_argument("--gate-mode", default="resting_limit")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--no-force", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    OUT.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for market in args.markets:
        mroot = OUT / market
        existing = mroot / "result_row.json"
        # Resume-friendly: keep finished markets unless --force (default force=True via not no_force)
        if args.no_force and existing.exists():
            row = json.loads(existing.read_text(encoding="utf-8"))
            rows.append(row)
            print("SKIP %s (existing result_row.json N/S=%s)" % (market, row.get("net_stress")), flush=True)
            continue
        print("=== %s prior-opposed +1×10R (%s) ===" % (market.upper(), args.gate_mode), flush=True)
        result = run(
            mroot,
            force=not args.no_force,
            market=market,
            gate_mode=args.gate_mode,
            prior_opposite_only=True,
            book="S_1_1_3_plus_1x10R",
        )
        row = {
            "market": market,
            "strategy_id": result.strategy_id,
            "trades": result.trades,
            "net_usd": round(result.net_usd, 2),
            "stress_usd": round(result.stress_dd_usd, 2),
            "net_stress": round(result.net_stress, 3),
            "win_rate_pct": round(result.win_rate_pct, 2),
            "prior_opposite_entries": result.prior_opposite_entries,
            "causality_violations": result.causality_violations,
            "hub": str(mroot.relative_to(REPO)),
        }
        rows.append(row)
        (mroot / "result_row.json").write_text(json.dumps(row, indent=2) + "\n")
        print(
            "  %s Net/Stress=%.2f net=$%.0f trades=%d"
            % (market, row["net_stress"], row["net_usd"], row["trades"]),
            flush=True,
        )

    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["market"])
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# Prior-opposed S_1_1_3 + 1×10R (futures StrategyPlugin)",
        "",
        "Book: 1 TP1 + 1 TP2 + 3 EOD runners + **1 runner @ 10×R** (BE after TP1).",
        "Gate: resting_limit prior-opposed. Plugin: `v2b_scaleout`.",
        "",
        "| market | trades | net | stress | N/S | causality |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | %s | $%.0f | $%.0f | **%.2f** | %s |"
            % (r["market"], r["trades"], r["net_usd"], r["stress_usd"], r["net_stress"], r["causality_violations"])
        )
    lines += [
        "",
        "Compare to baseline S_1_1_3 hubs and post-process `prior_opposed_10r_addon/`.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    email = [
        "Prior-opposed +1×10R futures StrategyPlugin",
        "",
        "Book: S_1_1_3 + one targeted 10R runner (v2b_scaleout).",
        "",
    ]
    for r in rows:
        email.append(
            "%-4s N/S=%.2f  net=$%.0f  trades=%d  caus=%d"
            % (r["market"].upper(), r["net_stress"], r["net_usd"], r["trades"], r["causality_violations"])
        )
    email += ["", "Hub: live/state/prior_opposed_plus_1x10R_futures/"]
    body = "\n".join(email) + "\n"
    (OUT / "EMAIL.txt").write_text(body)
    if args.email:
        send_email(subject="potions: prior-opposed +1×10R futures plugin replay", body=body)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
