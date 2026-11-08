from PyQt5 import QtCore
import numpy as np
from scipy.optimize import curve_fit
import time

class FreqDataThread(QtCore.QThread):
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
        self.freq_arr = []
        self.time_arr = []
        self.initial_fit_parameter = [10, 5, 0, 20]
        self.freq_index = 0
        # Input data
        self.sig = None
        self.loop = None
        self.sig_ave_temp = []
        # Data used to emit
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
            print("start fit")
            popt, pcov = curve_fit(self.cos_fit_function, self.time_arr, self.sig, p0=self.initial_fit_parameter)
            a_fit, f_fit, phi_fit, b_fit = popt
            mod_amp_fit = np.abs(a_fit /b_fit)
            self.raw[7][self.freq_index][self.loop] = [mod_amp_fit, self.loop, self.freq_arr[self.freq_index]]

        except BaseException as e:
            print("FDThread error:",e)
            return
        # Decide if to add a new loop for the average
        state = self.loop > self.loop_old
        if state:
            self.loop_old = self.loop
            # self.ref_all.append(self.ref_ave_temp)
            self.sig_all.append(self.sig_ave_temp)

        # Replace the data with the data we get in the scanning
        self.sig_all[self.loop][self.freq_index] = mod_amp_fit
        # Update the plot every 1 second.
        t = time.perf_counter()
        if t > self.last_update_time or state:
            # self.ref_emit = list(np.average(self.ref_all, axis=0))
            self.sig_emit = list(np.average(self.sig_all, axis=0))
            self.update.emit(self.sig_emit)
            self.last_update_time = t

        self.running_status = False

    def cos_fit_function(self, t, a, f, phi, b):
        return a * np.cos(2 * np.pi * f * t * 10**-6 + phi) + b
