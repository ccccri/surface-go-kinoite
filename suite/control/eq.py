"""Output equaliser of Surface Control: ten parametric bands on the speaker filter chain (PipeWire builtin biquads, coefficients set live),
one set for the speakers and one for the headphone jack that can be kept in sync. No UI code here."""
import math
import os
import re

import backend

RATE = 48000
N = 10
TYPES = ("peak", "lowshelf", "highshelf", "lowpass", "highpass", "notch")
CONF = os.path.expanduser("~/.config/pipewire/pipewire.conf.d/10-speaker-gain.conf")
NODE = "boosted_speakers"
OUTPUTS = ("speaker", "headphones")


# A band slot can hold the kinds listed here (each kind is its own biquad in the chain, neutral when not used): the ends can be shelves or
# cut filters, the middle bands are peaking filters. The filter chain cannot change a biquad's kind while running, so every kind a slot may use exists.
SLOT_KINDS = {0: ("peak", "lowshelf", "highpass"), N - 1: ("peak", "highshelf", "lowpass")}
LABEL = {"peak": "bq_peaking", "lowshelf": "bq_lowshelf", "highshelf": "bq_highshelf", "highpass": "bq_highpass", "lowpass": "bq_lowpass"}
SUFFIX = {"peak": "p", "lowshelf": "s", "highshelf": "s", "highpass": "c", "lowpass": "c"}


def kinds(i):
    return SLOT_KINDS.get(i, ("peak",))


def flat_bands():
    freqs = (60, 120, 250, 500, 1000, 2000, 4000, 8000, 12000, 14000)
    types = ["lowshelf"] + ["peak"] * 8 + ["highshelf"]
    return [{"type": t, "freq": float(f), "gain": 0.0, "q": 0.71 if t != "peak" else 1.0, "on": True} for t, f in zip(types, freqs)]


def new_set(boost=120):
    return {"boost": boost, "preamp": 0.0, "bands": flat_bands()}


def coefficients(b, rate=RATE):
    """RBJ cookbook biquad (b0 b1 b2 a0 a1 a2) for one band; an unused or neutral band is the identity."""
    if not b.get("on", True):
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    f = max(10.0, min(float(b["freq"]), rate / 2 * 0.98))
    q = max(0.1, min(float(b["q"]), 20.0))
    g = float(b["gain"])
    t = b["type"]
    if t in ("peak", "lowshelf", "highshelf") and abs(g) < 1e-4:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    A = 10 ** (g / 40.0)
    w = 2 * math.pi * f / rate
    cw, sw = math.cos(w), math.sin(w)
    al = sw / (2 * q)
    if t == "peak":
        return (1 + al * A, -2 * cw, 1 - al * A, 1 + al / A, -2 * cw, 1 - al / A)
    s = 2 * math.sqrt(A) * al
    if t == "lowshelf":
        return (A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s),
                (A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s)
    if t == "highshelf":
        return (A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s),
                (A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s)
    if t == "lowpass":
        return ((1 - cw) / 2, 1 - cw, (1 - cw) / 2, 1 + al, -2 * cw, 1 - al)
    if t == "highpass":
        return ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2, 1 + al, -2 * cw, 1 - al)
    if t == "notch":
        return (1.0, -2 * cw, 1.0, 1 + al, -2 * cw, 1 - al)
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def normalised(c):
    """Coefficients divided by a0, so that a0 is 1: the raw biquad of the filter chain takes them as they are."""
    b0, b1, b2, a0, a1, a2 = c
    return (b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0)


def magnitude_db(bands, freq, rate=RATE):
    """Response of all bands at one frequency, for tests and the graph."""
    w = 2 * math.pi * freq / rate
    total = 0.0
    for b in bands:
        b0, b1, b2, a0, a1, a2 = coefficients(b, rate)
        num = b0 * b0 + b1 * b1 + b2 * b2 + 2 * (b0 * b1 + b1 * b2) * math.cos(w) + 2 * b0 * b2 * math.cos(2 * w)
        den = a0 * a0 + a1 * a1 + a2 * a2 + 2 * (a0 * a1 + a1 * a2) * math.cos(w) + 2 * a0 * a2 * math.cos(2 * w)
        total += 10 * math.log10(max(num, 1e-30) / max(den, 1e-30))
    return total


