import os, subprocess, sys, glob, re, numpy as np
W, H = 1600, 1200
n = int(sys.argv[1]); B = os.path.expanduser("~/libcamera-build/libcamera-0.7.1/build/src/ipa/ipu3")
tmp = "/dev/shm/aft"; os.makedirs(tmp, exist_ok=True)
try: os.remove("/dev/shm/afpos")
except FileNotFoundError: pass
def ten(a):
    a = a.astype(np.float32); gx = a[1:-1, 2:] - a[1:-1, :-2]; gy = a[2:, 1:-1] - a[:-2, 1:-1]
    return float(np.mean(gx * gx + gy * gy))
for i in range(n):
    for f in glob.glob(tmp + "/*.bin"): os.remove(f)
    env = dict(os.environ, LIBCAMERA_IPA_MODULE_PATH=B, LIBCAMERA_LOG_LEVELS="IPU3Af:DEBUG")
    r = subprocess.run(["timeout", "-s", "KILL", "40", "cam", "-c", "1", "--capture=150", "-s", "width=%d,height=%d,pixelformat=NV12" % (W, H),
                        "--file=" + tmp + "/f-#.bin"], env=env, capture_output=True, text=True)
    steps = re.findall(r"AFVAR step (\d+) variance ([0-9.e+]+)", r.stderr)
    last = steps[-1][0] if steps else "?"
    moves = re.findall(r"Previous step is (\d+) Current step is (\d+)", r.stderr)
    fs = sorted(glob.glob(tmp + "/f-*.bin"))
    if not fs: print(i, "no frames"); continue
    y = np.fromfile(fs[-1], dtype=np.uint8)[: W * H].reshape(H, W)
    coarse = [int(b) for a, b in moves if int(b) - int(a) == 30]
    print("run %2d  final lens %-5s star %7.1f  coarse steps reached %s  scans %d" % (i, last, ten(y[105:470, 510:860]),
          (max(coarse) if coarse else None), sum(1 for a, b in moves if b == "30" or b == "0")), flush=True)
    open("/dev/shm/aft_run%02d.log" % i, "w").write(r.stderr)
