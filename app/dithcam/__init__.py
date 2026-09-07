# DITHRPIX - A four-shade camera for the Badger 2350.
#
# Uses a single capture resolution (320x240) to avoid the ~5s reset stall required
# when switching sizes. This resolution is downsampled into the 234x176 view,
# providing higher detail at the cost of a slightly lower framerate (~1343ms per frame).
import sys
import os
import time
import gc
import json

sys.path.insert(0, "/system/apps/dithcam")
os.chdir("/system/apps/dithcam")

from badgeware import clear_running
clear_running()

from machine import UART, Pin
import powman
import vc0706
from vc0706 import VC0706, CameraError
import tone
import rotate
import dither
import png

CAPTURE_SIZE = vc0706.SIZE_320x240   # downsampled into the view, not stretched
DEFAULT_BAUD = 38400            # the camera always powers up here
FAST_BAUD = 115200
THUMB_CACHE = 4                 # thumbnails are loaded on demand, not up front
MAX_FILES = 60                  # Maximum files before reusing oldest slot
IDLE_MS = 30000                 # Idle timeout before sleep
BOOT_BUDGET_MS = 8000           # Camera initialization timeout
PROBE_MS = 300                  # Polling interval for readiness checks
PREVIEW_MS = 1500               # Minimum interval between live view refreshes
DITHER_MODES = dither.MODES     # Available dithering algorithms
TIDY_VERSION = 2                # Storage cleanup version indicator

# Tone mapping maps specific segments of the auto-exposed input range to the
# display's four shades. Letters correspond to visual brightness (L = Low brightness).
TONES = (("A", 0, 255), ("L", 128, 255), ("M", 64, 192), ("H", 0, 128))

W, H = screen.width, screen.height

# ---- Rail UI Layout ------------------------------------------------------
# Configures the vertical stack. Adjusting a gap or height propagates down.
GAP = 4                         # between groups
TIGHT = 2                       # between paired lines (name, counter)

H_BATTERY = 8
H_NAME = 6                      # ark is 6px
H_TEXT = 14                     # sins at 2x
H_COUNT = 7                     # the counter stays at native size
H_TONE = 16                     # kept empty; holds the stack spacing open
H_THUMB = 8

# (key, height, gap above it)
STACK = (
    ("battery", H_BATTERY, GAP),
    ("name1",   H_NAME,    GAP),
    ("name2",   H_NAME,    TIGHT),
    ("count",   H_COUNT,   GAP),
    ("max",     H_COUNT,   TIGHT),
    ("tone",    H_TONE,    GAP),
    ("a",       H_TEXT,    GAP),
    ("b",       H_TEXT,    GAP),
    ("c",       H_TEXT,    GAP),
    ("up",      H_THUMB,   GAP),
    ("down",    H_THUMB,   GAP),
)

Y = {}
_cursor = 0
for _key, _h, _gap in STACK:
    _cursor += _gap
    Y[_key] = _cursor
    _cursor += _h

# Positions the browsing buttons flush with the bottom of the display.
Y["down"] = H - H_THUMB
Y["up"] = Y["down"] - GAP - H_THUMB

VIEW_W = int(H * 4 / 3)         # 234 - the full 4:3 frame, uncropped
RAIL_W = W - VIEW_W             # 30
RAIL_X = VIEW_W

# --------------------------------------------------------------- metrics ---
NAME_FONT = font.ark            # 6px, the branding and the refresh mark
TEXT_FONT = font.sins           # 7px, the button legends
NAME_SIZE = 1                   # ark at native size
TEXT_SIZE = 2                   # sins doubled
COUNT_SIZE = 1                  # the counter stays native


def cap_ink(fnt, size, sample="B"):
    """Calculates the physical rendering bounds of a capital letter.

    Measures the exact rendered height to align UI elements correctly, as
    standard layout boxes include excessive padding. Renders a scratch sample
    to the framebuffer and measures it before the first screen update.
    """
    previous = screen.font
    screen.font = fnt
    width, height = (int(v) for v in screen.measure_text(sample, size))
    screen.pen = color.white
    screen.rectangle(0, 0, width, height)
    screen.pen = color.black
    screen.text(sample, 0, 0, size)
    screen.font = previous
    raw, stride = screen.raw, screen.stride
    rows = [y for y in range(height)
            if any(raw[y * stride + x * 4] < 128 for x in range(width))]
    if not rows:                                  # a blank sample: no offset
        return width, height, 0, height
    return width, height, rows[0], rows[-1] - rows[0] + 1


