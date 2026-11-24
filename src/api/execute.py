"""Hardware executors: drive the scan threads from the job framework.

Everything here runs without a Qt window.  The scan threads are plain
QThread subclasses; calling ``run()`` directly executes the scan in the
current thread, and their signals are delivered synchronously, so no event
loop is needed.
"""

from __future__ import annotations

import json
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
    if job.kind == "point_scan":
        return run_point_scan(job)
    if job.kind == "track":
        return run_track(job)
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


def _run_max_track(hardware, mode="galvo", step=None, integral_ms=200):
    """
    One head-less MaxThread hill climb (X, Y, Z).

    Returns (ok, info) where info holds the origin, the final position and the
    peak counts per axis.
    """
    from src.threads.track_threads.MaxThread import MaxThread

    if step is None:
        step = 0.0025 if mode == "galvo" else 0.1

    tracker = MaxThread(hardware=hardware)
    tracker.step = float(step)
    tracker.step_angle = float(step)
    tracker.set_parameters(
        integral_time=int(integral_ms),
        scan_mode=0 if mode == "stage" else 1,
    )

    collected = {}
    errors = []
    tracker.tracking_data.connect(lambda *args: collected.update(data=args))
    tracker.error.connect(errors.append)

    tracker.run()

    if errors:
        print("[auto track] tracker error: %s" % "; ".join(errors))

    if errors or "data" not in collected:
        return False, {}

    pos_list, cts_list, pos_origin, pos_final = collected["data"]

    return True, {
        "origin": [round(float(v), 5) for v in pos_origin],
        "final": [round(float(v), 5) for v in pos_final],
        "max_counts": [int(max(c)) for c in cts_list],
    }


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
                        mode=params.get("track_mode", "galvo"),
                        step=params.get("track_step"),
                        integral_ms=int(params.get("track_integral_ms", 200)),
                    )
                except Exception as exc:  # noqa: BLE001
                    print("[auto track] failed: %s" % exc)

                track_events.append(dict(ok=ok, **info))
                print("[auto track] %s" % ("finished" if ok else "failed"))

                thread.notify_tracking_finished(ok)

            thread.track_update.connect(
                _on_track_request, QtCore.Qt.DirectConnection
            )

        _RUNNING[job.job_id] = thread
        started = time.time()
        thread.run()                     # blocks until the sweep is finished
        elapsed = time.time() - started

        if job.stop_requested:
            raise RuntimeError("scan stopped by request")
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
        }

        if auto_track:
            summary["track_events"] = track_events

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
                )
            )
            files.append(
                _write_table(
                    os.path.join(job.out_dir, "raw.txt"),
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
                )
            )
            files.append(
                _write_table(
                    os.path.join(job.out_dir, "raw.txt"),
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
    Find the brightest spot along X, Y and Z and move there.

    MaxThread measures 7 points per axis around the current position and moves
    to the best one, so the sample really moves.  The laser is only touched
    when laser_on is set; otherwise it must already be on for the APD to see
    anything.
    """
    from src.hardware import DeviceManager
    from src.threads.track_threads.MaxThread import MaxThread

    params = job.params
    mode = params.get("mode", "galvo")

    if mode not in ("galvo", "stage"):
        raise ValueError("mode must be 'galvo' or 'stage'")

    integral_ms = int(params.get("integral_ms", 200))
    step = float(params.get("step", 0.0025 if mode == "galvo" else 0.1))
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

        # digital 0 high and analog 0 = 1.0 is the laser-on state
        hardware.pulser.all_constant([0])

    thread = None
    try:
        thread = MaxThread(hardware=hardware)
        thread.step = step
        thread.step_angle = step
        thread.set_parameters(
            integral_time=integral_ms,
            scan_mode=0 if mode == "stage" else 1,
        )

        collected = {}
        errors = []
        thread.tracking_data.connect(lambda *args: collected.update(data=args))
        thread.error.connect(errors.append)

        _RUNNING[job.job_id] = thread
        started = time.time()
        thread.run()                     # blocks until X, Y and Z are done
        elapsed = time.time() - started

        if job.stop_requested:
            raise RuntimeError("tracking stopped by request")
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
                title="max search (%s, step %g, %d ms)" % (mode, step, integral_ms),
            )
        ]

        summary = {
            "mode": mode,
            "step": step,
            "integral_ms": integral_ms,
            "origin": [round(float(v), 5) for v in pos_origin],
            "final": [round(float(v), 5) for v in pos_final],
            "max_counts": [int(max(c)) for c in cts_list],
            "elapsed_s": round(elapsed, 2),
            "laser_switched_on": laser_on,
        }
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
