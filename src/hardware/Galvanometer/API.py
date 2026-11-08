"""
product information:
scan angle: +/- 10degree mechanical angle
input scale factor: 1V/mech degree

digital:
input mode: XY2-100 16bit DAC
min degree: 20/65536=0.0003degree
optical angle is 2 times than mechanical angle: 0.00061degree
it can be changed to rad: 0.0006/180*pi=10.65urad
For Olympus 40X 0.95NA (f=4.5mm), it can be support resolution as 4.5*(50/200)*tan(10.65urad)=12nm
For Nikon 40x 0.8NA (f=5mm), it can be support resolution as 5*(50/200)*tan(10.65urad)=13.3nm

Analog:
AWG can output a resolution with 14 bit
For single position set for galvanometer, we use DC mode (voltage +/- 10v, min 1uV)
For scan, we use ramp function (90 duty, and need phase shift)
In the scan, it also needs to be triggered by pulse streamer
"""

import pyvisa,time


class SCANNER:
    def __init__(self):
        """
        connect to AWG devices
        """
        self._ip = 'USB0::0x1AB1::0x0642::DG1ZA261100909::INSTR'
        self._AWG = pyvisa.ResourceManager()
        self.AWG = None
        self._angle = None
        self._state = None
        self._channel_state = None

    def connect_scanner_analog(self):
        """
        connect to AWG devices
        """
        self.AWG = self._AWG.open_resource(self._ip)
        self.check_connection_analog()
        # self.single_angle_mode_analog()

    def check_connection_analog(self):
        """
        check connection with AWG
        '*IDN?' Get information from AWG connection
        :return: none
        """
        self._state = self.AWG.query('*IDN?')
        print(self._state)

    def single_angle_mode_analog(self, axis):
        """
        set the channel of AWG output as DC, using the offset to move the x/y mirror
        ':SOUR[<AxisID>]:FUNC <name>' Set AWG output as wave function
        '1' for x-axis, '2' for y-axis.
        DC/SIN/RAMP/SQU normal use function
        ':SOUR[<AxisID>]:VOLT:OFFS <voltage>' set the output voltage offset as 0Vdc
        ':OUTP[<AxisID>] [STATE]' open or close the output channel
        {ON|1|OFF|0} four choose, 1=ON, 0=OFF
        """
        self.AWG.write(':SOUR' + axis + ':FUNC DC')
        self.AWG.write(':SOUR' + axis + ':VOLT:OFFS 0')
        self.AWG.write(':OUTP' + axis + ' ON')
        # self.AWG.write(':SOUR2:FUNC DC')
        # self.AWG.write(':SOUR2:VOLT:OFFS 0')
        # self.AWG.write(':OUTP2 ON')

    def single_angle_mode_analog_close(self, axis):
        self.AWG.write(':OUTP' + axis + ' OFF')

    def close_scanner_analog(self):
        self._AWG.close()
        self.AWG = None

    def read_angle_analog(self, axis):
        """
        Reads the angle from x/y mirror.
        Later, such value should be read out from controller J4 pos feedback voltage
        current use AWG output value to label the position of x/y mirror
        Args:
        axis (string): '1' for x-axis, '2' for y-axis.
        ':SOUR[<AxisID>]:APPL?' Get information of AWG output channel, for example, output form "DC,DEV,DEV,1.000000E+00"
        last one is voltage, 有效数字 7 位，如 1.000000E+00，表示波形偏移电压值为 1VDC
        Returns: float position of the mover.
        """
        self._channel_state = self.AWG.query(':SOUR' + axis + ':APPL?')
        self._angle = self._channel_state.replace('"','').split(',')[3]
        return float(self._angle)

    def mov_angle_analog(self, axis, angle):
        """
        Scan the mirror.
        Args:
        axis: '1' for x-axis, '2' for y-axis.
        angle: float voltage of the mirror (1V/mech ang).
        MOV {<AxisID> <Position>} Set Target voltage
        Returns: None
        """
        # send voltage
        self.AWG.write(':SOUR' + axis + ':VOLT:OFFS '+ str(angle))
        # current work on open loop
        # using PID to reach close loop
        # if accuracy is None:
        #     accuracy = self.accuracy
        # pos = self.read_pos(axis)
        # while abs(pos-location) > accuracy:
        #     pos = self.read_pos(axis)
            # wait
            # sleep(0.02)

    def scan_mode_analog(self, angle_min, angle_max, freq=10):
        """
        We use ramp function to do scan x-axis, freq 10Hz
        :param angle_min: the min voltage for start scan
        :param angle_max: the max voltage for start scan
        :param freq: each line scan frequency, 10Hz means 100ms per line
        we set symmetry as 80%, the scan for each line is around 80ms for fluorescence read
        :return: None
        """
        self.mov_angle_analog('1', angle_min)
        self.single_angle_mode_analog_close('1')
        self.AWG.write(':SOUR1:FUNC RAMP')  # setup Ch1 as ramp
        self.AWG.write(':SOUR1:FREQ ' + str(freq))  # setup Ch1 wave frequency as 10Hz
        self.AWG.write(':SOUR1:VOLT:LOW ' + str(angle_min)) # setup Ch1 low voltage
        self.AWG.write(':SOUR1:VOLT:HIGH ' + str(angle_max))  # setup Ch1 high voltage
        self.AWG.write(':SOUR1:FUNC:RAMP:SYMM 80') # setup Ch1 symmetry as 80%
        self.AWG.write(':SOUR1:PHAS 216') # setup Ch1 phase as 216 degree

    def scan_mode_sin_analog(self, angle_min, angle_max, freq=10):
        """
        Rising half (angle_min -> angle_max) is the forward scan,
        falling half (angle_max -> angle_min) is the flyback, so it is always 50/50
        :param angle_min: the min voltage for start scan
        :param angle_max: the max voltage for start scan
        :param freq: each line scan frequency (one full sine period per line)
        """
        self.mov_angle_analog('1', angle_min)
        self.single_angle_mode_analog_close('1')
        self.AWG.write(':SOUR1:FUNC SIN')  # setup Ch1 as sine
        self.AWG.write(':SOUR1:FREQ ' + str(freq))
        self.AWG.write(':SOUR1:VOLT:LOW ' + str(angle_min))
        self.AWG.write(':SOUR1:VOLT:HIGH ' + str(angle_max))
        self.AWG.write(':SOUR1:PHAS 270')  # sine minimum is at 270 degree, start the burst there

    def scanning_analog(self):
        """
        use burst mode to trigger the AWG
        ':SOUR1:BURS:TRIG:SOUR MAN' Manual source
        ':SOUR1:BURS:TRIG' 手动触发
        :return: None
        """
        self.AWG.write(':SOUR1:BURS ON') # open Ch1 bust mode
        # n circles mode
        # self.AWG.write(':SOUR1:BURS:MODE TRIG')  # choose the burst mode: n circles
        # self.AWG.write(':SOUR1:BURS:NCYC 1')   # circles number 1
        # self.AWG.write(':SOUR1:BURS:INT:PER 0.101') # period burst > period of ramp * circle number + 2 us
        # Gated mode
        self.AWG.write(':SOUR1:BURS:MODE GAT')  # choose the burst mode: n circles
        self.AWG.write(':SOUR1:BURS:GATE:POL NORM') # 设置 CH1 的门控脉冲串的门控极性为正极性
        # self.AWG.write(':SOUR1:BURS:PHAS 216')  # phase
        self.AWG.write(':SOUR1:BURS:TRIG:SOUR EXT')  # set the trigger source as external source
        self.AWG.write(':SOUR1:BURS:TDEL 0') # set the delay time between trigger and output
        self.AWG.write(':SOUR1:BURS:TRIG:SLOP POS') # set the rising edge as trigger
        self.AWG.write(':SOUR1:BURS:TRIG:TRIGO OFF')  # turn off the trigger output in the burst condition
        self.AWG.write(':OUTP1 ON')

    def scanning_analog_close(self):
        self.AWG.write(':SOUR1:BURS OFF')  # close Ch1 bust mode


if __name__ == '__main__':
    Scanner = SCANNER()
    time.sleep(10)
    Scanner.connect_scanner_analog()
    Scanner.single_angle_mode_analog()
    Scanner.scan_mode_analog(-1,2)
    Scanner.scanning_analog()
    time.sleep(10)
    Scanner.scanning_analog_close()
    Scanner.single_angle_mode_analog()
    Scanner.single_angle_mode_analog_close('1')
    # angle = Scanner.read_angle_analog('1')
    # print(angle)
    # Scanner.mov_angle_analog('1',0.001)
    # angle = Scanner.read_angle_analog('1')
    # print(angle)



