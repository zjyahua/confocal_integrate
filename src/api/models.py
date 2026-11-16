"""Shared data structures for the experiment API."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_DRY = "dry-run"
STATE_FAILED = "failed"
STATE_STOPPED = "stopped"


@dataclass
class Job:
    """One submitted experiment."""

    kind: str                      # "confocal_scan" or "point_scan"
    params: dict
    out_dir: str
    job_id: str = field(
        default_factory=lambda: time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    )
    state: str = STATE_QUEUED
    dry_run: bool = False
    created: float = field(default_factory=time.time)
    started: float = 0.0
    finished: float = 0.0
    progress: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    files: list = field(default_factory=list)
    error: str = ""
    stop_requested: bool = False

    @property
    def elapsed(self) -> float:
        now = self.finished or (time.time() if self.started else self.created)
        return round(now - (self.started or self.created), 2)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["elapsed"] = self.elapsed
        return data

    @staticmethod
    def from_dict(data: dict) -> "Job":
        allowed = {f for f in Job.__dataclass_fields__}  # type: ignore[attr-defined]
        return Job(**{k: v for k, v in data.items() if k in allowed})


def new_job(kind: str, params: dict, out_dir: str, dry_run: bool = False) -> Job:
    return Job(kind=kind, params=params, out_dir=out_dir, dry_run=dry_run)
