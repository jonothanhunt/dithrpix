# Replicate start_camera() step by step with timings, to find which call the
# app is blocking on. Every step is bounded, so this cannot itself hang.
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import vc0706
from vc0706 import VC0706, CameraError

BOOT_BUDGET_MS = 8000
PROBE_MS = 300


def uart(baud):
    return UART(1, baudrate=baud, tx=Pin(4), rx=Pin(5), timeout=1000, rxbuf=2048)


def step(name, fn):
    t0 = time.ticks_ms()
    try:
        r = fn()
        print("  %-28s %5dms  %s" % (name, time.ticks_diff(time.ticks_ms(), t0),
                                     r if r is not None else "ok"))
        return r
    except Exception as e:
        print("  %-28s %5dms  %s: %s" % (name, time.ticks_diff(time.ticks_ms(), t0),
                                         type(e).__name__, e))
        return None


def wait_ready(c, label):
    deadline = time.ticks_add(time.ticks_ms(), BOOT_BUDGET_MS)
    tries = 0
    t0 = time.ticks_ms()
    while True:
        tries += 1
        try:
            v = c.version(PROBE_MS)
            print("  %-28s %5dms  %s after %d tries"
                  % (label, time.ticks_diff(time.ticks_ms(), t0), v, tries))
            return v
        except CameraError as e:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                print("  %-28s %5dms  GAVE UP after %d tries: %s"
                      % (label, time.ticks_diff(time.ticks_ms(), t0), tries, e))
                return None
            time.sleep_ms(200)


print("start_camera(), step by step")
c = VC0706(uart(38400))
wait_ready(c, "wait_ready @38400")
step("color_mode(2)", lambda: c.color_mode(2))
step("set_image_size(320x240)", lambda: c.set_image_size(vc0706.SIZE_320x240))
step("reset()", lambda: c.reset())
c = VC0706(uart(38400))
wait_ready(c, "wait_ready after reset")
step("set_baud(115200)", lambda: c.set_baud(115200))
c = VC0706(uart(115200))
wait_ready(c, "wait_ready @115200")

print()
print("one frame end to end")
step("take_picture", lambda: c.take_picture())
n = step("frame_length", lambda: c.frame_length())
if n:
    data = step("read_frame", lambda: c.read_frame(n, 256))
    if data:
        print("  EOI:", "yes" if data[-2:] == b"\xff\xd9" else "NO")
step("resume", lambda: c.resume())
step("power_save(True)", lambda: c.power_save(True))
print("done")
