"""
Created on Feb 11, 2023

This File is the Main Thread for Confocal Scan

@author: Jiahua
"""
import sys
import os
import time
import yaml
import tempfile
import ast
from pathlib import Path
from ui.uipy.confocal_scan.confocal_scan import Ui_MainWindow
from PyQt5 import QtWidgets, QtCore

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib import colormaps
from matplotlib.widgets import Cursor
from src.threads.confocal_scan_threads import ConfocalScanThread, DataThread


class mainGUI(QtWidgets.QMainWindow):
    CACHE_LIFE = 7  # days

    def __init__(self, parent=None, hardware=None):
        QtWidgets.QWidget.__init__(self, parent)
        # Setup GUI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache\\confocal")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.scanning_cache = {
            "galva_mirror_plot": tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False),
            "galva_mirror_raw": tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False),
        }
        # Define some parameters need to be used in the program
        # self.APD_Counts = []
        # cursor
        self.cursor = None
        self.cur_vis = False
        self.ax = None
        self.cursor_click_cid = None
        self.mplMap = None
        self.mplToolbar = None
        self.curh = None
        self.curv = None
        self.image = None
        self.map = None
        self.mapColor = None
        self.cbar = None
        self.saved_data = None
        self.sThread = None
        self.dThread = None
        self.dataQThread = None
        self.hardware_initialized = False
        self.scanning = False
        self.config_confocal = None
        self.seq_dir = None
        self.pulse_seq = None
        self.pulse_name = None
        # Process for initialization
        # Hardware
        # Load defaults
        self.load_defaults()
        self.init_plot_area()
        self.hardware = hardware
        self.connect_methods()  # Connect methods to slots
        self.init_button_status()  # Init the state of buttons and textbox
        self.init_hardware()

    # Methods for initialization
    def connect_methods(self):
        """
        This method connects methods to the slots
        :return: None
        """
        # Menu Bar
        self.ui.actionSave_Defaults.triggered.connect(self.save_defaults)
        self.ui.actionLoad_Defaults.triggered.connect(self.load_defaults)

        # Image Group
        self.ui.pbResetPlot.clicked.connect(self.replot_image)
        self.ui.pbSavedata.clicked.connect(self.save_data)
        self.ui.vsMax.sliderMoved.connect(self.modify_image)
        self.ui.vsMin.sliderMoved.connect(self.modify_image)

        # Scan Group
        self.ui.pbStop.clicked.connect(self.stop_scan)
        self.ui.pbRun.clicked.connect(self.start_scan)

        # Position Control Group
        self.ui.pbNewCursor.clicked.connect(self.new_cursor)
        self.ui.pbShowCursor.clicked.connect(self.show_cursor)
        self.ui.pbHideCursor.clicked.connect(self.hide_cursor)
        self.ui.pbGoMid.clicked.connect(self.go_to_mid)
        self.ui.pbGo.clicked.connect(self.go_to)
        self.ui.pbGetPosition.clicked.connect(self.mark_current_position)

        # Scan Parameters Group
        self.ui.pbFullRange.clicked.connect(self.set_full_range)
        self.ui.pbCenterRange.clicked.connect(self.set_center_range)
        self.ui.cBresolution.currentTextChanged.connect(self.resolution_changed)

        # Time Parameters Group
        self.ui.pbLoadSeq.clicked.connect(self.open_pulse_seq)

        # Scan Configration
        self.ui.cBScanType.currentTextChanged.connect(self.scan_type_changed)
        self.ui.cBXZScanType.currentTextChanged.connect(self.xz_scan_type_changed)
        self.ui.cBTimeScanType.currentTextChanged.connect(self.time_scan_type_changed)

    def get_image_widgets(self):
        return [
            self.ui.pbResetPlot,
            self.ui.pbSavedata,
            self.ui.vsMax,
            self.ui.vsMin,
        ]

    def get_scan_widgets(self):
        return [
            self.ui.pbRun,
            self.ui.leScanDwellTime,
            self.ui.cBresolution,
        ]

    def get_scan_mode_widgets(self):
        return [
            self.ui.cBScanType,
            self.ui.cBXZScanType,
            self.ui.cBTimeScanType,
        ]

    def get_scan_parameter_common_widgets(self):
        return [
            self.ui.pbFullRange,
            self.ui.pbCenterRange,
            self.ui.lexscanstart,
            self.ui.lexscanend,
            self.ui.lexscanstep,
            self.ui.lerange,
        ]

    def get_y_scan_widgets(self):
        return [
            self.ui.leyscanstart,
            self.ui.leyscanend,
            self.ui.leyscanstep,
        ]

    def get_z_scan_widgets(self):
        return [
            self.ui.lezscanstart,
            self.ui.lezscanend,
            self.ui.lezscanstep,
        ]

    def get_position_widgets(self):
        return [
            self.ui.pbNewCursor,
            self.ui.pbShowCursor,
            self.ui.pbGoMid,
            self.ui.pbGo,
            self.ui.pbGetPosition,
            self.ui.leXCursorSet,
            self.ui.leYCursorSet,
            self.ui.leZCursorSet,
        ]

    def get_time_scan_widgets(self):
        return [
            self.ui.pbLoadSeq,
            self.ui.leTimeBInNumber,
            self.ui.leTimeBInWidth,
            self.ui.leFrameNum,
        ]

    def init_button_status(self):
        """
        This method set the state of buttons and textbox to initial state.
        :return: None
        """
        self.hardware_initialized = False
        self.scanning = False

        # Image Group
        self.set_widgets_enabled(self.get_image_widgets(), False)

        # Scan Group
        self.ui.pbStop.setEnabled(False)
        self.set_widgets_enabled(self.get_scan_widgets(), False)

        # Position Control Group
        self.ui.pbHideCursor.setEnabled(False)
        self.set_widgets_enabled(self.get_position_widgets(), False)

        # Scan Parameters Group
        self.set_widgets_enabled(self.get_scan_parameter_common_widgets(), False)
        self.set_widgets_enabled(self.get_y_scan_widgets(), False)
        self.set_widgets_enabled(self.get_z_scan_widgets(), False)

        # Time Parameters Group
        self.set_widgets_enabled(self.get_time_scan_widgets(), False)
        self.ui.leSeq.setEnabled(False)
        self.ui.ScanTimeParameters.hide()

    def init_plot_area(self):
        """
        Init image canvas, toolbar and cursor lines.
        """
        self.init_image_plot()
        self.init_toolbar_set()
        self.init_cursor_line()

    def init_image_plot(self):
        """
        Init the plot for image.
        """

        # 1. 确保 widgetImage 有 layout
        if self.ui.widgetImage.layout() is None:
            layout = QtWidgets.QVBoxLayout(self.ui.widgetImage)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        else:
            layout = self.ui.widgetImage.layout()

        # 2. 如果之前已经有 mplMap，先移除
        if hasattr(self, "mplMap") and self.mplMap is not None:
            layout.removeWidget(self.mplMap)
            self.mplMap.setParent(None)
            self.mplMap.deleteLater()
            self.mplMap = None

        # 3. 创建 Figure 和 Canvas
        fig = Figure(constrained_layout=True)

        self.mplMap = FigureCanvas(fig)
        layout.addWidget(self.mplMap)

        # 4. 创建 axes
        self.ax = fig.add_subplot(111)

        # 如果你后续代码还想用 self.mplMap.axes，也可以保留这句
        self.mplMap.axes = self.ax

        # 5. 读取 UI 参数
        x_start = float(self.ui.lexscanstart.text())
        x_end = float(self.ui.lexscanend.text())
        y_start = float(self.ui.leyscanstart.text())
        y_end = float(self.ui.leyscanend.text())
        y_step = float(self.ui.leyscanstep.text())

        xnum = int(self.ui.cBresolution.currentText())

        if y_step == 0:
            raise ValueError("Y scan step cannot be zero.")

        y_num = int(abs((y_end - y_start) / y_step))
        y_num = max(1, y_num)

        # 6. 初始化图像数据
        self.map = np.random.randint(0, 100, size=(y_num, xnum))

        self.mapColor = "gist_earth"

        # 7. 显示图像
        self.image = self.ax.imshow(
            self.map,
            cmap=colormaps.get_cmap(self.mapColor),
            vmin=0,
            vmax=self.map.max(),
            extent=(x_start, x_end, y_start, y_end),
            interpolation="nearest",
            origin="lower",
            aspect="equal",
            # 如果想让图像填满显示区域，用 aspect="auto"
        )

        self.ax.set_xlim(x_start, x_end)
        self.ax.set_ylim(y_start, y_end)

        # 8. Colorbar
        self.cbar = fig.colorbar(
            self.image,
            ax=self.ax,
            fraction=0.045,
            pad=0.04
        )

        self.mplMap.draw_idle()

    def init_toolbar_set(self):
        """
        Init the toolbar for image.
        """

        # 1. confirm whether widgetToolbar has layout
        if self.ui.widgetToolbar.layout() is None:
            layout = QtWidgets.QVBoxLayout(self.ui.widgetToolbar)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        else:
            layout = self.ui.widgetToolbar.layout()

        # 2. if there is a toolbar，remove firstly
        if hasattr(self, "mplToolbar") and self.mplToolbar is not None:
            layout.removeWidget(self.mplToolbar)
            self.mplToolbar.setParent(None)
            self.mplToolbar.deleteLater()
            self.mplToolbar = None

        # 3. confirm mplMap
        if not hasattr(self, "mplMap") or self.mplMap is None:
            raise RuntimeError("mplMap does not exist. Call init_image_plot() first.")

        # 4. create toolbar
        self.mplToolbar = NavigationToolbar(
            self.mplMap,
            self.ui.widgetToolbar
        )

        layout.addWidget(self.mplToolbar)

    def init_cursor_line(self):
        """
        Initialize cursor lines.
        """

        # 确保 self.ax 已经存在
        if not hasattr(self, "ax") or self.ax is None:
            raise RuntimeError("ax does not exist. Call init_image_plot() first.")

        self.cursor = None
        self.cur_vis = False
        self.cursor_click_cid = None

        x_cursor = float(self.ui.leXCursorSet.text())
        if self.ui.cBXZScanType.currentText() == "None":
            y_cursor = float(self.ui.leYCursorSet.text())
        else:
            y_cursor = float(self.ui.leZCursorSet.text())

        self.curh = self.ax.axhline(
            y=y_cursor,
            color="red",
            linewidth=1,
            visible=False
        )

        self.curv = self.ax.axvline(
            x=x_cursor,
            color="red",
            linewidth=1,
            visible=False
        )
        self.ui.pbShowCursor.setEnabled(True)
        self.ui.pbHideCursor.setEnabled(False)
        self.mplMap.draw_idle()

    # Load and Save defaults
    @QtCore.pyqtSlot()
    def open_defaults(self):
        directory = os.path.dirname(os.path.abspath(__file__))
        location, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose Defaults File', directory)
        if location != '':
            self.load_defaults(location)

    def load_defaults(self, config_path='config/config_confocal_GM.yaml'):
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        self.config_confocal = load_config(config_path=config_file)
        self.update_ui_based_on_default()

    @QtCore.pyqtSlot()
    def save_defaults(self, config_path='config/config_confocal_GM.yaml'):
        self.update_default_based_on_ui()
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        save_config(config=self.config_confocal, config_path=config_file)

    def get_scan_key(self, scan_type=None):
        if scan_type is None:
            scan_type = self.ui.cBScanType.currentText()
        scan_key_map = {
            "Galvo Mirror": "galvo_mirror_scan",
            "Piezo Stage": "piezo_scan",
        }
        if scan_type not in scan_key_map:
            raise ValueError(f"Unknown scan type: {scan_type}")
        return scan_key_map[scan_type]

    def update_ui_based_on_default(self, scan_type=None):
        scan_key = self.get_scan_key(scan_type)
        scan_cfg = self.config_confocal[scan_key]
        # X/Y parameters connect to scan type
        self.load_xy_scan_config_to_ui(scan_cfg)
        # X/Y cursors connect to scan type
        self.load_xy_cursor_to_ui(scan_cfg)
        # range connects to scan type
        self.set_lineedit_value(
            self.ui.lerange,
            scan_cfg.get("range", "")
        )
        # Z parameters always come from piezo_scan
        self.load_z_config_to_ui()
        # time parameters have no connect to scan type
        self.load_time_config_to_ui()

    def load_xy_scan_config_to_ui(self, scan_cfg):
        widgets = {
            "x": {
                "start": self.ui.lexscanstart,
                "end": self.ui.lexscanend,
                "step": self.ui.lexscanstep,
            },
            "y": {
                "start": self.ui.leyscanstart,
                "end": self.ui.leyscanend,
                "step": self.ui.leyscanstep,
            },
        }
        for axis, params in widgets.items():
            axis_cfg = scan_cfg.get(axis, {})
            for name, widget in params.items():
                self.set_lineedit_value(widget, axis_cfg.get(name, ""))

    def load_xy_cursor_to_ui(self, scan_cfg):
        cursor_cfg = scan_cfg.get("cursor", {})
        cursor_widgets = {
            "x": self.ui.leXCursorSet,
            "y": self.ui.leYCursorSet,
        }
        for axis, widget in cursor_widgets.items():
            self.set_lineedit_value(widget,cursor_cfg.get(axis, ""))

    def load_z_config_to_ui(self):
        piezo_cfg = self.config_confocal["piezo_scan"]
        z_cfg = piezo_cfg.get("z", {})
        cursor_cfg = piezo_cfg.get("cursor", {})
        self.set_lineedit_value(self.ui.lezscanstart, z_cfg.get("start", ""))
        self.set_lineedit_value(self.ui.lezscanend, z_cfg.get("end", ""))
        self.set_lineedit_value(self.ui.lezscanstep, z_cfg.get("step", ""))
        self.set_lineedit_value(self.ui.leZCursorSet, cursor_cfg.get("z", ""))

    def load_time_config_to_ui(self):
        time_cfg = self.config_confocal.get("time_parameter", {})
        self.set_lineedit_value(self.ui.leScanDwellTime, time_cfg.get("dwell_time", ""))
        self.set_lineedit_value(self.ui.leTimeBInWidth, time_cfg.get("bin_width_ps", ""))
        self.set_lineedit_value(self.ui.leTimeBInNumber, time_cfg.get("bin_number", ""))
        self.set_lineedit_value(self.ui.leFrameNum, time_cfg.get("frame_number", ""))

    def update_default_based_on_ui(self, scan_type=None):
        scan_key = self.get_scan_key(scan_type)
        scan_cfg = self.config_confocal[scan_key]
        # Save X/Y parameters to the config from current scan type
        self.save_xy_scan_ui_to_config(scan_cfg)
        # Save X/Y cursor to the config from current scan type
        self.save_xy_cursor_ui_to_config(scan_cfg)
        # Save range to the config from current scan type
        scan_cfg["range"] = self.get_float_from_lineedit(self.ui.lerange)
        # Save z parameter to piezo_scan
        self.save_z_ui_to_config()
        # save time parameters
        self.save_time_ui_to_config()

    def save_xy_scan_ui_to_config(self, scan_cfg):
        widgets = {
            "x": {
                "start": self.ui.lexscanstart,
                "end": self.ui.lexscanend,
                "step": self.ui.lexscanstep,
            },
            "y": {
                "start": self.ui.leyscanstart,
                "end": self.ui.leyscanend,
                "step": self.ui.leyscanstep,
            },
        }
        for axis, params in widgets.items():
            if axis not in scan_cfg:
                scan_cfg[axis] = {}
            for name, widget in params.items():
                scan_cfg[axis][name] = self.get_float_from_lineedit(widget)

    def save_xy_cursor_ui_to_config(self, scan_cfg):
        if "cursor" not in scan_cfg:
            scan_cfg["cursor"] = {}
        cursor_widgets = {
            "x": self.ui.leXCursorSet,
            "y": self.ui.leYCursorSet,
        }
        for axis, widget in cursor_widgets.items():
            scan_cfg["cursor"][axis] = self.get_float_from_lineedit(widget)

    def save_z_ui_to_config(self):
        piezo_cfg = self.config_confocal["piezo_scan"]
        if "z" not in piezo_cfg:
            piezo_cfg["z"] = {}
        if "cursor" not in piezo_cfg:
            piezo_cfg["cursor"] = {}
        piezo_cfg["z"]["start"] = self.get_float_from_lineedit(self.ui.lezscanstart)
        piezo_cfg["z"]["end"] = self.get_float_from_lineedit(self.ui.lezscanend)
        piezo_cfg["z"]["step"] = self.get_float_from_lineedit(self.ui.lezscanstep)
        piezo_cfg["cursor"]["z"] = self.get_float_from_lineedit(self.ui.leZCursorSet)

    def save_time_ui_to_config(self):
        time_cfg = self.config_confocal["time_parameter"]
        time_cfg["dwell_time"] = self.get_int_from_lineedit(self.ui.leScanDwellTime)
        time_cfg["frame_number"] = self.get_int_from_lineedit(self.ui.leFrameNum)
        time_cfg["bin_width_ps"] = self.get_int_from_lineedit(self.ui.leTimeBInWidth)
        time_cfg["bin_number"] = self.get_int_from_lineedit(self.ui.leTimeBInNumber)

    @staticmethod
    def set_lineedit_value(lineedit, value):
        lineedit.setText("" if value is None else str(value))

    @staticmethod
    def get_float_from_lineedit(lineedit, default=0.0):
        text = lineedit.text().strip()
        if text == "":
            return default
        return float(text)

    @staticmethod
    def get_int_from_lineedit(lineedit, default=0):
        text = lineedit.text().strip()
        if text == "":
            return default
        return int(float(text))

    # Methods for Hardware Group
    @QtCore.pyqtSlot()
    def init_hardware(self):
        """
        Init all hardware and pass them to Threads.
        """
        self.ui.statusbar.showMessage("Initializing Hardware...")
        self.set_hardware_ui_enabled(True)
        try:
            self.init_hardware_position()
            self.init_threads()

        except Exception as e:
            print(e)
            self.ui.statusbar.showMessage("Hardware Initialization Failed")
            return

        self.ui.statusbar.showMessage("Hardware Initialized Successfully")

    def init_hardware_position(self):
        """
        Initialize hardware position according to current scan type.
        """

        if self.is_galvo_scan():
            self.hardware.scanner.single_angle_mode_analog("1")
            self.hardware.scanner.single_angle_mode_analog("2")

        self.go_to()

    def init_threads(self):
        """
        Initialize scan thread and data thread.
        """
        self.sThread = ConfocalScanThread(self.hardware)

        self.dataQThread = QtCore.QThread(self)
        self.dThread = DataThread()
        self.dThread.moveToThread(self.dataQThread)
        self.dataQThread.finished.connect(self.dThread.deleteLater)
        self.dataQThread.start()

        self.sThread.data_update.connect(self.dThread.process_scan_packet)
        self.sThread.time_data_ready.connect(self.dThread.process_scan_packet)

        self.dThread.image_update.connect(self.update_image)
        self.dThread.error_occurred.connect(self.ui.statusbar.showMessage)

        self.sThread.status_update.connect(self.ui.statusbar.showMessage)
        self.sThread.error_occurred.connect(self.ui.statusbar.showMessage)

        self.sThread.finished.connect(self.scan_stopped)

    def set_hardware_ui_enabled(self, enabled):
        """
        Enable/disable UI controls after hardware initialization.
        """
        self.hardware_initialized = enabled

        self.set_widgets_enabled(self.get_image_widgets(), enabled)
        self.set_widgets_enabled(self.get_scan_widgets(), enabled)
        self.set_widgets_enabled(self.get_position_widgets(), enabled)
        self.set_widgets_enabled(self.get_scan_parameter_common_widgets(), enabled)

        # Stop button should only be enabled during scan
        self.ui.pbStop.setEnabled(False)

        # Hide cursor button initial state
        self.ui.pbHideCursor.setEnabled(False)

        # Restore Y/Z scan widgets according to current XY/XZ mode
        self.update_yz_scan_widgets_enabled(enabled)

        # Restore time parameter widgets according to current time scan mode
        self.update_time_scan_widgets_enabled(enabled)

    def update_yz_scan_widgets_enabled(self, enabled):
        """
        Enable Y or Z scan widgets according to XY/XZ scan mode.
        """

        if not enabled:
            self.set_widgets_enabled(self.get_y_scan_widgets(), False)
            self.set_widgets_enabled(self.get_z_scan_widgets(), False)
            return

        if self.is_xy_scan():
            self.set_widgets_enabled(self.get_y_scan_widgets(), True)
            self.set_widgets_enabled(self.get_z_scan_widgets(), False)
        else:
            self.set_widgets_enabled(self.get_y_scan_widgets(), False)
            self.set_widgets_enabled(self.get_z_scan_widgets(), True)

    def update_time_scan_widgets_enabled(self, enabled):
        """
        Enable/disable time scan parameter widgets.
        """

        is_time = self.is_time_scan()

        self.ui.ScanTimeParameters.setVisible(is_time)

        self.set_widgets_enabled(
            self.get_time_scan_widgets(),
            enabled and is_time
        )

    # Position Control Group
    @QtCore.pyqtSlot()
    def new_cursor(self):
        """
        Enable cursor selection on image.
        User clicks on image, then cursor position is updated.
        """
        self.hide_cursor()
        try:
            self.cursor = Cursor(self.ax, useblit=True, color='red', linewidth=1)
        except BaseException as e:
            print(e)
            return
        self.cursor_click_cid = self.mplMap.mpl_connect(
            "button_press_event",
            self.new_cursor_marked
        )
        self.mplMap.draw_idle()

    def new_cursor_marked(self, event):
        """
        Called when user clicks on matplotlib image.
        """

        # 只响应主图像 axes，不响应 colorbar 或空白区域
        if event.inaxes is not self.ax:
            return

        if event.xdata is None or event.ydata is None:
            return

        x = round(event.xdata, 4)
        y = round(event.ydata, 4)

        self.ui.leXCursorSet.setText(str(x))

        # 普通 XY scan：ydata 对应 Y
        # XZ scan：ydata 对应 Z
        if self.ui.cBXZScanType.currentText() == "None":
            self.ui.leYCursorSet.setText(str(y))
        else:
            self.ui.leZCursorSet.setText(str(y))

        # 断开鼠标点击事件
        if hasattr(self, "cursor_click_cid") and self.cursor_click_cid is not None:
            self.mplMap.mpl_disconnect(self.cursor_click_cid)
            self.cursor_click_cid = None

        # 关闭临时 Cursor
        if self.cursor is not None:
            self.cursor.disconnect_events()
            self.cursor = None

        # 更新 cursor line
        self.curh.set_ydata((y, y))
        self.curv.set_xdata((x, x))

        self.show_cursor()

    @QtCore.pyqtSlot()
    def show_cursor(self):
        """
        Show cursor lines according to current LineEdit values.
        """

        # 如果正在使用临时 cursor，先关闭
        if self.cursor is not None:
            self.cursor.disconnect_events()
            self.cursor = None

        # 如果还有鼠标点击事件，也断开
        if hasattr(self, "cursor_click_cid") and self.cursor_click_cid is not None:
            self.mplMap.mpl_disconnect(self.cursor_click_cid)
            self.cursor_click_cid = None

        try:
            x = float(self.ui.leXCursorSet.text())

            if self.ui.cBXZScanType.currentText() == "None":
                y = float(self.ui.leYCursorSet.text())
            else:
                y = float(self.ui.leZCursorSet.text())

        except ValueError:
            print("Invalid cursor value.")
            return

        self.curh.set_visible(True)
        self.curv.set_visible(True)

        self.curh.set_ydata((y, y))
        self.curv.set_xdata((x, x))

        self.mplMap.draw_idle()

        self.ui.pbShowCursor.setEnabled(False)
        self.ui.pbHideCursor.setEnabled(True)

    @QtCore.pyqtSlot()
    def hide_cursor(self):
        """
        Hide cursor lines.
        """
        self.cur_vis = False

        if hasattr(self, "curh") and self.curh is not None:
            self.curh.set_visible(False)

        if hasattr(self, "curv") and self.curv is not None:
            self.curv.set_visible(False)

        # 如果正在使用临时 cursor，先关闭
        if hasattr(self, "cursor") and self.cursor is not None:
            self.cursor.disconnect_events()
            self.cursor = None

        # 如果有点击事件，也断开
        if hasattr(self, "cursor_click_cid") and self.cursor_click_cid is not None:
            self.mplMap.mpl_disconnect(self.cursor_click_cid)
            self.cursor_click_cid = None

        if hasattr(self, "mplMap") and self.mplMap is not None:
            self.mplMap.draw_idle()

        self.ui.pbShowCursor.setEnabled(True)
        self.ui.pbHideCursor.setEnabled(False)

    @QtCore.pyqtSlot()
    def go_to_mid(self):
        x_mid, y_mid, z_mid = self.get_mid_position()

        self.ui.leXCursorSet.setText(f"{x_mid:.1f}")
        self.ui.leYCursorSet.setText(f"{y_mid:.1f}")
        self.ui.leZCursorSet.setText(f"{z_mid:.1f}")

        self.go_to()

    @QtCore.pyqtSlot()
    def go_to(self):
        x = float(self.ui.leXCursorSet.text())
        y = float(self.ui.leYCursorSet.text())
        z = float(self.ui.leZCursorSet.text())

        self.move_piezo_axis("3", z, self.ui.leZSet)

        if self.is_galvo_scan():
            self.move_galvo_axis("1", x, self.ui.leXSet)
            self.move_galvo_axis("2", y, self.ui.leYset)
        else:
            self.move_piezo_axis("1", x, self.ui.leXSet)
            self.move_piezo_axis("2", y, self.ui.leYset)

    def get_mid_position(self):
        if self.is_galvo_scan():
            return 0.0, 0.0, 50.0

        return 50.0, 50.0, 50.0

    def is_galvo_scan(self):
        return self.ui.cBScanType.currentText() == "Galvo Mirror"

    def move_piezo_axis(self, channel, value, display_lineedit):
        self.hardware.mover.move_pos(channel, value)
        actual = self.hardware.mover.read_pos(channel)
        display_lineedit.setText(f"{actual:.3f}")

    def move_galvo_axis(self, channel, value, display_lineedit):
        self.hardware.scanner.mov_angle_analog(channel, value)
        actual = self.hardware.scanner.read_angle_analog(channel)
        display_lineedit.setText(f"{actual:.6f}")

    def mark_current_position(self):
        """
        let cursor position data be actual position
        """
        if self.is_galvo_scan():
            self.ui.leXSet.setText('%.6f' % self.hardware.scanner.read_angle_analog('1'))
            self.ui.leYset.setText('%.6f' % self.hardware.scanner.read_angle_analog('2'))
        else:
            self.ui.leXSet.setText('%.3f' % self.hardware.mover.read_pos('1'))
            self.ui.leYset.setText('%.3f' % self.hardware.mover.read_pos('2'))

        self.ui.leZSet.setText('%.3f' % self.hardware.mover.read_pos('3'))

        self.ui.leXCursorSet.setText(self.ui.leXSet.text())
        self.ui.leYCursorSet.setText(self.ui.leYset.text())
        self.ui.leZCursorSet.setText(self.ui.leZSet.text())

    # Scan Parameters Group
    def get_axis_decimals(self, axis):
        """
        Galvo Mirror X/Y: 4 decimals
        Piezo Stage X/Y: 3 decimals
        Z: always 3 decimals
        """
        axis = axis.lower()

        if axis == "z":
            return 3

        if axis in ("x", "y"):
            return 6 if self.is_galvo_scan() else 3

        raise ValueError(f"Unknown axis: {axis}")

    def set_scan_axis_range(self, axis, start, end, resolution, decimals=None):
        """
        Set start/end/step LineEdits for one scan axis.
        """

        if resolution <= 0:
            raise ValueError("Resolution must be positive.")

        axis = axis.lower()

        widgets = {
            "x": {
                "start": self.ui.lexscanstart,
                "end": self.ui.lexscanend,
                "step": self.ui.lexscanstep,
            },
            "y": {
                "start": self.ui.leyscanstart,
                "end": self.ui.leyscanend,
                "step": self.ui.leyscanstep,
            },
            "z": {
                "start": self.ui.lezscanstart,
                "end": self.ui.lezscanend,
                "step": self.ui.lezscanstep,
            },
        }

        if axis not in widgets:
            raise ValueError(f"Unknown axis: {axis}")

        if decimals is None:
            decimals = self.get_axis_decimals(axis)

        step = (end - start) / resolution

        widgets[axis]["start"].setText(self.format_number(start, decimals))
        widgets[axis]["end"].setText(self.format_number(end, decimals))
        widgets[axis]["step"].setText(self.format_number(step, decimals))

    def set_full_range(self):
        """
        Set full scan range.
        """
        resolution = int(self.ui.cBresolution.currentText())

        if resolution <= 0:
            raise ValueError("Resolution must be positive.")

        if self.is_galvo_scan():
            xy_start, xy_end = -2.5, 2.5
        else:
            xy_start, xy_end = 0.0, 100.0

        z_start, z_end = 0.0, 100.0

        self.set_scan_axis_range("x", xy_start, xy_end, resolution)
        self.set_scan_axis_range("y", xy_start, xy_end, resolution)
        self.set_scan_axis_range("z", z_start, z_end, resolution)

    def set_center_range(self):
        """
        Set scan range centered at current cursor position.
        """
        resolution = int(self.ui.cBresolution.currentText())

        if resolution <= 0:
            raise ValueError("Resolution must be positive.")

        scan_range = float(self.ui.lerange.text())
        half_range = scan_range / 2

        x_center = float(self.ui.leXCursorSet.text())

        self.set_scan_axis_range(
            "x",
            x_center - half_range,
            x_center + half_range,
            resolution
        )

        if self.is_xy_scan():
            y_center = float(self.ui.leYCursorSet.text())

            self.set_scan_axis_range(
                "y",
                y_center - half_range,
                y_center + half_range,
                resolution
            )
        else:
            z_center = float(self.ui.leZCursorSet.text())

            self.set_scan_axis_range(
                "z",
                z_center - half_range,
                z_center + half_range,
                resolution
            )

        self.replot_image()

    def xz_scan_type_changed(self, text):
        editable = self.hardware_initialized and not self.scanning
        self.update_yz_scan_widgets_enabled(editable)

        try:
            self.update_scan_steps_by_current_mode()
        except Exception as e:
            print(f"Update scan steps failed: {e}")

        # 如果 plot 已经初始化，则更新图像
        if hasattr(self, "mplMap") and self.mplMap is not None:
            try:
                self.reset_map_by_current_resolution()
                self.replot_image()
            except Exception as e:
                print(f"Replot after XZ scan type changed failed: {e}")

    def time_scan_type_changed(self, text):
        """
        Show or hide time scan parameters.
        """
        editable = self.hardware_initialized and not self.scanning
        self.update_time_scan_widgets_enabled(editable)

    def is_xy_scan(self):
        return self.ui.cBXZScanType.currentText() == "None"

    @staticmethod
    def set_widgets_enabled(widgets, enabled):
        for widget in widgets:
            widget.setEnabled(enabled)

    @staticmethod
    def format_number(value, decimals=3):
        return f"{value:.{decimals}f}"

    @QtCore.pyqtSlot(str)
    def resolution_changed(self, _):
        self.update_scan_steps_by_current_mode()
        self.reset_map_by_current_resolution()
        self.replot_image()

    def reset_map_by_current_resolution(self):
        """
        Reset image map according to current resolution.
        """

        resolution = int(self.ui.cBresolution.currentText())

        if resolution <= 0:
            raise ValueError("Resolution must be positive.")

        x_num = resolution
        y_num = resolution

        self.map = np.random.randint(0, 100, size=(y_num, x_num))

    def update_scan_steps_by_current_mode(self):
        try:
            resolution = int(self.ui.cBresolution.currentText())

            if resolution <= 0:
                raise ValueError("Resolution must be positive.")

            self.update_axis_step_from_ui("x", resolution)

            if self.is_xy_scan():
                self.update_axis_step_from_ui("y", resolution)
            else:
                self.update_axis_step_from_ui("z", resolution)

        except Exception as e:
            print(f"Update scan steps failed: {e}")
            self.ui.statusbar.showMessage("Failed to update scan step")

    def update_axis_step_from_ui(self, axis, resolution):
        """
        Update one axis step according to current start/end LineEdit values.
        """
        axis = axis.lower()
        widgets = {
            "x": {
                "start": self.ui.lexscanstart,
                "end": self.ui.lexscanend,
                "step": self.ui.lexscanstep,
            },
            "y": {
                "start": self.ui.leyscanstart,
                "end": self.ui.leyscanend,
                "step": self.ui.leyscanstep,
            },
            "z": {
                "start": self.ui.lezscanstart,
                "end": self.ui.lezscanend,
                "step": self.ui.lezscanstep,
            },
        }

        if axis not in widgets:
            raise ValueError(f"Unknown axis: {axis}")

        start = float(widgets[axis]["start"].text())
        end = float(widgets[axis]["end"].text())

        step = (end - start) / resolution

        decimals = self.get_axis_decimals(axis)

        widgets[axis]["step"].setText(
            self.format_number(step, decimals)
        )


    def scan_type_changed(self, text):
        is_galvo = text == "Galvo Mirror"
        unit = "V" if is_galvo else "µm"
        coordinate_mode = "Native V" if is_galvo else "Physical µm"

        self.set_xy_unit_labels(unit)
        self.set_coordinate_mode(coordinate_mode)
        # UI text changed as text
        self.update_ui_based_on_default(text)
        # Update image
        self.init_plot_area()

    def set_xy_unit_labels(self, unit):
        labels = [
            self.ui.label_x_unit,
            self.ui.label_y_unit,
            self.ui.label_range_unit,
            self.ui.label_cursor_x_unit,
            self.ui.label_cursor_y_unit,
            self.ui.label_actual_x_unit,
            self.ui.label_actual_y_unit,
        ]

        for label in labels:
            label.setText(unit)

    def set_coordinate_mode(self, mode_text):
        index = self.ui.cBcoordinateMode.findText(mode_text)
        if index >= 0:
            self.ui.cBcoordinateMode.setCurrentIndex(index)

    def ensure_map_matches_resolution(self):
        """
        Make sure map shape matches current resolution.
        """
        resolution = int(self.ui.cBresolution.currentText())

        expected_shape = (resolution, resolution)

        if not hasattr(self, "map") or self.map is None:
            self.map = self.map = np.random.randint(0, 100, size=expected_shape)
            return

        if self.map.shape != expected_shape:
            self.map = self.map = np.random.randint(0, 100, size=expected_shape)

    # Methods for Image Group
    @QtCore.pyqtSlot()
    def replot_image(self):
        """
        Replot image according to current scan parameters.
        """
        if not hasattr(self, "mplMap") or self.mplMap is None:
            self.init_plot_area()
            return

        self.ensure_map_matches_resolution()

        fig = self.mplMap.figure

        # 清空 figure，包括旧 image、旧 colorbar、旧 cursor line
        fig.clear()

        # 重新创建 axes
        self.ax = fig.add_subplot(111)
        self.mplMap.axes = self.ax

        # 读取 X range
        x_start = float(self.ui.lexscanstart.text())
        x_end = float(self.ui.lexscanend.text())

        if self.is_xy_scan():
            y_start = float(self.ui.leyscanstart.text())
            y_end = float(self.ui.leyscanend.text())
            aspect = "equal"
        else:
            y_start = float(self.ui.lezscanstart.text())
            y_end = float(self.ui.lezscanend.text())
            aspect = "auto"

        v_max = float(np.max(self.map))

        # 防止 v_max == 0 时 color scale 异常
        if v_max <= 0:
            v_max = 1.0

        self.image = self.ax.imshow(
            self.map,
            cmap=colormaps.get_cmap(self.mapColor),
            vmin=0,
            vmax=v_max,
            extent=(x_start, x_end, y_start, y_end),
            interpolation="nearest",
            origin="lower",
            aspect=aspect,
        )

        self.ax.set_xlim(x_start, x_end)
        self.ax.set_ylim(y_start, y_end)

        self.cbar = fig.colorbar(
            self.image,
            ax=self.ax,
            fraction=0.045,
            pad=0.05
        )
        self.init_cursor_line()
        self.update_image_clim(redraw=False)
        self.mplMap.draw_idle()

    def is_time_scan(self):
        return self.ui.cBTimeScanType.currentText() != "None"

    def save_data(self):
        """
        Save intensity data and optional time-resolved data.
        """
        # 1. Get raw data safely
        if not hasattr(self, "dThread") or self.dThread is None:
            sys.stderr.write("DataThread does not exist!\n")
            return

        intensity_data = getattr(self.dThread, "raw_intensity", None)
        time_data = getattr(self.dThread, "raw_time_frames", None)

        x_arr = getattr(self.dThread, "xArr", None)
        y_arr = getattr(self.dThread, "yArr", None)

        bin_num = int(self.ui.leTimeBInNumber.text())
        bin_width = int(self.ui.leTimeBInWidth.text())
        frame_num = int(self.ui.leFrameNum.text())

        frame_indices = getattr(self.dThread, "raw_time_frame_indices", None)

        time_scan = self.is_time_scan()

        if intensity_data is None and not time_scan:
            sys.stderr.write("No intensity data to be saved!\n")
            return

        if time_scan and intensity_data is None and time_data is None:
            sys.stderr.write("No intensity/time data to be saved!\n")
            return

        # 2. Ask user for base file name
        default_dir = r"C:\zjh\experiment data"

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Enter save file",
            default_dir,
            "Text (*.txt)"
        )

        if file_path == "":
            sys.stderr.write("No file is saved!\n")
            return

        file_path = self.ensure_txt_suffix(file_path)

        # 3. Save data
        try:
            if time_scan:
                root, ext = os.path.splitext(file_path)

                if intensity_data is not None:
                    self.save_intensity_data_to_file(
                        root + "_intensity" + ext,
                        intensity_data
                    )

                if time_data is not None:
                    self.save_time_data_to_file(
                        root + "_time" + ext,
                        time_data,
                        x_arr,
                        y_arr,
                        bin_num,
                        bin_width,
                        frame_indices
                    )

            else:
                self.save_intensity_data_to_file(
                    file_path,
                    intensity_data
                )

        except Exception as e:
            sys.stderr.write(f"Save data failed: {e}\n")
            self.ui.statusbar.showMessage("Save data failed")
            return

        self.ui.statusbar.showMessage("Data saved successfully")

    def save_intensity_data_to_file(self, file_path, data):
        """
        Save intensity raw data.
        Expected shape: Nx3
        Columns: x, y/z, counts
        """
        raw = self.validate_raw_data(
            data=data,
            expected_cols=3,
            data_name="intensity data"
        )

        second_axis_name = "y" if self.is_xy_scan() else "z"

        header = f"x\t{second_axis_name}\tcounts"

        coord_fmt = "%.6f" if self.is_galvo_scan() else "%.3f"

        np.savetxt(
            file_path,
            raw,
            delimiter="\t",
            header=header,
            comments="",
            fmt=[coord_fmt, coord_fmt, "%d"]
        )

    def save_time_data_to_file(self, file_path, data, x_arr, y_arr, bin_num, bin_width, frame_indices):
        """
        Save time-resolved data as one txt file per frame.

        data:
            raw_time_frames

        Each frame:
            shape = (ny, nx, bin_num)
            or shape = (ny * nx, bin_num)

        Output:
            xxx_time_frame_0001.txt
            xxx_time_frame_0002.txt
            ...

        Each txt columns:
            x, y/z, t_ps, counts
        """

        if data is None:
            raise ValueError("time data is None")

        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("time data should be a non-empty list")

        nx = len(x_arr)
        ny = len(y_arr)

        t_arr = np.arange(bin_num, dtype=int) * bin_width

        root, ext = os.path.splitext(file_path)
        if ext.lower() != ".txt":
            ext = ".txt"

        if frame_indices is None or len(frame_indices) != len(data):
            frame_indices = np.arange(1, len(data) + 1, dtype=int)
        else:
            frame_indices = np.asarray(frame_indices, dtype=int)

        second_axis_name = "y" if self.is_xy_scan() else "z"

        header = f"x\t{second_axis_name}\tt_ps\tcounts"

        coord_fmt = "%.6f" if self.is_galvo_scan() else "%.3f"

        # 对一条 y-line，x 和 t 的列是固定的，可以提前生成
        x_col_one_line = np.repeat(x_arr, bin_num)
        t_col_one_line = np.tile(t_arr, nx)

        for frame_i, frame_data in enumerate(data):
            frame_index = int(frame_indices[frame_i])

            output_file = f"{root}_frame_{frame_index:04d}{ext}"

            counts_frame = self.convert_time_frame_to_counts_3d(
                frame_data=frame_data,
                ny=ny,
                nx=nx,
                bin_num=bin_num
            )

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(header + "\n")

                for iy in range(ny):
                    y_value = y_arr[iy]

                    second_col_one_line = np.full(
                        nx * bin_num,
                        y_value,
                        dtype=float
                    )

                    counts_line = counts_frame[iy, :, :].reshape(-1)

                    block = np.column_stack(
                        (
                            x_col_one_line,
                            second_col_one_line,
                            t_col_one_line,
                            counts_line
                        )
                    )

                    np.savetxt(
                        f,
                        block,
                        delimiter="\t",
                        fmt=[coord_fmt, coord_fmt, "%.0f", "%d"]
                    )

    @staticmethod
    def convert_time_frame_to_counts_3d(frame_data, ny, nx, bin_num):
        """
        Convert one frame to shape:

            ny, nx, bin_num

        Supported input:
            list[ny * nx][bin_num]
            ndarray shape = (ny * nx, bin_num)
            ndarray shape = (ny, nx, bin_num)
        """

        arr = np.asarray(frame_data)

        expected_pixel_num = ny * nx

        if arr.ndim == 3:
            if arr.shape != (ny, nx, bin_num):
                raise ValueError(
                    f"Invalid frame shape: got {arr.shape}, "
                    f"expected {(ny, nx, bin_num)}"
                )
            return arr

        if arr.ndim == 2:
            if arr.shape != (expected_pixel_num, bin_num):
                raise ValueError(
                    f"Invalid frame shape: got {arr.shape}, "
                    f"expected {(expected_pixel_num, bin_num)}"
                )

            return arr.reshape(ny, nx, bin_num)

        raise ValueError(
            f"Unsupported frame data shape: {arr.shape}"
        )

    @staticmethod
    def validate_raw_data(data, expected_cols, data_name="raw data"):
        """
        Validate raw data shape.
        expected_cols:
            intensity: 3 columns -> x, y/z, counts
            time: 4 columns -> x, y/z, t_ps, counts
        """
        if data is None:
            raise ValueError(f"No {data_name} to save.")

        raw = np.asarray(data)

        if raw.size == 0:
            raise ValueError(f"{data_name} is empty.")

        # Allow single row data like [x, y, counts]
        if raw.ndim == 1 and raw.shape[0] == expected_cols:
            raw = raw.reshape(1, expected_cols)

        if raw.ndim != 2 or raw.shape[1] != expected_cols:
            raise ValueError(
                f"{data_name} shape is wrong: {raw.shape}, "
                f"expected Nx{expected_cols}"
            )

        return raw

    @staticmethod
    def ensure_txt_suffix(file_path):
        """
        Make sure file path ends with .txt.
        """
        if not file_path.lower().endswith(".txt"):
            file_path += ".txt"

        return file_path

    def modify_image(self, _=None):
        """
        Slot for image contrast sliders/buttons.
        The optional argument is used to accept slider signal value.
        """
        self.update_image_clim(redraw=True)

    def update_image_clim(self, redraw=True):
        """
        Update image color limits.
        """
        if not hasattr(self, "image") or self.image is None:
            return

        if not hasattr(self, "map") or self.map is None:
            return

        val_max = self.ui.vsMax.value()
        val_min = self.ui.vsMin.value()

        map_max = max(float(np.max(self.map)), 1.0)
        map_mean = float(np.mean(self.map))

        v_max = map_max * (10 ** ((val_max + 1) / 20)) / 100000
        # v_min = min(map_mean, v_max) * val_min / 100
        v_min = v_max * val_min / 100
        v_min = min(v_min, v_max)

        if v_min >= v_max:
            v_min = 0

        self.image.set_clim(v_min, v_max)

        if redraw and hasattr(self, "mplMap") and self.mplMap is not None:
            self.mplMap.draw_idle()

    @staticmethod
    def _pulse_seq_directory():
        """
        Return PulseSeq directory.

        Current file:
            confocal_integrate/src/interface/sequence.py

        PulseSeq directory:
            confocal_integrate/config/PulseSeq
        """

        project_root = Path(__file__).resolve().parents[2]
        return project_root / "config" / "PulseSeq"

    @QtCore.pyqtSlot()
    def open_pulse_seq(self):
        # current_path = Path(__file__).resolve()
        directory = self._pulse_seq_directory()

        location, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose PulseSeq File",
            str(directory),
            "Text Files (*.txt);;All Files (*)"
        )

        if location:
            self.load_pulse_seq(location)

    def load_pulse_seq(self, seq_dir):
        """
        Load Pulse Sequence txt file.

        Example file content:
            ['Laser', '0', '10']
            ['MicroWave', '0', '0']
            ['Ref', '0', '0']
            ['Sig', '0', '10']
            ['Sum', '100']
            ['AOM','1.0']
        """

        seq_path = Path(seq_dir)

        if not seq_path.exists():
            raise FileNotFoundError(f"Pulse sequence file not found: {seq_path}")

        pulse_seq = {}

        with open(seq_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()

                # 跳过空行
                if not line:
                    continue

                try:
                    value = ast.literal_eval(line)
                except Exception as e:
                    raise ValueError(
                        f"Invalid pulse sequence format at line {line_num}: {line}"
                    ) from e

                if not isinstance(value, list) or len(value) == 0:
                    raise ValueError(
                        f"Pulse sequence line {line_num} should be a non-empty list: {line}"
                    )

                key = value[0]

                if not isinstance(key, str):
                    raise ValueError(
                        f"Pulse sequence key at line {line_num} should be string: {line}"
                    )

                # 数据结构：
                # {'Laser': ['0', '10'], ...}
                pulse_seq[key] = value[1:]

        self.seq_dir = str(seq_path)
        self.pulse_seq = pulse_seq
        self.pulse_name = seq_path.stem

        self.ui.leSeq.setText(self.pulse_name)

        print("load successful")
        print("Pulse Sequence:", self.pulse_seq)

    def configure_data_thread_before_scan(self):
        resolution = int(self.ui.cBresolution.currentText())

        x_start = float(self.ui.lexscanstart.text())
        x_end = float(self.ui.lexscanend.text())

        xarr = np.linspace(
            x_start,
            x_end,
            resolution,
            endpoint=False
        )

        if self.is_xy_scan():
            second_start = float(self.ui.leyscanstart.text())
            second_end = float(self.ui.leyscanend.text())
        else:
            second_start = float(self.ui.lezscanstart.text())
            second_end = float(self.ui.lezscanend.text())

        yarr = np.linspace(
            second_start,
            second_end,
            resolution,
            endpoint=False
        )

        self.dThread.set_config(
            xarr=xarr,
            yarr=yarr,
            resolution=resolution,
            bin_num=int(self.ui.leTimeBInNumber.text()),
            bin_width=int(self.ui.leTimeBInWidth.text()),
            frame_num=int(self.ui.leFrameNum.text()),
            reset_raw=True,
        )

    # Methods for Scan Group
    @QtCore.pyqtSlot()
    def start_scan(self):
        """
        Start scan.
        """

        if self.sThread.isRunning():
            self.ui.statusbar.showMessage("Scan is already running.")
            return

        if self.is_time_scan() and not self.pulse_seq:
            self.ui.statusbar.showMessage("Please load laser sequence.")
            return

        # self.replot_image()
        self.ui.statusbar.showMessage("Scanning...")

        try:
            self.configure_scan_thread_before_scan()
            self.configure_data_thread_before_scan()

        except Exception as e:
            print(f"Failed to configure scan: {e}")
            self.ui.statusbar.showMessage("Failed to configure scan.")
            return

        self.set_scan_ui_enabled(scanning=True)

        self.sThread.start()

    def configure_scan_thread_before_scan(self):
        """
        Read UI parameters and configure scan thread.
        """

        parameters, xz_scan = self.get_scan_parameters_from_ui()

        self.sThread.set_config(
            parameters=parameters,
            resolution=int(self.ui.cBresolution.currentText()),
            scan_type=self.ui.cBScanType.currentText(),
            time_scan_type=self.ui.cBTimeScanType.currentText(),
            xz_scan=xz_scan,

            # Intensity scan / dwell time
            scan_dwell_time=float(self.ui.leScanDwellTime.text()),

            # Time scan
            bin_width=int(self.ui.leTimeBInWidth.text()),
            bin_num=int(self.ui.leTimeBInNumber.text()),
            frame_num=int(self.ui.leFrameNum.text()),
            pulse_seq=self.pulse_seq,
        )

    def get_scan_parameters_from_ui(self):
        """
        Get scan parameters from UI.

        Return:
            parameters:
                [x_start, x_end, x_step,
                 second_start, second_end, second_step,
                 fixed_axis_position]

            xz_scan:
                False -> XY scan
                True  -> XZ scan
        """

        x_start = float(self.ui.lexscanstart.text())
        x_end = float(self.ui.lexscanend.text())
        x_step = float(self.ui.lexscanstep.text())

        if self.is_xy_scan():
            second_start = float(self.ui.leyscanstart.text())
            second_end = float(self.ui.leyscanend.text())
            second_step = float(self.ui.leyscanstep.text())
            fixed_axis_position = float(self.ui.leZCursorSet.text())
            xz_scan = False

        else:
            second_start = float(self.ui.lezscanstart.text())
            second_end = float(self.ui.lezscanend.text())
            second_step = float(self.ui.lezscanstep.text())
            fixed_axis_position = float(self.ui.leYCursorSet.text())
            xz_scan = True

        parameters = [
            x_start,
            x_end,
            x_step,
            second_start,
            second_end,
            second_step,
            fixed_axis_position,
        ]

        return parameters, xz_scan

    def set_scan_ui_enabled(self, scanning):
        """
        Enable/disable UI widgets during scan.

        scanning=True:
            disable scan parameter widgets
            enable Stop
            disable Run

        scanning=False:
            restore widgets according to current XY/XZ and time scan mode
        """
        self.scanning = scanning
        editable = self.hardware_initialized and not scanning

        # Image group
        # 一般扫描时仍然允许调 contrast slider，但是不建议保存数据
        self.ui.pbResetPlot.setEnabled(editable)
        self.ui.pbSavedata.setEnabled(editable)
        self.ui.vsMax.setEnabled(self.hardware_initialized)
        self.ui.vsMin.setEnabled(self.hardware_initialized)

        # Scan Group
        self.ui.pbStop.setEnabled(scanning)
        self.set_widgets_enabled(self.get_scan_widgets(), editable)

        # Mode widgets
        self.set_widgets_enabled(self.get_scan_mode_widgets(), editable)

        # Scan Parameters Group
        self.set_widgets_enabled(self.get_scan_parameter_common_widgets(), editable)

        # Y/Z scan widgets
        self.update_yz_scan_widgets_enabled(editable)

        # Position Group
        self.set_widgets_enabled(self.get_position_widgets(), editable)

        # Hide cursor button depends on cursor visibility
        if not editable:
            self.ui.pbHideCursor.setEnabled(False)
        else:
            self.ui.pbHideCursor.setEnabled(
                getattr(self, "cur_vis", False)
            )

        # Time scan parameters
        self.update_time_scan_widgets_enabled(editable)

    @QtCore.pyqtSlot()
    def scan_stopped(self):
        """
        Called when scan thread is finished.
        """
        self.set_scan_ui_enabled(scanning=False)
        self.ui.statusbar.showMessage("Scanning stopped.")

    @QtCore.pyqtSlot()
    def stop_scan(self):
        """
        Stop scan.
        """
        self.ui.statusbar.showMessage("Scan stopping...")
        self.ui.pbStop.setEnabled(False)

        if hasattr(self.sThread, "stop"):
            self.sThread.stop()
        else:
            self.sThread.running = False

    # dThread
    # Run when signal 'update' emit
    @QtCore.pyqtSlot(object)
    def update_image(self, new_map):
        self.map = np.asarray(new_map)

        self.image.set_data(self.map)
        self.update_image_clim(redraw=False)

        self.mplMap.draw_idle()

    # clean cache
    def periodic_clear_cache(self, days=1):
        del self.scanning_cache
        # define time tag
        now = time.time()
        # define expire  limit
        expiration_time = days * 86400
        for filename in os.listdir(self.cache_dir):
            file_path = os.path.join(self.cache_dir, filename)
            if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > expiration_time:
                os.remove(file_path)  # 删除过期文件

    def shutdown_threads(self):
        """
        Safely stop scan thread and data thread before closing interface.
        """

        # 1. Stop scan thread first
        if hasattr(self, "sThread") and self.sThread is not None:
            try:
                if self.sThread.isRunning():
                    if hasattr(self.sThread, "stop"):
                        self.sThread.stop()
                    else:
                        self.sThread.running = False

                    # Wait for hardware cleanup in scan thread
                    if not self.sThread.wait(5000):
                        print("Warning: sThread did not stop in time.")
                        # 不推荐 terminate，除非必须
                        self.sThread.terminate()
                        self.sThread.wait()

            except Exception as e:
                print(f"Failed to stop sThread: {e}")

        # 2. Disconnect signals to avoid updating closing UI
        if hasattr(self, "sThread") and self.sThread is not None:
            try:
                self.safe_disconnect(self.sThread.data_update, self.dThread.process_scan_packet)
                self.safe_disconnect(self.sThread.time_data_ready, self.dThread.process_scan_packet)
                self.safe_disconnect(self.sThread.status_update, self.ui.statusbar.showMessage)
                self.safe_disconnect(self.sThread.error_occurred, self.ui.statusbar.showMessage)
                self.safe_disconnect(self.sThread.finished, self.scan_stopped)
            except Exception as e:
                print(f"Failed to disconnect sThread signals: {e}")

        if hasattr(self, "dThread") and self.dThread is not None:
            try:
                self.safe_disconnect(self.dThread.image_update, self.update_image)
                self.safe_disconnect(self.dThread.error_occurred, self.ui.statusbar.showMessage)
            except Exception as e:
                print(f"Failed to disconnect dThread signals: {e}")

        # 3. Stop dataQThread
        if hasattr(self, "dataQThread") and self.dataQThread is not None:
            try:
                if self.dataQThread.isRunning():
                    self.dataQThread.quit()

                    if not self.dataQThread.wait(5000):
                        print("Warning: dataQThread did not stop in time.")
                        self.dataQThread.terminate()
                        self.dataQThread.wait()

            except Exception as e:
                print(f"Failed to stop dataQThread: {e}")

    @staticmethod
    def safe_disconnect(signal, slot=None):
        try:
            if slot is None:
                signal.disconnect()
            else:
                signal.disconnect(slot)
        except TypeError:
            pass
        except RuntimeError:
            pass

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

        # 如果正在扫描，建议先确认是否停止
        if hasattr(self, "sThread") and self.sThread is not None:
            if self.sThread.isRunning():
                stop_reply = QtWidgets.QMessageBox.question(
                    self,
                    "Scan is running",
                    "Scan is still running. Stop scan and close?",
                    QtWidgets.QMessageBox.Yes |
                    QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No
                )

                if stop_reply == QtWidgets.QMessageBox.No:
                    event.ignore()
                    return

        self.periodic_clear_cache(days=self.CACHE_LIFE)

        # 关键：关闭线程
        self.shutdown_threads()

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