"""Run NQ timing autopsy + causal proxy replays (resting-limit + provisional)."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from typing import List, Optional

from .nq_v2b_prior_opposed_replay import Result, run
from .nq_v2b_prior_opposed_timing_study import DEFAULT_OUT as TIMING_OUT
from .nq_v2b_prior_opposed_timing_study import run as run_timing_study
from .v2b_st_pmc_alignment_study import REPO


def _row(label: str, result: Result) -> dict:
    return {
        "label": label,
        "trades": str(result.trades),
        "units": str(result.units),
        "net_usd": "%.2f" % result.net_usd,
        "closed_dd_usd": "%.2f" % result.closed_dd_usd,
        "intrabar_stress_dd_usd": "%.2f" % result.stress_dd_usd,
        "win_rate_pct": "%.2f" % result.win_rate_pct,
        "profit_factor": "%.3f" % result.profit_factor,
        "net_over_stress": "%.2f" % result.net_stress,
        "prior_opposite_entries": str(result.prior_opposite_entries),
        "causality_violations": str(result.causality_violations),
        "state_root": str(result.state_root),
    }


def write_comparison(output_root: Path, rows: List[dict], timing_index: Path) -> None:
    with (output_root / "comparison.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# NQ Prior-Opposed Causal Proxy Comparison",
        "",
        "Timing autopsy: `%s`" % timing_index.relative_to(REPO),
        "",
        "| Label | Trades | Net | Closed DD | Stress DD | Win % | PF | Net/Stress | Prior@entry |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | $%s | $%s | $%s | %s | %s | %s | %s |"
            % (
                row["label"],
                row["trades"],
                row["net_usd"],
                row["closed_dd_usd"],
                row["intrabar_stress_dd_usd"],
                row["win_rate_pct"],
                row["profit_factor"],
                row["net_over_stress"],
                row["prior_opposite_entries"],
            )
        )
    lines.extend(
        [
            "",
            "## Proxies",
            "",
            "- **resting_limit:** arm v2b only after opposite ST entry limit is resting (`live_after_ts`).",
            "- **provisional_invalidate_60m:** trade all regime v2b; flatten if no opposite 1m-touch ST fill within 60 minutes of entry.",
            "- Banked hourly / 1m-touch rows are referenced from existing state folders (not re-run here).",
            "",
            "Files:",
            "",
            "- `comparison.csv`",
            "- `resting_limit/`",
            "- `provisional_invalidate_60m/`",
        ]
    )
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2021-03-04")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/nq_v2b_prior_opposed_causal_proxies")
    parser.add_argument("--skip-timing", action="store_true")
    parser.add_argument("--skip-resting", action="store_true")
    parser.add_argument("--skip-provisional", action="store_true")
    parser.add_argument("--invalidate-minutes", type=int, default=60)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    force = not args.no_force
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    timing_index = TIMING_OUT / "INDEX.md"
    if not args.skip_timing:
        timing_index = run_timing_study(TIMING_OUT)

    rows: List[dict] = []
    # Reference rows from existing replays when present
    for label, summary in [
        ("banked_hourly_stamp", REPO / "live/state/nq_v2b_prior_opposed_stpmc_broker_like/summary.csv"),
        ("fill_1m_touch", REPO / "live/state/nq_v2b_prior_opposed_stpmc_1m_touch/summary.csv"),
    ]:
        if summary.exists():
            import pandas as pd

            s = pd.read_csv(summary).iloc[0]
            rows.append(
                {
                    "label": label,
                    "trades": str(s["trades"]),
                    "units": str(s["units"]),
                    "net_usd": str(s["net_usd"]),
                    "closed_dd_usd": str(s["closed_dd_usd"]),
                    "intrabar_stress_dd_usd": str(s["intrabar_stress_dd_usd"]),
                    "win_rate_pct": str(s["win_rate_pct"]),
                    "profit_factor": str(s["profit_factor"]),
                    "net_over_stress": str(s["net_over_stress"]),
                    "prior_opposite_entries": str(s.get("prior_opposite_entries", "")),
                    "causality_violations": str(s.get("causality_violations", "")),
                    "state_root": str(summary.parent),
                }
            )

    if not args.skip_resting:
        print("=== Resting-limit gate replay ===", flush=True)
        resting = run(
            output_root / "resting_limit",
            force=force,
            market="nq",
            start=start,
            gate_mode="resting_limit",
            prior_opposite_only=True,
            refine_st_touches=False,
        )
        rows.append(_row("resting_limit", resting))

    if not args.skip_provisional:
        print("=== Provisional v2b + invalidate %dm ===" % args.invalidate_minutes, flush=True)
        provisional = run(
            output_root / ("provisional_invalidate_%dm" % args.invalidate_minutes),
            force=force,
            market="nq",
            start=start,
            gate_mode="fill_1m_touch",
            prior_opposite_only=False,
            invalidate_without_opposite_minutes=args.invalidate_minutes,
            refine_st_touches=True,
            require_prior_validation=False,
        )
        rows.append(_row("provisional_invalidate_%dm" % args.invalidate_minutes, provisional))

    if rows:
        write_comparison(output_root, rows, timing_index)
        print("Wrote %s" % (output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
