from pipython import GCSDevice, pitools
from time import sleep
import numpy

class Mover():
    def __init__(self):
        self.pi_device = GCSDevice('E-727')
        self.accuracy = 0.01  # Micron
        self.data = []

    def connect(self):
        stages = 'P-561.3CD'
        # self.pi_device.ConnectUSB('0124022553')
        self.pi_device.ConnectUSB('0124032775')
        pitools.startup(self.pi_device, stages=stages, refmodes=None)
        # state = pitools.getservo(self.pi_device,'1')
        # print(state)
        pitools.setservo(self.pi_device,'1',states=True)
        pitools.setservo(self.pi_device, '2', states=True)
        pitools.setservo(self.pi_device, '3', states=True)

    def read_pos(self, axis):
        """
        Reads the position of the mover.
        Args:
            axis: '1' for x-axis, '2' for y-axis, and '3' for z-axis.
            POS? [{<AxisID>}] Get Real Position
        Returns: float position of the mover.
        """
        pos = self.pi_device.read('POS? ' + axis)
        spa, ret = pos.split('=')
        ret = float(ret)
        return ret

    def move_pos(self, axis, location, accuracy=None):
        """
        Moves the mover.
        Args:
            axis: '1' for x-axis, '2' for y-axis, and '3' for z-axis.
            location: float position of the mover.
            accuracy: for check whether the mover is moved or not.
            MOV {<AxisID> <Position>} Set Target Position
        Returns: None
        """
        # send location
        self.pi_device.send('MOV ' + axis + ' ' + str(location))
        if accuracy is None:
            accuracy = self.accuracy
        pos = self.read_pos(axis)
        # move x
        while abs(pos-location) > accuracy:
            # read position (Dummy)
            pos = self.read_pos(axis)
            # wait
            sleep(0.02)

    def signal_set(self, x_min, x_max, scan_time_pixel=2500):
        """
        set the scan waveform and trigger
        Args:
            x_min: scan waveform minimum
            x_max: scan waveform maximum

        "WAV" creat a waveform table
        example:
        "WAV 1 X LIN 1500 30 15 1500 0 370" Define a line waveform for Wave Table 1
        <WaveTableID> = 1
        <AppendWave> = X
        <WaveType> = LIN
        <SegLength> = 1500
        <Amp> = 30
        <Offset> = 15
        <WaveLength> = 1500
        <StartPoint> = 0
        <SpeedUpDown> = 370
        all segment lens： 50us * 5000 = 250ms

        Should first set the signal state of the output lines to "low" for all waveform points ("low" is also default)
        This can be done with TWS or TWC. Then use the TWS command to define the trigger actions (high/low level,
        rising/falling edge) for selected output lines at selected waveform points
        "TWC" Clear All Wave Related Triggers
        "TWS" Set TriggerLine Action To Waveform Point
        TWS {<TrigOutID> <PointNumber> <Switch>}

        "TWS 1 500 1 1 1500 1 1 1900 1 1 2000 1" Set trigger actions for the digital output line OUT1 (identifier is 1):
        at the waveform points 500, 1500, 1900 and 2000 it is set high;
        at all other points the state of the line is low (due to the TWC usage).
        Limitations for GCS Commands:
        The number of characters per line is limited to 256 byte
        Need use for loop to generate digital output lines.

        send 111 TTL
        Returns: None
        """
        num = int(scan_time_pixel / 50 * 100)
        self.pi_device.send('WAV 1 X LIN ' + str(num) + ' ' + str(x_max - x_min) + ' ' + str(x_min) + ' ' + str(num) + ' ' + '0 0')
        self.pi_device.send('WAV 1 & LIN 1000 0 ' + str(x_max) + ' 1000 ' + '0 0')
        self.pi_device.send('WAV 1 & LIN 4000 ' + str(x_min - x_max) + ' ' + str(x_max) + ' 4000 ' + '0 0')
        # print(self.pi_device.send('WAV? 1'))
        self.pi_device.send('TWC')
        for i in range(1, int(scan_time_pixel / 50 * 110) + 2, int(scan_time_pixel / 50)):
            self.pi_device.send('TWS 1 ' + str(i) + ' 1')

    def scanning(self, start, scan_time_pixel=2500):
        """
        Scan the mover and sent the trigger signal.
        Args:
            start: start float position of the mover.

            activate the Generator Trigger mode for the selected output lines, use the CTO command
            CTO {<TrigOutID> <CTOPam> <Value>}
            To select the mode, set <CTOPam> = 3 and <Value> to the code of the mode
            9 = Generator Pulse Trigger; the trigger line action must be defined with TWS.
            The trigger output will be synchronized with the wave generator output.
            The length of a single trigger pulse is shorter than the servo cycle duration.
            If the signal level is set to HIGH with TWS for consecutive points of a wave table,
            the signal level therefore changes back to LOW after each point

            "WSL 1 1" connect the wave generator 1 to wave table 1.
            "WGO 1 1" Start output of Wave Generator 1 immediately (synchronized by servo cycles)
            "WGO 1 0" Stop output of Wave Generator 1
            "WGR" Starts Recording in Sync with Wave Generator
            "DRR?" Get Recorded Data Values
            DRR? [<StartPoint> <NumberOfPoints>[{<RecTableID>}]]

        array number 5501

        Returns: Recorded Data array with size of 111
        """
        # move to the start position
        self.move_pos('1', start)
        # print('moved to start ', self.read_pos('1'))
        self.pi_device.send('CTO 1 3 9')
        self.pi_device.send('WSL 1 1')
        # self.pi_device.send('WSL 1 2')
        self.pi_device.send('WGR')
        self.pi_device.send('WGO 1 1')

        self.data = self.pi_device.read('DRR? 1 '+ str(int(scan_time_pixel / 50 * 110) + 1) + ' 1')
        # print('raw data back ', self.data)

        self.pi_device.send('WGO 1 0')
        array = []
        for each in self.data.split('\n')[:-1]:
            if not (each.startswith('#') or each == chr(10)):
                try:
                    array.append(float(each))
                except BaseException as e:
                    print(e)
                    pass
        # print(numpy.array(array).size)
        arr = numpy.transpose(numpy.array(array[:-1]).reshape(110, int(scan_time_pixel / 50)))[0].tolist()
        arr.append(array[-1])
        # print('data translate ',perf_counter())
        return arr

    def record_pos(self):
        array = []
        self.data = self.data.split('\n')
        f = open('1000.txt', 'w')
        for each in self.data:
            if each.startswith('#'):
                continue
            elif each == chr(10):
                continue
            else:
                f.write(each + '\n')
                try:
                    array.append(float(each))
                except BaseException as e:
                    print(e)
                    pass
        f.close()
        return array


if __name__ == '__main__':
    Pi = Mover()
    Pi.connect()
    print('x position:', Pi.read_pos('1'))
    print('y position:', Pi.read_pos('2'))
    print('z position:', Pi.read_pos('3'))
    #
    Pi.move_pos('1', 120)
    # print('x position:', Pi.read_pos('1'))
    Pi.move_pos('2', 80)
    # print('y position:', Pi.read_pos('2'))
    # Pi.move_pos('3', 100)
    # print('z position:', Pi.read_pos('3'))
    # Pi.signal_set(100, 120)
    # pos = Pi.scanning(100)
    # print(pos)
    # t = numpy.linspace(0,250, 111)


