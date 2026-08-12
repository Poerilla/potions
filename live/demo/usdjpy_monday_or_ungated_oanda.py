"""USDJPY Monday OR Phase 2 primary — OANDA practice demo.

Tracker / Phase 2 default: ``M2_S3_R1`` (``monday_or_breakout``), N/S ≈ 8.20.
Artifacts: ``live/demo/usdjpy_monday_or_ungated_oanda/``.

Streams practice prices, aggregates 1m → 15m (left-labeled like research), routes
real practice orders via ``OandaBroker``. Local CSVs mirror Account Changes.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from datetime import time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

from ..broker import DEFAULT_TICK_SIZE
from ..engine import Engine
from ..models import Bar, StrategyInstance, as_row, utc_now_iso
from ..monday_or_phase2_tags import PAIR_PHASE2_DEFAULT, plugin_config
from ..oanda import (
    DEFAULT_PRIMARY_ACCOUNT,
    FifteenMinuteBarAggregator,
    OandaApiClient,
    OandaBroker,
    OandaConfig,
    QuoteOneMinuteBarBuilder,
    bid_ask_from_event,
    mid_price_from_event,
    parse_oanda_ts,
)
from ..store import FlatFileStore
from ..verification import SpoofVerificationProvider
from . import demo_run_root
from .oanda_v2b_ungated_common import (
    ACCOUNT_CHANGES_POLL_SECONDS,
    PROGRESS_HEARTBEAT_SECONDS,
    _interruptible_sleep,
    _jsonable,
    _log_stream_error,
    _price_levels,
    _remove_pidfile,
    append_progress,
    pid_is_alive,
    pidfile_path,
    poll_account_changes,
    progress_path,
    read_pid,
    run_log_path,
    run_meta_path,
    state_root_for,
)

INSTRUMENT = "USDJPY"
STRATEGY_ID = "usdjpy_monday_or_ungated_oanda"
RUN_DIRNAME = "usdjpy_monday_or_ungated_oanda"
PHASE2_TAG = PAIR_PHASE2_DEFAULT["USDJPY"]  # M2_S3_R1
TICK = 0.001
CLI_COMMAND = "demo-usdjpy-monday-or-oanda"
NY = pytz.timezone("America/New_York")
WEEK_END_SIZE_REPORT_NY = dt_time(15, 59)


def default_output_root() -> Path:
    return demo_run_root(RUN_DIRNAME)


def strategy_config_payload() -> Dict[str, Any]:
    payload = plugin_config(TICK, PHASE2_TAG, pair="USDJPY")
    payload.update(
        {
            "phase2_tag": PHASE2_TAG,
            "week_end_flatten": "15:59",
            "paper_only": False,
            "oanda_routing": True,
            "signal_price": "mid",
            "fill_price": "oanda",
        }
    )
    return payload


def write_run_meta(output_root: Path, *, config: OandaConfig) -> Dict[str, Any]:
    payload = strategy_config_payload()
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": STRATEGY_ID,
        "strategy_type": "monday_or_breakout",
        "phase2_tag": PHASE2_TAG,
        "instrument": INSTRUMENT,
        "oanda_instrument": config.symbol_for(INSTRUMENT),
        "tick_size": TICK,
        "timeframe": "15m",
        "entry_qty": payload["entry_qty"],
        "dd30_qty": payload["dd30_qty"],
        "dd50_qty": payload["dd50_qty"],
        "shifted_entry_qty": payload["shifted_entry_qty"],
        "max_trades_per_week": payload["max_trades_per_week"],
        "units_note": "Strategy qty maps 1:1 to OANDA units (tiny practice size; not research 7700 units).",
        "account_mode": "paper",
        "oanda_routing": True,
        "allow_live_routing": False,
        "oanda_env": config.env,
        "oanda_account_id": config.account_id or DEFAULT_PRIMARY_ACCOUNT,
        "oanda_api_url": config.api_url,
        "oanda_stream_url": config.stream_url,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "tracker": "STRATEGY_TRACKER Monday OR FX + monday_or_sizing_sweep_broker USDJPY #1 M2_S3_R1 N/S 8.20",
        "note": "OANDA practice Monday OR: 15m candles from quote stream; real practice orders; Fri 15:59 ET EOW chart pack.",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path) -> FlatFileStore:
    store = FlatFileStore(state_root_for(output_root))
    store.ensure()
    payload = strategy_config_payload()
    max_qty = max(int(payload["entry_qty"]), int(payload["shifted_entry_qty"]))
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=STRATEGY_ID,
                strategy_type="monday_or_breakout",
                version="v1",
                instrument=INSTRUMENT,
                broker_instrument=INSTRUMENT,
                account_mode="paper",
                enabled=True,
                timeframes="15m",
                max_contracts=max_qty,
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_engine(store: FlatFileStore, *, config: OandaConfig, client: OandaApiClient) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    broker = OandaBroker(
        store, config=config, client=client, allow_live_routing=False,
        authority_strategy_ids=[STRATEGY_ID],
    )
    return Engine(
        store=store,
        broker=broker,
        persist_bars=True,
        persist_health=True,
        tick_size={INSTRUMENT: TICK},
        verification_provider=SpoofVerificationProvider(store),
        emit_order_alerts=True,
        broker_log_events=True,
        broker_persist_modifications=True,
        slippage_ticks=0.0,
    )


class MondayOrOandaRunner:
    def __init__(
        self,
        *,
        output_root: Optional[Path] = None,
        config: Optional[OandaConfig] = None,
        client: Optional[OandaApiClient] = None,
    ):
        self.output_root = Path(output_root) if output_root is not None else default_output_root()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config = config or OandaConfig.from_env()
        self.store = bootstrap_store(self.output_root)
        self.client = client or OandaApiClient(config=self.config, store=self.store)
        self.engine = build_engine(self.store, config=self.config, client=self.client)
        self.builder_1m = QuoteOneMinuteBarBuilder(INSTRUMENT, source="oanda_monday_or_quote")
        self.agg_15m = FifteenMinuteBarAggregator(INSTRUMENT, source="oanda_monday_or_15m")
        self._last_progress_at = 0.0
        self._last_changes_poll_at = 0.0
        self.ticks_logged = 0
        self.bars_1m = 0
        self.bars_15m = 0
        self.fills_from_oanda = 0
        self.stop_requested = False
        self._weekly_size_week: Optional[str] = None
        self._weekly_chart_week: Optional[str] = None

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    def bootstrap_reconcile(self) -> None:
        broker = self.engine.broker
        if isinstance(broker, OandaBroker):
            try:
                broker.register_authority_strategy(STRATEGY_ID)
                broker.reconcile_from_account_details()
                append_progress(
                    self.output_root,
                    "OANDA reconcile lastTransactionID=%s open_orders=%d positions=%d"
                    % (
                        broker.last_transaction_id,
                        len(broker.reconcile_orders()),
                        len([p for p in broker.reconcile_positions() if p.quantity != 0]),
                    ),
                )
            except Exception as exc:
                append_progress(self.output_root, "WARN reconcile_from_account_details failed: %s" % exc)

    def maybe_poll_changes(self, *, force: bool = False) -> None:
        now = time.time()
        if (not force) and (now - self._last_changes_poll_at < ACCOUNT_CHANGES_POLL_SECONDS):
            return
        self._last_changes_poll_at = now
        n = poll_account_changes(self.engine, self.client, instrument=INSTRUMENT)
        if n:
            self.fills_from_oanda += n
            append_progress(self.output_root, "OANDA fills applied n=%d total=%d" % (n, self.fills_from_oanda))

    def on_price_tick(
        self,
        *,
        bid: float,
        ask: float,
        mid: Optional[float],
        ts: str,
        quantity: float = 0.0,
        raw: Optional[Dict[str, Any]] = None,
    ) -> List[Bar]:
        mid_px = float(mid) if mid is not None else (float(bid) + float(ask)) / 2.0
        day = parse_oanda_ts(ts).astimezone(NY).date().isoformat()
        payload = {
            "type": "price",
            "instrument": INSTRUMENT,
            "oanda_instrument": self.config.symbol_for(INSTRUMENT),
            "bid": bid,
            "ask": ask,
            "mid": mid_px,
            "spread": float(ask) - float(bid),
            "quantity": quantity,
            "event_ts": ts,
        }
        if raw:
            payload["raw"] = _jsonable(raw)
        self.store.append_event("fx_ticks/%s" % day, payload)
        self.ticks_logged += 1

        completed_15: List[Bar] = []
        for bar_1m in self.builder_1m.on_quote(bid=float(bid), ask=float(ask), mid=mid_px, quantity=quantity, ts=ts):
            self.bars_1m += 1
            self.store.append_bar(bar_1m)
            for bar_15 in self.agg_15m.on_bar(bar_1m):
                self._handle_15m(bar_15)
                completed_15.append(bar_15)
        self.maybe_poll_changes()
        self._maybe_weekly_size_report(ts)
        self._maybe_weekly_eow_charts(ts)
        self._maybe_heartbeat()
        return completed_15

    def _maybe_weekly_size_report(self, ts: str) -> None:
        """Friday >= 15:59 NY — echo price-data + log sizes once per ISO week."""
        from .size_report import append_size_report

        wall = parse_oanda_ts(ts).astimezone(NY)
        if wall.weekday() != 4:
            return
        if wall.timetz().replace(tzinfo=None) < WEEK_END_SIZE_REPORT_NY:
            return
        week_key = wall.date().isoformat()
        if self._weekly_size_week == week_key:
            return
        self._weekly_size_week = week_key
        try:
            append_size_report(
                self.output_root,
                append_progress,
                label="weekly_eow",
                session_date=wall.date(),
            )
        except Exception as exc:
            append_progress(self.output_root, "WARN weekly FILE_SIZES failed: %s" % exc)

    def _maybe_weekly_eow_charts(self, ts: str) -> None:
        """Friday >= 15:59 NY — Monday OR week overview + per-trade chart pack."""
        from .monday_or_eow_charts import maybe_write_eow_chart_pack

        wall = parse_oanda_ts(ts).astimezone(NY)
        if wall.weekday() != 4:
            return
        if wall.timetz().replace(tzinfo=None) < WEEK_END_SIZE_REPORT_NY:
            return
        week_key = wall.date().isoformat()
        if self._weekly_chart_week == week_key:
            return
        self._weekly_chart_week = week_key
        maybe_write_eow_chart_pack(
            self.output_root,
            INSTRUMENT,
            as_of=wall.date(),
            log=append_progress,
        )

    def flush(self) -> List[Bar]:
        out: List[Bar] = []
        for bar_1m in self.builder_1m.flush():
            self.bars_1m += 1
            self.store.append_bar(bar_1m)
            for bar_15 in self.agg_15m.on_bar(bar_1m):
                self._handle_15m(bar_15)
                out.append(bar_15)
        for bar_15 in self.agg_15m.flush():
            self._handle_15m(bar_15)
            out.append(bar_15)
        self.maybe_poll_changes(force=True)
        return out

    def _handle_15m(self, bar: Bar) -> None:
        self.bars_15m += 1
        self.engine.process_bar(bar)
        self.maybe_poll_changes(force=True)
        append_progress(
            self.output_root,
            "15m bar ts=%s o=%.3f h=%.3f l=%.3f c=%.3f" % (bar.ts, bar.open, bar.high, bar.low, bar.close),
        )

    def _maybe_heartbeat(self) -> None:
        now = time.time()
        if now - self._last_progress_at < PROGRESS_HEARTBEAT_SECONDS:
            return
        self._last_progress_at = now
        open_positions = [
            p for p in self.engine.broker.reconcile_positions() if float(getattr(p, "quantity", 0) or 0) != 0
        ]
        append_progress(
            self.output_root,
            "heartbeat ticks=%d bars_1m=%d bars_15m=%d orders=%d open_positions=%d oanda_fills=%d tag=%s"
            % (
                self.ticks_logged,
                self.bars_1m,
                self.bars_15m,
                len(self.engine.broker.reconcile_orders()),
                len(open_positions),
                self.fills_from_oanda,
                PHASE2_TAG,
            ),
        )


def run_stream_loop(
    *,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    max_ticks: int = 0,
    reconnect_initial_seconds: float = 2.0,
    reconnect_max_seconds: float = 60.0,
) -> int:
    output_root = Path(output_root) if output_root is not None else default_output_root()
    config = config or OandaConfig.from_env()
    config.validate_for_network()
    if str(config.env).lower() != "practice":
        append_progress(output_root, "REFUSING non-practice OANDA_ENV=%s" % config.env)
        return 2

    runner = MondayOrOandaRunner(output_root=output_root, config=config)
    meta = write_run_meta(output_root, config=config)
    pidfile_path(output_root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_progress(
        output_root,
        "STARTED USDJPY Monday OR OANDA practice tag=%s strategy=%s account=%s state=%s pid=%s"
        % (PHASE2_TAG, STRATEGY_ID, config.account_id, state_root_for(output_root), os.getpid()),
    )
    append_progress(
        output_root,
        "RUN_META %s"
        % json.dumps(
            {k: meta[k] for k in ("started_at", "phase2_tag", "oanda_env", "oanda_routing", "allow_live_routing") if k in meta},
            sort_keys=True,
        ),
    )

    signal.signal(signal.SIGINT, runner.request_stop)
    signal.signal(signal.SIGTERM, runner.request_stop)
    runner.bootstrap_reconcile()

    client = runner.client
    oanda_name = config.symbol_for(INSTRUMENT)
    price_ticks = 0
    reconnect_attempt = 0
    backoff = float(reconnect_initial_seconds)
    exit_code = 0

    try:
        while not runner.stop_requested:
            reconnect_attempt += 1
            append_progress(
                output_root,
                "Opening pricing stream attempt=%d instrument=%s host=%s account=%s snapshot=True"
                % (reconnect_attempt, oanda_name, config.stream_hostname(), config.account_id),
            )
            try:
                response = client.pricing_stream([oanda_name], snapshot=True)
                status = int(getattr(response, "status", 0) or 0)
                if status != 200:
                    raise RuntimeError(
                        "pricing stream HTTP status=%s reason=%s"
                        % (response.status, getattr(response, "reason", ""))
                    )
            except Exception as open_exc:
                _log_stream_error(
                    output_root,
                    runner.store,
                    stage="stream_open",
                    exc=open_exc,
                    extra={"attempt": reconnect_attempt, "backoff_seconds": backoff},
                )
                if runner.stop_requested:
                    break
                append_progress(output_root, "RECONNECT sleeping %.1fs after stream_open failure" % backoff)
                _interruptible_sleep(runner, backoff)
                backoff = min(backoff * 2.0, reconnect_max_seconds)
                continue

            append_progress(output_root, "STREAM connected attempt=%d status=200" % reconnect_attempt)
            backoff = float(reconnect_initial_seconds)
            session_ticks = 0
            try:
                for msg_type, msg in response.parts():
                    if runner.stop_requested:
                        break
                    if msg_type == "pricing.PricingHeartbeat" or getattr(msg, "type", None) == "HEARTBEAT":
                        runner.maybe_poll_changes()
                        continue
                    event = {
                        "instrument": getattr(msg, "instrument", oanda_name),
                        "time": getattr(msg, "time", utc_now_iso()),
                        "bids": _price_levels(getattr(msg, "bids", None)),
                        "asks": _price_levels(getattr(msg, "asks", None)),
                        "closeoutBid": getattr(msg, "closeoutBid", None),
                        "closeoutAsk": getattr(msg, "closeoutAsk", None),
                    }
                    bid, ask = bid_ask_from_event(event)
                    mid = mid_price_from_event(event)
                    if bid is None or ask is None:
                        if mid is None:
                            continue
                        half = TICK * 5.0
                        bid = mid - half
                        ask = mid + half
                    ts = str(event.get("time") or utc_now_iso())
                    try:
                        runner.on_price_tick(bid=float(bid), ask=float(ask), mid=mid, ts=ts, quantity=0.0, raw=event)
                    except Exception as tick_exc:
                        _log_stream_error(
                            output_root,
                            runner.store,
                            stage="tick_handle",
                            exc=tick_exc,
                            extra={"event_ts": ts},
                        )
                        continue
                    price_ticks += 1
                    session_ticks += 1
                    if max_ticks and price_ticks >= max_ticks:
                        append_progress(output_root, "max_ticks=%d reached; stopping" % max_ticks)
                        runner.stop_requested = True
                        break
            except Exception as stream_exc:
                _log_stream_error(
                    output_root,
                    runner.store,
                    stage="stream_read",
                    exc=stream_exc,
                    extra={"attempt": reconnect_attempt, "session_ticks": session_ticks, "total_ticks": price_ticks},
                )
                if runner.stop_requested:
                    break
                append_progress(output_root, "RECONNECT sleeping %.1fs after stream_read failure" % backoff)
                _interruptible_sleep(runner, backoff)
                backoff = min(backoff * 2.0, reconnect_max_seconds)
                continue

            if runner.stop_requested:
                break
            append_progress(
                output_root,
                "WARN stream ended without error attempt=%d session_ticks=%d; reconnecting in %.1fs"
                % (reconnect_attempt, session_ticks, backoff),
            )
            _interruptible_sleep(runner, backoff)
            backoff = min(backoff * 2.0, reconnect_max_seconds)
    except Exception as fatal_exc:
        _log_stream_error(output_root, runner.store, stage="fatal", exc=fatal_exc)
        exit_code = 1
    finally:
        runner.flush()
        append_progress(
            output_root,
            "STOPPED ticks=%d bars_1m=%d bars_15m=%d oanda_fills=%d reconnect_attempts=%d"
            % (price_ticks, runner.bars_1m, runner.bars_15m, runner.fills_from_oanda, reconnect_attempt),
        )
        _remove_pidfile(output_root)
    return exit_code


def spawn_daemon(*, output_root: Path, max_ticks: int = 0, oanda_config_path: str = "") -> int:
    from .oanda_v2b_ungated_common import OandaDemoSpec, spawn_daemon as _spawn

    # Reuse spawn helper; pass a dummy spec (only used for typing in common).
    spec = OandaDemoSpec(
        instrument=INSTRUMENT,
        strategy_id=STRATEGY_ID,
        run_dirname=RUN_DIRNAME,
        tick=TICK,
        strategy_type="monday_or_breakout",
    )
    return _spawn(
        spec,
        output_root=output_root,
        cli_command=CLI_COMMAND,
        max_ticks=max_ticks,
        oanda_config_path=oanda_config_path,
    )


def status_daemon(output_root: Path) -> int:
    pid = read_pid(output_root)
    meta = {}
    if run_meta_path(output_root).exists():
        meta = json.loads(run_meta_path(output_root).read_text(encoding="utf-8"))
    if pid is None:
        print("status: not running (no pidfile)")
        return 1
    alive = pid_is_alive(pid)
    print(
        "status: pid=%d alive=%s started_at=%s tag=%s state=%s routing=%s"
        % (
            pid,
            alive,
            meta.get("started_at", "?"),
            meta.get("phase2_tag", PHASE2_TAG),
            meta.get("state_root", state_root_for(output_root)),
            meta.get("oanda_routing", True),
        )
    )
    return 0 if alive else 1


def stop_daemon(output_root: Path) -> int:
    from .oanda_v2b_ungated_common import stop_daemon as _stop

    return _stop(output_root)
