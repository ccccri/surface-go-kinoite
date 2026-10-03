#!/bin/bash
# Rear camera picture size selector (command line twin of Surface Control > Cameras). Camera apps such as Kamoso take the FIRST size the camera
# offers and have no setting for it, so the choice is made here: "min_width" in ~/.config/surface-suite/camera/ov8865.profile is the smallest
# rear size offered (see patches/libcamera-0.7.1-zz-live-profile.patch). WirePlumber (which hosts libcamera) is restarted: reopen the camera app.
#   camera-mode smooth   1536x1152 at 30 fps (default: video calls, live view)
#   camera-mode high     2048x1536 at about 15 fps
#   camera-mode max      3200x2400 (8 MP, the full sensor) at about 11-15 fps
#   camera-mode status   show the current mode
PROFILE=$HOME/.config/surface-suite/camera/ov8865.profile

current() {
    case $(sed -n 's/^min_width *\([0-9]*\).*/\1/p' "$PROFILE" 2>/dev/null) in
        2048) echo high ;;
        3200) echo max ;;
        *) echo smooth ;;
    esac
}

mode=${1:-status}
[ "$mode" = status ] && { current; exit 0; }
case "$mode" in
    smooth) w= ;;
    high) w=2048 ;;
    max) w=3200 ;;
    *) echo "usage: $0 smooth|high|max|status" >&2; exit 2 ;;
esac
mkdir -p "$(dirname "$PROFILE")"
touch "$PROFILE"
sed -i '/^min_width/d' "$PROFILE"
[ -n "$w" ] && echo "min_width $w" >> "$PROFILE"
[ -s "$PROFILE" ] || rm -f "$PROFILE"
systemctl --user restart wireplumber
echo "rear camera mode: $mode"
