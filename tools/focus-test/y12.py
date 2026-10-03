import os, subprocess, sys, re, numpy as np
positions = [int(x) for x in sys.argv[1].split(",")]
B = os.path.expanduser("~/libcamera-build/libcamera-0.7.1/build/src/ipa/ipu3")
print("lens     y1 variance     y2 variance")
for p in positions:
    open("/dev/shm/afpos", "w").write(str(p))
    env = dict(os.environ, LIBCAMERA_IPA_MODULE_PATH=B, LIBCAMERA_LOG_LEVELS="IPU3Af:DEBUG")
    r = subprocess.run(["timeout", "-s", "KILL", "40", "cam", "-c", "1", "--capture=70", "-s", "width=1600,height=1200,pixelformat=NV12"], env=env, capture_output=True, text=True)
    v = re.findall(r"HOOK focus %d y1 ([0-9.e+]+) y2 ([0-9.e+]+)" % p, r.stderr)
    a = np.array([[float(x), float(y)] for x, y in v[-12:]])
    print("%4d  %14.0f  %14.0f" % (p, np.median(a[:, 0]), np.median(a[:, 1])), flush=True)
os.remove("/dev/shm/afpos")
