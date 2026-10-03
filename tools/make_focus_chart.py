#!/usr/bin/env python3
"""Generate a printable A4 focus/sharpness chart (SVG + PostScript; PDF through Ghostscript).

Everything is black/white/grey vector art: the printer's colour accuracy does not matter, only contrast.
Print at 100% ("actual size", no fit-to-page) and check that the scale bar measures 10 cm.

Contents: Siemens stars (resolution vs. distance from the centre), slanted edges (for an MTF measurement),
line-pair groups, text in many sizes, a grey step wedge, a 10 cm scale and corner marks.
usage: make_focus_chart.py [outdir]
"""
import math
import os
import subprocess
import sys

W, H = 210.0, 297.0          # A4 in mm, origin top-left, y down
out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
items = []                   # drawing list, backend independent


def rect(x, y, w, h, gray=0.0):
    items.append(("poly", [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], gray))


def poly(pts, gray=0.0):
    items.append(("poly", pts, gray))


def line(x1, y1, x2, y2, width=0.3, gray=0.0):
    items.append(("line", x1, y1, x2, y2, width, gray))


def text(x, y, s, pt, bold=False, anchor="start", gray=0.0):
    items.append(("text", x, y, s, pt, bold, anchor, gray))


def circle_outline(cx, cy, r, width=0.3):
    pts = [(cx + r * math.cos(a * math.pi / 90), cy + r * math.sin(a * math.pi / 90)) for a in range(181)]
    for a, b in zip(pts, pts[1:]):
        line(a[0], a[1], b[0], b[1], width)


def siemens_star(cx, cy, r, cycles):
    n = cycles * 2
    for i in range(0, n, 2):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        steps = 3
        pts = [(cx, cy)]
        for k in range(steps + 1):
            a = a0 + (a1 - a0) * k / steps
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        poly(pts, 0.0)
    circle_outline(cx, cy, r, 0.25)


def rotated_square(cx, cy, size, angle_deg, gray=0.0):
    a = math.radians(angle_deg)
    h = size / 2
    pts = []
    for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h)):
        pts.append((cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)))
    poly(pts, gray)


def bars(x, y, width, length, count, vertical):
    """count black bars of the given width separated by white gaps of the same width."""
    for i in range(count):
        off = i * 2 * width
        if vertical:
            rect(x + off, y, width, length)
        else:
            rect(x, y + off, length, width)


# ---- frame, title, scale --------------------------------------------------------------------------------------------
rect(0, 0, 0.001, 0.001, 1.0)    # make sure the bounding box is the full page
line(6, 6, W - 6, 6, 0.8); line(W - 6, 6, W - 6, H - 6, 0.8); line(W - 6, H - 6, 6, H - 6, 0.8); line(6, H - 6, 6, 6, 0.8)
text(W / 2, 13.5, "Surface Go camera focus & sharpness chart", 13, bold=True, anchor="middle")
text(W / 2, 19, "Print at 100% (Actual size, NOT fit to page). Hold the camera parallel to the sheet; the page should fill the view.",
     6.3, anchor="middle")
line(20, 25, 120, 25, 0.5)
for i in range(11):
    line(20 + i * 10, 23.3 if i % 5 else 22.3, 20 + i * 10, 26.7 if i % 5 else 27.7, 0.4)
text(122, 26.3, "<- this bar must measure 10 cm", 6.3)

# ---- large Siemens star (centre) --------------------------------------------------------------------------------------
siemens_star(75, 82, 50, 36)
text(75, 138.5, "Siemens star: where the spokes blur into grey = resolution limit", 6.3, anchor="middle")

# ---- small stars, slanted edges (right column) ----------------------------------------------------------------------
siemens_star(170, 50, 19, 24)
siemens_star(170, 92, 19, 24)
rotated_square(170, 132, 24, 5)
rotated_square(140, 132, 12, 5)
text(170, 148, "slanted edges (5 deg)", 6.3, anchor="middle")

# ---- line-pair groups -------------------------------------------------------------------------------------------------
widths = [4.0, 3.0, 2.5, 2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3]
x = 12
text(12, 154.5, "Line pairs (mm): " + "  ".join(("%g" % w) for w in widths), 5.6)
for w in widths:
    count = 3 if w >= 2.5 else 5            # keep the horizontal groups short so they never reach the text below
    span = count * 2 * w - w
    bars(x, 158, w, 14, count, vertical=True)            # vertical bars, 14 mm tall
    bars(x, 175, w, span, count, vertical=False)         # horizontal bars
    x += span + 3
    if x > W - 14:
        break

