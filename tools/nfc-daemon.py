#!/usr/bin/env python3
"""nfc-daemon: always-on NFC tag reader for the Linux kernel NFC subsystem (no neard).

Runs as root (system service). It owns the reader: polls for tags, reads NDEF from Type 2 tags
(NTAG / MIFARE Ultralight) through a raw NFC socket, releases the tag in the kernel after every read
and re-arms polling right away. Results are broadcast as JSON lines on a unix socket that the
desktop notifier (nfc-notify, a user service) reads.

Why not neard: it crashes when a tag disappears mid-read and, under fast tag swapping, leaves the kernel
with an "active target" so that polling silently stops (nci_start_poll: there is an active target).

Only the Python standard library is used.
"""
import ctypes
import errno
import json
import os
import select
import socket
import struct
import sys
import threading
import time

SOCK_PATH = os.environ.get("NFC_SOCK", "/run/nfc-notify/events.sock")
SOCK_GROUP = os.environ.get("NFC_SOCK_GROUP", "wheel")
ABSENCE_S = 1.0          # same tag not seen for this long = it was removed, notify again
REPOLL_RESTING_S = 0.3   # pause between polls while the same tag keeps resting on the reader
# Give up reading a tag after this long. Must be longer than the kernel's own NCI data timeout (NCI_DATA_TIMEOUT = 3 s):
# if we close the socket and send RF_DEACTIVATE while the kernel still has a data exchange in flight, the controller
# never answers it and the kernel waits NCI_RF_DEACTIVATE_TIMEOUT = 30 s with the whole NFC stack blocked.
RAW_TIMEOUT_S = 3.3

AF_NFC, NFC_SOCKPROTO_RAW = 39, 0
NLM_F_REQUEST, NLM_F_ACK, NLM_F_DUMP = 1, 4, 0x300
NLMSG_ERROR, NLMSG_DONE = 2, 3
CMD = dict(DEV_UP=2, DEV_DOWN=3, START_POLL=6, STOP_POLL=7, GET_TARGET=8, TARGETS_FOUND=9,
           DEACTIVATE_TARGET=30)
A = dict(DEVICE_INDEX=1, PROTOCOLS=3, TARGET_INDEX=4, SENS_RES=5, SEL_RES=6, NFCID1=7, IM_PROTOCOLS=13)
NFC_PROTO = dict(JEWEL=1, MIFARE=2, FELICA=3, ISO14443=4, NFC_DEP=5, ISO14443_B=6, ISO15693=7)
POLL_PROTOS = sum(1 << NFC_PROTO[n] for n in ("MIFARE", "FELICA", "ISO14443", "ISO14443_B"))
DEV_INDEX = 0


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------------------ generic netlink
def nla(t, d):
    n = 4 + len(d)
    return struct.pack("HH", n, t) + d + b"\0" * ((4 - n % 4) % 4)


def parse_attrs(b):
    out = {}
    while len(b) >= 4:
        n, t = struct.unpack_from("HH", b)
        if n < 4:
            break
        out[t & 0x3fff] = b[4:n]
        b = b[(n + 3) & ~3:]
    return out


def u32(v):
    return struct.pack("I", v)


