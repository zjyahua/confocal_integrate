"""
This Thread used for confocal scanning part
"""
import time

from PyQt5 import QtCore
import numpy as np

class ConfocalScanThread(QtCore.QThread):
    """
    Confocal Scanning module as a thread, based on PyQt5.QtCore.QThread
    Here is current confocal scan thread structure
    ConfocalScanThread.run()
    if time_scan_type == "None":
        if scan_type == "Galvo Mirror":
            self._run_galvo_intensity_scan()
        elif scan_type == "Piezo Stage":
            self._run_piezo_intensity_scan()
    else:
        if scan_type == "Galvo Mirror":
            self._run_galvo_time_scan()
        elif scan_type == "Piezo Stage":
            self._run_piezo_time_scan()  # 之后再实现
    """
    data_update = QtCore.pyqtSignal(object)
    time_data_ready = QtCore.pyqtSignal(object)
    status_update = QtCore.pyqtSignal(str)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, hardware=None, parent=None):
        super().__init__(parent)  # Inherit the init method of parent class
        self._hardware = hardware
        self.running = False

        # scan type
        self.scan_type = "Galvo Mirror"  # "Galvo Mirror" or "Piezo Stage"
        self.time_scan_type = "None"  # "None" or "lifetime"
        self.xz_scan = False

        # [x_start, x_end, x_step, second_start, second_end, second_step, fixed_axis_pos]
        self.parameters = [-2.5, 2.5, 0.05, -2.5, 2.5, 0.05, 50.0]

        # common
        self.resolution = 100

        # Galvo intensity scan
        self.scan_dwell_time = 1  #ms 10Hz for 100 resolution
        self.scan_freq = 10

        # Piezo intensity scan
        # self.scan_time_pixel = int(self.dwell_time)*1000  # 10ms is better for piezo stage
        self.piezo_extra_gates = 10  # 原来 piezo 100 resolution 时 configure_scan 110

        # Time scan
        self.bin_width = 50  # ps
        self.bin_num = 2000
        self.frame_num = 1
        self.pulse_seq = None

        # data cache
        self.posArr = []
        self.ctsArr = []
        self.intArr = []

        # pulse sequence
        self.pulse_seq_first = []
        self.pulse_seq_normal = []

    def set_config(
        self,
        *,
        parameters=None,
        resolution=None,
        scan_type=None,
        time_scan_type=None,
        xz_scan=None,
        scan_dwell_time=None,
        bin_width=None,
        bin_num=None,
        frame_num=None,
        pulse_seq=None
    ):
        if parameters is not None:
            self.parameters = parameters

        if resolution is not None:
            self.resolution = int(resolution)

        if scan_type is not None:
            self.scan_type = scan_type

        if time_scan_type is not None:
            self.time_scan_type = time_scan_type

        if xz_scan is not None:
            self.xz_scan = bool(xz_scan)

        if scan_dwell_time is not None:
            self.scan_dwell_time = float(scan_dwell_time)

        if bin_width is not None:
            self.bin_width = int(bin_width)

        if bin_num is not None:
            self.bin_num = int(bin_num)

        if frame_num is not None:
            self.frame_num = int(frame_num)

        if pulse_seq is not None:
            self.pulse_seq = pulse_seq

    def stop(self):
        self.running = False
        self.requestInterruption()

    def run(self):
        self.running = True

        try:
            if self.time_scan_type == "None":
                if self.scan_type == "Galvo Mirror":
                    self._run_galvo_intensity_scan()
                    # self._run_galvo_intensity_sin_scan()

                elif self.scan_type == "Piezo Stage":
                    self._run_piezo_intensity_scan()

                else:
                    raise ValueError(f"Unknown scan type: {self.scan_type}")

            else:
                if self.scan_type == "Galvo Mirror":
                    self._run_galvo_time_scan()

                elif self.scan_type == "Piezo Stage":
                    raise NotImplementedError(
                        "Piezo Stage time scan is not implemented yet."
                    )

                else:
                    raise ValueError(f"Unknown scan type: {self.scan_type}")

        except Exception as e:
            msg = f"Scan failed: {e}"
            print(msg)
            self.error_occurred.emit(msg)

        finally:
            self.running = False

    def _get_scan_axes(self):
        """
        Return scan axes.

        parameters:
            [x_start, x_end, x_step,
             second_start, second_end, second_step,
             fixed_axis_pos]

        XY scan:
            second axis = Y
            fixed axis = Z

        XZ scan:
            second axis = Z
            fixed axis = Y
        """
        x_start, x_end, x_step, second_start, second_end, second_step, fixed_axis_pos = self.parameters

        if x_step == 0:
            raise ValueError("X step cannot be zero.")

        if second_step == 0:
            raise ValueError("Second axis step cannot be zero.")

        resolution = int(self.resolution)

        if resolution <= 0:
            raise ValueError("Resolution must be positive.")

        # Use exactly the same definition as the image axis in DataThread
        # (confocal_scan.configure_data_thread_before_scan: np.linspace(..., endpoint=False)).
        # np.arange would return ceil((end - start) / step) points, which can be
        # resolution + 1 depending on floating point rounding of the coordinates.
        second_axis = np.linspace(
            second_start,
            second_end,
            resolution,
            endpoint=False,
        )

        return x_start, x_end, x_step, second_axis, fixed_axis_pos

    def _move_to_fixed_axis(self, fixed_axis_pos):
        """
        Move to fixed axis position.

        Galvo XY:
            fixed axis = Z piezo

        Galvo XZ:
            fixed axis = Y galvo

        Piezo XY:
            fixed axis = Z piezo

        Piezo XZ:
            fixed axis = Y piezo
        """
        if self.scan_type == "Galvo Mirror":
            if not self.xz_scan:
                # XY scan, fixed Z
                self._hardware.mover.move_pos("3", fixed_axis_pos)
            else:
                # XZ scan, fixed Y by galvo channel 2
                self._hardware.scanner.mov_angle_analog("2", fixed_axis_pos)

        elif self.scan_type == "Piezo Stage":
            if not self.xz_scan:
                # XY scan, fixed Z
                self._hardware.mover.move_pos("3", fixed_axis_pos)
            else:
                # XZ scan, fixed Y
                self._hardware.mover.move_pos("2", fixed_axis_pos)

        else:
            raise ValueError(f"Unknown scan type: {self.scan_type}")

    def _move_second_axis(self, value):
        """
        Move slow scan axis.

        XY scan:
            second axis = Y

        XZ scan:
            second axis = Z
        """
        if self.scan_type == "Galvo Mirror":
            if not self.xz_scan:
                # XY scan, move Y galvo
                self._hardware.scanner.mov_angle_analog("2", float(value))
            else:
                # XZ scan, move Z piezo
                self._hardware.mover.move_pos("3", float(value))

        elif self.scan_type == "Piezo Stage":
            if not self.xz_scan:
                # XY scan, move Y piezo
                self._hardware.mover.move_pos("2", float(value))
            else:
                # XZ scan, move Z piezo
                self._hardware.mover.move_pos("3", float(value))

        else:
            raise ValueError(f"Unknown scan type: {self.scan_type}")

    def _run_piezo_intensity_scan(self):
        """
        Piezo Stage intensity scan.
        """
        self.status_update.emit("Starting Piezo Stage intensity scan")
        x_start, x_end, x_step, second_axis, fixed_axis_pos = self._get_scan_axes()

        nx_pixel = int(self.resolution)

        print("Move to fixed layer")
        self._move_to_fixed_axis(fixed_axis_pos)

        try:
            number_of_gates = int(nx_pixel + self.piezo_extra_gates)
            self._hardware.counter.configure_scan(number_of_gates=number_of_gates, scan_method=0)

            # set waveform and trigger for scanning
            # x max up take int
            scan_time_pixel = int(self.scan_dwell_time)*1000  #1ms
            self._hardware.mover.signal_set(int(x_start), int(x_end), scan_time_pixel)
            self._hardware.counter.start_scan_measure()
            # scan and deal with data
            print("Start Piezo intensity scan")
            time.sleep(1)
            # Scanning process

            for i, second_pos in enumerate(second_axis):
                if not self.running:
                    print("Warning: Scanning is stopped!")
                    break

                self._move_second_axis(second_pos)

                try:
                    time.sleep(0.05)
                    self.posArr = self._hardware.mover.scanning(int(x_start), scan_time_pixel)
                    time.sleep(0.2)
                    self.ctsArr = self._hardware.counter.get_scan_data()
                except BaseException as e:
                    print(e, second_pos)
                    self.error_occurred.emit(str(e))
                    continue

                try:
                    self._hardware.counter.scan_recount()
                except Exception as e:
                    print(f"counter.scan_recount failed: {e}")

                packet = {
                    "mode": "intensity",
                    "scan_type": "Piezo Stage",
                    "xz_scan": self.xz_scan,
                    "line_index": i,
                    "line_pos": second_pos,
                    "x_pos": list(self.posArr),
                    "counts": list(self.ctsArr),
                }

                self.data_update.emit(packet)


        finally:
            self._cleanup_piezo_intensity_scan()

    def _cleanup_piezo_intensity_scan(self):
        self.running = False
        try:
            self._hardware.counter.stop_scan_measure()
        except Exception as e:
            print(f"counter.stop_scan_measure failed: {e}")

        self.status_update.emit("Piezo intensity scan finished")

    def _run_galvo_intensity_scan(self):
        """
        Galvo Mirror intensity scan.
        """
        self.status_update.emit("Starting Galvo intensity scan")

        x_start, x_end, x_step, second_axis, fixed_axis_pos = self._get_scan_axes()

        nx_pixel = int(self.resolution)
        ny_pixel = int(len(second_axis))

        print("Move to fixed layer")
        self._move_to_fixed_axis(fixed_axis_pos)

        try:
            self._hardware.counter.configure_scan(
                number_of_gates=int(nx_pixel * ny_pixel),
                scan_method=1
            )

            self.pulse_seq_first, self.scan_freq, _ = (
                self.generate_intensity_sequence_by_dwell_ms(
                    dwell_time_ms=self.scan_dwell_time,
                    resolution=self.resolution,
                    first_line=0,
                )
            )

            self.pulse_seq_normal, _, _ = (
                self.generate_intensity_sequence_by_dwell_ms(
                    dwell_time_ms=self.scan_dwell_time,
                    resolution=self.resolution,
                    first_line=1,
                )
            )

            self._hardware.scanner.scan_mode_analog(
                float(x_start),
                float(x_end),
                self.scan_freq
            )

            self._hardware.scanner.scanning_analog()
            self._hardware.counter.start_scan_measure()

            self._hardware.pulser.trigger_mode()

            self._hardware.pulser.upload_seq_list(self.pulse_seq_first, 1)

            print("Start Galvo intensity scan")
            time.sleep(1)

            for i, second_pos in enumerate(second_axis):
                if not self.running:
                    print("Warning: Scanning is stopped!")
                    break

                self._move_second_axis(second_pos)
                print(second_pos)

                try:
                    if i == 1:
                        self._hardware.pulser.upload_seq_list(
                            self.pulse_seq_normal,
                            1
                        )

                    self._hardware.pulser.start_now()
                    self._wait_pulser_finished()

                    self.ctsArr = self._hardware.counter.get_scan_data()

                except Exception as e:
                    print(e, second_pos)
                    self.error_occurred.emit(str(e))
                    continue

                packet = {
                    "mode": "intensity",
                    "scan_type": "Galvo Mirror",
                    "xz_scan": self.xz_scan,
                    "line_index": i,
                    "line_pos": second_pos,
                    "x_pos": None,
                    "counts": self.ctsArr,
                }

                self.data_update.emit(packet)

        finally:
            self._cleanup_galvo_intensity_scan()

    def _cleanup_galvo_intensity_scan(self):
        self.running = False
        time.sleep(0.1)

        try:
            self._hardware.counter.scan_recount()
        except Exception as e:
            print(f"counter.scan_recount failed: {e}")

        try:
            self._hardware.counter.stop_scan_measure()
        except Exception as e:
            print(f"counter.stop_scan_measure failed: {e}")

        try:
            self._hardware.scanner.scanning_analog_close()
        except Exception as e:
            print(f"scanner.scanning_analog_close failed: {e}")

        try:
            self._hardware.scanner.single_angle_mode_analog("1")
        except Exception as e:
            print(f"scanner.single_angle_mode_analog failed: {e}")

        self.status_update.emit("Galvo intensity scan finished")

    def _run_galvo_time_scan(self):
        """
        Galvo Mirror time-resolved / FLIM scan.
        """

        self.status_update.emit("Starting Galvo time scan")

        x_start, x_end, x_step, second_axis, fixed_axis_pos = self._get_scan_axes()

        nx_pixel = int(self.resolution)
        ny_pixel = int(len(second_axis))

        print("Move to fixed layer")
        self._move_to_fixed_axis(fixed_axis_pos)

        try:
            self._hardware.counter.configure_flim_scan(
                self.bin_width,
                self.bin_num,
                number_of_gates=int(nx_pixel * ny_pixel)
            )

            self.pulse_seq_first, self.scan_freq, _ = (
                self.generate_time_sequence_by_dwell_ms(
                    dwell_time_ms=self.scan_dwell_time,
                    resolution=self.resolution,
                    pulse_seq=self.pulse_seq,
                    first_line=0,
                )
            )

            self.pulse_seq_normal, _, _ = (
                self.generate_time_sequence_by_dwell_ms(
                    dwell_time_ms=self.scan_dwell_time,
                    resolution=self.resolution,
                    pulse_seq=self.pulse_seq,
                    first_line=1,
                )
            )

            self._hardware.scanner.scan_mode_analog(
                float(x_start),
                float(x_end),
                self.scan_freq
            )

            self._hardware.scanner.scanning_analog()
            self._hardware.counter.start_flim_scan_measure()

            self._hardware.pulser.trigger_mode()

            self._hardware.pulser.upload_seq_list(
                self.pulse_seq_first,
                1
            )

            print("Start Galvo time scan")
            time.sleep(1)

            for frame_idx in range(1, self.frame_num + 1):
                if not self.running:
                    print("Warning: Scanning is stopped before frame starts!")
                    break

                print(f"Start frame {frame_idx}/{self.frame_num}")
                self.status_update.emit(f"Galvo time scan frame {frame_idx}/{self.frame_num}")

                for i, second_pos in enumerate(second_axis):
                    if not self.running:
                        print("Warning: Scanning is stopped!")
                        break

                    self._move_second_axis(second_pos)

                    try:
                        if frame_idx == 1 and i == 1:
                            self._hardware.pulser.upload_seq_list(
                                self.pulse_seq_normal,
                                1
                            )

                        self._hardware.pulser.start_now()
                        self._wait_pulser_finished()

                        if i == ny_pixel - 1:
                            self.ctsArr, self.intArr = self._hardware.counter.get_flim_scan_ready_data()

                            packet = {
                                "mode": "time",
                                "time_scan_type": self.time_scan_type,
                                "scan_type": "Galvo Mirror",
                                "xz_scan": self.xz_scan,
                                "frame_index": frame_idx,
                                "frame_num": self.frame_num,
                                "line_index": i,
                                "line_pos": second_pos,
                                "time_data": self.ctsArr,
                                "intensity_data": self.intArr,
                            }

                            self.time_data_ready.emit(packet)

                        else:
                            self.intArr = self._hardware.counter.get_flim_scan_current_data()

                            packet = {
                                "mode": "intensity",
                                "scan_type": "Galvo Mirror",
                                "time_scan_type": self.time_scan_type,
                                "xz_scan": self.xz_scan,
                                "line_index": i,
                                "line_pos": second_pos,
                                "x_pos": None,
                                "counts": self.intArr,
                            }

                            self.data_update.emit(packet)

                    except Exception as e:
                        print(e, second_pos)
                        self.error_occurred.emit(str(e))
                        continue

                if not self.running:
                    break

                print(f"Finished frame {frame_idx}/{self.frame_num}")

        finally:
            self._cleanup_galvo_time_scan()

    def _cleanup_galvo_time_scan(self):
        self.running = False
        time.sleep(0.1)

        try:
            self._hardware.pulser.init_ps()
        except Exception as e:
            print(f"pulser.init_ps failed: {e}")

        try:
            self._hardware.counter.flim_scan_recount()
        except Exception as e:
            print(f"counter.flim_scan_recount failed: {e}")

        try:
            self._hardware.counter.stop_flim_scan_measure()
        except Exception as e:
            print(f"counter.stop_flim_scan_measure failed: {e}")

        try:
            self._hardware.scanner.scanning_analog_close()
        except Exception as e:
            print(f"scanner.scanning_analog_close failed: {e}")

        try:
            self._hardware.scanner.single_angle_mode_analog("1")
        except Exception as e:
            print(f"scanner.single_angle_mode_analog failed: {e}")

        self.status_update.emit("Galvo time scan finished")

    def _wait_pulser_finished(self):
        while self.running and self._hardware.pulser.is_running():
            time.sleep(0.001)

    @staticmethod
    def generate_intensity_sequence_by_dwell_ms(
            dwell_time_ms,
            resolution,
            first_line=0,
            scan_duty=0.8,
            gate_high_ratio=0.9,
    ):
        """
        Generate pulse sequence for galvo intensity scan based on pixel dwell time.

        UI dwell time unit:
            ms / pixel

        Pulse sequence unit:
            ns

        AWG ramp:
            80% forward scan
            20% flyback

        Parameters
        ----------
        dwell_time_ms : float
            Pixel dwell time in ms.

        resolution : int
            Number of pixels per line.

        first_line : int
            0 for first line, 1 for normal line.

        scan_duty : float
            Fraction of one AWG period used for forward scan.
            For 80% forward scan, use 0.8.

        gate_high_ratio : float
            Fraction of each pixel dwell time used as counter gate high.
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

        resolution = int(resolution)
        dwell_time_ms = float(dwell_time_ms)

        if resolution <= 0:
            raise ValueError("resolution must be positive.")

        if dwell_time_ms <= 0:
            raise ValueError("dwell_time_ms must be positive.")

        if not 0 < scan_duty < 1:
            raise ValueError("scan_duty must be between 0 and 1.")

        if not 0 < gate_high_ratio < 1:
            raise ValueError("gate_high_ratio must be between 0 and 1.")

        # ms -> ns
        dwell_time_ns = int(round(dwell_time_ms * 1e6))

        # 80% line period is used for forward scan
        forward_scan_time_ns = int(dwell_time_ns * resolution)

        # Full AWG ramp period
        line_period_ns = int(round(forward_scan_time_ns / scan_duty))

        # 20% fly back time
        fly_back_time_ns = line_period_ns - forward_scan_time_ns

        # AWG ramp frequency
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
        # One gate per pixel.
        gate_high_ns = int(round(dwell_time_ns * gate_high_ratio))
        gate_low_ns = dwell_time_ns - gate_high_ns

        # Make sure duration is at least 1 ns
        gate_high_ns = max(1, gate_high_ns)
        gate_low_ns = max(1, gate_low_ns)

        sig_seq = (
                [(delay_ns, 0)]
                + [(gate_high_ns, 1), (gate_low_ns, 0)] * resolution
                + [(fly_back_time_ns, 0)]
        )

        # -------------------------
        # Channel 6: AWG trigger
        # -------------------------
        # high for 10% of one line period,
        # low for 90% of one line period.
        awg_seq = [
            (delay_ns, 0),
            (int(line_period_ns * 0.1), 1),
            (int(line_period_ns * 0.9), 0),
        ]

        seq_list = [
            (0, laser_seq),
            (1, sig_seq),
            (6, awg_seq),
            (0, aom_voltage_seq)
        ]

        return seq_list, scan_freq_hz, line_period_ns

    @classmethod
    def generate_time_sequence_by_dwell_ms(
            cls,
            dwell_time_ms,
            resolution,
            pulse_seq,
            first_line=0,
            scan_duty=0.8,
            gate_high_ratio=0.9,
    ):
        """
        Generate pulse sequence for galvo time scan based on pixel dwell time and laser sequence.

        UI dwell time unit:
            ms / pixel

        Pulse sequence unit:
            ns

        AWG ramp:
            80% forward scan
            20% flyback

        Parameters
        ----------
        dwell_time_ms : float
            Pixel dwell time in ms.

        resolution : int
            Number of pixels per line.

        pulse_seq:
            laser pulse unit

        first_line : int
            0 for first line, 1 for normal line.

        scan_duty : float
            Fraction of one AWG period used for forward scan.
            For 80% forward scan, use 0.8.

        gate_high_ratio : float
            Fraction of each pixel dwell time used as counter gate high.
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

        resolution = int(resolution)
        dwell_time_ms = float(dwell_time_ms)

        if resolution <= 0:
            raise ValueError("resolution must be positive.")

        if dwell_time_ms <= 0:
            raise ValueError("dwell_time_ms must be positive.")

        if not pulse_seq:
            raise ValueError("there is no pulse seq.")

        if "Sum" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Sum'.")

        if "Laser" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Laser'.")

        if not 0 < scan_duty < 1:
            raise ValueError("scan_duty must be between 0 and 1.")

        if not 0 < gate_high_ratio < 1:
            raise ValueError("gate_high_ratio must be between 0 and 1.")

        # ms -> ns
        dwell_time_ns = int(round(dwell_time_ms * 1e6))

        if dwell_time_ns < 2:
            raise ValueError(
                f"dwell_time_ns is too small for gate high/low split: {dwell_time_ns}"
            )

        # 80% line period is used for forward scan
        forward_scan_time_ns = int(dwell_time_ns * resolution)

        # Full AWG ramp period
        line_period_ns = int(round(forward_scan_time_ns / scan_duty))

        if line_period_ns <= forward_scan_time_ns:
            raise ValueError(
                "line_period_ns must be larger than forward_scan_time_ns. "
                f"line_period_ns={line_period_ns}, "
                f"forward_scan_time_ns={forward_scan_time_ns}"
            )

        # 20% fly back time
        fly_back_time_ns = line_period_ns - forward_scan_time_ns

        # AWG ramp frequency
        scan_freq_hz = 1e9 / line_period_ns

        # Delay before first/normal line
        delay_ns = int(1e8) if first_line == 0 else int(1e7)

        # -------------------------
        # Digital Channel 0: laser TTL control for AOM
        # -------------------------
        # Pulse sequence period from txt, unit ns
        pulse_period_ns = int(float(pulse_seq["Sum"][0]))

        if pulse_period_ns <= 0:
            raise ValueError(
                f"pulse_seq['Sum'] must be positive, got {pulse_seq['Sum']}"
            )

        laser_pattern = cls.convert_high_intervals_to_segments(
            pulse_seq["Laser"],
            pulse_period_ns
        )

        laser_forward_seq = cls.repeat_segments_to_duration(
            laser_pattern,
            forward_scan_time_ns
        )

        laser_seq = cls._normalize_segments(
            [(delay_ns, 0)]
            + laser_forward_seq
            + [(fly_back_time_ns, 0)]
        )

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
        # One gate per pixel.
        gate_high_ns = int(round(dwell_time_ns * gate_high_ratio))
        gate_low_ns = dwell_time_ns - gate_high_ns

        # Make sure duration is at least 1 ns
        gate_high_ns = max(1, gate_high_ns)
        gate_low_ns = max(1, gate_low_ns)

        sig_seq = (
                [(delay_ns, 0)]
                + [(gate_high_ns, 1), (gate_low_ns, 0)] * resolution
                + [(fly_back_time_ns, 0)]
        )

        # -------------------------
        # Channel 5: same with laser sequence for Timetagger
        # to calculate the time difference with APD photon signal
        # -------------------------
        timetagger_seq = list(laser_seq)

        # -------------------------
        # Channel 6: AWG trigger
        # -------------------------
        # high for 10% of one line period,
        # low for 90% of one line period.
        awg_seq = [
            (delay_ns, 0),
            (int(line_period_ns * 0.1), 1),
            (int(line_period_ns * 0.9), 0),
        ]

        seq_list = [
            (0, laser_seq),
            (1, sig_seq),
            (5, timetagger_seq),
            (6, awg_seq),
            (0, aom_voltage_seq)
        ]

        return seq_list, scan_freq_hz, line_period_ns

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

    @staticmethod
    def _append_segment(seq, duration, level):
        """
        Append one segment and merge with previous one if level is the same.
        """
        duration = int(duration)

        if duration <= 0:
            return

        if seq and seq[-1][1] == level:
            seq[-1] = (seq[-1][0] + duration, level)
        else:
            seq.append((duration, level))

    @staticmethod
    def _normalize_segments(seq):
        """
        Remove zero-duration segments and merge adjacent segments with same level.
        """
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

    @classmethod
    def repeat_segments_to_duration(cls, segments, target_time):
        """
        Repeat a pulse segment pattern until reaching target_time exactly.

        If target_time is not an integer multiple of pattern duration,
        the last repeated pattern will be truncated.
        """
        target_time = int(target_time)
        if target_time < 0:
            raise ValueError(f"target_time must be non-negative, got {target_time}")

        if target_time == 0:
            return []

        if not segments:
            return [(target_time, 0)]

        pattern_time = sum(int(duration) for duration, _ in segments)
        if pattern_time <= 0:
            raise ValueError("Pulse segment pattern duration must be positive.")

        # Special case: all low or all high, compress directly
        if len(segments) == 1:
            duration, level = segments[0]
            return [(target_time, level)]

        full_repeat, remainder = divmod(target_time, pattern_time)

        out = []

        for _ in range(full_repeat):
            for duration, level in segments:
                cls._append_segment(out, duration, level)

        if remainder > 0:
            for duration, level in segments:
                if remainder <= 0:
                    break

                used_duration = min(duration, remainder)
                cls._append_segment(out, used_duration, level)
                remainder -= used_duration

        return out