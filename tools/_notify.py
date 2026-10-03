"""Desktop notifications from a script that runs as root (sudo): a root process has no session bus, so the notification is sent as the user who ran sudo."""
import os
import subprocess


def notify(title, text, urgent=True, sound=True):
    uid = os.environ.get("SUDO_UID")
    user = os.environ.get("SUDO_USER")
    if not uid or not user:
        cmd = ["notify-send", "-a", "Surface test", title, text]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    env = ["XDG_RUNTIME_DIR=/run/user/%s" % uid, "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%s/bus" % uid, "WAYLAND_DISPLAY=wayland-0"]
    base = ["runuser", "-u", user, "--", "env"] + env
    subprocess.run(base + ["notify-send", "-a", "Surface test", "-u", "normal", "-t", "5000", "-h", "string:x-canonical-private-synchronous:surface-test", title, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sound:
        subprocess.Popen(base + ["pw-play", "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
