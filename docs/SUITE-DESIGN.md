# Surface Linux Suite - design

Goal: on a clean Fedora Kinoite install on a Surface Go, one installer + one reboot gives a fully working machine (cameras with autofocus and good colour, NFC, volume buttons,
stylus, audio, folio keyboard recovery) and a control panel that keeps it working. No `rpm-ostree` layering: everything lives in `/var`, `/etc`, `~/.local` and toolbox.

Tested hardware: Surface Go 1824 (Pentium 4415Y, OV5693 front, OV8865 rear), Kinoite 44, Secure Boot on. Other models are untested.

## 1. Install: one command, one reboot
`./install.sh` (replaces the numbered scripts, which stay as the building blocks):
1. checks (Kinoite, Secure Boot state, network, free space), asks for sudo once;
2. creates the module signing key and queues the MOK enrolment (Secure Boot: the one unavoidable manual step is the blue "MokManager" screen at the next boot, a password typed twice; with
   Secure Boot off it is skipped);
3. installs the stage-2 job (systemd, runs once at the next boot, shows progress as a notification and in the control panel);
4. reboots. After the MOK step stage 2 builds the kernel modules, the patched libcamera, installs tunings, user services and apps, then asks for a last reboot.
Everything is idempotent: running it again repairs. The same mechanism is used after a kernel update.

## 2. Boot-time change detection (`surface-watch`)
A user service at login (and a root timer for headless cases) compares the running system with `/var/lib/surface-suite/state.json` written by the installer:
kernel version vs modules built for it, libcamera/pipewire/wireplumber versions vs the patched build, MOK key enrolled, installed tuning hashes, WirePlumber drop-ins intact,
rpm-ostree deployment id, Fedora release. It classifies each difference (ok / needs rebuild / may break a fix) and shows it in the panel and as one notification with a
"Repair now" button. Nothing is rebuilt silently (the build needs sudo and the signing key).

## 3. Components
- **Surface Control** (PySide6 + QML, native on Kinoite where PySide6 and Kirigami are already installed): Overview, Cameras, Audio and input, NFC, Updates and log.
- **Surface Camera** (second app, same toolkit): a camera app with pro controls and presets.
- **surface-helper** (root, D-Bus + polkit): only the actions that need root (install a tuning to `/etc`, install rebuilt modules, reset the folio, enable/disable fixes).
  The apps never run as root.
- **libcamera patches + tunings** (this repository): the fixes themselves.
- **Camera control channel**: see 4.

## 4. Camera settings: global vs session
All apps get the camera through PipeWire (WirePlumber hosts libcamera). Only one client can use the ImgU at a time.
- **Profile (global)**: `~/.config/surface-suite/camera/<sensor>.json` is read by the patched libcamera (tuning values: black level, noise reduction, temporal denoise, tone curve,
  lens-shading extra, mirror, and the *size list / first size offered*, which is what decides what Zoom or Kamoso get). A change made in the panel is written to the profile and
  applied live: the pipeline re-reads it every N frames (the same mechanism as the `/dev/shm` hooks used during development, done properly). Persistent across reboots, applies to every app.
- **Session override**: the camera app writes `session.json` (with its pid) while it is running; the pipeline merges it over the profile only while that pid is alive. Closing the app,
  or a crash, removes the effect. The app offers "apply to this session" or "apply to all apps" (= write the profile instead).
- What can live in the pipeline (cheap on a Pentium, so valid for all apps): all corrections done so far, tone curve and per-channel curves, saturation / hue / tint (UV matrix),
  vignetting, temporal denoise, mirror, manual focus position and AF mode, size and frame rate.
- What cannot (too heavy for the CPU at 30 fps): 3D LUTs and "filters". Those run on the GPU in the camera app (session only) or in an optional **virtual camera**
  ("Surface Go Camera (filtered)": a PipeWire node fed by a GStreamer/GL pipeline, started on demand). A WirePlumber rule can hide the raw nodes so that every app only sees the
  virtual one, which is how "apply to all apps" works for LUTs.

## 5. Pages
- Overview: health of everything (the checks of `03-verify.sh`), what changed since install, repair button.
- Cameras: camera switch always visible, live preview (holds the camera: other apps cannot use it meanwhile, said in the UI), size/fps for apps, profile editor with live sliders,
  presets (`frontale_1` and own ones), calibration wizards (white screen -> lens shading, covered lens -> black level), focus peaking + sharpness meter, AF mode / manual focus.
- Audio and input: speaker scale, microphone filter, volume buttons hold-to-repeat, folio recovery, stylus battery.
- NFC: daemon state, last tag, sound/notification.
- Updates and log: patch/module state per kernel, rebuild, logs, export/import of presets.

Status 2026-10-02 night: Control app has Overview (detail pages), Updates, Cameras (live editor), Keyboard (test), Audio, NFC, Stylus, Sensors. See README, section Surface Control.

## 6. Milestones (each one tested on the Surface)
1. Repository layout, `install.sh` stage structure, `surface-watch`, Control app with the Overview page and the rear camera mode selector.
2. Camera control channel in libcamera (profile + session override, live reload) and the Cameras page with live preview and sliders. DONE for gamma, contrast, black level, spatial/temporal denoise, size (front and rear); still to add: saturation/tint, vignetting, manual focus and AF mode.
3. Calibration wizards and presets; focus peaking.
4. Audio / input / NFC / stylus pages.
5. Surface Camera app, then the virtual camera.
6. Packaging, documentation, release.

## 7. Limits to say out loud
Secure Boot needs the MOK step. One camera client at a time. Only the Surface Go 1824 is verified. Software filters are limited by a 4-thread Pentium; heavy ones go through the GPU.
