from src.hardware import DeviceManager
import numpy as np

hardware = DeviceManager()
hardware.init_scanner()

scan_dwell_time = 1
resolution = 100

x_start = -1
x_end = 1

scan_freq = 10

hardware.scanner.scan_mode_sin_analog(float(x_start), float(x_end), scan_freq)
hardware.scanner.scanning_analog()