class Metrics:
    """Caches font measurement data for precise UI alignment."""

    def __init__(self, fnt, size):
        self.font = fnt
        self.size = size
        self.width, self.box_height, top, self.height = cap_ink(fnt, size)
        # Offset required to convert center alignment to true ink-center alignment.
        self.offset = top + self.height / 2 - self.box_height / 2


TEXT = Metrics(TEXT_FONT, TEXT_SIZE)      # A B C and the tone letters
COUNT = Metrics(TEXT_FONT, COUNT_SIZE)    # the two counter rows
NAME = Metrics(NAME_FONT, NAME_SIZE)      # DITH / RPIX, and R for refresh

SPLASH_ROWS = 8                 # DITHRPIX, one letter per band
SPLASH_PAD = 4                  # breathing room inside each band
SPLASH_BAND = H // SPLASH_ROWS


def fit_splash():
    """Calculates the maximum font size for the splash screen that maintains margins."""
    best = NAME
    for size in range(NAME_SIZE + 1, 12):
        m = Metrics(NAME_FONT, size)
        if m.height > SPLASH_BAND - SPLASH_PAD or m.width > RAIL_W - SPLASH_PAD:
            break
        best = m
    return best


SPLASH = fit_splash()

INVERT_PAD = 2                  # breathing room around the ink, not the box
STROKE = 3                      # chevron weight
CHEVRON_TRIM = 4                # narrower than the slot, so it reads as a mark
SHUTTER_D = TEXT.width - 2      # a dot as wide as the letter beside it
BIN_H = 10                      # matches the C it labels
BIN_W = BIN_H - 4               # taller than it is wide, so it is not a battery
BATTERY_W = 14                  # body only; the nub adds one more
DISABLED = color.rgb(170, 170, 170)   # one of the four shades, so it stays flat
PENDING = color.rgb(85, 85, 85)       # not taken yet: three-quarters dark

# Configures the dual-column button layout on the UI rail.
THUMB_W_WANTED = 11
PAIR_GAP = 4
LEFT_NUDGE = 2                  # optical centring: the marks are lighter
COUNT_NUDGE = -1

SLOT_R_W = TEXT.width
SLOT_L_W = max(THUMB_W_WANTED, TEXT.width)
PAIR_X = RAIL_X + (RAIL_W - (SLOT_L_W + PAIR_GAP + SLOT_R_W)) // 2
SLOT_L_X = PAIR_X + LEFT_NUDGE
SLOT_R_X = PAIR_X + SLOT_L_W + PAIR_GAP
NAME_MARGIN = 3                 # 3px either side of the four letters
NAME_CELL = (RAIL_W - NAME_MARGIN * 2) // 4
NAME_ROWS = ("DITH", "RPIX")

THUMB_W, THUMB_H = THUMB_W_WANTED, H_THUMB
CHEVRON_H = 6


state = {"tone": 0, "dither": 0, "mode": "LIVE", "gal": 0}
State.load("dithcam", state)

# Maps physical buttons to their powman wake reasons. Allows capturing
# button events that wake the device from deep sleep.
WAKE_BUTTON = {
    powman.WAKE_BUTTON_A: BUTTON_A,
    powman.WAKE_BUTTON_B: BUTTON_B,
    powman.WAKE_BUTTON_C: BUTTON_C,
    powman.WAKE_BUTTON_UP: BUTTON_UP,
    powman.WAKE_BUTTON_DOWN: BUTTON_DOWN,
}
_reason = powman.get_wake_reason()
wake = WAKE_BUTTON.get(_reason)

# Splash screen is only shown on cold boot, not on wake from deep sleep.
cold_boot = _reason not in WAKE_BUTTON and _reason != powman.WAKE_ALARM


cam = None
last_draw = 0
ready = False                   # the app has yet to draw a real screen
confirming = False              # delete prompt is up
index = []                      # photo numbers, newest first
thumbs = {}                     # seq -> thumbnail, filled on demand
mode = "LIVE"
gal_i = 0


# ---------------------------------------------------------------- camera ---
def open_uart(baud):
    return UART(1, baudrate=baud, tx=Pin(4), rx=Pin(5), timeout=1000, rxbuf=2048)


def wait_ready(c):
    """Polls the camera for readiness during initialization.

    Accommodates variable boot times (particularly on battery power) to ensure
    commands are only sent when the DSP is ready.
    """
    deadline = time.ticks_add(time.ticks_ms(), BOOT_BUDGET_MS)
    while True:
        try:
            return c.version(PROBE_MS)
        except CameraError:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                raise
            time.sleep_ms(200)


