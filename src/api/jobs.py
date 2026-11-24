"""Background job runner shared by the CLI and the HTTP service."""

from __future__ import annotations

import json
import os
import threading
import time

from src.api import logs, models
from src.api.paths import default_out_dir, is_data_kind
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
        if out_dir is None:
            out_dir = default_out_dir(kind) if is_data_kind(kind) else ""

        job = models.new_job(kind, params, out_dir, dry_run=dry_run)

        with self._lock:
            self._jobs[job.job_id] = job

        logs.write(
            kind,
            "START %s job=%s dry_run=%s out=%s"
            % (kind, job.job_id, dry_run, out_dir or "-"),
            params,
        )

        self._record_history(job)

        thread = threading.Thread(target=self._execute, args=(job,), daemon=True)
        self._threads[job.job_id] = thread
        thread.start()
        return job

    @staticmethod
    def _record_history(job):
        """Keep a copy on disk so status/result work without a service."""
        try:
            from src.api import history

            data = job.to_dict()

            # summary.json is written after job.files was captured, so list the
            # directory again here
            if job.out_dir and os.path.isdir(job.out_dir):
                data["files"] = sorted(os.listdir(job.out_dir))

            history.record(data)
        except Exception as exc:  # noqa: BLE001 - history must never break a run
            print("local job history failed: %s" % exc)

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

        data_job = is_data_kind(job.kind) and bool(job.out_dir)

        # record the running state so status/stop can see the job from outside
        self._record_history(job)

        if data_job:
            os.makedirs(job.out_dir, exist_ok=True)

        try:
            if data_job:
                self._write(job, "params.json", job.params)

            plan = build_plan(job.kind, job.params)
            job.progress = {"phase": "plan", "plan": plan}

            if data_job:
                self._write(job, "plan.json", plan)

            logs.write(
                job.kind,
                "PLAN %s job=%s ok=%s estimate=%ss"
                % (job.kind, job.job_id, plan.get("ok"), plan.get("estimate_s")),
                plan.get("warnings") or None,
            )

            if not plan["ok"]:
                raise ValueError("; ".join(plan["errors"]))

            if job.dry_run:
                job.summary = plan
                job.files = ["params.json", "plan.json"] if data_job else []
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
            job.files = sorted(os.listdir(job.out_dir)) if data_job else []
            # a STOP file leaves the collected data in place but marks the run
            job.state = (
                models.STATE_STOPPED if job.stop_requested else models.STATE_DONE
            )

        except Exception as exc:  # noqa: BLE001 - reported to the caller
            job.error = "%s: %s" % (type(exc).__name__, exc)
            job.state = models.STATE_STOPPED if job.stop_requested else models.STATE_FAILED
        finally:
            job.finished = time.time()

            if data_job:
                self._write(job, "summary.json", job.summary or {"error": job.error})

            logs.write(
                job.kind,
                "END %s job=%s state=%s elapsed=%.1fs%s"
                % (
                    job.kind,
                    job.job_id,
                    job.state,
                    job.elapsed,
                    (" error=" + job.error) if job.error else "",
                ),
                job.summary or None,
            )

            self._record_history(job)

    @staticmethod
    def _write(job, name, payload):
        os.makedirs(job.out_dir, exist_ok=True)
        path = os.path.join(job.out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)


def local_runner():
    """Return a runner used when no service is running (CLI fallback)."""
    return JobRunner(executor=None)
