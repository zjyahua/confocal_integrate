"""
This Thread is used for data processing
"""

import time
import numpy as np
from PyQt5 import QtCore


class DataThread(QtCore.QObject):
    """
    Unified data processor for:
        1. Galvo Mirror intensity scan
        2. Piezo Stage intensity scan
        3. Galvo Mirror time / FLIM scan

    Input:
        packet from ConfocalScanThread

    Output:
        image_update(map)
    """

    image_update = QtCore.pyqtSignal(object)
    # raw_intensity_update = QtCore.pyqtSignal(object)
    # raw_time_update = QtCore.pyqtSignal(object)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.raw_intensity = None
        self.raw_time_frames = None
        self.raw_time_frame_indices = None

        self.xArr = np.array([])
        self.yArr = np.array([])
        self.map = None

        self.resolution = 100

        self.bin_num = 2000
        self.bin_width = 1000
        self.frame_num = 1

    def set_config(
        self,
        *,
        xarr,
        yarr,
        resolution,
        bin_num=None,
        bin_width=None,
        frame_num=None,
        reset_raw=True,
    ):
        self.xArr = np.asarray(xarr, dtype=float)
        self.yArr = np.asarray(yarr, dtype=float)
        self.resolution = int(resolution)

        if bin_num is not None:
            self.bin_num = int(bin_num)

        if bin_width is not None:
            self.bin_width = int(bin_width)

        if frame_num is not None:
            self.frame_num = int(frame_num)

        ny = len(self.yArr)
        nx = len(self.xArr)

        self.map = np.zeros((ny, nx), dtype=float)

        if reset_raw:
            self.raw_intensity = None
            self.raw_time_data = None

    @QtCore.pyqtSlot(object)
    def process_scan_packet(self, packet):
        """
        Main entrance for all scan data packets.
        """

        try:
            mode = packet.get("mode")
            scan_type = packet.get("scan_type")

            if mode == "intensity":
                if scan_type == "Galvo Mirror":
                    self.process_galvo_intensity(packet)

                elif scan_type == "Piezo Stage":
                    self.process_piezo_intensity(packet)

                else:
                    raise ValueError(f"Unknown scan type: {scan_type}")

            elif mode == "time":
                if scan_type == "Galvo Mirror":
                    self.process_galvo_time(packet)

                elif scan_type == "Piezo Stage":
                    raise NotImplementedError(
                        "Piezo Stage time data processing is not implemented yet."
                    )

                else:
                    raise ValueError(f"Unknown scan type: {scan_type}")

            else:
                raise ValueError(f"Unknown data mode: {mode}")

        except Exception as e:
            msg = f"Data processing failed: {e}"
            print(msg)
            self.error_occurred.emit(msg)

    def process_galvo_intensity(self, packet):
        """
        Process Galvo Mirror intensity scan data.
        """

        line_index = self.get_line_index(packet)
        line_pos = float(packet["line_pos"])

        counts = np.asarray(packet["counts"], dtype=int).reshape(-1)

        nx = len(self.xArr)
        ny = len(self.yArr)
        expected_size = nx * ny

        # Never fall back to counts[:nx]. That branch silently copies the first
        # line into every row whenever the scan line count differs from the image
        # row count, which produces a plausible looking but wrong image.
        if counts.size != expected_size:
            raise ValueError(
                f"Galvo counts length mismatch: got {counts.size}, "
                f"expected {expected_size} ({ny} rows x {nx} columns). "
                f"Scan axis and image axis must use the same resolution."
            )

        # Counter returns the whole frame: cumulative gates for every pixel.
        self.map = counts.reshape(ny, nx)
        line_counts = self.map[line_index, :]

        self.append_raw_intensity(
            x_values=self.xArr,
            second_pos=line_pos,
            counts=line_counts
        )

        self.emit_image_update()

    def process_piezo_intensity(self, packet):
        """
        Process Piezo Stage intensity scan data.
        """

        line_index = self.get_line_index(packet)
        line_pos = float(packet["line_pos"])

        x_pos = packet.get("x_pos")
        counts = packet.get("counts")

        if x_pos is None:
            raise ValueError("Piezo packet has no x_pos data.")

        x_data = np.asarray(x_pos, dtype=float).reshape(-1)
        counts_data = np.asarray(counts, dtype=int).reshape(-1)

        aligned_x, aligned_counts = self.align_piezo_x_counts(
            x_data,
            counts_data
        )

        picked_counts = self.pick_counts_by_command_x(
            command_x=self.xArr,
            measured_x=aligned_x,
            counts=aligned_counts
        )

        self.map[line_index, :] = picked_counts

        self.append_raw_intensity(
            x_values=aligned_x,
            second_pos=line_pos,
            counts=aligned_counts
        )

        self.emit_image_update()

    def process_galvo_time(self, packet):
        """
        Process Galvo Mirror time-resolved / FLIM data.
        """
        frame_index = int(packet.get("frame_index", 0))
        frame_num = int(packet.get("frame_num", 1))

        intensity_data = np.asarray(
            packet["intensity_data"],
            dtype=float
        ).reshape(-1)

        time_data = np.asarray(packet["time_data"])

        nx = len(self.xArr)
        ny = len(self.yArr)
        expected_size = nx * ny

        if intensity_data.size != expected_size:
            raise ValueError(
                f"Intensity length mismatch: got {intensity_data.size}, "
                f"expected {expected_size} = {nx} * {ny}"
            )

        self.map = intensity_data.reshape(ny, nx)

        raw_time = self.build_time_raw_data(time_data)

        # 第 1 帧时初始化, frame index start from 1
        if frame_index == 1 or not hasattr(self, "raw_time_frames"):
            self.raw_time_frames = []
            self.raw_time_frame_indices = []

        self.raw_time_frames.append(raw_time)
        self.raw_time_frame_indices.append(frame_index)

        # self.raw_time_update.emit(self.raw_time_data)

        self.emit_image_update(force=True)

    @staticmethod
    def align_piezo_x_counts(x_data, counts_data):
        """
        Align piezo position data and counts data.

        If x_data has one more point than counts_data, use midpoint of adjacent x.
        """

        x_data = np.asarray(x_data, dtype=float).reshape(-1)
        counts_data = np.asarray(counts_data, dtype=float).reshape(-1)

        if x_data.size == counts_data.size + 1:
            aligned_x = (x_data[:-1] + x_data[1:]) / 2
            aligned_counts = counts_data

        elif x_data.size == counts_data.size:
            aligned_x = x_data
            aligned_counts = counts_data

        else:
            min_len = min(x_data.size, counts_data.size)
            aligned_x = x_data[:min_len]
            aligned_counts = counts_data[:min_len]

        return aligned_x, aligned_counts

    @staticmethod
    def pick_counts_by_command_x(command_x, measured_x, counts):
        """
        For each command x position, find nearest measured x position.
        """

        command_x = np.asarray(command_x, dtype=float).reshape(-1)
        measured_x = np.asarray(measured_x, dtype=float).reshape(-1)
        counts = np.asarray(counts, dtype=float).reshape(-1)

        picked_counts = []

        for x_cmd in command_x:
            closest_index = int(np.argmin(np.abs(measured_x - x_cmd)))
            picked_counts.append(counts[closest_index])

        return np.asarray(picked_counts, dtype=float)

    def build_time_raw_data(self, time_data):
        """
        Build raw time data table.

        Output columns:
            x, y_or_z, t_ps, counts
        """

        nx = len(self.xArr)
        ny = len(self.yArr)
        expected_pixel_num = nx * ny

        cts = np.asarray(time_data)

        if cts.ndim == 1:
            if cts.size != expected_pixel_num * self.bin_num:
                raise ValueError(
                    f"time_data size mismatch: got {cts.size}, "
                    f"expected {expected_pixel_num * self.bin_num}"
                )
            cts = cts.reshape(expected_pixel_num, self.bin_num)

        elif cts.ndim == 2:
            if cts.shape[0] != expected_pixel_num:
                raise ValueError(
                    f"time_data pixel number mismatch: got {cts.shape[0]}, "
                    f"expected {expected_pixel_num}"
                )

            if cts.shape[1] != self.bin_num:
                raise ValueError(
                    f"time_data bin number mismatch: got {cts.shape[1]}, "
                    f"expected {self.bin_num}"
                )

        else:
            raise ValueError(f"Unsupported time_data shape: {cts.shape}")

        # t_arr = np.arange(self.bin_num) * self.bin_width
        #
        # x_col = np.tile(np.repeat(self.xArr, self.bin_num), ny)
        # y_col = np.repeat(self.yArr, nx * self.bin_num)
        # t_col = np.tile(t_arr, expected_pixel_num)
        # counts_col = cts.reshape(-1)
        #
        # raw_time = np.column_stack(
        #     (x_col, y_col, t_col, counts_col)
        # )

        counts_frame = cts.reshape(ny, nx, self.bin_num)

        return counts_frame

    def append_raw_intensity(self, x_values, second_pos, counts):
        """
        Append line raw intensity data.

        Output columns:
            x, y_or_z, counts
        """

        x_values = np.asarray(x_values, dtype=float).reshape(-1)
        counts = np.asarray(counts, dtype=int).reshape(-1)

        min_len = min(x_values.size, counts.size)

        x_values = x_values[:min_len]
        counts = counts[:min_len]

        second_arr = np.full(min_len, float(second_pos))

        line_raw = np.column_stack(
            (x_values, second_arr, counts)
        )

        if self.raw_intensity is None:
            self.raw_intensity = line_raw
        else:
            self.raw_intensity = np.append(
                self.raw_intensity,
                line_raw,
                axis=0
            )

        # self.raw_intensity_update.emit(self.raw_intensity)

    def get_line_index(self, packet):
        """
        Get line index from packet.
        Prefer packet['line_index']; fallback to nearest line_pos.
        """

        if "line_index" in packet:
            line_index = int(packet["line_index"])

            if 0 <= line_index < len(self.yArr):
                return line_index

        line_pos = float(packet["line_pos"])

        return int(np.argmin(np.abs(self.yArr - line_pos)))

    def emit_image_update(self, force=False):
        if self.map is not None:
            self.image_update.emit(self.map.copy())

    # def run(self):
    #     self.running = True
    #     # Because the first data in counts do not have meaning, we delete it in the ConfocalScanThread
    #     # Cause self.xData has one more data point than self.countsData
    #     # Deal with this first
    #     x1 = deque(self.xData)
    #     x2 = deque(self.xData)
    #     x1.pop()
    #     # x2.pop()
    #     x2.popleft()
    #
    #     new_xData = (np.asarray(x1) + np.asarray(x2)) / 2
    #     self.xData = new_xData
    #     # Create count data array
    #     picked_counts = []
    #
    #     for x_pos in self.xArr:
    #         # Search self.xData for the closest value
    #         each_x_arr = np.array([x_pos] * np.size(self.xData))
    #         diff_arr = list(np.abs(self.xData - each_x_arr))
    #         closest_index = diff_arr.index(min(diff_arr))
    #
    #         cts_temp = self.countsData[closest_index]
    #
    #         picked_counts.append(cts_temp * self.sample_rate)
    #
    #
    #     # Find the location in y axes
    #     y_index = list(self.yArr).index(self.y)
    #
    #     # Put it into the image matrix
    #
    #     self.map[y_index] = np.asarray(picked_counts)
    #
    #     # Save the raw data: original_xData, original_y, Counts data
    #     y_arr = [self.y] * len(self.xData)
    #
    #     line_raw = np.transpose(np.asarray([self.xData, y_arr, self.countsData], dtype=object))
    #
    #     if self.raw is None:
    #         self.raw = line_raw
    #     else:
    #         self.raw = np.append(self.raw, line_raw, axis=0)
    #
    #     # Update the image with 1 second interval
    #     t = time.perf_counter()
    #     if t - self.lastUpdateTime > 1:
    #         self.update.emit(self.map)
    #         self.lastUpdateTime = t
    #
    #     self.running = False
