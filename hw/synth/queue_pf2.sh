#!/bin/bash
# Test 2c follow-up queue: engine_top_pf2 (VNU_PASSES 1 / 2, LUTRAM) at 2.5 ns, then at the estimated fmax.
# 2 lanes x 4 threads = 8 cores. Usage: ./queue_pf2.sh 1|2
cd "$(dirname "$0")"
./queue_2c.sh engine_top_pf2_p$1_lutram
./rerun_fmax.sh engine_top_pf2_p$1_lutram
echo "$(date -u '+%F %T') pf2 lane $1 finished" >> logs/queue.log
