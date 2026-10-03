#!/bin/bash
# Turns the hold-to-repeat of the device volume buttons on or off (needs root: Surface Control runs it through polkit).
#   volume-hold.sh on | off | status
# The choice is stored in /var/lib/local-kmods/volume_hold and given to the patched intel_hid module when it loads at boot (modprobe rule
# in /etc/modprobe.d/intel-hid-local.conf); it is also applied to the running module now.
P=/sys/module/intel_hid/parameters/volume_hold
case "${1:-status}" in
    on)  v=1; c=Y ;;
    off) v=0; c=N ;;
    status) [ -r "$P" ] && cat "$P" || echo unavailable; exit 0 ;;
    *) echo "usage: $0 on|off|status" >&2; exit 2 ;;
esac
[ -w "$P" ] || { echo "the patched intel_hid module is not loaded (run the install script)" >&2; exit 1; }
echo $v > /var/lib/local-kmods/volume_hold
echo $c > "$P"
echo "volume buttons: hold to repeat is now $([ $v = 1 ] && echo on || echo off)"
