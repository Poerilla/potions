"""NQ-lead NAS100 synced follower — broker-like replay.

Uses existing NQ prior-opposed campaign entries as the lead signal. NAS100 only
enters inside a tight sync window with mapped OR structure checks, then manages
local CFD ``S_1_1_1`` exits. Standalone NQ / NAS100 prior-opposed paths are
untouched.
"""

from __future__ import annotations

import argparse
import csv
import io
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
from .nq_lead_nas100_sync import (
    attach_mapped_or,
    build_coupled_nq_stream,
    campaigns_for_json,
    load_nq_lead_campaigns,
    map_campaign_at_reveal,
)
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
COUPLED_NQ_ROOT = REPO / "live" / "state" / "nq_v2b_prior_opposed_causal_proxies" / "resting_limit"
COUPLED_OUTPUT = REPO / "live" / "state" / "nas100_v2b_nq_lead_coupled_resting_limit"
COUPLED_STRATEGY_ID = "nas100_v2b_nq_lead_coupled_S_1_1_1"
DSR_TRIAL_ID = "TRL-2026-00203"


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
        "available_at_ts",
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
    causality_violations: Optional[int] = None,
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
        causality_violations=skipped if causality_violations is None else int(causality_violations),
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


def _ny_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/New_York")
    else:
        ts = ts.tz_convert("America/New_York")
    return ts


def coupled_lookahead_rows(sync_path: Path, events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Entries that printed on or before the NQ bar-complete timestamp."""

    by_id = {str(ev["campaign_id"]): ev for ev in events if ev.get("kind") == "campaign"}
    bad: List[Dict[str, str]] = []
    if not sync_path.exists():
        return bad
    with sync_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("state") != "entered":
                continue
            camp = by_id.get(str(row.get("campaign_id") or ""))
            if camp is None:
                bad.append({"campaign_id": row.get("campaign_id") or "", "violation": "missing_campaign"})
                continue
            if _ny_ts(row["t_nas"]) <= _ny_ts(camp["available_at_ts"]):
                bad.append(
                    {
                        "campaign_id": str(row.get("campaign_id") or ""),
                        "t_nas": str(row.get("t_nas") or ""),
                        "available_at_ts": str(camp["available_at_ts"]),
                        "violation": "entry_not_after_nq_bar_complete",
                    }
                )
    return bad


def _dsr_table(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    preface: List[str] = []
    idx = 0
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].startswith("#")):
        preface.append(lines[idx])
        idx += 1
    body = "\n".join(lines[idx:]) + ("\n" if lines[idx:] else "")
    reader = csv.DictReader(body.splitlines())
    return preface, list(reader.fieldnames or []), list(reader)


def _append_dsr_running(*, hub: Path, start: date, end: Optional[date]) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    if path.exists() and DSR_TRIAL_ID in path.read_text(encoding="utf-8"):
        return
    row = {
        "trial_id": DSR_TRIAL_ID,
        "entry_date": "2026-10-03",
        "analyst": "cursor",
        "trial_class": "CAUSALITY_AUDIT",
        "trial_subclass": "nas100_nq_lead_coupled_resting_limit",
        "parent_trial_id": "",
        "is_independent": "TRUE",
        "market": "NAS100",
        "replay_window_start": start.isoformat(),
        "replay_window_end": end.isoformat() if end else "",
        "replay_type": "FULL_HISTORY",
        "is_oos": "FALSE",
        "training_window_start": "",
        "training_window_end": "",
        "parameters_json": json.dumps(
            {
                "gate": "resting_limit_hour_complete",
                "stream": "coupled_bar_complete",
                "preload_exits": False,
                "hub": str(hub),
            },
            sort_keys=True,
        ),
        "fixed_parameters_ref": "live/nq_lead_nas100_prior_opposed_replay.py",
        "num_params_varied": "0",
        "sharpe_ratio": "",
        "sortino_ratio": "",
        "cagr_pct": "",
        "calmar_ratio": "",
        "max_drawdown_pct": "",
        "trade_count": "",
        "pf": "",
        "net_pnl": "",
        "qqq_correlation": "",
        "qqq_downside_capture": "",
        "counts_toward_dsr": "TRUE",
        "counts_toward_permutation_test": "FALSE",
        "dsr_weight": "1.00",
        "dsr_exclusion_reason": "",
        "status": "RUNNING",
        "superseded_by": "",
        "run_hash": "",
        "notes": "Logged before peek. Coupled NQ stream, hour-complete resting-limit, no preloaded exits.",
        "disclosure_review": "FALSE",
    }
    if path.exists() and path.stat().st_size > 0:
        _preface, header, _rows = _dsr_table(path)
        ordered = {key: row.get(key, "") for key in header}
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
            writer.writerow(ordered)
        return
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)


def _finish_dsr(result: Result, violations: int) -> None:
    """Update only this trial's RUNNING line. Do not rewrite the rest of the ledger."""

    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    if not path.exists():
        return
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    header = None
    header_idx = None
    for idx, line in enumerate(raw_lines):
        if line.startswith("trial_id,"):
            header = next(csv.reader([line]))
            header_idx = idx
            break
    if not header or header_idx is None:
        return
    notes = (
        "Coupled resting-limit stream. net=%.2f stress=%.2f N/S=%.2f trades=%d violations=%d"
        % (result.net_usd, result.stress_dd_usd, result.net_stress, result.trades, violations)
    )
    changed = False
    for idx in range(header_idx + 1, len(raw_lines)):
        if not raw_lines[idx].startswith(DSR_TRIAL_ID + ","):
            continue
        parsed = next(csv.reader([raw_lines[idx]]))
        row = {key: (parsed[i] if i < len(parsed) else "") for i, key in enumerate(header)}
        if row.get("status") != "RUNNING":
            continue
        row["status"] = "COMPLETE"
        row["trade_count"] = str(result.trades)
        row["pf"] = "" if math.isinf(result.profit_factor) else "%.6f" % result.profit_factor
        row["net_pnl"] = "%.2f" % result.net_usd
        row["notes"] = notes
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=header, lineterminator="", extrasaction="ignore")
        writer.writerow(row)
        raw_lines[idx] = buf.getvalue()
        changed = True
    if changed:
        path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")


