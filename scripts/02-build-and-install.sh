#!/bin/bash
# Step 2 (run ON the Surface Go, as your normal user, AFTER the MOK key is enrolled).
# Also re-run this after every kernel update: the modules are built per kernel version.
#
# Builds, signs and installs two kernel modules and sets up userspace NFC:
#   * ov8865   rear camera: fixes the stale sensor mode that turns the picture into green stripes, and reports the real pixel rate
#              (libcamera computed every exposure time 4x too short) and allows fractional analogue gains
#              when something (WirePlumber) keeps the autofocus subdevice open
#   * nxp-nci_i2c   NFC: stock kernel driver + the ACPI id NXP3001 used by the Surface Go
#   * libcamera tuning files for both sensors (much better exposure, see tuning/ipu3/*.yaml)
#   * intel-hid  device volume buttons: press/hold/release (hold = keep changing the volume)
#   * nxp-nci  NFC core with a shorter polling period (250 ms instead of the NCI default 1000 ms)
#   * nfc-daemon + nfc-notify   always-on tag reader (system service) and desktop sound/notification (user service)
#
# Modules go to /var/lib/local-kmods (/usr is read-only on Kinoite) and are loaded through
# /etc/modprobe.d "install" rules that fall back to the stock module if the local file is missing
# (for example right after a kernel update), so a kernel update never breaks the boot.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
K=$(uname -r)                                   # e.g. 7.2.7-200.fc44.x86_64
UPSTREAM_TAG=v${K%%-*}                          # e.g. v7.2.7
MOKDIR=${MOKDIR:-$HOME/mok}
TB=${TB:-surface-build}
WORK=$HOME/kmod-build/$K
KDIR=/usr/src/kernels/$K
DEST=/var/lib/local-kmods

say() { printf '\n== %s\n' "$*"; }

[ -f "$MOKDIR/MOK.priv" ] && [ -f "$MOKDIR/MOK.der" ] || { echo "No MOK key in $MOKDIR: run 01-upgrade-and-mok.sh first"; exit 1; }
# capture first: "mokutil | grep -q" under pipefail fails with SIGPIPE when grep exits early
TEST=$(mokutil --test-key "$MOKDIR/MOK.der" 2>&1 || true)
grep -q "is already enrolled" <<<"$TEST" \
    || { echo "The MOK key in $MOKDIR is not enrolled yet (blue screen at boot; after a reinstall run 01-upgrade-and-mok.sh again). Aborting."; exit 1; }

say "Build container ($TB) and kernel headers for $K"
toolbox list --containers 2>/dev/null | grep -qw "$TB" || toolbox create -y "$TB"
toolbox run -c "$TB" sudo dnf install -y "kernel-devel-$K" gcc make git curl openssl elfutils-libelf-devel

say "Fetching upstream $UPSTREAM_TAG sources"
rm -rf "$WORK"; mkdir -p "$WORK/ov8865" "$WORK/ov5693" "$WORK/nxp-nci" "$WORK/nxp-nci-core" "$WORK/intel-hid"
get() { curl -fsSL "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/$1?h=$UPSTREAM_TAG" -o "$2"; }
get drivers/media/i2c/ov8865.c "$WORK/ov8865/ov8865.c"
get drivers/media/i2c/ov5693.c "$WORK/ov5693/ov5693.c"
get drivers/nfc/nxp-nci/i2c.c  "$WORK/nxp-nci/i2c.c"
get drivers/nfc/nxp-nci/nxp-nci.h "$WORK/nxp-nci/nxp-nci.h"
get drivers/nfc/nxp-nci/core.c "$WORK/nxp-nci-core/core.c"
get drivers/nfc/nxp-nci/firmware.c "$WORK/nxp-nci-core/firmware.c"
cp "$WORK/nxp-nci/nxp-nci.h" "$WORK/nxp-nci-core/nxp-nci.h"
get drivers/platform/x86/intel/hid.c "$WORK/intel-hid/hid.c"
# newer kernels include a header from the parent directory; build out of tree with a local copy
get drivers/platform/x86/dual_accel_detect.h "$WORK/intel-hid/dual_accel_detect.h" 2>/dev/null || true

BUILD_OV8865=1; BUILD_OV5693=1; BUILD_NCI=1; BUILD_CORE=1; BUILD_HID=1
if grep -q post_setup "$WORK/nxp-nci-core/core.c"; then
    echo "nxp-nci core: upstream already has a post_setup hook, not building the poll-period patch."; BUILD_CORE=0
