from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .replay_realism import hardened_replay_engine_kwargs
from .v2b_strategy_cross_market_replay import MARKETS, ReplayResult, run_markets


def run_baseline_comparison(
    *,
    output_root: Path,
    markets: Sequence[str],
    max_days: int = 30,
    start: Optional[date] = None,
) -> List[ReplayResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    meta = {
        "realism": hardened_replay_engine_kwargs(),
        "max_days": max_days,
        "markets": list(markets),
        "dense_rth_bars": True,
    }
    (output_root / "realism_config.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    missing = [m for m in markets if not MARKETS[m.lower()].dbn_path.exists()]
    if missing:
        write_baseline_index(output_root, [], Path("live/CHANGE_LOG.md"))
        raise FileNotFoundError(
            "Missing DBN files for markets %s. See %s/INDEX.md for run instructions."
            % (missing, output_root)
        )
    return run_markets(output_root=output_root, market_names=markets, max_days=max_days, start=start)


def write_baseline_index(output_root: Path, results: Sequence[ReplayResult], prior_summary: Optional[Path]) -> None:
    lines = [
        "# V2B Cross-Market Hardened Replay Baseline",
        "",
        "Replay uses dense RTH 1m forward-fill, 1-tick slippage, synthetic spread overlay,",
        "stop-first OCO, and directional adverse-path limit guards.",
        "",
        "| Market | Units | Net | Closed DD | Intrabar Stress DD | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            "| %s | %d | $%.2f | $%.2f | $%.2f | %.2f |"
            % (r.instrument, r.units, r.net_usd, r.closed_dd_usd, r.intrabar_stress_dd_usd, r.net_over_stress)
        )
    lines.extend(["", "## Prior baseline", ""])
    if prior_summary and prior_summary.exists():
        lines.append("Compare against `%s` from pre-hardening snapshots." % prior_summary)
    else:
        lines.append("No prior summary path supplied; compare to `live/CHANGE_LOG.md` realism rerun section.")
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run hardened V2B cross-market replay baseline")
    parser.add_argument("--output-root", default="live/state/v2b_hardened_replay_baseline")
    parser.add_argument("--markets", default="mnq,nq")
    parser.add_argument("--max-days", type=int, default=30)
    parser.add_argument("--start", default="")
    parser.add_argument("--prior-summary", default="live/state/v2b_oco_cross_market/v2b_oco_cross_market_summary.csv")
    args = parser.parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    start = date.fromisoformat(args.start) if args.start else None
    output_root = Path(args.output_root)
    results = run_baseline_comparison(output_root=output_root, markets=markets, max_days=args.max_days, start=start)
    write_baseline_index(output_root, results, Path(args.prior_summary) if args.prior_summary else None)
    print("Wrote hardened baseline to %s" % output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
