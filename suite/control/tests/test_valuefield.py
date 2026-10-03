"""The typed-value field: what it accepts, clamps and refuses. Run: python3 tests/test_valuefield.py"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

app = QGuiApplication([])
e = QQmlApplicationEngine()
qml = os.path.join(HERE, "..", "qml")
tmp = os.path.join(qml, "_vf.qml")
open(tmp, "w").write("""
import QtQuick
import QtQuick.Window
Window { width: 300; height: 200; visible: true
  property string results: ""
  ValueField { id: g; from: 1.0; to: 2.4; step: 0.05; value: 1.5 }
  ValueField { id: c; from: 0; to: 1; step: 0.05; value: 0.3 }
  ValueField { id: ev; from: -2; to: 2; step: 0.1; unit: "EV"; value: 0 }
  ValueField { id: boost; from: 100; to: 180; step: 1; unit: "%"; value: 120 }
  ValueField { id: tn; from: 0; to: 5; step: 1; value: 3; names: ["off","low","medium","high","stronger","maximum"] }
  ValueField { id: hue; from: -180; to: 180; step: 1; unit: "\\u00b0"; value: 0 }
  Component.onCompleted: {
    const o = {}
    o.g18 = g.parse("1.8"); o.gcomma = g.parse("1,8"); o.c50 = c.parse("50%"); o.ev = ev.parse("-1.5 EV"); o.evminus = ev.parse("\\u22121"); o.ev07 = ev.parse("+0,7ev")
    o.boost150 = boost.parse("150%"); o.hue = hue.parse("-90\\u00b0"); o.tn_high = tn.parse("high"); o.tn_max = tn.parse("MAXIMUM"); o.tn2 = tn.parse("2")
    o.abc = String(g.parse("abc")); o.empty = String(g.parse("")); o.minus = String(g.parse("-"))
    let got = []; g.committed.connect(v => got.push(v))
    g.text = "9"; g.commit(); g.text = "0"; g.commit(); g.text = "hello"; g.commit(); const after = g.text; g.text = "1,234"; g.commit()
    o.got = got; o.after = after
    o.example_names = tn.example; o.example_unit = ev.example
    results = JSON.stringify(o)
  }
}
""")
e.load(QUrl.fromLocalFile(tmp))
r = json.loads(e.rootObjects()[0].property("results"))
os.remove(tmp)
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, flush=True)


check("decimal comma", r["g18"] == 1.8 and r["gcomma"] == 1.8)
check("percent on a 0..1 control", r["c50"] == 0.5)
check("unit text, unicode minus, plus sign", r["ev"] == -1.5 and r["evminus"] == -1 and r["ev07"] == 0.7 and r["hue"] == -90)
check("percent on a percent control stays", r["boost150"] == 150)
check("level names, case-insensitive, or numbers", r["tn_high"] == 3 and r["tn_max"] == 5 and r["tn2"] == 2)
check("not a number is refused", r["abc"] == "NaN" and r["empty"] == "NaN" and r["minus"] == "NaN")
check("out of range is clamped, rounded, garbage ignored", r["got"] == [2.4, 1, 1.23] and r["after"] == "1.50")
check("the hint shows examples", "low" in r["example_names"] and "e.g." in r["example_unit"])
print("ALL PASS" if ok else "SOME FAILED", flush=True)
os._exit(0 if ok else 1)
