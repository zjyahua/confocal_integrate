"""
This Thread is used for data processing
"""

import numpy as np
from PyQt5 import QtCore


class DataThread(QtCore.QObject):
    """
    Unified data processor for:
        1. time scan with histogram count mode
        2. time scan with gate count mode
        3. frequency scan with gate count mode

    Input:
        packet from SinglePointscanThread

    Output:
        image_update(sig)
    """

    image_update = QtCore.pyqtSignal(object)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.raw_histogram = None
        self.raw_gate_frequency = None
        self.raw_gate_time = None

        self.bin_num = 2000
        self.bin_width = 1000
        # Exp configuration
        self.Total_loop_num = 10
        self.current_loop_num = 0

        # Time scan
        self.time_sweep_arr = []

        # Frequency scan
        self.freq_sweep_arr = []

        # data cache
        self.his_ctsArr = []
        self.gate_ctsArr = []

        # Histogram helper variables
        self.histogram_time_axis = None
        self.histogram_loop_valid = None

        # frequency helper variables
        self.gate_frequency_valid = None
        self.gate_frequency_x_axis = None

        # time scan helper variables
        self.gate_time_valid = None
        self.gate_time_x_axis = None

        self.last_loop_index = -1

    def set_config(
        self,
        *,
        time_sweep_arr=None,
        freq_sweep_arr=None,
        bin_num=None,
        bin_width=None,
        total_loop_num=None,
        reset_raw=True,
    ):
        if time_sweep_arr is not None:
            self.time_sweep_arr = time_sweep_arr

        if freq_sweep_arr is not None:
            self.freq_sweep_arr = freq_sweep_arr

        if bin_num is not None:
            self.bin_num = int(bin_num)

        if bin_width is not None:
            self.bin_width = int(bin_width)

        if total_loop_num is not None:
            self.Total_loop_num = int(total_loop_num)

        if reset_raw:
            self.raw_histogram = None
            self.histogram_time_axis = None
            self.histogram_loop_valid = None

            self.raw_gate_frequency = None
            self.gate_frequency_valid = None
            self.gate_frequency_x_axis = None

            self.raw_gate_time = None
            self.gate_time_valid = None
            self.gate_time_x_axis = None

            # self.last_update_time = 0.0
            self.last_loop_index = -1
            self.current_loop_num = 0

    @QtCore.pyqtSlot(object)
    def process_packet(self, packet):
        """
        Main entrance for all scan data packets.
        """

        try:
            scan_type = packet.get("scan_type")
            count_mode = packet.get("count_mode")

            if count_mode == "Histogram":
                self.process_histogram(packet)

            elif count_mode == "Gate":
                if scan_type == "Time Scan":
                    self.process_gate_time(packet)

                elif scan_type == "Frequency Scan":
                    self.process_gate_frequency(packet)

                else:
                    raise ValueError(f"Unknown scan type: {scan_type}")

            else:
                raise ValueError(f"Unknown data mode: {count_mode}")

        except Exception as e:
            msg = f"Data processing failed: {e}"
            print(msg)
            self.error_occurred.emit(msg)

    def _init_histogram_buffer(self, loop_num, bin_num):
        """
        Initialize raw histogram buffer.

        raw_histogram shape:
            [loop_index, bin_index, data_column]

        data_column:
            0 -> Signal count
            1 -> Time/ns
            2 -> Loop number
        """

        self.raw_histogram = np.zeros(
            shape=(loop_num, bin_num, 3),
            dtype=float
        )

        self.histogram_loop_valid = np.zeros(loop_num, dtype=bool)

        # The histogram x axis comes from the binning itself, never from the
        # time-scan sweep: their lengths can coincide by accident (e.g. 100 bins
        # and 100 time-scan points), which silently relabels the axis with the
        # wrong range (0-1000 ns instead of 20-2000 ns).
        # bin_width is in ps, convert to ns.
        bin_width_ns = self.bin_width / 1000.0
        self.histogram_time_axis = np.arange(1, bin_num + 1) * bin_width_ns

    def process_histogram(self, packet):
        """
        Process histogram packet.

        Expected packet:

        packet = {
            "scan_type": self.scan_type,
            "count_mode": "Histogram",
            "loop_index": loop_idx,
            "loop_num": self.Total_loop_num,
            "time_data": self.his_ctsArr[0],
        }

        Assumption:
            loop_index is 0-based:
                0, 1, 2, ..., loop_num - 1
        """

        loop_idx = int(packet["loop_index"])
        loop_num = int(packet.get("loop_num", self.Total_loop_num))

        counts = np.asarray(packet["time_data"], dtype=int).ravel()
        bin_num = counts.size

        if bin_num != self.bin_num:
            raise ValueError(
                f"Histogram bin number mismatch: "
                f"packet has {bin_num}, config has {self.bin_num}"
            )

        if loop_idx < 0 or loop_idx >= loop_num:
            raise ValueError(
                f"Invalid loop index {loop_idx}, loop_num is {loop_num}"
            )

        if (
                self.raw_histogram is None
                or self.raw_histogram.shape != (loop_num, bin_num, 3)
        ):
            self._init_histogram_buffer(loop_num, bin_num)

        # Save current loop raw data
        self.raw_histogram[loop_idx, :, 0] = counts
        self.raw_histogram[loop_idx, :, 1] = self.histogram_time_axis
        self.raw_histogram[loop_idx, :, 2] = loop_idx

        self.histogram_loop_valid[loop_idx] = True
        self.current_loop_num = loop_idx

        # Average only valid/received loops
        valid_data = self.raw_histogram[self.histogram_loop_valid, :, 0].astype(float)

        if valid_data.size == 0:
            sig_ave = np.zeros(bin_num, dtype=float)
        else:
            sig_ave = np.average(valid_data, axis=0)

        # Emit update when loop changes
        # now = time.perf_counter()
        loop_changed = loop_idx != self.last_loop_index
        # time_to_update = now - self.last_update_time >= self.update_interval
        is_last_loop = loop_idx == loop_num - 1

        if loop_changed or is_last_loop:
            self.image_update.emit({
                "plot_type": "histogram",
                "scan_type": packet.get("scan_type"),
                "count_mode": "Histogram",

                "loop_index": loop_idx,
                "loop_num": loop_num,
                "valid_loop_num": int(np.sum(self.histogram_loop_valid)),

                "x": self.histogram_time_axis.copy(),
                "y": sig_ave.copy(),

                # optional: current loop data
                "current_counts": counts.copy(),
            })

            # self.last_update_time = now

        self.last_loop_index = loop_idx

    def _init_gate_buffer(
            self,
            *,
            loop_num,
            point_num,
            raw_attr,
            valid_attr,
            x_axis_attr,
            sweep_arr,
    ):
        """
        Initialize gate scan buffer.

        Raw data shape:
            [loop_index, point_index, column]

        column:
            0 -> Signal
            1 -> Reference
            2 -> X value, frequency or time
            3 -> Loop index
        """

        setattr(
            self,
            raw_attr,
            np.full(
                shape=(loop_num, point_num, 4),
                fill_value=np.nan,
                dtype=float,
            )
        )

        setattr(
            self,
            valid_attr,
            np.zeros(
                shape=(loop_num, point_num),
                dtype=bool,
            )
        )

        if sweep_arr is not None and len(sweep_arr) == point_num:
            x_axis = np.asarray(sweep_arr, dtype=float)
        else:
            x_axis = np.full(point_num, np.nan, dtype=float)

        setattr(self, x_axis_attr, x_axis)

    @staticmethod
    def _validate_loop_point(loop_idx, loop_num, point_idx, point_num):
        """
        Validate loop index and point index.
        """

        if loop_idx < 0 or loop_idx >= loop_num:
            raise ValueError(
                f"Invalid loop index {loop_idx}, loop_num={loop_num}"
            )

        if point_idx < 0 or point_idx >= point_num:
            raise ValueError(
                f"Invalid point index {point_idx}, point_num={point_num}"
            )

    @staticmethod
    def _average_gate_data(raw, valid):
        """
        Average signal/reference over valid loops.

        Parameters
        ----------
        raw:
            shape = [loop_num, point_num, 4]

        valid:
            shape = [loop_num, point_num]

        Returns
        -------
        sig_ave, ref_ave
        """

        point_num = raw.shape[1]

        valid_count = np.sum(valid, axis=0).astype(float)

        sig_sum = np.sum(
            np.where(valid, raw[:, :, 0], 0.0),
            axis=0
        )

        ref_sum = np.sum(
            np.where(valid, raw[:, :, 1], 0.0),
            axis=0
        )

        sig_ave = np.full(point_num, np.nan, dtype=float)
        ref_ave = np.full(point_num, np.nan, dtype=float)

        np.divide(
            sig_sum,
            valid_count,
            out=sig_ave,
            where=valid_count > 0
        )

        np.divide(
            ref_sum,
            valid_count,
            out=ref_ave,
            where=valid_count > 0
        )

        return sig_ave, ref_ave

    def _process_gate_scan(
            self,
            packet,
            *,
            scan_type,
            plot_type,
            x_key,
            raw_attr,
            valid_attr,
            x_axis_attr,
            sweep_arr,
    ):
        """
        Generic processor for:
            1. frequency scan with gate count mode
            2. time scan with gate count mode
        """

        loop_idx = int(packet["loop_index"])
        loop_num = int(packet.get("loop_num", self.Total_loop_num))

        point_idx = int(packet["point_index"])
        point_num = int(packet["point_num"])

        x_value = float(packet[x_key])
        sig = float(packet["sig"])
        ref = float(packet["ref"])

        self._validate_loop_point(
            loop_idx,
            loop_num,
            point_idx,
            point_num,
        )

        raw = getattr(self, raw_attr, None)

        if raw is None or raw.shape != (loop_num, point_num, 4):
            self._init_gate_buffer(
                loop_num=loop_num,
                point_num=point_num,
                raw_attr=raw_attr,
                valid_attr=valid_attr,
                x_axis_attr=x_axis_attr,
                sweep_arr=sweep_arr,
            )

        raw = getattr(self, raw_attr)
        valid = getattr(self, valid_attr)
        x_axis = getattr(self, x_axis_attr)

        raw[loop_idx, point_idx, 0] = sig
        raw[loop_idx, point_idx, 1] = ref
        raw[loop_idx, point_idx, 2] = x_value
        raw[loop_idx, point_idx, 3] = loop_idx

        valid[loop_idx, point_idx] = True
        x_axis[point_idx] = x_value

        self.current_loop_num = loop_idx

        sig_ave, ref_ave = self._average_gate_data(raw, valid)

        self.image_update.emit({
            "plot_type": plot_type,
            "scan_type": scan_type,
            "count_mode": "Gate",

            "loop_index": loop_idx,
            "loop_num": loop_num,

            "point_index": point_idx,
            "point_num": point_num,

            "sig": sig,
            "ref": ref,

            "x": x_axis.copy(),
            "sig_y": sig_ave.copy(),
            "ref_y": ref_ave.copy(),
        })

    def process_gate_frequency(self, packet):
        """
        Process frequency scan with gate count mode.
        """

        self._process_gate_scan(
            packet,
            scan_type="Frequency Scan",
            plot_type="frequency_scan",
            x_key="frequency",

            raw_attr="raw_gate_frequency",
            valid_attr="gate_frequency_valid",
            x_axis_attr="gate_frequency_x_axis",

            sweep_arr=self.freq_sweep_arr,
        )

    def process_gate_time(self, packet):
        """
        Process time scan with gate count mode.
        """

        self._process_gate_scan(
            packet,
            scan_type="Time Scan",
            plot_type="time_scan",
            x_key="time_point",

            raw_attr="raw_gate_time",
            valid_attr="gate_time_valid",
            x_axis_attr="gate_time_x_axis",

            sweep_arr=self.time_sweep_arr,
        )