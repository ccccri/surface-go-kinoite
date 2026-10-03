#!/bin/bash
# AF trials from forced start positions on a static scene: usage aftrial2.sh "100 600 ..." 
export XDG_RUNTIME_DIR=/run/user/1000
STARTS=${1:-"20 100 200 450 600 700"}
rm -f /dev/shm/afpos
toolbox run -c cam-test timeout 400 gst-launch-1.0 -q pipewiresrc target-object=libcamera_input.__SB_.PCI0.LNK0 ! videoconvert ! fakesink >/dev/null 2>&1 &
sleep 8
echo "start -> final | time to settle | log"
for st in $STARTS; do
  echo $st > /dev/shm/afpos; sleep 2.5
  T0=$(date +%s.%N); rm -f /dev/shm/afpos
  sleep 7
  F=$(toolbox run -c cam-test v4l2-ctl -d /dev/v4l-subdev9 -C focus_absolute | awk '{print $2}')
  J=$(journalctl --user -u wireplumber --since "@${T0%.*}" --no-pager | grep -E "Local search ends|Parked|full scan" | sed 's/.*IPU3Af af.cpp:[0-9]* //' | tr '\n' ';' | cut -c1-200)
  echo "$st -> $F  | $J"
done
pkill -x gst-launch-1.0
