import powman

CAMERA = "/system/apps/dithcam"
FALLBACK = "/system/apps/menu"

# Boot straight into the camera rather than the launcher.
app = CAMERA if file_exists(CAMERA) else FALLBACK

launch(app)

rtc.clear_alarm()
reset()