class NfcNetlink:
    def __init__(self):
        self.s = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 16)
        self.s.bind((0, 0))
        self.seq = 1
        self.events = []                       # multicast events seen while waiting for replies
        self.fam = self.grp = None
        self._resolve()
        self.s.setsockopt(270, 1, self.grp)    # SOL_NETLINK, NETLINK_ADD_MEMBERSHIP

    @staticmethod
    def _msgs(data):
        while len(data) >= 16:
            n, t, f, s, p = struct.unpack_from("IHHII", data)
            if n < 16:
                break
            yield t, f, data[16:n]
            data = data[(n + 3) & ~3:]

    def _send(self, fam, cmd, attrs, flags):
        self.seq += 1
        g = struct.pack("BBH", cmd, 1, 0) + attrs
        self.s.send(struct.pack("IHHII", 16 + len(g), fam, flags, self.seq, 0) + g)

    def _resolve(self):
        self._send(0x10, 3, nla(2, b"nfc\0"), NLM_F_REQUEST)
        for t, f, body in self._msgs(self.s.recv(65536)):
            if t == NLMSG_ERROR:
                raise RuntimeError("kernel has no NFC netlink family")
            at = parse_attrs(body[4:])
            self.fam = struct.unpack("H", at[1])[0]
            for g in parse_attrs(at.get(7, b"")).values():
                ga = parse_attrs(g)
                if ga.get(1, b"").rstrip(b"\0") == b"events":
                    self.grp = struct.unpack("I", ga[2])[0]

    def call(self, cmd, attrs=b"", dump=False):
        """Send a command; return (errno, [reply attribute dicts]). Events that arrive meanwhile are kept."""
        t0 = time.monotonic()
        err, replies = self._call(cmd, attrs, dump)
        took = time.monotonic() - t0
        if took > 1.0:                          # the kernel blocks on NCI timeouts (5 s, 30 s for RF_DEACTIVATE)
            log("slow netlink call cmd=%d took %.1f s (%s)" % (cmd, took, errno.errorcode.get(err, err)))
        return err, replies

    def _call(self, cmd, attrs, dump):
        self._send(self.fam, cmd, attrs, NLM_F_REQUEST | (NLM_F_DUMP if dump else NLM_F_ACK))
        replies = []
        while True:
            for t, f, body in self._msgs(self.s.recv(65536)):
                if t == NLMSG_ERROR:
                    return -struct.unpack_from("i", body)[0], replies
                if t == NLMSG_DONE:
                    return 0, replies
                if t == self.fam:
                    if body[0] == CMD["TARGETS_FOUND"]:
                        self.events.append("targets")
                    elif body[0] == cmd:
                        replies.append(parse_attrs(body[4:]))

    def wait_targets(self, timeout):
        """Block until the kernel reports targets (or timeout). Returns True if targets were found."""
        if self.events:
            self.events.clear()
            return True
        if not select.select([self.s], [], [], timeout)[0]:
            return False
        for t, f, body in self._msgs(self.s.recv(65536)):
            if t == self.fam and body[0] == CMD["TARGETS_FOUND"]:
                return True
        return False


DEV = nla(A["DEVICE_INDEX"], u32(DEV_INDEX))


def dev_up(nl):
    return nl.call(CMD["DEV_UP"], DEV)[0]


def start_poll(nl):
    return nl.call(CMD["START_POLL"], DEV + nla(A["IM_PROTOCOLS"], u32(POLL_PROTOS)))[0]


def get_targets(nl):
    err, replies = nl.call(CMD["GET_TARGET"], DEV, dump=True)
    out = []
    for at in replies:
        if A["TARGET_INDEX"] not in at:
            continue
        out.append(dict(
            idx=struct.unpack("I", at[A["TARGET_INDEX"]])[0],
            protos=struct.unpack("I", at[A["PROTOCOLS"]])[0] if A["PROTOCOLS"] in at else 0,
            uid=at.get(A["NFCID1"], b""),
            sens_res=at.get(A["SENS_RES"], b""),
            sel_res=at.get(A["SEL_RES"], b"")))
    return out


def deactivate(nl, target_idx):
    return nl.call(CMD["DEACTIVATE_TARGET"], DEV + nla(A["TARGET_INDEX"], u32(target_idx)))[0]


def release_stale_targets(nl):
    """Clear an 'active target' left behind by a crashed run, so that polling can start."""
    for t in get_targets(nl):
        deactivate(nl, t["idx"])


# ------------------------------------------------------------------------------ Type 2 tag + NDEF
libc = ctypes.CDLL(None, use_errno=True)


def raw_connect(sock, target_idx, protocol):
    # struct sockaddr_nfc { sa_family_t (u16); u32 dev_idx; u32 target_idx; u32 nfc_protocol; }
    addr = struct.pack("HxxIII", AF_NFC, DEV_INDEX, target_idx, protocol)
    if libc.connect(sock.fileno(), addr, len(addr)) != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))


def t2_read(sock, page):
    """READ command: 16 bytes = pages page..page+3. The kernel prepends a status byte (0 = ok)."""
    sock.send(bytes([0x30, page]))
    resp = sock.recv(64)
    if len(resp) < 17 or resp[0] != 0:
        raise OSError(errno.EIO, "read failed")
    return resp[1:17]


