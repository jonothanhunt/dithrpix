# VC0706 driver for the PTC06 v3.1.
# Protocol structure:
#   send   56 00 <cmd> <len> [payload]
#   reply  76 00 <cmd> <status> <len> [data]
import time

RESET = 0x26
GEN_VERSION = 0x11
SET_PORT = 0x24
READ_FBUF = 0x32
GET_FBUF_LEN = 0x34
FBUF_CTRL = 0x36
READ_DATA = 0x30
WRITE_DATA = 0x31
POWER_SAVE_CTRL = 0x3E
COLOR_CTRL = 0x3C
AE_CTRL = 0x40

STOP_CURRENT = 0x00
RESUME = 0x03

SIZE_640x480 = 0x00
SIZE_320x240 = 0x11
SIZE_160x120 = 0x22

# Upper bound for frame size to prevent infinite loops on corrupted length data.
MAX_FRAME = 65536
READ_BUDGET_MS = 15000

BAUD_DIVIDER = {9600: 0xAEC8, 19200: 0x56E4, 38400: 0x2AF2,
                57600: 0x1C4C, 115200: 0x0DA6}


class CameraError(Exception):
    pass


class VC0706:
    def __init__(self, uart):
        self.uart = uart
        self.last_raw = b""

    # -- plumbing ---------------------------------------------------------
    def _drain(self):
        while self.uart.any():
            self.uart.read(self.uart.any())

    def _read_exact(self, n, timeout_ms=4000):
        buf = bytearray()
        end = time.ticks_add(time.ticks_ms(), timeout_ms)
        while len(buf) < n and time.ticks_diff(end, time.ticks_ms()) > 0:
            chunk = self.uart.read(min(n - len(buf), 512))
            if chunk:
                buf.extend(chunk)
        return bytes(buf)

    def _send(self, cmd, payload=b""):
        self._drain()
        self.uart.write(bytes([0x56, 0x00, cmd, len(payload)]) + payload)

    def _reply(self, cmd, extra=0, timeout_ms=4000):
        """Read the 5-byte header plus `extra` data bytes, and check it."""
        resp = self._read_exact(5 + extra, timeout_ms)
        self.last_raw = resp
        if len(resp) < 5:
            raise CameraError("short reply %d bytes: %s" % (len(resp), hexs(resp)))
        if resp[0] != 0x76 or resp[2] != cmd or resp[3] != 0x00:
            raise CameraError("bad reply: %s" % hexs(resp))
        return resp

    def _run(self, cmd, payload=b"", extra=0, timeout_ms=4000):
        self._send(cmd, payload)
        return self._reply(cmd, extra, timeout_ms)

    # -- commands ---------------------------------------------------------
    def version(self, timeout_ms=4000):
        """Returns firmware version. Can be used with a short timeout as a readiness probe."""
        resp = self._run(GEN_VERSION, b"", 11, timeout_ms)
        return bytes(resp[5:16]).decode()

    def reset(self):
        self._send(RESET, b"")
        time.sleep(0.2)
        self._drain()

    def set_baud(self, baud):
        d = BAUD_DIVIDER[baud]
        self._run(SET_PORT, bytes([0x01, (d >> 8) & 0xFF, d & 0xFF]))
        time.sleep(0.1)

    def set_image_size(self, size):
        # Takes effect only after a reset.
        self._run(WRITE_DATA, bytes([0x04, 0x01, 0x00, 0x19, size]))

    def color_mode(self, show_mode):
        """0 auto, 1 colour, 2 black-and-white. Control-by-UART is 0x01.
        Protocol sheet 1.3.2.17: 56 00 3C 02 <ctrl> <show>."""
        self._run(COLOR_CTRL, bytes([0x01, show_mode]))

    def read_sensor_reg(self, addr, width=1):
        """1.3.2.5: 56 00 30 05 02 <num> <width> <addr hi> <addr lo>."""
        resp = self._run(READ_DATA,
                         bytes([0x02, 0x01, width, (addr >> 8) & 0xFF, addr & 0xFF]),
                         width)
        return resp[5]

    def write_sensor_reg(self, addr, value, width=1):
        """1.3.2.6: 56 00 31 06 02 <num> <width> <addr hi> <addr lo> <data>."""
        self._run(WRITE_DATA,
                  bytes([0x02, 0x01, width, (addr >> 8) & 0xFF, addr & 0xFF, value]))

    def power_save(self, on):
        """Protocol sheet 1.3.2.19: 56 00 3E 03 <type 0> <by UART> <on/off>.
        Reduces the ~75mA continuous idle current draw."""
        self._run(POWER_SAVE_CTRL, bytes([0x00, 0x01, 0x01 if on else 0x00]))

    def take_picture(self):
        self._run(FBUF_CTRL, bytes([STOP_CURRENT]))

    def resume(self):
        self._run(FBUF_CTRL, bytes([RESUME]))

    def frame_length(self):
        resp = self._run(GET_FBUF_LEN, bytes([0x00]), 4)
        n = (resp[5] << 24) | (resp[6] << 16) | (resp[7] << 8) | resp[8]
        if n <= 0 or n > MAX_FRAME:
            raise CameraError("implausible frame length %d" % n)
        return n

    def read_frame(self, length, chunk=256, progress=None):
        """Reads JPEG data from the frame buffer.
        
        Addresses and transfer lengths must be multiples of 8. The final transfer 
        is rounded up to the nearest multiple of 8 to prevent truncation of the 
        JPEG EOI marker, and the over-read is trimmed before returning.
        """
        if chunk % 8:
            raise ValueError("chunk must be a multiple of 8")
        out = bytearray()
        addr = 0
        deadline = time.ticks_add(time.ticks_ms(), READ_BUDGET_MS)
        while addr < length:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                raise CameraError("frame read timed out at %d/%d" % (addr, length))
            want = min(chunk, length - addr)
            n = (want + 7) & ~7     # round up; the tail is trimmed on return
            # 00 = current frame buffer, 0A = MCU-driven transfer,
            # then addr(4), length(4), delay(2). The outer length byte is
            # added by _send - it must not be repeated here.
            payload = bytes([0x00, 0x0A,
                             (addr >> 24) & 0xFF, (addr >> 16) & 0xFF,
                             (addr >> 8) & 0xFF, addr & 0xFF,
                             (n >> 24) & 0xFF, (n >> 16) & 0xFF,
                             (n >> 8) & 0xFF, n & 0xFF,
                             0x00, 0x0A])
            self._send(READ_FBUF, payload)
            head = self._read_exact(5)
            if len(head) < 5 or head[0] != 0x76 or head[3] != 0x00:
                raise CameraError("fbuf @%d: %s" % (addr, hexs(head)))
            data = self._read_exact(n)
            if len(data) != n:
                raise CameraError("fbuf @%d short %d/%d" % (addr, len(data), n))
            out.extend(data)
            self._read_exact(5)     # trailing ack
            addr += want
            if progress:
                progress(addr, length)
        return bytes(out[:length])  # discard the rounding over-read


def hexs(b):
    return " ".join("%02X" % x for x in b) if b else "(nothing)"
