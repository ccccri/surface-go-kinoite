# Rear camera autofocus test tools

Used with the printed chart (`samples/focus-chart-A4.pdf`) fixed in front of the rear camera.

- `afhook.py`   patches a libcamera 0.7.1 source tree (`src/ipa/ipu3/algorithms/af.cpp`) with a TEST HOOK: while `/dev/shm/afpos` exists the
  lens is frozen at the step written in it, and the AF variance is logged at every frame. Build the tree, then point a stock `cam` at the
  resulting IPA with `LIBCAMERA_IPA_MODULE_PATH=<tree>/build/src/ipa/ipu3` (unsigned modules run isolated, that is fine).
  Do NOT install a build with this hook.
- `hooksweep.py`  sweeps the lens positions with the hook and prints sharpness (mean squared gradient of the star / chart) against the position.
- `aftrials.py`   restarts the real autofocus N times and prints where it settles and how sharp the last frame is.
Stop WirePlumber (`systemctl --user stop wireplumber`) first, the camera can only be opened by one process.

## In situ colour calibration (lens shading extra gain)
- `lsc.cpp.calibration-hook`: `src/ipa/ipu3/algorithms/lsc.cpp` of the guide's patch plus a test hook that reads 16 floats (red then blue extra gain, 8 points of the
  BDS-normalised radius each) from `/dev/shm/lscextra` every frame. Replace the file in a libcamera 0.7.1 build tree, build, and run WirePlumber from that build tree
  (`LD_LIBRARY_PATH`, `LIBCAMERA_IPA_MODULE_PATH`, `LIBCAMERA_IPA_PROXY_PATH`, and `LIBCAMERA_IPA_CONFIG_PATH=/etc/libcamera/ipa` or the tuning is ignored).
- `calib.sh LNK0|LNK1 <iterations> <power>`: closed loop on a uniform white target (power 0.6 converges; 1.6 oscillates). Prints the radial R/G, B/G, G profiles per iteration and the final
  16 values (also saved in `/tmp/lscextra.<LNK>`): put them in `tuning/calibration/<sensor>.json`.
- `prof.sh LNK0|LNK1`: the same profile once, with the installed tuning.

## Autofocus accuracy tests (static scene, textured object at ~30 cm, Surface on its kickstand)
- `afhook2.py <tree>/src/ipa/ipu3/algorithms`: adds a TEST HOOK to af.cpp: while `/dev/shm/afpos` exists the lens is frozen at that step and "HOOK <step> <variance>" is logged. Never install such a build.
- `afsweep.sh <label> [max] [step]`: steps the frozen lens through the range and prints image sharpness (gradient energy of a centre crop) and the AF statistic per position.
- `aftrial2.sh "<start steps>"`: forces the lens to each start position, releases it and prints where the real autofocus settles.
