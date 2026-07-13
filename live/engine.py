from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .broker import BaseBroker, PaperBroker
from .causality import AUDIT, CausalityGuard
from .jobs import JobQueue
from .manager import StrategyManager
from .models import Bar, utc_now_iso
from .notifications import DiskNotificationSink, NotificationSink
from .reporting import generate_market_close_report
from .risk import RiskManager
from .spread_model import SpreadModel
from .store import FlatFileStore, default_state_root
from .supervisor import RuntimeSupervisor
from .verification import SpoofVerificationProvider, VerificationProvider


class Engine:
    def __init__(
        self,
        store: Optional[FlatFileStore] = None,
        broker: Optional[BaseBroker] = None,
        manager: Optional[StrategyManager] = None,
        persist_bars: bool = True,
        persist_health: bool = True,
        slippage_ticks: float = 0.0,
        tick_size: Optional[Dict[str, float]] = None,
        strict_moc: bool = False,
        spread_model: Optional[SpreadModel] = None,
        directional_adverse_path: bool = True,
        notification_sink: Optional[NotificationSink] = None,
        verification_provider: Optional[VerificationProvider] = None,
        emit_order_alerts: bool = True,
        broker_log_events: bool = True,
        broker_persist_modifications: bool = True,
        runtime_supervisor: Optional[RuntimeSupervisor] = None,
        causality_mode: str = AUDIT,
        causality_guard: Optional[CausalityGuard] = None,
    ):
        self.store = store or FlatFileStore(default_state_root())
        self.store.ensure()
        self.persist_bars = persist_bars
        self.persist_health = persist_health
        self.broker = broker or PaperBroker(
            self.store,
            slippage_ticks=slippage_ticks,
            tick_size=tick_size,
            strict_moc=strict_moc,
            spread_model=spread_model,
            directional_adverse_path=directional_adverse_path,
            log_events=broker_log_events,
            persist_modifications=broker_persist_modifications,
        )
        self.runtime_supervisor = runtime_supervisor
        self.causality_guard = causality_guard or CausalityGuard(self.store, mode=causality_mode)
        self.jobs = JobQueue(self.store)
        self.notifications = notification_sink or DiskNotificationSink(self.store)
        self.manager = manager or StrategyManager(
            store=self.store,
            broker=self.broker,
            risk=RiskManager(self.store, supervisor=self.runtime_supervisor),
            verification=verification_provider or SpoofVerificationProvider(self.store),
            notifications=self.notifications,
            emit_order_alerts=emit_order_alerts,
            causality_guard=self.causality_guard,
        )

    def process_bar(self, bar: Bar) -> None:
        if self.persist_bars:
            self.store.append_bar(bar)
        process_bar = getattr(self.broker, "process_bar", None)
        process_market_close_bar = getattr(self.broker, "process_market_close_bar", None)
        for _ in range(20):
            fills = process_bar(bar) if callable(process_bar) else []
            if not fills:
                break
            self.manager.on_fills(fills)
        self.manager.on_bar_close(bar)
        for _ in range(20):
            fills = process_bar(bar) if callable(process_bar) else []
            if not fills:
                break
            self.manager.on_fills(fills)
        close_fills = process_market_close_bar(bar) if callable(process_market_close_bar) else []
        if close_fills:
            self.manager.on_fills(close_fills)
        if self.persist_health:
            self.store.write_json(
                "health.json",
                {
                    "status": "ok",
                    "updated_at": utc_now_iso(),
                    "last_bar": bar.ts,
                    "instrument": bar.instrument,
                    "timeframe": bar.timeframe,
                },
            )

    def run_pending_jobs(self, limit: int = 100) -> int:
        processed = 0
        for job in self.jobs.pending()[:limit]:
            job_id = job["job_id"]
            self.jobs.mark_running(job_id)
            try:
                self._run_job(job)
                self.jobs.mark_done(job_id)
                processed += 1
            except Exception as exc:
                self.jobs.mark_failed(job_id, str(exc))
        return processed

    def _run_job(self, job: Dict[str, str]) -> None:
        payload = json.loads(job.get("payload_json") or "{}")
        job_type = job.get("job_type")
        if job_type == "bar_close":
            self.process_bar(Bar.from_row(payload))
        elif job_type == "generate_report":
            generate_market_close_report(self.store, payload.get("report_date", ""))
        elif job_type == "healthcheck":
            self.store.write_json("health.json", {"status": "ok", "updated_at": utc_now_iso()})
        elif job_type in {"reconcile_orders", "reconcile_positions", "send_alerts", "market_data_refresh", "daily_close_update", "evaluate_strategy", "place_order_intent"}:
            # v0 placeholder: the replay path performs these directly.
            self.store.append_event("jobs", {"event": "noop", "job_type": job_type, "job_id": job.get("job_id")})
        else:
            raise ValueError("Unknown job type: %s" % job_type)

    def replay_bars(self, bars: Iterable[Bar]) -> None:
        for bar in bars:
            self.process_bar(bar)


def bars_from_csv(path: Path, instrument: str, timeframe: str, source: str = "") -> List[Bar]:
    import csv

    rows: List[Bar] = []
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            ts = raw.get("ts") or raw.get("timestamp") or raw.get("date") or raw.get("datetime")
            if not ts:
                raise ValueError("CSV row missing ts/timestamp/date/datetime")
            rows.append(
                Bar(
                    instrument=instrument,
                    timeframe=timeframe,
                    ts=str(ts),
                    open=float(raw.get("open") or raw.get("Open")),
                    high=float(raw.get("high") or raw.get("High")),
                    low=float(raw.get("low") or raw.get("Low")),
                    close=float(raw.get("close") or raw.get("Close")),
                    volume=float(raw.get("volume") or raw.get("Volume") or 0.0),
                    complete=True,
                    source=source or str(path),
                )
            )
    return rows
