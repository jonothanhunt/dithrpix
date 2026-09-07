# Does the VC0703's built-in downsize work without a reset?
#
# If it does, the camera can sit at 320x240 permanently: halved for a fast
# live preview, full for the capture, with no 5s reset between the two. That
# would give better stills than the 160x120 we upscale today.
#
# Run with:  mpremote run probe_downsize.py
# Writes /probe_*.jpg for pulling off afterwards. Leaves /photos alone.
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import vc0706
from vc0706 import VC0706, CameraError

DOWNSIZE_CTRL = 0x54
DOWNSIZE_STATUS = 0x55

# bits 1-0 width, bits 3-2 height: 00 none, 01 half, 10 quarter
NONE, HALF = 0x00, 0x05


def uart(baud):
    return UART(1, baudrate=baud, tx=Pin(4), rx=Pin(5), timeout=1000, rxbuf=2048)


def find_camera():
    """The app leaves the camera at 115200, and interrupting the app does not
    reset it, so meet it wherever it actually is rather than assuming."""
    for baud in (115200, 38400):
        c = VC0706(uart(baud))
        try:
            print("found at %d: %s" % (baud, c.version()))
            return c
        except CameraError:
            pass
    raise SystemExit("no reply at either baud - power-cycle the badge")


def open_camera(size):
    c = find_camera()
    c.color_mode(2)
    c.set_image_size(size)
    c.reset()
    time.sleep(2.5)
    c = VC0706(uart(38400))
    c.set_baud(115200)
    c = VC0706(uart(115200))
    print("at 115200:", c.version())
    return c


def downsize_status(c):
    try:
        resp = c._run(DOWNSIZE_STATUS, b"", 1)
        return resp[5]
    except CameraError as e:
        return "unsupported (%s)" % e


def set_downsize(c, value):
    try:
        c._run(DOWNSIZE_CTRL, bytes([value]))
        return True
    except CameraError as e:
        print("  DOWNSIZE_CTRL %#04x rejected: %s" % (value, e))
        return False


def shot(c, tag):
    """One capture, timed end to end, written out for inspection."""
    t0 = time.ticks_ms()
    c.take_picture()
    length = c.frame_length()
    t1 = time.ticks_ms()
    data = c.read_frame(length, 256)
    t2 = time.ticks_ms()
    c.resume()
    capture_ms = time.ticks_diff(t1, t0)
    read_ms = time.ticks_diff(t2, t1)
    path = "/probe_%s.jpg" % tag
    with open(path, "wb") as f:
        f.write(data)
    print("  %-14s %6d B  capture %4d ms  read %5d ms  (%4.1f kB/s)  -> %s"
          % (tag, len(data), capture_ms, read_ms,
             len(data) / max(read_ms, 1), path))
    return len(data), capture_ms + read_ms


print("=== 320x240 ===")
cam = open_camera(vc0706.SIZE_320x240)
print("downsize status at start:", downsize_status(cam))
shot(cam, "320_full")

print("applying downsize HALF (no reset)...")
if set_downsize(cam, HALF):
    print("downsize status now:", downsize_status(cam))
    shot(cam, "320_half")
    print("restoring downsize NONE (no reset)...")
    set_downsize(cam, NONE)
    print("downsize status now:", downsize_status(cam))
    shot(cam, "320_restored")

print("=== 160x120 (what the app uses today) ===")
cam = open_camera(vc0706.SIZE_160x120)
shot(cam, "160_full")

cam.power_save(True)
print("done - camera parked")
