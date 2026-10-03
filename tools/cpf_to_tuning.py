#!/usr/bin/env python3
"""Turn the Intel IQStudio calibration (.cpf) shipped in Microsoft's Surface Go driver package into libcamera IPU3 tuning data.

The cameras of the Surface Go were calibrated by Intel/Microsoft for the Windows driver (Skylake generation "SKL_2015ww22a" files). The same
numbers describe the sensors on Linux. Microsoft's public driver MSI contains, per sensor module, a CPFF container; this script reads the
"color matrices" record (CMC nid 18) which holds, for each calibration light source:
  * the sensor white point as chromaticity R/G and B/G (u16, 8 fractional bits) and the CIE xy of the light source (u16 each, 16 fractional bits)
  * the 3x3 colour correction matrix sensor RGB -> linear sRGB (int32, 16 fractional bits; every row sums to 1, i.e. it is applied after white balance)
The container layout is the one documented by https://github.com/dmanresa-saes/surface-ipu6-cameras (tools/decode_aiqb.py, MIT). The Skylake-era files
have no nested sections: a single AIQB chain starts at offset 0x38 with records {size u32, format u8, key u8, name_id u16}.

Only the numbers are used; nothing from the Microsoft package is redistributed by this guide. To get the files:
    curl -LO https://download.microsoft.com/download/1/9/2/19206af7-09ce-4aa6-8966-051d2e79e62b/SurfaceGo_Win10_19042_22.104.24060_WiFi_0.msi
    msiextract -C out SurfaceGo_Win10_19042_22.104.24060_WiFi_0.msi            # msitools
    # -> out/SurfaceUpdate/Drivers/Camera/OV5693/OV5693_<module>_SKY.cpf and .../OV8865/OV8865_<module>_SKY.cpf
usage: cpf_to_tuning.py <file.cpf> <base.yaml> <out.yaml> [--ccm] [--calibration tuning/calibration/<sensor>.json]
    writes base.yaml with an "Lsc" algorithm (patches/libcamera-0.7.1-ipu3-lsc.patch) with the lens
    shading tables (patches/libcamera-0.7.1-ipu3-lsc.patch). The lens shading record (CMC nid 10) holds, for each calibration light source, the gain of
    the four pixels of the Bayer quad in raster order (top left, top right, bottom left, bottom right: B, Gb, Gr, R for the BGGR sensors; u16 with 12
    fractional bits, 1.0 at the centre of the image) on a grid of 64 x 64 pixel cells of the pixel array.
    With --ccm the colour matrices are added to the Awb algorithm too (patches/libcamera-0.7.1-ipu3-ccm.patch). They are NOT in the shipped tuning:
    with the grey-world white balance they amplified every white balance error (magenta casts), see the README.
"""
import math
import struct
import sys

LIGHT = {1: "A", 2: "B", 3: "C", 4: "D50", 5: "D55", 6: "D65", 7: "D75", 8: "E", 9: "F1", 10: "F2 (cool white)", 11: "F3",
         12: "F4 (warm white)", 13: "F5", 14: "F6", 15: "F7", 16: "F8", 17: "F9", 18: "F10", 19: "F11 (TL84)", 20: "F12"}


def mccamy(x, y):
    n = (x - 0.3320) / (0.1858 - y)
    return 449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33


def records(d):
    off = 0x38
    while off + 8 <= len(d):
        size, fmt, key, nid = struct.unpack_from("<IBBH", d, off)
        if size < 8 or off + size > len(d):
            return
        yield nid, d[off + 8:off + size]
        off += size


def color_matrices(d):
    body = next(b for nid, b in records(d) if nid == 18)
    n = struct.unpack_from("<H", body, 0)[0]
    out = []
    for k in range(n):
        e = body[2 + 84 * k: 2 + 84 * (k + 1)]
        src, = struct.unpack_from("<I", e, 0)
        rg, bg, x16, y16 = struct.unpack_from("<4H", e, 4)
        m = [struct.unpack_from("<i", e, 12 + 4 * i)[0] / 65536.0 for i in range(9)]
        x, y = x16 / 65536.0, y16 / 65536.0
        valid = rg > 0 and bg > 0 and all(abs(sum(m[i:i + 3]) - 1.0) < 0.02 for i in (0, 3, 6))
        out.append({"src": src, "rg": rg / 256.0, "bg": bg / 256.0, "x": x, "y": y, "m": m, "valid": valid and 0.2 < x < 0.6})
    return out


def locus_key(rg, bg):
    """Integer key used by the IPU3 Awb algorithm: 1000 * ln(B/G over R/G) + 5000, increasing from warm to cool light."""
    return int(round(1000.0 * math.log(bg / rg))) + 5000


