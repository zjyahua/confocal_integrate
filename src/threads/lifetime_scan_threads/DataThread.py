"""
This Thread is used for data processing
"""

from PyQt5 import QtCore
from collections import deque
import numpy as np
import time
import sys

class DataThread(QtCore.QThread):
    """
    Data handler module as a thread, based on PyQt5.QtCore.QThread
    Use to handle line data and put it into image matrix.
    Needs:
    self.xArr: list of x command positions (100 points)
    self.y: y command position for the line
    self.yArr: list of y command positions (100 points)
    self.xData: position data
    self.countsData: photon count data
    """

    SIGNAL_update = QtCore.pyqtSignal(np.ndarray, name='update')

    def __init__(self, parent=None):
        self.lastUpdateTime = time.perf_counter()
        super().__init__(parent)
        self.raw = None
        self.y = None
        self.running = False
        self.xArr = []
        self.yArr = []
        self.map = None
        self.resolution = 100
        self.bin_num = 2000
        self.bin_width = 1000
        # self.sample_rate = 400
        # self.xData = []
        self.countsData = []
        self.countsIntensity = []

    def run(self):
        self.running = True

        # Find the location in y axes
        y_index = list(self.yArr).index(self.y)

        # Put it into the image matrix
        nx_pixel = self.resolution
        ny_pixel = len(self.yArr)
        expected_size = nx_pixel * ny_pixel

        if len(self.countsIntensity) != expected_size:
            raise ValueError(
                f"countsData length mismatch: got {len(self.countsIntensity)}, "
                f"expected {expected_size} = {nx_pixel} * {ny_pixel}"
            )


        # Put it into the image matrix
        # self.countsIntensity = np.sum(self.countsData,axis=1)
        self.map = np.reshape(self.countsIntensity, (ny_pixel, nx_pixel))

        if y_index == ny_pixel - 1:
            cts = np.asarray(self.countsData)
            x_arr = np.asarray(self.xArr)
            y_arr = np.asarray(self.yArr)
            t_arr = np.arange(self.bin_num) * self.bin_width  # ps

            # Create columns
            x_col = np.tile(np.repeat(x_arr, self.bin_num), ny_pixel)
            y_col = np.repeat(y_arr, nx_pixel * self.bin_num)
            t_col = np.tile(t_arr, nx_pixel * ny_pixel)
            counts_col = cts.reshape(-1)

            self.raw = np.column_stack((x_col, y_col, t_col, counts_col))

        # Updata image
        self.update.emit(self.map)
        self.running = False
