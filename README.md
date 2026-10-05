# Surface Go on Linux: cameras, NFC and Surface Control

A Surface Go 1st gen (model 1824, 8 GB RAM, NVMe SSD, Wi-Fi only) on Fedora Kinoite with Secure Boot on and **no `rpm-ostree` layering**: working front and rear cameras with autofocus, NFC, volume buttons,
a control panel (**Surface Control**) and a watcher that notices kernel updates. Tested on one tablet only (see `CONTRIBUTING.md` to report other models).

**Why this exists.** The [linux-surface](https://github.com/linux-surface/linux-surface) kernel is the usual answer for Surface devices, but for this tablet it did not
seem to give more than the stock Fedora kernel in our tests, and it leaves the same gaps open: the rear camera, the NFC reader and the volume buttons.
This project fills those gaps on top of the stock kernel (a few small patched drivers, a patched libcamera, some services) and adds a control panel.

- Quick start: `scripts/01-upgrade-and-mok.sh`, reboot, `scripts/02-build-and-install.sh`, `scripts/03-verify.sh` (details below).
- The control panel: `suite/control` (installed as `surface-control`), described in the "Surface Control" section.
- Design of the whole suite: `docs/SUITE-DESIGN.md`. Reddit/announcement draft: `docs/REDDIT-POST.md`.

**Planned:** the kernel-update check shown inside Surface Control itself instead of only as a notification.
**Not yet tested end to end:** the installer window running steps 1 and 2 for real on a freshly installed system (the page flow, the verification and a failing step are tested with fake steps).

---

# Surface Go 1st gen (model 1824, 8 GB RAM, NVMe SSD, Wi-Fi only) on Fedora Kinoite: cameras + NFC

Worked out and verified on 2026-09-30 on this Surface Go running Fedora Kinoite 44 (kernel 7.2.7-200.fc44),
Secure Boot **enabled**. Everything below was done and tested on the real device.

## What you get

| Part | Status |
|---|---|
| Front camera (OV5693) | Works, 30 fps. Fixed focus. With the tuning in `tuning/ipu3/` a backlit scene (window behind you) is exposed properly and colours are neutral by eye. A measured colour comparison with a phone is still to do (see "Colour limits"). |
| Rear camera (OV8865) | Works after the kernel patch below, 30 fps at 720p, 15 fps at 1080p, with **autofocus**: libcamera's contrast AF runs by itself and settles after ~3 s, so wait a moment after opening the camera before taking a picture. |
| IR camera (OV7251, Windows Hello) | Detected by the kernel, not exposed by libcamera. Not usable. |
| NFC | Works, always on. Reads NDEF from Type 2 tags (NTAG / Ultralight) in ~15 ms; other cards/phones are reported by UID only. |

NFC behaves like on a phone: the reader polls all the time and, when a tag shows up, plays a sound and shows a
notification with what is on it. A link is opened only if you click **Open** in the notification.
Two small services do this (both installed by step 2):

- `nfc-daemon` (system service, root): owns the reader, polls, reads the tag and releases it in the kernel, re-arms polling.
- `nfc-notify` (systemd *user* service): receives events from the daemon on `/run/nfc-notify/events.sock`
  (group `wheel`) and shows the notification + sound. Stop it with `systemctl --user disable --now nfc-notify`.

Power use. For NFC to notice a tag by itself, the reader has to send out a short radio pulse over and over, even when nothing is near. The more
often it does, the sooner a tag is noticed and the more battery it uses. The chip's default is one pulse per second; a small patch to the
`nxp-nci` driver (`patches/nxp-nci-poll-period.patch`, parameter `poll_period_ms`) sets it to every 250 ms, so a tag is noticed within a quarter of a second.
Measured: reading a tag takes 10-17 ms and the notification gets the result 1 ms later. The extra battery drain was **not measured**; if it matters to you,
raise the value (or stop the service: `systemctl disable --now nfc-daemon`).
When the desktop power profile is **Power Saver**, `nfc-daemon` reads for 0.6 s and then switches the reader off for 3.4 s, about 8 times fewer radio pulses; a tag can then take up to
~4 s to be noticed. Any other profile goes back to continuous polling by itself.

Colour limits: libcamera 0.7.x has no colour-correction-matrix (`Ccm`) algorithm for the IPU3, so colours can only be balanced by
the automatic white balance. Neutral surfaces come out neutral, saturated blues are somewhat more saturated than on the iPhone 15 Pro we compared against.
That comparison was a single informal one and should not be relied on. **Future work:** tune the colours properly and publish side-by-side photos with a phone.
A newer libcamera lists `Ccm` in its IPU3 tuning file; when Fedora ships it, a matrix can be added to `tuning/ipu3/*.yaml`.

## Quick path on a clean install

**Before wiping a tablet that already works, copy `~/mok` somewhere safe.** Put it back in the same place after reinstalling: the key is already trusted by the firmware, so the blue MOK screen is not needed again.

**Easiest: the installer window.** In a terminal on the Surface:

```bash
git clone https://github.com/ccccri/surface-go-kinoite.git ~/surface-go-kinoite
~/surface-go-kinoite/install.sh
```

On a brand new Kinoite install PySide6 is missing until the first system update, so the first run does step 1 in the terminal (update + key); restart, press the keys on the blue MOK screen, run `install.sh` again and the window opens. The wizard checks the device, asks for your password once, runs the steps below with a progress bar, tells you what to press on the blue
MOK screen, reopens by itself after each restart and ends with the verification. "Show details" opens the console output for power users. It looks at the
system to know where it is, so closing it is safe. The steps below are what it runs; you can still do them by hand.

**By hand**

Do this on the Surface, as your normal user, in a terminal (Konsole). The scripts expect the folder in your home directory:

```bash
git clone https://github.com/ccccri/surface-go-kinoite.git ~/surface-go-kinoite
cd ~/surface-go-kinoite
bash scripts/01-upgrade-and-mok.sh      # upgrade + create signing key, queue MOK enrollment
systemctl reboot
```

At boot a **blue MOK screen** appears, you have about 10 seconds to press a key:
`Enroll MOK` -> `Continue` -> `Yes` -> password (`surface`, or whatever you set with `MOK_PASSWORD=`) -> `Reboot`.
It needs the keyboard attached. The MOK screen **always uses a US (QWERTY) keyboard layout**, whatever layout the system uses, so the default password `surface` is
safe to type; if you choose your own with `MOK_PASSWORD=`, use only characters that are in the same place on a US keyboard
(see the [linux-surface Secure Boot page](https://github.com/linux-surface/linux-surface/wiki/Secure-Boot)).

```bash
cd ~/surface-go-kinoite
bash scripts/02-build-and-install.sh    # builds + signs + installs the modules, installs the NFC services
systemctl reboot
bash scripts/03-verify.sh               # all lines should say [ok]
```

Test NFC: hold a tag on the back of the device and move it slowly (the antenna position is not marked):
you should hear a sound and get a notification. Test cameras: install Kamoso or Snapshot from Discover.

**After a kernel update** the patched modules have to be rebuilt, because they are built for one exact kernel. You do not have to remember it: a small
service (`kmods-check`) runs at every login, and when the running kernel has no matching build it shows a notification with a **Rebuild now** button
(about 5 minutes, asks for your password, then offers a reboot). The same rebuild is on the Updates page of Surface Control. Re-run
`scripts/02-build-and-install.sh` by hand only after a libcamera update. If a rebuild is missed, nothing breaks: the modprobe rules fall back to the stock modules (rear
camera goes back to the green-stripe bug, NFC disappears).

## Why each piece is needed (root causes)

**1. Old kernel: cameras completely dead (`cam -l` lists nothing).**
The installer image carried kernel 6.19.x. In 6.19 the `dw9719` autofocus driver lost its
`i2c_device_id` table, so the VCM device that `ov8865` creates never binds. The sensors then wait for it
forever, the CIO2 notifier never completes, and the media graph shows every sensor with `0 link`.
Symptom: `media-ctl -d /dev/media0 -p` shows `ov5693/ov8865/ov7251 ... (1 pad, 0 link)`.
Fix: `rpm-ostree upgrade` (kernel 7.2.7 works). No layering needed.

**2. Rear camera: green stripes, one frame, stall.**
WirePlumber's libcamera monitor keeps the VCM subdev open, which keeps the sensor runtime-active. A later
format change then never reaches the hardware; the sensor keeps the old mode while CIO2 expects the new one
(`ipu3-cio2: payload length is N, received M` in dmesg). Fix: `patches/ov8865-stale-mode.mbox` (two commits from
the linux-surface project: reprogram the sensor at stream start if the mode differs, plus a PM reference leak fix),
built as an out-of-tree `ov8865.ko` and signed. Upstream 7.2.7 does not contain it; the build script skips the
patch automatically when the source already has it (`hw_mode`).
Reference: https://github.com/linux-surface/linux-surface/pull/2169

**2b. Dark pictures (both cameras).**
The stock `uncalibrated.yaml` aims at a mean luminance of 0.16 and only forces the brightest 2% of the histogram to 0.5.
With a window in the frame the exposure follows the window and the rest is black (measured 83% of the pixels below
20/255; the rear camera 60%). `tuning/ipu3/ov5693.yaml` and `ov8865.yaml` raise the target to 0.30 and add a lower
constraint (25-55% quantile band >= 0.18): same backlit scene, dark pixels 83% -> ~4%, median luma 0 -> ~120/255.
libcamera loads `/etc/libcamera/ipa/ipu3/<sensor>.yaml` before `/usr/share/...`, no `/usr` change needed. Test variants
without touching `/etc`: `LIBCAMERA_IPA_CONFIG_PATH=/some/dir cam ...` with `/some/dir/ipu3/<sensor>.yaml`.
Note: a toolbox has its own `/etc`, so `cam` inside it does not see the host's tuning files (WirePlumber, on the host, does).

**2c. WirePlumber crashes (apps that use the cameras).**
Reproduced with a stress test (PipeWire clients starting/stopping on both cameras at random sizes: WirePlumber died 8 times
in ~90 s). Two separate bugs in libcamera 0.7.1's IPU3 pipeline, both fixed by `patches/libcamera-0.7.1-ipu3-crash-fixes.patch`:
- `SIGABRT` in `std::clamp` (`calculateBDSHeight`, `IPU3CameraConfiguration::validate()`): `minIFHeight` is unsigned and
  wraps around for small inputs, so clamp gets lo > hi. Fedora builds with `_GLIBCXX_ASSERTIONS`, so it aborts instead of
  just misbehaving.
- `SIGSEGV` in `IPU3Frames::create` / `IPU3CameraData::paramsComputed`: `IPU3Frames::clear()` did not clear the map of frames in
  flight, so a late completion after `stop()` found a stale entry and pushed already-freed param/stat buffers back into
  the "available" queues; `init()` did not empty the queues either, so the next `start()` used a dangling pointer.
  Also `bufferAvailable.connect()` was called on every start and never disconnected.
The same version is rebuilt (same ABI as the PipeWire plugin), IPU3 pipeline only, installed in
`/usr/local/libcamera-patched` and used by WirePlumber only, via `~/.config/systemd/user/wireplumber.service.d/patched-libcamera.conf`
(`LD_LIBRARY_PATH`). After the fix the same stress test ran without a single crash. The script rebuilds it for the installed
libcamera version and falls back to the stock library if the patch no longer applies. Check what WirePlumber loads with
`grep libcamera /proc/$(pgrep -x wireplumber)/maps`.

**2d. Image quality vs. what Kamoso asks for (sensor modes).**
Kamoso requests 640x480. libcamera then picks the smallest sensor mode that covers it, and the AE's maximum exposure is the
sensor's exposure-control limit, which follows that mode's default frame time:
rear OV8865 800x600 mode = 2.7 ms (black pictures), 1632x1224 mode = 8.3 ms (120 fps); front OV5693 1296x972 = 16.5 ms (60 fps),
2592x1944 = 33 ms. Fixes applied: drop the 800x600 mode (ov8865), cap the ov5693 default at 30 fps. NOT solved: the rear camera still
has only 8.3 ms of exposure (see "Tried and rejected"). Sensor delays: libcamera had empty `sensorDelays` for both sensors and assumed
(exposure 2, gain 1); measured with the AE loop on a static scene: the defaults oscillate (11-13% brightness stdev) while (2,2), (3,2)
and (2,3) were stable, so (2,2) (used for many OmniVision sensors) is set in `libcamera-0.7.1-sensor-delays.patch`.

**Open: AE kicks.** In the PipeWire path the brightness still shows periodic bursts (+40% decaying over ~13 frames) every ~16 frames, and
a few near-black frames at start (the first AGC decision has a digital gain of ~1e8 because the first statistics are empty). Not caused
by: Af (removed from the front tuning, no change), CPU governor (performance, no change). Changing `kMaxFrameContexts` 16 -> 64 in
`src/ipa/ipu3/ipu3.cpp` changed the behaviour (more, not fewer, steps) without fixing it. The rear result was 0.24% stdev three times in a
row right after the delay fix, then 12-40% in later runs, so there is another variable I did not pin down (it was stable while Kamoso was
streaming the other camera at the same time). Measure with a static region, e.g. the ceiling, not the whole frame.

**3. NFC.**
ACPI device `\_SB.PCI0.I2C0.NFC1`, HID `NXP3001`, I2C address 0x28, resources: GpioInt (IRQ), GpioIo, GpioIo.
It is an NXP NCI 1.1 controller (CORE_RESET_RSP reports NCI version 0x11), NOT a PN7160. The in-tree
`nxp-nci_i2c` driver already handles this family with exactly this GPIO order (index 1 = firmware download
request, index 2 = enable) but only knows the ACPI ids NXP1001/NXP1002/NXP7471. The one-line patch
`patches/nxp-nci-add-NXP3001.patch` adds `NXP3001`. Then the normal kernel NFC stack (`nfc0`) works.
Things that were tried and are NOT needed: the NXP `nxpnfc`/`libnfc-nci` out-of-tree stack and porting it.

**3b. Why not neard.** neard 0.19 read tags fine but was not usable for an always-on reader: it segfaults in
`data_recv` (`plugins/nfctype2.c`) when a tag disappears during a read, and under fast tag swapping it leaves the
kernel with an "active target" (`nci: nci_start_poll: there is an active target` in dmesg), after which polling silently
stops for tens of seconds. The rule in the kernel: opening a raw NFC socket to a tag activates it, and it stays active
until `NFC_CMD_DEACTIVATE_TARGET`; only then can polling restart. `tools/nfc-daemon.py` (standard library only, netlink +
`AF_NFC` raw socket, Type 2 NDEF parser) does exactly that after every read, and recovers a stale target on start.

**4. Secure Boot and module signing.**
Secure Boot is on with kernel lockdown, so unsigned modules are refused. Fedora's module-signing key is
generated per build and thrown away, so it cannot be reused; you need your own key enrolled through MOK
(`mokutil --import`, confirmed once on the blue screen). `01-upgrade-and-mok.sh` creates the key in `~/mok`
(keep `MOK.priv` private; anyone with it can sign modules your kernel will accept).

**5. Kinoite specifics.**
`/usr` is read-only, so modules live in `/var/lib/local-kmods` (SELinux type `modules_object_t`) and are
loaded by `insmod` from `/etc/modprobe.d` "install" rules. NFC needs a systemd service (`local-nxp-nci.service`)
because the kernel has no alias for `NXP3001` (nothing autoloads the module) and `systemd-modules-load`
runs before `/var` is mounted, so it cannot find the file. Build tools live in a toolbox, not on the host.

### Rear camera picture is mirrored
The OV8865 rear camera delivers a horizontally mirrored picture (text in the scene is reversed in every application) while the front camera is fine. The kernel reports
`camera_sensor_rotation 0` and orientation "Back", and a mirror cannot be described by a rotation, so libcamera applies no flip. `patches/libcamera-0.7.1-ipu3-ov8865-hflip.patch` XORs
`Transform::HFlip` into the transform the IPU3 pipeline applies to the sensor when the sensor model is ov8865: the sensor itself flips the readout, no copy in software.
Checked by pointing the camera at a monitor showing text: the text reads correctly with the patch.

### Autofocus: local search instead of "homing", measured accuracy, speed
The stock IPU3 autofocus restarts from lens step 0 and sweeps the whole range every time the scene changes (the lens visibly goes to a "transition" position first),
and it only restarts when one frame's sharpness differs by more than 50% from the best value of the scan. `patches/libcamera-0.7.1-af-robust-scan.patch` now:
- keeps a reference sharpness measured on the parked lens (8 frames) and restarts when the sharpness stays more than 30% away from it for 3 frames;
- restarts with a *local* hill climb from the current position: sharpness at the current step and one step (48) above/below, then it follows the better direction
  (4 frames per position) until it has fallen below 85% of the best for two positions, then 3 positions 12 steps apart and a parabola place the peak;
- falls back to the full scan when the neighbours are flat within 12% (the lens is on the far-blurred plateau, where the sharpness has no gradient: measured the same value
  within a few % over 130 steps, and a stuck lens there never recovers by itself) or when no peak is found in 40 positions;
- rescans (up to twice) if the sharpness of the parked lens is below 70% of the value that made it choose the position.
Measured on a static textured scene at 30 cm (lens frozen with a test hook, image gradient energy per step): the image sharpness peaks at step 300-312, the AF statistic at 288,
and the curve is wide (>= 97% of the maximum within +-24 steps). Eight restarts from forced start positions (20 ... 700) ended at 286-297 each; 0 spurious restarts in 60 s of a static scene;
a 300 step refocus takes 1.6 - 2.4 s (about 0.4 s of that is the exposure settling and the change detection). A first version with a coarse 48 step climb and a +-16 refinement
missed the peak (too short a refinement range): a coarse climb needs a refinement that covers half a step on each side.

## Device volume buttons, stylus battery, audio, touch

**Rear camera autofocus (libcamera IPU3 `Af`): four separate defects.** Measured with the printed chart and a test hook that freezes
the lens (`tools/focus-test/`). For the chart at ~35 cm the image sharpness (mean squared gradient) has one peak at lens step ~320
(~1635 against ~90 out of focus, same peak in all five regions of the image, so the chart was parallel to the sensor), and the stock
autofocus ended anywhere between 29 and 396, often 30% softer than the maximum:
1. *Coarse scan stopped at the first 10% drop.* In the flat out-of-focus part of the range the statistic wobbles 5-10% per frame, so noise
   was taken as the peak (1 start in 12 stayed at step 29, sharpness 78).
2. *Scan started while the auto exposure was still converging.* The statistic scales with brightness squared; in the first ~1.5 s gain
   jumps 16 -> 4 -> 12 -> 1 and the first scan ended at step 59. The AF now waits until exposure*gain changes <5% for 6 frames.
3. *Fine scan used the Y2 statistic*, which decreases monotonically with the lens position (7.7M at 260 -> 5.5M at 450, no maximum), while Y1
   has a clear peak at 310-320. Y1 is used for both scans.
4. *Fine scan compared each sample with the previous one*, so a peak that falls 2-3% per step never ended the scan and it ran to the end of its
   window (and the lens was still moving during the first fine samples, which could even restart the whole scan). The scan now tracks the
   global maximum, stops 10% below it, and waits 10 frames after the lens jumps back. The fine window is +-36 steps (step 3) instead of
   +-5% of the focus step, and the AF grid covers two thirds of the processed image (up to 32x24 cells) instead of the minimum 256x128 pixels, so it no longer
   depends on whatever small detail is exactly in the centre. The grid must be computed from the BDS output size: a fixed 1024x768 grid
   was larger than the image of a 640x480 stream (what Kamoso asks for), corrupted the 3A statistics and left the auto exposure stuck
   at maximum gain (fully white, green image, no frames with `cam`). Always check the PipeWire feed at 640x480, not only `cam` at 1600x1200.
All in `patches/libcamera-0.7.1-af-robust-scan.patch`. Result: 20 of 20 starts settle between 312 and 321 (sharpness 1630-1640) at 1600x1200, and the 640x480 PipeWire feed is well exposed and sharp.
In Kamoso the old code did 3 scans in the first minute (23 in 3 minutes while the camera was moved); the new one did 1 in 186 s.
Only ~35 cm and one scene were measured; 20 and 80 cm are still to do.

**Rear camera: flashing picture and blown-out start-up (three more root causes).** Measured on the PipeWire feed at 640x480 (what Kamoso
uses) with `gst-launch-1.0 pipewiresrc target-object=libcamera_input.__SB_.PCI0.LNK0` and the mean luma of every frame. Before: luma toggled between
~124 and ~171 every ~5 frames (57 jumps >10% in 10 s), sharpness 100/74, and the first ~100 frames were blown out.
1. *Wrong pixel rate, every time 4x too short.* The `ov8865` driver reports `pixel_rate` from the MIPI link (288 MHz), but the binned mode
   (hts 1923) runs at 72 MHz: frame rate against VBLANK gives 26.7 us per line (30 fps at vblank 22). libcamera derives the exposure time from
   the pixel rate, so the AE believed it exposed for 8.3 ms while the sensor integrated for the whole 33 ms frame, which is 3.3 periods of
   the 100 Hz lamp flicker and beats against the frame rate. `patches/ov8865-pixel-rate.patch` reports 72 MHz for that mode.
   (Setting a long VBLANK before streaming, e.g. 3768 lines = a 130 ms frame, makes the CIO2 receiver stop with
   `inter-frame long packet discarded`; changing it while streaming works.)
2. *Analogue gain in whole steps of 1x.* The driver's control is 128..2048 with step 128 and the V4L2 core rounds to the step, so the AE asking
   for 1.2x-1.7x got 1x or 2x (2^(1/2.2) = 1.37, exactly the luma jump). The sensor itself is continuous (luma 25 -> 27 -> 29 -> 33 ... -> 81 for
   gain 1.0 ... 3.0 with step 1). `patches/ov8865-analogue-gain-step.patch` sets step 1.
3. *Start-up.* `patches/libcamera-0.7.1-ipu3-agc.patch` ignores the statistics of the first 8 frames (the AE used to jump to maximum gain and needed ~100 frames
   to come back) and rounds exposure times of 10 ms or more down to a multiple of 10 ms, compensating with analogue gain (flicker of mains lamps).
After: steady luma 136 +- 1, sharpness 696-706, settled ~70 frames (~2 s) after opening (a short damped oscillation remains); the front camera is flat at 135.
Also seen: a rebuilt module from a stale `kmod-build` source had the 800x600 mode again (black 640x480 image): always regenerate the sources
from upstream, which script 02 does.

**Colour: lens shading from the Windows calibration (and why the colour matrices are not shipped).** The vignetting (3.2-3.7x darker in the corners) and the
magenta centre / green edges on white came from the missing lens shading correction. Microsoft's public driver MSI for the Surface Go
(`SurfaceGo_Win10_19042_22.104.24060_WiFi_0.msi`, `msiextract` from msitools) contains the Intel IQStudio calibration (`.cpf`, CPFF container) of every camera module
under `SurfaceUpdate/Drivers/Camera/`. The module of a given device is in its ACPI tables: `LNKn` in the DSDT returns `YHCU` (front, OV5693) and `YHCT` (rear, OV8865), so
the files are `OV5693_YHCU_SKY.cpf` and `OV8865_YHCT_SKY.cpf` (the `MSHW...` files are other Surface models; using them gave worse colours). `tools/cpf_to_tuning.py` decodes
them (layout of the Skylake-era files: AIQB chain at 0x38, records `{size u32, fmt u8, key u8, nid u16}`; nid 10 = lens shading, nid 18 = colour matrices) and writes
`tuning/ipu3/*.yaml` from `tuning/base/*.yaml`; `patches/libcamera-0.7.1-ipu3-lsc.patch` adds the `Lsc` algorithm. Things that had to be measured, not assumed:
- the table has, per light source (5 rear, 4 usable front), 4 channels of a 51x39 (rear) / 41x31 (front) grid of 64 pixel cells of the pixel array, u16 with 12 fractional bits,
  1.0 in the middle; the 4 channels are the quad pixels in **raster order**, so BGGR sensors are B, Gb, Gr, R (I first assumed R, Gr, Gb, B and got red/blue swapped);
- the ImgU shading LUT (`ipu3_uapi_shd_lut`) takes a **12 bit value, gain = 1 + value / 1024** (range [1, 5)); the header comment suggests 16 bits / 16384 and the brightness then
  wraps around at 4096 (coloured rings). Measured with a constant table, and with one entry at a time (`r` really is red, `b` blue);
- ImgU grid = cells of 2^k BDS pixels (k chosen so that the grid has at most 73x56 cells), mapped to the pixel array through the BDS scaling, the (centred) input feeder
  window and the binning. The binning cannot come from `sensorInfo.analogCrop`: the ov8865 driver reports the binned 1632x1224 mode (whole field of view, 2x2 binned) as a 1:1
  crop in the middle of the array, so it is deduced from the ratio active area / sensor output;
- tables of the two light sources around the white point chosen by the AWB are blended (key `1000 * ln(B/G / R/G) + 5000`).
Measured on a uniform white (the PC monitor, rear camera): corner brightness 0.60 -> 1.00 of the centre, corner R/G 0.94 -> 0.98, centre neutral. The colour matrices of the same
calibration (`--ccm`, `patches/libcamera-0.7.1-ipu3-ccm.patch`, 5-6 light sources, Q13 into the ImgU CCM) are decoded and work but are off by default: with the grey-world white
balance they amplify every white balance error (centre magenta (151,143,153) instead of (149,146,150)). The proper way would be a white balance constrained to the measured
illuminant locus, as the Windows driver does. **Black level (shadows crushed to black).** libcamera subtracts a fixed 64 (10 bit) from the data of both sensors ("first rough approximation" in `blc.cpp`). With the lens covered
and the AE frozen at analogue gain 1 and 4 (hooks on `/dev/shm/blfix` and `/dev/shm/agcfix`, scan of the subtracted value), the output only starts to lift below **~5 (R) and ~1-2 (G, B) for
the rear** and **~20 (R) and ~10 (G, B) for the front**; at gain 16 (what the AE picks in the dark) they read about twice as high, so scan at fixed gain. Keys, black mousepad and backpacks lost
all detail because ~50 DN of real signal were thrown away. `patches/libcamera-0.7.1-ipu3-blc.patch` reads `black: [ Gr, R, B, Gb ]` from the tuning (default 64); shipped values rear [1, 5, 1, 1],
front [9, 18, 9, 9] (slightly below the measurement so blacks are not lifted). A finger is a bad cover: skin passes red light, use something opaque for the front (red reads highest there).

**In situ colour calibration (the tables are not enough).** With the Windows tables the luminance was flat but the white balance still turned the centre magenta
(white sheet, rear: R/G falling from 1.0 at the centre to 0.78 at the edge, centre RGB 127 105 110). Same scene, with and without the lens shading: the tables only
cover a fraction of the real red falloff, and since the grey-world AWB measures the whole frame the unevenness comes back as a magenta centre. Every permutation of the table channels
was tried with a hot-swappable hook and none flattened it, so the tables are used as they are and an extra red and blue gain vs radius (`extra:` in the `Lsc` tuning, 8 points of the
BDS-normalised radius, 0 ... 1.4) is fitted on the device: closed loop on a uniform white target (the sheet 3 cm from the lens, uniform light), measure the radial R/G, B/G, multiply
the extra by (1/ratio)^0.6, repeat. The exponent matters: with 1.6 the loop oscillates (AWB reacts to every change, measured response ~1.5x), with 0.6 it converges in 2
iterations. Rear result (`tuning/calibration/ov8865.json`): R/G and B/G 1.00 +- 0.01 at every radius, centre RGB 108 106 109. The extra needed is small (red +20% at the edge,
blue +4%). Front (`tuning/calibration/ov5693.json`, its tables leave the brightness at 0.75 of the centre too, so there is a third extra, `g`, on all channels): before centre RGB 157 130 133, R/G 0.59 at the
edge; after centre 113 110 111, brightness +-3%, B/G flat, R/G within 2% up to ~70% of the radius, then +14% / -5% in the two outermost rings (not a radial effect; the raw loop result is jagged
and is regularised with a polynomial in r^2 and r^4, `tools/focus-test/smooth.py`). The fit is for the light it was done in (cool room light, tables of D55/D65 blended); other lights have not been checked. Procedure (`tools/focus-test/calib.sh`, `prof.sh`; the loop needs a build of the Lsc
algorithm that reads 16 floats from /dev/shm/lscextra every frame): capture 1152x864 via pipewiresrc, ring-average, update.
Still open: black level (libcamera subtracts 64, the calibration has ~6 per channel in a different domain: needs a dark frame), CCM + locus constrained AWB.
Test method that worked: fullscreen white on the PC (`ffplay -fs -f lavfi -i color=c=white:s=3840x2160`) and the camera 3-5 cm from it; a hand-held sheet is useless
(the colour of the light is not uniform either).

**Resolution of the pictures.** The PipeWire plugin lists first the offered size closest to 640x480 and Kamoso (a flatpak, no setting for it) takes the first one, so every picture
was 640x480; the pipeline also only offered sizes up to its 1280x720 default. `patches/libcamera-0.7.1-ipu3-viewfinder-sizes.patch` changes this:
- front (OV5693): a range from 1152x864 (first 4:3 standard size) up to the ImgU maximum;
- rear (OV8865): an explicit list, 1536x1152 first, then 2048x1536 and 3200x2400. The rear 1632x1224 binned mode streams at 30 fps but the ImgU needs 64x32 pixels of margin around the
  picture (`kOutputMargin*`), so the largest ImgU-aligned (multiple of 64 wide) 4:3 size at 30 fps is 1536x1152. Measured fps: 1152x864 30.7, 1536x1152 32, 1600x1200 only 15
  (the margin forces the full 3264x2448 mode), 2048x1536 15, 3200x2400 11. A size range only gets the PipeWire plugin's list of *standard* sizes, none of which is both 4:3 and aligned
  between 1152x864 and 1600x1200, hence the explicit list. Do not offer a size the ImgU has to align (the standard 1400x1050 becomes 1344x1048): the stream then differs from what the
  application negotiated and Kamoso crashes.

**Choosing the picture size (selector).** Camera apps take the first size offered and Kamoso has no setting for it, so the size to offer first is a setting: `min_width` in the camera profile
(see "Live camera profile" below), changed from Surface Control > Cameras (or `surface-camera-mode smooth|high|max` for the rear). Rear: *smooth* 1536x1152 at 30 fps, *high* 2048x1536,
*max* 3200x2400 (8 MP), the last two at 11-15 fps. Front (measured): 1152x864 and 1536x1152 about 28 fps, 2048x1536 about 23 fps, 2560x1920 about 20 fps. At 15 fps the live view looks "drunk"
(the autofocus is also half as fast, it works per frame), so use *smooth* for video calls and live view and a bigger size for photos. A size change restarts WirePlumber: reopen the camera app.

**Live camera profile.** `patches/libcamera-0.7.1-zz-live-profile.patch` adds `include/libcamera/internal/live_profile.h`: the IPU3 IPA and pipeline handler re-read
`~/.config/surface-suite/camera/<sensor>.profile` (ov5693 = front, ov8865 = rear) at most every 200 ms (when its modification time changes), no restart (a gamma change is visible about 300 ms later, measured). Text file, one `key values` per line:
`gamma 1.5`, `contrast 0.3`, `shadows -1..1`, `highlights -1..1` (tone curve, IPA), `exposure <EV>` (auto exposure target, IPA), `black 9 18 9 9`, `bnr 1700 24 4 8 8 10`,
`tnr <min weight 1/256> <threshold>` (`tnr 0 0` = off, software temporal denoise), `saturation 1`, `hue <deg>` (-180..180 is the whole wheel), `hue_spin <deg/s>` (turns the wheel all the time: rainbow effect, measured: mean chroma angle advances steadily at the set speed), `temperature -1..1`, `tint -1..1`, `sharpness 0..3` (software, on the NV12 output after the
denoiser: chroma matrix on the U/V plane, unsharp mask with coring on the luma; free when neutral), `focus <0..1023>` (manual lens position, absent = autofocus; the IPA writes
`/dev/shm/surface-camera-<sensor>.state` with the lens position and sharpness a few times a second), `mirror 1` / `flip 1` (sensor flip on top of the built-in correction, read when the camera is configured),
`min_width <px>` (smallest size offered, read when the camera list is built, so WirePlumber restarts). A key in the profile wins over the tuning file; no profile = the tuned defaults. `<sensor>.session` (first line `pid <N>`) is merged on top while process N lives, for per-app settings (used by the future
camera app). Measured live (front, scene luma): exposure +1/-1 EV: 165/83 vs 111; saturation 0 gives zero chroma; temperature +1 moves U/V to 117/139; mirror 1 correlates 0.89 with the flipped normal frame; manual focus 350 reads back as 350; sharpness 3 raises the Laplacian energy 4.4 -> 6.5. Earlier:  gamma 1.0/2.2 changes mean luma 84/148 vs 116 default within a second; `tnr 0 0` triples the frame-to-frame noise, `tnr 20 20` halves it.

**Volume buttons: holding did not repeat.** `intel-hid` (5-button array) gets ACPI notifications 0xC4/0xC5
(volume up press/release) and 0xC6/0xC7 (down) but the stock driver turns every press into a press+release pair
through `sparse_keymap` autorelease, so KWin sees a tap however long you hold. `patches/intel-hid-volume-hold.patch`
reports the real press on 0xC4/0xC6 and the release on 0xC5/0xC7; a 4 s safety timer releases the key if a release
notification is ever lost. Verified with `/dev/input` (press...release matches the physical hold) and with `wpctl`
(volume keeps moving while held, one short press = one step). Plasma does the repeating itself.

**Stylus battery always 0%.** The ELAN9038 digitizer descriptor declares a Digitizer "Battery Strength" usage (0x3b) that
never carries data, so the kernel creates `hid-0018:04F3:261A.0005-battery-7` (capacity 0, status Unknown). `hid` is built
into the Fedora kernel, so it cannot be patched as a module; `scripts/04-stylus-battery.sh` loads a tiny HID-BPF program
(`udev-hid-bpf`, ships with Fedora) that rewrites that usage to "Undefined". The real pen battery is the Bluetooth
"Surface Pen" one; BLE pens disconnect when idle, so it is listed only while the pen is connected.

**Audio too quiet.** Measured with the internal microphone: 100% to 150% sink volume is +12.3 dB (software gain), the
hardware mixer (ALSA Master) is already at 0 dB at 100%, and the 1 kHz test tone at -12 dBFS does not distort more at 150%.
Music with full-scale peaks will clip digitally at 150%. Settings applied: `~/.config/plasmaparc` with
`RaiseMaximumVolume=true` (keys/slider reach 150%) and `VolumeStep=5`. A limiter (EasyEffects flatpak or a LADSPA/LV2 limiter)
would allow even more loudness without clipping; none is installed.

**Speaker scale (user decision).** The loudest level measured without extra distortion was the old 150% sink volume, so a virtual
filter-chain sink (`tuning/pipewire/10-speaker-gain.conf`) applies a fixed +4.75 dB (gain 1.728 = (1.5/1.25)^3) and makes the displayed
**125%** equal that level (measured: -16.3 dBFS vs -15.3 dBFS for the old 150%). The physical sink stays at 100%. Plasma only offers
100% or 150% as maximum, so 126-150% is possible but beyond the tested range (THD grows). Headphones share the same sink, so the
boost applies to them too: keep the volume lower there.

**Microphone too sensitive.** PipeWire's 100% source volume sets ALSA Capture +30 dB *and* Internal Mic Boost +30 dB (+60 dB): an empty room
measured -6.8 dBFS RMS with peaks at 0 dBFS. The physical source is kept low (`wpctl set-volume <source> 0.20` = Capture +18 dB (0.25 = +23.5 dB clipped on normal speech at 40 cm),
boost 0, remembered by WirePlumber) and `tuning/pipewire/20-mic-filter.conf` adds a virtual "Built-in Microphone (filtered)" (WebRTC noise
suppression + high-pass) as default source. Copy both files to `~/.config/pipewire/pipewire.conf.d/` and restart pipewire/wireplumber.

**Trackpad sometimes missing after boot.** The keyboard cover is USB 045e:09b5; its trackpad interface is first grabbed by `hid-generic`
and then taken over by the `hid-multitouch` module. All 6 boots logged so far were fine, so the failure was not reproduced;
`tools/folio-heal.sh` (+ `.service`, installed in `/usr/local/sbin` and `/etc/systemd/system`, started by the udev rule `tools/99-folio-heal.rules` in `/etc/udev/rules.d` every time the cover appears, at boot or when attached later) waits for the trackpad to be bound to
hid-multitouch, and if not, logs the state (`journalctl -t folio-heal`) and re-enumerates the USB device (`authorized` 0 -> 1, the software
equivalent of unplugging the cover; tested: the trackpad comes back bound to hid-multitouch). If it ever triggers, the log shows the cause.

**Touch sensitivity.** `hid-multitouch` exposes no sensitivity parameter for the ELAN9038 digitizer; libinput only offers the
calibration matrix (identity now). Nothing to tune unless a concrete symptom (ghost touches, offsets) shows up.

### Hold-to-repeat volume keys can be switched off

The patched `intel_hid` has a module parameter `volume_hold` (default on). Surface Control shows it as a switch on the Audio page; from a
terminal: `sudo tools/volume-hold.sh on|off|status`. The choice is stored in `/var/lib/local-kmods/volume_hold` and is passed to the module by
the modprobe rule that `scripts/02-build-and-install.sh` installs.

### Surface Pen

The pen's side button is `BTN_STYLUS` and the eraser end is `BTN_TOOL_RUBBER` on the touchscreen device. The button on the flat end is Bluetooth only:
click = `Meta+F20`, double-click = `Meta+F19`, hold = `Meta+F18` (the Windows mapping), from the "Surface Pen Keyboard" input device. If the pen shows
"Connected" in `bluetoothctl` but `ServicesResolved` stays `false` and no "Surface Pen Keyboard" device exists, the bond is stale: `bluetoothctl remove <addr>`,
hold the flat-end button for 5-7 s (white LED blinking) and pair again. `tools/pen-capture.py [barrel|tip|eraser|detonator]` records what each part sends.

### Front camera mirror / flip (ov5693)
The ov5693 driver reports neither a Bayer order change nor a binned-mode limit for its flips, and both bite: with only one of mirror/flip on the picture turned purple (the Bayer order
becomes GBRG, measured with the chroma of a flipped reference frame: GBRG correlates +0.3..0.5, the other three orders are about 0 or give the purple cast), and in the binned modes
(1296x972, used for outputs up to 1152x864) any flip gives no data at all (`ipu3-cio2: payload length is ..., received 0`, black picture). `patches/libcamera-0.7.1-zz-live-profile.patch` therefore
(a) declares GBRG to the ImgU input when exactly one flip is on (the raw layout is identical, only the declared order differs; the CIO2/CSI-2 side keeps BGGR so link validation still passes) and
(b) forces the full 2592x1944 sensor mode when a flip is on (the ImgU scales down: 1152x864 flipped runs at about 27 fps). Checked at 1152x864 and 2560x1920: mean U/V stay at 128, both flips and none unchanged.
The rear camera (ov8865) flags its flips correctly and needed nothing.

## Surface Control (suite/control)
PySide6 + Kirigami app (native on Kinoite, no layering), no title bar of its own, minimum size of 38 x 26 grid units, window geometry restored after the full-screen key test.
- **Patches and modules** (was Overview): every check opens a page (what it does, how it works, what to do), no explanations in the list.
- **Cameras**: fixed 4:3 preview (no black bars) that starts by itself, scrolling editor in titled boxes (Focus, Output, Light, Colour, Detail, Geometry), a switch to hide the explanations,
  every value is a field you can click and type in (decimal comma, minus, unit, percent; out of range is clamped, text is refused), per-control reset, manual focus with sharpness meter,
  rainbow (hue_spin), a little Wikipedia button next to every setting that has a page, and **presets per camera** (`~/.config/surface-suite/presets/<front|rear>/<name>.json`: apply, save as, update, rename, duplicate, delete; the active one is shown).
- **Keyboard cover**: live attached/disconnected state, reset, keyboard + trackpad test (layout read from the system through libxkbcommon, rows of the ISO Surface cover; Plasma shortcuts blocked through
  `org.kde.KGlobalAccel.blockGlobalShortcuts` with a watcher that unblocks them if the app dies; full screen; hold Esc to leave).
- **Audio**: volume, **output equaliser** (`suite/control/eq.py`, `qml/EqEditor.qml`): ten parametric bands on the speaker filter chain (biquads `bq_peaking/lowshelf/highshelf/highpass/lowpass` whose Freq/Q/Gain are set live
  with `pw-cli set-param`; bq_raw cannot be used, in PipeWire 1.6 it takes its coefficients from the config, not from controls), a graph with draggable handles, pre-amplifier, speaker boost, built-in and own presets in one list,
  import and export of Equalizer APO / AutoEQ text files (the format AutoEQ, Equalizer APO and EasyEffects share), and a tick box to use the same settings for the headphone jack (the jack is a port of the same card, so the chain
  serves both; with the box off each output has its own set and `suite/control/audio_route.py`, a user service on `pactl subscribe`, applies the set of the port in use). Speaker test with short desktop sounds
  (`audio-channel-front-left/right.oga` through `pw-play --channel-map`) and a 40 Hz to 16 kHz sweep. "Verify the settings are applied" reads the running filter chains back and compares them with what is saved.
  The graph and the band editor appear with the Advanced switch (without it: presets and the boost); the graph uses pointer handlers that take a drag over from the scrolling page, so a finger can move the dots.
  Built-in presets can be deleted (with a warning); the install script brings them back (`suite/control/restore_defaults.py`) and never touches custom ones. Microphone: test right under the device, enhancer filter chain with one preset list (built-in and yours), gain / low cut / bass / presence / treble.
  The first enabling of the equaliser or the enhancer restarts PipeWire (a module loaded with `pw-cli load-module` vanishes with the client). Unit tests of the maths and the file format: `suite/control/tests/test_eq.py`.
- **NFC**: tags shown in the window while the page is open (pid in `$XDG_RUNTIME_DIR/surface-nfc-window`, `nfc-notify` then skips the desktop notification), reader test with read and delivery times.
- **Stylus and touch**: pen test canvas (pressure, tilt, eraser end, side/top buttons, from the raw Qt tablet events through an event filter; Qt Quick items do not get tilt), Bluetooth pen state
  and battery from BlueZ, a tick box for the HID-BPF filter that hides the fake stylus battery (`tools/stylus-filter.sh` through polkit, then a popup with a countdown and Restart now). Buttons shown: Barrel and Rubber (top).
- **Sensors and battery**: ambient light read about 16 times a second (the hub updates at 10 Hz), accelerometer and gyro bars,
  battery, and "About this tablet": firmware, display name and its manufacture week and year (from the EDID: the best age hint), battery model and capacity, the disk the system is on, CPU, memory, install date.
The enhancer needs a restart of the sound server the first time (a module loaded with `pw-cli load-module` disappears with the client that loaded it).

## Gotchas learned the hard way

- `/dev/shm` (tmpfs) has a quota: long test runs that keep raw frames fill it and `cam --file` then writes empty files ("Disk quota exceeded"). Delete test frames afterwards.

- **Never unload camera/NFC modules by hand (`modprobe -r`/`rmmod`): reboot instead.** `nxp_nci_i2c` also hangs when removed
  (`rmmod` stuck in `D` state inside `nxp_nci_close`) and then blocks the shutdown, needing a forced power-off.
- **Never `modprobe -r ipu3_imgu`.** It oopses (`imgu_css_irq_ack`), the module hangs in `(C-)` state and the
  next reboot hangs; only a forced power-off recovers. Reboot instead of reloading camera modules.
- **Stop WirePlumber while testing with `cam`:** `systemctl --user stop wireplumber`, restart it afterwards.
  Both fight for the same camera otherwise (`Failed to setup link ... Device or resource busy`).
- **`timeout -s KILL toolbox run ... cam` leaves the `cam` process alive inside the container** and it keeps the
  camera busy. Put `timeout` inside: `toolbox run -c NAME timeout -s KILL 40 cam ...`.
- **`pkill -f name` over ssh kills your own ssh shell** when the command line contains that name (it happened again: use `pkill -x name`).
- **Do not run `plasmalogin --example-config` to read the config**: it hangs and leaves a second login-manager process behind. Read
  `/etc/plasmalogin.conf` (all commented) and put overrides in `/etc/plasmalogin.conf.d/*.conf`.
- Autologin (Plasma Login Manager): `[Autologin]` with `User=<you>` and `Session=plasma.desktop` in `/etc/plasmalogin.conf.d/10-autologin.conf`, or
  System Settings > Login Screen. Without a desktop session the cameras/NFC notifications do not work and camera devices have no ACL.
- `gst-launch-1.0 libcamerasrc camera-name=...` needs the backslash doubled and hung for me; use `cam`.
- **Camera device permissions only exist for the user with an active desktop session** (uaccess ACLs). Right after a reboot, before
  anyone logs in, `cam` over ssh fails with `Unable to populate media device ... Permission denied`. For a test without logging in:
  `sudo setfacl -m u:$USER:rw /dev/media* /dev/video* /dev/v4l-subdev*` (reset by the next reboot).
- Stress test that reproduces the WirePlumber crashes (run in a toolbox with `pipewire-gstreamer`): loop of
  `gst-launch-1.0 -q pipewiresrc target-object=libcamera_input.__SB_.PCI0.LNK$N num-buffers=$K ! videoconvert ! videoscale ! video/x-raw,width=$W,height=$H ! fakesink`
  with N in {0,1}, overlapping sessions and W x H drawn from 320x240, 640x480, 1280x720, 1920x1080, 800x600, 640x360 ...;
  then `coredumpctl list --since <start>`.
- Dynamic debug (`/sys/kernel/debug/dynamic_debug/control`) is blocked by lockdown.
- **Kernel NFC: a tag opened through a raw socket stays "active" until you deactivate it** (see 3b). If polling stalls with
  `there is an active target` in dmesg, that is the cause.
- To debug the NFC daemon: `journalctl -u nfc-daemon -f` (one line per tag, with read time) and
  `journalctl --user -u nfc-notify -f`.
- `wpctl status` shows no cameras until someone is logged in on the desktop (the libcamera monitor needs an
  active seat session); on the login screen the check in `03-verify.sh` is skipped for that reason.
- The NFC I2C address ACKs only while the chip is powered. If `write` returns `EREMOTEIO` the enable line is low
  (this is how I found the GPIO order was firmware=1, enable=2: with the roles swapped the chip stayed off).
- `mokutil` password entry needs a real terminal; the script uses `--hash-file` so it is non-interactive.
- The firmware may already trust old keys from earlier installs (`linux-surface`, `ublue`, `rEFInd` keys showed
  up in the platform keyring). Harmless, but `keyctl list %:.platform` shows what is trusted.

## Tried and rejected

- **Longer exposure on the rear camera by raising `vts` in the ov8865 mode table** (`rejected/ov8865-default-30fps.patch.REJECTED`).
  The rear sensor's 1632x1224 mode (the one used for 720p) has `vts=1248, hts=1923` at 288 MHz = 8.3 ms per frame, i.e. it
  runs at ~120 fps, and libcamera's IPU3 IPA takes the maximum exposure from the sensor's exposure control range at configure
  time (there is even a `\todo take VBLANK into account` in `src/ipa/ipu3/ipu3.cpp`). So the rear camera can never expose longer
  than 8.3 ms and makes up with gain in dim light. Making the driver default 30 fps (`vts=4992`) makes libcamera see a 33 ms
  limit, but only if the current VBLANK *value* follows the default; when I made it follow, the sensor started sending long
  packets outside the frame boundaries (`ipu3-cio2: CSI-2 receiver port 0: inter-frame long packet discarded` flood) and the
  stream stalled after one frame. Without making the value follow, AE believed in 33 ms while the sensor did 8 ms and ran the
  gain away (black image). A working fix has to set VBLANK from libcamera (FrameDurationLimits) and needs the sensor timing
  understood; not done.
- **A reference chart for colour tuning**: not useful yet, because libcamera 0.7.x's IPU3 IPA has no colour-correction-matrix
  algorithm to apply the result to (only white balance and gamma).
- Forcing `vertical_blanking` from userspace on the rear sensor (v4l2-ctl while streaming): 100/300/600/1200/2400 work (frame
  rate falls as expected), but 3768 (30 fps in the 1632x1224 mode) floods `ipu3-cio2: CSI-2 receiver port 0: inter-frame long packet
  discarded` (6000 errors in 4 s). Leave the value at 22 afterwards: `v4l2-ctl -d /dev/v4l-subdevN --set-ctrl vertical_blanking=22`
  (it persists until the module is reloaded and libcamera does not reset it).
- Moving the AE frame-context ring size, removing `Af` for a sensor without lens, CPU governor `performance`: no fix for the AE kicks.
- neard for NFC (see 3b) and the NXP `nxpnfc`/`libnfc-nci` stack.

## Debug commands

```bash
media-ctl -d /dev/media0 -p                       # sensors must have links to ipu3-csi2
cam -l                                             # in the toolbox (libcamera-tools): lists 2 cameras
cam -c 1 --capture=10 --file=/tmp/f-#.bin          # rear=1, front=2; NV12
wpctl status                                       # "Built-in Front/Back Camera" under Video
ls /sys/class/nfc/                                 # nfc0
journalctl -u nfc-daemon -f                        # NFC daemon log, one line per tag
sudo systemctl stop nfc-daemon; sudo python3 tools/nfc_poll.py 60   # raw kernel-NFC poll, prints tag UID
sudo cat /proc/modules | grep -E 'ov8865|nxp_nci'  # "(O)" = our out-of-tree build is loaded
```

## Files

```
scripts/01-upgrade-and-mok.sh    upgrade, create MOK key, queue enrollment
scripts/02-build-and-install.sh  build/sign/install ov8865 + nxp-nci (core + i2c), modprobe rules, NFC services
scripts/03-verify.sh             health check
scripts/04-stylus-battery.sh     optional: HID-BPF fix for the fake 0% stylus battery
tuning/ipu3/*.yaml               libcamera exposure tuning for the two sensors
patches/libcamera-0.7.1-ipu3-crash-fixes.patch  fixes WirePlumber aborts/segfaults (IPU3 pipeline)
patches/libcamera-0.7.1-ipu3-blc.patch    black level from the tuning instead of a fixed 64
patches/libcamera-0.7.1-ipu3-lsc.patch    Lens shading (ImgU shd block) from the calibration tables
patches/libcamera-0.7.1-ipu3-ccm.patch    Awb applies colour matrices from the tuning (not used by the shipped tuning)
patches/libcamera-0.7.1-ipu3-viewfinder-sizes.patch  offered sizes: 1152x864 and up
tools/cpf_to_tuning.py            Windows .cpf calibration -> libcamera tuning (lens shading, optional colour matrices)
tuning/base/*.yaml                tuning that works with the stock libcamera; tuning/ipu3/*.yaml = base + lens shading (needs the patched libcamera)
patches/libcamera-0.7.1-af-robust-scan.patch    autofocus: wait for AE, Y1 statistic, global maximum, bigger grid (see README)
patches/libcamera-0.7.1-sensor-delays.patch     ov5693/ov8865 sensor delays 2,2 (AE was oscillating with the defaults)
patches/ov8865-pixel-rate.patch      real pixel rate (72 MHz) for the binned mode: libcamera exposure times were 4x too short
patches/ov8865-analogue-gain-step.patch  analogue gain step 1 instead of 128 (whole multiples of 1x made the picture flash)
patches/libcamera-0.7.1-ipu3-agc.patch  AGC: skip the first 8 frames, exposure multiple of 10 ms (flicker)
patches/ov8865-drop-svga-mode.patch  removes the 800x600 mode (8 ms frames) so 640x480 requests do not get a 2.7 ms exposure limit
patches/ov5693-cap-30fps.patch       front camera default timing capped at 30 fps (exposure limit 33 ms instead of 16.5 ms at 640x480)
patches/nxp-nci-i2c-read-retry.patch  NACKed NCI reads are retried and no longer latch hard_fault (stalled NFC for a minute)
patches/ov8865-stale-mode.mbox   linux-surface fix (2 commits) for the rear camera
patches/nxp-nci-add-NXP3001.patch  ACPI id for the NFC controller
patches/nxp-nci-poll-period.patch  polling period 250 ms (NCI TOTAL_DURATION) via post_setup
patches/intel-hid-volume-hold.patch  device volume buttons: press/hold/release (hold keeps changing the volume)
patches/hid-bpf/*.bpf.c          HID-BPF program hiding the digitizer's fake battery
tools/folio-heal.sh + .service + 99-folio-heal.rules   attach-time check/recovery for the keyboard cover trackpad (installed by step 2)
tuning/pipewire/*.conf           speaker gain scale and filtered microphone
tools/make_focus_chart.py        generates samples/focus-chart-A4.{svg,pdf} (print at 100%)
tools/nfc-daemon.py + .service   the always-on NFC reader (system service)
tools/nfc-notify.py + .service   sound + desktop notification (user service)
tools/nfc_poll.py                minimal netlink NFC poller for debugging
tools/nfc_latency.py             detection latency test straight against the kernel
```

## What this changes on the system (to undo it)

- `/etc/modprobe.d/ov8865-local.conf`, `/etc/modprobe.d/nxp-nci-local.conf`, `/etc/modprobe.d/nxp-nci-core-local.conf`
- `/etc/systemd/system/local-nxp-nci.service` and `nfc-daemon.service` (enabled), `/var/lib/nfc-daemon/`
- user service `~/.config/systemd/user/nfc-notify.service`, `~/.local/bin/nfc-notify`
- `/var/lib/local-kmods/*.ko`
- `/etc/libcamera/ipa/ipu3/ov5693.yaml`, `ov8865.yaml`
- `/usr/local/libcamera-patched/` and `~/.config/systemd/user/wireplumber.service.d/patched-libcamera.conf` (patched libcamera for WirePlumber)
- MOK entry "Surface Go local module signing" (`mokutil --delete` on `~/mok/MOK.der`)
- a toolbox called `surface-build`
- temporary while experimenting: a NOPASSWD sudoers file, remove it: `sudo rm /etc/sudoers.d/99-claude-test`

## After a kernel update

The patched modules are built per kernel version. After `rpm-ostree` boots a new kernel the modprobe rules silently fall back to the stock modules: the rear
camera then shows a green picture (stale sensor mode, wrong pixel rate; dmesg shows `ipu3-cio2: payload length is ..., received ...`). Fix: run
`scripts/02-build-and-install.sh` again on the Surface and reboot. Seen on 7.2.7 -> 7.2.8; that kernel also moved an `#include` in `intel/hid.c`, which the script now handles.

## License

MIT (see `LICENSE`) for the scripts, Surface Control and the documentation. The patches in `patches/` keep the license of the project they modify (libcamera: LGPL-2.1+, Linux kernel: GPL-2.0).
