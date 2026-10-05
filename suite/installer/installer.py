#!/usr/bin/env python3
"""Surface Go installer: a small wizard that runs scripts/01..03 with a progress view, a graphical password prompt and an optional console pane.

The state is never stored: every time the window opens it looks at the system (MOK key, build marker for the running kernel) and goes to the right page, so it
also works after the restart that the Secure Boot step needs. Environment variables for testing: SURFACE_INSTALLER_FAKE=1 runs fake steps."""
import os
import re
import shlex
import shutil
import subprocess
import sys

from PySide6.QtCore import QObject, Property, QProcess, QProcessEnvironment, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.abspath(os.path.join(HERE, "..", ".."))
FAKE = bool(os.environ.get("SURFACE_INSTALLER_FAKE"))
MOK_PASSWORD = "surface"
AUTOSTART = os.path.expanduser("~/.config/autostart/surface-installer.desktop")
KMODS = "/var/lib/local-kmods"
LOGFILE = os.path.expanduser("~/.local/state/surface-installer/install.log")      # everything the steps print, to read with tail -f or to attach to a bug report


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def checks():
    """The things worth knowing before starting: (label, ok, detail)."""
    out = []
    try:
        product = open("/sys/class/dmi/id/product_name").read().strip()
    except OSError:
        product = "unknown"
    out.append(("Device", "Surface Go" in product, product + ("" if "Surface Go" in product else " - only the Surface Go 1st gen (1824) has been tested")))
    rc, o = run(["rpm-ostree", "status"])
    out.append(("Fedora Kinoite (or another Fedora Atomic desktop)", rc == 0, "rpm-ostree found" if rc == 0 else "rpm-ostree not found"))
    rc, o = run(["mokutil", "--sb-state"])
    out.append(("Secure Boot", True, o.strip().splitlines()[0] if o.strip() else "unknown"))
    rc, o = run(["curl", "-fsI", "--max-time", "6", "https://git.kernel.org"], timeout=10)
    out.append(("Internet connection", rc == 0, "reachable" if rc == 0 else "cannot reach git.kernel.org: the drivers are downloaded from there"))
    free = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
    out.append(("Free disk space", free > 6, "%.0f GB free (about 6 GB needed for the build)" % free))
    return out


def stage():
    """Where the installation is, from the system itself."""
    if FAKE:
        return os.environ.get("SURFACE_INSTALLER_STAGE", "welcome")
    der = os.path.join(os.environ.get("MOKDIR", os.path.expanduser("~/mok")), "MOK.der")
    rc, test = run(["mokutil", "--test-key", der]) if os.path.exists(der) else (1, "")
    if "is already enrolled" in test:
        if os.path.exists("%s/built-%s" % (KMODS, os.uname().release)):
            return "verify"
        return "install"
    rc, new = run(["mokutil", "--list-new"])
    if os.path.exists(der) and "Surface Go local module signing" in new:
        return "restart-mok"
    return "welcome"


