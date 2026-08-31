"""NAS100 v2b clean-break pyramid trail (trail06_m4_e2_out_be) — OANDA practice demo.

Frozen candidate from CFD validation / 1m-fill book (brl_21741b260a28):
  max 4, add every 2 outside bars, trail@0.6→BE + 2R target, soft exit close≤OR high.

Streams practice quotes → 1m → completed **left-label** 5m bars (research parity).
Routes practice orders via ``OandaBroker`` on dedicated account ``-003``.

Artifacts: ``live/demo/nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda/``.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

from ..broker import DEFAULT_TICK_SIZE
from ..engine import Engine
from ..models import Bar, StrategyInstance, as_row, utc_now_iso
from ..oanda import (
    DEFAULT_PRIMARY_ACCOUNT,
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
from . import demo_run_root, next_stream_backoff
from .oanda_daemon_reconcile import (
    containment_bootstrap,
    containment_note_activity,
    containment_on_reconnect,
    containment_poll,
    install_containment,
)
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

INSTRUMENT = "NAS100"
TICK = 0.1
STRATEGY_TYPE = "v2b_clean_break"
STRATEGY_ID = "nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda"
RUN_DIRNAME = "nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda"
CLI_COMMAND = "demo-nas100-clean-break-trail-oanda"
VARIANT = "trail06_m4_e2_out_be"
MAX_QTY = 4
NY = pytz.timezone("America/New_York")


def strategy_config_payload() -> Dict[str, Any]:
    return {
        "variant": VARIANT,
        "entry_qty": 1,
        "required_break_num": 0,
        "stop_mode": "opposite",
        "size_model": "pyramid_outside",
        "max_pyramid_qty": MAX_QTY,
        "pyramid_add_every_n": 2,
        "pyramid_add_mode": "outside",
        "trail_at_frac": 0.6,
        "trail_to": "entry",
        "pyramid_place_2r_target": True,
        "entry_offset_ticks": 2,
        "tick_size": TICK,
        "rth_start": "09:30",
        "or_end": "09:45",
        "eod_cutoff": "15:55",
        "record_levels": True,
        "paper_only": False,
        "oanda_routing": True,
        "parent_run_id": "brl_21741b260a28",
        "frozen_candidate": VARIANT,
    }


class LeftLabelFiveMinuteBarAggregator:
    """1m → 5m with left label / left closed (matches research ``resample(label=left)``).

    Bucket ``:00–:04`` emits completed 5m bar whose ``ts`` is the bucket start.
    """

    def __init__(self, instrument: str, source: str = "oanda_1m_aggregate_left5m"):
        self.instrument = instrument
        self.source = source
        self._bucket_key: Optional[datetime] = None
        self._bars: List[Bar] = []

    def on_bar(self, bar: Bar) -> List[Bar]:
        if bar.timeframe != "1m":
            return []
        dt = parse_oanda_ts(bar.ts)
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        bucket = dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
        emitted: List[Bar] = []
        if self._bucket_key is not None and bucket != self._bucket_key:
            emitted.extend(self._flush_bucket())
            self._bars = []
        self._bucket_key = bucket
        self._bars.append(bar)
        if dt.minute % 5 == 4:
            emitted.extend(self._flush_bucket())
            self._bars = []
            self._bucket_key = None
        return emitted

    def flush(self) -> List[Bar]:
        return self._flush_bucket()

    def _flush_bucket(self) -> List[Bar]:
        if not self._bars or self._bucket_key is None:
            return []
        bars = list(self._bars)
        ts = self._bucket_key.isoformat()
        return [
            Bar(
                instrument=self.instrument,
                timeframe="5m",
                ts=ts,
                open=bars[0].open,
                high=max(b.high for b in bars),
                low=min(b.low for b in bars),
                close=bars[-1].close,
                volume=sum(b.volume for b in bars),
                complete=True,
                source=self.source,
            )
        ]


def default_output_root() -> Path:
    return demo_run_root(RUN_DIRNAME)


def write_run_meta(output_root: Path, *, config: OandaConfig) -> Dict[str, Any]:
    payload = strategy_config_payload()
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": STRATEGY_ID,
        "strategy_type": STRATEGY_TYPE,
        "variant": VARIANT,
        "instrument": INSTRUMENT,
        "oanda_instrument": config.symbol_for(INSTRUMENT),
        "tick_size": TICK,
        "timeframe": "5m",
        "max_pyramid_qty": MAX_QTY,
        "account_mode": "paper",
        "oanda_routing": True,
        "allow_live_routing": False,
        "oanda_env": config.env,
        "oanda_account_id": config.account_id or DEFAULT_PRIMARY_ACCOUNT,
        "oanda_api_url": config.api_url,
        "oanda_stream_url": config.stream_url,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "parent_run_id": "brl_21741b260a28",
        "note": "NAS100 clean-break pyramid trail OANDA practice; left-label 5m; replaces Fair US30 on -003.",
        "config": payload,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path) -> FlatFileStore:
    root = state_root_for(output_root)
    store = FlatFileStore(root)
    store.ensure()
    payload = strategy_config_payload()
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=STRATEGY_ID,
                strategy_type=STRATEGY_TYPE,
                version="v1",
                instrument=INSTRUMENT,
                broker_instrument=INSTRUMENT,
                account_mode="paper",
                enabled=True,
                timeframes="5m",
                max_contracts=MAX_QTY,
                max_open_orders=32,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_engine(store: FlatFileStore, *, config: OandaConfig, client: OandaApiClient) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    from ..supervisor import RuntimeSupervisor

    supervisor = RuntimeSupervisor(store, provider="oanda")
    broker = OandaBroker(
        store,
        config=config,
        client=client,
        allow_live_routing=False,
        supervisor=supervisor,
        authority_strategy_ids=[STRATEGY_ID],
        position_scope_instruments=[INSTRUMENT],
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


class Runner:
    def __init__(self, *, output_root: Path, config: OandaConfig):
        self.output_root = output_root
        self.config = config
        self.store = bootstrap_store(output_root)
        self.client = OandaApiClient(config=config, store=self.store)
        self.engine = build_engine(self.store, config=config, client=self.client)
        self.builder_1m = QuoteOneMinuteBarBuilder(INSTRUMENT, source="oanda_clean_break_quote")
        self.agg_5m = LeftLabelFiveMinuteBarAggregator(INSTRUMENT)
        self._last_progress_at = 0.0
        self._last_changes_poll_at = 0.0
        self.ticks_logged = 0
        self.bars_1m = 0
        self.bars_5m = 0
        self.fills_from_oanda = 0
        self.stop_requested = False
        install_containment(
            self,
            instrument=INSTRUMENT,
            strategy_id=STRATEGY_ID,
            strategy_type=STRATEGY_TYPE,
            entry_qty=float(MAX_QTY),
        )

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
        containment_bootstrap(self, append_progress_fn=append_progress)

    def maybe_poll_changes(self, *, force: bool = False) -> None:
        now = time.time()
        if (not force) and (now - self._last_changes_poll_at < ACCOUNT_CHANGES_POLL_SECONDS):
            return
        self._last_changes_poll_at = now
        n = poll_account_changes(self.engine, self.client, instrument=INSTRUMENT)
        if n:
            self.fills_from_oanda += n
            append_progress(self.output_root, "OANDA fills applied n=%d total=%d" % (n, self.fills_from_oanda))
        containment_poll(self, append_progress_fn=append_progress)

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
        self.store.append_event("rth_ticks/%s" % day, payload)
        self.ticks_logged += 1
        containment_note_activity(self)

        completed_5: List[Bar] = []
        for bar_1m in self.builder_1m.on_quote(bid=float(bid), ask=float(ask), mid=mid_px, quantity=quantity, ts=ts):
            self.bars_1m += 1
            self.store.append_bar(bar_1m)
            for bar_5 in self.agg_5m.on_bar(bar_1m):
                self._handle_5m(bar_5)
                completed_5.append(bar_5)
        self.maybe_poll_changes()
        self._maybe_heartbeat()
        return completed_5

    def flush(self) -> List[Bar]:
        out: List[Bar] = []
        for bar_1m in self.builder_1m.flush():
            self.bars_1m += 1
            self.store.append_bar(bar_1m)
            for bar_5 in self.agg_5m.on_bar(bar_1m):
                self._handle_5m(bar_5)
                out.append(bar_5)
        for bar_5 in self.agg_5m.flush():
            self._handle_5m(bar_5)
            out.append(bar_5)
        self.maybe_poll_changes(force=True)
        return out

    def _handle_5m(self, bar: Bar) -> None:
        self.bars_5m += 1
        self.engine.process_bar(bar)
        self.maybe_poll_changes(force=True)
        append_progress(
            self.output_root,
            "5m bar ts=%s o=%.2f h=%.2f l=%.2f c=%.2f" % (bar.ts, bar.open, bar.high, bar.low, bar.close),
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
            "heartbeat ticks=%d bars_1m=%d bars_5m=%d orders=%d open_positions=%d oanda_fills=%d variant=%s"
            % (
                self.ticks_logged,
                self.bars_1m,
                self.bars_5m,
                len(self.engine.broker.reconcile_orders()),
                len(open_positions),
                self.fills_from_oanda,
                VARIANT,
            ),
        )


def run_stream_loop(*, output_root: Optional[Path] = None, config: Optional[OandaConfig] = None, max_ticks: int = 0) -> int:
    output_root = Path(output_root) if output_root is not None else default_output_root()
    output_root.mkdir(parents=True, exist_ok=True)
    config = config or OandaConfig.from_env()
    runner = Runner(output_root=output_root, config=config)
    write_run_meta(output_root, config=config)
    pidfile_path(output_root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_progress(
        output_root,
        "STARTED NAS100 clean-break trail OANDA practice variant=%s strategy=%s account=%s state=%s pid=%s"
        % (VARIANT, STRATEGY_ID, config.account_id, state_root_for(output_root), os.getpid()),
    )

    signal.signal(signal.SIGINT, runner.request_stop)
    signal.signal(signal.SIGTERM, runner.request_stop)
    runner.bootstrap_reconcile()

    client = runner.client
    oanda_name = config.symbol_for(INSTRUMENT)
    price_ticks = 0
    reconnect_attempt = 0
    reconnect_initial_seconds = 2.0
    reconnect_max_seconds = 60.0
    backoff = float(reconnect_initial_seconds)
    exit_code = 0

    try:
        while not runner.stop_requested:
            reconnect_attempt += 1
            append_progress(
                output_root,
                "Opening pricing stream attempt=%d instrument=%s host=%s account=%s"
                % (reconnect_attempt, oanda_name, config.stream_hostname(), config.account_id),
            )
            try:
                response = client.pricing_stream([oanda_name], snapshot=True)
                status = int(getattr(response, "status", 0) or 0)
                if status != 200:
                    raise RuntimeError("pricing stream HTTP status=%s" % response.status)
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
                backoff = next_stream_backoff(backoff, reconnect_max_seconds, open_exc)
                continue

            append_progress(output_root, "STREAM connected attempt=%d status=200" % reconnect_attempt)
            backoff = float(reconnect_initial_seconds)
            session_ticks = 0
            if reconnect_attempt > 1:
                containment_on_reconnect(runner, append_progress_fn=append_progress)
            try:
                for msg_type, msg in response.parts():
                    if runner.stop_requested:
                        break
                    if msg_type == "pricing.PricingHeartbeat" or getattr(msg, "type", None) == "HEARTBEAT":
                        containment_note_activity(runner)
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
                    extra={"attempt": reconnect_attempt, "session_ticks": session_ticks},
                )
                if runner.stop_requested:
                    break
                append_progress(output_root, "RECONNECT sleeping %.1fs after stream_read failure" % backoff)
                _interruptible_sleep(runner, backoff)
                backoff = next_stream_backoff(backoff, reconnect_max_seconds, stream_exc)
                continue

            if runner.stop_requested:
                break
            append_progress(
                output_root,
                "WARN stream ended without error attempt=%d session_ticks=%d; reconnecting in %.1fs"
                % (reconnect_attempt, session_ticks, backoff),
            )
            _interruptible_sleep(runner, backoff)
            backoff = next_stream_backoff(backoff, reconnect_max_seconds)
    except Exception as fatal_exc:
        _log_stream_error(output_root, runner.store, stage="fatal", exc=fatal_exc)
        exit_code = 1
    finally:
        runner.flush()
        append_progress(
            output_root,
            "STOPPED ticks=%d bars_1m=%d bars_5m=%d oanda_fills=%d reconnect_attempts=%d"
            % (price_ticks, runner.bars_1m, runner.bars_5m, runner.fills_from_oanda, reconnect_attempt),
        )
        _remove_pidfile(output_root)
    return exit_code


def spawn_daemon(*, output_root: Path, max_ticks: int = 0, oanda_config_path: str = "") -> int:
    from .oanda_v2b_ungated_common import OandaDemoSpec, spawn_daemon as _spawn

    spec = OandaDemoSpec(
        instrument=INSTRUMENT,
        strategy_id=STRATEGY_ID,
        run_dirname=RUN_DIRNAME,
        tick=TICK,
        entry_qty=MAX_QTY,
        strategy_type=STRATEGY_TYPE,
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
        "status: pid=%d alive=%s started_at=%s variant=%s state=%s routing=%s account=%s"
        % (
            pid,
            alive,
            meta.get("started_at", "?"),
            meta.get("variant", VARIANT),
            meta.get("state_root", state_root_for(output_root)),
            meta.get("oanda_routing", True),
            meta.get("oanda_account_id", "?"),
        )
    )
    return 0 if alive else 1


def stop_daemon(output_root: Path) -> int:
    from .oanda_v2b_ungated_common import stop_daemon as _stop

    return _stop(output_root)
