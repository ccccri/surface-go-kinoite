"""Surface Control backend: health checks and the actions the pages trigger. No UI code here."""
import glob
import os
import threading
import time
import re
import subprocess
from dataclasses import dataclass, asdict

GUIDE = os.environ.get("SURFACE_GUIDE", os.path.expanduser("~/surface-go-kinoite"))
KMODS = "/var/lib/local-kmods"


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


@dataclass
class Check:
    group: str
    name: str
    status: str   # ok | warn | fail
    detail: str = ""
    what: str = ""   # what the fix does
    tech: str = ""   # how it works, where it lives
    fix: str = ""    # what to do when it is not green


# name prefix -> (what it does, how it works, what to do when it is not working)
INFO = {
    "Kernel modules built": (
        "Linux ships the camera, NFC and volume-button drivers without the Surface-specific changes. The suite rebuilds four of them with patches and signs them for Secure Boot.",
        "The modules are built against one exact kernel version and stored in /var/lib/local-kmods. A marker file built-<kernel> says the build for that kernel exists. Every kernel update brings a new version, so the modules must be built again.",
        "Open Updates and repair and press Rebuild, then restart. The build takes a few minutes and needs the sudo password."),
    "Module ov8865": (
        "Driver of the rear camera sensor. Patched so the picture has the right pixel rate (stable exposure, no flashing), finer analogue gain steps, no unusable mode, and a reset after a stale mode.",
        "Four small patches in patches/ov8865-*.patch. The stock driver reports a pixel rate four times too high for the binned mode, so the auto exposure believes it exposes for a quarter of the real time and the picture flashes under artificial light.",
        "Rebuild the modules (Updates and repair). If it stays red, the kernel changed in a way the patches do not fit: check the build log."),
    "Module ov5693": (
        "Driver of the front camera sensor. Patched to cap the frame rate at 30 fps.",
        "patches/ov5693-cap-30fps.patch. The sensor advertises modes faster than the CIO2 receiver can take, which makes the stream stall.",
        "Rebuild the modules (Updates and repair)."),
    "Module nxp_nci": (
        "Driver of the NFC chip. Patched so the Surface Go reader answers reliably and polls often enough to detect tags quickly.",
        "Three patches (nxp-nci-*.patch): the NXP3001 ACPI id, a read retry on the I2C bus, and a shorter poll period.",
        "Rebuild the modules (Updates and repair)."),
    "Secure Boot": (
        "With Secure Boot on, the kernel only loads signed modules. The suite signs its modules with its own key, which you enrolled once at the blue MOK screen.",
        "mokutil --sb-state reports the state. The key lives in /var/lib/local-kmods; the public part is enrolled in the firmware.",
        "If modules do not load after a firmware reset, enrol the key again with the first install script."),
    "libcamera package": (
        "libcamera is the camera stack behind Kamoso, Firefox and video-call apps. The patches fix crashes, the mirrored rear camera, autofocus, exposure, colour, lens shading, noise and add the live settings of the Cameras page.",
        "libcamera 0.7.1 is rebuilt in a toolbox with the patches in patches/libcamera-0.7.1-*.patch and installed in /var/usrlocal/libcamera-patched. It does not replace the system package: a WirePlumber drop-in points the camera service at it.",
        "A libcamera update changes the version: the patches must be ported before the camera fixes work again. Until then the stock libcamera still works, without the fixes."),
    "Rear camera visible": (
        "The rear camera shows up as a PipeWire device, which is how apps get cameras on this desktop.",
        "WirePlumber runs libcamera and publishes one node per camera (libcamera_input.__SB_.PCI0.LNK0 is the rear one).",
        "Restart the camera service (Updates and repair). If still missing: the sensor module is not loaded, see the module checks."),
    "Front camera visible": (
        "The front camera shows up as a PipeWire device.",
        "Node libcamera_input.__SB_.PCI0.LNK1.",
        "Restart the camera service (Updates and repair)."),
    "WirePlumber uses": (
        "Makes the camera service load the patched libcamera instead of the system one. Without it apps get no autofocus fix, wrong colours and the mirrored rear camera.",
        "A drop-in is a small file that adds settings to a service without touching its original file: ~/.config/systemd/user/wireplumber.service.d/patched-libcamera.conf sets LD_LIBRARY_PATH.",
        "Run the install script again, it recreates the drop-in."),
    "Tuning ov5693": (
        "Colour and image tuning of the front sensor: black level, colour correction, lens shading (brighter corners), tone curve and noise reduction.",
        "/etc/libcamera/ipa/ipu3/ov5693.yaml, generated from the Windows calibration file plus our own measurements (tools/cpf_to_tuning.py). The Cameras page changes values on top of this file without editing it.",
        "Run the install script again to regenerate the file."),
    "Tuning ov8865": (
        "Colour and image tuning of the rear sensor, calibrated separately from the front one.",
        "/etc/libcamera/ipa/ipu3/ov8865.yaml, same origin as the front. The autofocus search is not in this file but in the patched libcamera.",
        "Run the install script again to regenerate the file."),
    "Rear camera size mode": (
        "Which picture size the rear camera offers to apps first. Apps take the first size, so this decides what Kamoso or Zoom get.",
        "The key min_width of the rear camera profile (Cameras page). Smooth keeps 30 fps, bigger sizes use the full sensor at about 15 fps.",
        "Change it in the Cameras page."),
    "NFC reader": (
        "Reads NFC tags and shows a notification with their content, with a delay of about half a second.",
        "A root daemon (nfc-daemon) owns the reader through the kernel NFC subsystem; a user service (nfc-notify) plays a sound and shows the notification.",
        "Check the NFC page. If the device is missing, the nxp_nci modules are not loaded."),
    "Battery": (
        "Charge level and health of the battery.",
        "Read from /sys/class/power_supply. Health is the full-charge capacity now divided by the capacity when new.",
        "Nothing to fix: below 80% health the battery is simply worn."),
}


def info_for(name):
    return next((v for k, v in INFO.items() if name.startswith(k)), ("", "", ""))


def kernel_checks():
    k = os.uname().release
    out = []
    built = os.path.exists(f"{KMODS}/built-{k}")
    out.append(Check("System", "Kernel modules built for this kernel", "ok" if built else "fail",
                     k if built else f"{k}: no build marker, the camera, NFC and volume fixes are not active (Updates > Rebuild)"))
    try:
        mods = open("/proc/modules").read()
    except OSError:
        mods = ""
    for m in ("ov8865", "ov5693", "nxp_nci_i2c", "nxp_nci"):
        line = next((l for l in mods.splitlines() if l.startswith(m + " ")), "")
        if not line:
            out.append(Check("System", f"Module {m}", "fail", "not loaded"))
        elif "(O)" in line:
            out.append(Check("System", f"Module {m}", "ok", "local patched build"))
        else:
            out.append(Check("System", f"Module {m}", "warn", "stock module loaded (patched one missing for this kernel?)"))
    rc, sb = run(["mokutil", "--sb-state"])
    out.append(Check("System", "Secure Boot", "ok", sb.splitlines()[0] if sb else "unknown"))
    return out


