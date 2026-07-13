from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .engine import Engine
from .hourly_st_pmc_loss_research import VariantConfig, variants
from .hourly_st_pmc_retest_replay import (
    DEFAULT_FEE_PER_UNIT,
    DEFAULT_SLIPPAGE_TICKS,
    read_bars_from_engine_bars,
)
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import AuditResult, audit_units, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any, resample_hourly


REPO = Path(__file__).resolve().parents[1]
TICK_SIZE = {
    "MNQ": 0.25,
    "NQ": 0.25,
    "MES": 0.25,
    "ES": 0.25,
    "MYM": 1.0,
    "YM": 1.0,
}
MARKET_CONFIGS = {
    "mnq": {
        "instrument": "MNQ",
        "daily": REPO / "mnq" / "mnq_daily.csv",
        "dbn": REPO / "mnq" / "raw" / "glbx-mdp3-20210304-20260303.ohlcv-1m.csv",
    },
    "nq": {
        "instrument": "NQ",
        "daily": REPO / "nq" / "nq_daily.csv",
        "dbn": REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
    },
    "es": {
        "instrument": "ES",
        "daily": REPO / "es" / "es_daily.csv",
        "dbn": REPO / "es" / "raw" / "glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst",
    },
    "mes": {
        "instrument": "MES",
        "daily": REPO / "mes" / "mes_daily.csv",
        "dbn": REPO / "mes" / "mes_1min_raw.csv",
    },
    "mym": {
        "instrument": "MYM",
        "daily": REPO / "mym" / "mym_daily.csv",
        "dbn": REPO / "mym" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
    },
    "ym": {
        "instrument": "YM",
        "daily": REPO / "ym" / "ym_daily.csv",
        "dbn": REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    },
}
_WORKER_BARS: Sequence[Bar] = []
_WORKER_ARGS: Optional[argparse.Namespace] = None


@dataclass(frozen=True)
class VariantReplayResult:
    market: str
    instrument: str
    variant: str
    strategy_id: str
    state_root: Path
    audit: AuditResult
    profit_factor: float

    @property
    def net_over_stress(self) -> float:
        return self.audit.net_usd / abs(self.audit.intrabar_mtm_dd_usd) if self.audit.intrabar_mtm_dd_usd else 0.0

    @property
    def win_rate(self) -> float:
        return 100.0 * self.audit.win_units / self.audit.units if self.audit.units else 0.0


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
                raise RuntimeError("Replay already running: pid %s (%s)" % (pid_text, self.path))
            self.path.unlink(missing_ok=True)
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(self.fd, ("%d\n" % os.getpid()).encode("utf-8"))
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
                ts=ts.isoformat(),
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


def config_json(cfg: VariantConfig, daily_path: Path, instrument: str) -> str:
    payload: Dict[str, object] = {
        "daily_bars_path": str(daily_path),
        "stop_pts": cfg.stop_pts,
        "target_pts": cfg.tp1_pts,
        "tick_size": TICK_SIZE.get(instrument.upper(), 0.25),
        "entry_qty": cfg.entry_qty,
        "tp1_qty": cfg.tp1_qty,
        "runner_qty": cfg.runner_qty,
        "runner_target_pts": cfg.runner_tp_pts or 0.0,
        "runner_stop_to_be_after_tp1": cfg.runner_stop_to_be_after_tp1,
        "ma_filter": cfg.ma_filter,
        "close_against_entry_exit": cfg.close_against_entry_exit,
        "st_flip_exit": cfg.st_flip_exit,
        "pmc_cross_exit": cfg.pmc_cross_exit,
        "record_levels": False,
    }
    return json.dumps(payload, sort_keys=True)