def find_camera():
    """Detects and connects to the camera by polling available baud rates.

    Handles differences in camera state between cold starts (38400 baud) 
    and soft resets (115200 baud).
    """
    for baud in (FAST_BAUD, DEFAULT_BAUD):
        c = VC0706(open_uart(baud))
        try:
            c.version(PROBE_MS)
            return c
        except CameraError:
            pass
    c = VC0706(open_uart(DEFAULT_BAUD))
    wait_ready(c)                          # still powering up
    return c


def start_camera():
    global cam
    c = find_camera()
    c.color_mode(2)                        # DSP does the greyscale
    c.set_image_size(CAPTURE_SIZE)
    c.reset()
    c = VC0706(open_uart(DEFAULT_BAUD))    # a reset drops it back to 38400
    wait_ready(c)
    # Upgrade baud rate for improved framerate.
    c.set_baud(FAST_BAUD)
    c = VC0706(open_uart(FAST_BAUD))
    wait_ready(c)
    cam = c


def ensure_camera():
    """Initializes the camera hardware on demand to avoid unnecessary power draw."""
    if cam is None:
        start_camera()


def grab():
    ensure_camera()
    cam.take_picture()
    jpeg = cam.read_frame(cam.frame_length(), 256)
    cam.resume()
    return image.load(jpeg)


# ------------------------------------------------------------------ view ---
def draw_view(img, direct=False):
    """Renders the image into the 234x176 view with tone mapping and dithering."""
    screen.pen = color.white
    screen.rectangle(0, 0, VIEW_W, H)
    if img is None:
        return
    screen.blit(img, rect(0, 0, img.width, img.height), rect(0, 0, VIEW_W, H))
    if direct:
        return          # a stored photo is already toned and dithered
    rotate.apply(screen.raw, screen.stride, 0, VIEW_W, H)
    _, lo, hi = TONES[state["tone"]]
    tone.apply(screen.raw, screen.stride, 0, VIEW_W, H, lo, hi)
    dither.apply(screen.raw, screen.stride, 0, 0, VIEW_W, H,
                 DITHER_MODES[state["dither"]])


# --------------------------------------------------------------- photos ----
def next_seq():
    """Returns the next available file sequence number."""
    for n in range(1, MAX_FILES + 1):
        if n not in index:
            return n
    return index[-1]              # full: the oldest slot gets reused


def photo_path(seq):
    return "/photos/dith%03d.png" % seq


def thumb_for(seq):
    """Lazily loads and returns a thumbnail for the given sequence number."""
    if seq is None:
        return None
    got = thumbs.get(seq)
    if got is None:
        got = thumbnail_of(image.load(photo_path(seq)))
        if len(thumbs) >= THUMB_CACHE:
            thumbs.clear()
        thumbs[seq] = got
    return got


# ------------------------------------------------------------------ rail ---
MIDDLE = (image.CENTER, image.MIDDLE)


def cell(x, y, w, h):
    """A box to place something in. Everything in the rail is positioned by
    box rather than by coordinate, which is what keeps the columns aligned."""
    return rect(int(x), int(y), int(w), int(h))


def left_cell(y, h=None):
    return cell(SLOT_L_X, y, SLOT_L_W, h or H_TEXT)


def right_cell(y, h=None):
    return cell(SLOT_R_X, y, SLOT_R_W, h or H_TEXT)


def label(text, box, m, invert=False, pen=None, left=False):
    """Renders text aligned to its calculated ink center."""
    previous = screen.font
    screen.font = m.font
    if invert:
        height = m.height + INVERT_PAD * 2
        screen.pen = color.black
        screen.rectangle(box.x, int(box.y + (box.h - height) / 2),
                         box.w, height)
        screen.pen = color.white
    else:
        screen.pen = pen or color.black
    if left:
        # Placed by coordinate so the digits start on a known edge, with the
        # ink still centred in the row.
        screen.text(text, box.x,
                    int(box.y + (box.h - m.box_height) / 2 - m.offset), m.size)
    else:
        screen.text(text, cell(box.x, box.y - m.offset, box.w, box.h), m.size,
                    align=MIDDLE)
    screen.pen = color.black
    screen.font = previous


