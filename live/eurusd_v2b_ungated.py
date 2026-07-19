"""Run ungated EURUSD v2b OCO with explicit sizing (default S_1_1_1)."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .eurusd_overnight_sweep import FEE_PER_UNIT, INSTRUMENT, MARKET, TICK, _fx_spread, _has_full_rth_close
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MarketConfig, _regime_dates
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_START = date(2015, 1, 2)


def run(
    *,
    output_root: Path,
    entry_qty: int,
    tp1_qty: int,
    tp2_qty: int,
    start: date,
    force: bool,
    max_days: Optional[int] = None,
) -> dict:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    one_m, daily = ensure_eurusd_platform_files(REPO, force=False)
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    slug = "eurusd_v2b_oco_S_%d_%d_%d" % (tp1_qty, tp2_qty, runner)
    strategy_id = slug
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = MarketConfig(
        market=MARKET,
        instrument=INSTRUMENT,
        daily_path=daily,
        dbn_path=one_m,
        start=start,
        fee_per_unit=FEE_PER_UNIT,
    )
    print("Loading EURUSD 1m for ungated %s..." % slug, flush=True)
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    print("  regime sessions: %d" % len(regime_dates), flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "market": MARKET,
        "mode": "oco_then_reverse",
        "entry_qty": entry_qty,
        "tp1_qty": tp1_qty,
        "tp2_qty": tp2_qty,
        "tick_size": TICK,
        "use_regime_filter": True,
        "prior_opposite_only": False,
        "start": start.isoformat(),
        "regime_dates": [d.isoformat() for d in regime_dates],
        "record_levels": False,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="v2b_scaleout",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=entry_qty,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={INSTRUMENT: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=_fx_spread()),
    )
    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(regime_dates, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=INSTRUMENT,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 250 == 0:
            print("  %s %d/%d" % (strategy_id, idx, len(regime_dates)), flush=True)
    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=INSTRUMENT,
        fee_per_unit=FEE_PER_UNIT,
    )
    result = {
        "strategy_id": strategy_id,
        "sizing": "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner),
        "entry_qty": entry_qty,
        "regime_days": len(regime_dates),
        "start": start.isoformat(),
        "units": len(units),
        "trades": len({u.trade_id for u in units}),
        "net_usd": float(audit["net_usd"]),
        "closed_dd_usd": float(audit["closed_dd_usd"]),
        "intrabar_stress_dd_usd": float(audit["intrabar_stress_dd_usd"]),
        "max_open_units": int(audit["max_open_units"]),
        "win_rate": float(audit["win_rate"]),
        "profit_factor": float(audit["profit_factor"]),
    }
    result["net_over_stress"] = (
        result["net_usd"] / abs(result["intrabar_stress_dd_usd"]) if result["intrabar_stress_dd_usd"] else 0.0
    )
    pd.DataFrame([result]).to_csv(output_root / "summary.csv", index=False)
    lines = [
        "# EURUSD Ungated v2b %s" % result["sizing"],
        "",
        "All-day OCO `v2b_scaleout` with **no** prior-opposed ST+PMC gate.",
        "",
        "| Sizing | Sessions | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %s | %d | %d | %d | $%.2f | $%.2f | $%.2f | %.2f | %.1f | %.3f |"
        % (
            result["sizing"],
            result["regime_days"],
            result["trades"],
            result["units"],
            result["net_usd"],
            result["closed_dd_usd"],
            result["intrabar_stress_dd_usd"],
            result["net_over_stress"],
            result["win_rate"],
            result["profit_factor"],
        ),
        "",
        "- Start: **%s**" % start.isoformat(),
        "- Entry / TP1 / TP2 / runner: **%d / %d / %d / %d**" % (entry_qty, tp1_qty, tp2_qty, runner),
        "",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[one_m, daily],
        output_paths=[output_root / "summary.csv", output_root / "INDEX.md", state_root / "fills.csv"],
        strategy_config=payload,
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "spread_model": "fx_half_pip"},
        causality_mode="audit",
        extra={"driver": "eurusd_v2b_ungated"},
    )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ungated EURUSD v2b OCO sizing replay.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_v2b_ungated_S_1_1_1",
    )
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--entry-qty", type=int, default=3)
    parser.add_argument("--tp1-qty", type=int, default=1)
    parser.add_argument("--tp2-qty", type=int, default=1)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    result = run(
        output_root=args.output_root,
        entry_qty=args.entry_qty,
        tp1_qty=args.tp1_qty,
        tp2_qty=args.tp2_qty,
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
    )
    print(
        "Wrote %s Net=$%.2f Net/Stress=%.2f"
        % (args.output_root / "INDEX.md", result["net_usd"], result["net_over_stress"]),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
