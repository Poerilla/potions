"""NQ-lead NAS100 synced follower — broker-like replay.

Uses existing NQ prior-opposed campaign entries as the lead signal. NAS100 only
enters inside a tight sync window with mapped OR structure checks, then manages
local CFD ``S_1_1_1`` exits. Standalone NQ / NAS100 prior-opposed paths are
untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import ensure_nas100_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_strategyplugin_variants import REPO
from .models import Bar, StrategyInstance, as_row
from .nq_lead_nas100_sync import attach_mapped_or, campaigns_for_json, load_nq_lead_campaigns
from .nq_v2b_prior_opposed_replay import Result, write_report
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills


INSTRUMENT = "NAS100"
MARKET = "nas100"
TICK = 0.1
# Native CFD book stays $1/pt; reporting / economic standard for NQ-lead is ×40
# (entry reading: S_1_1_1 qty 3 @ $40/pt ≡ $120 per index point).
POINT_VALUE = 1.0
DOLLAR_SCALE = 40.0
FEE_PER_UNIT = 1.50
DEFAULT_START = date(2021, 3, 4)
STRATEGY_ID = "nas100_v2b_nq_lead_synced_S_1_1_1"
DEFAULT_NQ_ROOT = REPO / "live" / "state" / "nq_v2b_prior_opposed_stpmc_broker_like"
DEFAULT_OUTPUT = REPO / "live" / "state" / "nas100_v2b_nq_lead_synced_broker_like"


def _ensure_meta() -> None:
    POINT_VALUES.setdefault(INSTRUMENT, POINT_VALUE)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)


def _dump_sync_audit(state_root: Path, output_root: Path) -> Path:
    """Flatten plugin sync_audit from strategy_state into sync_audit.csv."""

    import sys

    csv.field_size_limit(sys.maxsize)
    path = state_root / "strategy_state.csv"
    out = output_root / "sync_audit.csv"
    rows: List[Dict[str, Any]] = []
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    state = json.loads(row.get("state_json") or "{}")
                except json.JSONDecodeError:
                    continue
                for item in state.get("sync_audit") or []:
                    rows.append(dict(item))
    fields = [
        "campaign_id",
        "side",
        "t_nq",
        "t_nas",
        "entry_delta_seconds",
        "state",
        "skip_reason",
        "nas_signal_px",
        "nq_entry",
        "mapped_or_high",
        "mapped_or_low",
        "map_ratio",
    ]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return out


def _summarize(
    strategy_id: str,
    state_root: Path,
    audit_bars: List[AuditBar],
    *,
    regime_days: int,
    start_date: date,
    sync_audit_path: Path,
) -> Result:
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intrabar_safe(strategy_id, state_root, audit_bars, units)
    net = float(audit["net_usd"])
    stress = float(audit["intrabar_stress_dd_usd"])
    point_value = POINT_VALUES[INSTRUMENT]
    unit_pnl = [(u.points * point_value - FEE_PER_UNIT) for u in units]
    gross_win = sum(v for v in unit_pnl if v > 0)
    gross_loss = abs(sum(v for v in unit_pnl if v <= 0))
    trade_ids = sorted({u.trade_id for u in units})
    wins_by_trade = 0
    side_by_trade: Dict[str, str] = {}
    for tid in trade_ids:
        trade_units = [u for u in units if u.trade_id == tid]
        pnl = sum((u.points * point_value - FEE_PER_UNIT) for u in trade_units)
        if trade_units:
            side_by_trade[tid] = "long" if trade_units[0].direction.lower().startswith("long") else "short"
        if pnl > 0:
            wins_by_trade += 1

    entered = skipped = 0
    if sync_audit_path.exists():
        with sync_audit_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("state") == "entered":
                    entered += 1
                elif row.get("state") == "skipped":
                    skipped += 1

    return Result(
        strategy_id=strategy_id,
        trades=len(trade_ids),
        units=len(units),
        net_usd=net,
        closed_dd_usd=float(audit["closed_dd_usd"]),
        stress_dd_usd=stress,
        win_rate_pct=100.0 * wins_by_trade / len(trade_ids) if trade_ids else 0.0,
        profit_factor=gross_win / gross_loss if gross_loss else math.inf,
        net_stress=net / abs(stress) if stress else 0.0,
        state_root=state_root,
        instrument=INSTRUMENT,
        market=MARKET,
        regime_days=regime_days,
        prior_opposite_entries=entered,
        causality_violations=skipped,
        long_trades=sum(1 for side in side_by_trade.values() if side == "long"),
        short_trades=sum(1 for side in side_by_trade.values() if side == "short"),
        start_date=start_date,
    )


def fast_intrabar_safe(strategy_id, state_root, audit_bars, units):
    try:
        return fast_intraday_audit(
            strategy_id=strategy_id,
            state_root=state_root,
            bars=audit_bars,
            units=units,
            instrument=INSTRUMENT,
            fee_per_unit=FEE_PER_UNIT,
        )
    except Exception:
        # Fallback minimal metrics from unit PnL only.
        point_value = POINT_VALUES[INSTRUMENT]
        pnls = [u.points * point_value - FEE_PER_UNIT for u in units]
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)
        return {
            "net_usd": sum(pnls),
            "closed_dd_usd": max_dd,
            "intrabar_stress_dd_usd": max_dd,
        }


def run(
    *,
    output_root: Path,
    nq_state_root: Path,
    force: bool = True,
    start: date = DEFAULT_START,
    end: Optional[date] = None,
    t_max_seconds: float = 60.0,
    delta_early_seconds: float = 30.0,
    max_days: Optional[int] = None,
    force_convert: bool = False,
) -> Result:
    _ensure_meta()
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    one_m, _daily = ensure_nas100_platform_files(REPO, force=force_convert)

    print("Loading NQ lead campaigns from %s ..." % nq_state_root, flush=True)
    campaigns = load_nq_lead_campaigns(Path(nq_state_root), start=start, end=end)
    print("  %d sessions with lead campaigns" % len(campaigns), flush=True)

    print("Loading NAS100 1m bars ...", flush=True)
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    campaigns = attach_mapped_or(campaigns, gby)
    lead_json = campaigns_for_json(campaigns)

    # Replay sessions that have both a lead campaign and NAS bars.
    sessions = sorted(date.fromisoformat(s) for s in campaigns if date.fromisoformat(s) in gby)
    sessions = [d for d in sessions if d >= start]
    if end is not None:
        sessions = [d for d in sessions if d <= end]
    if max_days is not None:
        sessions = sessions[:max_days]
    print("  replay sessions: %d" % len(sessions), flush=True)

    state_root = output_root / "states" / STRATEGY_ID
    if force and state_root.exists():
        shutil.rmtree(state_root)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=STRATEGY_ID,
        strategy_type="v2b_nq_lead_nas100",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=5,
        max_open_orders=64,
        config_json=json.dumps(
            {
                "tick_size": TICK,
                "entry_qty": 3,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "t_max_seconds": t_max_seconds,
                "delta_early_seconds": delta_early_seconds,
                "nq_lead_campaigns": lead_json,
                "record_sync_audit": True,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])

    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={INSTRUMENT: TICK},
        **hardened_replay_engine_kwargs(slippage_ticks=1.0),
    )

    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(sessions, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            if pd.isna(row.get("close")):
                continue
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=INSTRUMENT,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(one_m),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 100 == 0:
            print("  NAS100 nq-lead %d/%d sessions" % (idx, len(sessions)), flush=True)
    store.flush_tables()

    sync_path = _dump_sync_audit(state_root, output_root)
    result = _summarize(
        STRATEGY_ID,
        state_root,
        audit_bars,
        regime_days=len(sessions),
        start_date=start,
        sync_audit_path=sync_path,
    )
    write_report(output_root, result, gate_mode="nq_lead_sync")
    # Rewrite INDEX with sync-specific blurb.
    index = output_root / "INDEX.md"
    extra = [
        "",
        "## NQ-lead sync",
        "",
        "- Lead book: `%s`" % nq_state_root,
        "- Sync ceiling: **%.0fs** (early Δ **%.0fs**)" % (t_max_seconds, delta_early_seconds),
        "- Entered campaigns (audit): **%d**" % result.prior_opposite_entries,
        "- Skipped campaigns (audit): **%d**" % result.causality_violations,
        "- CFD-local exits: `S_1_1_1` + EOD on NAS100 after synced entry",
        "- Original NQ / standalone NAS100 prior-opposed strategies unchanged",
        "",
        "Files: `summary.csv`, `sync_audit.csv`, `states/%s/`" % STRATEGY_ID,
        "",
    ]
    if index.exists():
        index.write_text(index.read_text(encoding="utf-8") + "\n".join(extra), encoding="utf-8")

    write_run_manifest(
        output_root,
        data_inputs=[one_m, Path(nq_state_root) / "states" / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3" / "unit_trades.csv"],
        output_paths=[output_root / "summary.csv", output_root / "INDEX.md", sync_path, state_root / "fills.csv"],
        strategy_config={
            "strategy_id": STRATEGY_ID,
            "strategy_type": "v2b_nq_lead_nas100",
            "t_max_seconds": t_max_seconds,
            "delta_early_seconds": delta_early_seconds,
            "sizing": "S_1_1_1",
            "point_value": POINT_VALUE,
            "dollar_scale": DOLLAR_SCALE,
            "tick_size": TICK,
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT},
        causality_mode="nq_lead_sync",
        extra={"driver": "nq_lead_nas100_prior_opposed_replay", "sessions": len(sessions)},
    )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NQ-lead NAS100 synced follower broker-like replay.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--nq-state-root", type=Path, default=DEFAULT_NQ_ROOT)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=None, help="Optional YYYY-MM-DD inclusive end.")
    parser.add_argument("--t-max-seconds", type=float, default=60.0)
    parser.add_argument("--delta-early-seconds", type=float, default=30.0)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--force-convert", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None
    result = run(
        output_root=args.output_root,
        nq_state_root=args.nq_state_root,
        force=not args.no_force,
        start=start,
        end=end,
        t_max_seconds=args.t_max_seconds,
        delta_early_seconds=args.delta_early_seconds,
        max_days=args.max_days,
        force_convert=args.force_convert,
    )
    print(
        "Wrote %s (Net=$%.2f entered=%d skipped=%d)"
        % (
            args.output_root / "INDEX.md",
            result.net_usd,
            result.prior_opposite_entries,
            result.causality_violations,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
