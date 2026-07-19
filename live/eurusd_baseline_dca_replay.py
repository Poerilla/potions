"""DCA scale-in on the promoted EURUSD hourly ST+PMC FX baseline.

Baseline: sl25/tp75 3R, ma_filter=bull_prior_only, single unit.
DCA: while thesis still holds, rest another ST-retest limit (own 25/75 bracket)
up to max_adds units.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import List, Optional

from .engine import Engine
from .eurusd_overnight_sweep import INSTRUMENT, MARKET, PIP, TICK, _fx_spread, _load_hourly_bars
from .fx_data import ensure_eurusd_platform_files
from .hourly_st_pmc_retest_replay import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS, read_bars_from_engine_bars
from .models import StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import audit_units, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
OUT_DEFAULT = REPO / "live" / "state" / "eurusd_baseline_dca"
BASELINE_NAME = "sl25_tp75_3r_ma_bull_prior"
STOP_PTS = 25 * PIP
TARGET_PTS = 75 * PIP


def _run_one(
    *,
    bars,
    one_m: Path,
    daily_path: Path,
    out: Path,
    max_adds: int,
    force: bool,
    use_fx_spread: bool,
) -> dict:
    dca = max_adds > 1
    slug = BASELINE_NAME if not dca else "%s_dca_x%d" % (BASELINE_NAME, max_adds)
    strategy_id = "%s_hourly_st_pmc_%s" % (MARKET, slug)
    state_root = out / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)

    config = {
        "daily_bars_path": str(daily_path),
        "atr_len": 14,
        "atr_mult": 3.0,
        "stop_pts": STOP_PTS,
        "target_pts": TARGET_PTS,
        "tick_size": TICK,
        "entry_qty": 1,
        "tp1_qty": 1,
        "runner_qty": 0,
        "runner_target_pts": 0.0,
        "runner_stop_to_be_after_tp1": False,
        "ma_filter": "bull_prior_only",
        "close_against_entry_exit": False,
        "st_flip_exit": False,
        "pmc_cross_exit": False,
        "dca_enabled": dca,
        "add_qty": 1,
        "max_adds": max_adds,
    }
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="hourly_st_pmc_retest",
        version="v2",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="1h",
        max_contracts=max(1, max_adds),
        max_open_orders=32,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])

    engine_kwargs = dict(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        tick_size={INSTRUMENT: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    if use_fx_spread:
        engine_kwargs["spread_model"] = _fx_spread()

    engine = Engine(**engine_kwargs)
    print("Replaying %s (%d bars, max_adds=%d)..." % (strategy_id, len(bars), max_adds), flush=True)
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 20000 == 0:
            print("  %d/%d" % (idx, len(bars)), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(fills_path, strategy_id)
    audit = audit_units(
        name="EURUSD baseline ST+PMC DCA x%d" % max_adds,
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m,
        bars=read_bars_from_engine_bars(list(bars)),
        units=units,
        instrument=INSTRUMENT,
        notes=(
            "Baseline 25/75 3R bull_prior_only + DCA max_adds=%d (ST retest limit adds). "
            "fee=$%.2f/unit; slippage=%g; fx_spread=%s."
            % (max_adds, DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS, use_fx_spread)
        ),
        output_root=out / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    row = {
        "strategy_id": strategy_id,
        "max_adds": max_adds,
        "dca_enabled": dca,
        "trades": audit.trades,
        "units": audit.units,
        "net_usd": round(audit.net_usd, 2),
        "closed_dd_usd": round(audit.close_mtm_dd_usd, 2),
        "stress_dd_usd": round(audit.intrabar_mtm_dd_usd, 2),
        "net_over_stress": round(ratio, 3),
        "win_units": audit.win_units,
        "win_rate_pct": round(100.0 * audit.win_units / audit.units, 2) if audit.units else 0.0,
        "max_open_units": audit.max_open_units,
        "vs_baseline": round(audit.net_usd - 23533.68, 2),
    }
    print(json.dumps(row, indent=2), flush=True)
    return row


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD FX baseline + DCA replay")
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-fx-spread", action="store_true", help="Match bare run_variant (no FX spread)")
    parser.add_argument(
        "--max-adds",
        type=str,
        default="1,2,3,5",
        help="Comma list of max_adds (1 = baseline control)",
    )
    args = parser.parse_args(argv)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    one_m, daily = ensure_eurusd_platform_files(REPO)
    print("Loading hourly bars...", flush=True)
    bars = _load_hourly_bars(one_m)
    print("  %d bars" % len(bars), flush=True)

    max_adds_list = [max(1, int(x.strip())) for x in args.max_adds.split(",") if x.strip()]
    rows = []
    for n in max_adds_list:
        rows.append(
            _run_one(
                bars=bars,
                one_m=one_m,
                daily_path=daily,
                out=out,
                max_adds=n,
                force=args.force,
                use_fx_spread=not args.no_fx_spread,
            )
        )

    baseline = next((r for r in rows if r["max_adds"] == 1), None)
    lines = [
        "# EURUSD FX baseline + DCA",
        "",
        "Promoted sleeve `sl25_tp75_3r_ma_bull_prior` with optional ST-retest DCA adds",
        "(each add = own 25/75 bracket at current SuperTrend, while thesis holds).",
        "",
        "| max_adds | Net | Stress DD | Net/Stress | Units | WR | Max open | vs baseline net |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| %d | $%s | $%s | %.3f | %d | %.1f%% | %d | $%+.0f |"
            % (
                r["max_adds"],
                f"{r['net_usd']:,.2f}",
                f"{r['stress_dd_usd']:,.2f}",
                r["net_over_stress"],
                r["units"],
                r["win_rate_pct"],
                r["max_open_units"],
                r["vs_baseline"],
            )
        )
    promoted = 23533.68
    stress_b = 15745.46
    lines.extend(
        [
            "",
            "Promoted pack reference: net **$%.2f** / stress **−$%.2f** / Net/Stress **1.49**."
            % (promoted, stress_b),
            "FX half-spread: **%s**. Fee $%.2f/unit."
            % ("on" if not args.no_fx_spread else "off", DEFAULT_FEE_PER_UNIT),
            "",
            "Control (max_adds=1) should be near the promoted tape; DCA rows test scale-in.",
            "",
        ]
    )
    if baseline:
        lines.append(
            "This-run control: net $%.2f / stress $%.2f / Net/Stress %.3f."
            % (baseline["net_usd"], baseline["stress_dd_usd"], baseline["net_over_stress"])
        )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
