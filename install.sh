#!/bin/bash
# Opens the Surface Go installer (a window). Needs a desktop session. For the plain scripts see README.md.
HERE=$(cd "$(dirname "$0")" && pwd)
if [ -z "$SURFACE_NO_PYSIDE" ] && python3 -c "import PySide6.QtQml" 2>/dev/null; then
    exec python3 "$HERE/suite/installer/installer.py" "$@"
fi
# A freshly installed Kinoite does not have PySide6 yet (it comes with the first system update), so the window cannot open: run the first step here in the terminal.
# It updates the system and queues the Secure Boot key; after the restart (and the blue MOK screen) run this file again and the window opens.
echo "Step 1 of the installation runs here in the terminal: it updates the system and prepares the Secure Boot key."
echo "After it finishes, restart, complete the blue MOK screen (see README.md), then run   $HERE/install.sh   again: the window opens."
echo
bash "$HERE/scripts/01-upgrade-and-mok.sh"
