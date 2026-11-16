"""Parameter validation and dry-run planning.

Nothing here touches hardware: it loads the pulse sequence, builds exactly
the waveform the scan thread would build, and reports segment counts plus
a duration estimate.  The CLI runs this before every experiment, so an
agent cannot start a scan that the Pulse Streamer cannot hold.
"""

from __future__ import annotations

import ast
import math
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULSE_ROOT = os.path.join(REPO_ROOT, "config", "PulseSeq")

# Hard limits: anything outside these is refused, not merely warned about.
LIMITS = {
    "max_segments": 8000,        # per digital channel (Pulse Streamer memory)
    "min_dwell_ms": 0.002,
    "max_dwell_ms": 5.0,
    "max_resolution": 500,
    "max_point_num": 2000,
    "max_loops": 1000,
    "max_average": 500000,
    "max_seconds": 3600.0,
}


def load_pulse_seq(path):
    """Parse a config/PulseSeq/*.txt file into {name: [values...]}."""
    seq = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            values = ast.literal_eval(line)
            if not isinstance(values, (list, tuple)) or len(values) < 2:
                raise ValueError(
                    "%s:%d is not a [name, values...] line: %s"
                    % (path, line_number, line)
                )
            seq[str(values[0])] = [str(v) for v in values[1:]]
    return seq


def resolve_sequence(name):
    """Accept 'rabi/Rabi_130ns.txt', 'Rabi_130ns.txt' or an absolute path."""
    if not name:
        return None

    if os.path.isabs(name) and os.path.isfile(name):
        return name

    direct = os.path.join(PULSE_ROOT, name)
    if os.path.isfile(direct):
        return direct

    for root, _dirs, files in os.walk(PULSE_ROOT):
        candidate = os.path.join(root, name)
        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError("pulse sequence not found: %s" % name)


def _thread_classes():
    """Import the scan threads lazily (they pull in PyQt5)."""
    from src.threads.confocal_scan_threads.ConfocalScanThread import ConfocalScanThread
    from src.threads.single_point_exp_threads.SinglePointscanThread import (
        SinglePointscanThread,
    )

    return ConfocalScanThread, SinglePointscanThread


def _channel_segments(seq_list):
    """Segment count per channel (the last entry is the analog channel)."""
    out = {}
    for index, (channel, segments) in enumerate(seq_list):
        label = "analog %d" % channel if index == len(seq_list) - 1 else "digital %d" % channel
        out[label] = len(segments)
    return out


def _finish(plan):
    """Copy limits into the plan and decide ok/warnings."""
    plan.setdefault("warnings", [])
    plan.setdefault("errors", [])

    segments = plan.get("channels", {})
    limit = LIMITS["max_segments"]
    for label, count in segments.items():
        if count > limit:
            plan["errors"].append(
                "%s needs %d segments, above the %d limit; reduce dwell or resolution"
                % (label, count, limit)
            )

    seconds = plan.get("estimate_s", 0.0)
    if seconds > LIMITS["max_seconds"]:
        plan["errors"].append(
            "estimated %.0f s exceeds the %.0f s limit" % (seconds, LIMITS["max_seconds"])
        )

    plan["ok"] = not plan["errors"]
    return plan


