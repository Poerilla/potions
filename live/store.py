from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import (
    Alert,
    Bar,
    BrokerOrder,
    Fill,
    Job,
    LevelUpdate,
    OrderIntent,
    Position,
    StrategyInstance,
    VerificationRequest,
    as_row,
    utc_now_iso,
)


TABLE_SCHEMAS: Dict[str, Sequence[str]] = {
    "levels": (
        "strategy_id",
        "instrument",
        "level_name",
        "price",
        "active_from",
        "active_to",
        "metadata_json",
    ),
    "strategy_instances": (
        "strategy_id",
        "strategy_type",
        "version",
        "instrument",
        "broker_instrument",
        "account_mode",
        "enabled",
        "timeframes",
        "max_contracts",
        "max_open_orders",
        "config_json",
    ),
    "strategy_state": ("strategy_id", "state_json", "updated_at"),
    "order_intents": (
        "intent_id",
        "strategy_id",
        "trade_id",
        "instrument",
        "account_mode",
        "side",
        "order_type",
        "quantity",
        "limit_price",
        "stop_price",
        "reason",
        "status",
        "requires_verification",
        "verification_id",
        "parent_intent_id",
        "reduce_only",
        "bracket_role",
        "bracket_stop_price",
        "bracket_target_price",
        "oco_group",
        "tif",
        "live_after_ts",
        "expires_after_ts",
        "created_at",
        "updated_at",
    ),
    "orders": (
        "broker_order_id",
        "intent_id",
        "strategy_id",
        "trade_id",
        "instrument",
        "account_mode",
        "side",
        "order_type",
        "quantity",
        "remaining_quantity",
        "status",
        "limit_price",
        "stop_price",
        "reduce_only",
        "bracket_role",
        "parent_order_id",
        "oco_group",
        "live_after_ts",
        "expires_after_ts",
        "created_at",
        "updated_at",
    ),
    "fills": (
        "fill_id",
        "broker_order_id",
        "intent_id",
        "strategy_id",
        "trade_id",
        "instrument",
        "account_mode",
        "side",
        "quantity",
        "price",
        "ts",
        "reason",
        "mid_price",
        "bid_price",
        "ask_price",
        "spread",
    ),
    "positions": (
        "position_id",
        "strategy_id",
        "instrument",
        "account_mode",
        "quantity",
        "avg_price",
        "realized_pnl",
        "updated_at",
    ),
    "jobs": (
        "job_id",
        "job_type",
        "status",
        "scheduled_for",
        "payload_json",
        "attempts",
        "last_error",
        "created_at",
        "updated_at",
    ),
    "alerts": (
        "alert_id",
        "strategy_id",
        "level",
        "message",
        "payload_json",
        "status",
        "created_at",
    ),
    "pending_verifications": (
        "verification_id",
        "intent_id",
        "strategy_id",
        "account_mode",
        "status",
        "challenge",
        "created_at",
        "approved_at",
    ),
    "feature_snapshots": (
        "feature_name",
        "strategy_id",
        "instrument",
        "event_ts",
        "available_at_ts",
        "current_bar_ts",
        "source",
        "value_ref",
        "metadata_json",
    ),
    "causality_violations": (
        "violation_id",
        "strategy_id",
        "instrument",
        "violation_type",
        "current_bar_ts",
        "offending_ts",
        "severity",
        "action_taken",
        "feature_name",
        "intent_id",
        "scrutiny_classification",
        "details_json",
        "created_at",
    ),
}

BAR_SCHEMA = (
    "instrument",
    "timeframe",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "complete",
    "source",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "ask_open",
    "ask_high",
    "ask_low",
    "ask_close",
)