def camera_checks():
    out = []
    rc, nodes = run(["pw-cli", "ls", "Node"])
    for lnk, label in (("LNK0", "Rear camera"), ("LNK1", "Front camera")):
        out.append(Check("Cameras", label + " visible to apps", "ok" if lnk in nodes else "fail",
                         "PipeWire node present" if lnk in nodes else "no PipeWire node"))
    rc, env = run(["systemctl", "--user", "show", "wireplumber", "-p", "Environment"])
    out.append(Check("Cameras", "WirePlumber uses the patched libcamera", "ok" if "libcamera-patched" in env else "fail",
                     "" if "libcamera-patched" in env else "drop-in missing: other apps get the stock libcamera"))
    for s in ("ov5693", "ov8865"):
        p = f"/etc/libcamera/ipa/ipu3/{s}.yaml"
        try:
            txt = open(p).read()
            out.append(Check("Cameras", f"Tuning {s}", "ok" if "- Lsc:" in txt else "warn",
                             "lens shading + black level + tone curve" if "- Lsc:" in txt else "base tuning only"))
        except OSError:
            out.append(Check("Cameras", f"Tuning {s}", "fail", p + " missing"))
    out.append(Check("Cameras", "Rear camera size mode", "ok", rear_mode()))
    return out


def rear_mode():
    m = int(read_profile("rear").get("min_width", [0])[0])
    return {2048: "high", 3200: "max"}.get(m, "smooth") if m else "smooth"


def libcamera_check():
    rc, v = run(["rpm", "-q", "--qf", "%{VERSION}", "libcamera"])
    patches = glob.glob(f"{GUIDE}/patches/libcamera-{v}-*.patch") if rc == 0 else []
    if rc != 0:
        return Check("System", "libcamera package", "warn", "not installed")
    if patches:
        return Check("System", "libcamera package", "ok", f"{v}: {len(patches)} patches available")
    return Check("System", "libcamera package", "warn", f"{v}: no patches for this version, fixes need porting")


def device_checks():
    out = []
    if os.path.isdir("/sys/class/nfc/nfc0"):
        rc, a = run(["systemctl", "is-active", "nfc-daemon"])
        out.append(Check("Devices", "NFC reader", "ok" if a == "active" else "warn", "daemon " + a))
    else:
        out.append(Check("Devices", "NFC reader", "fail", "/sys/class/nfc/nfc0 missing"))
    for b in glob.glob("/sys/class/power_supply/BAT*"):
        try:
            cap = int(open(b + "/capacity").read())
            full = int(open(b + "/charge_full").read())
            design = int(open(b + "/charge_full_design").read())
            st = open(b + "/status").read().strip()
            out.append(Check("Devices", "Battery", "ok", f"{cap}% {st.lower()}, health {100 * full // design}%"))
        except (OSError, ValueError, ZeroDivisionError):
            pass
    return out


def all_checks():
    items = kernel_checks() + [libcamera_check()] + camera_checks() + device_checks()
    for c in items:
        c.what, c.tech, c.fix = info_for(c.name)
    return [asdict(c) for c in items]




def _num(path, default=None):
    try:
        return float(open(path).read())
    except (OSError, ValueError):
        return default


def _iio(name):
    for d in glob.glob("/sys/bus/iio/devices/iio:device*"):
        try:
            if open(d + "/name").read().strip() == name:
                return d
        except OSError:
            pass
    return None


def _battery_read():
    """Battery numbers from sysfs (plain files: fast)."""
    for b in glob.glob("/sys/class/power_supply/BAT*"):
        cap, full, design = _num(b + "/capacity"), _num(b + "/charge_full"), _num(b + "/charge_full_design")
        now, cur, volt = _num(b + "/charge_now"), _num(b + "/current_now"), _num(b + "/voltage_now")
        try:
            status = open(b + "/status").read().strip()
        except OSError:
            status = "Unknown"
        bat = {"percent": min(cap, 100) if cap is not None else None, "status": status,
               "cycles": int(_num(b + "/cycle_count", 0)), "health": round(100 * full / design) if full and design else None}
        if cur is not None and volt is not None:
            bat["watts"] = round(cur * volt / 1e12, 1)
        if cur and now is not None and full is not None and cur > 0:
            hours = (full - now) / cur if status == "Charging" else now / cur
            if hours > 0:
                bat["hours"] = round(hours, 1)
        return bat
    return None


_sens = {"light": None, "seen": 0.0, "thread": None}


def sensors():
    """Light and battery. The battery is read at once; the light sensor sits behind the sensor hub (a read of a sleeping sensor takes
    ~200 ms, an awake one ~12 ms) so a background thread reads it about 8 times a second while calls keep coming (the hub itself updates at 10 Hz)."""
    import threading
    import time
    _sens["seen"] = time.monotonic()
    if _sens["thread"] is None or not _sens["thread"].is_alive():
        def loop():
            d = _iio("als")
            while d and time.monotonic() - _sens["seen"] < 4.0:
                raw, sc = _num(d + "/in_illuminance_raw"), _num(d + "/in_illuminance_scale", 1)
                if raw is not None:
                    _sens["light"] = round(raw * sc, 1)
                time.sleep(0.05)
        _sens["thread"] = threading.Thread(target=loop, daemon=True)
        _sens["thread"].start()
    out = {}
    if _sens["light"] is not None:
        out["lux"] = _sens["light"]
    bat = _battery_read()
    if bat:
        out["battery"] = bat
    return out


