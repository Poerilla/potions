from __future__ import annotations

"""V2B scaleout sizing sweep across markets.

Grid sweep of ``entry_qty`` / ``tp1_qty`` / ``tp2_qty`` for the
``v2b_scaleout`` plugin, replayed through the same 1-minute broker-like path
used by ``v2b_strategy_cross_market_replay.py``.

The v2b strategy was extended in 2026-05-21 to honour per-bucket quantities:

- ``tp1_qty`` contracts exit at TP1 (range == OR width above/below the OR).
- ``tp2_qty`` contracts exit at TP2 (2x range).
- The implicit runner = ``entry_qty - tp1_qty - tp2_qty`` rides the runner
  stop until either the runner stop fires or the EOD flatten triggers.

Realism baseline is inherited from ``broker_like_replays.py`` (1-tick
slippage, $1.50/RT fee, stop gap-through, stop-first same-bar ordering,
OCO-collapsed risk projection).
"""

import argparse
import csv
import json
import math
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .broker_like_replays import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import (
    MARKETS as V2B_MARKETS,
    MarketConfig,
    _regime_dates,
    _rth_bars,
    load_1m_by_ny_date_any,
)
from .v2b_strategy_replay import (
    AuditBar,
    DEFAULT_SLIPPAGE_TICKS as V2B_DEFAULT_SLIPPAGE_TICKS,
    FEE_PER_UNIT,
    fast_intraday_audit,
    units_from_v2b_fills,
)


@dataclass(frozen=True)
class V2BSizingScenario:
    slug: str
    label: str
    entry_qty: int
    tp1_qty: int
    tp2_qty: int
    mode: str = "oco_then_reverse"   # "oco_then_reverse" | "strict_long_then_short"
    notes: str = ""

    @property
    def runner_qty(self) -> int:
        return max(0, int(self.entry_qty) - int(self.tp1_qty) - int(self.tp2_qty))

    def to_config(self, market: str, regime_dates_iso: List[str], start: Optional[date]) -> Dict[str, object]:
        return {
            "market": market,
            "mode": self.mode,
            "entry_qty": int(self.entry_qty),
            "tp1_qty": int(self.tp1_qty),
            "tp2_qty": int(self.tp2_qty),
            "tick_size": 0.25,
            "use_regime_filter": True,
            "start": start.isoformat() if start else "",
            "regime_dates": list(regime_dates_iso),
            "record_levels": False,
        }


# Scenarios: TP1 / TP2 / runner. entry_qty = TP1 + TP2 + runner.
# Naming convention: e.g. "S_4_2_1" = entry=7, 4 at TP1, 2 at TP2, 1 runner.
DEFAULT_SCENARIOS: List[V2BSizingScenario] = [
    # --- Baselines ---
    V2BSizingScenario(
        slug="S_1_1_0", label="1/1/0 (entry 2, no runner)",
        entry_qty=2, tp1_qty=1, tp2_qty=1,
        notes="Current production v2b scaleout 1+1 with no runner.",
    ),
    V2BSizingScenario(
        slug="S_1_1_1", label="1/1/1 (entry 3, baseline with runner)",
        entry_qty=3, tp1_qty=1, tp2_qty=1,
        notes="Baseline + 1 runner contract.",
    ),
    # --- User's pattern: 4 / 2 / 1 ---
    V2BSizingScenario(
        slug="S_4_2_1", label="4/2/1 (entry 7)",
        entry_qty=7, tp1_qty=4, tp2_qty=2,
        notes="User's pick: front-load 4 at TP1, 2 at TP2, 1 runner.",
    ),
    V2BSizingScenario(
        slug="S_4_1_1", label="4/1/1 (entry 6)",
        entry_qty=6, tp1_qty=4, tp2_qty=1,
        notes="Heavy quick exit, light TP2 and runner.",
    ),
    # --- Symmetric scales ---
    V2BSizingScenario(
        slug="S_2_2_0", label="2/2/0 (entry 4, no runner)",
        entry_qty=4, tp1_qty=2, tp2_qty=2,
        notes="Doubled baseline; no runner.",
    ),
    V2BSizingScenario(
        slug="S_2_2_2", label="2/2/2 (entry 6)",
        entry_qty=6, tp1_qty=2, tp2_qty=2,
        notes="Symmetric scaling with equal runner.",
    ),
    # --- Front-loaded variants ---
    V2BSizingScenario(
        slug="S_3_1_1", label="3/1/1 (entry 5)",
        entry_qty=5, tp1_qty=3, tp2_qty=1,
        notes="Mildly front-loaded.",
    ),
    V2BSizingScenario(
        slug="S_5_2_1", label="5/2/1 (entry 8)",
        entry_qty=8, tp1_qty=5, tp2_qty=2,
        notes="Extreme front-loading.",
    ),
    # --- Back-loaded (bigger runner) ---
    V2BSizingScenario(
        slug="S_1_1_3", label="1/1/3 (entry 5, big runner)",
        entry_qty=5, tp1_qty=1, tp2_qty=1,
        notes="Modest scaleouts, larger runner for trend.",
    ),
    V2BSizingScenario(
        slug="S_2_1_2", label="2/1/2 (entry 5)",
        entry_qty=5, tp1_qty=2, tp2_qty=1,
        notes="Balanced front + runner; thin TP2.",
    ),
]


