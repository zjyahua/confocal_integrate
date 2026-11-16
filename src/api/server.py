"""Localhost control service.

The service is the single control surface for the experiment.  It can run
inside the Qt application (so a human watches the same scan) or stand alone
(so the CLI drives the hardware with no window at all).  Either way the
client talks to it the same way.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_PATH = os.path.join(REPO_ROOT, ".api_token")
PORT_PATH = os.path.join(REPO_ROOT, ".api_port")


class ControlService:
    """Transport independent command handler (easy to unit test)."""

    def __init__(self, runner, gui=None):
        self.runner = runner
        self.gui = gui

    # ------------------------------------------------------------- routing
    def handle(self, method, path, query=None, body=None):
        query = query or {}
        body = body or {}

        if path == "/health":
            return 200, {
                "ok": True,
                "gui": self.gui is not None,
                "jobs": len(self.runner.list(1000)),
            }

        if path == "/jobs" and method == "POST":
            kind = body.get("kind")
            params = body.get("params") or {}
            if kind not in ("confocal_scan", "point_scan"):
                return 400, {"error": "kind must be confocal_scan or point_scan"}
            job = self.runner.submit(
                kind,
                params,
                out_dir=body.get("out_dir"),
                dry_run=bool(body.get("dry_run", True)),
            )
            return 200, job.to_dict()

        if path == "/jobs" and method == "GET":
            limit = int(query.get("limit", ["20"])[0])
            return 200, {"jobs": [job.to_dict() for job in self.runner.list(limit)]}

        if path in ("/job", "/result"):
            job_id = query.get("job_id", [None])[0]
            job = self.runner.get(job_id) if job_id else None
            if job is None:
                return 404, {"error": "job not found: %s" % job_id}
            payload = job.to_dict()
            if path == "/result":
                payload["files"] = [
                    os.path.join(job.out_dir, name)
                    for name in sorted(os.listdir(job.out_dir))
                ] if os.path.isdir(job.out_dir) else []
            return 200, payload

        if path == "/stop" and method == "POST":
            job_id = body.get("job_id")
            if not self.runner.stop(job_id):
                return 404, {"error": "job not found: %s" % job_id}
            return 200, {"ok": True, "job_id": job_id}

        return 404, {"error": "unknown endpoint: %s %s" % (method, path)}


class _Handler(BaseHTTPRequestHandler):
    server_version = "ConfocalApi/0.1"

    def log_message(self, fmt, *args):  # keep the console quiet
        return

    # ------------------------------------------------------------- helpers
    def _authorized(self):
        expected = self.server.control_token
        return expected is None or self.headers.get("X-Api-Token") == expected

    def _reply(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _dispatch(self, method):
        if not self._authorized():
            return self._reply(401, {"error": "bad or missing X-Api-Token"})

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        body = {}
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except ValueError:
                return self._reply(400, {"error": "body is not valid JSON"})

        try:
            status, payload = self.server.control.handle(method, parsed.path, query, body)
        except Exception as exc:  # noqa: BLE001 - surface it to the caller
            status, payload = 500, {"error": "%s: %s" % (type(exc).__name__, exc)}
        return self._reply(status, payload)

    def do_GET(self):
        return self._dispatch("GET")

    def do_POST(self):
        return self._dispatch("POST")


def start_service(runner, gui=None, host="127.0.0.1", port=0, token=None):
    """Start the control service in a background thread.

    Returns (server, thread, port).  The token is written next to the repo so
    the CLI (and only the CLI) can pick it up.
    """
    control = ControlService(runner, gui=gui)

    if token is None:
        token = secrets.token_hex(16)

    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.control = control
    server.control_token = token

    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    with open(TOKEN_PATH, "w", encoding="utf-8") as handle:
        handle.write(token)
    with open(PORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(str(actual_port))

    return server, thread, actual_port


def stop_service(server):
    try:
        server.shutdown()
        server.server_close()
    finally:
        for path in (TOKEN_PATH, PORT_PATH):
            try:
                os.remove(path)
            except OSError:
                pass


def read_endpoint():
    """Return (port, token) if a service is registered, else (None, None)."""
    try:
        with open(PORT_PATH, "r", encoding="utf-8") as handle:
            port = int(handle.read().strip())
        with open(TOKEN_PATH, "r", encoding="utf-8") as handle:
            token = handle.read().strip()
        return port, token
    except (OSError, ValueError):
        return None, None
