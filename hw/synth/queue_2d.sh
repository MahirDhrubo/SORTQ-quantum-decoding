#!/bin/bash
# Test 2d calibration runs (cnu / vnu at the X decoder's other degrees), 2 lanes x 4 threads, 2.5 ns.
cd "$(dirname "$0")"
case $1 in
  A) ./queue_2c.sh cnu_d16 vnu_d2 vnu_d4 ;;
  B) ./queue_2c.sh cnu_d25 vnu_d3 vnu_d5 ;;
esac
echo "$(date -u '+%F %T') 2d lane $1 finished" >> logs/queue.log
