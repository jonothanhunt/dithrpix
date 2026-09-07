# Lightweight 2-bit indexed PNG exporter.
#
# Because MicroPython's zlib implementation lacks compression support, IDAT
# chunks are constructed using uncompressed deflate blocks. This produces
# valid, lossless PNGs compatible with standard decoders and image.load()
# without requiring significant RAM overhead.
SHADES = (0x00, 0x55, 0xAA, 0xFF)

INDEX = bytearray(256)
for _v in range(256):
    INDEX[_v] = 0 if _v < 43 else (1 if _v < 128 else (2 if _v < 213 else 3))


def _crc32(data):
    try:
        import binascii
        return binascii.crc32(data) & 0xFFFFFFFF
    except (ImportError, AttributeError):
        crc = 0xFFFFFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
        return crc ^ 0xFFFFFFFF


def _adler32(data):
    a, b = 1, 0
    for byte in data:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return (b << 16) | a


def _stored(data):
    """A zlib stream of uncompressed deflate blocks - no compressor needed."""
    out = bytearray(b"\x78\x01")
    pos, n = 0, len(data)
    while True:
        chunk = min(65535, n - pos)
        final = 1 if pos + chunk >= n else 0
        out.append(final)
        out += bytes((chunk & 0xFF, chunk >> 8,
                      (~chunk) & 0xFF, ((~chunk) >> 8) & 0xFF))
        out += data[pos:pos + chunk]
        pos += chunk
        if final:
            break
    a = _adler32(data)
    out += bytes((a >> 24 & 0xFF, a >> 16 & 0xFF, a >> 8 & 0xFF, a & 0xFF))
    return bytes(out)


def _be32(v):
    return bytes((v >> 24 & 0xFF, v >> 16 & 0xFF, v >> 8 & 0xFF, v & 0xFF))


def _chunk(tag, body):
    return _be32(len(body)) + tag + body + _be32(_crc32(tag + body))


def save(path, rows, width, height):
    """`rows` yields one bytes-like of palette indices per row, top first."""
    ihdr = _be32(width) + _be32(height) + bytes((2, 3, 0, 0, 0))
    plte = b"".join(bytes((s, s, s)) for s in SHADES)
    raw = bytearray()
    for row in rows:
        raw.append(0)                        # filter 0: none
        packed = 0
        bits = 0
        for x in range(width):
            packed = (packed << 2) | (row[x] & 3)
            bits += 2
            if bits == 8:
                raw.append(packed)
                packed = bits = 0
        if bits:
            raw.append(packed << (8 - bits))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"PLTE", plte))
        f.write(_chunk(b"IDAT", _stored(bytes(raw))))
        f.write(_chunk(b"IEND", b""))
    return path


def save_screen(path, raw, stride, x0, width, height):
    """Straight out of the framebuffer. `raw` is RGBA, so the red byte of each
    pixel carries the grey level."""
    def rows():
        line = bytearray(width)
        for y in range(height):
            base = y * stride + x0 * 4
            for x in range(width):
                line[x] = INDEX[raw[base + x * 4]]
            yield line
    return save(path, rows(), width, height)
