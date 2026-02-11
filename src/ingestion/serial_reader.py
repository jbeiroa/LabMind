import serial
import serial.tools.list_ports
import time


class ArduinoSerial:    
    def __init__(self, port=None, baudrate=9600, timeout=1, 
                 bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                 stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False,
                 inter_char_timeout=None):
        self.port = port if port else self.auto_detect_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.inter_char_timeout = inter_char_timeout
        self.connection = None

    @staticmethod
    def auto_detect_port():
        """Serial port autodetection.

        Raises:
            Exception: If no port/Arduino was detected.

        Returns:
            str: serial port device name
        """
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if ("Arduino" in port.description 
                or "tty" in port.device 
                or "COM" in port.device
                or "cu.usb" in port.device):
                print(f"Auto-detected Arduino on {port.device}")
                return port.device
        raise Exception("No Arduino detected. Please specify the port manually.")

    def connect(self):
        """Establish connection with the Arduino."""
        if not self.port:
            raise Exception("No available serial port found.")
        
        self.connection = serial.Serial(
            self.port, self.baudrate, timeout=self.timeout,
            bytesize=self.bytesize, parity=self.parity,
            stopbits=self.stopbits, xonxoff=self.xonxoff,
            rtscts=self.rtscts, interCharTimeout=self.inter_char_timeout
        )
        time.sleep(2)  # Allow Arduino to initialize
        print(f"Connected to Arduino on {self.port}")

    def read_data(self):
        """Read and return data from the serial port."""
        if self.connection and self.connection.in_waiting:
            return self.connection.readline().decode().strip()
        return None

    def write_data(self, data):
        """Send data to the Arduino."""
        self.connection.reset_input_buffer()
        if self.connection:
            self.connection.write(data.encode())

    def disconnect(self):
        """Close the connection."""
        if self.connection:
            self.connection.close()
            print("Disconnected from Arduino")

if __name__ == "__main__":
    arduino = ArduinoSerial()
    try:
        loop_duration = 5
        start_time = time.time()
        arduino.connect()
        arduino.write_data("s")
        while time.time() - start_time < loop_duration:
            r = arduino.read_data()
            if r is not None:
                print(r)
        arduino.write_data("p")
    except KeyboardInterrupt:
        print("Exiting...")
        arduino.write_data("p")
    finally:
        arduino.disconnect()