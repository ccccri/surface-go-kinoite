#!/bin/bash
# Step 3 (run ON the Surface Go after the reboot): checks that cameras and NFC are wired up.
K=$(uname -r)
ok()   { printf '  [ok]   %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; }
check() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

echo "Kernel: $K"
echo "Cameras"
check "ov5693/ov8865/ov7251 bound"            'grep -q ov8865 /proc/modules && grep -q ov5693 /proc/modules'
check "dw9719 (autofocus) bound"               'grep -q "^dw9719" /proc/modules'
check "ov8865 is the local patched build (O)"  'grep "^ov8865" /proc/modules | grep -q "(O)"  || grep -q hw_mode /usr/lib/modules/$(uname -r)/kernel/drivers/media/i2c/ov8865.ko.xz'
# a real desktop login is a seat0 session whose class is not "greeter"
if loginctl list-sessions --no-legend | awk '$4 == "seat0" && $6 != "greeter" { f = 1 } END { exit !f }'; then
    check "PipeWire sees the cameras"          'wpctl status | grep -q "Built-in Back Camera" && wpctl status | grep -q "Built-in Front Camera"'
else
    echo "  [skip] PipeWire camera check: nobody is logged in graphically (log in and run again)"
fi
echo "Camera image quality (patched libcamera and tuning)"
if command -v v4l2-ctl >/dev/null 2>&1; then
    check "ov8865 reports the real pixel rate (72 MHz binned mode)"  'r=1; for d in /sys/class/video4linux/v4l-subdev*; do grep -q ov8865 $d/name && v4l2-ctl -d /dev/$(basename $d) -C pixel_rate 2>/dev/null | grep -q "72000000" && r=0; done; [ $r = 0 ]'
else
    echo "  [skip] ov8865 pixel rate check: v4l2-ctl (v4l-utils) is not installed"
fi
check "patched libcamera installed"            'test -f /usr/local/libcamera-patched/lib/libcamera/ipa/ipa_ipu3.so'
check "WirePlumber uses the patched libcamera" 'systemctl --user show wireplumber -p Environment | grep -q libcamera-patched'
check "tuning has the lens shading tables"     'grep -q "^  - Lsc:" /etc/libcamera/ipa/ipu3/ov5693.yaml && grep -q "^  - Lsc:" /etc/libcamera/ipa/ipu3/ov8865.yaml'
# the first size is the one the rear profile asks for (min_width, set in Surface Control > Cameras): 0 = 1536x1152
RW=$(sed -n 's/^min_width *\([0-9]*\).*/\1/p' "$HOME/.config/surface-suite/camera/ov8865.profile" 2>/dev/null); case ${RW:-0} in 2048) RSIZE=2048x1536;; 2560) RSIZE=2560x1920;; 3200) RSIZE=3200x2400;; *) RSIZE=1536x1152;; esac
check "first size offered to applications (rear) is $RSIZE" 'id=$(pw-cli ls Node 2>/dev/null | grep -B8 LNK0 | grep "^	id" | tail -1 | awk "{print \$2}" | tr -d ,); pw-cli enum-params $id EnumFormat 2>&1 | grep Rectangle | head -1 | grep -q '"$RSIZE"
echo "NFC"
check "nxp_nci_i2c is the local build (O)"     'grep "^nxp_nci_i2c" /proc/modules | grep -q "(O)"'
check "nxp_nci core is the local build (O)"    'grep "^nxp_nci " /proc/modules | grep -q "(O)"'
check "driver bound to NXP3001:00"             'readlink /sys/bus/i2c/devices/i2c-NXP3001:00/driver | grep -q nxp-nci_i2c'
check "/sys/class/nfc/nfc0 exists"             'test -d /sys/class/nfc/nfc0'
check "nfc-daemon running (enabled at boot)"   'systemctl is-active --quiet nfc-daemon && systemctl is-enabled --quiet nfc-daemon'
check "nfc-notify (user service) running"      'systemctl --user is-active --quiet nfc-notify'
echo
echo "Try a tag:   put an NFC tag on the back: you should hear a sound and get a notification (log: journalctl -u nfc-daemon -f)"
echo "Try cameras: install Kamoso or Snapshot from Discover"
