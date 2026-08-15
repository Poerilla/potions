"""Curated OANDA fault-day replay harness.

Loads real demo bar slices + frozen book snapshots from
``live/tests/fixtures/oanda_faults/cases/`` and verifies containment hardenings
fire the same way they should have on the incident day.

This is deliberately offline (no live OANDA calls): bars come from practice
demo stores; books are reconstructed incident fixtures.

Usage::

    python -m potions.live.demo.oanda_fault_replay
    python -m potions.live.demo.oanda_fault_replay --case 2026-08-13_stop_only_v2b
    python -m potions.live.demo.oanda_fault_replay --also-plugin-replay
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..models import Bar, utc_now_iso
from ..oanda import OandaBroker, OandaConfig
from ..store import FlatFileStore
from ..supervisor import ENTRY_FROZEN, FLAT_FOR_DAY, RuntimeSupervisor
from .oanda_daemon_reconcile import (
    DaemonContainmentController,
    detect_foreign_bleed,
    evaluate_fixture_book,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "oanda_faults" / "cases"


@dataclass
class FaultBookReplayResult:
    case: str
    book: str
    instrument: str
    strategy_id: str
    as_of: str
    bar_count: int
    bars_path: str
    detector_classification: str
    detector_action: str
    containment_classification: str
    containment_actions: List[str]
    supervisor_mode: str
    expected_classification: str
    expected_action: str
    ok: bool
    plugin_replay: Optional[Dict[str, Any]] = None
    live_fill_compare: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class _OfflineClient:
    """Minimal client so OandaBroker never hits the network during fault replay."""

    def __init__(self, pending: Optional[List[Dict[str, Any]]] = None, trades: Optional[List[Dict[str, Any]]] = None):
        self.pending = list(pending or [])
        self.trades = list(trades or [])
        self.cancelled: List[str] = []
        self.closed: List[Any] = []

    def account_details(self):
        return {
            "lastTransactionID": "1",
            "account": {
                "lastTransactionID": "1",
                "orders": list(self.pending),
                "trades": list(self.trades),
                "positions": [],
            },
        }

    def cancel_order(self, order_id):
        self.cancelled.append(str(order_id))
        self.pending = [o for o in self.pending if str(o.get("id")) != str(order_id)]
        return {"orderCancelTransaction": {"orderID": str(order_id)}}

    def close_position(self, instrument, **kwargs):
        self.closed.append((instrument, kwargs))
        return {"lastTransactionID": "2"}


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _compare_live_fills(
    book_dir: Path,
    *,
    plugin_info: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Compare frozen live demo fills for the incident day vs plugin smoke fills.

    Used to document missed/orphan fill classes against the same OANDA bar day.
    Does not gate PASS/FAIL unless expected.json sets require_live_fill_parity.
    """
    live_path = book_dir / "live_fills_that_day.csv"
    if not live_path.exists():
        live_path = book_dir / "fills.csv"
    live_rows = _read_csv(live_path)
    if not live_rows and plugin_info is None:
        return None
    live_entries = [
        r
        for r in live_rows
        if "eod" not in str(r.get("reason") or "").lower()
        and "flat" not in str(r.get("reason") or "").lower()
    ]
    plugin_fills = int((plugin_info or {}).get("fills") or 0)
    return {
        "live_fill_rows": len(live_rows),
        "live_non_eod_fills": len(live_entries),
        "live_reasons": sorted({str(r.get("reason") or "") for r in live_rows if r.get("reason")}),
        "plugin_fills": plugin_fills,
        "source": live_path.name,
    }


def _seed_book(store: FlatFileStore, book_dir: Path) -> None:
    for row in _read_csv(book_dir / "positions.csv"):
        store.upsert_row("positions", "position_id", row)
    for row in _read_csv(book_dir / "orders.csv"):
        store.upsert_row("orders", "broker_order_id", row)
    for row in _read_csv(book_dir / "fills.csv"):
        if "fill_id" in row:
            store.upsert_row("fills", "fill_id", row)