URI_PREFIX = ["", "http://www.", "https://www.", "http://", "https://", "tel:", "mailto:",
              "ftp://anonymous:anonymous@", "ftp://ftp.", "ftps://", "sftp://", "smb://", "nfs://",
              "ftp://", "dav://", "news:", "telnet://", "imap:", "rtsp://", "urn:", "pop:", "sip:",
              "sips:", "tftp:", "btspp://", "btl2cap://", "btgoep://", "tcpobex://", "irdaobex://",
              "file://", "urn:epc:id:", "urn:epc:tag:", "urn:epc:pat:", "urn:epc:raw:", "urn:epc:",
              "urn:nfc:"]


def read_t2_ndef(sock):
    """Return the raw NDEF message bytes of a Type 2 tag ('' if none)."""
    cc = t2_read(sock, 3)[:4]
    if cc[0] != 0xE1:
        return b""                                     # not NFC Forum formatted
    limit = cc[2] * 8                                  # data area size in bytes
    data = b""
    page = 4
    while len(data) < limit and page < 4 + limit // 4 + 4:
        data += t2_read(sock, page)
        page += 4
        msg = tlv_ndef(data)
        if msg is not None:
            return msg
    return b""


def tlv_ndef(data):
    """Find the NDEF TLV (0x03). Returns the message when complete, b'' if the tag says empty, None if more data is needed."""
    i = 0
    while i < len(data):
        t = data[i]
        if t == 0x00:                                  # NULL TLV
            i += 1
            continue
        if t == 0xFE:                                  # terminator
            return b""
        if i + 1 >= len(data):
            return None
        n = data[i + 1]
        hdr = 2
        if n == 0xFF:
            if i + 3 >= len(data):
                return None
            n = struct.unpack(">H", data[i + 2:i + 4])[0]
            hdr = 4
        if t == 0x03:
            return data[i + hdr:i + hdr + n] if len(data) >= i + hdr + n else None
        i += hdr + n
    return None


def parse_ndef(msg, depth=0):
    """Return a list of {'kind': ..., 'value': ...} for the records in an NDEF message."""
    out = []
    i = 0
    while i < len(msg):
        flags = msg[i]
        tnf, sr, il = flags & 0x07, bool(flags & 0x10), bool(flags & 0x08)
        i += 1
        if i >= len(msg):
            break
        tlen = msg[i]
        i += 1
        if sr:
            plen = msg[i]
            i += 1
        else:
            plen = struct.unpack(">I", msg[i:i + 4])[0]
            i += 4
        ilen = 0
        if il:
            ilen = msg[i]
            i += 1
        rtype = msg[i:i + tlen]
        i += tlen + ilen
        payload = msg[i:i + plen]
        i += plen
        if tnf == 1 and rtype == b"U" and payload:
            prefix = URI_PREFIX[payload[0]] if payload[0] < len(URI_PREFIX) else ""
            out.append(dict(kind="uri", value=prefix + payload[1:].decode("utf-8", "replace")))
        elif tnf == 1 and rtype == b"T" and payload:
            lang_len = payload[0] & 0x3F
            enc = "utf-16" if payload[0] & 0x80 else "utf-8"
            out.append(dict(kind="text", lang=payload[1:1 + lang_len].decode("ascii", "replace"),
                            value=payload[1 + lang_len:].decode(enc, "replace")))
        elif tnf == 1 and rtype == b"Sp" and depth < 3:
            out.append(dict(kind="smartposter", value=parse_ndef(payload, depth + 1)))
        elif tnf == 2:
            out.append(dict(kind="mime", value=rtype.decode("ascii", "replace"), size=len(payload)))
        elif tnf == 4:
            out.append(dict(kind="external", value=rtype.decode("ascii", "replace")))
        else:
            out.append(dict(kind="other", value="TNF %d %s" % (tnf, rtype.decode("ascii", "replace"))))
        if flags & 0x40:                               # message end
            break
    return out


def read_tag(nl, target):
    """Activate the tag through a raw socket, read its NDEF records, always release it. Returns a record list."""
    protos = target["protos"]
    if not protos & (1 << NFC_PROTO["MIFARE"]):
        return None                                    # not a Type 2 tag: report the UID only
    sock = socket.socket(AF_NFC, socket.SOCK_SEQPACKET, NFC_SOCKPROTO_RAW)
    sock.settimeout(RAW_TIMEOUT_S)
    activated = False
    try:
        raw_connect(sock, target["idx"], NFC_PROTO["MIFARE"])
        activated = True
        return parse_ndef(read_t2_ndef(sock))
    except (OSError, socket.timeout, IndexError, struct.error) as exc:
        log("read failed: %s" % exc)
        return None
    finally:
        sock.close()
        if activated:                                  # without this the kernel refuses to poll again
            deactivate(nl, target["idx"])