def _normalise(s):
    """A set from the file or a caller: right number of bands, valid types, numbers in range."""
    out = {"boost": float(max(100, min(180, s.get("boost", 120)))), "preamp": float(max(-24, min(12, s.get("preamp", 0.0)))), "bands": []}
    bands = list(s.get("bands", []))[:N]
    for i, b in enumerate(bands):
        out["bands"].append({"type": b.get("type") if b.get("type") in kinds(i) else "peak",
                             "freq": float(max(20, min(20000, b.get("freq", 1000)))), "gain": float(max(-24, min(24, b.get("gain", 0)))),
                             "q": float(max(0.1, min(20, b.get("q", 1.0)))), "on": bool(b.get("on", True))})
    flat = flat_bands()
    while len(out["bands"]) < N:
        out["bands"].append(dict(flat[len(out["bands"])]))
    return out


# ---- state ----
def available():
    try:
        return "eqL0p" in open(CONF).read()
    except OSError:
        return False


def _first_boost():
    """The boost you had before the equaliser existed: from the saved copy of the old chain if there is one, else from the running config."""
    try:
        m = re.search(r'"Mult"\s*=\s*([0-9.]+)', open(CONF + ".before-eq").read())
        if m:
            return round(float(m.group(1)) ** (1 / 3) * 100)
    except (OSError, ValueError):
        pass
    return backend.speaker_boost()


def load():
    d = backend._audio_load()
    eq = d.get("eq", {})
    sets = eq.get("sets", {})
    speaker = _normalise(sets["speaker"]) if "speaker" in sets else new_set(_first_boost())
    headphones = _normalise(sets["headphones"]) if "headphones" in sets else new_set(100)
    return {"sync": bool(eq.get("sync", True)), "sets": {"speaker": speaker, "headphones": headphones}}


def _store(state):
    d = backend._audio_load()
    d["eq"] = state
    backend._audio_save(d)


def active_output():
    """'headphones' while the jack is in use, else 'speaker' (the active port of the sound card)."""
    rc, out = backend.run(["pactl", "list", "sinks"], timeout=6)
    m = re.search(r"Name: alsa_output[^\n]*\n(?:.*\n)*?\s*Active Port: ([^\n]+)", out)
    return "headphones" if m and "headphone" in m.group(1).lower() else "speaker"


def effective(state, output):
    """The set that sounds: the speaker set for both outputs while they are synced."""
    return state["sets"]["speaker" if state["sync"] else output]


def neutral(kind):
    """Controls that make a biquad of this kind do nothing."""
    return {"Freq": 5.0 if kind == "highpass" else 23000.0 if kind == "lowpass" else 1000.0, "Q": 0.707, "Gain": 0.0}


def params(s):
    """Filter chain controls for one set, both channels: every biquad of every slot, the ones not in use neutral."""
    p = {}
    pre = 10 ** (s["preamp"] / 20.0)
    mult = (s["boost"] / 100.0) ** 3
    for ch in "LR":
        p[f"pre{ch}:Mult"] = pre
        p[f"gain{ch}:Mult"] = mult
        for i, band in enumerate(s["bands"]):
            for kind in kinds(i):
                c = neutral(kind)
                if band["on"] and band["type"] == kind:
                    c = {"Freq": band["freq"], "Q": band["q"], "Gain": band["gain"]}
                for k, v in c.items():
                    p[f"eq{ch}{i}{kind[0]}:{k}"] = v
    return p


def apply(s):
    """Live, to the running filter chain."""
    return backend._pw_set(NODE, params(s))


def apply_active():
    state = load()
    return apply(effective(state, active_output()))


def set_output(output, s):
    """A change from the panel: store it, write the file the chain starts from, and apply it now if this output (or the synced one) is playing."""
    state = load()
    state["sets"][output] = _normalise(s)
    _store(state)
    write_conf(effective(state, "speaker"))
    if state["sync"] or active_output() == output:
        apply(effective(state, active_output()))
    return True


