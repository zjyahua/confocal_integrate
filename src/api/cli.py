"""Command line entry point for the experiment API.

    python -m src.api.cli scan  --mode intensity --dwell-ms 0.05 ...
    python -m src.api.cli point --mode freq --start 2800 --end 2940 ...
    python -m src.api.cli status | result --job ID | stop --job ID
    python -m src.api.cli serve  [--port 8765]
    python -m src.api.cli demo   [--out DIR]

When the Qt application is running it hosts the control service; the CLI
then forwards the command to it, so the GUI shows the same scan and the
parameters appear in its widgets.  When no service is running the CLI
executes the job itself (headless).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from src.api import execute, render
from src.api.client import find_service
from src.api.jobs import JobRunner
from src.api.paths import default_out_dir
from src.api.server import REPO_ROOT, start_service, stop_service


# --------------------------------------------------------------------- utils
def _default_out_dir():
    return default_out_dir()


def _print_json(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _summarise(job):
    print("job       : %s" % job.get("job_id"))
    print("kind      : %s" % job.get("kind"))
    print("state     : %s" % job.get("state"))
    if job.get("error"):
        print("error     : %s" % job["error"])
    plan = (job.get("progress") or {}).get("plan") or job.get("summary") or {}
    if isinstance(plan, dict):
        if plan.get("estimate_s") is not None:
            print("estimate  : %.1f s" % float(plan["estimate_s"]))
        if plan.get("channels"):
            print("segments  : %s" % plan["channels"])
        for warning in plan.get("warnings", []):
            print("warning   : %s" % warning)
        for error in plan.get("errors", []):
            print("error     : %s" % error)
    progress = job.get("progress") or {}
    if progress.get("phase") == "running":
        if progress.get("point_num"):
            print(
                "progress  : loop %s/%s point %s/%s"
                % (progress.get("loop"), progress.get("loop_num"),
                   progress.get("point"), progress.get("point_num"))
            )
        elif progress.get("line_num"):
            print(
                "progress  : line %s/%s"
                % (progress.get("line"), progress.get("line_num"))
            )
        print(
            "timing    : %.1f s elapsed, eta %s"
            % (progress.get("elapsed_s", 0.0),
               "-" if progress.get("eta_s") is None
               else "%.1f s" % progress["eta_s"])
        )
    if job.get("out_dir"):
        print("out_dir   : %s" % job["out_dir"])


def _wait_service(client, job_id, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.job(job_id)
        if job["state"] in ("done", "failed", "stopped", "dry-run"):
            return job
        time.sleep(0.3)
    return client.job(job_id)


def _wait_local(runner, job_id, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = runner.get(job_id)
        if job.state in ("done", "failed", "stopped", "dry-run"):
            return job.to_dict()
        time.sleep(0.1)
    return runner.get(job_id).to_dict()


def _run(kind, params, args):
    """Send the job to the service when it exists, otherwise run locally."""
    client = find_service()
    dry_run = bool(args.dry_run)
    out_dir = args.out or _default_out_dir()

    if client is not None:
        health = client.health()
        where = "GUI is running" if health.get("gui") else "control service is running"
        print("[service] %s, forwarding the job to it" % where)
        job = client.submit(kind, params, out_dir=out_dir, dry_run=dry_run)
        job = _wait_service(client, job["job_id"], args.timeout)
    else:
        print("[local] no service running, executing head-less")
        runner = JobRunner(executor=execute.execute)
        job = runner.submit(kind, params, out_dir=out_dir, dry_run=dry_run).to_dict()
        job = _wait_local(runner, job["job_id"], args.timeout)

    if args.json:
        _print_json(job)
    else:
        _summarise(job)

    return 0 if job["state"] in ("done", "dry-run") else 1


# ------------------------------------------------------------------ commands
def cmd_scan(args):
    params = {
        "mode": args.mode,
        "dwell_ms": args.dwell_ms,
        "resolution": args.resolution,
        "x_start": args.x_start,
        "x_end": args.x_end,
        "y_start": args.y_start,
        "y_end": args.y_end,
        "first_line": not args.normal_line,
        "z": args.z,
        "live_interval_s": args.live_interval,
    }
    if args.sequence:
        params["sequence"] = args.sequence
    return _run("confocal_scan", params, args)


def cmd_point(args):
    params = {
        "mode": args.mode,
        "count_mode": args.count_mode,
        "start": args.start,
        "end": args.end,
        "loops": args.loops,
        "average_num": args.average,
        "live_interval_s": args.live_interval,
    }
    if args.mode == "freq":
        params["step"] = args.step
    else:
        params["points"] = args.points
        params["time_scale"] = args.time_scale

    if args.count_mode == "Histogram":
        params["bin_width"] = args.bin_width
        params["bin_num"] = args.bin_num

    if args.frequency is not None:
        params["frequency"] = args.frequency

    if args.auto_track:
        params["auto_track"] = True
        params["track_threshold"] = args.track_threshold
        params["track_mode"] = args.track_mode
        params["track_integral_ms"] = args.track_integral_ms

        if args.track_step is not None:
            params["track_step"] = args.track_step

        if args.track_continue_on_failure:
            params["track_stop_on_failure"] = False

    if args.sequence:
        params["sequence"] = args.sequence

    return _run("point_scan", params, args)


def cmd_track(args):
    params = {
        "mode": args.mode,
        "integral_ms": args.integral_ms,
        "laser_on": args.laser_on,
    }

    if args.step is not None:
        params["step"] = args.step

    return _run("track", params, args)


def cmd_status(args):
    client = find_service()
    if client is not None:
        if args.job:
            job = client.job(args.job)
            _print_json(job) if args.json else _summarise(job)
        else:
            jobs = client.jobs(args.limit)
            for job in jobs["jobs"]:
                print("%-28s %-8s %-14s %s" % (
                    job["job_id"], job["state"], job["kind"], job.get("out_dir", "")))
        return 0

    print("no service is running (start it with: python -m src.api.cli serve)")
    return 1


def cmd_result(args):
    client = find_service()
    if client is None:
        print("no service is running")
        return 1
    result = client.result(args.job)
    _print_json(result) if args.json else _summarise(result)
    return 0


def cmd_stop(args):
    client = find_service()
    if client is None:
        print("no service is running")
        return 1
    client.stop(args.job)
    print("stop requested for %s" % args.job)
    return 0


def cmd_serve(args):
    runner = JobRunner(executor=execute.execute)
    server, _thread, port = start_service(runner, port=args.port)
    print("control service on http://127.0.0.1:%d" % port)
    print("token file: %s" % os.path.join(REPO_ROOT, ".api_token"))
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        stop_service(server)
    return 0


def cmd_demo(args):
    out_dir = args.out or _default_out_dir()
    files = render.demo(out_dir)
    print(json.dumps({"out_dir": out_dir, "files": files}, indent=2))
    return 0


# --------------------------------------------------------------------- parser
def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m src.api.cli",
        description="Head-less control for the confocal experiment suite.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--out", help="output directory for this job")
        p.add_argument("--dry-run", action="store_true",
                       help="plan only: validate parameters, do not touch hardware")
        p.add_argument("--json", action="store_true", help="print the job as JSON")
        p.add_argument("--timeout", type=float, default=900.0,
                       help="seconds to wait for the job (default 900)")
        p.add_argument("--live-interval", type=float, default=2.0,
                       help="seconds between live.png snapshots (0 disables)")

    scan = sub.add_parser("scan", help="galvo confocal scan")
    scan.add_argument("--mode", choices=("intensity", "time"), default="intensity")
    scan.add_argument("--dwell-ms", type=float, default=0.05)
    scan.add_argument("--resolution", type=int, default=100)
    scan.add_argument("--x-start", type=float, default=-1.0)
    scan.add_argument("--x-end", type=float, default=1.0)
    scan.add_argument("--y-start", type=float, default=-1.0)
    scan.add_argument("--y-end", type=float, default=1.0)
    scan.add_argument("--normal-line", action="store_true",
                      help="use the shorter delay (not the first line)")
    scan.add_argument("--z", type=float, default=None,
                      help="fixed Z position; omit to keep the current one")
    scan.add_argument("--sequence", help="pulse sequence, e.g. rabi/Rabi_130ns.txt")
    common(scan)
    scan.set_defaults(func=cmd_scan)

    point = sub.add_parser("point", help="single point sweep (ODMR / Rabi / T1)")
    point.add_argument("--mode", choices=("freq", "time"), default="freq")
    point.add_argument("--count-mode", choices=("Gate", "Histogram"), default="Gate")
    point.add_argument("--start", type=float, default=2800.0)
    point.add_argument("--end", type=float, default=2940.0)
    point.add_argument("--step", type=float, default=1.0)
    point.add_argument("--points", type=int, default=100)
    point.add_argument("--loops", type=int, default=10)
    point.add_argument("--average", type=int, default=10000)
    point.add_argument("--time-scale", choices=("Linear", "Exponential"),
                       default="Linear",
                       help="time sweep spacing (only for --mode time)")
    point.add_argument("--bin-width", type=int, default=100,
                       help="histogram bin width in ps (only for --count-mode Histogram)")
    point.add_argument("--bin-num", type=int, default=1000,
                       help="histogram bin number (only for --count-mode Histogram)")
    point.add_argument("--frequency", type=float, default=None,
                       help="MW frequency in MHz to set before a time scan")
    point.add_argument("--auto-track", action="store_true",
                       help="run a tracking search when ref drops below the threshold")
    point.add_argument("--track-threshold", type=int, default=None,
                       help="ref counts that trigger tracking (required with --auto-track)")
    point.add_argument("--track-mode", choices=("galvo", "stage"), default="galvo",
                       help="how the tracking search moves X/Y")
    point.add_argument("--track-step", type=float, default=None,
                       help="tracking step: V for galvo (0.0025), um for stage (0.1)")
    point.add_argument("--track-integral-ms", type=int, default=200,
                       help="count integration time of one tracking point")
    point.add_argument("--track-continue-on-failure", action="store_true",
                       help="keep scanning when a tracking run fails")
    point.add_argument("--sequence", default="rabi/Rabi_130ns.txt")
    common(point)
    point.set_defaults(func=cmd_point)

    track = sub.add_parser(
        "track", help="find the brightest spot and move the sample there"
    )
    track.add_argument("--mode", choices=("galvo", "stage"), default="galvo",
                       help="galvo: move X/Y with the mirror; stage: with the piezo")
    track.add_argument("--step", type=float, default=None,
                       help="step in V (galvo, default 0.0025) or um (stage, default 0.1)")
    track.add_argument("--integral-ms", type=int, default=200,
                       help="count integration time per point in ms")
    track.add_argument("--laser-on", action="store_true",
                       help="switch the laser on for the run (restored afterwards)")
    common(track)
    track.set_defaults(func=cmd_track)

    status = sub.add_parser("status", help="list jobs or show one job")
    status.add_argument("--job")
    status.add_argument("--limit", type=int, default=10)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    result = sub.add_parser("result", help="files and summary of a finished job")
    result.add_argument("--job", required=True)
    result.add_argument("--json", action="store_true")
    result.set_defaults(func=cmd_result)

    stop = sub.add_parser("stop", help="ask a running job to stop")
    stop.add_argument("--job", required=True)
    stop.set_defaults(func=cmd_stop)

    serve = sub.add_parser("serve", help="run the control service without a GUI")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)

    demo = sub.add_parser("demo", help="render demo figures")
    demo.add_argument("--out")
    demo.set_defaults(func=cmd_demo)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
