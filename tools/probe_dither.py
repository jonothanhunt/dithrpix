# What dithering does this firmware actually offer, and can each option be
# pinned to our four shades?
#
# The rule the whole app rests on is that a photo is stored exactly as the
# panel shows it, so any algorithm we offer must land on [0, 85, 170, 255] and
# nothing else. The stylised filters (c64, cga) probably impose their
# own palettes - which would break that - so every candidate is checked by
# looking at the values it actually produces, not by its name.
#
# Also renders a gradient swatch at the size the rail cell would use, to see
# whether a pattern is even legible that small.
import picovector as pv

SHADES = [0, 85, 170, 255]
PALETTE = [pv.color.rgb(v, v, v) for v in SHADES]
W, H = 64, 32                   # big enough to judge the pattern
CELL_W, CELL_H = 11, 14         # the actual rail cell


def gradient(w, h):
    """A left-to-right ramp: every input level appears, so a dither has
    something to work with at all four shades."""
    im = pv.image(w, h)
    for x in range(w):
        v = int(255 * x / max(w - 1, 1))
        im.pen = pv.color.rgb(v, v, v)
        im.rectangle(x, 0, 1, h)
    return im


def values(im, w, h):
    raw, stride = im.raw, im.stride
    seen = set()
    for y in range(h):
        base = y * stride
        for x in range(w):
            seen.add(raw[base + x * 4])
    return sorted(seen)


print("candidate filters on an image instance:")
probe = pv.image(4, 4)
for name in ("dither", "palette_dither", "onebit", "monochrome", "threshold",
             "duotone", "c64", "cga", "contrast", "window", "invert"):
    print("  %-16s %s" % (name, "yes" if hasattr(probe, name) else "no"))

print()
print("calling each, and checking what values come out")
print("(anything other than [0, 85, 170, 255] cannot be stored as-is)")


def attempt(label, apply):
    im = gradient(W, H)
    try:
        apply(im)
    except Exception as e:
        print("  %-34s %s: %s" % (label, type(e).__name__, e))
        return
    got = values(im, W, H)
    ok = got == SHADES
    print("  %-34s %-2d values %s %s"
          % (label, len(got), got[:8], "<- ours" if ok else ""))


for strength in (0, 64, 128, 255):
    attempt("palette_dither(SHADES, %d)" % strength,
            lambda im, s=strength: im.palette_dither(PALETTE, s))

for args in ((), (PALETTE,), (PALETTE, 128), (4,), (128,)):
    attempt("dither%s" % (args,), lambda im, a=args: im.dither(*a))

attempt("onebit()", lambda im: im.onebit())
attempt("monochrome()", lambda im: im.monochrome())
attempt("threshold(128, 0, 255)", lambda im: im.threshold(128, 0, 255))
attempt("c64()", lambda im: im.c64())
attempt("cga()", lambda im: im.cga())

print()
print("swatch legibility at the rail cell size (%dx%d):" % (CELL_W, CELL_H))
sw = gradient(CELL_W, CELL_H)
sw.palette_dither(PALETTE, 128)
raw, stride = sw.raw, sw.stride
for y in range(CELL_H):
    row = "".join(" .:#"[SHADES.index(raw[y * stride + x * 4])]
                  if raw[y * stride + x * 4] in SHADES else "?"
                  for x in range(CELL_W))
    print("    |%s|" % row)
