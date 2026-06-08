from __future__ import annotations

from typing import Dict, List

from .models import Job, as_row, utc_now_iso
from .store import FlatFileStore


class JobQueue:
    def __init__(self, store: FlatFileStore):
        self.store = store
        self.store.ensure()

    def enqueue(self, job_type: str, payload_json: str = "{}", scheduled_for: str = "") -> Job:
        job = Job.create(job_type=job_type, payload_json=payload_json, scheduled_for=scheduled_for)
        self.store.add_job(job)
        return job

    def pending(self) -> List[Dict[str, str]]:
        rows = [row for row in self.store.read_table("jobs") if row.get("status") == "pending"]
        return sorted(rows, key=lambda r: (r.get("scheduled_for", ""), r.get("created_at", "")))

    def mark_running(self, job_id: str) -> None:
        self._mark(job_id, "running")

    def mark_done(self, job_id: str) -> None:
        self._mark(job_id, "done")

    def mark_failed(self, job_id: str, error: str) -> None:
        self.store.update_job_status(job_id, "failed", last_error=error)

    def _mark(self, job_id: str, status: str) -> None:
        rows = self.store.read_table("jobs")
        for row in rows:
            if row.get("job_id") == job_id:
                row["status"] = status
                row["updated_at"] = utc_now_iso()
        self.store.write_table("jobs", rows)
