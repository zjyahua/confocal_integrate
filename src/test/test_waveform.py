"""
Teaching demo: galvo sine scan in pulse mode, triggered by the Pulse Streamer.

运行流程
    1. 振镜 AWG 设为正弦，并进入外部门控的 burst 模式（burst gated, EXT trigger）。
    2. Pulse Streamer 上传一行的序列后 start_now()。
    3. 序列里 Channel 6 先给出触发脉冲，AWG 才开始输出正弦，振镜随之开始扫一行；
       同一个序列里 Channel 1 输出计数门控（每像素一个），Channel 0 控制激光 TTL。

通道分配（upload_seq_list 的约定：列表最后一个元素是模拟通道）
    digital 0 : AOM 激光 TTL
    digital 1 : 计数卡门控
    digital 6 : AWG 触发
    analog  0 : AOM 透射电压

扫描几何
    振镜走正弦：x(t) = (1 - cos(pi * t / T)) / 2，上升半周为前扫，下降半周为回扫。
    前扫时长 = 所有像素时长之和；回扫与前扫等长，因此行周期 = 2 x 前扫。
"""

from src.hardware import DeviceManager
import numpy as np
import time


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


def generate_time_by_duration_time(durations_ns, first_line=0, gate_high_ratio=0.9):
    """
    Generate pulse sequence for a sine X scan from the time of each pixel.

    durations_ns : list of pixel times in ns (from sin_pixel_durations_ns)
    first_line   : 0 for first line, 1 for normal line

    Forward scan = sum(durations_ns) = rising half of the sine.
    Flyback = falling half, same length, so one AWG period = 2 x forward.

    Every pixel gets the same gate length (gate_high_ratio x shortest pixel),
    centred in its own time window, so all pixels count photons for the same time.

    Parameters
    ----------
    durations_ns : list
        Pixel times in ns.

    first_line : int
        0 for first line, 1 for normal line.

    gate_high_ratio : float
        Fraction of the shortest pixel dwell time used as counter gate high.
        0.9 means 90% high, 10% low.

    Returns
    -------
    seq_list : list
        Pulse sequence list.

    scan_freq_hz : float
        Calculated AWG scan frequency in Hz.

    line_period_ns : int
        One full line period in ns.
    """
    durations_ns = [int(duration) for duration in durations_ns]

    if not durations_ns:
        raise ValueError("durations_ns must not be empty.")

    if not 0 < gate_high_ratio < 1:
        raise ValueError("gate_high_ratio must be between 0 and 1.")

    # forward half = sum of all pixel times
    forward_ns = int(sum(durations_ns))

    # full sine period: rise and fall are equal
    line_period_ns = 2 * forward_ns

    # falling half
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
    # One equal length gate per pixel, centred inside that pixel's time window.
    gate_ns = max(1, int(min(durations_ns) * gate_high_ratio))

    sig_seq = [(delay_ns, 0)]
    for duration in durations_ns:
        lead_ns = (duration - gate_ns) // 2
        sig_seq += [(lead_ns, 0), (gate_ns, 1), (duration - gate_ns - lead_ns, 0)]
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
hardware = DeviceManager()
hardware.init_scanner()
hardware.init_pulser()

scan_dwell_time = 1  # ms, duration of the shortest (middle) pixel
resolution = 100  # pixels per line

x_start = -1
x_end = 1

durations_ns = sin_pixel_durations_ns(scan_dwell_time, resolution)
seq_list, scan_freq_hz, line_period_ns = generate_time_by_duration_time(durations_ns, 0)

# Galvo AWG: sine wave in gated burst mode. It only outputs while Channel 6 of the
# Pulse Streamer is high, so the scan and the pixel gates start together.
hardware.scanner.scan_mode_sin_analog(float(x_start), float(x_end), scan_freq_hz)
hardware.scanner.scanning_analog()

hardware.pulser.trigger_mode()
hardware.pulser.upload_seq_list(seq_list, 100)
hardware.pulser.start_now()

while hardware.pulser.is_running():
    time.sleep(0.001)
