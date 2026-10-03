"""NFC window mode with a fake daemon socket: the flag file, the events, and nfc-notify seeing the window. Run: python3 tests/test_nfc_window.py"""
import json
import os
import socket
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NFC_SOCK"] = "/tmp/nfc-test.sock"
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import main  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

if os.path.exists("/tmp/nfc-test.sock"):
    os.remove("/tmp/nfc-test.sock")
srv = socket.socket(socket.AF_UNIX)
srv.bind("/tmp/nfc-test.sock")
srv.listen(1)


def serve():
    c, _ = srv.accept()
    time.sleep(0.4)
    c.sendall((json.dumps({"time": time.time() - 0.05, "uid": "04:aa", "type": "iso14443", "records": [{"kind": "uri", "value": "https://example.org"}], "read_ms": 12}) + "\n").encode())
    time.sleep(0.3)
    c.sendall(b"not json at all\n")
    c.sendall((json.dumps({"time": time.time(), "uid": "04:bb", "type": "mifare", "records": None, "read_ms": 7}) + "\n").encode())
    time.sleep(3)


threading.Thread(target=serve, daemon=True).start()
app = QGuiApplication([])
b = main.Bridge()
b._nfcSignal.connect(b._onNfc)
flag = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "surface-nfc-window")
ok = []


def check(name, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


b.nfcWindow(True)
check("the window writes its pid", os.path.exists(flag) and open(flag).read() == str(os.getpid()))
b.nfcWindow(True)
check("opening twice is harmless", b._nfcThread is not None)


def done():
    ev = b.nfcEvents
    check("two tags arrived, newest first", [e["uid"] for e in ev] == ["04:bb", "04:aa"])
    check("a broken line is ignored", len(ev) == 2)
    check("link, read time and delivery are filled", ev[1]["lines"] == ["Link: https://example.org"] and ev[1]["readMs"] == 12 and ev[1]["deliverMs"] >= 0)
    check("a card without NDEF is described", "no readable data" in ev[0]["lines"][0])
    b.nfcWindow(False)
    check("closing removes the flag", not os.path.exists(flag))
    b.nfcWindow(False)
    print("SUMMARY: %d/%d" % (sum(ok), len(ok)), flush=True)
    os._exit(0 if all(ok) else 1)


QTimer.singleShot(2500, done)
app.exec()
