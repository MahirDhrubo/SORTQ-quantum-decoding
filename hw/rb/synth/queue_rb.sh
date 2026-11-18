#!/bin/bash
# Test 2f Vivado queue (tmux sortq_queue, window rb): waits until the other session's re-synthesis lane has finished
# ("fix lane finished" in ../../synth/logs/queue.log), then engine_top_rb at 2.5 ns and at the estimated fmax.
# 4 threads. Log: logs/queue_rb.log; runs in runs/<run>[_fmax].
cd "$(dirname "$0")"; mkdir -p logs runs; mkdir -p logs runs
L=logs/queue_rb.log
v() { echo "$(date -u '+%F %T') $*" >> $L; }
v "waiting for the re-synthesis job"
while ! grep -q "fix lane finished" ../../synth/logs/queue.log 2>/dev/null; do sleep 120; done
v "re-synthesis done, starting"
[ -n "$XILINX_SETTINGS" ] && source "$XILINX_SETTINGS" > /dev/null 2>&1   # else vivado must be on PATH
run1() {   # run period tag
  d=runs/$1${3:+_$3}; mkdir -p $d
  [ -f $d/result.txt ] && { v "skip $d (done)"; return; }
  v "start $1 period $2"
  ( cd $d && vivado -mode batch -nojournal -log vivado.log -source ../../run_block_rb.tcl -tclargs $1 $2 4 . 1 > stdout.txt 2>&1 )
  v "end $d $(grep -h '^wns' $d/result.txt 2>/dev/null || echo FAILED)"
}
for r in ${RUNS:-engine_top_rb}; do
  run1 $r 2.5
  w=$(grep "^wns" runs/$r/result.txt | cut -d" " -f2)
  p=$(python3 -c "import math; print(f\"{math.ceil((2.5 - ($w)) * 100 - 1e-9) / 100:.2f}\")")
  v "fmax rerun $r: wns $w -> period $p"
  run1 $r $p fmax
  # retry until a confirmation run closes (period + |WNS|, at most 3 retries), so the queue never stops on a miss
  t=fmax
  for k in 2 3 4; do
    w=$(grep "^wns" runs/${r}_$t/result.txt | cut -d" " -f2)
    python3 -c "import sys; sys.exit(0 if float(\"$w\") >= 0 else 1)" && break
    p=$(python3 -c "import math; print(f\"{math.ceil(($p - ($w)) * 100 - 1e-9) / 100:.2f}\")")
    v "confirmation $t missed (wns $w) -> retry at $p"
    t=fmax$k; run1 $r $p $t
  done
done
v "rb queue finished"
