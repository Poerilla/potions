"""Overnight EURUSD broker-like sweep across STRATEGY_TRACKER leaders.

Runs Yearly ORB, ATR Supertrend (ladder + 3-initial + weekly), Monthly ORB,
Hourly ST+PMC pip-scaled variants, plain v2b OCO (S_1_1_3 and 1/0/0), and folds
in the already-banked prior-opposed result.

Designed for unattended overnight use: durable progress log, per-strategy
catch, and a final ranked SUMMARY.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import traceback
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import BrokerReplaySpec, REPLAY_SPECS, _month_end_dates, _runtime_config
from .engine import Engine, bars_from_csv
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import run_variant
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, AuditResult, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .reporting import generate_market_close_report
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MarketConfig, _regime_dates
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
MARKET = "eurusd"
PIP = 0.0001
TICK = 0.00001
POINT_VALUE = 100000.0
FEE_PER_UNIT = 7.0
DEFAULT_START_1M = date(2015, 1, 2)
NY = "America/New_York"

# Tracker-leading ST+PMC shapes, translated to pips for FX absolute prices.
ST_VARIANTS: List[VariantConfig] = [
    VariantConfig("base_1x_50sl_150tp", stop_pts=50 * PIP, tp1_pts=150 * PIP, notes="50/150 pip base."),
    VariantConfig("sl40_tp120_3r", stop_pts=40 * PIP, tp1_pts=120 * PIP, notes="YM-favorite 40/120 3R in pips."),
    VariantConfig("sl25_tp75_3r", stop_pts=25 * PIP, tp1_pts=75 * PIP, notes="Best cross-market hourly 25/75 3R in pips."),
    VariantConfig(
        "sl25_tp75_3r_ma_bull_prior",
        stop_pts=25 * PIP,
        tp1_pts=75 * PIP,
        ma_filter="bull_prior_only",
        notes="25/75 with prior MA50>MA150 gate.",
    ),
    VariantConfig(
        "sl40_tp120_3r_ma_directional_prior",
        stop_pts=40 * PIP,
        tp1_pts=120 * PIP,
        ma_filter="directional_prior",
        notes="40/120 with directional prior MA filter.",
    ),
]


@dataclass
class SweepRow:
    family: str
    name: str
    strategy_id: str
    status: str
    units: int = 0
    trades: int = 0
    net_usd: float = 0.0
    closed_dd_usd: float = 0.0
    stress_dd_usd: float = 0.0
    max_open_units: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    net_over_stress: float = 0.0
    notes: str = ""
    error: str = ""

    @property
    def sort_key(self) -> float:
        if self.status != "ok" or self.stress_dd_usd == 0:
            return float("-inf")
        return self.net_usd / abs(self.stress_dd_usd)


def _ensure_meta() -> None:
    POINT_VALUES.setdefault(INSTRUMENT, POINT_VALUE)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)


def _progress(output_root: Path, message: str) -> None:
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    path = output_root / "PROGRESS.log"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_row(output_root: Path, rows: List[SweepRow], row: SweepRow) -> None:
    rows.append(row)
    _write_summary(output_root, rows)


def _fx_spread() -> SpreadModel:
    return SpreadModel(
        rth_half_spread_ticks=5.0,
        eth_half_spread_ticks=10.0,
        open_widen_half_spread_ticks=10.0,
        low_volume_threshold=1.0,
        low_volume_multiplier=1.5,
        tick_size=TICK,
    )


def run_daily_specs(
    *,
    daily_path: Path,
    output_root: Path,
    rows: List[SweepRow],
    force: bool,
) -> None:
    _ensure_meta()
    bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    _progress(output_root, "Daily bars loaded: %d" % len(bars))
    specs: List[BrokerReplaySpec] = list(REPLAY_SPECS)
    for spec in specs:
        strategy_id = "%s_%s" % (MARKET, spec.slug)
        family = "yearly_orb" if "yearly" in spec.slug else ("atr" if "atr" in spec.slug else "monthly_orb")
        _progress(output_root, "START daily %s" % strategy_id)
        try:
            state_root = output_root / "states" / strategy_id
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
            Engine(
                store=store,
                slippage_ticks=1.0,
                tick_size={INSTRUMENT: TICK},
            ).replay_bars(bars)
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
                notes=spec.notes + " EURUSD overnight sweep; fee=$%.2f/unit." % FEE_PER_UNIT,
                output_root=output_root / "audits",
                fee_per_unit=FEE_PER_UNIT,
            )
            ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            _append_row(
                output_root,
                rows,
                SweepRow(
                    family=family,
                    name=spec.name,
                    strategy_id=strategy_id,
                    status="ok",
                    units=audit.units,
                    trades=audit.trades,
                    net_usd=audit.net_usd,
                    closed_dd_usd=audit.close_mtm_dd_usd,
                    stress_dd_usd=audit.intrabar_mtm_dd_usd,
                    max_open_units=audit.max_open_units,
                    win_rate_pct=100.0 * audit.win_units / audit.units if audit.units else 0.0,
                    profit_factor=float("nan"),
                    net_over_stress=ratio,
                    notes=spec.notes,
                ),
            )
            _progress(
                output_root,
                "DONE daily %s Net=$%.2f Net/Stress=%.2f" % (strategy_id, audit.net_usd, ratio),
            )
        except Exception as exc:
            _progress(output_root, "FAIL daily %s: %s" % (strategy_id, exc))
            _append_row(
                output_root,
                rows,
                SweepRow(
                    family=family,
                    name=spec.name,
                    strategy_id=strategy_id,
                    status="error",
                    error="%s\n%s" % (exc, traceback.format_exc()),
                ),
            )


def _load_hourly_bars(one_m: Path) -> List[Bar]:
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    hourly_df = resample_hourly(concat_all_1m(gby))
    bars: List[Bar] = []
    for ts, row in hourly_df.iterrows():
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


def run_st_pmc_variants(
    *,
    one_m: Path,
    daily_path: Path,
    output_root: Path,
    rows: List[SweepRow],
    force: bool,
) -> None:
    _ensure_meta()
    from . import hourly_st_pmc_strategyplugin_variants as hsv

    hsv.TICK_SIZE[INSTRUMENT] = TICK
    _progress(output_root, "Loading hourly bars for ST+PMC variants...")
    bars = _load_hourly_bars(one_m)
    _progress(output_root, "Hourly bars: %d" % len(bars))
    st_root = output_root / "st_pmc"
    for cfg in ST_VARIANTS:
        strategy_id = "%s_hourly_st_pmc_%s" % (MARKET, cfg.name)
        _progress(output_root, "START ST+PMC %s" % strategy_id)
        try:
            result = run_variant(
                cfg=cfg,
                bars=bars,
                output_root=st_root,
                dbn=one_m,
                daily_path=daily_path,
                instrument=INSTRUMENT,
                market=MARKET,
                force=force,
                quiet=True,
            )
            audit = result.audit
            ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            _append_row(
                output_root,
                rows,
                SweepRow(
                    family="hourly_st_pmc",
                    name="Hourly ST+PMC %s" % cfg.name,
                    strategy_id=strategy_id,
                    status="ok",
                    units=audit.units,
                    trades=audit.trades,
                    net_usd=audit.net_usd,
                    closed_dd_usd=audit.close_mtm_dd_usd,
                    stress_dd_usd=audit.intrabar_mtm_dd_usd,
                    max_open_units=audit.max_open_units,
                    win_rate_pct=100.0 * audit.win_units / audit.units if audit.units else 0.0,
                    profit_factor=result.profit_factor if math.isfinite(result.profit_factor) else float("nan"),
                    net_over_stress=ratio,
                    notes=cfg.notes,
                ),
            )
            _progress(
                output_root,
                "DONE ST+PMC %s Net=$%.2f Net/Stress=%.2f" % (strategy_id, audit.net_usd, ratio),
            )
        except Exception as exc:
            _progress(output_root, "FAIL ST+PMC %s: %s" % (strategy_id, exc))
            _append_row(
                output_root,
                rows,
                SweepRow(
                    family="hourly_st_pmc",
                    name="Hourly ST+PMC %s" % cfg.name,
                    strategy_id=strategy_id,
                    status="error",
                    error="%s\n%s" % (exc, traceback.format_exc()),
                ),
            )


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = rth_bars(raw_day, session, dense=True)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def run_v2b_variants(
    *,
    one_m: Path,
    daily_path: Path,
    output_root: Path,
    rows: List[SweepRow],
    force: bool,
    start: date,
    max_days: Optional[int],
) -> None:
    _ensure_meta()
    cfg = MarketConfig(
        market=MARKET,
        instrument=INSTRUMENT,
        daily_path=daily_path,
        dbn_path=one_m,
        start=start,
        fee_per_unit=FEE_PER_UNIT,
    )
    _progress(output_root, "Loading 1m for v2b OCO variants...")
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    _progress(output_root, "v2b regime sessions: %d" % len(regime_dates))

    variants = [
        (
            "v2b_oco_S_1_1_3",
            {
                "mode": "oco_then_reverse",
                "entry_qty": 5,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "prior_opposite_only": False,
            },
            "Tracker-leading all-day v2b runner-heavy S_1_1_3.",
        ),
        (
            "v2b_oco_1_0_0",
            {
                "mode": "oco_then_reverse",
                "entry_qty": 1,
                "tp1_qty": 1,
                "tp2_qty": 0,
                "prior_opposite_only": False,
            },
            "Start-small TP1-only plumbing expression.",
        ),
    ]

    for slug, knobs, notes in variants:
        strategy_id = "%s_%s" % (MARKET, slug)
        _progress(output_root, "START v2b %s" % strategy_id)
        try:
            state_root = output_root / "states" / strategy_id
            if force and state_root.exists():
                shutil.rmtree(state_root)
            store = FlatFileStore(state_root, defer_table_writes=True)
            store.ensure()
            payload = {
                "market": MARKET,
                "tick_size": TICK,
                "use_regime_filter": True,
                "start": start.isoformat(),
                "regime_dates": [d.isoformat() for d in regime_dates],
                "record_levels": False,
                **knobs,
            }
            instance = StrategyInstance(
                strategy_id=strategy_id,
                strategy_type="v2b_scaleout",
                version="v1",
                instrument=INSTRUMENT,
                broker_instrument=INSTRUMENT,
                account_mode="paper",
                enabled=True,
                timeframes="1m",
                max_contracts=int(knobs["entry_qty"]),
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
            store.write_table("strategy_instances", [as_row(instance)])
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
                    _progress(output_root, "  %s %d/%d" % (strategy_id, idx, len(regime_dates)))
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
            net = float(audit["net_usd"])
            stress = float(audit["intrabar_stress_dd_usd"])
            closed = float(audit["closed_dd_usd"])
            trades = len({u.trade_id for u in units})
            wins = sum(1 for u in units if u.points > 0)
            ratio = net / abs(stress) if stress else 0.0
            _append_row(
                output_root,
                rows,
                SweepRow(
                    family="v2b",
                    name=slug,
                    strategy_id=strategy_id,
                    status="ok",
                    units=len(units),
                    trades=trades,
                    net_usd=net,
                    closed_dd_usd=closed,
                    stress_dd_usd=stress,
                    max_open_units=int(audit["max_open_units"]),
                    win_rate_pct=100.0 * wins / len(units) if units else 0.0,
                    profit_factor=float(audit["profit_factor"]) if math.isfinite(float(audit["profit_factor"])) else float("nan"),
                    net_over_stress=ratio,
                    notes=notes,
                ),
            )
            _progress(output_root, "DONE v2b %s Net=$%.2f Net/Stress=%.2f" % (strategy_id, net, ratio))
        except Exception as exc:
            _progress(output_root, "FAIL v2b %s: %s" % (strategy_id, exc))
            _append_row(
                output_root,
                rows,
                SweepRow(
                    family="v2b",
                    name=slug,
                    strategy_id=strategy_id,
                    status="error",
                    error="%s\n%s" % (exc, traceback.format_exc()),
                ),
            )


def import_prior_opposed(output_root: Path, rows: List[SweepRow]) -> None:
    prior = REPO / "live" / "state" / "eurusd_v2b_prior_opposed_stpmc_broker_like" / "summary.csv"
    if not prior.exists():
        _progress(output_root, "SKIP prior-opposed import (missing %s)" % prior)
        return
    with prior.open(newline="", encoding="utf-8") as fh:
        rec = next(csv.DictReader(fh), None)
    if not rec:
        return
    net = float(rec["net_usd"])
    stress = float(rec["intrabar_stress_dd_usd"])
    _append_row(
        output_root,
        rows,
        SweepRow(
            family="v2b_prior_opposed",
            name="v2b prior-opposed ST+PMC S_1_1_3",
            strategy_id=rec["strategy_id"],
            status="ok",
            units=int(float(rec["units"])),
            trades=int(float(rec["trades"])),
            net_usd=net,
            closed_dd_usd=float(rec["closed_dd_usd"]),
            stress_dd_usd=stress,
            win_rate_pct=float(rec["win_rate_pct"]),
            profit_factor=float(rec["profit_factor"]),
            net_over_stress=float(rec["net_over_stress"]),
            notes="Imported from eurusd_v2b_prior_opposed_stpmc_broker_like (2015+).",
        ),
    )
    _progress(output_root, "Imported prior-opposed Net=$%.2f" % net)


def _write_summary(output_root: Path, rows: Sequence[SweepRow]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    ranked = sorted(rows, key=lambda r: r.sort_key, reverse=True)
    csv_path = output_root / "summary.csv"
    fieldnames = list(asdict(ranked[0]).keys()) if ranked else ["strategy_id"]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in ranked:
            payload = asdict(row)
            for key in ("net_usd", "closed_dd_usd", "stress_dd_usd", "win_rate_pct", "profit_factor", "net_over_stress"):
                val = payload[key]
                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    payload[key] = ""
                elif isinstance(val, float):
                    payload[key] = "%.4f" % val
            writer.writerow(payload)

    lines = [
        "# EURUSD Overnight Broker-Like Sweep",
        "",
        "Tracker-led candidates on Histdata EURUSD through `Engine + PaperBroker + StrategyPlugin`.",
        "",
        "- Point value: **$100,000** / lot (standard).",
        "- Tick: **0.00001**; ST stops/targets in **pips**.",
        "- Fee proxy: **$%.2f**/unit; 1m rows use ~0.5 pip half-spread." % FEE_PER_UNIT,
        "- Daily families: Yearly ORB, Monthly ORB, ATR Supertrend.",
        "- Hourly: ST+PMC pip variants; 1m: v2b OCO + imported prior-opposed.",
        "",
        "| Rank | Family | Candidate | Trades | Units | Net | Stress DD | Net/Stress | Win% | Status |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %s | %d | %d | $%s | $%s | %.2f | %.1f | %s |"
            % (
                idx,
                row.family,
                row.name,
                row.trades,
                row.units,
                _money(row.net_usd),
                _money(row.stress_dd_usd),
                row.net_over_stress if row.status == "ok" else 0.0,
                row.win_rate_pct,
                row.status,
            )
        )
    errors = [r for r in ranked if r.status == "error"]
    if errors:
        lines.extend(["", "## Errors", ""])
        for row in errors:
            lines.append("- `%s`: %s" % (row.strategy_id, row.error.splitlines()[0] if row.error else "unknown"))
    lines.extend(["", "Progress log: `PROGRESS.log`", "CSV: `summary.csv`", ""])
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _money(value: float) -> str:
    if value != value:  # NaN
        return "n/a"
    return "{:,.2f}".format(value)


def run(
    *,
    output_root: Path,
    force: bool = True,
    start: date = DEFAULT_START_1M,
    max_days: Optional[int] = None,
    skip_daily: bool = False,
    skip_st: bool = False,
    skip_v2b: bool = False,
) -> List[SweepRow]:
    _ensure_meta()
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress(output_root, "EURUSD overnight sweep starting")
    one_m, daily = ensure_eurusd_platform_files(REPO, force=False)
    rows: List[SweepRow] = []

    import_prior_opposed(output_root, rows)

    if not skip_daily:
        run_daily_specs(daily_path=daily, output_root=output_root, rows=rows, force=force)
    if not skip_st:
        run_st_pmc_variants(one_m=one_m, daily_path=daily, output_root=output_root, rows=rows, force=force)
    if not skip_v2b:
        run_v2b_variants(
            one_m=one_m,
            daily_path=daily,
            output_root=output_root,
            rows=rows,
            force=force,
            start=start,
            max_days=max_days,
        )

    _write_summary(output_root, rows)
    write_run_manifest(
        output_root,
        data_inputs=[one_m, daily],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md", output_root / "PROGRESS.log"],
        strategy_config={"market": MARKET, "start": start.isoformat(), "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "spread_model": "fx_half_pip"},
        causality_mode="audit",
        extra={"driver": "eurusd_overnight_sweep", "row_count": len(rows)},
    )
    _progress(output_root, "Sweep complete (%d rows)" % len(rows))
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Overnight EURUSD tracker-led broker-like sweep.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_overnight_sweep",
    )
    parser.add_argument("--start", default=DEFAULT_START_1M.isoformat())
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--skip-daily", action="store_true")
    parser.add_argument("--skip-st", action="store_true")
    parser.add_argument("--skip-v2b", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    run(
        output_root=args.output_root,
        force=not args.no_force,
        start=start,
        max_days=args.max_days,
        skip_daily=args.skip_daily,
        skip_st=args.skip_st,
        skip_v2b=args.skip_v2b,
    )
    print("Wrote %s" % (args.output_root / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
