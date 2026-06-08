from __future__ import annotations

"""ATR Supertrend DCA sizing sweep.

Defines a grid of ``initial_qty`` / ``add_qty`` / ``max_contracts`` /
``add_interval`` combinations for the ``atr_supertrend_dca`` strategy and
runs each through the broker-like ``Engine`` + ``PaperBroker`` path so
results are directly comparable with ``broker_like_replays.py`` rankings.

The realism baseline (1-tick slippage, $1.50/RT fee, stop gap-through,
stop-first same-bar ordering) is applied automatically.

Default markets: MNQ + NQ (the two most discussed ATR markets). Use
``--markets`` to override.
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
class SizingScenario:
    slug: str
    label: str
    signal_tf: str            # "daily" | "weekly"
    schedule: str             # "fixed" | "ladder112221"
    initial_qty: int
    add_qty: int
    max_contracts: int
    add_interval: int         # weeks between eligible adds
    use_entry_guard: bool = True
    daily_use_weekly_flat: bool = False
    ladder: Optional[List[int]] = None
    notes: str = ""

    def to_config(self) -> Dict[str, object]:
        cfg: Dict[str, object] = {
            "signal_tf": self.signal_tf,
            "schedule": self.schedule,
            "initial_qty": int(self.initial_qty),
            "add_qty": int(self.add_qty),
            "max_contracts": int(self.max_contracts),
            "add_interval": int(self.add_interval),
            "use_entry_guard": bool(self.use_entry_guard),
            "daily_use_weekly_flat": bool(self.daily_use_weekly_flat),
            "add_on_friday_close": True,
            "record_levels": False,
        }
        if self.ladder is not None:
            cfg["ladder"] = list(self.ladder)
        return cfg


DEFAULT_SCENARIOS: List[SizingScenario] = [
    # Baselines that already exist in broker_like_replays for cross-reference
    SizingScenario(
        slug="daily_3init_1add_10max_intv2",
        label="Daily 3-initial / 1-add / 10-max / interval=2",
        signal_tf="daily", schedule="fixed",
        initial_qty=3, add_qty=1, max_contracts=10, add_interval=2,
        notes="Mirrors atr_daily_3initial_10max baseline.",
    ),
    SizingScenario(
        slug="daily_ladder112221_10max_intv2",
        label="Daily ladder 1/1/2/2/2/1 / 10-max / interval=2",
        signal_tf="daily", schedule="ladder112221",
        initial_qty=1, add_qty=1, max_contracts=10, add_interval=2,
        ladder=[1, 1, 2, 2, 2, 1],
        notes="Mirrors atr_daily_ladder112221_10max baseline.",
    ),
    SizingScenario(
        slug="weekly_2init_3add_6max_intv2",
        label="Weekly 2-initial / 3-add / 6-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=2, add_qty=3, max_contracts=6, add_interval=2,
        notes="User-friendly weekly sweet-spot pick.",
    ),
    # New sizing exploration cells
    SizingScenario(
        slug="weekly_1init_2add_6max_intv2",
        label="Weekly 1-initial / 2-add / 6-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=1, add_qty=2, max_contracts=6, add_interval=2,
        notes="Slow start, modest adds, conservative ceiling.",
    ),
    SizingScenario(
        slug="weekly_2init_2add_5max_intv2",
        label="Weekly 2-initial / 2-add / 5-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=2, add_qty=2, max_contracts=5, add_interval=2,
        notes="Lower ceiling vs friendly-pick.",
    ),
    SizingScenario(
        slug="weekly_2init_2add_6max_intv2",
        label="Weekly 2-initial / 2-add / 6-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=2, add_qty=2, max_contracts=6, add_interval=2,
        notes="Match friendly-pick max but slower adds.",
    ),
    SizingScenario(
        slug="weekly_2init_3add_8max_intv2",
        label="Weekly 2-initial / 3-add / 8-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=2, add_qty=3, max_contracts=8, add_interval=2,
        notes="Friendly-pick but with higher ceiling.",
    ),
    SizingScenario(
        slug="weekly_3init_1add_6max_intv2",
        label="Weekly 3-initial / 1-add / 6-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=3, add_qty=1, max_contracts=6, add_interval=2,
        notes="Front-loaded entry, conservative ceiling.",
    ),
    SizingScenario(
        slug="weekly_3init_2add_8max_intv2",
        label="Weekly 3-initial / 2-add / 8-max / interval=2",
        signal_tf="weekly", schedule="fixed",
        initial_qty=3, add_qty=2, max_contracts=8, add_interval=2,
        notes="Front-loaded plus moderate adds.",
    ),
    SizingScenario(
        slug="weekly_1init_1add_6max_intv1",
        label="Weekly 1-initial / 1-add / 6-max / interval=1",
        signal_tf="weekly", schedule="fixed",
        initial_qty=1, add_qty=1, max_contracts=6, add_interval=1,
        notes="Slow start but adds every week instead of bi-weekly.",
    ),
    SizingScenario(
        slug="weekly_2init_2add_6max_intv4",
        label="Weekly 2-initial / 2-add / 6-max / interval=4",
        signal_tf="weekly", schedule="fixed",
        initial_qty=2, add_qty=2, max_contracts=6, add_interval=4,
        notes="Less-frequent adds; tests under-trade hypothesis.",
    ),
    SizingScenario(
        slug="daily_2init_2add_6max_intv2",
        label="Daily 2-initial / 2-add / 6-max / interval=2",
        signal_tf="daily", schedule="fixed",
        initial_qty=2, add_qty=2, max_contracts=6, add_interval=2,
        notes="Daily mirror of weekly 2/2/6.",
    ),
    SizingScenario(
        slug="daily_2init_3add_6max_intv2",
        label="Daily 2-initial / 3-add / 6-max / interval=2",
        signal_tf="daily", schedule="fixed",
        initial_qty=2, add_qty=3, max_contracts=6, add_interval=2,
        notes="Daily friendly-pick mirror.",
    ),
    SizingScenario(
        slug="weekly_2init_3add_6max_intv2_no_guard",
        label="Weekly 2/3/6/intv=2 (no entry guard)",
        signal_tf="weekly", schedule="fixed",
        initial_qty=2, add_qty=3, max_contracts=6, add_interval=2,
        use_entry_guard=False,
        notes="Friendly-pick without the prior-fill entry guard. Tests cost of the guard.",
    ),
    SizingScenario(
        slug="ladder12221_6max_intv2",
        label="Custom ladder 1/2/2/2/1 / 6-max / interval=2",
        signal_tf="weekly", schedule="ladder112221",
        initial_qty=1, add_qty=1, max_contracts=6, add_interval=2,
        ladder=[1, 2, 2, 2, 1],
        notes="Front-loaded ladder capped at 6.",
    ),
]


@dataclass(frozen=True)
class SizingResult:
    market: str
    instrument: str
    scenario: SizingScenario
    units: int
    trades: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int

    @property
    def net_over_stress(self) -> float:
        return self.net_usd / abs(self.intrabar_stress_dd_usd) if self.intrabar_stress_dd_usd else 0.0


def run_sweep(
    *,
    output_root: Path,
    market_names: Sequence[str],
    scenarios: Sequence[SizingScenario] = DEFAULT_SCENARIOS,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    fee_per_unit: float = DEFAULT_FEE_PER_UNIT,
    force: bool = True,
) -> List[SizingResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    states_root = output_root / "states"
    audits_root = output_root / "audits"
    states_root.mkdir(parents=True, exist_ok=True)
    audits_root.mkdir(parents=True, exist_ok=True)

    market_set = {m.market for m in MARKETS}
    selected_markets = [m for m in MARKETS if m.market in market_set and m.market in {x.lower() for x in market_names}]
    if not selected_markets:
        raise ValueError(f"No matching markets in MARKETS for: {market_names!r}")

    results: List[SizingResult] = []
    for market in selected_markets:
        if not market.daily_path.exists() or market.instrument not in POINT_VALUES:
            print(f"Skipping {market.instrument}, missing daily bars: {market.daily_path}", flush=True)
            continue
        bars = bars_from_csv(market.daily_path, market.instrument, "D", source=str(market.daily_path))
        if not bars:
            continue
        for scenario in scenarios:
            slug = f"{market.market}_atr_sizing_{scenario.slug}"
            state_root = states_root / slug
            if force and state_root.exists():
                shutil.rmtree(state_root)
            state = FlatFileStore(state_root)
            state.ensure()
            instance = StrategyInstance(
                strategy_id=slug,
                strategy_type="atr_supertrend_dca",
                version="v1",
                instrument=market.instrument,
                broker_instrument=market.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="D",
                max_contracts=int(scenario.max_contracts),
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
                f"Realism: slippage={slippage_ticks:g} tick, fee=${fee_per_unit:.2f}/unit."
            ).strip()
            audit = audit_units(
                name=f"{market.instrument} {scenario.label}",
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
            res = SizingResult(
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
                f"{market.instrument:>4} {scenario.slug:<40} net=${res.net_usd:>12,.2f} "
                f"stress=${res.intrabar_stress_dd_usd:>12,.2f} ratio={res.net_over_stress:.2f}",
                flush=True,
            )

    _write_summary(output_root, results, slippage_ticks, fee_per_unit)
    return results


def _write_summary(
    output_root: Path,
    results: List[SizingResult],
    slippage_ticks: float,
    fee_per_unit: float,
) -> None:
    rows = []
    ranked = sorted(results, key=lambda r: r.net_over_stress, reverse=True)
    for rank, r in enumerate(ranked, start=1):
        rows.append(
            {
                "rank": str(rank),
                "market": r.market,
                "instrument": r.instrument,
                "slug": r.scenario.slug,
                "label": r.scenario.label,
                "signal_tf": r.scenario.signal_tf,
                "schedule": r.scenario.schedule,
                "initial_qty": str(r.scenario.initial_qty),
                "add_qty": str(r.scenario.add_qty),
                "max_contracts": str(r.scenario.max_contracts),
                "add_interval_weeks": str(r.scenario.add_interval),
                "use_entry_guard": "true" if r.scenario.use_entry_guard else "false",
                "units": str(r.units),
                "trades": str(r.trades),
                "net_usd": "%.2f" % r.net_usd,
                "closed_dd_usd": "%.2f" % r.closed_dd_usd,
                "intrabar_stress_dd_usd": "%.2f" % r.intrabar_stress_dd_usd,
                "max_open_units": str(r.max_open_units),
                "net_over_stress_dd": "%.2f" % r.net_over_stress,
                "notes": r.scenario.notes,
            }
        )
    _write_csv(output_root / "summary.csv", rows)

    lines = [
        "# ATR Supertrend DCA Sizing Sweep",
        "",
        "Each row is one ATR Supertrend DCA sizing combination run through the same broker-like ",
        "`Engine` + `PaperBroker` path used by `broker_like_replays.py`.",
        "",
        f"Realism baseline: `slippage_ticks={slippage_ticks:g}`, `fee_per_unit=${fee_per_unit:.2f}`, ",
        "stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.",
        "",
        "Ranking is by `Net / Stress DD`. Net DD is intrabar stress mark-to-market.",
        "",
        "| Rank | Market | Sizing | Init | Add | Max | Intv (wks) | Sched | Guard | Units | Trades | Net | Stress DD | Net / Stress |",
        "|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in ranked:
        rank = ranked.index(r) + 1
        lines.append(
            "| {rank} | {market} | {label} | {init} | {add} | {max} | {intv} | {sched} | {guard} | "
            "{units} | {trades} | ${net:,.2f} | ${dd:,.2f} | {ratio:.2f} |".format(
                rank=rank,
                market=r.instrument,
                label=r.scenario.label,
                init=r.scenario.initial_qty,
                add=r.scenario.add_qty,
                max=r.scenario.max_contracts,
                intv=r.scenario.add_interval,
                sched=r.scenario.schedule,
                guard="yes" if r.scenario.use_entry_guard else "no",
                units=r.units,
                trades=r.trades,
                net=r.net_usd,
                dd=r.intrabar_stress_dd_usd,
                ratio=r.net_over_stress,
            )
        )
    lines.append("")
    lines.append("## Per-Market Net / Stress")
    by_market: Dict[str, List[SizingResult]] = {}
    for r in results:
        by_market.setdefault(r.instrument, []).append(r)
    for inst in sorted(by_market):
        rows_m = sorted(by_market[inst], key=lambda r: r.net_over_stress, reverse=True)
        lines.append("")
        lines.append(f"### {inst}")
        lines.append("")
        lines.append("| Sizing | Init | Add | Max | Intv | Net | Stress DD | Net / Stress |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in rows_m:
            lines.append(
                f"| {r.scenario.label} | {r.scenario.initial_qty} | {r.scenario.add_qty} | "
                f"{r.scenario.max_contracts} | {r.scenario.add_interval} | "
                f"${r.net_usd:,.2f} | ${r.intrabar_stress_dd_usd:,.2f} | {r.net_over_stress:.2f} |"
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
    parser = argparse.ArgumentParser(description="Run an ATR Supertrend DCA sizing sweep.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("potions/live/state/atr_sizing_sweep"),
    )
    parser.add_argument(
        "--markets",
        type=str,
        default="mnq,nq",
        help="Comma-separated markets to sweep (mnq,nq,es,mes,ym,mym).",
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
