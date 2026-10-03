#!/usr/bin/env python3
"""Minimal Linux NFC (generic netlink) poller: power on nfc0, poll, print tags found."""
import socket, struct, sys, time, select, errno

NLM_F_REQUEST, NLM_F_ACK, NLM_F_DUMP = 1, 4, 0x300
NLMSG_ERROR, NLMSG_DONE = 2, 3
CMD = dict(GET_DEVICE=1, DEV_UP=2, DEV_DOWN=3, START_POLL=6, STOP_POLL=7, GET_TARGET=8, TARGETS_FOUND=9)
A = dict(DEVICE_INDEX=1, PROTOCOLS=3, TARGET_INDEX=4, SENS_RES=5, SEL_RES=6, NFCID1=7, IM_PROTOCOLS=13)

def nla(t, d): l = 4 + len(d); return struct.pack("HH", l, t) + d + b"\0" * ((4 - l % 4) % 4)
def parse(b):
    out = {}
    while len(b) >= 4:
        l, t = struct.unpack_from("HH", b); out[t & 0x3fff] = b[4:l]; b = b[(l + 3) & ~3:]
    return out
def msg(fam, cmd, attrs=b"", flags=NLM_F_REQUEST, seq=1):
    g = struct.pack("BBH", cmd, 1, 0) + attrs
    return struct.pack("IHHII", 16 + len(g), fam, flags, seq, 0) + g
def msgs(data):
    while len(data) >= 16:
        l, t, f, s, p = struct.unpack_from("IHHII", data); yield t, f, data[16:l]; data = data[(l + 3) & ~3:]

s = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 16); s.bind((0, 0))
s.send(msg(0x10, 3, nla(2, b"nfc\0")))
fam = grp = None
for t, f, body in msgs(s.recv(65536)):
    if t == NLMSG_ERROR: sys.exit("nfc netlink family not found (is CONFIG_NFC loaded?)")
    at = parse(body[4:]); fam = struct.unpack("H", at[1])[0]
    for g in _ if False else []: pass
    if 7 in at:
        for g in parse(at[7]).values():
            ga = parse(g)
            if ga.get(1, b"").rstrip(b"\0") == b"events": grp = struct.unpack("I", ga[2])[0]
s.setsockopt(270, 1, grp)      # SOL_NETLINK, NETLINK_ADD_MEMBERSHIP

def call(cmd, attrs=b"", quiet=False):
    s.send(msg(fam, cmd, attrs, NLM_F_REQUEST | NLM_F_ACK, seq=2))
    while True:
        for t, f, body in msgs(s.recv(65536)):
            if t == NLMSG_ERROR:
                e = -struct.unpack_from("i", body)[0]
                if e and not quiet: print(f"  cmd {cmd}: {errno.errorcode.get(e, e)}")
                return e
dev = nla(A["DEVICE_INDEX"], struct.pack("I", 0))
print("dev_up  ->", call(CMD["DEV_UP"], dev))
proto = int(sys.argv[2], 0) if len(sys.argv) > 2 else (1<<1)|(1<<2)|(1<<3)|(1<<4)|(1<<6)   # jewel,mifare,felica,iso14443,iso14443b
print("poll    ->", call(CMD["START_POLL"], dev + nla(A["IM_PROTOCOLS"], struct.pack("I", proto))))
print(f"polling for {int(sys.argv[1]) if len(sys.argv) > 1 else 60}s - hold the tag on the device...", flush=True)
end = time.time() + (int(sys.argv[1]) if len(sys.argv) > 1 else 60); found = False
while time.time() < end:
    if not select.select([s], [], [], 1)[0]: continue
    for t, f, body in msgs(s.recv(65536)):
        if t != fam or body[0] != CMD["TARGETS_FOUND"]: continue
        s.send(msg(fam, CMD["GET_TARGET"], dev, NLM_F_REQUEST | NLM_F_DUMP, seq=3))
        for t2, f2, b2 in msgs(s.recv(65536)):
            if t2 != fam: continue
            at = parse(b2[4:])
            uid = at.get(A["NFCID1"], b"").hex(":")
            print(f"TAG FOUND: uid={uid or '?'} sens_res={at.get(A['SENS_RES'], b'').hex()} sel_res={at.get(A['SEL_RES'], b'').hex()} protocols=0x{struct.unpack('I', at[A['PROTOCOLS']])[0]:x}" if A["PROTOCOLS"] in at else f"TARGET: {at}")
            found = True
    if found: break
call(CMD["STOP_POLL"], dev, True); call(CMD["DEV_DOWN"], dev, True)
print("done" if found else "no tag detected")
