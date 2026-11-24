"""Local job history.

The control service keeps its jobs in memory, which disappears with the
process.  When the CLI executes a job in-process there is no service at all,
so every job is also appended to ``<repo>/.api_jobs.json`` (git-ignored).
That is what `status` and `result` read when no service is running.
"""

from __future__ import annotations

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HISTORY_PATH = os.path.join(REPO_ROOT, ".api_jobs.json")

MAX_ENTRIES = 50


def load():
    """Return the recorded jobs, newest first (empty list when unreadable)."""
    try:
        with open(HISTORY_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []

    return data if isinstance(data, list) else []


def save(jobs):
    """Write the history atomically, keeping only the newest entries."""
    tmp_path = HISTORY_PATH + ".tmp"

    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(jobs[:MAX_ENTRIES], handle, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, HISTORY_PATH)
    except OSError as exc:  # history is best effort, never break a run
        print("local job history not written: %s" % exc)


def record(job):
    """Insert or update one job dict and keep the newest MAX_ENTRIES."""
    if not isinstance(job, dict) or not job.get("job_id"):
        return

    jobs = [item for item in load() if item.get("job_id") != job["job_id"]]
    jobs.insert(0, job)
    save(jobs)


def recent(limit=10):
    return load()[: int(limit)]


def get(job_id):
    for job in load():
        if job.get("job_id") == job_id:
            return job
    return None
