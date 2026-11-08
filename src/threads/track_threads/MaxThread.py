"""
This Thread is used to find the point has the max value of counts
"""
from PyQt5 import QtCore
import numpy as np
import time


class MaxThread(QtCore.QThread):
    """
    Maximizing module as a thread, based on PyQt5.QtCore.QThread
    parameters:
    @hardware: python object of hardware control
    """

    counts = QtCore.pyqtSignal(int)
    moved = QtCore.pyqtSignal(float, float, float)
    tracking_data = QtCore.pyqtSignal(list, list, list, list)
    error = QtCore.pyqtSignal(str)

    def __init__(self, hardware=None, parent=None):
        super().__init__(parent)
        self._hardware = hardware

        self.step = 0.1  # Um
        self.step_angle = 0.001 # angle  # 0.1V 4um 0.01 400nm 0.0025 100nm
        self.integral_time = 200  # Ms
        self.scan_mode = 1  # 0 for piezo stage, 1 for galvo mirror

    def set_parameters(
            self,
            integral_time=None,
            scan_mode=None
    ):
        """
        Set parameters before starting the thread.
        """
        if integral_time is not None:
            integral_time = int(integral_time)
            if integral_time <= 0:
                raise ValueError("integral_time must be greater than 0 ms.")
            self.integral_time = integral_time

        if scan_mode is not None:
            scan_mode = int(scan_mode)
            if scan_mode not in (0, 1):
                raise ValueError("scan_mode must be 0 or 1.")
            self.scan_mode = scan_mode

    def stop(self):
        """
        Stop the max tracking thread safely.
        """
        self.requestInterruption()

    def _check_hardware(self):
        """
        Check basic hardware interface.
        """

        if self._hardware is None:
            raise RuntimeError("Hardware is None.")

        if not hasattr(self._hardware, "counter"):
            raise RuntimeError("Hardware has no counter.")

        if not hasattr(self._hardware, "mover"):
            raise RuntimeError("Hardware has no mover.")

        if not hasattr(self._hardware, "scanner"):
            raise RuntimeError("Hardware has no scanner.")

    def _sleep_integral_time(self):
        """
        Sleep for one integral time.
        Return
        ------
        bool
            True if normal, False if interruption requested.
        """
        sleep_ms = int(self.integral_time)

        # 分成小段 sleep，这样 stop() 时不会等太久
        chunk = 20
        elapsed = 0

        while elapsed < sleep_ms:
            if self.isInterruptionRequested():
                return False

            dt = min(chunk, sleep_ms - elapsed)
            self.msleep(dt)
            elapsed += dt

        return not self.isInterruptionRequested()

    def _scan_axis(self, read_func, move_func, step):
        """
        Generic 1D scan.

        Parameters
        ----------
        read_func : callable
            Function to read current position.
        move_func : callable
            Function to move to target position.
        step : float
            Scan step.

        Returns
        -------
        list or None
            [position_list, counts_list, position_origin, position_final]
        """

        cts_arr = []

        pos_origin = float(read_func())

        # 生成 7 个点：-3, -2, -1, 0, 1, 2, 3
        pos_list = pos_origin + step * np.arange(-3, 4)

        dummy_pos = pos_origin - 4 * step

        max_cts = -np.inf
        pos_final = pos_origin

        # Move to dummy point and discard first buggy count
        move_func(float(dummy_pos))

        if not self._sleep_integral_time():
            return None

        try:
            _ = self._hardware.counter.get_once_counter_data()
        except Exception:
            # 如果 discard 失败，也继续交给外层处理更清晰
            raise

        for point in pos_list:
            if self.isInterruptionRequested():
                return None

            move_func(float(point))

            if not self._sleep_integral_time():
                return None

            counts_data = self._hardware.counter.get_once_counter_data()
            counts_data = int(counts_data)

            self.counts.emit(counts_data)
            cts_arr.append(counts_data)

            if counts_data > max_cts:
                max_cts = counts_data
                pos_final = float(point)

        # Move to best position
        if not self.isInterruptionRequested():
            move_func(float(pos_final))

        return [
            pos_list.tolist(),
            cts_arr,
            float(pos_origin),
            float(pos_final)
        ]

    def scan_mover(self, ax):
        """
        Scan one mover axis.
        """

        return self._scan_axis(
            read_func=lambda: self._hardware.mover.read_pos(ax),
            move_func=lambda pos: self._hardware.mover.move_pos(ax, pos),
            step=self.step
        )

    def scan_scanner_angle(self, ax):
        """
        Scan one scanner angle axis.
        """

        return self._scan_axis(
            read_func=lambda: self._hardware.scanner.read_angle_analog(ax),
            move_func=lambda angle: self._hardware.scanner.mov_angle_analog(ax, angle),
            step=self.step_angle
        )

    def run(self):
        """
        Thread entry.
        """
        counter_started = False
        try:
            self._check_hardware()
            counter = self._hardware.counter

            counter.configure_count_once(self.integral_time)
            counter.start_once_counter_measure()
            counter_started = True
            time.sleep(1)

            if self.scan_mode == 0:
                # Piezo / mover mode
                x_axis = self.scan_mover("1")
                if x_axis is None:
                    return

                y_axis = self.scan_mover("2")
                if y_axis is None:
                    return

            elif self.scan_mode == 1:
                # Galvo / scanner mode
                x_axis = self.scan_scanner_angle("1")
                if x_axis is None:
                    return

                y_axis = self.scan_scanner_angle("2")
                if y_axis is None:
                    return

            else:
                raise RuntimeError(f"Invalid scan_mode: {self.scan_mode}")

            # Z axis always uses mover
            z_axis = self.scan_mover("3")
            if z_axis is None:
                return

            if self.isInterruptionRequested():
                return

            if self.scan_mode == 0:
                x_now = float(self._hardware.mover.read_pos("1"))
                y_now = float(self._hardware.mover.read_pos("2"))
                z_now = float(self._hardware.mover.read_pos("3"))
            else:
                x_now = float(self._hardware.scanner.read_angle_analog("1"))
                y_now = float(self._hardware.scanner.read_angle_analog("2"))
                z_now = float(self._hardware.mover.read_pos("3"))

            self.moved.emit(x_now, y_now, z_now)

            pos_list = [
                x_axis[0],
                y_axis[0],
                z_axis[0]
            ]

            cts_list = [
                x_axis[1],
                y_axis[1],
                z_axis[1]
            ]

            pos_origin = [
                x_axis[2],
                y_axis[2],
                z_axis[2]
            ]

            pos_final = [
                x_axis[3],
                y_axis[3],
                z_axis[3]
            ]

            self.tracking_data.emit(
                pos_list,
                cts_list,
                pos_origin,
                pos_final
            )

        except Exception as e:
            self.error.emit(str(e))

        finally:
            if self._hardware is not None and hasattr(self._hardware, "counter"):
                if counter_started:
                    try:
                        self._hardware.counter.stop_once_counter_measure()
                    except Exception as e:
                        self.error.emit(f"Failed to stop counter: {e}")
