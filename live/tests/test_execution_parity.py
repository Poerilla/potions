from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from potions.live.execution_parity_audit import audit_execution_parity, match_units
from potions.live.manual_journal import MANUAL_JOURNAL_FILL_COLUMNS, validate_manual_journal
from potions.live.replay_audit import Unit, units_from_live_fills


def _write_fills(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANUAL_JOURNAL_FILL_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_manual_journal_template_validates():
    tmp = tempfile.TemporaryDirectory()
    try:
        path = Path(tmp.name) / "fills.csv"
        _write_fills(
            path,
            [
                {
                    "fill_id": "f1",
                    "broker_order_id": "o1",
                    "intent_id": "",
                    "strategy_id": "manual_v2b_session",
                    "trade_id": "t1",
                    "instrument": "MNQ",
                    "account_mode": "paper",
                    "side": "buy",
                    "quantity": "1",
                    "price": "100.00",
                    "ts": "2026-03-04T10:00:00-05:00",
                    "reason": "entry",
                    "session_date": "2026-03-04",
                    "order_type": "market",
                    "source": "tradovate_demo",
                    "notes": "",
                },
                {
                    "fill_id": "f2",
                    "broker_order_id": "o2",
                    "intent_id": "",
                    "strategy_id": "manual_v2b_session",
                    "trade_id": "t1",
                    "instrument": "MNQ",
                    "account_mode": "paper",
                    "side": "sell",
                    "quantity": "1",
                    "price": "101.00",
                    "ts": "2026-03-04T10:05:00-05:00",
                    "reason": "tp1",
                    "session_date": "2026-03-04",
                    "order_type": "limit",
                    "source": "tradovate_demo",
                    "notes": "",
                },
            ],
        )
        result = validate_manual_journal(path)
        assert result.ok
        assert result.row_count == 2
    finally:
        tmp.cleanup()


def test_execution_parity_matches_and_flags_sim_better_fills():
    tmp = tempfile.TemporaryDirectory()
    try:
        live_path = Path(tmp.name) / "live.csv"
        sim_path = Path(tmp.name) / "sim.csv"
        base = {
            "fill_id": "",
            "broker_order_id": "",
            "intent_id": "",
            "strategy_id": "manual_v2b_session",
            "trade_id": "t1",
            "instrument": "MNQ",
            "account_mode": "paper",
            "quantity": "1",
            "session_date": "2026-03-04",
            "order_type": "market",
            "source": "test",
            "notes": "",
        }
        _write_fills(
            live_path,
            [
                dict(base, fill_id="l1", side="buy", price="100.00", ts="2026-03-04T10:00:00-05:00", reason="entry"),
                dict(base, fill_id="l2", side="sell", price="101.00", ts="2026-03-04T10:05:00-05:00", reason="tp1"),
            ],
        )
        _write_fills(
            sim_path,
            [
                dict(base, fill_id="s1", side="buy", price="99.75", ts="2026-03-04T10:00:00-05:00", reason="entry"),
                dict(base, fill_id="s2", side="sell", price="101.25", ts="2026-03-04T10:05:00-05:00", reason="tp1"),
            ],
        )
        live_units = units_from_live_fills(live_path, "manual_v2b_session")
        sim_units = units_from_live_fills(sim_path, "manual_v2b_session")
        matched, _, _ = match_units(live_units, sim_units)
        assert len(matched) == 1
        result = audit_execution_parity(
            live_fills=live_path,
            sim_fills=sim_path,
            live_strategy_id="manual_v2b_session",
            sim_strategy_id="manual_v2b_session",
        )
        assert result.matched == 1
        assert result.median_entry_delta > 0
        assert not result.ok
    finally:
        tmp.cleanup()
