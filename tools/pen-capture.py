#!/usr/bin/env python3
"""Guided capture of everything the pen sends, to find out which event is the barrel button, the top (rubber/eraser) button, the eraser end and the tip.
Run as root (it reads /dev/input/event*):   sudo python3 pen-capture.py
It tells you what to do in four steps of 12 seconds; each step prints the events that arrived, per input device. Paste the output back."""
import glob
import os
import select
import struct
import subprocess
import sys
import time

NAMES = {
    (1, 0x14a): "BTN_TOUCH", (1, 0x140): "BTN_TOOL_PEN", (1, 0x141): "BTN_TOOL_RUBBER", (1, 0x14b): "BTN_STYLUS", (1, 0x14c): "BTN_STYLUS2",
    (1, 0x14d): "BTN_STYLUS3", (1, 0x110): "BTN_LEFT", (1, 0x111): "BTN_RIGHT", (1, 0x112): "BTN_MIDDLE", (3, 0): "ABS_X", (3, 1): "ABS_Y",
    (3, 0x18): "ABS_PRESSURE", (3, 0x1a): "ABS_TILT_X", (3, 0x1b): "ABS_TILT_Y", (3, 0x28): "ABS_MISC", (4, 4): "MSC_SCAN",
}
PHASES = [("BARREL: spam the button on the body of the pen (press and release quickly many times) with the pen hovering 1-2 cm above the screen", 15, False),
          ("TIP: touch the screen with the tip and draw a short line, pressing harder and tilting the pen", 12, False),
          ("ERASER, light touch: turn the pen around and touch the screen with the flat end 3 times, lifting each time (a tiny soft click)", 14, False),
          ("SHORTCUT BUTTON, in the air: pen away from the screen, press the flat end hard with your thumb like a detonator 4 times", 14, True),
          ("SHORTCUT BUTTON, near the screen: hover the flat end 1 cm above the screen and press it hard 4 times", 14, True)]


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _notify import notify as _n  # noqa: E402


def notify(text):
    _n("Surface pen test", text)


def main():
    phases = PHASES
    if len(sys.argv) > 1:
        phases = {"barrel": PHASES[:1], "tip": PHASES[1:2], "eraser": PHASES[2:3], "detonator": PHASES[3:]}[sys.argv[1]]
    devs = {}
    for p in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        name = open("/sys/class/input/%s/device/name" % os.path.basename(p)).read().strip()
        devs[fd] = (p, name)
    print("listening on:")
    for p, n in devs.values():
        print("  %s  %s" % (p, n))
    print()
    for i, (text, secs, bt) in enumerate(phases, 1):
        print("=== Step %d: %s" % (i, text), flush=True)
        notify("Step %d: %s" % (i, text))
        time.sleep(4)
        print("   (go! %d seconds)" % secs, flush=True)
        seen = {}
        log = []
        t0 = time.time()
        btm = None
        if bt:
            btm = subprocess.Popen(["btmon"], stdout=open("/tmp/btmon-step%d.txt" % i, "w"), stderr=subprocess.DEVNULL)
        t_end = time.time() + secs
        while time.time() < t_end:
            r, _, _ = select.select(list(devs), [], [], 0.2)
            for fd in r:
                try:
                    data = os.read(fd, 24 * 64)
                except OSError:
                    continue
                for k in range(0, len(data) - 23, 24):
                    _, _, typ, code, val = struct.unpack("llHHi", data[k:k + 24])
                    if typ == 0 or (typ == 3 and code in (0, 1, 0x18, 0x1a, 0x1b) and False):
                        continue
                    key = (devs[fd][1], NAMES.get((typ, code), "type %d code %#x" % (typ, code)))
                    seen.setdefault(key, set()).add(val)
                    if typ in (1, 4) or (typ == 3 and code == 0x28):
                        log.append("%5.2fs %s %s=%d" % (time.time() - t0, devs[fd][1][-12:], key[1], val))
        if not seen:
            print("   nothing arrived on any input device during this step")
            os.system("cat /proc/bus/input/devices | grep -A3 -i 'stylus\\|pen' | head -12")
        for (dev, ev), vals in sorted(seen.items()):
            shown = sorted(vals)
            print("   %-38s %-18s values %s%s" % (dev[:38], ev, shown[:8], " ..." if len(shown) > 8 else ""))
        if btm:
            btm.terminate()
            btm.wait()
            lines = open("/tmp/btmon-step%d.txt" % i).read().splitlines()
            print("   bluetooth: %d lines captured; ACL/HID lines:" % len(lines))
            for l in [l for l in lines if "ACL" in l or "ATT" in l or "HID" in l or "Handle Value" in l][:30]:
                print("     " + l.strip())
        if log:
            print("   in order (buttons, tool, scan codes):")
            last = None
            for l in log:
                if l.split(" ", 1)[1] != last:
                    print("     " + l)
                last = l.split(" ", 1)[1]
            print()
        print()
    notify("Done. Paste the terminal output back to Claude.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("run it as root: sudo python3 %s" % sys.argv[0])
    main()
