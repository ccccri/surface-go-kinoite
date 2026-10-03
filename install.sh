#!/bin/bash
# Opens the Surface Go installer (a window). Needs a desktop session. For the plain scripts see README.md.
HERE=$(cd "$(dirname "$0")" && pwd)
exec python3 "$HERE/suite/installer/installer.py" "$@"
