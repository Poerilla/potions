"""Broker-like EURUSD 15m SuperTrend flip-fade DCA replay."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Optional

from .engine import Engine
from .eurusd_intraday_st_dca_replay import (
    FEE_PER_HALF_LOT,
    HALF_LOT_POINT_VALUE,
    INSTRUMENT,
    NY,
    TICK,
    load_15m_bars,
)
from .eurusd_overnight_sweep import _fx_spread
from .fx_data import ensure_eurusd_platform_files
from .hourly_st_pmc_retest_replay import read_bars_from_engine_bars
from .models import StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
STRATEGY_ID = "eurusd_intraday_st_fade_dca_15m_0p5x5"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD 15m ST fade-DCA broker replay")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_intraday_st_fade_dca_broker",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    state_root = out / "states" / STRATEGY_ID
    if args.force and state_root.exists():
        shutil.rmtree(state_root)

    one_m_path, _daily = ensure_eurusd_platform_files(REPO)
    print("Loading 15m bars %s → %s (ST fade DCA) ..." % (args.start, args.end), flush=True)
    bars = load_15m_bars(one_m_path, args.start, args.end)
    print("  %d bars" % len(bars), flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=STRATEGY_ID,
        strategy_type="intraday_st_fade_dca",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="15m",
        max_contracts=5,
        max_open_orders=32,
        config_json=json.dumps(
            {
                "timeframe": "15m",
                "atr_len": 14,
                "atr_mult": 3.0,
                "add_qty": 1,
                "max_adds": 5,
                "tick_size": TICK,
                "session_gate": True,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])

    prev_pv = POINT_VALUES.get(INSTRUMENT)
    POINT_VALUES[INSTRUMENT] = HALF_LOT_POINT_VALUE

    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=1.0,
        tick_size={INSTRUMENT: TICK},
        spread_model=_fx_spread(),
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )

    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 20000 == 0:
            print("  replayed %d/%d" % (idx, len(bars)), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    if not fills_path.exists():
        raise SystemExit("No fills written at %s" % fills_path)
    units = units_from_live_fills(fills_path, STRATEGY_ID)
    audit = audit_units(
        name="EURUSD 15m ST fade DCA 0.5×5",
        slug=STRATEGY_ID,
        source=fills_path,
        bar_source=one_m_path,
        bars=read_bars_from_engine_bars(bars),
        units=units,
        instrument=INSTRUMENT,
        notes=(
            "Fade ST flips with DCA toward new trail; 1R stop from entry→trail. "
            "Close-only stop; limit target at live ST. Unit=0.5 lot. Fee $%.2f/unit."
            % FEE_PER_HALF_LOT
        ),
        output_root=out / "audits" / STRATEGY_ID,
        fee_per_unit=FEE_PER_HALF_LOT,
    )
    if prev_pv is not None:
        POINT_VALUES[INSTRUMENT] = prev_pv

    ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    summary = {
        "strategy_id": STRATEGY_ID,
        "trades": audit.trades,
        "units": audit.units,
        "net_usd": round(audit.net_usd, 2),
        "closed_dd_usd": round(audit.close_mtm_dd_usd, 2),
        "stress_dd_usd": round(audit.intrabar_mtm_dd_usd, 2),
        "net_over_stress": round(ratio, 3),
        "win_units": audit.win_units,
        "win_rate_pct": round(100.0 * audit.win_units / audit.units, 2) if audit.units else 0.0,
        "max_open_units": audit.max_open_units,
        "window": "%s → %s" % (args.start, args.end),
        "unit_definition": "1 unit = 0.5 standard lot",
        "state_root": str(state_root),
        "vs_fx_baseline": (
            "upgrade candidate"
            if audit.net_usd > 0 and ratio >= 1.0
            else "not an upgrade"
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# EURUSD 15m ST flip-fade DCA — broker-like replay",
                "",
                "On ST flip: fade with DCA toward the new trail (1R stop = entry↔trail distance).",
                "",
                "| Metric | Value |",
                "|---|---:|",
                "| Net | $%s |" % f"{audit.net_usd:,.2f}",
                "| Intrabar stress DD | $%s |" % f"{audit.intrabar_mtm_dd_usd:,.2f}",
                "| Closed DD | $%s |" % f"{audit.close_mtm_dd_usd:,.2f}",
                "| Net / Stress | %.3f |" % ratio,
                "| Trades / Units | %d / %d |" % (audit.trades, audit.units),
                "| Win units %% | %.1f |"
                % (100.0 * audit.win_units / audit.units if audit.units else 0.0),
                "| Max open units | %d |" % audit.max_open_units,
                "| vs FX baseline | %s |" % summary["vs_fx_baseline"],
                "",
                "Window: %s → %s. Session: London 08:00 → NY 16:00." % (args.start, args.end),
                "Unit = 0.5 lot (PV $50,000). Fee $%.2f/unit." % FEE_PER_HALF_LOT,
                "",
                "States: `%s`" % state_root,
                "Audit: `%s`" % (out / "audits" / STRATEGY_ID),
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2), flush=True)
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