# ---- text in many sizes -----------------------------------------------------------------------------------------------
y = 204
sample = "The quick brown fox jumps over the lazy dog 0123456789"
for pt in (5, 6, 7, 8, 10, 12, 16):
    text(12, y, "%gpt  %s" % (pt, sample if pt < 16 else sample[:40]), pt)
    y += pt * 0.36 + 3.2

# ---- grey step wedge ---------------------------------------------------------------------------------------------------
wy = 259
text(12, wy - 2.5, "Grey steps (neutral? flat?)", 6.3)
for i in range(11):
    rect(12 + i * 16.8, wy, 16.8, 14, 1.0 - i / 10.0)
    text(12 + i * 16.8 + 8.4, wy + 18.5, "%d%%" % (i * 10), 5.6, anchor="middle")
line(12, wy, 12 + 11 * 16.8, wy, 0.2); line(12, wy + 14, 12 + 11 * 16.8, wy + 14, 0.2)

# ---- fine crosshair grid (field flatness / distortion) ----------------------------------------------------------------
for cx, cy in ((12, 33), (W - 12, 33), (12, H - 14), (W - 12, H - 14)):     # corner crosses: field flatness / tilt
    line(cx - 3, cy, cx + 3, cy, 0.3); line(cx, cy - 3, cx, cy + 3, 0.3)
text(W / 2, H - 9, "Test at ~20 cm, ~40 cm and ~80 cm. Note which distance the autofocus fails at.", 6.3, anchor="middle")


# ---- backends ---------------------------------------------------------------------------------------------------------
def esc_xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def g255(gray):
    v = int(round(gray * 255))
    return "rgb(%d,%d,%d)" % (v, v, v)


svg = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">',
       '<rect width="210" height="297" fill="white"/>']
for it in items:
    if it[0] == "poly":
        svg.append('<polygon fill="%s" points="%s"/>' % (g255(it[2]), " ".join("%.3f,%.3f" % p for p in it[1])))
    elif it[0] == "line":
        svg.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="%s" stroke-width="%.3f"/>'
                   % (it[1], it[2], it[3], it[4], g255(it[6]), it[5]))
    else:
        _, x, y, s, pt, bold, anchor, gray = it
        svg.append('<text x="%.3f" y="%.3f" font-family="Liberation Sans, Helvetica, Arial, sans-serif" font-size="%.3f" '
                   'font-weight="%s" text-anchor="%s" fill="%s">%s</text>'
                   % (x, y, pt * 25.4 / 72, "bold" if bold else "normal", anchor, g255(gray), esc_xml(s)))
svg.append("</svg>")

PT = 72 / 25.4
ps = ["%!PS-Adobe-3.0", "%%BoundingBox: 0 0 596 842", "<< /PageSize [595.276 841.89] >> setpagedevice",
      "1 setgray 0 0 595.276 841.89 rectfill", "0 setlinecap"]
for it in items:
    if it[0] == "poly":
        pts = it[1]
        ps.append("%.3f setgray newpath %.3f %.3f moveto %s closepath fill"
                  % (it[2], pts[0][0] * PT, (H - pts[0][1]) * PT,
                     " ".join("%.3f %.3f lineto" % (p[0] * PT, (H - p[1]) * PT) for p in pts[1:])))
    elif it[0] == "line":
        ps.append("%.3f setgray %.3f setlinewidth newpath %.3f %.3f moveto %.3f %.3f lineto stroke"
                  % (it[6], it[5] * PT, it[1] * PT, (H - it[2]) * PT, it[3] * PT, (H - it[4]) * PT))
    else:
        _, x, y, s, pt, bold, anchor, gray = it
        s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        font = "Helvetica-Bold" if bold else "Helvetica"
        move = "%.3f %.3f moveto" % (x * PT, (H - y) * PT)
        if anchor == "middle":
            move += " (%s) stringwidth pop 2 div neg 0 rmoveto" % s
        ps.append("%.3f setgray /%s findfont %.3f scalefont setfont %s (%s) show" % (gray, font, pt, move, s))
ps.append("showpage")

os.makedirs(out_dir, exist_ok=True)
base = os.path.join(out_dir, "focus-chart-A4")
open(base + ".svg", "w").write("\n".join(svg))
open(base + ".ps", "w").write("\n".join(ps))
subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", "-dPDFSETTINGS=/prepress", "-dEmbedAllFonts=true",
                "-sPAPERSIZE=a4", "-sOutputFile=" + base + ".pdf", base + ".ps"], check=True)
os.remove(base + ".ps")
print("wrote", base + ".svg", "and", base + ".pdf")