def run_coupled(
    *,
    output_root: Path,
    nq_state_root: Path,
    force: bool = True,
    start: date = DEFAULT_START,
    end: Optional[date] = None,
    t_max_seconds: float = 60.0,
    max_days: Optional[int] = None,
    force_convert: bool = False,
    email: bool = False,
    record_trial: Optional[bool] = None,
) -> Result:
    """Replay NAS100 against a live NQ event stream.

    The strategy config starts with an empty campaign book. Each NQ campaign
    is ingested only once its entry bar is complete. Exit times are ingested
    only once those exit bars are complete.
    """

    from .run_ledger import begin_run, complete_run, fail_run

    _ensure_meta()
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    full_history = max_days is None
    if record_trial is None:
        record_trial = full_history
    run_id = ""
    if record_trial:
        _append_dsr_running(hub=output_root, start=start, end=end)
    run_id = begin_run(
        run_class="broker_like",
        variant_slug="nas100_nq_lead_coupled_resting_limit",
        instrument=INSTRUMENT,
        hub_path=output_root,
        dsr_trial_id=DSR_TRIAL_ID if record_trial else "",
        notes="coupled hour-complete resting-limit stream; exits not preloaded",
        meta={
            "nq_state_root": str(nq_state_root),
            "t_max_seconds": t_max_seconds,
            "max_days": max_days,
            "gate": "resting_limit_hour_complete",
        },
    )
    try:
        result, violations, skipped = _run_coupled_body(
            output_root=output_root,
            nq_state_root=Path(nq_state_root),
            force=force,
            start=start,
            end=end,
            t_max_seconds=t_max_seconds,
            max_days=max_days,
            force_convert=force_convert,
        )
    except Exception as exc:
        fail_run(run_id, notes="coupled stream crashed: %s" % exc)
        if email:
            _email_coupled(output_root, None, crashed=str(exc))
        raise
    complete_run(
        run_id,
        net_usd=result.net_usd,
        stress_dd_usd=result.stress_dd_usd,
        close_mtm_dd_usd=result.closed_dd_usd,
        ns=result.net_stress,
        trades=result.trades,
        units=result.units,
        replay_start=start.isoformat(),
        replay_end=end.isoformat() if end else "",
        hub_path=output_root,
        notes="violations=%d skipped=%d" % (violations, skipped),
    )
    if record_trial:
        _finish_dsr(result, violations)
    if email:
        _email_coupled(output_root, result, violations=violations, skipped=skipped)
    return result


