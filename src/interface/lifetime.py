"""
Created on Dec 10, 2024

This File is the Main Thread for lifetime

@author: jiahua
"""

import sys
import os
import yaml
import time
from collections import deque
from ui.uipy.Lifetime.confocal_lifetime import Ui_MainWindow
from PyQt5 import QtWidgets, QtCore

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from src.threads.lifetime_threads import TimeDataThread, TimeSweepThread, FreqDataThread, FreqSweepThread
# import src.utils.logger as logger

class mainGUI(QtWidgets.QMainWindow):
    SIGNAL_ExpLifetimeClose = QtCore.pyqtSignal(name='ExpLifetimeClose')

    def __init__(self, parent=None, hardware=None, track_interface=None):
        QtWidgets.QWidget.__init__(self, parent)
        # Setup GUI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # init data
        self.track_interface = track_interface
        self.time_sweep = None
        self.time_sig = None
        self.time_sig_ave = None
        self.freq_sweep = [5,10,20,25,40,50,100,125,200,250,500,625,1000,1250,2500,5000]
        self.freq_sig = None
        self.freq_sig_ave = None
        self.pulse_name = None
        self.data_seq = None
        self.pulse_seq = None
        self.saved_time_data = None
        self.saved_freq_data = None
        self.time_sig_plot = None
        self.fre_sig_plot = None
        self.pause_status = None
        self.config_lifetime = None
        self.config_lifetime_freq_list = None
        self.config_lifetime_fit = None
        self.a_fit = None
        self.b_fit = None
        self.phi_fit = None
        self.auto_save_location = None
        # Process for initialization
        self.load_defaults()  # Load defaults
        self.generate_time_sweep_points()
        self.generate_freq_sweep_points(self.freq_sweep)
        self.connect_methods()  # Connect methods to slots
        self.init_button_status()
        self.init_time_data_plot()
        self.init_time_toolbar_set()
        self.init_freq_data_plot()
        self.init_freq_toolbar_set()
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

    def load_defaults(self, config_path='config/config_lifetime.yaml'):
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        self.config_lifetime = load_config(config_path=config_file)
        self.update_ui_based_on_default()

    @QtCore.pyqtSlot()
    def save_defaults(self, config_path='config/config_lifetime.yaml'):
        self.update_default_based_on_ui()
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        save_config(config=self.config_lifetime, config_path=config_file)

    def update_ui_based_on_default(self):
        self.ui.Time_bin_width_lineEdit.setText(str(self.config_lifetime['Scan_Time_Parameters']['bin_width_ps']))
        self.ui.Time_bin_num_lineEdit.setText(str(self.config_lifetime['Scan_Time_Parameters']['bin_number']))
        self.ui.Pulse_Tloops_lineEdit.setText(str(self.config_lifetime['Exp_Parameters']['Total_loop']))
        self.ui.Pulse_Taverage_lineEdit.setText(str(self.config_lifetime['Exp_Parameters']['Total_average']))
        self.ui.Freq_num.setText(str(self.config_lifetime['Freq_Parameter']['Freq_kHz']))

    def update_default_based_on_ui(self):
        self.config_lifetime['Scan_Time_Parameters']['bin_width_ps'] = int(self.ui.Time_bin_width_lineEdit.text())
        self.config_lifetime['Scan_Time_Parameters']['bin_number'] = int(self.ui.Time_bin_num_lineEdit.text())
        self.config_lifetime['Exp_Parameters']['Total_loop'] = int(self.ui.Pulse_Tloops_lineEdit.text())
        self.config_lifetime['Exp_Parameters']['Total_average'] = int(self.ui.Pulse_Taverage_lineEdit.text())
        self.config_lifetime['Freq_Parameter']['Freq_kHz'] = int(self.ui.Freq_num.text())

    # Methods for initialization
    def connect_methods(self):
        """
        This method connects methods to the slots
        :return: None
        """
        # Menu Bar
        self.ui.actionSave_Defaults.triggered.connect(self.save_defaults)
        self.ui.actionLoad_Defaults.triggered.connect(self.load_defaults)

        # Data Group
        self.ui.Time_Data_Save_pushButton.clicked.connect(self.save_time_data)
        self.ui.Freq_Data_Save_pushButton.clicked.connect(self.save_freq_data)

        # Pulse Group
        self.ui.Seq_Load_pushButton.clicked.connect(self.open_pulse_seq)
        self.ui.Freq_list_Load_pushButton.clicked.connect(self.load_freq_list)
        self.ui.Freq_list_UnLoad_pushButton.clicked.connect(self.unload_freq_list)
        self.ui.Fit_Load_pushButton.clicked.connect(self.load_fit_parameter)
        self.ui.Fit_UnLoad_pushButton.clicked.connect(self.unload_fit_parameter)

        # Exp Group
        self.ui.TCSPC_Experiment_Start_pushButton.clicked.connect(self.tcspc_start_scan)
        self.ui.TCSPC_Experiment_Stop_pushButton.clicked.connect(self.tcspc_stop_scan)
        self.ui.Freq_Experiment_Start_pushButton.clicked.connect(self.freq_start_scan)
        self.ui.Freq_Experiment_Stop_pushButton.clicked.connect(self.freq_stop_scan)

    def init_button_status(self):
        """
        This method set the state of buttons and textbox to initial state.
        :return: None
        """
        # Data Group
        self.ui.Time_Data_Save_pushButton.setEnabled(False)
        self.ui.Freq_Data_Save_pushButton.setEnabled(False)
        # Exp Group
        self.ui.TCSPC_Experiment_Stop_pushButton.setEnabled(False)
        self.ui.TCSPC_Experiment_Start_pushButton.setEnabled(False)
        self.ui.Freq_Experiment_Start_pushButton.setEnabled(False)
        self.ui.Freq_Experiment_Stop_pushButton.setEnabled(False)
        # Pulse Group
        self.ui.Seq_Load_pushButton.setEnabled(False)
        self.ui.Freq_list_Load_pushButton.setEnabled(False)
        self.ui.Freq_list_UnLoad_pushButton.setEnabled(False)
        # Track Group
        self.ui.Track_Auto_Track_checkbox.setEnabled(False)
        # sequence Group
        self.ui.cB_Sin.setEnabled(False)
        self.ui.cB_SelfDefine.setEnabled(False)

    def init_time_data_plot(self):
        """
        Init the plot for image.
        :return: None
        """
        # Set canvas
        fig1 = Figure()
        self.ui.time_data_fig = FigureCanvas(fig1)
        self.ui.time_data_fig.setParent(self.ui.Time_Sig_Data_line_Window_widget)
        self.ui.time_data_fig.setGeometry(QtCore.QRect(QtCore.QPoint(0, 0), self.ui.Time_Sig_Data_line_Window_widget.size()))
        self.ui.time_data_fig.axes = self.ui.time_data_fig.figure.add_subplot(111)
        self.ui.time_data_fig.figure.subplots_adjust(top=0.95, bottom=0.25, right=0.9)
        # Init plot
        self.time_sig_plot, = self.ui.time_data_fig.axes.plot(self.time_sweep, self.time_sig_ave, 'b')
        # Set fig parameters
        self.ui.time_data_fig.axes.set_xlabel('time (ns)')
        self.ui.time_data_fig.axes.set_ylabel('Counts')
        self.ui.time_data_fig.axes.legend('sig', fontsize=6.5, bbox_to_anchor=(1, 1), loc='upper right')
        self.ui.time_data_fig.axes.set_xlim(np.min(self.time_sweep), np.max(self.time_sweep))
        self.ui.time_data_fig.draw()

    def init_freq_data_plot(self):
        """
        Init the plot for image.
        :return: None
        """
        # Set canvas
        fig2 = Figure()
        self.ui.freq_data_fig = FigureCanvas(fig2)
        self.ui.freq_data_fig.setParent(self.ui.Freq_Sig_Data_line_Window_widget)
        self.ui.freq_data_fig.setGeometry(QtCore.QRect(QtCore.QPoint(0, 0), self.ui.Freq_Sig_Data_line_Window_widget.size()))
        self.ui.freq_data_fig.axes = self.ui.freq_data_fig.figure.add_subplot(111)
        self.ui.freq_data_fig.figure.subplots_adjust(top=0.95, bottom=0.25, right=0.9)
        # Init plot
        self.freq_sig_plot, = self.ui.freq_data_fig.axes.plot(self.freq_sweep, self.freq_sig_ave, 'b')
        # Set fig parameters
        self.ui.freq_data_fig.axes.set_xlabel('freq (kHz)')
        self.ui.freq_data_fig.axes.set_ylabel('Modulation Amplitude')
        self.ui.freq_data_fig.axes.legend('sig', fontsize=6.5, bbox_to_anchor=(1, 1), loc='upper right')
        self.ui.freq_data_fig.axes.set_xlim(np.min(self.freq_sweep), np.max(self.freq_sweep))
        self.ui.freq_data_fig.axes.set_xscale("log")
        self.ui.freq_data_fig.draw()

    def init_time_toolbar_set(self):
        """
        Init the toolbar for image
        Returns: None
        """
        self.ui.time_mplToolbar = NavigationToolbar(self.ui.time_data_fig, self.ui.Time_Sig_Data_Toolbar_widget)
        self.ui.time_mplToolbar.setGeometry(QtCore.QRect(0, 0, self.ui.Time_Sig_Data_Toolbar_widget.size().width(), 25))
        self.ui.time_mplToolbar.setParent(self.ui.Time_Sig_Data_Toolbar_widget)

    def init_freq_toolbar_set(self):
        self.ui.freq_mplToolbar = NavigationToolbar(self.ui.freq_data_fig, self.ui.Freq_Sig_Data_Toolbar_widget)
        self.ui.freq_mplToolbar.setGeometry(QtCore.QRect(0, 0, self.ui.Freq_Sig_Data_Toolbar_widget.size().width(), 25))
        self.ui.freq_mplToolbar.setParent(self.ui.Freq_Sig_Data_Toolbar_widget)

    def generate_time_sweep_points(self):
        """
        generate the sweep points based on the parameter
        :return: None
        """
        start_time = float(self.ui.Time_bin_width_lineEdit.text())/1000
        end_time = start_time * float(self.ui.Time_bin_num_lineEdit.text())
        loop_num = int(self.ui.Pulse_Tloops_lineEdit.text())
        time_step_num = int(self.ui.Time_bin_num_lineEdit.text())
        self.time_sweep = list(np.linspace(start_time, end_time, time_step_num))
        self.time_sig = np.random.randint(0, 5, size=(loop_num, time_step_num))
        self.time_sig_ave = list(np.average(self.time_sig, axis=0))

    def generate_time_sweep_points_and_replot(self):
        """
        Generate the sweep point and replot the plot for Data
        :return: None
        """
        self.generate_time_sweep_points()
        self.replot_time_data()
        self.ui.statusbar.showMessage('Successfully replot the figure!')

    def generate_freq_sweep_points(self, freq_list):
        loop_num = int(self.ui.Pulse_Tloops_lineEdit.text())
        self.freq_sweep = freq_list
        freq_step_num = len(self.freq_sweep)
        self.freq_sig = np.random.randint(0, 1, size=(loop_num, freq_step_num))
        self.freq_sig_ave = list(np.average(self.freq_sig, axis=0))

    @QtCore.pyqtSlot()
    def open_pulse_seq(self):
        current_path = os.path.dirname(os.path.abspath(__file__))
        Seq_path = 'config/PulseSeq'
        directory = os.path.join(os.path.dirname(os.path.dirname(current_path)), Seq_path)
        location, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose PulseSeq File', directory)
        if location != '':
            self.load_pulse_seq(location)

    # Methods for Pulse Group
    def load_pulse_seq(self, seq_dir):
        """
        This method load the Pulse Seq, change the name display in textbox.
        This method will also update the plot for Pulse Sequence.
        :param seq_dir: The absolute dir of the Pulse Sequence txt file
        :return: None
        """
        dir_pulse_seq_load = seq_dir
        # Load Sequence
        if dir_pulse_seq_load != '':
            # Record the dir
            self.seq_dir = dir_pulse_seq_load
            with (open(dir_pulse_seq_load, 'r') as f_pulse_seq_load):
                self.pulse_seq = {}
                for each_pulse in f_pulse_seq_load.readlines():
                    if each_pulse[-1] == '\n':
                        value = each_pulse[:-1].replace('[', '').replace(']', '').replace(' ', '').split(', ')
                        value = value[0].replace("'", '').replace("'", '').split(',')
                        key = value[0]
                        self.pulse_seq[key] = value
        print('load successful')
        print('Pulse Sequence:', self.pulse_seq)
        # Load the name of seq
        self.pulse_name = dir_pulse_seq_load.split('/')[-1].replace('.txt', '')
        # print("pulse seq:", self.pulse_seq)
        self.ui.Seq_label.setText(self.pulse_name)

    def load_freq_list(self):
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_path = 'config/config_lifetime_freq_list.yaml'
        CONFIG_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        self.config_lifetime_freq_list = load_config(config_path=CONFIG_file)
        self.generate_freq_list()

    def generate_freq_list(self):
        self.freq_sweep = self.config_lifetime_freq_list['freq_list']['freq']
        print("freq_list:", self.freq_sweep)
        self.ui.rB_load.setChecked(True)
        self.ui.rB_unload.setChecked(False)
        self.ui.Freq_list_Load_pushButton.setEnabled(False)
        self.ui.Freq_list_UnLoad_pushButton.setEnabled(True)

    def unload_freq_list(self):
        self.freq_sweep = None
        self.ui.rB_load.setChecked(False)
        self.ui.rB_unload.setChecked(True)
        self.ui.Freq_list_Load_pushButton.setEnabled(True)
        self.ui.Freq_list_UnLoad_pushButton.setEnabled(False)

    def load_fit_parameter(self):
        current_path = os.path.dirname(os.path.abspath(__file__))
        config_path = 'config/config_lifetime_fit.yaml'
        CONFIG_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        self.config_lifetime_fit = load_config(config_path=CONFIG_file)
        self.generate_fit_parameter()

    def generate_fit_parameter(self):
        self.a_fit = self.config_lifetime_fit['fit_parameter']['a_fit']
        self.phi_fit = self.config_lifetime_fit['fit_parameter']['phi_fit']
        self.b_fit = self.config_lifetime_fit['fit_parameter']['b_fit']
        self.ui.rB_fit_load.setChecked(True)
        self.ui.rB_fit_unload.setChecked(False)
        self.ui.Fit_Load_pushButton.setEnabled(False)
        self.ui.Fit_UnLoad_pushButton.setEnabled(True)

    def unload_fit_parameter(self):
        self.a_fit = None
        self.phi_fit = None
        self.b_fit = None
        self.ui.rB_fit_load.setChecked(False)
        self.ui.rB_fit_unload.setChecked(True)
        self.ui.Fit_Load_pushButton.setEnabled(True)
        self.ui.Fit_UnLoad_pushButton.setEnabled(False)

    def init_raw_time_data(self):
        """
        Init the raw data for the scan.
        This method will also write the scanning parameters at the beginning of the data
        :param.
            True for Frequency Sweep
            False for Time Sweep
        :return: None
        """
        # Init a new list fpr raw data
        self.tdThread.raw = []
        # Create raw data list for Frequency Sweep Settings
        self.tdThread.raw.append(['DATA_VERSION:', '2.1'])
        self.tdThread.raw.append(['Pulse_sequence:', self.data_seq])
        self.tdThread.raw.append(['Experiment time:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                                  'Scanning Mode:', 'Time Sweep'])
        self.tdThread.raw.append(['Total Loop:', self.ui.Pulse_Tloops_lineEdit.text(),
                                 'Point per loop:', self.ui.Time_bin_num_lineEdit.text(),
                                 'Seq Repeat time:', self.ui.Pulse_Taverage_lineEdit.text()])
        self.tdThread.raw.append(['Loop:', '0', 'Point:', '0'])
        self.tdThread.raw.append(['Data Mode:', 'Linear'])
        self.tdThread.raw.append(['Signal', 'Time (ns)', 'Loop Num'])
        self.tdThread.raw.append(np.zeros((int(self.ui.Pulse_Tloops_lineEdit.text()),
                                            int(self.ui.Time_bin_num_lineEdit.text()),
                                            int(3)),
                                            dtype=float).tolist()
                                 )

    def init_raw_freq_data(self):
        """
        Init the raw data for the freq scan.
        This method will also write the scanning parameters at the beginning of the data
        :param.
            True for Frequency Sweep
            False for Time Sweep
        :return: None
        """
        # Init a new list fpr raw data
        self.fdThread.raw = []
        # Create raw data list for Frequency Sweep Settings
        self.fdThread.raw.append(['DATA_VERSION:', '2.1'])
        self.fdThread.raw.append(['Pulse_sequence:', self.data_seq])
        self.fdThread.raw.append(['Experiment time:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                                  'Scanning Mode:', 'freq Sweep'])
        self.fdThread.raw.append(['Total Freq:', len(self.freq_sweep),
                                 'Loop per Freq:', self.ui.Pulse_Tloops_lineEdit.text(),
                                 'Seq Repeat time:', self.ui.Pulse_Taverage_lineEdit.text()])
        self.fdThread.raw.append(['Loop:', '0', 'Point:', '0'])
        self.fdThread.raw.append(['Data Mode:', 'log'])
        self.fdThread.raw.append(['Modulation Amplitude', 'Loop Num', 'freq (kHz)'])
        self.fdThread.raw.append(np.zeros((int(len(self.freq_sweep)),
                                            int(self.ui.Pulse_Tloops_lineEdit.text()),
                                            int(3)),
                                            dtype=float).tolist()
                                 )

    def generate_data_seq(self):
        self.data_seq = []
        for key, value in self.pulse_seq.items():
            self.data_seq.append(value)
        self.data_seq = self.data_seq[:-2]

    def generate_freq_data_seq(self):
        self.data_seq = [['Laser', '0', '10'], ['Sig', '0', '10']]

    # Methods for Data Group
    def save_time_data(self):
        """
        This methods save let the user choose the location, and save the txt data
        :return: None
        """
        # Move the dir to 'Cache/Data' (default location for saving data)
        os.chdir(r"C:\zjh\experiment data")
        # Call the dialog for saving data, get dir from it
        dir_save_data = QtWidgets.QFileDialog.getSaveFileName(self, 'save data',
                                                              time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                                                        'Text (*.txt)')
        # Reshape the dir
        dir_save_data = str(dir_save_data[0].replace('/', '\\'))
        self.write_time_data(dir_save_data)

    def write_time_data(self,dir_save_data):
        # Get the Raw Data from DataThread
        try:
            self.saved_time_data = self.tdThread.raw
            if self.saved_time_data is None:
                raise BaseException
        except BaseException:
            sys.stderr.write('No data to be saved!\n')
            return
        # Save Data
        if dir_save_data != '':
            with open(dir_save_data, 'w') as f_save_data:
                # Write Data Version, Pulse Sequence, Experiment time, Scanning Mode, Total Loop Number, Point per
                # loop, Seq repeat time and tittle of the data at the beginning of the data file.
                for each_description in self.saved_time_data[:7]:
                    for i in range(len(each_description)):
                        f_save_data.write(str(each_description[i]))
                        f_save_data.write('\t')
                    f_save_data.write('\n')
                # Write Data into the txt file
                for each_dataloop in self.saved_time_data[7]:
                    for each_datapoint in each_dataloop:
                        f_save_data.write(str(each_datapoint[0]) + '\t' + str(each_datapoint[1]) + '\t' +
                                          str(each_datapoint[2]) + '\n')
        else:
            sys.stderr.write('No File is saved!\n')
        # Move the dir back to the dir that the Main Thread belongs to
        os.chdir(os.path.dirname(__file__))

    # Methods for Data Group
    def save_freq_data(self):
        """
        This methods save let the user choose the location, and save the txt data
        :return: None
        """
        # Get the Raw Data from DataThread
        try:
            self.saved_freq_data = self.fdThread.raw
            if self.saved_freq_data is None:
                raise BaseException
        except BaseException:
            sys.stderr.write('No data to be saved!\n')
            return

        # Move the dir to 'Cache/Data' (default location for saving data)
        os.chdir(r"C:\zjh\experiment data")
        # Call the dialog for saving data, get dir from it
        dir_save_data = QtWidgets.QFileDialog.getSaveFileName(self, 'save data',
                                                              time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                                                        'Text (*.txt)')
        # Reshape the dir
        dir_save_data = str(dir_save_data[0].replace('/', '\\'))
        # Save Data
        if dir_save_data != '':
            with open(dir_save_data, 'w') as f_save_data:
                # Write Data Version, Pulse Sequence, Experiment time, Scanning Mode, Total Loop Number, Point per
                # loop, Seq repeat time and tittle of the data at the beginning of the data file.
                for each_description in self.saved_freq_data[:7]:
                    for i in range(len(each_description)):
                        f_save_data.write(str(each_description[i]))
                        f_save_data.write('\t')
                    f_save_data.write('\n')
                # Write Data into the txt file
                for each_dataloop in self.saved_freq_data[7]:
                    for each_datapoint in each_dataloop:
                        f_save_data.write(str(each_datapoint[0]) + '\t' + str(each_datapoint[1]) + '\t' +
                                            str(each_datapoint[2]) + '\n')
        else:
            sys.stderr.write('No File is saved!\n')
        # Move the dir back to the dir that the Main Thread belongs to
        os.chdir(os.path.dirname(__file__))

    # Methods for Data Thread
    @QtCore.pyqtSlot(list)
    def update_base_on_data(self, sig):
        """
        Replot the Data Plot based on data
        :param sig: Signal Data (list)
        :return: None
        """
        # self.ref_ave = ref
        self.time_sig_ave = sig
        self.replot_time_data()

    def replot_time_data(self):
        """
        Replot the data plot.
        :return: None
        """
        # self.ref_plot.set_data(self.freq_sweep, self.ref_ave)
        self.time_sig_plot.set_data(self.time_sweep, self.time_sig_ave)
        self.ui.time_data_fig.axes.set_xlabel('time (ns)')
        self.ui.time_data_fig.axes.set_ylabel('Counts')
        self.ui.time_data_fig.axes.set_xlim(np.min(self.time_sweep), np.max(self.time_sweep))
        self.ui.time_data_fig.axes.set_xscale("linear")

        self.ui.time_data_fig.axes.set_ylim(np.min(self.time_sig_ave) -
                                            np.ptp(self.time_sig_ave) * 0.05,
                                            np.max(self.time_sig_ave) +
                                            np.ptp(self.time_sig_ave) * 0.05)
        self.ui.time_data_fig.draw()
        self.ui.statusbar.showMessage('Successfully replot the figure!')
        print('Successfully replot the figure!')

    # Methods for Data Thread
    @QtCore.pyqtSlot(list)
    def update_base_on_freq_data(self, sig):
        """
        Replot the Data Plot based on data
        :param sig: Signal Data (list)
        :return: None
        """
        # self.ref_ave = ref
        self.freq_sig_ave = sig
        self.replot_freq_data()

    def replot_freq_data(self):
        """
        Replot the data plot.
        :return: None
        """
        # self.ref_plot.set_data(self.freq_sweep, self.ref_ave)
        self.freq_sig_plot.set_data(self.freq_sweep, self.freq_sig_ave)
        self.ui.freq_data_fig.axes.set_xlabel('freq (kHz)')
        self.ui.freq_data_fig.axes.set_ylabel('Modulation Amplitude')
        self.ui.freq_data_fig.axes.set_xlim(np.min(self.freq_sweep), np.max(self.freq_sweep))
        self.ui.freq_data_fig.axes.set_xscale("log")

        self.ui.freq_data_fig.axes.set_ylim(np.min(self.freq_sig_ave) -
                                            np.ptp(self.freq_sig_ave) * 0.05,
                                            np.max(self.freq_sig_ave) +
                                            np.ptp(self.freq_sig_ave) * 0.05)
        self.ui.freq_data_fig.draw()
        self.ui.statusbar.showMessage('Successfully replot the figure!')

    # Methods for Hardware Group
    @QtCore.pyqtSlot()
    def init_hardware(self):
        """
        Init all hardware and pass them to Threads
        :return:
        """
        self.ui.statusbar.showMessage('Initializing Hardware...')
        try:
            # Initialize Threads
            # Initialize Data Thread
            self.tdThread = TimeDataThread()
            self.tdThread.update.connect(self.update_base_on_data)
            self.fdThread = FreqDataThread()
            self.fdThread.update.connect(self.update_base_on_freq_data)
            # Initialize freq sweep thread
            self.tsThread = TimeSweepThread(self.hardware)
            self.tsThread.update.connect(self.tcspc_exp_data_back)
            self.tsThread.finished.connect(self.time_scan_stop)
            self.fsThread = FreqSweepThread(self.hardware)
            self.fsThread.updatestate.connect(self.freq_scan_state_update)
            self.fsThread.update.connect(self.freq_exp_data_back)
            self.fsThread.track.connect(self.auto_track_function)
            self.fsThread.finished.connect(self.time_scan_stop)

        except BaseException as e:
            print(e)
            self.ui.statusbar.showMessage('Hardware Initialization Failed')
            return
        # Enable Buttons
        # Track Group
        self.ui.Track_Auto_Track_checkbox.setEnabled(True)
        # pulse Group
        self.ui.Seq_Load_pushButton.setEnabled(True)
        self.ui.Freq_list_Load_pushButton.setEnabled(True)
        # Exp Group
        self.ui.TCSPC_Experiment_Start_pushButton.setEnabled(True)
        self.ui.Freq_Experiment_Start_pushButton.setEnabled(True)
        # Sequence Group
        self.ui.cB_Sin.setEnabled(True)
        self.ui.cB_SelfDefine.setEnabled(True)
        # Change the Status Bar Message
        self.ui.statusbar.showMessage('Hardware Initialized Successfully')

    # Methods for Exp Group
    def tcspc_start_scan(self):
        """
        This Method Start the Scan.
        :return: None
        """
        self.tcspc_scan_setting()
        # Set Button enable state
        self.ui.TCSPC_Experiment_Stop_pushButton.setEnabled(True)
        self.ui.TCSPC_Experiment_Start_pushButton.setEnabled(False)
        self.ui.Freq_Experiment_Stop_pushButton.setEnabled(False)
        self.ui.Freq_Experiment_Start_pushButton.setEnabled(False)
        # Init current state display
        self.ui.Scan_Cloop_lineEdit.setText('0')
        self.ui.Scan_CFloop_lineEdit.setText('1')
        # Disable text box
        # Time Group
        # Scanning Status
        self.ui.Pulse_Tloops_lineEdit.setEnabled(False)
        self.ui.Pulse_Taverage_lineEdit.setEnabled(False)
        # data status
        self.ui.Time_Data_Save_pushButton.setEnabled(True)
        self.ui.Freq_Data_Save_pushButton.setEnabled(False)

    def tcspc_scan_setting(self):
        self.pause_status = False  # Set the pause state
        self.generate_time_sweep_points_and_replot()
        # Init all the data
        self.generate_data_seq()
        self.init_raw_time_data()
        self.tdThread.sig_all = []
        self.tdThread.time_arr = self.time_sweep
        self.tdThread.loop_old = -1
        # Set parameters based on scan mode
        # Set scan parameters
        # These will not change in one experiment
        self.tsThread.bin_width = int(self.ui.Time_bin_width_lineEdit.text())
        self.tsThread.bin_num = int(self.ui.Time_bin_num_lineEdit.text())
        self.tsThread.pulse_form = self.pulse_seq
        # These can be changed when pause/resume the experiment
        self.tsThread.loop_num = [0, int(self.ui.Pulse_Tloops_lineEdit.text())]
        self.tsThread.average_num = int(self.ui.Pulse_Taverage_lineEdit.text())
        # These can be changed during the experiment
        self.tsThread.self_define = self.ui.cB_SelfDefine.isChecked()
        self.tsThread.sin = self.ui.cB_Sin.isChecked()
        self.tsThread.freq = int(self.ui.Freq_num.text()) * 1e3
        # Start fsThread
        self.tsThread.start()
        print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    @QtCore.pyqtSlot()
    def tcspc_stop_scan(self):
        """
        Call this method when push the stop button.
        If the Scan Thread is in pause status, the methods will change the status first,
        then call self.scan_stop() to initial the button status.
        :return: None
        """
        if self.pause_status is True:
            self.pause_status = False
        self.time_scan_stop()

    # Methods for Sweep Threads
    @QtCore.pyqtSlot(np.ndarray, int)
    def tcspc_exp_data_back(self, sig, loop_num):
        """
        Pass the data that Scan Thread send back to Data Thread
        :param sig: Signal Counts  (int)
        :param loop_num: Number of loop (int)
        :return: None
        """
        self.tsThread.pause = False
        self.tdThread.sig = sig
        self.tdThread.loop = loop_num
        self.tdThread.sig_ave_temp = self.time_sig_ave
        self.tdThread.start()
        self.ui.Scan_Cloop_lineEdit.setText(str(loop_num + 1))
        print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    # Methods for Sweep Threads
    @QtCore.pyqtSlot(np.ndarray, int, int)
    def freq_exp_data_back(self, sig, loop_num, freq_num):
        """
        Pass the data that Scan Thread send back to Data Thread
        :param sig: Signal Counts  (int)
        :param loop_num: Number of loop (int)
        :return: None
        """
        print("data back")
        self.fsThread.pause = False

        self.tdThread.sig = sig
        self.tdThread.loop = loop_num
        self.tdThread.sig_ave_temp = self.time_sig_ave
        self.tdThread.start()

        self.fdThread.sig = sig
        self.fdThread.loop = loop_num
        self.fdThread.freq_index = freq_num
        self.fdThread.sig_ave_temp = self.freq_sig_ave
        self.fdThread.start()

        self.ui.Scan_Cloop_lineEdit.setText(str(loop_num + 1))
        self.ui.Scan_CFloop_lineEdit.setText(str(freq_num + 1))

        print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    @QtCore.pyqtSlot()
    def time_scan_stop(self):
        """
        Call this method when scan thread end
        If the Scan Thread end with pause status, the methods will do nothing
        if the Scan Thread end directly, the method will initial the button status
        :return: None
        """
        # print(1)
        # If in Pause Status, do nothing
        if self.pause_status is True:
            return
        # print(1)
        # Set the running status of the Scanning Thread
        self.tsThread.running_status = False
        self.fsThread.running_status = False
        # Set Start Button
        self.ui.TCSPC_Experiment_Stop_pushButton.setEnabled(False)
        self.ui.TCSPC_Experiment_Start_pushButton.setEnabled(True)
        self.ui.Freq_Experiment_Start_pushButton.setEnabled(True)
        self.ui.Freq_Experiment_Stop_pushButton.setEnabled(False)
        # Track Group
        self.ui.Track_Auto_Track_checkbox.setEnabled(True)
        # Time Group
        self.ui.Time_bin_num_lineEdit.setEnabled(True)
        self.ui.Time_bin_width_lineEdit.setEnabled(True)
        # Scanning Status
        self.ui.Pulse_Tloops_lineEdit.setEnabled(True)
        self.ui.Pulse_Taverage_lineEdit.setEnabled(True)

    @QtCore.pyqtSlot()
    def freq_start_scan(self):
        # judge freq list whether is load
        if self.ui.rB_load.isChecked() is False:
            print("please load freq list for freq scan!")
            self.time_scan_stop()

        if self.ui.rB_fit_load.isChecked() is False:
            print("please load fit parameter for freq scan!")
            self.time_scan_stop()
        # generate save pave for time sig
        directory = os.path.dirname(os.path.abspath(__file__))
        location,_ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose Save File', directory)
        self.auto_save_location = os.path.dirname(location)
        print(self.auto_save_location)
        # setup parameter
        self.generate_freq_sweep_points(self.freq_sweep)
        self.replot_freq_data()
        self.generate_freq_data_seq()
        self.init_raw_freq_data()
        self.fsThread.freq_arr = self.freq_sweep
        self.fsThread.loop_num = [0, int(self.ui.Pulse_Tloops_lineEdit.text())]
        self.fsThread.freq_num = [0, np.size(self.freq_sweep)]
        self.fdThread.sig_all = []
        self.tdThread.sig_all = []
        self.fdThread.freq_arr = self.freq_sweep
        self.fdThread.loop_old = -1
        self.tdThread.loop_old = -1
        self.ui.Time_bin_num_lineEdit.setText('400')
        self.fsThread.bin_num = int(self.ui.Time_bin_num_lineEdit.text())
        # start scan
        self.fsThread.start()
        # button state
        self.ui.TCSPC_Experiment_Stop_pushButton.setEnabled(False)
        self.ui.TCSPC_Experiment_Start_pushButton.setEnabled(False)
        self.ui.Freq_Experiment_Stop_pushButton.setEnabled(True)
        self.ui.Freq_Experiment_Start_pushButton.setEnabled(False)
        self.ui.Pulse_Tloops_lineEdit.setEnabled(False)
        self.ui.Pulse_Taverage_lineEdit.setEnabled(False)
        self.ui.Time_Data_Save_pushButton.setEnabled(False)
        self.ui.Freq_Data_Save_pushButton.setEnabled(True)

    @QtCore.pyqtSlot(int, int, int)
    def freq_scan_state_update(self, freq, average_num, bin_width):
        # set text
        self.ui.Freq_num.setText(str(freq))
        self.ui.Pulse_Taverage_lineEdit.setText(str(average_num))
        self.ui.Time_bin_width_lineEdit.setText(str(bin_width))
        # print("Freq Scan set finish!")
        # further init fdThread
        self.generate_time_sweep_points_and_replot()
        # Init all the data
        self.generate_freq_data_seq()
        self.init_raw_time_data()
        self.fdThread.time_arr = self.time_sweep
        self.tdThread.time_arr = self.time_sweep
        self.fdThread.initial_fit_parameter = [self.a_fit,freq,self.phi_fit,self.b_fit]
        self.fsThread.state_pause = False

    @QtCore.pyqtSlot(int)
    def auto_track_function(self, freq_num):
        # print("Current frequency number:", freq_num + 1)
        print("prepare to track and save time signal!")
        # track
        if self.ui.Track_Auto_Track_checkbox.isChecked() is True:
            self.hardware.pulser.all_constant([0], analog_0=1.0)
            self.use_track_function()
            time.sleep(10)
            # self.hardware.pulser.init_ps()
        # auto save time signal
        try:
            self.auto_save_time_sig(self.freq_sweep[freq_num])
        except BaseException as e:
            print(e)
            return
        self.fsThread.track_pause = False

    def auto_save_time_sig(self, freq):
        file_name = 'freq_' + str(freq) +'_kHz.txt'
        save_path = os.path.join(self.auto_save_location, file_name)
        # print(save_path)
        self.write_time_data(save_path)
        self.hardware.pulser.init_ps()

    def use_track_function(self):
        """
        communication with track interface
        use track function to track the diamond position
        :return:
        """
        self.track_interface.track_max_count()

    @QtCore.pyqtSlot()
    def freq_stop_scan(self):
        """
        Call this method when push the stop button.
        If the Scan Thread is in pause status, the methods will change the status first,
        then call self.scan_stop() to initial the button status.
        :return: None
        """
        if self.pause_status is True:
            self.pause_status = False
        self.time_scan_stop()

    @QtCore.pyqtSlot(QtCore.QEvent)
    def closeEvent(self, event):
        """
        When close the event, ask if to save the Defaults
        :param event:
        :return: None
        """
        quit_message = 'Save parameters as Defaults?'
        reply = QtWidgets.QMessageBox.question(self, 'Message', quit_message, QtWidgets.QMessageBox.Save |
                                               QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if reply == QtWidgets.QMessageBox.Save:
            self.ExpLifetimeClose.emit()
            event.accept()
        elif reply == QtWidgets.QMessageBox.Discard:
            self.ExpLifetimeClose.emit()
            event.accept()
        else:
            event.ignore()

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