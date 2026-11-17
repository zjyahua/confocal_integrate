"""
Teaching demo: galvo sine scan in pulse mode, triggered by the Pulse Streamer.

Run sequence
    1. The Galvo AWG is set to a sine and switched into gated burst mode
       (burst gated, EXT trigger).
    2. The Pulse Streamer uploads one line of the sequence, then start_now().
    3. Channel 6 of the sequence fires first, which starts the sine output of the
       AWG and therefore the scan of one line; in the same sequence Channel 1
       outputs the counter gate (one per pixel) and Channel 0 drives the laser TTL.

Channel map (upload_seq_list convention: the last element is the analog channel)
    digital 0 : AOM laser TTL
    digital 1 : counter gate
    digital 6 : AWG trigger
    analog  0 : AOM transmission voltage

Scan geometry
    The mirror follows a sine: x(t) = (1 - cos(pi * t / T)) / 2. The rising half is
    the forward scan, the falling half is the flyback.
    Forward time = sum of all pixel times; the flyback is equally long, so one line
    period = 2 x forward.

Two optional waveform designs (both only change the Channel 1 gates, the scan
geometry stays the same)
    return_scan     = True  also count on the flyback: mirror the forward gates in
                            time and place them on the falling half, so one line
                            gets 2 x resolution gates (the counter has to be
                            configured for twice as many).
                    = False no counting on the flyback, the falling half stays low
                            (the original behaviour).

    full_pixel_gate = True  the gate covers the whole pixel window (long pixels at
                            the line ends get long gates, the short middle pixels
                            get short gates), leaving only the gap of the shortest
                            pixel between two gates.
                    = False every pixel gets the same gate length
                            (gate_high_ratio x the shortest pixel).

Note: this demo only shows how the sequence is designed; it does not normalise the
gate counts afterwards.
"""

import time

import numpy as np

from src.hardware import DeviceManager


def sin_pixel_durations_ns(dwell_time_ms, resolution):
    """
    Pixel times (ns) for the forward (rising) half of a sine X scan.

    Mirror position over the forward half: x(t) = (1 - cos(pi * t / T)) / 2, from 0 to 1.
    Pixel k ends at x = k / N, so it ends at time t_k = T * arccos(1 - 2k / N) / pi.

    The mirror is fastest in the middle of the line, so the middle pixel is the
    shortest. T is chosen so that the shortest pixel lasts dwell_time_ms.

    Example (resolution=100, dwell 1 ms): middle pixels 1 ms, edge pixels about 10 ms,
    forward half about 157 ms.
    """
    k = np.arange(int(resolution) + 1)
    edges = np.arccos(1 - 2 * k / resolution) / np.pi  # pixel edges as fraction of T
    forward_ns = float(dwell_time_ms) * 1e6 / np.diff(edges).min()
    return np.diff(np.round(edges * forward_ns)).astype(int).tolist()


def sin_gate_lengths_ns(durations_ns, gate_high_ratio=0.9, full_pixel_gate=False):
    """
    Counter gate length (ns) of every pixel.

    full_pixel_gate=False : every pixel gets the same gate, gate_high_ratio x the
                            shortest pixel. Equal integration time for every pixel,
                            but long pixels spend most of their window with the
                            gate closed.
    full_pixel_gate=True  : the gate stays open for the whole time the mirror is
                            inside the pixel window, so it is long at the line ends
                            and short in the middle. Between two gates only the gap
                            of the shortest pixel is left. Counts now scale with the
                            pixel time, which the caller has to normalise later.
    """
    shortest_gate_ns = max(1, int(min(durations_ns) * gate_high_ratio))

    if not full_pixel_gate:
        return [shortest_gate_ns] * len(durations_ns)

    gap_ns = min(durations_ns) - shortest_gate_ns
    return [duration - gap_ns for duration in durations_ns]


def _normalize_segments(seq):
    """Merge adjacent segments with the same level, drop zero length segments."""
    out = []
    for duration, level in seq:
        duration = int(duration)
        if duration <= 0:
            continue
        if out and out[-1][1] == level:
            out[-1] = (out[-1][0] + duration, level)
        else:
            out.append((duration, level))
    return out


