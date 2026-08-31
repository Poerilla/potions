from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from potions.live.engine import Engine
from potions.live.models import Bar, StrategyInstance, as_row
from potions.live.store import FlatFileStore
from potions.live.strategies.first_hour_follow import FirstHourFollowStrategy


def _store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def _inst(store, **cfg):
    payload = {
        "tick_size": 0.25,
        "entry_qty": 1,
        "r_mult": 3.0,
        "min_fh_bars": 2,
        "require_fh_body": "strong",
        "require_sweep_side": "sweep_with_side",
        "strong_body_min": 0.66,
        "suppress_alerts": True,
    }
    payload.update(cfg)
    inst = StrategyInstance(
        strategy_id="nq_fh_test",
        strategy_type="first_hour_follow",
        version="v1",
        instrument="NQ",
        broker_instrument="NQ",
        account_mode="paper",
        enabled=True,
        timeframes="5m,1h",
        max_contracts=2,
        max_open_orders=8,
        config_json=json.dumps(payload, sort_keys=True),
    )
    store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
    return inst


def _b(ts, o, h, l, c, tf="5m"):
    return Bar("NQ", tf, ts, o, h, l, c, volume=10.0, complete=True)


def _day_bars(day: str, fh_open, fh_high, fh_low, fh_close, eod_close=None):
    """Two FH bars (09:30 + 10:25) and an EOD bar."""
    o = float(fh_open)
    h = float(fh_high)
    l = float(fh_low)
    c = float(fh_close)
    mid = (o + c) / 2.0
    eod = float(eod_close if eod_close is not None else c)
    return [
        _b("%sT09:30:00" % day, o, max(o, h * 0.99), min(o, l * 1.01) if l else o, mid),
        _b("%sT10:25:00" % day, mid, h, l, c),
        _b("%sT15:55:00" % day, eod, eod + 1, eod - 1, eod),
    ]


def test_sweep_with_side_strong_enters_and_weak_skips():
    tmp, store = _store()
    try:
        _inst(store)
        engine = Engine(store=store, persist_bars=False, persist_health=False, emit_order_alerts=False)
        # Day 1 sets prior-day high at 100 and a low well below so day-2 longs
        # take PDH without also taking PDL (that would be fade_follow_through).
        bars = _day_bars("2024-01-02", 95, 100, 80, 96, eod_close=96)
        # Day 2 strong long that takes PDH → sweep_with_side.
        bars += _day_bars("2024-01-03", 95, 106, 94.5, 105, eod_close=110)
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        entries = [f for f in fills if str(f.get("reason")) == "entry"]
        assert len(entries) == 1
        assert str(entries[0]["ts"]).startswith("2024-01-03T10:25")
        assert str(entries[0]["side"]) == "buy"
    finally:
        tmp.cleanup()


def test_sweep_gate_skips_fade_follow_through():
    tmp, store = _store()
    try:
        _inst(store)
        engine = Engine(store=store, persist_bars=False, persist_health=False, emit_order_alerts=False)
        bars = _day_bars("2024-01-02", 95, 100, 80, 96, eod_close=96)
        # Strong SHORT that takes PDH → fade_follow_through, not sweep_with_side.
        bars += _day_bars("2024-01-03", 106, 107, 94, 95, eod_close=91)
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        entries = [f for f in fills if str(f.get("reason")) == "entry"]
        assert entries == []
    finally:
        tmp.cleanup()


