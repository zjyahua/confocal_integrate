"""
Created on Feb 11, 2023

This File is the Main Thread for process the confocal Scan image

@author: Jiahua
"""
import sys
import os
import time
from symbol import import_from

import yaml
import tempfile

from ui.uipy.scan_image_deal.confocal_scan_image_deal import Ui_MainWindow
from PyQt5 import QtWidgets, QtCore

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib import colormaps
from matplotlib.widgets import Cursor
from src.fitting_method.Lifetime_fit import Lifetime_fitting as lf
from src.fitting_method.sin_fit import sin_fit as sf

class mainGUI(QtWidgets.QMainWindow):
    SIGNAL_Data_Image_Close = QtCore.pyqtSignal(name='Data_Image_Close')
    CACHE_LIFE = 7  # days

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        # Setup GUI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache\\confocal")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.scanning_cache = {
            "piezo_plot": tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False),
            "piezo_raw": tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False),
        }
        # Define some parameters need to be used in the program
        # self.APD_Counts = []
        # cursor
        self.cursor = None
        self.curh = None
        self.curv = None
        self.image = None
        self.map = None
        self.mapColor = None
        self.cbar = None
        self.saved_data = None
        self.xArr = None
        self.yArr = None
        self.x_arr = None
        self.raw_image = None
        self.raw_reshape_image = None
        self.intensity_map = None
        self.x_data = None
        self.y_data = None
        self.time_data_pixel = None
        self.time_sig = None
        self.fit_curve = None
        self.time_sweep = None
        self.time_sig_plot = None
        self.fit_plot = None
        self.calculation_map = None
        self.cal_mapColor = None
        self.min_cal_map = None
        self.max_cal_map = None
        # Process for initialization
        # Hardware
        # Load defaults
        self.load_defaults()
        # init intensity group image
        self.init_image_plot()  # Init the plot for Scan image
        self.init_toolbar_set()  # Init the toolbar
        self.init_cursor_line()  # Init the cursor
        # init cal group image
        self.init_cal_image_plot() # Init the cal image
        self.init_cal_toolbar_set() # init the cal toolbar
        # init pixel curve
        self.generate_time_sweep_points()
        self.init_pixel_curve_plot()
        self.init_pixel_toolbar_set()
        # button setup
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

        # Intensity Image Group
        self.ui.pbResetPlot.clicked.connect(self.replot_image)
        self.ui.pbSavedata.clicked.connect(self.save_data)
        self.ui.vsMax.sliderMoved.connect(self.modify_image)

        # Calculate Image Group
        self.ui.pbResetPlot_cal.clicked.connect(self.replot_image_cal)
        self.ui.pbSavedata_cal.clicked.connect(self.save_data_cal)
        self.ui.vsMax_cal_image.sliderMoved.connect(self.modify_image_cal)

        # Pixel Control Group
        self.ui.pbNewCursor.clicked.connect(self.new_cursor)
        self.ui.pbShowCursor.clicked.connect(self.show_cursor)
        self.ui.pbHideCursor.clicked.connect(self.hide_cursor)

        # Pixel fit Group
        self.ui.pb_plot.clicked.connect(self.plot_curve)
        self.ui.pb_fit.clicked.connect(self.fit_data)

        # Cal Group
        self.ui.pb_load_data.clicked.connect(self.load_data)
        self.ui.pb_cal.clicked.connect(self.cal_fun_image)


    def init_button_status(self):
        """
        This method set the state of buttons and textbox to initial state.
        :return: None
        """
        # Image Group
        self.ui.pbResetPlot.setEnabled(False)
        self.ui.pbSavedata.setEnabled(False)
        self.ui.vsMax.setEnabled(False)

        # Position Control Group
        self.ui.pbNewCursor.setEnabled(False)
        self.ui.pbHideCursor.setEnabled(False)
        self.ui.pbShowCursor.setEnabled(False)

    def init_image_plot(self):
        """
        Init the plot for image.
        :return: None
        """
        fig = Figure()
        self.ui.mplMap = FigureCanvas(fig)
        self.ui.mplMap.setParent(self.ui.widgetImage)
        self.ui.mplMap.axes = fig.add_subplot(111)
        self.ui.mplMap.setGeometry(QtCore.QRect(QtCore.QPoint(0, 0), self.ui.widgetImage.size()))

        # Initialize Dump Map Data
        xnum = int((float(self.ui.lexscanend.text()) - float(self.ui.lexscanstart.text())) /
                   float(self.ui.lexscanstep.text()))
        ynum = int((float(self.ui.leyscanend.text()) - float(self.ui.leyscanstart.text())) /
                   float(self.ui.leyscanstep.text()))
        self.map = np.random.randint(0, 100, size=(ynum, xnum))

        # Initialize Map
        self.mapColor = 'gist_earth'
        self.image = self.ui.mplMap.axes.imshow(self.map, cmap=colormaps.get_cmap(self.mapColor),
                                                vmin=0, vmax=self.map.max(),
                                                extent=[float(self.ui.lexscanstart.text()),
                                                        float(self.ui.lexscanend.text()),
                                                        float(self.ui.leyscanstart.text()),
                                                        float(self.ui.leyscanend.text())],
                                                interpolation='nearest',
                                                origin='lower')
        self.ui.mplMap.axes.set_ylim([float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.mplMap.axes.set_xlim([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text())])
        self.cbar = self.ui.mplMap.figure.colorbar(self.image, fraction=0.045, pad=0.05)
        # self.ui.mplMap.figure.tight_layout()
        self.ui.mplMap.figure.subplots_adjust(top=0.935, bottom=0.089, left=0.221, right=0.817)

    def init_toolbar_set(self):
        """
        Init the toolbar for image
        Returns: None
        """
        self.ui.mplToolbar = NavigationToolbar(self.ui.mplMap, self.ui.widgetToolbar)
        self.ui.mplToolbar.setGeometry(QtCore.QRect(0, 0, self.ui.widgetToolbar.size().width(), 25))
        self.ui.mplToolbar.setParent(self.ui.widgetToolbar)

    def init_cal_image_plot(self):
        """
        Init the plot for image.
        :return: None
        """
        fig_cal = Figure()
        self.ui.calMap = FigureCanvas(fig_cal)
        self.ui.calMap.setParent(self.ui.widget_cal_image)
        self.ui.calMap.axes = fig_cal.add_subplot(111)
        self.ui.calMap.setGeometry(QtCore.QRect(QtCore.QPoint(0, 0), self.ui.widget_cal_image.size()))

        # Initialize Dump Map Data
        xnum = int((float(self.ui.lexscanend.text()) - float(self.ui.lexscanstart.text())) /
                   float(self.ui.lexscanstep.text()))
        ynum = int((float(self.ui.leyscanend.text()) - float(self.ui.leyscanstart.text())) /
                   float(self.ui.leyscanstep.text()))
        self.cal_map = np.random.randint(0, 100, size=(ynum, xnum))

        # Initialize Map
        self.cal_mapColor = 'jet'
        self.cal_image = self.ui.calMap.axes.imshow(self.cal_map, cmap=colormaps.get_cmap(self.cal_mapColor),
                                                    vmin=0, vmax=self.cal_map.max(),
                                                    extent=[float(self.ui.lexscanstart.text()),
                                                        float(self.ui.lexscanend.text()),
                                                        float(self.ui.leyscanstart.text()),
                                                        float(self.ui.leyscanend.text())],
                                                    interpolation='nearest',
                                                    origin='lower')
        self.ui.calMap.axes.set_ylim([float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.calMap.axes.set_xlim([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text())])
        self.cal_cbar = self.ui.calMap.figure.colorbar(self.cal_image, fraction=0.045, pad=0.05)
        # self.ui.calMap.figure.tight_layout()
        self.ui.calMap.figure.subplots_adjust(top=0.935, bottom=0.089, left=0.221, right=0.817)

    def init_cal_toolbar_set(self):
        """
        Init the toolbar for image
        Returns: None
        """
        self.ui.calToolbar = NavigationToolbar(self.ui.calMap, self.ui.widget_cal_Toolbar)
        self.ui.calToolbar.setGeometry(QtCore.QRect(0, 0, self.ui.widget_cal_Toolbar.size().width(), 25))
        self.ui.calToolbar.setParent(self.ui.widget_cal_Toolbar)

    def init_pixel_curve_plot(self):
        """
        Init the plot for pixel curve.
        :return: None
        """
        # Set canvas
        fig1 = Figure()
        self.ui.time_data_fig = FigureCanvas(fig1)
        self.ui.time_data_fig.setParent(self.ui.widget_line_curve)
        self.ui.time_data_fig.setGeometry(QtCore.QRect(QtCore.QPoint(0, 0), self.ui.widget_line_curve.size()))
        self.ui.time_data_fig.axes = self.ui.time_data_fig.figure.add_subplot(111)
        self.ui.time_data_fig.figure.subplots_adjust(top=0.896, bottom=0.386, left=0.126, right=0.923)
        # Init plot
        self.time_sig_plot, = self.ui.time_data_fig.axes.plot(self.time_sweep, self.time_sig, 'b',linewidth = '0.5')
        self.fit_plot, = self.ui.time_data_fig.axes.plot(self.time_sweep, self.fit_curve, 'k', linewidth = '2')
        # Set fig parameters
        self.ui.time_data_fig.axes.set_xlabel('time (ns)')
        self.ui.time_data_fig.axes.set_ylabel('Counts')
        self.ui.time_data_fig.axes.legend(('fit', 'sig'), fontsize=6.5, loc='upper left')
        self.ui.time_data_fig.axes.set_xlim(np.min(self.time_sweep), np.max(self.time_sweep))
        self.ui.time_data_fig.draw()

    def init_pixel_toolbar_set(self):
        """
        Init the toolbar for pixel curve
        Returns: None
        """
        self.ui.time_mplToolbar = NavigationToolbar(self.ui.time_data_fig, self.ui.widget_line_Toolbar)
        self.ui.time_mplToolbar.setGeometry(QtCore.QRect(0, 0, self.ui.widget_line_Toolbar.size().width(), 25))
        self.ui.time_mplToolbar.setParent(self.ui.widget_line_Toolbar)

    def generate_time_sweep_points(self):
        """
        generate the sweep points based on the parameter
        start time unit ns
        :return: None
        """
        start_time = float(self.ui.Time_bin_width_lineEdit.text())/1000
        end_time = start_time * float(self.ui.Time_bin_num_lineEdit.text())
        time_step_num = int(self.ui.Time_bin_num_lineEdit.text())
        self.time_sweep = list(np.linspace(start_time, end_time, time_step_num))
        self.time_sig = np.random.randint(0, 5, size=time_step_num)
        self.fit_curve = np.zeros(time_step_num)

    def init_cursor_line(self):
        # Initialize Cursor Lines
        self.cursor = None
        self.curh = self.ui.mplMap.axes.axhline(color='red', linewidth=1, visible=False)
        self.curh.set_ydata((float(self.ui.leYCursorSet.text()), float(self.ui.leYCursorSet.text())))
        self.curv = self.ui.mplMap.axes.axvline(color='red', linewidth=1, visible=False)
        self.curv.set_xdata((float(self.ui.leXCursorSet.text()), float(self.ui.leXCursorSet.text())))

    # Load and Save defaults
    @QtCore.pyqtSlot()
    def open_defaults(self):
        directory = os.path.dirname(os.path.abspath(__file__))
        location, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose Defaults File', directory)
        if location != '':
            self.load_defaults(location)

    def load_defaults(self, config_path='config/config_confocal_image_scan_deal.yaml'):
            current_path = os.path.dirname(os.path.abspath(__file__))
            CONFIG_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
            self.config_confocal = load_config(config_path=CONFIG_file)
            self.update_ui_based_on_default()

    @QtCore.pyqtSlot()
    def save_defaults(self, config_path='config/config_confocal_image_scan_deal.yaml'):
        self.update_default_based_on_ui()
        current_path = os.path.dirname(os.path.abspath(__file__))
        CONFIG_file = os.path.join(os.path.dirname(os.path.dirname(current_path)), config_path)
        save_config(config=self.config_confocal, config_path=CONFIG_file)

    def update_ui_based_on_default(self):
        self.ui.lexscanstart.setText(str(self.config_confocal['piezo_scan']['x']['start']))
        self.ui.leyscanstart.setText(str(self.config_confocal['piezo_scan']['y']['start']))
        self.ui.lexscanend.setText(str(self.config_confocal['piezo_scan']['x']['end']))
        self.ui.leyscanend.setText(str(self.config_confocal['piezo_scan']['y']['end']))
        self.ui.lexscanstep.setText(str(self.config_confocal['piezo_scan']['x']['step']))
        self.ui.leyscanstep.setText(str(self.config_confocal['piezo_scan']['y']['step']))
        self.ui.leXCursorSet.setText(str(self.config_confocal['piezo_scan']['cursor']['x']))
        self.ui.leYCursorSet.setText(str(self.config_confocal['piezo_scan']['cursor']['y']))
        self.ui.Time_bin_width_lineEdit.setText(str(self.config_confocal['time_parameter']['bin_width_ps']))
        self.ui.Time_bin_num_lineEdit.setText(str(self.config_confocal['time_parameter']['bin_number']))
        self.ui.Time_Freq_lineEdit.setText(str(self.config_confocal['time_parameter']['Freq_kHz']))
        self.ui.a1_lineEdit.setText(str(self.config_confocal['lifetime_parameter']['a1']))
        self.ui.a2_lineEdit.setText(str(self.config_confocal['lifetime_parameter']['a2']))
        self.ui.lifetime_lineEdit_1.setText(str(self.config_confocal['lifetime_parameter']['t1']))
        self.ui.lifetime_lineEdit_2.setText(str(self.config_confocal['lifetime_parameter']['t2']))
        self.ui.IRF_time_position_lineEdit.setText(str(self.config_confocal['lifetime_parameter']['IRF_t']))
        self.ui.IRF_FWHM_lineEdit.setText(str(self.config_confocal['lifetime_parameter']['IRF_W']))
        self.ui.Background_lineEdit.setText(str(self.config_confocal['Back_parameter']['background']))

    def update_default_based_on_ui(self):
        self.config_confocal['piezo_scan']['x']['start'] = float(self.ui.lexscanstart.text())
        self.config_confocal['piezo_scan']['y']['start'] = float(self.ui.leyscanstart.text())
        self.config_confocal['piezo_scan']['x']['end'] = float(self.ui.lexscanend.text())
        self.config_confocal['piezo_scan']['y']['end'] = float(self.ui.leyscanend.text())
        self.config_confocal['piezo_scan']['x']['step'] = float(self.ui.lexscanstep.text())
        self.config_confocal['piezo_scan']['y']['step'] = float(self.ui.leyscanstep.text())
        self.config_confocal['piezo_scan']['cursor']['x'] = float(self.ui.leXCursorSet.text())
        self.config_confocal['piezo_scan']['cursor']['y'] = float(self.ui.leYCursorSet.text())
        self.config_confocal['time_parameter']['bin_width_ps'] = int(self.ui.Time_bin_width_lineEdit.text())
        self.config_confocal['time_parameter']['bin_number'] = int(self.ui.Time_bin_num_lineEdit.text())
        self.config_confocal['time_parameter']['Freq_kHz'] = int(self.ui.Time_Freq_lineEdit.text())
        self.config_confocal['lifetime_parameter']['a1'] = float(self.ui.a1_lineEdit.text())
        self.config_confocal['lifetime_parameter']['a2'] = float(self.ui.a2_lineEdit.text())
        self.config_confocal['lifetime_parameter']['t1'] = float(self.ui.lifetime_lineEdit_1.text())
        self.config_confocal['lifetime_parameter']['t2'] = float(self.ui.lifetime_lineEdit_2.text())
        self.config_confocal['lifetime_parameter']['IRF_t'] = float(self.ui.IRF_time_position_lineEdit.text())
        self.config_confocal['lifetime_parameter']['IRF_W'] = float(self.ui.IRF_FWHM_lineEdit.text())
        self.config_confocal['Back_parameter']['background'] = int(self.ui.Background_lineEdit.text())

    # Methods for Hardware Group
    @QtCore.pyqtSlot()
    def init_hardware(self):
        """
        Init all hardware and pass them to Threads
        :return:
        """

        self.ui.statusbar.showMessage('Initializing...')
        # Enable Buttons
        # Image Group
        self.ui.pbResetPlot.setEnabled(True)
        self.ui.pbSavedata.setEnabled(True)
        self.ui.vsMax.setEnabled(True)
        # Scan Parameters Group
        # Position Control Group
        self.ui.pbNewCursor.setEnabled(True)
        self.ui.pbShowCursor.setEnabled(True)
        # Change the Status Bar Message
        self.ui.statusbar.showMessage('Initialized Successfully')


    # Position Control Group
    @QtCore.pyqtSlot()
    def new_cursor(self):
        self.hide_cursor()
        try:
            self.cursor = Cursor(self.ui.mplMap.axes, useblit=True, color='red', linewidth=1)
        except BaseException as e:
            print(e)
            return
        self.cursor.connect_event('button_press_event', self.new_cursor_marked)
        self.ui.mplMap.draw()

    @QtCore.pyqtSlot()
    def new_cursor_marked(self, event):
        if event.inaxes and event.x < 450:
            x = round(event.xdata, 3)
            y = round(event.ydata, 3)
            self.ui.leXCursorSet.setText(str(x))
            self.ui.leYCursorSet.setText(str(y))
            self.cursor.disconnect_events()
            self.curh.set_ydata((y, y))
            self.curv.set_xdata((x, x))
            self.show_cursor()
            self.cursor = None

    @QtCore.pyqtSlot()
    def show_cursor(self):
        if self.cursor:
            self.cursor.disconnect_events()
            self.cursor = None
        self.curh.set_visible(True)
        self.curh.set_ydata((float(self.ui.leYCursorSet.text()), float(self.ui.leYCursorSet.text())))
        self.curv.set_visible(True)
        self.curv.set_xdata((float(self.ui.leXCursorSet.text()), float(self.ui.leXCursorSet.text())))
        self.ui.mplMap.draw()
        self.ui.pbShowCursor.setEnabled(False)
        self.ui.pbHideCursor.setEnabled(True)

    @QtCore.pyqtSlot()
    def hide_cursor(self):
        self.cur_vis = False
        self.curh.set_visible(False)
        self.curv.set_visible(False)
        self.ui.mplMap.draw()
        self.ui.pbShowCursor.setEnabled(True)
        self.ui.pbHideCursor.setEnabled(False)

    # Methods for image Group
    @QtCore.pyqtSlot()
    def replot_image(self):
        self.ui.mplMap.figure.clear()
        self.ui.mplMap.axes = self.ui.mplMap.figure.add_subplot(111)

        self.image = self.ui.mplMap.axes.imshow(self.map, cmap=colormaps.get_cmap(self.mapColor),
                                                vmin=0, vmax=self.map.max(),
                                                extent=[float(self.ui.lexscanstart.text()),
                                                        float(self.ui.lexscanend.text()),
                                                        float(self.ui.leyscanstart.text()),
                                                        float(self.ui.leyscanend.text())],
                                                interpolation='nearest',
                                                origin='lower')
        self.ui.mplMap.axes.set_ylim([float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.mplMap.axes.set_xlim([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text())])
        self.cbar = self.ui.mplMap.figure.colorbar(self.image, fraction=0.045, pad=0.05)
        self.ui.mplMap.figure.tight_layout()
        # self.ui.mplMap.figure.subplots_adjust(top=0.95, bottom=0.05, left=0.08, right=0.9)
        self.init_cursor_line()
        self.modify_image()

    @QtCore.pyqtSlot()
    def replot_image_cal(self):
        self.ui.calMap.figure.clear()
        self.ui.calMap.axes = self.ui.calMap.figure.add_subplot(111)

        self.cal_image = self.ui.calMap.axes.imshow(self.cal_map, cmap=colormaps.get_cmap(self.cal_mapColor),
                                                vmin=self.cal_map.min(), vmax=self.cal_map.max(),
                                                extent=[float(self.ui.lexscanstart.text()),
                                                        float(self.ui.lexscanend.text()),
                                                        float(self.ui.leyscanstart.text()),
                                                        float(self.ui.leyscanend.text())],
                                                interpolation='nearest',
                                                origin='lower')
        self.ui.calMap.axes.set_ylim([float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.calMap.axes.set_xlim([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text())])
        self.cal_cbar = self.ui.calMap.figure.colorbar(self.cal_image, fraction=0.045, pad=0.05)
        self.ui.calMap.axes.set_facecolor('black')
        self.ui.calMap.figure.tight_layout()
        # self.ui.mplMap.figure.subplots_adjust(top=0.95, bottom=0.05, left=0.08, right=0.9)
        self.modify_image_cal()

    def save_data(self):
        """
        This methods save let the user choose the location, and save the txt data
        :return: None
        """
        # Get the Raw Data from DataThread
        try:
            # self.saved_data = self.dThread.raw
            self.saved_data = self.map
            if self.saved_data is None:
                raise BaseException
        except BaseException:
            sys.stderr.write('No data to be saved!\n')
            return

        # Move the dir to 'Cache/Data' (default location for saving data)
        os.chdir(r"C:\zjh\experiment data")
        # Call the dialog for saving data, get dir from it
        dir_save_data = QtWidgets.QFileDialog.getSaveFileName(self, 'Enter save file', '', 'Text (*.txt)')
        # Reshape the dir
        dir_save_data = str(dir_save_data[0].replace('/', '\\'))
        # Save Data
        if dir_save_data != '':
            np.savetxt(dir_save_data, self.saved_data, fmt='%.0f')
        else:
            sys.stderr.write('No File is saved!\n')
        # Move the dir back to the dir that the Main Thread belongs to
        os.chdir(os.path.dirname(__file__))

    @QtCore.pyqtSlot()
    def modify_image(self):
        val_max = self.ui.vsMax.value()
        # val_min = self.ui.vsMin.value()
        vmax = self.map.max() * (10 ** ((val_max + 1) / 20)) / 100000
        # vmin = min(self.map.mean(), vmax) * val_min / 100
        self.image.set_clim(0, vmax)
        self.ui.mplMap.draw()

    @QtCore.pyqtSlot()
    def modify_image_cal(self):
        val_max = self.ui.vsMax_cal_image.value()
        # val_min = self.ui.vsMin.value()
        vmax = self.cal_map.max() * (10 ** ((val_max + 1) / 20)) / 100000
        # vmin = min(self.map.mean(), vmax) * val_min / 100
        self.cal_image.set_clim(0, vmax)
        self.ui.calMap.draw()

    def load_data(self):
        self.ui.statusbar.showMessage('Load Data...')
        # Move the dir to 'Cache/Data' (default location for saving data)
        os.chdir(r"C:\zjh\experiment data")
        # Call the dialog for load data, get dir from it
        dir_load_data = QtWidgets.QFileDialog.getOpenFileName(self, 'Load Data', '', 'Text (*.txt)')
        dir_load_data = str(dir_load_data[0].replace('/', '\\'))
        if dir_load_data != '':
            self.x_data, self.y_data, self.time_data_pixel=self.update_data_based_on_dir(dir_load_data)
        # reshape list to np.array
        self.x_arr, self.raw_image = self.reshape_image(self.x_data,self.time_data_pixel)
        # generate intensity image
        self.intensity_map, self.raw_reshape_image = self.generate_intensity_image(self.x_arr, self.raw_image)
        # update image
        self.update_image(self.intensity_map)
        self.ui.statusbar.showMessage('Finish Draw Intensity Image')

    @QtCore.pyqtSlot()
    def update_data_based_on_dir(self, directory):
        with open(directory) as file_raw_data:
            raw_data = file_raw_data.readlines()
            # init data
            x_data = []
            y_data = []
            time_data_pixel = []
            for lines in raw_data:
                data_arr = lines.split()
                x_data.append(float(data_arr[0]))
                y_data.append(float(data_arr[1]))
                time_data_pixel.append(int(data_arr[2]))
        return x_data, y_data, time_data_pixel

    @QtCore.pyqtSlot()
    def reshape_image(self,x,time_list):
        self.yArr = np.arange(float(self.ui.leyscanstart.text()),
                              float(self.ui.leyscanend.text()),
                              float(self.ui.leyscanstep.text()))
        y_length = np.size(self.yArr)
        x_arr = np.zeros((y_length,110))
        num = int(np.size(x) / y_length / 110)
        raw_image = np.zeros((y_length,110,num))
        for j in range(y_length):
            for i in range(110):
                start = i * num + j * num * 110
                raw_image[j, i, :] = time_list[start : start + num]
                x_arr[j,i] = x[start]
        return x_arr, raw_image

    def generate_intensity_image(self, x, raw_image):
        self.xArr = np.arange(float(self.ui.lexscanstart.text()),
                              float(self.ui.lexscanend.text()),
                              float(self.ui.lexscanstep.text()))
        y_length = np.size(self.yArr)
        intensity_map = np.zeros((y_length, 100))
        num = int(np.size(self.x_data) / y_length / 110)
        raw_reshape_image = np.zeros((y_length, 100, num))
        for j in range(y_length):
            picked_counts = []
            for i in range(100):
                x_pos = self.xArr[i]
                # Search self.xData for the closest value
                each_x_arr = np.array([x_pos] * np.size(x[j]))
                diff_arr = list(np.abs(x[j] - each_x_arr))
                closest_index = diff_arr.index(min(diff_arr))
                raw_reshape_image[j,i,:]=raw_image[j,closest_index,:]
                cts_temp = np.sum(raw_image[j,closest_index,:])
                picked_counts.append(cts_temp)
            # Put it into the image matrix
            intensity_map[j] = np.asarray(picked_counts)
        return intensity_map, raw_reshape_image

    @QtCore.pyqtSlot()
    def update_image(self, map_array):
        self.map = map_array
        self.image.set_data(self.map)
        self.image.set_extent([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text()),
                               float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.mplMap.axes.set_ylim([float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.mplMap.axes.set_xlim([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text())])
        self.ui.vsMax.setValue(99)
        self.image.set_clim(0, self.map.max())
        self.ui.mplMap.draw()

    def plot_curve(self):
        y_length = np.size(self.yArr)
        index_x = int((float(self.ui.leXCursorSet.text())-float(self.ui.lexscanstart.text())) /
                      (float(self.ui.lexscanend.text())-float(self.ui.lexscanstart.text())) * 100)
        index_y = int((float(self.ui.leYCursorSet.text())-float(self.ui.leyscanstart.text())) /
                      (float(self.ui.leyscanend.text())-float(self.ui.leyscanstart.text())) * y_length)
        self.generate_new_time_step()
        self.time_sig = self.raw_reshape_image[index_y,index_x]
        self.replot_time_data()

    def replot_time_data(self):
        """
        Replot the data plot.
        :return: None
        """
        # self.ref_plot.set_data(self.freq_sweep, self.ref_ave)
        if np.size(self.time_sweep) != np.size(self.time_sig):
            self.ui.statusbar.showMessage('Rewrite time parameters!')
        else:
            self.time_sig_plot.set_data(self.time_sweep, self.time_sig)
            self.ui.time_data_fig.axes.set_xlabel('time (ns)')
            self.ui.time_data_fig.axes.set_ylabel('Counts')
            self.ui.time_data_fig.axes.set_xlim(np.min(self.time_sweep), np.max(self.time_sweep))
            self.ui.time_data_fig.axes.set_xscale("linear")
            self.ui.time_data_fig.axes.set_ylim(0, np.max(self.time_sig) + np.ptp(self.time_sig) * 0.05)
            self.ui.time_data_fig.draw()
            self.ui.statusbar.showMessage('Successfully replot the figure!')

    def fit_data(self):
        if self.ui.comboBox.currentText() == 'lifetime':
            constant = 0
            init_value = [float(self.ui.a1_lineEdit.text()), float(self.ui.a2_lineEdit.text()),
                          float(self.ui.lifetime_lineEdit_1.text()), float(self.ui.IRF_time_position_lineEdit.text()),
                          float(self.ui.IRF_time_position_lineEdit.text()), float(self.ui.IRF_FWHM_lineEdit.text()), constant]
            self.popt, self.fit_curve = lf(np.array(self.time_sweep), np.array(self.time_sig), init_value)
            self.update_plot_fit_curve()
            # update text box
            self.ui.FitWidget.setPlainText('a1= ' + str(round(self.popt[0], 2)) + '\n')
            self.ui.FitWidget.appendPlainText('a2= ' + str(round(self.popt[1], 3)) + '\n')
            self.ui.FitWidget.appendPlainText('Lifetime 1= ' + str(round(self.popt[2], 2)) + 'ns\n')
            self.ui.FitWidget.appendPlainText('Lifetime 2= ' + str(round(self.popt[3], 2)) + 'ns\n')
            self.ui.FitWidget.appendPlainText('IRF time position= ' + str(round(self.popt[4],2)) + 'ns\n')
            self.ui.FitWidget.appendPlainText('IRF FWHM= ' + str(round(self.popt[5], 2)) + 'ns\n')
            self.ui.statusbar.showMessage('Data fitting Successfully.')
        else:
            init_value = [float(self.ui.Time_Freq_lineEdit.text()), 0, 40, 0, 100]
            self.generate_new_time_step()
            self.popt, self.fit_curve = sf(np.array(self.time_sweep), np.array(self.time_sig),float(self.ui.Time_Freq_lineEdit.text()), init_value)
            self.update_plot_fit_curve()
            # update text box
            self.ui.FitWidget.setPlainText('DC= ' + str(round(self.popt[4], 2)) + '\n')
            self.ui.FitWidget.appendPlainText('Amplitude= ' + str(round(self.popt[2], 2)) + '\n')
            self.ui.FitWidget.appendPlainText('Phase= ' + str(round(self.popt[3], 2)) + ' deg\n')
            self.ui.FitWidget.appendPlainText('Frequency= ' + str(round(self.popt[0], 2)) + 'kHz\n')
            self.ui.statusbar.showMessage('Data fitting Successfully.')

    def generate_new_time_step(self):
        start_time = float(self.ui.Time_bin_width_lineEdit.text()) / 1000
        end_time = start_time * float(self.ui.Time_bin_num_lineEdit.text())
        time_step_num = int(self.ui.Time_bin_num_lineEdit.text())
        self.time_sweep = list(np.linspace(start_time, end_time, time_step_num))

    def update_plot_fit_curve(self):
        # Init plot
        self.fit_plot.set_data(self.time_sweep, self.fit_curve)
        # Set fig parameters
        self.ui.time_data_fig.draw()

    def cal_fun_image(self):
        y_length = np.size(self.yArr)
        self.calculation_map = np.zeros((y_length, 100))
        self.generate_new_time_step()
        for j in range(y_length):
            for i in range(100):
                if self.intensity_map[j,i] < int(self.ui.Background_lineEdit.text()):
                    self.calculation_map[j,i] = 0
                else:
                    if self.ui.comboBox.currentText() == 'lifetime':
                        constant = 0
                        init_value = [float(self.ui.a1_lineEdit.text()), float(self.ui.a2_lineEdit.text()),
                                    float(self.ui.lifetime_lineEdit_1.text()),
                                    float(self.ui.IRF_time_position_lineEdit.text()),
                                    float(self.ui.IRF_time_position_lineEdit.text()),
                                    float(self.ui.IRF_FWHM_lineEdit.text()), constant]
                        self.popt, self.fit_curve = lf(np.array(self.time_sweep), np.array(self.raw_reshape_image[j,i,:]), init_value)
                        # self.calculation_map[j, i] = self.popt[1] * self.popt[2] + (1 - self.popt[1]) * self.popt[3]  # efficient lifetime
                        self.calculation_map[j, i] = self.popt[3]
                    else:
                        init_value = [float(self.ui.Time_Freq_lineEdit.text()), 0, 40, 0, 100]
                        self.popt, self.fit_curve = sf(np.array(self.time_sweep), np.array(self.raw_reshape_image[j,i,:]),
                                                       float(self.ui.Time_Freq_lineEdit.text()), init_value)
                        if self.ui.comboBox.currentText() == 'lock in amp':
                            self.calculation_map[j, i] = self.popt[2] / self.popt [4]
                        elif self.ui.comboBox.currentText() == 'lock in phi':
                            self.calculation_map[j, i] = self.popt[3]
                        else:
                            self.calculation_map[j, i] = 0
                            self.ui.statusbar.showMessage('Wrong choose.')
        self.update_cal_image(self.calculation_map)

    def update_cal_image(self,map_array):
        mask = map_array != 0
        if np.any(mask):
            self.min_cal_map = np.min(map_array[mask])
            self.max_cal_map = np.max(map_array[mask])
        map_mask = np.ma.masked_where(map_array == 0, map_array)
        self.cal_map = map_mask
        self.cal_image.set_data(self.cal_map)
        self.cal_image.set_extent([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text()),
                                   float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.calMap.axes.set_ylim([float(self.ui.leyscanstart.text()), float(self.ui.leyscanend.text())])
        self.ui.calMap.axes.set_xlim([float(self.ui.lexscanstart.text()), float(self.ui.lexscanend.text())])
        self.ui.calMap.axes.set_facecolor('black')
        self.ui.vsMax_cal_image.setValue(99)
        self.cal_image.set_clim(self.min_cal_map, self.max_cal_map)
        self.ui.calMap.draw()

    def save_data_cal(self):
        """
        This methods save let the user choose the location, and save the txt data
        :return: None
        """
        # Get the Raw Data from DataThread
        try:
            self.saved_cal_data = self.calculation_map
        except:
            sys.stderr.write('No data to be saved!\n')
            return
        # Move the dir to 'Cache/Data' (default location for saving data)
        os.chdir(r"C:\zjh\experiment data")
        # self.save_data_txt()
        self.save_cal_data()

    def save_cal_data(self):
        dir_save_data = QtWidgets.QFileDialog.getSaveFileName(self, 'Enter save file', '', 'Text (*.txt)')
        dir_save_data = str(dir_save_data[0].replace('/', '\\'))
        if dir_save_data != '':
            f = open(dir_save_data, 'w')
            for each_datapoint in self.saved_cal_data:
                for each_datapoint_count in each_datapoint[2]:
                    f.write(str(each_datapoint[0]) + '\t' + str(each_datapoint[1]) + '\t' + str(each_datapoint_count) + '\n')
            f.close()
        else:
            sys.stderr.write('No File is saved!\n')

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

    @QtCore.pyqtSlot(QtCore.QEvent)
    def closeEvent(self, event):
        quit_msg = "Save parameters as Defaults?"
        reply = QtWidgets.QMessageBox.question(self, 'Message', quit_msg, QtWidgets.QMessageBox.Save |
                                               QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if reply == QtWidgets.QMessageBox.Save:
            self.save_defaults()
            self.Data_Image_Close.emit()
            self.periodic_clear_cache(days=self.CACHE_LIFE)
            event.accept()
        elif reply == QtWidgets.QMessageBox.Discard:
            self.Data_Image_Close.emit()
            self.periodic_clear_cache(days=self.CACHE_LIFE)
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
