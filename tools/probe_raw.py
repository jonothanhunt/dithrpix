# The datasheet disagrees with itself about the downsize commands, and the
# camera disagrees with both. So: send each candidate, dump whatever comes
# back without validating it, and judge purely by whether the captured frame
# actually changes size. Frame size is ground truth; status registers have
# already lied to us once.
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import vc0706
from vc0706 import VC0706, CameraError

READ_FBUF = 0x32
FULL, HALF = 0x00, 0x05


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


def raw(c, cmd, payload=b"", wait_ms=300):
    """Send and dump the reply, whatever it is."""
    c._drain()
    c.uart.write(bytes([0x56, 0x00, cmd, len(payload)]) + payload)
    time.sleep_ms(wait_ms)
    got = c.uart.read(c.uart.any()) or b""
    return " ".join("%02X" % b for b in got) or "(nothing)"


def frame_size(c):
    """Capture and report the length only - cheap, and it is what matters."""
    try:
        c.take_picture()
        n = c.frame_length()
        c.resume()
        return n
    except CameraError as e:
        c.resume()
        return "error: %s" % e


cam = find_camera()
cam.color_mode(2)
print("base: 320x240 via set_image_size + reset")
cam.set_image_size(vc0706.SIZE_320x240)
cam.reset()
time.sleep(2.5)
cam = VC0706(uart(38400))
cam.set_baud(115200)
cam = VC0706(uart(115200))
print("  version:", cam.version())
print("  frame at 320x240:", frame_size(cam))

for cmd in (0x53, 0x54, 0x55):
    print("\n--- command %#04x" % cmd)
    print("  get  (no payload) ->", raw(cam, cmd))
    print("  set  HALF (0x05)  ->", raw(cam, cmd, bytes([HALF])))
    print("  frame after HALF  :", frame_size(cam))
    print("  set  FULL (0x00)  ->", raw(cam, cmd, bytes([FULL])))
    print("  frame after FULL  :", frame_size(cam))

print("\nrestoring 160x120 for the app")
cam.set_image_size(vc0706.SIZE_160x120)
cam.reset()
time.sleep(2.0)
print("done")
