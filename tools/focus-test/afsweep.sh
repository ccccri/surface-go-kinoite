#!/bin/bash
# usage: afsweep.sh <label> [max=720] [step=12]   (needs the afhook2 build running as WirePlumber IPA; static scene!)
export XDG_RUNTIME_DIR=/run/user/1000
L=${1:-s}; MAX=${2:-720}; ST=${3:-12}
rm -rf /dev/shm/sw; mkdir -p /dev/shm/sw; rm -f /dev/shm/afpos /dev/shm/swpos.txt
N=$(( (MAX/ST+1) * 2 + 20 ))
toolbox run -c cam-test timeout $((N+20)) gst-launch-1.0 -q pipewiresrc target-object=libcamera_input.__SB_.PCI0.LNK0 ! videoconvert ! video/x-raw,format=GRAY8,width=1152,height=864 ! videorate ! video/x-raw,framerate=3/1 ! multifilesink location=/dev/shm/sw/f-%04d.raw >/dev/null 2>&1 &
sleep 6
S=$(date +%s)
for p in $(seq 0 $ST $MAX); do
  echo $p > /dev/shm/afpos
  echo "$(date +%s.%N) $p" >> /dev/shm/swpos.txt
  sleep 1.0
done
rm -f /dev/shm/afpos
sleep 2
journalctl --user -u wireplumber --since "@$S" --no-pager | grep "HOOK" | sed 's/.*HOOK //' > /dev/shm/swvar.txt
pkill -x gst-launch-1.0
toolbox run -c cam-test python3 - $L <<'PY'
import numpy as np, glob, os, sys, collections
pos=[(float(a),int(b)) for a,b in (l.split() for l in open('/dev/shm/swpos.txt'))]
var=collections.defaultdict(list)
for l in open('/dev/shm/swvar.txt'):
    p,v=l.split(); var[int(p)].append(float(v))
fs=sorted(glob.glob('/dev/shm/sw/f-*.raw'))
res=collections.defaultdict(list)
for f in fs:
    t=os.stat(f).st_mtime
    cur=None
    for ts,p in pos:
        if ts+0.5<=t<ts+1.05: cur=p     # frames taken 0.5..1.05 s after the lens command
    if cur is None: continue
    a=np.fromfile(f,dtype=np.uint8).reshape(864,1152).astype(float)[216:648,288:864]
    gx=np.diff(a,axis=1); gy=np.diff(a,axis=0)
    res[cur].append((gx**2).mean()+(gy**2).mean())
print("pos  image-sharpness  AF-variance")
rows=[]
for ts,p in pos:
    if p in res:
        rows.append((p,np.mean(res[p]),np.median(var[p][-3:]) if var[p] else 0))
mx=max(r[1] for r in rows); mv=max(r[2] for r in rows) or 1
for p,s,v in rows: print("%4d  %5.2f %s  %5.2f"%(p,s/mx,"#"*int(30*s/mx),v/mv))
bi=max(rows,key=lambda r:r[1]); bv=max(rows,key=lambda r:r[2])
print("IMAGE peak at",bi[0],"  AF-variance peak at",bv[0])
PY
