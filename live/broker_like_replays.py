from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .reporting import generate_market_close_report
from .replay_manifest import write_run_manifest
from .replay_audit import (
    AuditResult,
    POINT_VALUES,
    audit_units,
    read_bars,
    units_from_live_fills,
    units_from_units_csv,
)
from .store import FlatFileStore


@dataclass(frozen=True)
class MarketSpec:
    market: str
    instrument: str
    daily_path: Path


@dataclass(frozen=True)
class BrokerReplaySpec:
    name: str
    slug: str
    strategy_type: str
    max_contracts: int
    config: Dict[str, object]
    notes: str


MARKETS: List[MarketSpec] = [
    MarketSpec("mnq", "MNQ", Path("potions/mnq/mnq_daily.csv")),
    MarketSpec("nq", "NQ", Path("potions/nq/nq_daily.csv")),
    MarketSpec("es", "ES", Path("potions/es/es_daily.csv")),
    MarketSpec("mes", "MES", Path("potions/mes/mes_daily.csv")),
    MarketSpec("ym", "YM", Path("potions/ym/ym_daily.csv")),
    MarketSpec("mym", "MYM", Path("potions/mym/mym_daily.csv")),
]


DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_FEE_PER_UNIT = 1.50


REPLAY_SPECS: List[BrokerReplaySpec] = [
    BrokerReplaySpec(
        name="Yearly ORB scaleout3",
        slug="yearly_orb_scaleout3",
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
        },
        notes="Broker-like daily StrategyPlugin replay. Orders activate after confirming daily close.",
    ),
    BrokerReplaySpec(
        name="Yearly ORB scaleout3 20% range-close",
        slug="yearly_orb_scaleout3_range_close_20pct",
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
            "range_close_inside_frac": 0.20,
            "entry_mode": "oco_stop",
        },
        notes="Broker-like daily StrategyPlugin replay. OCO stop entries arm both yearly boundaries and range-close exits require a close 20% back into the yearly ORB.",
    ),
    BrokerReplaySpec(
        name="Monthly ORB restricted scaleout3",
        slug="monthly_orb_restricted_scaleout3",
        strategy_type="monthly_orb_restricted_scaleout3",
        max_contracts=3,
        config={
            "allow_shorts": True,
            "or_sessions": 3,
            "max_trades_per_month": 2,
            "batch_qty": 1,
            "record_levels": False,
        },
        notes="Broker-like daily StrategyPlugin replay of the formerly daily-OHLC monthly restricted scaleout3 branch.",
    ),
    BrokerReplaySpec(
        name="Monthly ORB restricted scaleout3 boundary-stop entry",
        slug="monthly_orb_restricted_scaleout3_boundary_stop",
        strategy_type="monthly_orb_restricted_scaleout3",
        max_contracts=3,
        config={
            "allow_shorts": True,
            "or_sessions": 3,
            "max_trades_per_month": 3,
            "batch_qty": 1,
            "entry_mode": "boundary_stop",
            "failed_break_retrace_frac": 0.25,
            "record_levels": False,
        },
        notes="Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR.",
    ),
    BrokerReplaySpec(
        name="ATR daily ladder 1/1/2/2/2 10-max",
        slug="atr_daily_ladder112221_10max",
        strategy_type="atr_supertrend_dca",
        max_contracts=10,
        config={
            "signal_tf": "daily",
            "schedule": "ladder112221",
            "initial_qty": 1,
            "add_qty": 1,
            "max_contracts": 10,
            "add_interval": 2,
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Broker-like daily StrategyPlugin replay. Current top MNQ ATR signal-replay shape.",
    ),
    BrokerReplaySpec(
        name="ATR daily 3-initial 10-max",
        slug="atr_daily_3initial_10max",
        strategy_type="atr_supertrend_dca",
        max_contracts=10,
        config={
            "signal_tf": "daily",
            "schedule": "fixed",
            "initial_qty": 3,
            "add_qty": 1,
            "max_contracts": 10,
            "add_interval": 2,
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Broker-like daily StrategyPlugin replay. Higher net, more heat than ladder in MNQ signal pass.",
    ),
    BrokerReplaySpec(
        name="ATR weekly 2-initial / 3-add / 6-max",
        slug="atr_weekly_2initial_3add_6max",
        strategy_type="atr_supertrend_dca",
        max_contracts=6,
        config={
            "signal_tf": "weekly",
            "schedule": "fixed",
            "initial_qty": 2,
            "add_qty": 3,
            "max_contracts": 6,
            "add_interval": 2,
            "use_entry_guard": True,
            "daily_use_weekly_flat": False,
            "add_on_friday_close": True,
        },
        notes="Broker-like replay of the recent TradingView sweet-spot sizing candidate.",
    ),
]


def run_broker_like_replays(
    output_root: Path,
    force: bool = True,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    fee_per_unit: float = DEFAULT_FEE_PER_UNIT,
) -> List[AuditResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    states_root = output_root / "states"
    audit_root = output_root / "audits"
    charts_root = output_root / "charts"
    states_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)
    results: List[AuditResult] = []

    for market in MARKETS:
        if not market.daily_path.exists() or market.instrument not in POINT_VALUES:
            continue
        bars = bars_from_csv(market.daily_path, market.instrument, "D", source=str(market.daily_path))
        if not bars:
            continue
        for spec in REPLAY_SPECS:
            state_root = states_root / f"{market.market}_{spec.slug}"
            if force and state_root.exists():
                shutil.rmtree(state_root)
            state = FlatFileStore(state_root, defer_table_writes=True)
            state.ensure()
            strategy_id = f"{market.market}_{spec.slug}"
            instance = StrategyInstance(
                strategy_id=strategy_id,
                strategy_type=spec.strategy_type,
                version="v1",
                instrument=market.instrument,
                broker_instrument=market.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="D",
                max_contracts=spec.max_contracts,
                max_open_orders=64,
                config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
            )
            state.upsert_row("strategy_instances", "strategy_id", as_row(instance))
            Engine(store=state, slippage_ticks=slippage_ticks).replay_bars(bars)
            state.flush_tables()
            generate_market_close_report(state, bars[-1].ts[:10])
            replay_bars = read_bars(state_root / "bars" / f"{market.instrument}_D.csv", "ts")
            units = units_from_live_fills(
                state_root / "fills.csv",
                strategy_id,
                replay_bars[-1].ts,
                replay_bars[-1].close,
            )
            note = (
                spec.notes
                + f" Open units marked at final replay close. Slippage={slippage_ticks:g} tick(s),"
                + f" fee=${fee_per_unit:.2f}/unit."
            )
            results.append(
                audit_units(
                    name=f"{market.instrument} {spec.name}",
                    slug=strategy_id,
                    source=state_root / "fills.csv",
                    bar_source=state_root / "bars" / f"{market.instrument}_D.csv",
                    bars=replay_bars,
                    units=units,
                    instrument=market.instrument,
                    notes=note,
                    output_root=audit_root,
                    fee_per_unit=fee_per_unit,
                )
            )

    _write_summary(output_root, results, slippage_ticks=slippage_ticks, fee_per_unit=fee_per_unit)
    _write_atr_comparison_chart(output_root, charts_root)
    write_run_manifest(
        output_root,
        data_inputs=[market.daily_path for market in MARKETS if market.daily_path.exists()],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md", charts_root / "INDEX.md"],
        broker_realism_config={"slippage_ticks": slippage_ticks, "fee_per_unit": fee_per_unit, "stop_gap_through": True, "stop_first": True},
        causality_mode="audit",
        extra={"driver": "broker_like_replays", "result_count": len(results)},
    )
    return results


def _runtime_config(spec: BrokerReplaySpec, bars) -> Dict[str, object]:
    config = dict(spec.config)
    if spec.strategy_type in {"monthly_orb_restricted_scaleout3", "monthly_orb_v2b_oco"}:
        config.setdefault("flatten_month_end", True)
        config["month_end_dates"] = _month_end_dates(bars)
    return config


def _month_end_dates(bars) -> List[str]:
    last_by_month: Dict[str, str] = {}
    for bar in bars:
        day = str(bar.ts)[:10]
        last_by_month[day[:7]] = day
    return [last_by_month[key] for key in sorted(last_by_month)]


def _write_summary(
    root: Path,
    results: List[AuditResult],
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    fee_per_unit: float = DEFAULT_FEE_PER_UNIT,
) -> None:
    rows = []
    ranked = sorted(results, key=lambda r: r.net_usd / abs(r.intrabar_mtm_dd_usd or -1), reverse=True)
    for r in ranked:
        ratio = r.net_usd / abs(r.intrabar_mtm_dd_usd) if r.intrabar_mtm_dd_usd else 0.0
        rows.append(
            {
                "candidate": r.name,
                "slug": r.slug,
                "instrument": r.instrument,
                "units": str(r.units),
                "trades": str(r.trades),
                "net_usd": "%.2f" % r.net_usd,
                "close_mtm_dd_usd": "%.2f" % r.close_mtm_dd_usd,
                "intrabar_mtm_dd_usd": "%.2f" % r.intrabar_mtm_dd_usd,
                "max_open_units": str(r.max_open_units),
                "net_over_stress_dd": "%.2f" % ratio,
            }
        )
    _write_csv(root / "summary.csv", rows)
    lines = [
        "# Broker-Like Bar Replay Rankings",
        "",
        "New standard: strategy-generated `OrderIntent`s through `Engine` + `PaperBroker`. Orders become active only after the confirming bar has closed. Open units are marked at the final replay close.",
        "",
        f"Realism knobs: `slippage_ticks={slippage_ticks:g}`, `fee_per_unit=${fee_per_unit:.2f}`, stop gap-through enabled, OCO-collapsed risk projection.",
        "",
        "| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            "| %d | %s | %s | %s | %s | $%s | $%s | $%s | %s | %s |"
            % (
                idx,
                row["candidate"],
                row["instrument"],
                row["units"],
                row["trades"],
                _money(float(row["net_usd"])),
                _money(float(row["close_mtm_dd_usd"])),
                _money(float(row["intrabar_mtm_dd_usd"])),
                row["max_open_units"],
                row["net_over_stress_dd"],
            )
        )
    lines.extend(
        [
            "",
            "## Coverage Notes",
            "",
            "- Monthly overlap range breakout daily-ST retest x5 remains a 4h causal research artifact. MNQ/NQ have 4h caches; ES/MES/YM/MYM do not yet have equivalent 4h cache files in this workspace.",
            "- v2b clean-break variants need a 1m/5m StrategyPlugin before they can be compared in this broker-like table.",
            "- This table is intentionally different from theoretical/research tables: it favors implementability and order timing over optimistic same-bar fills.",
            "",
        ]
    )
    (root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_atr_comparison_chart(root: Path, charts_root: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    charts_root.mkdir(parents=True, exist_ok=True)
    broker_eq = root / "audits" / "mnq_atr_daily_ladder112221_10max" / "equity_curve.csv"
    theoretical_units = Path("potions/mnq/case_studies/atr_supertrend_dca_long_biweekly_10max_weekly_flat_entry_guard_ladder112221/units.csv")
    bars_path = Path("potions/mnq/mnq_daily.csv")
    theoretical_root = root / "theoretical_reference"
    if theoretical_units.exists() and bars_path.exists():
        bars = read_bars(bars_path, "date")
        units = units_from_units_csv(theoretical_units, "mnq_atr_daily_ladder112221_theoretical")
        audit_units(
            name="MNQ ATR daily ladder theoretical artifact",
            slug="mnq_atr_daily_ladder112221_theoretical",
            source=theoretical_units,
            bar_source=bars_path,
            bars=bars,
            units=units,
            instrument="MNQ",
            notes="Old unit-level research artifact, used only for theoretical-vs-broker-like chart comparison.",
            output_root=theoretical_root,
        )
    theoretical_eq = theoretical_root / "mnq_atr_daily_ladder112221_theoretical" / "equity_curve.csv"
    if not broker_eq.exists() or not theoretical_eq.exists():
        return

    panels = [
        ("Theoretical artifact", theoretical_eq),
        ("Broker-like StrategyPlugin replay", broker_eq),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=False)
    for ax, (title, path) in zip(axes, panels):
        rows = _read_csv(path)
        x = [row["ts"][:10] for row in rows]
        y = [float(row["close_equity_points"]) * POINT_VALUES["MNQ"] for row in rows]
        dd = [float(row["intrabar_dd_usd"]) for row in rows]
        ax.plot(range(len(y)), y, color="#0f766e", linewidth=1.5)
        ax.fill_between(range(len(dd)), dd, 0, color="#dc2626", alpha=0.18)
        ax.set_title(title)
        ax.set_ylabel("USD")
        ax.grid(True, alpha=0.25)
        if x:
            tick_idx = list(range(0, len(x), max(len(x) // 6, 1)))
            ax.set_xticks(tick_idx)
            ax.set_xticklabels([x[i][:4] for i in tick_idx], rotation=0)
    fig.suptitle("MNQ ATR Daily Ladder 1/1/2/2/2: Theoretical vs Broker-Like Replay")
    fig.tight_layout()
    fig.text(
        0.01,
        0.005,
        "Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, stop gap-through ON, stop-first same-bar, OCO-collapsed risk.",
        fontsize=7,
        color="#475569",
        ha="left",
    )
    out = charts_root / "mnq_atr_daily_ladder112221_theoretical_vs_broker_like.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)

    weekly_eq = root / "audits" / "mnq_atr_weekly_2initial_3add_6max" / "equity_curve.csv"
    if weekly_eq.exists():
        rows = _read_csv(weekly_eq)
        y = [float(row["close_equity_points"]) * POINT_VALUES["MNQ"] for row in rows]
        dd = [float(row["intrabar_dd_usd"]) for row in rows]
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(range(len(y)), y, color="#2563eb", linewidth=1.5)
        ax.fill_between(range(len(dd)), dd, 0, color="#dc2626", alpha=0.18)
        ax.set_title("MNQ ATR Weekly 2-Initial / 3-Add / 6-Max Broker-Like Replay")
        ax.set_ylabel("USD")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.text(
            0.01,
            0.005,
            "Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, stop gap-through ON, stop-first same-bar, OCO-collapsed risk.",
            fontsize=7,
            color="#475569",
            ha="left",
        )
        fig.savefig(charts_root / "mnq_atr_weekly_2initial_3add_6max_broker_like.png", dpi=150)
        plt.close(fig)

    (charts_root / "INDEX.md").write_text(
        "\n".join(
            [
                "# Broker-Like Replay Charts",
                "",
                "![MNQ ATR daily ladder theoretical vs broker-like](mnq_atr_daily_ladder112221_theoretical_vs_broker_like.png)",
                "",
                "![MNQ ATR weekly 2-initial broker-like](mnq_atr_weekly_2initial_3add_6max_broker_like.png)",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run broker-like StrategyPlugin bar replays across viable candidates.")
    parser.add_argument("--output-root", type=Path, default=Path("potions/live/state/broker_like_replays"))
    parser.add_argument("--no-force", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_broker_like_replays(args.output_root, force=not args.no_force)
    for result in results:
        ratio = result.net_usd / abs(result.intrabar_mtm_dd_usd) if result.intrabar_mtm_dd_usd else 0.0
        print(
            "%s net=$%s stress=$%s ratio=%.2f"
            % (result.slug, _money(result.net_usd), _money(result.intrabar_mtm_dd_usd), ratio)
        )
    print("Wrote %s" % args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
