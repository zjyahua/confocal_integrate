"""

"""

import sys

from ui.uipy.mainWindow import Ui_MainWindow
from PyQt5 import QtWidgets, QtCore

from src.interface.confocal_scan import mainGUI as Confocal_interface
from src.interface.track import mainGUI as Track_interface
from src.interface.sequence import mainGUI as Sequence_interface
try:
    # 荧光寿命模块：本地保留，暂不包含在公开仓库中（功能已并入单点脉冲实验）
    from src.interface.lifetime import mainGUI as lifetime_interface
except ImportError:
    lifetime_interface = None
from src.interface.scan_image_deal import mainGUI as scan_image_process_interface
from src.interface.single_point_exp import mainGUI as Single_point_exp_interface
from src.hardware import DeviceManager
import src.utils.logger as logger


class mainGUI(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.hardware = DeviceManager()
        self.laser_status = 0
        self.connect_pb_all()
        self.Confocal_interface = None
        self._hardware_cleaned = False
        self.Track_interface = None
        self.Sequence_interface = None
        self.lifetime_interface = None
        self.Singe_point_exp_interface = None
        self.data_process_scan_image_interface = None
        # self.PulseESR_interface = None

    def connect_pb_all(self):
        # experiment interface group
        self.ui.pbExpConfocal.clicked.connect(self.open_confocal_interface)
        self.ui.pbExpTrack.clicked.connect(self.open_track_interface)
        self.ui.pbExpSequence.clicked.connect(self.open_sequence_interface)
        if lifetime_interface is None:
            self.ui.pbExpLifetime.setEnabled(False)
            self.ui.pbExpLifetime.setToolTip('本版本未包含荧光寿命模块（功能已并入单点脉冲实验）')
        else:
            self.ui.pbExpLifetime.clicked.connect(self.open_lifetime_interface)
        self.ui.pbExpTimePulse.clicked.connect(self.open_single_point_exp_interface)
        # data process interface group
        self.ui.pbDP_confocal.clicked.connect(self.open_data_process_scan_image_interface)
        # self.ui.pbExpRotation.clicked.connect(self.open_PulseESRPolarization_interface)
        # self.ui.pbExpESR.clicked.connect(self.open_PulseESR_interface)
        # pb button connect
        self.ui.pbPiezoInit.clicked.connect(self.hardware.init_mover)
        self.ui.pbPiezoReset.clicked.connect(self.hardware.reset_mover)
        self.ui.pbGalvaInit.clicked.connect(self.hardware.init_scanner)
        self.ui.pbGalvaReset.clicked.connect(self.hardware.reset_scanner)
        # self.ui.pbPulseGenInit.clicked.connect(lambda: self.hardware.init_pulser())
        self.ui.pbPulseGenInit.clicked.connect(self.hardware.init_pulser)
        self.ui.pbPulseGenReset.clicked.connect(self.hardware.reset_pulser)
        self.ui.pbTaggerInit.clicked.connect(self.hardware.init_counter)
        self.ui.pbTaggerReset.clicked.connect(self.hardware.reset_counter)
        self.ui.pbMWInit.clicked.connect(self.hardware.init_mw_source)
        self.ui.pbMWReset.clicked.connect(self.hardware.reset_mw_source)
        self.ui.pbLaserOn.clicked.connect(self.laser_on)
        self.ui.pbLaserOff.clicked.connect(self.laser_off)
        self.ui.pbInitAll.clicked.connect(self.hardware.init_all_device)
        self.ui.pbResetAll.clicked.connect(self.hardware.cleanup)
        # connect device status update signal to handling function
        self.hardware.DeviceStatusUpdate.connect(self.update_hardware_status)

    # function for processing input hardware status signal
    @QtCore.pyqtSlot(str, bool, name='DeviceStatusUpdate')
    def update_hardware_status(self, device, status):
        if device == 'mover':
            self.ui.rbPiezoConnect.setChecked(status), self.ui.rbPiezoDisconnect.setChecked(not status)
            self.ui.pbPiezoInit.setEnabled(not status), self.ui.pbPiezoReset.setEnabled(status)
        elif device == 'scanner':
            self.ui.rbGalvaConnect.setChecked(status), self.ui.rbGalvaDisconnect.setChecked(not status)
            self.ui.pbGalvaInit.setEnabled(not status), self.ui.pbGalvaReset.setEnabled(status)
        elif device == 'pulser':
            self.ui.rbPulseGenConnect.setChecked(status), self.ui.rbPulseGenDisconnect.setChecked(not status)
            self.ui.pbPulseGenInit.setEnabled(not status), self.ui.pbPulseGenReset.setEnabled(status)
        elif device == 'counter':
            self.ui.rbTaggerConnect.setChecked(status), self.ui.rbTaggerDisconnect.setChecked(not status)
            self.ui.pbTaggerInit.setEnabled(not status), self.ui.pbTaggerReset.setEnabled(status)
        elif device == 'MW':
            self.ui.rbMWConnect.setChecked(status), self.ui.rbMWDisconnect.setChecked(not status)
            self.ui.pbMWInit.setEnabled(not status), self.ui.pbMWReset.setEnabled(status)

    # function for handling experiment interface
    @QtCore.pyqtSlot()
    def open_confocal_interface(self):
        if self.hardware.mover_status == 0 and self.hardware.scanner_status == 0:
            print('Please init Piezo stage and Galvo Mirror !')
            return

        if self.Confocal_interface is None:
            self.Confocal_interface = Confocal_interface(hardware=self.hardware)
            self.Confocal_interface.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.Confocal_interface.destroyed.connect(self.confocal_interface_destroyed)
            self.Confocal_interface.show()
            self.ui.statusbar.showMessage('Open Confocal scan window.', msecs=3000)
        else:
            self.Confocal_interface.show()
            self.Confocal_interface.raise_()
            self.Confocal_interface.activateWindow()
            self.ui.statusbar.showMessage('Confocal scan window is opened already!', msecs=3000)

    @QtCore.pyqtSlot()
    def confocal_interface_destroyed(self):
        print("Confocal interface destroyed")
        self.Confocal_interface = None

    @QtCore.pyqtSlot()
    def open_track_interface(self):
        if self.hardware.mover_status == 0:
            print('Please init Piezo stage !')
            return

        if self.Track_interface is None:
            self.Track_interface = Track_interface(hardware=self.hardware)
            self.Track_interface.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.Track_interface.destroyed.connect(self.track_interface_closed)
            self.Track_interface.show()
            self.ui.statusbar.showMessage('Open Track window.', msecs=3000)
        else:
            self.Track_interface.show()
            self.Track_interface.raise_()
            self.Track_interface.activateWindow()
            self.ui.statusbar.showMessage('Track window is opened already!', msecs=3000)

    @QtCore.pyqtSlot()
    def track_interface_closed(self):
        self.Track_interface = None

    @QtCore.pyqtSlot()
    def open_sequence_interface(self):
        if self.Sequence_interface is None:
            self.Sequence_interface = Sequence_interface()
            self.Sequence_interface.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.Sequence_interface.destroyed.connect(self.sequence_interface_closed)
            self.Sequence_interface.show()
            self.ui.statusbar.showMessage('Open Sequence window.', msecs=3000)
        else:
            self.Sequence_interface.show()
            self.Sequence_interface.raise_()
            self.Sequence_interface.activateWindow()
            self.ui.statusbar.showMessage('Sequence window is opened already!', msecs=3000)

    @QtCore.pyqtSlot()
    def sequence_interface_closed(self):
        self.Sequence_interface = None

    @QtCore.pyqtSlot()
    def open_lifetime_interface(self):
        if lifetime_interface is None:
            self.ui.statusbar.showMessage('本版本未包含荧光寿命模块，请使用单点脉冲实验。', msecs=3000)
            return
        if self.lifetime_interface is None:
            self.lifetime_interface = lifetime_interface(hardware=self.hardware, track_interface=self.Track_interface)
            self.lifetime_interface.ExpLifetimeClose.connect(self.lifetime_interface_closed)
            self.lifetime_interface.show()
            self.ui.statusbar.showMessage('Open Sequence window.', msecs=3000)
        else:
            self.ui.statusbar.showMessage('Sequence window is opened already!', msecs=3000)

    @QtCore.pyqtSlot()
    def lifetime_interface_closed(self):
        self.lifetime_interface = None

    @QtCore.pyqtSlot()
    def open_data_process_scan_image_interface(self):
        if self.data_process_scan_image_interface is None:
            self.data_process_scan_image_interface = scan_image_process_interface()
            self.data_process_scan_image_interface.Data_Image_Close.connect(self.data_process_scan_image_interface_closed)
            self.data_process_scan_image_interface.show()
            self.ui.statusbar.showMessage('Open scan image process window.', msecs=3000)
        else:
            self.ui.statusbar.showMessage('scan image process window is opened already!', msecs=3000)

    @QtCore.pyqtSlot()
    def data_process_scan_image_interface_closed(self):
        self.data_process_scan_image_interface = None

    @QtCore.pyqtSlot()
    def open_single_point_exp_interface(self):
        if self.Singe_point_exp_interface is None:
            self.Singe_point_exp_interface = Single_point_exp_interface(
                hardware=self.hardware,
                track_interface=self.Track_interface
            )
            self.Singe_point_exp_interface.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            self.Singe_point_exp_interface.destroyed.connect(self.single_point_exp_interface_closed)
            self.Singe_point_exp_interface.show()
            self.ui.statusbar.showMessage('Open single point experiment window.', msecs=3000)
        else:
            self.Singe_point_exp_interface.show()
            self.Singe_point_exp_interface.raise_()
            self.Singe_point_exp_interface.activateWindow()
            self.ui.statusbar.showMessage('Single point experiment window is opened already!', msecs=3000)

    @QtCore.pyqtSlot()
    def single_point_exp_interface_closed(self):
        self.Singe_point_exp_interface = None

    def closeEvent(self, event):
        quit_message = "Do you want to quit?"

        reply = QtWidgets.QMessageBox.question(
            self,
            "Message",
            quit_message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel
        )

        if reply != QtWidgets.QMessageBox.Yes:
            event.ignore()
            return

        try:
            # 1. 先关闭 Confocal interface
            if self.Confocal_interface is not None:
                ok = self.Confocal_interface.close()

                # 如果 Confocal interface 的 closeEvent 里用户点了 Cancel，
                # close() 会返回 False，此时主程序也不退出
                if not ok:
                    event.ignore()
                    return

            # 2. 关闭 Track interface
            if self.Track_interface is not None:
                ok_track = self.Track_interface.close()

                # 如果 Confocal interface 的 closeEvent 里用户点了 Cancel，
                # close() 会返回 False，此时主程序也不退出
                if not ok_track:
                    event.ignore()
                    return

            # 2. 再清理主程序硬件资源
            self.cleanup_hardware_once()

            event.accept()

        except Exception as e:
            print("Main closeEvent error:", e)
            event.ignore()

    def cleanup_hardware_once(self):
        if getattr(self, "_hardware_cleaned", False):
            return

        self._hardware_cleaned = True

        if self.hardware is not None:
            print("Cleaning hardware...")
            self.hardware.cleanup()
            print("Hardware cleaned")

    # Methods for laser
    def laser_on(self):
        """
        turn on the laser
        """
        if self.hardware.pulser_status == 0:
            print('Please init pulse streamer!')
        elif self.ui.leAOMVoltage.text() == '':
            print('Please type in AOM Voltage!')
        else:
            self.hardware.pulser.all_constant([0], analog_0=float(self.ui.leAOMVoltage.text()))
            self.laser_status = 1
            self.update_laser_state(self.laser_status)

    def laser_off(self):
        """
        turn off the laser
        """
        self.hardware.pulser.init_ps()
        self.laser_status = 0
        self.update_laser_state(self.laser_status)

    def update_laser_state(self, status):
        self.ui.rbLaserOn.setChecked(status), self.ui.rbLaserOff.setChecked(not status)
        self.ui.pbLaserOn.setEnabled(not status), self.ui.pbLaserOff.setEnabled(status)

def blank_function():
    pass


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    myWindow = mainGUI()
    myWindow.show()
    sys.exit(app.exec_())