from __future__ import annotations

import json
import tempfile
from pathlib import Path

from potions.live.broker import PaperBroker
from potions.live.demo.eurusd_v2b_ungated_paper import (
    DemoPaperRunner,
    append_progress,
    bootstrap_store,
    is_ny_rth,
    write_run_meta,
)
from potions.live.models import Bar, OrderIntent
from potions.live.oanda import OandaConfig, QuoteOneMinuteBarBuilder, parse_oanda_ts
from potions.live.store import FlatFileStore


def test_is_ny_rth_gates_on_america_new_york_clock():
    assert is_ny_rth("2026-07-21T14:00:00Z")
    assert not is_ny_rth("2026-07-21T13:00:00Z")
    assert not is_ny_rth("2026-07-21T20:00:00Z")
    assert is_ny_rth("2026-07-21T19:59:00Z")


def test_quote_builder_emits_mid_bid_ask_ohlc():
    builder = QuoteOneMinuteBarBuilder("EURUSD")
    out = []
    out.extend(builder.on_quote(bid=1.1000, ask=1.1002, ts="2026-07-21T13:30:10Z"))
    out.extend(builder.on_quote(bid=1.1001, ask=1.1003, ts="2026-07-21T13:30:40Z"))
    out.extend(builder.on_quote(bid=1.1005, ask=1.1007, ts="2026-07-21T13:31:05Z"))
    assert len(out) == 1
    bar = out[0]
    assert bar.has_quote_book()
    assert bar.open == (1.1000 + 1.1002) / 2.0
    assert bar.bid_low == 1.1000
    assert bar.ask_high == 1.1003
    assert bar.close == (1.1001 + 1.1003) / 2.0


def test_paper_broker_buys_at_ask_sells_at_bid_when_quote_book_present():
    tmp = tempfile.TemporaryDirectory()
    try:
        store = FlatFileStore(Path(tmp.name))
        store.ensure()
        broker = PaperBroker(store, slippage_ticks=0.0, spread_model=None, tick_size={"EURUSD": 0.00001})
        buy = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="EURUSD",
            account_mode="paper",
            side="buy",
            order_type="market",
            quantity=1,
            requires_verification=False,
        )
        buy_order = broker.submit_order_intent(buy)
        bar = Bar(
            instrument="EURUSD",
            timeframe="1m",
            ts="2026-07-21T13:31:00Z",
            open=1.1001,
            high=1.1002,
            low=1.1000,
            close=1.1001,
            bid_open=1.1000,
            bid_high=1.1000,
            bid_low=1.0999,
            bid_close=1.1000,
            ask_open=1.1002,
            ask_high=1.1003,
            ask_low=1.1002,
            ask_close=1.1002,
            source="test",
        )
        fills = broker.process_bar(bar)
        assert len(fills) == 1
        assert fills[0].price == 1.1002  # ask_open
        assert fills[0].ask_price == 1.1002
        assert fills[0].bid_price == 1.1000
        assert fills[0].spread is not None and abs(fills[0].spread - 0.0002) < 1e-12

        sell = OrderIntent.create(
            strategy_id="s1",
            trade_id="t1",
            instrument="EURUSD",
            account_mode="paper",
            side="sell",
            order_type="market",
            quantity=1,
            requires_verification=False,
            reduce_only=True,
        )
        broker.submit_order_intent(sell)
        bar2 = Bar(
            instrument="EURUSD",
            timeframe="1m",
            ts="2026-07-21T13:32:00Z",
            open=1.1001,
            high=1.1002,
            low=1.1000,
            close=1.1001,
            bid_open=1.0998,
            bid_high=1.0999,
            bid_low=1.0998,
            bid_close=1.0998,
            ask_open=1.1000,
            ask_high=1.1001,
            ask_low=1.1000,
            ask_close=1.1000,
            source="test",
        )
        sell_fills = broker.process_bar(bar2)
        assert len(sell_fills) == 1
        assert sell_fills[0].price == 1.0998  # bid_open
    finally:
        tmp.cleanup()


def test_demo_runner_logs_ticks_only_in_rth_and_engines_only_rth_bars():
    tmp = tempfile.TemporaryDirectory()
    try:
        output_root = Path(tmp.name) / "eurusd_v2b_ungated_paper"
        store = bootstrap_store(output_root)
        runner = DemoPaperRunner(output_root=output_root, store=store)

        for minute in range(28, 30):
            for sec in (0, 30):
                runner.on_price_tick(
                    bid=1.10,
                    ask=1.1002,
                    ts="2026-07-21T13:%02d:%02dZ" % (minute, sec),
                    quantity=1,
                )
        for minute in range(30, 32):
            for sec in (0, 15, 30, 45):
                mid = 1.1000 + minute * 0.0001 + sec * 0.00001
                runner.on_price_tick(
                    bid=mid - 0.0001,
                    ask=mid + 0.0001,
                    price=mid,
                    ts="2026-07-21T13:%02d:%02dZ" % (minute, sec),
                    quantity=1,
                )
        runner.flush()

        assert runner.ticks_logged > 0
        day_file = output_root / "state" / "events" / "rth_ticks" / "2026-07-21.jsonl"
        assert day_file.exists()
        lines = [json.loads(line) for line in day_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert all(is_ny_rth(row["event_ts"]) for row in lines)
        assert all("bid" in row and "ask" in row and "mid" in row for row in lines)

        bars = store.read_bars("EURUSD", "1m")
        assert len(bars) >= 1
        assert any(bar.has_quote_book() for bar in bars)
        assert runner.bars_engine >= 1
        assert runner.bars_persisted >= runner.bars_engine
        progress = (output_root / "PROGRESS.log").read_text(encoding="utf-8")
        assert "NY RTH open" in progress
    finally:
        tmp.cleanup()


def test_run_meta_and_progress_written_without_token():
    tmp = tempfile.TemporaryDirectory()
    try:
        output_root = Path(tmp.name)
        config = OandaConfig(env="practice", account_id="101-002-39860312-001", token="")
        meta = write_run_meta(output_root, config=config)
        append_progress(output_root, "STARTED test")
        assert meta["oanda_routing"] is False
        assert meta["fill_price"] == "bid_ask"
        assert meta["signal_price"] == "mid"
        assert "token" not in meta
        assert (output_root / "RUN_META.json").exists()
        assert "STARTED test" in (output_root / "PROGRESS.log").read_text(encoding="utf-8")
    finally:
        tmp.cleanup()


def test_format_error_includes_type_and_traceback():
    from potions.live.demo.eurusd_v2b_ungated_paper import _format_error, _log_stream_error

    try:
        raise ConnectionError("stream gone")
    except ConnectionError as exc:
        text = _format_error(exc)
    assert "ConnectionError" in text
    assert "stream gone" in text
    assert "Traceback" in text

    tmp = tempfile.TemporaryDirectory()
    try:
        output_root = Path(tmp.name)
        store = FlatFileStore(output_root / "state")
        store.ensure()
        try:
            raise TimeoutError("read timed out")
        except TimeoutError as exc:
            _log_stream_error(output_root, store, stage="stream_read", exc=exc, extra={"attempt": 2})
        progress = (output_root / "PROGRESS.log").read_text(encoding="utf-8")
        assert "ERROR stage=stream_read" in progress
        assert "TimeoutError" in progress
        err_path = output_root / "state" / "events" / "stream_errors.jsonl"
        assert err_path.exists()
        row = json.loads(err_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["stage"] == "stream_read"
        assert row["error_type"] == "TimeoutError"
        assert row["attempt"] == 2
    finally:
        tmp.cleanup()
