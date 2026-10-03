#!/bin/bash
# Runs at every login (user service kmods-check.service). The patched kernel modules are built for ONE kernel version: after an
# rpm-ostree update the new kernel silently falls back to the stock modules (rear camera shows a green picture, NFC stops, ...).
# scripts/02-build-and-install.sh writes /var/lib/local-kmods/built-<kernel> when it finishes; if that marker is missing for the
# running kernel, tell the user and offer to rebuild. Nothing is built automatically: the build needs sudo and the MOK signing key.
K=$(uname -r)
GUIDE=${1:-$HOME/surface-go-kinoite}
[ -f "/var/lib/local-kmods/built-$K" ] && exit 0
[ -x "$GUIDE/scripts/02-build-and-install.sh" ] || exit 0
ACTION=$(notify-send -u critical -a "Surface Go" -i camera-web -w -A rebuild="Rebuild now" \
    "Kernel updated to $K" \
    "The patched camera/NFC/volume drivers are built per kernel. Rebuild them now (about 5 minutes, asks for your password), then reboot.")
if [ "$ACTION" = rebuild ]; then
    exec konsole --hold -e bash -c "'$GUIDE/scripts/02-build-and-install.sh' && echo && read -r -p 'Done. Reboot now? [y/N] ' a && [ \"\$a\" = y ] && systemctl reboot"
fi
