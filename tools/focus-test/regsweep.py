import os, subprocess, sys, glob, json, re, numpy as np
W, H = 1600, 1200
positions = [int(x) for x in sys.argv[1].split(",")]
B = os.path.expanduser("~/libcamera-build/libcamera-0.7.1/build/src/ipa/ipu3")
tmp = "/dev/shm/rsw"; os.makedirs(tmp, exist_ok=True)
ROI = {"center": (450, 750, 600, 1000), "star(low-right)": (605, 930, 860, 1180), "circles(up-right)": (390, 520, 920, 1190),
       "lines(left-mid)": (480, 1000, 640, 800), "wedge(up-left)": (360, 640, 340, 430)}
def ten(a):
    a = a.astype(np.float32); gx = a[1:-1, 2:] - a[1:-1, :-2]; gy = a[2:, 1:-1] - a[:-2, 1:-1]
    return float(np.mean(gx * gx + gy * gy))
res = {k: [] for k in ROI}
for p in positions:
    for f in glob.glob(tmp + "/*"): os.remove(f)
    open("/dev/shm/afpos", "w").write(str(p))
    env = dict(os.environ, LIBCAMERA_IPA_MODULE_PATH=B)
    subprocess.run(["timeout", "-s", "KILL", "40", "cam", "-c", "1", "--capture=70", "-s", "width=%d,height=%d,pixelformat=NV12" % (W, H),
                    "--file=" + tmp + "/f-#.bin"], env=env, capture_output=True, text=True)
    fs = sorted(glob.glob(tmp + "/f-*.bin"))
    if len(fs) < 30: print(p, "no frames"); continue
    ms = {k: [] for k in ROI}
    for f in fs[-5:]:
        y = np.fromfile(f, dtype=np.uint8)[: W * H].reshape(H, W)
        for k, (y0, y1, x0, x1) in ROI.items(): ms[k].append(ten(y[y0:y1, x0:x1]))
    for k in ROI: res[k].append(float(np.median(ms[k])))
os.remove("/dev/shm/afpos")
print("lens  " + " ".join("%8d" % p for p in positions))
for k in ROI:
    v = res[k]; i = int(np.argmax(v))
    print("%-18s peak at %d | " % (k, positions[i]) + " ".join("%8.0f" % x for x in v))
