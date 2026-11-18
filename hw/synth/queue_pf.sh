#!/bin/bash
# Test 2c follow-up queue (timing variant *_pf), 2 lanes x 4 threads = 8 cores, after the runs in flight.
# Usage: ./queue_pf.sh A <pid to wait for> | B <pid to wait for>
cd "$(dirname "$0")"
lane=$1; w=$2
while ps -p $w > /dev/null 2>&1; do sleep 60; done
case $lane in
  A) ./queue_2c.sh engine_top_pf_p1_lutram
     ./rerun_fmax.sh engine_top_p2_bram
     ./rerun_fmax.sh engine_top_pf_p1_lutram ;;
  B) ./queue_2c.sh round_step_pf_p1 ctrl_pf
     ./rerun_fmax.sh engine_top_p1_lutram
     ./rerun_fmax.sh round_step_pf_p1
     ./queue_2c.sh round_step_pf_p2 ;;
esac
echo "$(date -u '+%F %T') pf lane $lane finished" >> logs/queue.log
