#!/bin/bash
# closed loop: flatten R/G and B/G radially. usage: calib.sh <LNK0|LNK1> <iterations> <power>
export XDG_RUNTIME_DIR=/run/user/1000
CAM=${1:-LNK0}; ITER=${2:-5}; P=${3:-0.6}; PG=${4:-1.0}
R=$HOME/libcamera-build/libcamera-0.7.1/build
printf "[Service]\nEnvironment=LD_LIBRARY_PATH=%s/src/libcamera:%s/src/libcamera/base\nEnvironment=LIBCAMERA_IPA_MODULE_PATH=%s/src/ipa/ipu3\nEnvironment=LIBCAMERA_IPA_PROXY_PATH=%s/src/libcamera/proxy/worker\nEnvironment=LIBCAMERA_IPA_CONFIG_PATH=/etc/libcamera/ipa\n" $R $R $R $R > ~/.config/systemd/user/wireplumber.service.d/zz-dbg.conf
systemctl --user daemon-reload; systemctl --user restart wireplumber; sleep 5
echo "1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1" > /dev/shm/lscextra
for it in $(seq 0 $ITER); do
  rm -rf /dev/shm/cl; mkdir -p /dev/shm/cl
  toolbox run -c cam-test timeout 40 gst-launch-1.0 -q pipewiresrc target-object=libcamera_input.__SB_.PCI0.$CAM num-buffers=100 ! videoconvert ! video/x-raw,format=RGB,width=1152,height=864 ! multifilesink location=/dev/shm/cl/f-%03d.raw >/dev/null 2>&1
  toolbox run -c cam-test python3 - $it $P $PG <<'PY'
import numpy as np, sys
it, P, PG = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
a = np.fromfile('/dev/shm/cl/f-099.raw', dtype=np.uint8).reshape(864, 1152, 3).astype(float)
yy, xx = np.mgrid[0:864, 0:1152]
rad = np.hypot((xx - 576) / 576, (yy - 432) / 432)          # output frame radius, corner = 1.41
k = np.minimum((rad * 5).astype(int), 6)                     # rings of 0.2
cen = a[k == 0].mean(0)
rg = np.zeros(7); bg = np.zeros(7); g = np.zeros(7)
for i in range(7):
    c = a[k == i].mean(0)
    rg[i] = (c[0]/c[1])/(cen[0]/cen[1]); bg[i] = (c[2]/c[1])/(cen[2]/cen[1]); g[i] = c[1]/cen[1]
cur = [float(x) for x in open('/dev/shm/lscextra').read().split()]
fr, fb, fg = np.array(cur[:8]), np.array(cur[8:16]), np.array(cur[16:24])
print("iter %d centre %.0f %.0f %.0f | R/G %s | B/G %s | G %s" % (it, *cen, " ".join("%.2f" % v for v in rg), " ".join("%.2f" % v for v in bg), " ".join("%.2f" % v for v in g)))
# the output frame covers BDS radius ~0.8 * output radius: extra table is in BDS-normalised units (0.2 steps)
# ring i (output radius 0.2 i..0.2 i+0.2) -> BDS radius 0.16 i..; update the table points by interpolation in BDS units
rb = np.array([0.8 * (0.1 + 0.2 * i) for i in range(7)])       # BDS radius of the ring centres
pts = np.arange(8) * 0.2
need_r = (1.0 / rg) ** P; need_b = (1.0 / bg) ** P; need_g = (1.0 / g) ** PG
nr = np.interp(pts, rb, need_r); nb = np.interp(pts, rb, need_b); ng = np.interp(pts, rb, need_g)  # clamps beyond the measured range
fr2 = fr * nr; fb2 = fb * nb; fg2 = fg * ng
fr2[0] = fb2[0] = fg2[0] = 1.0
open('/dev/shm/lscextra', 'w').write(" ".join("%.4f" % v for v in list(fr2) + list(fb2) + list(fg2)))
PY
done
echo "FINAL extra (BDS radius 0,0.2,...,1.4): $(cat /dev/shm/lscextra)"
cp /dev/shm/lscextra /tmp/lscextra.$CAM
rm -rf /dev/shm/cl
