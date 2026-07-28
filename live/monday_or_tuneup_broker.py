"""StrategyPlugin broker battle-test for Monday OR cluster/skip tune-ups.

Replays USDJPY / EURUSD / GBPUSD (and optional others) through Engine +
PaperBroker with ``plugin_config(..., pair=)`` so sitout / skip-after-win
knobs are live in the strategy — not post-hoc fill filters.

Compares against Phase 1 sizing-sweep baseline metrics.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_monday_or_breakout_broker import JPY_USD, PAIRS, load_15m_bars
from .hourly_st_pmc_retest_replay import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS
from .models import StrategyInstance, as_row
from .monday_or_phase2_tags import PAIR_TUNEUPS, PHASE1_STATE_ROOTS, plugin_config
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills, Bar as AuditBar
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monday_or_phase2" / "tuneup_broker"

# Default battle cells (user request + USDJPY alternate with the +2.94 N/S study lift).
CELLS: List[Tuple[str, str]] = [
    ("USDJPY", "M2_S3_R1"),
    ("USDJPY", "M2_S3_R2"),
    ("EURUSD", "M1_S2_R2"),
    ("GBPUSD", "M1_S1_R2"),
]


def _baseline_metrics(pair: str, tag: str) -> Optional[dict]:
    root = REPO / PHASE1_STATE_ROOTS[pair]
    path = root / "states" / ("%s_%s" % (pair.lower(), tag.lower())) / "metrics.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_cell(
    pair: str,
    tag: str,
    out: Path,
    *,
    force: bool,
    bars=None,
    config_overlay: Optional[Dict] = None,
    strategy_suffix: str = "tuneup",
    compare_state_id: Optional[str] = None,
) -> dict:
    meta = PAIRS[pair]
    tick = float(meta["tick"])
    pv = float(meta["pv"])
    POINT_VALUES[pair] = pv
    DEFAULT_TICK_SIZE[pair] = tick

    strategy_id = "%s_%s_%s" % (pair.lower(), tag.lower(), strategy_suffix)
    state_root = out / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        print("[%s] %s cached (%s)" % (pair, tag, strategy_suffix), flush=True)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    if state_root.exists():
        shutil.rmtree(state_root)

    cfg = plugin_config(tick, tag, pair=pair)
    if config_overlay:
        for k, v in config_overlay.items():
            cfg[k] = v
        if "skip_entry_months" in cfg:
            months = []
            for m in cfg["skip_entry_months"] or []:
                try:
                    mi = int(m)
                except (TypeError, ValueError):
                    continue
                if 1 <= mi <= 12:
                    months.append(mi)
            cfg["skip_entry_months"] = sorted(set(months))
    tune = PAIR_TUNEUPS.get((pair, tag), {})
    print(
        "[%s] %s suffix=%s tuneup=%s sitout=%s skip_win=%s skip_months=%s"
        % (
            pair,
            tag,
            strategy_suffix,
            tune.get("tuneup_note"),
            cfg.get("week_sitout_after_pts"),
            cfg.get("skip_after_win_streak"),
            cfg.get("skip_entry_months"),
        ),
        flush=True,
    )

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    max_c = max(int(cfg["entry_qty"]), int(cfg["shifted_entry_qty"])) + 2
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="monday_or_breakout",
        version="v1",
        instrument=pair,
        broker_instrument=pair,
        account_mode="paper",
        enabled=True,
        timeframes="15m",
        max_contracts=max_c,
        max_open_orders=24,
        config_json=json.dumps(cfg, sort_keys=True),
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
    if bars is None:
        bars = load_15m_bars(pair)
    n = len(bars)
    print("[%s] %s bars=%s" % (pair, tag, f"{n:,}"), flush=True)
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 100000 == 0:
            print("  [%s %s] %d/%d" % (pair, tag, idx, n), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    one_m = REPO / "fx" / ("%s_1m.csv" % pair.lower())
    units = units_from_live_fills(fills_path, strategy_id)
    audit_bars = [
        AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars
    ]
    audit = audit_units(
        name="%s Monday OR %s tuneup" % (pair, tag),
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m,
        bars=audit_bars,
        units=units,
        instrument=pair,
        notes="Tune-up broker; fee $1.50; 1-tick slip; StrategyPlugin live knobs.",
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

    base = _baseline_metrics(pair, tag) or {}
    # Optional prior-step archive (XAU sitout-only before Jul/Sep/Dec lock).
    prior_path = out / "states" / ("%s_%s_sitout100_only" % (pair.lower(), tag.lower())) / "metrics.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
    # Compare vs another suffix (e.g. current tuneup when testing Aug+Sep).
    cmp_id = compare_state_id or ("%s_%s_tuneup" % (pair.lower(), tag.lower()))
    cmp_path = out / "states" / cmp_id / "metrics.json"
    cmp = json.loads(cmp_path.read_text(encoding="utf-8")) if cmp_path.exists() and cmp_id != strategy_id else {}
    row = {
        "symbol": pair,
        "tag": tag,
        "tuneup": tune.get("tuneup_note"),
        "strategy_suffix": strategy_suffix,
        "config": cfg,
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
        "baseline_net_usd": base.get("net_usd_approx"),
        "baseline_stress_usd": base.get("stress_usd_approx"),
        "baseline_ns": base.get("net_stress_usd"),
        "baseline_units": base.get("units"),
        "delta_net_usd": (net_usd - float(base["net_usd_approx"]))
        if base.get("net_usd_approx") is not None
        else None,
        "delta_stress_usd": (stress_usd - float(base["stress_usd_approx"]))
        if base.get("stress_usd_approx") is not None
        else None,
        "delta_ns": (ns - float(base["net_stress_usd"]))
        if base.get("net_stress_usd") is not None
        else None,
        "prior_sitout100_net_usd": prior.get("net_usd_approx"),
        "prior_sitout100_stress_usd": prior.get("stress_usd_approx"),
        "prior_sitout100_ns": prior.get("net_stress_usd"),
        "delta_vs_sitout100_net_usd": (net_usd - float(prior["net_usd_approx"]))
        if prior.get("net_usd_approx") is not None
        else None,
        "delta_vs_sitout100_stress_usd": (stress_usd - float(prior["stress_usd_approx"]))
        if prior.get("stress_usd_approx") is not None
        else None,
        "delta_vs_sitout100_ns": (ns - float(prior["net_stress_usd"]))
        if prior.get("net_stress_usd") is not None
        else None,
        "compare_id": cmp_id if cmp else None,
        "compare_net_usd": cmp.get("net_usd_approx"),
        "compare_stress_usd": cmp.get("stress_usd_approx"),
        "compare_ns": cmp.get("net_stress_usd"),
        "delta_vs_compare_net_usd": (net_usd - float(cmp["net_usd_approx"]))
        if cmp.get("net_usd_approx") is not None
        else None,
        "delta_vs_compare_stress_usd": (stress_usd - float(cmp["stress_usd_approx"]))
        if cmp.get("stress_usd_approx") is not None
        else None,
        "delta_vs_compare_ns": (ns - float(cmp["net_stress_usd"]))
        if cmp.get("net_stress_usd") is not None
        else None,
        "state_root": str(state_root),
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(
        "[%s] %s units=%d net≈$%+.0f stress≈$%+.0f N/S=%.2f (vs P1 ΔN/S=%s; vs %s ΔN/S=%s Δnet=$%s)"
        % (
            pair,
            tag,
            row["units"],
            net_usd,
            stress_usd,
            ns,
            ("%.2f" % row["delta_ns"]) if row["delta_ns"] is not None else "n/a",
            cmp_id if cmp else "n/a",
            ("%.2f" % row["delta_vs_compare_ns"]) if row["delta_vs_compare_ns"] is not None else "n/a",
            ("%+.0f" % row["delta_vs_compare_net_usd"])
            if row["delta_vs_compare_net_usd"] is not None
            else "n/a",
        ),
        flush=True,
    )
    return row


def write_summary(out: Path, rows: List[dict]) -> None:
    lines = [
        "# Monday OR tune-up — StrategyPlugin broker",
        "",
        "Engine + PaperBroker · 15m · 1-tick slip · $1.50/unit.",
        "Tune-ups applied **inside** `monday_or_breakout` (not fill post-filters).",
        "",
        "| pair | tag | tune-up | net$ | MTM DD$ | N/S | Δnet$ | ΔMTM$ | ΔN/S | units |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| %s | %s | %s | %+.0f | %+.0f | %.2f | %s | %s | %s | %d |"
            % (
                r["symbol"],
                r["tag"],
                r.get("tuneup") or "—",
                float(r["net_usd_approx"]),
                float(r["stress_usd_approx"]),
                float(r["net_stress_usd"]),
                ("%+.0f" % r["delta_net_usd"]) if r.get("delta_net_usd") is not None else "—",
                ("%+.0f" % r["delta_stress_usd"]) if r.get("delta_stress_usd") is not None else "—",
                ("%+.2f" % r["delta_ns"]) if r.get("delta_ns") is not None else "—",
                int(r["units"]),
            )
        )
    lines.extend(
        [
            "",
            "## Baseline (pre-tune Phase 1 broker)",
            "",
            "| pair | tag | net$ | MTM DD$ | N/S |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for r in rows:
        if r.get("baseline_ns") is None:
            continue
        lines.append(
            "| %s | %s | %+.0f | %+.0f | %.2f |"
            % (
                r["symbol"],
                r["tag"],
                float(r["baseline_net_usd"]),
                float(r["baseline_stress_usd"]),
                float(r["baseline_ns"]),
            )
        )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "SUMMARY.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--cells",
        nargs="*",
        default=None,
        help="Optional PAIR:TAG list (default: USDJPY×2, EURUSD, GBPUSD)",
    )
    ap.add_argument(
        "--skip-months",
        default=None,
        help="Comma months 1-12 to overlay as skip_entry_months (e.g. 8,9)",
    )
    ap.add_argument(
        "--suffix",
        default="tuneup",
        help="State folder suffix (default tuneup). Use e.g. skip_augsep for experiments.",
    )
    ap.add_argument(
        "--summary-name",
        default="SUMMARY.md",
        help="Summary filename under --out (avoid clobbering main SUMMARY for experiments)",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    cells = CELLS
    if args.cells:
        cells = []
        for item in args.cells:
            pair, tag = item.split(":", 1)
            cells.append((pair.upper(), tag.upper()))

    overlay = None
    if args.skip_months:
        months = [int(x.strip()) for x in str(args.skip_months).split(",") if x.strip()]
        overlay = {"skip_entry_months": months}

    # Cache 15m bars per pair
    bar_cache: Dict[str, list] = {}
    rows: List[dict] = []
    for pair, tag in cells:
        if pair not in bar_cache:
            print("[%s] loading 15m..." % pair, flush=True)
            bar_cache[pair] = load_15m_bars(pair)
        rows.append(
            run_cell(
                pair,
                tag,
                out,
                force=args.force,
                bars=bar_cache[pair],
                config_overlay=overlay,
                strategy_suffix=args.suffix,
            )
        )
    # Dedicated experiment summary when not writing main SUMMARY
    if args.summary_name != "SUMMARY.md" or args.suffix != "tuneup":
        exp = out / args.summary_name
        lines = [
            "# Experiment — StrategyPlugin broker",
            "",
            "suffix=`%s` overlay=%s" % (args.suffix, overlay),
            "",
            "| pair | tag | net$ | MTM DD$ | N/S | vs current tuneup ΔN/S | Δnet$ | ΔMTM$ | units |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            lines.append(
                "| %s | %s | %+.0f | %+.0f | %.2f | %s | %s | %s | %d |"
                % (
                    r["symbol"],
                    r["tag"],
                    float(r["net_usd_approx"]),
                    float(r["stress_usd_approx"]),
                    float(r["net_stress_usd"]),
                    ("%+.2f" % r["delta_vs_compare_ns"])
                    if r.get("delta_vs_compare_ns") is not None
                    else "—",
                    ("%+.0f" % r["delta_vs_compare_net_usd"])
                    if r.get("delta_vs_compare_net_usd") is not None
                    else "—",
                    ("%+.0f" % r["delta_vs_compare_stress_usd"])
                    if r.get("delta_vs_compare_stress_usd") is not None
                    else "—",
                    int(r["units"]),
                )
            )
        lines.append("")
        lines.append("Compare baseline = existing `*_tuneup` metrics (current core knobs).")
        exp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        (out / (Path(args.summary_name).stem + ".json")).write_text(
            json.dumps(rows, indent=2, default=str), encoding="utf-8"
        )
        print("DONE → %s" % exp, flush=True)
    else:
        write_summary(out, rows)
        print("DONE → %s" % (out / "SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
