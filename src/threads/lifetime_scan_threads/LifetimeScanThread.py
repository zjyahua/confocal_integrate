"""
This Thread used for confocal scanning part
"""
import time

from PyQt5 import QtCore
import numpy as np

class LifetimeScanThread(QtCore.QThread):
    """
    Confocal Scanning module as a thread, based on PyQt5.QtCore.QThread
    """
    SIGNAL_update = QtCore.pyqtSignal(float, list, name='update')
    SIGNAL_update_ready = QtCore.pyqtSignal(float, list, list, name='update_ready')

    def __init__(self, hardware=None, parent=None):
        self._hardware = hardware
        super().__init__(parent)  # Inherit the init method of parent class
        self.running = False
        self.parameters = [-2.5, 2.5, 0.05, -2.5, 2.5, 0.05, 100]
        self.bin_width = 50
        self.bin_num = 2000
        self.pulse_seq_first = []
        self.pulse_seq_normal = []
        self.seq_state = 'Square'
        self.ctsArr = []
        self.intArr = []
        self.resolution = int(100)
        self.scan_time_pixel = int(10) # 10ms
        self.period  = int(1000) #ms
        self.scan_freq = 1 # Hz
        self.laser_freq = 100 #kHz
        # [FAX_Start, FAX_End, FAX_Step, SAX_Start, SAX_End, SAX_Step, TAX_Position]  FAX: fast axes SAX: slow axes

    def generate_scan_sequence(self,scan_time_pixel,resolution, laser_freq, first_line = 0):
        period = int(scan_time_pixel * resolution / 0.8 * 1e6)  # ns
        if first_line == 0:
            delay = int(1 * 1e9)
        else:
            delay = int(1 * 1e8)
        segment = int(1 / laser_freq * 1e6) # ns  10us=10000ns
        multi_num = int(period * 0.8 / segment)  # 100ms*0.8 / period =8000
        laser_seq = [(int(delay * 0.1), 0)]+ [(segment // 2, 1),(segment // 2, 0)] * multi_num + [(int(period * 0.2), 0)]
        # laser_seq = [(int(delay * 0.1), 0), (period, 1)]
        aom_voltage_seq = [(int(delay * 0.1), 1.0),(period, 1.0)]
        # 80% period for fluorescence collect, 20% for scan back
        # sig_seq = [(int(delay * 0.1), 0)] + [(segment * 0.1, 1), (segment * 0.9, 0)] * int(resolution * 1.25)
        sig_seq = [(int(delay * 0.1), 0)] + [(int(scan_time_pixel * 1e6 * 0.9), 1), (int(scan_time_pixel * 1e6 * 0.1), 0)] * int(resolution) + [(int(period * 0.2), 0)]
        awg_seq = [(int(delay * 0.1), 0), (int(period * 0.1), 1), (int(period * 0.9), 0)]
        seq_list = [(0, laser_seq), (1, sig_seq),(5, laser_seq),(6, awg_seq), (0, aom_voltage_seq)]
        return seq_list

    def run(self):
        self.running = True
        # Move to Goal layer
        print('move to goal layer')
        self._hardware.mover.move_pos('3', self.parameters[6])
        x_start, x_end, x_step, y_start, y_end, y_step = self.parameters[:6]
        y_axis = np.arange(y_start, y_end, y_step)
        # set waveform and trigger for scanning
        nx_pixel = self.resolution
        ny_pixel = int(len(y_axis))
        self._hardware.counter.configure_flim_scan(self.bin_width, self.bin_num, number_of_gates=int(nx_pixel * ny_pixel))
        # self._hardware.counter.configure_scan(number_of_gates=int(nx_pixel * ny_pixel), scan_method=1)
        # x max up take int
        self.period = int(self.scan_time_pixel * self.resolution / 0.8)  # ms
        self.scan_freq = round(float(1000/self.period),1) # 0.8Hz for 10ms 100 pixel
        self._hardware.scanner.scan_mode_analog(float(x_start), float(x_end), self.scan_freq)
        self._hardware.scanner.scanning_analog()
        self._hardware.counter.start_flim_scan_measure()
        # time.sleep(1)
        self._hardware.pulser.trigger_mode()
        self.pulse_seq_first = self.generate_scan_sequence(self.scan_time_pixel, self.resolution,self.laser_freq, first_line=0)
        self.pulse_seq_normal = self.generate_scan_sequence(self.scan_time_pixel, self.resolution, self.laser_freq, first_line=1)
        self._hardware.pulser.upload_seq_list(self.pulse_seq_first, 1)
        # check pulse seq
        if self.seq_state is False:
            self.running = False
        # scan and deal with data
        print('start scan')
        time.sleep(1)
        # Scanning process

        for i, y_points in enumerate(y_axis):
            if not self.running:
                print('Warning: Scanning is stopped!')
                break

            self._hardware.scanner.mov_angle_analog('2', y_points)
                    # print(self._hardware.mover.read_pos('2'))
            try:
                if i == 1:
                    self._hardware.pulser.upload_seq_list(self.pulse_seq_normal, 1)
                # Start Pulse Generator
                self._hardware.pulser.start_now()
                while self._hardware.pulser.is_running():
                    time.sleep(0.001)

                if i == ny_pixel - 1:
                    self.ctsArr, self.intArr = self._hardware.counter.get_flim_scan_ready_data()
                    self.update_ready.emit(y_points,self.ctsArr,self.intArr)
                else:
                    self.intArr = self._hardware.counter.get_flim_scan_current_data()
                    self.update.emit(y_points, self.intArr)
            except BaseException as e:
                print(e, y_points)
                pass
                # print(self.ctsArr)
                # self.update.emit(y_points, self.ctsArr)

        self.running = False
        time.sleep(0.1)

        self._hardware.pulser.init_ps()
        self._hardware.counter.flim_scan_recount()
        self._hardware.counter.stop_flim_scan_measure()
        self._hardware.scanner.scanning_analog_close()
        self._hardware.scanner.single_angle_mode_analog('1')


