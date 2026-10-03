"""The equaliser graph with simulated mouse input: grabbing a band by its frequency, dragging it, double click, wheel, and a drag inside a scrolling page.
Uses a throw-away state folder, never your settings. Run: python3 tests/test_eq_ui.py"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tmp = tempfile.mkdtemp()
os.environ["HOME"] = tmp                 # eq.py and backend.py keep their files under $HOME/.config
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import main  # noqa: E402
from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

app = QGuiApplication([])
e = QQmlApplicationEngine()
b = main.Bridge()
b.setEq = lambda output, s: None          # no sound server involved
e.rootContext().setContextProperty("bridge", b)
qml = os.path.join(HERE, "..", "qml", "_equi.qml")
open(qml, "w").write("""
import QtQuick
import QtQuick.Window
import QtQuick.Controls as QQC2
Window { width: 900; height: 700; visible: true
  QQC2.ScrollView { anchors.fill: parent; contentWidth: availableWidth
    Column { width: parent.width; spacing: 400
      EqEditor { id: ed; objectName: "ed"; width: parent.width; advanced: true; st: ({ sets: { speaker: JSON.parse(JSON.stringify(flat)), headphones: JSON.parse(JSON.stringify(flat)) }, presets: [{ name: "Flat", builtin: true }], available: true, sync: true, active: "speaker" }) }
      Rectangle { width: 10; height: 900 } } } }
""".replace("flat", "({ boost: 120, preamp: 0, bands: [" + ",".join('{type:"%s",freq:%d,gain:0,q:1,on:true}' % (t, f) for t, f in zip(["lowshelf"] + ["peak"] * 8 + ["highshelf"], (60, 120, 250, 500, 1000, 2000, 4000, 8000, 12000, 14000))) + "] })"))
e.warnings.connect(lambda ws: [print("QML:", x.toString()) for x in ws])
e.load(QUrl.fromLocalFile(qml))
w = e.rootObjects()[0]
ed = w.findChild(QObject, "ed")
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def run():
    graph = [c for c in ed.findChildren(QObject) if c.metaObject().className().startswith("QQuickCanvas")][0]
    gx, gy = graph.mapToScene(__import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(0, 0)).x(), graph.mapToScene(__import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(0, 0)).y()
    width, height = graph.property("width"), graph.property("height")
    import math

    def fx(f):
        return gx + math.log(f / 20) / math.log(1000) * width
    y0 = gy + height / 2
    # grab band 5 (1 kHz) slightly off the dot, drag up and to the right
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, QPoint(int(fx(1000)) + 14, int(y0) - 12))
    for i in range(1, 11):
        QTest.mouseMove(w, QPoint(int(fx(1000)) + 14 + i * 6, int(y0) - 12 - i * 6))
        QTest.qWait(10)
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, QPoint(int(fx(1000)) + 74, int(y0) - 72))
    QTest.qWait(100)
    band = ed.property("cur").toVariant()["bands"][4] if hasattr(ed.property("cur"), "toVariant") else ed.property("cur")["bands"][4]
    check("a drag that starts near a dot moves that band (frequency %d Hz, gain %.1f dB)" % (band["freq"], band["gain"]), band["gain"] > 3 and band["freq"] > 1050)
    check("the dragged band becomes the selected one", ed.property("sel") == 4)
    # the page must not have scrolled while dragging
    sv = w.findChild(QObject, "") or None
    flick = [c for c in w.findChildren(QObject) if c.metaObject().className().startswith("QQuickFlickable")]
    ys = [(f.metaObject().className(), round(f.property("contentY") or 0, 1), round(f.property("contentHeight") or 0)) for f in flick]
    print("flickables (class, contentY, contentHeight):", ys)
    check("the page did not scroll during the drag", all((f.property("contentY") or 0) < 1 for f in flick if (f.property("contentHeight") or 0) > 1000) if flick else True)
    # double click switches a band off
    QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, QPoint(int(fx(250)), int(y0)))
    QTest.qWait(100)
    cur = ed.property("cur")
    cur = cur.toVariant() if hasattr(cur, "toVariant") else cur
    check("a double click switches a band off", cur["bands"][2]["on"] is False)
    print("SUMMARY: %d/%d" % (sum(ok), len(ok)), flush=True)
    os.remove(qml)
    os._exit(0 if all(ok) else 1)


QTimer.singleShot(1000, run)
app.exec()
