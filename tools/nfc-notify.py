#!/usr/bin/env python3
"""Desktop side of the NFC reader (runs as a systemd *user* service).

Connects to nfc-daemon (the root service that owns the reader) and, for every tag event, plays a
sound and shows a desktop notification with what is on the tag, like an iPhone. A link is only
opened if you click "Open" in the notification.

Needs: notify-send and pw-play (both present on Kinoite). Standard library only.
"""
import html
import json
import os
import shutil
import socket
import subprocess
import threading
import time

SOCK_PATH = os.environ.get("NFC_SOCK", "/run/nfc-notify/events.sock")
SOUND = "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"
OPENABLE = ("http://", "https://", "mailto:", "tel:")


def log(msg):
    print(msg, flush=True)


def flatten(records):
    """[(line, openable_url_or_None)] for a list of NDEF records."""
    out = []
    for r in records:
        kind, value = r.get("kind"), r.get("value")
        if kind == "uri":
            out.append(("Link: " + value, value))
        elif kind == "text":
            out.append(("Text: " + value, None))
        elif kind == "smartposter":
            out.extend(flatten(value))
        elif kind == "mime":
            out.append(("Data: " + value, None))
        elif kind == "external":
            out.append(("Record: " + value, None))
        else:
            out.append((str(value), None))
    return out


def play_sound():
    if shutil.which("pw-play") and os.path.exists(SOUND):
        subprocess.Popen(["pw-play", SOUND], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(title, body, url):
    cmd = ["notify-send", "--app-name=NFC", "--icon=nfc", "--urgency=normal", "--expire-time=10000"]
    if url and url.startswith(OPENABLE):
        cmd += ["--action=open=Open", "--wait"]
    cmd += [title, html.escape(body)]

    def run():
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception as exc:                       # notification daemon missing, timeout...
            log("notify-send failed: %s" % exc)
            return
        if out == "open" and url:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    threading.Thread(target=run, daemon=True).start()


def window_open():
    """The Surface Control NFC page shows the tags itself while it is open (it writes its pid here): no desktop notification then."""
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()), "surface-nfc-window")
    try:
        return os.path.exists("/proc/%d" % int(open(path).read().strip()))
    except (OSError, ValueError):
        return False


def handle(event):
    records = event.get("records")
    lines = flatten(records or [])
    url = next((u for _, u in lines if u), None)
    text = [l for l, _ in lines]
    if records is None:
        text.append("Card or device, no readable data")
    elif not lines:
        text.append("Empty or non-NDEF tag")
    text.append("%s, UID %s" % (event.get("type", "tag"), event.get("uid", "?")))
    latency = time.time() - event.get("time", time.time())
    log("event %s: %s (delivered in %.0f ms)" % (event.get("uid"), " | ".join(text), latency * 1000))
    play_sound()
    if not window_open():
        notify("NFC tag detected", "\n".join(text), url)


def main():
    log("nfc-notify running")
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCK_PATH)
        except OSError as exc:
            log("waiting for nfc-daemon (%s)" % exc.strerror)
            time.sleep(3)
            continue
        log("connected to nfc-daemon")
        buf = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        handle(json.loads(line))
                    except (ValueError, KeyError) as exc:
                        log("bad event: %s" % exc)
        except OSError:
            pass
        finally:
            s.close()
        log("lost connection to nfc-daemon, retrying")
        time.sleep(2)


if __name__ == "__main__":
    main()