def test_close_limit_enters_on_pullback_to_close():
    tmp, store = _store()
    try:
        _inst(
            store,
            require_fh_body="",
            require_sweep_side="",
            entry_mode="close_limit",
            sl_mode="open",
            tp_mode="r_mult",
            r_mult=3.0,
            min_fh_bars=2,
        )
        engine = Engine(store=store, persist_bars=False, persist_health=False, emit_order_alerts=False)
        # Green FH: open 100 close 110 → buy limit @ 110, SL @ 100, TP @ 140.
        bars = [
            _b("2024-01-03T09:30:00", 100, 108, 99.5, 105),
            _b("2024-01-03T10:25:00", 105, 111, 104, 110),
            # Pullback touches 110 → limit fill.
            _b("2024-01-03T10:30:00", 110.5, 111, 109.5, 110),
            # Continue to 3R.
            _b("2024-01-03T11:00:00", 110, 141, 109.75, 140.5),
            _b("2024-01-03T15:55:00", 140, 141, 139, 140),
        ]
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        entries = [f for f in fills if str(f.get("reason")) == "entry"]
        assert len(entries) == 1
        assert str(entries[0]["side"]) == "buy"
        assert float(entries[0]["price"]) == 110.0
        assert str(entries[0]["ts"]).startswith("2024-01-03T10:30")
    finally:
        tmp.cleanup()


def test_entry_dates_gate_allows_listed_session_only():
    tmp, store = _store()
    try:
        allow = Path(tmp.name) / "dates.txt"
        allow.write_text("2024-01-03\n", encoding="utf-8")
        _inst(
            store,
            require_fh_body="",
            require_sweep_side="",
            entry_mode="market_close",
            entry_dates_path=str(allow),
            min_fh_bars=2,
        )
        engine = Engine(store=store, persist_bars=False, persist_health=False, emit_order_alerts=False)
        # Day blocked by allowlist.
        bars = _day_bars("2024-01-02", 100, 110, 99, 108, eod_close=108)
        # Day allowed.
        bars += _day_bars("2024-01-03", 100, 110, 99, 108, eod_close=108)
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        entries = [f for f in fills if str(f.get("reason")) == "entry"]
        assert len(entries) == 1
        assert str(entries[0]["ts"]).startswith("2024-01-03T10:25")
    finally:
        tmp.cleanup()


def test_st_trail_ratchets_stop_after_hour_complete():
    tmp, store = _store()
    try:
        trail_log = Path(tmp.name) / "trail.jsonl"
        _inst(store, st_trail=True, trail_log_path=str(trail_log), require_sweep_side="sweep_with_side")
        engine = Engine(store=store, persist_bars=False, persist_health=False, emit_order_alerts=False)
        bars = []
        # Warm up ST with 16 bullish hourly bars.
        t0 = datetime(2024, 1, 2, 0, 0, 0)
        px = 90.0
        for i in range(16):
            ts = (t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S")
            bars.append(_b(ts, px, px + 2, px - 0.5, px + 1.5, tf="1h"))
            px += 1.5
        bars += _day_bars("2024-01-02", 95, 100, 80, 96, eod_close=96)
        # Day 3 FH entry only — do not flatten at 15:55 before the trail bars.
        bars += [
            _b("2024-01-03T09:30:00", 95, 104.94, 95, 100),
            _b("2024-01-03T10:25:00", 100, 106, 94.5, 105),
        ]
        # Hour-complete 10:00 bar is usable at 11:00.
        bars.append(_b("2024-01-03T10:00:00", 100.5, 108, 100, 107, tf="1h"))
        bars.append(_b("2024-01-03T11:00:00", 107, 109, 106.5, 108))
        bars.append(_b("2024-01-03T11:05:00", 108, 109, 107, 108.5))
        engine.replay_bars(bars)
        fills = store.read_table("fills")
        entries = [f for f in fills if str(f.get("reason")) == "entry"]
        assert entries, "expected sweep+strong entry"
        events = []
        if trail_log.exists():
            for line in trail_log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        mods = [e for e in events if e.get("event") == "trail_modify"]
        assert mods, "expected ST trail modify after aligned hour-complete ST"
        plugin = FirstHourFollowStrategy(store, engine.manager.plugins["nq_fh_test"].instance)
        assert plugin.strategy_type == "first_hour_follow"
    finally:
        tmp.cleanup()
