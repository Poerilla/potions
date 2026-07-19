"""Broker-like EURUSD runs for named Yearly ORB research variants.

1. yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close
   -> existing yearly_orb_scaleout3 (limit retest, inside-range swing stop,
      full range-close when price closes back into Jan-Mar OR)

2. yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close
   -> same base + weekly delivery scale-in add-on (1 unit, 2R, leg stop)
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import List, Optional

from .broker_like_replays import BrokerReplaySpec, _runtime_config
from .engine import Engine, bars_from_csv
from .fx_data import ensure_eurusd_platform_files
from .models import StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
MARKET = "eurusd"
TICK = 0.00001
FEE_PER_UNIT = 7.0


VARIANT_SPECS: List[BrokerReplaySpec] = [
    BrokerReplaySpec(
        name="Yearly ORB swing-stop scaleout3 inside-range / range-close",
        slug="yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close",
        strategy_type="yearly_orb_scaleout3",
        max_contracts=3,
        config={
            "or_start_month": 1,
            "or_end_month": 3,
            "trade_start_month": 4,
            "trade_end_month": 12,
            "batch_qty": 1,
            "tp25_frac": 0.25,
            "tp_full_mult": 1.0,
            "require_fresh_break": True,
            "entry_mode": "limit_retest",
            "delivery_scalein": False,
        },
        notes=(
            "Research twin of yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close. "
            "Limit retest, inside-range swing stop, full OR range-close."
        ),
    ),
    BrokerReplaySpec(
        name="Yearly ORB delivery scale-in weekly swings + range-close",
        slug="yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close",
        strategy_type="yearly_orb_scaleout3",
        max_contracts=4,
        config={
            "or_start_month": 1,
            "or_end_month": 3,
            "trade_start_month": 4,
            "trade_end_month": 12,
            "batch_qty": 1,
            "tp25_frac": 0.25,
            "tp_full_mult": 1.0,
            "require_fresh_break": True,
            "entry_mode": "limit_retest",
            "delivery_scalein": True,
            "delivery_scale_swing_timeframe": "weekly",
            "delivery_scale_qty": 1,
            "delivery_target_R": 2.0,
        },
        notes=(
            "Research twin of yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close. "
            "Base scaleout3 + weekly delivery scale-in (limit=signal close, leg stop, 2R)."
        ),
    ),
]


def run(output_root: Path, force: bool = False) -> None:
    ensure_eurusd_platform_files(REPO)
    daily_path = REPO / "fx" / "eurusd_daily.csv"
    if not daily_path.exists():
        raise FileNotFoundError(daily_path)

    output_root.mkdir(parents=True, exist_ok=True)
    bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    progress = output_root / "progress.log"
    results = []

    def log(msg: str) -> None:
        line = msg.rstrip() + "\n"
        progress.write_text(progress.read_text(encoding="utf-8") + line if progress.exists() else line, encoding="utf-8")
        print(line, end="")

    log("Loaded %d EURUSD daily bars" % len(bars))

    for spec in VARIANT_SPECS:
        strategy_id = "%s_%s" % (MARKET, spec.slug)
        state_root = output_root / "states" / strategy_id
        log("START %s" % strategy_id)
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
            notes=spec.notes + " fee=$%.2f/unit; point_value=$%.0f." % (FEE_PER_UNIT, POINT_VALUES[INSTRUMENT]),
            output_root=output_root / "audits",
            fee_per_unit=FEE_PER_UNIT,
        )
        ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        results.append((spec, audit, ratio))
        log(
            "DONE %s units=%d trades=%d Net=$%.2f CloseDD=$%.2f StressDD=$%.2f Net/Stress=%.2f max_open=%d"
            % (
                strategy_id,
                audit.units,
                audit.trades,
                audit.net_usd,
                audit.close_mtm_dd_usd,
                audit.intrabar_mtm_dd_usd,
                ratio,
                audit.max_open_units,
            )
        )

    lines = [
        "# EURUSD Yearly ORB research variants (broker-like)",
        "",
        "Driver: `live/eurusd_yearly_orb_variants_replay.py` via `Engine` + `PaperBroker`.",
        "",
        "| Candidate | Units | Trades | Net | Close DD | Stress DD | Max open | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for spec, audit, ratio in results:
        lines.append(
            "| %s | %d | %d | $%.2f | $%.2f | $%.2f | %d | %.2f |"
            % (
                spec.slug,
                audit.units,
                audit.trades,
                audit.net_usd,
                audit.close_mtm_dd_usd,
                audit.intrabar_mtm_dd_usd,
                audit.max_open_units,
                ratio,
            )
        )
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        output_paths=[output_root / "SUMMARY.md"],
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        causality_mode="audit",
        extra={"driver": "eurusd_yearly_orb_variants_replay", "variants": [s.slug for s in VARIANT_SPECS]},
    )
    log("Wrote %s" % (output_root / "SUMMARY.md"))


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_yearly_orb_research_variants",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    run(args.output_root, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
