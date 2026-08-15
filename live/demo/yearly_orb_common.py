"""Yearly ORB scaleout3 demos — daily-bar paper + OANDA practice.

Promotable FX / metals / CFD sleeves (banked N/S):

- AUDJPY 15.26, XAUUSD 11.30, EURUSD 8.31, XAGUSD 6.21, US30 3.56

Account: ``101-002-39860312-002`` (yearly practice book).

Warm-start: local ``fx/<sym>_daily.csv`` + OANDA ``D`` candles for any gap.
Paper replays history then polls for new complete daily bars. OANDA warm-starts
YOR state on PaperBroker (no historical practice orders), clears open paper
positions/orders, then routes only **new** daily closes through OandaBroker.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..broker import DEFAULT_TICK_SIZE
from ..engine import Engine, bars_from_csv
from ..models import Bar, StrategyInstance, as_row, utc_now_iso
from ..oanda import (
    DEFAULT_SECONDARY_ACCOUNT,
    OandaApiClient,
    OandaBroker,
    OandaConfig,
    parse_oanda_ts,
)
from ..replay_realism import hardened_replay_engine_kwargs
from ..store import FlatFileStore
from ..verification import SpoofVerificationProvider
from . import DEMO_ROOT, demo_run_root

REPO = Path(__file__).resolve().parents[2]
YEARLY_ACCOUNT = DEFAULT_SECONDARY_ACCOUNT
POLL_SECONDS = 300
PROGRESS_HEARTBEAT_SECONDS = 300


@dataclass(frozen=True)
class YearlyOrbSpec:
    instrument: str
    tick: float
    n_s_banked: float
    note: str
    batch_qty: int = 1
    local_daily: Optional[Path] = None

    @property
    def strategy_id_paper(self) -> str:
        return "%s_yearly_orb_paper" % self.instrument.lower()

    @property
    def strategy_id_oanda(self) -> str:
        return "%s_yearly_orb_oanda" % self.instrument.lower()

    @property
    def run_dirname_paper(self) -> str:
        return "%s_yearly_orb_paper" % self.instrument.lower()

    @property
    def run_dirname_oanda(self) -> str:
        return "%s_yearly_orb_oanda" % self.instrument.lower()

    def daily_csv(self) -> Path:
        if self.local_daily is not None:
            return self.local_daily
        return REPO / "fx" / ("%s_daily.csv" % self.instrument.lower())


# Promotable N/S only (FX / metals / CFDs). Skip NAS100/SPX — no banked yearly N/S.
SPECS: Dict[str, YearlyOrbSpec] = {
    "AUDJPY": YearlyOrbSpec("AUDJPY", 0.001, 15.26, "FX top4 #1"),
    "XAUUSD": YearlyOrbSpec("XAUUSD", 0.01, 11.30, "metals yearly leader"),
    "EURUSD": YearlyOrbSpec("EURUSD", 0.00001, 8.31, "overnight sweep yearly"),
    "XAGUSD": YearlyOrbSpec("XAGUSD", 0.001, 6.21, "metals #2"),
    "US30": YearlyOrbSpec("US30", 0.1, 3.56, "US30 CFD gambit #2"),
}


def spec_for(instrument: str) -> YearlyOrbSpec:
    key = instrument.upper().replace("/", "").replace("_", "")
    if key not in SPECS:
        raise KeyError("Unknown yearly ORB demo instrument %s (have %s)" % (instrument, ",".join(SPECS)))
    return SPECS[key]


def default_output_root(spec: YearlyOrbSpec, *, oanda: bool) -> Path:
    return demo_run_root(spec.run_dirname_oanda if oanda else spec.run_dirname_paper)


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


def strategy_config_payload(spec: YearlyOrbSpec, *, oanda_routing: bool) -> Dict[str, Any]:
    return {
        "or_start_month": 1,
        "or_end_month": 3,
        "trade_start_month": 4,
        "trade_end_month": 12,
        "batch_qty": spec.batch_qty,
        "tp25_frac": 0.25,
        "tp_full_mult": 1.0,
        "require_fresh_break": True,
        "entry_mode": "limit_retest",
        "delivery_scalein": False,
        "tick_size": spec.tick,
        "paper_only": not oanda_routing,
        "oanda_routing": oanda_routing,
        "yearly_account": YEARLY_ACCOUNT,
        "n_s_banked": spec.n_s_banked,
        "note": spec.note,
    }


def yearly_config(environ: Optional[Dict[str, str]] = None) -> OandaConfig:
    """OANDA config forced onto the yearly practice account (-002)."""
    env = dict(environ if environ is not None else os.environ)
    env["OANDA_ACCOUNT_ID"] = YEARLY_ACCOUNT
    # Prefer demo/.env if shell lacks token.
    dotenv = DEMO_ROOT / ".env"
    if dotenv.exists() and not env.get("OANDA_TOKEN"):
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        env["OANDA_ACCOUNT_ID"] = YEARLY_ACCOUNT
    return OandaConfig.from_env(env)


def write_run_meta(
    output_root: Path,
    *,
    spec: YearlyOrbSpec,
    config: OandaConfig,
    oanda_routing: bool,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": spec.strategy_id_oanda if oanda_routing else spec.strategy_id_paper,
        "strategy_type": "yearly_orb_scaleout3",
        "instrument": spec.instrument,
        "oanda_instrument": config.symbol_for(spec.instrument),
        "batch_qty": spec.batch_qty,
        "n_s_banked": spec.n_s_banked,
        "account_mode": "live" if oanda_routing else "paper",
        "oanda_routing": oanda_routing,
        "oanda_env": config.env,
        "oanda_account_id": YEARLY_ACCOUNT,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "note": "Yearly ORB daily demo on practice account -002.",
    }
    if extra:
        meta.update(extra)
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path, spec: YearlyOrbSpec, *, oanda_routing: bool) -> FlatFileStore:
    root = state_root_for(output_root)
    store = FlatFileStore(root)
    store.ensure()
    sid = spec.strategy_id_oanda if oanda_routing else spec.strategy_id_paper
    payload = strategy_config_payload(spec, oanda_routing=oanda_routing)
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=sid,
                strategy_type="yearly_orb_scaleout3",
                version="v1",
                instrument=spec.instrument,
                broker_instrument=spec.instrument,
                account_mode="live" if oanda_routing else "paper",
                enabled=True,
                timeframes="D",
                max_contracts=max(3, spec.batch_qty * 3),
                max_open_orders=24,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_paper_engine(store: FlatFileStore, *, spec: YearlyOrbSpec) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(spec.instrument, spec.tick)
    return Engine(
        store=store,
        persist_bars=True,
        persist_health=True,
        tick_size={spec.instrument: spec.tick},
        verification_provider=SpoofVerificationProvider(store),
        emit_order_alerts=True,
        broker_log_events=True,
        broker_persist_modifications=True,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=None),
    )


def build_oanda_engine(store: FlatFileStore, *, spec: YearlyOrbSpec, config: OandaConfig, client: OandaApiClient) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(spec.instrument, spec.tick)
    broker = OandaBroker(
        store, config=config, client=client, allow_live_routing=False,
        authority_strategy_ids=[spec.strategy_id_oanda],
        position_scope_instruments=[spec.instrument],
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


def _candle_to_bar(instrument: str, candle: Dict[str, Any], *, source: str) -> Optional[Bar]:
    if not candle.get("complete"):
        return None
    mid = candle.get("mid") or candle.get("bid") or candle.get("ask") or {}
    try:
        ts_raw = str(candle.get("time") or "")
        dt = parse_oanda_ts(ts_raw)
        # OANDA D candle ``time`` is the bucket start (often 21:00 UTC prior evening).
        # Label the bar by the UTC calendar date of that timestamp's *close* side (+1 day
        # when hour>=21 matches FX daily convention used in local fx/*_daily.csv).
        day = dt.astimezone(timezone.utc).date()
        if dt.astimezone(timezone.utc).hour >= 21:
            day = day + timedelta(days=1)
        return Bar(
            instrument=instrument,
            timeframe="D",
            ts=day.isoformat(),
            open=float(mid["o"]),
            high=float(mid["h"]),
            low=float(mid["l"]),
            close=float(mid["c"]),
            volume=float(candle.get("volume") or 0.0),
            complete=True,
            source=source,
        )
    except Exception:
        return None


def fetch_oanda_daily(
    client: OandaApiClient,
    config: OandaConfig,
    instrument: str,
    *,
    from_day: Optional[date] = None,
    count: Optional[int] = None,
) -> List[Bar]:
    oanda_name = config.symbol_for(instrument)
    kwargs: Dict[str, Any] = {"granularity": "D", "price": "M"}
    if from_day is not None:
        kwargs["fromTime"] = "%sT00:00:00.000000000Z" % from_day.isoformat()
        kwargs["toTime"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
    elif count is not None:
        kwargs["count"] = int(count)
    else:
        kwargs["count"] = 500
    body = client.candles(oanda_name, **kwargs)
    out: List[Bar] = []
    for c in body.get("candles") or []:
        bar = _candle_to_bar(instrument, c, source="oanda_D")
        if bar is not None:
            out.append(bar)
    return out


def load_merged_daily(
    spec: YearlyOrbSpec,
    client: OandaApiClient,
    config: OandaConfig,
    *,
    output_root: Path,
) -> Tuple[List[Bar], str]:
    """Local CSV + OANDA gap. Returns (bars, status_note). Skips instrument if no data."""
    local_path = spec.daily_csv()
    local: List[Bar] = []
    if local_path.exists():
        local = bars_from_csv(local_path, spec.instrument, "D", source=str(local_path))
        append_progress(output_root, "local daily %s bars=%d last=%s" % (spec.instrument, len(local), local[-1].ts if local else "-"))
    else:
        append_progress(output_root, "WARN no local daily at %s" % local_path)

    last_local: Optional[date] = None
    if local:
        try:
            last_local = date.fromisoformat(str(local[-1].ts)[:10])
        except ValueError:
            last_local = None

    remote: List[Bar] = []
    try:
        if last_local is None:
            remote = fetch_oanda_daily(client, config, spec.instrument, count=5000)
        else:
            # Overlap 5 days to absorb weekend/holiday gaps.
            remote = fetch_oanda_daily(client, config, spec.instrument, from_day=last_local - timedelta(days=5))
        append_progress(
            output_root,
            "oanda daily %s fetched=%d last=%s"
            % (spec.instrument, len(remote), remote[-1].ts if remote else "-"),
        )
    except Exception as exc:
        append_progress(output_root, "oanda daily FETCH FAIL %s: %s" % (spec.instrument, exc))
        if not local:
            return [], "no_local_no_oanda"
        return local, "local_only_oanda_fail"

    by_day: Dict[str, Bar] = {}
    for b in local:
        by_day[str(b.ts)[:10]] = b
    for b in remote:
        by_day[str(b.ts)[:10]] = b  # OANDA wins on overlap (fresher)
    merged = [by_day[k] for k in sorted(by_day)]
    if not merged:
        return [], "empty"
    return merged, "merged"


def _strip_open_book(store: FlatFileStore, output_root: Path) -> None:
    """After paper warm-start for OANDA: drop paper fills/orders/positions; keep strategy_state YOR."""
    # Cancel/zero tables that would confuse OandaBroker.
    for table in ("orders", "order_intents", "positions", "fills"):
        path = store.root / ("%s.csv" % table)
        if path.exists():
            # Rewrite header-only if present.
            text = path.read_text(encoding="utf-8")
            header = text.splitlines()[0] if text.strip() else ""
            if header:
                path.write_text(header + "\n", encoding="utf-8")
    # Clear active trade fields but keep YOR levels in strategy_state.
    state_path = store.root / "strategy_state.csv"
    if state_path.exists():
        import csv

        rows = list(csv.DictReader(state_path.open(encoding="utf-8")))
        if rows:
            fieldnames = list(rows[0].keys())
            for row in rows:
                raw = row.get("state_json") or row.get("state") or "{}"
                try:
                    st = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                st["active_trade_id"] = ""
                st["active_entry"] = None
                st["active_tp"] = None
                st["active_direction"] = ""
                st["full_tp_seen"] = "false"
                st["base_remaining_qty"] = 0
                st["delivery_trade_id"] = ""
                key = "state_json" if "state_json" in row else "state"
                row[key] = json.dumps(st, sort_keys=True)
            with state_path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
    append_progress(output_root, "OANDA warm-start: cleared paper book; kept YOR strategy_state")


def warm_start(
    engine: Engine,
    bars: Sequence[Bar],
    *,
    output_root: Path,
    hold_out_last: bool = True,
) -> Optional[str]:
    """Replay historical daily bars. Returns last processed day (ISO)."""
    if not bars:
        return None
    # Hold out the most recent complete day so the live poll loop owns "today's close" once.
    use = list(bars[:-1]) if hold_out_last and len(bars) > 1 else list(bars)
    append_progress(output_root, "warm-start replaying %d daily bars (%s → %s)" % (len(use), use[0].ts, use[-1].ts))
    n = 0
    for bar in use:
        engine.process_bar(bar)
        n += 1
        if n % 500 == 0:
            append_progress(output_root, "  warm-start %d/%d" % (n, len(use)))
    last = str(use[-1].ts)[:10]
    append_progress(output_root, "warm-start done last_day=%s" % last)
    return last


def read_pid(output_root: Path) -> Optional[int]:
    path = pidfile_path(output_root)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip().splitlines()[0])
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
        print("No pidfile at %s" % pidfile_path(output_root))
        return 1
    if not pid_is_alive(pid):
        print("Process %d not running; removing stale pidfile" % pid)
        pidfile_path(output_root).unlink(missing_ok=True)  # type: ignore[arg-type]
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
        print("status: not running (no pidfile) root=%s" % output_root)
        return 1
    alive = pid_is_alive(pid)
    print(
        "status: pid=%d alive=%s instrument=%s account=%s routing=%s state=%s"
        % (
            pid,
            alive,
            meta.get("instrument", "?"),
            meta.get("oanda_account_id", "?"),
            meta.get("oanda_routing", "?"),
            meta.get("state_root", state_root_for(output_root)),
        )
    )
    return 0 if alive else 1


class YearlyOrbDailyRunner:
    def __init__(
        self,
        spec: YearlyOrbSpec,
        *,
        output_root: Path,
        oanda_routing: bool,
        config: Optional[OandaConfig] = None,
    ):
        self.spec = spec
        self.output_root = output_root
        self.oanda_routing = oanda_routing
        self.config = config or yearly_config()
        self.store = bootstrap_store(output_root, spec, oanda_routing=oanda_routing)
        self.client = OandaApiClient(config=self.config, store=self.store)
        self.stop_requested = False
        self.last_day: Optional[str] = None
        self.bars_seen = 0
        self._last_progress_at = 0.0
        if oanda_routing:
            # Warm on paper first inside run_loop, then swap broker.
            self.engine = build_paper_engine(self.store, spec=spec)
        else:
            self.engine = build_paper_engine(self.store, spec=spec)

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    def _heartbeat(self) -> None:
        now = time.time()
        if now - self._last_progress_at < PROGRESS_HEARTBEAT_SECONDS:
            return
        self._last_progress_at = now
        open_pos = [p for p in self.engine.broker.reconcile_positions() if float(getattr(p, "quantity", 0) or 0) != 0]
        append_progress(
            self.output_root,
            "heartbeat bars=%d last_day=%s open_positions=%d orders=%d routing=%s"
            % (
                self.bars_seen,
                self.last_day,
                len(open_pos),
                len(self.engine.broker.reconcile_orders()),
                self.oanda_routing,
            ),
        )

    def _poll_new_daily(self) -> List[Bar]:
        try:
            remote = fetch_oanda_daily(self.client, self.config, self.spec.instrument, count=10)
        except Exception as exc:
            append_progress(self.output_root, "poll FAIL: %s" % exc)
            return []
        fresh: List[Bar] = []
        for bar in remote:
            day = str(bar.ts)[:10]
            if self.last_day and day <= self.last_day:
                continue
            fresh.append(bar)
        return fresh

    def run(self, *, max_polls: int = 0) -> int:
        self.output_root.mkdir(parents=True, exist_ok=True)
        write_run_meta(self.output_root, spec=self.spec, config=self.config, oanda_routing=self.oanda_routing)
        pidfile_path(self.output_root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
        append_progress(
            self.output_root,
            "STARTED yearly_orb %s routing=%s account=%s pid=%s"
            % (self.spec.instrument, self.oanda_routing, self.config.account_id, os.getpid()),
        )
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)

        bars, status = load_merged_daily(self.spec, self.client, self.config, output_root=self.output_root)
        if not bars:
            append_progress(self.output_root, "SKIP %s — no usable daily data (%s)" % (self.spec.instrument, status))
            pidfile_path(self.output_root).unlink(missing_ok=True)  # type: ignore[arg-type]
            return 3

        # Always warm-start on PaperBroker path first.
        paper_engine = build_paper_engine(self.store, spec=self.spec)
        self.engine = paper_engine
        self.last_day = warm_start(paper_engine, bars, output_root=self.output_root, hold_out_last=True)
        self.bars_seen = max(0, len(bars) - 1)

        if self.oanda_routing:
            _strip_open_book(self.store, self.output_root)
            self.engine = build_oanda_engine(self.store, spec=self.spec, config=self.config, client=self.client)
            try:
                broker = self.engine.broker
                if isinstance(broker, OandaBroker):
                    broker.reconcile_from_account_details()
                    append_progress(
                        self.output_root,
                        "OANDA reconcile lastTx=%s" % getattr(broker, "last_transaction_id", None),
                    )
            except Exception as exc:
                append_progress(self.output_root, "WARN oanda reconcile: %s" % exc)

        # Process any held-out / new complete days immediately.
        for bar in self._poll_new_daily():
            if self.stop_requested:
                break
            day = str(bar.ts)[:10]
            append_progress(self.output_root, "PROCESS daily %s close=%.6f" % (day, bar.close))
            self.engine.process_bar(bar)
            self.last_day = day
            self.bars_seen += 1

        polls = 0
        while not self.stop_requested:
            if max_polls and polls >= max_polls:
                break
            self._heartbeat()
            time.sleep(POLL_SECONDS)
            polls += 1
            for bar in self._poll_new_daily():
                if self.stop_requested:
                    break
                day = str(bar.ts)[:10]
                append_progress(self.output_root, "PROCESS daily %s close=%.6f" % (day, bar.close))
                self.engine.process_bar(bar)
                self.last_day = day
                self.bars_seen += 1
                if self.oanda_routing:
                    broker = self.engine.broker
                    if isinstance(broker, OandaBroker):
                        try:
                            # Drain account changes after daily intents.
                            if broker.last_transaction_id:
                                body = self.client.account_changes(since_transaction_id=broker.last_transaction_id)
                                fills = broker.apply_account_changes(body)
                                if fills:
                                    self.engine.manager.on_fills(fills)
                        except Exception as exc:
                            append_progress(self.output_root, "WARN account_changes: %s" % exc)

        append_progress(self.output_root, "STOPPED bars=%d last_day=%s" % (self.bars_seen, self.last_day))
        if pidfile_path(self.output_root).exists():
            pidfile_path(self.output_root).unlink()
        return 0


def run_loop(
    instrument: str,
    *,
    oanda_routing: bool,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    max_polls: int = 0,
) -> int:
    spec = spec_for(instrument)
    root = Path(output_root) if output_root is not None else default_output_root(spec, oanda=oanda_routing)
    cfg = config or yearly_config()
    if str(cfg.account_id) != YEARLY_ACCOUNT:
        cfg = OandaConfig(
            env=cfg.env,
            api_url=cfg.api_url,
            stream_url=cfg.stream_url,
            token=cfg.token,
            account_id=YEARLY_ACCOUNT,
            instrument_map=dict(cfg.instrument_map),
            application=cfg.application,
        )
    if str(cfg.env).lower() != "practice":
        append_progress(root, "REFUSING non-practice OANDA_ENV=%s" % cfg.env)
        return 2
    runner = YearlyOrbDailyRunner(spec, output_root=root, oanda_routing=oanda_routing, config=cfg)
    return runner.run(max_polls=max_polls)


def spawn_daemon(
    instrument: str,
    *,
    oanda_routing: bool,
    output_root: Optional[Path] = None,
    max_polls: int = 0,
    cli_command: str,
) -> int:
    spec = spec_for(instrument)
    root = Path(output_root) if output_root is not None else default_output_root(spec, oanda=oanda_routing)
    root.mkdir(parents=True, exist_ok=True)
    existing = read_pid(root)
    if existing is not None and pid_is_alive(existing):
        print("Already running as pid %d (%s)" % (existing, root))
        return 1
    log_fh = run_log_path(root).open("a", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "potions.live.cli",
        cli_command,
        "--instrument",
        spec.instrument,
        "--output-root",
        str(root),
    ]
    if max_polls:
        cmd.extend(["--max-polls", str(int(max_polls))])
    env = os.environ.copy()
    hsm = REPO.parent
    v20_src = REPO / "v20-python" / "src"
    env["PYTHONPATH"] = os.pathsep.join([str(hsm), str(v20_src)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["OANDA_ACCOUNT_ID"] = YEARLY_ACCOUNT
    # Load demo .env into child.
    dotenv = DEMO_ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        env["OANDA_ACCOUNT_ID"] = YEARLY_ACCOUNT

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
    pidfile_path(root).write_text(str(proc.pid) + "\n", encoding="utf-8")
    append_progress(root, "DAEMON spawned pid=%d cmd=%s" % (proc.pid, cli_command))
    print("Started yearly ORB daemon pid=%d instrument=%s routing=%s" % (proc.pid, spec.instrument, oanda_routing))
    print("  PROGRESS: %s" % progress_path(root))
    print("  state:    %s" % state_root_for(root))
    return 0


def probe_data(instruments: Optional[Sequence[str]] = None) -> List[Tuple[str, bool, str]]:
    """Return (instrument, ok, detail) for each candidate."""
    cfg = yearly_config()
    client = OandaApiClient(config=cfg)
    out: List[Tuple[str, bool, str]] = []
    keys = [i.upper() for i in instruments] if instruments else list(SPECS.keys())
    for key in keys:
        spec = spec_for(key)
        local = spec.daily_csv()
        local_ok = local.exists()
        try:
            remote = fetch_oanda_daily(client, cfg, spec.instrument, count=3)
            remote_ok = bool(remote)
            detail = "local=%s remote_last=%s" % (
                local_ok and (bars_from_csv(local, spec.instrument, "D")[-1].ts if local_ok else False),
                remote[-1].ts if remote else None,
            )
            out.append((spec.instrument, local_ok or remote_ok, detail))
        except Exception as exc:
            out.append((spec.instrument, local_ok, "oanda_fail=%s local=%s" % (exc, local_ok)))
    return out