def device_info():
    """What tells the age and the identity of this tablet: firmware, panel, battery, storage, system install. Everything readable without root."""
    import time
    def rd(p, d=""):
        try:
            return open(p).read().strip()
        except OSError:
            return d
    out = {"model": rd("/sys/class/dmi/id/sys_vendor") + " " + rd("/sys/class/dmi/id/product_name"),
           "firmware": rd("/sys/class/dmi/id/bios_version"), "firmwareDate": rd("/sys/class/dmi/id/bios_date")}
    # display: manufacture week and year, name, from the EDID the panel reports
    for p in glob.glob("/sys/class/drm/*eDP*/edid"):
        try:
            e = open(p, "rb").read()
            if len(e) >= 128:
                week, year = e[16], e[17] + 1990
                name = ""
                for k in range(54, 126, 18):
                    if e[k:k + 3] == b"\x00\x00\x00" and e[k + 3] == 0xFC:
                        name = e[k + 5:k + 18].split(b"\n")[0].decode("ascii", "replace").strip()
                out["display"] = {"name": name, "week": week, "year": year, "size": f"{e[21]} x {e[22]} cm"}
        except OSError:
            pass
    for p in glob.glob("/sys/class/power_supply/BAT*"):
        out["battery"] = {"maker": rd(p + "/manufacturer"), "model": rd(p + "/model_name"), "serial": rd(p + "/serial_number"),
                          "design": round((_num(p + "/charge_full_design", 0) or 0) / 1000), "now": round((_num(p + "/charge_full", 0) or 0) / 1000)}
        break
    # the disk the system lives on (an SD card in the slot would otherwise be picked first)
    rc, src = run(["findmnt", "-no", "SOURCE", "/var"])
    rc, parent = run(["lsblk", "-no", "PKNAME", src.split("[")[0]]) if src else (1, "")
    cand = [parent.splitlines()[0]] if rc == 0 and parent.strip() else []
    for n in cand + [os.path.basename(p) for p in sorted(glob.glob("/sys/block/*"))]:
        p = "/sys/block/" + n
        if n.startswith(("nvme", "mmcblk", "sd")) and "boot" not in n:
            size = (_num(p + "/size", 0) or 0) * 512 / 1e9
            if size > 1:
                out["storage"] = {"model": rd(p + "/device/model") or rd(p + "/device/name"), "size": round(size)}
                break
    try:
        st = os.stat("/var/home") if os.path.exists("/var/home") else os.stat("/var")
        rc, birth = run(["stat", "-c", "%w", "/var"])
        out["installed"] = birth.split(" ")[0] if birth and birth[0].isdigit() else ""
    except OSError:
        out["installed"] = ""
    cpu = ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    out["cpu"] = cpu
    try:
        out["memory"] = round(int(next(l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemTotal"))) / 1048576, 1)
    except (OSError, StopIteration, ValueError):
        out["memory"] = 0
    out["kernel"] = os.uname().release
    return out


def folio_reset():
    return run(["systemctl", "start", "folio-reset.service"], timeout=40)


def folio_attached():
    return any(open(f).read().strip() == "09b5" for f in glob.glob("/sys/bus/usb/devices/*/idProduct")
               if os.path.exists(os.path.dirname(f) + "/idVendor") and open(os.path.dirname(f) + "/idVendor").read().strip() == "045e")


# ---- camera profile: ~/.config/surface-suite/camera/<sensor>.profile, read live by the patched libcamera ----
PROFILE_DIR = os.environ.get("SURFACE_PROFILE_DIR", os.path.expanduser("~/.config/surface-suite/camera"))
SENSORS = {"front": "ov5693", "rear": "ov8865"}
# picture sizes offered to apps (key "min_width": the smallest width offered, which is the first size apps take) and what each costs
SIZES = {
    "front": [(0, "1152x864", "about 28 fps"), (1536, "1536x1152", "about 28 fps"), (2048, "2048x1536", "about 23 fps"),
              (2560, "2560x1920", "about 20 fps")],
    "rear": [(0, "1536x1152", "30 fps"), (2048, "2048x1536", "about 15 fps"), (2560, "2560x1920", "about 13 fps"),
             (3200, "3200x2400", "about 11 fps")],
}
PREVIEW_SIZE = {"front": {0: (1152, 864), 1536: (1536, 1152), 2048: (2048, 1536), 2560: (2560, 1920)},
                "rear": {0: (1536, 1152), 2048: (2048, 1536), 2560: (2560, 1920), 3200: (3200, 2400)}}


def profile_path(cam):
    return os.path.join(PROFILE_DIR, SENSORS[cam] + ".profile")


def read_profile(cam):
    out = {}
    try:
        for line in open(profile_path(cam)):
            line = line.split("#")[0].split()
            if line:
                try:
                    out[line[0]] = [float(x) for x in line[1:]]
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def write_profile(cam, values):
    """Atomic write: the pipeline polls the file and must never see a half-written one."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    path = profile_path(cam)
    if not values:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("# Written by Surface Control. Read live by the patched libcamera; delete the file to go back to the tuning defaults.\n")
        for k, v in values.items():
            f.write(k + " " + " ".join(("%g" % x) for x in v) + "\n")
    os.replace(tmp, path)


def tuning_defaults(cam):
    """What the tuning file gives when the profile says nothing."""
    import json
    try:
        d = json.load(open(f"{GUIDE}/tuning/calibration/{SENSORS[cam]}.json"))
    except (OSError, ValueError):
        d = {}
    tone = d.get("tone", {})
    return {"gamma": tone.get("gamma", 1.5), "contrast": tone.get("contrast", 0.3),
            "black": d.get("black", [1, 5, 1, 1]), "bnr": d.get("bnr", [1700, 16, 6, 6, 6, 8]),
            "tnr": [48, 12]}


# temporal denoise levels: (minimum weight in 1/256, threshold). Lower weight = stronger. Level 0 is off.
TNR_LEVELS = [(0, 0), (160, 12), (96, 12), (48, 12), (24, 14), (12, 16)]
TNR_NAMES = ["off", "low", "medium", "high", "stronger", "maximum"]


def tnr_level(tnr):
    if len(tnr) != 2:
        return 3
    return min(range(len(TNR_LEVELS)), key=lambda i: abs(TNR_LEVELS[i][0] - tnr[0]) + abs(TNR_LEVELS[i][1] - tnr[1]))


def controls(cam):
    """The adjustments of the Cameras page, grouped like a photo editor. 'default' is what the tuning gives."""
    d = tuning_defaults(cam)
    return [
        {"group": "Light", "items": [
            {"key": "exposure", "label": "Exposure", "min": -2, "max": 2, "step": 0.1, "default": 0, "unit": "EV",
             "desc": "Brightens or darkens the whole picture by changing the brightness the auto exposure aims for. Works with the light the sensor really collects, so it adds less noise than brightening afterwards."},
            {"key": "gamma", "adv": True, "label": "Brightness curve", "min": 1.0, "max": 2.4, "step": 0.05, "default": d["gamma"], "unit": "",
             "desc": "Higher values lift the dark and middle tones (like the middle slider of Curves). The picture looks brighter and flatter."},
            {"key": "contrast", "label": "Contrast", "min": 0, "max": 1, "step": 0.05, "default": d["contrast"], "unit": "",
             "desc": "Darkens the shadows and brightens the highlights without moving the middle tones."},
            {"key": "shadows", "label": "Shadows", "min": -1, "max": 1, "step": 0.05, "default": 0, "unit": "",
             "desc": "Raises (positive) or lowers (negative) only the dark part of the picture, to open up a dark room or deepen the blacks."},
            {"key": "highlights", "label": "Highlights", "min": -1, "max": 1, "step": 0.05, "default": 0, "unit": "",
             "desc": "Lowers (negative) or raises (positive) only the bright part, to recover a bright window or sky."},
            {"key": "blackShift", "adv": True, "label": "Black point", "min": -8, "max": 24, "step": 1, "default": 0, "unit": "",
             "desc": "The level the sensor calls black. Higher gives deeper blacks and a slightly darker picture; too high crushes the shadows."},
        ]},
        {"group": "Colour", "items": [
            {"key": "saturation", "label": "Saturation", "min": 0, "max": 2, "step": 0.05, "default": 1, "unit": "",
             "desc": "How vivid the colours are. 0 is black and white, 1 is the natural picture."},
            {"key": "temperature", "label": "Temperature", "min": -1, "max": 1, "step": 0.05, "default": 0, "unit": "",
             "desc": "Moves the colours towards blue (negative, cooler) or orange (positive, warmer). Use it when the light is yellow or bluish."},
            {"key": "tint", "label": "Tint", "min": -1, "max": 1, "step": 0.05, "default": 0, "unit": "",
             "desc": "Moves the colours towards green (negative) or magenta (positive). Corrects fluorescent light or a colour cast on skin."},
            {"key": "hue", "label": "Hue shift", "min": -180, "max": 180, "step": 1, "default": 0, "unit": "\u00b0",
             "desc": "Rotates all the colours around the colour wheel: -180 to 180 is the whole wheel (skin turns blue, green, purple...). A creative effect."},
            {"key": "hue_spin", "label": "Rainbow", "min": -360, "max": 360, "step": 5, "default": 0, "unit": "\u00b0/s",
             "desc": "Keeps turning the colour wheel all the time, so the colours change constantly. The number is the speed in degrees per second: 360 is one full turn every second, 30 one turn in 12 seconds. Negative turns the other way. 0 is off."},
        ]},
        {"group": "Detail", "items": [
            {"key": "sharpness", "label": "Sharpness", "min": 0, "max": 3, "step": 0.1, "default": 0, "unit": "",
             "desc": "Makes edges crisper. Small differences are ignored so the noise is not sharpened. Uses some CPU at large sizes."},
            {"key": "spatial", "adv": True, "label": "Noise reduction", "min": 0, "max": 4000, "step": 100, "default": d["bnr"][0], "unit": "",
             "desc": "Smooths each frame. Too much makes skin and walls look waxy."},
            {"key": "temporal", "label": "Grain removal over time", "min": 0, "max": 5, "step": 1, "default": tnr_level(d["tnr"]), "unit": "level",
             "desc": "Averages with the previous frame: removes the crawling grain on flat areas. Strong levels leave faint trails behind fast movement."},
        ]},
    ]


SIMPLE_KEYS = ("exposure", "gamma", "contrast", "shadows", "highlights", "saturation", "temperature", "tint", "hue", "hue_spin", "sharpness")


def camera_settings(cam):
    """Values as shown in the UI: profile value if present, else the default. 'dirty' tells if anything is customised."""
    p, d = read_profile(cam), tuning_defaults(cam)
    out = {}
    for g in controls(cam):
        for it in g["items"]:
            out[it["key"]] = it["default"]
    for k in SIMPLE_KEYS:
        if k in p and p[k]:
            out[k] = p[k][0]
    if "black" in p and len(p["black"]) == 4:
        out["blackShift"] = round(p["black"][0] - d["black"][0])
    if "bnr" in p and len(p["bnr"]) == 6:
        out["spatial"] = p["bnr"][0]
    if "tnr" in p:
        out["temporal"] = tnr_level(p["tnr"])
    out["minWidth"] = int(p.get("min_width", [0])[0])
    out["mirror"] = bool(p.get("mirror", [0])[0])
    out["flip"] = bool(p.get("flip", [0])[0])
    out["focusManual"] = "focus" in p
    out["focus"] = int(p["focus"][0]) if p.get("focus") else int(focus_state(cam).get("focus", 0))
    out["dirty"] = any(k != "min_width" for k in p)
    return out


def set_camera_setting(cam, key, value):
    """Change one setting; the others stay as they are. Returns True when the size changed (the camera service restarts)."""
    p, d = read_profile(cam), tuning_defaults(cam)
    restart = False
    if key in SIMPLE_KEYS:
        default = next(it["default"] for g in controls(cam) for it in g["items"] if it["key"] == key)
        if abs(float(value) - default) < 1e-9:
            p.pop(key, None)
        else:
            p[key] = [round(float(value), 3)]
    elif key == "blackShift":
        if int(value) == 0:
            p.pop("black", None)
        else:
            p["black"] = [max(0, b + int(value)) for b in d["black"]]
    elif key == "spatial":
        if int(value) == d["bnr"][0]:
            p.pop("bnr", None)
        else:
            p["bnr"] = [int(value)] + d["bnr"][1:]
    elif key == "temporal":
        if int(value) == tnr_level(d["tnr"]):
            p.pop("tnr", None)
        else:
            p["tnr"] = list(TNR_LEVELS[int(value)])
    elif key in ("mirror", "flip"):
        if value:
            p[key] = [1]
        else:
            p.pop(key, None)
    elif key == "focus":
        p["focus"] = [max(0, min(1023, int(value)))]
    elif key == "focusManual":
        if value:
            p["focus"] = [int(focus_state(cam).get("focus", 400))]
        else:
            p.pop("focus", None)
    elif key == "minWidth":
        if int(value):
            p["min_width"] = [int(value)]
        else:
            p.pop("min_width", None)
        restart = True
    write_profile(cam, p)
    if restart:
        run(["systemctl", "--user", "restart", "wireplumber"], timeout=30)
    return restart


def reset_camera_setting(cam, key):
    """Put one control back to its default."""
    default = next((it["default"] for g in controls(cam) for it in g["items"] if it["key"] == key), None)
    if default is not None:
        set_camera_setting(cam, key, default)


def reset_camera_settings(cam, keep_size=True):
    p = read_profile(cam)
    keep = {k: v for k, v in p.items() if k == "min_width" and keep_size}
    write_profile(cam, keep)


def focus_state(cam):
    """Lens position and sharpness the autofocus last reported (written by the patched libcamera while a camera is open)."""
    out = {}
    path = f"/dev/shm/surface-camera-{SENSORS[cam]}.state"
    try:
        import time
        if time.time() - os.path.getmtime(path) > 4:
            return out   # no camera open: the file is old
        for line in open(path):
            k, _, v = line.partition(" ")
            out[k] = float(v)
    except (OSError, ValueError):
        pass
    return out


def migrate_old_mode():
    """The first version of the rear selector used a systemd drop-in; move it to the profile."""
    old = os.path.expanduser("~/.config/systemd/user/wireplumber.service.d/camera-mode.conf")
    try:
        m = re.search(r"MIN_WIDTH=(\d+)", open(old).read())
    except OSError:
        return
    p = read_profile("rear")
    if m and "min_width" not in p and int(m.group(1)):
        p["min_width"] = [int(m.group(1))]
        write_profile("rear", p)
    os.remove(old)
    run(["systemctl", "--user", "daemon-reload"])


# ---- NFC, audio, stylus, updates ----
def _active(unit, user=False):
    rc, out = run(["systemctl"] + (["--user"] if user else []) + ["is-active", unit])
    return out.strip() or "unknown"


def nfc_info():
    return {"device": os.path.isdir("/sys/class/nfc/nfc0"), "daemon": _active("nfc-daemon"), "notifier": _active("nfc-notify", True), "events": []}


_desc_cache = {}


def _wp_desc(target):
    """Name of the default device; cached for 20 s (the lookup is slow and the name rarely changes)."""
    import time
    hit = _desc_cache.get(target)
    if hit and time.monotonic() - hit[0] < 20:
        return hit[1]
    rc, out = run(["wpctl", "inspect", target])
    m = re.search(r'node\.description = "([^"]*)"', out)
    name = m.group(1) if m else "none"
    _desc_cache[target] = (time.monotonic(), name)
    return name


def _wp_volume(target):
    rc, out = run(["wpctl", "get-volume", target])
    m = re.search(r"Volume:\s*([0-9.]+)", out)
    return (float(m.group(1)) if m else 0.0), "MUTED" in out


SPEAKER_CONF = os.path.expanduser("~/.config/pipewire/pipewire.conf.d/10-speaker-gain.conf")
MIC_CONF = os.path.expanduser("~/.config/pipewire/pipewire.conf.d/30-mic-enhance.conf")
MIC_DEFAULTS = {"gain": 0.0, "lowcut": 80.0, "bass": 0.0, "presence": 0.0, "treble": 0.0}


_node_ids = {}


def _pw_node_id(name):
    import json
    if name in _node_ids:
        return _node_ids[name]
    rc, out = run(["pw-dump"], timeout=10)
    try:
        for o in json.loads(out):
            if o.get("type", "").endswith("Node") and o.get("info", {}).get("props", {}).get("node.name") == name:
                _node_ids[name] = o["id"]
                return o["id"]
    except ValueError:
        pass
    return None


def _pw_set(name, params):
    """Change filter-chain controls of a running node, e.g. {"gainL:Mult": 1.5}."""
    nid = _pw_node_id(name)
    if nid is None:
        return False
    items = " ".join('"%s" %g' % (k, v) for k, v in params.items())
    rc, out = run(["pw-cli", "set-param", str(nid), "Props", "{ params = [ %s ] }" % items])
    if rc != 0:
        _node_ids.pop(name, None)     # the node was recreated: look the id up again next time
    return rc == 0


def speaker_boost():
    """How much louder than the plain sink the speakers are driven, as the percentage the desktop volume has to be to sound the same
    (PipeWire volumes are cubic: gain = (percent / 100) ^ 3). 100 = no boost. Read from the gain stage of the speaker chain."""
    for path in (SPEAKER_CONF,):
        try:
            text = open(path).read()
        except OSError:
            continue
        m = re.search(r'name = gainL[^\n]*"Mult"\s*=\s*([0-9.]+)', text) or re.search(r'"Mult"\s*=\s*([0-9.]+)', text)
        if m:
            try:
                return round(float(m.group(1)) ** (1 / 3) * 100)
            except ValueError:
                pass
    return 100


def set_speaker_boost(percent):
    mult = (percent / 100.0) ** 3
    try:
        s = open(SPEAKER_CONF).read()
        s = re.sub(r'("Mult"\s*=\s*)[0-9.]+', lambda m: m.group(1) + "%.3f" % mult, s)
        open(SPEAKER_CONF, "w").write(s)
    except OSError:
        pass
    return _pw_set("boosted_speakers", {"gainL:Mult": mult, "gainR:Mult": mult})


def mic_settings():
    import json
    try:
        v = json.load(open(os.path.expanduser("~/.config/surface-suite/audio.json"))).get("mic", {})
    except (OSError, ValueError):
        v = {}
    out = dict(MIC_DEFAULTS)
    out.update({k: v[k] for k in MIC_DEFAULTS if k in v})
    out["available"] = os.path.exists(MIC_CONF)
    out["running"] = _pw_node_id("mic_enhanced") is not None
    return out


def _mic_controls(v):
    return {"hp:Freq": v["lowcut"], "bass:Gain": v["bass"], "pres:Gain": v["presence"], "treb:Gain": v["treble"],
            "gain:Mult": 10 ** (v["gain"] / 20.0)}


def set_mic_setting(key, value):
    import json
    v = {k: mic_settings()[k] for k in MIC_DEFAULTS}
    v[key] = float(value)
    d = _audio_load()
    d["mic"] = v
    _audio_save(d)
    _write_mic_conf(v)
    return _pw_set("mic_enhanced", _mic_controls(v))


def _write_mic_conf(v):
    """Keep the saved file in step with the live values: they are what the filter starts with after a restart."""
    try:
        s = open(MIC_CONF).read()
    except OSError:
        return
    for node, key, val in (("hp", "Freq", v["lowcut"]), ("bass", "Gain", v["bass"]), ("pres", "Gain", v["presence"]), ("treb", "Gain", v["treble"])):
        s = re.sub(r'(name = %s\s+label = \w+\s+control = \{[^}]*?"%s"\s*=\s*)[-0-9.]+' % (node, key), lambda m: m.group(1) + "%g" % val, s)
    s = re.sub(r'(name = gain\s+label = linear\s+control = \{\s*"Mult"\s*=\s*)[-0-9.]+', lambda m: m.group(1) + "%.4f" % (10 ** (v["gain"] / 20.0)), s)
    open(MIC_CONF, "w").write(s)


def enable_mic_enhancer():
    """Install the filter file and restart the sound server so that it loads it (a module loaded from outside would vanish with its loader).
    Audio and the cameras are interrupted for a second or two."""
    src = f"{GUIDE}/tuning/pipewire/30-mic-enhance.conf"
    os.makedirs(os.path.dirname(MIC_CONF), exist_ok=True)
    import shutil
    shutil.copyfile(src, MIC_CONF)
    _node_ids.clear()
    rc, out = run(["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service", "wireplumber.service"], timeout=40)
    if rc == 0:
        _make_default_source("mic_enhanced")
    return rc == 0, out


def _make_default_source(name):
    """WirePlumber remembers the default source, so the new virtual one has to be made default explicitly."""
    import time
    for _ in range(15):
        nid = _pw_node_id(name)
        if nid is not None:
            run(["wpctl", "set-default", str(nid)])
            return True
        _node_ids.pop(name, None)
        time.sleep(0.5)
    return False


def disable_mic_enhancer():
    try:
        os.remove(MIC_CONF)
    except OSError:
        pass
    _node_ids.clear()
    rc, out = run(["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service", "wireplumber.service"], timeout=40)
    if rc == 0:
        _make_default_source("mic_filtered")
    return rc == 0, out


def audio_info():
    out = {}
    for kind, target in (("output", "@DEFAULT_AUDIO_SINK@"), ("input", "@DEFAULT_AUDIO_SOURCE@")):
        vol, muted = _wp_volume(target)
        out[kind] = {"name": _wp_desc(target), "volume": vol, "muted": muted}
    out["speakerBoost"] = speaker_boost()
    out["mic"] = mic_settings()
    return out


SOUNDS = "/usr/share/sounds/freedesktop/stereo/"
# (file, channel map): the voices of the desktop sound theme announce the channel ("Front left", "Front right"), the chime plays on both
TEST_SOUNDS = {"left": ("audio-channel-front-left.oga", "FL"), "right": ("audio-channel-front-right.oga", "FR"), "both": ("stereo", None)}


def sweep_file():
    """A slow logarithmic sweep from 40 Hz to 16 kHz (8 s, faded in and out, a little below full level), made once into the runtime folder."""
    import math, struct, wave
    d = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "surface-control")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "sweep-40-16k.wav")
    if os.path.exists(path):
        return path
    rate, secs = 44100, 8.0
    w = wave.open(path, "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(rate)
    phase = 0.0
    buf = bytearray()
    k = math.log(16000 / 40.0)
    for n in range(int(rate * secs)):
        t = n / rate
        phase += 2 * math.pi * 40.0 * math.exp(k * t / secs) / rate
        v = 0.3 * min(1.0, t * 8, (secs - t) * 8) * math.sin(phase)
        s = int(v * 32767)
        buf += struct.pack("<hh", s, s)
    w.writeframes(bytes(buf))
    w.close()
    return path


def stereo_file():
    """A short stereo piece made once into the runtime folder: a soft pad with slightly detuned voices (wide), a centred bass, and a bell melody whose echoes ping-pong between the speakers."""
    import math, struct, wave
    d = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "surface-control")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "stereo-demo-3.wav")
    if os.path.exists(path):
        return path
    rate, secs = 44100, 3.4
    n = int(rate * secs)
    L = [0.0] * n
    R = [0.0] * n
    tau = 2 * math.pi

    def voice(buf, freq, start, dur, amp, kind):
        a0 = int(start * rate)
        for i in range(min(int(dur * rate), n - a0)):
            t = i / rate
            if kind == "pad":
                env = min(1.0, t / 0.6) * min(1.0, (dur - t) / 0.8)
                v = math.sin(tau * freq * t) + 0.4 * math.sin(tau * 2 * freq * t)
            elif kind == "bass":
                env = min(1.0, t * 60) * math.exp(-1.6 * t / dur)
                v = math.sin(tau * freq * t)
            else:                                                  # bell
                env = min(1.0, t * 300) * math.exp(-4.0 * t / dur)
                v = math.sin(tau * freq * t) + 0.5 * math.sin(tau * 2.01 * freq * t) + 0.2 * math.sin(tau * 3.99 * freq * t)
            buf[a0 + i] += amp * env * v

    chords = [([261.6, 329.6, 392.0], 65.4), ([220.0, 261.6, 329.6], 55.0), ([174.6, 220.0, 261.6], 43.65), ([196.0, 246.9, 293.7], 49.0)]
    for k, (notes, bass) in enumerate(chords[:1]):
        t0 = k * 2.25
        for j, f in enumerate(notes):                              # detuned copies: one a little flat on the left, a little sharp on the right
            voice(L, f * 0.997, t0, 3.2, 0.07, "pad")
            voice(R, f * 1.003, t0, 3.2, 0.07, "pad")
        voice(L, bass, t0, 2.2, 0.12, "bass")
        voice(R, bass, t0, 2.2, 0.12, "bass")
    tune = [(0, 784.0), (0.5, 659.3), (1.0, 523.3), (1.5, 659.3)]
    dry = [0.0] * n
    for t0, f in tune:
        voice(dry, f, t0 + 0.1, 0.9, 0.22, "bell")
    delay = int(0.3 * rate)
    for i in range(n):                                              # dry on the left, then echoes right, left, right, each quieter
        L[i] += dry[i]
        for k in range(1, 5):
            if i >= k * delay:
                (R if k % 2 else L)[i] += dry[i - k * delay] * 0.55 ** k
    w = wave.open(path, "wb")
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(rate)
    peak = max(max(map(abs, L)), max(map(abs, R)), 1e-9)
    g = 28000 / max(peak, 1.0)
    w.writeframes(b"".join(struct.pack("<hh", int(L[i] * g), int(R[i] * g)) for i in range(n)))
    w.close()
    return path


def sound_for(kind):
    """(path, channel map or None) of the short sound for the speaker test."""
    if kind == "sweep":
        return sweep_file(), None
    if kind == "both":
        return stereo_file(), None
    name, cmap = TEST_SOUNDS[kind]
    path = SOUNDS + name
    if not os.path.exists(path):
        raise OSError("the desktop sound " + name + " is not installed")
    return path, cmap


_osd_lock = threading.Lock()
_osd_timer = None


def _osd(enabled):
    v = "true" if enabled else "false"
    # the volume applet has its own switches (plasmaparc); plasmarc [OSD] is the general one
    for f, g, k in (("plasmaparc", "General", "VolumeOsd"), ("plasmaparc", "General", "MicrophoneSensitivityOsd"), ("plasmarc", "OSD", "Enabled")):
        run(["kwriteconfig6", "--file", f, "--group", g, "--key", k, v], timeout=5)


_osd_held = False


def osd_hold(on):
    """Keep the volume pop-up off for as long as the Audio page is open (the first change after a restore was still showing it)."""
    global _osd_held
    _osd_held = bool(on)
    if on:
        with _osd_lock:
            if _osd_timer:
                _osd_timer.cancel()
            _osd(False)
    else:
        osd_restore()


def osd_restore():
    """Turn the Plasma volume pop-up back on (also called when the app starts and exits, in case it was left off)."""
    global _osd_timer
    with _osd_lock:
        if _osd_timer:
            _osd_timer.cancel()
            _osd_timer = None
        if not _osd_held:
            _osd(True)


def set_volume(kind, value):
    """Set the volume without the on-screen pop-up of Plasma: the pop-up is switched off while the slider moves and back on 1.5 s after the last change."""
    global _osd_timer
    with _osd_lock:
        if _osd_timer:
            _osd_timer.cancel()
        elif not _osd_held:
            _osd(False)
            time.sleep(0.3)                    # let Plasma read the new setting before the first change
        _osd_timer = threading.Timer(2.5, osd_restore)
        _osd_timer.daemon = True
        _osd_timer.start()
    run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@" if kind == "output" else "@DEFAULT_AUDIO_SOURCE@", "%.2f" % value])


def toggle_mute(kind):
    run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@" if kind == "output" else "@DEFAULT_AUDIO_SOURCE@", "toggle"])


def stylus_info():
    try:
        devs = open("/proc/bus/input/devices").read()
    except OSError:
        devs = ""
    digitizer = [l.split('"')[1] for l in devs.splitlines() if l.startswith("N:") and "ELAN" in l and "UNKNOWN" not in l]
    fake = [os.path.basename(p) for p in glob.glob("/sys/class/power_supply/*")
            if os.path.basename(p) not in ("ACAD",) and not os.path.basename(p).startswith("BAT")]
    return {"digitizer": digitizer, "fakeBattery": fake, "bluetooth": bluetooth_batteries(), "filterInstalled": stylus_filter_installed()}


def bluetooth_batteries():
    """Paired Bluetooth devices with a battery service (the Surface Pen has one): connection state and level, straight from BlueZ."""
    out = []
    rc, devs = run(["bluetoothctl", "devices"], timeout=6)
    for line in devs.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3 or parts[0] != "Device":
            continue
        rc, info = run(["bluetoothctl", "info", parts[1]], timeout=6)
        if "Battery Service" not in info and "Battery Percentage" not in info:
            continue
        m = re.search(r"Battery Percentage:\s*0x[0-9a-fA-F]+\s*\((\d+)\)", info)
        out.append({"name": parts[2], "connected": "Connected: yes" in info, "battery": int(m.group(1)) if m else -1})
    return out


def update_info():
    k = os.uname().release
    kernels = sorted(os.path.basename(p)[6:] for p in glob.glob(f"{KMODS}/built-*"))
    rc, v = run(["rpm", "-q", "--qf", "%{VERSION}", "libcamera"])
    patches = sorted(os.path.basename(p) for p in glob.glob(f"{GUIDE}/patches/libcamera-{v}-*.patch")) if rc == 0 else []
    return {"kernel": k, "built": kernels, "builtNow": k in kernels, "libcamera": v if rc == 0 else "not installed",
            "patches": [p.replace(f"libcamera-{v}-", "").replace(".patch", "") for p in patches]}


def restart_cameras():
    return run(["systemctl", "--user", "restart", "wireplumber"], timeout=30)


def rebuild():
    """Opens the rebuild script in a terminal: it needs the sudo password and shows its progress."""
    try:
        subprocess.Popen(["konsole", "--hold", "-e", f"{GUIDE}/scripts/02-build-and-install.sh"])
        return True
    except OSError:
        return False


def nfc_describe(records):
    """One readable line per NDEF record of a tag event."""
    out = []
    for r in records or []:
        kind, value = r.get("kind"), r.get("value")
        if kind == "uri":
            out.append("Link: " + str(value))
        elif kind == "text":
            out.append("Text: " + str(value))
        elif kind == "smartposter":
            out.extend(nfc_describe(value))
        elif kind == "mime":
            out.append("Data: " + str(value))
        else:
            out.append(str(value))
    if records is None:
        out.append("Card or device, no readable data")
    elif not out:
        out.append("Empty or non-NDEF tag")
    return out


# ---- keyboard and trackpad test ----
def keyboard_layout():
    """(layout, variant, model) the desktop uses: the Plasma setting if there is one, else the system one (localectl)."""
    rc, kx = run(["kreadconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "LayoutList"])
    rc2, kv = run(["kreadconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "VariantList"])
    if rc == 0 and kx.strip():
        return kx.split(",")[0].strip(), (kv.split(",")[0].strip() if rc2 == 0 else ""), "pc105"
    rc, out = run(["localectl", "status"])
    get = lambda k: (re.search(k + r":\s*(\S+)", out) or [None, ""])[1] if re.search(k + r":\s*(\S+)", out) else ""
    return get("X11 Layout") or "us", get("X11 Variant"), get("X11 Model") or "pc105"


def key_labels(codes):
    """What each physical key (evdev code) types in the current layout, asked from libxkbcommon: {code: label}."""
    import ctypes
    import ctypes.util
    try:
        lib = ctypes.CDLL(ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0")

        class Names(ctypes.Structure):
            _fields_ = [(n, ctypes.c_char_p) for n in ("rules", "model", "layout", "variant", "options")]

        lib.xkb_context_new.restype = ctypes.c_void_p
        lib.xkb_context_new.argtypes = [ctypes.c_int]
        lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(Names), ctypes.c_int]
        lib.xkb_state_new.restype = ctypes.c_void_p
        lib.xkb_state_new.argtypes = [ctypes.c_void_p]
        lib.xkb_state_key_get_utf8.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        layout, variant, model = keyboard_layout()
        names = Names(b"evdev", model.encode(), layout.encode(), variant.encode(), b"")
        ctx = lib.xkb_context_new(0)
        km = lib.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
        st = lib.xkb_state_new(km)
        out = {}
        for c in codes:
            buf = ctypes.create_string_buffer(16)
            n = lib.xkb_state_key_get_utf8(st, c + 8, buf, 16)
            ch = buf.value.decode("utf-8", "replace") if n > 0 else ""
            out[c] = ch.upper() if ch.isalpha() and len(ch.upper()) == len(ch) else ch
        return out
    except (OSError, AttributeError):
        return {}


_unblocker = None


def block_shortcuts(block):
    """While the key test runs, Plasma's global shortcuts (Meta, Alt+Tab, media keys...) must not fire: KGlobalAccel can block them.
    A tiny watcher unblocks them again if this program dies while they are blocked."""
    global _unblocker
    call = ["busctl", "--user", "call", "org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel", "blockGlobalShortcuts", "b"]
    run(call + ["true" if block else "false"])
    if block and _unblocker is None:
        script = f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 1; done; " + " ".join(call) + " false"
        _unblocker = subprocess.Popen(["sh", "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif not block and _unblocker is not None:
        _unblocker.kill()
        _unblocker = None


# ---- camera presets: the whole profile of one camera under a name, ~/.config/surface-suite/presets/<front|rear>/<slug>.json ----
PRESET_DIR = os.path.join(os.path.dirname(PROFILE_DIR), "presets")


def _slug(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._")
    return s[:60]


def _preset_path(cam, pid):
    return os.path.join(PRESET_DIR, cam, pid + ".json")


def list_presets(cam):
    import json
    out = []
    for p in sorted(glob.glob(os.path.join(PRESET_DIR, cam, "*.json"))):
        try:
            d = json.load(open(p))
            out.append({"id": os.path.basename(p)[:-5], "name": d.get("name", os.path.basename(p)[:-5])})
        except (OSError, ValueError):
            pass
    out.sort(key=lambda x: x["name"].lower())
    cur = matching_preset(cam)
    for o in out:
        o["current"] = o["id"] == cur
    return out


def _preset_profile(cam, pid):
    import json
    try:
        return {k: [float(x) for x in v] for k, v in json.load(open(_preset_path(cam, pid)))["profile"].items()}
    except (OSError, ValueError, KeyError):
        return None


def matching_preset(cam):
    """Id of the preset whose settings equal the current ones (the size counts too), or ''."""
    cur = read_profile(cam)
    matches = [os.path.basename(p)[:-5] for p in sorted(glob.glob(os.path.join(PRESET_DIR, cam, "*.json")))
               if _preset_profile(cam, os.path.basename(p)[:-5]) == cur]
    last = ui_setting("lastPreset_" + cam, "")
    return last if last in matches else (matches[0] if matches else "")


def save_preset(cam, name, overwrite=False):
    """Returns 'ok', 'invalid' (empty or unusable name) or 'exists'."""
    import json
    name = name.strip()
    pid = _slug(name)
    if not pid:
        return "invalid"
    if os.path.exists(_preset_path(cam, pid)) and not overwrite:
        return "exists"
    os.makedirs(os.path.join(PRESET_DIR, cam), exist_ok=True)
    json.dump({"name": name, "profile": read_profile(cam)}, open(_preset_path(cam, pid), "w"), indent=1)
    set_ui_setting("lastPreset_" + cam, pid)
    return "ok"


def apply_preset(cam, pid):
    """Makes the preset the current profile. Returns True when the picture size changed (the camera service must restart)."""
    prof = _preset_profile(cam, pid)
    if prof is None:
        return False
    old = read_profile(cam).get("min_width")
    write_profile(cam, prof)
    set_ui_setting("lastPreset_" + cam, pid)
    changed = prof.get("min_width") != old
    if changed:
        run(["systemctl", "--user", "restart", "wireplumber"], timeout=30)
    return changed


def rename_preset(cam, pid, new_name):
    import json
    new_name = new_name.strip()
    nid = _slug(new_name)
    if not nid:
        return "invalid"
    if nid != pid and os.path.exists(_preset_path(cam, nid)):
        return "exists"
    try:
        d = json.load(open(_preset_path(cam, pid)))
    except (OSError, ValueError):
        return "invalid"
    d["name"] = new_name
    json.dump(d, open(_preset_path(cam, nid), "w"), indent=1)
    if nid != pid:
        os.remove(_preset_path(cam, pid))
    return "ok"


def delete_preset(cam, pid):
    try:
        os.remove(_preset_path(cam, pid))
    except OSError:
        pass


def duplicate_preset(cam, pid, new_name):
    import json
    nid = _slug(new_name)
    if not nid:
        return "invalid"
    if os.path.exists(_preset_path(cam, nid)):
        return "exists"
    try:
        d = json.load(open(_preset_path(cam, pid)))
    except (OSError, ValueError):
        return "invalid"
    d["name"] = new_name.strip()
    json.dump(d, open(_preset_path(cam, nid), "w"), indent=1)
    return "ok"


# ---- small settings of the panel itself (hints on or off...) ----
UI_FILE = os.path.expanduser("~/.config/surface-suite/control.json")


def ui_setting(key, default):
    import json
    try:
        return json.load(open(UI_FILE)).get(key, default)
    except (OSError, ValueError):
        return default


def set_ui_setting(key, value):
    import json
    try:
        d = json.load(open(UI_FILE))
    except (OSError, ValueError):
        d = {}
    d[key] = value
    os.makedirs(os.path.dirname(UI_FILE), exist_ok=True)
    json.dump(d, open(UI_FILE, "w"))


# ---- motion: accelerometer + gyroscope -> orientation of the tablet for the 3D model ----
_motion = {"acc": None, "gyr": None, "yaw": 0.0, "t": None}


def reset_yaw():
    _motion["yaw"] = 0.0


def _motion_step(inv):
    """One read of accel (every time) and gyro (every third time), then the orientation. Reading a sysfs raw value costs about 12 ms,
    so this runs in a background thread and motion() only returns the latest result."""
    import math
    import time
    a, g = _motion["acc"], _motion["gyr"]
    sa = _motion.setdefault("sa", _num(a + "/in_accel_scale", 1))
    acc = [_num(f"{a}/in_accel_{ax}_raw") for ax in "xyz"]
    if None in acc:
        return None
    acc = [v * sa for v in acc]
    out = {"accel": [round(v, 2) for v in acc]}
    _motion["n"] = _motion.get("n", 0) + 1
    if g and _motion["n"] % 3 == 1:
        sg = _motion.setdefault("sg", _num(g + "/in_anglvel_scale", 1))
        raw = [_num(f"{g}/in_anglvel_{ax}_raw") for ax in "xyz"]
        if None not in raw:
            _motion["gyr_val"] = [v * sg * k for v, k in zip(raw, inv)]      # rad/s
    gyr = _motion.get("gyr_val", [0.0, 0.0, 0.0])
    out["gyro"] = [round(math.degrees(v), 1) for v in gyr]
    # these sensors report the direction gravity pulls (Windows convention): "up" is the opposite
    up = [-v * k for v, k in zip(acc, inv)]
    n = math.sqrt(sum(v * v for v in up)) or 1.0
    ux, uy, uz = (v / n for v in up)
    if uy < -0.9999:
        qw, qx, qy, qz = 0.0, 0.0, 0.0, 1.0
    else:
        qw, qx, qy, qz = 1 + uy, -uz, 0.0, ux
        m = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz) or 1.0
        qw, qx, qy, qz = qw / m, qx / m, qy / m, qz / m
    now = time.monotonic()
    if _motion["t"] is not None:
        dt = min(now - _motion["t"], 0.5)
        _motion["yaw"] += (gyr[0] * ux + gyr[1] * uy + gyr[2] * uz) * dt
    _motion["t"] = now
    h = _motion["yaw"] / 2
    yw, yy = math.cos(h), math.sin(h)
    out["q"] = [yw * qw - yy * qy, yw * qx + yy * qz, yw * qy + yy * qw, yw * qz - yy * qx]
    return out


def motion(inv=(1, 1, 1)):
    """Latest orientation of the tablet for the 3D model: accel (m/s^2), gyro (deg/s) and the quaternion (w, x, y, z) that turns the
    model so that the measured gravity points up; the turn around the vertical comes from the gyroscope (it drifts slowly: reset_yaw).
    The first call starts a reader thread that keeps going while calls keep coming."""
    import threading
    import time
    if _motion["acc"] is None:
        _motion["acc"] = _iio("accel_3d")
        _motion["gyr"] = _iio("gyro_3d")
    if not _motion["acc"]:
        return {}
    _motion["inv"] = inv
    _motion["seen"] = time.monotonic()
    if not _motion.get("thread") or not _motion["thread"].is_alive():
        def loop():
            while time.monotonic() - _motion["seen"] < 2.0:      # stops by itself when nobody asks any more
                r = _motion_step(_motion["inv"])
                if r:
                    _motion["last"] = r
                else:
                    time.sleep(0.1)
            _motion["t"] = None
        _motion["thread"] = threading.Thread(target=loop, daemon=True)
        _motion["thread"].start()
    return _motion.get("last", {})


def set_sensor_rate(hz):
    """Faster sensor updates while the 3D view is open (the hub default is 10 Hz). Needs write access to sysfs, see tools/61-surface-sensors.rules; ignored without."""
    for name, attr in (("accel_3d", "in_accel_sampling_frequency"), ("gyro_3d", "in_anglvel_sampling_frequency")):
        d = _iio(name)
        if d:
            try:
                open(f"{d}/{attr}", "w").write(str(hz))
            except OSError:
                pass


# ---- stylus: HID-BPF filter that hides the fake battery ----
STYLUS_RULE = "/etc/udev/rules.d/99-hid-bpf-stylus.rules"


def stylus_filter_installed():
    return os.path.exists(STYLUS_RULE)


def stylus_filter_toggle(on):
    """Runs the helper as root through polkit (the desktop shows its password dialog); falls back to sudo without a password.
    Returns (ok, message)."""
    script = f"{GUIDE}/tools/stylus-filter.sh"
    out = ""
    for cmd in (["pkexec", script, "on" if on else "off"], ["sudo", "-n", script, "on" if on else "off"]):
        rc, out = run(cmd, timeout=120)
        if rc == 0:
            return True, out
        if cmd[0] == "pkexec" and rc == 126:        # the user closed the password dialog
            return False, "Cancelled"
    return False, out or "Could not get permission"


# ---- audio presets: output (speaker boost) and input (microphone enhancer values) ----
def _audio_file():
    return os.path.expanduser("~/.config/surface-suite/audio.json")


def _audio_load():
    import json
    try:
        return json.load(open(_audio_file()))
    except (OSError, ValueError):
        return {}


def _audio_save(d):
    import json
    os.makedirs(os.path.dirname(_audio_file()), exist_ok=True)
    json.dump(d, open(_audio_file(), "w"), indent=1)


def audio_presets(kind):
    return sorted(_audio_load().get("presets", {}).get(kind, {}).keys(), key=str.lower)


def save_audio_preset(kind, name):
    name = name.strip()
    if not name:
        return "invalid"
    d = _audio_load()
    vals = {"boost": speaker_boost()} if kind == "output" else {k: mic_settings()[k] for k in MIC_DEFAULTS}
    d.setdefault("presets", {}).setdefault(kind, {})[name] = vals
    _audio_save(d)
    return "ok"


def apply_audio_preset(kind, name):
    vals = _audio_load().get("presets", {}).get(kind, {}).get(name)
    if not vals:
        return False
    if kind == "output":
        set_speaker_boost(vals.get("boost", 120))
    else:
        d = _audio_load()
        d["mic"] = {k: float(vals.get(k, MIC_DEFAULTS[k])) for k in MIC_DEFAULTS}
        _audio_save(d)
        _write_mic_conf(d["mic"])
        _pw_set("mic_enhanced", _mic_controls(d["mic"]))
    return True


def delete_audio_preset(kind, name):
    d = _audio_load()
    d.get("presets", {}).get(kind, {}).pop(name, None)
    _audio_save(d)


# ---- microphone presets: the built-in looks and your own in one list ----
MIC_BUILTIN = {
    "Flat": dict(MIC_DEFAULTS),
    "Clear voice": {"gain": 3.0, "lowcut": 110.0, "bass": -2.0, "presence": 3.0, "treble": -1.0},
    "Warm": {"gain": 2.0, "lowcut": 70.0, "bass": 3.0, "presence": 1.0, "treble": -3.0},
}


def hidden_presets(kind):
    """Built-in presets the user deleted. The installer brings them back (restore_defaults); presets made by the user are never touched."""
    return set(_audio_load().get("hidden", {}).get(kind, []))


def hide_builtin(kind, name):
    d = _audio_load()
    h = d.setdefault("hidden", {}).setdefault(kind, [])
    if name not in h:
        h.append(name)
    _audio_save(d)


def restore_defaults():
    """Puts the built-in presets back (called by the install script after the patches are applied again). Custom presets stay."""
    d = _audio_load()
    d.pop("hidden", None)
    _audio_save(d)


def mic_presets():
    custom = _audio_load().get("presets", {}).get("input", {})
    hidden = hidden_presets("input")
    return [{"name": n, "builtin": True} for n in MIC_BUILTIN if n not in hidden] + [{"name": n, "builtin": False} for n in sorted(custom, key=str.lower)]


def apply_mic_preset(name):
    vals = (MIC_BUILTIN.get(name) if name not in hidden_presets("input") else None) or _audio_load().get("presets", {}).get("input", {}).get(name)
    if not vals:
        return False
    d = _audio_load()
    d["mic"] = {k: float(vals.get(k, MIC_DEFAULTS[k])) for k in MIC_DEFAULTS}
    _audio_save(d)
    _write_mic_conf(d["mic"])
    _pw_set("mic_enhanced", _mic_controls(d["mic"]))
    return True


def save_mic_preset(name):
    if name.strip() in MIC_BUILTIN:
        return "invalid"
    return save_audio_preset("input", name)


def pw_params(node_name):
    """The controls a running filter chain node reports now, as {"node:Control": value}."""
    import json
    nid = _pw_node_id(node_name)
    if nid is None:
        return {}
    rc, out = run(["pw-dump", str(nid)], timeout=10)
    try:
        for p in json.loads(out)[0]["info"]["params"]["Props"]:
            if "params" in p and any(str(x).endswith(":Mult") or ":" in str(x) for x in p["params"][::2]):
                return dict(zip(p["params"][::2], p["params"][1::2]))
    except (ValueError, KeyError, IndexError):
        pass
    return {}


def verify_mic():
    """Compares what the microphone filter is doing with what is saved. Returns a list of (what, expected, actual)."""
    v = mic_settings()
    if not v.get("available"):
        return None
    got = pw_params("mic_enhanced")
    bad = []
    if not got:
        return [("the filter is not running", "-", "-")]
    for k, exp in _mic_controls({x: v[x] for x in MIC_DEFAULTS}).items():
        act = got.get(k)
        if act is None or abs(act - exp) > 1e-3 * max(1.0, abs(exp)):
            bad.append((k, round(exp, 4), None if act is None else round(act, 4)))
    return bad


# ---- hold-to-repeat of the device volume buttons (parameter of the patched intel_hid module) ----
def volume_hold_state():
    """True / False, or None when the patched module (with the parameter) is not loaded."""
    try:
        return open("/sys/module/intel_hid/parameters/volume_hold").read().strip() == "Y"
    except OSError:
        return None


def set_volume_hold(on):
    script = f"{GUIDE}/tools/volume-hold.sh"
    out = ""
    for cmd in (["pkexec", script, "on" if on else "off"], ["sudo", "-n", script, "on" if on else "off"]):
        rc, out = run(cmd, timeout=60)
        if rc == 0:
            return True, out
        if cmd[0] == "pkexec" and rc == 126:
            return False, "Cancelled"
    return False, out or "Could not get permission"