def _load_bars(book_dir: Path, instrument: str) -> List[Dict[str, str]]:
    bars_dir = book_dir / "bars"
    if not bars_dir.exists():
        return []
    preferred = bars_dir / ("%s_1m.csv" % instrument.upper())
    paths = [preferred] if preferred.exists() else sorted(bars_dir.glob("*.csv"))
    rows: List[Dict[str, str]] = []
    for path in paths:
        rows.extend(_read_csv(path))
    rows.sort(key=lambda r: str(r.get("ts") or ""))
    return rows


def _normalize_as_of(as_of: str) -> str:
    """Convert as_of to a UTC Z string for ISO lexicographic compare with bar ts."""
    raw = str(as_of or "").strip()
    if not raw:
        return ""
    if raw.endswith("Z"):
        return raw
    try:
        from datetime import datetime, timezone

        if raw.endswith(("-04:00", "-05:00")) or "+" in raw[10:]:
            dt = datetime.fromisoformat(raw)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    return raw


def _bars_up_to(rows: Sequence[Dict[str, str]], as_of: str) -> List[Dict[str, str]]:
    """Keep bars with ts <= as_of (ISO string compare after normalizing offsets)."""
    as_of_s = _normalize_as_of(as_of)
    if not as_of_s:
        return list(rows)
    out = [r for r in rows if str(r.get("ts") or "") <= as_of_s]
    return out if out else list(rows)


def _persist_bars(store: FlatFileStore, rows: Sequence[Dict[str, str]], *, instrument: str) -> int:
    """Write fixture bars under ``state/bars/`` the same way OANDA demos do."""
    if not rows:
        return 0
    bars_dir = store.root / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    path = bars_dir / ("%s_1m.csv" % instrument.upper())
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def _maybe_plugin_replay(
    *,
    store: FlatFileStore,
    instrument: str,
    strategy_id: str,
    strategy_type: str,
    bar_rows: Sequence[Dict[str, str]],
) -> Dict[str, Any]:
    """Lightweight PaperBroker replay of fixture bars (plugin smoke, not PnL truth)."""
    try:
        from ..broker import PaperBroker
        from ..engine import Engine, bars_from_csv
        from ..models import StrategyInstance, as_row
    except Exception as exc:  # pragma: no cover
        return {"status": "skip", "reason": "import_failed:%s" % exc}

    # Ensure a strategy instance exists so Engine can load the plugin.
    existing = [r for r in store.read_table("strategy_instances") if r.get("strategy_id") == strategy_id]
    if not existing:
        store.upsert_row(
            "strategy_instances",
            "strategy_id",
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type=strategy_type or "v2b_scaleout",
                    version="fault_replay",
                    instrument=instrument,
                    broker_instrument=instrument,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=8,
                    max_open_orders=64,
                    config_json=json.dumps({"fault_replay": True, "paper_only": True}, sort_keys=True),
                )
            ),
        )

    bars_path = store.root / "bars" / ("%s_1m.csv" % instrument.upper())
    if bars_path.exists():
        bars = bars_from_csv(bars_path, instrument, "1m", source="oanda_fault_fixture")
    else:
        bars = []
        for row in bar_rows:
            try:
                bars.append(
                    Bar(
                        instrument=str(row.get("instrument") or instrument),
                        timeframe=str(row.get("timeframe") or "1m"),
                        ts=str(row.get("ts") or ""),
                        open=float(row.get("open") or 0.0),
                        high=float(row.get("high") or 0.0),
                        low=float(row.get("low") or 0.0),
                        close=float(row.get("close") or 0.0),
                        volume=float(row.get("volume") or 0.0),
                        complete=str(row.get("complete") or "true").lower() in {"1", "true", "yes"},
                        source=str(row.get("source") or "oanda_fault_fixture"),
                    )
                )
            except Exception:
                continue

    broker = PaperBroker(store)
    engine = Engine(
        store=store,
        broker=broker,
        persist_bars=False,
        persist_health=False,
        emit_order_alerts=False,
        broker_log_events=False,
        slippage_ticks=0.0,
    )
    played = 0
    errors = 0
    for bar in bars:
        if not bar.complete or not bar.ts:
            continue
        try:
            engine.process_bar(bar)
            played += 1
        except Exception:
            errors += 1
    fills = store.read_table("fills")
    return {
        "status": "ok",
        "bars_played": played,
        "errors": errors,
        "fills": len(fills),
        "open_positions": len([p for p in store.read_table("positions") if float(p.get("quantity") or 0) != 0]),
    }


