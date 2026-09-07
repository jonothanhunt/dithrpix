# Viper-optimized row kernels for dithering algorithms.
# 
# Operates in-place on single rows of the RGBA framebuffer (4 bytes/pixel, R=G=B).
# Pre-computed 256-byte quantization lookup tables are utilized to avoid division 
# in the inner loop. Error diffusion modes maintain 16x scale integer error rows 
# to prevent rounding losses prior to final downshift.
import micropython


@micropython.viper
def flat_row(buf: ptr8, base: int, w: int, quant: ptr8):
    """No dithering: every pixel to its nearest shade. Posterised and stark."""
    x = 0
    while x < w:
        i = base + x * 4
        q = int(quant[int(buf[i])])
        buf[i] = q
        buf[i + 1] = q
        buf[i + 2] = q
        x += 1


@micropython.viper
def ordered_row(buf: ptr8, base: int, w: int, quant: ptr8,
                table: ptr8, row_offset: int, spread: int):
    """Bayer ordered dither. `table` is one 4-entry row of the 4x4 matrix,
    picked by the caller, so the kernel never needs to know y."""
    half = spread >> 1
    x = 0
    while x < w:
        i = base + x * 4
        v = int(buf[i]) + ((int(table[row_offset + (x & 3)]) * spread) >> 4) - half
        if v < 0:
            v = 0
        elif v > 255:
            v = 255
        q = int(quant[v])
        buf[i] = q
        buf[i + 1] = q
        buf[i + 2] = q
        x += 1


@micropython.viper
def floyd_row(buf: ptr8, base: int, w: int, quant: ptr8,
              cur: ptr32, nxt: ptr32):
    """Floyd-Steinberg: 7/16 right, 3/16 below-left, 5/16 below, 1/16
    below-right. The most detail of the four, with a fine organic grain.
    `cur` and `nxt` are w+2 wide so the edges need no special casing."""
    x = 0
    while x < w:
        i = base + x * 4
        v = int(buf[i]) + (cur[x + 1] >> 4)
        if v < 0:
            v = 0
        elif v > 255:
            v = 255
        q = int(quant[v])
        e = v - q
        buf[i] = q
        buf[i + 1] = q
        buf[i + 2] = q
        cur[x + 2] = cur[x + 2] + e * 7
        nxt[x] = nxt[x] + e * 3
        nxt[x + 1] = nxt[x + 1] + e * 5
        nxt[x + 2] = nxt[x + 2] + e
        x += 1


@micropython.viper
def atkinson_row(buf: ptr8, base: int, w: int, quant: ptr8,
                 cur: ptr32, nxt: ptr32, nxt2: ptr32):
    """Atkinson: an eighth of the error to each of six neighbours, so only
    three quarters of it is carried at all. Loses shadow and highlight detail
    on purpose, which is what gives it that crisp early-Mac contrast."""
    x = 0
    while x < w:
        i = base + x * 4
        v = int(buf[i]) + (cur[x + 1] >> 3)
        if v < 0:
            v = 0
        elif v > 255:
            v = 255
        q = int(quant[v])
        e = v - q
        buf[i] = q
        buf[i + 1] = q
        buf[i + 2] = q
        cur[x + 2] = cur[x + 2] + e
        cur[x + 3] = cur[x + 3] + e
        nxt[x] = nxt[x] + e
        nxt[x + 1] = nxt[x + 1] + e
        nxt[x + 2] = nxt[x + 2] + e
        nxt2[x + 1] = nxt2[x + 1] + e
        x += 1
