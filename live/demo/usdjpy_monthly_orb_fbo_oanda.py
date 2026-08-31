"""USDJPY Monthly ORB FBO 1/1/3 atr80 — OANDA practice demo (account -006).

Banked research (daily decision / PaperBroker): N/S ≈ 4.25, ~+$108k / −$25k,
156 campaigns. Hub: ``live/state/fx_cross_pair_tracker_leaders/``.

Warm-start: local ``fx/usdjpy_daily.csv`` + OANDA ``D`` candles → PaperBroker
replay (hold out last day), strip paper book, then route only **new** daily
closes through ``OandaBroker``. Resting entry stops fill intradaily via account
changes polling; protective SL is research ``stop_mode=close`` (day close).
"""

from __future__ import annotations

import csv
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from ..broker import DEFAULT_TICK_SIZE
from ..broker_like_replays import _month_end_dates
from ..engine import Engine
from ..models import Bar, StrategyInstance, as_row, utc_now_iso
from ..oanda import OandaApiClient, OandaBroker, OandaConfig
from ..replay_realism import hardened_replay_engine_kwargs
from ..store import FlatFileStore
from ..verification import SpoofVerificationProvider
from . import DEMO_ROOT, demo_run_root
from .yearly_orb_common import append_progress as _yor_append_progress
from .yearly_orb_common import (
    fetch_oanda_daily,
    load_merged_daily,
    pid_is_alive,
    read_pid,
    warm_start,
)

REPO = Path(__file__).resolve().parents[2]
MONTHLY_ACCOUNT = "101-002-39860312-006"
INSTRUMENT = "USDJPY"
TICK = 0.001
STRATEGY_ID = "usdjpy_monthly_orb_fbo_atr80_oanda"
RUN_DIRNAME = "usdjpy_monthly_orb_fbo_oanda"
CLI_COMMAND = "demo-usdjpy-monthly-fbo-oanda"
POLL_SECONDS = 60
PROGRESS_HEARTBEAT_SECONDS = 300
# Practice units (1:1:3). Research used abstract qty 5/1/1 with JPY PV.
ENTRY_QTY = 1000
TP1_QTY = 200
TP2_QTY = 200


class _DailySpec:
    """Shim so yearly ``load_merged_daily`` can load USDJPY daily CSV."""

    instrument = INSTRUMENT

    def daily_csv(self) -> Path:
        return REPO / "fx" / "usdjpy_daily.csv"


def default_output_root() -> Path:
    return demo_run_root(RUN_DIRNAME)


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


def atr80_filter_path(output_root: Path) -> Path:
    return state_root_for(output_root) / "filters" / "usdjpy_atr80.csv"


def append_progress(output_root: Path, message: str) -> None:
    _yor_append_progress(output_root, message)


def monthly_config(
    *,
    oanda_config_path: str = "",
    environ: Optional[Dict[str, str]] = None,
) -> OandaConfig:
    """Force practice account -006; optional JSON overlay for env/account."""
    env = dict(environ if environ is not None else os.environ)
    dotenv = DEMO_ROOT / ".env"
    if dotenv.exists() and not env.get("OANDA_TOKEN"):
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    env["OANDA_ACCOUNT_ID"] = MONTHLY_ACCOUNT
    if oanda_config_path:
        cfg = OandaConfig.from_json_file(Path(oanda_config_path), environ=env)
    else:
        cfg = OandaConfig.from_env(env)
    if str(cfg.account_id) != MONTHLY_ACCOUNT:
        cfg = OandaConfig(
            env=cfg.env,
            api_url=cfg.api_url,
            stream_url=cfg.stream_url,
            token=cfg.token,
            account_id=MONTHLY_ACCOUNT,
            instrument_map=dict(cfg.instrument_map),
            application=cfg.application,
        )
    return cfg


