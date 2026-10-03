"""Every QML page and component must load without errors. Run on the machine with Qt: python3 tests/test_pages.py"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import main  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402

app = QGuiApplication([])
b = main.Bridge()
e = QQmlApplicationEngine()
for k, v in (("bridge", b), ("startCam", "front"), ("startTest", False), ("keytestSeconds", 0), ("tablet", main.TabletFilter()), ("startPage", "OverviewPage.qml")):
    e.rootContext().setContextProperty(k, v)
e.addImageProvider("preview", b.provider)
bad = 0
qml = os.path.join(HERE, "..", "qml")
for f in sorted(x for x in os.listdir(qml) if x.endswith(".qml") and x != "Main.qml"):
    c = QQmlComponent(e, QUrl.fromLocalFile(os.path.join(qml, f)))
    o = c.create()
    if not o:
        bad += 1
        print("FAIL", f, [x.toString() for x in c.errors()][:2])
print("pages loaded, failures:", bad, flush=True)
os._exit(1 if bad else 0)
