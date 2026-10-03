import sys, math
vals = [float(x) for x in open(sys.argv[1]).read().split()]
n = 8
pts = [0.2 * i for i in range(n)]
out = []
for ch in range(3):
    v = vals[ch*n:(ch+1)*n]
    # fit log f = a r^2 + b r^4 on r = 0 .. 1.2 (the last two points are clamped extrapolation)
    xs = [(p**2, p**4, math.log(max(f, 1e-3))) for p, f in zip(pts[:7], v[:7])]
    s11 = sum(a*a for a, b, y in xs); s12 = sum(a*b for a, b, y in xs); s22 = sum(b*b for a, b, y in xs)
    t1 = sum(a*y for a, b, y in xs); t2 = sum(b*y for a, b, y in xs)
    det = s11*s22 - s12*s12
    a = (t1*s22 - t2*s12)/det; b = (s11*t2 - s12*t1)/det
    sm = [math.exp(a*p**2 + b*p**4) for p in pts]
    sm[7] = sm[6]; sm[0] = 1.0
    out += sm
    print("ch%d raw %s" % (ch, " ".join("%.2f" % x for x in v)))
    print("    smooth %s" % " ".join("%.4f" % x for x in sm))
open(sys.argv[2], "w").write(" ".join("%.4f" % x for x in out))
