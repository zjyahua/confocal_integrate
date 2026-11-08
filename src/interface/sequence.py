"""
Created on Dec 4, 2024
Update on Oct 21, 2026

This File is the Main Thread for Sequence define
"""
import sys
import ast
from pathlib import Path
from ui.uipy.Sequence.Sequence import Ui_MainWindow
from PyQt5 import QtWidgets, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

class mainGUI(QtWidgets.QMainWindow):

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        # Setup GUI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.seq_fig = None
        self.seq_dir = None  # The directory of the pulse sequence txt file
        self.pulse_seq = None  # The pulse sequence (list) that using for generate and using in the main thread
        self.pulse_name = None
        # Process for initialization
        self.connect_methods()  # Connect methods to slots
        self.init_seq_plot()  # Init the plot for sequence
        # init button condition
        # pulse Group
        self.ui.Seq_Load_pushButton.setEnabled(True)
        self.ui.Seq_Show_pushButton.setEnabled(False)
        self.ui.Seq_Save_pushButton.setEnabled(False)

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

        if not directory.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Directory Not Found",
                f"PulseSeq directory not found:\n{directory}"
            )
            return

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

                key = self._normalize_seq_key(value[0])

                if not isinstance(key, str):
                    raise ValueError(
                        f"Pulse sequence key at line {line_num} should be string: {line}"
                    )

                # 数据结构：
                # {'Laser': ['0', '10'], ...}
                # key = value[0]
                # pulse_seq[key] = value[1:]
                pulse_seq[key] = [str(v) for v in value[1:]]

        self.seq_dir = str(seq_path)
        self.pulse_seq = pulse_seq
        self.pulse_name = seq_path.stem

        self._set_pulse_seq_to_gui()

        self.ui.Seq_label.setText(self.pulse_name)

        print("load successful")
        print("Pulse Sequence:", self.pulse_seq)
        # Update the plot
        self.update_pulse_seq_plot()
        # Enable Animate Pushbutton
        self.ui.Seq_Show_pushButton.setEnabled(True)
        self.ui.Seq_Save_pushButton.setEnabled(True)

    def update_pulse_seq_plot(self):
        """
        Update pulse sequence plot using self.seq_fig.
        """

        try:
            if not self.pulse_seq:
                raise ValueError("No pulse sequence loaded.")

            pulse_period_ns = self._get_pulse_period_ns(self.pulse_seq)

            laser_seq = self.convert_high_intervals_to_segments(
                self.pulse_seq.get("Laser", []),
                pulse_period_ns
            )

            mw_seq = self.convert_high_intervals_to_segments(
                self.pulse_seq.get("MicroWave", []),
                pulse_period_ns
            )

            ref_seq = self.convert_high_intervals_to_segments(
                self.pulse_seq.get("Ref", []),
                pulse_period_ns
            )

            sig_seq = self.convert_high_intervals_to_segments(
                self.pulse_seq.get("Sig", []),
                pulse_period_ns
            )

            aom_values = self.pulse_seq.get("AOM", [])
            aom_voltage = float(aom_values[0]) if aom_values else 0.0
            aom_seq = [(pulse_period_ns, aom_voltage)]

            if self.seq_fig is None:
                canvas, ax = self._create_canvas(
                    self.ui.Seq_Window_widget,
                    "seq_fig"
                )
            else:
                canvas = self.seq_fig
                fig = canvas.figure
                fig.clear()
                ax = fig.add_subplot(111)

            self._plot_segments(ax, laser_seq, offset=8, style="g-", label="laser")
            self._plot_segments(ax, mw_seq, offset=6, style="r-", label="mw")
            self._plot_segments(ax, ref_seq, offset=4, style="k-", label="ref")
            self._plot_segments(ax, sig_seq, offset=2, style="b-", label="sig")
            self._plot_segments(ax, aom_seq, offset=0, style="y-", label="aom")

            ax.set_xlim(0, pulse_period_ns)
            ax.set_ylim(-0.5, 9.5)

            ax.set_xlabel("Time (ns)")
            ax.set_ylabel("Channel")
            ax.grid(True, alpha=0.3)

            ax.legend(
                fontsize=6.5,
                bbox_to_anchor=(1, 1),
                loc="upper left"
            )

            canvas.draw_idle()

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Pulse Sequence",
                f"Failed to update pulse sequence plot:\n{e}"
            )

    def pulse_seq_plot(self):
        """
        Read pulse sequence from GUI and update plot.
        """

        try:
            self.pulse_seq = self._read_pulse_seq_from_gui()
            self.update_pulse_seq_plot()
            self.ui.Seq_Save_pushButton.setEnabled(True)

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Pulse Sequence",
                f"Failed to read pulse sequence:\n{e}"
            )

    def save_pulse_seq(self):
        """
        Save pulse sequence to txt file.
        """

        try:
            self.pulse_seq = self._read_pulse_seq_from_gui()
            self._validate_pulse_seq(self.pulse_seq)

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid Pulse Sequence",
                f"Cannot save pulse sequence:\n{e}"
            )
            return

        directory = self._pulse_seq_directory()
        directory.mkdir(parents=True, exist_ok=True)

        default_name = self.pulse_name if self.pulse_name else "PulseSeq"
        default_path = directory / f"{default_name}.txt"

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save PulseSeq File",
            str(default_path),
            "Text Files (*.txt);;All Files (*)"
        )

        if not save_path:
            return

        save_path = Path(save_path)

        if save_path.suffix.lower() != ".txt":
            save_path = save_path.with_suffix(".txt")

        seq_order = [
            "Laser",
            "MicroWave",
            "Ref",
            "Sig",
            "AOM",
            "Sum",
        ]

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                for key in seq_order:
                    row = [key] + self.pulse_seq.get(key, [])
                    f.write(repr(row) + "\n")

            self.seq_dir = str(save_path)
            self.pulse_name = save_path.stem
            self.ui.Seq_label.setText(self.pulse_name)

            print(f"Pulse sequence saved to: {save_path}")

        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Save Failed",
                f"Failed to save pulse sequence:\n{e}"
            )

    def _read_pulse_seq_from_gui(self):
        """
        Read pulse sequence from lineEdits.

        Accepted lineEdit formats:
            ['0', '10']
            ['Laser', '0', '10']
            100
            ['100']
        """

        return {
            "Laser": self._parse_seq_text(
                self.ui.Seq_Laser_lineEdit.text(),
                "Laser"
            ),
            "MicroWave": self._parse_seq_text(
                self.ui.Seq_MW_lineEdit.text(),
                "MicroWave"
            ),
            "Ref": self._parse_seq_text(
                self.ui.Seq_Ref_lineEdit.text(),
                "Ref"
            ),
            "Sig": self._parse_seq_text(
                self.ui.Seq_Sig_lineEdit.text(),
                "Sig"
            ),
            "AOM": self._parse_seq_text(
                self.ui.Seq_AOM_lineEdit.text(),
                "AOM"
            ),
            "Sum": self._parse_seq_text(
                self.ui.Seq_Sum_lineEdit.text(),
                "Sum"
            ),
        }

    def _set_pulse_seq_to_gui(self):
        """
        Display self.pulse_seq in lineEdits.
        The lineEdits only show value lists, without key names.
        """

        if not self.pulse_seq:
            return

        self.ui.Seq_Laser_lineEdit.setText(str(self.pulse_seq.get("Laser", [])))
        self.ui.Seq_MW_lineEdit.setText(str(self.pulse_seq.get("MicroWave", [])))
        self.ui.Seq_Ref_lineEdit.setText(str(self.pulse_seq.get("Ref", [])))
        self.ui.Seq_Sig_lineEdit.setText(str(self.pulse_seq.get("Sig", [])))
        self.ui.Seq_AOM_lineEdit.setText(str(self.pulse_seq.get("AOM", [])))
        self.ui.Seq_Sum_lineEdit.setText(str(self.pulse_seq.get("Sum", [])))

    def _parse_seq_text(self, text, key):
        """
        Parse one sequence lineEdit.

        Example:
            key = 'Laser'

            ['0', '10']              -> ['0', '10']
            ['Laser', '0', '10']     -> ['0', '10']
            100                      -> ['100']
            ['100']                  -> ['100']
        """

        text = text.strip()

        if not text:
            return []

        value = ast.literal_eval(text)

        if isinstance(value, tuple):
            value = list(value)

        elif not isinstance(value, list):
            value = [value]

        if value:
            first = value[0]

            if isinstance(first, str):
                first_key = self._normalize_seq_key(first)

                if first_key == key:
                    value = value[1:]

        return [str(v) for v in value]

    @staticmethod
    def _normalize_seq_key(key):
        """
        Normalize pulse sequence key names.
        """

        key = str(key).strip()

        if key.lower() == "microwave":
            return "MicroWave"

        return key

    @staticmethod
    def _get_pulse_period_ns(pulse_seq):
        """
        Get pulse period from pulse_seq['Sum'].
        """

        if "Sum" not in pulse_seq:
            raise ValueError("pulse_seq must contain key 'Sum'.")

        if not pulse_seq["Sum"]:
            raise ValueError("pulse_seq['Sum'] is empty.")

        pulse_period_ns = int(float(pulse_seq["Sum"][0]))

        if pulse_period_ns <= 0:
            raise ValueError(
                f"pulse_seq['Sum'] must be positive, got {pulse_seq['Sum']}"
            )

        return pulse_period_ns

    def _validate_pulse_seq(self, pulse_seq):
        """
        Validate pulse sequence before saving.
        """

        pulse_period_ns = self._get_pulse_period_ns(pulse_seq)

        for key in ["Laser", "MicroWave", "Ref", "Sig"]:
            self.convert_high_intervals_to_segments(
                pulse_seq.get(key, []),
                pulse_period_ns
            )

        aom_values = pulse_seq.get("AOM", [])

        if aom_values:
            float(aom_values[0])

    @staticmethod
    def _segments_to_step_xy(segments, offset=0.0, scale=1.0):
        """
        Convert segment list to x/y data for step plot.

        Example:
            segments = [(10, 1), (90, 0)]

        Output:
            x = [0, 10, 100]
            y = [1, 0, 0]
        """

        x = [0]
        y = []

        current_time = 0

        for duration, value in segments:
            duration = int(duration)
            value = offset + float(value) * scale

            current_time += duration
            x.append(current_time)
            y.append(value)

        if not y:
            y = [offset]
            x = [0, 0]

        y.append(y[-1])

        return x, y

    def _plot_segments(self, ax, segments, offset, style, label):
        """
        Plot one pulse channel.
        """

        x, y = self._segments_to_step_xy(
            segments,
            offset=offset,
            scale=1.0
        )

        ax.step(
            x,
            y,
            style,
            where="post",
            label=label
        )

    @staticmethod
    def convert_high_intervals_to_segments(interval_list, total_time):
        """
        Convert high-level intervals to pulse segments.

        Example
        -------
        interval_list = ['0', '10']
        total_time = 100

        return:
            [(10, 1), (90, 0)]

        interval_list = ['0', '10', '50', '80']
        total_time = 100

        return:
            [(10, 1), (40, 0), (30, 1), (20, 0)]
        """

        total_time = int(float(total_time))

        if total_time <= 0:
            raise ValueError(f"total_time must be positive, got {total_time}")

        if interval_list is None:
            return [(total_time, 0)]

        times = [int(float(x)) for x in interval_list]

        if len(times) == 0:
            return [(total_time, 0)]

        if len(times) % 2 != 0:
            raise ValueError(
                f"High interval list must contain start/end pairs: {interval_list}"
            )

        if any(t < 0 for t in times):
            raise ValueError(f"Pulse time cannot be negative: {times}")

        if any(t > total_time for t in times):
            raise ValueError(
                f"Pulse time exceeds total_time={total_time}: {times}"
            )

        segments = []
        current_time = 0

        for start, end in zip(times[0::2], times[1::2]):
            if end < start:
                raise ValueError(
                    f"Pulse end time must be >= start time: start={start}, end={end}"
                )

            if start < current_time:
                raise ValueError(
                    f"Pulse intervals overlap or are not sorted: {interval_list}"
                )

            if start > current_time:
                segments.append((start - current_time, 0))

            if end > start:
                segments.append((end - start, 1))

            current_time = end

        if current_time < total_time:
            segments.append((total_time - current_time, 0))

        if not segments:
            segments = [(total_time, 0)]

        return segments

    # Methods for initialization
    def connect_methods(self):
        """
        This method connects methods to the slots
        :return: None
        """
        # Pulse Group
        self.ui.Seq_Load_pushButton.clicked.connect(self.open_pulse_seq)
        self.ui.Seq_Show_pushButton.clicked.connect(self.pulse_seq_plot)
        self.ui.Seq_Save_pushButton.clicked.connect(self.save_pulse_seq)

    def init_seq_plot(self):
        """
        Initialize the pulse sequence plot.
        Only use self.seq_fig.
        """

        canvas, ax = self._create_canvas(
            self.ui.Seq_Window_widget,
            "seq_fig"
        )

        x = [0, 1000]

        ax.plot(x, [8, 8], "g-", label="laser")
        ax.plot(x, [6, 6], "r-", label="mw")
        ax.plot(x, [4, 4], "k-", label="ref")
        ax.plot(x, [2, 2], "b-", label="sig")
        ax.plot(x, [0, 0], "y-", label="aom")

        ax.set_ylim(-0.5, 9.5)
        ax.set_xlabel("Time")
        ax.set_ylabel("Channel")
        ax.grid(True, alpha=0.3)

        ax.legend(
            fontsize=6.5,
            bbox_to_anchor=(1, 1),
            loc="upper left"
        )

        canvas.draw_idle()

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

    def closeEvent(self, event):
        reply = QtWidgets.QMessageBox.question(
            self,
            "Exit",
            "Close Sequence window?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    myWindow = mainGUI()
    myWindow.show()
    sys.exit(app.exec_())