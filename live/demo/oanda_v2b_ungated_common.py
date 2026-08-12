"""Shared runner for ungated v2b OANDA practice demos (real practice orders).

OANDA is order/fill/position truth; local CSVs are an audit mirror via Account Changes.
Paper demos under ``*_v2b_ungated_paper`` are unchanged.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
from . import demo_run_root
from .session_pnl import append_session_result

NY_TZ = pytz.timezone("America/New_York")
RTH_OPEN = dt_time(9, 30)
RTH_CLOSE = dt_time(16, 0)
PROGRESS_HEARTBEAT_SECONDS = 300
ACCOUNT_CHANGES_POLL_SECONDS = 2.0
OANDA_RESULTS_CSV = Path(__file__).resolve().parent / "ungated_oanda_demo.csv"


@dataclass(frozen=True)
class OandaDemoSpec:
    instrument: str
    strategy_id: str
    run_dirname: str
    tick: float
    entry_qty: int = 3
    tp1_qty: int = 1
    tp2_qty: int = 1
    strategy_type: str = "v2b_scaleout"


def default_output_root(spec: OandaDemoSpec) -> Path:
    return demo_run_root(spec.run_dirname)


def state_root_for(output_root: Path) -> Path:
    return output_root / "state"


def progress_path(output_root: Path) -> Path:
    return output_root / "PROGRESS.log"


def run_meta_path(output_root: Path) -> Path:
    return output_root / "RUN_META.json"


def pidfile_path(output_root: Path) -> Path:
    return output_root / "pidfile"


def run_log_path(output_root: Path) -> Path:
    return output_root / "run.log"


def append_progress(output_root: Path, message: str) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    with progress_path(output_root).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ny_wall_time(ts: str) -> datetime:
    dt = parse_oanda_ts(ts)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(NY_TZ)


def is_ny_rth(ts: str) -> bool:
    ny = ny_wall_time(ts)
    clock = ny.time()
    if clock.tzinfo is not None:
        clock = clock.replace(tzinfo=None)
    return RTH_OPEN <= clock < RTH_CLOSE


def strategy_config_payload(spec: OandaDemoSpec) -> Dict[str, Any]:
    return {
        "mode": "oco_then_reverse",
        "entry_qty": spec.entry_qty,
        "tp1_qty": spec.tp1_qty,
        "tp2_qty": spec.tp2_qty,
        "tick_size": spec.tick,
        "rth_start": "09:30",
        "or_end": "09:45",
        "eod_cutoff": "15:59",
        "use_regime_filter": False,
        "prior_opposite_only": False,
        "record_levels": True,
        "paper_only": False,
        "oanda_routing": True,
        "signal_price": "mid",
        "fill_price": "oanda",
    }


def write_run_meta(output_root: Path, *, spec: OandaDemoSpec, config: OandaConfig, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": spec.strategy_id,
        "strategy_type": spec.strategy_type,
        "instrument": spec.instrument,
        "oanda_instrument": config.symbol_for(spec.instrument),
        "sizing": "S_1_1_1",
        "entry_qty": spec.entry_qty,
        "tp1_qty": spec.tp1_qty,
        "tp2_qty": spec.tp2_qty,
        "units_note": "Strategy qty maps 1:1 to OANDA units (tiny practice size).",
        "use_regime_filter": False,
        "prior_opposite_only": False,
        "account_mode": "paper",
        "oanda_routing": True,
        "allow_live_routing": False,
        "oanda_env": config.env,
        "oanda_account_id": config.account_id or DEFAULT_PRIMARY_ACCOUNT,
        "oanda_api_url": config.api_url,
        "oanda_stream_url": config.stream_url,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "note": "OANDA practice order-routing demo: prices + real practice orders; local state mirrors Account Changes.",
    }
    if extra:
        meta.update(extra)
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path, spec: OandaDemoSpec) -> FlatFileStore:
    root = state_root_for(output_root)
    store = FlatFileStore(root)
    store.ensure()
    payload = strategy_config_payload(spec)
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=spec.strategy_id,
                strategy_type=spec.strategy_type,
                version="v1",
                instrument=spec.instrument,
                broker_instrument=spec.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="1m",
                max_contracts=spec.entry_qty,
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_engine(store: FlatFileStore, *, spec: OandaDemoSpec, config: OandaConfig, client: OandaApiClient) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(spec.instrument, spec.tick)
    broker = OandaBroker(
        store,
        config=config,
        client=client,
        allow_live_routing=False,
        authority_strategy_ids=[spec.strategy_id],
    )
    return Engine(
        store=store,
        broker=broker,
        persist_bars=True,
        persist_health=True,
        tick_size={spec.instrument: spec.tick},
        verification_provider=SpoofVerificationProvider(store),
        emit_order_alerts=True,
        broker_log_events=True,
        broker_persist_modifications=True,
        slippage_ticks=0.0,
    )


def poll_account_changes(engine: Engine, client: OandaApiClient, *, instrument: str) -> int:
    """Pull Account Changes; apply fills for this broker and notify strategies.

    Returns number of fills delivered to ``StrategyManager.on_fills``.
    """
    broker = engine.broker
    if not isinstance(broker, OandaBroker):
        return 0
    # Keep remote-order authority scoped to this engine's strategy ids.
    try:
        broker.register_authority_strategies(
            plugin.instance.strategy_id for plugin in engine.manager.plugins.values()
        )
    except Exception:
        pass
    delivered: List = []
    # Immediate create/close fills queued for Engine (also drain here between bars).
    pending = getattr(broker, "_pending_fills", None)
    if pending:
        delivered.extend(list(pending))
        broker._pending_fills = []
    if not broker.last_transaction_id:
        broker.reconcile_from_account_details()
        if delivered:
            local = [f for f in delivered if f.instrument == instrument]
            if local:
                engine.manager.on_fills(local)
            return len(local)
        return 0
    try:
        body = client.account_changes(since_transaction_id=broker.last_transaction_id)
    except Exception as exc:
        engine.store.append_event(
            "reconciliation_events",
            {"event": "oanda_account_changes_error", "error": str(exc), "ts": utc_now_iso()},
        )
        if delivered:
            local = [f for f in delivered if f.instrument == instrument]
            if local:
                engine.manager.on_fills(local)
            return len(local)
        return 0
    fills = broker.apply_account_changes(body)
    delivered.extend(fills)
    # Periodic / deferred gate-off orphan sweep (cancel remote rests not in local open).
    try:
        sweep = broker.maybe_sweep_remote_order_authority()
        if sweep and not sweep.get("skipped") and int(sweep.get("orphans_cancelled") or 0) > 0:
            engine.store.append_event(
                "reconciliation_events",
                {
                    "event": "oanda_remote_authority_sweep",
                    "orphans_cancelled": sweep.get("orphans_cancelled"),
                    "remote_pending": sweep.get("remote_pending"),
                    "local_open": sweep.get("local_open"),
                    "reason": sweep.get("reason"),
                    "ts": utc_now_iso(),
                },
            )
    except Exception as exc:
        engine.store.append_event(
            "reconciliation_events",
            {"event": "oanda_remote_authority_sweep_error", "error": str(exc), "ts": utc_now_iso()},
        )
    local = [f for f in delivered if f.instrument == instrument]
    if local:
        engine.manager.on_fills(local)
    return len(local)


class DemoOandaRunner:
    def __init__(
        self,
        spec: OandaDemoSpec,
        *,
        output_root: Optional[Path] = None,
        store: Optional[FlatFileStore] = None,
        engine: Optional[Engine] = None,
        config: Optional[OandaConfig] = None,
        client: Optional[OandaApiClient] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.spec = spec
        self.output_root = Path(output_root) if output_root is not None else default_output_root(spec)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config = config or OandaConfig.from_env()
        self.store = store or bootstrap_store(self.output_root, spec)
        self.client = client or OandaApiClient(config=self.config, store=self.store)
        self.engine = engine or build_engine(self.store, spec=spec, config=self.config, client=self.client)
        self.builder = QuoteOneMinuteBarBuilder(spec.instrument, source="oanda_demo_quote")
        self._clock = clock or time.time
        self._last_progress_at = 0.0
        self._last_changes_poll_at = 0.0
        self._rth_open_logged = False
        self._rth_close_logged = False
        self._session_day = ""
        self.ticks_logged = 0
        self.bars_persisted = 0
        self.bars_engine = 0
        self.fills_from_oanda = 0
        self.stop_requested = False

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    def bootstrap_reconcile(self) -> None:
        broker = self.engine.broker
        if isinstance(broker, OandaBroker):
            try:
                broker.register_authority_strategy(self.spec.strategy_id)
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
        now = self._clock()
        if (not force) and (now - self._last_changes_poll_at < ACCOUNT_CHANGES_POLL_SECONDS):
            return
        self._last_changes_poll_at = now
        n = poll_account_changes(self.engine, self.client, instrument=self.spec.instrument)
        if n:
            self.fills_from_oanda += n
            append_progress(self.output_root, "OANDA fills applied n=%d total=%d" % (n, self.fills_from_oanda))

    def on_price_tick(
        self,
        *,
        price: Optional[float] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        ts: str,
        quantity: float = 0.0,
        raw: Optional[Dict[str, Any]] = None,
    ) -> List[Bar]:
        if bid is None or ask is None:
            if price is None:
                return []
            half = self.spec.tick * 5.0
            mid = float(price)
            bid = mid - half
            ask = mid + half
        mid = float(price) if price is not None else (float(bid) + float(ask)) / 2.0
        in_rth = is_ny_rth(ts)
        self._maybe_log_session_edges(ts, in_rth)
        if in_rth:
            payload = {
                "type": "price",
                "instrument": self.spec.instrument,
                "oanda_instrument": self.config.symbol_for(self.spec.instrument),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread": float(ask) - float(bid),
                "quantity": quantity,
                "event_ts": ts,
            }
            if raw:
                payload["raw"] = _jsonable(raw)
            day = ny_wall_time(ts).date().isoformat()
            self.store.append_event("rth_ticks/%s" % day, payload)
            self.store.append_event("raw_market_data/oanda/%s" % day, payload)
            self.ticks_logged += 1

        completed = self.builder.on_quote(bid=float(bid), ask=float(ask), mid=mid, quantity=quantity, ts=ts)
        for bar in completed:
            self._handle_completed_bar(bar)
        self.maybe_poll_changes()
        self._maybe_heartbeat()
        return completed

    def flush(self) -> List[Bar]:
        bars = self.builder.flush()
        for bar in bars:
            self._handle_completed_bar(bar)
        self.maybe_poll_changes(force=True)
        return bars

    def _handle_completed_bar(self, bar: Bar) -> None:
        self.bars_persisted += 1
        if is_ny_rth(bar.ts):
            self.engine.process_bar(bar)
            self.bars_engine += 1
            self.maybe_poll_changes(force=True)
        else:
            self.store.append_bar(bar)

    def _maybe_log_session_edges(self, ts: str, in_rth: bool) -> None:
        day = ny_wall_time(ts).date().isoformat()
        if day != self._session_day:
            self._session_day = day
            self._rth_open_logged = False
            self._rth_close_logged = False
        if in_rth and not self._rth_open_logged:
            append_progress(self.output_root, "NY RTH open — tick logging + OANDA routing armed for %s" % day)
            self._rth_open_logged = True
        if (not in_rth) and self._rth_open_logged and not self._rth_close_logged:
            clock = ny_wall_time(ts).time().replace(tzinfo=None)
            if clock >= RTH_CLOSE:
                append_progress(self.output_root, "NY RTH close — strategy idle; feed continues for %s" % day)
                self._rth_close_logged = True
                self.maybe_poll_changes(force=True)
                from .eod_charts import maybe_write_eod_chart
                from ..replay_audit import POINT_VALUES

                maybe_write_eod_chart(
                    self.output_root,
                    self.spec.instrument,
                    session_date=day,
                    point_value=POINT_VALUES.get(self.spec.instrument),
                    log=append_progress,
                )
                try:
                    row = append_session_result(
                        OANDA_RESULTS_CSV,
                        demo=self.spec.instrument,
                        session_date=ny_wall_time(ts).date(),
                        instrument=self.spec.instrument,
                        fills_path=state_root_for(self.output_root) / "fills.csv",
                    )
                    if row:
                        append_progress(
                            self.output_root,
                            "SESSION_PNL wrote %s demo=%s path=%s usd=%s"
                            % (OANDA_RESULTS_CSV.name, row["demo"], row["path"], row["usd"]),
                        )
                except Exception as exc:
                    append_progress(self.output_root, "WARN session PnL append failed: %s" % exc)
                # End-of-week size snapshot for rotation planning (Friday RTH close).
                if ny_wall_time(ts).weekday() == 4:
                    try:
                        from .size_report import append_size_report

                        append_size_report(
                            self.output_root,
                            append_progress,
                            label="weekly_eow",
                            session_date=ny_wall_time(ts).date(),
                        )
                    except Exception as exc:
                        append_progress(self.output_root, "WARN weekly FILE_SIZES failed: %s" % exc)

    def _maybe_heartbeat(self) -> None:
        now = self._clock()
        if now - self._last_progress_at < PROGRESS_HEARTBEAT_SECONDS:
            return
        self._last_progress_at = now
        open_positions = [
            p for p in self.engine.broker.reconcile_positions() if float(getattr(p, "quantity", 0) or 0) != 0
        ]
        pos_qty = sum(float(p.quantity) for p in open_positions)
        append_progress(
            self.output_root,
            "heartbeat ticks_logged=%d bars_persisted=%d bars_engine=%d orders=%d open_positions=%d pos_qty=%s oanda_fills=%d"
            % (
                self.ticks_logged,
                self.bars_persisted,
                self.bars_engine,
                len(self.engine.broker.reconcile_orders()),
                len(open_positions),
                pos_qty,
                self.fills_from_oanda,
            ),
        )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "dict"):
        try:
            return _jsonable(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _format_error(exc: BaseException) -> str:
    import traceback

    tb = traceback.format_exc()
    return "type=%s msg=%r repr=%r\n%s" % (type(exc).__name__, str(exc), exc, tb.rstrip())


def _log_stream_error(output_root: Path, store: FlatFileStore, *, stage: str, exc: BaseException, extra: Optional[Dict[str, Any]] = None) -> None:
    detail = _format_error(exc)
    append_progress(output_root, "ERROR stage=%s %s" % (stage, detail.split("\n", 1)[0]))
    for line in detail.splitlines()[1:]:
        if line.strip():
            append_progress(output_root, "ERROR_TB %s" % line)
    payload = {
        "event": "stream_error",
        "stage": stage,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "error_repr": repr(exc),
        "traceback": detail,
        "ts": utc_now_iso(),
    }
    if extra:
        payload.update(extra)
    store.append_event("stream_errors", payload)


def run_stream_loop(
    spec: OandaDemoSpec,
    *,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    max_ticks: int = 0,
    reconnect_initial_seconds: float = 2.0,
    reconnect_max_seconds: float = 60.0,
) -> int:
    output_root = Path(output_root) if output_root is not None else default_output_root(spec)
    config = config or OandaConfig.from_env()
    config.validate_for_network()
    if str(config.env).lower() != "practice":
        append_progress(output_root, "REFUSING non-practice OANDA_ENV=%s (demo is practice-only)" % config.env)
        return 2

    runner = DemoOandaRunner(spec, output_root=output_root, config=config)
    meta = write_run_meta(output_root, spec=spec, config=config)
    pidfile_path(output_root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_progress(
        output_root,
        "STARTED OANDA practice demo strategy=%s sizing=S_1_1_1 oanda_env=%s account=%s state=%s pid=%s"
        % (spec.strategy_id, config.env, config.account_id, state_root_for(output_root), os.getpid()),
    )
    append_progress(
        output_root,
        "RUN_META %s"
        % json.dumps(
            {
                k: meta[k]
                for k in ("started_at", "oanda_env", "oanda_account_id", "oanda_routing", "allow_live_routing")
                if k in meta
            },
            sort_keys=True,
        ),
    )

    signal.signal(signal.SIGINT, runner.request_stop)
    signal.signal(signal.SIGTERM, runner.request_stop)

    runner.bootstrap_reconcile()
    client = runner.client
    oanda_name = config.symbol_for(spec.instrument)
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
                        "pricing stream HTTP status=%s reason=%s body=%r"
                        % (response.status, getattr(response, "reason", ""), getattr(response, "raw_body", None) or getattr(response, "body", None))
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
                        half = spec.tick * 5.0
                        bid = mid - half
                        ask = mid + half
                    ts = str(event.get("time") or utc_now_iso())
                    try:
                        runner.on_price_tick(bid=float(bid), ask=float(ask), price=mid, ts=ts, quantity=0.0, raw=event)
                    except Exception as tick_exc:
                        _log_stream_error(
                            output_root,
                            runner.store,
                            stage="tick_handle",
                            exc=tick_exc,
                            extra={"event_ts": ts, "bid": bid, "ask": ask, "mid": mid},
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
                    extra={
                        "attempt": reconnect_attempt,
                        "session_ticks": session_ticks,
                        "total_ticks": price_ticks,
                        "bars_persisted": runner.bars_persisted,
                        "bars_engine": runner.bars_engine,
                    },
                )
                if runner.stop_requested:
                    break
                append_progress(
                    output_root,
                    "RECONNECT sleeping %.1fs after stream_read failure (session_ticks=%d total_ticks=%d)"
                    % (backoff, session_ticks, price_ticks),
                )
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
            "STOPPED ticks=%d ticks_logged=%d bars_persisted=%d bars_engine=%d oanda_fills=%d reconnect_attempts=%d"
            % (
                price_ticks,
                runner.ticks_logged,
                runner.bars_persisted,
                runner.bars_engine,
                runner.fills_from_oanda,
                reconnect_attempt,
            ),
        )
        _remove_pidfile(output_root)
    return exit_code


def _interruptible_sleep(runner: DemoOandaRunner, seconds: float) -> None:
    deadline = time.time() + max(0.0, float(seconds))
    while time.time() < deadline:
        if runner.stop_requested:
            return
        time.sleep(min(0.5, deadline - time.time()))


def _remove_pidfile(output_root: Path) -> None:
    path = pidfile_path(output_root)
    if path.exists():
        path.unlink()


def _price_levels(levels: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not levels:
        return out
    for item in levels:
        if hasattr(item, "price"):
            out.append({"price": item.price, "liquidity": getattr(item, "liquidity", None)})
        elif isinstance(item, dict):
            out.append(item)
    return out


def read_pid(output_root: Path) -> Optional[int]:
    path = pidfile_path(output_root)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_daemon(output_root: Path) -> int:
    pid = read_pid(output_root)
    if pid is None:
        append_progress(output_root, "stop: no pidfile")
        print("No pidfile at %s" % pidfile_path(output_root))
        return 1
    if not pid_is_alive(pid):
        print("Process %d not running; removing stale pidfile" % pid)
        if pidfile_path(output_root).exists():
            pidfile_path(output_root).unlink()
        return 0
    os.kill(pid, signal.SIGTERM)
    append_progress(output_root, "stop: sent SIGTERM to pid=%d" % pid)
    print("Sent SIGTERM to %d" % pid)
    return 0


def status_daemon(output_root: Path, *, spec: OandaDemoSpec) -> int:
    pid = read_pid(output_root)
    meta = {}
    if run_meta_path(output_root).exists():
        meta = json.loads(run_meta_path(output_root).read_text(encoding="utf-8"))
    if pid is None:
        print("status: not running (no pidfile)")
        return 1
    alive = pid_is_alive(pid)
    print(
        "status: pid=%d alive=%s started_at=%s state=%s routing=%s"
        % (
            pid,
            alive,
            meta.get("started_at", "?"),
            meta.get("state_root", state_root_for(output_root)),
            meta.get("oanda_routing", True),
        )
    )
    return 0 if alive else 1


def spawn_daemon(
    spec: OandaDemoSpec,
    *,
    output_root: Path,
    cli_command: str,
    max_ticks: int = 0,
    oanda_config_path: str = "",
) -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    existing = read_pid(output_root)
    if existing is not None and pid_is_alive(existing):
        print("Already running as pid %d (see %s)" % (existing, pidfile_path(output_root)))
        return 1

    log_fh = run_log_path(output_root).open("a", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "potions.live.cli",
        "--state-root",
        str(state_root_for(output_root)),
        cli_command,
        "--output-root",
        str(output_root),
    ]
    if max_ticks:
        cmd.extend(["--max-ticks", str(int(max_ticks))])
    if oanda_config_path:
        cmd.extend(["--oanda-config", oanda_config_path])

    env = os.environ.copy()
    repo = Path(__file__).resolve().parents[2]  # .../potions
    hsm = repo.parent
    v20_src = repo / "v20-python" / "src"
    path_bits = [str(hsm), str(v20_src)]
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(path_bits + ([existing_pp] if existing_pp else []))

    import subprocess

    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
        cwd=str(hsm),
    )
    pidfile_path(output_root).write_text(str(proc.pid) + "\n", encoding="utf-8")
    append_progress(output_root, "DAEMON spawned pid=%d run_log=%s" % (proc.pid, run_log_path(output_root)))
    print("Started OANDA practice demo daemon pid=%d (%s)" % (proc.pid, cli_command))
    print("  PROGRESS: %s" % progress_path(output_root))
    print("  run.log:  %s" % run_log_path(output_root))
    print("  state:    %s" % state_root_for(output_root))
    return 0
