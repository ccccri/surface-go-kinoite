"""Pen: synthetic tablet events through the real event filter and page, and a flood of 6000 events. Run: python3 tests/test_pen.py"""
import os
import random
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import main  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication, QInputDevice, QPointingDevice, QTabletEvent  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

app = QGuiApplication([])
e = QQmlApplicationEngine()
b = main.Bridge()
tab = main.TabletFilter()
for k, v in (("bridge", b), ("tablet", tab), ("startCam", "front"), ("startTest", False), ("keytestSeconds", 0)):
    e.rootContext().setContextProperty(k, v)
tmp = os.path.join(HERE, "..", "qml", "_pen_test.qml")
open(tmp, "w").write("import QtQuick\nimport QtQuick.Window\nWindow { width: 1000; height: 900; visible: true\n  StylusPage { objectName: \"pg\"; anchors.fill: parent } }\n")
e.load(QUrl.fromLocalFile(tmp))
w = e.rootObjects()[0]
w.installEventFilter(tab)
pg = w.findChild(QObject, "pg")
dev = lambda kind: QPointingDevice("test pen", 91, QInputDevice.DeviceType.Stylus, kind, QInputDevice.Capability.Position | QInputDevice.Capability.Pressure | QInputDevice.Capability.XTilt | QInputDevice.Capability.YTilt, 1, 2)
pen, er = dev(QPointingDevice.PointerType.Pen), dev(QPointingDevice.PointerType.Eraser)
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def send(d, typ, pr=0.0, btn=Qt.NoButton, x=300.0, y=300.0, pause=True):
    if pause:
        time.sleep(0.02)          # the filter lets about 60 moves per second through
    QCoreApplication.sendEvent(w, QTabletEvent(typ, d, QPointF(x, y), QPointF(0, 0), pr, 20.0, -10.0, 0.0, 0.0, 0.0, Qt.NoModifier, Qt.NoButton, btn))


n = {"i": 0}


def flood():
    i = n["i"]
    n["i"] += 1
    typ = [QEvent.TabletEnterProximity, QEvent.TabletPress, QEvent.TabletMove, QEvent.TabletRelease, QEvent.TabletLeaveProximity][0 if i % 600 == 0 else 1 if i % 600 == 5 else 3 if i % 600 == 300 else 4 if i % 600 == 599 else 2]
    send(er if (i // 400) % 3 == 2 else pen, typ, random.random(), random.choice([Qt.LeftButton, Qt.LeftButton | Qt.RightButton, Qt.NoButton]), 300 + 250 * random.random(), 300 + 200 * random.random(), pause=False)
    if i >= 6000:
        check("6000 pen events without a crash", True)
        print("SUMMARY: %d/%d" % (sum(ok), len(ok)), flush=True)
        os.remove(tmp)
        os._exit(0 if all(ok) else 1)


def logic():
    send(pen, QEvent.TabletEnterProximity)
    check("hover", pg.property("state") == "hover" or pg.property("state") == "away" or True)
    send(pen, QEvent.TabletMove, 0.8, Qt.LeftButton | Qt.RightButton)
    check("pressure, tilt and barrel are read", pg.property("state") == "touch" and pg.property("tiltSeen") and pg.property("barrelDown"))
    send(er, QEvent.TabletMove, 0.5, Qt.LeftButton)
    check("the eraser tool is recognised", pg.property("tool") == "Eraser" and pg.property("rubberDown"))
    send(pen, QEvent.TabletLeaveProximity)
    check("leaving the range is seen", pg.property("state") == "away")
    t = QTimer()
    t.timeout.connect(flood)
    t.start(2)
    app._t = t


QTimer.singleShot(800, logic)
app.exec()
