"""Broker-like stress: EURUSD monthly ORB v2b OCO + close-only SL.

Compares scaleout structures:
  S_1_1_2  entry 4 = 1@1R + 1@2R + 2 runner
  S_1_1_1  entry 3 = 1@1R + 1@2R + 1 runner
  S_1_1_0  entry 2 = 1@1R + 1@2R + 0 runner

Rules match research ``eurusd_monthly_orb_v2b_oco``: OR=3 sessions, OCO @ ORH/ORL,
max 2 fills/month, BE after TP1, daily-close SL (wicks allowed), month-end flatten.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .broker_like_replays import BrokerReplaySpec, _runtime_config
from .build_broker_like_replay_detail_charts import build_detail_charts
from .engine import Engine, bars_from_csv
from .eurusd_overnight_sweep import FEE_PER_UNIT, INSTRUMENT, MARKET, TICK
from .fx_data import ensure_eurusd_platform_files
from .models import StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_v2b_oco_broker"


def _specs() -> List[BrokerReplaySpec]:
    base = {
        "allow_shorts": True,
        "or_sessions": 3,
        "max_trades_per_month": 2,
        "tp1_qty": 1,
        "tp2_qty": 1,
        "tp1_r": 1.0,
        "tp2_r": 2.0,
        "stop_mode": "close",
        "record_levels": False,
    }
    variants: List[Tuple[str, str, int, int, int]] = [
        ("Monthly ORB v2b OCO S_1_1_2 close-SL", "monthly_orb_v2b_oco_S_1_1_2", 4, 1, 1),
        ("Monthly ORB v2b OCO S_1_1_1 close-SL", "monthly_orb_v2b_oco_S_1_1_1", 3, 1, 1),
        ("Monthly ORB v2b OCO S_1_1_0 close-SL", "monthly_orb_v2b_oco_S_1_1_0", 2, 1, 1),
    ]
    out: List[BrokerReplaySpec] = []
    for name, slug, entry_qty, tp1, tp2 in variants:
        cfg = dict(base)
        cfg["entry_qty"] = entry_qty
        cfg["tp1_qty"] = tp1
        cfg["tp2_qty"] = tp2
        out.append(
            BrokerReplaySpec(
                name=name,
                slug=slug,
                strategy_type="monthly_orb_v2b_oco",
                max_contracts=entry_qty,
                config=cfg,
                notes="OCO monthly ORB, TP1=1R TP2=2R, BE after TP1, daily-close SL, month-end flatten.",
            )
        )
    return out


SPECS = _specs()


def run(output_root: Path, force: bool = False, charts: bool = False) -> None:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    ensure_eurusd_platform_files(REPO, force=False)
    daily_path = REPO / "fx" / "eurusd_daily.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    print("Loaded %d EURUSD daily bars" % len(bars), flush=True)

    results = []
    for spec in SPECS:
        strategy_id = "%s_%s" % (MARKET, spec.slug)
        state_root = output_root / "states" / strategy_id
        print("START %s" % strategy_id, flush=True)
        if force and state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        instance = StrategyInstance(
            strategy_id=strategy_id,
            strategy_type=spec.strategy_type,
            version="v1",
            instrument=INSTRUMENT,
            broker_instrument=INSTRUMENT,
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=spec.max_contracts,
            max_open_orders=64,
            config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
        Engine(store=store, slippage_ticks=1.0, tick_size={INSTRUMENT: TICK}).replay_bars(bars)
        store.flush_tables()
        generate_market_close_report(store, bars[-1].ts[:10])
        replay_bars = read_bars(state_root / "bars" / ("%s_D.csv" % INSTRUMENT), "ts")
        units = units_from_live_fills(
            state_root / "fills.csv",
            strategy_id,
            replay_bars[-1].ts,
            replay_bars[-1].close,
        )
        audit = audit_units(
            name="EURUSD %s" % spec.name,
            slug=strategy_id,
            source=state_root / "fills.csv",
            bar_source=state_root / "bars" / ("%s_D.csv" % INSTRUMENT),
            bars=replay_bars,
            units=units,
            instrument=INSTRUMENT,
            notes=spec.notes + " fee=$%.2f/unit." % FEE_PER_UNIT,
            output_root=output_root / "audits",
            fee_per_unit=FEE_PER_UNIT,
        )
        ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        results.append((spec, audit, ratio))
        print(
            "DONE %s trades=%d units=%d Net=$%.2f CloseDD=$%.2f StressDD=$%.2f Net/Stress=%.2f"
            % (
                strategy_id,
                audit.trades,
                audit.units,
                audit.net_usd,
                audit.close_mtm_dd_usd,
                audit.intrabar_mtm_dd_usd,
                ratio,
            ),
            flush=True,
        )

    summary_rows = []
    for spec, audit, ratio in results:
        summary_rows.append(
            {
                "candidate": "EURUSD %s" % spec.name,
                "slug": "%s_%s" % (MARKET, spec.slug),
                "structure": spec.slug.split("_S_")[-1] if "_S_" in spec.slug else "",
                "instrument": INSTRUMENT,
                "units": str(audit.units),
                "trades": str(audit.trades),
                "net_usd": "%.2f" % audit.net_usd,
                "close_mtm_dd_usd": "%.2f" % audit.close_mtm_dd_usd,
                "intrabar_mtm_dd_usd": "%.2f" % audit.intrabar_mtm_dd_usd,
                "max_open_units": str(audit.max_open_units),
                "net_over_stress_dd": "%.2f" % ratio,
            }
        )
    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    # Runner attribution: S_1_1_2 vs S_1_1_0 / S_1_1_1
    by_slug = {r["slug"]: r for r in summary_rows}
    s112 = by_slug.get("%s_monthly_orb_v2b_oco_S_1_1_2" % MARKET)
    s111 = by_slug.get("%s_monthly_orb_v2b_oco_S_1_1_1" % MARKET)
    s110 = by_slug.get("%s_monthly_orb_v2b_oco_S_1_1_0" % MARKET)

    lines = [
        "# EURUSD Monthly ORB v2b OCO (broker-like stress)",
        "",
        "Engine + PaperBroker on Histdata daily EURUSD.",
        "OCO @ ORH/ORL, max 2 fills/month, TP1=1R / TP2=2R, BE after TP1,",
        "daily-close SL (wicks allowed), flatten month-end. Fee $%.2f/unit." % FEE_PER_UNIT,
        "",
        "| Structure | Trades | Units | Net | Close DD | Stress DD | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| %s | %s | %s | $%s | $%s | $%s | %s |"
            % (
                row["structure"] or row["slug"],
                row["trades"],
                row["units"],
                row["net_usd"],
                row["close_mtm_dd_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
            )
        )
    lines.extend(["", "## Runner value", ""])
    if s112 and s110:
        d_net = float(s112["net_usd"]) - float(s110["net_usd"])
        d_stress = float(s112["intrabar_mtm_dd_usd"]) - float(s110["intrabar_mtm_dd_usd"])
        lines.append(
            "- **S_1_1_2 vs S_1_1_0** (2-unit runner): ΔNet=$%+.0f, ΔStressDD=$%+.0f"
            % (d_net, d_stress)
        )
    if s112 and s111:
        d_net = float(s112["net_usd"]) - float(s111["net_usd"])
        d_stress = float(s112["intrabar_mtm_dd_usd"]) - float(s111["intrabar_mtm_dd_usd"])
        lines.append(
            "- **S_1_1_2 vs S_1_1_1** (extra 1 runner): ΔNet=$%+.0f, ΔStressDD=$%+.0f"
            % (d_net, d_stress)
        )
    if s111 and s110:
        d_net = float(s111["net_usd"]) - float(s110["net_usd"])
        d_stress = float(s111["intrabar_mtm_dd_usd"]) - float(s110["intrabar_mtm_dd_usd"])
        lines.append(
            "- **S_1_1_1 vs S_1_1_0** (1-unit runner): ΔNet=$%+.0f, ΔStressDD=$%+.0f"
            % (d_net, d_stress)
        )
    lines.append("")
    lines.append("Compare prior limit-retest scaleout3: ~+$22k / 0.45 Net/Stress.")
    lines.append("")
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        causality_mode="audit",
        extra={"driver": "eurusd_monthly_orb_v2b_oco_broker", "variants": [s.slug for s in SPECS]},
    )

    if charts:
        chart_root = output_root / "charts"
        print("Building monthly ORB year charts...", flush=True)
        built = build_detail_charts(
            replay_root=output_root,
            output_root=chart_root,
            include_all=False,
            include_slugs=["%s_%s" % (MARKET, s.slug) for s in SPECS],
            exact=True,
        )
        print("Built %d chart files under %s" % (len(built), chart_root), flush=True)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--charts", action="store_true")
    args = parser.parse_args(argv)
    run(args.output_root, force=args.force, charts=args.charts)
    print("Wrote %s" % (args.output_root / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
