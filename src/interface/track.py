"""
Created on Dec 3, 2024

This File is the Main Thread for Track
"""

import sys
import os
import yaml
from collections import deque
from ui.uipy.Track.track import Ui_MainWindow
from PyQt5 import QtWidgets, QtCore

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from src.threads.track_threads import CountThread, MaxThread
import src.utils.logger as logger

class mainGUI(QtWidgets.QMainWindow):

    # bool: success
    # str : message
    tracking_finished = QtCore.pyqtSignal(bool, str)

    def __init__(self, parent=None, hardware=None):
        QtWidgets.QWidget.__init__(self, parent)
        # Setup GUI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.position_x = deque(np.arange(10).tolist())
        self.position_y = deque(np.arange(10).tolist())
        self.position_z = deque(np.arange(10).tolist())

        self.count_x = deque(np.zeros(10, dtype=int).tolist())
        self.count_y = deque(np.zeros(10, dtype=int).tolist())
        self.count_z = deque(np.zeros(10, dtype=int).tolist())

        self.countPlot_x = None
        self.countPlot_y = None
        self.countPlot_z = None

        self.track_x_fig = None
        self.track_y_fig = None
        self.track_z_fig = None

        self.track_x_ax = None
        self.track_y_ax = None
        self.track_z_ax = None

        self.config_track = None
        self.hardware_initialized = False
        self.tracking = False
        self.cThread = None
        self.maxThread = None

        self._max_error_msg = ""
        self._max_has_result = False
        # Process for initialization
        self.load_defaults()  # Load defaults
        self.connect_methods()  # Connect methods to slots
        self.init_track_plot()  # Init the plot for Tracking
        self.init_button_status()
        # Hardware
        self.hardware = hardware
        self.init_hardware()

    # Load and Save defaults
    @QtCore.pyqtSlot()
    def open_defaults(self):
        directory = os.path.dirname(os.path.abspath(__file__))
        location, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose Defaults File', directory)
        if location != '':
            self.load_defaults(location)

    def load_defaults(self, config_path='config/config_track.yaml'):
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        self.config_track = load_config(config_path=config_file)
        self.update_ui_based_on_default()

    @QtCore.pyqtSlot()
    def save_defaults(self, config_path='config/config_track.yaml'):
        self.update_default_based_on_ui()
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        save_config(config=self.config_track, config_path=config_file)

    def update_ui_based_on_default(self):
        self.ui.leIntegralTime.setText(str(self.config_track['Count']['integral_time']))
        self.ui.lemovestep.setText(str(self.config_track['move']['piezo_step']))

    def update_default_based_on_ui(self):
        self.config_track['Count']['integral_time'] = float(self.ui.leIntegralTime.text())
        self.config_track['move']['piezo_step'] = float(self.ui.lemovestep.text())

    @staticmethod
    def _ensure_layout(widget):
        """
        Ensure the widget has a QVBoxLayout.
        """
        layout = widget.layout()

        if layout is None:
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

        return layout

    @staticmethod
    def _remove_old_canvas(layout, canvas):
        """
        Remove old matplotlib canvas safely.
        """
        if canvas is not None:
            layout.removeWidget(canvas)
            canvas.setParent(None)
            canvas.deleteLater()

    def _init_single_track_plot(self, axis_name, widget, title):
        """
        Init single track plot.

        Parameters
        ----------
        axis_name : str
            'x', 'y' or 'z'
        widget : QWidget
            Parent widget for this plot
        title : str
            Plot title
        """

        # 1. 确保 widget 有 layout
        layout = self._ensure_layout(widget)

        # 2. 删除旧 canvas
        canvas_attr = f"track_{axis_name}_fig"
        old_canvas = getattr(self, canvas_attr, None)
        self._remove_old_canvas(layout, old_canvas)

        # 3. 创建 Figure 和 Canvas
        fig = Figure(constrained_layout=True)
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)

        # 保存到 self.track_x_fig / track_y_fig / track_z_fig
        setattr(self, canvas_attr, canvas)

        # 4. 创建 axes
        ax = fig.add_subplot(111)

        # 保存到 self.track_x_ax / self.track_y_ax / self.track_z_ax
        ax_attr = f"track_{axis_name}_ax"
        setattr(self, ax_attr, ax)

        # 5. 读取数据
        position = getattr(self, f"position_{axis_name}")
        count = getattr(self, f"count_{axis_name}")

        # 6. 绘图
        line, = ax.plot(position, count)

        # 保存为 self.countPlot_x / self.countPlot_y / self.countPlot_z
        setattr(self, f"countPlot_{axis_name}", line)

        # 7. 美化
        ax.set_title(title)
        ax.set_xlabel("Position")
        ax.set_ylabel("Count")
        ax.grid(True, alpha=0.3)

        canvas.draw_idle()

        return canvas, ax, line

    def init_track_plot(self):
        """
        Init track plots for X/Y/Z axis.
        """
        track_configs = [
            ("x", self.ui.widgetTrackX, "X Axis"),
            ("y", self.ui.widgetTrackY, "Y Axis"),
            ("z", self.ui.widgetTrackZ, "Z Axis"),
        ]

        for axis_name, widget, title in track_configs:
            self._init_single_track_plot(axis_name, widget, title)

    # Methods for initialization
    def connect_methods(self):
        """
        This method connects methods to the slots
        :return: None
        """
        # Menu Bar
        self.ui.actionSave_Defaults.triggered.connect(self.save_defaults)
        self.ui.actionLoad_Defaults.triggered.connect(self.load_defaults)
        # Scan Configration
        self.ui.cBScanType.currentTextChanged.connect(self.scan_type_changed)
        # Move Group
        self.ui.pbleft.clicked.connect(self.move_position_left)
        self.ui.pbright.clicked.connect(self.move_position_right)
        self.ui.checkBoxX.stateChanged.connect(self.x_move_mode)
        self.ui.checkBoxY.stateChanged.connect(self.y_move_mode)
        self.ui.checkBoxZ.stateChanged.connect(self.z_move_mode)
        # Counts Group
        self.ui.pbCountOn.clicked.connect(self.count_start)
        # Track Group
        self.ui.pbMax.clicked.connect(self.track_max_count)

    def init_button_status(self):
        self.hardware_initialized = False
        self.tracking = False
        # Move Group
        self.set_widgets_enabled(self.get_move_widgets(), False)
        self.set_widgets_enabled(self.get_move_xy_widgets(), False)

    def get_move_widgets(self):
        return [
            self.ui.pbleft,
            self.ui.pbright,
            self.ui.checkBoxZ,
            self.ui.lemovestep,
        ]

    def get_move_xy_widgets(self):
        return [
            self.ui.checkBoxX,
            self.ui.checkBoxY,
        ]

    @staticmethod
    def set_widgets_enabled(widgets, enabled):
        for widget in widgets:
            widget.setEnabled(enabled)

    def scan_type_changed(self, text):
        is_galvo = text == "Galvo Mirror"
        unit = "V" if is_galvo else "µm"
        self.set_xy_unit_labels(unit)
        self.update_position()
        self.set_widgets_enabled(self.get_move_xy_widgets(), not is_galvo)

    def set_xy_unit_labels(self, unit):
        labels = [
            self.ui.label_actual_x_unit,
            self.ui.label_actual_y_unit,
        ]

        for label in labels:
            label.setText(unit)

    def is_galvo_scan(self):
        return self.ui.cBScanType.currentText() == "Galvo Mirror"

    def update_position(self) -> None:
        """
        get real position of piezo by measured the realtime position, then update the ui.
        :return: None
        """
        try:
            if self.is_galvo_scan:
                self.ui.leXSet.setText('%.4f' % self.hardware.scanner.read_angle_analog('1'))
                self.ui.leYset.setText('%.4f' % self.hardware.scanner.read_angle_analog('2'))
            else:
                self.ui.leXSet.setText('%.3f' % self.hardware.mover.read_pos('1'))
                self.ui.leYset.setText('%.3f' % self.hardware.mover.read_pos('2'))

            self.ui.leZSet.setText('%.3f' % self.hardware.mover.read_pos('3'))
        except Exception as e:
            logger.logger.info(e)

    # Methods for Move Group
    def _move_position(self, direction):
        """
        Move selected piezo axis.

        Parameters
        ----------
        direction : int or float
            -1 means left/backward, +1 means right/forward.
        """

        try:
            move_step = float(self.ui.lemovestep.text())
        except ValueError:
            self.ui.statusbar.showMessage("Invalid move step!")
            return

        axis_configs = [
            (self.ui.checkBoxX, "1", self.ui.leXSet, "%.3f"),
            (self.ui.checkBoxY, "2", self.ui.leYset, "%.3f"),
            (self.ui.checkBoxZ, "3", self.ui.leZSet, "%.3f"),
        ]

        for checkbox, axis, lineedit, fmt in axis_configs:
            if checkbox.isChecked():
                try:
                    current_pos = float(lineedit.text())
                    target_pos = current_pos + direction * move_step

                    self.hardware.mover.move_pos(axis, target_pos)

                    real_pos = self.hardware.mover.read_pos(axis)
                    lineedit.setText(fmt % real_pos)

                except Exception as e:
                    self.ui.statusbar.showMessage(f"Move failed: {e}")

                return

        self.ui.statusbar.showMessage("No Direction to Move!")

    def move_position_left(self):
        """
        Piezo stage move at x/y/z direction left direction
        :return: None
        """
        self._move_position(direction=-1)

    def move_position_right(self):
        """
        Piezo stage move at x/y/z right direction
        :return: None
        """
        self._move_position(direction=1)

    def x_move_mode(self):
        """
        change move in x direction, false other checkbox
        Returns: None
        """
        enable_yz = not self.ui.checkBoxX.isChecked()

        self.ui.checkBoxY.setEnabled(enable_yz)
        self.ui.checkBoxZ.setEnabled(enable_yz)

    def y_move_mode(self):
        """
        Change move mode in Y direction.
        """
        enable_xz = not self.ui.checkBoxY.isChecked()

        self.ui.checkBoxX.setEnabled(enable_xz)
        self.ui.checkBoxZ.setEnabled(enable_xz)

    def z_move_mode(self):
        """
        Change move mode in Z direction.
        """
        z_checked = self.ui.checkBoxZ.isChecked()
        galvo_scan = self.is_galvo_scan()

        enable_xy = not z_checked and not galvo_scan

        self.ui.checkBoxX.setEnabled(enable_xy)
        self.ui.checkBoxY.setEnabled(enable_xy)

    @QtCore.pyqtSlot()
    def init_hardware(self):
        self.ui.statusbar.showMessage('Initializing...')
        self.set_hardware_ui_enabled(True)
        try:
            self.update_position()
            self.init_threads()

        except Exception as e:
            print(e)
            self.ui.statusbar.showMessage("Hardware Initialization Failed")
            return

        self.ui.statusbar.showMessage("Hardware Initialized Successfully")

    def init_threads(self):
        # Initialize Count Thread
        self.cThread = CountThread(self.hardware)
        self.cThread.counts.connect(self.update_counts)
        self.cThread.error.connect(self.ui.statusbar.showMessage)
        self.cThread.finished.connect(self.count_stopped)
        # Initialize Max Thread
        self.maxThread = MaxThread(self.hardware)
        self.maxThread.counts.connect(self.update_counts)
        self.maxThread.moved.connect(self.gone_to)
        self.maxThread.tracking_data.connect(self.update_tracking_result)
        self.maxThread.error.connect(self._on_max_error)
        self.maxThread.finished.connect(self.max_finished)

    def set_hardware_ui_enabled(self, enabled):
        """
        Enable/disable UI controls after hardware initialization.
        """
        self.hardware_initialized = enabled
        self.set_widgets_enabled(self.get_move_widgets(), enabled)

    @QtCore.pyqtSlot(str)
    def _on_max_error(self, msg):
        self._max_error_msg = msg
        self.ui.statusbar.showMessage(msg)

    # Count Group
    @QtCore.pyqtSlot()
    def count_start(self):
        # 避免重复 start
        if self.cThread.isRunning():
            return
        # 先读取并检查积分时间
        try:
            integral_time = int(self.ui.leIntegralTime.text())
            if integral_time <= 0:
                raise ValueError
        except ValueError:
            self.ui.statusbar.showMessage("Invalid integral time.")
            return

        # 设置积分时间
        # 如果你的 CountThread 里有 set_integral_time()，推荐这样写
        if hasattr(self.cThread, "set_integral_time"):
            self.cThread.set_integral_time(integral_time)
        else:
            self.cThread.integral_time = integral_time

        self.ui.statusbar.showMessage("Counting...")

        # change Button state
        self.ui.pbMax.setEnabled(False)
        self.ui.cBScanType.setEnabled(False)
        self.set_widgets_enabled(self.get_move_widgets(), False)
        self.ui.leIntegralTime.setEnabled(False)
        # change On button to off function
        self.ui.pbCountOn.setText('Count Off')
        self.ui.pbCountOn.clicked.disconnect()
        self.ui.pbCountOn.clicked.connect(self.count_stop)
        self.cThread.start()

    @QtCore.pyqtSlot()
    def count_stop(self):
        if self.cThread.isRunning():
            self.ui.statusbar.showMessage("Stopping counting...")

            # 防止用户重复点击
            self.ui.pbCountOn.setEnabled(False)

            # 新版本 CountThread 里使用 requestInterruption()
            self.cThread.stop()

    @QtCore.pyqtSlot(int)
    def update_counts(self, data):
        self.ui.lcdNumber.display(int(data))

    @QtCore.pyqtSlot()
    def count_stopped(self):
        """
        Called when CountThread is finished.
        """
        self.ui.statusbar.clearMessage()

        self.ui.pbMax.setEnabled(True)
        self.ui.pbCountOn.setEnabled(True)
        self.ui.leIntegralTime.setEnabled(True)
        self.ui.cBScanType.setEnabled(True)

        self.ui.pbCountOn.setText("Count On")

        try:
            self.ui.pbCountOn.clicked.disconnect()
        except TypeError:
            pass

        self.ui.pbCountOn.clicked.connect(self.count_start)
        self.set_widgets_enabled(self.get_move_widgets(), True)

    # Track Group
    @QtCore.pyqtSlot()
    def track_max_count(self):
        """
        Start max tracking.
        """

        if self.maxThread.isRunning():
            self.ui.statusbar.showMessage("Tracking is already running.")
            return True

        self._max_error_msg = ""
        self._max_has_result = False

        try:
            # scan mode
            if self.is_galvo_scan():
                scan_mode = 1
            else:
                # 默认 galvo
                scan_mode = 0

            # 积分时间
            # 如果希望 MaxThread 使用单独的积分时间控件，可以换成对应 lineEdit
            # integral_time = int(self.ui.leIntegralTime.text())
            integral_time = int(200) #200ms

            if integral_time <= 0:
                raise ValueError("Integral time must be greater than 0.")

            self.maxThread.set_parameters(
                integral_time=integral_time,
                scan_mode=scan_mode
            )

        except Exception as e:
            msg = f"Invalid tracking parameters: {e}"
            self.ui.statusbar.showMessage(msg)
            self.tracking_finished.emit(False, msg)
            return False

        self.ui.statusbar.showMessage("Tracking max count...")

        self.ui.pbMax.setEnabled(False)
        self.ui.pbCountOn.setEnabled(False)
        self.ui.leIntegralTime.setEnabled(False)
        self.ui.cBScanType.setEnabled(False)
        self.set_widgets_enabled(self.get_move_widgets(), False)

        self.maxThread.start()
        return True

    @QtCore.pyqtSlot(list, list, list, list)
    def update_tracking_result(self, pos_list, cts_list, pos_origin, pos_final):
        """
        Update tracking plots.

        Parameters
        ----------
        pos_list : list
            [x_pos_list, y_pos_list, z_pos_list]

        cts_list : list
            [x_cts_list, y_cts_list, z_cts_list]

        pos_origin : list
            [x_origin, y_origin, z_origin]

        pos_final : list
            [x_final, y_final, z_final]
        """
        self._max_has_result = True
        plot_configs = [
            {
                "canvas": self.track_x_fig,
                "ax": self.track_x_ax,
                "title": "X Axis",
                "index": 0,
            },
            {
                "canvas": self.track_y_fig,
                "ax": self.track_y_ax,
                "title": "Y Axis",
                "index": 1,
            },
            {
                "canvas": self.track_z_fig,
                "ax": self.track_z_ax,
                "title": "Z Axis",
                "index": 2,
            },
        ]

        for cfg in plot_configs:
            i = cfg["index"]

            self._update_single_tracking_plot(
                canvas=cfg["canvas"],
                ax=cfg["ax"],
                title=cfg["title"],
                pos=pos_list[i],
                cts=cts_list[i],
                origin=pos_origin[i],
                final=pos_final[i],
            )

    @staticmethod
    def _update_single_tracking_plot(
            canvas,
            ax,
            title,
            pos,
            cts,
            origin,
            final
    ):
        """
        Update one tracking plot.
        """
        if canvas is None or ax is None:
            return

        ax.clear()

        ax.set_title(title)

        if pos is None or cts is None or len(pos) == 0 or len(cts) == 0:
            ax.text(
                0.5,
                0.5,
                "No data",
                ha="center",
                va="center",
                transform=ax.transAxes
            )
            canvas.draw_idle()
            return

        ax.plot(pos, cts, "r.-", label="Counts")

        # 原始位置，红色虚线
        ax.axvline(
            origin,
            color="r",
            linestyle="--",
            linewidth=1.2,
            label="Origin"
        )

        # 最优位置，蓝色虚线
        ax.axvline(
            final,
            color="b",
            linestyle="--",
            linewidth=1.2,
            label="Final"
        )

        ax.set_xlabel("Position")
        ax.set_ylabel("Counts")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8)

        canvas.draw_idle()

    # Run when signal 'moved' emit
    @QtCore.pyqtSlot(float, float, float)
    def gone_to(self, x, y, z):
        if self.is_galvo_scan():
            self.ui.leXSet.setText('%.6f' % x)
            self.ui.leYset.setText('%.6f' % y)
        else:
            self.ui.leXSet.setText('%.3f' % x)
            self.ui.leYset.setText('%.3f' % y)

        self.ui.leZSet.setText('%.3f' % z)

    @QtCore.pyqtSlot()
    def max_finished(self):
        """
        Called when MaxThread finished.
        """
        self.ui.statusbar.clearMessage()

        self.ui.pbMax.setEnabled(True)
        self.ui.pbCountOn.setEnabled(True)
        self.ui.leIntegralTime.setEnabled(True)
        self.ui.cBScanType.setEnabled(True)
        self.set_widgets_enabled(self.get_move_widgets(), True)

        if self._max_error_msg:
            ok = False
            msg = self._max_error_msg
        elif not self._max_has_result:
            ok = False
            msg = "Tracking interrupted."
        else:
            ok = True
            msg = "Tracking finished."

        self.tracking_finished.emit(ok, msg)

    @QtCore.pyqtSlot()
    def stop_max_count(self):
        """
        Stop max tracking.
        """
        if self.maxThread.isRunning():
            self.ui.statusbar.showMessage("Stopping tracking...")
            self.maxThread.stop()

    def closeEvent(self, event):
        reply = QtWidgets.QMessageBox.question(
            self,
            "Message",
            "Save parameters as Defaults?",
            QtWidgets.QMessageBox.Save |
            QtWidgets.QMessageBox.Discard |
            QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel
        )

        if reply == QtWidgets.QMessageBox.Cancel:
            event.ignore()
            return

        if reply == QtWidgets.QMessageBox.Save:
            try:
                self.save_defaults()
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to save defaults:\n{e}"
                )
                event.ignore()
                return

        event.accept()

def load_config(config_path):
    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    return config


def save_config(config, config_path):
    with open(config_path, 'w') as config_file:
        yaml.dump(config, config_file, default_flow_style=False)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    myWindow = mainGUI()
    myWindow.show()
    sys.exit(app.exec_())