def plan_confocal(params):
    """Validate and plan a galvo confocal scan."""
    ConfocalScanThread, _ = _thread_classes()

    mode = params.get("mode", "intensity")
    if mode not in ("intensity", "time"):
        return _finish({"errors": ["mode must be 'intensity' or 'time', got %r" % mode]})

    dwell_ms = float(params.get("dwell_ms", 0.05))
    resolution = int(params.get("resolution", 100))

    errors = []
    if not LIMITS["min_dwell_ms"] <= dwell_ms <= LIMITS["max_dwell_ms"]:
        errors.append(
            "dwell_ms %.4f outside [%g, %g]"
            % (dwell_ms, LIMITS["min_dwell_ms"], LIMITS["max_dwell_ms"])
        )
    if not 1 <= resolution <= LIMITS["max_resolution"]:
        errors.append("resolution outside [1, %d]" % LIMITS["max_resolution"])
    if errors:
        return _finish({"errors": errors})

    pulse_seq = None
    sequence_path = None
    if mode == "time":
        sequence_path = resolve_sequence(params.get("sequence"))
        pulse_seq = load_pulse_seq(sequence_path)

    common = dict(
        dwell_time_ms=dwell_ms,
        resolution=resolution,
        first_line=1 if params.get("first_line", True) else 0,
    )

    if mode == "intensity":
        try:
            seq_list, scan_freq_hz, line_period_ns = (
                ConfocalScanThread.generate_intensity_sequence_by_dwell_ms(**common)
            )
        except Exception as exc:  # noqa: BLE001 - reported as a plan error
            return _finish({"errors": ["cannot build the intensity sequence: %s" % exc]})
    else:
        try:
            seq_list, scan_freq_hz, line_period_ns = (
                ConfocalScanThread.generate_time_sequence_by_dwell_ms(
                    pulse_seq=pulse_seq, **common
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _finish({"errors": ["cannot build the time sequence: %s" % exc]})

    delay_ns = int(1e8) if common["first_line"] == 0 else int(1e7)
    lines = resolution
    per_line_s = (delay_ns + line_period_ns) / 1e9

    plan = {
        "kind": "confocal_scan",
        "mode": mode,
        "sequence": sequence_path,
        "dwell_ms": dwell_ms,
        "resolution": resolution,
        "lines": lines,
        "line_period_ns": int(line_period_ns),
        "scan_freq_hz": float(scan_freq_hz),
        "channels": _channel_segments(seq_list),
        "estimate_s": round(lines * (per_line_s + 0.05), 1),
    }

    if mode == "intensity" and params.get("sequence"):
        plan["warnings"].append("sequence is ignored in intensity mode")
    if mode == "time" and not params.get("sequence"):
        plan["warnings"].append("time mode without sequence falls back to the last one")

    return _finish(plan)


def plan_point(params):
    """Validate and plan a single point sweep (ODMR / Rabi / T1)."""
    _, SinglePointscanThread = _thread_classes()

    mode = params.get("mode", "freq")
    if mode not in ("freq", "time"):
        return _finish({"errors": ["mode must be 'freq' or 'time', got %r" % mode]})

    count_mode = params.get("count_mode", "Gate")
    if count_mode not in ("Gate", "Histogram"):
        return _finish({"errors": ["count_mode must be 'Gate' or 'Histogram'"]})

    loops = int(params.get("loops", 10))
    average = int(params.get("average_num", 10000))

    errors = []
    if not 1 <= loops <= LIMITS["max_loops"]:
        errors.append("loops outside [1, %d]" % LIMITS["max_loops"])
    if not 1 <= average <= LIMITS["max_average"]:
        errors.append("average_num outside [1, %d]" % LIMITS["max_average"])
    if errors:
        return _finish({"errors": errors})

    start = float(params.get("start", 2800.0))
    end = float(params.get("end", 2940.0))

    if mode == "freq":
        step = float(params.get("step", 1.0))
        if step <= 0:
            return _finish({"errors": ["step must be positive"]})
        points = int(math.ceil((end - start) / step)) + 1
    else:
        points = int(params.get("points", 100))

    if not 1 <= points <= LIMITS["max_point_num"]:
        return _finish({"errors": ["points outside [1, %d]" % LIMITS["max_point_num"]]})

    sequence_path = resolve_sequence(params.get("sequence"))
    pulse_seq = load_pulse_seq(sequence_path)

    # For a time sweep the sequence contains "+t" placeholders: evaluate the
    # longest one so the estimate is the worst case.
    working = pulse_seq
    if mode == "time":
        working = SinglePointscanThread.update_time_to_seq(pulse_seq, int(end))

    try:
        SinglePointscanThread.generate_pulse_sequence(working, count_mode)
    except Exception as exc:  # noqa: BLE001 - reported as a plan error
        hint = ""
        if count_mode == "Gate":
            hint = (
                " (Gate mode needs both Ref and Sig intervals; use "
                "count_mode=Histogram for a sequence with an empty Ref)"
            )
        return _finish(
            {"errors": ["sequence cannot be used in %s mode: %s%s" % (count_mode, exc, hint)]}
        )

    pulse_period_ns = int(float(working["Sum"][0]))
    per_point_s = average * pulse_period_ns / 1e9 + 0.1

    plan = {
        "kind": "point_scan",
        "mode": mode,
        "count_mode": count_mode,
        "sequence": sequence_path,
        "points": points,
        "loops": loops,
        "average_num": average,
        "pulse_period_ns": pulse_period_ns,
        "start": start,
        "end": end,
        "estimate_s": round(points * loops * per_point_s, 1),
    }

    if count_mode == "Gate" and "Ref" in pulse_seq:
        ref = [float(v) for v in pulse_seq["Ref"]]
        if len(ref) == 2 and ref[1] <= ref[0]:
            plan["warnings"].append(
                "Ref interval is empty; Gate mode needs a real Ref window "
                "(Histogram mode may be what you want)"
            )

    return _finish(plan)


def build_plan(kind, params):
    if kind == "confocal_scan":
        return plan_confocal(params)
    if kind == "point_scan":
        return plan_point(params)
    return _finish({"errors": ["unknown job kind: %r" % kind]})