def generate_sine_sequence_by_dwell_ms(
        dwell_time_ms,
        resolution,
        first_line=0,
        gate_high_ratio=0.9,
        return_scan=False,
        full_pixel_gate=False,
):
    """
    Generate the pulse sequence for one sine X scan line, by pixel dwell time.

    Same layout as generate_intensity_sequence_by_dwell_ms: the image axis is
    given in ms/pixel and the pixel times of the sine scan are derived from it.

    Note that a sine scan has no scan_duty parameter: the rising and falling
    halves are always equal (50/50).

    Parameters
    ----------
    dwell_time_ms : float
        Duration of the SHORTEST pixel (middle of the line), in ms.

    resolution : int
        Number of pixels per line.

    first_line : int
        0 for the first line, 1 for a normal line.

    gate_high_ratio : float
        Fraction of the shortest pixel used for the gate when
        full_pixel_gate is False.

    return_scan : bool
        True: also count on the falling half by mirroring the gates in time.
        The counter then needs 2 x resolution gates per line.

    full_pixel_gate : bool
        True: gate covers the whole pixel window (see sin_gate_lengths_ns).

    Returns
    -------
    seq_list : list
        Pulse sequence list.

    scan_freq_hz : float
        Sine frequency the galvo AWG must be set to.

    line_period_ns : int
        One full sine period in ns.
    """
    resolution = int(resolution)
    dwell_time_ms = float(dwell_time_ms)

    if resolution <= 0:
        raise ValueError("resolution must be positive.")

    if dwell_time_ms <= 0:
        raise ValueError("dwell_time_ms must be positive.")

    if not 0 < gate_high_ratio < 1:
        raise ValueError("gate_high_ratio must be between 0 and 1.")

    # pixel times of the forward (rising) half
    durations_ns = sin_pixel_durations_ns(dwell_time_ms, resolution)

    # forward half = sum of all pixel times, the falling half is equally long
    forward_ns = int(sum(durations_ns))
    line_period_ns = 2 * forward_ns
    fly_back_ns = line_period_ns - forward_ns

    # AWG sine frequency
    scan_freq_hz = 1e9 / line_period_ns

    # Delay before first/normal line
    delay_ns = int(1e8) if first_line == 0 else int(1e7)

    # -------------------------
    # Digital Channel 0: laser TTL control
    # -------------------------
    # Keep laser ON during delay + one full line period.
    laser_seq = [
        (delay_ns, 1),
        (line_period_ns, 1),
    ]

    # -------------------------
    # Analog Channel 0: laser transmission control by AOM voltage
    # -------------------------
    # Keep laser ON during delay + one full line period.
    aom_voltage_seq = [
        (delay_ns, 1.0),
        (line_period_ns, 1.0),
    ]

    # -------------------------
    # Channel 1: counter gate
    # -------------------------
    gates_ns = sin_gate_lengths_ns(durations_ns, gate_high_ratio, full_pixel_gate)

    sig_seq = [(delay_ns, 0)]
    for duration_ns, gate_ns in zip(durations_ns, gates_ns):
        lead_ns = (duration_ns - gate_ns) // 2
        sig_seq += [(lead_ns, 0), (gate_ns, 1), (duration_ns - gate_ns - lead_ns, 0)]

    if return_scan:
        # The mirror passes the same pixels in reverse order on the way back, so
        # mirror the gate pattern in time and put it into the falling half.
        sig_seq = _normalize_segments(sig_seq + list(reversed(sig_seq[1:])))
    else:
        sig_seq = _normalize_segments(sig_seq + [(fly_back_ns, 0)])

    # -------------------------
    # Channel 6: AWG trigger
    # -------------------------
    # high for 10% of one line period, low for the rest.
    trigger_ns = int(line_period_ns * 0.1)
    awg_seq = [
        (delay_ns, 0),
        (trigger_ns, 1),
        (line_period_ns - trigger_ns, 0),
    ]

    seq_list = [
        (0, laser_seq),
        (1, sig_seq),
        (6, awg_seq),
        (0, aom_voltage_seq),
    ]

    return seq_list, scan_freq_hz, line_period_ns


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    scan_dwell_time = 1  # ms, duration of the shortest (middle) pixel
    resolution = 100  # pixels per line

    x_start = -1
    x_end = 1

    return_scan = True       # True: also count on the falling half (2 x gates)
    full_pixel_gate = False   # True: gate covers the whole pixel window

    seq_list, scan_freq_hz, line_period_ns = generate_sine_sequence_by_dwell_ms(
        scan_dwell_time,
        resolution,
        first_line=0,
        return_scan=return_scan,
        full_pixel_gate=full_pixel_gate,
    )

    gates_per_line = sum(1 for _, level in seq_list[1][1] if level == 1)
    print("line period   : %.3f ms" % (line_period_ns / 1e6))
    print("scan frequency: %.4f Hz" % scan_freq_hz)
    print("gates per line: %d  (counter must be configured for this many)" % gates_per_line)

    hardware = DeviceManager()
    hardware.init_scanner()
    hardware.init_pulser()

    # Galvo AWG: sine wave in gated burst mode. It only outputs while Channel 6 of the
    # Pulse Streamer is high, so the scan and the pixel gates start together.
    hardware.scanner.scan_mode_sin_analog(float(x_start), float(x_end), scan_freq_hz)
    hardware.scanner.scanning_analog()

    hardware.pulser.trigger_mode()
    hardware.pulser.upload_seq_list(seq_list, 100)
    hardware.pulser.start_now()

    while hardware.pulser.is_running():
        time.sleep(0.001)
