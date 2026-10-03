# Preset `frontale_1` - front camera (OV5693, module YHCU) as accepted on 2026-10-02

Snapshot of everything that shapes the picture of the **front** camera, taken when the owner called the result "quite good" (grain much reduced, colours
correct, a slight magenta residue in the corners). Use it as a restore point while the rear camera is being worked on.

## Contents
- `tuning/base/ov5693.yaml`, `tuning/ipu3/ov5693.yaml` (the one installed in `/etc/libcamera/ipa/ipu3/`), `tuning/calibration/ov5693.json` (the input of `tools/cpf_to_tuning.py`).
- `patches/`: all libcamera 0.7.1 patches and the ov5693 kernel patch as they were (the libcamera code is shared with the rear camera: Lsc, blc/bnr, tone mapping, temporal denoise, agc, af, crash fixes, sensor delays, viewfinder sizes, ov8865 hflip).
- `tools/cpf_to_tuning.py`: the generator of the tuning from the Windows calibration + the JSON.
- `restore.sh`: copies all of this back into the guide (then re-run `scripts/02-build-and-install.sh`).

## Settings of the front camera in this preset
| Area | Value | Where |
|---|---|---|
| Lens shading | Windows YHCU tables (4 light sources, 41x31 cells) + in situ extra: R/B by radius, overall gain (g) capped at 1.4 | `ov5693.json` `r`, `b`, `g` |
| Black level | Gr 9, R 18, B 9, Gb 9 (measured with the lens covered, slightly below) | `black` |
| Bayer noise reduction | cf 1700, cg 24, alpha 4, beta 8, gamma 8, max_inf 10 | `bnr` (blc patch) |
| Tone curve | gamma 1.5, contrast 0.3; AE target 0.22, shadow constraint 0.10 | `tone` (tonemapping patch) |
| Temporal denoise (software) | min weight 48/256, threshold 12 levels, NV12 Y and UV; `LIBCAMERA_IPU3_TNR="<w> <t>"` overrides, `"0 0"` disables | `ipu3-temporal-denoise.patch` |
| White balance | grey world (libcamera Awb), no colour matrix | base yaml |
| AE | exposure >= 10 ms in multiples of 10 ms (50 Hz flicker), skip first 8 frames | `ipu3-agc.patch` |
| Size | 1152x864 first, up to the ImgU maximum | `ipu3-viewfinder-sizes.patch` |
| Sensor | default timing capped at 30 fps | `ov5693-cap-30fps.patch` |

## State when saved
Temporal noise (12 frames, 16x16 blocks, stationary scene, dim room): 0.4-0.7 levels per pixel with the temporal denoiser (1.4-1.7 without). Known issues left: slight magenta in
the corners, some noise on dark walls between window and wall, skin looks very smooth ("beauty filter") because of the temporal denoiser.
