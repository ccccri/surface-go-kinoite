# Contributing

This started as one person's fix for one tablet (Surface Go 1824, Fedora Kinoite). Reports from other Surface models are the most useful thing you can send.

- **Tested hardware:** only the Surface Go 1824 (OV5693 front, OV8865 rear, Pentium 4415Y). Anything else is unverified: a hardware report (issue template) tells us what to port.
- **Patches** live in `patches/`: kernel drivers (`ov*.patch`, `nxp-nci-*`, `intel-hid-*`) and libcamera 0.7.1 (`libcamera-0.7.1-*.patch`, applied in file name order on a clean tarball). A new patch must apply on a clean tree together with the others:
  `for p in patches/libcamera-0.7.1-*.patch; do git apply -p1 "$p"; done`.
- **Surface Control** is `suite/control` (PySide6 + Kirigami). `backend.py` has no UI code; the pages are in `qml/`. Run it from a checkout with `SURFACE_GUIDE=$PWD python3 suite/control/main.py`.
- **Tests:** `suite/control/tests/run_all.sh` on the tablet runs the page loader, backend, typed-value field, NFC window, keyboard test, pen (6000 synthetic events), equaliser maths, equaliser and preview stress, a fuzz of the camera profile against the patched libcamera, and opens every page in the real window. The camera and audio ones touch the hardware and put your settings back.
- **Measure, do not guess.** The camera work is full of measurements (`tools/focus-test/`, README). A change to colour, focus or noise should come with a number or a picture.
- **No layering:** the install must not use `rpm-ostree install`. Everything lives in `/var`, `/etc`, `~/.local` and the toolbox.
- Keep user-visible text in English (US).

License: MIT for the scripts, the Surface Control app and the documentation (see `LICENSE`). The files in `patches/` are derived from other projects and keep their licenses: the libcamera patches follow libcamera's LGPL-2.1+, the kernel patches the kernel's GPL-2.0.
