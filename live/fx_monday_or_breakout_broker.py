"""Broker-like StrategyPlugin battle test: Monday OR breakout across FX/metals.

Runs ``monday_or_breakout`` through Engine + PaperBroker on 15m bars derived
from ``fx/{pair}_1m.csv`` (Histdata via ``fx/raw/``). Default config matches
the research best CE sleeve: 3 lots, DD cuts 30%/50%, shifted primary, HTF
both-opposed skip.

Instruments: EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_retest_replay import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


from .monday_or_phase2_tags import PAIR_PHASE2_DEFAULT, plugin_config, resolve_tag


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "fx_monday_or_breakout_broker"
JPY_USD = 110.0

PAIRS: Dict[str, Dict[str, object]] = {
    "EURUSD": dict(tick=0.00001, quote="USD", pv=100_000.0),
    "GBPUSD": dict(tick=0.00001, quote="USD", pv=100_000.0),
    "USDJPY": dict(tick=0.001, quote="JPY", pv=100_000.0),
    "AUDJPY": dict(tick=0.001, quote="JPY", pv=100_000.0),
    "XAUUSD": dict(tick=0.01, quote="USD", pv=100.0),
    "XAGUSD": dict(tick=0.001, quote="USD", pv=1000.0),
}


def resample_15m(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("15min", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def load_15m_bars(sym: str) -> List[Bar]:
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    if not one_m.exists():
        raise FileNotFoundError("Missing %s — convert from fx/raw first" % one_m)
    bars_by_day = load_fx_1m_by_ny_date(one_m, sym)
    m15 = resample_15m(concat_all_1m(bars_by_day))
    out: List[Bar] = []
    for ts, row in m15.iterrows():
        out.append(
            Bar(
                instrument=sym,
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
    return out


def _config_json(tick: float, sym: str, tag: Optional[str] = None) -> str:
    """Pair-specific Phase 2 / Phase 1-footnote tag; falls back to M1_S1_R1 baseline."""
    use_tag = tag or PAIR_PHASE2_DEFAULT.get(sym)
    if use_tag:
        try:
            return json.dumps(plugin_config(tick, use_tag), sort_keys=True)
        except KeyError:
            pass
    # Pre-Phase-2 baseline (M1_S1_R1)
    return json.dumps(
        {
            "tick_size": tick,
            "entry_qty": 3,
            "dd30_qty": 2,
            "dd50_qty": 1,
            "shifted_entry_qty": 3,
            "shifted_dd30_qty": 2,
            "shifted_dd50_qty": 1,
            "reward_R": 2.0,
            "max_trades_per_week": 2,
            "skip_both_opposed": True,
            "shifted_primary": True,
            "obv_ma": 20,
        },
        sort_keys=True,
    )


def run_pair(sym: str, out: Path, force: bool, tag: Optional[str] = None) -> dict:
    meta = PAIRS[sym]
    tick = float(meta["tick"])
    pv = float(meta["pv"])
    POINT_VALUES[sym] = pv
    DEFAULT_TICK_SIZE[sym] = tick

    use_tag = tag or PAIR_PHASE2_DEFAULT.get(sym) or "M1_S1_R1"
    strategy_id = "%s_monday_or_%s" % (sym.lower(), use_tag.lower())
    state_root = out / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    fills_path = state_root / "fills.csv"
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    if (not force) and metrics_path.exists():
        print("[%s] using cached metrics (%s)" % (sym, use_tag), flush=True)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    print("[%s] loading 15m bars (tag=%s)..." % (sym, use_tag), flush=True)
    bars = load_15m_bars(sym)
    print("[%s] %s 15m bars" % (sym, f"{len(bars):,}"), flush=True)

    need_replay = force or not fills_path.exists()
    if need_replay:
        if force and state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        try:
            spec = resolve_tag(use_tag)
            max_c = max(int(spec["entry_qty"]), int(spec["shifted_entry_qty"])) + 2
        except KeyError:
            max_c = 5
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
            config_json=_config_json(tick, sym, use_tag),
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
        print("[%s] replaying..." % sym, flush=True)
        for idx, bar in enumerate(bars, start=1):
            engine.process_bar(bar)
            if idx % 50000 == 0:
                print("  [%s] %d/%d" % (sym, idx, len(bars)), flush=True)
        if hasattr(engine.broker, "flush_state"):
            engine.broker.flush_state()
        store.flush_tables()
    else:
        print("[%s] auditing existing fills (skip replay)" % sym, flush=True)

    units = units_from_live_fills(fills_path, strategy_id)
    from .replay_audit import Bar as AuditBar

    audit_bars = [
        AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars
    ]
    audit = audit_units(
        name="%s Monday OR shiftprim+HTF" % sym,
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m,
        bars=audit_bars,
        units=units,
        instrument=sym,
        notes="Monday OR breakout shifted-primary + HTF; fee $1.50; 1-tick slip.",
        output_root=out / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    net = float(audit.net_usd)
    stress = float(audit.intrabar_mtm_dd_usd)
    closed = float(audit.close_mtm_dd_usd)
    ns = (net / abs(stress)) if stress else 0.0
    quote = str(meta["quote"])
    net_usd_approx = net / JPY_USD if quote == "JPY" else net
    stress_usd_approx = stress / JPY_USD if quote == "JPY" else stress
    row = {
        "symbol": sym,
        "tag": use_tag,
        "quote": quote,
        "strategy_id": strategy_id,
        "units": int(audit.units),
        "net": net,
        "closed_dd": closed,
        "stress_dd": stress,
        "net_stress": ns,
        "net_usd_approx": net_usd_approx,
        "stress_usd_approx": stress_usd_approx,
        "net_stress_usd_approx": (net_usd_approx / abs(stress_usd_approx)) if stress_usd_approx else 0.0,
        "state_root": str(state_root),
    }
    (state_root / "metrics.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(
        "[%s] units=%d net=%.0f stress=%.0f N/S=%.2f%s"
        % (
            sym,
            row["units"],
            net,
            stress,
            ns,
            (" (≈$%.0f / N/S≈%.2f)" % (net_usd_approx, row["net_stress_usd_approx"]))
            if quote == "JPY"
            else "",
        ),
        flush=True,
    )
    return row


def write_summary(out: Path, rows: List[dict]) -> None:
    lines = [
        "# FX Monday OR breakout — broker-like (StrategyPlugin)",
        "",
        "Plugin: `monday_or_breakout` · Engine + PaperBroker · 15m bars · "
        "1-tick slip · $1.50/unit fee.",
        "",
        "## Rules",
        "",
        "- Mon OR H/L → Tue–Fri close breakout; **3** lots; drop **2**@30% DD, cut **1**@50%; "
        "SL=1R TP=2R.",
        "- **Shifted primary** after flat@50% (opposite Mon extreme, same structure).",
        "- **HTF filter:** skip when last 1h MA50/150 and OBV×SMA20 both opposed.",
        "- Max 2 primary trades/week.",
        "",
        "## Results (ranked by Net/Stress; JPY pairs also show ≈USD @ 110)",
        "",
        "| Rank | Pair | Units | Net | Stress DD | **N/S** | ≈USD net | ≈USD N/S |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = sorted(rows, key=lambda r: r["net_stress_usd_approx"], reverse=True)
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | **%s** | %d | %s%.0f | %s%.0f | **%.2f** | $%.0f | **%.2f** |"
            % (
                i,
                r["symbol"],
                r["units"],
                "" if r["quote"] == "USD" else ("¥" if r["quote"] == "JPY" else ""),
                r["net"],
                "" if r["quote"] == "USD" else ("¥" if r["quote"] == "JPY" else ""),
                r["stress_dd"],
                r["net_stress"],
                r["net_usd_approx"],
                r["net_stress_usd_approx"],
            )
        )
    lines.extend(
        [
            "",
            "## vs STRATEGY_TRACKER FX intraday baseline",
            "",
            "Promoted FX **intraday** sleeve today: Hourly ST+PMC MA-bull "
            "(EURUSD **+$23.5k / −$15.7k / 1.49** Net/Stress).",
            "Monthly FBO sleeves are a different horizon ($7 fee pack).",
            "",
            "Research pandas sim (EURUSD, not broker): shiftprim+HTF "
            "**+$124.6k / −$56.4k closed / 2.21** Net/|DD| — expect broker "
            "slip + next-open entry to compress that.",
            "",
            "State root: `%s`" % out,
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--pairs",
        default=",".join(PAIRS.keys()),
        help="Comma-separated symbols (default: all)",
    )
    parser.add_argument("--force", action="store_true", default=True)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    force = bool(args.force) and not bool(args.no_force)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    pairs = [p.strip().upper() for p in str(args.pairs).split(",") if p.strip()]
    rows: List[dict] = []
    for sym in pairs:
        if sym not in PAIRS:
            print("Skip unknown pair %s" % sym, flush=True)
            continue
        try:
            rows.append(run_pair(sym, out, force))
            write_summary(out, rows)  # incremental
        except Exception as exc:
            print("[%s] FAILED: %s" % (sym, exc), flush=True)
            import traceback

            traceback.print_exc()
    write_summary(out, rows)
    print("SUMMARY → %s" % (out / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
