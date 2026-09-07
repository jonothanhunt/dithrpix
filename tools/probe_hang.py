# Where is the app blocking? Test the two things that changed, in isolation,
# each with its own ceiling so nothing here can hang.
import sys
import time

sys.path.insert(0, "/system/apps/dithcam")
from machine import UART, Pin

print("1. open UART and watch what the camera emits on power-up")
u = UART(1, baudrate=38400, tx=Pin(4), rx=Pin(5), timeout=1000, rxbuf=2048)
total = 0
spins = 0
t0 = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), t0) < 4000:
    n = u.any()
    if n:
        total += len(u.read(n) or b"")
        spins += 1
    time.sleep_ms(10)
print("   %d bytes over 4s in %d bursts - a drain loop only ends when this "
      "reaches 0" % (total, spins))

print()
print("2. is uart.any() ever actually zero?")
zero = 0
for _ in range(50):
    if u.any() == 0:
        zero += 1
    time.sleep_ms(20)
print("   any()==0 on %d of 50 samples" % zero)

print()
print("3. does the camera answer version() now?")
import vc0706
from vc0706 import VC0706, CameraError
c = VC0706(u)
for attempt in range(5):
    try:
        t0 = time.ticks_ms()
        v = c.version(500)
        print("   attempt %d: %s after %dms" % (attempt, v,
                                                time.ticks_diff(time.ticks_ms(), t0)))
        break
    except CameraError as e:
        print("   attempt %d: %s" % (attempt, e))
        time.sleep_ms(300)

print()
print("4. viper dither kernels on a small buffer")
import picovector as pv
import dither
im = pv.image(32, 16)
im.pen = pv.color.rgb(128, 128, 128)
im.rectangle(0, 0, 32, 16)
for mode in dither.MODES:
    t0 = time.ticks_ms()
    dither.apply(im.raw, im.stride, 0, 0, 32, 16, mode)
    print("   mode %d ok in %dms" % (mode, time.ticks_diff(time.ticks_ms(), t0)))

print()
print("5. viper dither at full view size (234x176) - the real cost")
big = pv.image(234, 176)
big.pen = pv.color.rgb(128, 128, 128)
big.rectangle(0, 0, 234, 176)
for mode in dither.MODES:
    big.pen = pv.color.rgb(128, 128, 128)
    big.rectangle(0, 0, 234, 176)
    t0 = time.ticks_ms()
    dither.apply(big.raw, big.stride, 0, 0, 234, 176, mode)
    print("   mode %d: %dms" % (mode, time.ticks_diff(time.ticks_ms(), t0)))

print("done")
