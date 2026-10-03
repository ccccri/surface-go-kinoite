#!/usr/bin/env python3
"""Brings back the built-in audio presets the user deleted. Run by the install script after the patches are applied again; your own presets stay."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backend

backend.restore_defaults()
print("built-in presets restored (custom presets untouched)")