def proto_name(protos):
    for name in ("MIFARE", "JEWEL", "FELICA", "ISO14443", "ISO14443_B", "ISO15693", "NFC_DEP"):
        if protos & (1 << NFC_PROTO[name]):
            return {"MIFARE": "Type 2", "JEWEL": "Type 1", "FELICA": "Type 3 (FeliCa)",
                    "ISO14443": "ISO-DEP (Type 4)", "ISO14443_B": "ISO-DEP B",
                    "ISO15693": "ISO 15693", "NFC_DEP": "NFC-DEP"}[name]
    return "tag"


# ------------------------------------------------------------------------------ event broadcast
class EventServer:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            os.unlink(path)
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        try:
            import grp
            os.chown(path, 0, grp.getgrnam(SOCK_GROUP).gr_gid)
        except (KeyError, ImportError):
            pass
        os.chmod(path, 0o660)
        self.srv.listen(4)
        self.clients = []
        self.lock = threading.Lock()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            c, _ = self.srv.accept()
            c.settimeout(1.0)
            with self.lock:
                self.clients.append(c)
            log("notifier connected (%d)" % len(self.clients))

    def publish(self, event):
        line = (json.dumps(event) + "\n").encode()
        with self.lock:
            for c in list(self.clients):
                try:
                    c.sendall(line)
                except OSError:
                    self.clients.remove(c)
                    c.close()


# ------------------------------------------------------------------------------ main loop
def wait_for_adapter():
    while not os.path.isdir("/sys/class/nfc/nfc%d" % DEV_INDEX):
        time.sleep(2)


def main():
    wait_for_adapter()
    nl = NfcNetlink()
    server = EventServer(SOCK_PATH)
    last = {"uid": None, "seen": 0.0}
    errors = 0
    log("nfc-daemon running")

    err = dev_up(nl)
    if err not in (0, errno.EALREADY):
        log("dev_up: %s" % errno.errorcode.get(err, err))

    polling, poll_started = False, 0.0
    while True:
        # (Re)start polling when it is not running, and re-arm every 10 s as a safety net (resume from
        # suspend, adapter reset). EBUSY then only means "already polling".
        if not polling or time.monotonic() - poll_started > 10:
            err = start_poll(nl)
            if err == errno.EBUSY and not polling:
                release_stale_targets(nl)      # an old active target blocks polling
                err = start_poll(nl)
            if err not in (0, errno.EBUSY):
                errors += 1
                log("start_poll: %s" % errno.errorcode.get(err, err))
                if errors >= 5:                # power-cycle the adapter as a last resort
                    nl.call(CMD["DEV_DOWN"], DEV)
                    dev_up(nl)
                    errors = 0
                polling = False
                time.sleep(1)
                continue
            errors = 0
            polling, poll_started = True, time.monotonic()

        if not nl.wait_targets(2.0):
            continue                           # nothing yet: poll is still running, wait again

        polling = False                        # the kernel stops polling once it reports targets
        t0 = time.monotonic()
        targets = get_targets(nl)
        if not targets:
            continue
        tg = targets[0]
        uid = ":".join("%02x" % b for b in tg["uid"])
        now = time.monotonic()
        repeat = bool(uid) and uid == last["uid"] and now - last["seen"] < ABSENCE_S
        last["uid"], last["seen"] = uid, now

        if repeat:                             # same tag still resting: no read, no event
            time.sleep(REPOLL_RESTING_S)       # it was never activated, so polling can simply restart
            continue

        records = read_tag(nl, tg)
        read_ms = (time.monotonic() - t0) * 1000
        event = dict(time=time.time(), uid=uid, type=proto_name(tg["protos"]), records=records, read_ms=round(read_ms))
        log("tag %s %s %s (%.0f ms)" % (uid, event["type"], json.dumps(records), read_ms))
        server.publish(event)
        last["seen"] = time.monotonic()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
