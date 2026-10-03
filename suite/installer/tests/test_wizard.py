"""Drives the installer window offscreen with fake steps: every page must load without QML warnings, steps must advance, verify lines must parse.
Run: QT_QPA_PLATFORM=offscreen python3 suite/installer/tests/test_wizard.py"""
import os
import sys
import time

os.environ["SURFACE_INSTALLER_FAKE"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import installer                                          # noqa: E402
from PySide6.QtCore import QCoreApplication, QUrl, qInstallMessageHandler, QTimer   # noqa: E402
from PySide6.QtGui import QGuiApplication                 # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine           # noqa: E402

warnings = []
qInstallMessageHandler(lambda mode, ctx, msg: warnings.append(msg))
app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
bridge = installer.Bridge()
engine.rootContext().setContextProperty("bridge", bridge)
engine.load(QUrl.fromLocalFile(os.path.join(installer.HERE, "qml", "Wizard.qml")))
fails = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        fails.append(name)


def wait(cond, secs=8):
    t = time.time()
    while time.time() - t < secs:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


check("window loads", bool(engine.rootObjects()))
check("starts at welcome", bridge.stageName == "welcome")
check("wrong password refused, right one accepted", not bridge.checkPassword("bad") and bridge.checkPassword("ok"))
bridge.startPrepare()
check("prepare is busy", bridge.busy)
check("prepare ends in restart-mok", wait(lambda: not bridge.busy) and bridge.stageName == "restart-mok")
check("progress reached the end", bridge.progress == 1.0)
bridge.startInstall(False)
check("install ends in restart-after", wait(lambda: not bridge.busy) and bridge.stageName == "restart-after")
bridge.skipToVerify()
bridge.startVerify()
check("verify ends in done", wait(lambda: not bridge.busy) and bridge.stageName == "done")
states = [r["state"] for r in bridge.results]
check("verify lines parsed (ok + FAIL seen)", "ok" in states and "FAIL" in states)
os.environ["SURFACE_INSTALLER_FAKE_CMD"] = "exit 3"
bridge._set_stage("install")
errs = []
bridge.failed.connect(errs.append)
bridge.startInstall(False)
wait(lambda: not bridge.busy)
check("a failing step reports the error and stays on the page", bool(errs) and bridge.stageName == "install")
for _ in range(20):
    app.processEvents()
bad = [w for w in warnings if "Wizard.qml" in w or "TypeError" in w or "ReferenceError" in w]
check("no QML warnings", not bad)
for w in bad[:5]:
    print("   ", w)
print("SUMMARY: %d/%d" % (11 - len(fails) if False else 0, 0) if False else ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)
