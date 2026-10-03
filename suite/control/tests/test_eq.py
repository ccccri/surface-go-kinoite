"""Checks of the equaliser maths and files (no hardware). Run: python3 tests/test_eq.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import eq  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


b = [{"type": "peak", "freq": 1000, "gain": 6, "q": 1.0, "on": True}]
check("peak +6 dB at its centre", abs(eq.magnitude_db(b, 1000) - 6) < 0.01)
check("peak is ~0 far away", abs(eq.magnitude_db(b, 50)) < 0.3 and abs(eq.magnitude_db(b, 15000)) < 0.3)
b = [{"type": "lowshelf", "freq": 200, "gain": -6, "q": 0.71, "on": True}]
check("low shelf -6 dB at 20 Hz, 0 at 5 kHz", abs(eq.magnitude_db(b, 20) + 6) < 0.3 and abs(eq.magnitude_db(b, 5000)) < 0.1)
b = [{"type": "highshelf", "freq": 6000, "gain": 4, "q": 0.71, "on": True}]
check("high shelf +4 dB at 18 kHz, 0 at 100 Hz", abs(eq.magnitude_db(b, 18000) - 4) < 0.4 and abs(eq.magnitude_db(b, 100)) < 0.1)
b = [{"type": "highpass", "freq": 120, "gain": 0, "q": 0.71, "on": True}]
check("high-pass cuts 20 Hz by more than 20 dB, passes 2 kHz", eq.magnitude_db(b, 20) < -20 and abs(eq.magnitude_db(b, 2000)) < 0.3)
check("off band is flat", abs(eq.magnitude_db([{"type": "peak", "freq": 1000, "gain": 9, "q": 1, "on": False}], 1000)) < 1e-9)
check("flat set is the identity", all(abs(eq.magnitude_db(eq.flat_bands(), f)) < 1e-9 for f in (30, 300, 3000, 12000)))

txt = """Preamp: -6.1 dB
Filter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.70
Filter 2: ON PK Fc 1000 Hz Gain -2,5 dB Q 1.41
Filter 3: ON HSC Fc 8000 Hz Gain -3.0 dB Q 0.71
Filter 4: OFF PK Fc 3000 Hz Gain 2 dB BW Oct 0.5
Filter 5: ON NO Fc 100 Hz Q 1
garbage line
"""
s, notes = eq.parse_apo(txt)
check("APO file: preamp, low shelf in slot 1, high shelf in slot 10", s and s["preamp"] == -6.1 and s["bands"][0]["type"] == "lowshelf" and s["bands"][9]["type"] == "highshelf")
check("APO file: comma decimal, BW Oct converted to Q, notch refused with a note", s["bands"][1]["gain"] == -2.5 and any("notch" in n for n in notes))
check("not an APO file is refused", eq.parse_apo("hello")[0] is None)
many = "\n".join("Filter %d: ON PK Fc %d Hz Gain %d dB Q 1" % (i, 100 + i * 500, (i % 7) - 3) for i in range(1, 16))
s2, n2 = eq.parse_apo(many)
check("15 peaking filters: 10 used, a note says so", len(s2["bands"]) == 10 and any("weakest" in x for x in n2))
s3, _ = eq.parse_apo(eq.export_apo(s))
check("export then import keeps preamp and filters", abs(s3["preamp"] - s["preamp"]) < 0.06 and s3["bands"][0]["type"] == "lowshelf")
bad = eq._normalise({"boost": 9999, "preamp": -999, "bands": [{"type": "evil", "freq": 1e9, "gain": 1e9, "q": -5, "on": 1}] * 30})
check("out of range values are clamped, always 10 bands", len(bad["bands"]) == 10 and bad["boost"] == 180 and bad["preamp"] == -24 and bad["bands"][0]["freq"] == 20000 and bad["bands"][0]["type"] == "peak")
check("a middle band cannot become a shelf", eq._normalise({"bands": [{"type": "lowshelf"}] * 10})["bands"][4]["type"] == "peak")
t = eq.conf_text(eq.new_set(125))
check("config has 28 biquads (14 per channel) and the speaker boost", t.count("bq_") == 28 and "1.95312" in t)
p = eq.params(eq.new_set(125))
check("params cover every biquad of both channels", len(p) == 88 and p["gainL:Mult"] == p["gainR:Mult"])
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
