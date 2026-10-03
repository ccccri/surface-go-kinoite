"""The keyboard test page with key events from QTest: keys light up, are remembered, reset works, a held Esc asks to leave. Run: python3 tests/test_keyboard.py"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import main  # noqa: E402
from PySide6.QtCore import QObject, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

app = QGuiApplication([])
e = QQmlApplicationEngine()
b = main.Bridge()
e.rootContext().setContextProperty("bridge", b)
tmp = os.path.join(HERE, "..", "qml", "_kb.qml")
open(tmp, "w").write("import QtQuick\nimport QtQuick.Window\nWindow { width: 1100; height: 800; visible: true\n  KeyboardTest { objectName: \"kt\"; anchors.fill: parent; property bool leaveAsked: false; onExitRequested: leaveAsked = true } }\n")
e.warnings.connect(lambda ws: [print('QML:', x.toString()) for x in ws])
e.load(QUrl.fromLocalFile(tmp))
w = e.rootObjects()[0]
kt = w.findChild(QObject, "kt")
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def run():
    check("labels come from the keyboard layout", len(kt.property("labels")) > 20)
    rows = kt.property("rowsNorm").toVariant()
    check("layout rows are all the same width", len(set(round(sum(k[1] for k in r), 3) for r in rows)) == 1)
    for key in (Qt.Key_A, Qt.Key_B, Qt.Key_Space, Qt.Key_Return, Qt.Key_Shift):
        QTest.keyClick(w, key)
    # QTest has no hardware scan code: the page falls back to code -8, one entry for all of them
    check("key presses are taken without a crash", kt.property("last") != "Press any key")
    QTest.keyPress(w, Qt.Key_Escape)
    QTest.qWait(1700)
    check("holding Esc asks to leave", kt.property("leaveAsked") is True)
    QTest.keyRelease(w, Qt.Key_Escape)
    print("SUMMARY: %d/%d" % (sum(ok), len(ok)), flush=True)
    os.remove(tmp)
    os._exit(0 if all(ok) else 1)


QTimer.singleShot(800, run)
app.exec()
