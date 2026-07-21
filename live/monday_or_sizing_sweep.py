"""Monday OR sizing sweep — adapted to shifted-primary sidecar.

Adapted plan (vs generic same-direction SL sidecar)
---------------------------------------------------
Our sidecar is **shifted primary**: after main flat@50% DD, wait for the
**opposite Monday extreme** breakout with the same DD structure — not a
same-direction re-entry at the symbolic SL.

Sweep dimensions
----------------
1. **Main** entry size + (qty@30% DD, qty@50% DD)
2. **Sidecar (shifted)** entry size + exit split
3. **Max primary trades/week** (re-entry / weekly arm cap analogue)

Session filters deferred (we already trade Tue–Fri full week; London/NY
hour gates are Phase 2).

Phase 1 (default): M1–M3 × S1–S3 × R1–R3 (27 cells).
Phase full: M1–M6 × S1–S5 × R1–R3.

Selection (research pandas Net/|Closed DD|):
  prefer NetStress-equivalent Net/|DD| ≥ baseline, PF ≥ 1.05, then max CE.
Broker confirmation of top cells is optional (`--broker-top N` deferred).

Runs load 15m once per instrument then loop scenarios (data load dominated).
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .eurusd_monday_or_breakout_15m import (
    build_htf_features,
    list_mondays,
    resample_15m,
    simulate_week,
    summarize,
)
from .fx_data import load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monday_or_sizing_sweep"
JPY_USD = 110.0

# Point values for Net reporting (USDJPY/AUDJPY nets are in JPY units)
PV = {
    "EURUSD": 100_000.0,
    "GBPUSD": 100_000.0,
    "USDJPY": 100_000.0,
    "AUDJPY": 100_000.0,
}


@dataclass(frozen=True)
class SizeScenario:
    slug: str
    entry: int
    dd30: int
    dd50: int
    note: str = ""

    def cuts(self) -> Tuple[Tuple[float, int], ...]:
        cuts: List[Tuple[float, int]] = []
        if self.dd30 > 0:
            cuts.append((0.30, self.dd30))
        if self.dd50 > 0:
            cuts.append((0.50, self.dd50))
        if not cuts:
            raise ValueError("empty cuts for %s" % self.slug)
        if self.dd30 + self.dd50 != self.entry:
            raise ValueError(
                "%s: dd30+dd50 (%d) != entry (%d)" % (self.slug, self.dd30 + self.dd50, self.entry)
            )
        return tuple(cuts)


# Main leg grid
MAIN_FULL: List[SizeScenario] = [
    SizeScenario("M1", 3, 2, 1, "baseline 3 / drop2@30 / cut1@50"),
    SizeScenario("M2", 3, 1, 2, "more size at 50% DD"),
    SizeScenario("M3", 2, 1, 1, "smaller exposure"),
    SizeScenario("M4", 4, 2, 2, "larger balanced"),
    SizeScenario("M5", 4, 1, 3, "aggressive runner-heavy"),
    SizeScenario("M6", 5, 2, 3, "aggressive size"),
]
MAIN_PHASE1 = [m for m in MAIN_FULL if m.slug in {"M1", "M2", "M3"}]

# Sidecar = shifted primary size grid
SIDE_FULL: List[SizeScenario] = [
    SizeScenario("S1", 3, 2, 1, "match main baseline"),
    SizeScenario("S2", 2, 1, 1, "lighter shifted"),
    SizeScenario("S3", 4, 2, 2, "heavier shifted"),
    SizeScenario("S4", 3, 1, 2, "runner-heavy shifted"),
    SizeScenario("S5", 1, 0, 1, "probe shifted (flat@50 only)"),
]
SIDE_PHASE1 = [s for s in SIDE_FULL if s.slug in {"S1", "S2", "S3"}]

# Max primary trades / week (re-arm cap)
REENTRY_FULL: List[Tuple[str, int, str]] = [
    ("R1", 2, "baseline max 2 primary/week"),
    ("R2", 3, "allow 3 primary/week"),
    ("R3", 99, "effectively unlimited primary/week"),
]
REENTRY_PHASE1 = REENTRY_FULL  # all three are cheap


def load_instrument(sym: str) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], List[pd.Timestamp]]:
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    if not one_m.exists():
        raise FileNotFoundError(one_m)
    print("[%s] loading 1m → 15m + HTF..." % sym, flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m, sym)
    m1 = concat_all_1m(bars_by_day)
    if m1.index.tz is None:
        m1.index = m1.index.tz_localize("America/New_York")
    else:
        m1.index = m1.index.tz_convert("America/New_York")
    m15 = resample_15m(m1)
    h1 = build_htf_features(m1)
    mondays = list_mondays(m15)
    print("[%s] %s 15m bars | %d weeks" % (sym, f"{len(m15):,}", len(mondays)), flush=True)
    return m15, h1, mondays


def run_scenario(
    m15: pd.DataFrame,
    h1: Optional[pd.DataFrame],
    mondays: Sequence[pd.Timestamp],
    *,
    main: SizeScenario,
    side: SizeScenario,
    max_trades: int,
) -> Dict[str, float]:
    trades = []
    for mon in mondays:
        trades.extend(
            simulate_week(
                m15,
                mon,
                max_trades=max_trades,
                reward_R=2.0,
                contracts=main.entry,
                dd_cuts=main.cuts(),
                reverse_fade=False,
                shifted_primary=True,
                shifted_contracts=side.entry,
                shifted_dd_cuts=side.cuts(),
                h1=h1,
                skip_both_opposed=True,
            )
        )
    return summarize(trades)


def to_usd_net(sym: str, net: float) -> float:
    if sym in {"USDJPY", "AUDJPY"}:
        return net / JPY_USD
    return net


def write_plan(out: Path) -> None:
    text = """# Monday OR sizing sweep — adapted plan

