# Two things, both small enough not to blow the heap:
#
# 1. Is 320x240 stable over repeated captures? The wild frame sizes in the
#    last probe followed writes to 0x54/0x55, but they need ruling out as a
#    property of 320x240 itself before the app moves to it.
# 2. Does blit average when it shrinks? Uses a 64x48 source rather than the
#    320x240 one that crashed the board - the question is about the sampling
#    rule, and that does not depend on the size.
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin
import picovector as pv
import vc0706
from vc0706 import VC0706, CameraError


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


print("=== 1. stability at 320x240 ===")
cam = find_camera()
cam.color_mode(2)
cam.set_image_size(vc0706.SIZE_320x240)
cam.reset()
time.sleep(2.5)
cam = VC0706(uart(38400))
cam.set_baud(115200)
cam = VC0706(uart(115200))
print("version:", cam.version())

for i in range(5):
    cam.take_picture()
    length = cam.frame_length()
    t0 = time.ticks_ms()
    data = cam.read_frame(length, 256)      # the driver on the badge is fixed
    ms = time.ticks_diff(time.ticks_ms(), t0)
    cam.resume()
    print("  shot %d: %6d B  read %5d ms  EOI %s"
          % (i + 1, len(data), ms, "yes" if data[-2:] == b"\xff\xd9" else "NO"))
    del data

cam.set_image_size(vc0706.SIZE_160x120)
cam.reset()
time.sleep(2.0)
print("restored 160x120")

print()
print("=== 2. does blit average when it shrinks? ===")
SRC_W, SRC_H = 64, 48
DST_W, DST_H = 47, 35


def histogram(im, w, h):
    raw, stride = im.raw, im.stride
    seen = {}
    for y in range(h):
        base = y * stride
        for x in range(w):
            v = raw[base + x * 4]
            seen[v] = seen.get(v, 0) + 1
    return sorted(seen)


src = pv.image(SRC_W, SRC_H)
src.pen = pv.color.rgb(255, 255, 255)
src.rectangle(0, 0, SRC_W, SRC_H)
src.pen = pv.color.rgb(0, 0, 0)
for x in range(0, SRC_W, 2):                # 1px stripes: the worst case
    src.rectangle(x, 0, 1, SRC_H)
print("source values:", histogram(src, SRC_W, SRC_H))

for name, aa in (("OFF", pv.image.OFF), ("X2", pv.image.X2), ("X4", pv.image.X4)):
    dst = pv.image(DST_W, DST_H)
    dst.antialias = aa
    dst.blit(src, pv.rect(0, 0, SRC_W, SRC_H), pv.rect(0, 0, DST_W, DST_H))
    values = histogram(dst, DST_W, DST_H)
    print("  antialias %-3s -> %2d values %s%s"
          % (name, len(values), values[:10], " ..." if len(values) > 10 else ""))
    del dst

print()
print("more than 2 values means it averages; exactly 2 means nearest-neighbour")
