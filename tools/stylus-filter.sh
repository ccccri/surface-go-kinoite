#!/bin/bash
# Turns the HID-BPF filter that hides the fake stylus battery on or off (run from Surface Control, in a terminal: it needs sudo).
#   stylus-filter.sh off   keeps the filter file but disables its udev rule
#   stylus-filter.sh on    enables the rule again (run scripts/04-stylus-battery.sh first if the filter was never installed)
# The change shows up the next time the touchscreen is detected: restart the tablet.
RULE=/etc/udev/rules.d/99-hid-bpf-stylus.rules
case "${1:-}" in
    off) [ -e "$RULE" ] && sudo mv "$RULE" "$RULE.disabled" ;;
    on)
        if [ -e "$RULE.disabled" ]; then sudo mv "$RULE.disabled" "$RULE"
        elif [ ! -e "$RULE" ]; then echo "The filter is not installed: run $(dirname "$0")/../scripts/04-stylus-battery.sh"; exit 1; fi ;;
    *) echo "usage: $0 on|off"; exit 2 ;;
esac
sudo udevadm control --reload
echo "Done. Restart the tablet for the change to take effect."
