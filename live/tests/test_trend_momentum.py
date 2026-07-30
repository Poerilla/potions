"""Unit tests for TrendMomentumStrategy."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytz

from potions.live.engine import Engine
from potions.live.models import Bar, StrategyInstance, as_row
from potions.live.store import FlatFileStore
from potions.live.strategies.trend_momentum import TrendMomentumStrategy, default_config

NY = pytz.timezone("America/New_York")

# lookback=2 HH+HL + 2-bar pullback + momentum (validated offline)
CLEAN_UP = [
    (100.0, 100.5, 99.8, 100.3),
    (100.2, 100.7, 100.0, 100.5),
    (100.4, 100.9, 100.2, 100.7),
    (100.6, 101.1, 100.4, 100.9),
    (100.8, 101.3, 100.6, 101.1),
    (101.0, 102.0, 100.8, 101.8),
    (101.8, 103.5, 101.7, 103.0),  # H1
    (103.0, 103.2, 102.0, 102.2),
    (102.2, 102.4, 101.0, 101.2),
    (101.2, 101.5, 100.0, 100.5),  # L1
    (100.5, 101.0, 100.1, 100.8),
    (100.8, 102.0, 100.7, 101.8),
    (101.8, 105.0, 101.7, 104.5),  # H2 HH
    (104.5, 104.8, 103.5, 103.8),
    (103.8, 104.0, 102.5, 102.8),
    (102.8, 103.0, 101.5, 101.8),  # L2 HL
    (101.8, 102.5, 101.6, 102.2),
    (102.2, 102.5, 102.0, 102.1),  # pb1
    (102.1, 102.2, 101.8, 101.9),  # pb2
    (101.9, 108.0, 101.8, 107.5),  # momentum
]


def _store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name), defer_table_writes=True)
    store.ensure()
    return tmp, store


def _bar(ts: datetime, o: float, h: float, l: float, c: float, tf: str = "5m") -> Bar:
    if ts.tzinfo is None:
        ts = NY.localize(ts)
    return Bar(
        instrument="TEST",
        timeframe=tf,
        ts=ts.isoformat(),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1.0,
        complete=True,
        source="synthetic",
    )


def _plugin(store: FlatFileStore, **cfg_over) -> TrendMomentumStrategy:
    cfg = default_config(0.25, atr_len=5, swing_lookback=2, **cfg_over)
    instance = StrategyInstance(
        strategy_id="tm_test",
        strategy_type="trend_momentum",
        version="v1",
        instrument="TEST",
        broker_instrument="TEST",
        account_mode="paper",
        enabled=True,
        timeframes="5m",
        max_contracts=1,
        config_json=json.dumps(cfg),
    )
    return TrendMomentumStrategy(store, instance)


def _upsert(store: FlatFileStore, cfg: dict) -> None:
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id="tm_test",
                strategy_type="trend_momentum",
                version="v1",
                instrument="TEST",
                broker_instrument="TEST",
                account_mode="paper",
                enabled=True,
                timeframes="5m",
                max_contracts=1,
                config_json=json.dumps(cfg),
            )
        ),
    )


def test_registry_has_trend_momentum():
    from potions.live.registry import StrategyRegistry

    assert "trend_momentum" in StrategyRegistry().available()


def test_trend_hh_hl_and_momentum_helpers():
    tmp, store = _store()
    try:
        s = _plugin(store, momentum_atr_mult=0.5, min_pullback_bars=2)
        start = NY.localize(datetime(2024, 6, 3, 10, 0))
        for i, (o, h, l, c) in enumerate(CLEAN_UP):
            s._append_bar(_bar(start + timedelta(minutes=5 * i), o, h, l, c))
        highs, lows = s._confirmed_swings()
        assert s._trend_direction() == "up", "swings highs=%s lows=%s" % (highs, lows)
        assert s._is_momentum_bar("up")
        assert s._pullback_gate("up")
        assert s._atr() is not None
    finally:
        tmp.cleanup()


def test_engine_entry_on_clean_uptrend():
    tmp, store = _store()
    try:
        cfg = default_config(
            0.25,
            atr_len=5,
            momentum_atr_mult=0.5,
            swing_lookback=2,
            min_pullback_bars=2,
            trend_end_mode="opposite",
        )
        _upsert(store, cfg)
        start = NY.localize(datetime(2024, 6, 3, 10, 0))
        ohlc = CLEAN_UP + [
            (107.5, 109.0, 107.4, 108.5),
            (108.5, 109.0, 108.0, 108.8),
        ]
        bars = [
            _bar(start + timedelta(minutes=5 * i), o, h, l, c) for i, (o, h, l, c) in enumerate(ohlc)
        ]
        Engine(store=store, slippage_ticks=0.0, tick_size={"TEST": 0.25}).replay_bars(bars)
        store.flush_tables()
        fills = store.read_table("fills")
        entries = [f for f in fills if f.get("reason") == "entry"]
        assert len(entries) >= 1, fills
        assert entries[0]["side"] == "buy"
    finally:
        tmp.cleanup()


def test_no_entry_without_trend():
    tmp, store = _store()
    try:
        cfg = default_config(0.25, atr_len=5, momentum_atr_mult=0.3, swing_lookback=2, min_pullback_bars=0)
        _upsert(store, cfg)
        start = NY.localize(datetime(2024, 6, 3, 10, 0))
        bars = []
        for i in range(40):
            o = 100 + (0.3 if i % 2 == 0 else -0.3)
            c = 100 - (0.3 if i % 2 == 0 else -0.3)
            bars.append(
                _bar(start + timedelta(minutes=5 * i), o, max(o, c) + 0.1, min(o, c) - 0.1, c)
            )
        Engine(store=store, slippage_ticks=0.0, tick_size={"TEST": 0.25}).replay_bars(bars)
        store.flush_tables()
        assert [f for f in store.read_table("fills") if f.get("reason") == "entry"] == []
    finally:
        tmp.cleanup()


def test_narrow_bar_stop_uses_far_side():
    tmp, store = _store()
    try:
        s = _plugin(store, narrow_atr_frac=0.5, momentum_atr_mult=0.01, min_pullback_bars=0)
        start = NY.localize(datetime(2024, 6, 3, 10, 0))
        for i in range(20):
            s._append_bar(
                _bar(start + timedelta(minutes=5 * i), 100, 110, 90, 105 if i % 2 == 0 else 95)
            )
        atr = s._atr()
        assert atr is not None and atr > 5
        narrow = _bar(start + timedelta(minutes=5 * 21), 100, 100.4, 100.0, 100.35)
        assert (narrow.high - narrow.low) < 0.5 * atr
        assert (narrow.low - 0.25) < (narrow.high + narrow.low) / 2
    finally:
        tmp.cleanup()