def _email_coupled(
    output_root: Path,
    result: Optional[Result],
    *,
    violations: int = 0,
    skipped: int = 0,
    crashed: str = "",
) -> None:
    from .notify_email import send_email

    if crashed:
        subject = "potions: NAS100 NQ-lead coupled stream crashed"
        body = "Hub: %s\nCrash: %s\n" % (output_root, crashed)
    else:
        assert result is not None
        stance = "causal stream clean" if violations == 0 else "REJECT — lookahead rows"
        subject = "potions: NAS100 NQ-lead coupled stream complete"
        body = "\n".join(
            [
                "Hub: %s" % output_root,
                "Book: NQ resting-limit hour-complete (not left-label).",
                "Stream: campaign emitted after the NQ entry bar completes; exit times are not preloaded.",
                "Trades: %d" % result.trades,
                "Net: $%.2f" % result.net_usd,
                "Stress DD: $%.2f" % result.stress_dd_usd,
                "Net/Stress: %.2f" % result.net_stress,
                "Entered: %d" % result.prior_opposite_entries,
                "Skipped: %d" % skipped,
                "Lookahead violations: %d" % violations,
                "Stance: %s. Research only — not a demo promote." % stance,
                "",
            ]
        )
    email_path = output_root / "EMAIL.txt"
    email_path.write_text(body, encoding="utf-8")
    send_email(subject=subject, body=body)