def run_variant(
    *,
    cfg: VariantConfig,
    bars: Sequence[Bar],
    output_root: Path,
    dbn: Path,
    daily_path: Path,
    instrument: str = "YM",
    market: str = "ym",
    force: bool = True,
    quiet: bool = True,
) -> VariantReplayResult:
    strategy_id = "%s_hourly_st_pmc_%s" % (market, cfg.name)
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="hourly_st_pmc_retest",
        version="v2",
        instrument=instrument,
        broker_instrument=instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1h",
        max_contracts=max(1, int(cfg.entry_qty)),
        max_open_orders=16,
        config_json=config_json(cfg, daily_path, instrument),
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
        if idx % 20000 == 0:
            print("  %s replayed %d/%d bars" % (cfg.name, idx, len(bars)), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(fills_path, strategy_id)
    audit = audit_units(
        name="%s Hourly ST + PMC %s (StrategyPlugin)" % (instrument, cfg.name),
        slug=strategy_id,
        source=fills_path,
        bar_source=dbn,
        bars=read_bars_from_engine_bars(list(bars)),
        units=units,
        instrument=instrument,
        notes=(
            "Engine + PaperBroker StrategyPlugin replay. Variant=%s; stop=%g; target=%g; "
            "tp1_qty=%d; runner_qty=%d; runner_target=%s; ma_filter=%s; "
            "close_against=%s; st_flip_exit=%s; pmc_cross_exit=%s; slippage=%g tick; fee=$%.2f/unit."
            % (
                cfg.name,
                cfg.stop_pts,
                cfg.tp1_pts,
                cfg.tp1_qty,
                cfg.runner_qty,
                cfg.runner_tp_pts,
                cfg.ma_filter,
                cfg.close_against_entry_exit,
                cfg.st_flip_exit,
                cfg.pmc_cross_exit,
                DEFAULT_SLIPPAGE_TICKS,
                DEFAULT_FEE_PER_UNIT,
            )
        ),
        output_root=output_root / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    pf = fee_adjusted_profit_factor(output_root / "audits" / strategy_id / strategy_id / "unit_fills.csv")
    return VariantReplayResult(
        market=market,
        instrument=instrument,
        variant=cfg.name,
        strategy_id=strategy_id,
        state_root=state_root,
        audit=audit,
        profit_factor=pf,
    )


def run_combined_variants(
    *,
    configs: Sequence[VariantConfig],
    bars: Sequence[Bar],
    output_root: Path,
    dbn: Path,
    daily_path: Path,
    instrument: str = "YM",
    market: str = "ym",
    force: bool = True,
    quiet: bool = True,
) -> List[VariantReplayResult]:
    state_root = output_root / "combined_state"
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instances: List[StrategyInstance] = []
    variant_by_strategy: Dict[str, VariantConfig] = {}
    for cfg in configs:
        strategy_id = "%s_hourly_st_pmc_%s" % (market, cfg.name)
        variant_by_strategy[strategy_id] = cfg
        instances.append(
            StrategyInstance(
                strategy_id=strategy_id,
                strategy_type="hourly_st_pmc_retest",
                version="v2",
                instrument=instrument,
                broker_instrument=instrument,
                account_mode="paper",
                enabled=True,
                timeframes="1h",
                max_contracts=max(1, int(cfg.entry_qty)),
                max_open_orders=16,
                config_json=config_json(cfg, daily_path, instrument),
            )
        )
    store.write_table("strategy_instances", [as_row(instance) for instance in instances])
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
            print("  combined replayed %d/%d bars" % (idx, len(bars)), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    audit_bars = read_bars_from_engine_bars(list(bars))
    results: List[VariantReplayResult] = []
    for strategy_id, cfg in variant_by_strategy.items():
        units = units_from_live_fills(fills_path, strategy_id)
        audit = audit_units(
            name="%s Hourly ST + PMC %s (StrategyPlugin)" % (instrument, cfg.name),
            slug=strategy_id,
            source=fills_path,
            bar_source=dbn,
            bars=audit_bars,
            units=units,
            instrument=instrument,
            notes=(
                "Combined multi-strategy Engine + PaperBroker StrategyPlugin replay. Variant=%s; "
                "stop=%g; target=%g; tp1_qty=%d; runner_qty=%d; runner_target=%s; "
                "ma_filter=%s; close_against=%s; st_flip_exit=%s; pmc_cross_exit=%s; "
                "slippage=%g tick; fee=$%.2f/unit."
                % (
                    cfg.name,
                    cfg.stop_pts,
                    cfg.tp1_pts,
                    cfg.tp1_qty,
                    cfg.runner_qty,
                    cfg.runner_tp_pts,
                    cfg.ma_filter,
                    cfg.close_against_entry_exit,
                    cfg.st_flip_exit,
                    cfg.pmc_cross_exit,
                    DEFAULT_SLIPPAGE_TICKS,
                    DEFAULT_FEE_PER_UNIT,
                )
            ),
            output_root=output_root / "audits" / strategy_id,
            fee_per_unit=DEFAULT_FEE_PER_UNIT,
        )
        pf = fee_adjusted_profit_factor(output_root / "audits" / strategy_id / strategy_id / "unit_fills.csv")
        results.append(
            VariantReplayResult(
                market=market,
                instrument=instrument,
                variant=cfg.name,
                strategy_id=strategy_id,
                state_root=state_root,
                audit=audit,
                profit_factor=pf,
            )
        )
    return results


def fee_adjusted_profit_factor(unit_fills_path: Path) -> float:
    gross_win = 0.0
    gross_loss = 0.0
    if not unit_fills_path.exists():
        return float("inf")
    with unit_fills_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pnl = float(row.get("usd") or 0.0) - DEFAULT_FEE_PER_UNIT
            if pnl > 0:
                gross_win += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)
    return gross_win / gross_loss if gross_loss else float("inf")


def write_summary(output_root: Path, results: Sequence[VariantReplayResult], title: str = "Hourly ST + PMC") -> None:
    rows = []
    for item in sorted(results, key=lambda r: r.net_over_stress, reverse=True):
        rows.append(
            {
                "market": item.market,
                "instrument": item.instrument,
                "variant": item.variant,
                "strategy_id": item.strategy_id,
                "units": item.audit.units,
                "trades": item.audit.trades,
                "net_usd": "%.2f" % item.audit.net_usd,
                "closed_dd_usd": "%.2f" % item.audit.close_mtm_dd_usd,
                "intrabar_stress_dd_usd": "%.2f" % item.audit.intrabar_mtm_dd_usd,
                "max_open_units": item.audit.max_open_units,
                "win_rate_pct": "%.2f" % item.win_rate,
                "profit_factor": "%.4f" % item.profit_factor if item.profit_factor != float("inf") else "inf",
                "net_over_stress": "%.4f" % item.net_over_stress,
                "state_root": str(item.state_root),
            }
        )
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["variant"])
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# %s StrategyPlugin Variant Replays" % title,
        "",
        "All rows are full `Engine + PaperBroker + StrategyPlugin` replays with realism defaults.",
        "",
        "| Rank | Market | Variant | Units | Trades | Net | Stress DD | Net/Stress | PF | Win Rate | Max Open |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(rows, start=1):
        lines.append(
            "| %d | %s | `%s` | %s | %s | $%s | $%s | %.2f | %s | %.1f%% | %s |"
            % (
                rank,
                row["instrument"],
                row["variant"],
                f"{int(row['units']):,}",
                f"{int(row['trades']):,}",
                f"{float(row['net_usd']):,.2f}",
                f"{float(row['intrabar_stress_dd_usd']):,.2f}",
                float(row["net_over_stress"]),
                row["profit_factor"] if row["profit_factor"] == "inf" else "%.2f" % float(row["profit_factor"]),
                float(row["win_rate_pct"]),
                row["max_open_units"],
            )
        )
    lines.extend(["", "CSV: `summary.csv`", ""])
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _run_variant_worker(cfg: VariantConfig) -> VariantReplayResult:
    if _WORKER_ARGS is None:
        raise RuntimeError("Worker args not initialized")
    return run_variant(
        cfg=cfg,
        bars=_WORKER_BARS,
        output_root=_WORKER_ARGS.output_root,
        dbn=_WORKER_ARGS.dbn,
        daily_path=_WORKER_ARGS.daily,
        instrument=_WORKER_ARGS.instrument,
        market=_WORKER_ARGS.market,
        quiet=not _WORKER_ARGS.no_quiet,
    )


def _market_config(market: str, dbn: Optional[Path] = None, daily: Optional[Path] = None) -> Dict[str, object]:
    key = market.lower()
    if key not in MARKET_CONFIGS:
        raise SystemExit("Unknown market: %s" % market)
    cfg = dict(MARKET_CONFIGS[key])
    if dbn is not None:
        cfg["dbn"] = dbn
    if daily is not None:
        cfg["daily"] = daily
    cfg["market"] = key
    return cfg


def _output_root(args: argparse.Namespace, markets: Sequence[str]) -> Path:
    if args.output_root is not None:
        return args.output_root
    if len(markets) == 1 and markets[0].lower() == "ym":
        return REPO / "live" / "state" / "hourly_st_pmc_strategyplugin_variants"
    if len(markets) == 1:
        return REPO / "live" / "state" / ("hourly_st_pmc_strategyplugin_variants_%s" % markets[0].lower())
    return REPO / "live" / "state" / "hourly_st_pmc_strategyplugin_variants_cross_market"


def _select_variants(names: Sequence[str]) -> List[VariantConfig]:
    all_variants = variants()
    if not names:
        return all_variants
    wanted = set(names)
    selected = [cfg for cfg in all_variants if cfg.name in wanted]
    missing = wanted - {cfg.name for cfg in selected}
    if missing:
        raise SystemExit("Unknown variants: %s" % ", ".join(sorted(missing)))
    return selected


def run_market_sweep(args: argparse.Namespace, market: str, output_root: Path) -> List[VariantReplayResult]:
    cfg = _market_config(
        market,
        dbn=args.dbn if len(args.selected_markets) == 1 else None,
        daily=args.daily if len(args.selected_markets) == 1 else None,
    )
    market_name = str(cfg["market"])
    instrument = str(cfg["instrument"])
    dbn = Path(cfg["dbn"])
    daily = Path(cfg["daily"])
    if not dbn.exists():
        raise FileNotFoundError(dbn)
    if not daily.exists():
        raise FileNotFoundError(daily)

    market_root = output_root if len(args.selected_markets) == 1 else output_root / market_name
    with ReplayLock(market_root, "hourly_st_pmc_strategyplugin_variants_%s" % market_name):
        print("Loading %s hourly bars once..." % instrument, flush=True)
        bars = load_hourly_bars(dbn, instrument)
        if args.max_bars:
            bars = bars[: args.max_bars]
        print("  %s hourly bars" % f"{len(bars):,}", flush=True)
        selected_variants = _select_variants(args.variants)
        results: List[VariantReplayResult] = []
        workers = max(1, int(args.workers))
        if not args.separate_states:
            print("Running %d %s variants in one combined Engine replay..." % (len(selected_variants), instrument), flush=True)
            results = run_combined_variants(
                configs=selected_variants,
                bars=bars,
                output_root=market_root,
                dbn=dbn,
                daily_path=daily,
                instrument=instrument,
                market=market_name,
                quiet=not args.no_quiet,
            )
            for result in sorted(results, key=lambda item: item.net_over_stress, reverse=True):
                print_result(result)
            write_summary(market_root, results, "%s Hourly ST + PMC" % instrument)
        elif workers == 1 or len(selected_variants) <= 1:
            for idx, variant in enumerate(selected_variants, start=1):
                print("Running %s %d/%d %s..." % (instrument, idx, len(selected_variants), variant.name), flush=True)
                result = run_variant(
                    cfg=variant,
                    bars=bars,
                    output_root=market_root,
                    dbn=dbn,
                    daily_path=daily,
                    instrument=instrument,
                    market=market_name,
                    quiet=not args.no_quiet,
                )
                print_result(result)
                results.append(result)
                write_summary(market_root, results, "%s Hourly ST + PMC" % instrument)
        else:
            global _WORKER_BARS, _WORKER_ARGS
            _WORKER_BARS = bars
            worker_args = argparse.Namespace(**vars(args))
            worker_args.output_root = market_root
            worker_args.dbn = dbn
            worker_args.daily = daily
            worker_args.instrument = instrument
            worker_args.market = market_name
            _WORKER_ARGS = worker_args
            print("Running %d %s variants with %d workers..." % (len(selected_variants), instrument, workers), flush=True)
            ctx = mp.get_context("fork")
            with ctx.Pool(processes=workers) as pool:
                for result in pool.imap_unordered(_run_variant_worker, selected_variants):
                    print_result(result)
                    results.append(result)
                    write_summary(market_root, results, "%s Hourly ST + PMC" % instrument)
        write_summary(market_root, results, "%s Hourly ST + PMC" % instrument)
        print("Wrote %s" % (market_root / "SUMMARY.md"), flush=True)
        return results


def write_cross_market_summary(output_root: Path, results: Sequence[VariantReplayResult]) -> None:
    if not results:
        return
    write_summary(output_root, results, "Cross-Market Hourly ST + PMC")
    best_by_market: List[VariantReplayResult] = []
    for market in sorted({r.market for r in results}):
        market_results = [r for r in results if r.market == market]
        best_by_market.append(max(market_results, key=lambda r: r.net_over_stress))
    write_summary(output_root / "best_by_market", best_by_market, "Best Hourly ST + PMC Variant By Market")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run hourly ST+PMC variants through Engine + PaperBroker.")
    parser.add_argument("--market", default="ym", choices=sorted(MARKET_CONFIGS), help="Single market to run.")
    parser.add_argument("--markets", nargs="*", default=[], choices=sorted(MARKET_CONFIGS), help="Run multiple markets.")
    parser.add_argument(
        "--dbn",
        type=Path,
        default=None,
        help="Override single-market 1m source path.",
    )
    parser.add_argument("--daily", type=Path, default=None, help="Override single-market daily source path.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    parser.add_argument("--variants", nargs="*", default=[], help="Optional subset of variant names.")
    parser.add_argument("--max-bars", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--separate-states", action="store_true", help="Replay each variant in its own state root.")
    parser.add_argument("--no-quiet", action="store_true")
    args = parser.parse_args(argv)
    args.selected_markets = [m.lower() for m in (args.markets or [args.market])]
    if len(args.selected_markets) > 1 and (args.dbn is not None or args.daily is not None):
        raise SystemExit("--dbn/--daily overrides are only supported for a single market run.")
    output_root = _output_root(args, args.selected_markets)
    all_results: List[VariantReplayResult] = []
    for market in args.selected_markets:
        all_results.extend(run_market_sweep(args, market, output_root))
        if len(args.selected_markets) > 1:
            write_cross_market_summary(output_root, all_results)
    if len(args.selected_markets) > 1:
        write_cross_market_summary(output_root, all_results)
        print("Wrote %s" % (output_root / "SUMMARY.md"), flush=True)
    return 0


def print_result(result: VariantReplayResult) -> None:
    print(
        "  %s %s Net=$%s Stress=$%s Net/Stress=%.2f"
        % (
            result.instrument,
            result.variant,
            f"{result.audit.net_usd:,.2f}",
            f"{result.audit.intrabar_mtm_dd_usd:,.2f}",
            result.net_over_stress,
        ),
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
