"""US30 London prior-opposed v2b — paper/OANDA demo with live ST+PMC gate feed.

Research book: ``S_1_1_3`` London OR 03:00–03:15 → flatten 11:59, gated by
same-session opposite-side hourly ST+PMC (``sl50_tp150_3r``).

Live sleeve starts at **0.25 size** (1 unit ≈ quarter of the 5-unit research
book) until concentration / live ST parity justifies half or full size.

ST events are pulled from the sibling US30 ST+PMC demos (paper↔paper,
oanda↔oanda) and optionally seeded from the research resting-limit tape.
"""

from __future__ import annotations

import csv
import json
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ..broker import DEFAULT_TICK_SIZE
from ..engine import Engine
from ..models import StrategyInstance, as_row, utc_now_iso
from ..nq_v2b_prior_opposed_replay import load_st_events
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
from . import DEMO_ROOT, demo_run_root, next_stream_backoff
from .oanda_daemon_reconcile import (
    containment_bootstrap,
    containment_note_activity,
    containment_on_reconnect,
    containment_poll,
    install_containment,
    oanda_broker_with_supervisor,
)

NY = pytz.timezone("America/New_York")
LONDON_OPEN = dt_time(3, 0)
OR_END = dt_time(3, 15)
EOD = dt_time(11, 59)
PROGRESS_HEARTBEAT_SECONDS = 300
ACCOUNT_CHANGES_POLL_SECONDS = 2.0
ST_POLL_SECONDS = 15.0
GATE_AUDIT_SECONDS = 60.0
BAR_POLL_SECONDS = 2.0
# Prefer sibling ST demo 1m bars (avoids another OANDA pricing stream on US30).
PRICE_SOURCE = "st_feed_bars"

INSTRUMENT = "US30"
TICK = 0.1
STRATEGY_TYPE = "v2b_scaleout"
PLUGIN_VERSION = "v1"
BOOK_LABEL = "S_1_0_0"  # 1-unit quarter sleeve of research S_1_1_3
SIZE_MULT = 0.25
ENTRY_QTY = 1
TP1_QTY = 0
TP2_QTY = 0

REPO = Path(__file__).resolve().parents[2]
RESEARCH_ST_ROOT = (
    REPO
    / "live"
    / "state"
    / "us30_st_pmc_runner_variants"
    / "states"
    / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"
)
RESEARCH_HUB = "live/state/fx_v2b_london_prior_opposed"


@dataclass(frozen=True)
class LondonPriorOpposedSpec:
    instrument: str
    strategy_id: str
    run_dirname: str
    paper_only: bool
    oanda_routing: bool
    st_feed_dirname: str
    st_strategy_id: str
    cli_command: str
    tick: float = TICK
    entry_qty: int = ENTRY_QTY
    tp1_qty: int = TP1_QTY
    tp2_qty: int = TP2_QTY
    size_mult: float = SIZE_MULT
    book: str = BOOK_LABEL
    strategy_type: str = STRATEGY_TYPE


PAPER_SPEC = LondonPriorOpposedSpec(
    instrument=INSTRUMENT,
    strategy_id="us30_london_prior_opposed_S_1_0_0_qtr_paper",
    run_dirname="us30_london_prior_opposed_paper",
    paper_only=True,
    oanda_routing=False,
    st_feed_dirname="us30_hourly_st_pmc_sl50_tp150_3r_paper",
    st_strategy_id="us30_hourly_st_pmc_sl50_tp150_3r_paper",
    cli_command="demo-us30-london-prior-opposed-paper",
)

OANDA_SPEC = LondonPriorOpposedSpec(
    instrument=INSTRUMENT,
    strategy_id="us30_london_prior_opposed_S_1_0_0_qtr_oanda",
    run_dirname="us30_london_prior_opposed_oanda",
    paper_only=False,
    oanda_routing=True,
    st_feed_dirname="us30_hourly_st_pmc_sl50_tp150_3r_oanda",
    st_strategy_id="us30_hourly_st_pmc_sl50_tp150_3r_oanda",
    cli_command="demo-us30-london-prior-opposed-oanda",
)


_GATE_AUDIT_FIELDS = (
    "logged_at",
    "session_date",
    "bar_ts",
    "prior_opposed_long_ok",
    "prior_opposed_short_ok",
    "prior_st_event_ts_for_long",
    "prior_st_event_side_for_long",
    "prior_st_event_ts_for_short",
    "prior_st_event_side_for_short",
    "st_events_today",
    "gate_arm_decision",
    "entry_eligible",
    "entry_eligible_ts",
    "oco_state",
    "open_entry_orders",
    "open_order_ids",
    "position_qty",
    "fill_result",
    "skip_reason",
    "size_mult",
    "entry_qty",
    "phase",
)


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


def default_output_root(spec: LondonPriorOpposedSpec) -> Path:
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


def st_events_path(output_root: Path) -> Path:
    return output_root / "st_events.json"


def gate_audit_path(output_root: Path) -> Path:
    return output_root / "gate_audit.csv"


