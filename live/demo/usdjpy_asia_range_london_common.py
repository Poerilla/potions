"""USDJPY Asia-range London v2b — shared paper/OANDA demo helpers.

Promoted book: ``S_3_1_3`` + Jan blackout + shadow roll50 WR≥40% / PF≥1.
Plugin: ``v2b_scaleout`` with ``session_or_ranges`` (Asia 19:00–03:00 NY) and
``live/asia_range_shadow.py`` book updated after each London EOD.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ..asia_range_shadow import append_shadow_campaign, load_shadow_book, save_shadow_book, seed_shadow_nets
from ..broker import DEFAULT_TICK_SIZE
from ..engine import Engine
from ..fx_v2b_london_ungated import resolve_book
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
from ..replay_realism import hardened_replay_engine_kwargs
from ..store import FlatFileStore
from ..verification import SpoofVerificationProvider
from . import DEMO_ROOT, demo_run_root

NY = pytz.timezone("America/New_York")
ASIA_START = dt_time(19, 0)
ASIA_END = dt_time(3, 0)
LONDON_OPEN = dt_time(3, 0)
EOD = dt_time(11, 59)
PROGRESS_HEARTBEAT_SECONDS = 300
MIN_ASIA_BARS = 180
BOOK = "S_3_1_3"
TICK = 0.001


def _load_demo_env() -> Dict[str, str]:
    env = dict(os.environ)
    dotenv = DEMO_ROOT / ".env"
    if dotenv.exists() and not env.get("OANDA_TOKEN"):
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def oanda_config_from_env() -> OandaConfig:
    return OandaConfig.from_env(_load_demo_env())


@dataclass(frozen=True)
class AsiaRangeDemoSpec:
    instrument: str
    strategy_id: str
    run_dirname: str
    paper_only: bool
    oanda_routing: bool
    tick: float = TICK
    book: str = BOOK
    strategy_type: str = "v2b_scaleout"
    cli_command: str = ""


PAPER_SPEC = AsiaRangeDemoSpec(
    instrument="USDJPY",
    strategy_id="usdjpy_asia_range_london_S_3_1_3_flt_paper",
    run_dirname="usdjpy_asia_range_london_paper",
    paper_only=True,
    oanda_routing=False,
    cli_command="demo-usdjpy-asia-range-paper",
)

OANDA_SPEC = AsiaRangeDemoSpec(
    instrument="USDJPY",
    strategy_id="usdjpy_asia_range_london_S_3_1_3_flt_oanda",
    run_dirname="usdjpy_asia_range_london_oanda",
    paper_only=False,
    oanda_routing=True,
    cli_command="demo-usdjpy-asia-range-oanda",
)


def default_output_root(spec: AsiaRangeDemoSpec) -> Path:
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


def shadow_path(output_root: Path) -> Path:
    return output_root / "shadow_campaigns.json"


def campaign_parity_path(output_root: Path) -> Path:
    return output_root / "campaign_parity.csv"


_PARITY_FIELDS = (
    "session_date",
    "shadow_50_wr",
    "shadow_50_pf",
    "shadow_n",
    "decision",
    "reason",
    "realized_campaign_net",
    "next_shadow_n",
    "warmup",
    "logged_at",
)


def append_campaign_parity(output_root: Path, row: Dict[str, Any]) -> None:
    """Append one live-parity audit row (research tape comparable)."""
    import csv

    path = campaign_parity_path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    payload = {k: row.get(k, "") for k in _PARITY_FIELDS}
    if not payload.get("logged_at"):
        payload["logged_at"] = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_PARITY_FIELDS))
        if write_header:
            w.writeheader()
        w.writerow(payload)


def append_progress(output_root: Path, message: str) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    with progress_path(output_root).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ensure_shadow_seed(output_root: Path) -> List[float]:
    path = shadow_path(output_root)
    existing = load_shadow_book(path)
    if existing:
        return existing
    nets = seed_shadow_nets(window=50)
    save_shadow_book(
        path,
        nets,
        meta={"seed": "usdjpy_v2b_asia_range_london_S_3_1_3 last50", "book": BOOK},
    )
    return nets


def strategy_config_payload(spec: AsiaRangeDemoSpec, output_root: Path) -> Dict[str, Any]:
    sizing = resolve_book(spec.book)
    nets = ensure_shadow_seed(output_root)
    return {
        "mode": "oco_then_reverse",
        "entry_qty": sizing["entry_qty"],
        "tp1_qty": sizing["tp1_qty"],
        "tp2_qty": sizing["tp2_qty"],
        "tick_size": spec.tick,
        "rth_start": "03:00",
        "or_end": "03:00",
        "or_bars": 1,
        "eod_cutoff": "11:59",
        "use_regime_filter": False,
        "prior_opposite_only": False,
        "clock": "asia_range_london",
        "asia_window": "19:00-03:00",
        "session_or_ranges": {},
        "skip_entry_months": [1],
        "shadow_roll_window": 50,
        "shadow_min_wr": 0.40,
        "shadow_min_pf": 1.0,
        "shadow_campaigns_seed": nets,
        "shadow_campaigns_path": str(shadow_path(output_root)),
        "record_levels": True,
        "paper_only": spec.paper_only,
        "oanda_routing": spec.oanda_routing,
        "signal_price": "mid",
        "fill_price": "bid_ask" if spec.paper_only else "oanda",
        "book": spec.book,
        "variant": "skip_months+roll50_wr40_pf1",
    }


def write_run_meta(output_root: Path, *, spec: AsiaRangeDemoSpec, config: OandaConfig) -> Dict[str, Any]:
    payload = strategy_config_payload(spec, output_root)
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": spec.strategy_id,
        "strategy_type": spec.strategy_type,
        "instrument": spec.instrument,
        "oanda_instrument": config.symbol_for(spec.instrument),
        "book": spec.book,
        "variant": "skip_months+roll50_wr40_pf1",
        "skip_entry_months": [1],
        "shadow_roll_window": 50,
        "shadow_min_wr": 0.40,
        "shadow_min_pf": 1.0,
        "entry_qty": payload["entry_qty"],
        "tp1_qty": payload["tp1_qty"],
        "tp2_qty": payload["tp2_qty"],
        "account_mode": "paper",
        "oanda_routing": spec.oanda_routing,
        "allow_live_routing": False,
        "oanda_env": config.env,
        "oanda_account_id": config.account_id or DEFAULT_PRIMARY_ACCOUNT,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "tracker": "USDJPY Asia-range London S_3_1_3 filtered N/S 7.23",
        "hub": "live/state/fx_v2b_asia_range_london_usdjpy_filters",
        "note": "Asia OR 19:00-03:00 → arm London 03:00 → flatten 11:59; Jan skip + shadow roll50.",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path, spec: AsiaRangeDemoSpec) -> FlatFileStore:
    store = FlatFileStore(state_root_for(output_root))
    store.ensure()
    payload = strategy_config_payload(spec, output_root)
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
                max_contracts=int(payload["entry_qty"]),
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    return store


def build_engine(store: FlatFileStore, *, spec: AsiaRangeDemoSpec, config: Optional[OandaConfig] = None, client: Optional[OandaApiClient] = None) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(spec.instrument, spec.tick)
    if spec.oanda_routing:
        assert config is not None and client is not None
        broker = OandaBroker(store, config=config, client=client, allow_live_routing=False)
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
        )
    return Engine(
        store=store,
        persist_bars=True,
        persist_health=True,
        tick_size={spec.instrument: spec.tick},
        verification_provider=SpoofVerificationProvider(store),
        emit_order_alerts=True,
        broker_log_events=True,
        broker_persist_modifications=True,
        **hardened_replay_engine_kwargs(slippage_ticks=0.0, spread_model=None),
    )


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


class AsiaRangeRunner:
    """Stream quotes, build Asia H/L overnight, arm v2b at London open."""

    def __init__(
        self,
        *,
        spec: AsiaRangeDemoSpec,
        output_root: Optional[Path] = None,
        config: Optional[OandaConfig] = None,
        client: Optional[OandaApiClient] = None,
    ):
        self.spec = spec
        self.output_root = Path(output_root) if output_root is not None else default_output_root(spec)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config = config or oanda_config_from_env()
        self.store = bootstrap_store(self.output_root, spec)
        self.client = client or OandaApiClient(config=self.config, store=self.store)
        self.engine = build_engine(self.store, spec=spec, config=self.config, client=self.client)
        self.builder_1m = QuoteOneMinuteBarBuilder(
            spec.instrument,
            source="oanda_asia_range_%s" % ("paper" if spec.paper_only else "oanda"),
        )
        self._last_progress_at = 0.0
        self.ticks_logged = 0
        self.bars_1m = 0
        self.stop_requested = False
        self._asia_hi: Optional[float] = None
        self._asia_lo: Optional[float] = None
        self._asia_bars = 0
        self._asia_session: Optional[date] = None  # London session date this Asia window feeds
        self._injected_session: Optional[str] = None
        self._shadow_done_session: Optional[str] = None

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    def _london_session_for_asia_ts(self, wall: datetime) -> date:
        """Asia [19:00, 03:00) feeds the London calendar date at/after 03:00."""
        if wall.timetz().replace(tzinfo=None) >= ASIA_START:
            return wall.date() + timedelta(days=1)
        return wall.date()

    def _in_asia_window(self, wall: datetime) -> bool:
        t = wall.timetz().replace(tzinfo=None)
        return t >= ASIA_START or t < ASIA_END

    def _update_asia_range(self, wall: datetime, high: float, low: float) -> None:
        sess = self._london_session_for_asia_ts(wall)
        if self._asia_session != sess:
            self._asia_session = sess
            self._asia_hi = None
            self._asia_lo = None
            self._asia_bars = 0
            self._injected_session = None
        if not self._in_asia_window(wall):
            return
        self._asia_bars += 1
        self._asia_hi = high if self._asia_hi is None else max(self._asia_hi, high)
        self._asia_lo = low if self._asia_lo is None else min(self._asia_lo, low)

    def _maybe_inject_session_or(self, wall: datetime) -> None:
        if self._asia_session is None or self._asia_hi is None or self._asia_lo is None:
            return
        if self._asia_hi <= self._asia_lo or self._asia_bars < MIN_ASIA_BARS:
            return
        sess = self._asia_session.isoformat()
        if self._injected_session == sess:
            return
        # Inject once we reach London open for that session.
        if wall.date() != self._asia_session:
            return
        if wall.timetz().replace(tzinfo=None) < LONDON_OPEN:
            return
        rows = self.store.read_table("strategy_instances")
        if not rows:
            return
        row = dict(rows[0])
        try:
            cfg = json.loads(row.get("config_json") or "{}")
        except json.JSONDecodeError:
            cfg = {}
        ranges = dict(cfg.get("session_or_ranges") or {})
        ranges[sess] = {
            "high": float(self._asia_hi),
            "low": float(self._asia_lo),
            "asia_bars": int(self._asia_bars),
            "asia_window": "19:00-03:00",
        }
        cfg["session_or_ranges"] = ranges
        # Refresh shadow seed from file so overnight EOD appends are visible.
        cfg["shadow_campaigns_seed"] = load_shadow_book(shadow_path(self.output_root))
        row["config_json"] = json.dumps(cfg, sort_keys=True)
        self.store.upsert_row("strategy_instances", "strategy_id", row)
        plugin = self.engine.manager.plugins.get(self.spec.strategy_id)
        if plugin is not None:
            plugin.config["session_or_ranges"] = ranges
            plugin.config["shadow_campaigns_seed"] = cfg["shadow_campaigns_seed"]
            plugin.config["shadow_campaigns_path"] = str(shadow_path(self.output_root))
            st = dict(plugin.state or {})
            st["shadow_campaigns"] = list(cfg["shadow_campaigns_seed"])
            plugin.state = st
            if hasattr(plugin, "_commit_state"):
                try:
                    plugin._commit_state(st)
                except Exception:
                    pass
        self._injected_session = sess
        append_progress(
            self.output_root,
            "asia_or injected session=%s hi=%.3f lo=%.3f bars=%d" % (sess, self._asia_hi, self._asia_lo, self._asia_bars),
        )
        self._log_parity_decision(sess, plugin)

    def _log_parity_decision(self, sess: str, plugin: Any) -> None:
        """Log skip/take + shadow WR/PF at London inject (live-parity audit)."""
        try:
            if plugin is None or not hasattr(plugin, "session_gate_decision"):
                return
            decision = plugin.session_gate_decision(sess, dict(plugin.state or {}))
            append_campaign_parity(
                self.output_root,
                {
                    "session_date": sess,
                    "shadow_50_wr": "%.4f" % float(decision.get("shadow_50_wr") or 0.0),
                    "shadow_50_pf": "%.4f" % float(decision.get("shadow_50_pf") or 0.0),
                    "shadow_n": int(decision.get("shadow_n") or 0),
                    "decision": decision.get("decision") or "",
                    "reason": decision.get("reason") or "",
                    "realized_campaign_net": "",
                    "next_shadow_n": "",
                    "warmup": "1" if decision.get("warmup") else "0",
                },
            )
            append_progress(
                self.output_root,
                "parity session=%s decision=%s reason=%s wr=%.3f pf=%.3f n=%d"
                % (
                    sess,
                    decision.get("decision"),
                    decision.get("reason"),
                    float(decision.get("shadow_50_wr") or 0.0),
                    float(decision.get("shadow_50_pf") or 0.0),
                    int(decision.get("shadow_n") or 0),
                ),
            )
        except Exception as exc:
            append_progress(self.output_root, "parity log failed session=%s: %s" % (sess, exc))

    def _maybe_append_shadow_from_live(self, wall: datetime) -> None:
        """After London EOD, append today's live campaign net into the shadow book.

        When the gate sat out there is no live campaign — research still advances
        the shadow via unfiltered sim. Here we append live campaign PnL when we
        traded; sit-out days are logged for a follow-up candle-sim append.
        """
        if wall.timetz().replace(tzinfo=None) < EOD:
            return
        sess = wall.date().isoformat()
        if self._shadow_done_session == sess:
            return
        fills_path = state_root_for(self.output_root) / "fills.csv"
        if not fills_path.exists():
            append_progress(self.output_root, "shadow sitout_or_empty session=%s (no fills yet)" % sess)
            self._shadow_done_session = sess
            return
        try:
            import pandas as pd

            df = pd.read_csv(fills_path)
            if df.empty or "ts" not in df.columns:
                self._shadow_done_session = sess
                return
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            day = df[df["ts"].dt.tz_convert("America/New_York").dt.date.astype(str) == sess]
            if day.empty:
                append_progress(self.output_root, "shadow sitout session=%s (no fills today)" % sess)
                self._shadow_done_session = sess
                return
            # Approximate campaign net from fills using mid/price * signed qty.
            # Prefer unit_trades if the engine wrote them; else skip append.
            unit_path = state_root_for(self.output_root) / "unit_trades.csv"
            net = None
            if unit_path.exists():
                ut = pd.read_csv(unit_path)
                if not ut.empty and "entry_ts" in ut.columns:
                    ut["entry_ts"] = pd.to_datetime(ut["entry_ts"], utc=True)
                    today = ut[ut["entry_ts"].dt.tz_convert("America/New_York").dt.date.astype(str) == sess]
                    if not today.empty and "net_usd" in today.columns:
                        net = float(today.groupby("trade_id")["net_usd"].sum().sum())
            if net is None:
                append_progress(self.output_root, "shadow defer session=%s (await unit_trades / candle-sim)" % sess)
                # Still close the parity row for sit-out / no-fill days.
                append_campaign_parity(
                    self.output_root,
                    {
                        "session_date": sess,
                        "shadow_50_wr": "",
                        "shadow_50_pf": "",
                        "shadow_n": "",
                        "decision": "eod",
                        "reason": "sitout_or_no_unit_trades",
                        "realized_campaign_net": "",
                        "next_shadow_n": len(load_shadow_book(shadow_path(self.output_root))),
                        "warmup": "",
                    },
                )
                self._shadow_done_session = sess
                return
            nets = append_shadow_campaign(shadow_path(self.output_root), net)
            append_progress(self.output_root, "shadow append session=%s net=%.2f" % (sess, net))
            append_campaign_parity(
                self.output_root,
                {
                    "session_date": sess,
                    "shadow_50_wr": "",
                    "shadow_50_pf": "",
                    "shadow_n": "",
                    "decision": "eod",
                    "reason": "realized",
                    "realized_campaign_net": "%.4f" % float(net),
                    "next_shadow_n": len(nets),
                    "warmup": "",
                },
            )
            self._shadow_done_session = sess
        except Exception as exc:
            append_progress(self.output_root, "shadow append failed session=%s: %s" % (sess, exc))
            self._shadow_done_session = sess

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
        wall = parse_oanda_ts(ts).astimezone(NY)
        day = wall.date().isoformat()
        payload = {
            "type": "price",
            "instrument": self.spec.instrument,
            "oanda_instrument": self.config.symbol_for(self.spec.instrument),
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

        completed: List[Bar] = []
        for bar_1m in self.builder_1m.on_quote(bid=float(bid), ask=float(ask), mid=mid_px, quantity=quantity, ts=ts):
            self.bars_1m += 1
            self.store.append_bar(bar_1m)
            self._update_asia_range(parse_oanda_ts(bar_1m.ts).astimezone(NY), float(bar_1m.high), float(bar_1m.low))
            self._maybe_inject_session_or(parse_oanda_ts(bar_1m.ts).astimezone(NY))
            self.engine.process_bar(bar_1m)
            completed.append(bar_1m)
        self._maybe_append_shadow_from_live(wall)
        self._maybe_heartbeat()
        return completed

    def flush(self) -> List[Bar]:
        out: List[Bar] = []
        for bar_1m in self.builder_1m.flush():
            self.bars_1m += 1
            self.store.append_bar(bar_1m)
            self._update_asia_range(parse_oanda_ts(bar_1m.ts).astimezone(NY), float(bar_1m.high), float(bar_1m.low))
            self._maybe_inject_session_or(parse_oanda_ts(bar_1m.ts).astimezone(NY))
            self.engine.process_bar(bar_1m)
            out.append(bar_1m)
        return out

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
            "heartbeat ticks=%d bars_1m=%d orders=%d open_positions=%d asia_bars=%d book=%s"
            % (
                self.ticks_logged,
                self.bars_1m,
                len(self.engine.broker.reconcile_orders()),
                len(open_positions),
                self._asia_bars,
                self.spec.book,
            ),
        )


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid(output_root: Path) -> Optional[int]:
    path = pidfile_path(output_root)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip().splitlines()[0])
    except Exception:
        return None


def status_daemon(output_root: Path, *, spec: AsiaRangeDemoSpec) -> int:
    pid = read_pid(output_root)
    alive = bool(pid and pid_is_alive(pid))
    meta = {}
    if run_meta_path(output_root).exists():
        try:
            meta = json.loads(run_meta_path(output_root).read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    print(
        "pid=%s alive=%s started_at=%s state=%s routing=%s book=%s"
        % (
            pid,
            alive,
            meta.get("started_at"),
            state_root_for(output_root),
            spec.oanda_routing,
            spec.book,
        )
    )
    return 0 if alive else 1


def stop_daemon(output_root: Path) -> int:
    pid = read_pid(output_root)
    if not pid:
        print("no pidfile")
        return 1
    if not pid_is_alive(pid):
        pidfile_path(output_root).unlink(missing_ok=True)
        print("stale pidfile removed")
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if not pid_is_alive(pid):
            break
        time.sleep(0.25)
    pidfile_path(output_root).unlink(missing_ok=True)
    print("stopped pid=%s" % pid)
    return 0


def spawn_daemon(*, spec: AsiaRangeDemoSpec, output_root: Path, max_ticks: int = 0, oanda_config_path: str = "") -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    existing = read_pid(output_root)
    if existing and pid_is_alive(existing):
        print("already running pid=%s" % existing)
        return 1
    cmd = [
        sys.executable,
        "-m",
        "potions.live.cli",
        spec.cli_command,
        "--output-root",
        str(output_root),
    ]
    if max_ticks:
        cmd.extend(["--max-ticks", str(max_ticks)])
    if oanda_config_path:
        cmd.extend(["--oanda-config", oanda_config_path])
    logf = run_log_path(output_root).open("a", encoding="utf-8")
    child_env = _load_demo_env()
    child_env["PYTHONPATH"] = "/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    proc = __import__("subprocess").Popen(
        cmd,
        stdout=logf,
        stderr=logf,
        start_new_session=True,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=child_env,
    )
    pidfile_path(output_root).write_text("%s\n" % proc.pid, encoding="utf-8")
    append_progress(output_root, "spawned daemon pid=%s cmd=%s" % (proc.pid, " ".join(cmd)))
    print("spawned pid=%s" % proc.pid)
    return 0


def run_stream_loop(
    *,
    spec: AsiaRangeDemoSpec,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    max_ticks: int = 0,
    reconnect_initial_seconds: float = 2.0,
    reconnect_max_seconds: float = 60.0,
) -> int:
    from .oanda_v2b_ungated_common import (
        _interruptible_sleep,
        _log_stream_error,
        _price_levels,
        _remove_pidfile,
    )

    cfg = config or oanda_config_from_env()
    cfg.validate_for_network()
    if str(cfg.env).lower() != "practice":
        root = Path(output_root) if output_root is not None else default_output_root(spec)
        append_progress(root, "REFUSING non-practice OANDA_ENV=%s" % cfg.env)
        return 2

    root = Path(output_root) if output_root is not None else default_output_root(spec)
    meta = write_run_meta(root, spec=spec, config=cfg)
    runner = AsiaRangeRunner(spec=spec, output_root=root, config=cfg)
    pidfile_path(root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_progress(
        root,
        "STARTED %s book=%s routing=%s account=%s state=%s pid=%s"
        % (spec.strategy_id, spec.book, spec.oanda_routing, cfg.account_id, state_root_for(root), os.getpid()),
    )
    append_progress(
        root,
        "RUN_META %s"
        % json.dumps(
            {k: meta[k] for k in ("started_at", "book", "variant", "oanda_env", "oanda_routing") if k in meta},
            sort_keys=True,
        ),
    )

    signal.signal(signal.SIGINT, runner.request_stop)
    signal.signal(signal.SIGTERM, runner.request_stop)

    client = runner.client
    oanda_name = cfg.symbol_for(spec.instrument)
    price_ticks = 0
    reconnect_attempt = 0
    backoff = float(reconnect_initial_seconds)
    exit_code = 0

    try:
        while not runner.stop_requested:
            reconnect_attempt += 1
            append_progress(
                root,
                "Opening pricing stream attempt=%d instrument=%s host=%s account=%s snapshot=True"
                % (reconnect_attempt, oanda_name, cfg.stream_hostname(), cfg.account_id),
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
                    root,
                    runner.store,
                    stage="stream_open",
                    exc=open_exc,
                    extra={"attempt": reconnect_attempt, "backoff_seconds": backoff},
                )
                if runner.stop_requested:
                    break
                append_progress(root, "RECONNECT sleeping %.1fs after stream_open failure" % backoff)
                _interruptible_sleep(runner, backoff)
                backoff = min(backoff * 2.0, reconnect_max_seconds)
                continue

            append_progress(root, "STREAM connected attempt=%d status=200" % reconnect_attempt)
            backoff = float(reconnect_initial_seconds)
            session_ticks = 0
            try:
                for msg_type, msg in response.parts():
                    if runner.stop_requested:
                        break
                    if msg_type == "pricing.PricingHeartbeat" or getattr(msg, "type", None) == "HEARTBEAT":
                        runner._maybe_heartbeat()
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
                        runner.on_price_tick(
                            bid=float(bid), ask=float(ask), mid=mid, ts=ts, quantity=0.0, raw=event
                        )
                    except Exception as tick_exc:
                        _log_stream_error(
                            root,
                            runner.store,
                            stage="tick_handle",
                            exc=tick_exc,
                            extra={"event_ts": ts},
                        )
                        continue
                    session_ticks += 1
                    price_ticks += 1
                    if max_ticks and price_ticks >= max_ticks:
                        append_progress(root, "max_ticks=%d reached; stopping" % max_ticks)
                        runner.request_stop()
                        break
            except Exception as stream_exc:
                _log_stream_error(
                    root,
                    runner.store,
                    stage="stream_read",
                    exc=stream_exc,
                    extra={"attempt": reconnect_attempt, "session_ticks": session_ticks, "total_ticks": price_ticks},
                )
                if runner.stop_requested:
                    break
                append_progress(root, "RECONNECT sleeping %.1fs after stream_read failure" % backoff)
                _interruptible_sleep(runner, backoff)
                backoff = min(backoff * 2.0, reconnect_max_seconds)
                continue

            if runner.stop_requested:
                break
            append_progress(
                root,
                "WARN stream ended without error attempt=%d session_ticks=%d; reconnecting in %.1fs"
                % (reconnect_attempt, session_ticks, backoff),
            )
            _interruptible_sleep(runner, backoff)
            backoff = min(backoff * 2.0, reconnect_max_seconds)
    except Exception as fatal_exc:
        _log_stream_error(root, runner.store, stage="fatal", exc=fatal_exc)
        exit_code = 1
    finally:
        runner.flush()
        append_progress(
            root,
            "STOPPED ticks=%d bars_1m=%d reconnect_attempts=%d"
            % (price_ticks, runner.bars_1m, reconnect_attempt),
        )
        _remove_pidfile(root)
    return exit_code
