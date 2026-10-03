#!/usr/bin/env python3
"""Headless helper (user service): keeps the equaliser of the sound output in step with the jack.

The speakers and the headphone jack are two ports of one sound card. When the equaliser is not synced they have their own settings; this
watches the card (pactl subscribe) and applies the set of the port in use, at login and every time the jack is plugged or unplugged.
It does nothing while the equaliser is off. Uses the same code as Surface Control (eq.py, backend.py), no Qt."""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eq  # noqa: E402


def apply_now(last):
    if not eq.available():
        return last
    out = eq.active_output()
    state = eq.load()
    key = (out, state["sync"], repr(eq.effective(state, out)))
    if key != last:
        eq.apply(eq.effective(state, out))
        print("applied the %s settings%s" % (out, " (synced)" if state["sync"] else ""), flush=True)
    return key


def main():
    last = None
    while True:
        try:
            last = apply_now(last)
            p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True)
            for line in p.stdout:
                # card / sink changes cover plugging the jack; wait a moment for the port to settle, then look
                if "'change' on sink" in line or "'change' on card" in line or "'new' on sink" in line:
                    time.sleep(0.4)
                    last = apply_now(last)
            p.wait()
        except OSError as e:
            print("waiting for the sound server:", e, flush=True)
        time.sleep(3)


if __name__ == "__main__":
    main()
