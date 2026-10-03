#!/usr/bin/env python3
"""Looks for the keyboard backlight of the Type Cover. On the Surface Go cover the backlight is the second function of F1; the Fn key has a light like Caps
Lock: with the light ON the top row types F1..F12, with the light OFF the keys do their special job (F1 = keyboard brightness).
Three steps of 15 seconds, announced by notifications: F1 with the Fn light off, F1 with the Fn light on, the Fn key itself. It prints everything the cover
sends (input events of its devices and raw reports of its HID interfaces) and reads the vendor feature report 4 at the end of each step.
It never writes anything to the cover. Run as root:   sudo python3 folio-backlight-probe.py"""
import fcntl
import glob
import os
import select
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _notify import notify  # noqa: E402

KEYS = {59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6", 65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12", 0x179: "KBDILLUMTOGGLE",
        0x17a: "KBDILLUMDOWN", 0x17b: "KBDILLUMUP", 0x8a: "BRIGHTNESS?", 0xe0: "BRIGHTNESSDOWN", 0xe1: "BRIGHTNESSUP", 0x1e0: "ILLUM?", 0x1d0: "FN"}
STEPS = [("FN LIGHT OFF: make sure the light on the Fn key is OFF, then press F1 slowly 4 times (the keyboard brightness should change)", 15),
         ("FN LIGHT ON: press the Fn key once so that its light turns ON, then press F1 slowly 4 times (it should type F1 now)", 15),
         ("FN KEY: press the Fn key itself 4 times, slowly (the light toggles)", 15)]


def feature4(fd):
    """Reads the vendor feature report 4 with a time limit (a blocking read must not hang the test)."""
    out = []

    def go():
        buf = bytearray(64)
        buf[0] = 4
        try:
            n = fcntl.ioctl(fd, (3 << 30) | (64 << 16) | (ord("H") << 8) | 0x07, buf, True)
            out.append(bytes(buf[:12]).hex())
        except OSError as e:
            out.append("error %s" % e.strerror)
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(2.0)
    return out[0] if out else "no answer in 2 s"


def main():
    evs, raws, feat = {}, {}, None
    for p in sorted(glob.glob("/dev/input/event*")):
        name = open("/sys/class/input/%s/device/name" % os.path.basename(p)).read().strip()
        if "Surface Keyboard" in name:
            evs[os.open(p, os.O_RDONLY | os.O_NONBLOCK)] = name.replace("Microsoft Surface Keyboard", "cover") + " (" + os.path.basename(p) + ")"
    for d in sorted(glob.glob("/sys/bus/hid/devices/0003:045E:09B5.*")):
        for h in glob.glob(d + "/hidraw/hidraw*"):
            try:
                fd = os.open("/dev/" + os.path.basename(h), os.O_RDWR | os.O_NONBLOCK)
            except OSError:
                continue
            raws[fd] = "hid " + os.path.basename(d)[-4:]
            try:
                if b"\x06\x01\xff" in open(d + "/report_descriptor", "rb").read():       # usage page 0xff01: the vendor reports of the cover
                    feat = fd
            except OSError:
                pass
    print("listening on:", ", ".join(list(evs.values()) + list(raws.values())), flush=True)
    for i, (text, secs) in enumerate(STEPS, 1):
        secs = 3 if os.environ.get("PROBE_FAST") else secs
        print("\n=== Step %d: %s" % (i, text), flush=True)
        notify("Folio test, step %d" % i, text)
        time.sleep(0.5 if os.environ.get("PROBE_FAST") else 4)
        print("   (go! %d seconds)" % secs, flush=True)
        before = feature4(feat) if feat else "n/a"
        t_end = time.time() + secs
        n = 0
        while time.time() < t_end:
            r, _, _ = select.select(list(evs) + list(raws), [], [], 0.3)
            for fd in r:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    continue
                if fd in evs:
                    for k in range(0, len(data) - 23, 24):
                        _, _, typ, code, val = struct.unpack("llHHi", data[k:k + 24])
                        if typ == 1:
                            print("   %s  KEY %s (%#x) %s" % (evs[fd], KEYS.get(code, "code %d" % code), code, "down" if val == 1 else "up" if val == 0 else "repeat"), flush=True)
                            n += 1
                else:
                    print("   %s  report %s" % (raws[fd], data[:16].hex()), flush=True)
                    n += 1
        after = feature4(feat) if feat else "n/a"
        print("   events: %d   feature report 4 before: %s   after: %s" % (n, before, after), flush=True)
    notify("Folio test finished", "Thank you: paste the terminal output back.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("run it as root: sudo python3 %s" % sys.argv[0])
    main()
