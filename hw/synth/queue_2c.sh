#!/bin/bash
# Test 2c queue: two lanes of Vivado runs in parallel, 4 threads each (8 cores total). Runs in tmux sortq_queue.
# Usage: ./queue_2c.sh A|B   -> runs that lane's list in order; status in runs/<run>/status, log runs/<run>/vivado.log
cd "$(dirname "$0")"; mkdir -p logs runs
[ -n "$XILINX_SETTINGS" ] && source "$XILINX_SETTINGS" > /dev/null 2>&1   # else vivado must be on PATH
PERIOD=${PERIOD:-2.5}
case $1 in
  A) LIST="engine_top_p1_bram engine_top_p1_lutram engine_top_p2_bram engine_top_p2_lutram" ;;
  B) LIST="cnu vnu vnu_nosat gamma_src prior_rf conv_check ctrl commit rot2d state_mem_reg state_mem_lutram state_mem_bram round_step_p1 round_step_p2" ;;
  *) LIST="$*" ;;
esac
for r in $LIST; do
  d=runs/${r}${TAG:+_$TAG}; mkdir -p $d
  [ -f $d/result.txt ] && { echo "$(date -u '+%F %T') skip $r (done)" >> logs/queue.log; continue; }
  echo running > $d/status
  echo "$(date -u '+%F %T') start $r period $PERIOD" >> logs/queue.log
  dcp=0; [[ $r == engine_top* ]] && dcp=1
  ( cd $d && vivado -mode batch -nojournal -log vivado.log -source ../../run_block.tcl -tclargs $r $PERIOD 4 . $dcp > stdout.txt 2>&1 )
  if [ -f $d/result.txt ]; then echo done > $d/status; else echo failed > $d/status; fi
  echo "$(date -u '+%F %T') end $r $(cat $d/status) $(grep -h '^wns' $d/result.txt 2>/dev/null)" >> logs/queue.log
done
echo "$(date -u '+%F %T') lane $1 finished" >> logs/queue.log