class FlatFileStore:
    def __init__(self, root: Path, defer_table_writes: bool = False):
        self.root = Path(root)
        self.bars_dir = self.root / "bars"
        self.events_dir = self.root / "events"
        self.reports_dir = self.root / "reports"
        self.outbox_dir = self.root / "outbox"
        self.defer_table_writes = defer_table_writes
        self._table_cache: Dict[str, List[Dict[str, str]]] = {}
        self._table_index_cache: Dict[tuple[str, str], Dict[str, int]] = {}

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.bars_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        for table, columns in TABLE_SCHEMAS.items():
            path = self.table_path(table)
            if not path.exists() and table not in self._table_cache:
                self.write_table(table, [], columns=columns)
        health = self.root / "health.json"
        if not health.exists():
            self.write_json("health.json", {"status": "init", "updated_at": utc_now_iso()})

    def table_path(self, table: str) -> Path:
        if table not in TABLE_SCHEMAS:
            raise KeyError("Unknown table: %s" % table)
        return self.root / ("%s.csv" % table)

    def bars_path(self, instrument: str, timeframe: str) -> Path:
        safe = ("%s_%s" % (instrument, timeframe)).replace("/", "_").replace(" ", "_")
        return self.bars_dir / ("%s.csv" % safe)

    def read_table(self, table: str) -> List[Dict[str, str]]:
        if table in self._table_cache:
            return [dict(row) for row in self._table_cache[table]]
        path = self.table_path(table)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if self.defer_table_writes:
            self._table_cache[table] = [dict(row) for row in rows]
        return rows

    def write_table(
        self,
        table: str,
        rows: Iterable[Dict[str, Any]],
        columns: Optional[Sequence[str]] = None,
    ) -> None:
        columns = tuple(columns or TABLE_SCHEMAS[table])
        materialized = [{k: "" if v is None else str(v) for k, v in row.items()} for row in rows]
        if self.defer_table_writes:
            self._table_cache[table] = materialized
            for cache_key in list(self._table_index_cache):
                if cache_key[0] == table:
                    del self._table_index_cache[cache_key]
            return
        path = self.table_path(table)
        self._atomic_write_csv(path, materialized, columns)

    def append_rows(self, table: str, rows: Iterable[Dict[str, Any]]) -> None:
        materialized = [{k: "" if v is None else str(v) for k, v in row.items()} for row in rows]
        if self.defer_table_writes:
            if table not in self._table_cache:
                self.read_table(table)
            existing = self._table_cache.setdefault(table, [])
            start = len(existing)
            existing.extend(materialized)
            for (indexed_table, key), index in list(self._table_index_cache.items()):
                if indexed_table != table:
                    continue
                for offset, item in enumerate(materialized):
                    if key in item:
                        index[str(item[key])] = start + offset
            return
        existing = self.read_table(table)
        existing.extend(materialized)
        self.write_table(table, existing)

    def upsert_row(self, table: str, key: str, row: Dict[str, Any]) -> None:
        normalized = {k: "" if v is None else str(v) for k, v in row.items()}
        value = str(normalized[key])
        if self.defer_table_writes:
            if table not in self._table_cache:
                self.read_table(table)
            rows = self._table_cache.setdefault(table, [])
            index = self._deferred_index(table, key)
            idx = index.get(value)
            if idx is not None:
                merged = dict(rows[idx])
                merged.update(normalized)
                rows[idx] = merged
                return
            index[value] = len(rows)
            rows.append(normalized)
            return
        rows = self.read_table(table)
        found = False
        out = []
        for old in rows:
            if str(old.get(key)) == value:
                merged = dict(old)
                merged.update(normalized)
                out.append(merged)
                found = True
            else:
                out.append(old)
        if not found:
            out.append(normalized)
        self.write_table(table, out)

    def append_event(self, stream: str, payload: Dict[str, Any]) -> None:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        row = dict(payload)
        row.setdefault("ts", utc_now_iso())
        path = self.events_dir / ("%s.jsonl" % stream)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def read_bars(self, instrument: str, timeframe: str) -> List[Bar]:
        path = self.bars_path(instrument, timeframe)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as fh:
            return [Bar.from_row(row) for row in csv.DictReader(fh)]

    def table_rows_view(self, table: str) -> List[Dict[str, str]]:
        if self.defer_table_writes:
            if table not in self._table_cache:
                self.read_table(table)
            return self._table_cache.setdefault(table, [])
        return self.read_table(table)

    def _deferred_index(self, table: str, key: str) -> Dict[str, int]:
        cache_key = (table, key)
        if cache_key not in self._table_index_cache:
            rows = self._table_cache.setdefault(table, [])
            self._table_index_cache[cache_key] = {
                str(row.get(key)): idx
                for idx, row in enumerate(rows)
                if key in row
            }
        return self._table_index_cache[cache_key]

    def write_bars(self, instrument: str, timeframe: str, bars: Iterable[Bar]) -> None:
        rows = [as_row(bar) for bar in bars]
        self._atomic_write_csv(self.bars_path(instrument, timeframe), rows, BAR_SCHEMA)

    def append_bar(self, bar: Bar) -> None:
        path = self.bars_path(bar.instrument, bar.timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(BAR_SCHEMA), extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow(as_row(bar))

    def load_strategy_instances(self) -> List[StrategyInstance]:
        return [StrategyInstance.from_row(row) for row in self.read_table("strategy_instances")]

    def load_orders(self) -> List[BrokerOrder]:
        return [BrokerOrder.from_row(row) for row in self.read_table("orders")]

    def load_order_intents(self) -> List[OrderIntent]:
        return [OrderIntent.from_row(row) for row in self.read_table("order_intents")]

    def load_positions(self) -> List[Position]:
        return [Position.from_row(row) for row in self.read_table("positions")]

    def add_alert(self, alert: Alert) -> None:
        self.append_rows("alerts", [as_row(alert)])
        self.append_event("alerts", as_row(alert))

    def add_level(self, level: LevelUpdate) -> None:
        self.append_rows("levels", [as_row(level)])
        self.append_event("levels", as_row(level))

    def add_job(self, job: Job) -> None:
        self.append_rows("jobs", [as_row(job)])

    def update_job_status(self, job_id: str, status: str, last_error: str = "") -> None:
        rows = self.read_table("jobs")
        for row in rows:
            if row.get("job_id") == job_id:
                row["status"] = status
                row["updated_at"] = utc_now_iso()
                if last_error:
                    row["last_error"] = last_error
                row["attempts"] = str(int(float(row.get("attempts") or 0)) + 1)
        self.write_table("jobs", rows)

    def get_state(self, strategy_id: str) -> Dict[str, Any]:
        for row in self.read_table("strategy_state"):
            if row.get("strategy_id") == strategy_id:
                try:
                    return json.loads(row.get("state_json") or "{}")
                except json.JSONDecodeError:
                    return {}
        return {}

    def put_state(self, strategy_id: str, state: Dict[str, Any]) -> None:
        self.upsert_row(
            "strategy_state",
            "strategy_id",
            {
                "strategy_id": strategy_id,
                "state_json": json.dumps(state, sort_keys=True),
                "updated_at": utc_now_iso(),
            },
        )

    def read_json(self, relative_path: str) -> Dict[str, Any]:
        path = self.root / relative_path
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, relative_path: str, data: Dict[str, Any]) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(str(tmp), str(path))

    def _atomic_write_csv(
        self,
        path: Path,
        rows: Iterable[Dict[str, Any]],
        columns: Sequence[str],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({col: "" if row.get(col) is None else row.get(col, "") for col in columns})
        os.replace(str(tmp), str(path))

    def flush_tables(self) -> None:
        for table, rows in list(self._table_cache.items()):
            self._atomic_write_csv(self.table_path(table), rows, TABLE_SCHEMAS[table])


def default_state_root() -> Path:
    return Path(__file__).resolve().parent / "state"
