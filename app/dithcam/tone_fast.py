# Viper-optimized inner loop for tone mapping. 
# 
# Isolated in a separate module to allow graceful fallback to standard Python
# implementations on firmware builds lacking native Viper compiler support.
import micropython


@micropython.viper
def row(buf: ptr8, start: int, count: int, lut: ptr8):
    i = int(start)
    end = i + int(count) * 4
    while i < end:
        buf[i] = lut[buf[i]]
        buf[i + 1] = lut[buf[i + 1]]
        buf[i + 2] = lut[buf[i + 2]]
        i += 4
