# Viper-optimized inner loop for framebuffer rotation.
import micropython


@micropython.viper
def rotate_180(buf: ptr8, stride: int, w: int, h: int, x0: int):
    s = int(stride)
    w_int = int(w)
    h_int = int(h)
    half_h = h_int >> 1
    x0_bytes = int(x0) * 4
    
    for y in range(half_h):
        y_opp = h_int - 1 - y
        r1 = y * s + x0_bytes
        r2 = y_opp * s + x0_bytes
        
        for x in range(w_int):
            x_opp = w_int - 1 - x
            p1 = r1 + (x << 2)
            p2 = r2 + (x_opp << 2)
            
            t0 = buf[p1]
            t1 = buf[p1+1]
            t2 = buf[p1+2]
            t3 = buf[p1+3]
            
            buf[p1] = buf[p2]
            buf[p1+1] = buf[p2+1]
            buf[p1+2] = buf[p2+2]
            buf[p1+3] = buf[p2+3]
            
            buf[p2] = t0
            buf[p2+1] = t1
            buf[p2+2] = t2
            buf[p2+3] = t3
            
    if h_int & 1:
        y = half_h
        r1 = y * s + x0_bytes
        half_w = w_int >> 1
        for x in range(half_w):
            x_opp = w_int - 1 - x
            p1 = r1 + (x << 2)
            p2 = r1 + (x_opp << 2)
            
            t0 = buf[p1]
            t1 = buf[p1+1]
            t2 = buf[p1+2]
            t3 = buf[p1+3]
            
            buf[p1] = buf[p2]
            buf[p1+1] = buf[p2+1]
            buf[p1+2] = buf[p2+2]
            buf[p1+3] = buf[p2+3]
            
            buf[p2] = t0
            buf[p2+1] = t1
            buf[p2+2] = t2
            buf[p2+3] = t3
