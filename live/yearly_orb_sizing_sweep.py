from __future__ import annotations

"""Yearly ORB scaleout3 sizing sweep.

Grid sweep of per-unit sizing for the ``yearly_orb_scaleout3`` plugin. Each
row is one ``(tp25_qty, tp_qty, runner_qty)`` combination, replayed through
the same broker-like ``Engine`` + ``PaperBroker`` path used by
``broker_like_replays.py`` so the rows are directly comparable to the live
production leaderboard.

Knobs swept:

- ``tp25_qty``: contracts that exit at 25% of the way to the full TP
- ``tp_qty``: contracts that exit at the full TP (range == OR width)
- ``runner_qty``: contracts that ride to the runner stop / breakeven runner

The Yearly ORB strategy was extended in 2026-05-21 to honour these per-bucket
quantities for both the default ``limit_retest`` entry mode and the
``oco_stop`` entry mode used by the 20% range-close variant. ``batch_qty=1``
is the legacy "1/1/1 scaleout3" baseline.

Realism baseline is inherited from ``broker_like_replays.py`` (1-tick
slippage, $1.50/RT fee, stop gap-through, stop-first same-bar ordering,
OCO-collapsed risk projection).
"""

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .broker_like_replays import (
    DEFAULT_FEE_PER_UNIT,
    DEFAULT_SLIPPAGE_TICKS,
    MARKETS,
)
from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .reporting import generate_market_close_report
from .store import FlatFileStore


@dataclass(frozen=True)
class YearlyOrbSizingScenario:
    slug: str
    label: str
    tp25_qty: int
    tp_qty: int
    runner_qty: int
    entry_mode: str = "limit_retest"   # "limit_retest" | "oco_stop"
    range_close_inside_frac: Optional[float] = None
    notes: str = ""

    @property
    def total_qty(self) -> int:
        return int(self.tp25_qty) + int(self.tp_qty) + int(self.runner_qty)

    def to_config(self) -> Dict[str, object]:
        cfg: Dict[str, object] = {
            "or_start_month": 1,
            "or_end_month": 3,
            "trade_start_month": 4,
            "trade_end_month": 12,
            "batch_qty": 1,
            "tp25_qty": int(self.tp25_qty),
            "tp_qty": int(self.tp_qty),
            "runner_qty": int(self.runner_qty),
            "tp25_frac": 0.25,
            "tp_full_mult": 1.0,
            "require_fresh_break": True,
            "entry_mode": self.entry_mode,
        }
        if self.range_close_inside_frac is not None:
            cfg["range_close_inside_frac"] = float(self.range_close_inside_frac)
        return cfg


