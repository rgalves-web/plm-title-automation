"""In-process background jobs — the operator never chooses a timeout.

The source-truth gate re-reads every cited document by OCR and takes minutes
(assessment §3.4). It must not block the RUN request. Jobs run on daemon threads
and the UI polls their status; the long OCR window is the flow layer's concern,
not the operator's patience (blueprint §5).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    kind: str
    unit: str
    status: str = "running"          # running | done | error
    progress: str = ""
    result: dict[str, Any] | None = None
    error: str = ""
    started_at: str = field(default_factory=_now)
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "unit": self.unit,
            "status": self.status, "progress": self.progress,
            "result": self.result, "error": self.error,
            "started_at": self.started_at, "finished_at": self.finished_at,
        }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, unit: str, fn: Callable[[Job], dict[str, Any]]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, unit=unit)
        with self._lock:
            self._jobs[job.id] = job

        def _run() -> None:
            try:
                result = fn(job)
                with self._lock:
                    job.result = result
                    job.status = "done"
                    job.finished_at = _now()
            except Exception as exc:  # noqa: BLE001 — surface honestly, never crash the server
                with self._lock:
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.status = "error"
                    job.finished_at = _now()

        threading.Thread(target=_run, name=f"job-{kind}-{unit}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def latest_for(self, unit: str, kind: str) -> Job | None:
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.unit == unit and j.kind == kind]
        return max(jobs, key=lambda j: j.started_at) if jobs else None