def append_progress(output_root: Path, message: str) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    with progress_path(output_root).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def st_feed_root(spec: LondonPriorOpposedSpec) -> Path:
    return DEMO_ROOT / spec.st_feed_dirname / "state"


def _ny_date_iso(ts: str) -> str:
    dt = parse_oanda_ts(ts)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(NY).date().isoformat()


def _ny_wall(ts: str) -> datetime:
    dt = parse_oanda_ts(ts)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(NY)


def in_london_session(ts: str) -> bool:
    wall = _ny_wall(ts)
    clock = wall.timetz().replace(tzinfo=None)
    return LONDON_OPEN <= clock <= EOD


def _event_key(ev: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(ev.get("available_at_ts") or ev.get("ts") or ""),
        str(ev.get("side") or "").lower(),
        str(ev.get("source") or ""),
    )


def merge_st_events(
    base: Dict[str, List[Dict[str, Any]]],
    incoming: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {k: [dict(e) for e in v] for k, v in (base or {}).items()}
    for session, events in (incoming or {}).items():
        bucket = out.setdefault(str(session), [])
        have = {_event_key(e) for e in bucket}
        for ev in events:
            key = _event_key(ev)
            if key in have:
                continue
            bucket.append(dict(ev))
            have.add(key)
        bucket.sort(key=lambda e: str(e.get("available_at_ts") or e.get("ts") or ""))
    return out


def load_research_st_seed(*, max_sessions: int = 120) -> Dict[str, List[Dict[str, Any]]]:
    """Seed delayed-arming history from research resting-limit / fill tape."""
    fills = RESEARCH_ST_ROOT / "fills.csv"
    orders = RESEARCH_ST_ROOT / "orders.csv"
    sid = "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"
    if not fills.exists() and not orders.exists():
        return {}
    try:
        if orders.exists():
            events = load_st_events(
                fills if fills.exists() else orders,
                sid,
                orders_path=orders,
                gate_mode="resting_limit",
                # US30 runner hub is completed-hour causal (live_after already hour-complete).
                st_signal_stamp="completed_hour",
            )
            source = "research_resting_limit_completed_hour"
        else:
            events = load_st_events(fills, sid, gate_mode="fill")
            source = "research_fill"
    except Exception:
        return {}
    # Keep only recent sessions to bound config size.
    sessions = sorted(events.keys())[-max_sessions:]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for sess in sessions:
        rows = []
        for ev in events.get(sess) or []:
            row = dict(ev)
            row.setdefault("source", source)
            rows.append(row)
        if rows:
            out[sess] = rows
    return out


def load_live_st_events_from_fills(
    *,
    fills_path: Path,
    strategy_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Convert live ST+PMC entry fills into delayed-arming gate events."""
    if not fills_path.exists():
        return {}
    try:
        import pandas as pd
    except ImportError:
        return {}
    df = pd.read_csv(fills_path)
    if df.empty:
        return {}
    if "strategy_id" in df.columns:
        df = df[df["strategy_id"].astype(str) == str(strategy_id)]
    if "reason" in df.columns:
        df = df[df["reason"].astype(str).isin(["entry", "runner_entry"])]
    if df.empty or "ts" not in df.columns or "side" not in df.columns:
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in df.itertuples(index=False):
        ts = str(getattr(row, "ts", "") or "")
        if not ts:
            continue
        try:
            ny_ts = _ny_wall(ts)
            sess = ny_ts.date().isoformat()
            avail = ny_ts.isoformat()
        except Exception:
            continue
        side = "long" if str(getattr(row, "side", "")).lower() == "buy" else "short"
        out.setdefault(sess, []).append(
            {
                "ts": avail,
                "available_at_ts": avail,
                "side": side,
                "source": "live_st_fill",
                "fill_id": str(getattr(row, "fill_id", "") or ""),
                "strategy_id": strategy_id,
            }
        )
    for sess in out:
        out[sess].sort(key=lambda e: e["available_at_ts"])
    return out


def collect_st_events(spec: LondonPriorOpposedSpec, *, seed_research: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    events: Dict[str, List[Dict[str, Any]]] = {}
    if seed_research:
        events = merge_st_events(events, load_research_st_seed())
    feed = st_feed_root(spec)
    live = load_live_st_events_from_fills(
        fills_path=feed / "fills.csv",
        strategy_id=spec.st_strategy_id,
    )
    return merge_st_events(events, live)


def persist_st_events(output_root: Path, events: Dict[str, List[Dict[str, Any]]]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": utc_now_iso(),
        "sessions": len(events),
        "events": sum(len(v) for v in events.values()),
        "dynamic_sizing_events": events,
    }
    st_events_path(output_root).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_gate_audit(output_root: Path, row: Dict[str, Any]) -> None:
    path = gate_audit_path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    payload = {k: row.get(k, "") for k in _GATE_AUDIT_FIELDS}
    if not payload.get("logged_at"):
        payload["logged_at"] = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_GATE_AUDIT_FIELDS))
        if write_header:
            w.writeheader()
        w.writerow(payload)


def strategy_config_payload(
    spec: LondonPriorOpposedSpec,
    *,
    st_events: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    events = st_events if st_events is not None else {}
    return {
        "mode": "oco_then_reverse",
        "entry_qty": int(spec.entry_qty),
        "tp1_qty": int(spec.tp1_qty),
        "tp2_qty": int(spec.tp2_qty),
        "tick_size": float(spec.tick),
        "rth_start": "03:00",
        "or_end": "03:15",
        "eod_cutoff": "11:59",
        "use_regime_filter": False,
        "require_regime_dates": False,
        "prior_opposite_only": True,
        "prior_opposite_entry_qty": int(spec.entry_qty),
        "prior_opposite_tp1_qty": int(spec.tp1_qty),
        "prior_opposite_tp2_qty": int(spec.tp2_qty),
        "dynamic_sizing_events": events,
        "gate_mode": "live_st_fill",
        "st_variant": "sl50_tp150_3r",
        "st_feed": spec.st_feed_dirname,
        "clock": "london_open",
        "size_mult": float(spec.size_mult),
        "book": spec.book,
        "research_book": "S_1_1_3",
        "record_levels": True,
        "paper_only": bool(spec.paper_only),
        "oanda_routing": bool(spec.oanda_routing),
        "signal_price": "mid",
        "fill_price": "bid_ask" if spec.paper_only else "oanda",
        "variant": "london_prior_opposed_qtr",
        "hub": RESEARCH_HUB,
    }


def write_run_meta(output_root: Path, *, spec: LondonPriorOpposedSpec, config: OandaConfig) -> Dict[str, Any]:
    payload = strategy_config_payload(spec)
    meta = {
        "started_at": utc_now_iso(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "strategy_id": spec.strategy_id,
        "strategy_type": spec.strategy_type,
        "instrument": spec.instrument,
        "oanda_instrument": config.symbol_for(spec.instrument),
        "book": spec.book,
        "research_book": "S_1_1_3",
        "size_mult": spec.size_mult,
        "entry_qty": payload["entry_qty"],
        "tp1_qty": payload["tp1_qty"],
        "tp2_qty": payload["tp2_qty"],
        "prior_opposite_only": True,
        "clock": "london_open",
        "st_feed": spec.st_feed_dirname,
        "st_strategy_id": spec.st_strategy_id,
        "account_mode": "paper",
        "oanda_routing": spec.oanda_routing,
        "allow_live_routing": False,
        "oanda_env": config.env,
        "oanda_account_id": config.account_id or DEFAULT_PRIMARY_ACCOUNT,
        "output_root": str(output_root),
        "state_root": str(state_root_for(output_root)),
        "hub": RESEARCH_HUB,
        "tracker": (
            "US30 London prior-opposed delayed-arming quarter-size demo; "
            "research N/S 6.23 (curiosity); promote half/full only after live ST parity + robustness"
        ),
        "note": (
            "London OR 03:00-03:15 → flatten 11:59; arms only after same-session opposite "
            "live ST+PMC entry from sibling demo; size_mult=0.25 (1 unit). "
            "Prices: default st_feed_bars (sibling ST 1m tape) to avoid OANDA stream caps."
        ),
        "gate_audit": str(gate_audit_path(output_root)),
        "st_events": str(st_events_path(output_root)),
        "price_source": PRICE_SOURCE,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    run_meta_path(output_root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def bootstrap_store(output_root: Path, spec: LondonPriorOpposedSpec) -> FlatFileStore:
    root = state_root_for(output_root)
    store = FlatFileStore(root)
    store.ensure()
    events = collect_st_events(spec, seed_research=True)
    persist_st_events(output_root, events)
    payload = strategy_config_payload(spec, st_events=events)
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=spec.strategy_id,
                strategy_type=spec.strategy_type,
                version=PLUGIN_VERSION,
                instrument=spec.instrument,
                broker_instrument=spec.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="1m",
                max_contracts=int(spec.entry_qty),
                max_open_orders=64,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )
    n_ev = sum(len(v) for v in events.values())
    append_progress(
        output_root,
        "bootstrap st_events sessions=%d events=%d feed=%s"
        % (len(events), n_ev, spec.st_feed_dirname),
    )
    return store


def build_engine(
    store: FlatFileStore,
    *,
    spec: LondonPriorOpposedSpec,
    config: Optional[OandaConfig] = None,
    client: Optional[OandaApiClient] = None,
) -> Engine:
    DEFAULT_TICK_SIZE.setdefault(spec.instrument, spec.tick)
    if spec.oanda_routing:
        assert config is not None
        broker = oanda_broker_with_supervisor(
            store,
            config=config,
            client=client or OandaApiClient(config=config, store=store),
            strategy_id=spec.strategy_id,
            instrument=spec.instrument,
            allow_live_routing=False,
        )
        return Engine(
            store=store,
            persist_bars=True,
            persist_health=True,
            tick_size={spec.instrument: spec.tick},
            broker=broker,
            verification_provider=SpoofVerificationProvider(store),
            emit_order_alerts=True,
            broker_log_events=True,
            broker_persist_modifications=True,
            slippage_ticks=0.0,
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


def _oco_state(plugin: Any, context_orders: List[Any], position_qty: int) -> str:
    if position_qty != 0:
        return "in_position"
    entryish = [
        o
        for o in context_orders
        if str(getattr(o, "bracket_role", "") or "") in {"", "entry", "oco_entry"}
        or str(getattr(o, "reason", "") or "").startswith("v2b_entry")
        or str(getattr(o, "order_type", "")).lower() == "stop"
        and not bool(getattr(o, "reduce_only", False))
    ]
    # Prefer non-reduce-only working orders as "armed".
    working = [
        o
        for o in context_orders
        if str(getattr(o, "status", "")) in {"submitted", "partially_filled", "working", "pendingnew", "accepted"}
        and not bool(getattr(o, "reduce_only", False))
    ]
    if working:
        return "oco_armed"
    phase = ""
    try:
        phase = str((plugin.state or {}).get("phase") or "")
    except Exception:
        phase = ""
    if phase:
        return "phase:%s" % phase
    if entryish:
        return "orders_present"
    return "flat_no_oco"


def build_gate_audit_row(
    *,
    spec: LondonPriorOpposedSpec,
    plugin: Any,
    bar_ts: str,
    open_orders: List[Any],
    position_qty: int,
    recent_fill_reason: str = "",
) -> Dict[str, Any]:
    session = _ny_date_iso(bar_ts)
    events = (plugin.config.get("dynamic_sizing_events") or {}).get(session, []) if plugin else []
    long_ev = plugin._prior_opposite_event_for_entry(bar_ts, "Long") if plugin else None
    short_ev = plugin._prior_opposite_event_for_entry(bar_ts, "Short") if plugin else None
    long_ok = long_ev is not None
    short_ok = short_ev is not None
    wall = _ny_wall(bar_ts)
    clock = wall.timetz().replace(tzinfo=None)
    skip_reason = ""
    entry_eligible = "0"
    entry_eligible_ts = ""
    if clock < LONDON_OPEN:
        skip_reason = "before_london_open"
        gate = "wait_pre_london"
    elif clock > EOD:
        skip_reason = "after_eod"
        gate = "session_closed"
    elif LONDON_OPEN <= clock < OR_END:
        skip_reason = "building_or"
        gate = "or_window"
    elif not long_ok and not short_ok:
        skip_reason = "no_prior_opposite_st_event"
        gate = "disarm_wait_st"
    elif long_ok and short_ok:
        gate = "arm_both_sides"
        entry_eligible = "1"
        entry_eligible_ts = bar_ts
    elif long_ok:
        gate = "arm_long_only"
        entry_eligible = "1"
        entry_eligible_ts = bar_ts
    else:
        gate = "arm_short_only"
        entry_eligible = "1"
        entry_eligible_ts = bar_ts

    working = [
        o
        for o in open_orders
        if str(getattr(o, "status", "")) in {"submitted", "partially_filled", "working", "pendingnew", "accepted"}
        and str(getattr(o, "strategy_id", "")) == spec.strategy_id
    ]
    entry_orders = [o for o in working if not bool(getattr(o, "reduce_only", False))]
    order_desc = ",".join(
        "%s:%s" % (getattr(o, "side", ""), getattr(o, "order_type", "")) for o in entry_orders
    )
    order_ids = ",".join(str(getattr(o, "broker_order_id", "") or getattr(o, "order_id", "")) for o in entry_orders)
    phase = ""
    try:
        phase = str((plugin.state or {}).get("phase") or "") if plugin else ""
    except Exception:
        phase = ""

    return {
        "session_date": session,
        "bar_ts": bar_ts,
        "prior_opposed_long_ok": "1" if long_ok else "0",
        "prior_opposed_short_ok": "1" if short_ok else "0",
        "prior_st_event_ts_for_long": str((long_ev or {}).get("available_at_ts") or (long_ev or {}).get("ts") or ""),
        "prior_st_event_side_for_long": str((long_ev or {}).get("side") or ""),
        "prior_st_event_ts_for_short": str((short_ev or {}).get("available_at_ts") or (short_ev or {}).get("ts") or ""),
        "prior_st_event_side_for_short": str((short_ev or {}).get("side") or ""),
        "st_events_today": len(events),
        "gate_arm_decision": gate,
        "entry_eligible": entry_eligible,
        "entry_eligible_ts": entry_eligible_ts,
        "oco_state": _oco_state(plugin, working, position_qty),
        "open_entry_orders": order_desc,
        "open_order_ids": order_ids,
        "position_qty": position_qty,
        "fill_result": recent_fill_reason or ("flat" if position_qty == 0 else "open"),
        "skip_reason": skip_reason,
        "size_mult": spec.size_mult,
        "entry_qty": spec.entry_qty,
        "phase": phase,
    }


class DemoLondonPriorOpposedRunner:
    def __init__(
        self,
        spec: LondonPriorOpposedSpec,
        *,
        output_root: Optional[Path] = None,
        store: Optional[FlatFileStore] = None,
        engine: Optional[Engine] = None,
        config: Optional[OandaConfig] = None,
        client: Optional[OandaApiClient] = None,
        clock: Optional[Any] = None,
    ):
        self.spec = spec
        self.output_root = Path(output_root) if output_root is not None else default_output_root(spec)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config = config or oanda_config_from_env()
        self.store = store or bootstrap_store(self.output_root, spec)
        self.client = client or OandaApiClient(config=self.config, store=self.store)
        self.engine = engine or build_engine(
            self.store, spec=spec, config=self.config, client=self.client
        )
        self.builder = QuoteOneMinuteBarBuilder(spec.instrument, source="oanda_london_prior_opposed")
        self._clock = clock or time.time
        self._last_progress_at = 0.0
        self._last_st_poll_at = 0.0
        self._last_gate_audit_at = 0.0
        self._last_changes_poll_at = 0.0
        self._last_audit_fingerprint = ""
        self._session_day = ""
        self._seen_fill_ids: set = set()
        self._prime_seen_fills()
        self.ticks_logged = 0
        self.bars_engine = 0
        self.bars_1m = 0
        self.st_injects = 0
        self.fills_from_oanda = 0
        self.stop_requested = False
        self.containment = None
        if spec.oanda_routing:
            install_containment(
                self,
                instrument=spec.instrument,
                strategy_id=spec.strategy_id,
                strategy_type=str(getattr(spec, "strategy_type", None) or "v2b_scaleout"),
                entry_qty=float(spec.entry_qty or 0),
            )

    def _prime_seen_fills(self) -> None:
        """Avoid re-auditing historical fills after a daemon restart."""
        path = state_root_for(self.output_root) / "fills.csv"
        if not path.exists():
            return
        try:
            import pandas as pd

            df = pd.read_csv(path)
            if df.empty or "fill_id" not in df.columns:
                return
            if "strategy_id" in df.columns:
                df = df[df["strategy_id"].astype(str) == self.spec.strategy_id]
            for fid in df["fill_id"].astype(str).tolist():
                if fid:
                    self._seen_fill_ids.add(fid)
        except Exception:
            return

    def _strategy_open_orders(self) -> List[Any]:
        return [
            o
            for o in self.engine.broker.reconcile_orders()
            if str(getattr(o, "strategy_id", "")) == self.spec.strategy_id
            and str(getattr(o, "status", "")) in {"submitted", "partially_filled", "working", "accepted"}
        ]

    def _strategy_position_qty(self) -> int:
        qty = 0
        for p in self.engine.broker.reconcile_positions():
            if (
                str(getattr(p, "strategy_id", "")) == self.spec.strategy_id
                and str(getattr(p, "instrument", "")) == self.spec.instrument
            ):
                qty += int(getattr(p, "quantity", 0) or 0)
        return qty

    def _new_strategy_fills(self) -> List[Dict[str, str]]:
        path = state_root_for(self.output_root) / "fills.csv"
        if not path.exists():
            return []
        try:
            import pandas as pd

            df = pd.read_csv(path)
        except Exception:
            return []
        if df.empty:
            return []
        if "strategy_id" in df.columns:
            df = df[df["strategy_id"].astype(str) == self.spec.strategy_id]
        out: List[Dict[str, str]] = []
        for row in df.itertuples(index=False):
            fid = str(getattr(row, "fill_id", "") or "")
            if not fid or fid in self._seen_fill_ids:
                continue
            self._seen_fill_ids.add(fid)
            out.append(
                {
                    "fill_id": fid,
                    "ts": str(getattr(row, "ts", "") or ""),
                    "side": str(getattr(row, "side", "") or ""),
                    "reason": str(getattr(row, "reason", "") or ""),
                    "quantity": str(getattr(row, "quantity", "") or ""),
                    "price": str(getattr(row, "price", "") or ""),
                }
            )
        return out

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    def flush(self) -> None:
        for bar in self.builder.flush():
            self._handle_bar(bar)

    def _maybe_heartbeat(self) -> None:
        now = float(self._clock())
        if (now - self._last_progress_at) < PROGRESS_HEARTBEAT_SECONDS:
            return
        self._last_progress_at = now
        self._inject_st_events()
        open_n = len(self._strategy_open_orders())
        pos_qty = self._strategy_position_qty()
        append_progress(
            self.output_root,
            "heartbeat ticks=%d bars=%d st_injects=%d orders=%d position_qty=%d size_mult=%.2f"
            % (self.ticks_logged, self.bars_engine, self.st_injects, open_n, pos_qty, self.spec.size_mult),
        )

    def bootstrap_reconcile(self) -> None:
        broker = self.engine.broker
        if isinstance(broker, OandaBroker):
            try:
                broker.register_authority_strategy(self.spec.strategy_id)
                broker.reconcile_from_account_details()
                append_progress(
                    self.output_root,
                    "OANDA reconcile lastTransactionID=%s"
                    % getattr(broker, "last_transaction_id", None),
                )
            except Exception as exc:
                append_progress(self.output_root, "WARN reconcile failed: %s" % exc)
        containment_bootstrap(self, append_progress_fn=append_progress)

    def _inject_st_events(self, *, force: bool = False) -> int:
        now = float(self._clock())
        if not force and (now - self._last_st_poll_at) < ST_POLL_SECONDS:
            return 0
        self._last_st_poll_at = now
        fresh = collect_st_events(self.spec, seed_research=False)
        # Keep research seed + prior live events already in plugin/config.
        rows = self.store.read_table("strategy_instances")
        if not rows:
            return 0
        row = dict(rows[0])
        try:
            cfg = json.loads(row.get("config_json") or "{}")
        except json.JSONDecodeError:
            cfg = {}
        existing = cfg.get("dynamic_sizing_events") or {}
        merged = merge_st_events(existing, fresh)
        before = sum(len(v) for v in existing.values())
        after = sum(len(v) for v in merged.values())
        if after == before and not force:
            return 0
        cfg["dynamic_sizing_events"] = merged
        row["config_json"] = json.dumps(cfg, sort_keys=True)
        self.store.upsert_row("strategy_instances", "strategy_id", row)
        plugin = self.engine.manager.plugins.get(self.spec.strategy_id)
        if plugin is not None:
            plugin.config["dynamic_sizing_events"] = merged
        persist_st_events(self.output_root, merged)
        added = after - before
        if added > 0:
            self.st_injects += 1
            append_progress(
                self.output_root,
                "st_events inject +%d total_events=%d sessions=%d"
                % (added, after, len(merged)),
            )
            # Force a gate row so arm/disarm flips are visible when ST lands mid-session.
            tip_bars = self.store.read_bars(self.spec.instrument, "1m")
            tip_ts = tip_bars[-1].ts if tip_bars else utc_now_iso()
            try:
                self._maybe_gate_audit(str(tip_ts), force=True)
            except Exception as exc:
                append_progress(self.output_root, "WARN post-inject gate_audit failed: %s" % exc)
        return added

    def _maybe_gate_audit(self, bar_ts: str, *, force: bool = False, recent_fill_reason: str = "") -> None:
        now = float(self._clock())
        if (
            not force
            and (now - self._last_gate_audit_at) < GATE_AUDIT_SECONDS
            and not self._session_changed(bar_ts)
            and not recent_fill_reason
        ):
            return
        self._last_gate_audit_at = now
        plugin = self.engine.manager.plugins.get(self.spec.strategy_id)
        if plugin is None:
            return
        open_orders = self._strategy_open_orders()
        pos_qty = self._strategy_position_qty()
        row = build_gate_audit_row(
            spec=self.spec,
            plugin=plugin,
            bar_ts=bar_ts,
            open_orders=open_orders,
            position_qty=pos_qty,
            recent_fill_reason=recent_fill_reason,
        )
        fingerprint = "|".join(
            str(row.get(k))
            for k in (
                "session_date",
                "gate_arm_decision",
                "oco_state",
                "prior_opposed_long_ok",
                "prior_opposed_short_ok",
                "position_qty",
                "open_entry_orders",
                "skip_reason",
                "st_events_today",
                "fill_result",
            )
        )
        if fingerprint == self._last_audit_fingerprint and not force:
            return
        self._last_audit_fingerprint = fingerprint
        append_gate_audit(self.output_root, row)
        append_progress(
            self.output_root,
            "gate session=%s decision=%s oco=%s long_ok=%s short_ok=%s st_today=%s fill=%s skip=%s"
            % (
                row["session_date"],
                row["gate_arm_decision"],
                row["oco_state"],
                row["prior_opposed_long_ok"],
                row["prior_opposed_short_ok"],
                row["st_events_today"],
                row["fill_result"] or "-",
                row["skip_reason"] or "-",
            ),
        )

    def _session_changed(self, bar_ts: str) -> bool:
        sess = _ny_date_iso(bar_ts)
        if sess != self._session_day:
            self._session_day = sess
            return True
        return False

    def _poll_account_changes(self) -> int:
        if not self.spec.oanda_routing or self.client is None:
            return 0
        from .oanda_v2b_ungated_common import poll_account_changes

        now = float(self._clock())
        if (now - self._last_changes_poll_at) < ACCOUNT_CHANGES_POLL_SECONDS:
            return 0
        self._last_changes_poll_at = now
        n = poll_account_changes(self.engine, self.client, instrument=self.spec.instrument)
        self.fills_from_oanda += n
        containment_poll(self, append_progress_fn=append_progress)
        return n

    def on_price_tick(
        self,
        *,
        bid: float,
        ask: float,
        mid: Optional[float],
        ts: str,
        quantity: float = 0.0,
        raw: Optional[Dict[str, Any]] = None,
    ) -> None:
        del raw
        self.ticks_logged += 1
        containment_note_activity(self)
        self._inject_st_events()
        self._poll_account_changes()
        for bar in self.builder.on_quote(ts=ts, bid=bid, ask=ask, mid=mid, quantity=quantity):
            self._handle_bar(bar)
        self._maybe_heartbeat()

    def _handle_bar(self, bar: Any) -> None:
        self.bars_1m += 1
        # Drive engine for London + buffer so OR build / EOD flatten fire.
        wall = _ny_wall(bar.ts)
        clock = wall.timetz().replace(tzinfo=None)
        if dt_time(2, 45) <= clock <= dt_time(12, 10):
            self.engine.process_bar(bar)
            self.bars_engine += 1
            new_fills = self._new_strategy_fills()
            if new_fills:
                for fill in new_fills:
                    reason = "fill:%s:%s:qty=%s@%s" % (
                        fill.get("reason") or "unknown",
                        fill.get("side") or "",
                        fill.get("quantity") or "",
                        fill.get("price") or "",
                    )
                    self._maybe_gate_audit(
                        fill.get("ts") or bar.ts,
                        force=True,
                        recent_fill_reason=reason,
                    )
                    append_progress(
                        self.output_root,
                        "FILL %s id=%s ts=%s" % (reason, fill.get("fill_id"), fill.get("ts")),
                    )
            else:
                self._maybe_gate_audit(bar.ts)
        else:
            # Still refresh ST gate audit outside London window (skip reasons).
            self._maybe_gate_audit(bar.ts)


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


def status_daemon(output_root: Path, *, spec: LondonPriorOpposedSpec) -> int:
    pid = read_pid(output_root)
    alive = bool(pid and pid_is_alive(pid))
    meta: Dict[str, Any] = {}
    if run_meta_path(output_root).exists():
        try:
            meta = json.loads(run_meta_path(output_root).read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    print(
        "pid=%s alive=%s started_at=%s state=%s routing=%s size_mult=%s book=%s st_feed=%s"
        % (
            pid,
            alive,
            meta.get("started_at"),
            state_root_for(output_root),
            spec.oanda_routing,
            spec.size_mult,
            spec.book,
            spec.st_feed_dirname,
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


def spawn_daemon(
    *,
    spec: LondonPriorOpposedSpec,
    output_root: Path,
    max_ticks: int = 0,
    oanda_config_path: str = "",
) -> int:
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
    spec: LondonPriorOpposedSpec,
    output_root: Optional[Path] = None,
    config: Optional[OandaConfig] = None,
    max_ticks: int = 0,
    reconnect_initial_seconds: float = 2.0,
    reconnect_max_seconds: float = 60.0,
    price_source: str = PRICE_SOURCE,
) -> int:
    """Run the demo.

    ``price_source``:
      - ``st_feed_bars`` (default): poll sibling ST+PMC demo 1m bars — no extra
        OANDA pricing stream (important under practice stream caps).
      - ``pricing_stream``: open a dedicated US30 pricing stream.
    """
    from .oanda_v2b_ungated_common import (
        _interruptible_sleep,
        _log_stream_error,
        _price_levels,
        _remove_pidfile,
    )

    cfg = config or oanda_config_from_env()
    cfg.validate_for_network()
    root = Path(output_root) if output_root is not None else default_output_root(spec)
    root.mkdir(parents=True, exist_ok=True)
    if str(cfg.env).lower() != "practice":
        append_progress(root, "REFUSING non-practice OANDA_ENV=%s" % cfg.env)
        return 2

    meta = write_run_meta(root, spec=spec, config=cfg)
    meta["price_source"] = price_source
    run_meta_path(root).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runner = DemoLondonPriorOpposedRunner(spec, output_root=root, config=cfg)
    runner.bootstrap_reconcile()
    runner._inject_st_events(force=True)
    pidfile_path(root).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    append_progress(
        root,
        "STARTED %s routing=%s size_mult=%.2f book=%s st_feed=%s price_source=%s account=%s pid=%s"
        % (
            spec.strategy_id,
            spec.oanda_routing,
            spec.size_mult,
            spec.book,
            spec.st_feed_dirname,
            price_source,
            cfg.account_id,
            os.getpid(),
        ),
    )
    append_progress(
        root,
        "RUN_META %s"
        % json.dumps(
            {
                k: meta[k]
                for k in (
                    "started_at",
                    "book",
                    "size_mult",
                    "prior_opposite_only",
                    "oanda_env",
                    "oanda_routing",
                    "st_feed",
                    "price_source",
                )
                if k in meta
            },
            sort_keys=True,
        ),
    )

    signal.signal(signal.SIGINT, runner.request_stop)
    signal.signal(signal.SIGTERM, runner.request_stop)

    exit_code = 0
    price_ticks = 0
    reconnect_attempt = 0

    try:
        if price_source == "st_feed_bars":
            exit_code, price_ticks = _run_st_feed_bar_loop(
                spec=spec,
                root=root,
                runner=runner,
                max_ticks=max_ticks,
            )
        else:
            exit_code, price_ticks, reconnect_attempt = _run_pricing_stream_loop(
                spec=spec,
                root=root,
                runner=runner,
                cfg=cfg,
                max_ticks=max_ticks,
                reconnect_initial_seconds=reconnect_initial_seconds,
                reconnect_max_seconds=reconnect_max_seconds,
                _interruptible_sleep=_interruptible_sleep,
                _log_stream_error=_log_stream_error,
                _price_levels=_price_levels,
            )
    except Exception as fatal_exc:
        _log_stream_error(root, runner.store, stage="fatal", exc=fatal_exc)
        exit_code = 1
    finally:
        runner.flush()
        append_progress(
            root,
            "STOPPED ticks=%d bars=%d st_injects=%d reconnect_attempts=%d"
            % (price_ticks, runner.bars_engine, runner.st_injects, reconnect_attempt),
        )
        _remove_pidfile(root)
    return exit_code


def _run_st_feed_bar_loop(
    *,
    spec: LondonPriorOpposedSpec,
    root: Path,
    runner: DemoLondonPriorOpposedRunner,
    max_ticks: int,
) -> Tuple[int, int]:
    """Poll sibling ST demo 1m bars and drive the London prior-opposed engine."""
    feed = FlatFileStore(st_feed_root(spec))
    seen: set = set()
    # Seed cursor near tip so we don't replay entire ST history through the engine.
    existing = feed.read_bars(spec.instrument, "1m")
    if len(existing) > 5:
        for b in existing[:-2]:
            seen.add(str(b.ts))
    append_progress(
        root,
        "price_source=st_feed_bars feed=%s primed_seen=%d tip=%s"
        % (spec.st_feed_dirname, len(seen), existing[-1].ts if existing else "none"),
    )
    # Snapshot gate state immediately (London may be closed; still records ST feed / skip).
    if existing:
        try:
            runner._maybe_gate_audit(str(existing[-1].ts))
            # Force fingerprint refresh on first poll by clearing so a second write can happen
            # when session state changes.
        except Exception as exc:
            append_progress(root, "WARN initial gate_audit failed: %s" % exc)
    price_ticks = 0
    idle_loops = 0
    while not runner.stop_requested:
        runner._inject_st_events()
        runner._poll_account_changes()
        containment_note_activity(runner)
        bars = feed.read_bars(spec.instrument, "1m")
        # Only scan the tip — full history was primed into ``seen``.
        new_bars = [b for b in bars[-80:] if str(b.ts) not in seen]
        if not new_bars:
            idle_loops += 1
            if idle_loops % 30 == 1:
                runner._maybe_heartbeat()
            time.sleep(BAR_POLL_SECONDS)
            continue
        idle_loops = 0
        for bar in new_bars:
            if runner.stop_requested:
                break
            seen.add(str(bar.ts))
            # Persist into our own store for audit / reconcile.
            try:
                runner.store.append_bar(bar)
            except Exception:
                pass
            runner._handle_bar(bar)
            price_ticks += 1
            if max_ticks and price_ticks >= max_ticks:
                append_progress(root, "max_ticks=%d reached; stopping" % max_ticks)
                runner.request_stop()
                break
        runner._maybe_heartbeat()
    return 0, price_ticks


def _run_pricing_stream_loop(
    *,
    spec: LondonPriorOpposedSpec,
    root: Path,
    runner: DemoLondonPriorOpposedRunner,
    cfg: OandaConfig,
    max_ticks: int,
    reconnect_initial_seconds: float,
    reconnect_max_seconds: float,
    _interruptible_sleep,
    _log_stream_error,
    _price_levels,
) -> Tuple[int, int, int]:
    client = runner.client
    oanda_name = cfg.symbol_for(spec.instrument)
    price_ticks = 0
    reconnect_attempt = 0
    backoff = float(reconnect_initial_seconds)
    exit_code = 0

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
            backoff = next_stream_backoff(backoff, reconnect_max_seconds, open_exc)
            continue

        append_progress(root, "STREAM connected attempt=%d status=200" % reconnect_attempt)
        containment_on_reconnect(runner, append_progress_fn=append_progress)
        backoff = float(reconnect_initial_seconds)
        session_ticks = 0
        try:
            for msg_type, msg in response.parts():
                if runner.stop_requested:
                    break
                if msg_type == "pricing.PricingHeartbeat" or getattr(msg, "type", None) == "HEARTBEAT":
                    containment_note_activity(runner)
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
                extra={
                    "attempt": reconnect_attempt,
                    "session_ticks": session_ticks,
                    "total_ticks": price_ticks,
                },
            )
            if runner.stop_requested:
                break
            append_progress(root, "RECONNECT sleeping %.1fs after stream_read failure" % backoff)
            _interruptible_sleep(runner, backoff)
            backoff = next_stream_backoff(backoff, reconnect_max_seconds, stream_exc)
            continue

        if runner.stop_requested:
            break
        append_progress(
            root,
            "WARN stream ended without error attempt=%d session_ticks=%d; reconnecting in %.1fs"
            % (reconnect_attempt, session_ticks, backoff),
        )
        _interruptible_sleep(runner, backoff)
        backoff = next_stream_backoff(backoff, reconnect_max_seconds)
    return exit_code, price_ticks, reconnect_attempt
