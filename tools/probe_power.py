# How does this firmware handle sleep, wake and power?
#
# On battery the badge powers down inside wait_for_button_or_alarm, so a button
# press restarts main.py from scratch and the app always comes up in LIVE mode.
# The button that woke it is lost, which is why the gallery is unreachable on
# battery. Something must record the wake source - find it.
#
# Read-only: introspects and prints, touches no state.
import sys

print("=== powman ===")
try:
    import powman
    for n in sorted(n for n in dir(powman) if not n.startswith("_")):
        try:
            v = getattr(powman, n)
            print("  %-24s %s" % (n, v if not callable(v) else "<callable>"))
        except Exception as e:
            print("  %-24s <error %s>" % (n, e))
except ImportError as e:
    print("  no powman:", e)

print()
print("=== badgeware module ===")
import badgeware
for n in sorted(n for n in dir(badgeware) if not n.startswith("_")):
    print("  %-24s %s" % (n, "<callable>" if callable(getattr(badgeware, n, None)) else ""))

print()
print("=== the badge object (as an app sees it) ===")
try:
    from badgeware import display
    print("  display:", [n for n in dir(display) if not n.startswith("_")])
except Exception as e:
    print("  display:", e)

print()
print("=== machine: reset cause and wake ===")
import machine
print("  machine:", [n for n in dir(machine) if not n.startswith("_")])
for n in ("reset_cause", "wake_reason", "PWRON_RESET", "DEEPSLEEP_RESET",
          "DEEPSLEEP", "SLEEP", "PIN_WAKE", "RTC_WAKE"):
    if hasattr(machine, n):
        v = getattr(machine, n)
        try:
            print("  machine.%-16s %s" % (n, v() if callable(v) else v))
        except Exception as e:
            print("  machine.%-16s <%s>" % (n, e))

print()
print("=== rtc ===")
try:
    import rtc
    print("  rtc:", [n for n in dir(rtc) if not n.startswith("_")])
except ImportError:
    print("  no top-level rtc module")
