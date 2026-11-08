"""
This Thread used for confocal single point experiment part
"""
import time
from PyQt5 import QtCore
import numpy as np
import threading

class SinglePointscanThread(QtCore.QThread):

    data_update = QtCore.pyqtSignal(object)
    track_update = QtCore.pyqtSignal(str)
    status_update = QtCore.pyqtSignal(str)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, hardware=None, parent=None):
        super().__init__(parent)  # Inherit the init method of parent class
        self._hardware = hardware
        self.running = False

        self.auto_track_enabled = False
        self.stop_on_track_failure = True

        self._track_done_event = threading.Event()
        self._track_result = False
        self.track_timeout_s = 120.0

        self.scan_type = "Time Scan"  # Time scan or frequency scan
        self.count_mode = "Gate"
        self.pulse_seq = None

        # track
        self.threshold = None

        # Time histogram scan
        self.bin_width = 50  # ps
        self.bin_num = 2000

        # Exp configuration
        self.Total_loop_num = 10
        self.current_loop_num = 0
        self.average_num = 1000

        # Time scan
        self.time_sweep_arr = []

        # Frequency scan
        self.freq_sweep_arr = []

        # data cache
        self.his_ctsArr = []
        self.gate_ctsArr = []

        # pulse sequence
        self.pulse_seq_histogram = []
        self.pulse_seq_freq = []

    def set_single_point_exp_config(
        self,
        *,
        scan_type=None,
        count_mode=None,
        bin_width=None,
        bin_num=None,
        total_loop_num=None,
        average_num=None,
        pulse_seq=None,
        time_sweep_arr = None,
        freq_sweep_arr = None,
        threshold = None,
        auto_track_enabled=None,
    ):
        if scan_type is not None:
            self.scan_type = scan_type

        if count_mode is not None:
            self.count_mode = count_mode

        if bin_width is not None:
            self.bin_width = int(bin_width)

        if bin_num is not None:
            self.bin_num = int(bin_num)

        if total_loop_num is not None:
            self.Total_loop_num = int(total_loop_num)

        if average_num is not None:
            self.average_num = int(average_num)

        if pulse_seq is not None:
            self.pulse_seq = pulse_seq

        if time_sweep_arr is not None:
            self.time_sweep_arr = time_sweep_arr

        if freq_sweep_arr is not None:
            self.freq_sweep_arr = freq_sweep_arr

        if threshold is not None:
            self.threshold = int(threshold)

        if auto_track_enabled is not None:
            self.auto_track_enabled = bool(auto_track_enabled)

    def stop(self):
        self.running = False
        self.requestInterruption()
        self.notify_tracking_finished(False)

    def run(self):
        self.running = True

        try:
            if self.count_mode == "Histogram":
                self._run_histogram_scan()

            elif self.count_mode == "Gate":
                if self.scan_type == "Time Scan":
                    self._run_time_scan()
                elif self.scan_type == "Frequency Scan":
                    self._run_frequency_scan()
                else:
                    raise ValueError(f"Unknown scan type: {self.scan_type}")

            else:
                raise ValueError(f"Unknown count mode: {self.count_mode}")

        except Exception as e:
            msg = f"Scan failed: {e}"
            print(msg)
            self.error_occurred.emit(msg)

        finally:
            self.running = False

    def _run_histogram_scan(self):
        self.status_update.emit("Starting time scan with histogram count mode")
        try:
            self._hardware.counter.configure_flim(
                self.bin_width,
                self.bin_num,
                number_of_gates=int(1)
            )
            self.pulse_seq_histogram = self.generate_pulse_sequence(self.pulse_seq, self.count_mode)

            self._hardware.counter.start_flim_measure()
            self._hardware.pulser.trigger_mode()

            self._hardware.pulser.upload_seq_list(self.pulse_seq_histogram, self.average_num)

            print("Start time scan with histogram count mode")
            time.sleep(1)

            for loop_idx in range(self.Total_loop_num):
                if not self.running:
                    print("Warning: Scanning is stopped!")
                    break

                # self.status_update.emit(f"time scan with histogram {loop_idx}/{self.Total_loop_num}")

                self._hardware.pulser.start_now()
                self._wait_pulser_finished()

                time.sleep(0.05)
                # self._hardware.counter.wait_fim_finished()
                self.his_ctsArr = self._hardware.counter.get_flim_data()

                packet = {
                    "scan_type": self.scan_type,
                    "count_mode": "Histogram",
                    "loop_index": loop_idx,
                    "loop_num": self.Total_loop_num,
                    "time_data": self.his_ctsArr[0],
                }

                self._hardware.counter.flim_recount()
                # Emit the data to the Main Thread
                self.data_update.emit(packet)

        finally:
            self._cleanup_histogram_time_scan()


    def _cleanup_histogram_time_scan(self):
        self.running = False
        time.sleep(0.1)

        try:
            self._hardware.pulser.init_ps()
        except Exception as e:
            print(f"pulser.init_ps failed: {e}")

        try:
            self._hardware.counter.flim_recount()
        except Exception as e:
            print(f"counter recount failed: {e}")

        try:
            self._hardware.counter.stop_flim_measure()
        except Exception as e:
            print(f"counter:stop measure failed: {e}")

        self.status_update.emit("time scan with histogram count mode finished")

    def _run_frequency_scan(self):
        """
        Frequency scan with gate count mode.

        For each frequency point:
            1. Set MW frequency
            2. Run pulse sequence average_num times
            3. Read gate counter data
            4. Sum Ref and Sig counts
            5. Emit packet to DataThread

        Assumption:
            Each pulse period has exactly two counter gates:
                gate 0 -> Ref
                gate 1 -> Sig

            Thus, gate data order is:
                Ref, Sig, Ref, Sig, Ref, Sig, ...
        """
        self.status_update.emit("Starting frequency scan with gate count mode")

        if self._hardware is None:
            raise RuntimeError("Hardware is not initialized.")

        freq_arr = np.asarray(self.freq_sweep_arr, dtype=float)

        if freq_arr.size <= 0:
            raise ValueError("Frequency sweep array is empty.")

        if self.average_num <= 0:
            raise ValueError("average_num must be larger than 0.")

        point_num = int(freq_arr.size)

        gates_per_point = int(self.average_num) * 2

        try:
            self._hardware.counter.configure_gate(
                number_of_gates=int(gates_per_point)
            )

            self.pulse_seq_freq = self.generate_pulse_sequence(
                self.pulse_seq,
                self.count_mode
            )

            self._hardware.counter.start_gate_measure()
            self._prepare_pulser_base_on_seq(
                self.pulse_seq_freq,
                self.average_num
            )

            print("Start frequency scan")
            time.sleep(1)

            for loop_idx in range(self.Total_loop_num):
                if not self.running or self.isInterruptionRequested():
                    print("Warning: Scanning is stopped!")
                    break

                # self.status_update.emit(
                #     f"Frequency scan loop {loop_idx + 1}/{self.Total_loop_num}"
                # )

                for point_idx in range(point_num):
                    if not self.running or self.isInterruptionRequested():
                        print("Warning: Scanning is stopped!")
                        break

                    freq = float(freq_arr[point_idx])
                    self._hardware.mw_source.set_frequency(float(freq))

                    time.sleep(0.1)

                    self._hardware.pulser.start_now()
                    self._wait_pulser_finished()

                    # If your counter has a real wait method, use it.
                    if hasattr(self._hardware.counter, "wait_gate_finished"):
                        self._hardware.counter.wait_gate_finished()
                    else:
                        time.sleep(0.05)

                    gate_data = np.asarray(self._hardware.counter.get_gate_data()).ravel()

                    if gate_data.size < gates_per_point:
                        raise RuntimeError(
                            f"Not enough gate data. "
                        )

                    cts_arr = gate_data[:gates_per_point]

                    ref = int(np.sum(cts_arr[0::2]))
                    sig = int(np.sum(cts_arr[1::2]))

                    packet = {
                        "scan_type": self.scan_type,
                        "count_mode": "Gate",

                        "loop_index": loop_idx,
                        "loop_num": self.Total_loop_num,

                        "point_index": point_idx,
                        "point_num": point_num,

                        "frequency": float(freq),
                        "sig": sig,
                        "ref": ref,

                        "raw_gate_data": cts_arr.copy(),
                    }

                    self.data_update.emit(packet)

                    keep_scanning = self._auto_track_if_needed_after_scan_point(ref)

                    if not keep_scanning:
                        break

                    if hasattr(self._hardware.counter, "gate_recount"):
                        self._hardware.counter.gate_recount()

        finally:
            self._cleanup_frequency_scan()

    def _prepare_pulser_base_on_seq(self, seq, average_num):
        """
        Prepare Pulser for scan.
        Called before scan starts and after auto tracking  finishes.

        :param seq:
            experiment Pulse
        :param average_num:
            sequence repeat number
        :return: None
        """
        self._hardware.pulser.trigger_mode()
        self._hardware.pulser.upload_seq_list(seq, average_num)

    def _auto_track_if_needed_after_scan_point(self, ref):
        """
        Run auto track if ref is below threshold

        :param ref: reference value for auto track judgement
        :return: True or False
        """
        if not self.auto_track_enabled:
            return True

        if self.threshold is None:
            return True

        if int(ref) >= int(self.threshold):
            return True

        msg =(
            f"Starting auto tracking..."
        )

        self.status_update.emit(msg)

        # Make sure pulse sequence is not actively controlling in hardware
        try:
            self._hardware.pulser.init_ps()
        except Exception as e:
            print(f"pulser.init_ps before tracking failed: {e}")

        ok = self._request_tracking_and_wait(msg)

        if not self.running or self.isInterruptionRequested():
            return False

        if not ok:
            if self.stop_on_track_failure:
                self.status_update.emit("Auto tracking failed. Stopping scan.")
                self.running = False
                return False

            self.status_update.emit("Auto tracking failed. Continue scan anyway.")

        # return pulser to trigger mode
        try:
            self._prepare_pulser_base_on_seq(self.pulse_seq_freq,self.average_num)
        except Exception as e:
            msg = f"Failed to restore pulser after tracking: {e}"
            self.error_occurred.emit(msg)
            self.running = False
            return False

        if ok:
            self.status_update.emit("Auto tracking finished. Scan resumed.")

        return True

    def _cleanup_frequency_scan(self):
        self.running = False
        time.sleep(0.05)

        try:
            self._hardware.pulser.init_ps()
        except Exception as e:
            print(f"pulser.init_ps failed: {e}")

        try:
            if hasattr(self._hardware.counter, "gate_recount"):
                self._hardware.counter.gate_recount()
        except Exception as e:
            print(f"counter.gate_recount failed: {e}")

        try:
            self._hardware.counter.stop_gate_measure()
        except Exception as e:
            print(f"counter.stop_gate_measure failed: {e}")

        self.status_update.emit("Frequency scan finished")

    def _wait_pulser_finished(self):
        while self.running and self._hardware.pulser.is_running():
            time.sleep(0.001)

    def notify_tracking_finished(self, ok=True):
        """
        Called from GUI thread when MaxThread really finished.
        """
        self._track_result = bool(ok)
        self._track_done_event.set()

    def _request_tracking_and_wait(self, message):
        """
        Emit a tracking request and block this scan thread until the track GUI
        reports that MaxThread has finished.

        This blocks only the scan thread, not the Qt GUI thread.
        """

        self._track_result = False
        self._track_done_event.clear()
        self.track_pause = True

        self.track_update.emit(message)

        start_time = time.monotonic()

        while self.running and not self.isInterruptionRequested():
            if self._track_done_event.wait(timeout=0.05):
                self.track_pause = False
                return self._track_result

            if self.track_timeout_s is not None:
                if time.monotonic() - start_time > self.track_timeout_s:
                    self.track_pause = False
                    self.error_occurred.emit("Auto tracking timeout.")
                    return False

        self.track_pause = False
        return False

    def _run_time_scan(self):
        """
        Time scan with gate count mode.

        For each time point:
            1. Based on time, update the sequence
            2. Run pulse sequence average_num times
            3. Read gate counter data
            4. Sum Ref and Sig counts
            5. Emit packet to DataThread

        Assumption:
            Each pulse period has exactly two counter gates:
                gate 0 -> Ref
                gate 1 -> Sig

            Thus, gate data order is:
                Ref, Sig, Ref, Sig, Ref, Sig, ...
        """
        self.status_update.emit("Starting time scan with gate count mode")

        if self._hardware is None:
            raise RuntimeError("Hardware is not initialized.")

        time_arr = np.asarray(self.time_sweep_arr, dtype=float)

        if time_arr.size <= 0:
            raise ValueError("Time sweep array is empty.")

        if self.average_num <= 0:
            raise ValueError("average_num must be larger than 0.")

        point_num = int(time_arr.size)

        gates_per_point = int(self.average_num) * 2
        gates_per_loop = gates_per_point * point_num

        try:
            self._hardware.counter.configure_gate(
                number_of_gates=int(gates_per_loop)
            )

            self._hardware.counter.start_gate_measure()
            self._hardware.pulser.trigger_mode()

            print("Start time scan")
            time.sleep(1)

            for loop_idx in range(self.Total_loop_num):
                if not self.running:
                    print("Warning: Scanning is stopped!")
                    break

                # self.status_update.emit(
                #     f"Frequency scan loop {loop_idx + 1}/{self.Total_loop_num}"
                # )

                for point_idx in range(point_num):
                    if not self.running:
                        print("Warning: Scanning is stopped!")
                        break

                    time_point = time_arr[point_idx]

                    self.pulse_seq_update_with_time = self.update_time_to_seq(self.pulse_seq, time_point)

                    self.pulse_seq_time = self.generate_pulse_sequence(
                        self.pulse_seq_update_with_time,
                        self.count_mode
                    )
                    self._hardware.pulser.upload_seq_list(self.pulse_seq_time, self.average_num)

                    self._hardware.pulser.start_now()
                    self._wait_pulser_finished()

                    time.sleep(0.05)
                    gate_data = np.asarray(self._hardware.counter.get_gate_data()).ravel()

                    start = gates_per_point * point_idx
                    end = start + gates_per_point

                    if gate_data.size < end:
                        raise RuntimeError(
                            f"Not enough gate data. "
                            f"Need {end}, got {gate_data.size}."
                        )

                    cts_arr = gate_data[start:end]

                    ref = int(np.sum(cts_arr[0::2]))
                    sig = int(np.sum(cts_arr[1::2]))

                    packet = {
                        "scan_type": self.scan_type,
                        "count_mode": "Gate",

                        "loop_index": loop_idx,
                        "loop_num": self.Total_loop_num,

                        "point_index": point_idx,
                        "point_num": point_num,

                        "time_point": int(time_point),
                        "sig": sig,
                        "ref": ref,

                        "raw_gate_data": cts_arr.copy(),
                    }

                    self.data_update.emit(packet)

                if hasattr(self._hardware.counter, "gate_recount"):
                    self._hardware.counter.gate_recount()

                time.sleep(0.1)

        finally:
            self._cleanup_time_scan()

    def _cleanup_time_scan(self):
        self.running = False
        time.sleep(0.05)

        try:
            self._hardware.pulser.init_ps()
        except Exception as e:
            print(f"pulser.init_ps failed: {e}")

        try:
            if hasattr(self._hardware.counter, "gate_recount"):
                self._hardware.counter.gate_recount()
        except Exception as e:
            print(f"counter.gate_recount failed: {e}")

        try:
            self._hardware.counter.stop_gate_measure()
        except Exception as e:
            print(f"counter.stop_gate_measure failed: {e}")

        self.status_update.emit("Time scan with gate count mode finished")

    @classmethod
    def update_time_to_seq(
            cls,
            pulse_seq,
            time_value
    ):
        """
        Replace variable t in pulse sequence with time_value and calculate
        simple time expressions.

        Example
        -------
        pulse_seq = {
            'Laser': ['500', '1500', '3700+t', '4200+t'],
            'MicroWave': ['3000', '3000+t'],
            'Ref': ['1300', '1600'],
            'Sig': ['4100+t', '4400+t'],
            'Sum': ['4700+t'],
            'AOM': ['1.0']
        }

        time_value = 10

        Return:
        {
            'Laser': ['500', '1500', '3710', '4210'],
            'MicroWave': ['3000', '3010'],
            'Ref': ['1300', '1600'],
            'Sig': ['4110', '4410'],
            'Sum': ['4710'],
            'AOM': ['1.0']
        }
        """

        if pulse_seq is None:
            raise ValueError("pulse_seq is None.")

        updated_pulse_seq = {}

        for key, value_list in pulse_seq.items():

            if key == "AOM":
                updated_pulse_seq[key] = value_list.copy() if isinstance(value_list, list) else value_list
                continue

            if isinstance(value_list, (list, tuple)):
                updated_pulse_seq[key] = [
                    cls.eval_int_time_expr(value, time_value)
                    for value in value_list
                ]
            else:
                updated_pulse_seq[key] = cls.eval_int_time_expr(value_list, time_value)

        return updated_pulse_seq

    @staticmethod
    def eval_int_time_expr(expr, time_value):
        """
        Evaluate an integer time expression containing optional variable t.

        Supported examples:
            500
            "500"
            "3700+t"
            "3000-t"
            "t+3000"
            "4700+t"

        Parameters
        ----------
        expr:
            int or string time expression

        time_value:
            integer value used to replace t

        Returns
        -------
        int
        """

        t_value = int(time_value)

        if isinstance(expr, int):
            return expr

        s = str(expr).strip().replace(" ", "")

        if s == "":
            raise ValueError("Empty time expression.")

        total = 0
        i = 0
        sign = 1

        while i < len(s):
            ch = s[i]

            if ch == "+":
                sign = 1
                i += 1

            elif ch == "-":
                sign = -1
                i += 1

            if i >= len(s):
                raise ValueError(f"Invalid time expression: {expr}")

            if s[i] == "t":
                value = t_value
                i += 1

            elif s[i].isdigit():
                j = i

                while j < len(s) and s[j].isdigit():
                    j += 1

                value = int(s[i:j])
                i = j

            else:
                raise ValueError(f"Invalid time expression: {expr}")

            total += sign * value
            sign = 1

            if i < len(s) and s[i] not in "+-":
                raise ValueError(f"Invalid time expression: {expr}")

        return int(total)

    @classmethod
    def generate_pulse_sequence(
            cls,
            pulse_seq,
            count_mode
    ):
        """
        Generate pulse sequence for time scan with histogram count mode.

        Pulse sequence unit:
            ns

        Parameters
        ----------
        pulse_seq:
            {'Laser': ['500', '2500', '4800', '5300'],
            'MicroWave': ['4000', '4100'],
            'Ref': ['2300', '2600'],
            'Sig': ['5200', '5500'],
            'AOM': ['1.0'],
            'Sum': ['5800']}

        count_mode:
            "Gate" or "Histogram"

        Returns
        -------
        seq_list : list
            Pulse sequence list.
        """
        if not pulse_seq:
            raise ValueError("there is no pulse seq.")

        if "Sum" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Sum'.")

        if "Laser" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Laser'.")

        if "Ref" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Ref'.")

        if "Sig" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Sig'.")

        if "MicroWave" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'MicroWave'.")
        # -------------------------
        # Digital Channel 0: laser TTL control for AOM
        # -------------------------
        # Pulse sequence period from txt, unit ns
        pulse_period_ns = int(float(pulse_seq["Sum"][0]))

        if pulse_period_ns <= 0:
            raise ValueError(
                f"pulse_seq['Sum'] must be positive, got {pulse_seq['Sum']}"
            )

        laser_seq = cls.convert_high_intervals_to_segments(
            pulse_seq["Laser"],
            pulse_period_ns
        )

        # -------------------------
        # Analog Channel 0: laser transmission control by AOM voltage
        # -------------------------
        # Keep laser ON during one full line period.
        aom_voltage_seq = [
            (pulse_period_ns, 1.0),
        ]
        # aom_voltage_seq = cls.convert_high_intervals_to_segments(
        #     pulse_seq["AOM"],
        #     pulse_period_ns
        # )

        # -------------------------
        # Channel 1: counter
        # dependent on gate or histogram
        # -------------------------
        # Sig pulse to record the time tagger

        if count_mode == "Histogram":
            sig_seq = cls.convert_high_intervals_to_segments(
                pulse_seq["Sig"],
                pulse_period_ns
            )
        elif count_mode == "Gate":
            sig_seq = cls.convert_ref_sig_to_gate_segments(
                pulse_seq["Ref"],
                pulse_seq["Sig"],
                pulse_period_ns,
            )
        else:
            raise ValueError(f"Unknown count mode: {count_mode}")

        # -------------------------
        # Channel 3: Microwave TTL control
        # to spin control
        # -------------------------
        mw_seq = cls.convert_high_intervals_to_segments(
            pulse_seq["MicroWave"],
            pulse_period_ns
        )

        # laser_seq = laser_seq * average_num
        # sig_seq = sig_seq * average_num
        # mw_seq = mw_seq * average_num
        # aom_voltage_seq = aom_voltage_seq * average_num

        seq_list = [
            (0, laser_seq),
            (1, sig_seq),
            (3, mw_seq),
            (0, aom_voltage_seq)
        ]

        return seq_list

    @classmethod
    def convert_ref_sig_to_gate_segments(
            cls,
            ref_intervals,
            sig_intervals,
            total_time,
    ):
        ref_times = cls._parse_interval_times(ref_intervals)
        sig_times = cls._parse_interval_times(sig_intervals)

        if len(ref_times) != 2:
            raise ValueError(
                f"Frequency gate mode expects exactly one Ref interval, "
                f"got {ref_intervals}"
            )

        if len(sig_times) != 2:
            raise ValueError(
                f"Frequency gate mode expects exactly one Sig interval, "
                f"got {sig_intervals}"
            )

        ref_start, ref_end = ref_times
        sig_start, sig_end = sig_times

        if not (0 <= ref_start < ref_end <= total_time):
            raise ValueError(
                f"Invalid Ref interval {ref_times}, total_time={total_time}"
            )

        if not (0 <= sig_start < sig_end <= total_time):
            raise ValueError(
                f"Invalid Sig interval {sig_times}, total_time={total_time}"
            )

        if ref_end >= sig_start:
            raise ValueError(
                "Ref gate must finish before Sig gate starts. "
                "A low gap between Ref and Sig is required."
            )

        return cls.convert_high_intervals_to_segments(
            [ref_start, ref_end, sig_start, sig_end],
            total_time,
        )

    @classmethod
    def _parse_interval_times(cls, interval_list):
        if interval_list is None:
            return []

        return [int(float(x)) for x in interval_list]

    @staticmethod
    def convert_high_intervals_to_segments(interval_list, total_time):
        """
        Convert high-level intervals to pulse segments.

        Example
        -------
        interval_list = ['0', '10']
        total_time = 100

        return:
            [(10, 1), (90, 0)]

        interval_list = ['0', '10', '50', '80']
        total_time = 100

        return:
            [(10, 1), (40, 0), (30, 1), (20, 0)]
        """
        total_time = int(float(total_time))

        if total_time <= 0:
            raise ValueError(f"total_time must be positive, got {total_time}")

        if interval_list is None:
            return [(total_time, 0)]

        times = [int(float(x)) for x in interval_list]

        if len(times) == 0:
            return [(total_time, 0)]

        if len(times) % 2 != 0:
            raise ValueError(
                f"High interval list must contain start/end pairs: {interval_list}"
            )

        if any(t < 0 for t in times):
            raise ValueError(f"Pulse time cannot be negative: {times}")

        if any(t > total_time for t in times):
            raise ValueError(
                f"Pulse time exceeds total_time={total_time}: {times}"
            )

        segments = []
        current_time = 0

        for start, end in zip(times[0::2], times[1::2]):
            if end < start:
                raise ValueError(
                    f"Pulse end time must be >= start time: start={start}, end={end}"
                )

            if start < current_time:
                raise ValueError(
                    f"Pulse intervals overlap or are not sorted: {interval_list}"
                )

            if start > current_time:
                if segments and segments[-1][1] == 0:
                    segments[-1] = (segments[-1][0] + start - current_time, 0)
                else:
                    segments.append((start - current_time, 0))

            if end > start:
                if segments and segments[-1][1] == 1:
                    segments[-1] = (segments[-1][0] + end - start, 1)
                else:
                    segments.append((end - start, 1))

            current_time = end

        if current_time < total_time:
            if segments and segments[-1][1] == 0:
                segments[-1] = (segments[-1][0] + total_time - current_time, 0)
            else:
                segments.append((total_time - current_time, 0))

        if not segments:
            segments = [(total_time, 0)]

        return segments


