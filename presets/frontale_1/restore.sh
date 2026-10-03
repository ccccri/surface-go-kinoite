#!/bin/bash
# Restore the "frontale_1" preset (front camera as accepted on 2026-10-02): copies the preset files over the guide's
# tuning/patches/tools. Afterwards re-run scripts/02-build-and-install.sh on the Surface (rebuilds libcamera with these
# patches and installs the front tuning) and reboot. Nothing outside the guide directory is touched by this script.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
GUIDE=$(cd "$HERE/../.." && pwd)
echo "Restoring preset $(basename "$HERE") into $GUIDE"
cp -v "$HERE"/tuning/base/ov5693.yaml        "$GUIDE"/tuning/base/
cp -v "$HERE"/tuning/ipu3/ov5693.yaml        "$GUIDE"/tuning/ipu3/
cp -v "$HERE"/tuning/calibration/ov5693.json "$GUIDE"/tuning/calibration/
cp -v "$HERE"/patches/*.patch                "$GUIDE"/patches/
cp -v "$HERE"/tools/cpf_to_tuning.py         "$GUIDE"/tools/
echo
echo "Now run: $GUIDE/scripts/02-build-and-install.sh   (then reboot)"
echo "To only reinstall the front tuning without rebuilding: sudo install -m 644 $GUIDE/tuning/ipu3/ov5693.yaml /etc/libcamera/ipa/ipu3/ && systemctl --user restart wireplumber"
