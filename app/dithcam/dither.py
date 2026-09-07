# Provides custom dithering algorithms mapping to a strict four-shade palette.
#
# Custom implementations are required because standard firmware dithers (e.g., c64)
# use arbitrary palettes. To guarantee that exported PNGs are byte-for-byte identical
# to the display, all values must strictly map to [0, 85, 170, 255].
#
# Dithering is applied in-place to the raw framebuffer or image buffer.
from array import array

from dither_fast import flat_row, ordered_row, floyd_row, atkinson_row

SHADES = (0, 85, 170, 255)
STEP = 85                       # the gap between adjacent shades

ORDERED = 0
FLOYD = 1
ATKINSON = 2
FLAT = 3
MODES = (ORDERED, FLOYD, ATKINSON, FLAT)

# Bayer 4x4, the classic ordered threshold matrix. Flattened row-major so a
# viper kernel can index one row of it without a second dimension.
BAYER = bytes((0, 8, 2, 10,
               12, 4, 14, 6,
               3, 11, 1, 9,
               15, 7, 13, 5))

# Input level to nearest shade. Built once; keeps division out of the kernels.
QUANT = bytearray(256)
for _i in range(256):
    QUANT[_i] = SHADES[(_i * 3 + 127) // 255]

_rows = {}                      # width -> the error rows that width needs


def _error_rows(w):
    """Three int32 rows, reused across frames. Two extra cells either side so
    the diffusion kernels can write past the edges without bounds checks."""
    got = _rows.get(w)
    if got is None:
        got = tuple(array("i", bytearray(4 * (w + 4))) for _ in range(3))
        _rows[w] = got
    return got


def _clear(row):
    for i in range(len(row)):
        row[i] = 0


def apply(raw, stride, x0, y0, w, h, mode):
    """Dither a rectangle of `raw` in place, in the given mode.

    The geometry is coerced here because this is the boundary to viper, whose
    pointer arithmetic takes integers only - and a rect's attributes come back
    as floats, so passing one straight through raises TypeError.
    """
    x0, y0, w, h = int(x0), int(y0), int(w), int(h)
    if mode == ORDERED:
        for y in range(h):
            ordered_row(raw, (y0 + y) * stride + x0 * 4, w, QUANT,
                        BAYER, (y & 3) * 4, STEP)
        return
    if mode == FLAT:
        for y in range(h):
            flat_row(raw, (y0 + y) * stride + x0 * 4, w, QUANT)
        return

    cur, nxt, nxt2 = _error_rows(w)
    _clear(cur)
    _clear(nxt)
    _clear(nxt2)
    if mode == FLOYD:
        for y in range(h):
            floyd_row(raw, (y0 + y) * stride + x0 * 4, w, QUANT, cur, nxt)
            cur, nxt = nxt, cur
            _clear(nxt)
    else:
        for y in range(h):
            atkinson_row(raw, (y0 + y) * stride + x0 * 4, w, QUANT, cur, nxt, nxt2)
            cur, nxt, nxt2 = nxt, nxt2, cur
            _clear(nxt2)
