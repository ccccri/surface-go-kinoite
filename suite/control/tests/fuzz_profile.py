"""Feeds the patched libcamera garbage profiles while a camera streams, and rewrites the profile every 50 ms: no crash, frames keep coming.
It uses your real profile folder (the camera reads that one) and puts your files back at the end. Run: python3 tests/fuzz_profile.py"""
import os
import random
import shutil
import subprocess
import time

d = os.path.expanduser("~/.config/surface-suite/camera")
os.makedirs(d, exist_ok=True)      # a freshly installed system has no profile folder yet
fp = d + "/ov5693.profile"
saved = {}
for n in os.listdir(d) if os.path.isdir(d) else []:
    saved[n] = open(d + "/" + n, "rb").read()
W, H = 1152, 864
fs = W * H * 3 // 2
min_width = [l for l in open(fp).read().splitlines() if l.startswith("min_width")] if os.path.exists(fp) else []
if min_width:
    W, H = int(min_width[0].split()[1]), int(int(min_width[0].split()[1]) * 3 / 4)
    fs = W * H * 3 // 2
cases = [("garbage values", "gamma abc\ncontrast\ntnr 1\nbnr 1 2\nblack 999 -5 a b\nhue_spin nan\nsaturation inf\nexposure 1e308\nmin_width -1\nsharpness -3\n"),
         ("huge numbers", "gamma 1e300\ncontrast -1e300\nshadows 1e9\nhighlights -1e9\ntemperature 99999\nhue 1e12\nhue_spin 1e9\nsharpness 1e9\nexposure 1e9\nsaturation 1e9\n"),
         ("zero and negative", "gamma 0\ngamma -1\ncontrast -5\nsaturation -2\ntnr -5 -5\ntnr 300 300\nbnr 99999 99 99 99 99 99\nblack 255 255 255 255\n"),
         ("binary junk", "\x00\x01\x02\xff\xfe\n\x7f\x7f gamma\n\n###\n#gamma 3\n"),
         ("very long line", "gamma " + "1 " * 50000 + "\n"),
         ("extreme combination", "saturation 2\nhue_spin 360\nsharpness 3\ntemperature 1\ntint 1\nexposure 2\ngamma 2.4\ncontrast 1\nshadows 1\nhighlights 1\n"),
         ("empty file", "")]
ok = True


def stream(secs, tick=None):
    p = subprocess.Popen(["gst-launch-1.0", "-q", "pipewiresrc", "target-object=libcamera_input.__SB_.PCI0.LNK1", "!", "video/x-raw,format=NV12,width=%d,height=%d" % (W, H), "!", "fdsink", "fd=1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    t0 = time.time()
    n = 0
    while time.time() - t0 < secs:
        if len(p.stdout.read(fs)) < fs:
            break
        n += 1
        if tick:
            tick()
    p.terminate()
    p.wait()
    time.sleep(2)
    return n


def wp():
    return subprocess.run(["systemctl", "--user", "is-active", "wireplumber"], capture_output=True, text=True).stdout.strip()


try:
    for name, txt in cases:
        open(fp, "w", errors="surrogateescape").write("\n".join(min_width) + "\n" + txt)
        n = stream(4)
        good = n > 20 and wp() == "active"
        ok &= good
        print(("PASS " if good else "FAIL ") + name, "frames", n, "wireplumber", wp(), flush=True)
    open(fp, "w").write("\n".join(min_width) + "\n")
    nxt = [0.0]

    def churn():
        if time.time() > nxt[0]:
            nxt[0] = time.time() + 0.05
            open(fp + ".t", "w").write("\n".join(min_width) + "\ngamma %.2f\nexposure %.1f\nhue %d\nsaturation %.2f\n" % (random.uniform(1, 2.4), random.uniform(-2, 2), random.randint(-180, 180), random.uniform(0, 2)))
            os.replace(fp + ".t", fp)
    n = stream(8, churn)
    good = n > 40 and wp() == "active"
    ok &= good
    print(("PASS " if good else "FAIL ") + "profile rewritten every 50 ms for 8 s", "frames", n, flush=True)
finally:
    for f in os.listdir(d):
        if f not in saved:
            os.remove(d + "/" + f)
    for f, c in saved.items():
        open(d + "/" + f, "wb").write(c)
    print("your profiles are back", flush=True)
print("ALL PASS" if ok else "SOME FAILED")
