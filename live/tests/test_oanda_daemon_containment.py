"""Containment + curated OANDA fault-fixture regressions."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from potions.live.demo.oanda_daemon_reconcile import (
    DaemonContainmentController,
    detect_foreign_bleed,
    evaluate_bracket_invariant,
    evaluate_fixture_book,
    maybe_clear_flat_for_day_on_session_roll,
    ny_session_date,
    read_flat_for_day,
    write_flat_for_day,
    containment_email_mode,
    ny_past_containment_email_eod,
)
from potions.live.models import OrderIntent, utc_now_iso
from potions.live.oanda import OandaBroker, OandaConfig, OandaRoutingBlocked
from potions.live.store import FlatFileStore
from potions.live.supervisor import ENTRY_FROZEN, FLAT_FOR_DAY, RUNNING, RuntimeSupervisor

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "oanda_faults" / "cases"


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


class _FakeClient:
    def __init__(self, pending=None, trades=None):
        self.pending = list(pending or [])
        self.trades = list(trades or [])
        self.cancelled = []
        self.closed = []

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


def _iter_fixture_books():
    if not FIXTURES.exists():
        return
    for case_dir in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
        for book_dir in sorted(p for p in case_dir.iterdir() if p.is_dir()):
            expected_path = book_dir / "expected.json"
            if not expected_path.exists():
                continue
            yield case_dir.name, book_dir, json.loads(expected_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case_name,book_dir,expected", list(_iter_fixture_books()))
def test_fixture_detectors_match_expected(case_name, book_dir, expected):
    if expected.get("detector") == "stream_stale" or expected.get("classification") == "stream_stale":
        pytest.skip("stream_stale is controller-level; covered by fault-day replay + dedicated test")
    if expected.get("detector") == "foreign_bleed":
        import csv

        with (book_dir / "positions.csv").open(newline="", encoding="utf-8") as fh:
            positions = list(csv.DictReader(fh))
        result = detect_foreign_bleed(
            positions,
            focus_instrument=expected["instrument"],
            strategy_id=expected["strategy_id"],
        )
    else:
        result = evaluate_fixture_book(
            positions_csv=book_dir / "positions.csv",
            orders_csv=book_dir / "orders.csv",
            instrument=expected["instrument"],
            strategy_id=expected["strategy_id"],
            strategy_type=expected.get("strategy_type") or "v2b_scaleout",
            entry_qty=float(expected.get("entry_qty") or 3),
            broker_qty=expected.get("broker_qty"),
        )
    assert result.classification == expected["classification"], case_name
    assert result.recommended_action == expected["recommended_action"], case_name
    if expected["classification"] in {"ok", "armed_entry"}:
        assert result.ok
    else:
        assert not result.ok


def test_supervisor_flat_for_day_survives_mark_reconciled():
    tmp, store = make_store()
    try:
        supervisor = RuntimeSupervisor(store, provider="oanda")
        supervisor.mark_flat_for_day("qty_mismatch", {"x": 1})
        assert supervisor.mode == FLAT_FOR_DAY
        supervisor.start_reconciliation("oanda_account_details")
        assert supervisor.mode == FLAT_FOR_DAY
        supervisor.mark_reconciled("oanda_account_details_reconciled")
        assert supervisor.mode == FLAT_FOR_DAY
        assert not supervisor.entries_allowed(OrderIntent.create(
            strategy_id="s",
            trade_id="t",
            instrument="NAS100",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=1.0,
            reason="entry",
            requires_verification=False,
        ))
        # Reduce-only still allowed.
        assert supervisor.entries_allowed(OrderIntent.create(
            strategy_id="s",
            trade_id="t",
            instrument="NAS100",
            account_mode="paper",
            side="sell",
            order_type="market",
            quantity=1,
            reason="flat",
            requires_verification=False,
            reduce_only=True,
        ))
    finally:
        tmp.cleanup()


def test_flat_for_day_clears_on_session_roll():
    tmp, store = make_store()
    try:
        supervisor = RuntimeSupervisor(store, provider="oanda")
        write_flat_for_day(
            store,
            {
                "reason": "qty_mismatch",
                "session_date": "2020-01-01",
                "asof": utc_now_iso(),
            },
        )
        supervisor.mark_flat_for_day("qty_mismatch")
        cleared = maybe_clear_flat_for_day_on_session_roll(
            store, supervisor, session_date=ny_session_date()
        )
        assert cleared
        assert read_flat_for_day(store) is None
        assert supervisor.mode == RUNNING
    finally:
        tmp.cleanup()


def test_live_containment_freezes_on_stop_only_fixture():
    book = FIXTURES / "2026-08-13_stop_only_v2b" / "nas100"
    expected = json.loads((book / "expected.json").read_text(encoding="utf-8"))
    tmp, store = make_store()
    try:
        # Seed local mirror from fixture.
        import csv

        with (book / "positions.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                store.upsert_row("positions", "position_id", row)
        with (book / "orders.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                store.upsert_row("orders", "broker_order_id", row)
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        client = _FakeClient(pending=[], trades=[])
        supervisor = RuntimeSupervisor(store, provider="oanda")
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            supervisor=supervisor,
            authority_strategy_ids=[expected["strategy_id"]],
            position_scope_instruments=["NAS100"],
        )
        # Avoid network reconcile rewriting seeded rows: no trades → rewrite empties.
        # Run detector path via controller with phase that skips account when client returns empty —
        # seed positions already in broker cache from store load.
        controller = DaemonContainmentController(
            store=store,
            broker=broker,
            supervisor=supervisor,
            instrument="NAS100",
            strategy_id=expected["strategy_id"],
            strategy_type="v2b_scaleout",
            entry_qty=3,
            mode="live",
            email_on_action=False,
            clock=lambda: 1_000_000.0,
        )
        # Force local-only cycle (no account rewrite): monkeypatch client away for cycle body.
        broker.client = None
        result = controller.run_cycle(phase="bracket_watchdog", force=True)
        assert result.invariant is not None
        assert result.invariant.classification == "stop_only"
        assert supervisor.mode == ENTRY_FROZEN
        assert any(a.startswith("freeze") for a in result.actions)
        assert (store.root / "daemon_strategy_state.json").exists()
    finally:
        tmp.cleanup()


def test_live_containment_flattens_on_qty_mismatch():
    tmp, store = make_store()
    try:
        # Local long 3 vs broker short -3 (opposite side = hard mismatch).
        store.upsert_row(
            "positions",
            "position_id",
            {
                "position_id": "nas100_v2b_ungated_oanda|NAS100|paper",
                "strategy_id": "nas100_v2b_ungated_oanda",
                "instrument": "NAS100",
                "account_mode": "paper",
                "quantity": "3",
                "avg_price": "29000",
                "realized_pnl": "0",
                "updated_at": utc_now_iso(),
            },
        )
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        client = _FakeClient(
            pending=[],
            trades=[
                {
                    "id": "trade1",
                    "instrument": "NAS100_USD",
                    "currentUnits": "-3",
                    "price": "29000",
                }
            ],
        )
        supervisor = RuntimeSupervisor(store, provider="oanda")
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            supervisor=supervisor,
            authority_strategy_ids=["nas100_v2b_ungated_oanda"],
            position_scope_instruments=["NAS100"],
        )
        broker._strategy_tag_for_open_trade = lambda trade_id: "nas100_v2b_ungated_oanda"  # type: ignore
        controller = DaemonContainmentController(
            store=store,
            broker=broker,
            supervisor=supervisor,
            instrument="NAS100",
            strategy_id="nas100_v2b_ungated_oanda",
            strategy_type="v2b_scaleout",
            entry_qty=3,
            mode="live",
            email_on_action=False,
            clock=lambda: 1_000_000.0,
        )
        result = controller.run_cycle(phase="hard_reconcile", force=True)
        assert result.invariant is not None
        assert result.invariant.classification == "qty_mismatch"
        assert supervisor.mode == FLAT_FOR_DAY
        assert read_flat_for_day(store) is not None
        assert result.flat_for_day
    finally:
        tmp.cleanup()


def test_orphan_protective_sweep_cancels_remote_sl_when_flat():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        client = _FakeClient(
            pending=[
                {
                    "id": "9001",
                    "type": "STOP_LOSS",
                    "state": "PENDING",
                    "instrument": "NAS100_USD",
                    "tradeID": "dead",
                    "clientExtensions": {"tag": "nas100_v2b_ungated_oanda"},
                }
            ],
            trades=[],
        )
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            authority_strategy_ids=["nas100_v2b_ungated_oanda"],
            position_scope_instruments=["NAS100"],
        )
        n = broker.sweep_orphan_protectives_when_flat(
            strategy_id="nas100_v2b_ungated_oanda",
            instrument="NAS100",
            reason="unit_test",
        )
        assert n >= 1
        assert "9001" in client.cancelled
    finally:
        tmp.cleanup()


def test_shadow_mode_does_not_mutate_supervisor():
    book = FIXTURES / "2026-08-13_stop_only_v2b" / "nas100"
    expected = json.loads((book / "expected.json").read_text(encoding="utf-8"))
    tmp, store = make_store()
    try:
        import csv

        with (book / "positions.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                store.upsert_row("positions", "position_id", row)
        with (book / "orders.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                store.upsert_row("orders", "broker_order_id", row)
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        supervisor = RuntimeSupervisor(store, provider="oanda")
        broker = OandaBroker(
            store,
            config=config,
            client=None,
            supervisor=supervisor,
            authority_strategy_ids=[expected["strategy_id"]],
            position_scope_instruments=["NAS100"],
        )
        controller = DaemonContainmentController(
            store=store,
            broker=broker,
            supervisor=supervisor,
            instrument="NAS100",
            strategy_id=expected["strategy_id"],
            strategy_type="v2b_scaleout",
            entry_qty=3,
            mode="shadow",
            email_on_action=False,
        )
        result = controller.run_cycle(phase="bracket_watchdog", force=True)
        assert result.shadow
        assert supervisor.mode == RUNNING
        assert "shadow_would_freeze_entries" in result.actions
    finally:
        tmp.cleanup()


def test_stream_stale_freezes_and_reconnect_rearms():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        supervisor = RuntimeSupervisor(store, provider="oanda")
        broker = OandaBroker(
            store,
            config=config,
            client=_FakeClient(),
            supervisor=supervisor,
            authority_strategy_ids=["nas100_v2b_ungated_oanda"],
            position_scope_instruments=["NAS100"],
        )
        clock = {"t": 1_000_000.0}
        controller = DaemonContainmentController(
            store=store,
            broker=broker,
            supervisor=supervisor,
            instrument="NAS100",
            strategy_id="nas100_v2b_ungated_oanda",
            strategy_type="v2b_scaleout",
            entry_qty=3,
            mode="live",
            stream_stale_s=180.0,
            email_on_action=False,
            clock=lambda: clock["t"],
        )
        controller._last_stream_at = clock["t"] - 400.0
        result = controller.run_cycle(phase="stream_watchdog", force=True)
        assert result.invariant is not None
        assert result.invariant.classification == "stream_stale"
        assert supervisor.mode == ENTRY_FROZEN
        assert controller._stream_stale_latched

        # Reconnect + REST reconcile while book still healthy → rearm.
        clock["t"] += 1.0
        re = controller.note_stream_reconnected()
        assert re.invariant is not None and re.invariant.ok
        assert "stream_rearmed" in re.actions
        assert supervisor.mode == RUNNING
        assert not controller._stream_stale_latched
    finally:
        tmp.cleanup()


def test_next_stream_backoff_has_jitter_and_429_floor():
    from potions.live.demo import next_stream_backoff

    class Exc429(Exception):
        def __str__(self):
            return "HTTP 429 Too Many Requests"

    vals = {next_stream_backoff(60.0, 180.0, Exc429()) for _ in range(30)}
    assert min(vals) >= 96.0  # 120 * 0.8
    assert max(vals) <= 300.0
    assert len(vals) > 1  # jitter varies


def test_containment_email_eod_digest_once_per_session(monkeypatch):
    """Watchdog findings accumulate; one email after NY 16:00 per session."""
    import potions.live.demo.oanda_daemon_reconcile as mod
    from potions.live.demo.oanda_daemon_reconcile import (
        BracketInvariantResult,
        ContainmentCycleResult,
    )

    monkeypatch.setenv("POTIONS_OANDA_CONTAINMENT_EMAIL", "eod")
    assert containment_email_mode() == "eod"

    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"US30": "US30_USD"})
        broker = OandaBroker(store, config=config, client=None, authority_strategy_ids=["us30_st"])
        ctrl = DaemonContainmentController(
            store=store,
            broker=broker,
            supervisor=None,
            instrument="US30",
            strategy_id="us30_st",
            email_on_action=True,
        )
        assert ctrl.email_mode == "eod"
        sent = []
        monkeypatch.setattr(
            "potions.live.notify_email.send_email",
            lambda **kw: sent.append(kw.get("subject") or ""),
        )
        inv = BracketInvariantResult(
            ok=False,
            classification="orphan_protective",
            ownership_certain=True,
            local_qty=0.0,
            stop_qty=0.0,
            tp_qty=0.0,
            working_roles=[],
            reasons=["flat_with_working_protectives=1"],
            recommended_action="cancel_orphans",
        )
        result = ContainmentCycleResult(
            mode="shadow",
            phase="bracket_watchdog",
            state="ARMED_FLAT",
            invariant=inv,
            actions=["detect:orphan_protective", "shadow_would_cancel_orphan_protectives"],
            shadow=True,
        )
        ctrl._record_email_digest(result)
        ctrl._record_email_digest(result)
        digest = json.loads((store.root / "containment_email_digest.json").read_text(encoding="utf-8"))
        assert digest["by_class"]["orphan_protective"] == 2

        monkeypatch.setattr(mod, "ny_past_containment_email_eod", lambda now=None: False)
        ctrl._maybe_flush_eod_email()
        assert sent == []

        monkeypatch.setattr(mod, "ny_past_containment_email_eod", lambda now=None: True)
        ctrl._maybe_flush_eod_email()
        assert len(sent) == 1
        assert "EOD digest" in sent[0]
        ctrl._maybe_flush_eod_email()
        assert len(sent) == 1
    finally:
        tmp.cleanup()


def test_flat_entry_limit_is_armed_entry_not_orphan():
    result = evaluate_bracket_invariant(
        instrument="US30",
        strategy_id="us30_3r",
        positions=[],
        orders=[
            {
                "broker_order_id": "e1",
                "strategy_id": "us30_3r",
                "instrument": "US30",
                "status": "working",
                "order_type": "limit",
                "bracket_role": "entry",
                "quantity": 1,
                "reduce_only": False,
            }
        ],
    )
    assert result.ok
    assert result.classification == "armed_entry"
    assert result.recommended_action == "none"


def test_flat_entry_with_account_qty_is_cross_book():
    result = evaluate_bracket_invariant(
        instrument="NAS100",
        strategy_id="nas100_3r",
        positions=[],
        orders=[
            {
                "broker_order_id": "e1",
                "strategy_id": "nas100_3r",
                "instrument": "NAS100",
                "status": "working",
                "order_type": "limit",
                "bracket_role": "entry",
                "quantity": 1,
                "reduce_only": False,
            }
        ],
        account_instrument_qty=2.0,
    )
    assert not result.ok
    assert result.classification == "cross_book_entry"
    assert result.recommended_action == "cancel_orphans"


def test_cross_book_entry_gate_blocks_submit_when_sibling_open():
    tmp, store = make_store()
    try:
        config = OandaConfig(account_id="101-002-39860312-001", instrument_map={"NAS100": "NAS100_USD"})
        client = _FakeClient(
            pending=[],
            trades=[
                {
                    "id": "t_runners",
                    "instrument": "NAS100_USD",
                    "currentUnits": "2",
                    "price": "29335.4",
                    "clientExtensions": {"tag": "nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda"},
                }
            ],
        )
        broker = OandaBroker(
            store,
            config=config,
            client=client,
            authority_strategy_ids=["nas100_hourly_st_pmc_sl50_tp150_3r_oanda"],
            position_scope_instruments=["NAS100"],
        )
        intent = OrderIntent.create(
            strategy_id="nas100_hourly_st_pmc_sl50_tp150_3r_oanda",
            trade_id="pending",
            instrument="NAS100",
            account_mode="paper",
            side="buy",
            order_type="limit",
            quantity=1,
            limit_price=29335.4,
            reason="entry",
            bracket_role="entry",
            requires_verification=False,
        )
        with pytest.raises(OandaRoutingBlocked, match="cross_book_instrument_open"):
            broker.submit_order_intent(intent)
    finally:
        tmp.cleanup()
