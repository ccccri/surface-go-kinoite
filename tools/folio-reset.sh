#!/bin/bash
# Manual reset of the Surface Go keyboard cover ("folio", USB 045e:09b5): re-enumerates the USB device, which is the software
# equivalent of unplugging and re-attaching the cover (the trackpad sometimes stays bound but silent, and the automatic check in
# folio-heal.sh cannot see that). Started as root by folio-reset.service; a polkit rule lets the local user start it with one tap.
log() { logger -t folio-reset "$*"; }
USBDEV=$(grep -l '^045e$' /sys/bus/usb/devices/*/idVendor 2>/dev/null | while read -r f; do d=${f%/idVendor}
    [ "$(cat "$d/idProduct")" = 09b5 ] && echo "$d" && break; done)
[ -n "$USBDEV" ] || { log "keyboard cover not attached"; exit 1; }
log "re-enumerating $USBDEV"
echo 0 > "$USBDEV/authorized"; sleep 2; echo 1 > "$USBDEV/authorized"
for _ in $(seq 1 15); do
    for d in /sys/bus/hid/devices/0003:045E:09B5.*; do
        [ "$(basename "$(readlink -f "$d/driver" 2>/dev/null)")" = hid-multitouch ] && { log "trackpad bound to hid-multitouch again"; exit 0; }
    done
    sleep 1
done
log "trackpad did not come back"
exit 1