def battery(y):
    """Renders the battery indicator showing current charge level."""
    level = badge.battery_level()
    width, height = BATTERY_W, H_BATTERY
    x = RAIL_X + (RAIL_W - (width + 1)) // 2
    screen.pen = color.black
    screen.shape(shape.rectangle(x, y, width, height))
    screen.shape(shape.rectangle(x + width, y + 2, 1, 4))
    screen.pen = color.white
    screen.shape(shape.rectangle(x + 1, y + 1, width - 2, height - 2))
    screen.pen = color.black
    screen.shape(shape.rectangle(x + 2, y + 2,
                                 ((width - 4) / 100) * level, height - 4))


def name():
    """Four letters across the rail, each centred in its own cell."""
    for word, y in ((NAME_ROWS[0], Y["name1"]), (NAME_ROWS[1], Y["name2"])):
        for i, ch in enumerate(word):
            label(ch, cell(RAIL_X + NAME_MARGIN + i * NAME_CELL, y,
                           NAME_CELL, H_NAME), NAME)


def counter():
    """Renders the photo counter and maximum limit indicator."""
    x = RAIL_X + NAME_MARGIN + COUNT_NUDGE
    width = RAIL_W - NAME_MARGIN * 2
    pending = mode == "LIVE"
    label(str(next_seq() if pending else index[gal_i]),
          cell(x, Y["count"], width, H_COUNT), COUNT, left=True,
          pen=PENDING if pending else None)
    label(str(MAX_FILES), cell(x, Y["max"], width, H_COUNT), COUNT, left=True)


