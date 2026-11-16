"""Hardware executors: drive the scan threads from the job framework.

Everything here runs without a Qt window.  The scan threads are plain
QThread subclasses; calling ``run()`` directly executes the scan in the
current thread, and their signals are delivered synchronously, so no event
loop is needed.
"""

from __future__ import annotations

import os
import time

import numpy as np

from src.api import render

# job_id -> running scan thread, so /stop can interrupt it
_RUNNING = {}


def request_stop(job_id):
    """Ask a running scan to stop (safe from another thread)."""
    thread = _RUNNING.get(job_id)
    if thread is None:
        return False
    thread.stop()
    return True


def execute(job):
    """Entry point used by JobRunner."""
    if job.kind == "confocal_scan":
        return run_confocal_scan(job)
    raise NotImplementedError("no executor for %r yet" % job.kind)


# ------------------------------------------------------------------ helpers
def _write_raw(path, raw):
    raw = np.asarray(raw, dtype=float)
    np.savetxt(
        path,
        raw,
        header="x\ty\tcounts",
        fmt="%.6f\t%.6f\t%.0f",
        comments="",
    )
    return path


def _summary_of(map2d, params, elapsed_s):
    data = np.asarray(map2d, dtype=float)
    peak_index = np.unravel_index(int(np.argmax(data)), data.shape)
    return {
        "shape": list(data.shape),
        "counts_mean": round(float(np.mean(data)), 2),
        "counts_max": round(float(np.max(data)), 1),
        "counts_min": round(float(np.min(data)), 1),
        "peak_row_col": [int(peak_index[0]), int(peak_index[1])],
        "elapsed_s": round(elapsed_s, 2),
        "params": params,
    }


# ------------------------------------------------------------ confocal scan
def run_confocal_scan(job):
    """Galvo intensity scan, head-less."""
    from src.hardware import DeviceManager
    from src.threads.confocal_scan_threads.ConfocalScanThread import ConfocalScanThread
    from src.threads.confocal_scan_threads.DataThread import DataThread

    params = job.params
    mode = params.get("mode", "intensity")
    if mode != "intensity":
        raise NotImplementedError(
            "only intensity scans are wired so far (mode=%r); "
            "time / FLIM scans come next" % mode
        )

    x_start = float(params.get("x_start", -1.0))
    x_end = float(params.get("x_end", 1.0))
    y_start = float(params.get("y_start", -1.0))
    y_end = float(params.get("y_end", 1.0))
    resolution = int(params.get("resolution", 100))
    dwell_ms = float(params.get("dwell_ms", 0.05))

    x_step = (x_end - x_start) / resolution
    if x_step == 0:
        x_step = 1e-6

    hardware = DeviceManager()
    hardware.init_mover()
    hardware.init_scanner()
    hardware.init_pulser()
    hardware.init_counter()

    # Never guess the focus: when z is not given, stay where the stage is.
    z_param = params.get("z")
    if z_param is None and hardware.mover is not None:
        try:
            z_param = float(hardware.mover.read_pos("3"))
        except Exception:  # noqa: BLE001 - fall back to a no-op move
            z_param = None
    if z_param is None:
        z_param = 50.0

    missing = [
        name
        for name, device in (
            ("scanner", hardware.scanner),
            ("pulser", hardware.pulser),
            ("counter", hardware.counter),
        )
        if device is None
    ]
    if missing:
        raise RuntimeError("devices not connected: %s" % ", ".join(missing))

    thread = None
    try:
        thread = ConfocalScanThread(hardware=hardware)
        thread.set_config(
            parameters=[x_start, x_end, x_step, y_start, y_end, x_step, z_param],
            resolution=resolution,
            scan_type="Galvo Mirror",
            time_scan_type="None",
            xz_scan=False,
            scan_dwell_time=dwell_ms,
        )

        x_axis = np.linspace(x_start, x_end, resolution, endpoint=False)
        y_axis = np.linspace(y_start, y_end, resolution, endpoint=False)

        data_thread = DataThread()
        data_thread.set_config(
            xarr=x_axis,
            yarr=y_axis,
            resolution=resolution,
            reset_raw=True,
        )

        errors = []
        thread.data_update.connect(data_thread.process_scan_packet)
        thread.error_occurred.connect(errors.append)

        _RUNNING[job.job_id] = thread
        started = time.time()
        thread.run()                     # blocks until the scan is finished
        elapsed = time.time() - started

        if job.stop_requested:
            raise RuntimeError("scan stopped by request")
        if errors:
            raise RuntimeError("; ".join(errors))
        if data_thread.map is None:
            raise RuntimeError("the scan finished without producing a map")

        map2d = np.asarray(data_thread.map, dtype=float)

        files = []
        files.append(
            _write_raw(os.path.join(job.out_dir, "raw.txt"), data_thread.raw_intensity)
        )
        files.append(
            render.render_map(
                map2d,
                os.path.join(job.out_dir, "image.png"),
                title="confocal scan %dx%d, dwell %.3g ms" % (resolution, resolution, dwell_ms),
                xlabel="x (V)",
                ylabel="y (V)",
                extent=[x_start, x_end, y_start, y_end],
            )
        )

        return _summary_of(map2d, params, elapsed)

    finally:
        _RUNNING.pop(job.job_id, None)
        if thread is not None:
            try:
                thread.stop()
            except Exception:  # noqa: BLE001
                pass
        for reset in (
            hardware.reset_counter,
            hardware.reset_pulser,
            hardware.reset_scanner,
            hardware.reset_mover,
        ):
            try:
                reset()
            except Exception:  # noqa: BLE001
                pass
