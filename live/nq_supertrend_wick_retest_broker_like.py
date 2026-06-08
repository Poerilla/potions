from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import AuditResult, audit_units, units_from_live_fills
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class ReplayResult:
    strategy_id: str
    state_root: Path
    audit: AuditResult


def resample_signal_bars(rth: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return rth.copy()
    return (
        rth.resample("%dmin" % minutes, label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def load_signal_bars(*, market: str, instrument: str, st_minutes: int, max_days: Optional[int] = None, start: Optional[date] = None) -> List[Bar]:
    cfg = MARKETS[market]
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    bars: List[Bar] = []
    sessions = sorted(by_day.keys())
    if start is not None:
        sessions = [session for session in sessions if session >= start]
    if max_days is not None:
        sessions = sessions[:max_days]
    for session in sessions:
        rth = _rth_bars(by_day.get(session), session)
        if rth.empty:
            continue
        signal = resample_signal_bars(rth, st_minutes)
        for ts, row in signal.iterrows():
            bars.append(
                Bar(
                    instrument=instrument,
                    timeframe="%dm" % st_minutes,
                    ts=pd.Timestamp(ts).isoformat(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    complete=True,
                    source=str(cfg.dbn_path),
                )
            )
    return bars


def run(
    *,
    output_root: Path,
    market: str = "nq",
    st_minutes: int = 3,
    target_pts: float = 50.0,
    max_days: Optional[int] = None,
    start: Optional[date] = None,
    force: bool = True,
    quiet: bool = True,
) -> ReplayResult:
    cfg = MARKETS[market]
    instrument = cfg.instrument
    strategy_id = "%s_%dm_st_wick_retest_target%g" % (market, st_minutes, target_pts)
    state_root = output_root / "states" / strategy_id
    output_root.mkdir(parents=True, exist_ok=True)
    if force and state_root.exists():
        shutil.rmtree(state_root)

    print("Loading %s %dm RTH bars..." % (instrument, st_minutes), flush=True)
    bars = load_signal_bars(market=market, instrument=instrument, st_minutes=st_minutes, max_days=max_days, start=start)
    print("  %s bars" % f"{len(bars):,}", flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="supertrend_wick_retest",
        version="v1",
        instrument=instrument,
        broker_instrument=instrument,
        account_mode="paper",
        enabled=True,
        timeframes="%dm" % st_minutes,
        max_contracts=1,
        max_open_orders=8,
        config_json=json.dumps(
            {
                "timeframe": "%dm" % st_minutes,
                "atr_len": 14,
                "atr_mult": 2.0,
                "target_pts": target_pts,
                "tick_size": 0.25,
                "entry_qty": 1,
                "max_trades_per_day": 4,
                "entry_cutoff": "15:45",
                "eod_cutoff": "15:57" if st_minutes == 3 else "15:59",
                "record_levels": False,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        tick_size={instrument: 0.25},
        notification_sink=NullNotificationSink() if quiet else None,
        verification_provider=QuietPaperVerificationProvider() if quiet else None,
        emit_order_alerts=not quiet,
        broker_log_events=not quiet,
        broker_persist_modifications=not quiet,
    )
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 50000 == 0:
            print("  replayed %d/%d bars" % (idx, len(bars)), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(fills_path, strategy_id)
    audit = audit_units(
        name="%s %dm Supertrend Wick-Retest Target %g (StrategyPlugin)" % (instrument, st_minutes, target_pts),
        slug=strategy_id,
        source=fills_path,
        bar_source=Path(MARKETS[market].dbn_path),
        bars=read_bars_from_engine_bars(bars),
        units=units,
        instrument=instrument,
        notes=(
            "Broker-like replay through Engine + PaperBroker. "
            "%dm Supertrend ATR(14)x2 wick touch, next-bar-open market entry, "
            "1-left/2-right swing confirmation, %g point fixed target, close-through-ST exit, "
            "max 4 trades/day, slippage=%g tick, fee=$%.2f/unit."
            % (st_minutes, target_pts, DEFAULT_SLIPPAGE_TICKS, DEFAULT_FEE_PER_UNIT)
        ),
        output_root=output_root / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    _write_summary(output_root, strategy_id, state_root, audit, st_minutes, target_pts, market)
    return ReplayResult(strategy_id=strategy_id, state_root=state_root, audit=audit)


def read_bars_from_engine_bars(bars: List[Bar]):
    from .replay_audit import Bar as AuditBar

    return [AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars]


def _write_summary(
    output_root: Path,
    strategy_id: str,
    state_root: Path,
    audit: AuditResult,
    st_minutes: int,
    target_pts: float,
    market: str,
) -> None:
    unit_fills_path = output_root / "audits" / strategy_id / strategy_id / "unit_fills.csv"
    pf = _fee_adjusted_profit_factor(unit_fills_path, DEFAULT_FEE_PER_UNIT)
    win_rate = 100.0 * audit.win_units / audit.units if audit.units else 0.0
    net_over_stress = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    pf_text = "inf" if math.isinf(pf) else "%.2f" % pf
    lines = [
        "# NQ 3m Supertrend Wick-Retest Target 50 Broker-Like Replay",
        "",
        "This is the larger-history `StrategyPlugin` version of the sample-100 prototype.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Market | %s |" % market.upper(),
        "| Signal timeframe | %dm |" % st_minutes,
        "| Target | %.1f pts |" % target_pts,
        "| Trades | %d |" % audit.trades,
        "| Units | %d |" % audit.units,
        "| Win rate | %.1f%% |" % win_rate,
        "| Net USD | $%s |" % f"{audit.net_usd:,.2f}",
        "| Profit factor | %s |" % pf_text,
        "| Closed DD USD | $%s |" % f"{audit.close_mtm_dd_usd:,.2f}",
        "| Intrabar stress DD USD | $%s |" % f"{audit.intrabar_mtm_dd_usd:,.2f}",
        "| Max open units | %d |" % audit.max_open_units,
        "| Net / stress | %.2f |" % net_over_stress,
        "",
        "State root: `%s`" % state_root,
        "",
        "Files:",
        "",
        "- [`unit_fills.csv`](audits/%s/%s/unit_fills.csv)" % (strategy_id, strategy_id),
        "- [`equity_curve.csv`](audits/%s/%s/equity_curve.csv)" % (strategy_id, strategy_id),
        "- [`fills.csv`](states/%s/fills.csv)" % strategy_id,
        "",
        audit.notes,
        "",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    _write_exit_reason_summary(unit_fills_path, output_root / "exit_reason_summary.csv")
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)
    print(
        "Trades=%d Net=$%s PF=%s Stress=$%s Net/Stress=%.2f"
        % (audit.trades, f"{audit.net_usd:,.2f}", pf_text, f"{audit.intrabar_mtm_dd_usd:,.2f}", net_over_stress),
        flush=True,
    )


def _write_exit_reason_summary(unit_fills_path: Path, out_path: Path) -> None:
    rows = []
    if unit_fills_path.exists():
        with unit_fills_path.open("r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    by_reason: dict[str, list[float]] = {}
    for row in rows:
        reason = row.get("exit_reason", "")
        usd = float(row.get("usd") or row.get("net_usd") or row.get("pnl_usd") or 0.0)
        by_reason.setdefault(reason, []).append(usd)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["exit_reason", "units", "net_usd", "avg_usd"])
        writer.writeheader()
        for reason, vals in sorted(by_reason.items()):
            writer.writerow(
                {
                    "exit_reason": reason,
                    "units": len(vals),
                    "net_usd": "%.2f" % sum(vals),
                    "avg_usd": "%.2f" % (sum(vals) / len(vals) if vals else 0.0),
                }
            )


def _fee_adjusted_profit_factor(unit_fills_path: Path, fee_per_unit: float) -> float:
    gross_win = 0.0
    gross_loss = 0.0
    if not unit_fills_path.exists():
        return 0.0
    with unit_fills_path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            net = float(row.get("usd") or row.get("net_usd") or row.get("pnl_usd") or 0.0)
            if "usd" not in row and "net_usd" not in row and "pnl_usd" not in row:
                net = float(row.get("points") or 0.0) * 20.0 - float(fee_per_unit)
            if net > 0:
                gross_win += net
            else:
                gross_loss += abs(net)
    return gross_win / gross_loss if gross_loss else math.inf


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run broker-like NQ Supertrend wick-retest replay.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/nq_3m_st_wick_retest_target50_broker_like")
    parser.add_argument("--market", default="nq", choices=sorted(MARKETS.keys()))
    parser.add_argument("--st-minutes", type=int, default=3)
    parser.add_argument("--target-pts", type=float, default=50.0)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--start", default="")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    start = pd.Timestamp(args.start).date() if args.start else None
    run(
        output_root=args.output_root,
        market=args.market,
        st_minutes=args.st_minutes,
        target_pts=args.target_pts,
        max_days=args.max_days,
        start=start,
        force=not args.no_force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
