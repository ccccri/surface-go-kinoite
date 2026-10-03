"""Preview stress: rapid start/stop/switch, kill the pipeline from outside, setting floods, restart of the camera service.
Needs the cameras; uses an isolated profile folder for the app's own writes. Run: python3 tests/stress_preview.py"""
import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SURFACE_PROFILE_DIR"] = "/tmp/surface-control-stress/camera"
sys.argv = ["x"]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import backend  # noqa: E402
import main  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
b = main.Bridge()
b._frameSignal.connect(b._onFrame)
b._previewEnded.connect(b._onPreviewEnded)
b._restartSignal.connect(b._restartFinished)
# the picture size the cameras really offer comes from the real profile: copy only that into the isolated folder
real = os.path.expanduser("~/.config/surface-suite/camera")
os.makedirs(backend.PROFILE_DIR, exist_ok=True)
for cam, model in (("front", "ov5693"), ("rear", "ov8865")):
    try:
        lines = [l for l in open(real + "/" + model + ".profile") if l.startswith("min_width")]
    except OSError:
        lines = []
    open(backend.PROFILE_DIR + "/" + model + ".profile", "w").write("".join(lines))
res = []


def gst():
    return int(subprocess.run("ps -eo args | grep -c '[g]st-launch-1.0 -q pipewiresrc'", shell=True, capture_output=True, text=True).stdout.strip() or 0)


def rec(name, ok, extra=""):
    res.append(ok)
    print(("PASS " if ok else "FAIL ") + name, extra, flush=True)


steps = []


def step(ms, fn):
    steps.append((ms, fn))


def rapid():
    for i in range(30):
        b.startPreview("front" if i % 2 == 0 else "rear")
        if i % 3 == 0:
            b.stopPreview()
    b.stopPreview()


step(100, rapid)
step(2500, lambda: rec("30 rapid start/stop/switch leave no process", gst() == 0, "(%d left)" % gst()))
step(100, lambda: b.startPreview("front"))
step(5000, lambda: subprocess.run("pkill -x gst-launch-1.0", shell=True))
step(3500, lambda: rec("the app recovers when the pipeline is killed from outside", b.previewCamera == ""))
step(100, lambda: b.startPreview("rear"))
step(3500, lambda: rec("the preview restarts and delivers frames", b.previewFrame > 0 and b.previewCamera == "rear", "(%d frames)" % b.previewFrame))


def flood():
    t = time.time()
    n = 0
    while time.time() - t < 2:
        b.setCameraSetting("rear", "gamma", 1.0 + (n % 14) / 10.0)
        n += 1
    rec("hundreds of setting writes in 2 s", n > 100, "(%d)" % n)
    rec("the profile still parses", "gamma" in backend.read_profile("rear"))


step(100, flood)
step(300, lambda: b.stopPreview())
step(200, lambda: b.restartCameras())
step(9000, lambda: rec("restarting the camera service finishes", not b.busy))
step(100, lambda: b.startPreview("front"))
step(3500, lambda: rec("preview works after the restart", b.previewFrame > 0, "(%d frames)" % b.previewFrame))
step(100, lambda: b.stopPreview())
step(1000, lambda: (print("SUMMARY: %d/%d" % (sum(res), len(res)), flush=True), os._exit(0 if all(res) else 1)))
idx = {"i": 0}


def go():
    if idx["i"] >= len(steps):
        return
    ms, fn = steps[idx["i"]]
    idx["i"] += 1
    QTimer.singleShot(ms, lambda: (fn(), go()))


go()
app.exec()
