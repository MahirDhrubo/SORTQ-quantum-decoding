#!/bin/bash
# 2c re-synthesis with the Test 3d fixes: engine_top_pf2 (VNU_PASSES 1, LUTRAM) at 2.5 ns, then at the estimated fmax,
# then collect.py. 4 threads. Runs in tmux sortq_queue.
cd "$(dirname "$0")"
./queue_2c.sh engine_top_pf2fix_p1_lutram
./rerun_fmax.sh engine_top_pf2fix_p1_lutram
python3 collect.py runs results.json > logs/collect_fix.log 2>&1
echo "$(date -u '+%F %T') fix lane finished" >> logs/queue.log