def set_sync(on):
    state = load()
    state["sync"] = bool(on)
    if on:
        state["sets"]["headphones"] = dict(state["sets"]["speaker"])
    _store(state)
    apply(effective(state, active_output()))


# ---- the configuration file ----
def conf_text(s):
    pre = 10 ** (s["preamp"] / 20.0)
    mult = (s["boost"] / 100.0) ** 3
    nodes = []
    links = []
    ctl_of = {}
    for i, band in enumerate(s["bands"]):
        for kind in kinds(i):
            c = neutral(kind)
            if band["on"] and band["type"] == kind:
                c = {"Freq": band["freq"], "Q": band["q"], "Gain": band["gain"]}
            ctl_of[(i, kind)] = c
    for ch in "LR":
        nodes.append(f'          {{ type = builtin name = pre{ch} label = linear control = {{ "Mult" = {pre:.5f} "Add" = 0.0 }} }}')
        prev = f"pre{ch}"
        for i in range(N):
            for kind in kinds(i):
                name = f"eq{ch}{i}{kind[0]}"
                c = ctl_of[(i, kind)]
                nodes.append(f'          {{ type = builtin name = {name} label = {LABEL[kind]} control = {{ "Freq" = {c["Freq"]:.2f} "Q" = {c["Q"]:.3f} "Gain" = {c["Gain"]:.3f} }} }}')
                links.append(f'          {{ output = "{prev}:Out" input = "{name}:In" }}')
                prev = name
        nodes.append(f'          {{ type = builtin name = gain{ch} label = linear control = {{ "Mult" = {mult:.5f} "Add" = 0.0 }} }}')
        links.append(f'          {{ output = "{prev}:Out" input = "gain{ch}:In" }}')
    return f'''# Speaker chain of Surface Control: pre-amplifier, ten parametric bands (biquads whose frequency, Q and gain are set live), then the speaker boost.
# The Surface Go speakers are quiet: the boost is a fixed digital gain, (percent / 100)^3 because PipeWire volumes are cubic. The physical sink
# must stay at 100%. This file is rewritten by Surface Control; the values here are what the chain starts with.
context.modules = [
  {{ name = libpipewire-module-filter-chain
    args = {{
      node.description = "Built-in Speakers (boosted)"
      media.name       = "Built-in Speakers (boosted)"
      filter.graph = {{
        nodes = [
{chr(10).join(nodes)}
        ]
        links = [
{chr(10).join(links)}
        ]
        inputs  = [ "preL:In" "preR:In" ]
        outputs = [ "gainL:Out" "gainR:Out" ]
      }}
      audio.channels = 2
      audio.position = [ FL FR ]
      capture.props = {{
        node.name = "boosted_speakers"
        media.class = Audio/Sink
        priority.session = 2000
        priority.driver = 2000
      }}
      playback.props = {{
        node.name = "boosted_speakers_out"
        node.passive = true
        target.object = "alsa_output.pci-0000_00_1f.3.analog-stereo"
      }}
    }}
  }}
]
'''


def write_conf(s):
    if not available():
        return False
    open(CONF, "w").write(conf_text(s))
    return True


def enable():
    """Replace the plain boost chain by the equaliser chain and restart the sound server (audio and cameras reconnect)."""
    state = load()
    try:
        backup = CONF + ".before-eq"
        if not os.path.exists(backup) and os.path.exists(CONF):
            open(backup, "w").write(open(CONF).read())
        open(CONF, "w").write(conf_text(effective(state, "speaker")))
    except OSError as e:
        return False, str(e)
    backend._node_ids.clear()
    rc, out = backend.run(["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service", "wireplumber.service"], timeout=40)
    return rc == 0, out


# ---- presets: built-in and your own, one list ----
def _pk(freq, gain, q=1.0):
    return {"type": "peak", "freq": float(freq), "gain": float(gain), "q": q, "on": True}


