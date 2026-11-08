"""
This Thread is used to counting
"""

from PyQt5 import QtCore
import time


class CountThread(QtCore.QThread):
    """
    Counting module as a thread, based on PyQt5.QtCore.QThread
    parameters:
    @hardware: python object of hardware control
    """

    counts = QtCore.pyqtSignal(int)
    error = QtCore.pyqtSignal(str)

    def __init__(self, hardware=None, parent=None):
        super().__init__(parent)
        self._hardware = hardware
        self.running = False
        # self.pause = False
        # integral time unit is ms
        self.integral_time = 1000

    def set_integral_time(self, integral_time):
        """
        Set integral time in ms.
        """
        integral_time = int(integral_time)

        if integral_time <= 0:
            raise ValueError("integral_time must be greater than 0 ms.")

        self.integral_time = integral_time

    def stop(self):
        """
        Stop the counting thread safely.
        """
        self.requestInterruption()

    def run(self):
        """
        Thread entry.
        """
        if self._hardware is None:
            self.error.emit("Hardware is None.")
            return

        if not hasattr(self._hardware, "counter"):
            self.error.emit("Hardware has no counter.")
            return

        try:
            self._hardware.counter.configure_count_once(self.integral_time)
            self._hardware.counter.start_once_counter_measure()
            time.sleep(1)

            while not self.isInterruptionRequested():
                # 等待一个积分周期
                self.msleep(self.integral_time)
                if self.isInterruptionRequested():
                    break

                cts = self._hardware.counter.get_once_counter_data()
                self.counts.emit(int(cts))
                print(cts)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            try:
                self._hardware.counter.stop_once_counter_measure()
            except Exception as e:
                self.error.emit(f"Failed to stop counter: {e}")
