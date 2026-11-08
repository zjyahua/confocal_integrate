"""
This file used to list all the hardware we use.
"""
import src.utils.logger as logger
from PyQt5 import QtCore
# from src.hardware.XMT_E70D4.API import XMT
from src.hardware.PI_E7273_CDA.API import Mover
from src.hardware.Galvanometer.API import SCANNER
# from src.hardware.SynthUSB3 import SynthUSB3
from src.hardware.Swabian_Pulse_Streamer.API import PulseGenerator
from src.hardware.Swabian_TimeTaggerUltra.API import TimeTaggerCounter
from src.hardware.Synth_HD.API import MicrowaveSynthHD


class DeviceManager(QtCore.QObject):
    # SIGNAL_DeviceStatusUpdate = QtCore.pyqtSignal(str, bool, name='DeviceStatusUpdate')
    DeviceStatusUpdate = QtCore.pyqtSignal(str, bool)
    """
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mover = None
        self.mover_status = 0
        self.scanner = None
        self.scanner_status = 0
        self.pulser = None
        self.pulser_status = 0
        self.counter = None
        self.counter_status = 0
        self.mw_source = None
        self.mw_source_status = 0

    def init_all_device(self, pulser_serial='00-26-32-f0-92-26', counter_serial="2208000ZCM"):
        self.init_mover()
        self.init_pulser()
        self.init_counter()
        self.init_mw_source()
        self.init_scanner()

    def cleanup(self):
        self.reset_mover()
        self.reset_pulser()
        self.reset_counter()
        self.reset_mw_source()
        self.reset_scanner()

    # function for all individual device

    def init_mover(self):
        if not self.mover_status:
            try:
                self.mover = Mover()
                self.mover.connect()
            except BaseException as e:
                logger.logger.info(f"Mover init failed! {e}")
            else:
                self.mover_status = 1
                self.DeviceStatusUpdate.emit('mover', self.mover_status)

    def reset_mover(self):
        if self.mover_status:
            try:
                pass
            except BaseException as e:
                logger.logger.info(f"Mover reset failed! {e}")
            else:
                self.mover = None
                self.mover_status = 0
                self.DeviceStatusUpdate.emit('mover', self.mover_status)

    def init_scanner(self):
        if not self.scanner_status:
            try:
                self.scanner = SCANNER()
                self.scanner.connect_scanner_analog()
            except BaseException as e:
                logger.logger.info(f"Scanner init failed! {e}")
            else:
                self.scanner_status = 1
                self.DeviceStatusUpdate.emit('scanner', self.scanner_status)

    def reset_scanner(self):
        if self.scanner_status:
            try:
                self.scanner.close_scanner_analog()
            except BaseException as e:
                logger.logger.info(f"Scanner reset failed! {e}")
            else:
                self.scanner = None
                self.scanner_status = 0
                self.DeviceStatusUpdate.emit('scanner', self.scanner_status)

    def init_pulser(self):
        if not self.pulser_status:
            try:
                self.pulser = PulseGenerator()
            except BaseException as e:
                logger.logger.warning(f"Pulser init failed! {e}")
            else:
                self.pulser_status = 1
                self.DeviceStatusUpdate.emit('pulser', self.pulser_status)

    def reset_pulser(self):
        if self.pulser_status:
            try:
                self.pulser.init_ps()
            except BaseException as e:
                logger.logger.warning(f"Pulser reset failed! {e}")
            else:
                self.pulser = None
                self.pulser_status = 0
                self.DeviceStatusUpdate.emit('pulser', self.pulser_status)

    def init_counter(self):
        if not self.counter_status:
            try:
                self.counter = TimeTaggerCounter()
            except BaseException as e:
                logger.logger.info(f"Counter init failed! {e}")
            else:
                self.counter_status = 1
                self.DeviceStatusUpdate.emit('counter', self.counter_status)

    def reset_counter(self):
        if self.counter_status:
            try:
                self.counter.on_deactivate()
            except BaseException as e:
                logger.logger.info(f"Counter reset failed! {e}")
            else:
                self.counter = None
                self.counter_status = 0
                self.DeviceStatusUpdate.emit('counter', self.counter_status)

    def init_mw_source(self):
        if not self.mw_source_status:
            try:
                self.mw_source = MicrowaveSynthHD()
                self.mw_source.on_activate()
            except BaseException as e:
                logger.logger.info(f"MW_source init failed! {e}")
            else:
                self.mw_source_status = 1
                self.DeviceStatusUpdate.emit('MW', self.mw_source_status)

    def reset_mw_source(self):
        if self.mw_source_status:
            try:
                self.mw_source.off()
            except BaseException as e:
                logger.logger.info(f"MW_source reset failed! {e}")
            else:
                self.mw_source = None
                self.mw_source_status = 0
                self.DeviceStatusUpdate.emit('MW', self.mw_source_status)