def replay_fault_book(
    book_dir: Path,
    *,
    case_name: str,
    mode: str = "live",
    also_plugin_replay: bool = False,
) -> FaultBookReplayResult:
    expected = json.loads((book_dir / "expected.json").read_text(encoding="utf-8"))
    meta_path = book_dir.parent / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    instrument = str(expected["instrument"]).upper()
    strategy_id = str(expected["strategy_id"])
    strategy_type = str(expected.get("strategy_type") or "v2b_scaleout")
    entry_qty = float(expected.get("entry_qty") or 3.0)
    as_of = str(meta.get("as_of") or expected.get("as_of") or "")

    all_bars = _load_bars(book_dir, instrument)
    bars = _bars_up_to(all_bars, as_of) if as_of else list(all_bars)

    if expected.get("detector") == "foreign_bleed":
        detector = detect_foreign_bleed(
            _read_csv(book_dir / "positions.csv"),
            focus_instrument=instrument,
            strategy_id=strategy_id,
        )
    else:
        detector = evaluate_fixture_book(
            positions_csv=book_dir / "positions.csv",
            orders_csv=book_dir / "orders.csv",
            instrument=instrument,
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            entry_qty=entry_qty,
            broker_qty=expected.get("broker_qty"),
        )

    tmp = tempfile.TemporaryDirectory(prefix="oanda_fault_")
    try:
        store = FlatFileStore(Path(tmp.name))
        store.ensure()
        bar_count = _persist_bars(store, bars, instrument=instrument)

        plugin_info: Optional[Dict[str, Any]] = None
        if also_plugin_replay and bars:
            # Plugin replay on a *clean* clone of bars only (before fault book seed).
            plugin_tmp = tempfile.TemporaryDirectory(prefix="oanda_fault_plugin_")
            try:
                pstore = FlatFileStore(Path(plugin_tmp.name))
                pstore.ensure()
                _persist_bars(pstore, bars, instrument=instrument)
                plugin_info = _maybe_plugin_replay(
                    store=pstore,
                    instrument=instrument,
                    strategy_id=strategy_id,
                    strategy_type=strategy_type,
                    bar_rows=bars,
                )
            finally:
                plugin_tmp.cleanup()

        _seed_book(store, book_dir)

        # Broker qty for hard-mismatch cases: synthesize trades when expected provides broker_qty.
        trades: List[Dict[str, Any]] = []
        broker_qty = expected.get("broker_qty")
        if broker_qty is not None and abs(float(broker_qty)) > 1e-9:
            trades.append(
                {
                    "id": "fault_trade",
                    "instrument": "%s_USD" % instrument if instrument in {"NAS100", "SPX500", "US30"} else instrument,
                    "currentUnits": str(broker_qty),
                    "price": "1",
                }
            )

        config = OandaConfig(
            account_id="101-002-39860312-001",
            instrument_map={instrument: ("%s_USD" % instrument if instrument in {"NAS100", "SPX500", "US30"} else instrument)},
        )
        client = _OfflineClient(pending=[], trades=trades)
        supervisor = RuntimeSupervisor(store, provider="oanda")
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            supervisor=supervisor,
            authority_strategy_ids=[strategy_id],
            position_scope_instruments=[instrument],
        )
        if trades:
            broker._strategy_tag_for_open_trade = lambda trade_id: strategy_id  # type: ignore

        controller = DaemonContainmentController(
            store=store,
            broker=broker,
            supervisor=supervisor,
            instrument=instrument,
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            entry_qty=entry_qty,
            mode=mode,
            email_on_action=False,
            clock=lambda: 1_000_000.0,
        )

        exp_class = str(expected["classification"])
        # Stream-hung missed-entry cases: inject stale last-activity age.
        if expected.get("detector") == "stream_stale" or exp_class == "stream_stale":
            age = float(expected.get("stream_age_s") or 400.0)
            controller._last_stream_at = float(controller._clock()) - age
            phase = "stream_watchdog"
            broker.client = None  # type: ignore
            result = controller.run_cycle(phase=phase, force=True)
        else:
            # Local-only watchdog unless we need account details for qty mismatch.
            phase = "hard_reconcile" if expected.get("classification") == "qty_mismatch" else "bracket_watchdog"
            if phase == "bracket_watchdog":
                broker.client = None  # type: ignore
            result = controller.run_cycle(phase=phase, force=True)

        inv = result.invariant
        classification = inv.classification if inv is not None else "none"
        exp_action = str(expected["recommended_action"])
        ok = classification == exp_class and (
            exp_action == "none"
            or any(
                (
                    exp_action == "freeze_entries" and supervisor.mode == ENTRY_FROZEN,
                    exp_action == "flat_for_day" and supervisor.mode == FLAT_FOR_DAY,
                    exp_action == "cancel_orphans" and any("orphan" in a for a in result.actions),
                    # shadow-style: action listed even if supervisor unchanged
                    exp_action in result.actions,
                    any(a.startswith(exp_action.split("_")[0]) for a in result.actions),
                )
            )
        )
        # Tighten: detector must also agree (stream_stale is controller-level; book detector stays ok/flat).
        if expected.get("detector") == "stream_stale" or exp_class == "stream_stale":
            ok = ok and detector.classification in {"ok", "stream_stale"}
        else:
            ok = ok and detector.classification == exp_class and detector.recommended_action == exp_action

        notes: List[str] = []
        if not bars:
            notes.append("no_bar_slice")
        if also_plugin_replay and plugin_info is None:
            notes.append("plugin_replay_skipped")

        live_cmp = _compare_live_fills(book_dir, plugin_info=plugin_info)

        return FaultBookReplayResult(
            case=case_name,
            book=book_dir.name,
            instrument=instrument,
            strategy_id=strategy_id,
            as_of=as_of,
            bar_count=bar_count,
            bars_path=str(book_dir / "bars") if (book_dir / "bars").exists() else "",
            detector_classification=detector.classification,
            detector_action=detector.recommended_action,
            containment_classification=classification,
            containment_actions=list(result.actions),
            supervisor_mode=str(supervisor.mode),
            expected_classification=exp_class,
            expected_action=exp_action,
            ok=bool(ok),
            plugin_replay=plugin_info,
            live_fill_compare=live_cmp,
            notes=notes,
        )
    finally:
        tmp.cleanup()