fi
if grep -q hw_mode "$WORK/ov8865/ov8865.c"; then
    echo "ov8865: upstream already contains the stale-mode fix, not building it."; BUILD_OV8865=0
fi
if grep -q NXP3001 "$WORK/nxp-nci/i2c.c"; then
    echo "nxp-nci: upstream already knows NXP3001, not building it."; BUILD_NCI=0
fi

say "Patching"
if [ $BUILD_OV5693 = 1 ]; then
    if (cd "$WORK/ov5693" && mkdir -p drivers/media/i2c && cp ov5693.c drivers/media/i2c/ov5693.c \
            && git apply "$HERE/patches/ov5693-cap-30fps.patch" && cp drivers/media/i2c/ov5693.c ov5693.c \
            && rm -rf drivers && printf 'obj-m += ov5693.o\n' > Kbuild); then :; else
        echo "ov5693: patch does not apply (probably fixed upstream), not building it."; BUILD_OV5693=0
    fi
fi
if [ $BUILD_OV8865 = 1 ]; then
    (cd "$WORK/ov8865" && mkdir -p drivers/media/i2c && cp ov8865.c drivers/media/i2c/ov8865.c \
        && git apply "$HERE/patches/ov8865-stale-mode.mbox" \
        && git apply "$HERE/patches/ov8865-drop-svga-mode.patch" \
        && git apply "$HERE/patches/ov8865-pixel-rate.patch" \
        && git apply "$HERE/patches/ov8865-analogue-gain-step.patch" && cp drivers/media/i2c/ov8865.c ov8865.c \
        && rm -rf drivers && printf 'obj-m += ov8865.o\n' > Kbuild)
fi
if [ $BUILD_NCI = 1 ]; then
    (cd "$WORK/nxp-nci" && mkdir -p drivers/nfc/nxp-nci && cp i2c.c drivers/nfc/nxp-nci/i2c.c \
        && git apply "$HERE/patches/nxp-nci-add-NXP3001.patch" \
        && git apply "$HERE/patches/nxp-nci-i2c-read-retry.patch" && cp drivers/nfc/nxp-nci/i2c.c i2c.c \
        && rm -rf drivers && printf 'obj-m += nxp-nci_i2c.o\nnxp-nci_i2c-y := i2c.o\n' > Kbuild)
fi
if [ $BUILD_CORE = 1 ]; then
    (cd "$WORK/nxp-nci-core" && mkdir -p drivers/nfc/nxp-nci && cp core.c drivers/nfc/nxp-nci/core.c \
        && git apply "$HERE/patches/nxp-nci-poll-period.patch" && cp drivers/nfc/nxp-nci/core.c core.c \
        && rm -rf drivers && printf 'obj-m += nxp-nci.o\nnxp-nci-y := core.o firmware.o\n' > Kbuild)
fi

if [ $BUILD_HID = 1 ]; then
    if (cd "$WORK/intel-hid" && mkdir -p drivers/platform/x86/intel && cp hid.c drivers/platform/x86/intel/hid.c \
            && git apply "$HERE/patches/intel-hid-volume-hold.patch" && cp drivers/platform/x86/intel/hid.c hid.c \
            && sed -i 's#"\.\./dual_accel_detect\.h"#"dual_accel_detect.h"#' hid.c \
            && rm -rf drivers && printf 'obj-m += intel_hid.o\nintel_hid-y := hid.o\n' > Kbuild); then :; else
        echo "intel-hid: patch does not apply (probably fixed upstream), not building it."; BUILD_HID=0
    fi
fi

say "Building and signing"
sudo mkdir -p "$DEST"
install_mod() {   # <dir> <module>
    toolbox run -c "$TB" make -C "$KDIR" M="$WORK/$1" modules >"$WORK/$1/build.log" 2>&1 \
        || { tail -20 "$WORK/$1/build.log"; exit 1; }
    toolbox run -c "$TB" "$KDIR/scripts/sign-file" sha256 "$MOKDIR/MOK.priv" "$MOKDIR/MOK.der" "$WORK/$1/$2.ko"
    sudo cp "$WORK/$1/$2.ko" "$DEST/$2-$K.ko"
    sudo chcon -t modules_object_t "$DEST" "$DEST/$2-$K.ko"
    echo "installed $DEST/$2-$K.ko"
}
[ $BUILD_OV8865 = 1 ] && install_mod ov8865 ov8865
[ $BUILD_OV5693 = 1 ] && install_mod ov5693 ov5693
[ $BUILD_NCI = 1 ] && install_mod nxp-nci nxp-nci_i2c
[ $BUILD_CORE = 1 ] && install_mod nxp-nci-core nxp-nci
[ $BUILD_HID = 1 ] && install_mod intel-hid intel_hid