def write_atr80_filter(bars: Sequence[Bar], path: Path) -> Path:
    """Causal ATR14 rolling-500 pctl ≤ 0.80 daily gate (same as research)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for b in bars:
        rows.append(
            dict(
                date=str(b.ts)[:10],
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
            )
        )
    d = pd.DataFrame(rows)
    if d.empty:
        pd.DataFrame(columns=["date", "long_ok", "short_ok"]).to_csv(path, index=False)
        return path
    d = d.sort_values("date").reset_index(drop=True)
    tr = np.maximum(
        d.high - d.low,
        np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()),
    )
    d["atr14"] = tr.rolling(14).mean()
    d["pctl"] = d.atr14.rolling(500, min_periods=100).rank(pct=True)
    out = []
    for _, r in d.iterrows():
        ok = True if r.pctl != r.pctl else bool(r.pctl <= 0.80)
        out.append(dict(date=r.date, long_ok=ok, short_ok=ok))
    pd.DataFrame(out).to_csv(path, index=False)
    return path


def strategy_config_payload(
    *,
    bars: Sequence[Bar],
    atr80_csv: Path,
    oanda_routing: bool,
) -> Dict[str, Any]:
    return {
        "allow_shorts": True,
        "or_sessions": 3,
        "max_trades_per_month": 2,
        "entry_qty": ENTRY_QTY,
        "tp1_qty": TP1_QTY,
        "tp2_qty": TP2_QTY,
        "tp1_r": 0.25,
        "tp2_r": 1.0,
        "runner_r": 2.0,
        "be_after": "tp1",
        "entry_mode": "first_break_opposite",
        "stop_mode": "close",
        "flip_after_stop": False,
        "eod_stop_to_or_mid": False,
        "flatten_month_end": True,
        "record_levels": False,
        "feed_timeframe": "D",
        "entry_filter_csv": str(atr80_csv),
        "entry_filter_rearm": True,
        "month_end_dates": _month_end_dates(bars),
        "paper_only": not oanda_routing,
        "oanda_routing": oanda_routing,
        "tick_size": TICK,
        "book": "fbo_1_1_3_atr80",
        "n_s_banked": 4.25,
        "units_note": "Practice 1000/200/200 (1/1/3). Research used abstract qty 5/1/1.",
    }


def write_run_meta(output_root: Path, *, config: OandaConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": STRATEGY_ID,
        "strategy_type": "monthly_orb_v2b_oco",
        "instrument": INSTRUMENT,
        "oanda_instrument": config.symbol_for(INSTRUMENT),
        "tick_size": TICK,
        "timeframe": "D",
        "book": "fbo_1_1_3_atr80",
        "entry_qty": ENTRY_QTY,
        "tp1_qty": TP1_QTY,
        "tp2_qty": TP2_QTY,
        "n_s_banked": 4.25,
        "account_mode": "live",
        "oanda_routing": True,
        "allow_live_routing": False,
        "oanda_env": config.env,
        "oanda_account_id": MONTHLY_ACCOUNT,
        "oanda_api_url": config.api_url,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "tracker": "fx_cross_pair_tracker_leaders USDJPY FBO 1/1/3 atr80 N/S 4.25",
        "note": "Monthly FBO atr80 on practice -006; daily decisions; close-SL; atr80 gate.",
        "config_snapshot": {k: payload[k] for k in ("entry_mode", "stop_mode", "or_sessions", "entry_filter_csv") if k in payload},
    }
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path, payload: Dict[str, Any]) -> FlatFileStore:
    store = FlatFileStore(state_root_for(output_root))
    store.ensure()
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=STRATEGY_ID,
                strategy_type="monthly_orb_v2b_oco",
                version="v1",
                instrument=INSTRUMENT,
                broker_instrument=INSTRUMENT,
                account_mode="live",
                enabled=True,
                timeframes="D",
                max_contracts=ENTRY_QTY,
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_paper_engine(store: FlatFileStore) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    return Engine(
        store=store,
        persist_bars=True,
        persist_health=True,
        tick_size={INSTRUMENT: TICK},
        verification_provider=SpoofVerificationProvider(store),
        emit_order_alerts=True,
        broker_log_events=True,
        broker_persist_modifications=True,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=None),
    )


def build_oanda_engine(store: FlatFileStore, *, config: OandaConfig, client: OandaApiClient) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    broker = OandaBroker(
        store,
        config=config,
        client=client,
        allow_live_routing=False,
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


def _strip_open_book(store: FlatFileStore, output_root: Path) -> None:
    """Drop paper fills/orders/positions; keep monthly OR state; re-arm entry stops."""
    for table in ("orders", "order_intents", "positions", "fills"):
        path = store.root / ("%s.csv" % table)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            header = text.splitlines()[0] if text.strip() else ""
            if header:
                path.write_text(header + "\n", encoding="utf-8")
    state_path = store.root / "strategy_state.csv"
    if state_path.exists():
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
                st["active_direction"] = ""
                st["campaign_stop"] = None
                st["tp1_hit"] = False
                st["tp2_hit"] = False
                # Force re-place of resting opposite stop on next daily bar via OANDA.
                if str(st.get("phase") or "") in {"wait_fill", "arm_opposite"} or bool(st.get("opposite_armed")):
                    st["opposite_armed"] = False
                    if str(st.get("first_break_side") or ""):
                        st["phase"] = "arm_opposite"
                key = "state_json" if "state_json" in row else "state"
                row[key] = json.dumps(st, sort_keys=True)
            with state_path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
    append_progress(output_root, "OANDA warm-start: cleared paper book; kept monthly OR state; re-arm pending")


def status_daemon(output_root: Path) -> int:
    pid = read_pid(output_root)
    meta: Dict[str, Any] = {}
    if run_meta_path(output_root).exists():
        meta = json.loads(run_meta_path(output_root).read_text(encoding="utf-8"))
    if pid is None:
        print("status: not running (no pidfile) root=%s" % output_root)
        return 1
    alive = pid_is_alive(pid)
    print(
        "status: pid=%d alive=%s book=%s account=%s routing=%s state=%s"
        % (
            pid,
            alive,
            meta.get("book", "fbo_1_1_3_atr80"),
            meta.get("oanda_account_id", MONTHLY_ACCOUNT),
            meta.get("oanda_routing", True),
            meta.get("state_root", state_root_for(output_root)),
        )
    )
    return 0 if alive else 1


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


class MonthlyFboOandaRunner:
    def __init__(self, *, output_root: Path, config: OandaConfig):
        self.output_root = output_root
        self.config = config
        self.stop_requested = False
        self.last_day: Optional[str] = None
        self.bars_seen = 0
        self.fills_from_oanda = 0
        self._last_progress_at = 0.0
        self.store: Optional[FlatFileStore] = None
        self.client: Optional[OandaApiClient] = None
        self.engine: Optional[Engine] = None

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    def _heartbeat(self) -> None:
        now = time.time()
        if now - self._last_progress_at < PROGRESS_HEARTBEAT_SECONDS:
            return
        self._last_progress_at = now
        assert self.engine is not None
        open_pos = [p for p in self.engine.broker.reconcile_positions() if float(getattr(p, "quantity", 0) or 0) != 0]
        append_progress(
            self.output_root,
            "heartbeat bars=%d last_day=%s open_positions=%d orders=%d oanda_fills=%d account=%s"
            % (
                self.bars_seen,
                self.last_day,
                len(open_pos),
                len(self.engine.broker.reconcile_orders()),
                self.fills_from_oanda,
                MONTHLY_ACCOUNT,
            ),
        )

    def _poll_new_daily(self) -> List[Bar]:
        assert self.client is not None
        try:
            remote = fetch_oanda_daily(self.client, self.config, INSTRUMENT, count=10)
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

    def _drain_account_changes(self) -> None:
        assert self.engine is not None and self.client is not None
        broker = self.engine.broker
        if not isinstance(broker, OandaBroker):
            return
        try:
            if not broker.last_transaction_id:
                return
            body = self.client.account_changes(since_transaction_id=broker.last_transaction_id)
            fills = broker.apply_account_changes(body)
            if fills:
                self.fills_from_oanda += len(fills)
                self.engine.manager.on_fills(fills)
                append_progress(
                    self.output_root,
                    "OANDA fills applied n=%d total=%d" % (len(fills), self.fills_from_oanda),
                )
        except Exception as exc:
            append_progress(self.output_root, "WARN account_changes: %s" % exc)

    def run(self, *, max_polls: int = 0) -> int:
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config.validate_for_network()
        if str(self.config.env).lower() != "practice":
            append_progress(self.output_root, "REFUSING non-practice OANDA_ENV=%s" % self.config.env)
            return 2
        if str(self.config.account_id) != MONTHLY_ACCOUNT:
            append_progress(
                self.output_root,
                "REFUSING account_id=%s (want %s)" % (self.config.account_id, MONTHLY_ACCOUNT),
            )
            return 2

        # Probe account access early (clear error if token lacks -006).
        probe_client = OandaApiClient(config=self.config)
        try:
            body = probe_client.account_details()
        except Exception as exc:
            append_progress(
                self.output_root,
                "REFUSING: OANDA account %s not accessible (%s). "
                "Token lists the id but API returns forbidden — grant practice API access for -006, then respawn."
                % (MONTHLY_ACCOUNT, exc),
            )
            return 4
        if isinstance(body, dict) and body.get("errorMessage"):
            append_progress(
                self.output_root,
                "REFUSING: OANDA account %s error=%s — grant practice API access for -006, then respawn."
                % (MONTHLY_ACCOUNT, body.get("errorMessage")),
            )
            return 4
        if isinstance(body, dict) and not (body.get("account") or {}).get("id"):
            # Soft 403 bodies sometimes omit account.
            err = body.get("errorMessage") or body.get("errorCode") or "no account payload"
            append_progress(
                self.output_root,
                "REFUSING: OANDA account %s inaccessible (%s)." % (MONTHLY_ACCOUNT, err),
            )
            return 4

        # Bootstrap needs bars for month_end + atr80; load first with a throwaway store client.
        tmp_store = FlatFileStore(state_root_for(self.output_root))
        tmp_store.ensure()
        self.client = OandaApiClient(config=self.config, store=tmp_store)
        bars, status = load_merged_daily(
            _DailySpec(),
            self.client,
            self.config,
            output_root=self.output_root,
        )
        if not bars:
            append_progress(self.output_root, "SKIP — no usable daily data (%s)" % status)
            return 3

        atr_path = write_atr80_filter(bars, atr80_filter_path(self.output_root))
        payload = strategy_config_payload(bars=bars, atr80_csv=atr_path, oanda_routing=True)
        self.store = bootstrap_store(self.output_root, payload)
        self.client = OandaApiClient(config=self.config, store=self.store)
        write_run_meta(self.output_root, config=self.config, payload=payload)
        pidfile_path(self.output_root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
        append_progress(
            self.output_root,
            "STARTED USDJPY monthly FBO atr80 OANDA account=%s pid=%s atr80=%s"
            % (MONTHLY_ACCOUNT, os.getpid(), atr_path),
        )

        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)

        paper = build_paper_engine(self.store)
        self.engine = paper
        self.last_day = warm_start(paper, bars, output_root=self.output_root, hold_out_last=True)
        self.bars_seen = max(0, len(bars) - 1)
        _strip_open_book(self.store, self.output_root)
        self.engine = build_oanda_engine(self.store, config=self.config, client=self.client)
        try:
            broker = self.engine.broker
            if isinstance(broker, OandaBroker):
                broker.register_authority_strategy(STRATEGY_ID)
                broker.reconcile_from_account_details()
                append_progress(
                    self.output_root,
                    "OANDA reconcile lastTx=%s" % getattr(broker, "last_transaction_id", None),
                )
        except Exception as exc:
            append_progress(self.output_root, "WARN oanda reconcile: %s" % exc)

        for bar in self._poll_new_daily():
            if self.stop_requested:
                break
            day = str(bar.ts)[:10]
            append_progress(self.output_root, "PROCESS daily %s close=%.5f" % (day, bar.close))
            self.engine.process_bar(bar)
            self.last_day = day
            self.bars_seen += 1
            self._drain_account_changes()

        polls = 0
        while not self.stop_requested:
            if max_polls and polls >= max_polls:
                break
            self._heartbeat()
            self._drain_account_changes()
            time.sleep(POLL_SECONDS)
            polls += 1
            for bar in self._poll_new_daily():
                if self.stop_requested:
                    break
                day = str(bar.ts)[:10]
                append_progress(self.output_root, "PROCESS daily %s close=%.5f" % (day, bar.close))
                self.engine.process_bar(bar)
                self.last_day = day
                self.bars_seen += 1
                self._drain_account_changes()

        append_progress(
            self.output_root,
            "STOPPED bars=%d last_day=%s oanda_fills=%d" % (self.bars_seen, self.last_day, self.fills_from_oanda),
        )
        if pidfile_path(self.output_root).exists():
            pidfile_path(self.output_root).unlink()
        return 0


def run_loop(
    *,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    oanda_config_path: str = "",
    max_polls: int = 0,
) -> int:
    root = Path(output_root) if output_root is not None else default_output_root()
    cfg = config or monthly_config(oanda_config_path=oanda_config_path)
    return MonthlyFboOandaRunner(output_root=root, config=cfg).run(max_polls=max_polls)


def spawn_daemon(
    *,
    output_root: Optional[Path] = None,
    max_polls: int = 0,
    oanda_config_path: str = "",
) -> int:
    root = Path(output_root) if output_root is not None else default_output_root()
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
        CLI_COMMAND,
        "--output-root",
        str(root),
    ]
    if max_polls:
        cmd.extend(["--max-polls", str(int(max_polls))])
    if oanda_config_path:
        cmd.extend(["--oanda-config", str(oanda_config_path)])
    env = os.environ.copy()
    hsm = REPO.parent
    v20_src = REPO / "v20-python" / "src"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(hsm), str(v20_src)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env["OANDA_ACCOUNT_ID"] = MONTHLY_ACCOUNT
    dotenv = DEMO_ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        env["OANDA_ACCOUNT_ID"] = MONTHLY_ACCOUNT

    import subprocess

    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    append_progress(root, "spawned daemon pid=%d cmd=%s" % (proc.pid, " ".join(cmd)))
    print("Spawned %s pid=%d root=%s" % (CLI_COMMAND, proc.pid, root))
    return 0