def iter_fault_books(case_filter: Optional[str] = None):
    if not FIXTURE_ROOT.exists():
        return
    for case_dir in sorted(p for p in FIXTURE_ROOT.iterdir() if p.is_dir()):
        if case_filter and case_dir.name != case_filter:
            continue
        for book_dir in sorted(p for p in case_dir.iterdir() if p.is_dir()):
            if not (book_dir / "expected.json").exists():
                continue
            yield case_dir.name, book_dir


def run_all(
    *,
    case: Optional[str] = None,
    mode: str = "live",
    also_plugin_replay: bool = False,
) -> List[FaultBookReplayResult]:
    return [
        replay_fault_book(book_dir, case_name=case_name, mode=mode, also_plugin_replay=also_plugin_replay)
        for case_name, book_dir in iter_fault_books(case)
    ]


def curate_case_from_demo(
    *,
    demo_root: Path,
    case_name: str,
    book_name: str,
    instrument: str,
    strategy_id: str,
    strategy_type: str,
    as_of: str,
    day: str,
    classification: str,
    recommended_action: str,
    entry_qty: float = 3.0,
    broker_qty: Optional[float] = None,
    dest_root: Optional[Path] = None,
) -> Path:
    """Freeze a live demo book's positions/orders + that day's bars into a new fixture case."""
    dest_root = dest_root or FIXTURE_ROOT
    book_dir = dest_root / case_name / book_name
    if book_dir.exists():
        shutil.rmtree(book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)

    state = demo_root / "state"
    for name in ("positions.csv", "orders.csv", "fills.csv"):
        src = state / name
        if src.exists():
            shutil.copy2(src, book_dir / name)

    bars_src = state / "bars"
    bars_dst = book_dir / "bars"
    bars_dst.mkdir(exist_ok=True)
    if bars_src.exists():
        for src in bars_src.glob("*.csv"):
            rows = []
            with src.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                fields = reader.fieldnames
                for row in reader:
                    if str(row.get("ts") or "").startswith(day):
                        rows.append(row)
            if not rows or not fields:
                continue
            with (bars_dst / src.name).open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)

    expected = {
        "instrument": instrument,
        "strategy_id": strategy_id,
        "strategy_type": strategy_type,
        "entry_qty": entry_qty,
        "classification": classification,
        "recommended_action": recommended_action,
        "as_of": as_of,
    }
    if broker_qty is not None:
        expected["broker_qty"] = broker_qty
    (book_dir / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")

    meta_path = dest_root / case_name / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(
            json.dumps(
                {
                    "incident": case_name,
                    "provenance": [str(demo_root)],
                    "as_of": as_of,
                    "expected": {"classification": classification, "recommended_action": recommended_action},
                    "curated_at": utc_now_iso(),
                    "note": "Frozen from live demo state + OANDA bar day slice.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return book_dir


def write_hub_report(
    results: Sequence[FaultBookReplayResult],
    *,
    hub: Path,
    mode: str,
    also_plugin_replay: bool,
) -> None:
    """Write HARNESS_OUT.txt / SUMMARY.md / EMAIL.txt under a state hub."""
    hub = Path(hub)
    hub.mkdir(parents=True, exist_ok=True)
    failed = [r for r in results if not r.ok]
    lines = []
    for r in results:
        flag = "PASS" if r.ok else "FAIL"
        plugin = ""
        if also_plugin_replay:
            plugin = " plugin=%s" % ((r.plugin_replay or {}).get("status") or "None")
        live = ""
        if r.live_fill_compare:
            live = " live_fills=%s/%s" % (
                r.live_fill_compare.get("live_non_eod_fills"),
                r.live_fill_compare.get("live_fill_rows"),
            )
        lines.append(
            "%s %s/%s class=%s action=%s supervisor=%s bars=%d%s%s"
            % (
                flag,
                r.case,
                r.book,
                r.containment_classification,
                ",".join(r.containment_actions) or "-",
                r.supervisor_mode,
                r.bar_count,
                plugin,
                live,
            )
        )
    lines.append("summary: %d/%d pass" % (len(results) - len(failed), len(results)))
    (hub / "HARNESS_OUT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = [
        "# OANDA curated fault replay",
        "",
        "Generated: %s" % utc_now_iso(),
        "Mode: `%s` (containment enforce)" % mode,
        "Fixtures: `live/tests/fixtures/oanda_faults/cases/`",
        "Harness: `python -m potions.live.demo.oanda_fault_replay`",
        "",
        "## Results (%d/%d pass)" % (len(results) - len(failed), len(results)),
        "",
        "| Case | Book | Class | Action | Supervisor | Bars | Plugin | Live fills |",
        "|------|------|-------|--------|------------|------|--------|------------|",
    ]
    for r in results:
        summary.append(
            "| %s | %s | %s | %s | %s | %d | %s | %s |"
            % (
                r.case,
                r.book,
                r.containment_classification,
                ",".join(r.containment_actions) or "-",
                r.supervisor_mode,
                r.bar_count,
                (r.plugin_replay or {}).get("status") if r.plugin_replay else "-",
                (
                    "%s non-eod / %s total"
                    % (
                        (r.live_fill_compare or {}).get("live_non_eod_fills"),
                        (r.live_fill_compare or {}).get("live_fill_rows"),
                    )
                    if r.live_fill_compare
                    else "-"
                ),
            )
        )
    summary.extend(
        [
            "",
            "## Purpose",
            "",
            "Offline regression of real Aug 13–14 OANDA practice incidents",
            "(stop-only, orphan protective, stream-hung missed entry, open-without-brackets,",
            "foreign bleed, qty mismatch) against daemon containment hardenings.",
            "",
            "Default live daemons stay on `POTIONS_OANDA_CONTAINMENT=shadow` until",
            "≥1 week of clean practice shadow.",
            "",
        ]
    )
    (hub / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")

    email = [
        "potions: OANDA containment + curated fault env",
        "",
        "Hub: %s/" % hub.as_posix().split("/potions/")[-1] if "/potions/" in hub.as_posix() else str(hub),
        "Fixtures: live/tests/fixtures/oanda_faults/",
        "Harness: python -m potions.live.demo.oanda_fault_replay --also-plugin-replay",
        "",
        "Fault harness (%s mode): %d/%d PASS" % (mode, len(results) - len(failed), len(results)),
    ]
    for r in results:
        email.append(
            "- %s/%s → %s (%s)"
            % (r.case, r.book, r.containment_classification, ",".join(r.containment_actions) or "none")
        )
    email.extend(
        [
            "",
            "Wired runners: v2b / Monday OR / ST+PMC / asia-range / London prior-opposed",
            "Env: POTIONS_OANDA_CONTAINMENT=shadow (keep until ≥1 week practice shadow)",
            "",
            "Stance: promote shadow on practice daemons; do not enable live flatten yet.",
            "",
        ]
    )
    (hub / "EMAIL.txt").write_text("\n".join(email), encoding="utf-8")
    (hub / "results.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now_iso(),
                "mode": mode,
                "n": len(results),
                "n_fail": len(failed),
                "results": [r.as_dict() for r in results],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay curated OANDA fault-day fixtures through containment.")
    parser.add_argument("--case", default=None, help="Only this case directory name")
    parser.add_argument("--mode", default="live", choices=("live", "shadow"))
    parser.add_argument("--also-plugin-replay", action="store_true", help="Also smoke PaperBroker plugin on bar slice")
    parser.add_argument("--json-out", default="", help="Optional path for JSON report")
    parser.add_argument(
        "--hub",
        default="",
        help="Optional hub dir (writes HARNESS_OUT.txt / SUMMARY.md / EMAIL.txt / results.json)",
    )
    parser.add_argument("--email", action="store_true", help="Send EMAIL.txt via Resend when --hub is set")
    args = parser.parse_args(list(argv) if argv is not None else None)

    results = run_all(case=args.case, mode=args.mode, also_plugin_replay=args.also_plugin_replay)
    failed = [r for r in results if not r.ok]
    for r in results:
        flag = "PASS" if r.ok else "FAIL"
        print(
            "%s %s/%s class=%s action=%s supervisor=%s bars=%d %s"
            % (
                flag,
                r.case,
                r.book,
                r.containment_classification,
                ",".join(r.containment_actions) or "-",
                r.supervisor_mode,
                r.bar_count,
                ("plugin=%s" % (r.plugin_replay or {}).get("status")) if args.also_plugin_replay else "",
            )
        )
    payload = {
        "generated_at": utc_now_iso(),
        "n": len(results),
        "n_fail": len(failed),
        "results": [r.as_dict() for r in results],
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % out)
    if args.hub:
        hub = Path(args.hub)
        write_hub_report(results, hub=hub, mode=args.mode, also_plugin_replay=args.also_plugin_replay)
        print("wrote hub %s" % hub)
        if args.email:
            try:
                from ..notify_email import send_email

                body = (hub / "EMAIL.txt").read_text(encoding="utf-8")
                send_email(subject="potions: OANDA curated fault replay", body=body)
                print("emailed completion summary")
            except Exception as exc:
                print("WARN email failed: %s" % exc)
    print("summary: %d/%d pass" % (len(results) - len(failed), len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
