# Retry of the downsize test with the command numbers the datasheet's detailed
# sections give, rather than the ones its summary table gives.
#
# The summary table says DOWNSIZE_CTRL 0x54 / DOWNSIZE_STATUS 0x55. Sections
# 1.3.2.27 and 1.3.2.28 say set is 0x53 ("0x56+0x00+0x53+0x01+0x05 the width
# and height will be the half of previous attribute") and get is 0x54. The
# first probe wrote its ratio into the *read* command, which is exactly why the
# status echoed back whatever was sent while the frame size never moved.
#
# If this works: leave the sensor at 320x240 and halve it to 160x120 for the
# live preview with no reset, then take the capture at full 320x240.
#
# Run with:  mpremote run probe_downsize2.py
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import vc0706
from vc0706 import VC0706, CameraError

DOWNSIZE_SET = 0x53             # 1.3.2.27, one ratio byte
DOWNSIZE_GET = 0x54             # 1.3.2.28, no payload, returns one byte

# bits[1:0] width, bits[3:2] height; 00 = 1:1, 01 = 1:2, 10 = 1:4.
# Height zoom may not exceed width zoom, and the result must stay a multiple
# of 16 wide and 8 high - 320x240 halved is 160x120, which satisfies both.
FULL = 0x00
HALF = 0x05
READ_FBUF = 0x32


def uart(baud):
    return UART(1, baudrate=baud, tx=Pin(4), rx=Pin(5), timeout=1000, rxbuf=2048)


def find_camera():
    for baud in (115200, 38400):
        c = VC0706(uart(baud))
        try:
            c.version()
            return c
        except CameraError:
            pass
    raise SystemExit("no reply at either baud")


def read_frame(c, length, chunk=256):
    """Rounds the tail up and trims, so the EOI marker survives."""
    out = bytearray()
    addr = 0
    while addr < length:
        want = min(chunk, length - addr)
        n = (want + 7) & ~7
        c._send(READ_FBUF, bytes([0x00, 0x0A,
                                  (addr >> 24) & 0xFF, (addr >> 16) & 0xFF,
                                  (addr >> 8) & 0xFF, addr & 0xFF,
                                  (n >> 24) & 0xFF, (n >> 16) & 0xFF,
                                  (n >> 8) & 0xFF, n & 0xFF, 0x00, 0x0A]))
        head = c._read_exact(5)
        if len(head) < 5 or head[0] != 0x76 or head[3] != 0x00:
            raise CameraError("fbuf @%d" % addr)
        data = c._read_exact(n)
        if len(data) != n:
            raise CameraError("fbuf @%d short" % addr)
        out.extend(data)
        c._read_exact(5)
        addr += want
    return bytes(out[:length])


def set_ratio(c, ratio):
    c._run(DOWNSIZE_SET, bytes([ratio]))


def get_ratio(c):
    return c._run(DOWNSIZE_GET, b"", 1)[5]


def shot(c, tag):
    c.take_picture()
    length = c.frame_length()
    t0 = time.ticks_ms()
    data = read_frame(c, length)
    ms = time.ticks_diff(time.ticks_ms(), t0)
    c.resume()
    with open("/ds_%s.jpg" % tag, "wb") as f:
        f.write(data)
    print("    %-10s %6d B  read %5d ms  EOI %s"
          % (tag, len(data), ms, "yes" if data[-2:] == b"\xff\xd9" else "NO"))
    return len(data)


cam = find_camera()
cam.color_mode(2)
print("setting 320x240 base (one reset)")
cam.set_image_size(vc0706.SIZE_320x240)
cam.reset()
time.sleep(2.5)
cam = VC0706(uart(38400))
cam.set_baud(115200)
cam = VC0706(uart(115200))
print("  version:", cam.version())

print("\nratio FULL (0x00) - expect ~12kB")
set_ratio(cam, FULL)
print("    get_ratio ->", hex(get_ratio(cam)))
full = shot(cam, "full")

print("\nratio HALF (0x05) via 0x53, NO reset - expect ~3.5kB if it works")
set_ratio(cam, HALF)
print("    get_ratio ->", hex(get_ratio(cam)))
half = shot(cam, "half")

print("\nback to FULL (0x00), NO reset - expect ~12kB again")
set_ratio(cam, FULL)
print("    get_ratio ->", hex(get_ratio(cam)))
again = shot(cam, "full2")

print("\nverdict:")
if half < full * 0.6 and again > full * 0.6:
    print("  DOWNSIZE WORKS LIVE - fast preview + full capture is on")
else:
    print("  no size change: %d -> %d -> %d" % (full, half, again))

cam.set_image_size(vc0706.SIZE_160x120)
cam.reset()
time.sleep(2.0)
print("restored 160x120 for the app")
