#!/bin/bash
# Test 2f timing-closure queue (tmux sortq_queue window tc): synth once, then 4 implementation variants in parallel at
# 4.76 ns (4 threads each). A variant that misses is re-run at period + |WNS| (rounded up to 0.01 ns) until it closes
# (at most 3 retries), each variant in its own lane. Log: tc/queue_tc.log; runs in tc/runs/<variant>_<period>.
cd "$(dirname "$0")"; mkdir -p runs
L=queue_tc.log
v() { echo "$(date -u '+%F %T') $*" >> $L; }
[ -n "$XILINX_SETTINGS" ] && source "$XILINX_SETTINGS" > /dev/null 2>&1   # else vivado must be on PATH
TARGET=${TARGET:-4.76}
if [ ! -f synth.dcp ]; then
  v "synth start"
  vivado -mode batch -nojournal -log synth.log -source synth_dcp.tcl > synth.out 2>&1
  [ -f synth.dcp ] || { v "synth FAILED"; exit 1; }
  v "synth done ($(grep -o 'SYNTH_DONE [0-9]*' synth.out))"
fi
lane() {   # variant place_directive
  local name=$1 pdir=$2 p=$TARGET
  for k in 0 1 2 3; do
    d=runs/${name}_$p; mkdir -p $d
    if [ ! -f $d/result.txt ]; then
      v "start $name ($pdir) period $p"
      ( cd $d && vivado -mode batch -nojournal -log vivado.log -source ../../impl.tcl -tclargs $p $pdir . > stdout.txt 2>&1 )
    fi
    w=$(grep "^wns " $d/result.txt 2>/dev/null | cut -d" " -f2)
    [ -z "$w" ] && { v "end $name $p FAILED"; return; }
    v "end $name period $p wns $w"
    python3 -c "import sys; sys.exit(0 if float('$w') >= 0 else 1)" && { v "$name closes at $p"; return; }
    p=$(python3 -c "import math; print(f'{math.ceil(($p - ($w)) * 100 - 1e-9) / 100:.2f}')")
  done
  v "$name: no closure after retries"
}
lane A_explore Explore &
lane B_extratiming ExtraTimingOpt &
lane C_extranetdelay ExtraNetDelay_high &
lane D_wldriven WLDrivenBlockPlacement &
wait
v "tc queue finished"