def builtin_presets():
    def mk(boost=None, preamp=0.0, edits=None):
        s = new_set(boost or 120)
        s["preamp"] = preamp
        for i, (t, f, g, q) in (edits or {}).items():
            s["bands"][i] = {"type": t, "freq": float(f), "gain": float(g), "q": q, "on": True}
        return s
    return {
        "Flat": mk(),
        "Bass boost": mk(preamp=-4, edits={0: ("lowshelf", 90, 6, 0.7), 1: ("peak", 150, 3, 1.0)}),
        "Warm": mk(preamp=-2, edits={0: ("lowshelf", 120, 3, 0.7), 8: ("peak", 12000, -2, 1.0), 9: ("highshelf", 9000, -3, 0.7)}),
        "Bright": mk(preamp=-3, edits={0: ("lowshelf", 100, -2, 0.7), 7: ("peak", 6000, 2, 1.0), 9: ("highshelf", 9000, 5, 0.7)}),
        "Vocal clarity": mk(preamp=-2, edits={0: ("lowshelf", 150, -3, 0.7), 4: ("peak", 1000, 1.5, 1.0), 5: ("peak", 3000, 4, 1.2), 7: ("peak", 6000, 1.5, 1.0)}),
        "Loudness (smile)": mk(preamp=-5, edits={0: ("lowshelf", 80, 6, 0.7), 1: ("peak", 160, 2, 1.0), 6: ("peak", 4000, 2, 1.0), 9: ("highshelf", 9000, 5, 0.7)}),
        "Tame harshness": mk(preamp=0, edits={6: ("peak", 3500, -3, 1.5), 7: ("peak", 6500, -3, 1.5), 9: ("highshelf", 10000, -2, 0.7)}),
    }


def preset_names():
    user = backend._audio_load().get("presets", {}).get("eq", {})
    hidden = backend.hidden_presets("eq")
    return [{"name": n, "builtin": True} for n in builtin_presets() if n not in hidden] + [{"name": n, "builtin": False} for n in sorted(user, key=str.lower)]


def preset_set(name):
    b = builtin_presets()
    if name in b and name not in backend.hidden_presets("eq"):
        return b[name]
    s = backend._audio_load().get("presets", {}).get("eq", {}).get(name)
    return _normalise(s) if s else None


def save_preset(name, s):
    name = name.strip()
    if not name or (name in builtin_presets() and name not in backend.hidden_presets("eq")):
        return "invalid"
    d = backend._audio_load()
    d.setdefault("presets", {}).setdefault("eq", {})[name] = _normalise(s)
    backend._audio_save(d)
    return "ok"


def delete_preset(name):
    if name in builtin_presets():
        backend.hide_builtin("eq", name)      # a built-in one: hidden until the installer restores the defaults
        return
    d = backend._audio_load()
    d.get("presets", {}).get("eq", {}).pop(name, None)
    backend._audio_save(d)


# ---- Equalizer APO / AutoEQ text files ("Preamp: -6 dB", "Filter 1: ON PK Fc 105 Hz Gain -2.5 dB Q 0.70") ----
_APO = {"PK": "peak", "PEQ": "peak", "MODAL": "peak", "LS": "lowshelf", "LSC": "lowshelf", "LSQ": "lowshelf", "HS": "highshelf", "HSC": "highshelf",
        "HSQ": "highshelf", "LP": "lowpass", "LPQ": "lowpass", "HP": "highpass", "HPQ": "highpass", "NO": "notch"}


def parse_apo(text):
    """Returns (set, notes). The text format is what AutoEQ, Equalizer APO and EasyEffects share."""
    notes = []
    pre = 0.0
    bands = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"Preamp:\s*([-+]?\d+(?:[.,]\d+)?)\s*dB", line, re.I)
        if m:
            pre = float(m.group(1).replace(",", "."))
            continue
        m = re.match(r"Filter\s*\d*:\s*(ON|OFF)\s+(\w+)\s+Fc\s+([\d.,]+)\s*Hz(?:\s+Gain\s+([-+]?[\d.,]+)\s*dB)?(?:\s+Q\s+([\d.,]+))?(?:\s+BW\s+Oct\s+([\d.,]+))?", line, re.I)
        if not m:
            continue
        kind = _APO.get(m.group(2).upper())
        if not kind:
            notes.append("skipped a %s filter" % m.group(2))
            continue
        f = float(m.group(3).replace(",", "."))
        g = float((m.group(4) or "0").replace(",", "."))
        if m.group(5):
            q = float(m.group(5).replace(",", "."))
        elif m.group(6):
            bw = float(m.group(6).replace(",", "."))
            q = math.sqrt(2 ** bw) / (2 ** bw - 1) if bw > 0 else 1.0
        else:
            q = 0.71
        bands.append({"type": kind, "freq": f, "gain": g, "q": q, "on": m.group(1).upper() == "ON"})
    if not bands:
        return None, ["no filters found: is this an Equalizer APO / AutoEQ text file?"]
    s = new_set(100)
    s["preamp"] = pre
    s["bands"] = assign_slots(bands, notes)
    return _normalise(s), notes