say "modprobe rules and boot service"
if [ $BUILD_OV8865 = 1 ]; then
sudo tee /etc/modprobe.d/ov8865-local.conf >/dev/null <<'EOF'
# Locally patched + signed ov8865 (rear camera stale-mode fix) for the running kernel;
# falls back to the stock module if the file for this exact kernel is missing or rejected.
install ov8865 /usr/sbin/modprobe -a videodev v4l2-fwnode mc v4l2-async; /usr/sbin/insmod /var/lib/local-kmods/ov8865-$(/usr/bin/uname -r).ko || /usr/sbin/modprobe --ignore-install ov8865
EOF
fi
if [ $BUILD_OV5693 = 1 ]; then
sudo tee /etc/modprobe.d/ov5693-local.conf >/dev/null <<'EOF'
# Locally patched + signed ov5693 (front camera: default timing capped at 30 fps) for the running kernel; stock module as fallback.
install ov5693 /usr/sbin/modprobe -a videodev v4l2-fwnode mc v4l2-async v4l2-cci; /usr/sbin/insmod /var/lib/local-kmods/ov5693-$(/usr/bin/uname -r).ko || /usr/sbin/modprobe --ignore-install ov5693
EOF
fi
if [ $BUILD_HID = 1 ]; then
sudo tee /etc/modprobe.d/intel-hid-local.conf >/dev/null <<'EOF'
# Locally patched + signed intel-hid (hold-to-repeat for the device volume buttons); stock module as fallback.
install intel_hid /usr/sbin/modprobe -a sparse-keymap; /usr/sbin/insmod /var/lib/local-kmods/intel_hid-$(/usr/bin/uname -r).ko volume_hold=$(/usr/bin/cat /var/lib/local-kmods/volume_hold 2>/dev/null || echo 1) || /usr/sbin/modprobe --ignore-install intel_hid
EOF
fi
if [ $BUILD_CORE = 1 ]; then
sudo tee /etc/modprobe.d/nxp-nci-core-local.conf >/dev/null <<'EOF'
# Locally patched + signed nxp-nci core (sets a shorter NFC polling period, default 250 ms instead of the
# NCI default 1000 ms); stock module as fallback. To tune: append e.g. " poll_period_ms=150" after insmod's file.
install nxp_nci /usr/sbin/modprobe -a nci; /usr/sbin/insmod /var/lib/local-kmods/nxp-nci-$(/usr/bin/uname -r).ko || /usr/sbin/modprobe --ignore-install nxp_nci
EOF
fi
if [ $BUILD_NCI = 1 ]; then
sudo tee /etc/modprobe.d/nxp-nci-local.conf >/dev/null <<'EOF'
# Surface Go NFC: the stock nxp-nci_i2c lacks the ACPI id NXP3001. Load our locally patched
# + signed build for the running kernel; fall back to the stock module if missing/rejected.
install nxp_nci_i2c /usr/sbin/modprobe -a nxp-nci; /usr/sbin/insmod /var/lib/local-kmods/nxp-nci_i2c-$(/usr/bin/uname -r).ko || /usr/sbin/modprobe --ignore-install nxp_nci_i2c
EOF
# The kernel has no alias for NXP3001, so nothing autoloads the driver: use a service. It must run
# after local-fs.target: systemd-modules-load is too early, /var is not mounted yet on Kinoite.
sudo tee /etc/systemd/system/local-nxp-nci.service >/dev/null <<'EOF'
[Unit]
Description=Load locally built NFC driver for Surface Go (ACPI NXP3001)
After=local-fs.target systemd-modules-load.service
ConditionPathExists=/sys/bus/acpi/devices/NXP3001:00

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/modprobe nxp_nci_i2c

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable local-nxp-nci.service
fi

