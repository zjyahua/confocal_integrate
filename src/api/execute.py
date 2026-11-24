"""Hardware executors: drive the scan threads from the job framework.

Everything here runs without a Qt window.  The scan threads are plain
QThread subclasses; calling ``run()`` directly executes the scan in the
current thread, and their signals are delivered synchronously, so no event
loop is needed.
"""

from __future__ import annotations

import json
import os
import threading
import time

import numpy as np

from src.api import render

# job_id -> running scan thread, so /stop can interrupt it
_RUNNING = {}

STOP_FILENAME = "STOP"


def stop_file_path(out_dir):
    """<out_dir>/STOP is the request file watched while the job runs."""
    return os.path.join(out_dir, STOP_FILENAME) if out_dir else None


def request_stop_via_file(out_dir):
    """Create the STOP file; the running job notices it and stops after a point."""
    path = stop_file_path(out_dir)

    if path is None or not os.path.isdir(out_dir):
        return False

    try:
        with open(path, "a", encoding="utf-8"):
            pass
    except OSError:
        return False

    return True


def _start_stop_watcher(job, get_thread, interval_s=0.2):
    """
    Watch <out_dir>/STOP and stop the running thread when it appears.

    Returns a callable that must be called when the job is over; it stops the
    watcher so no thread is left behind.
    """
    path = stop_file_path(job.out_dir)

    if path is None:
        return lambda: None

    # a stale file from an earlier run must not stop this one immediately
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass

    done = threading.Event()

    def watch():
        while not done.wait(interval_s):
            if not os.path.exists(path):
                continue

            thread = get_thread()

            if thread is not None:
                try:
                    thread.stop()
                except Exception:  # noqa: BLE001
                    pass

            job.stop_requested = True
            print("[stop] STOP file found, stopping after the current point")

            try:
                from src.api import logs

                logs.write(job.kind, "STOP requested via STOP file", {"job": job.job_id})
            except Exception:  # noqa: BLE001
                pass

            break

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    return done.set




def request_stop(job_id):
    """Ask a running scan to stop (safe from another thread)."""
    thread = _RUNNING.get(job_id)
    if thread is None:
        return False
    thread.stop()
    return True


def _plot_xscale(mode, params):
    """A log x axis for time scans that were sampled exponentially."""
    if mode == "time" and params.get("time_scale") == "Exponential":
        return "log"
    return "linear"


