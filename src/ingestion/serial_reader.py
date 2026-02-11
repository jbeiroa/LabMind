import os
import queue
import serial
import serial.tools.list_ports
import threading
import time
import requests


class ArduinoSerial:    
    def __init__(self, port=None, baudrate=115200, timeout=1, 
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
        self.connection.reset_input_buffer()
        self.connection.reset_output_buffer()
        print(f"Connected to Arduino on {self.port}")

    def read_data(self):
        """Read and return data from the serial port."""
        if self.connection and self.connection.in_waiting:
            return self.connection.readline().decode(errors="ignore").strip()
        return None

    def write_data(self, data):
        """Send data to the Arduino."""
        if self.connection:
            self.connection.reset_input_buffer()
            self.connection.write(data.encode())

    def disconnect(self):
        """Close the connection."""
        if self.connection:
            self.connection.close()
            print("Disconnected from Arduino")


def parse_reading_line(raw_line):
    parts = raw_line.split(",", maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Malformed reading: {raw_line!r}")
    timestamp_text, value_text = parts
    return int(timestamp_text), float(value_text)


class ReadingSender:
    def __init__(
        self,
        ingest_batch_url,
        request_timeout_s=2,
        batch_size=25,
        flush_interval_s=0.2,
        max_queue_size=5000,
    ):
        self.ingest_batch_url = ingest_batch_url
        self.request_timeout_s = request_timeout_s
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.sent_count = 0
        self.dropped_count = 0

    def start(self):
        self.thread.start()

    def enqueue(self, payload):
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self.dropped_count += 1
            if self.dropped_count % 100 == 0:
                print(f"Dropped {self.dropped_count} readings due to full queue")

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _send_batch(self, batch):
        response = requests.post(
            self.ingest_batch_url, json=batch, timeout=self.request_timeout_s
        )
        response.raise_for_status()
        self.sent_count += len(batch)

    def _worker(self):
        batch = []
        last_flush = time.time()
        while not self.stop_event.is_set() or not self.queue.empty() or batch:
            timeout = max(0.01, self.flush_interval_s - (time.time() - last_flush))
            try:
                item = self.queue.get(timeout=timeout)
                batch.append(item)
            except queue.Empty:
                pass

            should_flush = (
                len(batch) >= self.batch_size
                or (batch and (time.time() - last_flush) >= self.flush_interval_s)
            )
            if should_flush:
                try:
                    self._send_batch(batch)
                except requests.RequestException as exc:
                    print(f"Failed to send batch of {len(batch)} readings: {exc}")
                batch = []
                last_flush = time.time()


if __name__ == "__main__":
    ingest_url = os.getenv("LABMIND_INGEST_URL", "http://localhost:8002/reading")
    ingest_batch_url = os.getenv(
        "LABMIND_INGEST_BATCH_URL", ingest_url.replace("/reading", "/readings")
    )
    request_timeout_s = float(os.getenv("LABMIND_INGEST_TIMEOUT_S", "2"))
    batch_size = int(os.getenv("LABMIND_BATCH_SIZE", "25"))
    flush_interval_s = float(os.getenv("LABMIND_BATCH_FLUSH_S", "0.2"))
    loop_duration = float(os.getenv("LABMIND_LOOP_DURATION_S", "5"))
    serial_baudrate = int(os.getenv("LABMIND_SERIAL_BAUD", "115200"))
    arduino = ArduinoSerial(baudrate=serial_baudrate)
    sender = ReadingSender(
        ingest_batch_url=ingest_batch_url,
        request_timeout_s=request_timeout_s,
        batch_size=batch_size,
        flush_interval_s=flush_interval_s,
    )
    try:
        sender.start()
        arduino.connect()
        # Retry start command in case board reset timing races the first write.
        for _ in range(3):
            arduino.write_data("s")
            time.sleep(0.1)
        start_time = time.time()
        parsed_count = 0
        while time.time() - start_time < loop_duration:
            r = arduino.read_data()
            if r is not None:
                try:
                    timestamp_ms, value = parse_reading_line(r)
                except ValueError as exc:
                    print(f"Skipping invalid serial row: {exc}")
                    continue

                payload = {
                    "device_id": "HC-SR04",
                    "timestamp_ms": timestamp_ms,
                    "value": value,
                }
                sender.enqueue(payload)
                parsed_count += 1
            else:
                time.sleep(0.001)
        arduino.write_data("p")
        print(
            "Acquisition complete. "
            f"parsed={parsed_count}, sent={sender.sent_count}, dropped={sender.dropped_count}"
        )
        if parsed_count == 0:
            print(
                "No readings parsed. Check Arduino sketch baud rate and command handling. "
                f"Current host baud={serial_baudrate}."
            )
    except KeyboardInterrupt:
        print("Exiting...")
        arduino.write_data("p")
    finally:
        sender.stop()
        arduino.disconnect()