def shutter(y):
    box = left_cell(y)
    screen.pen = color.black
    screen.circle(box.x + box.w // 2, box.y + box.h // 2, SHUTTER_D // 2)


def bin_icon(y):
    """Marks C as the delete key while browsing."""
    box = left_cell(y)
    x = box.x + (box.w - BIN_W) // 2
    top = box.y + (box.h - BIN_H) // 2
    screen.pen = color.black
    screen.rectangle(x + BIN_W // 2 - 1, top, 3, 2)      # handle
    screen.rectangle(x, top + 2, BIN_W, 1)               # lid
    screen.rectangle(x + 1, top + 4, BIN_W - 2, BIN_H - 4)


def swatch(y):
    """Renders a live swatch of the current dithering algorithm."""
    box = left_cell(y)
    for i in range(box.h):
        level = 255 * i // (box.h - 1)
        screen.pen = color.rgb(level, level, level)
        screen.rectangle(box.x, box.y + i, box.w, 1)
    dither.apply(screen.raw, screen.stride, box.x, box.y, box.w, box.h,
                 DITHER_MODES[state["dither"]])
    screen.pen = color.black


def refresh_icon(y):
    """DOWN re-takes the preview while framing."""
    label("R", left_cell(y, H_THUMB), NAME)


def chevron(y, up, on=True):
    """shape.line carries a thickness, unlike screen.line."""
    box = right_cell(y, H_THUMB)
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    arm = (box.w - CHEVRON_TRIM) / 2
    dy = -CHEVRON_H / 2 if up else CHEVRON_H / 2
    screen.pen = color.black if on else DISABLED
    screen.shape(shape.line(cx - arm, cy - dy, cx, cy + dy, STROKE))
    screen.shape(shape.line(cx, cy + dy, cx + arm, cy - dy, STROKE))
    screen.pen = color.black


def thumb(src, y):
    if src is None:
        return
    box = left_cell(y, H_THUMB)
    screen.blit(src, rect(0, 0, src.width, src.height),
                rect(box.x, box.y, THUMB_W, THUMB_H))


def draw_rail():
    screen.pen = color.white
    screen.rectangle(RAIL_X, 0, RAIL_W, H)

    battery(Y["battery"])
    name()
    counter()

    total = len(index)
    tone_i = state["tone"]
    live = mode == "LIVE"

    # Y["tone"] is left empty to preserve layout height.
    if live:
        label(TONES[tone_i][0], left_cell(Y["a"]), TEXT, invert=True)
        swatch(Y["c"])                     # C cycles the dither
        label("A", right_cell(Y["a"]), TEXT)
    else:
        bin_icon(Y["c"])                   # C deletes while browsing
    label("B", right_cell(Y["b"]), TEXT)
    label("C", right_cell(Y["c"]), TEXT)
    shutter(Y["b"])

    # Gallery navigation logic.
    older = (index[0] if total else None) if live else (
        index[gal_i + 1] if gal_i + 1 < total else None)
    thumb(thumb_for(older), Y["up"])
    chevron(Y["up"], True, on=older is not None)
    if live:
        refresh_icon(Y["down"])            # DOWN re-takes the preview
    elif gal_i > 0:
        thumb(thumb_for(index[gal_i - 1]), Y["down"])
    chevron(Y["down"], False)



def confirm_box():
    """Renders a deletion confirmation prompt."""
    prompt = "delete? C=yes"
    previous = screen.font
    screen.font = NAME.font
    width, height = (int(v) for v in screen.measure_text(prompt, NAME.size))
    screen.font = previous
    box = cell((VIEW_W - width) / 2 - 6, (H - height) / 2 - 5,
               width + 12, height + 10)
    screen.pen = color.white
    screen.rectangle(box.x, box.y, box.w, box.h)
    screen.pen = color.black
    screen.shape(shape.rectangle(box.x, box.y, box.w, box.h).stroke(1))
    label(prompt, box, NAME)


def compose(img, direct=False):
    """Draw everything without touching the panel."""
    draw_view(img, direct)
    draw_rail()


def overlay(note):
    """Renders an error overlay at the bottom of the view."""
    previous = screen.font
    screen.font = NAME.font
    width, height = (int(v) for v in screen.measure_text(note, NAME.size))
    screen.font = previous
    box = cell(0, H - height - 2, width + 6, height + 2)
    screen.pen = color.white
    screen.rectangle(box.x, box.y, box.w, box.h)
    label(note, box, NAME)


def paint():
    global last_draw
    badge.mode(FAST_UPDATE)
    badge.update()
    last_draw = time.ticks_ms()


def show(img, note=None, direct=False):
    compose(img, direct)
    if note:
        overlay(note)
    paint()


def thumbnail_of(img):
    th = image(THUMB_W, THUMB_H)
    th.blit(img, rect(0, 0, img.width, img.height),
            rect(0, 0, THUMB_W, THUMB_H))
    dither.apply(th.raw, th.stride, 0, 0, THUMB_W, THUMB_H,
                 DITHER_MODES[state["dither"]])
    return th


def read_index():
    """Reads the chronological photo index from disk."""
    try:
        with open("/photos/index.json") as f:
            return [int(seq) for seq in json.load(f)]
    except OSError:
        return []                # no photos taken yet


def discard(path):
    """Safely removes a file if it exists."""
    try:
        os.remove(path)
    except OSError:
        pass


def cleanup():
    """Performs one-time storage cleanup based on TIDY_VERSION.
    
    Removes deprecated caches, backups, and legacy image formats to reclaim space.
    """
    if state.get("tidied") == TIDY_VERSION:
        return
    for name in (".fsbackup", ".fsbackup.crc32", "mesh_cache.png",
                 "mesh_cache_A.png", "mesh_cache_B.png", "mesh_cache_C.png"):
        discard("/" + name)
    # One PNG now replaces the BMP-and-JPEG pair the previous build wrote.
    try:
        for name in os.listdir("/photos"):
            if name.endswith(".bmp") or name.endswith(".jpg"):
                discard("/photos/" + name)
    except OSError:
        pass                     # no photos taken yet
    state["tidied"] = TIDY_VERSION
    state.pop("seq", None)       # superseded by next_seq() reading the index
    State.save("dithcam", state)


def save_photo():
    """Exports the framebuffer as a 2-bit indexed PNG."""
    try:
        os.mkdir("/photos")
    except OSError:
        pass
    seq = next_seq()
    png.save_screen(photo_path(seq), screen.raw, screen.stride, 0, VIEW_W, H)
    # Rebuild rather than insert-then-dedupe: list.remove() takes the *first*
    # match, which was the newly added entry.
    index[:] = [seq] + [n for n in index if n != seq]
    del index[MAX_FILES:]
    write_index()
    return seq


def write_index():
    with open("/photos/index.json", "w") as f:
        json.dump(index, f)


def delete_current():
    """Drop the photo under the cursor, on disk and in the index."""
    global gal_i
    seq = index.pop(gal_i)
    discard(photo_path(seq))
    thumbs.pop(seq, None)
    write_index()
    if gal_i >= len(index):
        gal_i = max(0, len(index) - 1)


def load_photos():
    """Initializes the gallery index and syncs it with the filesystem."""
    stored = read_index()[:MAX_FILES]
    index.extend(seq for seq in stored if file_exists(photo_path(seq)))
    if len(index) != len(stored):
        write_index()
    # Anything in /photos the index doesn't claim is a leftover from a failed
    # save; it only wastes space on a 1MB volume.
    keep = set(photo_path(seq).rsplit("/", 1)[-1] for seq in index)
    try:
        for name in os.listdir("/photos"):
            if name.endswith(".png") and name not in keep:
                discard("/photos/" + name)
    except OSError:
        pass


def splash():
    """Renders the startup splash screen."""
    screen.pen = color.white
    screen.rectangle(0, 0, W, H)
    for i, ch in enumerate(NAME_ROWS[0] + NAME_ROWS[1]):
        label(ch, cell(RAIL_X, i * SPLASH_BAND, RAIL_W, SPLASH_BAND), SPLASH)
    paint()


def live():
    try:
        show(grab())
        gc.collect()
    except CameraError as e:
        show(None, note=str(e)[:40])


def show_stored(i):
    try:
        show(image.load(photo_path(index[i])), direct=True)
    except Exception as e:
        show(None, note="can't open photo: %s" % type(e).__name__)


def capture():
    """Captures a photo, saves it, and updates the display."""
    try:
        img = grab()
    except CameraError as e:
        show(None, note=str(e)[:40])
        return
    compose(img)
    seq = save_photo()
    thumbs[seq] = thumbnail_of(img)
    draw_rail()                    # pick up the new thumbnail and count
    paint()


def show_current():
    """Renders the current UI state."""
    if mode == "GALLERY":
        show_stored(gal_i)
    else:
        live()


def remember():
    """Persists the current UI state to flash storage."""
    if state["mode"] == mode and state["gal"] == gal_i:
        return
    state["mode"] = mode
    state["gal"] = gal_i
    State.save("dithcam", state)


def update():
    """Main event loop responsible for handling input and state transitions."""
    global mode, gal_i, confirming, wake, ready

    a = badge.pressed(BUTTON_A)
    b = badge.pressed(BUTTON_B)
    c = badge.pressed(BUTTON_C)
    up = badge.pressed(BUTTON_UP)
    down = badge.pressed(BUTTON_DOWN)
    if wake is not None:
        # Replay the press that woke the badge, once, as though it had been
        # made while running.
        a = a or wake == BUTTON_A
        b = b or wake == BUTTON_B
        c = c or wake == BUTTON_C
        up = up or wake == BUTTON_UP
        down = down or wake == BUTTON_DOWN
        wake = None

    if confirming:
        if a or b or c or up or down:
            confirming = False
            if c:
                delete_current()
            if index:
                show_stored(gal_i)
            else:
                mode = "LIVE"
                live()
    elif mode == "GALLERY":
        if c and index:
            confirming = True
            compose(image.load(photo_path(index[gal_i])), direct=True)
            confirm_box()
            paint()
        elif up and gal_i + 1 < len(index):
            gal_i += 1
            show_stored(gal_i)
        elif down and gal_i > 0:
            gal_i -= 1
            show_stored(gal_i)
        elif down or b:
            mode = "LIVE"
            live()
    else:
        if a:
            state["tone"] = (state["tone"] + 1) % len(TONES)
            State.save("dithcam", state)
            live()
        elif c:
            state["dither"] = (state["dither"] + 1) % len(DITHER_MODES)
            State.save("dithcam", state)
            live()
        elif up and index:
            gal_i = 0
            mode = "GALLERY"
            show_stored(gal_i)
        elif b:
            capture()
        elif down:
            live()                         # DOWN refreshes the view

    if not ready:
        # Initial UI render post-wake. Prevents unnecessary camera initialization
        # if the device wakes directly into gallery mode.
        ready = True
        if not (a or b or c or up or down):
            show_current()

    # Performs necessary state persistence and hardware shutdown procedures
    # before transitioning to deep sleep. The RP2350 RTC does not tick
    # while sleeping on this device, meaning execution is entirely event-driven.
    gc.collect()
    remember()
    wait_for_button_or_alarm(timeout=IDLE_MS)


# ------------------------------------------------------------------ main ---
cleanup()
load_photos()

# Restores previous UI state. Invalid gallery indices fallback to live view.
# Deletion confirmation state is intentionally discarded across reboots.
gal_i = state["gal"]
if state["mode"] == "GALLERY" and gal_i < len(index):
    mode = "GALLERY"
else:
    mode = "LIVE"
    gal_i = 0

if cold_boot:
    splash()                    # the only thing drawn before the first update

run(update)
