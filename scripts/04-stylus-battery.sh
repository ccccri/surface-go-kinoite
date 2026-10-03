#!/bin/bash
# Optional (run ON the Surface Go): removes the fake "Stylus 0%/1% discharging" battery that the ELAN digitizer creates.
# The report descriptor declares a Digitizer "Battery Strength" usage that never carries data; a tiny HID-BPF program
# turns that usage into "Undefined" so the kernel does not create the power_supply. The real pen battery is the
# Bluetooth one (shown only while the pen is connected, i.e. after pressing a pen button).
# Needs udev-hid-bpf (ships with Fedora). Nothing to rebuild after kernel updates: BPF objects are loaded at runtime.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
TB=${TB:-surface-build}
SRC=$HERE/patches/hid-bpf/0010-Microsoft__Surface-Go-stylus-battery.bpf.c
W=$HOME/hid-bpf-build
rm -rf "$W"; mkdir -p "$W"
toolbox run -c "$TB" sudo dnf install -y clang libbpf-devel bpftool llvm git
toolbox run -c "$TB" bash -c "cd '$W' && git clone --depth 1 https://gitlab.freedesktop.org/libevdev/udev-hid-bpf.git uhb \
    && cd uhb/src/bpf && cp '$SRC' . && bpftool btf dump file /sys/kernel/btf/vmlinux format c > vmlinux.h \
    && clang -g -O2 -target bpf -D__TARGET_ARCH_x86 -I. -c $(basename "$SRC") -o '$W/stylus.o' 2>/dev/null \
    && bpftool gen object '$W/stylus.bpf.o' '$W/stylus.o'"
sudo udev-hid-bpf install --force "$W/stylus.bpf.o"
sudo udevadm control --reload
sudo udevadm trigger --action=add --subsystem-match=hid
sleep 3
ls /sys/class/power_supply/
