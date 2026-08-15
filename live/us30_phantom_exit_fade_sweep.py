"""US30: fade phantom exits of hourly ST+PMC and v2b via StrategyPlugin.

For each source variant's would-be exit (from prior broker fills):
- original long + TP → fade short; original long + SL → fade long
- original short + TP → fade long; original short + SL → fade short

Nested grid: each source × fade risk pairs (25/75, 40/120, 50/150),
same index-point risk sweep as hourly ST+PMC.

ST+PMC source order: 50/150 → 40/120 → 25/75 → 25/75+MA.
v2b: first non-EOD exit per trade (tp1/tp2 = TP; wide_stop/runner_stop = SL).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

REPO = Path(__file__).resolve().parents[1]
SRC_SWEEP = REPO / "live" / "state" / "us30_futures_strats_sweep"
OUT = REPO / "live" / "state" / "us30_phantom_exit_fade_sweep"

SYM = "US30"
MARKET = "us30"
TICK = 0.1
POINT_VALUE = 1.0
FEE = DEFAULT_FEE_PER_UNIT

# Fade risk sweep (same absolute distances as ST+PMC index-point pack).
FADE_RISKS: List[Tuple[str, float, float]] = [
    ("sl25_tp75", 25.0, 75.0),
    ("sl40_tp120", 40.0, 120.0),
    ("sl50_tp150", 50.0, 150.0),
]

# Source phantoms: ST+PMC fills, ordered as requested (wide → tight, then MA).
ST_PMC_SOURCES: List[Tuple[str, Path]] = [
    (
        "sl50_tp150_3r",
        SRC_SWEEP / "st_pmc" / "states" / "us30_hourly_st_pmc_sl50_tp150_3r" / "fills.csv",
    ),
    (
        "sl40_tp120_3r",
        SRC_SWEEP / "st_pmc" / "states" / "us30_hourly_st_pmc_sl40_tp120_3r" / "fills.csv",
    ),
    (
        "sl25_tp75_3r",
        SRC_SWEEP / "st_pmc" / "states" / "us30_hourly_st_pmc_sl25_tp75_3r" / "fills.csv",
    ),
    (
        "sl25_tp75_3r_ma_directional_prior",
        SRC_SWEEP
        / "st_pmc"
        / "states"
        / "us30_hourly_st_pmc_sl25_tp75_3r_ma_directional_prior"
        / "fills.csv",
    ),
]

V2B_FILLS = SRC_SWEEP / "states" / "us30_v2b_oco_prior_opposed_S_1_1_3" / "fills.csv"

ST_PMC_EXIT = {"stop", "target"}
V2B_TP = {"tp1", "tp2"}
V2B_SL = {"wide_stop", "runner_stop"}
V2B_SKIP = {"eod_close", "eod", "flatten", "entry"}


def _progress(msg: str) -> None:
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _ensure_meta() -> None:
    POINT_VALUES[SYM] = POINT_VALUE
    DEFAULT_TICK_SIZE[SYM] = TICK


def _fade_side(entry_side: str, exit_reason: str, *, tp_reasons: set, sl_reasons: set) -> Optional[str]:
    """Return fade market side (buy/sell) from source entry + exit kind."""
    ent = str(entry_side).lower()
    reason = str(exit_reason).lower()
    if ent not in {"buy", "sell"}:
        return None
    if reason in tp_reasons:
        # Fade the TP: opposite of original.
        return "sell" if ent == "buy" else "buy"
    if reason in sl_reasons:
        # Fade the SL: same side as original (enter from the stop level).
        return ent
    return None


def phantoms_from_st_pmc_fills(fills_path: Path) -> List[Dict[str, Any]]:
    df = pd.read_csv(fills_path)
    out: List[Dict[str, Any]] = []
    for trade_id, g in df.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"].isin(ST_PMC_EXIT)]
        if entries.empty or exits.empty:
            continue
        ent = entries.iloc[0]
        ex = exits.iloc[0]
        side = _fade_side(ent["side"], ex["reason"], tp_reasons={"target"}, sl_reasons={"stop"})
        if side is None:
            continue
        out.append(
            {
                "source_trade_id": str(trade_id),
                "source_entry_side": str(ent["side"]).lower(),
                "source_exit_reason": str(ex["reason"]),
                "trigger_ts": str(ex["ts"]),
                "trigger_price": float(ex["price"]),
                "fade_side": side,
            }
        )
    return sorted(out, key=lambda p: p["trigger_ts"])


def phantoms_from_v2b_fills(fills_path: Path) -> List[Dict[str, Any]]:
    """First TP/SL exit per trade; skip EOD-only phantoms."""
    df = pd.read_csv(fills_path)
    out: List[Dict[str, Any]] = []
    for trade_id, g in df.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        if entries.empty:
            continue
        ent = entries.iloc[0]
        first = None
        for _, row in g.iterrows():
            reason = str(row["reason"])
            if reason == "entry":
                continue
            if reason in V2B_SKIP:
                # EOD before a structural exit → no fade trigger for this trade.
                break
            if reason in V2B_TP or reason in V2B_SL:
                first = row
                break
        if first is None:
            continue
        side = _fade_side(
            ent["side"],
            first["reason"],
            tp_reasons=V2B_TP,
            sl_reasons=V2B_SL,
        )
        if side is None:
            continue
        out.append(
            {
                "source_trade_id": str(trade_id),
                "source_entry_side": str(ent["side"]).lower(),
                "source_exit_reason": str(first["reason"]),
                "trigger_ts": str(first["ts"]),
                "trigger_price": float(first["price"]),
                "fade_side": side,
            }
        )
    return sorted(out, key=lambda p: p["trigger_ts"])


def load_1m_and_hourly_bars() -> Tuple[List[Bar], List[Bar]]:
    one_m = REPO / "fx" / "us30_1m.csv"
    gby = load_fx_1m_by_ny_date(one_m, SYM)
    df = concat_all_1m(gby)
    bars_1m: List[Bar] = []
    for ts, row in df.iterrows():
        bars_1m.append(
            Bar(
                instrument=SYM,
                timeframe="1m",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(one_m),
            )
        )
    hourly = (
        df.resample("1h", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )
    bars_1h: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars_1h.append(
            Bar(
                instrument=SYM,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source="resampled_1h_for_audit",
            )
        )
    return bars_1m, bars_1h


def _plugin_flat(engine: Engine, strategy_id: str) -> bool:
    try:
        plugin = engine.manager.plugins[strategy_id]
    except Exception:
        return True
    state = plugin.state or {}
    if state.get("current_leg_open") or state.get("awaiting_entry"):
        return False
    # Belt-and-suspenders: any resting orders mean we must keep ticking.
    try:
        open_orders = engine.broker.open_orders_for_strategy(strategy_id)  # type: ignore[attr-defined]
        if open_orders:
            return False
    except Exception:
        pass
    return True


def _next_phantom_ts(engine: Engine, strategy_id: str, phantoms: Sequence[Dict[str, Any]]) -> Optional[str]:
    try:
        plugin = engine.manager.plugins[strategy_id]
    except Exception:
        return phantoms[0]["trigger_ts"] if phantoms else None
    state = plugin.state or {}
    idx = int(state.get("phantom_idx") or 0)
    if idx >= len(phantoms):
        return None
    return str(phantoms[idx].get("trigger_ts") or "") or None


def replay_fade(
    *,
    strategy_id: str,
    phantoms: List[Dict[str, Any]],
    fade_name: str,
    stop_pts: float,
    target_pts: float,
    bars: List[Bar],
    state_root: Path,
    phantoms_path: Path,
    force: bool,
) -> Path:
    fills_path = state_root / "fills.csv"
    if (not force) and fills_path.exists() and fills_path.stat().st_size > 100:
        return fills_path
    if force and state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    phantoms_path.parent.mkdir(parents=True, exist_ok=True)
    phantoms_path.write_text(json.dumps(phantoms, indent=2), encoding="utf-8")

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    cfg = {
        "tick_size": TICK,
        "entry_qty": 1,
        "stop_pts": stop_pts,
        "target_pts": target_pts,
        "phantoms_path": str(phantoms_path),
        "timeframe": "1m",
    }
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="phantom_exit_fade",
        version="v1",
        instrument=SYM,
        broker_instrument=SYM,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=1,
        max_open_orders=8,
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

    n = len(bars)
    i = 0
    processed = 0
    while i < n:
        # Skip idle bars while flat until the next phantom trigger.
        if _plugin_flat(engine, strategy_id):
            nxt = _next_phantom_ts(engine, strategy_id, phantoms)
            if nxt is None:
                break
            bar_ts = bars[i].ts
            if bar_ts < nxt:
                # Binary search forward to first bar >= nxt
                lo, hi = i, n
                while lo < hi:
                    mid = (lo + hi) // 2
                    if bars[mid].ts < nxt:
                        lo = mid + 1
                    else:
                        hi = mid
                i = lo
                if i >= n:
                    break
        engine.process_bar(bars[i])
        processed += 1
        i += 1
        if processed % 200000 == 0:
            _progress("  %s processed %d bars (i=%d/%d)" % (strategy_id, processed, i, n))

    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()
    return fills_path


def _row_ok(family: str, name: str, strategy_id: str, audit) -> dict:
    ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    return dict(
        family=family,
        name=name,
        strategy_id=strategy_id,
        status="ok",
        units=audit.units,
        trades=audit.trades,
        net_usd=round(audit.net_usd, 2),
        stress_dd_usd=round(audit.intrabar_mtm_dd_usd, 2),
        ns=round(ns, 2),
        wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
        phantoms=getattr(audit, "_phantoms", None),
    )


def _write_summary(rows: List[dict]) -> None:
    if not rows:
        return
    keys: List[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    path = OUT / "summary.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _audit_fade(
    *,
    strategy_id: str,
    name: str,
    fills_path: Path,
    audit_bars: List[Bar],
    notes: str,
) -> Any:
    units = units_from_live_fills(fills_path, strategy_id)
    return audit_units(
        name=name,
        slug=strategy_id,
        source=fills_path,
        bar_source=REPO / "fx" / "us30_1m.csv",
        bars=audit_bars,
        units=units,
        instrument=SYM,
        notes=notes,
        output_root=OUT / "audits" / strategy_id,
        fee_per_unit=FEE,
    )


def run_st_pmc_grid(
    rows: List[dict],
    bars: List[Bar],
    audit_bars: List[Bar],
    force: bool,
    sources: Optional[List[str]],
    max_phantoms: Optional[int],
) -> None:
    for src_name, fills in ST_PMC_SOURCES:
        if sources and src_name not in sources:
            continue
        if not fills.exists():
            _progress("MISSING source fills %s" % fills)
            continue
        phantoms = phantoms_from_st_pmc_fills(fills)
        if max_phantoms is not None:
            phantoms = phantoms[: max(0, int(max_phantoms))]
        _progress("ST+PMC source %s → %d phantoms" % (src_name, len(phantoms)))
        for fade_name, stop_pts, target_pts in FADE_RISKS:
            sid = "us30_fade_stpmc_%s__%s" % (src_name, fade_name)
            if any(str(r.get("strategy_id")) == sid and r.get("status") == "ok" for r in rows) and not force:
                _progress("SKIP %s" % sid)
                continue
            _progress("START %s (%d phantoms, fade %g/%g)" % (sid, len(phantoms), stop_pts, target_pts))
            state_root = OUT / "st_pmc" / "states" / sid
            phantoms_path = OUT / "st_pmc" / "phantoms" / ("%s.json" % src_name)
            try:
                fills_path = replay_fade(
                    strategy_id=sid,
                    phantoms=phantoms,
                    fade_name=fade_name,
                    stop_pts=stop_pts,
                    target_pts=target_pts,
                    bars=bars,
                    state_root=state_root,
                    phantoms_path=phantoms_path,
                    force=force,
                )
                audit = _audit_fade(
                    strategy_id=sid,
                    name="US30 fade ST+PMC %s → %s" % (src_name, fade_name),
                    fills_path=fills_path,
                    audit_bars=audit_bars,
                    notes=(
                        "Phantom-exit fade of hourly ST+PMC %s. Fade SL/TP=%g/%g. "
                        "Phantoms=%d. Fee=$%.2f/unit. MTM audit on hourly resample."
                        % (src_name, stop_pts, target_pts, len(phantoms), FEE)
                    ),
                )
                row = _row_ok(
                    family="st_pmc_phantom_fade",
                    name="fade %s × %s" % (src_name, fade_name),
                    strategy_id=sid,
                    audit=audit,
                )
                row["phantoms"] = len(phantoms)
                row["source"] = src_name
                row["fade"] = fade_name
                rows.append(row)
                _progress("DONE %s Net=$%.0f N/S=%.2f units=%s" % (sid, audit.net_usd, row["ns"], audit.units))
            except Exception as exc:
                import traceback

                _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
                rows.append(
                    dict(
                        family="st_pmc_phantom_fade",
                        name="fade %s × %s" % (src_name, fade_name),
                        strategy_id=sid,
                        status="error",
                        error=str(exc),
                        source=src_name,
                        fade=fade_name,
                        phantoms=len(phantoms),
                    )
                )
            _write_summary(rows)


def run_v2b_grid(
    rows: List[dict],
    bars: List[Bar],
    audit_bars: List[Bar],
    force: bool,
    max_phantoms: Optional[int],
) -> None:
    if not V2B_FILLS.exists():
        _progress("MISSING v2b fills %s" % V2B_FILLS)
        return
    phantoms = phantoms_from_v2b_fills(V2B_FILLS)
    if max_phantoms is not None:
        phantoms = phantoms[: max(0, int(max_phantoms))]
    _progress("v2b source → %d phantoms" % len(phantoms))
    for fade_name, stop_pts, target_pts in FADE_RISKS:
        sid = "us30_fade_v2b_prior_opposed__%s" % fade_name
        if any(str(r.get("strategy_id")) == sid and r.get("status") == "ok" for r in rows) and not force:
            _progress("SKIP %s" % sid)
            continue
        _progress("START %s (%d phantoms, fade %g/%g)" % (sid, len(phantoms), stop_pts, target_pts))
        state_root = OUT / "v2b" / "states" / sid
        phantoms_path = OUT / "v2b" / "phantoms" / "prior_opposed.json"
        try:
            fills_path = replay_fade(
                strategy_id=sid,
                phantoms=phantoms,
                fade_name=fade_name,
                stop_pts=stop_pts,
                target_pts=target_pts,
                bars=bars,
                state_root=state_root,
                phantoms_path=phantoms_path,
                force=force,
            )
            audit = _audit_fade(
                strategy_id=sid,
                name="US30 fade v2b prior-opposed → %s" % fade_name,
                fills_path=fills_path,
                audit_bars=audit_bars,
                notes=(
                    "Phantom-exit fade of v2b prior-opposed S_1_1_3 (first TP/SL). "
                    "Fade SL/TP=%g/%g. Phantoms=%d. Fee=$%.2f/unit. MTM audit on hourly resample."
                    % (stop_pts, target_pts, len(phantoms), FEE)
                ),
            )
            row = _row_ok(
                family="v2b_phantom_fade",
                name="fade v2b × %s" % fade_name,
                strategy_id=sid,
                audit=audit,
            )
            row["phantoms"] = len(phantoms)
            row["source"] = "v2b_prior_opposed"
            row["fade"] = fade_name
            rows.append(row)
            _progress("DONE %s Net=$%.0f N/S=%.2f units=%s" % (sid, audit.net_usd, row["ns"], audit.units))
        except Exception as exc:
            import traceback

            _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
            rows.append(
                dict(
                    family="v2b_phantom_fade",
                    name="fade v2b × %s" % fade_name,
                    strategy_id=sid,
                    status="error",
                    error=str(exc),
                    source="v2b_prior_opposed",
                    fade=fade_name,
                    phantoms=len(phantoms),
                )
            )
        _write_summary(rows)


def write_report(rows: List[dict]) -> None:
    ok = [r for r in rows if r.get("status") == "ok"]
    lines = [
        "# US30 — Phantom-exit fade sweep",
        "",
        "Fade the would-be SL/TP of hourly ST+PMC and v2b (do not take the source trade).",
        "Fade risk sweep: 25/75, 40/120, 50/150 (index points). Broker = Engine + PaperBroker.",
        "",
        "| family | source | fade | net_usd | stress_dd | N/S | units | wr% |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(ok, key=lambda x: -float(x.get("ns") or 0)):
        lines.append(
            "| %s | %s | %s | %.0f | %.0f | %.2f | %s | %s |"
            % (
                r.get("family"),
                r.get("source"),
                r.get("fade"),
                float(r.get("net_usd") or 0),
                float(r.get("stress_dd_usd") or 0),
                float(r.get("ns") or 0),
                r.get("units"),
                r.get("wr_units"),
            )
        )
    lines.extend(
        [
            "",
            "Driver: `live/us30_phantom_exit_fade_sweep.py`",
            "Plugin: `phantom_exit_fade`",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["stpmc", "v2b", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--sources",
        type=str,
        default="",
        help="Comma-separated ST+PMC source names to run (default: all).",
    )
    p.add_argument("--max-phantoms", type=int, default=None, help="Cap phantoms per source (smoke tests).")
    args = p.parse_args()
    _ensure_meta()
    OUT.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    summary_path = OUT / "summary.csv"
    if summary_path.exists() and not args.force:
        rows = pd.read_csv(summary_path).to_dict("records")

    _progress("loading US30 1m + hourly audit bars...")
    bars, audit_bars = load_1m_and_hourly_bars()
    _progress("1m bars: %d | hourly audit bars: %d" % (len(bars), len(audit_bars)))

    sources = [s.strip() for s in args.sources.split(",") if s.strip()] or None
    if args.stage in ("stpmc", "all"):
        run_st_pmc_grid(rows, bars, audit_bars, args.force, sources, args.max_phantoms)
    if args.stage in ("v2b", "all"):
        run_v2b_grid(rows, bars, audit_bars, args.force, args.max_phantoms)
    write_report(rows)
    _progress("DONE — wrote %s" % (OUT / "summary.csv"))


if __name__ == "__main__":
    main()