def assign_slots(bands, notes):
    """Puts imported filters into the ten slots: the first low shelf (or high-pass) in slot 1, the first high shelf (or low-pass) in slot 10,
    peaking filters in the middle slots by frequency; what does not fit is dropped (the weakest first) and said."""
    slots = [None] * N
    peaks = []
    for b in bands:
        t = b["type"]
        if t == "lowshelf" and (slots[0] is None or slots[0]["type"] == "highpass"):
            slots[0] = b
        elif t == "highpass" and slots[0] is None:
            slots[0] = b
        elif t == "highshelf" and (slots[N - 1] is None or slots[N - 1]["type"] == "lowpass"):
            slots[N - 1] = b
        elif t == "lowpass" and slots[N - 1] is None:
            slots[N - 1] = b
        elif t == "peak":
            peaks.append(b)
        else:
            notes.append("a %s filter at %d Hz does not fit (one shelf or cut per end, no notch): skipped" % (t, round(b["freq"])))
    free = [i for i in range(N) if slots[i] is None]
    middle = [i for i in range(1, N - 1) if slots[i] is None]
    peaks.sort(key=lambda b: -abs(b["gain"]))
    room = len(middle) + sum(1 for i in (0, N - 1) if slots[i] is None)
    if len(peaks) > room:
        notes.append("%d peaking filters but room for %d: the weakest %d are skipped" % (len(peaks), room, len(peaks) - room))
        peaks = peaks[:room]
    peaks.sort(key=lambda b: b["freq"])
    order = [i for i in range(N) if slots[i] is None]
    # fill free slots in frequency order: low frequencies in the low slots
    for i, b in zip(order, peaks):
        slots[i] = b
    flat = flat_bands()
    return [slots[i] if slots[i] is not None else flat[i] for i in range(N)]


def export_apo(s):
    names = {"peak": "PK", "lowshelf": "LSC", "highshelf": "HSC", "lowpass": "LP", "highpass": "HP", "notch": "NO"}
    lines = ["Preamp: %.1f dB" % s["preamp"]]
    for i, b in enumerate(s["bands"], 1):
        lines.append("Filter %d: %s %s Fc %d Hz Gain %.1f dB Q %.2f" % (i, "ON" if b["on"] else "OFF", names[b["type"]], round(b["freq"]), b["gain"], b["q"]))
    return "\n".join(lines) + "\n"


def verify():
    """Compares the running chain with the stored set of the output in use: [(control, expected, actual)] of what differs, [] when all is applied."""
    if not available():
        return None
    state = load()
    exp = params(effective(state, active_output()))
    got = backend.pw_params(NODE)
    if not got:
        return [("the equaliser chain is not running", "-", "-")]
    bad = []
    for k, v in exp.items():
        a = got.get(k)
        if a is None or abs(a - v) > 1e-3 * max(1.0, abs(v)):
            bad.append((k, round(v, 4), None if a is None else round(a, 4)))
    return bad


def disable():
    """Back to the plain boost chain saved when the equaliser was first enabled (10-speaker-gain.conf.before-eq), and a restart of the sound server."""
    backup = CONF + ".before-eq"
    try:
        text = open(backup).read()
    except OSError:
        return False, "no saved copy of the old chain"
    open(CONF, "w").write(text)
    backend._node_ids.clear()
    rc, out = backend.run(["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service", "wireplumber.service"], timeout=40)
    return rc == 0, out
