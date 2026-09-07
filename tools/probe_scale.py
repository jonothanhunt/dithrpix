# Does blit average when it shrinks, or just drop pixels?
#
# It decides whether moving to 320x240 helps. Downsampling 320->234 with a
# nearest-neighbour blit would alias and could look worse than the 160->234
# upscale we do now; area-averaging is what makes the extra detail pay.
#
# Method: a 1px-pitch vertical stripe pattern is the worst case. Shrink it and
# look at the histogram. Nearest sampling can only ever return the two source
# values; any averaging shows up as intermediate greys.
import picovector as pv

SRC_W, SRC_H = 320, 240
DST_W, DST_H = 234, 176


def stripes():
    im = pv.image(SRC_W, SRC_H)
    im.pen = pv.color.rgb(255, 255, 255)
    im.rectangle(0, 0, SRC_W, SRC_H)
    im.pen = pv.color.rgb(0, 0, 0)
    for x in range(0, SRC_W, 2):
        im.rectangle(x, 0, 1, SRC_H)
    return im


def histogram(im, w, h):
    raw, stride = im.raw, im.stride
    seen = {}
    for y in range(0, h, 4):
        base = y * stride
        for x in range(w):
            v = raw[base + x * 4]
            seen[v] = seen.get(v, 0) + 1
    return sorted(seen.items())


src = stripes()
print("source distinct values:", [v for v, _ in histogram(src, SRC_W, SRC_H)])

for aa_name, aa in (("OFF", pv.image.OFF), ("X2", pv.image.X2), ("X4", pv.image.X4)):
    dst = pv.image(DST_W, DST_H)
    dst.antialias = aa
    dst.blit(src, pv.rect(0, 0, SRC_W, SRC_H), pv.rect(0, 0, DST_W, DST_H))
    values = [v for v, _ in histogram(dst, DST_W, DST_H)]
    print("antialias %-3s -> %2d distinct values %s"
          % (aa_name, len(values), values[:12]))

print()
print("image.window signature probe:")
test = pv.image(16, 16)
test.pen = pv.color.rgb(128, 128, 128)
test.rectangle(0, 0, 16, 16)
for args in ((0, 255), (64, 192), (0, 255, 0, 255)):
    probe = pv.image(16, 16)
    probe.pen = pv.color.rgb(128, 128, 128)
    probe.rectangle(0, 0, 16, 16)
    try:
        probe.window(*args)
        print("  window%s ok -> centre pixel %d" % (args, probe.raw[8 * probe.stride + 8 * 4]))
    except Exception as e:
        print("  window%s -> %s: %s" % (args, type(e).__name__, e))
