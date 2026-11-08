from PyQt5 import QtCore
import time
import numpy as np

class FreqSweepThread(QtCore.QThread):
    SIGNAL_update = QtCore.pyqtSignal(np.ndarray, int, int, name='update')
    SIGNAL_updatastate = QtCore.pyqtSignal(int, int, int, name='updatestate')
    SIGNAL_track = QtCore.pyqtSignal(int, name='track')

    def __init__(self, hardware=None, parent=None):
        super().__init__(parent)
        # Get hardware from Main Thread
        self._hardware = hardware
        # Initialize scanning parameters
        self.freq_arr = []
        self.bin_width = 50
        self.bin_num = 2000
        # Parameters can be changed when pause/resume the experiment
        self.loop_num = [0, 10]  # [Current Loop , Total Loop]
        self.freq_num = [0, 16]  # [Current freq, Total freq]
        self.average_num = 1000
        self.freq = 1000 * 1e3 # kHz
        # Parameter may change during the experiment
        # self.threshold = 0
        self.running_status = False
        self.pause = False
        self.state_pause = False
        # Init
        self.pulse_seq = []

    def run(self):
        """
        Do the Scanning part
        :return: None
        :emit: [Signal, Reference, Time, Point Number, Loop Number]
        """
        # Define the running status
        self.running_status = True

        for freq in self.freq_arr:
            self.state_pause = True
            print("current freq (kHz):", freq)
            self.freq = freq * 1e3 # kHz
            self.average_num = int(freq * 10)
            self.bin_width = int(5000 / freq * 1000)
            # update state in each freq
            self.updatestate.emit(int(freq), self.average_num, self.bin_width)
            while self.state_pause is True:
                pass
            self.pulse_seq = self.generate_sin_seq(f=self.freq, multi_num=self.average_num)
            self._hardware.counter.configure_flim(self.bin_width, self.bin_num, number_of_gates=int(1))
            self._hardware.counter.start_flim_measure()
            time.sleep(1)
            self._hardware.pulser.trigger_mode()
            # Sweeping Time
            # Do the sweep by loop
            self.loop_num[0] = 0
            self.track_pause = True
            for loop in range(self.loop_num[1])[self.loop_num[0]:]:
                # Sweep the Time
                # If running, do the scan
                # Generate the Pulse Sequence for the time
                while self.running_status is True:
                    self.pause = True
                    # print(self.pulse_seq)
                    # Write Pulse Sequence into Pulse Generator
                    self._hardware.pulser.upload_seq_list(self.pulse_seq, 1)
                    # Start Pulse Generator
                    self._hardware.pulser.start_now()
                    while self._hardware.pulser.is_running():
                        pass
                    # Get the data and close the Counter
                    time.sleep(0.05)
                    cts_arr = self._hardware.counter.get_flim_data()
                    sig = cts_arr[0]
                    self._hardware.counter.flim_recount()
                    # Emit the data to the Main Thread
                    self.update.emit(sig, self.loop_num[0], self.freq_num[0])
                    while self.pause is True:
                        pass
                    break

                # If not scanning, jump out of all the loop
                else:
                    # print(1)
                    try:
                        raise EndForLoop()
                    except BaseException as e:
                        print(e)
                        return
                # print(1)
                # When finish one loop, init the point number and update the loop number
                self.loop_num[0] = self.loop_num[0] + 1
                # print(1)

            self._hardware.pulser.init_ps()
            self._hardware.counter.stop_flim_measure()
            self.track.emit(self.freq_num[0])
            while self.track_pause is True:
                pass
            self.freq_num[0] = self.freq_num[0] + 1

        # At the end of the scanning, set running status to False
        self.running_status = False
        # Sleep time to update the data again
        time.sleep(1)
        # If the point_num and loop_num meet the following condition, means the scanning fully finish
        if self.loop_num[0] == self.loop_num[1]:
            # Update the last data
            self.update.emit(sig, self.loop_num[1] - 1, self.freq_num[1]-1)
        else:
            # Update the last data
            self.update.emit(sig, self.loop_num[0], self.freq_num[0])

    def generate_sin_seq(self, f, multi_num):
        sum = int(1/f*1e9)
        sig_seq = [(10, 1), (sum-10, 0)] * multi_num
        laser_seq = [(sum, 1)] * multi_num

        t = np.linspace(start=4, stop=sum - 4, num=int(sum / 8))
        y = 0.65 + 0.1 * np.cos(2 * np.pi * f * t * 1e-9)
        # V = (3.513 * np.power(y, 5) - 9.09 * np.power(y, 4) + 9.365 * np.power(y, 3) - 4.721 * np.power(y, 2)
        #      + 1.591 * np.power(y, 1) + 0.3405)
        aom_voltage_seq = []
        for i in range(len(t)):
            aom_voltage_seq.append((8, round(y[i], 4)))
        aom_voltage_seq = aom_voltage_seq * multi_num
        # aom_voltage_seq = [(sum//2, 1.0), (sum//2, 0.5)] * multi_num
        seq_list = [(0, laser_seq), (1, sig_seq), (0, aom_voltage_seq)]
        return seq_list

class EndForLoop(Exception):
    pass