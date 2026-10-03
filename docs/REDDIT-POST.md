# Reddit post draft (r/SurfaceLinux, then r/Fedora and r/kde if it goes well)

**Title:** Surface Go 1824 on Fedora Kinoite: working cameras with autofocus, NFC, and a control panel (looking for testers on other Surface models)

**Body:**

I got a Surface Go (1824) working properly on Fedora Kinoite 44 with Secure Boot on, no `rpm-ostree` layering, and put everything in one repo: scripts, patches, tunings and a small control panel.

What works on my unit:

- **Front and rear cameras** through libcamera/PipeWire, so Firefox, Kamoso, Zoom and friends see them. The rear camera has a rewritten **autofocus** (the stock one hunts and often settles blurry), correct orientation (it was mirrored), stable exposure under artificial light (the driver reported a wrong pixel rate), proper black level, tone curve and lens shading from the Windows calibration, and a software temporal denoiser.
- **NFC** always on, iPhone-style: sound + notification with the tag content, about 15 ms to read an NDEF tag.
- Volume buttons with hold-to-repeat, a fixed fake "stylus 0%" battery, louder speakers, a sane microphone, keyboard-cover recovery.
- **Surface Control** (PySide6 + Kirigami, native on Kinoite): health checks with an explanation for each fix, a live camera editor (exposure, curves, shadows/highlights, colour, sharpness, denoise, manual focus with a sharpness meter, mirror/flip, picture size) whose settings apply to *every* app, per-camera presets, audio (speaker boost, mic enhancer, tests), NFC test, pen test (pressure/tilt/eraser), a 3D view of the tablet from the accelerometer and gyro, keyboard and trackpad test.
- A watcher that notices a kernel update (the patched kernel modules are per kernel) and offers a one-click rebuild.

What does not: the IR camera (Windows Hello) is not exposed by libcamera. Only the Surface Go 1824 is verified; other models will need porting and I want to know what breaks. Secure Boot needs the usual MOK enrolment step once (blue screen, password typed twice).

It is a test installation for now (one tablet, a few weeks of work), so expect rough edges. Everything is measured rather than guessed: the repo has the numbers and the test tools.

Repo: <link>

If you try it on another Surface (Go 2/3, Pro, Laptop...) please open a hardware report: what the Overview page says, `uname -r`, and what the cameras do.
