#!/bin/bash
# Step 1 (run ON the Surface Go, as your normal user).
#
#  - upgrades Kinoite to the latest image (the installer ships kernel 6.19.x, whose dw9719 driver
#    is broken and leaves the cameras dead; kernel >= 7.x fixes that part)
#  - creates a module-signing key and queues its enrollment in the firmware (MOK), because
#    Secure Boot refuses unsigned kernel modules and Fedora's own module key does not exist anymore
#
# After this script: reboot. A blue "MOK management" screen appears; you have ~10 seconds to press a
# key. Choose: Enroll MOK -> Continue -> Yes -> type the password -> Reboot.
set -euo pipefail

MOK_PASSWORD=${MOK_PASSWORD:-surface}   # only used once, at the blue screen
MOKDIR=${MOKDIR:-$HOME/mok}

mkdir -p "$MOKDIR" && chmod 700 "$MOKDIR" && cd "$MOKDIR"
if [ ! -f MOK.priv ]; then
    openssl req -new -x509 -newkey rsa:2048 -keyout MOK.priv -out MOK.pem -days 36500 -nodes \
        -subj "/CN=Surface Go local module signing/" \
        -addext "keyUsage=digitalSignature" \
        -addext "extendedKeyUsage=codeSigning" \
        -addext "basicConstraints=critical,CA:FALSE"
    openssl x509 -in MOK.pem -outform DER -out MOK.der
    chmod 600 MOK.priv
fi

ENROLLED=$(mokutil --list-enrolled 2>/dev/null || true)   # not piped: grep -q + pipefail = SIGPIPE
if grep -q "Surface Go local module signing" <<<"$ENROLLED"; then
    echo "MOK key already enrolled, nothing to queue."
else
    mokutil --generate-hash="$MOK_PASSWORD" > hash.txt
    sudo mokutil --import MOK.der --hash-file hash.txt
    echo "MOK enrollment queued (password: $MOK_PASSWORD)."
fi

sudo rpm-ostree upgrade || true
echo
echo "Now run: systemctl reboot   (and complete the blue MOK screen within ~10 s)"
