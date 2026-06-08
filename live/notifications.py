from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .models import Alert, as_row, utc_now_iso
from .store import FlatFileStore


class NotificationSink:
    def send(self, alert: Alert) -> None:
        raise NotImplementedError


class DiskNotificationSink(NotificationSink):
    def __init__(self, store: FlatFileStore):
        self.store = store
        self.store.ensure()

    def send(self, alert: Alert) -> None:
        path = self.store.outbox_dir / "notifications.jsonl"
        row = as_row(alert)
        row["sent_at"] = utc_now_iso()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        self.store.upsert_row("alerts", "alert_id", dict(row, status="sent"))
        self.store.append_event("notifications", row)


class EmailNotificationStub(NotificationSink):
    def __init__(self, store: FlatFileStore):
        self.store = store

    def send(self, alert: Alert) -> None:
        self.store.append_event("email_stub", dict(as_row(alert), sent_at=utc_now_iso()))


class SmsNotificationStub(NotificationSink):
    def __init__(self, store: FlatFileStore):
        self.store = store

    def send(self, alert: Alert) -> None:
        self.store.append_event("sms_stub", dict(as_row(alert), sent_at=utc_now_iso()))


class NullNotificationSink(NotificationSink):
    def send(self, alert: Alert) -> None:
        return None
