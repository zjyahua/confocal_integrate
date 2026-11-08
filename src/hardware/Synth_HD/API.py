from windfreak import SynthHD

class MicrowaveSynthHD():
    def __init__(self):
        self._serial_port = 'COM3'
        self._channel = 1
        self._conn = SynthHD(self._serial_port)
        # self._conn.init()
        self.model = self._conn.model_type
        self.ser_nr = self._conn.serial_number
        self.mod_hw = self._conn.hardware_version
        self.mod_fw = self._conn.firmware_version
        print('Found {0} Ser No: {1} {2} {3}'.format(self.model, self.ser_nr, self.mod_hw, self.mod_fw))
        temp = self._conn.read('temperature')
        print('MW synth temperature: {0}°C'.format(temp))
        print('Selected channel is Ch{}'.format(self._channel))
        self.current_output_mode = 'cw'

    def on_activate(self):
        self._conn.init()

    def _off(self):
        """ Turn the current channel off.

        @return tuple: see _stat()
        """
        self._conn[self._channel].enable = False
        return self._stat()

    def _on(self):
        """ Turn on the current channel.

        @return tuple(bool): see _stat()
        """
        self._conn[self._channel].enable = True
        return self._stat()

    def get_status(self):
        """
        Gets the current status of the MW source, i.e. the mode (cw, list or sweep) and
        the output state (stopped, running)

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        status = self._stat()
        active = status[0] == 1 and status[1] == 1 and status[2] == 1

        return self.current_output_mode, active

    def _stat(self):
        """ Return status of PLL, power amplifier and output power muting for current channel.

        @return tuple(bool): PLL on, power amplifier on, output power muting on
        """
        # PLL status
        e = self._conn[self._channel].pll_enable
        # power amplifier status
        r = self._conn[self._channel].pa_enable
        # hig/low power selector
        h = self._conn[self._channel].rf_enable
        return e, r, h

    def off(self):
        """ Switches off any microwave output.
        @return int: error code (0:OK, -1:error)
        """
        # disable sweep mode
        self._conn.sweep_enable = False
        # set trigger source to software
        self._conn.trigger_mode = 'disabled'
        # turn off everything for the current channel
        self._off()
        return 0

    def get_power(self):
        """ Gets the microwave output power.

        @return float: the power set at the device in dBm
        """
        if self.current_output_mode == 'cw':
            mw_cw_power = float(self._conn[self._channel].power)
            return mw_cw_power
        elif self.current_output_mode == 'sweep':
            mw_sweep_power = float(self._conn[self._channel].read('sweep_power_low'))
            return mw_sweep_power

    def get_frequency(self):
        """
        Gets the frequency of the microwave output.
        Returns single float value if the device is in cw mode.
        Returns list if the device is sweep mode.

        @return [float, list]: frequency(s) currently set for this device in MHz
        """
        if self.current_output_mode == 'cw':
            # query frequency
            mw_cw_frequency = float(self._conn[self._channel].frequency)  # unit Hz
            return mw_cw_frequency
        elif self.current_output_mode == 'sweep':
            mw_start_freq = float(self._conn[self._channel].read('sweep_freq_low'))
            mw_stop_freq = float(self._conn[self._channel].read('sweep_freq_high'))
            mw_step_freq = float(self._conn[self._channel].read('sweep_freq_step'))
            return mw_start_freq, mw_stop_freq, mw_step_freq

    def set_frequency(self, frequency=None):
        self.current_output_mode = 'cw'
        # trigger mode: software
        self._conn.trigger_mode = 'disabled'
        if frequency is not None:
            self._conn[self._channel].frequency = frequency * 1e6
        mw_cw_freq = float(self._conn[self._channel].frequency) * 1e6
        return mw_cw_freq, 'cw'

    def set_power(self, power=None):
        self.current_output_mode = 'cw'
        # trigger mode: software
        self._conn.trigger_mode = 'disabled'
        if power is not None:
            self._conn[self._channel].power = power
        mw_cw_power = float(self._conn[self._channel].power)
        return mw_cw_power, 'cw'

    def set_cw(self, frequency=None, power=None):
        """
        Configures the device for cw-mode and optionally sets frequency and/or power

        @param float frequency: frequency to set in MHz
        @param float power: power to set in dBm
        @return float, float, str: current frequency in Hz, current power in dBm, current mode
        """
        self.current_output_mode = 'cw'

        self._conn.write('sweep_type', 0)  # Sweep type {0: linear, 1: tabular}
        self._conn.sweep_enable = True  # run continuous when x=1

        # trigger mode: software
        self._conn.trigger_mode = 'disabled'

        # sweep frequency and steps

        if frequency is not None:
            self._conn[self._channel].frequency = frequency * 1e6
            self._conn[self._channel].write('sweep_freq_high', frequency)
            self._conn[self._channel].write('sweep_freq_low', frequency)
        if power is not None:
            self._conn[self._channel].power = power
            self._conn[self._channel].write('sweep_power_high', power)
            self._conn[self._channel].write('sweep_power_low', power)

        mw_cw_freq = float(self._conn[self._channel].frequency) * 1e6
        mw_cw_power = float(self._conn[self._channel].power)
        print('CW f: {0} {2} P: {1} {3}'.format(frequency, power, mw_cw_freq, mw_cw_power))
        return mw_cw_freq, mw_cw_power, 'cw'

    def cw_on(self):
        """
        Switches on cw microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """
        self.current_output_mode = 'cw'
        self._on()
        # enable sweep mode and set to start frequency
        self._conn.write('sweep_single', 1)  # Run sweep
        return 0

    def sweep_on(self):
        """ Switches on the sweep mode.

        @return int: error code (0:OK, -1:error)
        """
        self.current_output_mode = 'sweep'
        self._on()
        # enable sweep mode and set to start frequency
        self._conn.write('sweep_single', 1)  # Run sweep
        # query sweep mode
        # mode = int(self._conn.read('sweep_single'))
        return 0

    def set_sweep(self, start=None, stop=None, step=None, power=None):
        """
        Configures the device for sweep-mode and optionally sets frequency start/stop/step
        and/or power

        @return float, float, float, float, str: current start frequency in MHz,
                                                 current stop frequency in MHz,
                                                 current frequency step in MHz,
                                                 current power in dBm,
                                                 current mode
        """
        self.current_output_mode = 'sweep'
        if (start is not None) and (stop is not None) and (step is not None):
            # sweep mode: linear sweep, non-continuous
            self._conn.write('sweep_type', 0)  # Sweep type {0: linear, 1: tabular}
            self._conn.sweep_enable = False  # running a single sweep when x=0
            # self._conn.write('sweep_cont', 0)
            # trigger mode: single step
            self._conn.trigger_mode = 'single frequency step'

            # sweep direction
            if stop >= start:
                self._conn.write('sweep_direction', 1)
            else:
                self._conn.write('sweep_direction', 0)

            # sweep lower and upper frequency and steps
            self._conn[self._channel].write('sweep_freq_high', stop)
            self._conn[self._channel].write('sweep_freq_low', start)
            self._conn[self._channel].write('sweep_freq_step', step)

        # sweep power
        if power is not None:
            # set power
            self._conn[self._channel].power = power
            # set sweep lower end power
            self._conn[self._channel].write('sweep_power_low', power)
            # set sweep upper end power
            self._conn[self._channel].write('sweep_power_high', power)

        # query lower frequency
        mw_start_freq = float(self._conn[self._channel].read('sweep_freq_low'))
        # query upper frequency
        mw_stop_freq = float(self._conn[self._channel].read('sweep_freq_high'))
        # query sweep step size
        mw_step_freq = float(self._conn[self._channel].read('sweep_freq_step'))
        # query power
        mw_power = float(self._conn[self._channel].power)
        # query sweep lower end power
        mw_sweep_power_start = float(self._conn[self._channel].read('sweep_power_low'))
        # query sweep upper end power
        mw_sweep_power_stop = float(self._conn[self._channel].read('sweep_power_low'))
        print('SWEEP: {} -> {} {}, {} -> {} {}, {} -> {}'.format(
            start, stop, step, mw_start_freq, mw_stop_freq, mw_step_freq, mw_power,
            mw_sweep_power_start, mw_sweep_power_stop))
        return (
            mw_start_freq,
            mw_stop_freq,
            mw_step_freq,
            mw_sweep_power_start,
            'sweep'
        )

    def reset_sweep_pos(self):
        """
        Reset of MW sweep mode position to start (start frequency)
        @return int: error code (0:OK, -1:error)
        """
        # enable sweep mode and set to start frequency
        self._conn.write('sweep_single', 1)  # Run sweep
        return 0

    def set_ext_trigger(self, dwell_time):
        """ Set the external trigger for this device with proper polarization.

        TriggerEdge basically low TTL value
        @param dwell_time: minimum dwell time in microseconds

        @return object: new time in microseconds
        """
        print('Trigger at low TTL value dwell for {}'.format(dwell_time))
        # Sweep time step in [4, 10000] ms
        self._conn[self._channel].write('sweep_time_step', float(dwell_time))
        new_time = float(self._conn[self._channel].read('sweep_time_step'))
        return new_time

