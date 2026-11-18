#!/bin/bash
# Test 2f: second confirmation run of engine_top_rb (4.90 ns missed by 0.345 ns) at 4.90 + 0.345 -> 5.25 ns. 4 threads.
cd "$(dirname "$0")"; mkdir -p logs runs; L=logs/queue_rb.log
v() { echo "$(date -u "+%F %T") $*" >> $L; }
[ -n "$XILINX_SETTINGS" ] && source "$XILINX_SETTINGS" > /dev/null 2>&1   # else vivado must be on PATH
d=runs/engine_top_rb_fmax2; mkdir -p $d
v "start engine_top_rb period 5.25"
( cd $d && vivado -mode batch -nojournal -log vivado.log -source ../../run_block_rb.tcl -tclargs engine_top_rb 5.25 4 . 1 > stdout.txt 2>&1 )
v "end $d $(grep -h "^wns" $d/result.txt 2>/dev/null || echo FAILED)"