class Bridge(QObject):
    stageChanged = Signal()
    busyChanged = Signal()
    logLine = Signal(str)
    stepChanged = Signal()
    verifyChanged = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._stage = stage()
        self._busy = False
        self._step = ""
        self._progress = 0.0
        self._total = 1
        self._seen = 0
        self._proc = None
        self._results = []
        self._buf = ""
        self._pw = ""

    # ---------------------------------------------------------------- properties
    def _get_stage(self):
        return self._stage

    def _get_busy(self):
        return self._busy

    def _get_step(self):
        return self._step

    def _get_progress(self):
        return self._progress

    def _get_results(self):
        return self._results

    stageName = Property(str, _get_stage, notify=stageChanged)
    busy = Property(bool, _get_busy, notify=busyChanged)
    step = Property(str, _get_step, notify=stepChanged)
    progress = Property(float, _get_progress, notify=stepChanged)
    results = Property("QVariantList", _get_results, notify=verifyChanged)

    def _set_stage(self, s):
        self._stage = s
        self.stageChanged.emit()

    # ---------------------------------------------------------------- slots
    @Slot(result="QVariantList")
    def systemChecks(self):
        if FAKE:
            return [{"label": "Device", "ok": True, "detail": "Surface Go (fake)"}]
        return [{"label": l, "ok": ok, "detail": d} for l, ok, d in checks()]

    @Slot(str, result=bool)
    def checkPassword(self, pw):
        if FAKE:
            return pw == "ok"
        r = subprocess.run(["sudo", "-S", "-k", "-p", "", "-v"], input=pw + "\n", capture_output=True, text=True)
        if r.returncode == 0:
            self._pw = pw
            return True
        return False

    @Slot(str, result=str)
    def mokPassword(self, _):
        return MOK_PASSWORD

    @Slot()
    def startPrepare(self):
        self._run("01-upgrade-and-mok.sh", "restart-mok", 3, {"MOK_PASSWORD": MOK_PASSWORD})
        self._write_autostart()

    @Slot(bool)
    def startInstall(self, stylus):
        self._pen = bool(stylus)
        self._run("02-build-and-install.sh", "restart-after", 12, {}, then=self._maybe_stylus)

    def _maybe_stylus(self):
        if getattr(self, "_pen", False):
            self._run("04-stylus-battery.sh", "restart-after", 4, {})

    @Slot()
    def startVerify(self):
        self._results = []
        self.verifyChanged.emit()
        self._run("03-verify.sh", "done", 1, {}, parse=True)

    @Slot()
    def reboot(self):
        if FAKE:
            self.logLine.emit("(fake) would restart now\n")
            return
        subprocess.Popen(["systemctl", "reboot"])

    @Slot()
    def skipToVerify(self):
        self._set_stage("verify")

    @Slot()
    def finish(self):
        try:
            os.remove(AUTOSTART)
        except OSError:
            pass
        QGuiApplication.quit()

    @Slot()
    def openControl(self):
        exe = os.path.expanduser("~/.local/bin/surface-control")
        if os.path.exists(exe):
            subprocess.Popen([exe], start_new_session=True)

    # ---------------------------------------------------------------- running a step
    def _write_autostart(self):
        if FAKE:
            return                                  # tests must never leave an autostart entry behind
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Surface Go installer\nExec=python3 %s --resume\nIcon=system-software-install\nX-KDE-autostart-after=panel\n"
                    % shlex.quote(os.path.join(HERE, "installer.py")))

    def _run(self, script, next_stage, total, extra_env, then=None, parse=False):
        if self._busy:
            return
        self._busy, self._seen, self._total, self._progress, self._buf = True, 0, max(1, total), 0.0, ""
        self._next, self._then, self._parse = next_stage, then, parse
        self._step = "Starting..."
        self.busyChanged.emit()
        self.stepChanged.emit()
        p = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        for k, v in extra_env.items():
            env.insert(k, v)
        # no terminal for sudo: it asks the helper, which prints the password the window already collected
        env.insert("SUDO_ASKPASS", os.path.join(HERE, "askpass.sh"))
        env.insert("PATH", os.path.join(HERE, "bin") + ":" + env.value("PATH"))      # bin/sudo = sudo -A, so the scripts need no change
        env.insert("SURFACE_INSTALLER_PW", self._pw)
        p.setProcessEnvironment(env)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.finished.connect(self._finished)
        self._proc = p
        if FAKE:
            p.start("bash", ["-c", "for i in 1 2 3; do echo \"== fake step $i\"; sleep 0.3; echo detail $i; done; "
                             + ("echo '  [ok]   fake check'; echo '  [FAIL] fake failing check';" if script.startswith("03") else "")
                             + os.environ.get("SURFACE_INSTALLER_FAKE_CMD", "true")])
        else:
            p.start("setsid", ["-w", "bash", os.path.join(GUIDE, "scripts", script)])
        self.logLine.emit("$ %s\n" % script)
        self._log("\n$ %s\n" % script)

    def _log(self, text):
        if FAKE:
            return
        try:
            os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)
            with open(LOGFILE, "a") as f:
                f.write(text)
        except OSError:
            pass

    def _read(self):
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._log(data)
        self.logLine.emit(data)
        self._buf += data
        *lines, self._buf = self._buf.split("\n")
        for l in lines:
            self._line(l)

    def _line(self, l):
        if l.startswith("== "):
            self._seen += 1
            self._step = l[3:].strip()
            self._progress = min(0.97, self._seen / (self._total + 1))
            self.stepChanged.emit()
        elif self._parse:
            m = re.match(r"\s*\[(ok|FAIL|skip)\]\s+(.*)", l)
            if m:
                self._results.append({"state": m.group(1), "text": m.group(2)})
                self.verifyChanged.emit()
            elif l and not l.startswith(" ") and not l.startswith("Try ") and ":" not in l[:3]:
                self._results.append({"state": "head", "text": l.strip()})
                self.verifyChanged.emit()

    def _finished(self, code, _status):
        if self._buf:
            self._line(self._buf)
        self._busy = False
        self._progress = 1.0 if code == 0 else self._progress
        self.busyChanged.emit()
        self.stepChanged.emit()
        if code != 0:
            self._log("\n[installer] step failed with code %d\n" % code)
            self.failed.emit("The step stopped with an error (code %d). Open the details below to see why; fix it and press Try again." % code)
            return
        if self._then:
            t, self._then = self._then, None
            t()
            if self._busy:
                return
        self._set_stage(self._next)


def main():
    if "--resume" in sys.argv and stage() == "welcome":      # started at login but nothing to continue: remove the entry and stay away
        try:
            os.remove(AUTOSTART)
        except OSError:
            pass
        return
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Surface Go installer")
    app.setDesktopFileName("surface-installer")
    app.setWindowIcon(QIcon.fromTheme("system-software-install"))
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "Wizard.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
