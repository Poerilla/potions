"""Trade-id lot matching + reachable stop stress."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from potions.live.replay_audit import (
    Bar,
    Unit,
    _reachable_intrabar_points,
    audit_units,
    units_from_live_fills,
)


def _write_fills(path: Path, rows):
    fields = [
        "fill_id",
        "broker_order_id",
        "intent_id",
        "strategy_id",
        "trade_id",
        "instrument",
        "account_mode",
        "side",
        "quantity",
        "price",
        "ts",
        "reason",
        "mid_price",
        "bid_price",
        "ask_price",
        "spread",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, row in enumerate(rows):
            base = {k: "" for k in fields}
            base.update(row)
            base.setdefault("fill_id", "f%d" % i)
            base.setdefault("broker_order_id", "o%d" % i)
            base.setdefault("instrument", "NQ")
            base.setdefault("account_mode", "paper")
            base.setdefault("quantity", "1")
            w.writerow(base)


def test_units_match_within_trade_id_not_across_concurrent_shorts():
    """Two concurrent shorts must not cross-pair exits (legacy FIFO bug)."""
    tmp = tempfile.TemporaryDirectory()
    try:
        path = Path(tmp.name) / "fills.csv"
        sid = "nq_test"
        _write_fills(
            path,
            [
                # Trade A: short @ 100, later cover @ 100 (BE scratch)
                {
                    "strategy_id": sid,
                    "trade_id": "tA",
                    "side": "sell",
                    "price": "100",
                    "ts": "2024-01-01T10:00:00-05:00",
                    "reason": "runner_entry",
                },
                # Trade B: short @ 200
                {
                    "strategy_id": sid,
                    "trade_id": "tB",
                    "side": "sell",
                    "price": "200",
                    "ts": "2024-01-01T10:01:00-05:00",
                    "reason": "runner_entry",
                },
                # Close B first (BE scratch). Trade-id match → −0.25; cross-FIFO pairs B's
                # exit with A's entry @100 → bogus −100.25.
                {
                    "strategy_id": sid,
                    "trade_id": "tB",
                    "side": "buy",
                    "price": "200.25",
                    "ts": "2024-01-02T10:00:00-05:00",
                    "reason": "runner_stop",
                },
                {
                    "strategy_id": sid,
                    "trade_id": "tA",
                    "side": "buy",
                    "price": "150",
                    "ts": "2024-06-01T10:00:00-05:00",
                    "reason": "runner_stop",
                },
            ],
        )
        units = units_from_live_fills(path, sid, match_within_trade_id=True)
        assert len(units) == 2
        by = {u.trade_id: u for u in units}
        assert abs(by["tB"].points - (-0.25)) < 1e-9
        assert abs(by["tA"].points - (-50.0)) < 1e-9

        legacy = units_from_live_fills(path, sid, match_within_trade_id=False)
        legacy_by = {u.trade_id: u for u in legacy}
        # Contaminated: B's exit attributed to A's entry
        assert legacy_by["tA"].points < -50
    finally:
        tmp.cleanup()


def test_reachable_stress_clips_to_be_stop():
    unit = Unit(
        candidate="c",
        trade_id="t1",
        unit_id="1",
        direction="Short",
        entry_ts="2024-01-01T10:00:00-05:00",
        entry_price=100.0,
        exit_ts="2024-01-03T10:00:00-05:00",
        exit_price=100.0,
        exit_reason="runner_stop",
        entry_reason="runner_entry",
        hard_stop_price=150.0,
        be_after_ts="2024-01-01T11:00:00-05:00",
    )
    # After BE: bar opens at entry then spikes to 200 — stop touched at entry, not 200
    bar = Bar(
        ts="2024-01-02T10:00:00-05:00",
        open=100.0,
        high=200.0,
        low=99.0,
        close=150.0,
    )
    pts = _reachable_intrabar_points(unit, bar)
    assert abs(pts - 0.0) < 1e-9  # short BE stop @ 100 → fill 100 → 0 pts

    raw = unit.entry_price - bar.high
    assert raw == -100.0


def test_reachable_stress_gap_open_beyond_stop():
    unit = Unit(
        candidate="c",
        trade_id="t1",
        unit_id="1",
        direction="Long",
        entry_ts="2024-01-01T10:00:00-05:00",
        entry_price=100.0,
        exit_ts="2024-01-02T10:00:00-05:00",
        exit_price=90.0,
        exit_reason="stop",
        entry_reason="entry",
        hard_stop_price=95.0,
        be_after_ts="",
    )
    bar = Bar(ts="2024-01-01T12:00:00-05:00", open=90.0, high=91.0, low=88.0, close=89.0)
    pts = _reachable_intrabar_points(unit, bar)
    assert abs(pts - (90.0 - 100.0)) < 1e-9  # gap open fill, not low 88


def test_forced_flat_marks_open_lots():
    tmp = tempfile.TemporaryDirectory()
    try:
        path = Path(tmp.name) / "fills.csv"
        sid = "nq_test"
        _write_fills(
            path,
            [
                {
                    "strategy_id": sid,
                    "trade_id": "t1",
                    "side": "buy",
                    "price": "100",
                    "ts": "2024-01-01T10:00:00-05:00",
                    "reason": "entry",
                },
            ],
        )
        units = units_from_live_fills(
            path,
            sid,
            mark_open_ts="2024-12-31T16:00:00-05:00",
            mark_open_price=110.0,
            mark_exit_reason="forced_flat_eod",
            stop_pts=50.0,
        )
        assert len(units) == 1
        assert units[0].exit_reason == "forced_flat_eod"
        assert abs(units[0].points - 10.0) < 1e-9
        assert units[0].hard_stop_price == 50.0
    finally:
        tmp.cleanup()


def test_audit_units_uses_reachable_stress():
    unit = Unit(
        candidate="c",
        trade_id="t1",
        unit_id="1",
        direction="Short",
        entry_ts="2024-01-01T10:00:00-05:00",
        entry_price=100.0,
        exit_ts="2024-01-03T10:00:00-05:00",
        exit_price=100.0,
        exit_reason="runner_stop",
        entry_reason="runner_entry",
        hard_stop_price=150.0,
        be_after_ts="2024-01-01T10:00:00-05:00",
    )
    bars = [
        Bar(ts="2024-01-01T10:00:00-05:00", open=100, high=100, low=100, close=100),
        Bar(ts="2024-01-02T10:00:00-05:00", open=101, high=200, low=99, close=150),
        Bar(ts="2024-01-03T10:00:00-05:00", open=100, high=100, low=100, close=100),
    ]
    tmp = tempfile.TemporaryDirectory()
    try:
        out = Path(tmp.name)
        result = audit_units(
            name="t",
            slug="t",
            source=out / "fills.csv",
            bar_source=out / "bars.csv",
            bars=bars,
            units=[unit],
            instrument="NQ",
            notes="test",
            output_root=out,
        )
        # With BE clip, stress should be near zero — not −100 pts × $20 = −$2000
        assert result.intrabar_mtm_dd_usd > -100.0
    finally:
        tmp.cleanup()
