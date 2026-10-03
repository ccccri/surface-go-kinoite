#!/bin/bash
# Boot-time check for the Surface Go keyboard cover ("folio", USB 045e:09b5): its trackpad is handled by hid-multitouch,
# which is a module loaded AFTER hid-generic already grabbed the device and then takes it over. Sometimes that hand-over
# does not happen and the trackpad is dead until the cover is unplugged. This waits for the trackpad to be bound
# to hid-multitouch; if it is not, it logs the state (journalctl -t folio-heal) and re-enumerates the USB device, which is
# the software equivalent of unplugging the cover. It never touches the device if the cover is not attached.
log() { logger -t folio-heal "$*"; }
USBDEV=$(grep -l '^045e$' /sys/bus/usb/devices/*/idVendor 2>/dev/null | while read -r f; do d=${f%/idVendor}
    [ "$(cat "$d/idProduct")" = 09b5 ] && echo "$d" && break; done)
[ -n "$USBDEV" ] || { log "keyboard cover not attached, nothing to do"; exit 0; }

bound() { for d in /sys/bus/hid/devices/0003:045E:09B5.*; do
    [ "$(basename "$(readlink -f "$d/driver" 2>/dev/null)")" = hid-multitouch ] && return 0; done; return 1; }

for attempt in 1 2 3; do
    for _ in $(seq 1 20); do bound && { log "trackpad bound to hid-multitouch (attempt $attempt): ok"; exit 0; }; sleep 1; done
    log "trackpad NOT bound after 20 s (attempt $attempt). hid devices: $(ls /sys/bus/hid/devices | grep 09B5 | tr '\n' ' ')"
    for d in /sys/bus/hid/devices/0003:045E:09B5.*; do
        log "  $(basename "$d") driver=$(basename "$(readlink -f "$d/driver" 2>/dev/null)" 2>/dev/null)"; done
    log "re-enumerating $USBDEV"
    echo 0 > "$USBDEV/authorized"; sleep 2; echo 1 > "$USBDEV/authorized"
    sleep 3
done
log "giving up: trackpad still not bound"
exit 1
