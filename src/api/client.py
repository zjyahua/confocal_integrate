"""Thin HTTP client for the control service (standard library only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from src.api.server import read_endpoint


class ServiceClient:
    def __init__(self, port, token, host="127.0.0.1"):
        self.base = "http://%s:%d" % (host, port)
        self.token = token

    # ------------------------------------------------------------- helpers
    def _request(self, method, path, payload=None, timeout=10.0):
        data = None
        headers = {"X-Api-Token": self.token}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # ------------------------------------------------------------- calls
    def health(self):
        return self._request("GET", "/health")

    def submit(self, kind, params, out_dir=None, dry_run=True):
        return self._request(
            "POST",
            "/jobs",
            {"kind": kind, "params": params, "out_dir": out_dir, "dry_run": dry_run},
        )

    def job(self, job_id):
        return self._request("GET", "/job?job_id=%s" % job_id)

    def jobs(self, limit=20):
        return self._request("GET", "/jobs?limit=%d" % limit)

    def result(self, job_id):
        return self._request("GET", "/result?job_id=%s" % job_id)

    def stop(self, job_id):
        return self._request("POST", "/stop", {"job_id": job_id})


def find_service(timeout=1.0):
    """Return a client if a service is running, else None."""
    port, token = read_endpoint()
    if port is None:
        return None

    client = ServiceClient(port, token)
    try:
        client._request("GET", "/health", timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return client