def _run_coupled_body(
    *,
    output_root: Path,
    nq_state_root: Path,
    force: bool,
    start: date,
    end: Optional[date],
    t_max_seconds: float,
    max_days: Optional[int],
    force_convert: bool,
) -> tuple:
    one_m, _daily = ensure_nas100_platform_files(REPO, force=force_convert)
    print("Building coupled NQ stream from %s ..." % nq_state_root, flush=True)
    events = build_coupled_nq_stream(nq_state_root, start=start, end=end)
    n_campaigns = sum(1 for ev in events if ev["kind"] == "campaign")
    n_miles = sum(1 for ev in events if ev["kind"] == "milestone")
    print("  %d campaigns, %d milestones (exits not on the campaign rows)" % (n_campaigns, n_miles), flush=True)
    for ev in events:
        if ev["kind"] == "campaign" and any(k in ev for k in ("t_nq_tp1", "t_nq_stop", "t_nq_eod")):
            raise RuntimeError("coupled campaign preloaded an exit time")

    print("Loading NAS100 1m bars ...", flush=True)
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    sessions = sorted({date.fromisoformat(ev["session"]) for ev in events if ev["kind"] == "campaign"})
    sessions = [day for day in sessions if day in gby and day >= start]
    if end is not None:
        sessions = [day for day in sessions if day <= end]
    if max_days is not None:
        sessions = sessions[:max_days]
    print("  replay sessions: %d" % len(sessions), flush=True)

    state_root = output_root / "states" / COUPLED_STRATEGY_ID
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=COUPLED_STRATEGY_ID,
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
                "delta_early_seconds": 0,
                "coupled_stream": True,
                "nq_lead_campaigns": {},
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
    plugin = engine.manager.plugins[COUPLED_STRATEGY_ID]

    cursor = 0
    prev_close: Optional[float] = None
    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(sessions, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            if pd.isna(row.get("close")):
                continue
            ts_s = pd.Timestamp(ts).isoformat()
            bar_dt = _ny_ts(ts)
            while cursor < len(events) and _ny_ts(events[cursor]["available_at_ts"]) < bar_dt:
                ev = events[cursor]
                if ev["kind"] == "campaign":
                    ev = map_campaign_at_reveal(ev, prev_close)
                plugin.ingest_coupled_event(ev)
                cursor += 1
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
            prev_close = float(bar.close)
        if idx % 100 == 0:
            print("  NAS100 coupled %d/%d sessions" % (idx, len(sessions)), flush=True)
    store.flush_tables()

    sync_path = _dump_sync_audit(state_root, output_root)
    bad = coupled_lookahead_rows(sync_path, events)
    viol_path = output_root / "coupled_causality.csv"
    with viol_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["campaign_id", "t_nas", "available_at_ts", "violation"],
        )
        writer.writeheader()
        for row in bad:
            writer.writerow(row)

    skipped = 0
    if sync_path.exists():
        with sync_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("state") == "skipped":
                    skipped += 1

    result = _summarize(
        COUPLED_STRATEGY_ID,
        state_root,
        audit_bars,
        regime_days=len(sessions),
        start_date=start,
        sync_audit_path=sync_path,
        causality_violations=len(bad),
    )
    write_report(output_root, result, gate_mode="nq_lead_coupled_resting_limit")
    index = output_root / "INDEX.md"
    extra = [
        "",
        "## Coupled NQ stream",
        "",
        "- Lead book: `%s` (hour-complete resting-limit, not the left-label fill-stamp book)" % nq_state_root,
        "- A campaign is ingested only after its NQ entry bar is complete (`available_at = fill bar + 1m`).",
        "- The NAS decision bar must be **strictly after** that timestamp.",
        "- TP1 / stop / EOD are separate milestone events. They are not stored on the campaign at entry time.",
        "- Mapped OR uses the prior completed NAS close at reveal, not the NQ entry minute.",
        "- Sync ceiling after bar-complete: **%.0fs**. Early window forced to **0s**." % t_max_seconds,
        "- Entered campaigns: **%d**" % result.prior_opposite_entries,
        "- Skipped campaigns: **%d**" % skipped,
        "- Lookahead violations (entry on or before NQ bar complete): **%d**" % len(bad),
        "",
        "Files: `summary.csv`, `sync_audit.csv`, `coupled_causality.csv`, `states/%s/`" % COUPLED_STRATEGY_ID,
        "",
    ]
    if index.exists():
        index.write_text(index.read_text(encoding="utf-8") + "\n".join(extra), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[
            one_m,
            nq_state_root / "states" / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3" / "unit_trades.csv",
        ],
        output_paths=[output_root / "summary.csv", output_root / "INDEX.md", sync_path, viol_path],
        strategy_config={
            "strategy_id": COUPLED_STRATEGY_ID,
            "strategy_type": "v2b_nq_lead_nas100",
            "coupled_stream": True,
            "gate": "resting_limit_hour_complete",
            "preload_exits": False,
            "t_max_seconds": t_max_seconds,
            "delta_early_seconds": 0,
            "sizing": "S_1_1_1",
            "point_value": POINT_VALUE,
            "dollar_scale": DOLLAR_SCALE,
            "tick_size": TICK,
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT},
        causality_mode="nq_lead_coupled_resting_limit",
        extra={"driver": "nq_lead_nas100_prior_opposed_replay", "sessions": len(sessions)},
    )
    return result, len(bad), skipped


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NQ-lead NAS100 synced follower broker-like replay.")
    parser.add_argument(
        "--coupled",
        action="store_true",
        help="Stream hour-complete resting-limit NQ events after each bar completes. Does not preload exits.",
    )
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--nq-state-root", type=Path, default=None)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=None, help="Optional YYYY-MM-DD inclusive end.")
    parser.add_argument("--t-max-seconds", type=float, default=60.0)
    parser.add_argument("--delta-early-seconds", type=float, default=30.0)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--force-convert", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument("--email", action="store_true")
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None
    if args.coupled:
        result = run_coupled(
            output_root=args.output_root or COUPLED_OUTPUT,
            nq_state_root=args.nq_state_root or COUPLED_NQ_ROOT,
            force=not args.no_force,
            start=start,
            end=end,
            t_max_seconds=args.t_max_seconds,
            max_days=args.max_days,
            force_convert=args.force_convert,
            email=args.email,
        )
        print(
            "Wrote %s (Net=$%.2f entered=%d violations=%d)"
            % (
                (args.output_root or COUPLED_OUTPUT) / "INDEX.md",
                result.net_usd,
                result.prior_opposite_entries,
                result.causality_violations,
            ),
            flush=True,
        )
        return 0
    legacy_output = args.output_root or DEFAULT_OUTPUT
    result = run(
        output_root=legacy_output,
        nq_state_root=args.nq_state_root or DEFAULT_NQ_ROOT,
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
            legacy_output / "INDEX.md",
            result.net_usd,
            result.prior_opposite_entries,
            result.causality_violations,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
