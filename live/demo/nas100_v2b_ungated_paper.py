"""NAS100 v2b OCO ungated paper demo: OANDA NAS100_USD prices in, PaperBroker only.

Artifacts live under ``live/demo/nas100_v2b_ungated_paper/`` (parallel to the
EURUSD demo and ``live/state/``). No orders are routed to OANDA.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
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
    OandaConfig,
    QuoteOneMinuteBarBuilder,
    bid_ask_from_event,
    mid_price_from_event,
    parse_oanda_ts,
)
from ..replay_realism import hardened_replay_engine_kwargs
from ..store import FlatFileStore
from ..verification import SpoofVerificationProvider
from . import demo_run_root

INSTRUMENT = "NAS100"
STRATEGY_ID = "nas100_v2b_ungated_demo"
STRATEGY_TYPE = "v2b_scaleout"
ENTRY_QTY = 3
TP1_QTY = 1
TP2_QTY = 1
TICK = 0.1  # OANDA NAS100_USD displayPrecision=1
NY_TZ = pytz.timezone("America/New_York")
RTH_OPEN = dt_time(9, 30)
RTH_CLOSE = dt_time(16, 0)
PROGRESS_HEARTBEAT_SECONDS = 300


def default_output_root() -> Path:
    return demo_run_root("nas100_v2b_ungated_paper")


def state_root_for(output_root: Optional[Path] = None) -> Path:
    return (output_root or default_output_root()) / "state"


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
    """True when ``ts`` falls in NY RTH [09:30, 16:00)."""
    ny = ny_wall_time(ts)
    clock = ny.time()
    if clock.tzinfo is not None:
        clock = clock.replace(tzinfo=None)
    return RTH_OPEN <= clock < RTH_CLOSE


def strategy_config_payload() -> Dict[str, Any]:
    return {
        "mode": "oco_then_reverse",
        "entry_qty": ENTRY_QTY,
        "tp1_qty": TP1_QTY,
        "tp2_qty": TP2_QTY,
        "tick_size": TICK,
        "rth_start": "09:30",
        "or_end": "09:45",
        "eod_cutoff": "15:59",
        "use_regime_filter": False,
        "prior_opposite_only": False,
        "record_levels": True,
        "paper_only": True,
        "oanda_routing": False,
        "signal_price": "mid",
        "fill_price": "bid_ask",
    }


def write_run_meta(output_root: Path, *, config: OandaConfig, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": STRATEGY_ID,
        "strategy_type": STRATEGY_TYPE,
        "instrument": INSTRUMENT,
        "oanda_instrument": config.symbol_for(INSTRUMENT),
        "sizing": "S_1_1_1",
        "entry_qty": ENTRY_QTY,
        "tp1_qty": TP1_QTY,
        "tp2_qty": TP2_QTY,
        "use_regime_filter": False,
        "prior_opposite_only": False,
        "account_mode": "paper",
        "oanda_routing": False,
        "signal_price": "mid",
        "fill_price": "bid_ask",
        "oanda_env": config.env,
        "oanda_account_id": config.account_id or DEFAULT_PRIMARY_ACCOUNT,
        "oanda_api_url": config.api_url,
        "oanda_stream_url": config.stream_url,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "note": "Paper-only demo: OANDA practice stream for prices; PaperBroker for fills. No OANDA order routing.",
    }
    if extra:
        meta.update(extra)
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
                timeframes="1m",
                max_contracts=ENTRY_QTY,
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_engine(store: FlatFileStore) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    # Quote-book bars carry real bid/ask; skip synthetic SpreadModel to avoid double-counting.
    return Engine(
        store=store,
        persist_bars=True,
        persist_health=True,
        tick_size={INSTRUMENT: TICK},
        verification_provider=SpoofVerificationProvider(store),
        emit_order_alerts=True,
        broker_log_events=True,
        broker_persist_modifications=True,
        **hardened_replay_engine_kwargs(slippage_ticks=0.0, spread_model=None),
    )


class DemoPaperRunner:
    """Offline-testable core: feed ticks, gate RTH logs, drive Engine on RTH bars."""

    def __init__(
        self,
        output_root: Optional[Path] = None,
        store: Optional[FlatFileStore] = None,
        engine: Optional[Engine] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.output_root = Path(output_root) if output_root is not None else default_output_root()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.store = store or bootstrap_store(self.output_root)
        self.engine = engine or build_engine(self.store)
        self.builder = QuoteOneMinuteBarBuilder(INSTRUMENT, source="oanda_demo_quote")
        self._clock = clock or time.time
        self._last_progress_at = 0.0
        self._rth_open_logged = False
        self._rth_close_logged = False
        self._session_day = ""
        self.ticks_logged = 0
        self.bars_persisted = 0
        self.bars_engine = 0
        self.stop_requested = False

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

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
        """Handle one quote tick. Mid drives signals; bid/ask OHLC ride on the bar for fills."""
        if bid is None or ask is None:
            if price is None:
                return []
            # Fallback: synthetic 1-tick half-spread around mid if quote sides missing.
            half = TICK * 5.0
            mid = float(price)
            bid = mid - half
            ask = mid + half
        mid = float(price) if price is not None else (float(bid) + float(ask)) / 2.0
        in_rth = is_ny_rth(ts)
        self._maybe_log_session_edges(ts, in_rth)
        if in_rth:
            payload = {
                "type": "price",
                "instrument": INSTRUMENT,
                "oanda_instrument": "EUR_USD",
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
        self._maybe_heartbeat()
        return completed

    def flush(self) -> List[Bar]:
        bars = self.builder.flush()
        for bar in bars:
            self._handle_completed_bar(bar)
        return bars

    def _handle_completed_bar(self, bar: Bar) -> None:
        self.bars_persisted += 1
        if is_ny_rth(bar.ts):
            # Engine.process_bar persists the bar when persist_bars=True.
            self.engine.process_bar(bar)
            self.bars_engine += 1
        else:
            self.store.append_bar(bar)

    def _maybe_log_session_edges(self, ts: str, in_rth: bool) -> None:
        day = ny_wall_time(ts).date().isoformat()
        if day != self._session_day:
            self._session_day = day
            self._rth_open_logged = False
            self._rth_close_logged = False
        if in_rth and not self._rth_open_logged:
            append_progress(self.output_root, "NY RTH open — tick logging + strategy engine armed for %s" % day)
            self._rth_open_logged = True
        if (not in_rth) and self._rth_open_logged and not self._rth_close_logged:
            clock = ny_wall_time(ts).time().replace(tzinfo=None)
            if clock >= RTH_CLOSE:
                append_progress(self.output_root, "NY RTH close — strategy idle; feed continues for %s" % day)
                self._rth_close_logged = True
                from .eod_charts import maybe_write_eod_chart
                from ..replay_audit import POINT_VALUES

                maybe_write_eod_chart(
                    self.output_root,
                    INSTRUMENT,
                    session_date=day,
                    point_value=POINT_VALUES.get(INSTRUMENT),
                    log=append_progress,
                )

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
            "heartbeat ticks_logged=%d bars_persisted=%d bars_engine=%d orders=%d open_positions=%d pos_qty=%s"
            % (
                self.ticks_logged,
                self.bars_persisted,
                self.bars_engine,
                len(self.engine.broker.reconcile_orders()),
                len(open_positions),
                pos_qty,
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
    # Full traceback on following progress lines (readable in PROGRESS.log / run.log)
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
    *,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    max_ticks: int = 0,
    reconnect_initial_seconds: float = 2.0,
    reconnect_max_seconds: float = 60.0,
) -> int:
    """Foreground: stream OANDA practice prices into the demo paper runner.

    Survives transient stream disconnects with exponential backoff reconnect.
    """
    output_root = Path(output_root) if output_root is not None else default_output_root()
    config = config or OandaConfig.from_env()
    config.validate_for_network()

    runner = DemoPaperRunner(output_root=output_root)
    meta = write_run_meta(output_root, config=config)
    pidfile_path(output_root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_progress(
        output_root,
        "STARTED paper demo strategy=%s sizing=S_1_1_1 oanda_env=%s account=%s state=%s pid=%s"
        % (STRATEGY_ID, config.env, config.account_id, state_root_for(output_root), os.getpid()),
    )
    append_progress(
        output_root,
        "RUN_META %s"
        % json.dumps(
            {
                k: meta[k]
                for k in ("started_at", "oanda_env", "oanda_account_id", "use_regime_filter", "signal_price", "fill_price")
                if k in meta
            },
            sort_keys=True,
        ),
    )

    signal.signal(signal.SIGINT, runner.request_stop)
    signal.signal(signal.SIGTERM, runner.request_stop)

    client = OandaApiClient(config=config, store=runner.store)
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

            # Clean end of parts() without exception — unusual for an infinite stream.
            if runner.stop_requested:
                break
            append_progress(
                output_root,
                "WARN stream ended without error attempt=%d session_ticks=%d; reconnecting in %.1fs"
                % (reconnect_attempt, session_ticks, backoff),
            )
            runner.store.append_event(
                "stream_errors",
                {
                    "event": "stream_ended_clean",
                    "attempt": reconnect_attempt,
                    "session_ticks": session_ticks,
                    "ts": utc_now_iso(),
                },
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
            "STOPPED ticks=%d ticks_logged=%d bars_persisted=%d bars_engine=%d reconnect_attempts=%d"
            % (price_ticks, runner.ticks_logged, runner.bars_persisted, runner.bars_engine, reconnect_attempt),
        )
        _remove_pidfile(output_root)
    return exit_code


def _interruptible_sleep(runner: DemoPaperRunner, seconds: float) -> None:
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
        "status: pid=%d alive=%s started_at=%s state=%s"
        % (pid, alive, meta.get("started_at", "?"), meta.get("state_root", state_root_for(output_root)))
    )
    return 0 if alive else 1


def spawn_daemon(
    *,
    output_root: Path,
    max_ticks: int = 0,
    oanda_config_path: str = "",
) -> int:
    """Detach a background child that runs the stream loop; write pidfile from parent after spawn."""
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
        "demo-nas100-v2b-paper",
        "--output-root",
        str(output_root),
    ]
    if max_ticks:
        cmd.extend(["--max-ticks", str(max_ticks)])
    if oanda_config_path:
        cmd.extend(["--oanda-config", oanda_config_path])

    env = os.environ.copy()
    # Workspace layout: potions package at <hsm>/potions → PYTHONPATH=<hsm>
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
    # Child writes pidfile itself; parent also records the spawn pid for immediate status.
    pidfile_path(output_root).write_text(str(proc.pid) + "\n", encoding="utf-8")
    append_progress(output_root, "DAEMON spawned pid=%d run_log=%s" % (proc.pid, run_log_path(output_root)))
    print("Started demo paper daemon pid=%d" % proc.pid)
    print("  PROGRESS: %s" % progress_path(output_root))
    print("  run.log:  %s" % run_log_path(output_root))
    print("  state:    %s" % state_root_for(output_root))
    return 0
