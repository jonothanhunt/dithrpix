# A fair A/B of the same scene at 160x120 and 320x240, using a corrected
# frame read.
#
# Two things learned from the earlier probes:
#   * DOWNSIZE_CTRL echoes back in its status register but does not change the
#     actual output size without a reset - the frame stayed at 3652 bytes
#     whether we asked for 640x480, 320x240 or 160x120. So 0x54 is the same
#     register set_image_size already writes, by another route, and the "fast
#     preview, full capture, no reset" plan is off.
#   * read_frame drops the final 1-7 bytes whenever the frame length is not a
#     multiple of 8, which eats the JPEG's EOI marker. 3652 % 8 == 4, so every
#     frame in that probe came back truncated. That is a live bug in the app.
#
# Hold the camera still - the two shots are seconds apart and are meant to be
# the same scene.
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import vc0706
from vc0706 import VC0706, CameraError

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
    """As the driver's, but the tail is read rounded UP to the next multiple
    of 8 and then trimmed, rather than dropped. The alignment rule is about
    the transfer, not the payload, so over-reading into the frame buffer is
    harmless - whereas under-reading loses the end of the JPEG."""
    out = bytearray()
    addr = 0
    while addr < length:
        want = min(chunk, length - addr)
        n = (want + 7) & ~7                 # round up, never down
        payload = bytes([0x00, 0x0A,
                         (addr >> 24) & 0xFF, (addr >> 16) & 0xFF,
                         (addr >> 8) & 0xFF, addr & 0xFF,
                         (n >> 24) & 0xFF, (n >> 16) & 0xFF,
                         (n >> 8) & 0xFF, n & 0xFF,
                         0x00, 0x0A])
        c._send(READ_FBUF, payload)
        head = c._read_exact(5)
        if len(head) < 5 or head[0] != 0x76 or head[3] != 0x00:
            raise CameraError("fbuf @%d" % addr)
        data = c._read_exact(n)
        if len(data) != n:
            raise CameraError("fbuf @%d short %d/%d" % (addr, len(data), n))
        out.extend(data)
        c._read_exact(5)
        addr += want
    return bytes(out[:length])              # trim the over-read tail


def configure(size):
    c = find_camera()
    c.color_mode(2)
    c.set_image_size(size)
    c.reset()
    time.sleep(2.5)
    c = VC0706(uart(38400))
    c.set_baud(115200)
    c = VC0706(uart(115200))
    c.version()
    return c


def shot(c, tag):
    c.take_picture()
    length = c.frame_length()
    t0 = time.ticks_ms()
    data = read_frame(c, length)
    ms = time.ticks_diff(time.ticks_ms(), t0)
    c.resume()
    with open("/ab_%s.jpg" % tag, "wb") as f:
        f.write(data)
    print("  %-8s %6d B  read %5d ms  len%%8=%d  EOI %s"
          % (tag, len(data), ms, length % 8,
             "yes" if data[-2:] == b"\xff\xd9" else "NO"))


print("160x120 (what the app does today)")
cam = configure(vc0706.SIZE_160x120)
shot(cam, "160")

print("320x240 (same scene - hold still)")
cam = configure(vc0706.SIZE_320x240)
shot(cam, "320")

print("back to 160x120 for the app")
cam = configure(vc0706.SIZE_160x120)
cam.power_save(True)
print("done")
