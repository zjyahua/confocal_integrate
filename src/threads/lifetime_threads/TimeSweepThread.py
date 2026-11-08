"""
Created on Jun 30, 2021

This Thread is used to do the Time Sweep experiment.

@author: Linjie
"""

from PyQt5 import QtCore
import time
import numpy as np
import random


class TimeSweepThread(QtCore.QThread):

    # Signal for passing the data to main thread ([Signal, Loop Number])
    SIGNAL_update = QtCore.pyqtSignal(np.ndarray, int, name='update')
    # Signal for passing the tracking data to main thread
    # SIGNAL_tracking_data = QtCore.pyqtSignal(list, list, list, list, name='tracking_data')

    def __init__(self, hardware=None, parent=None):
        super().__init__(parent)
        # Get hardware from Main Thread
        self._hardware = hardware
        self.step = 0.05  # Um
        self.integral_time = 100  # Ms
        self.countRate = 1000 / self.integral_time
        # Initialize scanning parameters
        # self.time_arr = []
        self.bin_width = 50
        self.bin_num = 2000
        self.pulse_form = []
        # Parameters can be changed when pause/resume the experiment
        self.loop_num = [0, 10]  # [Current Loop , Total Loop]
        self.average_num = 1000
        self.freq = 1000 * 1e3
        # Parameter may change during the experiment
        # self.threshold = 0
        self.sin = False
        self.self_define = False
        self.running_status = False
        self.pause = False
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
        self._hardware.counter.configure_flim(self.bin_width, self.bin_num, number_of_gates=int(1))
        self._hardware.counter.start_flim_measure()
        time.sleep(1)
        self._hardware.pulser.trigger_mode()

        if self.sin is True:
            self.pulse_seq = self.generate_sin_seq(f=self.freq, multi_num=self.average_num)
        elif self.self_define is True:
            self.pulse_seq = self.generate_seq(t=0, pulse_form=self.pulse_form, multi_num=self.average_num)
        else:
            self.running_status = False
            print("Please check the sin or self define box !")
        # Sweeping Time
        # Do the sweep by loop
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
                self.update.emit(sig, self.loop_num[0])
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
        # At the end of the scanning, set running status to False
        self.running_status = False
        # Sleep time to update the data again
        time.sleep(1)
        # If the point_num and loop_num meet the following condition, means the scanning fully finish
        if self.loop_num[0] == self.loop_num[1]:
            # Update the last data
            self.update.emit(sig, self.loop_num[1] - 1)
        else:
            # Update the last data
            self.update.emit(sig, self.loop_num[0])

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

    def generate_seq(self, t, pulse_form, multi_num):
        """
        This method first replace the 't' in the sequence with the time parameter, t
        :param t: The time to replace the 't' in the sequence.
        :param pulse_form: The pulse generated by the SeqEditor
        :return: Pulse sequence with the trigger pulse channel and delay
        """
        # Replace the t with time parameter
        # t_delay = 320
        sum = int(pulse_form['Sum'][-1].replace("+", '').replace("-", '').replace("t", ''))
        if '+' in pulse_form['Sum'][-1]:
            sum += t
        elif '-' in pulse_form['Sum'][-1]:
            sum -= t
        else:
            pass

        # print(pulse_form)
        laser_seq_list = pulse_form['Laser']
        aom_seq_list = pulse_form['AOM']
        aom_seq_cal = []
        laser_seq_cal = [0]
        for i in range(len(laser_seq_list))[1:]:
            laser_seq_cal_data = int(laser_seq_list[i].replace("+", '').replace("-", '').replace("t", ''))
            if '+' in laser_seq_list[i]:
                laser_seq_cal_data += t
            elif '-' in laser_seq_list[i]:
                laser_seq_cal_data -= t
            else:
                pass
            laser_seq_cal.append(laser_seq_cal_data)
        for i in range(len(aom_seq_list))[1:]:
            aom_seq_cal.append(float(aom_seq_list[i].replace("+", '').replace("-", '').replace("t", '')))
        laser_seq_cal.append(int(sum))
        laser_seq_cal = np.array(laser_seq_cal[1:]) - np.array(laser_seq_cal[:-1])
        laser_seq = []
        aom_voltage_seq = []
        for i in range(len(laser_seq_cal)):
            if i % 2 != 0:
                laser_seq.append((laser_seq_cal[i], 1))
                index = int((i - 1) / 2)
                aom_voltage_seq.append((laser_seq_cal[i], 1 * aom_seq_cal[index]))
            else:
                laser_seq.append((laser_seq_cal[i], 0))
                aom_voltage_seq.append((laser_seq_cal[i], 0))

        sig_seq_list = pulse_form['Sig']
        sig_seq_cal = [0]
        for i in range(len(sig_seq_list))[1:]:
            sig_seq_cal_data = int(sig_seq_list[i].replace("+", '').replace("-", '').replace("t", ''))
            if '+' in sig_seq_list[i]:
                sig_seq_cal_data += t
            elif '-' in sig_seq_list[i]:
                sig_seq_cal_data -= t
            else:
                pass
            sig_seq_cal.append(sig_seq_cal_data)
        sig_seq_cal.append(int(sum))
        sig_seq_cal = np.array(sig_seq_cal[1:]) - np.array(sig_seq_cal[:-1])
        sig_seq = []
        for i in range(len(sig_seq_cal)):
            if i % 2 != 0:
                sig_seq.append((sig_seq_cal[i], 1))
            else:
                sig_seq.append((sig_seq_cal[i], 0))

        laser_seq = laser_seq * multi_num
        sig_seq = sig_seq * multi_num
        aom_voltage_seq = aom_voltage_seq * multi_num

        seq_list = [(0, laser_seq), (1, sig_seq), (0, aom_voltage_seq)]
        return seq_list

class EndForLoop(Exception):
    pass
