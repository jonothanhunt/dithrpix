# Provides post-processing tone mapping for auto-exposed camera frames.
# Operates directly on the RGBA framebuffer (stride 1056 for 264x176) to map
# selected dynamic range slices to the display palette.
from tone_fast import row as _row

_cache = {}


def lut(lo, hi):
    key = (lo, hi)
    if key not in _cache:
        table = bytearray(256)
        span = hi - lo
        for i in range(256):
            v = (i - lo) * 255 // span
            table[i] = 0 if v < 0 else (255 if v > 255 else v)
        _cache[key] = table
    return _cache[key]


def apply(raw, stride, x0, w, h, lo, hi):
    if lo == 0 and hi == 255:
        return                      # identity, nothing to do
    table = lut(lo, hi)
    for y in range(h):
        _row(raw, y * stride + x0 * 4, w, table)
