#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000
CAM=${1:-LNK0}
rm -rf /dev/shm/pf; mkdir -p /dev/shm/pf
toolbox run -c cam-test timeout 40 gst-launch-1.0 -q pipewiresrc target-object=libcamera_input.__SB_.PCI0.$CAM num-buffers=130 ! videoconvert ! video/x-raw,format=RGB,width=1152,height=864 ! multifilesink location=/dev/shm/pf/f-%03d.raw >/dev/null 2>&1
toolbox run -c cam-test python3 - <<'PY'
import numpy as np
a = np.fromfile('/dev/shm/pf/f-129.raw', dtype=np.uint8).reshape(864, 1152, 3).astype(float)
yy, xx = np.mgrid[0:864, 0:1152]
rad = np.hypot((xx - 576) / 576, (yy - 432) / 432)
k = np.minimum((rad * 5).astype(int), 6)
cen = a[k == 0].mean(0)
print("centre RGB %.0f %.0f %.0f" % tuple(cen))
print("R/G rel:", " ".join("%.2f" % ((a[k==i].mean(0)[0]/a[k==i].mean(0)[1])/(cen[0]/cen[1])) for i in range(7)))
print("B/G rel:", " ".join("%.2f" % ((a[k==i].mean(0)[2]/a[k==i].mean(0)[1])/(cen[2]/cen[1])) for i in range(7)))
print("G  rel :", " ".join("%.2f" % (a[k==i].mean(0)[1]/cen[1]) for i in range(7)))
PY
rm -rf /dev/shm/pf
