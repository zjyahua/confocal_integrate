import sys
import os
import yaml
import numpy as np
import math
import time
import ast
from pathlib import Path
from PyQt5 import QtWidgets, QtCore
from ui.uipy.single_point_measurement.confocal_pulse_ODMR import Ui_MainWindow
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from src.threads.single_point_exp_threads import SinglePointscanThread, DataThread

class mainGUI(QtWidgets.QMainWindow):
    CACHE_LIFE = 7  # days

    def __init__(self, parent=None, hardware=None, track_interface=None):
        QtWidgets.QWidget.__init__(self, parent)
        # Setup GUI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.track_interface = track_interface
        self._waiting_for_auto_track = False

        # init parameters
        self.config_single_point_exp = None
        self.histogram_sweep = None
        self.histogram_sig = None
        self.histogram_sig_ave = None
        self.histogram_data_fig = None
        self.histogram_Toolbar = None
        self.HistogramPlot = None
        self.freq_sweep = None
        self.time_sweep = None
        self.ref_ave = None
        self.sig_ave = None
        self.scan_data_Toolbar = None
        self.scan_data_fig = None
        self.ScanSigPlot = None
        self.ScanRefPlot = None
        self.hardware_initialized = False
        self.scanning = False
        self.seq_dir = None
        self.pulse_seq = None
        self.pulse_name = None
        self.sThread = None
        self.dThread = None
        self.dataQThread = None
        # Process for initialization
        self.load_defaults()  # Load defaults
        self.init_data_plot() # init time histogram and init scan data
        self.hardware = hardware
        self.connect_method()  # Connect methods to slots
        self.init_button_status()  # Init the state of buttons and textbox
        self.init_hardware()

    # Load and Save defaults
    @QtCore.pyqtSlot()
    def open_defaults(self):
        directory = os.path.dirname(os.path.abspath(__file__))
        location, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose Defaults File', directory)
        if location != '':
            self.load_defaults(location)

    def load_defaults(self, config_path='config/config_single_point_exp.yaml'):
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        self.config_single_point_exp = load_config(config_path=config_file)
        self.update_ui_based_on_default()

    @QtCore.pyqtSlot()
    def save_defaults(self, config_path='config/config_single_point_exp.yaml'):
        self.update_default_based_on_ui()
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        save_config(config=self.config_single_point_exp, config_path=config_file)

    def update_ui_based_on_default(self):
        # load Microwave parameters
        self.load_microwave_config_to_ui()
        # load Time Pulse parameters
        self.load_time_pulse_config_to_ui()
        # load Exp scan parameters
        self.load_exp_scan_config_to_ui()
        # load Time histogram parameters
        self.load_time_histogram_config_to_ui()

    def load_microwave_config_to_ui(self):
        mw_cfg = self.config_single_point_exp.get("MW", {})
        self.set_lineedit_value(self.ui.leMWfreq, mw_cfg.get("current_freq", ""))
        self.set_lineedit_value(self.ui.leMWPower, mw_cfg.get("power", ""))
        self.set_lineedit_value(self.ui.leMWstartfreq, mw_cfg.get("start_freq", ""))
        self.set_lineedit_value(self.ui.leMWendfreq, mw_cfg.get("end_freq", ""))
        self.set_lineedit_value(self.ui.leMWstepfreq, mw_cfg.get("step_freq", ""))

    def load_time_histogram_config_to_ui(self):
        time_cfg = self.config_single_point_exp.get("Time_histogram", {})
        self.set_lineedit_value(self.ui.leTimeBInWidth, time_cfg.get("bin_width_ps", ""))
        self.set_lineedit_value(self.ui.leTimeBInNumber, time_cfg.get("bin_number", ""))

    def load_time_pulse_config_to_ui(self):
        time_pulse_cfg = self.config_single_point_exp.get("Time_pulse", {})
        self.set_lineedit_value(self.ui.leTimestartscan, time_pulse_cfg.get("start_time", ""))
        self.set_lineedit_value(self.ui.leTimeendscan, time_pulse_cfg.get("end_time", ""))
        self.set_lineedit_value(self.ui.leTimepointnum, time_pulse_cfg.get("time_num", ""))

    def load_exp_scan_config_to_ui(self):
        exp_cfg = self.config_single_point_exp.get("Exp_configration", {})
        self.set_lineedit_value(self.ui.Pulse_Tloops_lineEdit, exp_cfg.get("total_loop", ""))
        self.set_lineedit_value(self.ui.Pulse_Taverage_lineEdit, exp_cfg.get("total_average", ""))

    @staticmethod
    def set_lineedit_value(lineedit, value):
        lineedit.setText("" if value is None else str(value))

    def update_default_based_on_ui(self):
        # save microwave parameters
        self.save_microwave_ui_to_config()
        # save Time Pulse parameters
        self.save_time_pulse_ui_to_config()
        # save Exp scan parameters
        self.save_exp_scan_ui_to_config()
        # save time parameters
        self.save_time_histogram_ui_to_config()

    def save_microwave_ui_to_config(self):
        mw_cfg = self.config_single_point_exp.setdefault("MW", {})
        mw_cfg["current_freq"] = self.get_int_from_lineedit(self.ui.leMWfreq)
        mw_cfg["power"] = self.get_int_from_lineedit(self.ui.leMWPower)
        mw_cfg["start_freq"] = self.get_int_from_lineedit(self.ui.leMWstartfreq)
        mw_cfg["end_freq"] = self.get_int_from_lineedit(self.ui.leMWendfreq)
        mw_cfg["step_freq"] = self.get_int_from_lineedit(self.ui.leMWstepfreq)

    def save_time_pulse_ui_to_config(self):
        time_pulse_cfg = self.config_single_point_exp.setdefault("Time_pulse", {})
        time_pulse_cfg["start_time"] = self.get_int_from_lineedit(self.ui.leTimestartscan)
        time_pulse_cfg["end_time"] = self.get_int_from_lineedit(self.ui.leTimeendscan)
        time_pulse_cfg["time_num"] = self.get_int_from_lineedit(self.ui.leTimepointnum)

    def save_exp_scan_ui_to_config(self):
        exp_cfg = self.config_single_point_exp.setdefault("Exp_configration", {})
        exp_cfg["total_loop"]= self.get_int_from_lineedit(self.ui.Pulse_Tloops_lineEdit)
        exp_cfg["total_average"] = self.get_int_from_lineedit(self.ui.Pulse_Taverage_lineEdit)

    def save_time_histogram_ui_to_config(self):
        time_cfg = self.config_single_point_exp.setdefault("Time_histogram", {})
        time_cfg["bin_width_ps"] = self.get_int_from_lineedit(self.ui.leTimeBInWidth)
        time_cfg["bin_number"] = self.get_int_from_lineedit(self.ui.leTimeBInNumber)

    @staticmethod
    def get_int_from_lineedit(lineedit, default=0):
        text = lineedit.text().strip()
        if text == "":
            return default
        return int(float(text))

    def init_data_plot(self):
        """
        Init two data canvas and toolbars.
        """
        self.init_histogram_plot()
        self.init_histogram_toolbar_set()
        self.init_scan_data_plot()
        self.init_scan_data_toolbar_set()

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

    def _create_canvas(self, parent_widget, canvas_attr):
        """
        Create a new matplotlib canvas inside parent_widget.
        Remove the old one if it exists.
        """
        layout = self._ensure_layout(parent_widget)

        old_canvas = getattr(self, canvas_attr, None)
        self._remove_old_canvas(layout, old_canvas)

        fig = Figure(constrained_layout=True)
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)

        setattr(self, canvas_attr, canvas)

        ax = fig.add_subplot(111)

        return canvas, ax

    def _create_toolbar(self, toolbar_widget, toolbar_attr, canvas_attr):
        """
        Create a matplotlib toolbar for a canvas.
        Remove the old toolbar if it exists.
        """
        layout = self._ensure_layout(toolbar_widget)

        old_toolbar = getattr(self, toolbar_attr, None)
        self._remove_old_canvas(layout, old_toolbar)

        canvas = getattr(self, canvas_attr, None)

        if canvas is None:
            raise RuntimeError(f"{canvas_attr} does not exist. Create plot first.")

        toolbar = NavigationToolbar(canvas, toolbar_widget)
        layout.addWidget(toolbar)

        setattr(self, toolbar_attr, toolbar)

    def generate_histogram_sweep_points(self):
        """
        generate the sweep points based on the histogram parameter
        :return: None
        """
        bin_width = int(self.ui.leTimeBInWidth.text())/1000
        bin_number = int(self.ui.leTimeBInNumber.text())
        loop_num = int(self.ui.Pulse_Tloops_lineEdit.text())

        start_time = bin_width
        end_time = start_time * bin_number

        self.histogram_sweep = list(np.linspace(start_time, end_time, bin_number))
        self.histogram_sig = np.random.randint(0, 5, size=(loop_num, bin_number))
        self.histogram_sig_ave = list(np.average(self.histogram_sig, axis=0))

    def is_time_scan(self):
        return self.ui.cBScanType.currentText() == "Time Scan"

    def is_mw_state(self):
        return self.ui.cBMWMode.currentText() == "On"

    def is_histogram_mode(self):
        return self.ui.cBCountMode.currentText() == "Histogram"

    def is_thermal_model(self):
        return self.ui.cBThermalMode.currentText() == "None"

    def is_linear_time_scan(self):
        return self.ui.cBScanscale.currentText() == "Linear"

    def generate_scan_data_sweep_points(self):
        """
        generate the sweep points based on the histogram parameter
        :return: None
        """
        # Frequency scan parameters
        start_freq = float(self.ui.leMWstartfreq.text())
        end_freq = float(self.ui.leMWendfreq.text())
        step_freq = float(self.ui.leMWstepfreq.text())

        if step_freq <= 0:
            raise ValueError("Frequency step must be larger than 0.")

        freq_step_num = math.ceil(float((end_freq - start_freq) / step_freq)) + 1

        self.freq_sweep = list(np.linspace(start_freq, end_freq, freq_step_num))

        # Time scan parameters
        start_time = int(self.ui.leTimestartscan.text())  # unit ns
        end_time = int(self.ui.leTimeendscan.text())  # unit ns
        time_step_num = int(self.ui.leTimepointnum.text())

        if time_step_num <= 0:
            raise ValueError("Time point number must be larger than 0.")

        if self.is_time_scan():
            # Generate the Time Sweep Points (list) based on settings
            if self.is_linear_time_scan() is True:
                self.time_sweep = list(np.linspace(start_time, end_time, time_step_num))
            else:
                if start_time <= 0 or end_time <= 0:
                    raise ValueError("Log time scan requires start/end time > 0.")
                self.time_sweep = list(np.round(np.geomspace(start_time, end_time, time_step_num)))

            point_num = len(self.time_sweep)
        else:
            point_num = len(self.freq_sweep)

        # Generate Fake Data
        self.ref_ave = list(np.random.randint(10, 15, point_num))
        self.sig_ave = list(np.random.randint(0, 5, point_num))

    def init_histogram_plot(self):
        """
        Init the plot for histogram.
        :return: None
        """
        canvas, ax = self._create_canvas(
            self.ui.Time_data_widget,
            "histogram_data_fig"
        )

        self.generate_histogram_sweep_points()

        # 6. 绘图
        self.HistogramPlot, = ax.plot(self.histogram_sweep, self.histogram_sig_ave)

        # 7. 美化
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("Count")
        ax.grid(True, alpha=0.3)

        canvas.draw_idle()

    def init_histogram_toolbar_set(self):
        """
        Init the toolbar for image.
        """
        self._create_toolbar(
            self.ui.Time_data_toolbar_widget,
            "histogram_Toolbar",
            "histogram_data_fig"
        )

    def init_scan_data_plot(self):
        """
        Init the plot for scan data.
        if scan type is Time scan
        plot data is generated from time scan parameters
        if scan type is freq scan
        plot data is generated from MW freq scan parameters
        :return: None
        """
        canvas, ax = self._create_canvas(
            self.ui.Frequency_data_widget,
            "scan_data_fig"
        )

        self.generate_scan_data_sweep_points()

        if self.is_time_scan():
            x_data = self.time_sweep
            x_label = "Time (ns)"
        else:
            x_data = self.freq_sweep
            x_label = "Frequency (MHz)"

        self.ScanSigPlot, = ax.plot(
            x_data,
            self.sig_ave,
            color="b",
            label="Sig"
        )

        self.ScanRefPlot, = ax.plot(
            x_data,
            self.ref_ave,
            color="r",
            label="Ref"
        )

        # 7. 美化
        ax.set_xlabel(x_label)
        ax.set_ylabel("Count")
        ax.grid(True, alpha=0.3)
        ax.legend()

        canvas.draw_idle()

    def init_scan_data_toolbar_set(self):
        """
        Init the toolbar for image.
        """
        self._create_toolbar(
            self.ui.Frequency_data_toolbar_widget,
            "scan_data_Toolbar",
            "scan_data_fig"
        )

    def connect_method(self):
        # Menu Bar
        self.ui.actionSave_Defaults.triggered.connect(self.save_defaults)
        self.ui.actionLoad_Defaults.triggered.connect(self.load_defaults)

        # Exp Configuration
        self.ui.cBScanType.currentTextChanged.connect(self.scan_type_changed)
        self.ui.cBCountMode.currentTextChanged.connect(self.count_mode_changed)
        self.ui.cBMWMode.currentTextChanged.connect(self.mw_mode_changed)

        # MW state Group
        self.ui.pbMWon.clicked.connect(self.mw_on)
        self.ui.pbMWoff.clicked.connect(self.mw_off)

        # Data Group
        self.ui.pbSavetimedata.clicked.connect(self.save_histogram_data)
        self.ui.pbSavefrequencydata.clicked.connect(self.save_scan_data)

        # Exp scan
        self.ui.pBStart.clicked.connect(self.start_scan)
        self.ui.pBStop.clicked.connect(self.stop_scan)

        # Sequence
        self.ui.pbLoadSeq.clicked.connect(self.open_pulse_seq)

    def init_button_status(self):
        """
        This method set the state of buttons and textbox to initial state.
        :return: None
        """
        self.hardware_initialized = False
        self.scanning = False

        # Scan Group
        self.ui.pBStop.setEnabled(False)
        self.ui.pBStart.setEnabled(False)

        # Time Scale group
        self.ui.cBScanscale.setEnabled(False)

        # Time Scan Gate mode Group
        self.set_widgets_enabled(self.get_time_scan_gate_mode_widgets(), False)

        # MW scan Group
        self.set_widgets_enabled(self.get_mw_scan_widgets(), False)

        # MW state group
        # self.ui.rbMWoff.setChecked(True)
        self.ui.pbMWoff.setEnabled(False)
        self.ui.pbMWon.setEnabled(False)

        # MW group
        self.set_widgets_enabled(self.get_mw_widgets(), False)

        # Histogram Group
        self.set_widgets_enabled(self.get_histogram_widgets(), False)

        # Scan parameter Group
        self.set_widgets_enabled(self.get_scan_config_widgets(), False)

        # Sequence Group
        self.ui.pbLoadSeq.setEnabled(False)

        # Track Group
        self.set_widgets_enabled(self.get_track_widgets(), False)

    def get_time_scan_gate_mode_widgets(self):
        return [
            self.ui.leTimestartscan,
            self.ui.leTimeendscan,
            self.ui.leTimepointnum,
        ]

    def get_mw_scan_widgets(self):
        return [
            self.ui.leMWstartfreq,
            self.ui.leMWendfreq,
            self.ui.leMWstepfreq,
        ]

    def get_mw_widgets(self):
        return [
            self.ui.leMWfreq,
            self.ui.leMWPower,
            self.ui.pbMWon
        ]

    def get_histogram_widgets(self):
        return [
            self.ui.leTimeBInNumber,
            self.ui.leTimeBInWidth,
        ]

    def get_scan_config_widgets(self):
        return [
            self.ui.Pulse_Tloops_lineEdit,
            self.ui.Pulse_Taverage_lineEdit,
        ]

    def get_track_widgets(self):
        return [
            self.ui.Track_Threshold_lineEdit,
            self.ui.rBAutoTrack,
        ]

    @staticmethod
    def set_widgets_enabled(widgets, enabled):
        for widget in widgets:
            widget.setEnabled(enabled)

    def scan_type_changed(self, text):
        self.update_ui_by_mode()

    def count_mode_changed(self, text):
        self.update_ui_by_mode()

    def mw_mode_changed(self,text):
        self.update_ui_by_mode()

    def update_ui_by_mode(self):
        """
            Update group visibility and enable state according to:
            Scan type, Count mode, Microwave mode.
            """

        editable = self.hardware_initialized and not self.scanning

        is_time = self.is_time_scan()
        is_histogram = self.is_histogram_mode()
        is_gate = not is_histogram
        is_mw_on = self.is_mw_state()

        # ============================================================
        # Default: hide all mode-dependent groups first
        # ============================================================
        groups = [
            self.ui.Time_data_group,
            self.ui.Time_histogram_group,
            self.ui.Time_scan_config_group,
            self.ui.Time_scan_scale_group,
            self.ui.Frequency_data_group,
            self.ui.MW_state_group,
            self.ui.MW_group,
            self.ui.MW_scan_group,
        ]

        for group in groups:
            group.setVisible(False)

        # ============================================================
        # Case 1:
        # Time Scan + Histogram
        # ============================================================
        if is_time and is_histogram:
            self.ui.Time_data_group.setVisible(True)
            self.ui.Time_histogram_group.setVisible(True)

            if is_mw_on:
                self.ui.MW_state_group.setVisible(True)
                self.ui.MW_group.setVisible(True)

            self.set_widgets_enabled(
                self.get_histogram_widgets(),
                editable
            )

            self.set_widgets_enabled(
                self.get_time_scan_gate_mode_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_mw_widgets(),
                editable and is_mw_on
            )

            self.set_widgets_enabled(
                self.get_mw_scan_widgets(),
                False
            )

            self.init_histogram_plot()

            # ============================================================
            # Case 2:
            # Time Scan + Gate
            # ============================================================
        elif is_time and is_gate:
            self.ui.Time_scan_config_group.setVisible(True)
            self.ui.Time_scan_scale_group.setVisible(True)
            self.ui.Frequency_data_group.setVisible(True)

            if is_mw_on:
                self.ui.MW_state_group.setVisible(True)
                self.ui.MW_group.setVisible(True)

            self.ui.MW_scan_group.setVisible(False)

            self.set_widgets_enabled(
                self.get_histogram_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_time_scan_gate_mode_widgets(),
                editable
            )

            self.set_widgets_enabled(
                self.get_mw_widgets(),
                editable and is_mw_on
            )

            self.set_widgets_enabled(
                self.get_mw_scan_widgets(),
                False
            )

            self.init_scan_data_plot()

        # ============================================================
        # Case 3:
        # Frequency Scan + Gate
        # ============================================================
        elif not is_time and is_gate:
            self.ui.Frequency_data_group.setVisible(True)
            self.ui.MW_state_group.setVisible(True)
            self.ui.MW_group.setVisible(True)
            self.ui.MW_scan_group.setVisible(True)

            self.set_widgets_enabled(
                self.get_histogram_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_time_scan_gate_mode_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_mw_widgets(),
                editable
            )

            self.set_widgets_enabled(
                self.get_mw_scan_widgets(),
                editable
            )

            self.init_scan_data_plot()

        # ============================================================
        # Optional fallback:
        # Frequency Scan + Histogram
        # You probably do not want this mode.
        # Hide everything except maybe Frequency_data_group.
        # ============================================================
        else:
            self.set_widgets_enabled(
                self.get_histogram_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_time_scan_gate_mode_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_mw_widgets(),
                False
            )

            self.set_widgets_enabled(
                self.get_mw_scan_widgets(),
                False
            )

    # Methods for Hardware Group
    @QtCore.pyqtSlot()
    def init_hardware(self):
        """
        Init all hardware and pass them to Threads.
        """
        self.ui.statusbar.showMessage("Initializing...")
        self.set_hardware_ui_enabled(True)
        try:
            self.init_threads()

        except Exception as e:
            print(e)
            self.ui.statusbar.showMessage("Initialization Failed")
            return

        self.ui.statusbar.showMessage("Initialized Successfully")

    def set_hardware_ui_enabled(self, enabled):
        """
        Enable/disable UI controls after hardware initialization.
        """
        self.hardware_initialized = enabled

        self.set_widgets_enabled(self.get_time_scan_gate_mode_widgets(), enabled)
        self.set_widgets_enabled(self.get_mw_widgets(), enabled)
        self.set_widgets_enabled(self.get_mw_scan_widgets(), enabled)
        self.set_widgets_enabled(self.get_histogram_widgets(), enabled)
        self.set_widgets_enabled(self.get_track_widgets(), enabled)
        self.set_widgets_enabled(self.get_scan_config_widgets(), enabled)

        # Stop button should only be enabled during scan
        self.ui.pBStop.setEnabled(False)
        self.ui.pBStart.setEnabled(True)

        # Sequence Group
        self.ui.pbLoadSeq.setEnabled(True)

        # Time Scale group
        self.ui.cBScanscale.setEnabled(True)

        # Restore time parameter widgets according to current time scan mode
        self.update_ui_by_mode()

    def init_threads(self):
        """
        Initialize scan thread and data thread.
        """
        self.sThread = SinglePointscanThread(self.hardware)

        self.dataQThread = QtCore.QThread(self)
        self.dThread = DataThread()
        self.dThread.moveToThread(self.dataQThread)
        self.dataQThread.finished.connect(self.dThread.deleteLater)
        self.dataQThread.start()

        self.sThread.data_update.connect(self.dThread.process_packet)
        self.sThread.track_update.connect(self.auto_track_update)

        if self.track_interface is not None:
            if hasattr(self.track_interface, "tracking_finished"):
                self.track_interface.tracking_finished.connect(self.auto_track_finished)

        self.dThread.image_update.connect(self.update_image)
        self.dThread.error_occurred.connect(self.ui.statusbar.showMessage)

        self.sThread.status_update.connect(self.ui.statusbar.showMessage)
        self.sThread.error_occurred.connect(self.ui.statusbar.showMessage)

        self.sThread.finished.connect(self.scan_stopped)

    # Methods for Microwave Group
    def mw_on(self):
        self.hardware.mw_source.set_frequency(float(self.ui.leMWfreq.text()))
        self.hardware.mw_source.set_power(float(self.ui.leMWPower.text()))
        self.hardware.mw_source._on()
        self.ui.rbMWon.setChecked(True)
        self.ui.rbMWoff.setChecked(False)
        self.ui.pbMWon.setEnabled(False)
        self.ui.pbMWoff.setEnabled(True)

    def mw_off(self):
        self.hardware.mw_source.off()
        self.ui.rbMWon.setChecked(False)
        self.ui.rbMWoff.setChecked(True)
        self.ui.pbMWon.setEnabled(True)
        self.ui.pbMWoff.setEnabled(False)

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

    @QtCore.pyqtSlot(str)
    def auto_track_update(self, message):
        """
        Called when scan thread requests auto tracking.

        Important:
            track_interface.track_max_count() only starts MaxThread.
            The scan thread will be released only when auto_track_finished()
            receives track_interface.tracking_finished.
        """

        if self.track_interface is None:
            self.ui.statusbar.showMessage("No track interface available.")
            self.sThread.notify_tracking_finished(False)
            return

        if not self.ui.rBAutoTrack.isChecked():
            self.ui.statusbar.showMessage("Auto track is disabled.")
            self.sThread.notify_tracking_finished(True)
            return

        self._waiting_for_auto_track = True

        self.ui.statusbar.showMessage(message)

        try:
            # Prepare laser/AOM for tracking.
            self.hardware.pulser.all_constant([0], analog_0=1.0)

            started = self.track_interface.track_max_count()

            if not started:
                self._waiting_for_auto_track = False
                self.sThread.notify_tracking_finished(False)

        except Exception as e:
            self._waiting_for_auto_track = False
            msg = f"Failed to start auto tracking: {e}"
            self.ui.statusbar.showMessage(msg)
            self.sThread.notify_tracking_finished(False)

    @QtCore.pyqtSlot(bool, str)
    def auto_track_finished(self, ok, message):
        """
        Called when Track interface MaxThread really finished.
        """

        if not self._waiting_for_auto_track:
            return

        self._waiting_for_auto_track = False

        if ok:
            self.ui.statusbar.showMessage("Auto tracking finished. Resume scan.")
        else:
            self.ui.statusbar.showMessage(f"Auto tracking failed: {message}")

        self.sThread.notify_tracking_finished(ok)

    @QtCore.pyqtSlot(object)
    def update_image(self, data):
        """
        Receive processed data from DataThread and update GUI plots.
        """

        if not isinstance(data, dict):
            return

        plot_type = data.get("plot_type")

        if plot_type == "histogram":
            self._update_histogram_plot(data)

        elif plot_type in ("frequency_scan", "time_scan"):
            self._update_scan_plot(data, plot_type)

    def _update_histogram_plot(self, data):
        x = np.asarray(data["x"], dtype=float)
        y = np.asarray(data["y"], dtype=float)

        self.histogram_sweep = x.tolist()
        self.histogram_sig_ave = y.tolist()

        self.HistogramPlot.set_data(x, y)

        ax = self.HistogramPlot.axes

        self._autoscale_axis(ax, x, [y], force_y_zero=True)

        ax.figure.canvas.draw_idle()

        self._update_loop_point_ui(data, update_point=False)

    def _update_scan_plot(self, data, plot_type):
        """
        Update frequency scan or time scan plot.
        """

        x = np.asarray(data["x"], dtype=float)
        sig_y = np.asarray(data["sig_y"], dtype=float)
        ref_y = np.asarray(data["ref_y"], dtype=float)

        if plot_type == "frequency_scan":
            self.freq_sweep = x.tolist()
        elif plot_type == "time_scan":
            self.time_sweep = x.tolist()

        self.sig_ave = sig_y.tolist()
        self.ref_ave = ref_y.tolist()

        self.ScanSigPlot.set_data(x, sig_y)
        self.ScanRefPlot.set_data(x, ref_y)

        ax = self.ScanSigPlot.axes
        self._autoscale_axis(ax, x, [sig_y, ref_y], force_y_zero=False)
        ax.figure.canvas.draw_idle()

        self._update_loop_point_ui(data, update_point=True)
        self._update_track_ui(data, sig_y, ref_y)

    @staticmethod
    def _autoscale_axis(ax, x,  y_list, force_y_zero=False):
        """
        Auto scale x/y axis safely.
        """

        x = np.asarray(x, dtype=float)
        finite_x = x[np.isfinite(x)]

        if finite_x.size > 0:
            x_min = float(np.min(finite_x))
            x_max = float(np.max(finite_x))

            if x_min == x_max:
                margin = max(abs(x_min) * 1e-6, 1.0)
                ax.set_xlim(x_min - margin, x_max + margin)
            else:
                ax.set_xlim(x_min, x_max)

        finite_y_list = []

        for y in y_list:
            y = np.asarray(y, dtype=float)
            finite_y = y[np.isfinite(y)]

            if finite_y.size > 0:
                finite_y_list.append(finite_y)

        if not finite_y_list:
            return

        finite_y_all = np.concatenate(finite_y_list)

        y_min = float(np.min(finite_y_all))
        y_max = float(np.max(finite_y_all))

        if y_max <= 0:
            y_max = 1.0

        if force_y_zero or y_min >= 0:
            ax.set_ylim(0, y_max * 1.1)
        else:
            ax.set_ylim(y_min * 1.1, y_max * 1.1)

    def _update_loop_point_ui(self, data, update_point=False):
        """
        Update current loop and point display.
        """

        loop_idx = data.get("loop_index", None)

        if loop_idx is not None:
            self.ui.Scan_Cloop_lineEdit.setText(str(int(loop_idx) + 1))

        if update_point:
            point_idx = data.get("point_index", None)

            if point_idx is not None:
                self.ui.Scan_Cpoint_lineEdit.setText(str(int(point_idx) + 1))

    def _update_track_ui(self, data, sig_y=None, ref_y=None):
        """
        Update Track_Sig_lineEdit and Track_Ref_lineEdit.

        Priority:
            1. Use data["sig"] and data["ref"] if they exist.
            2. Otherwise, use sig_y/ref_y at current point_index.
        """

        sig = data.get("sig", None)
        ref = data.get("ref", None)

        point_idx = data.get("point_index", None)

        if point_idx is not None:
            point_idx = int(point_idx)

            if sig is None and sig_y is not None:
                if 0 <= point_idx < len(sig_y):
                    sig = sig_y[point_idx]

            if ref is None and ref_y is not None:
                if 0 <= point_idx < len(ref_y):
                    ref = ref_y[point_idx]

        if sig is not None and np.isfinite(sig):
            self.ui.Track_Sig_lineEdit.setText(self._format_number(sig))

        if ref is not None and np.isfinite(ref):
            self.ui.Track_Ref_lineEdit.setText(self._format_number(ref))

    @staticmethod
    def _format_number(value):
        """
        Format number for lineEdit display.
        """

        value = float(value)

        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))

        return f"{value:.9g}"

    # Methods for Data Group
    def save_histogram_data(self):
        """
        Let user choose file location and save histogram raw data.
        """

        default_dir = r"C:\zjh\experiment data"
        os.makedirs(default_dir, exist_ok=True)

        default_name = time.strftime(
            "%Y-%m-%d_%H-%M-%S_histogram.txt",
            time.localtime()
        )

        default_path = os.path.join(default_dir, default_name)

        dir_save_data, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save histogram data",
            default_path,
            "Text (*.txt)"
        )

        if dir_save_data == "":
            sys.stderr.write("No file is saved!\n")
            return

        if not dir_save_data.lower().endswith(".txt"):
            dir_save_data += ".txt"

        self.write_histogram_data(dir_save_data)

    def write_histogram_data(self, dir_save_data):
        """
        Save histogram raw data to txt file.
        """

        raw = getattr(self.dThread, "raw_histogram", None)

        if raw is None:
            sys.stderr.write("No histogram data to be saved!\n")
            self.ui.statusbar.showMessage("No histogram data to be saved!")
            return

        raw = np.asarray(raw)

        if raw.ndim != 3 or raw.shape[2] != 3:
            sys.stderr.write("Invalid histogram raw data format!\n")
            self.ui.statusbar.showMessage("Invalid histogram raw data format!")
            return

        # Optional: only save loops that already have valid data
        valid_loop = getattr(self.dThread, "histogram_loop_valid", None)

        if valid_loop is not None:
            valid_loop = np.asarray(valid_loop, dtype=bool)

            if np.any(valid_loop):
                raw_to_save = raw[valid_loop]
            else:
                sys.stderr.write("No valid histogram loop data to be saved!\n")
                self.ui.statusbar.showMessage("No valid histogram loop data to be saved!")
                return
        else:
            raw_to_save = raw

        loop_num = raw.shape[0]
        bin_num = raw.shape[1]

        try:
            with open(dir_save_data, "w", encoding="utf-8") as f:
                # Header
                header = [
                    ["DATA_VERSION:", "2.1"],
                    ["Pulse_sequence:", self.pulse_seq],
                    [
                        "Experiment time:",
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                        "Scanning Mode:",
                        "Time Sweep",
                    ],
                    [
                        "Count Mode:",
                        "Histogram",
                        "Total Loop:",
                        loop_num,
                        "Point per loop:",
                        bin_num,
                    ],
                    [
                        "Bin width:",
                        self.dThread.bin_width,
                        "Unit:",
                        "ps",
                    ],
                    ["Data Mode:", "Linear"],
                    ["Signal", "Time (ns)", "Loop Num"],
                ]

                for row in header:
                    f.write("\t".join(map(str, row)) + "\n")

                # Data
                for loop_data in raw_to_save:
                    for point in loop_data:
                        f.write(
                            f"{point[0]:.0f}\t"
                            f"{point[1]:.9g}\t"
                            f"{point[2]:.0f}\n"
                        )

            self.ui.statusbar.showMessage(f"Histogram data saved: {dir_save_data}")

        except Exception as e:
            msg = f"Failed to save histogram data: {e}"
            sys.stderr.write(msg + "\n")
            self.ui.statusbar.showMessage(msg)

    # Methods for Data Group
    def save_scan_data(self):
        """
        Save gate scan data.
        Automatically choose time scan or frequency scan according to current scan type.
        """

        default_dir = r"C:\zjh\experiment data"
        os.makedirs(default_dir, exist_ok=True)

        scan_name = "time_gate" if self.is_time_scan() else "frequency_gate"

        default_name = time.strftime(
            f"%Y-%m-%d_%H-%M-%S_{scan_name}.txt",
            time.localtime()
        )

        default_path = os.path.join(default_dir, default_name)

        dir_save_data, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Scan data",
            default_path,
            "Text (*.txt)"
        )

        if dir_save_data == "":
            sys.stderr.write("No file is saved!\n")
            return

        if not dir_save_data.lower().endswith(".txt"):
            dir_save_data += ".txt"

        if self.is_time_scan():
            self.write_time_scan_data(dir_save_data)
        else:
            self.write_frequency_scan_data(dir_save_data)

    def write_time_scan_data(self, dir_save_data):
        """
        Save time gate scan data.

        Raw data format:
            raw shape == (loop_num, point_num, 4)

            column 0 -> Signal
            column 1 -> Reference
            column 2 -> Time
            column 3 -> Loop number
        """

        self._write_gate_scan_data(
            dir_save_data=dir_save_data,
            raw_attr="raw_gate_time",
            valid_attr="gate_time_valid",
            scan_label="time",
            scanning_mode="Time Sweep",
            data_mode=self.ui.cBScanscale.currentText(),
            x_title="Time (ns)",
            x_format=".0f",
        )

    def write_frequency_scan_data(self, dir_save_data):
        """
        Save frequency gate scan data.

        Raw data format:
            raw shape == (loop_num, point_num, 4)

            column 0 -> Signal
            column 1 -> Reference
            column 2 -> Frequency
            column 3 -> Loop number
        """

        self._write_gate_scan_data(
            dir_save_data=dir_save_data,
            raw_attr="raw_gate_frequency",
            valid_attr="gate_frequency_valid",
            scan_label="frequency",
            scanning_mode="Frequency Sweep",
            data_mode="Linear",
            x_title="Frequency (MHz)",
            x_format=".9g",
        )

    def _write_gate_scan_data(
            self,
            *,
            dir_save_data,
            raw_attr,
            valid_attr,
            scan_label,
            scanning_mode,
            data_mode,
            x_title,
            x_format,
    ):
        """
        Generic writer for gate scan data.

        Raw data format:
            raw shape == (loop_num, point_num, 4)

            column 0 -> Signal
            column 1 -> Reference
            column 2 -> X value, time or frequency
            column 3 -> Loop number
        """

        scan_label = scan_label.lower()
        scan_label_title = scan_label.capitalize()

        raw = getattr(self.dThread, raw_attr, None)

        if raw is None:
            msg = f"No {scan_label} scan data to be saved!"
            sys.stderr.write(msg + "\n")
            self.ui.statusbar.showMessage(msg)
            return

        raw = np.asarray(raw)

        if raw.ndim != 3 or raw.shape[2] != 4:
            msg = f"Invalid {scan_label} scan raw data format!"
            sys.stderr.write(msg + "\n")
            self.ui.statusbar.showMessage(msg)
            return

        loop_num = raw.shape[0]
        point_num = raw.shape[1]

        valid_point = getattr(self.dThread, valid_attr, None)

        if valid_point is not None:
            valid_point = np.asarray(valid_point, dtype=bool)

            if valid_point.shape != (loop_num, point_num):
                msg = f"Invalid {scan_label} valid mask format!"
                sys.stderr.write(msg + "\n")
                self.ui.statusbar.showMessage(msg)
                return

        else:
            # If no valid mask exists, save finite points only.
            valid_point = np.all(np.isfinite(raw), axis=2)

        if not np.any(valid_point):
            msg = f"No valid {scan_label} scan data to be saved!"
            sys.stderr.write(msg + "\n")
            self.ui.statusbar.showMessage(msg)
            return

        try:
            with open(dir_save_data, "w", encoding="utf-8") as f:
                header = [
                    ["DATA_VERSION:", "2.1"],
                    ["Pulse_sequence:", self.pulse_seq],
                    [
                        "Experiment time:",
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                        "Scanning Mode:",
                        scanning_mode,
                    ],
                    [
                        "Count Mode:",
                        "Gate",
                        "Total Loop:",
                        loop_num,
                        "Point per loop:",
                        point_num,
                    ],
                    [
                        "MW Power:",
                        self.ui.leMWPower.text(),
                        "Unit:",
                        "dBm",
                    ],
                    [
                        "Average Number:",
                        self.ui.Pulse_Taverage_lineEdit.text(),
                    ],
                    ["Data Mode:", data_mode],
                    [
                        "Signal",
                        "Reference",
                        x_title,
                        "Loop Num",
                    ],
                ]

                for row in header:
                    f.write("\t".join(map(str, row)) + "\n")

                saved_count = 0

                for loop_idx in range(loop_num):
                    for point_idx in range(point_num):
                        if not valid_point[loop_idx, point_idx]:
                            continue

                        sig = raw[loop_idx, point_idx, 0]
                        ref = raw[loop_idx, point_idx, 1]
                        x_value = raw[loop_idx, point_idx, 2]
                        loop_value = raw[loop_idx, point_idx, 3]

                        if not np.all(np.isfinite([sig, ref, x_value, loop_value])):
                            continue

                        f.write(
                            f"{sig:.0f}\t"
                            f"{ref:.0f}\t"
                            f"{x_value:{x_format}}\t"
                            f"{loop_value:.0f}\n"
                        )

                        saved_count += 1

            self.ui.statusbar.showMessage(
                f"{scan_label_title} scan data saved: {dir_save_data}"
            )

        except Exception as e:
            msg = f"Failed to save {scan_label} scan data: {e}"
            sys.stderr.write(msg + "\n")
            self.ui.statusbar.showMessage(msg)

    def start_scan(self):
        if self.sThread.isRunning():
            self.ui.statusbar.showMessage("Scan is already running.")
            return

        if not self.pulse_seq:
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
        if self.is_histogram_mode():
            self.generate_histogram_sweep_points()
        else:
            self.generate_scan_data_sweep_points()

        self.sThread.set_single_point_exp_config(
            scan_type=self.ui.cBScanType.currentText(),
            count_mode=self.ui.cBCountMode.currentText(),
            bin_width=int(self.ui.leTimeBInWidth.text()),
            bin_num=int(self.ui.leTimeBInNumber.text()),
            total_loop_num=int(self.ui.Pulse_Tloops_lineEdit.text()),
            average_num=int(self.ui.Pulse_Taverage_lineEdit.text()),
            pulse_seq=self.pulse_seq,
            time_sweep_arr=self.time_sweep,
            freq_sweep_arr=self.freq_sweep,
            threshold=int(self.ui.Track_Threshold_lineEdit.text()),
            auto_track_enabled=self.ui.rBAutoTrack.isChecked(),
        )

    def configure_data_thread_before_scan(self):
        self.dThread.set_config(
            time_sweep_arr=self.time_sweep,
            freq_sweep_arr=self.freq_sweep,
            bin_num=int(self.ui.leTimeBInNumber.text()),
            bin_width=int(self.ui.leTimeBInWidth.text()),
            total_loop_num=int(self.ui.Pulse_Tloops_lineEdit.text()),
            reset_raw=True,
        )

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
        self.ui.pbSavetimedata.setEnabled(editable)
        self.ui.pbSavefrequencydata.setEnabled(editable)

        # Scan Group
        self.ui.pBStop.setEnabled(scanning)
        self.ui.pBStart.setEnabled(not scanning)
        self.set_widgets_enabled(self.get_scan_config_widgets(), editable)

        # histogram Group
        self.set_widgets_enabled(self.get_histogram_widgets(), editable)

        # MW Group
        if self.is_mw_state():
            self.set_widgets_enabled(self.get_mw_widgets(), editable)
            self.ui.pbMWoff.setEnabled(editable)
        self.set_widgets_enabled(self.get_mw_scan_widgets(), editable)

        # Time scan group
        self.set_widgets_enabled(self.get_time_scan_gate_mode_widgets(), editable)
        self.ui.cBScanscale.setEnabled(editable)

        # Track Group
        self.set_widgets_enabled(self.get_track_widgets(), editable)

    @QtCore.pyqtSlot()
    def scan_stopped(self):
        """
        Called when scan thread is finished.
        """
        self.set_scan_ui_enabled(scanning=False)
        if self.is_mw_state():
            self.ui.pbMWon.setEnabled(False)
        self.ui.statusbar.showMessage("Scanning stopped.")

    @QtCore.pyqtSlot()
    def stop_scan(self):
        """
        Stop scan.
        """
        self.ui.statusbar.showMessage("Scan stopping...")
        self.ui.pBStop.setEnabled(False)

        if hasattr(self.sThread, "stop"):
            self.sThread.stop()
        else:
            self.sThread.running = False

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
                self.safe_disconnect(self.sThread.data_update, self.dThread.process_packet)
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