# A grid of per-unit sizings (tp25 / tp / runner). Total = sum of three.
# Naming convention: "L_4_2_1" = limit_retest, 4 scale-out / 2 TP / 1 runner.
# Range-close 20% variants are flagged with "_rc20".
DEFAULT_SCENARIOS: List[YearlyOrbSizingScenario] = [
    # --- Baselines: 1/1/1 limit_retest matches the current production row ---
    YearlyOrbSizingScenario(
        slug="L_1_1_1", label="limit_retest 1/1/1 (baseline)",
        tp25_qty=1, tp_qty=1, runner_qty=1,
        notes="Existing production yearly ORB scaleout3 row.",
    ),
    YearlyOrbSizingScenario(
        slug="L_1_1_1_rc20", label="limit_retest 1/1/1 + 20% range-close",
        tp25_qty=1, tp_qty=1, runner_qty=1,
        range_close_inside_frac=0.20,
        notes="Baseline plus the 20% range-close exit.",
    ),
    YearlyOrbSizingScenario(
        slug="O_1_1_1_rc20", label="oco_stop 1/1/1 + 20% range-close",
        tp25_qty=1, tp_qty=1, runner_qty=1,
        entry_mode="oco_stop",
        range_close_inside_frac=0.20,
        notes="Current OCO+20% production row.",
    ),
    # --- User's requested 4/2/1 family ---
    YearlyOrbSizingScenario(
        slug="L_4_2_1", label="limit_retest 4/2/1",
        tp25_qty=4, tp_qty=2, runner_qty=1,
        notes="User's pick: front-load 4 scale-out, 2 at TP, 1 runner.",
    ),
    YearlyOrbSizingScenario(
        slug="L_4_2_1_rc20", label="limit_retest 4/2/1 + 20% range-close",
        tp25_qty=4, tp_qty=2, runner_qty=1,
        range_close_inside_frac=0.20,
        notes="User's pick with 20% range-close.",
    ),
    YearlyOrbSizingScenario(
        slug="O_4_2_1_rc20", label="oco_stop 4/2/1 + 20% range-close",
        tp25_qty=4, tp_qty=2, runner_qty=1,
        entry_mode="oco_stop",
        range_close_inside_frac=0.20,
        notes="User's pick as OCO stop entry.",
    ),
    # --- Symmetric scales ---
    YearlyOrbSizingScenario(
        slug="L_2_2_2", label="limit_retest 2/2/2",
        tp25_qty=2, tp_qty=2, runner_qty=2,
        notes="Doubled baseline; 6 total contracts.",
    ),
    YearlyOrbSizingScenario(
        slug="L_3_3_3", label="limit_retest 3/3/3",
        tp25_qty=3, tp_qty=3, runner_qty=3,
        notes="Tripled baseline; 9 total contracts.",
    ),
    # --- Front-loaded variants (heavier scale-out) ---
    YearlyOrbSizingScenario(
        slug="L_2_1_1", label="limit_retest 2/1/1",
        tp25_qty=2, tp_qty=1, runner_qty=1,
        notes="Mildly front-loaded.",
    ),
    YearlyOrbSizingScenario(
        slug="L_3_2_1", label="limit_retest 3/2/1",
        tp25_qty=3, tp_qty=2, runner_qty=1,
        notes="Steeper front-load than user's pick.",
    ),
    YearlyOrbSizingScenario(
        slug="L_5_2_1", label="limit_retest 5/2/1",
        tp25_qty=5, tp_qty=2, runner_qty=1,
        notes="Extreme front-loading.",
    ),
    YearlyOrbSizingScenario(
        slug="L_4_1_1", label="limit_retest 4/1/1",
        tp25_qty=4, tp_qty=1, runner_qty=1,
        notes="Heavy quick exit, light TP and runner.",
    ),
    # --- Back-loaded (bigger runner) ---
    YearlyOrbSizingScenario(
        slug="L_1_1_3", label="limit_retest 1/1/3",
        tp25_qty=1, tp_qty=1, runner_qty=3,
        notes="Modest scaleouts, larger runner for trend.",
    ),
    YearlyOrbSizingScenario(
        slug="L_1_2_4", label="limit_retest 1/2/4",
        tp25_qty=1, tp_qty=2, runner_qty=4,
        notes="Back-loaded; big runner.",
    ),
    YearlyOrbSizingScenario(
        slug="L_2_2_4", label="limit_retest 2/2/4",
        tp25_qty=2, tp_qty=2, runner_qty=4,
        notes="Balanced with extra runner weight.",
    ),
    # --- TP-heavy ---
    YearlyOrbSizingScenario(
        slug="L_2_4_1", label="limit_retest 2/4/1",
        tp25_qty=2, tp_qty=4, runner_qty=1,
        notes="Heavy on full-TP exit.",
    ),
    YearlyOrbSizingScenario(
        slug="L_1_3_3", label="limit_retest 1/3/3",
        tp25_qty=1, tp_qty=3, runner_qty=3,
        notes="TP-heavy with sizable runner.",
    ),
    # --- Asymmetric front + runner ---
    YearlyOrbSizingScenario(
        slug="L_4_2_2", label="limit_retest 4/2/2",
        tp25_qty=4, tp_qty=2, runner_qty=2,
        notes="User's pick with bigger runner.",
    ),
    YearlyOrbSizingScenario(
        slug="L_3_1_3", label="limit_retest 3/1/3",
        tp25_qty=3, tp_qty=1, runner_qty=3,
        notes="Front and runner heavy; thin middle.",
    ),
]


@dataclass(frozen=True)
class SweepResult:
    market: str
    instrument: str
    scenario: YearlyOrbSizingScenario
    units: int
    trades: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int

    @property
    def net_over_stress(self) -> float:
        if not self.intrabar_stress_dd_usd:
            return 0.0
        return self.net_usd / abs(self.intrabar_stress_dd_usd)