say "libcamera tuning (exposure for backlit scenes; libcamera reads /etc/libcamera/ipa before /usr/share)"
sudo mkdir -p /etc/libcamera/ipa/ipu3
# The base tuning only uses algorithms of the stock libcamera. The full tuning (lens shading tables) needs the patched libcamera below:
# it is installed from there, only once that build exists (the stock libcamera refuses a tuning file with an unknown algorithm).
sudo install -m 644 "$HERE"/tuning/base/*.yaml /etc/libcamera/ipa/ipu3/

say "libcamera with the IPU3 crash fixes (the stock one makes WirePlumber abort/segfault when apps ask for other sizes)"
# Same version as the installed package = same ABI, so the PipeWire plugin can use it. Only the IPU3 pipeline is built,
# installed to /usr/local/libcamera-patched and selected for WirePlumber only, through a systemd user drop-in.
LCV=$(rpm -q --qf '%{VERSION}' libcamera 2>/dev/null || true)
LCPATCHES=("$HERE"/patches/libcamera-"$LCV"-*.patch)   # one set of patches per libcamera version
LCROOT="$HOME/libcamera-build"
LCDROPIN="$HOME/.config/systemd/user/wireplumber.service.d/patched-libcamera.conf"
if [ -z "$LCV" ]; then
    echo "libcamera is not installed, skipping."
else
    mkdir -p "$LCROOT"
    rm -rf -- "$LCROOT/libcamera-$LCV" "$LCROOT/stage"
    curl -fsSL "https://github.com/libcamera-org/libcamera/archive/refs/tags/v$LCV.tar.gz" | tar xz -C "$LCROOT"
    LCOK=1
    [ -e "${LCPATCHES[0]}" ] || LCOK=0
    for P in "${LCPATCHES[@]}"; do
        (cd "$LCROOT/libcamera-$LCV" && git apply --check -p1 "$P") 2>/dev/null || LCOK=0
    done
    if [ $LCOK = 1 ]; then
        for P in "${LCPATCHES[@]}"; do (cd "$LCROOT/libcamera-$LCV" && git apply -p1 "$P"); done
        toolbox run -c "$TB" sudo dnf install -y meson ninja-build python3-yaml python3-jinja2 python3-ply \
            libyaml-devel systemd-devel openssl-devel gcc-c++ pkgconf-pkg-config
        toolbox run -c "$TB" bash -c "cd '$LCROOT/libcamera-$LCV' \
            && meson setup build -Dprefix=/usr/local/libcamera-patched -Dlibdir=lib -Dsysconfdir=/etc \
                 -Dbuildtype=release -Dpipelines=ipu3 -Dipas=ipu3 -Dcam=disabled -Dqcam=disabled \
                 -Dgstreamer=disabled -Dlc-compliance=disabled -Dpycamera=disabled -Ddocumentation=disabled \
                 -Dtest=false -Dandroid=disabled -Dv4l2=false -Dtracing=disabled \
            && ninja -C build && DESTDIR='$LCROOT/stage' ninja -C build install"
        sudo rm -rf /var/usrlocal/libcamera-patched
        sudo cp -a "$LCROOT/stage/usr/local/libcamera-patched" /var/usrlocal/libcamera-patched
        sudo restorecon -R /var/usrlocal/libcamera-patched
        mkdir -p "$(dirname "$LCDROPIN")"
        cat > "$LCDROPIN" <<LCEOF
[Service]
# libcamera $LCV rebuilt with the IPU3 fixes (same version = same ABI as the system libcamera)
Environment=LD_LIBRARY_PATH=/usr/local/libcamera-patched/lib
LCEOF
        # lens shading tables from the Windows calibration of the camera modules (see README, tools/cpf_to_tuning.py)
        sudo install -m 644 "$HERE"/tuning/ipu3/*.yaml /etc/libcamera/ipa/ipu3/
        systemctl --user daemon-reload 2>/dev/null || true
        systemctl --user restart wireplumber 2>/dev/null || echo "Restart WirePlumber from the desktop session: systemctl --user restart wireplumber"
    else
        echo "The libcamera patches do not apply to libcamera $LCV (probably fixed upstream, or it needs a rebase): using the stock libcamera."
        rm -f -- "$LCDROPIN"
    fi
fi

say "nfc-daemon (always-on NFC reader, talks to the kernel directly; replaces neard)"
# neard is NOT used: it segfaults when a tag disappears mid-read and under fast tag swapping it leaves the
# kernel with an "active target" so polling silently stops. The daemon releases every tag after reading it.
sudo mkdir -p /var/lib/nfc-daemon
sudo install -m 755 "$HERE/tools/nfc-daemon.py" /var/lib/nfc-daemon/nfc-daemon.py
sudo install -m 644 "$HERE/tools/nfc-daemon.service" /etc/systemd/system/nfc-daemon.service
sudo systemctl daemon-reload
sudo systemctl enable nfc-daemon.service
# the adapter only exists once the local driver is loaded; on a first run the reboot below starts everything in order
if [ -d /sys/class/nfc/nfc0 ]; then sudo systemctl restart nfc-daemon.service; fi

say "nfc-notify (sound + notification when a tag is detected, always listening)"
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
install -m 755 "$HERE/tools/nfc-notify.py" "$HOME/.local/bin/nfc-notify"
install -m 644 "$HERE/tools/nfc-notify.service" "$HOME/.config/systemd/user/nfc-notify.service"
systemctl --user daemon-reload 2>/dev/null || true
if ! systemctl --user enable --now nfc-notify.service 2>/dev/null; then
    echo "Could not start the user service from here; log in on the desktop and run: systemctl --user enable --now nfc-notify"
fi

say "Kernel update watcher (tells you when a new kernel needs the modules rebuilt)"
echo ok | sudo tee "$DEST/built-$K" >/dev/null
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
install -m 755 "$HERE/tools/kmods-check.sh" "$HOME/.local/bin/surface-kmods-check"
mkdir -p "$HOME/.config/pipewire/pipewire.conf.d"
for f in 10-speaker-gain 20-mic-filter; do [ -e "$HOME/.config/pipewire/pipewire.conf.d/$f.conf" ] || cp "$HERE/tuning/pipewire/$f.conf" "$HOME/.config/pipewire/pipewire.conf.d/$f.conf"; done   # speaker boost, filtered microphone (never overwritten: Surface Control edits them)
sed "s#@GUIDE@#$HERE#g" "$HERE/tools/kmods-check.service" > "$HOME/.config/systemd/user/kmods-check.service"
sed "s#@GUIDE@#$HERE#g" "$HERE/tools/kmods-rebuild.desktop" > "$HOME/.local/share/applications/surface-kmods-rebuild.desktop"
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable kmods-check.service 2>/dev/null || true
sed "s#@GUIDE@#$HERE#g" "$HERE/tools/surface-audio-route.service" > "$HOME/.config/systemd/user/surface-audio-route.service"   # equalizer per output (jack/speakers)
systemctl --user enable surface-audio-route.service 2>/dev/null || true
python3 "$HERE/suite/control/restore_defaults.py" || true   # built-in audio presets the user deleted come back, custom ones stay
sudo install -m 644 "$HERE/tools/61-surface-sensors.rules" /etc/udev/rules.d/61-surface-sensors.rules   # lets the 3D/sensor pages raise the sensor update rate
install -m 755 "$HERE/tools/camera-mode.sh" "$HOME/.local/bin/surface-camera-mode"
sed "s#@GUIDE@#$HERE#g" "$HERE/suite/control/surface-control" > "$HOME/.local/bin/surface-control"; chmod 755 "$HOME/.local/bin/surface-control"
sed "s#@BIN@#$HOME/.local/bin/surface-control#g" "$HERE/suite/control/surface-control.desktop" > "$HOME/.local/share/applications/surface-control.desktop"

say "Keyboard cover recovery (trackpad not picked up after boot, and a reset button in Surface Control)"
sudo install -m 755 "$HERE/tools/folio-heal.sh" /usr/local/sbin/folio-heal.sh
sudo install -m 755 "$HERE/tools/folio-reset.sh" /usr/local/sbin/folio-reset.sh
sudo install -m 644 "$HERE/tools/folio-heal.service" /etc/systemd/system/folio-heal.service
sudo install -m 644 "$HERE/tools/folio-reset.service" /etc/systemd/system/folio-reset.service
sudo install -m 644 "$HERE/tools/99-folio-heal.rules" /etc/udev/rules.d/99-folio-heal.rules
sudo install -m 644 "$HERE/tools/50-folio-reset.rules" /etc/polkit-1/rules.d/50-folio-reset.rules
sudo restorecon /usr/local/sbin/folio-*.sh 2>/dev/null || true
sudo systemctl daemon-reload
sudo udevadm control --reload
install -m 644 "$HERE/tools/folio-reset.desktop" "$HOME/.local/share/applications/folio-reset.desktop"

say "Done"
echo "REBOOT now (do not try rmmod/modprobe -r on ipu3_imgu, nxp_nci or nxp_nci_i2c: they hang and block shutdown)."
echo "Then verify with: $HERE/scripts/03-verify.sh"
