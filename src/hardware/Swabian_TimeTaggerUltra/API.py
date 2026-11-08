import TimeTagger

class TimeTaggerCounter():
    """
    This class defines a counter that counts incoming pulses at gate time.
    When finished, call self.recount() to clean up.
    """
    def __init__(self):
        # initiate timetagger
        self.tagger = TimeTagger.createTimeTagger("22440012YD")
        self.tagger.reset()
        # channel_list
        self._channel_apd = 1
        self._channel_detect_rise = 2  # Rising edge on input 2
        self._channel_detect_fall = -2  # Falling edge on input 2
        self._channel_pi_stage = 3
        self._channel_laser_detect_rise = 4
        # set trigger level for three channels
        # APD
        self.tagger.setTriggerLevel(1, 0.5)
        # Gate from Pulsestreamer
        self.tagger.setTriggerLevel(2, 0.5)
        self.tagger.setTriggerLevel(4, 0.5)
        # TTL from PI stage (Max Voltage 1.02 V)
        self.tagger.setTriggerLevel(3, 0.5)
        # parameter
        self._number_of_gates = int(100)
        self._bin_width = 1
        self._bin_num = int(2000)
        # state
        self.state = 0
        # init counter
        self.scan = None
        self.gate = None
        self.once_counter = None
        # self.counter = None
        self.flim = None
        self.flim_scan = None

    def configure_scan(self, number_of_gates=int(110), scan_method = 0):
        """
        end_channel = the next begin channel, either can use delay to generate end channel
        Args:
            number_of_gates: total scan TTL number
            scan_method: 0 for pi stage, 1 for galvo mirror
        Returns: number_of_gates
        """

        self._number_of_gates = number_of_gates
        if scan_method == 0:
            self.scan = TimeTagger.CountBetweenMarkers(
                tagger=self.tagger,
                click_channel=self._channel_apd,
                begin_channel=self._channel_pi_stage,
                n_values=number_of_gates
            )
        else:
            self.scan = TimeTagger.CountBetweenMarkers(
                tagger=self.tagger,
                click_channel=self._channel_apd,
                begin_channel=self._channel_detect_rise,
                end_channel=self._channel_detect_fall,
                n_values=number_of_gates
            )
        self.scan.stop()
        self.tagger.sync()
        self.state = 1
        return number_of_gates

    def get_status(self):
        """ Receives the current status of the Fast Counter and outputs it as
            return value.

        0 = un-configured
        1 = idle
        2 = running
        -1 = error state
        """
        return self.state

    def configure_gate(self, number_of_gates=int(1)):
        """
        This method initializes the gate counter.
        Args:
            number_of_gates: must be int
        Returns:
        """
        self._number_of_gates = number_of_gates
        # init gate counter
        self.gate = TimeTagger.CountBetweenMarkers(
            tagger=self.tagger,
            click_channel=self._channel_apd,
            begin_channel=self._channel_detect_rise,
            end_channel=self._channel_detect_fall,
            n_values=number_of_gates
        )
        self.tagger.sync()
        self.gate.stop()
        self.state = 1
        return number_of_gates

    def configure_count_once(self, bin_width_s):
        """
        This method initializes the once counter.
        Args:
            bin_width_s: (int) Length of a single time bin in microseconds.
        Returns: width of time bin in microseconds.
        """
        self._bin_width = bin_width_s * 1e9
        self.once_counter = TimeTagger.Counter(
            tagger=self.tagger,
            channels=[self._channel_apd],
            binwidth=self._bin_width,
            n_values=int(1)
        )
        self.tagger.sync()
        self.once_counter.stop()
        self.state = 1
        return bin_width_s

    def configure_flim(self, bin_width_s, bin_num_s, number_of_gates=int(1)):
        """
        This method initializes the time difference measurement.
        Args:
            bin_width_s: (int) Length of a single time bin in picoseconds.
            bin_num_s: (int) Modulation frequency in MHz.
            number_of_gates: (int) pixel of scan
        Returns:

        """
        self._bin_width = bin_width_s
        self._bin_num = bin_num_s
        self._number_of_gates = number_of_gates
        self.flim = TimeTagger.TimeDifferences(
            tagger=self.tagger,
            click_channel=self._channel_apd,
            start_channel=self._channel_detect_rise,
            binwidth=self._bin_width,
            n_bins=self._bin_num,
            n_histograms=self._number_of_gates
        )
        self.tagger.sync()
        self.flim.stop()
        self.state = 1
        return bin_width_s, bin_num_s

    def configure_flim_scan(self, bin_width_s, bin_num_s, number_of_gates=int(110)):
        """
        This method initializes the time difference measurement.
        Args:
            bin_width_s: (int) Length of a single time bin in picoseconds.
            bin_num_s: (int) Modulation frequency in MHz.
            number_of_gates: (int) pixel of scan
        Returns:

        """
        self._bin_width = bin_width_s
        self._bin_num = bin_num_s
        self._number_of_gates = number_of_gates
        self.flim_scan = TimeTagger.Flim(
            tagger=self.tagger,
            click_channel=self._channel_apd,
            start_channel=self._channel_laser_detect_rise,
            pixel_begin_channel=self._channel_detect_rise,
            pixel_end_channel=self._channel_detect_fall,
            binwidth=self._bin_width,
            n_bins=self._bin_num,
            n_pixels=self._number_of_gates
        )
        # self.flim_scan = TimeTagger.TimeDifferences(
        #     tagger=self.tagger,
        #     click_channel=self._channel_apd,
        #     start_channel=self._channel_laser_detect_rise,
        #     next_channel=self._channel_detect_rise,
        #     binwidth=self._bin_width,
        #     n_bins=self._bin_num,
        #     n_histograms=self._number_of_gates
        # )
        self.tagger.sync()
        self.flim_scan.stop()
        self.state = 1
        return bin_width_s, bin_num_s

    def on_deactivate(self):
        self.get_status()
        if self.state == 1:
            if self.scan != None:
                self.scan.stop()
            if self.gate != None:
                self.gate.stop()
            if self.once_counter != None:
                self.once_counter.stop()
            if self.flim != None:
                self.flim.stop()
            if self.flim_scan != None:
                self.flim_scan.stop()
        else:
            self.scan = None
            self.gate = None
            self.once_counter = None
            self.flim = None
            self.flim_scan = None

    def get_bin_width(self):
        """ Returns the width of a single time bin in the timetrace in microseconds. """
        width_in_microseconds = self._bin_width * 1e-9
        return width_in_microseconds

    def start_scan_measure(self):
        """ Start the scan counter. """
        self.scan.clear()
        self.scan.start()
        self.state = 2
        return 0

    def stop_scan_measure(self):
        """ Stop the scan counter. """
        self.scan.stop()
        self.state = 1
        return 0

    def start_gate_measure(self):
        """ Start the gate counter. """
        self.gate.clear()
        self.gate.start()
        self.state = 2
        return 0

    def stop_gate_measure(self):
        """ Stop the gaet counter. """
        self.gate.stop()
        self.state = 1
        return 0

    def start_once_counter_measure(self):
        """ Start the fast counter. """
        self.once_counter.clear()
        self.once_counter.start()
        self.state = 2
        return 0

    def stop_once_counter_measure(self):
        """ Stop the fast counter. """
        self.once_counter.stop()
        self.state = 1
        return 0

    def start_flim_measure(self):
        self.flim.clear()
        self.flim.start()
        self.state = 2
        return 0

    def stop_flim_measure(self):
        self.flim.stop()
        self.state = 1
        return 0

    def start_flim_scan_measure(self):
        self.flim_scan.clear()
        self.flim_scan.start()
        self.state = 2
        return 0

    def stop_flim_scan_measure(self):
        self.flim_scan.stop()
        self.state = 1
        return 0

    def get_gate_data(self):
        """
        need to wait 200 us after last gate measurement
        Receives the gate data and outputs the gate data. The data type is np array.
        Use tolist to change to list type
        """
        arr = self.gate.getData()
        return arr.tolist()

    def get_once_counter_data(self):
        """
        self.once_counter.getData()  [[0]] type
        Returns: data
        """
        arr = int(self.once_counter.getData())
        return arr

    def get_scan_data(self):
        arr = self.scan.getData()
        return arr.tolist()

    def get_flim_data(self):
        arr = self.flim.getData()
        return arr.tolist()

    def wait_flim_finished(self):
        self.flim.waitUntilFinished(timeout=-1)

    def wait_gate_finished(self):
        self.gate.waitUntilFinished(timeout=-1)

    def get_flim_scan_current_data(self):
        # arr = self.flim_scan.getData()
        # arr = self.flim_scan.getCurrentFrame()
        intensity = self.flim_scan.getCurrentFrameIntensity()
        return intensity.tolist()

    def get_flim_scan_ready_data(self):
        # arr = self.flim_scan.getData()
        arr = self.flim_scan.getReadyFrame()
        intensity = self.flim_scan.getReadyFrameIntensity()
        return arr.tolist(), intensity.tolist()

    def once_counter_recount(self):
        self.once_counter.clear()

    def scan_recount(self):
        self.scan.clear()

    def gate_recount(self):
        self.gate.clear()

    def flim_recount(self):
        self.flim.clear()

    def flim_scan_recount(self):
        self.flim_scan.clear()

if __name__ == "__main__":
    counter = TimeTaggerCounter()
    counter.configure_gate()
