"""EURUSD WO gap reversal + weekly-mid MA500 companion overnight jobs."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .replay_manifest import write_run_manifest
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
MARKET = "eurusd"
PIP = 0.0001
TICK = 0.00001
FEE = 7.0


def _ensure() -> None:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)


def _log(path: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), msg)
    print(line, flush=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _audit_bars(bars: List[Bar]):
    from .replay_audit import Bar as AuditBar

    return [AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars]


def load_hourly(one_m: Path) -> List[Bar]:
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    hourly = resample_hourly(concat_all_1m(gby))
    bars: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars.append(
            Bar(
                instrument=INSTRUMENT,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
        )
    return bars


def load_15m(one_m: Path) -> List[Bar]:
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    one = concat_all_1m(gby)
    frame = (
        one.resample("15min", label="left", closed="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
        .dropna(subset=["open"])
    )
    bars: List[Bar] = []
    for ts, row in frame.iterrows():
        bars.append(
            Bar(
                instrument=INSTRUMENT,
                timeframe="15m",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
        )
    return bars


def run_wo_gap(output_root: Path, one_m: Path, force: bool) -> None:
    _ensure()
    log = output_root / "PROGRESS.log"
    strategy_id = "%s_wo_gap_reversal" % MARKET
    _log(log, "START %s" % strategy_id)
    bars = load_hourly(one_m)
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="wo_gap_reversal",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1h",
                    max_contracts=2,
                    max_open_orders=12,
                    config_json=json.dumps(
                        {
                            "gap_pct": 0.55,
                            "use_swing_filter": True,
                            "max_trades_per_week": 2,
                            "stop_after_win": True,
                            "max_fill_wait_bars": 6,
                            "stop_pts": 50 * PIP,
                            "tp1_pts": 50 * PIP,
                            "runner_target_pts": 300 * PIP,
                            "tp1_qty": 1,
                            "runner_qty": 1,
                            "tick_size": TICK,
                            "short_only": False,
                            "record_levels": False,
                        },
                        sort_keys=True,
                    ),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=1.0,
        tick_size={INSTRUMENT: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 25000 == 0:
            _log(log, "  %s %d/%d" % (strategy_id, idx, len(bars)))
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()
    units = units_from_live_fills(state_root / "fills.csv", strategy_id, bars[-1].ts, bars[-1].close)
    audit = audit_units(
        name="EURUSD WO Gap Reversal",
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=one_m,
        bars=_audit_bars(bars),
        units=units,
        instrument=INSTRUMENT,
        notes="EURUSD pip-scaled WO gap (50/50/300 pips).",
        output_root=output_root / "audits",
        fee_per_unit=FEE,
    )
    ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    _log(log, "DONE %s Net=$%.2f Net/Stress=%.2f" % (strategy_id, audit.net_usd, ratio))
    (output_root / "wo_gap_summary.txt").write_text(
        "strategy_id=%s net=%.2f stress=%.2f net_stress=%.2f units=%d trades=%d\n"
        % (strategy_id, audit.net_usd, audit.intrabar_mtm_dd_usd, ratio, audit.units, audit.trades),
        encoding="utf-8",
    )


def run_weekly_mid(output_root: Path, one_m: Path, force: bool) -> None:
    _ensure()
    log = output_root / "PROGRESS.log"
    strategy_id = "%s_weekly_mid_ma500_bias" % MARKET
    _log(log, "START %s" % strategy_id)
    bars = load_15m(one_m)
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="weekly_mid_ma500_bias",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="15m",
                    max_contracts=1,
                    max_open_orders=8,
                    config_json=json.dumps(
                        {
                            "ma_window": 500,
                            "entry_qty": 1,
                            "max_trades_per_week": 6,
                            "risk_pts": 50 * PIP,
                            "target_pts": 300 * PIP,
                            "tick_size": TICK,
                            "record_levels": False,
                            "stop_after_weekly_win": False,
                        },
                        sort_keys=True,
                    ),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=1.0,
        tick_size={INSTRUMENT: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 50000 == 0:
            _log(log, "  %s %d/%d" % (strategy_id, idx, len(bars)))
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()
    units = units_from_live_fills(state_root / "fills.csv", strategy_id, bars[-1].ts, bars[-1].close)
    audit = audit_units(
        name="EURUSD Weekly Mid MA500 Bias",
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=one_m,
        bars=_audit_bars(bars),
        units=units,
        instrument=INSTRUMENT,
        notes="EURUSD 15m weekly-mid MA500 bias StrategyPlugin.",
        output_root=output_root / "audits",
        fee_per_unit=FEE,
    )
    ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    _log(log, "DONE %s Net=$%.2f Net/Stress=%.2f" % (strategy_id, audit.net_usd, ratio))
    (output_root / "weekly_mid_summary.txt").write_text(
        "strategy_id=%s net=%.2f stress=%.2f net_stress=%.2f units=%d trades=%d\n"
        % (strategy_id, audit.net_usd, audit.intrabar_mtm_dd_usd, ratio, audit.units, audit.trades),
        encoding="utf-8",
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=REPO / "live" / "state" / "eurusd_overnight_extras")
    parser.add_argument("--skip-wo", action="store_true")
    parser.add_argument("--skip-weekly-mid", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    one_m, _daily = ensure_eurusd_platform_files(REPO, force=False)
    if not args.skip_wo:
        try:
            run_wo_gap(args.output_root, one_m, force=not args.no_force)
        except Exception as exc:
            _log(args.output_root / "PROGRESS.log", "FAIL wo_gap: %s" % exc)
    if not args.skip_weekly_mid:
        try:
            run_weekly_mid(args.output_root, one_m, force=not args.no_force)
        except Exception as exc:
            _log(args.output_root / "PROGRESS.log", "FAIL weekly_mid: %s" % exc)
    write_run_manifest(
        args.output_root,
        data_inputs=[one_m],
        output_paths=[args.output_root / "PROGRESS.log"],
        extra={"driver": "eurusd_overnight_extras"},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
