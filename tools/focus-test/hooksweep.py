import os, subprocess, sys, glob, json, re, numpy as np
W, H = 1600, 1200
positions = [int(x) for x in sys.argv[1].split(",")]; tag = sys.argv[2]
B = os.path.expanduser("~/libcamera-build/libcamera-0.7.1/build/src/ipa/ipu3")
tmp = "/dev/shm/hs"; os.makedirs(tmp, exist_ok=True)
def ten(a):
    a = a.astype(np.float32); gx = a[1:-1, 2:] - a[1:-1, :-2]; gy = a[2:, 1:-1] - a[:-2, 1:-1]
    return float(np.mean(gx * gx + gy * gy))
out = []
for p in positions:
    for f in glob.glob(tmp + "/*"): os.remove(f)
    open("/dev/shm/afpos", "w").write(str(p))
    env = dict(os.environ, LIBCAMERA_IPA_MODULE_PATH=B, LIBCAMERA_LOG_LEVELS="IPU3Af:DEBUG")
    r = subprocess.run(["timeout", "-s", "KILL", "40", "cam", "-c", "1", "--capture=70", "-s", "width=%d,height=%d,pixelformat=NV12" % (W, H),
                        "--file=" + tmp + "/f-#.bin"], env=env, capture_output=True, text=True)
    var = [float(m) for m in re.findall(r"HOOK focus %d variance ([0-9.e+]+)" % p, r.stderr)]
    fs = sorted(glob.glob(tmp + "/f-*.bin"))
    if len(fs) < 30: print(p, "no frames", len(fs)); continue
    m = []
    for f in fs[-5:]:
        y = np.fromfile(f, dtype=np.uint8)[: W * H].reshape(H, W)
        m.append((ten(y[105:470, 510:860]), ten(y[30:740, 360:1420])))
    m = np.median(np.array(m), axis=0)
    v = float(np.median(var[-10:])) if var else float("nan")
    out.append((p, float(m[0]), float(m[1]), v))
    print("lens %4d  star %8.1f  chart %8.1f  afvar %10.1f" % (p, m[0], m[1], v), flush=True)
os.remove("/dev/shm/afpos")
json.dump(out, open("/dev/shm/hooksweep_%s.json" % tag, "w"))
