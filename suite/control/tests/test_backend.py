"""Backend checks with an isolated profile folder (never touches your settings). Run: python3 tests/test_backend.py"""
import glob
import os
import shutil
import sys

base = "/tmp/surface-control-test"
shutil.rmtree(base, ignore_errors=True)
os.makedirs(base)
os.environ["SURFACE_PROFILE_DIR"] = base + "/camera"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import backend as b  # noqa: E402

b.UI_FILE = base + "/control.json"
ok = True


def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, extra)


check("no presets at start", b.list_presets("front") == [])
b.set_camera_setting("front", "gamma", 1.8)
b.set_camera_setting("front", "hue", 120)
b.set_camera_setting("front", "hue_spin", 90)
check("save, refuse duplicate, overwrite", b.save_preset("front", "JoJo look") == "ok" and b.save_preset("front", "JoJo look") == "exists" and b.save_preset("front", "JoJo look", True) == "ok")
check("empty and symbol-only names are invalid", b.save_preset("front", "   ") == "invalid" and b.save_preset("front", "///") == "invalid")
check("presets are per camera", b.list_presets("rear") == [] and len(b.list_presets("front")) == 1)
b.reset_camera_settings("front")
b.apply_preset("front", b.list_presets("front")[0]["id"])
s = b.camera_settings("front")
check("apply restores the values", s["gamma"] == 1.8 and s["hue"] == 120 and s["hue_spin"] == 90)
check("the active preset is detected", [p["current"] for p in b.list_presets("front")] == [True])
pid = b.list_presets("front")[0]["id"]
check("rename, duplicate, delete", b.rename_preset("front", pid, "JJBA") == "ok" and b.duplicate_preset("front", "JJBA", "copy") == "ok" and (b.delete_preset("front", "copy") or True) and len(b.list_presets("front")) == 1)
b.set_camera_setting("front", "hue_spin", 0)
check("rainbow 0 removes the key", "hue_spin" not in b.read_profile("front"))
check("every control has its default, range and an explanation", all(it["min"] < it["max"] and it.get("desc") for g in b.controls("front") for it in g["items"]))
# corrupt files
os.makedirs(base + "/presets/front", exist_ok=True)
open(base + "/presets/front/bad.json", "w").write("{not json")
open(base + "/presets/front/wrong.json", "w").write('{"name":"wrong","profile":{"gamma":"x"}}')
check("corrupt preset files do not break the list", isinstance(b.list_presets("front"), list))
b.apply_preset("front", "bad")
b.apply_preset("front", "wrong")
b.apply_preset("front", "missing")
open(b.PROFILE_DIR + "/ov5693.profile", "w").write("\x00\xff garbage \n gamma\n gamma abc\n")
check("a corrupt profile reads as defaults", isinstance(b.camera_settings("front"), dict))
for name in ("A" * 500, "../../etc/passwd", "ünïcödé 日本語 🎸", 'a/b\\c:d*e?f"g<h>i|j'):
    r = b.save_preset("front", name)
    check("preset name %r -> %s" % (name[:16], r), r in ("ok", "invalid"))
check("no preset file outside its folder", all(os.path.dirname(p).endswith("/front") for p in glob.glob(base + "/presets/**/*.json", recursive=True)))
check("ui settings", b.ui_setting("x", 5) == 5 and (b.set_ui_setting("x", False) or True) and b.ui_setting("x", 5) is False)
check("sensors() answers at once", isinstance(b.sensors(), dict))
check("device info has the display date", "display" in b.device_info() and b.device_info()["display"]["year"] > 2000)
check("all health checks are green", all(c["status"] == "ok" for c in b.all_checks()), str([c["name"] for c in b.all_checks() if c["status"] != "ok"]))
print("ALL PASS" if ok else "SOME FAILED", flush=True)
shutil.rmtree(base, ignore_errors=True)
sys.exit(0 if ok else 1)
