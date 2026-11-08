# import API classes into the current namespace

"""
Created on Dec 10, 2022

@author: jia hua

This File is used for control of pulsestreamer
Works under python 3.9
Need the pulsestreamer package
"""


from pulsestreamer import PulseStreamer, Sequence, TriggerStart, OutputState, TriggerRearm
# import numpy as np
import time


class PulseGenerator():
    def __init__(self):
        """
        connect to devices in the network
        """
        ip = '169.254.8.2'
        self.ps = PulseStreamer(ip)

    def init_ps(self):
        """
        all digital channels are low and analog channel 0.0
        """
        self.ps.constant(OutputState.ZERO())

    def all_constant(self, digital_channel_number, analog_0=1.0, analog_1=0.0):
        """
        digital_channel=the channel number, could be a list like [0,1,2,4]
        analog_0/1 = the voltage
        digital_channel is constant high and analog channel for voltage set
        """
        self.ps.constant(OutputState(digital_channel_number, analog_0, analog_1))

    def trigger_mode(self, start_mode='software', rearm_mode='auto'):
        """
        start mode has:
        TriggerStart.IMMEDIATE: Trigger immediately after a sequence is uploaded. (default)
        TriggerStart.SOFTWARE: Trigger by calling startNow() method.
        TriggerStart.HARDWARE_RISING: External trigger on the rising edge.
        TriggerStart.HARDWARE_FALLING: External trigger on the falling edge.
        TriggerStart.HARDWARE_RISING_AND_FALLING: External trigger on rising and falling edges.

        rearm mode has:
        TriggerRearm.AUTO: Trigger immediately after a sequence is uploaded. (default)
        TriggerRearm.MANUAL:Trigger once only and do not rearm automatically. Rearm manually via the rearm() method.
        """

        if start_mode == 'software':
            start_mode = TriggerStart.SOFTWARE
        elif start_mode == 'hardware_rising':
            start_mode = TriggerStart.HARDWARE_RISING
        elif start_mode == 'hardware_falling':
            start_mode = TriggerStart.HARDWARE_FALLING
        elif start_mode == 'hardware_rising_and_falling':
            start_mode = TriggerStart.HARDWARE_RISING_AND_FALLING
        else:
            start_mode = TriggerStart.IMMEDIATE

        if rearm_mode == 'manual':
            rearm_mode = TriggerRearm.MANUAL
        else:
            rearm_mode = TriggerRearm.AUTO

        self.ps.setTrigger(start=start_mode, rearm=rearm_mode)

    # Example: PulseGenerator.setTrigger('internal')

    def get_trigger_state(self):
        """
        check trigger state
        """
        start_status = self.ps.getTriggerStart()
        return start_status.name

    def digital_pulse_sequence(self, channel, pattern, n_run):
        """
        create a pulse sequence for one digital channel
        clock is 125MHz
        if pattern length cannot device 8 to get an int, stream will over length to get the length/8=int
        a method to get the pattern is n_run*pattern, require n_run/8=int
        if pattern/8=int, could repeat the pattern by stream(seq,n_run)

        channels (list[int]) – Digital channel number(s) as labeled on the Pulse Streamer connectors panel.
        pattern (list) – A pattern to be assigned to the channel.
        n_run is int for repeat times, better n_run/8=int

        the following seq is same
        seq1 = Sequence.repeat(seq, 5)
        seq1 = seq * 5
        seq1 = 5 * seq

        after finish seq, will back to laser on ([0] is high, analog_0 is 1.0) OutputState([0], 1.0, 0.0)
        """
        seq = Sequence()
        seq.setDigital(channel, pattern)
        self.ps.stream(seq, n_run, OutputState.ZERO())

    def analog_pulse_sequence(self, channel, pattern, n_run):
        """
        create a pulse sequence for one analog channel
        clock is 125MHz
        if pattern length cannot device 8ns to get an int, stream will over length to get the length/8=int
        a method to get the pattern is n_run*pattern, require n_run/8=int
        if pattern/8=int, could repeat the pattern by stream(seq,n_run)

        channels (list[int]) – Digital channel number(s) as labeled on the Pulse Streamer connectors panel.
        pattern (list) – A pattern to be assigned to the channel.
        n_run is int for repeat times, better n_run/8=int

        the following seq is same
        seq1 = Sequence.repeat(seq, 5)
        seq1 = seq * 5
        seq1 = 5 * seq

        after finish seq, will back to laser on ([0] is high, analog_0 is 1.0)
        """
        seq = Sequence()
        seq.setAnalog(channel, pattern)
        self.ps.stream(seq, n_run, OutputState.ZERO())

    # Upload the sequences to the pulse generator
    def upload_seq_list(self, seq_list, n_run):
        """
        our seq_list=[(channel#,laser_seq),(channel#,mw_seq),(channel#,camera_seq),(channel#,mw_analog_seq)]
        laser_seq=[(duration, level),(duration, level),(duration, level)]
        mw_seq=[(duration, level),(duration, level),(duration, level)]
        camera_seq=[(duration, level),(duration, level),(duration, level)]
        mw_analog_seq=constant 1V
        for exp
        laser_channel=[0]
        mw_channel=[1]
        camera_seq=[2]
        """
        seq = Sequence()
        for ch_number in range(len(seq_list)-1):
            seq.setDigital(seq_list[ch_number][0], seq_list[ch_number][1])
        seq.setAnalog(0, seq_list[-1][1])

        self.ps.stream(seq, n_run, OutputState.ZERO())

    # Internal trigger
    def start_now(self):
        """
        If the start is TriggerStart SOFTWARE then the sequence is started every time the startNow() is called.
        If the start is TriggerStart IMMEDIATE, n_runs>=0, and the sequence has finished,
        then startNow() will trigger the sequence again.
        """
        self.ps.startNow()

    def is_running(self):
        """
        Returns True if the Pulse Streamer is currently streaming a sequence.
        When the sequence has finished and the device remains in the final state, this method returns False again.
        """
        return self.ps.isStreaming()

    def force_stop(self):
        """
        for want to stop pulse suddenly
        """
        self.ps.forceFinal()

    def reset(self):
        """
        Each pulse experiment need this function to clear pulse stream
        """
        self.ps.reset()

if __name__ == '__main__':
    pulser = PulseGenerator()
    pulser.all_constant([0])
    t1 = time.time()
    time.sleep(1)
    pulser.trigger_mode()
    # pulser.init_ps()
    # pulser.all_constant([], 0.0, 0.0)
    pulser.get_trigger_state()
    pulser.init_ps()
    t2 = time.time()
    print(t2 - t1)