def lsc_sets(d, ccm_entries):
    """Lens shading tables per light source, keyed on the same illuminant locus coordinate as the colour matrices."""
    body = next(b for nid, b in records(d) if nid == 10)
    _fmt, n, w, h = struct.unpack_from("<4H", body, 0)
    p = 8
    sets = []
    for _ in range(n):
        src, _c, x16, y16 = struct.unpack_from("<4H", body, p)
        p += 8
        chans = []
        for _c in range(4):
            chans.append(struct.unpack_from("<%dH" % (w * h), body, p))
            p += w * h * 2
        x, y = x16 / 65536.0, y16 / 65536.0
        # skip tables with an all-zero channel (unused slots)
        if min(max(c) for c in chans) == 0:
            continue
        near = min(ccm_entries, key=lambda e: (e["x"] - x) ** 2 + (e["y"] - y) ** 2)
        sets.append({"src": src, "key": locus_key(near["rg"], near["bg"]), "x": x, "y": y, "chans": chans})
    sets.sort(key=lambda s: s["key"])
    out, seen = [], set()
    for s in sets:
        if s["key"] in seen:
            continue
        seen.add(s["key"])
        out.append(s)
    return w, h, out


def flow(values, indent, per_line=24):
    lines = []
    for i in range(0, len(values), per_line):
        lines.append(" " * indent + ", ".join(str(v) for v in values[i:i + per_line]))
    return ",\n".join(lines)


def main():
    argv = sys.argv[1:]
    calib = None
    if "--calibration" in argv:
        i = argv.index("--calibration")
        calib = argv[i + 1]
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    with_ccm = "--ccm" in argv
    cpf, base, out = args[:3]
    d = open(cpf, "rb").read()
    if d[:4] != b"CPFF":
        sys.exit("not a CPFF file")
    entries = [e for e in color_matrices(d) if e["valid"]]
    seen, rows = set(), []
    for e in sorted(entries, key=lambda e: locus_key(e["rg"], e["bg"])):
        k = locus_key(e["rg"], e["bg"])
        if k in seen:
            continue
        seen.add(k)
        rows.append((k, e))
    awb = ["  - Awb:", "      ccms:"]
    for k, e in rows:
        awb.append("        # %s, ~%.0f K, white point R/G %.3f B/G %.3f" % (LIGHT.get(e["src"], e["src"]), mccamy(e["x"], e["y"]), e["rg"], e["bg"]))
        awb.append("        - ct: %d" % k)
        awb.append("          ccm: [ %s ]" % ", ".join("%.4f" % v for v in e["m"]))
    w, h, sets = lsc_sets(d, entries)
    lsc = ["  - Lsc:", "      cell: 64", "      grid: [ %d, %d ]" % (w, h), "      sets:"]
    for s in sets:
        lsc.append("        # light source %s, CIE xy %.3f %.3f" % (LIGHT.get(s["src"], s["src"]), s["x"], s["y"]))
        lsc.append("        - ct: %d" % s["key"])
        for name, ch in zip(("c0", "c1", "c2", "c3"), s["chans"]):
            lsc.append("          %s: [" % name)
            lsc.append(flow(ch, 12))
            lsc.append("          ]")
    if calib:
        import json
        c = json.load(open(calib))
        lsc.append("      extra:")
        lsc.append("        # in situ correction of the colour shading left by the tables (see README): red, blue and overall (g) extra gain at BDS radius 0, 0.2 ... 1.4")
        lsc.append("        r: [ %s ]" % ", ".join("%.4f" % v for v in c["r"]))
        lsc.append("        b: [ %s ]" % ", ".join("%.4f" % v for v in c["b"]))
        lsc.append("        g: [ %s ]" % ", ".join("%.4f" % v for v in c.get("g", [1.0] * 8)))
        if "black" in c:
            blc = ["  - BlackLevelCorrection:", "      # black level of Gr, R, B, Gb (patches/libcamera-0.7.1-ipu3-blc.patch), measured with the lens covered", "      black: [ %s ]" % ", ".join(str(v) for v in c["black"])]
            if "bnr" in c:
                blc += ["      # Bayer noise reduction [cf, cg, alpha, beta, gamma, max_inf] (same patch)", "      bnr: [ %s ]" % ", ".join(str(v) for v in c["bnr"])]
    text = open(base).read()
    assert "  - Awb:\n" in text and "  - ToneMapping:\n" in text
    if with_ccm:
        text = text.replace("  - Awb:\n", "\n".join(awb) + "\n", 1)
    text = text.replace("  - ToneMapping:\n", "  - ToneMapping:\n" + "\n".join(lsc) + "\n", 1)
    if calib and "tone" in c:
        t = c["tone"]
        text = text.replace("relativeLuminanceTarget: [ 0, 0.30 ]", "relativeLuminanceTarget: [ 0, %s ]" % t["agc_target"], 1)
        text = text.replace("yTarget: [ 0, 0.18 ]", "yTarget: [ 0, %s ]" % t["agc_lower"], 1)
        text = text.replace("  - ToneMapping:\n", "  - ToneMapping:\n      # tone curve (patches/libcamera-0.7.1-ipu3-tonemapping.patch), AE targets above are matched to it\n      gamma: %s\n      contrast: %s\n" % (t["gamma"], t.get("contrast", 0)), 1)
    if calib and "black" in c:
        assert "  - BlackLevelCorrection:\n" in text
        text = text.replace("  - BlackLevelCorrection:\n", "\n".join(blc) + "\n", 1)
    open(out, "w").write(text)
    print("wrote %s: %s, %d lens shading tables of %dx%d cells" % (out, ("%d colour matrices" % len(rows)) if with_ccm else "no colour matrices", len(sets), w, h))


if __name__ == "__main__":
    main()