@dataclass(frozen=True)
class SweepResult:
    market: str
    instrument: str
    scenario: V2BSizingScenario
    regime_days: int
    units: int
    trades: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int
    win_rate: float
    profit_factor: float

    @property
    def net_over_stress(self) -> float:
        if not self.intrabar_stress_dd_usd:
            return 0.0
        return self.net_usd / abs(self.intrabar_stress_dd_usd)


def run_sweep(
    *,
    output_root: Path,
    market_names: Sequence[str],
    scenarios: Sequence[V2BSizingScenario] = DEFAULT_SCENARIOS,
    start: Optional[date] = None,
    max_days: Optional[int] = None,
    slippage_ticks: float = V2B_DEFAULT_SLIPPAGE_TICKS,
    fee_per_unit: float = FEE_PER_UNIT,
    force: bool = True,
) -> List[SweepResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    states_root = output_root / "states"
    states_root.mkdir(parents=True, exist_ok=True)

    wanted = {x.lower() for x in market_names}
    selected = [V2B_MARKETS[m] for m in V2B_MARKETS if m in wanted]
    if not selected:
        raise ValueError(f"No matching markets in V2B_MARKETS for: {market_names!r}")

    results: List[SweepResult] = []
    for cfg in selected:
        if not cfg.dbn_path.exists():
            print(f"Skipping {cfg.instrument}, missing DBN/CSV at {cfg.dbn_path}", flush=True)
            continue
        if not cfg.daily_path.exists():
            print(f"Skipping {cfg.instrument}, missing daily bars at {cfg.daily_path}", flush=True)
            continue
        print(f"Loading {cfg.instrument} 1m for V2B sizing sweep...", flush=True)
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
        regime_dates = _regime_dates(cfg, gby, start=start)
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
        regime_dates_iso = [d.isoformat() for d in regime_dates]
        print(f"  {cfg.instrument} regime sessions: {len(regime_dates)}", flush=True)

        for scenario in scenarios:
            slug = f"{cfg.market}_v2b_sizing_{scenario.slug}"
            state_root = states_root / slug
            if force and state_root.exists():
                shutil.rmtree(state_root)
            store = FlatFileStore(state_root, defer_table_writes=True)
            store.ensure()
            instance = StrategyInstance(
                strategy_id=slug,
                strategy_type="v2b_scaleout",
                version="v1",
                instrument=cfg.instrument,
                broker_instrument=cfg.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="1m",
                max_contracts=int(scenario.entry_qty),
                max_open_orders=64,
                config_json=json.dumps(scenario.to_config(cfg.market, regime_dates_iso, start), sort_keys=True),
            )
            store.write_table("strategy_instances", [as_row(instance)])
            engine = Engine(
                store=store,
                persist_bars=False,
                persist_health=False,
                slippage_ticks=slippage_ticks,
            )
            audit_bars: List[AuditBar] = []
            for idx, day in enumerate(regime_dates, start=1):
                df = _rth_bars(gby.get(day), day)
                if df.empty:
                    continue
                for ts, row in df.iterrows():
                    ts_s = pd.Timestamp(ts).isoformat()
                    bar = Bar(
                        instrument=cfg.instrument,
                        timeframe="1m",
                        ts=ts_s,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                        complete=True,
                        source=str(cfg.dbn_path),
                    )
                    engine.process_bar(bar)
                    audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
                if idx % 500 == 0:
                    print(f"  {cfg.instrument} {scenario.slug}: {idx}/{len(regime_dates)} sessions", flush=True)
            store.flush_tables()
            units = units_from_v2b_fills(state_root / "fills.csv", slug)
            audit = fast_intraday_audit(
                strategy_id=slug,
                state_root=state_root,
                bars=audit_bars,
                units=units,
                instrument=cfg.instrument,
                fee_per_unit=fee_per_unit,
            )
            res = SweepResult(
                market=cfg.market,
                instrument=cfg.instrument,
                scenario=scenario,
                regime_days=len(regime_dates),
                units=len(units),
                trades=len({u.trade_id for u in units}),
                net_usd=audit["net_usd"],
                closed_dd_usd=audit["closed_dd_usd"],
                intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
                max_open_units=audit["max_open_units"],
                win_rate=audit["win_rate"],
                profit_factor=audit["profit_factor"],
            )
            results.append(res)
            print(
                f"{cfg.instrument:>4} {scenario.slug:<10} "
                f"(tp1={scenario.tp1_qty} tp2={scenario.tp2_qty} runner={scenario.runner_qty} entry={scenario.entry_qty}) "
                f"net=${res.net_usd:>12,.2f} stress=${res.intrabar_stress_dd_usd:>12,.2f} ratio={res.net_over_stress:.2f}",
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
    ranked = sorted(results, key=lambda r: r.net_over_stress, reverse=True)
    rows = []
    for rank, r in enumerate(ranked, start=1):
        s = r.scenario
        rows.append(
            {
                "rank": str(rank),
                "market": r.market,
                "instrument": r.instrument,
                "slug": s.slug,
                "label": s.label,
                "mode": s.mode,
                "entry_qty": str(s.entry_qty),
                "tp1_qty": str(s.tp1_qty),
                "tp2_qty": str(s.tp2_qty),
                "runner_qty": str(s.runner_qty),
                "regime_days": str(r.regime_days),
                "units": str(r.units),
                "trades": str(r.trades),
                "net_usd": "%.2f" % r.net_usd,
                "closed_dd_usd": "%.2f" % r.closed_dd_usd,
                "intrabar_stress_dd_usd": "%.2f" % r.intrabar_stress_dd_usd,
                "max_open_units": str(r.max_open_units),
                "win_rate_pct": "%.2f" % r.win_rate,
                "profit_factor": ("%.3f" % r.profit_factor) if math.isfinite(r.profit_factor) else "inf",
                "net_over_stress_dd": "%.2f" % r.net_over_stress,
                "notes": s.notes,
            }
        )
    _write_csv(output_root / "summary.csv", rows)

    lines = [
        "# V2B Scaleout Sizing Sweep",
        "",
        "Each row is one per-unit ladder (`tp1_qty / tp2_qty / runner_qty`) for the ",
        "v2b_scaleout plugin driven through the same 1-minute broker-like path used by ",
        "`v2b_strategy_cross_market_replay.py`.",
        "",
        f"Realism baseline: `slippage_ticks={slippage_ticks:g}`, `fee_per_unit=${fee_per_unit:.2f}`, ",
        "stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.",
        "",
        "Ranking is by `Net / Stress DD`.",
        "",
        "| Rank | Market | Sizing | Entry | TP1 | TP2 | Runner | Sessions | Units | Trades | Net | Stress DD | Net / Stress |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in ranked:
        rank = ranked.index(r) + 1
        s = r.scenario
        lines.append(
            f"| {rank} | {r.instrument} | {s.label} | {s.entry_qty} | {s.tp1_qty} | {s.tp2_qty} | "
            f"{s.runner_qty} | {r.regime_days} | {r.units} | {r.trades} | "
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
        lines.append("| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in rows_m:
            s = r.scenario
            pf = ("%.2f" % r.profit_factor) if math.isfinite(r.profit_factor) else "inf"
            lines.append(
                f"| {s.label} | {s.entry_qty} | {s.tp1_qty} | {s.tp2_qty} | {s.runner_qty} | {r.units} | "
                f"${r.net_usd:,.2f} | ${r.intrabar_stress_dd_usd:,.2f} | {r.net_over_stress:.2f} | "
                f"{r.win_rate:.1f}% | {pf} |"
            )

    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- [`summary.csv`](summary.csv) — same data, CSV.")
    lines.append("- `states/<slug>/` — broker state, fills, orders, audit for each row.")

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
    parser = argparse.ArgumentParser(description="Run a v2b_scaleout sizing sweep across markets.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("potions/live/state/v2b_sizing_sweep"),
    )
    parser.add_argument(
        "--markets",
        type=str,
        default="mnq,nq,ym,mym,es,mes",
        help="Comma-separated markets (mnq,nq,es,mes,ym,mym).",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2021-03-04",
        help="Common start date for apples-to-apples comparison.",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=None,
        help="Optional cap on regime days per market (smoke test).",
    )
    parser.add_argument(
        "--slippage-ticks",
        type=float,
        default=V2B_DEFAULT_SLIPPAGE_TICKS,
    )
    parser.add_argument(
        "--fee-per-unit",
        type=float,
        default=FEE_PER_UNIT,
    )
    parser.add_argument("--no-force", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    start = date.fromisoformat(args.start) if args.start else None
    results = run_sweep(
        output_root=args.output_root,
        market_names=markets,
        start=start,
        max_days=args.max_days,
        slippage_ticks=args.slippage_ticks,
        fee_per_unit=args.fee_per_unit,
        force=not args.no_force,
    )
    print(f"Wrote {args.output_root}/SUMMARY.md with {len(results)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