def execute(job):
    """Entry point used by JobRunner."""
    if job.kind == "confocal_scan":
        return run_confocal_scan(job)
    if job.kind == "point_scan":
        return run_point_scan(job)
    if job.kind == "track":
        return run_track(job)
    if job.kind == "goto":
        return run_goto(job)
    if job.kind == "where":
        return run_where(job)
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
    row, col = int(peak_index[0]), int(peak_index[1])

    summary = {
        "shape": list(data.shape),
        "counts_mean": round(float(np.mean(data)), 2),
        "counts_max": round(float(np.max(data)), 1),
        "counts_min": round(float(np.min(data)), 1),
        "peak_row_col": [row, col],
        "elapsed_s": round(elapsed_s, 2),
        "params": params,
    }

    # the peak pixel as scan voltages, so the spot can be revisited with goto
    try:
        resolution = int(params.get("resolution", data.shape[1]))
        x_start = float(params.get("x_start", -1.0))
        x_end = float(params.get("x_end", 1.0))
        y_start = float(params.get("y_start", -1.0))
        y_end = float(params.get("y_end", 1.0))

        summary["peak_x_v"] = round(
            x_start + col * (x_end - x_start) / resolution, 5
        )
        summary["peak_y_v"] = round(
            y_start + row * (y_end - y_start) / resolution, 5
        )
    except (TypeError, ValueError):
        pass

    return summary


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

        live_interval_s = float(params.get("live_interval_s", 2.0))
        live_state = {"start": time.time(), "last": 0.0}

        def _write_live(packet):
            """Partial map snapshot while the scan runs."""
            now = time.time()
            progress = {}

            if isinstance(packet, dict):
                line_index = int(packet.get("line_index", 0))
                line_num = int(packet.get("line_num", resolution))
                elapsed = now - live_state["start"]
                frac = min(1.0, (line_index + 1) / max(line_num, 1))
                progress = {
                    "phase": "running",
                    "line": line_index + 1,
                    "line_num": line_num,
                    "elapsed_s": round(elapsed, 1),
                    "eta_s": round(elapsed / frac * (1.0 - frac), 1) if frac > 0 else None,
                }
                plan = job.progress.get("plan") if isinstance(job.progress, dict) else None
                if plan is not None:
                    progress["plan"] = plan
                job.progress = progress

            if live_interval_s <= 0 or now - live_state["last"] < live_interval_s:
                return

            live_state["last"] = now

            if data_thread.map is None:
                return

            try:
                render.render_map(
                    data_thread.map,
                    os.path.join(job.out_dir, "live.png"),
                    title="live scan (%d/%d lines)" % (progress["line"], progress["line_num"]),
                    xlabel="x (V)",
                    ylabel="y (V)",
                    extent=[x_start, x_end, y_start, y_end],
                )
            except Exception as exc:  # noqa: BLE001 - live view is best effort
                print("[live] render failed: %s" % exc)
                return

            try:
                with open(
                    os.path.join(job.out_dir, "live.json"), "w", encoding="utf-8"
                ) as handle:
                    json.dump(progress, handle, indent=2)
            except OSError as exc:
                print("[live] write failed: %s" % exc)

            print(
                "[live] line %d/%d  elapsed %.1fs  eta %s"
                % (
                    progress["line"],
                    progress["line_num"],
                    progress["elapsed_s"],
                    "-" if progress["eta_s"] is None else "%.1fs" % progress["eta_s"],
                )
            )

        thread.data_update.connect(_write_live)

        _RUNNING[job.job_id] = thread
        stop_watcher_done = _start_stop_watcher(job, lambda: thread)
        stopped = False

        started = time.time()

        try:
            thread.run()                 # blocks until the scan is finished
        finally:
            stop_watcher_done()

        elapsed = time.time() - started
        stopped = bool(job.stop_requested)

        if stopped:
            print("[stop] confocal scan stopped after %d lines" % (data_thread.map.shape[0] if data_thread.map is not None else 0))

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

        summary = _summary_of(map2d, params, elapsed)
        summary["stopped"] = stopped

        return summary

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


# ------------------------------------------------------------ point sweep
def _write_table(path, columns, header):
    """Write columns of numbers with a header line."""
    data = np.column_stack([np.asarray(c, dtype=float) for c in columns])
    np.savetxt(
        path,
        data,
        header="\t".join(header),
        fmt="%.6g",
        comments="",
    )
    return path


def _run_max_track(hardware, step_v=None, z_step=None, integral_ms=200):
    """
    One head-less MaxThread hill climb.

    The arrangement is fixed: X/Y move the galvo mirror (volts), Z moves the
    piezo stage (micrometres).  Returns (ok, info).
    """
    from src.threads.track_threads.MaxThread import MaxThread

    tracker = MaxThread(hardware=hardware)
    tracker.step_angle = float(0.0025 if step_v is None else step_v)
    tracker.step = float(0.1 if z_step is None else z_step)
    tracker.set_parameters(integral_time=int(integral_ms), scan_mode=1)

    collected = {}
    errors = []
    tracker.tracking_data.connect(lambda *args: collected.update(data=args))
    tracker.error.connect(errors.append)

    tracker.run()

    if errors:
        print("[track] tracker error: %s" % "; ".join(errors))

    if errors or "data" not in collected:
        return False, {}

    pos_list, cts_list, pos_origin, pos_final = collected["data"]

    return True, {
        "origin": [round(float(v), 5) for v in pos_origin],
        "final": [round(float(v), 5) for v in pos_final],
        "max_counts": [int(max(c)) for c in cts_list],
    }


def _write_gate_raw(path, raw, valid, x_name):
    """One row per loop and point, exactly as the DataThread stored it."""
    data = np.asarray(raw, dtype=float)
    mask = np.asarray(valid, dtype=bool)

    rows = []

    # only loops that actually ran, and only the points that were measured
    for loop_idx in range(data.shape[0]):
        for point_idx in range(data.shape[1]):
            if not mask[loop_idx, point_idx]:
                continue

            sig_v, ref_v, x_v = data[loop_idx, point_idx, 0:3]
            rows.append(
                (
                    loop_idx + 1,
                    point_idx + 1,
                    x_v,
                    sig_v,
                    ref_v,
                    int(mask[loop_idx, point_idx]),
                )
            )

    np.savetxt(
        path,
        np.asarray(rows, dtype=float),
        header="loop\tpoint\t%s\tsig\tref\tvalid" % x_name,
        fmt="%d\t%d\t%.6g\t%.6g\t%.6g\t%d",
        comments="",
    )
    return path


