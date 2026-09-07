# Two questions:
#   1. Is frame_length() being read before the DSP has finished the frame?
#      Two of four probe frames came back with no EOI marker, both at the
#      larger sizes, after a "capture" that reported 4-12ms.
#   2. Does DOWNSIZE_CTRL really change resolution with no reset?
#
# Run with:  mpremote run probe_settle.py
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import vc0706
from vc0706 import VC0706, CameraError

DOWNSIZE_CTRL = 0x54
DOWNSIZE_STATUS = 0x55

# The same values set_image_size writes to register 0x0019 - which is the
# clue: "image size" on this part appears to *be* a downsize of the sensor's
# native 640x480, which is why 0x00 produced the biggest frame.
FULL_640 = 0x00
HALF_320 = 0x11
QUARTER_160 = 0x22
NAMES = {FULL_640: "640x480", HALF_320: "320x240", QUARTER_160: "160x120"}


def uart(baud):
    return UART(1, baudrate=baud, tx=Pin(4), rx=Pin(5), timeout=1000, rxbuf=2048)


def find_camera():
    for baud in (115200, 38400):
        c = VC0706(uart(baud))
        try:
            c.version()
            return c, baud
        except CameraError:
            pass
    raise SystemExit("no reply at either baud")


def settle_test(c, settle_ms):
    """Take a picture, wait, then see whether the reported length has stopped
    moving and whether the JPEG we pull actually ends in FFD9."""
    c.take_picture()
    if settle_ms:
        time.sleep_ms(settle_ms)
    first = c.frame_length()
    time.sleep_ms(60)
    second = c.frame_length()
    data = c.read_frame(first, 256)
    c.resume()
    ends_ok = data[-2:] == b"\xff\xd9"
    print("    settle %4dms  len %6d -> %6d %-8s  EOI %s"
          % (settle_ms, first, second,
             "STABLE" if first == second else "GREW",
             "yes" if ends_ok else "NO"))
    return first == second and ends_ok


cam, baud = find_camera()
print("camera at %d baud" % baud)
cam.color_mode(2)

for size in (QUARTER_160, HALF_320, FULL_640):
    print("\n%s via DOWNSIZE_CTRL, no reset:" % NAMES[size])
    cam._run(DOWNSIZE_CTRL, bytes([size]))
    status = cam._run(DOWNSIZE_STATUS, b"", 1)[5]
    print("  status reads %#04x (asked for %#04x)" % (status, size))
    for settle in (0, 50, 150, 300):
        try:
            settle_test(cam, settle)
        except CameraError as e:
            print("    settle %4dms  ERROR %s" % (settle, e))

print("\nback to 160x120 for the app")
cam._run(DOWNSIZE_CTRL, bytes([QUARTER_160]))
cam.power_save(True)
print("done")
