"""Broker-like stress: EURUSD monthly ORB scaleout3 ladder + close-only SL.

Shared risk / management
------------------------
- OR = first 3 sessions
- Max 2 fills/month
- Structure **1/1/1**: 1 @ 0.25R (TP25), 1 @ 1R, 1 runner
- SL → BE after TP1 (0.25R)
- Wick-through SL ignored (daily close only)
- Flatten month-end
- Fee $7 / lot

Variants
--------
1. ``oco`` — OCO stop @ ORH/ORL immediately after OR
2. ``first_break_opposite`` — ignore first OR break, then arm stop opposite
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import List, Optional

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
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_tp25_close_sl_broker"

LADDER = {
    "allow_shorts": True,
    "or_sessions": 3,
    "max_trades_per_month": 2,
    "entry_qty": 3,
    "tp1_qty": 1,
    "tp2_qty": 1,
    "tp1_r": 0.25,
    "tp2_r": 1.0,
    "stop_mode": "close",
    "record_levels": False,
}


def _specs() -> List[BrokerReplaySpec]:
    return [
        BrokerReplaySpec(
            name="Monthly ORB OCO TP25/1R/runner close-SL",
            slug="monthly_orb_oco_tp25_1r_runner",
            strategy_type="monthly_orb_v2b_oco",
            max_contracts=3,
            config={**LADDER, "entry_mode": "oco"},
            notes="OCO after OR. 1@0.25R / 1@1R / 1 runner. BE after TP1. Daily-close SL.",
        ),
        BrokerReplaySpec(
            name="Monthly ORB first-break opposite TP25/1R/runner close-SL",
            slug="monthly_orb_first_break_opp_tp25_1r_runner",
            strategy_type="monthly_orb_v2b_oco",
            max_contracts=3,
            config={**LADDER, "entry_mode": "first_break_opposite"},
            notes="Ignore first OR break, arm opposite stop. Same 1@0.25R / 1@1R / 1 runner ladder.",
        ),
    ]


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
                "entry_mode": str(spec.config.get("entry_mode")),
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

    lines = [
        "# EURUSD Monthly ORB TP25/1R/runner (broker-like)",
        "",
        "Shared: OR=3, max 2/month, **1 @ 0.25R / 1 @ 1R / 1 runner**, BE after TP1,",
        "daily-close SL, month-end flatten. Fee $%.2f/unit." % FEE_PER_UNIT,
        "",
        "| Entry mode | Trades | Units | Net | Close DD | Stress DD | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| %s | %s | %s | $%s | $%s | $%s | %s |"
            % (
                row["entry_mode"],
                row["trades"],
                row["units"],
                row["net_usd"],
                row["close_mtm_dd_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
            )
        )
    lines.extend(
        [
            "",
            "- **oco**: arm OCO @ ORH/ORL right after OR forms.",
            "- **first_break_opposite**: ignore first OR break, then arm stop the other way.",
            "",
            "Compare prior limit-retest scaleout3: ~+$22k / 0.45 Net/Stress.",
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        causality_mode="audit",
        extra={"driver": "eurusd_monthly_orb_tp25_close_sl_broker", "variants": [s.slug for s in SPECS]},
    )

    if charts:
        chart_root = output_root / "charts"
        print("Building charts...", flush=True)
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