def _write_histogram_raw(path, raw, valid):
    """One row per loop and bin."""
    data = np.asarray(raw, dtype=float)
    mask = np.asarray(valid, dtype=bool)

    rows = []

    for loop_idx in range(data.shape[0]):
        if not mask[loop_idx]:
            continue

        for bin_idx in range(data.shape[1]):
            counts_v = data[loop_idx, bin_idx, 0]
            time_v = data[loop_idx, bin_idx, 1]
            rows.append((loop_idx + 1, bin_idx + 1, time_v, counts_v))

    np.savetxt(
        path,
        np.asarray(rows if rows else [(0, 0, 0.0, 0.0)], dtype=float),
        header="loop\tbin\ttime_ns\tcounts",
        fmt="%d\t%d\t%.6g\t%.6g",
        comments="",
    )
    return path


def run_point_scan(job):
    """
    Single point sweep: frequency (ODMR) or time (Rabi / T1) in Gate mode, or
    a time histogram (lifetime).

    With auto_track enabled the thread asks for a tracking run whenever the
    reference counts drop below track_threshold; head-less that request is
    answered by running MaxThread on the same hardware, exactly like the GUI's
    tracking window does.
    """
    import numpy as np

    from src.api.plan import build_point_sweeps, load_pulse_seq, resolve_sequence
    from src.hardware import DeviceManager
    from src.threads.single_point_exp_threads.DataThread import DataThread
    from src.threads.single_point_exp_threads.SinglePointscanThread import (
        SinglePointscanThread,
    )

    params = job.params
    mode = params.get("mode", "freq")
    count_mode = params.get("count_mode", "Gate")

    if (mode, count_mode) not in (
        ("freq", "Gate"),
        ("time", "Gate"),
        ("time", "Histogram"),
    ):
        raise ValueError(
            "%s + %s is not supported; use freq + Gate, time + Gate or "
            "time + Histogram" % (mode, count_mode)
        )

    loops = int(params.get("loops", 10))
    average = int(params.get("average_num", 10000))
    bin_width = int(params.get("bin_width", 100))
    bin_num = int(params.get("bin_num", 1000))

    freq_sweep, time_sweep = build_point_sweeps(params)
    pulse_seq = load_pulse_seq(resolve_sequence(params.get("sequence")))

    hardware = DeviceManager()
    hardware.init_counter()
    hardware.init_pulser()

    if mode == "freq":
        hardware.init_mw_source()

    missing = []
    if hardware.counter is None:
        missing.append("counter")
    if hardware.pulser is None:
        missing.append("pulser")
    if mode == "freq" and hardware.mw_source is None:
        missing.append("mw source")
    if missing:
        raise RuntimeError("devices not connected: %s" % ", ".join(missing))

    frequency = params.get("frequency")
    if frequency is not None and hardware.mw_source is not None:
        hardware.mw_source.set_frequency(float(frequency))

    auto_track = bool(params.get("auto_track", False))
    learn_threshold = bool(params.get("track_threshold_from_first_loop"))
    track_events = []

    if auto_track:
        # MaxThread needs the mover and the scanner, even in stage mode
        hardware.init_mover()
        hardware.init_scanner()

        if hardware.mover is None or hardware.scanner is None:
            raise RuntimeError(
                "auto tracking needs the piezo mover and the galvo scanner"
            )

    thread = None
    try:
        thread = SinglePointscanThread(hardware=hardware)
        thread.set_single_point_exp_config(
            scan_type="Freq Scan" if mode == "freq" else "Time Scan",
            count_mode=count_mode,
            bin_width=bin_width,
            bin_num=bin_num,
            total_loop_num=loops,
            average_num=average,
            pulse_seq=pulse_seq,
            time_sweep_arr=time_sweep,
            freq_sweep_arr=freq_sweep,
            threshold=params.get("track_threshold"),
            auto_track_enabled=auto_track,
            auto_track_learn_first_loop=learn_threshold,
        )

        thread.stop_on_track_failure = bool(
            params.get("track_stop_on_failure", True)
        )

        data_thread = DataThread()
        data_thread.set_config(
            time_sweep_arr=time_sweep,
            freq_sweep_arr=freq_sweep,
            bin_num=bin_num,
            bin_width=bin_width,
            total_loop_num=loops,
            reset_raw=True,
        )

        errors = []
        thread.data_update.connect(data_thread.process_packet)
        thread.error_occurred.connect(errors.append)
        data_thread.error_occurred.connect(errors.append)

        live_interval_s = float(params.get("live_interval_s", 2.0))
        live_state = {"start": time.time(), "last": 0.0, "png": ""}

        def _write_live(payload):
            """Update job.progress and, every live_interval_s, a live.png."""
            if not isinstance(payload, dict):
                return

            now = time.time()
            plot_type = payload.get("plot_type")
            loop_idx = int(payload.get("loop_index", 0))
            loop_num = int(payload.get("loop_num", 1))

            if plot_type == "histogram":
                point_idx, point_num = 0, 1
            else:
                point_idx = int(payload.get("point_index", 0))
                point_num = int(payload.get("point_num", 1))

            total = max(loop_num * point_num, 1)
            done = min(total, loop_idx * point_num + point_idx + 1)
            frac = done / total
            elapsed = now - live_state["start"]
            eta_s = (elapsed / frac) * (1.0 - frac) if frac > 0 else None

            progress = {
                "phase": "running",
                "loop": loop_idx + 1,
                "loop_num": loop_num,
                "point": None if plot_type == "histogram" else point_idx + 1,
                "point_num": None if plot_type == "histogram" else point_num,
                "elapsed_s": round(elapsed, 1),
                "eta_s": None if eta_s is None else round(eta_s, 1),
            }

            plan = job.progress.get("plan") if isinstance(job.progress, dict) else None
            if plan is not None:
                progress["plan"] = plan
            job.progress = progress

            if live_interval_s <= 0 or now - live_state["last"] < live_interval_s:
                return

            live_state["last"] = now

            try:
                if plot_type == "histogram":
                    render.render_histogram(
                        payload.get("y", []),
                        os.path.join(job.out_dir, "live.png"),
                        title="live histogram",
                        x=payload.get("x"),
                    )
                else:
                    render.render_sweep(
                        payload.get("x", []),
                        payload.get("sig_y", []),
                        payload.get("ref_y", []),
                        path=os.path.join(job.out_dir, "live.png"),
                        title="live %s scan" % ("frequency" if mode == "freq" else "time"),
                        xlabel="Frequency (MHz)" if mode == "freq" else "Time (ns)",
                        ylabel="Counts",
                        xscale=_plot_xscale(mode, params),
                    )
            except Exception as exc:  # noqa: BLE001 - live view is best effort
                print("[live] render failed: %s" % exc)
                return

            live_state["png"] = os.path.join(job.out_dir, "live.png")

            try:
                with open(
                    os.path.join(job.out_dir, "live.json"), "w", encoding="utf-8"
                ) as handle:
                    json.dump(progress, handle, indent=2)
            except OSError as exc:
                print("[live] write failed: %s" % exc)

            print(
                "[live] loop %d/%d point %s%s  elapsed %.1fs  eta %s"
                % (
                    progress["loop"],
                    progress["loop_num"],
                    "-" if progress["point"] is None else progress["point"],
                    "" if progress["point_num"] is None
                    else "/%d" % progress["point_num"],
                    progress["elapsed_s"],
                    "-" if progress["eta_s"] is None else "%.1fs" % progress["eta_s"],
                )
            )

        data_thread.image_update.connect(_write_live)

        if auto_track:
            from PyQt5 import QtCore

            def _on_track_request(message):
                # Runs inside track_update.emit() on this thread, like the GUI's
                # auto_track_update slot, and releases the scan thread when the
                # tracking run is over.
                print("[auto track] %s" % message)

                ok = False
                info = {}

                try:
                    # the scan thread switched the pulser off before asking
                    hardware.pulser.all_constant([0], analog_0=1.0)

                    ok, info = _run_max_track(
                        hardware,
                        step_v=params.get("track_step"),
                        z_step=params.get("track_z_step"),
                        integral_ms=int(params.get("track_integral_ms", 200)),
                    )
                except Exception as exc:  # noqa: BLE001
                    print("[auto track] failed: %s" % exc)

                track_events.append(dict(ok=ok, **info))
                print("[auto track] %s" % ("finished" if ok else "failed"))

                from src.api import logs

                logs.write(
                    "point_scan",
                    "AUTO TRACK %s loop/point=%s"
                    % ("ok" if ok else "failed", message),
                    info or None,
                )

                thread.notify_tracking_finished(ok)

            thread.track_update.connect(
                _on_track_request, QtCore.Qt.DirectConnection
            )

        _RUNNING[job.job_id] = thread
        stop_watcher_done = _start_stop_watcher(job, lambda: thread)
        stopped = False

        started = time.time()

        try:
            thread.run()                 # blocks until the sweep is finished
        finally:
            stop_watcher_done()

        elapsed = time.time() - started
        stopped = bool(job.stop_requested)

        if stopped:
            print("[stop] point scan stopped, keeping the loops that finished")

        if errors:
            raise RuntimeError("; ".join(errors))

        files = []
        summary = {
            "mode": mode,
            "count_mode": count_mode,
            "loops": loops,
            "average_num": average,
            "sequence": params.get("sequence"),
            "elapsed_s": round(elapsed, 2),
            "auto_track": auto_track,
            "stopped": stopped,
        }

        if auto_track:
            summary["track_events"] = track_events
            summary["learned_track_threshold"] = thread.threshold

            if learn_threshold and thread.threshold is not None:
                print("[auto track] learned threshold: %d" % thread.threshold)

        if count_mode == "Histogram":
            raw = data_thread.raw_histogram

            if raw is None:
                raise RuntimeError("the histogram scan produced no data")

            counts = np.mean(raw[:, :, 0], axis=0)
            x = np.asarray(data_thread.histogram_time_axis, dtype=float)

            peak = int(np.argmax(counts))
            summary.update(
                {
                    "bins": int(counts.size),
                    "bin_width_ps": bin_width,
                    "total_counts": int(np.sum(counts)),
                    "peak_time_ns": round(float(x[peak]), 3),
                    "peak_counts": round(float(counts[peak]), 2),
                }
            )

            files.append(
                render.render_histogram(
                    counts,
                    os.path.join(job.out_dir, "histogram.png"),
                    title="time histogram",
                    x=x,
                )
            )
            files.append(
                _write_histogram_raw(
                    os.path.join(job.out_dir, "raw.txt"),
                    raw,
                    data_thread.histogram_loop_valid,
                )
            )
            files.append(
                _write_table(
                    os.path.join(job.out_dir, "average.txt"),
                    [x, counts],
                    ["time_ns", "counts"],
                )
            )
        else:
            if mode == "freq":
                raw = data_thread.raw_gate_frequency
                valid = data_thread.gate_frequency_valid
                x = data_thread.gate_frequency_x_axis
                x_label = "Frequency (MHz)"
                x_name = "frequency_mhz"
            else:
                raw = data_thread.raw_gate_time
                valid = data_thread.gate_time_valid
                x = data_thread.gate_time_x_axis
                x_label = "Time (ns)"
                x_name = "time_ns"

            if raw is None:
                raise RuntimeError("the gate scan produced no data")

            sig_ave, ref_ave = DataThread._average_gate_data(raw, valid)
            x = np.asarray(x, dtype=float)

            peak = int(np.argmax(ref_ave))
            ref_max = float(np.max(ref_ave))
            ref_min = float(np.min(ref_ave))

            summary.update(
                {
                    "points": int(x.size),
                    "peak_x": round(float(x[peak]), 4),
                    "sig_mean": round(float(np.mean(sig_ave)), 2),
                    "ref_mean": round(float(np.mean(ref_ave)), 2),
                    "ref_max": round(ref_max, 2),
                    "ref_min": round(ref_min, 2),
                }
            )
            if ref_max > 0:
                summary["contrast_pct"] = round(
                    (ref_max - ref_min) / ref_max * 100.0, 2
                )

            # optional curve fit on the same data
            fit_kind = str(params.get("fit", "none") or "none").lower()

            if fit_kind not in ("none", ""):
                from src.api import fitting

                column = str(params.get("fit_column", "ratio")).lower()

                if column == "sig":
                    y_fit_data = np.asarray(sig_ave, dtype=float)
                elif column == "ref":
                    y_fit_data = np.asarray(ref_ave, dtype=float)
                else:
                    column = "ratio"
                    y_fit_data = np.asarray(sig_ave, dtype=float) / np.maximum(
                        np.asarray(ref_ave, dtype=float), 1e-9
                    )

                options = {}

                if fit_kind == "lorentz" and params.get("fit_peaks"):
                    options["peaks"] = int(params["fit_peaks"])

                try:
                    fit_result, y_curve = fitting.fit_curve(
                        fit_kind, x, y_fit_data, **options
                    )
                    fit_result["column"] = column
                    summary["fit"] = fit_result

                    files.append(
                        render.render_fit(
                            x,
                            y_fit_data,
                            y_curve,
                            path=os.path.join(job.out_dir, "fit.png"),
                            title="%s fit (%s)" % (fit_kind, column),
                            xlabel=x_label,
                            annotation=fitting.describe(fit_result),
                            xscale=_plot_xscale(mode, params),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - a failed fit is not fatal
                    summary["fit"] = {
                        "kind": fit_kind,
                        "ok": False,
                        "error": "%s: %s" % (type(exc).__name__, exc),
                    }

            files.append(
                render.render_sweep(
                    x,
                    sig_ave,
                    ref_ave,
                    path=os.path.join(job.out_dir, "sweep.png"),
                    title="%s %s" % (mode, count_mode),
                    xlabel=x_label,
                    ylabel="Counts",
                    xscale=_plot_xscale(mode, params),
                )
            )
            files.append(
                _write_gate_raw(
                    os.path.join(job.out_dir, "raw.txt"),
                    raw,
                    valid,
                    x_name,
                )
            )
            files.append(
                _write_table(
                    os.path.join(job.out_dir, "average.txt"),
                    [x, sig_ave, ref_ave],
                    [x_name, "sig", "ref"],
                )
            )

        return summary

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
            hardware.reset_mw_source,
        ):
            try:
                reset()
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------------- tracking
def run_track(job):
    """
    Find the brightest spot and move there.

    The arrangement is fixed: X/Y move the galvo mirror (volts), Z moves the
    piezo stage (micrometres).  The sample really moves.
    """
    from src.hardware import DeviceManager
    from src.threads.track_threads.MaxThread import MaxThread

    params = job.params

    integral_ms = int(params.get("integral_ms", 200))
    step_v = float(params.get("step", 0.0025))
    z_step = float(params.get("z_step", 0.1))
    laser_on = bool(params.get("laser_on", False))

    hardware = DeviceManager()
    hardware.init_mover()
    hardware.init_scanner()
    hardware.init_counter()

    missing = []
    if hardware.mover is None:
        missing.append("mover")
    if hardware.scanner is None:
        missing.append("scanner")
    if hardware.counter is None:
        missing.append("counter")
    if missing:
        raise RuntimeError("devices not connected: %s" % ", ".join(missing))

    if laser_on:
        hardware.init_pulser()

        if hardware.pulser is None:
            raise RuntimeError("pulser not connected, cannot switch the laser on")

        hardware.pulser.all_constant([0])

    thread = None
    try:
        thread = MaxThread(hardware=hardware)
        thread.step_angle = step_v
        thread.step = z_step
        thread.set_parameters(integral_time=integral_ms, scan_mode=1)

        collected = {}
        errors = []
        thread.tracking_data.connect(lambda *args: collected.update(data=args))
        thread.error.connect(errors.append)

        _RUNNING[job.job_id] = thread
        stop_watcher_done = _start_stop_watcher(job, lambda: thread)
        stopped = False

        started = time.time()

        try:
            thread.run()                 # blocks until X, Y and Z are done
        finally:
            stop_watcher_done()

        elapsed = time.time() - started
        stopped = bool(job.stop_requested)

        if stopped and "data" not in collected:
            print("[stop] tracking stopped before it finished")
            return {"stopped": True, "step_v": step_v, "z_step_um": z_step}

        if errors:
            raise RuntimeError("; ".join(errors))
        if "data" not in collected:
            raise RuntimeError("tracking produced no data")

        pos_list, cts_list, pos_origin, pos_final = collected["data"]

        files = [
            render.render_track(
                pos_list,
                cts_list,
                pos_origin,
                pos_final,
                path=os.path.join(job.out_dir, "track.png"),
                title="max search (step %.4g V / %.4g um, %d ms)"
                % (step_v, z_step, integral_ms),
            )
        ]

        return {
            "step_v": step_v,
            "z_step_um": z_step,
            "integral_ms": integral_ms,
            "origin": [round(float(v), 5) for v in pos_origin],
            "final": [round(float(v), 5) for v in pos_final],
            "max_counts": [int(max(c)) for c in cts_list],
            "elapsed_s": round(elapsed, 2),
            "laser_switched_on": laser_on,
            "stopped": stopped,
        }

    finally:
        _RUNNING.pop(job.job_id, None)

        if thread is not None:
            try:
                thread.stop()
            except Exception:  # noqa: BLE001
                pass

        for reset in (
            hardware.reset_counter,
            hardware.reset_mover,
            hardware.reset_scanner,
        ):
            try:
                reset()
            except Exception:  # noqa: BLE001
                pass

        if laser_on:
            try:
                hardware.reset_pulser()
            except Exception:  # noqa: BLE001
                pass


# -------------------------------------------------------------- positioning
def _read_position(hardware):
    """Current position: X/Y are galvo volts, Z is piezo micrometres."""
    return {
        "x": float(hardware.scanner.read_angle_analog("1")),
        "y": float(hardware.scanner.read_angle_analog("2")),
        "z": float(hardware.mover.read_pos("3")),
    }


def _position_hardware():
    from src.hardware import DeviceManager

    hardware = DeviceManager()
    hardware.init_mover()
    hardware.init_scanner()

    missing = []

    if hardware.mover is None:
        missing.append("mover")
    if hardware.scanner is None:
        missing.append("scanner")
    if missing:
        raise RuntimeError("devices not connected: %s" % ", ".join(missing))

    return hardware


def run_where(job):
    """Read the current position; this never moves anything."""
    hardware = _position_hardware()

    try:
        position = _read_position(hardware)

        return {
            "x_v": round(position["x"], 5),
            "y_v": round(position["y"], 5),
            "z_um": round(position["z"], 5),
        }
    finally:
        for reset in (hardware.reset_scanner, hardware.reset_mover):
            try:
                reset()
            except Exception:  # noqa: BLE001
                pass


def run_goto(job):
    """Move to a point: X/Y galvo volts, Z piezo micrometres."""
    from src.api.plan import resolve_goto_target

    params = job.params
    hardware = _position_hardware()

    try:
        before = _read_position(hardware)

        target = {}
        requested = set()

        relative = any(params.get(key) is not None for key in ("dx", "dy", "dz"))

        if relative:
            for key in ("x", "y", "z"):
                delta = params.get("d" + key)

                if delta is not None:
                    target[key] = before[key] + float(delta)
                    requested.add(key)
        else:
            target = resolve_goto_target(params)
            requested = set(target)

        # X/Y on the galvo mirror
        if "x" in requested:
            hardware.scanner.mov_angle_analog("1", float(target["x"]))
        if "y" in requested:
            hardware.scanner.mov_angle_analog("2", float(target["y"]))

        # Z on the piezo stage
        if "z" in requested:
            hardware.mover.move_pos("3", float(target["z"]))

        time.sleep(0.2)
        after = _read_position(hardware)

        summary = {}

        for key, suffix in (("x", "v"), ("y", "v"), ("z", "um")):
            summary["from_%s_%s" % (key, suffix)] = round(before[key], 5)
            summary["to_%s_%s" % (key, suffix)] = round(after[key], 5)

            if key in target:
                summary["target_%s_%s" % (key, suffix)] = round(float(target[key]), 5)

        return summary

    finally:
        for reset in (hardware.reset_scanner, hardware.reset_mover):
            try:
                reset()
            except Exception:  # noqa: BLE001
                pass
