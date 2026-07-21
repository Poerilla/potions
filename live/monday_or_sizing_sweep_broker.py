"""Broker-like sizing sweep for Monday OR (Phase 1 / full grid).

Replays each M×S×R cell through Engine + PaperBroker and ranks by Net/Stress.
Loads 15m bars once per pair. Sidecar = shifted primary (plugin knobs).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_monday_or_breakout_broker import PAIRS, JPY_USD, load_15m_bars
from .hourly_st_pmc_retest_replay import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS
from .models import StrategyInstance, as_row
from .monday_or_sizing_sweep import (
    MAIN_FULL,
    MAIN_PHASE1,
    REENTRY_FULL,
    REENTRY_PHASE1,
    SIDE_FULL,
    SIDE_PHASE1,
    SizeScenario,
)
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills, Bar as AuditBar
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monday_or_sizing_sweep_broker"


def _cfg(
    tick: float,
    main: SizeScenario,
    side: SizeScenario,
    max_trades: int,
) -> str:
    return json.dumps(
        {
            "tick_size": tick,
            "entry_qty": main.entry,
            "dd30_qty": main.dd30,
            "dd50_qty": main.dd50,
            "shifted_entry_qty": side.entry,
            "shifted_dd30_qty": side.dd30,
            "shifted_dd50_qty": side.dd50,
            "reward_R": 2.0,
            "max_trades_per_week": max_trades,
            "skip_both_opposed": True,
            "shifted_primary": True,
            "obv_ma": 20,
        },
        sort_keys=True,
    )


def run_cell(
    sym: str,
    bars,
    *,
    tag: str,
    main: SizeScenario,
    side: SizeScenario,
    max_trades: int,
    out: Path,
    force: bool,
) -> dict:
    meta = PAIRS[sym]
    tick = float(meta["tick"])
    pv = float(meta["pv"])
    POINT_VALUES[sym] = pv
    DEFAULT_TICK_SIZE[sym] = tick

    strategy_id = "%s_%s" % (sym.lower(), tag.lower())
    state_root = out / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        print("[%s] %s cached" % (sym, tag), flush=True)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    if state_root.exists():
        shutil.rmtree(state_root)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    max_c = max(main.entry, side.entry) + 2
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="monday_or_breakout",
        version="v1",
        instrument=sym,
        broker_instrument=sym,
        account_mode="paper",
        enabled=True,
        timeframes="15m",
        max_contracts=max_c,
        max_open_orders=24,
        config_json=_cfg(tick, main, side, max_trades),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    n = len(bars)
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 100000 == 0:
            print("  [%s %s] %d/%d" % (sym, tag, idx, n), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    units = units_from_live_fills(fills_path, strategy_id)
    audit_bars = [
        AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars
    ]
    audit = audit_units(
        name="%s Monday OR %s" % (sym, tag),
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m,
        bars=audit_bars,
        units=units,
        instrument=sym,
        notes="Broker sizing sweep; fee $1.50; 1-tick slip.",
        output_root=out / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    net = float(audit.net_usd)
    stress = float(audit.intrabar_mtm_dd_usd)
    closed = float(audit.close_mtm_dd_usd)
    quote = str(meta["quote"])
    net_usd = net / JPY_USD if quote == "JPY" else net
    stress_usd = stress / JPY_USD if quote == "JPY" else stress
    ns = (net_usd / abs(stress_usd)) if stress_usd else 0.0
    row = {
        "symbol": sym,
        "tag": tag,
        "main": main.slug,
        "main_entry": main.entry,
        "main_dd30": main.dd30,
        "main_dd50": main.dd50,
        "side": side.slug,
        "side_entry": side.entry,
        "side_dd30": side.dd30,
        "side_dd50": side.dd50,
        "reentry": "R%d" % (1 if max_trades == 2 else (2 if max_trades == 3 else 3)),
        "max_primary_per_week": max_trades,
        "units": int(audit.units),
        "net": net,
        "closed_dd": closed,
        "stress_dd": stress,
        "net_stress": (net / abs(stress)) if stress else 0.0,
        "net_usd_approx": net_usd,
        "stress_usd_approx": stress_usd,
        "net_stress_usd": ns,
        "quote": quote,
        "strategy_id": strategy_id,
        "state_root": str(state_root),
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(
        "[%s] %s units=%d net≈$%.0f stress≈$%.0f N/S=%.2f"
        % (sym, tag, row["units"], net_usd, stress_usd, ns),
        flush=True,
    )
    return row


def write_summary(out: Path, rows: List[dict]) -> None:
    lines = [
        "# Monday OR sizing sweep — broker-like ranking",
        "",
        "Engine + PaperBroker · 15m · 1-tick slip · $1.50/unit · HTF + shifted primary.",
        "Ranked by **≈USD Net/Stress**.",
        "",
    ]
    by_sym: Dict[str, List[dict]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    for sym, srows in by_sym.items():
        ranked = sorted(srows, key=lambda r: float(r["net_stress_usd"]), reverse=True)
        base = next((r for r in ranked if r["tag"] == "M1_S1_R1"), None)
        pick = ranked[0]
        lines.extend(
            [
                "## %s" % sym,
                "",
                (
                    "Baseline `M1_S1_R1`: N/S **%.2f** · ≈$%+.0f net · stress ≈$%+.0f"
                    % (
                        float(base["net_stress_usd"]),
                        float(base["net_usd_approx"]),
                        float(base["stress_usd_approx"]),
                    )
                    if base
                    else "Baseline missing."
                ),
                "",
                "**#1 broker:** `%s` — N/S **%.2f** · ≈$%+.0f · stress ≈$%+.0f · units %d"
                % (
                    pick["tag"],
                    float(pick["net_stress_usd"]),
                    float(pick["net_usd_approx"]),
                    float(pick["stress_usd_approx"]),
                    int(pick["units"]),
                ),
                "",
                "| Rank | Tag | Main | Side | Max/wk | ≈USD Net | ≈USD Stress | **N/S** | Units |",
                "|---:|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for i, r in enumerate(ranked, start=1):
            lines.append(
                "| %d | `%s` | %d=(%d@30,%d@50) | %d=(%d@30,%d@50) | %s | $%+.0f | $%+.0f | **%.2f** | %d |"
                % (
                    i,
                    r["tag"],
                    r["main_entry"],
                    r["main_dd30"],
                    r["main_dd50"],
                    r["side_entry"],
                    r["side_dd30"],
                    r["side_dd50"],
                    r["max_primary_per_week"] if int(r["max_primary_per_week"]) < 90 else "∞",
                    float(r["net_usd_approx"]),
                    float(r["stress_usd_approx"]),
                    float(r["net_stress_usd"]),
                    int(r["units"]),
                )
            )
        lines.append("")
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--pairs", default="EURUSD,USDJPY")
    parser.add_argument("--phase", choices=("1", "full"), default="1")
    parser.add_argument("--force", action="store_true", default=True)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    force = bool(args.force) and not bool(args.no_force)

    mains = MAIN_PHASE1 if args.phase == "1" else MAIN_FULL
    sides = SIDE_PHASE1 if args.phase == "1" else SIDE_FULL
    reentries = REENTRY_PHASE1 if args.phase == "1" else REENTRY_FULL

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    pairs = [p.strip().upper() for p in str(args.pairs).split(",") if p.strip()]
    rows: List[dict] = []

    for sym in pairs:
        if sym not in PAIRS:
            print("skip unknown %s" % sym, flush=True)
            continue
        print("[%s] loading 15m once..." % sym, flush=True)
        bars = load_15m_bars(sym)
        print("[%s] %s bars" % (sym, f"{len(bars):,}"), flush=True)
        cells = [(m, s, r) for m in mains for s in sides for r in reentries]
        for k, (main, side, (rslug, max_tr, _)) in enumerate(cells, start=1):
            tag = "%s_%s_%s" % (main.slug, side.slug, rslug)
            print("[%s] %d/%d %s" % (sym, k, len(cells), tag), flush=True)
            row = run_cell(
                sym,
                bars,
                tag=tag,
                main=main,
                side=side,
                max_trades=max_tr,
                out=out,
                force=force,
            )
            rows.append(row)
            _write_csv(out / "results.csv", rows)
            write_summary(out, rows)

    _write_csv(out / "results.csv", rows)
    write_summary(out, rows)
    print("SUMMARY → %s" % (out / "SUMMARY.md"), flush=True)
    return 0


def _write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    raise SystemExit(main())