def run_sweep(
    *,
    output_root: Path,
    market_names: Sequence[str],
    scenarios: Sequence[YearlyOrbSizingScenario] = DEFAULT_SCENARIOS,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    fee_per_unit: float = DEFAULT_FEE_PER_UNIT,
    force: bool = True,
) -> List[SweepResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    states_root = output_root / "states"
    audits_root = output_root / "audits"
    states_root.mkdir(parents=True, exist_ok=True)
    audits_root.mkdir(parents=True, exist_ok=True)

    wanted = {x.lower() for x in market_names}
    selected = [m for m in MARKETS if m.market in wanted]
    if not selected:
        raise ValueError(f"No matching markets in MARKETS for: {market_names!r}")

    results: List[SweepResult] = []
    for market in selected:
        if not market.daily_path.exists() or market.instrument not in POINT_VALUES:
            print(f"Skipping {market.instrument}, missing daily bars: {market.daily_path}", flush=True)
            continue
        bars = bars_from_csv(market.daily_path, market.instrument, "D", source=str(market.daily_path))
        if not bars:
            continue
        for scenario in scenarios:
            slug = f"{market.market}_yorb_sizing_{scenario.slug}"
            state_root = states_root / slug
            if force and state_root.exists():
                shutil.rmtree(state_root)
            state = FlatFileStore(state_root)
            state.ensure()
            instance = StrategyInstance(
                strategy_id=slug,
                strategy_type="yearly_orb_scaleout3",
                version="v1",
                instrument=market.instrument,
                broker_instrument=market.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="D",
                # Max contracts must accommodate the full ladder. Risk projection
                # is collapsed-by-OCO-group, so a 4/2/1 = 7 ladder needs at least 7.
                max_contracts=max(scenario.total_qty, 1),
                max_open_orders=64,
                config_json=json.dumps(scenario.to_config(), sort_keys=True),
            )
            state.upsert_row("strategy_instances", "strategy_id", as_row(instance))
            Engine(store=state, slippage_ticks=slippage_ticks).replay_bars(bars)
            generate_market_close_report(state, bars[-1].ts[:10])
            replay_bars = read_bars(state_root / "bars" / f"{market.instrument}_D.csv", "ts")
            units = units_from_live_fills(
                state_root / "fills.csv",
                slug,
                replay_bars[-1].ts,
                replay_bars[-1].close,
            )
            note = (
                f"{scenario.notes} "
                f"Realism: slippage={slippage_ticks:g} tick, fee=${fee_per_unit:.2f}/unit. "
                f"Per-unit sizing tp25/tp/runner = {scenario.tp25_qty}/{scenario.tp_qty}/{scenario.runner_qty}."
            ).strip()
            audit = audit_units(
                name=f"{market.instrument} Yearly ORB {scenario.label}",
                slug=slug,
                source=state_root / "fills.csv",
                bar_source=state_root / "bars" / f"{market.instrument}_D.csv",
                bars=replay_bars,
                units=units,
                instrument=market.instrument,
                notes=note,
                output_root=audits_root,
                fee_per_unit=fee_per_unit,
            )
            res = SweepResult(
                market=market.market,
                instrument=market.instrument,
                scenario=scenario,
                units=audit.units,
                trades=audit.trades,
                net_usd=audit.net_usd,
                closed_dd_usd=audit.close_mtm_dd_usd,
                intrabar_stress_dd_usd=audit.intrabar_mtm_dd_usd,
                max_open_units=audit.max_open_units,
            )
            results.append(res)
            print(
                f"{market.instrument:>4} {scenario.slug:<22} "
                f"({scenario.tp25_qty}/{scenario.tp_qty}/{scenario.runner_qty} tot={scenario.total_qty}, {scenario.entry_mode:<12} rc={scenario.range_close_inside_frac}) "
                f"net=${res.net_usd:>12,.2f} stress=${res.intrabar_stress_dd_usd:>11,.2f} ratio={res.net_over_stress:.2f}",
                flush=True,
            )

    _write_summary(output_root, results, slippage_ticks, fee_per_unit)
    return results


def _write_summary(
    output_root: Path,
    results: List[SweepResult],
    slippage_ticks: float,
    fee_per_unit: float,
) -> None:
    rows = []
    ranked = sorted(results, key=lambda r: r.net_over_stress, reverse=True)
    for rank, r in enumerate(ranked, start=1):
        s = r.scenario
        rows.append(
            {
                "rank": str(rank),
                "market": r.market,
                "instrument": r.instrument,
                "slug": s.slug,
                "label": s.label,
                "entry_mode": s.entry_mode,
                "range_close_inside_frac": "" if s.range_close_inside_frac is None else f"{s.range_close_inside_frac:.2f}",
                "tp25_qty": str(s.tp25_qty),
                "tp_qty": str(s.tp_qty),
                "runner_qty": str(s.runner_qty),
                "total_qty": str(s.total_qty),
                "units": str(r.units),
                "trades": str(r.trades),
                "net_usd": "%.2f" % r.net_usd,
                "closed_dd_usd": "%.2f" % r.closed_dd_usd,
                "intrabar_stress_dd_usd": "%.2f" % r.intrabar_stress_dd_usd,
                "max_open_units": str(r.max_open_units),
                "net_over_stress_dd": "%.2f" % r.net_over_stress,
                "notes": s.notes,
            }
        )
    _write_csv(output_root / "summary.csv", rows)

    lines = [
        "# Yearly ORB Scaleout3 Sizing Sweep",
        "",
        "Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for ",
        "`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` ",
        "path used by `broker_like_replays.py`.",
        "",
        f"Realism baseline: `slippage_ticks={slippage_ticks:g}`, `fee_per_unit=${fee_per_unit:.2f}`, ",
        "stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.",
        "",
        "Ranking is by `Net / Stress DD`.",
        "",
        "| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | RC | Units | Trades | Net | Stress DD | Net / Stress |",
        "|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in ranked:
        rank = ranked.index(r) + 1
        s = r.scenario
        rc = "—" if s.range_close_inside_frac is None else f"{int(s.range_close_inside_frac*100)}%"
        lines.append(
            f"| {rank} | {r.instrument} | {s.label} | {s.tp25_qty} | {s.tp_qty} | {s.runner_qty} | "
            f"{s.total_qty} | {s.entry_mode} | {rc} | {r.units} | {r.trades} | "
            f"${r.net_usd:,.2f} | ${r.intrabar_stress_dd_usd:,.2f} | {r.net_over_stress:.2f} |"
        )

    lines.append("")
    lines.append("## Per-Market Ranking")
    by_market: Dict[str, List[SweepResult]] = {}
    for r in results:
        by_market.setdefault(r.instrument, []).append(r)
    for inst in sorted(by_market):
        rows_m = sorted(by_market[inst], key=lambda r: r.net_over_stress, reverse=True)
        lines.append("")
        lines.append(f"### {inst}")
        lines.append("")
        lines.append("| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |")
        lines.append("|---|---:|---:|---:|---:|---|---|---:|---:|---:|")
        for r in rows_m:
            s = r.scenario
            rc = "—" if s.range_close_inside_frac is None else f"{int(s.range_close_inside_frac*100)}%"
            lines.append(
                f"| {s.label} | {s.tp25_qty} | {s.tp_qty} | {s.runner_qty} | {s.total_qty} | "
                f"{s.entry_mode} | {rc} | ${r.net_usd:,.2f} | ${r.intrabar_stress_dd_usd:,.2f} | "
                f"{r.net_over_stress:.2f} |"
            )

    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- [`summary.csv`](summary.csv) — same data, CSV.")
    lines.append("- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.")
    lines.append("- `states/<slug>/` — broker state, fills, orders, and report for each row.")

    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Yearly ORB scaleout3 sizing sweep.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("potions/live/state/yearly_orb_sizing_sweep"),
    )
    parser.add_argument(
        "--markets",
        type=str,
        default="mnq,nq",
        help="Comma-separated markets (mnq,nq,es,mes,ym,mym).",
    )
    parser.add_argument(
        "--slippage-ticks",
        type=float,
        default=DEFAULT_SLIPPAGE_TICKS,
    )
    parser.add_argument(
        "--fee-per-unit",
        type=float,
        default=DEFAULT_FEE_PER_UNIT,
    )
    parser.add_argument("--no-force", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    results = run_sweep(
        output_root=args.output_root,
        market_names=markets,
        slippage_ticks=args.slippage_ticks,
        fee_per_unit=args.fee_per_unit,
        force=not args.no_force,
    )
    print(f"Wrote {args.output_root}/SUMMARY.md with {len(results)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
