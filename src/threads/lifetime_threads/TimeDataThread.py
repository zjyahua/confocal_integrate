"""
Created on Jun 30, 2021

This Thread is used to do the data processing in the experiment.
The Raw Data is all 0, when the scanning get the new data, the data at corresponding location will be rewrite.

@author: Linjie
"""

from PyQt5 import QtCore
import numpy as np
import time


class TimeDataThread(QtCore.QThread):

    SIGNAL_update = QtCore.pyqtSignal(list, name='update')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_update_time = time.perf_counter()
        # self._hardware = hardware
        self.running_status = False
        self.raw = None

        # Data for whole measurement
        # self.ref_all = []
        self.sig_all = []
        self.time_arr = []
        # Input data
        self.sig = None
        # self.ref = None
        self.loop = None

        # self.ref_ave_temp = []
        self.sig_ave_temp = []
        # Data used to emit
        self.ref_emit = []
        self.sig_emit = []
        # Init loop_old to -1 make sure the data will be update at the beginning of the scanning
        self.loop_old = -1

    def run(self):
        """
        Emit: List of the average value of Signal and Reference (Only for update the plot in GUI)
        Update the data for the plot every 1 second
        Rewrite the value in raw (Raw Data)
        """
        self.running_status = True
        # Rewrite the data in raw data
        # For each point data in raw, it contains 3 value: Signal Counts, Frequency/Time, Loop Number
        try:
            for i in range(len(self.time_arr)):
                # print(i)
                self.raw[7][self.loop][i] = [self.sig[i], self.time_arr[i], self.loop]
        except BaseException as e:
            print(e)
            return
        # Decide if to add a new loop for the average
        state = self.loop > self.loop_old
        if state:
            self.loop_old = self.loop
            # self.ref_all.append(self.ref_ave_temp)
            self.sig_all.append(self.sig_ave_temp)

        # Replace the data with the data we get in the scanning
        self.sig_all[self.loop][:] = self.sig

        # Update the plot every 1 second.
        t = time.perf_counter()
        if t > self.last_update_time or state:
            # self.ref_emit = list(np.average(self.ref_all, axis=0))
            self.sig_emit = list(np.average(self.sig_all, axis=0))
            self.update.emit(self.sig_emit)
            self.last_update_time = t

        self.running_status = False
