#!/usr/bin/env python3
"""Surface Control - control panel of the Surface Linux suite."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import json
import socket
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, QTimer, QEvent
from PySide6.QtGui import QGuiApplication, QImage, QDesktopServices
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider

import backend
import eq

PW, PH = 800, 600     # size of the preview frames


class Bridge(QObject):
    checksChanged = Signal()
    busyChanged = Signal()
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self._checks = []
        self._busy = False
        self._pool = ThreadPoolExecutor(max_workers=2)
        self._pending = []
        self._nfcEvents = []
        self._latestPending = {}
        self._latestRunning = set()
        self._latestLock = threading.Lock()
        self._testState = "idle"
        self._testProc = None
        self._toneToken = None
        self._micLevel = 0.0
        self._recPath = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "surface-control", "mic-test.wav")
        self._nfcConnected = False
        self._nfcThread = None
        self._nfcStop = None
        self._proc = None
        self._previewCam = ""
        self._previewError = ""
        self._frameNo = 0
        self.provider = PreviewProvider()

    @Property("QVariantList", notify=checksChanged)
    def checks(self):
        return self._checks

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    def _set_busy(self, v):
        self._busy = v
        self.busyChanged.emit()

    @Slot(result="QVariantMap")
    def deviceInfo(self):
        return backend.device_info()

    @Slot(result="QVariantMap")
    def sensors(self):
        return backend.sensors()

    @Slot(result=bool)
    def folioAttached(self):
        return backend.folio_attached()

    @Slot()
    def folioReset(self):
        self._set_busy(True)

        def work():
            self._folioDone = backend.folio_reset()
            self._folioSignal.emit()
        self._pool.submit(work)

    _folioSignal = Signal()

    @Slot()
    def _folioFinished(self):
        rc, out = self._folioDone
        self._set_busy(False)
        self.message.emit("Keyboard cover detected again" if rc == 0 else "Reset failed: " + out)

    @Slot()
    def refresh(self):
        self._set_busy(True)
        f = self._pool.submit(backend.all_checks)
        f.add_done_callback(lambda fut: self._done_checks(fut.result()))

    def _done_checks(self, res):
        # called from a worker thread: hop to the Qt thread through a queued signal
        self._pending = res
        self._applyChecks.emit()

    _applyChecks = Signal()

    @Slot()
    def _apply(self):
        self._checks = self._pending
        self.checksChanged.emit()
        self._set_busy(False)

    # ---- NFC: while the NFC page is open the tags are shown here instead of as desktop notifications ----
    nfcChanged = Signal()
    _nfcSignal = Signal(str)

    @Property("QVariantList", notify=nfcChanged)
    def nfcEvents(self):
        return self._nfcEvents

    @Property(bool, notify=nfcChanged)
    def nfcConnected(self):
        return self._nfcConnected

    @Slot(bool)
    def nfcWindow(self, on):
        flag = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()), "surface-nfc-window")
        if on and self._nfcThread is None:
            try:
                open(flag, "w").write(str(os.getpid()))
            except OSError:
                pass
            self._nfcStop = threading.Event()
            self._nfcThread = threading.Thread(target=self._nfcReader, args=(self._nfcStop,), daemon=True)
            self._nfcThread.start()
        elif not on and self._nfcThread is not None:
            self._nfcStop.set()
            self._nfcThread = None
            try:
                os.remove(flag)
            except OSError:
                pass
            self._nfcConnected = False
            self.nfcChanged.emit()

    def _nfcReader(self, stop):
        path = os.environ.get("NFC_SOCK", "/run/nfc-notify/events.sock")
        while not stop.is_set():
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            try:
                s.connect(path)
            except OSError:
                s.close()
                stop.wait(2)
                continue
            self._nfcConnected = True
            self._nfcSignal.emit("")
            buf = b""
            try:
                while not stop.is_set():
                    try:
                        chunk = s.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self._nfcSignal.emit(line.decode("utf-8", "replace"))
            except OSError:
                pass
            finally:
                s.close()
            self._nfcConnected = False
            self._nfcSignal.emit("")

    @Slot(str)
    def _onNfc(self, line):
        if line:
            try:
                ev = json.loads(line)
            except ValueError:
                return
            lines = backend.nfc_describe(ev.get("records"))
            self._nfcEvents = [{
                "time": time.strftime("%H:%M:%S", time.localtime(ev.get("time", time.time()))),
                "uid": ev.get("uid", "?"), "type": ev.get("type", "tag"), "lines": lines,
                "readMs": ev.get("read_ms", -1), "deliverMs": round((time.time() - ev.get("time", time.time())) * 1000),
                "stamp": ev.get("time", time.time()),
            }] + self._nfcEvents[:49]
        self.nfcChanged.emit()

    @Slot()
    def clearNfcEvents(self):
        self._nfcEvents = []
        self.nfcChanged.emit()

    # ---- audio: speaker boost, microphone enhancer, tests ----
    # Dragging a slider fires dozens of changes; each one costs a few tens of milliseconds of subprocess calls. They are done in the
    # background and only the latest value of each control is kept, so the slider stays smooth.
    def _latest(self, key, fn, *args):
        with self._latestLock:
            self._latestPending[key] = (fn, args)
            if key in self._latestRunning:
                return
            self._latestRunning.add(key)

        def work():
            while True:
                with self._latestLock:
                    item = self._latestPending.pop(key, None)
                    if item is None:
                        self._latestRunning.discard(key)
                        return
                try:
                    item[0](*item[1])
                except Exception:       # a failed live change must not kill the worker
                    pass
        self._pool.submit(work)

    @Slot(float)
    def setSpeakerBoost(self, percent):
        self._latest("boost", backend.set_speaker_boost, percent)

    @Slot(str, float)
    def setMicSetting(self, key, value):
        self._latest("mic-" + key, backend.set_mic_setting, key, value)

    @Slot(bool)
    def enableMicEnhancer(self, on):
        self.stopPreview()
        self._set_busy(True)

        def work():
            self._enhDone = backend.enable_mic_enhancer() if on else backend.disable_mic_enhancer()
            self._enhSignal.emit()
        self._pool.submit(work)

    _enhSignal = Signal()

    @Slot()
    def _enhFinished(self):
        ok, out = self._enhDone
        self._set_busy(False)
        self.message.emit("Done. Reopen apps that use the camera or the microphone." if ok else "Failed: " + out)
        self.audioChanged.emit()

    audioChanged = Signal()
    testChanged = Signal()
    _levelSignal = Signal(float)
    _testEnded = Signal()

    @Property(str, notify=testChanged)
    def testState(self):
        return self._testState

    @Property(float, notify=testChanged)
    def micLevel(self):
        return self._micLevel

    @Property(bool, notify=testChanged)
    def hasRecording(self):
        return os.path.exists(self._recPath)

    def _stopTestProc(self):
        proc, self._testProc = self._testProc, None
        if proc and proc.poll() is None:
            proc.terminate()

    @Slot(str)
    def playTone(self, kind):
        self._stopTestProc()
        self._testState = "tone-" + kind
        self.testChanged.emit()
        token = object()
        self._toneToken = token

        def work():
            try:
                path, cmap = backend.sound_for(kind)
            except (OSError, KeyError) as e:
                self._toneError = str(e)
                self._testEnded.emit()
                return
            if self._toneToken is not token:                  # stopped or replaced meanwhile
                return
            try:
                cmd = ["pw-play"] + (["--channel-map", cmap] if cmap else []) + [path]
                self._testProc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as e:
                self._toneError = str(e)
                self._testEnded.emit()
                return
            proc = self._testProc
            proc.wait()
            if self._testProc is proc:
                self._testEnded.emit()
        self._pool.submit(work)

    @Slot()
    def stopTest(self):
        self._toneToken = None
        self._stopTestProc()
        self._testState = "idle"
        self._micLevel = 0.0
        self.testChanged.emit()

    @Slot()
    def _onTestEnded(self):
        if self._testProc is None or self._testProc.poll() is not None:
            self._testProc = None
            self._testState = "idle"
            self._micLevel = 0.0
            self.testChanged.emit()

    @Slot()
    def micRecord(self):
        """Records 6 seconds from the default microphone, with a live level, to play back afterwards."""
        self._stopTestProc()
        import array
        import math
        import wave
        try:
            proc = subprocess.Popen(["pw-record", "--raw", "--rate", "48000", "--channels", "1", "--format", "s16", "-"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.message.emit("Could not record: %s" % e)
            return
        os.makedirs(os.path.dirname(self._recPath), exist_ok=True)
        self._testProc = proc
        self._testState = "recording"
        self.testChanged.emit()

        def work():
            wav = wave.open(self._recPath, "wb")
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            t0 = time.time()
            chunk = 4800     # 50 ms of 16-bit mono
            while time.time() - t0 < 6 and proc.poll() is None:
                buf = proc.stdout.read(chunk * 2)
                if len(buf) < chunk * 2:
                    break
                wav.writeframes(buf)
                samples = array.array("h")
                samples.frombytes(buf)
                part = samples[::8]
                rms = math.sqrt(sum(x * x for x in part) / len(part)) if part else 0
                db = 20 * math.log10(rms / 32768) if rms > 0 else -90
                self._levelSignal.emit(max(0.0, min(1.0, (db + 60) / 60)))
            wav.close()
            if proc.poll() is None:
                proc.terminate()
            self._levelSignal.emit(-1.0)
        threading.Thread(target=work, daemon=True).start()

    @Slot(float)
    def _onLevel(self, level):
        if level < 0:
            self._testProc = None
            self._testState = "idle"
            self._micLevel = 0.0
        else:
            self._micLevel = level
        self.testChanged.emit()

    @Slot()
    def micPlayback(self):
        self._stopTestProc()
        try:
            self._testProc = subprocess.Popen(["pw-play", self._recPath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.message.emit("Could not play: %s" % e)
            return
        self._testState = "playing"
        self.testChanged.emit()
        proc = self._testProc

        def wait():
            proc.wait()
            self._testEnded.emit()
        threading.Thread(target=wait, daemon=True).start()

    @Slot(result="QVariantMap")
    def keyLabels(self):
        codes = list(range(1, 90)) + [100, 103, 105, 106, 108, 111, 125]
        return {str(k): v for k, v in backend.key_labels(codes).items()}

    @Slot(result=str)
    def keyboardLayout(self):
        layout, variant, model = backend.keyboard_layout()
        return layout + (" (" + variant + ")" if variant else "")

    @Slot(bool)
    def blockShortcuts(self, on):
        backend.block_shortcuts(on)

    @Slot(bool, bool, bool, result="QVariantMap")
    def motion(self, ix, iy, iz):
        return backend.motion((-1 if ix else 1, -1 if iy else 1, -1 if iz else 1))

    @Slot(int)
    def sensorRate(self, hz):
        backend.set_sensor_rate(hz)

    @Slot()
    def resetYaw(self):
        backend.reset_yaw()

    stylusFilterDone = Signal(bool, str)
    _stylusSignal = Signal()

    @Slot(bool)
    def stylusFilter(self, on):
        self._set_busy(True)

        def work():
            self._stylusResult = backend.stylus_filter_toggle(on)
            self._stylusSignal.emit()
        self._pool.submit(work)

    @Slot()
    def _stylusFinished(self):
        ok, out = self._stylusResult
        self._set_busy(False)
        self.stylusFilterDone.emit(ok, out)

    @Slot()
    def restartNow(self):
        subprocess.Popen(["systemctl", "reboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---- output equaliser ----
    eqChanged = Signal()
    _eqSignal = Signal()

    @Slot(result="QVariantMap")
    def eqState(self):
        st = eq.load()
        return {"available": eq.available(), "sync": st["sync"], "sets": st["sets"], "active": eq.active_output(),
                "presets": eq.preset_names()}

    @Slot(str, "QVariantMap")
    def setEq(self, output, s):
        self._latest("eq-" + output, eq.set_output, output, s)

    @Slot(bool)
    def setEqSync(self, on):
        self._latest("eq-sync", eq.set_sync, on)
        self.eqChanged.emit()

    @Slot(str, str)
    def applyEqPreset(self, output, name):
        s = eq.preset_set(name)
        if s:
            eq.set_output(output, s)
            self.eqChanged.emit()

    @Slot(str, "QVariantMap", result=str)
    def saveEqPreset(self, name, s):
        r = eq.save_preset(name, s)
        self.eqChanged.emit()
        return r

    @Slot(str)
    def deleteEqPreset(self, name):
        eq.delete_preset(name)
        self.eqChanged.emit()

    @Slot(str, str, result="QVariantMap")
    def importEq(self, output, path):
        """Reads an Equalizer APO / AutoEQ text file into one output."""
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path
        try:
            text = open(path, encoding="utf-8", errors="replace").read(200000)
        except OSError as e:
            return {"ok": False, "notes": [str(e)]}
        s, notes = eq.parse_apo(text)
        if s is None:
            return {"ok": False, "notes": notes}
        cur = eq.load()["sets"][output]
        s["boost"] = cur["boost"]
        eq.set_output(output, s)
        self.eqChanged.emit()
        return {"ok": True, "notes": notes, "bands": len(s["bands"])}

    @Slot(str, str, result="QVariantMap")
    def exportEq(self, output, path):
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path
        try:
            open(path, "w").write(eq.export_apo(eq.load()["sets"][output]))
        except OSError as e:
            return {"ok": False, "notes": [str(e)]}
        return {"ok": True, "notes": []}

    @Slot()
    def enableEq(self):
        self.stopPreview()
        self._set_busy(True)

        def work():
            self._eqDone = eq.enable()
            self._eqSignal.emit()
        self._pool.submit(work)

    @Slot()
    def _eqFinished(self):
        ok, out = self._eqDone
        self._set_busy(False)
        self.message.emit("Equalizer enabled. Reopen apps that use audio or the cameras." if ok else "Failed: " + out)
        self.eqChanged.emit()
        self.audioChanged.emit()

    @Slot(result="QVariantList")
    def micPresets(self):
        return backend.mic_presets()

    @Slot(str)
    def applyMicPreset(self, name):
        backend.apply_mic_preset(name)
        self.audioChanged.emit()

    @Slot(str, result=str)
    def saveMicPreset(self, name):
        r = backend.save_mic_preset(name)
        self.audioChanged.emit()
        return r

    @Slot(str)
    def deleteMicPreset(self, name):
        if name in backend.MIC_BUILTIN:
            backend.hide_builtin("input", name)
        else:
            backend.delete_audio_preset("input", name)
        self.audioChanged.emit()

    @Slot(result="QVariantList")
    def verifyAudio(self):
        """Is what is saved what the sound server is doing? A list of lines for a dialog."""
        lines = []
        e = eq.verify()
        if e is None:
            lines.append("Equalizer: not enabled")
        elif not e:
            lines.append("Equalizer and speaker boost: applied (every band, the pre-amplifier and the boost match the saved settings)")
        else:
            lines.append("Equalizer: %d values differ, for example %s (saved %s, running %s)" % (len(e), e[0][0], e[0][1], e[0][2]))
        mv = backend.verify_mic()
        if mv is None:
            lines.append("Microphone enhancer: not enabled")
        elif not mv:
            lines.append("Microphone enhancer: applied (gain, low cut, bass, presence and treble match)")
        else:
            lines.append("Microphone enhancer: %d values differ, for example %s (saved %s, running %s)" % (len(mv), mv[0][0], mv[0][1], mv[0][2]))
        lines.append("Playing through: " + ("the headphone jack" if eq.active_output() == "headphones" else "the speakers") + ("; the equalizer is " + ("shared by both outputs" if eq.load()["sync"] else "separate for each output") if eq.available() else ""))
        return lines

    @Slot()
    def disableEq(self):
        self.stopPreview()
        self._set_busy(True)

        def work():
            self._eqDone = eq.disable()
            self._eqSignal.emit()
        self._pool.submit(work)

    @Slot()
    def restoreDefaultPresets(self):
        backend.restore_defaults()
        self.eqChanged.emit()
        self.audioChanged.emit()

    @Slot(str, result="QVariantList")
    def audioPresets(self, kind):
        return backend.audio_presets(kind)

    @Slot(str, str, result=str)
    def saveAudioPreset(self, kind, name):
        r = backend.save_audio_preset(kind, name)
        self.audioChanged.emit()
        return r

    @Slot(str, str)
    def applyAudioPreset(self, kind, name):
        backend.apply_audio_preset(kind, name)
        self.audioChanged.emit()

    @Slot(str, str)
    def deleteAudioPreset(self, kind, name):
        backend.delete_audio_preset(kind, name)
        self.audioChanged.emit()

    @Slot(str)
    def notify(self, text):
        self.message.emit(text)

    @Slot(str)
    def openUrl(self, url):
        if url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(url))

    volumeHoldChanged = Signal()
    _holdSignal = Signal()

    @Slot(result="QVariant")
    def volumeHold(self):
        return backend.volume_hold_state()

    @Slot(bool)
    def setVolumeHold(self, on):
        self._set_busy(True)

        def work():
            self._holdResult = backend.set_volume_hold(on)
            self._holdSignal.emit()
        self._pool.submit(work)

    @Slot()
    def _holdFinished(self):
        ok, out = self._holdResult
        self._set_busy(False)
        if not ok:
            self.message.emit("Could not change it: " + out)
        self.volumeHoldChanged.emit()

    # ---- small pages ----
    @Slot(result="QVariantMap")
    def nfcInfo(self):
        return backend.nfc_info()

    @Slot(result="QVariantMap")
    def audioInfo(self):
        return backend.audio_info()

    @Slot(bool)
    def osdHold(self, on):
        self._pool.submit(backend.osd_hold, on)

    @Slot(str, float)
    def setVolume(self, kind, value):
        self._latest("vol-" + kind, backend.set_volume, kind, value)

    @Slot(str)
    def toggleMute(self, kind):
        backend.toggle_mute(kind)

    @Slot(result="QVariantMap")
    def stylusInfo(self):
        return backend.stylus_info()

    @Slot(result="QVariantMap")
    def updateInfo(self):
        return backend.update_info()

    @Slot()
    def restartCameras(self):
        self.stopPreview()
        self._set_busy(True)

        def work():
            backend.restart_cameras()
            self._restartSignal.emit()
        self._pool.submit(work)

    _restartSignal = Signal()

    @Slot()
    def _restartFinished(self):
        self._set_busy(False)
        self.message.emit("Camera service restarted. Reopen camera apps.")

    @Slot()
    def rebuild(self):
        if not backend.rebuild():
            self.message.emit("Could not open a terminal (konsole)")

    # ---- presets and panel settings ----
    presetsChanged = Signal()

    @Slot(str, result="QVariantList")
    def presets(self, cam):
        return backend.list_presets(cam)

    @Slot(str, str, bool, result=str)
    def savePreset(self, cam, name, overwrite):
        r = backend.save_preset(cam, name, overwrite)
        self.presetsChanged.emit()
        return r

    @Slot(str, str, str, result=str)
    def renamePreset(self, cam, pid, name):
        r = backend.rename_preset(cam, pid, name)
        self.presetsChanged.emit()
        return r

    @Slot(str, str, str, result=str)
    def duplicatePreset(self, cam, pid, name):
        r = backend.duplicate_preset(cam, pid, name)
        self.presetsChanged.emit()
        return r

    @Slot(str, str)
    def deletePreset(self, cam, pid):
        backend.delete_preset(cam, pid)
        self.presetsChanged.emit()

    @Slot(str, str)
    def applyPreset(self, cam, pid):
        was = self._previewCam == cam
        self._set_busy(True)
        self.stopPreview()

        def work():
            backend.apply_preset(cam, pid)
            self._presetDone = (cam, was)
            self._presetSignal.emit()
        self._pool.submit(work)

    _presetSignal = Signal()

    @Slot()
    def _presetFinished(self):
        cam, was = self._presetDone
        self._set_busy(False)
        self.cameraChanged.emit()
        self.presetsChanged.emit()
        if was:
            self.startPreview(cam)

    @Slot(str, "QVariant", result="QVariant")
    def uiSetting(self, key, default):
        return backend.ui_setting(key, default)

    @Slot(str, "QVariant")
    def setUiSetting(self, key, value):
        backend.set_ui_setting(key, value)

    # ---- camera settings (profile files read live by libcamera) ----
    @Slot(str, result="QVariantList")
    def cameraControls(self, cam):
        return backend.controls(cam)

    @Slot(str, str)
    def resetCameraSetting(self, cam, key):
        backend.reset_camera_setting(cam, key)
        self.cameraChanged.emit()

    @Slot(str, result="QVariantMap")
    def focusState(self, cam):
        return backend.focus_state(cam)

    @Slot(str, result="QVariantMap")
    def cameraSettings(self, cam):
        return backend.camera_settings(cam)

    @Slot(str, result="QVariantList")
    def cameraSizes(self, cam):
        return [{"minWidth": w, "text": f"{name}, {fps}"} for w, name, fps in backend.SIZES[cam]]

    @Slot(str, str, float)
    def setCameraSetting(self, cam, key, value):
        if key in ("mirror", "flip"):
            # read when the camera is configured: reopen the preview
            was = self._previewCam == cam
            self.stopPreview()
            backend.set_camera_setting(cam, key, value)
            if was:
                QTimer.singleShot(1500, lambda: self.startPreview(cam))
            return
        if key != "minWidth":
            backend.set_camera_setting(cam, key, value)
            return
        # a size change restarts the camera service: do it off the GUI thread, and restart the preview if it was running
        was = self._previewCam == cam
        self.stopPreview()
        self._set_busy(True)

        def work():
            backend.set_camera_setting(cam, key, value)
            self._sizeDone = (cam, was)
            self._sizeSignal.emit()
        self._pool.submit(work)

    _sizeSignal = Signal()

    @Slot()
    def _sizeFinished(self):
        cam, was = self._sizeDone
        self._set_busy(False)
        self.message.emit("Picture size changed: reopen camera apps that were running.")
        self.cameraChanged.emit()
        if was:
            self.startPreview(cam)

    @Slot(str)
    def resetCamera(self, cam):
        backend.reset_camera_settings(cam)
        self.cameraChanged.emit()

    cameraChanged = Signal()

    # ---- live preview: a GStreamer pipeline on the PipeWire camera, scaled down, raw RGB frames over a pipe ----
    previewChanged = Signal()
    _frameSignal = Signal(bytes)
    _previewEnded = Signal()

    @Property(str, notify=previewChanged)
    def previewCamera(self):
        return self._previewCam

    @Property(int, notify=previewChanged)
    def previewFrame(self):
        return self._frameNo

    @Property(str, notify=previewChanged)
    def previewError(self):
        return self._previewError

    @Slot(str)
    def startPreview(self, cam):
        self.stopPreview()
        self._previewError = ""
        w, h = backend.PREVIEW_SIZE[cam][backend.camera_settings(cam)["minWidth"]]
        node = "libcamera_input.__SB_.PCI0." + ("LNK1" if cam == "front" else "LNK0")
        cmd = ["gst-launch-1.0", "-q", "pipewiresrc", "target-object=" + node, "!",
               f"video/x-raw,format=NV12,width={w},height={h}", "!", "videoscale", "!",
               f"video/x-raw,width={PW},height={PH}", "!", "videoconvert", "!",
               f"video/x-raw,format=RGB,width={PW},height={PH}", "!", "fdsink", "fd=1"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            self._previewError = str(e)
            self.previewChanged.emit()
            return
        self._proc = proc
        self._previewCam = cam
        self.previewChanged.emit()

        def reader():
            size = PW * PH * 3
            got = False
            while True:
                buf = proc.stdout.read(size)
                if len(buf) < size:
                    break
                got = True
                self._frameSignal.emit(buf)
            if not got and self._proc is proc:
                self._previewError = "The camera did not deliver frames (is another app using it?)"
            self._previewEnded.emit()
        threading.Thread(target=reader, daemon=True).start()

    @Slot()
    def stopPreview(self):
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._previewCam:
            self._previewCam = ""
            self.previewChanged.emit()

    @Slot(bytes)
    def _onFrame(self, buf):
        if not self._previewCam:
            return
        self.provider.image = QImage(buf, PW, PH, PW * 3, QImage.Format_RGB888).copy()
        self._frameNo += 1
        self.previewChanged.emit()

    @Slot()
    def _onPreviewEnded(self):
        if self._proc is not None and self._proc.poll() is not None:
            self._proc = None
            self._previewCam = ""
            self.previewChanged.emit()


class TabletFilter(QObject):
    """Sees the raw pen events of the window (pressure, tilt, eraser end, buttons) that Qt Quick items do not get, and hands them to the Stylus page."""
    event = Signal("QVariantMap")
    _kinds = {QEvent.TabletPress: "press", QEvent.TabletMove: "move", QEvent.TabletRelease: "release",
              QEvent.TabletEnterProximity: "enter", QEvent.TabletLeaveProximity: "leave"}

    _last = 0.0

    def eventFilter(self, obj, ev):
        kind = self._kinds.get(ev.type())
        if kind == "move":
            # a pen reports 100+ times a second: the page only needs about 60 updates a second, more makes the layout work for nothing
            now = time.monotonic()
            if now - self._last < 0.016:
                return False
            self._last = now
        if kind:
            try:
                p = ev.position()
                self.event.emit({
                    "kind": kind, "x": p.x(), "y": p.y(), "pressure": float(ev.pressure()),
                    "xTilt": float(ev.xTilt()), "yTilt": float(ev.yTilt()), "rotation": float(ev.rotation()),
                    "tangential": float(ev.tangentialPressure()),
                    "tool": {4: "pen", 8: "eraser", 16: "cursor"}.get(int(ev.pointerType().value), "unknown"),
                    "buttons": int(ev.buttons().value) if hasattr(ev.buttons(), "value") else int(ev.buttons()),
                })
            except (AttributeError, TypeError, ValueError):
                pass
        return False


class PreviewProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.image = QImage(PW, PH, QImage.Format_RGB888)
        self.image.fill(0)

    def requestImage(self, id, size, requestedSize):
        return self.image


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Surface Control")
    app.setDesktopFileName("surface-control")
    bridge = Bridge()
    bridge._applyChecks.connect(bridge._apply)
    bridge._sizeSignal.connect(bridge._sizeFinished)
    bridge._nfcSignal.connect(bridge._onNfc)
    bridge._holdSignal.connect(bridge._holdFinished)
    bridge._eqSignal.connect(bridge._eqFinished)
    bridge._stylusSignal.connect(bridge._stylusFinished)
    bridge._presetSignal.connect(bridge._presetFinished)
    bridge._enhSignal.connect(bridge._enhFinished)
    bridge._levelSignal.connect(bridge._onLevel)
    bridge._testEnded.connect(bridge._onTestEnded)
    app.aboutToQuit.connect(bridge.stopTest)
    app.aboutToQuit.connect(lambda: backend.osd_hold(False))
    app.aboutToQuit.connect(lambda: bridge.blockShortcuts(False))
    bridge._restartSignal.connect(bridge._restartFinished)
    bridge._frameSignal.connect(bridge._onFrame)
    bridge._previewEnded.connect(bridge._onPreviewEnded)
    app.aboutToQuit.connect(bridge.stopPreview)
    app.aboutToQuit.connect(lambda: bridge.nfcWindow(False))
    bridge._folioSignal.connect(bridge._folioFinished)
    backend.migrate_old_mode()
    backend.osd_restore()
    engine = QQmlApplicationEngine()
    engine.addImageProvider("preview", bridge.provider)
    engine.rootContext().setContextProperty("bridge", bridge)
    from tips import TIPS
    engine.rootContext().setContextProperty("tips", TIPS)
    bridge.tablet = TabletFilter()
    engine.rootContext().setContextProperty("tablet", bridge.tablet)
    page = sys.argv[sys.argv.index("--page") + 1] if "--page" in sys.argv else "Overview"
    engine.rootContext().setContextProperty("startCam", sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else "front")
    engine.rootContext().setContextProperty("keytestSeconds", int(os.environ.get("SURFACE_KEYTEST_SECONDS", "0")))   # for tests: leave the key test by itself
    engine.rootContext().setContextProperty("startTest", "--keytest" in sys.argv)
    engine.rootContext().setContextProperty("startPage", {"updates": "UpdatesPage.qml"}.get(page, page.capitalize() + "Page.qml"))
    engine.load(QUrl.fromLocalFile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml", "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    engine.rootObjects()[0].installEventFilter(bridge.tablet)
    bridge.refresh()
    if "--preview" in sys.argv:
        bridge.startPreview(sys.argv[sys.argv.index("--preview") + 1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
