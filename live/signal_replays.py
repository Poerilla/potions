from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .reporting import generate_market_close_report
from .replay_audit import AuditResult, audit_units, read_bars, units_from_live_fills
from .store import FlatFileStore


@dataclass(frozen=True)
class SignalReplaySpec:
    name: str
    slug: str
    strategy_type: str
    config: Dict[str, object]
    max_contracts: int
    notes: str


ATR_SPECS: List[SignalReplaySpec] = [
    SignalReplaySpec(
        name="ATR weekly 2-initial / 3-add / 6-max",
        slug="mnq_atr_weekly_2initial_3add_6max",
        strategy_type="atr_supertrend_dca",
        max_contracts=6,
        config={
            "signal_tf": "weekly",
            "initial_qty": 2,
            "add_qty": 3,
            "max_contracts": 6,
            "add_interval": 2,
            "schedule": "fixed",
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Current TV sweet-spot sizing candidate; true StrategyPlugin/PaperBroker replay.",
    ),
    SignalReplaySpec(
        name="ATR weekly 3-initial / 1-add / 10-max",
        slug="mnq_atr_weekly_3initial_10max",
        strategy_type="atr_supertrend_dca",
        max_contracts=10,
        config={
            "signal_tf": "weekly",
            "initial_qty": 3,
            "add_qty": 1,
            "max_contracts": 10,
            "add_interval": 2,
            "schedule": "fixed",
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Weekly-primary 3-initial candidate; true StrategyPlugin/PaperBroker replay.",
    ),
    SignalReplaySpec(
        name="ATR weekly ladder 1/1/2/2/2 / 10-max",
        slug="mnq_atr_weekly_ladder112221_10max",
        strategy_type="atr_supertrend_dca",
        max_contracts=10,
        config={
            "signal_tf": "weekly",
            "initial_qty": 1,
            "add_qty": 1,
            "max_contracts": 10,
            "add_interval": 2,
            "schedule": "ladder112221",
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Weekly-primary ladder candidate; true StrategyPlugin/PaperBroker replay.",
    ),
    SignalReplaySpec(
        name="ATR daily 3-initial / 1-add / 10-max",
        slug="mnq_atr_daily_3initial_10max",
        strategy_type="atr_supertrend_dca",
        max_contracts=10,
        config={
            "signal_tf": "daily",
            "initial_qty": 3,
            "add_qty": 1,
            "max_contracts": 10,
            "add_interval": 2,
            "schedule": "fixed",
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Daily-primary 3-initial candidate; true StrategyPlugin/PaperBroker replay.",
    ),
    SignalReplaySpec(
        name="ATR daily ladder 1/1/2/2/2 / 10-max",
        slug="mnq_atr_daily_ladder112221_10max",
        strategy_type="atr_supertrend_dca",
        max_contracts=10,
        config={
            "signal_tf": "daily",
            "initial_qty": 1,
            "add_qty": 1,
            "max_contracts": 10,
            "add_interval": 2,
            "schedule": "ladder112221",
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Daily-primary ladder candidate; true StrategyPlugin/PaperBroker replay.",
    ),
    SignalReplaySpec(
        name="ATR daily weekly-flat 5-max",
        slug="mnq_atr_daily_weekly_flat_5max",
        strategy_type="atr_supertrend_dca",
        max_contracts=5,
        config={
            "signal_tf": "daily",
            "initial_qty": 3,
            "add_qty": 1,
            "max_contracts": 5,
            "add_interval": 2,
            "schedule": "fixed",
            "use_entry_guard": True,
            "daily_use_weekly_flat": True,
            "add_on_friday_close": True,
        },
        notes="Lower-stack daily weekly-flat candidate; true StrategyPlugin/PaperBroker replay.",
    ),
]


def run_signal_replays(output_root: Path, bars_path: Path, force: bool = True) -> List[AuditResult]:
    repo = Path.cwd()
    if repo.name != "potions":
        repo = repo / "potions"
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    audit_root = output_root / "audits"
    audit_root.mkdir(parents=True, exist_ok=True)

    results: List[AuditResult] = []
    yearly_state = repo / "live" / "state" / "mnq_yearly_orb_paper_replay"
    yearly_bars_path = yearly_state / "bars" / "MNQ_D.csv"
    if (yearly_state / "fills.csv").exists() and yearly_bars_path.exists():
        bars = read_bars(yearly_bars_path, "ts")
        units = units_from_live_fills(yearly_state / "fills.csv", "mnq_yearly_orb_scaleout3_live_runtime", bars[-1].ts, bars[-1].close)
        results.append(
            audit_units(
                name="Yearly ORB scaleout3 live-runtime replay",
                slug="mnq_yearly_orb_scaleout3_live_runtime",
                source=yearly_state / "fills.csv",
                bar_source=yearly_bars_path,
                bars=bars,
                units=units,
                instrument="MNQ",
                notes="Existing true Yearly ORB StrategyPlugin/PaperBroker replay; open units marked at final close if any.",
                output_root=audit_root,
            )
        )

    for spec in ATR_SPECS:
        state_root = output_root / spec.slug
        if force and state_root.exists():
            shutil.rmtree(state_root)
        state = FlatFileStore(state_root)
        state.ensure()
        instance = StrategyInstance(
            strategy_id=spec.slug,
            strategy_type=spec.strategy_type,
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=spec.max_contracts,
            max_open_orders=64,
            config_json=json.dumps(spec.config, sort_keys=True),
        )
        state.upsert_row("strategy_instances", "strategy_id", as_row(instance))
        bars = bars_from_csv(bars_path, "MNQ", "D", source=str(bars_path))
        Engine(store=state).replay_bars(bars)
        generate_market_close_report(state, bars[-1].ts[:10])
        replay_bars = read_bars(state_root / "bars" / "MNQ_D.csv", "ts")
        units = units_from_live_fills(state_root / "fills.csv", spec.slug, replay_bars[-1].ts, replay_bars[-1].close)
        results.append(
            audit_units(
                name=spec.name,
                slug=spec.slug,
                source=state_root / "fills.csv",
                bar_source=state_root / "bars" / "MNQ_D.csv",
                bars=replay_bars,
                units=units,
                instrument="MNQ",
                notes=spec.notes + " Open units are marked at final replay close.",
                output_root=audit_root,
            )
        )

    _write_summary(output_root, results)
    return results


def _write_summary(root: Path, results: List[AuditResult]) -> None:
    rows = []
    for r in sorted(results, key=lambda item: item.net_usd / abs(item.intrabar_mtm_dd_usd or -1), reverse=True):
        ratio = r.net_usd / abs(r.intrabar_mtm_dd_usd) if r.intrabar_mtm_dd_usd else 0.0
        rows.append(
            {
                "candidate": r.name,
                "slug": r.slug,
                "units": str(r.units),
                "trades": str(r.trades),
                "net_usd": "%.2f" % r.net_usd,
                "close_mtm_dd_usd": "%.2f" % r.close_mtm_dd_usd,
                "intrabar_mtm_dd_usd": "%.2f" % r.intrabar_mtm_dd_usd,
                "max_open_units": str(r.max_open_units),
                "net_over_stress_dd": "%.2f" % ratio,
            }
        )
    _write_csv(root / "summary.csv", rows)
    lines = [
        "# StrategyPlugin Signal Replay Rankings",
        "",
        "These rows are true `StrategyPlugin` passes through `Engine` + `PaperBroker`, not direct research CSV replays. Open positions are marked at the final replay close so live-style stack heat is visible.",
        "",
        "| Rank | Candidate | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            "| %d | %s | %s | %s | $%s | $%s | $%s | %s | %s |"
            % (
                idx,
                row["candidate"],
                row["units"],
                row["trades"],
                _money(float(row["net_usd"])),
                _money(float(row["close_mtm_dd_usd"])),
                _money(float(row["intrabar_mtm_dd_usd"])),
                row["max_open_units"],
                row["net_over_stress_dd"],
            )
        )
    lines.extend(
        [
            "",
            "## Not Yet Promoted To Signal Replay",
            "",
            "- Monthly ORB restricted scaleout3 is still a research/artifact replay until its live plugin is implemented.",
            "- Monthly overlap range breakout daily-ST retest x5 is still a 4h research/artifact replay until its live plugin is implemented.",
            "- v2b clean-break variants are still intraday research sims until a 1m/5m StrategyPlugin exists.",
            "",
        ]
    )
    (root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    import csv

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


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run StrategyPlugin signal replays for leading candidates.")
    parser.add_argument("--output-root", type=Path, default=Path("potions/live/state/strategy_plugin_signal_replays"))
    parser.add_argument("--bars", type=Path, default=Path("potions/mnq/mnq_daily.csv"))
    parser.add_argument("--no-force", action="store_true", help="Keep existing replay state folders.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_signal_replays(args.output_root, args.bars, force=not args.no_force)
    for r in results:
        print(
            "%s net=$%s stress_dd=$%s max_open=%d"
            % (r.slug, _money(r.net_usd), _money(r.intrabar_mtm_dd_usd), r.max_open_units)
        )
    print("Wrote %s" % args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
