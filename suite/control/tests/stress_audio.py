"""Equaliser and microphone controls under load (needs the equaliser chain enabled). Run: python3 tests/stress_audio.py"""
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import backend  # noqa: E402
import eq  # noqa: E402

ok = True


def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, extra, flush=True)


check("equaliser chain present", eq.available())
orig = eq.load()
try:
    t = time.time()
    n = 0
    while time.time() - t < 6:
        s = eq.new_set(125)
        for b in s["bands"]:
            b["gain"] = random.uniform(-12, 12)
            b["freq"] = random.choice([60, 250, 1000, 4000, 12000])
            b["q"] = random.uniform(0.3, 6)
        s["preamp"] = random.uniform(-12, 0)
        eq.apply(s)
        n += 1
    check("%d random full equaliser updates in 6 s" % n, n > 20)
    check("the sound server is still up", subprocess.run(["systemctl", "--user", "is-active", "pipewire"], capture_output=True, text=True).stdout.strip() == "active")
    nid = backend._pw_node_id("boosted_speakers")
    d = json.loads(subprocess.run(["pw-dump", str(nid)], capture_output=True, text=True).stdout)[0]
    params = {}
    for p in d["info"]["params"]["Props"]:
        if "params" in p and "gainL:Mult" in p["params"]:
            params = dict(zip(p["params"][::2], p["params"][1::2]))
    check("values read back match the last update", abs(params.get("preL:Mult", 0) - 10 ** (s["preamp"] / 20)) < 1e-3)
    # extreme but legal values
    s = eq.new_set(180)
    for b in s["bands"]:
        b.update(gain=24.0, q=20.0, freq=20000.0)
    s["preamp"] = -24.0
    eq.apply(s)
    time.sleep(0.5)
    check("extreme bands (+24 dB, Q 20, 20 kHz) are accepted", subprocess.run(["systemctl", "--user", "is-active", "pipewire"], capture_output=True, text=True).stdout.strip() == "active")
    # mic controls
    m0 = backend.mic_settings()
    t = time.time()
    k = 0
    while time.time() - t < 3:
        backend.set_mic_setting("gain", random.uniform(-12, 12))
        k += 1
    check("%d microphone setting changes in 3 s" % k, k > 10)
    for key in ("gain", "lowcut", "bass", "presence", "treble"):
        backend.set_mic_setting(key, m0[key])
    check("microphone settings restored", abs(backend.mic_settings()["gain"] - m0["gain"]) < 1e-6)
finally:
    eq._store(orig)
    eq.write_conf(eq.effective(orig, "speaker"))
    eq.apply(eq.effective(orig, eq.active_output()))
    print("your equaliser is back", flush=True)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
