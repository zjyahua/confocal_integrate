"""Background job runner shared by the CLI and the HTTP service."""

from __future__ import annotations

import json
import os
import threading
import time

from src.api import models
from src.api.paths import default_out_dir
from src.api.plan import build_plan


class JobRunner:
    """Keeps the job table and executes jobs one at a time.

    The runner never touches hardware itself.  A real scan is delegated to
    ``executor(job)`` which is injected by the caller (the GUI integration or
    the headless scan module).  Without an executor only dry runs work.
    """

    def __init__(self, executor=None, hardware_lock=None):
        self.executor = executor
        self.hardware_lock = hardware_lock or threading.Lock()
        self._jobs = {}
        self._lock = threading.Lock()
        self._threads = {}

    # ------------------------------------------------------------------ api
    def submit(self, kind, params, out_dir=None, dry_run=False):
        out_dir = out_dir or default_out_dir()
        job = models.new_job(kind, params, out_dir, dry_run=dry_run)

        with self._lock:
            self._jobs[job.job_id] = job

        thread = threading.Thread(target=self._execute, args=(job,), daemon=True)
        self._threads[job.job_id] = thread
        thread.start()
        return job

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit=20):
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
        return jobs[:limit]

    def stop(self, job_id):
        job = self.get(job_id)
        if job is None:
            return False
        job.stop_requested = True
        try:
            from src.api.execute import request_stop

            request_stop(job_id)
        except Exception:  # noqa: BLE001 - stopping is best effort
            pass
        return True

    # ------------------------------------------------------------ execution
    def _execute(self, job):
        job.state = models.STATE_RUNNING
        job.started = time.time()
        os.makedirs(job.out_dir, exist_ok=True)

        try:
            self._write(job, "params.json", job.params)

            plan = build_plan(job.kind, job.params)
            job.progress = {"phase": "plan", "plan": plan}
            self._write(job, "plan.json", plan)

            if not plan["ok"]:
                raise ValueError("; ".join(plan["errors"]))

            if job.dry_run:
                job.summary = plan
                job.files = ["params.json", "plan.json"]
                job.state = models.STATE_DRY
                return

            if self.executor is None:
                raise NotImplementedError(
                    "no executor wired yet: real scans need hardware support, "
                    "run with --dry-run for now"
                )

            if not self.hardware_lock.acquire(timeout=5):
                raise RuntimeError("hardware is busy with another job")

            try:
                result = self.executor(job)
            finally:
                self.hardware_lock.release()

            job.summary = result or {}
            job.files = sorted(os.listdir(job.out_dir))
            job.state = models.STATE_DONE

        except Exception as exc:  # noqa: BLE001 - reported to the caller
            job.error = "%s: %s" % (type(exc).__name__, exc)
            job.state = models.STATE_STOPPED if job.stop_requested else models.STATE_FAILED
        finally:
            job.finished = time.time()
            self._write(job, "summary.json", job.summary or {"error": job.error})

    @staticmethod
    def _write(job, name, payload):
        os.makedirs(job.out_dir, exist_ok=True)
        path = os.path.join(job.out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)


def local_runner():
    """Return a runner used when no service is running (CLI fallback)."""
    return JobRunner(executor=None)
