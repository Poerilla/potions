from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import AuditResult, audit_units, read_bars, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any, resample_hourly

REPO = Path(__file__).resolve().parents[1]

DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class ReplayResult:
    strategy_id: str
    state_root: Path
    audit: AuditResult


class ReplayLock:
    def __init__(self, output_root: Path, name: str):
        self.path = output_root / ("%s.lock" % name)
        self.fd: Optional[int] = None

    def __enter__(self) -> "ReplayLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = self.path.read_text(encoding="utf-8").strip() if self.path.exists() else ""
            pid_text = owner.splitlines()[0].strip() if owner else ""
            if pid_text.isdigit() and _pid_is_running(int(pid_text)):
                raise RuntimeError("Replay already running for this output root: pid %s (%s)" % (pid_text, self.path))
            self.path.unlink(missing_ok=True)
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        payload = "%d\n%s\n" % (os.getpid(), os.getcwd())
        os.write(self.fd, payload.encode("utf-8"))
        os.close(self.fd)
        self.fd = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.path.unlink(missing_ok=True)


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def load_hourly_bars(dbn: Path, instrument: str = "YM") -> List[Bar]:
    gby = load_1m_by_ny_date_any(dbn.resolve(), instrument.lower())
    hourly_df = resample_hourly(concat_all_1m(gby))
    bars: List[Bar] = []
    for ts, row in hourly_df.iterrows():
        bars.append(
            Bar(
                instrument=instrument,
                timeframe="1h",
                ts=pd.Timestamp(ts).isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(dbn),
            )
        )
    return bars


def run(
    *,
    output_root: Path,
    dbn: Path,
    daily_path: Path,
    instrument: str = "YM",
    market: str = "ym",
    stop_pts: float = 50.0,
    target_pts: float = 150.0,
    force: bool = True,
    quiet: bool = True,
    max_bars: Optional[int] = None,
) -> ReplayResult:
    output_root.mkdir(parents=True, exist_ok=True)
    strategy_id = "%s_hourly_st_pmc_retest" % market
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)

    print("Loading %s hourly bars for StrategyPlugin replay..." % instrument, flush=True)
    bars = load_hourly_bars(dbn, instrument=instrument)
    if max_bars is not None:
        bars = bars[:max_bars]
    print("  %s hourly bars" % f"{len(bars):,}", flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="hourly_st_pmc_retest",
        version="v1",
        instrument=instrument,
        broker_instrument=instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1h",
        max_contracts=1,
        max_open_orders=8,
        config_json=json.dumps(
            {
                "daily_bars_path": str(daily_path),
                "stop_pts": stop_pts,
                "target_pts": target_pts,
                "tick_size": 1.0,
                "entry_qty": 1,
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
        notification_sink=NullNotificationSink() if quiet else None,
        verification_provider=QuietPaperVerificationProvider() if quiet else None,
        emit_order_alerts=not quiet,
        broker_log_events=not quiet,
        broker_persist_modifications=not quiet,
    )
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 10000 == 0:
            print("  replayed %d/%d bars" % (idx, len(bars)), flush=True)

    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()
    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(fills_path, strategy_id)
    audit_bars = read_bars_from_engine_bars(bars)
    audit = audit_units(
        name="%s Hourly ST + PMC Retest (StrategyPlugin)" % instrument,
        slug=strategy_id,
        source=fills_path,
        bar_source=dbn,
        bars=audit_bars,
        units=units,
        instrument=instrument,
        notes=(
            "Hardened StrategyPlugin replay via Engine + PaperBroker. "
            "Hourly limit at ST stop filtered by prior month close; "
            "%g pt stop / %g pt target; slippage=%g tick; fee=$%.2f/unit."
            % (stop_pts, target_pts, DEFAULT_SLIPPAGE_TICKS, DEFAULT_FEE_PER_UNIT)
        ),
        output_root=output_root / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    _write_summary(output_root, audit, strategy_id, state_root)
    return ReplayResult(strategy_id=strategy_id, state_root=state_root, audit=audit)


def read_bars_from_engine_bars(bars: List[Bar]):
    from .replay_audit import Bar as AuditBar

    return [
        AuditBar(
            ts=b.ts,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
        )
        for b in bars
    ]


def _write_summary(output_root: Path, audit: AuditResult, strategy_id: str, state_root: Path) -> None:
    unit_fills_path = output_root / "audits" / strategy_id / strategy_id / "unit_fills.csv"
    pf = _fee_adjusted_profit_factor(unit_fills_path, DEFAULT_FEE_PER_UNIT)
    pf_s = "%.2f" % pf if pf != float("inf") else "inf"
    win_rate = 100.0 * audit.win_units / audit.units if audit.units else 0.0
    net_over_stress = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    lines = [
        "# YM Hourly ST + PMC StrategyPlugin Replay",
        "",
        "Live-orderable path through `Engine + PaperBroker` with realism defaults.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Trades | %d |" % audit.trades,
        "| Units | %d |" % audit.units,
        "| Win rate | %.1f%% |" % win_rate,
        "| Net USD | $%s |" % f"{audit.net_usd:,.2f}",
        "| Profit factor | %s |" % pf_s,
        "| Closed DD USD | $%s |" % f"{audit.close_mtm_dd_usd:,.2f}",
        "| Intrabar stress DD USD | $%s |" % f"{audit.intrabar_mtm_dd_usd:,.2f}",
        "| Net / stress | %.2f |" % net_over_stress,
        "",
        "State root: `%s`" % state_root,
        "",
        audit.notes,
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (output_root / "SUMMARY.md"), flush=True)
    print(
        "Trades=%d Net=$%s PF=%s Net/Stress=%.2f"
        % (audit.trades, f"{audit.net_usd:,.2f}", pf_s, net_over_stress),
        flush=True,
    )


def _fee_adjusted_profit_factor(unit_fills_path: Path, fee_per_unit: float) -> float:
    if not unit_fills_path.exists():
        return float("inf")
    gross_win = 0.0
    gross_loss = 0.0
    with unit_fills_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pnl = float(row.get("usd") or 0.0) - fee_per_unit
            if pnl > 0:
                gross_win += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)
    return gross_win / gross_loss if gross_loss else float("inf")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay hourly ST+PMC strategy through live Engine.")
    parser.add_argument(
        "--dbn",
        type=Path,
        default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    )
    parser.add_argument("--daily", type=Path, default=REPO / "ym" / "ym_daily.csv")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=REPO / "live" / "state" / "hourly_st_pmc_retest",
    )
    parser.add_argument("--stop-pts", type=float, default=50.0)
    parser.add_argument("--target-pts", type=float, default=150.0)
    parser.add_argument("--max-bars", type=int, default=None)
    parser.add_argument("--no-quiet", action="store_true", help="Write order alerts and verification rows during replay.")
    args = parser.parse_args(argv)
    with ReplayLock(args.out_root, "hourly_st_pmc_retest_replay"):
        run(
            output_root=args.out_root,
            dbn=args.dbn,
            daily_path=args.daily,
            stop_pts=args.stop_pts,
            target_pts=args.target_pts,
            quiet=not args.no_quiet,
            max_bars=args.max_bars,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
