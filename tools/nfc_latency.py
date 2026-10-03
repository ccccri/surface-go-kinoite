#!/usr/bin/env python3
"""Measure NFC detection latency straight against the kernel (generic netlink), without neard.

Hold ONE tag on the device for the whole run. It waits for the first detection, then repeats:
  deactivate target -> start poll -> time until the kernel reports the tag again.
That time is the pure detection latency for a tag that is already in the field.
Also shows what happens if you start polling while a target is still active (the neard problem).
Run as root, with neard stopped:  systemctl stop neard
"""
import errno
import select
import socket
import struct
import sys
import time

NLM_F_REQUEST, NLM_F_ACK, NLM_F_DUMP = 1, 4, 0x300
NLMSG_ERROR = 2
CMD = dict(DEV_UP=2, DEV_DOWN=3, START_POLL=6, STOP_POLL=7, GET_TARGET=8, TARGETS_FOUND=9,
           TARGET_LOST=12, DEACTIVATE_TARGET=30)
A = dict(DEVICE_INDEX=1, TARGET_INDEX=4, NFCID1=7, IM_PROTOCOLS=13)
PROTO = (1 << 2) | (1 << 3) | (1 << 4) | (1 << 6)        # mifare, felica, iso14443, iso14443b


def nla(t, d):
    n = 4 + len(d)
    return struct.pack("HH", n, t) + d + b"\0" * ((4 - n % 4) % 4)


def parse(b):
    out = {}
    while len(b) >= 4:
        n, t = struct.unpack_from("HH", b)
        out[t & 0x3fff] = b[4:n]
        b = b[(n + 3) & ~3:]
    return out


def msg(fam, cmd, attrs=b"", flags=NLM_F_REQUEST, seq=1):
    g = struct.pack("BBH", cmd, 1, 0) + attrs
    return struct.pack("IHHII", 16 + len(g), fam, flags, seq, 0) + g


def msgs(data):
    while len(data) >= 16:
        n, t, f, s, p = struct.unpack_from("IHHII", data)
        yield t, f, data[16:n]
        data = data[(n + 3) & ~3:]


sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 16)
sock.bind((0, 0))
sock.send(msg(0x10, 3, nla(2, b"nfc\0")))
fam = grp = None
for t, f, body in msgs(sock.recv(65536)):
    at = parse(body[4:])
    fam = struct.unpack("H", at[1])[0]
    for g in parse(at.get(7, b"")).values():
        ga = parse(g)
        if ga.get(1, b"").rstrip(b"\0") == b"events":
            grp = struct.unpack("I", ga[2])[0]
sock.setsockopt(270, 1, grp)
DEV = nla(A["DEVICE_INDEX"], struct.pack("I", 0))


def call(cmd, attrs=DEV):
    sock.send(msg(fam, cmd, attrs, NLM_F_REQUEST | NLM_F_ACK, seq=2))
    while True:
        for t, f, body in msgs(sock.recv(65536)):
            if t == NLMSG_ERROR:
                return -struct.unpack_from("i", body)[0]


def name(e):
    return "ok" if e == 0 else errno.errorcode.get(e, e)


def wait_found(timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not select.select([sock], [], [], 0.05)[0]:
            continue
        for t, f, body in msgs(sock.recv(65536)):
            if t == fam and body[0] == CMD["TARGETS_FOUND"]:
                return time.monotonic()
    return None


def target_index():
    sock.send(msg(fam, CMD["GET_TARGET"], DEV, NLM_F_REQUEST | NLM_F_DUMP, seq=3))
    idx = None
    for t, f, body in msgs(sock.recv(65536)):
        if t == fam:
            at = parse(body[4:])
            if A["TARGET_INDEX"] in at:
                idx = struct.unpack("I", at[A["TARGET_INDEX"]])[0]
    return idx


def poll_attrs():
    return DEV + nla(A["IM_PROTOCOLS"], struct.pack("I", PROTO))


print("dev_up:", name(call(CMD["DEV_UP"])))
print("start_poll:", name(call(CMD["START_POLL"], poll_attrs())))
print("waiting up to 60 s for the first tag - put ONE tag on the device and keep it there ...", flush=True)
if wait_found(60) is None:
    sys.exit("no tag found")
print("first tag found. Keep it still.\n")

times = []
for i in range(10):
    idx = target_index()
    e_busy = call(CMD["START_POLL"], poll_attrs())          # what neard does after a removal
    e_deact = call(CMD["DEACTIVATE_TARGET"], DEV + nla(A["TARGET_INDEX"], struct.pack("I", idx or 0)))
    t0 = time.monotonic()
    e_start = call(CMD["START_POLL"], poll_attrs())
    t_found = wait_found(15)
    dt = None if t_found is None else (t_found - t0) * 1000
    times.append(dt)
    print("run %2d: start_poll while target active -> %-8s deactivate -> %-8s restart -> %-8s "
          "detected after %s" % (i + 1, name(e_busy), name(e_deact), name(e_start),
                                 "TIMEOUT" if dt is None else "%.0f ms" % dt), flush=True)

ok = [t for t in times if t is not None]
if ok:
    print("\ndetection latency with the tag already present: min %.0f  median %.0f  max %.0f ms (%d/%d ok)"
          % (min(ok), sorted(ok)[len(ok) // 2], max(ok), len(ok), len(times)))
call(CMD["STOP_POLL"], DEV)
call(CMD["DEV_DOWN"], DEV)