## What we actually have

- **Main:** Mon OR breakout, 3 / drop2@30 / cut1@50, SL=1R TP=2R, HTF both-opposed skip.
- **Sidecar:** **shifted primary** (opposite Mon extreme after flat@50%), **not**
  same-direction re-entry at the symbolic SL.
- **Weekly cap:** max N primary trades/week (baseline N=2). Sidecar does not consume the cap.
- **Sessions:** Tue–Fri full week (no London/NY hour filter yet — Phase 2).

## Dimensions

| Dim | Meaning | Phase 1 | Full |
|---|---|---|---|
| M* | Main entry + (qty@30%, qty@50%) | M1–M3 | M1–M6 |
| S* | Shifted sidecar sizing | S1–S3 | S1–S5 |
| R* | Max primary trades/week | R1=2, R2=3, R3=99 | same |

## Selection

Among cells with Net/|DD| ≥ baseline×0.95 and PF ≥ 1.05, pick highest Net/|DD|,
then highest ≈USD net. Confirm top cells on USDJPY (viability pair).

Baseline tag: **M1_S1_R1** (current research champion structure).
"""
    (out / "ADAPTED_PLAN.md").write_text(text, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--pairs",
        default="EURUSD,USDJPY",
        help="Comma-separated (default EURUSD,USDJPY)",
    )
    parser.add_argument(
        "--phase",
        choices=("1", "full"),
        default="1",
        help="Phase 1 = M1-3×S1-3×R1-3; full = M1-6×S1-5×R1-3",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    write_plan(out)

    mains = MAIN_PHASE1 if args.phase == "1" else MAIN_FULL
    sides = SIDE_PHASE1 if args.phase == "1" else SIDE_FULL
    reentries = REENTRY_PHASE1

    pairs = [p.strip().upper() for p in str(args.pairs).split(",") if p.strip()]
    all_rows: List[dict] = []

    for sym in pairs:
        m15, h1, mondays = load_instrument(sym)
        baseline_stats = None
        n_scen = len(mains) * len(sides) * len(reentries)
        k = 0
        for main in mains:
            for side in sides:
                for rslug, max_tr, rnote in reentries:
                    k += 1
                    tag = "%s_%s_%s" % (main.slug, side.slug, rslug)
                    print("[%s] %d/%d %s ..." % (sym, k, n_scen, tag), flush=True)
                    stats = run_scenario(
                        m15, h1, mondays, main=main, side=side, max_trades=max_tr
                    )
                    net = float(stats["net_usd"])
                    dd = float(stats["max_dd"])
                    ce = (net / abs(dd)) if dd else 0.0
                    net_usd = to_usd_net(sym, net)
                    dd_usd = to_usd_net(sym, dd)
                    row = {
                        "symbol": sym,
                        "tag": tag,
                        "main": main.slug,
                        "main_entry": main.entry,
                        "main_dd30": main.dd30,
                        "main_dd50": main.dd50,
                        "side": side.slug,
                        "side_entry": side.entry,
                        "side_dd30": side.dd30,
                        "side_dd50": side.dd50,
                        "reentry": rslug,
                        "max_primary_per_week": max_tr,
                        "trades": int(stats["trades"]),
                        "primary_trades": int(stats.get("primary_trades", 0)),
                        "shifted_trades": int(stats.get("shifted_primaries", 0)),
                        "net": net,
                        "closed_dd": dd,
                        "net_dd": ce,
                        "net_usd_approx": net_usd,
                        "dd_usd_approx": dd_usd,
                        "net_dd_usd": (net_usd / abs(dd_usd)) if dd_usd else 0.0,
                        "pf": float(stats["profit_factor"])
                        if stats["profit_factor"] != float("inf")
                        else 99.0,
                        "wr_pct": float(stats["win_rate_pct"]),
                        "main_note": main.note,
                        "side_note": side.note,
                        "reentry_note": rnote,
                    }
                    all_rows.append(row)
                    if tag == "M1_S1_R1":
                        baseline_stats = row
                    # incremental CSV
                    _write_csv(out / "results.csv", all_rows)

        if baseline_stats:
            (out / ("baseline_%s.json" % sym.lower())).write_text(
                json.dumps(baseline_stats, indent=2), encoding="utf-8"
            )

    _write_csv(out / "results.csv", all_rows)
    _write_summary(out, all_rows)
    print("SUMMARY → %s" % (out / "SUMMARY.md"), flush=True)
    return 0


def _write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_summary(out: Path, rows: List[dict]) -> None:
    lines = [
        "# Monday OR sizing sweep",
        "",
        "Adapted plan: [`ADAPTED_PLAN.md`](ADAPTED_PLAN.md).",
        "Sidecar = **shifted primary** (opposite Mon extreme), not same-direction SL re-entry.",
        "",
    ]
    by_sym: Dict[str, List[dict]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)

    for sym, srows in by_sym.items():
        base = next((r for r in srows if r["tag"] == "M1_S1_R1"), None)
        base_ce = float(base["net_dd_usd"]) if base else 0.0
        ranked = sorted(srows, key=lambda r: (r["net_dd_usd"], r["net_usd_approx"]), reverse=True)
        # selection pool
        pool = [
            r
            for r in ranked
            if r["net_dd_usd"] >= base_ce * 0.95 and r["pf"] >= 1.05
        ]
        pick = pool[0] if pool else ranked[0]
        lines.extend(
            [
                "## %s" % sym,
                "",
                (
                    "Baseline **M1_S1_R1**: Net/|DD|≈**%.2f** | ≈USD net $%+.0f | PF %.2f"
                    % (base_ce, base["net_usd_approx"], base["pf"])
                    if base
                    else "Baseline M1_S1_R1 missing."
                ),
                "",
                "**Selected:** `%s` — Net/|DD| **%.2f** | ≈USD $%+.0f | PF %.2f | trades %d"
                % (
                    pick["tag"],
                    pick["net_dd_usd"],
                    pick["net_usd_approx"],
                    pick["pf"],
                    pick["trades"],
                ),
                "",
                "| Rank | Tag | Main | Side | Max/wk | ≈USD Net | ≈USD DD | **N/\|DD\|** | PF | WR | n |",
                "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for i, r in enumerate(ranked[:15], start=1):
            lines.append(
                "| %d | `%s` | %d=(%d@30,%d@50) | %d=(%d@30,%d@50) | %s | $%+.0f | $%+.0f | **%.2f** | %.2f | %.0f%% | %d |"
                % (
                    i,
                    r["tag"],
                    r["main_entry"],
                    r["main_dd30"],
                    r["main_dd50"],
                    r["side_entry"],
                    r["side_dd30"],
                    r["side_dd50"],
                    r["max_primary_per_week"] if r["max_primary_per_week"] < 90 else "∞",
                    r["net_usd_approx"],
                    r["dd_usd_approx"],
                    r["net_dd_usd"],
                    r["pf"],
                    r["wr_pct"],
                    r["trades"],
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Read",
            "",
            "- Prefer cells that beat or match baseline CE without exploding DD.",
            "- USDJPY is the broker-viability pair; EURUSD is the research reference.",
            "- Expand to `--phase full` if Phase 1 winner is not M1_S1_R1.",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
